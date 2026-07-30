"""Visualize mechanism-intended effects directly.

For L_mutual:
  - vert-heat: Wall-class only, color = verticality (|n·g|→RGB green=vertical, red=tilted)
  - horiz-heat: Terrain/Roof-class, color = horizontality (|n·g|→RGB)

For L_structure:
  - group-dev: Colored by angle to own group's representative normal (green=aligned, red=deviated)
  - coplanar-dev: Colored by distance to own group's plane (green=on plane, red=off)

All use the same orthographic rasterizer from render_3d_views.py.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import torch

sys.path.insert(0, ".")
from scripts.input_and_alignment.render_3d_views import (
    qn, make_camera, render, save_png,
)


def load_gravity():
    g = np.array(json.load(open("data/matrixcity/gravity.json"))["e_gravity"])
    return g / np.linalg.norm(g)


def heatmap_color(v, v0, v1, cmap="GnYlRd"):
    """Map scalar v∈[v0,v1] to RGB. Green→Yellow→Red; values outside range clipped."""
    t = np.clip((v - v0) / (v1 - v0), 0, 1)
    # simple GYR: 0=green, 0.5=yellow, 1=red
    r = np.where(t < 0.5, 2 * t, 1.0)
    g = np.where(t < 0.5, 1.0, 2 * (1 - t))
    b = np.zeros_like(t)
    return np.stack([r, g, b], axis=-1).astype(np.float32)


def load_ckpt(path):
    sd = torch.load(path, map_location="cpu", weights_only=False)["state_dict"]
    return {
        "means": sd["means"].numpy().astype(np.float32),
        "quats": sd["quats"].numpy().astype(np.float32),
        "log_scales": sd["log_scales"].numpy().astype(np.float32),
        "sem_logits": sd["sem_logits"].numpy().astype(np.float32),
        "opacities": torch.sigmoid(sd["opacities_raw"]).numpy().astype(np.float32),
    }


def compute_groups_and_dev(ckpt_path, voxel=0.05, n_dir=12, min_gr=5):
    """Compute per-primitive: group_id, angle_deviation_deg, coplanar_distance."""
    from src.stage2.grouping import group_primitives
    d = load_ckpt(ckpt_path)
    means = d["means"]; quats = d["quats"]; log_s = d["log_scales"]; sem = d["sem_logits"]
    n = qn(quats)
    n /= np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-8)
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
    N = len(means)
    angle_dev = np.full(N, np.nan, dtype=np.float32)
    coplanar_d = np.full(N, np.nan, dtype=np.float32)
    valid = gids >= 0
    idx_valid = np.where(valid)[0]
    # vectorize
    gi = gids[valid]
    ni = n[valid]
    rn = rep_n_np[gi]
    rd = rep_d_np[gi]
    cos_a = np.clip(np.abs((ni * rn).sum(axis=1)), 0, 1)
    angle_dev[valid] = np.degrees(np.arccos(cos_a))
    coplanar_d[valid] = np.abs((means[valid] * rn).sum(axis=1) + rd)
    return d, n, gids, angle_dev, coplanar_d


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ckpt", required=True)
    ap.add_argument("--label", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--bbox", nargs=6, type=float, required=True)
    ap.add_argument("--views", nargs="+", default=["oblique", "front"])
    ap.add_argument("--modes", nargs="+", default=[
        "vert_wall", "horiz_terrain", "horiz_roof", "group_dev", "coplanar_dev"
    ])
    ap.add_argument("--width", type=int, default=1200)
    ap.add_argument("--height", type=int, default=900)
    ap.add_argument("--point-size", type=float, default=4.0)
    args = ap.parse_args()

    out = Path(args.out_dir); out.mkdir(parents=True, exist_ok=True)
    lo = np.array(args.bbox[:3]); hi = np.array(args.bbox[3:])

    print(f"[{args.label}] loading + grouping...")
    d, n, gids, ang_dev, copl_d = compute_groups_and_dev(args.ckpt)
    g = load_gravity()
    sem_cls = d["sem_logits"].argmax(axis=1)
    means = d["means"]; op = d["opacities"]

    in_bb = np.all((means >= lo) & (means <= hi), axis=1)
    print(f"  total={len(means)}, in_bbox={in_bb.sum()}")

    # Normal-to-gravity alignment |n·g|
    ndg = np.abs((n * g).sum(axis=1))

    mode_specs = {
        # Green=vertical wall (|n·g|≈0), Red=tilted (|n·g|≈1). Only Wall-class shown.
        "vert_wall": ("Wall-class verticality", sem_cls == 2, ndg, 0.0, 0.8),
        # Green=horizontal terrain (|n·g|≈1), Red=tilted (≈0). Only Terrain-class shown.
        "horiz_terrain": ("Terrain-class horizontality", sem_cls == 3, 1.0 - ndg, 0.0, 0.8),
        # Green=horizontal roof, Red=tilted. Only Roof-class shown.
        "horiz_roof": ("Roof-class horizontality", sem_cls == 1, 1.0 - ndg, 0.0, 0.8),
        # Green=aligned with group normal (0°), Red=deviated (30°+)
        "group_dev": ("Group normal deviation", gids >= 0, ang_dev, 0.0, 30.0),
        # Green=on group plane, Red=off
        "coplanar_dev": ("Coplanar deviation", gids >= 0, copl_d, 0.0, 0.08),
    }

    for view in args.views:
        R, t, hw, hh, _ = make_camera(lo, hi, view)
        for mode in args.modes:
            if mode not in mode_specs: continue
            title, mask, val, v0, v1 = mode_specs[mode]
            # Combine: in_bbox AND the mode's class mask
            active = in_bb & mask
            if active.sum() < 10:
                print(f"  [{mode}] only {active.sum()} primitives — skip")
                continue
            pts = means[active]
            nor = n[active]
            opa = op[active]
            colors = heatmap_color(val[active], v0, v1)
            img = render(pts, nor, colors, opa, R, t, hw, hh,
                         W=args.width, H=args.height, point_size=args.point_size)
            fname = f"{args.label}_{view}_{mode}.png"
            save_png(img, out / fname)
            frac_low = float((val[active] < v0 + 0.25 * (v1 - v0)).mean())
            print(f"  wrote {fname}  (N={active.sum()}, frac_green={frac_low*100:.1f}%)")


if __name__ == "__main__":
    main()
