"""Mechanism evidence rendered as proper 2DGS splats via gsplat.

Unlike render_mechanism_evidence.py (custom ortho point splats), this uses
gsplat.rasterization_2dgs with per-primitive feature colors = heatmap of our
scalar of interest. Produces proper oriented planar disk rendering with
perspective projection, alpha compositing, and correct occlusion.

Modes:
  vert_wall    — Wall-class verticality (|n·g| → green=0, red=1)
  horiz_roof   — Roof-class horizontality (1−|n·g| → green=0, red=1)
  horiz_terrain — Terrain-class horizontality
  group_dev    — Angular deviation from group representative normal
  coplanar_dev — Distance to group representative plane

Each rendered from a specified dataset view (by index).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import imageio.v2 as imageio
import numpy as np
import torch
import yaml

sys.path.insert(0, ".")
from src.stage2.dataloader import ColmapDataset
from src.stage2.model import GaussianModel2D
from gsplat import rasterization_2dgs


def qn(q):
    q = q / np.maximum(np.linalg.norm(q, axis=1, keepdims=True), 1e-8)
    w, x, y, z = q[:, 0], q[:, 1], q[:, 2], q[:, 3]
    n = np.stack([2*(x*z+w*y), 2*(y*z-w*x), 1-2*(x*x+y*y)], axis=1)
    n /= np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-8)
    return n


def heatmap_gyr(v, v0, v1):
    """Green (good) → Yellow → Red (bad)."""
    t = np.clip((v - v0) / (v1 - v0), 0, 1)
    r = np.where(t < 0.5, 2 * t, 1.0)
    g = np.where(t < 0.5, 1.0, 2 * (1 - t))
    b = np.zeros_like(t)
    return np.stack([r, g, b], axis=-1).astype(np.float32)


def compute_groups(ckpt_path, voxel=0.05, n_dir=12, min_gr=5):
    from src.stage2.grouping import group_primitives
    sd = torch.load(ckpt_path, map_location="cpu", weights_only=False)["state_dict"]
    means = sd["means"].numpy().astype(np.float32)
    quats = sd["quats"].numpy().astype(np.float32)
    log_s = sd["log_scales"].numpy().astype(np.float32)
    sem = sd["sem_logits"].numpy().astype(np.float32)
    n = qn(quats)
    scales = np.exp(log_s)
    gids, rep_n, rep_d = group_primitives(
        centers=torch.from_numpy(means).cuda(),
        normals=torch.from_numpy(n).cuda(),
        sem_logits=torch.from_numpy(sem).cuda(),
        scales=torch.from_numpy(scales).cuda(),
        voxel_size=voxel, n_directions=n_dir, min_group_size=min_gr,
    )
    gids = gids.cpu().numpy()
    rep_n_np = rep_n.cpu().numpy()
    rep_d_np = rep_d.cpu().numpy()
    ang_dev = np.full(len(means), np.nan, dtype=np.float32)
    copl_d = np.full(len(means), np.nan, dtype=np.float32)
    valid = gids >= 0
    gi = gids[valid]
    ni = n[valid]
    rn = rep_n_np[gi]; rd = rep_d_np[gi]
    cos_a = np.clip(np.abs((ni * rn).sum(axis=1)), 0, 1)
    ang_dev[valid] = np.degrees(np.arccos(cos_a))
    copl_d[valid] = np.abs((means[valid] * rn).sum(axis=1) + rd)
    return means, n, sem, scales, quats, gids, ang_dev, copl_d


def render_feature(model, colors_custom, mask, w2c, K, W, H, device,
                   gray_nontarget=True, nontarget_rgb=(0.72, 0.72, 0.72)):
    """Render ALL primitives with custom RGB. Target (mask=True) gets
    colors_custom; non-target gets muted gray (so scene context is preserved).
    """
    means = model.means.detach().contiguous()
    quats = model.quats.detach().contiguous()
    scales = model.scales.detach().contiguous()
    opacities = model.opacities.detach().contiguous()
    N = means.shape[0]
    colors_full = torch.from_numpy(colors_custom).to(device).contiguous()
    if gray_nontarget:
        gray = torch.tensor(nontarget_rgb, device=device).expand(N, 3).contiguous()
        mask_dev = mask.to(device).view(-1, 1).float()
        colors_full = colors_full * mask_dev + gray * (1 - mask_dev)
    viewmats = w2c.unsqueeze(0).to(device)
    Ks = K.unsqueeze(0).to(device)
    out = rasterization_2dgs(
        means=means, quats=quats, scales=scales, opacities=opacities,
        colors=colors_full,
        viewmats=viewmats, Ks=Ks,
        width=W, height=H,
        render_mode="RGB",
        sh_degree=None,
        backgrounds=torch.ones(1, 3, device=device),
    )
    rgb = out[0][0]
    return rgb.detach().clamp(0, 1).cpu().numpy()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ckpt", required=True)
    ap.add_argument("--label", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--config", default="configs/input_and_alignment/matrixcity_step1_6.yaml")
    ap.add_argument("--views", nargs="+", type=int, default=[5368, 5083, 5528, 5328])
    ap.add_argument("--modes", nargs="+", default=["vert_wall", "horiz_terrain", "horiz_roof", "group_dev", "coplanar_dev"])
    args = ap.parse_args()

    out = Path(args.out_dir); out.mkdir(parents=True, exist_ok=True)
    cfg = yaml.safe_load(open(args.config))
    device = "cuda"
    ds = ColmapDataset(cfg["data_root"], downscale=cfg.get("downscale", 1.0),
                       load_depth=False, load_normal=False)

    # Load gravity
    g = np.array(json.load(open("data/matrixcity/gravity.json"))["e_gravity"])
    g /= np.linalg.norm(g)

    # Compute groups and per-primitive scalars
    print(f"[{args.label}] grouping...")
    means_np, n_np, sem_np, scales_np, quats_np, gids, ang_dev, copl_d = compute_groups(args.ckpt)
    sem_cls = sem_np.argmax(axis=1)
    ndg = np.abs((n_np * g).sum(axis=1))

    # Load model via standard loader
    m = GaussianModel2D(ds.points_xyz, ds.points_rgb,
                        sh_degree=cfg.get("sh_degree", 3), device=device).to(device)
    sd = torch.load(args.ckpt, map_location=device, weights_only=False)["state_dict"]
    for name, p in list(m.named_parameters()):
        t = sd.get(name)
        if t is None: continue
        if p.shape != t.shape:
            parts = name.split("."); obj = m
            for pp in parts[:-1]: obj = getattr(obj, pp)
            setattr(obj, parts[-1], torch.nn.Parameter(t.clone()))
        else:
            p.data.copy_(t)

    # Mode specs: (class_filter, scalar, v0, v1)
    mode_specs = {
        "vert_wall":     (sem_cls == 2, ndg,          0.0, 0.8),
        "horiz_terrain": (sem_cls == 3, 1.0 - ndg,    0.0, 0.8),
        "horiz_roof":   (sem_cls == 1, 1.0 - ndg,     0.0, 0.8),
        "group_dev":     (gids >= 0,   ang_dev,       0.0, 30.0),
        "coplanar_dev":  (gids >= 0,   copl_d,        0.0, 0.08),
    }

    for mode in args.modes:
        cls_mask_np, scalar, v0, v1 = mode_specs[mode]
        cls_mask = torch.from_numpy(cls_mask_np).to(device)
        colors = heatmap_gyr(scalar, v0, v1)  # (N, 3) float32
        # Replace NaNs (for ungrouped primitives) with gray
        if np.isnan(scalar).any():
            nan_mask = np.isnan(scalar)
            colors[nan_mask] = np.array([0.7, 0.7, 0.7], dtype=np.float32)

        for idx in args.views:
            b = ds[idx]
            w2c = b["w2c"]
            K = b["K"]
            H, W = b["height"], b["width"]
            rgb = render_feature(m, colors, cls_mask, w2c, K, W, H, device)
            img = (rgb * 255).astype(np.uint8)
            fname = f"{args.label}_v{idx:04d}_{mode}.png"
            imageio.imwrite(out / fname, img)
            # log fraction green (within threshold)
            active_scalar = scalar[cls_mask_np]
            frac_green = float((active_scalar < v0 + 0.25 * (v1 - v0)).mean()) if len(active_scalar) else 0
            print(f"  wrote {fname}  N={int(cls_mask_np.sum())}  frac_green={frac_green*100:.1f}%")


if __name__ == "__main__":
    main()
