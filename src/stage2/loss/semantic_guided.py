"""Semantic-addressed geometry regularizers for the S3-A upper-bound test.

This module deliberately contains no monocular-depth input.  The semantic label
only supplies the *address* of two rendered-depth regularizers:

* ``L_smooth``: a masked five-point Laplacian on expected rendered depth;
* ``L_plane``: a point-to-plane residual to a robust, periodically detached fit.

``L_nb`` reuses the existing monocular *normal* map, but only on the roof-class
morphological boundary.  In particular, the instance cut line used by the depth
regularizers is never part of the boundary-normal mask.

The footprint split itself is produced once by the S3 preprocessing/audit
script.  For image ``foo.jpg``, ``SemanticRegionCache`` expects ``foo.npz`` with:

``region_ids``
    ``(H,W) int32``; zero means excluded, positive values identify a
    footprint-split roof region.  The producer applies the >=256 px test to the
    *source class connected component before splitting*; a small split child is
    therefore still retained.
``cutline_mask``
    ``(H,W) bool``; the full +/-7 px exclusion band around instance cuts.
``metadata_json``
    Required JSON scalar.  Its cache contract locks 8-connectivity, 256 px
    pre-split minimum, +/-7 px cut band, and the 20 m Roofer footprint buffer.
    ``regions`` maps each id to building id, source component id/size, and the
    pre-split footprint-overlap count.  A one-time raycast-building-id check may
    also be recorded here.  Mapping fields are audit-only, never loss values.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Any, Dict, Optional

import numpy as np
import torch
import torch.nn.functional as F


def _zero_like_graph(x: torch.Tensor) -> torch.Tensor:
    """Return a scalar zero that remains connected to ``x``'s graph."""

    return x.sum() * 0.0


def _huber_mean(values: torch.Tensor, delta: float) -> torch.Tensor:
    if values.numel() == 0:
        return _zero_like_graph(values)
    return F.smooth_l1_loss(
        values,
        torch.zeros_like(values),
        beta=float(delta),
        reduction="mean",
    )


@dataclass
class RegionFrame:
    """One cached, footprint-split semantic frame."""

    region_ids: torch.Tensor
    cutline_mask: torch.Tensor
    metadata: Dict[str, Any] = field(default_factory=dict)


class SemanticRegionCache:
    """Lazy loader for fixed per-view S3 semantic-region caches."""

    def __init__(
        self,
        root: str | Path,
        *,
        expected_cutline_half_width_px: int = 7,
        expected_source_component_min_pixels: int = 256,
        expected_connectivity: int = 8,
        expected_footprint_buffer_m: float = 20.0,
    ):
        self.root = Path(root)
        self.expected_cutline_half_width_px = int(expected_cutline_half_width_px)
        self.expected_source_component_min_pixels = int(expected_source_component_min_pixels)
        self.expected_connectivity = int(expected_connectivity)
        self.expected_footprint_buffer_m = float(expected_footprint_buffer_m)
        self._cpu_cache: Dict[str, RegionFrame] = {}

    @staticmethod
    def _parse_metadata(npz: np.lib.npyio.NpzFile) -> Dict[str, Any]:
        if "metadata_json" not in npz.files:
            return {}
        raw = npz["metadata_json"]
        if isinstance(raw, np.ndarray):
            raw = raw.item()
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        parsed = json.loads(str(raw))
        if not isinstance(parsed, dict):
            raise ValueError("metadata_json must decode to a JSON object")
        return parsed

    def _validate_contract(self, metadata: Dict[str, Any], path: Path) -> None:
        contract = metadata.get("cache_contract", metadata)
        required = {
            "cutline_half_width_px": self.expected_cutline_half_width_px,
            "source_component_min_pixels": self.expected_source_component_min_pixels,
            "connectivity": self.expected_connectivity,
            "footprint_buffer_m": self.expected_footprint_buffer_m,
        }
        for key, expected in required.items():
            if key not in contract:
                raise ValueError(f"{path}: metadata_json misses required cache contract field {key!r}")
            actual = contract[key]
            if isinstance(expected, float):
                matches = abs(float(actual) - expected) <= 1e-6
            else:
                matches = int(actual) == expected
            if not matches:
                raise ValueError(
                    f"{path}: cache contract {key}={actual!r}, expected {expected!r}"
                )

    def validate_files(self, image_names: list[str]) -> None:
        """Fail before training if any view has a missing/mismatched cache."""

        for image_name in image_names:
            stem = Path(image_name).stem
            path = self.root / f"{stem}.npz"
            if not path.exists():
                raise FileNotFoundError(path)
            with np.load(path, allow_pickle=False) as npz:
                required = {"region_ids", "cutline_mask", "metadata_json"}
                missing = sorted(required - set(npz.files))
                if missing:
                    raise ValueError(f"{path}: missing arrays {missing}")
                region_ids = npz["region_ids"]
                cutline_mask = npz["cutline_mask"]
                if region_ids.ndim != 2 or cutline_mask.shape != region_ids.shape:
                    raise ValueError(
                        f"{path}: region_ids and cutline_mask must be same-shape HxW arrays"
                    )
                self._validate_contract(self._parse_metadata(npz), path)

    def _load_cpu(self, image_name: str) -> RegionFrame:
        stem = Path(image_name).stem
        if stem in self._cpu_cache:
            return self._cpu_cache[stem]
        path = self.root / f"{stem}.npz"
        if not path.exists():
            raise FileNotFoundError(
                f"Missing semantic-region cache for {image_name!r}: {path}"
            )
        with np.load(path, allow_pickle=False) as npz:
            required = {"region_ids", "cutline_mask"}
            missing = sorted(required - set(npz.files))
            if missing:
                raise ValueError(f"{path}: missing arrays {missing}")
            region_ids = np.asarray(npz["region_ids"])
            cutline_mask = np.asarray(npz["cutline_mask"])
            metadata = self._parse_metadata(npz)
        if region_ids.ndim != 2 or cutline_mask.shape != region_ids.shape:
            raise ValueError(
                f"{path}: region_ids and cutline_mask must be same-shape HxW arrays"
            )
        if np.any(region_ids < 0):
            raise ValueError(f"{path}: region_ids must be non-negative")
        self._validate_contract(metadata, path)
        metadata_regions = metadata.get("regions", {})
        if not isinstance(metadata_regions, dict):
            raise ValueError(f"{path}: metadata_json.regions must be an object")
        positive_ids = set(int(v) for v in np.unique(region_ids) if int(v) > 0)
        mapped_ids = set(int(v) for v in metadata_regions)
        missing_mapping = sorted(positive_ids - mapped_ids)
        if missing_mapping:
            raise ValueError(f"{path}: positive region ids lack metadata mapping: {missing_mapping}")
        for rid in positive_ids:
            row = metadata_regions.get(str(rid), metadata_regions.get(rid, {}))
            required_region_fields = {
                "building_id",
                "source_component_id",
                "source_component_pixel_count",
                "pre_split_overlap_count",
            }
            missing_fields = sorted(required_region_fields - set(row))
            if missing_fields:
                raise ValueError(
                    f"{path}: region {rid} metadata misses {missing_fields}"
                )
        frame = RegionFrame(
            # Producer ids are int32.  Preserving that dtype cuts the eventual
            # all-view lazy CPU cache roughly in half versus an unnecessary
            # int64 expansion; comparisons/unique do not require int64 here.
            region_ids=torch.from_numpy(region_ids.astype(np.int32, copy=False)),
            cutline_mask=torch.from_numpy(cutline_mask.astype(np.bool_, copy=False)),
            metadata=metadata,
        )
        self._cpu_cache[stem] = frame
        return frame

    def get(
        self,
        image_name: str,
        height: int,
        width: int,
        device: torch.device | str,
    ) -> RegionFrame:
        frame = self._load_cpu(image_name)
        ids = frame.region_ids
        cut = frame.cutline_mask
        if ids.shape != (height, width):
            raise ValueError(
                f"semantic-region cache resolution {tuple(ids.shape)} does not match "
                f"render resolution {(height, width)} for {image_name!r}; resizing would "
                "move the locked 7 px cutline and is forbidden"
            )
        return RegionFrame(
            region_ids=ids.to(device=device, non_blocking=True),
            cutline_mask=cut.to(device=device, non_blocking=True),
            metadata=frame.metadata,
        )


def class_boundary_band(
    semantic: torch.Tensor,
    *,
    roof_class: int = 1,
    kernel_size: int = 5,
) -> torch.Tensor:
    """Morphological roof/non-roof boundary, independent of instance cuts.

    ``kernel_size=5`` implements a *true five-pixel output band*: take the
    one-pixel roof-side class transition ``M - erode_3(M)`` and dilate it by a
    5x5 structuring element.  On a straight in-frame boundary this is exactly
    two non-roof pixels + the roof transition pixel + two roof pixels.  Pooling
    does not fabricate non-roof pixels outside the image, so an all-roof image
    (or a roof merely touching the image border) has no artificial border band.
    """

    if semantic.ndim != 2:
        raise ValueError("semantic must have shape (H,W)")
    if kernel_size <= 0 or kernel_size % 2 == 0:
        raise ValueError("kernel_size must be a positive odd integer")
    roof = (semantic == int(roof_class)).to(torch.float32)[None, None]
    # Max-pool pads with -inf.  Therefore an image exterior does not count as
    # a non-roof neighbour, which avoids a spurious frame-edge normal loss.
    nonroof = 1.0 - roof
    near_nonroof = F.max_pool2d(nonroof, 3, stride=1, padding=1) > 0.5
    inner_transition = (roof > 0.5) & near_nonroof
    pad = kernel_size // 2
    band = F.max_pool2d(
        inner_transition.to(torch.float32), kernel_size, stride=1, padding=pad
    )
    return band[0, 0] > 0.5


def masked_laplacian_smoothness(
    depth: torch.Tensor,
    alpha: torch.Tensor,
    region_ids: torch.Tensor,
    cutline_mask: torch.Tensor,
    *,
    alpha_threshold: float = 0.5,
    huber_delta: float = 1.0,
) -> tuple[torch.Tensor, Dict[str, Any]]:
    """Huber loss on a strictly valid five-point depth Laplacian.

    A stencil contributes only when centre+north+south+west+east all belong to
    the same retained split region, are outside the +/-7 px cut band, have
    finite depth, and have alpha >= ``alpha_threshold``.  Thus neither a class
    boundary, an instance cut, nor one invalid rendered-depth pixel can pull a
    valid roof pixel.
    """

    if not (
        depth.ndim == alpha.ndim == region_ids.ndim == cutline_mask.ndim == 2
        and depth.shape == alpha.shape == region_ids.shape == cutline_mask.shape
    ):
        raise ValueError("depth, alpha, region_ids, and cutline_mask must be same-shape HxW")
    if min(depth.shape) < 3:
        return _zero_like_graph(depth), {"valid_stencil_count": 0, "eligible_region_count": 0}

    # Positive ids already come only from source class-components that passed
    # the producer's pre-split >=256 px lock.  Do not reapply the threshold to a
    # (possibly smaller) per-building split child here.
    eligible_ids = torch.unique(region_ids[region_ids > 0])
    if eligible_ids.numel() == 0:
        return _zero_like_graph(depth), {"valid_stencil_count": 0, "eligible_region_count": 0}
    eligible = region_ids > 0

    rid_c = region_ids[1:-1, 1:-1]
    id_same = (
        (rid_c > 0)
        & eligible[1:-1, 1:-1]
        & (region_ids[:-2, 1:-1] == rid_c)
        & (region_ids[2:, 1:-1] == rid_c)
        & (region_ids[1:-1, :-2] == rid_c)
        & (region_ids[1:-1, 2:] == rid_c)
    )
    render_valid = torch.isfinite(depth) & torch.isfinite(alpha) & (alpha >= float(alpha_threshold))
    usable = render_valid & (~cutline_mask)
    stencil_valid = (
        id_same
        & usable[1:-1, 1:-1]
        & usable[:-2, 1:-1]
        & usable[2:, 1:-1]
        & usable[1:-1, :-2]
        & usable[1:-1, 2:]
    )
    lap = (
        depth[:-2, 1:-1]
        + depth[2:, 1:-1]
        + depth[1:-1, :-2]
        + depth[1:-1, 2:]
        - 4.0 * depth[1:-1, 1:-1]
    )
    # Locked formula: sum_R mean_{p in R}.  A single global mean would silently
    # area-weight large roofs and is therefore intentionally not used.
    region_losses = []
    per_region_stencil_count: Dict[int, int] = {}
    for rid_t in eligible_ids:
        rid = int(rid_t.detach().cpu().item())
        region_stencils = stencil_valid & (rid_c == rid_t)
        values = lap[region_stencils]
        per_region_stencil_count[rid] = int(values.numel())
        if values.numel():
            region_losses.append(_huber_mean(values, huber_delta))
    loss = torch.stack(region_losses).sum() if region_losses else _zero_like_graph(depth)
    return loss, {
        "valid_stencil_count": int(stencil_valid.sum().detach().cpu().item()),
        "eligible_region_count": int(eligible_ids.numel()),
        "per_region_stencil_count": per_region_stencil_count,
    }


def backproject_depth(depth: torch.Tensor, K: torch.Tensor) -> torch.Tensor:
    """Backproject z-depth to camera-frame 3D; rigid-frame distances are invariant."""

    if depth.ndim != 2 or K.shape != (3, 3):
        raise ValueError("depth must be HxW and K must be 3x3")
    height, width = depth.shape
    v, u = torch.meshgrid(
        torch.arange(height, device=depth.device, dtype=depth.dtype),
        torch.arange(width, device=depth.device, dtype=depth.dtype),
        indexing="ij",
    )
    z = depth
    x = (u - K[0, 2].to(depth.dtype)) / K[0, 0].to(depth.dtype) * z
    y = (v - K[1, 2].to(depth.dtype)) / K[1, 1].to(depth.dtype) * z
    return torch.stack((x, y, z), dim=-1)


def robust_plane_fit(
    points: torch.Tensor,
    *,
    huber_delta: float = 1.0,
    irls_iterations: int = 5,
) -> tuple[torch.Tensor, torch.Tensor]:
    """Fit a free-orientation plane with weighted PCA IRLS under ``no_grad``."""

    if points.ndim != 2 or points.shape[-1] != 3 or points.shape[0] < 3:
        raise ValueError("points must have shape (N,3), N>=3")
    with torch.no_grad():
        p = points.detach().to(torch.float64)
        weights = torch.ones(p.shape[0], dtype=p.dtype, device=p.device)
        n = torch.tensor([0.0, 0.0, 1.0], dtype=p.dtype, device=p.device)
        d = torch.zeros((), dtype=p.dtype, device=p.device)
        for _ in range(max(1, int(irls_iterations))):
            wsum = weights.sum().clamp_min(1e-12)
            centroid = (weights[:, None] * p).sum(dim=0) / wsum
            centred = p - centroid
            covariance = (centred * weights[:, None]).T @ centred / wsum
            _eigvals, eigvecs = torch.linalg.eigh(covariance)
            n = F.normalize(eigvecs[:, 0], dim=0, eps=1e-12)
            d = -(n * centroid).sum()
            residual = (p @ n + d).abs()
            weights = torch.where(
                residual <= float(huber_delta),
                torch.ones_like(residual),
                float(huber_delta) / residual.clamp_min(1e-12),
            )
        return n.to(points.dtype).detach(), d.to(points.dtype).detach()


@dataclass
class _PlaneState:
    normal: torch.Tensor
    offset: torch.Tensor
    fitted_iteration: int


class SemanticGuidedGeometry:
    """Stateful S3-A rendered-depth and class-boundary normal losses."""

    def __init__(
        self,
        region_cache: Optional[SemanticRegionCache],
        *,
        roof_class: int = 1,
        alpha_threshold: float = 0.5,
        plane_min_pixels: int = 64,
        plane_refit_every: int = 500,
        huber_delta: float = 1.0,
        plane_irls_iterations: int = 5,
        boundary_kernel_size: int = 5,
    ):
        self.region_cache = region_cache
        self.roof_class = int(roof_class)
        self.alpha_threshold = float(alpha_threshold)
        self.plane_min_pixels = int(plane_min_pixels)
        self.plane_refit_every = int(plane_refit_every)
        self.huber_delta = float(huber_delta)
        self.plane_irls_iterations = int(plane_irls_iterations)
        self.boundary_kernel_size = int(boundary_kernel_size)
        if not 0.0 <= self.alpha_threshold <= 1.0:
            raise ValueError("alpha_threshold must be in [0,1]")
        if self.plane_min_pixels < 3:
            raise ValueError("plane_min_pixels must be >=3")
        if self.plane_refit_every <= 0 or self.plane_irls_iterations <= 0:
            raise ValueError("plane refit interval and IRLS iterations must be positive")
        if self.huber_delta <= 0:
            raise ValueError("huber_delta must be positive")
        if self.boundary_kernel_size <= 0 or self.boundary_kernel_size % 2 == 0:
            raise ValueError("boundary kernel size must be a positive odd integer")
        self._planes: Dict[tuple[str, int], _PlaneState] = {}

    def _region_stats(
        self,
        frame: RegionFrame,
        alpha: torch.Tensor,
        depth_anchor_mask: Optional[torch.Tensor],
    ) -> list[Dict[str, Any]]:
        rows: list[Dict[str, Any]] = []
        metadata_regions = frame.metadata.get("regions", {})
        for rid_t in torch.unique(frame.region_ids[frame.region_ids > 0]):
            rid = int(rid_t.detach().cpu().item())
            mask = (frame.region_ids == rid) & (~frame.cutline_mask)
            count = int(mask.sum().detach().cpu().item())
            rendered = mask & torch.isfinite(alpha) & (alpha >= self.alpha_threshold)
            rendered_count = int(rendered.sum().detach().cpu().item())
            anchor_count = 0
            if depth_anchor_mask is not None:
                anchor_count = int((mask & depth_anchor_mask.bool()).sum().detach().cpu().item())
            md = metadata_regions.get(str(rid), metadata_regions.get(rid, {}))
            rows.append(
                {
                    "region_id": rid,
                    "building_id": md.get("building_id", ""),
                    "source_component_id": md.get("source_component_id", ""),
                    "source_component_pixel_count": md.get(
                        "source_component_pixel_count", ""
                    ),
                    "pre_split_overlap_count": md.get("pre_split_overlap_count", ""),
                    "region_pixel_count": count,
                    "render_valid_pixel_count": rendered_count,
                    "render_valid_fraction": rendered_count / max(count, 1),
                    "depth_anchor_pixel_count": anchor_count,
                    "depth_anchor_fraction": anchor_count / max(count, 1),
                }
            )
        return rows

    def __call__(
        self,
        *,
        iteration: int,
        view_key: str,
        depth: torch.Tensor,
        alpha: torch.Tensor,
        K: torch.Tensor,
        semantic: torch.Tensor,
        normal_render: torch.Tensor,
        normal_target: Optional[torch.Tensor],
        normal_mask: Optional[torch.Tensor],
        depth_anchor_mask: Optional[torch.Tensor] = None,
        enable_semdepth: bool = True,
        enable_boundary_normal: bool = True,
    ) -> Dict[str, Any]:
        """Evaluate active S3 terms and return loss scalars plus audit material."""

        zero_depth = _zero_like_graph(depth)
        zero_normal = _zero_like_graph(normal_render)
        result: Dict[str, Any] = {
            "smooth": zero_depth,
            "plane": zero_depth,
            "boundary_normal": zero_normal,
            "region_rows": [],
            "metadata": {},
            "smooth_valid_stencil_count": 0,
            "boundary_valid_pixel_count": 0,
            "boundary_kernel_size": self.boundary_kernel_size,
            "boundary_radius_px": self.boundary_kernel_size // 2,
            "region_ids": None,
            "cutline_mask": None,
        }

        frame: Optional[RegionFrame] = None
        if enable_semdepth:
            if self.region_cache is None:
                raise RuntimeError("semantic depth is enabled but semantic_region_cache is unset")
            frame = self.region_cache.get(view_key, depth.shape[0], depth.shape[1], depth.device)
            smooth, smooth_stats = masked_laplacian_smoothness(
                depth,
                alpha,
                frame.region_ids,
                frame.cutline_mask,
                alpha_threshold=self.alpha_threshold,
                huber_delta=self.huber_delta,
            )
            result["smooth"] = smooth
            result["smooth_valid_stencil_count"] = smooth_stats["valid_stencil_count"]
            result["metadata"] = frame.metadata
            result["region_ids"] = frame.region_ids
            result["cutline_mask"] = frame.cutline_mask
            region_rows = self._region_stats(frame, alpha, depth_anchor_mask)
            smooth_counts = smooth_stats.get("per_region_stencil_count", {})
            for row in region_rows:
                row["smooth_valid_stencil_count"] = smooth_counts.get(
                    int(row["region_id"]), 0
                )

            points = backproject_depth(depth, K)
            plane_residuals = []
            row_by_region = {int(row["region_id"]): row for row in region_rows}
            for rid, row in row_by_region.items():
                region_mask = (
                    (frame.region_ids == rid)
                    & (~frame.cutline_mask)
                    & torch.isfinite(depth)
                    & torch.isfinite(alpha)
                    & (alpha >= self.alpha_threshold)
                )
                n_valid = int(region_mask.sum().detach().cpu().item())
                key = (str(view_key), rid)
                state = self._planes.get(key)
                should_refit = (
                    state is None
                    or int(iteration) - state.fitted_iteration >= self.plane_refit_every
                )
                row["plane_valid_pixel_count"] = n_valid
                row["plane_skipped_lt64"] = int(n_valid < self.plane_min_pixels)
                if n_valid < self.plane_min_pixels:
                    row["plane_fitted_iteration"] = ""
                    continue
                if should_refit:
                    normal, offset = robust_plane_fit(
                        points[region_mask],
                        huber_delta=self.huber_delta,
                        irls_iterations=self.plane_irls_iterations,
                    )
                    state = _PlaneState(normal, offset, int(iteration))
                    self._planes[key] = state
                assert state is not None
                # n,d stay detached until the next >=500-iteration refresh.
                residual = points[region_mask] @ state.normal + state.offset
                plane_residuals.append(residual)
                row["plane_loss"] = float(
                    _huber_mean(residual, self.huber_delta).detach().cpu().item()
                )
                row["plane_fitted_iteration"] = state.fitted_iteration
            if plane_residuals:
                # Locked L_plane is one pixel-level mean after each region has
                # obtained its own detached robust plane.  Concatenating avoids
                # over-weighting a small split child.
                result["plane"] = _huber_mean(
                    torch.cat(plane_residuals, dim=0), self.huber_delta
                )
            result["region_rows"] = region_rows

        if enable_boundary_normal:
            if normal_target is None or normal_mask is None:
                raise RuntimeError("boundary normal is enabled but no normal target/mask was loaded")
            band = class_boundary_band(
                semantic,
                roof_class=self.roof_class,
                kernel_size=self.boundary_kernel_size,
            )
            valid = band & normal_mask.bool()
            result["boundary_valid_pixel_count"] = int(valid.sum().detach().cpu().item())
            if bool(valid.any().item()):
                pred = F.normalize(normal_render, dim=-1, eps=1e-6)
                target = F.normalize(normal_target, dim=-1, eps=1e-6)
                error = 1.0 - (pred * target).sum(dim=-1).abs()
                result["boundary_normal"] = error[valid].mean()
        return result
