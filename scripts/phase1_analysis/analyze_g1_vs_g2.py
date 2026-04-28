"""8.4 Phase 1 G1 vs G2 post-hoc σ comparison.

For each Phase 1 condition (Baseline=semantic, Mutual, Structure, Both=ablation):
  - Load ckpt
  - Run group_primitives() (G1) and group_primitives_g2() (G2)
  - Compute per-group σ_normal_intra and σ_coplanar
  - Report deltas

Output: results/phase1_g1_vs_g2_summary.json + console table
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
import torch

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from src.stage2.model import quat_to_rotmat
from src.stage2.grouping import group_primitives, group_primitives_g2

PHASE1_CONDITIONS = {
    "Baseline (Step 1-3)":  "results/phase1_semantic/run/ckpt/final.pt",
    "Mutual (Step 1-4)":    "results/phase1_mutual/run/ckpt/final.pt",
    "Structure (Step 1-5)": "results/phase1_structure/run/ckpt/final.pt",
    "Both (Step 1-6)":      "results/phase1_ablation/run/ckpt/final.pt",
}


def load_primitives(ckpt_path: str, device="cuda"):
    sd = torch.load(ckpt_path, map_location="cpu")["state_dict"]
    means = sd["means"].float().to(device)
    quats = sd["quats"].float().to(device)
    log_scales = sd["log_scales"].float().to(device)
    sem_logits = sd["sem_logits"].float().to(device)
    R = quat_to_rotmat(quats)
    normals = R[..., :, 2]
    scales = torch.exp(log_scales)
    return means, normals, scales, sem_logits


def per_group_sigma(centers, normals, scales, sem_logits, group_fn, **kwargs):
    """Vectorized: returns σ_normal_intra (deg) and σ_coplanar (m) over groups.

    All ops via torch tensor on GPU then small reduction → fast even for 250k groups.
    """
    gid, rep_n, rep_d = group_fn(centers=centers, normals=normals,
                                  sem_logits=sem_logits, scales=scales, **kwargs)
    G = int(rep_n.shape[0])
    if G == 0:
        return {"n_groups": 0, "n_grouped": 0,
                "sigma_normal_intra_deg_mean": float("nan"), "sigma_normal_intra_deg_median": float("nan"),
                "sigma_coplanar_m_mean": float("nan"), "sigma_coplanar_m_median": float("nan")}

    device = centers.device
    valid = gid >= 0
    g = gid[valid]                            # (M,)
    n_i = normals[valid]                      # (M,3)
    c_i = centers[valid]                      # (M,3)
    rn = rep_n[g]                             # (M,3) per primitive's group rep
    rd = rep_d[g]                             # (M,)

    # σ_normal_intra: angle (deg) between n_i and group rep, sign-disambiguated
    cos_v = (n_i * rn).sum(-1).clamp(-1, 1)
    ang = torch.acos(cos_v.abs()) * (180.0 / 3.141592653589793)   # |·| handles sign
    # σ_coplanar: |n·c + d|
    off = ((c_i * rn).sum(-1) + rd).abs()

    # group-wise mean (sum / count)
    n_in_g = torch.zeros(G, device=device, dtype=torch.float64)
    sum_ang2 = torch.zeros(G, device=device, dtype=torch.float64)
    sum_ang = torch.zeros(G, device=device, dtype=torch.float64)
    sum_off2 = torch.zeros(G, device=device, dtype=torch.float64)
    n_in_g.index_add_(0, g, torch.ones_like(g, dtype=torch.float64))
    sum_ang.index_add_(0, g, ang.double())
    sum_ang2.index_add_(0, g, ang.double() ** 2)
    sum_off2.index_add_(0, g, off.double() ** 2)

    keep = n_in_g >= 2
    nig = n_in_g[keep]
    mean_ang = sum_ang[keep] / nig
    var_ang = sum_ang2[keep] / nig - mean_ang ** 2
    sigma_n_per_group = var_ang.clamp_min(0).sqrt()  # deg, std within group
    sigma_c_per_group = (sum_off2[keep] / nig).clamp_min(0).sqrt()  # m, RMS

    sn_mean = float(sigma_n_per_group.mean().item())
    sn_med = float(sigma_n_per_group.median().item())
    sc_mean = float(sigma_c_per_group.mean().item())
    sc_med = float(sigma_c_per_group.median().item())

    return {
        "n_groups": G,
        "n_groups_with_2plus": int(keep.sum().item()),
        "n_grouped": int(valid.sum().item()),
        "sigma_normal_intra_deg_mean": sn_mean,
        "sigma_normal_intra_deg_median": sn_med,
        "sigma_coplanar_m_mean": sc_mean,
        "sigma_coplanar_m_median": sc_med,
    }


def main():
    out_dir = Path("results/phase1_analysis")
    out_dir.mkdir(parents=True, exist_ok=True)

    summary = {}
    for cond, ckpt in PHASE1_CONDITIONS.items():
        ckpt_path = _ROOT / ckpt
        if not ckpt_path.exists():
            print(f"  {cond}: SKIP (no ckpt)")
            continue
        print(f"\n=== {cond} ===")
        print(f"  loading {ckpt}")
        centers, normals, scales, sem_logits = load_primitives(str(ckpt_path))
        N = centers.shape[0]
        print(f"  N_primitives = {N:,}")

        t0 = time.perf_counter()
        g1_stats = per_group_sigma(centers, normals, scales, sem_logits,
                                    group_primitives,
                                    voxel_size=0.05, n_directions=12,
                                    min_group_size=5, exclude_bg=True)
        t_g1 = time.perf_counter() - t0
        print(f"  G1 ({t_g1:.1f}s): n_groups={g1_stats['n_groups']:6d}  "
              f"σ_normal={g1_stats['sigma_normal_intra_deg_mean']:.3f}°  "
              f"σ_coplanar={g1_stats['sigma_coplanar_m_mean']*1000:.2f}mm")

        t0 = time.perf_counter()
        g2_stats = per_group_sigma(centers, normals, scales, sem_logits,
                                    group_primitives_g2,
                                    voxel_size=2.0, n_directions=12,
                                    merge_n_cos=0.92, merge_d_tol=0.5,
                                    min_group_size=30, exclude_bg=True)
        t_g2 = time.perf_counter() - t0
        print(f"  G2 ({t_g2:.1f}s): n_groups={g2_stats['n_groups']:6d}  "
              f"σ_normal={g2_stats['sigma_normal_intra_deg_mean']:.3f}°  "
              f"σ_coplanar={g2_stats['sigma_coplanar_m_mean']*1000:.2f}mm")

        summary[cond] = {
            "ckpt": ckpt,
            "n_primitives": N,
            "G1": {**g1_stats, "timing_sec": round(t_g1, 2)},
            "G2": {**g2_stats, "timing_sec": round(t_g2, 2)},
        }

    out_path = out_dir / "g1_vs_g2_summary.json"
    with open(out_path, "w") as f:
        json.dump(summary, f, indent=2)
    print(f"\n[done] wrote {out_path}")

    # Print delta table
    print("\n" + "="*100)
    print(f"{'Condition':<25} {'σ_normal G1°':>12} {'σ_normal G2°':>12} {'Δ%':>8} | "
          f"{'σ_coplanar G1mm':>14} {'σ_coplanar G2mm':>14} {'Δ%':>8}")
    print("="*100)
    for cond, s in summary.items():
        sn1 = s["G1"]["sigma_normal_intra_deg_mean"]
        sn2 = s["G2"]["sigma_normal_intra_deg_mean"]
        sc1 = s["G1"]["sigma_coplanar_m_mean"] * 1000
        sc2 = s["G2"]["sigma_coplanar_m_mean"] * 1000
        dn = (sn2 - sn1) / sn1 * 100 if sn1 > 0 else 0
        dc = (sc2 - sc1) / sc1 * 100 if sc1 > 0 else 0
        print(f"{cond:<25} {sn1:>12.3f} {sn2:>12.3f} {dn:>+7.1f}% | "
              f"{sc1:>14.2f} {sc2:>14.2f} {dc:>+7.1f}%")


if __name__ == "__main__":
    main()
