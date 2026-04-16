"""Coverage heatmap and px/primitive metric.

Coverage(view) = fraction of pixels with alpha > threshold.
px/prim = rendered pixels covered / num primitives.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import imageio.v2 as imageio
import matplotlib.cm as cm
import numpy as np
import torch
import yaml

from src.stage2.dataloader import SeongsuDataset
from src.stage2.model import GaussianModel2D
from src.stage2.renderer import render


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ckpt", required=True)
    ap.add_argument("--config", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--alpha-th", type=float, default=0.5)
    args = ap.parse_args()

    with open(args.config) as f:
        cfg = yaml.safe_load(f)
    device = "cuda"
    ds = SeongsuDataset(root=cfg["data_root"], downscale=cfg.get("downscale", 0.5))
    model = GaussianModel2D(points_xyz=ds.points_xyz, points_rgb=ds.points_rgb,
                            sh_degree=cfg.get("sh_degree", 3), device=device).to(device)
    sd = torch.load(args.ckpt, map_location=device)["state_dict"]
    for name, p in list(model.named_parameters()):
        t = sd.get(name)
        if t is None: continue
        if p.shape != t.shape:
            parts = name.split(".")
            obj = model
            for pp in parts[:-1]:
                obj = getattr(obj, pp)
            setattr(obj, parts[-1], torch.nn.Parameter(t.clone()))
        else:
            p.data.copy_(t)

    out_dir = Path(args.out); out_dir.mkdir(parents=True, exist_ok=True)
    covs = []
    acc = None
    count = 0
    for idx in range(len(ds)):
        b = ds[idx]
        with torch.no_grad():
            o = render(model, b["w2c"].to(device), b["K"].to(device), b["width"], b["height"], render_mode="RGB+ED")
        a = o["alpha"].cpu().numpy()
        covs.append(float((a > args.alpha_th).mean()))
        if acc is None:
            acc = a.copy()
        else:
            acc += a
        count += 1
        if idx < 4:
            imageio.imwrite(out_dir / f"alpha_v{idx:02d}.png", (np.clip(a, 0, 1) * 255).astype(np.uint8))
    avg = acc / max(count, 1)
    avg_norm = np.clip(avg / max(avg.max(), 1e-6), 0, 1)
    imageio.imwrite(out_dir / "coverage_mean.png", (cm.turbo(avg_norm)[..., :3] * 255).astype(np.uint8))

    covered_px = float((avg > args.alpha_th).sum())
    px_per_prim = covered_px / max(model.num_points, 1)
    summary = {
        "coverage_mean": float(np.mean(covs)),
        "coverage_std": float(np.std(covs)),
        "n_prim": int(model.num_points),
        "px_per_prim_on_mean_alpha": px_per_prim,
        "n_views": count,
    }
    (out_dir / "summary.txt").write_text("\n".join(f"{k}: {v}" for k, v in summary.items()))
    print(summary)


if __name__ == "__main__":
    main()
