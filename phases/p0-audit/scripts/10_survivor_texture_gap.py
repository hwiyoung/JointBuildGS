#!/usr/bin/env python3
"""T10 survivor texture-gap correlation test.

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
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageDraw


TASK_ID = "T10"
CANONICAL_RUN = "w3_2b_roofer_repeatability_20260612_220747/run_2"
BUILDING_CLASS = 6
GRID_CELL_M = 1.0
FOOTPRINT_GPKG = "data/work/footprints/lod2_ground_plan.gpkg"
FOOTPRINT_LAYER = "lod2_ground_plan"
IMAGE_DIR = "data/work/images/Images"
NEAR_NADIR_MAX_INCIDENT_DEG = 20.0
MIN_IN_FRAME_FRACTION = 0.35
MIN_TEXTURE_PIXELS = 80
MAX_IMAGE_TEXTURE_VIEWS = 8
PERMUTATION_COUNT = 9999
PERMUTATION_SEED = 20260615


@dataclass
class ImageTextureMetric:
    building_id: str
    image_name: str
    texture_gradient_mean: float
    gray_std: float
    brightness_median: float
    shadow_ratio: float
    incidence_deg: float
    mask_pixel_count: int


def host_entrypoint() -> None:
    repo = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env.setdefault("P0_UID", str(os.getuid()))
    env.setdefault("P0_GID", str(os.getgid()))
    run_id = env.get("RUN_ID") or datetime.now().strftime("t10_survivor_texture_gap_%Y%m%d_%H%M%S")
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
                "/workspace/scripts/10_survivor_texture_gap.py",
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
    print("report=docs/W3_survivor_texture_gap.md")


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

    t7_rows = read_csv(docs / "W3_failure_diagnosis_building_metrics.csv")
    survivor_ids = [row["building_id"] for row in t7_rows if row["cohort"] == "control_success_71"]
    if len(survivor_ids) != 71:
        raise RuntimeError(f"Expected 71 survivor/control-success buildings from T7, got {len(survivor_ids)}")

    quality_rows = read_csv(docs / "W3_2c_canonical_roofer_quality_metrics.csv")
    quality_by_id = {row["building_id"]: row for row in quality_rows}
    internal_rows = read_csv(docs / "W3_2c_canonical_internal_boundary_metrics.csv")
    dim_internal_by_id = {row["building_id"]: row for row in internal_rows if row["input"] == "dim"}

    footprint_gpkg = root / FOOTPRINT_GPKG
    t9.assert_gpkg_epsg25832(footprint_gpkg, FOOTPRINT_LAYER)
    footprint_geojson = scratch_dir / "lod2_ground_plan.geojson"
    t9.convert_gpkg_to_geojson(footprint_gpkg, footprint_geojson, FOOTPRINT_LAYER)
    footprints = t7.load_footprints(footprint_geojson, set(survivor_ids))
    t7.assert_epsg25832_footprints(footprints)

    dim_path = data / "work/w2/dim_v1_classified_z_minus0p174.laz"
    if not dim_path.exists():
        dim_path = data / "work/classify/dim_v1_classified_z.laz"
    bbox = t7.combined_bbox([footprints[bid] for bid in survivor_ids], buffer_m=12.0)
    dim_cloud = t7.read_cloud("DIM", [dim_path], bbox)
    t7.assert_epsg25832_cloud("DIM", dim_cloud)

    point_metrics: dict[str, dict[str, float]] = {}
    surface_by_id: dict[str, Any] = {}
    for bid in survivor_ids:
        footprint = footprints[bid]
        surface = t7.surface_metrics(dim_cloud, footprint)
        surface_by_id[bid] = surface
        x, y, _z = t7.clip_building_points(dim_cloud, footprint)
        point_metrics[bid] = {
            "dim_point_count": float(surface.point_count),
            "dim_density_pts_m2": surface.density_pts_m2,
            "dim_hole_ratio": surface.hole_ratio,
            "dim_density_cv": grid_density_cv(t7, x, y, footprint),
            "dim_plane_rmse_m": surface.plane_rmse_m,
        }

    camera_model = t7.parse_camera_model(data / "work/colmap/sparse/0/cameras.txt")
    scene_ref = read_json(data / "work/opf/opf/scene_reference_frame.json")
    cameras = t7.parse_colmap_cameras(data / "work/colmap/sparse/0/images.txt", scene_ref)
    t7.assert_epsg25832_camera_range(cameras)
    image_dir = root / IMAGE_DIR
    assert_image_inputs(image_dir, cameras)
    image_metrics = measure_survivor_image_texture(
        t7,
        image_dir,
        survivor_ids,
        footprints,
        surface_by_id,
        cameras,
        camera_model,
        scene_ref,
    )
    image_by_id = summarize_image_texture(image_metrics)

    building_rows = build_building_rows(
        survivor_ids,
        quality_by_id,
        dim_internal_by_id,
        point_metrics,
        image_by_id,
    )
    add_texture_deficit_scores(building_rows)
    correlation_rows = build_correlation_rows(building_rows)
    strata_rows = build_strata_rows(building_rows)
    observation = build_observation(correlation_rows, strata_rows)

    metrics_csv = docs / "W3_survivor_texture_gap_building_metrics.csv"
    correlations_csv = docs / "W3_survivor_texture_gap_correlations.csv"
    strata_csv = docs / "W3_survivor_texture_gap_strata.csv"
    metrics_json = data / "work/diagnose/t10_survivor_texture_gap_metrics.json"
    scatter_fig = figs / "w3_survivor_t10_texture_gap_scatter.png"
    report_md = docs / "W3_survivor_texture_gap.md"

    write_csv(metrics_csv, [format_building_row(row) for row in building_rows])
    write_csv(correlations_csv, correlation_rows)
    write_csv(strata_csv, strata_rows)
    write_metrics_json(metrics_json, run_id, building_rows, correlation_rows, strata_rows, observation)
    render_scatter(scatter_fig, building_rows, correlation_rows)
    write_report(
        report_md,
        run_id,
        run_dir,
        metrics_csv,
        correlations_csv,
        strata_csv,
        metrics_json,
        scatter_fig,
        correlation_rows,
        strata_rows,
        observation,
    )
    add_to_g1_package(package, package_figs, report_md, metrics_csv, correlations_csv, strata_csv, scatter_fig)
    copy_outputs(
        run_dir,
        [
            report_md,
            metrics_csv,
            correlations_csv,
            strata_csv,
            metrics_json,
            scatter_fig,
            package / "W3_survivor_texture_gap.md",
            package / "t10_survivor_texture_gap_building_metrics.csv",
            package / "t10_survivor_texture_gap_correlations.csv",
            package / "t10_survivor_texture_gap_strata.csv",
            package_figs / "fig_14_t10_survivor_texture_gap_scatter.png",
            package / "manifest.json",
        ],
    )

    main_corr = find_correlation(correlation_rows, "texture_deficit_score", "delta_plane_f1_als_minus_dim")
    print(f"survivor_n={len(building_rows)}")
    print(f"image_texture_n={sum(row['image_texture_sample_count'] > 0 for row in building_rows)}")
    print(f"texture_delta_f1_spearman_r={main_corr['spearman_r']}")
    print(f"texture_delta_f1_permutation_p={main_corr['p_value']}")
    print(f"observation={observation}")
    print(f"report={rel(report_md)}")


def load_helper_module(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load helper module from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def grid_density_cv(t7: Any, x: np.ndarray, y: np.ndarray, footprint: Any) -> float:
    min_x, min_y, max_x, max_y = footprint.bbox
    xs = np.arange(min_x + GRID_CELL_M * 0.5, max_x, GRID_CELL_M)
    ys = np.arange(min_y + GRID_CELL_M * 0.5, max_y, GRID_CELL_M)
    if xs.size == 0 or ys.size == 0:
        return math.nan
    grid_x, grid_y = np.meshgrid(xs, ys)
    inside = t7.points_in_polygon(grid_x.ravel(), grid_y.ravel(), footprint.ring)
    total = int(np.count_nonzero(inside))
    if total == 0:
        return math.nan
    counts: dict[tuple[int, int], int] = {}
    if x.size:
        ix = np.floor((x - min_x) / GRID_CELL_M).astype(np.int64)
        iy = np.floor((y - min_y) / GRID_CELL_M).astype(np.int64)
        for cell_x, cell_y in zip(ix, iy):
            key = (int(cell_x), int(cell_y))
            counts[key] = counts.get(key, 0) + 1
    grid_ix = np.floor((grid_x.ravel()[inside] - min_x) / GRID_CELL_M).astype(np.int64)
    grid_iy = np.floor((grid_y.ravel()[inside] - min_y) / GRID_CELL_M).astype(np.int64)
    values = np.array([counts.get((int(a), int(b)), 0) for a, b in zip(grid_ix, grid_iy)], dtype=np.float64)
    mean = float(np.mean(values))
    if mean <= 0.0:
        return math.nan
    return float(np.std(values) / mean)


def measure_survivor_image_texture(
    t7: Any,
    image_dir: Path,
    survivor_ids: list[str],
    footprints: dict[str, Any],
    surface_by_id: dict[str, Any],
    cameras: list[Any],
    camera_model: Any,
    scene_ref: dict[str, Any],
) -> list[ImageTextureMetric]:
    candidates: dict[str, list[dict[str, Any]]] = {bid: [] for bid in survivor_ids}
    for bid in survivor_ids:
        footprint = footprints[bid]
        surface = surface_by_id[bid]
        roof_z = surface.roof_z_p90 if np.isfinite(surface.roof_z_p90) else surface.roof_z_median
        if not np.isfinite(roof_z):
            continue
        normal = surface.normal if surface.normal is not None else np.array([0.0, 0.0, 1.0], dtype=np.float64)
        samples = t7.footprint_sample_points(footprint, roof_z)
        roof_ring = footprint_roof_ring(footprint, roof_z)
        centroid_xy = np.mean(footprint.ring[:-1], axis=0)
        centroid = np.array([centroid_xy[0], centroid_xy[1], roof_z], dtype=np.float64)
        for camera in cameras:
            projected_samples, in_front = t7.project_points(samples, camera, camera_model, scene_ref)
            in_frame = (
                in_front
                & (projected_samples[:, 0] >= 0.0)
                & (projected_samples[:, 0] < camera_model.width)
                & (projected_samples[:, 1] >= 0.0)
                & (projected_samples[:, 1] < camera_model.height)
            )
            fraction = float(np.count_nonzero(in_frame) / samples.shape[0])
            if fraction < MIN_IN_FRAME_FRACTION:
                continue
            incidence = incidence_angle(camera.center_base, centroid, normal)
            if not np.isfinite(incidence) or incidence > NEAR_NADIR_MAX_INCIDENT_DEG:
                continue
            projected_ring, ring_front = t7.project_points(roof_ring, camera, camera_model, scene_ref)
            if not np.all(ring_front) or not projection_overlaps_image(projected_ring, camera_model):
                continue
            candidates[bid].append(
                {
                    "building_id": bid,
                    "image_name": camera.name,
                    "incidence_deg": incidence,
                    "in_frame_fraction": fraction,
                    "projected_ring": projected_ring,
                }
            )

    selected_by_image: dict[str, list[dict[str, Any]]] = {}
    for bid, items in candidates.items():
        items.sort(key=lambda item: (item["incidence_deg"], -item["in_frame_fraction"]))
        chosen = items[:MAX_IMAGE_TEXTURE_VIEWS]
        for item in chosen:
            selected_by_image.setdefault(item["image_name"], []).append(item)

    metrics: list[ImageTextureMetric] = []
    for image_name, items in sorted(selected_by_image.items()):
        with Image.open(image_dir / image_name) as image:
            gray = np.asarray(image.convert("L"), dtype=np.float32) / 255.0
            width, height = image.size
            for item in items:
                metric = measure_projected_crop(gray, width, height, item)
                if metric is not None:
                    metrics.append(metric)
    return metrics


def footprint_roof_ring(footprint: Any, roof_z: float) -> np.ndarray:
    xy = footprint.ring[:-1]
    return np.column_stack([xy, np.full(xy.shape[0], roof_z, dtype=np.float64)])


def incidence_angle(camera_center: np.ndarray, target: np.ndarray, normal: np.ndarray) -> float:
    view_vec = camera_center - target
    norm = float(np.linalg.norm(view_vec))
    if norm <= 0.0:
        return math.nan
    unit = view_vec / norm
    cos_incidence = float(np.clip(np.dot(unit, normal), -1.0, 1.0))
    return math.degrees(math.acos(abs(cos_incidence)))


def projection_overlaps_image(projected_ring: np.ndarray, camera_model: Any) -> bool:
    if not np.all(np.isfinite(projected_ring)):
        return False
    min_u = float(np.min(projected_ring[:, 0]))
    max_u = float(np.max(projected_ring[:, 0]))
    min_v = float(np.min(projected_ring[:, 1]))
    max_v = float(np.max(projected_ring[:, 1]))
    return max_u >= 0.0 and min_u < camera_model.width and max_v >= 0.0 and min_v < camera_model.height


def measure_projected_crop(gray: np.ndarray, width: int, height: int, item: dict[str, Any]) -> ImageTextureMetric | None:
    ring = item["projected_ring"]
    min_u = max(0, int(math.floor(float(np.min(ring[:, 0])))) - 4)
    min_v = max(0, int(math.floor(float(np.min(ring[:, 1])))) - 4)
    max_u = min(width, int(math.ceil(float(np.max(ring[:, 0])))) + 5)
    max_v = min(height, int(math.ceil(float(np.max(ring[:, 1])))) + 5)
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
    return ImageTextureMetric(
        building_id=item["building_id"],
        image_name=item["image_name"],
        texture_gradient_mean=float(np.mean(gradient[mask])),
        gray_std=float(np.std(pixels)),
        brightness_median=float(np.median(pixels)),
        shadow_ratio=float(np.count_nonzero(pixels < 0.20) / mask_pixels),
        incidence_deg=float(item["incidence_deg"]),
        mask_pixel_count=mask_pixels,
    )


def summarize_image_texture(metrics: list[ImageTextureMetric]) -> dict[str, dict[str, float]]:
    grouped: dict[str, list[ImageTextureMetric]] = {}
    for metric in metrics:
        grouped.setdefault(metric.building_id, []).append(metric)
    output: dict[str, dict[str, float]] = {}
    for bid, items in grouped.items():
        output[bid] = {
            "image_texture_sample_count": float(len(items)),
            "image_texture_gradient_median": median([item.texture_gradient_mean for item in items]),
            "image_texture_gradient_p10": percentile([item.texture_gradient_mean for item in items], 10.0),
            "image_gray_std_median": median([item.gray_std for item in items]),
            "image_brightness_median": median([item.brightness_median for item in items]),
            "image_shadow_ratio_median": median([item.shadow_ratio for item in items]),
            "image_incidence_deg_median": median([item.incidence_deg for item in items]),
        }
    return output


def assert_image_inputs(image_dir: Path, cameras: list[Any]) -> None:
    missing = [camera.name for camera in cameras if not (image_dir / camera.name).exists()]
    if missing:
        raise FileNotFoundError(f"Missing {len(missing)} images under {image_dir}: {', '.join(missing[:5])}")


def build_building_rows(
    survivor_ids: list[str],
    quality_by_id: dict[str, dict[str, str]],
    dim_internal_by_id: dict[str, dict[str, str]],
    point_metrics: dict[str, dict[str, float]],
    image_by_id: dict[str, dict[str, float]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for bid in survivor_ids:
        quality = quality_by_id.get(bid)
        if quality is None:
            raise RuntimeError(f"Missing canonical quality metrics for survivor {bid}")
        internal = dim_internal_by_id.get(bid, {})
        point = point_metrics[bid]
        image = image_by_id.get(bid, {})
        als_f1 = to_float(quality["als_plane_f1"])
        dim_f1 = to_float(quality["dim_plane_f1"])
        row = {
            "building_id": bid,
            "als_plane_f1": als_f1,
            "dim_plane_f1": dim_f1,
            "delta_plane_f1_als_minus_dim": als_f1 - dim_f1 if np.isfinite(als_f1) and np.isfinite(dim_f1) else math.nan,
            "dim_internal_boundary_hausdorff_m": to_float(internal.get("internal_boundary_hausdorff_m", "")),
            "dim_internal_boundary_chamfer_m": to_float(internal.get("internal_boundary_chamfer_m", "")),
            "dim_height_nmad_m": to_float(quality.get("dim_height_nmad_m", "")),
            **point,
            "image_texture_sample_count": image.get("image_texture_sample_count", 0.0),
            "image_texture_gradient_median": image.get("image_texture_gradient_median", math.nan),
            "image_texture_gradient_p10": image.get("image_texture_gradient_p10", math.nan),
            "image_gray_std_median": image.get("image_gray_std_median", math.nan),
            "image_brightness_median": image.get("image_brightness_median", math.nan),
            "image_shadow_ratio_median": image.get("image_shadow_ratio_median", math.nan),
            "image_incidence_deg_median": image.get("image_incidence_deg_median", math.nan),
        }
        rows.append(row)
    return rows


def add_texture_deficit_scores(rows: list[dict[str, Any]]) -> None:
    specs = [
        ("dim_hole_ratio", 1.0),
        ("dim_density_cv", 1.0),
        ("dim_plane_rmse_m", 1.0),
        ("dim_density_pts_m2", -1.0),
        ("image_texture_gradient_median", -1.0),
    ]
    rank_maps: dict[str, dict[str, float]] = {}
    for key, direction in specs:
        values = [(row["building_id"], float(row.get(key, math.nan))) for row in rows]
        finite = [(bid, value) for bid, value in values if np.isfinite(value)]
        if not finite:
            continue
        arr = np.array([value for _bid, value in finite], dtype=np.float64)
        ranks = rankdata(arr)
        denom = max(len(arr) - 1, 1)
        scores = ranks / denom
        if direction < 0:
            scores = 1.0 - scores
        rank_maps[key] = {bid: float(score) for (bid, _value), score in zip(finite, scores)}
    for row in rows:
        parts = [rank_maps[key][row["building_id"]] for key in rank_maps if row["building_id"] in rank_maps[key]]
        row["texture_deficit_score"] = float(np.mean(parts)) if parts else math.nan


def build_correlation_rows(rows: list[dict[str, Any]]) -> list[dict[str, str]]:
    predictors = [
        ("texture_deficit_score", "higher means lower/patchier DIM or image texture"),
        ("dim_hole_ratio", "higher means more empty footprint grid cells"),
        ("dim_density_cv", "higher means more uneven local DIM point density"),
        ("dim_plane_rmse_m", "higher means rougher DIM roof plane fit"),
        ("dim_density_pts_m2", "higher means denser DIM building points"),
        ("image_texture_gradient_median", "higher means more image roof texture"),
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
                rho, p_value = spearman_permutation_p(x[mask], y[mask], rng)
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


def spearman_permutation_p(x: np.ndarray, y: np.ndarray, rng: np.random.Generator) -> tuple[float, float]:
    rx = rankdata(x)
    ry = rankdata(y)
    observed = pearson_corr(rx, ry)
    if not np.isfinite(observed):
        return math.nan, math.nan
    count = 0
    for _ in range(PERMUTATION_COUNT):
        permuted = rng.permutation(rx)
        if abs(pearson_corr(permuted, ry)) >= abs(observed) - 1e-15:
            count += 1
    p_value = (count + 1.0) / (PERMUTATION_COUNT + 1.0)
    return float(observed), float(p_value)


def rankdata(values: np.ndarray) -> np.ndarray:
    order = np.argsort(values, kind="mergesort")
    ranks = np.empty(values.shape[0], dtype=np.float64)
    sorted_values = values[order]
    i = 0
    while i < sorted_values.size:
        j = i + 1
        while j < sorted_values.size and sorted_values[j] == sorted_values[i]:
            j += 1
        rank = (i + j - 1) / 2.0
        ranks[order[i:j]] = rank
        i = j
    return ranks


def pearson_corr(x: np.ndarray, y: np.ndarray) -> float:
    x0 = x - float(np.mean(x))
    y0 = y - float(np.mean(y))
    denom = float(np.sqrt(np.sum(x0 * x0) * np.sum(y0 * y0)))
    if denom <= 0.0:
        return math.nan
    return float(np.sum(x0 * y0) / denom)


def build_strata_rows(rows: list[dict[str, Any]]) -> list[dict[str, str]]:
    scores = np.array([row["texture_deficit_score"] for row in rows if np.isfinite(row["texture_deficit_score"])], dtype=np.float64)
    if scores.size == 0:
        return []
    cutoff = float(np.median(scores))
    low_texture = [row for row in rows if np.isfinite(row["texture_deficit_score"]) and row["texture_deficit_score"] >= cutoff]
    high_texture = [row for row in rows if np.isfinite(row["texture_deficit_score"]) and row["texture_deficit_score"] < cutoff]
    return [
        format_stratum("low_texture_high_deficit", low_texture, cutoff),
        format_stratum("high_texture_low_deficit", high_texture, cutoff),
    ]


def format_stratum(label: str, rows: list[dict[str, Any]], cutoff: float) -> dict[str, str]:
    return {
        "stratum": label,
        "n": str(len(rows)),
        "texture_deficit_cutoff": fmt(cutoff, 4),
        "texture_deficit_median": fmt(median([row["texture_deficit_score"] for row in rows]), 4),
        "delta_plane_f1_median": fmt(median([row["delta_plane_f1_als_minus_dim"] for row in rows]), 4),
        "delta_plane_f1_p25": fmt(percentile([row["delta_plane_f1_als_minus_dim"] for row in rows], 25.0), 4),
        "delta_plane_f1_p75": fmt(percentile([row["delta_plane_f1_als_minus_dim"] for row in rows], 75.0), 4),
        "dim_plane_f1_median": fmt(median([row["dim_plane_f1"] for row in rows]), 4),
        "dim_internal_hausdorff_median_m": fmt(median([row["dim_internal_boundary_hausdorff_m"] for row in rows]), 4),
    }


def build_observation(correlation_rows: list[dict[str, str]], strata_rows: list[dict[str, str]]) -> str:
    main = find_correlation(correlation_rows, "texture_deficit_score", "delta_plane_f1_als_minus_dim")
    rho = to_float(main["spearman_r"])
    p_value = to_float(main["p_value"])
    low = next((row for row in strata_rows if row["stratum"] == "low_texture_high_deficit"), None)
    high = next((row for row in strata_rows if row["stratum"] == "high_texture_low_deficit"), None)
    low_gap = to_float(low["delta_plane_f1_median"]) if low else math.nan
    high_gap = to_float(high["delta_plane_f1_median"]) if high else math.nan
    direction = "통합 메커니즘 지지 관찰" if np.isfinite(rho) and rho >= 0.30 and p_value <= 0.10 else "통합 메커니즘 불지지/약함 관찰"
    return (
        f"텍스처 결손 점수 vs ALS-DIM ΔF1 Spearman r={rho:.3f}, p={p_value:.4f}; "
        f"저텍스처 strata ΔF1 중앙값 {low_gap:.3f}, 고텍스처 {high_gap:.3f} -> {direction}(판정 아님, E5 확증 필요)."
    )


def find_correlation(correlation_rows: list[dict[str, str]], predictor: str, target: str) -> dict[str, str]:
    for row in correlation_rows:
        if row["predictor"] == predictor and row["target"] == target:
            return row
    raise KeyError((predictor, target))


def write_metrics_json(
    path: Path,
    run_id: str,
    building_rows: list[dict[str, Any]],
    correlation_rows: list[dict[str, str]],
    strata_rows: list[dict[str, str]],
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
        "correlations": correlation_rows,
        "strata": strata_rows,
        "rows": sanitize_json(building_rows),
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def render_scatter(out_path: Path, rows: list[dict[str, Any]], correlation_rows: list[dict[str, str]]) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    x = np.array([row["texture_deficit_score"] for row in rows], dtype=np.float64)
    y = np.array([row["delta_plane_f1_als_minus_dim"] for row in rows], dtype=np.float64)
    mask = np.isfinite(x) & np.isfinite(y)
    cutoff = float(np.median(x[mask]))
    colors = np.where(x[mask] >= cutoff, "#d62728", "#2f6fbb")
    main = find_correlation(correlation_rows, "texture_deficit_score", "delta_plane_f1_als_minus_dim")
    fig, ax = plt.subplots(figsize=(7.4, 5.2), constrained_layout=True)
    ax.scatter(x[mask], y[mask], c=colors, s=42, alpha=0.85, edgecolors="#222222", linewidths=0.3)
    if np.count_nonzero(mask) >= 2:
        coef = np.polyfit(x[mask], y[mask], deg=1)
        xs = np.linspace(float(np.min(x[mask])), float(np.max(x[mask])), 100)
        ax.plot(xs, coef[0] * xs + coef[1], color="#222222", linewidth=1.1)
    ax.axvline(cutoff, color="#777777", linestyle="--", linewidth=0.9)
    ax.axhline(0.0, color="#999999", linestyle=":", linewidth=0.8)
    ax.set_xlabel("Texture deficit score (higher = lower/patchier texture)")
    ax.set_ylabel("Plane F1 gap (ALS - DIM)")
    ax.set_title(f"T10 survivor texture vs plane F1 gap\nSpearman r={main['spearman_r']}, p={main['p_value']}, n={main['n']}")
    ax.grid(True, linewidth=0.3, alpha=0.35)
    fig.savefig(out_path, dpi=220)
    plt.close(fig)


def write_report(
    out_path: Path,
    run_id: str,
    run_dir: Path,
    metrics_csv: Path,
    correlations_csv: Path,
    strata_csv: Path,
    metrics_json: Path,
    scatter_fig: Path,
    correlation_rows: list[dict[str, str]],
    strata_rows: list[dict[str, str]],
    observation: str,
) -> None:
    main_rows = [
        row
        for row in correlation_rows
        if row["predictor"]
        in {"texture_deficit_score", "dim_hole_ratio", "dim_density_cv", "dim_plane_rmse_m", "image_texture_gradient_median"}
        and row["target"] in {"dim_plane_f1", "delta_plane_f1_als_minus_dim", "dim_internal_boundary_hausdorff_m"}
    ]
    out_path.write_text(
        "\n".join(
            [
                "# W3 Survivor Texture Gap (T10)",
                "",
                f"- Run ID: {run_id}",
                f"- Run directory: {rel(run_dir)}",
                f"- Canonical input: `{CANONICAL_RUN}`",
                f"- Building metrics CSV: `{rel(metrics_csv)}`",
                f"- Correlation CSV: `{rel(correlations_csv)}`",
                f"- Strata CSV: `{rel(strata_csv)}`",
                f"- Metrics JSON: `{rel(metrics_json)}`",
                "- Inputs: T7 survivor 71 IDs, canonical W3 paired quality metrics, DIM LAZ, T5 footprint GPKG, and original UAV images.",
                "- CRS: EPSG:25832 numeric UTM32 for footprints, DIM LAZ, and camera centers after T2 scene-reference transform.",
                "- Scope: correlation/stratified observation only. P0 acceptance/rejection remains outside this T10 output.",
                "",
                "## Observation",
                "",
                f"- {observation}",
                "",
                "## Correlations",
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
                        "texture_deficit_cutoff",
                        "texture_deficit_median",
                        "delta_plane_f1_median",
                        "delta_plane_f1_p25",
                        "delta_plane_f1_p75",
                        "dim_plane_f1_median",
                        "dim_internal_hausdorff_median_m",
                    ],
                ),
                "",
                "## Figure",
                "",
                f"![texture vs plane F1 gap]({rel(scatter_fig).replace('docs/', '')})",
                "",
                "## Notes",
                "",
                "- Texture deficit score averages rank-normalized DIM hole ratio, DIM local density CV, DIM plane RMSE, inverse DIM density, and inverse near-nadir image gradient.",
                f"- Spearman p-values use a deterministic {PERMUTATION_COUNT}-permutation two-sided test with seed {PERMUTATION_SEED}.",
                "- Internal Hausdorff correlations use only survivor buildings with measurable DIM internal boundaries.",
                "- This table tests whether survivor degradation follows the same texture mechanism as the T9 failure extreme; it is not a method-level conclusion.",
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
    scatter_fig: Path,
) -> None:
    package.mkdir(parents=True, exist_ok=True)
    package_figs.mkdir(parents=True, exist_ok=True)
    targets = [
        (report_md, package / "W3_survivor_texture_gap.md"),
        (metrics_csv, package / "t10_survivor_texture_gap_building_metrics.csv"),
        (correlations_csv, package / "t10_survivor_texture_gap_correlations.csv"),
        (strata_csv, package / "t10_survivor_texture_gap_strata.csv"),
        (scatter_fig, package_figs / "fig_14_t10_survivor_texture_gap_scatter.png"),
    ]
    for src, dst in targets:
        shutil.copy2(src, dst)
    manifest_path = package / "manifest.json"
    if manifest_path.exists():
        manifest = read_json(manifest_path)
    else:
        manifest = {"package": "G1_package", "canonical_run": CANONICAL_RUN, "files": [], "figure_count": 0}
    files = set(manifest.get("files", []))
    for _, dst in targets:
        files.add(dst.relative_to(package).as_posix())
    manifest["files"] = sorted(files)
    manifest["figure_count"] = sum(1 for item in manifest["files"] if item.startswith("figs/") and item.endswith(".png"))
    manifest["t10_survivor_texture_gap"] = {
        "report": "W3_survivor_texture_gap.md",
        "figure": "figs/fig_14_t10_survivor_texture_gap_scatter.png",
        "tables": [
            "t10_survivor_texture_gap_building_metrics.csv",
            "t10_survivor_texture_gap_correlations.csv",
            "t10_survivor_texture_gap_strata.csv",
        ],
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def format_building_row(row: dict[str, Any]) -> dict[str, str]:
    fields = [
        "building_id",
        "als_plane_f1",
        "dim_plane_f1",
        "delta_plane_f1_als_minus_dim",
        "dim_internal_boundary_hausdorff_m",
        "dim_internal_boundary_chamfer_m",
        "dim_height_nmad_m",
        "dim_point_count",
        "dim_density_pts_m2",
        "dim_hole_ratio",
        "dim_density_cv",
        "dim_plane_rmse_m",
        "image_texture_sample_count",
        "image_texture_gradient_median",
        "image_texture_gradient_p10",
        "image_gray_std_median",
        "image_brightness_median",
        "image_shadow_ratio_median",
        "image_incidence_deg_median",
        "texture_deficit_score",
    ]
    output: dict[str, str] = {}
    for field in fields:
        value = row.get(field, "")
        if field == "building_id":
            output[field] = str(value)
        elif field in {"dim_point_count", "image_texture_sample_count"}:
            output[field] = str(int(value)) if np.isfinite(float(value)) else "n/a"
        else:
            output[field] = fmt(float(value), 5 if "texture" in field or "cv" in field or "rmse" in field else 4)
    return output


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
    issues = repo / "docs/issues.md"
    with issues.open("a", encoding="utf-8") as fh:
        fh.write(f"\n## {TASK_ID} Survivor Texture Gap\n\n")
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
                "dim_pointcloud: data/work/w2/dim_v1_classified_z_minus0p174.laz",
                "images: " + IMAGE_DIR,
                "footprints: " + FOOTPRINT_GPKG,
                "crs: EPSG:25832 numeric UTM32 coordinates",
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
        "# T10 Survivor Texture Gap Tool Versions",
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
    text = path.as_posix()
    return text.replace("/workspace/", "")


def main() -> None:
    if os.environ.get("P0_INSIDE_CONTAINER") == "1":
        compute_entrypoint()
    else:
        host_entrypoint()


if __name__ == "__main__":
    main()
