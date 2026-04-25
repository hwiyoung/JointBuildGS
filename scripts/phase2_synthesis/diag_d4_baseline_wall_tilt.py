"""D4: Why does Baseline Stage 2 produce only 28% perfectly-vertical walls
when GT has 100%?

For bid=2 (flat, simple box) Baseline wall primitives:
  1. Compute tilt = angle between normal and perpendicular-to-gravity plane
  2. Plot tilt distribution (histogram + spatial map)
  3. Overlay tilt on 3D wall position — is tilt concentrated at edges/corners?

Output:
  results/phase2_ablation_citygml/figures/fig_d4_baseline_wall_tilt.png
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.phase2_synthesis.obj_gt import parse_scene_obj  # noqa
from scripts.phase2_synthesis.run_stage3 import _load_model, _build_primitives_dict  # noqa


BIDS = [2, 22, 21]  # flat, gable, complex


def tilt_deg_from_gravity(n, gravity=np.array([0., 1., 0.])):
    """Wall is perfectly vertical iff n·gravity ≈ 0. Tilt = angle from horizontal."""
    n = n / np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-8)
    cos_g = np.abs(n @ gravity)
    cos_g = np.clip(cos_g, 0, 1)
    return np.degrees(np.arcsin(cos_g))


def analyze_bid(prims, bid, gt):
    b_gt = next(b for b in gt["buildings"] if b["building_id"] == bid)
    all_v = np.concatenate([f["vertices"] for f in b_gt["faces"]], axis=0)
    mn, mx = all_v.min(0) - 2, all_v.max(0) + 2
    mask_bbox = ((prims["centers"] >= mn) & (prims["centers"] <= mx)).all(axis=1)
    mask_opa = prims["opacities"] >= 0.05
    sel = np.where(mask_bbox & mask_opa)[0]
    centers = prims["centers"][sel]
    normals = prims["normals"][sel]
    sem = prims["semantic_probs"][sel]
    labels = sem.argmax(axis=1)
    wall_mask = labels == 2
    w_centers = centers[wall_mask]
    w_normals = normals[wall_mask]
    tilts = tilt_deg_from_gravity(w_normals)
    return {
        "n_wall": int(wall_mask.sum()),
        "centers": w_centers,
        "normals": w_normals,
        "tilts": tilts,
        "building_gt": b_gt,
        "all_vertices": all_v,
    }


def main():
    scene = parse_scene_obj(str(ROOT / "results/phase2_synthesis/scene.obj"))
    ck = ROOT / "results/phase2_ablation_citygml/baseline/ckpt/final.pt"
    m = _load_model(ck)
    prims = _build_primitives_dict(m) | {"opacities": m["opacities"]}

    fig = plt.figure(figsize=(16, 4 * len(BIDS)))
    for row_i, bid in enumerate(BIDS):
        r = analyze_bid(prims, bid, scene)
        btype = r["building_gt"]["type"]
        tilts = r["tilts"]
        centers = r["centers"]

        # histogram
        ax = fig.add_subplot(len(BIDS), 3, row_i * 3 + 1)
        ax.hist(tilts, bins=50, range=(0, 45), color="#4C9AFF", edgecolor="k")
        ax.axvline(5, color="r", ls="--", label="5° threshold")
        pct_5 = (tilts < 5).mean() * 100
        pct_1 = (tilts < 1).mean() * 100
        ax.set_xlabel("Tilt from vertical (deg)")
        ax.set_ylabel("# wall primitives")
        ax.set_title(f"bid={bid} ({btype})\n"
                     f"{r['n_wall']} wall prims\n"
                     f"{pct_5:.1f}% < 5°,  {pct_1:.1f}% < 1° (GT = 100%)",
                     fontsize=10)
        ax.legend(fontsize=8)

        # 3D colored by tilt — side view
        ax = fig.add_subplot(len(BIDS), 3, row_i * 3 + 2, projection="3d")
        sc = ax.scatter(centers[:, 0], centers[:, 1], centers[:, 2],
                         c=tilts, cmap="Reds", vmin=0, vmax=30,
                         s=5, alpha=0.6, edgecolors="none")
        # GT walls as wireframe
        for f in r["building_gt"]["faces"]:
            if f["semantic_class"] == 2:
                v = np.array(f["vertices"])
                v = np.vstack([v, v[0]])
                ax.plot(v[:, 0], v[:, 1], v[:, 2], "k-", lw=0.3, alpha=0.5)
        ax.set_xlabel("X"); ax.set_ylabel("Y (down)"); ax.set_zlabel("Z")
        ax.invert_yaxis()
        ax.set_title(f"Wall primitive tilt — 3D view\n(color = degrees from vertical)", fontsize=9)
        plt.colorbar(sc, ax=ax, fraction=0.04, label="tilt (°)")

        # Spatial edge analysis: compute distance from wall primitives to GT wall edges
        # (i.e., corner proximity) — is tilt concentrated at edges?
        ax = fig.add_subplot(len(BIDS), 3, row_i * 3 + 3)
        # Get GT wall edges (line segments)
        gt_edges = []
        for f in r["building_gt"]["faces"]:
            if f["semantic_class"] == 2:
                v = np.array(f["vertices"])
                for i in range(len(v)):
                    gt_edges.append((v[i], v[(i + 1) % len(v)]))
        # Distance from each wall prim to nearest edge endpoint (corner proxy)
        corners = np.array([e[0] for e in gt_edges])  # many endpoints
        if len(corners) > 0:
            d_corners = np.linalg.norm(
                centers[:, None, :] - corners[None, :, :], axis=2).min(axis=1)
            ax.scatter(d_corners, tilts, s=4, alpha=0.4)
            # Binned mean
            bins = np.linspace(0, d_corners.max() + 0.5, 15)
            bin_idx = np.digitize(d_corners, bins) - 1
            bin_mean = [tilts[bin_idx == i].mean() if (bin_idx == i).sum() > 0 else np.nan
                         for i in range(len(bins) - 1)]
            ax.plot(bins[:-1] + (bins[1] - bins[0]) / 2, bin_mean, "r-o",
                    label="bin mean", linewidth=1.5, markersize=4)
            ax.set_xlabel("Distance to nearest GT wall corner (m)")
            ax.set_ylabel("Tilt from vertical (°)")
            ax.set_title("Tilt vs corner proximity\n(high tilt at corners = edge effect)",
                         fontsize=9)
            ax.legend(fontsize=8)
            ax.grid(alpha=0.3)

    plt.suptitle("D4: Baseline Wall primitive verticality — why is GT (100%) not matched?",
                 fontsize=12, weight="bold", y=1.005)
    plt.tight_layout()
    out = ROOT / "results/phase2_ablation_citygml/figures/fig_d4_baseline_wall_tilt.png"
    plt.savefig(out, dpi=110, bbox_inches="tight")
    print(f"  -> {out}")

    # Save stats
    stats = {}
    for bid in BIDS:
        r = analyze_bid(prims, bid, scene)
        tilts = r["tilts"]
        stats[f"bid_{bid}"] = {
            "type": r["building_gt"]["type"],
            "n_wall": int(r["n_wall"]),
            "tilt_lt_1_deg_pct": float((tilts < 1).mean() * 100),
            "tilt_lt_5_deg_pct": float((tilts < 5).mean() * 100),
            "tilt_lt_10_deg_pct": float((tilts < 10).mean() * 100),
            "tilt_mean": float(tilts.mean()),
            "tilt_median": float(np.median(tilts)),
        }
    (ROOT / "results/phase2_ablation_citygml/_diag/d4_stats.json").parent.mkdir(parents=True, exist_ok=True)
    (ROOT / "results/phase2_ablation_citygml/_diag/d4_stats.json").write_text(json.dumps(stats, indent=2))
    for k, v in stats.items():
        print(f"{k}: {v}")


if __name__ == "__main__":
    main()
