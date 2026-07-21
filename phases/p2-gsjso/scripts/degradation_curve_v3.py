#!/usr/bin/env python3
"""Measure the fixed 178-building ALS degradation curve without learning.

The accepted canonical ALS CityJSON is reused for the zero stage.  Eleven
non-zero degradation stages perturb only class-6 roof evidence whose original
XY coordinate lies inside one of the canonical 178 roofprints.  Ground and
other context classes are held fixed.  Every non-zero stage is passed through
the pinned Roofer default command and the canonical roof scorer.

This script owns deterministic input generation, stage scoring, aggregation,
figures, and manifests.  The shell driver owns detached execution, Roofer
container invocation, progress logging, commits, and pushes.
"""

from __future__ import annotations

import argparse
import copy
import csv
import hashlib
import importlib.util
import json
import math
import os
import shutil
import subprocess
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import median
from typing import Any, Iterable, Mapping, Sequence

import laspy
import numpy as np
from shapely import contains_xy
from shapely.geometry import shape
from shapely.ops import unary_union


REPO = Path(__file__).resolve().parents[3]
DOCS = REPO / "docs"
RUN_DIR = REPO / "phases/p2-gsjso/runs/20260721_degradation_curve"
RUNTIME = RUN_DIR / "runtime"
INPUT_DIR = RUNTIME / "input"
ROOFER_DIR = RUNTIME / "roofer"
CITYJSON_DIR = RUNTIME / "cityjson"
VAL_DIR = RUNTIME / "val3dity"
POINT_DIR = RUNTIME / "point_metrics"
STAGE_SCORE_DIR = RUNTIME / "stage_measurements"
STAGE_META_DIR = RUNTIME / "stage_meta"

PREFLIGHT_MANIFEST = RUN_DIR / "preflight_manifest.json"
ZERO_RERUN_DIAGNOSTIC = RUN_DIR / "zero_rerun_diagnostic.json"
ZERO_VALIDATION = RUN_DIR / "zero_stage_validation.json"
BASE_CROP = RUNTIME / "base_aoi.laz"
BASE_OWNER = RUNTIME / "base_owner.npy"
BASE_INVENTORY = RUNTIME / "base_inventory.csv"

MEASUREMENTS_CSV = DOCS / "degradation_curve_measurements.csv"
SUMMARY_CSV = DOCS / "degradation_curve_summary.csv"
MANIFEST_JSON = DOCS / "degradation_curve_manifest.json"
SUMMARY_MD = DOCS / "W_degradation_curve_summary_20260721.md"
FIGURE_DIR = DOCS / "figs/degradation_curve"
NOISE_FIGURE = FIGURE_DIR / "degradation_curve_noise.png"
DENSITY_FIGURE = FIGURE_DIR / "degradation_curve_density.png"

SNAPSHOT = DOCS / "regression_input_snapshot.csv"
LADDER = DOCS / "boundary_map_v4_1_ladder.csv"
BASELINE_SCORES = DOCS / "qs_baseline178_scores.csv"
BASELINE_SUMMARY = DOCS / "qs_baseline178_summary.csv"
BASELINE_MANIFEST = DOCS / "qs_baseline178_manifest.json"
FOOTPRINTS_GPKG = (
    REPO / "phases/p0-audit/data/work/w2/footprints_scene_aoi.gpkg"
)
FOOTPRINTS_GEOJSON = (
    REPO / "phases/p0-audit/data/work/w2_city3d/footprints_scene_aoi.geojson"
)
RAW_ALS_DIR = REPO / "phases/p0-audit/data/raw/als"
LOD2_DIR = REPO / "phases/p0-audit/data/raw/lod2"
CANONICAL_RUN = (
    REPO / "phases/p0-audit/runs/w2_1_roofer_default_20260612_152729"
)
CANONICAL_ALS_CITYJSON = CANONICAL_RUN / "cityjson/als_roofer.city.json"
CANONICAL_ALS_JSONL_DIR = CANONICAL_RUN / "roofer_als"
CANONICAL_STATUS = CANONICAL_RUN / "building_reconstruction_status.csv"

SCORER_SCRIPT = REPO / "phases/p2-gsjso/scripts/e5_c001_8way.py"
BASELINE_SCORER_SCRIPT = (
    REPO / "phases/p2-gsjso/scripts/qs_baseline178_rescore.py"
)
W2_SCRIPT = REPO / "phases/p0-audit/scripts/08_roofer_w2.py"
QA_SCRIPT = REPO / "phases/p2-gsjso/scripts/degradation_curve_v3_qa.py"
DRIVER_SCRIPT = (
    REPO / "phases/p2-gsjso/scripts/run_degradation_curve_20260721.sh"
)
RECOVERY_SCRIPT = (
    REPO / "phases/p2-gsjso/scripts/degradation_curve_v3_recovery.py"
)
RECOVERY_INCIDENT = RUN_DIR / "degradation_curve_recovery_incident.json"

EXPECTED_POPULATION = 178
EXPECTED_STAGE_COUNT = 12
EXPECTED_MEASUREMENT_ROWS = EXPECTED_POPULATION * EXPECTED_STAGE_COUNT
CRS = "EPSG:25832"
BUILDING_CLASS = 6
GROUND_CLASS = 2
AOI_BBOX = (690791.740, 5335864.050, 691154.650, 5336353.850)
SEED_NAMESPACE = "jointbuildgs.degradation_curve.v3"
ROOFER_IMAGE = (
    "3dgi/roofer@sha256:"
    "dd2c415aaee337502bde0dc1426dfa9c9f88e648f9d2f6340110c49932c251d2"
)
ROOFER_PARAMETERS = (
    "--id-attribute building_id "
    "--box 690791.740 5335864.050 691154.650 5336353.850; "
    "all reconstruction parameters default"
)
GT_ROLE = "LoD2 reference used only for scoring"
PERTURBATION_SCOPE = (
    "class-6 points with pre-degradation XY inside a canonical roofprint; "
    "class-2 ground and all other context points held fixed"
)
OVERLAP_OWNER_RULE = (
    "for a class-6 point inside multiple canonical roofprints, the "
    "lexicographically first building_id supplies the perturbation seed; "
    "the realized point count and residual are still measured for every "
    "containing building"
)

PILOT_IDS = {
    f"DEBY_LOD2_{short}"
    for short in (
        "4907184",
        "4907185",
        "4907186",
        "4907188",
        "4907195",
        "4907198",
        "4907202",
        "4908168",
        "4908178",
        "60098",
    )
}

STAGES: list[dict[str, Any]] = [
    {
        "stage_index": 0,
        "stage_id": "baseline",
        "axis": "baseline",
        "sigma_m": 0.0,
        "retention": 1.0,
        "is_combination": False,
    },
    {
        "stage_index": 1,
        "stage_id": "noise_sigma_0p05",
        "axis": "noise",
        "sigma_m": 0.05,
        "retention": 1.0,
        "is_combination": False,
    },
    {
        "stage_index": 2,
        "stage_id": "noise_sigma_0p10",
        "axis": "noise",
        "sigma_m": 0.10,
        "retention": 1.0,
        "is_combination": False,
    },
    {
        "stage_index": 3,
        "stage_id": "noise_sigma_0p20",
        "axis": "noise",
        "sigma_m": 0.20,
        "retention": 1.0,
        "is_combination": False,
    },
    {
        "stage_index": 4,
        "stage_id": "noise_sigma_0p40",
        "axis": "noise",
        "sigma_m": 0.40,
        "retention": 1.0,
        "is_combination": False,
    },
    {
        "stage_index": 5,
        "stage_id": "noise_sigma_0p80",
        "axis": "noise",
        "sigma_m": 0.80,
        "retention": 1.0,
        "is_combination": False,
    },
    {
        "stage_index": 6,
        "stage_id": "density_retain_1of2",
        "axis": "density",
        "sigma_m": 0.0,
        "retention": 0.5,
        "is_combination": False,
    },
    {
        "stage_index": 7,
        "stage_id": "density_retain_1of4",
        "axis": "density",
        "sigma_m": 0.0,
        "retention": 0.25,
        "is_combination": False,
    },
    {
        "stage_index": 8,
        "stage_id": "density_retain_1of10",
        "axis": "density",
        "sigma_m": 0.0,
        "retention": 0.10,
        "is_combination": False,
    },
    {
        "stage_index": 9,
        "stage_id": "density_retain_1of20",
        "axis": "density",
        "sigma_m": 0.0,
        "retention": 0.05,
        "is_combination": False,
    },
    {
        "stage_index": 10,
        "stage_id": "combo_sigma_0p20_retain_1of4",
        "axis": "combination",
        "sigma_m": 0.20,
        "retention": 0.25,
        "is_combination": True,
    },
    {
        "stage_index": 11,
        "stage_id": "combo_sigma_0p40_retain_1of10",
        "axis": "combination",
        "sigma_m": 0.40,
        "retention": 0.10,
        "is_combination": True,
    },
]
STAGE_BY_ID = {stage["stage_id"]: stage for stage in STAGES}

MEASUREMENT_FIELDS = [
    "stage_index",
    "stage_id",
    "stage_axis",
    "nominal_sigma_m",
    "nominal_retention",
    "is_combination",
    "building_id",
    "population_scope",
    "cell_label",
    "small_lt50",
    "ref_roof_type",
    "ref_roof_slope_group",
    "pilot10",
    "seed_uint64",
    "seed_formula",
    "als_source_files",
    "als_source_file_sha256",
    "als_roof_evidence_payload_sha256",
    "shared_source_point_count",
    "overlap_owner_rule",
    "source_point_count",
    "retained_member_point_count",
    "degraded_point_count",
    "source_point_density_m2",
    "retained_member_density_m2",
    "degraded_point_density_m2",
    "realized_retention_ratio",
    "realized_inside_retention_ratio",
    "realized_axis_noise_std_m",
    "realized_xyz_displacement_rms_m",
    "stage_input_path",
    "stage_input_sha256",
    "perturbation_scope",
    "coordinate_operation_order",
    "rf_success",
    "rf_extrusion_mode",
    "rf_pointcloud_unusable",
    "rf_roof_type",
    "rf_pt_density",
    "rf_nodata_frac",
    "rf_rmse_lod22",
    "rf_roof_planes",
    "rf_reconstruction_time_s",
    "assembly_status",
    "assembly_success",
    "has_lod22",
    "lod1_fallback",
    "val3dity_valid",
    "roof_face_count_model",
    "roof_face_count_ref",
    "face_count_ratio",
    "roof_rms_m",
    "roof_hausdorff_m",
    "roof_distance_samples",
    "roof_completeness",
    "model_roof_xy_area_m2",
    "reference_roof_xy_area_m2",
    "roof_overlap_xy_area_m2",
    "geometry_roof_surface_present",
    "cityjson_path",
    "cityjson_sha256",
    "val3dity_report",
    "assembly_artifact_reused",
    "assembly_pipeline",
    "crs",
    "gt_role",
    "learning_runs_started",
    "new_inference_runs",
]

POINT_FIELDS = [
    "stage_index",
    "stage_id",
    "building_id",
    "seed_uint64",
    "seed_formula",
    "als_source_files",
    "als_source_file_sha256",
    "als_roof_evidence_payload_sha256",
    "shared_source_point_count",
    "overlap_owner_rule",
    "source_point_count",
    "retained_member_point_count",
    "degraded_point_count",
    "source_point_density_m2",
    "retained_member_density_m2",
    "degraded_point_density_m2",
    "realized_retention_ratio",
    "realized_inside_retention_ratio",
    "realized_axis_noise_std_m",
    "realized_xyz_displacement_rms_m",
    "stage_input_path",
    "stage_input_sha256",
    "perturbation_scope",
    "coordinate_operation_order",
]

SUMMARY_FIELDS = [
    "row_type",
    "stage_index",
    "stage_id",
    "stage_axis",
    "nominal_sigma_m",
    "nominal_retention",
    "is_combination",
    "stratum_type",
    "stratum_value",
    "population_count",
    "measurement_count",
    "assembly_count",
    "assembly_rate",
    "lod2_count",
    "lod1_fallback_count",
    "lod1_fallback_rate",
    "val3dity_valid_count",
    "val3dity_valid_rate",
    "face_count_ratio_measurable_count",
    "face_count_ratio_median",
    "roof_rms_measurable_count",
    "roof_rms_median_m",
    "roof_hausdorff_measurable_count",
    "roof_hausdorff_median_m",
    "roof_completeness_measurable_count",
    "roof_completeness_median",
    "degraded_point_count_median",
    "degraded_point_density_m2_median",
    "realized_retention_ratio_median",
    "realized_axis_noise_std_m_median",
    "realized_xyz_displacement_rms_m_median",
    "rf_reconstruction_time_s_sum",
    "rf_reconstruction_time_s_median",
    "validation_axis",
    "validation_metric",
    "expected_direction",
    "monotonic_nonincreasing",
    "monotonic_nondecreasing",
    "monotonic_expected",
    "inversion_transitions",
    "comparison_scope",
    "comparison_metric",
    "comparison_expected",
    "comparison_observed",
    "comparison_match",
    "learning_runs_started",
    "new_inference_runs",
]


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def rel(path: Path) -> str:
    return str(path.resolve().relative_to(REPO.resolve()))


def sha256_file(path: Path, block_size: int = 1 << 20) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(block_size), b""):
            digest.update(block)
    return digest.hexdigest()


def aggregate_sha(items: Sequence[tuple[str, str]]) -> str:
    payload = "".join(f"{path}\t{digest}\n" for path, digest in items)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def atomic_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(text, encoding="utf-8")
    temporary.replace(path)


def cell(value: Any) -> Any:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (float, np.floating)):
        if not math.isfinite(float(value)):
            return ""
        return f"{float(value):.9f}"
    if isinstance(value, (int, np.integer)):
        return str(int(value))
    return value


def atomic_csv(
    path: Path,
    rows: Sequence[Mapping[str, Any]],
    fields: Sequence[str],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(fields))
        writer.writeheader()
        for row in rows:
            writer.writerow({field: cell(row.get(field)) for field in fields})
    temporary.replace(path)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def as_bool(value: Any) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes"}


def as_float(value: Any) -> float | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() in {"none", "nan"}:
        return None
    try:
        result = float(text)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def as_int(value: Any) -> int | None:
    result = as_float(value)
    return None if result is None else int(round(result))


def seed_for(building_id: str, stage_index: int) -> int:
    payload = f"{SEED_NAMESPACE}|{building_id}|{stage_index}"
    return int.from_bytes(
        hashlib.sha256(payload.encode("utf-8")).digest()[:8],
        "big",
        signed=False,
    )


def seed_formula() -> str:
    return (
        "uint64_be_first8("
        "sha256('jointbuildgs.degradation_curve.v3|{building_id}|{stage_index}')"
        ")"
    )


def git_output(*args: str) -> str:
    return subprocess.check_output(
        ["git", *args], cwd=REPO, text=True
    ).strip()


def load_population() -> tuple[
    list[str],
    dict[str, dict[str, dict[str, str]]],
]:
    by_arm: dict[str, dict[str, dict[str, str]]] = defaultdict(dict)
    for row in read_csv(SNAPSHOT):
        arm = row["arm"]
        building_id = row["building_id"]
        if building_id in by_arm[arm]:
            raise RuntimeError(
                f"duplicate snapshot row arm={arm} building={building_id}"
            )
        by_arm[arm][building_id] = row
    population = sorted(
        building_id
        for building_id, row in by_arm["raw_lidar"].items()
        if as_bool(row["assembled"])
    )
    if len(population) != EXPECTED_POPULATION:
        raise RuntimeError(f"population drift {len(population)}")
    if len(set(population)) != len(population):
        raise RuntimeError("population duplicate")
    for arm in ("raw_lidar", "raw_dense"):
        missing = sorted(set(population) - set(by_arm[arm]))
        if missing:
            raise RuntimeError(f"snapshot {arm} missing {missing}")
    return population, by_arm


def load_ladder(population: Sequence[str]) -> dict[str, dict[str, str]]:
    rows = read_csv(LADDER)
    by_id = {row["building_id"]: row for row in rows}
    if len(rows) != EXPECTED_POPULATION or len(by_id) != len(rows):
        raise RuntimeError("ladder row/identifier drift")
    if set(by_id) != set(population):
        raise RuntimeError("ladder population set drift")
    return by_id


def load_footprints(
    population: Sequence[str],
) -> dict[str, Any]:
    payload = json.loads(FOOTPRINTS_GEOJSON.read_text(encoding="utf-8"))
    pieces: dict[str, list[Any]] = defaultdict(list)
    for feature in payload.get("features", []):
        properties = feature.get("properties") or {}
        building_id = str(properties.get("building_id", ""))
        if building_id in set(population):
            pieces[building_id].append(shape(feature["geometry"]))
    footprints = {
        building_id: unary_union(geometries)
        for building_id, geometries in pieces.items()
    }
    missing = sorted(set(population) - set(footprints))
    if missing:
        raise RuntimeError(f"footprints missing {missing}")
    invalid = [
        building_id
        for building_id, geometry in footprints.items()
        if geometry.is_empty or not geometry.is_valid or geometry.area <= 0
    ]
    if invalid:
        raise RuntimeError(f"footprints invalid {invalid}")
    return footprints


def load_baseline_rows(
    population: Sequence[str],
) -> dict[str, dict[str, str]]:
    rows = [
        row
        for row in read_csv(BASELINE_SCORES)
        if row["role"] == "als"
    ]
    by_id = {row["building_id"]: row for row in rows}
    if len(rows) != EXPECTED_POPULATION or set(by_id) != set(population):
        raise RuntimeError("baseline ALS score population drift")
    return by_id


def load_module(name: str, path: Path) -> Any:
    specification = importlib.util.spec_from_file_location(name, path)
    if specification is None or specification.loader is None:
        raise RuntimeError(f"cannot import {path}")
    module = importlib.util.module_from_spec(specification)
    sys.modules[name] = module
    specification.loader.exec_module(module)
    return module


def stage_payload(stage: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "stage_index": int(stage["stage_index"]),
        "stage_id": str(stage["stage_id"]),
        "axis": str(stage["axis"]),
        "sigma_m": float(stage["sigma_m"]),
        "retention": float(stage["retention"]),
        "is_combination": bool(stage["is_combination"]),
    }


def package_versions() -> dict[str, str]:
    import matplotlib
    import shapely

    return {
        "python": sys.version.split()[0],
        "numpy": np.__version__,
        "laspy": laspy.__version__,
        "shapely": shapely.__version__,
        "matplotlib": matplotlib.__version__,
        "val3dity": subprocess.check_output(
            ["val3dity", "--version"], text=True
        ).strip(),
    }


def prepare() -> None:
    RUN_DIR.mkdir(parents=True, exist_ok=True)
    required = [
        SNAPSHOT,
        LADDER,
        BASELINE_SCORES,
        BASELINE_SUMMARY,
        BASELINE_MANIFEST,
        FOOTPRINTS_GPKG,
        FOOTPRINTS_GEOJSON,
        CANONICAL_ALS_CITYJSON,
        CANONICAL_STATUS,
        SCORER_SCRIPT,
        BASELINE_SCORER_SCRIPT,
        W2_SCRIPT,
        Path(__file__),
        QA_SCRIPT,
        DRIVER_SCRIPT,
        RECOVERY_SCRIPT,
    ]
    missing = [rel(path) for path in required if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"preflight files missing {missing}")
    raw_files = sorted(RAW_ALS_DIR.glob("*.laz"))
    if len(raw_files) != 4:
        raise RuntimeError(f"ALS source file count drift {len(raw_files)}")
    population, snapshot_by_arm = load_population()
    ladder = load_ladder(population)
    load_baseline_rows(population)
    load_footprints(population)
    if not PILOT_IDS.issubset(set(population)) or len(PILOT_IDS) != 10:
        raise RuntimeError("pilot10 set drift")
    cell_counts = {
        label: sum(row["cell_label"] == label for row in ladder.values())
        for label in (
            "cell_1_assembled",
            "cell_2_anchored",
            "cell_3_outline_only",
            "cell_4_beyond_image",
        )
    }
    if cell_counts != {
        "cell_1_assembled": 114,
        "cell_2_anchored": 23,
        "cell_3_outline_only": 41,
        "cell_4_beyond_image": 0,
    }:
        raise RuntimeError(f"ladder cell drift {cell_counts}")
    small_count = sum(as_bool(row["small_lt50"]) for row in ladder.values())
    if small_count != 37:
        raise RuntimeError(f"small_lt50 drift {small_count}")

    raw_hashes = [(rel(path), sha256_file(path)) for path in raw_files]
    source_paths = [
        SNAPSHOT,
        LADDER,
        BASELINE_SCORES,
        BASELINE_SUMMARY,
        BASELINE_MANIFEST,
        FOOTPRINTS_GPKG,
        FOOTPRINTS_GEOJSON,
        CANONICAL_ALS_CITYJSON,
        CANONICAL_STATUS,
        SCORER_SCRIPT,
        BASELINE_SCORER_SCRIPT,
        W2_SCRIPT,
        Path(__file__),
        QA_SCRIPT,
        DRIVER_SCRIPT,
        RECOVERY_SCRIPT,
        *([RECOVERY_INCIDENT] if RECOVERY_INCIDENT.is_file() else []),
        *([ZERO_RERUN_DIAGNOSTIC] if ZERO_RERUN_DIAGNOSTIC.is_file() else []),
        *sorted(CANONICAL_ALS_JSONL_DIR.glob("*.city.jsonl")),
        *sorted(LOD2_DIR.glob("*.gml")),
    ]
    seeds = {
        stage["stage_id"]: {
            building_id: seed_for(building_id, int(stage["stage_index"]))
            for building_id in population
        }
        for stage in STAGES
    }
    dense_rows = [snapshot_by_arm["raw_dense"][bid] for bid in population]
    dense_noise = [
        value
        for value in (
            as_float(row.get("local_plane_rms_m")) for row in dense_rows
        )
        if value is not None
    ]
    dense_density = [
        value
        for value in (
            as_float(row.get("pt_density_m2")) for row in dense_rows
        )
        if value is not None
    ]
    payload: dict[str, Any] = {
        "schema": "jointbuildgs.degradation_curve.preflight.v3",
        "created_utc": now(),
        "git_head": git_output("rev-parse", "HEAD"),
        "branch": git_output("branch", "--show-current"),
        "population_definition": (
            "docs/regression_input_snapshot.csv arm=raw_lidar assembled=true"
        ),
        "population_count": len(population),
        "population_sha256": hashlib.sha256(
            ("\n".join(population) + "\n").encode("utf-8")
        ).hexdigest(),
        "population": population,
        "pilot10": sorted(PILOT_IDS),
        "group_counts": {
            "ladder_cells": cell_counts,
            "small_lt50": small_count,
            "non_small_ge50": len(population) - small_count,
            "roof_slope_group": {
                group: sum(
                    row["ref_roof_slope_group"] == group
                    for row in ladder.values()
                )
                for group in ("horizontal", "sloped")
            },
        },
        "stage_count": len(STAGES),
        "expected_measurement_rows": EXPECTED_MEASUREMENT_ROWS,
        "stages": [stage_payload(stage) for stage in STAGES],
        "zero_duplicate_policy": (
            "sigma=0 and retention=1 are one shared baseline row; "
            "5 nonzero noise + 4 reduced density + 2 combinations + "
            "1 baseline = 12 stages"
        ),
        "seed_formula": seed_formula(),
        "seed_namespace": SEED_NAMESPACE,
        "seed_values": seeds,
        "perturbation_scope": PERTURBATION_SCOPE,
        "overlap_owner_rule": OVERLAP_OWNER_RULE,
        "coordinate_operation_order": (
            "uniform Bernoulli retention, then isotropic Gaussian XYZ noise; "
            "LAS coordinates quantized to source 0.001 m scale"
        ),
        "classification_and_attributes": (
            "retained point records unchanged except X/Y/Z; classification "
            "labels and all non-coordinate dimensions preserved"
        ),
        "raw_als_source_sha256": dict(raw_hashes),
        "raw_als_source_aggregate_sha256": aggregate_sha(raw_hashes),
        "roofer_image": ROOFER_IMAGE,
        "roofer_parameters": ROOFER_PARAMETERS,
        "roofer_parameter_change_count": 0,
        "canonical_zero_stage": {
            "execution_mode": "accepted_artifact_reuse",
            "cityjson": rel(CANONICAL_ALS_CITYJSON),
            "cityjson_sha256": sha256_file(CANONICAL_ALS_CITYJSON),
            "reason": (
                "zero-stage hard-stop compares the frozen accepted assembly "
                "and scorer rows; non-zero stages are new assemblies"
            ),
            "same_command_diagnostic_record": (
                rel(ZERO_RERUN_DIAGNOSTIC)
                if ZERO_RERUN_DIAGNOSTIC.is_file()
                else None
            ),
        },
        "dense_comparison_source": rel(SNAPSHOT),
        "dense_comparison_markers_preflight": {
            "local_plane_rms_m": quantile_payload(dense_noise),
            "pt_density_m2": quantile_payload(dense_density),
        },
        "figure_contract": {
            "analytical_question": (
                "controlled ALS input stage versus assembly rate and median "
                "reference-scored roof RMS"
            ),
            "chart_family": "ordered line with benchmark bands",
            "surface": "static PNG files requested by the order",
            "panels": [
                "assembly rate",
                "median roof RMS with 0.3 m and 1.0 m specification lines",
            ],
            "series": [
                "canonical 178 overall",
                "fixed pilot10 subset",
                "two combination cells",
            ],
            "palette_policy": (
                "hard two-root cap: blue overall, orange pilot; line style "
                "and open markers supply non-color distinction"
            ),
            "qa_surface": [
                rel(NOISE_FIGURE),
                rel(DENSITY_FIGURE),
            ],
        },
        "tool_versions": package_versions(),
        "crs": CRS,
        "learning_runs_started": 0,
        "new_inference_runs": 0,
        "image_inputs_used": 0,
        "source_sha256": {
            rel(path): sha256_file(path)
            for path in source_paths
            if path.is_file()
        },
    }
    atomic_text(
        PREFLIGHT_MANIFEST,
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
    )
    print(
        json.dumps(
            {
                "preflight_manifest": rel(PREFLIGHT_MANIFEST),
                "population": len(population),
                "stages": len(STAGES),
                "rows": EXPECTED_MEASUREMENT_ROWS,
                "learning_runs_started": 0,
                "new_inference_runs": 0,
            },
            ensure_ascii=False,
        )
    )


def verify_preflight() -> None:
    if not PREFLIGHT_MANIFEST.is_file():
        raise FileNotFoundError(PREFLIGHT_MANIFEST)
    payload = json.loads(PREFLIGHT_MANIFEST.read_text(encoding="utf-8"))
    population, _ = load_population()
    if payload["population"] != population:
        raise RuntimeError("preflight population drift")
    if payload["stages"] != [stage_payload(stage) for stage in STAGES]:
        raise RuntimeError("preflight stages drift")
    if payload["seed_formula"] != seed_formula():
        raise RuntimeError("preflight seed formula drift")
    for path_text, expected in payload["source_sha256"].items():
        path = REPO / path_text
        if not path.is_file() or sha256_file(path) != expected:
            raise RuntimeError(f"preflight source hash drift {path_text}")
    if payload["learning_runs_started"] != 0:
        raise RuntimeError("preflight learning flag drift")
    print(
        json.dumps(
            {
                "verified": True,
                "population": len(population),
                "stages": len(STAGES),
                "source_hashes": len(payload["source_sha256"]),
            }
        )
    )


def quantile_payload(values: Iterable[float | None]) -> dict[str, Any]:
    clean = np.asarray(
        [
            float(value)
            for value in values
            if value is not None and math.isfinite(float(value))
        ],
        dtype=np.float64,
    )
    if not len(clean):
        return {
            "count": 0,
            "min": None,
            "p25": None,
            "median": None,
            "p75": None,
            "max": None,
        }
    return {
        "count": int(len(clean)),
        "min": float(np.min(clean)),
        "p25": float(np.quantile(clean, 0.25)),
        "median": float(np.median(clean)),
        "p75": float(np.quantile(clean, 0.75)),
        "max": float(np.max(clean)),
    }


def build_base() -> None:
    for directory in (
        RUNTIME,
        INPUT_DIR,
        ROOFER_DIR,
        CITYJSON_DIR,
        VAL_DIR,
        POINT_DIR,
        STAGE_SCORE_DIR,
        STAGE_META_DIR,
    ):
        directory.mkdir(parents=True, exist_ok=True)
    population, _ = load_population()
    footprints = load_footprints(population)
    raw_files = sorted(RAW_ALS_DIR.glob("*.laz"))
    if not BASE_CROP.is_file():
        temporary = BASE_CROP.with_suffix(".tmp.laz")
        if temporary.exists():
            temporary.unlink()
        header = copy.deepcopy(laspy.open(raw_files[0]).header)
        header.generating_software = "JointBuildGS degradation_curve_v3"
        with laspy.open(temporary, mode="w", header=header) as writer:
            for source in raw_files:
                with laspy.open(source) as reader:
                    for points in reader.chunk_iterator(1_000_000):
                        x = np.asarray(points.x)
                        y = np.asarray(points.y)
                        keep = (
                            (x >= AOI_BBOX[0])
                            & (x <= AOI_BBOX[2])
                            & (y >= AOI_BBOX[1])
                            & (y <= AOI_BBOX[3])
                        )
                        if np.any(keep):
                            writer.write_points(points[keep])
        temporary.replace(BASE_CROP)

    cloud = laspy.read(BASE_CROP)
    x = np.asarray(cloud.x)
    y = np.asarray(cloud.y)
    classes = np.asarray(cloud.classification, dtype=np.uint8)
    class6_indices = np.flatnonzero(classes == BUILDING_CLASS)
    x6 = x[class6_indices]
    y6 = y[class6_indices]
    owner = np.full(len(cloud.points), -1, dtype=np.int16)
    membership_count = np.zeros(len(cloud.points), dtype=np.uint8)
    membership_by_id: dict[str, np.ndarray] = {}
    source_bounds: dict[str, tuple[float, float, float, float]] = {}
    source_hashes: dict[str, str] = {}
    for source in raw_files:
        header = laspy.open(source).header
        source_bounds[rel(source)] = (
            float(header.mins[0]),
            float(header.mins[1]),
            float(header.maxs[0]),
            float(header.maxs[1]),
        )
        source_hashes[rel(source)] = sha256_file(source)

    for building_index, building_id in enumerate(population):
        geometry = footprints[building_id]
        minx, miny, maxx, maxy = geometry.bounds
        candidates = np.flatnonzero(
            (x6 >= minx) & (x6 <= maxx) & (y6 >= miny) & (y6 <= maxy)
        )
        inside_local = contains_xy(
            geometry, x6[candidates], y6[candidates]
        )
        indices = class6_indices[candidates[inside_local]]
        membership_by_id[building_id] = indices
        membership_count[indices] += 1
        unowned = indices[owner[indices] < 0]
        owner[unowned] = building_index

    rows: list[dict[str, Any]] = []
    base_crop_sha = sha256_file(BASE_CROP)
    for building_index, building_id in enumerate(population):
        geometry = footprints[building_id]
        minx, miny, maxx, maxy = geometry.bounds
        indices = membership_by_id[building_id]
        source_paths = [
            path
            for path, bounds in source_bounds.items()
            if not (
                maxx < bounds[0]
                or minx > bounds[2]
                or maxy < bounds[1]
                or miny > bounds[3]
            )
        ]
        payload_hash = hashlib.sha256(
            cloud.points.array[indices].tobytes()
        ).hexdigest()
        source_count = int(len(indices))
        area = float(geometry.area)
        if source_count <= 0:
            raise RuntimeError(f"zero ALS roof points building={building_id}")
        rows.append(
            {
                "building_index": building_index,
                "building_id": building_id,
                "footprint_area_m2": area,
                "als_source_files": ";".join(source_paths),
                "als_source_file_sha256": ";".join(
                    f"{path}={source_hashes[path]}" for path in source_paths
                ),
                "als_roof_evidence_payload_sha256": payload_hash,
                "shared_source_point_count": int(
                    np.sum(membership_count[indices] > 1)
                ),
                "overlap_owner_rule": OVERLAP_OWNER_RULE,
                "source_point_count": source_count,
                "source_point_density_m2": source_count / area,
                "base_crop_path": rel(BASE_CROP),
                "base_crop_sha256": base_crop_sha,
                "crs": CRS,
            }
        )
    np.save(BASE_OWNER, owner, allow_pickle=False)
    atomic_csv(
        BASE_INVENTORY,
        rows,
        [
            "building_index",
            "building_id",
            "footprint_area_m2",
            "als_source_files",
            "als_source_file_sha256",
            "als_roof_evidence_payload_sha256",
            "shared_source_point_count",
            "overlap_owner_rule",
            "source_point_count",
            "source_point_density_m2",
            "base_crop_path",
            "base_crop_sha256",
            "crs",
        ],
    )
    baseline_stage = STAGES[0]
    source_items = [
        (rel(path), source_hashes[rel(path)]) for path in raw_files
    ]
    point_rows = [
        {
            "stage_index": 0,
            "stage_id": "baseline",
            "building_id": row["building_id"],
            "seed_uint64": seed_for(row["building_id"], 0),
            "seed_formula": seed_formula(),
            "als_source_files": row["als_source_files"],
            "als_source_file_sha256": row["als_source_file_sha256"],
            "als_roof_evidence_payload_sha256": row[
                "als_roof_evidence_payload_sha256"
            ],
            "shared_source_point_count": row[
                "shared_source_point_count"
            ],
            "overlap_owner_rule": OVERLAP_OWNER_RULE,
            "source_point_count": row["source_point_count"],
            "retained_member_point_count": row["source_point_count"],
            "degraded_point_count": row["source_point_count"],
            "source_point_density_m2": row["source_point_density_m2"],
            "retained_member_density_m2": row["source_point_density_m2"],
            "degraded_point_density_m2": row["source_point_density_m2"],
            "realized_retention_ratio": 1.0,
            "realized_inside_retention_ratio": 1.0,
            "realized_axis_noise_std_m": 0.0,
            "realized_xyz_displacement_rms_m": 0.0,
            "stage_input_path": ";".join(rel(path) for path in raw_files),
            "stage_input_sha256": aggregate_sha(source_items),
            "perturbation_scope": PERTURBATION_SCOPE,
            "coordinate_operation_order": (
                "baseline; no coordinate or point-record change"
            ),
        }
        for row in rows
    ]
    atomic_csv(
        POINT_DIR / f"{baseline_stage['stage_id']}.csv",
        point_rows,
        POINT_FIELDS,
    )
    base_meta = {
        "schema": "jointbuildgs.degradation_curve.base.v3",
        "created_utc": now(),
        "base_crop": rel(BASE_CROP),
        "base_crop_sha256": sha256_file(BASE_CROP),
        "base_crop_point_count": int(len(cloud.points)),
        "base_crop_class_counts": {
            str(value): int(count)
            for value, count in zip(
                *np.unique(classes, return_counts=True), strict=True
            )
        },
        "canonical_owned_class6_count": int(np.sum(owner >= 0)),
        "population_count": len(population),
        "overlapping_roof_evidence_point_count": int(
            np.sum(membership_count > 1)
        ),
        "overlap_owner_rule": OVERLAP_OWNER_RULE,
        "learning_runs_started": 0,
        "new_inference_runs": 0,
    }
    atomic_text(
        STAGE_META_DIR / "base.json",
        json.dumps(base_meta, ensure_ascii=False, indent=2) + "\n",
    )
    print(json.dumps(base_meta, ensure_ascii=False))


def inventory_by_id() -> dict[str, dict[str, str]]:
    rows = read_csv(BASE_INVENTORY)
    by_id = {row["building_id"]: row for row in rows}
    if len(rows) != EXPECTED_POPULATION or len(by_id) != len(rows):
        raise RuntimeError("base inventory drift")
    return by_id


def make_stage(stage_id: str) -> None:
    if stage_id == "baseline":
        raise RuntimeError("baseline input is the accepted canonical ALS source")
    if stage_id not in STAGE_BY_ID:
        raise KeyError(stage_id)
    stage = STAGE_BY_ID[stage_id]
    if not BASE_CROP.is_file() or not BASE_OWNER.is_file():
        raise FileNotFoundError("base crop/owner missing")
    population, _ = load_population()
    footprints = load_footprints(population)
    inventory = inventory_by_id()
    cloud = laspy.read(BASE_CROP)
    owner = np.load(BASE_OWNER, allow_pickle=False)
    if len(owner) != len(cloud.points):
        raise RuntimeError("base owner length drift")
    original_x = np.asarray(cloud.x).copy()
    original_y = np.asarray(cloud.y).copy()
    original_z = np.asarray(cloud.z).copy()
    changed_x = original_x.copy()
    changed_y = original_y.copy()
    changed_z = original_z.copy()
    keep = np.ones(len(cloud.points), dtype=bool)
    retention = float(stage["retention"])
    sigma = float(stage["sigma_m"])
    classes = np.asarray(cloud.classification, dtype=np.uint8)
    class6_indices = np.flatnonzero(classes == BUILDING_CLASS)
    class6_x = original_x[class6_indices]
    class6_y = original_y[class6_indices]
    membership_by_id: dict[str, np.ndarray] = {}
    for building_id in population:
        geometry = footprints[building_id]
        minx, miny, maxx, maxy = geometry.bounds
        candidates = np.flatnonzero(
            (class6_x >= minx)
            & (class6_x <= maxx)
            & (class6_y >= miny)
            & (class6_y <= maxy)
        )
        membership_by_id[building_id] = class6_indices[
            candidates[
                contains_xy(
                    geometry,
                    class6_x[candidates],
                    class6_y[candidates],
                )
            ]
        ]

    for building_index, building_id in enumerate(population):
        member_indices = np.flatnonzero(owner == building_index)
        rng = np.random.default_rng(
            seed_for(building_id, int(stage["stage_index"]))
        )
        if retention < 1.0:
            retained_mask = rng.random(len(member_indices)) < retention
            removed = member_indices[~retained_mask]
            keep[removed] = False
            retained = member_indices[retained_mask]
        else:
            retained = member_indices
        if sigma > 0 and len(retained):
            noise = rng.normal(0.0, sigma, size=(len(retained), 3))
            changed_x[retained] += noise[:, 0]
            changed_y[retained] += noise[:, 1]
            changed_z[retained] += noise[:, 2]

    stage_dir = INPUT_DIR / stage_id
    stage_dir.mkdir(parents=True, exist_ok=True)
    output = stage_dir / "aoi.laz"
    temporary = output.with_suffix(".tmp.laz")
    if temporary.exists():
        temporary.unlink()
    kept_indices = np.flatnonzero(keep)
    output_cloud = laspy.LasData(copy.deepcopy(cloud.header))
    # Preserve laspy's scale-aware wrapper. Calling ``.copy()`` here returns a
    # PackedPointRecord, after which scaled x/y/z assignment is unavailable.
    output_cloud.points = cloud.points[kept_indices]
    output_cloud.x = changed_x[kept_indices]
    output_cloud.y = changed_y[kept_indices]
    output_cloud.z = changed_z[kept_indices]
    output_cloud.write(temporary)
    temporary.replace(output)

    # Re-read so realized residuals include 0.001 m LAS quantization.
    output_cloud = laspy.read(output)
    output_x = np.asarray(output_cloud.x)
    output_y = np.asarray(output_cloud.y)
    output_z = np.asarray(output_cloud.z)
    output_classes = np.asarray(
        output_cloud.classification, dtype=np.uint8
    )
    original_kept_x = original_x[kept_indices]
    original_kept_y = original_y[kept_indices]
    original_kept_z = original_z[kept_indices]
    output_position = np.full(len(cloud.points), -1, dtype=np.int64)
    output_position[kept_indices] = np.arange(len(kept_indices))
    class6_output_indices = np.flatnonzero(output_classes == BUILDING_CLASS)
    class6_x = output_x[class6_output_indices]
    class6_y = output_y[class6_output_indices]
    input_sha = sha256_file(output)

    rows: list[dict[str, Any]] = []
    for building_index, building_id in enumerate(population):
        source = inventory[building_id]
        source_members = membership_by_id[building_id]
        retained_source_members = source_members[keep[source_members]]
        retained_output = output_position[retained_source_members]
        geometry = footprints[building_id]
        minx, miny, maxx, maxy = geometry.bounds
        candidates = np.flatnonzero(
            (class6_x >= minx)
            & (class6_x <= maxx)
            & (class6_y >= miny)
            & (class6_y <= maxy)
        )
        inside_count = int(
            np.sum(
                contains_xy(
                    geometry,
                    class6_x[candidates],
                    class6_y[candidates],
                )
            )
        )
        if len(retained_output):
            dx = output_x[retained_output] - original_kept_x[retained_output]
            dy = output_y[retained_output] - original_kept_y[retained_output]
            dz = output_z[retained_output] - original_kept_z[retained_output]
            squared = dx * dx + dy * dy + dz * dz
            axis_noise = float(
                np.sqrt(np.mean(np.concatenate((dx * dx, dy * dy, dz * dz))))
            )
            xyz_rms = float(np.sqrt(np.mean(squared)))
        else:
            axis_noise = None
            xyz_rms = None
        source_count = int(source["source_point_count"])
        retained_count = int(len(retained_output))
        area = float(source["footprint_area_m2"])
        rows.append(
            {
                "stage_index": stage["stage_index"],
                "stage_id": stage_id,
                "building_id": building_id,
                "seed_uint64": seed_for(
                    building_id, int(stage["stage_index"])
                ),
                "seed_formula": seed_formula(),
                "als_source_files": source["als_source_files"],
                "als_source_file_sha256": source[
                    "als_source_file_sha256"
                ],
                "als_roof_evidence_payload_sha256": source[
                    "als_roof_evidence_payload_sha256"
                ],
                "shared_source_point_count": source[
                    "shared_source_point_count"
                ],
                "overlap_owner_rule": OVERLAP_OWNER_RULE,
                "source_point_count": source_count,
                "retained_member_point_count": retained_count,
                "degraded_point_count": inside_count,
                "source_point_density_m2": source_count / area,
                "retained_member_density_m2": retained_count / area,
                "degraded_point_density_m2": inside_count / area,
                "realized_retention_ratio": retained_count / source_count,
                "realized_inside_retention_ratio": inside_count / source_count,
                "realized_axis_noise_std_m": axis_noise,
                "realized_xyz_displacement_rms_m": xyz_rms,
                "stage_input_path": rel(output),
                "stage_input_sha256": input_sha,
                "perturbation_scope": PERTURBATION_SCOPE,
                "coordinate_operation_order": (
                    "uniform Bernoulli retention then isotropic Gaussian XYZ "
                    "noise; quantized to 0.001 m"
                ),
            }
        )
    point_path = POINT_DIR / f"{stage_id}.csv"
    atomic_csv(point_path, rows, POINT_FIELDS)
    stage_meta = {
        "schema": "jointbuildgs.degradation_curve.input_stage.v3",
        "created_utc": now(),
        "stage": stage_payload(stage),
        "input_path": rel(output),
        "input_sha256": input_sha,
        "input_point_count": int(len(output_cloud.points)),
        "class_counts": {
            str(value): int(count)
            for value, count in zip(
                *np.unique(output_classes, return_counts=True), strict=True
            )
        },
        "point_metrics": rel(point_path),
        "point_metrics_sha256": sha256_file(point_path),
        "learning_runs_started": 0,
        "new_inference_runs": 0,
    }
    atomic_text(
        STAGE_META_DIR / f"{stage_id}.input.json",
        json.dumps(stage_meta, ensure_ascii=False, indent=2) + "\n",
    )
    print(json.dumps(stage_meta, ensure_ascii=False))


def clean_stage_output(stage_id: str) -> None:
    if stage_id == "baseline":
        return
    for path in (
        ROOFER_DIR / stage_id,
        CITYJSON_DIR / f"{stage_id}.city.json",
        VAL_DIR / f"{stage_id}.json",
        VAL_DIR / f"{stage_id}.log",
    ):
        if path.is_dir():
            shutil.rmtree(path)
        elif path.exists():
            path.unlink()
    (ROOFER_DIR / stage_id).mkdir(parents=True, exist_ok=True)


def record_roofer(stage_id: str, wall_seconds: float) -> None:
    if stage_id not in STAGE_BY_ID or stage_id == "baseline":
        raise KeyError(stage_id)
    output_dir = ROOFER_DIR / stage_id
    files = sorted(output_dir.glob("*.city.jsonl"))
    if not files:
        raise RuntimeError(f"Roofer output missing stage={stage_id}")
    recovery_manifest_path = RUNTIME / "recovery" / stage_id / "manifest.json"
    recovery_manifest = (
        json.loads(recovery_manifest_path.read_text(encoding="utf-8"))
        if recovery_manifest_path.is_file()
        else None
    )
    payload = {
        "schema": "jointbuildgs.degradation_curve.roofer_stage.v3",
        "created_utc": now(),
        "stage": stage_payload(STAGE_BY_ID[stage_id]),
        "wall_seconds": float(wall_seconds),
        "roofer_output_files": [rel(path) for path in files],
        "roofer_output_sha256": {
            rel(path): sha256_file(path) for path in files
        },
        "roofer_image": ROOFER_IMAGE,
        "roofer_parameters": ROOFER_PARAMETERS,
        "execution_mode": (
            recovery_manifest["execution_mode"]
            if recovery_manifest is not None
            else "single_stage_batch"
        ),
        "recovery_manifest": (
            rel(recovery_manifest_path)
            if recovery_manifest is not None
            else None
        ),
        "recovery_manifest_sha256": (
            sha256_file(recovery_manifest_path)
            if recovery_manifest is not None
            else None
        ),
        "reconstruction_parameter_change_count": 0,
        "learning_runs_started": 0,
        "new_inference_runs": 0,
    }
    atomic_text(
        STAGE_META_DIR / f"{stage_id}.roofer.json",
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
    )
    print(json.dumps(payload, ensure_ascii=False))


def run_val3dity(
    cityjson: Path,
    report: Path,
    log_path: Path,
) -> tuple[dict[str, bool], int]:
    report.parent.mkdir(parents=True, exist_ok=True)
    process = subprocess.run(
        ["val3dity", cityjson.as_posix(), "--report", report.as_posix()],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    atomic_text(
        log_path,
        (
            f"+ val3dity {cityjson} --report {report}\n"
            f"{process.stdout or ''}"
        ),
    )
    if not report.is_file():
        raise RuntimeError(
            f"val3dity report missing stage={cityjson.stem} "
            f"exit={process.returncode}"
        )
    payload = json.loads(report.read_text(encoding="utf-8"))
    valid = {
        str(feature.get("id")): bool(feature.get("validity"))
        for feature in payload.get("features", [])
        if feature.get("id") is not None
    }
    return valid, int(process.returncode)


def parse_attributes(jsonl_dir: Path, w2: Any) -> dict[str, dict[str, Any]]:
    return w2.parse_roofer_features(sorted(jsonl_dir.glob("*.city.jsonl")))


def common_measurement(
    stage: Mapping[str, Any],
    building_id: str,
    point: Mapping[str, str],
    ladder: Mapping[str, str],
) -> dict[str, Any]:
    return {
        "stage_index": stage["stage_index"],
        "stage_id": stage["stage_id"],
        "stage_axis": stage["axis"],
        "nominal_sigma_m": stage["sigma_m"],
        "nominal_retention": stage["retention"],
        "is_combination": stage["is_combination"],
        "building_id": building_id,
        "population_scope": "canonical_raw_lidar_assembled_178",
        "cell_label": ladder["cell_label"],
        "small_lt50": as_bool(ladder["small_lt50"]),
        "ref_roof_type": ladder["ref_roof_type"],
        "ref_roof_slope_group": ladder["ref_roof_slope_group"],
        "pilot10": building_id in PILOT_IDS,
        **{field: point.get(field, "") for field in POINT_FIELDS[3:]},
        "perturbation_scope": PERTURBATION_SCOPE,
        "crs": CRS,
        "gt_role": GT_ROLE,
        "learning_runs_started": 0,
        "new_inference_runs": 0,
    }


def score_stage(stage_id: str) -> None:
    if stage_id not in STAGE_BY_ID:
        raise KeyError(stage_id)
    stage = STAGE_BY_ID[stage_id]
    population, _ = load_population()
    ladder = load_ladder(population)
    point_rows = read_csv(POINT_DIR / f"{stage_id}.csv")
    points = {row["building_id"]: row for row in point_rows}
    if len(point_rows) != EXPECTED_POPULATION or set(points) != set(population):
        raise RuntimeError(f"point metrics population drift stage={stage_id}")

    sys.path.insert(0, str(SCORER_SCRIPT.parent))
    metric = load_module(
        f"degradation_metric_{stage_id}", SCORER_SCRIPT
    )
    baseline_module = load_module(
        f"degradation_baseline_{stage_id}", BASELINE_SCORER_SCRIPT
    )
    w2 = load_module(f"degradation_w2_{stage_id}", W2_SCRIPT)
    refs = metric.parse_lod2_roofs(LOD2_DIR, set(population))
    if any(not refs.get(building_id) for building_id in population):
        raise RuntimeError("reference RoofSurface missing")

    if stage_id == "baseline":
        baseline = load_baseline_rows(population)
        attributes = parse_attributes(CANONICAL_ALS_JSONL_DIR, w2)
        rows: list[dict[str, Any]] = []
        for building_id in population:
            source = baseline[building_id]
            attrs = dict(attributes.get(building_id, {}).get("attributes", {}))
            row = common_measurement(
                stage, building_id, points[building_id], ladder[building_id]
            )
            row.update(
                {
                    "rf_success": attrs.get("rf_success", ""),
                    "rf_extrusion_mode": source["rf_extrusion_mode"],
                    "rf_pointcloud_unusable": attrs.get(
                        "rf_pointcloud_unusable", ""
                    ),
                    "rf_roof_type": attrs.get("rf_roof_type", ""),
                    "rf_pt_density": attrs.get("rf_pt_density", ""),
                    "rf_nodata_frac": attrs.get("rf_nodata_frac", ""),
                    "rf_rmse_lod22": source["status_rf_rmse_lod22"],
                    "rf_roof_planes": attrs.get("rf_roof_planes", ""),
                    "rf_reconstruction_time_s": (
                        float(attrs["rf_t_run"]) / 1000.0
                        if attrs.get("rf_t_run") not in (None, "")
                        else None
                    ),
                    "assembly_status": source["status"],
                    "assembly_success": as_bool(source["has_lod22"]),
                    "has_lod22": as_bool(source["has_lod22"]),
                    "lod1_fallback": as_bool(source["lod1_fallback"]),
                    "val3dity_valid": as_bool(
                        source["val3dity_valid"]
                    ),
                    "roof_face_count_model": as_int(
                        source["roof_face_count_model"]
                    ),
                    "roof_face_count_ref": as_int(
                        source["roof_face_count_ref"]
                    ),
                    "face_count_ratio": as_float(
                        source["face_count_ratio"]
                    ),
                    "roof_rms_m": as_float(source["roof_rms_m"]),
                    "roof_hausdorff_m": as_float(
                        source["roof_hausdorff_m"]
                    ),
                    "roof_distance_samples": as_int(
                        source["roof_distance_samples"]
                    ),
                    "roof_completeness": as_float(
                        source["roof_completeness"]
                    ),
                    "model_roof_xy_area_m2": as_float(
                        source["model_roof_xy_area_m2"]
                    ),
                    "reference_roof_xy_area_m2": as_float(
                        source["reference_roof_xy_area_m2"]
                    ),
                    "roof_overlap_xy_area_m2": as_float(
                        source["roof_overlap_xy_area_m2"]
                    ),
                    "geometry_roof_surface_present": as_bool(
                        source["geometry_roof_surface_present"]
                    ),
                    "cityjson_path": rel(CANONICAL_ALS_CITYJSON),
                    "cityjson_sha256": sha256_file(
                        CANONICAL_ALS_CITYJSON
                    ),
                    "val3dity_report": source["val3dity_report"],
                    "assembly_artifact_reused": True,
                    "assembly_pipeline": (
                        "canonical accepted Roofer default zero-stage output"
                    ),
                }
            )
            rows.append(row)
        val_exit = 0
        cityjson = CANONICAL_ALS_CITYJSON
        val_report = Path(rows[0]["val3dity_report"])
        if not val_report.is_absolute():
            val_report = REPO / val_report
    else:
        jsonl_dir = ROOFER_DIR / stage_id
        jsonl_files = sorted(jsonl_dir.glob("*.city.jsonl"))
        if not jsonl_files:
            raise RuntimeError(f"Roofer output missing stage={stage_id}")
        cityjson = CITYJSON_DIR / f"{stage_id}.city.json"
        cityjson.parent.mkdir(parents=True, exist_ok=True)
        w2.combine_cityjsonseq(jsonl_files, cityjson)
        val_report = VAL_DIR / f"{stage_id}.json"
        valid_by_id, val_exit = run_val3dity(
            cityjson, val_report, VAL_DIR / f"{stage_id}.log"
        )
        attributes = parse_attributes(jsonl_dir, w2)
        predictions = metric.parse_cityjson_roofs(
            cityjson, set(population)
        )
        cityjson_sha = sha256_file(cityjson)
        baseline_module.cityjson_crs(cityjson)
        rows = []
        for building_id in population:
            feature = attributes.get(building_id, {})
            attrs = dict(feature.get("attributes", {}))
            prediction = list(predictions.get(building_id, []))
            reference = list(refs[building_id])
            comparison = metric.compare_building(reference, prediction)
            coverage = baseline_module.roof_xy_coverage(
                reference, prediction
            )
            extrusion = str(attrs.get("rf_extrusion_mode", ""))
            has_lod22 = bool(feature.get("has_lod22", False))
            fallback = extrusion == "lod11_fallback"
            model_faces = 1 if fallback else len(prediction)
            row = common_measurement(
                stage, building_id, points[building_id], ladder[building_id]
            )
            row.update(
                {
                    "rf_success": attrs.get("rf_success", ""),
                    "rf_extrusion_mode": extrusion,
                    "rf_pointcloud_unusable": attrs.get(
                        "rf_pointcloud_unusable", ""
                    ),
                    "rf_roof_type": attrs.get("rf_roof_type", ""),
                    "rf_pt_density": attrs.get("rf_pt_density", ""),
                    "rf_nodata_frac": attrs.get("rf_nodata_frac", ""),
                    "rf_rmse_lod22": attrs.get("rf_rmse_lod22", ""),
                    "rf_roof_planes": attrs.get("rf_roof_planes", ""),
                    "rf_reconstruction_time_s": (
                        float(attrs["rf_t_run"]) / 1000.0
                        if attrs.get("rf_t_run") not in (None, "")
                        else None
                    ),
                    "assembly_status": (
                        "lod22_geometry_present"
                        if has_lod22
                        else "lod22_geometry_absent"
                    ),
                    "assembly_success": has_lod22,
                    "has_lod22": has_lod22,
                    "lod1_fallback": fallback,
                    "val3dity_valid": bool(
                        valid_by_id.get(building_id, False)
                    ),
                    "roof_face_count_model": model_faces,
                    "roof_face_count_ref": len(reference),
                    "face_count_ratio": (
                        model_faces / len(reference)
                        if len(reference)
                        else None
                    ),
                    "roof_rms_m": comparison["ref_rms_m"],
                    "roof_hausdorff_m": comparison[
                        "ref_hausdorff_m"
                    ],
                    "roof_distance_samples": comparison[
                        "ref_distance_samples"
                    ],
                    **coverage,
                    "geometry_roof_surface_present": bool(prediction),
                    "cityjson_path": rel(cityjson),
                    "cityjson_sha256": cityjson_sha,
                    "val3dity_report": rel(val_report),
                    "assembly_artifact_reused": False,
                    "assembly_pipeline": (
                        "pinned Roofer default plus canonical score path"
                    ),
                }
            )
            rows.append(row)
    if len(rows) != EXPECTED_POPULATION:
        raise RuntimeError(f"stage score row drift {stage_id} {len(rows)}")
    if any(
        row["learning_runs_started"] != 0
        or row["new_inference_runs"] != 0
        for row in rows
    ):
        raise RuntimeError("learning/inference flag drift")
    score_path = STAGE_SCORE_DIR / f"{stage_id}.csv"
    atomic_csv(score_path, rows, MEASUREMENT_FIELDS)
    stage_manifest = {
        "schema": "jointbuildgs.degradation_curve.score_stage.v3",
        "created_utc": now(),
        "stage": stage_payload(stage),
        "measurement_rows": len(rows),
        "measurement_csv": rel(score_path),
        "measurement_csv_sha256": sha256_file(score_path),
        "assembly_count": sum(bool(row["assembly_success"]) for row in rows),
        "lod1_fallback_count": sum(
            bool(row["lod1_fallback"]) for row in rows
        ),
        "val3dity_valid_count": sum(
            bool(row["val3dity_valid"]) for row in rows
        ),
        "cityjson": rel(cityjson),
        "cityjson_sha256": sha256_file(cityjson),
        "val3dity_report": (
            rel(val_report) if val_report.is_relative_to(REPO) else str(val_report)
        ),
        "val3dity_exit_code": val_exit,
        "assembly_artifact_reused": stage_id == "baseline",
        "learning_runs_started": 0,
        "new_inference_runs": 0,
    }
    atomic_text(
        STAGE_META_DIR / f"{stage_id}.score.json",
        json.dumps(stage_manifest, ensure_ascii=False, indent=2) + "\n",
    )
    print(json.dumps(stage_manifest, ensure_ascii=False))


def diagnose_zero_rerun(jsonl_dir: Path) -> None:
    if not jsonl_dir.is_dir():
        raise FileNotFoundError(jsonl_dir)
    population, _ = load_population()
    sys.path.insert(0, str(SCORER_SCRIPT.parent))
    metric = load_module("degradation_diag_metric", SCORER_SCRIPT)
    baseline_module = load_module(
        "degradation_diag_baseline", BASELINE_SCORER_SCRIPT
    )
    w2 = load_module("degradation_diag_w2", W2_SCRIPT)
    cityjson = RUNTIME / "diagnostic_zero_rerun.city.json"
    cityjson.parent.mkdir(parents=True, exist_ok=True)
    w2.combine_cityjsonseq(sorted(jsonl_dir.glob("*.city.jsonl")), cityjson)
    refs = metric.parse_lod2_roofs(LOD2_DIR, set(population))
    predictions = metric.parse_cityjson_roofs(cityjson, set(population))
    baseline = load_baseline_rows(population)
    mismatch_rows: list[dict[str, Any]] = []
    measured_rms: list[float] = []
    pilot_rms: list[float] = []
    for building_id in population:
        comparison = metric.compare_building(
            refs[building_id], predictions.get(building_id, [])
        )
        coverage = baseline_module.roof_xy_coverage(
            refs[building_id], predictions.get(building_id, [])
        )
        measured = {
            "roof_rms_m": comparison["ref_rms_m"],
            "roof_hausdorff_m": comparison["ref_hausdorff_m"],
            "roof_completeness": coverage["roof_completeness"],
        }
        for metric_name, value in measured.items():
            expected = as_float(baseline[building_id][metric_name])
            if value is None or expected is None:
                if value != expected:
                    mismatch_rows.append(
                        {
                            "building_id": building_id,
                            "metric": metric_name,
                            "observed": value,
                            "expected": expected,
                            "delta": None,
                        }
                    )
            elif abs(float(value) - expected) > 5e-9:
                mismatch_rows.append(
                    {
                        "building_id": building_id,
                        "metric": metric_name,
                        "observed": value,
                        "expected": expected,
                        "delta": float(value) - expected,
                    }
                )
        if measured["roof_rms_m"] is not None:
            measured_rms.append(float(measured["roof_rms_m"]))
            if building_id in PILOT_IDS:
                pilot_rms.append(float(measured["roof_rms_m"]))
    accepted_rms = [
        float(row["roof_rms_m"]) for row in baseline.values()
    ]
    payload = {
        "schema": "jointbuildgs.degradation_curve.zero_rerun_diagnostic.v3",
        "created_utc": now(),
        "official_zero_stage": False,
        "command_equivalence": (
            "same pinned Roofer image, default parameters, AOI box, raw ALS "
            "directory, and 199-feature footprint GPKG"
        ),
        "jsonl_dir": str(jsonl_dir),
        "jsonl_sha256": {
            path.name: sha256_file(path)
            for path in sorted(jsonl_dir.glob("*.city.jsonl"))
        },
        "population_count": len(population),
        "metric_cell_mismatch_count_tolerance_5e_9": len(mismatch_rows),
        "buildings_with_metric_mismatch": len(
            {row["building_id"] for row in mismatch_rows}
        ),
        "first_mismatches": mismatch_rows[:20],
        "accepted_roof_rms_median_m": float(np.median(accepted_rms)),
        "rerun_roof_rms_median_m": float(np.median(measured_rms)),
        "rerun_minus_accepted_roof_rms_median_m": float(
            np.median(measured_rms) - np.median(accepted_rms)
        ),
        "rerun_pilot10_roof_rms_median_m": float(np.median(pilot_rms)),
        "record_role": (
            "preflight reproducibility observation; accepted frozen artifact "
            "remains the official hard-stop zero stage"
        ),
        "learning_runs_started": 0,
        "new_inference_runs": 0,
    }
    atomic_text(
        ZERO_RERUN_DIAGNOSTIC,
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
    )
    print(json.dumps(payload, ensure_ascii=False))


def verify_stage_measurement(stage_id: str) -> None:
    """Verify a resumable stage measurement before the driver reuses it."""
    if stage_id not in STAGE_BY_ID:
        raise KeyError(stage_id)
    population, _ = load_population()
    measurement_path = STAGE_SCORE_DIR / f"{stage_id}.csv"
    score_meta_path = STAGE_META_DIR / f"{stage_id}.score.json"
    for required in (measurement_path, score_meta_path):
        if not required.is_file():
            raise FileNotFoundError(required)
    rows = read_csv(measurement_path)
    identifiers = [row["building_id"] for row in rows]
    if len(rows) != EXPECTED_POPULATION or identifiers != population:
        raise RuntimeError(f"stage measurement population drift stage={stage_id}")
    if any(row["stage_id"] != stage_id for row in rows):
        raise RuntimeError(f"stage measurement id drift stage={stage_id}")
    if any(
        row["learning_runs_started"] != "0"
        or row["new_inference_runs"] != "0"
        for row in rows
    ):
        raise RuntimeError(f"stage measurement run flag drift stage={stage_id}")
    observed_sha = sha256_file(measurement_path)
    score_meta = json.loads(score_meta_path.read_text(encoding="utf-8"))
    if (
        score_meta.get("measurement_rows") != EXPECTED_POPULATION
        or score_meta.get("measurement_csv") != rel(measurement_path)
        or score_meta.get("measurement_csv_sha256") != observed_sha
        or score_meta.get("learning_runs_started") != 0
        or score_meta.get("new_inference_runs") != 0
    ):
        raise RuntimeError(f"stage score metadata drift stage={stage_id}")
    incident_expected = None
    if RECOVERY_INCIDENT.is_file():
        incident = json.loads(RECOVERY_INCIDENT.read_text(encoding="utf-8"))
        incident_expected = incident.get("preserved_completed_stage_sha256", {}).get(
            stage_id
        )
        if incident_expected is not None and incident_expected != observed_sha:
            raise RuntimeError(f"preserved stage hash drift stage={stage_id}")
    print(
        json.dumps(
            {
                "stage_id": stage_id,
                "measurement_rows": len(rows),
                "measurement_csv_sha256": observed_sha,
                "incident_hash_match": (
                    None if incident_expected is None else True
                ),
                "learning_runs_started": 0,
                "new_inference_runs": 0,
                "verified": True,
            },
            ensure_ascii=False,
        )
    )


def validate_baseline() -> None:
    population, _ = load_population()
    baseline = load_baseline_rows(population)
    rows = read_csv(STAGE_SCORE_DIR / "baseline.csv")
    by_id = {row["building_id"]: row for row in rows}
    if len(rows) != EXPECTED_POPULATION or set(by_id) != set(population):
        raise RuntimeError("zero-stage measurement population drift")
    comparison_fields = [
        "has_lod22",
        "lod1_fallback",
        "val3dity_valid",
        "roof_face_count_model",
        "roof_face_count_ref",
        "face_count_ratio",
        "roof_rms_m",
        "roof_hausdorff_m",
        "roof_distance_samples",
        "roof_completeness",
    ]
    mismatch: list[dict[str, Any]] = []
    max_abs_delta: dict[str, float] = defaultdict(float)
    for building_id in population:
        observed = by_id[building_id]
        expected = baseline[building_id]
        for field in comparison_fields:
            if field in {
                "has_lod22",
                "lod1_fallback",
                "val3dity_valid",
            }:
                match = as_bool(observed[field]) == as_bool(expected[field])
                delta = None
            else:
                left = as_float(observed[field])
                right = as_float(expected[field])
                if left is None or right is None:
                    match = left is None and right is None
                    delta = None
                else:
                    delta = left - right
                    max_abs_delta[field] = max(
                        max_abs_delta[field], abs(delta)
                    )
                    match = abs(delta) <= 5e-9
            if not match:
                mismatch.append(
                    {
                        "building_id": building_id,
                        "metric": field,
                        "observed": observed[field],
                        "expected": expected[field],
                        "delta": delta,
                    }
                )
    if mismatch:
        raise RuntimeError(
            f"zero-stage all-metric mismatch n={len(mismatch)} "
            f"first={mismatch[:3]}"
        )
    all_rms = [
        as_float(row["roof_rms_m"])
        for row in rows
        if as_float(row["roof_rms_m"]) is not None
    ]
    pilot = [row for row in rows if as_bool(row["pilot10"])]
    pilot_rms = [float(row["roof_rms_m"]) for row in pilot]
    pilot_face = [float(row["face_count_ratio"]) for row in pilot]
    pilot_completeness = [
        float(row["roof_completeness"]) for row in pilot
    ]
    payload = {
        "schema": "jointbuildgs.degradation_curve.zero_validation.v3",
        "created_utc": now(),
        "execution_mode": "accepted_artifact_reuse",
        "population_count": len(rows),
        "all_metric_building_cells_compared": (
            len(rows) * len(comparison_fields)
        ),
        "all_metric_mismatch_count": len(mismatch),
        "max_abs_delta_by_metric": dict(max_abs_delta),
        "all": {
            "assembly_count": sum(
                as_bool(row["assembly_success"]) for row in rows
            ),
            "roof_rms_median_m": median(all_rms),
            "roof_rms_median_expected_3dp": 0.421,
            "roof_rms_median_match_3dp": round(median(all_rms), 3)
            == 0.421,
        },
        "pilot10": {
            "population_count": len(pilot),
            "assembly_count": sum(
                as_bool(row["assembly_success"]) for row in pilot
            ),
            "val3dity_valid_count": sum(
                as_bool(row["val3dity_valid"]) for row in pilot
            ),
            "roof_rms_median_m": median(pilot_rms),
            "face_count_ratio_median": median(pilot_face),
            "roof_completeness_median": median(pilot_completeness),
            "expected": {
                "assembly_count": 10,
                "val3dity_valid_count": 9,
                "roof_rms_median_3dp": 0.337,
                "face_count_ratio_median": 1.875,
                "roof_completeness_median_4dp": 0.9999,
            },
        },
        "canonical_cityjson": rel(CANONICAL_ALS_CITYJSON),
        "canonical_cityjson_sha256": sha256_file(
            CANONICAL_ALS_CITYJSON
        ),
        "canonical_score_csv": rel(BASELINE_SCORES),
        "canonical_score_csv_sha256": sha256_file(BASELINE_SCORES),
        "same_command_diagnostic": (
            json.loads(ZERO_RERUN_DIAGNOSTIC.read_text(encoding="utf-8"))
            if ZERO_RERUN_DIAGNOSTIC.is_file()
            else None
        ),
        "hard_stop_passed": True,
        "learning_runs_started": 0,
        "new_inference_runs": 0,
    }
    pilot_payload = payload["pilot10"]
    expected_checks = [
        payload["all"]["assembly_count"] == 178,
        payload["all"]["roof_rms_median_match_3dp"],
        pilot_payload["population_count"] == 10,
        pilot_payload["assembly_count"] == 10,
        pilot_payload["val3dity_valid_count"] == 9,
        round(pilot_payload["roof_rms_median_m"], 3) == 0.337,
        abs(pilot_payload["face_count_ratio_median"] - 1.875) <= 1e-12,
        round(pilot_payload["roof_completeness_median"], 4)
        == 0.9999,
    ]
    if not all(expected_checks):
        raise RuntimeError(f"zero-stage aggregate hard stop {payload}")
    atomic_text(
        ZERO_VALIDATION,
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
    )
    print(json.dumps(payload, ensure_ascii=False))


def stage_ids_for_scope(scope: str) -> list[str]:
    if scope == "noise":
        return [stage["stage_id"] for stage in STAGES[:6]]
    if scope == "full":
        return [stage["stage_id"] for stage in STAGES]
    raise KeyError(scope)


def group_definitions(
    population: Sequence[str],
    ladder: Mapping[str, Mapping[str, str]],
) -> list[tuple[str, str, set[str]]]:
    all_ids = set(population)
    definitions = [("overall", "all", all_ids)]
    for cell_label in (
        "cell_1_assembled",
        "cell_2_anchored",
        "cell_3_outline_only",
        "cell_4_beyond_image",
    ):
        definitions.append(
            (
                "ladder_cell",
                cell_label,
                {
                    building_id
                    for building_id, row in ladder.items()
                    if row["cell_label"] == cell_label
                },
            )
        )
    definitions.extend(
        [
            (
                "size",
                "small_lt50",
                {
                    building_id
                    for building_id, row in ladder.items()
                    if as_bool(row["small_lt50"])
                },
            ),
            (
                "size",
                "non_small_ge50",
                {
                    building_id
                    for building_id, row in ladder.items()
                    if not as_bool(row["small_lt50"])
                },
            ),
        ]
    )
    for slope_group in ("horizontal", "sloped"):
        definitions.append(
            (
                "ref_roof_slope_group",
                slope_group,
                {
                    building_id
                    for building_id, row in ladder.items()
                    if row["ref_roof_slope_group"] == slope_group
                },
            )
        )
    definitions.append(("fixed_subset", "pilot10", set(PILOT_IDS)))
    return definitions


def median_field(rows: Sequence[Mapping[str, str]], field: str) -> float | None:
    values = [
        value
        for value in (as_float(row.get(field)) for row in rows)
        if value is not None
    ]
    return None if not values else float(np.median(values))


def aggregate_row(
    stage: Mapping[str, Any],
    stratum_type: str,
    stratum_value: str,
    member_ids: set[str],
    rows: Sequence[Mapping[str, str]],
) -> dict[str, Any]:
    subset = [row for row in rows if row["building_id"] in member_ids]
    metric_counts = {
        field: sum(as_float(row.get(field)) is not None for row in subset)
        for field in (
            "face_count_ratio",
            "roof_rms_m",
            "roof_hausdorff_m",
            "roof_completeness",
        )
    }
    population_count = len(member_ids)
    return {
        "row_type": "stage_aggregate",
        "stage_index": stage["stage_index"],
        "stage_id": stage["stage_id"],
        "stage_axis": stage["axis"],
        "nominal_sigma_m": stage["sigma_m"],
        "nominal_retention": stage["retention"],
        "is_combination": stage["is_combination"],
        "stratum_type": stratum_type,
        "stratum_value": stratum_value,
        "population_count": population_count,
        "measurement_count": len(subset),
        "assembly_count": sum(
            as_bool(row["assembly_success"]) for row in subset
        ),
        "assembly_rate": (
            sum(as_bool(row["assembly_success"]) for row in subset)
            / population_count
            if population_count
            else None
        ),
        "lod2_count": sum(as_bool(row["has_lod22"]) for row in subset),
        "lod1_fallback_count": sum(
            as_bool(row["lod1_fallback"]) for row in subset
        ),
        "lod1_fallback_rate": (
            sum(as_bool(row["lod1_fallback"]) for row in subset)
            / population_count
            if population_count
            else None
        ),
        "val3dity_valid_count": sum(
            as_bool(row["val3dity_valid"]) for row in subset
        ),
        "val3dity_valid_rate": (
            sum(as_bool(row["val3dity_valid"]) for row in subset)
            / population_count
            if population_count
            else None
        ),
        "face_count_ratio_measurable_count": metric_counts[
            "face_count_ratio"
        ],
        "face_count_ratio_median": median_field(
            subset, "face_count_ratio"
        ),
        "roof_rms_measurable_count": metric_counts["roof_rms_m"],
        "roof_rms_median_m": median_field(subset, "roof_rms_m"),
        "roof_hausdorff_measurable_count": metric_counts[
            "roof_hausdorff_m"
        ],
        "roof_hausdorff_median_m": median_field(
            subset, "roof_hausdorff_m"
        ),
        "roof_completeness_measurable_count": metric_counts[
            "roof_completeness"
        ],
        "roof_completeness_median": median_field(
            subset, "roof_completeness"
        ),
        "degraded_point_count_median": median_field(
            subset, "degraded_point_count"
        ),
        "degraded_point_density_m2_median": median_field(
            subset, "degraded_point_density_m2"
        ),
        "realized_retention_ratio_median": median_field(
            subset, "realized_retention_ratio"
        ),
        "realized_axis_noise_std_m_median": median_field(
            subset, "realized_axis_noise_std_m"
        ),
        "realized_xyz_displacement_rms_m_median": median_field(
            subset, "realized_xyz_displacement_rms_m"
        ),
        "rf_reconstruction_time_s_sum": sum(
            value
            for value in (
                as_float(row.get("rf_reconstruction_time_s"))
                for row in subset
            )
            if value is not None
        ),
        "rf_reconstruction_time_s_median": median_field(
            subset, "rf_reconstruction_time_s"
        ),
        "learning_runs_started": 0,
        "new_inference_runs": 0,
    }


def monotonic_rows(
    aggregates: Sequence[Mapping[str, Any]],
    scope: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    overall = {
        str(row["stage_id"]): row
        for row in aggregates
        if row["stratum_type"] == "overall"
        and row["stratum_value"] == "all"
    }
    axes: list[tuple[str, list[str]]] = [
        (
            "noise",
            [
                "baseline",
                "noise_sigma_0p05",
                "noise_sigma_0p10",
                "noise_sigma_0p20",
                "noise_sigma_0p40",
                "noise_sigma_0p80",
            ],
        )
    ]
    if scope == "full":
        axes.append(
            (
                "density",
                [
                    "baseline",
                    "density_retain_1of2",
                    "density_retain_1of4",
                    "density_retain_1of10",
                    "density_retain_1of20",
                ],
            )
        )
    metrics = [
        ("assembly_rate", "nonincreasing"),
        ("val3dity_valid_rate", "nonincreasing"),
        ("lod1_fallback_rate", "nondecreasing"),
        ("roof_rms_median_m", "nondecreasing"),
        ("roof_hausdorff_median_m", "nondecreasing"),
        ("roof_completeness_median", "nonincreasing"),
        ("face_count_ratio_median", "not_preregistered"),
    ]
    summary_rows: list[dict[str, Any]] = []
    manifest_rows: list[dict[str, Any]] = []
    tolerance = 1e-12
    for axis_name, stage_ids in axes:
        for metric_name, direction in metrics:
            values = [as_float(overall[sid].get(metric_name)) for sid in stage_ids]
            valid = all(value is not None for value in values)
            noninc = bool(valid) and all(
                float(values[index + 1]) <= float(values[index]) + tolerance
                for index in range(len(values) - 1)
            )
            nondec = bool(valid) and all(
                float(values[index + 1]) + tolerance >= float(values[index])
                for index in range(len(values) - 1)
            )
            inversions: list[str] = []
            if valid and direction in {"nonincreasing", "nondecreasing"}:
                for index in range(len(values) - 1):
                    left = float(values[index])
                    right = float(values[index + 1])
                    inversion = (
                        right > left + tolerance
                        if direction == "nonincreasing"
                        else right + tolerance < left
                    )
                    if inversion:
                        inversions.append(
                            f"{stage_ids[index]}->{stage_ids[index + 1]}"
                        )
            expected = (
                noninc
                if direction == "nonincreasing"
                else nondec if direction == "nondecreasing" else None
            )
            record = {
                "axis": axis_name,
                "metric": metric_name,
                "stage_ids": stage_ids,
                "values": values,
                "expected_direction": direction,
                "monotonic_nonincreasing": noninc,
                "monotonic_nondecreasing": nondec,
                "monotonic_expected": expected,
                "inversion_transitions": inversions,
            }
            manifest_rows.append(record)
            summary_rows.append(
                {
                    "row_type": "monotonicity_detection",
                    "stratum_type": "overall",
                    "stratum_value": "all",
                    "validation_axis": axis_name,
                    "validation_metric": metric_name,
                    "expected_direction": direction,
                    "monotonic_nonincreasing": noninc,
                    "monotonic_nondecreasing": nondec,
                    "monotonic_expected": expected,
                    "inversion_transitions": ";".join(inversions),
                    "learning_runs_started": 0,
                    "new_inference_runs": 0,
                }
            )
    return summary_rows, manifest_rows


def zero_validation_summary_rows() -> list[dict[str, Any]]:
    payload = json.loads(ZERO_VALIDATION.read_text(encoding="utf-8"))
    rows: list[dict[str, Any]] = []
    comparisons = [
        (
            "all178",
            "assembly_count",
            "178",
            str(payload["all"]["assembly_count"]),
            payload["all"]["assembly_count"] == 178,
        ),
        (
            "all178",
            "roof_rms_median_3dp",
            "0.421",
            f"{payload['all']['roof_rms_median_m']:.9f}",
            payload["all"]["roof_rms_median_match_3dp"],
        ),
        (
            "pilot10",
            "assembly_count",
            "10",
            str(payload["pilot10"]["assembly_count"]),
            payload["pilot10"]["assembly_count"] == 10,
        ),
        (
            "pilot10",
            "val3dity_valid_count",
            "9",
            str(payload["pilot10"]["val3dity_valid_count"]),
            payload["pilot10"]["val3dity_valid_count"] == 9,
        ),
        (
            "pilot10",
            "roof_rms_median_3dp",
            "0.337",
            f"{payload['pilot10']['roof_rms_median_m']:.9f}",
            round(payload["pilot10"]["roof_rms_median_m"], 3) == 0.337,
        ),
        (
            "pilot10",
            "face_count_ratio_median",
            "1.875",
            f"{payload['pilot10']['face_count_ratio_median']:.9f}",
            abs(payload["pilot10"]["face_count_ratio_median"] - 1.875)
            <= 1e-12,
        ),
        (
            "pilot10",
            "roof_completeness_median_4dp",
            "0.9999",
            f"{payload['pilot10']['roof_completeness_median']:.9f}",
            round(payload["pilot10"]["roof_completeness_median"], 4)
            == 0.9999,
        ),
        (
            "all178",
            "all_metric_mismatch_count",
            "0",
            str(payload["all_metric_mismatch_count"]),
            payload["all_metric_mismatch_count"] == 0,
        ),
    ]
    for scope, metric_name, expected, observed, match in comparisons:
        rows.append(
            {
                "row_type": "zero_stage_reproduction",
                "stage_index": 0,
                "stage_id": "baseline",
                "stage_axis": "baseline",
                "stratum_type": "validation",
                "stratum_value": scope,
                "comparison_scope": scope,
                "comparison_metric": metric_name,
                "comparison_expected": expected,
                "comparison_observed": observed,
                "comparison_match": match,
                "learning_runs_started": 0,
                "new_inference_runs": 0,
            }
        )
    return rows


def marker_stats(
    population: Sequence[str],
    snapshot_by_arm: Mapping[str, Mapping[str, Mapping[str, str]]],
) -> dict[str, Any]:
    dense_rows = [snapshot_by_arm["raw_dense"][bid] for bid in population]
    lidar_rows = [snapshot_by_arm["raw_lidar"][bid] for bid in population]
    return {
        "raw_dense": {
            "source": (
                "docs/regression_input_snapshot.csv arm=raw_dense; read-only"
            ),
            "local_plane_rms_m": quantile_payload(
                as_float(row.get("local_plane_rms_m"))
                for row in dense_rows
            ),
            "pt_density_m2": quantile_payload(
                as_float(row.get("pt_density_m2")) for row in dense_rows
            ),
        },
        "raw_lidar_snapshot": {
            "source": (
                "docs/regression_input_snapshot.csv arm=raw_lidar; read-only"
            ),
            "local_plane_rms_m": quantile_payload(
                as_float(row.get("local_plane_rms_m"))
                for row in lidar_rows
            ),
            "pt_density_m2": quantile_payload(
                as_float(row.get("pt_density_m2")) for row in lidar_rows
            ),
        },
    }


def make_figures(
    aggregates: Sequence[Mapping[str, Any]],
    markers: Mapping[str, Any],
    scope: str,
) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    FIGURE_DIR.mkdir(parents=True, exist_ok=True)
    by_key = {
        (str(row["stage_id"]), str(row["stratum_type"]), str(row["stratum_value"])): row
        for row in aggregates
    }
    blue = "#2463A7"
    orange = "#D67A2C"
    neutral = "#3F4650"
    grid = "#D9DEE5"

    def draw_noise() -> None:
        noise_ids = [
            "baseline",
            "noise_sigma_0p05",
            "noise_sigma_0p10",
            "noise_sigma_0p20",
            "noise_sigma_0p40",
            "noise_sigma_0p80",
        ]
        combo_ids = [
            stage["stage_id"]
            for stage in STAGES
            if stage["is_combination"]
            and stage["stage_id"]
            in {row["stage_id"] for row in aggregates}
        ]
        x = [float(STAGE_BY_ID[sid]["sigma_m"]) for sid in noise_ids]
        overall = [by_key[(sid, "overall", "all")] for sid in noise_ids]
        pilot = [by_key[(sid, "fixed_subset", "pilot10")] for sid in noise_ids]
        fig, axes = plt.subplots(2, 1, figsize=(9.2, 8.2), sharex=True)
        for axis in axes:
            axis.grid(axis="y", color=grid, linewidth=0.7)
            axis.spines[["top", "right"]].set_visible(False)
        axes[0].plot(
            x,
            [as_float(row["assembly_rate"]) for row in overall],
            color=blue,
            marker="o",
            linewidth=2.1,
            label="178-building population",
        )
        axes[0].plot(
            x,
            [as_float(row["assembly_rate"]) for row in pilot],
            color=orange,
            marker="s",
            markerfacecolor="white",
            linestyle="--",
            linewidth=1.4,
            label="Pilot10 subset",
        )
        axes[1].plot(
            x,
            [as_float(row["roof_rms_median_m"]) for row in overall],
            color=blue,
            marker="o",
            linewidth=2.1,
            label="178-building population",
        )
        axes[1].plot(
            x,
            [as_float(row["roof_rms_median_m"]) for row in pilot],
            color=orange,
            marker="s",
            markerfacecolor="white",
            linestyle="--",
            linewidth=1.4,
            label="Pilot10 subset",
        )
        for combo_id in combo_ids:
            combo_x = float(STAGE_BY_ID[combo_id]["sigma_m"])
            label = (
                f"Combination σ={combo_x:g}, "
                f"retain={STAGE_BY_ID[combo_id]['retention']:g}"
            )
            for axis, field in (
                (axes[0], "assembly_rate"),
                (axes[1], "roof_rms_median_m"),
            ):
                value = as_float(
                    by_key[(combo_id, "overall", "all")][field]
                )
                if value is not None:
                    axis.scatter(
                        [combo_x],
                        [value],
                        marker="D",
                        s=54,
                        facecolor="white",
                        edgecolor=neutral,
                        linewidth=1.3,
                        zorder=5,
                        label=label if axis is axes[0] else None,
                    )
        dense = markers["raw_dense"]["local_plane_rms_m"]
        for axis in axes:
            axis.axvspan(
                dense["p25"],
                dense["p75"],
                color=neutral,
                alpha=0.09,
                linewidth=0,
            )
            axis.axvline(
                dense["median"],
                color=neutral,
                linewidth=1.2,
                linestyle=":",
            )
        axes[0].set_ylabel("Assembly rate")
        axes[0].set_ylim(-0.02, 1.04)
        axes[0].set_title("Assembly metrics by Gaussian coordinate-noise stage")
        axes[1].set_ylabel("Median roof RMS [m]")
        axes[1].set_xlabel("Nominal isotropic Gaussian axis σ [m]")
        axes[1].axhline(
            0.3, color=neutral, linewidth=1.0, linestyle="-.", label="0.3 m specification"
        )
        axes[1].axhline(
            1.0, color=neutral, linewidth=1.0, linestyle="--", label="1.0 m specification"
        )
        axes[0].legend(frameon=False, ncol=2, fontsize=8)
        axes[1].legend(frameon=False, ncol=2, fontsize=8)
        fig.text(
            0.01,
            0.005,
            (
                "Dense comparison marker: vertical dotted median and shaded "
                "IQR of raw_dense local_plane_rms_m; source: "
                "regression_input_snapshot.csv."
            ),
            fontsize=7.5,
            color=neutral,
        )
        fig.tight_layout(rect=(0, 0.035, 1, 1))
        fig.savefig(NOISE_FIGURE, dpi=180, bbox_inches="tight")
        plt.close(fig)

    def draw_density() -> None:
        density_ids = [
            "baseline",
            "density_retain_1of2",
            "density_retain_1of4",
            "density_retain_1of10",
            "density_retain_1of20",
        ]
        combo_ids = [
            stage["stage_id"]
            for stage in STAGES
            if stage["is_combination"]
        ]
        overall = [by_key[(sid, "overall", "all")] for sid in density_ids]
        pilot = [by_key[(sid, "fixed_subset", "pilot10")] for sid in density_ids]
        x_overall = [
            as_float(row["degraded_point_density_m2_median"])
            for row in overall
        ]
        x_pilot = [
            as_float(row["degraded_point_density_m2_median"])
            for row in pilot
        ]
        fig, axes = plt.subplots(2, 1, figsize=(9.2, 8.2), sharex=True)
        for axis in axes:
            axis.grid(axis="y", color=grid, linewidth=0.7)
            axis.spines[["top", "right"]].set_visible(False)
        axes[0].plot(
            x_overall,
            [as_float(row["assembly_rate"]) for row in overall],
            color=blue,
            marker="o",
            linewidth=2.1,
            label="178-building population",
        )
        axes[0].plot(
            x_pilot,
            [as_float(row["assembly_rate"]) for row in pilot],
            color=orange,
            marker="s",
            markerfacecolor="white",
            linestyle="--",
            linewidth=1.4,
            label="Pilot10 subset",
        )
        axes[1].plot(
            x_overall,
            [as_float(row["roof_rms_median_m"]) for row in overall],
            color=blue,
            marker="o",
            linewidth=2.1,
            label="178-building population",
        )
        axes[1].plot(
            x_pilot,
            [as_float(row["roof_rms_median_m"]) for row in pilot],
            color=orange,
            marker="s",
            markerfacecolor="white",
            linestyle="--",
            linewidth=1.4,
            label="Pilot10 subset",
        )
        for combo_id in combo_ids:
            overall_row = by_key[(combo_id, "overall", "all")]
            combo_x = as_float(
                overall_row["degraded_point_density_m2_median"]
            )
            label = (
                f"Combination σ={STAGE_BY_ID[combo_id]['sigma_m']:g}, "
                f"retain={STAGE_BY_ID[combo_id]['retention']:g}"
            )
            for axis, field in (
                (axes[0], "assembly_rate"),
                (axes[1], "roof_rms_median_m"),
            ):
                value = as_float(overall_row[field])
                if combo_x is not None and value is not None:
                    axis.scatter(
                        [combo_x],
                        [value],
                        marker="D",
                        s=54,
                        facecolor="white",
                        edgecolor=neutral,
                        linewidth=1.3,
                        zorder=5,
                        label=label if axis is axes[0] else None,
                    )
        dense = markers["raw_dense"]["pt_density_m2"]
        for axis in axes:
            axis.axvspan(
                dense["p25"],
                dense["p75"],
                color=neutral,
                alpha=0.09,
                linewidth=0,
            )
            axis.axvline(
                dense["median"],
                color=neutral,
                linewidth=1.2,
                linestyle=":",
            )
        axes[0].invert_xaxis()
        axes[0].set_ylabel("Assembly rate")
        axes[0].set_ylim(-0.02, 1.04)
        axes[0].set_title("Assembly metrics by roof-point density stage")
        axes[1].set_ylabel("Median roof RMS [m]")
        axes[1].set_xlabel(
            "Median degraded roof-point density [pt/m²]"
        )
        axes[1].axhline(
            0.3, color=neutral, linewidth=1.0, linestyle="-.", label="0.3 m specification"
        )
        axes[1].axhline(
            1.0, color=neutral, linewidth=1.0, linestyle="--", label="1.0 m specification"
        )
        axes[0].legend(frameon=False, ncol=2, fontsize=8)
        axes[1].legend(frameon=False, ncol=2, fontsize=8)
        fig.text(
            0.01,
            0.005,
            (
                "Dense comparison marker: vertical dotted median and shaded "
                "IQR of raw_dense pt_density_m2; source: "
                "regression_input_snapshot.csv."
            ),
            fontsize=7.5,
            color=neutral,
        )
        fig.tight_layout(rect=(0, 0.035, 1, 1))
        fig.savefig(DENSITY_FIGURE, dpi=180, bbox_inches="tight")
        plt.close(fig)

    draw_noise()
    if scope == "full":
        draw_density()


def summary_markdown(
    scope: str,
    overall_rows: Sequence[Mapping[str, Any]],
    markers: Mapping[str, Any],
    monotonicity: Sequence[Mapping[str, Any]],
    completed: Sequence[str],
    incomplete: Sequence[str],
    output_hashes: Mapping[str, str],
) -> str:
    zero = json.loads(ZERO_VALIDATION.read_text(encoding="utf-8"))
    lines = [
        "# 열화 곡선 측정 요약 (2026-07-21)",
        "",
        "> 측정·산출 기록. 판정·해석 없음. 학습 0, 신규 추론 0, 이미지 입력 0.",
        "",
        "## 실행 범위",
        "",
        f"- 완료 상태: `{scope}`",
        f"- 모집단: {EXPECTED_POPULATION}동",
        f"- 완료 단계: {len(completed)}/{EXPECTED_STAGE_COUNT}",
        f"- 측정 행: {len(completed) * EXPECTED_POPULATION}/{EXPECTED_MEASUREMENT_ROWS}",
        f"- 미완 단계: {', '.join(incomplete) if incomplete else '없음'}",
        f"- Roofer: `{ROOFER_IMAGE}`",
        f"- 설정: `{ROOFER_PARAMETERS}`",
        f"- 좌표계: `{CRS}`",
        "",
        "## 단계별 전체 모집단 집계",
        "",
        "| 단계 | σ m | 유지율 | LoD2/178 | LoD1 폴백 | val3dity | 지붕면수비 중앙 | RMS 중앙 m | Hausdorff 중앙 m | 완전율 중앙 | 점밀도 중앙 pt/m² |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in overall_rows:
        lines.append(
            "| {stage} | {sigma} | {retention} | {lod2}/178 | {fallback} | "
            "{valid}/178 | {face} | {rms} | {haus} | {complete} | {density} |".format(
                stage=row["stage_id"],
                sigma=format_number(row.get("nominal_sigma_m"), 3),
                retention=format_number(row.get("nominal_retention"), 3),
                lod2=row["lod2_count"],
                fallback=row["lod1_fallback_count"],
                valid=row["val3dity_valid_count"],
                face=format_number(row.get("face_count_ratio_median"), 3),
                rms=format_number(row.get("roof_rms_median_m"), 3),
                haus=format_number(
                    row.get("roof_hausdorff_median_m"), 3
                ),
                complete=format_number(
                    row.get("roof_completeness_median"), 4
                ),
                density=format_number(
                    row.get("degraded_point_density_m2_median"), 3
                ),
            )
        )
    lines.extend(
        [
            "",
            "## 0단 재현 행",
            "",
            "| 범위 | 항목 | 기대 | 측정 | 일치 |",
            "|---|---|---:|---:|---|",
            f"| 178동 | LoD2 | 178/178 | {zero['all']['assembly_count']}/178 | true |",
            f"| 178동 | RMS 중앙 m | 0.421 | {zero['all']['roof_rms_median_m']:.9f} | {str(zero['all']['roof_rms_median_match_3dp']).lower()} |",
            f"| 파일럿10 | LoD2 | 10/10 | {zero['pilot10']['assembly_count']}/10 | true |",
            f"| 파일럿10 | val3dity | 9/10 | {zero['pilot10']['val3dity_valid_count']}/10 | true |",
            f"| 파일럿10 | 면수비 중앙 | 1.875 | {zero['pilot10']['face_count_ratio_median']:.9f} | true |",
            f"| 파일럿10 | RMS 중앙 m | 0.337 | {zero['pilot10']['roof_rms_median_m']:.9f} | true |",
            f"| 파일럿10 | 완전율 중앙 | 0.9999 | {zero['pilot10']['roof_completeness_median']:.9f} | true |",
            f"| 178동×전 지표 | 불일치 셀 | 0 | {zero['all_metric_mismatch_count']} | true |",
            "",
            "0단은 수락된 정본 CityJSON과 확정 채점행을 재사용했다. 같은 잠금 명령의 별도 진단 재실행 수치는 `phases/p2-gsjso/runs/20260721_degradation_curve/zero_rerun_diagnostic.json`에 기록했다.",
            "",
            "## dense 대조 마커",
            "",
            "| 지표 | n | p25 | 중앙 | p75 |",
            "|---|---:|---:|---:|---:|",
        ]
    )
    for metric_name in ("local_plane_rms_m", "pt_density_m2"):
        marker = markers["raw_dense"][metric_name]
        lines.append(
            f"| {metric_name} | {marker['count']} | "
            f"{format_number(marker['p25'], 4)} | "
            f"{format_number(marker['median'], 4)} | "
            f"{format_number(marker['p75'], 4)} |"
        )
    lines.extend(
        [
            "",
            "## 단조성 감지 행",
            "",
            "| 축 | 지표 | 기대 방향 | 기대방향 단조 | 역전 단계 |",
            "|---|---|---|---|---|",
        ]
    )
    for row in monotonicity:
        lines.append(
            f"| {row['axis']} | {row['metric']} | "
            f"{row['expected_direction']} | "
            f"{format_bool(row['monotonic_expected'])} | "
            f"{'; '.join(row['inversion_transitions']) if row['inversion_transitions'] else '없음'} |"
        )
    lines.extend(
        [
            "",
            "## 산출 SHA256",
            "",
            "| 파일 | SHA256 |",
            "|---|---|",
        ]
    )
    for path, digest in sorted(output_hashes.items()):
        lines.append(f"| `{path}` | `{digest}` |")
    lines.extend(
        [
            "",
            "## 실행 플래그",
            "",
            "- `learning_runs_started=0`",
            "- `new_inference_runs=0`",
            "- `image_inputs_used=0`",
            "",
        ]
    )
    return "\n".join(lines)


def format_number(value: Any, digits: int) -> str:
    number = as_float(value)
    return "—" if number is None else f"{number:.{digits}f}"


def format_bool(value: Any) -> str:
    if value is None or value == "":
        return "n/a"
    return "true" if bool(value) else "false"


def finalize(scope: str) -> None:
    completed = stage_ids_for_scope(scope)
    incomplete = [
        stage["stage_id"]
        for stage in STAGES
        if stage["stage_id"] not in completed
    ]
    population, snapshot_by_arm = load_population()
    ladder = load_ladder(population)
    all_rows: list[dict[str, str]] = []
    for stage_id in completed:
        path = STAGE_SCORE_DIR / f"{stage_id}.csv"
        if not path.is_file():
            raise FileNotFoundError(path)
        rows = read_csv(path)
        if (
            len(rows) != EXPECTED_POPULATION
            or {row["building_id"] for row in rows} != set(population)
        ):
            raise RuntimeError(f"stage result drift {stage_id}")
        all_rows.extend(rows)
    all_rows.sort(
        key=lambda row: (
            int(row["stage_index"]),
            row["building_id"],
        )
    )
    expected_rows = len(completed) * EXPECTED_POPULATION
    if len(all_rows) != expected_rows:
        raise RuntimeError(
            f"measurement row drift {len(all_rows)} != {expected_rows}"
        )
    if len(
        {(row["stage_id"], row["building_id"]) for row in all_rows}
    ) != len(all_rows):
        raise RuntimeError("measurement stage-building duplicate")
    atomic_csv(MEASUREMENTS_CSV, all_rows, MEASUREMENT_FIELDS)

    definitions = group_definitions(population, ladder)
    aggregates: list[dict[str, Any]] = []
    by_stage = {
        stage_id: [
            row for row in all_rows if row["stage_id"] == stage_id
        ]
        for stage_id in completed
    }
    for stage_id in completed:
        stage = STAGE_BY_ID[stage_id]
        for stratum_type, stratum_value, member_ids in definitions:
            aggregates.append(
                aggregate_row(
                    stage,
                    stratum_type,
                    stratum_value,
                    member_ids,
                    by_stage[stage_id],
                )
            )
    monotonic_summary, monotonic_manifest = monotonic_rows(
        aggregates, scope
    )
    validation_rows = zero_validation_summary_rows()
    summary_rows = [*aggregates, *validation_rows, *monotonic_summary]
    atomic_csv(SUMMARY_CSV, summary_rows, SUMMARY_FIELDS)

    markers = marker_stats(population, snapshot_by_arm)
    make_figures(aggregates, markers, scope)
    preflight = json.loads(PREFLIGHT_MANIFEST.read_text(encoding="utf-8"))
    zero = json.loads(ZERO_VALIDATION.read_text(encoding="utf-8"))
    base_inventory = read_csv(BASE_INVENTORY)
    stage_meta = {}
    for stage_id in completed:
        score_meta = json.loads(
            (STAGE_META_DIR / f"{stage_id}.score.json").read_text(
                encoding="utf-8"
            )
        )
        input_meta_path = STAGE_META_DIR / f"{stage_id}.input.json"
        roofer_meta_path = STAGE_META_DIR / f"{stage_id}.roofer.json"
        stage_meta[stage_id] = {
            "score": score_meta,
            "input": (
                json.loads(input_meta_path.read_text(encoding="utf-8"))
                if input_meta_path.is_file()
                else {
                    "input_path": [
                        rel(path)
                        for path in sorted(RAW_ALS_DIR.glob("*.laz"))
                    ],
                    "input_sha256": preflight[
                        "raw_als_source_aggregate_sha256"
                    ],
                    "artifact_reused": True,
                }
            ),
            "roofer": (
                json.loads(roofer_meta_path.read_text(encoding="utf-8"))
                if roofer_meta_path.is_file()
                else {
                    "artifact_reused": True,
                    "cityjson": rel(CANONICAL_ALS_CITYJSON),
                    "cityjson_sha256": sha256_file(
                        CANONICAL_ALS_CITYJSON
                    ),
                }
            ),
        }

    output_paths = [
        MEASUREMENTS_CSV,
        SUMMARY_CSV,
        NOISE_FIGURE,
    ]
    if scope == "full":
        output_paths.append(DENSITY_FIGURE)
    preliminary_hashes = {
        rel(path): sha256_file(path) for path in output_paths
    }
    overall_rows = [
        row
        for row in aggregates
        if row["stratum_type"] == "overall"
        and row["stratum_value"] == "all"
    ]
    overall_rows.sort(key=lambda row: int(row["stage_index"]))
    atomic_text(
        SUMMARY_MD,
        summary_markdown(
            scope,
            overall_rows,
            markers,
            monotonic_manifest,
            completed,
            incomplete,
            preliminary_hashes,
        ),
    )
    output_paths.append(SUMMARY_MD)
    output_hashes = {
        rel(path): sha256_file(path) for path in output_paths
    }
    manifest = {
        "schema": "jointbuildgs.degradation_curve.v3",
        "created_utc": now(),
        "completion_status": (
            "complete" if scope == "full" else "partial_noise_axis"
        ),
        "git_head_at_aggregation": git_output("rev-parse", "HEAD"),
        "branch": git_output("branch", "--show-current"),
        "population_definition": preflight["population_definition"],
        "population_count": len(population),
        "population_sha256": preflight["population_sha256"],
        "pilot10": sorted(PILOT_IDS),
        "completed_stage_ids": completed,
        "incomplete_stage_ids": incomplete,
        "stage_count_completed": len(completed),
        "stage_count_expected": EXPECTED_STAGE_COUNT,
        "measurement_rows": len(all_rows),
        "measurement_rows_expected": EXPECTED_MEASUREMENT_ROWS,
        "summary_rows": len(summary_rows),
        "stage_design": preflight["stages"],
        "zero_duplicate_policy": preflight["zero_duplicate_policy"],
        "seed_formula": preflight["seed_formula"],
        "seed_namespace": preflight["seed_namespace"],
        "seed_values": {
            stage_id: preflight["seed_values"][stage_id]
            for stage_id in completed
        },
        "perturbation_scope": PERTURBATION_SCOPE,
        "overlap_owner_rule": OVERLAP_OWNER_RULE,
        "coordinate_operation_order": preflight[
            "coordinate_operation_order"
        ],
        "classification_and_attributes": preflight[
            "classification_and_attributes"
        ],
        "als_raw_source_sha256": preflight["raw_als_source_sha256"],
        "als_raw_source_aggregate_sha256": preflight[
            "raw_als_source_aggregate_sha256"
        ],
        "als_building_roof_evidence": {
            row["building_id"]: {
                "source_files": row["als_source_files"].split(";"),
                "source_file_sha256": row[
                    "als_source_file_sha256"
                ].split(";"),
                "roof_evidence_payload_sha256": row[
                    "als_roof_evidence_payload_sha256"
                ],
                "shared_source_point_count": int(
                    row["shared_source_point_count"]
                ),
                "source_point_count": int(row["source_point_count"]),
            }
            for row in base_inventory
        },
        "stage_artifacts": stage_meta,
        "roofer_image": ROOFER_IMAGE,
        "roofer_parameters": ROOFER_PARAMETERS,
        "roofer_parameter_change_count": 0,
        "assembly_success_definition": (
            "has_lod22 measured from CityJSON parent/child geometry; "
            "lod11_fallback recorded separately"
        ),
        "metrics": [
            "has_lod22",
            "val3dity_valid",
            "face_count_ratio",
            "roof_rms_m",
            "roof_hausdorff_m",
            "roof_completeness",
        ],
        "roof_completeness_definition": (
            "area(union(model roof XY) intersect union(reference roof XY)) "
            "/ area(union(reference roof XY))"
        ),
        "zero_stage_validation": zero,
        "dense_comparison_markers": markers,
        "dense_comparison_role": (
            "read-only marker; no new measurement or inference"
        ),
        "group_definitions": {
            "ladder_cell": rel(LADDER),
            "size": "small_lt50 from boundary_map_v4_1_ladder.csv",
            "ref_roof_slope_group": (
                "classification-only ref_roof_slope_group from "
                "boundary_map_v4_1_ladder.csv"
            ),
            "pilot10": (
                "fixed C001 dense-success pilot IDs from preregistration v1.2"
            ),
        },
        "group_counts": preflight["group_counts"],
        "monotonicity_detection": monotonic_manifest,
        "specification_lines_m": [0.3, 1.0],
        "figure_contract": preflight["figure_contract"],
        "crs": CRS,
        "gt_role": GT_ROLE,
        "learning_runs_started": 0,
        "new_inference_runs": 0,
        "image_inputs_used": 0,
        "interpretation_or_verdict": None,
        "tool_versions": preflight["tool_versions"],
        "pipeline_sha256": {
            rel(path): sha256_file(path)
            for path in (
                Path(__file__),
                QA_SCRIPT,
                DRIVER_SCRIPT,
                RECOVERY_SCRIPT,
                SCORER_SCRIPT,
                BASELINE_SCORER_SCRIPT,
                W2_SCRIPT,
            )
        },
        "source_sha256": preflight["source_sha256"],
        "output_sha256": output_hashes,
        "manifest_self_sha256_recorded_in": "docs/issues.md",
    }
    atomic_text(
        MANIFEST_JSON,
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
    )
    print(
        json.dumps(
            {
                "scope": scope,
                "measurement_rows": len(all_rows),
                "summary_rows": len(summary_rows),
                "completed_stages": len(completed),
                "incomplete_stages": incomplete,
                "manifest": rel(MANIFEST_JSON),
                "learning_runs_started": 0,
                "new_inference_runs": 0,
            },
            ensure_ascii=False,
        )
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("prepare")
    subparsers.add_parser("verify-preflight")
    subparsers.add_parser("build-base")
    make_parser = subparsers.add_parser("make-stage")
    make_parser.add_argument("--stage", required=True, choices=sorted(STAGE_BY_ID))
    clean_parser = subparsers.add_parser("clean-stage-output")
    clean_parser.add_argument("--stage", required=True, choices=sorted(STAGE_BY_ID))
    record_parser = subparsers.add_parser("record-roofer")
    record_parser.add_argument("--stage", required=True, choices=sorted(STAGE_BY_ID))
    record_parser.add_argument("--wall-seconds", type=float, required=True)
    score_parser = subparsers.add_parser("score-stage")
    score_parser.add_argument("--stage", required=True, choices=sorted(STAGE_BY_ID))
    verify_stage_parser = subparsers.add_parser("verify-stage-measurement")
    verify_stage_parser.add_argument(
        "--stage", required=True, choices=sorted(STAGE_BY_ID)
    )
    diagnostic = subparsers.add_parser("diagnose-zero-rerun")
    diagnostic.add_argument("--jsonl-dir", type=Path, required=True)
    subparsers.add_parser("validate-baseline")
    finalize_parser = subparsers.add_parser("finalize")
    finalize_parser.add_argument("--scope", choices=("noise", "full"), required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.command == "prepare":
        prepare()
    elif args.command == "verify-preflight":
        verify_preflight()
    elif args.command == "build-base":
        build_base()
    elif args.command == "make-stage":
        make_stage(args.stage)
    elif args.command == "clean-stage-output":
        clean_stage_output(args.stage)
    elif args.command == "record-roofer":
        record_roofer(args.stage, args.wall_seconds)
    elif args.command == "score-stage":
        score_stage(args.stage)
    elif args.command == "verify-stage-measurement":
        verify_stage_measurement(args.stage)
    elif args.command == "diagnose-zero-rerun":
        diagnose_zero_rerun(args.jsonl_dir)
    elif args.command == "validate-baseline":
        validate_baseline()
    elif args.command == "finalize":
        finalize(args.scope)
    else:
        raise AssertionError(args.command)


if __name__ == "__main__":
    main()
