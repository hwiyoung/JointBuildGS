"""gsplat 2DGS renderer wrapper.

Thin wrapper around gsplat.rasterization_2dgs that packages RGB + depth + normal.

gsplat 1.4 rasterization_2dgs returns:
    (render_colors, render_alphas, render_normals, render_normals_from_depth,
     render_distort, render_median, meta)

- render_normals: (C,H,W,3) already world-frame (gsplat applies inv(viewmat) @ R.T)
- render_normals_from_depth: (H,W,3) after .squeeze(0) inside gsplat, or None
"""
from __future__ import annotations

import os
from typing import Dict

import torch
import torch.nn.functional as F
from gsplat import rasterization_2dgs

from .model import GaussianModel2D


def _backgrounds_for_render(
    bg_color: torch.Tensor | None,
    render_mode: str,
) -> torch.Tensor | None:
    """Match gsplat's background channels after it appends rendered depth.

    gsplat 1.5 appends depth to the RGB feature tensor for ``RGB+D`` and
    ``RGB+ED`` but does not append the corresponding zero-valued background
    channel.  Supplying an ordinary RGB background would therefore reach the
    CUDA wrapper as ``(1, 3)`` against four rendered channels.  Keep the
    wrapper contract explicit here so RGB stays white while empty depth stays
    zero.
    """
    if bg_color is None:
        return None
    if bg_color.ndim != 1:
        raise ValueError(f"bg_color must be one-dimensional, got {tuple(bg_color.shape)}")
    if render_mode in {"RGB+D", "RGB+ED"}:
        depth_background = torch.zeros(
            1,
            device=bg_color.device,
            dtype=bg_color.dtype,
        )
        bg_color = torch.cat((bg_color, depth_background))
    elif render_mode in {"D", "ED"}:
        bg_color = torch.zeros(1, device=bg_color.device, dtype=bg_color.dtype)
    return bg_color.unsqueeze(0)


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
    surface_normal_depth_mode: str = "gsplat_expected",
) -> Dict[str, torch.Tensor]:
    if surface_normal_depth_mode not in {
        "gsplat_expected",
        "surface_intersection_expected",
    }:
        raise ValueError(
            "surface_normal_depth_mode must be "
            "gsplat_expected|surface_intersection_expected"
        )
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
        backgrounds=_backgrounds_for_render(bg_color, render_mode),
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

    surface_intersection_depth = None
    surface_intersection_hit = None
    if os.environ.get("JBGS_GSPLAT_MEDIAN_IS_SURFACE_SUM") == "1":
        # The experiment-only gsplat overlay repurposes render_median as the
        # unnormalised sum of alpha-compositing weights times the exact
        # perspective-correct ray--surfel intersection Z.  Dividing by the
        # unchanged accumulated alpha yields the expected surface-hit depth.
        # RGB, historical expected depth, alpha, distortion, normals, and
        # densification metadata remain byte-for-byte on the legacy path.
        surface_sum = render_median[0, ..., 0]
        alpha = render_alphas[0, ..., 0]
        surface_intersection_depth = surface_sum / alpha.clamp(min=1e-10)
        surface_intersection_hit = (
            (alpha > 1e-6)
            & torch.isfinite(surface_intersection_depth)
            & (surface_intersection_depth > near_plane)
            & (surface_intersection_depth < far_plane)
        )

    if surface_normal_depth_mode == "surface_intersection_expected":
        if surface_intersection_depth is None or surface_intersection_hit is None:
            raise RuntimeError(
                "surface_intersection_expected requires the audited "
                "JBGS_GSPLAT_MEDIAN_IS_SURFACE_SUM rasterizer overlay"
            )
        n_surf = _depth_to_normal(surface_intersection_depth, K, viewmat)
    # surf_normals from gsplat can be None or wrong shape; compute ourselves if needed
    elif surf_normals is None or surf_normals.ndim != 3 or surf_normals.shape[0] != height:
        n_surf = _depth_to_normal(depth, K, viewmat)
    else:
        n_surf = surf_normals

    result = {
        "rgb": rgb,
        "depth": depth,
        "alpha": render_alphas[0, ..., 0],
        "normal_render": n_render,
        "normal_surf": n_surf,
        "distort": render_distort[0, ..., 0] if render_distort is not None else torch.zeros(height, width, device=device),
        "depth_median": render_median[0, ..., 0] if render_median is not None else depth,
        "meta": meta,
    }
    if surface_intersection_depth is not None:
        result["depth_surface_intersection"] = surface_intersection_depth
        result["depth_surface_intersection_hit"] = surface_intersection_hit
    return result


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

    # Pad the last column/row explicitly.  ``torch.nn.functional.pad`` does
    # not support replicate mode with a six-value pad tuple on an unbatched
    # HxWxC tensor in the pinned PyTorch build.
    n_cam = torch.cat((n_cam, n_cam[:, -1:, :]), dim=1)
    n_cam = torch.cat((n_cam, n_cam[-1:, :, :]), dim=0)

    # camera -> world
    c2w_rot = torch.linalg.inv(w2c[:3, :3])
    n_world = n_cam @ c2w_rot.T
    return n_world
