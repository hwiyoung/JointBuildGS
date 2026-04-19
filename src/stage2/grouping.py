"""Group primitives for Mechanism 2 (L_structure).

Grouping criteria (per CLAUDE.md §메커니즘 2):
  - same class (argmax(f_i))
  - normal similarity (cos > threshold, default 0.95 ≈ 18°)
  - spatial proximity (same voxel)

Implementation: O(N) hashing.
  group_id = hash(class, voxel_3d, normal_direction_quantized)

Representative plane per group:
  n_k = normalize( Σ_{i∈G_k} w_i · n_i ),  w_i = max(exp(log_scales_i[:2]))
  d_k = −n_k · c̄_k                  (plane eq: n_k · x + d_k = 0)
"""
from __future__ import annotations

from typing import Tuple

import torch
import torch.nn.functional as F


# 12 direction basis (half-sphere upper; we'll use |dot| so it's symmetric)
def _fibonacci_directions(n: int = 12, device="cpu") -> torch.Tensor:
    """n evenly distributed unit vectors on sphere (Fibonacci lattice)."""
    indices = torch.arange(n, dtype=torch.float32, device=device) + 0.5
    phi = torch.acos(1 - 2 * indices / n)
    theta = torch.pi * (1 + 5 ** 0.5) * indices
    x = torch.sin(phi) * torch.cos(theta)
    y = torch.sin(phi) * torch.sin(theta)
    z = torch.cos(phi)
    return F.normalize(torch.stack([x, y, z], dim=-1), dim=-1)


def group_primitives(
    centers: torch.Tensor,        # (N, 3)
    normals: torch.Tensor,        # (N, 3) unit
    sem_logits: torch.Tensor,     # (N, K)
    scales: torch.Tensor,         # (N, 3) (not log)
    voxel_size: float = 0.05,
    n_directions: int = 12,
    min_group_size: int = 5,
    exclude_bg: bool = True,
) -> Tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
    """Assign group id per primitive.

    Returns:
        group_ids: (N,) int64, -1 = ungrouped (BG or singleton)
        rep_normals: (G, 3)   representative normals per valid group (G = num groups)
        rep_d: (G,)           plane offsets so that n_k · x + d_k = 0 on plane
    """
    device = centers.device
    N = centers.shape[0]
    with torch.no_grad():
        cls = sem_logits.argmax(dim=-1)           # (N,) in [0..K-1]

        # voxel_3d = floor(c / voxel_size)
        vox = torch.floor(centers / voxel_size).to(torch.int64)  # (N, 3)

        # normal direction bin: argmax |n · b_j|
        basis = _fibonacci_directions(n_directions, device=device)  # (D, 3)
        cos_ib = (normals @ basis.T).abs()                           # (N, D)
        dir_bin = cos_ib.argmax(dim=-1)                              # (N,)

        # Exclude BG (class 0): assign -1 group id
        valid = (cls != 0) if exclude_bg else torch.ones(N, dtype=torch.bool, device=device)

        # Hash: (class, vox_x, vox_y, vox_z, dir) → int64 unique id
        # Use large primes to reduce collision; or just use torch.unique with concatenated key.
        key = torch.stack([
            cls.to(torch.int64),
            vox[:, 0], vox[:, 1], vox[:, 2],
            dir_bin.to(torch.int64),
        ], dim=-1)                                                   # (N, 5)
        # Only valid entries go to unique
        key_valid = key[valid]
        # torch.unique with return_inverse
        uniq, inv = torch.unique(key_valid, return_inverse=True, dim=0)
        G_raw = uniq.shape[0]

        # group_ids for all primitives: init -1, then fill valid with inv
        raw_ids = torch.full((N,), -1, dtype=torch.int64, device=device)
        raw_ids[valid] = inv                                         # 0..G_raw-1

        # Filter groups by min size
        counts = torch.bincount(inv, minlength=G_raw)                # (G_raw,)
        keep = counts >= min_group_size                              # (G_raw,)
        # Remap: kept groups get new 0..G-1; rest get -1.
        remap = torch.full((G_raw,), -1, dtype=torch.int64, device=device)
        kept_idx = torch.nonzero(keep, as_tuple=False).squeeze(-1)
        remap[kept_idx] = torch.arange(kept_idx.numel(), device=device)
        group_ids = torch.full((N,), -1, dtype=torch.int64, device=device)
        valid2 = raw_ids >= 0
        group_ids[valid2] = remap[raw_ids[valid2]]
        group_ids[group_ids < 0] = -1

        # Compute rep_normals and rep_d per kept group
        G = kept_idx.numel()
        if G == 0:
            return group_ids, torch.zeros((0, 3), device=device), torch.zeros((0,), device=device)

        # Weights: max in-plane scale
        w = scales[:, :2].max(dim=-1).values                         # (N,)

        # Accumulate weighted normals + centers per group
        rep_n_acc = torch.zeros((G, 3), dtype=torch.float32, device=device)
        rep_c_acc = torch.zeros((G, 3), dtype=torch.float32, device=device)
        rep_w_acc = torch.zeros((G,), dtype=torch.float32, device=device)
        mask_in_group = group_ids >= 0
        g = group_ids[mask_in_group]
        rep_n_acc.index_add_(0, g, normals[mask_in_group] * w[mask_in_group, None])
        rep_c_acc.index_add_(0, g, centers[mask_in_group] * w[mask_in_group, None])
        rep_w_acc.index_add_(0, g, w[mask_in_group])

        rep_n = F.normalize(rep_n_acc / rep_w_acc[:, None].clamp_min(1e-8), dim=-1)
        rep_c = rep_c_acc / rep_w_acc[:, None].clamp_min(1e-8)
        rep_d = -(rep_n * rep_c).sum(dim=-1)

    return group_ids, rep_n, rep_d
