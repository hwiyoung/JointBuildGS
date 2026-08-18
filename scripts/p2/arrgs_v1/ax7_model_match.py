#!/usr/bin/env python3
"""AX-7 model champion match (S0'): E7/E8 roofer.obj on the ARRGS model scale.

Purpose: the v3 reproduction record (B022 0.778 / B036 0.805 / B173 0.079,
frozen w5+pfreeze+i3) so far has no fair model-to-model opponent. This run
scores the sealed shared-Roofer models of E7 (Existing ALS alone) and E8
(E2 union ALS, no judgment) with the exact proxy recipe (model surface
samples vs E1 crop cls6, tau=0.5) to (a) place the reproduction/judgment
models on one scale and (b) define the AX-8 gate numbers on that scale.

Pre-registered expectations (2026-08-16, scientific_verdict stays null):
  1. Readout independence (E6 removal-table appendix): E7 floor-stripped
     proxy-f1 lands in the v1-reproduction band +-0.05
     (B022 0.692 / B036 0.798 / B173 0.076) -- same ALS material read by
     two different extractors (shared Roofer vs ARRGS S4). If it misses,
     the extractor gap is registered as a confound and AX-8 gates are
     defined on the ARRGS-internal scale only.
  2. E8 (union, no judgment) >= E7 on the two unchanged buildings, and
     E8 >> E7 on B173 (current MVS covers the stale prior; mixed with
     stale-roof precision loss, so no numeric bound is registered).
  Output contract: AX-8 scale = {hold: B022/B036 champion numbers incl.
  v3 reproduction 0.778/0.805; discretion: B173 E8 number = the natural
  lower bound a judged model must beat (judgment must outdo no-judgment)}.
  Evaluation only -- no kill condition. The sealed geometry_eval chain
  remains the official scorer; ARRGS enters the E-ring officially only via
  point-cloud export -> shared Roofer (contract path, noted in readout).

Fairness adapter (recorded): roofer.obj has no g-groups, so sample_obj
would score its floor plates as cls6 and weight walls at roof density.
Faces are therefore re-classified geometrically to match the ARRGS brep
grouping: horizontal (|nz|>0.95) at base elevation (<= E1 ground p99
+ 0.5 m) -> ground (excluded, like the brep 'g ground' group); |nz|<0.3
-> wall (density 8); else roof (density 25). B022 audit: floor candidates
are a single z=10.52 plane, 2619 m2 of 13470 m2 total. The unadapted
all-roof score is kept as a sensitivity row.

Usage (CPU container): ax7_model_match.py
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
from anchor_sweep import read_ply_xyz_cls, f1_proxy, E1_DIR  # noqa: E402
from xreal_run import BUILDINGS, OUT  # noqa: E402

A2 = Path("/artifacts/JointBuildGS/phase-payloads/p2/journal1_phase_a_v1/"
          "P2-JOURNAL1-PHASE-A-v1/a2/assets_roofer_input")
ROOT = OUT / "P2-ARRGS-AX7-v1"
ANCHOR_SUMMARY = OUT / "P2-ARRGS-ANCHOR-v1/anchor_summary.json"


def load_obj(path):
    verts, tris = [], []
    for ln in open(path):
        t = ln.split()
        if not t:
            continue
        if t[0] == "v":
            verts.append([float(t[1]), float(t[2]), float(t[3])])
        elif t[0] == "f":
            tris.append([int(x) - 1 for x in t[1:4]])
    return np.asarray(verts), np.asarray(tris, dtype=int)


def sample_classified(verts, tris, ground_z99, seed=0,
                      d_roof=25.0, d_wall=8.0):
    """Sample faces with ARRGS-brep-equivalent class/density assignment."""
    if len(tris) == 0:  # empty model (e.g. B036 E7): scored as f1=0
        return np.zeros((0, 3)), {"area_total_m2": 0.0,
                                  "area_floor_m2": 0.0, "area_wall_m2": 0.0}
    a, b, c = verts[tris[:, 0]], verts[tris[:, 1]], verts[tris[:, 2]]
    n = np.cross(b - a, c - a)
    area = 0.5 * np.linalg.norm(n, axis=1)
    nz = np.abs(n[:, 2]) / np.maximum(np.linalg.norm(n, axis=1), 1e-12)
    zc = (a[:, 2] + b[:, 2] + c[:, 2]) / 3
    floor = (nz > 0.95) & (zc <= ground_z99 + 0.5)
    wall = (~floor) & (nz < 0.3)
    rng = np.random.default_rng(seed)
    pts, cs = [], []
    for i in range(len(tris)):
        dens = 0.0 if floor[i] else (d_wall if wall[i] else d_roof)
        k = int(area[i] * dens)
        if k < 1:
            if floor[i]:
                continue
            k = 1
        r1 = np.sqrt(rng.random(k))
        r2 = rng.random(k)
        p = ((1 - r1)[:, None] * a[i] + (r1 * (1 - r2))[:, None] * b[i]
             + (r1 * r2)[:, None] * c[i])
        pts.append(p)
        cs.append(np.full(k, 6, dtype=np.uint8))
    stats = {"area_total_m2": round(float(area.sum()), 1),
             "area_floor_m2": round(float(area[floor].sum()), 1),
             "area_wall_m2": round(float(area[wall].sum()), 1)}
    if not pts:
        return np.zeros((0, 3)), stats
    return np.concatenate(pts), stats


def main():
    ROOT.mkdir(parents=True, exist_ok=True)
    summary = {"_recipe": {
        "metric": "proxy-f1 model-samples vs E1 crop cls6, tau=0.5",
        "adapter": "floor(|nz|>0.95 & z<=E1 ground p99+0.5) dropped; "
                   "wall(|nz|<0.3) density 8; roof density 25",
        "sensitivity": "raw = all faces as roof density 25 (no adapter)"}}
    for bk, meta in BUILDINGS.items():
        ref_xyz, ref_cls = read_ply_xyz_cls(E1_DIR / f"{meta['bkey']}.points.ply")
        ground_z99 = float(np.percentile(ref_xyz[ref_cls == 2][:, 2], 99))
        ref6 = ref_xyz[ref_cls == 6]
        row = {"e1_ground_z99": round(ground_z99, 2)}
        for cond in ("E7", "E8"):
            obj = A2 / cond / f"{meta['bkey']}.roofer.obj"
            if not obj.is_file():
                row[cond] = {"error": "missing obj"}
                continue
            verts, tris = load_obj(obj)
            pts, stats = sample_classified(verts, tris, ground_z99)
            adapted = f1_proxy(pts, ref6)
            # sensitivity: raw sample_obj semantics (all faces roof d25)
            raw_pts, _ = sample_classified(
                verts, tris, ground_z99=-1e9, d_wall=25.0)
            raw = f1_proxy(raw_pts, ref6)
            row[cond] = {"f1_proxy_e1": adapted, "raw_all_roof": raw,
                         **stats}
            print(f"[ax7] {bk} {cond}: adapted {adapted['f1']:.3f} "
                  f"(raw {raw['f1']:.3f})", flush=True)
        summary[bk] = row

    # champion table: pull ARRGS reference rows from the anchor summary
    anchor = json.load(open(ANCHOR_SUMMARY)) if ANCHOR_SUMMARY.is_file() else {}
    orc = (anchor.get("_verdict") or {}).get("oracle_f1_proxy") or {}
    table = {}
    for bk in BUILDINGS:
        def f1_of(name):
            return ((anchor.get(name, {}).get("f1_proxy_e1") or {})
                    .get("f1"))
        table[bk] = {
            "repro_v1": (orc.get(bk) or {}).get("f1"),
            "repro_v3_frozen": f1_of(f"{bk}_w5_pfreeze_i3"),
            "judged_best_global_w": max(
                (v for v in (f1_of(f"{bk}_w0.02"), f1_of(f"{bk}_w0.1"),
                             f1_of(f"{bk}_w0"), f1_of(f"{bk}_w5"))
                 if v is not None), default=None),
            "E7_shared_roofer": (summary[bk].get("E7", {})
                                 .get("f1_proxy_e1") or {}).get("f1"),
            "E8_shared_roofer": (summary[bk].get("E8", {})
                                 .get("f1_proxy_e1") or {}).get("f1"),
        }
    summary["_champion_table"] = table
    summary["_verdict"] = {
        "scientific_verdict": None,
        "prereg_1_readout_independence": {
            bk: (table[bk]["E7_shared_roofer"] is not None
                 and table[bk]["repro_v1"] is not None
                 and abs(table[bk]["E7_shared_roofer"]
                         - table[bk]["repro_v1"]) <= 0.05)
            for bk in BUILDINGS},
        "prereg_2_E8_ge_E7_unchanged": {
            bk: (table[bk]["E8_shared_roofer"] is not None
                 and table[bk]["E7_shared_roofer"] is not None
                 and table[bk]["E8_shared_roofer"]
                 >= table[bk]["E7_shared_roofer"])
            for bk in ("B022", "B036")},
        "ax8_scale_proposal": {
            "hold_B022": table["B022"]["repro_v3_frozen"],
            "hold_B036": table["B036"]["repro_v3_frozen"],
            "discretion_B173_natural_floor_E8":
                table["B173"]["E8_shared_roofer"]},
    }
    out = ROOT / "ax7_summary.json"
    json.dump(summary, open(out, "w"), indent=1, default=str)
    print("[ax7] ->", out)
    print(json.dumps(summary["_champion_table"], indent=1, default=str))
    print(json.dumps(summary["_verdict"], indent=1, default=str))


if __name__ == "__main__":
    main()
