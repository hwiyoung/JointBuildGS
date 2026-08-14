#!/usr/bin/env python3
"""S1R: candidate planes from the sealed Roofer outputs (E7/E8 arm OBJs).

Reuses the sealed-chain Roofer LoD2 models as the plane detector:
  prior      — E7 (ALS-only) roof faces  -> plane + support polygon
  mvs_union  — E8 (E2∪ALS) roof faces not already in E7 (current-evidence increment)

Each candidate carries a SUPPORT REGION (XY polygon union of its faces,
buffered): the arrangement still cuts with infinite planes, but renderable
facets/seeds are restricted to the support — this removes the pierce-facet
seeding that plagued v1 (B022 59% wall/pierce budget).

Verdict (input-side only; E1 stays evaluation-only): explained fraction of the
ALS upper-envelope points + largest coherent unexplained region inside the
footprint.
"""
from __future__ import annotations

import numpy as np
from shapely.geometry import MultiPoint, Point, Polygon
from shapely.ops import unary_union

ANG_MERGE = 3.0      # deg: faces on the same plane
D_MERGE = 0.15       # m
MIN_SUPPORT = 4.0    # m^2
MAX_PLANES = 26      # sawtooth roofs need many parallel planes (linear cell cost)
NZ_MIN = 0.10        # allow steep roofs; walls come from the footprint


def parse_obj(path):
    verts, tris = [], []
    for ln in open(path):
        t = ln.split()
        if not t:
            continue
        if t[0] == "v":
            verts.append([float(x) for x in t[1:4]])
        elif t[0] == "f":
            tris.append([int(x.split("/")[0]) - 1 for x in t[1:4]])
    return np.asarray(verts), np.asarray(tris, dtype=int)


def roof_planes_from_obj(path, nz_min=NZ_MIN):
    verts, tris = parse_obj(path)
    if len(tris) == 0:
        return []
    planes = []  # each: {n, d, area, tris_xy:[Polygon]}
    for tri in tris:
        a, b, c = verts[tri]
        n = np.cross(b - a, c - a)
        ln = np.linalg.norm(n)
        if ln < 1e-9:
            continue
        n = n / ln
        if n[2] < 0:
            n = -n
        if n[2] < nz_min:      # wall-like -> footprint supplies these
            continue
        d = float(n @ a)
        area = 0.5 * ln
        poly = Polygon([(a[0], a[1]), (b[0], b[1]), (c[0], c[1])])
        if not poly.is_valid or poly.area < 1e-6:
            poly = None
        hit = None
        for p in planes:
            cos = float(np.clip(p["n"] @ n, -1, 1))
            if np.degrees(np.arccos(abs(cos))) < ANG_MERGE and abs(p["d"] - d) < D_MERGE:
                hit = p
                break
        if hit is None:
            planes.append({"n": n, "d": d, "area": area,
                           "tris_xy": [poly] if poly else []})
        else:
            w = hit["area"] + area
            hit["n"] = hit["n"] * (hit["area"] / w) + n * (area / w)
            hit["n"] /= np.linalg.norm(hit["n"])
            hit["d"] = hit["d"] * (hit["area"] / w) + d * (area / w)
            hit["area"] = w
            if poly is not None:
                hit["tris_xy"].append(poly)
    out = []
    for p in planes:
        if p["area"] < MIN_SUPPORT or not p["tris_xy"]:
            continue
        sup = unary_union(p["tris_xy"]).buffer(0.8).simplify(0.3)
        out.append({"n": p["n"], "d": p["d"], "area": float(p["area"]),
                    "support": sup})
    out.sort(key=lambda p: -p["area"])
    return out[:MAX_PLANES]


def upper_envelope(pts, grid=0.5, band=0.4):
    """Column-top skin: per XY cell keep points within `band` of the cell max z.
    This is the surface a roof-plane candidate set is expected to explain —
    facade curtains collapse to their top edge instead of polluting the gate."""
    if len(pts) == 0:
        return pts
    ij = np.floor(pts[:, :2] / grid).astype(int)
    import collections
    top = collections.defaultdict(lambda: -1e9)
    for (i, j), z in zip(map(tuple, ij), pts[:, 2]):
        if z > top[(i, j)]:
            top[(i, j)] = z
    keep = np.array([pts[k, 2] > top[tuple(ij[k])] - band for k in range(len(pts))])
    out = pts[keep]
    return out[::max(1, len(out) // 60000)]


def _support_coords(sup):
    geoms = getattr(sup, "geoms", [sup])
    return [np.asarray(g.exterior.coords)[:-1].tolist() for g in geoms
            if g.geom_type == "Polygon" and g.area > 0.5]


def candidates_from_roofer(e7_obj, e8_obj, delta_shift=None):
    """delta_shift: X3 injection applied to the PRIOR (E7) planes/supports."""
    e7 = roof_planes_from_obj(e7_obj) if e7_obj else []
    e8 = roof_planes_from_obj(e8_obj) if e8_obj else []
    cands = []
    if delta_shift is not None and np.any(delta_shift):
        s = np.asarray(delta_shift, dtype=float)
        for p in e7:
            p["d"] = float(p["d"] + p["n"] @ s)
            from shapely import affinity
            p["support"] = affinity.translate(p["support"], xoff=s[0], yoff=s[1])
    e7 = e7[:18]   # arrangement-size caps (crossing planes are the costly ones)
    for i, p in enumerate(e7):
        cands.append({"id": f"prior{i}", "n": p["n"].tolist(), "d": p["d"],
                      "source": "prior_als",
                      "prior": {"n0": p["n"].tolist(), "d0": p["d"],
                                "w": min(1.0, p["area"] / 200.0 + 0.3)},
                      "support": _support_coords(p["support"])})
    kept = 0
    for p in e8:
        if kept >= 8:
            break
        dup = False
        for q in e7:
            cos = abs(float(np.asarray(q["n"]) @ p["n"]))
            if np.degrees(np.arccos(min(1.0, cos))) < 5.0 and abs(q["d"] - p["d"]) < 0.3:
                dup = True
                break
        if not dup:
            cands.append({"id": f"mvs{kept}", "n": p["n"].tolist(), "d": p["d"],
                          "source": "mvs", "prior": None,
                          "support": _support_coords(p["support"])})
            kept += 1
    return cands


def gapfill_planes(cands, envelope_pts, footprint_xy, tol=0.3, max_new=5,
                   min_pts=80, ransac_fn=None):
    """Coherent-gap supplement: local plane detection on the unexplained
    envelope points inside the footprint (steep allowed). Returns new
    candidate dicts (source='gapfill') with inlier-hull supports."""
    fp = Polygon(footprint_xy)
    if len(envelope_pts) == 0 or ransac_fn is None:
        return []
    from shapely.prepared import prep
    fpp = prep(fp)
    m_in = np.array([fpp.contains(Point(x, y)) for x, y in envelope_pts[:, :2]])
    env = envelope_pts[m_in]
    if len(env) == 0:
        return []
    D = np.full(len(env), 1e9)
    for p in cands:
        n = np.asarray(p["n"])
        D = np.minimum(D, np.abs(env @ n - p["d"]))
    gap = env[D > tol]
    if len(gap) < min_pts:
        return []
    found = ransac_fn(gap, max_planes=max_new, tol=0.2, min_frac=0.02,
                      min_abs=min_pts, reject_vertical=0.1)
    out = []
    for i, pl in enumerate(found):
        n = np.asarray(pl["n"]); d = pl["d"]
        inl = gap[np.abs(gap @ n - d) < 0.25]
        if len(inl) < min_pts:
            continue
        sup = MultiPoint([tuple(q) for q in inl[:, :2][::max(1, len(inl)//800)]]) \
            .convex_hull.buffer(0.8).simplify(0.3)
        out.append({"id": f"gap{i}", "n": n.tolist(), "d": float(d),
                    "source": "gapfill", "prior": None,
                    "support": _support_coords(sup)})
    return out


def s1_verdict(cands, envelope_pts, footprint_xy, tol=0.3, grid=1.0):
    """Input-side S1 gate: explained% of upper-envelope points + largest
    coherent unexplained region (m^2) inside the footprint."""
    fp = Polygon(footprint_xy)
    if len(envelope_pts):
        from shapely.prepared import prep
        fpp = prep(fp)
        m_in = np.array([fpp.contains(Point(x, y)) for x, y in envelope_pts[:, :2]])
        envelope_pts = envelope_pts[m_in]  # the gate judges THIS building only
    if len(envelope_pts) == 0:
        return {"explained": 0.0, "largest_gap_m2": None, "pass": False}
    D = np.full(len(envelope_pts), 1e9)
    for p in cands:
        n = np.asarray(p["n"])
        D = np.minimum(D, np.abs(envelope_pts @ n - p["d"]))
    unex = envelope_pts[D > tol]
    ui = unex
    explained = 1.0 - len(unex) / len(envelope_pts)
    # coherent gap via occupancy grid connected components
    largest = 0.0
    if len(ui):
        ij = np.floor(ui[:, :2] / grid).astype(int)
        cells = set(map(tuple, ij))
        seen = set()
        for c in cells:
            if c in seen:
                continue
            stack, comp = [c], 0
            seen.add(c)
            while stack:
                x, y = stack.pop()
                comp += 1
                for nb in ((x+1, y), (x-1, y), (x, y+1), (x, y-1)):
                    if nb in cells and nb not in seen:
                        seen.add(nb)
                        stack.append(nb)
            largest = max(largest, comp * grid * grid)
    return {"explained": round(float(explained), 4),
            "largest_gap_m2": round(float(largest), 1),
            "pass": bool(explained >= 0.90 and largest < 20.0)}
