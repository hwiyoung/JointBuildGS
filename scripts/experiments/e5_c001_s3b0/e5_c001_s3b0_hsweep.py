#!/usr/bin/env python3
"""S3-B step-0b full-frame outline observability and GT-free h-sweep.

Height estimation uses only source imagery, fixed COLMAP poses, supplied
footprints, cached image-derived FM ground, and the non-GT 0-e neighbor masks.
LoD2 is loaded only after every height/segment peak has been fixed in memory.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import os
import platform
from collections import defaultdict
from pathlib import Path
from typing import Any, Sequence

os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib")
os.environ.setdefault("XDG_CACHE_HOME", "/tmp")

import cv2
import matplotlib
import numpy as np
from PIL import Image as PILImage

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

import e5_c001_s3b0_common as common


OUTLINE_FIELDS = [
    "building_id",
    "view_stem",
    "source_image",
    "source_width_px",
    "source_height_px",
    "provisional_height_source",
    "provisional_plane_ax_local",
    "provisional_plane_by_local",
    "provisional_plane_c_local",
    "outline_sample_count",
    "positive_depth_sample_count",
    "in_frame_sample_count",
    "in_frame_fraction",
    "unique_in_frame_pixel_count",
    "frame_cut",
    "semantic_exclusion_known_pixel_count",
    "semantic_exclusion_known_fraction",
    "target_mask_overlap_pixel_count",
    "target_mask_overlap_fraction",
    "neighbor_mask_overlap_pixel_count",
    "occlusion_estimate_fraction",
    "neighbor_excluded_pixel_count",
    "edge_valid_pixel_count",
    "edge_response_sum",
    "edge_response_mean",
    "edge_response_median",
    "edge_response_p10",
    "edge_definition",
    "semantic_mask_scope",
    "semantic_mask_npz",
    "semantic_mask_sha256",
    "gt_used_for_measurement",
    "lod2_used_for_measurement",
    "als_used_for_measurement",
    "learning_runs_started",
    "new_inference_runs",
    "status",
    "note",
]


HSWEEP_FIELDS = [
    "row_type",
    "building_id",
    "view_stem",
    "segment_index",
    "segment_length_m",
    "segment_midpoint_e_utm",
    "segment_midpoint_n_utm",
    "height_stage",
    "height_local_m",
    "height_above_ground_m",
    "edge_score_sum",
    "edge_score_mean",
    "outline_sample_count",
    "positive_depth_sample_count",
    "in_frame_sample_count",
    "unique_in_frame_pixel_count",
    "neighbor_excluded_pixel_count",
    "semantic_exclusion_known_pixel_count",
    "contributing_view_count",
    "h_est_local_m",
    "h_est_above_ground_m",
    "peak_score",
    "background_median_score",
    "peak_to_background_ratio",
    "peak_status",
    "view_h_est_median_local_m",
    "view_h_est_mad_m",
    "view_h_est_std_m",
    "view_h_est_range_m",
    "ground_z_local_m",
    "fm_anchor_z_local_m",
    "reference_roof_z_local_m",
    "delta_h_vs_fm_anchor_m",
    "delta_h_vs_reference_m",
    "segment_plane_anchor_count",
    "segment_plane_ax_local",
    "segment_plane_by_local",
    "segment_plane_c_local",
    "segment_plane_anchor_rms_m",
    "variant",
    "scope",
    "distance_lower_m",
    "distance_upper_m",
    "point_count",
    "signed_delta_z_median_m",
    "signed_delta_z_mad_m",
    "abs_delta_z_median_m",
    "rms_delta_z_m",
    "p0_signed_delta_z_median_m",
    "p0_abs_delta_z_median_m",
    "p0_rms_delta_z_m",
    "delta_signed_median_vs_p0_m",
    "delta_abs_median_vs_p0_m",
    "delta_rms_vs_p0_m",
    "edge_definition",
    "score_definition",
    "semantic_mask_scope",
    "gt_used_for_estimation",
    "lod2_used_for_estimation",
    "als_used_for_estimation",
    "gt_used_for_posthoc_score",
    "lod2_used_for_posthoc_score",
    "als_used_for_posthoc_score",
    "learning_runs_started",
    "new_inference_runs",
    "status",
    "note",
]

ANCHOR_FIELDS = [
    "building_id",
    "segment_index",
    "segment_length_m",
    "segment_midpoint_e_utm",
    "segment_midpoint_n_utm",
    "h_est_local_m",
    "h_est_above_ground_m",
    "peak_score",
    "background_median_score",
    "peak_to_background_ratio",
    "peak_status",
    "ground_z_local_m",
    "edge_definition",
    "score_definition",
    "semantic_mask_scope",
    "gt_used",
    "lod2_used",
    "als_used",
    "learning_runs_started",
    "new_inference_runs",
    "status",
]


def gradient_magnitude(image_rgb: np.ndarray) -> np.ndarray:
    gray = cv2.cvtColor(np.asarray(image_rgb, dtype=np.uint8), cv2.COLOR_RGB2GRAY)
    value = gray.astype(np.float64) / 255.0
    grad_y, grad_x = np.gradient(value)
    return np.hypot(grad_x, grad_y)


def regular_grid(lower: float, upper: float, step: float) -> np.ndarray:
    count = int(round((upper - lower) / step))
    values = lower + np.arange(count + 1, dtype=np.float64) * step
    if abs(values[-1] - upper) > 1e-8:
        raise RuntimeError(f"grid endpoint drift: {values[-1]} vs {upper}")
    return np.round(values, 10)


def fine_grid(
    centre: float,
    lower: float,
    upper: float,
    half_width: float,
    step: float,
) -> np.ndarray:
    start = max(lower, centre - half_width)
    stop = min(upper, centre + half_width)
    count = int(round((stop - start) / step))
    return np.round(start + np.arange(count + 1, dtype=np.float64) * step, 10)


def select_peak(
    heights: np.ndarray,
    scores: np.ndarray,
    parent_centre: float | None = None,
) -> tuple[int, str]:
    h = np.asarray(heights, dtype=np.float64)
    s = np.asarray(scores, dtype=np.float64)
    if len(h) != len(s) or not len(h):
        raise ValueError("height/score vectors must have equal nonzero length")
    maximum = float(np.max(s))
    candidates = np.flatnonzero(np.isclose(s, maximum, rtol=0.0, atol=1e-12))
    centre = float(parent_centre) if parent_centre is not None else float(np.median(h))
    order = sorted(candidates.tolist(), key=lambda index: (abs(float(h[index]) - centre), float(h[index])))
    index = int(order[0])
    if maximum <= 0.0:
        status = "zero_curve"
    elif len(candidates) > 1:
        status = "tied_positive_peak"
    elif index in (0, len(h) - 1):
        status = "boundary_positive_peak"
    else:
        status = "interior_positive_peak"
    return index, status


def peak_statistics(
    coarse_heights: np.ndarray,
    coarse_scores: np.ndarray,
    h_est: float,
    peak_score: float,
    exclusion_half_width: float,
) -> tuple[float | None, float | None]:
    background = np.asarray(coarse_scores, dtype=np.float64)[
        np.abs(np.asarray(coarse_heights, dtype=np.float64) - float(h_est))
        > float(exclusion_half_width)
    ]
    if not len(background):
        return None, None
    median = float(np.median(background))
    ratio = float(peak_score / median) if median > 0 else None
    return median, ratio


def densify_segment(left: np.ndarray, right: np.ndarray, step_m: float) -> np.ndarray:
    left = np.asarray(left, dtype=np.float64).reshape(2)
    right = np.asarray(right, dtype=np.float64).reshape(2)
    length = float(np.linalg.norm(right - left))
    count = max(1, int(math.ceil(length / float(step_m))))
    fractions = np.arange(count, dtype=np.float64) / count
    return left[None, :] + fractions[:, None] * (right - left)[None, :]


def boundary_segments(footprint: Any, step_m: float) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    index = 0
    for polygon_index, polygon in enumerate(common.flatten_polygons(footprint), 1):
        ring = np.asarray(polygon.exterior.coords, dtype=np.float64)
        for edge_index, (left, right) in enumerate(zip(ring[:-1], ring[1:]), 1):
            index += 1
            output.append(
                {
                    "segment_index": index,
                    "polygon_index": polygon_index,
                    "edge_index": edge_index,
                    "left": left,
                    "right": right,
                    "midpoint": (left + right) / 2.0,
                    "length_m": float(np.linalg.norm(right - left)),
                    "points": densify_segment(left, right, step_m),
                }
            )
    if not output:
        raise RuntimeError("footprint has no exterior segments")
    return output


def all_boundary_points(segments: Sequence[dict[str, Any]]) -> np.ndarray:
    return np.vstack([np.asarray(segment["points"], dtype=np.float64) for segment in segments])


def native_masks(
    mask_path: Path,
    crop_box: Sequence[int],
    source_shape_hw: tuple[int, int],
) -> tuple[np.ndarray, np.ndarray, np.ndarray, dict[str, Any]]:
    with np.load(mask_path, allow_pickle=False) as archive:
        target_crop = np.asarray(archive["target_mask"], dtype=bool)
        neighbor_crop = np.asarray(archive["neighbor_mask"], dtype=bool)
        metadata = json.loads(str(archive["metadata_json"].item()))
    height, width = source_shape_hw
    target = np.zeros((height, width), dtype=bool)
    neighbor = np.zeros((height, width), dtype=bool)
    known = np.zeros((height, width), dtype=bool)
    x0, y0, x1, y1 = (int(value) for value in crop_box)
    if target_crop.shape != (y1 - y0, x1 - x0):
        raise RuntimeError(f"0-e mask/crop-box shape drift: {mask_path}")
    target[y0:y1, x0:x1] = target_crop
    neighbor[y0:y1, x0:x1] = neighbor_crop
    known[y0:y1, x0:x1] = True
    return target, neighbor, known, metadata


def project_native(
    xy_utm: np.ndarray,
    z_local: np.ndarray | float,
    view: dict[str, Any],
    offset: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    xy = np.asarray(xy_utm, dtype=np.float64).reshape(-1, 2)
    z = np.broadcast_to(np.asarray(z_local, dtype=np.float64), (len(xy),))
    local = np.column_stack([xy[:, 0] - offset[0], xy[:, 1] - offset[1], z])
    rotation = np.asarray(view["R_w2c"], dtype=np.float64)
    translation = np.asarray(view["t_w2c"], dtype=np.float64)
    camera = local @ rotation.T + translation[None, :]
    intrinsic = np.asarray(view["K_source"], dtype=np.float64)
    uvw = camera @ intrinsic.T
    uv = np.full((len(xy), 2), np.nan, dtype=np.float64)
    positive = camera[:, 2] > 1e-9
    uv[positive] = uvw[positive, :2] / uvw[positive, 2:3]
    return uv, camera[:, 2]


def sample_outline(
    xy_utm: np.ndarray,
    z_local: np.ndarray | float,
    view: dict[str, Any],
    offset: np.ndarray,
    gradient: np.ndarray,
    target_mask: np.ndarray,
    neighbor_mask: np.ndarray,
    semantic_known: np.ndarray,
) -> dict[str, Any]:
    uv, depth = project_native(xy_utm, z_local, view, offset)
    height, width = gradient.shape
    positive = np.isfinite(uv).all(axis=1) & np.isfinite(depth) & (depth > 1e-9)
    rounded = np.zeros((len(uv), 2), dtype=np.int64)
    rounded[positive] = np.rint(uv[positive]).astype(np.int64)
    in_frame = (
        positive
        & (rounded[:, 0] >= 0)
        & (rounded[:, 0] < width)
        & (rounded[:, 1] >= 0)
        & (rounded[:, 1] < height)
    )
    sampled = rounded[in_frame]
    if len(sampled):
        linear = sampled[:, 1] * width + sampled[:, 0]
        _, first = np.unique(linear, return_index=True)
        pixels = sampled[np.sort(first)]
    else:
        pixels = np.empty((0, 2), dtype=np.int64)
    if len(pixels):
        values = gradient[pixels[:, 1], pixels[:, 0]]
        target = target_mask[pixels[:, 1], pixels[:, 0]]
        neighbor = neighbor_mask[pixels[:, 1], pixels[:, 0]]
        known = semantic_known[pixels[:, 1], pixels[:, 0]]
    else:
        values = np.empty(0, dtype=np.float64)
        target = neighbor = known = np.empty(0, dtype=bool)
    # The commissioned score requires neighbor-edge exclusion.  The 0-e
    # non-GT mask exists only inside the locked native crop, so pixels outside
    # that known region remain part of frame-observability counts but cannot
    # enter the edge score.
    usable = known & ~neighbor
    valid_values = values[usable & np.isfinite(values)]
    return {
        "outline_sample_count": int(len(xy_utm)),
        "positive_depth_sample_count": int(positive.sum()),
        "in_frame_sample_count": int(in_frame.sum()),
        "in_frame_fraction": float(in_frame.sum() / len(xy_utm)) if len(xy_utm) else None,
        "unique_in_frame_pixel_count": int(len(pixels)),
        "frame_cut": bool(int(in_frame.sum()) < len(xy_utm)),
        "semantic_exclusion_known_pixel_count": int(known.sum()),
        "semantic_exclusion_known_fraction": float(known.mean()) if len(known) else None,
        "target_mask_overlap_pixel_count": int(target.sum()),
        "target_mask_overlap_fraction": float(target.mean()) if len(target) else None,
        "neighbor_mask_overlap_pixel_count": int(neighbor.sum()),
        "occlusion_estimate_fraction": float(neighbor.mean()) if len(neighbor) else None,
        "neighbor_excluded_pixel_count": int(neighbor.sum()),
        "edge_valid_pixel_count": int(len(valid_values)),
        "edge_response_sum": float(np.sum(valid_values)) if len(valid_values) else 0.0,
        "edge_response_mean": float(np.mean(valid_values)) if len(valid_values) else None,
        "edge_response_median": float(np.median(valid_values)) if len(valid_values) else None,
        "edge_response_p10": float(np.quantile(valid_values, 0.10)) if len(valid_values) else None,
    }


def curve_for_context(
    points_utm: np.ndarray,
    heights: np.ndarray,
    context: dict[str, Any],
    offset: np.ndarray,
) -> list[dict[str, Any]]:
    return [
        sample_outline(
            points_utm,
            float(height),
            context["view"],
            offset,
            context["gradient"],
            context["target_full"],
            context["neighbor_full"],
            context["known_full"],
        )
        for height in heights
    ]


def aggregate_curves(curves: Sequence[Sequence[dict[str, Any]]]) -> list[dict[str, Any]]:
    if not curves:
        return []
    output: list[dict[str, Any]] = []
    for index in range(len(curves[0])):
        rows = [curve[index] for curve in curves]
        valid_means = [
            float(row["edge_response_mean"])
            for row in rows
            if row["edge_response_mean"] is not None
        ]
        output.append(
            {
                "edge_response_sum": float(sum(row["edge_response_sum"] for row in rows)),
                "edge_response_mean": float(np.mean(valid_means)) if valid_means else None,
                "outline_sample_count": int(sum(row["outline_sample_count"] for row in rows)),
                "positive_depth_sample_count": int(
                    sum(row["positive_depth_sample_count"] for row in rows)
                ),
                "in_frame_sample_count": int(sum(row["in_frame_sample_count"] for row in rows)),
                "unique_in_frame_pixel_count": int(
                    sum(row["unique_in_frame_pixel_count"] for row in rows)
                ),
                "neighbor_excluded_pixel_count": int(
                    sum(row["neighbor_excluded_pixel_count"] for row in rows)
                ),
                "semantic_exclusion_known_pixel_count": int(
                    sum(row["semantic_exclusion_known_pixel_count"] for row in rows)
                ),
                "contributing_view_count": int(
                    sum(row["edge_valid_pixel_count"] > 0 for row in rows)
                ),
            }
        )
    return output


def curve_row(
    *,
    row_type: str,
    building_id: str,
    view_stem: str,
    segment: dict[str, Any] | None,
    stage: str,
    height: float,
    ground: float,
    measurement: dict[str, Any],
    lock: dict[str, Any],
) -> dict[str, Any]:
    hs = lock["hsweep_0b"]
    return {
        "row_type": row_type,
        "building_id": building_id,
        "view_stem": view_stem,
        "segment_index": segment["segment_index"] if segment else None,
        "segment_length_m": segment["length_m"] if segment else None,
        "segment_midpoint_e_utm": segment["midpoint"][0] if segment else None,
        "segment_midpoint_n_utm": segment["midpoint"][1] if segment else None,
        "height_stage": stage,
        "height_local_m": height,
        "height_above_ground_m": float(height - ground),
        "edge_score_sum": measurement["edge_response_sum"],
        "edge_score_mean": measurement["edge_response_mean"],
        "outline_sample_count": measurement["outline_sample_count"],
        "positive_depth_sample_count": measurement["positive_depth_sample_count"],
        "in_frame_sample_count": measurement["in_frame_sample_count"],
        "unique_in_frame_pixel_count": measurement["unique_in_frame_pixel_count"],
        "neighbor_excluded_pixel_count": measurement["neighbor_excluded_pixel_count"],
        "semantic_exclusion_known_pixel_count": measurement[
            "semantic_exclusion_known_pixel_count"
        ],
        "contributing_view_count": measurement.get(
            "contributing_view_count",
            int(measurement.get("edge_valid_pixel_count", 0) > 0),
        ),
        "edge_definition": hs["edge_definition"],
        "score_definition": hs["score_definition"],
        "semantic_mask_scope": hs["semantic_mask_scope"],
        "gt_used_for_estimation": False,
        "lod2_used_for_estimation": False,
        "als_used_for_estimation": False,
        "gt_used_for_posthoc_score": False,
        "lod2_used_for_posthoc_score": False,
        "als_used_for_posthoc_score": False,
        "learning_runs_started": 0,
        "new_inference_runs": 0,
        "status": "measured",
        "note": "",
    }


def metric_values(errors: np.ndarray) -> dict[str, float | None]:
    values = np.asarray(errors, dtype=np.float64)
    values = values[np.isfinite(values)]
    if not len(values):
        return {
            "signed_delta_z_median_m": None,
            "signed_delta_z_mad_m": None,
            "abs_delta_z_median_m": None,
            "rms_delta_z_m": None,
        }
    median = float(np.median(values))
    return {
        "signed_delta_z_median_m": median,
        "signed_delta_z_mad_m": float(np.median(np.abs(values - median))),
        "abs_delta_z_median_m": float(np.median(np.abs(values))),
        "rms_delta_z_m": float(np.sqrt(np.mean(values * values))),
    }


def nearest_distance(xy: np.ndarray, anchors: np.ndarray) -> np.ndarray:
    left = np.asarray(xy, dtype=np.float64).reshape(-1, 2)
    right = np.asarray(anchors, dtype=np.float64).reshape(-1, 2)
    return np.sqrt(
        np.min(np.sum((left[:, None, :] - right[None, :, :]) ** 2, axis=2), axis=1)
    )


def fit_anchor_plane(anchors_local: np.ndarray) -> tuple[np.ndarray | None, float | None]:
    values = np.asarray(anchors_local, dtype=np.float64).reshape(-1, 3)
    if len(values) < 3 or np.linalg.matrix_rank(
        np.column_stack([values[:, 0], values[:, 1], np.ones(len(values))])
    ) < 3:
        return None, None
    design = np.column_stack([values[:, 0], values[:, 1], np.ones(len(values))])
    plane = np.linalg.lstsq(design, values[:, 2], rcond=None)[0]
    residual = values[:, 2] - design @ plane
    return plane.astype(np.float64), float(np.sqrt(np.mean(residual * residual)))


def plot_curves(
    output_path: Path,
    building_id: str,
    measurement: dict[str, Any],
) -> None:
    ground = measurement["ground"]
    coarse_h = measurement["coarse_heights"]
    aggregate_coarse = measurement["aggregate_coarse_scores"]
    fine_h = measurement["fine_heights"]
    aggregate_fine = measurement["aggregate_fine_scores"]
    figure, axes = plt.subplots(1, 3, figsize=(16, 4.8))
    axes[0].plot(coarse_h - ground, aggregate_coarse, "o-", markersize=3, label="aggregate coarse")
    axes[0].plot(fine_h - ground, aggregate_fine, ".-", markersize=4, label="aggregate fine")
    axes[0].axvline(measurement["h_est"] - ground, color="black", linestyle="--", label="h_est")
    axes[0].axvline(
        measurement["fm_anchor"] - ground,
        color="#7f8c8d",
        linestyle=":",
        label="FM anchor",
    )
    if measurement.get("reference_z") is not None:
        axes[0].axvline(
            measurement["reference_z"] - ground,
            color="#8e44ad",
            linestyle="-.",
            label="reference score-only",
        )
    axes[0].set_xlabel("height above observed ground [m]")
    axes[0].set_ylabel("edge score sum")
    axes[0].set_title(
        f"Aggregate curve\nh_est={measurement['h_est']:.3f}, ratio="
        f"{measurement['sharpness'] if measurement['sharpness'] is not None else float('nan'):.3f}"
    )
    axes[0].legend(fontsize=8)

    for stem, record in measurement["view_peaks"].items():
        axes[1].plot(
            record["coarse_heights"] - ground,
            record["coarse_scores"],
            linewidth=1.1,
            label=stem[-6:],
        )
        axes[1].scatter(
            [record["h_est"] - ground],
            [record["peak_score"]],
            s=24,
        )
    axes[1].set_xlabel("height above observed ground [m]")
    axes[1].set_ylabel("edge score sum")
    axes[1].set_title("Per-view coarse curves and fine peaks")
    axes[1].legend(fontsize=7, ncol=2)

    segment_ids = [row["segment_index"] for row in measurement["segment_peaks"]]
    segment_heights = [row["h_est"] - ground for row in measurement["segment_peaks"]]
    axes[2].scatter(segment_ids, segment_heights, s=55, label="segment h")
    axes[2].axhline(measurement["h_est"] - ground, color="black", linestyle="--", label="aggregate h")
    axes[2].set_xticks(segment_ids)
    axes[2].set_xlabel("footprint segment index")
    axes[2].set_ylabel("height above observed ground [m]")
    axes[2].set_title("Boundary-segment peaks")
    axes[2].legend(fontsize=8)
    figure.suptitle(f"{building_id} GT-free h-sweep measurement", fontsize=13)
    figure.tight_layout(rect=(0, 0, 1, 0.94))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(output_path, dpi=170, bbox_inches="tight")
    plt.close(figure)


def plot_native_overlays(
    output_path: Path,
    building_id: str,
    measurement: dict[str, Any],
    points_utm: np.ndarray,
    offset: np.ndarray,
) -> None:
    contexts = measurement["contexts"]
    columns = min(3, len(contexts))
    rows = int(math.ceil(len(contexts) / columns))
    figure, axes = plt.subplots(rows, columns, figsize=(6.2 * columns, 4.8 * rows), squeeze=False)
    for axis in axes.flat:
        axis.axis("off")
    for axis, context in zip(axes.flat, contexts):
        image = context["image"].copy().astype(np.float32)
        target = context["target_full"]
        neighbor = context["neighbor_full"]
        image[target] = 0.70 * image[target] + 0.30 * np.asarray([0, 220, 255])
        image[neighbor] = 0.70 * image[neighbor] + 0.30 * np.asarray([255, 165, 0])
        axis.imshow(np.clip(image, 0, 255).astype(np.uint8))
        uv, depth = project_native(points_utm, measurement["h_est"], context["view"], offset)
        valid = np.isfinite(uv).all(axis=1) & (depth > 0)
        if np.any(valid):
            axis.plot(uv[valid, 0], uv[valid, 1], color="#39ff14", linewidth=1.8)
        peak_sample = sample_outline(
            points_utm,
            measurement["h_est"],
            context["view"],
            offset,
            context["gradient"],
            context["target_full"],
            context["neighbor_full"],
            context["known_full"],
        )
        axis.set_xlim(0, context["image"].shape[1])
        axis.set_ylim(context["image"].shape[0], 0)
        axis.set_title(context["stem"].replace("DJI_20241217", ""), fontsize=9)
        axis.text(
            0.01,
            0.01,
            (
                f"in-frame={peak_sample['in_frame_fraction']:.3f} "
                f"neighbor={peak_sample['occlusion_estimate_fraction'] or 0.0:.3f}\n"
                f"edge_mean={peak_sample['edge_response_mean'] or 0.0:.5f}"
            ),
            transform=axis.transAxes,
            va="bottom",
            ha="left",
            fontsize=8,
            color="white",
            bbox={"facecolor": "black", "alpha": 0.65, "pad": 3},
        )
        axis.axis("off")
    figure.suptitle(
        f"{building_id} native-frame overlay at h_est={measurement['h_est']:.3f} local m "
        "(green outline; cyan target; orange neighbor)",
        fontsize=13,
    )
    figure.tight_layout(rect=(0, 0, 1, 0.95))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close(figure)


def run(args: argparse.Namespace) -> None:
    lock = common.load_lock(args.lock)
    sources = {key: common.resolve(value) for key, value in lock["sources"].items()}
    outputs = {key: common.resolve(value) for key, value in lock["outputs"].items()}
    hs = lock["hsweep_0b"]
    if int(lock["learning_runs_allowed"]) != 0:
        raise RuntimeError("learning-zero lock drift")
    contexts = common.load_crop_contexts(sources["prepared_root"], lock["targets"])
    footprints = common.load_footprints(sources["footprints"], lock["targets"])
    offset = common.load_world_offset(sources["train_manifest"])
    fm = common.load_fm_summaries(sources["fm_rescore_csv"])

    source_paths: set[Path] = {
        args.lock.resolve(),
        Path(__file__).resolve(),
        Path(common.__file__).resolve(),
        common.REPO / "scripts/experiments/e5_c001_s3b0/run_e5_c001_s3b0_hsweep.sh",
        common.REPO / "tests/experiments/e5_c001_s3b0/test_e5_c001_s3b0_hsweep.py",
        sources["footprints"],
        sources["train_manifest"],
        sources["fm_rescore_csv"],
        sources["p0_fill_npz"],
    }
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for context in contexts:
        view = context["view"]
        source_path = sources["source_images"] / str(view["source_image_name"])
        image = np.asarray(PILImage.open(source_path).convert("RGB"), dtype=np.uint8)
        expected_wh = tuple(int(value) for value in view["source_size_wh"])
        if image.shape[1::-1] != expected_wh:
            raise RuntimeError(f"native source size drift: {source_path}")
        mask_path = outputs["semantic_masks"] / f"{context['building_id']}_{context['stem']}.npz"
        target, neighbor, known, metadata = native_masks(
            mask_path,
            view["crop_box_xyxy"],
            image.shape[:2],
        )
        if metadata["building_id"] != context["building_id"] or metadata["view_stem"] != context["stem"]:
            raise RuntimeError(f"0-e mask address drift: {mask_path}")
        record = {
            **context,
            "source_path": source_path,
            "mask_path": mask_path,
            "image": image,
            "gradient": gradient_magnitude(image),
            "target_full": target,
            "neighbor_full": neighbor,
            "known_full": known,
        }
        grouped[context["short"]].append(record)
        source_paths.update({context["manifest_path"], source_path, mask_path})

    outline_rows: list[dict[str, Any]] = []
    hsweep_rows: list[dict[str, Any]] = []
    measurements: dict[str, dict[str, Any]] = {}
    for short in lock["targets"]:
        building_id = common.full_id(short)
        footprint = footprints[building_id]
        segments = boundary_segments(footprint, float(hs["boundary_sample_step_m"]))
        points_utm = all_boundary_points(segments)
        contexts_for_building = sorted(grouped[short], key=lambda row: row["stem"])
        provisional_plane = np.asarray(fm[short]["plane"], dtype=np.float64)
        provisional_z = common.plane_z_local(points_utm, provisional_plane, offset)
        for context in contexts_for_building:
            observed = sample_outline(
                points_utm,
                provisional_z,
                context["view"],
                offset,
                context["gradient"],
                context["target_full"],
                context["neighbor_full"],
                context["known_full"],
            )
            outline_rows.append(
                {
                    "building_id": building_id,
                    "view_stem": context["stem"],
                    "source_image": common.rel(context["source_path"]),
                    "source_width_px": context["image"].shape[1],
                    "source_height_px": context["image"].shape[0],
                    "provisional_height_source": "cached image-derived FM fitted plane",
                    "provisional_plane_ax_local": provisional_plane[0],
                    "provisional_plane_by_local": provisional_plane[1],
                    "provisional_plane_c_local": provisional_plane[2],
                    **observed,
                    "edge_definition": hs["edge_definition"],
                    "semantic_mask_scope": hs["semantic_mask_scope"],
                    "semantic_mask_npz": common.rel(context["mask_path"]),
                    "semantic_mask_sha256": common.sha256_file(context["mask_path"]),
                    "gt_used_for_measurement": False,
                    "lod2_used_for_measurement": False,
                    "als_used_for_measurement": False,
                    "learning_runs_started": 0,
                    "new_inference_runs": 0,
                    "status": "measured",
                    "note": "occlusion estimate is projected-outline overlap with available 0-e neighbor mask",
                }
            )

        ground = float(fm[short]["ground_z_local_m"])
        lower = ground + float(hs["ground_plus_min_m"])
        upper = ground + float(hs["ground_plus_max_m"])
        coarse_heights = regular_grid(lower, upper, float(hs["coarse_step_m"]))
        view_coarse: dict[str, list[dict[str, Any]]] = {}
        for context in contexts_for_building:
            curve = curve_for_context(points_utm, coarse_heights, context, offset)
            view_coarse[context["stem"]] = curve
            for height, result in zip(coarse_heights, curve):
                hsweep_rows.append(
                    curve_row(
                        row_type="view_curve",
                        building_id=building_id,
                        view_stem=context["stem"],
                        segment=None,
                        stage="coarse",
                        height=float(height),
                        ground=ground,
                        measurement=result,
                        lock=lock,
                    )
                )
        aggregate_coarse = aggregate_curves(list(view_coarse.values()))
        aggregate_coarse_scores = np.asarray(
            [row["edge_response_sum"] for row in aggregate_coarse], dtype=np.float64
        )
        aggregate_coarse_index, _aggregate_coarse_status = select_peak(
            coarse_heights, aggregate_coarse_scores
        )
        aggregate_coarse_peak = float(coarse_heights[aggregate_coarse_index])
        for height, result in zip(coarse_heights, aggregate_coarse):
            hsweep_rows.append(
                curve_row(
                    row_type="aggregate_curve",
                    building_id=building_id,
                    view_stem="ALL",
                    segment=None,
                    stage="coarse",
                    height=float(height),
                    ground=ground,
                    measurement=result,
                    lock=lock,
                )
            )

        fine_heights = fine_grid(
            aggregate_coarse_peak,
            lower,
            upper,
            float(hs["fine_half_width_m"]),
            float(hs["fine_step_m"]),
        )
        aggregate_fine_by_view = [
            curve_for_context(points_utm, fine_heights, context, offset)
            for context in contexts_for_building
        ]
        aggregate_fine = aggregate_curves(aggregate_fine_by_view)
        aggregate_fine_scores = np.asarray(
            [row["edge_response_sum"] for row in aggregate_fine], dtype=np.float64
        )
        fine_index, peak_status = select_peak(
            fine_heights, aggregate_fine_scores, aggregate_coarse_peak
        )
        h_est = float(fine_heights[fine_index])
        peak_score = float(aggregate_fine_scores[fine_index])
        background, sharpness = peak_statistics(
            coarse_heights,
            aggregate_coarse_scores,
            h_est,
            peak_score,
            float(hs["background_exclusion_half_width_m"]),
        )
        for height, result in zip(fine_heights, aggregate_fine):
            hsweep_rows.append(
                curve_row(
                    row_type="aggregate_curve",
                    building_id=building_id,
                    view_stem="ALL",
                    segment=None,
                    stage="fine",
                    height=float(height),
                    ground=ground,
                    measurement=result,
                    lock=lock,
                )
            )

        view_peaks: dict[str, dict[str, Any]] = {}
        for context in contexts_for_building:
            stem = context["stem"]
            coarse_scores = np.asarray(
                [row["edge_response_sum"] for row in view_coarse[stem]], dtype=np.float64
            )
            coarse_index, _coarse_status = select_peak(coarse_heights, coarse_scores)
            coarse_peak = float(coarse_heights[coarse_index])
            view_fine_heights = fine_grid(
                coarse_peak,
                lower,
                upper,
                float(hs["fine_half_width_m"]),
                float(hs["fine_step_m"]),
            )
            view_fine = curve_for_context(points_utm, view_fine_heights, context, offset)
            view_fine_scores = np.asarray(
                [row["edge_response_sum"] for row in view_fine], dtype=np.float64
            )
            view_index, view_status = select_peak(
                view_fine_heights, view_fine_scores, coarse_peak
            )
            view_h = float(view_fine_heights[view_index])
            view_peak_score = float(view_fine_scores[view_index])
            view_background, view_sharpness = peak_statistics(
                coarse_heights,
                coarse_scores,
                view_h,
                view_peak_score,
                float(hs["background_exclusion_half_width_m"]),
            )
            for height, result in zip(view_fine_heights, view_fine):
                hsweep_rows.append(
                    curve_row(
                        row_type="view_curve",
                        building_id=building_id,
                        view_stem=stem,
                        segment=None,
                        stage="fine",
                        height=float(height),
                        ground=ground,
                        measurement=result,
                        lock=lock,
                    )
                )
            view_peaks[stem] = {
                "h_est": view_h,
                "peak_score": view_peak_score,
                "background": view_background,
                "sharpness": view_sharpness,
                "peak_status": view_status,
                "coarse_heights": coarse_heights,
                "coarse_scores": coarse_scores,
            }
            hsweep_rows.append(
                {
                    "row_type": "view_peak",
                    "building_id": building_id,
                    "view_stem": stem,
                    "h_est_local_m": view_h,
                    "h_est_above_ground_m": view_h - ground,
                    "peak_score": view_peak_score,
                    "background_median_score": view_background,
                    "peak_to_background_ratio": view_sharpness,
                    "peak_status": view_status,
                    "ground_z_local_m": ground,
                    "fm_anchor_z_local_m": float(fm[short]["inside_z_median_local_m"]),
                    "edge_definition": hs["edge_definition"],
                    "score_definition": hs["score_definition"],
                    "semantic_mask_scope": hs["semantic_mask_scope"],
                    "gt_used_for_estimation": False,
                    "lod2_used_for_estimation": False,
                    "als_used_for_estimation": False,
                    "gt_used_for_posthoc_score": False,
                    "lod2_used_for_posthoc_score": False,
                    "als_used_for_posthoc_score": False,
                    "learning_runs_started": 0,
                    "new_inference_runs": 0,
                    "status": "measured",
                    "note": "fine window centred on this view's coarse maximum",
                }
            )

        segment_peaks: list[dict[str, Any]] = []
        for segment in segments:
            segment_points = np.asarray(segment["points"], dtype=np.float64)
            segment_coarse_by_view = [
                curve_for_context(segment_points, coarse_heights, context, offset)
                for context in contexts_for_building
            ]
            segment_coarse = aggregate_curves(segment_coarse_by_view)
            segment_coarse_scores = np.asarray(
                [row["edge_response_sum"] for row in segment_coarse], dtype=np.float64
            )
            segment_coarse_index, _segment_coarse_status = select_peak(
                coarse_heights, segment_coarse_scores
            )
            segment_coarse_peak = float(coarse_heights[segment_coarse_index])
            for height, result in zip(coarse_heights, segment_coarse):
                hsweep_rows.append(
                    curve_row(
                        row_type="segment_curve",
                        building_id=building_id,
                        view_stem="ALL",
                        segment=segment,
                        stage="coarse",
                        height=float(height),
                        ground=ground,
                        measurement=result,
                        lock=lock,
                    )
                )
            segment_fine_heights = fine_grid(
                segment_coarse_peak,
                lower,
                upper,
                float(hs["fine_half_width_m"]),
                float(hs["fine_step_m"]),
            )
            segment_fine_by_view = [
                curve_for_context(segment_points, segment_fine_heights, context, offset)
                for context in contexts_for_building
            ]
            segment_fine = aggregate_curves(segment_fine_by_view)
            segment_fine_scores = np.asarray(
                [row["edge_response_sum"] for row in segment_fine], dtype=np.float64
            )
            segment_index, segment_status = select_peak(
                segment_fine_heights, segment_fine_scores, segment_coarse_peak
            )
            segment_h = float(segment_fine_heights[segment_index])
            segment_peak_score = float(segment_fine_scores[segment_index])
            segment_background, segment_sharpness = peak_statistics(
                coarse_heights,
                segment_coarse_scores,
                segment_h,
                segment_peak_score,
                float(hs["background_exclusion_half_width_m"]),
            )
            for height, result in zip(segment_fine_heights, segment_fine):
                hsweep_rows.append(
                    curve_row(
                        row_type="segment_curve",
                        building_id=building_id,
                        view_stem="ALL",
                        segment=segment,
                        stage="fine",
                        height=float(height),
                        ground=ground,
                        measurement=result,
                        lock=lock,
                    )
                )
            peak_record = {
                "segment_index": segment["segment_index"],
                "segment_length_m": segment["length_m"],
                "midpoint": segment["midpoint"],
                "h_est": segment_h,
                "peak_score": segment_peak_score,
                "background": segment_background,
                "sharpness": segment_sharpness,
                "peak_status": segment_status,
            }
            segment_peaks.append(peak_record)
            hsweep_rows.append(
                {
                    "row_type": "segment_peak",
                    "building_id": building_id,
                    "view_stem": "ALL",
                    "segment_index": segment["segment_index"],
                    "segment_length_m": segment["length_m"],
                    "segment_midpoint_e_utm": segment["midpoint"][0],
                    "segment_midpoint_n_utm": segment["midpoint"][1],
                    "h_est_local_m": segment_h,
                    "h_est_above_ground_m": segment_h - ground,
                    "peak_score": segment_peak_score,
                    "background_median_score": segment_background,
                    "peak_to_background_ratio": segment_sharpness,
                    "peak_status": segment_status,
                    "ground_z_local_m": ground,
                    "fm_anchor_z_local_m": float(fm[short]["inside_z_median_local_m"]),
                    "edge_definition": hs["edge_definition"],
                    "score_definition": hs["score_definition"],
                    "semantic_mask_scope": hs["semantic_mask_scope"],
                    "gt_used_for_estimation": False,
                    "lod2_used_for_estimation": False,
                    "als_used_for_estimation": False,
                    "gt_used_for_posthoc_score": False,
                    "lod2_used_for_posthoc_score": False,
                    "als_used_for_posthoc_score": False,
                    "learning_runs_started": 0,
                    "new_inference_runs": 0,
                    "status": "measured",
                    "note": "segment midpoint is the V2 anchor address; height is GT-free",
                }
            )

        segment_anchors_local = np.asarray(
            [
                [
                    row["midpoint"][0] - offset[0],
                    row["midpoint"][1] - offset[1],
                    row["h_est"],
                ]
                for row in segment_peaks
            ],
            dtype=np.float64,
        )
        segment_plane, segment_plane_rms = fit_anchor_plane(segment_anchors_local)
        view_heights = np.asarray([row["h_est"] for row in view_peaks.values()], dtype=np.float64)
        view_median = float(np.median(view_heights))
        view_mad = float(np.median(np.abs(view_heights - view_median)))
        building_row = {
            "row_type": "building_peak",
            "building_id": building_id,
            "view_stem": "ALL",
            "h_est_local_m": h_est,
            "h_est_above_ground_m": h_est - ground,
            "peak_score": peak_score,
            "background_median_score": background,
            "peak_to_background_ratio": sharpness,
            "peak_status": peak_status,
            "view_h_est_median_local_m": view_median,
            "view_h_est_mad_m": view_mad,
            "view_h_est_std_m": float(np.std(view_heights)),
            "view_h_est_range_m": float(np.ptp(view_heights)),
            "ground_z_local_m": ground,
            "fm_anchor_z_local_m": float(fm[short]["inside_z_median_local_m"]),
            "delta_h_vs_fm_anchor_m": h_est - float(fm[short]["inside_z_median_local_m"]),
            "segment_plane_anchor_count": int(len(segment_anchors_local)),
            "segment_plane_ax_local": segment_plane[0] if segment_plane is not None else None,
            "segment_plane_by_local": segment_plane[1] if segment_plane is not None else None,
            "segment_plane_c_local": segment_plane[2] if segment_plane is not None else None,
            "segment_plane_anchor_rms_m": segment_plane_rms,
            "edge_definition": hs["edge_definition"],
            "score_definition": hs["score_definition"],
            "semantic_mask_scope": hs["semantic_mask_scope"],
            "gt_used_for_estimation": False,
            "lod2_used_for_estimation": False,
            "als_used_for_estimation": False,
            "gt_used_for_posthoc_score": False,
            "lod2_used_for_posthoc_score": False,
            "als_used_for_posthoc_score": False,
            "learning_runs_started": 0,
            "new_inference_runs": 0,
            "status": "measured",
            "note": "reference columns appended only after all building/segment peaks were fixed",
        }
        hsweep_rows.append(building_row)
        measurements[short] = {
            "building_id": building_id,
            "contexts": contexts_for_building,
            "segments": segments,
            "points_utm": points_utm,
            "ground": ground,
            "fm_anchor": float(fm[short]["inside_z_median_local_m"]),
            "coarse_heights": coarse_heights,
            "aggregate_coarse_scores": aggregate_coarse_scores,
            "fine_heights": fine_heights,
            "aggregate_fine_scores": aggregate_fine_scores,
            "h_est": h_est,
            "peak_score": peak_score,
            "background": background,
            "sharpness": sharpness,
            "peak_status": peak_status,
            "view_peaks": view_peaks,
            "segment_peaks": segment_peaks,
            "segment_anchors_local": segment_anchors_local,
            "segment_plane": segment_plane,
            "segment_plane_rms": segment_plane_rms,
            "building_row": building_row,
        }

    # Dedicated V2 handoff is written before any reference source is opened.
    anchor_rows = [
        {
            "building_id": row["building_id"],
            "segment_index": row["segment_index"],
            "segment_length_m": row["segment_length_m"],
            "segment_midpoint_e_utm": row["segment_midpoint_e_utm"],
            "segment_midpoint_n_utm": row["segment_midpoint_n_utm"],
            "h_est_local_m": row["h_est_local_m"],
            "h_est_above_ground_m": row["h_est_above_ground_m"],
            "peak_score": row["peak_score"],
            "background_median_score": row["background_median_score"],
            "peak_to_background_ratio": row["peak_to_background_ratio"],
            "peak_status": row["peak_status"],
            "ground_z_local_m": row["ground_z_local_m"],
            "edge_definition": row["edge_definition"],
            "score_definition": row["score_definition"],
            "semantic_mask_scope": row["semantic_mask_scope"],
            "gt_used": False,
            "lod2_used": False,
            "als_used": False,
            "learning_runs_started": 0,
            "new_inference_runs": 0,
            "status": "measured",
        }
        for row in hsweep_rows
        if row["row_type"] == "segment_peak"
    ]
    common.atomic_csv(outputs["hsweep_anchor_csv"], anchor_rows, ANCHOR_FIELDS)

    # Post-hoc reference load begins only after all GT-free peaks, planes, and
    # the dedicated anchor handoff are fixed.
    roofs = common.load_lod2_roofs(sources["lod2_dir"], lock["targets"])
    projection = json.loads(sources["projection_datum"].read_text(encoding="utf-8"))
    geoid_m = float(projection["orthometric_geoid_m"])
    score_only_paths = {
        sources["projection_datum"],
        *sorted(sources["lod2_dir"].glob("*.gml")),
    }
    for short in lock["targets"]:
        measurement = measurements[short]
        building_id = measurement["building_id"]
        centroid = np.asarray(footprints[building_id].centroid.coords[0], dtype=np.float64)
        reference_z = float(
            common.reference_roof_z(centroid[None, :], roofs[short], geoid_m)[0]
            - offset[2]
        )
        measurement["reference_z"] = reference_z
        row = measurement["building_row"]
        row["reference_roof_z_local_m"] = reference_z
        row["delta_h_vs_reference_m"] = measurement["h_est"] - reference_z
        row["gt_used_for_posthoc_score"] = True
        row["lod2_used_for_posthoc_score"] = True

    # 4907199 segment-plane far-field profile vs the existing P0 plane.
    target_short = "4907199"
    measurement = measurements[target_short]
    building_id = measurement["building_id"]
    p0 = np.load(sources["p0_fill_npz"], allow_pickle=False)
    lattice = np.asarray(p0[f"{building_id}_local_xyz"], dtype=np.float64)
    fm_points = np.asarray(p0[f"{building_id}_fm_local_xyz"], dtype=np.float64)
    xy_local = lattice[:, :2]
    xy_utm = xy_local + offset[None, :2]
    reference_z = common.reference_roof_z(xy_utm, roofs[target_short], geoid_m) - offset[2]
    if measurement["segment_plane"] is not None:
        plane = measurement["segment_plane"]
        segment_z = plane[0] * xy_local[:, 0] + plane[1] * xy_local[:, 1] + plane[2]
    else:
        segment_z = np.full(len(xy_local), np.nan, dtype=np.float64)
    distance = nearest_distance(xy_local, fm_points[:, :2])
    bins = [float(value) for value in lock["seed_0f"]["far_field_distance_bins_m"]]
    variants = {"P0": lattice[:, 2], "hsweep_segment_plane": segment_z}
    baseline: dict[tuple[str, float | None, float | None], dict[str, Any]] = {}
    profile_rows: list[dict[str, Any]] = []
    scopes: list[tuple[str, float | None, float | None, np.ndarray]] = [
        ("overall", None, None, np.ones(len(xy_local), dtype=bool))
    ]
    for index, lower in enumerate(bins):
        upper = bins[index + 1] if index + 1 < len(bins) else None
        mask = distance >= lower
        if upper is not None:
            mask &= distance < upper
        scopes.append(("far_field", lower, upper, mask))
    for variant, z in variants.items():
        error = z - reference_z
        for scope, lower, upper, mask in scopes:
            metrics = metric_values(error[mask])
            row = {
                "row_type": "far_field_profile",
                "building_id": building_id,
                "view_stem": "ALL",
                "variant": variant,
                "scope": scope,
                "distance_lower_m": lower,
                "distance_upper_m": upper,
                "point_count": int(mask.sum()),
                **metrics,
                "ground_z_local_m": measurement["ground"],
                "fm_anchor_z_local_m": measurement["fm_anchor"],
                "reference_roof_z_local_m": measurement["reference_z"],
                "segment_plane_anchor_count": len(measurement["segment_anchors_local"]),
                "segment_plane_ax_local": (
                    measurement["segment_plane"][0]
                    if measurement["segment_plane"] is not None
                    else None
                ),
                "segment_plane_by_local": (
                    measurement["segment_plane"][1]
                    if measurement["segment_plane"] is not None
                    else None
                ),
                "segment_plane_c_local": (
                    measurement["segment_plane"][2]
                    if measurement["segment_plane"] is not None
                    else None
                ),
                "segment_plane_anchor_rms_m": measurement["segment_plane_rms"],
                "edge_definition": hs["edge_definition"],
                "score_definition": hs["score_definition"],
                "semantic_mask_scope": hs["semantic_mask_scope"],
                "gt_used_for_estimation": False,
                "lod2_used_for_estimation": False,
                "als_used_for_estimation": False,
                "gt_used_for_posthoc_score": True,
                "lod2_used_for_posthoc_score": True,
                "als_used_for_posthoc_score": False,
                "learning_runs_started": 0,
                "new_inference_runs": 0,
                "status": (
                    "measured"
                    if int(mask.sum()) and np.isfinite(error[mask]).any()
                    else "empty_scope"
                ),
                "note": "segment h anchors and plane fixed before reference load",
            }
            key = (scope, lower, upper)
            if variant == "P0":
                baseline[key] = metrics
            profile_rows.append(row)
    for row in profile_rows:
        base = baseline[(row["scope"], row["distance_lower_m"], row["distance_upper_m"])]
        row["p0_signed_delta_z_median_m"] = base["signed_delta_z_median_m"]
        row["p0_abs_delta_z_median_m"] = base["abs_delta_z_median_m"]
        row["p0_rms_delta_z_m"] = base["rms_delta_z_m"]
        for source, target in (
            ("signed_delta_z_median_m", "delta_signed_median_vs_p0_m"),
            ("abs_delta_z_median_m", "delta_abs_median_vs_p0_m"),
            ("rms_delta_z_m", "delta_rms_vs_p0_m"),
        ):
            value = row[source]
            baseline_value = base[source]
            row[target] = (
                float(value) - float(baseline_value)
                if value is not None and baseline_value is not None
                else None
            )
        hsweep_rows.append(row)

    common.atomic_csv(outputs["outline_csv"], outline_rows, OUTLINE_FIELDS)
    common.atomic_csv(outputs["hsweep_csv"], hsweep_rows, HSWEEP_FIELDS)
    figure_dir = outputs["hsweep_figure_dir"]
    figure_paths: list[Path] = []
    for short in lock["targets"]:
        measurement = measurements[short]
        curve_path = figure_dir / f"{measurement['building_id']}_hsweep_curves.png"
        overlay_path = figure_dir / f"{measurement['building_id']}_native_overlay.png"
        plot_curves(curve_path, measurement["building_id"], measurement)
        plot_native_overlays(
            overlay_path,
            measurement["building_id"],
            measurement,
            measurement["points_utm"],
            offset,
        )
        figure_paths.extend([curve_path, overlay_path])

    output_paths = [
        outputs["outline_csv"],
        outputs["hsweep_csv"],
        outputs["hsweep_anchor_csv"],
        *figure_paths,
    ]
    manifest = {
        "schema": "jointbuildgs.s3b0.hsweep.v1",
        "created_utc": common.now(),
        "git": {
            "head": common.git_value("rev-parse", "HEAD"),
            "branch": common.git_value("branch", "--show-current"),
            "dirty": bool(common.git_value("status", "--porcelain")),
        },
        "crs": lock["crs"],
        "estimation_contract": {
            "range": "observed exterior ground +2m through +40m",
            "coarse_step_m": hs["coarse_step_m"],
            "fine_half_width_m": hs["fine_half_width_m"],
            "fine_step_m": hs["fine_step_m"],
            "boundary_sample_step_m": hs["boundary_sample_step_m"],
            "edge_definition": hs["edge_definition"],
            "score_definition": hs["score_definition"],
            "semantic_mask_scope": hs["semantic_mask_scope"],
            "peak_tie_rule": hs["peak_tie_rule"],
            "gt_used": False,
            "lod2_used": False,
            "als_used": False,
        },
        "posthoc_score_contract": {
            "reference": "CityGML LoD2 RoofSurface plus configured orthometric geoid",
            "building_reference_address": "supplied footprint centroid",
            "far_field_target": "4907199",
            "far_field_distance": "nearest footprint-inside FM anchor XY",
            "gt_used": True,
            "lod2_used": True,
            "als_used": False,
            "ordering": "all building/view/segment peaks and segment planes fixed before reference load",
        },
        "building_measurements": {
            short: {
                "h_est_local_m": row["h_est"],
                "peak_status": row["peak_status"],
                "peak_to_background_ratio": row["sharpness"],
                "view_h_est_values_local_m": [
                    value["h_est"] for value in row["view_peaks"].values()
                ],
                "segment_h_est_values_local_m": [
                    value["h_est"] for value in row["segment_peaks"]
                ],
                "segment_plane_ax_by_c": (
                    row["segment_plane"].tolist()
                    if row["segment_plane"] is not None
                    else None
                ),
                "segment_plane_anchor_rms_m": row["segment_plane_rms"],
                "reference_roof_z_local_m_score_only": row["reference_z"],
            }
            for short, row in measurements.items()
        },
        "counts": {
            "outline_rows": len(outline_rows),
            "hsweep_rows": len(hsweep_rows),
            "figures": len(figure_paths),
            "view_count": len(contexts),
            "segment_peak_rows": sum(
                row["row_type"] == "segment_peak" for row in hsweep_rows
            ),
            "gtfree_anchor_rows": len(anchor_rows),
        },
        "learning_runs_started": 0,
        "new_inference_runs": 0,
        "runtime": {
            "python": platform.python_version(),
            "numpy": np.__version__,
            "opencv": cv2.__version__,
            "docker_image": lock["containers"]["main_image"],
            "docker_image_id": lock["containers"]["main_image_id"],
        },
        "estimation_source_sha256": common.source_hashes(source_paths),
        "score_only_source_sha256": common.source_hashes(score_only_paths),
        "output_sha256": common.source_hashes(output_paths),
    }
    run_dir = outputs["hsweep_run"]
    run_dir.mkdir(parents=True, exist_ok=True)
    common.atomic_json(run_dir / "manifest.json", manifest)
    print(
        json.dumps(
            {
                "status": "measured",
                "outline_rows": len(outline_rows),
                "hsweep_rows": len(hsweep_rows),
                "figures": len(figure_paths),
                "learning_runs_started": 0,
                "new_inference_runs": 0,
            },
            ensure_ascii=False,
        )
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--lock", type=Path, default=common.DEFAULT_LOCK)
    run(parser.parse_args())


if __name__ == "__main__":
    main()
