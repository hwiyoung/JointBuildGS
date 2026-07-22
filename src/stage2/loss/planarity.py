"""Rendered-depth plane regularizers for the quality-axis pilot.

The functions in this module are deliberately independent from the Stage 2
training loop.  They operate on rendered depth in camera coordinates and fit
their supervising planes from detached points, so gradients only move the
rendered depth toward the fitted plane.

``local_rendered_depth_coplanarity`` is the segmentation-free PGSR-style
``soft`` arm.  "Global" application means that the same local rule is applied
throughout the valid image; it never means fitting one plane to a whole scene.

``region_rendered_depth_coplanarity`` is the common ``medium`` primitive used
by the controlled vision-mask / GT-mask pair.  The caller supplies either an
integer region map or non-overlapping boolean region masks.

2DGS already fixes the out-of-plane thickness.  The accompanying flattening
function is therefore an audit only and intentionally cannot contribute a loss.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import math
from typing import Any, Mapping

import torch
import torch.nn.functional as F


@dataclass(frozen=True)
class PlanarityOutput:
    """Loss plus detached bookkeeping for one rendered view."""

    loss: torch.Tensor
    plane_count: int
    point_count: int
    diagnostics: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class FlatteningInvariantAudit:
    """Audit result for the fixed 2DGS out-of-plane thickness.

    ``contributes_to_loss`` is permanently false.  In particular, callers must
    not put this invariant in the ``plane`` loss or its loss-share numerator.
    """

    passed: bool
    expected_thickness: float
    max_abs_error: float
    finite_count: int
    total_count: int
    contributes_to_loss: bool = False


def _graph_zero(value: torch.Tensor) -> torch.Tensor:
    finite = torch.where(torch.isfinite(value), value, torch.zeros_like(value))
    return finite.sum() * 0.0


def _validate_depth_and_intrinsics(
    depth: torch.Tensor,
    intrinsics: torch.Tensor,
) -> tuple[int, int, torch.Tensor]:
    if depth.ndim != 2:
        raise ValueError(f"depth must have shape (H,W), got {tuple(depth.shape)}")
    if not depth.is_floating_point():
        raise TypeError("depth must be a floating-point tensor")
    if intrinsics.shape != (3, 3):
        raise ValueError(
            f"intrinsics must have shape (3,3), got {tuple(intrinsics.shape)}"
        )
    K = intrinsics.to(device=depth.device, dtype=depth.dtype)
    if not bool(torch.isfinite(K).all()):
        raise ValueError("intrinsics must be finite")
    if float(K[0, 0].detach()) <= 0.0 or float(K[1, 1].detach()) <= 0.0:
        raise ValueError("intrinsics focal lengths must be positive")
    return int(depth.shape[0]), int(depth.shape[1]), K


def _valid_pixels(
    depth: torch.Tensor,
    *,
    alpha: torch.Tensor | None,
    valid_mask: torch.Tensor | None,
    alpha_threshold: float,
) -> torch.Tensor:
    valid = torch.isfinite(depth) & (depth > 0)
    if alpha is not None:
        if alpha.shape != depth.shape:
            raise ValueError("alpha must have the same (H,W) shape as depth")
        valid = valid & torch.isfinite(alpha) & (alpha >= float(alpha_threshold))
    if valid_mask is not None:
        if valid_mask.shape != depth.shape:
            raise ValueError("valid_mask must have the same (H,W) shape as depth")
        valid = valid & valid_mask.to(device=depth.device, dtype=torch.bool)
    return valid


def backproject_rendered_depth(
    depth: torch.Tensor,
    intrinsics: torch.Tensor,
) -> torch.Tensor:
    """Back-project a rendered depth map to camera-coordinate XYZ.

    Invalid depths are replaced by zero here and are excluded by the loss
    masks.  This avoids ``NaN * 0`` contamination while retaining gradients for
    every valid depth value.
    """

    height, width, K = _validate_depth_and_intrinsics(depth, intrinsics)
    z = torch.where(torch.isfinite(depth), depth, torch.zeros_like(depth))
    yy, xx = torch.meshgrid(
        torch.arange(height, device=depth.device, dtype=depth.dtype),
        torch.arange(width, device=depth.device, dtype=depth.dtype),
        indexing="ij",
    )
    x = (xx - K[0, 2]) * z / K[0, 0]
    y = (yy - K[1, 2]) * z / K[1, 1]
    return torch.stack((x, y, z), dim=-1)


def _batched_detached_plane_fit(
    points: torch.Tensor,
    valid: torch.Tensor,
    *,
    min_points: int,
    min_second_eigenvalue: float,
) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor, torch.Tensor, torch.Tensor]:
    """Fit detached free-orientation planes to ``(B,P,3)`` point batches."""

    if points.ndim != 3 or points.shape[-1] != 3:
        raise ValueError("points must have shape (B,P,3)")
    if valid.shape != points.shape[:2]:
        raise ValueError("valid must have shape (B,P)")

    detached = points.detach()
    weights = valid.to(dtype=points.dtype)
    count = weights.sum(dim=1)
    safe_points = torch.where(valid[..., None], detached, torch.zeros_like(detached))
    centroid = safe_points.sum(dim=1) / count.clamp_min(1.0)[:, None]
    centered = torch.where(
        valid[..., None],
        detached - centroid[:, None, :],
        torch.zeros_like(detached),
    )
    covariance = torch.einsum("bpi,bpj,bp->bij", centered, centered, weights)
    covariance = covariance / count.clamp_min(1.0)[:, None, None]
    eigenvalues, eigenvectors = torch.linalg.eigh(covariance)
    normals = eigenvectors[:, :, 0].detach()
    offsets = (-(normals * centroid).sum(dim=-1)).detach()
    eligible = (count >= int(min_points)) & (
        eigenvalues[:, 1] >= float(min_second_eigenvalue)
    )
    return normals, offsets, eligible, count, eigenvalues.detach()


def _absolute_residual_mean(
    points: torch.Tensor,
    valid: torch.Tensor,
    normals: torch.Tensor,
    offsets: torch.Tensor,
) -> torch.Tensor:
    signed = (points * normals[:, None, :]).sum(dim=-1) + offsets[:, None]
    errors = signed.abs()
    weights = valid.to(dtype=points.dtype)
    return (errors * weights).sum(dim=1) / weights.sum(dim=1).clamp_min(1.0)


def local_rendered_depth_coplanarity(
    depth: torch.Tensor,
    intrinsics: torch.Tensor,
    *,
    alpha: torch.Tensor | None = None,
    valid_mask: torch.Tensor | None = None,
    window_size: int = 7,
    stride: int = 4,
    min_points: int = 16,
    alpha_threshold: float = 0.5,
    max_depth_range: float | None = 1.0,
    min_second_eigenvalue: float = 1.0e-10,
) -> PlanarityOutput:
    """Segmentation-free local L1 plane consistency on rendered depth.

    Windows that straddle a depth discontinuity wider than
    ``max_depth_range`` are rejected rather than forcing separate surfaces into
    one plane.  Passing ``None`` disables that guard.  ``depth`` is expected to
    be the already alpha-normalized/unbiased plane-intersection rendered depth;
    this module does not reinterpret or renormalize it.  Plane parameters are
    fit from detached points; the L1 residual remains differentiable in depth.
    """

    height, width, _ = _validate_depth_and_intrinsics(depth, intrinsics)
    if window_size < 3 or window_size % 2 == 0:
        raise ValueError("window_size must be an odd integer >= 3")
    if stride < 1:
        raise ValueError("stride must be >= 1")
    if min_points < 3 or min_points > window_size * window_size:
        raise ValueError("min_points must be in [3, window_size**2]")
    if max_depth_range is not None and max_depth_range <= 0:
        raise ValueError("max_depth_range must be positive or None")
    if height < window_size or width < window_size:
        return PlanarityOutput(
            loss=_graph_zero(depth),
            plane_count=0,
            point_count=0,
            diagnostics={"candidate_window_count": 0, "rejected_depth_edge_count": 0},
        )

    valid = _valid_pixels(
        depth,
        alpha=alpha,
        valid_mask=valid_mask,
        alpha_threshold=alpha_threshold,
    )
    points = backproject_rendered_depth(depth, intrinsics)
    points_patches = F.unfold(
        points.permute(2, 0, 1).unsqueeze(0),
        kernel_size=window_size,
        stride=stride,
    )
    point_count_per_window = window_size * window_size
    points_patches = points_patches.reshape(
        3, point_count_per_window, -1
    ).permute(2, 1, 0)
    valid_patches = F.unfold(
        valid.to(dtype=depth.dtype)[None, None],
        kernel_size=window_size,
        stride=stride,
    ).squeeze(0).transpose(0, 1).to(dtype=torch.bool)

    normals, offsets, eligible, counts, eigenvalues = _batched_detached_plane_fit(
        points_patches,
        valid_patches,
        min_points=min_points,
        min_second_eigenvalue=min_second_eigenvalue,
    )

    rejected_depth_edge_count = 0
    if max_depth_range is not None:
        depth_patches = F.unfold(
            torch.where(torch.isfinite(depth), depth, torch.zeros_like(depth))[None, None],
            kernel_size=window_size,
            stride=stride,
        ).squeeze(0).transpose(0, 1)
        inf = torch.full_like(depth_patches, float("inf"))
        ninf = torch.full_like(depth_patches, float("-inf"))
        patch_min = torch.where(valid_patches, depth_patches, inf).min(dim=1).values
        patch_max = torch.where(valid_patches, depth_patches, ninf).max(dim=1).values
        depth_ok = (patch_max - patch_min) <= float(max_depth_range)
        rejected_depth_edge_count = int((eligible & ~depth_ok).sum().item())
        eligible = eligible & depth_ok

    if not bool(eligible.any()):
        return PlanarityOutput(
            loss=_graph_zero(depth),
            plane_count=0,
            point_count=0,
            diagnostics={
                "candidate_window_count": int(points_patches.shape[0]),
                "rejected_depth_edge_count": rejected_depth_edge_count,
            },
        )

    per_window = _absolute_residual_mean(
        points_patches,
        valid_patches,
        normals,
        offsets,
    )
    selected = per_window[eligible]
    selected_eigenvalues = eigenvalues[eligible]
    return PlanarityOutput(
        loss=selected.mean(),
        plane_count=int(eligible.sum().item()),
        point_count=int(counts[eligible].sum().item()),
        diagnostics={
            "candidate_window_count": int(points_patches.shape[0]),
            "rejected_depth_edge_count": rejected_depth_edge_count,
            "mean_fit_smallest_eigenvalue": float(
                selected_eigenvalues[:, 0].mean().cpu()
            ),
        },
    )


def _coerce_region_masks(
    region_masks: torch.Tensor,
    *,
    height: int,
    width: int,
    device: torch.device,
) -> tuple[torch.Tensor, list[int]]:
    masks = region_masks.to(device=device)
    if masks.dtype == torch.bool:
        if masks.ndim == 2:
            masks = masks.unsqueeze(0)
        elif masks.ndim != 3:
            raise ValueError("boolean region_masks must have shape (H,W) or (R,H,W)")
        if masks.shape[1:] != (height, width):
            raise ValueError("region_masks spatial shape must match depth")
        overlap = masks.to(torch.int16).sum(dim=0) > 1
        if bool(overlap.any()):
            raise ValueError("boolean region masks must not overlap")
        return masks, list(range(1, int(masks.shape[0]) + 1))

    if masks.ndim != 2 or masks.shape != (height, width):
        raise ValueError("integer region map must have shape (H,W)")
    if masks.is_floating_point():
        raise TypeError("region_masks must be boolean masks or an integer label map")
    region_ids = [int(v) for v in torch.unique(masks).detach().cpu().tolist() if int(v) > 0]
    if not region_ids:
        return torch.zeros((0, height, width), dtype=torch.bool, device=device), []
    return torch.stack([masks == region_id for region_id in region_ids]), region_ids


def region_rendered_depth_coplanarity(
    depth: torch.Tensor,
    intrinsics: torch.Tensor,
    region_masks: torch.Tensor,
    *,
    alpha: torch.Tensor | None = None,
    valid_mask: torch.Tensor | None = None,
    min_points: int = 16,
    alpha_threshold: float = 0.5,
    min_second_eigenvalue: float = 1.0e-10,
) -> PlanarityOutput:
    """Fit one detached plane per supplied region and return the mean L1 residual."""

    height, width, _ = _validate_depth_and_intrinsics(depth, intrinsics)
    if min_points < 3:
        raise ValueError("min_points must be >= 3")

    masks, region_ids = _coerce_region_masks(
        region_masks,
        height=height,
        width=width,
        device=depth.device,
    )
    base_valid = _valid_pixels(
        depth,
        alpha=alpha,
        valid_mask=valid_mask,
        alpha_threshold=alpha_threshold,
    )
    if masks.shape[0] == 0:
        return PlanarityOutput(
            loss=_graph_zero(depth),
            plane_count=0,
            point_count=0,
            diagnostics={"region_rows": []},
        )

    points_hw = backproject_rendered_depth(depth, intrinsics)
    points = points_hw.reshape(1, height * width, 3).expand(masks.shape[0], -1, -1)
    region_valid = masks.reshape(masks.shape[0], -1) & base_valid.reshape(1, -1)
    normals, offsets, eligible, counts, eigenvalues = _batched_detached_plane_fit(
        points,
        region_valid,
        min_points=min_points,
        min_second_eigenvalue=min_second_eigenvalue,
    )
    if not bool(eligible.any()):
        rows = [
            {
                "region_id": region_id,
                "point_count": int(counts[idx].item()),
                "eligible": False,
            }
            for idx, region_id in enumerate(region_ids)
        ]
        return PlanarityOutput(
            loss=_graph_zero(depth),
            plane_count=0,
            point_count=0,
            diagnostics={"region_rows": rows},
        )

    per_region = _absolute_residual_mean(
        points,
        region_valid,
        normals,
        offsets,
    )
    rows = []
    for idx, region_id in enumerate(region_ids):
        row = {
            "region_id": region_id,
            "point_count": int(counts[idx].item()),
            "eligible": bool(eligible[idx].item()),
        }
        if row["eligible"]:
            row["raw_loss"] = float(per_region[idx].detach().cpu())
            row["fit_smallest_eigenvalue"] = float(eigenvalues[idx, 0].cpu())
        rows.append(row)

    return PlanarityOutput(
        loss=per_region[eligible].mean(),
        plane_count=int(eligible.sum().item()),
        point_count=int(counts[eligible].sum().item()),
        diagnostics={"region_rows": rows},
    )


def audit_2dgs_flattening_invariant(
    scales: torch.Tensor,
    *,
    expected_thickness: float = 1.0e-6,
    atol: float = 1.0e-9,
) -> FlatteningInvariantAudit:
    """Check, but never optimize or score, the fixed 2DGS thickness."""

    if scales.ndim < 2 or scales.shape[-1] != 3:
        raise ValueError("scales must have shape (...,3)")
    if expected_thickness <= 0 or atol < 0:
        raise ValueError("expected_thickness must be positive and atol non-negative")
    thickness = scales[..., 2].detach()
    finite = torch.isfinite(thickness)
    if bool(finite.any()):
        max_error = float(
            (thickness[finite] - float(expected_thickness)).abs().max().cpu()
        )
    else:
        max_error = math.inf
    passed = bool(finite.all()) and max_error <= float(atol)
    return FlatteningInvariantAudit(
        passed=passed,
        expected_thickness=float(expected_thickness),
        max_abs_error=max_error,
        finite_count=int(finite.sum().item()),
        total_count=int(thickness.numel()),
    )


@torch.no_grad()
def calibrate_forward_only_plane_weight(
    weighted_roof_photo: torch.Tensor | float,
    raw_roof_plane: torch.Tensor | float,
    *,
    target_ratio: float = 1.0,
) -> float:
    """Return one pre-step plane weight; this function stores no mutable state.

    The caller must persist the returned scalar in a resolved config before the
    first optimizer step.  Calling this during training to auto-adjust a weight
    would violate the pilot contract.
    """

    photo = float(torch.as_tensor(weighted_roof_photo).detach().cpu())
    plane = float(torch.as_tensor(raw_roof_plane).detach().cpu())
    if not math.isfinite(photo) or not math.isfinite(plane):
        raise ValueError("calibration losses must be finite")
    if photo <= 0.0 or plane <= 0.0:
        raise ValueError("calibration losses must be strictly positive")
    if not math.isfinite(target_ratio) or target_ratio <= 0.0:
        raise ValueError("target_ratio must be finite and positive")
    return float(target_ratio) * abs(photo) / abs(plane)


__all__ = [
    "FlatteningInvariantAudit",
    "PlanarityOutput",
    "audit_2dgs_flattening_invariant",
    "backproject_rendered_depth",
    "calibrate_forward_only_plane_weight",
    "local_rendered_depth_coplanarity",
    "region_rendered_depth_coplanarity",
]
