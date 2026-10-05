"""Accelerated, explicitly scoped Wu--Vallet paper-based sampled-ray update.

This implements the v1 declared-choice component on actual triangulated inputs.
It is not the unpublished author code or a triangle/tetrahedron volume test.
No optical origin is estimated here. ONLY_CURRENT_IMAGE_RAYS is a one-direction
partial method: old surfaces behind a current observation cannot be contradicted
by the missing old acquisition rays and may therefore survive in the output.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from time import perf_counter
from typing import Any

import numpy as np
import open3d as o3d
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components

from src.phd.wu_vallet_p3_v1.ray_update import (
    CHANGED, CONSISTENT, LABELS, SINGLE, SensorMesh as RequiredOriginMesh,
    _counts, _vertex_labels,
)


@dataclass(frozen=True)
class SensorMesh:
    vertices: np.ndarray
    triangles: np.ndarray
    optical_origins: np.ndarray | None
    native_rows: np.ndarray | None = None

    def __post_init__(self) -> None:
        if self.optical_origins is not None and not np.isfinite(self.optical_origins).all():
            origins = np.array(self.optical_origins, dtype=np.float64, copy=True)
            if origins.shape != np.asarray(self.vertices).shape:
                raise ValueError("optical origins shape mismatch")
            available = np.isfinite(origins).all(axis=1)
            unavailable = np.isnan(origins).all(axis=1)
            if not (available | unavailable).all():
                raise ValueError("Unavailable origins require three NaNs; partial NaN or infinity prohibited")
            checked = SensorMesh(self.vertices, self.triangles, None, self.native_rows)
            if np.any(np.linalg.norm(origins[available] - checked.vertices[available], axis=1) <= 1e-12):
                raise ValueError("Optical origin cannot equal its observed vertex")
            for name in ("vertices", "triangles", "native_rows"):
                object.__setattr__(self, name, getattr(checked, name))
            origins.setflags(write=False)
            object.__setattr__(self, "optical_origins", origins)
            return
        # The authoritative geometry/origin checks remain shared with v1 when
        # origins exist. Missing origins are permitted only at the old interface;
        # classify_and_update enforces that role and direction explicitly.
        if self.optical_origins is not None:
            checked = RequiredOriginMesh(self.vertices, self.triangles,
                                         self.optical_origins, self.native_rows)
            for name in ("vertices", "triangles", "optical_origins", "native_rows"):
                object.__setattr__(self, name, getattr(checked, name))
            return
        v = np.array(self.vertices, dtype=np.float64, copy=True)
        t0 = np.asarray(self.triangles)
        if v.ndim != 2 or v.shape[1] != 3 or not np.isfinite(v).all():
            raise ValueError("vertices must be finite [N,3]")
        if t0.ndim != 2 or t0.shape[1] != 3 or t0.dtype.kind not in "iu":
            raise ValueError("triangles must be integer [F,3]")
        t = np.array(t0, dtype=np.int64, copy=True)
        if t.size and (t.min() < 0 or t.max() >= len(v)):
            raise ValueError("triangle index outside vertices")
        if len(t):
            tv = v[t]
            if np.any(np.linalg.norm(np.cross(tv[:, 1] - tv[:, 0], tv[:, 2] - tv[:, 0]), axis=1) <= 1e-12):
                raise ValueError("degenerate triangles require explicit preprocessing")
        r0 = np.arange(len(v), dtype=np.int64) if self.native_rows is None else np.asarray(self.native_rows)
        if r0.shape != (len(v),) or r0.dtype.kind not in "iu" or len(np.unique(r0)) != len(r0):
            raise ValueError("native_rows must uniquely identify input vertices")
        rows = np.array(r0, dtype=np.int64, copy=True)
        for name, value in (("vertices", v), ("triangles", t), ("native_rows", rows)):
            value.setflags(write=False)
            object.__setattr__(self, name, value)


@dataclass(frozen=True)
class RuntimeConfig:
    distance_tolerance_m: float
    direction_mode: str = "BIDIRECTIONAL"
    ray_sampling: str = "vertices_and_centroid"
    check_source_visibility: bool = True
    small_region_area_m2: float = 0.0
    query_chunk_size: int = 131072
    nthreads: int = 6
    numeric_epsilon: float = 1e-9

    def __post_init__(self) -> None:
        for name in ("distance_tolerance_m", "small_region_area_m2"):
            value = getattr(self, name)
            if not np.isfinite(value) or value < 0:
                raise ValueError(f"{name} must be finite and nonnegative")
        if self.direction_mode not in ("BIDIRECTIONAL", "ONLY_CURRENT_IMAGE_RAYS"):
            raise ValueError("direction_mode must explicitly name the supported acquisition directions")
        if self.ray_sampling not in ("vertices_and_centroid", "centroid"):
            raise ValueError("unsupported ray sampling")
        if self.query_chunk_size < 1 or self.nthreads < 1:
            raise ValueError("query_chunk_size and nthreads must be positive")
        if not np.isfinite(self.numeric_epsilon) or self.numeric_epsilon <= 0:
            raise ValueError("numeric_epsilon must be positive")


def _paired_point_triangle_distance(points: np.ndarray, tri: np.ndarray) -> np.ndarray:
    """Float64 distances to the accelerated closest-triangle candidates."""
    a, b, c = tri[:, 0], tri[:, 1], tri[:, 2]
    ab, ac, ap = b - a, c - a, points - a
    normal = np.cross(ab, ac)
    n2 = np.einsum("ij,ij->i", normal, normal)
    signed = np.einsum("ij,ij->i", ap, normal)
    projected = ap - (signed / n2)[:, None] * normal
    aa = np.einsum("ij,ij->i", ab, ab)
    acdot = np.einsum("ij,ij->i", ab, ac)
    cc = np.einsum("ij,ij->i", ac, ac)
    aq = np.einsum("ij,ij->i", ab, projected)
    cq = np.einsum("ij,ij->i", ac, projected)
    denom = aa * cc - acdot * acdot
    u, v = (cc * aq - acdot * cq) / denom, (aa * cq - acdot * aq) / denom
    inside = (u >= -1e-12) & (v >= -1e-12) & (u + v <= 1 + 1e-12)
    squared = np.full(len(points), np.inf)
    for start, end in ((a, b), (b, c), (c, a)):
        edge = end - start
        along = np.clip(np.einsum("ij,ij->i", points - start, edge) /
                        np.einsum("ij,ij->i", edge, edge), 0, 1)
        residual = points - start - along[:, None] * edge
        squared = np.minimum(squared, np.einsum("ij,ij->i", residual, residual))
    squared[inside] = signed[inside] ** 2 / n2[inside]
    return np.sqrt(np.maximum(squared, 0))


class TriangleScene:
    """Batched Embree scene; finite segments retain v1 endpoint semantics.

    Open3D selects triangle candidates in float32 after a common recentering;
    distance to the selected triangle is evaluated again in float64. Boundary
    triangle ties can differ from the NumPy BVH and are not exact-code parity.
    """

    def __init__(self, mesh: SensorMesh, config: RuntimeConfig, shift: np.ndarray | None = None):
        self.mesh, self.config = mesh, config
        self.shift = np.zeros(3) if shift is None else np.asarray(shift, dtype=np.float64)
        self.scene = o3d.t.geometry.RaycastingScene(nthreads=config.nthreads)
        self.empty = len(mesh.triangles) == 0
        if not self.empty:
            self.scene.add_triangles(
                o3d.core.Tensor(np.asarray(mesh.vertices - self.shift, dtype=np.float32)),
                o3d.core.Tensor(np.asarray(mesh.triangles, dtype=np.uint32)),
            )

    def distances(self, points: np.ndarray) -> np.ndarray:
        points = np.asarray(points, dtype=np.float64)
        result = np.full(len(points), np.inf)
        if self.empty:
            return result
        for start in range(0, len(points), self.config.query_chunk_size):
            stop = min(start + self.config.query_chunk_size, len(points))
            chunk = points[start:stop]
            closest = self.scene.compute_closest_points(
                o3d.core.Tensor(np.asarray(chunk - self.shift, dtype=np.float32)),
                nthreads=self.config.nthreads,
            )
            ids = closest["primitive_ids"].numpy().astype(np.int64)
            result[start:stop] = _paired_point_triangle_distance(chunk, self.mesh.vertices[self.mesh.triangles[ids]])
        return result

    def first_hits(self, origins: np.ndarray, endpoints: np.ndarray,
                   endpoint_margin_m: float) -> tuple[np.ndarray, np.ndarray]:
        origins, endpoints = np.asarray(origins, dtype=np.float64), np.asarray(endpoints, dtype=np.float64)
        result_ids, result_distance = np.full(len(origins), -1, dtype=np.int64), np.full(len(origins), np.inf)
        if self.empty:
            return result_ids, result_distance
        for start in range(0, len(origins), self.config.query_chunk_size):
            stop = min(start + self.config.query_chunk_size, len(origins))
            origin, endpoint = origins[start:stop], endpoints[start:stop]
            delta = endpoint - origin
            length = np.linalg.norm(delta, axis=1)
            safe_length = np.where(length > 0, length, 1)
            direction = delta / safe_length[:, None]
            rays = o3d.core.Tensor(np.asarray(np.concatenate((origin - self.shift, direction), axis=1), dtype=np.float32))
            hit = self.scene.cast_rays(rays, nthreads=self.config.nthreads)
            ids = hit["primitive_ids"].numpy().astype(np.int64)
            distance = hit["t_hit"].numpy().astype(np.float64)
            # A ray starting on a surface must continue past that zero-distance
            # hit; v1 accepts only t > epsilon. Enumerate only these rare rays.
            near_origin = np.isfinite(distance) & (distance <= self.config.numeric_epsilon)
            if near_origin.any():
                exceptional = np.flatnonzero(near_origin)
                all_hits = self.scene.list_intersections(
                    o3d.core.Tensor(rays.numpy()[exceptional]), nthreads=self.config.nthreads)
                splits = all_hits["ray_splits"].numpy()
                all_t, all_ids = all_hits["t_hit"].numpy(), all_hits["primitive_ids"].numpy()
                for j, ray_id in enumerate(exceptional):
                    candidates = np.arange(splits[j], splits[j + 1], dtype=np.int64)
                    candidates = candidates[all_t[candidates] > self.config.numeric_epsilon]
                    if len(candidates):
                        winner = candidates[np.argmin(all_t[candidates])]
                        distance[ray_id], ids[ray_id] = float(all_t[winner]), int(all_ids[winner])
                    else:
                        distance[ray_id] = np.inf
            valid = np.isfinite(distance) & (ids < len(self.mesh.triangles))
            # Float64 line/plane intersection removes float32 rounding around the
            # finite endpoint threshold; candidate discovery remains float32.
            at = np.flatnonzero(valid)
            if len(at):
                tri = self.mesh.vertices[self.mesh.triangles[ids[at]]]
                normal = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
                denominator = np.einsum("ij,ij->i", direction[at], normal)
                numerator = np.einsum("ij,ij->i", tri[:, 0] - origin[at], normal)
                distance[at] = np.divide(numerator, denominator, out=np.full(len(at), np.inf),
                                         where=np.abs(denominator) > 1e-30)
            valid &= distance > self.config.numeric_epsilon
            valid &= distance < length - max(endpoint_margin_m, self.config.numeric_epsilon)
            result_ids[start:stop][valid], result_distance[start:stop][valid] = ids[valid], distance[valid]
        return result_ids, result_distance


def _samples(mesh: SensorMesh, mode: str) -> tuple[np.ndarray, np.ndarray | None]:
    points = mesh.vertices[mesh.triangles]
    origins = None if mesh.optical_origins is None else mesh.optical_origins[mesh.triangles]
    if mode == "centroid":
        return points.mean(axis=1, keepdims=True), None if origins is None else origins.mean(axis=1, keepdims=True)
    return (np.concatenate((points, points.mean(axis=1, keepdims=True)), axis=1),
            None if origins is None else np.concatenate((origins, origins.mean(axis=1, keepdims=True)), axis=1))


def region_diagnostics(mesh: SensorMesh, face_labels: np.ndarray,
                       minimum_changed_area_m2: float = 0.0) -> tuple[np.ndarray, dict[str, Any]]:
    """Edge-connected changed regions; optional changed->single demotion only.

    The area criterion and demotion target are explicit development choices,
    because the paper does not publish its small-region filter specification.
    Original labels are not modified. A zero threshold only measures regions.
    """
    changed_ids = np.flatnonzero(face_labels == CHANGED)
    refined = face_labels.copy()
    component_ids = np.full(len(face_labels), -1, dtype=np.int64)
    if not len(changed_ids):
        return refined, {"changed_component_ids": component_ids, "component_face_counts": np.zeros(0, dtype=np.int64),
                         "component_areas_m2": np.zeros(0), "component_count": 0,
                         "demoted_changed_faces": 0, "nonmanifold_changed_edges": 0}
    tri_ids = mesh.triangles[changed_ids]
    edges = np.concatenate((tri_ids[:, [0, 1]], tri_ids[:, [1, 2]], tri_ids[:, [2, 0]]))
    owners = np.tile(np.arange(len(changed_ids)), 3)
    edges.sort(axis=1)
    order = np.lexsort((edges[:, 1], edges[:, 0]))
    edges, owners = edges[order], owners[order]
    same = np.all(edges[1:] == edges[:-1], axis=1)
    left, right = owners[:-1][same], owners[1:][same]
    adjacency = coo_matrix((np.ones(len(left), dtype=np.uint8), (left, right)),
                           shape=(len(changed_ids), len(changed_ids))).tocsr()
    n, components = connected_components(adjacency, directed=False)
    component_ids[changed_ids] = components
    triangles = mesh.vertices[tri_ids]
    face_areas = 0.5 * np.linalg.norm(np.cross(triangles[:, 1] - triangles[:, 0],
                                             triangles[:, 2] - triangles[:, 0]), axis=1)
    counts = np.bincount(components, minlength=n)
    areas = np.bincount(components, weights=face_areas, minlength=n)
    removed = areas[components] < minimum_changed_area_m2
    refined[changed_ids[removed]] = SINGLE
    starts = np.r_[0, np.flatnonzero(~same) + 1, len(edges)]
    return refined, {"changed_component_ids": component_ids, "component_face_counts": counts,
                     "component_areas_m2": areas, "component_count": int(n),
                     "demoted_changed_faces": int(removed.sum()),
                     "nonmanifold_changed_edges": int(np.count_nonzero(np.diff(starts) > 2))}


def _assembled(meshes: dict[str, SensorMesh], labels: dict[str, np.ndarray]) -> dict[str, Any]:
    vertex_labels = {side: _vertex_labels(mesh, labels[side]) for side, mesh in meshes.items()}
    keep = {"old": vertex_labels["old"] != CHANGED, "new": vertex_labels["new"] != CONSISTENT}
    return {
        "old_face_labels": labels["old"], "new_face_labels": labels["new"],
        "old_vertex_labels": vertex_labels["old"], "new_vertex_labels": vertex_labels["new"],
        "old_keep_mask": keep["old"], "new_keep_mask": keep["new"],
        "updated_points": np.concatenate([meshes[side].vertices[keep[side]] for side in ("old", "new")]),
        "updated_source": np.concatenate([np.full(int(keep[side].sum()), side, dtype="U3") for side in ("old", "new")]),
        "updated_native_rows": np.concatenate([meshes[side].native_rows[keep[side]] for side in ("old", "new")]),
    }


def classify_and_update(old: SensorMesh, new: SensorMesh, config: RuntimeConfig) -> dict[str, Any]:
    started = perf_counter()
    if new.optical_origins is None or not np.isfinite(new.optical_origins).all():
        raise ValueError("current image optical origins are required")
    if config.direction_mode == "BIDIRECTIONAL" and old.optical_origins is None:
        raise ValueError("BIDIRECTIONAL requires measured or explicitly supplied old optical origins")
    if config.direction_mode == "BIDIRECTIONAL" and not np.isfinite(old.optical_origins).all(axis=1).any():
        raise ValueError("BIDIRECTIONAL requires at least one available old origin")
    meshes = {"old": old, "new": new}
    all_vertices = np.concatenate((old.vertices, new.vertices))
    shift = (all_vertices.min(axis=0) + all_vertices.max(axis=0)) / 2 if len(all_vertices) else np.zeros(3)
    scenes = {side: TriangleScene(mesh, config, shift) for side, mesh in meshes.items()}
    samples = {side: _samples(mesh, config.ray_sampling) for side, mesh in meshes.items()}
    labels, distances = {}, {}
    for side, other in (("old", "new"), ("new", "old")):
        points = samples[side][0]
        distances[side] = scenes[other].distances(points.reshape(-1, 3)).reshape(points.shape[:2])
        consistent = np.all(distances[side] <= config.distance_tolerance_m + config.numeric_epsilon, axis=1)
        labels[side] = np.where(consistent, CONSISTENT, SINGLE).astype("U10")
    consistent = {side: label == CONSISTENT for side, label in labels.items()}
    directions = (("old", "new"), ("new", "old")) if config.direction_mode == "BIDIRECTIONAL" else (("new", "old"),)
    diagnostics: dict[str, Any] = {"directions": {}, "query_shift_xyz": shift.tolist()}
    conflict_pairs = []
    for side, other in directions:
        points, origins = samples[side]
        assert origins is not None
        face_ids = np.flatnonzero(~consistent[side])
        nsample = points.shape[1]
        endpoints, starts = points[face_ids].reshape(-1, 3), origins[face_ids].reshape(-1, 3)
        source_face = np.repeat(face_ids, nsample)
        source_sample = np.tile(np.arange(nsample), len(face_ids))
        available = np.isfinite(starts).all(axis=1)
        nondegenerate = available & (np.linalg.norm(endpoints - starts, axis=1) > config.numeric_epsilon)
        visible = nondegenerate.copy()
        if config.check_source_visibility:
            self_ids, _ = scenes[side].first_hits(starts[available], endpoints[available], config.distance_tolerance_m)
            visible[available] &= self_ids < 0
        query_ids = np.flatnonzero(visible)
        target_ids, hit_distance = scenes[other].first_hits(starts[visible], endpoints[visible], config.distance_tolerance_m)
        hits = target_ids >= 0
        ray_ids, target = query_ids[hits], target_ids[hits]
        src = source_face[ray_ids]
        labels[side][src] = CHANGED
        labels[other][target[~consistent[other][target]]] = CHANGED
        old_face, new_face = (src, target) if side == "old" else (target, src)
        conflict_pairs.append(np.column_stack((np.full(len(src), 0 if side == "old" else 1),
                                               old_face, new_face, source_sample[ray_ids], hit_distance[hits])))
        diagnostics["directions"][f"{side}_to_{other}"] = {
            "attempted_rays": len(starts), "source_self_occluded_rays": int((nondegenerate & ~visible).sum()),
            "target_hits": int(hits.sum()), "hits_on_consistent_target_faces": int(consistent[other][target].sum()),
            "degenerate_sample_rays": int((available & ~nondegenerate).sum()),
            "unavailable_origin_sample_rays": int((~available).sum()),
        }
    raw_labels = {side: label.copy() for side, label in labels.items()}
    region_info = {}
    for side, mesh in meshes.items():
        labels[side], region_info[side] = region_diagnostics(mesh, raw_labels[side], config.small_region_area_m2)
    result = _assembled(meshes, labels)
    raw = _assembled(meshes, raw_labels)
    result.update({f"raw_{key}": value for key, value in raw.items()})
    result.update({
        "conflict_pairs": np.concatenate(conflict_pairs) if conflict_pairs else np.empty((0, 5)),
        "conflict_pair_columns": ["direction_0_old_1_new", "old_face", "new_face", "source_sample", "hit_distance_m"],
        "old_sample_surface_distances_m": distances["old"], "new_sample_surface_distances_m": distances["new"],
        "region_diagnostics": region_info,
        "diagnostics": diagnostics,
        "reproduction_scope": {
            "name": "WU_VALLET_2026_PAPER_BASED_ACCELERATED_SAMPLED_RAY_COMPONENT",
            "native_2026_reproduction": False, "scientific_verdict": None,
            "config": asdict(config), "backend": f"Open3D {o3d.__version__} RaycastingScene CPU",
            "candidate_precision": "float32_common_recentered_triangle_and_ray_queries",
            "surface_distance_precision": "float64_distance_to_accelerated_closest_triangle_candidate",
            "intersection_distance_precision": "float64_plane_intersection_for_float32_selected_hit_triangle",
            "optical_origins": {side: "missing_not_invented" if mesh.optical_origins is None else "explicit_input_per_vertex" for side, mesh in meshes.items()},
            "unavailable_origin_vertices": {side: len(mesh.vertices) if mesh.optical_origins is None else
                                             int((~np.isfinite(mesh.optical_origins).all(axis=1)).sum())
                                             for side, mesh in meshes.items()},
            "partial_origin_policy": "Retain target geometry and skip unavailable source rays; missing face-centroid origins also skipped",
            "executed_directions": [f"{a}_to_{b}" for a, b in directions],
            "missing_old_ray_effect": ("not_applicable" if config.direction_mode == "BIDIRECTIONAL" else
                                       "cannot_mark_old_background_behind_current_foreground_using_missing_old_rays"),
            "consistency_rule": "all_face_samples_within_euclidean_surface_distance_tolerance",
            "face_precedence": "consistent_before_sampled_conflict_before_single",
            "vertex_precedence": "consistent_before_changed_before_single",
            "update_rule": "keep_old_except_changed_add_new_except_consistent",
            "construction_policy": "Fig6_old_background_removed_only_when_old_ray_hits_new_foreground",
            "small_region_filter": "edge_connected_changed_area_below_explicit_threshold_demoted_to_single_raw_labels_preserved",
            "unknown_or_omitted": ["official_code_and_exact_numeric_parameters_unavailable",
                                   "sampled_rays_not_triangle_tetrahedron_volume_intersection",
                                   "small_region_filter_specification_and_threshold_unpublished",
                                   "meshing_and_PSMNet_equivalence_must_be_recorded_by_caller",
                                   "face_and_vertex_aggregation_are_declared_development_choices",
                                   "single_and_hidden_regions_are_not_certified_current_geometry",
                                   "float32_candidate_discovery_and_shared_edge_ties_may_differ_from_v1_float64_BVH"],
        },
    })
    for prefix, assembled, face_label in (("", result, labels), ("raw_", raw, raw_labels)):
        diagnostics[f"{prefix}face_counts"] = {side: _counts(value) for side, value in face_label.items()}
        diagnostics[f"{prefix}vertex_counts"] = {side: _counts(assembled[f"{side}_vertex_labels"]) for side in meshes}
        diagnostics[f"{prefix}retained_old_vertices"] = int(assembled["old_keep_mask"].sum())
        diagnostics[f"{prefix}removed_old_vertices"] = int((~assembled["old_keep_mask"]).sum())
        diagnostics[f"{prefix}admitted_new_vertices"] = int(assembled["new_keep_mask"].sum())
        diagnostics[f"{prefix}excluded_consistent_new_vertices"] = int((~assembled["new_keep_mask"]).sum())
        diagnostics[f"{prefix}output_points"] = len(assembled["updated_points"])
    diagnostics["isolated_vertices"] = {side: len(mesh.vertices) - len(np.unique(mesh.triangles)) for side, mesh in meshes.items()}
    diagnostics["elapsed_seconds"] = perf_counter() - started
    return result
