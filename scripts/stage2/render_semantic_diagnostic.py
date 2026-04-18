"""Render semantic comparisons selected by diagnostic criteria.

Picks 4 representative test frames:
  (1) Best: highest per-frame mIoU
  (2) Worst: lowest per-frame mIoU
  (3) Roof↔Terrain confusion: max (Roof/Terrain mix-up rate)
  (4) Wall boundary error: max Wall FP+FN

Output layout per row: [RGB | GT sem | Pred sem | Error mask]
Error mask: gray = ignore(BG in GT), green = correct, red = wrong
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import imageio.v2 as imageio
import numpy as np
import torch
import yaml
from tqdm import tqdm

from src.stage2.dataloader import ColmapDataset
from src.stage2.model import GaussianModel2D
from src.stage2.renderer import render_semantic


COLORS = np.array([
    [0, 0, 0],         # BG
    [220, 60, 60],     # Roof
    [60, 180, 60],     # Wall
    [60, 80, 200],     # Terrain
], dtype=np.uint8)
CLASS_NAMES = ["BG", "Roof", "Wall", "Terrain"]


def _load_model(ckpt, cfg, device):
    ds_tmp = ColmapDataset(root=cfg["data_root"], downscale=cfg.get("downscale", 1.0),
                           load_depth=False, load_normal=False)
    model = GaussianModel2D(ds_tmp.points_xyz, ds_tmp.points_rgb,
                            sh_degree=cfg.get("sh_degree", 3), device=device).to(device)
    sd = torch.load(ckpt, map_location=device, weights_only=False)["state_dict"]
    for name, p in list(model.named_parameters()):
        t = sd.get(name)
        if t is None: continue
        if p.shape != t.shape:
            parts = name.split(".")
            obj = model
            for pp in parts[:-1]: obj = getattr(obj, pp)
            setattr(obj, parts[-1], torch.nn.Parameter(t.clone()))
        else:
            p.data.copy_(t)
    return model


def per_frame_stats(gt, pred):
    """Compute per-frame stats on valid pixels (gt != 0)."""
    valid = gt != 0
    if valid.sum() == 0:
        return None
    correct = ((gt == pred) & valid).sum()
    total = valid.sum()
    acc = correct / total

    # Roof↔Terrain confusion: pred=Terrain where GT=Roof, or pred=Roof where GT=Terrain
    roof_to_terrain = ((gt == 1) & (pred == 3) & valid).sum()
    terrain_to_roof = ((gt == 3) & (pred == 1) & valid).sum()
    rt_valid = ((gt == 1) | (gt == 3)) & valid
    rt_confusion = (roof_to_terrain + terrain_to_roof) / max(rt_valid.sum(), 1)

    # Wall errors: GT=Wall but pred!=Wall, or pred=Wall but GT!=Wall
    wall_fp = ((pred == 2) & (gt != 2) & valid).sum()
    wall_fn = ((gt == 2) & (pred != 2) & valid).sum()
    wall_valid = ((gt == 2) | (pred == 2)) & valid
    wall_err = (wall_fp + wall_fn) / max(wall_valid.sum(), 1)

    # per-class IoU on this frame
    ious = {}
    for c in range(1, 4):
        tp = ((gt == c) & (pred == c) & valid).sum()
        fp = ((pred == c) & (gt != c) & valid).sum()
        fn = ((gt == c) & (pred != c) & valid).sum()
        d = tp + fp + fn
        ious[CLASS_NAMES[c]] = float(tp / d) if d > 0 else float("nan")

    miou = np.nanmean([v for v in ious.values()])
    return {
        "acc": float(acc),
        "miou": float(miou),
        "iou_per_class": {k: float(v) for k, v in ious.items()},
        "rt_confusion_rate": float(rt_confusion),
        "wall_err_rate": float(wall_err),
        "valid_px": int(total),
    }


def make_error_mask(gt, pred):
    """Gray where gt=BG (ignore), green=correct, red=wrong."""
    H, W = gt.shape
    img = np.zeros((H, W, 3), dtype=np.uint8)
    valid = gt != 0
    img[~valid] = [80, 80, 80]  # gray
    correct = (gt == pred) & valid
    wrong = (gt != pred) & valid
    img[correct] = [50, 180, 50]
    img[wrong] = [230, 50, 50]
    return img


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ckpt", required=True)
    ap.add_argument("--config", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--test-ratio", type=float, default=0.1)
    ap.add_argument("--max-views", type=int, default=100)
    args = ap.parse_args()

    with open(args.config) as f:
        cfg = yaml.safe_load(f)
    device = "cuda"
    out_dir = Path(args.out); out_dir.mkdir(parents=True, exist_ok=True)

    model = _load_model(args.ckpt, cfg, device)
    ds = ColmapDataset(root=cfg["data_root"], downscale=cfg.get("downscale", 1.0),
                       load_depth=False, load_normal=False, load_semantic=True)

    n = len(ds)
    test_start = max(1, int(n * (1 - args.test_ratio)))
    test_idx = list(range(test_start, n))
    if args.max_views and len(test_idx) > args.max_views:
        stride = len(test_idx) // args.max_views
        test_idx = test_idx[::stride][:args.max_views]
    print(f"[diag] scanning {len(test_idx)} test views...")

    records = []
    preds_cache = {}
    for idx in tqdm(test_idx, desc="scan"):
        b = ds[idx]
        if "semantic" not in b: continue
        with torch.no_grad():
            logits = render_semantic(model, b["w2c"].to(device), b["K"].to(device),
                                     b["width"], b["height"])
        pred = logits.argmax(dim=-1).cpu().numpy().astype(np.int64)
        gt = b["semantic"].numpy()
        stats = per_frame_stats(gt, pred)
        if stats is None: continue
        stats["idx"] = idx
        records.append(stats)
        preds_cache[idx] = pred

    # Select 4 representative frames
    # (1) best miou, (2) worst miou (among frames with enough valid px),
    # (3) max Roof↔Terrain confusion, (4) max Wall error
    min_valid_px = 500_000  # at least 25% of image
    viable = [r for r in records if r["valid_px"] >= min_valid_px]
    viable.sort(key=lambda r: -r["miou"])
    best = viable[0]
    worst = viable[-1]
    rt = max(viable, key=lambda r: r["rt_confusion_rate"])
    wall = max(viable, key=lambda r: r["wall_err_rate"])
    # avoid duplicates
    picks = {}
    for tag, r in [("best", best), ("worst", worst), ("rt", rt), ("wall", wall)]:
        if r["idx"] not in picks:
            picks[r["idx"]] = (tag, r)
    # if duplicates, fill with next-best of whatever's missing
    while len(picks) < 4:
        for r in viable[1:]:
            if r["idx"] not in picks:
                picks[r["idx"]] = ("extra", r)
                break
        break

    # Render panel: each row = RGB | GT | Pred | Error, 4 rows
    rows = []
    captions = []
    # Order: best, rt, wall, worst
    order = []
    for tag in ["best", "rt", "wall", "worst"]:
        for k, (t, r) in picks.items():
            if t == tag:
                order.append((tag, r)); break
    for tag, r in order[:4]:
        idx = r["idx"]
        b = ds[idx]
        gt = b["semantic"].numpy()
        pred = preds_cache[idx]
        rgb = (b["rgb"].numpy() * 255).astype(np.uint8)
        gt_rgb = COLORS[gt]
        pred_rgb = COLORS[pred]
        err = make_error_mask(gt, pred)
        row = np.concatenate([rgb, gt_rgb, pred_rgb, err], axis=1)
        rows.append(row)
        captions.append(
            f"[{tag}] idx={idx} mIoU={r['miou']:.3f} "
            f"Roof={r['iou_per_class']['Roof']:.2f} "
            f"Wall={r['iou_per_class']['Wall']:.2f} "
            f"Terrain={r['iou_per_class']['Terrain']:.2f} "
            f"RT-conf={r['rt_confusion_rate']:.2%} Wall-err={r['wall_err_rate']:.2%}"
        )
        print(captions[-1])

    min_w = min(r.shape[1] for r in rows)
    rows = [r[:, :min_w] for r in rows]
    panel = np.concatenate(rows, axis=0)
    imageio.imwrite(out_dir / "semantic_diagnostic.png", panel)
    (out_dir / "captions.txt").write_text("\n".join(captions))

    # save per-frame stats
    with open(out_dir / "per_frame_stats.json", "w") as f:
        json.dump(records, f, indent=2)

    # Also save individual frames for zoom-in
    for tag, r in order[:4]:
        idx = r["idx"]
        b = ds[idx]
        gt = b["semantic"].numpy()
        pred = preds_cache[idx]
        rgb = (b["rgb"].numpy() * 255).astype(np.uint8)
        imageio.imwrite(out_dir / f"{tag}_rgb.png", rgb)
        imageio.imwrite(out_dir / f"{tag}_gt.png", COLORS[gt])
        imageio.imwrite(out_dir / f"{tag}_pred.png", COLORS[pred])
        imageio.imwrite(out_dir / f"{tag}_err.png", make_error_mask(gt, pred))


if __name__ == "__main__":
    main()
