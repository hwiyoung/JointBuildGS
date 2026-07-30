#!/usr/bin/env python3
"""T11 refined survivor image-texture correlation test.

Run from phases/p0-audit/. Host mode re-runs this script inside the P0 tools
container so LAZ/GIS/image processing stays in the recorded audit toolchain.
"""

from __future__ import annotations

import csv
import importlib.util
import json
import math
import os
import shutil
import subprocess
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageDraw


TASK_ID = "T11"
CANONICAL_RUN = "w3_2b_roofer_repeatability_20260612_220747/run_2"
BUILDING_CLASS = 6
FOOTPRINT_GPKG = "data/work/footprints/lod2_ground_plan.gpkg"
FOOTPRINT_LAYER = "lod2_ground_plan"
IMAGE_DIR = "data/work/images/Images"
NEAR_NADIR_MAX_INCIDENT_DEG = 20.0
MIN_TEXTURE_PIXELS = 80
MAX_SURVIVOR_TEXTURE_VIEWS = 8
MAX_FAILURE_TEXTURE_VIEWS = 28
FIGURE_FAILURE_ID = "DEBY_LOD2_4907182"
PERMUTATION_COUNT = 9999
PERMUTATION_SEED = 20260615


@dataclass
class SharpCropMetric:
    building_id: str
    cohort: str
    image_name: str
    incidence_deg: float
    in_frame_fraction: float
    gradient_mean: float
    gradient_median: float
    gradient_p10: float
    low_texture_pixel_ratio: float
    gray_std: float
    brightness_median: float
    shadow_ratio: float
    mask_pixel_count: int
    bbox: tuple[int, int, int, int]
    polygon_in_crop: np.ndarray
    gradient_values: np.ndarray = field(repr=False)


@dataclass
class FigurePatch:
    panel: str
    building_id: str
    image_name: str
    gradient_p10: float
    low_texture_pixel_ratio: float
    incidence_deg: float
    mask_pixel_count: int
    patch_size_px: int
    rgb: np.ndarray = field(repr=False)


def host_entrypoint() -> None:
    repo = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env.setdefault("P0_UID", str(os.getuid()))
    env.setdefault("P0_GID", str(os.getgid()))
    run_id = env.get("RUN_ID") or datetime.now().strftime("t11_survivor_texture_refine_%Y%m%d_%H%M%S")
    git_commit = capture(["git", "rev-parse", "--short", "HEAD"], cwd=repo.parent).strip()
    run_dir = repo / "runs" / run_id
    logs_dir = run_dir / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)

    write_host_config(run_dir, run_id, git_commit)
    compose = ["docker", "compose", "-f", str(repo / "env/docker-compose.p0.yml")]
    if env.get("SKIP_BUILD") != "1":
        run(compose + ["build", "tools"], cwd=repo, env=env, log_path=logs_dir / "build_tools.log")
    write_host_versions(repo, run_dir, compose, env, git_commit)
    try:
        run(
            compose
            + [
                "run",
                "-T",
                "--rm",
                "-e",
                "P0_INSIDE_CONTAINER=1",
                "-e",
                f"RUN_ID={run_id}",
                "-e",
                f"P0_GIT_COMMIT={git_commit}",
                "tools",
                "python",
                "/workspace/scripts/11_survivor_texture_refine.py",
                "--mode",
                "compute",
            ],
            cwd=repo,
            env=env,
            log_path=logs_dir / "compute.log",
        )
    except subprocess.CalledProcessError as exc:
        record_issue(repo, run_id, f"failed with exit code {exc.returncode}")
        raise

    print(f"run_id={run_id}")
    print(f"run_dir=runs/{run_id}")
    print("report=docs/W3_survivor_texture_refine.md")


def compute_entrypoint() -> None:
    root = Path("/workspace")
    docs = root / "docs"
    data = root / "data"
    figs = docs / "figs"
    package = docs / "G1_package"
    package_figs = package / "figs"
    run_id = os.environ["RUN_ID"]
    run_dir = root / "runs" / run_id
    scratch_dir = run_dir / "scratch"
    run_dir.mkdir(parents=True, exist_ok=True)
    scratch_dir.mkdir(parents=True, exist_ok=True)
    figs.mkdir(parents=True, exist_ok=True)

    t7 = load_helper_module("t7_failure_diagnosis", root / "scripts/07_failure_diagnosis.py")
    t9 = load_helper_module("t9_failure_surface_cause", root / "scripts/09_failure_surface_cause.py")
    t10 = load_helper_module("t10_survivor_texture_gap", root / "scripts/10_survivor_texture_gap.py")

    survivor_ids = [
        row["building_id"]
        for row in read_csv(docs / "W3_failure_diagnosis_building_metrics.csv")
        if row["cohort"] == "control_success_71"
    ]
    if len(survivor_ids) != 71:
        raise RuntimeError(f"Expected 71 survivor buildings from T7, got {len(survivor_ids)}")

    t9_failure_rows = read_csv(docs / "W3_failure_surface_cause_building_metrics.csv")
    assert_t9_confirmed_failure(t9_failure_rows, FIGURE_FAILURE_ID)
    target_ids = sorted(set(survivor_ids + [FIGURE_FAILURE_ID]))

    quality_by_id = {row["building_id"]: row for row in read_csv(docs / "W3_2c_canonical_roofer_quality_metrics.csv")}
    internal_rows = read_csv(docs / "W3_2c_canonical_internal_boundary_metrics.csv")
    dim_internal_by_id = {row["building_id"]: row for row in internal_rows if row["input"] == "dim"}

    t9.assert_gpkg_epsg25832(root / FOOTPRINT_GPKG, FOOTPRINT_LAYER)
    footprint_geojson = scratch_dir / "lod2_ground_plan.geojson"
    t9.convert_gpkg_to_geojson(root / FOOTPRINT_GPKG, footprint_geojson, FOOTPRINT_LAYER)
    footprints = t7.load_footprints(footprint_geojson, set(target_ids))
    t7.assert_epsg25832_footprints(footprints)

    dim_path = data / "work/w2/dim_v1_classified_z_minus0p174.laz"
    if not dim_path.exists():
        dim_path = data / "work/classify/dim_v1_classified_z.laz"
    bbox = t7.combined_bbox([footprints[bid] for bid in target_ids], buffer_m=12.0)
    dim_cloud = t7.read_cloud("DIM", [dim_path], bbox)
    t7.assert_epsg25832_cloud("DIM", dim_cloud)

    surface_by_id = {bid: t7.surface_metrics(dim_cloud, footprints[bid]) for bid in target_ids}
    camera_model = t7.parse_camera_model(data / "work/colmap/sparse/0/cameras.txt")
    scene_ref = read_json(data / "work/opf/opf/scene_reference_frame.json")
    cameras = t7.parse_colmap_cameras(data / "work/colmap/sparse/0/images.txt", scene_ref)
    t7.assert_epsg25832_camera_range(cameras)
    image_dir = root / IMAGE_DIR
    assert_image_inputs(image_dir, cameras)

    low_gradient_threshold = read_t9_low_gradient_threshold(docs / "W3_failure_surface_cause_thresholds.csv")
    candidates = t9.build_view_candidates(
        [FIGURE_FAILURE_ID],
        survivor_ids,
        footprints,
        surface_by_id,
        cameras,
        camera_model,
        scene_ref,
    )
    view_counts = t9.count_views(candidates)
    selected = select_near_nadir_candidates(candidates)
    crop_metrics = measure_sharp_crop_metrics(image_dir, selected, low_gradient_threshold)
    texture_by_id = summarize_sharp_metrics(crop_metrics)

    building_rows = build_building_rows(survivor_ids, quality_by_id, dim_internal_by_id, view_counts, texture_by_id)
    correlation_rows = build_correlation_rows(t10, building_rows)
    strata_rows = build_strata_rows(building_rows)
    observation = build_observation(correlation_rows, strata_rows)
    threshold_rows = build_threshold_rows(low_gradient_threshold)

    metrics_csv = docs / "W3_survivor_texture_refine_building_metrics.csv"
    correlations_csv = docs / "W3_survivor_texture_refine_correlations.csv"
    strata_csv = docs / "W3_survivor_texture_refine_strata.csv"
    thresholds_csv = docs / "W3_survivor_texture_refine_thresholds.csv"
    metrics_json = data / "work/diagnose/t11_survivor_texture_refine_metrics.json"
    scatter_fig = figs / "w3_survivor_t11_texture_refine_scatter.png"
    roof_fig = figs / "w3_t11_figure_1_1_roof_texture.png"
    report_md = docs / "W3_survivor_texture_refine.md"

    write_csv(metrics_csv, [format_building_row(row) for row in building_rows])
    write_csv(correlations_csv, correlation_rows)
    write_csv(strata_csv, strata_rows)
    write_csv(thresholds_csv, threshold_rows)
    write_metrics_json(metrics_json, run_id, building_rows, correlation_rows, strata_rows, threshold_rows, observation)
    render_scatter(scatter_fig, building_rows, correlation_rows)
    figure_examples = render_roof_crop_figure(roof_fig, image_dir, crop_metrics, low_gradient_threshold)
    write_report(
        report_md,
        run_id,
        run_dir,
        metrics_csv,
        correlations_csv,
        strata_csv,
        thresholds_csv,
        metrics_json,
        scatter_fig,
        roof_fig,
        correlation_rows,
        strata_rows,
        threshold_rows,
        figure_examples,
        observation,
    )
    add_to_g1_package(
        package,
        package_figs,
        report_md,
        metrics_csv,
        correlations_csv,
        strata_csv,
        thresholds_csv,
        scatter_fig,
        roof_fig,
    )
    copy_outputs(
        run_dir,
        [
            report_md,
            metrics_csv,
            correlations_csv,
            strata_csv,
            thresholds_csv,
            metrics_json,
            scatter_fig,
            roof_fig,
            package / "W3_survivor_texture_refine.md",
            package / "t11_survivor_texture_refine_building_metrics.csv",
            package / "t11_survivor_texture_refine_correlations.csv",
            package / "t11_survivor_texture_refine_strata.csv",
            package / "t11_survivor_texture_refine_thresholds.csv",
            package_figs / "fig_02_figure_1_1a_dim_unrecovered_4907182.png",
            package_figs / "fig_15_t11_survivor_texture_refine_scatter.png",
            package / "manifest.json",
        ],
    )

    main_corr = find_correlation(correlation_rows, "sharp_low_texture_pixel_ratio", "delta_plane_f1_als_minus_dim")
    print(f"survivor_n={len(building_rows)}")
    print(f"image_texture_n={sum(row['sharp_texture_sample_count'] > 0 for row in building_rows)}")
    print(f"sharp_low_texture_delta_f1_spearman_r={main_corr['spearman_r']}")
    print(f"sharp_low_texture_delta_f1_permutation_p={main_corr['p_value']}")
    print(f"observation={observation}")


def assert_t9_confirmed_failure(rows: list[dict[str, str]], building_id: str) -> None:
    row = next((item for item in rows if item["building_id"] == building_id), None)
    if row is None:
        raise RuntimeError(f"{building_id} is missing from T9 failure surface table")
    if row.get("surface_cause_classification") != "무텍스처" or row.get("surface_cause_recoverable") != "yes":
        raise RuntimeError(f"{building_id} is not a T9 texture-confirmed/recoverable failure row")
    if "below the control-success threshold" not in row.get("classification_note", ""):
        raise RuntimeError(f"{building_id} is not a T9 threshold-confirmed texture failure")


def read_t9_low_gradient_threshold(path: Path) -> float:
    rows = read_csv(path)
    for row in rows:
        if row["threshold"] == "texture_gradient_low_max":
            value = float(row["value"])
            if not np.isfinite(value) or value <= 0.0:
                raise RuntimeError(f"Invalid T9 low-gradient threshold: {row['value']}")
            return value
    raise RuntimeError(f"Missing texture_gradient_low_max in {path}")


def select_near_nadir_candidates(candidates: list[Any]) -> list[Any]:
    grouped: dict[str, list[Any]] = defaultdict(list)
    for candidate in candidates:
        if candidate.view_kind == "near_nadir":
            grouped[candidate.building_id].append(candidate)
    selected: list[Any] = []
    for bid, items in sorted(grouped.items()):
        items.sort(key=lambda item: (item.incidence_deg, -item.in_frame_fraction))
        limit = MAX_FAILURE_TEXTURE_VIEWS if bid == FIGURE_FAILURE_ID else MAX_SURVIVOR_TEXTURE_VIEWS
        selected.extend(items[:limit])
    return selected


def measure_sharp_crop_metrics(image_dir: Path, candidates: list[Any], low_gradient_threshold: float) -> list[SharpCropMetric]:
    candidates_by_image: dict[str, list[Any]] = defaultdict(list)
    for candidate in candidates:
        candidates_by_image[candidate.image_name].append(candidate)
    output: list[SharpCropMetric] = []
    for image_name, group in sorted(candidates_by_image.items()):
        with Image.open(image_dir / image_name) as image:
            rgb = image.convert("RGB")
            gray = np.asarray(rgb.convert("L"), dtype=np.float32) / 255.0
            width, height = rgb.size
            for candidate in group:
                metric = measure_single_sharp_crop(gray, width, height, candidate, low_gradient_threshold)
                if metric is not None:
                    output.append(metric)
    return output


def measure_single_sharp_crop(
    gray: np.ndarray,
    width: int,
    height: int,
    candidate: Any,
    low_gradient_threshold: float,
) -> SharpCropMetric | None:
    ring = candidate.projected_ring
    min_u = max(0, int(math.floor(float(np.min(ring[:, 0])))) - 3)
    min_v = max(0, int(math.floor(float(np.min(ring[:, 1])))) - 3)
    max_u = min(width, int(math.ceil(float(np.max(ring[:, 0])))) + 4)
    max_v = min(height, int(math.ceil(float(np.max(ring[:, 1])))) + 4)
    if max_u <= min_u + 2 or max_v <= min_v + 2:
        return None
    crop_gray = gray[min_v:max_v, min_u:max_u]
    polygon = ring - np.array([min_u, min_v], dtype=np.float64)
    mask_img = Image.new("L", (max_u - min_u, max_v - min_v), 0)
    draw = ImageDraw.Draw(mask_img)
    draw.polygon([tuple(map(float, pt)) for pt in polygon], fill=255)
    mask = np.asarray(mask_img, dtype=bool)
    mask_pixels = int(np.count_nonzero(mask))
    if mask_pixels < MIN_TEXTURE_PIXELS:
        return None
    pixels = crop_gray[mask]
    gy, gx = np.gradient(crop_gray)
    gradient = np.sqrt(gx * gx + gy * gy)
    roof_gradient = np.asarray(gradient[mask], dtype=np.float32)
    return SharpCropMetric(
        building_id=candidate.building_id,
        cohort=candidate.cohort,
        image_name=candidate.image_name,
        incidence_deg=float(candidate.incidence_deg),
        in_frame_fraction=float(candidate.in_frame_fraction),
        gradient_mean=float(np.mean(roof_gradient)),
        gradient_median=float(np.median(roof_gradient)),
        gradient_p10=float(np.percentile(roof_gradient, 10.0)),
        low_texture_pixel_ratio=float(np.count_nonzero(roof_gradient < low_gradient_threshold) / roof_gradient.size),
        gray_std=float(np.std(pixels)),
        brightness_median=float(np.median(pixels)),
        shadow_ratio=float(np.count_nonzero(pixels < 0.20) / mask_pixels),
        mask_pixel_count=mask_pixels,
        bbox=(min_u, min_v, max_u, max_v),
        polygon_in_crop=polygon,
        gradient_values=roof_gradient,
    )


def summarize_sharp_metrics(metrics: list[SharpCropMetric]) -> dict[str, dict[str, float]]:
    grouped: dict[str, list[SharpCropMetric]] = defaultdict(list)
    for metric in metrics:
        grouped[metric.building_id].append(metric)
    output: dict[str, dict[str, float]] = {}
    for bid, items in grouped.items():
        gradients = np.concatenate([item.gradient_values for item in items])
        total_pixels = int(sum(item.mask_pixel_count for item in items))
        low_pixels = sum(int(round(item.low_texture_pixel_ratio * item.mask_pixel_count)) for item in items)
        output[bid] = {
            "sharp_texture_sample_count": float(len(items)),
            "sharp_mask_pixel_count_total": float(total_pixels),
            "sharp_low_texture_pixel_ratio": float(low_pixels / total_pixels) if total_pixels else math.nan,
            "sharp_gradient_p10": float(np.percentile(gradients, 10.0)) if gradients.size else math.nan,
            "sharp_gradient_median": float(np.median(gradients)) if gradients.size else math.nan,
            "sharp_gradient_mean": float(np.mean(gradients)) if gradients.size else math.nan,
            "sharp_crop_gradient_p10_median": median([item.gradient_p10 for item in items]),
            "sharp_gray_std_median": median([item.gray_std for item in items]),
            "sharp_brightness_median": median([item.brightness_median for item in items]),
            "sharp_shadow_ratio_median": median([item.shadow_ratio for item in items]),
            "sharp_incidence_deg_median": median([item.incidence_deg for item in items]),
        }
    return output


def build_building_rows(
    survivor_ids: list[str],
    quality_by_id: dict[str, dict[str, str]],
    dim_internal_by_id: dict[str, dict[str, str]],
    view_counts: dict[str, dict[str, Any]],
    texture_by_id: dict[str, dict[str, float]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for bid in survivor_ids:
        quality = quality_by_id.get(bid)
        if quality is None:
            raise RuntimeError(f"Missing canonical quality metrics for survivor {bid}")
        internal = dim_internal_by_id.get(bid, {})
        texture = texture_by_id.get(bid, {})
        als_f1 = to_float(quality["als_plane_f1"])
        dim_f1 = to_float(quality["dim_plane_f1"])
        counts = view_counts.get(bid, {})
        rows.append(
            {
                "building_id": bid,
                "als_plane_f1": als_f1,
                "dim_plane_f1": dim_f1,
                "delta_plane_f1_als_minus_dim": als_f1 - dim_f1 if np.isfinite(als_f1) and np.isfinite(dim_f1) else math.nan,
                "dim_internal_boundary_hausdorff_m": to_float(internal.get("internal_boundary_hausdorff_m", "")),
                "dim_internal_boundary_chamfer_m": to_float(internal.get("internal_boundary_chamfer_m", "")),
                "dim_height_nmad_m": to_float(quality.get("dim_height_nmad_m", "")),
                "near_nadir_view_count": float(counts.get("near_nadir_view_count", 0)),
                "oblique_view_count": float(counts.get("oblique_view_count", 0)),
                "all_view_count": float(counts.get("all_view_count", 0)),
                "sharp_texture_sample_count": texture.get("sharp_texture_sample_count", 0.0),
                "sharp_mask_pixel_count_total": texture.get("sharp_mask_pixel_count_total", 0.0),
                "sharp_low_texture_pixel_ratio": texture.get("sharp_low_texture_pixel_ratio", math.nan),
                "sharp_gradient_p10": texture.get("sharp_gradient_p10", math.nan),
                "sharp_gradient_median": texture.get("sharp_gradient_median", math.nan),
                "sharp_gradient_mean": texture.get("sharp_gradient_mean", math.nan),
                "sharp_crop_gradient_p10_median": texture.get("sharp_crop_gradient_p10_median", math.nan),
                "sharp_gray_std_median": texture.get("sharp_gray_std_median", math.nan),
                "sharp_brightness_median": texture.get("sharp_brightness_median", math.nan),
                "sharp_shadow_ratio_median": texture.get("sharp_shadow_ratio_median", math.nan),
                "sharp_incidence_deg_median": texture.get("sharp_incidence_deg_median", math.nan),
            }
        )
    return rows


def build_correlation_rows(t10: Any, rows: list[dict[str, Any]]) -> list[dict[str, str]]:
    predictors = [
        ("sharp_low_texture_pixel_ratio", "higher means more roof pixels below the T9 low-gradient threshold"),
        ("sharp_gradient_p10", "higher means stronger worst-decile near-nadir roof texture"),
        ("sharp_gradient_median", "higher means stronger median near-nadir roof texture"),
        ("sharp_gradient_mean", "higher means stronger mean near-nadir roof texture"),
        ("sharp_shadow_ratio_median", "higher means darker/shadowed roof pixels"),
    ]
    targets = [
        ("dim_plane_f1", "DIM plane F1"),
        ("delta_plane_f1_als_minus_dim", "ALS-DIM plane F1 gap"),
        ("dim_internal_boundary_hausdorff_m", "DIM internal Hausdorff"),
    ]
    output: list[dict[str, str]] = []
    rng = np.random.default_rng(PERMUTATION_SEED)
    for predictor, predictor_note in predictors:
        for target, target_note in targets:
            x = np.array([float(row.get(predictor, math.nan)) for row in rows], dtype=np.float64)
            y = np.array([float(row.get(target, math.nan)) for row in rows], dtype=np.float64)
            mask = np.isfinite(x) & np.isfinite(y)
            if int(np.count_nonzero(mask)) < 5:
                rho = math.nan
                p_value = math.nan
            else:
                rho, p_value = t10.spearman_permutation_p(x[mask], y[mask], rng)
            output.append(
                {
                    "predictor": predictor,
                    "target": target,
                    "n": str(int(np.count_nonzero(mask))),
                    "spearman_r": fmt(rho, 4),
                    "p_value": fmt(p_value, 4),
                    "predictor_note": predictor_note,
                    "target_note": target_note,
                }
            )
    return output


def build_strata_rows(rows: list[dict[str, Any]]) -> list[dict[str, str]]:
    ratios = np.array([row["sharp_low_texture_pixel_ratio"] for row in rows if np.isfinite(row["sharp_low_texture_pixel_ratio"])], dtype=np.float64)
    if ratios.size == 0:
        return []
    cutoff = float(np.median(ratios))
    low_texture = [row for row in rows if np.isfinite(row["sharp_low_texture_pixel_ratio"]) and row["sharp_low_texture_pixel_ratio"] >= cutoff]
    high_texture = [row for row in rows if np.isfinite(row["sharp_low_texture_pixel_ratio"]) and row["sharp_low_texture_pixel_ratio"] < cutoff]
    return [
        format_stratum("low_texture_high_lowgrad_share", low_texture, cutoff),
        format_stratum("high_texture_low_lowgrad_share", high_texture, cutoff),
    ]


def format_stratum(label: str, rows: list[dict[str, Any]], cutoff: float) -> dict[str, str]:
    return {
        "stratum": label,
        "n": str(len(rows)),
        "low_texture_pixel_ratio_cutoff": fmt(cutoff, 4),
        "low_texture_pixel_ratio_median": fmt(median([row["sharp_low_texture_pixel_ratio"] for row in rows]), 4),
        "sharp_gradient_p10_median": fmt(median([row["sharp_gradient_p10"] for row in rows]), 5),
        "delta_plane_f1_median": fmt(median([row["delta_plane_f1_als_minus_dim"] for row in rows]), 4),
        "delta_plane_f1_p25": fmt(percentile([row["delta_plane_f1_als_minus_dim"] for row in rows], 25.0), 4),
        "delta_plane_f1_p75": fmt(percentile([row["delta_plane_f1_als_minus_dim"] for row in rows], 75.0), 4),
        "dim_plane_f1_median": fmt(median([row["dim_plane_f1"] for row in rows]), 4),
        "dim_internal_hausdorff_median_m": fmt(median([row["dim_internal_boundary_hausdorff_m"] for row in rows]), 4),
    }


def build_observation(correlation_rows: list[dict[str, str]], strata_rows: list[dict[str, str]]) -> str:
    main = find_correlation(correlation_rows, "sharp_low_texture_pixel_ratio", "delta_plane_f1_als_minus_dim")
    rho = to_float(main["spearman_r"])
    p_value = to_float(main["p_value"])
    low = next((row for row in strata_rows if row["stratum"] == "low_texture_high_lowgrad_share"), None)
    high = next((row for row in strata_rows if row["stratum"] == "high_texture_low_lowgrad_share"), None)
    low_gap = to_float(low["delta_plane_f1_median"]) if low else math.nan
    high_gap = to_float(high["delta_plane_f1_median"]) if high else math.nan
    support = np.isfinite(rho) and rho >= 0.30 and p_value <= 0.10 and np.isfinite(low_gap) and np.isfinite(high_gap) and low_gap > high_gap
    direction = "통합 메커니즘 지지 관찰" if support else "통합 메커니즘 불지지/약함 관찰"
    return (
        f"날카로운 텍스처 지표로 survivor ΔF1 상관 r={rho:.3f}, p={p_value:.4f}; "
        f"저텍스처 strata ΔF1 중앙값 {low_gap:.3f}, 고텍스처 {high_gap:.3f} -> {direction}(판정 아님, E5 확증 필요)."
    )


def build_threshold_rows(low_gradient_threshold: float) -> list[dict[str, str]]:
    return [
        {
            "threshold": "near_nadir_incidence_max_deg",
            "value": fmt(NEAR_NADIR_MAX_INCIDENT_DEG, 3),
            "source": "fixed T9 definition",
            "interpretation": "view is near-nadir when incidence angle is <= threshold",
        },
        {
            "threshold": "local_gradient_low_threshold",
            "value": fmt(low_gradient_threshold, 5),
            "source": "docs/W3_failure_surface_cause_thresholds.csv texture_gradient_low_max",
            "interpretation": "roof pixel is low-texture when local grayscale gradient is below this value",
        },
        {
            "threshold": "max_survivor_near_nadir_views",
            "value": str(MAX_SURVIVOR_TEXTURE_VIEWS),
            "source": "T10/T11 fixed sampling cap",
            "interpretation": "nearest-nadir survivor views used for per-building image texture",
        },
        {
            "threshold": "figure_textureless_failure_id",
            "value": FIGURE_FAILURE_ID,
            "source": "T9 threshold-confirmed texture failure",
            "interpretation": "failure crop used for regenerated Figure 1.1",
        },
    ]


def write_metrics_json(
    path: Path,
    run_id: str,
    building_rows: list[dict[str, Any]],
    correlation_rows: list[dict[str, str]],
    strata_rows: list[dict[str, str]],
    threshold_rows: list[dict[str, str]],
    observation: str,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "run_id": run_id,
        "task_id": TASK_ID,
        "canonical_run": CANONICAL_RUN,
        "crs": "EPSG:25832 numeric UTM32 for footprints, DIM LAZ, and camera centers after T2 OPF scene-reference transform",
        "survivor_count": len(building_rows),
        "permutation_count": PERMUTATION_COUNT,
        "permutation_seed": PERMUTATION_SEED,
        "observation": observation,
        "thresholds": threshold_rows,
        "correlations": correlation_rows,
        "strata": strata_rows,
        "rows": sanitize_json(building_rows),
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def render_scatter(out_path: Path, rows: list[dict[str, Any]], correlation_rows: list[dict[str, str]]) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    x = np.array([row["sharp_low_texture_pixel_ratio"] for row in rows], dtype=np.float64)
    y = np.array([row["delta_plane_f1_als_minus_dim"] for row in rows], dtype=np.float64)
    mask = np.isfinite(x) & np.isfinite(y)
    cutoff = float(np.median(x[mask]))
    colors = np.where(x[mask] >= cutoff, "#d62728", "#2f6fbb")
    main = find_correlation(correlation_rows, "sharp_low_texture_pixel_ratio", "delta_plane_f1_als_minus_dim")
    fig, ax = plt.subplots(figsize=(7.4, 5.2), constrained_layout=True)
    ax.scatter(x[mask], y[mask], c=colors, s=42, alpha=0.85, edgecolors="#222222", linewidths=0.3)
    if np.count_nonzero(mask) >= 2:
        coef = np.polyfit(x[mask], y[mask], deg=1)
        xs = np.linspace(float(np.min(x[mask])), float(np.max(x[mask])), 100)
        ax.plot(xs, coef[0] * xs + coef[1], color="#222222", linewidth=1.1)
    ax.axvline(cutoff, color="#777777", linestyle="--", linewidth=0.9)
    ax.axhline(0.0, color="#999999", linestyle=":", linewidth=0.8)
    ax.set_xlabel("Low-texture roof-pixel ratio (local gradient below T9 threshold)")
    ax.set_ylabel("Plane F1 gap (ALS - DIM)")
    ax.set_title(f"T11 refined image texture vs plane F1 gap\nSpearman r={main['spearman_r']}, p={main['p_value']}, n={main['n']}")
    ax.grid(True, linewidth=0.3, alpha=0.35)
    fig.savefig(out_path, dpi=220)
    plt.close(fig)


def render_roof_crop_figure(
    out_path: Path,
    image_dir: Path,
    crop_metrics: list[SharpCropMetric],
    low_gradient_threshold: float,
) -> list[dict[str, str]]:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    textured = [
        item
        for item in crop_metrics
        if item.cohort == "control_success_71" and np.isfinite(item.gradient_p10) and item.mask_pixel_count >= MIN_TEXTURE_PIXELS
    ]
    textureless = [
        item
        for item in crop_metrics
        if item.building_id == FIGURE_FAILURE_ID and np.isfinite(item.gradient_p10) and item.mask_pixel_count >= MIN_TEXTURE_PIXELS
    ]
    if not textured or not textureless:
        raise RuntimeError("Not enough crop metrics to render T11 Figure 1.1")
    high = max(textured, key=lambda item: (item.gradient_p10, item.gradient_median, -item.low_texture_pixel_ratio))
    low = max(textureless, key=lambda item: (item.low_texture_pixel_ratio, -item.gradient_p10))
    examples = [
        extract_roof_patch("textured_survivor", image_dir / high.image_name, high, low_gradient_threshold, prefer="high"),
        extract_roof_patch("textureless_failure", image_dir / low.image_name, low, low_gradient_threshold, prefer="low"),
    ]
    fig, axes = plt.subplots(1, 2, figsize=(9.2, 4.2), constrained_layout=True)
    for ax, patch in zip(axes, examples):
        title = "textured survivor roof patch" if patch.panel == "textured_survivor" else "textureless failure roof patch"
        ax.imshow(patch.rgb)
        short_id = patch.building_id.replace("DEBY_LOD2_", "")
        ax.set_title(
            f"{title}\n{short_id}, p10={patch.gradient_p10:.4f}, low-px={patch.low_texture_pixel_ratio:.2f}, inc={patch.incidence_deg:.1f} deg",
            fontsize=8.5,
        )
        ax.set_axis_off()
    fig.suptitle("Figure 1.1 refined: near-nadir roof-only interior patches", fontsize=11)
    fig.savefig(out_path, dpi=240)
    plt.close(fig)
    return [format_figure_example(patch) for patch in examples]


def extract_roof_patch(
    panel: str,
    image_path: Path,
    metric: SharpCropMetric,
    low_gradient_threshold: float,
    prefer: str,
) -> FigurePatch:
    with Image.open(image_path) as image:
        rgb = image.convert("RGB")
        crop_img = rgb.crop(metric.bbox)
        crop = np.asarray(crop_img)
    gray = np.asarray(crop_img.convert("L"), dtype=np.float32) / 255.0
    mask_img = Image.new("L", crop_img.size, 0)
    draw = ImageDraw.Draw(mask_img)
    draw.polygon([tuple(map(float, pt)) for pt in metric.polygon_in_crop], fill=255)
    mask = np.asarray(mask_img, dtype=bool)
    gy, gx = np.gradient(gray)
    gradient = np.sqrt(gx * gx + gy * gy)
    h, w = gray.shape
    max_size = max(48, min(h, w))
    candidate_sizes = sorted(
        {size for size in (360, 300, 240, 200, 160, 128, 96, 72, 48) if size <= max_size},
        reverse=True,
    )
    for coverage_min in (0.985, 0.95, 0.90):
        best: tuple[float, int, int, int, np.ndarray, np.ndarray] | None = None
        for size in candidate_sizes:
            step = max(size // 5, 12)
            for y0 in range(0, max(h - size + 1, 1), step):
                for x0 in range(0, max(w - size + 1, 1), step):
                    patch_mask = mask[y0 : y0 + size, x0 : x0 + size]
                    if patch_mask.shape != (size, size):
                        continue
                    coverage = float(np.count_nonzero(patch_mask) / patch_mask.size)
                    if coverage < coverage_min:
                        continue
                    values = gradient[y0 : y0 + size, x0 : x0 + size][patch_mask]
                    if values.size < MIN_TEXTURE_PIXELS:
                        continue
                    p10 = float(np.percentile(values, 10.0))
                    low_ratio = float(np.count_nonzero(values < low_gradient_threshold) / values.size)
                    mean = float(np.mean(values))
                    if prefer == "high":
                        score = p10 + 0.25 * mean - 0.02 * low_ratio + 0.0001 * size
                    else:
                        score = low_ratio - p10 - 0.1 * mean + 0.0001 * size
                    if best is None or score > best[0]:
                        best = (score, x0, y0, size, values, patch_mask)
        if best is not None:
            _score, x0, y0, size, values, patch_mask = best
            patch_rgb = crop[y0 : y0 + size, x0 : x0 + size].copy()
            white = np.full_like(patch_rgb, 255)
            white[patch_mask] = patch_rgb[patch_mask]
            return FigurePatch(
                panel=panel,
                building_id=metric.building_id,
                image_name=metric.image_name,
                gradient_p10=float(np.percentile(values, 10.0)),
                low_texture_pixel_ratio=float(np.count_nonzero(values < low_gradient_threshold) / values.size),
                incidence_deg=metric.incidence_deg,
                mask_pixel_count=int(values.size),
                patch_size_px=size,
                rgb=white,
            )

    values = gradient[mask]
    white = np.full_like(crop, 255)
    white[mask] = crop[mask]
    return FigurePatch(
        panel=panel,
        building_id=metric.building_id,
        image_name=metric.image_name,
        gradient_p10=float(np.percentile(values, 10.0)),
        low_texture_pixel_ratio=float(np.count_nonzero(values < low_gradient_threshold) / values.size),
        incidence_deg=metric.incidence_deg,
        mask_pixel_count=int(values.size),
        patch_size_px=int(min(h, w)),
        rgb=white,
    )


def format_figure_example(patch: FigurePatch) -> dict[str, str]:
    return {
        "panel": patch.panel,
        "building_id": patch.building_id,
        "image_name": patch.image_name,
        "gradient_p10": fmt(patch.gradient_p10, 5),
        "low_texture_pixel_ratio": fmt(patch.low_texture_pixel_ratio, 4),
        "incidence_deg": fmt(patch.incidence_deg, 2),
        "mask_pixel_count": str(patch.mask_pixel_count),
        "patch_size_px": str(patch.patch_size_px),
    }


def write_report(
    out_path: Path,
    run_id: str,
    run_dir: Path,
    metrics_csv: Path,
    correlations_csv: Path,
    strata_csv: Path,
    thresholds_csv: Path,
    metrics_json: Path,
    scatter_fig: Path,
    roof_fig: Path,
    correlation_rows: list[dict[str, str]],
    strata_rows: list[dict[str, str]],
    threshold_rows: list[dict[str, str]],
    figure_examples: list[dict[str, str]],
    observation: str,
) -> None:
    main_rows = [
        row
        for row in correlation_rows
        if row["predictor"] in {"sharp_low_texture_pixel_ratio", "sharp_gradient_p10", "sharp_gradient_median"}
        and row["target"] in {"dim_plane_f1", "delta_plane_f1_als_minus_dim", "dim_internal_boundary_hausdorff_m"}
    ]
    out_path.write_text(
        "\n".join(
            [
                "# W3 Survivor Texture Refine (T11)",
                "",
                f"- Run ID: {run_id}",
                f"- Run directory: {rel(run_dir)}",
                f"- Canonical input: `{CANONICAL_RUN}`",
                f"- Building metrics CSV: `{rel(metrics_csv)}`",
                f"- Correlation CSV: `{rel(correlations_csv)}`",
                f"- Strata CSV: `{rel(strata_csv)}`",
                f"- Threshold CSV: `{rel(thresholds_csv)}`",
                f"- Metrics JSON: `{rel(metrics_json)}`",
                "- Inputs: T7 survivor 71 IDs, canonical W3 paired quality metrics, T9 thresholds/failure class, original UAV images, T2 COLMAP poses, T5 footprint GPKG, and T3 DIM LAZ.",
                "- CRS: EPSG:25832 numeric UTM32 for footprints, DIM LAZ, and camera centers after T2 scene-reference transform.",
                "- Scope: direct image-texture correlation/stratified observation only. P0 acceptance/rejection remains outside this T11 output.",
                "",
                "## Observation",
                "",
                f"- {observation}",
                "",
                "## Refined Correlations",
                "",
                markdown_table(main_rows, ["predictor", "target", "n", "spearman_r", "p_value", "predictor_note"]),
                "",
                "## Texture Strata",
                "",
                markdown_table(
                    strata_rows,
                    [
                        "stratum",
                        "n",
                        "low_texture_pixel_ratio_cutoff",
                        "low_texture_pixel_ratio_median",
                        "sharp_gradient_p10_median",
                        "delta_plane_f1_median",
                        "delta_plane_f1_p25",
                        "delta_plane_f1_p75",
                        "dim_plane_f1_median",
                        "dim_internal_hausdorff_median_m",
                    ],
                ),
                "",
                "## Adopted Thresholds",
                "",
                markdown_table(threshold_rows, ["threshold", "value", "source", "interpretation"]),
                "",
                "## Figure 1.1 Crop Selection",
                "",
                markdown_table(
                    figure_examples,
                    [
                        "panel",
                        "building_id",
                        "image_name",
                        "gradient_p10",
                        "low_texture_pixel_ratio",
                        "incidence_deg",
                        "mask_pixel_count",
                        "patch_size_px",
                    ],
                ),
                "",
                f"![refined Figure 1.1 roof crops]({rel(roof_fig).replace('docs/', '')})",
                "",
                "## Scatter",
                "",
                f"![refined texture vs plane F1 gap]({rel(scatter_fig).replace('docs/', '')})",
                "",
                "## Notes",
                "",
                "- `sharp_low_texture_pixel_ratio` is the footprint-mask roof-pixel fraction whose local grayscale gradient is below the T9 control-success low-gradient threshold.",
                "- `sharp_gradient_p10` is computed from all selected near-nadir roof-mask pixels per building, not from view-level medians.",
                f"- Spearman p-values use a deterministic {PERMUTATION_COUNT}-permutation two-sided test with seed {PERMUTATION_SEED}.",
                "- Internal Hausdorff correlations use only survivor buildings with measurable DIM internal boundaries.",
                "- Figure 1.1 selects high-coverage interior patches from the projected footprint roof polygon, so the displayed crops exclude visible walls/windows outside the footprint.",
                "- This T11 output tests whether survivor degradation follows the same texture mechanism as the T9 failure extreme; it is not a method-level conclusion.",
                "",
            ]
        ),
        encoding="utf-8",
    )


def add_to_g1_package(
    package: Path,
    package_figs: Path,
    report_md: Path,
    metrics_csv: Path,
    correlations_csv: Path,
    strata_csv: Path,
    thresholds_csv: Path,
    scatter_fig: Path,
    roof_fig: Path,
) -> None:
    package.mkdir(parents=True, exist_ok=True)
    package_figs.mkdir(parents=True, exist_ok=True)
    targets = [
        (report_md, package / "W3_survivor_texture_refine.md"),
        (metrics_csv, package / "t11_survivor_texture_refine_building_metrics.csv"),
        (correlations_csv, package / "t11_survivor_texture_refine_correlations.csv"),
        (strata_csv, package / "t11_survivor_texture_refine_strata.csv"),
        (thresholds_csv, package / "t11_survivor_texture_refine_thresholds.csv"),
        (roof_fig, package_figs / "fig_02_figure_1_1a_dim_unrecovered_4907182.png"),
        (scatter_fig, package_figs / "fig_15_t11_survivor_texture_refine_scatter.png"),
    ]
    for src, dst in targets:
        shutil.copy2(src, dst)
    update_package_captions(package / "captions.md")
    manifest_path = package / "manifest.json"
    if manifest_path.exists():
        manifest = read_json(manifest_path)
    else:
        manifest = {"package": "G1_package", "canonical_run": CANONICAL_RUN, "files": [], "figure_count": 0}
    files = set(manifest.get("files", []))
    for _, dst in targets:
        files.add(dst.relative_to(package).as_posix())
    files.add("captions.md")
    manifest["files"] = sorted(files)
    manifest["figure_count"] = sum(1 for item in manifest["files"] if item.startswith("figs/") and item.endswith(".png"))
    manifest["t11_survivor_texture_refine"] = {
        "report": "W3_survivor_texture_refine.md",
        "figure_1_1": "figs/fig_02_figure_1_1a_dim_unrecovered_4907182.png",
        "scatter": "figs/fig_15_t11_survivor_texture_refine_scatter.png",
        "tables": [
            "t11_survivor_texture_refine_building_metrics.csv",
            "t11_survivor_texture_refine_correlations.csv",
            "t11_survivor_texture_refine_strata.csv",
            "t11_survivor_texture_refine_thresholds.csv",
        ],
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def update_package_captions(path: Path) -> None:
    if not path.exists():
        return
    lines = path.read_text(encoding="utf-8").splitlines()
    figure2 = "| Figure 2 | figs/fig_02_figure_1_1a_dim_unrecovered_4907182.png | Figure 1.1 refined: near-nadir roof-only crops contrasting a high-texture survivor roof with threshold-confirmed textureless failure DEBY_LOD2_4907182. |"
    figure15 = "| Figure 15 | figs/fig_15_t11_survivor_texture_refine_scatter.png | T11 survivor low-texture roof-pixel ratio versus ALS-DIM plane F1 gap; colors split the median low-texture ratio strata. |"
    updated: list[str] = []
    replaced2 = False
    replaced15 = False
    for line in lines:
        if line.startswith("| Figure 2 |"):
            updated.append(figure2)
            replaced2 = True
        elif line.startswith("| Figure 15 |"):
            updated.append(figure15)
            replaced15 = True
        else:
            updated.append(line)
    if not replaced2:
        updated.append(figure2)
    if not replaced15:
        updated.append(figure15)
    path.write_text("\n".join(updated) + "\n", encoding="utf-8")


def format_building_row(row: dict[str, Any]) -> dict[str, str]:
    fields = [
        "building_id",
        "als_plane_f1",
        "dim_plane_f1",
        "delta_plane_f1_als_minus_dim",
        "dim_internal_boundary_hausdorff_m",
        "dim_internal_boundary_chamfer_m",
        "dim_height_nmad_m",
        "near_nadir_view_count",
        "oblique_view_count",
        "all_view_count",
        "sharp_texture_sample_count",
        "sharp_mask_pixel_count_total",
        "sharp_low_texture_pixel_ratio",
        "sharp_gradient_p10",
        "sharp_gradient_median",
        "sharp_gradient_mean",
        "sharp_crop_gradient_p10_median",
        "sharp_gray_std_median",
        "sharp_brightness_median",
        "sharp_shadow_ratio_median",
        "sharp_incidence_deg_median",
    ]
    output: dict[str, str] = {}
    int_fields = {
        "near_nadir_view_count",
        "oblique_view_count",
        "all_view_count",
        "sharp_texture_sample_count",
        "sharp_mask_pixel_count_total",
    }
    for field_name in fields:
        value = row.get(field_name, "")
        if field_name == "building_id":
            output[field_name] = str(value)
        elif field_name in int_fields:
            output[field_name] = str(int(float(value))) if np.isfinite(float(value)) else "n/a"
        else:
            output[field_name] = fmt(float(value), 5 if "gradient" in field_name or "ratio" in field_name or "std" in field_name else 4)
    return output


def load_helper_module(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load helper module {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fieldnames = list(rows[0].keys())
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def assert_image_inputs(image_dir: Path, cameras: list[Any]) -> None:
    missing = [camera.name for camera in cameras if not (image_dir / camera.name).exists()]
    if missing:
        raise FileNotFoundError(f"Missing {len(missing)} images under {image_dir}: {', '.join(missing[:5])}")


def run(
    cmd: list[str],
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
    log_path: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    print("+ " + " ".join(cmd), flush=True)
    if log_path:
        with log_path.open("w", encoding="utf-8") as log:
            log.write("+ " + " ".join(cmd) + "\n")
            proc = subprocess.run(cmd, cwd=cwd, env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            log.write(proc.stdout)
            print(proc.stdout, end="", flush=True)
            proc.check_returncode()
            return proc
    return subprocess.run(cmd, cwd=cwd, env=env, text=True, check=True)


def capture(cmd: list[str], cwd: Path | None = None) -> str:
    proc = subprocess.run(cmd, cwd=cwd, text=True, capture_output=True, check=False)
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr or proc.stdout).strip())
    return proc.stdout


def record_issue(repo: Path, run_id: str, message: str) -> None:
    issues = repo / "phases/p0-audit/docs/issues.md"
    with issues.open("a", encoding="utf-8") as fh:
        fh.write(f"\n## {TASK_ID} Survivor Texture Refine\n\n")
        fh.write(f"- {run_id}: {message}. See runs/{run_id}/logs/.\n")


def write_host_config(run_dir: Path, run_id: str, git_commit: str) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "config.yaml").write_text(
        "\n".join(
            [
                f"task_id: {TASK_ID}",
                f"run_id: {run_id}",
                f"git_commit: {git_commit}",
                "canonical_run: " + CANONICAL_RUN,
                "survivor_ids: docs/W3_failure_diagnosis_building_metrics.csv cohort=control_success_71",
                "quality_metrics: docs/W3_2c_canonical_roofer_quality_metrics.csv",
                "internal_boundary: docs/W3_2c_canonical_internal_boundary_metrics.csv",
                "t9_thresholds: docs/W3_failure_surface_cause_thresholds.csv",
                "dim_pointcloud: data/work/w2/dim_v1_classified_z_minus0p174.laz",
                "images: " + IMAGE_DIR,
                "footprints: " + FOOTPRINT_GPKG,
                "crs: EPSG:25832 numeric UTM32 coordinates",
                f"near_nadir_incidence_max_deg: {NEAR_NADIR_MAX_INCIDENT_DEG}",
                f"spearman_permutations: {PERMUTATION_COUNT}",
                "classification_rule: correlation/strata observation only; no P0 judgement",
                "",
            ]
        ),
        encoding="utf-8",
    )


def write_host_versions(
    repo: Path,
    run_dir: Path,
    compose: list[str],
    env: dict[str, str],
    git_commit: str,
) -> None:
    lines = [
        "# T11 Survivor Texture Refine Tool Versions",
        "",
        f"- Generated: {datetime.now(timezone.utc).astimezone().isoformat(timespec='seconds')}",
        f"- Run ID: {run_dir.name}",
        f"- Repository commit: {git_commit}",
        "",
        "```console",
    ]
    version_cmds = [
        ["git", "status", "--short", "--branch"],
        compose + ["run", "-T", "--rm", "tools", "python", "--version"],
        compose
        + [
            "run",
            "-T",
            "--rm",
            "tools",
            "python",
            "-c",
            "import PIL, laspy, matplotlib, numpy; print('Pillow=' + PIL.__version__); print('laspy=' + laspy.__version__); print('matplotlib=' + matplotlib.__version__); print('numpy=' + numpy.__version__)",
        ],
        compose + ["run", "-T", "--rm", "tools", "ogrinfo", "--version"],
    ]
    for cmd in version_cmds:
        proc = subprocess.run(cmd, cwd=repo, env=env, text=True, capture_output=True, check=False)
        lines.append("$ " + " ".join(cmd))
        out = (proc.stdout or proc.stderr).strip()
        if out:
            lines.append(out)
        if proc.returncode != 0:
            lines.append(f"[exit {proc.returncode}]")
    lines.append("```")
    (run_dir / "versions.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")


def copy_outputs(run_dir: Path, paths: list[Path]) -> None:
    snapshot = run_dir / "outputs"
    snapshot.mkdir(parents=True, exist_ok=True)
    for path in paths:
        if not path.exists():
            continue
        if path.is_relative_to(Path("/workspace/docs")):
            dst = snapshot / "docs" / path.relative_to(Path("/workspace/docs"))
        elif path.is_relative_to(Path("/workspace/data")):
            dst = snapshot / "data" / path.relative_to(Path("/workspace/data"))
        else:
            dst = snapshot / path.name
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, dst)


def find_correlation(correlation_rows: list[dict[str, str]], predictor: str, target: str) -> dict[str, str]:
    for row in correlation_rows:
        if row["predictor"] == predictor and row["target"] == target:
            return row
    raise KeyError((predictor, target))


def markdown_table(rows: list[dict[str, str]], columns: list[str]) -> str:
    if not rows:
        return "_No rows._"
    lines = [
        "| " + " | ".join(columns) + " |",
        "| " + " | ".join("---" for _ in columns) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(str(row.get(col, "")) for col in columns) + " |")
    return "\n".join(lines)


def sanitize_json(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: sanitize_json(val) for key, val in value.items()}
    if isinstance(value, list):
        return [sanitize_json(item) for item in value]
    if isinstance(value, float) and not np.isfinite(value):
        return None
    if isinstance(value, np.generic):
        return value.item()
    return value


def to_float(value: Any) -> float:
    if value is None or value == "":
        return math.nan
    try:
        return float(value)
    except (TypeError, ValueError):
        return math.nan


def median(values: list[float]) -> float:
    arr = np.array([value for value in values if np.isfinite(float(value))], dtype=np.float64)
    return float(np.median(arr)) if arr.size else math.nan


def percentile(values: list[float], q: float) -> float:
    arr = np.array([value for value in values if np.isfinite(float(value))], dtype=np.float64)
    return float(np.percentile(arr, q)) if arr.size else math.nan


def fmt(value: float, decimals: int) -> str:
    if value is None or not np.isfinite(float(value)):
        return "n/a"
    return f"{float(value):.{decimals}f}"


def rel(path: Path) -> str:
    return path.as_posix().replace("/workspace/", "")


def main() -> None:
    if os.environ.get("P0_INSIDE_CONTAINER") == "1":
        compute_entrypoint()
    else:
        host_entrypoint()


if __name__ == "__main__":
    main()
