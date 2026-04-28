"""Compute F1@0.5m and F1@1m of rendered depth vs GT depth (Phase 1-style).

For each Phase 2 ckpt + each eval view:
  - Render depth (from primitives)
  - Get GT depth from dataset
  - Convert both to 3D point clouds (using camera intrinsics + extrinsics)
  - Compute bidirectional F1 at 0.5m and 1.0m thresholds

Output: 4-condition summary.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import torch

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from src.stage2.model import GaussianModel2D, quat_to_rotmat
from src.stage2.dataloader import ColmapDataset
from src.stage2.renderer import render
from scripts.phase2_synthesis.perturb_psnr_test import make_model

CONDS_PHASE2 = {
    "Baseline":  "results/phase2_ablation_citygml/baseline/ckpt/final.pt",
    "Mutual":    "results/phase2_ablation_citygml/mutual/ckpt/final.pt",
    "Structure": "results/phase2_ablation_citygml/structure/ckpt/final.pt",
    "Both":      "results/phase2_ablation_citygml/both/ckpt/final.pt",
}


def depth_to_pcd(depth, K, w2c, mask=None, sample_stride=4):
    """Back-project depth to world-frame point cloud.

    depth: (H, W) float
    K: (3, 3)
    w2c: (4, 4)
    """
    H, W = depth.shape
    yy, xx = np.meshgrid(np.arange(0, H, sample_stride),
                          np.arange(0, W, sample_stride), indexing='ij')
    z = depth[yy, xx]
    if mask is not None:
        m = mask[yy, xx]
    else:
        m = z > 0
    if not m.any():
        return np.zeros((0, 3))
    yy, xx, z = yy[m], xx[m], z[m]
    fx, fy, cx, cy = K[0, 0], K[1, 1], K[0, 2], K[1, 2]
    xc = (xx - cx) * z / fx
    yc = (yy - cy) * z / fy
    pts_cam = np.stack([xc, yc, z], axis=-1)  # (N, 3)
    # transform cam→world: pts_world = R^T * (pts_cam - t) where w2c = [R | t]
    R = w2c[:3, :3]
    t = w2c[:3, 3]
    pts_world = (pts_cam - t[None, :]) @ R   # = R^T * (p - t)
    return pts_world


def f1_at(pred, gt, thresh):
    """Bidirectional F1 from KD-tree NN distances."""
    if pred.shape[0] == 0 or gt.shape[0] == 0:
        return 0.0
    from scipy.spatial import cKDTree
    tp = cKDTree(pred); tg = cKDTree(gt)
    d_p2g, _ = tg.query(pred, k=1)
    d_g2p, _ = tp.query(gt, k=1)
    precision = float((d_p2g < thresh).mean())
    recall    = float((d_g2p < thresh).mean())
    if precision + recall == 0:
        return 0.0
    return 2 * precision * recall / (precision + recall)


def evaluate(ckpt_path, ds, eval_idx, device="cuda", n_max=20):
    sd = torch.load(ckpt_path, map_location="cpu")["state_dict"]
    means = sd["means"].float().to(device)
    quats = sd["quats"].float().to(device)
    log_scales = sd["log_scales"].float().to(device)
    opa_raw = sd["opacities_raw"].float().to(device)
    sem = sd["sem_logits"].float().to(device)
    sh0 = sd["sh0"].float().to(device)
    shN = sd["shN"].float().to(device)
    model = make_model(means, quats, log_scales, opa_raw, sem, sh0, shN, device)

    f1_05_list = []
    f1_10_list = []
    n_done = 0
    for vi in eval_idx:
        if n_done >= n_max:
            break
        item = ds[vi]
        if "depth" not in item:
            continue
        H, W = item["height"], item["width"]
        w2c_t = item["w2c"].to(device)
        K_t = item["K"].to(device)
        gt_depth = item["depth"].cpu().numpy()  # (H, W)
        gt_mask = item["depth_mask"].cpu().numpy() if "depth_mask" in item else (gt_depth > 0)

        with torch.no_grad():
            out = render(model, w2c_t, K_t, W, H, sh_degree=3, render_mode="RGB+ED")
        pred_depth = out["depth"].squeeze(0).cpu().numpy()
        pred_mask = pred_depth > 0.01
        valid = gt_mask & pred_mask & (gt_depth < 1e3) & (pred_depth < 1e3)

        # depth → 3D point clouds (world frame)
        K_np = K_t.cpu().numpy()
        w2c_np = w2c_t.cpu().numpy()
        gt_pcd = depth_to_pcd(gt_depth, K_np, w2c_np, mask=valid, sample_stride=4)
        pred_pcd = depth_to_pcd(pred_depth, K_np, w2c_np, mask=valid, sample_stride=4)

        if gt_pcd.shape[0] < 100 or pred_pcd.shape[0] < 100:
            continue
        f1_05 = f1_at(pred_pcd, gt_pcd, 0.5)
        f1_10 = f1_at(pred_pcd, gt_pcd, 1.0)
        f1_05_list.append(f1_05); f1_10_list.append(f1_10)
        n_done += 1

    return {
        "n_views": n_done,
        "F1@0.5m": float(np.mean(f1_05_list)) if f1_05_list else float("nan"),
        "F1@1.0m": float(np.mean(f1_10_list)) if f1_10_list else float("nan"),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-root", default="results/phase2_synthesis/dataset")
    ap.add_argument("--out", default="results/phase2_ablation_citygml/_f1_geometry")
    ap.add_argument("--n-views", type=int, default=20)
    args = ap.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    device = "cuda"

    ds = ColmapDataset(root=args.data_root, downscale=1.0,
                       load_depth=True, load_normal=False, load_semantic=False)
    eval_idx = [i for i in range(len(ds)) if i % 10 == 9]
    print(f"[F1] {len(ds)} frames, {len(eval_idx)} eval views, using {min(args.n_views, len(eval_idx))}")

    summary = {}
    for cond, ck in CONDS_PHASE2.items():
        ck_path = _ROOT / ck
        if not ck_path.exists():
            print(f"  {cond}: SKIP")
            continue
        print(f"\n=== {cond} ===")
        res = evaluate(str(ck_path), ds, eval_idx, device=device, n_max=args.n_views)
        print(f"  F1@0.5m = {res['F1@0.5m']:.4f}   F1@1.0m = {res['F1@1.0m']:.4f}   (n={res['n_views']})")
        summary[cond] = res

    out_path = out_dir / "phase2_f1_geometry.json"
    with open(out_path, "w") as f:
        json.dump(summary, f, indent=2)
    print(f"\nwrote {out_path}")

    print("\n" + "="*60)
    print(f"{'Cond':<12} {'F1@0.5m':>10} {'F1@1.0m':>10}")
    print("="*60)
    for cond, r in summary.items():
        print(f"{cond:<12} {r['F1@0.5m']:>10.4f} {r['F1@1.0m']:>10.4f}")
    print("\nReference (Phase 1 ablation REPORT):")
    print("  Baseline   0.998   ?")
    print("  Mutual     0.998   ?")
    print("  Structure  0.999   ?")
    print("  Both       0.999   ?")


if __name__ == "__main__":
    main()
