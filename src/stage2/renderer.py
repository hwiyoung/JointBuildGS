"""gsplat 2DGS renderer wrapper.

Thin wrapper around gsplat.rasterization_2dgs that packages RGB + depth + normal.

gsplat 1.4 rasterization_2dgs returns:
    (render_colors, render_alphas, render_normals, render_normals_from_depth,
     render_distort, render_median, meta)

- render_normals: (C,H,W,3) already world-frame (gsplat applies inv(viewmat) @ R.T)
- render_normals_from_depth: (H,W,3) after .squeeze(0) inside gsplat, or None
"""
from __future__ import annotations

from typing import Dict

import torch
import torch.nn.functional as F
from gsplat import rasterization_2dgs

from .model import GaussianModel2D


def render(
    model: GaussianModel2D,
    viewmat: torch.Tensor,  # (4,4) world->cam
    K: torch.Tensor,        # (3,3)
    width: int,
    height: int,
    sh_degree: int | None = None,
    render_mode: str = "RGB+ED",
    near_plane: float = 0.01,
    far_plane: float = 1e10,
    bg_color: torch.Tensor | None = None,
    depth_mode: str = "expected",
) -> Dict[str, torch.Tensor]:
    device = model.means.device
    viewmats = viewmat.unsqueeze(0).to(device)  # (1,4,4)
    Ks = K.unsqueeze(0).to(device)              # (1,3,3)

    colors = model.colors_sh()  # (N, K, 3)
    if sh_degree is None:
        sh_degree = model.active_sh_degree

    out = rasterization_2dgs(
        means=model.means,
        quats=model.quats,
        scales=model.scales,
        opacities=model.opacities,
        colors=colors,
        viewmats=viewmats,
        Ks=Ks,
        width=width,
        height=height,
        near_plane=near_plane,
        far_plane=far_plane,
        render_mode=render_mode,
        depth_mode=depth_mode,
        sh_degree=sh_degree,
        backgrounds=bg_color.unsqueeze(0) if bg_color is not None else None,
    )

    render_colors = out[0]       # (1, H, W, 3+1)
    render_alphas = out[1]       # (1, H, W, 1)
    render_normals = out[2]      # (1, H, W, 3) — already world-frame
    surf_normals = out[3]        # (H, W, 3) or None — depth-derived, world-frame
    render_distort = out[4]      # (1, H, W, 1)
    render_median = out[5]       # (1, H, W, 1)
    meta = out[-1]

    if render_mode.endswith("+ED") or render_mode.endswith("+D"):
        rgb = render_colors[0, ..., :3]
        depth = render_colors[0, ..., 3]
    else:
        rgb = render_colors[0]
        depth = torch.zeros(height, width, device=device)

    n_render = render_normals[0]  # (H, W, 3) world-frame

    # surf_normals from gsplat can be None or wrong shape; compute ourselves if needed
    if surf_normals is None or surf_normals.ndim != 3 or surf_normals.shape[0] != height:
        n_surf = _depth_to_normal(depth, K, viewmat)
    else:
        n_surf = surf_normals

    return {
        "rgb": rgb,
        "depth": depth,
        "alpha": render_alphas[0, ..., 0],
        "normal_render": n_render,
        "normal_surf": n_surf,
        "distort": render_distort[0, ..., 0] if render_distort is not None else torch.zeros(height, width, device=device),
        "depth_median": render_median[0, ..., 0] if render_median is not None else depth,
        "meta": meta,
    }


def render_semantic(
    model: GaussianModel2D,
    viewmat: torch.Tensor,
    K: torch.Tensor,
    width: int,
    height: int,
    near_plane: float = 0.01,
    far_plane: float = 1e10,
    sem_detach_geometry: bool = True,
) -> torch.Tensor:
    """Render per-pixel semantic logits by alpha-compositing model.sem_logits.

    Gradient isolation (default, sem_detach_geometry=True): geometry params
    (means, quats, scales, opacities, SH) are detached inside this function, so
    L_sem's gradient flows ONLY back through model.sem_logits. This keeps L_sem
    from corrupting geometry optimization.

    P2 impl ② "depth coupling" sets sem_detach_geometry=False: geometry is NOT
    detached, so L_sem's gradient also flows into means/quats/scales/opacities —
    semantics can then move geometry (the carved seed columns toward the labelled
    roof). Default stays True so the existing configs are unaffected.

    Returns:
        (H, W, K) float — raw logits (not softmaxed).
    """
    device = model.means.device
    viewmats = viewmat.unsqueeze(0).to(device)
    Ks = K.unsqueeze(0).to(device)

    # Geometry: detached (gradient isolation) unless impl ② releases it.
    if sem_detach_geometry:
        means = model.means.detach()
        quats = model.quats.detach()
        scales = model.scales.detach()
        opacities = model.opacities.detach()
    else:
        means = model.means
        quats = model.quats
        scales = model.scales
        opacities = model.opacities
    # gsplat 1.5 expects non-SH feature colors to carry the camera batch
    # dimension, i.e. (C, N, D), even for a single view.
    colors_feat = model.sem_logits.unsqueeze(0) if model.sem_logits.ndim == 2 else model.sem_logits

    out = rasterization_2dgs(
        means=means, quats=quats, scales=scales, opacities=opacities,
        colors=colors_feat,
        viewmats=viewmats, Ks=Ks,
        width=width, height=height,
        near_plane=near_plane, far_plane=far_plane,
        render_mode="RGB",  # just feature alpha blending
        sh_degree=None,
    )
    render_feat = out[0][0]  # (H, W, K)
    return render_feat


def _depth_to_normal(
    depth: torch.Tensor,  # (H, W)
    K: torch.Tensor,      # (3, 3)
    w2c: torch.Tensor,    # (4, 4)
) -> torch.Tensor:
    """Compute world-frame normals from rendered depth via finite differences."""
    H, W = depth.shape
    device = depth.device
    fx, fy = K[0, 0], K[1, 1]
    cx, cy = K[0, 2], K[1, 2]

    v, u = torch.meshgrid(
        torch.arange(H, device=device, dtype=torch.float32),
        torch.arange(W, device=device, dtype=torch.float32),
        indexing="ij",
    )
    z = depth
    x = (u - cx) / fx * z
    y = (v - cy) / fy * z
    pts_cam = torch.stack([x, y, z], dim=-1)  # (H, W, 3)

    dx = pts_cam[:, 1:, :] - pts_cam[:, :-1, :]   # (H, W-1, 3)
    dy = pts_cam[1:, :, :] - pts_cam[:-1, :, :]   # (H-1, W, 3)
    n_cam = torch.cross(dx[:-1, :, :], dy[:, :-1, :], dim=-1)  # (H-1, W-1, 3)
    n_cam = F.normalize(n_cam, dim=-1, eps=1e-6)

    # pad to (H, W, 3)
    n_cam = F.pad(n_cam, (0, 0, 0, 1, 0, 1), mode="replicate")

    # camera -> world
    c2w_rot = torch.linalg.inv(w2c[:3, :3])
    n_world = n_cam @ c2w_rot.T
    return n_world
