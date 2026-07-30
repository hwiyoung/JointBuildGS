"""Phase 1 visual verification — building-heavy views at full resolution.

For each view, render side-by-side:
  Row 1 (photo): GT | Baseline | Mutual | Structure | Both
  Row 2 (semantic): GT_sem | Baseline | Mutual | Structure | Both
Output: one large PNG per view (no matplotlib, direct pixel concatenation).

Purpose: let user eyeball "does Phase 1 actually reconstruct buildings well?"
  - Photo row shows photometric quality (Both should be close to GT)
  - Semantic row shows class prediction quality (Both should match GT Wall/Roof/Terrain layout)
"""
from __future__ import annotations

import argparse
from pathlib import Path

import imageio.v2 as imageio
import numpy as np
import torch
import yaml

import sys; sys.path.insert(0, ".")
from src.stage2.dataloader import ColmapDataset
from src.stage2.model import GaussianModel2D
from src.stage2.renderer import render, render_semantic


COLORS = np.array([
    [0, 0, 0],          # BG (black)
    [220, 60, 60],      # Roof (red)
    [60, 80, 200],      # Wall (blue)
    [60, 180, 60],      # Terrain (green)
], dtype=np.uint8)


def load_model(ckpt, cfg, device, ds):
    m = GaussianModel2D(ds.points_xyz, ds.points_rgb,
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


def label_strip(text, width, height=30, color=(240, 240, 240)):
    """Simple text-strip using PIL."""
    from PIL import Image, ImageDraw, ImageFont
    img = Image.new("RGB", (width, height), color=color)
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 18)
    except Exception:
        font = ImageFont.load_default()
    draw.text((width // 2, height // 2), text, fill=(20, 20, 20), font=font, anchor="mm")
    return np.array(img)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="configs/input_and_alignment/matrixcity_step1_6.yaml")
    ap.add_argument("--views", nargs="+", type=int, default=[408, 801, 4870, 27])
    ap.add_argument("--out-dir", default="results/phase1_ablation/figures/phase1_visual_check")
    args = ap.parse_args()

    cfg = yaml.safe_load(open(args.config))
    device = "cuda"
    ds = ColmapDataset(cfg["data_root"], downscale=cfg.get("downscale", 1.0),
                       load_depth=False, load_normal=False, load_semantic=True)

    conds = [
        ("Baseline", "results/phase1_semantic/run/ckpt/final.pt"),
        ("Mutual",   "results/phase1_mutual/run/ckpt/final.pt"),
        ("Structure","results/phase1_structure/run/ckpt/final.pt"),
        ("Both",     "results/phase1_ablation/run/ckpt/final.pt"),
    ]
    print("loading 4 models...")
    models = [(lbl, load_model(p, cfg, device, ds)) for lbl, p in conds]

    out = Path(args.out_dir); out.mkdir(parents=True, exist_ok=True)

    for idx in args.views:
        b = ds[idx]
        gt_rgb = (b["rgb"].numpy() * 255).astype(np.uint8)
        gt_sem_t = b.get("semantic")
        gt_sem_np = gt_sem_t.numpy() if hasattr(gt_sem_t, "numpy") else np.array(gt_sem_t)
        gt_sem_img = COLORS[np.clip(gt_sem_np.astype(np.int64), 0, 3)]
        w2c = b["w2c"]; K = b["K"]
        H, W = b["height"], b["width"]

        photos = [("GT", gt_rgb)]
        sems = [("GT", gt_sem_img)]
        for lbl, m in models:
            with torch.no_grad():
                pout = render(m, w2c.to(device), K.to(device), W, H,
                              sh_degree=m.max_sh_degree, render_mode="RGB+ED")
                rgb = (pout["rgb"].detach().clamp(0, 1).cpu().numpy() * 255).astype(np.uint8)
                logits = render_semantic(m, w2c.to(device), K.to(device), W, H)
                pred = logits.detach().cpu().numpy().argmax(axis=-1).clip(0, 3)
                sem_img = COLORS[pred]
            photos.append((lbl, rgb))
            sems.append((lbl, sem_img))

        # Build labeled panel
        col_labels_photo = [label_strip(f"Photo — {lbl}", W) for lbl, _ in photos]
        col_labels_sem = [label_strip(f"Semantic — {lbl}", W) for lbl, _ in sems]
        photo_row_imgs = np.concatenate([i for _, i in photos], axis=1)
        photo_label_row = np.concatenate(col_labels_photo, axis=1)
        sem_row_imgs = np.concatenate([i for _, i in sems], axis=1)
        sem_label_row = np.concatenate(col_labels_sem, axis=1)

        panel = np.concatenate([
            photo_label_row, photo_row_imgs,
            sem_label_row, sem_row_imgs,
        ], axis=0)
        imageio.imwrite(out / f"v{idx:04d}_panel.png", panel)
        print(f"wrote v{idx:04d}_panel.png  ({W}×{H} per cell, 5 cols)")

    (out / "README.txt").write_text(
        "Phase 1 visual verification panels.\n"
        "Layout: 5 cols × 4 rows (labels + photos + labels + semantic).\n"
        "  Cols: GT, Baseline, Mutual, Structure, Both\n"
        "  Semantic colors: BG=black, Roof=red, Wall=blue, Terrain=green\n"
        "Views selected for high building content (Roof + Wall > 80% of pixels).\n"
    )


if __name__ == "__main__":
    main()
