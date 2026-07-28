"""Reference-backed TUM2TWIN baseline metrics and provisional R_v1 strata.

The module runs in the existing ``jointbuildgs:dev`` image after the P0-tools
cache adapter has read LAS/LAZ and CityGML inputs.  It never aligns, trains, or
reconstructs geometry.
"""
from __future__ import annotations

import argparse
import csv
import glob
import importlib.util
import json
import math
import os
import signal
import subprocess
import time
import traceback
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import matplotlib
import numpy as np
from scipy.spatial import cKDTree
from scipy.stats import rankdata
from shapely import contains_xy, wkt

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402


REPO = Path(__file__).resolve().parents[1]
SCIENTIFIC_STATUS = (
    "R_v1 is a relative, provisional stratification for experiment selection. "
    "It is not a final scientific readiness or quality certification."
)
SCHEMA = "jointbuildgs.tum2twin_rv1.result.v1"


def now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat()


def read_config(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        import yaml

        return yaml.safe_load(text)


def atomic_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(text, encoding="utf-8")
    os.replace(temporary, path)


def atomic_json(path: Path, payload: Any) -> None:
    atomic_text(
        path,
        json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=True) + "\n",
    )


def csv_value(value: Any) -> Any:
    if value is None:
        return "NaN"
    if isinstance(value, (float, np.floating)):
        return f"{float(value):.9f}" if math.isfinite(float(value)) else "NaN"
    if isinstance(value, bool):
        return str(value).lower()
    if isinstance(value, (list, dict)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return value


def atomic_csv(path: Path, rows: Sequence[Mapping[str, Any]], fields: Sequence[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if fields is None:
        keys: set[str] = set()
        for row in rows:
            keys.update(row)
        fields = sorted(keys)
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(fields), extrasaction="ignore", lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: csv_value(row.get(field)) for field in fields})
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def finite(value: Any) -> bool:
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def number(value: Any) -> float:
    try:
        parsed = float(value)
        return parsed if math.isfinite(parsed) else math.nan
    except (TypeError, ValueError):
        return math.nan


def bool_value(value: Any) -> bool:
    return str(value).strip().lower() in {"true", "1", "yes", "y"}


def load_population(config: dict[str, Any]) -> list[str]:
    source = REPO / config["sources"]["population_manifest"]
    rows = list(csv.DictReader(source.open(newline="", encoding="utf-8")))
    arm = config["sources"]["population_arm"]
    ids = sorted(
        row["building_id"]
        for row in rows
        if row.get("arm") == arm and bool_value(row.get("assembled"))
    )
    if len(ids) != 178 or len(set(ids)) != 178:
        raise RuntimeError(f"canonical population drift rows={len(ids)} unique={len(set(ids))}")
    return ids


def voxel_downsample(points: np.ndarray, voxel_size: float) -> np.ndarray:
    points = np.asarray(points, dtype=np.float64)
    if len(points) == 0:
        return points.reshape((0, 3))
    origin = np.min(points, axis=0)
    keys = np.floor((points - origin) / voxel_size).astype(np.int64)
    _, inverse = np.unique(keys, axis=0, return_inverse=True)
    counts = np.bincount(inverse).astype(np.float64)
    result = np.empty((len(counts), 3), dtype=np.float64)
    for axis in range(3):
        result[:, axis] = np.bincount(inverse, weights=points[:, axis]) / counts
    return result


def deterministic_cap(points: np.ndarray, maximum: int) -> tuple[np.ndarray, bool]:
    if len(points) <= maximum:
        return points, False
    indices = np.linspace(0, len(points) - 1, maximum, dtype=np.int64)
    return points[indices], True


def nearest_distances(source: np.ndarray, target: np.ndarray, workers: int = 1) -> np.ndarray:
    if len(source) == 0 or len(target) == 0:
        return np.empty(0, dtype=np.float64)
    distances, _indices = cKDTree(np.asarray(target, dtype=np.float64)).query(
        np.asarray(source, dtype=np.float64),
        k=1,
        workers=max(1, int(workers)),
    )
    return np.asarray(distances, dtype=np.float64)


def precision_recall_fscore(
    reconstruction_to_reference: np.ndarray,
    reference_to_reconstruction: np.ndarray,
    threshold: float,
) -> tuple[float, float, float]:
    if not len(reconstruction_to_reference) or not len(reference_to_reconstruction):
        return math.nan, math.nan, math.nan
    precision = float(np.mean(reconstruction_to_reference <= threshold))
    recall = float(np.mean(reference_to_reconstruction <= threshold))
    fscore = 2.0 * precision * recall / (precision + recall) if precision + recall > 0 else 0.0
    return precision, recall, fscore


def distance_summary(values: np.ndarray, prefix: str) -> dict[str, Any]:
    if not len(values):
        return {
            f"{prefix}_median_m": math.nan,
            f"{prefix}_p90_m": math.nan,
            f"{prefix}_p95_m": math.nan,
        }
    return {
        f"{prefix}_median_m": float(np.median(values)),
        f"{prefix}_p90_m": float(np.percentile(values, 90)),
        f"{prefix}_p95_m": float(np.percentile(values, 95)),
    }


def surface_thickness_p90(points: np.ndarray, xy_cell: float) -> float:
    if not len(points):
        return math.nan
    origin = np.min(points[:, :2], axis=0)
    keys = np.floor((points[:, :2] - origin) / xy_cell).astype(np.int64)
    _, inverse = np.unique(keys, axis=0, return_inverse=True)
    order = np.argsort(inverse, kind="mergesort")
    inv_sorted = inverse[order]
    z_sorted = points[order, 2]
    starts = np.r_[0, np.nonzero(np.diff(inv_sorted))[0] + 1]
    ends = np.r_[starts[1:], len(inv_sorted)]
    spans = np.asarray([np.max(z_sorted[start:end]) - np.min(z_sorted[start:end]) for start, end in zip(starts, ends)])
    return float(np.percentile(spans, 90)) if len(spans) else math.nan


def density_diagnostics(points: np.ndarray, polygon_wkt: str, area_m2: float, grid_m: float) -> dict[str, Any]:
    polygon = wkt.loads(polygon_wkt)
    minx, miny, maxx, maxy = polygon.bounds
    xs = np.arange(minx + grid_m / 2.0, maxx, grid_m)
    ys = np.arange(miny + grid_m / 2.0, maxy, grid_m)
    if not len(xs) or not len(ys):
        return {
            "roof_points_per_m2": len(points) / area_m2 if area_m2 > 0 else math.nan,
            "local_density_cv": math.nan,
            "largest_data_gap_m": math.nan,
            "diagnostic_grid_cells": 0,
        }
    xx, yy = np.meshgrid(xs, ys)
    centers = np.column_stack([xx.ravel(), yy.ravel()])
    centers = centers[contains_xy(polygon, centers[:, 0], centers[:, 1])]
    if not len(centers):
        return {
            "roof_points_per_m2": len(points) / area_m2 if area_m2 > 0 else math.nan,
            "local_density_cv": math.nan,
            "largest_data_gap_m": math.nan,
            "diagnostic_grid_cells": 0,
        }
    if len(points):
        ix = np.floor((points[:, 0] - minx) / grid_m).astype(int)
        iy = np.floor((points[:, 1] - miny) / grid_m).astype(int)
        occupied: dict[tuple[int, int], int] = {}
        for key in zip(ix, iy):
            occupied[key] = occupied.get(key, 0) + 1
        counts = np.asarray(
            [
                occupied.get(
                    (int(math.floor((x - minx) / grid_m)), int(math.floor((y - miny) / grid_m))),
                    0,
                )
                for x, y in centers
            ],
            dtype=float,
        )
        mean = float(np.mean(counts))
        cv = float(np.std(counts) / mean) if mean > 0 else math.nan
        gap = float(np.max(nearest_distances(np.column_stack([centers, np.zeros(len(centers))]), np.column_stack([points[:, :2], np.zeros(len(points))]))))
    else:
        cv = math.nan
        gap = math.nan
    return {
        "roof_points_per_m2": len(points) / area_m2 if area_m2 > 0 else math.nan,
        "local_density_cv": cv,
        "largest_data_gap_m": gap,
        "diagnostic_grid_cells": int(len(centers)),
    }


def load_cache_array(path: Path) -> dict[str, np.ndarray]:
    with np.load(path, allow_pickle=False) as payload:
        return {key: np.asarray(payload[key]) for key in payload.files}


def load_existing_diagnostics(config: dict[str, Any]) -> dict[str, dict[str, str]]:
    path = REPO / config["sources"]["existing_pointcloud_diagnostics"]
    if not path.is_file():
        return {}
    result: dict[str, dict[str, str]] = {}
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if row.get("arm") == "raw_dense":
                result[row["building_id"]] = row
    return result


@contextmanager
def building_timeout(seconds: int):
    def raise_timeout(_signum: int, _frame: Any) -> None:
        raise TimeoutError(f"per-building timeout after {seconds}s")

    if seconds <= 0 or not hasattr(signal, "SIGALRM"):
        yield
        return
    previous = signal.signal(signal.SIGALRM, raise_timeout)
    signal.alarm(seconds)
    try:
        yield
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, previous)


def compute_building(
    config: dict[str, Any],
    building_id: str,
    existing_diag: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    processing = config["processing"]
    cache_root = REPO / config["outputs"]["cache_root"] / building_id
    complete = cache_root / "complete.json"
    required = [complete, cache_root / "dense.npz", cache_root / "reference.npz", cache_root / "lod2.json", cache_root / "footprint.json"]
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"incomplete cache: {missing}")
    dense = load_cache_array(cache_root / "dense.npz")
    reference = load_cache_array(cache_root / "reference.npz")
    footprint = json.loads((cache_root / "footprint.json").read_text(encoding="utf-8"))
    lod2 = json.loads((cache_root / "lod2.json").read_text(encoding="utf-8"))
    dense_inside = dense["inside"].astype(bool)
    ref_inside = reference["inside"].astype(bool)
    dense_class = dense["classification"].astype(np.uint8)
    ref_class = reference["classification"].astype(np.uint8)
    reconstruction_raw = dense["xyz"][dense_inside & (dense_class == 6)]
    reference_raw = reference["xyz"][ref_inside & (ref_class == 6)]
    voxel = float(processing["voxel_size_m"])
    reconstruction = voxel_downsample(reconstruction_raw, voxel)
    reference_points = voxel_downsample(reference_raw, voxel)
    maximum = int(processing["max_surface_points_per_direction"])
    reconstruction, reconstruction_capped = deterministic_cap(reconstruction, maximum)
    reference_points, reference_capped = deterministic_cap(reference_points, maximum)
    r2ref = nearest_distances(reconstruction, reference_points, int(processing["worker_count"]))
    ref2r = nearest_distances(reference_points, reconstruction, int(processing["worker_count"]))
    surface_available = bool(len(r2ref) and len(ref2r))
    result: dict[str, Any] = {
        "schema": SCHEMA,
        "run_id": config["run_id"],
        "building_id": building_id,
        "processing_status": "success",
        "processing_reason": "ok",
        "scientific_status": SCIENTIFIC_STATUS,
        "provisional": True,
        "crs": config["crs"],
        "footprint_area_m2": number(footprint.get("area_m2")),
        "surface_reference_role": config["sources"]["surface_reference_role"],
        "surface_metric_available": surface_available,
        "surface_metric_reason": "ok" if surface_available else "class-6 reconstruction or reference points unavailable",
        "reconstruction_class6_count_raw": int(len(reconstruction_raw)),
        "reference_class6_count_raw": int(len(reference_raw)),
        "reconstruction_surface_count_voxel": int(len(reconstruction)),
        "reference_surface_count_voxel": int(len(reference_points)),
        "surface_sampling_capped": bool(reconstruction_capped or reference_capped),
        "voxel_size_m": voxel,
        "class2_ground_point_count": int(np.sum(dense_inside & (dense_class == 2))),
        "class6_building_point_count": int(np.sum(dense_inside & (dense_class == 6))),
        "ground_point_availability": bool(np.any(dense_inside & (dense_class == 2))),
        "building_classification_availability": bool(np.any(dense_inside & (dense_class == 6))),
        "classification_availability": bool(np.any(dense_inside & (dense_class == 2)) and np.any(dense_inside & (dense_class == 6))),
        "input_pointcloud_provenance": config["sources"]["dense_mvs_pointcloud"],
        "surface_reference_provenance": config["sources"]["surface_reference_pointclouds"],
        "crop_buffer_m": number(footprint.get("crop_buffer_m")),
        "icp_applied": False,
        "normal_estimation_enabled": bool(processing["normal_estimation_enabled"]),
        "point_to_plane_median_m": math.nan,
        "point_to_plane_p95_m": math.nan,
        "point_to_plane_reason": "normal estimation disabled by config",
        "normal_angular_error_median_deg": math.nan,
        "normal_angular_error_p90_deg": math.nan,
        "normal_metric_reason": "normal estimation disabled by config",
        "appearance_status": "not_evaluated",
        "appearance_metric_source": "none",
        "psnr": math.nan,
        "ssim": math.nan,
        "lpips": math.nan,
        "texture_coverage": math.nan,
        "appearance_reason": config["appearance"]["missing_reason"],
        "completed_at": now(),
    }
    for threshold in processing["distance_thresholds_m"]:
        precision, recall, fscore = precision_recall_fscore(r2ref, ref2r, float(threshold))
        suffix = str(float(threshold)).replace(".", "p")
        result[f"surface_precision_{suffix}m"] = precision
        result[f"surface_recall_{suffix}m"] = recall
        result[f"surface_fscore_{suffix}m"] = fscore
    result.update(distance_summary(r2ref, "reconstruction_to_reference"))
    result.update(distance_summary(ref2r, "reference_to_reconstruction"))
    result["bidirectional_distance_p95_m"] = (
        max(result["reconstruction_to_reference_p95_m"], result["reference_to_reconstruction_p95_m"])
        if surface_available
        else math.nan
    )
    result["maximum_hole_radius_proxy_m"] = float(np.max(ref2r)) if len(ref2r) else math.nan
    result["largest_unsupported_roof_region"] = result["maximum_hole_radius_proxy_m"]
    result["largest_unsupported_roof_region_reason"] = "maximum reference-to-reconstruction nearest distance; point-sampled radius proxy"
    result["surface_thickness_p90_m"] = surface_thickness_p90(reconstruction, max(voxel, 0.2))
    result.update(
        density_diagnostics(
            reconstruction_raw,
            footprint["wkt"],
            float(footprint["area_m2"]),
            float(processing["diagnostic_grid_m"]),
        )
    )
    result.update(lod2)
    diag = dict(existing_diag or {})
    result.update(
        {
            "existing_local_plane_rms_m": number(diag.get("local_plane_rms_m")),
            "existing_m3c2_rms_m": number(diag.get("m3c2_rms_m")),
            "existing_m3c2_valid": bool_value(diag.get("m3c2_valid")),
            "existing_diagnostic_provenance": config["sources"]["existing_pointcloud_diagnostics"],
            "roofprint_alignment_information": diag.get("z_datum_history", "unknown"),
            "nodata_frac": number(lod2.get("rf_nodata_frac")),
            "nodata_r": math.nan,
            "nodata_r_reason": "field not present in canonical Roofer status",
        }
    )
    return result


def percentile_ranks(values: Sequence[Any], inverse: bool = False) -> list[float]:
    output = [math.nan] * len(values)
    valid_indices = [index for index, value in enumerate(values) if finite(value)]
    if not valid_indices:
        return output
    array = np.asarray([float(values[index]) for index in valid_indices], dtype=float)
    if len(array) == 1:
        ranks = np.asarray([0.5])
    else:
        ranks = (rankdata(array, method="average") - 1.0) / (len(array) - 1.0)
    if inverse:
        ranks = 1.0 - ranks
    for index, rank in zip(valid_indices, ranks):
        output[index] = float(rank)
    return output


def r_label(surface_high: bool, lod2_high: bool) -> str:
    return {
        (True, True): "R0",
        (False, True): "R1",
        (True, False): "R2",
        (False, False): "R3",
    }[(surface_high, lod2_high)]


def classify_rows(rows: list[dict[str, Any]], quantiles: Sequence[float]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    fscore = [row.get("surface_fscore_0p2m") for row in rows]
    distance = [row.get("bidirectional_distance_p95_m") for row in rows]
    plane_f1 = [row.get("roof_plane_f1") for row in rows]
    rmsz = [row.get("rmsz_m") for row in rows]
    ranks = {
        "r_f": percentile_ranks(fscore),
        "r_d": percentile_ranks(distance, inverse=True),
        "r_p": percentile_ranks(plane_f1),
        "r_z": percentile_ranks(rmsz, inverse=True),
    }
    classified: list[dict[str, Any]] = []
    for index, source_row in enumerate(rows):
        row = dict(source_row)
        for key in ranks:
            row[key] = ranks[key][index]
        surface_parts = [row[key] for key in ("r_f", "r_d") if finite(row[key])]
        if surface_parts:
            row["surface_score"] = float(np.mean(surface_parts))
            row["surface_axis"] = "known"
            row["surface_score_confidence"] = "high" if len(surface_parts) == 2 else "low"
        else:
            row["surface_score"] = math.nan
            row["surface_axis"] = "unknown"
            row["surface_score_confidence"] = "unknown"
        forced = (
            not bool_value(row.get("roofer_success"))
            or not bool_value(row.get("has_lod22"))
            or row.get("val3dity_lod22_valid") is False
        )
        lod_parts = [row[key] for key in ("r_p", "r_z") if finite(row[key])]
        if forced:
            row["lod2_score"] = 0.0
            row["lod2_axis"] = "known_forced_zero"
            row["lod2_score_confidence"] = "forced_failure"
            row["lod2_forced_zero"] = True
        elif lod_parts:
            row["lod2_score"] = float(np.mean(lod_parts))
            row["lod2_axis"] = "known"
            row["lod2_score_confidence"] = "high" if len(lod_parts) == 2 else "low"
            row["lod2_forced_zero"] = False
        else:
            row["lod2_score"] = math.nan
            row["lod2_axis"] = "unknown"
            row["lod2_score_confidence"] = "unknown"
            row["lod2_forced_zero"] = False
        row["primary_metric_missing"] = not finite(row.get("surface_fscore_0p2m")) or not finite(row.get("roof_plane_f1"))
        classified.append(row)
    surface_scores = np.asarray([row["surface_score"] for row in classified if finite(row["surface_score"])], dtype=float)
    lod2_scores = np.asarray([row["lod2_score"] for row in classified if finite(row["lod2_score"])], dtype=float)
    thresholds: dict[str, Any] = {}
    sensitivity: list[dict[str, Any]] = []
    for q in quantiles:
        qkey = f"q{int(round(float(q) * 100))}"
        surface_threshold = float(np.quantile(surface_scores, q)) if len(surface_scores) else math.nan
        lod2_threshold = float(np.quantile(lod2_scores, q)) if len(lod2_scores) else math.nan
        thresholds[qkey] = {"surface": surface_threshold, "lod2": lod2_threshold}
        for row in classified:
            if row["surface_axis"] == "unknown" or row["lod2_axis"] == "unknown" or row["primary_metric_missing"]:
                label = "RX"
                surface_axis_label = "unknown" if row["surface_axis"] == "unknown" else "not_classified"
                lod2_axis_label = "unknown" if row["lod2_axis"] == "unknown" else "not_classified"
            else:
                surface_high = float(row["surface_score"]) >= surface_threshold
                lod2_high = float(row["lod2_score"]) >= lod2_threshold
                surface_axis_label = "high" if surface_high else "low"
                lod2_axis_label = "high" if lod2_high else "low"
                label = r_label(surface_high, lod2_high)
            row[f"provisional_R_{qkey}"] = label
            sensitivity.append(
                {
                    "building_id": row["building_id"],
                    "q": q,
                    "surface_threshold": surface_threshold,
                    "lod2_threshold": lod2_threshold,
                    "surface_axis_label": surface_axis_label,
                    "lod2_axis_label": lod2_axis_label,
                    "provisional_R": label,
                    "scientific_status": SCIENTIFIC_STATUS,
                }
            )
    for row in classified:
        labels = [row[f"provisional_R_q{int(round(float(q) * 100))}"] for q in quantiles]
        stable = len(set(labels)) == 1 and labels[0] != "RX"
        row["provisional_R_stable"] = stable
        row["provisional_R_final"] = labels[0] if stable else "RX"
        reasons: list[str] = []
        if row["primary_metric_missing"]:
            reasons.append("primary metric missing")
        if row["surface_axis"] == "unknown":
            reasons.append("surface axis unknown")
        if row["lod2_axis"] == "unknown":
            reasons.append("LoD2 axis unknown")
        if len(set(labels)) != 1:
            reasons.append("q40/q50/q60 label instability")
        if row.get("lod2_forced_zero"):
            reasons.append("LoD2 score forced to zero by failure/missing/invalid shell")
        row["classification_reason"] = "; ".join(reasons) if reasons else "stable across q40/q50/q60"
        if row["provisional_R_final"] == "RX":
            row["classification_confidence"] = "unknown" if "unknown" in row["classification_reason"] else "low"
        elif row["surface_score_confidence"] == "high" and row["lod2_score_confidence"] == "high":
            row["classification_confidence"] = "high"
        else:
            row["classification_confidence"] = "low"
    return classified, sensitivity, thresholds


def result_valid(path: Path, building_id: str) -> bool:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload.get("schema") == SCHEMA and payload.get("building_id") == building_id
    except (OSError, json.JSONDecodeError):
        return False


def write_building_result(path: Path, row: dict[str, Any]) -> None:
    atomic_json(path, row)


def output_root(config: dict[str, Any]) -> Path:
    return REPO / config["outputs"]["root"]


def load_state(config: dict[str, Any]) -> dict[str, Any]:
    path = output_root(config) / "run_state.json"
    if path.is_file():
        return json.loads(path.read_text(encoding="utf-8"))
    return {
        "run_id": config["run_id"],
        "current_stage": "N0_REPO_AUDIT",
        "stage_status": "pending",
        "start_time": now(),
        "last_heartbeat": now(),
        "processed_buildings": 0,
        "total_buildings": 178,
        "successful_buildings": 0,
        "failed_buildings": 0,
        "skipped_buildings": 0,
        "current_building_id": None,
        "background_pid": None,
        "error_summary": [],
    }


def update_state(config: dict[str, Any], **updates: Any) -> dict[str, Any]:
    state = load_state(config)
    state.update(updates)
    state["last_heartbeat"] = now()
    atomic_json(output_root(config) / "run_state.json", state)
    atomic_json(
        output_root(config) / "heartbeat.json",
        {
            "run_id": config["run_id"],
            "timestamp": state["last_heartbeat"],
            "stage": state.get("current_stage"),
            "status": state.get("stage_status"),
            "current_building_id": state.get("current_building_id"),
            "processed_buildings": state.get("processed_buildings"),
        },
    )
    return state


def write_status(config: dict[str, Any], state: Mapping[str, Any], note: str = "") -> None:
    text = [
        "# Nightly R_v1 status",
        "",
        f"- Run ID: `{config['run_id']}`",
        f"- Current stage: `{state.get('current_stage')}`",
        f"- Stage status: `{state.get('stage_status')}`",
        f"- Processed: {state.get('processed_buildings', 0)} / {state.get('total_buildings', 178)}",
        f"- Successful: {state.get('successful_buildings', 0)}",
        f"- Failed: {state.get('failed_buildings', 0)}",
        f"- Skipped/resumed: {state.get('skipped_buildings', 0)}",
        f"- Current building: `{state.get('current_building_id') or 'none'}`",
        f"- Background PID: `{state.get('background_pid') or 'not started'}`",
        "",
        f"> {SCIENTIFIC_STATUS}",
    ]
    if note:
        text.extend(["", note])
    atomic_text(output_root(config) / "STATUS.md", "\n".join(text) + "\n")


def collect_result_files(root: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    successes: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    for path in sorted(root.glob("*.json")):
        try:
            row = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if row.get("processing_status") == "success":
            successes.append(row)
        else:
            failures.append(row)
    return successes, failures


def update_progress(config: dict[str, Any], results_root: Path, stage: str) -> tuple[int, int]:
    successes, failures = collect_result_files(results_root)
    rows = [
        {
            "building_id": row.get("building_id"),
            "status": row.get("processing_status"),
            "stage": stage,
            "reason": row.get("processing_reason", ""),
            "updated_at": row.get("completed_at", ""),
        }
        for row in [*successes, *failures]
    ]
    atomic_csv(output_root(config) / "progress.csv", rows, ["building_id", "status", "stage", "reason", "updated_at"])
    return len(successes), len(failures)


def process_ids(config: dict[str, Any], ids: list[str], full_batch: bool, resume: bool) -> list[dict[str, Any]]:
    root = output_root(config)
    results_root = REPO / config["outputs"]["per_building_root"] if full_batch else root / "dry_run" / "building_results"
    results_root.mkdir(parents=True, exist_ok=True)
    existing = load_existing_diagnostics(config)
    skipped = 0
    for building_id in ids:
        destination = results_root / f"{building_id}.json"
        if resume and result_valid(destination, building_id):
            skipped += 1
            continue
        if full_batch:
            successes, failures = update_progress(config, results_root, "N3_FULL_BATCH")
            state = update_state(
                config,
                current_stage="N3_FULL_BATCH",
                stage_status="running",
                processed_buildings=successes + failures,
                successful_buildings=successes,
                failed_buildings=failures,
                skipped_buildings=skipped,
                current_building_id=building_id,
            )
            write_status(config, state, "Per-building result files are written atomically after each completed building.")
        try:
            with building_timeout(int(config["processing"]["per_building_timeout_seconds"])):
                row = compute_building(config, building_id, existing.get(building_id))
        except Exception as exc:  # unattended: record and continue
            row = {
                "schema": SCHEMA,
                "run_id": config["run_id"],
                "building_id": building_id,
                "processing_status": "failed",
                "processing_reason": f"{type(exc).__name__}: {exc}",
                "traceback": traceback.format_exc(),
                "scientific_status": SCIENTIFIC_STATUS,
                "completed_at": now(),
            }
        write_building_result(destination, row)
    successes, failures = collect_result_files(results_root)
    if not full_batch:
        atomic_csv(root / "dry_run" / "dry_run_summary.csv", [*successes, *failures])
    return [*successes, *failures]


def git_head() -> str:
    process = subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO, text=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, check=False)
    return process.stdout.strip() or "unknown"


def write_plots(root: Path, rows: list[dict[str, Any]]) -> list[str]:
    plot_root = root / "plots"
    plot_root.mkdir(parents=True, exist_ok=True)
    written: list[str] = []

    def scatter(xkey: str, ykey: str, name: str, xlabel: str, ylabel: str, color_by_r: bool = False) -> None:
        pairs = [(number(row.get(xkey)), number(row.get(ykey)), row.get("provisional_R_final", "RX")) for row in rows]
        pairs = [value for value in pairs if finite(value[0]) and finite(value[1])]
        fig, ax = plt.subplots(figsize=(6.4, 5.0))
        palette = {"R0": "#2ca02c", "R1": "#1f77b4", "R2": "#ff7f0e", "R3": "#d62728", "RX": "#7f7f7f"}
        if pairs:
            colors = [palette.get(label, "#7f7f7f") for _x, _y, label in pairs] if color_by_r else "#3366aa"
            ax.scatter([value[0] for value in pairs], [value[1] for value in pairs], c=colors, s=18, alpha=0.8)
        ax.set_xlabel(xlabel)
        ax.set_ylabel(ylabel)
        ax.grid(alpha=0.2)
        fig.tight_layout()
        path = plot_root / name
        fig.savefig(path, dpi=160)
        plt.close(fig)
        written.append(str(path.relative_to(root)))

    scatter("surface_score", "lod2_score", "surface_score_vs_lod2_score.png", "surface score", "LoD2 score", True)
    scatter("surface_fscore_0p2m", "bidirectional_distance_p95_m", "fscore02_vs_distance_p95.png", "F-score @ 0.2 m", "bidirectional p95 (m)")
    scatter("roof_plane_f1", "rmsz_m", "roof_plane_f1_vs_rmsz.png", "roof-plane F1", "RMSZ (m)")
    scatter("surface_fscore_0p2m", "roof_plane_f1", "surface_fscore02_vs_roof_plane_f1.png", "surface F-score @ 0.2 m", "roof-plane F1")

    labels = ["R0", "R1", "R2", "R3", "RX"]
    counts = [sum(row.get("provisional_R_final") == label for row in rows) for label in labels]
    fig, ax = plt.subplots(figsize=(6.4, 4.3))
    ax.bar(labels, counts, color=["#2ca02c", "#1f77b4", "#ff7f0e", "#d62728", "#7f7f7f"])
    ax.set_ylabel("building count")
    ax.set_title("Provisional R_v1 counts")
    fig.tight_layout()
    path = plot_root / "r_counts.png"
    fig.savefig(path, dpi=160)
    plt.close(fig)
    written.append(str(path.relative_to(root)))

    stable_counts = [sum(row.get(f"provisional_R_q{q}") == row.get("provisional_R_final") and row.get("provisional_R_final") != "RX" for row in rows) for q in (40, 50, 60)]
    fig, ax = plt.subplots(figsize=(6.4, 4.3))
    ax.bar(["q40", "q50", "q60"], stable_counts, color="#5b8ff9")
    ax.set_ylabel("rows agreeing with stable final R")
    ax.set_title("q40/q50/q60 label stability")
    fig.tight_layout()
    path = plot_root / "q_label_stability.png"
    fig.savefig(path, dpi=160)
    plt.close(fig)
    written.append(str(path.relative_to(root)))

    area_rows = [row for row in rows if finite(row.get("footprint_area_m2"))]
    if area_rows:
        areas = np.asarray([float(row["footprint_area_m2"]) for row in area_rows])
        q1, q2 = np.quantile(areas, [1 / 3, 2 / 3])
        groups = {"small": [], "medium": [], "large": []}
        for row in area_rows:
            area = float(row["footprint_area_m2"])
            group = "small" if area <= q1 else ("medium" if area <= q2 else "large")
            groups[group].append(row)
        fig, ax = plt.subplots(figsize=(7.2, 4.6))
        bottom = np.zeros(3)
        x = np.arange(3)
        for label, color in zip(labels, ["#2ca02c", "#1f77b4", "#ff7f0e", "#d62728", "#7f7f7f"]):
            values = np.asarray([sum(row.get("provisional_R_final") == label for row in groups[group]) for group in ("small", "medium", "large")])
            ax.bar(x, values, bottom=bottom, label=label, color=color)
            bottom += values
        ax.set_xticks(x, ["small", "medium", "large"])
        ax.set_ylabel("building count")
        ax.legend(ncol=5, fontsize=8)
        fig.tight_layout()
        path = plot_root / "r_by_building_area.png"
        fig.savefig(path, dpi=160)
        plt.close(fig)
        written.append(str(path.relative_to(root)))
    return written


def resolve_existing_views(config: dict[str, Any], building_id: str) -> tuple[list[str], str]:
    pattern = config["sources"].get("existing_per_building_views_glob", "").format(building_id=building_id)
    matches = sorted(glob.glob(str(REPO / pattern)))
    for path_text in reversed(matches):
        path = Path(path_text)
        with path.open(newline="", encoding="utf-8") as handle:
            names = [row.get("image_name", "") for row in csv.DictReader(handle)]
        names = [name for name in names if name]
        if names:
            return list(dict.fromkeys(names)), str(path.relative_to(REPO))
    return [], "unknown: no existing per-building visibility list found"


def export_candidates(config: dict[str, Any], rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    root = output_root(config)
    candidate_root = REPO / config["outputs"]["candidate_root"]
    candidate_root.mkdir(parents=True, exist_ok=True)
    exported: list[dict[str, Any]] = []
    for label in ("R0", "R1", "R2", "R3", "RX"):
        group = [row for row in rows if row.get("provisional_R_final") == label and row.get("processing_status") == "success"]
        if not group:
            continue
        surface_center = float(np.nanmedian([number(row.get("surface_score")) for row in group]))
        lod2_center = float(np.nanmedian([number(row.get("lod2_score")) for row in group]))
        area_values = np.asarray([number(row.get("footprint_area_m2")) for row in group], dtype=float)
        finite_area = area_values[np.isfinite(area_values)]
        area_center = float(np.median(finite_area)) if len(finite_area) else math.nan

        def center_distance(row: Mapping[str, Any]) -> float:
            values = []
            if finite(row.get("surface_score")) and finite(surface_center):
                values.append((float(row["surface_score"]) - surface_center) ** 2)
            if finite(row.get("lod2_score")) and finite(lod2_center):
                values.append((float(row["lod2_score"]) - lod2_center) ** 2)
            area_penalty = 0.0
            if finite(row.get("footprint_area_m2")) and finite(area_center) and area_center > 0:
                area_penalty = 0.05 * abs(math.log(max(float(row["footprint_area_m2"]), 1e-6) / area_center))
            return math.sqrt(sum(values)) + area_penalty if values else 1e6 + area_penalty

        selected = sorted(group, key=lambda row: (center_distance(row), row["building_id"]))[:3]
        for row in selected:
            building_id = row["building_id"]
            views, view_source = resolve_existing_views(config, building_id)
            cache_footprint = REPO / config["outputs"]["cache_root"] / building_id / "footprint.json"
            footprint = json.loads(cache_footprint.read_text(encoding="utf-8")) if cache_footprint.is_file() else {}
            payload = {
                "schema": "jointbuildgs.tum2twin_rv1.local_scene_draft.v1",
                "run_id": config["run_id"],
                "provisional_R_final": label,
                "building_id": building_id,
                "selection_role": "group-center representative for follow-up only",
                "scientific_status": SCIENTIFIC_STATUS,
                "footprint_reference": config["sources"]["footprints"],
                "footprint_wkt": footprint.get("wkt"),
                "footprint_buffer_m": config["processing"]["crop_buffer_m"],
                "image_list": views,
                "image_list_source": view_source,
                "image_list_status": "resolved_existing" if views else "unknown",
                "global_camera_pose_reference": config["sources"]["camera_pose_manifest"],
                "preserve_global_camera_poses": True,
                "image_directory_reference": config["sources"]["image_directory"],
                "source_data_copy": False,
                "gs_training_started": False,
                "prior_loss_started": False,
            }
            destination = candidate_root / label / f"{building_id}.json"
            atomic_json(destination, payload)
            exported.append(
                {
                    "provisional_R_final": label,
                    "building_id": building_id,
                    "center_distance": center_distance(row),
                    "footprint_area_m2": row.get("footprint_area_m2"),
                    "image_list_status": payload["image_list_status"],
                    "image_count": len(views),
                    "config_path": str(destination.relative_to(root)),
                    "scientific_status": SCIENTIFIC_STATUS,
                }
            )
    atomic_csv(candidate_root / "candidate_manifest.csv", exported)
    return exported


def write_report_outputs(config: dict[str, Any], rows: list[dict[str, Any]], failures: list[dict[str, Any]]) -> dict[str, Any]:
    root = output_root(config)
    classified, sensitivity, thresholds = classify_rows(rows, config["processing"]["quantile_sensitivity"])
    atomic_csv(root / "building_metrics.csv", classified)
    atomic_json(root / "building_metrics.json", {"scientific_status": SCIENTIFIC_STATUS, "run_id": config["run_id"], "buildings": classified})
    class_fields = [
        "building_id", "surface_score", "surface_score_confidence", "surface_axis", "lod2_score", "lod2_score_confidence", "lod2_axis",
        "provisional_R_q40", "provisional_R_q50", "provisional_R_q60", "provisional_R_stable", "provisional_R_final",
        "classification_confidence", "classification_reason", "scientific_status",
    ]
    atomic_csv(root / "provisional_classification.csv", classified, class_fields)
    atomic_csv(root / "classification_sensitivity.csv", sensitivity)
    atomic_csv(root / "failed_buildings.csv", failures, ["building_id", "processing_status", "processing_reason", "completed_at", "scientific_status"])
    parquet_created = False
    parquet_reason = "pyarrow unavailable in existing containers; no package installed"
    if config["outputs"].get("write_parquet_if_available") and importlib.util.find_spec("pyarrow") is not None:
        try:
            import pandas as pd

            pd.DataFrame(classified).to_parquet(root / "building_metrics.parquet", index=False)
            parquet_created = True
            parquet_reason = "created with existing pyarrow"
        except Exception as exc:
            parquet_reason = f"existing parquet writer failed: {type(exc).__name__}: {exc}"
    plots = write_plots(root, classified)
    candidates = export_candidates(config, classified)
    counts = {label: sum(row.get("provisional_R_final") == label for row in classified) for label in ("R0", "R1", "R2", "R3", "RX")}
    summary = [
        "# TUM2TWIN provisional R_v1 classification summary",
        "",
        f"> {SCIENTIFIC_STATUS}",
        "",
        f"- Run ID: `{config['run_id']}`",
        f"- Processed successfully: {len(classified)}",
        f"- Processing failures: {len(failures)}",
        f"- Final counts: {counts}",
        f"- Quantile thresholds: `{json.dumps(thresholds, sort_keys=True)}`",
        f"- Appearance: not evaluated — {config['appearance']['missing_reason']}",
        f"- Parquet: {'created' if parquet_created else 'not created'} — {parquet_reason}",
        f"- Candidate drafts: {len(candidates)}; unresolved image lists remain explicitly unknown.",
        "",
        "Diagnostics are explanatory only and never override an R label. The nine PDF IDs were processed as parser/sanity cases with no expected label.",
    ]
    atomic_text(root / "classification_summary.md", "\n".join(summary) + "\n")
    metadata = {
        "schema": "jointbuildgs.tum2twin_rv1.run_metadata.v1",
        "run_id": config["run_id"],
        "scientific_status": SCIENTIFIC_STATUS,
        "provisional": True,
        "git_head": git_head(),
        "completed_at": now(),
        "population_count": 178,
        "successful_buildings": len(classified),
        "failed_buildings": len(failures),
        "classification_counts": counts,
        "quantile_thresholds": thresholds,
        "parquet_created": parquet_created,
        "parquet_reason": parquet_reason,
        "appearance_evaluated": False,
        "appearance_reason": config["appearance"]["missing_reason"],
        "plots": plots,
        "candidate_count": len(candidates),
        "source_data_modified": False,
        "gs_training_started": 0,
        "new_prior_loss_runs": 0,
        "container_compute": "jointbuildgs:dev",
        "cache_container": "jointbuildgs-p0-tools:t0",
    }
    atomic_json(root / "run_metadata.json", metadata)
    return metadata


def full_batch(config: dict[str, Any], resume: bool) -> None:
    population = load_population(config)
    process_ids(config, population, full_batch=True, resume=resume)
    results_root = REPO / config["outputs"]["per_building_root"]
    successes, failures = collect_result_files(results_root)
    success_count, failure_count = update_progress(config, results_root, "N3_FULL_BATCH")
    state = update_state(
        config,
        current_stage="N4_REPORT",
        stage_status="running",
        processed_buildings=success_count + failure_count,
        successful_buildings=success_count,
        failed_buildings=failure_count,
        current_building_id=None,
    )
    write_status(config, state, "Batch measurement ended; report and candidate export are running.")
    metadata = write_report_outputs(config, successes, failures)
    state = update_state(
        config,
        current_stage="DONE",
        stage_status="completed",
        processed_buildings=success_count + failure_count,
        successful_buildings=success_count,
        failed_buildings=failure_count,
        current_building_id=None,
        error_summary=[row.get("processing_reason") for row in failures[:20]],
    )
    write_status(config, state, "N4 report and N5 candidate export completed automatically.")
    atomic_json(output_root(config) / "DONE", {"completed_at": now(), "run_id": config["run_id"], "metadata": metadata})


def dry_run_preflight(config: dict[str, Any]) -> None:
    population = load_population(config)
    required = [
        REPO / config["sources"]["footprints"],
        REPO / config["sources"]["dense_mvs_pointcloud"],
        *(REPO / path for path in config["sources"]["surface_reference_pointclouds"]),
        REPO / config["sources"]["roofer_status"],
        REPO / config["sources"]["roofer_cityjson"],
    ]
    missing = [str(path) for path in required if not path.is_file()]
    recon = np.asarray([[0, 0, 0], [1, 0, 0]], dtype=float)
    ref = np.asarray([[0.05, 0, 0], [1.30, 0, 0]], dtype=float)
    d1 = nearest_distances(recon, ref)
    d2 = nearest_distances(ref, recon)
    precision, recall, fscore = precision_recall_fscore(d1, d2, 0.1)
    payload = {
        "schema": "jointbuildgs.tum2twin_rv1.dry_run_preflight.v1",
        "run_id": config["run_id"],
        "population_count": len(population),
        "required_source_missing": missing,
        "synthetic_precision_0p1m": precision,
        "synthetic_recall_0p1m": recall,
        "synthetic_fscore_0p1m": fscore,
        "status": "passed" if not missing else "failed",
        "scientific_status": SCIENTIFIC_STATUS,
        "timestamp": now(),
    }
    atomic_json(output_root(config) / "dry_run" / "preflight.json", payload)
    if missing:
        raise RuntimeError(f"dry-run preflight missing sources: {missing}")


def heartbeat_loop(config: dict[str, Any]) -> None:
    interval = max(10, int(config["processing"]["heartbeat_interval_seconds"]))
    active = True

    def stop(_signum: int, _frame: Any) -> None:
        nonlocal active
        active = False

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    while active:
        state = load_state(config)
        update_state(config, **{key: value for key, value in state.items() if key not in {"last_heartbeat"}})
        time.sleep(interval)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--ids", nargs="+")
    mode.add_argument("--all", action="store_true")
    mode.add_argument("--report-only", action="store_true")
    mode.add_argument("--heartbeat-loop", action="store_true")
    mode.add_argument("--register-background-pid", type=int)
    mode.add_argument("--set-stage")
    parser.add_argument("--stage-status", default="running")
    parser.add_argument("--resume", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = read_config((REPO / args.config).resolve())
    if args.register_background_pid is not None:
        state = update_state(config, background_pid=args.register_background_pid)
        write_status(config, state)
    elif args.set_stage:
        state = update_state(config, current_stage=args.set_stage, stage_status=args.stage_status)
        write_status(config, state)
    elif args.heartbeat_loop:
        heartbeat_loop(config)
    elif args.dry_run:
        dry_run_preflight(config)
    elif args.ids:
        process_ids(config, args.ids, full_batch=False, resume=args.resume)
    elif args.all:
        full_batch(config, args.resume)
    elif args.report_only:
        successes, failures = collect_result_files(REPO / config["outputs"]["per_building_root"])
        write_report_outputs(config, successes, failures)


if __name__ == "__main__":
    main()
