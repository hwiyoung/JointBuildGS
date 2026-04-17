"""Geometric evaluation: F1 score (0.5m, 1.0m thresholds), Chamfer Distance.

Compares primitives (Gaussian centers) against GT point cloud.

Usage:
    python scripts/stage2/eval_geometry.py \
        --ckpt results/phase1_vanilla/run/ckpt/final.pt \
        --gt data/matrixcity/small_city_pointcloud/point_cloud_ds20/aerial/Block_all.ply \
        --out results/phase1_vanilla/run/eval_geometry
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import torch
from plyfile import PlyData
from scipy.spatial import cKDTree


def read_ply_xyz(path: str) -> np.ndarray:
    ply = PlyData.read(path)
    v = ply["vertex"]
    xyz = np.stack([np.asarray(v["x"]), np.asarray(v["y"]), np.asarray(v["z"])], axis=1)
    return xyz.astype(np.float64)


def chamfer_and_f1(pred: np.ndarray, gt: np.ndarray, thresholds=(0.5, 1.0)):
    """Compute symmetric Chamfer distance and F1 at given thresholds."""
    t_pred = cKDTree(pred)
    t_gt = cKDTree(gt)

    d_pred_to_gt, _ = t_gt.query(pred, k=1)   # for each pred, nearest GT
    d_gt_to_pred, _ = t_pred.query(gt, k=1)   # for each GT, nearest pred

    # Chamfer Distance (mean)
    chamfer = float(d_pred_to_gt.mean() + d_gt_to_pred.mean())
    chamfer_sym = float(0.5 * (d_pred_to_gt.mean() + d_gt_to_pred.mean()))

    results = {
        "n_pred": int(len(pred)),
        "n_gt": int(len(gt)),
        "chamfer_sum": chamfer,
        "chamfer_sym_mean": chamfer_sym,
        "pred_to_gt_mean": float(d_pred_to_gt.mean()),
        "pred_to_gt_median": float(np.median(d_pred_to_gt)),
        "gt_to_pred_mean": float(d_gt_to_pred.mean()),
        "gt_to_pred_median": float(np.median(d_gt_to_pred)),
    }

    for tau in thresholds:
        # Precision: fraction of pred points within tau of some GT point
        precision = float((d_pred_to_gt < tau).mean())
        # Recall: fraction of GT points within tau of some pred point
        recall = float((d_gt_to_pred < tau).mean())
        f1 = 2 * precision * recall / max(precision + recall, 1e-10)
        results[f"precision_{tau}"] = precision
        results[f"recall_{tau}"] = recall
        results[f"f1_{tau}"] = f1

    return results


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ckpt", required=True)
    ap.add_argument("--gt", required=True, help="GT point cloud PLY path")
    ap.add_argument("--out", required=True)
    ap.add_argument("--thresholds", nargs="+", type=float, default=[0.5, 1.0])
    args = ap.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    # Load predicted centers
    sd = torch.load(args.ckpt, map_location="cpu", weights_only=False)["state_dict"]
    pred = sd["means"].cpu().numpy().astype(np.float64)
    print(f"pred centers: {pred.shape}")

    # Load GT
    gt = read_ply_xyz(args.gt)
    print(f"gt points: {gt.shape}")

    # Optional: subsample GT if very large (for speed)
    MAX_GT = 5_000_000
    if len(gt) > MAX_GT:
        idx = np.random.choice(len(gt), MAX_GT, replace=False)
        gt = gt[idx]
        print(f"gt subsampled to {len(gt)}")

    # Compute
    results = chamfer_and_f1(pred, gt, thresholds=args.thresholds)
    print(json.dumps(results, indent=2))

    (out_dir / "geometry_metrics.json").write_text(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
