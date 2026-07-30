"""Evaluate inter-primitive consistency: σ_normal_intra, σ_coplanar, group stats.

Compares two checkpoints (typically Step 1-3 baseline vs Step 1-5 with L_structure).

σ_normal_intra: per-group std of normals projected on representative normal.
  Low = primitives in a group have very similar normals.
σ_coplanar: per-group RMS of primitive-to-plane distance.
  Low = primitives in a group lie on the same plane.

Uses the SAME grouping (from baseline) to fairly compare:
  - Group with ckpt A → compute σ for A and σ for B on same groups.
This isolates effect of L_structure from grouping changes.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F


def qn(q):
    q = q / np.maximum(np.linalg.norm(q, axis=1, keepdims=True), 1e-8)
    w, x, y, z = q[:, 0], q[:, 1], q[:, 2], q[:, 3]
    return np.stack([2*(x*z+w*y), 2*(y*z-w*x), 1-2*(x*x+y*y)], axis=1)


def load(ckpt):
    sd = torch.load(ckpt, map_location="cpu", weights_only=False)["state_dict"]
    return (
        sd["means"].numpy().astype(np.float32),
        sd["quats"].numpy().astype(np.float32),
        sd["log_scales"].numpy().astype(np.float32),
        sd["sem_logits"].numpy().astype(np.float32),
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ckpt-a", required=True, help="baseline")
    ap.add_argument("--ckpt-b", required=True, help="with L_structure")
    ap.add_argument("--out", required=True)
    ap.add_argument("--label-a", default="A")
    ap.add_argument("--label-b", default="B")
    ap.add_argument("--voxel-size", type=float, default=0.05)
    ap.add_argument("--n-directions", type=int, default=12)
    ap.add_argument("--min-group-size", type=int, default=5)
    args = ap.parse_args()

    out_dir = Path(args.out); out_dir.mkdir(parents=True, exist_ok=True)

    import sys; sys.path.insert(0, ".")
    from src.stage2.grouping import group_primitives

    mA, qA, lsA, sA = load(args.ckpt_a)
    mB, qB, lsB, sB = load(args.ckpt_b)

    nA = qn(qA); nA = nA / np.maximum(np.linalg.norm(nA, axis=1, keepdims=True), 1e-8)
    nB = qn(qB); nB = nB / np.maximum(np.linalg.norm(nB, axis=1, keepdims=True), 1e-8)

    def group_and_sigma(m, n, ls, s_, label):
        """Group primitives and compute per-group σ using OWN grouping."""
        gids, rep_n, rep_d = group_primitives(
            centers=torch.from_numpy(m).cuda(),
            normals=torch.from_numpy(n).cuda(),
            sem_logits=torch.from_numpy(s_).cuda(),
            scales=torch.from_numpy(np.exp(ls)).cuda(),
            voxel_size=args.voxel_size,
            n_directions=args.n_directions,
            min_group_size=args.min_group_size,
        )
        gids = gids.cpu().numpy()
        rep_n_np = rep_n.cpu().numpy()
        rep_d_np = rep_d.cpu().numpy()
        G = rep_n_np.shape[0]
        print(f"Groups ({label}): {G}, in-group: {(gids>=0).sum()}/{len(gids)}")

        sig_n = np.zeros(G, dtype=np.float64)
        sig_c = np.zeros(G, dtype=np.float64)
        sizes_out = np.zeros(G, dtype=np.int64)
        for k in range(G):
            mask = gids == k
            size = int(mask.sum())
            if size < 2: continue
            sizes_out[k] = size
            cos = np.abs((n[mask] * rep_n_np[k]).sum(axis=1))
            sig_n[k] = float(np.sqrt(((1 - cos) ** 2).mean()))
            sd = (m[mask] * rep_n_np[k]).sum(axis=1) + rep_d_np[k]
            sig_c[k] = float(np.sqrt((sd ** 2).mean()))
        valid = sizes_out >= 2
        return sig_n[valid], sig_c[valid], sizes_out[valid], G, int((gids>=0).sum()), len(gids)

    sig_n_A, sig_c_A, sizes_A, G_A, in_A, N_A = group_and_sigma(mA, nA, lsA, sA, args.label_a)
    sig_n_B, sig_c_B, sizes_B, G_B, in_B, N_B = group_and_sigma(mB, nB, lsB, sB, args.label_b)
    # For unified table use union
    sizes = sizes_A  # for printing mean/median reference

    # weighted by group size
    wA = sizes_A / sizes_A.sum() if sizes_A.sum() > 0 else sizes_A
    wB = sizes_B / sizes_B.sum() if sizes_B.sum() > 0 else sizes_B
    results = {
        "note": "Each ckpt grouped independently (different N/classifications)",
        args.label_a: {
            "n_groups": G_A, "n_in_group": in_A, "total_primitives": N_A,
            "mean_group_size": float(sizes_A.mean()) if sizes_A.size else 0,
            "median_group_size": float(np.median(sizes_A)) if sizes_A.size else 0,
            "sigma_normal_intra_mean": float(sig_n_A.mean()),
            "sigma_normal_intra_wmean": float((sig_n_A * wA).sum()),
            "sigma_coplanar_mean": float(sig_c_A.mean()),
            "sigma_coplanar_wmean": float((sig_c_A * wA).sum()),
        },
        args.label_b: {
            "n_groups": G_B, "n_in_group": in_B, "total_primitives": N_B,
            "mean_group_size": float(sizes_B.mean()) if sizes_B.size else 0,
            "median_group_size": float(np.median(sizes_B)) if sizes_B.size else 0,
            "sigma_normal_intra_mean": float(sig_n_B.mean()),
            "sigma_normal_intra_wmean": float((sig_n_B * wB).sum()),
            "sigma_coplanar_mean": float(sig_c_B.mean()),
            "sigma_coplanar_wmean": float((sig_c_B * wB).sum()),
        },
    }
    print(json.dumps(results, indent=2))
    (out_dir / "structure_stats.json").write_text(json.dumps(results, indent=2))

    # Histograms
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))

    bins_n = np.linspace(0, sig_n_A.max() * 1.1, 60)
    axes[0].hist(sig_n_A, bins=bins_n, color="steelblue", alpha=0.6, label=f"{args.label_a} (mean={sig_n_A.mean():.4f})")
    axes[0].hist(sig_n_B, bins=bins_n, color="crimson", alpha=0.6, label=f"{args.label_b} (mean={sig_n_B.mean():.4f})")
    axes[0].set_title("σ_normal_intra per group"); axes[0].set_xlabel("RMS(1 − |n·n_k|)"); axes[0].legend(); axes[0].grid(alpha=0.3)

    bins_c = np.linspace(0, max(sig_c_A.max(), sig_c_B.max()) * 0.5, 60)
    axes[1].hist(sig_c_A, bins=bins_c, color="steelblue", alpha=0.6, label=f"{args.label_a} (mean={sig_c_A.mean():.4f})")
    axes[1].hist(sig_c_B, bins=bins_c, color="crimson", alpha=0.6, label=f"{args.label_b} (mean={sig_c_B.mean():.4f})")
    axes[1].set_title("σ_coplanar per group"); axes[1].set_xlabel("RMS(n_k·c + d_k)"); axes[1].legend(); axes[1].grid(alpha=0.3)

    plt.tight_layout()
    plt.savefig(out_dir / "structure_histograms.png", dpi=100, bbox_inches="tight")
    print(f"wrote {out_dir/'structure_histograms.png'}")


if __name__ == "__main__":
    main()
