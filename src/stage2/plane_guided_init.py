"""Deterministic MVS plane-guided initialization for pilot arms 04a/04b.

The two medium arms call the exact same functions in this module.  Their only
allowed difference is the immutable plane-region mask manifest bound by the
dataset.  Evidence comes exclusively from fixed training cameras, image-derived
MVS depth, and world-frame MVS normals.
"""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

import numpy as np
from scipy.spatial import cKDTree


AUDIT_SCHEMA = "jointbuildgs.pilot_1wave.plane_guided_init.v1"
RESUME_AUDIT_SCHEMA = (
    "jointbuildgs.pilot_1wave.plane_guided_init_resume_verification.v1"
)
ALGORITHM = "masked_mvs_depth_world_normal_knn_to_mvs_seed.v1"
MEDIUM_ARMS = frozenset(
    {"04a_plane_medium_vision", "04b_plane_medium_gt_upperbound"}
)


@dataclass(frozen=True)
class PlaneGuidedInitConfig:
    """Prelocked deterministic sampling and nearest-neighbour controls."""

    stride_px: int
    grid_offset_px: int
    knn: int
    tolerance_m: float
    min_coverage: float
    query_chunk_size: int

    def __post_init__(self) -> None:
        if isinstance(self.stride_px, bool) or self.stride_px < 1:
            raise ValueError("stride_px must be an integer >=1")
        if (
            isinstance(self.grid_offset_px, bool)
            or self.grid_offset_px < 0
            or self.grid_offset_px >= self.stride_px
        ):
            raise ValueError("grid_offset_px must be in [0,stride_px)")
        if isinstance(self.knn, bool) or not 1 <= self.knn <= 64:
            raise ValueError("knn must be an integer in [1,64]")
        if not math.isfinite(self.tolerance_m) or self.tolerance_m <= 0.0:
            raise ValueError("tolerance_m must be finite and >0")
        if not math.isfinite(self.min_coverage) or not 0.0 < self.min_coverage <= 1.0:
            raise ValueError("min_coverage must be finite and in (0,1]")
        if isinstance(self.query_chunk_size, bool) or self.query_chunk_size < 1:
            raise ValueError("query_chunk_size must be an integer >=1")

    def as_dict(self) -> dict[str, Any]:
        return {
            "stride_px": int(self.stride_px),
            "grid_offset_px": int(self.grid_offset_px),
            "knn": int(self.knn),
            "tolerance_m": float(self.tolerance_m),
            "min_coverage": float(self.min_coverage),
            "query_chunk_size": int(self.query_chunk_size),
        }


@dataclass(frozen=True)
class ViewEvidence:
    xyz_world: np.ndarray
    normals_world_up: np.ndarray
    plane_mask_pixels: int
    joint_valid_pixels: int


@dataclass(frozen=True)
class NeighborAssignment:
    normals_world_up: np.ndarray
    matched_mask: np.ndarray
    zero_sum_fallback_count: int


@dataclass(frozen=True)
class PlaneGuidedInitialization:
    normals_world_up: np.ndarray
    matched_mask: np.ndarray
    audit: dict[str, Any]


def _canonical_json_bytes(payload: Any) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _json_sha256(payload: Any) -> str:
    return hashlib.sha256(_canonical_json_bytes(payload)).hexdigest()


def _file_sha256(path: Path, block_size: int = 1 << 20) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(block_size), b""):
            digest.update(block)
    return digest.hexdigest()


def _array_sha256(value: np.ndarray, dtype: str) -> str:
    array = np.ascontiguousarray(np.asarray(value, dtype=np.dtype(dtype)))
    digest = hashlib.sha256()
    digest.update(_canonical_json_bytes({"shape": list(array.shape), "dtype": dtype}))
    digest.update(array.tobytes(order="C"))
    return digest.hexdigest()


def _coerce_bool_image(value: np.ndarray, shape: tuple[int, int], name: str) -> np.ndarray:
    array = np.asarray(value)
    if array.shape != shape or array.dtype != np.bool_:
        raise ValueError(f"{name} must be bool with shape {shape}, got {array.shape}/{array.dtype}")
    return np.ascontiguousarray(array)


def _normal_summary(normals: np.ndarray) -> dict[str, Any]:
    value = np.asarray(normals, dtype=np.float64)
    if value.ndim != 2 or value.shape[1] != 3 or len(value) == 0:
        return {
            "count": 0,
            "mean_xyz": None,
            "z_min": None,
            "z_median": None,
            "angle_to_positive_z_deg_p50": None,
            "angle_to_positive_z_deg_p95": None,
            "angle_to_positive_z_deg_max": None,
        }
    angles = np.degrees(np.arccos(np.clip(value[:, 2], -1.0, 1.0)))
    return {
        "count": int(len(value)),
        "mean_xyz": [float(component) for component in value.mean(axis=0)],
        "z_min": float(value[:, 2].min()),
        "z_median": float(np.median(value[:, 2])),
        "angle_to_positive_z_deg_p50": float(np.percentile(angles, 50.0)),
        "angle_to_positive_z_deg_p95": float(np.percentile(angles, 95.0)),
        "angle_to_positive_z_deg_max": float(angles.max()),
    }


def sample_masked_mvs_view(
    *,
    depth: np.ndarray,
    depth_valid: np.ndarray,
    normals_world: np.ndarray,
    normal_valid: np.ndarray,
    plane_region_mask: np.ndarray,
    intrinsics: np.ndarray,
    rotation_world_to_camera: np.ndarray,
    translation_world_to_camera: np.ndarray,
    stride_px: int,
    grid_offset_px: int,
) -> ViewEvidence:
    """Sample one fixed view and back-project its MVS evidence to world space."""

    depth = np.asarray(depth, dtype=np.float64)
    if depth.ndim != 2:
        raise ValueError("depth must have shape (H,W)")
    shape = (int(depth.shape[0]), int(depth.shape[1]))
    depth_valid = _coerce_bool_image(depth_valid, shape, "depth_valid")
    normal_valid = _coerce_bool_image(normal_valid, shape, "normal_valid")
    plane_region_mask = _coerce_bool_image(
        plane_region_mask, shape, "plane_region_mask"
    )
    normals = np.asarray(normals_world, dtype=np.float64)
    if normals.shape != (*shape, 3):
        raise ValueError(f"normals_world must have shape {(*shape, 3)}")

    K = np.asarray(intrinsics, dtype=np.float64)
    R = np.asarray(rotation_world_to_camera, dtype=np.float64)
    t = np.asarray(translation_world_to_camera, dtype=np.float64).reshape(-1)
    if K.shape != (3, 3) or R.shape != (3, 3) or t.shape != (3,):
        raise ValueError("K/R/t must have shapes (3,3)/(3,3)/(3,)")
    if not np.isfinite(K).all() or not np.isfinite(R).all() or not np.isfinite(t).all():
        raise ValueError("K/R/t must be finite")
    if stride_px < 1 or not 0 <= grid_offset_px < stride_px:
        raise ValueError("invalid deterministic sampling grid")

    normal_norm = np.linalg.norm(normals, axis=-1)
    joint = (
        plane_region_mask
        & depth_valid
        & normal_valid
        & np.isfinite(depth)
        & (depth > 0.0)
        & np.isfinite(normals).all(axis=-1)
        & (normal_norm > 1.0e-8)
    )
    # ``np.nonzero`` is row-major and avoids materializing two full int64 image
    # grids.  The fixed offset filter preserves that deterministic order.
    joint_y, joint_x = np.nonzero(joint)
    on_grid = (
        ((joint_y - int(grid_offset_px)) % int(stride_px) == 0)
        & ((joint_x - int(grid_offset_px)) % int(stride_px) == 0)
    )
    selected_y = joint_y[on_grid]
    selected_x = joint_x[on_grid]
    if len(selected_y) == 0:
        return ViewEvidence(
            xyz_world=np.empty((0, 3), dtype=np.float32),
            normals_world_up=np.empty((0, 3), dtype=np.float32),
            plane_mask_pixels=int(plane_region_mask.sum()),
            joint_valid_pixels=int(joint.sum()),
        )

    pixels = np.stack(
        (
            selected_x.astype(np.float64),
            selected_y.astype(np.float64),
            np.ones(len(selected_y), dtype=np.float64),
        ),
        axis=1,
    )
    rays = pixels @ np.linalg.inv(K).T
    xyz_camera = rays * depth[selected_y, selected_x, None]
    xyz_world = (xyz_camera - t[None, :]) @ R

    normal = normals[selected_y, selected_x]
    normal = normal / np.linalg.norm(normal, axis=1, keepdims=True)
    normal[normal[:, 2] < 0.0] *= -1.0
    if not np.isfinite(xyz_world).all() or not np.isfinite(normal).all():
        raise RuntimeError("non-finite sampled MVS evidence escaped the validity gate")
    return ViewEvidence(
        xyz_world=np.ascontiguousarray(xyz_world, dtype=np.float32),
        normals_world_up=np.ascontiguousarray(normal, dtype=np.float32),
        plane_mask_pixels=int(plane_region_mask.sum()),
        joint_valid_pixels=int(joint.sum()),
    )


def assign_seed_normals_knn(
    seed_xyz: np.ndarray,
    evidence_xyz: np.ndarray,
    evidence_normals_world_up: np.ndarray,
    *,
    knn: int,
    tolerance_m: float,
    query_chunk_size: int,
) -> NeighborAssignment:
    """Assign an arithmetic mean of up to ``knn`` nearby evidence normals."""

    seeds = np.ascontiguousarray(np.asarray(seed_xyz, dtype=np.float64))
    evidence = np.ascontiguousarray(np.asarray(evidence_xyz, dtype=np.float64))
    normals = np.ascontiguousarray(
        np.asarray(evidence_normals_world_up, dtype=np.float64)
    )
    if seeds.ndim != 2 or seeds.shape[1] != 3 or len(seeds) == 0:
        raise ValueError("seed_xyz must be a nonempty (N,3) array")
    if evidence.ndim != 2 or evidence.shape[1] != 3 or len(evidence) == 0:
        raise ValueError("evidence_xyz must be a nonempty (M,3) array")
    if normals.shape != evidence.shape:
        raise ValueError("evidence normals must have the same shape as evidence_xyz")
    if not np.isfinite(seeds).all() or not np.isfinite(evidence).all():
        raise ValueError("seed and evidence xyz must be finite")
    if not np.isfinite(normals).all():
        raise ValueError("evidence normals must be finite")
    normal_norm = np.linalg.norm(normals, axis=1)
    if np.any(normal_norm <= 1.0e-8):
        raise ValueError("evidence normals must be nonzero")
    normals = normals / normal_norm[:, None]
    if np.any(normals[:, 2] < -1.0e-7):
        raise ValueError("evidence normals must be in the +Z hemisphere")
    if isinstance(knn, bool) or not 1 <= knn <= 64:
        raise ValueError("knn must be in [1,64]")
    if not math.isfinite(tolerance_m) or tolerance_m <= 0.0:
        raise ValueError("tolerance_m must be finite and >0")
    if isinstance(query_chunk_size, bool) or query_chunk_size < 1:
        raise ValueError("query_chunk_size must be >=1")

    assigned = np.zeros((len(seeds), 3), dtype=np.float64)
    assigned[:, 2] = 1.0
    matched = np.zeros(len(seeds), dtype=np.bool_)
    zero_sum_fallback_count = 0
    query_k = min(int(knn), len(evidence))
    tree = cKDTree(evidence, compact_nodes=True, balanced_tree=True)
    for start in range(0, len(seeds), int(query_chunk_size)):
        stop = min(start + int(query_chunk_size), len(seeds))
        distances, indices = tree.query(
            seeds[start:stop],
            k=query_k,
            distance_upper_bound=float(tolerance_m),
            workers=1,
        )
        if query_k == 1:
            distances = distances[:, None]
            indices = indices[:, None]
        valid = (
            np.isfinite(distances)
            & (distances <= float(tolerance_m))
            & (indices < len(evidence))
        )
        safe_indices = np.where(valid, indices, 0)
        candidate = normals[safe_indices]
        sums = (candidate * valid[..., None]).sum(axis=1)
        counts = valid.sum(axis=1)
        chunk_matched = counts > 0
        sum_norm = np.linalg.norm(sums, axis=1)
        nonzero = chunk_matched & (sum_norm > 1.0e-12)
        assigned_chunk = assigned[start:stop]
        assigned_chunk[nonzero] = sums[nonzero] / sum_norm[nonzero, None]

        zero_sum = chunk_matched & ~nonzero
        if bool(zero_sum.any()):
            # ``tree.query`` orders by distance.  Falling back to its first
            # qualifying neighbour keeps exact-horizontal cancellation finite
            # without adding randomness.
            first = np.argmax(valid[zero_sum], axis=1)
            rows = safe_indices[zero_sum, first]
            assigned_chunk[zero_sum] = normals[rows]
            zero_sum_fallback_count += int(zero_sum.sum())
        matched[start:stop] = chunk_matched

    # Numerical averaging can produce a tiny negative z at the equator.
    assigned[assigned[:, 2] < 0.0] *= -1.0
    return NeighborAssignment(
        normals_world_up=np.ascontiguousarray(assigned, dtype=np.float32),
        matched_mask=matched,
        zero_sum_fallback_count=zero_sum_fallback_count,
    )


def build_plane_guided_initialization(
    *,
    dataset: Any,
    training_view_indices: Sequence[int],
    mvs_seed_xyz: np.ndarray,
    plane_mask_binding: Any,
    pilot_arm: str,
    config: PlaneGuidedInitConfig,
) -> PlaneGuidedInitialization:
    """Build and audit the start-gate initialization without touching a model."""

    if pilot_arm not in MEDIUM_ARMS:
        raise ValueError(f"plane-guided initialization is restricted to {sorted(MEDIUM_ARMS)}")
    seed_xyz = np.ascontiguousarray(np.asarray(mvs_seed_xyz, dtype=np.float32))
    if seed_xyz.ndim != 2 or seed_xyz.shape[1] != 3 or len(seed_xyz) == 0:
        raise ValueError("mvs_seed_xyz must be a nonempty (N,3) array")
    if not np.isfinite(seed_xyz).all():
        raise ValueError("mvs_seed_xyz must be finite")

    indices = [int(index) for index in training_view_indices]
    if not indices or len(indices) != len(set(indices)):
        raise ValueError("training_view_indices must be nonempty and unique")
    if any(index < 0 or index >= len(dataset.frames) for index in indices):
        raise ValueError("training_view_indices contains an out-of-range index")
    indices.sort(key=lambda index: (dataset.frames[index].name, index))

    evidence_xyz: list[np.ndarray] = []
    evidence_normal: list[np.ndarray] = []
    view_rows: list[dict[str, Any]] = []
    for index in indices:
        frame = dataset.frames[index]
        height, width = dataset.image_size(index)
        depth, depth_valid = dataset._load_depth(frame, height, width)
        normals, normal_valid = dataset._load_normal(frame, height, width)
        if depth is None or depth_valid is None or normals is None or normal_valid is None:
            raise RuntimeError(f"training view {frame.name!r} is missing MVS depth/normal")
        plane_mask = plane_mask_binding.load(frame, (height, width))
        sampled = sample_masked_mvs_view(
            depth=depth,
            depth_valid=np.asarray(depth_valid),
            normals_world=normals,
            normal_valid=np.asarray(normal_valid),
            plane_region_mask=np.asarray(plane_mask),
            intrinsics=dataset.scaled_K(index),
            rotation_world_to_camera=frame.R,
            translation_world_to_camera=frame.t,
            stride_px=config.stride_px,
            grid_offset_px=config.grid_offset_px,
        )
        evidence_xyz.append(sampled.xyz_world)
        evidence_normal.append(sampled.normals_world_up)
        view_rows.append(
            {
                "view_id": frame.name,
                "plane_mask_pixels": sampled.plane_mask_pixels,
                "joint_valid_pixels": sampled.joint_valid_pixels,
                "sampled_evidence_count": int(len(sampled.xyz_world)),
                "empty_plane_mask": sampled.plane_mask_pixels == 0,
            }
        )

    all_xyz = np.ascontiguousarray(np.concatenate(evidence_xyz, axis=0), dtype=np.float32)
    all_normal = np.ascontiguousarray(
        np.concatenate(evidence_normal, axis=0), dtype=np.float32
    )
    if len(all_xyz) == 0:
        raise RuntimeError(
            "plane-guided initialization has zero aggregate training-view MVS evidence"
        )
    assignment = assign_seed_normals_knn(
        seed_xyz,
        all_xyz,
        all_normal,
        knn=config.knn,
        tolerance_m=config.tolerance_m,
        query_chunk_size=config.query_chunk_size,
    )
    matched_count = int(assignment.matched_mask.sum())
    matched_fraction = float(matched_count / len(seed_xyz))
    if matched_count == 0:
        raise RuntimeError(
            "plane-guided initialization matched zero MVS seed points within tolerance"
        )
    if matched_fraction < config.min_coverage:
        raise RuntimeError(
            "plane-guided initialization coverage below prelocked minimum: "
            f"{matched_fraction:.9f} < {config.min_coverage:.9f}"
        )

    binding_audit = dict(plane_mask_binding.audit)
    manifest_path = Path(binding_audit["manifest_path"]).resolve()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest_sha256 = _file_sha256(manifest_path)
    if manifest_sha256 != binding_audit.get("manifest_sha256"):
        raise RuntimeError("plane mask manifest SHA changed after dataset preflight")

    parameters = config.as_dict()
    algorithm_contract = {
        "algorithm": ALGORITHM,
        "parameters": parameters,
        "camera_policy": "fixed_colmap_training_views_only",
        "depth_source": "image_derived_mvs_depth",
        "normal_source": "image_derived_mvs_normal_world_frame",
        "sample_rule": "plane_mask AND depth_valid AND normal_valid on fixed row_major_grid",
        "backprojection": "pixel_homogeneous_times_camera_z_then_inverse_fixed_w2c",
        "normal_sign": "flip_to_positive_z_hemisphere",
        "neighbor_aggregation": "unweighted_mean_of_up_to_k_within_tolerance",
        "unmatched_normal": [0.0, 0.0, 1.0],
        "query_engine": "scipy.spatial.cKDTree_workers_1_chunked",
    }
    algorithm_sha256 = _json_sha256(algorithm_contract)
    seed_sha256 = _array_sha256(seed_xyz, "<f4")
    evidence_xyz_sha256 = _array_sha256(all_xyz, "<f4")
    evidence_normal_sha256 = _array_sha256(all_normal, "<f4")
    assigned_sha256 = _array_sha256(assignment.normals_world_up, "<f4")
    input_binding = {
        "algorithm_sha256": algorithm_sha256,
        "plane_mask_manifest_sha256": manifest_sha256,
        "plane_mask_inventory_sha256": binding_audit.get("inventory_sha256"),
        "training_view_ids": [row["view_id"] for row in view_rows],
        "mvs_seed_xyz_sha256": seed_sha256,
        "evidence_xyz_sha256": evidence_xyz_sha256,
        "evidence_normals_world_up_sha256": evidence_normal_sha256,
        "assigned_normals_world_up_sha256": assigned_sha256,
    }
    audit = {
        "schema": AUDIT_SCHEMA,
        "pilot_arm": pilot_arm,
        "passed": True,
        "evaluated_before_optimizer_creation": True,
        "algorithm": algorithm_contract,
        "algorithm_sha256": algorithm_sha256,
        "binding_sha256": _json_sha256(input_binding),
        "source": {
            "manifest_path": str(manifest_path),
            "manifest_sha256": manifest_sha256,
            "inventory_sha256": binding_audit.get("inventory_sha256"),
            "purpose": binding_audit.get("purpose"),
            "mask_source": binding_audit.get("source"),
            "source_disclosure": manifest.get("source_disclosure"),
            "manifest_view_count": int(binding_audit.get("view_count", 0)),
            "training_view_count": len(view_rows),
            "training_nonempty_mask_view_count": sum(
                not row["empty_plane_mask"] for row in view_rows
            ),
            "training_empty_mask_view_count": sum(
                row["empty_plane_mask"] for row in view_rows
            ),
            "training_evidence_view_count": sum(
                row["sampled_evidence_count"] > 0 for row in view_rows
            ),
        },
        "parameters": parameters,
        "counts": {
            "mvs_seed_count": int(len(seed_xyz)),
            "evidence_sample_count": int(len(all_xyz)),
            "matched_seed_count": matched_count,
            "unmatched_seed_count": int(len(seed_xyz) - matched_count),
            "matched_seed_fraction": matched_fraction,
            "zero_sum_fallback_count": assignment.zero_sum_fallback_count,
        },
        "hashes": {
            "mvs_seed_xyz_sha256": seed_sha256,
            "evidence_xyz_sha256": evidence_xyz_sha256,
            "evidence_normals_world_up_sha256": evidence_normal_sha256,
            "assigned_normals_world_up_sha256": assigned_sha256,
        },
        "normal_stats": {
            "sampled_evidence": _normal_summary(all_normal),
            "matched_assigned": _normal_summary(
                assignment.normals_world_up[assignment.matched_mask]
            ),
            "all_assigned_including_unmatched_positive_z": _normal_summary(
                assignment.normals_world_up
            ),
        },
        "views": view_rows,
    }
    return PlaneGuidedInitialization(
        normals_world_up=assignment.normals_world_up,
        matched_mask=assignment.matched_mask,
        audit=audit,
    )


def verify_resume_initialization_audit(
    previous_audit_path: str | Path,
    current: PlaneGuidedInitialization,
) -> dict[str, Any]:
    """Validate that a resume binds to the exact fresh-start initializer input."""

    path = Path(previous_audit_path)
    if not path.is_file():
        raise RuntimeError(
            "resume requires the fresh-start plane-guided initialization audit: "
            f"{path}"
        )
    try:
        previous = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"cannot read prior plane-guided initialization audit: {exc}") from exc
    if not isinstance(previous, dict) or previous.get("schema") != AUDIT_SCHEMA:
        raise RuntimeError("prior plane-guided initialization audit schema mismatch")
    checks = {
        "pilot_arm": (previous.get("pilot_arm"), current.audit["pilot_arm"]),
        "algorithm_sha256": (
            previous.get("algorithm_sha256"), current.audit["algorithm_sha256"]
        ),
        "binding_sha256": (
            previous.get("binding_sha256"), current.audit["binding_sha256"]
        ),
        "assigned_normals_world_up_sha256": (
            (previous.get("hashes") or {}).get("assigned_normals_world_up_sha256"),
            current.audit["hashes"]["assigned_normals_world_up_sha256"],
        ),
    }
    mismatched = [name for name, (old, new) in checks.items() if old != new]
    if mismatched:
        raise RuntimeError(
            "resume plane-guided initialization audit binding mismatch: "
            + ", ".join(mismatched)
        )
    return {
        "schema": RESUME_AUDIT_SCHEMA,
        "passed": True,
        "checkpoint_quaternions_take_precedence": True,
        "initializer_reapplied": False,
        "fresh_audit_path": str(path.resolve()),
        "fresh_audit_sha256": _file_sha256(path),
        "algorithm_sha256": current.audit["algorithm_sha256"],
        "binding_sha256": current.audit["binding_sha256"],
        "assigned_normals_world_up_sha256": current.audit["hashes"][
            "assigned_normals_world_up_sha256"
        ],
    }
