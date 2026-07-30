"""Render same views with two checkpoints (Step A vs Step B) for side-by-side comparison.

Selection: 4 views chosen by diagnostic criteria on semantic (if available):
  - best mIoU (Step A), worst mIoU (Step A), max RT confusion, max Wall error
OR if --simple, use linspace.

Output per row: RGB_GT | Step A render | Step B render | diff(A,B) ×5
"""
from __future__ import annotations

import argparse
from pathlib import Path

import imageio.v2 as imageio
import numpy as np
import torch
import yaml

from src.stage2.dataloader import ColmapDataset
from src.stage2.model import GaussianModel2D
from src.stage2.renderer import render


def _load(ckpt, cfg, device):
    ds_tmp = ColmapDataset(cfg["data_root"], downscale=cfg.get("downscale", 1.0),
                           load_depth=False, load_normal=False)
    m = GaussianModel2D(ds_tmp.points_xyz, ds_tmp.points_rgb,
                        sh_degree=cfg.get("sh_degree", 3), device=device).to(device)
    sd = torch.load(ckpt, map_location=device, weights_only=False)["state_dict"]
    for name, p in list(m.named_parameters()):
        t = sd.get(name)
        if t is None: continue
        if p.shape != t.shape:
            parts = name.split("."); obj = m
            for pp in parts[:-1]: obj = getattr(obj, pp)
            setattr(obj, parts[-1], torch.nn.Parameter(t.clone()))
        else:
            p.data.copy_(t)
    return m


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ckpt-a", required=True)
    ap.add_argument("--ckpt-b", required=True)
    ap.add_argument("--config", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--label-a", default="A")
    ap.add_argument("--label-b", default="B")
    ap.add_argument("--views", nargs="+", type=int, required=True,
                    help="explicit frame indices to render")
    args = ap.parse_args()

    with open(args.config) as f: cfg = yaml.safe_load(f)
    device = "cuda"
    ds = ColmapDataset(cfg["data_root"], downscale=cfg.get("downscale", 1.0),
                       load_depth=False, load_normal=False)
    mA = _load(args.ckpt_a, cfg, device)
    mB = _load(args.ckpt_b, cfg, device)

    out_dir = Path(args.out); out_dir.mkdir(parents=True, exist_ok=True)

    rows = []
    for idx in args.views:
        b = ds[idx]
        gt = (b["rgb"].numpy() * 255).astype(np.uint8)
        w2c = b["w2c"].to(device); K = b["K"].to(device)
        H, W = b["height"], b["width"]
        with torch.no_grad():
            oa = render(mA, w2c, K, W, H, sh_degree=mA.max_sh_degree, render_mode="RGB+ED")
            ob = render(mB, w2c, K, W, H, sh_degree=mB.max_sh_degree, render_mode="RGB+ED")
        rA = (oa["rgb"].clamp(0,1).cpu().numpy() * 255).astype(np.uint8)
        rB = (ob["rgb"].clamp(0,1).cpu().numpy() * 255).astype(np.uint8)
        diff = np.clip(np.abs(rA.astype(np.int32) - rB.astype(np.int32)) * 5, 0, 255).astype(np.uint8)
        row = np.concatenate([gt, rA, rB, diff], axis=1)
        rows.append(row)
        # individual
        imageio.imwrite(out_dir / f"v{idx:04d}_gt.png", gt)
        imageio.imwrite(out_dir / f"v{idx:04d}_{args.label_a}.png", rA)
        imageio.imwrite(out_dir / f"v{idx:04d}_{args.label_b}.png", rB)
        imageio.imwrite(out_dir / f"v{idx:04d}_diff_x5.png", diff)

    panel = np.concatenate(rows, axis=0)
    imageio.imwrite(out_dir / "compare_steps.png", panel)
    # caption
    (out_dir / "README.txt").write_text(
        f"Layout per row: GT | {args.label_a} | {args.label_b} | diff×5\n"
        f"Views: {args.views}\n"
    )
    print(f"wrote {out_dir}/compare_steps.png ({len(args.views)} rows)")


if __name__ == "__main__":
    main()
