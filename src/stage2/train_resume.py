"""Trainer-side contracts for Stage 2 full-state checkpoint integration.

This module owns the deterministic scheduling, binding, append-only CSV cursor,
and non-model runtime state that sit between ``train.py`` and ``checkpoint.py``.
Keeping these mechanics separate makes them testable without constructing a
COLMAP dataset or launching a renderer.
"""
from __future__ import annotations

import hashlib
import json
import os
import random
import tempfile
from pathlib import Path
from typing import Any, Mapping, Sequence


FULL_STATE_REQUIRED_STEPS = (5000, 10000, 15000, 20000)
FULL_STATE_RUNTIME_SCHEMA = "jointbuildgs.stage2.trainer_runtime.v1"
FULL_STATE_LOSS_CURSOR_SCHEMA = "jointbuildgs.stage2.loss_csv_cursor.v1"
FULL_STATE_MANIFEST_SCHEMA = "jointbuildgs.stage2.resume_manifest.v1"
PUBLISHED_FILE_MODE = 0o644
FULL_STATE_DEFAULT_LOSS_CSV_PATHS = (
    "audit/loss_grad_norms.csv",
    "audit/semantic_geometry.csv",
    "audit/semantic_target_observations.csv",
)
FULL_STATE_BINDING_EXCLUDED_CONFIG_KEYS = frozenset(
    {
        # Operational selectors may change from auto to an explicit file without
        # changing the learned experiment being resumed.
        "full_state_resume",
        "full_state_resume_strict_cuda_rng",
    }
)


def full_state_options(cfg: Mapping[str, Any]) -> dict[str, Any]:
    """Parse opt-in resume/checkpoint controls without changing legacy defaults."""

    raw_resume = cfg.get("full_state_resume")
    if raw_resume is False or raw_resume is None:
        resume_request = None
    elif isinstance(raw_resume, str) and raw_resume.strip().lower() in {
        "",
        "off",
        "none",
        "false",
    }:
        resume_request = None
    elif isinstance(raw_resume, str):
        resume_request = raw_resume.strip()
    else:
        raise ValueError(
            "full_state_resume must be absent/off, 'auto', 'latest', or a checkpoint path"
        )

    enabled = bool(cfg.get("full_state_checkpoint", False) or resume_request)
    configured_steps = cfg.get("full_state_checkpoint_steps") or []
    if not isinstance(configured_steps, (list, tuple)):
        raise ValueError("full_state_checkpoint_steps must be a list of positive integers")
    steps: set[int] = set()
    for raw_step in configured_steps:
        if isinstance(raw_step, bool) or not isinstance(raw_step, int) or raw_step <= 0:
            raise ValueError(
                "full_state_checkpoint_steps must contain only positive integers"
            )
        steps.add(int(raw_step))
    if enabled:
        # The first-wave guard contract cannot silently drop any required save.
        steps.update(FULL_STATE_REQUIRED_STEPS)

    extra_loss_paths = cfg.get("full_state_loss_csv_paths") or []
    if not isinstance(extra_loss_paths, (list, tuple)):
        raise ValueError("full_state_loss_csv_paths must be a list of relative paths")
    loss_paths = list(FULL_STATE_DEFAULT_LOSS_CSV_PATHS)
    for raw_path in extra_loss_paths:
        if not isinstance(raw_path, str) or not raw_path.strip():
            raise ValueError(
                "full_state_loss_csv_paths must contain non-empty relative paths"
            )
        loss_paths.append(raw_path.strip())
    normalized_loss_paths = tuple(
        sorted({normalize_relative_output_path(path) for path in loss_paths})
    )

    return {
        "enabled": enabled,
        "resume_request": resume_request,
        "checkpoint_steps": tuple(sorted(steps)),
        "loss_csv_paths": normalized_loss_paths,
        "strict_cuda_rng": bool(cfg.get("full_state_resume_strict_cuda_rng", True)),
    }


def normalize_relative_output_path(value: str) -> str:
    path = Path(value)
    if path.is_absolute() or not path.parts:
        raise ValueError(f"full-state output cursor path must be relative: {value!r}")
    if ".." in path.parts:
        raise ValueError(
            f"full-state output cursor path cannot escape the output directory: {value!r}"
        )
    normalized = Path(os.path.normpath(str(path)))
    if normalized == Path(".") or ".." in normalized.parts:
        raise ValueError(
            f"full-state output cursor path cannot escape the output directory: {value!r}"
        )
    return normalized.as_posix()


def output_relative_path(out_dir: Path, relative_path: str) -> Path:
    normalized = normalize_relative_output_path(relative_path)
    root = out_dir.resolve()
    target = (root / normalized).resolve(strict=False)
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise ValueError(
            f"full-state cursor path escapes output directory: {relative_path!r}"
        ) from exc
    return target


def _json_sha256(value: Any) -> str:
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def full_state_binding_sha256(
    *,
    cfg: Mapping[str, Any],
    effective_training_config: Mapping[str, Any],
    out_dir: Path,
) -> dict[str, str]:
    """Bind learned state while excluding only resume transport selectors."""

    bound_config = {
        key: value
        for key, value in cfg.items()
        if key not in FULL_STATE_BINDING_EXCLUDED_CONFIG_KEYS
    }
    output_path = str(out_dir.resolve())
    return {
        "training_config": _json_sha256(bound_config),
        "effective_training_config": _json_sha256(effective_training_config),
        "output_path": hashlib.sha256(output_path.encode("utf-8")).hexdigest(),
    }


def _sha256_prefix(path: Path, size_bytes: int) -> str:
    digest = hashlib.sha256()
    remaining = int(size_bytes)
    with path.open("rb") as stream:
        while remaining:
            chunk = stream.read(min(1024 * 1024, remaining))
            if not chunk:
                raise RuntimeError(
                    f"loss CSV {path} ended before saved cursor {size_bytes} bytes"
                )
            digest.update(chunk)
            remaining -= len(chunk)
    return digest.hexdigest()


def capture_loss_csv_cursor(
    out_dir: Path,
    relative_paths: Sequence[str],
    *,
    completed_steps: int,
) -> dict[str, Any]:
    """Capture closed append-only loss CSV positions at a checkpoint boundary."""

    files: dict[str, dict[str, Any]] = {}
    for relative_path in relative_paths:
        normalized = normalize_relative_output_path(relative_path)
        path = output_relative_path(out_dir, normalized)
        if path.exists():
            if not path.is_file():
                raise RuntimeError(f"loss CSV cursor target is not a file: {path}")
            size_bytes = path.stat().st_size
            files[normalized] = {
                "exists": True,
                "size_bytes": int(size_bytes),
                "prefix_sha256": _sha256_prefix(path, size_bytes),
            }
        else:
            files[normalized] = {
                "exists": False,
                "size_bytes": 0,
                "prefix_sha256": None,
            }
    return {
        "schema": FULL_STATE_LOSS_CURSOR_SCHEMA,
        "completed_steps": int(completed_steps),
        "files": files,
    }


def empty_loss_csv_cursor(relative_paths: Sequence[str]) -> dict[str, Any]:
    """Return the only valid zero-step cursor for a fresh pre-checkpoint retry."""

    normalized = sorted(
        {normalize_relative_output_path(path) for path in relative_paths}
    )
    return {
        "schema": FULL_STATE_LOSS_CURSOR_SCHEMA,
        "completed_steps": 0,
        "files": {
            path: {
                "exists": False,
                "size_bytes": 0,
                "prefix_sha256": None,
            }
            for path in normalized
        },
    }


def restore_loss_csv_cursor(
    out_dir: Path,
    relative_paths: Sequence[str],
    cursor: Mapping[str, Any],
    *,
    expected_completed_steps: int,
) -> list[str]:
    """Validate checkpoint prefixes and remove only uncheckpointed CSV tails."""

    if cursor.get("schema") != FULL_STATE_LOSS_CURSOR_SCHEMA:
        raise RuntimeError(f"unsupported loss CSV cursor schema: {cursor.get('schema')!r}")
    if int(cursor.get("completed_steps", -1)) != int(expected_completed_steps):
        raise RuntimeError(
            "loss CSV cursor/checkpoint step mismatch: "
            f"cursor={cursor.get('completed_steps')}, checkpoint={expected_completed_steps}"
        )
    files = cursor.get("files")
    if not isinstance(files, Mapping):
        raise RuntimeError("loss CSV cursor files must be a mapping")
    expected_paths = {normalize_relative_output_path(path) for path in relative_paths}
    if set(files) != expected_paths:
        raise RuntimeError(
            "loss CSV cursor path mismatch: "
            f"cursor={sorted(files)}, config={sorted(expected_paths)}"
        )

    actions: list[str] = []
    touched_parents: set[Path] = set()
    for relative_path in sorted(expected_paths):
        record = files[relative_path]
        if not isinstance(record, Mapping):
            raise RuntimeError(f"malformed loss CSV cursor for {relative_path}")
        path = output_relative_path(out_dir, relative_path)
        expected_exists = record.get("exists") is True
        expected_size = int(record.get("size_bytes", -1))
        expected_sha = record.get("prefix_sha256")
        if expected_size < 0:
            raise RuntimeError(f"invalid loss CSV byte cursor for {relative_path}")

        if not expected_exists:
            if expected_size != 0 or expected_sha is not None:
                raise RuntimeError(f"inconsistent absent loss CSV cursor for {relative_path}")
            if path.exists():
                if not path.is_file():
                    raise RuntimeError(f"loss CSV rollback target is not a file: {path}")
                path.unlink()
                touched_parents.add(path.parent)
                actions.append(f"removed post-checkpoint file {relative_path}")
            continue

        if not isinstance(expected_sha, str) or len(expected_sha) != 64:
            raise RuntimeError(f"invalid loss CSV prefix SHA for {relative_path}")
        if not path.is_file():
            raise RuntimeError(f"loss CSV required by checkpoint is missing: {path}")
        actual_size = path.stat().st_size
        if actual_size < expected_size:
            raise RuntimeError(
                f"loss CSV {relative_path} is shorter than checkpoint cursor: "
                f"actual={actual_size}, expected>={expected_size}"
            )
        actual_sha = _sha256_prefix(path, expected_size)
        if actual_sha != expected_sha:
            raise RuntimeError(
                f"loss CSV prefix changed before checkpoint cursor for {relative_path}: "
                f"expected={expected_sha}, actual={actual_sha}"
            )
        if actual_size > expected_size:
            with path.open("r+b") as stream:
                stream.truncate(expected_size)
                stream.flush()
                os.fsync(stream.fileno())
            touched_parents.add(path.parent)
            actions.append(
                f"truncated {relative_path} from {actual_size} to {expected_size} bytes"
            )

    for parent in touched_parents:
        fsync_output_directory(parent)
    return actions


def capture_trainer_runtime_state(
    *,
    structure_groups: Mapping[str, Any],
    semantic_geometry: Any,
    semantic_target_observations: Mapping[str, int],
    semantic_pi_audited_targets: set[str],
) -> dict[str, Any]:
    """Capture every mutable non-model trainer object that affects continuation."""

    return {
        "schema": FULL_STATE_RUNTIME_SCHEMA,
        "structure_groups": dict(structure_groups),
        "semantic_geometry_planes": (
            None if semantic_geometry is None else dict(semantic_geometry._planes)
        ),
        "semantic_target_observations": {
            str(key): int(value)
            for key, value in semantic_target_observations.items()
        },
        "semantic_pi_audited_targets": sorted(semantic_pi_audited_targets),
    }


def restore_trainer_runtime_state(
    saved: Mapping[str, Any],
    *,
    semantic_geometry: Any,
    expected_semantic_targets: set[str],
) -> tuple[dict[str, Any], dict[str, int], set[str]]:
    if saved.get("schema") != FULL_STATE_RUNTIME_SCHEMA:
        raise RuntimeError(f"unsupported trainer runtime schema: {saved.get('schema')!r}")
    structure_groups = saved.get("structure_groups")
    if not isinstance(structure_groups, Mapping) or set(structure_groups) != {
        "group_ids",
        "rep_n",
        "rep_d",
    }:
        raise RuntimeError("saved structure grouping state is malformed")
    planes = saved.get("semantic_geometry_planes")
    if semantic_geometry is None:
        if planes not in (None, {}):
            raise RuntimeError(
                "checkpoint contains semantic plane state but current config disables it"
            )
    else:
        if not isinstance(planes, Mapping):
            raise RuntimeError("checkpoint semantic plane state is malformed")
        semantic_geometry._planes = dict(planes)

    observations = saved.get("semantic_target_observations")
    if not isinstance(observations, Mapping) or set(observations) != expected_semantic_targets:
        raise RuntimeError(
            "semantic target observation keys differ from the bound configuration"
        )
    restored_observations: dict[str, int] = {}
    for key, value in observations.items():
        count = int(value)
        if count < 0:
            raise RuntimeError("semantic target observation counts must be non-negative")
        restored_observations[str(key)] = count
    raw_audited = saved.get("semantic_pi_audited_targets")
    if not isinstance(raw_audited, (list, tuple, set)):
        raise RuntimeError("saved semantic audited targets are malformed")
    audited = {str(value) for value in raw_audited}
    if not audited.issubset(expected_semantic_targets):
        raise RuntimeError("saved semantic audited targets are outside the configured set")
    return dict(structure_groups), restored_observations, audited


def training_view_index(
    train_indices: Sequence[int], *, iteration: int, sequential: bool
) -> int:
    """Select a view using the zero-based update index preserved across resume."""

    if not train_indices:
        raise ValueError("training view index is empty")
    if sequential:
        return int(train_indices[iteration % len(train_indices)])
    return int(random.choice(train_indices))


def full_state_checkpoint_due(
    full_state: Mapping[str, Any], *, completed_steps: int
) -> bool:
    return bool(
        full_state.get("enabled")
        and int(completed_steps) in full_state.get("checkpoint_steps", ())
    )


def learning_runs_for_process(
    prior_count: int, *, resuming: bool, will_train: bool
) -> tuple[int, bool]:
    """Increment once for a fresh learning start and never for a resume."""

    if isinstance(prior_count, bool) or not isinstance(prior_count, int) or prior_count < 0:
        raise ValueError("prior learning run count must be a non-negative integer")
    increment = bool(will_train and not resuming)
    return prior_count + int(increment), increment


def read_learning_runs_started(manifest_path: Path) -> int:
    if not manifest_path.exists():
        return 0
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"cannot read full-state manifest {manifest_path}: {exc}") from exc
    if payload.get("schema") != FULL_STATE_MANIFEST_SCHEMA:
        raise RuntimeError(f"unsupported full-state manifest schema in {manifest_path}")
    value = payload.get("learning_runs_started")
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise RuntimeError(f"invalid learning_runs_started in {manifest_path}")
    return int(value)


def atomic_write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, raw_tmp = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    tmp_path = Path(raw_tmp)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            descriptor = -1
            json.dump(payload, stream, indent=2, sort_keys=True)
            stream.write("\n")
            os.fchmod(stream.fileno(), PUBLISHED_FILE_MODE)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(tmp_path, path)
        fsync_output_directory(path.parent)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        try:
            tmp_path.unlink()
        except FileNotFoundError:
            pass


def fsync_output_directory(directory: Path) -> None:
    descriptor = os.open(directory, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
