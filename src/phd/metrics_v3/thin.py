"""Thinning of GT points (PHD-MAIN-STAGE1-v1 3.4): one point per 0.1 m cell, the one nearest the cell centre (ties: lowest index)."""
import numpy as np


def keep_nearest(coords, cell=0.1, group=None):
    """coords (n, 2): the cell coordinates (roof: x, y; wall: s along the face, z); group (n,) optional: cells are separate per group
    (e.g. the wall surface). Returns a boolean keep mask (one True per occupied cell)."""
    c = np.asarray(coords, np.float64)
    n = len(c)
    if n == 0:
        return np.zeros(0, bool)
    q = np.floor(c / cell).astype(np.int64)
    centre = (q + 0.5) * cell
    d2 = ((c - centre) ** 2).sum(1)
    g = np.zeros(n, np.int64) if group is None else np.asarray(group, np.int64)
    order = np.lexsort((np.arange(n), d2, q[:, 1], q[:, 0], g))      # by cell, then distance, then index
    gs, q0, q1 = g[order], q[order, 0], q[order, 1]
    first = np.ones(n, bool)
    first[1:] = (gs[1:] != gs[:-1]) | (q0[1:] != q0[:-1]) | (q1[1:] != q1[:-1])
    keep = np.zeros(n, bool)
    keep[order[first]] = True
    return keep


def wall_coords(X, normal):
    """(s, z) on the wall plane: s = horizontal coordinate along the face (unit tangent perpendicular to the normal's horizontal part)."""
    X = np.asarray(X, np.float64)
    nh = np.asarray(normal, np.float64)[..., :2]
    nh = nh / np.maximum(np.linalg.norm(nh, axis=-1, keepdims=True), 1e-12)
    t = np.stack([-nh[..., 1], nh[..., 0]], -1)
    s = (X[:, :2] * t).sum(-1)
    return np.column_stack([s, X[:, 2]])
