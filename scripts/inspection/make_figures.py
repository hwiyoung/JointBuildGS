"""Phase 2 Step 2-2 — make 5 figures.

Inputs:
    results/phase2_ablation_citygml/<cond>/eval/eval_summary.json   (per condition)
    results/phase2_ablation_citygml/<cond>/stage3/                   (CityJSON per building)
    results/phase2_ablation_citygml/<cond>/renders/                  (trained 2DGS renders)
    results/synthetic_a/3dbag_results.json                           (normal-noise baseline)

Outputs (results/phase2_ablation_citygml/figures/):
    fig1_citygml_4cond.png          per-condition 3D CityGML comparison (scene view)
    fig2_val3dity_bars.png          4-condition val3dity pass rate bar chart
    fig3_error_heatmap.png          error code distribution heatmap
    fig4_syntheticA_mapping.png     Synthetic A normal-noise curve w/ 4 conditions overlaid
    fig5_representative_building.png one building across 4 conditions + GT
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, List

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from scripts.stage3_readout.obj_gt import parse_scene_obj  # noqa: E402
from scripts.stage3_readout.eval_citygml import load_cityjson_building, faces_to_mesh  # noqa: E402


CONDS = ["baseline", "mutual", "structure", "both"]
COND_COLORS = {
    "baseline": "#888888",
    "mutual": "#4C9AFF",
    "structure": "#FFB040",
    "both": "#20A050",
}
CLS_COLORS = {
    "RoofSurface": "#C53030",
    "WallSurface": "#2C5282",
    "GroundSurface": "#718096",
    "Roof": "#C53030",
    "Wall": "#2C5282",
    "Ground": "#718096",
    "Terrain": "#718096",
}


def _load_eval(root: Path, cond: str) -> Dict:
    p = root / cond / "eval" / "eval_summary.json"
    if not p.exists():
        return {}
    return json.loads(p.read_text())


def _load_stage3_summary(root: Path, cond: str) -> Dict:
    p = root / cond / "stage3" / "stage3_summary.json"
    if not p.exists():
        return {}
    return json.loads(p.read_text())


# ---------- fig 1: 4-condition 3D CityGML comparison ----------

def fig1_citygml_scene(root: Path, gt: Dict, out_path: Path):
    """Render scene polygons (all 20 buildings) for each condition and GT."""
    fig = plt.figure(figsize=(20, 5))
    views = [("GT", None)] + [(c, c) for c in CONDS]
    for col, (title, cond) in enumerate(views):
        ax = fig.add_subplot(1, 5, col + 1, projection="3d")
        if cond is None:
            # GT: draw each GT face
            for b in gt["buildings"]:
                for f in b["faces"]:
                    _poly3d(ax, f["vertices"], CLS_COLORS.get(f["material"], "#aaa"))
        else:
            sdir = root / cond / "stage3"
            if not sdir.exists():
                ax.text(0.5, 0.5, 0.5, "no stage3 output",
                        ha="center", transform=ax.transAxes)
                ax.set_title(title)
                continue
            for bd in sorted(sdir.glob("building_*")):
                cj = bd / "building.city.json"
                if not cj.exists():
                    continue
                try:
                    bldg = load_cityjson_building(cj)
                except Exception:
                    continue
                for f in bldg["faces"]:
                    _poly3d(ax, f["vertices"],
                            CLS_COLORS.get(f["type"], "#aaa"))
        ax.set_title(title)
        ax.set_box_aspect((1, 1, 0.3))
        ax.view_init(elev=35, azim=-50)
        ax.set_xticks([]); ax.set_yticks([]); ax.set_zticks([])
    plt.suptitle("Phase 2 Step 2-2 — 4-condition CityGML comparison (GT | baseline | mutual | structure | both)",
                 fontsize=12)
    plt.tight_layout()
    plt.savefig(out_path, dpi=140, bbox_inches="tight")
    plt.close()
    print(f"  -> {out_path}")


def _poly3d(ax, poly: np.ndarray, color: str, edge: str = "#000"):
    from mpl_toolkits.mplot3d.art3d import Poly3DCollection
    # matplotlib 3D convention: X right, Y up, Z out of screen
    # our scene: X right, Y down (COLMAP -Y up), Z toward camera → flip Y
    p = poly.copy()
    p[:, 1] = -p[:, 1]
    poly3d = [p.tolist()]
    pc = Poly3DCollection(poly3d, facecolor=color, edgecolor=edge,
                          linewidth=0.15, alpha=0.85)
    ax.add_collection3d(pc)
    # Expand limits
    _expand_lim(ax, p)


def _expand_lim(ax, p):
    x0, y0, z0 = p.min(axis=0); x1, y1, z1 = p.max(axis=0)
    cur_x = ax.get_xlim(); cur_y = ax.get_ylim(); cur_z = ax.get_zlim()
    ax.set_xlim(min(cur_x[0], x0), max(cur_x[1], x1))
    ax.set_ylim(min(cur_y[0], y0), max(cur_y[1], y1))
    ax.set_zlim(min(cur_z[0], z0), max(cur_z[1], z1))


# ---------- fig 2: val3dity bars ----------

def fig2_val3dity_bars(root: Path, out_path: Path):
    fig, ax = plt.subplots(figsize=(8, 5))
    rates = []
    labels = []
    for c in CONDS:
        ev = _load_eval(root, c)
        rate = (ev.get("aggregate", {}) or {}).get("val3dity_pass_rate", 0.0) * 100
        rates.append(rate)
        labels.append(c)
    bars = ax.bar(labels, rates,
                  color=[COND_COLORS[c] for c in labels],
                  edgecolor="#000", linewidth=0.5)
    for b, r in zip(bars, rates):
        ax.text(b.get_x() + b.get_width()/2, r + 1, f"{r:.1f}%",
                ha="center", fontsize=11)
    ax.set_ylabel("val3dity pass rate (%)")
    ax.set_ylim(0, 105)
    ax.set_title("Phase 2 Step 2-2 — val3dity pass rate per condition")
    ax.grid(axis="y", alpha=0.3)
    plt.tight_layout()
    plt.savefig(out_path, dpi=140, bbox_inches="tight")
    plt.close()
    print(f"  -> {out_path}")


# ---------- fig 3: error type heatmap ----------

def fig3_error_heatmap(root: Path, out_path: Path):
    all_codes: List[str] = []
    matrix = {}
    for c in CONDS:
        ev = _load_eval(root, c)
        codes = (ev.get("aggregate", {}) or {}).get("val3dity_error_codes", {}) or {}
        matrix[c] = codes
        for k in codes:
            if k not in all_codes:
                all_codes.append(k)
    if not all_codes:
        all_codes = ["(no errors recorded)"]
    all_codes.sort()
    data = np.zeros((len(CONDS), len(all_codes)), dtype=np.int64)
    for ci, c in enumerate(CONDS):
        for ki, k in enumerate(all_codes):
            data[ci, ki] = matrix[c].get(k, 0)

    fig, ax = plt.subplots(figsize=(max(8, len(all_codes) * 0.8 + 4), 3.5))
    im = ax.imshow(data, aspect="auto", cmap="OrRd")
    ax.set_yticks(range(len(CONDS))); ax.set_yticklabels(CONDS)
    ax.set_xticks(range(len(all_codes))); ax.set_xticklabels(all_codes, rotation=45, ha="right")
    for i in range(data.shape[0]):
        for j in range(data.shape[1]):
            ax.text(j, i, f"{data[i,j]}", ha="center", va="center",
                    color="white" if data[i, j] > data.max() * 0.5 else "black",
                    fontsize=10)
    ax.set_title("Phase 2 Step 2-2 — val3dity error code distribution (buildings × error code)")
    plt.colorbar(im, ax=ax, label="count")
    plt.tight_layout()
    plt.savefig(out_path, dpi=140, bbox_inches="tight")
    plt.close()
    print(f"  -> {out_path}")


# ---------- fig 4: Synthetic A mapping ----------

def fig4_synthetic_a_mapping(root: Path, synth_a_json: Path, out_path: Path):
    """Plot Synthetic A normal-noise curve; overlay 4 conditions at their (sigma_normal, val3dity) coords."""
    if not synth_a_json.exists():
        print(f"  [warn] {synth_a_json} not found; skipping fig 4")
        return
    data = json.loads(synth_a_json.read_text())
    # Synthetic A normal-noise series: clean (0°), 2°, 10°, 20°
    series = [("clean", 0.0), ("normal_2deg", 2.0), ("normal_10deg", 10.0),
              ("normal_20deg", 20.0)]
    xs, ys = [], []
    for tag, deg in series:
        items = [e for e in data if e["noise"] == tag]
        if not items:
            continue
        pass_rate = np.mean([1.0 if e.get("val3dity_valid") else 0.0 for e in items])
        xs.append(deg); ys.append(pass_rate * 100)

    fig, ax = plt.subplots(figsize=(9, 5.5))
    ax.plot(xs, ys, "ko-", linewidth=2, markersize=8,
            label="Synthetic A (normal noise curve)")
    for i, (x, y) in enumerate(zip(xs, ys)):
        ax.annotate(f"{series[i][0]}: {y:.0f}%", (x, y),
                    textcoords="offset points", xytext=(8, 8), fontsize=9)
    # overlay 4 conditions
    for c in CONDS:
        ev = _load_eval(root, c)
        agg = ev.get("aggregate", {}) or {}
        sx = agg.get("mean_sigma_normal_deg", float("nan"))
        sy = agg.get("val3dity_pass_rate", 0.0) * 100
        if np.isnan(sx):
            continue
        ax.scatter([sx], [sy], s=180, c=COND_COLORS[c], marker="*",
                   edgecolor="k", linewidth=1.2, label=f"Phase 2 / {c}",
                   zorder=5)
    ax.set_xlabel("σ_normal (deg)  — higher = noisier normals")
    ax.set_ylabel("val3dity pass rate (%)")
    ax.set_xlim(-1, 25); ax.set_ylim(0, 105)
    ax.grid(True, alpha=0.3)
    ax.legend(loc="lower left", fontsize=9)
    ax.set_title("Phase 2 Step 2-2 — 4 conditions mapped onto Synthetic A normal-noise curve")
    plt.tight_layout()
    plt.savefig(out_path, dpi=140, bbox_inches="tight")
    plt.close()
    print(f"  -> {out_path}")


# ---------- fig 5: representative building comparison ----------

def fig5_representative_building(root: Path, gt: Dict, out_path: Path,
                                 building_id: int = 9):
    """Draw one building (chosen by default as a hip roof, bid=9 = hip) from each condition + GT."""
    fig = plt.figure(figsize=(20, 4))
    # GT first
    gt_b = next((b for b in gt["buildings"] if b["building_id"] == building_id), None)
    if gt_b is None:
        print(f"  [warn] building_{building_id} not found in GT")
        return
    ax = fig.add_subplot(1, 5, 1, projection="3d")
    for f in gt_b["faces"]:
        _poly3d(ax, f["vertices"], CLS_COLORS.get(f["material"], "#aaa"))
    ax.set_title(f"GT  (building_{building_id:02d} {gt_b['type']})")
    ax.set_box_aspect((1, 1, 0.7))
    ax.view_init(elev=25, azim=-40)
    ax.set_xticks([]); ax.set_yticks([]); ax.set_zticks([])

    for col, cond in enumerate(CONDS):
        ax = fig.add_subplot(1, 5, col + 2, projection="3d")
        cj = root / cond / "stage3" / f"building_{building_id:02d}" / "building.city.json"
        if cj.exists():
            try:
                bldg = load_cityjson_building(cj)
                for f in bldg["faces"]:
                    _poly3d(ax, f["vertices"], CLS_COLORS.get(f["type"], "#aaa"))
            except Exception as e:
                ax.text(0.5, 0.5, 0.5, f"load error: {e}", transform=ax.transAxes)
        else:
            ax.text(0.5, 0.5, 0.5, "no CityJSON", ha="center", transform=ax.transAxes)
        ax.set_title(cond)
        ax.set_box_aspect((1, 1, 0.7))
        ax.view_init(elev=25, azim=-40)
        ax.set_xticks([]); ax.set_yticks([]); ax.set_zticks([])

    plt.suptitle(f"Phase 2 Step 2-2 — representative building_{building_id:02d} "
                 f"({gt_b['type']}): GT vs 4 conditions")
    plt.tight_layout()
    plt.savefig(out_path, dpi=140, bbox_inches="tight")
    plt.close()
    print(f"  -> {out_path}")


# ---------- main ----------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default="results/phase2_ablation_citygml")
    ap.add_argument("--scene", default="results/phase2_synthesis/scene.obj")
    ap.add_argument("--synth-a", default="results/synthetic_a/3dbag_results.json")
    ap.add_argument("--rep-building", type=int, default=9)
    args = ap.parse_args()

    root = Path(args.root)
    figs = root / "figures"
    figs.mkdir(parents=True, exist_ok=True)

    gt = parse_scene_obj(args.scene)

    print("fig 1: scene-level 4-condition CityGML")
    fig1_citygml_scene(root, gt, figs / "fig1_citygml_4cond.png")
    print("fig 2: val3dity bars")
    fig2_val3dity_bars(root, figs / "fig2_val3dity_bars.png")
    print("fig 3: error heatmap")
    fig3_error_heatmap(root, figs / "fig3_error_heatmap.png")
    print("fig 4: Synthetic A mapping")
    fig4_synthetic_a_mapping(root, Path(args.synth_a), figs / "fig4_syntheticA_mapping.png")
    print(f"fig 5: representative building (bid={args.rep_building})")
    fig5_representative_building(root, gt, figs / "fig5_representative_building.png",
                                  building_id=args.rep_building)
    print("[done]")


if __name__ == "__main__":
    main()
