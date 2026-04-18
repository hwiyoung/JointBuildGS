"""L_mutual — Intra-primitive domain rule loss (Mechanism 1).

Per-primitive bidirectional constraint coupling semantic class (f_i) and
geometric normal/center (n_i, c_i) through domain rules.

L_mutual = Σ_i [
    p_wall · L_vert(n_i)                # walls should have horizontal normal
  + p_roof · L_slope(n_i)               # roofs should NOT be flat (penalize wall-like)
  + p_terrain · L_horiz(n_i)            # terrain should have vertical normal (up)
  + p_roof · L_height_roof(c_i)         # roofs should be above height threshold
  + p_terrain · L_height_terrain(c_i)   # terrain should be below height threshold
]

Gradient flows bidirectionally through p_c (from softmax(f_i)) AND the geometric terms:
  - f_i gets gradient via p_c × (geom_err)
  - n_i gets gradient via p_c × d(geom_err)/dn
  - c_i gets gradient only through L_height (height component)

References:
  - legacy/planarsplat_ref/loss_util.py (L_vert, L_slope, L_horiz)
  - CLAUDE.md §메커니즘 1: 양방향 gradient, s_i 없음
"""
from __future__ import annotations

import torch
import torch.nn.functional as F


def _height_axis(e_gravity: torch.Tensor) -> int:
    """Return axis index where |e_gravity| is largest (typically 2 for Z-up world)."""
    return int(e_gravity.abs().argmax().item())


def l_mutual(
    normals: torch.Tensor,          # (N, 3) per-primitive normals in world frame
    centers: torch.Tensor,          # (N, 3) per-primitive centers in world frame
    sem_logits: torch.Tensor,       # (N, K=4) raw semantic logits
    e_gravity: torch.Tensor,        # (3,) unit gravity vector, e.g. (0,0,-1)
    tau: float = 0.15,
    height_th: float = 0.15,        # world-height threshold separating Terrain / Roof
    w_vert: float = 1.0,
    w_slope: float = 1.0,
    w_horiz: float = 1.0,
    w_height: float = 1.0,
    mode: str = "full",             # "full" | "sem2geo" | "geo2sem"
) -> dict:
    """Compute L_mutual with optional gradient mode for diagnostics.

    Returns a dict with the total loss and per-term breakdown.

    Classes (must match dataloader): 0=BG, 1=Roof, 2=Wall, 3=Terrain.
    """
    if mode == "none":
        zero = torch.zeros((), device=normals.device)
        return {"total": zero, "vert": zero, "slope": zero, "horiz": zero, "height": zero}

    # Class probabilities
    p = F.softmax(sem_logits, dim=-1)       # (N, 4)
    p_roof = p[:, 1]
    p_wall = p[:, 2]
    p_terrain = p[:, 3]

    if mode == "sem2geo":
        p_roof = p_roof.detach()
        p_wall = p_wall.detach()
        p_terrain = p_terrain.detach()

    # Normalize and dot with gravity
    n = F.normalize(normals, dim=-1, eps=1e-6)
    c = centers
    e_g = e_gravity.to(n.device)
    if mode == "geo2sem":
        n = n.detach()
        c = c.detach()

    dot = (n * e_g).sum(dim=-1)             # (N,)

    # Geometric terms
    L_vert  = dot ** 2                       # wall: 0 when horizontal
    L_horiz = (1.0 - dot.abs()) ** 2         # terrain: 0 when vertical (|n·g|=1)
    L_slope = F.relu(tau - dot ** 2) ** 2    # roof: penalty if too horizontal (wall-like)

    # Height term — uses component along gravity's magnitude direction
    # World Z-up: e_g ≈ (0,0,-1), so "height" = centers along +gravity opposite = -c·e_g
    # Equivalently: height = (-c) · e_g, but cleaner to use the axis with largest |e_g|
    ax = _height_axis(e_g)
    sign = -torch.sign(e_g[ax])              # +1 if e_g points in -Z (Z-up world)
    height = sign * c[:, ax]                 # (N,) larger = higher altitude

    # Roof should be above height_th, Terrain below
    L_h_roof = F.relu(height_th - height) ** 2
    L_h_terrain = F.relu(height - height_th) ** 2

    # Weighted sum per primitive, mean over all primitives
    loss_vert = (p_wall * L_vert).mean()
    loss_slope = (p_roof * L_slope).mean()
    loss_horiz = (p_terrain * L_horiz).mean()
    loss_height = (p_roof * L_h_roof + p_terrain * L_h_terrain).mean()

    total = (
        w_vert * loss_vert
        + w_slope * loss_slope
        + w_horiz * loss_horiz
        + w_height * loss_height
    )
    return {
        "total": total,
        "vert": loss_vert.detach(),
        "slope": loss_slope.detach(),
        "horiz": loss_horiz.detach(),
        "height": loss_height.detach(),
    }
