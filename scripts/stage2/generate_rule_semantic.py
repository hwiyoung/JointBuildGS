"""Generate rule-based semantic GT for MatrixCity from GT depth + GT normal + camera pose.

Classes (K=4):
  0 BG       — depth beyond far sentinel (sky)
  1 Roof     — horizontal surface at high world z (|n_z| > H_TH, z > HEIGHT_TH)
  2 Wall     — near-vertical surface (|n_z| < V_TH)
  3 Terrain  — horizontal surface at low world z (|n_z| > H_TH, z <= HEIGHT_TH)

Ambiguous (V_TH <= |n_z| <= H_TH, slanted) → assigned BG (ignore in L_sem).

Output: PNG files (uint8, values 0..3) in data/matrixcity/semantic/{frame_idx:04d}.png

Usage (inside container):
    python scripts/stage2/generate_rule_semantic.py \
        --data-root data/matrixcity \
        --out-dir data/matrixcity/semantic
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path

os.environ.setdefault("OPENCV_IO_ENABLE_OPENEXR", "1")
import cv2
import numpy as np
from PIL import Image
from tqdm import tqdm

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.stage2.colmap_io import read_cameras_bin, read_images_bin  # noqa: E402


H_TH = 0.7         # |n_z| >= H_TH → horizontal (roof or terrain)
V_TH = 0.3         # |n_z| <= V_TH → vertical (wall)
FAR_SENTINEL = 28000.0  # EXR depth values >= this → sky/BG
DEPTH_SCALE = 1.0 / 10590  # UE cm → COLMAP world unit (from Step 1-2)


def classify_frame(
    depth_raw: np.ndarray,      # (H,W) float32, EXR raw (UE cm)
    normal_world: np.ndarray,   # (H,W,3) float32 unit vectors
    c2w: np.ndarray,            # (4,4)
    K: np.ndarray,              # (3,3)
    height_th: float,           # world_z threshold for Roof vs Terrain (COLMAP unit)
) -> np.ndarray:
    H, W = depth_raw.shape
    label = np.zeros((H, W), dtype=np.uint8)

    valid = (depth_raw > 0) & (depth_raw < FAR_SENTINEL)
    label[~valid] = 0  # BG

    if not valid.any():
        return label

    # Scale depth to COLMAP unit
    depth = depth_raw * DEPTH_SCALE

    # Classify by normal
    n_z_abs = np.abs(normal_world[..., 2])
    is_horizontal = n_z_abs >= H_TH
    is_vertical = n_z_abs <= V_TH
    # Slanted (between) → keep as BG (ignore in loss)

    # Compute world z for horizontal pixels (unproject center of each pixel)
    # camera-frame point: [(u-cx)/fx * d, (v-cy)/fy * d, d]
    # world point: c2w @ [..., 1]
    # We only need the world z component.
    u = np.arange(W, dtype=np.float32)[None, :].repeat(H, axis=0)
    v = np.arange(H, dtype=np.float32)[:, None].repeat(W, axis=1)
    fx, fy = K[0, 0], K[1, 1]
    cx, cy = K[0, 2], K[1, 2]
    x_cam = (u - cx) / fx * depth
    y_cam = (v - cy) / fy * depth
    z_cam = depth
    # c2w: 4x4. World z = c2w[2,0]*x + c2w[2,1]*y + c2w[2,2]*z + c2w[2,3]
    wz = c2w[2, 0] * x_cam + c2w[2, 1] * y_cam + c2w[2, 2] * z_cam + c2w[2, 3]

    is_roof = valid & is_horizontal & (wz >= height_th)
    is_terrain = valid & is_horizontal & (wz < height_th)
    is_wall = valid & is_vertical

    label[is_roof] = 1
    label[is_wall] = 2
    label[is_terrain] = 3
    # Slanted horizontal surfaces (between thresholds) remain BG (ignored)
    return label


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-root", default="data/matrixcity")
    ap.add_argument("--out-dir", default="data/matrixcity/semantic")
    ap.add_argument("--height-th", type=float, default=0.02,
                    help="world z threshold (COLMAP unit) for Roof vs Terrain; ~2m real at scale 107m/unit")
    ap.add_argument("--limit", type=int, default=None, help="limit for quick test")
    args = ap.parse_args()

    root = Path(args.data_root)
    out_dir = Path(args.out_dir); out_dir.mkdir(parents=True, exist_ok=True)

    # Load camera poses from sparse
    sparse_dir = root / "sparse" / "0"
    cameras = read_cameras_bin(sparse_dir / "cameras.bin")
    images = read_images_bin(sparse_dir / "images.bin")
    print(f"[data] {len(images)} frames, {len(cameras)} camera(s)")

    # Assume single camera
    cam = next(iter(cameras.values()))
    K = cam.K()

    frames = sorted(images.values(), key=lambda im: im.name)
    if args.limit:
        frames = frames[:args.limit]

    # Stats
    class_counts = np.zeros(4, dtype=np.int64)

    for img in tqdm(frames, desc="semantic"):
        stem = Path(img.name).stem  # e.g., 0042
        depth_path = root / "depth" / f"{stem}.exr"
        normal_path = root / "normal" / f"{stem}.exr"
        if not depth_path.exists() or not normal_path.exists():
            continue

        # Depth
        d_raw = cv2.imread(str(depth_path), cv2.IMREAD_UNCHANGED)
        d = d_raw[..., 0] if d_raw.ndim == 3 else d_raw

        # Normal (world frame, BGR→RGB, (n+1)/2 decode)
        n_raw = cv2.imread(str(normal_path), cv2.IMREAD_UNCHANGED)
        n_rgb = n_raw[..., :3][..., ::-1].astype(np.float32)
        n_world = n_rgb * 2.0 - 1.0
        mag = np.linalg.norm(n_world, axis=-1, keepdims=True)
        n_world = np.where(mag > 1e-6, n_world / np.maximum(mag, 1e-6), 0.0)

        # camera pose
        w2c = np.eye(4, dtype=np.float64)
        w2c[:3, :3] = img.R()
        w2c[:3, 3] = img.tvec
        c2w = np.linalg.inv(w2c)

        label = classify_frame(d.astype(np.float32), n_world.astype(np.float32), c2w, K, args.height_th)

        # stats
        for c in range(4):
            class_counts[c] += int((label == c).sum())

        Image.fromarray(label).save(out_dir / f"{stem}.png", compress_level=3)

    total = class_counts.sum()
    print(f"\n=== class distribution ===")
    for c, name in enumerate(["BG", "Roof", "Wall", "Terrain"]):
        pct = class_counts[c] / max(total, 1) * 100
        print(f"  {name:>8s}: {class_counts[c]:>12d} ({pct:5.1f}%)")


if __name__ == "__main__":
    main()
