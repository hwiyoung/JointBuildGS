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


def _ssim_window(
    channels: int,
    *,
    window_size: int,
    dtype: torch.dtype,
    device: torch.device,
) -> torch.Tensor:
    """Return the historical normalized Gaussian SSIM window."""

    sigma = 1.5
    coords = (
        torch.arange(window_size, dtype=dtype, device=device)
        - window_size // 2
    )
    g = torch.exp(-(coords**2) / (2 * sigma**2))
    g = (g / g.sum()).reshape(1, 1, -1)
    return (g.mT * g).reshape(1, 1, window_size, window_size).expand(
        channels, 1, -1, -1
    )


def ssim(img1: torch.Tensor, img2: torch.Tensor, window_size: int = 11) -> torch.Tensor:
    """Differentiable SSIM. img: (H,W,3) in [0,1]."""
    if img1.ndim == 3:
        img1 = img1.permute(2, 0, 1).unsqueeze(0)
        img2 = img2.permute(2, 0, 1).unsqueeze(0)
    C = img1.shape[1]
    window = _ssim_window(
        C,
        window_size=window_size,
        dtype=img1.dtype,
        device=img1.device,
    )

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


def masked_ssim(
    img1: torch.Tensor,
    img2: torch.Tensor,
    mask: torch.Tensor,
    window_size: int = 11,
) -> torch.Tensor:
    """SSIM whose value and gradient are independent of pixels outside ``mask``.

    Local moments are normalized by the Gaussian-weighted valid support and
    only mask-centred windows enter the final mean.  Multiplying every moment
    input by the binary support before convolution is essential: merely
    masking a conventional SSIM map would still let neighbouring outside
    pixels influence the selected windows and their gradients.
    """

    if img1.shape != img2.shape or img1.ndim != 3 or img1.shape[-1] != 3:
        raise ValueError("masked_ssim expects same-shape HxWx3 RGB tensors")
    if mask.dtype != torch.bool or mask.shape != img1.shape[:2]:
        raise ValueError("masked_ssim mask must be bool HxW aligned with RGB")
    if not bool(mask.any().item()):
        raise ValueError("masked_ssim forbids an empty mask")
    if window_size < 1 or window_size % 2 == 0:
        raise ValueError("SSIM window_size must be a positive odd integer")

    value1 = img1.permute(2, 0, 1).unsqueeze(0)
    value2 = img2.permute(2, 0, 1).unsqueeze(0)
    channels = int(value1.shape[1])
    support = mask.to(device=img1.device, dtype=img1.dtype)[None, None]
    support_channels = support.expand(1, channels, -1, -1)
    window = _ssim_window(
        channels,
        window_size=window_size,
        dtype=img1.dtype,
        device=img1.device,
    )
    padding = window_size // 2
    weighted_support = F.conv2d(
        support_channels,
        window,
        padding=padding,
        groups=channels,
    )
    denominator = weighted_support.clamp_min(torch.finfo(img1.dtype).eps)

    def moment(value: torch.Tensor) -> torch.Tensor:
        return F.conv2d(
            value * support_channels,
            window,
            padding=padding,
            groups=channels,
        ) / denominator

    mu1 = moment(value1)
    mu2 = moment(value2)
    mu1_sq = mu1.square()
    mu2_sq = mu2.square()
    mu12 = mu1 * mu2
    sigma1_sq = moment(value1.square()) - mu1_sq
    sigma2_sq = moment(value2.square()) - mu2_sq
    sigma12 = moment(value1 * value2) - mu12
    C1, C2 = 0.01**2, 0.03**2
    ssim_map = ((2 * mu12 + C1) * (2 * sigma12 + C2)) / (
        (mu1_sq + mu2_sq + C1) * (sigma1_sq + sigma2_sq + C2)
    )
    selected = support_channels.to(torch.bool)
    return ssim_map[selected].mean()


def l_photo(
    rgb_pred: torch.Tensor,
    rgb_gt: torch.Tensor,
    lam: float = 0.2,
    mask: torch.Tensor | None = None,
) -> torch.Tensor:
    """L_photo = (1-λ)·L1 + λ·(1 - SSIM), optionally footprint-masked."""

    if mask is None:
        l1_term = (rgb_pred - rgb_gt).abs().mean()
        s = ssim(rgb_pred.clamp(0, 1), rgb_gt.clamp(0, 1))
    else:
        if rgb_pred.shape != rgb_gt.shape or rgb_pred.ndim != 3:
            raise ValueError("masked photo loss expects same-shape HxWxC tensors")
        if mask.dtype != torch.bool or mask.shape != rgb_pred.shape[:2]:
            raise ValueError("photo mask must be bool HxW aligned with RGB")
        selected = mask[..., None].expand_as(rgb_pred)
        if not bool(selected.any().item()):
            raise ValueError("masked photo loss forbids an empty mask")
        l1_term = (rgb_pred - rgb_gt).abs()[selected].mean()
        s = masked_ssim(
            rgb_pred.clamp(0, 1),
            rgb_gt.clamp(0, 1),
            mask,
        )
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


def l_normal_target_regions(
    n_pred_world: torch.Tensor,
    n_target_world: torch.Tensor,
    region_ids: torch.Tensor,
    valid_mask: torch.Tensor,
    *,
    min_pixels: int = 64,
) -> tuple[torch.Tensor, dict]:
    """Equal-per-region monocular-normal loss on oracle-addressed target roofs."""

    if n_pred_world.shape != n_target_world.shape or n_pred_world.ndim != 3:
        raise ValueError("normal tensors must be same-shape HxWx3")
    if region_ids.shape != n_pred_world.shape[:2] or valid_mask.shape != region_ids.shape:
        raise ValueError("region_ids/valid_mask must match normal HxW")
    if min_pixels < 1:
        raise ValueError("min_pixels must be positive")
    nr = F.normalize(n_pred_world, dim=-1, eps=1e-6)
    nt = F.normalize(n_target_world, dim=-1, eps=1e-6)
    err = 1.0 - (nr * nt).sum(-1).abs()
    valid = valid_mask.bool() & torch.isfinite(err)
    losses = []
    rows = {}
    for rid_tensor in torch.unique(region_ids[(region_ids > 0) & valid]):
        rid = int(rid_tensor.detach().cpu().item())
        mask = valid & (region_ids == rid_tensor)
        count = int(mask.sum().detach().cpu().item())
        row = {"valid_pixel_count": count, "status": "active"}
        rows[rid] = row
        if count >= int(min_pixels):
            region_loss = err[mask].mean()
            row["mean_one_minus_abs_cos"] = float(
                region_loss.detach().cpu().item()
            )
            losses.append(region_loss)
        else:
            row["status"] = "skipped_lt_min_pixels"
    zero = torch.where(
        torch.isfinite(n_pred_world), n_pred_world, torch.zeros_like(n_pred_world)
    ).sum() * 0.0
    loss = torch.stack(losses).mean() if losses else zero
    return loss, {
        "eligible_region_count": len(losses),
        "per_region": rows,
        "aggregate": "mean_of_per_region_means",
        "min_pixels": int(min_pixels),
    }


def l_mono_depth_ssi(
    depth_pred: torch.Tensor,
    mono_depth: torch.Tensor,
    region_ids: torch.Tensor,
    valid_mask: torch.Tensor,
    *,
    min_pixels: int = 64,
    variance_epsilon: float = 1e-12,
) -> tuple[torch.Tensor, dict]:
    """Affine scale-and-shift invariant depth loss on target address regions.

    For each region, solve ``s,t = argmin ||s*mono+t-rendered||^2`` and take
    the mean absolute residual.  Regions are then equally averaged so a large
    roof cannot dominate a small one.  Empty, <64-pixel, or constant-mono
    regions return a graph-connected zero and never leak gradient outside the
    selected address mask.
    """

    if not (
        depth_pred.ndim == mono_depth.ndim == region_ids.ndim == valid_mask.ndim == 2
        and depth_pred.shape == mono_depth.shape == region_ids.shape == valid_mask.shape
    ):
        raise ValueError("depth, mono_depth, region_ids, and valid_mask must be same-shape HxW")
    if min_pixels < 1:
        raise ValueError("min_pixels must be positive")
    valid = (
        valid_mask.bool()
        & (region_ids > 0)
        & torch.isfinite(depth_pred)
        & torch.isfinite(mono_depth)
        & (mono_depth > 0)
    )
    losses = []
    rows = {}
    for rid_tensor in torch.unique(region_ids[valid]):
        rid = int(rid_tensor.detach().cpu().item())
        mask = valid & (region_ids == rid_tensor)
        count = int(mask.sum().detach().cpu().item())
        row = {"valid_pixel_count": count, "status": "active"}
        rows[rid] = row
        if count < int(min_pixels):
            row["status"] = "skipped_lt_min_pixels"
            continue
        x = mono_depth[mask]
        y = depth_pred[mask]
        x_mean = x.mean()
        y_mean = y.mean()
        x_centered = x - x_mean
        denominator = x_centered.square().sum()
        row["mono_variance_sum"] = float(denominator.detach().cpu().item())
        if not bool(torch.isfinite(denominator).item()) or float(
            denominator.detach().cpu().item()
        ) <= variance_epsilon:
            row["status"] = "skipped_degenerate_constant_mono"
            continue
        scale = (x_centered * (y - y_mean)).sum() / denominator
        shift = y_mean - scale * x_mean
        residual = scale * x + shift - y
        region_loss = residual.abs().mean()
        if not bool(torch.isfinite(region_loss).item()):
            row["status"] = "skipped_nonfinite_fit"
            continue
        row["scale"] = float(scale.detach().cpu().item())
        row["shift"] = float(shift.detach().cpu().item())
        row["mean_abs_residual"] = float(region_loss.detach().cpu().item())
        losses.append(region_loss)
    zero = torch.where(
        torch.isfinite(depth_pred), depth_pred, torch.zeros_like(depth_pred)
    ).sum() * 0.0
    loss = torch.stack(losses).mean() if losses else zero
    return loss, {
        "eligible_region_count": len(losses),
        "per_region": rows,
        "fit": "least_squares s*mono+t to rendered depth",
        "residual": "mean_absolute",
        "aggregate": "mean_of_per_region_means",
        "min_pixels": int(min_pixels),
    }


def l_sem(
    sem_pred: torch.Tensor,       # (H, W, K) raw logits
    sem_gt: torch.Tensor,         # (H, W) int64 labels
    ignore_index: int = 0,
) -> torch.Tensor:
    """CrossEntropy with ignore_index. sem_gt values outside [0, K-1] are ignored."""
    H, W, K = sem_pred.shape
    logits = sem_pred.reshape(-1, K)      # (H*W, K)
    labels = sem_gt.reshape(-1).long()    # (H*W,)
    return F.cross_entropy(logits, labels, ignore_index=ignore_index)


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
