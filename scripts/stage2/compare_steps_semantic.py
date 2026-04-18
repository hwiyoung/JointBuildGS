"""Render semantic predictions for two checkpoints on same views, side-by-side.

Layout per row: GT_RGB | GT_sem | Step-A pred | Step-B pred | Step-A err | Step-B err
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
from src.stage2.renderer import render_semantic


COLORS = np.array([[0,0,0],[220,60,60],[60,180,60],[60,80,200]], dtype=np.uint8)


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


def err_mask(gt, pred):
    out = np.zeros((*gt.shape, 3), dtype=np.uint8)
    valid = gt != 0
    out[~valid] = [80,80,80]
    out[(gt==pred) & valid] = [50,180,50]
    out[(gt!=pred) & valid] = [230,50,50]
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ckpt-a", required=True)
    ap.add_argument("--ckpt-b", required=True)
    ap.add_argument("--config", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--label-a", default="A")
    ap.add_argument("--label-b", default="B")
    ap.add_argument("--views", nargs="+", type=int, required=True)
    args = ap.parse_args()

    with open(args.config) as f: cfg = yaml.safe_load(f)
    device = "cuda"
    ds = ColmapDataset(cfg["data_root"], downscale=cfg.get("downscale", 1.0),
                       load_depth=False, load_normal=False, load_semantic=True)
    mA = _load(args.ckpt_a, cfg, device)
    mB = _load(args.ckpt_b, cfg, device)

    out_dir = Path(args.out); out_dir.mkdir(parents=True, exist_ok=True)

    rows = []
    stats = []
    for idx in args.views:
        b = ds[idx]
        gt = b["semantic"].numpy()
        rgb = (b["rgb"].numpy() * 255).astype(np.uint8)
        w2c = b["w2c"].to(device); K = b["K"].to(device)
        H, W = b["height"], b["width"]
        with torch.no_grad():
            pa = render_semantic(mA, w2c, K, W, H).argmax(-1).cpu().numpy().astype(np.int64)
            pb = render_semantic(mB, w2c, K, W, H).argmax(-1).cpu().numpy().astype(np.int64)

        # per-frame mIoU
        def iou(gt, pr):
            ious = []
            valid = gt != 0
            for c in range(1, 4):
                tp = ((gt==c)&(pr==c)&valid).sum()
                fp = ((pr==c)&(gt!=c)&valid).sum()
                fn = ((gt==c)&(pr!=c)&valid).sum()
                d = tp+fp+fn
                ious.append(tp/d if d>0 else float("nan"))
            return np.nanmean(ious)
        mA_iou = iou(gt, pa)
        mB_iou = iou(gt, pb)

        row = np.concatenate([rgb, COLORS[gt], COLORS[pa], COLORS[pb],
                              err_mask(gt, pa), err_mask(gt, pb)], axis=1)
        rows.append(row)
        stats.append((idx, mA_iou, mB_iou))

    min_w = min(r.shape[1] for r in rows)
    rows = [r[:, :min_w] for r in rows]
    panel = np.concatenate(rows, axis=0)
    imageio.imwrite(out_dir / "compare_semantic.png", panel)

    caption = f"Layout per row: RGB | GT_sem | {args.label_a} pred | {args.label_b} pred | {args.label_a} err | {args.label_b} err\n"
    caption += f"(BG=black, Roof=red, Wall=green, Terrain=blue; err: gray=ignore, green=correct, red=wrong)\n\n"
    for idx, ma, mb in stats:
        caption += f"idx={idx}: {args.label_a} mIoU={ma:.3f}, {args.label_b} mIoU={mb:.3f}, Δ={mb-ma:+.3f}\n"
    (out_dir / "README.txt").write_text(caption)
    print(caption)


if __name__ == "__main__":
    main()
