#!/usr/bin/env python3
"""Oracle-occupancy probe: S1R candidates + S2 init hypothesis, ZERO optimization.

Hardens o_init directly (o>0.5 -> solid), extracts the boundary B-rep and
exports evaluator crops. This isolates where the score ceiling really is:
  oracle ~= optimized  -> bottleneck is representation/metric semantics, NOT S3+4
  oracle >> optimized  -> the optimizer actively degrades the init hypothesis
  oracle << optimized  -> the optimizer adds value (insufficiently)
"""
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from real_scene import load_real_scene  # noqa: E402
from arrangement import build_arrangement  # noqa: E402
from arrgs_train import solid_boundary_faces, export_obj  # noqa: E402
from export_eval_points import sample_obj, write_ply  # noqa: E402

BASE = Path("/artifacts/JointBuildGS/phase-payloads/p2/arrgs_v1")
E2 = ("/artifacts/JointBuildGS/phase-payloads/p2/e1_e6_roofer_ox_review_v1/"
     "P2-E1-E6-GATE5-DASHBOARD-v1/assets_roofer_input/E2")
BUILDINGS = [("DEBY_LOD2_4906965", "B022_DEBY_LOD2_4906965"),
             ("DEBY_LOD2_4959326", "B173_DEBY_LOD2_4959326"),
             ("DEBY_LOD2_4906982", "B036_DEBY_LOD2_4906982")]

arm_dir = BASE / "eval_arm_ARRGS_ORACLE"
arm_dir.mkdir(exist_ok=True)
out_root = BASE / "P2-ARRGS-ORACLE-v1/runs"

for sid, bkey in BUILDINGS:
    rs = load_real_scene({"type": "real", "stable_id": sid, "bkey": bkey,
                          "e2_dir": E2, "max_views": 8, "image_scale": 0.4}, "cpu")
    arr = build_arrangement(rs["planes"], rs["footprint"], rs["ground_z"],
                            rs["top_z"], margin=1.2)
    o = []
    fn = rs["o_init_fn"]
    for c in arr["cells"]:
        o.append(0.0 if c["fixed"] == 0.0 else
                 (1.0 if fn(np.asarray(c["centroid"])) > 0.5 else 0.0))
    faces_solid = solid_boundary_faces(arr, o)
    rd = out_root / bkey.split("_")[0]
    rd.mkdir(parents=True, exist_ok=True)
    counts = export_obj(faces_solid, rd / "s5_brep.obj", rs["ground_z"])
    xyz, cls = sample_obj(rd / "s5_brep.obj")
    write_ply(arm_dir / f"{bkey}.points.ply", xyz, cls)
    json.dump({"groups": counts, "cells": len(arr["cells"]),
               "solid_cells": int(sum(1 for v in o if v > 0.5)),
               "s1_verdict": rs["s1_verdict"], "scientific_verdict": None},
              open(rd / "oracle.json", "w"), indent=1)
    print(f"[oracle] {bkey.split('_')[0]}: cells={len(arr['cells'])} "
          f"solid={sum(1 for v in o if v > 0.5)} groups={counts} pts={len(xyz)}")
print("done")
