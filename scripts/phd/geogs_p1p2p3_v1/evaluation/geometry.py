"""Surface evaluation for the frozen GeoGS development diagnostic.

Only call this module with frozen reconstruction candidates. References are
evaluation inputs and never participate in adaptation, alignment, or training.
"""
from pathlib import Path

import numpy as np
import open3d as o3d
from scipy.spatial import cKDTree

DEFAULT_THRESHOLDS = (0.1, 0.2, 0.25, 0.5, 1.0, 2.0)


def _points(value):
    result = np.asarray(value, dtype=np.float64).reshape(-1, 3)
    if not np.isfinite(result).all():
        raise ValueError("Geometry contains nonfinite coordinates")
    return result


def _bounds(value):
    if isinstance(value, dict):
        value = [value[axis] for axis in ("x", "y", "z")]
    result = np.asarray(value, dtype=np.float64)
    if result.shape != (3, 2) or not np.isfinite(result).all() or not np.all(result[:, 0] < result[:, 1]):
        raise ValueError("Bounds must contain three finite increasing [lower, upper] intervals")
    return result


def inside_half_open(points, bounds):
    points, bounds = _points(points), _bounds(bounds)
    return np.all((points >= bounds[:, 0]) & (points < bounds[:, 1]), axis=1)


def triangle_areas(vertices, triangles):
    vertices = _points(vertices)
    triangles = np.asarray(triangles, dtype=np.int64).reshape(-1, 3)
    if len(triangles) and (triangles.min() < 0 or triangles.max() >= len(vertices)):
        raise ValueError("Triangle index outside vertex array")
    corners = vertices[triangles]
    return np.linalg.norm(np.cross(corners[:, 1] - corners[:, 0], corners[:, 2] - corners[:, 0]), axis=1) * 0.5


def clip_mesh_to_box(vertices, triangles, bounds):
    """Clip boundary-crossing triangles; do not discard their interior portions.

    Polygon intersections on an upper plane remain as zero-area boundary edges.
    A face lying entirely on an excluded upper plane is discarded, implementing
    half-open ownership without removing crossing faces.
    """
    vertices, bounds = _points(vertices), _bounds(bounds)
    faces = np.asarray(triangles, dtype=np.int64).reshape(-1, 3)
    areas = triangle_areas(vertices, faces)
    faces = faces[areas > 0]
    corners = vertices[faces]
    overlaps = np.all((corners.max(axis=1) >= bounds[:, 0]) & (corners.min(axis=1) < bounds[:, 1]), axis=1)
    faces, corners = faces[overlaps], corners[overlaps]
    entirely_inside = np.all((corners >= bounds[:, 0]) & (corners < bounds[:, 1]), axis=(1, 2))
    out_vertices = list(corners[entirely_inside].reshape(-1, 3))
    out_triangles = list(np.arange(len(out_vertices), dtype=np.int64).reshape(-1, 3))
    for face in faces[~entirely_inside]:
        polygon = vertices[face].copy()
        for axis in range(3):
            for side in (0, 1):
                plane = bounds[axis, side]
                if not len(polygon):
                    break
                clipped = []
                previous = polygon[-1]
                previous_inside = previous[axis] >= plane if side == 0 else previous[axis] <= plane
                for current in polygon:
                    current_inside = current[axis] >= plane if side == 0 else current[axis] <= plane
                    if current_inside != previous_inside:
                        fraction = (plane - previous[axis]) / (current[axis] - previous[axis])
                        crossing = previous + fraction * (current - previous)
                        crossing[axis] = plane
                        clipped.append(crossing)
                    if current_inside:
                        clipped.append(current)
                    previous, previous_inside = current, current_inside
                polygon = np.asarray(clipped, dtype=np.float64).reshape(-1, 3)
        if len(polygon) < 3 or any(np.all(polygon[:, axis] == bounds[axis, 1]) for axis in range(3)):
            continue
        for index in range(1, len(polygon) - 1):
            corners = polygon[[0, index, index + 1]]
            if np.linalg.norm(np.cross(corners[1] - corners[0], corners[2] - corners[0])) == 0:
                continue
            offset = len(out_vertices)
            out_vertices.extend(corners)
            out_triangles.append([offset, offset + 1, offset + 2])
    return np.asarray(out_vertices, dtype=np.float64).reshape(-1, 3), np.asarray(out_triangles, dtype=np.int64).reshape(-1, 3)


def sample_surface(vertices, triangles, spacing=0.1, seed=0):
    """Seeded area-uniform samples at ceil(surface_area / spacing**2) density."""
    if not np.isfinite(spacing) or spacing <= 0:
        raise ValueError("Surface spacing must be positive")
    vertices = _points(vertices)
    triangles = np.asarray(triangles, dtype=np.int64).reshape(-1, 3)
    area = triangle_areas(vertices, triangles)
    positive = area > 0
    triangles, area = triangles[positive], area[positive]
    total_area = float(area.sum())
    if total_area == 0:
        return np.empty((0, 3), dtype=np.float64), total_area
    count = int(np.ceil(total_area / float(spacing) ** 2))
    generator = np.random.default_rng(seed)
    picked = generator.choice(len(triangles), size=count, p=area / total_area)
    uv = generator.random((count, 2))
    root_u = np.sqrt(uv[:, 0])
    barycentric = np.column_stack((1 - root_u, root_u * (1 - uv[:, 1]), root_u * uv[:, 1]))
    sampled = np.einsum("ni,nij->nj", barycentric, vertices[triangles[picked]])
    return sampled, total_area


def voxel_reference(points, voxel_size=0.1, origin=(0.0, 0.0, 0.0)):
    """Select an original reference point per fixed-origin floor voxel.

    The point nearest each cell center represents that cell, with coordinate
    tie-breaks. No averaging, interpolation, registration, or surface fitting
    changes the reference geometry.
    """
    points = _points(points)
    if not np.isfinite(voxel_size) or voxel_size <= 0:
        raise ValueError("Reference voxel size must be positive")
    origin = np.asarray(origin, dtype=np.float64).reshape(3)
    if not np.isfinite(origin).all():
        raise ValueError("Voxel origin must be finite")
    if not len(points):
        return points.copy(), np.empty(0, dtype=np.int64)
    cells = np.floor((points - origin) / voxel_size).astype(np.int64)
    centers = origin + (cells + 0.5) * voxel_size
    squared = np.sum((points - centers) ** 2, axis=1)
    order = np.lexsort((points[:, 2], points[:, 1], points[:, 0], squared, cells[:, 2], cells[:, 1], cells[:, 0]))
    sorted_cells = cells[order]
    first = np.r_[True, np.any(sorted_cells[1:] != sorted_cells[:-1], axis=1)]
    indices = order[first]
    return points[indices].copy(), indices


def points_to_triangle_surface(points, vertices, triangles, chunk_size=100000):
    """Unsigned point-to-triangle BVH distance, including triangle interiors."""
    points, vertices = _points(points), _points(vertices)
    triangles = np.asarray(triangles, dtype=np.int64).reshape(-1, 3)
    area = triangle_areas(vertices, triangles)
    triangles = triangles[area > 0]
    if not len(points):
        return np.empty(0, dtype=np.float64)
    if not len(triangles):
        return np.full(len(points), np.inf, dtype=np.float64)
    scene = o3d.t.geometry.RaycastingScene()
    # Open3D's BVH API requires Float32 positions; callers supply the frozen
    # local metric frame, not large global eastings/northings.
    scene.add_triangles(o3d.core.Tensor(vertices.astype(np.float32)), o3d.core.Tensor(triangles.astype(np.uint32)))
    distances = []
    for start in range(0, len(points), chunk_size):
        query = o3d.core.Tensor(points[start:start + chunk_size].astype(np.float32))
        distances.append(scene.compute_distance(query).numpy().astype(np.float64))
    return np.concatenate(distances)


def distance_statistics(distances):
    values = np.asarray(distances, dtype=np.float64)
    if not len(values) or not np.isfinite(values).all():
        return {key: None for key in ("mean", "median", "p95", "rmse")}
    return {"mean": float(values.mean()), "median": float(np.median(values)),
            "p95": float(np.percentile(values, 95)), "rmse": float(np.sqrt(np.mean(values ** 2)))}


def xy_support_diagnostic(prediction_points, reference_points, cell_size=0.5, origin=(0.0, 0.0)):
    if not np.isfinite(cell_size) or cell_size <= 0:
        raise ValueError("XY support cell size must be positive")
    origin = np.asarray(origin, dtype=np.float64).reshape(2)
    def cells(points):
        return {tuple(cell) for cell in np.floor((_points(points)[:, :2] - origin) / cell_size).astype(np.int64)}
    pred, ref = cells(prediction_points), cells(reference_points)
    return {"cell_size_m": cell_size, "origin": origin.tolist(), "reference_supported_cells": len(ref),
            "prediction_sample_supported_cells": len(pred), "reference_cells_without_prediction_samples": len(ref - pred),
            "prediction_cells_without_reference_points": len(pred - ref),
            "status": "CONTEXTUAL_SUPPORT_DIAGNOSTIC_NOT_PROOF_OF_COVERAGE_OR_FAILURE"}


def evaluate_geometry(vertices, triangles, reference_points, bounds, spacing=0.1,
                      reference_voxel_size=0.1, seed=0, thresholds=DEFAULT_THRESHOLDS,
                      voxel_origin=(0.0, 0.0, 0.0), xy_cell_size=0.5):
    """Return JSON-ready metrics and machine-readable arrays for one fixed ROI."""
    bounds = _bounds(bounds)
    reference_points = _points(reference_points)
    reference_membership = np.flatnonzero(inside_half_open(reference_points, bounds))
    reference, selected = voxel_reference(reference_points[reference_membership], reference_voxel_size, voxel_origin)
    vertices, triangles = clip_mesh_to_box(vertices, triangles, bounds)
    samples, surface_area = sample_surface(vertices, triangles, spacing, seed)
    # Half-open membership also removes any floating-point sample on an excluded edge.
    samples = samples[inside_half_open(samples, bounds)]
    if not len(reference):
        status = "NOT_ASSESSED_REFERENCE_ABSENT"
        pred_to_ref = np.full(len(samples), np.nan)
        ref_to_mesh = np.empty(0)
    elif not len(samples):
        status = "RECONSTRUCTION_FAILURE"
        pred_to_ref = np.empty(0)
        ref_to_mesh = np.full(len(reference), np.inf)
    else:
        status = "ASSESSED_DEVELOPMENT_ONLY"
        pred_to_ref = cKDTree(reference).query(samples, workers=1)[0]
        ref_to_mesh = points_to_triangle_surface(reference, vertices, triangles)
    threshold_rows = []
    for threshold in thresholds:
        if not np.isfinite(threshold) or threshold <= 0:
            raise ValueError("Distance threshold must be positive")
        if not len(reference):
            precision = recall = f1 = None
        else:
            precision = float(np.mean(pred_to_ref < threshold)) if len(pred_to_ref) else 0.0
            recall = float(np.mean(ref_to_mesh < threshold))
            f1 = 2 * precision * recall / (precision + recall) if precision + recall > 0 else 0.0
        threshold_rows.append({"threshold_m": float(threshold), "precision": precision, "recall": recall, "f1": f1})
    metrics = {"scientific_verdict": None, "status": status, "bounds_half_open": bounds.tolist(),
               "seed": seed, "surface_sample_spacing_m": spacing, "surface_area_m2": surface_area,
               "surface_samples": len(samples), "reference_points_in_roi": len(reference_membership),
               "reference_voxel_size_m": reference_voxel_size, "reference_voxel_origin": list(voxel_origin),
               "reference_points_after_voxel": len(reference), "bvh_coordinate_dtype": "float32_local_metric",
               "reference_coverage_verified_by_this_function": False,
               "prediction_distance_interpretation": "proximity to observed reference points; reference absence within ROI must be assessed separately",
               "prediction_to_reference_point": distance_statistics(pred_to_ref),
               "reference_to_prediction_triangle": distance_statistics(ref_to_mesh), "thresholds": threshold_rows,
               "empty_prediction_precision_convention": "zero when reference exists; F1 zero",
               "xy_support": xy_support_diagnostic(samples, reference, xy_cell_size, np.asarray(voxel_origin)[:2])}
    arrays = {"prediction_surface_samples": samples, "reference_points": reference,
              "reference_original_indices": reference_membership[selected],
              "prediction_to_reference_distance": pred_to_ref, "reference_to_triangle_distance": ref_to_mesh,
              "clipped_vertices": vertices, "clipped_triangles": triangles}
    return metrics, arrays


def save_distance_arrays(path, arrays):
    """Write a fresh NPZ; never overwrite an earlier evaluation result."""
    with Path(path).open("xb") as stream:
        np.savez_compressed(stream, **arrays)
