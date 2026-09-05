"""Photometric height sweeps on fixed native-point support.

The only candidate modification is an offset along scene-coordinate Z.  This is
not an estimated gravity direction.  FOV support is checked, but visibility and
occlusion are not; correlations are conditional diagnostic evidence, not a
currentness or geometric-use decision.  No MVS or evaluation reference is used.
"""
from __future__ import annotations

import hashlib
from typing import Any, Callable

import numpy as np

from scripts.phd.warp_ncc_v1.run import (
    bilinear_image,
    project_pixels,
    select_pairs,
)


def _digest(array: np.ndarray, dtype: str) -> str:
    """Hash canonical little-endian row-major bytes, without an array header."""
    return hashlib.sha256(np.ascontiguousarray(array, dtype=dtype).tobytes()).hexdigest()


def measure_height_sweep(
    xyz: np.ndarray,
    group_index: np.ndarray,
    heights: np.ndarray,
    cameras: dict,
    images: dict,
    view_ids: list[int],
    image_loader: Callable[[int], np.ndarray],
    params: dict,
    progress: Callable[[int, int], None] | None = None,
) -> dict[str, Any]:
    """Measure grouped unweighted ZNCC for ``xyz + [0, 0, height]``.

    ``group_index`` contains every integer from zero to G-1.  ``xyz`` row order
    identifies the native points: the caller must retain its mapping to source
    point IDs.  No resampling, plane fitting, or sample weighting is performed.
    Images must be full-resolution undistorted floating-point grayscale arrays;
    ``min_gray_std`` is in the loader's grayscale units, without normalization.

    Each pair uses the intersection of its in-FOV point rows over *all* heights,
    so the population for every group is identical throughout that pair's sweep.
    Texture tests do not change this support.  Missing samples or insufficient
    texture leave rho NaN and texture_ok False, rather than rejecting a candidate.

    Main outputs are rho/texture_ok/std_a/std_b [H, P, G], count [P, G], and
    pair_indices [P, 2] indexing view_ids.  pair_view_ids contains the image IDs.
    Support is stored as CSR-style support_offsets and support_point_indices;
    each pair's SHA256 hashes its ordered input-row indices as little-endian i8.
    Camera world_centres [V, 3] and pair_reference [3] use the source frame.
    ``progress``, if supplied, receives (completed_views, total_views).
    """
    xyz = np.asarray(xyz, dtype=np.float64)
    group_index = np.asarray(group_index)
    heights = np.asarray(heights, dtype=np.float64)
    if xyz.ndim != 2 or xyz.shape[1] != 3 or len(xyz) == 0:
        raise ValueError("xyz must be a nonempty [N, 3] array")
    if not np.isfinite(xyz).all():
        raise ValueError("xyz must contain only finite coordinates")
    if group_index.shape != (len(xyz),) or not np.issubdtype(group_index.dtype, np.integer):
        raise ValueError("group_index must be an integer [N] array")
    group_index = group_index.astype(np.int64, copy=False)
    groups = np.unique(group_index)
    if not np.array_equal(groups, np.arange(len(groups), dtype=np.int64)):
        raise ValueError("group_index must contain contiguous IDs starting at zero")
    if heights.ndim != 1 or len(heights) == 0 or not np.isfinite(heights).all():
        raise ValueError("heights must be a nonempty finite [H] array")
    if len(set(view_ids)) != len(view_ids):
        raise ValueError("view_ids must not contain duplicates")

    min_angle = float(params["min_pair_angle_deg"])
    max_angle = float(params["max_pair_angle_deg"])
    max_ratio = float(params["max_distance_ratio"])
    min_points_value = float(params["min_points"])
    min_std = float(params["min_gray_std"])
    if not all(np.isfinite(x) for x in (min_angle, max_angle, max_ratio, min_points_value, min_std)):
        raise ValueError("photometry parameters must be finite")
    if not (0 <= min_angle <= max_angle <= 180) or max_ratio < 1:
        raise ValueError("invalid pair angle or distance-ratio limits")
    if min_points_value < 2 or not min_points_value.is_integer() or min_std < 0:
        raise ValueError("min_points must be an integer >= 2 and min_gray_std >= 0")
    min_points = int(min_points_value)

    n_heights, n_views, n_points, n_groups = len(heights), len(view_ids), len(xyz), len(groups)
    luminance = np.full((n_heights, n_views, n_points), np.nan, dtype=np.float32)
    in_fov = np.zeros((n_heights, n_views, n_points), dtype=bool)
    centres: dict[int, np.ndarray] = {}
    reference = np.median(xyz, axis=0)
    for vi, iid in enumerate(view_ids):
        im = images[iid]
        cam = cameras[im.camera_id]
        if cam.model not in ("PINHOLE", "SIMPLE_PINHOLE"):
            raise ValueError(f"image {iid}: undistorted pinhole camera required, got {cam.model}")
        width, image_height = int(cam.width), int(cam.height)
        R, t, K = np.asarray(im.R()), np.asarray(im.tvec), np.asarray(cam.K())
        if R.shape != (3, 3) or t.shape != (3,) or K.shape != (3, 3):
            raise ValueError(f"image {iid}: invalid camera matrix dimensions")
        if not all(np.isfinite(value).all() for value in (R, t, K)):
            raise ValueError(f"image {iid}: nonfinite camera parameters")
        centres[iid] = -R.T @ t
        if np.linalg.norm(centres[iid] - reference) <= 1e-12:
            raise ValueError(f"image {iid}: camera centre coincides with pair reference")
        gray = np.asarray(image_loader(iid))
        if gray.shape != (image_height, width) or not np.issubdtype(gray.dtype, np.floating):
            raise ValueError(f"image {iid}: expected full-resolution floating-point grayscale")
        for hi, height_offset in enumerate(heights):
            shifted = xyz.copy()
            shifted[:, 2] += height_offset
            u, v, depth, _, _, inside = project_pixels(shifted, R, t, K, width, image_height)
            # Match warp_ncc_v1's bilinear-safe margins and +0.5 pixel centres.
            inside = (inside & (depth > 1e-6) & (u >= 1.0) & (u < width - 2.0)
                      & (v >= 1.0) & (v < image_height - 2.0))
            sampled = bilinear_image(gray, u[inside], v[inside]).astype(np.float32)
            if not np.isfinite(sampled).all():
                raise ValueError(f"image {iid}: nonfinite grayscale on projected point support")
            in_fov[hi, vi] = inside
            luminance[hi, vi, inside] = sampled
        if progress is not None:
            progress(vi + 1, n_views)

    pairs = select_pairs(view_ids, centres, reference, min_angle, max_angle, max_ratio)
    n_pairs = len(pairs)
    shape = (n_heights, n_pairs, n_groups)
    rho = np.full(shape, np.nan, dtype=np.float32)
    texture_ok = np.zeros(shape, dtype=bool)
    std_a = np.full(shape, np.nan, dtype=np.float32)
    std_b = np.full(shape, np.nan, dtype=np.float32)
    count = np.zeros((n_pairs, n_groups), dtype=np.int64)
    support_parts: list[np.ndarray] = []
    support_hashes: list[str] = []
    support_offsets = [0]
    for pi, (ai, bi, _angle, _ratio) in enumerate(pairs):
        support = np.flatnonzero(np.all(in_fov[:, ai] & in_fov[:, bi], axis=0))
        support_parts.append(support)
        support_hashes.append(_digest(support, "<i8"))
        support_offsets.append(support_offsets[-1] + len(support))
        labels = group_index[support]
        counts = np.bincount(labels, minlength=n_groups)
        count[pi] = counts
        if len(support) == 0:
            continue
        divisor = np.maximum(counts, 1)
        for hi in range(n_heights):
            a = luminance[hi, ai, support].astype(np.float64)
            b = luminance[hi, bi, support].astype(np.float64)
            mean_a = np.bincount(labels, weights=a, minlength=n_groups) / divisor
            mean_b = np.bincount(labels, weights=b, minlength=n_groups) / divisor
            da, db = a - mean_a[labels], b - mean_b[labels]
            # Centre first: subtracting raw second moments is unstable near flat images.
            var_a = np.bincount(labels, weights=da * da, minlength=n_groups) / divisor
            var_b = np.bincount(labels, weights=db * db, minlength=n_groups) / divisor
            cov = np.bincount(labels, weights=da * db, minlength=n_groups) / divisor
            sa, sb = np.sqrt(var_a), np.sqrt(var_b)
            std_a[hi, pi] = np.where(counts > 0, sa, np.nan)
            std_b[hi, pi] = np.where(counts > 0, sb, np.nan)
            denominator = sa * sb
            valid = ((counts >= min_points) & (sa >= min_std) & (sb >= min_std)
                     & (denominator > 0) & np.isfinite(denominator))
            values = np.full(n_groups, np.nan, dtype=np.float64)
            np.divide(cov, denominator, out=values, where=valid)
            valid &= np.isfinite(values)
            rho[hi, pi] = np.where(valid, np.clip(values, -1.0, 1.0), np.nan)
            texture_ok[hi, pi] = valid

    pair_indices = np.asarray([(a, b) for a, b, _, _ in pairs], dtype=np.int64).reshape(-1, 2)
    return {
        "rho": rho,
        "count": count,
        "texture_ok": texture_ok,
        "std_a": std_a,
        "std_b": std_b,
        "pair_indices": pair_indices,
        "pair_view_ids": np.asarray(view_ids, dtype=np.int64)[pair_indices],
        "pair_angles": np.asarray([angle for _, _, angle, _ in pairs], dtype=np.float64),
        "pair_distance_ratios": np.asarray([ratio for _, _, _, ratio in pairs], dtype=np.float64),
        "support_offsets": np.asarray(support_offsets, dtype=np.int64),
        "support_point_indices": (np.concatenate(support_parts) if support_parts
                                  else np.empty(0, dtype=np.int64)),
        "support_sha256": np.asarray(support_hashes, dtype="U64"),
        "world_centres": np.asarray([centres[iid] for iid in view_ids], dtype=np.float64).reshape(-1, 3),
        "pair_reference": reference,
        "heights": heights.copy(),
        "metadata": {
            "schema": "jointbuildgs.phd.prior_use_height_probe.photometry.v1",
            "scientific_verdict": None,
            "visibility": "UNVERIFIED_NO_OCCLUSION_TEST",
            "height_axis": "scene-coordinate Z; not estimated gravity",
            "pair_reference": "coordinate-wise median of the unshifted native prior xyz",
            "support_rule": "pairwise intersection of bilinear-safe FOV over all heights",
            "support_index_space": "xyz input row order; caller retains native source point IDs",
            "support_hash_encoding": "ordered input-row indices, little-endian int64, C bytes",
            "xyz_sha256_float64_le": _digest(xyz, "<f8"),
            "group_index_sha256_int64_le": _digest(group_index, "<i8"),
            "grayscale_scale": "unchanged from image_loader",
            "min_points": min_points,
            "min_gray_std": min_std,
            "min_pair_angle_deg": min_angle,
            "max_pair_angle_deg": max_angle,
            "max_distance_ratio": max_ratio,
            "n_points": n_points,
            "n_groups": n_groups,
            "n_views": n_views,
            "n_heights": n_heights,
        },
    }
