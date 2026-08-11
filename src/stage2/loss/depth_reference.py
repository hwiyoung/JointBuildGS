"""Reference-derived depth losses used by bounded Stage-2 diagnostics."""
from __future__ import annotations

import torch


def dn_splatter_edge_aware_log_l1(
    depth_pred: torch.Tensor,
    depth_gt: torch.Tensor,
    rgb_gt: torch.Tensor,
    mask: torch.Tensor,
    *,
    depth_tolerance: float = 0.1,
) -> torch.Tensor:
    """DN-Splatter EdgeAwareLogL1 for HxW depth and HxWx3 RGB.

    The reduction follows the pinned DN-Splatter implementation: horizontal
    and vertical terms are reduced independently, and an RGB edge attenuates
    the depth residual at the pixel on the low-index side of that edge.
    """

    if depth_pred.shape != depth_gt.shape or depth_pred.ndim != 2:
        raise ValueError("DN depth tensors must be same-shape HxW")
    if rgb_gt.shape != (*depth_gt.shape, 3):
        raise ValueError("DN RGB tensor must be HxWx3 and depth-aligned")
    if mask.dtype != torch.bool or mask.shape != depth_gt.shape:
        raise ValueError("DN mask must be bool HxW and depth-aligned")
    if depth_gt.shape[0] < 2 or depth_gt.shape[1] < 2:
        raise ValueError("DN EdgeAwareLogL1 requires H,W >= 2")

    valid = mask & torch.isfinite(depth_gt) & (depth_gt > depth_tolerance)
    valid &= torch.isfinite(depth_pred)
    valid_x = valid[:, :-1]
    valid_y = valid[:-1, :]
    if not bool(valid_x.any().item()) or not bool(valid_y.any().item()):
        raise ValueError("DN EdgeAwareLogL1 has no valid x/y support")

    log_l1 = torch.log1p(torch.abs(depth_pred - depth_gt))
    rgb_grad_x = torch.mean(torch.abs(rgb_gt[:, :-1] - rgb_gt[:, 1:]), dim=-1)
    rgb_grad_y = torch.mean(torch.abs(rgb_gt[:-1, :] - rgb_gt[1:, :]), dim=-1)
    loss_x = torch.exp(-rgb_grad_x) * log_l1[:, :-1]
    loss_y = torch.exp(-rgb_grad_y) * log_l1[:-1, :]
    return loss_x[valid_x].mean() + loss_y[valid_y].mean()
