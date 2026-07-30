#!/usr/bin/env python3
"""S3-B step-0c learning-zero gate-score measurement.

This script only recombines committed/cached image, point, FM, mono-normal, and
0-e SAM-mask artifacts.  It does not start GS optimisation or model inference.
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
import open3d as o3d
from PIL import Image
from shapely import contains_xy

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from src.stage2.colmap_io import read_points3d_bin

import e5_c001_s3b0_common as common


FIELDS = [
    "row_type",
    "building_id",
    "view_stem",
    "target_region_pixels",
    "neighbor_region_pixels",
    "texture_valid_pixels",
    "low_gradient_pixel_ratio",
    "gradient_p10",
    "gradient_median",
    "gradient_mean",
    "sfm_candidate_point_count",
    "sfm_positive_depth_count",
    "sfm_in_frame_point_count",
    "sfm_target_mask_point_count",
    "sfm_target_mask_unique_pixel_count",
    "sfm_target_mask_yield",
    "mvs_candidate_point_count",
    "mvs_positive_depth_count",
    "mvs_in_frame_point_count",
    "mvs_target_mask_point_count",
    "mvs_target_mask_unique_pixel_count",
    "mvs_target_mask_yield",
    "fm_eligible_pair_count",
    "fm_cached_dlt_survivor_count",
    "fm_inside_point_count",
    "fm_inside_point_yield",
    "mono_fm_angle_median_deg",
    "mono_fm_angle_mad_deg",
    "mono_finite_normal_count",
    "mono_fm_angle_available",
    "existing_mono_fm_angle_gate_deg",
    "existing_mono_fm_angle_gate_eligible",
    "new_composite_gate_threshold_defined",
    "texture_definition",
    "point_support_rule",
    "fm_pair_rule",
    "semantic_mask_role",
    "semantic_mask_npz",
    "semantic_mask_sha256",
    "gt_used",
    "lod2_used",
    "als_used",
    "learning_runs_started",
    "new_inference_runs",
    "status",
    "note",
]


def finite_float(value: str | float | None) -> float | None:
    if value is None or value == "":
        return None
    parsed = float(value)
    return parsed if math.isfinite(parsed) else None


def texture_metrics(
    image_rgb: np.ndarray,
    mask: np.ndarray,
    threshold: float,
) -> dict[str, Any]:
    """Return T11 texture values inside a supplied region mask."""
    rgb = np.asarray(image_rgb, dtype=np.uint8)
    region = np.asarray(mask, dtype=bool)
    if rgb.shape[:2] != region.shape:
        raise ValueError(f"image/mask shape mismatch: {rgb.shape[:2]} vs {region.shape}")
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY).astype(np.float64) / 255.0
    grad_y, grad_x = np.gradient(gray)
    magnitude = np.hypot(grad_x, grad_y)
    values = magnitude[region & np.isfinite(magnitude)]
    if not len(values):
        return {
            "texture_valid_pixels": 0,
            "low_gradient_pixel_ratio": None,
            "gradient_p10": None,
            "gradient_median": None,
            "gradient_mean": None,
        }
    return {
        "texture_valid_pixels": int(len(values)),
        "low_gradient_pixel_ratio": float(np.mean(values < float(threshold))),
        "gradient_p10": float(np.quantile(values, 0.10)),
        "gradient_median": float(np.median(values)),
        "gradient_mean": float(np.mean(values)),
    }


def project_support(
    points_local: np.ndarray,
    view: dict[str, Any],
    target_mask: np.ndarray,
) -> dict[str, Any]:
    """Project candidate local-frame points and sample the nearest crop pixel."""
    points = np.asarray(points_local, dtype=np.float64).reshape(-1, 3)
    height, width = target_mask.shape
    if not len(points):
        return {
            "candidate_point_count": 0,
            "positive_depth_count": 0,
            "in_frame_point_count": 0,
            "target_mask_point_count": 0,
            "target_mask_unique_pixel_count": 0,
            "target_mask_yield": None,
        }
    rotation = np.asarray(view["R_w2c"], dtype=np.float64)
    translation = np.asarray(view["t_w2c"], dtype=np.float64)
    intrinsic = np.asarray(view["K_crop"], dtype=np.float64)
    camera = points @ rotation.T + translation[None, :]
    positive = np.isfinite(camera).all(axis=1) & (camera[:, 2] > 1e-9)
    uvw = camera[positive] @ intrinsic.T
    uv = uvw[:, :2] / uvw[:, 2:3]
    pixels = np.rint(uv).astype(np.int64)
    in_frame = (
        np.isfinite(uv).all(axis=1)
        & (pixels[:, 0] >= 0)
        & (pixels[:, 0] < width)
        & (pixels[:, 1] >= 0)
        & (pixels[:, 1] < height)
    )
    sampled = pixels[in_frame]
    hit = (
        target_mask[sampled[:, 1], sampled[:, 0]]
        if len(sampled)
        else np.zeros(0, dtype=bool)
    )
    hit_pixels = sampled[hit]
    unique = (
        len(np.unique(hit_pixels[:, 1] * width + hit_pixels[:, 0]))
        if len(hit_pixels)
        else 0
    )
    in_frame_count = int(in_frame.sum())
    hit_count = int(hit.sum())
    return {
        "candidate_point_count": int(len(points)),
        "positive_depth_count": int(positive.sum()),
        "in_frame_point_count": in_frame_count,
        "target_mask_point_count": hit_count,
        "target_mask_unique_pixel_count": int(unique),
        "target_mask_yield": float(hit_count / in_frame_count) if in_frame_count else None,
    }


def target_point_candidates(
    points_local: np.ndarray,
    footprint: Any,
    offset: np.ndarray,
    minimum_z_local_m: float,
) -> np.ndarray:
    """Filter zero-iteration points with the locked footprint/height rule."""
    points = np.asarray(points_local, dtype=np.float64).reshape(-1, 3)
    utm_x = points[:, 0] + offset[0]
    utm_y = points[:, 1] + offset[1]
    minx, miny, maxx, maxy = footprint.bounds
    box = (
        (utm_x >= minx)
        & (utm_x <= maxx)
        & (utm_y >= miny)
        & (utm_y <= maxy)
        & (points[:, 2] >= float(minimum_z_local_m))
        & np.isfinite(points).all(axis=1)
    )
    indices = np.flatnonzero(box)
    if not len(indices):
        return np.empty((0, 3), dtype=np.float64)
    inside = contains_xy(footprint, utm_x[indices], utm_y[indices])
    return np.asarray(points[indices[inside]], dtype=np.float64)


def load_mono_rows(path: Path) -> dict[tuple[str, str], dict[str, Any]]:
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    return {
        (common.short_id(row["building_id"]), row["view_stem"]): row
        for row in rows
        if row.get("row_type") == "view"
    }


def load_fm_view_scores(path: Path) -> dict[tuple[str, str], dict[str, int]]:
    """Attribute each eligible cached pair's counts to both endpoint views."""
    output: dict[tuple[str, str], dict[str, int]] = defaultdict(
        lambda: {"pair_count": 0, "survivor_count": 0, "inside_count": 0}
    )
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    for row in rows:
        if row.get("row_type") != "view_pair" or row.get("eligible_summary_pair") != "true":
            continue
        short = common.short_id(row["building_id"])
        survivors = int(row["cached_dlt_survivor_count"] or 0)
        inside = int(row["inside_point_count"] or 0)
        for stem in (row["view_a"], row["view_b"]):
            target = output[(short, stem)]
            target["pair_count"] += 1
            target["survivor_count"] += survivors
            target["inside_count"] += inside
    return dict(output)


def load_semantic_mask(path: Path) -> tuple[np.ndarray, np.ndarray, dict[str, Any]]:
    with np.load(path, allow_pickle=False) as archive:
        expected = {"metadata_json", "neighbor_mask", "projected_target_mask", "target_mask"}
        if set(archive.files) != expected:
            raise RuntimeError(f"0-e mask key drift: {path}: {sorted(archive.files)}")
        target = np.asarray(archive["target_mask"], dtype=bool)
        neighbor = np.asarray(archive["neighbor_mask"], dtype=bool)
        metadata = json.loads(str(archive["metadata_json"].item()))
    if int(metadata.get("learning_runs_started", -1)) != 0:
        raise RuntimeError(f"0-e mask learning flag drift: {path}")
    return target, neighbor, metadata


def aggregate_rows(rows: Sequence[dict[str, Any]], building_id: str) -> dict[str, Any]:
    def values(field: str) -> np.ndarray:
        return np.asarray(
            [float(row[field]) for row in rows if row.get(field) is not None],
            dtype=np.float64,
        )

    def median(field: str) -> float | None:
        data = values(field)
        return float(np.median(data)) if len(data) else None

    sfm_in = sum(int(row["sfm_in_frame_point_count"]) for row in rows)
    sfm_hit = sum(int(row["sfm_target_mask_point_count"]) for row in rows)
    mvs_in = sum(int(row["mvs_in_frame_point_count"]) for row in rows)
    mvs_hit = sum(int(row["mvs_target_mask_point_count"]) for row in rows)
    fm_survivors = sum(int(row["fm_cached_dlt_survivor_count"]) for row in rows)
    fm_inside = sum(int(row["fm_inside_point_count"]) for row in rows)
    return {
        "row_type": "building_summary",
        "building_id": building_id,
        "view_stem": "",
        "target_region_pixels": sum(int(row["target_region_pixels"]) for row in rows),
        "neighbor_region_pixels": sum(int(row["neighbor_region_pixels"]) for row in rows),
        "texture_valid_pixels": sum(int(row["texture_valid_pixels"]) for row in rows),
        "low_gradient_pixel_ratio": median("low_gradient_pixel_ratio"),
        "gradient_p10": median("gradient_p10"),
        "gradient_median": median("gradient_median"),
        "gradient_mean": median("gradient_mean"),
        "sfm_candidate_point_count": int(rows[0]["sfm_candidate_point_count"]) if rows else 0,
        "sfm_positive_depth_count": sum(int(row["sfm_positive_depth_count"]) for row in rows),
        "sfm_in_frame_point_count": sfm_in,
        "sfm_target_mask_point_count": sfm_hit,
        "sfm_target_mask_unique_pixel_count": sum(
            int(row["sfm_target_mask_unique_pixel_count"]) for row in rows
        ),
        "sfm_target_mask_yield": float(sfm_hit / sfm_in) if sfm_in else None,
        "mvs_candidate_point_count": int(rows[0]["mvs_candidate_point_count"]) if rows else 0,
        "mvs_positive_depth_count": sum(int(row["mvs_positive_depth_count"]) for row in rows),
        "mvs_in_frame_point_count": mvs_in,
        "mvs_target_mask_point_count": mvs_hit,
        "mvs_target_mask_unique_pixel_count": sum(
            int(row["mvs_target_mask_unique_pixel_count"]) for row in rows
        ),
        "mvs_target_mask_yield": float(mvs_hit / mvs_in) if mvs_in else None,
        "fm_eligible_pair_count": sum(int(row["fm_eligible_pair_count"]) for row in rows),
        "fm_cached_dlt_survivor_count": fm_survivors,
        "fm_inside_point_count": fm_inside,
        "fm_inside_point_yield": float(fm_inside / fm_survivors) if fm_survivors else None,
        "mono_fm_angle_median_deg": median("mono_fm_angle_median_deg"),
        "mono_fm_angle_mad_deg": median("mono_fm_angle_mad_deg"),
        "mono_finite_normal_count": sum(int(row["mono_finite_normal_count"]) for row in rows),
        "mono_fm_angle_available": sum(bool(row["mono_fm_angle_available"]) for row in rows),
        "existing_mono_fm_angle_gate_deg": rows[0]["existing_mono_fm_angle_gate_deg"],
        "existing_mono_fm_angle_gate_eligible": sum(
            bool(row["existing_mono_fm_angle_gate_eligible"]) for row in rows
        ),
        "new_composite_gate_threshold_defined": False,
        "texture_definition": rows[0]["texture_definition"],
        "point_support_rule": rows[0]["point_support_rule"],
        "fm_pair_rule": rows[0]["fm_pair_rule"],
        "semantic_mask_role": "0-e non-GT SAM target masks; aggregate of view rows",
        "semantic_mask_npz": "",
        "semantic_mask_sha256": "",
        "gt_used": False,
        "lod2_used": False,
        "als_used": False,
        "learning_runs_started": 0,
        "new_inference_runs": 0,
        "status": "measured",
        "note": "medians for texture/mono scalars; support counts summed across views",
    }


def plot_building(
    building_id: str,
    rows: Sequence[dict[str, Any]],
    records: dict[str, dict[str, Any]],
    output_path: Path,
) -> None:
    columns = min(3, len(rows))
    grid_rows = int(math.ceil(len(rows) / columns))
    figure, axes = plt.subplots(
        grid_rows,
        columns,
        figsize=(5.2 * columns, 4.5 * grid_rows),
        squeeze=False,
    )
    for axis in axes.flat:
        axis.axis("off")
    for axis, row in zip(axes.flat, rows):
        record = records[row["view_stem"]]
        image = record["image"].astype(np.float32)
        target = record["target"]
        neighbor = record["neighbor"]
        overlay = image.copy()
        overlay[target] = 0.55 * overlay[target] + 0.45 * np.asarray([0, 220, 255])
        overlay[neighbor] = 0.55 * overlay[neighbor] + 0.45 * np.asarray([255, 165, 0])
        axis.imshow(np.clip(overlay, 0, 255).astype(np.uint8))
        angle = row["mono_fm_angle_median_deg"]
        angle_text = "NA" if angle is None else f"{float(angle):.1f}"
        text = (
            f"low={float(row['low_gradient_pixel_ratio']):.3f} "
            f"p10={float(row['gradient_p10']):.4f}\n"
            f"SfM={row['sfm_target_mask_point_count']}/{row['sfm_in_frame_point_count']} "
            f"MVS={row['mvs_target_mask_point_count']}/{row['mvs_in_frame_point_count']}\n"
            f"FM={row['fm_inside_point_count']}/{row['fm_cached_dlt_survivor_count']} "
            f"mono-FM={angle_text} deg"
        )
        axis.set_title(row["view_stem"].replace("DJI_20241217", ""), fontsize=9)
        axis.text(
            0.01,
            0.01,
            text,
            transform=axis.transAxes,
            va="bottom",
            ha="left",
            fontsize=8,
            color="white",
            bbox={"facecolor": "black", "alpha": 0.65, "pad": 3},
        )
        axis.axis("off")
    figure.suptitle(
        f"{building_id} gate-score inputs (cyan target SAM; orange neighbor SAM)",
        fontsize=13,
    )
    figure.tight_layout(rect=(0, 0, 1, 0.95))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(output_path, dpi=170, bbox_inches="tight")
    plt.close(figure)


def run(args: argparse.Namespace) -> None:
    lock = common.load_lock(args.lock)
    if int(lock["learning_runs_allowed"]) != 0:
        raise RuntimeError("learning-zero lock drift")
    sources = {key: common.resolve(value) for key, value in lock["sources"].items()}
    outputs = {key: common.resolve(value) for key, value in lock["outputs"].items()}
    gate = lock["gate_0c"]
    threshold = float(gate["low_gradient_threshold"])
    angle_gate = float(gate["existing_mono_fm_view_angle_deg"])

    contexts = common.load_crop_contexts(sources["prepared_root"], lock["targets"])
    footprints = common.load_footprints(sources["footprints"], lock["targets"])
    offset = common.load_world_offset(sources["train_manifest"])
    fm_summaries = common.load_fm_summaries(sources["fm_rescore_csv"])
    mono_rows = load_mono_rows(sources["mono_diag_csv"])
    fm_views = load_fm_view_scores(sources["fm_rescore_csv"])
    sparse = np.asarray(read_points3d_bin(sources["sparse_points"]), dtype=np.float64)[:, :3]
    dense = np.asarray(o3d.io.read_point_cloud(str(sources["dense_init"])).points, dtype=np.float64)

    candidates: dict[str, dict[str, np.ndarray]] = {}
    for short in lock["targets"]:
        minimum_z = (
            float(fm_summaries[short]["ground_z_local_m"])
            + float(lock["alpha_0a"]["roof_candidate_min_above_ground_m"])
        )
        footprint = footprints[common.full_id(short)]
        candidates[short] = {
            "sfm": target_point_candidates(sparse, footprint, offset, minimum_z),
            "mvs": target_point_candidates(dense, footprint, offset, minimum_z),
        }

    run_dir = outputs["gate_run"]
    figure_dir = outputs["gate_figure_dir"]
    run_dir.mkdir(parents=True, exist_ok=True)
    figure_dir.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, Any]] = []
    building_records: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    source_paths: set[Path] = {
        args.lock.resolve(),
        Path(__file__).resolve(),
        Path(common.__file__).resolve(),
        sources["fm_rescore_csv"],
        sources["mono_diag_csv"],
        sources["sparse_points"],
        sources["dense_init"],
        sources["footprints"],
        sources["train_manifest"],
        outputs["mask_iou_csv"],
        common.REPO / "scripts/e5_c001/s3b0/run_e5_c001_s3b0_gate.sh",
        common.REPO / "tests/e5_c001/s3b0/test_e5_c001_s3b0_gate.py",
    }

    for context in contexts:
        short = context["short"]
        building_id = context["building_id"]
        stem = context["stem"]
        image = np.asarray(Image.open(context["image_path"]).convert("RGB"), dtype=np.uint8)
        mask_path = outputs["semantic_masks"] / f"{building_id}_{stem}.npz"
        target, neighbor, mask_metadata = load_semantic_mask(mask_path)
        if target.shape != image.shape[:2]:
            raise RuntimeError(f"0-e mask/image shape mismatch: {mask_path}")
        if mask_metadata["building_id"] != building_id or mask_metadata["view_stem"] != stem:
            raise RuntimeError(f"0-e mask address drift: {mask_path}")
        texture = texture_metrics(image, target, threshold)
        sfm_support = project_support(candidates[short]["sfm"], context["view"], target)
        mvs_support = project_support(candidates[short]["mvs"], context["view"], target)
        mono = mono_rows.get((short, stem), {})
        angle = finite_float(mono.get("angle_median_deg_absdot"))
        angle_mad = finite_float(mono.get("angle_mad_deg_absdot"))
        mono_count = int(mono.get("finite_normal_count") or 0)
        fm = fm_views.get(
            (short, stem),
            {"pair_count": 0, "survivor_count": 0, "inside_count": 0},
        )
        row = {
            "row_type": "view",
            "building_id": building_id,
            "view_stem": stem,
            "target_region_pixels": int(target.sum()),
            "neighbor_region_pixels": int(neighbor.sum()),
            **texture,
            "sfm_candidate_point_count": sfm_support["candidate_point_count"],
            "sfm_positive_depth_count": sfm_support["positive_depth_count"],
            "sfm_in_frame_point_count": sfm_support["in_frame_point_count"],
            "sfm_target_mask_point_count": sfm_support["target_mask_point_count"],
            "sfm_target_mask_unique_pixel_count": sfm_support["target_mask_unique_pixel_count"],
            "sfm_target_mask_yield": sfm_support["target_mask_yield"],
            "mvs_candidate_point_count": mvs_support["candidate_point_count"],
            "mvs_positive_depth_count": mvs_support["positive_depth_count"],
            "mvs_in_frame_point_count": mvs_support["in_frame_point_count"],
            "mvs_target_mask_point_count": mvs_support["target_mask_point_count"],
            "mvs_target_mask_unique_pixel_count": mvs_support["target_mask_unique_pixel_count"],
            "mvs_target_mask_yield": mvs_support["target_mask_yield"],
            "fm_eligible_pair_count": fm["pair_count"],
            "fm_cached_dlt_survivor_count": fm["survivor_count"],
            "fm_inside_point_count": fm["inside_count"],
            "fm_inside_point_yield": (
                float(fm["inside_count"] / fm["survivor_count"])
                if fm["survivor_count"]
                else None
            ),
            "mono_fm_angle_median_deg": angle,
            "mono_fm_angle_mad_deg": angle_mad,
            "mono_finite_normal_count": mono_count,
            "mono_fm_angle_available": angle is not None,
            "existing_mono_fm_angle_gate_deg": angle_gate,
            "existing_mono_fm_angle_gate_eligible": angle is not None and angle <= angle_gate,
            "new_composite_gate_threshold_defined": False,
            "texture_definition": gate["texture_definition"],
            "point_support_rule": gate["point_support_rule"],
            "fm_pair_rule": gate["fm_pair_rule"],
            "semantic_mask_role": "0-e non-GT SAM target/neighbor mask reuse",
            "semantic_mask_npz": common.rel(mask_path),
            "semantic_mask_sha256": common.sha256_file(mask_path),
            "gt_used": False,
            "lod2_used": False,
            "als_used": False,
            "learning_runs_started": 0,
            "new_inference_runs": 0,
            "status": "measured",
            "note": "existing 22.5deg mono-FM marker only; no composite gate threshold",
        }
        rows.append(row)
        building_records[building_id][stem] = {
            "image": image,
            "target": target,
            "neighbor": neighbor,
        }
        source_paths.update(
            {
                context["image_path"],
                context["manifest_path"],
                context["normal_path"],
                mask_path,
            }
        )

    for short in lock["targets"]:
        building_id = common.full_id(short)
        view_rows = [row for row in rows if row["building_id"] == building_id]
        rows.append(aggregate_rows(view_rows, building_id))
        figure_path = figure_dir / f"{building_id}_gate_scores.png"
        plot_building(building_id, view_rows, building_records[building_id], figure_path)

    common.atomic_csv(outputs["gate_csv"], rows, FIELDS)
    figures = sorted(figure_dir.glob("*.png"))
    output_paths = [outputs["gate_csv"], *figures]
    manifest = {
        "schema": "jointbuildgs.s3b0.gate_scores.v1",
        "created_utc": common.now(),
        "git": {
            "head": common.git_value("rev-parse", "HEAD"),
            "branch": common.git_value("branch", "--show-current"),
            "dirty": bool(common.git_value("status", "--porcelain")),
        },
        "crs": lock["crs"],
        "definitions": {
            "texture": gate["texture_definition"],
            "low_gradient_threshold": threshold,
            "point_support_rule": gate["point_support_rule"],
            "projection_sampling": gate["projection_sampling"],
            "fm_pair_rule": gate["fm_pair_rule"],
            "existing_mono_fm_view_angle_deg": angle_gate,
            "new_composite_threshold_defined": False,
        },
        "counts": {
            "view_rows": sum(row["row_type"] == "view" for row in rows),
            "building_summary_rows": sum(row["row_type"] == "building_summary" for row in rows),
            "figures": len(figures),
        },
        "gt_boundary": {
            "gt_used": False,
            "lod2_used": False,
            "als_used": False,
            "semantic_mask": "0-e non-GT SAM output; LoD2-raycast cache not read by this task",
        },
        "learning_runs_started": 0,
        "new_inference_runs": 0,
        "runtime": {
            "python": platform.python_version(),
            "numpy": np.__version__,
            "opencv": cv2.__version__,
            "open3d": o3d.__version__,
            "docker_image": lock["containers"]["main_image"],
            "docker_image_id": lock["containers"]["main_image_id"],
        },
        "source_sha256": common.source_hashes(source_paths),
        "output_sha256": common.source_hashes(output_paths),
    }
    common.atomic_json(run_dir / "manifest.json", manifest)
    print(
        json.dumps(
            {
                "status": "measured",
                "view_rows": manifest["counts"]["view_rows"],
                "building_summary_rows": manifest["counts"]["building_summary_rows"],
                "figures": len(figures),
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
