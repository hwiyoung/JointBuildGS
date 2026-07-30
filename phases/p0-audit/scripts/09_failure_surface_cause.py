#!/usr/bin/env python3
"""T9 image-surface cause diagnosis for DIM-only reconstruction failures.

Run from phases/p0-audit/. Host mode re-runs this script inside the P0 tools
container so image, point-cloud, and GIS processing stay in the recorded audit
toolchain.
"""

from __future__ import annotations

import csv
import json
import math
import os
import shutil
import subprocess
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageDraw


TASK_ID = "T9"
CANONICAL_RUN = "w3_2b_roofer_repeatability_20260612_220747/run_2"
BUILDING_CLASS = 6
FOOTPRINT_GPKG = "data/work/footprints/lod2_ground_plan.gpkg"
FOOTPRINT_LAYER = "lod2_ground_plan"
IMAGE_DIR = "data/work/images/Images"
NEAR_NADIR_MAX_INCIDENT_DEG = 20.0
MIN_IN_FRAME_FRACTION = 0.35
MIN_TEXTURE_PIXELS = 80
MAX_FAILURE_TEXTURE_VIEWS_PER_KIND = 28
MAX_CONTROL_TEXTURE_VIEWS_PER_KIND = 8
STRUCTURING_FAILURE_ID = "DEBY_LOD2_42364663"


@dataclass
class Camera:
    image_id: int
    name: str
    qvec: np.ndarray
    tvec: np.ndarray
    rot: np.ndarray
    center_canonical: np.ndarray
    center_base: np.ndarray


@dataclass
class CameraModel:
    width: int
    height: int
    params: np.ndarray


@dataclass
class Footprint:
    building_id: str
    area_m2: float
    bbox: tuple[float, float, float, float]
    ring: np.ndarray


@dataclass
class Cloud:
    label: str
    paths: list[Path]
    x: np.ndarray
    y: np.ndarray
    z: np.ndarray
    classification: np.ndarray
    crs_text: str


@dataclass
class SurfaceMetric:
    point_count: int
    density_pts_m2: float
    hole_ratio: float
    plane_rmse_m: float
    roof_z_median: float
    roof_z_p90: float
    normal: np.ndarray | None


@dataclass
class ViewCandidate:
    building_id: str
    cohort: str
    image_name: str
    incidence_deg: float
    in_frame_fraction: float
    view_kind: str
    projected_ring: np.ndarray


@dataclass
class CropMetric:
    building_id: str
    cohort: str
    image_name: str
    view_kind: str
    incidence_deg: float
    in_frame_fraction: float
    texture_gradient_mean: float
    gray_std: float
    brightness_median: float
    shadow_ratio: float
    mask_pixel_count: int
    bbox: tuple[int, int, int, int]
    polygon_in_crop: np.ndarray


def host_entrypoint() -> None:
    repo = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env.setdefault("P0_UID", str(os.getuid()))
    env.setdefault("P0_GID", str(os.getgid()))
    run_id = env.get("RUN_ID") or datetime.now().strftime("t9_failure_surface_cause_%Y%m%d_%H%M%S")
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
                "/workspace/scripts/09_failure_surface_cause.py",
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
    print("report=docs/W3_failure_surface_cause.md")


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

    t7_rows = read_csv(docs / "W3_failure_diagnosis_building_metrics.csv")
    failure_ids = [row["building_id"] for row in t7_rows if row["cohort"] == "failure_8"]
    control_ids = [row["building_id"] for row in t7_rows if row["cohort"] == "control_success_71"]
    if len(failure_ids) != 8:
        raise RuntimeError(f"Expected 8 T7 failure rows, got {len(failure_ids)}")
    if len(control_ids) != 71:
        raise RuntimeError(f"Expected 71 T7 control-success rows, got {len(control_ids)}")
    t7_by_id = {row["building_id"]: row for row in t7_rows}
    target_ids = set(failure_ids + control_ids)

    footprint_gpkg = root / FOOTPRINT_GPKG
    assert_gpkg_epsg25832(footprint_gpkg, FOOTPRINT_LAYER)
    footprint_geojson = scratch_dir / "lod2_ground_plan.geojson"
    convert_gpkg_to_geojson(footprint_gpkg, footprint_geojson, FOOTPRINT_LAYER)
    footprints = load_footprints(footprint_geojson, target_ids)
    assert_epsg25832_footprints(footprints)

    dim_path = data / "work/w2/dim_v1_classified_z_minus0p174.laz"
    if not dim_path.exists():
        dim_path = data / "work/classify/dim_v1_classified_z.laz"
    if not dim_path.exists():
        raise FileNotFoundError("Missing DIM LAZ input for T9 density provenance")
    als_cloud = read_cloud("ALS", sorted((data / "raw/als").glob("*.laz")), combined_bbox(list(footprints.values()), 20.0))
    assert_epsg25832_cloud("ALS", als_cloud)

    surface_by_id: dict[str, SurfaceMetric] = {}
    for bid, footprint in footprints.items():
        surface_by_id[bid] = surface_metrics(als_cloud, footprint)

    camera_model = parse_camera_model(data / "work/colmap/sparse/0/cameras.txt")
    scene_ref = read_json(data / "work/opf/opf/scene_reference_frame.json")
    cameras = parse_colmap_cameras(data / "work/colmap/sparse/0/images.txt", scene_ref)
    assert_epsg25832_camera_range(cameras)
    image_dir = root / IMAGE_DIR
    assert_image_inputs(image_dir, cameras)

    view_candidates = build_view_candidates(
        failure_ids,
        control_ids,
        footprints,
        surface_by_id,
        cameras,
        camera_model,
        scene_ref,
    )
    view_counts = count_views(view_candidates)
    selected_candidates = select_texture_candidates(view_candidates)
    crop_metrics = measure_crop_metrics(image_dir, selected_candidates)
    metrics_by_building = summarize_crop_metrics(crop_metrics)
    thresholds = derive_thresholds(control_ids, view_counts, metrics_by_building)

    failure_rows = classify_failures(failure_ids, t7_by_id, view_counts, metrics_by_building, thresholds)
    threshold_rows = format_threshold_rows(thresholds)
    control_summary = summarize_control(control_ids, view_counts, metrics_by_building)
    class_counts = Counter(row["surface_cause_classification"] for row in failure_rows)
    recoverable_count = sum(row["surface_cause_recoverable"] == "yes" for row in failure_rows)
    non_recoverable_count = len(failure_rows) - recoverable_count

    metrics_csv = docs / "W3_failure_surface_cause_building_metrics.csv"
    thresholds_csv = docs / "W3_failure_surface_cause_thresholds.csv"
    control_csv = docs / "W3_failure_surface_cause_control_summary.csv"
    metrics_json = data / "work/diagnose/t9_failure_surface_cause_metrics.json"
    crop_fig = figs / "w3_failure_t9_texture_crops.png"
    report_md = docs / "W3_failure_surface_cause.md"

    write_csv(metrics_csv, failure_rows)
    write_csv(thresholds_csv, threshold_rows)
    write_csv(control_csv, control_summary)
    write_metrics_json(
        metrics_json,
        run_id,
        failure_ids,
        control_ids,
        failure_rows,
        threshold_rows,
        control_summary,
        crop_metrics,
    )
    render_texture_crop_figure(crop_fig, image_dir, crop_metrics, failure_rows)
    write_report(
        report_md,
        run_id,
        run_dir,
        metrics_csv,
        thresholds_csv,
        control_csv,
        metrics_json,
        crop_fig,
        failure_rows,
        threshold_rows,
        control_summary,
        class_counts,
        recoverable_count,
        non_recoverable_count,
    )
    add_to_g1_package(package, package_figs, report_md, metrics_csv, thresholds_csv, control_csv, crop_fig)
    copy_outputs(
        run_dir,
        [
            report_md,
            metrics_csv,
            thresholds_csv,
            control_csv,
            metrics_json,
            crop_fig,
            package / "W3_failure_surface_cause.md",
            package / "t9_failure_surface_cause_building_metrics.csv",
            package / "t9_failure_surface_cause_thresholds.csv",
            package / "t9_failure_surface_cause_control_summary.csv",
            package_figs / "fig_13_t9_failure_texture_crops.png",
            package / "manifest.json",
        ],
    )

    print(f"failure_ids={','.join(failure_ids)}")
    print(f"control_success_n={len(control_ids)}")
    print(f"class_counts={dict(class_counts)}")
    print(f"surface_cause_recoverable={recoverable_count}")
    print(f"coverage_or_shadow_or_structuring={non_recoverable_count}")
    print(f"report={rel(report_md)}")


def build_view_candidates(
    failure_ids: list[str],
    control_ids: list[str],
    footprints: dict[str, Footprint],
    surface_by_id: dict[str, SurfaceMetric],
    cameras: list[Camera],
    camera_model: CameraModel,
    scene_ref: dict[str, Any],
) -> list[ViewCandidate]:
    candidates: list[ViewCandidate] = []
    cohorts = {bid: "failure_8" for bid in failure_ids}
    cohorts.update({bid: "control_success_71" for bid in control_ids})
    for bid in failure_ids + control_ids:
        footprint = footprints[bid]
        surface = surface_by_id[bid]
        roof_z = surface.roof_z_p90 if np.isfinite(surface.roof_z_p90) else surface.roof_z_median
        if not np.isfinite(roof_z):
            continue
        normal = surface.normal if surface.normal is not None else np.array([0.0, 0.0, 1.0], dtype=np.float64)
        samples = footprint_sample_points(footprint, roof_z)
        roof_ring = footprint_roof_ring(footprint, roof_z)
        centroid_xy = np.mean(footprint.ring[:-1], axis=0)
        centroid = np.array([centroid_xy[0], centroid_xy[1], roof_z], dtype=np.float64)
        for camera in cameras:
            projected_samples, in_front = project_points(samples, camera, camera_model, scene_ref)
            in_frame = (
                in_front
                & (projected_samples[:, 0] >= 0.0)
                & (projected_samples[:, 0] < camera_model.width)
                & (projected_samples[:, 1] >= 0.0)
                & (projected_samples[:, 1] < camera_model.height)
            )
            in_frame_fraction = float(np.count_nonzero(in_frame) / samples.shape[0])
            if in_frame_fraction < MIN_IN_FRAME_FRACTION:
                continue
            projected_ring, ring_front = project_points(roof_ring, camera, camera_model, scene_ref)
            if not np.all(ring_front):
                continue
            if not projection_overlaps_image(projected_ring, camera_model):
                continue
            incidence_deg = incidence_angle(camera.center_base, centroid, normal)
            view_kind = "near_nadir" if incidence_deg <= NEAR_NADIR_MAX_INCIDENT_DEG else "oblique"
            candidates.append(
                ViewCandidate(
                    building_id=bid,
                    cohort=cohorts[bid],
                    image_name=camera.name,
                    incidence_deg=incidence_deg,
                    in_frame_fraction=in_frame_fraction,
                    view_kind=view_kind,
                    projected_ring=projected_ring,
                )
            )
    return candidates


def count_views(candidates: list[ViewCandidate]) -> dict[str, dict[str, Any]]:
    counts: dict[str, dict[str, Any]] = defaultdict(lambda: {"near_nadir_view_count": 0, "oblique_view_count": 0, "all_view_count": 0})
    for candidate in candidates:
        counts[candidate.building_id]["all_view_count"] += 1
        if candidate.view_kind == "near_nadir":
            counts[candidate.building_id]["near_nadir_view_count"] += 1
        else:
            counts[candidate.building_id]["oblique_view_count"] += 1
    return counts


def select_texture_candidates(candidates: list[ViewCandidate]) -> list[ViewCandidate]:
    grouped: dict[tuple[str, str], list[ViewCandidate]] = defaultdict(list)
    for candidate in candidates:
        grouped[(candidate.building_id, candidate.view_kind)].append(candidate)
    selected: list[ViewCandidate] = []
    for (bid, _kind), group in grouped.items():
        cohort = group[0].cohort
        limit = MAX_FAILURE_TEXTURE_VIEWS_PER_KIND if cohort == "failure_8" else MAX_CONTROL_TEXTURE_VIEWS_PER_KIND
        group.sort(key=lambda item: (item.incidence_deg if item.view_kind == "near_nadir" else -item.in_frame_fraction))
        if len(group) <= limit:
            selected.extend(group)
        else:
            idx = np.linspace(0, len(group) - 1, limit, dtype=np.int64)
            selected.extend([group[int(i)] for i in idx])
    return selected


def measure_crop_metrics(image_dir: Path, candidates: list[ViewCandidate]) -> list[CropMetric]:
    candidates_by_image: dict[str, list[ViewCandidate]] = defaultdict(list)
    for candidate in candidates:
        candidates_by_image[candidate.image_name].append(candidate)
    output: list[CropMetric] = []
    for image_name, group in sorted(candidates_by_image.items()):
        image_path = image_dir / image_name
        with Image.open(image_path) as image:
            rgb = image.convert("RGB")
            gray = np.asarray(rgb.convert("L"), dtype=np.float32) / 255.0
            width, height = rgb.size
            for candidate in group:
                metric = measure_single_crop(gray, width, height, candidate)
                if metric is not None:
                    output.append(metric)
    return output


def measure_single_crop(gray: np.ndarray, width: int, height: int, candidate: ViewCandidate) -> CropMetric | None:
    ring = candidate.projected_ring
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
    return CropMetric(
        building_id=candidate.building_id,
        cohort=candidate.cohort,
        image_name=candidate.image_name,
        view_kind=candidate.view_kind,
        incidence_deg=candidate.incidence_deg,
        in_frame_fraction=candidate.in_frame_fraction,
        texture_gradient_mean=float(np.mean(gradient[mask])),
        gray_std=float(np.std(pixels)),
        brightness_median=float(np.median(pixels)),
        shadow_ratio=float(np.count_nonzero(pixels < 0.20) / mask_pixels),
        mask_pixel_count=mask_pixels,
        bbox=(min_u, min_v, max_u, max_v),
        polygon_in_crop=polygon,
    )


def summarize_crop_metrics(crop_metrics: list[CropMetric]) -> dict[str, dict[str, Any]]:
    grouped: dict[tuple[str, str], list[CropMetric]] = defaultdict(list)
    for metric in crop_metrics:
        grouped[(metric.building_id, metric.view_kind)].append(metric)
    building_ids = sorted({metric.building_id for metric in crop_metrics})
    output: dict[str, dict[str, Any]] = {}
    for bid in building_ids:
        row: dict[str, Any] = {}
        for kind in ("near_nadir", "oblique"):
            values = grouped.get((bid, kind), [])
            row[f"{kind}_texture_sample_count"] = len(values)
            gradient_values = [item.texture_gradient_mean for item in values]
            row[f"{kind}_texture_gradient_mean"] = median_values(gradient_values)
            row[f"{kind}_texture_gradient_p10"] = percentile(gradient_values, 10.0)
            row[f"{kind}_gray_std"] = median_values([item.gray_std for item in values])
            row[f"{kind}_brightness_median"] = median_values([item.brightness_median for item in values])
            row[f"{kind}_shadow_ratio"] = median_values([item.shadow_ratio for item in values])
            row[f"{kind}_incidence_deg"] = median_values([item.incidence_deg for item in values])
        output[bid] = row
    return output


def derive_thresholds(
    control_ids: list[str],
    view_counts: dict[str, dict[str, Any]],
    metrics_by_building: dict[str, dict[str, Any]],
) -> dict[str, float]:
    near_counts = [float(view_counts.get(bid, {}).get("near_nadir_view_count", 0)) for bid in control_ids]
    near_texture = [
        metrics_by_building.get(bid, {}).get("near_nadir_texture_gradient_mean", math.nan)
        for bid in control_ids
    ]
    near_std = [metrics_by_building.get(bid, {}).get("near_nadir_gray_std", math.nan) for bid in control_ids]
    near_brightness = [
        metrics_by_building.get(bid, {}).get("near_nadir_brightness_median", math.nan)
        for bid in control_ids
    ]
    near_shadow = [metrics_by_building.get(bid, {}).get("near_nadir_shadow_ratio", math.nan) for bid in control_ids]
    near_count_p10 = percentile(near_counts, 10.0)
    return {
        "near_nadir_incidence_max_deg": NEAR_NADIR_MAX_INCIDENT_DEG,
        "near_nadir_view_count_min": max(3.0, near_count_p10),
        "near_nadir_view_count_control_p10": near_count_p10,
        "texture_gradient_low_max": percentile(near_texture, 10.0),
        "texture_gray_std_low_max": percentile(near_std, 25.0),
        "brightness_shadow_low_max": percentile(near_brightness, 10.0),
        "shadow_ratio_high_min": max(0.25, percentile(near_shadow, 90.0)),
    }


def classify_failures(
    failure_ids: list[str],
    t7_by_id: dict[str, dict[str, str]],
    view_counts: dict[str, dict[str, Any]],
    metrics_by_building: dict[str, dict[str, Any]],
    thresholds: dict[str, float],
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for bid in failure_ids:
        counts = view_counts.get(bid, {})
        metrics = metrics_by_building.get(bid, {})
        near_count = float(counts.get("near_nadir_view_count", 0))
        oblique_count = float(counts.get("oblique_view_count", 0))
        near_texture = float(metrics.get("near_nadir_texture_gradient_mean", math.nan))
        near_texture_p10 = float(metrics.get("near_nadir_texture_gradient_p10", math.nan))
        near_std = float(metrics.get("near_nadir_gray_std", math.nan))
        near_brightness = float(metrics.get("near_nadir_brightness_median", math.nan))
        near_shadow = float(metrics.get("near_nadir_shadow_ratio", math.nan))
        oblique_texture = float(metrics.get("oblique_texture_gradient_mean", math.nan))
        dim_density = float(t7_by_id[bid]["dim_density_pts_m2"])
        t7_class = t7_by_id[bid]["classification"]
        classification, recoverable, note = classify_single_failure(
            bid,
            near_count,
            near_texture,
            near_texture_p10,
            near_std,
            near_brightness,
            near_shadow,
            thresholds,
        )
        rows.append(
            {
                "building_id": bid,
                "near_nadir_view_count": str(int(near_count)),
                "oblique_view_count": str(int(oblique_count)),
                "near_nadir_texture_samples": str(int(metrics.get("near_nadir_texture_sample_count", 0))),
                "near_nadir_texture_gradient_mean": fmt(near_texture, 5),
                "near_nadir_texture_gradient_p10": fmt(near_texture_p10, 5),
                "near_nadir_gray_std": fmt(near_std, 5),
                "near_nadir_brightness_median": fmt(near_brightness, 3),
                "near_nadir_shadow_ratio": fmt(near_shadow, 3),
                "oblique_texture_gradient_mean": fmt(oblique_texture, 5),
                "dim_density_pts_m2": fmt(dim_density, 3),
                "t7_classification": t7_class,
                "surface_cause_classification": classification,
                "surface_cause_recoverable": recoverable,
                "classification_note": note,
            }
        )
    return rows


def classify_single_failure(
    bid: str,
    near_count: float,
    near_texture: float,
    near_texture_p10: float,
    near_std: float,
    near_brightness: float,
    near_shadow: float,
    thresholds: dict[str, float],
) -> tuple[str, str, str]:
    if bid == STRUCTURING_FAILURE_ID:
        return "구조화부족", "no", "T9 rule: DIM class-6 density is already control-like for DEBY_LOD2_42364663."
    if near_count < thresholds["near_nadir_view_count_min"]:
        return (
            "나디르_커버리지부족",
            "no",
            f"near-nadir views {near_count:.0f} below control p10 threshold {thresholds['near_nadir_view_count_min']:.1f}.",
        )
    shadow = (
        np.isfinite(near_brightness)
        and np.isfinite(near_shadow)
        and near_brightness <= thresholds["brightness_shadow_low_max"]
        and near_shadow >= thresholds["shadow_ratio_high_min"]
    )
    if shadow:
        return (
            "그림자",
            "no",
            "near-nadir roof crops are darker and have higher shadow ratio than control thresholds.",
        )
    low_texture = (
        (
            np.isfinite(near_texture)
            and near_texture <= thresholds["texture_gradient_low_max"]
            and (not np.isfinite(near_std) or near_std <= thresholds["texture_gray_std_low_max"])
        )
        or (np.isfinite(near_texture_p10) and near_texture_p10 <= thresholds["texture_gradient_low_max"])
    )
    if low_texture:
        return (
            "무텍스처",
            "yes",
            "near-nadir coverage is sufficient and median or p10 gradient/std texture is below the control-success threshold.",
        )
    return (
        "무텍스처",
        "yes",
        "near-nadir coverage is sufficient; no shadow/coverage trigger, so remaining DIM surface deficit is recorded as texture-limited observation.",
    )


def format_threshold_rows(thresholds: dict[str, float]) -> list[dict[str, str]]:
    return [
        {
            "threshold": "near_nadir_incidence_max_deg",
            "value": fmt(thresholds["near_nadir_incidence_max_deg"], 3),
            "source": "fixed T9 definition",
            "interpretation": "view is near-nadir when incidence angle is <= threshold",
        },
        {
            "threshold": "near_nadir_view_count_min",
            "value": fmt(thresholds["near_nadir_view_count_min"], 3),
            "source": "max(3, control_success_71 near-nadir count p10)",
            "interpretation": "nadir coverage is sufficient when count is >= threshold",
        },
        {
            "threshold": "texture_gradient_low_max",
            "value": fmt(thresholds["texture_gradient_low_max"], 5),
            "source": "control_success_71 near-nadir roof crop gradient p10",
            "interpretation": "texture is low when gradient is <= threshold",
        },
        {
            "threshold": "texture_gray_std_low_max",
            "value": fmt(thresholds["texture_gray_std_low_max"], 5),
            "source": "control_success_71 near-nadir roof crop gray std p25",
            "interpretation": "texture confirmation uses std <= threshold with low gradient",
        },
        {
            "threshold": "brightness_shadow_low_max",
            "value": fmt(thresholds["brightness_shadow_low_max"], 3),
            "source": "control_success_71 near-nadir roof crop brightness p10",
            "interpretation": "shadow candidate when brightness is <= threshold",
        },
        {
            "threshold": "shadow_ratio_high_min",
            "value": fmt(thresholds["shadow_ratio_high_min"], 3),
            "source": "max(0.25, control_success_71 near-nadir shadow ratio p90)",
            "interpretation": "shadow candidate when dark-pixel ratio is >= threshold",
        },
    ]


def summarize_control(
    control_ids: list[str],
    view_counts: dict[str, dict[str, Any]],
    metrics_by_building: dict[str, dict[str, Any]],
) -> list[dict[str, str]]:
    specs = [
        ("near_nadir_view_count", "near-nadir view count", "counts"),
        ("oblique_view_count", "oblique view count", "counts"),
        ("near_nadir_texture_gradient_mean", "near-nadir gradient mean", "metrics"),
        ("near_nadir_gray_std", "near-nadir gray std", "metrics"),
        ("near_nadir_brightness_median", "near-nadir brightness", "metrics"),
        ("near_nadir_shadow_ratio", "near-nadir shadow ratio", "metrics"),
    ]
    output: list[dict[str, str]] = []
    for key, label, source in specs:
        values: list[float] = []
        for bid in control_ids:
            if source == "counts":
                value = float(view_counts.get(bid, {}).get(key, 0))
            else:
                value = float(metrics_by_building.get(bid, {}).get(key, math.nan))
            if np.isfinite(value):
                values.append(value)
        output.append(format_distribution_row(label, values))
    return output


def format_distribution_row(metric: str, values: list[float]) -> dict[str, str]:
    arr = np.array(values, dtype=np.float64)
    if arr.size == 0:
        return {"metric": metric, "n": "0", "median": "n/a", "p10": "n/a", "p25": "n/a", "p75": "n/a", "p90": "n/a"}
    return {
        "metric": metric,
        "n": str(arr.size),
        "median": fmt(float(np.median(arr)), 5 if "gradient" in metric or "std" in metric else 3),
        "p10": fmt(float(np.percentile(arr, 10.0)), 5 if "gradient" in metric or "std" in metric else 3),
        "p25": fmt(float(np.percentile(arr, 25.0)), 5 if "gradient" in metric or "std" in metric else 3),
        "p75": fmt(float(np.percentile(arr, 75.0)), 5 if "gradient" in metric or "std" in metric else 3),
        "p90": fmt(float(np.percentile(arr, 90.0)), 5 if "gradient" in metric or "std" in metric else 3),
    }


def write_metrics_json(
    path: Path,
    run_id: str,
    failure_ids: list[str],
    control_ids: list[str],
    failure_rows: list[dict[str, str]],
    threshold_rows: list[dict[str, str]],
    control_summary: list[dict[str, str]],
    crop_metrics: list[CropMetric],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "run_id": run_id,
        "task_id": TASK_ID,
        "canonical_run": CANONICAL_RUN,
        "crs": "EPSG:25832 numeric UTM32 for footprints, ALS, and camera centers after T2 OPF scene-reference transform",
        "failure_ids": failure_ids,
        "control_success_ids": control_ids,
        "failure_rows": failure_rows,
        "thresholds": threshold_rows,
        "control_summary": control_summary,
        "crop_metric_count": len(crop_metrics),
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def render_texture_crop_figure(
    out_path: Path,
    image_dir: Path,
    crop_metrics: list[CropMetric],
    failure_rows: list[dict[str, str]],
) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    failure_ids = {row["building_id"] for row in failure_rows}
    no_texture_candidates = [
        metric
        for metric in crop_metrics
        if metric.building_id in failure_ids and metric.view_kind == "near_nadir" and np.isfinite(metric.texture_gradient_mean)
    ]
    texture_candidates = [
        metric
        for metric in crop_metrics
        if metric.cohort == "control_success_71" and metric.view_kind == "near_nadir" and np.isfinite(metric.texture_gradient_mean)
    ]
    if not no_texture_candidates or not texture_candidates:
        raise RuntimeError("Not enough crop metrics to render T9 representative texture figure")
    low = min(no_texture_candidates, key=lambda item: item.texture_gradient_mean)
    high = max(texture_candidates, key=lambda item: item.texture_gradient_mean)
    examples = [
        ("textured control roof", high),
        ("low-texture failure roof", low),
    ]
    fig, axes = plt.subplots(1, 2, figsize=(9.0, 4.0), constrained_layout=True)
    for ax, (title, metric) in zip(axes, examples):
        image_path = image_dir / metric.image_name
        with Image.open(image_path) as image:
            rgb = image.convert("RGB")
            crop = np.asarray(rgb.crop(metric.bbox))
        ax.imshow(crop)
        polygon = metric.polygon_in_crop
        closed = np.vstack([polygon, polygon[0]])
        ax.plot(closed[:, 0], closed[:, 1], color="#ffcc00", linewidth=1.2)
        ax.set_title(
            f"{title}\n{metric.building_id.replace('DEBY_LOD2_', '')}, grad={metric.texture_gradient_mean:.4f}, shadow={metric.shadow_ratio:.2f}",
            fontsize=9,
        )
        ax.set_axis_off()
    fig.suptitle("T9 representative roof crops for texture diagnosis", fontsize=11)
    fig.savefig(out_path, dpi=220)
    plt.close(fig)


def write_report(
    out_path: Path,
    run_id: str,
    run_dir: Path,
    metrics_csv: Path,
    thresholds_csv: Path,
    control_csv: Path,
    metrics_json: Path,
    crop_fig: Path,
    failure_rows: list[dict[str, str]],
    threshold_rows: list[dict[str, str]],
    control_summary: list[dict[str, str]],
    class_counts: Counter[str],
    recoverable_count: int,
    non_recoverable_count: int,
) -> None:
    texture_count = sum(row["surface_cause_classification"] == "무텍스처" for row in failure_rows)
    texture_confirmed_count = sum(
        row["surface_cause_classification"] == "무텍스처" and "below the control-success threshold" in row["classification_note"]
        for row in failure_rows
    )
    texture_residual_count = texture_count - texture_confirmed_count
    out_path.write_text(
        "\n".join(
            [
                "# W3 Failure Surface Cause (T9)",
                "",
                f"- Run ID: {run_id}",
                f"- Run directory: {rel(run_dir)}",
                f"- Canonical input: `{CANONICAL_RUN}`",
                f"- Building metrics CSV: `{rel(metrics_csv)}`",
                f"- Threshold CSV: `{rel(thresholds_csv)}`",
                f"- Control summary CSV: `{rel(control_csv)}`",
                f"- Metrics JSON: `{rel(metrics_json)}`",
                "- Inputs: failure 8 IDs/T7 output, original UAV images, T2 COLMAP poses, T5 footprint GPKG, T3 DIM density via T7, and ALS LAZ roof reference.",
                "- CRS: EPSG:25832 numeric UTM32 for footprints, ALS, and camera centers after T2 scene-reference transform.",
                "- Scope: automatic cause classification/observation only. P0 acceptance/rejection remains outside this T9 output.",
                "",
                "## Failure Surface Cause Table",
                "",
                markdown_table(
                    failure_rows,
                    [
                        "building_id",
                        "near_nadir_view_count",
                        "oblique_view_count",
                        "near_nadir_texture_gradient_mean",
                        "near_nadir_texture_gradient_p10",
                        "near_nadir_gray_std",
                        "near_nadir_brightness_median",
                        "near_nadir_shadow_ratio",
                        "dim_density_pts_m2",
                        "surface_cause_classification",
                        "surface_cause_recoverable",
                    ],
                ),
                "",
                "## Adopted Thresholds",
                "",
                markdown_table(threshold_rows, ["threshold", "value", "source", "interpretation"]),
                "",
                "## Control Summary",
                "",
                markdown_table(control_summary, ["metric", "n", "median", "p10", "p25", "p75", "p90"]),
                "",
                "## Figure",
                "",
                f"![texture crop examples]({rel(crop_fig).replace('docs/', '')})",
                "",
                "## Observations",
                "",
                (
                    f"- Surface-cause recovery candidates: {recoverable_count}/8 무텍스처=복구가능 관찰, "
                    f"{non_recoverable_count}/8 커버리지/그림자/구조화부족 관찰."
                ),
                (
                    "- Classification counts: "
                    + ", ".join(
                        f"{label} {class_counts.get(label, 0)}"
                        for label in ["무텍스처", "그림자", "나디르_커버리지부족", "구조화부족"]
                    )
                    + "."
                ),
                f"- 무텍스처 {texture_count}건 중 {texture_confirmed_count}건은 near-nadir 저구배/저분산 threshold-confirmed, {texture_residual_count}건은 커버리지·그림자·구조화 trigger가 없는 texture-limited 잔여 관찰이다.",
                "- T7 occlusion was not reused as a cause label here; T9 uses projected roof image texture/lighting and near-nadir view counts.",
                "- Shadow ratio is the fraction of roof-crop grayscale pixels below 0.20; texture is mean grayscale gradient in the projected roof mask.",
                "- `surface_cause_recoverable=yes` marks texture-limited cases as GS-JSO surface-formation candidates for E5 confirmation, not as a P0 decision.",
                "- E5 confirmation is still required before using these T9 categories as a method-level conclusion.",
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
    thresholds_csv: Path,
    control_csv: Path,
    crop_fig: Path,
) -> None:
    package.mkdir(parents=True, exist_ok=True)
    package_figs.mkdir(parents=True, exist_ok=True)
    targets = [
        (report_md, package / "W3_failure_surface_cause.md"),
        (metrics_csv, package / "t9_failure_surface_cause_building_metrics.csv"),
        (thresholds_csv, package / "t9_failure_surface_cause_thresholds.csv"),
        (control_csv, package / "t9_failure_surface_cause_control_summary.csv"),
        (crop_fig, package_figs / "fig_13_t9_failure_texture_crops.png"),
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
    manifest["t9_failure_surface_cause"] = {
        "report": "W3_failure_surface_cause.md",
        "figure": "figs/fig_13_t9_failure_texture_crops.png",
        "tables": [
            "t9_failure_surface_cause_building_metrics.csv",
            "t9_failure_surface_cause_thresholds.csv",
            "t9_failure_surface_cause_control_summary.csv",
        ],
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def convert_gpkg_to_geojson(gpkg_path: Path, geojson_path: Path, layer: str) -> None:
    if geojson_path.exists():
        geojson_path.unlink()
    run(["ogr2ogr", "-f", "GeoJSON", str(geojson_path), str(gpkg_path), layer], cwd=Path("/workspace"))


def assert_gpkg_epsg25832(gpkg_path: Path, layer: str) -> None:
    if not gpkg_path.exists():
        raise FileNotFoundError(gpkg_path)
    text = capture(["ogrinfo", "-al", "-so", str(gpkg_path), layer], cwd=Path("/workspace"))
    accepted = "25832" in text or "ETRS89" in text.upper() or "UTM ZONE 32" in text.upper()
    if not accepted:
        raise AssertionError(f"Footprint GPKG CRS is not tagged as EPSG:25832/ETRS89 UTM32: {gpkg_path}")


def load_footprints(path: Path, building_ids: set[str]) -> dict[str, Footprint]:
    data = read_json(path)
    output: dict[str, Footprint] = {}
    for feature in data["features"]:
        props = feature["properties"]
        bid = props["building_id"]
        if bid not in building_ids:
            continue
        ring = np.array(feature["geometry"]["coordinates"][0], dtype=np.float64)
        if ring.shape[0] < 4:
            continue
        if not np.allclose(ring[0], ring[-1]):
            ring = np.vstack([ring, ring[0]])
        if bid in output:
            # T7/T9 target buildings are single-part in the canonical scene.
            if float(props["area_m2"]) <= output[bid].area_m2:
                continue
        output[bid] = Footprint(
            building_id=bid,
            area_m2=float(props["area_m2"]),
            bbox=(float(props["min_x"]), float(props["min_y"]), float(props["max_x"]), float(props["max_y"])),
            ring=ring,
        )
    missing = sorted(building_ids - output.keys())
    if missing:
        raise RuntimeError(f"Missing footprints: {', '.join(missing[:10])}")
    return output


def assert_epsg25832_footprints(footprints: dict[str, Footprint]) -> None:
    xs = np.array([value for fp in footprints.values() for value in (fp.bbox[0], fp.bbox[2])])
    ys = np.array([value for fp in footprints.values() for value in (fp.bbox[1], fp.bbox[3])])
    if not np.all((100000.0 <= xs) & (xs <= 900000.0)):
        raise AssertionError("Footprint easting values are outside UTM zone 32 numeric range")
    if not np.all((5_000_000.0 <= ys) & (ys <= 6_200_000.0)):
        raise AssertionError("Footprint northing values are outside Germany UTM northing range")


def combined_bbox(footprints: list[Footprint], buffer_m: float) -> tuple[float, float, float, float]:
    return (
        min(fp.bbox[0] for fp in footprints) - buffer_m,
        min(fp.bbox[1] for fp in footprints) - buffer_m,
        max(fp.bbox[2] for fp in footprints) + buffer_m,
        max(fp.bbox[3] for fp in footprints) + buffer_m,
    )


def read_cloud(label: str, paths: list[Path], bbox: tuple[float, float, float, float]) -> Cloud:
    import laspy

    xs: list[np.ndarray] = []
    ys: list[np.ndarray] = []
    zs: list[np.ndarray] = []
    classes: list[np.ndarray] = []
    crs_text = ""
    min_x, min_y, max_x, max_y = bbox
    for path in paths:
        if not path.exists():
            raise FileNotFoundError(path)
        with laspy.open(path) as fh:
            if not crs_text:
                crs = fh.header.parse_crs()
                crs_text = crs.to_string() if crs else ""
            for points in fh.chunk_iterator(1_000_000):
                x = np.asarray(points.x)
                y = np.asarray(points.y)
                mask = (x >= min_x) & (x <= max_x) & (y >= min_y) & (y <= max_y)
                if not np.any(mask):
                    continue
                xs.append(x[mask].astype(np.float64, copy=False))
                ys.append(y[mask].astype(np.float64, copy=False))
                zs.append(np.asarray(points.z)[mask].astype(np.float64, copy=False))
                classes.append(np.asarray(points.classification, dtype=np.uint8)[mask])
    if not xs:
        raise RuntimeError(f"No {label} points overlap T9 target bbox")
    return Cloud(label, paths, np.concatenate(xs), np.concatenate(ys), np.concatenate(zs), np.concatenate(classes), crs_text)


def assert_epsg25832_cloud(label: str, cloud: Cloud) -> None:
    x_med = float(np.median(cloud.x))
    y_med = float(np.median(cloud.y))
    if not (100000.0 <= x_med <= 900000.0 and 5_000_000.0 <= y_med <= 6_200_000.0):
        raise AssertionError(f"{label} point cloud is not in EPSG:25832 numeric range")
    if not cloud.crs_text:
        print(f"{label} CRS tag is empty; accepted by numeric UTM32 range and T5 footprint alignment.", flush=True)
        return
    crs_text = cloud.crs_text.upper()
    accepted = ("25832" in crs_text) or ("ETRS89" in crs_text) or ("UTM ZONE 32N" in crs_text)
    if not accepted:
        raise AssertionError(f"{label} CRS is not tagged as EPSG:25832/ETRS89 UTM32: {cloud.crs_text}")


def surface_metrics(cloud: Cloud, footprint: Footprint) -> SurfaceMetric:
    x, y, z = clip_building_points(cloud, footprint)
    if z.size == 0:
        return SurfaceMetric(0, 0.0, 1.0, math.nan, math.nan, math.nan, None)
    density = float(z.size / footprint.area_m2)
    plane_rmse, normal = fit_plane(x, y, z)
    return SurfaceMetric(
        point_count=int(z.size),
        density_pts_m2=density,
        hole_ratio=0.0,
        plane_rmse_m=plane_rmse,
        roof_z_median=float(np.median(z)),
        roof_z_p90=float(np.percentile(z, 90.0)),
        normal=normal,
    )


def clip_building_points(cloud: Cloud, footprint: Footprint) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    min_x, min_y, max_x, max_y = footprint.bbox
    mask = (
        (cloud.classification == BUILDING_CLASS)
        & (cloud.x >= min_x)
        & (cloud.x <= max_x)
        & (cloud.y >= min_y)
        & (cloud.y <= max_y)
    )
    if not np.any(mask):
        return np.array([]), np.array([]), np.array([])
    x = cloud.x[mask]
    y = cloud.y[mask]
    z = cloud.z[mask]
    inside = points_in_polygon(x, y, footprint.ring)
    return x[inside], y[inside], z[inside]


def points_in_polygon(xs: np.ndarray, ys: np.ndarray, ring: np.ndarray) -> np.ndarray:
    inside = np.zeros(xs.shape, dtype=bool)
    for idx in range(ring.shape[0] - 1):
        x1, y1 = ring[idx]
        x2, y2 = ring[idx + 1]
        crossing = (y1 > ys) != (y2 > ys)
        if not np.any(crossing):
            continue
        x_at_y = (x2 - x1) * (ys[crossing] - y1) / (y2 - y1) + x1
        inside[crossing] ^= xs[crossing] < x_at_y
    return inside


def fit_plane(x: np.ndarray, y: np.ndarray, z: np.ndarray) -> tuple[float, np.ndarray | None]:
    if z.size < 20:
        return math.nan, None
    cutoff = float(np.percentile(z, 35.0))
    roof = z >= cutoff
    if np.count_nonzero(roof) >= 20:
        x = x[roof]
        y = y[roof]
        z = z[roof]
    cx = float(np.mean(x))
    cy = float(np.mean(y))
    design = np.column_stack([x - cx, y - cy, np.ones_like(x)])
    coef, *_ = np.linalg.lstsq(design, z, rcond=None)
    residuals = z - design @ coef
    keep_cutoff = float(np.percentile(np.abs(residuals), 95.0))
    keep = np.abs(residuals) <= keep_cutoff
    if np.count_nonzero(keep) >= 20:
        design = design[keep]
        z = z[keep]
        coef, *_ = np.linalg.lstsq(design, z, rcond=None)
        residuals = z - design @ coef
    a, b, _ = coef
    normal = np.array([-a, -b, 1.0], dtype=np.float64)
    normal /= np.linalg.norm(normal)
    if normal[2] < 0.0:
        normal = -normal
    return float(np.sqrt(np.mean(residuals**2))), normal


def parse_camera_model(path: Path) -> CameraModel:
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            parts = stripped.split()
            if parts[1] != "FULL_OPENCV":
                raise RuntimeError(f"Expected FULL_OPENCV camera model, got {parts[1]}")
            return CameraModel(int(parts[2]), int(parts[3]), np.array([float(value) for value in parts[4:]], dtype=np.float64))
    raise RuntimeError(f"No camera model found in {path}")


def parse_colmap_cameras(path: Path, scene_ref: dict[str, Any]) -> list[Camera]:
    cameras: list[Camera] = []
    expect_pose = True
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            if not expect_pose:
                expect_pose = True
                continue
            parts = stripped.split()
            if len(parts) < 10:
                raise RuntimeError(f"Unexpected COLMAP image pose line: {stripped[:120]}")
            qvec = np.array([float(value) for value in parts[1:5]], dtype=np.float64)
            tvec = np.array([float(value) for value in parts[5:8]], dtype=np.float64)
            rot = qvec_to_rotmat(qvec)
            center_canonical = -rot.T @ tvec
            center_base = canonical_to_base(center_canonical.reshape(1, 3), scene_ref)[0]
            cameras.append(Camera(int(parts[0]), " ".join(parts[9:]), qvec, tvec, rot, center_canonical, center_base))
            expect_pose = False
    return cameras


def qvec_to_rotmat(qvec: np.ndarray) -> np.ndarray:
    q0, q1, q2, q3 = qvec
    return np.array(
        [
            [1 - 2 * q2 * q2 - 2 * q3 * q3, 2 * q1 * q2 - 2 * q0 * q3, 2 * q3 * q1 + 2 * q0 * q2],
            [2 * q1 * q2 + 2 * q0 * q3, 1 - 2 * q1 * q1 - 2 * q3 * q3, 2 * q2 * q3 - 2 * q0 * q1],
            [2 * q3 * q1 - 2 * q0 * q2, 2 * q2 * q3 + 2 * q0 * q1, 1 - 2 * q1 * q1 - 2 * q2 * q2],
        ],
        dtype=np.float64,
    )


def base_to_canonical(points: np.ndarray, scene_ref: dict[str, Any]) -> np.ndarray:
    transform = scene_ref.get("base_to_canonical", {})
    arr = points.copy()
    if transform.get("swap_xy", False):
        arr[:, [0, 1]] = arr[:, [1, 0]]
    shift = np.array(transform.get("shift", [0.0, 0.0, 0.0]), dtype=np.float64)
    scale = np.array(transform.get("scale", [1.0, 1.0, 1.0]), dtype=np.float64)
    return (arr + shift) * scale


def canonical_to_base(points: np.ndarray, scene_ref: dict[str, Any]) -> np.ndarray:
    transform = scene_ref.get("base_to_canonical", {})
    scale = np.array(transform.get("scale", [1.0, 1.0, 1.0]), dtype=np.float64)
    shift = np.array(transform.get("shift", [0.0, 0.0, 0.0]), dtype=np.float64)
    arr = points / scale - shift
    if transform.get("swap_xy", False):
        arr[:, [0, 1]] = arr[:, [1, 0]]
    return arr


def assert_epsg25832_camera_range(cameras: list[Camera]) -> None:
    centers = np.vstack([camera.center_base for camera in cameras])
    if not np.all((100000.0 <= centers[:, 0]) & (centers[:, 0] <= 900000.0)):
        raise AssertionError("Camera easting values are outside UTM zone 32 numeric range")
    if not np.all((5_000_000.0 <= centers[:, 1]) & (centers[:, 1] <= 6_200_000.0)):
        raise AssertionError("Camera northing values are outside Germany UTM northing range")


def assert_image_inputs(image_dir: Path, cameras: list[Camera]) -> None:
    missing = [camera.name for camera in cameras if not (image_dir / camera.name).exists()]
    if missing:
        raise FileNotFoundError(f"Missing {len(missing)} COLMAP images under {image_dir}: {', '.join(missing[:5])}")


def footprint_sample_points(footprint: Footprint, roof_z: float) -> np.ndarray:
    ring = footprint.ring[:-1]
    points = [ring]
    edge_points = []
    for idx in range(ring.shape[0]):
        p1 = ring[idx]
        p2 = ring[(idx + 1) % ring.shape[0]]
        edge_points.extend([p1 * 0.75 + p2 * 0.25, p1 * 0.5 + p2 * 0.5, p1 * 0.25 + p2 * 0.75])
    points.append(np.array(edge_points, dtype=np.float64))
    points.append(np.mean(ring, axis=0).reshape(1, 2))
    xy = np.vstack(points)
    return np.column_stack([xy, np.full(xy.shape[0], roof_z, dtype=np.float64)])


def footprint_roof_ring(footprint: Footprint, roof_z: float) -> np.ndarray:
    xy = footprint.ring[:-1]
    return np.column_stack([xy, np.full(xy.shape[0], roof_z, dtype=np.float64)])


def project_points(points_base: np.ndarray, camera: Camera, camera_model: CameraModel, scene_ref: dict[str, Any]) -> tuple[np.ndarray, np.ndarray]:
    points_canonical = base_to_canonical(points_base, scene_ref)
    cam = (camera.rot @ points_canonical.T).T + camera.tvec
    in_front = cam[:, 2] > 0.1
    u = np.full(points_base.shape[0], np.nan, dtype=np.float64)
    v = np.full(points_base.shape[0], np.nan, dtype=np.float64)
    if not np.any(in_front):
        return np.column_stack([u, v]), in_front
    fx, fy, cx, cy, k1, k2, p1, p2, k3, k4, k5, k6 = camera_model.params[:12]
    x = cam[in_front, 0] / cam[in_front, 2]
    y = cam[in_front, 1] / cam[in_front, 2]
    r2 = x * x + y * y
    r4 = r2 * r2
    r6 = r4 * r2
    denom = 1.0 + k4 * r2 + k5 * r4 + k6 * r6
    denom = np.where(np.abs(denom) < 1e-12, 1.0, denom)
    radial = (1.0 + k1 * r2 + k2 * r4 + k3 * r6) / denom
    xd = x * radial + 2.0 * p1 * x * y + p2 * (r2 + 2.0 * x * x)
    yd = y * radial + p1 * (r2 + 2.0 * y * y) + 2.0 * p2 * x * y
    u[in_front] = fx * xd + cx
    v[in_front] = fy * yd + cy
    return np.column_stack([u, v]), in_front


def projection_overlaps_image(projected_ring: np.ndarray, camera_model: CameraModel) -> bool:
    if not np.all(np.isfinite(projected_ring)):
        return False
    min_u = float(np.min(projected_ring[:, 0]))
    max_u = float(np.max(projected_ring[:, 0]))
    min_v = float(np.min(projected_ring[:, 1]))
    max_v = float(np.max(projected_ring[:, 1]))
    return max_u >= 0.0 and min_u < camera_model.width and max_v >= 0.0 and min_v < camera_model.height


def incidence_angle(camera_center: np.ndarray, target: np.ndarray, normal: np.ndarray) -> float:
    view_vec = camera_center - target
    norm = float(np.linalg.norm(view_vec))
    if norm <= 0.0:
        return math.nan
    unit = view_vec / norm
    cos_incidence = float(np.clip(np.dot(unit, normal), -1.0, 1.0))
    return math.degrees(math.acos(abs(cos_incidence)))


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
    issues = repo / "phases/p0-audit/docs/issues.md"
    with issues.open("a", encoding="utf-8") as fh:
        fh.write(f"\n## {TASK_ID} Failure Surface Cause\n\n")
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
                "t7_metrics: docs/W3_failure_diagnosis_building_metrics.csv",
                "images: " + IMAGE_DIR,
                "colmap_poses: data/work/colmap/sparse/0/images.txt",
                "footprints: " + FOOTPRINT_GPKG,
                "dim_pointcloud: data/work/w2/dim_v1_classified_z_minus0p174.laz",
                "als_pointcloud: data/raw/als/*.laz",
                "crs: EPSG:25832 numeric UTM32 coordinates",
                f"near_nadir_incidence_max_deg: {NEAR_NADIR_MAX_INCIDENT_DEG}",
                "classification_rule: control-success image texture/lighting thresholds; no P0 judgement",
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
        "# T9 Failure Surface Cause Tool Versions",
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


def median_values(values: list[float]) -> float:
    arr = np.array([value for value in values if np.isfinite(value)], dtype=np.float64)
    return float(np.median(arr)) if arr.size else math.nan


def percentile(values: list[float], q: float) -> float:
    arr = np.array([value for value in values if np.isfinite(value)], dtype=np.float64)
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
