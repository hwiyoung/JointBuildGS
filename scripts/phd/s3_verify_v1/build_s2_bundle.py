#!/usr/bin/env python3
"""S2 bundle writer — phd_s3_verify_s2_bundle_v1 (verification page 2 data).

ZERO optimization steps. Regenerates the S1 bundle in-process (same plane ids,
same thinned point rows; SYNTH_GABLE gains deterministic pseudo-ALS first),
then cuts the legacy arrangement (arrangement.py, unmodified) over the exact
S1 candidate set and serializes the S2 stage:

- cells: only the footprint-prism interior (the model domain). Cells outside
  the footprint stay o=0 virtual outside — Σ cell volume = footprint area ×
  (top_z − ground_z). Each interior cell is judged by the r16 o_init rule:
  single vertical pillar (radius 0.75 m) at the CELL CENTROID over the ALS
  rows (source==1) of the thinned s1_points.ply, z_surf = p90; below→t 0.75,
  above→0.15, empty pillar→0.4 (r16 reselection). o_state = [t > 0.5].
- faces: interior cut faces carry the full s1 p### ring list of their cutting
  plane ((n,d) match at 1e-6); prism-boundary faces become domain
  wall/ground/top with cell_b null. initial_real = F* (|Δo_state| = 1, o=0
  beyond the domain).
- seeds: one legacy-spacing grid pass on EVERY face, gate-0 faces included
  (lifetime rule (2)); no subsampling; centroid fallback keeps ≥1 seed/face.

Usage (container):
  bash scripts/p2/arrgs_v1/run_host.sh <gpu> \
      scripts/phd/s3_verify_v1/build_s2_bundle.py [run ...]   # default: all
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
for p in (HERE, REPO / "scripts/p2/arrgs_v1", REPO / "scripts/p2/journal1_phase_a_v1"):
    sys.path.insert(0, str(p))

import build_s1_bundle as s1b  # noqa: E402
from bundle_io import unit_plane  # noqa: E402
from arrangement import build_arrangement, plane_frame  # noqa: E402

CFG = s1b.CFG
O_CFG = CFG["o_init"]
T_OF = {"below": float(O_CFG["t"]["below"]), "above": float(O_CFG["t"]["above"]),
        "empty": float(O_CFG["t"]["empty"]), "outside": float(O_CFG["t"]["outside"])}
RADIUS = float(O_CFG["radius_m"])
SPACING = float(CFG["seeds"]["spacing_m"])
SEED_SIZE = float(CFG["seeds"]["size_m"])
MARGIN = CFG["arrangement"]["domain_margin_m"]
S2_SCHEMA = str(CFG["s2_schema"])
DOMAIN_KIND = {"domain:z-": "ground", "domain:z+": "top"}  # everything else: wall


def map_s1_planes(planes, entries):
    """legacy cut plane -> all s1 p### ring ids with the same unit (n,d), 1e-6."""
    out = {}
    for p in planes:
        n, d = unit_plane(p["n"], p["d"])
        out[p["id"]] = [f"p{i:03d}" for i, e in enumerate(entries)
                        if abs(e["d"] - d) <= 1e-6
                        and float(np.abs(np.asarray(e["n"]) - n).max()) <= 1e-6]
    return out


def judge_cell(centroid, tree, als_rows, xyz):
    """r16 o_init: single centroid pillar, p90 of ALS z. -> (t, surf dict)."""
    cx, cy, cz = (float(v) for v in centroid)
    loc = sorted(tree.query_ball_point([cx, cy], r=RADIUS)) if tree is not None else []
    rows = als_rows[np.asarray(loc, dtype=int)] if loc else np.zeros(0, dtype=int)
    if len(rows) == 0:
        t, z_surf, verdict = T_OF["empty"], None, "empty"
    else:
        z_surf = float(np.percentile(xyz[rows, 2], 90))
        t, verdict = (T_OF["below"], "below") if cz < z_surf else (T_OF["above"], "above")
    return t, {"cx": round(cx, 4), "cy": round(cy, 4), "radius_m": RADIUS,
               "z_surf": round(z_surf, 4) if z_surf is not None else None,
               "n_col_pts": int(len(rows)), "col_pt_idx": [int(i) for i in rows],
               "verdict": verdict}


def face_grid(n, d, poly3d):
    """One grid pass in the shared plane frame; centroid fallback -> >=1 seed."""
    import shapely
    from shapely.geometry import Polygon
    origin, e1, e2 = plane_frame(np.asarray(n, dtype=np.float64), float(d))
    P = np.asarray(poly3d, dtype=np.float64)
    uv_ring = np.stack([(P - origin) @ e1, (P - origin) @ e2], axis=1)
    poly = Polygon(uv_ring)
    if not poly.is_valid:
        poly = poly.buffer(0)
    minx, miny, maxx, maxy = poly.bounds
    xs = np.arange(minx + SPACING / 2, maxx, SPACING)
    ys = np.arange(miny + SPACING / 2, maxy, SPACING)
    pts = np.zeros((0, 2))
    if len(xs) and len(ys):
        gx, gy = np.meshgrid(xs, ys, indexing="ij")
        keep = shapely.contains_xy(poly, gx.ravel(), gy.ravel())
        pts = np.stack([gx.ravel()[keep], gy.ravel()[keep]], axis=1)
    if len(pts) == 0 or not np.isfinite(pts).all():
        c = poly.centroid
        pts = (np.asarray([[c.x, c.y]]) if np.isfinite([c.x, c.y]).all()
               else uv_ring.mean(axis=0)[None, :])
    mu = origin[None, :] + pts[:, :1] * e1[None, :] + pts[:, 1:2] * e2[None, :]
    return pts, mu


def build_s2(ctx):
    p2s1 = map_s1_planes(ctx["planes"], ctx["entries"])
    planes = [p for p in ctx["planes"] if p2s1[p["id"]]]  # exactly the S1 set
    margin = float(MARGIN[ctx["dataset_kind"]])
    arr = build_arrangement(planes, ctx["fp_xy"], float(ctx["ground_z"]),
                            float(ctx["top_z"]), margin=margin)

    inside = [c for c in arr["cells"] if c["fixed"] is None]
    idx2cid = {c["idx"]: f"c{k:04d}" for k, c in enumerate(inside)}

    # faces: keep those touching the interior; prism boundary -> domain faces.
    # arr["faces"] order is hash-dependent (set iteration in the legacy code),
    # so IDs come from a deterministic sort: (plane rank, cells, face centroid).
    rank = {p["id"]: j for j, p in enumerate(planes)}
    for j, pid in enumerate(("domain:x+", "domain:x-", "domain:y+", "domain:y-",
                             "domain:z+", "domain:z-")):
        rank[pid] = len(planes) + j
    kept = []
    for f in arr["faces"]:
        a_in, b_in = f["cell_a"] in idx2cid, f["cell_b"] in idx2cid
        if not a_in and not b_in:
            continue
        cen = np.asarray(f["poly3d"], dtype=np.float64).mean(axis=0)
        if a_in and b_in:
            kept.append((f, f["cell_a"], f["cell_b"], None, cen))
        else:  # one side beyond the model domain (outside footprint / box)
            dom = DOMAIN_KIND.get(f["plane_id"], "wall")
            kept.append((f, f["cell_a"] if a_in else f["cell_b"], None, dom, cen))
    kept.sort(key=lambda t: (rank[t[0]["plane_id"]], t[1],
                             -1 if t[2] is None else t[2],
                             round(t[4][0], 6), round(t[4][1], 6), round(t[4][2], 6)))

    from scipy.spatial import cKDTree
    als_rows = np.nonzero(ctx["src"] == 1)[0]
    tree = cKDTree(ctx["xyz"][als_rows][:, :2]) if len(als_rows) else None
    t_of_cell, surf_of_cell, o_of_cell = {}, {}, {}
    for c in inside:
        cid = idx2cid[c["idx"]]
        t, surf = judge_cell(c["centroid"], tree, als_rows, ctx["xyz"])
        t_of_cell[cid], surf_of_cell[cid] = t, surf
        o_of_cell[cid] = int(t > 0.5)

    faces_json, seeds_json = [], []
    cell_faces = {idx2cid[c["idx"]]: [] for c in inside}
    cell_cutids = {idx2cid[c["idx"]]: [] for c in inside}
    n_seed = 0
    for fi, (f, a, b, dom, _cen) in enumerate(kept):
        fid = f"f{fi:05d}"
        ca, cb = idx2cid[a], idx2cid[b] if b is not None else None
        oa, ob = o_of_cell[ca], o_of_cell[cb] if cb is not None else 0
        cell_faces[ca].append(fid)
        if cb is not None:
            cell_faces[cb].append(fid)
        if not f["plane_id"].startswith("domain:"):
            cell_cutids[ca].append(f["plane_id"])
            if cb is not None:
                cell_cutids[cb].append(f["plane_id"])
        faces_json.append({
            "face_id": fid, "cell_a": ca, "cell_b": cb,
            "s1_plane_ids": [] if dom is not None else list(p2s1[f["plane_id"]]),
            "domain": dom,
            "n": [round(float(v), 6) for v in f["n"]],
            "d": round(float(f["d"]), 4),
            "poly3d": np.round(f["poly3d"], 4).tolist(),
            "area_m2": round(float(f["area"]), 4),
            "initial_real": abs(oa - ob) == 1,
        })
        uv, mu = face_grid(f["n"], f["d"], f["poly3d"])
        for k in range(len(uv)):
            seeds_json.append({"seed_id": f"s{n_seed:06d}", "face_id": fid,
                               "uv": np.round(uv[k], 4).tolist(),
                               "mu": np.round(mu[k], 4).tolist()})
            n_seed += 1

    cells_json = []
    for c in inside:
        cid = idx2cid[c["idx"]]
        cut_ids, seen = [], set()
        for pid in sorted(set(cell_cutids[cid]), key=lambda q: rank[q]):
            for s1_id in p2s1[pid]:
                if s1_id not in seen:
                    seen.add(s1_id)
                    cut_ids.append(s1_id)
        cells_json.append({
            "cell_id": cid,
            "centroid": [round(float(v), 4) for v in c["centroid"]],
            "volume_m3": round(float(c["volume"]), 6),
            "fixed": False,  # outside-footprint cells are not serialized (o=0 virtual)
            "t": t_of_cell[cid], "o_state": o_of_cell[cid],
            "surf": surf_of_cell[cid],
            "cut_plane_ids": cut_ids, "face_ids": cell_faces[cid],
        })

    from shapely.geometry import Polygon
    fp_poly = Polygon(np.asarray(ctx["fp_xy"])[:, :2])
    if not fp_poly.is_valid:
        fp_poly = fp_poly.buffer(0)
    prism = float(fp_poly.area) * (float(ctx["top_z"]) - float(ctx["ground_z"]))
    sum_cells = float(sum(c["volume_m3"] for c in cells_json))

    out_dir = ctx["out_dir"]
    json.dump({"cells": cells_json, "prism_volume_m3": round(prism, 4),
               "sum_cell_volume_m3": round(sum_cells, 4)},
              open(out_dir / "s2_cells.json", "w"))
    json.dump({"faces": faces_json}, open(out_dir / "s2_faces.json", "w"))
    json.dump({"grid": {"spacing_m": SPACING, "size_m": SEED_SIZE},
               "seeds": seeds_json}, open(out_dir / "s2_seeds.json", "w"))

    n_als = int(len(als_rows))
    manifest = json.load(open(out_dir / "manifest.json"))
    manifest["stage"] = "s1+s2"
    manifest["s2_schema"] = S2_SCHEMA
    manifest["o_init_def"] = dict(
        O_CFG,
        pillar_source=(
            f"s1_points.ply source==1 rows (post-thinning, stride {ctx['stride']}: "
            f"{n_als} of {ctx['n_als_orig']} original ALS points) — pillars judge "
            "the thinned set so col_pt_idx back-references resolve in the viewer"))
    manifest["counts"].update({"cells": len(cells_json), "faces": len(faces_json),
                               "seeds": len(seeds_json)})
    manifest["volumes"] = {"prism_m3": round(prism, 4),
                           "sum_cells_m3": round(sum_cells, 4)}
    manifest["arrangement"] = {
        "domain_margin_m": margin,
        "source": "scripts/p2/arrgs_v1/arrangement.py build_arrangement (unmodified)",
        "cells_scope": ("footprint-prism interior only; outside cells stay o=0 "
                        "virtual, prism-boundary facets become domain faces")}
    json.dump(manifest, open(out_dir / "manifest.json", "w"), indent=1)
    print(f"[s2-bundle] {ctx['name']}: cells {len(cells_json)} faces {len(faces_json)} "
          f"seeds {len(seeds_json)} | prism {prism:.1f} sum {sum_cells:.1f} "
          f"({abs(sum_cells - prism) / max(prism, 1e-9):.2e} rel)", flush=True)


def verify_run(ctx):
    """Re-read the written bundle and enforce the check contract; -> stats."""
    out_dir = ctx["out_dir"]
    cells_doc = json.load(open(out_dir / "s2_cells.json"))
    faces_doc = json.load(open(out_dir / "s2_faces.json"))
    seeds_doc = json.load(open(out_dir / "s2_seeds.json"))
    s1_planes = json.load(open(out_dir / "s1_planes.json"))
    cells, faces, seeds = cells_doc["cells"], faces_doc["faces"], seeds_doc["seeds"]
    cell_by_id = {c["cell_id"]: c for c in cells}
    face_ids = {f["face_id"] for f in faces}
    s1_ids = {p["plane_id"] for p in s1_planes["planes"]}
    src, xyz = ctx["src"], ctx["xyz"]

    prism = float(cells_doc["prism_volume_m3"])
    sum_cells = float(sum(c["volume_m3"] for c in cells))
    assert abs(sum_cells - prism) <= 1e-3 * prism, (
        f"volume: sum {sum_cells} vs prism {prism}")

    verdicts = {"below": 0, "above": 0, "empty": 0, "outside": 0}
    for c in cells:
        v = c["surf"]["verdict"]
        verdicts[v] += 1
        assert abs(c["t"] - T_OF[v]) <= 1e-9 and c["o_state"] == int(c["t"] > 0.5)
        idx = np.asarray(c["surf"]["col_pt_idx"], dtype=int)
        assert c["surf"]["n_col_pts"] == len(idx)
        if len(idx):
            assert (src[idx] == 1).all(), f"{c['cell_id']}: non-ALS pillar rows"
            r = np.hypot(xyz[idx, 0] - c["surf"]["cx"], xyz[idx, 1] - c["surf"]["cy"])
            assert float(r.max()) <= RADIUS + 1e-3
        assert all(q in s1_ids for q in c["cut_plane_ids"])
        assert all(q in face_ids for q in c["face_ids"])
    for f in faces:
        oa = cell_by_id[f["cell_a"]]["o_state"]
        ob = cell_by_id[f["cell_b"]]["o_state"] if f["cell_b"] is not None else 0
        assert f["initial_real"] == (abs(oa - ob) == 1), f"{f['face_id']}: F* mismatch"
        if f["domain"] is None:
            assert f["s1_plane_ids"] and all(q in s1_ids for q in f["s1_plane_ids"])
        else:
            assert f["s1_plane_ids"] == [] and f["cell_b"] is None
        assert f["face_id"] in cell_by_id[f["cell_a"]]["face_ids"]
        if f["cell_b"] is not None:
            assert f["face_id"] in cell_by_id[f["cell_b"]]["face_ids"]
    seeded = {s["face_id"] for s in seeds}
    assert all(s["face_id"] in face_ids for s in seeds)
    assert seeded == face_ids, f"faces without seeds: {sorted(face_ids - seeded)[:5]}"

    n_on = sum(c["o_state"] for c in cells)
    return {"name": ctx["name"], "cells": len(cells), "faces": len(faces),
            "seeds": len(seeds), "on_cells": n_on, "verdicts": verdicts,
            "prism_m3": prism, "sum_cells_m3": round(sum_cells, 4),
            "initial_real_faces": sum(1 for f in faces if f["initial_real"])}


def main():
    runs = sys.argv[1:] or CFG["runs"]
    out_root = Path(CFG["out_root"])
    gravity, lod2_faces = s1b.real_context([r for r in runs if r != "SYNTH_GABLE"])
    stats = []
    for r in runs:
        ctx = (s1b.build_synth(out_root) if r == "SYNTH_GABLE"
               else s1b.build_real(r, out_root, gravity, lod2_faces))
        build_s2(ctx)
        stats.append(verify_run(ctx))
        print(f"[s2-verify] {json.dumps(stats[-1])}", flush=True)


if __name__ == "__main__":
    main()
