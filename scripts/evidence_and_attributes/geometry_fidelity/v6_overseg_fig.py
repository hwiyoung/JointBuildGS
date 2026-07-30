#!/usr/bin/env python3
"""P2 v6 over-seg figure — representative rough-vs-smooth roof pair (4906972).
Top-view roof points (building class-6) coloured by signed residual to the dominant plane
(±0.4 m), per arm, annotated with patch_rms / ransac / Roofer facet. Shows GS surface is
locally SMOOTH yet Roofer emits many facets -> (나). Read-only, p0-tools (matplotlib Agg).
Out: docs/figs/tum_transfer/v6_overseg_4906972.png
"""
import csv
from pathlib import Path
import numpy as np, laspy
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

REPO = "/workspace/JointBuildGS"
EVALROOT = f"{REPO}/phases/p0-audit/runs/mob_eval"
BID = "DEBY_LOD2_4906972"
PANELS = [("GS_dense", "gs_seed_dense"), ("raw_dense", "raw_dense"), ("LiDAR", "raw_lidar")]
CSV = f"{REPO}/results/tum_transfer/mob/analysis_pack_v6/overseg_diag.csv"


def main():
    met = {}
    for r in csv.DictReader(open(CSV)):
        if r["building"] == "4906972":
            met[r["arm"]] = r

    fig, axes = plt.subplots(1, len(PANELS), figsize=(5 * len(PANELS), 4.6))
    for ax, (label, arm) in zip(axes, PANELS):
        c = laspy.read(f"{EVALROOT}/{arm}/{BID}_orig_classified.las")
        cl = np.asarray(c.classification)
        P = np.column_stack([np.asarray(c.x), np.asarray(c.y), np.asarray(c.z)])[cl == 6]
        cen = P.mean(0); _, _, Vt = np.linalg.svd(P - cen, full_matrices=False)
        res = (P - cen) @ Vt[-1]                      # signed residual to dominant plane
        sc = ax.scatter(P[:, 0] - cen[0], P[:, 1] - cen[1], c=np.clip(res, -0.4, 0.4),
                        cmap="coolwarm", s=2, vmin=-0.4, vmax=0.4, linewidths=0)
        m = met.get(label, {})
        ax.set_title(f"{label}  n={len(P):,}\npatchRMS={m.get('patch_rms_med_m')}m  "
                     f"ransac={m.get('ransac_planes')}  Roofer={m.get('roofer_facet')}", fontsize=10)
        ax.set_aspect("equal"); ax.set_xlabel("x (m)"); ax.set_ylabel("y (m)")
    cb = fig.colorbar(sc, ax=axes, fraction=0.025, pad=0.02)
    cb.set_label("signed residual to dominant plane (m)")
    fig.suptitle("v6 over-seg - 4906972 (ref RoofSurface=3): GS roof locally smooth (low patch-RMS) "
                 "yet Roofer over-splits -> threshold-driven (B). Observation only.", fontsize=11)
    out = Path(f"{REPO}/docs/figs/tum_transfer/v6_overseg_4906972.png")
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=130, bbox_inches="tight")
    print(f"[done] -> {out}")


if __name__ == "__main__":
    main()
