"""Fixed loss-share audit helpers for quality-axis pilot wave 1.

This module is deliberately bookkeeping-only.  It never changes a loss weight,
selects a mask, or participates in back-propagation.  The trainer supplies the
already resolved seven public terms and their recomputations inside the common
projected-footprint roof audit scope.
"""
from __future__ import annotations

import csv
import math
from pathlib import Path
from typing import Mapping

import torch
import torch.nn.functional as F


PUBLIC_TERMS = ("pho", "dep", "nrm", "nc", "str.na", "str.cp", "plane")
LOSS_SHARE_RELATIVE_PATH = "audit/pilot_loss_shares.csv"
LOSS_DETAIL_RELATIVE_PATH = "audit/pilot_loss_details.csv"
PLANE_RATIO_RELATIVE_PATH = "audit/pilot_plane_photo_ratio.csv"
FULL_STATE_CSV_PATHS = (
    LOSS_SHARE_RELATIVE_PATH,
    LOSS_DETAIL_RELATIVE_PATH,
    PLANE_RATIO_RELATIVE_PATH,
)


def _finite_scalar(value: torch.Tensor | float, *, name: str) -> float:
    result = float(torch.as_tensor(value).detach().cpu().item())
    if not math.isfinite(result):
        raise FloatingPointError(f"pilot loss audit {name} is not finite: {result}")
    return result


def _validate_terms(values: Mapping[str, torch.Tensor | float], *, name: str) -> None:
    if set(values) != set(PUBLIC_TERMS):
        missing = sorted(set(PUBLIC_TERMS) - set(values))
        extra = sorted(set(values) - set(PUBLIC_TERMS))
        raise ValueError(f"{name} must contain the fixed public terms; missing={missing} extra={extra}")


def absolute_shares(
    weighted: Mapping[str, torch.Tensor | float],
) -> dict[str, float]:
    """Return abs-weight shares, with an exact all-zero result for denominator 0."""

    _validate_terms(weighted, name="weighted")
    magnitudes = {
        term: abs(_finite_scalar(weighted[term], name=f"weighted[{term}]"))
        for term in PUBLIC_TERMS
    }
    denominator = sum(magnitudes.values())
    if denominator == 0.0:
        return {term: 0.0 for term in PUBLIC_TERMS}
    return {term: magnitudes[term] / denominator for term in PUBLIC_TERMS}


def public_normal_term(
    primary_mvs_raw: torch.Tensor,
    auxiliary_mono_raw: torch.Tensor,
    *,
    primary_weight: float,
    auxiliary_weight: float,
) -> tuple[torch.Tensor, torch.Tensor]:
    """Return the locked public ``nrm`` raw subtotal and weighted sum."""

    raw = primary_mvs_raw + auxiliary_mono_raw
    weighted = (
        float(primary_weight) * primary_mvs_raw
        + float(auxiliary_weight) * auxiliary_mono_raw
    )
    return raw, weighted


def append_loss_share_rows(
    out_dir: Path,
    *,
    iteration: int,
    raw: Mapping[str, torch.Tensor | float],
    weighted: Mapping[str, torch.Tensor | float],
    roof_weighted: Mapping[str, torch.Tensor | float],
) -> None:
    """Append the exact seven rows and six public columns required by the lock."""

    if int(iteration) <= 0:
        raise ValueError("pilot audit iteration uses completed updates and must be positive")
    _validate_terms(raw, name="raw")
    _validate_terms(weighted, name="weighted")
    _validate_terms(roof_weighted, name="roof_weighted")
    shares = absolute_shares(weighted)
    roof_shares = absolute_shares(roof_weighted)
    path = Path(out_dir) / LOSS_SHARE_RELATIVE_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    write_header = not path.exists()
    with path.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["iter", "term", "raw", "weighted", "share", "roof_share"],
            lineterminator="\n",
        )
        if write_header:
            writer.writeheader()
        for term in PUBLIC_TERMS:
            writer.writerow(
                {
                    "iter": int(iteration),
                    "term": term,
                    "raw": _finite_scalar(raw[term], name=f"raw[{term}]"),
                    "weighted": _finite_scalar(weighted[term], name=f"weighted[{term}]"),
                    "share": shares[term],
                    "roof_share": roof_shares[term],
                }
            )


def append_detail_rows(out_dir: Path, rows: list[dict]) -> None:
    """Append internal detail without widening the locked public CSV schema."""

    if not rows:
        return
    fields = [
        "iter",
        "detail",
        "raw",
        "weight",
        "weighted",
        "roof_raw",
        "roof_weighted",
        "count",
        "status",
    ]
    path = Path(out_dir) / LOSS_DETAIL_RELATIVE_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    write_header = not path.exists()
    with path.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        if write_header:
            writer.writeheader()
        for input_row in rows:
            row = {field: input_row.get(field, "") for field in fields}
            writer.writerow(row)


def append_plane_photo_ratio(
    out_dir: Path,
    *,
    iteration: int,
    weighted_roof_plane: torch.Tensor | float,
    weighted_roof_photo: torch.Tensor | float,
) -> float:
    """Record the strong-arm equivalence audit; never modify the plane weight."""

    plane = abs(_finite_scalar(weighted_roof_plane, name="weighted_roof_plane"))
    photo = abs(_finite_scalar(weighted_roof_photo, name="weighted_roof_photo"))
    ratio = plane / photo if photo > 0.0 else 0.0
    path = Path(out_dir) / PLANE_RATIO_RELATIVE_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    write_header = not path.exists()
    with path.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "iter",
                "weighted_roof_plane",
                "weighted_roof_photo",
                "plane_photo_ratio",
                "within_required_0p5_to_2p0",
            ],
            lineterminator="\n",
        )
        if write_header:
            writer.writeheader()
        writer.writerow(
            {
                "iter": int(iteration),
                "weighted_roof_plane": plane,
                "weighted_roof_photo": photo,
                "plane_photo_ratio": ratio,
                "within_required_0p5_to_2p0": int(photo > 0.0 and 0.5 <= ratio <= 2.0),
            }
        )
    return ratio


def masked_normal_consistency(
    normal_render: torch.Tensor,
    normal_surface: torch.Tensor,
    mask: torch.Tensor,
    *,
    alpha: torch.Tensor | None = None,
) -> torch.Tensor:
    """Recompute ``L_nc`` inside one bool audit mask."""

    if mask.dtype != torch.bool or mask.shape != normal_render.shape[:2]:
        raise ValueError("roof audit mask must be bool HxW aligned with normals")
    nr = F.normalize(normal_render, dim=-1, eps=1.0e-6)
    ns = F.normalize(normal_surface, dim=-1, eps=1.0e-6)
    error = 1.0 - (nr * ns).sum(dim=-1)
    weight = mask.to(dtype=error.dtype)
    if alpha is not None:
        if alpha.shape != mask.shape:
            raise ValueError("alpha must be HxW aligned with the roof audit mask")
        weight = weight * alpha.detach().to(dtype=error.dtype)
    return (error * weight).sum() / weight.sum().clamp_min(1.0)


def structure_terms_in_scope(
    *,
    normals: torch.Tensor,
    centers: torch.Tensor,
    group_ids: torch.Tensor | None,
    rep_normals: torch.Tensor | None,
    rep_d: torch.Tensor | None,
    primitive_scope: torch.Tensor,
) -> tuple[torch.Tensor, torch.Tensor, int]:
    """Recompute NA/CP only for grouped primitives inside footprint XY union."""

    zero = torch.where(torch.isfinite(centers), centers, torch.zeros_like(centers)).sum() * 0.0
    if group_ids is None or rep_normals is None or rep_d is None:
        return zero, zero, 0
    if primitive_scope.dtype != torch.bool or primitive_scope.shape != group_ids.shape:
        raise ValueError("primitive_scope must be bool and aligned with group_ids")
    selected = primitive_scope & (group_ids >= 0)
    if not bool(selected.any().item()) or rep_normals.shape[0] == 0:
        return zero, zero, 0
    groups = group_ids[selected]
    representatives = rep_normals[groups].detach()
    offsets = rep_d[groups].detach()
    selected_normals = normals[selected]
    selected_centers = centers[selected]
    normal_align = (1.0 - (selected_normals * representatives).sum(dim=-1).abs()).square().mean()
    signed_distance = (representatives * selected_centers).sum(dim=-1) + offsets
    coplanar = signed_distance.square().mean()
    return normal_align, coplanar, int(selected.sum().item())


__all__ = [
    "FULL_STATE_CSV_PATHS",
    "LOSS_DETAIL_RELATIVE_PATH",
    "LOSS_SHARE_RELATIVE_PATH",
    "PLANE_RATIO_RELATIVE_PATH",
    "PUBLIC_TERMS",
    "absolute_shares",
    "append_detail_rows",
    "append_loss_share_rows",
    "append_plane_photo_ratio",
    "masked_normal_consistency",
    "public_normal_term",
    "structure_terms_in_scope",
]
