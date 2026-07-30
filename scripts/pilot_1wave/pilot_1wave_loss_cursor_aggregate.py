#!/usr/bin/env python3
"""Build the P1W loss-share aggregate from exact 20k checkpoint cursors.

The checkpoint payload, not the live CSV length, is authoritative.  Every
source CSV is read at the byte cursor stored in ``loss_log_cursor`` and is
accepted only when the completed 20k file has exactly that length and prefix
SHA-256.  The script is CPU-only and publishes immutable, deterministic files:
an aggregate CSV, ten per-run receipts, and one aggregate receipt.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import os
from pathlib import Path
import re
import tempfile
from types import SimpleNamespace
from typing import Any, Callable, Mapping, Sequence


REPO = Path(__file__).resolve().parents[2]
RUN_ID = "20260721_pilot_1wave"
RUN_DIR = REPO / "phases/p2-gsjso/runs" / RUN_ID
DEFAULT_TRAINING_ROOT = RUN_DIR / "training/runs"
DEFAULT_OUTPUT = RUN_DIR / "pilot_1wave_loss_shares.csv"
DEFAULT_RECEIPT = RUN_DIR / "pilot_1wave_loss_shares.receipt.json"
DEFAULT_RUN_RECEIPT_DIR = RUN_DIR / "pilot_1wave_loss_share_receipts"
CONTAINER_REPO = Path("/workspace/JointBuildGS")

TASK_ID = "P1W-LOSS-CURSOR-AGGREGATE"
SCORING_SCHEMA_VERSION = "jointbuildgs.pilot_1wave.scoring.v1"
RUN_RECEIPT_SCHEMA = "jointbuildgs.pilot_1wave.loss_cursor_run_receipt.v1"
AGGREGATE_RECEIPT_SCHEMA = (
    "jointbuildgs.pilot_1wave.loss_cursor_aggregate_receipt.v1"
)
FULL_STATE_SCHEMA = "jointbuildgs.stage2.resume_manifest.v1"
LOSS_CURSOR_SCHEMA = "jointbuildgs.stage2.loss_csv_cursor.v1"
STEP_SEMANTICS = "completed_optimizer_updates"
CHECKPOINT_STEP = 20_000
CHECKPOINT_STEPS = (5_000, 10_000, 15_000, 20_000)
AUDIT_EVERY = 100
EXPECTED_ITER_COUNT = CHECKPOINT_STEP // AUDIT_EVERY
EXPECTED_ROWS_PER_RUN = 1_400
EXPECTED_TOTAL_ROWS = 14_000
EXPECTED_CONDITIONS = ("01", "02", "03", "04a", "04b")
EXPECTED_SEEDS = (1001, 1002)
EXPECTED_RUN_KEYS = tuple(
    (condition, seed)
    for condition in EXPECTED_CONDITIONS
    for seed in EXPECTED_SEEDS
)
LOSS_SHARE_RELATIVE_PATH = "audit/pilot_loss_shares.csv"
EXPECTED_LOSS_PATHS = (
    "audit/loss_grad_norms.csv",
    "audit/pilot_loss_details.csv",
    "audit/pilot_loss_shares.csv",
    "audit/pilot_plane_photo_ratio.csv",
    "audit/semantic_geometry.csv",
    "audit/semantic_target_observations.csv",
)
SOURCE_FIELDS = ("iter", "term", "raw", "weighted", "share", "roof_share")
LOSS_TERMS = ("pho", "dep", "nrm", "nc", "str.na", "str.cp", "plane")
OUTPUT_FIELDS = (
    "schema_version",
    "condition_id",
    "seed",
    "checkpoint_step",
    "checkpoint_sha256",
    "iter",
    "term",
    "raw",
    "weighted",
    "share",
    "roof_share",
)
BINDING_KEYS = {"training_config", "effective_training_config", "output_path"}
CURSOR_RECORD_KEYS = {"exists", "size_bytes", "prefix_sha256"}
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_SIDECAR_RE = re.compile(r"^([0-9a-f]{64})  (step_020000\.pt)\n$")


class AggregateError(RuntimeError):
    """A locked source, checkpoint, cursor, or immutable output is invalid."""


CheckpointLoader = Callable[..., Any]


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path, block_size: int = 1 << 20) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(block_size), b""):
            digest.update(block)
    return digest.hexdigest()


def _json_bytes(value: Any) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def _canonical_path(path: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(REPO.resolve()).as_posix()
    except ValueError:
        return str(resolved)


def _require_regular(path: Path, label: str) -> Path:
    if path.is_symlink():
        raise AggregateError(f"{label} must not be a symlink: {path}")
    if not path.is_file():
        raise AggregateError(f"{label} must be a regular file: {path}")
    return path.resolve()


def _resolve_declared_path(value: Any, *, declaring_file: Path) -> Path:
    text = str(value or "").strip()
    if not text:
        raise AggregateError(f"empty path declared by {declaring_file}")
    declared = Path(text)
    candidates: list[Path] = []
    if declared.is_absolute():
        candidates.append(declared)
        try:
            candidates.append(REPO / declared.relative_to(CONTAINER_REPO))
        except ValueError:
            pass
    else:
        candidates.extend((declaring_file.parent / declared, REPO / declared))
    existing = [candidate.resolve() for candidate in candidates if candidate.exists()]
    unique = {str(candidate) for candidate in existing}
    if not unique:
        raise AggregateError(
            f"declared path does not exist: {text!r} ({declaring_file})"
        )
    if len(unique) != 1:
        raise AggregateError(f"ambiguous declared path: {text!r} -> {sorted(unique)}")
    return Path(next(iter(unique)))


def _require_sha256(value: Any, label: str) -> str:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        raise AggregateError(f"{label} must be a lowercase SHA-256 digest")
    return value


def _require_exact(value: Any, expected: Any, label: str) -> None:
    if value != expected:
        raise AggregateError(f"{label} mismatch: {value!r} != {expected!r}")


def discover_locked_manifests(training_root: Path) -> dict[tuple[str, int], Path]:
    if training_root.is_symlink() or not training_root.is_dir():
        raise AggregateError(f"training root must be a non-symlink directory: {training_root}")
    found: dict[tuple[str, int], Path] = {}
    for manifest in sorted(training_root.glob("*/seed_*/full_state_manifest.json")):
        run_dir = manifest.parent
        condition_dir = run_dir.parent
        if manifest.is_symlink() or run_dir.is_symlink() or condition_dir.is_symlink():
            raise AggregateError(f"run layout must not contain symlinks: {manifest}")
        seed_match = re.fullmatch(r"seed_([0-9]+)", run_dir.name)
        if seed_match is None:
            raise AggregateError(f"invalid seed directory: {run_dir}")
        key = (condition_dir.name, int(seed_match.group(1)))
        if key in found:
            raise AggregateError(f"duplicate full-state manifest for run {key}")
        found[key] = _require_regular(manifest, "full-state manifest")
    expected = set(EXPECTED_RUN_KEYS)
    actual = set(found)
    if actual != expected:
        raise AggregateError(
            "locked run discovery mismatch: "
            f"missing={sorted(expected - actual)}, extra={sorted(actual - expected)}"
        )
    return {key: found[key] for key in EXPECTED_RUN_KEYS}


def _validate_binding(value: Any, *, output_path_text: str) -> dict[str, str]:
    if not isinstance(value, Mapping) or set(value) != BINDING_KEYS:
        raise AggregateError("full-state binding must contain exactly three locked keys")
    binding = {
        str(key): _require_sha256(digest, f"binding {key}")
        for key, digest in value.items()
    }
    expected_output = hashlib.sha256(output_path_text.encode("utf-8")).hexdigest()
    _require_exact(binding["output_path"], expected_output, "output-path binding")
    return binding


def _validate_cursor(cursor: Any) -> tuple[dict[str, Any], dict[str, Any]]:
    if not isinstance(cursor, Mapping) or set(cursor) != {
        "schema",
        "completed_steps",
        "files",
    }:
        raise AggregateError("checkpoint loss cursor shape changed")
    _require_exact(cursor.get("schema"), LOSS_CURSOR_SCHEMA, "loss cursor schema")
    _require_exact(
        int(cursor.get("completed_steps", -1)),
        CHECKPOINT_STEP,
        "loss cursor completed steps",
    )
    files = cursor.get("files")
    if not isinstance(files, Mapping) or tuple(sorted(files)) != EXPECTED_LOSS_PATHS:
        raise AggregateError(
            "checkpoint loss path set changed: "
            f"{sorted(files) if isinstance(files, Mapping) else files!r}"
        )
    normalized: dict[str, dict[str, Any]] = {}
    for relative_path in EXPECTED_LOSS_PATHS:
        record = files[relative_path]
        if not isinstance(record, Mapping) or set(record) != CURSOR_RECORD_KEYS:
            raise AggregateError(f"cursor record shape changed: {relative_path}")
        exists = record.get("exists")
        if not isinstance(exists, bool):
            raise AggregateError(f"cursor exists flag is not boolean: {relative_path}")
        size = record.get("size_bytes")
        if isinstance(size, bool) or not isinstance(size, int) or size < 0:
            raise AggregateError(f"cursor byte size is invalid: {relative_path}")
        digest = record.get("prefix_sha256")
        if exists:
            if size <= 0:
                raise AggregateError(f"present cursor has no bytes: {relative_path}")
            digest = _require_sha256(digest, f"cursor prefix {relative_path}")
        elif size != 0 or digest is not None:
            raise AggregateError(f"absent cursor record is inconsistent: {relative_path}")
        normalized[relative_path] = {
            "exists": exists,
            "size_bytes": size,
            "prefix_sha256": digest,
        }
    share = normalized[LOSS_SHARE_RELATIVE_PATH]
    if not share["exists"]:
        raise AggregateError("20k checkpoint has no pilot loss-share cursor")
    normalized_cursor = {
        "schema": LOSS_CURSOR_SCHEMA,
        "completed_steps": CHECKPOINT_STEP,
        "files": normalized,
    }
    return normalized_cursor, share


def _read_exact_completed_prefix(
    path: Path, *, size_bytes: int, prefix_sha256: str
) -> bytes:
    path = _require_regular(path, "loss-share CSV")
    with path.open("rb") as stream:
        before = os.fstat(stream.fileno())
        if before.st_size < size_bytes:
            raise AggregateError(
                f"loss-share CSV is shorter than checkpoint cursor: "
                f"actual={before.st_size}, expected={size_bytes}"
            )
        if before.st_size > size_bytes:
            raise AggregateError(
                f"loss-share CSV has an uncheckpointed tail: "
                f"actual={before.st_size}, checkpoint={size_bytes}"
            )
        data = stream.read(size_bytes)
        if len(data) != size_bytes:
            raise AggregateError("loss-share CSV was truncated while reading")
        if stream.read(1):
            raise AggregateError("loss-share CSV grew beyond the checkpoint cursor")
        after = os.fstat(stream.fileno())
    stable_before = (before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns)
    stable_after = (after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns)
    if stable_before != stable_after:
        raise AggregateError("loss-share CSV changed while reading")
    actual_sha = sha256_bytes(data)
    _require_exact(actual_sha, prefix_sha256, "loss-share checkpoint prefix SHA256")
    if not data.endswith(b"\n"):
        raise AggregateError("loss-share checkpoint cursor cuts through a CSV row")
    return data


def _parse_loss_rows(data: bytes) -> list[dict[str, str]]:
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise AggregateError(f"loss-share prefix is not UTF-8: {exc}") from exc
    reader = csv.DictReader(io.StringIO(text, newline=""))
    if tuple(reader.fieldnames or ()) != SOURCE_FIELDS:
        raise AggregateError(
            f"loss-share header changed: {tuple(reader.fieldnames or ())!r}"
        )
    rows = list(reader)
    if len(rows) != EXPECTED_ROWS_PER_RUN:
        raise AggregateError(
            f"loss-share row count is not exact 20k: {len(rows)} != {EXPECTED_ROWS_PER_RUN}"
        )
    expected_iters = list(range(AUDIT_EVERY, CHECKPOINT_STEP + 1, AUDIT_EVERY))
    for index, expected_iter in enumerate(expected_iters):
        block = rows[index * len(LOSS_TERMS) : (index + 1) * len(LOSS_TERMS)]
        actual_terms: list[str] = []
        for row in block:
            if None in row or any(row.get(field) is None for field in SOURCE_FIELDS):
                raise AggregateError(f"malformed loss-share CSV row at iter {expected_iter}")
            try:
                actual_iter = int(row["iter"])
            except (TypeError, ValueError) as exc:
                raise AggregateError(f"invalid loss-share iter: {row.get('iter')!r}") from exc
            if str(actual_iter) != row["iter"] or actual_iter != expected_iter:
                raise AggregateError(
                    f"loss-share iteration drift: {row['iter']!r} != {expected_iter}"
                )
            actual_terms.append(row["term"])
            for field in ("raw", "weighted", "share", "roof_share"):
                try:
                    number = float(row[field])
                except (TypeError, ValueError) as exc:
                    raise AggregateError(
                        f"loss-share {field} is not numeric at iter {expected_iter}"
                    ) from exc
                if not math.isfinite(number):
                    raise AggregateError(
                        f"loss-share {field} is non-finite at iter {expected_iter}"
                    )
        if tuple(actual_terms) != LOSS_TERMS:
            raise AggregateError(
                f"loss-share term order/set drift at iter {expected_iter}: "
                f"{actual_terms!r}"
            )
    return rows


def _ratio_evidence(condition: str, rows: Sequence[Mapping[str, str]]) -> dict[str, Any]:
    applicable = condition in {"04a", "04b"}
    if not applicable:
        return {"applicable": False}
    defined = 0
    within = 0
    first_defined: dict[str, Any] | None = None
    first_within: dict[str, Any] | None = None
    for offset in range(0, len(rows), len(LOSS_TERMS)):
        block = {row["term"]: row for row in rows[offset : offset + len(LOSS_TERMS)]}
        photo = float(block["pho"]["roof_share"])
        plane = float(block["plane"]["roof_share"])
        if photo == 0.0:
            continue
        ratio = plane / photo
        evidence = {
            "iter": int(block["pho"]["iter"]),
            "plane_roof_share": plane,
            "photo_roof_share": photo,
            "plane_photo_ratio": ratio,
        }
        defined += 1
        if first_defined is None:
            first_defined = evidence
        if 0.5 <= ratio <= 2.0:
            within += 1
            if first_within is None:
                first_within = evidence
    return {
        "applicable": True,
        "definition": "roof_share(plane)/roof_share(pho)",
        "required_range_inclusive": [0.5, 2.0],
        "defined_iter_count": defined,
        "within_required_count": within,
        "first_defined": first_defined,
        "first_within": first_within,
    }


def _default_checkpoint_loader(path: Path, **kwargs: Any) -> Any:
    # Imported lazily so CLI can hide CUDA before torch is imported.
    if str(REPO) not in os.sys.path:
        os.sys.path.insert(0, str(REPO))
    from src.stage2.checkpoint import load_training_checkpoint

    return load_training_checkpoint(path, **kwargs)


def _load_run(
    condition: str,
    seed: int,
    manifest_path: Path,
    *,
    loader: CheckpointLoader,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    run_dir = manifest_path.parent.resolve()
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AggregateError(f"cannot read full-state manifest {manifest_path}: {exc}") from exc
    if not isinstance(manifest, Mapping):
        raise AggregateError(f"full-state manifest is not an object: {manifest_path}")
    _require_exact(manifest.get("schema"), FULL_STATE_SCHEMA, "full-state schema")
    _require_exact(manifest.get("max_iter"), CHECKPOINT_STEP, "full-state max_iter")
    _require_exact(
        manifest.get("checkpoint_steps"),
        list(CHECKPOINT_STEPS),
        "full-state checkpoint schedule",
    )
    _require_exact(
        manifest.get("step_semantics"), STEP_SEMANTICS, "full-state step semantics"
    )
    _require_exact(
        manifest.get("loss_csv_paths"),
        list(EXPECTED_LOSS_PATHS),
        "full-state loss path list",
    )
    _require_exact(
        manifest.get("last_completed_steps"),
        CHECKPOINT_STEP,
        "full-state last completed steps",
    )
    _require_exact(manifest.get("process_completed"), True, "process completion")
    _require_exact(
        manifest.get("process_completed_steps"),
        CHECKPOINT_STEP,
        "process completed steps",
    )
    learning_runs_started = manifest.get("learning_runs_started")
    if (
        isinstance(learning_runs_started, bool)
        or not isinstance(learning_runs_started, int)
        or learning_runs_started < 1
    ):
        raise AggregateError("full-state manifest does not prove a learning run")

    output_path_text = str(manifest.get("output_path") or "")
    declared_output = _resolve_declared_path(
        output_path_text, declaring_file=manifest_path
    )
    _require_exact(declared_output, run_dir, "full-state output directory")
    binding = _validate_binding(
        manifest.get("binding_sha256"), output_path_text=output_path_text
    )

    config_path = _require_regular(
        _resolve_declared_path(manifest.get("config_path"), declaring_file=manifest_path),
        "training config",
    )
    config_sha = sha256_file(config_path)
    _require_exact(
        config_sha,
        _require_sha256(manifest.get("config_file_sha256"), "config file SHA256"),
        "training config SHA256",
    )

    latest = manifest.get("latest_full_checkpoint")
    if not isinstance(latest, Mapping) or set(latest) != {
        "path",
        "sha256",
        "completed_steps",
    }:
        raise AggregateError("latest_full_checkpoint shape changed")
    _require_exact(
        latest.get("completed_steps"), CHECKPOINT_STEP, "latest checkpoint steps"
    )
    expected_checkpoint = run_dir / "ckpt/step_020000.pt"
    checkpoint = _require_regular(
        _resolve_declared_path(latest.get("path"), declaring_file=manifest_path),
        "20k checkpoint",
    )
    _require_exact(checkpoint, expected_checkpoint.resolve(), "20k checkpoint path")
    checkpoint_sha = _require_sha256(latest.get("sha256"), "checkpoint SHA256")
    sidecar = _require_regular(Path(f"{checkpoint}.sha256"), "checkpoint SHA sidecar")
    try:
        sidecar_text = sidecar.read_text(encoding="ascii")
    except (OSError, UnicodeDecodeError) as exc:
        raise AggregateError(f"cannot read checkpoint SHA sidecar: {exc}") from exc
    sidecar_match = _SIDECAR_RE.fullmatch(sidecar_text)
    if sidecar_match is None or sidecar_match.group(1) != checkpoint_sha:
        raise AggregateError("checkpoint SHA sidecar is malformed or mismatched")

    loaded = loader(
        checkpoint,
        expected_binding_sha256=binding,
        map_location="cpu",
    )
    _require_exact(loaded.sha256, checkpoint_sha, "loaded checkpoint SHA256")
    _require_exact(
        int(loaded.completed_steps), CHECKPOINT_STEP, "loaded checkpoint steps"
    )
    payload = loaded.payload
    if not isinstance(payload, Mapping):
        raise AggregateError("loaded checkpoint payload is not an object")
    _require_exact(payload.get("step_semantics"), STEP_SEMANTICS, "payload semantics")
    _require_exact(payload.get("binding_sha256"), binding, "payload binding")
    if int(payload.get("learning_runs_started", 0) or 0) < 1:
        raise AggregateError("checkpoint payload does not prove a learning run")
    cursor, share_cursor = _validate_cursor(payload.get("loss_log_cursor"))

    source_path = run_dir / LOSS_SHARE_RELATIVE_PATH
    source_bytes = _read_exact_completed_prefix(
        source_path,
        size_bytes=int(share_cursor["size_bytes"]),
        prefix_sha256=str(share_cursor["prefix_sha256"]),
    )
    source_rows = _parse_loss_rows(source_bytes)
    output_rows = [
        {
            "schema_version": SCORING_SCHEMA_VERSION,
            "condition_id": condition,
            "seed": seed,
            "checkpoint_step": CHECKPOINT_STEP,
            "checkpoint_sha256": checkpoint_sha,
            **{field: row[field] for field in SOURCE_FIELDS},
        }
        for row in source_rows
    ]
    receipt = {
        "schema": RUN_RECEIPT_SCHEMA,
        "task_id": TASK_ID,
        "run_id": RUN_ID,
        "condition_id": condition,
        "seed": seed,
        "cpu_only": True,
        "checkpoint_map_location": "cpu",
        "full_state_manifest": {
            "path": _canonical_path(manifest_path),
            "sha256": sha256_file(manifest_path),
            "schema": FULL_STATE_SCHEMA,
        },
        "training_config": {
            "path": _canonical_path(config_path),
            "sha256": config_sha,
        },
        "binding_sha256": binding,
        "checkpoint": {
            "path": _canonical_path(checkpoint),
            "sha256": checkpoint_sha,
            "sidecar_path": _canonical_path(sidecar),
            "sidecar_sha256": sha256_file(sidecar),
            "completed_steps": CHECKPOINT_STEP,
            "step_semantics": STEP_SEMANTICS,
        },
        "loss_cursor": cursor,
        "loss_share_source": {
            "path": _canonical_path(source_path),
            "size_bytes": len(source_bytes),
            "prefix_sha256": sha256_bytes(source_bytes),
            "tail_bytes": 0,
            "header": list(SOURCE_FIELDS),
            "row_count": len(source_rows),
            "first_iter": int(source_rows[0]["iter"]),
            "last_iter": int(source_rows[-1]["iter"]),
            "audit_every": AUDIT_EVERY,
            "terms_per_iter": list(LOSS_TERMS),
        },
        "plane_photo_ratio_evidence": _ratio_evidence(condition, source_rows),
    }
    return output_rows, receipt


def _csv_header_bytes() -> bytes:
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(
        buffer, fieldnames=OUTPUT_FIELDS, lineterminator="\n", extrasaction="raise"
    )
    writer.writeheader()
    return buffer.getvalue().encode("utf-8")


def _csv_data_bytes(rows: Sequence[Mapping[str, Any]]) -> bytes:
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(
        buffer, fieldnames=OUTPUT_FIELDS, lineterminator="\n", extrasaction="raise"
    )
    writer.writerows(rows)
    return buffer.getvalue().encode("utf-8")


def _preflight_immutable(targets: Mapping[Path, bytes]) -> None:
    resolved: set[Path] = set()
    for path, expected in targets.items():
        target = path.resolve(strict=False)
        if target in resolved:
            raise AggregateError(f"duplicate output target: {path}")
        resolved.add(target)
        if path.is_symlink():
            raise AggregateError(f"immutable output must not be a symlink: {path}")
        if path.exists():
            if not path.is_file():
                raise AggregateError(f"immutable output is not a regular file: {path}")
            actual = path.read_bytes()
            if actual != expected:
                raise AggregateError(
                    f"refusing to replace non-identical immutable output: {path}"
                )


def _publish_one_immutable(path: Path, data: bytes) -> bool:
    if path.exists():
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.parent.is_symlink():
        raise AggregateError(f"output parent must not be a symlink: {path.parent}")
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, 0o644)
        try:
            os.link(temporary, path)
        except FileExistsError:
            if path.is_symlink() or not path.is_file() or path.read_bytes() != data:
                raise AggregateError(
                    f"immutable output appeared with different bytes: {path}"
                )
            return False
        directory_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
        return True
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def aggregate_loss_cursors(
    *,
    training_root: Path,
    output_path: Path,
    receipt_path: Path,
    run_receipt_dir: Path,
    loader: CheckpointLoader | None = None,
) -> dict[str, Any]:
    loader = loader or _default_checkpoint_loader
    manifests = discover_locked_manifests(training_root)
    all_rows: list[dict[str, Any]] = []
    run_receipts: list[dict[str, Any]] = []
    run_chunks: list[bytes] = []
    row_cursor = 1
    for condition, seed in EXPECTED_RUN_KEYS:
        rows, receipt = _load_run(
            condition,
            seed,
            manifests[(condition, seed)],
            loader=loader,
        )
        if len(rows) != EXPECTED_ROWS_PER_RUN:
            raise AggregateError(f"unexpected run row count: {condition}/seed{seed}")
        chunk = _csv_data_bytes(rows)
        receipt["aggregate_rows"] = {
            "first_data_row_1based": row_cursor,
            "last_data_row_1based": row_cursor + len(rows) - 1,
            "row_count": len(rows),
            "csv_data_bytes_sha256": sha256_bytes(chunk),
        }
        row_cursor += len(rows)
        all_rows.extend(rows)
        run_receipts.append(receipt)
        run_chunks.append(chunk)
    if len(all_rows) != EXPECTED_TOTAL_ROWS:
        raise AggregateError(
            f"aggregate row count drift: {len(all_rows)} != {EXPECTED_TOTAL_ROWS}"
        )

    aggregate_bytes = _csv_header_bytes() + b"".join(run_chunks)
    aggregate_sha = sha256_bytes(aggregate_bytes)
    targets: dict[Path, bytes] = {output_path: aggregate_bytes}
    run_receipt_records: list[dict[str, Any]] = []
    for receipt in run_receipts:
        receipt["aggregate_output"] = {
            "path": _canonical_path(output_path),
            "sha256": aggregate_sha,
            "row_count": EXPECTED_TOTAL_ROWS,
            "fields": list(OUTPUT_FIELDS),
        }
        condition = str(receipt["condition_id"])
        seed = int(receipt["seed"])
        run_receipt_path = run_receipt_dir / f"{condition}_seed{seed}.json"
        receipt_bytes = _json_bytes(receipt)
        targets[run_receipt_path] = receipt_bytes
        run_receipt_records.append(
            {
                "condition_id": condition,
                "seed": seed,
                "path": _canonical_path(run_receipt_path),
                "sha256": sha256_bytes(receipt_bytes),
            }
        )

    aggregate_receipt = {
        "schema": AGGREGATE_RECEIPT_SCHEMA,
        "task_id": TASK_ID,
        "run_id": RUN_ID,
        "state": "complete",
        "cpu_only": True,
        "checkpoint_map_location": "cpu",
        "expected_run_keys": [
            {"condition_id": condition, "seed": seed}
            for condition, seed in EXPECTED_RUN_KEYS
        ],
        "run_count": len(run_receipts),
        "rows_per_run": EXPECTED_ROWS_PER_RUN,
        "aggregate_row_count": len(all_rows),
        "aggregate_output": {
            "path": _canonical_path(output_path),
            "sha256": aggregate_sha,
            "fields": list(OUTPUT_FIELDS),
        },
        "run_receipts": run_receipt_records,
        "script": {
            "path": _canonical_path(Path(__file__)),
            "sha256": sha256_file(Path(__file__)),
        },
        "interpretation_or_verdict": None,
    }
    aggregate_receipt_bytes = _json_bytes(aggregate_receipt)
    targets[receipt_path] = aggregate_receipt_bytes

    _preflight_immutable(targets)
    created = sum(_publish_one_immutable(path, data) for path, data in targets.items())
    return {
        "schema": AGGREGATE_RECEIPT_SCHEMA,
        "state": "published" if created else "already_present_identical",
        "created_file_count": created,
        "file_count": len(targets),
        "aggregate_output": str(output_path),
        "aggregate_sha256": aggregate_sha,
        "aggregate_row_count": len(all_rows),
        "receipt": str(receipt_path),
        "receipt_sha256": sha256_bytes(aggregate_receipt_bytes),
        "run_receipt_count": len(run_receipts),
    }


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--training-root", type=Path, default=DEFAULT_TRAINING_ROOT)
    result.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    result.add_argument("--receipt", type=Path, default=DEFAULT_RECEIPT)
    result.add_argument(
        "--run-receipt-dir", type=Path, default=DEFAULT_RUN_RECEIPT_DIR
    )
    return result


def main(argv: Sequence[str] | None = None) -> int:
    if not Path("/.dockerenv").is_file():
        raise AggregateError("loss cursor aggregation must run inside Docker")
    os.environ["CUDA_VISIBLE_DEVICES"] = "-1"
    os.environ["NVIDIA_VISIBLE_DEVICES"] = "none"
    args = parser().parse_args(argv)
    result = aggregate_loss_cursors(
        training_root=args.training_root,
        output_path=args.output,
        receipt_path=args.receipt,
        run_receipt_dir=args.run_receipt_dir,
    )
    print(json.dumps(result, sort_keys=True, separators=(",", ":")), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
