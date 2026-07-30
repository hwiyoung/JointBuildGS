#!/usr/bin/env python3
"""Build honest class-6 TIN support-boundary segments for image overlays.

The public API accepts only an XYZ point array and the three numeric filters
used by the existing fusion-W1 TIN builder.  It does not accept masks,
reference models, semantic models, or target-outline geometry.  Boundary
segments are the incidence-one edges of the filtered TIN and therefore retain
the actual Z value of every TIN vertex.  Disconnected support components remain
disconnected; no convex hull or synthetic closing edge is introduced.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from pathlib import Path
import sys
from types import MappingProxyType
from typing import Mapping

import numpy as np


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import fusion_w1_preprocess_v1_20260725 as V1  # noqa: E402


class RoofBoundaryError(RuntimeError):
    """The XYZ input or resulting filtered TIN cannot define a boundary."""


@dataclass(frozen=True)
class BoundaryComponent:
    """One edge-connected component, represented as unordered 3D segments."""

    edge_vertex_indices: np.ndarray
    segments_xyz: np.ndarray


@dataclass(frozen=True)
class RoofBoundary:
    """Filtered TIN plus its complete incidence-one support boundary."""

    tin_vertices_xyz: np.ndarray
    tin_triangle_vertex_indices: np.ndarray
    boundary_edge_vertex_indices: np.ndarray
    boundary_segments_xyz: np.ndarray
    components: tuple[BoundaryComponent, ...]
    tin_stats: Mapping[str, int | float]


def _readonly_array(values: np.ndarray, dtype: np.dtype) -> np.ndarray:
    output = np.ascontiguousarray(values, dtype=dtype).copy()
    output.setflags(write=False)
    return output


def _finite_number(name: str, value: float) -> float:
    try:
        output = float(value)
    except (TypeError, ValueError) as exc:
        raise RoofBoundaryError(f"{name} must be numeric") from exc
    if not math.isfinite(output):
        raise RoofBoundaryError(f"{name} must be finite")
    return output


def _validate_filters(
    maximum_xy_edge_m: float,
    maximum_slope_deg: float,
    minimum_xy_triangle_area_m2: float,
) -> tuple[float, float, float]:
    maximum_edge = _finite_number("maximum_xy_edge_m", maximum_xy_edge_m)
    maximum_slope = _finite_number("maximum_slope_deg", maximum_slope_deg)
    minimum_area = _finite_number(
        "minimum_xy_triangle_area_m2", minimum_xy_triangle_area_m2
    )
    if maximum_edge <= 0.0:
        raise RoofBoundaryError("maximum_xy_edge_m must be positive")
    if not 0.0 <= maximum_slope < 90.0:
        raise RoofBoundaryError("maximum_slope_deg must be in [0, 90)")
    if minimum_area <= 0.0:
        raise RoofBoundaryError("minimum_xy_triangle_area_m2 must be positive")
    return maximum_edge, maximum_slope, minimum_area


def _boundary_edges(triangles: np.ndarray) -> np.ndarray:
    faces = np.asarray(triangles, dtype=np.int64)
    if faces.ndim != 2 or faces.shape[1] != 3 or len(faces) == 0:
        raise RoofBoundaryError("filtered TIN triangles must have shape (T, 3)")
    edges = np.vstack(
        (faces[:, [0, 1]], faces[:, [1, 2]], faces[:, [2, 0]])
    )
    edges.sort(axis=1)
    unique_edges, counts = np.unique(edges, axis=0, return_counts=True)
    boundary = unique_edges[counts == 1]
    if len(boundary) == 0:
        raise RoofBoundaryError("filtered TIN has no incidence-one boundary edges")
    return boundary


def _component_edge_indices(boundary_edges: np.ndarray) -> tuple[np.ndarray, ...]:
    """Return deterministic edge-connected groups without inventing ring order."""

    by_vertex: dict[int, list[int]] = {}
    for edge_index, (first, second) in enumerate(boundary_edges):
        by_vertex.setdefault(int(first), []).append(edge_index)
        by_vertex.setdefault(int(second), []).append(edge_index)

    unvisited = set(range(len(boundary_edges)))
    groups: list[np.ndarray] = []
    while unvisited:
        start = min(unvisited)
        stack = [start]
        component: set[int] = set()
        while stack:
            edge_index = stack.pop()
            if edge_index not in unvisited:
                continue
            unvisited.remove(edge_index)
            component.add(edge_index)
            for vertex_index in boundary_edges[edge_index]:
                for neighbor in by_vertex[int(vertex_index)]:
                    if neighbor in unvisited:
                        stack.append(neighbor)
        groups.append(np.asarray(sorted(component), dtype=np.int64))

    groups.sort(
        key=lambda indices: tuple(
            int(value) for value in boundary_edges[int(indices[0])]
        )
    )
    return tuple(groups)


def build_roof_boundary(
    points_xyz: np.ndarray,
    *,
    maximum_xy_edge_m: float,
    maximum_slope_deg: float,
    minimum_xy_triangle_area_m2: float,
) -> RoofBoundary:
    """Build a filtered 2.5D TIN and return its actual-XYZ support boundary.

    ``points_xyz`` must already be the permitted class-6 point support in the
    coordinate frame that a downstream projector expects.  The function does
    not crop, flatten, interpolate, close, or otherwise infer an outline.
    """

    try:
        points = np.asarray(points_xyz, dtype=np.float64)
    except (TypeError, ValueError) as exc:
        raise RoofBoundaryError("points_xyz must be a numeric array") from exc
    if points.ndim != 2 or points.shape[1] != 3 or len(points) < 3:
        raise RoofBoundaryError("points_xyz must have shape (N, 3), N >= 3")
    if not np.isfinite(points).all():
        raise RoofBoundaryError("points_xyz must contain only finite values")

    maximum_edge, maximum_slope, minimum_area = _validate_filters(
        maximum_xy_edge_m,
        maximum_slope_deg,
        minimum_xy_triangle_area_m2,
    )
    try:
        tin = V1.build_tin(
            points,
            maximum_xy_edge_m=maximum_edge,
            maximum_slope_deg=maximum_slope,
            minimum_xy_triangle_area_m2=minimum_area,
        )
    except Exception as exc:
        raise RoofBoundaryError(f"class-6 TIN construction failed: {exc}") from exc

    vertices = _readonly_array(tin.vertices, np.dtype(np.float64))
    triangles = _readonly_array(tin.simplices, np.dtype(np.int64))
    edge_indices = _readonly_array(_boundary_edges(triangles), np.dtype(np.int64))
    segments = _readonly_array(vertices[edge_indices], np.dtype(np.float64))

    components: list[BoundaryComponent] = []
    for component_indices in _component_edge_indices(edge_indices):
        component_edges = _readonly_array(
            edge_indices[component_indices], np.dtype(np.int64)
        )
        component_segments = _readonly_array(
            vertices[component_edges], np.dtype(np.float64)
        )
        components.append(
            BoundaryComponent(
                edge_vertex_indices=component_edges,
                segments_xyz=component_segments,
            )
        )

    stats = dict(tin.stats)
    stats.update(
        {
            "boundary_edges_n": int(len(edge_indices)),
            "boundary_vertices_n": int(len(np.unique(edge_indices))),
            "boundary_components_n": int(len(components)),
        }
    )
    return RoofBoundary(
        tin_vertices_xyz=vertices,
        tin_triangle_vertex_indices=triangles,
        boundary_edge_vertex_indices=edge_indices,
        boundary_segments_xyz=segments,
        components=tuple(components),
        tin_stats=MappingProxyType(stats),
    )


__all__ = [
    "BoundaryComponent",
    "RoofBoundary",
    "RoofBoundaryError",
    "build_roof_boundary",
]
