"""Render semantic maps for a few views and save side-by-side with GT.

Usage:
    python scripts/input_and_alignment/visualization_and_export/render_semantic_views.py --ckpt ... --config ... --out ... --n 4
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


COLORS = np.array([
    [0, 0, 0],         # BG
    [220, 60, 60],     # Roof
    [60, 180, 60],     # Wall
    [60, 80, 200],     # Terrain
], dtype=np.uint8)


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
    return model


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
    out_dir = Path(args.out); out_dir.mkdir(parents=True, exist_ok=True)

    model = _load_model(args.ckpt, cfg, device)
    ds = ColmapDataset(root=cfg["data_root"], downscale=cfg.get("downscale", 1.0),
                       load_depth=False, load_normal=False, load_semantic=True)
    idxs = np.linspace(0, len(ds) - 1, args.n, dtype=int).tolist()

    rows = []
    for k, idx in enumerate(idxs):
        b = ds[idx]
        w2c = b["w2c"].to(device)
        Kcam = b["K"].to(device)
        H, W = b["height"], b["width"]
        with torch.no_grad():
            logits = render_semantic(model, w2c, Kcam, W, H)
        pred = logits.argmax(dim=-1).cpu().numpy().astype(np.int64)
        pred_rgb = COLORS[pred]

        rgb_gt = (b["rgb"].numpy() * 255).astype(np.uint8)

        if "semantic" in b:
            gt_rgb = COLORS[b["semantic"].numpy()]
        else:
            gt_rgb = np.zeros_like(pred_rgb)

        imageio.imwrite(out_dir / f"v{k:02d}_sem_pred.png", pred_rgb)
        imageio.imwrite(out_dir / f"v{k:02d}_sem_gt.png", gt_rgb)
        row = np.concatenate([rgb_gt, gt_rgb, pred_rgb], axis=1)
        rows.append(row)

    min_w = min(r.shape[1] for r in rows)
    rows = [r[:, :min_w] for r in rows]
    panel = np.concatenate(rows, axis=0)
    imageio.imwrite(out_dir / "semantic_comparison.png", panel)
    print(f"wrote {len(idxs)} views and panel")


if __name__ == "__main__":
    main()
