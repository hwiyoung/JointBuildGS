"""Export primitives as PLY with random group colors.

Uses the same grouping as training-time L_structure.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import torch


def qn(q):
    q = q / np.maximum(np.linalg.norm(q, axis=1, keepdims=True), 1e-8)
    w, x, y, z = q[:, 0], q[:, 1], q[:, 2], q[:, 3]
    return np.stack([2*(x*z+w*y), 2*(y*z-w*x), 1-2*(x*x+y*y)], axis=1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ckpt", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--voxel-size", type=float, default=0.05)
    ap.add_argument("--n-directions", type=int, default=12)
    ap.add_argument("--min-group-size", type=int, default=5)
    args = ap.parse_args()

    import sys; sys.path.insert(0, ".")
    from src.stage2.grouping import group_primitives

    sd = torch.load(args.ckpt, map_location="cpu", weights_only=False)["state_dict"]
    means = sd["means"].cuda()
    quats = sd["quats"].cuda()
    log_scales = sd["log_scales"].cuda()
    sem_logits = sd["sem_logits"].cuda()
    normals = torch.from_numpy(qn(quats.cpu().numpy())).cuda()
    normals = torch.nn.functional.normalize(normals, dim=-1)
    scales = torch.exp(log_scales)

    gids, rep_n, rep_d = group_primitives(
        centers=means, normals=normals, sem_logits=sem_logits, scales=scales,
        voxel_size=args.voxel_size, n_directions=args.n_directions,
        min_group_size=args.min_group_size,
    )
    gids = gids.cpu().numpy()
    means_np = means.cpu().numpy()

    # random color per group; -1 → gray
    G = gids.max() + 1 if (gids >= 0).any() else 0
    rng = np.random.RandomState(42)
    palette = rng.randint(30, 240, size=(max(G, 1), 3), dtype=np.uint8)
    rgb = np.where(
        (gids >= 0)[:, None],
        palette[np.maximum(gids, 0)],
        np.array([120, 120, 120], dtype=np.uint8),
    ).astype(np.uint8)

    N = len(means_np)
    out = Path(args.out); out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "wb") as f:
        f.write(b"ply\nformat binary_little_endian 1.0\n")
        f.write(f"element vertex {N}\n".encode())
        f.write(b"property float x\nproperty float y\nproperty float z\n")
        f.write(b"property uchar red\nproperty uchar green\nproperty uchar blue\n")
        f.write(b"property int group_id\n")
        f.write(b"end_header\n")
        data = np.empty(N, dtype=[
            ("x","<f4"),("y","<f4"),("z","<f4"),
            ("r","u1"),("g","u1"),("b","u1"),
            ("gid","<i4"),
        ])
        data["x"], data["y"], data["z"] = means_np[:,0], means_np[:,1], means_np[:,2]
        data["r"], data["g"], data["b"] = rgb[:,0], rgb[:,1], rgb[:,2]
        data["gid"] = gids
        data.tofile(f)

    print(f"wrote {N} primitives -> {out}")
    print(f"  groups: {G}, in-group: {(gids>=0).sum()} ({(gids>=0).mean()*100:.1f}%)")


if __name__ == "__main__":
    main()
