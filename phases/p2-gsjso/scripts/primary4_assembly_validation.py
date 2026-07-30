#!/usr/bin/env python3
"""E-PRIMARY4 learning-zero flat-input assembly measurement.

The generation stage reuses the B-1 0.5 m footprint-fill and occupied-cell
roofprint functions.  Locked MASt3R anchor medians are read from the v4.1
ladder.  LoD2 reference geometry is opened only by ``score-group`` after the
classified LAZ and roofprint inputs have been written.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import io
import json
import math
import os
import platform
import subprocess
import sys
import time
import zipfile
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterable, Sequence

os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib")
os.environ.setdefault("XDG_CACHE_HOME", "/tmp")

import laspy
import numpy as np
from pyproj import CRS
from shapely import contains_xy, make_valid
from shapely.geometry import GeometryCollection, MultiPolygon, Point, Polygon, box, mapping, shape
from shapely.ops import unary_union

REPO = Path(__file__).resolve().parents[3]
SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import e5_c001_8way as metrics  # noqa: E402
import e5_c001_s3ap_phase0_baselines as p0  # noqa: E402


TASK_ID = "E-PRIMARY4-20260721"
RUN_ID = "20260721_primary4_assembly_validation"
RUN_DIR = REPO / "phases/p2-gsjso/runs" / RUN_ID
INPUT_DIR = RUN_DIR / "inputs"
POINT_DIR = RUN_DIR / "flat_points"
ROOFER_DIR = RUN_DIR / "roofer"
CITYJSON_DIR = RUN_DIR / "cityjson"
VAL_DIR = RUN_DIR / "val3dity"
LOG = RUN_DIR / "run.log"
PREFLIGHT = RUN_DIR / "preflight.json"
PREPARED = RUN_DIR / "prepared.json"
VERSIONS = RUN_DIR / "versions.txt"

CONFIG_PATH = REPO / "phases/p2-gsjso/configs/primary4_assembly_validation_v2.json"
QA_SCRIPT = REPO / "phases/p2-gsjso/scripts/primary4_assembly_validation_qa.py"
DOCS = REPO / "docs"
MEASUREMENTS = DOCS / "primary4_assembly_validation_measurements.csv"
SUMMARY = DOCS / "W_primary4_assembly_validation_summary_20260721.md"
MANIFEST = DOCS / "primary4_assembly_validation_manifest.json"

GROUPS = {
    "reproduction": ("4907199",),
    "targets": ("4908049", "104586480", "4908048"),
}

ROOFER_PARAMETERS = (
    "--id-attribute building_id --jobs 3 --srs EPSG:25832 "
    "--bld-class 6 --grnd-class 2 --lod22"
)


MEASUREMENT_FIELDS = [
    "task_id",
    "row_role",
    "building_id",
    "anchor_source",
    "anchor_inside_z_median_m",
    "anchor_footprint_inside_point_count",
    "anchor_inside_z_mad_m",
    "ref_roof_type",
    "input_note",
    "grid_m",
    "nominal_density_pt_m2",
    "flat_point_count",
    "flat_points_npz",
    "flat_points_npz_sha256",
    "flat_xyz_payload_sha256",
    "ground_z_local_m",
    "ground_z_mad_m",
    "ground_method",
    "ground_observed_point_count",
    "ground_cell_count",
    "ground_mode_cell_count",
    "ground_source",
    "classified_laz",
    "classified_laz_sha256",
    "roofprint_geojson",
    "roofprint_geojson_sha256",
    "roofer_cityjson",
    "roofer_cityjson_sha256",
    "roofer_status",
    "roofer_reason",
    "rf_extrusion_mode",
    "assembly_success",
    "has_lod22",
    "has_lod22_geometry",
    "lod1_fallback",
    "val3dity_valid",
    "val3dity_report",
    "val3dity_exit_code",
    "roof_face_count_model",
    "roof_face_count_ref",
    "face_count_ratio",
    "signed_delta_z_median_m",
    "signed_delta_z_mad_m",
    "signed_delta_z_q05_m",
    "signed_delta_z_q95_m",
    "abs_delta_z_median_m",
    "roof_rms_m",
    "roof_hausdorff_m",
    "roof_distance_samples",
    "roof_completeness",
    "model_roof_xy_area_m2",
    "reference_roof_xy_area_m2",
    "roof_overlap_xy_area_m2",
    "success_gauge_id",
    "success_gauge_formula",
    "success_gauge_max_abs_error_m",
    "success_gauge_true",
    "roofer_parameters",
    "crs",
    "reference_role",
    "reference_used_for_input_generation",
    "learning_runs_started",
    "new_inference_runs",
    "image_inputs_used",
    "gpu_used",
    "roofer_wall_seconds",
    "score_wall_seconds",
    "elapsed_seconds",
    "status",
]


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def rel(path: Path | str) -> str:
    value = Path(path)
    try:
        return str(value.resolve().relative_to(REPO.resolve()))
    except ValueError:
        return str(value.resolve())


def full_id(short: str) -> str:
    return f"DEBY_LOD2_{short}"


def sha256_file(path: Path, block_size: int = 1 << 20) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block_data in iter(lambda: handle.read(block_size), b""):
            digest.update(block_data)
    return digest.hexdigest()


def payload_sha256(array: np.ndarray) -> str:
    value = np.ascontiguousarray(array)
    return hashlib.sha256(value.view(np.uint8)).hexdigest()


def atomic_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(text, encoding="utf-8")
    os.replace(temporary, path)


def atomic_json(path: Path, payload: Any) -> None:
    atomic_text(path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


def fmt(value: Any) -> Any:
    if value is None:
        return ""
    if isinstance(value, bool):
        return str(value).lower()
    if isinstance(value, (float, np.floating)):
        return "" if not math.isfinite(float(value)) else f"{float(value):.12f}"
    return value


def atomic_csv(path: Path, rows: Sequence[dict[str, Any]], fields: Sequence[str]) -> None:
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
            writer.writerow({field: fmt(row.get(field)) for field in fields})
    os.replace(temporary, path)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def log(message: str) -> None:
    line = f"{now()} {message}"
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    print(line, flush=True)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def config() -> dict[str, Any]:
    payload = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    require(payload["learning_runs_allowed"] == 0, "learning lock drift")
    require(payload["new_inference_runs_allowed"] == 0, "inference lock drift")
    require(payload["image_inputs_allowed"] == 0, "image-input lock drift")
    require(payload["success_gauge"]["selected"] == "b", "success gauge drift")
    require(float(payload["grid_m"]) == 0.5, "grid lock drift")
    require(payload["roofer"]["parameters"] == ROOFER_PARAMETERS, "Roofer parameter drift")
    return payload


def load_module(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot import {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def npy_bytes(array: np.ndarray) -> bytes:
    stream = io.BytesIO()
    np.lib.format.write_array(stream, np.asarray(array), allow_pickle=False)
    return stream.getvalue()


def atomic_deterministic_npz(path: Path, arrays: dict[str, np.ndarray]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("wb") as raw:
        with zipfile.ZipFile(raw, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
            for key in sorted(arrays):
                info = zipfile.ZipInfo(f"{key}.npy", date_time=(1980, 1, 1, 0, 0, 0))
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


def anchor_rows(cfg: dict[str, Any]) -> dict[str, dict[str, Any]]:
    ladder = REPO / cfg["source_paths"]["anchor_ladder"]
    selected = {
        row["building_id"].removeprefix("DEBY_LOD2_"): row
        for row in read_csv(ladder)
        if row["building_id"].removeprefix("DEBY_LOD2_")
        in cfg["targets_in_output_order"]
    }
    require(set(selected) == set(cfg["targets_in_output_order"]), "anchor target-set mismatch")
    for short, expected in cfg["anchor_lock"].items():
        row = selected[short]
        for field in (
            "anchor_inside_z_median_m",
            "anchor_footprint_inside_point_count",
            "anchor_inside_z_mad_m",
            "ref_roof_type",
        ):
            require(
                row[field] == str(expected[field]),
                f"anchor lock mismatch {short} {field}: {row[field]} != {expected[field]}",
            )
        require(row["anchor_status"] == "measured", f"anchor status drift {short}")
        require(row["learning_runs_started"] == "0", f"anchor learning drift {short}")
    return selected


def b1_lock_check(cfg: dict[str, Any]) -> dict[str, Any]:
    sources = cfg["source_paths"]
    b1_manifest_path = REPO / sources["b1_manifest"]
    b1_manifest = json.loads(b1_manifest_path.read_text(encoding="utf-8"))
    b1_script = REPO / sources["b1_script"]
    require(
        b1_manifest["source_sha256"][rel(b1_script)] == sha256_file(b1_script),
        "B-1 script SHA drift",
    )
    flat_rows = [
        row
        for row in read_csv(REPO / sources["b1_flat_scores"])
        if row["building_id"] == full_id("4907199")
        and row["scope"] == "overall"
        and Decimal(row["grid_m"]) == Decimal("0.5")
    ]
    assembly_rows = [
        row
        for row in read_csv(REPO / sources["b1_assembly_scores"])
        if row["building_id"] == full_id("4907199")
        and Decimal(row["grid_m"]) == Decimal("0.5")
    ]
    require(len(flat_rows) == 1, "B-1 199 flat row cardinality drift")
    require(len(assembly_rows) == 1, "B-1 199 assembly row cardinality drift")
    flat = flat_rows[0]
    assembly = assembly_rows[0]
    expected = cfg["reproduction_hard_stop"]
    require(
        Decimal(flat["signed_delta_z_median_m"])
        == Decimal(expected["expected_b1_seed_signed_delta_z_median_m"]),
        "B-1 seed signed median drift",
    )
    require(int(flat["point_count"]) == int(expected["expected_flat_point_count"]), "B-1 fill count drift")
    require(
        Decimal(assembly["roof_rms_m"]) == Decimal(expected["expected_b1_roof_rms_m"]),
        "B-1 assembly RMS drift",
    )
    require(
        Decimal(assembly["roof_hausdorff_m"])
        == Decimal(expected["expected_b1_roof_hausdorff_m"]),
        "B-1 assembly Hausdorff drift",
    )
    require(assembly["rf_extrusion_mode"] == expected["expected_b1_rf_extrusion_mode"], "B-1 mode drift")
    require(
        (assembly["has_lod22"].lower() == "true") is bool(expected["expected_b1_has_lod22"]),
        "B-1 has_lod22 drift",
    )
    require(
        (assembly["lod1_fallback"].lower() == "true") is bool(expected["expected_b1_lod1_fallback"]),
        "B-1 fallback drift",
    )
    require(
        (assembly["val3dity_valid"].lower() == "true") is bool(expected["expected_b1_val3dity_valid"]),
        "B-1 val3dity drift",
    )
    return {
        "manifest": rel(b1_manifest_path),
        "manifest_sha256": sha256_file(b1_manifest_path),
        "script": rel(b1_script),
        "script_sha256": sha256_file(b1_script),
        "flat_score_row": flat,
        "assembly_score_row": assembly,
    }


def preflight() -> None:
    cfg = config()
    anchors = anchor_rows(cfg)
    b1 = b1_lock_check(cfg)
    source_paths = [
        REPO / path
        for path in cfg["source_paths"].values()
        if not str(path).endswith("lod2")
    ]
    missing = [rel(path) for path in source_paths if not path.exists()]
    require(not missing, f"missing sources: {missing}")
    crop_manifest = json.loads(
        (REPO / cfg["source_paths"]["c001_crop_manifest"]).read_text(encoding="utf-8")
    )
    require(
        crop_manifest["seed_clips"]["sparse"]["source"]
        == cfg["source_paths"]["full_sparse_seed"],
        "sparse parent-source lineage drift",
    )
    require(
        crop_manifest["seed_clips"]["dense"]["source"]
        == cfg["source_paths"]["full_dense_seed"],
        "dense parent-source lineage drift",
    )
    payload = {
        "schema": "jointbuildgs.primary4.preflight.v2",
        "created_utc": now(),
        "task_id": TASK_ID,
        "target_set_match": True,
        "target_order": cfg["targets_in_output_order"],
        "anchor_lock_match": True,
        "anchor_values": {
            short: {
                "z": row["anchor_inside_z_median_m"],
                "inside_count": row["anchor_footprint_inside_point_count"],
                "mad": row["anchor_inside_z_mad_m"],
                "ref_roof_type": row["ref_roof_type"],
            }
            for short, row in anchors.items()
        },
        "b1_lock_match": True,
        "b1": b1,
        "success_gauge_locked_before_measurement": cfg["success_gauge"],
        "learning_runs_started": 0,
        "new_inference_runs": 0,
        "image_inputs_used": 0,
        "gpu_used": False,
    }
    atomic_json(PREFLIGHT, payload)
    log("preflight complete target_set=4 anchor_lock=true b1_lock=true learning=0 inference=0")


def read_xyz_ply(path: Path) -> np.ndarray:
    header = bytearray()
    with path.open("rb") as handle:
        while b"end_header\n" not in header:
            line = handle.readline()
            if not line:
                raise RuntimeError(f"incomplete PLY header: {rel(path)}")
            header.extend(line)
        text = header.decode("ascii")
        lines = text.splitlines()
        vertex_line = next((line for line in lines if line.startswith("element vertex ")), None)
        format_line = next((line for line in lines if line.startswith("format ")), None)
        require(vertex_line is not None and format_line is not None, f"PLY metadata missing: {rel(path)}")
        count = int(vertex_line.split()[-1])
        properties = [line for line in lines if line.startswith("property ")]
        if "binary_little_endian" in format_line:
            require(
                properties == ["property float64 x", "property float64 y", "property float64 z"],
                f"unsupported binary PLY schema: {rel(path)} {properties}",
            )
            structured = np.fromfile(
                handle,
                dtype=np.dtype([("x", "<f8"), ("y", "<f8"), ("z", "<f8")]),
                count=count,
            )
            points = structured.view("<f8").reshape(-1, 3)
        elif "ascii" in format_line:
            points = np.loadtxt(
                path,
                skiprows=len(lines),
                max_rows=count,
                usecols=(0, 1, 2),
                dtype=np.float64,
            )
        else:
            raise RuntimeError(f"unsupported PLY format: {format_line}")
    points = np.asarray(points, dtype=np.float64).reshape(-1, 3)
    require(len(points) == count, f"PLY count mismatch {rel(path)}: {len(points)} != {count}")
    require(np.isfinite(points).all(), f"non-finite PLY coordinates: {rel(path)}")
    return points


def all_footprint_union(path: Path) -> Any:
    payload = json.loads(path.read_text(encoding="utf-8"))
    crs = str(payload.get("crs", {}).get("properties", {}).get("name", ""))
    require("25832" in crs, f"footprint CRS drift: {crs}")
    polygons = [make_valid(shape(feature["geometry"])) for feature in payload["features"]]
    require(bool(polygons), "empty footprint source")
    return make_valid(unary_union(polygons))


def points_in_geometry(points_local: np.ndarray, geometry: Any, offset: np.ndarray) -> np.ndarray:
    minx, miny, maxx, maxy = geometry.bounds
    x = points_local[:, 0] + float(offset[0])
    y = points_local[:, 1] + float(offset[1])
    candidate = (x >= minx) & (x <= maxx) & (y >= miny) & (y <= maxy)
    result = np.zeros(len(points_local), dtype=bool)
    indices = np.flatnonzero(candidate)
    if len(indices):
        result[indices] = contains_xy(geometry, x[indices], y[indices])
    return result


def estimate_ground(
    short: str,
    target: Any,
    all_footprints: Any,
    points_local: np.ndarray,
    offset: np.ndarray,
    spec: dict[str, Any],
) -> dict[str, Any]:
    """Exact B-1 parent formula from e5_c001_s3ap_fm_retri_rescore.py."""
    minimum = float(spec["target_outer_distance_min_m"])
    maximum = float(spec["target_outer_distance_max_m"])
    exclusion = float(spec["all_footprint_exclusion_buffer_m"])
    region = make_valid(target.buffer(maximum).difference(target.buffer(minimum)))
    region = make_valid(region.difference(all_footprints.buffer(exclusion)))
    selected = points_local[points_in_geometry(points_local, region, offset)]
    require(len(selected) > 0, f"no clean exterior observed points for {short}")
    grid = float(spec["grid_m"])
    world_xy = selected[:, :2] + offset[:2]
    cell_xy = np.floor(world_xy / grid).astype(np.int64)
    unique, inverse = np.unique(cell_xy, axis=0, return_inverse=True)
    cell_q10: list[float] = []
    for index in range(len(unique)):
        values = selected[inverse == index, 2]
        if len(values) >= int(spec["min_points_per_cell"]):
            cell_q10.append(float(np.quantile(values, float(spec["cell_z_quantile"]))))
    values = np.asarray(cell_q10, dtype=np.float64)
    require(len(values) > 0, f"no clean exterior ground cells for {short}")
    if len(values) >= 4:
        q1, q3 = np.quantile(values, [0.25, 0.75])
        iqr = float(q3 - q1)
        clipped = values[(values >= q1 - 1.5 * iqr) & (values <= q3 + 1.5 * iqr)]
    else:
        clipped = values
    bin_width = float(spec["mode_bin_m"])
    bin_ids = np.floor(clipped / bin_width).astype(np.int64)
    bins, counts = np.unique(bin_ids, return_counts=True)
    max_count = int(np.max(counts))
    mode_bin = int(np.min(bins[counts == max_count]))
    mode_centre = (mode_bin + 0.5) * bin_width
    selected_cells = clipped[np.abs(clipped - mode_centre) <= float(spec["mode_half_window_m"])]
    method = "clean exterior 1m-cell q10 lower-mode median"
    if len(selected_cells) < 3:
        selected_cells = clipped
        method = "clean exterior 1m-cell q10 Tukey-clipped median fallback"
    ground = float(np.median(selected_cells))
    return {
        "ground_z_local_m": ground,
        "ground_z_mad_m": float(np.median(np.abs(selected_cells - ground))),
        "ground_method": method,
        "ground_region_rule": (
            f"target {minimum:.1f}-{maximum:.1f}m exterior; "
            f"all footprint buffers {exclusion:.1f}m excluded"
        ),
        "ground_observed_point_count": int(len(selected)),
        "ground_cell_count": int(len(values)),
        "ground_mode_cell_count": int(len(selected_cells)),
        "ground_mode_centre_local_m": mode_centre,
        "ground_source": (
            "full-scene parent SfM sparse seed PLY + dense-init seed PLY; "
            "supplied footprints used for exterior/exclusion masks; no LoD2 or ALS elevation"
        ),
    }


def point_npz(short: str, xyz64: np.ndarray, anchor: dict[str, str], ground: dict[str, Any]) -> Path:
    path = POINT_DIR / f"{full_id(short)}_flat_g0500_points.npz"
    xyz = np.ascontiguousarray(xyz64, dtype=np.float32)
    metadata = {
        "schema": "jointbuildgs.primary4.flat_points.v2",
        "building_id": full_id(short),
        "crs": "EPSG:25832",
        "coordinate_frame": "gs_local",
        "grid_m": 0.5,
        "plane_ax_local": 0.0,
        "plane_by_local": 0.0,
        "plane_c_local": float(anchor["anchor_inside_z_median_m"]),
        "height_anchor_source": rel(REPO / config()["source_paths"]["anchor_ladder"]),
        "height_anchor_count": int(anchor["anchor_footprint_inside_point_count"]),
        "height_anchor_mad_m": float(anchor["anchor_inside_z_mad_m"]),
        "ground_z_local_m": ground["ground_z_local_m"],
        "reference_used_for_generation": False,
        "learning_runs_started": 0,
        "new_inference_runs": 0,
    }
    atomic_deterministic_npz(
        path,
        {
            "metadata_json": np.asarray(
                json.dumps(metadata, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            ),
            "xyz": xyz,
        },
    )
    return path


def write_classified_laz(
    path: Path,
    shorts: Sequence[str],
    fill_by_short: dict[str, np.ndarray],
    ground_by_short: dict[str, dict[str, Any]],
    offset: np.ndarray,
) -> None:
    roof = np.concatenate([fill_by_short[short] + offset[None, :] for short in shorts], axis=0)
    ground_parts: list[np.ndarray] = []
    for short in shorts:
        part = fill_by_short[short] + offset[None, :]
        part = part.copy()
        part[:, 2] = float(ground_by_short[short]["ground_z_local_m"]) + float(offset[2])
        ground_parts.append(part)
    ground = np.concatenate(ground_parts, axis=0)
    xyz = np.vstack([roof, ground])
    classes = np.concatenate(
        [
            np.full(len(roof), 6, dtype=np.uint8),
            np.full(len(ground), 2, dtype=np.uint8),
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
    temporary = path.with_name(path.stem + ".tmp.laz")
    cloud.write(temporary)
    os.replace(temporary, path)


def write_roofprints(
    path: Path,
    group: str,
    shorts: Sequence[str],
    fill_by_short: dict[str, np.ndarray],
    offset: np.ndarray,
) -> None:
    features = []
    for short in shorts:
        geometry = p0.occupied_cell_union(fill_by_short[short], offset, 0.5)
        features.append(
            {
                "type": "Feature",
                "properties": {
                    "building_id": full_id(short),
                    "source": "flat_seed_point_occupied_cell_union",
                    "grid_m": 0.5,
                    "point_count": len(fill_by_short[short]),
                },
                "geometry": mapping(geometry),
            }
        )
    payload = {
        "type": "FeatureCollection",
        "name": f"primary4_{group}_flat_g0500_roofprints",
        "crs": {"type": "name", "properties": {"name": "urn:ogc:def:crs:EPSG::25832"}},
        "features": features,
    }
    atomic_text(path, json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n")


def prepare() -> None:
    cfg = config()
    require(PREFLIGHT.is_file(), f"missing preflight: {rel(PREFLIGHT)}")
    anchors = anchor_rows(cfg)
    RUN_DIR.mkdir(parents=True, exist_ok=True)
    INPUT_DIR.mkdir(parents=True, exist_ok=True)
    POINT_DIR.mkdir(parents=True, exist_ok=True)
    offset = np.asarray(
        json.loads(
            (REPO / cfg["source_paths"]["c001_crop_manifest"]).read_text(encoding="utf-8")
        )["world_offset"],
        dtype=np.float64,
    )
    footprints = p0.load_footprints(cfg["targets_in_output_order"])
    footprint_source = REPO / cfg["source_paths"]["footprints"]
    all_footprints = all_footprint_union(footprint_source)
    sparse_path = REPO / cfg["source_paths"]["full_sparse_seed"]
    dense_path = REPO / cfg["source_paths"]["full_dense_seed"]
    observed = np.concatenate([read_xyz_ply(sparse_path), read_xyz_ply(dense_path)], axis=0)
    ground_by_short: dict[str, dict[str, Any]] = {}
    fill_by_short: dict[str, np.ndarray] = {}
    point_records: dict[str, dict[str, Any]] = {}
    for short in cfg["targets_in_output_order"]:
        anchor = anchors[short]
        ground = estimate_ground(
            short,
            footprints[short],
            all_footprints,
            observed,
            offset,
            cfg["flat_input"]["ground_parameters"],
        )
        flat, eligible = p0.fill_footprint(
            footprints[short],
            offset,
            np.asarray([0.0, 0.0, float(anchor["anchor_inside_z_median_m"])], dtype=np.float64),
            0.5,
        )
        require(len(flat) == eligible, f"flat lattice count drift {short}")
        ground_by_short[short] = ground
        fill_by_short[short] = flat
        path = point_npz(short, flat, anchor, ground)
        with np.load(path, allow_pickle=False) as archive:
            xyz_payload = np.asarray(archive["xyz"], dtype=np.float32)
        point_records[short] = {
            "path": rel(path),
            "sha256": sha256_file(path),
            "xyz_payload_sha256": payload_sha256(xyz_payload),
            "point_count": len(flat),
            "z_local_m": anchor["anchor_inside_z_median_m"],
        }
        log(
            f"prepare building={short} flat_points={len(flat)} "
            f"z={anchor['anchor_inside_z_median_m']} ground={ground['ground_z_local_m']:.6f}"
        )
    expected = cfg["reproduction_hard_stop"]
    require(
        len(fill_by_short["4907199"]) == int(expected["expected_flat_point_count"]),
        "199 fill-count reproduction failed",
    )
    b1_ground_rows = [
        row
        for row in read_csv(REPO / "docs/experiments/input-and-alignment/e5_c001_s3ap/tables/e5_c001_s3ap_fm_retri_rescore.csv")
        if row["row_type"] == "building_summary" and row["building_id"] == full_id("4907199")
    ]
    require(len(b1_ground_rows) == 1, "199 B-1 ground row cardinality drift")
    b1_ground = b1_ground_rows[0]
    require(
        abs(ground_by_short["4907199"]["ground_z_local_m"] - float(b1_ground["ground_z_local_m"]))
        <= 5e-7,
        "199 parent-source ground reproduction failed",
    )
    group_inputs: dict[str, dict[str, Any]] = {}
    for group, shorts in GROUPS.items():
        laz_path = INPUT_DIR / f"{group}_flat_g0500.laz"
        roofprint_path = INPUT_DIR / f"{group}_flat_g0500.geojson"
        write_classified_laz(laz_path, shorts, fill_by_short, ground_by_short, offset)
        write_roofprints(roofprint_path, group, shorts, fill_by_short, offset)
        group_inputs[group] = {
            "targets": list(shorts),
            "classified_laz": rel(laz_path),
            "classified_laz_sha256": sha256_file(laz_path),
            "roofprint_geojson": rel(roofprint_path),
            "roofprint_geojson_sha256": sha256_file(roofprint_path),
        }
    prepared = {
        "schema": "jointbuildgs.primary4.prepared.v2",
        "created_utc": now(),
        "task_id": TASK_ID,
        "targets": cfg["targets_in_output_order"],
        "grid_m": 0.5,
        "nominal_density_pt_m2": 4.0,
        "offset": offset.tolist(),
        "input_anchor_lock": {
            short: {
                "anchor_inside_z_median_m": anchors[short]["anchor_inside_z_median_m"],
                "anchor_footprint_inside_point_count": anchors[short]["anchor_footprint_inside_point_count"],
                "anchor_inside_z_mad_m": anchors[short]["anchor_inside_z_mad_m"],
                "source_match": True,
            }
            for short in cfg["targets_in_output_order"]
        },
        "flat_points": point_records,
        "ground": ground_by_short,
        "ground_parent_sources": {
            "sparse": {"path": rel(sparse_path), "sha256": sha256_file(sparse_path)},
            "dense": {"path": rel(dense_path), "sha256": sha256_file(dense_path)},
        },
        "groups": group_inputs,
        "reference_geometry_opened_during_prepare": False,
        "roofer_parameters": ROOFER_PARAMETERS,
        "crs": "EPSG:25832",
        "learning_runs_started": 0,
        "new_inference_runs": 0,
        "image_inputs_used": 0,
        "gpu_used": False,
    }
    atomic_json(PREPARED, prepared)
    version_lines = [
        f"created_utc={now()}",
        f"git_head={subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=REPO, text=True).strip()}",
        f"git_branch={subprocess.check_output(['git', 'branch', '--show-current'], cwd=REPO, text=True).strip()}",
        f"python={platform.python_version()}",
        "tools_image=jointbuildgs-p0-tools:t0",
        f"roofer_image={cfg['roofer']['image']}",
        "val3dity=2.6.0",
        f"roofer_parameters={ROOFER_PARAMETERS}",
        "crs=EPSG:25832",
        "learning_runs_started=0",
        "new_inference_runs=0",
        "image_inputs_used=0",
        "gpu_used=false",
        "",
    ]
    atomic_text(VERSIONS, "\n".join(version_lines))
    log("prepare complete groups=2 buildings=4 reference_opened=false")


def run_val3dity(cityjson: Path, report: Path) -> tuple[int, dict[str, bool]]:
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
        f"+ val3dity {cityjson} --report {report}\n{process.stdout or ''}",
    )
    require(report.is_file(), f"val3dity report missing: {rel(report)}")
    payload = json.loads(report.read_text(encoding="utf-8"))
    valid = {
        str(feature.get("id")): bool(feature.get("validity"))
        for feature in payload.get("features", [])
        if feature.get("id") is not None
    }
    return int(process.returncode), valid


def parse_bool(value: Any) -> bool:
    return str(value).strip().lower() in {"true", "1"}


def cityjson_lod22_presence(path: Path, building_ids: Sequence[str]) -> dict[str, bool]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    objects = payload.get("CityObjects") or {}
    result: dict[str, bool] = {}
    for building_id in building_ids:
        parent = objects.get(building_id) or {}
        object_ids = [building_id, *(parent.get("children") or [])]
        result[building_id] = any(
            str(geometry.get("lod")) == "2.2"
            for object_id in object_ids
            for geometry in (objects.get(object_id) or {}).get("geometry", [])
        )
    return result


def roof_xy_coverage(refs: Sequence[Any], predictions: Sequence[Any]) -> dict[str, float | None]:
    ref_polygons = [
        polygon
        for surface in refs
        for polygon in metrics.flatten_polygons(surface.polygon)
    ]
    model_polygons = [
        polygon
        for surface in predictions
        for polygon in metrics.flatten_polygons(surface.polygon)
    ]
    ref_union = unary_union(ref_polygons) if ref_polygons else GeometryCollection()
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
    return {
        "roof_completeness": min(1.0, max(0.0, overlap_area / reference_area)),
        "model_roof_xy_area_m2": model_area,
        "reference_roof_xy_area_m2": reference_area,
        "roof_overlap_xy_area_m2": overlap_area,
    }


def signed_reference_distance(predictions: Sequence[Any], refs: Sequence[Any]) -> dict[str, Any]:
    diffs: list[np.ndarray] = []
    for prediction in predictions:
        points = metrics.sample_polygon_points(
            prediction.polygon,
            metrics.SAMPLE_SPACING_M,
            limit=1200,
        )
        if not len(points):
            continue
        predicted_z = prediction.z_at(points[:, 0], points[:, 1])
        reference_z = np.full(len(points), np.nan, dtype=np.float64)
        for index, (x, y) in enumerate(points):
            point = Point(float(x), float(y))
            candidates = [
                reference
                for reference in refs
                if any(polygon.covers(point) for polygon in metrics.flatten_polygons(reference.polygon))
            ]
            if not candidates:
                candidates = sorted(
                    refs,
                    key=lambda reference: min(
                        polygon.distance(point)
                        for polygon in metrics.flatten_polygons(reference.polygon)
                    ),
                )[:1]
            if candidates:
                z_values = np.asarray(
                    [
                        reference.z_at(np.asarray([x]), np.asarray([y]))[0]
                        for reference in candidates
                    ],
                    dtype=np.float64,
                )
                reference_z[index] = z_values[int(np.argmin(np.abs(predicted_z[index] - z_values)))]
        finite = np.isfinite(reference_z)
        if np.any(finite):
            diffs.append(predicted_z[finite] - reference_z[finite])
    if not diffs:
        return {
            "signed_delta_z_median_m": None,
            "signed_delta_z_mad_m": None,
            "signed_delta_z_q05_m": None,
            "signed_delta_z_q95_m": None,
            "abs_delta_z_median_m": None,
            "rms_m": None,
            "hausdorff_m": None,
            "samples": 0,
        }
    values = np.concatenate(diffs)
    median = float(np.median(values))
    return {
        "signed_delta_z_median_m": median,
        "signed_delta_z_mad_m": float(np.median(np.abs(values - median))),
        "signed_delta_z_q05_m": float(np.quantile(values, 0.05)),
        "signed_delta_z_q95_m": float(np.quantile(values, 0.95)),
        "abs_delta_z_median_m": float(np.median(np.abs(values))),
        "rms_m": float(np.sqrt(np.mean(values * values))),
        "hausdorff_m": float(np.max(np.abs(values))),
        "samples": int(len(values)),
    }


def combine_group(group: str, shorts: Sequence[str]) -> tuple[Path, list[dict[str, str]], dict[str, bool], Path, int]:
    cfg = config()
    source = REPO / cfg["source_paths"]["standard_status_script"]
    jsonl_files = sorted((ROOFER_DIR / group).glob("*.city.jsonl"))
    require(bool(jsonl_files), f"missing Roofer JSONSeq group={group}")
    w2 = load_module(f"primary4_w2_{group}", source)
    cityjson = CITYJSON_DIR / f"{group}_flat_g0500.city.json"
    cityjson.parent.mkdir(parents=True, exist_ok=True)
    w2.combine_cityjsonseq(jsonl_files, cityjson)
    report = VAL_DIR / f"{group}_flat_g0500.json"
    exit_code, valid = run_val3dity(cityjson, report)
    val_payload = json.loads(report.read_text(encoding="utf-8"))
    val_by_id = {
        str(feature.get("id")): feature
        for feature in val_payload.get("features", [])
        if feature.get("id") is not None
    }
    roofer_by_id = w2.parse_roofer_features(jsonl_files)
    statuses = w2.classify_buildings(
        "FLAT",
        [full_id(short) for short in shorts],
        roofer_by_id,
        val_by_id,
    )
    return cityjson, statuses, valid, report, exit_code


def score_group(group: str, roofer_wall_seconds: float) -> None:
    started = time.monotonic()
    cfg = config()
    require(group in GROUPS, f"unknown group {group}")
    require(PREPARED.is_file(), f"missing prepared input: {rel(PREPARED)}")
    prepared = json.loads(PREPARED.read_text(encoding="utf-8"))
    shorts = GROUPS[group]
    anchors = anchor_rows(cfg)
    geoid = float(
        json.loads((REPO / cfg["source_paths"]["projection_datum"]).read_text(encoding="utf-8"))[
            "orthometric_geoid_m"
        ]
    )
    building_ids = [full_id(short) for short in shorts]
    references = metrics.parse_lod2_roofs(
        REPO / cfg["source_paths"]["lod2_dir"],
        set(building_ids),
    )
    cityjson, statuses, valid, report, val_exit = combine_group(group, shorts)
    status_by_id = {row["building_id"]: row for row in statuses}
    parsed = metrics.parse_cityjson_roofs(cityjson, set(building_ids))
    geometry_lod22 = cityjson_lod22_presence(cityjson, building_ids)
    rows: list[dict[str, Any]] = []
    for short in shorts:
        bid = full_id(short)
        prediction = metrics.shift_surface_z(parsed.get(bid, []), -geoid)
        reference = references[bid]
        comparison = metrics.compare_building(reference, prediction)
        signed = signed_reference_distance(prediction, reference)
        if comparison["ref_rms_m"] is not None:
            require(
                abs(float(comparison["ref_rms_m"]) - float(signed["rms_m"])) <= 1e-12,
                f"RMS path mismatch {short}",
            )
            require(
                abs(float(comparison["ref_hausdorff_m"]) - float(signed["hausdorff_m"])) <= 1e-12,
                f"Hausdorff path mismatch {short}",
            )
        coverage = roof_xy_coverage(reference, prediction)
        status = status_by_id[bid]
        mode = str(status.get("rf_extrusion_mode", ""))
        fallback = mode == "lod11_fallback"
        has_lod22 = parse_bool(status.get("has_lod22")) and not fallback
        require(
            has_lod22 == bool(geometry_lod22[bid]) if has_lod22 else True,
            f"LoD2 status/geometry mismatch {short}",
        )
        model_face_count = 1 if fallback and prediction else len(prediction)
        ref_face_count = len(reference)
        signed_median = signed["signed_delta_z_median_m"]
        gauge_true = bool(
            has_lod22
            and signed_median is not None
            and abs(float(signed_median))
            <= float(cfg["success_gauge"]["max_abs_signed_delta_z_median_m"])
        )
        point = prepared["flat_points"][short]
        ground = prepared["ground"][short]
        group_input = prepared["groups"][group]
        row = {
            "task_id": TASK_ID,
            "row_role": cfg["anchor_lock"][short]["row_role"],
            "building_id": bid,
            "anchor_source": cfg["source_paths"]["anchor_ladder"],
            "anchor_inside_z_median_m": anchors[short]["anchor_inside_z_median_m"],
            "anchor_footprint_inside_point_count": int(anchors[short]["anchor_footprint_inside_point_count"]),
            "anchor_inside_z_mad_m": anchors[short]["anchor_inside_z_mad_m"],
            "ref_roof_type": anchors[short]["ref_roof_type"],
            "input_note": cfg["anchor_lock"][short].get("input_note", ""),
            "grid_m": 0.5,
            "nominal_density_pt_m2": 4.0,
            "flat_point_count": int(point["point_count"]),
            "flat_points_npz": point["path"],
            "flat_points_npz_sha256": point["sha256"],
            "flat_xyz_payload_sha256": point["xyz_payload_sha256"],
            "ground_z_local_m": ground["ground_z_local_m"],
            "ground_z_mad_m": ground["ground_z_mad_m"],
            "ground_method": ground["ground_method"],
            "ground_observed_point_count": ground["ground_observed_point_count"],
            "ground_cell_count": ground["ground_cell_count"],
            "ground_mode_cell_count": ground["ground_mode_cell_count"],
            "ground_source": ground["ground_source"],
            "classified_laz": group_input["classified_laz"],
            "classified_laz_sha256": group_input["classified_laz_sha256"],
            "roofprint_geojson": group_input["roofprint_geojson"],
            "roofprint_geojson_sha256": group_input["roofprint_geojson_sha256"],
            "roofer_cityjson": rel(cityjson),
            "roofer_cityjson_sha256": sha256_file(cityjson),
            "roofer_status": status.get("status", ""),
            "roofer_reason": status.get("reason", ""),
            "rf_extrusion_mode": mode,
            "assembly_success": has_lod22,
            "has_lod22": has_lod22,
            "has_lod22_geometry": geometry_lod22[bid],
            "lod1_fallback": fallback,
            "val3dity_valid": valid.get(bid, False),
            "val3dity_report": rel(report),
            "val3dity_exit_code": val_exit,
            "roof_face_count_model": model_face_count,
            "roof_face_count_ref": ref_face_count,
            "face_count_ratio": model_face_count / ref_face_count if ref_face_count else None,
            "signed_delta_z_median_m": signed_median,
            "signed_delta_z_mad_m": signed["signed_delta_z_mad_m"],
            "signed_delta_z_q05_m": signed["signed_delta_z_q05_m"],
            "signed_delta_z_q95_m": signed["signed_delta_z_q95_m"],
            "abs_delta_z_median_m": signed["abs_delta_z_median_m"],
            "roof_rms_m": comparison["ref_rms_m"],
            "roof_hausdorff_m": comparison["ref_hausdorff_m"],
            "roof_distance_samples": comparison["ref_distance_samples"],
            **coverage,
            "success_gauge_id": "b",
            "success_gauge_formula": cfg["success_gauge"]["formula"],
            "success_gauge_max_abs_error_m": cfg["success_gauge"]["max_abs_signed_delta_z_median_m"],
            "success_gauge_true": gauge_true,
            "roofer_parameters": ROOFER_PARAMETERS,
            "crs": "EPSG:25832",
            "reference_role": "LoD2 opened after input freeze for scoring and ref_roof_type reporting only",
            "reference_used_for_input_generation": False,
            "learning_runs_started": 0,
            "new_inference_runs": 0,
            "image_inputs_used": 0,
            "gpu_used": False,
            "roofer_wall_seconds": float(roofer_wall_seconds),
            "score_wall_seconds": 0.0,
            "elapsed_seconds": 0.0,
            "status": "measured",
        }
        rows.append(row)
    score_seconds = time.monotonic() - started
    for row in rows:
        row["score_wall_seconds"] = score_seconds
        row["elapsed_seconds"] = float(roofer_wall_seconds) + score_seconds
    output = RUN_DIR / f"{group}_measurements.json"
    atomic_json(
        output,
        {
            "schema": "jointbuildgs.primary4.group_measurements.v2",
            "created_utc": now(),
            "group": group,
            "rows": rows,
            "learning_runs_started": 0,
            "new_inference_runs": 0,
            "image_inputs_used": 0,
            "gpu_used": False,
        },
    )
    if group == "reproduction":
        row = rows[0]
        expected = cfg["reproduction_hard_stop"]
        tolerance = float(expected["numeric_tolerance_m"])
        checks = {
            "flat_point_count": row["flat_point_count"] == int(expected["expected_flat_point_count"]),
            "signed_delta_z_median_m": (
                row["signed_delta_z_median_m"] is not None
                and abs(
                    float(row["signed_delta_z_median_m"])
                    - float(expected["expected_b1_assembly_signed_delta_z_median_m"])
                )
                <= tolerance
            ),
            "roof_rms_m": (
                row["roof_rms_m"] is not None
                and abs(float(row["roof_rms_m"]) - float(expected["expected_b1_roof_rms_m"]))
                <= tolerance
            ),
            "roof_hausdorff_m": (
                row["roof_hausdorff_m"] is not None
                and abs(
                    float(row["roof_hausdorff_m"])
                    - float(expected["expected_b1_roof_hausdorff_m"])
                )
                <= tolerance
            ),
            "rf_extrusion_mode": row["rf_extrusion_mode"] == expected["expected_b1_rf_extrusion_mode"],
            "has_lod22": row["has_lod22"] is bool(expected["expected_b1_has_lod22"]),
            "lod1_fallback": row["lod1_fallback"] is bool(expected["expected_b1_lod1_fallback"]),
            "val3dity_valid": row["val3dity_valid"] is bool(expected["expected_b1_val3dity_valid"]),
        }
        check_payload = {
            "schema": "jointbuildgs.primary4.reproduction_check.v2",
            "created_utc": now(),
            "building_id": full_id("4907199"),
            "expected": expected,
            "observed": {
                key: row[key]
                for key in (
                    "flat_point_count",
                    "signed_delta_z_median_m",
                    "roof_rms_m",
                    "roof_hausdorff_m",
                    "rf_extrusion_mode",
                    "has_lod22",
                    "lod1_fallback",
                    "val3dity_valid",
                )
            },
            "checks": checks,
            "passed": all(checks.values()),
        }
        atomic_json(RUN_DIR / "reproduction_check.json", check_payload)
        require(all(checks.values()), f"199 reproduction hard stop: {checks}")
    log(
        f"score group={group} rows={len(rows)} lod22={sum(bool(row['has_lod22']) for row in rows)} "
        f"gauge_true={sum(bool(row['success_gauge_true']) for row in rows)}"
    )


def summary_markdown(rows: Sequence[dict[str, Any]], reproduction: dict[str, Any]) -> str:
    def number(value: Any, digits: int = 3) -> str:
        if value is None or value == "":
            return "NA"
        return f"{float(value):.{digits}f}"

    lines = [
        "# 주 명단 4동 수평면 합성 점군 조립 측정",
        "",
        "- 범위: 4907199 재현 1동 + 4908049·104586480·4908048 신규 3동.",
        "- 입력: 0.5 m 격자, 상수 높이, class 6 지붕 + B-1 동일 지면 공식 class 2.",
        "- 조립: 잠금 Roofer 표준 설정. 참조 LoD2는 입력 고정 후 채점에만 사용.",
        "- 학습 0, 신규 추론 0, 이미지 입력 0, GPU 0.",
        "",
        "## 측정표",
        "",
        "| 건물 | 행 | rf_extrusion_mode | has_lod22 | 부호 중앙오차 m | 지붕 RMS m | 면수비 | 완전율 | val3dity | 눈금 b |",
        "|---|---|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in rows:
        lines.append(
            "| {bid} | {role} | `{mode}` | {lod2} | {signed} | {rms} | {ratio} | {complete} | {valid} | {gauge} |".format(
                bid=row["building_id"].removeprefix("DEBY_LOD2_"),
                role=row["row_role"],
                mode=row["rf_extrusion_mode"] or "NA",
                lod2=str(bool(row["has_lod22"])).lower(),
                signed=number(row["signed_delta_z_median_m"]),
                rms=number(row["roof_rms_m"]),
                ratio=number(row["face_count_ratio"]),
                complete=number(row["roof_completeness"], 4),
                valid=str(bool(row["val3dity_valid"])).lower(),
                gauge=str(bool(row["success_gauge_true"])).lower(),
            )
        )
    lines.extend(
        [
            "",
            "눈금 b: `has_lod22 == true AND abs(signed_delta_z_median_m) <= 1.0 m`.",
            "",
            "## 4907199 재현 행",
            "",
            f"- B-1 조립 중앙오차 기대값: {number(reproduction['expected']['expected_b1_assembly_signed_delta_z_median_m'], 12)} m.",
            f"- 이번 중앙오차: {number(reproduction['observed']['signed_delta_z_median_m'], 12)} m.",
            f"- 전 재현 검사 통과: `{str(bool(reproduction['passed'])).lower()}`.",
            "",
            "## 입력·범위 기록",
            "",
            "- 네 z 값은 `boundary_map_v4_1_ladder.csv`의 잠금 문자열과 일치한다.",
            "- 4908048은 참조 분류 `multiple horizontal`; 입력은 잠금 지시에 따라 MAD 0.039240 m의 단일 상수 높이로 작성했다.",
            "- 지면 공식은 B-1 C001 clip의 원천인 전역 sparse/dense seed PLY에 같은 외곽·격자·q10·하위 모드 파라미터를 적용했다.",
            "- 이 문서는 4/4 문장 또는 K2 확정·후퇴를 기록하지 않는다.",
            "",
        ]
    )
    return "\n".join(lines)


def finalize() -> None:
    cfg = config()
    require(PREPARED.is_file(), "prepared input missing")
    group_payloads = {
        group: json.loads((RUN_DIR / f"{group}_measurements.json").read_text(encoding="utf-8"))
        for group in GROUPS
    }
    by_short = {
        row["building_id"].removeprefix("DEBY_LOD2_"): row
        for payload in group_payloads.values()
        for row in payload["rows"]
    }
    require(set(by_short) == set(cfg["targets_in_output_order"]), "final row-set mismatch")
    rows = [by_short[short] for short in cfg["targets_in_output_order"]]
    atomic_csv(MEASUREMENTS, rows, MEASUREMENT_FIELDS)
    reproduction = json.loads((RUN_DIR / "reproduction_check.json").read_text(encoding="utf-8"))
    require(reproduction["passed"] is True, "reproduction check not passed")
    atomic_text(SUMMARY, summary_markdown(rows, reproduction))
    log(
        f"finalize outputs rows=4 has_lod22={sum(bool(row['has_lod22']) for row in rows)} "
        f"gauge_true={sum(bool(row['success_gauge_true']) for row in rows)} learning=0 inference=0"
    )
    source_paths = {
        Path(__file__),
        QA_SCRIPT,
        CONFIG_PATH,
        *[
            REPO / path
            for key, path in cfg["source_paths"].items()
            if key != "lod2_dir"
        ],
        *sorted((REPO / cfg["source_paths"]["lod2_dir"]).glob("*.gml")),
        REPO / "phases/p2-gsjso/runs/20260716_genclose_flat_density/cityjson/flat_density_g0500.city.json",
    }
    output_paths = {
        MEASUREMENTS,
        SUMMARY,
        *[
            path
            for path in RUN_DIR.rglob("*")
            if path.is_file()
        ],
    }
    prepared = json.loads(PREPARED.read_text(encoding="utf-8"))
    manifest = {
        "schema": "jointbuildgs.primary4_assembly_validation.v2",
        "created_utc": now(),
        "task_id": TASK_ID,
        "git_head_at_measurement": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=REPO, text=True
        ).strip(),
        "branch": subprocess.check_output(
            ["git", "branch", "--show-current"], cwd=REPO, text=True
        ).strip(),
        "targets": cfg["targets_in_output_order"],
        "new_targets": cfg["new_targets"],
        "reproduction_target": cfg["reproduction_target"],
        "input_z_lock": prepared["input_anchor_lock"],
        "input_z_lock_all_match": all(
            value["source_match"] for value in prepared["input_anchor_lock"].values()
        ),
        "flat_input": cfg["flat_input"],
        "grid_m": 0.5,
        "nominal_density_pt_m2": 4.0,
        "roofer": cfg["roofer"],
        "standard_scoring": {
            "status": cfg["source_paths"]["standard_status_script"],
            "roof_distance": cfg["source_paths"]["standard_metric_script"],
            "roof_completeness": cfg["source_paths"]["standard_completeness_script"],
            "reference_role": "LoD2 scoring and ref_roof_type classification only",
        },
        "success_gauge": cfg["success_gauge"],
        "reproduction_check": reproduction,
        "result_counts": {
            "rows": len(rows),
            "has_lod22_true": sum(bool(row["has_lod22"]) for row in rows),
            "lod1_fallback_true": sum(bool(row["lod1_fallback"]) for row in rows),
            "val3dity_valid_true": sum(bool(row["val3dity_valid"]) for row in rows),
            "success_gauge_true": sum(bool(row["success_gauge_true"]) for row in rows),
        },
        "multiple_horizontal_record": {
            "building_id": full_id("4908048"),
            "ref_roof_type": "multiple horizontal",
            "anchor_inside_z_mad_m": cfg["anchor_lock"]["4908048"]["anchor_inside_z_mad_m"],
            "input_geometry": "single constant-height horizontal plane per locked order",
        },
        "learning_runs_started": 0,
        "new_inference_runs": 0,
        "image_inputs_used": 0,
        "gpu_used": False,
        "interpretation_or_verdict": None,
        "orchestration_logs_excluded_from_payload_hash_scope": [
            "phases/p2-gsjso/runs/20260721_primary4_assembly_validation_driver"
        ],
        "source_sha256": {
            rel(path): sha256_file(path)
            for path in sorted(source_paths)
            if path.is_file()
        },
        "output_sha256": {
            rel(path): sha256_file(path)
            for path in sorted(output_paths)
            if path.is_file() and path != MANIFEST
        },
    }
    atomic_json(MANIFEST, manifest)


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("preflight")
    sub.add_parser("prepare")
    score = sub.add_parser("score-group")
    score.add_argument("--group", required=True, choices=tuple(GROUPS))
    score.add_argument("--roofer-wall-seconds", required=True, type=float)
    sub.add_parser("finalize")
    args = parser.parse_args()
    if args.command == "preflight":
        preflight()
    elif args.command == "prepare":
        prepare()
    elif args.command == "score-group":
        score_group(args.group, args.roofer_wall_seconds)
    else:
        finalize()


if __name__ == "__main__":
    main()
