#!/usr/bin/env python3
"""ARRGS S2: plane arrangement over a footprint prism.

Cuts an axis-aligned domain box (footprint bbox + margin, ground..top) by
candidate planes into convex cells, extracts shared facets between adjacent
cells, and marks cells outside the footprint polygon as fixed-empty (o=0).

Conventions
- Halfspace: n·x <= d (unit n).
- Domain boundary facets are adjacent to a virtual outside cell with o=0
  fixed, so the domain bottom (at ground elevation) yields GroundSurface
  faces automatically when interior cells harden to solid.
- All geometry is float64 numpy; no torch here (S2 is deterministic
  construction, not a decision stage).
"""
from __future__ import annotations

import json
import numpy as np
from scipy.optimize import linprog
from scipy.spatial import ConvexHull, HalfspaceIntersection
from shapely.geometry import Polygon, Point

TOL = 1e-6
FACE_MIN_AREA = 1e-3  # m^2


def _unit(v):
    v = np.asarray(v, dtype=np.float64)
    return v / np.linalg.norm(v)


def chebyshev_center(normals, offsets):
    """Interior point of {n·x <= d} via Chebyshev center LP. Returns None if empty/degenerate."""
    normals = np.asarray(normals, dtype=np.float64)
    offsets = np.asarray(offsets, dtype=np.float64)
    m = normals.shape[0]
    # maximize r  s.t.  n·x + r <= d   (n unit)
    c = np.zeros(4)
    c[3] = -1.0
    A = np.hstack([normals, np.ones((m, 1))])
    res = linprog(c, A_ub=A, b_ub=offsets, bounds=[(None, None)] * 3 + [(0, None)],
                  method="highs")
    if not res.success or res.x[3] < 1e-9:
        return None
    return res.x[:3]


def cell_vertices(normals, offsets):
    """Vertex enumeration for {n·x <= d}. Returns (V,3) or None if empty."""
    ip = chebyshev_center(normals, offsets)
    if ip is None:
        return None
    hs = np.hstack([normals, -np.asarray(offsets, dtype=np.float64)[:, None]])
    try:
        hi = HalfspaceIntersection(hs, ip)
    except Exception:
        return None
    verts = hi.intersections
    # dedupe
    if len(verts) == 0:
        return None
    keep = []
    for v in verts:
        if not any(np.linalg.norm(v - k) < 1e-5 for k in keep):
            keep.append(v)
    return np.asarray(keep)


class Cell:
    __slots__ = ("normals", "offsets", "plane_ids", "verts", "idx", "fixed", "centroid")

    def __init__(self, normals, offsets, plane_ids, verts):
        self.normals = np.asarray(normals, dtype=np.float64)
        self.offsets = np.asarray(offsets, dtype=np.float64)
        self.plane_ids = list(plane_ids)
        self.verts = verts
        self.idx = -1
        self.fixed = None  # None=trainable, 0.0=fixed empty
        self.centroid = verts.mean(axis=0)

    def split(self, n, d, plane_id):
        """Split by plane n·x = d. Returns (below, above) — either may be None."""
        s = self.verts @ n - d
        if s.max() < TOL:   # entirely below
            return self, None
        if s.min() > -TOL:  # entirely above
            return None, self
        below = self._child(np.vstack([self.normals, n]), np.append(self.offsets, d),
                            self.plane_ids + [plane_id])
        above = self._child(np.vstack([self.normals, -n]), np.append(self.offsets, -d),
                            self.plane_ids + [plane_id])
        # degenerate split guard: keep original if a side vanished
        if below is None:
            return None, (above if above is not None else self)
        if above is None:
            return below, None
        return below, above

    @staticmethod
    def _child(normals, offsets, plane_ids):
        verts = cell_vertices(normals, offsets)
        if verts is None or len(verts) < 4:
            return None
        c = Cell(normals, offsets, plane_ids, verts)
        return c

    def facet_on(self, n, d, frame):
        """Vertices of this cell lying on plane n·x=d, hull-ordered in the SHARED
        plane frame (origin,e1,e2). Returns (poly3d (M,3), poly2d (M,2)) or None."""
        s = np.abs(self.verts @ n - d)
        pts = self.verts[s < 1e-4]
        if len(pts) < 3:
            return None
        origin, e1, e2 = frame
        uv = np.stack([(pts - origin) @ e1, (pts - origin) @ e2], axis=1)
        try:
            hull = ConvexHull(uv)
        except Exception:
            return None
        order = hull.vertices
        return pts[order], uv[order]


def plane_frame(n, d):
    """Canonical shared 2D frame on plane n·x=d."""
    n = _unit(n)
    origin = n * d
    ref = np.array([1.0, 0.0, 0.0]) if abs(n[0]) < 0.9 else np.array([0.0, 1.0, 0.0])
    e1 = _unit(ref - np.dot(ref, n) * n)
    e2 = np.cross(n, e1)
    return origin, e1, e2


def build_arrangement(planes, footprint_xy, ground_z, top_z, margin=1.0):
    """planes: list of {id, n:[3], d, source, prior:{n0,d0}|None}
    footprint_xy: (M,2) polygon (world/scene frame XY)
    Returns arrangement dict (cells, faces) — see module docstring.
    """
    fp = Polygon(footprint_xy)
    if not fp.is_valid:
        fp = fp.buffer(0)
    minx, miny, maxx, maxy = fp.bounds
    minx -= margin; miny -= margin; maxx += margin; maxy += margin
    # domain box halfspaces (id 'domain:*' — adjacent to virtual outside o=0)
    dom_n = np.array([[1, 0, 0], [-1, 0, 0], [0, 1, 0], [0, -1, 0], [0, 0, 1], [0, 0, -1]],
                     dtype=np.float64)
    dom_d = np.array([maxx, -minx, maxy, -miny, top_z, -ground_z])
    dom_ids = [f"domain:{k}" for k in ("x+", "x-", "y+", "y-", "z+", "z-")]
    root_verts = cell_vertices(dom_n, dom_d)
    cells = [Cell(dom_n, dom_d, dom_ids, root_verts)]

    for p in planes:
        n = _unit(p["n"]); d = float(p["d"])
        if not (np.isfinite(n).all() and np.isfinite(d)):
            raise ValueError(f"non-finite plane {p['id']}: n={p['n']} d={p['d']}")
        nxt = []
        for c in cells:
            below, above = c.split(n, d, p["id"])
            for side in (below, above):
                if side is not None:
                    nxt.append(side)
        cells = nxt

    # mark cells: outside footprint XY -> fixed empty
    for i, c in enumerate(cells):
        c.idx = i
        if not fp.contains(Point(c.centroid[0], c.centroid[1])):
            c.fixed = 0.0

    # facets grouped by plane (candidate planes + domain boundary)
    plane_map = {p["id"]: (_unit(p["n"]), float(p["d"])) for p in planes}
    for pid, n, d in zip(dom_ids, dom_n, dom_d):
        plane_map[pid] = (_unit(n), float(d))

    faces = []
    by_plane = {}
    for c in cells:
        for pid in set(c.plane_ids):
            by_plane.setdefault(pid, []).append(c)

    for pid, group in by_plane.items():
        n, d = plane_map[pid]
        frame = plane_frame(n, d)
        origin, e1, e2 = frame
        entries = []
        for c in group:
            f = c.facet_on(n, d, frame)
            if f is None:
                continue
            poly3d, uv = f
            side = "below" if np.dot(c.centroid, n) - d < 0 else "above"
            entries.append((c, Polygon(uv), poly3d, side))
        # pair below/above cells on this plane (shared frame -> real overlaps only)
        below = [e for e in entries if e[3] == "below"]
        above = [e for e in entries if e[3] == "above"]
        used_pairs = set()
        for cb, pb, v3b, _ in below:
            for ca, pa, _, _ in above:
                inter = pb.intersection(pa)
                if inter.is_empty or getattr(inter, "area", 0.0) < FACE_MIN_AREA:
                    continue
                key = (cb.idx, ca.idx)
                if key in used_pairs:
                    continue
                used_pairs.add(key)
                if inter.geom_type != "Polygon":
                    inter = max(list(getattr(inter, "geoms", [])) or [None],
                                key=lambda g: g.area if g is not None else -1)
                    if inter is None or inter.area < FACE_MIN_AREA:
                        continue
                poly2d = np.asarray(inter.exterior.coords)[:-1]
                poly3d = origin[None, :] + poly2d[:, :1] * e1[None, :] + poly2d[:, 1:2] * e2[None, :]
                faces.append({"plane_id": pid, "cell_a": cb.idx, "cell_b": ca.idx,
                              "n": n.tolist(), "d": d, "poly3d": poly3d.tolist(),
                              "area": float(inter.area)})
        # domain boundary: facets vs virtual outside (cell_b = -1)
        if pid.startswith("domain:"):
            for c, poly, v3, side in entries:
                faces.append({"plane_id": pid, "cell_a": c.idx, "cell_b": -1,
                              "n": n.tolist(), "d": d, "poly3d": v3.tolist(),
                              "area": float(poly.area)})

    cells_out = [{"idx": c.idx, "centroid": c.centroid.tolist(),
                  "verts": c.verts.tolist(), "fixed": c.fixed,
                  "volume": _cell_volume(c)} for c in cells]
    return {"cells": cells_out, "faces": [f for f in faces if f["area"] >= FACE_MIN_AREA],
            "footprint_xy": np.asarray(footprint_xy).tolist(),
            "ground_z": ground_z, "top_z": top_z}


def _cell_volume(c):
    try:
        return float(ConvexHull(c.verts).volume)
    except Exception:
        return 0.0


def label_cells_by_solid(arr, inside_fn):
    """Ground-truth cell labels for synthetic scenes: inside_fn(xyz)->bool."""
    return [1.0 if inside_fn(np.asarray(c["centroid"])) else 0.0 for c in arr["cells"]]


if __name__ == "__main__":
    # self-test: gable prism
    fp = [(0, 0), (20, 0), (20, 12), (0, 12)]
    planes = [
        {"id": "roofL", "n": [0.0, -0.5547, 0.8321], "d": 0.8321 * 6.0, "source": "gt"},
        {"id": "roofR", "n": [0.0, 0.5547, 0.8321], "d": 0.5547 * 12 + 0.8321 * 6.0, "source": "gt"},
        {"id": "w0", "n": [0, -1, 0], "d": 0.0, "source": "fp"},
        {"id": "w1", "n": [1, 0, 0], "d": 20.0, "source": "fp"},
        {"id": "w2", "n": [0, 1, 0], "d": 12.0, "source": "fp"},
        {"id": "w3", "n": [-1, 0, 0], "d": 0.0, "source": "fp"},
        {"id": "distractor_flat", "n": [0, 0, 1], "d": 7.0, "source": "distractor"},
    ]
    arr = build_arrangement(planes, fp, ground_z=0.0, top_z=13.0, margin=1.5)
    n_free = sum(1 for c in arr["cells"] if c["fixed"] is None)
    print(json.dumps({"cells": len(arr["cells"]), "free_cells": n_free,
                      "faces": len(arr["faces"]),
                      "boundary_faces": sum(1 for f in arr["faces"] if f["cell_b"] == -1)}))
