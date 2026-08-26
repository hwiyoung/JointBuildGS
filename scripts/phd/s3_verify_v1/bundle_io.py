#!/usr/bin/env python3
"""phd_s3_verify_s1_bundle_v1 IO + plane-geometry helpers (S1 bundle writer)."""
from __future__ import annotations

import numpy as np

PLY_FMT = {"float": ("f", 4), "uchar": ("B", 1), "double": ("d", 8),
           "int": ("i", 4), "uint": ("I", 4)}


def read_ply_points(path):
    """Binary LE PLY -> (xyz f64, rgb u8 | None, classification i32 | None)."""
    with open(path, "rb") as f:
        header = b""
        while not header.endswith(b"end_header\n"):
            header += f.readline()
        count, props = 0, []
        for ln in header.decode().splitlines():
            if ln.startswith("element vertex"):
                count = int(ln.split()[-1])
            elif ln.startswith("property"):
                _, typ, name = ln.split()
                props.append((typ, name))
        size = sum(PLY_FMT[t][1] for t, _ in props)
        raw = np.frombuffer(f.read(count * size), dtype=np.dtype(
            [(nm, "<" + PLY_FMT[t][0]) for t, nm in props]))
    xyz = np.stack([raw["x"], raw["y"], raw["z"]], axis=1).astype(np.float64)
    names = raw.dtype.names
    rgb = (np.stack([raw["red"], raw["green"], raw["blue"]], axis=1)
           if "red" in names else None)
    cls = raw["classification"].astype(np.int32) if "classification" in names else None
    return xyz, rgb, cls


def write_s1_points_ply(path, xyz, rgb, source):
    """Contract PLY: x,y,z float32 + red,green,blue uchar + source uchar."""
    n = len(xyz)
    rec = np.empty(n, dtype=[("x", "<f4"), ("y", "<f4"), ("z", "<f4"),
                             ("red", "u1"), ("green", "u1"), ("blue", "u1"),
                             ("source", "u1")])
    rec["x"], rec["y"], rec["z"] = xyz[:, 0], xyz[:, 1], xyz[:, 2]
    rec["red"], rec["green"], rec["blue"] = rgb[:, 0], rgb[:, 1], rgb[:, 2]
    rec["source"] = source
    header = ("ply\nformat binary_little_endian 1.0\n"
              f"element vertex {n}\n"
              "property float x\nproperty float y\nproperty float z\n"
              "property uchar red\nproperty uchar green\nproperty uchar blue\n"
              "property uchar source\nend_header\n")
    with open(path, "wb") as f:
        f.write(header.encode())
        f.write(rec.tobytes())


def thin_stride(n, max_points):
    stride = max(1, int(np.ceil(n / max_points)))
    return np.arange(0, n, stride), stride


def unit_plane(n, d):
    n = np.asarray(n, dtype=np.float64)
    ln = float(np.linalg.norm(n))
    return n / ln, float(d) / ln


def plane_frame(ring3d, n):
    """(origin, u, w): in-plane 2D frame from a 3D support ring."""
    ring3d = np.asarray(ring3d, dtype=np.float64)
    o = ring3d[0]
    for v in ring3d[1:]:
        e = v - o
        e = e - np.dot(e, n) * n
        ln = np.linalg.norm(e)
        if ln > 1e-6:
            u = e / ln
            return o, u, np.cross(n, u)
    raise ValueError("degenerate support ring")


def lift_ring_xy(ring_xy, n, d):
    """XY ring -> 3D ring on a non-vertical plane n.p=d."""
    ring_xy = np.asarray(ring_xy, dtype=np.float64)[:, :2]
    z = (d - ring_xy @ n[:2]) / n[2]
    return np.c_[ring_xy, z]


def vertical_rect(ring_xy, n, d, z0, z1):
    """XY support (corridor/segment) -> in-plane rectangle on a vertical plane."""
    nxy = np.asarray(n[:2], dtype=np.float64)
    nxy = nxy / np.linalg.norm(nxy)
    e = np.array([-nxy[1], nxy[0]])
    p0 = d * nxy
    t = (np.asarray(ring_xy, dtype=np.float64)[:, :2] - p0) @ e
    a, b = p0 + t.min() * e, p0 + t.max() * e
    return np.array([[a[0], a[1], z0], [b[0], b[1], z0],
                     [b[0], b[1], z1], [a[0], a[1], z1]])


def plane_inliers(xyz, mvs_mask, n, d, ring3d, tau_m, buffer_m):
    """Registered inlier rule (contract): source==0 points with
    |signed point-plane distance| <= tau_m AND in-plane projection inside the
    support polygon buffered by buffer_m (plane-frame 2D)."""
    import shapely
    from shapely.geometry import Polygon
    dist = xyz @ n - d
    idx = np.nonzero(mvs_mask & (np.abs(dist) <= tau_m))[0]
    if len(idx) == 0:
        return idx, dist
    o, u, w = plane_frame(ring3d, n)
    ring3d = np.asarray(ring3d, dtype=np.float64)
    ruv = np.stack([(ring3d - o) @ u, (ring3d - o) @ w], axis=1)
    if len(ruv) < 3:
        return idx[:0], dist
    poly = Polygon(ruv)
    if not poly.is_valid:
        poly = poly.buffer(0)
    poly = poly.buffer(buffer_m)
    p = xyz[idx] - o
    inside = shapely.contains_xy(poly, p @ u, p @ w)
    return idx[inside], dist
