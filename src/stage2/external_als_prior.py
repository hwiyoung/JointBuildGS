"""Confidence-gated Existing-ALS losses for the bounded C4 technical run."""
from __future__ import annotations

from typing import Any

import torch


def current_consistency_attenuation(residual_m: torch.Tensor, conflict_scale_m: float) -> torch.Tensor:
    """Return a detached confidence multiplier that only lowers ALS influence."""
    if conflict_scale_m <= 0:
        raise ValueError("conflict_scale_m must be positive")
    if not torch.isfinite(residual_m).all():
        raise ValueError("current-consistency residual must be finite")
    return torch.exp(-torch.clamp(residual_m, min=0.0) / float(conflict_scale_m)).detach()


def _als_denominator(weight: torch.Tensor, count: int, normalization: str) -> torch.Tensor:
    """Legacy confidence_sum renormalizes uniform attenuation away; valid_pixel_count keeps it absolute."""
    if normalization == "confidence_sum":
        return weight.sum().clamp_min(torch.finfo(weight.dtype).eps)
    if normalization == "valid_pixel_count":
        return torch.tensor(float(count), dtype=weight.dtype, device=weight.device)
    raise ValueError("external ALS normalization must be confidence_sum|valid_pixel_count")


def robust_als_depth_loss(
    rendered_depth: torch.Tensor,
    prior_depth: torch.Tensor,
    confidence: torch.Tensor,
    mask: torch.Tensor,
    *,
    huber_delta_m: float,
    normalization: str = "confidence_sum",
) -> tuple[torch.Tensor, dict[str, Any]]:
    """Confidence-weighted Huber loss in metric camera depth."""
    if huber_delta_m <= 0:
        raise ValueError("huber_delta_m must be positive")
    if not (rendered_depth.shape == prior_depth.shape == confidence.shape == mask.shape and rendered_depth.ndim == 2):
        raise ValueError("ALS depth tensors must be same-shape HxW")
    if mask.dtype != torch.bool:
        raise ValueError("ALS depth mask must be bool")
    valid = mask & torch.isfinite(rendered_depth) & torch.isfinite(prior_depth) & torch.isfinite(confidence) & (prior_depth > 0) & (confidence > 0)
    count = int(valid.sum().detach().cpu().item())
    if count == 0:
        return rendered_depth.sum() * 0.0, {"valid_pixel_count": 0, "confidence_sum": 0.0}
    residual = (rendered_depth[valid] - prior_depth[valid]).abs()
    delta = float(huber_delta_m)
    huber = torch.where(residual <= delta, 0.5 * residual.square() / delta, residual - 0.5 * delta)
    weight = confidence[valid].clamp(0.0, 1.0)
    loss = (weight * huber).sum() / _als_denominator(weight, count, normalization)
    return loss, {"valid_pixel_count": count, "confidence_sum": float(weight.detach().sum().cpu().item())}


def sign_invariant_als_normal_loss(
    rendered_normal: torch.Tensor,
    prior_normal: torch.Tensor,
    confidence: torch.Tensor,
    mask: torch.Tensor,
    *,
    normalization: str = "confidence_sum",
) -> tuple[torch.Tensor, dict[str, Any]]:
    """Confidence-weighted 1-|dot| loss; normal sign is intentionally ignored."""
    if not (rendered_normal.shape == prior_normal.shape and rendered_normal.ndim == 3 and rendered_normal.shape[-1] == 3):
        raise ValueError("ALS normals must be same-shape HxWx3")
    if confidence.shape != mask.shape or mask.shape != rendered_normal.shape[:2] or mask.dtype != torch.bool:
        raise ValueError("ALS normal confidence/mask must be HxW and mask bool")
    rendered_norm = torch.linalg.vector_norm(rendered_normal, dim=-1)
    prior_norm = torch.linalg.vector_norm(prior_normal, dim=-1)
    valid = mask & torch.isfinite(rendered_normal).all(dim=-1) & torch.isfinite(prior_normal).all(dim=-1) & torch.isfinite(confidence) & (prior_norm > 1.0e-6) & (confidence > 0)
    count = int(valid.sum().detach().cpu().item())
    if count == 0:
        return rendered_normal.sum() * 0.0, {"valid_pixel_count": 0, "confidence_sum": 0.0}
    predicted = torch.nn.functional.normalize(rendered_normal[valid], dim=-1, eps=1.0e-6)
    prior = prior_normal[valid] / prior_norm[valid][:, None]
    weight = confidence[valid].clamp(0.0, 1.0)
    loss = (weight * (1.0 - torch.abs((predicted * prior).sum(dim=-1)))).sum() / _als_denominator(weight, count, normalization)
    return loss, {"valid_pixel_count": count, "confidence_sum": float(weight.detach().sum().cpu().item())}


def combine_confidence_gates(
    registration: torch.Tensor,
    density: torch.Tensor,
    planarity: torch.Tensor,
    visibility: torch.Tensor,
    current_consistency: torch.Tensor,
) -> torch.Tensor:
    """Multiply the five frozen [0,1] gates; no component can raise another."""
    shapes = {tuple(value.shape) for value in (registration, density, planarity, visibility, current_consistency)}
    if len(shapes) != 1:
        raise ValueError("all ALS confidence gates must have identical shapes")
    values = (registration, density, planarity, visibility, current_consistency)
    if any(not torch.isfinite(value).all() for value in values):
        raise ValueError("ALS confidence gates must be finite")
    return torch.stack([value.clamp(0.0, 1.0) for value in values], dim=0).prod(dim=0)
