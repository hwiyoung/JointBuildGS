"""Compute Stage 2 primitive structure metrics on Phase 2 checkpoints.

Metrics:
  - sigma_normal_intra (deg): within-group std of normals, averaged over groups
  - sigma_coplanar (m): within-group RMS of primitive-center to plane distance
  - Wall vertical fraction: fraction of Wall primitives with |n·gravity| < 0.1
  - Roof horizontal fraction: fraction of Roof primitives with |n·gravity| > 0.9
  - Primitive counts by class (BG/Roof/Wall/Terrain)
  - Average # planes per building (after clustering)

Grouping uses cluster_primitives from src/stage3 with default params (same as
Stage 3 pipeline), per building.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from collections import defaultdict

import numpy as np
import torch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from src.stage3.clustering import cluster_primitives  # noqa: E402
from scripts.stage3_readout.obj_gt import parse_scene_obj  # noqa: E402


def _assign_primitives_fast(prims, gt, pad=2.0, opacity_thresh=0.05):
    """Vectorized version: each primitive → nearest building bbox center (with bbox check)."""
    centers = prims["centers"]  # (N, 3)
    opa = prims["opacities"]
    keep_mask = opa >= opacity_thresh
    centers = centers[keep_mask]
    kept_idx = np.where(keep_mask)[0]

    n_b = len(gt["buildings"])
    bmins = np.zeros((n_b, 3), dtype=np.float32)
    bmaxs = np.zeros((n_b, 3), dtype=np.float32)
    bcenters = np.zeros((n_b, 3), dtype=np.float32)
    bids = []
    for bi, b in enumerate(gt["buildings"]):
        vs = np.concatenate([f["vertices"] for f in b["faces"]], axis=0)
        bmins[bi] = vs.min(axis=0) - pad
        bmaxs[bi] = vs.max(axis=0) + pad
        bcenters[bi] = vs.mean(axis=0)
        bids.append(b["building_id"])

    # Batched to control memory: 50k primitives × 131 buildings at a time
    CHUNK = 50000
    best = np.empty(len(centers), dtype=np.int32)
    for s in range(0, len(centers), CHUNK):
        e = min(s + CHUNK, len(centers))
        c = centers[s:e]  # (k, 3)
        inside = ((c[:, None, :] >= bmins[None, :, :]) &
                  (c[:, None, :] <= bmaxs[None, :, :])).all(axis=2)  # (k, B)
        dist = np.linalg.norm(c[:, None, :] - bcenters[None, :, :], axis=2)  # (k, B)
        choose = np.where(inside, dist, np.inf)
        any_in = inside.any(axis=1)
        best[s:e] = np.where(any_in, choose.argmin(axis=1), dist.argmin(axis=1))

    assignment = {bid: [] for bid in bids}
    for i, bi in enumerate(best):
        assignment[bids[int(bi)]].append(int(kept_idx[i]))
    return {bid: np.asarray(v) for bid, v in assignment.items() if len(v) > 0}


def _load_model(ckpt_path):
    ck = torch.load(ckpt_path, map_location="cpu", weights_only=False)
    sd = ck["state_dict"]
    means = sd["means"].numpy()
    # normals from quats (last right column of R = up for 2DGS)
    q = sd["quats"].numpy()
    q = q / np.maximum(np.linalg.norm(q, axis=1, keepdims=True), 1e-8)
    w, x, y, z = q[:, 0], q[:, 1], q[:, 2], q[:, 3]
    normals = np.stack([2*(x*z + w*y), 2*(y*z - w*x), 1 - 2*(x*x + y*y)], axis=1)
    log_scales = sd["log_scales"].numpy()  # (N, 3) log-scales — 2DGS uses first 2
    areas = np.exp(log_scales[:, 0]) * np.exp(log_scales[:, 1])
    sem_logits = sd["sem_logits"].numpy()
    sem = np.exp(sem_logits - sem_logits.max(axis=1, keepdims=True))
    sem = sem / sem.sum(axis=1, keepdims=True)
    opacity_raw = sd["opacities_raw"].numpy()
    opacity = 1 / (1 + np.exp(-opacity_raw))
    return {"means": means, "normals": normals, "areas": areas,
            "semantic_probs": sem, "opacity": opacity, "opacities": opacity,
            "centers": means, "n_prim": len(means)}


def _compute_per_building(prims, assignment, cos_thresh=0.85):
    """For each building, cluster primitives and compute per-building metrics."""
    centers = prims["means"]
    normals = prims["normals"]
    areas = prims["areas"]
    labels = prims["semantic_probs"].argmax(axis=1)

    sigma_normal_intra_list = []  # deg
    sigma_coplanar_list = []  # meters
    n_groups_per_b = []
    wall_vert_fracs = []
    roof_horiz_fracs = []

    # gravity: Y-down convention (scene.obj). gravity vector = (0, 1, 0) points "down"
    gravity = np.array([0.0, 1.0, 0.0])

    for bid, prim_ids in assignment.items():
        if len(prim_ids) < 5:
            continue
        b_centers = centers[prim_ids]
        b_normals = normals[prim_ids]
        b_areas = areas[prim_ids]
        b_labels = labels[prim_ids]

        # Cluster (same method as Stage 3)
        try:
            groups = cluster_primitives(b_centers, b_normals, b_areas, b_labels,
                                        cos_thresh=cos_thresh)
        except Exception:
            continue
        if not groups:
            continue
        n_groups_per_b.append(len(groups))

        # Per-group σ
        for g in groups:
            pids_local = g["prim_ids"]
            if len(pids_local) < 2:
                continue
            n_rep = np.asarray(g["plane_normal"])
            d_rep = float(g["plane_d"])
            n_rep = n_rep / max(np.linalg.norm(n_rep), 1e-8)
            gn = b_normals[pids_local]
            gc = b_centers[pids_local]
            # Flip to representative direction
            dot = gn @ n_rep
            gn = gn * np.sign(dot + 1e-12)[:, None]
            # σ_normal_intra: angle between each primitive normal and representative
            cos_vals = np.clip(gn @ n_rep, -1, 1)
            ang = np.degrees(np.arccos(cos_vals))
            sigma_normal_intra_list.append(float(ang.std()))
            # σ_coplanar: distance from primitive center to rep plane
            offsets = np.abs(gc @ n_rep - d_rep)
            sigma_coplanar_list.append(float(np.sqrt((offsets ** 2).mean())))

        # Wall vertical fraction: wall prims (label==2) with |n·gravity| < 0.1
        wall_mask = b_labels == 2
        if wall_mask.sum() > 0:
            wn = b_normals[wall_mask]
            cos_g = np.abs(wn @ gravity)
            wall_vert_fracs.append(float((cos_g < 0.1).mean()))
        # Roof horizontal fraction: roof prims (label==1) with |n·gravity| > 0.9
        roof_mask = b_labels == 1
        if roof_mask.sum() > 0:
            rn = b_normals[roof_mask]
            cos_g = np.abs(rn @ gravity)
            roof_horiz_fracs.append(float((cos_g > 0.9).mean()))

    return {
        "sigma_normal_intra_deg_mean": float(np.mean(sigma_normal_intra_list))
            if sigma_normal_intra_list else float("nan"),
        "sigma_normal_intra_deg_median": float(np.median(sigma_normal_intra_list))
            if sigma_normal_intra_list else float("nan"),
        "sigma_coplanar_m_mean": float(np.mean(sigma_coplanar_list))
            if sigma_coplanar_list else float("nan"),
        "sigma_coplanar_m_median": float(np.median(sigma_coplanar_list))
            if sigma_coplanar_list else float("nan"),
        "n_groups_per_building_mean": float(np.mean(n_groups_per_b))
            if n_groups_per_b else float("nan"),
        "n_groups_per_building_median": float(np.median(n_groups_per_b))
            if n_groups_per_b else float("nan"),
        "wall_vertical_fraction": float(np.mean(wall_vert_fracs))
            if wall_vert_fracs else float("nan"),
        "roof_horizontal_fraction": float(np.mean(roof_horiz_fracs))
            if roof_horiz_fracs else float("nan"),
        "n_buildings_measured": len(n_groups_per_b),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=str(ROOT / "results/phase2_ablation_citygml"))
    ap.add_argument("--scene", default=str(ROOT / "results/phase2_synthesis/scene.obj"))
    ap.add_argument("--conditions", nargs="+",
                    default=["baseline", "mutual", "structure", "both"])
    ap.add_argument("--opacity-thresh", type=float, default=0.05)
    ap.add_argument("--out", default=None, help="output JSON path")
    args = ap.parse_args()

    root = Path(args.root)
    scene = parse_scene_obj(args.scene)

    # Overall stats
    all_results = {}
    for cond in args.conditions:
        ck_path = root / cond / "ckpt/final.pt"
        if not ck_path.exists():
            print(f"[{cond}] MISSING {ck_path}")
            continue
        print(f"[{cond}] loading {ck_path.name}…")
        prims = _load_model(ck_path)
        # Global class counts (opacity filtered)
        op_mask = prims["opacity"] >= args.opacity_thresh
        sem = prims["semantic_probs"][op_mask].argmax(axis=1)
        class_counts = {k: int((sem == i).sum()) for i, k in
                        enumerate(["BG", "Roof", "Wall", "Terrain"])}
        class_fracs = {k: float(v / max(sem.shape[0], 1))
                       for k, v in class_counts.items()}

        # Building assignment (per-building primitive IDs)
        print(f"[{cond}] assigning primitives to buildings…")
        assignment = _assign_primitives_fast(
            prims, scene, opacity_thresh=args.opacity_thresh)
        # Filter tiny assignments
        assignment = {bid: ids for bid, ids in assignment.items() if len(ids) >= 5}

        print(f"[{cond}] computing per-building metrics for {len(assignment)} bldgs…")
        metrics = _compute_per_building(prims, assignment)
        metrics["n_primitives_total"] = int(prims["n_prim"])
        metrics["n_primitives_active"] = int(op_mask.sum())
        metrics["class_counts"] = class_counts
        metrics["class_fractions"] = class_fracs
        metrics["n_buildings_assigned"] = len(assignment)
        all_results[cond] = metrics
        print(f"[{cond}] summary:")
        for k, v in metrics.items():
            if isinstance(v, (int, float)):
                print(f"   {k}: {v:.4f}" if isinstance(v, float) else f"   {k}: {v}")

    # Print comparison table
    print("\n\n===== Stage 2 primitive structure comparison =====")
    headers = ["Metric"] + args.conditions
    rows = [
        ("σ_normal_intra (deg) mean", "sigma_normal_intra_deg_mean"),
        ("σ_normal_intra (deg) median", "sigma_normal_intra_deg_median"),
        ("σ_coplanar (m) mean", "sigma_coplanar_m_mean"),
        ("σ_coplanar (m) median", "sigma_coplanar_m_median"),
        ("n_groups/building mean", "n_groups_per_building_mean"),
        ("n_groups/building median", "n_groups_per_building_median"),
        ("Wall vertical %", "wall_vertical_fraction"),
        ("Roof horizontal %", "roof_horizontal_fraction"),
        ("N active primitives", "n_primitives_active"),
        ("n_buildings measured", "n_buildings_measured"),
    ]
    w_first = 28
    w_each = 14
    print(f"{headers[0]:<{w_first}}" + "".join(f"{h:>{w_each}}" for h in headers[1:]))
    print("-" * (w_first + w_each * len(args.conditions)))
    for title, key in rows:
        vals = []
        for cond in args.conditions:
            v = all_results.get(cond, {}).get(key, "—")
            if isinstance(v, float):
                if "%" in title:
                    v = f"{v*100:.1f}%"
                elif "N active" in title or "n_buildings" in title:
                    v = f"{int(v)}"
                else:
                    v = f"{v:.3f}"
            vals.append(v)
        print(f"{title:<{w_first}}" + "".join(f"{v:>{w_each}}" for v in vals))

    # Class fractions
    print("\n===== Class fractions (of active primitives) =====")
    print(f"{'Class':<{w_first}}" + "".join(f"{h:>{w_each}}" for h in args.conditions))
    print("-" * (w_first + w_each * len(args.conditions)))
    for k in ["BG", "Roof", "Wall", "Terrain"]:
        vals = [f"{all_results[c]['class_fractions'][k]*100:.1f}%"
                if c in all_results else "—"
                for c in args.conditions]
        print(f"{k:<{w_first}}" + "".join(f"{v:>{w_each}}" for v in vals))

    out = args.out or str(Path(args.root) / "stage2_primitive_metrics.json")
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    Path(out).write_text(json.dumps(all_results, indent=2, default=str))
    print(f"\n[saved] {out}")


if __name__ == "__main__":
    main()
