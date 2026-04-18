"""Estimate gravity direction from MatrixCity GT normals over Terrain pixels.

Approach:
  1. Sample N random frames with semantic GT
  2. For pixels labeled Terrain (class 3), collect world-frame GT normals
  3. Average → UP direction
  4. e_gravity = -UP (unit vector)

For synthetic MatrixCity (Z-up), expected: UP ≈ (0, 0, 1) → e_gravity ≈ (0, 0, -1).

Usage:
    python scripts/stage2/estimate_gravity.py --data-root data/matrixcity --out data/matrixcity/gravity.json
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

os.environ.setdefault("OPENCV_IO_ENABLE_OPENEXR", "1")
import cv2
import numpy as np
from PIL import Image
from tqdm import tqdm


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-root", default="data/matrixcity")
    ap.add_argument("--out", default="data/matrixcity/gravity.json")
    ap.add_argument("--n-frames", type=int, default=100)
    ap.add_argument("--max-pixels-per-frame", type=int, default=50_000)
    args = ap.parse_args()

    root = Path(args.data_root)
    sem_dir = root / "semantic"
    nrm_dir = root / "normal"

    sem_files = sorted(sem_dir.glob("*.png"))
    if not sem_files:
        raise FileNotFoundError(f"no semantic PNGs in {sem_dir}")
    stride = max(1, len(sem_files) // args.n_frames)
    frames = sem_files[::stride][:args.n_frames]
    print(f"[gravity] scanning {len(frames)} frames")

    acc = np.zeros(3, dtype=np.float64)
    total_terrain_px = 0
    per_frame_mean = []

    for sp in tqdm(frames, desc="scan"):
        stem = sp.stem
        np_path = nrm_dir / f"{stem}.exr"
        if not np_path.exists():
            continue

        sem = np.asarray(Image.open(sp))  # (H, W) uint8
        raw = cv2.imread(str(np_path), cv2.IMREAD_UNCHANGED)
        n_rgb = raw[..., :3][..., ::-1].astype(np.float32)
        n_world = n_rgb * 2.0 - 1.0

        mask = sem == 3  # Terrain
        if mask.sum() == 0:
            continue

        pts = n_world[mask]
        mag = np.linalg.norm(pts, axis=1)
        pts = pts[mag > 0.5]
        if len(pts) == 0:
            continue
        pts = pts / np.linalg.norm(pts, axis=1, keepdims=True)
        if len(pts) > args.max_pixels_per_frame:
            idx = np.random.choice(len(pts), args.max_pixels_per_frame, replace=False)
            pts = pts[idx]

        acc += pts.sum(axis=0)
        total_terrain_px += len(pts)
        per_frame_mean.append(pts.mean(axis=0))

    if total_terrain_px == 0:
        raise RuntimeError("No terrain pixels found")

    UP = acc / total_terrain_px
    UP_norm = UP / np.linalg.norm(UP)
    e_g = -UP_norm

    # Stats
    pfm = np.asarray(per_frame_mean)
    pfm_norm = pfm / np.maximum(np.linalg.norm(pfm, axis=1, keepdims=True), 1e-8)
    consistency = float(np.dot(pfm_norm, UP_norm).mean())

    print()
    print(f"total Terrain normal samples: {total_terrain_px:,}")
    print(f"UP (mean Terrain normal):     ({UP_norm[0]:+.4f}, {UP_norm[1]:+.4f}, {UP_norm[2]:+.4f})")
    print(f"e_gravity = -UP:              ({e_g[0]:+.4f}, {e_g[1]:+.4f}, {e_g[2]:+.4f})")
    print(f"per-frame consistency (cos):  {consistency:.4f}  (1.0 = perfectly aligned)")

    out = {
        "up": UP_norm.tolist(),
        "e_gravity": e_g.tolist(),
        "n_samples": int(total_terrain_px),
        "n_frames": len(frames),
        "per_frame_consistency": consistency,
    }
    Path(args.out).write_text(json.dumps(out, indent=2))
    print(f"\nwrote {args.out}")


if __name__ == "__main__":
    main()
