#!/usr/bin/env python3
"""P2 make-or-break figures: input GS point clouds (quality + recovery), height/ref-distance coloured.
Runs in P0 tools container (matplotlib + numpy). Writes to docs/figs/tum_transfer/."""
import json, sys
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.path import Path as MplPath

REPO = "/workspace/JointBuildGS"
ARMS = ["vanilla", "baseline", "mutual", "structure", "both"]
FIGDIR = f"{REPO}/docs/figs/tum_transfer"
geo = json.load(open(f"{REPO}/results/tum_transfer/analysis/footprints_aoi.geojson"))["features"]
base = json.load(open(f"{REPO}/results/tum_transfer/mob/baselines.json"))


def ring(bid):
    g = [f for f in geo if f["properties"]["building_id"] == bid][0]["geometry"]
    return np.asarray(g["coordinates"][0] if g["type"] == "Polygon" else g["coordinates"][0][0])[:, :2]


def clip(npz, bid, buf=2.0):
    P = np.load(npz)["P_utm_clean"]
    r = ring(bid); fp = MplPath(r)
    x0, y0, x1, y1 = r[:, 0].min() - buf, r[:, 1].min() - buf, r[:, 0].max() + buf, r[:, 1].max() + buf
    m = (P[:, 0] >= x0) & (P[:, 0] <= x1) & (P[:, 1] >= y0) & (P[:, 1] <= y1)
    return P[m]


def sub(P, n=40000):
    if len(P) <= n:
        return P
    return P[np.random.default_rng(0).choice(len(P), n, replace=False)]


def quality_fig(bid, facets, rms):
    fig, axes = plt.subplots(2, len(ARMS), figsize=(3.0 * len(ARMS), 6))
    r = ring(bid)
    for j, a in enumerate(ARMS):
        P = sub(clip(f"{REPO}/results/tum_transfer/mob/tsdf_{a}.npz", bid))
        for i, (ix, iz, lab) in enumerate([(0, 1, "top (x-y)"), (0, 2, "side (x-z)")]):
            ax = axes[i, j]
            if len(P):
                c = P[:, 2]
                ax.scatter(P[:, ix], P[:, iz], c=c, s=0.4, cmap="viridis", linewidths=0)
            if i == 0:
                ax.plot(np.append(r[:, 0], r[0, 0]), np.append(r[:, 1], r[0, 1]), "r-", lw=1.0)
                ax.set_aspect("equal")
            ax.set_xticks([]); ax.set_yticks([])
            if i == 0:
                ax.set_title(f"{a}\nfacets={facets.get(a,'?')} RMS={rms.get(a,'?')}m", fontsize=9)
            if j == 0:
                ax.set_ylabel(lab, fontsize=9)
    fig.suptitle(f"{bid} (ref roof faces={base[bid]['ref_roof_surfaces']}) — GS TSDF input, coloured by height",
                 fontsize=11)
    fig.tight_layout()
    out = f"{FIGDIR}/mob_quality_{bid.split('_')[-1]}.png"
    fig.savefig(out, dpi=110); plt.close(fig)
    print("wrote", out)


def recovery_fig(bids):
    fig, axes = plt.subplots(2, len(bids), figsize=(3.2 * len(bids), 6.2))
    if len(bids) == 1:
        axes = axes.reshape(2, 1)
    for j, bid in enumerate(bids):
        r = ring(bid)
        for i, a in enumerate(["vanilla", "both"]):
            ax = axes[i, j]
            P = sub(clip(f"{REPO}/results/tum_transfer/mob/tsdf_{a}.npz", bid))
            if len(P):
                ax.scatter(P[:, 0], P[:, 1], c=P[:, 2], s=0.6, cmap="viridis", linewidths=0)
            ax.plot(np.append(r[:, 0], r[0, 0]), np.append(r[:, 1], r[0, 1]), "r-", lw=1.2)
            ax.set_aspect("equal"); ax.set_xticks([]); ax.set_yticks([])
            if i == 0:
                ax.set_title(f"{bid.split('_')[-1]} (ref {base[bid]['ref_roof_surfaces']} faces)\n"
                             f"sfm-seed pts in fp", fontsize=9)
            if j == 0:
                ax.set_ylabel(f"{a}\nTSDF top", fontsize=9)
            ax.text(0.5, -0.08, f"{a}: {len(clip(f'{REPO}/results/tum_transfer/mob/tsdf_{a}.npz', bid))} pts",
                    transform=ax.transAxes, ha="center", fontsize=8)
    fig.suptitle("Recovery axis — seeding split: reconstructed (left) vs textureless no-seed (right)", fontsize=11)
    fig.tight_layout()
    out = f"{FIGDIR}/mob_recovery_split.png"
    fig.savefig(out, dpi=110); plt.close(fig)
    print("wrote", out)


if __name__ == "__main__":
    import os
    os.makedirs(FIGDIR, exist_ok=True)
    # quality control 4906972: facets (orig) + RMS (orig) from eval
    facets = {"vanilla": 17, "baseline": 12, "mutual": 26, "structure": 7, "both": 29}
    rms = {"vanilla": 4.63, "baseline": 1.18, "mutual": 2.69, "structure": 1.14, "both": 3.80}
    quality_fig("DEBY_LOD2_4906972", facets, rms)
    recovery_fig(["DEBY_LOD2_42364659", "DEBY_LOD2_42364663", "DEBY_LOD2_4907182", "DEBY_LOD2_4908176"])
    print("[done]")
