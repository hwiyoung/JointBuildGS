"""Data-fitting losses: L_photo, L_depth, L_normal, L_nc."""
from __future__ import annotations

import torch
import torch.nn.functional as F


def l1(a: torch.Tensor, b: torch.Tensor, mask: torch.Tensor | None = None) -> torch.Tensor:
    d = (a - b).abs()
    if mask is not None:
        m = mask.to(d.dtype)
        return (d * m).sum() / m.sum().clamp_min(1.0)
    return d.mean()


def ssim(img1: torch.Tensor, img2: torch.Tensor, window_size: int = 11) -> torch.Tensor:
    """Differentiable SSIM. img: (H,W,3) in [0,1]."""
    if img1.ndim == 3:
        img1 = img1.permute(2, 0, 1).unsqueeze(0)
        img2 = img2.permute(2, 0, 1).unsqueeze(0)
    C = img1.shape[1]
    sigma = 1.5
    coords = torch.arange(window_size, dtype=torch.float32, device=img1.device) - window_size // 2
    g = torch.exp(-(coords ** 2) / (2 * sigma ** 2))
    g = (g / g.sum()).reshape(1, 1, -1)
    window = (g.mT * g).reshape(1, 1, window_size, window_size).expand(C, 1, -1, -1)

    mu1 = F.conv2d(img1, window, padding=window_size // 2, groups=C)
    mu2 = F.conv2d(img2, window, padding=window_size // 2, groups=C)
    mu1_sq = mu1 * mu1
    mu2_sq = mu2 * mu2
    mu12 = mu1 * mu2
    sigma1_sq = F.conv2d(img1 * img1, window, padding=window_size // 2, groups=C) - mu1_sq
    sigma2_sq = F.conv2d(img2 * img2, window, padding=window_size // 2, groups=C) - mu2_sq
    sigma12 = F.conv2d(img1 * img2, window, padding=window_size // 2, groups=C) - mu12
    C1, C2 = 0.01 ** 2, 0.03 ** 2
    ssim_map = ((2 * mu12 + C1) * (2 * sigma12 + C2)) / ((mu1_sq + mu2_sq + C1) * (sigma1_sq + sigma2_sq + C2))
    return ssim_map.mean()


def l_photo(rgb_pred: torch.Tensor, rgb_gt: torch.Tensor, lam: float = 0.2) -> torch.Tensor:
    """L_photo = (1-λ)·L1 + λ·(1 - SSIM).  rgb shape: (H,W,3), [0,1]."""
    l1_term = (rgb_pred - rgb_gt).abs().mean()
    s = ssim(rgb_pred.clamp(0, 1), rgb_gt.clamp(0, 1))
    return (1 - lam) * l1_term + lam * (1 - s)


def l_depth(depth_pred: torch.Tensor, depth_gt: torch.Tensor, mask: torch.Tensor) -> torch.Tensor:
    """Masked L1 on positive-depth pixels."""
    return l1(depth_pred, depth_gt, mask=mask)


def l_normal(
    n_pred_world: torch.Tensor,   # (H,W,3) world-frame rendered normal
    n_gt_world: torch.Tensor,     # (H,W,3) world-frame GT normal (dataloader canonicalizes)
    w2c: torch.Tensor,            # (4,4) unused (kept for API compat)
    mask: torch.Tensor,           # (H,W) bool
) -> torch.Tensor:
    """1 - |cos(n_render, n_GT)| in world frame.

    Dataloader returns GT normals already in world frame (converts from camera for COLMAP).
    abs(cos) makes the loss sign-invariant (handles orientation flips).
    """
    n_pred = F.normalize(n_pred_world, dim=-1, eps=1e-6)
    n_gt = F.normalize(n_gt_world, dim=-1, eps=1e-6)
    cos = (n_pred * n_gt).sum(-1)
    err = 1.0 - cos.abs()
    m = mask.to(err.dtype)
    return (err * m).sum() / m.sum().clamp_min(1.0)


def l_nc(n_render: torch.Tensor, n_surf: torch.Tensor, alpha: torch.Tensor | None = None) -> torch.Tensor:
    """Normal-consistency: render-normal vs depth-derived-normal (both world frame).

    Args:
        n_render: (H,W,3)
        n_surf:   (H,W,3) depth-derived
        alpha:    (H,W) optional weighting mask
    """
    nr = F.normalize(n_render, dim=-1, eps=1e-6)
    ns = F.normalize(n_surf, dim=-1, eps=1e-6)
    err = 1.0 - (nr * ns).sum(-1)
    if alpha is not None:
        return (err * alpha).sum() / alpha.sum().clamp_min(1.0)
    return err.mean()
