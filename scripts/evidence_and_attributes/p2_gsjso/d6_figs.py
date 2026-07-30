#!/usr/bin/env python3
"""P2-D6 step0 figures (clean, communicative; replaces the cell-PCA scatter grid artifact).

fig1  curved 4906969: (left) roof cross-section profile overlay GS vs LiDAR on shared axes — same
      curved surface, GS ~33x denser; (right) per-point local-plane |residual| distribution
      GS vs LiDAR vs GS@LiDAR-density — GS not rougher than LiDAR.
fig2  facets-vs-epsilon: target-only Roofer facets vs --plane-detect-epsilon for the 3 buildings
      (GS vs LiDAR) — GS floors above LiDAR; gap invariant to threshold.
fig3  facets-vs-density: native vs LiDAR-density GS (the density-match collapse) vs LiDAR.

Runs in jointbuildgs-p0-tools:t0 (numpy + laspy + matplotlib). Observation only; verdict=김휘영.
"""
import csv, sys
from collections import defaultdict
from pathlib import Path
import numpy as np
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt

sys.path.insert(0, "/workspace/JointBuildGS/phases/p2-gsjso/scripts")
from d6_overseg_diag import (REPO, EVALROOT, footprint, read_roof, local_fit,
                             voxel_downsample_2d, FIGDIR)
PACK = REPO / "results/tum_transfer/mob/analysis_pack_d6"


def fig1_curved():
    paths, area = footprint("4906969")
    gs = read_roof(EVALROOT, "gs_d4_dense", "4906969", paths)
    li = read_roof(EVALROOT, "raw_lidar", "4906969", paths)
    li_dens = len(li) / area
    gs_dm = voxel_downsample_2d(gs, 1.0 / np.sqrt(li_dens))
    rng = np.random.default_rng(0)
    gs_plot = gs[rng.choice(len(gs), min(4000, len(gs)), replace=False)]

    fig, ax = plt.subplots(1, 2, figsize=(14, 5.5))
    # centered y-slice cross-section: |y - y_mid| < band, plot x vs z -> clean arch profile
    ymid = float(np.median(li[:, 1])); band = 1.5
    x0 = np.r_[gs[:, 0], li[:, 0]].min()
    gss = gs[np.abs(gs[:, 1] - ymid) < band]
    if len(gss) > 4000:
        gss = gss[rng.choice(len(gss), 4000, replace=False)]
    lis = li[np.abs(li[:, 1] - ymid) < band]
    ax[0].scatter(gss[:, 0] - x0, gss[:, 2], s=6, c="tab:orange", alpha=0.5,
                  label=f"GS_dense gssem ({len(gss)} in slice)")
    ax[0].scatter(lis[:, 0] - x0, lis[:, 2], s=18, c="tab:blue", alpha=0.9,
                  label=f"LiDAR ({len(lis)} in slice)")
    ax[0].set_xlabel("x - x0 (m)"); ax[0].set_ylabel("z (m)")
    ax[0].set_title(f"4906969 roof profile — centered y-slice (|y-y_mid|<{band} m): same curve, GS denser")
    ax[0].legend(loc="lower center", fontsize=8)

    # residual distribution
    rgs = local_fit(gs)[1]; rli = local_fit(li)[1]; rdm = local_fit(gs_dm)[1]
    bins = np.linspace(0, np.percentile(np.r_[rgs, rli], 98), 40)
    for r, lab, col in [(rgs, f"GS native (RMS {np.sqrt((rgs**2).mean()):.3f})", "tab:orange"),
                        (rdm, f"GS@LiDAR-dens (RMS {np.sqrt((rdm**2).mean()):.3f})", "tab:green"),
                        (rli, f"LiDAR (RMS {np.sqrt((rli**2).mean()):.3f})", "tab:blue")]:
        ax[1].hist(r, bins=bins, density=True, histtype="step", lw=2, color=col, label=lab)
    ax[1].set_xlabel("|local-plane residual| (m), 1.5 m cell PCA"); ax[1].set_ylabel("density")
    ax[1].set_title("Local roughness distribution — GS not rougher than LiDAR")
    ax[1].legend(fontsize=8)
    fig.tight_layout()
    fp = FIGDIR / "4906969_gssem_vs_lidar.png"
    fig.savefig(fp, dpi=120); plt.close(fig)
    print(f"[fig1] -> {fp}")


def fig2_epsilon():
    rows = list(csv.DictReader(open(PACK / "roofer_sweep_d6.csv")))
    piv = defaultdict(dict)
    for r in rows:
        if r["axis"] == "epsilon":
            piv[(r["target"], r["source"])][float(r["eps"])] = int(r["facets_target_only"])
    eps = sorted({float(r["eps"]) for r in rows if r["axis"] == "epsilon"})
    titles = {"4906969": "curved 4906969 (ref 3, LiDAR 5)",
              "42364659": "composite 42364659 (ref 2)", "4906972": "flat 4906972 (ref 3)"}
    fig, axs = plt.subplots(1, 3, figsize=(16, 4.6), sharey=True)
    for ax, t in zip(axs, ["4906969", "42364659", "4906972"]):
        for (tt, src), d in sorted(piv.items()):
            if tt != t:
                continue
            ys = [d.get(e) for e in eps]
            sty = dict(marker="o", lw=2)
            if src == "LiDAR":
                sty.update(color="tab:blue")
            elif src == "GS_acmp":
                sty.update(color="tab:green", ls="--")
            else:
                sty.update(color="tab:orange")
            ax.plot(eps, ys, label=src, **sty)
        ax.axhline(3, color="grey", ls=":", lw=1)
        ax.set_title(titles[t]); ax.set_xlabel("--plane-detect-epsilon (m)")
        ax.legend(fontsize=8)
    axs[0].set_ylabel("target-only roof facets")
    fig.suptitle("D6 (c) Roofer epsilon sweep — GS floors above LiDAR; gap invariant to threshold")
    fig.tight_layout()
    fp = FIGDIR / "facets_vs_epsilon.png"
    fig.savefig(fp, dpi=120); plt.close(fig)
    print(f"[fig2] -> {fp}")


if __name__ == "__main__":
    FIGDIR.mkdir(parents=True, exist_ok=True)
    fig1_curved()
    fig2_epsilon()
