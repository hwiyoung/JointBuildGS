#!/usr/bin/env python3
"""R3: rescore the canonical 178-building dense/ALS baselines.

This is a learning-zero, inference-zero measurement over existing products.
The evaluation population is locked to the ``raw_lidar`` rows with
``assembled=true`` in ``docs/experiments/evaluation/attr_outcome_regression/tables/regression_input_snapshot.csv``.  Dense(w2_1),
ALS(w2_1), and reference self-check rows use the same CityJSON roof parser and
vertical-distance implementation as the C001 A-wave rescore.

The dense input was shifted by -0.174 m before its original Roofer assembly.
Both assembled baseline CityJSON files are already in EPSG:25832, so the
additional score-time shift is fixed to 0.0 m, matching the A-wave rule for
canonical dense and ALS baselines.
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
import os
import subprocess
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib")
os.environ.setdefault("XDG_CACHE_HOME", "/tmp")

import matplotlib
import numpy as np
from shapely.ops import unary_union

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402


REPO = Path(__file__).resolve().parents[3]
SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import e5_c001_8way as metric  # noqa: E402


RUN_ID = "20260718_qs_baseline178_rescore"
RUN_DIR = REPO / "phases/p2-gsjso/runs" / RUN_ID
VAL_DIR = RUN_DIR / "val3dity"
RUN_LOG = RUN_DIR / "run.log"

DOCS = REPO / "docs"
SCORES_CSV = DOCS / "qs_baseline178_scores.csv"
SUMMARY_CSV = DOCS / "qs_baseline178_summary.csv"
MANIFEST = DOCS / "qs_baseline178_manifest.json"
FIGURE = DOCS / "figs/qs_baseline178/dense_vs_als_rms_distribution.png"

SNAPSHOT = DOCS / "regression_input_snapshot.csv"
STATUS_CSV = (
    REPO
    / "phases/p0-audit/runs/w2_1_roofer_default_20260612_152729"
    / "building_reconstruction_status.csv"
)
DENSE_CITYJSON = (
    REPO
    / "phases/p0-audit/runs/w2_1_roofer_default_20260612_152729"
    / "cityjson/dim_roofer.city.json"
)
ALS_CITYJSON = (
    REPO
    / "phases/p0-audit/runs/w2_1_roofer_default_20260612_152729"
    / "cityjson/als_roofer.city.json"
)
LOD2_DIR = REPO / "phases/p0-audit/data/raw/lod2"
A_SCORE_SCRIPT = REPO / "scripts/evaluation/quality_score/overnight_qs_rescore.py"
METRIC_SCRIPT = REPO / "scripts/e5_c001/e5_c001_8way.py"
W2_SCRIPT = REPO / "phases/p0-audit/scripts/08_roofer_w2.py"

CRS = "EPSG:25832"
SCORE_TIME_Z_SHIFT_M = 0.0
DENSE_PREASSEMBLY_Z_SHIFT_M = -0.174
EXPECTED_POPULATION = 178
EXPECTED_DENSE_LOD2 = 114
EXPECTED_ALS_LOD2 = 178

MODEL_SPECS = (
    {
        "model_id": "canonical_dense_w2_1",
        "role": "dense",
        "status_input": "DIM",
        "snapshot_arm": "raw_dense",
        "cityjson": DENSE_CITYJSON,
        "source_preassembly_z_shift_m": DENSE_PREASSEMBLY_Z_SHIFT_M,
    },
    {
        "model_id": "als_w2_1",
        "role": "als",
        "status_input": "ALS",
        "snapshot_arm": "raw_lidar",
        "cityjson": ALS_CITYJSON,
        "source_preassembly_z_shift_m": 0.0,
    },
    {
        "model_id": "reference_lod2",
        "role": "reference",
        "status_input": "",
        "snapshot_arm": "",
        "cityjson": None,
        "source_preassembly_z_shift_m": 0.0,
    },
)

SCORE_FIELDS = [
    "model_id",
    "role",
    "building_id",
    "population_source",
    "status",
    "status_reason",
    "rf_extrusion_mode",
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
    "snapshot_assembled",
    "old_status_has_lod22",
    "status_agreement",
    "status_rf_rmse_lod22",
    "cityjson_path",
    "cityjson_sha256",
    "cityjson_crs",
    "status_path",
    "val3dity_report",
    "val3dity_exit_code",
    "xy_alignment",
    "xy_overlap_ratio",
    "source_preassembly_z_shift_m",
    "z_shift_to_reference_m",
    "z_shift_rule",
    "gt_role",
    "learning_runs_started",
    "new_inference_runs",
]

SUMMARY_FIELDS = [
    "row_type",
    "model_id",
    "role",
    "population_count",
    "lod2_count",
    "lod2_failure_count",
    "val3dity_valid_count",
    "face_count_ratio_measurable_count",
    "face_count_ratio_min",
    "face_count_ratio_p10",
    "face_count_ratio_p25",
    "face_count_ratio_median",
    "face_count_ratio_p75",
    "face_count_ratio_p90",
    "face_count_ratio_max",
    "roof_rms_measurable_count",
    "roof_rms_min_m",
    "roof_rms_p10_m",
    "roof_rms_p25_m",
    "roof_rms_median_m",
    "roof_rms_p75_m",
    "roof_rms_p90_m",
    "roof_rms_max_m",
    "roof_completeness_measurable_count",
    "roof_completeness_min",
    "roof_completeness_p10",
    "roof_completeness_p25",
    "roof_completeness_median",
    "roof_completeness_p75",
    "roof_completeness_p90",
    "roof_completeness_max",
    "status_agreement_count",
    "status_disagreement_count",
    "status_agreement_rate",
    "snapshot_assembled_count",
    "old_status_has_lod22_count",
    "status_disagreement_building_ids",
    "reference_self_rms_zero_count",
    "reference_self_completeness_one_count",
    "learning_runs_started",
    "new_inference_runs",
]


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def rel(path: Path | None) -> str:
    if path is None:
        return ""
    try:
        return str(path.resolve().relative_to(REPO.resolve()))
    except ValueError:
        return str(path.resolve())


def sha256_file(path: Path, block_size: int = 1 << 20) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(block_size), b""):
            digest.update(block)
    return digest.hexdigest()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def bool_value(value: Any) -> bool:
    return str(value).strip().lower() in {"true", "1", "yes", "y"}


def number(value: Any) -> float | None:
    try:
        if value in ("", None, "None", "none", "nan"):
            return None
        parsed = float(value)
        return parsed if math.isfinite(parsed) else None
    except (TypeError, ValueError):
        return None


def format_value(value: Any) -> Any:
    if value is None:
        return ""
    if isinstance(value, bool):
        return str(value).lower()
    if isinstance(value, (float, np.floating)):
        return "" if not math.isfinite(float(value)) else f"{float(value):.9f}"
    return value


def atomic_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(text, encoding="utf-8")
    os.replace(temporary, path)


def atomic_csv(
    path: Path,
    rows: Sequence[Mapping[str, Any]],
    fields: Sequence[str],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=list(fields),
            extrasaction="ignore",
            lineterminator="\n",
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {field: format_value(row.get(field)) for field in fields}
            )
    os.replace(temporary, path)


def log(message: str) -> None:
    line = f"{now()} {message}"
    RUN_LOG.parent.mkdir(parents=True, exist_ok=True)
    with RUN_LOG.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    print(line, flush=True)


def load_population() -> tuple[list[str], dict[str, dict[str, dict[str, str]]]]:
    rows = read_csv(SNAPSHOT)
    by_arm: dict[str, dict[str, dict[str, str]]] = defaultdict(dict)
    for row in rows:
        arm = row.get("arm", "")
        building_id = row.get("building_id", "")
        if building_id:
            if building_id in by_arm[arm]:
                raise RuntimeError(f"duplicate snapshot row arm={arm} id={building_id}")
            by_arm[arm][building_id] = row
    population = sorted(
        building_id
        for building_id, row in by_arm["raw_lidar"].items()
        if bool_value(row.get("assembled"))
    )
    if len(population) != EXPECTED_POPULATION or len(set(population)) != len(
        population
    ):
        raise RuntimeError(
            f"canonical population drift rows={len(population)} "
            f"unique={len(set(population))}"
        )
    population_set = set(population)
    for arm in ("raw_dense", "raw_lidar"):
        missing = sorted(population_set - set(by_arm[arm]))
        if missing:
            raise RuntimeError(
                f"snapshot arm={arm} missing canonical ids: {missing}"
            )
    missing_ref_planes = [
        building_id
        for building_id in population
        if number(by_arm["raw_lidar"][building_id].get("ref_roof_planes"))
        in (None, 0.0)
    ]
    if missing_ref_planes:
        raise RuntimeError(
            f"canonical reference-roof counts missing: {missing_ref_planes}"
        )
    return population, by_arm


def load_status(
    population: Sequence[str],
) -> dict[str, dict[str, dict[str, str]]]:
    wanted = set(population)
    output: dict[str, dict[str, dict[str, str]]] = {
        "DIM": {},
        "ALS": {},
    }
    for row in read_csv(STATUS_CSV):
        label = row.get("input", "")
        building_id = row.get("building_id", "")
        if label not in output or building_id not in wanted:
            continue
        if building_id in output[label]:
            raise RuntimeError(f"duplicate status row input={label} id={building_id}")
        output[label][building_id] = row
    for label in output:
        missing = sorted(wanted - set(output[label]))
        extra = sorted(set(output[label]) - wanted)
        if missing or extra:
            raise RuntimeError(
                f"status population drift input={label} "
                f"missing={missing} extra={extra}"
            )
    counts = {
        label: sum(
            bool_value(row.get("has_lod22")) for row in output[label].values()
        )
        for label in output
    }
    if counts["DIM"] != EXPECTED_DENSE_LOD2:
        raise RuntimeError(f"DIM has_lod22 drift {counts['DIM']}")
    if counts["ALS"] != EXPECTED_ALS_LOD2:
        raise RuntimeError(f"ALS has_lod22 drift {counts['ALS']}")
    return output


def cityjson_crs(path: Path) -> str:
    payload = json.loads(path.read_text(encoding="utf-8"))
    reference_system = str(
        (payload.get("metadata") or {}).get("referenceSystem", "")
    )
    if not reference_system.endswith("/25832") and reference_system != CRS:
        raise RuntimeError(
            f"CityJSON CRS mismatch path={rel(path)} crs={reference_system}"
        )
    return reference_system


def cityjson_lod22_presence(
    path: Path,
    population: Sequence[str],
) -> dict[str, bool]:
    """Measure LoD 2.2 presence directly from parent/child CityObjects."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    cityobjects = payload.get("CityObjects") or {}
    measured: dict[str, bool] = {}
    for building_id in population:
        parent = cityobjects.get(building_id) or {}
        object_ids = [building_id, *(parent.get("children") or [])]
        measured[building_id] = any(
            str(geometry.get("lod")) == "2.2"
            for object_id in object_ids
            for geometry in (cityobjects.get(object_id) or {}).get(
                "geometry", []
            )
        )
    return measured


def run_val3dity(path: Path) -> tuple[dict[str, bool], Path, int]:
    digest = sha256_file(path)
    report = VAL_DIR / f"{digest}.json"
    report_log = VAL_DIR / f"{digest}.log"
    report.parent.mkdir(parents=True, exist_ok=True)
    process = subprocess.run(
        ["val3dity", path.as_posix(), "--report", report.as_posix()],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    atomic_text(
        report_log,
        f"+ val3dity {path} --report {report}\n{process.stdout or ''}",
    )
    if not report.is_file():
        raise RuntimeError(
            f"val3dity report missing exit={process.returncode} path={rel(path)}"
        )
    payload = json.loads(report.read_text(encoding="utf-8"))
    valid = {
        str(feature.get("id")): bool(feature.get("validity"))
        for feature in payload.get("features", [])
        if feature.get("id") is not None
    }
    return valid, report, int(process.returncode)


def roof_xy_coverage(
    refs: Sequence[Any],
    predictions: Sequence[Any],
) -> dict[str, float | None]:
    ref_polygons = [
        polygon
        for surface in refs
        for polygon in metric.flatten_polygons(surface.polygon)
    ]
    model_polygons = [
        polygon
        for surface in predictions
        for polygon in metric.flatten_polygons(surface.polygon)
    ]
    if not ref_polygons:
        return {
            "roof_completeness": None,
            "model_roof_xy_area_m2": None,
            "reference_roof_xy_area_m2": None,
            "roof_overlap_xy_area_m2": None,
        }
    ref_union = unary_union(ref_polygons)
    reference_area = float(ref_union.area)
    if reference_area <= 0:
        return {
            "roof_completeness": None,
            "model_roof_xy_area_m2": None,
            "reference_roof_xy_area_m2": reference_area,
            "roof_overlap_xy_area_m2": None,
        }
    if not model_polygons:
        return {
            "roof_completeness": 0.0,
            "model_roof_xy_area_m2": 0.0,
            "reference_roof_xy_area_m2": reference_area,
            "roof_overlap_xy_area_m2": 0.0,
        }
    model_union = unary_union(model_polygons)
    model_area = float(model_union.area)
    overlap_area = float(model_union.intersection(ref_union).area)
    completeness = min(1.0, max(0.0, overlap_area / reference_area))
    return {
        "roof_completeness": completeness,
        "model_roof_xy_area_m2": model_area,
        "reference_roof_xy_area_m2": reference_area,
        "roof_overlap_xy_area_m2": overlap_area,
    }


def xy_check(
    refs: Sequence[Any],
    predictions: Sequence[Any],
) -> tuple[str, float | None]:
    if not predictions:
        return "no_roof_geometry", None
    ref_union = unary_union(
        [
            polygon
            for surface in refs
            for polygon in metric.flatten_polygons(surface.polygon)
        ]
    )
    model_union = unary_union(
        [
            polygon
            for surface in predictions
            for polygon in metric.flatten_polygons(surface.polygon)
        ]
    )
    if ref_union.is_empty or model_union.is_empty:
        return "empty_union", None
    overlap = float(model_union.intersection(ref_union.buffer(1.0)).area)
    ratio = overlap / max(float(model_union.area), 1e-9)
    return ("aligned" if ratio >= 0.5 else "low_overlap"), ratio


def build_scores(
    population: Sequence[str],
    snapshot_by_arm: Mapping[str, Mapping[str, Mapping[str, str]]],
    status_by_input: Mapping[str, Mapping[str, Mapping[str, str]]],
    refs: Mapping[str, Sequence[Any]],
) -> list[dict[str, Any]]:
    target_set = set(population)
    rows: list[dict[str, Any]] = []
    for spec in MODEL_SPECS:
        model_id = str(spec["model_id"])
        role = str(spec["role"])
        cityjson = spec["cityjson"]
        if role == "reference":
            predictions = {building_id: refs[building_id] for building_id in population}
            valid_by_id = {building_id: True for building_id in population}
            val_report = ""
            val_exit = 0
            cityjson_sha = ""
            reference_system = CRS
        else:
            assert isinstance(cityjson, Path)
            if not cityjson.is_file():
                raise FileNotFoundError(cityjson)
            geometry_lod22 = cityjson_lod22_presence(cityjson, population)
            predictions = metric.parse_cityjson_roofs(cityjson, target_set)
            predictions = {
                building_id: metric.shift_surface_z(
                    list(predictions.get(building_id, [])),
                    SCORE_TIME_Z_SHIFT_M,
                )
                for building_id in population
            }
            valid_by_id, val_path, val_exit = run_val3dity(cityjson)
            val_report = rel(val_path)
            cityjson_sha = sha256_file(cityjson)
            reference_system = cityjson_crs(cityjson)
        log(f"score model={model_id} buildings={len(population)}")
        for building_id in population:
            prediction = list(predictions.get(building_id, []))
            reference = list(refs[building_id])
            comparison = metric.compare_building(reference, prediction)
            coverage = roof_xy_coverage(reference, prediction)
            alignment, overlap_ratio = xy_check(reference, prediction)
            if role == "reference":
                status = {}
                status_name = "reference"
                status_reason = "reference_self_check"
                extrusion_mode = ""
                has_lod22 = True
                fallback = False
                valid = True
                model_faces = len(reference)
                snapshot_assembled: bool | None = None
                old_status_lod2: bool | None = None
                agreement: bool | None = None
                status_path = ""
            else:
                status_input = str(spec["status_input"])
                status = dict(status_by_input[status_input][building_id])
                extrusion_mode = status.get("rf_extrusion_mode", "")
                fallback = extrusion_mode == "lod11_fallback"
                has_lod22 = geometry_lod22[building_id]
                valid = bool(valid_by_id.get(building_id, False))
                model_faces = 1 if fallback else len(prediction)
                status_name = (
                    "lod22_geometry_present"
                    if has_lod22
                    else "lod22_geometry_absent"
                )
                status_reason = (
                    "CityJSON parent/child geometry contains lod=2.2"
                    if has_lod22
                    else "CityJSON parent/child geometry has no lod=2.2"
                )
                snapshot_arm = str(spec["snapshot_arm"])
                snapshot_assembled = bool_value(
                    snapshot_by_arm[snapshot_arm][building_id].get("assembled")
                )
                old_status_lod2 = bool_value(status.get("has_lod22"))
                agreement = has_lod22 == old_status_lod2
                status_path = rel(STATUS_CSV)
            ref_faces = len(reference)
            rows.append(
                {
                    "model_id": model_id,
                    "role": role,
                    "building_id": building_id,
                    "population_source": (
                        "docs/experiments/evaluation/attr_outcome_regression/tables/regression_input_snapshot.csv:"
                        "raw_lidar assembled=true"
                    ),
                    "status": status_name,
                    "status_reason": status_reason,
                    "rf_extrusion_mode": extrusion_mode,
                    "has_lod22": has_lod22,
                    "lod1_fallback": fallback,
                    "val3dity_valid": valid,
                    "roof_face_count_model": model_faces,
                    "roof_face_count_ref": ref_faces,
                    "face_count_ratio": (
                        model_faces / ref_faces if ref_faces else None
                    ),
                    "roof_rms_m": comparison["ref_rms_m"],
                    "roof_hausdorff_m": comparison["ref_hausdorff_m"],
                    "roof_distance_samples": comparison["ref_distance_samples"],
                    **coverage,
                    "geometry_roof_surface_present": bool(prediction),
                    "snapshot_assembled": snapshot_assembled,
                    "old_status_has_lod22": old_status_lod2,
                    "status_agreement": agreement,
                    "status_rf_rmse_lod22": status.get("rf_rmse_lod22", ""),
                    "cityjson_path": (
                        rel(cityjson)
                        if isinstance(cityjson, Path)
                        else "phases/p0-audit/data/raw/lod2/*.gml"
                    ),
                    "cityjson_sha256": cityjson_sha,
                    "cityjson_crs": reference_system,
                    "status_path": status_path,
                    "val3dity_report": val_report or "reference_self_check",
                    "val3dity_exit_code": val_exit,
                    "xy_alignment": alignment,
                    "xy_overlap_ratio": overlap_ratio,
                    "source_preassembly_z_shift_m": spec[
                        "source_preassembly_z_shift_m"
                    ],
                    "z_shift_to_reference_m": SCORE_TIME_Z_SHIFT_M,
                    "z_shift_rule": (
                        "canonical dense/ALS/reference are already in common "
                        "EPSG:25832; A-wave score-time candidate set is {0.0}"
                    ),
                    "gt_role": (
                        "LoD2 reference used only for scoring and reference "
                        "self-check"
                    ),
                    "learning_runs_started": 0,
                    "new_inference_runs": 0,
                }
            )
    expected_rows = EXPECTED_POPULATION * len(MODEL_SPECS)
    if len(rows) != expected_rows:
        raise RuntimeError(f"score row drift {len(rows)} != {expected_rows}")
    measured_counts = {
        role: sum(
            bool(row["has_lod22"]) for row in rows if row["role"] == role
        )
        for role in ("dense", "als")
    }
    if measured_counts != {
        "dense": EXPECTED_DENSE_LOD2,
        "als": EXPECTED_ALS_LOD2,
    }:
        raise RuntimeError(f"geometry LoD2.2 count drift {measured_counts}")
    if any(
        row["learning_runs_started"] != 0 or row["new_inference_runs"] != 0
        for row in rows
    ):
        raise RuntimeError("learning/inference flag drift")
    return rows


def quantiles(values: Iterable[float | None]) -> dict[str, float | int | None]:
    finite = np.asarray(
        [float(value) for value in values if value is not None and math.isfinite(float(value))],
        dtype=float,
    )
    if not len(finite):
        return {
            "count": 0,
            "min": None,
            "p10": None,
            "p25": None,
            "median": None,
            "p75": None,
            "p90": None,
            "max": None,
        }
    return {
        "count": int(len(finite)),
        "min": float(np.min(finite)),
        "p10": float(np.quantile(finite, 0.10)),
        "p25": float(np.quantile(finite, 0.25)),
        "median": float(np.median(finite)),
        "p75": float(np.quantile(finite, 0.75)),
        "p90": float(np.quantile(finite, 0.90)),
        "max": float(np.max(finite)),
    }


def build_summary(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for spec in MODEL_SPECS:
        model_id = str(spec["model_id"])
        role = str(spec["role"])
        subset = [row for row in rows if row["model_id"] == model_id]
        face = quantiles(number(row.get("face_count_ratio")) for row in subset)
        rms = quantiles(number(row.get("roof_rms_m")) for row in subset)
        completeness = quantiles(
            number(row.get("roof_completeness")) for row in subset
        )
        agreement_rows = [
            row for row in subset if row.get("status_agreement") is not None
        ]
        disagreements = [
            str(row["building_id"])
            for row in agreement_rows
            if not bool(row["status_agreement"])
        ]
        agreement_count = len(agreement_rows) - len(disagreements)
        output.append(
            {
                "row_type": "model_distribution",
                "model_id": model_id,
                "role": role,
                "population_count": len(subset),
                "lod2_count": sum(bool(row["has_lod22"]) for row in subset),
                "lod2_failure_count": sum(
                    not bool(row["has_lod22"]) for row in subset
                ),
                "val3dity_valid_count": sum(
                    bool(row["val3dity_valid"]) for row in subset
                ),
                "face_count_ratio_measurable_count": face["count"],
                "face_count_ratio_min": face["min"],
                "face_count_ratio_p10": face["p10"],
                "face_count_ratio_p25": face["p25"],
                "face_count_ratio_median": face["median"],
                "face_count_ratio_p75": face["p75"],
                "face_count_ratio_p90": face["p90"],
                "face_count_ratio_max": face["max"],
                "roof_rms_measurable_count": rms["count"],
                "roof_rms_min_m": rms["min"],
                "roof_rms_p10_m": rms["p10"],
                "roof_rms_p25_m": rms["p25"],
                "roof_rms_median_m": rms["median"],
                "roof_rms_p75_m": rms["p75"],
                "roof_rms_p90_m": rms["p90"],
                "roof_rms_max_m": rms["max"],
                "roof_completeness_measurable_count": completeness["count"],
                "roof_completeness_min": completeness["min"],
                "roof_completeness_p10": completeness["p10"],
                "roof_completeness_p25": completeness["p25"],
                "roof_completeness_median": completeness["median"],
                "roof_completeness_p75": completeness["p75"],
                "roof_completeness_p90": completeness["p90"],
                "roof_completeness_max": completeness["max"],
                "status_agreement_count": (
                    agreement_count if agreement_rows else None
                ),
                "status_disagreement_count": (
                    len(disagreements) if agreement_rows else None
                ),
                "status_agreement_rate": (
                    agreement_count / len(agreement_rows)
                    if agreement_rows
                    else None
                ),
                "snapshot_assembled_count": (
                    sum(bool(row["snapshot_assembled"]) for row in agreement_rows)
                    if agreement_rows
                    else None
                ),
                "old_status_has_lod22_count": (
                    sum(bool(row["old_status_has_lod22"]) for row in agreement_rows)
                    if agreement_rows
                    else None
                ),
                "status_disagreement_building_ids": ";".join(disagreements),
                "reference_self_rms_zero_count": sum(
                    role == "reference"
                    and abs(float(row["roof_rms_m"] or 0.0)) <= 1e-9
                    for row in subset
                ),
                "reference_self_completeness_one_count": sum(
                    role == "reference"
                    and abs(float(row["roof_completeness"] or 0.0) - 1.0)
                    <= 1e-9
                    for row in subset
                ),
                "learning_runs_started": 0,
                "new_inference_runs": 0,
            }
        )
        if agreement_rows:
            output.append(
                {
                    "row_type": "old_status_has_lod22_agreement",
                    "model_id": model_id,
                    "role": role,
                    "population_count": len(agreement_rows),
                    "lod2_count": sum(
                        bool(row["has_lod22"]) for row in agreement_rows
                    ),
                    "lod2_failure_count": sum(
                        not bool(row["has_lod22"]) for row in agreement_rows
                    ),
                    "status_agreement_count": agreement_count,
                    "status_disagreement_count": len(disagreements),
                    "status_agreement_rate": (
                        agreement_count / len(agreement_rows)
                    ),
                    "snapshot_assembled_count": sum(
                        bool(row["snapshot_assembled"])
                        for row in agreement_rows
                    ),
                    "old_status_has_lod22_count": sum(
                        bool(row["old_status_has_lod22"])
                        for row in agreement_rows
                    ),
                    "status_disagreement_building_ids": ";".join(disagreements),
                    "learning_runs_started": 0,
                    "new_inference_runs": 0,
                }
            )
    reference = [row for row in rows if row["role"] == "reference"]
    if (
        len(reference) != EXPECTED_POPULATION
        or any(abs(float(row["roof_rms_m"] or 0.0)) > 1e-9 for row in reference)
        or any(
            abs(float(row["roof_completeness"] or 0.0) - 1.0) > 1e-9
            for row in reference
        )
    ):
        raise RuntimeError("reference self-check integrity drift")
    agreement_rows = [
        row
        for row in rows
        if row["role"] in {"dense", "als"}
        and row.get("status_agreement") is not None
    ]
    if any(not bool(row["status_agreement"]) for row in agreement_rows):
        raise RuntimeError("snapshot versus old has_lod22 disagreement")
    return output


def make_figure(rows: Sequence[Mapping[str, Any]]) -> None:
    values: dict[str, np.ndarray] = {}
    labels = {
        "dense": "dense(w2_1)",
        "als": "ALS",
    }
    colors = {
        "dense": "#1f77b4",
        "als": "#ff7f0e",
    }
    for role in labels:
        values[role] = np.asarray(
            [
                float(row["roof_rms_m"])
                for row in rows
                if row["role"] == role and number(row.get("roof_rms_m")) is not None
            ],
            dtype=float,
        )
    finite_all = np.concatenate(
        [array for array in values.values() if len(array)]
    )
    if not len(finite_all):
        raise RuntimeError("no baseline RMS values available for distribution figure")
    upper = float(np.max(finite_all))
    bins = np.linspace(0.0, max(upper, 0.1), 24)
    figure, axes = plt.subplots(1, 2, figsize=(11.5, 4.8), dpi=180)
    for role in labels:
        array = values[role]
        axes[0].hist(
            array,
            bins=bins,
            histtype="step",
            linewidth=1.8,
            density=True,
            label=f"{labels[role]} (n={len(array)})",
            color=colors[role],
        )
        ordered = np.sort(array)
        axes[1].step(
            ordered,
            np.arange(1, len(ordered) + 1) / len(ordered),
            where="post",
            linewidth=1.8,
            label=(
                f"{labels[role]} "
                f"(median={float(np.median(array)):.3f} m)"
            ),
            color=colors[role],
        )
    axes[0].set_xlabel("roof RMS [m]")
    axes[0].set_ylabel("density")
    axes[0].set_title("Roof RMS histogram")
    axes[1].set_xlabel("roof RMS [m]")
    axes[1].set_ylabel("empirical cumulative fraction")
    axes[1].set_title("Roof RMS empirical distribution")
    for axis in axes:
        axis.grid(alpha=0.2)
        axis.legend(fontsize=8)
    figure.suptitle("Canonical 178-building baseline roof RMS distributions")
    figure.tight_layout(rect=[0, 0, 1, 0.96])
    FIGURE.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(FIGURE)
    plt.close(figure)


def write_manifest(
    population: Sequence[str],
    scores: Sequence[Mapping[str, Any]],
    summary: Sequence[Mapping[str, Any]],
) -> None:
    source_paths = [
        SNAPSHOT,
        STATUS_CSV,
        DENSE_CITYJSON,
        ALS_CITYJSON,
        A_SCORE_SCRIPT,
        METRIC_SCRIPT,
        W2_SCRIPT,
        Path(__file__),
        *sorted(LOD2_DIR.glob("*.gml")),
    ]
    output_paths = [
        SCORES_CSV,
        SUMMARY_CSV,
        FIGURE,
        *sorted(VAL_DIR.glob("*")),
    ]
    by_role = {
        role: [row for row in scores if row["role"] == role]
        for role in ("dense", "als", "reference")
    }
    payload = {
        "schema": "jointbuildgs.qs_baseline178.v1",
        "created_utc": now(),
        "git_head_at_measurement": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=REPO, text=True
        ).strip(),
        "branch": subprocess.check_output(
            ["git", "branch", "--show-current"], cwd=REPO, text=True
        ).strip(),
        "population_definition": (
            "docs/experiments/evaluation/attr_outcome_regression/tables/regression_input_snapshot.csv raw_lidar assembled=true"
        ),
        "population_count": len(population),
        "population_sha256": hashlib.sha256(
            ("\n".join(population) + "\n").encode("utf-8")
        ).hexdigest(),
        "model_rows": {
            role: len(rows) for role, rows in by_role.items()
        },
        "score_rows": len(scores),
        "summary_rows": len(summary),
        "canonical_counts": {
            "dense_has_lod22": sum(
                bool(row["has_lod22"]) for row in by_role["dense"]
            ),
            "dense_no_lod22": sum(
                not bool(row["has_lod22"]) for row in by_role["dense"]
            ),
            "als_has_lod22": sum(
                bool(row["has_lod22"]) for row in by_role["als"]
            ),
        },
        "old_status_agreement": {
            role: {
                "agreement_count": sum(
                    bool(row["status_agreement"]) for row in by_role[role]
                ),
                "population_count": len(by_role[role]),
                "agreement_rate": (
                    sum(
                        bool(row["status_agreement"])
                        for row in by_role[role]
                    )
                    / len(by_role[role])
                ),
            }
            for role in ("dense", "als")
        },
        "metrics": [
            "has_lod22",
            "val3dity_valid",
            "face_count_ratio",
            "roof_rms_m",
            "roof_completeness",
        ],
        "roof_completeness_definition": (
            "area(union(model roof XY) intersect union(reference roof XY)) "
            "/ area(union(reference roof XY))"
        ),
        "distance_definition_source": rel(METRIC_SCRIPT),
        "score_time_z_shift_m": SCORE_TIME_Z_SHIFT_M,
        "dense_source_preassembly_z_shift_m": DENSE_PREASSEMBLY_Z_SHIFT_M,
        "z_shift_rule": (
            "canonical dense/ALS/reference already share EPSG:25832; "
            "score-time shift fixed at 0.0 m"
        ),
        "crs": CRS,
        "val3dity_version": subprocess.check_output(
            ["val3dity", "--version"], text=True
        ).strip(),
        "learning_runs_started": 0,
        "new_inference_runs": 0,
        "gt_role": (
            "LoD2 reference used only for scoring, figure, and reference "
            "self-check"
        ),
        "interpretation_or_verdict": None,
        "source_sha256": {
            rel(path): sha256_file(path)
            for path in source_paths
            if path.is_file()
        },
        "output_sha256": {
            rel(path): sha256_file(path)
            for path in output_paths
            if path.is_file()
        },
    }
    atomic_text(MANIFEST, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


def main() -> None:
    RUN_DIR.mkdir(parents=True, exist_ok=True)
    VAL_DIR.mkdir(parents=True, exist_ok=True)
    atomic_text(RUN_LOG, "")
    log("start learning_runs_started=0 new_inference_runs=0")
    population, snapshot_by_arm = load_population()
    status_by_input = load_status(population)
    refs = metric.parse_lod2_roofs(LOD2_DIR, set(population))
    missing_reference = [
        building_id for building_id in population if not refs.get(building_id)
    ]
    if missing_reference:
        raise RuntimeError(f"reference RoofSurface missing {missing_reference}")
    scores = build_scores(
        population,
        snapshot_by_arm,
        status_by_input,
        refs,
    )
    summary = build_summary(scores)
    atomic_csv(SCORES_CSV, scores, SCORE_FIELDS)
    atomic_csv(SUMMARY_CSV, summary, SUMMARY_FIELDS)
    make_figure(scores)
    write_manifest(population, scores, summary)
    log(
        f"complete population={len(population)} scores={len(scores)} "
        f"summary={len(summary)} learning_runs_started=0 "
        "new_inference_runs=0"
    )


if __name__ == "__main__":
    main()
