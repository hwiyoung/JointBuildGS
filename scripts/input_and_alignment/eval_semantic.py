"""Semantic evaluation: render semantic, argmax, compare to rule-based GT.

Metrics: mIoU (overall), per-class IoU.

Usage:
    python scripts/input_and_alignment/eval_semantic.py \
        --ckpt results/phase1_semantic/run/ckpt/final.pt \
        --config configs/input_and_alignment/matrixcity_step1_3.yaml \
        --out results/phase1_semantic/run/eval_semantic \
        --test-ratio 0.1 --max-views 100
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import torch
import yaml
from tqdm import tqdm

from src.stage2.dataloader import ColmapDataset
from src.stage2.model import GaussianModel2D
from src.stage2.renderer import render_semantic


K_CLASS = 4
CLASS_NAMES = ["BG", "Roof", "Wall", "Terrain"]


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
    print(f"[eval-sem] test={len(test_idx)}")

    # Accumulate confusion matrix (K x K). rows: gt, cols: pred.
    confusion = np.zeros((K_CLASS, K_CLASS), dtype=np.int64)
    n_with_gt = 0

    for idx in tqdm(test_idx, desc="eval-sem"):
        b = ds[idx]
        if "semantic" not in b:
            continue
        gt = b["semantic"].numpy()  # (H, W) int
        w2c = b["w2c"].to(device)
        Kcam = b["K"].to(device)
        H, W = b["height"], b["width"]
        with torch.no_grad():
            logits = render_semantic(model, w2c, Kcam, W, H)  # (H, W, K)
        pred = logits.argmax(dim=-1).cpu().numpy().astype(np.int64)

        valid = gt != 0  # ignore BG (class 0) per ignore_index
        for c_gt in range(K_CLASS):
            for c_pr in range(K_CLASS):
                confusion[c_gt, c_pr] += int(((gt == c_gt) & (pred == c_pr) & valid).sum())
        n_with_gt += 1

    # IoU per class (excluding BG since it's ignore)
    ious = {}
    per_class = {}
    for c in range(1, K_CLASS):
        tp = confusion[c, c]
        fp = confusion[:, c].sum() - tp
        fn = confusion[c, :].sum() - tp
        denom = tp + fp + fn
        iou = float(tp / denom) if denom > 0 else float("nan")
        ious[CLASS_NAMES[c]] = iou
        per_class[CLASS_NAMES[c]] = {
            "iou": iou,
            "tp": int(tp),
            "fp": int(fp),
            "fn": int(fn),
        }

    miou = float(np.mean([v for v in ious.values() if not np.isnan(v)]))
    overall_acc = float(np.diag(confusion).sum() / max(confusion.sum(), 1))

    results = {
        "n_test_views": n_with_gt,
        "mIoU (excl. BG)": miou,
        "overall_accuracy": overall_acc,
        "per_class_iou": ious,
        "per_class_details": per_class,
        "confusion_matrix": confusion.tolist(),
        "class_names": CLASS_NAMES,
    }
    print(json.dumps(results, indent=2))
    (out_dir / "semantic_metrics.json").write_text(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
