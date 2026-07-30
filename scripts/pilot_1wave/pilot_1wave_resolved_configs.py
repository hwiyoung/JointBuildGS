#!/usr/bin/env python3
"""Resolve the ten immutable P1W training YAMLs from approved inputs.

This is deliberately a configuration boundary, not a trainer wrapper.  It
binds every input by SHA-256, rejects an invalid forward-only calibration
receipt, and enforces the 04a/04b controlled-pair rule before publishing any
YAML.  It never starts learning.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import tempfile
from typing import Any, Iterable, Mapping
import sys

import yaml


REPO = Path(__file__).resolve().parents[3]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from src.stage2.pilot_mask_schema import (  # noqa: E402
    BinaryMaskSet,
    MaskPurpose,
    MaskSource,
)

RUN_ID = "20260721_pilot_1wave"
SCHEMA = "jointbuildgs.pilot_1wave.resolved_configs.v1"
CALIBRATION_SCAFFOLD_SCHEMA = "jointbuildgs.pilot_1wave.calibration_scaffold.v1"
CALIBRATION_SCAFFOLDS_MANIFEST_SCHEMA = (
    "jointbuildgs.pilot_1wave.calibration_scaffolds_manifest.v1"
)
MATERIALIZED_INPUT_INVENTORY_SCHEMA = (
    "jointbuildgs.pilot_1wave.materialized_input_inventory.v1"
)
LOCK_SCHEMA = "jointbuildgs.pilot_1wave.calibration_lock.v1"
RECEIPT_SCHEMA = "jointbuildgs.pilot_1wave.plane_calibration_receipt.v1"
OFFICIAL_BACKEND_ID = "jointbuildgs.stage2_forward_backend.v1"
CONTAINER_REPO = Path("/workspace/JointBuildGS")

CONDITIONS = (
    ("01", "01_surface"),
    ("02", "02_photo_control"),
    ("03", "03_plane_soft"),
    ("04a", "04a_plane_medium_vision"),
    ("04b", "04b_plane_medium_gt_upperbound"),
)
EXPECTED_MASKS = {
    "04a": ("vision_groundedsam_roof", ("04a_plane_medium_vision",)),
    "04b": ("lod2_roofsurface_gt_upperbound", ("04b_plane_medium_gt_upperbound",)),
}
FORBIDDEN_WEIGHTS = (
    "w_sem",
    "w_mutual",
    "w_mvc",
    "w_distort",
    "w_mono_depth",
    "w_semdepth_smooth",
    "w_semdepth_plane",
    "w_boundary_normal",
)
PAIR_ALLOWED_DIFFERENCE_KEYS = frozenset(
    {
        "pilot_arm",
        "pilot_condition",
        "pilot_job_id",
        "out_dir",
        "plane_region_mask_manifest",
        "pilot_plane_region_source",
        "pilot_plane_region_manifest_sha256",
    }
)
PAIR_REQUIRED_SCAFFOLD_DIFFERENCE_KEYS = frozenset(
    {
        "pilot_arm",
        "pilot_condition",
        "pilot_job_id",
        "plane_region_mask_manifest",
        "pilot_plane_region_source",
        "pilot_plane_region_manifest_sha256",
    }
)
PAIR_REQUIRED_TRAINING_DIFFERENCE_KEYS = (
    PAIR_REQUIRED_SCAFFOLD_DIFFERENCE_KEYS | {"out_dir"}
)


class ContractError(ValueError):
    """An input or resolved configuration violates the locked P1W contract."""


def require_docker() -> None:
    if not Path("/.dockerenv").exists():
        raise ContractError(
            "P1W config generation must run in the pinned Docker image"
        )


def sha256_file(path: Path, block_size: int = 1 << 20) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(block_size), b""):
            digest.update(block)
    return digest.hexdigest()


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def canonical_json_bytes(payload: Any) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _input_file_record(repo: Path, path: Path, role: str, view_id: str | None = None) -> dict[str, Any]:
    """Hash one immutable calibration/training input with a mutation guard."""

    path = path.resolve()
    repo_relative(repo, path)
    if not path.is_file() or path.is_symlink():
        raise ContractError(f"materialized input must be a regular non-symlink file: {path}")
    before = path.stat()
    digest = sha256_file(path)
    after = path.stat()
    before_identity = (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
    after_identity = (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
    if before_identity != after_identity:
        raise ContractError(f"materialized input changed while hashing: {path}")
    record: dict[str, Any] = {
        "role": role,
        "path": repo_relative(repo, path),
        "size_bytes": int(after.st_size),
        "sha256": digest,
    }
    if view_id is not None:
        record["view_id"] = view_id
    return record


def build_materialized_input_inventory(
    *,
    repo: Path,
    data_root: Path,
    mono_dir: Path,
    view_ids: Iterable[str],
) -> dict[str, Any]:
    """Bind every byte consumed by the initial Stage2 scaffold.

    COLMAP's loader deterministically prefers the geometric MVS files, so only
    those selected files are admitted.  Photo/plane-mask payloads are bound by
    their separate immutable BinaryMaskSet manifests.
    """

    repo = repo.resolve()
    data_root = data_root.resolve()
    mono_dir = mono_dir.resolve()
    repo_relative(repo, data_root)
    repo_relative(repo, mono_dir)
    ordered_views = [str(value) for value in view_ids]
    if not ordered_views or ordered_views != sorted(ordered_views):
        raise ContractError("materialized input view IDs must be nonempty and sorted")
    if len(ordered_views) != len(set(ordered_views)):
        raise ContractError("materialized input view IDs must be unique")

    records = [
        _input_file_record(repo, data_root / "sparse/0/cameras.bin", "sfm_cameras"),
        _input_file_record(repo, data_root / "sparse/0/images.bin", "sfm_images"),
        _input_file_record(repo, data_root / "sparse/0/points3D.bin", "sfm_points3d"),
    ]
    for view_id in ordered_views:
        stem = Path(view_id).stem
        records.extend(
            [
                _input_file_record(
                    repo, data_root / "images" / view_id, "rgb", view_id
                ),
                _input_file_record(
                    repo,
                    data_root / "stereo/depth_maps" / f"{view_id}.geometric.bin",
                    "mvs_depth_geometric",
                    view_id,
                ),
                _input_file_record(
                    repo,
                    data_root / "stereo/normal_maps" / f"{view_id}.geometric.bin",
                    "mvs_normal_geometric",
                    view_id,
                ),
                _input_file_record(
                    repo, mono_dir / f"{stem}.npy", "mono_normal_omnidata", view_id
                ),
            ]
        )
    role_counts: dict[str, int] = {}
    total_bytes = 0
    for record in records:
        role = str(record["role"])
        role_counts[role] = role_counts.get(role, 0) + 1
        total_bytes += int(record["size_bytes"])
    return {
        "schema": MATERIALIZED_INPUT_INVENTORY_SCHEMA,
        "run_id": RUN_ID,
        "mode": "result_blind_materialized_stage2_inputs",
        "data_root": repo_relative(repo, data_root),
        "mono_normal_dir": repo_relative(repo, mono_dir),
        "view_ids": ordered_views,
        "view_count": len(ordered_views),
        "role_counts": role_counts,
        "file_count": len(records),
        "total_bytes": total_bytes,
        "records": records,
        "records_sha256": sha256_bytes(canonical_json_bytes(records)),
        "learning_runs_started": 0,
        "optimizer_updates": 0,
    }


def validate_materialized_input_inventory(
    repo: Path,
    inventory_path: Path,
    *,
    expected_sha256: str | None = None,
) -> dict[str, Any]:
    """Verify the published inventory and every bound materialized byte."""

    repo = repo.resolve()
    inventory_path = inventory_path.resolve()
    if expected_sha256 is not None:
        require_equal(
            sha256_file(inventory_path),
            expected_sha256,
            "materialized input inventory SHA256",
        )
    payload = load_json(inventory_path)
    require_equal(
        payload.get("schema"),
        MATERIALIZED_INPUT_INVENTORY_SCHEMA,
        "materialized input inventory schema",
    )
    require_equal(payload.get("run_id"), RUN_ID, "materialized input run_id")
    require_equal(payload.get("learning_runs_started"), 0, "materialized input learning count")
    require_equal(payload.get("optimizer_updates"), 0, "materialized input optimizer count")
    records = payload.get("records")
    if not isinstance(records, list) or not records:
        raise ContractError("materialized input inventory has no records")
    view_ids = payload.get("view_ids")
    if (
        not isinstance(view_ids, list)
        or not view_ids
        or any(not isinstance(value, str) or not value for value in view_ids)
        or view_ids != sorted(view_ids)
        or len(view_ids) != len(set(view_ids))
    ):
        raise ContractError("materialized input inventory has invalid view IDs")
    data_root = resolve_repo_path(repo, str(payload.get("data_root", "")))
    mono_dir = resolve_repo_path(repo, str(payload.get("mono_normal_dir", "")))
    repo_relative(repo, data_root)
    repo_relative(repo, mono_dir)
    expected_identities: list[tuple[str, str, str | None]] = [
        (
            "sfm_cameras",
            repo_relative(repo, data_root / "sparse/0/cameras.bin"),
            None,
        ),
        (
            "sfm_images",
            repo_relative(repo, data_root / "sparse/0/images.bin"),
            None,
        ),
        (
            "sfm_points3d",
            repo_relative(repo, data_root / "sparse/0/points3D.bin"),
            None,
        ),
    ]
    for view_id in view_ids:
        stem = Path(view_id).stem
        expected_identities.extend(
            [
                ("rgb", repo_relative(repo, data_root / "images" / view_id), view_id),
                (
                    "mvs_depth_geometric",
                    repo_relative(
                        repo,
                        data_root
                        / "stereo/depth_maps"
                        / f"{view_id}.geometric.bin",
                    ),
                    view_id,
                ),
                (
                    "mvs_normal_geometric",
                    repo_relative(
                        repo,
                        data_root
                        / "stereo/normal_maps"
                        / f"{view_id}.geometric.bin",
                    ),
                    view_id,
                ),
                (
                    "mono_normal_omnidata",
                    repo_relative(repo, mono_dir / f"{stem}.npy"),
                    view_id,
                ),
            ]
        )
    require_equal(
        len(records),
        len(expected_identities),
        "materialized input exact record count",
    )
    require_equal(
        sha256_bytes(canonical_json_bytes(records)),
        payload.get("records_sha256"),
        "materialized input records SHA256",
    )
    actual_role_counts: dict[str, int] = {}
    actual_total_bytes = 0
    seen_paths: set[str] = set()
    for index, (record, expected_identity) in enumerate(
        zip(records, expected_identities, strict=True)
    ):
        if not isinstance(record, Mapping):
            raise ContractError(f"materialized input record {index} is not an object")
        expected_view_id = expected_identity[2]
        expected_keys = {"role", "path", "size_bytes", "sha256"}
        if expected_view_id is not None:
            expected_keys.add("view_id")
        require_equal(
            set(record), expected_keys, f"materialized input record {index} keys"
        )
        actual_identity = (
            record.get("role"),
            record.get("path"),
            record.get("view_id") if expected_view_id is not None else None,
        )
        require_equal(
            actual_identity,
            expected_identity,
            f"materialized input record {index} identity",
        )
        relative = str(record.get("path", ""))
        if not relative or relative in seen_paths:
            raise ContractError(f"materialized input path is empty/duplicate: {relative!r}")
        path = resolve_repo_path(repo, relative)
        repo_relative(repo, path)
        if not path.is_file() or path.is_symlink():
            raise ContractError(f"materialized input is missing/non-regular: {path}")
        stat_result = path.stat()
        require_equal(int(stat_result.st_size), record.get("size_bytes"), f"input size {relative}")
        require_equal(sha256_file(path), record.get("sha256"), f"input SHA256 {relative}")
        role = str(record.get("role", ""))
        if not role:
            raise ContractError(f"materialized input has no role: {relative}")
        actual_role_counts[role] = actual_role_counts.get(role, 0) + 1
        actual_total_bytes += int(stat_result.st_size)
        seen_paths.add(relative)
    require_equal(len(records), payload.get("file_count"), "materialized input file count")
    require_equal(actual_total_bytes, payload.get("total_bytes"), "materialized input byte count")
    require_equal(actual_role_counts, payload.get("role_counts"), "materialized input role counts")
    require_equal(len(view_ids), payload.get("view_count"), "materialized input view count")
    expected_roles = {
        "sfm_cameras": 1,
        "sfm_images": 1,
        "sfm_points3d": 1,
        "rgb": len(view_ids),
        "mvs_depth_geometric": len(view_ids),
        "mvs_normal_geometric": len(view_ids),
        "mono_normal_omnidata": len(view_ids),
    }
    require_equal(actual_role_counts, expected_roles, "materialized input exact role inventory")
    return payload


def load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ContractError(f"cannot read JSON {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ContractError(f"JSON root must be an object: {path}")
    return payload


def resolve_repo_path(repo: Path, value: str | Path) -> Path:
    path = Path(value)
    return path.resolve() if path.is_absolute() else (repo / path).resolve()


def repo_relative(repo: Path, path: Path) -> str:
    try:
        return str(path.resolve().relative_to(repo.resolve()))
    except ValueError as exc:
        raise ContractError(f"path is outside the repository: {path}") from exc


def container_path(repo: Path, path: Path) -> str:
    return str(CONTAINER_REPO / repo_relative(repo, path))


def require_equal(actual: Any, expected: Any, field: str) -> None:
    if actual != expected:
        raise ContractError(f"{field}: expected {expected!r}, got {actual!r}")


def require_number(value: Any, field: str, *, positive: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ContractError(f"{field} must be a numeric scalar")
    result = float(value)
    if not math.isfinite(result) or (positive and result <= 0.0):
        suffix = " and >0" if positive else ""
        raise ContractError(f"{field} must be finite{suffix}")
    return result


def verify_binding(repo: Path, binding: Mapping[str, Any], field: str) -> Path:
    if not isinstance(binding, Mapping):
        raise ContractError(f"{field} must be a path/SHA binding")
    if "path" not in binding or "sha256" not in binding:
        raise ContractError(f"{field} must contain path and sha256")
    path = resolve_repo_path(repo, str(binding["path"]))
    if not path.is_file():
        raise ContractError(f"{field} path is missing: {path}")
    actual = sha256_file(path)
    require_equal(actual, str(binding["sha256"]), f"{field}.sha256")
    return path


def verify_nested_bindings(repo: Path, value: Any, field: str) -> None:
    """Verify every nested object that declares either member of path/SHA."""

    if isinstance(value, Mapping):
        has_path = "path" in value
        has_sha = "sha256" in value
        if has_path or has_sha:
            if not (has_path and has_sha):
                raise ContractError(f"{field} has an incomplete path/SHA binding")
            verify_binding(repo, value, field)
        for key, child in value.items():
            verify_nested_bindings(repo, child, f"{field}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            verify_nested_bindings(repo, child, f"{field}[{index}]")


def validate_lock(repo: Path, lock_path: Path) -> tuple[dict[str, Any], dict[str, Path]]:
    lock = load_json(lock_path)
    require_equal(lock.get("schema"), LOCK_SCHEMA, "calibration lock schema")
    require_equal(lock.get("run_id"), RUN_ID, "calibration lock run_id")
    require_equal(lock.get("created_before_optimizer_results"), True, "result-blind lock")
    bindings = lock.get("input_bindings")
    if not isinstance(bindings, dict):
        raise ContractError("calibration lock input_bindings must be an object")
    required = {
        "prep_manifest",
        "pilot_set_manifest",
        "dense_seed",
        "projected_footprint_mask_manifest",
        "omnidata_manifest",
    }
    if not required.issubset(bindings):
        raise ContractError(f"calibration lock missing inputs: {sorted(required - set(bindings))}")
    paths = {
        key: verify_binding(repo, bindings[key], f"lock.input_bindings.{key}")
        for key in sorted(required)
    }

    budget = lock.get("training_budget", {})
    require_equal(budget.get("seeds"), [1001, 1002], "training seeds")
    require_equal(budget.get("max_optimizer_updates"), 20000, "max updates")
    require_equal(
        budget.get("full_state_checkpoint_updates"),
        [5000, 10000, 15000, 20000],
        "full-state checkpoints",
    )
    require_equal(budget.get("gpu_count"), 2, "GPU count")
    require_equal(float(budget.get("wall_guard_hours", -1)), 9.0, "wall guard")
    require_equal(
        float(budget.get("stop_starting_new_runs_hours", -1)),
        8.5,
        "new-run stop gate",
    )
    require_equal(budget.get("partial_is_winner_eligible"), False, "partial eligibility")

    resolution = lock.get("forward_only_resolution", {})
    require_equal(resolution.get("calibration_seed"), 1001, "calibration seed")

    recipe = lock.get("base_recipe", {})
    require_equal(recipe.get("forbidden_weights_zero"), list(FORBIDDEN_WEIGHTS), "forbidden weights")
    require_equal(recipe.get("structure_grouping"), "g2_geometry", "structure grouping")
    return lock, paths


def _validate_ratio_row(
    row: Mapping[str, Any], field: str, *, target_required: bool
) -> dict[str, float | None]:
    required = (
        "w_plane",
        "target_ratio",
        "aggregate_weighted_roof_photo",
        "aggregate_raw_roof_plane",
        "achieved_ratio",
        "eligible_view_count",
    )
    missing = set(required) - set(row)
    if missing:
        raise ContractError(f"{field} missing fields: {sorted(missing)}")
    values: dict[str, float | None] = {}
    for key in required:
        if key == "target_ratio" and not target_required:
            require_equal(row[key], None, f"{field}.target_ratio")
            values[key] = None
        else:
            values[key] = require_number(
                row[key],
                f"{field}.{key}",
                positive=(key != "eligible_view_count"),
            )
    if int(values["eligible_view_count"]) != values["eligible_view_count"]:
        raise ContractError(f"{field}.eligible_view_count must be integral")
    if values["eligible_view_count"] < 8:
        raise ContractError(f"{field} has fewer than 8 eligible views")
    recomputed = float(values["w_plane"]) * float(
        values["aggregate_raw_roof_plane"]
    ) / float(values["aggregate_weighted_roof_photo"])
    if not math.isclose(recomputed, values["achieved_ratio"], rel_tol=1e-9, abs_tol=1e-12):
        raise ContractError(f"{field}.achieved_ratio does not reproduce from aggregates")
    return values


def validate_receipt(
    repo: Path,
    receipt_path: Path,
    lock_path: Path,
    lock: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, float]]:
    receipt = load_json(receipt_path)
    require_equal(receipt.get("schema"), RECEIPT_SCHEMA, "calibration receipt schema")
    require_equal(receipt.get("run_id"), RUN_ID, "calibration receipt run_id")
    require_equal(receipt.get("state"), "complete", "calibration receipt state")
    require_equal(receipt.get("official"), True, "official calibration receipt")
    require_equal(receipt.get("synthetic"), False, "synthetic calibration receipt")
    require_equal(
        receipt.get("official_backend_id"),
        OFFICIAL_BACKEND_ID,
        "official calibration backend ID",
    )
    require_equal(
        receipt.get("backend"),
        {"id": OFFICIAL_BACKEND_ID, "synthetic": False},
        "calibration backend contract",
    )

    runtime = receipt.get("runtime_attestation")
    if not isinstance(runtime, Mapping):
        raise ContractError("calibration receipt runtime_attestation must be an object")
    require_equal(runtime.get("state"), "official_attested", "runtime state")
    require_equal(runtime.get("synthetic"), False, "runtime synthetic flag")
    require_equal(runtime.get("container"), True, "runtime container flag")
    locked_runtime = lock.get("forward_runtime")
    if not isinstance(locked_runtime, Mapping):
        raise ContractError("calibration lock is missing forward_runtime")
    for key in (
        "image_tag",
        "image_id",
        "host_attestation_environment",
        "python",
        "torch",
        "cuda",
        "gsplat",
        "numpy",
        "scipy",
        "pillow",
    ):
        require_equal(runtime.get(key), locked_runtime.get(key), f"runtime {key}")
    require_equal(runtime.get("cuda_available"), True, "runtime CUDA available")
    cuda_device_count = runtime.get("cuda_device_count")
    if (
        isinstance(cuda_device_count, bool)
        or not isinstance(cuda_device_count, int)
        or cuda_device_count < 1
    ):
        raise ContractError("official calibration requires at least one CUDA device")

    optimizer = receipt.get("optimizer_audit", {})
    for key in ("optimizer_objects_created", "backward_calls", "optimizer_updates"):
        require_equal(optimizer.get(key), 0, f"optimizer_audit.{key}")

    view = receipt.get("view_lock", {})
    lock_view = lock["view_selection"]
    require_equal(view.get("view_ids"), lock_view["calibration_view_ids"], "calibration views")
    require_equal(
        view.get("view_ids_sha256"),
        lock_view["calibration_view_ids_sha256_newline_joined"],
        "calibration view hash",
    )
    require_equal(view.get("minimum_eligible_views"), 8, "minimum eligible views")
    require_equal(view.get("random_view_sampling"), False, "random view sampling")
    seed_lock = receipt.get("seed_lock", {})
    require_equal(
        seed_lock.get("calibration_seed"),
        lock["forward_only_resolution"]["calibration_seed"],
        "receipt calibration seed",
    )
    require_equal(
        seed_lock.get("weight_reused_for_seeds"),
        lock["training_budget"]["seeds"],
        "receipt training seed reuse",
    )

    inputs = receipt.get("inputs")
    if not isinstance(inputs, Mapping):
        raise ContractError("calibration receipt inputs must be an object")
    for required_input in (
        "calibration_lock",
        "calibration_scaffolds_manifest",
        "materialized_input_inventory",
        "dense_seed",
        "configs",
        "masks",
        "code",
    ):
        if required_input not in inputs:
            raise ContractError(
                f"calibration receipt is missing inputs.{required_input}"
            )
    lock_binding = inputs.get("calibration_lock")
    bound_lock = verify_binding(repo, lock_binding, "receipt.inputs.calibration_lock")
    require_equal(bound_lock, lock_path.resolve(), "receipt calibration lock path")
    verify_nested_bindings(repo, inputs, "receipt.inputs")

    input_validation = receipt.get("input_validation")
    if not isinstance(input_validation, Mapping):
        raise ContractError("calibration receipt input_validation must be an object")
    require_equal(
        input_validation.get("verified_before_and_after_forward"),
        True,
        "calibration input before/after verification",
    )
    require_equal(
        input_validation.get("common_04a_04b_view_shape_geometry_exact"),
        True,
        "calibration mask inventory control",
    )

    rows = receipt.get("resolved_weights")
    if not isinstance(rows, Mapping):
        raise ContractError("calibration receipt resolved_weights must be an object")
    values = {
        condition: _validate_ratio_row(
            rows.get(condition, {}),
            f"resolved_weights.{condition}",
            target_required=(condition != "04b"),
        )
        for condition in ("03", "04a", "04b")
    }
    require_equal(values["03"]["target_ratio"], 0.25, "03 target ratio")
    require_equal(values["04a"]["target_ratio"], 1.0, "04a target ratio")
    require_equal(rows["04b"].get("source_weight_condition"), "04a", "04b source weight")
    require_equal(values["04b"]["w_plane"], values["04a"]["w_plane"], "04 pair w_plane")

    medium = receipt.get("medium_verification", {})
    require_equal(medium.get("inclusive_ratio_range"), [0.5, 2.0], "medium ratio range")
    require_equal(medium.get("shared_weight_exact"), True, "medium shared weight")
    require_equal(medium.get("passed"), True, "medium verification")
    require_equal(medium.get("retuned_04b"), False, "04b retuning prohibition")
    conditions = medium.get("conditions", {})
    for condition in ("04a", "04b"):
        row = conditions.get(condition, {}) if isinstance(conditions, Mapping) else {}
        require_equal(row.get("passed"), True, f"medium {condition} passed")
        achieved = require_number(row.get("achieved_ratio"), f"medium {condition} ratio", positive=True)
        require_equal(achieved, values[condition]["achieved_ratio"], f"medium {condition} receipt ratio")
        if not 0.5 <= achieved <= 2.0:
            raise ContractError(f"medium {condition} ratio is outside [0.5,2.0]")
    return receipt, {condition: values[condition]["w_plane"] for condition in values}


def validate_mask_manifest(
    repo: Path,
    path: Path,
    *,
    source: str,
    consumers: Iterable[str],
) -> dict[str, Any]:
    try:
        mask_set = BinaryMaskSet(path)
    except Exception as exc:
        raise ContractError(f"invalid immutable binary mask set {path}: {exc}") from exc
    require_equal(mask_set.purpose, MaskPurpose.PLANE_REGION, f"{path} loader purpose")
    require_equal(mask_set.source.value, source, f"{path} loader source")
    require_equal(mask_set.consumer_arms, tuple(consumers), f"{path} loader consumers")
    for view_id in mask_set.records:
        try:
            mask_set.load(view_id)
        except Exception as exc:
            raise ContractError(f"invalid binary mask payload {path}/{view_id}: {exc}") from exc
    payload = load_json(path)
    require_equal(payload.get("schema"), "jointbuildgs.pilot_binary_view_masks.v1", f"{path} schema")
    require_equal(payload.get("run_id"), RUN_ID, f"{path} run_id")
    require_equal(payload.get("crs"), "EPSG:25832", f"{path} CRS")
    require_equal(payload.get("purpose"), "plane_region", f"{path} purpose")
    require_equal(payload.get("source"), source, f"{path} source")
    require_equal(payload.get("consumer_arms"), list(consumers), f"{path} consumers")
    require_equal(payload.get("binary_mask_only"), True, f"{path} binary-only")
    records = payload.get("records")
    if not isinstance(records, list) or not records:
        raise ContractError(f"{path} has no mask records")
    seen: set[str] = set()
    inventory: list[tuple[str, tuple[int, int], str]] = []
    for index, record in enumerate(records):
        if not isinstance(record, Mapping):
            raise ContractError(f"{path} record {index} is not an object")
        view_id = record.get("view_id")
        shape = record.get("shape")
        if not isinstance(view_id, str) or not view_id or view_id in seen:
            raise ContractError(f"{path} invalid/duplicate view_id: {view_id!r}")
        if not isinstance(shape, list) or len(shape) != 2 or any(type(v) is not int or v <= 0 for v in shape):
            raise ContractError(f"{path} invalid shape for {view_id}")
        mask_path = (path.parent / str(record.get("file", ""))).resolve()
        try:
            mask_path.relative_to(path.parent.resolve())
        except ValueError as exc:
            raise ContractError(f"{path} mask file escapes its root") from exc
        if not mask_path.is_file():
            raise ContractError(f"{path} missing mask file: {mask_path}")
        require_equal(sha256_file(mask_path), record.get("mask_sha256"), f"{path} mask SHA {view_id}")
        seen.add(view_id)
        inventory.append((view_id, (shape[0], shape[1]), str(record.get("geometry_sha256"))))
    if [item[0] for item in inventory] != sorted(seen):
        raise ContractError(f"{path} records must be sorted by view_id")
    return {"payload": payload, "inventory": inventory, "sha256": sha256_file(path)}


def _photo_manifest_inventory(path: Path) -> list[str]:
    try:
        mask_set = BinaryMaskSet(path)
    except Exception as exc:
        raise ContractError(f"invalid immutable photo-mask set {path}: {exc}") from exc
    require_equal(mask_set.purpose, MaskPurpose.PHOTO_SUPPORT, "photo mask loader purpose")
    require_equal(
        mask_set.source,
        MaskSource.LOD2_GROUNDSURFACE_XY_SFM_HEIGHT,
        "photo mask loader source",
    )
    for view_id in mask_set.records:
        try:
            mask_set.load(view_id)
        except Exception as exc:
            raise ContractError(f"invalid photo-mask payload {path}/{view_id}: {exc}") from exc
    payload = load_json(path)
    require_equal(payload.get("purpose"), "photo_support", "photo mask purpose")
    require_equal(payload.get("source"), "lod2_groundsurface_xy_sfm_height", "photo mask source")
    records = payload.get("records")
    if not isinstance(records, list) or not records:
        raise ContractError("photo mask has no records")
    return [str(row["view_id"]) for row in records]


def _extract_prep(prep_path: Path, repo: Path) -> tuple[list[str], list[float], Path]:
    prep = load_json(prep_path)
    require_equal(prep.get("schema"), "jointbuildgs.pilot_1wave.prep_manifest.v1", "prep schema")
    ids = prep.get("score_building_ids_rank_order")
    if not isinstance(ids, list) or not ids:
        raise ContractError("prep manifest has no score building IDs")
    shift = prep.get("world_shift")
    if not isinstance(shift, list) or len(shift) != 3:
        raise ContractError("prep manifest world_shift must have three values")
    source_sha = prep.get("source_sha256", {})
    footprint = resolve_repo_path(repo, "results/tum_transfer/analysis/footprints_aoi.geojson")
    if not footprint.is_file():
        raise ContractError(f"structure footprint source is missing: {footprint}")
    declared = (
        source_sha.get(repo_relative(repo, footprint))
        if isinstance(source_sha, Mapping)
        else None
    )
    if declared is not None:
        require_equal(sha256_file(footprint), declared, "prep footprint SHA")
    data_root = prep_path.parent / "data"
    if not data_root.is_dir():
        raise ContractError(f"prepared data root is missing: {data_root}")
    return [str(value) for value in ids], [float(value) for value in shift], footprint


def _extract_mono_dir(omnidata_path: Path, repo: Path) -> Path:
    payload = load_json(omnidata_path)
    require_equal(payload.get("schema"), "jointbuildgs.pilot_1wave.omnidata_normal.manifest.v1", "Omnidata schema")
    status = payload.get("state", payload.get("status"))
    require_equal(status, "complete", "Omnidata state")
    normal_dir = resolve_repo_path(repo, str(payload.get("normal_dir", "")))
    if not normal_dir.is_dir():
        raise ContractError(f"Omnidata normal directory is missing: {normal_dir}")
    return normal_dir


def _validated_plane_masks(
    repo: Path,
    *,
    mask_04a_path: Path,
    mask_04b_path: Path,
    photo_mask_path: Path,
) -> dict[str, dict[str, Any]]:
    masks: dict[str, dict[str, Any]] = {}
    for condition, path in (
        ("04a", mask_04a_path.resolve()),
        ("04b", mask_04b_path.resolve()),
    ):
        source, consumers = EXPECTED_MASKS[condition]
        masks[condition] = {
            **validate_mask_manifest(
                repo, path, source=source, consumers=consumers
            ),
            "path": path,
        }
    if masks["04a"]["inventory"] != masks["04b"]["inventory"]:
        raise ContractError(
            "04a/04b view, shape, and geometry inventories must match exactly"
        )
    photo_views = _photo_manifest_inventory(photo_mask_path)
    if [row[0] for row in masks["04a"]["inventory"]] != photo_views:
        raise ContractError(
            "04a/04b mask inventory must equal the common photo-mask inventory"
        )
    return masks


def _calibration_scaffold_config(
    *,
    repo: Path,
    lock: Mapping[str, Any],
    paths: Mapping[str, Path],
    mask_info: Mapping[str, Mapping[str, Any]],
    condition: str,
    arm: str,
    seed: int,
    data_root: Path,
    mono_dir: Path,
    materialized_inventory_path: Path,
    materialized_inventory_sha256: str,
) -> dict[str, Any]:
    """Return a forward-only scaffold; no optimizer or learning-run contract."""

    recipe = lock["base_recipe"]
    primitive = lock["plane_primitive"]
    init = lock["plane_guided_initialization"]
    config: dict[str, Any] = {
        "pilot_calibration_scaffold_schema": CALIBRATION_SCAFFOLD_SCHEMA,
        "pilot_calibration_only": True,
        "pilot_calibration_optimizer_objects_created": 0,
        "pilot_calibration_backward_calls": 0,
        "pilot_calibration_optimizer_updates": 0,
        "pilot_run_id": RUN_ID,
        "pilot_condition": condition,
        "pilot_arm": arm,
        "pilot_job_id": f"calibration_{condition}_seed{seed}",
        "pilot_calibration_lock_path": container_path(repo, paths["lock"]),
        "pilot_calibration_lock_sha256": sha256_file(paths["lock"]),
        "seed": seed,
        "device": "cuda",
        "data_root": container_path(repo, data_root),
        "pilot_materialized_input_inventory_path": container_path(
            repo, materialized_inventory_path
        ),
        "pilot_materialized_input_inventory_sha256": materialized_inventory_sha256,
        "init_pointcloud": container_path(repo, paths["dense_seed"]),
        "init_pointcloud_mode": "concat",
        "mvs_seed_init_opacity": 0.25,
        "downscale": 1.0,
        "sh_degree": 3,
        "sh_up_every": 1000,
        # The calibration runner validates max_iter only as a recipe identity
        # field.  The calibration-only flags above prohibit a training loop.
        "max_iter": 20000,
        "load_depth": True,
        "load_normal": True,
        "load_semantic": False,
        "seed_semantic": False,
        "normal_dir": None,
        "normal_encoding": "half_range",
        "depth_scale": 1.0,
        "mono_normal_dir": container_path(repo, mono_dir),
        "mono_normal_loss": "global",
        "w_photo": float(recipe["w_photo"]),
        "photo_lam": float(recipe["photo_lam"]),
        "w_depth": float(recipe["w_depth"]),
        "w_normal": float(recipe["w_normal_mvs"]),
        "w_mono_normal_aux": float(recipe["w_mono_normal_aux"]),
        "w_nc": float(recipe["w_nc"]),
        "w_structure": float(recipe["w_structure"]),
        "w_structure_na": float(recipe["w_structure_na"]),
        "w_structure_cp": float(recipe["w_structure_cp"]),
        "depth_warmup": int(recipe["depth_normal_warmup_updates"]),
        "depth_schedule": "ramp",
        "depth_ramp_steps": int(recipe["depth_normal_ramp_updates"]),
        "normal_warmup": int(recipe["depth_normal_warmup_updates"]),
        "normal_schedule": "ramp",
        "normal_ramp_steps": int(recipe["depth_normal_ramp_updates"]),
        "structure_grouping": "g2_geometry",
        "structure_voxel_size": float(recipe["structure_voxel_size_m"]),
        "structure_merge_n_cos": float(recipe["structure_merge_normal_cos"]),
        "structure_merge_d_tol": float(recipe["structure_merge_distance_m"]),
        "structure_min_group": int(recipe["structure_min_group"]),
        "structure_warmup": int(recipe["structure_warmup_updates"]),
        "structure_regroup_every": int(recipe["structure_regroup_every_updates"]),
        "roof_audit_mask_manifest": container_path(repo, paths["photo_mask"]),
        "photo_mask_manifest": container_path(repo, paths["photo_mask"]),
        "pilot_plane_window_size": int(primitive["window_size_px"]),
        "pilot_plane_stride": int(primitive["stride_px"]),
        "pilot_plane_min_points": int(primitive["minimum_points"]),
        "pilot_plane_alpha_threshold": float(primitive["alpha_threshold"]),
        "pilot_plane_max_depth_range": float(primitive["maximum_depth_range_m"]),
        "pilot_plane_min_second_eigenvalue": float(
            primitive["minimum_second_eigenvalue"]
        ),
    }
    for key in FORBIDDEN_WEIGHTS:
        config[key] = 0.0
    if condition in {"04a", "04b"}:
        info = mask_info[condition]
        config.update(
            {
                "plane_region_mask_manifest": container_path(repo, info["path"]),
                "pilot_plane_region_source": info["payload"]["source"],
                "pilot_plane_region_manifest_sha256": info["sha256"],
                "pilot_plane_init_stride_px": int(
                    init["pilot_plane_init_stride_px"]
                ),
                "pilot_plane_init_grid_offset_px": int(
                    init["pilot_plane_init_grid_offset_px"]
                ),
                "pilot_plane_init_knn": int(init["pilot_plane_init_knn"]),
                "pilot_plane_init_tolerance_m": float(
                    init["pilot_plane_init_tolerance_m"]
                ),
                "pilot_plane_init_min_coverage": float(
                    init["pilot_plane_init_min_coverage"]
                ),
                "pilot_plane_init_query_chunk_size": int(
                    init["pilot_plane_init_query_chunk_size"]
                ),
            }
        )
    return config


def build_calibration_plan(
    *,
    repo: Path,
    lock_path: Path,
    mask_04a_path: Path,
    mask_04b_path: Path,
    output_dir: Path,
    calibration_seed: int,
) -> tuple[list[dict[str, Any]], dict[str, Any], dict[str, Any]]:
    """Stage A: prepare three forward-only configs without a receipt."""

    if calibration_seed != 1001:
        raise ContractError("calibration seed is result-blind locked to exactly 1001")
    repo = repo.resolve()
    lock_path = lock_path.resolve()
    lock, bound = validate_lock(repo, lock_path)
    paths = {
        **bound,
        "lock": lock_path,
        "photo_mask": bound["projected_footprint_mask_manifest"],
    }
    masks = _validated_plane_masks(
        repo,
        mask_04a_path=mask_04a_path,
        mask_04b_path=mask_04b_path,
        photo_mask_path=paths["photo_mask"],
    )
    _building_ids, _world_shift, _footprint = _extract_prep(
        paths["prep_manifest"], repo
    )
    mono_dir = _extract_mono_dir(paths["omnidata_manifest"], repo)
    data_root = paths["prep_manifest"].parent / "data"
    materialized_inventory = build_materialized_input_inventory(
        repo=repo,
        data_root=data_root,
        mono_dir=mono_dir,
        view_ids=[row[0] for row in masks["04a"]["inventory"]],
    )
    materialized_inventory_path = output_dir.resolve() / "materialized_input_inventory.json"
    materialized_inventory_bytes = (
        json.dumps(
            materialized_inventory,
            ensure_ascii=False,
            indent=2,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")
    materialized_inventory_sha256 = sha256_bytes(materialized_inventory_bytes)
    configs = [
        _calibration_scaffold_config(
            repo=repo,
            lock=lock,
            paths=paths,
            mask_info=masks,
            condition=condition,
            arm=dict(CONDITIONS)[condition],
            seed=calibration_seed,
            data_root=data_root,
            mono_dir=mono_dir,
            materialized_inventory_path=materialized_inventory_path,
            materialized_inventory_sha256=materialized_inventory_sha256,
        )
        for condition in ("03", "04a", "04b")
    ]
    by_condition = {cfg["pilot_condition"]: cfg for cfg in configs}
    differences = pair_differences(by_condition["04a"], by_condition["04b"])
    unexpected = differences - PAIR_ALLOWED_DIFFERENCE_KEYS
    if unexpected:
        raise ContractError(
            "04a/04b calibration scaffolds differ outside mask provenance: "
            f"{sorted(unexpected)}"
        )
    if differences != PAIR_REQUIRED_SCAFFOLD_DIFFERENCE_KEYS:
        raise ContractError(
            "04a/04b calibration scaffold required differences changed: "
            f"expected={sorted(PAIR_REQUIRED_SCAFFOLD_DIFFERENCE_KEYS)} "
            f"actual={sorted(differences)}"
        )
    manifest = {
        "schema": CALIBRATION_SCAFFOLDS_MANIFEST_SCHEMA,
        "run_id": RUN_ID,
        "state": "prepared_forward_only",
        "pilot_calibration_only": True,
        "learning_runs_started": 0,
        "optimizer_audit": {
            "optimizer_objects_created": 0,
            "backward_calls": 0,
            "optimizer_updates": 0,
        },
        "calibration_seed": calibration_seed,
        "inputs": {
            "calibration_lock": {
                "path": repo_relative(repo, lock_path),
                "sha256": sha256_file(lock_path),
            },
            "04a_plane_mask": {
                "path": repo_relative(repo, mask_04a_path),
                "sha256": masks["04a"]["sha256"],
            },
            "04b_plane_mask": {
                "path": repo_relative(repo, mask_04b_path),
                "sha256": masks["04b"]["sha256"],
            },
            "materialized_input_inventory": {
                "path": repo_relative(repo, materialized_inventory_path),
                "sha256": materialized_inventory_sha256,
                "records_sha256": materialized_inventory["records_sha256"],
                "file_count": materialized_inventory["file_count"],
                "total_bytes": materialized_inventory["total_bytes"],
            },
        },
        "pair_control": {
            "allowed_difference_keys": sorted(PAIR_ALLOWED_DIFFERENCE_KEYS),
            "required_difference_keys": sorted(
                PAIR_REQUIRED_SCAFFOLD_DIFFERENCE_KEYS
            ),
            "difference_keys": sorted(differences),
            "passed": True,
        },
        "config_count": 3,
        "configs": [],
    }
    return configs, manifest, materialized_inventory


def validate_receipt_scaffolds(
    repo: Path,
    receipt: Mapping[str, Any],
    *,
    lock_path: Path,
    paths: Mapping[str, Path],
    masks: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    inputs = receipt["inputs"]
    scaffold_manifest_path = verify_binding(
        repo,
        inputs.get("calibration_scaffolds_manifest"),
        "receipt.inputs.calibration_scaffolds_manifest",
    )
    scaffold_manifest_sha256 = sha256_file(scaffold_manifest_path)
    if scaffold_manifest_path.stat().st_mode & 0o222:
        raise ContractError("calibration scaffold manifest must be immutable")
    if scaffold_manifest_path.parent.stat().st_mode & 0o222:
        raise ContractError("calibration scaffold bundle must be immutable")
    scaffold_manifest = load_json(scaffold_manifest_path)
    require_equal(
        scaffold_manifest.get("schema"),
        CALIBRATION_SCAFFOLDS_MANIFEST_SCHEMA,
        "calibration scaffold manifest schema",
    )
    require_equal(
        scaffold_manifest.get("run_id"), RUN_ID, "calibration scaffold run_id"
    )
    require_equal(
        scaffold_manifest.get("state"),
        "prepared_forward_only",
        "calibration scaffold state",
    )
    require_equal(
        scaffold_manifest.get("pilot_calibration_only"),
        True,
        "calibration scaffold-only state",
    )
    require_equal(
        scaffold_manifest.get("learning_runs_started"),
        0,
        "calibration scaffold learning count",
    )
    require_equal(
        scaffold_manifest.get("config_count"), 3, "calibration scaffold count"
    )

    manifest_inputs = scaffold_manifest.get("inputs")
    if not isinstance(manifest_inputs, Mapping):
        raise ContractError("calibration scaffold manifest inputs must be an object")
    manifest_lock_path = verify_binding(
        repo,
        manifest_inputs.get("calibration_lock"),
        "calibration_scaffold.inputs.calibration_lock",
    )
    require_equal(manifest_lock_path, lock_path.resolve(), "scaffold lock path")
    for condition, key in (("04a", "04a_plane_mask"), ("04b", "04b_plane_mask")):
        mask_path = verify_binding(
            repo,
            manifest_inputs.get(key),
            f"calibration_scaffold.inputs.{key}",
        )
        require_equal(mask_path, masks[condition]["path"], f"scaffold {condition} mask")

    inventory_path = verify_binding(
        repo,
        inputs.get("materialized_input_inventory"),
        "receipt.inputs.materialized_input_inventory",
    )
    inventory_sha256 = sha256_file(inventory_path)
    scaffold_inventory_path = verify_binding(
        repo,
        manifest_inputs.get("materialized_input_inventory"),
        "calibration_scaffold.inputs.materialized_input_inventory",
    )
    require_equal(scaffold_inventory_path, inventory_path, "scaffold inventory path")
    require_equal(
        str((manifest_inputs.get("materialized_input_inventory") or {}).get("sha256")),
        inventory_sha256,
        "scaffold inventory SHA256",
    )
    require_equal(
        inventory_path.parent,
        scaffold_manifest_path.parent,
        "inventory scaffold bundle",
    )
    if inventory_path.stat().st_mode & 0o222:
        raise ContractError("materialized input inventory must be immutable")
    materialized_inventory = validate_materialized_input_inventory(
        repo, inventory_path, expected_sha256=inventory_sha256
    )
    declared_inventory_audit = (receipt.get("input_validation") or {}).get(
        "materialized_input_inventory"
    )
    if not isinstance(declared_inventory_audit, Mapping):
        raise ContractError(
            "receipt input_validation.materialized_input_inventory is missing"
        )
    for key in ("schema", "records_sha256", "view_count", "file_count", "total_bytes"):
        require_equal(
            declared_inventory_audit.get(key),
            materialized_inventory.get(key),
            f"receipt materialized inventory {key}",
        )
    require_equal(
        declared_inventory_audit.get("sha256"),
        inventory_sha256,
        "receipt materialized inventory SHA256",
    )

    expected_bindings = {
        "dense_seed": paths["dense_seed"],
        "common_roof_audit": paths["photo_mask"],
        "04a_plane": masks["04a"]["path"],
        "04b_plane": masks["04b"]["path"],
    }
    actual_bindings = {
        "dense_seed": inputs.get("dense_seed"),
        "common_roof_audit": (inputs.get("masks") or {}).get(
            "common_roof_audit"
        ),
        "04a_plane": (inputs.get("masks") or {}).get("04a_plane"),
        "04b_plane": (inputs.get("masks") or {}).get("04b_plane"),
    }
    for name, expected_path in expected_bindings.items():
        actual_path = verify_binding(
            repo, actual_bindings[name], f"receipt.inputs.{name}"
        )
        require_equal(actual_path, expected_path.resolve(), f"receipt {name} path")

    config_bindings = inputs.get("configs")
    if not isinstance(config_bindings, Mapping) or set(config_bindings) != {
        "03",
        "04a",
        "04b",
    }:
        raise ContractError("receipt must bind exactly the three calibration configs")
    manifest_config_records = scaffold_manifest.get("configs")
    if not isinstance(manifest_config_records, list) or len(manifest_config_records) != 3:
        raise ContractError("calibration scaffold manifest must list three configs")
    manifest_configs: dict[str, Mapping[str, Any]] = {}
    for record in manifest_config_records:
        if not isinstance(record, Mapping):
            raise ContractError("calibration scaffold config record must be an object")
        condition = str(record.get("condition", ""))
        if condition in manifest_configs:
            raise ContractError(f"duplicate calibration scaffold condition: {condition}")
        manifest_configs[condition] = record
    require_equal(
        set(manifest_configs), {"03", "04a", "04b"}, "scaffold config conditions"
    )
    scaffolds: dict[str, dict[str, Any]] = {}
    for condition, arm in (("03", "03_plane_soft"), ("04a", "04a_plane_medium_vision"), ("04b", "04b_plane_medium_gt_upperbound")):
        config_path = verify_binding(
            repo,
            config_bindings[condition],
            f"receipt.inputs.configs.{condition}",
        )
        manifest_record = manifest_configs[condition]
        require_equal(
            manifest_record.get("pilot_arm"), arm, f"{condition} manifest arm"
        )
        require_equal(manifest_record.get("seed"), 1001, f"{condition} manifest seed")
        manifest_config_path = resolve_repo_path(
            repo, str(manifest_record.get("path", ""))
        )
        require_equal(
            manifest_config_path, config_path, f"{condition} manifest config path"
        )
        require_equal(
            manifest_record.get("sha256"),
            sha256_file(config_path),
            f"{condition} manifest config SHA256",
        )
        require_equal(
            config_path.parent,
            scaffold_manifest_path.parent,
            f"{condition} scaffold bundle",
        )
        if config_path.stat().st_mode & 0o222:
            raise ContractError(f"{condition} calibration scaffold must be immutable")
        try:
            config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError) as exc:
            raise ContractError(f"cannot read calibration scaffold {config_path}: {exc}") from exc
        if not isinstance(config, dict):
            raise ContractError(f"calibration scaffold is not a mapping: {config_path}")
        require_equal(
            config.get("pilot_calibration_scaffold_schema"),
            CALIBRATION_SCAFFOLD_SCHEMA,
            f"{condition} scaffold schema",
        )
        require_equal(config.get("pilot_calibration_only"), True, f"{condition} calibration-only")
        require_equal(config.get("pilot_condition"), condition, f"{condition} condition")
        require_equal(config.get("pilot_arm"), arm, f"{condition} arm")
        require_equal(
            config.get("pilot_calibration_lock_path"),
            container_path(repo, lock_path),
            f"{condition} lock path",
        )
        require_equal(
            config.get("pilot_calibration_lock_sha256"),
            sha256_file(lock_path),
            f"{condition} lock SHA",
        )
        require_equal(
            config.get("pilot_materialized_input_inventory_path"),
            container_path(repo, inventory_path),
            f"{condition} inventory path",
        )
        require_equal(
            config.get("pilot_materialized_input_inventory_sha256"),
            inventory_sha256,
            f"{condition} inventory SHA256",
        )
        require_equal(
            config.get("data_root"),
            container_path(
                repo,
                resolve_repo_path(repo, materialized_inventory["data_root"]),
            ),
            f"{condition} data root",
        )
        require_equal(
            config.get("mono_normal_dir"),
            container_path(
                repo,
                resolve_repo_path(repo, materialized_inventory["mono_normal_dir"]),
            ),
            f"{condition} mono normal directory",
        )
        for key in (
            "pilot_calibration_optimizer_objects_created",
            "pilot_calibration_backward_calls",
            "pilot_calibration_optimizer_updates",
        ):
            require_equal(config.get(key), 0, f"{condition} {key}")
        scaffolds[condition] = config
    differences = pair_differences(scaffolds["04a"], scaffolds["04b"])
    unexpected = differences - PAIR_ALLOWED_DIFFERENCE_KEYS
    if unexpected:
        raise ContractError(
            "receipt-bound 04a/04b scaffolds differ outside mask provenance: "
            f"{sorted(unexpected)}"
        )
    if differences != PAIR_REQUIRED_SCAFFOLD_DIFFERENCE_KEYS:
        raise ContractError(
            "receipt-bound 04a/04b scaffold required differences changed: "
            f"expected={sorted(PAIR_REQUIRED_SCAFFOLD_DIFFERENCE_KEYS)} "
            f"actual={sorted(differences)}"
        )
    return {
        "scaffold_manifest_path": scaffold_manifest_path,
        "scaffold_manifest_sha256": scaffold_manifest_sha256,
        "inventory_path": inventory_path,
        "inventory_sha256": inventory_sha256,
        "inventory": materialized_inventory,
    }


def _base_config(
    *,
    repo: Path,
    lock: Mapping[str, Any],
    paths: Mapping[str, Path],
    receipt_path: Path,
    receipt_sha: str,
    building_ids: list[str],
    world_shift: list[float],
    footprint_path: Path,
    data_root: Path,
    mono_dir: Path,
    materialized_inventory_path: Path,
    materialized_inventory_sha256: str,
    condition: str,
    arm: str,
    seed: int,
    output_root: Path,
    weights: Mapping[str, float],
    mask_info: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    recipe = lock["base_recipe"]
    primitive = lock["plane_primitive"]
    init = lock["plane_guided_initialization"]
    job_id = f"{condition}_seed{seed}"
    run_out = output_root / condition / f"seed_{seed}"
    config: dict[str, Any] = {
        "pilot_resolved_config_schema": SCHEMA,
        "pilot_run_id": RUN_ID,
        "pilot_condition": condition,
        "pilot_arm": arm,
        "pilot_job_id": job_id,
        "pilot_calibration_lock_path": container_path(repo, paths["lock"]),
        "pilot_calibration_lock_sha256": sha256_file(paths["lock"]),
        "pilot_calibration_receipt_path": container_path(repo, receipt_path),
        "pilot_calibration_receipt_sha256": receipt_sha,
        "seed": seed,
        "device": "cuda",
        "data_root": container_path(repo, data_root),
        "pilot_materialized_input_inventory_path": container_path(
            repo, materialized_inventory_path
        ),
        "pilot_materialized_input_inventory_sha256": (
            materialized_inventory_sha256
        ),
        "init_pointcloud": container_path(repo, paths["dense_seed"]),
        "init_pointcloud_mode": "concat",
        "mvs_seed_init_opacity": 0.10 if condition == "01" else 0.25,
        "seed_protect": condition != "01",
        "seed_protect_until_iter": None,
        "seed_log_footprints": container_path(repo, footprint_path),
        "seed_log_buildings": building_ids,
        "world_offset": world_shift,
        "downscale": 1.0,
        "sh_degree": 3,
        "sh_up_every": 1000,
        "w_photo": float(recipe["w_photo"]),
        "photo_lam": float(recipe["photo_lam"]),
        "w_depth": float(recipe["w_depth"]),
        "w_normal": float(recipe["w_normal_mvs"]),
        "w_mono_normal_aux": float(recipe["w_mono_normal_aux"]),
        "w_nc": float(recipe["w_nc"]),
        "w_structure": float(recipe["w_structure"]),
        "w_structure_na": float(recipe["w_structure_na"]),
        "w_structure_cp": float(recipe["w_structure_cp"]),
        "w_plane": float(weights[condition]) if condition in weights else 0.0,
        "load_depth": True,
        "load_normal": True,
        "load_semantic": False,
        "normal_dir": None,
        "normal_encoding": "half_range",
        "depth_scale": 1.0,
        "depth_warmup": int(recipe["depth_normal_warmup_updates"]),
        "depth_schedule": "ramp",
        "depth_ramp_steps": int(recipe["depth_normal_ramp_updates"]),
        "normal_warmup": int(recipe["depth_normal_warmup_updates"]),
        "normal_schedule": "ramp",
        "normal_ramp_steps": int(recipe["depth_normal_ramp_updates"]),
        "mono_normal_dir": container_path(repo, mono_dir),
        "mono_normal_loss": "global",
        "seed_semantic": False,
        "structure_grouping": "g2_geometry",
        "structure_voxel_size": float(recipe["structure_voxel_size_m"]),
        "structure_merge_n_cos": float(recipe["structure_merge_normal_cos"]),
        "structure_merge_d_tol": float(recipe["structure_merge_distance_m"]),
        "structure_min_group": int(recipe["structure_min_group"]),
        "structure_warmup": int(recipe["structure_warmup_updates"]),
        "structure_regroup_every": int(recipe["structure_regroup_every_updates"]),
        "structure_partition_footprints": container_path(repo, footprint_path),
        "structure_partition_buildings": building_ids,
        "structure_partition_world_offset": world_shift,
        "lr_means": 1.6e-4,
        "lr_scales": 5.0e-3,
        "lr_quats": 1.0e-3,
        "lr_opacities": 5.0e-2,
        "lr_sh0": 2.5e-3,
        "lr_shN": 1.25e-4,
        "prune_opa": 0.005,
        "grow_grad2d": 1.0e-3,
        "grow_scale3d": 0.01,
        "prune_scale3d": 0.1,
        "refine_start_iter": 500,
        "refine_stop_iter": 15000,
        "refine_every": 200,
        "reset_every": 3000,
        "max_iter": 20000,
        "eval_every": 2000,
        "ckpt_every": 5000,
        "full_state_checkpoint": True,
        "full_state_checkpoint_steps": [5000, 10000, 15000, 20000],
        "full_state_loss_csv_paths": [
            "audit/pilot_loss_shares.csv",
            "audit/pilot_loss_details.csv",
            "audit/pilot_plane_photo_ratio.csv",
        ],
        "full_state_resume": "auto",
        "pilot_loss_audit_every": 100,
        "roof_audit_mask_manifest": container_path(repo, paths["photo_mask"]),
        "out_dir": container_path(repo, run_out),
    }
    for key in FORBIDDEN_WEIGHTS:
        config[key] = 0.0
    if condition != "01":
        config["photo_mask_manifest"] = container_path(repo, paths["photo_mask"])
    if condition in {"03", "04a", "04b"}:
        config.update(
            {
                "pilot_plane_window_size": int(primitive["window_size_px"]),
                "pilot_plane_stride": int(primitive["stride_px"]),
                "pilot_plane_min_points": int(primitive["minimum_points"]),
                "pilot_plane_alpha_threshold": float(primitive["alpha_threshold"]),
                "pilot_plane_max_depth_range": float(primitive["maximum_depth_range_m"]),
                "pilot_plane_min_second_eigenvalue": float(primitive["minimum_second_eigenvalue"]),
            }
        )
    if condition in {"04a", "04b"}:
        info = mask_info[condition]
        config.update(
            {
                "plane_region_mask_manifest": container_path(repo, info["path"]),
                "pilot_plane_region_source": info["payload"]["source"],
                "pilot_plane_region_manifest_sha256": info["sha256"],
                "pilot_plane_init_stride_px": int(init["pilot_plane_init_stride_px"]),
                "pilot_plane_init_grid_offset_px": int(init["pilot_plane_init_grid_offset_px"]),
                "pilot_plane_init_knn": int(init["pilot_plane_init_knn"]),
                "pilot_plane_init_tolerance_m": float(init["pilot_plane_init_tolerance_m"]),
                "pilot_plane_init_min_coverage": float(init["pilot_plane_init_min_coverage"]),
                "pilot_plane_init_query_chunk_size": int(init["pilot_plane_init_query_chunk_size"]),
            }
        )
    return config


def pair_differences(left: Mapping[str, Any], right: Mapping[str, Any]) -> set[str]:
    return {
        key
        for key in set(left) | set(right)
        if left.get(key, object()) != right.get(key, object())
    }


def build_resolved_plan(
    *,
    repo: Path,
    lock_path: Path,
    receipt_path: Path,
    mask_04a_path: Path,
    mask_04b_path: Path,
    output_dir: Path,
    training_output_root: Path | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    repo = repo.resolve()
    lock_path = lock_path.resolve()
    receipt_path = receipt_path.resolve()
    output_dir = output_dir.resolve()
    training_output_root = (
        (output_dir.parent / "runs").resolve()
        if training_output_root is None
        else training_output_root.resolve()
    )
    repo_relative(repo, output_dir)
    repo_relative(repo, training_output_root)
    if (
        output_dir == training_output_root
        or output_dir in training_output_root.parents
        or training_output_root in output_dir.parents
    ):
        raise ContractError(
            "resolved config bundle and writable training output root must not overlap"
        )
    lock, bound = validate_lock(repo, lock_path)
    paths = {**bound, "lock": lock_path, "photo_mask": bound["projected_footprint_mask_manifest"]}
    receipt, weights = validate_receipt(repo, receipt_path, lock_path, lock)
    masks = _validated_plane_masks(
        repo,
        mask_04a_path=mask_04a_path,
        mask_04b_path=mask_04b_path,
        photo_mask_path=paths["photo_mask"],
    )
    receipt_scaffolds = validate_receipt_scaffolds(
        repo,
        receipt,
        lock_path=lock_path,
        paths=paths,
        masks=masks,
    )

    building_ids, world_shift, footprint = _extract_prep(paths["prep_manifest"], repo)
    mono_dir = _extract_mono_dir(paths["omnidata_manifest"], repo)
    data_root = paths["prep_manifest"].parent / "data"
    receipt_sha = sha256_file(receipt_path)

    configs: list[dict[str, Any]] = []
    for condition, arm in CONDITIONS:
        for seed in (1001, 1002):
            configs.append(
                _base_config(
                    repo=repo,
                    lock=lock,
                    paths=paths,
                    receipt_path=receipt_path,
                    receipt_sha=receipt_sha,
                    building_ids=building_ids,
                    world_shift=world_shift,
                    footprint_path=footprint,
                    data_root=data_root,
                    mono_dir=mono_dir,
                    materialized_inventory_path=receipt_scaffolds[
                        "inventory_path"
                    ],
                    materialized_inventory_sha256=receipt_scaffolds[
                        "inventory_sha256"
                    ],
                    condition=condition,
                    arm=arm,
                    seed=seed,
                    output_root=training_output_root,
                    weights=weights,
                    mask_info=masks,
                )
            )

    by_key = {(cfg["pilot_condition"], cfg["seed"]): cfg for cfg in configs}
    pair_audits = []
    for seed in (1001, 1002):
        differences = pair_differences(by_key[("04a", seed)], by_key[("04b", seed)])
        unexpected = differences - PAIR_ALLOWED_DIFFERENCE_KEYS
        if unexpected:
            raise ContractError(f"04a/04b pair differs outside mask provenance: {sorted(unexpected)}")
        if differences != PAIR_REQUIRED_TRAINING_DIFFERENCE_KEYS:
            raise ContractError(
                "04a/04b training pair required differences changed: "
                f"expected={sorted(PAIR_REQUIRED_TRAINING_DIFFERENCE_KEYS)} "
                f"actual={sorted(differences)}"
            )
        require_equal(
            by_key[("04a", seed)]["w_plane"],
            by_key[("04b", seed)]["w_plane"],
            f"04 pair weight seed {seed}",
        )
        pair_audits.append({"seed": seed, "difference_keys": sorted(differences), "passed": True})

    manifest = {
        "schema": SCHEMA,
        "run_id": RUN_ID,
        "state": "resolved",
        "learning_runs_started": 0,
        "inputs": {
            "calibration_lock": {"path": repo_relative(repo, lock_path), "sha256": sha256_file(lock_path)},
            "calibration_receipt": {"path": repo_relative(repo, receipt_path), "sha256": receipt_sha},
            "calibration_scaffolds_manifest": {
                "path": repo_relative(
                    repo, receipt_scaffolds["scaffold_manifest_path"]
                ),
                "sha256": receipt_scaffolds["scaffold_manifest_sha256"],
            },
            "materialized_input_inventory": {
                "path": repo_relative(repo, receipt_scaffolds["inventory_path"]),
                "sha256": receipt_scaffolds["inventory_sha256"],
                "records_sha256": receipt_scaffolds["inventory"][
                    "records_sha256"
                ],
                "view_count": receipt_scaffolds["inventory"]["view_count"],
                "file_count": receipt_scaffolds["inventory"]["file_count"],
                "total_bytes": receipt_scaffolds["inventory"]["total_bytes"],
            },
            "04a_plane_mask": {"path": repo_relative(repo, mask_04a_path), "sha256": masks["04a"]["sha256"]},
            "04b_plane_mask": {"path": repo_relative(repo, mask_04b_path), "sha256": masks["04b"]["sha256"]},
        },
        "resolved_weights": {"03": weights["03"], "04a": weights["04a"], "04b": weights["04b"]},
        "budget": copy.deepcopy(lock["training_budget"]),
        "training_output_root": {
            "path": repo_relative(repo, training_output_root),
            "container_path": container_path(repo, training_output_root),
            "writable_and_separate_from_config_bundle": True,
        },
        "pair_control": {
            "allowed_difference_keys": sorted(PAIR_ALLOWED_DIFFERENCE_KEYS),
            "required_difference_keys": sorted(
                PAIR_REQUIRED_TRAINING_DIFFERENCE_KEYS
            ),
            "audits": pair_audits,
            "shared_medium_weight_exact": True,
        },
        "config_count": len(configs),
        "jobs": [],
        "receipt_state": receipt["state"],
    }
    return configs, manifest


def render_config(config: Mapping[str, Any]) -> bytes:
    text = yaml.safe_dump(dict(config), sort_keys=False, allow_unicode=True)
    return text.encode("utf-8")


def publish_calibration_scaffolds(
    *,
    repo: Path,
    output_dir: Path,
    configs: list[dict[str, Any]],
    manifest: dict[str, Any],
    materialized_input_inventory: dict[str, Any],
) -> Path:
    output_dir = output_dir.resolve()
    repo_relative(repo, output_dir)
    if output_dir.exists():
        raise ContractError(
            f"calibration scaffold output must not already exist: {output_dir}"
        )
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(
        tempfile.mkdtemp(prefix=f".{output_dir.name}.", dir=output_dir.parent)
    )
    try:
        inventory_path = temporary / "materialized_input_inventory.json"
        inventory_path.write_text(
            json.dumps(
                materialized_input_inventory,
                ensure_ascii=False,
                indent=2,
                allow_nan=False,
            )
            + "\n",
            encoding="utf-8",
        )
        expected_inventory = manifest["inputs"]["materialized_input_inventory"]
        require_equal(
            sha256_file(inventory_path),
            expected_inventory["sha256"],
            "published materialized input inventory SHA256",
        )
        records = []
        for config in configs:
            condition = config["pilot_condition"]
            name = f"calibration_{condition}_seed{config['seed']}.yaml"
            data = render_config(config)
            (temporary / name).write_bytes(data)
            records.append(
                {
                    "condition": condition,
                    "pilot_arm": config["pilot_arm"],
                    "seed": config["seed"],
                    "path": repo_relative(repo, output_dir / name),
                    "sha256": sha256_bytes(data),
                }
            )
        manifest_path = temporary / "calibration_scaffolds_manifest.json"
        manifest_path.write_text(
            json.dumps(
                {**manifest, "configs": records},
                ensure_ascii=False,
                indent=2,
                allow_nan=False,
            )
            + "\n",
            encoding="utf-8",
        )
        for child in temporary.iterdir():
            child.chmod(0o444)
        os.replace(temporary, output_dir)
        output_dir.chmod(0o555)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    return output_dir / "calibration_scaffolds_manifest.json"


def publish_configs(
    *,
    repo: Path,
    output_dir: Path,
    configs: list[dict[str, Any]],
    manifest: dict[str, Any],
) -> Path:
    output_dir = output_dir.resolve()
    repo_relative(repo, output_dir)
    if output_dir.exists():
        raise ContractError(f"resolved config output must not already exist: {output_dir}")
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f".{output_dir.name}.", dir=output_dir.parent))
    try:
        records = []
        for config in configs:
            name = f"{config['pilot_condition']}_seed{config['seed']}.yaml"
            data = render_config(config)
            path = temporary / name
            path.write_bytes(data)
            records.append(
                {
                    "sequence": len(records) + 1,
                    "job_id": config["pilot_job_id"],
                    "condition": config["pilot_condition"],
                    "pilot_arm": config["pilot_arm"],
                    "seed": config["seed"],
                    "config_path": repo_relative(repo, output_dir / name),
                    "config_sha256": sha256_bytes(data),
                    "out_dir": config["out_dir"],
                }
            )
        manifest = {**manifest, "jobs": records}
        manifest_path = temporary / "resolved_configs_manifest.json"
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
            encoding="utf-8",
        )
        for child in temporary.iterdir():
            child.chmod(0o444)
        os.replace(temporary, output_dir)
        output_dir.chmod(0o555)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    return output_dir / "resolved_configs_manifest.json"


def parser() -> argparse.ArgumentParser:
    default_run = REPO / "phases/p2-gsjso/runs" / RUN_ID
    result = argparse.ArgumentParser(description=__doc__)
    subcommands = result.add_subparsers(dest="command", required=True)

    prepare = subcommands.add_parser(
        "prepare-calibration",
        help="publish three optimizer-free calibration scaffold YAMLs",
    )
    prepare.add_argument(
        "--calibration-lock",
        type=Path,
        default=REPO
        / "phases/p2-gsjso/configs/pilot_1wave_calibration_lock.json",
    )
    prepare.add_argument("--mask-04a", type=Path, required=True)
    prepare.add_argument("--mask-04b", type=Path, required=True)
    prepare.add_argument(
        "--calibration-seed", type=int, choices=(1001,), default=1001
    )
    prepare.add_argument(
        "--output-dir",
        type=Path,
        default=default_run / "calibration/scaffolds",
    )
    prepare.add_argument("--dry-run", action="store_true")

    resolve = subcommands.add_parser(
        "resolve-training", help="validate the receipt and publish ten training YAMLs"
    )
    resolve.add_argument(
        "--calibration-lock",
        type=Path,
        default=REPO
        / "phases/p2-gsjso/configs/pilot_1wave_calibration_lock.json",
    )
    resolve.add_argument(
        "--calibration-receipt",
        type=Path,
        default=default_run / "calibration/plane_calibration_receipt.json",
    )
    resolve.add_argument("--mask-04a", type=Path, required=True)
    resolve.add_argument("--mask-04b", type=Path, required=True)
    resolve.add_argument(
        "--output-dir",
        type=Path,
        default=default_run / "training/resolved_configs",
    )
    resolve.add_argument(
        "--training-output-root",
        type=Path,
        default=default_run / "training/runs",
        help="separate writable root for trainer outputs",
    )
    resolve.add_argument(
        "--dry-run", action="store_true", help="validate and print without writing"
    )
    return result


def main(argv: list[str] | None = None) -> int:
    require_docker()
    args = parser().parse_args(argv)
    if args.command == "prepare-calibration":
        configs, manifest, materialized_input_inventory = build_calibration_plan(
            repo=REPO,
            lock_path=args.calibration_lock,
            mask_04a_path=args.mask_04a,
            mask_04b_path=args.mask_04b,
            output_dir=args.output_dir,
            calibration_seed=args.calibration_seed,
        )
        if args.dry_run:
            print(
                json.dumps(
                    {
                        "state": "dry_run_calibration_scaffolds_validated",
                        "config_count": len(configs),
                        "conditions": [cfg["pilot_condition"] for cfg in configs],
                        "learning_runs_started": 0,
                        "optimizer_audit": manifest["optimizer_audit"],
                        "04_pair_control": manifest["pair_control"],
                    },
                    ensure_ascii=False,
                    indent=2,
                    allow_nan=False,
                )
            )
            return 0
        path = publish_calibration_scaffolds(
            repo=REPO,
            output_dir=args.output_dir,
            configs=configs,
            manifest=manifest,
            materialized_input_inventory=materialized_input_inventory,
        )
        print(
            json.dumps(
                {
                    "state": "calibration_scaffolds_published",
                    "manifest": repo_relative(REPO, path),
                    "config_count": len(configs),
                    "learning_runs_started": 0,
                },
                indent=2,
            )
        )
        return 0

    if args.command != "resolve-training":
        raise AssertionError(args.command)
    configs, manifest = build_resolved_plan(
        repo=REPO,
        lock_path=args.calibration_lock,
        receipt_path=args.calibration_receipt,
        mask_04a_path=args.mask_04a,
        mask_04b_path=args.mask_04b,
        output_dir=args.output_dir,
        training_output_root=args.training_output_root,
    )
    if args.dry_run:
        print(
            json.dumps(
                {
                    "state": "dry_run_validated",
                    "config_count": len(configs),
                    "jobs": [cfg["pilot_job_id"] for cfg in configs],
                    "resolved_weights": manifest["resolved_weights"],
                    "04_pair_control": manifest["pair_control"],
                },
                ensure_ascii=False,
                indent=2,
                allow_nan=False,
            )
        )
        return 0
    path = publish_configs(repo=REPO, output_dir=args.output_dir, configs=configs, manifest=manifest)
    print(json.dumps({"state": "published", "manifest": repo_relative(REPO, path), "config_count": len(configs)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
