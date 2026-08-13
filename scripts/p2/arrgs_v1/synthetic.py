#!/usr/bin/env python3
"""ARRGS X0 synthetic scenes: GT surfaces -> textured GT gaussians -> target
renders from a camera ring, plus over-complete candidate planes (GT + distractors)
and GT inside-functions for occupancy accuracy scoring.

Everything is deterministic (fixed seeds/spacings); no dataset dependency.
"""
from __future__ import annotations

import numpy as np

H, W = 600, 800
FX = 800.0


def look_at(pos, target, up=(0, 0, 1.0)):
    """OpenCV world-to-camera 4x4."""
    pos = np.asarray(pos, dtype=np.float64)
    fwd = np.asarray(target, dtype=np.float64) - pos
    fwd /= np.linalg.norm(fwd)
    right = np.cross(fwd, np.asarray(up, dtype=np.float64))
    right /= np.linalg.norm(right)
    down = np.cross(fwd, right)
    R = np.stack([right, down, fwd], axis=0)
    T = np.eye(4)
    T[:3, :3] = R
    T[:3, 3] = -R @ pos
    return T


def camera_ring(center, radius=32.0, height=26.0, count=16):
    """Two-elevation ring: high (nadir-ish) + low (oblique — eave/wall parallax).
    X0 lesson: a single high ring is near-blind to thin eave slivers."""
    mats, Ks = [], []
    K = np.array([[FX, 0, W / 2], [0, FX, H / 2], [0, 0, 1.0]])
    rings = [(radius, height, count), (radius + 8.0, 11.0, count // 2)]
    for r, hgt, cnt in rings:
        for i in range(cnt):
            a = 2 * np.pi * (i + 0.5 * (hgt < height)) / cnt
            pos = np.array([center[0] + r * np.cos(a),
                            center[1] + r * np.sin(a), hgt])
            mats.append(look_at(pos, center))
            Ks.append(K)
    return np.stack(mats), np.stack(Ks)


def _face_frame(n):
    n = np.asarray(n, dtype=np.float64)
    n = n / np.linalg.norm(n)
    ref = np.array([1.0, 0, 0]) if abs(n[0]) < 0.9 else np.array([0.0, 1, 0])
    e1 = ref - np.dot(ref, n) * n
    e1 /= np.linalg.norm(e1)
    return n, e1, np.cross(n, e1)


def _sample_poly(poly3d, n, spacing=0.18):
    """Grid sample points on a 3D planar polygon."""
    from shapely.geometry import Polygon, Point
    n, e1, e2 = _face_frame(n)
    origin = np.asarray(poly3d[0], dtype=np.float64)
    uv = np.stack([(np.asarray(poly3d) - origin) @ e1,
                   (np.asarray(poly3d) - origin) @ e2], axis=1)
    poly = Polygon(uv)
    minx, miny, maxx, maxy = poly.bounds
    pts, uvs = [], []
    for x in np.arange(minx + spacing / 2, maxx, spacing):
        for y in np.arange(miny + spacing / 2, maxy, spacing):
            if poly.contains(Point(x, y)):
                pts.append(origin + x * e1 + y * e2)
                uvs.append((x, y))
    return np.asarray(pts), np.asarray(uvs), (n, e1, e2)


def gt_surfaces(kind):
    """Returns list of (poly3d, n, base_rgb) fully describing the GT building
    + surrounding ground, and the solid inside-function."""
    fp = np.array([(0, 0), (20, 0), (20, 12), (0, 12)], dtype=np.float64)
    ground_ring = np.array([(-10, -10), (30, -10), (30, 22), (-10, 22)], dtype=np.float64)
    surfaces = []
    # surrounding ground (context only; outside model domain)
    surfaces.append((np.c_[ground_ring, np.zeros(4)], [0, 0, 1.0], (0.35, 0.45, 0.30)))
    if kind == "box":
        zr = 8.0
        roof = np.c_[fp, np.full(4, zr)]
        surfaces.append((roof, [0, 0, 1.0], (0.75, 0.45, 0.35)))
        walls_z = [(0.0, zr)] * 4
        def inside(p):
            return (0 <= p[0] <= 20) and (0 <= p[1] <= 12) and (0 <= p[2] <= zr)
        wall_tops = lambda x, y: zr
    elif kind == "gable":
        eave, ridge = 6.0, 10.0
        # ridge along x at y=6
        def wall_tops(x, y):
            return eave + (ridge - eave) * (1 - abs(y - 6.0) / 6.0)
        roofL = np.array([(0, 0, eave), (20, 0, eave), (20, 6, ridge), (0, 6, ridge)])
        roofR = np.array([(0, 6, ridge), (20, 6, ridge), (20, 12, eave), (0, 12, eave)])
        c = 1.0 / np.hypot(6, ridge - eave)
        nL = np.array([0.0, -(ridge - eave) * c, 6 * c]); nL /= np.linalg.norm(nL)
        nR = np.array([0.0, (ridge - eave) * c, 6 * c]); nR /= np.linalg.norm(nR)
        surfaces.append((roofL, nL.tolist(), (0.75, 0.45, 0.35)))
        surfaces.append((roofR, nR.tolist(), (0.70, 0.40, 0.32)))
        def inside(p):
            if not (0 <= p[0] <= 20 and 0 <= p[1] <= 12):
                return False
            return 0 <= p[2] <= wall_tops(p[0], p[1])
    else:
        raise ValueError(kind)
    # walls (gable ends included as polygons with apex)
    edges = [((0, 0), (20, 0), [0, -1, 0]), ((20, 0), (20, 12), [1, 0, 0]),
             ((20, 12), (0, 12), [0, 1, 0]), ((0, 12), (0, 0), [-1, 0, 0])]
    for (a, b, n) in edges:
        za, zb = wall_tops(*a), wall_tops(*b)
        poly = [(*a, 0.0), (*b, 0.0), (*b, zb)]
        # gable end walls need the apex point when the top varies
        if kind == "gable" and a[0] == b[0]:  # x=const ends
            apex = (a[0], 6.0, 10.0)
            poly = [(*a, 0.0), (*b, 0.0), (*b, zb), apex, (*a, za)]
        else:
            poly = [(*a, 0.0), (*b, 0.0), (*b, zb), (*a, za)]
        surfaces.append((np.asarray(poly, dtype=np.float64), n, (0.72, 0.68, 0.60)))
    return surfaces, inside, fp


def gt_gaussians(kind, spacing=0.18):
    """Textured GT gaussian soup for target rendering."""
    surfaces, inside, fp = gt_surfaces(kind)
    means, normals, colors = [], [], []
    for poly3d, n, base in surfaces:
        pts, uvs, (nn, e1, e2) = _sample_poly(poly3d, n, spacing)
        if len(pts) == 0:
            continue
        checker = ((np.floor(uvs[:, 0] / 1.0) + np.floor(uvs[:, 1] / 1.0)) % 2) * 0.22
        rng = np.random.default_rng(0)
        noise = rng.normal(0, 0.03, size=(len(pts), 3))
        col = np.clip(np.asarray(base)[None, :] * (0.85 + checker[:, None]) + noise, 0, 1)
        means.append(pts)
        normals.append(np.tile(nn, (len(pts), 1)))
        colors.append(col)
    return (np.concatenate(means), np.concatenate(normals),
            np.concatenate(colors), inside, fp, spacing)


def candidate_planes(kind, perturb=0.0, seed=0):
    """Over-complete candidates: GT planes + distractors. perturb: deg/m jitter."""
    fp = [(0, 0), (20, 0), (20, 12), (0, 12)]
    planes = []
    def add(pid, n, d, source):
        planes.append({"id": pid, "n": list(np.asarray(n, dtype=float)),
                       "d": float(d), "source": source, "prior": None})
    if kind == "box":
        add("roof_flat", [0, 0, 1], 8.0, "gt")
        add("distractor_low", [0, 0, 1], 6.5, "distractor")
        s = np.sin(np.deg2rad(10)); c = np.cos(np.deg2rad(10))
        add("distractor_tilt", [0, -s, c], c * 8.5 - s * 6.0, "distractor")
    else:
        c = 1.0 / np.hypot(6, 4.0)
        nL = np.array([0.0, -4 * c, 6 * c]); nL /= np.linalg.norm(nL)
        nR = np.array([0.0, 4 * c, 6 * c]); nR /= np.linalg.norm(nR)
        add("roofL", nL, float(nL @ np.array([0, 0, 6.0])), "gt")
        add("roofR", nR, float(nR @ np.array([0, 12, 6.0])), "gt")
        add("distractor_flat", [0, 0, 1], 7.0, "distractor")
        add("distractor_offset", nL, float(nL @ np.array([0, 0, 6.0])) + 0.8, "distractor")
    for i, (a, b) in enumerate(zip(fp, fp[1:] + fp[:1])):
        e = np.array([b[0] - a[0], b[1] - a[1], 0.0])
        n = np.array([e[1], -e[0], 0.0])
        n /= np.linalg.norm(n)
        add(f"wall{i}", n, float(n[:2] @ np.asarray(a)), "footprint")
    if perturb > 0:
        rng = np.random.default_rng(seed)
        for p in planes:
            if p["source"] == "footprint":
                continue
            ang = np.deg2rad(perturb)
            ax = rng.normal(size=3); ax /= np.linalg.norm(ax)
            n = np.asarray(p["n"])
            n = n * np.cos(ang) + np.cross(ax, n) * np.sin(ang)
            p["n"] = list(n / np.linalg.norm(n))
            p["d"] = p["d"] + rng.uniform(-perturb * 0.1, perturb * 0.1)
    return planes, fp
