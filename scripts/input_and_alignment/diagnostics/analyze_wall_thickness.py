"""Quantify 'wall thickness' by fitting a plane to primitives in a Y-slab and
measuring primitive-to-plane distance per condition.

Purpose: give a concrete number behind "Structure/Both makes walls thinner".
For each condition:
  - take Wall-class primitives in the slab
  - fit a least-squares plane (SVD) constrained to vertical orientation
  - report mean/median/std of |n·(p - c)| (signed distance to plane)
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import torch


CONDS = [
    ("Baseline", "results/phase1_semantic/run/ckpt/final.pt"),
    ("Mutual",   "results/phase1_mutual/run/ckpt/final.pt"),
    ("Structure","results/phase1_structure/run/ckpt/final.pt"),
    ("Both",     "results/phase1_ablation/run/ckpt/final.pt"),
]


def fit_vertical_plane(pts):
    """Fit a vertical plane (normal lies in XY) to 3D points.
    Returns: (normal (3,), centroid (3,)).
    """
    if len(pts) < 10:
        return None, None
    # project to XY (z ignored for plane fit since normal is vertical)
    xy = pts[:, :2]
    c_xy = xy.mean(axis=0)
    xy_centered = xy - c_xy
    # 2D PCA: smallest eigenvector = normal direction (in XY)
    cov = xy_centered.T @ xy_centered / len(xy_centered)
    eigvals, eigvecs = np.linalg.eigh(cov)
    # smallest eigenvector
    n_xy = eigvecs[:, 0]  # (2,)
    # form 3D normal (z=0 = horizontal normal = vertical wall)
    n = np.array([n_xy[0], n_xy[1], 0.0])
    n /= np.linalg.norm(n)
    c = np.array([c_xy[0], c_xy[1], pts[:, 2].mean()])
    return n, c


def qn_to_n(q):
    q = q / np.maximum(np.linalg.norm(q, axis=1, keepdims=True), 1e-8)
    w, x, y, z = q[:, 0], q[:, 1], q[:, 2], q[:, 3]
    n = np.stack([2*(x*z+w*y), 2*(y*z-w*x), 1-2*(x*x+y*y)], axis=1)
    n /= np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-8)
    return n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--y-slab", nargs=2, type=float, default=[2.5, 2.7], help="y range of slab")
    ap.add_argument("--x-range", nargs=2, type=float, default=[1.25, 5.25])
    ap.add_argument("--z-range", nargs=2, type=float, default=[0.0, 3.0])
    ap.add_argument("--out", default="results/phase1_ablation/figures/wall_thickness.json")
    args = ap.parse_args()

    y_lo, y_hi = args.y_slab
    x_lo, x_hi = args.x_range
    z_lo, z_hi = args.z_range

    results = {
        "slab": {"y": args.y_slab, "x": args.x_range, "z": args.z_range},
        "conditions": {},
    }

    print(f"{'cond':<10} {'n_wall':>7} {'pos_med[mm]':>11} {'pos_p90[mm]':>11} "
          f"{'n_std[°]':>8} {'n_p90[°]':>8} {'n·plane':>8}")
    for label, ckpt in CONDS:
        sd = torch.load(ckpt, map_location="cpu", weights_only=False)["state_dict"]
        m = sd["means"].numpy().astype(np.float64)
        q = sd["quats"].numpy().astype(np.float64)
        sem = sd["sem_logits"].numpy().argmax(axis=1)
        n_all = qn_to_n(q)

        in_slab = (
            (m[:, 1] >= y_lo) & (m[:, 1] <= y_hi) &
            (m[:, 0] >= x_lo) & (m[:, 0] <= x_hi) &
            (m[:, 2] >= z_lo) & (m[:, 2] <= z_hi)
        )
        wall_mask = sem == 2  # Wall class
        wall_idx = in_slab & wall_mask
        wall_pts = m[wall_idx]
        wall_n = n_all[wall_idx]

        plane_n, plane_c = fit_vertical_plane(wall_pts)
        if plane_n is None:
            results["conditions"][label] = {"error": "too few Wall primitives in slab"}
            continue

        # Position thickness: |p - c| · plane_n
        pos_d = np.abs((wall_pts - plane_c) @ plane_n)
        # Normal alignment: angle between each primitive's normal and the plane normal
        cos_a = np.abs((wall_n * plane_n).sum(axis=1))
        cos_a = np.clip(cos_a, -1, 1)
        angle_deg = np.degrees(np.arccos(cos_a))
        # Normal consistency: std of angles from mean direction (smaller = tighter wall)
        # Use circular-ish: angle to the robust mean normal direction
        # Robust mean: median quaternion-based → here use projection along plane_n
        n_sig = float(angle_deg.std())
        n_p90 = float(np.percentile(angle_deg, 90))
        n_dot = float(cos_a.mean())

        results["conditions"][label] = {
            "n_wall_in_slab": int(wall_idx.sum()),
            "plane_normal": plane_n.tolist(),
            "pos_thickness": {
                "mean_mm": float(pos_d.mean() * 1000),
                "median_mm": float(np.median(pos_d) * 1000),
                "p90_mm": float(np.percentile(pos_d, 90) * 1000),
                "std_mm": float(pos_d.std() * 1000),
            },
            "normal_alignment": {
                "mean_angle_deg": float(angle_deg.mean()),
                "median_angle_deg": float(np.median(angle_deg)),
                "p90_angle_deg": n_p90,
                "std_angle_deg": n_sig,
                "mean_cos": n_dot,
            },
        }
        print(f"{label:<10} {len(wall_pts):>7d} "
              f"{np.median(pos_d)*1000:>11.1f} {np.percentile(pos_d,90)*1000:>11.1f} "
              f"{n_sig:>8.2f} {n_p90:>8.2f} {n_dot:>8.3f}")

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(results, indent=2))
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
