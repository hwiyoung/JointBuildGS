"""Full test-set rendering evaluation: PSNR, SSIM, LPIPS.

Usage (inside container):
    python scripts/stage2/eval_rendering.py \
        --ckpt results/phase1_vanilla/run/ckpt/final.pt \
        --config configs/input_and_alignment/matrixcity_vanilla.yaml \
        --out results/phase1_vanilla/run/eval_rendering \
        --test-ratio 0.1
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F
import yaml
from tqdm import tqdm

from src.stage2.dataloader import ColmapDataset
from src.stage2.model import GaussianModel2D
from src.stage2.renderer import render


def _load_model(ckpt_path, cfg, device):
    ds_tmp = ColmapDataset(root=cfg["data_root"], downscale=cfg.get("downscale", 1.0),
                           load_depth=False, load_normal=False)
    model = GaussianModel2D(points_xyz=ds_tmp.points_xyz, points_rgb=ds_tmp.points_rgb,
                            sh_degree=cfg.get("sh_degree", 3), device=device).to(device)
    sd = torch.load(ckpt_path, map_location=device, weights_only=False)["state_dict"]
    for name, p in list(model.named_parameters()):
        t = sd.get(name)
        if t is None:
            continue
        if p.shape != t.shape:
            parts = name.split(".")
            obj = model
            for pp in parts[:-1]:
                obj = getattr(obj, pp)
            setattr(obj, parts[-1], torch.nn.Parameter(t.clone()))
        else:
            p.data.copy_(t)
    return model, ds_tmp


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ckpt", required=True)
    ap.add_argument("--config", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--test-ratio", type=float, default=0.1)
    ap.add_argument("--max-views", type=int, default=100, help="cap test views for speed")
    args = ap.parse_args()

    with open(args.config) as f:
        cfg = yaml.safe_load(f)
    device = "cuda"
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    model, ds = _load_model(args.ckpt, cfg, device)

    n = len(ds)
    test_start = max(1, int(n * (1 - args.test_ratio)))
    test_idx = list(range(test_start, n))
    if args.max_views and len(test_idx) > args.max_views:
        stride = len(test_idx) // args.max_views
        test_idx = test_idx[::stride][:args.max_views]
    print(f"[eval] frames={n}, test={len(test_idx)} (start={test_start})")

    # Metrics
    from pytorch_msssim import ssim as ssim_fn
    import lpips
    lpips_net = lpips.LPIPS(net="vgg").to(device).eval()

    psnrs, ssims, lpips_vals = [], [], []

    for idx in tqdm(test_idx, desc="eval"):
        b = ds[idx]
        rgb_gt = b["rgb"].to(device)  # (H,W,3) [0,1]
        w2c = b["w2c"].to(device)
        K = b["K"].to(device)
        H, W = b["height"], b["width"]
        with torch.no_grad():
            o = render(model, w2c, K, W, H, sh_degree=model.max_sh_degree, render_mode="RGB+ED")
        rgb_pred = o["rgb"].clamp(0, 1)

        mse = ((rgb_pred - rgb_gt) ** 2).mean().item()
        psnrs.append(-10 * math.log10(max(mse, 1e-10)))

        # SSIM & LPIPS expect (1,3,H,W)
        p = rgb_pred.permute(2, 0, 1).unsqueeze(0)
        g = rgb_gt.permute(2, 0, 1).unsqueeze(0)
        with torch.no_grad():
            ssims.append(float(ssim_fn(p, g, data_range=1.0)))
            # LPIPS expects [-1,1]
            lp = lpips_net(p * 2 - 1, g * 2 - 1).item()
            lpips_vals.append(lp)

    summary = {
        "n_test_views": len(test_idx),
        "psnr_mean": float(np.mean(psnrs)),
        "psnr_std": float(np.std(psnrs)),
        "ssim_mean": float(np.mean(ssims)),
        "ssim_std": float(np.std(ssims)),
        "lpips_mean": float(np.mean(lpips_vals)),
        "lpips_std": float(np.std(lpips_vals)),
    }
    (out_dir / "rendering_metrics.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
