"""Find views where Baseline vs Both semantic prediction differs most.

Scans test views, renders semantic for Baseline + Both, measures pixel-level
disagreement. Outputs top-N views with largest diff → these are where mechanism
effect SHOULD be visible.
"""
import argparse
from pathlib import Path

import numpy as np
import torch
import yaml

import sys; sys.path.insert(0, ".")
from src.stage2.dataloader import ColmapDataset
from src.stage2.model import GaussianModel2D
from src.stage2.renderer import render_semantic


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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="configs/input_and_alignment/matrixcity_step1_6.yaml")
    ap.add_argument("--n-sample", type=int, default=200)
    ap.add_argument("--top-n", type=int, default=10)
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()

    cfg = yaml.safe_load(open(args.config))
    device = "cuda"
    ds = ColmapDataset(cfg["data_root"], downscale=cfg.get("downscale", 1.0),
                       load_depth=False, load_normal=False, load_semantic=True)

    m_base = load_model("results/phase1_semantic/run/ckpt/final.pt", cfg, device, ds)
    m_both = load_model("results/phase1_ablation/run/ckpt/final.pt", cfg, device, ds)

    import random
    random.seed(args.seed)
    indices = random.sample(range(len(ds)), args.n_sample)

    scores = []
    for idx in indices:
        b = ds[idx]
        w2c = b["w2c"].to(device); K = b["K"].to(device)
        H, W = b["height"], b["width"]
        with torch.no_grad():
            logits_a = render_semantic(m_base, w2c, K, W, H)
            logits_b = render_semantic(m_both, w2c, K, W, H)
        pred_a = logits_a.argmax(dim=-1).cpu().numpy()
        pred_b = logits_b.argmax(dim=-1).cpu().numpy()
        diff_pct = float((pred_a != pred_b).mean())
        # Also: fraction of pixels that changed from Wall(2)→Roof(1)
        wall_to_roof = float(((pred_a == 2) & (pred_b == 1)).mean())
        wall_fraction_a = float((pred_a == 2).mean())
        wall_fraction_b = float((pred_b == 2).mean())
        scores.append((diff_pct, wall_to_roof, wall_fraction_a, wall_fraction_b, idx))

    scores.sort(reverse=True)
    print(f"\nTop {args.top_n} views by overall pixel disagreement (Baseline vs Both):")
    print(f"{'idx':>6} {'diff%':>7} {'W→R%':>7} {'Wall_A':>7} {'Wall_B':>7}")
    for d, w2r, wa, wb, i in scores[:args.top_n]:
        print(f"{i:>6d} {d*100:>6.1f}% {w2r*100:>6.1f}% {wa*100:>6.1f}% {wb*100:>6.1f}%")

    print(f"\nTop {args.top_n} views by Wall→Roof pixel shift (most dramatic Mech1 evidence):")
    scores.sort(key=lambda x: -x[1])
    for d, w2r, wa, wb, i in scores[:args.top_n]:
        print(f"{i:>6d} {d*100:>6.1f}% {w2r*100:>6.1f}% {wa*100:>6.1f}% {wb*100:>6.1f}%")


if __name__ == "__main__":
    main()
