"""Export 2DGS primitives as a PLY point cloud (centers + normals + colors).

Usage (inside container):
    python scripts/input_and_alignment/export_ply.py --ckpt results/phase1_vanilla/run/ckpt/final.pt \
        --out results/phase1_vanilla/run/primitives.ply
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import torch

from src.stage2.model import GaussianModel2D, quat_to_rotmat


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ckpt", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    sd = torch.load(args.ckpt, map_location="cpu")["state_dict"]
    means = sd["means"].cpu().numpy()
    quats = sd["quats"].cpu().numpy()
    sh0 = sd["sh0"].cpu().numpy()  # (N,1,3)
    R = quat_to_rotmat(torch.from_numpy(quats)).numpy()
    normals = R[..., 2]

    C0 = 0.28209479177387814
    rgb = np.clip(sh0[:, 0, :] * C0 + 0.5, 0, 1) * 255
    rgb = rgb.astype(np.uint8)

    N = means.shape[0]
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "wb") as f:
        f.write(b"ply\nformat binary_little_endian 1.0\n")
        f.write(f"element vertex {N}\n".encode())
        f.write(b"property float x\nproperty float y\nproperty float z\n")
        f.write(b"property float nx\nproperty float ny\nproperty float nz\n")
        f.write(b"property uchar red\nproperty uchar green\nproperty uchar blue\n")
        f.write(b"end_header\n")
        data = np.empty(N, dtype=[
            ("x", "<f4"), ("y", "<f4"), ("z", "<f4"),
            ("nx", "<f4"), ("ny", "<f4"), ("nz", "<f4"),
            ("r", "u1"), ("g", "u1"), ("b", "u1"),
        ])
        data["x"], data["y"], data["z"] = means[:, 0], means[:, 1], means[:, 2]
        data["nx"], data["ny"], data["nz"] = normals[:, 0], normals[:, 1], normals[:, 2]
        data["r"], data["g"], data["b"] = rgb[:, 0], rgb[:, 1], rgb[:, 2]
        data.tofile(f)
    print(f"wrote {N} primitives -> {out}")


if __name__ == "__main__":
    main()
