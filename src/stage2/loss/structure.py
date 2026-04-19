"""L_structure — Inter-primitive alignment (Mechanism 2).

L_structure = λ_na · L_normal_align + λ_cp · L_coplanar

Where (n_k, d_k) are the representative plane per group, detached:
    L_normal_align = mean_{i in grouped} (1 − n_i · n_k[group(i)])²
    L_coplanar     = mean_{i in grouped} (n_k[group(i)] · c_i + d_k[group(i)])²

Gradient:
  - n_i gradient via L_normal_align (n_k detach).
  - c_i gradient via L_coplanar (n_k, d_k detach).
  - f_i NOT differentiated (group assignment = argmax, discrete).
  - s_i NOT included.
"""
from __future__ import annotations

import torch


def l_structure(
    normals: torch.Tensor,     # (N, 3) primitive normals, world (from quats)
    centers: torch.Tensor,     # (N, 3)
    group_ids: torch.Tensor,   # (N,) int64, -1 for ungrouped
    rep_normals: torch.Tensor, # (G, 3) detached
    rep_d: torch.Tensor,       # (G,)  detached
    w_normal_align: float = 1.0,
    w_coplanar: float = 1.0,
):
    """Compute L_structure with per-term breakdown.

    Returns a dict: total, normal_align, coplanar, n_used (grouped primitives).
    """
    zero = torch.zeros((), device=normals.device)
    if rep_normals.shape[0] == 0 or (group_ids >= 0).sum() == 0:
        return {"total": zero, "normal_align": zero, "coplanar": zero, "n_used": 0}

    mask = group_ids >= 0
    g = group_ids[mask]              # (M,) in [0..G-1]
    n_i = normals[mask]              # (M, 3)
    c_i = centers[mask]              # (M, 3)
    # Gather rep per primitive (detach to block gradient into rep)
    n_k = rep_normals[g].detach()    # (M, 3)
    d_k = rep_d[g].detach()          # (M,)

    cos = (n_i * n_k).sum(dim=-1)    # (M,)
    # Use |cos| to be sign-robust (rep normal orientation may differ in sign)
    err_align = (1.0 - cos.abs()) ** 2
    loss_align = err_align.mean()

    # Signed distance to plane: n_k·c + d_k
    sd = (n_k * c_i).sum(dim=-1) + d_k
    loss_coplanar = (sd ** 2).mean()

    total = w_normal_align * loss_align + w_coplanar * loss_coplanar
    return {
        "total": total,
        "normal_align": loss_align.detach(),
        "coplanar": loss_coplanar.detach(),
        "n_used": int(mask.sum().item()),
    }
