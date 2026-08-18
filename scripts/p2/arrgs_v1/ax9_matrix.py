#!/usr/bin/env python3
"""AX-9 input-by-readout matrix (CPU, triad): fill the champion-table gaps.

Arms (repro form = zero optimization, our assembler, multi-point labelling):
  A "unionInit"  — v3 hypotheses unchanged; occupancy init = ALS UNION
     current-image crop cls6 (o_init_source="union"). Measures what breaking
     the judge/defendant separation at init buys/costs — the no-judgment
     union restated inside our assembler (Roofer version = E8).
  B "imageOnly"  — hypotheses = E8-increment ("mvs" source) + footprint
     only; init = current-image points (o_init_source="mvs"); tower
     candidates off (ALS-derived). Claim-2 arm in repro form. Recorded
     approximations: "mvs" planes are the E8-minus-E7 increment (closest
     available image-contributed set); ground elevation stays the crop
     statistic (shared scene constant).
  C "E2 model scale" — sealed E2 roofer.obj scored with the AX-7 adapter.
     Asset search (2026-08-18): no *.roofer.obj exists for E2 in any payload
     (points only) -> recorded as asset_missing; producing it needs a sealed
     Stage-3 rerun (separate approval).

Pre-registered expectations (2026-08-18, scientific_verdict stays null):
  A: unchanged buildings within +-0.02 of v3 repro (current points should
     not flip solid columns there); B173 rises above 0.30 toward the union
     band. A large B173 rise is NOT a win for the method — it restates the
     no-judgment union; it is the claim-5 comparison arm on our assembler.
  B: all three BELOW their v3 repro; B036 (image-collapse profile) worst.
     Completeness collapse where the image is blind is the claim-2
     signature. Any building where imageOnly ~= v3 repro is a recorded
     danger flag for claim 2 (prior necessity) there.

Usage (CPU container): ax9_matrix.py
"""
import json
import sys
import traceback
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from real_scene import load_real_scene  # noqa: E402
from arrangement import build_arrangement  # noqa: E402
from arrgs_train import solid_boundary_faces, export_obj  # noqa: E402
from export_eval_points import sample_obj  # noqa: E402
from anchor_sweep import read_ply_xyz_cls, f1_proxy, E1_DIR  # noqa: E402
from xreal_run import BUILDINGS, OUT, scene_for  # noqa: E402

ROOT = OUT / "P2-ARRGS-AX9-v1"
ANCHOR = OUT / "P2-ARRGS-ANCHOR-v1/anchor_summary.json"
AX7 = OUT / "P2-ARRGS-AX7-v1/ax7_summary.json"


def repro_build(scene, out_dir):
    rs = load_real_scene(scene, "cpu")
    arr = build_arrangement(rs["planes"], rs["footprint"], rs["ground_z"],
                            rs["top_z"], margin=1.2)
    fn = rs["o_init_fn"]
    o = []
    for c in arr["cells"]:
        if c["fixed"] is not None:
            o.append(float(c["fixed"]))
            continue
        cen = np.asarray(c["centroid"])
        pts = [cen]
        for v in (c.get("verts") or [])[:12]:
            pts.append(0.5 * (np.asarray(v, dtype=float) + cen))
        o.append(1.0 if np.mean([fn(p) for p in pts]) > 0.5 else 0.0)
    out_dir.mkdir(parents=True, exist_ok=True)
    export_obj(solid_boundary_faces(arr, o), out_dir / "s5_brep.obj",
               rs["ground_z"])
    return (out_dir / "s5_brep.obj", len(arr["cells"]),
            [p["source"] for p in rs["planes"]])


def main():
    ROOT.mkdir(parents=True, exist_ok=True)
    summary = {"_prereg": "see module docstring",
               "E2_model_scale": "asset_missing (no E2 *.roofer.obj in any "
                                 "payload; sealed rerun needs approval)"}
    for bk, meta in BUILDINGS.items():
        ref_xyz, ref_cls = read_ply_xyz_cls(E1_DIR / f"{meta['bkey']}.points.ply")
        ref6 = ref_xyz[ref_cls == 6] if ref_cls is not None else ref_xyz
        row = {}
        for arm in ("unionInit", "imageOnly"):
            try:
                scene = scene_for(bk)
                scene["skip_images"] = True
                scene["o_init_variant"] = "top_cluster"
                if arm == "unionInit":
                    scene["tower_candidates"] = True
                    scene["o_init_source"] = "union"
                else:
                    scene["o_init_source"] = "mvs"
                    scene["s1_sources"] = ["mvs"]
                obj, cells, srcs = repro_build(scene, ROOT / "runs" / f"{bk}_{arm}")
                xyz, cls = sample_obj(obj)
                sc = f1_proxy(xyz[cls == 6], ref6) if len(xyz) else None
                from collections import Counter
                row[arm] = {"f1_proxy_e1": sc, "cells": cells,
                            "plane_sources": dict(Counter(srcs))}
                print(f"[ax9] {bk} {arm}: "
                      f"{(sc or {}).get('f1')}", flush=True)
            except Exception as e:
                traceback.print_exc()
                row[arm] = {"error": str(e)[:200]}
        summary[bk] = row
        json.dump(summary, open(ROOT / "ax9_summary.json", "w"), indent=1,
                  default=str)

    # champion columns for context
    anchor = json.load(open(ANCHOR)) if ANCHOR.is_file() else {}
    ax7 = json.load(open(AX7)) if AX7.is_file() else {}
    table = {}
    for bk in BUILDINGS:
        table[bk] = {
            "repro_v3": (anchor.get(f"{bk}_w5_pfreeze_i3", {})
                         .get("f1_proxy_e1") or {}).get("f1"),
            "unionInit": ((summary[bk].get("unionInit") or {})
                          .get("f1_proxy_e1") or {}).get("f1"),
            "imageOnly": ((summary[bk].get("imageOnly") or {})
                          .get("f1_proxy_e1") or {}).get("f1"),
            "E7_roofer": ((ax7.get(bk, {}).get("E7") or {})
                          .get("f1_proxy_e1") or {}).get("f1"),
            "E8_roofer": ((ax7.get(bk, {}).get("E8") or {})
                          .get("f1_proxy_e1") or {}).get("f1"),
        }
    v3 = {"B022": 0.7782, "B036": 0.805, "B173": 0.0791}
    summary["_champion_table"] = table
    summary["_verdict"] = {
        "scientific_verdict": None,
        "A_unchanged_within_0.02": {
            bk: (table[bk]["unionInit"] is not None
                 and abs(table[bk]["unionInit"] - v3[bk]) <= 0.02)
            for bk in ("B022", "B036")},
        "A_B173_above_0.30": (table["B173"]["unionInit"] or 0) > 0.30,
        "B_all_below_v3": {
            bk: (table[bk]["imageOnly"] is not None
                 and table[bk]["imageOnly"] < v3[bk] - 0.02)
            for bk in ("B022", "B036", "B173")},
        "B_claim2_danger_flags": [
            bk for bk in BUILDINGS
            if table[bk]["imageOnly"] is not None
            and table[bk]["imageOnly"] >= v3[bk] - 0.02],
    }
    json.dump(summary, open(ROOT / "ax9_summary.json", "w"), indent=1,
              default=str)
    print(json.dumps(summary["_champion_table"], indent=1, default=str))
    print(json.dumps(summary["_verdict"], indent=1, default=str))


if __name__ == "__main__":
    main()
