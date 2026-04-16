"""Render RGB/Depth/Normal views from a trained checkpoint.

Usage:
    python scripts/stage2/render_views.py --ckpt <ckpt> --config <yaml> \
        --out results/phase1_vanilla/run/renders_final --n 4
"""
from __future__ import annotations

import argparse
import math
from pathlib import Path

import imageio.v2 as imageio
import numpy as np
import torch
import yaml

from src.stage2.dataloader import ColmapDataset
from src.stage2.model import GaussianModel2D
from src.stage2.renderer import render


def _depth_to_rgb(d: np.ndarray, mask: np.ndarray | None = None) -> np.ndarray:
    import matplotlib.cm as cm
    m = mask if mask is not None else (d > 0)
    if m.sum() == 0:
        return np.zeros((*d.shape, 3), dtype=np.uint8)
    lo, hi = np.percentile(d[m], [2, 98])
    x = np.clip((d - lo) / max(hi - lo, 1e-6), 0, 1)
    return (cm.turbo(x)[..., :3] * 255).astype(np.uint8)


def _normal_to_rgb(n: np.ndarray) -> np.ndarray:
    return ((n * 0.5 + 0.5).clip(0, 1) * 255).astype(np.uint8)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ckpt", required=True)
    ap.add_argument("--config", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--n", type=int, default=4)
    args = ap.parse_args()

    with open(args.config) as f:
        cfg = yaml.safe_load(f)
    device = "cuda"

    ds = ColmapDataset(root=cfg["data_root"], downscale=cfg.get("downscale", 1.0))
    model = GaussianModel2D(points_xyz=ds.points_xyz, points_rgb=ds.points_rgb,
                            sh_degree=cfg.get("sh_degree", 3), device=device).to(device)
    sd = torch.load(args.ckpt, map_location=device)["state_dict"]
    # Expand params to match stored shape
    for name, p in list(model.named_parameters()):
        t = sd.get(name)
        if t is None: continue
        if p.shape != t.shape:
            # densified checkpoint: rebuild param with correct shape
            new_p = torch.nn.Parameter(t.clone())
            # set attribute
            parts = name.split(".")
            obj = model
            for pp in parts[:-1]:
                obj = getattr(obj, pp)
            setattr(obj, parts[-1], new_p)
        else:
            p.data.copy_(t)

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    idxs = np.linspace(0, len(ds) - 1, args.n, dtype=int).tolist()

    psnrs, depth_maes, n_coses = [], [], []
    for k, idx in enumerate(idxs):
        b = ds[idx]
        rgb_gt = b["rgb"].to(device)
        w2c = b["w2c"].to(device)
        K = b["K"].to(device)
        H, W = b["height"], b["width"]
        with torch.no_grad():
            o = render(model, w2c, K, W, H, sh_degree=model.max_sh_degree, render_mode="RGB+ED")
        rgb_p = o["rgb"].clamp(0, 1).cpu().numpy()
        depth = o["depth"].cpu().numpy()
        n_world = o["normal_render"].cpu().numpy()
        # camera-frame normal for display
        R = w2c[:3, :3].cpu().numpy()
        n_cam = n_world @ R.T
        imageio.imwrite(out_dir / f"v{k:02d}_rgb_pred.png", (rgb_p * 255).astype(np.uint8))
        imageio.imwrite(out_dir / f"v{k:02d}_rgb_gt.png",   (rgb_gt.cpu().numpy() * 255).astype(np.uint8))
        imageio.imwrite(out_dir / f"v{k:02d}_depth.png",    _depth_to_rgb(depth))
        imageio.imwrite(out_dir / f"v{k:02d}_normal.png",   _normal_to_rgb(n_cam))

        mse = float(((rgb_p - rgb_gt.cpu().numpy()) ** 2).mean())
        psnrs.append(20 * math.log10(1.0) - 10 * math.log10(max(mse, 1e-10)))
        if "depth" in b:
            d_gt = b["depth"].numpy(); d_m = b["depth_mask"].numpy()
            if d_m.sum() > 0:
                depth_maes.append(float(np.abs(depth - d_gt)[d_m].mean()))
        if "normal" in b:
            n_gt = b["normal"].numpy(); n_m = b["normal_mask"].numpy()
            dot = np.abs(np.sum(n_cam * n_gt, axis=-1))
            if n_m.sum() > 0:
                n_coses.append(float(dot[n_m].mean()))

    summary = {
        "psnr_mean": float(np.mean(psnrs)),
        "depth_mae_mean": float(np.mean(depth_maes)) if depth_maes else None,
        "normal_cos_mean": float(np.mean(n_coses)) if n_coses else None,
        "n_views": len(idxs),
    }
    (out_dir / "summary.txt").write_text("\n".join(f"{k}: {v}" for k, v in summary.items()))
    print(summary)


if __name__ == "__main__":
    main()
