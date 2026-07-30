"""Export primitives as PLY with normal attributes for CloudCompare splat viewing.

Includes:
  - position (x, y, z)
  - normal  (nx, ny, nz)  ← enables CloudCompare "Color by Normal" shader
  - color   (r, g, b)     = normal mapped to RGB ((n+1)/2)
  - group id (gid)        = L_structure grouping assignment

In CloudCompare:
  1. Load PLY → displayed as point cloud with normal-coded colors
  2. Enable "Display > Shading > Phong" or "Color by Normal" to use nx,ny,nz
  3. For disk-like splat rendering: enable "Normal splat" render mode
  4. Sync camera across multiple loaded PLYs via Camera Link (right-click menu)
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import torch


def qn(q):
    q = q / np.maximum(np.linalg.norm(q, axis=1, keepdims=True), 1e-8)
    w, x, y, z = q[:, 0], q[:, 1], q[:, 2], q[:, 3]
    n = np.stack([2*(x*z+w*y), 2*(y*z-w*x), 1-2*(x*x+y*y)], axis=1)
    n /= np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-8)
    return n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ckpt", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--color-mode", default="normal", choices=["normal", "group", "class"])
    ap.add_argument("--voxel-size", type=float, default=0.05)
    ap.add_argument("--n-directions", type=int, default=12)
    ap.add_argument("--min-group-size", type=int, default=5)
    args = ap.parse_args()

    import sys; sys.path.insert(0, ".")

    sd = torch.load(args.ckpt, map_location="cpu", weights_only=False)["state_dict"]
    means = sd["means"].numpy().astype(np.float32)
    quats = sd["quats"].numpy().astype(np.float32)
    sem = sd["sem_logits"].numpy().astype(np.float32)
    log_s = sd["log_scales"].numpy().astype(np.float32)
    normals = qn(quats).astype(np.float32)

    # Compute group ids for group-coloring (and gid attribute)
    from src.stage2.grouping import group_primitives
    scales = np.exp(log_s)
    gids, _, _ = group_primitives(
        centers=torch.from_numpy(means).cuda(),
        normals=torch.from_numpy(normals).cuda(),
        sem_logits=torch.from_numpy(sem).cuda(),
        scales=torch.from_numpy(scales).cuda(),
        voxel_size=args.voxel_size, n_directions=args.n_directions,
        min_group_size=args.min_group_size,
    )
    gids_np = gids.cpu().numpy().astype(np.int32)

    # Choose RGB coloring
    if args.color_mode == "normal":
        # Normal → RGB: ((n+1)/2) in [0,1]
        rgb = ((normals + 1.0) * 0.5 * 255).clip(0, 255).astype(np.uint8)
    elif args.color_mode == "group":
        G = int(gids_np.max() + 1) if (gids_np >= 0).any() else 1
        rng = np.random.RandomState(42)
        palette = rng.randint(30, 240, size=(max(G, 1), 3), dtype=np.uint8)
        rgb = np.where(
            (gids_np >= 0)[:, None],
            palette[np.maximum(gids_np, 0)],
            np.array([120, 120, 120], dtype=np.uint8),
        ).astype(np.uint8)
    elif args.color_mode == "class":
        class_colors = np.array([
            [100, 100, 100],  # BG
            [220, 60, 60],    # Roof
            [60, 80, 200],    # Wall
            [60, 180, 60],    # Terrain
        ], dtype=np.uint8)
        cls = sem.argmax(axis=1)
        rgb = class_colors[cls]

    N = len(means)
    out_path = Path(args.out); out_path.parent.mkdir(parents=True, exist_ok=True)

    # Use Open3D for MeshLab/CloudCompare-compatible PLY output
    import open3d as o3d
    pcd = o3d.geometry.PointCloud()
    pcd.points = o3d.utility.Vector3dVector(means.astype(np.float64))
    pcd.normals = o3d.utility.Vector3dVector(normals.astype(np.float64))
    pcd.colors = o3d.utility.Vector3dVector(rgb.astype(np.float64) / 255.0)
    o3d.io.write_point_cloud(str(out_path), pcd, write_ascii=False)

    print(f"wrote {N} primitives with normals -> {out_path}")
    print(f"  color mode: {args.color_mode}")
    if args.color_mode == "normal":
        print("  Open in CloudCompare → points colored by normal direction ((n+1)/2)")
        print("  Same-colored regions = same normal direction = planar surface")
    print(f"  groups: {int(gids_np.max()+1) if (gids_np >= 0).any() else 0}, "
          f"in-group: {(gids_np >= 0).sum()} ({(gids_np >= 0).mean()*100:.1f}%)")


if __name__ == "__main__":
    main()
