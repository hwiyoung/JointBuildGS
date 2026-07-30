"""Geometric evaluation: F1 score (0.5m, 1.0m thresholds), Chamfer Distance.

Compares primitives (Gaussian centers) against GT point cloud.
Optionally runs ICP alignment before metrics.

Usage:
    python scripts/input_and_alignment/diagnostics/eval_geometry.py \
        --ckpt results/phase1_vanilla/run/ckpt/final.pt \
        --gt data/matrixcity/small_city_pointcloud/point_cloud_ds20/aerial/Block_all.ply \
        --out results/phase1_vanilla/run/eval_geometry \
        --align icp
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

    d_pred_to_gt, _ = t_gt.query(pred, k=1)
    d_gt_to_pred, _ = t_pred.query(gt, k=1)

    results = {
        "n_pred": int(len(pred)),
        "n_gt": int(len(gt)),
        "chamfer_sum": float(d_pred_to_gt.mean() + d_gt_to_pred.mean()),
        "chamfer_sym_mean": float(0.5 * (d_pred_to_gt.mean() + d_gt_to_pred.mean())),
        "pred_to_gt_mean": float(d_pred_to_gt.mean()),
        "pred_to_gt_median": float(np.median(d_pred_to_gt)),
        "gt_to_pred_mean": float(d_gt_to_pred.mean()),
        "gt_to_pred_median": float(np.median(d_gt_to_pred)),
    }
    for tau in thresholds:
        precision = float((d_pred_to_gt < tau).mean())
        recall = float((d_gt_to_pred < tau).mean())
        f1 = 2 * precision * recall / max(precision + recall, 1e-10)
        results[f"precision_{tau}"] = precision
        results[f"recall_{tau}"] = recall
        results[f"f1_{tau}"] = f1
    return results


def icp_align(src: np.ndarray, tgt: np.ndarray, max_iter: int = 30, sample: int = 200_000):
    """Point-to-point ICP. Returns aligned src and 4x4 transform.

    Uses random subsample for speed. src will be moved to align with tgt.
    """
    # Subsample both for speed
    if len(src) > sample:
        src_s = src[np.random.choice(len(src), sample, replace=False)]
    else:
        src_s = src
    if len(tgt) > sample:
        tgt_s = tgt[np.random.choice(len(tgt), sample, replace=False)]
    else:
        tgt_s = tgt

    T = np.eye(4)
    prev_err = np.inf
    for i in range(max_iter):
        # Transform src
        src_h = np.hstack([src_s, np.ones((len(src_s), 1))])
        src_t = (T @ src_h.T).T[:, :3]
        # Nearest neighbor in tgt
        tree = cKDTree(tgt_s)
        d, idx = tree.query(src_t, k=1)
        correspondences = tgt_s[idx]
        # Kabsch: best rigid transform aligning src_t → correspondences
        mu_s = src_t.mean(0)
        mu_t = correspondences.mean(0)
        H = (src_t - mu_s).T @ (correspondences - mu_t)
        U, S, Vt = np.linalg.svd(H)
        R = Vt.T @ U.T
        if np.linalg.det(R) < 0:
            Vt[-1] *= -1
            R = Vt.T @ U.T
        t = mu_t - R @ mu_s
        dT = np.eye(4)
        dT[:3, :3] = R
        dT[:3, 3] = t
        T = dT @ T
        err = d.mean()
        if abs(prev_err - err) < 1e-4:
            break
        prev_err = err

    # Apply final transform to full src
    src_h = np.hstack([src, np.ones((len(src), 1))])
    src_aligned = (T @ src_h.T).T[:, :3]
    return src_aligned, T, err


def filter_floaters(pts: np.ndarray, z_min: float = None, z_max: float = None) -> np.ndarray:
    """Optional filter to remove obvious floaters by z range."""
    mask = np.ones(len(pts), dtype=bool)
    if z_min is not None:
        mask &= pts[:, 2] >= z_min
    if z_max is not None:
        mask &= pts[:, 2] <= z_max
    return pts[mask]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ckpt", required=True)
    ap.add_argument("--gt", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--thresholds", nargs="+", type=float, default=[0.5, 1.0])
    ap.add_argument("--align", choices=["none", "icp"], default="none")
    ap.add_argument("--filter-floaters", action="store_true",
                    help="Drop pred points with z outside [gt_z_min - margin, gt_z_max + margin]")
    ap.add_argument("--max-gt", type=int, default=5_000_000)
    args = ap.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    # Load predicted centers
    sd = torch.load(args.ckpt, map_location="cpu", weights_only=False)["state_dict"]
    pred = sd["means"].cpu().numpy().astype(np.float64)
    print(f"[data] pred centers: {pred.shape}, "
          f"z range [{pred[:,2].min():.2f}, {pred[:,2].max():.2f}]")

    # Load GT
    gt = read_ply_xyz(args.gt)
    print(f"[data] gt points: {gt.shape}, "
          f"z range [{gt[:,2].min():.2f}, {gt[:,2].max():.2f}]")

    # Optional: filter floaters first (huge negative z)
    pred_raw = pred.copy()
    if args.filter_floaters:
        z_margin = 2.0
        z_lo = gt[:, 2].min() - z_margin
        z_hi = gt[:, 2].max() + z_margin
        pred = filter_floaters(pred, z_min=z_lo, z_max=z_hi)
        print(f"[filter] floaters removed: {len(pred_raw)} -> {len(pred)} "
              f"(kept z in [{z_lo:.2f}, {z_hi:.2f}])")

    # Subsample GT for speed
    if len(gt) > args.max_gt:
        idx = np.random.choice(len(gt), args.max_gt, replace=False)
        gt = gt[idx]
        print(f"[data] gt subsampled to {len(gt)}")

    # ICP alignment
    align_info = {"method": args.align}
    if args.align == "icp":
        print("[icp] running alignment...")
        pred, T, icp_err = icp_align(pred, gt, max_iter=30, sample=200_000)
        align_info["T"] = T.tolist()
        align_info["final_mean_nn_dist"] = float(icp_err)
        print(f"[icp] done, final mean nn dist = {icp_err:.4f}")

    # Compute metrics
    results = chamfer_and_f1(pred, gt, thresholds=args.thresholds)
    results["align"] = align_info
    if args.filter_floaters:
        results["n_pred_filtered_out"] = int(len(pred_raw) - (len(pred) if args.align == "none" else len(pred)))
    print(json.dumps(results, indent=2))

    (out_dir / "geometry_metrics.json").write_text(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
