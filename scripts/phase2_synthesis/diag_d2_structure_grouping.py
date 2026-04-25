"""D2: L_structure grouping output diagnosis.

Question: L_structure shows nearly zero effect on σ_normal_intra (Phase 1: −45%,
Phase 2: +1%). Why? This experiment compares actual grouping outputs.

For several buildings × {baseline, structure}:
  1. Cluster primitives identically (same algorithm/params).
  2. Compare group count, per-group size, per-group σ_normal_intra, σ_coplanar.
  3. Identify whether L_structure produces:
     (a) similar groups but tighter (σ ↓ within same groups) — expected
     (b) different groups (split/merge) — could explain null effect
     (c) similar groups and similar σ — no-op effect

Buildings: 3 representative (flat, gable, complex).
Output: per-building JSON + one aggregate figure.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from collections import defaultdict

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.phase2_synthesis.obj_gt import parse_scene_obj  # noqa
from scripts.phase2_synthesis.run_stage3 import _load_model, _build_primitives_dict  # noqa
from src.stage3.clustering import cluster_primitives  # noqa


CONDS = ["baseline", "structure"]
COND_COLORS = {"baseline": "#888888", "structure": "#FFB040"}
SAMPLE_BIDS = [2, 6, 21]  # flat, hip, complex — representative


def cluster_and_measure(prims: dict, bid: int, gt: dict, cos_thresh=0.85):
    """Same clustering code path as Stage 3, per building."""
    b_gt = next(b for b in gt["buildings"] if b["building_id"] == bid)
    all_v = np.concatenate([f["vertices"] for f in b_gt["faces"]], axis=0)
    mn, mx = all_v.min(0) - 2, all_v.max(0) + 2
    mask_bbox = ((prims["centers"] >= mn) & (prims["centers"] <= mx)).all(axis=1)
    mask_opa = prims["opacities"] >= 0.05
    sel = np.where(mask_bbox & mask_opa)[0]
    if len(sel) < 10:
        return None

    centers = prims["centers"][sel]
    normals = prims["normals"][sel]
    areas = prims["areas"][sel]
    sem = prims["semantic_probs"][sel]
    labels = sem.argmax(axis=1)

    groups = cluster_primitives(centers, normals, areas, labels, cos_thresh=cos_thresh)
    # Per-group metrics
    group_stats = []
    for gi, g in enumerate(groups):
        pids = g["prim_ids"]
        if len(pids) < 2:
            continue
        gn = normals[pids]
        gc = centers[pids]
        rep_n = np.asarray(g["plane_normal"])
        rep_d = float(g["plane_d"])
        dot = gn @ rep_n
        gn_flip = gn * np.sign(dot + 1e-12)[:, None]
        ang = np.degrees(np.arccos(np.clip(gn_flip @ rep_n, -1, 1)))
        offs = np.abs(gc @ rep_n - rep_d)
        group_stats.append({
            "idx": gi,
            "size": len(pids),
            "class": int(g["class"]),
            "sigma_normal_deg": float(ang.std()),
            "sigma_coplanar_m": float(np.sqrt((offs ** 2).mean())),
            "rep_normal": [float(x) for x in rep_n],
            "rep_d": rep_d,
        })
    return {
        "n_primitives_total": int(len(sel)),
        "n_groups": len(group_stats),
        "groups": group_stats,
        "all_sigma_normal_mean": float(np.mean([g["sigma_normal_deg"] for g in group_stats]))
            if group_stats else None,
        "all_sigma_coplanar_mean": float(np.mean([g["sigma_coplanar_m"] for g in group_stats]))
            if group_stats else None,
    }


def match_groups_by_normal(groups_a, groups_b, tol_cos=0.85):
    """Heuristic matching: for each group in A, find best match in B by
    representative normal direction + center proximity."""
    pairs = []
    used_b = set()
    for ga in groups_a:
        best_j = -1
        best_score = -np.inf
        na = np.asarray(ga["rep_normal"])
        for j, gb in enumerate(groups_b):
            if j in used_b: continue
            if gb["class"] != ga["class"]: continue
            nb = np.asarray(gb["rep_normal"])
            cos = abs(na @ nb)
            if cos < tol_cos: continue
            # secondary: similar size
            size_ratio = min(ga["size"], gb["size"]) / max(ga["size"], gb["size"])
            score = cos + 0.5 * size_ratio
            if score > best_score:
                best_score = score; best_j = j
        if best_j >= 0:
            used_b.add(best_j)
            pairs.append((ga["idx"], groups_b[best_j]["idx"], float(best_score)))
    return pairs


def main():
    out_dir = ROOT / "results/phase2_ablation_citygml/_diag/d2"
    out_dir.mkdir(parents=True, exist_ok=True)
    scene = parse_scene_obj(str(ROOT / "results/phase2_synthesis/scene.obj"))

    import torch  # noqa
    prims_cache = {}

    all_results = {}
    for bid in SAMPLE_BIDS:
        b_gt = next((b for b in scene["buildings"] if b["building_id"] == bid), None)
        if b_gt is None: continue
        btype = b_gt.get("type", "?")
        print(f"\n=== bid={bid} ({btype}) ===")
        per_cond = {}
        for cond in CONDS:
            if cond not in prims_cache:
                ck = ROOT / "results/phase2_ablation_citygml" / cond / "ckpt/final.pt"
                m = _load_model(ck)
                prims_cache[cond] = _build_primitives_dict(m) | {
                    "opacities": m["opacities"]}
            prims = prims_cache[cond]
            r = cluster_and_measure(prims, bid, scene)
            per_cond[cond] = r
            if r is None:
                print(f"  {cond}: skip")
                continue
            print(f"  {cond}: {r['n_groups']} groups, "
                  f"σn mean={r['all_sigma_normal_mean']:.2f}°, "
                  f"σcp mean={r['all_sigma_coplanar_mean']:.3f}m")
            # Class breakdown
            by_class = defaultdict(list)
            for g in r["groups"]: by_class[g["class"]].append(g)
            for cls, gs in sorted(by_class.items()):
                cname = {1:"Roof",2:"Wall",3:"Terrain"}.get(cls,"?")
                sizes = [g["size"] for g in gs]
                sns = [g["sigma_normal_deg"] for g in gs]
                print(f"    {cname}: {len(gs)} groups, sizes {sizes}, "
                      f"σn {[f'{s:.1f}' for s in sns]}")

        # Match groups between conditions
        if per_cond.get("baseline") and per_cond.get("structure"):
            pairs = match_groups_by_normal(
                per_cond["baseline"]["groups"], per_cond["structure"]["groups"])
            print(f"  matched {len(pairs)} groups between baseline & structure")
            # For matched pairs, compare σ_normal
            match_compare = []
            for bi, si, score in pairs:
                g_b = next(g for g in per_cond["baseline"]["groups"] if g["idx"] == bi)
                g_s = next(g for g in per_cond["structure"]["groups"] if g["idx"] == si)
                match_compare.append({
                    "class": g_b["class"],
                    "baseline_size": g_b["size"],
                    "structure_size": g_s["size"],
                    "baseline_sn": g_b["sigma_normal_deg"],
                    "structure_sn": g_s["sigma_normal_deg"],
                    "baseline_cp": g_b["sigma_coplanar_m"],
                    "structure_cp": g_s["sigma_coplanar_m"],
                    "match_score": score,
                })
            per_cond["matched_pairs"] = match_compare
            # Aggregate
            if match_compare:
                delta_sn = [(m["structure_sn"] - m["baseline_sn"]) for m in match_compare]
                delta_cp = [(m["structure_cp"] - m["baseline_cp"]) for m in match_compare]
                print(f"  matched σn change: mean={np.mean(delta_sn):.3f}° (negative=improvement)")
                print(f"  matched σcp change: mean={np.mean(delta_cp):.3f}m")
        all_results[f"bid_{bid}"] = per_cond

    (out_dir / "d2_results.json").write_text(json.dumps(all_results, indent=2, default=str))

    # Aggregate figure
    fig, axes = plt.subplots(1, 3, figsize=(16, 5))
    for ax_i, (bid, r) in enumerate(all_results.items()):
        ax = axes[ax_i]
        if not r.get("baseline") or not r.get("structure"):
            continue
        sn_b = [g["sigma_normal_deg"] for g in r["baseline"]["groups"]]
        sn_s = [g["sigma_normal_deg"] for g in r["structure"]["groups"]]
        # side-by-side boxplot
        ax.boxplot([sn_b, sn_s], labels=["Baseline", "Structure"],
                    patch_artist=True,
                    boxprops=dict(facecolor="#ccc"))
        ax.scatter([1] * len(sn_b), sn_b, color=COND_COLORS["baseline"],
                    s=30, alpha=0.7, edgecolor="k", zorder=3)
        ax.scatter([2] * len(sn_s), sn_s, color=COND_COLORS["structure"],
                    s=30, alpha=0.7, edgecolor="k", zorder=3)
        ax.set_ylabel("σ_normal_intra (deg)")
        ax.set_title(f"{bid} ({next(b['type'] for b in scene['buildings'] if b['building_id']==int(bid.split('_')[1]))})\n"
                     f"Baseline: {r['baseline']['n_groups']}g σn_mean={r['baseline']['all_sigma_normal_mean']:.1f}°\n"
                     f"Structure: {r['structure']['n_groups']}g σn_mean={r['structure']['all_sigma_normal_mean']:.1f}°",
                     fontsize=10)
        ax.grid(axis="y", alpha=0.3)
    plt.suptitle("D2: L_structure grouping output — per-group σ_normal_intra\n"
                 "Each point = one group's within-cluster normal std. Baseline vs Structure side-by-side.",
                 fontsize=12, weight="bold", y=1.02)
    plt.tight_layout()
    out_png = ROOT / "results/phase2_ablation_citygml/figures/fig_d2_structure_grouping.png"
    plt.savefig(out_png, dpi=110, bbox_inches="tight")
    plt.close()
    print(f"  -> {out_png}")


if __name__ == "__main__":
    main()
