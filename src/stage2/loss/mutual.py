"""L_mutual — Intra-primitive domain rule loss (Mechanism 1).

Per-primitive bidirectional constraint coupling semantic class (f_i) and
geometric normal/center (n_i, c_i) through domain rules.

L_mutual = Σ_i [
    p_wall · L_vert(n_i)                # walls should have horizontal normal
  + p_roof · L_slope(n_i)               # roofs should not be wall-like
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


_MUTUAL_RETURN_KEYS = (
    "total",
    "vert",
    "slope",
    "horiz",
    "height",
    "wall_vertical",
    "roof_nonwall",
    "terrain_normal",
    "terrain_height",
    "height_roof",
    "height_terrain",
    "sem_geom_calib",
    "sem_geom_reliability",
    "sem_geom_active_frac",
    "sem_geom_entropy",
    "roof_wall_relation",
    "terrain_wall_relation",
)


def _height_axis(e_gravity: torch.Tensor) -> int:
    """Return axis index where |e_gravity| is largest (typically 2 for Z-up world)."""
    return int(e_gravity.abs().argmax().item())


def _zero_terms(device: torch.device) -> dict:
    zero = torch.zeros((), device=device)
    return {k: zero for k in _MUTUAL_RETURN_KEYS}


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
    w_height_roof: float = 1.0,
    w_height_terrain: float = 1.0,
    mode: str = "full",             # "full" | "sem2geo" | "geo2sem"
    enable_wall_vertical: bool = True,
    enable_roof_nonwall: bool = True,
    enable_terrain_normal: bool = True,
    enable_terrain_height: bool = True,
    enable_height_roof_side: bool = True,
    enable_height_terrain_side: bool = True,
    terrain_gate_mode: str = "none",
    terrain_gate_conf_min: float = 0.0,
    terrain_gate_mass_min: float = 0.0,
    terrain_gate_entropy_max: float = 1.0,
    terrain_height_reference: str = "fixed",
    terrain_height_quantile: float = 0.5,
    terrain_height_margin: float = 0.0,
    enable_sem_geom_calib: bool = False,
    semcal_classes: str = "roof_wall",
    semcal_tau: float = 0.05,
    semcal_weight_beta: float = 0.0,
    semcal_reliability_gate: str = "conf_entropy",
    semcal_entropy_tau: float = 0.75,
    semcal_entropy_alpha: float = 0.10,
) -> dict:
    """Compute L_mutual with optional gradient mode for diagnostics.

    Returns a dict with the total loss and per-term breakdown.

    Classes (must match dataloader): 0=BG, 1=Roof, 2=Wall, 3=Terrain.
    """
    if mode == "none":
        return _zero_terms(normals.device)

    if terrain_gate_mode not in {"none", "confidence", "class_mass", "mass_entropy"}:
        raise ValueError(
            f"Unsupported terrain_gate_mode={terrain_gate_mode!r}. "
            "Implemented values are 'none', 'confidence', 'class_mass', and 'mass_entropy'."
        )
    if terrain_height_reference not in {"fixed", "terrain_quantile"}:
        raise ValueError(
            f"Unsupported terrain_height_reference={terrain_height_reference!r}. "
            "Implemented values are 'fixed' and 'terrain_quantile'."
        )
    if semcal_classes != "roof_wall":
        raise ValueError(
            f"Unsupported semcal_classes={semcal_classes!r}. "
            "FC-S6E implements only roof_wall semantic calibration."
        )
    if semcal_reliability_gate not in {"none", "confidence", "entropy", "conf_entropy"}:
        raise ValueError(
            f"Unsupported semcal_reliability_gate={semcal_reliability_gate!r}. "
            "Implemented values are 'none', 'confidence', 'entropy', and 'conf_entropy'."
        )

    # Class probabilities
    p = F.softmax(sem_logits, dim=-1)       # (N, 4)
    p_roof = p[:, 1]
    p_wall = p[:, 2]
    p_terrain = p[:, 3]
    terrain_gate = torch.ones_like(p_terrain)
    if terrain_gate_mode == "confidence":
        with torch.no_grad():
            terrain_gate = (p_terrain >= float(terrain_gate_conf_min)).to(p_terrain.dtype)
    elif terrain_gate_mode in {"class_mass", "mass_entropy"}:
        with torch.no_grad():
            entropy = -(p * (p.clamp_min(1e-8).log())).sum(dim=-1)
            entropy = entropy / torch.log(torch.tensor(float(p.shape[-1]), device=p.device))
            terrain_mass = p_terrain.mean()
            terrain_entropy = (p_terrain * entropy).sum() / p_terrain.sum().clamp_min(1e-8)
            gate_value = terrain_mass >= float(terrain_gate_mass_min)
            if terrain_gate_mode == "mass_entropy":
                gate_value = gate_value and terrain_entropy <= float(terrain_gate_entropy_max)
        terrain_gate = torch.full_like(p_terrain, float(gate_value))

    if mode == "sem2geo":
        p_roof = p_roof.detach()
        p_wall = p_wall.detach()
        p_terrain = p_terrain.detach()
        terrain_gate = terrain_gate.detach()

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
    terrain_height_th = torch.tensor(float(height_th), device=height.device, dtype=height.dtype)
    if terrain_height_reference == "terrain_quantile":
        with torch.no_grad():
            weights = (p_terrain * terrain_gate).clamp_min(0)
            total_weight = weights.sum()
            if total_weight > 1e-8 and height.numel() > 0:
                order = torch.argsort(height)
                h_sorted = height[order]
                w_sorted = weights[order]
                cdf = torch.cumsum(w_sorted, dim=0) / total_weight
                q = float(min(max(terrain_height_quantile, 0.0), 1.0))
                q_tensor = torch.tensor(q, device=height.device, dtype=height.dtype)
                idx = torch.searchsorted(cdf, q_tensor).clamp(max=len(h_sorted) - 1)
                terrain_height_th = h_sorted[idx].detach() + float(terrain_height_margin)
    L_h_terrain = F.relu(height - terrain_height_th) ** 2

    # Weighted sum per primitive, mean over all primitives
    loss_vert_raw = (p_wall * L_vert).mean()
    loss_slope_raw = (p_roof * L_slope).mean()
    loss_horiz_raw = (p_terrain * terrain_gate * L_horiz).mean()
    loss_h_roof_raw = (p_roof * L_h_roof).mean()
    loss_h_terrain_raw = (p_terrain * terrain_gate * L_h_terrain).mean()
    loss_height_raw = (p_roof * L_h_roof + p_terrain * terrain_gate * L_h_terrain).mean()

    zero = torch.zeros((), device=normals.device)
    loss_semcal = zero
    semcal_reliability_mean = zero
    semcal_active_frac = zero
    semcal_entropy_mean = zero
    if enable_sem_geom_calib and float(semcal_weight_beta) != 0.0:
        p_rw = p[:, [1, 2]]
        p_rw_norm = p_rw / p_rw.sum(dim=-1, keepdim=True).clamp_min(1e-8)
        with torch.no_grad():
            dot2_teacher = dot.detach() ** 2
            e_wall = dot2_teacher
            e_roof = F.relu(float(tau) - dot2_teacher) ** 2
            tau_geom = max(float(semcal_tau), 1e-8)
            score_roof = torch.exp(-e_roof / tau_geom)
            score_wall = torch.exp(-e_wall / tau_geom)
            s_geom = torch.stack([score_roof, score_wall], dim=-1)
            s_geom = s_geom / s_geom.sum(dim=-1, keepdim=True).clamp_min(1e-8)

            p_rw_teacher = p_rw_norm.detach()
            entropy = -(p_rw_teacher * p_rw_teacher.clamp_min(1e-8).log()).sum(dim=-1)
            entropy = entropy / torch.log(torch.tensor(2.0, device=entropy.device))
            confidence_gate = p[:, [1, 2]].detach().max(dim=-1).values.clamp(0.0, 1.0)
            entropy_gate = torch.sigmoid(
                (float(semcal_entropy_tau) - entropy) / max(float(semcal_entropy_alpha), 1e-8)
            )
            if semcal_reliability_gate == "none":
                reliability = torch.ones_like(confidence_gate)
            elif semcal_reliability_gate == "confidence":
                reliability = confidence_gate
            elif semcal_reliability_gate == "entropy":
                reliability = entropy_gate
            else:
                reliability = confidence_gate * entropy_gate
            reliability = reliability.detach()
            semcal_reliability_mean = reliability.mean().detach()
            semcal_active_frac = (reliability > 0.05).float().mean().detach()
            semcal_entropy_mean = entropy.mean().detach()

        kl = (
            s_geom
            * (s_geom.clamp_min(1e-8).log() - p_rw_norm.clamp_min(1e-8).log())
        ).sum(dim=-1)
        loss_semcal = (reliability * kl).mean()
    loss_vert = loss_vert_raw if enable_wall_vertical else zero
    loss_slope = loss_slope_raw if enable_roof_nonwall else zero
    loss_horiz = loss_horiz_raw if enable_terrain_normal else zero
    loss_h_roof = loss_h_roof_raw if enable_height_roof_side else zero
    loss_h_terrain = (
        loss_h_terrain_raw
        if (enable_terrain_height and enable_height_terrain_side)
        else zero
    )
    legacy_height_path = (
        enable_height_roof_side
        and enable_terrain_height
        and enable_height_terrain_side
        and terrain_height_reference == "fixed"
        and float(w_height_roof) == 1.0
        and float(w_height_terrain) == 1.0
    )
    if legacy_height_path:
        # Preserve the legacy reduction exactly when all height controls are on.
        loss_height = loss_height_raw
    else:
        loss_height = float(w_height_roof) * loss_h_roof + float(w_height_terrain) * loss_h_terrain

    total = (
        w_vert * loss_vert
        + w_slope * loss_slope
        + w_horiz * loss_horiz
        + w_height * loss_height
        + float(semcal_weight_beta) * loss_semcal
    )
    return {
        "total": total,
        "vert": loss_vert.detach(),
        "slope": loss_slope.detach(),
        "horiz": loss_horiz.detach(),
        "height": loss_height.detach(),
        "wall_vertical": loss_vert.detach(),
        "roof_nonwall": loss_slope.detach(),
        "terrain_normal": loss_horiz.detach(),
        # FC-S5 keeps this as the active terrain-side height threshold penalty.
        # Robust terrain compactness is a future loss, not enabled here.
        "terrain_height": loss_h_terrain.detach(),
        "height_roof": loss_h_roof.detach(),
        "height_terrain": loss_h_terrain.detach(),
        "sem_geom_calib": loss_semcal.detach(),
        "sem_geom_reliability": semcal_reliability_mean,
        "sem_geom_active_frac": semcal_active_frac,
        "sem_geom_entropy": semcal_entropy_mean,
        "roof_wall_relation": zero,
        "terrain_wall_relation": zero,
    }
