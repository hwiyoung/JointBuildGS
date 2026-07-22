#!/usr/bin/env python3
"""Fail-closed checkpoint lineage shared by the P1W read-out adapters.

This module is deliberately geometry-agnostic.  It binds a read-out artifact to
the exact full-state checkpoint declared by the trainer manifest, then lets the
classifier, Roofer adapter, and scorer re-open and verify the same bytes.
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import numpy as np


REPO = Path(__file__).resolve().parents[3]
CONTAINER_REPO = Path("/workspace/JointBuildGS")
LINEAGE_SCHEMA = "jointbuildgs.pilot_1wave.readout_lineage.v1"
CLASSIFICATION_SCHEMA = "jointbuildgs.pilot_1wave.scene_classification.v1"
FULL_STATE_MANIFEST_SCHEMA = "jointbuildgs.stage2.resume_manifest.v1"
FULL_STATE_CHECKPOINT_FORMAT = "jointbuildgs.stage2.full_state"
FULL_STATE_STEP_SEMANTICS = "completed_optimizer_updates"
FULL_STATE_STEPS = (5_000, 10_000, 15_000, 20_000)
MAX_ITER = 20_000
CONDITION_ARMS = {
    "01": "01_surface",
    "02": "02_photo_control",
    "03": "03_plane_soft",
    "04a": "04a_plane_medium_vision",
    "04b": "04b_plane_medium_gt_upperbound",
}
EXPECTED_SEEDS = (1001, 1002)


def sha256_file(path: Path, block_size: int = 1 << 20) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(block_size), b""):
            digest.update(block)
    return digest.hexdigest()


def require_equal(actual: Any, expected: Any, label: str) -> None:
    if actual != expected:
        raise RuntimeError(f"{label} drift: {actual!r} != {expected!r}")


def canonical_repo_path(path: Path, *, repo_root: Path = REPO) -> str:
    """Return one environment-independent repository-relative POSIX path."""

    resolved = path.resolve()
    root = repo_root.resolve()
    try:
        relative = resolved.relative_to(root)
    except ValueError as exc:
        raise RuntimeError(f"lineage artifact is outside repository: {resolved}") from exc
    if not relative.parts or ".." in relative.parts:
        raise RuntimeError(f"invalid repository-relative lineage path: {relative}")
    return relative.as_posix()


def resolve_declared_path(value: Any, *, declaring_file: Path) -> Path:
    """Resolve repository/container paths without accepting ambiguous bytes."""

    text = str(value or "").strip()
    if not text:
        raise RuntimeError(f"empty path declared by {declaring_file}")
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
        raise FileNotFoundError(
            f"declared artifact does not exist: {text} ({declaring_file})"
        )
    if len(unique) != 1:
        raise RuntimeError(f"ambiguous declared path: {text} -> {sorted(unique)}")
    return Path(next(iter(unique)))


def validate_condition_seed(condition_id: str, seed: int) -> None:
    if condition_id not in CONDITION_ARMS:
        raise RuntimeError(f"unknown condition_id: {condition_id}")
    if int(seed) not in EXPECTED_SEEDS:
        raise RuntimeError(f"unknown seed: {seed}")


def _load_config_identity(path: Path) -> dict[str, Any]:
    """Read only the locked top-level identity keys from JSON or simple YAML."""

    if path.suffix.lower() == ".json":
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise RuntimeError(f"training config must be an object: {path}")
        return payload
    result: dict[str, Any] = {}
    wanted = {"max_iter", "pilot_arm", "seed"}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        if not raw_line.strip() or raw_line.lstrip().startswith("#"):
            continue
        if raw_line[:1].isspace() or ":" not in raw_line:
            continue
        key, raw_value = raw_line.split(":", 1)
        key = key.strip()
        if key not in wanted:
            continue
        value = raw_value.split(" #", 1)[0].strip().strip("'\"")
        if key in {"max_iter", "seed"}:
            try:
                result[key] = int(value)
            except ValueError as exc:
                raise RuntimeError(f"invalid {key} in training config: {path}") from exc
        else:
            result[key] = value
    return result


def validate_full_state_binding(
    *,
    checkpoint_path: Path,
    checkpoint_sha256: str,
    completed_steps: int,
    condition_id: str,
    seed: int,
    manifest_path: Path,
    checkpoint_binding_sha256: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Verify that one manifest declares these exact checkpoint bytes."""

    validate_condition_seed(condition_id, seed)
    checkpoint_path = checkpoint_path.resolve()
    manifest_path = manifest_path.resolve()
    if not checkpoint_path.is_file() or not manifest_path.is_file():
        raise FileNotFoundError(
            checkpoint_path if not checkpoint_path.is_file() else manifest_path
        )
    actual_checkpoint_sha = sha256_file(checkpoint_path)
    require_equal(actual_checkpoint_sha, checkpoint_sha256, "checkpoint SHA256")
    if int(completed_steps) not in FULL_STATE_STEPS:
        raise RuntimeError(f"checkpoint step is outside the locked schedule: {completed_steps}")

    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError("full-state manifest root must be an object")
    require_equal(
        payload.get("schema"), FULL_STATE_MANIFEST_SCHEMA, "full-state manifest schema"
    )
    require_equal(int(payload.get("max_iter", -1)), MAX_ITER, "full-state max_iter")
    require_equal(
        payload.get("step_semantics"),
        FULL_STATE_STEP_SEMANTICS,
        "full-state step semantics",
    )
    schedule = tuple(int(value) for value in payload.get("checkpoint_steps", []))
    missing = sorted(set(FULL_STATE_STEPS) - set(schedule))
    if missing:
        raise RuntimeError(f"full-state checkpoint schedule missing: {missing}")
    require_equal(
        int(payload.get("last_completed_steps", -1)),
        int(completed_steps),
        "manifest/checkpoint completed steps",
    )
    if int(payload.get("learning_runs_started", 0) or 0) < 1:
        raise RuntimeError("full-state manifest does not prove a learning run")

    latest = payload.get("latest_full_checkpoint")
    if not isinstance(latest, Mapping):
        raise RuntimeError("full-state manifest has no latest_full_checkpoint")
    declared_checkpoint = resolve_declared_path(
        latest.get("path"), declaring_file=manifest_path
    )
    require_equal(declared_checkpoint, checkpoint_path, "manifest checkpoint path")
    require_equal(
        int(latest.get("completed_steps", -1)),
        int(completed_steps),
        "manifest checkpoint step",
    )
    require_equal(latest.get("sha256"), actual_checkpoint_sha, "manifest checkpoint SHA256")

    config_path = resolve_declared_path(
        payload.get("config_path"), declaring_file=manifest_path
    )
    config_sha = sha256_file(config_path)
    require_equal(config_sha, payload.get("config_file_sha256"), "training config SHA256")
    config = _load_config_identity(config_path)
    require_equal(int(config.get("max_iter", -1)), MAX_ITER, "training config max_iter")
    require_equal(config.get("pilot_arm"), CONDITION_ARMS[condition_id], "training config arm")
    require_equal(int(config.get("seed", -1)), int(seed), "training config seed")

    manifest_binding = payload.get("binding_sha256")
    if checkpoint_binding_sha256 is not None:
        require_equal(
            dict(manifest_binding or {}),
            dict(checkpoint_binding_sha256),
            "checkpoint/manifest binding SHA256",
        )

    eligible_20k = (
        int(completed_steps) == MAX_ITER
        and payload.get("process_completed") is True
        and int(payload.get("process_completed_steps", -1)) == MAX_ITER
    )
    if int(completed_steps) == MAX_ITER and not eligible_20k:
        raise RuntimeError("20k checkpoint lacks the completed trainer epilogue")
    return {
        "schema": LINEAGE_SCHEMA,
        "condition_id": condition_id,
        "seed": int(seed),
        "checkpoint": {
            "format": FULL_STATE_CHECKPOINT_FORMAT,
            "path": canonical_repo_path(checkpoint_path),
            "sha256": actual_checkpoint_sha,
            "completed_steps": int(completed_steps),
            "step_semantics": FULL_STATE_STEP_SEMANTICS,
        },
        "full_state_manifest": {
            "path": canonical_repo_path(manifest_path),
            "sha256": sha256_file(manifest_path),
            "schema": FULL_STATE_MANIFEST_SCHEMA,
        },
        "training_config": {
            "path": canonical_repo_path(config_path),
            "sha256": config_sha,
            "pilot_arm": config["pilot_arm"],
        },
        "verified_full_state": True,
        "eligible_20k_full_state": eligible_20k,
    }


def validate_readout_lineage(
    lineage: Mapping[str, Any],
    *,
    expected_condition: str | None = None,
    expected_seed: int | None = None,
) -> dict[str, Any]:
    """Re-open and verify every immutable artifact named by a lineage record."""

    if not isinstance(lineage, Mapping):
        raise RuntimeError("read-out lineage must be an object")
    require_equal(lineage.get("schema"), LINEAGE_SCHEMA, "read-out lineage schema")
    condition_id = str(lineage.get("condition_id", ""))
    seed = int(lineage.get("seed", -1))
    validate_condition_seed(condition_id, seed)
    if expected_condition is not None:
        require_equal(condition_id, expected_condition, "read-out lineage condition")
    if expected_seed is not None:
        require_equal(seed, int(expected_seed), "read-out lineage seed")
    if lineage.get("verified_full_state") is not True:
        raise RuntimeError("read-out lineage is not a verified full state")
    if lineage.get("geometry_only") is not True:
        raise RuntimeError("read-out lineage is not geometry-only")

    checkpoint = lineage.get("checkpoint")
    manifest = lineage.get("full_state_manifest")
    if not isinstance(checkpoint, Mapping) or not isinstance(manifest, Mapping):
        raise RuntimeError("read-out lineage lacks checkpoint/full-state records")
    require_equal(
        checkpoint.get("format"), FULL_STATE_CHECKPOINT_FORMAT, "checkpoint format"
    )
    require_equal(
        checkpoint.get("step_semantics"),
        FULL_STATE_STEP_SEMANTICS,
        "checkpoint step semantics",
    )
    step = int(checkpoint.get("completed_steps", -1))
    checkpoint_path = resolve_declared_path(
        checkpoint.get("path"), declaring_file=REPO / "lineage.json"
    )
    manifest_path = resolve_declared_path(
        manifest.get("path"), declaring_file=REPO / "lineage.json"
    )
    require_equal(sha256_file(checkpoint_path), checkpoint.get("sha256"), "checkpoint SHA256")
    require_equal(
        sha256_file(manifest_path), manifest.get("sha256"), "full-state manifest SHA256"
    )
    normalized = validate_full_state_binding(
        checkpoint_path=checkpoint_path,
        checkpoint_sha256=str(checkpoint.get("sha256", "")),
        completed_steps=step,
        condition_id=condition_id,
        seed=seed,
        manifest_path=manifest_path,
    )
    require_equal(
        bool(lineage.get("eligible_20k_full_state")),
        bool(normalized["eligible_20k_full_state"]),
        "read-out lineage 20k eligibility",
    )
    normalized["geometry_only"] = True
    return normalized


def validate_classification_receipt(
    receipt_path: Path,
    *,
    pointcloud_path: Path,
    expected_condition: str,
    expected_seed: int,
) -> dict[str, Any]:
    """Bind a classified LAS to its NPZ and exact source checkpoint lineage."""

    receipt_path = receipt_path.resolve()
    pointcloud_path = pointcloud_path.resolve()
    if not receipt_path.is_file() or not pointcloud_path.is_file():
        raise FileNotFoundError(
            receipt_path if not receipt_path.is_file() else pointcloud_path
        )
    payload = json.loads(receipt_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError("classification receipt root must be an object")
    require_equal(payload.get("schema"), CLASSIFICATION_SCHEMA, "classification schema")
    require_equal(payload.get("state"), "complete", "classification state")
    classified = payload.get("classified_las")
    source_npz = payload.get("source_scene_npz")
    if not isinstance(classified, Mapping) or not isinstance(source_npz, Mapping):
        raise RuntimeError("classification receipt lacks LAS/NPZ records")
    declared_las = resolve_declared_path(
        classified.get("path"), declaring_file=receipt_path
    )
    require_equal(declared_las, pointcloud_path, "classification LAS path")
    require_equal(
        sha256_file(pointcloud_path), classified.get("sha256"), "classification LAS SHA256"
    )
    npz_path = resolve_declared_path(source_npz.get("path"), declaring_file=receipt_path)
    require_equal(sha256_file(npz_path), source_npz.get("sha256"), "source NPZ SHA256")
    try:
        with np.load(npz_path, allow_pickle=False) as npz:
            if "readout_lineage_json" not in npz:
                raise RuntimeError("source NPZ lacks readout_lineage_json")
            encoded = np.asarray(npz["readout_lineage_json"])
    except ValueError as exc:
        raise RuntimeError("source NPZ lineage must not require pickle") from exc
    if encoded.shape != () or encoded.dtype.kind not in {"U", "S"}:
        raise RuntimeError("source NPZ lineage must be a non-object scalar string")
    raw = encoded.item()
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")
    try:
        embedded_lineage = json.loads(str(raw))
    except json.JSONDecodeError as exc:
        raise RuntimeError("source NPZ lineage is invalid JSON") from exc
    require_equal(
        embedded_lineage,
        payload.get("readout_lineage"),
        "source NPZ/classification lineage",
    )
    lineage = validate_readout_lineage(
        embedded_lineage,
        expected_condition=expected_condition,
        expected_seed=expected_seed,
    )
    return {
        "path": str(receipt_path),
        "sha256": sha256_file(receipt_path),
        "scene_npz_path": str(npz_path),
        "scene_npz_sha256": source_npz.get("sha256"),
        "pointcloud_path": str(pointcloud_path),
        "pointcloud_sha256": classified.get("sha256"),
        "readout_lineage": lineage,
    }
