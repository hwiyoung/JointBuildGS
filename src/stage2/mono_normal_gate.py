"""Locked Omnidata auxiliary-normal gate for pilot wave 1.

MVS normals remain the primary normal supervision.  This module only builds a
binary agreement gate by comparing the primary MVS map with the Omnidata map,
then evaluates an explicitly separate auxiliary loss inside that gate.  It
cannot replace, reweight, or disable the caller's primary-normal loss.

The preregistered rule is intentionally not configurable at runtime:

* full, non-overlapping 16x16 patches (incomplete bottom/right borders ignored),
* at least 64 mutually valid pixels in a patch,
* sign-invariant per-pixel angular disagreement,
* patch ``torch.median`` disagreement <= 15 degrees, and
* only mutually valid pixels of eligible patches enter the auxiliary loss.
"""
from __future__ import annotations

import math
from typing import Any, Optional

import torch


PATCH_SIZE = 16
MIN_MUTUAL_VALID_PIXELS = 64
MAX_PATCH_MEDIAN_ANGLE_DEG = 15.0
AUDIT_SCHEMA = "jointbuildgs.pilot_mono_normal_gate.v1"


def _validate_normal_map(value: torch.Tensor, name: str) -> None:
    if not isinstance(value, torch.Tensor):
        raise TypeError(f"{name} must be a torch.Tensor")
    if value.ndim != 3 or value.shape[-1] != 3:
        raise ValueError(f"{name} must have shape HxWx3, got {tuple(value.shape)}")
    if not value.is_floating_point():
        raise ValueError(f"{name} must use a floating dtype")


def _validate_valid_mask(
    value: Optional[torch.Tensor],
    *,
    shape: tuple[int, int],
    device: torch.device,
    name: str,
) -> torch.Tensor:
    if value is None:
        return torch.ones(shape, dtype=torch.bool, device=device)
    if not isinstance(value, torch.Tensor):
        raise TypeError(f"{name} must be a torch.Tensor")
    if value.dtype != torch.bool or tuple(value.shape) != shape:
        raise ValueError(f"{name} must be a bool HxW tensor with shape {shape}")
    if value.device != device:
        raise ValueError(f"{name} must be on the same device as the normal maps")
    return value


def build_mono_normal_gate(
    primary_mvs_normal: torch.Tensor,
    auxiliary_omnidata_normal: torch.Tensor,
    primary_valid: Optional[torch.Tensor] = None,
    auxiliary_valid: Optional[torch.Tensor] = None,
) -> tuple[torch.Tensor, dict[str, Any]]:
    """Build the fixed patch gate and a JSON-serializable exact audit.

    Normal orientation is sign-invariant: ``n`` and ``-n`` have zero angular
    disagreement.  Validity masks are combined with finite, non-zero-vector
    checks.  The returned bool HxW tensor is detached by construction.
    """

    _validate_normal_map(primary_mvs_normal, "primary_mvs_normal")
    _validate_normal_map(auxiliary_omnidata_normal, "auxiliary_omnidata_normal")
    if primary_mvs_normal.shape != auxiliary_omnidata_normal.shape:
        raise ValueError("primary and auxiliary normal maps must have identical shape")
    if primary_mvs_normal.device != auxiliary_omnidata_normal.device:
        raise ValueError("primary and auxiliary normal maps must be on the same device")

    height, width = (int(primary_mvs_normal.shape[0]), int(primary_mvs_normal.shape[1]))
    shape = (height, width)
    device = primary_mvs_normal.device
    primary_valid_input = _validate_valid_mask(
        primary_valid,
        shape=shape,
        device=device,
        name="primary_valid",
    )
    auxiliary_valid_input = _validate_valid_mask(
        auxiliary_valid,
        shape=shape,
        device=device,
        name="auxiliary_valid",
    )

    with torch.no_grad():
        primary_finite = torch.isfinite(primary_mvs_normal).all(dim=-1)
        auxiliary_finite = torch.isfinite(auxiliary_omnidata_normal).all(dim=-1)
        primary_norm = torch.linalg.vector_norm(primary_mvs_normal, dim=-1)
        auxiliary_norm = torch.linalg.vector_norm(auxiliary_omnidata_normal, dim=-1)
        primary_effective_valid = (
            primary_valid_input & primary_finite & (primary_norm > 1.0e-6)
        )
        auxiliary_effective_valid = (
            auxiliary_valid_input & auxiliary_finite & (auxiliary_norm > 1.0e-6)
        )
        mutual_valid = primary_effective_valid & auxiliary_effective_valid

        primary_unit = primary_mvs_normal / primary_norm.clamp_min(1.0e-6)[..., None]
        auxiliary_unit = (
            auxiliary_omnidata_normal
            / auxiliary_norm.clamp_min(1.0e-6)[..., None]
        )
        cosine = (primary_unit * auxiliary_unit).sum(dim=-1).abs().clamp(0.0, 1.0)
        angle_deg = torch.acos(cosine) * (180.0 / math.pi)

        grid_rows = height // PATCH_SIZE
        grid_cols = width // PATCH_SIZE
        gate = torch.zeros(shape, dtype=torch.bool, device=device)
        patches: list[dict[str, Any]] = []
        eligible_count = 0
        insufficient_count = 0
        angle_rejected_count = 0
        for patch_row in range(grid_rows):
            y0 = patch_row * PATCH_SIZE
            y1 = y0 + PATCH_SIZE
            for patch_col in range(grid_cols):
                x0 = patch_col * PATCH_SIZE
                x1 = x0 + PATCH_SIZE
                patch_valid = mutual_valid[y0:y1, x0:x1]
                valid_count = int(patch_valid.sum().item())
                median_angle: Optional[float]
                if valid_count < MIN_MUTUAL_VALID_PIXELS:
                    eligible = False
                    median_angle = None
                    rejection_reason = "insufficient_mutual_valid"
                    insufficient_count += 1
                else:
                    # torch.median selects the lower middle order statistic for
                    # an even count; recording this pins the audit definition.
                    median_tensor = torch.median(
                        angle_deg[y0:y1, x0:x1][patch_valid]
                    )
                    median_angle = float(median_tensor.item())
                    eligible = median_angle <= MAX_PATCH_MEDIAN_ANGLE_DEG
                    if eligible:
                        rejection_reason = None
                        gate[y0:y1, x0:x1] = patch_valid
                        eligible_count += 1
                    else:
                        rejection_reason = "median_angle_above_threshold"
                        angle_rejected_count += 1
                patches.append(
                    {
                        "patch_row": patch_row,
                        "patch_col": patch_col,
                        "y0": y0,
                        "y1": y1,
                        "x0": x0,
                        "x1": x1,
                        "mutual_valid_pixel_count": valid_count,
                        "median_angle_deg": median_angle,
                        "eligible": eligible,
                        "rejection_reason": rejection_reason,
                    }
                )

        full_patch_count = grid_rows * grid_cols
        mutual_valid_count = int(mutual_valid.sum().item())
        covered_mutual_valid_count = int(
            mutual_valid[: grid_rows * PATCH_SIZE, : grid_cols * PATCH_SIZE]
            .sum()
            .item()
        )
        gated_count = int(gate.sum().item())
        audit: dict[str, Any] = {
            "schema": AUDIT_SCHEMA,
            "patch_size": PATCH_SIZE,
            "patch_layout": "full_nonoverlap_top_left_origin",
            "incomplete_border_policy": "excluded",
            "min_mutual_valid_pixels": MIN_MUTUAL_VALID_PIXELS,
            "max_patch_median_angle_deg": MAX_PATCH_MEDIAN_ANGLE_DEG,
            "angle_definition": "degrees(acos(clamp(abs(dot(unit_primary,unit_aux)),0,1)))",
            "median_definition": "torch.median_lower_order_statistic_for_even_count",
            "threshold_comparison": "median_angle_deg <= 15.0",
            "height": height,
            "width": width,
            "grid_rows": grid_rows,
            "grid_cols": grid_cols,
            "covered_height": grid_rows * PATCH_SIZE,
            "covered_width": grid_cols * PATCH_SIZE,
            "full_patch_count": full_patch_count,
            "eligible_patch_count": eligible_count,
            "rejected_insufficient_valid_patch_count": insufficient_count,
            "rejected_angle_patch_count": angle_rejected_count,
            "primary_input_valid_pixel_count": int(primary_valid_input.sum().item()),
            "auxiliary_input_valid_pixel_count": int(auxiliary_valid_input.sum().item()),
            "primary_effective_valid_pixel_count": int(
                primary_effective_valid.sum().item()
            ),
            "auxiliary_effective_valid_pixel_count": int(
                auxiliary_effective_valid.sum().item()
            ),
            "mutual_valid_pixel_count": mutual_valid_count,
            "covered_mutual_valid_pixel_count": covered_mutual_valid_count,
            "border_mutual_valid_pixel_count": (
                mutual_valid_count - covered_mutual_valid_count
            ),
            "gated_pixel_count": gated_count,
            "eligible_patch_fraction": (
                float(eligible_count / full_patch_count)
                if full_patch_count
                else 0.0
            ),
            "gated_mutual_valid_fraction": (
                float(gated_count / mutual_valid_count) if mutual_valid_count else 0.0
            ),
            "patches": patches,
        }
    return gate, audit


def l_auxiliary_mono_normal(
    predicted_normal: torch.Tensor,
    auxiliary_omnidata_normal: torch.Tensor,
    gate: torch.Tensor,
) -> torch.Tensor:
    """Sign-invariant auxiliary cosine loss inside a precomputed gate.

    This is a distinct loss term.  The primary MVS normal loss must be computed
    separately by the caller and remains active independent of this result.
    An empty gate returns a graph-connected exact zero, giving the prediction an
    exact zero gradient instead of ``None``.
    """

    _validate_normal_map(predicted_normal, "predicted_normal")
    _validate_normal_map(auxiliary_omnidata_normal, "auxiliary_omnidata_normal")
    if predicted_normal.shape != auxiliary_omnidata_normal.shape:
        raise ValueError("predicted and auxiliary normal maps must have identical shape")
    if predicted_normal.device != auxiliary_omnidata_normal.device:
        raise ValueError("predicted and auxiliary normal maps must be on the same device")
    if (
        not isinstance(gate, torch.Tensor)
        or gate.dtype != torch.bool
        or tuple(gate.shape) != tuple(predicted_normal.shape[:2])
    ):
        raise ValueError("gate must be a bool HxW tensor aligned with the normal maps")
    if gate.device != predicted_normal.device:
        raise ValueError("gate must be on the same device as the normal maps")
    if not bool(gate.any().item()):
        return predicted_normal.sum() * 0.0
    if not bool(torch.isfinite(auxiliary_omnidata_normal[gate]).all().item()):
        raise ValueError("gated auxiliary normals must be finite")
    if not bool(
        (
            torch.linalg.vector_norm(auxiliary_omnidata_normal[gate], dim=-1)
            > 1.0e-6
        )
        .all()
        .item()
    ):
        raise ValueError("gated auxiliary normals must be non-zero")

    predicted_unit = torch.nn.functional.normalize(predicted_normal[gate], dim=-1)
    auxiliary_unit = torch.nn.functional.normalize(
        auxiliary_omnidata_normal[gate], dim=-1
    )
    cosine = (predicted_unit * auxiliary_unit).sum(dim=-1).abs().clamp(0.0, 1.0)
    return (1.0 - cosine).mean()


__all__ = [
    "AUDIT_SCHEMA",
    "MAX_PATCH_MEDIAN_ANGLE_DEG",
    "MIN_MUTUAL_VALID_PIXELS",
    "PATCH_SIZE",
    "build_mono_normal_gate",
    "l_auxiliary_mono_normal",
]
