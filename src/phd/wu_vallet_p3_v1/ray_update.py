"""Paper-based, sampled-ray component of Wu--Vallet (2026), not native reproduction.

Both sensor topology and per-vertex optical origins are mandatory.  This module
does not infer either from XYZ, produce PSMNet geometry, or establish currentness.
The paper does not specify its numeric thresholds, intersection sampling, or
face-to-point aggregation.  The explicit choices below are development choices.
In particular, four rays per face do NOT equal the tetrahedron visibility test
discussed by Wu et al. (2023).  Fig. 6's two-date update also deletes old geometry
behind new construction; that policy is not a general proof of disappearance.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

import numpy as np
from scipy.spatial import cKDTree

CONSISTENT = "consistent"
CHANGED = "changed"
SINGLE = "single"
LABELS = (CONSISTENT, CHANGED, SINGLE)
SCOPE = "WU_VALLET_2026_PAPER_BASED_SAMPLED_RAY_COMPONENT"


@dataclass(frozen=True)
class SensorMesh:
    vertices: np.ndarray
    triangles: np.ndarray
    optical_origins: np.ndarray
    native_rows: np.ndarray | None = None

    def __post_init__(self) -> None:
        v = np.array(self.vertices, dtype=np.float64, copy=True)
        t0 = np.asarray(self.triangles)
        o = np.array(self.optical_origins, dtype=np.float64, copy=True)
        if v.ndim != 2 or v.shape[1] != 3 or not np.isfinite(v).all():
            raise ValueError("vertices must be finite [N,3]")
        if t0.ndim != 2 or t0.shape[1] != 3 or t0.dtype.kind not in "iu":
            raise ValueError("triangles must be an integer [F,3] topology array")
        t = np.array(t0, dtype=np.int64, copy=True)
        if t.size and (t.min() < 0 or t.max() >= len(v)):
            raise ValueError("triangle index outside vertices")
        if o.shape != v.shape or not np.isfinite(o).all():
            raise ValueError("optical_origins must be explicit finite [N,3]")
        if len(v) and np.any(np.linalg.norm(o - v, axis=1) <= 1e-12):
            raise ValueError("optical origin cannot equal its observed vertex")
        if len(t):
            tv = v[t]
            twice_area = np.linalg.norm(np.cross(tv[:, 1] - tv[:, 0], tv[:, 2] - tv[:, 0]), axis=1)
            if np.any(twice_area <= 1e-12):
                raise ValueError("degenerate triangles require explicit preprocessing")
        if self.native_rows is None:
            rows = np.arange(len(v), dtype=np.int64)
        else:
            rows0 = np.asarray(self.native_rows)
            if rows0.shape != (len(v),) or rows0.dtype.kind not in "iu":
                raise ValueError("native_rows must be integer [N]")
            rows = np.array(rows0, dtype=np.int64, copy=True)
            if len(np.unique(rows)) != len(rows):
                raise ValueError("native_rows must uniquely identify input vertices")
        for name, array in (("vertices", v), ("triangles", t), ("optical_origins", o), ("native_rows", rows)):
            array.setflags(write=False)
            object.__setattr__(self, name, array)


@dataclass(frozen=True)
class RayUpdateConfig:
    # Required: the 2026 paper does not publish a consistency tolerance.
    distance_tolerance_m: float
    ray_sampling: str = "vertices_and_centroid"
    check_source_visibility: bool = True
    numeric_epsilon: float = 1e-9
    bvh_leaf_faces: int = 16

    def __post_init__(self) -> None:
        if not np.isfinite(self.distance_tolerance_m) or self.distance_tolerance_m < 0:
            raise ValueError("distance_tolerance_m must be finite and nonnegative")
        if self.ray_sampling not in ("vertices_and_centroid", "centroid"):
            raise ValueError("unsupported ray_sampling")
        if not np.isfinite(self.numeric_epsilon) or self.numeric_epsilon <= 0:
            raise ValueError("numeric_epsilon must be positive")
        if self.bvh_leaf_faces < 1:
            raise ValueError("bvh_leaf_faces must be positive")


@dataclass
class _Node:
    lo: np.ndarray
    hi: np.ndarray
    face_ids: np.ndarray | None = None
    left: _Node | None = None
    right: _Node | None = None


def _point_triangle_distances(point: np.ndarray, triangles: np.ndarray) -> np.ndarray:
    """Euclidean point-to-triangle distance, including edge/vertex regions."""
    a, b, c = triangles[:, 0], triangles[:, 1], triangles[:, 2]
    ab, ac, ap = b - a, c - a, point - a
    n = np.cross(ab, ac)
    n2 = np.einsum("ij,ij->i", n, n)
    signed = np.einsum("ij,ij->i", ap, n)
    projected = point - (signed / n2)[:, None] * n
    aq = projected - a
    d00 = np.einsum("ij,ij->i", ab, ab)
    d01 = np.einsum("ij,ij->i", ab, ac)
    d11 = np.einsum("ij,ij->i", ac, ac)
    d20 = np.einsum("ij,ij->i", aq, ab)
    d21 = np.einsum("ij,ij->i", aq, ac)
    denominator = d00 * d11 - d01 * d01
    u = (d11 * d20 - d01 * d21) / denominator
    v = (d00 * d21 - d01 * d20) / denominator
    inside = (u >= -1e-12) & (v >= -1e-12) & (u + v <= 1 + 1e-12)
    squared = np.full(len(triangles), np.inf)
    for start, end in ((a, b), (b, c), (c, a)):
        edge = end - start
        alpha = np.clip(np.einsum("ij,ij->i", point - start, edge) / np.einsum("ij,ij->i", edge, edge), 0, 1)
        residual = point - start - alpha[:, None] * edge
        squared = np.minimum(squared, np.einsum("ij,ij->i", residual, residual))
    squared[inside] = signed[inside] ** 2 / n2[inside]
    return np.sqrt(np.maximum(squared, 0))


class _TriangleIndex:
    def __init__(self, mesh: SensorMesh, config: RayUpdateConfig):
        self.triangles = mesh.vertices[mesh.triangles]
        self.config = config
        self.centers = self.triangles.mean(axis=1)
        self.tree = cKDTree(self.centers) if len(self.triangles) else None
        self.max_radius = (float(np.linalg.norm(self.triangles - self.centers[:, None], axis=2).max())
                           if len(self.triangles) else 0.0)
        self.root = self._build(np.arange(len(self.triangles))) if len(self.triangles) else None

    def _build(self, ids: np.ndarray) -> _Node:
        tri = self.triangles[ids]
        node = _Node(tri.min(axis=(0, 1)), tri.max(axis=(0, 1)))
        if len(ids) <= self.config.bvh_leaf_faces:
            node.face_ids = ids
        else:
            axis = int(np.argmax(np.ptp(self.centers[ids], axis=0)))
            ordered = ids[np.argsort(self.centers[ids, axis], kind="stable")]
            middle = len(ids) // 2
            node.left = self._build(ordered[:middle])
            node.right = self._build(ordered[middle:])
        return node

    def within_distance(self, point: np.ndarray, tolerance: float) -> bool:
        if self.tree is None:
            return False
        ids = self.tree.query_ball_point(point, self.max_radius + tolerance + self.config.numeric_epsilon)
        if not ids:
            return False
        return bool(np.min(_point_triangle_distances(point, self.triangles[ids]))
                    <= tolerance + self.config.numeric_epsilon)

    def _box_hit(self, node: _Node, origin: np.ndarray, direction: np.ndarray, limit: float) -> bool:
        low, high = 0.0, limit
        eps = self.config.numeric_epsilon
        for axis in range(3):
            if abs(direction[axis]) < 1e-15:
                if origin[axis] < node.lo[axis] - eps or origin[axis] > node.hi[axis] + eps:
                    return False
            else:
                t0 = (node.lo[axis] - eps - origin[axis]) / direction[axis]
                t1 = (node.hi[axis] + eps - origin[axis]) / direction[axis]
                low, high = max(low, min(t0, t1)), min(high, max(t0, t1))
                if high < low:
                    return False
        return high >= max(low, eps)

    def first_hit(self, origin: np.ndarray, endpoint: np.ndarray, endpoint_margin_m: float) -> tuple[int, float] | None:
        """Nearest two-sided triangle hit strictly before the shortened endpoint."""
        delta = endpoint - origin
        length = float(np.linalg.norm(delta))
        eps = self.config.numeric_epsilon
        best_t = length - max(endpoint_margin_m, eps)
        if self.root is None or best_t <= eps:
            return None
        direction = delta / length
        best_id = -1
        stack = [self.root]
        while stack:
            node = stack.pop()
            if not self._box_hit(node, origin, direction, best_t):
                continue
            if node.face_ids is None:
                stack.extend((node.right, node.left))
                continue
            triangles = self.triangles[node.face_ids]
            e1, e2 = triangles[:, 1] - triangles[:, 0], triangles[:, 2] - triangles[:, 0]
            p = np.cross(np.broadcast_to(direction, e2.shape), e2)
            det = np.einsum("ij,ij->i", e1, p)
            scale = np.linalg.norm(e1, axis=1) * np.linalg.norm(e2, axis=1)
            valid = np.abs(det) > 1e-12 * scale
            inverse = np.divide(1.0, det, out=np.zeros_like(det), where=valid)
            tvec = origin - triangles[:, 0]
            u = np.einsum("ij,ij->i", tvec, p) * inverse
            q = np.cross(tvec, e1)
            v = q @ direction * inverse
            t = np.einsum("ij,ij->i", e2, q) * inverse
            valid &= (u >= -1e-12) & (v >= -1e-12) & (u + v <= 1 + 1e-12)
            valid &= (t > eps) & (t < best_t)
            if valid.any():
                candidates = np.flatnonzero(valid)
                winner = candidates[np.argmin(t[candidates])]
                best_t, best_id = float(t[winner]), int(node.face_ids[winner])
        return (best_id, best_t) if best_id >= 0 else None


def _face_samples(mesh: SensorMesh, config: RayUpdateConfig) -> tuple[np.ndarray, np.ndarray]:
    points, origins = mesh.vertices[mesh.triangles], mesh.optical_origins[mesh.triangles]
    centroids, center_origins = points.mean(axis=1, keepdims=True), origins.mean(axis=1, keepdims=True)
    if config.ray_sampling == "centroid":
        return centroids, center_origins
    return np.concatenate((points, centroids), axis=1), np.concatenate((origins, center_origins), axis=1)


def _vertex_labels(mesh: SensorMesh, face_labels: np.ndarray) -> np.ndarray:
    # Explicit development tie-break: consistent > changed > single. Isolated
    # vertices remain single; provenance reports them rather than inventing rays.
    labels = np.full(len(mesh.vertices), SINGLE, dtype="U10")
    for label in (CHANGED, CONSISTENT):
        indices = mesh.triangles[face_labels == label].ravel()
        labels[indices] = label
    return labels


def _counts(labels: np.ndarray) -> dict[str, int]:
    return {label: int(np.count_nonzero(labels == label)) for label in LABELS}


def classify_and_update(old: SensorMesh, new: SensorMesh, config: RayUpdateConfig) -> dict[str, Any]:
    """Classify sensor faces, apply the declared Fig.6 update, preserve source rows.

    Consistency requires every chosen sample of a face to be within tolerance of
    the other surface.  Nonconsistent source samples cast segments toward their
    observed endpoints.  A nearer target hit marks the nonconsistent source and
    target faces changed.  Consistent faces take precedence over conflict marks.
    Both acquisition directions are evaluated from their OWN supplied origins.
    No small-region filtering or mesh stitching is silently added.
    """
    meshes = {"old": old, "new": new}
    indices = {key: _TriangleIndex(mesh, config) for key, mesh in meshes.items()}
    samples = {key: _face_samples(mesh, config) for key, mesh in meshes.items()}
    labels: dict[str, np.ndarray] = {}
    diagnostics: dict[str, Any] = {"directions": {}}
    for side, other in (("old", "new"), ("new", "old")):
        flags = np.array([all(indices[other].within_distance(point, config.distance_tolerance_m)
                              for point in face) for face in samples[side][0]], dtype=bool)
        labels[side] = np.where(flags, CONSISTENT, SINGLE).astype("U10")

    consistent = {side: values == CONSISTENT for side, values in labels.items()}
    conflict_pairs = []
    for side, other in (("old", "new"), ("new", "old")):
        stats = {"attempted_rays": 0, "source_self_occluded_rays": 0, "target_hits": 0,
                 "hits_on_consistent_target_faces": 0, "degenerate_sample_rays": 0}
        for face_id, (points, origins) in enumerate(zip(*samples[side])):
            if consistent[side][face_id]:
                continue
            for sample_id, (point, origin) in enumerate(zip(points, origins)):
                stats["attempted_rays"] += 1
                if np.linalg.norm(point - origin) <= config.numeric_epsilon:
                    stats["degenerate_sample_rays"] += 1
                    continue
                if config.check_source_visibility and indices[side].first_hit(origin, point, config.distance_tolerance_m) is not None:
                    stats["source_self_occluded_rays"] += 1
                    continue
                hit = indices[other].first_hit(origin, point, config.distance_tolerance_m)
                if hit is None:
                    continue
                target_face, distance = hit
                stats["target_hits"] += 1
                labels[side][face_id] = CHANGED
                if consistent[other][target_face]:
                    stats["hits_on_consistent_target_faces"] += 1
                else:
                    labels[other][target_face] = CHANGED
                old_face, new_face = ((face_id, target_face) if side == "old" else (target_face, face_id))
                conflict_pairs.append((0 if side == "old" else 1, old_face, new_face, sample_id, distance))
        diagnostics["directions"][f"{side}_to_{other}"] = stats

    vertex_labels = {side: _vertex_labels(mesh, labels[side]) for side, mesh in meshes.items()}
    keep = {"old": vertex_labels["old"] != CHANGED, "new": vertex_labels["new"] != CONSISTENT}
    points = np.concatenate((old.vertices[keep["old"]], new.vertices[keep["new"]]))
    sources = np.concatenate((np.full(int(keep["old"].sum()), "old", dtype="U3"),
                              np.full(int(keep["new"].sum()), "new", dtype="U3")))
    rows = np.concatenate((old.native_rows[keep["old"]], new.native_rows[keep["new"]]))
    diagnostics.update({
        "face_counts": {side: _counts(values) for side, values in labels.items()},
        "vertex_counts": {side: _counts(values) for side, values in vertex_labels.items()},
        "retained_old_vertices": int(keep["old"].sum()),
        "removed_old_vertices": int((~keep["old"]).sum()),
        "admitted_new_vertices": int(keep["new"].sum()),
        "excluded_consistent_new_vertices": int((~keep["new"]).sum()),
        "output_points": len(points),
        "isolated_vertices": {side: len(mesh.vertices) - len(np.unique(mesh.triangles))
                              for side, mesh in meshes.items()},
    })
    return {
        "old_face_labels": labels["old"], "new_face_labels": labels["new"],
        "old_vertex_labels": vertex_labels["old"], "new_vertex_labels": vertex_labels["new"],
        "old_keep_mask": keep["old"], "new_keep_mask": keep["new"],
        "updated_points": points, "updated_source": sources, "updated_native_rows": rows,
        "conflict_pairs": np.array(conflict_pairs, dtype=np.float64).reshape(-1, 5),
        "conflict_pair_columns": ["direction_0_old_1_new", "old_face", "new_face", "source_sample", "hit_distance_m"],
        "diagnostics": diagnostics,
        "reproduction_scope": {
            "name": SCOPE, "native_2026_reproduction": False, "scientific_verdict": None,
            "config": asdict(config), "optical_origins": "required_input_per_vertex",
            "topology": "required_input_triangles",
            "consistency_rule": "all_face_samples_within_euclidean_surface_distance_tolerance",
            "face_precedence": "consistent_before_sampled_conflict_before_single",
            "vertex_precedence": "consistent_before_changed_before_single",
            "update_rule": "keep_old_except_changed_add_new_except_consistent",
            "construction_policy": "Fig6_old_background_removed_when_old_ray_hits_new_foreground",
            "unknown_or_omitted": [
                "official_code_and_exact_numeric_parameters_unavailable",
                "finite_sample_rays_not_triangle_tetrahedron_volume_intersection",
                "small_changed_region_filter_omitted_threshold_unpublished",
                "sensor_meshing_PSMNet_and_training_not_implemented_here",
                "point_aggregation_precedence_is_a_declared_development_choice",
                "single_and_hidden_regions_are_not_certified_current_geometry",
                "endpoint_consistency_samples_do_not_prove_whole_face_overlap",
            ],
        },
    }
