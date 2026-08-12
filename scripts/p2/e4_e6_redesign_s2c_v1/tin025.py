"""DSM TIN builder with area-normalized density gate (S2c, TIN 0.25 m).

Identical to the frozen S1 builder except the density gate: cell point counts
are converted to points-per-m2 so the gate is invariant to cell size
(`clip((density_per_m2 - 4) / 20, 0, 1)`, equivalent to the sealed 0.5 m-cell
formula at its own scale). Void fill and planarity are unchanged.
"""
from __future__ import annotations

import numpy as np
import open3d as o3d
from scipy.ndimage import label, uniform_filter


def dsm_tin(points_local: np.ndarray, cell_m: float):
    xy_min = points_local[:, :2].min(axis=0)
    cols = np.floor((points_local[:, 0] - xy_min[0]) / cell_m).astype(np.int64)
    rows = np.floor((points_local[:, 1] - xy_min[1]) / cell_m).astype(np.int64)
    n_cols = int(cols.max()) + 1
    n_rows = int(rows.max()) + 1
    flat = rows * n_cols + cols
    top = np.full(n_rows * n_cols, -np.inf, dtype=np.float64)
    np.maximum.at(top, flat, points_local[:, 2])
    count = np.bincount(flat, minlength=n_rows * n_cols).astype(np.float64)
    z_sum = np.bincount(flat, weights=points_local[:, 2], minlength=n_rows * n_cols)
    z_sq = np.bincount(flat, weights=points_local[:, 2] ** 2, minlength=n_rows * n_cols)
    with np.errstate(invalid="ignore", divide="ignore"):
        z_var = np.maximum(z_sq / np.maximum(count, 1) - (z_sum / np.maximum(count, 1)) ** 2, 0.0)
    z_std = np.sqrt(z_var)
    top = top.reshape(n_rows, n_cols)
    count = count.reshape(n_rows, n_cols)
    z_std = z_std.reshape(n_rows, n_cols)
    empty = ~np.isfinite(top)
    labels, _ = label(empty)
    border = np.unique(np.concatenate([labels[0], labels[-1], labels[:, 0], labels[:, -1]]))
    interior = empty & ~np.isin(labels, border[border > 0])
    grid = np.where(np.isfinite(top), top, 0.0)
    mask = np.isfinite(top).astype(np.float64)
    for _ in range(400):
        if not interior.any():
            break
        neighbor_sum = uniform_filter(grid * mask, size=3) * 9.0
        neighbor_count = uniform_filter(mask, size=3) * 9.0
        fill = interior & (neighbor_count >= 3.0)
        if not fill.any():
            break
        grid[fill] = neighbor_sum[fill] / neighbor_count[fill]
        mask[fill] = 1.0
        interior[fill] = False
    top = np.where(mask > 0, grid, -np.inf)
    valid = np.isfinite(top)
    index = np.full(top.shape, -1, dtype=np.int64)
    vertex_count = int(valid.sum())
    index[valid] = np.arange(vertex_count)
    grid_rows, grid_cols = np.nonzero(valid)
    vertices = np.column_stack((
        xy_min[0] + (grid_cols + 0.5) * cell_m,
        xy_min[1] + (grid_rows + 0.5) * cell_m,
        top[valid],
    ))
    density_per_m2 = count[valid] / (cell_m * cell_m)
    vertex_density = np.clip((density_per_m2 - 4.0) / 20.0, 0.0, 1.0)
    vertex_planarity = np.exp(-z_std[valid] / 0.2)
    a, b = index[:-1, :-1], index[:-1, 1:]
    c, d = index[1:, :-1], index[1:, 1:]
    quad = (a >= 0) & (b >= 0) & (c >= 0) & (d >= 0)
    triangles = np.concatenate([
        np.column_stack((a[quad], b[quad], c[quad])),
        np.column_stack((b[quad], d[quad], c[quad])),
    ])
    face_density = vertex_density[triangles].min(axis=1).astype(np.float32)
    face_planarity = vertex_planarity[triangles].min(axis=1).astype(np.float32)
    legacy = o3d.geometry.TriangleMesh(
        o3d.utility.Vector3dVector(vertices),
        o3d.utility.Vector3iVector(triangles.astype(np.int32)),
    )
    scene = o3d.t.geometry.RaycastingScene()
    scene.add_triangles(o3d.t.geometry.TriangleMesh.from_legacy(legacy))
    return scene, face_density, face_planarity, vertex_count, int(len(triangles))
