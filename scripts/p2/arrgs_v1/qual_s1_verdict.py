#!/usr/bin/env python3
"""S1 verdict maps: top-view coverage of candidate planes over (a) ALS input
and (b) E1 current GT. Grey = no candidate plane within tol -> unreachable by
S5 no matter what the optimizer does (the S1 ceiling).
"""
import json
import sys

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

B = "/artifacts/JointBuildGS/phase-payloads/p2/arrgs_v1"
A2 = ("/artifacts/JointBuildGS/phase-payloads/p2/journal1_phase_a_v1/"
      "P2-JOURNAL1-PHASE-A-v1/a2/assets_roofer_input")
OX = ("/artifacts/JointBuildGS/phase-payloads/p2/e1_e6_roofer_ox_review_v1/"
      "P2-E1-E6-GATE5-DASHBOARD-v1/assets_roofer_input")

sys.path.insert(0, "/workspace/JointBuildGS/scripts/p2/arrgs_v1")
from real_scene import read_ply_xyzc  # noqa: E402

RUNS = [("P2-ARRGS-X1-v1/runs/B022_clean", "B022", "B022_DEBY_LOD2_4906965"),
        ("P2-ARRGS-X2-v1/runs/B173_changed", "B173", "B173_DEBY_LOD2_4959326"),
        ("P2-ARRGS-X2-v1/runs/B036_hole", "B036", "B036_DEBY_LOD2_4906982")]
TOL = 0.3
COLORS = ["#c05038", "#4a9eff", "#50d890", "#ffd866", "#b07fd0", "#ff9060",
          "#60c0b0", "#d05880", "#90a840", "#6080e0"]

fig, axes = plt.subplots(2, 3, figsize=(15, 10))
summary = {}
for col, (run, label, bkey) in enumerate(RUNS):
    s1 = json.load(open(f"{B}/{run}/s1_candidates.json"))
    planes = [p for p in s1["planes"] if p["source"] in ("prior_als", "mvs")]
    fp = np.asarray(s1["footprint"])
    sources = [("ALS input", f"{A2}/E7/{bkey}.points.ply"),
               ("E1 current GT", f"{OX}/E1/{bkey}.points.ply")]
    for row, (sname, path) in enumerate(sources):
        xyz, cls = read_ply_xyzc(path)
        roof = xyz[cls == 6] if cls is not None else xyz
        sub = roof[::max(1, len(roof) // 80000)]
        D = np.full(len(sub), 1e9)
        Aidx = np.full(len(sub), -1)
        for j, p in enumerate(planes):
            n = np.asarray(p["n"]); d = p["d"]
            r = np.abs(sub @ n - d)
            m = r < np.minimum(D, TOL)
            Aidx[m] = j
            D = np.minimum(D, r)
        expl = float((Aidx >= 0).mean())
        summary[f"{label}|{sname}"] = expl
        ax = axes[row][col]
        grey = Aidx < 0
        ax.scatter(sub[grey, 0], sub[grey, 1], s=0.5, c="#666666", alpha=0.6)
        for j in range(len(planes)):
            m = Aidx == j
            if m.any():
                ax.scatter(sub[m, 0], sub[m, 1], s=0.5,
                           c=COLORS[j % len(COLORS)], alpha=0.7)
        ax.plot(np.r_[fp[:, 0], fp[0, 0]], np.r_[fp[:, 1], fp[0, 1]],
                "k-", lw=1.2)
        ax.set_aspect("equal")
        ax.set_xticks([]); ax.set_yticks([])
        ok = expl >= 0.9
        ax.set_title(f"{label} | {sname} - explained {expl:.0%} [{'PASS' if ok else 'FAIL'}]",
                     fontsize=11, color=("#207020" if ok else "#b03030"))
        if row == 0 and col == 0:
            ax.text(0.02, 0.02, "color = assigned plane / grey = NO candidate (unreachable by S5)\nblack = footprint", transform=ax.transAxes, fontsize=8,
                    va="bottom")
fig.suptitle("S1 verdict maps - EXPECTED: almost no grey (explained >= 90%)", fontsize=13)
fig.tight_layout()
fig.savefig(f"{B}/qual_s1_verdict.png", dpi=95, facecolor="white")
print(json.dumps(summary, indent=1, ensure_ascii=False))
print("saved", f"{B}/qual_s1_verdict.png")
