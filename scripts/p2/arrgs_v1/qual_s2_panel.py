#!/usr/bin/env python3
"""S2 QA: are the gaussian seeds where they should be?

Expected: seeds sit ON candidate faces (planar sheets), roof-candidate faces
carry the bulk of the budget near the ALS surface, walls get the rest; free
cells' o_init agrees with the ALS column surface.

Reconstructs seeds deterministically from the stored arrangement (same
seed_faces call as training) and plots top + side views colored by the source
of the face's plane, with ALS points (grey) as reference.
"""
import json
import sys

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

sys.path.insert(0, "/workspace/JointBuildGS/scripts/p2/arrgs_v1")
from arrgs_model import seed_faces  # noqa: E402
from real_scene import read_ply_xyzc  # noqa: E402

B = "/artifacts/JointBuildGS/phase-payloads/p2/arrgs_v1"
A2 = ("/artifacts/JointBuildGS/phase-payloads/p2/journal1_phase_a_v1/"
      "P2-JOURNAL1-PHASE-A-v1/a2/assets_roofer_input")
RUNS = [("P2-ARRGS-X1-v1/runs/B022_clean", "B022", "B022_DEBY_LOD2_4906965"),
        ("P2-ARRGS-X2-v1/runs/B173_changed", "B173", "B173_DEBY_LOD2_4959326"),
        ("P2-ARRGS-X2-v1/runs/B036_hole", "B036", "B036_DEBY_LOD2_4906982")]
SRC_COL = {"prior_als": "#4a9eff", "mvs": "#ffa040", "footprint": "#777777",
           "domain": "#3a3a3a"}

fig, axes = plt.subplots(2, 3, figsize=(16, 9))
for col, (run, label, bkey) in enumerate(RUNS):
    s1 = json.load(open(f"{B}/{run}/s1_candidates.json"))
    s2 = json.load(open(f"{B}/{run}/s2_arrangement.json"))
    cfg = json.load(open(f"{B}/{run}/run.json"))["config"]
    srcOf = {p["id"]: p["source"] for p in s1["planes"]}
    arr = {"cells": s2["cells"], "faces": s2["faces"]}
    seeds = seed_faces(arr, target_total=cfg.get("gaussians", 9000))
    xyz = seeds["xyz"]
    src = np.array([srcOf.get(s2["faces"][fi]["plane_id"], "domain")
                    for fi in seeds["face_idx"]])
    als, cls = read_ply_xyzc(f"{A2}/E7/{bkey}.points.ply")
    als = als[::max(1, len(als) // 40000)]
    shares = {k: float((src == k).mean()) for k in SRC_COL}
    free = [c for c in s2["cells"] if c["fixed"] is None]
    print(f"[{label}] seeds={len(xyz)} shares=" +
          " ".join(f"{k}:{v:.2f}" for k, v in shares.items() if v > 0) +
          f" | cells free/fixed={len(free)}/{len(s2['cells']) - len(free)}"
          f" | o_init solid={sum(1 for c in free if c.get('o_init', 0) > 0.5)}")
    for row, (dims, name) in enumerate([((0, 1), "top XY"), ((0, 2), "side XZ")]):
        ax = axes[row][col]
        ax.scatter(als[:, dims[0]], als[:, dims[1]], s=0.3, c="#cccccc", alpha=0.5)
        for k, c in SRC_COL.items():
            m = src == k
            if m.any():
                ax.scatter(xyz[m, dims[0]], xyz[m, dims[1]], s=0.8, c=c, alpha=0.6)
        ax.set_aspect("equal")
        ax.set_xticks([]); ax.set_yticks([])
        if row == 0:
            ax.set_title(f"{label} — seeds {len(xyz)} "
                         f"(prior {shares['prior_als']:.0%} / mvs {shares['mvs']:.0%} / "
                         f"wall {shares['footprint']:.0%})", fontsize=10)
        else:
            ax.set_title(name, fontsize=8)
fig.suptitle("S2 seeds (blue=prior-plane faces, orange=MVS, grey pts=ALS ref, "
             "dark=domain) — EXPECTED: colored seeds hug the grey surface; walls vertical",
             fontsize=11)
fig.tight_layout()
fig.savefig(f"{B}/qual_s2_seeds.png", dpi=95, facecolor="white")
print("saved", f"{B}/qual_s2_seeds.png")
