"""Export primitives as PLY with class colors (argmax(f_i))."""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import torch


COLORS = np.array([
    [0, 0, 0],         # BG
    [220, 60, 60],     # Roof
    [60, 180, 60],     # Wall
    [60, 80, 200],     # Terrain
], dtype=np.uint8)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ckpt", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    sd = torch.load(args.ckpt, map_location="cpu", weights_only=False)["state_dict"]
    means = sd["means"].cpu().numpy()
    sem_logits = sd["sem_logits"].cpu().numpy()
    classes = sem_logits.argmax(axis=1)
    rgb = COLORS[classes]

    N = means.shape[0]
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "wb") as f:
        f.write(b"ply\nformat binary_little_endian 1.0\n")
        f.write(f"element vertex {N}\n".encode())
        f.write(b"property float x\nproperty float y\nproperty float z\n")
        f.write(b"property uchar red\nproperty uchar green\nproperty uchar blue\n")
        f.write(b"property int class\n")
        f.write(b"end_header\n")
        data = np.empty(N, dtype=[
            ("x", "<f4"), ("y", "<f4"), ("z", "<f4"),
            ("r", "u1"), ("g", "u1"), ("b", "u1"),
            ("c", "<i4"),
        ])
        data["x"], data["y"], data["z"] = means[:, 0], means[:, 1], means[:, 2]
        data["r"], data["g"], data["b"] = rgb[:, 0], rgb[:, 1], rgb[:, 2]
        data["c"] = classes
        data.tofile(f)
    print(f"wrote {N} primitives -> {out}")
    # Class distribution
    unique, counts = np.unique(classes, return_counts=True)
    names = ["BG", "Roof", "Wall", "Terrain"]
    for u, c in zip(unique, counts):
        print(f"  {names[u]}: {c} ({c/N*100:.1f}%)")


if __name__ == "__main__":
    main()
