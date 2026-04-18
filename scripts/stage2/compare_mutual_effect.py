"""Compare effect of L_mutual on primitives: wall normal verticality + p_wall distribution.

For Step 1-3 (no L_mutual) vs Step 1-4 (with L_mutual) checkpoints, compute:
  1. Distribution of |n · e_gravity| for primitives with p_wall > threshold.
     Walls should have |n · e_g| ≈ 0 (horizontal normal).
     Metric: fraction of "wall" primitives with |n·e_g| < sin(10°) = 0.174
  2. Softmax(f_i) distribution change — are class probabilities more confident?
  3. Class count change from argmax(f_i).

Output: side-by-side histograms + stats JSON.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import torch
import torch.nn.functional as F


CLASS_NAMES = ["BG", "Roof", "Wall", "Terrain"]


def quat_to_normal(quats: torch.Tensor) -> torch.Tensor:
    """n = R(q)[:, 2]."""
    q = quats / quats.norm(dim=-1, keepdim=True).clamp_min(1e-8)
    w, x, y, z = q.unbind(-1)
    n_x = 2 * (x * z + w * y)
    n_y = 2 * (y * z - w * x)
    n_z = 1 - 2 * (x * x + y * y)
    return torch.stack([n_x, n_y, n_z], dim=-1)


def analyze_ckpt(path, e_g):
    sd = torch.load(path, map_location="cpu", weights_only=False)["state_dict"]
    quats = sd["quats"]
    sem_logits = sd["sem_logits"]
    p = F.softmax(sem_logits, dim=-1).numpy()
    classes = p.argmax(axis=1)

    n = quat_to_normal(quats).numpy()
    n = n / np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-8)
    dot_g = np.abs(n @ e_g)  # |n · e_g| ∈ [0,1]

    counts = {CLASS_NAMES[c]: int((classes == c).sum()) for c in range(4)}
    N = len(classes)

    # Wall stats: primitives with argmax=Wall, measure their |n·e_g|
    wall_mask = classes == 2
    wall_dot = dot_g[wall_mask]
    wall_n = int(wall_mask.sum())
    wall_vertical_frac = float((wall_dot < np.sin(np.deg2rad(10))).mean()) if wall_n > 0 else 0

    # Roof stats: argmax=Roof, measure their |n·e_g| (should be close to 1)
    roof_mask = classes == 1
    roof_dot = dot_g[roof_mask]
    roof_n = int(roof_mask.sum())
    roof_horizontal_frac = float((roof_dot > np.cos(np.deg2rad(10))).mean()) if roof_n > 0 else 0

    # Terrain stats
    terrain_mask = classes == 3
    terrain_dot = dot_g[terrain_mask]
    terrain_n = int(terrain_mask.sum())
    terrain_horizontal_frac = float((terrain_dot > np.cos(np.deg2rad(10))).mean()) if terrain_n > 0 else 0

    # Confidence: max softmax prob
    max_p = p.max(axis=1)

    return {
        "N": N,
        "counts": counts,
        "wall_vertical_frac": wall_vertical_frac,   # |n·e_g|<sin10° for walls
        "roof_horizontal_frac": roof_horizontal_frac,
        "terrain_horizontal_frac": terrain_horizontal_frac,
        "wall_dot": wall_dot,
        "roof_dot": roof_dot,
        "terrain_dot": terrain_dot,
        "mean_max_p": float(max_p.mean()),
        "p_wall": p[:, 2],
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ckpt-a", required=True, help="Step 1-3 (baseline)")
    ap.add_argument("--ckpt-b", required=True, help="Step 1-4 (with L_mutual)")
    ap.add_argument("--gravity", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--label-a", default="Step 1-3 (no L_mutual)")
    ap.add_argument("--label-b", default="Step 1-4 (+ L_mutual)")
    args = ap.parse_args()

    e_g = np.asarray(json.loads(Path(args.gravity).read_text())["e_gravity"], dtype=np.float64)
    print(f"e_gravity: {e_g}")

    A = analyze_ckpt(args.ckpt_a, e_g)
    B = analyze_ckpt(args.ckpt_b, e_g)

    out_dir = Path(args.out); out_dir.mkdir(parents=True, exist_ok=True)

    # Figure: 3 rows × 2 cols
    # Row 1: |n·e_g| histogram for wall class — lower is better (more vertical)
    # Row 2: |n·e_g| for roof class — higher is better (more horizontal)
    # Row 3: p_wall histogram
    fig, axes = plt.subplots(3, 2, figsize=(12, 10))

    bins = np.linspace(0, 1, 41)
    axes[0,0].hist(A["wall_dot"], bins=bins, color="steelblue", alpha=0.8)
    axes[0,0].axvline(np.sin(np.deg2rad(10)), color="red", linestyle="--",
                      label=f"vertical th (sin 10° ≈ 0.174)")
    axes[0,0].set_title(f"{args.label_a}  |  Wall primitives: |n·e_g|\n"
                        f"N={A['counts']['Wall']:,}  vertical-frac={A['wall_vertical_frac']:.3f}")
    axes[0,0].set_xlabel("|n·e_g|"); axes[0,0].set_ylabel("count"); axes[0,0].legend()
    axes[0,0].grid(True, alpha=0.3)

    axes[0,1].hist(B["wall_dot"], bins=bins, color="crimson", alpha=0.8)
    axes[0,1].axvline(np.sin(np.deg2rad(10)), color="red", linestyle="--")
    axes[0,1].set_title(f"{args.label_b}  |  Wall primitives: |n·e_g|\n"
                        f"N={B['counts']['Wall']:,}  vertical-frac={B['wall_vertical_frac']:.3f}")
    axes[0,1].set_xlabel("|n·e_g|"); axes[0,1].grid(True, alpha=0.3)

    # Roof |n·e_g| — should be ~1 (horizontal)
    axes[1,0].hist(A["roof_dot"], bins=bins, color="steelblue", alpha=0.8)
    axes[1,0].axvline(np.cos(np.deg2rad(10)), color="green", linestyle="--",
                      label="horizontal th (cos 10° ≈ 0.985)")
    axes[1,0].set_title(f"{args.label_a}  |  Roof: |n·e_g|\n"
                        f"N={A['counts']['Roof']:,}  horizontal-frac={A['roof_horizontal_frac']:.3f}")
    axes[1,0].set_xlabel("|n·e_g|"); axes[1,0].legend(); axes[1,0].grid(True, alpha=0.3)

    axes[1,1].hist(B["roof_dot"], bins=bins, color="crimson", alpha=0.8)
    axes[1,1].axvline(np.cos(np.deg2rad(10)), color="green", linestyle="--")
    axes[1,1].set_title(f"{args.label_b}  |  Roof: |n·e_g|\n"
                        f"N={B['counts']['Roof']:,}  horizontal-frac={B['roof_horizontal_frac']:.3f}")
    axes[1,1].set_xlabel("|n·e_g|"); axes[1,1].grid(True, alpha=0.3)

    # p_wall distribution
    pbins = np.linspace(0, 1, 41)
    axes[2,0].hist(A["p_wall"], bins=pbins, color="steelblue", alpha=0.8)
    axes[2,0].set_title(f"{args.label_a}  |  p_wall = softmax(f_i)[2]\n"
                        f"mean={A['p_wall'].mean():.3f}  >0.5 frac={(A['p_wall']>0.5).mean():.3f}")
    axes[2,0].set_xlabel("p_wall"); axes[2,0].set_yscale("log"); axes[2,0].grid(True, alpha=0.3)

    axes[2,1].hist(B["p_wall"], bins=pbins, color="crimson", alpha=0.8)
    axes[2,1].set_title(f"{args.label_b}  |  p_wall\n"
                        f"mean={B['p_wall'].mean():.3f}  >0.5 frac={(B['p_wall']>0.5).mean():.3f}")
    axes[2,1].set_xlabel("p_wall"); axes[2,1].set_yscale("log"); axes[2,1].grid(True, alpha=0.3)

    plt.tight_layout()
    plt.savefig(out_dir / "mutual_effect.png", dpi=100, bbox_inches="tight")
    print(f"wrote {out_dir/'mutual_effect.png'}")

    # Summary JSON
    summary = {
        "gravity": e_g.tolist(),
        args.label_a: {
            "N": A["N"], "counts": A["counts"],
            "wall_vertical_frac": A["wall_vertical_frac"],
            "roof_horizontal_frac": A["roof_horizontal_frac"],
            "terrain_horizontal_frac": A["terrain_horizontal_frac"],
            "mean_max_p": A["mean_max_p"],
            "p_wall_mean": float(A["p_wall"].mean()),
            "p_wall_gt_0.5_frac": float((A["p_wall"] > 0.5).mean()),
        },
        args.label_b: {
            "N": B["N"], "counts": B["counts"],
            "wall_vertical_frac": B["wall_vertical_frac"],
            "roof_horizontal_frac": B["roof_horizontal_frac"],
            "terrain_horizontal_frac": B["terrain_horizontal_frac"],
            "mean_max_p": B["mean_max_p"],
            "p_wall_mean": float(B["p_wall"].mean()),
            "p_wall_gt_0.5_frac": float((B["p_wall"] > 0.5).mean()),
        },
    }
    (out_dir / "mutual_effect.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
