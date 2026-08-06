"""Existing-LoD2 plane supervision for the E6 diagnostic arm."""
from __future__ import annotations

from typing import Any

import torch


def lod_plane_loss(
    rendered_depth: torch.Tensor,
    rendered_normal_camera: torch.Tensor,
    plane_point_camera: torch.Tensor,
    plane_normal_camera: torch.Tensor,
    plane_kind: torch.Tensor,
    building_weight: torch.Tensor,
    mask: torch.Tensor,
    K: torch.Tensor,
    *,
    wall_weight: float,
    roof_weight: float,
    max_distance_m: float,
    max_angle_deg: float,
) -> tuple[torch.Tensor, dict[str, Any]]:
    """Evaluate weighted point-to-plane distance after frozen distance/angle gates."""
    height, width = rendered_depth.shape
    expected_hw = (height, width)
    if rendered_normal_camera.shape != (height, width, 3):
        raise ValueError("rendered LoD normal must be HxWx3")
    if plane_point_camera.shape != plane_normal_camera.shape or plane_point_camera.shape != (height, width, 3):
        raise ValueError("LoD plane point/normal must be same-shape HxWx3")
    if any(value.shape != expected_hw for value in (plane_kind, building_weight, mask)):
        raise ValueError("LoD kind/weight/mask must be HxW")
    if mask.dtype != torch.bool or K.shape != (3, 3):
        raise ValueError("LoD mask must be bool and K must be 3x3")
    if wall_weight < 0 or roof_weight < 0 or max_distance_m <= 0 or not 0 < max_angle_deg < 90:
        raise ValueError("invalid LoD plane loss parameters")

    yy, xx = torch.meshgrid(
        torch.arange(height, device=rendered_depth.device, dtype=rendered_depth.dtype),
        torch.arange(width, device=rendered_depth.device, dtype=rendered_depth.dtype),
        indexing="ij",
    )
    pixels = torch.stack((xx, yy, torch.ones_like(xx)), dim=-1)
    rays = torch.matmul(pixels, torch.linalg.inv(K).T)
    points = rays * rendered_depth[..., None]
    plane_norm = torch.nn.functional.normalize(plane_normal_camera, dim=-1, eps=1.0e-6)
    rendered_norm = torch.nn.functional.normalize(rendered_normal_camera, dim=-1, eps=1.0e-6)
    distance = torch.abs(((points - plane_point_camera) * plane_norm).sum(dim=-1))
    cosine = torch.abs((rendered_norm * plane_norm).sum(dim=-1)).clamp(0.0, 1.0)
    cosine_threshold = torch.cos(
        torch.tensor(max_angle_deg, device=cosine.device, dtype=cosine.dtype)
        * torch.pi
        / 180.0
    )
    finite = (
        torch.isfinite(rendered_depth)
        & torch.isfinite(rendered_normal_camera).all(dim=-1)
        & torch.isfinite(plane_point_camera).all(dim=-1)
        & torch.isfinite(plane_normal_camera).all(dim=-1)
        & torch.isfinite(building_weight)
    )
    valid = (
        mask
        & finite
        & (rendered_depth > 0)
        & ((plane_kind == 1) | (plane_kind == 2))
        & (distance < max_distance_m)
        & (cosine >= cosine_threshold)
    )
    count = int(valid.sum().detach().cpu().item())
    if count == 0:
        return rendered_depth.sum() * 0.0, {
            "valid_pixel_count": 0,
            "wall_pixel_count": 0,
            "roof_pixel_count": 0,
            "weight_sum": 0.0,
        }
    kind_weight = torch.where(
        plane_kind == 1,
        torch.as_tensor(wall_weight, device=distance.device, dtype=distance.dtype),
        torch.as_tensor(roof_weight, device=distance.device, dtype=distance.dtype),
    )
    weight = kind_weight * building_weight.clamp(0.0, 1.0)
    selected_weight = weight[valid]
    loss = (selected_weight * distance[valid]).sum() / selected_weight.sum().clamp_min(
        torch.finfo(selected_weight.dtype).eps
    )
    return loss, {
        "valid_pixel_count": count,
        "wall_pixel_count": int((valid & (plane_kind == 1)).sum().detach().cpu().item()),
        "roof_pixel_count": int((valid & (plane_kind == 2)).sum().detach().cpu().item()),
        "weight_sum": float(selected_weight.detach().sum().cpu().item()),
    }
