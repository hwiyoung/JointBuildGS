"""SRDM (Huang et al., 2018) two-step matching: a paper reimplementation.

This is NOT the authors' implementation.  Inputs must already be rectified and
registered.  Section 3.1's histogram blunder filtering and camera adjustment are
outside this module.  No reference/ground-truth geometry is accepted here.

Implemented: Eq. 6 (Census + improved orientation histogram), Eq. 11/13-17
(orthogonal, bidirectional INM), Eq. 18/19 (weak constraint and rejection), and
Eq. 21/22 (local search interval and truncated strong constraint).  The HOG
descriptor follows Huang et al. 2016, Sec. 2.1 (12 unweighted orientation bins).
SRDM's HOG cutoff 30 on a 5x5 cell implies count-L1 units, whereas the 2016
description normalizes the histogram.  This unresolved source ambiguity is
explicitly recorded; neither interpretation is described as author-code exact.

All native compilation and execution MUST be performed in the project's Docker
environment.  Native binaries, costs, and scratch arrays are created only in the
caller-supplied work directory, never in the repository.
"""

from __future__ import annotations

import ctypes
import dataclasses
import hashlib
import math
from pathlib import Path
import subprocess
import tempfile
import time
from typing import Any

import cv2
import numpy as np


PAPER_URL = (
    "https://cpb-us-w2.wpmucdn.com/u.osu.edu/dist/4/28638/files/2018/07/"
    "LiDAR_and_Image_paper-V3_close_to_final-28lqxo6.pdf"
)
HOG_URL = (
    "https://isprs-annals.copernicus.org/articles/III-3/67/2016/"
    "isprs-annals-III-3-67-2016.pdf"
)


@dataclasses.dataclass(frozen=True)
class SRDMConfig:
    # Values explicitly stated by SRDM 2018.
    penalty: float = 0.4
    propagation_sigma: float = 10.0
    census_weight: float = 0.5
    census_truncation: float = 15.0
    hog_truncation: float = 30.0
    inconsistency_threshold: float = 2.0
    directions: tuple[int, ...] = (0, 45, 90, 135)
    # Reimplementation choices: not reported author defaults.
    weak_sigma: float = 2.0
    search_radius: int = 15
    intensity_tolerance: float = 10.0
    gamma: float = 2.0
    lr_tolerance: float = 1.0
    hog_cost_mode: str = "count_l1"
    weak_downsample: int = 1
    interpolate: bool = False
    threads: int = 4
    invalid_cost: float = 100000.0
    max_volume_gib: float = 5.0
    # Resource choices only: identical float32 arrays, kernels, and arithmetic.
    storage: str = "memmap"
    max_total_volume_gib: float = 24.0

    @classmethod
    def from_value(cls, value: "SRDMConfig | dict[str, Any] | None") -> "SRDMConfig":
        if value is None:
            return cls()
        if isinstance(value, cls):
            return value
        data = dict(value)
        if "directions" in data:
            data["directions"] = tuple(data["directions"])
        return cls(**data)

    def validate(self) -> None:
        positive = (self.propagation_sigma, self.census_truncation,
                    self.hog_truncation, self.weak_sigma, self.gamma,
                    self.invalid_cost, self.max_volume_gib, self.max_total_volume_gib)
        if not all(math.isfinite(x) and x > 0 for x in positive):
            raise ValueError("Scale, cutoff, and memory values must be finite and positive")
        nonnegative = (self.penalty, self.inconsistency_threshold,
                       self.intensity_tolerance, self.lr_tolerance)
        if not all(math.isfinite(x) and x >= 0 for x in nonnegative):
            raise ValueError("Penalty and tolerances must be finite and nonnegative")
        if not 0 <= self.census_weight <= 1:
            raise ValueError("census_weight must be in [0,1]")
        if not self.directions or len(set(self.directions)) != len(self.directions):
            raise ValueError("directions must be nonempty and unique")
        if any(d not in (0, 45, 90, 135) for d in self.directions):
            raise ValueError("Only the four paper orientations are supported")
        if self.hog_cost_mode not in ("count_l1", "normalized_l1"):
            raise ValueError("Explicitly choose count_l1 or normalized_l1 HOG units")
        if self.storage not in ("ram", "hybrid", "memmap"):
            raise ValueError("storage must be ram, hybrid, or memmap")
        if self.search_radius < 0 or self.weak_downsample < 1 or self.threads < 1:
            raise ValueError("Invalid window, scale, or thread count")


def implementation_receipt(config: SRDMConfig) -> dict[str, Any]:
    return {
        "method": "SRDM_2018_PAPER_REIMPLEMENTATION",
        "scientific_verdict": None,
        "paper_url": PAPER_URL,
        "hog_reference_url": HOG_URL,
        "config": dataclasses.asdict(config),
        "implemented_equations": [6, 11, 13, 14, 15, 16, 17, 18, 19, 21, 22],
        "author_code_available": False,
        "outside_core": ["camera_adjustment", "histogram_blunder_preprocessing"],
        "resource_implementation": {
            "storage": config.storage,
            "arithmetic": "identical float32 C++ kernels and array order in every storage mode",
            "ram": "two photo volumes plus four DP scratch volumes in ndarray memory",
            "hybrid": "photo volumes flushed once and reopened read-only; four DP scratch volumes in RAM",
            "memmap": "original six file-backed volumes, with DP scratch flushed before close",
            "source_audit": "resource change only; no image, disparity range, criterion, or source membership change",
            "memory_estimates_exclude": "descriptors, output maps, native per-thread scratch, file page cache, optional TIN",
        },
        "reimplementation_choices": {
            "hog_units": "2018 cutoff30 interpreted as count-L1; 2016 normalized text differs",
            "grayscale": "OpenCV RGB2GRAY uint8, original 0..255 intensity scale",
            "hog_zero_gradient": "atan2(0,0)=0, one vote in bin0",
            "census_comparison": "neighbor intensity < central intensity; center omitted",
            "descriptor_support": "5x5 cell plus 3x3 Sobel support; full 7x7 valid",
            "unreported_parameters": ["weak_sigma", "search_radius", "intensity_tolerance",
                                      "gamma", "lr_tolerance"],
            "empty_local_prior": "full supplied global disparity interval",
            "unassessed_prior": "excluded from stereo constraints, not labeled geometrically wrong",
            "filtered_membership_rule": "finite LR-consistent weak disparity AND absolute residual <= threshold",
            "unassessed_rule_evidence_limit": "paper removes occluded samples but does not specify Eq19 inheritance of LR-invalid pixels",
            "filter_off_comparison_scope": "joint effect of residual rejection and exclusion of unassessed constraints; not residual-mask-only ablation",
            "recurrence_normalization": "subtract label-independent per-pixel minimum; same argmin",
            "invalid_candidate": "finite sentinel; excluded from WTA; no correspondence invented",
            "invalid_image_support": "terminate propagation across invalid reference-image support",
            "lr_sampling": "nearest integer coordinate; right disparities have opposite sign",
            "subpixel": "quadratic local minimum, clamped to half a pixel",
            "interpolation": "optional Delaunay linear interpolation, convex hull only; separate mask",
            "weak_pyramid": "integer downsample; rejection threshold is in weak-level pixels",
        },
    }


def _native(work_dir: Path) -> ctypes.CDLL:
    """Compile only into explicit runtime scratch; no repository writes."""
    source = Path(__file__).with_name("inm_backend.cpp")
    digest = hashlib.sha256(source.read_bytes()).hexdigest()[:16]
    build_dir = work_dir / "native_build"
    build_dir.mkdir(parents=True, exist_ok=True)
    library = build_dir / f"inm_{digest}.so"
    if not library.exists():
        with tempfile.TemporaryDirectory(prefix="compile_", dir=build_dir) as staging:
            tmp = Path(staging) / "inm.so"
            subprocess.run(["g++", "-O3", "-std=c++17", "-fopenmp", "-fPIC", "-shared",
                            str(source), "-o", str(tmp)], check=True, capture_output=True, text=True)
            tmp.replace(library)
    lib = ctypes.CDLL(str(library))
    ptr = ctypes.c_void_p
    cint, cf = ctypes.c_int, ctypes.c_float
    lib.srdm_aggregate.argtypes = [ptr, ptr, cint, cint, cint, cf, cf,
                                    cint, cint, cint, ptr, ptr, ptr]
    lib.srdm_aggregate.restype = cint
    lib.srdm_photo.argtypes = [ptr, ptr, ptr, ptr, ptr, ptr, cint, cint, cint,
                              cint, cf, cf, cf, cint, ptr]
    lib.srdm_photo.restype = cint
    lib.srdm_ranges.argtypes = [ptr, ptr, ptr, cint, cint, cint, cf, cf,
                               cint, cint, cint, ptr, ptr]
    lib.srdm_ranges.restype = cint
    return lib


def _ptr(array: np.ndarray) -> ctypes.c_void_p:
    if not array.flags.c_contiguous:
        raise ValueError("Native arrays must be C-contiguous")
    return ctypes.c_void_p(array.ctypes.data)


def quadratic_weight(delta: np.ndarray | float, sigma: float = 10.0) -> np.ndarray:
    """SRDM Eq.13: the paper's 'Gaussian' branch is exp(-abs(delta)/sigma)."""
    d = np.abs(np.asarray(delta, dtype=np.float64))
    a = (math.exp(-2.0) - 1.0) / (4.0 * sigma * sigma)
    return np.where(d <= 2.0 * sigma, 1.0 + a * d * d, np.exp(-d / sigma))


def descriptors(rgb: np.ndarray, valid: np.ndarray | None = None,
                hog_cost_mode: str = "count_l1") -> dict[str, np.ndarray]:
    """5x5 Census and 12-bin improved HOG; no magnitude weighting."""
    rgb = np.asarray(rgb)
    if rgb.dtype != np.uint8 or rgb.ndim != 3 or rgb.shape[2] != 3:
        raise ValueError("Images must be RGB uint8 arrays of shape H,W,3")
    h, w = rgb.shape[:2]
    if min(h, w) < 7:
        raise ValueError("Images must have at least 7 pixels per dimension")
    gray_u8 = cv2.cvtColor(np.ascontiguousarray(rgb), cv2.COLOR_RGB2GRAY)
    gray = gray_u8.astype(np.float32)
    gx = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3, borderType=cv2.BORDER_REFLECT_101)
    gy = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3, borderType=cv2.BORDER_REFLECT_101)
    angle = np.mod(np.arctan2(gy, gx), 2.0 * np.pi)
    bins = np.minimum((angle * (12.0 / (2.0 * np.pi))).astype(np.int32), 11)
    hist = np.empty((h, w, 12), dtype=np.float32)
    for b in range(12):
        hist[:, :, b] = cv2.boxFilter((bins == b).astype(np.float32), -1,
                                     (5, 5), normalize=False,
                                     borderType=cv2.BORDER_REFLECT_101)
    if hog_cost_mode == "normalized_l1":
        hist /= 25.0
    elif hog_cost_mode != "count_l1":
        raise ValueError("Unknown HOG units")
    padded = np.pad(gray_u8, 2, mode="reflect")
    census = np.zeros((h, w), dtype=np.uint32)
    bit = 0
    for dy in range(-2, 3):
        for dx in range(-2, 3):
            if dx == 0 and dy == 0:
                continue
            census |= ((padded[2 + dy:2 + dy + h, 2 + dx:2 + dx + w] < gray_u8)
                       .astype(np.uint32) << bit)
            bit += 1
    if valid is None:
        support = np.ones((h, w), dtype=np.uint8)
    else:
        support = np.ascontiguousarray(valid, dtype=np.uint8)
        if support.shape != (h, w):
            raise ValueError("Image validity mask has wrong shape")
    support = cv2.erode(support, np.ones((7, 7), dtype=np.uint8),
                        borderType=cv2.BORDER_CONSTANT, borderValue=0)
    return {"gray": gray, "census": census, "hog": hist, "valid": support}


def _allocate(directory: Path, name: str, shape: tuple[int, ...],
              storage: str = "memmap", *, photo: bool = False) -> np.ndarray:
    """Change backing storage only; dimensions, dtype, and arithmetic stay fixed."""
    if storage == "ram" or (storage == "hybrid" and not photo):
        return np.empty(shape, dtype=np.float32)
    if storage not in ("memmap", "hybrid"):
        raise ValueError("Unknown array storage mode")
    path = directory / name
    if path.exists():
        raise FileExistsError(path)
    return np.memmap(path, mode="w+", dtype=np.float32, shape=shape)


def _close_array(array: np.ndarray, *, flush: bool = False) -> None:
    """Release file mappings safely; ndarray memory is freed by its owner's scope."""
    if isinstance(array, np.memmap):
        if flush and array.flags.writeable:
            array.flush()
        array._mmap.close()


def _photo_cost(left: dict[str, np.ndarray], right: dict[str, np.ndarray],
                lo: int, hi: int, cfg: SRDMConfig, lib: ctypes.CDLL,
                directory: Path, name: str) -> np.ndarray:
    h, w = left["gray"].shape
    cost = _allocate(directory, name, (h, w, hi - lo + 1), cfg.storage, photo=True)
    # The C++ kernel uses -1 for forbidden pairs; costs are otherwise in [0,1].
    code = lib.srdm_photo(_ptr(left["census"]), _ptr(right["census"]),
                          _ptr(left["hog"]), _ptr(right["hog"]),
                          _ptr(left["valid"]), _ptr(right["valid"]), h, w, lo, hi,
                          cfg.census_weight, cfg.census_truncation, cfg.hog_truncation,
                          cfg.threads, _ptr(cost))
    if code:
        raise RuntimeError(f"Cost kernel failed: {code}")
    if cfg.storage == "hybrid":
        # Finish the only write pass before DP starts; clean, read-only photo
        # pages can then be reclaimed under the container's memory limit.
        shape = cost.shape
        path = Path(cost.filename)
        _close_array(cost, flush=True)
        cost = np.memmap(path, mode="r", dtype=np.float32, shape=shape)
    return cost


def search_ranges(gray: np.ndarray, sparse: np.ndarray, disparity_min: int,
                  disparity_max: int, config: SRDMConfig | dict[str, Any] | None,
                  work_dir: str | Path) -> tuple[np.ndarray, np.ndarray]:
    """Eq.21 with same-intensity sparse neighbors; empty neighborhoods stay global."""
    cfg = SRDMConfig.from_value(config)
    cfg.validate()
    gray = np.ascontiguousarray(gray, dtype=np.float32)
    sparse = np.ascontiguousarray(sparse, dtype=np.float32)
    if gray.shape != sparse.shape or gray.ndim != 2:
        raise ValueError("gray and sparse must be equally shaped 2D arrays")
    valid = np.ascontiguousarray(np.isfinite(sparse), dtype=np.uint8)
    low = np.empty(gray.shape, dtype=np.int32)
    high = np.empty(gray.shape, dtype=np.int32)
    lib = _native(Path(work_dir))
    h, w = gray.shape
    code = lib.srdm_ranges(_ptr(gray), _ptr(sparse), _ptr(valid), h, w,
                           cfg.search_radius, cfg.intensity_tolerance, cfg.gamma,
                           disparity_min, disparity_max, cfg.threads, _ptr(low), _ptr(high))
    if code:
        raise RuntimeError(f"Range kernel failed: {code}")
    return low, high


def prior_unary(photo: np.ndarray, sparse: np.ndarray, labels: np.ndarray,
                mode: str, config: SRDMConfig | dict[str, Any] | None = None) -> np.ndarray:
    """Small-array public helper for Eq.18/22 verification; runtime uses stripes."""
    cfg = SRDMConfig.from_value(config)
    result = np.array(photo, dtype=np.float32, copy=True)
    _apply_prior(result, sparse, labels, mode, cfg)
    return result


def _apply_prior(unary: np.ndarray, sparse: np.ndarray, labels: np.ndarray,
                 mode: str, cfg: SRDMConfig) -> None:
    present = np.isfinite(sparse)
    if mode == "image_only" or not present.any():
        return
    if mode not in ("weak", "strong"):
        raise ValueError("Unknown prior mode")
    # Limit the temporary to one image row, regardless of full cost volume size.
    for y in range(unary.shape[0]):
        xs = np.flatnonzero(present[y])
        if not xs.size:
            continue
        difference = np.abs(labels[None, :] - sparse[y, xs, None])
        if mode == "weak":
            unary[y, xs] -= cfg.penalty * np.exp(-difference / cfg.weak_sigma)
        else:
            # At prior pixels Eq.22 replaces, rather than adds to, photometric cost.
            unary[y, xs] = np.minimum(difference, cfg.gamma)


def aggregate_cost_volume(cost: np.ndarray, gray: np.ndarray,
                          config: SRDMConfig | dict[str, Any] | None,
                          work_dir: str | Path, *, normalize: bool = True) -> np.ndarray:
    """Public verification helper; returns costs, so use only for small test volumes."""
    cfg = SRDMConfig.from_value(config)
    cfg.validate()
    cost = np.ascontiguousarray(cost, dtype=np.float32)
    gray = np.ascontiguousarray(gray, dtype=np.float32)
    if cost.ndim != 3 or cost.shape[:2] != gray.shape or not np.isfinite(cost).all():
        raise ValueError("Cost volume and grayscale image are invalid")
    result = np.empty_like(cost)
    first, second = np.empty_like(cost), np.empty_like(cost)
    bits = sum(1 << (d // 45) for d in cfg.directions)
    code = _native(Path(work_dir)).srdm_aggregate(
        _ptr(cost), _ptr(gray), *cost.shape, cfg.penalty, cfg.propagation_sigma,
        bits, int(normalize), cfg.threads, _ptr(result), _ptr(first), _ptr(second))
    if code:
        raise RuntimeError(f"Aggregation failed: {code}")
    return result


def _match_one(photo: np.ndarray, descriptor: dict[str, np.ndarray], sparse: np.ndarray,
               lo: int, hi: int, mode: str, cfg: SRDMConfig, lib: ctypes.CDLL,
               directory: Path, run_name: str) -> dict[str, np.ndarray]:
    shape = photo.shape
    labels = np.arange(lo, hi + 1, dtype=np.float32)
    with tempfile.TemporaryDirectory(prefix=run_name + "_", dir=directory) as temporary:
        tmp = Path(temporary)
        unary = _allocate(tmp, "unary.f32", shape, cfg.storage)
        # Copy in rows, without an accidental full-volume boolean/float temporary.
        for y in range(shape[0]):
            unary[y] = photo[y]
        _apply_prior(unary, sparse, labels, mode, cfg)
        if mode == "strong":
            low, high = search_ranges(descriptor["gray"], sparse, lo, hi, cfg, directory)
        else:
            low = np.full(shape[:2], lo, dtype=np.int32)
            high = np.full(shape[:2], hi, dtype=np.int32)
        for y in range(shape[0]):
            forbidden = ((photo[y] < 0) | (labels[None, :] < low[y, :, None])
                         | (labels[None, :] > high[y, :, None]))
            unary[y][forbidden] = cfg.invalid_cost
        accumulated = _allocate(tmp, "sum.f32", shape, cfg.storage)
        first = _allocate(tmp, "first.f32", shape, cfg.storage)
        second = _allocate(tmp, "second.f32", shape, cfg.storage)
        bits = sum(1 << (d // 45) for d in cfg.directions)
        propagation_gray = np.where(descriptor["valid"] > 0, descriptor["gray"], np.nan).astype(np.float32)
        code = lib.srdm_aggregate(_ptr(unary), _ptr(propagation_gray), *shape,
                                   cfg.penalty, cfg.propagation_sigma, bits, 1,
                                   cfg.threads, _ptr(accumulated), _ptr(first), _ptr(second))
        if code:
            raise RuntimeError(f"Aggregation failed in {run_name}: {code}")
        disparity = np.full(shape[:2], np.nan, dtype=np.float32)
        confidence_gap = np.zeros(shape[:2], dtype=np.float32)
        xs = np.arange(shape[1])
        for y in range(shape[0]):
            row = np.array(accumulated[y], copy=True)
            allowed = unary[y] < cfg.invalid_cost
            row[~allowed] = np.inf
            best = row.argmin(axis=1)
            best_cost = row[xs, best]
            good = np.isfinite(best_cost) & (descriptor["valid"][y] > 0)
            d = labels[best].copy()
            interior = good & (best > 0) & (best < shape[2] - 1)
            ii = xs[interior]
            jj = best[interior]
            a, b, c = row[ii, jj - 1], row[ii, jj], row[ii, jj + 1]
            denominator = a - 2 * b + c
            fit = np.isfinite(denominator) & (denominator > 1e-8)
            offset = np.zeros(ii.size, dtype=np.float32)
            offset[fit] = np.clip(0.5 * (a[fit] - c[fit]) / denominator[fit], -0.5, 0.5)
            d[ii] += offset
            disparity[y, good] = d[good]
            if shape[2] > 1:
                second_best = np.partition(row, 1, axis=1)[:, 1]
                finite_gap = good & np.isfinite(second_best)
                confidence_gap[y, finite_gap] = second_best[finite_gap] - best_cost[finite_gap]
        for array in (unary, accumulated, first, second):
            _close_array(array, flush=True)
        del unary, accumulated, first, second, array
    return {"disparity": disparity, "raw_valid": np.isfinite(disparity),
            "cost_gap_diagnostic": confidence_gap,
            "search_min": low, "search_max": high}


def left_right_valid(left: np.ndarray, right: np.ndarray, tolerance: float = 1.0) -> np.ndarray:
    """The right map uses x_right-x_left, so consistent disparities sum to zero."""
    if left.shape != right.shape or left.ndim != 2:
        raise ValueError("Left and right disparity maps must have equal 2D shape")
    h, w = left.shape
    ys, xs = np.indices(left.shape)
    finite = np.isfinite(left)
    xr = np.rint(xs - np.where(finite, left, 0)).astype(np.int64)
    inside = finite & (xr >= 0) & (xr < w)
    sampled = right[ys, np.clip(xr, 0, w - 1)]
    return inside & np.isfinite(sampled) & (np.abs(left + sampled) <= tolerance)


def _interpolate(disparity: np.ndarray, valid: np.ndarray,
                 support: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Optional TIN fill is never included in observed-valid geometry metrics."""
    from scipy.interpolate import LinearNDInterpolator
    from scipy.spatial import QhullError

    result = disparity.copy()
    target = (~valid) & support
    filled = np.zeros(valid.shape, dtype=bool)
    if valid.sum() < 3 or not target.any():
        return result, filled
    yy, xx = np.nonzero(valid)
    ty, tx = np.nonzero(target)
    try:
        model = LinearNDInterpolator(np.column_stack((xx, yy)), disparity[valid], fill_value=np.nan)
        for start in range(0, len(tx), 100000):
            stop = start + 100000
            values = model(tx[start:stop], ty[start:stop])
            good = np.isfinite(values)
            gy, gx = ty[start:stop][good], tx[start:stop][good]
            result[gy, gx] = values[good]
            filled[gy, gx] = True
    except QhullError:
        # A line/degenerate domain has no valid triangular interpolation.
        return result, filled
    return result, filled


def _finish_pair(left: dict[str, np.ndarray], right: dict[str, np.ndarray],
                 descriptor: dict[str, np.ndarray], cfg: SRDMConfig) -> dict[str, np.ndarray]:
    valid = left_right_valid(left["disparity"], right["disparity"], cfg.lr_tolerance)
    measured = np.where(valid, left["disparity"], np.nan).astype(np.float32)
    if cfg.interpolate:
        combined, fill = _interpolate(measured, valid, descriptor["valid"] > 0)
    else:
        combined, fill = measured.copy(), np.zeros(valid.shape, dtype=bool)
    return {"disparity": combined, "valid": valid, "interpolated_mask": fill,
            "measured_disparity": measured, "before_lr_disparity": left["disparity"],
            "right_disparity": right["disparity"],
            "cost_gap_diagnostic": left["cost_gap_diagnostic"],
            "search_min": left["search_min"], "search_max": left["search_max"]}


def project_sparse_to_right(sparse: np.ndarray) -> np.ndarray:
    """Fallback: left-visible samples only; strongest (nearest) disparity wins."""
    h, w = sparse.shape
    yy, xx = np.nonzero(np.isfinite(sparse))
    dd = sparse[yy, xx]
    xr = np.rint(xx - dd).astype(np.int64)
    inside = (xr >= 0) & (xr < w)
    yy, xr, dd = yy[inside], xr[inside], dd[inside]
    result = np.full((h, w), np.nan, dtype=np.float32)
    # The caller's physical disparity sign follows its rectified baseline. For
    # each collision larger magnitude means nearer depth; left-only support is
    # reported rather than pretending to recover independently right-visible ALS.
    order = np.argsort(np.abs(dd), kind="stable")
    result[yy[order], xr[order]] = -dd[order]
    return result


def _downsample_prior(sparse: np.ndarray, scale: int, shape: tuple[int, int]) -> np.ndarray:
    yy, xx = np.nonzero(np.isfinite(sparse))
    dd = sparse[yy, xx] / scale
    sy, sx = np.minimum(yy // scale, shape[0] - 1), np.minimum(xx // scale, shape[1] - 1)
    out = np.full(shape, np.nan, dtype=np.float32)
    order = np.argsort(np.abs(dd), kind="stable")
    out[sy[order], sx[order]] = dd[order]
    return out


def _decide(sparse: np.ndarray, weak: np.ndarray, weak_valid: np.ndarray,
            threshold: float) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    present = np.isfinite(sparse)
    testable = present & weak_valid & np.isfinite(weak)
    difference = np.where(testable, np.abs(weak - sparse), np.nan).astype(np.float32)
    keep = testable & (difference <= threshold)
    reject = testable & (difference > threshold)
    return keep, reject, present & ~testable, difference


def run_srdm(left: np.ndarray, right: np.ndarray, sparse_disparity: np.ndarray,
             disparity_min: int, disparity_max: int,
             config: SRDMConfig | dict[str, Any] | None = None, *,
             work_dir: str | Path,
             left_valid: np.ndarray | None = None,
             right_valid: np.ndarray | None = None,
             left_valid_mask: np.ndarray | None = None,
             right_valid_mask: np.ndarray | None = None,
             sparse_right_disparity: np.ndarray | None = None) -> dict[str, Any]:
    """Run weak filtering and image-only/all-prior/filtered-prior reconstruction.

    Sign convention: sparse_disparity = x_left - x_right. If supplied,
    sparse_right_disparity uses x_right - x_left. All input arrays stay unchanged.
    ``valid`` always means measured/LR-consistent, excluding optional TIN filling.
    """
    cfg = SRDMConfig.from_value(config)
    cfg.validate()
    if left_valid_mask is not None:
        if left_valid is not None:
            raise ValueError("Supply left_valid or left_valid_mask, not both")
        left_valid = left_valid_mask
    if right_valid_mask is not None:
        if right_valid is not None:
            raise ValueError("Supply right_valid or right_valid_mask, not both")
        right_valid = right_valid_mask
    if left.shape != right.shape:
        raise ValueError("Rectified image dimensions must match")
    if isinstance(disparity_min, bool) or isinstance(disparity_max, bool):
        raise ValueError("Disparity endpoints must be integer values")
    lo, hi = int(disparity_min), int(disparity_max)
    if lo != disparity_min or hi != disparity_max or lo > hi:
        raise ValueError("Disparity interval must be inclusive ordered integers")
    sparse = np.array(sparse_disparity, dtype=np.float32, copy=True)
    if sparse.shape != left.shape[:2] or sparse.ndim != 2:
        raise ValueError("Sparse disparity shape does not match the images")
    if np.isinf(sparse).any():
        raise ValueError("Use NaN, not infinity, for absent priors")
    if np.any(np.isfinite(sparse) & ((sparse < lo) | (sparse > hi))):
        raise ValueError("Global disparity bounds must contain every finite prior")
    source_right = "independent_right_projection" if sparse_right_disparity is not None else "left_sparse_reprojection"
    sparse_r = (project_sparse_to_right(sparse) if sparse_right_disparity is None
                else np.array(sparse_right_disparity, dtype=np.float32, copy=True))
    if sparse_r.shape != sparse.shape or np.isinf(sparse_r).any():
        raise ValueError("Right sparse disparity is invalid")
    if np.any(np.isfinite(sparse_r) & ((sparse_r < -hi) | (sparse_r > -lo))):
        raise ValueError("Global disparity bounds must contain every right prior")
    volume_gib = sparse.size * (hi - lo + 1) * 4 / (1024 ** 3)
    if volume_gib > cfg.max_volume_gib:
        raise MemoryError(f"One cost volume needs {volume_gib:.3f} GiB; explicit limit {cfg.max_volume_gib}")
    total_volume_gib = 6 * volume_gib
    if total_volume_gib > cfg.max_total_volume_gib:
        raise MemoryError(f"Six cost volumes need {total_volume_gib:.3f} GiB; "
                          f"explicit total limit {cfg.max_total_volume_gib}")
    ram_volume_count = {"ram": 6, "hybrid": 4, "memmap": 0}[cfg.storage]
    work = Path(work_dir)
    work.mkdir(parents=True, exist_ok=True)
    cfg_receipt = implementation_receipt(cfg)
    start = time.monotonic()
    print(f"[SRDM] start {sparse.shape}, disparities={lo}..{hi}, "
          f"one_volume={volume_gib:.3f}GiB, storage={cfg.storage}, "
          f"DP/photo_RAM={ram_volume_count*volume_gib:.3f}GiB, threads={cfg.threads}", flush=True)
    cv2.setNumThreads(cfg.threads)
    dl, dr = descriptors(left, left_valid, cfg.hog_cost_mode), descriptors(right, right_valid, cfg.hog_cost_mode)
    lib = _native(work)
    with tempfile.TemporaryDirectory(prefix="srdm_costs_", dir=work) as temporary:
        tmp = Path(temporary)
        photo_l = _photo_cost(dl, dr, lo, hi, cfg, lib, tmp, "left.f32")
        photo_r = _photo_cost(dr, dl, -hi, -lo, cfg, lib, tmp, "right.f32")
        print(f"[SRDM] photometric costs ready ({time.monotonic()-start:.1f}s)", flush=True)
        if cfg.weak_downsample != 1:
            scale = cfg.weak_downsample
            wh, ww = math.ceil(sparse.shape[0] / scale), math.ceil(sparse.shape[1] / scale)
            if wh < 7 or ww < 7:
                raise ValueError("Weak pyramid level is too small")
            # Use exact integer-scale sampling with padded dimensions, so disparity
            # scaling stays s rather than silently using an OpenCV resize ratio.
            pad_h, pad_w = wh * scale - sparse.shape[0], ww * scale - sparse.shape[1]
            def reduce_image(im: np.ndarray) -> np.ndarray:
                padded = cv2.copyMakeBorder(im, 0, pad_h, 0, pad_w, cv2.BORDER_REFLECT_101)
                return cv2.resize(padded, (ww, wh), interpolation=cv2.INTER_AREA)
            def reduce_valid(v: np.ndarray) -> np.ndarray:
                padded = np.pad(v, ((0, pad_h), (0, pad_w)), constant_values=0)
                return padded.reshape(wh, scale, ww, scale).min(axis=(1, 3)).astype(np.uint8)
            wl = descriptors(reduce_image(left), reduce_valid(dl["valid"]), cfg.hog_cost_mode)
            wr = descriptors(reduce_image(right), reduce_valid(dr["valid"]), cfg.hog_cost_mode)
            sl = _downsample_prior(sparse, scale, (wh, ww))
            sr = _downsample_prior(sparse_r, scale, (wh, ww))
            wlo, whi = math.floor(lo / scale), math.ceil(hi / scale)
            pl = _photo_cost(wl, wr, wlo, whi, cfg, lib, tmp, "weak_left.f32")
            pr = _photo_cost(wr, wl, -whi, -wlo, cfg, lib, tmp, "weak_right.f32")
            al = _match_one(pl, wl, sl, wlo, whi, "weak", cfg, lib, tmp, "weak_left")
            ar = _match_one(pr, wr, sr, -whi, -wlo, "weak", cfg, lib, tmp, "weak_right")
            vl = left_right_valid(al["disparity"], ar["disparity"], cfg.lr_tolerance)
            vr = left_right_valid(ar["disparity"], al["disparity"], cfg.lr_tolerance)
            def expand(array: np.ndarray) -> np.ndarray:
                return np.repeat(np.repeat(array, scale, axis=0), scale, axis=1)[:sparse.shape[0], :sparse.shape[1]]
            weak_l, weak_r = expand(al["disparity"]) * scale, expand(ar["disparity"]) * scale
            weak_vl, weak_vr = expand(vl), expand(vr)
            for array in (pl, pr):
                _close_array(array)
            del pl, pr, array
        else:
            al = _match_one(photo_l, dl, sparse, lo, hi, "weak", cfg, lib, tmp, "weak_left")
            ar = _match_one(photo_r, dr, sparse_r, -hi, -lo, "weak", cfg, lib, tmp, "weak_right")
            weak_l, weak_r = al["disparity"], ar["disparity"]
            weak_vl = left_right_valid(weak_l, weak_r, cfg.lr_tolerance)
            weak_vr = left_right_valid(weak_r, weak_l, cfg.lr_tolerance)
        threshold = cfg.inconsistency_threshold * cfg.weak_downsample
        keep, reject, untestable, difference = _decide(sparse, weak_l, weak_vl, threshold)
        keep_r, _, _, _ = _decide(sparse_r, weak_r, weak_vr, threshold)
        print(f"[SRDM] weak decision: keep={keep.sum()} reject={reject.sum()} "
              f"untestable={untestable.sum()} ({time.monotonic()-start:.1f}s)", flush=True)
        arms = {}
        for arm, mode, sl, sr in (
            ("image_only", "image_only", np.full_like(sparse, np.nan), np.full_like(sparse_r, np.nan)),
            ("all_prior", "strong", sparse, sparse_r),
            ("srdm", "strong", np.where(keep, sparse, np.nan), np.where(keep_r, sparse_r, np.nan)),
        ):
            print(f"[SRDM] reconstruct {arm}", flush=True)
            a = _match_one(photo_l, dl, sl, lo, hi, mode, cfg, lib, tmp, arm + "_left")
            b = _match_one(photo_r, dr, sr, -hi, -lo, mode, cfg, lib, tmp, arm + "_right")
            arms[arm] = _finish_pair(a, b, dl, cfg)
            print(f"[SRDM] {arm} measured={arms[arm]['valid'].sum()} "
                  f"filled={arms[arm]['interpolated_mask'].sum()} "
                  f"({time.monotonic()-start:.1f}s)", flush=True)
        for array in (photo_l, photo_r):
            _close_array(array)
        del photo_l, photo_r, array
    cfg_receipt.update({"elapsed_seconds": time.monotonic() - start,
                        "one_cost_volume_gib": volume_gib,
                        "max_simultaneous_full_cost_volumes": 6,
                        "estimated_total_cost_volume_gib": total_volume_gib,
                        "estimated_explicit_ram_cost_volume_gib": ram_volume_count * volume_gib,
                        "estimated_file_backed_cost_volume_gib": (6 - ram_volume_count) * volume_gib,
                        "right_prior_source": source_right,
                        "disparity_interval_inclusive": [lo, hi],
                        "inconsistency_threshold_full_resolution_pixels": threshold,
                        "input_sha256": {"left": hashlib.sha256(left.tobytes()).hexdigest(),
                                         "right": hashlib.sha256(right.tobytes()).hexdigest(),
                                         "sparse": hashlib.sha256(sparse.tobytes()).hexdigest()}})
    return {"weak_disparity": weak_l, "weak_valid": weak_vl,
            "weak_right_disparity": weak_r, "weak_right_valid": weak_vr,
            "prior_keep": keep, "prior_reject": reject,
            "prior_untestable": untestable,
            "prior_disparity_difference": difference,
            "prior_removed_from_constraints": np.isfinite(sparse) & ~keep,
            "arms": arms, "receipt": cfg_receipt}
