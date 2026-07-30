#!/usr/bin/env python3
"""Pre-optimizer, fixed-view plane-weight calibration for pilot wave 1.

This runner deliberately has no optimizer construction, backward call, or
parameter update path.  It renders the immutable initial scaffold on the 16
pre-registered views, measures roof-scoped photo and plane losses, resolves one
soft weight for arm 03 and one shared medium weight for arms 04a/04b, and emits
an immutable receipt for the training driver.

The actual forward backend is imported lazily so the contract/resolver tests do
not need a materialized GroundedSAM/GT mask inventory.  Once those inventories
exist, execute this module in the normal ``jointbuildgs:dev`` CUDA container.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import random
import secrets
import stat
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Protocol, Sequence


REPO = Path(__file__).resolve().parents[3]
LOCK_PATH = REPO / "phases/p2-gsjso/configs/pilot_1wave/pilot_1wave_calibration_lock.json"
DEFAULT_OUTPUT = (
    REPO
    / "phases/p2-gsjso/runs/pilot_1wave/20260721_pilot_1wave/calibration"
    / "plane_calibration_receipt.json"
)
LOCK_SHA256 = "7eb4db2df284388c076b4e6876b169be389edb8d3da601931d3ca7997cdf54b4"
LOCK_SCHEMA = "jointbuildgs.pilot_1wave.calibration_lock.v1"
RECEIPT_SCHEMA = "jointbuildgs.pilot_1wave.plane_calibration_receipt.v1"
SYNTHETIC_RECEIPT_SCHEMA = (
    "jointbuildgs.pilot_1wave.plane_calibration_receipt.synthetic_test_only.v1"
)
SCAFFOLD_SCHEMA = "jointbuildgs.pilot_1wave.calibration_scaffold.v1"
SCAFFOLD_MANIFEST_SCHEMA = (
    "jointbuildgs.pilot_1wave.calibration_scaffolds_manifest.v1"
)
MATERIALIZED_INPUT_INVENTORY_SCHEMA = (
    "jointbuildgs.pilot_1wave.materialized_input_inventory.v1"
)
RUN_ID = "20260721_pilot_1wave"
EXPECTED_VIEW_COUNT = 16
EXPECTED_MINIMUM_ELIGIBLE_VIEWS = 8
EXPECTED_VIEW_IDS_SHA256 = "a1b88b85b63bab7572f5e9ea492e3e73cb0ebd5c2d6e01860f1af1b2f125acfe"
CALIBRATION_SEED = 1001
CALIBRATION_SEED_REASON = (
    "lowest registered training seed; locked result-blind before forward-only calibration"
)
OFFICIAL_BACKEND_ID = "jointbuildgs.stage2_forward_backend.v1"
SYNTHETIC_BACKEND_ID = "jointbuildgs.synthetic_test_backend.v1"
OFFICIAL_RUNTIME = {
    "container_required": True,
    "image_tag": "jointbuildgs:dev",
    "image_id": "sha256:926b2fd5e31d9f22d44db347b703ed1acfe0a98d19c189c80324daec63fd6396",
    "host_attestation_environment": {
        "image_tag": "P1W_HOST_IMAGE_TAG",
        "image_id": "P1W_HOST_IMAGE_ID",
    },
    "python": "3.11.15",
    "torch": "2.4.1+cu121",
    "cuda": "12.1",
    "gsplat": "1.4.0",
    "numpy": "1.26.4",
    "scipy": "1.13.1",
    "pillow": "10.4.0",
}
CONDITION_ARM = {
    "03": "03_plane_soft",
    "04a": "04a_plane_medium_vision",
    "04b": "04b_plane_medium_gt_upperbound",
}
PLANE_MASK_SOURCE = {
    "04a": "vision_groundedsam_roof",
    "04b": "lod2_roofsurface_gt_upperbound",
}
COMMON_MASK_SOURCE = "lod2_groundsurface_xy_sfm_height"
TARGET_RATIO = {"03": 0.25, "04a": 1.0}
MEDIUM_RANGE = (0.5, 2.0)
ALLOWED_SEEDS = (1001, 1002)
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
PAIR_REQUIRED_DIFFERENCE_KEYS = frozenset(
    {
        "pilot_arm",
        "pilot_condition",
        "pilot_job_id",
        "plane_region_mask_manifest",
        "pilot_plane_region_source",
        "pilot_plane_region_manifest_sha256",
    }
)
CODE_PATHS = {
    "runner": Path(__file__).resolve(),
    "train_contract": REPO / "src/stage2/train.py",
    "model": REPO / "src/stage2/model.py",
    "renderer": REPO / "src/stage2/renderer.py",
    "dataloader": REPO / "src/stage2/dataloader.py",
    "colmap_io": REPO / "src/stage2/colmap_io.py",
    "data_fitting": REPO / "src/stage2/loss/data_fitting.py",
    "planarity": REPO / "src/stage2/loss/planarity.py",
    "plane_guided_init": REPO / "src/stage2/plane_guided_init.py",
    "pointcloud_io": REPO / "src/stage2/pointcloud_io.py",
    "seed_control": REPO / "src/stage2/seed_control.py",
    "pilot_mask_schema": REPO / "src/stage2/pilot_mask_schema.py",
    "config_resolver": REPO
    / "scripts/pilot_1wave/pilot_1wave_resolved_configs.py",
}


@dataclass(frozen=True)
class ConditionBinding:
    condition_id: str
    pilot_arm: str
    seed: int
    config_path: Path
    config: dict[str, Any]
    dense_seed_path: Path
    common_mask_path: Path
    plane_mask_path: Path | None
    materialized_inventory_path: Path


@dataclass(frozen=True)
class ForwardMeasurement:
    condition_id: str
    view_id: str
    weighted_roof_photo: float | None
    raw_roof_plane: float | None
    plane_count: int
    plane_point_count: int
    eligible: bool
    reason: str


class ForwardBackend(Protocol):
    def evaluate(
        self,
        binding: ConditionBinding,
        *,
        view_ids: Sequence[str],
        lock: Mapping[str, Any],
    ) -> tuple[list[ForwardMeasurement], dict[str, Any]]:
        """Return one row per fixed view and an explicit zero-update audit."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_file(path: Path, block_size: int = 1 << 20) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(block_size), b""):
            digest.update(block)
    return digest.hexdigest()


def rel(path: Path | str) -> str:
    value = Path(path).resolve()
    try:
        return str(value.relative_to(REPO.resolve()))
    except ValueError:
        return str(value)


def atomic_json(path: Path, payload: Mapping[str, Any]) -> None:
    """Publish immutable JSON without ever replacing an existing directory entry."""

    path = path.absolute()
    if os.path.lexists(path):
        raise RuntimeError(f"refusing to overwrite calibration receipt: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.parent.is_symlink():
        raise RuntimeError(f"receipt parent must not be a symlink: {path.parent}")
    temporary = path.parent / (
        f".{path.name}.{os.getpid()}.{secrets.token_hex(8)}.tmp"
    )
    text = json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    try:
        with temporary.open("xb") as handle:
            handle.write(text.encode("utf-8"))
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o444)
        try:
            os.link(temporary, path)
        except FileExistsError as exc:
            raise RuntimeError(
                f"refusing to overwrite calibration receipt: {path}"
            ) from exc
        directory_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        if temporary.exists():
            temporary.unlink()
            directory_fd = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)


def _mode(path: Path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


def _require_regular_immutable_file(path: Path, label: str) -> None:
    if path.is_symlink() or not path.is_file():
        raise RuntimeError(f"{label} must be a regular non-symlink file: {path}")
    _require_equal(_mode(path), 0o444, f"{label} mode")


def _require_equal(actual: Any, expected: Any, label: str) -> None:
    if actual != expected:
        raise RuntimeError(f"{label} drift: {actual!r} != {expected!r}")


def _require_close(actual: Any, expected: float, label: str) -> None:
    try:
        value = float(actual)
    except (TypeError, ValueError) as exc:
        raise RuntimeError(f"{label} must be numeric") from exc
    if not math.isfinite(value) or not math.isclose(
        value, float(expected), rel_tol=0.0, abs_tol=1e-12
    ):
        raise RuntimeError(f"{label} drift: {actual!r} != {expected!r}")


def _view_ids_sha256(view_ids: Sequence[str]) -> str:
    return hashlib.sha256("\n".join(view_ids).encode("utf-8")).hexdigest()


def load_calibration_lock(path: Path = LOCK_PATH) -> dict[str, Any]:
    path = path.resolve()
    if not path.is_file():
        raise FileNotFoundError(path)
    if path == LOCK_PATH.resolve():
        _require_equal(sha256_file(path), LOCK_SHA256, "calibration lock SHA256")
    payload = json.loads(path.read_text(encoding="utf-8"))
    _require_equal(payload.get("schema"), LOCK_SCHEMA, "calibration lock schema")
    _require_equal(payload.get("run_id"), RUN_ID, "calibration run_id")
    _require_equal(payload.get("created_before_optimizer_results"), True, "result-blind lock")

    selection = payload.get("view_selection") or {}
    view_ids = [str(value) for value in selection.get("calibration_view_ids", [])]
    _require_equal(len(view_ids), EXPECTED_VIEW_COUNT, "calibration view count")
    _require_equal(len(set(view_ids)), EXPECTED_VIEW_COUNT, "unique calibration views")
    _require_equal(selection.get("calibration_count"), EXPECTED_VIEW_COUNT, "locked view count")
    _require_equal(_view_ids_sha256(view_ids), EXPECTED_VIEW_IDS_SHA256, "calibration view IDs SHA256")
    _require_equal(
        selection.get("calibration_view_ids_sha256_newline_joined"),
        EXPECTED_VIEW_IDS_SHA256,
        "declared calibration view IDs SHA256",
    )

    resolution = payload.get("forward_only_resolution") or {}
    _require_equal(resolution.get("optimizer_updates"), 0, "locked optimizer updates")
    _require_equal(resolution.get("random_view_sampling"), False, "random view sampling")
    _require_equal(resolution.get("calibration_seed"), CALIBRATION_SEED, "calibration seed")
    _require_equal(
        resolution.get("calibration_seed_reason"),
        CALIBRATION_SEED_REASON,
        "calibration seed reason",
    )
    _require_equal(
        resolution.get("minimum_eligible_views"),
        EXPECTED_MINIMUM_ELIGIBLE_VIEWS,
        "minimum eligible views",
    )
    _require_close(
        (resolution.get("soft_03") or {}).get("target_plane_to_photo_ratio"),
        TARGET_RATIO["03"],
        "soft target ratio",
    )
    _require_close(
        (resolution.get("medium_04a") or {}).get("target_plane_to_photo_ratio"),
        TARGET_RATIO["04a"],
        "medium target ratio",
    )
    _require_equal(
        (resolution.get("medium_04a") or {}).get("weight_reused_for_conditions"),
        ["04a", "04b"],
        "medium weight reuse conditions",
    )
    _require_equal(
        (resolution.get("medium_verification") or {}).get("conditions"),
        ["04a", "04b"],
        "medium verification conditions",
    )
    _require_equal(
        (resolution.get("medium_verification") or {}).get("inclusive_ratio_range"),
        list(MEDIUM_RANGE),
        "medium verification range",
    )
    _require_equal(resolution.get("no_post_update_recalibration"), True, "no recalibration")
    _require_equal(
        (payload.get("training_budget") or {}).get("seeds"),
        list(ALLOWED_SEEDS),
        "weight reuse seeds",
    )
    _require_equal(
        payload.get("forward_runtime"),
        OFFICIAL_RUNTIME,
        "locked forward runtime",
    )
    return payload


def _load_config(path: Path) -> dict[str, Any]:
    path = path.resolve()
    if path.suffix.lower() == ".json":
        payload = json.loads(path.read_text(encoding="utf-8"))
    else:
        try:
            import yaml
        except ModuleNotFoundError as exc:
            raise RuntimeError("YAML config requires PyYAML in the Stage2 container") from exc
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError(f"config must contain a mapping: {path}")
    return payload


def _resolve_path(value: Any, *, declaring_file: Path) -> Path:
    text = str(value or "").strip()
    if not text:
        raise RuntimeError(f"empty path in {declaring_file}")
    declared = Path(text)
    candidates = (
        (declared,)
        if declared.is_absolute()
        else (declaring_file.parent / declared, REPO / declared)
    )
    existing = [candidate.resolve() for candidate in candidates if candidate.exists()]
    unique = {str(candidate) for candidate in existing}
    if not unique:
        raise FileNotFoundError(f"declared path does not exist: {text} ({declaring_file})")
    if len(unique) != 1:
        raise RuntimeError(f"ambiguous declared path {text}: {sorted(unique)}")
    return Path(next(iter(unique)))


def _binding(path: Path) -> dict[str, str]:
    if not path.is_file():
        raise FileNotFoundError(path)
    return {"path": rel(path), "sha256": sha256_file(path)}


def _mask_source(path: Path) -> str:
    from src.stage2.pilot_mask_schema import BinaryMaskSet

    return BinaryMaskSet(path).source.value


def _validate_binary_mask_set(
    path: Path,
    *,
    expected_purpose: str,
    expected_source: str,
    expected_consumers: Sequence[str],
) -> dict[str, Any]:
    """Validate the closed manifest and every referenced NPZ payload."""

    from src.stage2.pilot_mask_schema import BinaryMaskSet

    path = path.resolve()
    mask_set = BinaryMaskSet(path)
    _require_equal(mask_set.purpose.value, expected_purpose, f"{path} mask purpose")
    _require_equal(mask_set.source.value, expected_source, f"{path} mask source")
    _require_equal(
        tuple(mask_set.consumer_arms),
        tuple(expected_consumers),
        f"{path} mask consumers",
    )
    inventory: list[tuple[str, tuple[int, int], str]] = []
    aggregate_positive_pixels = 0
    for view_id, record in mask_set.records.items():
        mask = mask_set.load(view_id)
        _require_equal(tuple(mask.shape), record.shape, f"{path}/{view_id} shape")
        aggregate_positive_pixels += int(mask.sum())
        inventory.append((view_id, record.shape, record.geometry_sha256))
    return {
        "path": path,
        "manifest_sha256": sha256_file(path),
        "inventory_sha256": mask_set.inventory_sha256,
        "source": mask_set.source.value,
        "purpose": mask_set.purpose.value,
        "consumer_arms": list(mask_set.consumer_arms),
        "record_count": len(inventory),
        "aggregate_positive_pixels": aggregate_positive_pixels,
        "inventory": inventory,
    }


def _validate_all_mask_inputs(
    *,
    common_path: Path,
    plane_04a_path: Path,
    plane_04b_path: Path,
    calibration_view_ids: Sequence[str],
) -> dict[str, dict[str, Any]]:
    common = _validate_binary_mask_set(
        common_path,
        expected_purpose="photo_support",
        expected_source=COMMON_MASK_SOURCE,
        expected_consumers=(
            "02_photo_control",
            "03_plane_soft",
            "04a_plane_medium_vision",
            "04b_plane_medium_gt_upperbound",
        ),
    )
    plane_a = _validate_binary_mask_set(
        plane_04a_path,
        expected_purpose="plane_region",
        expected_source=PLANE_MASK_SOURCE["04a"],
        expected_consumers=(CONDITION_ARM["04a"],),
    )
    plane_b = _validate_binary_mask_set(
        plane_04b_path,
        expected_purpose="plane_region",
        expected_source=PLANE_MASK_SOURCE["04b"],
        expected_consumers=(CONDITION_ARM["04b"],),
    )
    _require_equal(
        plane_a["inventory"],
        common["inventory"],
        "04a/common view-shape-geometry inventory",
    )
    _require_equal(
        plane_b["inventory"],
        common["inventory"],
        "04b/common view-shape-geometry inventory",
    )
    present = {row[0] for row in common["inventory"]}
    missing = [view_id for view_id in calibration_view_ids if view_id not in present]
    if missing:
        raise RuntimeError(f"mask inventory misses locked calibration views: {missing}")
    return {"common": common, "04a": plane_a, "04b": plane_b}


def _mask_audit_receipt(value: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: value[key]
        for key in (
            "manifest_sha256",
            "inventory_sha256",
            "source",
            "purpose",
            "consumer_arms",
            "record_count",
            "aggregate_positive_pixels",
        )
    }


def _validate_materialized_input_inventory(
    path: Path,
    *,
    expected_sha256: str,
) -> dict[str, Any]:
    from pilot_1wave_resolved_configs import validate_materialized_input_inventory

    path = path.resolve()
    payload = validate_materialized_input_inventory(
        REPO,
        path,
        expected_sha256=expected_sha256,
    )
    _require_equal(
        payload.get("schema"),
        MATERIALIZED_INPUT_INVENTORY_SCHEMA,
        "materialized input inventory schema",
    )
    view_ids = payload.get("view_ids")
    if not isinstance(view_ids, list) or not view_ids:
        raise RuntimeError("materialized input inventory view_ids must be nonempty")
    expected_role_counts = {
        "sfm_cameras": 1,
        "sfm_images": 1,
        "sfm_points3d": 1,
        "rgb": len(view_ids),
        "mvs_depth_geometric": len(view_ids),
        "mvs_normal_geometric": len(view_ids),
        "mono_normal_omnidata": len(view_ids),
    }
    _require_equal(
        payload.get("role_counts"),
        expected_role_counts,
        "materialized input inventory role counts",
    )
    _require_equal(
        payload.get("file_count"),
        3 + 4 * len(view_ids),
        "materialized input inventory file count",
    )
    return payload


def _resolve_manifest_binding(
    binding: Any,
    *,
    declaring_file: Path,
    label: str,
) -> Path:
    if not isinstance(binding, Mapping) or "path" not in binding or "sha256" not in binding:
        raise RuntimeError(f"{label} must be a path/SHA binding")
    path = _resolve_path(binding["path"], declaring_file=declaring_file)
    _require_equal(sha256_file(path), binding["sha256"], f"{label} SHA256")
    return path


def validate_scaffold_bundle(
    *,
    manifest_path: Path,
    manifest_sha256: str,
    config_paths: Mapping[str, Path],
    calibration_seed: int,
) -> tuple[dict[str, Any], Path, str]:
    manifest_path = manifest_path.resolve()
    _require_regular_immutable_file(manifest_path, "scaffold manifest")
    _require_equal(
        sha256_file(manifest_path), manifest_sha256, "scaffold manifest SHA256"
    )
    bundle = manifest_path.parent
    if bundle.is_symlink() or not bundle.is_dir():
        raise RuntimeError(f"scaffold bundle must be a non-symlink directory: {bundle}")
    _require_equal(_mode(bundle), 0o555, "scaffold bundle mode")
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    _require_equal(payload.get("schema"), SCAFFOLD_MANIFEST_SCHEMA, "scaffold manifest schema")
    _require_equal(payload.get("run_id"), RUN_ID, "scaffold manifest run_id")
    _require_equal(payload.get("state"), "prepared_forward_only", "scaffold manifest state")
    _require_equal(payload.get("pilot_calibration_only"), True, "scaffold manifest calibration-only")
    _require_equal(payload.get("learning_runs_started"), 0, "scaffold learning runs")
    for key in ("optimizer_objects_created", "backward_calls", "optimizer_updates"):
        _require_equal(
            int((payload.get("optimizer_audit") or {}).get(key, -1)),
            0,
            f"scaffold manifest {key}",
        )
    _require_equal(payload.get("calibration_seed"), calibration_seed, "scaffold calibration seed")
    _require_equal(payload.get("config_count"), 3, "scaffold config count")
    records = payload.get("configs")
    if not isinstance(records, list) or len(records) != 3:
        raise RuntimeError("scaffold manifest must bind exactly three configs")
    by_condition: dict[str, Mapping[str, Any]] = {}
    bound_children = {manifest_path}
    for record in records:
        if not isinstance(record, Mapping):
            raise RuntimeError("scaffold config record must be an object")
        condition = str(record.get("condition", ""))
        if condition in by_condition:
            raise RuntimeError(f"duplicate scaffold condition: {condition}")
        by_condition[condition] = record
    _require_equal(set(by_condition), set(CONDITION_ARM), "scaffold condition set")
    for condition in ("03", "04a", "04b"):
        record = by_condition[condition]
        _require_equal(record.get("pilot_arm"), CONDITION_ARM[condition], f"{condition} scaffold arm")
        _require_equal(record.get("seed"), calibration_seed, f"{condition} scaffold seed")
        path = _resolve_manifest_binding(
            record,
            declaring_file=manifest_path,
            label=f"{condition} scaffold config",
        )
        _require_equal(path, Path(config_paths[condition]).resolve(), f"{condition} scaffold path")
        _require_equal(path.parent, bundle, f"{condition} scaffold bundle")
        _require_regular_immutable_file(path, f"{condition} scaffold config")
        bound_children.add(path)
    inputs = payload.get("inputs") or {}
    inventory_binding = inputs.get("materialized_input_inventory")
    inventory_path = _resolve_manifest_binding(
        inventory_binding,
        declaring_file=manifest_path,
        label="materialized input inventory",
    )
    _require_equal(inventory_path.parent, bundle, "materialized inventory bundle")
    _require_regular_immutable_file(inventory_path, "materialized input inventory")
    bound_children.add(inventory_path)
    actual_children = set(bundle.iterdir())
    _require_equal(actual_children, bound_children, "scaffold bundle child set")
    return payload, inventory_path, str(inventory_binding["sha256"])


def _validate_plane_parameters(config: Mapping[str, Any], lock: Mapping[str, Any]) -> None:
    primitive = lock["plane_primitive"]
    pairs = {
        "pilot_plane_window_size": primitive["window_size_px"],
        "pilot_plane_stride": primitive["stride_px"],
        "pilot_plane_min_points": primitive["minimum_points"],
        "pilot_plane_alpha_threshold": primitive["alpha_threshold"],
        "pilot_plane_max_depth_range": primitive["maximum_depth_range_m"],
        "pilot_plane_min_second_eigenvalue": primitive["minimum_second_eigenvalue"],
    }
    for key, expected in pairs.items():
        if key not in config:
            raise RuntimeError(f"calibration config must explicitly set {key}")
        if isinstance(expected, float):
            _require_close(config[key], expected, f"config {key}")
        else:
            _require_equal(config[key], expected, f"config {key}")


def _validate_plane_guided_init_parameters(
    config: Mapping[str, Any], lock: Mapping[str, Any]
) -> None:
    initialization = lock["plane_guided_initialization"]
    keys = (
        "pilot_plane_init_stride_px",
        "pilot_plane_init_grid_offset_px",
        "pilot_plane_init_knn",
        "pilot_plane_init_tolerance_m",
        "pilot_plane_init_min_coverage",
        "pilot_plane_init_query_chunk_size",
    )
    for key in keys:
        if key not in config:
            raise RuntimeError(f"medium calibration config must explicitly set {key}")
        expected = initialization[key]
        if isinstance(expected, float):
            _require_close(config[key], expected, f"config {key}")
        else:
            _require_equal(config[key], expected, f"config {key}")


def validate_condition_binding(
    condition_id: str,
    config_path: Path,
    *,
    lock: Mapping[str, Any],
    lock_path: Path,
    calibration_seed: int,
    materialized_inventory_path: Path,
    materialized_inventory: Mapping[str, Any],
) -> ConditionBinding:
    if condition_id not in CONDITION_ARM:
        raise RuntimeError(f"unsupported calibration condition: {condition_id}")
    config_path = config_path.resolve()
    if not config_path.is_file():
        raise FileNotFoundError(config_path)
    config = _load_config(config_path)
    arm = CONDITION_ARM[condition_id]
    _require_equal(
        config.get("pilot_calibration_scaffold_schema"),
        SCAFFOLD_SCHEMA,
        f"{condition_id} calibration scaffold schema",
    )
    _require_equal(
        config.get("pilot_calibration_only"),
        True,
        f"{condition_id} calibration-only flag",
    )
    _require_equal(config.get("pilot_run_id"), RUN_ID, f"{condition_id} pilot_run_id")
    _require_equal(
        config.get("pilot_condition"), condition_id, f"{condition_id} pilot_condition"
    )
    _require_equal(config.get("pilot_arm"), arm, f"{condition_id} pilot_arm")
    declared_lock = _resolve_path(
        config.get("pilot_calibration_lock_path"), declaring_file=config_path
    )
    _require_equal(declared_lock, lock_path.resolve(), f"{condition_id} calibration lock path")
    _require_equal(
        config.get("pilot_calibration_lock_sha256"),
        sha256_file(lock_path.resolve()),
        f"{condition_id} calibration lock SHA256",
    )
    for field in (
        "pilot_calibration_optimizer_objects_created",
        "pilot_calibration_backward_calls",
        "pilot_calibration_optimizer_updates",
    ):
        _require_equal(config.get(field), 0, f"{condition_id} {field}")
    _require_equal(int(config.get("seed", -1)), calibration_seed, f"{condition_id} seed")
    _require_equal(int(config.get("max_iter", -1)), 20_000, f"{condition_id} max_iter")
    exact_fields = {
        "device": "cuda",
        "init_pointcloud_mode": "concat",
        "mvs_seed_init_opacity": 0.25,
        "downscale": 1.0,
        "sh_degree": 3,
        "load_depth": True,
        "load_normal": True,
        "load_semantic": False,
        "seed_semantic": False,
        "normal_dir": None,
        "normal_encoding": "half_range",
        "depth_scale": 1.0,
        "mono_normal_loss": "global",
    }
    for key, expected in exact_fields.items():
        if isinstance(expected, float):
            _require_close(config.get(key), expected, f"{condition_id} {key}")
        else:
            _require_equal(config.get(key), expected, f"{condition_id} {key}")
    _require_close(config.get("w_photo"), lock["base_recipe"]["w_photo"], f"{condition_id} w_photo")
    _require_close(config.get("photo_lam"), lock["base_recipe"]["photo_lam"], f"{condition_id} photo_lam")
    for key, recipe_key in (
        ("w_depth", "w_depth"),
        ("w_normal", "w_normal_mvs"),
        ("w_mono_normal_aux", "w_mono_normal_aux"),
    ):
        _require_close(
            config.get(key),
            lock["base_recipe"][recipe_key],
            f"{condition_id} {key}",
        )
    _validate_plane_parameters(config, lock)
    if config.get("visible_views") not in (None, []):
        raise RuntimeError("calibration config must not prefilter the locked 481-view inventory")
    if config.get("train_views") is not None or config.get("eval_views") is not None:
        raise RuntimeError("calibration uses the locked modulo-10 training role only")

    dense_binding = lock["input_bindings"]["dense_seed"]
    dense_seed = _resolve_path(config.get("init_pointcloud"), declaring_file=config_path)
    _require_equal(rel(dense_seed), dense_binding["path"], f"{condition_id} dense seed path")
    _require_equal(sha256_file(dense_seed), dense_binding["sha256"], f"{condition_id} dense seed SHA256")

    declared_inventory = _resolve_path(
        config.get("pilot_materialized_input_inventory_path"),
        declaring_file=config_path,
    )
    _require_equal(
        declared_inventory,
        materialized_inventory_path.resolve(),
        f"{condition_id} materialized inventory path",
    )
    _require_equal(
        config.get("pilot_materialized_input_inventory_sha256"),
        sha256_file(materialized_inventory_path),
        f"{condition_id} materialized inventory SHA256",
    )
    data_root = _resolve_path(config.get("data_root"), declaring_file=config_path)
    expected_data_root = _resolve_path(
        materialized_inventory.get("data_root"),
        declaring_file=materialized_inventory_path,
    )
    _require_equal(data_root, expected_data_root, f"{condition_id} data_root")
    mono_dir = _resolve_path(config.get("mono_normal_dir"), declaring_file=config_path)
    expected_mono_dir = _resolve_path(
        materialized_inventory.get("mono_normal_dir"),
        declaring_file=materialized_inventory_path,
    )
    _require_equal(mono_dir, expected_mono_dir, f"{condition_id} mono_normal_dir")

    common_binding = lock["input_bindings"]["projected_footprint_mask_manifest"]
    roof_audit = _resolve_path(config.get("roof_audit_mask_manifest"), declaring_file=config_path)
    photo_mask = _resolve_path(config.get("photo_mask_manifest"), declaring_file=config_path)
    _require_equal(roof_audit, photo_mask, f"{condition_id} common photo/audit mask path")
    _require_equal(rel(roof_audit), common_binding["path"], f"{condition_id} common mask path")
    _require_equal(sha256_file(roof_audit), common_binding["sha256"], f"{condition_id} common mask SHA256")
    _require_equal(_mask_source(roof_audit), COMMON_MASK_SOURCE, f"{condition_id} common mask source")

    plane_mask: Path | None = None
    if condition_id == "03":
        if config.get("plane_region_mask_manifest") not in (None, ""):
            raise RuntimeError("03 calibration must remain segmentation-free")
    else:
        _validate_plane_guided_init_parameters(config, lock)
        plane_mask = _resolve_path(
            config.get("plane_region_mask_manifest"), declaring_file=config_path
        )
        _require_equal(_mask_source(plane_mask), PLANE_MASK_SOURCE[condition_id], f"{condition_id} plane mask source")
        _require_equal(
            config.get("pilot_plane_region_source"),
            PLANE_MASK_SOURCE[condition_id],
            f"{condition_id} declared plane mask source",
        )
        _require_equal(
            config.get("pilot_plane_region_manifest_sha256"),
            sha256_file(plane_mask),
            f"{condition_id} declared plane mask SHA256",
        )

    return ConditionBinding(
        condition_id=condition_id,
        pilot_arm=arm,
        seed=calibration_seed,
        config_path=config_path,
        config=dict(config),
        dense_seed_path=dense_seed,
        common_mask_path=roof_audit,
        plane_mask_path=plane_mask,
        materialized_inventory_path=materialized_inventory_path.resolve(),
    )


def validate_medium_scaffold_pair(bindings: Mapping[str, ConditionBinding]) -> list[str]:
    left = bindings["04a"].config
    right = bindings["04b"].config
    marker = object()
    differences = {
        key
        for key in set(left) | set(right)
        if left.get(key, marker) != right.get(key, marker)
    }
    unexpected = differences - PAIR_ALLOWED_DIFFERENCE_KEYS
    if unexpected:
        raise RuntimeError(
            "04a/04b calibration scaffold differs outside mask provenance: "
            f"{sorted(unexpected)}"
        )
    missing = PAIR_REQUIRED_DIFFERENCE_KEYS - differences
    if missing:
        raise RuntimeError(
            "04a/04b calibration scaffold does not disclose required provenance "
            f"differences: {sorted(missing)}"
        )
    return sorted(differences)


def build_input_receipts(
    bindings: Mapping[str, ConditionBinding],
    *,
    lock_path: Path,
    scaffold_manifest_path: Path,
    materialized_inventory_path: Path,
) -> tuple[dict[str, Any], dict[str, Any]]:
    dense_paths = {binding.dense_seed_path.resolve() for binding in bindings.values()}
    common_paths = {binding.common_mask_path.resolve() for binding in bindings.values()}
    _require_equal(len(dense_paths), 1, "shared dense seed path count")
    _require_equal(len(common_paths), 1, "shared common mask path count")
    inputs = {
        "calibration_lock": _binding(lock_path.resolve()),
        "calibration_scaffolds_manifest": _binding(
            scaffold_manifest_path.resolve()
        ),
        "materialized_input_inventory": _binding(
            materialized_inventory_path.resolve()
        ),
        "dense_seed": _binding(next(iter(dense_paths))),
        "configs": {
            condition: _binding(bindings[condition].config_path)
            for condition in ("03", "04a", "04b")
        },
        "masks": {
            "common_roof_audit": _binding(next(iter(common_paths))),
            "04a_plane": _binding(bindings["04a"].plane_mask_path),
            "04b_plane": _binding(bindings["04b"].plane_mask_path),
        },
        "code": {name: _binding(path) for name, path in CODE_PATHS.items()},
    }
    mask_sources = {
        "common_roof_audit": _mask_source(next(iter(common_paths))),
        "03_plane_scope": "segmentation_free_local_plane_intersect_common_roof_audit",
        "04a_plane": _mask_source(bindings["04a"].plane_mask_path),
        "04b_plane": _mask_source(bindings["04b"].plane_mask_path),
    }
    return inputs, mask_sources


def _validate_backend_audit(
    condition: str,
    audit: Mapping[str, Any],
    *,
    synthetic: bool,
) -> None:
    for field in ("optimizer_objects_created", "backward_calls", "optimizer_updates"):
        _require_equal(int(audit.get(field, -1)), 0, f"{condition} {field}")
    _require_equal(audit.get("forward_only"), True, f"{condition} forward-only audit")
    _require_equal(audit.get("synthetic"), synthetic, f"{condition} synthetic audit")
    _require_equal(
        audit.get("backend_id"),
        SYNTHETIC_BACKEND_ID if synthetic else OFFICIAL_BACKEND_ID,
        f"{condition} backend ID",
    )


def attest_official_runtime(lock: Mapping[str, Any]) -> dict[str, Any]:
    """Attest the exact pinned CUDA software image from host-provided identity."""

    import platform

    import PIL
    import gsplat
    import numpy as np
    import scipy
    import torch

    expected = lock.get("forward_runtime")
    _require_equal(expected, OFFICIAL_RUNTIME, "official runtime lock")
    if not Path("/.dockerenv").is_file():
        raise RuntimeError("official calibration must run inside the pinned Docker image")
    env_names = OFFICIAL_RUNTIME["host_attestation_environment"]
    host_image_tag = os.environ.get(env_names["image_tag"])
    host_image_id = os.environ.get(env_names["image_id"])
    if host_image_tag is None or host_image_id is None:
        raise RuntimeError(
            "host must pass P1W_HOST_IMAGE_TAG and P1W_HOST_IMAGE_ID into the container"
        )
    actual_versions = {
        "python": platform.python_version(),
        "torch": str(torch.__version__),
        "cuda": str(torch.version.cuda),
        "gsplat": str(gsplat.__version__),
        "numpy": str(np.__version__),
        "scipy": str(scipy.__version__),
        "pillow": str(PIL.__version__),
    }
    _require_equal(host_image_tag, OFFICIAL_RUNTIME["image_tag"], "host image tag")
    _require_equal(host_image_id, OFFICIAL_RUNTIME["image_id"], "host image ID")
    for key, actual in actual_versions.items():
        _require_equal(actual, OFFICIAL_RUNTIME[key], f"runtime {key}")
    _require_equal(torch.cuda.is_available(), True, "runtime CUDA availability")
    return {
        "state": "official_attested",
        "synthetic": False,
        "container": True,
        "image_tag": host_image_tag,
        "image_id": host_image_id,
        "host_attestation_environment": dict(env_names),
        **actual_versions,
        "cuda_available": True,
        "cuda_device_count": int(torch.cuda.device_count()),
    }


def _aggregate_condition(
    condition: str,
    rows: Sequence[ForwardMeasurement],
    view_ids: Sequence[str],
) -> dict[str, Any]:
    _require_equal(len(rows), len(view_ids), f"{condition} measurement row count")
    _require_equal([row.view_id for row in rows], list(view_ids), f"{condition} fixed view order")
    if any(row.condition_id != condition for row in rows):
        raise RuntimeError(f"{condition} measurement condition drift")
    eligible = [row for row in rows if row.eligible]
    if len(eligible) < EXPECTED_MINIMUM_ELIGIBLE_VIEWS:
        raise RuntimeError(
            f"{condition} eligible views below lock: {len(eligible)} < {EXPECTED_MINIMUM_ELIGIBLE_VIEWS}"
        )
    photo_values: list[float] = []
    plane_values: list[float] = []
    for row in eligible:
        photo = float(row.weighted_roof_photo) if row.weighted_roof_photo is not None else math.nan
        plane = float(row.raw_roof_plane) if row.raw_roof_plane is not None else math.nan
        if not math.isfinite(photo) or not math.isfinite(plane) or photo <= 0.0 or plane <= 0.0:
            raise RuntimeError(f"{condition}/{row.view_id} eligible row has nonpositive/nonfinite losses")
        photo_values.append(photo)
        plane_values.append(plane)
    aggregate_photo = math.fsum(photo_values)
    aggregate_plane = math.fsum(plane_values)
    if aggregate_photo <= 0.0 or aggregate_plane <= 0.0:
        raise RuntimeError(f"{condition} aggregate losses must be positive")
    return {
        "eligible_view_count": len(eligible),
        "ineligible_view_count": len(rows) - len(eligible),
        "aggregate_weighted_roof_photo": aggregate_photo,
        "aggregate_raw_roof_plane": aggregate_plane,
        "view_rows": [asdict(row) for row in rows],
    }


def _calibrate_weight(photo: float, plane: float, target_ratio: float) -> float:
    # Reuse the Stage2 scalar contract.  Import is intentionally lazy so the
    # receipt schema can be inspected outside the CUDA image.
    from src.stage2.loss.planarity import calibrate_forward_only_plane_weight

    return calibrate_forward_only_plane_weight(
        photo,
        plane,
        target_ratio=target_ratio,
    )


def resolve_weights(
    measurements: Mapping[str, Sequence[ForwardMeasurement]],
    *,
    view_ids: Sequence[str],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    aggregates = {
        condition: _aggregate_condition(condition, measurements[condition], view_ids)
        for condition in ("03", "04a", "04b")
    }
    soft = aggregates["03"]
    medium_a = aggregates["04a"]
    medium_b = aggregates["04b"]
    soft_weight = _calibrate_weight(
        soft["aggregate_weighted_roof_photo"],
        soft["aggregate_raw_roof_plane"],
        TARGET_RATIO["03"],
    )
    medium_weight = _calibrate_weight(
        medium_a["aggregate_weighted_roof_photo"],
        medium_a["aggregate_raw_roof_plane"],
        TARGET_RATIO["04a"],
    )

    def achieved(weight: float, aggregate: Mapping[str, Any]) -> float:
        return float(
            weight
            * float(aggregate["aggregate_raw_roof_plane"])
            / float(aggregate["aggregate_weighted_roof_photo"])
        )

    ratio_03 = achieved(soft_weight, soft)
    ratio_04a = achieved(medium_weight, medium_a)
    ratio_04b = achieved(medium_weight, medium_b)
    lower, upper = MEDIUM_RANGE
    pass_04a = lower <= ratio_04a <= upper
    pass_04b = lower <= ratio_04b <= upper
    if not pass_04a or not pass_04b:
        raise RuntimeError(
            "shared medium weight failed locked verification without retuning: "
            f"04a={ratio_04a:.9f}, 04b={ratio_04b:.9f}, range={MEDIUM_RANGE}"
        )

    resolved = {
        "03": {
            "w_plane": soft_weight,
            "target_ratio": TARGET_RATIO["03"],
            "aggregate_weighted_roof_photo": soft["aggregate_weighted_roof_photo"],
            "aggregate_raw_roof_plane": soft["aggregate_raw_roof_plane"],
            "achieved_ratio": ratio_03,
            "eligible_view_count": soft["eligible_view_count"],
        },
        "04a": {
            "w_plane": medium_weight,
            "target_ratio": TARGET_RATIO["04a"],
            "aggregate_weighted_roof_photo": medium_a["aggregate_weighted_roof_photo"],
            "aggregate_raw_roof_plane": medium_a["aggregate_raw_roof_plane"],
            "achieved_ratio": ratio_04a,
            "eligible_view_count": medium_a["eligible_view_count"],
        },
        "04b": {
            "w_plane": medium_weight,
            "source_weight_condition": "04a",
            "target_ratio": None,
            "aggregate_weighted_roof_photo": medium_b["aggregate_weighted_roof_photo"],
            "aggregate_raw_roof_plane": medium_b["aggregate_raw_roof_plane"],
            "achieved_ratio": ratio_04b,
            "eligible_view_count": medium_b["eligible_view_count"],
        },
    }
    verification = {
        "inclusive_ratio_range": list(MEDIUM_RANGE),
        "conditions": {
            "04a": {"achieved_ratio": ratio_04a, "passed": pass_04a},
            "04b": {"achieved_ratio": ratio_04b, "passed": pass_04b},
        },
        "shared_weight_exact": resolved["04a"]["w_plane"] == resolved["04b"]["w_plane"],
        "passed": pass_04a and pass_04b,
        "retuned_04b": False,
    }
    forward_rows = {
        condition: aggregates[condition]["view_rows"]
        for condition in ("03", "04a", "04b")
    }
    return resolved, verification, forward_rows


class Stage2ForwardBackend:
    """Exact initial-scaffold Stage2 renderer with no optimizer code path."""

    def evaluate(
        self,
        binding: ConditionBinding,
        *,
        view_ids: Sequence[str],
        lock: Mapping[str, Any],
    ) -> tuple[list[ForwardMeasurement], dict[str, Any]]:
        import numpy as np
        import torch

        from src.stage2.dataloader import ColmapDataset, resolve_view_roles
        from src.stage2.loss import data_fitting as data_loss
        from src.stage2.loss.planarity import local_rendered_depth_coplanarity
        from src.stage2.model import GaussianModel2D
        from src.stage2.plane_guided_init import (
            PlaneGuidedInitConfig,
            build_plane_guided_initialization,
        )
        from src.stage2.pointcloud_io import read_init_pointcloud
        from src.stage2.renderer import render
        from src.stage2.seed_control import apply_mvs_seed_init_opacity

        cfg = binding.config
        seed = int(binding.seed)
        random.seed(seed)
        np.random.seed(seed)
        torch.manual_seed(seed)
        torch.cuda.manual_seed_all(seed)
        device = str(cfg.get("device", "cuda"))
        if not device.startswith("cuda") or not torch.cuda.is_available():
            raise RuntimeError("Stage2 plane calibration requires the CUDA dev container")

        primary_normal_dir = cfg.get("normal_dir")
        dataset = ColmapDataset(
            root=cfg["data_root"],
            downscale=cfg.get("downscale", 0.5),
            load_depth=True,
            load_normal=True,
            load_semantic=False,
            normal_dir=primary_normal_dir,
            mono_normal_dir=cfg.get("mono_normal_dir"),
            depth_scale=cfg.get("depth_scale", 1.0),
            normal_encoding=cfg.get("normal_encoding", "half_range"),
            photo_mask_manifest=str(binding.common_mask_path),
            roof_audit_mask_manifest=str(binding.common_mask_path),
            plane_region_mask_manifest=(
                None if binding.plane_mask_path is None else str(binding.plane_mask_path)
            ),
            pilot_arm=binding.pilot_arm,
        )
        train_idx, _test_idx, role_audit = resolve_view_roles(dataset.frames)
        frame_index = {frame.name: index for index, frame in enumerate(dataset.frames)}
        missing = [view_id for view_id in view_ids if view_id not in frame_index]
        if missing:
            raise RuntimeError(f"dataset misses calibration views: {missing}")
        if any(frame_index[view_id] not in train_idx for view_id in view_ids):
            raise RuntimeError("a calibration view is outside the locked modulo-10 training role")

        points_xyz = dataset.points_xyz
        points_rgb = dataset.points_rgb
        seed_xyz = read_init_pointcloud(str(binding.dense_seed_path))
        scene_rgb = dataset.points_rgb.mean(axis=0)
        seed_rgb = np.broadcast_to(scene_rgb, (len(seed_xyz), 3)).astype(np.float32).copy()
        mode = str(cfg.get("init_pointcloud_mode", "concat"))
        if mode == "replace":
            points_xyz = seed_xyz.astype(np.float32)
            points_rgb = seed_rgb
            mvs_seed_mask = np.ones(len(points_xyz), dtype=np.bool_)
            surface_seed_mask = np.zeros(len(points_xyz), dtype=np.bool_)
        elif mode == "concat":
            original_count = len(points_xyz)
            points_xyz = np.concatenate([points_xyz, seed_xyz], axis=0).astype(np.float32)
            points_rgb = np.concatenate([points_rgb, seed_rgb], axis=0).astype(np.float32)
            mvs_seed_mask = np.zeros(len(points_xyz), dtype=np.bool_)
            mvs_seed_mask[original_count:] = True
            surface_seed_mask = None
        else:  # already rejected during binding; defensive at the heavy boundary
            raise RuntimeError(f"unsupported init_pointcloud_mode: {mode}")
        opacity = apply_mvs_seed_init_opacity(
            len(points_xyz),
            mvs_seed_mask,
            None,
            cfg.get("mvs_seed_init_opacity"),
        )
        model = GaussianModel2D(
            points_xyz=points_xyz,
            points_rgb=points_rgb,
            sh_degree=cfg.get("sh_degree", 3),
            device=device,
            points_init_opacity=opacity,
            surface_seed_mask=surface_seed_mask,
        ).to(device)

        plane_init_audit: dict[str, Any] | None = None
        if binding.condition_id in {"04a", "04b"}:
            init_lock = lock["plane_guided_initialization"]
            init_config = PlaneGuidedInitConfig(
                stride_px=int(init_lock["pilot_plane_init_stride_px"]),
                grid_offset_px=int(init_lock["pilot_plane_init_grid_offset_px"]),
                knn=int(init_lock["pilot_plane_init_knn"]),
                tolerance_m=float(init_lock["pilot_plane_init_tolerance_m"]),
                min_coverage=float(init_lock["pilot_plane_init_min_coverage"]),
                query_chunk_size=int(init_lock["pilot_plane_init_query_chunk_size"]),
            )
            initialization = build_plane_guided_initialization(
                dataset=dataset,
                training_view_indices=train_idx,
                mvs_seed_xyz=points_xyz[mvs_seed_mask],
                plane_mask_binding=dataset.plane_region_mask_binding,
                pilot_arm=binding.pilot_arm,
                config=init_config,
            )
            model.initialize_normals_from_world(
                torch.from_numpy(initialization.normals_world_up),
                torch.from_numpy(mvs_seed_mask),
            )
            plane_init_audit = {
                "binding_sha256": initialization.audit["binding_sha256"],
                "algorithm_sha256": initialization.audit["algorithm_sha256"],
                "counts": initialization.audit["counts"],
            }

        primitive = lock["plane_primitive"]
        rows: list[ForwardMeasurement] = []
        with torch.no_grad():
            for view_id in view_ids:
                index = frame_index[view_id]
                batch = dataset[index]
                height, width = int(batch["height"]), int(batch["width"])
                w2c = batch["w2c"].to(device)
                intrinsics = batch["K"].to(device)
                rendered = render(
                    model,
                    w2c,
                    intrinsics,
                    width,
                    height,
                    sh_degree=model.active_sh_degree,
                    render_mode="RGB+ED",
                )
                roof_mask = batch["roof_audit_mask"].to(device=device, dtype=torch.bool)
                photo = data_loss.l_photo(
                    rendered["rgb"],
                    batch["rgb"].to(device),
                    lam=float(lock["base_recipe"]["photo_lam"]),
                    mask=roof_mask,
                )
                valid_mask = roof_mask
                if binding.condition_id in {"04a", "04b"}:
                    valid_mask = valid_mask & batch["plane_region_mask"].to(
                        device=device, dtype=torch.bool
                    )
                plane = local_rendered_depth_coplanarity(
                    rendered["depth"],
                    intrinsics,
                    alpha=rendered["alpha"],
                    valid_mask=valid_mask,
                    window_size=int(primitive["window_size_px"]),
                    stride=int(primitive["stride_px"]),
                    min_points=int(primitive["minimum_points"]),
                    alpha_threshold=float(primitive["alpha_threshold"]),
                    max_depth_range=float(primitive["maximum_depth_range_m"]),
                    min_second_eigenvalue=float(primitive["minimum_second_eigenvalue"]),
                )
                weighted_photo = float(
                    float(lock["base_recipe"]["w_photo"]) * photo.detach().cpu().item()
                )
                raw_plane = float(plane.loss.detach().cpu().item())
                eligible = (
                    math.isfinite(weighted_photo)
                    and math.isfinite(raw_plane)
                    and weighted_photo > 0.0
                    and raw_plane > 0.0
                    and int(plane.plane_count) > 0
                    and int(plane.point_count) > 0
                )
                rows.append(
                    ForwardMeasurement(
                        condition_id=binding.condition_id,
                        view_id=view_id,
                        weighted_roof_photo=weighted_photo,
                        raw_roof_plane=raw_plane,
                        plane_count=int(plane.plane_count),
                        plane_point_count=int(plane.point_count),
                        eligible=eligible,
                        reason="eligible" if eligible else "nonpositive_or_empty_plane_measurement",
                    )
                )

        audit = {
            "backend_id": OFFICIAL_BACKEND_ID,
            "synthetic": False,
            "forward_only": True,
            "optimizer_objects_created": 0,
            "backward_calls": 0,
            "optimizer_updates": 0,
            "model_initial_point_count": int(model.num_points),
            "mvs_seed_point_count": int(mvs_seed_mask.sum()),
            "view_role_mode": role_audit["mode"],
            "plane_guided_initialization": plane_init_audit,
        }
        del model
        torch.cuda.empty_cache()
        return rows, audit


def _ensure_output_absent(output: Path) -> None:
    if os.path.lexists(output):
        raise RuntimeError(f"refusing to overwrite calibration receipt: {output}")


def _execute_calibration(
    *,
    config_paths: Mapping[str, Path],
    calibration_seed: int,
    output: Path,
    backend: ForwardBackend,
    synthetic: bool,
    runtime_attestation: Mapping[str, Any],
    scaffold_manifest_path: Path,
    scaffold_manifest_sha256: str,
    lock_path: Path = LOCK_PATH,
) -> dict[str, Any]:
    if not synthetic and type(backend) is not Stage2ForwardBackend:
        raise RuntimeError("official receipt requires the exact Stage2ForwardBackend")
    if calibration_seed != CALIBRATION_SEED:
        raise RuntimeError(
            f"calibration_seed must equal the result-blind lock: {CALIBRATION_SEED}"
        )
    _ensure_output_absent(output)
    lock = load_calibration_lock(lock_path)
    view_ids = [str(value) for value in lock["view_selection"]["calibration_view_ids"]]
    _require_equal(set(config_paths), set(CONDITION_ARM), "calibration config condition set")
    scaffold_manifest, materialized_inventory_path, materialized_inventory_sha256 = (
        validate_scaffold_bundle(
            manifest_path=scaffold_manifest_path,
            manifest_sha256=scaffold_manifest_sha256,
            config_paths=config_paths,
            calibration_seed=calibration_seed,
        )
    )
    materialized_inventory = _validate_materialized_input_inventory(
        materialized_inventory_path,
        expected_sha256=materialized_inventory_sha256,
    )
    bindings = {
        condition: validate_condition_binding(
            condition,
            Path(config_paths[condition]),
            lock=lock,
            lock_path=lock_path,
            calibration_seed=calibration_seed,
            materialized_inventory_path=materialized_inventory_path,
            materialized_inventory=materialized_inventory,
        )
        for condition in ("03", "04a", "04b")
    }
    pair_differences = validate_medium_scaffold_pair(bindings)
    plane_04a_path = bindings["04a"].plane_mask_path
    plane_04b_path = bindings["04b"].plane_mask_path
    if plane_04a_path is None or plane_04b_path is None:
        raise AssertionError("medium calibration bindings must have plane masks")
    masks_before = _validate_all_mask_inputs(
        common_path=bindings["03"].common_mask_path,
        plane_04a_path=plane_04a_path,
        plane_04b_path=plane_04b_path,
        calibration_view_ids=view_ids,
    )
    _require_equal(
        materialized_inventory["view_ids"],
        [row[0] for row in masks_before["common"]["inventory"]],
        "materialized/mask full view inventory",
    )
    inputs, mask_sources = build_input_receipts(
        bindings,
        lock_path=lock_path,
        scaffold_manifest_path=scaffold_manifest_path,
        materialized_inventory_path=materialized_inventory_path,
    )

    measurements: dict[str, list[ForwardMeasurement]] = {}
    backend_audits: dict[str, dict[str, Any]] = {}
    for condition in ("03", "04a", "04b"):
        rows, audit = backend.evaluate(bindings[condition], view_ids=view_ids, lock=lock)
        _validate_backend_audit(condition, audit, synthetic=synthetic)
        measurements[condition] = rows
        backend_audits[condition] = dict(audit)
    scaffold_manifest_after, inventory_path_after, inventory_sha_after = (
        validate_scaffold_bundle(
            manifest_path=scaffold_manifest_path,
            manifest_sha256=scaffold_manifest_sha256,
            config_paths=config_paths,
            calibration_seed=calibration_seed,
        )
    )
    _require_equal(scaffold_manifest_after, scaffold_manifest, "forward scaffold manifest")
    _require_equal(inventory_path_after, materialized_inventory_path, "forward inventory path")
    _require_equal(inventory_sha_after, materialized_inventory_sha256, "forward inventory SHA")
    materialized_inventory_after = _validate_materialized_input_inventory(
        inventory_path_after,
        expected_sha256=inventory_sha_after,
    )
    _require_equal(
        materialized_inventory_after,
        materialized_inventory,
        "forward materialized input inventory",
    )
    masks_after = _validate_all_mask_inputs(
        common_path=bindings["03"].common_mask_path,
        plane_04a_path=plane_04a_path,
        plane_04b_path=plane_04b_path,
        calibration_view_ids=view_ids,
    )
    _require_equal(masks_after, masks_before, "forward binary-mask payload inventory")
    inputs_after_forward, mask_sources_after_forward = build_input_receipts(
        bindings,
        lock_path=lock_path,
        scaffold_manifest_path=scaffold_manifest_path,
        materialized_inventory_path=materialized_inventory_path,
    )
    _require_equal(inputs_after_forward, inputs, "forward input SHA receipts")
    _require_equal(
        mask_sources_after_forward,
        mask_sources,
        "forward mask-source receipts",
    )
    resolved, medium_verification, forward_rows = resolve_weights(
        measurements,
        view_ids=view_ids,
    )
    if resolved["04a"]["w_plane"] != resolved["04b"]["w_plane"]:
        raise AssertionError("04b medium weight was not reused exactly from 04a")

    receipt = {
        "schema": SYNTHETIC_RECEIPT_SCHEMA if synthetic else RECEIPT_SCHEMA,
        "run_id": RUN_ID,
        "state": "nonofficial_test_only" if synthetic else "complete",
        "official": not synthetic,
        "official_backend_id": None if synthetic else OFFICIAL_BACKEND_ID,
        "synthetic": synthetic,
        "created_utc": utc_now(),
        "mode": (
            "synthetic_forward_contract_test_only"
            if synthetic
            else "forward_only_preoptimizer_fixed_views"
        ),
        "backend": {
            "id": SYNTHETIC_BACKEND_ID if synthetic else OFFICIAL_BACKEND_ID,
            "synthetic": synthetic,
        },
        "runtime_attestation": dict(runtime_attestation),
        "seed_lock": {
            "calibration_seed": calibration_seed,
            "calibration_seed_reason": CALIBRATION_SEED_REASON,
            "weight_reused_for_seeds": list(ALLOWED_SEEDS),
        },
        "optimizer_audit": {
            "optimizer_objects_created": 0,
            "backward_calls": 0,
            "optimizer_updates": 0,
        },
        "view_lock": {
            "view_ids": view_ids,
            "view_ids_sha256": _view_ids_sha256(view_ids),
            "view_count": len(view_ids),
            "minimum_eligible_views": EXPECTED_MINIMUM_ELIGIBLE_VIEWS,
            "random_view_sampling": False,
        },
        "inputs": inputs,
        "mask_sources": mask_sources,
        "input_validation": {
            "verified_before_and_after_forward": True,
            "scaffold_bundle": {
                "manifest_sha256": scaffold_manifest_sha256,
                "directory_mode": "0555",
                "file_mode": "0444",
            },
            "materialized_input_inventory": {
                "schema": materialized_inventory["schema"],
                "sha256": materialized_inventory_sha256,
                "records_sha256": materialized_inventory["records_sha256"],
                "view_count": materialized_inventory["view_count"],
                "file_count": materialized_inventory["file_count"],
                "total_bytes": materialized_inventory["total_bytes"],
            },
            "binary_mask_payloads": {
                name: _mask_audit_receipt(masks_before[name])
                for name in ("common", "04a", "04b")
            },
            "common_04a_04b_view_shape_geometry_exact": True,
        },
        "config_contract": {
            "calibration_scaffold_schema": SCAFFOLD_SCHEMA,
            "calibration_only": True,
            "conditions": {
                condition: {
                    "pilot_arm": bindings[condition].pilot_arm,
                    "seed": bindings[condition].seed,
                }
                for condition in ("03", "04a", "04b")
            },
            "04_pair_control": {
                "allowed_difference_keys": sorted(PAIR_ALLOWED_DIFFERENCE_KEYS),
                "observed_difference_keys": pair_differences,
                "passed": True,
            },
        },
        "resolved_weights": resolved,
        "medium_verification": medium_verification,
        "forward_measurements": forward_rows,
        "backend_audits": backend_audits,
        "post_update_recalibration": False,
    }
    atomic_json(output, receipt)
    return receipt


def run_calibration(
    *,
    config_paths: Mapping[str, Path],
    calibration_seed: int,
    output: Path,
    scaffold_manifest_path: Path,
    scaffold_manifest_sha256: str,
    lock_path: Path = LOCK_PATH,
) -> dict[str, Any]:
    """Run the sole official publisher with the non-injectable Stage2 backend."""

    _ensure_output_absent(output)
    lock = load_calibration_lock(lock_path)
    runtime_attestation = attest_official_runtime(lock)
    return _execute_calibration(
        config_paths=config_paths,
        calibration_seed=calibration_seed,
        output=output,
        backend=Stage2ForwardBackend(),
        synthetic=False,
        runtime_attestation=runtime_attestation,
        scaffold_manifest_path=scaffold_manifest_path,
        scaffold_manifest_sha256=scaffold_manifest_sha256,
        lock_path=lock_path,
    )


def _run_synthetic_calibration_for_test(
    *,
    config_paths: Mapping[str, Path],
    calibration_seed: int,
    output: Path,
    backend: ForwardBackend,
    scaffold_manifest_path: Path,
    scaffold_manifest_sha256: str,
    lock_path: Path,
) -> dict[str, Any]:
    """Exercise contract math while making an official receipt impossible."""

    return _execute_calibration(
        config_paths=config_paths,
        calibration_seed=calibration_seed,
        output=output,
        backend=backend,
        synthetic=True,
        runtime_attestation={
            "state": "synthetic_test_only",
            "synthetic": True,
        },
        scaffold_manifest_path=scaffold_manifest_path,
        scaffold_manifest_sha256=scaffold_manifest_sha256,
        lock_path=lock_path,
    )


def cli() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("check-lock")
    run = sub.add_parser("run")
    run.add_argument("--config-03", type=Path, required=True)
    run.add_argument("--config-04a", type=Path, required=True)
    run.add_argument("--config-04b", type=Path, required=True)
    run.add_argument("--scaffold-manifest", type=Path, required=True)
    run.add_argument("--scaffold-manifest-sha256", required=True)
    run.add_argument(
        "--calibration-seed",
        type=int,
        choices=(CALIBRATION_SEED,),
        required=True,
    )
    run.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def main() -> None:
    args = cli()
    if args.command == "check-lock":
        lock = load_calibration_lock()
        print(
            json.dumps(
                {
                    "schema": lock["schema"],
                    "view_count": len(lock["view_selection"]["calibration_view_ids"]),
                    "view_ids_sha256": EXPECTED_VIEW_IDS_SHA256,
                    "calibration_seed": CALIBRATION_SEED,
                    "optimizer_updates": 0,
                }
            )
        )
        return
    if args.command == "run":
        receipt = run_calibration(
            config_paths={
                "03": args.config_03,
                "04a": args.config_04a,
                "04b": args.config_04b,
            },
            calibration_seed=args.calibration_seed,
            output=args.output,
            scaffold_manifest_path=args.scaffold_manifest,
            scaffold_manifest_sha256=args.scaffold_manifest_sha256,
        )
        print(
            json.dumps(
                {
                    "receipt": rel(args.output),
                    "receipt_sha256": sha256_file(args.output),
                    "resolved_weights": receipt["resolved_weights"],
                }
            )
        )
        return
    raise AssertionError(args.command)


if __name__ == "__main__":
    main()
