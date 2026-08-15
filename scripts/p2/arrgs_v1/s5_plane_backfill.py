#!/usr/bin/env python3
"""Backfill s5_plane_summary.json for finished runs (from s5_brep.obj).

New runs get the summary natively from arrgs_train (arrangement-side, exact
plane_ids). This backfill recovers an equivalent surface-level summary from the
exported OBJ: triangles are clustered into planes by (normal, offset), coplanar
triangles are merged per plane, and connected components are counted. plane_id
becomes a synthetic label (class#k); counts/areas match the semantic intent.

Usage: python s5_plane_backfill.py [runs-root ...]   (skips runs that have one)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

DEFAULT_ROOTS = [
    "/artifacts/JointBuildGS/phase-payloads/p2/arrgs_v1/P2-ARRGS-ANCHOR-v1/runs",
]


def load_obj(path):
    """Returns (verts, polys) with polys = [(cls, [tri, ...])] — the exporter
    fan-triangulates each facet polygon with a shared first vertex and never
    reuses vertices across polygons, so consecutive triangles with the same
    first index reassemble into the original facet."""
    verts, polys, cls = [], [], "roof"
    last_first = None
    for ln in open(path):
        t = ln.split()
        if not t:
            continue
        if t[0] == "v":
            verts.append([float(x) for x in t[1:4]])
        elif t[0] == "g":
            cls = t[1]
            last_first = None
        elif t[0] == "f":
            tri = [int(x) - 1 for x in t[1:4]]
            if tri[0] != last_first:
                polys.append((cls, []))
                last_first = tri[0]
            polys[-1][1].append(tri)
    return np.asarray(verts), polys


def load_candidates(run_dir):
    """(n, d, id) rows from s1_candidates.json for real-plane-id assignment."""
    p = Path(run_dir) / "s1_candidates.json"
    if not p.is_file():
        return []
    out = []
    for pl in json.load(open(p)).get("planes", []):
        n = np.asarray(pl["n"], dtype=float)
        n = n / np.linalg.norm(n)
        out.append((n, float(pl["d"]), pl["id"]))
    return out


def match_plane_id(n, d, cands, ang_tol=0.996, d_tol=0.2):
    """Nearest candidate plane (either normal sign) within tolerance, else None."""
    best = None
    for cn, cd, cid in cands:
        for s in (1.0, -1.0):
            if float(n @ (s * cn)) >= ang_tol and abs(d - s * cd) <= d_tol:
                err = abs(d - s * cd) + (1 - float(n @ (s * cn)))
                if best is None or err < best[0]:
                    best = (err, cid)
    return best[1] if best else None


def summarize(obj_path, cands=()):
    from shapely.geometry import Polygon
    from shapely.ops import unary_union
    verts, obj_polys = load_obj(obj_path)
    # pass 1: orientation buckets per POLYGON (normal from its largest triangle
    # — per-triangle normals of thin slivers are rounding noise). Boundary-
    # rounding on d is NOT used as a key: it fragments a plane on a bin edge.
    buckets = {}  # (cls, n_key) -> list of (d, poly_tris, n)
    for cls, ptris in obj_polys:
        best, n = 0.0, None
        for tri in ptris:
            a, b, c = verts[tri[0]], verts[tri[1]], verts[tri[2]]
            cr = np.cross(b - a, c - a)
            l = np.linalg.norm(cr)
            if l > best:
                best, n = l, cr / l
        if n is None:
            continue
        if n[2] < 0 or (abs(n[2]) < 1e-3 and (n[0] < 0 or (abs(n[0]) < 1e-3 and n[1] < 0))):
            n = -n  # canonical hemisphere so both windings cluster together
        buckets.setdefault((cls, tuple(np.round(n, 1))), []).append(
            (float(n @ verts[ptris[0][0]]), ptris, n))
    # pass 2: within a bucket, 1-D cluster the offsets by gap (parallel planes
    # at different heights stay separate; same plane never splits)
    clusters = {}
    for (cls, nk), rows in buckets.items():
        rows.sort(key=lambda r: r[0])
        gid = 0
        prev_d = None
        for d, ptris, n in rows:
            if prev_d is not None and d - prev_d > 0.15:
                gid += 1
            prev_d = d
            key = (cls, nk, gid)
            c = clusters.setdefault(key, {"n": n, "d": d, "tris": [], "npoly": 0})
            c["tris"].extend(ptris)
            c["npoly"] += 1
    rows = []
    for (cls, _, _), c in clusters.items():
        n = c["n"]
        ref = np.array([1.0, 0, 0]) if abs(n[0]) < 0.9 else np.array([0.0, 1, 0])
        e1 = ref - (ref @ n) * n; e1 /= np.linalg.norm(e1)
        e2 = np.cross(n, e1)
        origin = n * c["d"]
        polys = []
        for tri in c["tris"]:
            p3 = verts[tri]
            uv = np.stack([(p3 - origin) @ e1, (p3 - origin) @ e2], axis=1)
            try:
                q = Polygon(uv).buffer(0.02)
                if q.is_valid and q.area > 1e-4:
                    polys.append(q)
            except Exception:
                pass
        if not polys:
            continue
        merged = unary_union(polys)
        geoms = list(getattr(merged, "geoms", [merged]))
        ncomp = sum(1 for g in geoms if g.area >= 0.25)
        if ncomp == 0:
            continue
        rows.append({"class": cls, "surfaces": ncomp,
                     "facets": c["npoly"],
                     "sliver_area": round(float(sum(g.area for g in geoms
                                                    if g.area < 0.25)), 2),
                     "area": round(float(merged.area), 2)})
        rows[-1]["_n"], rows[-1]["_d"] = c["n"], c["d"]
    rows.sort(key=lambda r: -r["area"])
    for i, r in enumerate(rows):
        n_, d_ = r.pop("_n"), r.pop("_d")
        pid = match_plane_id(n_, d_, cands) if cands else None
        r["plane_id"] = pid or f"{r['class']}#{i}"
    return rows


def main():
    roots = [Path(p) for p in (sys.argv[1:] or DEFAULT_ROOTS)]
    n = 0
    for root in roots:
        if not root.is_dir():
            continue
        for run in sorted(root.iterdir()):
            obj = run / "s5_brep.obj"
            out = run / "s5_plane_summary.json"
            if not obj.is_file() or out.is_file():
                continue
            try:
                rows = summarize(obj, load_candidates(run))
            except Exception as e:
                print(f"[backfill] {run.name}: FAILED {e}")
                continue
            sem = {}
            for r in rows:
                sem[r["class"]] = sem.get(r["class"], 0) + r["surfaces"]
            json.dump(rows, open(out, "w"))
            print(f"[backfill] {run.name}: semantic={sem}")
            n += 1
    print(f"[backfill] wrote {n} summaries")


if __name__ == "__main__":
    main()
