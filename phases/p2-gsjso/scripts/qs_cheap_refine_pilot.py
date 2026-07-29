#!/usr/bin/env python3
"""D-wave cheap refinement pilot over canonical dense(w2_1), learning zero.

Modes
-----
prepare
    Clip the canonical classified DIM cloud to the C001 18-building footprint
    population plus local ground context.  Reference LoD2 geometry is not read.
finalize
    Merge the already-produced Roofer JSONSeq output, run val3dity, and score
    the refined model through the same CityJSON roof comparison functions used
    by A.  Reference LoD2 is opened only in this scoring mode.

The refinement itself is the existing ``overseg_smooth.py`` implementation
with its declared defaults: cell=0.5 m, win=2, npass=1, building class=6.
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
import subprocess
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence

os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib")
os.environ.setdefault("XDG_CACHE_HOME", "/tmp")

import laspy
import matplotlib
import numpy as np
from shapely import contains_xy
from shapely.geometry import mapping, shape
from shapely.ops import unary_union

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402


REPO = Path(__file__).resolve().parents[3]
SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in os.sys.path:
    os.sys.path.insert(0, str(SCRIPT_DIR))

import e5_c001_8way as metrics  # noqa: E402
from e5_pilot_gate_tools import C001_IDS  # noqa: E402


RUN_ID = "20260717_qs_cheap_refine_pilot"
RUN_DIR = REPO / "phases/p2-gsjso/runs" / RUN_ID
INPUT_DIR = RUN_DIR / "input"
ROOFER_DIR = RUN_DIR / "roofer"
CITYJSON_DIR = RUN_DIR / "cityjson"
VAL_DIR = RUN_DIR / "val3dity"
LOG_DIR = RUN_DIR / "logs"
PREPARED = RUN_DIR / "prepared.json"
MANIFEST = RUN_DIR / "manifest.json"
VERSIONS = RUN_DIR / "versions.txt"

SOURCE_LAZ = (
    REPO
    / "phases/p0-audit/data/work/w2/dim_v1_classified_z_minus0p174.laz"
)
FOOTPRINT_SOURCE = (
    REPO
    / "phases/p0-audit/data/work/w2_city3d/footprints_scene_aoi.geojson"
)
CLIPPED_LAZ = INPUT_DIR / "dense_w2_1_c001_classified.laz"
REFINED_LAZ = INPUT_DIR / "dense_w2_1_c001_mls_default.laz"
C001_FOOTPRINTS = INPUT_DIR / "footprints_c001.geojson"
C001_FOOTPRINTS_GPKG = INPUT_DIR / "footprints_c001.gpkg"
REFINED_CITYJSON = CITYJSON_DIR / "dense_w2_1_c001_mls_default.city.json"
VAL_REPORT = VAL_DIR / "dense_w2_1_c001_mls_default.json"

BASELINE_CITYJSON = (
    REPO
    / "phases/p0-audit/runs/w2_1_roofer_default_20260612_152729"
    / "cityjson/dim_roofer.city.json"
)
BASELINE_SCORES = REPO / "docs/experiments/qs_rescore/tables/qs_rescore_scores.csv"
LOD2_DIR = REPO / "phases/p0-audit/data/raw/lod2"
W2_SCRIPT = REPO / "phases/p0-audit/scripts/08_roofer_w2.py"
SMOOTH_SCRIPT = REPO / "phases/p2-gsjso/scripts/overseg_smooth.py"
DRIVER_SCRIPT = (
    REPO / "phases/p2-gsjso/scripts/run_qs_cheap_refine_pilot_20260717.sh"
)

OUTPUT_CSV = REPO / "docs/qs_cheap_refine_pilot.csv"
FIGURE = REPO / "docs/figs/qs_cheap_refine_pilot.png"

CRS = "EPSG:25832"
GROUND_CLASS = 2
BUILDING_CLASS = 6
GROUND_CONTEXT_MARGIN_M = 5.0
BUILDING_CLIP_BUFFER_M = 0.5
REFINE_PARAMETERS = {
    "cell_m": 0.5,
    "window_radius_cells": 2,
    "passes": 1,
    "building_class": 6,
    "roof_top_cell_m": 1.0,
    "roof_top_band_m": 1.5,
}
ROOFER_IMAGE = (
    "3dgi/roofer@sha256:"
    "dd2c415aaee337502bde0dc1426dfa9c9f88e648f9d2f6340110c49932c251d2"
)
ROOFER_PARAMETERS = (
    "--id-attribute building_id --box C001_BBOX; "
    "all reconstruction parameters default"
)

FIELDS = [
    "building_id",
    "refinement_method",
    "refinement_parameters_json",
    "input_laz",
    "input_laz_sha256",
    "refined_laz",
    "refined_laz_sha256",
    "building_point_count",
    "point_displacement_support",
    "median_abs_point_dz_m",
    "p95_abs_point_dz_m",
    "baseline_roofer_status",
    "baseline_roofer_reason",
    "refined_roofer_status",
    "refined_roofer_reason",
    "baseline_rf_extrusion_mode",
    "refined_rf_extrusion_mode",
    "baseline_has_lod22",
    "refined_has_lod22",
    "delta_has_lod22",
    "baseline_lod1_fallback",
    "refined_lod1_fallback",
    "baseline_val3dity_valid",
    "refined_val3dity_valid",
    "baseline_roof_face_count",
    "refined_roof_face_count",
    "delta_roof_face_count",
    "reference_roof_face_count",
    "baseline_face_count_ratio",
    "refined_face_count_ratio",
    "delta_face_count_ratio",
    "baseline_roof_rms_m",
    "refined_roof_rms_m",
    "delta_roof_rms_m",
    "refined_roof_hausdorff_m",
    "roofer_cityjson",
    "roofer_cityjson_sha256",
    "roofer_parameters",
    "crs",
    "gt_role",
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
    temporary.replace(path)


def atomic_csv(path: Path, rows: Sequence[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=FIELDS,
            extrasaction="ignore",
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(path)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def parse_bool(value: Any) -> bool:
    return str(value).strip().lower() in {"true", "1", "yes"}


def optional_float(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def load_footprint_payload() -> tuple[dict[str, Any], dict[str, Any]]:
    source = json.loads(FOOTPRINT_SOURCE.read_text(encoding="utf-8"))
    wanted = set(C001_IDS)
    features = [
        feature
        for feature in source.get("features", [])
        if str((feature.get("properties") or {}).get("building_id", "")) in wanted
    ]
    found = {
        str((feature.get("properties") or {}).get("building_id", ""))
        for feature in features
    }
    if found != wanted:
        raise RuntimeError(f"C001 footprint drift missing={sorted(wanted - found)}")
    payload = {
        "type": "FeatureCollection",
        "name": "C001_18",
        "crs": {
            "type": "name",
            "properties": {"name": "urn:ogc:def:crs:EPSG::25832"},
        },
        "features": features,
    }
    geometries = {
        str(feature["properties"]["building_id"]): shape(feature["geometry"])
        for feature in features
    }
    return payload, geometries


def prepare() -> None:
    for directory in (RUN_DIR, INPUT_DIR, ROOFER_DIR, CITYJSON_DIR, VAL_DIR, LOG_DIR):
        directory.mkdir(parents=True, exist_ok=True)
    payload, footprints = load_footprint_payload()
    atomic_text(
        C001_FOOTPRINTS,
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n",
    )
    subprocess.run(
        [
            "ogr2ogr",
            "-overwrite",
            "-f",
            "GPKG",
            C001_FOOTPRINTS_GPKG.as_posix(),
            C001_FOOTPRINTS.as_posix(),
            "-nln",
            "footprints_c001",
        ],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=True,
    )
    union = unary_union(list(footprints.values()))
    minx, miny, maxx, maxy = union.bounds
    bbox = (
        minx - GROUND_CONTEXT_MARGIN_M,
        miny - GROUND_CONTEXT_MARGIN_M,
        maxx + GROUND_CONTEXT_MARGIN_M,
        maxy + GROUND_CONTEXT_MARGIN_M,
    )

    cloud = laspy.read(SOURCE_LAZ)
    x = np.asarray(cloud.x)
    y = np.asarray(cloud.y)
    classes = np.asarray(cloud.classification, dtype=np.uint8)
    in_bbox = (
        (x >= bbox[0])
        & (x <= bbox[2])
        & (y >= bbox[1])
        & (y <= bbox[3])
    )
    building_support = unary_union(
        [geometry.buffer(BUILDING_CLIP_BUFFER_M) for geometry in footprints.values()]
    )
    keep_building = (
        (classes == BUILDING_CLASS)
        & in_bbox
        & contains_xy(building_support, x, y)
    )
    keep_ground = (classes == GROUND_CLASS) & in_bbox
    keep = keep_building | keep_ground
    if int(keep_building.sum()) == 0 or int(keep_ground.sum()) == 0:
        raise RuntimeError(
            f"C001 clip empty building={int(keep_building.sum())} ground={int(keep_ground.sum())}"
        )

    header = copy.deepcopy(cloud.header)
    clipped = laspy.LasData(header)
    clipped.points = cloud.points[keep].copy()
    clipped.write(CLIPPED_LAZ)
    prepared = {
        "schema": "jointbuildgs.qs_cheap_refine.prepare.v1",
        "created_utc": now(),
        "source_laz": rel(SOURCE_LAZ),
        "source_laz_sha256": sha256_file(SOURCE_LAZ),
        "c001_footprints": rel(C001_FOOTPRINTS),
        "c001_footprints_sha256": sha256_file(C001_FOOTPRINTS),
        "c001_footprints_gpkg": rel(C001_FOOTPRINTS_GPKG),
        "c001_footprints_gpkg_sha256": sha256_file(C001_FOOTPRINTS_GPKG),
        "building_count": len(footprints),
        "clip_bbox_epsg25832": list(bbox),
        "ground_context_margin_m": GROUND_CONTEXT_MARGIN_M,
        "building_clip_buffer_m": BUILDING_CLIP_BUFFER_M,
        "class_counts": {
            str(BUILDING_CLASS): int(keep_building.sum()),
            str(GROUND_CLASS): int(keep_ground.sum()),
        },
        "refinement_method": "MLS-style local plane fit and z projection on roof-top class-6 points",
        "refinement_parameters": REFINE_PARAMETERS,
        "reference_opened": False,
        "learning_runs_started": 0,
        "new_inference_runs": 0,
    }
    atomic_text(PREPARED, json.dumps(prepared, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(prepared, ensure_ascii=False))


def load_module(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load module {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run_val3dity(cityjson: Path, report: Path) -> tuple[int, dict[str, bool]]:
    report.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        ["val3dity", cityjson.as_posix(), "--report", report.as_posix()],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    output = "\n".join(
        line.rstrip() for line in (proc.stdout or "").splitlines()
    ).rstrip()
    atomic_text(
        report.with_suffix(".log"),
        f"+ val3dity {cityjson} --report {report}\n"
        + (output + "\n" if output else ""),
    )
    if not report.is_file():
        raise RuntimeError(f"val3dity did not write report exit={proc.returncode}")
    payload = json.loads(report.read_text(encoding="utf-8"))
    valid = {
        str(feature.get("id")): bool(feature.get("validity"))
        for feature in payload.get("features", [])
        if feature.get("id") is not None
    }
    return int(proc.returncode), valid


def point_displacements(
    footprints: dict[str, Any],
) -> dict[str, dict[str, float | int | None]]:
    source = laspy.read(CLIPPED_LAZ)
    refined = laspy.read(REFINED_LAZ)
    if len(source.points) != len(refined.points):
        raise RuntimeError("refinement changed point count")
    classes = np.asarray(source.classification, dtype=np.uint8)
    if not np.array_equal(classes, np.asarray(refined.classification, dtype=np.uint8)):
        raise RuntimeError("refinement changed classifications")
    x = np.asarray(source.x)
    y = np.asarray(source.y)
    dz = np.asarray(refined.z) - np.asarray(source.z)
    output: dict[str, dict[str, float | int | None]] = {}
    for bid, footprint in footprints.items():
        mask = (classes == BUILDING_CLASS) & contains_xy(footprint, x, y)
        values = np.abs(dz[mask])
        output[bid] = {
            "count": int(mask.sum()),
            "median": float(np.median(values)) if len(values) else None,
            "p95": float(np.quantile(values, 0.95)) if len(values) else None,
        }
    return output


def plot_top(axis: Any, surfaces: Sequence[Any], title: str, fallback: bool = False) -> None:
    colors = plt.cm.Set3(np.linspace(0, 1, max(1, len(surfaces))))
    for index, surface in enumerate(surfaces):
        for polygon in metrics.flatten_polygons(surface.polygon):
            ring = np.asarray(polygon.exterior.coords)
            axis.fill(
                ring[:, 0],
                ring[:, 1],
                color=colors[index % len(colors)],
                edgecolor="black",
                linewidth=0.55,
                alpha=0.82,
            )
    if not surfaces:
        axis.text(
            0.5,
            0.5,
            "no roof geometry",
            transform=axis.transAxes,
            ha="center",
            va="center",
        )
    axis.set_aspect("equal")
    axis.set_title(title + ("\nLoD1 fallback" if fallback else ""), fontsize=8)
    axis.set_xticks([])
    axis.set_yticks([])


def representative_ids(rows: Sequence[dict[str, Any]]) -> list[str]:
    selected = ["DEBY_LOD2_4907199"]
    finite = [
        row
        for row in rows
        if row["delta_roof_rms_m"] is not None
        and math.isfinite(float(row["delta_roof_rms_m"]))
    ]
    if finite:
        selected.extend(
            [
                min(finite, key=lambda row: float(row["delta_roof_rms_m"]))[
                    "building_id"
                ],
                max(finite, key=lambda row: float(row["delta_roof_rms_m"]))[
                    "building_id"
                ],
                max(
                    finite,
                    key=lambda row: abs(float(row["delta_roof_face_count"])),
                )["building_id"],
            ]
        )
    unique = list(dict.fromkeys(selected))
    for bid in C001_IDS:
        if len(unique) >= 4:
            break
        if bid not in unique:
            unique.append(bid)
    return unique[:4]


def finalize() -> None:
    if not PREPARED.is_file() or not REFINED_LAZ.is_file():
        raise FileNotFoundError("prepare/refinement output missing")
    jsonl_files = sorted(ROOFER_DIR.glob("*.city.jsonl"))
    if not jsonl_files:
        raise FileNotFoundError(f"Roofer JSONSeq missing under {ROOFER_DIR}")
    w2 = load_module("qs_cheap_refine_w2", W2_SCRIPT)
    REFINED_CITYJSON.parent.mkdir(parents=True, exist_ok=True)
    w2.combine_cityjsonseq(jsonl_files, REFINED_CITYJSON)
    val_exit, valid = run_val3dity(REFINED_CITYJSON, VAL_REPORT)
    val_payload = json.loads(VAL_REPORT.read_text(encoding="utf-8"))
    val_by_id = {
        str(feature.get("id")): feature
        for feature in val_payload.get("features", [])
        if feature.get("id") is not None
    }
    roofer_by_id = w2.parse_roofer_features(jsonl_files)
    statuses = w2.classify_buildings("DIM_REFINED", C001_IDS, roofer_by_id, val_by_id)
    status_by_id = {row["building_id"]: row for row in statuses}

    baseline_scores = {
        row["building_id"]: row
        for row in read_csv(BASELINE_SCORES)
        if row["role"] == "canonical_dense"
    }
    if set(baseline_scores) != set(C001_IDS):
        raise RuntimeError("canonical dense baseline score population drift")
    refs = metrics.parse_lod2_roofs(LOD2_DIR, set(C001_IDS))
    baseline_surfaces = metrics.parse_cityjson_roofs(BASELINE_CITYJSON, set(C001_IDS))
    refined_surfaces = metrics.parse_cityjson_roofs(REFINED_CITYJSON, set(C001_IDS))
    _payload, footprints = load_footprint_payload()
    movements = point_displacements(footprints)

    rows: list[dict[str, Any]] = []
    for bid in C001_IDS:
        baseline = baseline_scores[bid]
        status = status_by_id[bid]
        predicted = refined_surfaces.get(bid, [])
        comparison = metrics.compare_building(refs[bid], predicted)
        refined_mode = str(status.get("rf_extrusion_mode", ""))
        refined_fallback = refined_mode == "lod11_fallback"
        refined_lod2 = parse_bool(status.get("has_lod22")) and not refined_fallback
        baseline_lod2 = parse_bool(baseline.get("has_lod22"))
        refined_faces = 1 if refined_fallback else len(predicted)
        baseline_faces = int(float(baseline["roof_face_count_model"]))
        ref_faces = len(refs[bid])
        baseline_ratio = float(baseline["face_count_ratio"])
        refined_ratio = refined_faces / ref_faces if ref_faces else None
        baseline_rms = optional_float(baseline.get("roof_rms_m"))
        refined_rms = comparison["ref_rms_m"]
        movement = movements[bid]
        rows.append(
            {
                "building_id": bid,
                "refinement_method": (
                    "MLS-style local plane fit and z projection on roof-top class-6 points"
                ),
                "refinement_parameters_json": json.dumps(
                    REFINE_PARAMETERS, sort_keys=True, separators=(",", ":")
                ),
                "input_laz": rel(CLIPPED_LAZ),
                "input_laz_sha256": sha256_file(CLIPPED_LAZ),
                "refined_laz": rel(REFINED_LAZ),
                "refined_laz_sha256": sha256_file(REFINED_LAZ),
                "building_point_count": movement["count"],
                "point_displacement_support": (
                    "all class-6 points inside exact footprint; unchanged points included"
                ),
                "median_abs_point_dz_m": movement["median"],
                "p95_abs_point_dz_m": movement["p95"],
                "baseline_roofer_status": baseline["status"],
                "baseline_roofer_reason": baseline["status_reason"],
                "refined_roofer_status": status["status"],
                "refined_roofer_reason": status["reason"],
                "baseline_rf_extrusion_mode": baseline["rf_extrusion_mode"],
                "refined_rf_extrusion_mode": refined_mode,
                "baseline_has_lod22": baseline_lod2,
                "refined_has_lod22": refined_lod2,
                "delta_has_lod22": int(refined_lod2) - int(baseline_lod2),
                "baseline_lod1_fallback": parse_bool(
                    baseline.get("lod1_fallback")
                ),
                "refined_lod1_fallback": refined_fallback,
                "baseline_val3dity_valid": parse_bool(
                    baseline.get("val3dity_valid")
                ),
                "refined_val3dity_valid": valid.get(bid, False),
                "baseline_roof_face_count": baseline_faces,
                "refined_roof_face_count": refined_faces,
                "delta_roof_face_count": refined_faces - baseline_faces,
                "reference_roof_face_count": ref_faces,
                "baseline_face_count_ratio": baseline_ratio,
                "refined_face_count_ratio": refined_ratio,
                "delta_face_count_ratio": (
                    refined_ratio - baseline_ratio
                    if refined_ratio is not None
                    else None
                ),
                "baseline_roof_rms_m": baseline_rms,
                "refined_roof_rms_m": refined_rms,
                "delta_roof_rms_m": (
                    float(refined_rms) - baseline_rms
                    if refined_rms is not None and baseline_rms is not None
                    else None
                ),
                "refined_roof_hausdorff_m": comparison["ref_hausdorff_m"],
                "roofer_cityjson": rel(REFINED_CITYJSON),
                "roofer_cityjson_sha256": sha256_file(REFINED_CITYJSON),
                "roofer_parameters": ROOFER_PARAMETERS,
                "crs": CRS,
                "gt_role": (
                    "LoD2 reference opened only after refined Roofer output for scoring"
                ),
                "learning_runs_started": 0,
                "new_inference_runs": 0,
            }
        )
    if len(rows) != 18:
        raise RuntimeError(f"D output row drift {len(rows)}")
    atomic_csv(OUTPUT_CSV, rows)

    selected = representative_ids(rows)
    row_by_id = {row["building_id"]: row for row in rows}
    figure, axes = plt.subplots(len(selected), 3, figsize=(12, 3.5 * len(selected)), dpi=180)
    axes = np.asarray(axes, dtype=object).reshape(len(selected), 3)
    for index, bid in enumerate(selected):
        row = row_by_id[bid]
        plot_top(
            axes[index, 0],
            refs[bid],
            f"{bid}\nreference | faces={row['reference_roof_face_count']}",
        )
        plot_top(
            axes[index, 1],
            baseline_surfaces.get(bid, []),
            (
                f"dense w2_1 | faces={row['baseline_roof_face_count']}"
                f" | RMS={float(row['baseline_roof_rms_m']):.2f}"
                if row["baseline_roof_rms_m"] is not None
                else f"dense w2_1 | faces={row['baseline_roof_face_count']} | RMS=NA"
            ),
            bool(row["baseline_lod1_fallback"]),
        )
        refined_rms = row["refined_roof_rms_m"]
        plot_top(
            axes[index, 2],
            refined_surfaces.get(bid, []),
            (
                f"MLS default | faces={row['refined_roof_face_count']}"
                f" | RMS={float(refined_rms):.2f}"
                if refined_rms is not None
                else f"MLS default | faces={row['refined_roof_face_count']} | RMS=NA"
            ),
            bool(row["refined_lod1_fallback"]),
        )
    figure.suptitle(
        "Dense(w2_1) cheap-refinement pilot: reference | baseline | MLS default",
        fontsize=12,
    )
    figure.tight_layout(rect=[0, 0, 1, 0.98])
    FIGURE.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(FIGURE)
    plt.close(figure)

    prepared = json.loads(PREPARED.read_text(encoding="utf-8"))
    source_paths = [
        SOURCE_LAZ,
        FOOTPRINT_SOURCE,
        BASELINE_CITYJSON,
        BASELINE_SCORES,
        W2_SCRIPT,
        SMOOTH_SCRIPT,
        Path(__file__),
        DRIVER_SCRIPT,
    ]
    output_paths = [
        CLIPPED_LAZ,
        REFINED_LAZ,
        C001_FOOTPRINTS,
        C001_FOOTPRINTS_GPKG,
        REFINED_CITYJSON,
        VAL_REPORT,
        VAL_REPORT.with_suffix(".log"),
        OUTPUT_CSV,
        FIGURE,
        PREPARED,
        *jsonl_files,
        LOG_DIR / "prepare.log",
        LOG_DIR / "refine.log",
        LOG_DIR / "roofer.log",
    ]
    paired_rms_rows = [
        row
        for row in rows
        if row["baseline_roof_rms_m"] is not None
        and row["refined_roof_rms_m"] is not None
    ]
    movement_rows = [
        row for row in rows if row["median_abs_point_dz_m"] is not None
    ]
    lod2_transitions: Counter[str] = Counter()
    for row in rows:
        baseline_lod2 = bool(row["baseline_has_lod22"])
        refined_lod2 = bool(row["refined_has_lod22"])
        if baseline_lod2 and refined_lod2:
            lod2_transitions["retained"] += 1
        elif baseline_lod2:
            lod2_transitions["lost"] += 1
        elif refined_lod2:
            lod2_transitions["gained"] += 1
        else:
            lod2_transitions["neither"] += 1
    refined_modes = Counter(
        str(row["refined_rf_extrusion_mode"]) or "blank" for row in rows
    )
    refined_statuses = Counter(str(row["refined_roofer_status"]) for row in rows)
    summary = {
        "baseline_lod2_count": sum(bool(row["baseline_has_lod22"]) for row in rows),
        "refined_lod2_count": sum(bool(row["refined_has_lod22"]) for row in rows),
        "lod2_transition_counts": {
            key: int(lod2_transitions.get(key, 0))
            for key in ("retained", "lost", "gained", "neither")
        },
        "baseline_val3dity_valid_count": sum(
            bool(row["baseline_val3dity_valid"]) for row in rows
        ),
        "refined_val3dity_valid_count": sum(
            bool(row["refined_val3dity_valid"]) for row in rows
        ),
        "baseline_median_face_count_ratio": float(
            np.median([float(row["baseline_face_count_ratio"]) for row in rows])
        ),
        "refined_median_face_count_ratio": float(
            np.median([float(row["refined_face_count_ratio"]) for row in rows])
        ),
        "baseline_median_roof_rms_m": float(
            np.median(
                [
                    float(row["baseline_roof_rms_m"])
                    for row in rows
                    if row["baseline_roof_rms_m"] is not None
                ]
            )
        ),
        "baseline_roof_rms_measurable_count": sum(
            row["baseline_roof_rms_m"] is not None for row in rows
        ),
        "refined_median_roof_rms_m": float(
            np.median(
                [
                    float(row["refined_roof_rms_m"])
                    for row in rows
                    if row["refined_roof_rms_m"] is not None
                ]
            )
        ),
        "refined_roof_rms_measurable_count": sum(
            row["refined_roof_rms_m"] is not None for row in rows
        ),
        "paired_roof_rms_count": len(paired_rms_rows),
        "paired_baseline_median_roof_rms_m": (
            float(
                np.median(
                    [float(row["baseline_roof_rms_m"]) for row in paired_rms_rows]
                )
            )
            if paired_rms_rows
            else None
        ),
        "paired_refined_median_roof_rms_m": (
            float(
                np.median(
                    [float(row["refined_roof_rms_m"]) for row in paired_rms_rows]
                )
            )
            if paired_rms_rows
            else None
        ),
        "paired_median_delta_roof_rms_m": (
            float(
                np.median(
                    [float(row["delta_roof_rms_m"]) for row in paired_rms_rows]
                )
            )
            if paired_rms_rows
            else None
        ),
        "refined_rf_extrusion_mode_counts": dict(sorted(refined_modes.items())),
        "refined_roofer_status_counts": dict(sorted(refined_statuses.items())),
        "point_movement_building_count": len(movement_rows),
        "point_movement_sum_exact_footprint_class6_points": sum(
            int(row["building_point_count"]) for row in rows
        ),
        "median_building_median_abs_point_dz_m": (
            float(
                np.median(
                    [float(row["median_abs_point_dz_m"]) for row in movement_rows]
                )
            )
            if movement_rows
            else None
        ),
    }
    version_lines = [
        f"run_id: {RUN_ID}",
        f"created_utc: {now()}",
        f"git_head: {subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=REPO, text=True).strip()}",
        "tools_image: jointbuildgs-p0-tools:t0",
        f"roofer_image: {ROOFER_IMAGE}",
        f"val3dity: {subprocess.check_output(['val3dity', '--version'], text=True).strip()}",
        f"refinement_parameters: {json.dumps(REFINE_PARAMETERS, sort_keys=True)}",
        "learning_runs_started: 0",
    ]
    atomic_text(VERSIONS, "\n".join(version_lines) + "\n")
    output_paths.append(VERSIONS)
    manifest = {
        "schema": "jointbuildgs.qs_cheap_refine_pilot.v1",
        "created_utc": now(),
        "git_head_at_measurement": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=REPO, text=True
        ).strip(),
        "branch": subprocess.check_output(
            ["git", "branch", "--show-current"], cwd=REPO, text=True
        ).strip(),
        "population": "C001 18 buildings",
        "population_count": 18,
        "input": "canonical dense(w2_1) classified point cloud",
        "refinement_method": (
            "MLS-style local plane fit and z projection on roof-top class-6 points"
        ),
        "refinement_parameters": REFINE_PARAMETERS,
        "clip": {
            "bbox_epsg25832": prepared["clip_bbox_epsg25832"],
            "ground_context_margin_m": GROUND_CONTEXT_MARGIN_M,
            "building_clip_buffer_m": BUILDING_CLIP_BUFFER_M,
        },
        "roofer_image": ROOFER_IMAGE,
        "roofer_parameters": ROOFER_PARAMETERS,
        "val3dity_exit_code": val_exit,
        "summary": summary,
        "comparison_population_note": (
            "Unpaired baseline/refined medians use their separately measurable "
            "populations; paired_* fields use only buildings measurable in both."
        ),
        "point_displacement_support": (
            "All class-6 points inside each exact footprint; unchanged points included. "
            "The 0.5 m buffer is used only to retain assembly input near footprint edges."
        ),
        "representative_figure_buildings": selected,
        "representative_selection_rule": (
            "4907199 plus min/max delta RMS and max absolute face-count delta; unique first 4"
        ),
        "learning_runs_started": 0,
        "new_inference_runs": 0,
        "gt_role": "LoD2 reference used only after reconstruction for scoring and figure",
        "interpretation_or_verdict": None,
        "source_sha256": {
            rel(path): sha256_file(path) for path in source_paths if path.is_file()
        },
        "output_sha256": {
            rel(path): sha256_file(path) for path in output_paths if path.is_file()
        },
    }
    atomic_text(MANIFEST, json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    print(
        json.dumps(
            {
                "rows": len(rows),
                "summary": summary,
                "learning_runs_started": 0,
            },
            ensure_ascii=False,
        )
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("prepare", "finalize"))
    args = parser.parse_args()
    if args.mode == "prepare":
        prepare()
    else:
        finalize()


if __name__ == "__main__":
    main()
