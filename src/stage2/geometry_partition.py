"""Geometry-only building partitions for first-wave structure grouping.

The quality-axis pilot deliberately disables semantic supervision.  Reusing
``sem_logits.argmax()`` for :math:`L_structure` grouping would therefore turn
random, untrained class logits into a hidden grouping input.  This module
instead assigns Gaussian centres to the approved footprint XY polygons.

Only XY is consumed.  The input GeoJSON's Z (if any), LoD2 roof faces, roof
types, and semantic properties are neither parsed nor returned.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

import numpy as np
import torch
from shapely import contains_xy, force_2d, make_valid
from shapely.geometry import GeometryCollection, MultiPolygon, Polygon, shape
from shapely.ops import unary_union


CRS = "EPSG:25832"


class GeometryPartitionError(ValueError):
    """The footprint partition contract is incomplete or ambiguous."""


@dataclass(frozen=True)
class FootprintPartition:
    """One ordered XY partition; ``partition_id`` is positive and stable."""

    partition_id: int
    building_id: str
    geometry: Polygon | MultiPolygon


def _full_id(value: str) -> str:
    text = str(value)
    return text if text.startswith("DEBY_LOD2_") else f"DEBY_LOD2_{text}"


def _polygonal(value: object) -> list[Polygon]:
    if value is None or getattr(value, "is_empty", True):
        return []
    if isinstance(value, Polygon):
        return [value]
    if isinstance(value, MultiPolygon):
        return list(value.geoms)
    if isinstance(value, GeometryCollection):
        output: list[Polygon] = []
        for part in value.geoms:
            output.extend(_polygonal(part))
        return output
    return []


def load_xy_partitions(
    geojson_path: str | Path,
    building_ids: Sequence[str],
) -> tuple[FootprintPartition, ...]:
    """Load only requested footprint XY, preserving caller order.

    Duplicate GeoJSON features for one building are unioned.  Overlap ownership
    later follows this same explicit order, so a point can never receive two
    partition IDs.
    """

    requested = [_full_id(value) for value in building_ids]
    if not requested or len(requested) != len(set(requested)):
        raise GeometryPartitionError("building_ids must be non-empty and unique")

    payload = json.loads(Path(geojson_path).read_text(encoding="utf-8"))
    crs = str((payload.get("crs") or {}).get("properties", {}).get("name", ""))
    if "25832" not in crs:
        raise GeometryPartitionError(f"footprint CRS is not {CRS}: {crs!r}")

    wanted = set(requested)
    pieces: dict[str, list[Polygon]] = {value: [] for value in requested}
    for feature in payload.get("features", []):
        props = feature.get("properties") or {}
        building_id = _full_id(str(props.get("building_id", "")))
        if building_id not in wanted:
            continue
        geometry_payload = feature.get("geometry")
        if not geometry_payload:
            continue
        # Force the geometry to 2D immediately so even a future 3D GeoJSON
        # cannot carry height through this boundary.  No feature property other
        # than the identifier is read.
        geometry = make_valid(force_2d(shape(geometry_payload)))
        pieces[building_id].extend(_polygonal(geometry))

    missing = [value for value in requested if not pieces[value]]
    if missing:
        raise GeometryPartitionError(f"missing polygonal footprints: {missing}")

    output: list[FootprintPartition] = []
    for partition_id, building_id in enumerate(requested, start=1):
        merged = make_valid(unary_union(pieces[building_id]))
        polygons = _polygonal(merged)
        if not polygons:
            raise GeometryPartitionError(f"empty footprint after union: {building_id}")
        polygonal = polygons[0] if len(polygons) == 1 else MultiPolygon(polygons)
        output.append(
            FootprintPartition(
                partition_id=partition_id,
                building_id=building_id,
                geometry=polygonal,
            )
        )
    return tuple(output)


def assign_partition_ids(
    centers_local: torch.Tensor,
    partitions: Iterable[FootprintPartition],
    *,
    world_offset_xy: Sequence[float],
    boundary_tolerance_m: float = 1.0e-7,
) -> torch.Tensor:
    """Assign centres to ordered footprints using XY only.

    ``0`` means outside every selected footprint.  If footprints overlap, the
    earlier caller-supplied building wins deterministically.  A tiny metric
    buffer includes points lying numerically on polygon boundaries without
    materially enlarging the training region.
    """

    if centers_local.ndim != 2 or centers_local.shape[1] != 3:
        raise GeometryPartitionError("centers_local must have shape (N,3)")
    if len(world_offset_xy) < 2:
        raise GeometryPartitionError("world_offset_xy must contain X and Y")
    if boundary_tolerance_m < 0:
        raise GeometryPartitionError("boundary_tolerance_m must be non-negative")

    ordered = tuple(partitions)
    ids = [row.partition_id for row in ordered]
    if ids != list(range(1, len(ordered) + 1)):
        raise GeometryPartitionError("partition IDs must be contiguous in caller order")

    device = centers_local.device
    xy = centers_local.detach().cpu().numpy().astype(np.float64, copy=False)[:, :2]
    xy = xy + np.asarray(world_offset_xy[:2], dtype=np.float64)[None, :]
    assigned = np.zeros(len(xy), dtype=np.int64)
    finite = np.isfinite(xy).all(axis=1)
    for row in ordered:
        geometry = row.geometry
        if boundary_tolerance_m:
            geometry = geometry.buffer(float(boundary_tolerance_m))
        inside = np.zeros(len(xy), dtype=bool)
        valid_indices = np.flatnonzero(finite & (assigned == 0))
        if len(valid_indices):
            inside[valid_indices] = contains_xy(
                geometry,
                xy[valid_indices, 0],
                xy[valid_indices, 1],
            )
        assigned[inside & (assigned == 0)] = int(row.partition_id)
    return torch.from_numpy(assigned).to(device=device, dtype=torch.int64)


def partition_logits(partition_ids: torch.Tensor, n_partitions: int) -> torch.Tensor:
    """Encode fixed partition IDs for existing grouping code, without semantics.

    Column 0 is the outside/background partition.  The returned values are
    constants with no gradient and are used only by discrete grouping.
    """

    if partition_ids.ndim != 1 or partition_ids.dtype != torch.int64:
        raise GeometryPartitionError("partition_ids must be an int64 vector")
    if n_partitions < 1:
        raise GeometryPartitionError("n_partitions must be positive")
    if partition_ids.numel() and (
        int(partition_ids.min().item()) < 0
        or int(partition_ids.max().item()) > int(n_partitions)
    ):
        raise GeometryPartitionError("partition ID lies outside the declared range")
    logits = torch.zeros(
        (partition_ids.shape[0], int(n_partitions) + 1),
        dtype=torch.float32,
        device=partition_ids.device,
    )
    logits.scatter_(1, partition_ids[:, None], 1.0)
    return logits
