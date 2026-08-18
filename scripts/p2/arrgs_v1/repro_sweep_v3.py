#!/usr/bin/env python3
"""v3-reproduction sweep over the confirmed-93 (AX-2 update): deterministic
S1+S2 backbone with the v3 input configuration (tower candidates + multi-point
cell labelling + top_cluster surface), zero optimization, CPU-only.

Pre-registered expectations (2026-08-17, scientific_verdict stays null):
  1. Population effect: buildings whose v1 deficit came from missing vertical
     partitions (B022 profile) improve; B022 itself reproduces ~+0.086.
  2. Guard at population scale: regressions (v3 - v1 < -0.02) affect <= 10%
     of scored buildings. More -> the v3 guards (bimodality gate, cluster
     area bounds) are insufficient outside the triad; tighten before v3
     becomes the default input configuration.
  3. Output contract: per-building v1/v3 proxy-f1 (model samples vs E1 cls6,
     tau=0.5 -- relative use only), delta ranking, improvement population
     size (delta > +0.02), regression list.
v1 arm = existing P2-ARRGS-ORACLE-v1 breps re-scored with the same recipe
(their sweep recorded no f1); v3 arm = fresh backbone with centroid+vertex
multi-point labelling hardened at 0.5 (arrgs_train semantics).

Usage (CPU container): repro_sweep_v3.py [start_idx]
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
from export_eval_points import sample_obj, write_ply  # noqa: E402
from anchor_sweep import read_ply_xyz_cls, f1_proxy, E1_DIR  # noqa: E402

BASE = Path("/artifacts/JointBuildGS/phase-payloads/p2/arrgs_v1")
LABELS = Path("/artifacts/JointBuildGS/phase-payloads/p2/journal1_phase_a_v1/"
              "P2-JOURNAL1-PHASE-A-v1/labels/selection_confirm_v1.json")
E7D = Path("/artifacts/JointBuildGS/phase-payloads/p2/journal1_phase_a_v1/"
           "P2-JOURNAL1-PHASE-A-v1/a2/assets_roofer_input/E7")
V1_RUNS = BASE / "P2-ARRGS-ORACLE-v1/runs"
ROOT = BASE / "P2-ARRGS-REPRO-V3-v1"
ARM = BASE / "eval_arm_ARRGS_REPRO_V3"


def score_obj(obj_path, ref6):
    xyz, cls = sample_obj(obj_path)
    if len(xyz) == 0:
        return None
    return f1_proxy(xyz[cls == 6], ref6)


def main():
    start = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    (ROOT / "runs").mkdir(parents=True, exist_ok=True)
    ARM.mkdir(exist_ok=True)
    sp = ROOT / "sweep_summary.json"
    summary = json.load(open(sp)) if sp.is_file() else {}

    bkeys = {}
    for p in E7D.glob("B*_DEBY_LOD2_*.points.ply"):
        k = p.name.replace(".points.ply", "")
        bkeys["_".join(k.split("_")[1:])] = k
    ids = sorted(json.load(open(LABELS))["effective_selected_ids"])

    for i, sid in enumerate(ids):
        if i < start:
            continue
        bkey = bkeys.get(sid)
        if bkey is None:
            summary[sid] = {"error": "no E7 crop"}
            continue
        bidx = bkey.split("_")[0]
        if summary.get(sid, {}).get("f1_v3") is not None:
            print(f"[{i+1}/{len(ids)}] {bidx} skip done", flush=True)
            continue
        try:
            ref_xyz, ref_cls = read_ply_xyz_cls(E1_DIR / f"{bkey}.points.ply")
            ref6 = ref_xyz[ref_cls == 6] if ref_cls is not None else ref_xyz
            row = {}
            v1_obj = V1_RUNS / bidx / "s5_brep.obj"
            s1 = score_obj(v1_obj, ref6) if v1_obj.is_file() else None
            row["f1_v1"] = s1["f1"] if s1 else None

            rs = load_real_scene({"type": "real", "stable_id": sid,
                                  "bkey": bkey, "skip_images": True,
                                  "o_init_variant": "top_cluster",
                                  "tower_candidates": True}, "cpu")
            arr = build_arrangement(rs["planes"], rs["footprint"],
                                    rs["ground_z"], rs["top_z"], margin=1.2)
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
            rd = ROOT / "runs" / bidx
            rd.mkdir(parents=True, exist_ok=True)
            counts = export_obj(solid_boundary_faces(arr, o),
                                rd / "s5_brep.obj", rs["ground_z"])
            s3 = score_obj(rd / "s5_brep.obj", ref6)
            if s3 is None:
                summary[sid] = {"error": "empty v3 brep", **row}
                continue
            xyz, cls = sample_obj(rd / "s5_brep.obj")
            write_ply(ARM / f"{bkey}.points.ply", xyz, cls)
            n_tower = sum(1 for p in rs["planes"]
                          if str(p.get("id", "")).startswith("twr"))
            json.dump({"groups": counts, "cells": len(arr["cells"]),
                       "n_tower_planes": n_tower,
                       "s1_verdict": rs["s1_verdict"],
                       "f1_proxy_e1": s3, "f1_proxy_e1_v1": s1,
                       "scientific_verdict": None},
                      open(rd / "repro_v3.json", "w"), default=str)
            row.update({"f1_v3": s3["f1"], "cells": len(arr["cells"]),
                        "n_tower_planes": n_tower,
                        "s1": rs["s1_verdict"]["grade"]})
            if row["f1_v1"] is not None:
                row["delta"] = round(row["f1_v3"] - row["f1_v1"], 4)
            summary[sid] = row
            print(f"[{i+1}/{len(ids)}] {bidx} v1={row['f1_v1']} "
                  f"v3={row['f1_v3']} d={row.get('delta')} "
                  f"tower={n_tower}", flush=True)
        except Exception as e:
            traceback.print_exc()
            summary[sid] = {"error": str(e)[:120]}
        json.dump(summary, open(sp, "w"), indent=1, default=str)

    # ranking + verdict block
    rows = [(sid, v) for sid, v in summary.items()
            if isinstance(v, dict) and v.get("delta") is not None]
    rows.sort(key=lambda kv: kv[1]["delta"], reverse=True)
    improved = [s for s, v in rows if v["delta"] > 0.02]
    regressed = [s for s, v in rows if v["delta"] < -0.02]
    summary["_verdict"] = {
        "scientific_verdict": None,
        "n_scored": len(rows),
        "n_improved_gt_0.02": len(improved),
        "n_regressed_lt_-0.02": len(regressed),
        "prereg_2_regression_le_10pct":
            len(rows) > 0 and len(regressed) <= 0.10 * len(rows),
        "top10_delta": [(s, summary[s]["delta"]) for s, _ in
                        [(s, v) for s, v in rows[:10]]],
        "bottom5_delta": [(s, summary[s]["delta"]) for s, _ in
                          [(s, v) for s, v in rows[-5:]]],
    }
    json.dump(summary, open(sp, "w"), indent=1, default=str)
    print("[repro-v3] done:", json.dumps(summary["_verdict"], indent=1,
                                         default=str))


if __name__ == "__main__":
    main()
