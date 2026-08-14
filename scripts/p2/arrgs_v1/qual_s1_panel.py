#!/usr/bin/env python3
"""S1 QA: do the candidate planes explain the ALS roof points?

Per building: ALS class-6 points colored by nearest candidate plane
(within tol), grey = unexplained; prints per-plane share + total explained
fraction. The S1 quality number is `explained@0.3m` — if low, everything
downstream is starved regardless of the optimizer.
"""
import json
import sys

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

B = "/artifacts/JointBuildGS/phase-payloads/p2/arrgs_v1"
E7D = ("/artifacts/JointBuildGS/phase-payloads/p2/journal1_phase_a_v1/"
       "P2-JOURNAL1-PHASE-A-v1/a2/assets_roofer_input/E7")

sys.path.insert(0, "/workspace/JointBuildGS/scripts/p2/arrgs_v1")
from real_scene import read_ply_xyzc  # noqa: E402

RUNS = [("P2-ARRGS-X1-v1/runs/B022_clean", "B022", "B022_DEBY_LOD2_4906965"),
        ("P2-ARRGS-X2-v1/runs/B173_changed", "B173", "B173_DEBY_LOD2_4959326"),
        ("P2-ARRGS-X2-v1/runs/B036_hole", "B036", "B036_DEBY_LOD2_4906982")]
TOL = 0.3
COLORS = ["#c05038", "#4a9eff", "#50d890", "#ffd866", "#b07fd0", "#ff9060",
          "#60c0b0", "#d05880", "#90a840", "#6080e0"]

fig = plt.figure(figsize=(15, 10))
for col, (run, label, bkey) in enumerate(RUNS):
    s1 = json.load(open(f"{B}/{run}/s1_candidates.json"))
    planes = [p for p in s1["planes"] if p["source"] in ("prior_als", "mvs")]
    xyz, cls = read_ply_xyzc(f"{E7D}/{bkey}.points.ply")
    roof = xyz[cls == 6] if cls is not None else xyz
    sub = roof[::max(1, len(roof) // 60000)]
    # nearest-plane assignment
    D = np.full(len(sub), 1e9)
    A = np.full(len(sub), -1)
    for j, p in enumerate(planes):
        n = np.asarray(p["n"]); d = p["d"]
        r = np.abs(sub @ n - d)
        m = r < np.minimum(D, TOL)
        A[m] = j
        D = np.minimum(D, r)
    explained = float((A >= 0).mean())
    stats = []
    for j, p in enumerate(planes):
        share = float((A == j).mean())
        stats.append(f"{p['id']}({p['source'][0]}|nz{abs(p['n'][2]):.2f}):{share:.2f}")
    print(f"[{label}] planes={len(planes)} explained@{TOL}m={explained:.2f} | " +
          " ".join(stats))
    for row, (elev, azim) in enumerate([(60, -60), (8, -60)]):
        ax = fig.add_subplot(2, 3, row * 3 + col + 1, projection="3d")
        grey = A < 0
        ax.scatter(sub[grey, 0], sub[grey, 1], sub[grey, 2], s=0.4, c="#909090",
                   alpha=0.4)
        for j in range(len(planes)):
            m = A == j
            if m.any():
                ax.scatter(sub[m, 0], sub[m, 1], sub[m, 2], s=0.4,
                           c=COLORS[j % len(COLORS)], alpha=0.7)
        mid = sub.mean(0)
        r = (sub.max(0) - sub.min(0)).max() / 2
        ax.set_xlim(mid[0] - r, mid[0] + r)
        ax.set_ylim(mid[1] - r, mid[1] + r)
        ax.set_zlim(mid[2] - r, mid[2] + r)
        ax.view_init(elev, azim)
        ax.set_axis_off()
        if row == 0:
            ax.set_title(f"{label} — S1 explained {explained:.0%}\n"
                         f"(color=assigned plane, grey=unexplained)", fontsize=9)
fig.tight_layout()
fig.savefig(f"{B}/qual_s1_planes_vs_als.png", dpi=90, facecolor="white")
print("saved", f"{B}/qual_s1_planes_vs_als.png")
