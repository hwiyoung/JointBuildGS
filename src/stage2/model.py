"""2DGS primitive model (gsplat-compatible).

Each primitive G_i = {c_i, q_i, s_i, opacity_i, SH_i}
    c_i:        (N, 3) center
    q_i:        (N, 4) unit quaternion (w, x, y, z) — defines local frame R(q)
                Columns of R(q) = [t_u, t_v, n]. So:
                  t_u = R[:, 0]
                  t_v = R[:, 1]
                  n   = R[:, 2]
                This matches CLAUDE.md (tangent_u/v learned, n derived).
    s_i:        (N, 2) in-plane scales
    opacity_i:  (N,) raw (sigmoid-activated at render)
    SH:         sh0 (N, 1, 3) + shN (N, (deg+1)^2-1, 3)

Initialization: COLMAP sparse point cloud (xyz + rgb). Quats init = identity.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional, Tuple

import numpy as np
import torch
import torch.nn as nn

# Semantic-seed init constants (P2 implementation ①, see semantic_seed.py).
SEED_SEM_LOGIT = 5.0     # near-one-hot: softmax([5,0,0,0]) ~= 0.97 for the seed class
SEED_INIT_OPACITY = 0.25  # mid opacity so seeds are not pruned immediately at init


# ---------- quaternion helpers ----------

def quat_to_rotmat(q: torch.Tensor) -> torch.Tensor:
    """q: (...,4) wxyz -> R: (...,3,3)."""
    q = q / q.norm(dim=-1, keepdim=True).clamp_min(1e-8)
    w, x, y, z = q.unbind(-1)
    B = q.shape[:-1]
    R = torch.stack(
        [
            1 - 2 * (y * y + z * z), 2 * (x * y - w * z), 2 * (x * z + w * y),
            2 * (x * y + w * z), 1 - 2 * (x * x + z * z), 2 * (y * z - w * x),
            2 * (x * z - w * y), 2 * (y * z + w * x), 1 - 2 * (x * x + y * y),
        ],
        dim=-1,
    ).reshape(*B, 3, 3)
    return R


# ---------- model ----------

class GaussianModel2D(nn.Module):
    def __init__(
        self,
        points_xyz: np.ndarray,
        points_rgb: np.ndarray,
        sh_degree: int = 3,
        init_scale_factor: float = 1.0,
        device: str = "cuda",
        points_sem: Optional[np.ndarray] = None,
        points_init_opacity: Optional[np.ndarray] = None,
        surface_seed_mask: Optional[np.ndarray] = None,
    ):
        super().__init__()
        self.sh_degree = sh_degree
        self.max_sh_degree = sh_degree
        self.active_sh_degree = 0  # warmup

        N = points_xyz.shape[0]
        xyz = torch.from_numpy(points_xyz).float()
        rgb = torch.from_numpy(points_rgb).float()

        # --- centers ---
        self.means = nn.Parameter(xyz.to(device))

        # --- quats: identity (w=1) ---
        quats = torch.zeros(N, 4)
        quats[:, 0] = 1.0
        self.quats = nn.Parameter(quats.to(device))

        # --- scales: 3 dims for gsplat; dim 0,1 = in-plane, dim 2 ≈ 0 (planar) ---
        s0 = _estimate_init_scale(points_xyz, k=3) * init_scale_factor  # (N,)
        log_s = torch.log(torch.from_numpy(s0).float().clamp_min(1e-6))
        log_scales = torch.zeros(N, 3)
        log_scales[:, 0] = log_s
        log_scales[:, 1] = log_s
        log_scales[:, 2] = math.log(1e-6)  # near-zero thickness → planar (2DGS)
        self.log_scales = nn.Parameter(log_scales.to(device))

        # --- semantic seed mask (P2 ①): points with a specified class id (>=0) ---
        # are carved seeds for textureless buildings; -1/None means "SfM point".
        if points_sem is not None:
            sem_ids = torch.from_numpy(np.asarray(points_sem)).long()
            seed_mask = sem_ids >= 0
        else:
            sem_ids = torch.full((N,), -1, dtype=torch.long)
            seed_mask = torch.zeros(N, dtype=torch.bool)

        # --- opacity: legacy path remains SfM=.10 / semantic carve=.25. ---
        if points_init_opacity is None:
            opacity_values = torch.full((N,), 0.1, dtype=torch.float32)
            if seed_mask.any():
                opacity_values[seed_mask] = SEED_INIT_OPACITY
        else:
            init = np.asarray(points_init_opacity)
            if init.shape != (N,) or not np.isfinite(init).all():
                raise ValueError("points_init_opacity must be finite with shape (N,)")
            if np.any((init <= 0.0) | (init >= 1.0)):
                raise ValueError("points_init_opacity values must lie in (0,1)")
            opacity_values = torch.from_numpy(init.astype(np.float32, copy=False))
        opa = torch.logit(opacity_values)
        self.opacities_raw = nn.Parameter(opa.to(device))

        # Plain tensor (not a persistent buffer) keeps legacy checkpoint state
        # dictionaries byte-compatible.  Densification copies this once into
        # strategy state, whose row-wise tensors preserve split/clone lineage.
        if surface_seed_mask is None:
            surface = torch.zeros(N, dtype=torch.bool)
        else:
            surface_np = np.asarray(surface_seed_mask)
            if surface_np.dtype != np.bool_ or surface_np.shape != (N,):
                raise ValueError("surface_seed_mask must be bool with shape (N,)")
            surface = torch.from_numpy(surface_np)
        self.surface_seed_mask = surface.to(device)

        # --- SH ---
        # DC from RGB in SH0 basis: C0 = 0.2820947917 ; sh_dc = (rgb - 0.5) / C0
        C0 = 0.28209479177387814
        sh0 = ((rgb - 0.5) / C0)[:, None, :]  # (N,1,3)
        n_rest = (sh_degree + 1) ** 2 - 1
        shN = torch.zeros(N, n_rest, 3)
        self.sh0 = nn.Parameter(sh0.to(device))
        self.shN = nn.Parameter(shN.to(device))

        # --- semantic logits f_i (N, K) ---
        # K=4: BG(0), Roof(1), Wall(2), Terrain(3). Init near-uniform with small noise;
        # carved seeds are initialised near-one-hot toward their carved class (P2 ①).
        self.num_classes = 4
        sem = 0.01 * torch.randn(N, self.num_classes)
        if seed_mask.any():
            seed_rows = torch.where(seed_mask)[0]
            sem[seed_rows, sem_ids[seed_rows]] += SEED_SEM_LOGIT
        self.sem_logits = nn.Parameter(sem.to(device))

    # ---------- derived ----------
    @property
    def num_points(self) -> int:
        return self.means.shape[0]

    @property
    def scales(self) -> torch.Tensor:
        """(N, 3) scales (exp). dim 2 is near-zero for 2DGS planarity."""
        return torch.exp(self.log_scales)

    @property
    def opacities(self) -> torch.Tensor:
        return torch.sigmoid(self.opacities_raw)

    def normals(self) -> torch.Tensor:
        """n_i = R(q_i)[:, 2] — per CLAUDE.md, n derived from learned frame."""
        R = quat_to_rotmat(self.quats)
        return R[..., :, 2]  # (N,3)

    def tangents(self) -> Tuple[torch.Tensor, torch.Tensor]:
        R = quat_to_rotmat(self.quats)
        return R[..., :, 0], R[..., :, 1]

    def colors_sh(self) -> torch.Tensor:
        """Return (N, (deg+1)^2, 3) for gsplat."""
        return torch.cat([self.sh0, self.shN], dim=1)

    # ---------- SH warmup (Gaussian-Splatting convention) ----------
    def oneup_sh_degree(self):
        if self.active_sh_degree < self.max_sh_degree:
            self.active_sh_degree += 1


def _inv_sigmoid(p: float) -> float:
    return float(np.log(p / (1 - p)))


def _estimate_init_scale(xyz: np.ndarray, k: int = 3) -> np.ndarray:
    """Mean distance to k nearest neighbors → per-point init scale."""
    from scipy.spatial import cKDTree

    tree = cKDTree(xyz)
    # k+1 because the nearest is the point itself
    d, _ = tree.query(xyz, k=k + 1)
    d = d[:, 1:]  # drop self
    s = d.mean(axis=1).astype(np.float32)
    s = np.clip(s, 1e-4, None)
    return s
