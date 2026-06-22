#!/usr/bin/env python3
"""P2 impl ② figure: per-building roof-class Gaussian z-range [prior-init | A | B] vs reference roof.
Runs in P0 tools container (matplotlib). Reads depth_release_convergence.json."""
import json
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

REPO = "/workspace/JointBuildGS"
rows = json.load(open(f"{REPO}/results/tum_transfer/mob_analysis/depth_release_convergence.json"))
fig, ax = plt.subplots(figsize=(13, 6))
cond_keys = [("prior", "#9e9e9e", "prior-init (A carve)"), ("A", "#1f77b4", "A after (honest)"),
             ("B", "#d62728", "B after (oracle)")]
xticks, xlabels = [], []
for i, r in enumerate(rows):
    base = i * 4
    for j, (k, c, _) in enumerate(cond_keys):
        s = r[k]; x = base + j
        if s is not None:
            ax.add_patch(plt.Rectangle((x - 0.35, s["p5"]), 0.7, s["p95"] - s["p5"],
                                       color=c, alpha=0.45, ec=c))
            ax.plot([x - 0.35, x + 0.35], [s["med"], s["med"]], color=c, lw=2.2)
        else:
            ax.text(x, r["ref_roof_local"], "none", ha="center", va="bottom", fontsize=7, color=c)
    # reference roof as a black line across the group
    ax.plot([base - 0.5, base + 2.5], [r["ref_roof_local"]] * 2, "k-", lw=2.0)
    xticks.append(base + 1)
    xlabels.append(f"{r['bid'].split('_')[-1]}\n({r['klass']})")
ax.set_xticks(xticks); ax.set_xticklabels(xlabels, fontsize=8)
ax.set_ylabel("roof-class Gaussian z (GS-local, m)")
ax.axvline(5 * 4 - 0.7, color="gray", ls=":", lw=1)
ax.text(2 * 4, ax.get_ylim()[1], "textureless (no-seed)", ha="center", fontsize=9, color="#555")
ax.text(6 * 4, ax.get_ylim()[1], "control", ha="center", fontsize=9, color="#555")
handles = [plt.Rectangle((0, 0), 1, 1, color=c, alpha=0.45) for _, c, _ in cond_keys]
handles.append(plt.Line2D([0], [0], color="k", lw=2))
ax.legend(handles, [l for _, _, l in cond_keys] + ["reference roof"], loc="lower right", fontsize=8)
ax.set_title("P2 ② depth coupling — roof-class Gaussian height: prior-init / A(honest) / B(oracle) vs reference roof\n"
             "(bar = [p5,p95] z-range, line = median; reference = black)", fontsize=10)
fig.tight_layout()
out = f"{REPO}/docs/figs/tum_transfer/depth_release_convergence.png"
fig.savefig(out, dpi=120); print("wrote", out)
