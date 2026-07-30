#!/usr/bin/env python3
"""R1 boundary-map v2, learning-zero CPU preparation and reporting.

The commands in this module only read frozen attributes, prepare the fourteen
requested crop-pair measurements, fit a calibration-only rule tree, prepare
the fixed-pose FM queue, and write measurement tables/figures.  MASt3R
inference is isolated in ``boundary_map_v2_mast3r.py``.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
import math
import os
import random
import subprocess
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence

os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib")
os.environ.setdefault("XDG_CACHE_HOME", "/tmp")

import matplotlib
import numpy as np
from shapely.geometry import MultiPolygon, Polygon

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import Patch  # noqa: E402


REPO = Path(__file__).resolve().parents[3]
DOCS = REPO / "docs"
RUN_DIR = REPO / "phases/p2-gsjso/runs/boundary_and_robustness/20260718_boundary_map_v2"
OLD_RUN_DIR = REPO / "phases/p2-gsjso/runs/boundary_and_robustness/20260716_boundary_map"

METRICS = DOCS / "archive/boundary_map/v2/tables/boundary_map_v2_metrics.csv"
LADDER = DOCS / "archive/boundary_map/v2/tables/boundary_map_v2_ladder.csv"
CONFUSION = DOCS / "archive/boundary_map/v2/tables/boundary_map_v2_confusion.csv"
CASES = DOCS / "experiments/boundary_map/tables/boundary_map_v2_boundary_cases.csv"
CONDITIONAL = DOCS / "archive/boundary_map/v2/tables/boundary_map_v2_conditional_targets.csv"
MANIFEST = DOCS / "experiments/boundary_map/manifests/boundary_map_v2_manifest.json"
SUMMARY = DOCS / "archive/boundary_map/v2/reports/W_boundary_map_v2_summary_20260718.md"
FIGURE = DOCS / "archive/boundary_map/v2/figs/boundary_map_v2_ladder.png"

PREP_MANIFEST = RUN_DIR / "prepare_manifest.json"
PREP_METRICS = RUN_DIR / "prepared_metrics.csv"
CROP_JOBS = RUN_DIR / "crop_pair_jobs.json"
ALL_JOBS = RUN_DIR / "all_projection_jobs.json"
CROP_RESULTS = RUN_DIR / "crop_pair_results.csv"
CROP_PROGRESS = RUN_DIR / "crop_pair_progress.json"
CROP_RUN_MANIFEST = RUN_DIR / "crop_pair_manifest.json"
CROP_LOG = RUN_DIR / "crop_pair.log"
RULE_JSON = RUN_DIR / "decision_rule.json"
PRIMARY_CSV = RUN_DIR / "primary_predictions.csv"
FM_JOBS = RUN_DIR / "fm_jobs.json"
FM_RESULTS = RUN_DIR / "fm_retriangulation.csv"
FM_PROGRESS = RUN_DIR / "fm_progress.json"
FM_RUN_MANIFEST = RUN_DIR / "fm_manifest.json"
FM_LOG = RUN_DIR / "fm.log"
LOG = RUN_DIR / "run.log"
MAST3R_HELPER = Path(__file__).with_name("boundary_map_v2_mast3r.py")
OLD_BOUNDARY_SCRIPT = Path(__file__).with_name("overnight_boundary_map.py")
POPULATION_AUX_SCRIPT = REPO / "scripts/evidence_and_attributes/population_analysis/population_aux_v3.py"
PROJECTION_DATUM_SCRIPT = REPO / "src/geospatial/projection_datum.py"

SNAPSHOT = DOCS / "regression_input_snapshot.csv"
POINTS = DOCS / "pointcloud_attributes_v1_3.csv"
AUX_V4 = DOCS / "population_aux_v4.csv"
LOWTEX = DOCS / "lowtex_v5.csv"
LOWTEX_SCRIPT = REPO / "scripts/evidence_and_attributes/population_analysis/aux_v4b.py"
MANUAL = DOCS / "manual_review_judgments.csv"
FOOTPRINTS = REPO / "results/tum_transfer/analysis/footprints_aoi.geojson"
PROJECTION_DATUM = REPO / "configs/input_and_alignment/projection_datum.json"
OLD_METRICS = DOCS / "archive/boundary_map/v1/tables/boundary_map_metrics.csv"
OLD_SUPPORT = OLD_RUN_DIR / "boundary_map_support_metrics.csv"
OLD_MATCHES = OLD_RUN_DIR / "mast3r_correspondence.csv"
OLD_JOBS = OLD_RUN_DIR / "mast3r_jobs.json"
OLD_MAST3R_MANIFEST = OLD_RUN_DIR / "mast3r_manifest.json"

CALIBRATION_SEED = 20260718
SMALL_AREA_M2 = 50.0
FM_MIN_DEFAULT = 1
FM_MAX_VIEWS = 5
FM_MAX_PAIRS = 10
MODEL_REVISION = "06e7259f34c3060f322df5cb0c7b9094f57e41fc"
MODEL_SHA256 = "0a615eb05fa9db654050aa655945ee5696e7c6c1b7f93f1ee8c37249010f6feb"
MODEL_BYTES = 2_754_661_648
MODEL_CONFIG_SHA256 = "718eb93dc4f9e4332b60cc0041af962d712cbd346d7770ce35c5b22cff68eae4"

WELL = "well_textured"
TEXTURELESS = "textureless_correspondence_anchored"
OUTLINE = "outline_only"
UNOBSERVABLE = "unobservable"
SMALL = "indeterminate_small"
EXPECTED_LABELS = (WELL, TEXTURELESS, OUTLINE)

REPAIR_14 = {
    f"DEBY_LOD2_{value}"
    for value in (
        "104583447", "104586480", "108246888", "42364609", "4908023",
        "4908024", "4908025", "4908026", "4908027", "4908028", "4908166",
        "4908352", "4908354", "8568403",
    )
}

FEATURES = (
    "texture_low_gradient_fraction",
    "texture_grad_p10",
    "dense_point_count",
    "dense_point_density_m2",
    "coverage_frac",
    "n_views_nadir",
    "frac_views_incidence_le60",
    "recon_score_median",
    "footprint_area_m2",
)

METRIC_FIELDS = [
    "building_id", "population_scope", "population_difference_status",
    "footprint_area_m2", "small_lt50", "texture_low_gradient_fraction",
    "texture_grad_p10", "texture_valid", "texture_view", "dense_point_count",
    "dense_point_density_m2", "dense_zero_points_recode", "coverage_frac",
    "coverage_zero_points_recode", "n_views_nadir",
    "frac_views_incidence_le60", "recon_score_median", "dense_assembled",
    "outline_inframe_frac_max", "outline_inframe_frac_median",
    "outline_valid_pixel_count_max", "outline_valid_pixel_count_median",
    "representative_view_count", "representative_views_json",
    "projection_status", "projection_reference_height_m",
    "projection_reference_height_used", "projection_reference_source",
    "crop_pair_correspondence_count", "crop_pair_reciprocal_raw_count",
    "crop_pair_border_count", "crop_pair_status", "crop_pair_view_a",
    "crop_pair_view_b", "crop_pair_model_revision", "crop_pair_model_sha256",
    "fm_status", "fm_view_a", "fm_view_b", "fm_baseline_m",
    "fm_selected_pair_count", "fm_completed_pair_count",
    "fm_successful_pair_count", "fm_excluded_pair_count",
    "fm_failed_pair_count",
    "fm_pending_pair_count", "fm_pair_status_json", "fm_pooling_rule",
    "fm_reprojection_pass_count", "fm_correspondence_count",
    "fm_z_median_m", "fm_z_mad_m", "fm_score",
    "fm_vertical_datum", "fm_projection_geoid_m",
    "fm_projection_datum_config_sha256",
    "feature_sources_json", "crs", "learning_runs_started",
    "new_inference_type",
]

LADDER_FIELDS = [
    "building_id", *FEATURES, "manual_split", "expected_tier",
    "primary_assignment", "primary_rule_path", "fm_status",
    "fm_selected_pair_count", "fm_successful_pair_count",
    "fm_excluded_pair_count",
    "fm_failed_pair_count", "fm_pending_pair_count",
    "fm_correspondence_count", "fm_z_median_m", "fm_z_mad_m", "fm_score",
    "fm_count_threshold", "outline_observable", "formula_assignment",
    "map_assignment", "assignment_record_status",
    "conditional_generation_target", "dense_assembled",
    "calibration_seed", "learning_runs_started",
]

CONFUSION_FIELDS = [
    "record_type", "comparison", "subset", "actual_label", "recorded_label",
    "count", "n_records", "correct_count", "accuracy",
    "constant_accuracy", "accuracy_gain", "calibration_seed",
    "rule_sha256", "evaluation_status", "learning_runs_started",
]

CASE_FIELDS = [
    "building_id", "manual_split", "expected_tier", "primary_assignment",
    "formula_assignment", "map_assignment", "fm_status",
    "fm_correspondence_count", "fm_count_threshold", "fm_z_median_m",
    "fm_score", "outline_observable", "spotcheck_reason",
    "primary_boundary_margin_normalized", "nearest_primary_predicate",
    "learning_runs_started",
]


def _load_old() -> Any:
    path = OLD_BOUNDARY_SCRIPT
    spec = importlib.util.spec_from_file_location("boundary_map_v1_locked", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot import {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def rel(path: Path | str) -> str:
    value = Path(path)
    try:
        return str(value.resolve().relative_to(REPO.resolve()))
    except ValueError:
        return str(value.resolve())


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def sha256_file(path: Path, block_size: int = 1 << 20) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(block_size), b""):
            digest.update(block)
    return digest.hexdigest()


def sha256_json(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def fmt(value: Any) -> Any:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        return f"{value:.6f}" if math.isfinite(value) else ""
    return value


def as_float(value: Any) -> float | None:
    try:
        output = float(value)
    except (TypeError, ValueError):
        return None
    return output if math.isfinite(output) else None


def as_int(value: Any) -> int | None:
    number = as_float(value)
    return int(round(number)) if number is not None else None


def as_bool(value: Any) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "y", "pass"}


def atomic_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(text, encoding="utf-8")
    temporary.replace(path)


def atomic_json(path: Path, payload: Any) -> None:
    atomic_text(path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


def atomic_csv(path: Path, rows: Sequence[dict[str, Any]], fields: Sequence[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    with temporary.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=list(fields), extrasaction="ignore", lineterminator="\n"
        )
        writer.writeheader()
        writer.writerows([{key: fmt(row.get(key)) for key in fields} for row in rows])
    temporary.replace(path)


def log(message: str) -> None:
    line = f"{now()} {message}"
    print(line, flush=True)
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")


def git_value(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=REPO, text=True).strip()


def expected_tier(label: str) -> str:
    if label == "무텍스처":
        return TEXTURELESS
    if "재질" in label or "저조도" in label:
        return OUTLINE
    return WELL


def stratified_split(
    manual_rows: Sequence[dict[str, str]],
) -> tuple[set[str], set[str], dict[str, str], dict[str, dict[str, int]]]:
    expected = {row["building_id"]: expected_tier(row["label"]) for row in manual_rows}
    grouped: dict[str, list[str]] = defaultdict(list)
    for bid, label in expected.items():
        grouped[label].append(bid)
    if {key: len(value) for key, value in grouped.items()} != {
        WELL: 34, TEXTURELESS: 4, OUTLINE: 6
    }:
        raise RuntimeError("manual expected-tier distribution drift")
    calibration: set[str] = set()
    validation: set[str] = set()
    inventory: dict[str, dict[str, int]] = {}
    for index, label in enumerate(EXPECTED_LABELS):
        ids = sorted(grouped[label])
        random.Random(CALIBRATION_SEED + index).shuffle(ids)
        cut = len(ids) // 2
        calibration.update(ids[:cut])
        validation.update(ids[cut:])
        inventory[label] = {"calibration": cut, "validation": len(ids) - cut}
    if len(calibration) != 22 or len(validation) != 22:
        raise RuntimeError("stratified manual split is not 22/22")
    if inventory[TEXTURELESS] != {"calibration": 2, "validation": 2}:
        raise RuntimeError("textureless split is not 2/2")
    return calibration, validation, expected, inventory


def canonical_population() -> tuple[set[str], dict[str, Any]]:
    rows = read_csv(SNAPSHOT)
    raw_lidar = [row for row in rows if row.get("arm") == "raw_lidar"]
    raw_dense = [row for row in rows if row.get("arm") == "raw_dense"]
    if len(raw_lidar) != 199 or len(raw_dense) != 199:
        raise RuntimeError("regression snapshot arm population drift")
    canonical = {row["building_id"] for row in raw_lidar if as_bool(row.get("assembled"))}
    dense_success = {row["building_id"] for row in raw_dense if as_bool(row.get("assembled"))}
    if len(canonical) != 178 or len(dense_success & canonical) != 114:
        raise RuntimeError("canonical 178 or dense 114/64 invariant failed")
    return canonical, {
        "raw_lidar_population": 199,
        "raw_lidar_assembled_true": len(canonical),
        "raw_lidar_assembled_false": 199 - len(canonical),
        "dense_success_in_canonical": len(dense_success & canonical),
        "dense_failure_in_canonical": len(canonical - dense_success),
    }


def projection_for_building(
    old: Any,
    bid: str,
    geom: Polygon | MultiPolygon,
    roof_z: float,
    cameras: Sequence[Any],
    width: int,
    height: int,
    params: np.ndarray,
    scene_ref: dict[str, Any],
    priority_rank: int,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    samples = old.boundary_samples(geom, old.BOUNDARY_STEP_M)
    candidates = []
    for camera in cameras:
        measured = old.projected_view(
            geom, roof_z, samples, camera, width, height, params, scene_ref
        )
        if measured is not None:
            candidates.append(measured)
    selected, selection_status = old.select_views(candidates)
    fractions = [row["inframe_frac"] for row in selected]
    pixels = [row["valid_pixel_count"] for row in selected]
    representative = [
        {
            "name": row["name"],
            "zenith_deg": round(float(row["zenith_deg"]), 6),
            "outline_inframe_frac": round(float(row["inframe_frac"]), 6),
            "outline_valid_pixel_count": int(row["valid_pixel_count"]),
        }
        for row in selected
    ]
    measurement = {
        "outline_inframe_frac_max": max(fractions) if fractions else None,
        "outline_inframe_frac_median": float(np.median(fractions)) if fractions else None,
        "outline_valid_pixel_count_max": max(pixels) if pixels else None,
        "outline_valid_pixel_count_median": float(np.median(pixels)) if pixels else None,
        "representative_view_count": len(selected),
        "representative_views_json": json.dumps(
            representative, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ),
        "projection_status": "prepared" if len(selected) >= 2 else selection_status,
        "projection_reference_height_m": roof_z,
    }
    if len(selected) < 2:
        return measurement, None
    left, right = selected[:2]
    job = {
        "building_id": bid,
        "evaluation_scope": "canonical_178",
        "priority_group": "repair_14",
        "priority_rank": priority_rank,
        "view_a": left["name"],
        "view_b": right["name"],
        "image_a": left["image_path"],
        "image_b": right["image_path"],
        "crop_a_xyxy": list(old.crop_box_4x3(left["all_uv"], width, height)),
        "crop_b_xyxy": list(old.crop_box_4x3(right["all_uv"], width, height)),
        "projected_rings_a": left["projected_rings"],
        "projected_rings_b": right["projected_rings"],
        "source_width": width,
        "source_height": height,
        "projection_reference_height_m": roof_z,
        "projection_reference_source": (
            "LoD2 CityGML; measurement/classification projection only"
        ),
        "learning_runs_started": 0,
    }
    return measurement, job


def fm_projection_pairs(
    old: Any,
    bid: str,
    geom: Polygon | MultiPolygon,
    roof_z: float,
    cameras: Sequence[Any],
    width: int,
    height: int,
    params: np.ndarray,
    scene_ref: dict[str, Any],
) -> list[dict[str, Any]]:
    """Prepare up to ten projected-footprint pairs without score-result feedback."""
    samples = old.boundary_samples(geom, old.BOUNDARY_STEP_M)
    usable: list[dict[str, Any]] = []
    for camera in cameras:
        measured = old.projected_view(
            geom, roof_z, samples, camera, width, height, params, scene_ref
        )
        if (
            measured is not None
            and measured["inframe_frac"] > 0.0
            and measured["valid_pixel_count"] >= 3
        ):
            usable.append(measured)
    usable.sort(
        key=lambda row: (
            -row["inframe_frac"],
            -row["valid_pixel_count"],
            row["zenith_deg"],
            row["name"],
        )
    )
    pool = usable[:FM_MAX_VIEWS]
    ranked: list[tuple[tuple[Any, ...], dict[str, Any], dict[str, Any]]] = []
    for left_index, left in enumerate(pool):
        for right in pool[left_index + 1:]:
            baseline = float(
                np.linalg.norm(
                    np.asarray(left["camera_center"], dtype=np.float64)
                    - np.asarray(right["camera_center"], dtype=np.float64)
                )
            )
            ranked.append(
                (
                    (
                        -min(left["inframe_frac"], right["inframe_frac"]),
                        -min(
                            left["valid_pixel_count"],
                            right["valid_pixel_count"],
                        ),
                        -baseline,
                        max(left["zenith_deg"], right["zenith_deg"]),
                        left["name"],
                        right["name"],
                    ),
                    left,
                    right,
                )
            )
    ranked.sort(key=lambda item: item[0])
    output = []
    for rank, (_key, left, right) in enumerate(
        ranked[:FM_MAX_PAIRS], start=1
    ):
        output.append(
            {
                "pair_rank": rank,
                "view_a": left["name"],
                "view_b": right["name"],
                "image_a": left["image_path"],
                "image_b": right["image_path"],
                "crop_a_xyxy": list(
                    old.crop_box_4x3(left["all_uv"], width, height)
                ),
                "crop_b_xyxy": list(
                    old.crop_box_4x3(right["all_uv"], width, height)
                ),
                "projected_rings_a": left["projected_rings"],
                "projected_rings_b": right["projected_rings"],
                "source_width": width,
                "source_height": height,
                "selection_min_outline_inframe_frac": min(
                    left["inframe_frac"], right["inframe_frac"]
                ),
                "selection_min_outline_valid_pixels": min(
                    left["valid_pixel_count"], right["valid_pixel_count"]
                ),
                "selection_camera_baseline_m": float(
                    np.linalg.norm(
                        np.asarray(left["camera_center"], dtype=np.float64)
                        - np.asarray(right["camera_center"], dtype=np.float64)
                    )
                ),
            }
        )
    return output


def prepare() -> None:
    """Create the canonical metrics table and the fourteen crop-pair jobs."""
    RUN_DIR.mkdir(parents=True, exist_ok=True)
    atomic_text(LOG, "")
    log("prepare start learning_runs_started=0")
    old = _load_old()
    canonical, checks = canonical_population()
    old_population = {row["building_id"] for row in read_csv(OLD_METRICS)}
    removed = sorted(old_population - canonical)
    added = sorted(canonical - old_population)
    if len(old_population) != 178 or len(removed) != 21 or len(added) != 21:
        raise RuntimeError("old-C/canonical symmetric difference is not 21+21")

    old_support = {row["building_id"]: row for row in read_csv(OLD_SUPPORT)}
    reused = canonical & set(old_support)
    missing = canonical - set(old_support)
    if len(reused) != 164 or missing != REPAIR_14:
        raise RuntimeError(
            f"reuse/new invariant failed: reused={len(reused)} missing={sorted(missing)}"
        )
    old_model = json.loads(
        OLD_MAST3R_MANIFEST.read_text(encoding="utf-8")
    ).get("model", {})
    expected_model = {
        "revision": MODEL_REVISION,
        "weights_sha256": MODEL_SHA256,
        "weights_bytes": MODEL_BYTES,
    }
    if old_model != expected_model:
        raise RuntimeError(
            f"20260716 MASt3R model lock mismatch: {old_model!r}"
        )

    snapshot_rows = read_csv(SNAPSHOT)
    dense = {
        row["building_id"]: row
        for row in snapshot_rows
        if row.get("arm") == "raw_dense"
    }
    point_rows = {
        row["building_id"]: row
        for row in read_csv(POINTS)
        if row.get("arm") == "raw_dense"
    }
    texture = {row["building_id"]: row for row in read_csv(LOWTEX)}
    aux_v4 = {row["building_id"]: row for row in read_csv(AUX_V4)}
    manual_rows = read_csv(MANUAL)
    calibration, validation, _expected, split_inventory = stratified_split(manual_rows)
    if not {row["building_id"] for row in manual_rows} <= canonical:
        raise RuntimeError("manual 44 is not a subset of canonical 178")

    geometries, areas = old.load_footprints()
    heights = old.load_reference_heights(REPAIR_14)
    scene_ref = json.loads(old.SCENE_REF.read_text(encoding="utf-8"))
    width, height, params = old.aux.parse_cam_model(old.CAMERAS)
    cameras = [
        camera
        for camera in old.aux.parse_cameras(old.IMAGES, scene_ref)
        if (old.IMAGE_DIR / camera.name).is_file()
    ]
    new_projection: dict[str, dict[str, Any]] = {}
    new_jobs: list[dict[str, Any]] = []
    for rank, bid in enumerate(sorted(REPAIR_14), start=1):
        measurement, job = projection_for_building(
            old, bid, geometries[bid], heights[bid], cameras, width, height,
            params, scene_ref, rank,
        )
        new_projection[bid] = measurement
        if job is not None:
            new_jobs.append(job)
        log(f"prepare repair={rank}/14 building={bid} job={job is not None}")
    failed_projection = sorted(
        bid for bid in REPAIR_14
        if new_projection[bid].get("projection_status") != "prepared"
    )

    old_match = {row["building_id"]: row for row in read_csv(OLD_MATCHES)}
    source_columns = {
        "texture_low_gradient_fraction": f"{rel(LOWTEX)}:roof_lowtex_v5",
        "texture_grad_p10": f"{rel(LOWTEX)}:roof_grad_p10_v5",
        "dense_point_count": f"{rel(POINTS)}:raw_dense.n_points_footprint",
        "dense_point_density_m2": f"{rel(POINTS)}:raw_dense.pt_density_m2",
        "coverage_frac": f"{rel(POINTS)}:raw_dense.coverage_frac",
        "n_views_nadir": f"{rel(AUX_V4)}:n_views_nadir",
        "frac_views_incidence_le60": f"{rel(AUX_V4)}:frac_views_incidence_le60",
        "recon_score_median": f"{rel(AUX_V4)}:recon_score_median",
        "footprint_area_m2": f"{rel(FOOTPRINTS)}:area_m2",
    }
    rows: list[dict[str, Any]] = []
    for bid in sorted(canonical):
        tex = texture[bid]
        point = point_rows[bid]
        obs = aux_v4[bid]
        dense_row = dense[bid]
        count = as_int(point.get("n_points_footprint"))
        zero = count == 0
        projection = (
            dict(old_support[bid]) if bid in old_support else new_projection[bid]
        )
        match = old_match.get(bid, {})
        row = {
            "building_id": bid,
            "population_scope": "canonical_raw_lidar_assembled_178",
            "population_difference_status": (
                "added_vs_20260716_C" if bid in added else "intersection_reused"
            ),
            "footprint_area_m2": areas[bid],
            "small_lt50": areas[bid] < SMALL_AREA_M2,
            "texture_low_gradient_fraction": as_float(tex.get("roof_lowtex_v5")),
            "texture_grad_p10": as_float(tex.get("roof_grad_p10_v5")),
            "texture_valid": tex.get("lowtex_valid", ""),
            "texture_view": tex.get("lowtex_v5_view", ""),
            "dense_point_count": count,
            "dense_point_density_m2": (
                0.0 if zero else as_float(point.get("pt_density_m2"))
            ),
            "dense_zero_points_recode": zero,
            "coverage_frac": 0.0 if zero else as_float(point.get("coverage_frac")),
            "coverage_zero_points_recode": zero,
            "n_views_nadir": as_float(obs.get("n_views_nadir")),
            "frac_views_incidence_le60": as_float(
                obs.get("frac_views_incidence_le60")
            ),
            "recon_score_median": as_float(obs.get("recon_score_median")),
            "dense_assembled": as_int(dense_row.get("assembled")),
            "outline_inframe_frac_max": as_float(
                projection.get("outline_inframe_frac_max")
            ),
            "outline_inframe_frac_median": as_float(
                projection.get("outline_inframe_frac_median")
            ),
            "outline_valid_pixel_count_max": as_int(
                projection.get("outline_valid_pixel_count_max")
            ),
            "outline_valid_pixel_count_median": as_float(
                projection.get("outline_valid_pixel_count_median")
            ),
            "representative_view_count": as_int(
                projection.get("representative_view_count")
            ),
            "representative_views_json": projection.get(
                "representative_views_json", ""
            ),
            "projection_status": projection.get("projection_status", ""),
            "projection_reference_height_m": as_float(
                projection.get("projection_reference_height_m")
            ),
            "projection_reference_height_used": True,
            "projection_reference_source": (
                "LoD2 CityGML; measurement/classification projection only"
            ),
            "crop_pair_correspondence_count": as_int(
                match.get("roof_correspondence_count")
            ),
            "crop_pair_reciprocal_raw_count": as_int(
                match.get("reciprocal_raw_count")
            ),
            "crop_pair_border_count": as_int(match.get("border_match_count")),
            "crop_pair_status": (
                match.get("status", "")
                if bid in reused
                else (
                    "projection_failed"
                    if bid in failed_projection else "pending_repair_14"
                )
            ),
            "crop_pair_view_a": (
                match.get("view_a", "")
                or projection.get("mast3r_view_a", "")
            ),
            "crop_pair_view_b": (
                match.get("view_b", "")
                or projection.get("mast3r_view_b", "")
            ),
            "crop_pair_model_revision": MODEL_REVISION,
            "crop_pair_model_sha256": MODEL_SHA256,
            "feature_sources_json": json.dumps(
                source_columns, sort_keys=True, separators=(",", ":")
            ),
            "crs": "EPSG:25832",
            "learning_runs_started": 0,
            "new_inference_type": (
                "R1-2 MASt3R crop-pair pending"
                if bid in REPAIR_14 else "none; frozen 20260716 crop-pair reused"
            ),
        }
        if any(row.get(feature) is None for feature in FEATURES):
            missing_features = [
                feature for feature in FEATURES if row.get(feature) is None
            ]
            raise RuntimeError(f"{bid} missing rule features {missing_features}")
        rows.append(row)

    old_jobs_payload = json.loads(OLD_JOBS.read_text(encoding="utf-8"))
    job_by_id = {
        job["building_id"]: dict(job) for job in old_jobs_payload.get("jobs", [])
    }
    for job in new_jobs:
        job_by_id[job["building_id"]] = job
    all_jobs = [job_by_id[bid] for bid in sorted(canonical) if bid in job_by_id]
    atomic_csv(PREP_METRICS, rows, METRIC_FIELDS)
    common_jobs = {
        "created_utc": now(),
        "model": {
            "revision": MODEL_REVISION,
            "weights_sha256": MODEL_SHA256,
            "weights_bytes": MODEL_BYTES,
            "config_sha256": MODEL_CONFIG_SHA256,
        },
        "crop_rule": (
            "projected footprint at LoD2 median roof height; 32px margin; "
            "exact 4:3; min 256x192; resize 512x384"
        ),
        "learning_runs_started": 0,
    }
    atomic_json(
        CROP_JOBS,
        {
            "schema": "jointbuildgs.boundary_map_v2.crop_pair_jobs.v1",
            **common_jobs,
            "requested_building_count": 14,
            "projectable_job_count": len(new_jobs),
            "unprojectable_buildings": failed_projection,
            "jobs": new_jobs,
        },
    )
    atomic_json(
        ALL_JOBS,
        {
            "schema": "jointbuildgs.boundary_map_v2.all_projection_jobs.v1",
            **common_jobs,
            "missing_projection_jobs": sorted(canonical - set(job_by_id)),
            "jobs": all_jobs,
        },
    )
    prep = {
        "schema": "jointbuildgs.boundary_map_v2.prepare.v1",
        "created_utc": now(),
        "git_head_at_measurement": git_value("rev-parse", "HEAD"),
        "branch": git_value("branch", "--show-current"),
        "canonical_population_rule": (
            "docs/experiments/evaluation/attr_outcome_regression/tables/regression_input_snapshot.csv arm=raw_lidar and assembled=true"
        ),
        "population_checks": checks,
        "old_c_population": len(old_population),
        "symmetric_difference_count": len(removed) + len(added),
        "removed_from_20260716_C": removed,
        "added_to_canonical_178": added,
        "reused_measurement_count": len(reused),
        "repair_measurement_count": len(missing),
        "repair_buildings": sorted(missing),
        "repair_crop_pair_job_count": len(new_jobs),
        "repair_projection_incomplete_buildings": failed_projection,
        "repair_texture_measurement": {
            "row_count": len(missing),
            "source": rel(LOWTEX),
            "columns": ["roof_lowtex_v5", "roof_grad_p10_v5"],
            "measurement_code": rel(LOWTEX_SCRIPT),
            "reuse_status": "locked full-population lowtex_v5 rows reused",
        },
        "manual_split_seed": CALIBRATION_SEED,
        "manual_split_inventory": split_inventory,
        "manual_calibration_buildings": sorted(calibration),
        "manual_validation_buildings": sorted(validation),
        "source_sha256": {
            rel(path): sha256_file(path)
            for path in (
                SNAPSHOT, POINTS, AUX_V4, LOWTEX, LOWTEX_SCRIPT, MANUAL,
                FOOTPRINTS,
                PROJECTION_DATUM,
                OLD_METRICS, OLD_SUPPORT, OLD_MATCHES, OLD_JOBS,
                OLD_MAST3R_MANIFEST, OLD_BOUNDARY_SCRIPT,
                POPULATION_AUX_SCRIPT, PROJECTION_DATUM_SCRIPT,
                Path(__file__),
            )
        },
        "output_sha256": {
            rel(path): sha256_file(path)
            for path in (PREP_METRICS, CROP_JOBS, ALL_JOBS)
        },
        "mast3r_model_lock_matches_20260716": True,
        "mast3r_model": expected_model,
        "learning_runs_started": 0,
        "new_inference_runs": 0,
        "interpretation_or_verdict": None,
    }
    atomic_json(PREP_MANIFEST, prep)
    log(
        f"prepare complete canonical=178 reused={len(reused)} repair={len(missing)} "
        f"crop_jobs={len(new_jobs)} learning_runs_started=0"
    )


def predicate_candidates(
    rows: Sequence[dict[str, Any]],
) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for feature in FEATURES:
        values = sorted({float(row[feature]) for row in rows})
        thresholds = (
            [(left + right) / 2.0 for left, right in zip(values, values[1:])]
            if len(values) > 1 else values
        )
        for threshold in thresholds:
            output.append({"feature": feature, "op": "<=", "threshold": threshold})
    return output


def predicate_value(row: dict[str, Any], predicate: dict[str, Any]) -> bool:
    return float(row[predicate["feature"]]) <= float(predicate["threshold"])


def majority_leaf(
    rows: Sequence[dict[str, Any]], expected: dict[str, str]
) -> tuple[dict[str, str], int]:
    counts = Counter(expected[row["building_id"]] for row in rows)
    label = min(
        EXPECTED_LABELS,
        key=lambda item: (-counts[item], EXPECTED_LABELS.index(item)),
    )
    return {"label": label}, counts[label]


def best_branch(
    rows: Sequence[dict[str, Any]],
    expected: dict[str, str],
    predicates: Sequence[dict[str, Any]],
) -> tuple[dict[str, Any], int, int, str]:
    leaf, correct = majority_leaf(rows, expected)
    best = (leaf, correct, 0, json.dumps(leaf, sort_keys=True))
    for predicate in predicates:
        left = [row for row in rows if predicate_value(row, predicate)]
        right = [row for row in rows if not predicate_value(row, predicate)]
        if not left or not right:
            continue
        left_leaf, left_correct = majority_leaf(left, expected)
        right_leaf, right_correct = majority_leaf(right, expected)
        node = {"predicate": predicate, "le": left_leaf, "gt": right_leaf}
        serial = json.dumps(node, sort_keys=True, separators=(",", ":"))
        candidate = (node, left_correct + right_correct, 1, serial)
        if (-candidate[1], candidate[2], candidate[3]) < (
            -best[1], best[2], best[3]
        ):
            best = candidate
    return best


def fit_tree(
    rows: Sequence[dict[str, Any]], expected: dict[str, str]
) -> tuple[dict[str, Any], int]:
    predicates = predicate_candidates(rows)
    leaf, correct = majority_leaf(rows, expected)
    best_tree: dict[str, Any] = leaf
    best_key = (-correct, 0, 0, json.dumps(leaf, sort_keys=True))
    for root in predicates:
        left = [row for row in rows if predicate_value(row, root)]
        right = [row for row in rows if not predicate_value(row, root)]
        if not left or not right:
            continue
        left_tree, left_correct, left_depth, _ = best_branch(left, expected, predicates)
        right_tree, right_correct, right_depth, _ = best_branch(
            right, expected, predicates
        )
        tree = {"predicate": root, "le": left_tree, "gt": right_tree}
        score = left_correct + right_correct
        depth = 1 + max(left_depth, right_depth)
        predicate_count = 1 + left_depth + right_depth
        serial = json.dumps(tree, sort_keys=True, separators=(",", ":"))
        key = (-score, depth, predicate_count, serial)
        if key < best_key:
            best_key = key
            best_tree = tree
    return best_tree, -best_key[0]


def apply_tree(row: dict[str, Any], tree: dict[str, Any]) -> tuple[str, str]:
    node = tree
    path: list[str] = []
    while "label" not in node:
        predicate = node["predicate"]
        branch = "le" if predicate_value(row, predicate) else "gt"
        path.append(
            f"{predicate['feature']}{predicate['op']}{float(predicate['threshold']):.9g}:{branch}"
        )
        node = node[branch]
    return node["label"], "|".join(path)


def active_predicates(tree: dict[str, Any]) -> list[dict[str, Any]]:
    if "label" in tree:
        return []
    output = [tree["predicate"]]
    output.extend(active_predicates(tree["le"]))
    output.extend(active_predicates(tree["gt"]))
    unique = {
        (
            item["feature"],
            item["op"],
            float(item["threshold"]),
        ): item
        for item in output
    }
    return [unique[key] for key in sorted(unique)]


def fit_primary() -> None:
    """Fit the depth<=2 rule on the stratified calibration half only."""
    rows = read_csv(PREP_METRICS)
    if len(rows) != 178:
        raise RuntimeError("prepare must provide 178 metric rows")
    typed = [{**row, **{feature: float(row[feature]) for feature in FEATURES}} for row in rows]
    manual_rows = read_csv(MANUAL)
    calibration, validation, expected, inventory = stratified_split(manual_rows)
    calibration_rows = [
        row for row in typed if row["building_id"] in calibration
    ]
    tree, correct = fit_tree(calibration_rows, expected)
    predictions = []
    for row in typed:
        assignment, path = apply_tree(row, tree)
        bid = row["building_id"]
        predictions.append(
            {
                "building_id": bid,
                "manual_split": (
                    "calibration" if bid in calibration
                    else ("validation" if bid in validation else "not_manual")
                ),
                "expected_tier": expected.get(bid, ""),
                "primary_assignment": assignment,
                "primary_rule_path": path,
                "learning_runs_started": 0,
            }
        )
    primary_fields = [
        "building_id", "manual_split", "expected_tier", "primary_assignment",
        "primary_rule_path", "learning_runs_started",
    ]
    atomic_csv(PRIMARY_CSV, predictions, primary_fields)
    rule = {
        "schema": "jointbuildgs.boundary_map_v2.depth2_rule.v1",
        "created_utc": now(),
        "maximum_depth": 2,
        "objective": "calibration exact expected-tier agreement",
        "tie_break": (
            "higher exact count; shallower depth; fewer predicates; "
            "lexicographic serialized rule; leaf-count ties use "
            "well_textured, textureless_correspondence_anchored, outline_only order"
        ),
        "features": list(FEATURES),
        "feature_thresholds": "midpoints of calibration-only unique values",
        "zero_point_recode": (
            "raw_dense n_points_footprint=0 -> pt_density_m2=0 and coverage_frac=0; "
            "recode flags retained"
        ),
        "calibration_seed": CALIBRATION_SEED,
        "split_inventory": inventory,
        "calibration_buildings": sorted(calibration),
        "validation_buildings_locked_not_used_for_fit": sorted(validation),
        "calibration_correct": correct,
        "calibration_n": len(calibration_rows),
        "tree": tree,
        "tree_sha256": sha256_json(tree),
        "learning_runs_started": 0,
        "interpretation_or_verdict": None,
    }
    atomic_json(RULE_JSON, rule)

    prediction_by_id = {row["building_id"]: row for row in predictions}
    textureless_ids = {
        row["building_id"] for row in manual_rows if expected_tier(row["label"]) == TEXTURELESS
    }
    old = _load_old()
    c001_ids = set(old.C001_IDS)
    candidates = [
        bid for bid, row in prediction_by_id.items()
        if row["primary_assignment"] != WELL
    ]
    candidates.sort(
        key=lambda bid: (
            0 if bid in c001_ids else (1 if bid in textureless_ids else 2),
            bid,
        )
    )
    geometries, _areas = old.load_footprints()
    heights = old.load_reference_heights(set(candidates))
    scene_ref = json.loads(old.SCENE_REF.read_text(encoding="utf-8"))
    width, height, params = old.aux.parse_cam_model(old.CAMERAS)
    cameras = [
        camera
        for camera in old.aux.parse_cameras(old.IMAGES, scene_ref)
        if (old.IMAGE_DIR / camera.name).is_file()
    ]
    fm_jobs = []
    pending_without_job = []
    pair_counts: dict[str, int] = {}
    for rank, bid in enumerate(candidates, start=1):
        pairs = fm_projection_pairs(
            old, bid, geometries[bid], heights[bid], cameras, width, height,
            params, scene_ref,
        )
        pair_counts[bid] = len(pairs)
        if not pairs:
            pending_without_job.append(bid)
            continue
        fm_jobs.append(
            {
                "building_id": bid,
                "evaluation_scope": "canonical_178",
                "priority_rank": rank,
                "priority_group": (
                    "C001" if bid in c001_ids
                    else (
                        "manual_textureless"
                        if bid in textureless_ids else "remaining"
                    )
                ),
                "primary_assignment": prediction_by_id[bid][
                    "primary_assignment"
                ],
                "selected_pair_count": len(pairs),
                "pairs": pairs,
                "projection_reference_height_m": heights[bid],
                "projection_reference_source": (
                    "LoD2 CityGML; measurement/classification projection only"
                ),
                "learning_runs_started": 0,
            }
        )
    atomic_json(
        FM_JOBS,
        {
            "schema": "jointbuildgs.boundary_map_v2.fm_jobs.v1",
            "created_utc": now(),
            "selection_rule": "all primary assignments other than well_textured",
            "priority_rule": "C001, manual textureless labels, remaining candidates",
            "candidate_count": len(candidates),
            "job_count": len(fm_jobs),
            "selected_pair_count_total": sum(pair_counts.values()),
            "selected_pair_count_by_building": pair_counts,
            "pending_without_projection_job": pending_without_job,
            "model": {
                "revision": MODEL_REVISION,
                "weights_sha256": MODEL_SHA256,
                "weights_bytes": MODEL_BYTES,
                "config_sha256": MODEL_CONFIG_SHA256,
            },
            "fm_rule": (
                "up to five deterministic projected-footprint views and ten "
                "ranked view pairs per building; MASt3R reciprocal 2D matches "
                "only; crop coordinates inverted to raw FULL_OPENCV pixels; "
                "undistort; float64 fixed COLMAP-pose DLT; positive depths; "
                "distorted source-pixel reprojection <=2px; pool all completed "
                "nondegenerate pairs before footprint-inside z median and count"
            ),
            "view_rule": (
                "top five by outline in-frame fraction, outline valid pixels, "
                "zenith, image name"
            ),
            "pair_rule": (
                "up to ten unordered pairs ranked by minimum in-frame fraction, "
                "minimum outline pixels, 3D camera baseline, maximum zenith, names"
            ),
            "max_gpu_cpu_seconds": 21600,
            "jobs": fm_jobs,
            "learning_runs_started": 0,
            "new_inference_type": "R1-4 FM fixed-pose retriangulation only",
        },
    )
    log(
        f"fit-primary complete calibration={correct}/22 candidates={len(candidates)} "
        f"fm_jobs={len(fm_jobs)} learning_runs_started=0"
    )


def outline_observable(row: dict[str, Any]) -> bool:
    return (
        (as_int(row.get("representative_view_count")) or 0) >= 2
        and (as_float(row.get("outline_inframe_frac_max")) or 0.0) > 0.0
        and (as_int(row.get("outline_valid_pixel_count_max")) or 0) >= 3
    )


def final_formula(
    primary: str,
    fm_count: int | None,
    fm_threshold: int,
    observable: bool,
    fm_status: str,
) -> str:
    if primary == WELL:
        return WELL
    if fm_status != "complete":
        return UNOBSERVABLE
    if fm_count is not None and fm_count >= fm_threshold:
        return TEXTURELESS
    if observable:
        return OUTLINE
    return UNOBSERVABLE


def calibrate_fm_threshold(
    rows: Sequence[dict[str, Any]],
    primary: dict[str, dict[str, str]],
    expected: dict[str, str],
    calibration: set[str],
) -> tuple[int, int | None, list[int], list[str], str]:
    calibration_candidates = {
        bid for bid in calibration
        if primary[bid]["primary_assignment"] != WELL
    }
    row_by_id = {row["building_id"]: row for row in rows}
    incomplete = sorted(
        bid for bid in calibration_candidates
        if row_by_id[bid].get("fm_status") != "complete"
    )
    if incomplete:
        return (
            FM_MIN_DEFAULT,
            None,
            [FM_MIN_DEFAULT],
            incomplete,
            "pending_calibration_fm",
        )
    counts = sorted({
        as_int(row.get("fm_correspondence_count"))
        for row in rows
        if row["building_id"] in calibration
        and primary[row["building_id"]]["primary_assignment"] != WELL
        and row.get("fm_status") == "complete"
        and as_int(row.get("fm_correspondence_count")) is not None
    })
    candidates = sorted(
        {
            FM_MIN_DEFAULT,
            *[value for value in counts if value is not None and value >= 1],
            *[(value or 0) + 1 for value in counts],
        }
    )
    best = (math.inf, FM_MIN_DEFAULT, 0)
    for threshold in candidates:
        correct = 0
        for row in rows:
            bid = row["building_id"]
            if bid not in calibration:
                continue
            recorded = final_formula(
                primary[bid]["primary_assignment"],
                as_int(row.get("fm_correspondence_count")),
                int(threshold),
                outline_observable(row),
                str(row.get("fm_status", "")),
            )
            correct += int(recorded == expected[bid])
        key = (-correct, int(threshold), correct)
        if key < best:
            best = key
    return (
        int(best[1]),
        int(best[2]),
        [int(value) for value in candidates],
        [],
        "calibrated_complete",
    )


def matrix_rows(
    comparison: str,
    subset: str,
    pairs: Sequence[tuple[str, str]],
    rule_sha: str,
) -> list[dict[str, Any]]:
    counts = Counter(pairs)
    return [
        {
            "record_type": "confusion_cell",
            "comparison": comparison,
            "subset": subset,
            "actual_label": actual,
            "recorded_label": recorded,
            "count": count,
            "n_records": len(pairs),
            "calibration_seed": CALIBRATION_SEED,
            "rule_sha256": rule_sha,
            "learning_runs_started": 0,
        }
        for (actual, recorded), count in sorted(counts.items())
    ]


def make_map(
    geometries: dict[str, Polygon | MultiPolygon],
    ladder: Sequence[dict[str, Any]],
) -> None:
    colors = {
        WELL: "#2ca25f", TEXTURELESS: "#3182bd", OUTLINE: "#fdae6b",
        UNOBSERVABLE: "#de2d26", SMALL: "#969696",
    }
    figure, axis = plt.subplots(figsize=(13, 10), dpi=190)
    counts = Counter(row["map_assignment"] for row in ladder)
    for row in ladder:
        geom = geometries[row["building_id"]]
        polygons = [geom] if isinstance(geom, Polygon) else list(geom.geoms)
        for polygon in polygons:
            x, y = polygon.exterior.xy
            axis.fill(
                x, y, facecolor=colors[row["map_assignment"]],
                edgecolor="#303030", linewidth=0.28,
            )
    axis.set_aspect("equal")
    axis.ticklabel_format(style="plain", useOffset=False)
    axis.set_xlabel("Easting [m], EPSG:25832")
    axis.set_ylabel("Northing [m], EPSG:25832")
    axis.set_title("Boundary map v2 records (canonical 178)")
    axis.legend(
        handles=[
            Patch(
                facecolor=colors[label], edgecolor="#303030",
                label=f"{label} (n={counts[label]})",
            )
            for label in (WELL, TEXTURELESS, OUTLINE, UNOBSERVABLE, SMALL)
            if counts[label]
        ],
        fontsize=7,
        loc="best",
    )
    axis.grid(alpha=0.12)
    figure.tight_layout()
    FIGURE.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(FIGURE)
    plt.close(figure)


def finalize() -> None:
    """Merge completed crop/FM rows and write the requested public artifacts."""
    rows = [dict(row) for row in read_csv(PREP_METRICS)]
    if len(rows) != 178:
        raise RuntimeError("metrics population is not 178")
    crop_results = {row["building_id"]: row for row in read_csv(CROP_RESULTS)}
    fm_results = {row["building_id"]: row for row in read_csv(FM_RESULTS)}
    crop_progress = (
        json.loads(CROP_PROGRESS.read_text(encoding="utf-8"))
        if CROP_PROGRESS.is_file() else {}
    )
    fm_progress = (
        json.loads(FM_PROGRESS.read_text(encoding="utf-8"))
        if FM_PROGRESS.is_file() else {}
    )
    crop_budget_pending = set(crop_progress.get("pending_buildings", []))
    fm_budget_pending = set(fm_progress.get("pending_buildings", []))
    for row in rows:
        crop = crop_results.get(row["building_id"])
        if crop:
            row.update(
                {
                    "crop_pair_correspondence_count": as_int(
                        crop.get("roof_correspondence_count")
                    ),
                    "crop_pair_reciprocal_raw_count": as_int(
                        crop.get("reciprocal_raw_count")
                    ),
                    "crop_pair_border_count": as_int(crop.get("border_match_count")),
                    "crop_pair_status": crop.get("status", ""),
                    "crop_pair_view_a": crop.get("view_a", ""),
                    "crop_pair_view_b": crop.get("view_b", ""),
                }
            )
        elif row["building_id"] in crop_budget_pending:
            row["crop_pair_status"] = (
                "time_budget_reached"
                if crop_progress.get("status") == "time_budget_reached"
                else "pending"
            )
        fm = fm_results.get(row["building_id"])
        if fm:
            row.update(
                {
                    "fm_status": fm.get("status", ""),
                    "fm_view_a": fm.get("view_a", ""),
                    "fm_view_b": fm.get("view_b", ""),
                    "fm_baseline_m": as_float(fm.get("baseline_m")),
                    "fm_selected_pair_count": as_int(
                        fm.get("selected_pair_count")
                    ),
                    "fm_completed_pair_count": as_int(
                        fm.get("completed_pair_count")
                    ),
                    "fm_successful_pair_count": as_int(
                        fm.get("successful_pair_count")
                    ),
                    "fm_excluded_pair_count": as_int(
                        fm.get("excluded_pair_count")
                    ),
                    "fm_failed_pair_count": as_int(
                        fm.get("failed_pair_count")
                    ),
                    "fm_pending_pair_count": as_int(
                        fm.get("pending_pair_count")
                    ),
                    "fm_pair_status_json": fm.get("pair_status_json", ""),
                    "fm_pooling_rule": fm.get("pooling_rule", ""),
                    "fm_reprojection_pass_count": as_int(
                        fm.get("reprojection_pass_count")
                    ),
                    "fm_correspondence_count": as_int(
                        fm.get("footprint_inside_count")
                    ),
                    "fm_z_median_m": as_float(fm.get("footprint_z_median_m")),
                    "fm_z_mad_m": as_float(fm.get("footprint_z_mad_m")),
                    "fm_score": as_float(fm.get("footprint_inside_fraction_of_border")),
                    "fm_vertical_datum": fm.get("vertical_datum", ""),
                    "fm_projection_geoid_m": as_float(
                        fm.get("projection_geoid_m")
                    ),
                    "fm_projection_datum_config_sha256": fm.get(
                        "projection_datum_config_sha256", ""
                    ),
                }
            )
        elif row["building_id"] in fm_budget_pending:
            row["fm_status"] = (
                "time_budget_reached"
                if fm_progress.get("status") == "time_budget_reached"
                else "pending"
            )
    primary_rows = read_csv(PRIMARY_CSV)
    primary = {row["building_id"]: row for row in primary_rows}
    if len(primary) != 178:
        raise RuntimeError("primary prediction population is not 178")
    rule = json.loads(RULE_JSON.read_text(encoding="utf-8"))
    primary_rule_sha = rule["tree_sha256"]
    manual_rows = read_csv(MANUAL)
    calibration, validation, expected, split_inventory = stratified_split(
        manual_rows
    )
    (
        fm_threshold,
        calibration_correct,
        fm_threshold_candidates,
        fm_calibration_incomplete,
        fm_threshold_status,
    ) = calibrate_fm_threshold(rows, primary, expected, calibration)
    final_rule_payload = {
        "primary_tree_sha256": primary_rule_sha,
        "fm_count_threshold": fm_threshold,
        "fm_threshold_status": fm_threshold_status,
        "outline_observable": (
            "representative_view_count>=2 and outline_inframe_frac_max>0 "
            "and outline_valid_pixel_count_max>=3"
        ),
        "fm_incomplete_assignment": UNOBSERVABLE,
        "small_rule": f"footprint_area_m2<{SMALL_AREA_M2} -> {SMALL}",
    }
    rule_sha = sha256_json(final_rule_payload)
    ladder: list[dict[str, Any]] = []
    for row in sorted(rows, key=lambda item: item["building_id"]):
        bid = row["building_id"]
        observable = outline_observable(row)
        formula = final_formula(
            primary[bid]["primary_assignment"],
            as_int(row.get("fm_correspondence_count")),
            fm_threshold,
            observable,
            str(row.get("fm_status", "")),
        )
        assignment_status = (
            "complete"
            if primary[bid]["primary_assignment"] == WELL
            or row.get("fm_status") == "complete"
            else f"fm_incomplete:{row.get('fm_status') or 'missing'}"
        )
        map_assignment = (
            SMALL if float(row["footprint_area_m2"]) < SMALL_AREA_M2 else formula
        )
        ladder.append(
            {
                "building_id": bid,
                **{feature: as_float(row.get(feature)) for feature in FEATURES},
                "manual_split": primary[bid]["manual_split"],
                "expected_tier": primary[bid]["expected_tier"],
                "primary_assignment": primary[bid]["primary_assignment"],
                "primary_rule_path": primary[bid]["primary_rule_path"],
                "fm_status": row.get("fm_status", ""),
                "fm_selected_pair_count": as_int(
                    row.get("fm_selected_pair_count")
                ),
                "fm_successful_pair_count": as_int(
                    row.get("fm_successful_pair_count")
                ),
                "fm_excluded_pair_count": as_int(
                    row.get("fm_excluded_pair_count")
                ),
                "fm_failed_pair_count": as_int(
                    row.get("fm_failed_pair_count")
                ),
                "fm_pending_pair_count": as_int(
                    row.get("fm_pending_pair_count")
                ),
                "fm_correspondence_count": as_int(
                    row.get("fm_correspondence_count")
                ),
                "fm_z_median_m": as_float(row.get("fm_z_median_m")),
                "fm_z_mad_m": as_float(row.get("fm_z_mad_m")),
                "fm_score": as_float(row.get("fm_score")),
                "fm_count_threshold": fm_threshold,
                "outline_observable": observable,
                "formula_assignment": formula,
                "map_assignment": map_assignment,
                "assignment_record_status": assignment_status,
                "conditional_generation_target": (
                    assignment_status == "complete"
                    and map_assignment in {TEXTURELESS, OUTLINE}
                ),
                "dense_assembled": as_int(row.get("dense_assembled")),
                "calibration_seed": CALIBRATION_SEED,
                "learning_runs_started": 0,
            }
        )
    ladder_by_id = {row["building_id"]: row for row in ladder}
    validation_available_ids = [
        bid for bid in sorted(validation)
        if ladder_by_id[bid]["assignment_record_status"] == "complete"
    ]
    full_validation_ready = (
        fm_threshold_status == "calibrated_complete"
        and len(validation_available_ids) == 22
    )
    validation_complete_ids = (
        validation_available_ids if full_validation_ready else []
    )
    validation_pairs = [
        (expected[bid], ladder_by_id[bid]["formula_assignment"])
        for bid in validation_complete_ids
    ]
    constant_pairs = [(expected[bid], WELL) for bid in validation_complete_ids]
    validation_correct = sum(actual == recorded for actual, recorded in validation_pairs)
    constant_correct = sum(actual == recorded for actual, recorded in constant_pairs)
    validation_accuracy = (
        validation_correct / len(validation_pairs) if validation_pairs else None
    )
    constant_accuracy = (
        constant_correct / len(constant_pairs) if constant_pairs else None
    )
    gain = (
        validation_accuracy - constant_accuracy
        if validation_accuracy is not None and constant_accuracy is not None
        else None
    )
    validation_status = (
        "complete"
        if full_validation_ready
        else (
            "unavailable_calibration_fm_incomplete"
            if fm_threshold_status != "calibrated_complete"
            else "unavailable_validation_fm_incomplete"
        )
    )
    validation_subset = (
        "manual_validation_22"
        if len(validation_pairs) == 22
        else f"manual_validation_measured_{len(validation_pairs)}"
    )
    confusion = matrix_rows(
        "manual_rule_validation", validation_subset,
        validation_pairs, rule_sha,
    )
    confusion.extend(
        matrix_rows(
            "constant_well_textured_validation", validation_subset,
            constant_pairs, rule_sha,
        )
    )
    dense_pairs = [
        (
            "dense_success" if row["dense_assembled"] == 1 else "dense_failure",
            "well_textured" if row["formula_assignment"] == WELL else "not_well_textured",
        )
        for row in ladder
    ]
    confusion.extend(
        matrix_rows("tier_vs_dense_success", "canonical_178", dense_pairs, rule_sha)
    )
    for tier in EXPECTED_LABELS:
        for split_name in ("calibration", "validation"):
            confusion.append(
                {
                    "record_type": "split_inventory",
                    "comparison": "manual_stratified_split",
                    "subset": "manual_44",
                    "actual_label": tier,
                    "recorded_label": split_name,
                    "count": split_inventory[tier][split_name],
                    "n_records": 44,
                    "calibration_seed": CALIBRATION_SEED,
                    "rule_sha256": rule_sha,
                    "learning_runs_started": 0,
                }
            )
    confusion.append(
        {
            "record_type": "validation_metric",
            "comparison": "manual_rule_vs_constant_well_textured",
            "subset": validation_subset,
            "n_records": len(validation_pairs),
            "correct_count": validation_correct,
            "accuracy": validation_accuracy,
            "constant_accuracy": constant_accuracy,
            "accuracy_gain": gain,
            "calibration_seed": CALIBRATION_SEED,
            "rule_sha256": rule_sha,
            "evaluation_status": validation_status,
            "learning_runs_started": 0,
        }
    )

    predicates = active_predicates(rule["tree"])
    feature_ranges = {
        feature: max(
            max(float(item[feature]) for item in ladder)
            - min(float(item[feature]) for item in ladder),
            1e-12,
        )
        for feature in {item["feature"] for item in predicates}
    }
    case_candidates: list[dict[str, Any]] = []
    for row in ladder:
        reasons = []
        if row["manual_split"] == "validation" and row["expected_tier"] != row["formula_assignment"]:
            reasons.append("validation_expected_recorded_difference")
        if (
            row["primary_assignment"] != WELL
            and row.get("fm_status") != "complete"
        ):
            reasons.append(
                f"fm_result_{row.get('fm_status') or 'missing'}"
            )
        count = row["fm_correspondence_count"]
        if count is not None and abs(count - fm_threshold) <= max(2, fm_threshold * 0.1):
            reasons.append("fm_count_near_threshold")
        if row["formula_assignment"] == UNOBSERVABLE:
            reasons.append("outline_and_fm_not_observed")
        margins = [
            (
                abs(
                    float(row[predicate["feature"]])
                    - float(predicate["threshold"])
                )
                / feature_ranges[predicate["feature"]],
                predicate,
            )
            for predicate in predicates
        ]
        if margins:
            margin, nearest = min(
                margins,
                key=lambda item: (
                    item[0],
                    item[1]["feature"],
                    float(item[1]["threshold"]),
                ),
            )
            nearest_text = (
                f"{nearest['feature']}{nearest['op']}"
                f"{float(nearest['threshold']):.9g}"
            )
        else:
            margin, nearest_text = math.inf, "constant_rule"
        case_candidates.append(
            {
                **{key: row.get(key) for key in CASE_FIELDS},
                "spotcheck_reason": ";".join(reasons),
                "primary_boundary_margin_normalized": margin,
                "nearest_primary_predicate": nearest_text,
                "learning_runs_started": 0,
            }
        )
    nearest_ids = {
        row["building_id"]
        for row in sorted(
            case_candidates,
            key=lambda item: (
                as_float(item["primary_boundary_margin_normalized"])
                if as_float(item["primary_boundary_margin_normalized"]) is not None
                else math.inf,
                item["building_id"],
            ),
        )[:15]
    }
    cases = []
    for row in case_candidates:
        if row["building_id"] in nearest_ids:
            row["spotcheck_reason"] = ";".join(
                value for value in (
                    row["spotcheck_reason"],
                    "near_active_primary_rule_boundary",
                )
                if value
            )
        if row["spotcheck_reason"]:
            cases.append(row)
    cases.sort(
        key=lambda row: (
            0 if "validation" in row["spotcheck_reason"] else 1,
            as_float(row["primary_boundary_margin_normalized"])
            if as_float(row["primary_boundary_margin_normalized"]) is not None
            else math.inf,
            row["building_id"],
        )
    )
    conditional = [
        {
            "building_id": row["building_id"],
            "assignment": row["formula_assignment"],
            "map_assignment": row["map_assignment"],
            "fm_correspondence_count": row["fm_correspondence_count"],
            "fm_z_median_m": row["fm_z_median_m"],
            "learning_runs_started": 0,
        }
        for row in ladder
        if (
            row["assignment_record_status"] == "complete"
            and row["map_assignment"] in {TEXTURELESS, OUTLINE}
        )
    ]
    conditional_fields = [
        "building_id", "assignment", "map_assignment",
        "fm_correspondence_count", "fm_z_median_m", "learning_runs_started",
    ]
    for row in rows:
        bid = row["building_id"]
        inference_types: list[str] = []
        if bid in REPAIR_14:
            inference_types.append(
                "R1-2 MASt3R crop-pair correspondence only"
            )
        if primary[bid]["primary_assignment"] != WELL:
            inference_types.append(
                "R1-4 FM fixed-pose retriangulation only"
            )
        row["new_inference_type"] = (
            "; ".join(inference_types)
            if inference_types
            else "none; frozen 20260716 crop-pair reused"
        )
    atomic_csv(METRICS, rows, METRIC_FIELDS)
    atomic_csv(LADDER, ladder, LADDER_FIELDS)
    atomic_csv(CONFUSION, confusion, CONFUSION_FIELDS)
    atomic_csv(CASES, cases, CASE_FIELDS)
    atomic_csv(CONDITIONAL, conditional, conditional_fields)
    old = _load_old()
    geometries, _areas = old.load_footprints()
    make_map(geometries, ladder)

    tier_counts = Counter(row["map_assignment"] for row in ladder)
    dense_counts = Counter(dense_pairs)
    validation_accuracy_text = (
        f"{validation_accuracy:.6f}"
        if validation_accuracy is not None else "NA"
    )
    constant_accuracy_text = (
        f"{constant_accuracy:.6f}"
        if constant_accuracy is not None else "NA"
    )
    gain_text = f"{gain:.6f}" if gain is not None else "NA"
    calibration_correct_text = (
        str(calibration_correct)
        if calibration_correct is not None else "NA"
    )
    summary_lines = [
        "# Boundary map v2 measurement summary (2026-07-18)",
        "",
        "## Population checks",
        "",
        "| check | count |",
        "|---|---:|",
        "| raw_lidar rows | 199 |",
        "| raw_lidar assembled=true | 178 |",
        "| raw_lidar assembled=false | 21 |",
        "| dense success in canonical population | 114 |",
        "| dense failure in canonical population | 64 |",
        "| 2026-07-16 C symmetric difference | 42 (21 removed + 21 added) |",
        "| reused measurements | 164 |",
        "| newly prepared outline/crop-pair rows | 14 |",
        "",
        "## Assignment counts",
        "",
        "| assignment | count |",
        "|---|---:|",
        *[
            f"| `{label}` | {tier_counts[label]} |"
            for label in (WELL, TEXTURELESS, OUTLINE, UNOBSERVABLE, SMALL)
        ],
        "",
        "## Manual validation and dense cross-tabulation",
        "",
        f"- validation status: {validation_status}",
        f"- validation assignments available/requested: {len(validation_available_ids)}/22",
        f"- validation records used for accuracy: {len(validation_pairs)}",
        f"- rule exact records: {validation_correct}",
        f"- rule accuracy: {validation_accuracy_text}",
        f"- constant `well_textured` exact records: {constant_correct}",
        f"- constant accuracy: {constant_accuracy_text}",
        f"- validation accuracy gain: {gain_text}",
        f"- FM threshold status: {fm_threshold_status}",
        f"- FM count threshold: {fm_threshold}",
        f"- final calibration exact records after FM channel: {calibration_correct_text}/22",
        f"- incomplete calibration FM buildings: {len(fm_calibration_incomplete)}",
        "",
        "FM pair status policy: all selected pairs processed plus at least one "
        "successful nondegenerate pair is `complete`; a successful eligible pair "
        "with pooled footprint count 0 remains complete/count0; baseline<=0.06 m "
        "pairs are excluded; pair exceptions or deadline-pending pairs make the "
        "building incomplete; incomplete FM counts are not used as negative evidence "
        "and those validation records are excluded.",
        "",
        "| dense outcome | recorded group | count |",
        "|---|---|---:|",
        *[
            f"| {actual} | {recorded} | {count} |"
            for (actual, recorded), count in sorted(dense_counts.items())
        ],
        "",
        "All rows record `learning_runs_started=0`. New inference fields are "
        "limited to R1-2 crop-pair measurement and R1-4 fixed-pose FM "
        "retriangulation. FM z is DHHN orthometric after the configured 45.7 m "
        "geoid subtraction. LoD2 height is used for projection/classification only.",
    ]
    atomic_text(SUMMARY, "\n".join(summary_lines) + "\n")
    log(
        f"finalize artifacts prepared metrics={len(rows)} ladder={len(ladder)} "
        f"validation={validation_correct}/{len(validation_pairs)} "
        f"gain={gain_text} "
        f"learning_runs_started=0"
    )

    prep = json.loads(PREP_MANIFEST.read_text(encoding="utf-8"))
    outputs = (METRICS, LADDER, CONFUSION, CASES, CONDITIONAL, FIGURE, SUMMARY)
    sources = (
        SNAPSHOT, POINTS, AUX_V4, LOWTEX, LOWTEX_SCRIPT, MANUAL,
        FOOTPRINTS, PROJECTION_DATUM,
        PREP_MANIFEST, PREP_METRICS, RULE_JSON, PRIMARY_CSV, CROP_JOBS,
        ALL_JOBS,
        FM_JOBS, Path(__file__), MAST3R_HELPER,
        OLD_BOUNDARY_SCRIPT, POPULATION_AUX_SCRIPT,
        PROJECTION_DATUM_SCRIPT,
    )
    runtime_outputs = (
        CROP_RESULTS, CROP_PROGRESS, CROP_RUN_MANIFEST, CROP_LOG,
        FM_RESULTS, FM_PROGRESS, FM_RUN_MANIFEST, FM_LOG, LOG,
    )
    fm_run_payload = (
        json.loads(FM_RUN_MANIFEST.read_text(encoding="utf-8"))
        if FM_RUN_MANIFEST.is_file() else {}
    )
    manifest = {
        "schema": "jointbuildgs.boundary_map_v2.v1",
        "created_utc": now(),
        "git_head_at_measurement": git_value("rev-parse", "HEAD"),
        "branch": git_value("branch", "--show-current"),
        "population": prep,
        "tier_names": [WELL, TEXTURELESS, OUTLINE, UNOBSERVABLE, SMALL],
        "rule": rule,
        "final_rule": final_rule_payload,
        "final_rule_sha256": rule_sha,
        "fm_count_threshold": fm_threshold,
        "fm_count_threshold_selection": {
            "reason": (
                "FM is the only correspondence-count channel used for "
                "textureless_correspondence_anchored; select the integer cutoff "
                "on calibration records only and keep validation records locked"
            ),
            "candidate_range": fm_threshold_candidates,
            "objective": (
                "maximize calibration exact expected-tier agreement after the "
                "depth<=2 primary non-well candidate rule"
            ),
            "tie_break": "smallest integer threshold",
            "default_candidate": FM_MIN_DEFAULT,
            "status": fm_threshold_status,
            "incomplete_calibration_buildings": fm_calibration_incomplete,
        },
        "fm_count_role": (
            "textureless_correspondence_anchored uses only fixed-pose FM "
            "footprint-inside correspondence count; crop-pair count is reference-only"
        ),
        "fm_vertical_datum": {
            "recorded_z": "DHHN orthometric",
            "conversion": (
                "fixed-pose canonical -> base ellipsoidal; subtract configured "
                "projection geoid before fm_z_median_m/fm_z_mad_m"
            ),
            "config": rel(PROJECTION_DATUM),
            "config_sha256": sha256_file(PROJECTION_DATUM),
        },
        "validation": {
            "status": validation_status,
            "requested_n": 22,
            "available_assignment_n": len(validation_available_ids),
            "accuracy_input_n": len(validation_pairs),
            "correct": validation_correct,
            "accuracy": validation_accuracy,
            "constant_classifier": WELL,
            "constant_correct": constant_correct,
            "constant_accuracy": constant_accuracy,
            "accuracy_gain": gain,
        },
        "fm_pair_status_policy": {
            "complete": (
                "all selected pairs processed, no pair exceptions, and at least "
                "one successful nondegenerate pair; pooled inside count may be zero"
            ),
            "excluded_pair": "fixed-pose baseline <=0.06m",
            "no_eligible_pairs": (
                "all processed pairs excluded; building count not used for assignment"
            ),
            "incomplete": (
                "any pair exception or deadline-pending pair; pooled count not "
                "used as negative evidence and validation record excluded"
            ),
            "pooling": (
                "sum counts and concatenate footprint-inside DHHN orthometric z "
                "from successful nondegenerate pairs"
            ),
        },
        "fm_pair_summary": fm_run_payload.get("pair_summary"),
        "dense_check": {
            "canonical_success": 114,
            "canonical_failure": 64,
            "confusion": {
                f"{actual}|{recorded}": count
                for (actual, recorded), count in sorted(dense_counts.items())
            },
        },
        "conditional_generation_buildings": [
            row["building_id"] for row in conditional
        ],
        "incomplete_crop_pair_buildings": sorted(
            row["building_id"]
            for row in rows
            if row["building_id"] in REPAIR_14
            and row.get("crop_pair_status") != "complete"
        ),
        "incomplete_crop_pair_status": {
            row["building_id"]: (row.get("crop_pair_status") or "missing")
            for row in rows
            if row["building_id"] in REPAIR_14
            and row.get("crop_pair_status") != "complete"
        },
        "incomplete_fm_buildings": sorted(
            row["building_id"]
            for row in ladder
            if row["primary_assignment"] != WELL
            and row.get("fm_status") != "complete"
        ),
        "fm_incomplete_buildings": sorted(
            row["building_id"]
            for row in ladder
            if row["primary_assignment"] != WELL
            and row.get("fm_status") != "complete"
        ),
        "incomplete_fm_status": {
            row["building_id"]: (row.get("fm_status") or "missing")
            for row in ladder
            if row["primary_assignment"] != WELL
            and row.get("fm_status") != "complete"
        },
        "model": {
            "revision": MODEL_REVISION,
            "weights_sha256": MODEL_SHA256,
            "weights_bytes": MODEL_BYTES,
            "config_sha256": MODEL_CONFIG_SHA256,
        },
        "source_sha256": {
            rel(path): sha256_file(path) for path in sources if path.is_file()
        },
        "output_sha256": {
            rel(path): sha256_file(path)
            for path in (*outputs, *runtime_outputs)
            if path.is_file()
        },
        "learning_runs_started": 0,
        "new_inference_type": [
            "R1-2 MASt3R crop-pair correspondence",
            "R1-4 MASt3R reciprocal matches with fixed-pose FM retriangulation",
        ],
        "interpretation_or_verdict": None,
    }
    atomic_json(MANIFEST, manifest)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "command", choices=("prepare", "fit-primary", "finalize")
    )
    args = parser.parse_args()
    if args.command == "prepare":
        prepare()
    elif args.command == "fit-primary":
        fit_primary()
    else:
        finalize()


if __name__ == "__main__":
    main()
