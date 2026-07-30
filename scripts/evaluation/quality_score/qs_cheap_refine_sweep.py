#!/usr/bin/env python3
"""R4: learning-zero and inference-zero cheap-refinement parameter sweep.

The host ``run`` mode executes the already-used ``overseg_smooth.py`` and the
pinned Roofer image for the declared 3 x 3 x 2 grid.  It resumes completed
conditions and keeps every condition in a separate directory.  Reference LoD2
is not opened until every Roofer condition exists and ``finalize`` starts.

Run from the repository root::

    python3 scripts/evaluation/quality_score/qs_cheap_refine_sweep.py run

The command is suitable for invocation by the repository's detached overnight
driver.  It starts no GS optimization, model training, or learned inference.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
import math
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


REPO = Path(__file__).resolve().parents[3]
SCRIPT = Path(__file__).resolve()
RUN_ID = "20260718_qs_cheap_refine_sweep"
RUN_DIR = REPO / "phases/p2-gsjso/runs" / RUN_ID
JOBS_DIR = RUN_DIR / "jobs"
LOG_DIR = RUN_DIR / "logs"
PREPARED = RUN_DIR / "prepared.json"
RUN_LOG = RUN_DIR / "run.log"

DOCS = REPO / "docs"
OUTPUT_CSV = DOCS / "qs_cheap_refine_sweep.csv"
SUMMARY_CSV = DOCS / "qs_cheap_refine_sweep_summary.csv"
MANIFEST = DOCS / "qs_cheap_refine_sweep_manifest.json"
FIGURE = DOCS / "figs/qs_cheap_refine_sweep/parameter_grid.png"

D_RUN = (
    REPO
    / "phases/p2-gsjso/runs/quality_score/20260717_qs_cheap_refine_pilot"
)
INPUT_LAZ = D_RUN / "input/dense_w2_1_c001_classified.laz"
FOOTPRINTS_GEOJSON = D_RUN / "input/footprints_c001.geojson"
FOOTPRINTS_GPKG = D_RUN / "input/footprints_c001.gpkg"
D_PREPARED = D_RUN / "prepared.json"
D_MANIFEST = D_RUN / "manifest.json"

BASELINE_CITYJSON = (
    REPO
    / "phases/p0-audit/runs/w2_1_roofer_default_20260612_152729"
    / "cityjson/dim_roofer.city.json"
)
BASELINE_SCORES = DOCS / "qs_rescore_scores.csv"
LOD2_DIR = REPO / "phases/p0-audit/data/raw/lod2"
W2_SCRIPT = REPO / "phases/p0-audit/scripts/08_roofer_w2.py"
METRIC_SCRIPT = REPO / "scripts/e5_c001/e5_c001_8way.py"
SMOOTH_SCRIPT = REPO / "scripts/evidence_and_attributes/geometry_fidelity/overseg_smooth.py"
D_SCRIPT = REPO / "scripts/evaluation/quality_score/qs_cheap_refine_pilot.py"
GATE_SCRIPT = REPO / "scripts/e5_c001/e5_pilot_gate_tools.py"

TOOLS_IMAGE = "jointbuildgs-p0-tools:t0"
DENSE_MODEL_ID = "canonical_dense_w2_1"
ROOFER_IMAGE = (
    "3dgi/roofer@sha256:"
    "dd2c415aaee337502bde0dc1426dfa9c9f88e648f9d2f6340110c49932c251d2"
)
CRS = "EPSG:25832"
EXPECTED_BUILDINGS = 18
CELLS_M = (0.25, 0.5, 1.0)
WINDOW_RADII_CELLS = (1, 2, 3)
PASSES = (1, 2)
GRID = tuple(
    (cell, window, passes)
    for cell in CELLS_M
    for window in WINDOW_RADII_CELLS
    for passes in PASSES
)
EXPECTED_CONDITIONS = 18
EXPECTED_ROWS = EXPECTED_BUILDINGS * EXPECTED_CONDITIONS

SCORE_FIELDS = [
    "condition_id",
    "cell_m",
    "window_radius_cells",
    "window_radius_m",
    "passes",
    "building_id",
    "refinement_method",
    "input_laz",
    "input_laz_sha256",
    "refined_laz",
    "refined_laz_sha256",
    "building_point_count",
    "median_abs_point_dz_m",
    "p95_abs_point_dz_m",
    "roofer_status",
    "roofer_reason",
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
    "baseline_has_lod22",
    "baseline_val3dity_valid",
    "baseline_face_count_ratio",
    "baseline_roof_rms_m",
    "baseline_roof_hausdorff_m",
    "baseline_roof_completeness",
    "delta_has_lod22",
    "delta_face_count_ratio",
    "delta_roof_rms_m",
    "delta_roof_completeness",
    "roofer_cityjson",
    "roofer_cityjson_sha256",
    "val3dity_report",
    "val3dity_exit_code",
    "crs",
    "z_shift_to_reference_m",
    "gt_role",
    "learning_runs_started",
    "new_inference_runs",
]

SUMMARY_FIELDS = [
    "condition_id",
    "cell_m",
    "window_radius_cells",
    "window_radius_m",
    "passes",
    "building_count",
    "has_lod22_count",
    "val3dity_valid_count",
    "rms_measurable_count",
    "roof_rms_min_m",
    "roof_rms_p25_m",
    "roof_rms_median_m",
    "roof_rms_p75_m",
    "roof_rms_max_m",
    "completeness_measurable_count",
    "roof_completeness_min",
    "roof_completeness_p25",
    "roof_completeness_median",
    "roof_completeness_p75",
    "roof_completeness_max",
    "face_ratio_measurable_count",
    "face_count_ratio_median",
    "median_building_median_abs_point_dz_m",
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


def atomic_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(text, encoding="utf-8")
    os.replace(temporary, path)


def scalar(value: Any) -> Any:
    if value is None:
        return ""
    if isinstance(value, bool):
        return str(value).lower()
    if isinstance(value, float):
        return "" if not math.isfinite(value) else f"{value:.9f}"
    return value


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
            writer.writerow({field: scalar(row.get(field)) for field in fields})
    os.replace(temporary, path)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def parse_bool(value: Any) -> bool:
    return str(value).strip().lower() in {"true", "1", "yes", "y"}


def optional_float(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def condition_id(cell: float, window: int, passes: int) -> str:
    return f"cell{int(round(cell * 100)):03d}_win{window}_pass{passes}"


def condition_paths(
    cell: float,
    window: int,
    passes: int,
) -> dict[str, Path]:
    tag = condition_id(cell, window, passes)
    root = JOBS_DIR / tag
    return {
        "root": root,
        "refined": root / f"dense_w2_1_c001_{tag}.laz",
        "roofer": root / "roofer",
        "roofer_complete": root / "roofer_complete.json",
        "cityjson": root / f"dense_w2_1_c001_{tag}.city.json",
        "val": root / f"dense_w2_1_c001_{tag}_val3dity.json",
        "refine_log": LOG_DIR / f"{tag}_refine.log",
        "roofer_log": LOG_DIR / f"{tag}_roofer.log",
    }


def append_log(message: str) -> None:
    line = f"{now()} {message}"
    RUN_LOG.parent.mkdir(parents=True, exist_ok=True)
    with RUN_LOG.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    print(line, flush=True)


def run_logged(command: Sequence[str], log_path: Path) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("w", encoding="utf-8") as handle:
        handle.write("+ " + " ".join(command) + "\n")
        handle.flush()
        process = subprocess.run(
            list(command),
            cwd=REPO,
            text=True,
            stdout=handle,
            stderr=subprocess.STDOUT,
            check=False,
        )
    if process.returncode:
        raise RuntimeError(
            f"command failed exit={process.returncode} log={rel(log_path)}"
        )


def docker_base(image: str) -> list[str]:
    return [
        "docker",
        "run",
        "--rm",
        "--user",
        f"{os.getuid()}:{os.getgid()}",
        "-e",
        "HOME=/tmp",
        "-e",
        "MPLCONFIGDIR=/tmp/matplotlib",
        "-e",
        "XDG_CACHE_HOME=/tmp",
        "-v",
        f"{REPO}:/workspace/JointBuildGS",
        "-w",
        "/workspace/JointBuildGS",
        image,
    ]


def workspace_path(path: Path) -> str:
    return f"/workspace/JointBuildGS/{rel(path)}"


def expected_c001_ids() -> set[str]:
    payload = json.loads(FOOTPRINTS_GEOJSON.read_text(encoding="utf-8"))
    identifiers = {
        str((feature.get("properties") or {}).get("building_id", ""))
        for feature in payload.get("features", [])
    }
    identifiers.discard("")
    if len(identifiers) != EXPECTED_BUILDINGS:
        raise RuntimeError(
            f"C001 footprint identifier count drift {len(identifiers)}"
        )
    return identifiers


def jsonseq_population_complete(paths: Sequence[Path]) -> bool:
    if not paths:
        return False
    expected = expected_c001_ids()
    recorded: list[str] = []
    try:
        for path in paths:
            with path.open(encoding="utf-8") as handle:
                for line in handle:
                    if not line.strip():
                        continue
                    payload = json.loads(line)
                    if payload.get("type") != "CityJSONFeature":
                        continue
                    identifier = str(payload.get("id", ""))
                    if identifier:
                        recorded.append(identifier)
    except (OSError, json.JSONDecodeError):
        return False
    return len(recorded) == EXPECTED_BUILDINGS and set(recorded) == expected


def write_roofer_completion(paths: Mapping[str, Path]) -> None:
    jsonseq = sorted(paths["roofer"].glob("*.city.jsonl"))
    if not jsonseq_population_complete(jsonseq):
        raise RuntimeError(
            f"cannot mark incomplete Roofer output: {rel(paths['roofer'])}"
        )
    payload = {
        "schema": "jointbuildgs.qs_cheap_refine_sweep.roofer_complete.v1",
        "created_utc": now(),
        "refined_laz": rel(paths["refined"]),
        "refined_laz_sha256": sha256_file(paths["refined"]),
        "population_count": EXPECTED_BUILDINGS,
        "building_ids": sorted(expected_c001_ids()),
        "jsonseq_sha256": {
            rel(path): sha256_file(path) for path in jsonseq
        },
        "learning_runs_started": 0,
        "new_inference_runs": 0,
    }
    atomic_text(
        paths["roofer_complete"],
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
    )


def roofer_completion_valid(paths: Mapping[str, Path]) -> bool:
    marker = paths["roofer_complete"]
    if not paths["refined"].is_file() or not marker.is_file():
        return False
    try:
        payload = json.loads(marker.read_text(encoding="utf-8"))
        jsonseq = sorted(paths["roofer"].glob("*.city.jsonl"))
        if not jsonseq_population_complete(jsonseq):
            return False
        if payload.get("population_count") != EXPECTED_BUILDINGS:
            return False
        if set(payload.get("building_ids") or []) != expected_c001_ids():
            return False
        if payload.get("refined_laz_sha256") != sha256_file(paths["refined"]):
            return False
        recorded = payload.get("jsonseq_sha256") or {}
        measured = {rel(path): sha256_file(path) for path in jsonseq}
        return recorded == measured
    except (OSError, ValueError, json.JSONDecodeError):
        return False


def docker_image_id(image: str) -> str:
    return subprocess.check_output(
        ["docker", "image", "inspect", "--format", "{{.Id}}", image],
        text=True,
    ).strip()


def cityjson_crs(path: Path) -> str:
    payload = json.loads(path.read_text(encoding="utf-8"))
    reference_system = str(
        (payload.get("metadata") or {}).get("referenceSystem", "")
    )
    if (
        reference_system != CRS
        and not reference_system.rstrip("/").endswith("/25832")
    ):
        raise RuntimeError(
            f"CityJSON CRS mismatch path={rel(path)} crs={reference_system}"
        )
    return reference_system


def validate_inputs() -> dict[str, Any]:
    required = [
        INPUT_LAZ,
        FOOTPRINTS_GEOJSON,
        FOOTPRINTS_GPKG,
        D_PREPARED,
        D_MANIFEST,
        BASELINE_CITYJSON,
        BASELINE_SCORES,
        W2_SCRIPT,
        METRIC_SCRIPT,
        SMOOTH_SCRIPT,
        GATE_SCRIPT,
    ]
    missing = [rel(path) for path in required if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"R4 inputs missing: {missing}")
    prepared = json.loads(D_PREPARED.read_text(encoding="utf-8"))
    d_manifest = json.loads(D_MANIFEST.read_text(encoding="utf-8"))
    if int(prepared.get("building_count", -1)) != EXPECTED_BUILDINGS:
        raise RuntimeError("D prepared C001 population drift")
    if prepared.get("reference_opened") is not False:
        raise RuntimeError("D prepare reference-opened flag drift")
    bbox = prepared.get("clip_bbox_epsg25832")
    if not isinstance(bbox, list) or len(bbox) != 4:
        raise RuntimeError("D prepared bbox missing")
    declared_hashes = d_manifest.get("output_sha256") or {}
    for path in (INPUT_LAZ, FOOTPRINTS_GEOJSON, FOOTPRINTS_GPKG):
        declared = declared_hashes.get(rel(path))
        actual = sha256_file(path)
        if declared != actual:
            raise RuntimeError(
                f"D committed input hash drift path={rel(path)} "
                f"declared={declared} actual={actual}"
            )
    if d_manifest.get("roofer_image") != ROOFER_IMAGE:
        raise RuntimeError("D Roofer image digest drift")
    return prepared


def prepare_run(force: bool = False) -> dict[str, Any]:
    prepared = validate_inputs()
    RUN_DIR.mkdir(parents=True, exist_ok=True)
    JOBS_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    if force:
        for cell, window, passes in GRID:
            paths = condition_paths(cell, window, passes)
            if paths["root"].is_dir():
                shutil.rmtree(paths["root"])
            for key in ("refine_log", "roofer_log"):
                paths[key].unlink(missing_ok=True)
    payload = {
        "schema": "jointbuildgs.qs_cheap_refine_sweep.prepare.v1",
        "created_utc": now(),
        "population": "C001 18 buildings",
        "population_count": EXPECTED_BUILDINGS,
        "input_laz": rel(INPUT_LAZ),
        "input_laz_sha256": sha256_file(INPUT_LAZ),
        "footprints_geojson": rel(FOOTPRINTS_GEOJSON),
        "footprints_geojson_sha256": sha256_file(FOOTPRINTS_GEOJSON),
        "footprints_gpkg": rel(FOOTPRINTS_GPKG),
        "footprints_gpkg_sha256": sha256_file(FOOTPRINTS_GPKG),
        "clip_bbox_epsg25832": prepared["clip_bbox_epsg25832"],
        "grid": [
            {
                "condition_id": condition_id(cell, window, passes),
                "cell_m": cell,
                "window_radius_cells": window,
                "window_radius_m": cell * window,
                "passes": passes,
            }
            for cell, window, passes in GRID
        ],
        "fixed_parameters": {
            "building_class": 6,
            "roof_top_cell_m": 1.0,
            "roof_top_band_m": 1.5,
        },
        "tools_image": TOOLS_IMAGE,
        "tools_image_id": docker_image_id(TOOLS_IMAGE),
        "roofer_image": ROOFER_IMAGE,
        "roofer_image_id": docker_image_id(ROOFER_IMAGE),
        "reference_opened": False,
        "learning_runs_started": 0,
        "new_inference_runs": 0,
    }
    atomic_text(PREPARED, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    return payload


def run_grid(force: bool = False) -> None:
    prepared = prepare_run(force=force)
    atomic_text(RUN_LOG, "")
    append_log(
        "start conditions=18 learning_runs_started=0 new_inference_runs=0"
    )
    bbox = [str(value) for value in prepared["clip_bbox_epsg25832"]]
    for index, (cell, window, passes) in enumerate(GRID, start=1):
        tag = condition_id(cell, window, passes)
        paths = condition_paths(cell, window, passes)
        paths["root"].mkdir(parents=True, exist_ok=True)
        paths["roofer"].mkdir(parents=True, exist_ok=True)
        jsonseq = sorted(paths["roofer"].glob("*.city.jsonl"))
        if roofer_completion_valid(paths):
            append_log(f"resume condition={tag} step={index}/18")
            continue
        paths["roofer_complete"].unlink(missing_ok=True)
        if jsonseq:
            append_log(
                f"replace incomplete Roofer JSONSeq condition={tag} step={index}/18"
            )
            shutil.rmtree(paths["roofer"])
            paths["roofer"].mkdir(parents=True, exist_ok=True)
        if not paths["refined"].is_file():
            append_log(f"refine condition={tag} step={index}/18")
            command = [
                *docker_base(TOOLS_IMAGE),
                "python3",
                workspace_path(SMOOTH_SCRIPT),
                "--in",
                workspace_path(INPUT_LAZ),
                "--out",
                workspace_path(paths["refined"]),
                "--cell",
                str(cell),
                "--win",
                str(window),
                "--npass",
                str(passes),
                "--bclass",
                "6",
            ]
            run_logged(command, paths["refine_log"])
        append_log(f"roofer condition={tag} step={index}/18")
        command = [
            *docker_base(ROOFER_IMAGE),
            "--id-attribute",
            "building_id",
            "--box",
            *bbox,
            workspace_path(paths["refined"]),
            workspace_path(FOOTPRINTS_GPKG),
            workspace_path(paths["roofer"]),
        ]
        run_logged(command, paths["roofer_log"])
        jsonseq = sorted(paths["roofer"].glob("*.city.jsonl"))
        if not jsonseq_population_complete(jsonseq):
            raise RuntimeError(
                f"Roofer JSONSeq population incomplete condition={tag}"
            )
        write_roofer_completion(paths)
    append_log("all Roofer conditions present; enter reference-only finalize")
    command = [
        *docker_base(TOOLS_IMAGE),
        "python3",
        workspace_path(SCRIPT),
        "finalize",
    ]
    run_logged(command, LOG_DIR / "finalize.log")
    append_log(
        f"complete rows={EXPECTED_ROWS} learning_runs_started=0 "
        "new_inference_runs=0"
    )


def load_module(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load module {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def run_val3dity(cityjson: Path, report: Path) -> tuple[int, dict[str, Any]]:
    report.parent.mkdir(parents=True, exist_ok=True)
    process = subprocess.run(
        ["val3dity", cityjson.as_posix(), "--report", report.as_posix()],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    atomic_text(
        report.with_suffix(".log"),
        f"+ val3dity {cityjson} --report {report}\n"
        f"{process.stdout or ''}",
    )
    if not report.is_file():
        raise RuntimeError(
            f"val3dity report missing exit={process.returncode} "
            f"cityjson={rel(cityjson)}"
        )
    payload = json.loads(report.read_text(encoding="utf-8"))
    return int(process.returncode), {
        str(feature.get("id")): feature
        for feature in payload.get("features", [])
        if feature.get("id") is not None
    }


def roof_xy_coverage(
    metric: Any,
    references: Sequence[Any],
    predictions: Sequence[Any],
) -> dict[str, float | None]:
    from shapely.ops import unary_union

    ref_polygons = [
        polygon
        for surface in references
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
    reference_union = unary_union(ref_polygons)
    reference_area = float(reference_union.area)
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
    overlap = float(model_union.intersection(reference_union).area)
    return {
        "roof_completeness": min(1.0, max(0.0, overlap / reference_area)),
        "model_roof_xy_area_m2": float(model_union.area),
        "reference_roof_xy_area_m2": reference_area,
        "roof_overlap_xy_area_m2": overlap,
    }


def point_displacements(
    input_laz: Path,
    refined_laz: Path,
    footprints: Mapping[str, Any],
) -> dict[str, dict[str, float | int | None]]:
    import laspy
    import numpy as np
    from shapely import contains_xy

    source = laspy.read(input_laz)
    refined = laspy.read(refined_laz)
    if len(source.points) != len(refined.points):
        raise RuntimeError(f"point count changed refined={rel(refined_laz)}")
    classes = np.asarray(source.classification, dtype=np.uint8)
    if not np.array_equal(
        classes, np.asarray(refined.classification, dtype=np.uint8)
    ):
        raise RuntimeError(
            f"classification changed refined={rel(refined_laz)}"
        )
    x = np.asarray(source.x)
    y = np.asarray(source.y)
    dz = np.abs(np.asarray(refined.z) - np.asarray(source.z))
    output: dict[str, dict[str, float | int | None]] = {}
    for building_id, footprint in footprints.items():
        mask = (classes == 6) & contains_xy(footprint, x, y)
        values = dz[mask]
        output[building_id] = {
            "count": int(mask.sum()),
            "median": float(np.median(values)) if len(values) else None,
            "p95": (
                float(np.quantile(values, 0.95)) if len(values) else None
            ),
        }
    return output


def quantiles(values: Iterable[float | None]) -> dict[str, Any]:
    import numpy as np

    finite = np.asarray(
        [
            float(value)
            for value in values
            if value is not None and math.isfinite(float(value))
        ],
        dtype=float,
    )
    if not len(finite):
        return {
            "count": 0,
            "min": None,
            "p25": None,
            "median": None,
            "p75": None,
            "max": None,
        }
    return {
        "count": int(len(finite)),
        "min": float(np.min(finite)),
        "p25": float(np.quantile(finite, 0.25)),
        "median": float(np.median(finite)),
        "p75": float(np.quantile(finite, 0.75)),
        "max": float(np.max(finite)),
    }


def build_summary(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    import numpy as np

    output: list[dict[str, Any]] = []
    for cell, window, passes in GRID:
        tag = condition_id(cell, window, passes)
        subset = [row for row in rows if row["condition_id"] == tag]
        if len(subset) != EXPECTED_BUILDINGS:
            raise RuntimeError(
                f"condition row drift condition={tag} rows={len(subset)}"
            )
        rms = quantiles(optional_float(row.get("roof_rms_m")) for row in subset)
        complete = quantiles(
            optional_float(row.get("roof_completeness")) for row in subset
        )
        face = quantiles(
            optional_float(row.get("face_count_ratio")) for row in subset
        )
        movement = [
            float(value)
            for value in (
                optional_float(row.get("median_abs_point_dz_m"))
                for row in subset
            )
            if value is not None
        ]
        output.append(
            {
                "condition_id": tag,
                "cell_m": cell,
                "window_radius_cells": window,
                "window_radius_m": cell * window,
                "passes": passes,
                "building_count": len(subset),
                "has_lod22_count": sum(
                    bool(row["has_lod22"]) for row in subset
                ),
                "val3dity_valid_count": sum(
                    bool(row["val3dity_valid"]) for row in subset
                ),
                "rms_measurable_count": rms["count"],
                "roof_rms_min_m": rms["min"],
                "roof_rms_p25_m": rms["p25"],
                "roof_rms_median_m": rms["median"],
                "roof_rms_p75_m": rms["p75"],
                "roof_rms_max_m": rms["max"],
                "completeness_measurable_count": complete["count"],
                "roof_completeness_min": complete["min"],
                "roof_completeness_p25": complete["p25"],
                "roof_completeness_median": complete["median"],
                "roof_completeness_p75": complete["p75"],
                "roof_completeness_max": complete["max"],
                "face_ratio_measurable_count": face["count"],
                "face_count_ratio_median": face["median"],
                "median_building_median_abs_point_dz_m": (
                    float(np.median(movement)) if movement else None
                ),
                "learning_runs_started": 0,
                "new_inference_runs": 0,
            }
        )
    return output


def make_figure(summary: Sequence[Mapping[str, Any]]) -> None:
    import matplotlib
    import numpy as np

    os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib")
    os.environ.setdefault("XDG_CACHE_HOME", "/tmp")
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    panels = [
        ("has_lod22_count", "LoD2.2 building count"),
        ("val3dity_valid_count", "val3dity valid building count"),
        ("roof_rms_median_m", "median roof RMS [m]"),
        ("roof_completeness_median", "median roof completeness"),
    ]
    colors = {1: "#1f77b4", 2: "#d62728"}
    figure, axes = plt.subplots(2, 2, figsize=(11.5, 8.0), dpi=180)
    for axis, (field, title) in zip(axes.ravel(), panels):
        for window in WINDOW_RADII_CELLS:
            for passes in PASSES:
                selected = sorted(
                    (
                        row
                        for row in summary
                        if int(row["window_radius_cells"]) == window
                        and int(row["passes"]) == passes
                        and row.get(field) is not None
                    ),
                    key=lambda row: float(row["cell_m"]),
                )
                axis.plot(
                    [float(row["cell_m"]) for row in selected],
                    [float(row[field]) for row in selected],
                    marker=("o" if passes == 1 else "s"),
                    linestyle=("-" if passes == 1 else "--"),
                    color=colors[passes],
                    alpha=0.55 + 0.13 * window,
                    label=f"win={window} cells, passes={passes}",
                )
        axis.set_xscale("log", base=2)
        axis.set_xticks(CELLS_M, labels=[str(cell) for cell in CELLS_M])
        axis.set_xlabel("cell [m]")
        axis.set_title(title)
        axis.grid(alpha=0.2)
    handles, labels = axes[0, 0].get_legend_handles_labels()
    figure.legend(handles, labels, loc="lower center", ncol=3, fontsize=8)
    figure.suptitle("C001 cheap-refinement parameter grid")
    figure.tight_layout(rect=[0, 0.07, 1, 0.96])
    FIGURE.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(FIGURE)
    plt.close(figure)


def finalize() -> None:
    from shapely.geometry import shape

    prepared = json.loads(PREPARED.read_text(encoding="utf-8"))
    if prepared.get("reference_opened") is not False:
        raise RuntimeError("prepare reference-opened flag drift")
    missing_conditions: list[str] = []
    jsonseq_by_condition: dict[str, list[Path]] = {}
    for cell, window, passes in GRID:
        tag = condition_id(cell, window, passes)
        paths = condition_paths(cell, window, passes)
        jsonseq = sorted(paths["roofer"].glob("*.city.jsonl"))
        if (
            not roofer_completion_valid(paths)
        ):
            missing_conditions.append(tag)
        jsonseq_by_condition[tag] = jsonseq
    if missing_conditions:
        raise RuntimeError(
            "all Roofer outputs are required before reference scoring: "
            + ",".join(missing_conditions)
        )

    metric = load_module("qs_cheap_sweep_metric", METRIC_SCRIPT)
    gate = load_module(
        "qs_cheap_sweep_gate",
        REPO / "scripts/e5_c001/e5_pilot_gate_tools.py",
    )
    w2 = load_module("qs_cheap_sweep_w2", W2_SCRIPT)
    building_ids = list(gate.C001_IDS)
    if len(building_ids) != EXPECTED_BUILDINGS:
        raise RuntimeError(f"C001 population drift {len(building_ids)}")
    wanted = set(building_ids)

    # Reference-dependent inputs are first opened here, after the completeness
    # assertion over every reconstruction condition above.
    references = metric.parse_lod2_roofs(LOD2_DIR, wanted)
    baseline_predictions = metric.parse_cityjson_roofs(
        BASELINE_CITYJSON, wanted
    )
    baseline_rows = {
        row["building_id"]: row
        for row in read_csv(BASELINE_SCORES)
        if row.get("role") == "canonical_dense"
    }
    if set(baseline_rows) != wanted:
        raise RuntimeError("canonical dense baseline score population drift")
    baseline_sha256 = sha256_file(BASELINE_CITYJSON)
    for building_id, row in baseline_rows.items():
        if row.get("model_id") != DENSE_MODEL_ID:
            raise RuntimeError(
                f"canonical dense model ID drift building={building_id}"
            )
        if row.get("cityjson_path") != rel(BASELINE_CITYJSON):
            raise RuntimeError(
                f"canonical dense CityJSON path drift building={building_id}"
            )
        if row.get("cityjson_sha256") != baseline_sha256:
            raise RuntimeError(
                f"canonical dense CityJSON SHA drift building={building_id}"
            )
    footprint_payload = json.loads(
        FOOTPRINTS_GEOJSON.read_text(encoding="utf-8")
    )
    footprints = {
        str(feature["properties"]["building_id"]): shape(feature["geometry"])
        for feature in footprint_payload.get("features", [])
    }
    if set(footprints) != wanted:
        raise RuntimeError("C001 footprint population drift")

    baseline_completeness = {
        building_id: roof_xy_coverage(
            metric,
            references[building_id],
            baseline_predictions.get(building_id, []),
        )["roof_completeness"]
        for building_id in building_ids
    }
    rows: list[dict[str, Any]] = []
    output_artifacts: list[Path] = []
    for cell, window, passes in GRID:
        tag = condition_id(cell, window, passes)
        paths = condition_paths(cell, window, passes)
        jsonseq = jsonseq_by_condition[tag]
        w2.combine_cityjsonseq(jsonseq, paths["cityjson"])
        verified_crs = cityjson_crs(paths["cityjson"])
        val_exit, val_by_id = run_val3dity(paths["cityjson"], paths["val"])
        roofer_by_id = w2.parse_roofer_features(jsonseq)
        status_rows = w2.classify_buildings(
            f"DENSE_REFINED_{tag}",
            building_ids,
            roofer_by_id,
            val_by_id,
        )
        status_by_id = {row["building_id"]: row for row in status_rows}
        predictions = metric.parse_cityjson_roofs(paths["cityjson"], wanted)
        movements = point_displacements(
            INPUT_LAZ, paths["refined"], footprints
        )
        condition_sha = sha256_file(paths["cityjson"])
        refined_sha = sha256_file(paths["refined"])
        for building_id in building_ids:
            status = status_by_id[building_id]
            prediction = list(predictions.get(building_id, []))
            reference = list(references[building_id])
            comparison = metric.compare_building(reference, prediction)
            coverage = roof_xy_coverage(metric, reference, prediction)
            fallback = (
                str(status.get("rf_extrusion_mode", ""))
                == "lod11_fallback"
            )
            has_lod22 = parse_bool(status.get("has_lod22")) and not fallback
            valid = bool(
                (val_by_id.get(building_id) or {}).get("validity", False)
            )
            model_faces = 1 if fallback else len(prediction)
            ref_faces = len(reference)
            face_ratio = model_faces / ref_faces if ref_faces else None
            baseline = baseline_rows[building_id]
            baseline_has_lod22 = parse_bool(baseline.get("has_lod22"))
            baseline_valid = parse_bool(baseline.get("val3dity_valid"))
            baseline_ratio = optional_float(baseline.get("face_count_ratio"))
            baseline_rms = optional_float(baseline.get("roof_rms_m"))
            baseline_hausdorff = optional_float(
                baseline.get("roof_hausdorff_m")
            )
            base_complete = optional_float(
                baseline.get("roof_completeness")
            )
            if base_complete is None:
                base_complete = baseline_completeness[building_id]
            refined_rms = comparison["ref_rms_m"]
            movement = movements[building_id]
            rows.append(
                {
                    "condition_id": tag,
                    "cell_m": cell,
                    "window_radius_cells": window,
                    "window_radius_m": cell * window,
                    "passes": passes,
                    "building_id": building_id,
                    "refinement_method": (
                        "overseg_smooth.py MLS-style local plane fit and "
                        "z projection on roof-top class-6 points"
                    ),
                    "input_laz": rel(INPUT_LAZ),
                    "input_laz_sha256": sha256_file(INPUT_LAZ),
                    "refined_laz": rel(paths["refined"]),
                    "refined_laz_sha256": refined_sha,
                    "building_point_count": movement["count"],
                    "median_abs_point_dz_m": movement["median"],
                    "p95_abs_point_dz_m": movement["p95"],
                    "roofer_status": status["status"],
                    "roofer_reason": status["reason"],
                    "rf_extrusion_mode": status.get(
                        "rf_extrusion_mode", ""
                    ),
                    "has_lod22": has_lod22,
                    "lod1_fallback": fallback,
                    "val3dity_valid": valid,
                    "roof_face_count_model": model_faces,
                    "roof_face_count_ref": ref_faces,
                    "face_count_ratio": face_ratio,
                    "roof_rms_m": refined_rms,
                    "roof_hausdorff_m": comparison["ref_hausdorff_m"],
                    "roof_distance_samples": comparison[
                        "ref_distance_samples"
                    ],
                    **coverage,
                    "baseline_has_lod22": baseline_has_lod22,
                    "baseline_val3dity_valid": baseline_valid,
                    "baseline_face_count_ratio": baseline_ratio,
                    "baseline_roof_rms_m": baseline_rms,
                    "baseline_roof_hausdorff_m": baseline_hausdorff,
                    "baseline_roof_completeness": base_complete,
                    "delta_has_lod22": (
                        int(has_lod22) - int(baseline_has_lod22)
                    ),
                    "delta_face_count_ratio": (
                        face_ratio - baseline_ratio
                        if face_ratio is not None
                        and baseline_ratio is not None
                        else None
                    ),
                    "delta_roof_rms_m": (
                        float(refined_rms) - baseline_rms
                        if refined_rms is not None
                        and baseline_rms is not None
                        else None
                    ),
                    "delta_roof_completeness": (
                        float(coverage["roof_completeness"])
                        - base_complete
                        if coverage["roof_completeness"] is not None
                        and base_complete is not None
                        else None
                    ),
                    "roofer_cityjson": rel(paths["cityjson"]),
                    "roofer_cityjson_sha256": condition_sha,
                    "val3dity_report": rel(paths["val"]),
                    "val3dity_exit_code": val_exit,
                    "crs": (
                        CRS
                        if verified_crs == CRS
                        or verified_crs.rstrip("/").endswith("/25832")
                        else verified_crs
                    ),
                    "z_shift_to_reference_m": 0.0,
                    "gt_role": (
                        "LoD2 reference opened only after all 18 Roofer "
                        "conditions; used for scoring and figure only"
                    ),
                    "learning_runs_started": 0,
                    "new_inference_runs": 0,
                }
            )
        output_artifacts.extend(
            [
                paths["refined"],
                paths["cityjson"],
                paths["val"],
                paths["val"].with_suffix(".log"),
                paths["roofer_complete"],
                *jsonseq,
            ]
        )

    if len(rows) != EXPECTED_ROWS:
        raise RuntimeError(f"R4 row drift {len(rows)} != {EXPECTED_ROWS}")
    if any(
        row["learning_runs_started"] != 0
        or row["new_inference_runs"] != 0
        for row in rows
    ):
        raise RuntimeError("learning/inference flag drift")
    summary = build_summary(rows)
    atomic_csv(OUTPUT_CSV, rows, SCORE_FIELDS)
    atomic_csv(SUMMARY_CSV, summary, SUMMARY_FIELDS)
    make_figure(summary)

    source_paths = [
        INPUT_LAZ,
        FOOTPRINTS_GEOJSON,
        FOOTPRINTS_GPKG,
        D_PREPARED,
        D_MANIFEST,
        BASELINE_CITYJSON,
        BASELINE_SCORES,
        W2_SCRIPT,
        METRIC_SCRIPT,
        SMOOTH_SCRIPT,
        D_SCRIPT,
        GATE_SCRIPT,
        SCRIPT,
        *sorted(LOD2_DIR.glob("*.gml")),
    ]
    output_paths = [
        PREPARED,
        OUTPUT_CSV,
        SUMMARY_CSV,
        FIGURE,
        *output_artifacts,
    ]
    manifest = {
        "schema": "jointbuildgs.qs_cheap_refine_sweep.v1",
        "created_utc": now(),
        "git_head_at_measurement": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=REPO, text=True
        ).strip(),
        "branch": subprocess.check_output(
            ["git", "branch", "--show-current"], cwd=REPO, text=True
        ).strip(),
        "population": "C001 18 buildings",
        "population_count": EXPECTED_BUILDINGS,
        "condition_count": EXPECTED_CONDITIONS,
        "score_rows": len(rows),
        "summary_rows": len(summary),
        "grid": prepared["grid"],
        "refinement_code": rel(SMOOTH_SCRIPT),
        "fixed_parameters": prepared["fixed_parameters"],
        "window_radius_unit": "cells",
        "roofer_image": ROOFER_IMAGE,
        "roofer_parameters": (
            "--id-attribute building_id --box C001_BBOX; "
            "all reconstruction parameters default"
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
        "distance_definition_source": rel(METRIC_SCRIPT),
        "score_time_z_shift_m": 0.0,
        "crs": CRS,
        "reference_opened_after_all_conditions": True,
        "learning_runs_started": 0,
        "new_inference_runs": 0,
        "gt_role": (
            "LoD2 reference used only after all reconstruction conditions "
            "for scoring and figure"
        ),
        "interpretation_or_verdict": None,
        "tools_image": TOOLS_IMAGE,
        "tools_image_id": prepared["tools_image_id"],
        "roofer_image_id": prepared["roofer_image_id"],
        "val3dity_version": subprocess.check_output(
            ["val3dity", "--version"], text=True
        ).strip(),
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
    atomic_text(MANIFEST, json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    print(
        json.dumps(
            {
                "conditions": len(summary),
                "rows": len(rows),
                "learning_runs_started": 0,
                "new_inference_runs": 0,
            },
            ensure_ascii=False,
        )
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("run", "prepare", "finalize"))
    parser.add_argument(
        "--force",
        action="store_true",
        help="remove only this sweep's per-condition outputs before run",
    )
    args = parser.parse_args()
    if args.mode == "run":
        run_grid(force=args.force)
    elif args.mode == "prepare":
        prepare_run(force=args.force)
    else:
        if args.force:
            parser.error("--force is not valid with finalize")
        finalize()


if __name__ == "__main__":
    main()
