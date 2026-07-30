#!/usr/bin/env python3
"""B wave: flat synthetic seed scoring and density-only Roofer sweep.

Subcommands:
  prepare   Generate flat seeds, official 0.5 m score rows, classified LAZ,
            and point-evidence roofprints for 0.5/0.25/0.125 m.
  finalize  Merge existing Roofer JSONSeq outputs, rerun val3dity, score all
            nine building-density models, draw the 3x3 top view, and execute
            the direct-plane conditional.

No GS optimization or model inference is started.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import importlib.util
import json
import math
import os
import platform
import subprocess
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence

os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib")
os.environ.setdefault("XDG_CACHE_HOME", "/tmp")

import laspy
import matplotlib
import numpy as np
from pyproj import CRS
from shapely import make_valid
from shapely.geometry import MultiPolygon, Point, Polygon, mapping

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

REPO = Path(__file__).resolve().parents[3]
SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import e5_c001_8way as metrics  # noqa: E402
import e5_c001_s3ap_phase0_baselines as p0  # noqa: E402


RUN_ID = "20260716_genclose_flat_density"
RUN_DIR = REPO / "phases/p2-gsjso/runs" / RUN_ID
SEED_DIR = RUN_DIR / "seeds"
INPUT_DIR = RUN_DIR / "roofer_inputs"
ROOFER_DIR = RUN_DIR / "roofer"
CITYJSON_DIR = RUN_DIR / "cityjson"
VAL_DIR = RUN_DIR / "val3dity"
LOG = RUN_DIR / "run.log"
MANIFEST = RUN_DIR / "manifest.json"
PREPARED = RUN_DIR / "prepared.json"
VERSIONS = RUN_DIR / "versions.txt"

DOCS = REPO / "docs"
FIG_DIR = DOCS / "figs/genclose"
SCORE_CSV = DOCS / "genclose_flat_seed_scores.csv"
ASSEMBLY_CSV = DOCS / "genclose_density_assembly.csv"
DIRECT_CSV = DOCS / "genclose_direct_plane.csv"
DIRECT_CITYJSON = RUN_DIR / "direct_plane/cityjson/genclose_direct_plane.city.json"
FIGURE = FIG_DIR / "genclose_density_assembly_topview.png"

TARGETS = ("4907199", "8568391", "8568392")
DENSITIES = (0.5, 0.25, 0.125)
DENSITY_LABEL = {0.5: "g0500", 0.25: "g0250", 0.125: "g0125"}
P0_FILL = REPO / "phases/p2-gsjso/runs/20260715_e5_c001_s3ap_phase0_baselines/p0_fill_points.npz"
P0_SCORE = DOCS / "s3b0_p0prime_scores.csv"
PLANEFIT = DOCS / "planefit_baseline.csv"
GROUND_SOURCE = DOCS / "e5_c001_s3ap_fm_retri_rescore.csv"
PROJECTION_DATUM = REPO / "configs/input_and_alignment/projection_datum.json"
TRAIN_MANIFEST = REPO / "results/tum_transfer/e5_pilot/C001/C001_train_prep_manifest.json"
FOOTPRINTS = REPO / "results/tum_transfer/analysis/footprints_aoi.geojson"
LOD2_DIR = REPO / "phases/p0-audit/data/raw/lod2"
W2_SCRIPT = REPO / "phases/p0-audit/scripts/08_roofer_w2.py"

EDGE_BAND_M = 1.0
FAR_BINS_M = (0.0, 1.0, 2.0, 4.0, 6.0)
ROOF_CLASS = 6
GROUND_CLASS = 2


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def rel(path: Path | str) -> str:
    value = Path(path)
    try:
        return str(value.resolve().relative_to(REPO.resolve()))
    except ValueError:
        return str(value.resolve())


def sha256_file(path: Path, block_size: int = 1 << 20) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(block_size), b""):
            digest.update(block)
    return digest.hexdigest()


def payload_sha256(array: np.ndarray) -> str:
    value = np.ascontiguousarray(array)
    return hashlib.sha256(value.view(np.uint8)).hexdigest()


def npy_bytes(array: np.ndarray) -> bytes:
    stream = io.BytesIO()
    np.lib.format.write_array(stream, np.asarray(array), allow_pickle=False)
    return stream.getvalue()


def atomic_deterministic_npz(path: Path, arrays: dict[str, np.ndarray]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("wb") as raw:
        with zipfile.ZipFile(
            raw,
            "w",
            compression=zipfile.ZIP_DEFLATED,
            compresslevel=9,
        ) as archive:
            for key in sorted(arrays):
                info = zipfile.ZipInfo(
                    f"{key}.npy",
                    date_time=(1980, 1, 1, 0, 0, 0),
                )
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o600 << 16
                archive.writestr(
                    info,
                    npy_bytes(arrays[key]),
                    compress_type=zipfile.ZIP_DEFLATED,
                    compresslevel=9,
                )
        raw.flush()
        os.fsync(raw.fileno())
    os.replace(temporary, path)


def metric_values(errors: np.ndarray) -> dict[str, float | None]:
    values = np.asarray(errors, dtype=np.float64)
    values = values[np.isfinite(values)]
    if not len(values):
        return {
            "signed_delta_z_median_m": None,
            "signed_delta_z_mad_m": None,
            "signed_delta_z_q05_m": None,
            "signed_delta_z_q95_m": None,
            "abs_delta_z_median_m": None,
            "rms_delta_z_m": None,
        }
    median = float(np.median(values))
    return {
        "signed_delta_z_median_m": median,
        "signed_delta_z_mad_m": float(np.median(np.abs(values - median))),
        "signed_delta_z_q05_m": float(np.quantile(values, 0.05)),
        "signed_delta_z_q95_m": float(np.quantile(values, 0.95)),
        "abs_delta_z_median_m": float(np.median(np.abs(values))),
        "rms_delta_z_m": float(np.sqrt(np.mean(values * values))),
    }


def nearest_distance(xy: np.ndarray, anchors: np.ndarray) -> np.ndarray:
    left = np.asarray(xy, dtype=np.float64).reshape(-1, 2)
    right = np.asarray(anchors, dtype=np.float64).reshape(-1, 2)
    if not len(right):
        return np.full(len(left), np.nan, dtype=np.float64)
    return np.sqrt(
        np.min(np.sum((left[:, None, :] - right[None, :, :]) ** 2, axis=2), axis=1)
    )


def score_masks(
    xy_utm: np.ndarray,
    footprint: Any,
    fm_xy_local: np.ndarray,
    xy_local: np.ndarray,
    edge_band_m: float,
    far_bins: Sequence[float],
    include_far_field: bool,
) -> list[tuple[str, float | None, float | None, np.ndarray]]:
    boundary_distance = np.asarray(
        [
            footprint.boundary.distance(Point(float(x), float(y)))
            for x, y in xy_utm
        ],
        dtype=np.float64,
    )
    scopes: list[tuple[str, float | None, float | None, np.ndarray]] = [
        ("overall", None, None, np.ones(len(xy_utm), dtype=bool)),
        ("edge", None, edge_band_m, boundary_distance <= edge_band_m),
        ("interior", edge_band_m, None, boundary_distance > edge_band_m),
    ]
    if include_far_field:
        distance = nearest_distance(xy_local, fm_xy_local)
        edges = [float(value) for value in far_bins]
        for index, lower in enumerate(edges):
            upper = edges[index + 1] if index + 1 < len(edges) else None
            mask = distance >= lower
            if upper is not None:
                mask &= distance < upper
            scopes.append(("far_field", lower, upper, mask))
    return scopes


def atomic_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def atomic_csv(path: Path, rows: Sequence[dict[str, Any]], fields: Sequence[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    with tmp.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(fields), extrasaction="ignore", lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: fmt(row.get(field)) for field in fields})
    os.replace(tmp, path)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def fmt(value: Any) -> Any:
    if value is None:
        return ""
    if isinstance(value, bool):
        return str(value).lower()
    if isinstance(value, (float, np.floating)):
        return "" if not math.isfinite(float(value)) else f"{float(value):.12f}"
    return value


def log(message: str) -> None:
    line = f"{now()} {message}"
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    print(line, flush=True)


def full_id(short: str) -> str:
    return f"DEBY_LOD2_{short}"


def density_path(root: Path, grid: float, suffix: str) -> Path:
    return root / f"flat_density_{DENSITY_LABEL[grid]}.{suffix}"


def load_module(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def load_anchors() -> dict[str, dict[str, Any]]:
    output: dict[str, dict[str, Any]] = {}
    for row in read_csv(PLANEFIT):
        short = row["building_id"].removeprefix("DEBY_LOD2_")
        if short not in TARGETS:
            continue
        output[short] = {
            "z_local_m": float(row["height_anchor_z_median_local_m"]),
            "count": int(float(row["fm_inside_point_count"])),
            "source": rel(PLANEFIT),
        }
    missing = sorted(set(TARGETS) - set(output))
    if missing:
        raise RuntimeError(f"missing anchors: {missing}")
    return output


def load_p0_baseline() -> dict[tuple[str, str, float | None, float | None], dict[str, str]]:
    result = {}
    for row in read_csv(P0_SCORE):
        if row.get("row_type") != "score" or row.get("variant") != "P0":
            continue
        short = row["building_id"].removeprefix("DEBY_LOD2_")
        if short not in TARGETS:
            continue
        lower = float(row["distance_lower_m"]) if row.get("distance_lower_m") else None
        upper = float(row["distance_upper_m"]) if row.get("distance_upper_m") else None
        result[(short, row["scope"], lower, upper)] = row
    return result


def seed_rgb(short: str) -> np.ndarray:
    path = (
        REPO
        / "phases/p2-gsjso/runs/20260715_e5_c001_s3ap_phase1_seedprep/seeds"
        / f"{full_id(short)}_p0_surface_seed.npz"
    )
    with np.load(path, allow_pickle=False) as archive:
        return np.asarray(archive["rgb"][0], dtype=np.float32)


def write_seed(short: str, grid: float, xyz64: np.ndarray, anchor: dict[str, Any]) -> Path:
    bid = full_id(short)
    path = SEED_DIR / f"{bid}_flat_{DENSITY_LABEL[grid]}_surface_seed.npz"
    xyz = np.ascontiguousarray(xyz64, dtype=np.float32)
    rgb = np.repeat(seed_rgb(short)[None, :], len(xyz), axis=0).astype(np.float32)
    sem = np.full(len(xyz), 1, dtype=np.int64)
    metadata = {
        "schema": "jointbuildgs.s3ap.surface_seeds.v1",
        "seed_type": "surface",
        "building_id": bid,
        "seed_variant": "flat_horizontal",
        "crs": "EPSG:25832",
        "coordinate_frame": "gs_local",
        "grid_m": grid,
        "height_anchor_source": "footprint_inside_MASt3R_correspondence_z_median",
        "height_anchor_count": anchor["count"],
        "height_anchor_z_median_local_m": anchor["z_local_m"],
        "plane_ax_local": 0.0,
        "plane_by_local": 0.0,
        "plane_c_local": anchor["z_local_m"],
        "gt_used_for_seed_generation": False,
        "lod2_used_for_seed_generation": False,
        "als_used_for_seed_generation": False,
        "learning_runs_started": 0,
        "new_inference_runs": 0,
    }
    atomic_deterministic_npz(
        path,
        {
            "metadata_json": np.asarray(
                json.dumps(metadata, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            ),
            "rgb": rgb,
            "sem": sem,
            "xyz": xyz,
        },
    )
    return path


def write_classified_laz(
    path: Path,
    fill_by_short: dict[str, np.ndarray],
    ground: dict[str, dict[str, Any]],
    offset: np.ndarray,
) -> None:
    roof = np.concatenate(
        [np.asarray(fill_by_short[short]) + offset[None, :] for short in TARGETS],
        axis=0,
    )
    ground_parts = []
    for short in TARGETS:
        part = np.asarray(fill_by_short[short]) + offset[None, :]
        part = part.copy()
        part[:, 2] = float(ground[short]["z_local_m"]) + offset[2]
        ground_parts.append(part)
    ground_xyz = np.concatenate(ground_parts, axis=0)
    xyz = np.vstack([roof, ground_xyz])
    classes = np.concatenate(
        [
            np.full(len(roof), ROOF_CLASS, dtype=np.uint8),
            np.full(len(ground_xyz), GROUND_CLASS, dtype=np.uint8),
        ]
    )
    header = laspy.LasHeader(point_format=6, version="1.4")
    header.scales = np.asarray([0.001, 0.001, 0.001])
    header.offsets = np.floor(np.min(xyz, axis=0))
    header.add_crs(CRS.from_epsg(25832))
    cloud = laspy.LasData(header)
    cloud.x, cloud.y, cloud.z = xyz[:, 0], xyz[:, 1], xyz[:, 2]
    cloud.classification = classes
    path.parent.mkdir(parents=True, exist_ok=True)
    cloud.write(path)


def write_roofprints(path: Path, fill_by_short: dict[str, np.ndarray], offset: np.ndarray, grid: float) -> None:
    features = []
    for short in TARGETS:
        geometry = p0.occupied_cell_union(fill_by_short[short], offset, grid)
        features.append(
            {
                "type": "Feature",
                "properties": {
                    "building_id": full_id(short),
                    "source": "flat_seed_point_occupied_cell_union",
                    "grid_m": grid,
                    "point_count": len(fill_by_short[short]),
                },
                "geometry": mapping(geometry),
            }
        )
    payload = {
        "type": "FeatureCollection",
        "name": f"flat_seed_roofprints_{DENSITY_LABEL[grid]}",
        "crs": {"type": "name", "properties": {"name": "urn:ogc:def:crs:EPSG::25832"}},
        "features": features,
    }
    atomic_text(path, json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n")


SCORE_FIELDS = [
    "building_id", "variant", "grid_m", "scope", "distance_lower_m", "distance_upper_m",
    "point_count", "signed_delta_z_median_m", "signed_delta_z_mad_m", "signed_delta_z_q05_m",
    "signed_delta_z_q95_m", "abs_delta_z_median_m", "rms_delta_z_m",
    "p0_signed_delta_z_median_m", "p0_abs_delta_z_median_m", "p0_rms_delta_z_m",
    "delta_signed_median_vs_p0_m", "delta_abs_median_vs_p0_m", "delta_rms_vs_p0_m",
    "plane_ax_local", "plane_by_local", "plane_c_local", "height_anchor_source",
    "height_anchor_count", "height_anchor_z_median_local_m", "seed_npz", "seed_npz_sha256",
    "seed_xyz_payload_sha256", "reference_source", "reference_used_for_seed_generation",
    "gt_used_for_seed_generation", "lod2_used_for_seed_generation", "als_used_for_seed_generation",
    "gt_used_for_score", "lod2_used_for_score", "als_used_for_score", "learning_runs_started",
    "new_inference_runs", "status", "note",
]

ASSEMBLY_FIELDS = [
    "building_id", "grid_m", "nominal_density_pt_m2", "density_variable_only",
    "classified_laz", "classified_laz_sha256", "roofprint_geojson", "roofprint_sha256",
    "roofer_cityjson", "roofer_cityjson_sha256", "roofer_status", "roofer_reason",
    "rf_extrusion_mode", "has_lod22", "lod1_fallback", "val3dity_valid",
    "val3dity_report", "roof_face_count_model", "roof_face_count_ref", "face_count_ratio",
    "roof_rms_m", "roof_hausdorff_m", "z_shift_to_reference_m", "roofer_parameters",
    "crs", "gt_role", "learning_runs_started", "new_inference_runs", "status",
]

DIRECT_FIELDS = [
    "row_type", "building_id", "execution_status", "skip_reason", "cityjson_path",
    "cityjson_sha256", "val3dity_valid", "val3dity_report", "roof_face_count",
    "plane_ax", "plane_by", "constant_z_local_m", "crs", "gt_role",
    "learning_runs_started", "new_inference_runs",
]


def prepare() -> None:
    RUN_DIR.mkdir(parents=True, exist_ok=True)
    SEED_DIR.mkdir(parents=True, exist_ok=True)
    INPUT_DIR.mkdir(parents=True, exist_ok=True)
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    atomic_text(LOG, "")
    offset = np.asarray(json.loads(TRAIN_MANIFEST.read_text(encoding="utf-8"))["world_offset"], dtype=np.float64)
    geoid = float(json.loads(PROJECTION_DATUM.read_text(encoding="utf-8"))["orthometric_geoid_m"])
    footprints = p0.load_footprints(TARGETS)
    anchors = load_anchors()
    ground = p0.load_observed_ground(GROUND_SOURCE, TARGETS)
    p0_archive = np.load(P0_FILL, allow_pickle=False)
    p0_baseline = load_p0_baseline()
    fill_by_density: dict[float, dict[str, np.ndarray]] = {}
    seed_paths: dict[tuple[str, float], Path] = {}

    # Generation stage: reference geometry is not opened here.
    for grid in DENSITIES:
        fill_by_density[grid] = {}
        for short in TARGETS:
            flat, eligible = p0.fill_footprint(
                footprints[short],
                offset,
                np.asarray([0.0, 0.0, anchors[short]["z_local_m"]], dtype=np.float64),
                grid,
            )
            if len(flat) != eligible:
                raise RuntimeError(f"flat lattice count drift {short} grid={grid}")
            fill_by_density[grid][short] = flat
            seed_paths[(short, grid)] = write_seed(short, grid, flat, anchors[short])
            log(f"seed {short} grid={grid} points={len(flat)} z={anchors[short]['z_local_m']:.6f}")
        laz_path = density_path(INPUT_DIR, grid, "laz")
        roofprint_path = density_path(INPUT_DIR, grid, "geojson")
        write_classified_laz(laz_path, fill_by_density[grid], ground, offset)
        write_roofprints(roofprint_path, fill_by_density[grid], offset, grid)
        log(f"roofer_input grid={grid} laz={rel(laz_path)} roofprint={rel(roofprint_path)}")

    # Score stage begins after all seed/assembly inputs are finalized.
    roofs = p0.load_lod2(TARGETS)
    score_rows: list[dict[str, Any]] = []
    for short in TARGETS:
        bid = full_id(short)
        flat = fill_by_density[0.5][short]
        fm_points = np.asarray(p0_archive[f"{bid}_fm_local_xyz"], dtype=np.float64)
        xy_local = flat[:, :2]
        xy_utm = xy_local + offset[None, :2]
        reference_z = p0.reference_z(xy_utm, roofs[short], geoid) - offset[2]
        errors = flat[:, 2] - reference_z
        scopes = score_masks(
            xy_utm,
            footprints[short],
            fm_points[:, :2],
            xy_local,
            EDGE_BAND_M,
            FAR_BINS_M,
            include_far_field=(short == "4907199"),
        )
        seed_path = seed_paths[(short, 0.5)]
        with np.load(seed_path, allow_pickle=False) as archive:
            xyz_payload = np.asarray(archive["xyz"], dtype=np.float32)
        for scope, lower, upper, mask in scopes:
            values = metric_values(errors[mask])
            baseline = p0_baseline[(short, scope, lower, upper)]
            base_signed = float(baseline["signed_delta_z_median_m"])
            base_abs = float(baseline["abs_delta_z_median_m"])
            base_rms = float(baseline["rms_delta_z_m"])
            row = {
                "building_id": bid,
                "variant": "flat_horizontal_v0",
                "grid_m": 0.5,
                "scope": scope,
                "distance_lower_m": lower,
                "distance_upper_m": upper,
                "point_count": int(mask.sum()),
                **values,
                "p0_signed_delta_z_median_m": base_signed,
                "p0_abs_delta_z_median_m": base_abs,
                "p0_rms_delta_z_m": base_rms,
                "delta_signed_median_vs_p0_m": (
                    values["signed_delta_z_median_m"] - base_signed
                    if values["signed_delta_z_median_m"] is not None
                    else None
                ),
                "delta_abs_median_vs_p0_m": (
                    values["abs_delta_z_median_m"] - base_abs
                    if values["abs_delta_z_median_m"] is not None
                    else None
                ),
                "delta_rms_vs_p0_m": (
                    values["rms_delta_z_m"] - base_rms
                    if values["rms_delta_z_m"] is not None
                    else None
                ),
                "plane_ax_local": 0.0,
                "plane_by_local": 0.0,
                "plane_c_local": anchors[short]["z_local_m"],
                "height_anchor_source": "footprint_inside_MASt3R_correspondence_z_median",
                "height_anchor_count": anchors[short]["count"],
                "height_anchor_z_median_local_m": anchors[short]["z_local_m"],
                "seed_npz": rel(seed_path),
                "seed_npz_sha256": sha256_file(seed_path),
                "seed_xyz_payload_sha256": payload_sha256(xyz_payload),
                "reference_source": "CityGML LoD2 RoofSurface + configured orthometric geoid",
                "reference_used_for_seed_generation": False,
                "gt_used_for_seed_generation": False,
                "lod2_used_for_seed_generation": False,
                "als_used_for_seed_generation": False,
                "gt_used_for_score": True,
                "lod2_used_for_score": True,
                "als_used_for_score": False,
                "learning_runs_started": 0,
                "new_inference_runs": 0,
                "status": "measured" if int(mask.sum()) else "empty_scope",
                "note": "reference opened after all flat seeds and Roofer inputs were written",
            }
            score_rows.append(row)
    atomic_csv(SCORE_CSV, score_rows, SCORE_FIELDS)
    prepared = {
        "schema": "jointbuildgs.genclose.prepare.v1",
        "created_utc": now(),
        "targets": list(TARGETS),
        "grids_m": list(DENSITIES),
        "offset": offset.tolist(),
        "geoid_m": geoid,
        "learning_runs_started": 0,
        "new_inference_runs": 0,
        "roofer_parameters": (
            "--id-attribute building_id --jobs 3 --srs EPSG:25832 "
            "--bld-class 6 --grnd-class 2 --lod22"
        ),
        "inputs": {
            DENSITY_LABEL[grid]: {
                "laz": rel(density_path(INPUT_DIR, grid, "laz")),
                "roofprint": rel(density_path(INPUT_DIR, grid, "geojson")),
            }
            for grid in DENSITIES
        },
    }
    atomic_text(PREPARED, json.dumps(prepared, ensure_ascii=False, indent=2) + "\n")
    atomic_text(
        VERSIONS,
        "\n".join(
            [
                f"created_utc={now()}",
                f"git_head={subprocess.check_output(['git','rev-parse','HEAD'],cwd=REPO,text=True).strip()}",
                f"python={platform.python_version()}",
                "tools_image=jointbuildgs-p0-tools:t0",
                "roofer_image=3dgi/roofer@sha256:dd2c415aaee337502bde0dc1426dfa9c9f88e648f9d2f6340110c49932c251d2",
                "val3dity=2.6.0",
                "learning_runs_started=0",
                "",
            ]
        ),
    )
    log(f"prepare complete score_rows={len(score_rows)} learning_runs_started=0")


def run_val3dity(cityjson: Path, report: Path) -> tuple[int, dict[str, bool]]:
    report.parent.mkdir(parents=True, exist_ok=True)
    log_path = report.with_suffix(".log")
    proc = subprocess.run(
        ["val3dity", cityjson.as_posix(), "--report", report.as_posix()],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    atomic_text(log_path, f"+ val3dity {cityjson} --report {report}\n{proc.stdout or ''}")
    payload = json.loads(report.read_text(encoding="utf-8"))
    valid = {
        str(feature.get("id")): bool(feature.get("validity"))
        for feature in payload.get("features", [])
        if feature.get("id")
    }
    return int(proc.returncode), valid


def parse_bool(value: Any) -> bool:
    return str(value).strip().lower() in {"true", "1"}


def combine_and_status(grid: float) -> tuple[Path, list[dict[str, str]], dict[str, bool], Path]:
    label = DENSITY_LABEL[grid]
    jsonl_files = sorted((ROOFER_DIR / label).glob("*.city.jsonl"))
    if not jsonl_files:
        raise RuntimeError(f"missing Roofer JSONSeq grid={grid}: {ROOFER_DIR / label}")
    w2 = load_module(f"genclose_w2_{label}", W2_SCRIPT)
    cityjson = CITYJSON_DIR / f"flat_density_{label}.city.json"
    cityjson.parent.mkdir(parents=True, exist_ok=True)
    w2.combine_cityjsonseq(jsonl_files, cityjson)
    report = VAL_DIR / f"flat_density_{label}.json"
    _exit, valid = run_val3dity(cityjson, report)
    val_payload = json.loads(report.read_text(encoding="utf-8"))
    val_by_id = {
        str(feature.get("id")): feature
        for feature in val_payload.get("features", [])
        if feature.get("id") is not None
    }
    roofer_by_id = w2.parse_roofer_features(jsonl_files)
    status = w2.classify_buildings("FLAT", [full_id(short) for short in TARGETS], roofer_by_id, val_by_id)
    return cityjson, status, valid, report


def plot_top(ax: Any, surfaces: Sequence[Any], title: str, fallback: bool) -> None:
    colors = plt.cm.Set3(np.linspace(0, 1, max(1, len(surfaces))))
    for index, surface in enumerate(surfaces):
        for polygon in metrics.flatten_polygons(surface.polygon):
            ring = np.asarray(polygon.exterior.coords)
            ax.fill(
                ring[:, 0],
                ring[:, 1],
                color=colors[index % len(colors)],
                edgecolor="black",
                linewidth=0.55,
                alpha=0.8,
            )
    if not surfaces:
        ax.text(0.5, 0.5, "no roof geometry", transform=ax.transAxes, ha="center", va="center")
    ax.set_aspect("equal")
    label = "LoD1 fallback" if fallback else "LoD2"
    ax.set_title(f"{title}\n{label}", fontsize=8)
    ax.set_xticks([])
    ax.set_yticks([])


def polygon_exterior(geom: Polygon | MultiPolygon) -> np.ndarray:
    polygon = geom if isinstance(geom, Polygon) else max(geom.geoms, key=lambda item: item.area)
    ring = np.asarray(polygon.exterior.coords, dtype=np.float64)
    if np.allclose(ring[0], ring[-1]):
        ring = ring[:-1]
    signed_area = 0.5 * np.sum(
        ring[:, 0] * np.roll(ring[:, 1], -1)
        - np.roll(ring[:, 0], -1) * ring[:, 1]
    )
    if signed_area < 0:
        ring = ring[::-1]
    return ring


def direct_cityjson(
    footprints: dict[str, Any],
    anchors: dict[str, dict[str, Any]],
    ground: dict[str, dict[str, Any]],
    offset: np.ndarray,
) -> None:
    vertices: list[list[float]] = []
    cityobjects: dict[str, Any] = {}

    def add_vertex(value: Iterable[float]) -> int:
        vertices.append([float(item) for item in value])
        return len(vertices) - 1

    for short in TARGETS:
        bid = full_id(short)
        ring = polygon_exterior(footprints[short])
        roof_z = float(anchors[short]["z_local_m"] + offset[2])
        ground_z = float(ground[short]["z_local_m"] + offset[2])
        roof_indices = [add_vertex((x, y, roof_z)) for x, y in ring]
        ground_indices = [add_vertex((x, y, ground_z)) for x, y in ring]
        faces: list[list[list[int]]] = []
        semantics: list[int] = []
        faces.append([roof_indices])
        semantics.append(0)
        reversed_ground = list(reversed(ground_indices))
        faces.append([reversed_ground])
        semantics.append(1)
        for index in range(len(ring)):
            nxt = (index + 1) % len(ring)
            faces.append(
                [[
                    ground_indices[index],
                    ground_indices[nxt],
                    roof_indices[nxt],
                    roof_indices[index],
                ]]
            )
            semantics.append(2)
        cityobjects[bid] = {
            "type": "Building",
            "geometry": [
                {
                    "type": "Solid",
                    "lod": "2.2",
                    "boundaries": [faces],
                    "semantics": {
                        "surfaces": [
                            {"type": "RoofSurface"},
                            {"type": "GroundSurface"},
                            {"type": "WallSurface"},
                        ],
                        "values": [[semantics]],
                    },
                }
            ],
        }
    payload = {
        "type": "CityJSON",
        "version": "2.0",
        "metadata": {
            "referenceSystem": "https://www.opengis.net/def/crs/EPSG/0/25832",
            "title": "genclose direct horizontal-plane conditional",
        },
        "CityObjects": cityobjects,
        "vertices": vertices,
    }
    atomic_text(DIRECT_CITYJSON, json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n")


def conditional_direct(all_fallback: bool, offset: np.ndarray) -> list[dict[str, Any]]:
    if not all_fallback:
        return [
            {
                "row_type": "skip",
                "building_id": "",
                "execution_status": "skipped",
                "skip_reason": "B-2 produced at least one accepted LoD2 assembly",
                "cityjson_path": "",
                "cityjson_sha256": "",
                "val3dity_valid": "",
                "val3dity_report": "",
                "roof_face_count": "",
                "plane_ax": "",
                "plane_by": "",
                "constant_z_local_m": "",
                "crs": "EPSG:25832",
                "gt_role": "none",
                "learning_runs_started": 0,
                "new_inference_runs": 0,
            }
        ]
    footprints = p0.load_footprints(TARGETS)
    anchors = load_anchors()
    ground = p0.load_observed_ground(GROUND_SOURCE, TARGETS)
    direct_cityjson(footprints, anchors, ground, offset)
    report = DIRECT_CITYJSON.parent / "genclose_direct_plane_val3dity.json"
    _exit, valid = run_val3dity(DIRECT_CITYJSON, report)
    return [
        {
            "row_type": "direct_plane",
            "building_id": full_id(short),
            "execution_status": "executed_all_density_fallback",
            "skip_reason": "",
            "cityjson_path": rel(DIRECT_CITYJSON),
            "cityjson_sha256": sha256_file(DIRECT_CITYJSON),
            "val3dity_valid": valid.get(full_id(short), False),
            "val3dity_report": rel(report),
            "roof_face_count": 1,
            "plane_ax": 0.0,
            "plane_by": 0.0,
            "constant_z_local_m": anchors[short]["z_local_m"],
            "crs": "EPSG:25832",
            "gt_role": "reference not used for direct geometry construction or validity",
            "learning_runs_started": 0,
            "new_inference_runs": 0,
        }
        for short in TARGETS
    ]


def finalize() -> None:
    if not PREPARED.is_file():
        raise FileNotFoundError(PREPARED)
    offset = np.asarray(json.loads(TRAIN_MANIFEST.read_text(encoding="utf-8"))["world_offset"], dtype=np.float64)
    geoid = float(json.loads(PROJECTION_DATUM.read_text(encoding="utf-8"))["orthometric_geoid_m"])
    refs = metrics.parse_lod2_roofs(LOD2_DIR, {full_id(short) for short in TARGETS})
    rows: list[dict[str, Any]] = []
    surfaces: dict[tuple[str, float], list[Any]] = {}
    for grid in DENSITIES:
        cityjson, statuses, valid, report = combine_and_status(grid)
        status_by_id = {row["building_id"]: row for row in statuses}
        parsed = metrics.parse_cityjson_roofs(cityjson, {full_id(short) for short in TARGETS})
        for short in TARGETS:
            bid = full_id(short)
            predicted = metrics.shift_surface_z(parsed.get(bid, []), -geoid)
            surfaces[(short, grid)] = predicted
            comparison = metrics.compare_building(refs[bid], predicted)
            status = status_by_id[bid]
            mode = status.get("rf_extrusion_mode", "")
            fallback = mode == "lod11_fallback"
            has_lod22 = parse_bool(status.get("has_lod22")) and not fallback
            face_count = 1 if fallback else len(predicted)
            ref_count = len(refs[bid])
            laz_path = density_path(INPUT_DIR, grid, "laz")
            roofprint_path = density_path(INPUT_DIR, grid, "geojson")
            rows.append(
                {
                    "building_id": bid,
                    "grid_m": grid,
                    "nominal_density_pt_m2": 1.0 / (grid * grid),
                    "density_variable_only": True,
                    "classified_laz": rel(laz_path),
                    "classified_laz_sha256": sha256_file(laz_path),
                    "roofprint_geojson": rel(roofprint_path),
                    "roofprint_sha256": sha256_file(roofprint_path),
                    "roofer_cityjson": rel(cityjson),
                    "roofer_cityjson_sha256": sha256_file(cityjson),
                    "roofer_status": status.get("status", ""),
                    "roofer_reason": status.get("reason", ""),
                    "rf_extrusion_mode": mode,
                    "has_lod22": has_lod22,
                    "lod1_fallback": fallback,
                    "val3dity_valid": valid.get(bid, False),
                    "val3dity_report": rel(report),
                    "roof_face_count_model": face_count,
                    "roof_face_count_ref": ref_count,
                    "face_count_ratio": face_count / ref_count if ref_count else None,
                    "roof_rms_m": comparison["ref_rms_m"],
                    "roof_hausdorff_m": comparison["ref_hausdorff_m"],
                    "z_shift_to_reference_m": -geoid,
                    "roofer_parameters": (
                        "--id-attribute building_id --jobs 3 --srs EPSG:25832 "
                        "--bld-class 6 --grnd-class 2 --lod22"
                    ),
                    "crs": "EPSG:25832",
                    "gt_role": "LoD2 reference opened after Roofer output for scoring only",
                    "learning_runs_started": 0,
                    "new_inference_runs": 0,
                    "status": "measured",
                }
            )
        atomic_csv(ASSEMBLY_CSV, rows, ASSEMBLY_FIELDS)
        log(f"finalize grid={grid} rows={len(rows)}")
    if len(rows) != 9:
        raise RuntimeError(f"density sweep row count {len(rows)} != 9")

    figure, axes = plt.subplots(3, 3, figsize=(11.5, 11.0), dpi=180)
    row_by_key = {(row["building_id"].removeprefix("DEBY_LOD2_"), float(row["grid_m"])): row for row in rows}
    for row_index, short in enumerate(TARGETS):
        for col_index, grid in enumerate(DENSITIES):
            row = row_by_key[(short, grid)]
            plot_top(
                axes[row_index, col_index],
                surfaces[(short, grid)],
                f"{short} | grid {grid:g} m | faces {row['roof_face_count_model']}",
                bool(row["lod1_fallback"]),
            )
    figure.suptitle("Flat synthetic point cloud: canonical Roofer density-only sweep", fontsize=12)
    figure.tight_layout(rect=[0, 0, 1, 0.98])
    FIGURE.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(FIGURE)
    plt.close(figure)

    direct_rows = conditional_direct(all(not bool(row["has_lod22"]) for row in rows), offset)
    atomic_csv(DIRECT_CSV, direct_rows, DIRECT_FIELDS)
    write_manifest(rows, direct_rows)
    log(
        f"finalize complete rows={len(rows)} lod2={sum(bool(row['has_lod22']) for row in rows)} "
        f"direct={direct_rows[0]['execution_status']} learning_runs_started=0"
    )


def write_manifest(rows: Sequence[dict[str, Any]], direct_rows: Sequence[dict[str, Any]]) -> None:
    source_paths = {
        Path(__file__),
        P0_FILL,
        P0_SCORE,
        PLANEFIT,
        GROUND_SOURCE,
        PROJECTION_DATUM,
        TRAIN_MANIFEST,
        FOOTPRINTS,
        W2_SCRIPT,
        REPO / "phases/p2-gsjso/scripts/e5_c001_s3ap_phase0_baselines.py",
        REPO / "scripts/e5_c001/s3b0/e5_c001_s3b0_common.py",
        REPO / "scripts/e5_c001/s3b0/e5_c001_s3b0_seed.py",
        *sorted(LOD2_DIR.glob("*.gml")),
    }
    outputs = {
        SCORE_CSV,
        ASSEMBLY_CSV,
        DIRECT_CSV,
        FIGURE,
        PREPARED,
        VERSIONS,
        LOG,
        *sorted(SEED_DIR.glob("*.npz")),
        *sorted(INPUT_DIR.glob("*")),
        *sorted(CITYJSON_DIR.glob("*")),
        *sorted(VAL_DIR.glob("*")),
        *sorted(ROOFER_DIR.glob("**/*")),
    }
    if DIRECT_CITYJSON.is_file():
        outputs.add(DIRECT_CITYJSON)
        outputs.update(DIRECT_CITYJSON.parent.glob("*"))
    payload = {
        "schema": "jointbuildgs.genclose.flat_density.v1",
        "created_utc": now(),
        "git_head_at_measurement": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=REPO, text=True
        ).strip(),
        "branch": subprocess.check_output(
            ["git", "branch", "--show-current"], cwd=REPO, text=True
        ).strip(),
        "targets": list(TARGETS),
        "grids_m": list(DENSITIES),
        "density_is_only_roofer_input_variable": True,
        "roofer_parameters": (
            "--id-attribute building_id --jobs 3 --srs EPSG:25832 "
            "--bld-class 6 --grnd-class 2 --lod22"
        ),
        "assembly_rows": len(rows),
        "lod2_count": sum(bool(row["has_lod22"]) for row in rows),
        "direct_conditional_status": direct_rows[0]["execution_status"],
        "learning_runs_started": 0,
        "new_inference_runs": 0,
        "interpretation_or_verdict": None,
        "source_sha256": {
            rel(path): sha256_file(path)
            for path in sorted(source_paths)
            if path.is_file()
        },
        "output_sha256": {
            rel(path): sha256_file(path)
            for path in sorted(outputs)
            if path.is_file() and path != MANIFEST
        },
    }
    atomic_text(MANIFEST, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("prepare", "finalize"))
    args = parser.parse_args()
    if args.command == "prepare":
        prepare()
    else:
        finalize()


if __name__ == "__main__":
    main()
