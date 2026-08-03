"""Outcome-free C3 checkpoint to Roofer point-evidence adapter.

This module deliberately stops before file publication, component association,
Roofer, validation, or evaluation.  It consumes only the arrays already stored
in a C3 ``final.pt`` checkpoint and never regroups primitives.  No building ID,
footprint, reference geometry, UAS, ALS, LoD1, or LoD2 input is accepted.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

import numpy as np
import torch


LOCAL_SHIFT_XYZ = (690_953.0, 5_336_071.0, 604.0)
AOI_BBOX_EPSG25832 = (690_791.74, 5_335_864.05, 691_154.65, 5_336_353.85)
GRID_CELL_M = 1.0
CRS = "EPSG:25832"


class C3CheckpointAdapterError(RuntimeError):
    """The stored checkpoint or deterministic materialization is invalid."""


@dataclass(frozen=True)
class C3CheckpointArrays:
    """Validated, read-only arrays copied from one stored C3 final checkpoint."""

    means: np.ndarray
    sem_logits: np.ndarray
    opacities_raw: np.ndarray
    group_ids: np.ndarray
    rep_normals: np.ndarray
    rep_d: np.ndarray
    iteration: int | None


@dataclass(frozen=True)
class ComponentPoint:
    """One deterministic point row, structurally compatible with component code."""

    x: float
    y: float
    z: float
    classification: int
    ix: int
    iy: int
    source_primitive_index: int
    stage2_group_id: int
    semantic_class: int
    selection_rule: str


@dataclass(frozen=True)
class SurfaceGroupLineage:
    """Stored Stage-2 group identity and its contribution to materialization."""

    group_id: int
    semantic_class: int
    representative_normal: tuple[float, float, float]
    representative_d: float
    stored_member_count: int
    aoi_member_count: int
    selected_point_count: int


@dataclass(frozen=True)
class MaterializedC3Evidence:
    """In-memory class-2/6 evidence; this object carries no execution authority."""

    points: tuple[ComponentPoint, ...]
    groups: tuple[SurfaceGroupLineage, ...]
    lineage_stats: Mapping[str, Any]
    scientific_verdict: None = None

    def xyz_class_rows(self) -> tuple[tuple[float, float, float, int], ...]:
        """Return compact rows for an in-memory LAS/Roofer adapter consumer."""

        return tuple((p.x, p.y, p.z, p.classification) for p in self.points)


def _numpy(value: Any, label: str) -> np.ndarray:
    if isinstance(value, torch.Tensor):
        value = value.detach().to(device="cpu").numpy()
    try:
        array = np.asarray(value)
    except Exception as error:  # pragma: no cover - defensive boundary
        raise C3CheckpointAdapterError(f"{label} is not array-like") from error
    if array.dtype.hasobject:
        raise C3CheckpointAdapterError(f"{label} has object dtype")
    return array


def _readonly_copy(value: np.ndarray, dtype: np.dtype[Any]) -> np.ndarray:
    copied = np.ascontiguousarray(value, dtype=dtype).copy()
    copied.setflags(write=False)
    return copied


def validate_c3_checkpoint_mapping(checkpoint: Mapping[str, Any]) -> C3CheckpointArrays:
    """Validate and copy the exact stored arrays without invoking grouping.

    The accepted layout is the inference ``final.pt`` written by
    :mod:`src.stage2.train`: model parameters live under ``state_dict`` and the
    three final grouping arrays live at checkpoint top level.
    """

    if not isinstance(checkpoint, Mapping):
        raise C3CheckpointAdapterError("checkpoint must be a mapping")
    state = checkpoint.get("state_dict")
    if not isinstance(state, Mapping):
        raise C3CheckpointAdapterError("checkpoint state_dict is missing or invalid")

    missing_state = sorted({"means", "sem_logits", "opacities_raw"} - set(state))
    missing_groups = sorted(
        {"stage2_group_ids", "stage2_rep_normals", "stage2_rep_d"} - set(checkpoint)
    )
    if missing_state or missing_groups:
        raise C3CheckpointAdapterError(
            f"required stored arrays are missing: state={missing_state}, groups={missing_groups}"
        )

    means_raw = _numpy(state["means"], "state_dict.means")
    logits_raw = _numpy(state["sem_logits"], "state_dict.sem_logits")
    opacity_raw = _numpy(state["opacities_raw"], "state_dict.opacities_raw")
    gids_raw = _numpy(checkpoint["stage2_group_ids"], "stage2_group_ids")
    normals_raw = _numpy(checkpoint["stage2_rep_normals"], "stage2_rep_normals")
    d_raw = _numpy(checkpoint["stage2_rep_d"], "stage2_rep_d")

    if means_raw.ndim != 2 or means_raw.shape[1] != 3 or means_raw.shape[0] == 0:
        raise C3CheckpointAdapterError("means must have non-empty shape (N,3)")
    count = int(means_raw.shape[0])
    if logits_raw.shape != (count, 4):
        raise C3CheckpointAdapterError("sem_logits must have exact shape (N,4)")
    if opacity_raw.shape not in ((count,), (count, 1)):
        raise C3CheckpointAdapterError("opacities_raw must have shape (N,) or (N,1)")
    if gids_raw.shape != (count,) or gids_raw.dtype.kind not in "iu" or gids_raw.dtype.kind == "b":
        raise C3CheckpointAdapterError("stage2_group_ids must be an integer vector of length N")
    if normals_raw.ndim != 2 or normals_raw.shape[1] != 3 or normals_raw.shape[0] == 0:
        raise C3CheckpointAdapterError("stage2_rep_normals must have non-empty shape (G,3)")
    group_count = int(normals_raw.shape[0])
    if d_raw.shape != (group_count,):
        raise C3CheckpointAdapterError("stage2_rep_d must have shape (G,)")
    for label, value in (
        ("means", means_raw),
        ("sem_logits", logits_raw),
        ("opacities_raw", opacity_raw),
        ("stage2_rep_normals", normals_raw),
        ("stage2_rep_d", d_raw),
    ):
        if value.dtype.kind not in "fiu" or not np.isfinite(value).all():
            raise C3CheckpointAdapterError(f"{label} must contain finite numeric values")

    means = _readonly_copy(means_raw, np.dtype(np.float64))
    sem_logits = _readonly_copy(logits_raw, np.dtype(np.float64))
    opacities_raw = _readonly_copy(opacity_raw.reshape(count), np.dtype(np.float64))
    group_ids = _readonly_copy(gids_raw, np.dtype(np.int64))
    rep_normals = _readonly_copy(normals_raw, np.dtype(np.float64))
    rep_d = _readonly_copy(d_raw, np.dtype(np.float64))

    if int(group_ids.min()) < -1 or int(group_ids.max()) >= group_count:
        raise C3CheckpointAdapterError("stage2_group_ids contain an invalid stored group index")
    used_groups = np.unique(group_ids[group_ids >= 0])
    if not np.array_equal(used_groups, np.arange(group_count, dtype=np.int64)):
        raise C3CheckpointAdapterError("stored Stage-2 group IDs are not contiguous and fully used")
    normal_norms = np.linalg.norm(rep_normals, axis=1)
    if np.any(normal_norms <= 1.0e-12) or not np.allclose(
        normal_norms, 1.0, rtol=1.0e-4, atol=1.0e-4
    ):
        raise C3CheckpointAdapterError("stored representative normals are not unit vectors")

    labels = np.argmax(sem_logits, axis=1)
    for group_id in range(group_count):
        member_labels = np.unique(labels[group_ids == group_id])
        if member_labels.size != 1:
            raise C3CheckpointAdapterError(
                f"stored Stage-2 group {group_id} crosses semantic classes"
            )

    n_prim = checkpoint.get("n_prim")
    if n_prim is not None and (isinstance(n_prim, bool) or int(n_prim) != count):
        raise C3CheckpointAdapterError("checkpoint n_prim differs from stored array length")
    iteration_raw = checkpoint.get("it")
    iteration: int | None = None
    if iteration_raw is not None:
        if isinstance(iteration_raw, bool):
            raise C3CheckpointAdapterError("checkpoint iteration is invalid")
        iteration = int(iteration_raw)
        if iteration < 0 or iteration != iteration_raw:
            raise C3CheckpointAdapterError("checkpoint iteration is invalid")

    return C3CheckpointArrays(
        means=means,
        sem_logits=sem_logits,
        opacities_raw=opacities_raw,
        group_ids=group_ids,
        rep_normals=rep_normals,
        rep_d=rep_d,
        iteration=iteration,
    )


def load_c3_checkpoint(path: str | Path) -> C3CheckpointArrays:
    """Load one regular checkpoint file on CPU and validate its stored arrays."""

    checkpoint_path = Path(path)
    if checkpoint_path.is_symlink() or not checkpoint_path.is_file():
        raise C3CheckpointAdapterError("checkpoint must be a regular non-symlink file")
    try:
        checkpoint = torch.load(
            checkpoint_path,
            map_location="cpu",
            weights_only=True,
        )
    except Exception as error:
        raise C3CheckpointAdapterError("cannot deserialize checkpoint safely") from error
    return validate_c3_checkpoint_mapping(checkpoint)


def _cell_index(x: float, y: float) -> tuple[int, int]:
    min_x, min_y = AOI_BBOX_EPSG25832[:2]
    return (
        int(np.floor((x - min_x) / GRID_CELL_M + 1.0e-9)),
        int(np.floor((y - min_y) / GRID_CELL_M + 1.0e-9)),
    )


def _cell_center(ix: int, iy: int) -> tuple[float, float]:
    min_x, min_y = AOI_BBOX_EPSG25832[:2]
    return (
        min_x + (ix + 0.5) * GRID_CELL_M,
        min_y + (iy + 0.5) * GRID_CELL_M,
    )


def _sigmoid(values: np.ndarray) -> np.ndarray:
    result = np.empty_like(values, dtype=np.float64)
    nonnegative = values >= 0
    result[nonnegative] = 1.0 / (1.0 + np.exp(-values[nonnegative]))
    exponent = np.exp(values[~nonnegative])
    result[~nonnegative] = exponent / (1.0 + exponent)
    return result


def _selection_rank(point: ComponentPoint) -> tuple[float | int, ...]:
    if point.classification == 6:
        # Highest building evidence wins. Exact-height ties prefer roof over
        # wall and then stable coordinates/lineage/source order.
        return (
            -point.z,
            point.semantic_class,
            point.x,
            point.y,
            point.stage2_group_id,
            point.source_primitive_index,
        )
    return (
        point.z,
        point.x,
        point.y,
        point.stage2_group_id,
        point.source_primitive_index,
    )


def materialize_component_ready_evidence(
    arrays: C3CheckpointArrays,
) -> MaterializedC3Evidence:
    """Materialize deterministic 1 m class-2/6 rows from stored G2 members.

    Building evidence is the maximum-Z roof/wall primitive in each cell;
    terrain evidence is the minimum-Z terrain primitive in each cell.  Both may
    coexist in one XY cell.  The output retains exact primitive/group lineage.
    """

    count = int(arrays.means.shape[0])
    if arrays.sem_logits.shape != (count, 4) or arrays.group_ids.shape != (count,):
        raise C3CheckpointAdapterError("validated array shapes changed before materialization")
    labels = np.argmax(arrays.sem_logits, axis=1).astype(np.int64, copy=False)
    world = arrays.means + np.asarray(LOCAL_SHIFT_XYZ, dtype=np.float64)[None, :]
    if not np.isfinite(world).all():
        raise C3CheckpointAdapterError("world-coordinate translation produced non-finite values")

    min_x, min_y, max_x, max_y = AOI_BBOX_EPSG25832
    selected: dict[tuple[int, int, int], ComponentPoint] = {}
    aoi_member_counts = np.zeros(len(arrays.rep_d), dtype=np.int64)
    mapped_aoi_candidates = 0
    mapped_outside_aoi = 0
    grouped_background = 0

    for source_index in range(count):
        group_id = int(arrays.group_ids[source_index])
        if group_id < 0:
            continue
        semantic_class = int(labels[source_index])
        if semantic_class == 0:
            grouped_background += 1
            continue
        classification = 6 if semantic_class in (1, 2) else 2
        x, y, z = (float(value) for value in world[source_index])
        if not (min_x <= x <= max_x and min_y <= y <= max_y):
            mapped_outside_aoi += 1
            continue
        ix, iy = _cell_index(x, y)
        cell_x, cell_y = _cell_center(ix, iy)
        aoi_member_counts[group_id] += 1
        mapped_aoi_candidates += 1
        point = ComponentPoint(
            x=cell_x,
            y=cell_y,
            z=z,
            classification=classification,
            ix=ix,
            iy=iy,
            source_primitive_index=source_index,
            stage2_group_id=group_id,
            semantic_class=semantic_class,
            selection_rule=("BUILDING_MAX_Z" if classification == 6 else "TERRAIN_MIN_Z"),
        )
        key = (classification, ix, iy)
        current = selected.get(key)
        if current is None or _selection_rank(point) < _selection_rank(current):
            selected[key] = point

    points = tuple(
        sorted(
            selected.values(),
            key=lambda p: (
                p.classification,
                p.iy,
                p.ix,
                p.z,
                p.stage2_group_id,
                p.source_primitive_index,
            ),
        )
    )
    selected_group_counts = np.zeros(len(arrays.rep_d), dtype=np.int64)
    for point in points:
        selected_group_counts[point.stage2_group_id] += 1

    groups: list[SurfaceGroupLineage] = []
    for group_id in range(len(arrays.rep_d)):
        member_mask = arrays.group_ids == group_id
        semantic_class = int(labels[np.flatnonzero(member_mask)[0]])
        groups.append(
            SurfaceGroupLineage(
                group_id=group_id,
                semantic_class=semantic_class,
                representative_normal=tuple(
                    float(value) for value in arrays.rep_normals[group_id]
                ),
                representative_d=float(arrays.rep_d[group_id]),
                stored_member_count=int(np.count_nonzero(member_mask)),
                aoi_member_count=int(aoi_member_counts[group_id]),
                selected_point_count=int(selected_group_counts[group_id]),
            )
        )

    output_class_counts = {
        "2": sum(point.classification == 2 for point in points),
        "6": sum(point.classification == 6 for point in points),
    }
    grouped_count = int(np.count_nonzero(arrays.group_ids >= 0))
    grouped_mask = arrays.group_ids >= 0
    grouped_opacity = _sigmoid(arrays.opacities_raw[grouped_mask])
    opacity_quantiles = {
        label: float(value)
        for label, value in zip(
            ("min", "p01", "p05", "p25", "p50", "p75", "p95", "p99", "max"),
            np.quantile(grouped_opacity, (0.0, 0.01, 0.05, 0.25, 0.5, 0.75, 0.95, 0.99, 1.0)),
        )
    }
    semantic_counts = {
        str(class_id): int(np.count_nonzero((arrays.group_ids >= 0) & (labels == class_id)))
        for class_id in range(4)
    }
    stats: dict[str, Any] = {
        "schema": "jointbuildgs.c3_checkpoint_roofer_materialization.v1",
        "checkpoint_iteration": arrays.iteration,
        "source_primitive_count": count,
        "stored_stage2_group_count": len(groups),
        "stored_grouped_primitive_count": grouped_count,
        "ungrouped_primitive_count": count - grouped_count,
        "stored_grouped_semantic_counts": semantic_counts,
        "grouped_background_dropped": grouped_background,
        "mapped_grouped_primitives_outside_aoi": mapped_outside_aoi,
        "mapped_grouped_primitives_inside_aoi_before_cell_reduction": mapped_aoi_candidates,
        "cell_reduction_dropped": mapped_aoi_candidates - len(points),
        "output_point_count": len(points),
        "output_class_counts": output_class_counts,
        "surface_eligibility": "STORED_STAGE2_GROUP_ID_GTE_ZERO",
        "semantic_to_las_class": {"0": "DROP", "1": 6, "2": 6, "3": 2},
        "building_cell_reducer": "MAX_Z",
        "terrain_cell_reducer": "MIN_Z",
        "grid_cell_m": GRID_CELL_M,
        "grid_origin_xy": list(AOI_BBOX_EPSG25832[:2]),
        "aoi_bbox_epsg25832": list(AOI_BBOX_EPSG25832),
        "crs": CRS,
        "local_to_world_add_xyz": list(LOCAL_SHIFT_XYZ),
        "stored_stage2_groups_reused_exact": True,
        "regroup_invocation_count": 0,
        "opacity_used": False,
        "opacity_threshold": None,
        "stored_grouped_opacity_quantiles_diagnostic_only": opacity_quantiles,
        "low_opacity_primitives_are_not_filtered": True,
        "gt_footprint_reference_uas_als_lod1_lod2_used": False,
        "scientific_verdict": None,
    }
    return MaterializedC3Evidence(
        points=points,
        groups=tuple(groups),
        lineage_stats=stats,
        scientific_verdict=None,
    )


__all__ = [
    "AOI_BBOX_EPSG25832",
    "CRS",
    "GRID_CELL_M",
    "LOCAL_SHIFT_XYZ",
    "C3CheckpointAdapterError",
    "C3CheckpointArrays",
    "ComponentPoint",
    "MaterializedC3Evidence",
    "SurfaceGroupLineage",
    "load_c3_checkpoint",
    "materialize_component_ready_evidence",
    "validate_c3_checkpoint_mapping",
]
