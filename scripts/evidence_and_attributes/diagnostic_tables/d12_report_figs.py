#!/usr/bin/env python3
"""Report-evidence qualitative figures (reuse existing eval outputs, no retrain):
 (a) linchpin recovery: raw-DIM point cloud (assembly fail) -> GS Roofer model -> reference LoD2.
 (b) over-seg: reference/ALS vs GS facets (per-facet color).
 (c) textureless 4907182: DIM point cloud (empty) vs ALS (full).
Runs in p0-tools. Observe only. Out: docs/figs/W_report_evidence/{a_recovery,b_overseg,c_textureless}.png
"""
import sys
from pathlib import Path
import numpy as np
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.cm as cm
REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))
from scripts.evidence_and_attributes.geometry_fidelity.d6_shape_audit import footprint_paths, read_cloud, roof_envelope, gml_building
from scripts.evidence_and_attributes.geometry_fidelity.overseg_analysis import parse_solid_roof

FIG = Path("/workspace/JointBuildGS/docs/figs/W_report_evidence"); FIG.mkdir(parents=True, exist_ok=True)


def draw_facets(ax, arm, bid, title):
    pr = parse_solid_roof(arm, bid)
    if pr is None:
        ax.text(0.5, 0.5, f"{arm}\n(no solid)", ha="center"); ax.set_axis_off(); return
    rf, V = pr
    cz = np.concatenate([V[r][:, 2] for r in rf]) if rf else np.array([0, 1])
    sm = cm.ScalarMappable(cmap="tab20");
    for i, r in enumerate(rf):
        ax.fill(V[r][:, 0], V[r][:, 1], color=cm.tab20(i % 20), alpha=0.85, edgecolor="k", lw=0.5)
    ax.set_aspect("equal"); ax.set_axis_off(); ax.set_title(f"{title}\n{len(rf)} facets", fontsize=9)


def draw_cloud(ax, arm, bid, title):
    paths = footprint_paths(bid)
    c = read_cloud(arm, bid, paths)
    if c is None or len(c) == 0:
        ax.text(0.5, 0.5, f"{title}\n(EMPTY / no points)", ha="center", color="red"); ax.set_axis_off(); return 0
    e = roof_envelope(c) if len(c) else c
    ax.scatter(e[:, 0], e[:, 1], c=e[:, 2], cmap="viridis", s=5)
    ax.set_aspect("equal"); ax.set_axis_off(); ax.set_title(f"{title}\n{len(c)} pts", fontsize=9)
    return len(c)


def draw_ref(ax, bid, title):
    rt, roof, wall = gml_building(bid)
    if not roof:
        ax.text(0.5, 0.5, f"ref\n(none)", ha="center"); ax.set_axis_off(); return
    for r in roof:
        ax.fill(r[:, 0], r[:, 1], alpha=0.4, edgecolor="g", lw=1.2, facecolor="lightgreen")
    ax.set_aspect("equal"); ax.set_axis_off(); ax.set_title(f"{title} (roofType {rt})\n{len(roof)} ref facets", fontsize=9)


def main():
    # (a) linchpin recovery — 42364659 (raw-DIM assembly fail; GS assembled; LiDAR also fail=GS-only)
    b = "42364659"
    fig, axs = plt.subplots(1, 4, figsize=(18, 5))
    draw_cloud(axs[0], "raw_dense", b, "raw-DIM points (assembly FAIL)")
    draw_facets(axs[1], "gs_seed_dense", b, "GS-JSO model (assembled)")
    draw_facets(axs[2], "gs_d4_dense", b, "GS-d4 model")
    draw_ref(axs[3], b, "reference LoD2")
    fig.suptitle(f"(a) LINCHPIN recovery {b}: raw-DIM 0-facet assembly FAIL -> GS-JSO assembled (LiDAR also failed = GS-only)", fontsize=11)
    fig.tight_layout(rect=[0, 0, 1, 0.94]); fig.savefig(FIG / "a_recovery.png", dpi=110); plt.close(fig)
    print("(a) a_recovery.png")

    # (b) over-seg — 4906972 (ref 3): gs_seed_dense (15, v6) vs gs_d4 (4, D4) vs reference
    b = "4906972"
    fig, axs = plt.subplots(1, 3, figsize=(14, 5))
    draw_ref(axs[0], b, "reference LoD2")
    draw_facets(axs[1], "gs_seed_dense", b, "GS v6-seed (over-seg)")
    draw_facets(axs[2], "gs_d4_dense", b, "GS-d4 (cp-normalized)")
    fig.suptitle(f"(b) OVER-SEG {b}: ref 3 facets vs GS v6-seed (15) vs GS-d4 (4) — cp-normalization controls facet count", fontsize=11)
    fig.tight_layout(rect=[0, 0, 1, 0.94]); fig.savefig(FIG / "b_overseg.png", dpi=110); plt.close(fig)
    print("(b) b_overseg.png")

    # (c) textureless 4907182 — DIM points (empty) vs ALS (full)
    b = "4907182"
    fig, axs = plt.subplots(1, 2, figsize=(11, 5))
    nd = draw_cloud(axs[0], "raw_dense", b, "DIM/MVS points (textureless)")
    na = draw_cloud(axs[1], "raw_lidar", b, "ALS points")
    fig.suptitle(f"(c) TEXTURELESS {b}: DIM/MVS empty vs ALS full — point-cloud intermediate collapses on textureless", fontsize=11)
    fig.tight_layout(rect=[0, 0, 1, 0.94]); fig.savefig(FIG / "c_textureless.png", dpi=110); plt.close(fig)
    print(f"(c) c_textureless.png (DIM {nd} pts vs ALS {na} pts)")
    print(f"[done] figs -> {FIG}/")


if __name__ == "__main__":
    main()
