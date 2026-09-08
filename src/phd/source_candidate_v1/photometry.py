"""Source-symmetric, finite-support plane scoring in undistorted images.

This is a custom ZNCC evaluator, not a reproduction of COLMAP PatchMatch.
It consumes no reference/GT geometry and makes no source decision. All nominal
source contrasts use identical camera pairs, reference pixels and pixel masks.
Depth contexts describe MODEL_SELF_VISIBILITY only: absent depth is UNKNOWN,
and a current MVS depth map must never be supplied as the ALS visibility map.

Camera convention: X_camera = X_world @ R.T + t. ``pixel_center_offset`` is
zero for the native integer-center COLMAP calibration used by this experiment.
Set it to 0.5 only when the supplied calibration has actually been converted.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from itertools import combinations
from typing import Any

import cv2
import numpy as np
from scipy.spatial import cKDTree


@dataclass(frozen=True)
class ScoringConfig:
    max_views: int = 12
    max_pairs: int = 12
    max_patch_centers: int = 9
    patch_width: int = 9
    max_anchor_radius_px: float = 16.0
    angle_min_deg: float = 2.0
    angle_max_deg: float = 45.0
    resolution_ratio_max: float = 2.0
    preferred_angle_deg: float = 12.0
    support_tolerance_m: float = 0.6
    minimum_patch_fraction: float = 0.75
    minimum_patch_pixels: int = 40
    minimum_patch_std: float = 3.0
    low_target_texture_cost: float = 0.5
    visibility_tolerance_m: float = 0.75
    profile_offsets_m: tuple[float, ...] = (-2.0, -1.0, -0.5, 0.0, 0.5, 1.0, 2.0)
    profile_shift_axis: str = "normal"
    pixel_center_offset: float = 0.0


def _config(value: ScoringConfig | dict | None) -> ScoringConfig:
    result = value if isinstance(value, ScoringConfig) else ScoringConfig(**(value or {}))
    if result.patch_width < 3 or result.patch_width % 2 == 0:
        raise ValueError("patch_width must be an odd integer >= 3")
    if result.max_patch_centers < 1 or result.max_pairs < 1 or result.max_views < 2:
        raise ValueError("positive sample/pair budgets and >= 2 views are required")
    if result.profile_shift_axis not in {"normal", "z"}:
        raise ValueError("profile_shift_axis must be normal or z")
    if 0.0 not in result.profile_offsets_m:
        raise ValueError("profile_offsets_m must include zero")
    return result


def project(points: np.ndarray, view: dict) -> tuple[np.ndarray, np.ndarray]:
    """Project world points using the supplied camera's unmodified calibration."""
    camera = np.asarray(points, dtype=np.float64) @ np.asarray(view["R"]).T + view["t"]
    homogeneous = camera @ np.asarray(view["K"]).T
    with np.errstate(divide="ignore", invalid="ignore"):
        pixels = homogeneous[..., :2] / homogeneous[..., 2, None]
    return pixels, camera[..., 2]


def _inside(pixels: np.ndarray, view: dict, cfg: ScoringConfig) -> np.ndarray:
    p = pixels - cfg.pixel_center_offset
    return (np.isfinite(p).all(-1) & (p[..., 0] >= 0) & (p[..., 1] >= 0)
            & (p[..., 0] <= view["width"] - 1) & (p[..., 1] <= view["height"] - 1))


def _sample_gray(pixels: np.ndarray, view: dict, cfg: ScoringConfig) -> np.ndarray:
    p = np.where(np.isfinite(pixels), pixels - cfg.pixel_center_offset, -1e6)
    return cv2.remap(np.asarray(view["gray"], dtype=np.float32),
                     np.ascontiguousarray(p[..., 0], dtype=np.float32),
                     np.ascontiguousarray(p[..., 1], dtype=np.float32),
                     cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=0)


def _prepare_candidate(candidate: dict, cfg: ScoringConfig) -> dict:
    center = np.asarray(candidate["center"], dtype=np.float64)
    normal = np.asarray(candidate["normal"], dtype=np.float64)
    support = np.asarray(candidate["support_points"], dtype=np.float64)
    if center.shape != (3,) or normal.shape != (3,) or support.ndim != 2 or support.shape[1] != 3:
        raise ValueError("candidate center/normal must be xyz; support_points must be Nx3")
    length = np.linalg.norm(normal)
    if length < 1e-9 or not np.isfinite(normal).all() or not np.isfinite(center).all():
        raise ValueError("candidate plane must be finite with nonzero normal")
    support = support[np.isfinite(support).all(1)]
    normal = normal / length
    axis = np.eye(3)[np.argmin(np.abs(normal))]
    tangent = np.cross(normal, axis)
    tangent /= np.linalg.norm(tangent)
    basis = np.column_stack((tangent, np.cross(normal, tangent)))
    return {**candidate, "center": center, "normal": normal, "support_points": support,
            "basis": basis, "tree": cKDTree((support - center) @ basis),
            "support_tolerance_m": float(candidate.get("support_tolerance_m", cfg.support_tolerance_m))}


def _intersect(pixels: np.ndarray, view: dict, candidate: dict,
               offset: float, cfg: ScoringConfig) -> tuple[np.ndarray, np.ndarray]:
    homogeneous = np.concatenate((pixels, np.ones((*pixels.shape[:-1], 1))), axis=-1)
    directions = homogeneous @ np.linalg.inv(view["K"]).T @ view["R"]
    camera_center = np.asarray(view["center"], dtype=np.float64)
    shift = candidate["normal"] if cfg.profile_shift_axis == "normal" else np.array([0., 0., 1.])
    translated_center = candidate["center"] + offset * shift
    denominator = directions @ candidate["normal"]
    with np.errstate(divide="ignore", invalid="ignore"):
        distance = ((translated_center - camera_center) @ candidate["normal"]) / denominator
    xyz = camera_center + distance[..., None] * directions
    valid = np.isfinite(xyz).all(-1) & (distance > 0) & (np.abs(denominator) > 1e-8)
    # Evaluate in the translated candidate's native tangential support, never an
    # infinite plane or the competing source's convex hull.
    coordinates = (xyz - translated_center) @ candidate["basis"]
    query = np.where(np.isfinite(coordinates), coordinates, 1e30)
    nearest = candidate["tree"].query(query.reshape(-1, 2), workers=1)[0].reshape(valid.shape)
    valid &= nearest <= candidate["support_tolerance_m"]
    return xyz, valid


def _visibility(pixels: np.ndarray, z: np.ndarray, view: dict, candidate: dict,
                cfg: ScoringConfig) -> tuple[np.ndarray, np.ndarray]:
    """Return not-model-occluded and model-depth-matched; unknown stays unmatched."""
    contexts = candidate.get("context_depths", {})
    context = contexts.get(view["id"], contexts.get(str(view["id"])))
    if context is None:
        return np.ones(z.shape, bool), np.zeros(z.shape, bool)
    if isinstance(context, dict):
        depth = np.asarray(context["depth"])
        sx = float(context.get("scale_x", depth.shape[1] / view["width"]))
        sy = float(context.get("scale_y", depth.shape[0] / view["height"]))
    else:
        depth = np.asarray(context)
        sx, sy = depth.shape[1] / view["width"], depth.shape[0] / view["height"]
    p = np.where(np.isfinite(pixels), pixels - cfg.pixel_center_offset, -1e6)
    ix = np.floor((p[..., 0] + 0.5) * sx).astype(np.int64)
    iy = np.floor((p[..., 1] + 0.5) * sy).astype(np.int64)
    inside = (ix >= 0) & (iy >= 0) & (ix < depth.shape[1]) & (iy < depth.shape[0])
    d = depth[np.clip(iy, 0, depth.shape[0] - 1), np.clip(ix, 0, depth.shape[1] - 1)]
    known = inside & np.isfinite(d) & (d > 0)
    not_occluded = ~known | (z <= d + cfg.visibility_tolerance_m)
    matched = known & (np.abs(z - d) <= cfg.visibility_tolerance_m)
    return not_occluded, matched


def _pair_geometry(views: list[dict], candidates: dict, cfg: ScoringConfig) -> list[dict]:
    center = np.mean([c["center"] for c in candidates.values()], axis=0)
    eligible = []
    for view in views:
        uv, z = project(center[None], view)
        if z[0] <= 0 or not _inside(uv, view, cfg)[0]:
            continue
        scale = float(np.sqrt(view["K"][0, 0] * view["K"][1, 1]) / z[0])
        margin = float(np.min(np.r_[uv[0], [view["width"] - 1, view["height"] - 1] - uv[0]]))
        eligible.append((margin, str(view["id"]), scale, view))
    eligible.sort(key=lambda x: (-x[0], x[1]))
    eligible = eligible[:cfg.max_views]
    all_pairs = []
    for first, second in combinations(eligible, 2):
        _, _, sa, a = first
        _, _, sb, b = second
        da, db = np.asarray(a["center"]) - center, np.asarray(b["center"]) - center
        angle = float(np.degrees(np.arccos(np.clip(da @ db / (np.linalg.norm(da) * np.linalg.norm(db)), -1, 1))))
        ratio = max(sa, sb) / min(sa, sb)
        if not cfg.angle_min_deg <= angle <= cfg.angle_max_deg or ratio > cfg.resolution_ratio_max:
            continue
        # Stable reference order is determined by camera IDs, never source cost.
        if str(a["id"]) > str(b["id"]):
            a, b = b, a
        all_pairs.append({"reference": a, "target": b,
                          "pair_id": f"{a['id']}->{b['id']}", "angle_deg": angle,
                          "rank": abs(angle - cfg.preferred_angle_deg) + 2 * abs(np.log(ratio))})
    all_pairs.sort(key=lambda p: (p["rank"], p["pair_id"]))
    # Seed the budget with disjoint camera groups so a good star graph cannot
    # masquerade as independent multiview support.
    selected, used = [], set()
    for pair in all_pairs:
        ids = {str(pair["reference"]["id"]), str(pair["target"]["id"])}
        if not ids & used and len(selected) < cfg.max_pairs:
            selected.append(pair)
            used |= ids
    selected_ids = {p["pair_id"] for p in selected}
    selected.extend(p for p in all_pairs if p["pair_id"] not in selected_ids)
    return selected[:cfg.max_pairs]


def _patch_pixels(view: dict, candidates: dict, cfg: ScoringConfig,
                  reference_pixels: Any = None) -> np.ndarray:
    if reference_pixels is not None:
        anchors = np.asarray(reference_pixels, dtype=float).reshape(-1, 2)
    else:
        centers, _ = project(np.array([c["center"] for c in candidates.values()]), view)
        midpoint = centers.mean(0)
        points = np.concatenate([c["support_points"] for c in candidates.values()])
        projected, z = project(points, view)
        projected = projected[(z > 0) & np.isfinite(projected).all(1)]
        if len(projected):
            low, high = np.quantile(projected, [0.1, 0.9], axis=0)
            radius = np.minimum(np.maximum((high - low) / 4, 1), cfg.max_anchor_radius_px)
        else:
            radius = np.ones(2)
        side = int(np.ceil(np.sqrt(cfg.max_patch_centers)))
        gx, gy = np.meshgrid(np.linspace(-1, 1, side), np.linspace(-1, 1, side))
        anchors = midpoint + np.column_stack((gx.ravel(), gy.ravel()))[:cfg.max_patch_centers] * radius
    # Integer sample centers provide reproducible image IDs under native K.
    anchors = np.round(anchors - cfg.pixel_center_offset) + cfg.pixel_center_offset
    anchors = np.unique(anchors, axis=0)
    radius = cfg.patch_width // 2
    dx, dy = np.meshgrid(np.arange(-radius, radius + 1), np.arange(-radius, radius + 1))
    return anchors[:, None, :] + np.column_stack((dx.ravel(), dy.ravel()))[None]


def _warp(pixels: np.ndarray, reference: dict, target: dict, candidate: dict,
          cfg: ScoringConfig, offset: float = 0, use_context: bool = True) -> dict:
    xyz, supported = _intersect(pixels, reference, candidate, offset, cfg)
    target_pixels, target_z = project(xyz, target)
    _, reference_z = project(xyz, reference)
    geometric = (supported & _inside(pixels, reference, cfg)
                 & _inside(target_pixels, target, cfg) & (target_z > 0))
    if use_context:
        ref_open, ref_matched = _visibility(pixels, reference_z, reference, candidate, cfg)
        tgt_open, tgt_matched = _visibility(target_pixels, target_z, target, candidate, cfg)
    else:
        ref_open = tgt_open = np.ones(geometric.shape, bool)
        ref_matched = tgt_matched = np.zeros(geometric.shape, bool)
    return {"values": _sample_gray(target_pixels, target, cfg), "geometric": geometric,
            "valid": geometric & ref_open & tgt_open,
            "verified": geometric & ref_matched & tgt_matched}


def _cost(reference: np.ndarray, target: np.ndarray, mask: np.ndarray,
          cfg: ScoringConfig) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    weights = mask.astype(float)
    n = mask.sum(1)
    a = (reference - (reference * weights).sum(1)[:, None] / np.maximum(n[:, None], 1)) * weights
    b = (target - (target * weights).sum(1)[:, None] / np.maximum(n[:, None], 1)) * weights
    va, vb = (a * a).sum(1), (b * b).sum(1)
    std_a = np.sqrt(va / np.maximum(n, 1))
    std_b = np.sqrt(vb / np.maximum(n, 1))
    enough = (n >= cfg.minimum_patch_pixels) & (n >= mask.shape[1] * cfg.minimum_patch_fraction)
    reference_textured = std_a >= cfg.minimum_patch_std
    low_target = (std_b < cfg.minimum_patch_std) & enough & reference_textured
    correlation = np.clip((a * b).sum(1) / np.sqrt(np.maximum(va * vb, 1e-20)), -1, 1)
    costs = (1 - correlation) / 2
    # A wrong, flat target receives the no-correlation cost; it cannot erase a
    # textured competitor's measurement. A flat REFERENCE leaves both unscored.
    costs[low_target] = cfg.low_target_texture_cost
    costs[~(enough & reference_textured)] = np.nan
    return costs, reference_textured & enough, low_target


def _number(values: list | np.ndarray) -> float | None:
    values = np.asarray(values, dtype=float)
    values = values[np.isfinite(values)]
    return float(np.median(values)) if len(values) else None


def _disjoint_count(pairs: list[tuple[str, str]]) -> int:
    """Maximum matching size for <=16 camera vertices, using a small bitmask DP."""
    vertices = sorted({v for pair in pairs for v in pair})
    if not vertices:
        return 0
    indices = {v: i for i, v in enumerate(vertices)}
    neighbors = [0] * len(vertices)
    for a, b in pairs:
        neighbors[indices[a]] |= 1 << indices[b]
        neighbors[indices[b]] |= 1 << indices[a]
    cache = {}
    def solve(mask):
        if mask == 0:
            return 0
        if mask in cache:
            return cache[mask]
        bit = mask & -mask
        vertex = bit.bit_length() - 1
        remaining = mask ^ bit
        best = solve(remaining)
        options = neighbors[vertex] & remaining
        while options:
            other = options & -options
            best = max(best, 1 + solve(remaining ^ other))
            options ^= other
        cache[mask] = best
        return best
    return solve((1 << len(vertices)) - 1)


def score_candidates(candidates: dict[str, dict], views: list[dict],
                     config: ScoringConfig | dict | None = None,
                     reference_pixels: dict | np.ndarray | None = None) -> dict:
    """Score exactly two source planes without deciding which source is valid.

    Candidate: center, normal, support_points, valid (default True), optional
    support_tolerance_m/context_depths. View: id,R,t,K,center,width,height,gray.
    ``gray`` is native undistorted intensity on the 0..255 scale, not normalized.
    Optional reference_pixels maps reference camera ID to Nx2 calibrated pixels,
    or supplies one Nx2 array for all reference cameras (mainly synthetic tests).
    Output contains JSON-safe values; visibility fractions concern source models
    and are neither verified current geometry nor free-space observations.
    """
    cfg = _config(config)
    if len(candidates) != 2:
        raise ValueError("exactly two source candidates are required for matched contrast")
    names = sorted(candidates)
    result = {"status": "invalid_candidates", "config": asdict(cfg), "candidates": {},
              "shared": {"selected_pairs": [], "pair_count": 0, "distinct_view_count": 0,
                         "disjoint_pair_count": 0, "common_patch_count": 0,
                         "common_scored_pair_count": 0,
                         "common_visibility_verified_fraction": 0.,
                         "visibility_semantics": "MODEL_SELF_VISIBILITY"},
              "contrast": {"source_order": names, "cost_first_minus_second": None,
                           "cost_mvs_minus_als": None, "paired_differences": []},
              "limitations": ["Observation compatibility is not calibrated source correctness.",
                              "Visibility is source model self-visibility; missing depth is UNKNOWN.",
                              "Current-image candidate construction and scoring images may be dependent.",
                              "Offset profiles use shifted native support and nominal visibility; profile coverage varies."]}
    for name in names:
        result["candidates"][name] = {"cost": None, "median_ncc": None, "support_patch_count": 0,
            "textured_patch_count": 0, "low_target_texture_count": 0, "pairs": [], "profile": [],
            "profile_range": None, "profile_best_offset_m": None}
    if any(not c.get("valid", True) or len(c.get("support_points", [])) < 3 for c in candidates.values()):
        return result
    prepared = {name: _prepare_candidate(candidates[name], cfg) for name in names}
    pairs = _pair_geometry(views, prepared, cfg)
    shared = result["shared"]
    shared["selected_pairs"] = [{"pair_id": p["pair_id"], "reference_id": p["reference"]["id"],
        "target_id": p["target"]["id"], "angle_deg": p["angle_deg"]} for p in pairs]
    shared["pair_count"] = len(pairs)
    if not pairs:
        result["status"] = "insufficient_views"
        return result
    pair_costs = {name: [] for name in names}
    profiles = {name: {float(o): {"costs": [], "paired_nominal": [], "paired_delta": [],
                                 "count": 0, "nominal_count": 0}
                       for o in cfg.profile_offsets_m} for name in names}
    scored_edges, all_verified, all_common = [], 0, 0
    for pair in pairs:
        reference, target = pair["reference"], pair["target"]
        if isinstance(reference_pixels, dict):
            anchors = reference_pixels.get(reference["id"], reference_pixels.get(str(reference["id"])))
        else:
            anchors = reference_pixels
        pixels = _patch_pixels(reference, prepared, cfg, anchors)
        reference_values = _sample_gray(pixels, reference, cfg)
        warps = {name: _warp(pixels, reference, target, c, cfg) for name, c in prepared.items()}
        common = np.logical_and.reduce([w["valid"] for w in warps.values()])
        verified = np.logical_and.reduce([w["verified"] for w in warps.values()]) & common
        all_verified += int(verified.sum())
        all_common += int(common.sum())
        enough = ((common.sum(1) >= cfg.minimum_patch_pixels)
                  & (common.sum(1) >= common.shape[1] * cfg.minimum_patch_fraction))
        shared["common_patch_count"] += int(enough.sum())
        pair_medians = {}
        for name in names:
            candidate_result = result["candidates"][name]
            costs, textured, low_target = _cost(reference_values, warps[name]["values"], common, cfg)
            count = int(np.isfinite(costs).sum())
            nominal_median = _number(costs)
            pair_medians[name] = nominal_median
            if nominal_median is not None:
                pair_costs[name].append(nominal_median)
            supported = warps[name]["geometric"].sum(1)
            candidate_result["support_patch_count"] += int(((supported >= cfg.minimum_patch_pixels)
                & (supported >= common.shape[1] * cfg.minimum_patch_fraction)).sum())
            candidate_result["textured_patch_count"] += int(textured.sum())
            candidate_result["low_target_texture_count"] += int(low_target.sum())
            candidate_result["pairs"].append({"pair_id": pair["pair_id"], "cost": nominal_median,
                "ncc": None if nominal_median is None else 1 - 2 * nominal_median,
                "common_patch_count": count, "verified_visibility_fraction":
                    float(verified.sum() / max(common.sum(), 1)),
                "reference_pixel_centers": pixels[:, pixels.shape[1] // 2].tolist()})
            # Controls do not query the unshifted own-source depth buffer: doing
            # so would penalize a shifted plane solely for leaving its source.
            for offset in profiles[name]:
                if offset == 0:
                    profile_costs = costs
                    paired_nominal = costs
                else:
                    shifted = _warp(pixels, reference, target, prepared[name], cfg, offset, use_context=False)
                    profile_mask = common & shifted["valid"]
                    profile_costs, _, _ = _cost(reference_values, shifted["values"],
                                               profile_mask, cfg)
                    paired_nominal, _, _ = _cost(reference_values, warps[name]["values"],
                                                 profile_mask, cfg)
                    profile_costs[~np.isfinite(costs)] = np.nan
                    paired_nominal[~np.isfinite(costs)] = np.nan
                entry = profiles[name][offset]
                median = _number(profile_costs)
                if median is not None:
                    entry["costs"].append(median)
                    entry["paired_nominal"].append(_number(paired_nominal))
                    entry["paired_delta"].append(_number(profile_costs - paired_nominal))
                entry["count"] += int(np.isfinite(profile_costs).sum())
                entry["nominal_count"] += count
        if all(pair_medians[n] is not None for n in names):
            scored_edges.append((str(reference["id"]), str(target["id"])))
            difference = pair_medians[names[0]] - pair_medians[names[1]]
            result["contrast"]["paired_differences"].append({"pair_id": pair["pair_id"],
                "cost_first_minus_second": difference,
                "cost_mvs_minus_als": pair_medians["mvs"] - pair_medians["als"] if set(names) == {"mvs", "als"} else None})
    shared["common_scored_pair_count"] = len(scored_edges)
    shared["distinct_view_count"] = len({v for edge in scored_edges for v in edge})
    shared["disjoint_pair_count"] = _disjoint_count(scored_edges)
    shared["common_visibility_verified_fraction"] = all_verified / max(all_common, 1)
    for name in names:
        out = result["candidates"][name]
        out["cost"] = _number(pair_costs[name])
        out["median_ncc"] = None if out["cost"] is None else 1 - 2 * out["cost"]
        for offset, entry in profiles[name].items():
            out["profile"].append({"offset_m": offset, "cost": _number(entry["costs"]),
                "paired_nominal_cost": _number(entry["paired_nominal"]),
                "paired_delta_cost": _number(entry["paired_delta"]),
                "common_patch_count": entry["count"],
                "coverage_fraction": entry["count"] / max(entry["nominal_count"], 1)})
        finite = [p for p in out["profile"] if p["cost"] is not None]
        if finite:
            out["profile_range"] = float(max(p["cost"] for p in finite) - min(p["cost"] for p in finite))
            out["profile_best_offset_m"] = min(finite, key=lambda p: (p["cost"], abs(p["offset_m"])))["offset_m"]
    if scored_edges:
        diffs = result["contrast"]["paired_differences"]
        result["contrast"]["cost_first_minus_second"] = _number([d["cost_first_minus_second"] for d in diffs])
        if set(names) == {"mvs", "als"}:
            result["contrast"]["cost_mvs_minus_als"] = _number([d["cost_mvs_minus_als"] for d in diffs])
    result["status"] = ("no_common_support" if shared["common_patch_count"] == 0 else
        "untextured" if not scored_edges else
        "insufficient_views" if shared["disjoint_pair_count"] < 2 or shared["distinct_view_count"] < 4 else "ok")
    return result
