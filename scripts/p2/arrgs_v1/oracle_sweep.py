#!/usr/bin/env python3
"""Oracle sweep over the confirmed-93: deterministic S1R+S2 backbone, zero
optimization, CPU-only (skip_images). Output: evaluator crops + per-building
oracle.json + sweep summary."""
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

BASE = Path("/artifacts/JointBuildGS/phase-payloads/p2/arrgs_v1")
LABELS = Path("/artifacts/JointBuildGS/phase-payloads/p2/journal1_phase_a_v1/"
              "P2-JOURNAL1-PHASE-A-v1/labels/selection_confirm_v1.json")
E7D = Path("/artifacts/JointBuildGS/phase-payloads/p2/journal1_phase_a_v1/"
           "P2-JOURNAL1-PHASE-A-v1/a2/assets_roofer_input/E7")

arm_dir = BASE / "eval_arm_ARRGS_ORACLE"
arm_dir.mkdir(exist_ok=True)
out_root = BASE / "P2-ARRGS-ORACLE-v1/runs"
bkeys = {}
for p in E7D.glob("B*_DEBY_LOD2_*.points.ply"):
    k = p.name.replace(".points.ply", "")
    bkeys["_".join(k.split("_")[1:])] = k

ids = sorted(json.load(open(LABELS))["effective_selected_ids"])
summary = {}
for i, sid in enumerate(ids):
    bkey = bkeys.get(sid)
    if bkey is None:
        summary[sid] = {"error": "no E7 crop"}
        continue
    try:
        rs = load_real_scene({"type": "real", "stable_id": sid, "bkey": bkey,
                              "skip_images": True}, "cpu")
        arr = build_arrangement(rs["planes"], rs["footprint"], rs["ground_z"],
                                rs["top_z"], margin=1.2)
        fn = rs["o_init_fn"]
        o = [0.0 if c["fixed"] == 0.0 else
             (1.0 if fn(np.asarray(c["centroid"])) > 0.5 else 0.0)
             for c in arr["cells"]]
        faces_solid = solid_boundary_faces(arr, o)
        rd = out_root / bkey.split("_")[0]
        rd.mkdir(parents=True, exist_ok=True)
        counts = export_obj(faces_solid, rd / "s5_brep.obj", rs["ground_z"])
        xyz, cls = sample_obj(rd / "s5_brep.obj")
        if len(xyz) == 0:
            summary[sid] = {"error": "empty brep"}
            continue
        write_ply(arm_dir / f"{bkey}.points.ply", xyz, cls)
        json.dump({"groups": counts, "cells": len(arr["cells"]),
                   "s1_verdict": rs["s1_verdict"], "s1_mode": rs["s1_mode"],
                   "scientific_verdict": None}, open(rd / "oracle.json", "w"))
        summary[sid] = {"cells": len(arr["cells"]), "s1": rs["s1_verdict"]["grade"]}
        print(f"[{i+1}/{len(ids)}] {bkey.split('_')[0]} cells={len(arr['cells'])} "
              f"s1={rs['s1_verdict']['grade']}", flush=True)
    except Exception as e:
        traceback.print_exc()
        summary[sid] = {"error": str(e)[:120]}
    json.dump(summary, open(BASE / "P2-ARRGS-ORACLE-v1/sweep_summary.json", "w"),
              indent=1)
print("sweep done:", sum(1 for v in summary.values() if "error" not in v), "/", len(ids))
