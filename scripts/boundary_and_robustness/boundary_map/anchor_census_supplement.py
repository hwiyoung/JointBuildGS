#!/usr/bin/env python3
"""Learning-zero same-minute-block re-pooling for nine anchor-census rows.

This script does not run MASt3R and does not start an optimizer.  It reads the
locked post-cheirality NPZ caches produced by R1-prime / the 2026-07-20 anchor
census, reapplies the unchanged 2 source-pixel reprojection ceiling and
footprint containment, and changes only the pair-pooling eligibility rule:
same acquisition-minute-block pairs are admitted when the fixed-camera-centre
baseline is greater than 0.06 m.

The fixed nine-building scope, the 104586480 cross-block reproduction check,
the 24-pair same-block reliability comparison, the 178-row ladder invariance
check, and every SHA-256 lineage check fail closed.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import subprocess
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import numpy as np
from shapely import contains_xy, make_valid
from shapely.geometry import MultiPolygon, Polygon, box, shape
from shapely.ops import unary_union


REPO = Path(__file__).resolve().parents[3]
RUN_ID = "20260720_anchor_census_supplement"
RUN_DIR = REPO / "phases/p2-gsjso/runs" / RUN_ID

CENSUS_RUN = REPO / "phases/p2-gsjso/runs/boundary_and_robustness/20260720_anchor_census"
R1P_RUN = REPO / "phases/p2-gsjso/runs/boundary_and_robustness/20260719_boundary_map_v3"
CENSUS_PAIRS = CENSUS_RUN / "anchor_census_pairs.csv"
CENSUS_MEASUREMENTS = CENSUS_RUN / "anchor_census_measurements.csv"
CENSUS_MANIFEST = CENSUS_RUN / "anchor_census_manifest.json"
CENSUS_INFERENCE_MANIFEST = (
    CENSUS_RUN / "anchor_census_inference_manifest.json"
)
R1P_PAIRS = R1P_RUN / "fm_dense_pairs.csv"
R1P_MEASUREMENTS = R1P_RUN / "fm_dense_measurements.csv"
R1P_MANIFEST = R1P_RUN / "fm_dense_manifest.json"

OLD_LADDER = REPO / "docs/archive/boundary_map/v4/tables/boundary_map_v4_ladder.csv"
OLD_PUBLIC_MANIFEST = REPO / "docs/experiments/input-and-alignment/boundary_map/manifests/boundary_map_v4_manifest.json"
OLD_FIGURE = REPO / "docs/figs/boundary_map/boundary_map_v4_map.png"
ENV_MANIFEST = REPO / "docs/experiments/input-and-alignment/e5_c001_s3ap/manifests/e5_c001_s3ap_fm_env_manifest.json"
FOOTPRINTS = REPO / "results/tum_transfer/analysis/footprints_aoi.geojson"
TRAIN_MANIFEST = (
    REPO
    / "results/tum_transfer/e5_pilot/C001/C001_train_prep_manifest.json"
)

RUN_PAIRS = RUN_DIR / "anchor_census_supplement_pairs.csv"
RUN_MEASUREMENTS = RUN_DIR / "anchor_census_supplement_measurements.csv"
RUN_RELIABILITY = (
    RUN_DIR / "anchor_census_supplement_same_block_reliability_pairs.csv"
)
RUN_MEASURE_MANIFEST = (
    RUN_DIR / "anchor_census_supplement_measure_manifest.json"
)

DOC_PAIRS = REPO / "docs/experiments/input-and-alignment/boundary_map/tables/anchor_census_supplement_pairs.csv"
DOC_MEASUREMENTS = (
    REPO / "docs/experiments/input-and-alignment/boundary_map/tables/anchor_census_supplement_measurements.csv"
)
DOC_RELIABILITY = (
    REPO / "docs/experiments/input-and-alignment/boundary_map/tables/anchor_census_supplement_same_block_reliability_pairs.csv"
)
NEW_LADDER = REPO / "docs/experiments/input-and-alignment/boundary_map/tables/boundary_map_v4_1_ladder.csv"
PUBLIC_MANIFEST = REPO / "docs/experiments/input-and-alignment/boundary_map/manifests/anchor_census_supplement_manifest.json"
SUMMARY = (
    REPO
    / "docs/experiments/input-and-alignment/boundary_map/reports/W_anchor_census_supplement_boundary_map_v4_1_summary_20260720.md"
)

TARGET_IDS = (
    "DEBY_LOD2_42364609",
    "DEBY_LOD2_4907031",
    "DEBY_LOD2_4907510",
    "DEBY_LOD2_4908051",
    "DEBY_LOD2_4908052",
    "DEBY_LOD2_4908054",
    "DEBY_LOD2_4908166",
    "DEBY_LOD2_4908167",
    "DEBY_LOD2_4908169",
)
CENSUS_TARGET_IDS = TARGET_IDS[:8]
R1P_TARGET_ID = TARGET_IDS[8]
REPRODUCTION_ID = "DEBY_LOD2_104586480"

ENV_MANIFEST_SHA256 = (
    "7246a77569a7af1b931ad60eda7012e6e3e8f4ff81b5e10f2e3c1a2efea80d68"
)
MODEL_ID = "naver/MASt3R_ViTLarge_BaseDecoder_512_catmlpdpt_metric"
MODEL_REVISION = "06e7259f34c3060f322df5cb0c7b9094f57e41fc"
MODEL_SHA256 = (
    "0a615eb05fa9db654050aa655945ee5696e7c6c1b7f93f1ee8c37249010f6feb"
)
DOCKER_IMAGE_ID = (
    "sha256:89d64b4c7112cc55db0d42d562e2a0208858658c0c67ab1bd48424175c50f501"
)
ALLOWLIST = "supplement_FM_dense_dial_2px_same_block"
REPROJECTION_THRESHOLD_PX = 2.0
BASELINE_THRESHOLD_M = 0.06
COVERAGE_GRID_M = 0.5
CRS = "EPSG:25832"

PAIR_INDEPENDENCE = "low_same_block"
REPRODUCTION_INDEPENDENCE = "original_cross_block_rule"
NO_NEW_INFERENCE = "none; locked raw-cache re-pooling only"
POOLING_RULE = (
    "concatenate 2px DLT survivors from same-acquisition-minute-block pairs "
    "with fixed-COLMAP camera-centre baseline >0.06m"
)
ORIGINAL_POOLING_RULE = (
    "concatenate 2px DLT survivors only from "
    "cross-acquisition-minute-block pairs with fixed-COLMAP "
    "camera-centre baseline >0.06m"
)
FOOTPRINT_ROLE = (
    "post-DLT footprint-XY containment and EPSG:25832 0.5m "
    "intersect-cell coverage denominator only"
)
LOD2_ROLE = "projection and classification only"

CELL_1 = "cell_1_assembled"
CELL_2 = "cell_2_anchored"
CELL_3 = "cell_3_outline_only"
CELL_4 = "cell_4_beyond_image"
CELLS = (CELL_1, CELL_2, CELL_3, CELL_4)

REPRODUCTION_EXPECTED = {
    "footprint_inside_point_count": 3364,
    "inside_z_median_m": -43.161802,
    "inside_z_mad_m": 0.071273,
}
RELIABILITY_EXPECTED = {
    "pair_count": 24,
    "median_abs_delta_z_m": 0.2714605,
    "p90_abs_delta_z_m": 5.092229,
    "maximum_abs_delta_z_m": 7.27513,
    "within_0_5m_count": 13,
    "within_0_5m_ratio": 13 / 24,
    "p90_method": "numpy.quantile(method=lower)",
}

NEW_LADDER_FIELDS = (
    "same_block_only",
    "pair_independence",
    "low_independence",
    "supplement_measurement_source",
    "supplement_measurement_lineage",
    "supplement_cache_reuse_runs",
    "supplement_new_mast3r_inference_runs",
    "supplement_new_inference_allowlist",
    "preregister_primary_list_eligible",
)

ALLOWED_TARGET_OLD_FIELD_CHANGES = {
    "anchor_status",
    "anchor_measurement_source",
    "anchor_measurement_lineage",
    "anchor_selected_dlt_point_count",
    "anchor_footprint_inside_point_count",
    "anchor_inside_z_median_m",
    "anchor_inside_z_mad_m",
    "anchor_coverage_ratio",
    "anchor_selected_pair_count",
    "anchor_completed_pair_count",
    "anchor_eligible_pair_count",
    "anchor_zero_observed",
    "anchor_undecided_sticker",
    "cell_label",
    "cell_assignment_basis",
    "new_inference_type",
}


PAIR_FIELDS = (
    "building_id",
    "target_order",
    "pair_rank",
    "view_a",
    "view_b",
    "source_scope",
    "source_pair_table",
    "source_pair_table_sha256",
    "source_pair_row_sha256",
    "source_cache_path",
    "source_cache_sha256",
    "cache_metadata_schema",
    "cache_metadata_created_utc",
    "crop_source",
    "camera_branch",
    "world_frame",
    "acquisition_block_a",
    "acquisition_block_b",
    "pair_relation",
    "same_block_only",
    "pair_independence",
    "known_colmap_baseline_m",
    "baseline_rule",
    "baseline_rule_passed",
    "reprojection_threshold_px",
    "eligible_supplement_pair",
    "status",
    "failure_reason",
    "reciprocal_match_count",
    "border_match_count",
    "dlt_finite_count",
    "positive_depth_count",
    "reprojection_2px_count",
    "footprint_inside_count",
    "inside_z_median_m",
    "inside_z_mad_m",
    "source_pair_metrics_reproduced",
    "source_inference_elapsed_seconds",
    "repool_elapsed_seconds",
    "cache_reuse_runs",
    "new_mast3r_inference_runs",
    "inference_execution",
    "origin_new_inference_type",
    "pair_fingerprint",
    "input_fingerprint",
    "model_id",
    "model_revision",
    "model_sha256",
    "docker_image_id",
    "reference_lod2_role",
    "crs",
    "learning_runs_started",
    "new_inference_type",
    "new_inference_allowlist",
)

MEASUREMENT_FIELDS = (
    "record_role",
    "building_id",
    "target_order",
    "source_scope",
    "source_pair_table",
    "source_address_rule",
    "status",
    "failure_reason",
    "measurement_complete",
    "same_block_only",
    "pair_independence",
    "low_independence",
    "preregister_primary_list_eligible",
    "selected_dlt_point_count",
    "footprint_inside_point_count",
    "inside_z_median_m",
    "inside_z_mad_m",
    "inside_z_median_local_m",
    "inside_z_mad_local_m",
    "coverage_grid_m",
    "coverage_eligible_cell_count",
    "coverage_occupied_cell_count",
    "coverage_ratio",
    "selected_pair_count",
    "completed_pair_count",
    "eligible_pair_count",
    "nonzero_inside_pair_count",
    "degenerate_pair_count",
    "failed_pair_count",
    "pair_status_summary",
    "cache_reuse_runs",
    "new_mast3r_inference_runs",
    "inference_execution",
    "elapsed_seconds",
    "anchor_status_before",
    "anchor_status_after",
    "anchor_undecided_sticker_before",
    "anchor_undecided_sticker_after",
    "cell_before",
    "cell_after",
    "ref_roof_type",
    "small_lt50",
    "reproduction_expected_inside_count",
    "reproduction_expected_inside_z_median_m",
    "reproduction_expected_inside_z_mad_m",
    "reproduction_check_passed",
    "model_id",
    "model_revision",
    "model_sha256",
    "docker_image_id",
    "environment_manifest",
    "environment_manifest_sha256",
    "pooling_rule",
    "reprojection_threshold_px",
    "baseline_threshold_m",
    "footprint_role",
    "reference_lod2_role",
    "crs",
    "learning_runs_started",
    "new_inference_type",
    "new_inference_allowlist",
)

RELIABILITY_FIELDS = (
    "building_id",
    "pair_rank",
    "view_a",
    "view_b",
    "pair_relation",
    "pair_independence",
    "footprint_inside_count",
    "same_block_pair_inside_z_median_m",
    "adopted_cross_block_inside_z_median_m",
    "abs_delta_z_m",
    "within_0_5m",
    "source_pair_table",
    "source_measurement_table",
    "source_cache_path",
    "source_cache_sha256",
    "source_pair_metrics_reproduced",
    "read_only_derivation",
    "learning_runs_started",
)


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def rel(path: Path | str) -> str:
    candidate = Path(path)
    try:
        return str(candidate.resolve().relative_to(REPO.resolve()))
    except ValueError:
        return str(candidate.resolve())


def full_id(value: Any) -> str:
    text = str(value).strip()
    if not text:
        raise RuntimeError("empty building_id")
    if text.startswith("DEBY_LOD2_"):
        return text
    return f"DEBY_LOD2_{text}"


def sha256_file(path: Path, block_size: int = 1 << 20) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(block_size), b""):
            digest.update(block)
    return digest.hexdigest()


def sha256_json(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def set_sha256(values: Iterable[str]) -> str:
    return sha256_json(sorted(set(values)))


def git_value(*args: str) -> str:
    try:
        return subprocess.check_output(
            ["git", *args],
            cwd=REPO,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return ""


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def read_csv_fields(path: Path) -> list[str]:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.reader(handle)
        return next(reader)


def as_bool(value: Any) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes"}


def as_int(value: Any) -> int | None:
    text = str(value).strip()
    if not text:
        return None
    return int(float(text))


def as_float(value: Any) -> float | None:
    text = str(value).strip()
    if not text:
        return None
    result = float(text)
    return result if math.isfinite(result) else None


def fmt(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (bool, np.bool_)):
        return "true" if bool(value) else "false"
    if isinstance(value, (float, np.floating)):
        result = float(value)
        return "" if not math.isfinite(result) else f"{result:.6f}"
    return str(value)


def atomic_csv(
    path: Path,
    rows: Sequence[Mapping[str, Any]],
    fields: Sequence[str],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
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
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def atomic_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def atomic_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        handle.write(value)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def finite_stats(values: np.ndarray) -> tuple[float | None, float | None]:
    finite = np.asarray(values, dtype=np.float64)
    finite = finite[np.isfinite(finite)]
    if not len(finite):
        return None, None
    median = float(np.median(finite))
    mad = float(np.median(np.abs(finite - median)))
    return median, mad


def acquisition_block(stem: str) -> str:
    pieces = Path(stem).stem.split("_")
    if len(pieces) < 2 or len(pieces[1]) < 12:
        raise RuntimeError(f"cannot derive acquisition minute block: {stem}")
    return pieces[1][:12]


def output_hashes(paths: Iterable[Path]) -> dict[str, str]:
    return {
        rel(path): sha256_file(path)
        for path in paths
        if path.is_file()
    }


def verify_hash_map(values: Mapping[str, Any], label: str) -> None:
    mismatches: list[str] = []
    for source, expected in values.items():
        path = REPO / source
        if not path.is_file():
            mismatches.append(f"{source}:missing")
        elif sha256_file(path) != expected:
            mismatches.append(f"{source}:sha256")
    if mismatches:
        raise RuntimeError(f"{label} hash mismatch: {mismatches}")


def required_sources() -> tuple[Path, ...]:
    return (
        CENSUS_PAIRS,
        CENSUS_MEASUREMENTS,
        CENSUS_MANIFEST,
        CENSUS_INFERENCE_MANIFEST,
        R1P_PAIRS,
        R1P_MEASUREMENTS,
        R1P_MANIFEST,
        OLD_LADDER,
        OLD_PUBLIC_MANIFEST,
        OLD_FIGURE,
        ENV_MANIFEST,
        FOOTPRINTS,
        TRAIN_MANIFEST,
        Path(__file__).resolve(),
    )


def environment_lock() -> dict[str, Any]:
    for path in required_sources():
        if not path.is_file():
            raise RuntimeError(f"missing required source: {rel(path)}")
    if sha256_file(ENV_MANIFEST) != ENV_MANIFEST_SHA256:
        raise RuntimeError("S3Ap environment manifest SHA256 drift")
    environment = json.loads(ENV_MANIFEST.read_text(encoding="utf-8"))
    model = environment.get("model", {})
    runtime = environment.get("runtime_lock", {})
    expected = {
        "model.id": (model.get("id"), MODEL_ID),
        "model.revision": (model.get("revision"), MODEL_REVISION),
        "model.weights_sha256": (
            model.get("weights_sha256"),
            MODEL_SHA256,
        ),
        "runtime.docker_image_id": (
            runtime.get("docker_image_id"),
            DOCKER_IMAGE_ID,
        ),
        "learning_runs_started": (
            environment.get("learning_runs_started"),
            0,
        ),
    }
    drift = {
        key: {"actual": actual, "expected": wanted}
        for key, (actual, wanted) in expected.items()
        if actual != wanted
    }
    if drift:
        raise RuntimeError(f"environment lock drift: {drift}")
    census = json.loads(CENSUS_INFERENCE_MANIFEST.read_text(encoding="utf-8"))
    census_runtime = census.get("runtime_lock", {})
    for key, wanted in (
        ("docker_image_id", DOCKER_IMAGE_ID),
        ("model_id", MODEL_ID),
        ("model_revision", MODEL_REVISION),
        ("weights_sha256", MODEL_SHA256),
        ("environment_manifest_sha256", ENV_MANIFEST_SHA256),
    ):
        if census_runtime.get(key) != wanted:
            raise RuntimeError(f"census runtime lock drift for {key}")
    return {
        "environment_manifest": rel(ENV_MANIFEST),
        "environment_manifest_sha256": ENV_MANIFEST_SHA256,
        "model_id": MODEL_ID,
        "model_revision": MODEL_REVISION,
        "weights_sha256": MODEL_SHA256,
        "docker_image_id": DOCKER_IMAGE_ID,
        "same_as_anchor_census": True,
        "learning_runs_started": 0,
    }


def load_offset() -> np.ndarray:
    payload = json.loads(TRAIN_MANIFEST.read_text(encoding="utf-8"))
    value = np.asarray(payload["world_offset"], dtype=np.float64)
    if value.shape != (3,) or not np.all(np.isfinite(value)):
        raise RuntimeError(f"invalid world offset: {value!r}")
    return value


def load_footprints(
    wanted: set[str],
) -> dict[str, Polygon | MultiPolygon]:
    payload = json.loads(FOOTPRINTS.read_text(encoding="utf-8"))
    crs = str(payload.get("crs", {}).get("properties", {}).get("name", ""))
    if "25832" not in crs:
        raise RuntimeError(f"footprint CRS is not EPSG:25832: {crs!r}")
    pieces: dict[str, list[Any]] = defaultdict(list)
    for feature in payload.get("features", []):
        building_id = full_id(
            (feature.get("properties") or {}).get("building_id", "")
        )
        if building_id not in wanted:
            continue
        geometry = make_valid(shape(feature["geometry"]))
        if not geometry.is_empty:
            pieces[building_id].append(geometry)
    result: dict[str, Polygon | MultiPolygon] = {}
    for building_id in sorted(wanted):
        if not pieces.get(building_id):
            raise RuntimeError(f"missing footprint: {building_id}")
        geometry = make_valid(unary_union(pieces[building_id]))
        if (
            geometry.is_empty
            or not isinstance(geometry, (Polygon, MultiPolygon))
        ):
            raise RuntimeError(f"invalid footprint: {building_id}")
        result[building_id] = geometry
    return result


def grid_coverage(
    points_local: np.ndarray,
    footprint: Polygon | MultiPolygon,
    offset: np.ndarray,
    grid: float,
) -> dict[str, Any]:
    minx, miny, maxx, maxy = footprint.bounds
    ix = np.arange(
        math.floor(minx / grid),
        math.floor(maxx / grid) + 1,
        dtype=np.int64,
    )
    iy = np.arange(
        math.floor(miny / grid),
        math.floor(maxy / grid) + 1,
        dtype=np.int64,
    )
    mesh_x, mesh_y = np.meshgrid(ix, iy, indexing="xy")
    eligible = {
        (cell_x, cell_y)
        for cell_x, cell_y in zip(
            mesh_x.ravel().tolist(),
            mesh_y.ravel().tolist(),
        )
        if footprint.intersects(
            box(
                cell_x * grid,
                cell_y * grid,
                (cell_x + 1) * grid,
                (cell_y + 1) * grid,
            )
        )
    }
    if len(points_local):
        world_xy = points_local[:, :2] + offset[:2]
        point_cells = np.floor(world_xy / grid).astype(np.int64)
        occupied = (
            set(
                zip(
                    point_cells[:, 0].tolist(),
                    point_cells[:, 1].tolist(),
                )
            )
            & eligible
        )
    else:
        occupied = set()
    return {
        "coverage_grid_m": grid,
        "coverage_eligible_cell_count": len(eligible),
        "coverage_occupied_cell_count": len(occupied),
        "coverage_ratio": (
            float(len(occupied) / len(eligible)) if eligible else None
        ),
    }


def source_tables() -> dict[str, dict[str, Any]]:
    census_rows = read_csv(CENSUS_PAIRS)
    r1p_rows = read_csv(R1P_PAIRS)
    return {
        "census": {
            "path": CENSUS_PAIRS,
            "sha256": sha256_file(CENSUS_PAIRS),
            "rows": census_rows,
        },
        "R1prime": {
            "path": R1P_PAIRS,
            "sha256": sha256_file(R1P_PAIRS),
            "rows": r1p_rows,
        },
    }


def rows_for_building(
    table: Mapping[str, Any],
    building_id: str,
) -> list[dict[str, str]]:
    rows = [
        row
        for row in table["rows"]
        if full_id(row["building_id"]) == building_id
    ]
    rows.sort(key=lambda row: int(row["pair_rank"]))
    if len(rows) != 10:
        raise RuntimeError(
            f"{building_id} source address count is {len(rows)}, expected 10"
        )
    if [int(row["pair_rank"]) for row in rows] != list(range(1, 11)):
        raise RuntimeError(f"{building_id} source pair ranks are not 1..10")
    return rows


def selected_and_inside(
    source_row: Mapping[str, str],
    footprint: Polygon | MultiPolygon,
    offset: np.ndarray,
) -> dict[str, Any]:
    started = time.monotonic()
    cache_path = REPO / source_row["cache_path"]
    if not cache_path.is_file():
        raise RuntimeError(f"missing locked raw cache: {rel(cache_path)}")
    actual_cache_sha = sha256_file(cache_path)
    if source_row["cache_sha256"] != actual_cache_sha:
        raise RuntimeError(f"raw cache SHA drift: {rel(cache_path)}")
    with np.load(cache_path, allow_pickle=False) as archive:
        required = {
            "world_local_xyz",
            "pixels_a",
            "pixels_b",
            "max_reprojection_error_px",
            "metadata_json",
        }
        if set(archive.files) != required:
            raise RuntimeError(
                f"raw cache fields drift: {rel(cache_path)} "
                f"{sorted(archive.files)}"
            )
        metadata = json.loads(str(archive["metadata_json"]))
        world = np.asarray(
            archive["world_local_xyz"], dtype=np.float64
        )
        max_error = np.asarray(
            archive["max_reprojection_error_px"], dtype=np.float64
        )
        pixels_a = np.asarray(archive["pixels_a"], dtype=np.float64)
        pixels_b = np.asarray(archive["pixels_b"], dtype=np.float64)
    expected_length = int(source_row["positive_depth_count"])
    if (
        len(world)
        != len(max_error)
        != len(pixels_a)
        != len(pixels_b)
    ):
        raise RuntimeError(f"raw cache array-length mismatch: {rel(cache_path)}")
    if {len(world), len(max_error), len(pixels_a), len(pixels_b)} != {
        expected_length
    }:
        raise RuntimeError(f"raw cache positive-depth drift: {rel(cache_path)}")
    if not (
        np.isfinite(world).all()
        and np.isfinite(max_error).all()
        and np.isfinite(pixels_a).all()
        and np.isfinite(pixels_b).all()
    ):
        raise RuntimeError(f"raw cache non-finite payload: {rel(cache_path)}")
    expected_metadata = {
        "schema": "jointbuildgs.boundary_map_v3.fm_dense.raw_pair.v2",
        "building_id": full_id(source_row["building_id"]),
        "pair_rank": int(source_row["pair_rank"]),
        "view_a": source_row["view_a"],
        "view_b": source_row["view_b"],
        "pair_fingerprint": source_row["pair_fingerprint"],
        "input_fingerprint": source_row["input_fingerprint"],
        "model_revision": MODEL_REVISION,
        "model_sha256": MODEL_SHA256,
        "docker_image_id": DOCKER_IMAGE_ID,
        "learning_runs_started": 0,
    }
    drift = {
        key: {"actual": metadata.get(key), "expected": wanted}
        for key, wanted in expected_metadata.items()
        if metadata.get(key) != wanted
    }
    if drift:
        raise RuntimeError(f"raw cache metadata drift: {rel(cache_path)} {drift}")
    selected = world[max_error <= REPROJECTION_THRESHOLD_PX]
    if len(selected):
        inside_mask = contains_xy(
            footprint,
            selected[:, 0] + offset[0],
            selected[:, 1] + offset[1],
        )
        inside = selected[inside_mask]
    else:
        inside = np.zeros((0, 3), dtype=np.float64)
    z_median, z_mad = finite_stats(inside[:, 2])
    source_selected = int(source_row["reprojection_2px_count"])
    source_inside = int(source_row["footprint_inside_count"])
    source_z = as_float(source_row["inside_z_median_m"])
    source_mad = as_float(source_row["inside_z_mad_m"])
    reproduced = bool(
        len(selected) == source_selected
        and len(inside) == source_inside
        and (
            (z_median is None and source_z is None)
            or (
                z_median is not None
                and source_z is not None
                and abs(z_median - source_z) <= 5e-7
            )
        )
        and (
            (z_mad is None and source_mad is None)
            or (
                z_mad is not None
                and source_mad is not None
                and abs(z_mad - source_mad) <= 5e-7
            )
        )
    )
    if not reproduced:
        raise RuntimeError(
            f"source pair metric reproduction drift: "
            f"{source_row['building_id']} rank={source_row['pair_rank']}"
        )
    block_a = acquisition_block(source_row["view_a"])
    block_b = acquisition_block(source_row["view_b"])
    relation = (
        "same_acquisition_minute_block"
        if block_a == block_b
        else "cross_acquisition_minute_block"
    )
    if (
        source_row["acquisition_block_a"] != block_a
        or source_row["acquisition_block_b"] != block_b
        or source_row["pair_relation"] != relation
    ):
        raise RuntimeError(
            f"source pair relation drift: "
            f"{source_row['building_id']} rank={source_row['pair_rank']}"
        )
    baseline = float(source_row["known_colmap_baseline_m"])
    metadata_baseline = float(metadata["known_colmap_baseline_m"])
    if abs(baseline - metadata_baseline) > 5e-7:
        raise RuntimeError(
            f"source pair baseline drift: "
            f"{source_row['building_id']} rank={source_row['pair_rank']}"
        )
    return {
        "cache_path": cache_path,
        "cache_sha256": actual_cache_sha,
        "metadata": metadata,
        "selected": selected,
        "inside": inside,
        "inside_z_median_m": z_median,
        "inside_z_mad_m": z_mad,
        "block_a": block_a,
        "block_b": block_b,
        "relation": relation,
        "baseline_m": baseline,
        "source_pair_metrics_reproduced": True,
        "repool_elapsed_seconds": time.monotonic() - started,
    }


def old_ladder_inventory() -> tuple[list[str], dict[str, dict[str, str]]]:
    fields = read_csv_fields(OLD_LADDER)
    rows = read_csv(OLD_LADDER)
    if len(rows) != 178 or len({row["building_id"] for row in rows}) != 178:
        raise RuntimeError("boundary_map_v4 ladder is not 178 unique rows")
    return fields, {row["building_id"]: row for row in rows}


def verify_target_set(
    old_by_id: Mapping[str, Mapping[str, str]],
) -> dict[str, Any]:
    unmeasurable = {
        building_id
        for building_id, row in old_by_id.items()
        if row["anchor_status"] == "unmeasurable"
    }
    fixed = set(TARGET_IDS)
    if unmeasurable != fixed:
        raise RuntimeError(
            "boundary_map_v4 unmeasurable set differs from fixed nine: "
            f"missing={sorted(fixed - unmeasurable)} "
            f"extra={sorted(unmeasurable - fixed)}"
        )
    dense_failure = {
        building_id
        for building_id, row in old_by_id.items()
        if not as_bool(row["dense_assembled"])
    }
    if len(dense_failure) != 64:
        raise RuntimeError("boundary_map_v4 dense-failure count is not 64")
    untouched_failure = dense_failure - fixed
    if len(untouched_failure) != 55:
        raise RuntimeError("dense-failure 64 minus supplement 9 is not 55")
    return {
        "boundary_map_v4_unmeasurable_count": len(unmeasurable),
        "fixed_target_count": len(fixed),
        "derived_equals_fixed": unmeasurable == fixed,
        "fixed_target_ids": list(TARGET_IDS),
        "fixed_target_set_sha256": set_sha256(fixed),
        "dense_failure_count": len(dense_failure),
        "untouched_dense_failure_count": len(untouched_failure),
        "arithmetic_check": "64-9=55",
        "scope_rule": (
            "only the fixed nine unmeasurable rows may be re-pooled and "
            "mechanically reassigned; the other 55 dense-failure rows remain "
            "unchanged, except the read-only 104586480 reproduction check"
        ),
    }


def source_scope(building_id: str) -> str:
    if building_id in set(CENSUS_TARGET_IDS) or (
        building_id == REPRODUCTION_ID
    ):
        return "census"
    if building_id == R1P_TARGET_ID:
        return "R1prime"
    raise RuntimeError(f"unsupported supplement building: {building_id}")


def build_pair_record(
    source_row: Mapping[str, str],
    detail: Mapping[str, Any],
    target_order: int,
    source_label: str,
    source_table: Mapping[str, Any],
) -> dict[str, Any]:
    same_block = detail["relation"] == "same_acquisition_minute_block"
    baseline_passed = detail["baseline_m"] > BASELINE_THRESHOLD_M
    eligible = same_block and baseline_passed
    return {
        "building_id": full_id(source_row["building_id"]),
        "target_order": target_order,
        "pair_rank": int(source_row["pair_rank"]),
        "view_a": source_row["view_a"],
        "view_b": source_row["view_b"],
        "source_scope": source_label,
        "source_pair_table": rel(source_table["path"]),
        "source_pair_table_sha256": source_table["sha256"],
        "source_pair_row_sha256": sha256_json(dict(source_row)),
        "source_cache_path": rel(detail["cache_path"]),
        "source_cache_sha256": detail["cache_sha256"],
        "cache_metadata_schema": detail["metadata"]["schema"],
        "cache_metadata_created_utc": detail["metadata"]["created_utc"],
        "crop_source": source_row["crop_source"],
        "camera_branch": source_row["camera_branch"],
        "world_frame": source_row["world_frame"],
        "acquisition_block_a": detail["block_a"],
        "acquisition_block_b": detail["block_b"],
        "pair_relation": detail["relation"],
        "same_block_only": True,
        "pair_independence": PAIR_INDEPENDENCE,
        "known_colmap_baseline_m": detail["baseline_m"],
        "baseline_rule": "fixed camera-centre baseline >0.06m",
        "baseline_rule_passed": baseline_passed,
        "reprojection_threshold_px": REPROJECTION_THRESHOLD_PX,
        "eligible_supplement_pair": eligible,
        "status": "success" if eligible else "degenerate",
        "failure_reason": (
            ""
            if eligible
            else (
                "not_same_acquisition_minute_block"
                if not same_block
                else "baseline<=0.06m"
            )
        ),
        "reciprocal_match_count": int(
            source_row["reciprocal_match_count"]
        ),
        "border_match_count": int(source_row["border_match_count"]),
        "dlt_finite_count": int(source_row["dlt_finite_count"]),
        "positive_depth_count": int(source_row["positive_depth_count"]),
        "reprojection_2px_count": len(detail["selected"]),
        "footprint_inside_count": len(detail["inside"]),
        "inside_z_median_m": detail["inside_z_median_m"],
        "inside_z_mad_m": detail["inside_z_mad_m"],
        "source_pair_metrics_reproduced": True,
        "source_inference_elapsed_seconds": as_float(
            source_row["elapsed_seconds"]
        ),
        "repool_elapsed_seconds": detail["repool_elapsed_seconds"],
        "cache_reuse_runs": 1,
        "new_mast3r_inference_runs": 0,
        "inference_execution": "cache_reuse",
        "origin_new_inference_type": source_row["new_inference_type"],
        "pair_fingerprint": source_row["pair_fingerprint"],
        "input_fingerprint": source_row["input_fingerprint"],
        "model_id": MODEL_ID,
        "model_revision": MODEL_REVISION,
        "model_sha256": MODEL_SHA256,
        "docker_image_id": DOCKER_IMAGE_ID,
        "reference_lod2_role": LOD2_ROLE,
        "crs": CRS,
        "learning_runs_started": 0,
        "new_inference_type": NO_NEW_INFERENCE,
        "new_inference_allowlist": ALLOWLIST,
        "_selected": detail["selected"],
        "_inside": detail["inside"],
    }


def target_measurement(
    building_id: str,
    target_order: int,
    source_table: Mapping[str, Any],
    source_label: str,
    footprint: Polygon | MultiPolygon,
    offset: np.ndarray,
    old_row: Mapping[str, str],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    started = time.monotonic()
    source_rows = rows_for_building(source_table, building_id)
    pair_rows: list[dict[str, Any]] = []
    for source_row in source_rows:
        detail = selected_and_inside(source_row, footprint, offset)
        pair_rows.append(
            build_pair_record(
                source_row,
                detail,
                target_order,
                source_label,
                source_table,
            )
        )
    if any(
        row["pair_relation"] != "same_acquisition_minute_block"
        for row in pair_rows
    ):
        raise RuntimeError(f"{building_id} target address is not same-block-only")
    eligible = [
        row for row in pair_rows if row["eligible_supplement_pair"]
    ]
    selected_parts = [row["_selected"] for row in eligible]
    inside_parts = [row["_inside"] for row in eligible]
    selected = (
        np.concatenate(selected_parts, axis=0)
        if selected_parts
        else np.zeros((0, 3), dtype=np.float64)
    )
    inside = (
        np.concatenate(inside_parts, axis=0)
        if inside_parts
        else np.zeros((0, 3), dtype=np.float64)
    )
    z_median, z_mad = finite_stats(inside[:, 2])
    coverage = grid_coverage(inside, footprint, offset, COVERAGE_GRID_M)
    complete = bool(eligible)
    status = "complete" if complete else "unmeasurable"
    inside_count = len(inside)
    if complete and inside_count >= 1:
        cell_after = CELL_2
    elif as_bool(old_row["outline_observable"]):
        cell_after = CELL_3
    else:
        cell_after = CELL_4
    record = {
        "record_role": "supplement_target",
        "building_id": building_id,
        "target_order": target_order,
        "source_scope": source_label,
        "source_pair_table": rel(source_table["path"]),
        "source_address_rule": (
            "census same 10-pair address reuse"
            if source_label == "census"
            else "R1prime same 10-pair address reuse"
        ),
        "status": status,
        "failure_reason": (
            "" if complete else "eligible_same_block_baseline_pairs=0"
        ),
        "measurement_complete": complete,
        "same_block_only": True,
        "pair_independence": PAIR_INDEPENDENCE,
        "low_independence": True,
        "preregister_primary_list_eligible": False,
        "selected_dlt_point_count": len(selected),
        "footprint_inside_point_count": inside_count,
        "inside_z_median_m": z_median,
        "inside_z_mad_m": z_mad,
        "inside_z_median_local_m": z_median,
        "inside_z_mad_local_m": z_mad,
        **coverage,
        "selected_pair_count": len(pair_rows),
        "completed_pair_count": len(pair_rows),
        "eligible_pair_count": len(eligible),
        "nonzero_inside_pair_count": sum(
            int(row["footprint_inside_count"]) > 0 for row in eligible
        ),
        "degenerate_pair_count": sum(
            row["status"] == "degenerate" for row in pair_rows
        ),
        "failed_pair_count": 0,
        "pair_status_summary": "success" if complete else "degenerate",
        "cache_reuse_runs": len(pair_rows),
        "new_mast3r_inference_runs": 0,
        "inference_execution": "cache_reuse",
        "elapsed_seconds": time.monotonic() - started,
        "anchor_status_before": old_row["anchor_status"],
        "anchor_status_after": "measured" if complete else "unmeasurable",
        "anchor_undecided_sticker_before": old_row[
            "anchor_undecided_sticker"
        ],
        "anchor_undecided_sticker_after": (
            "" if complete else "앵커 미판정"
        ),
        "cell_before": old_row["cell_label"],
        "cell_after": cell_after,
        "ref_roof_type": old_row["ref_roof_type"],
        "small_lt50": as_bool(old_row["small_lt50"]),
        "reproduction_expected_inside_count": None,
        "reproduction_expected_inside_z_median_m": None,
        "reproduction_expected_inside_z_mad_m": None,
        "reproduction_check_passed": None,
        "model_id": MODEL_ID,
        "model_revision": MODEL_REVISION,
        "model_sha256": MODEL_SHA256,
        "docker_image_id": DOCKER_IMAGE_ID,
        "environment_manifest": rel(ENV_MANIFEST),
        "environment_manifest_sha256": ENV_MANIFEST_SHA256,
        "pooling_rule": POOLING_RULE,
        "reprojection_threshold_px": REPROJECTION_THRESHOLD_PX,
        "baseline_threshold_m": BASELINE_THRESHOLD_M,
        "footprint_role": FOOTPRINT_ROLE,
        "reference_lod2_role": LOD2_ROLE,
        "crs": CRS,
        "learning_runs_started": 0,
        "new_inference_type": NO_NEW_INFERENCE,
        "new_inference_allowlist": ALLOWLIST,
    }
    return record, pair_rows


def reproduction_measurement(
    source_table: Mapping[str, Any],
    footprint: Polygon | MultiPolygon,
    offset: np.ndarray,
    old_row: Mapping[str, str],
) -> tuple[dict[str, Any], dict[str, Any]]:
    started = time.monotonic()
    source_rows = rows_for_building(source_table, REPRODUCTION_ID)
    details = [
        (source_row, selected_and_inside(source_row, footprint, offset))
        for source_row in source_rows
    ]
    eligible = [
        (source_row, detail)
        for source_row, detail in details
        if detail["relation"] == "cross_acquisition_minute_block"
        and detail["baseline_m"] > BASELINE_THRESHOLD_M
    ]
    selected_parts = [
        detail["selected"] for _source_row, detail in eligible
    ]
    inside_parts = [detail["inside"] for _source_row, detail in eligible]
    selected = (
        np.concatenate(selected_parts, axis=0)
        if selected_parts
        else np.zeros((0, 3), dtype=np.float64)
    )
    inside = (
        np.concatenate(inside_parts, axis=0)
        if inside_parts
        else np.zeros((0, 3), dtype=np.float64)
    )
    z_median, z_mad = finite_stats(inside[:, 2])
    coverage = grid_coverage(inside, footprint, offset, COVERAGE_GRID_M)
    passed = bool(
        len(inside)
        == REPRODUCTION_EXPECTED["footprint_inside_point_count"]
        and z_median is not None
        and abs(
            z_median - REPRODUCTION_EXPECTED["inside_z_median_m"]
        )
        <= 5e-7
        and z_mad is not None
        and abs(z_mad - REPRODUCTION_EXPECTED["inside_z_mad_m"])
        <= 5e-7
    )
    if not passed:
        raise RuntimeError(
            "104586480 reproduction hard stop: "
            f"inside={len(inside)} z={z_median} MAD={z_mad}"
        )
    record = {
        "record_role": "reproduction_check",
        "building_id": REPRODUCTION_ID,
        "target_order": 10,
        "source_scope": "anchor_census",
        "source_pair_table": rel(source_table["path"]),
        "source_address_rule": (
            "anchor census same 10-pair address; original cross-block "
            "eligibility retained"
        ),
        "status": "reproduction_pass",
        "failure_reason": "",
        "measurement_complete": True,
        "same_block_only": False,
        "pair_independence": REPRODUCTION_INDEPENDENCE,
        "low_independence": False,
        "preregister_primary_list_eligible": (
            "not_applicable_reproduction_check"
        ),
        "selected_dlt_point_count": len(selected),
        "footprint_inside_point_count": len(inside),
        "inside_z_median_m": z_median,
        "inside_z_mad_m": z_mad,
        "inside_z_median_local_m": z_median,
        "inside_z_mad_local_m": z_mad,
        **coverage,
        "selected_pair_count": len(details),
        "completed_pair_count": len(details),
        "eligible_pair_count": len(eligible),
        "nonzero_inside_pair_count": sum(
            len(detail["inside"]) > 0
            for _source_row, detail in eligible
        ),
        "degenerate_pair_count": len(details) - len(eligible),
        "failed_pair_count": 0,
        "pair_status_summary": "success",
        "cache_reuse_runs": len(details),
        "new_mast3r_inference_runs": 0,
        "inference_execution": "cache_reuse_read_only_reproduction",
        "elapsed_seconds": time.monotonic() - started,
        "anchor_status_before": old_row["anchor_status"],
        "anchor_status_after": old_row["anchor_status"],
        "anchor_undecided_sticker_before": old_row[
            "anchor_undecided_sticker"
        ],
        "anchor_undecided_sticker_after": old_row[
            "anchor_undecided_sticker"
        ],
        "cell_before": old_row["cell_label"],
        "cell_after": old_row["cell_label"],
        "ref_roof_type": old_row["ref_roof_type"],
        "small_lt50": as_bool(old_row["small_lt50"]),
        "reproduction_expected_inside_count": (
            REPRODUCTION_EXPECTED["footprint_inside_point_count"]
        ),
        "reproduction_expected_inside_z_median_m": (
            REPRODUCTION_EXPECTED["inside_z_median_m"]
        ),
        "reproduction_expected_inside_z_mad_m": (
            REPRODUCTION_EXPECTED["inside_z_mad_m"]
        ),
        "reproduction_check_passed": True,
        "model_id": MODEL_ID,
        "model_revision": MODEL_REVISION,
        "model_sha256": MODEL_SHA256,
        "docker_image_id": DOCKER_IMAGE_ID,
        "environment_manifest": rel(ENV_MANIFEST),
        "environment_manifest_sha256": ENV_MANIFEST_SHA256,
        "pooling_rule": ORIGINAL_POOLING_RULE,
        "reprojection_threshold_px": REPROJECTION_THRESHOLD_PX,
        "baseline_threshold_m": BASELINE_THRESHOLD_M,
        "footprint_role": FOOTPRINT_ROLE,
        "reference_lod2_role": LOD2_ROLE,
        "crs": CRS,
        "learning_runs_started": 0,
        "new_inference_type": NO_NEW_INFERENCE,
        "new_inference_allowlist": ALLOWLIST,
    }
    check = {
        "building_id": REPRODUCTION_ID,
        "expected": REPRODUCTION_EXPECTED,
        "observed": {
            "selected_dlt_point_count": len(selected),
            "footprint_inside_point_count": len(inside),
            "inside_z_median_m": z_median,
            "inside_z_mad_m": z_mad,
            "eligible_pair_count": len(eligible),
        },
        "passed": True,
        "hard_stop_on_mismatch": True,
        "source_pair_table": rel(source_table["path"]),
        "cache_reuse_runs": len(details),
    }
    return record, check


def reliability_comparison(
    census_table: Mapping[str, Any],
    footprints: Mapping[str, Polygon | MultiPolygon],
    offset: np.ndarray,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    measurements = {
        row["building_id"]: row for row in read_csv(CENSUS_MEASUREMENTS)
    }
    rows: list[dict[str, Any]] = []
    for source_row in census_table["rows"]:
        building_id = full_id(source_row["building_id"])
        adopted = measurements.get(building_id, {})
        adopted_z = as_float(adopted.get("inside_z_median_m", ""))
        if (
            source_row["pair_relation"]
            != "same_acquisition_minute_block"
            or int(source_row["footprint_inside_count"] or 0) <= 0
            or adopted_z is None
        ):
            continue
        detail = selected_and_inside(
            source_row, footprints[building_id], offset
        )
        pair_z = detail["inside_z_median_m"]
        if pair_z is None:
            raise RuntimeError(
                f"same-block reliability pair has no z: "
                f"{building_id} rank={source_row['pair_rank']}"
            )
        delta = abs(pair_z - adopted_z)
        rows.append(
            {
                "building_id": building_id,
                "pair_rank": int(source_row["pair_rank"]),
                "view_a": source_row["view_a"],
                "view_b": source_row["view_b"],
                "pair_relation": source_row["pair_relation"],
                "pair_independence": (
                    "low_same_block_read_only_comparison"
                ),
                "footprint_inside_count": int(
                    source_row["footprint_inside_count"]
                ),
                "same_block_pair_inside_z_median_m": pair_z,
                "adopted_cross_block_inside_z_median_m": adopted_z,
                "abs_delta_z_m": delta,
                "within_0_5m": delta <= 0.5,
                "source_pair_table": rel(CENSUS_PAIRS),
                "source_measurement_table": rel(CENSUS_MEASUREMENTS),
                "source_cache_path": rel(detail["cache_path"]),
                "source_cache_sha256": detail["cache_sha256"],
                "source_pair_metrics_reproduced": True,
                "read_only_derivation": True,
                "learning_runs_started": 0,
            }
        )
    rows.sort(key=lambda row: (row["building_id"], row["pair_rank"]))
    values = np.asarray(
        [float(row["abs_delta_z_m"]) for row in rows],
        dtype=np.float64,
    )
    if not len(values):
        raise RuntimeError("same-block reliability comparison is empty")
    summary = {
        "pair_count": len(rows),
        "building_count": len({row["building_id"] for row in rows}),
        "median_abs_delta_z_m": float(np.median(values)),
        "p90_abs_delta_z_m": float(
            np.quantile(values, 0.9, method="lower")
        ),
        "p90_method": "numpy.quantile(method=lower)",
        "maximum_abs_delta_z_m": float(np.max(values)),
        "within_0_5m_count": int(np.count_nonzero(values <= 0.5)),
        "within_0_5m_ratio": float(np.mean(values <= 0.5)),
        "source_rule": (
            "anchor_census_pairs same-acquisition-minute-block rows with "
            "footprint_inside_count>0 and a non-null adopted cross-block "
            "building z in anchor_census_measurements"
        ),
        "read_only_derivation": True,
    }
    for key in (
        "pair_count",
        "within_0_5m_count",
        "p90_method",
    ):
        if summary[key] != RELIABILITY_EXPECTED[key]:
            raise RuntimeError(
                f"same-block reliability {key} drift: "
                f"{summary[key]} != {RELIABILITY_EXPECTED[key]}"
            )
    for key in (
        "median_abs_delta_z_m",
        "p90_abs_delta_z_m",
        "maximum_abs_delta_z_m",
        "within_0_5m_ratio",
    ):
        if abs(summary[key] - RELIABILITY_EXPECTED[key]) > 5e-7:
            raise RuntimeError(
                f"same-block reliability {key} drift: "
                f"{summary[key]} != {RELIABILITY_EXPECTED[key]}"
            )
    return rows, summary


def build_measure_bundle() -> dict[str, Any]:
    started = time.monotonic()
    lock = environment_lock()
    old_fields, old_by_id = old_ladder_inventory()
    set_validation = verify_target_set(old_by_id)
    tables = source_tables()
    census_addresses = {
        building_id
        for building_id in CENSUS_TARGET_IDS
        if len(rows_for_building(tables["census"], building_id)) == 10
    }
    if census_addresses != set(CENSUS_TARGET_IDS):
        raise RuntimeError("census target address set drift")
    if len(rows_for_building(tables["R1prime"], R1P_TARGET_ID)) != 10:
        raise RuntimeError("R1prime 4908169 address count drift")
    wanted = set(TARGET_IDS) | {REPRODUCTION_ID}
    reliability_ids = {
        full_id(row["building_id"])
        for row in tables["census"]["rows"]
        if row["pair_relation"] == "same_acquisition_minute_block"
        and int(row["footprint_inside_count"] or 0) > 0
    }
    footprints = load_footprints(wanted | reliability_ids)
    offset = load_offset()

    measurements: list[dict[str, Any]] = []
    public_pairs: list[dict[str, Any]] = []
    for target_order, building_id in enumerate(TARGET_IDS, start=1):
        label = source_scope(building_id)
        table = tables[label]
        measurement, pair_rows = target_measurement(
            building_id,
            target_order,
            table,
            label,
            footprints[building_id],
            offset,
            old_by_id[building_id],
        )
        measurements.append(measurement)
        for row in pair_rows:
            public_pairs.append(
                {field: row.get(field) for field in PAIR_FIELDS}
            )
    reproduction, reproduction_check = reproduction_measurement(
        tables["census"],
        footprints[REPRODUCTION_ID],
        offset,
        old_by_id[REPRODUCTION_ID],
    )
    measurements.append(reproduction)
    reliability_rows, reliability_summary = reliability_comparison(
        tables["census"],
        footprints,
        offset,
    )
    if len(public_pairs) != 90:
        raise RuntimeError("supplement pair table is not 90 rows")
    if len(measurements) != 10:
        raise RuntimeError("supplement measurement table is not 10 rows")
    if any(row["learning_runs_started"] != 0 for row in measurements):
        raise RuntimeError("measurement learning-zero drift")
    if any(row["new_mast3r_inference_runs"] != 0 for row in measurements):
        raise RuntimeError("unexpected new inference in supplement")
    if any(
        row["pair_independence"] != PAIR_INDEPENDENCE
        or not row["same_block_only"]
        for row in public_pairs
    ):
        raise RuntimeError("target pair low-independence label drift")
    raw_cache_hashes = {
        row["source_cache_path"]: row["source_cache_sha256"]
        for row in public_pairs
    }
    for row in reliability_rows:
        raw_cache_hashes.setdefault(
            row["source_cache_path"], row["source_cache_sha256"]
        )
    reproduction_source_rows = rows_for_building(
        tables["census"], REPRODUCTION_ID
    )
    for source_row in reproduction_source_rows:
        raw_cache_hashes.setdefault(
            source_row["cache_path"], source_row["cache_sha256"]
        )
    return {
        "measurements": measurements,
        "pairs": public_pairs,
        "reliability_rows": reliability_rows,
        "reliability_summary": reliability_summary,
        "reproduction_check": reproduction_check,
        "set_validation": set_validation,
        "environment_lock": lock,
        "old_fields": old_fields,
        "raw_cache_sha256": dict(sorted(raw_cache_hashes.items())),
        "elapsed_seconds": time.monotonic() - started,
    }


def measure() -> None:
    bundle = build_measure_bundle()
    atomic_csv(RUN_PAIRS, bundle["pairs"], PAIR_FIELDS)
    atomic_csv(RUN_MEASUREMENTS, bundle["measurements"], MEASUREMENT_FIELDS)
    atomic_csv(RUN_RELIABILITY, bundle["reliability_rows"], RELIABILITY_FIELDS)
    atomic_csv(DOC_PAIRS, bundle["pairs"], PAIR_FIELDS)
    atomic_csv(DOC_MEASUREMENTS, bundle["measurements"], MEASUREMENT_FIELDS)
    atomic_csv(
        DOC_RELIABILITY,
        bundle["reliability_rows"],
        RELIABILITY_FIELDS,
    )
    source_paths = required_sources()
    outputs = (
        RUN_PAIRS,
        RUN_MEASUREMENTS,
        RUN_RELIABILITY,
        DOC_PAIRS,
        DOC_MEASUREMENTS,
        DOC_RELIABILITY,
    )
    target_rows = bundle["measurements"][:9]
    manifest = {
        "schema": "jointbuildgs.anchor_census_supplement.measurement.v1",
        "created_utc": now(),
        "status": (
            "complete"
            if all(as_bool(row["measurement_complete"]) for row in target_rows)
            else "complete_with_unmeasurable"
        ),
        "branch": git_value("branch", "--show-current"),
        "git_head_at_measurement": git_value("rev-parse", "HEAD"),
        "task_scope": (
            "fixed nine unmeasurable anchor rows; cache-only same-minute-block "
            "re-pooling plus one original-rule reproduction row"
        ),
        "set_validation": bundle["set_validation"],
        "source_address_validation": {
            "census_target_count": 8,
            "census_pair_count": 80,
            "census_source": rel(CENSUS_PAIRS),
            "R1prime_target_count": 1,
            "R1prime_pair_count": 10,
            "R1prime_source": rel(R1P_PAIRS),
            "address_replacement_count": 0,
            "all_target_pair_relations": "same_acquisition_minute_block",
        },
        "only_changed_measurement_rule": (
            "remove cross-acquisition-minute-block requirement; retain "
            "fixed-camera-centre baseline >0.06m, finite positive-depth DLT, "
            "and <=2.0 source-pixel reprojection error"
        ),
        "pooling_rule": POOLING_RULE,
        "environment_lock": bundle["environment_lock"],
        "row_counts": {
            "supplement_target_measurements": 9,
            "reproduction_measurements": 1,
            "measurement_total": 10,
            "supplement_target_pairs": 90,
            "same_block_reliability_pairs": len(
                bundle["reliability_rows"]
            ),
        },
        "target_results": [
            {
                key: row[key]
                for key in (
                    "building_id",
                    "status",
                    "selected_dlt_point_count",
                    "footprint_inside_point_count",
                    "inside_z_median_m",
                    "inside_z_mad_m",
                    "coverage_ratio",
                    "eligible_pair_count",
                    "cell_before",
                    "cell_after",
                    "same_block_only",
                    "pair_independence",
                )
            }
            for row in target_rows
        ],
        "reproduction_check": bundle["reproduction_check"],
        "same_block_reliability_comparison": bundle[
            "reliability_summary"
        ],
        "same_block_reliability_preregistered_scale": {
            "median_abs_delta_z_m": "approximately 0.27",
            "p90_abs_delta_z_m": "approximately 5.1",
            "maximum_abs_delta_z_m": "approximately 7.3",
            "within_0_5m_ratio": "approximately 54%",
        },
        "inference_accounting": {
            "target_cache_reuse_runs": 90,
            "reproduction_cache_reuse_runs": 10,
            "reliability_read_only_cache_validations": len(
                bundle["reliability_rows"]
            ),
            "new_mast3r_inference_runs": 0,
            "authorized_if_4908169_cache_missing": ALLOWLIST,
            "authorized_fallback_invoked": False,
            "gpu_used": False,
            "gpu_budget_seconds": 600,
            "learning_runs_started": 0,
        },
        "new_mast3r_inference_runs": 0,
        "learning_runs_started": 0,
        "source_sha256": output_hashes(source_paths),
        "raw_cache_sha256": bundle["raw_cache_sha256"],
        "output_sha256": output_hashes(outputs),
        "elapsed_seconds": bundle["elapsed_seconds"],
        "reference_lod2_role": LOD2_ROLE,
        "interpretation_or_verdict": None,
    }
    atomic_json(RUN_MEASURE_MANIFEST, manifest)
    print(
        json.dumps(
            {
                "status": manifest["status"],
                "target_measurements": 9,
                "target_pairs": 90,
                "reproduction": True,
                "reliability_pairs": len(bundle["reliability_rows"]),
                "new_mast3r_inference_runs": 0,
                "learning_runs_started": 0,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )


def target_measurement_by_id() -> dict[str, dict[str, str]]:
    rows = read_csv(RUN_MEASUREMENTS)
    targets = {
        row["building_id"]: row
        for row in rows
        if row["record_role"] == "supplement_target"
    }
    if set(targets) != set(TARGET_IDS):
        raise RuntimeError("supplement measurement target set drift")
    return targets


def cell_counts(rows: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    counts = Counter(str(row["cell_label"]) for row in rows)
    return {cell: counts[cell] for cell in CELLS}


def cell_counts_small(
    rows: Sequence[Mapping[str, Any]],
) -> dict[str, dict[str, int]]:
    output: dict[str, dict[str, int]] = {}
    for cell in CELLS:
        selected = [row for row in rows if row["cell_label"] == cell]
        small = sum(as_bool(row["small_lt50"]) for row in selected)
        output[cell] = {
            "total": len(selected),
            "nonsmall": len(selected) - small,
            "small_lt50": small,
        }
    return output


def updated_ladder() -> tuple[
    list[str],
    list[dict[str, Any]],
    dict[str, Any],
]:
    old_fields, old_by_id = old_ladder_inventory()
    targets = target_measurement_by_id()
    rows: list[dict[str, Any]] = []
    for building_id in sorted(old_by_id):
        old = old_by_id[building_id]
        row: dict[str, Any] = dict(old)
        if building_id in targets:
            measurement = targets[building_id]
            complete = as_bool(measurement["measurement_complete"])
            inside = as_int(measurement["footprint_inside_point_count"]) or 0
            observable = as_bool(old["outline_observable"])
            row.update(
                {
                    "anchor_status": (
                        "measured" if complete else "unmeasurable"
                    ),
                    "anchor_measurement_source": rel(RUN_MEASUREMENTS),
                    "anchor_measurement_lineage": (
                        "same_block_cache_repool_low_independence"
                    ),
                    "anchor_selected_dlt_point_count": measurement[
                        "selected_dlt_point_count"
                    ],
                    "anchor_footprint_inside_point_count": measurement[
                        "footprint_inside_point_count"
                    ],
                    "anchor_inside_z_median_m": measurement[
                        "inside_z_median_m"
                    ],
                    "anchor_inside_z_mad_m": measurement[
                        "inside_z_mad_m"
                    ],
                    "anchor_coverage_ratio": measurement["coverage_ratio"],
                    "anchor_selected_pair_count": measurement[
                        "selected_pair_count"
                    ],
                    "anchor_completed_pair_count": measurement[
                        "completed_pair_count"
                    ],
                    "anchor_eligible_pair_count": measurement[
                        "eligible_pair_count"
                    ],
                    "anchor_zero_observed": (
                        complete and inside == 0
                    ),
                    "anchor_undecided_sticker": (
                        "" if complete else "앵커 미판정"
                    ),
                    "new_inference_type": NO_NEW_INFERENCE,
                }
            )
            if complete and inside >= 1:
                row["cell_label"] = CELL_2
                row["cell_assignment_basis"] = (
                    "raw_dense assembled=false and same-block-only measured "
                    "footprint-inside count>=1; low_independence"
                )
            elif observable:
                row["cell_label"] = CELL_3
                row["cell_assignment_basis"] = (
                    "raw_dense assembled=false and same-block-only measured "
                    "footprint-inside count=0 and outline_observable=true; "
                    "low_independence"
                    if complete
                    else old["cell_assignment_basis"]
                )
            else:
                row["cell_label"] = CELL_4
                row["cell_assignment_basis"] = (
                    "raw_dense assembled=false and same-block-only measured "
                    "footprint-inside count=0 and outline_observable=false; "
                    "low_independence"
                    if complete
                    else old["cell_assignment_basis"]
                )
            row.update(
                {
                    "same_block_only": True,
                    "pair_independence": PAIR_INDEPENDENCE,
                    "low_independence": True,
                    "supplement_measurement_source": rel(
                        RUN_MEASUREMENTS
                    ),
                    "supplement_measurement_lineage": (
                        "cached fixed-pose DLT 2px; same-minute-block pooling"
                    ),
                    "supplement_cache_reuse_runs": measurement[
                        "cache_reuse_runs"
                    ],
                    "supplement_new_mast3r_inference_runs": measurement[
                        "new_mast3r_inference_runs"
                    ],
                    "supplement_new_inference_allowlist": ALLOWLIST,
                    "preregister_primary_list_eligible": False,
                }
            )
        else:
            row.update(
                {
                    "same_block_only": False,
                    "pair_independence": (
                        "not_supplement_target_original_value"
                    ),
                    "low_independence": False,
                    "supplement_measurement_source": "",
                    "supplement_measurement_lineage": "",
                    "supplement_cache_reuse_runs": 0,
                    "supplement_new_mast3r_inference_runs": 0,
                    "supplement_new_inference_allowlist": "",
                    "preregister_primary_list_eligible": (
                        "unchanged_not_evaluated_by_supplement"
                    ),
                }
            )
        rows.append(row)
    new_fields = list(old_fields) + [
        field for field in NEW_LADDER_FIELDS if field not in old_fields
    ]
    old_rows = [old_by_id[building_id] for building_id in sorted(old_by_id)]
    changed_old_fields: dict[str, list[str]] = {}
    for row in rows:
        old = old_by_id[row["building_id"]]
        changed = [
            field
            for field in old_fields
            if fmt(row.get(field)) != old.get(field, "")
        ]
        if changed:
            changed_old_fields[row["building_id"]] = changed
    if set(changed_old_fields) - set(TARGET_IDS):
        raise RuntimeError(
            "non-target old ladder fields changed: "
            f"{sorted(set(changed_old_fields) - set(TARGET_IDS))}"
        )
    for building_id, fields in changed_old_fields.items():
        unexpected = set(fields) - ALLOWED_TARGET_OLD_FIELD_CHANGES
        if unexpected:
            raise RuntimeError(
                f"{building_id} unexpected old-field changes: "
                f"{sorted(unexpected)}"
            )
    invariance = {
        "old_field_names": old_fields,
        "new_field_names": list(NEW_LADDER_FIELDS),
        "row_count": len(rows),
        "target_rows_allowed_to_change": list(TARGET_IDS),
        "target_rows_with_old_field_changes": sorted(changed_old_fields),
        "non_target_rows_old_fields_value_identical": (
            len(rows) - len(TARGET_IDS)
        ),
        "untouched_dense_failure_rows": 55,
        "reproduction_building_ladder_value_unchanged": (
            REPRODUCTION_ID not in changed_old_fields
        ),
        "changed_old_fields_by_target": changed_old_fields,
        "old_cell_counts": cell_counts(old_rows),
        "new_cell_counts": cell_counts(rows),
        "old_cell_counts_small_split": cell_counts_small(old_rows),
        "new_cell_counts_small_split": cell_counts_small(rows),
    }
    if len(rows) != 178:
        raise RuntimeError("boundary_map_v4_1 ladder is not 178 rows")
    return new_fields, rows, invariance


def markdown_table(
    rows: Sequence[Mapping[str, Any]],
    columns: Sequence[tuple[str, str]],
) -> list[str]:
    if not rows:
        return ["| 없음 |", "|---|"]
    output = [
        "| " + " | ".join(label for _field, label in columns) + " |",
        "|" + "|".join("---" for _field, _label in columns) + "|",
    ]
    for row in rows:
        output.append(
            "| "
            + " | ".join(fmt(row.get(field)) for field, _label in columns)
            + " |"
        )
    return output


def summary_markdown(
    ladder: Sequence[Mapping[str, Any]],
    invariance: Mapping[str, Any],
    measure_manifest: Mapping[str, Any],
) -> str:
    measurements = read_csv(RUN_MEASUREMENTS)
    targets = [
        row
        for row in measurements
        if row["record_role"] == "supplement_target"
    ]
    reproduction = next(
        row
        for row in measurements
        if row["record_role"] == "reproduction_check"
    )
    reliability = measure_manifest["same_block_reliability_comparison"]
    before = invariance["old_cell_counts_small_split"]
    after = invariance["new_cell_counts_small_split"]
    count_rows = [
        {
            "cell": cell,
            "before": before[cell]["total"],
            "after": after[cell]["total"],
            "before_small": before[cell]["small_lt50"],
            "after_small": after[cell]["small_lt50"],
        }
        for cell in CELLS
    ]
    unresolved = [
        row for row in targets if row["anchor_status_after"] == "unmeasurable"
    ]
    lines = [
        "# 앵커 census 보강 측정 및 boundary_map_v4.1 요약",
        "",
        "- 범위: 고정 9동 동일 취득 분-블록 쌍 재풀링·기계 셀 재배정",
        "- 신규 MASt3R 추론: `0` · GPU 사용: `false` · 학습 실행: `0`",
        f"- 쌍 표기: `{PAIR_INDEPENDENCE}` · 건물 표기: `same_block_only=true`",
        "- 지도 그림: 재생성하지 않음",
        "",
        "## 1. 셀 인원 전후",
        "",
        *markdown_table(
            count_rows,
            (
                ("cell", "셀"),
                ("before", "v4 전체"),
                ("after", "v4.1 전체"),
                ("before_small", "v4 소형"),
                ("after_small", "v4.1 소형"),
            ),
        ),
        "",
        "## 2. 고정 9동 재풀링 측정값",
        "",
        *markdown_table(
            targets,
            (
                ("building_id", "building_id"),
                ("eligible_pair_count", "인정 쌍"),
                ("selected_dlt_point_count", "2px 점"),
                ("footprint_inside_point_count", "inside 점"),
                ("inside_z_median_m", "inside z 중앙(m)"),
                ("inside_z_mad_m", "inside z MAD(m)"),
                ("cell_before", "이전 셀"),
                ("cell_after", "재배정 셀"),
            ),
        ),
        "",
        "> 위 9행은 모두 `same_block_only=true`, "
        "`pair_independence=low_same_block`이며 사전등록 §2 주 명단 산입 "
        "불가 표기를 포함한다.",
        "",
        "## 3. 104586480 원 규칙 재현",
        "",
        *markdown_table(
            [reproduction],
            (
                ("footprint_inside_point_count", "inside 점"),
                ("inside_z_median_m", "inside z 중앙(m)"),
                ("inside_z_mad_m", "inside z MAD(m)"),
                ("reproduction_check_passed", "재현 일치"),
            ),
        ),
        "",
        "## 4. 동일 블록 쌍 |Δz| 대조",
        "",
        f"- 대상: {reliability['pair_count']}쌍 / "
        f"{reliability['building_count']}동",
        f"- 중앙: {fmt(reliability['median_abs_delta_z_m'])} m",
        f"- p90: {fmt(reliability['p90_abs_delta_z_m'])} m "
        f"(`{reliability['p90_method']}`)",
        f"- 최대: {fmt(reliability['maximum_abs_delta_z_m'])} m",
        f"- |Δz|≤0.5 m: {reliability['within_0_5m_count']}/"
        f"{reliability['pair_count']} "
        f"({100 * reliability['within_0_5m_ratio']:.2f}%)",
        "",
        "## 5. 범위·상태 기록",
        "",
        f"- 9동 외 169행의 기존 열 값 동일: "
        f"`{invariance['non_target_rows_old_fields_value_identical']}`행",
        "- dense 실패 비대상 55동 원 값 재풀링 없음",
        f"- 보강 후 `unmeasurable` 유지: `{len(unresolved)}`동"
        + (
            " (" + ", ".join(row["building_id"] for row in unresolved) + ")"
            if unresolved
            else ""
        ),
        "- 참조 LoD2: 투영·분류 전용",
        "",
    ]
    return "\n".join(lines)


def finalize() -> None:
    qa_measure()
    measure_manifest = json.loads(
        RUN_MEASURE_MANIFEST.read_text(encoding="utf-8")
    )
    fields, ladder, invariance = updated_ladder()
    atomic_csv(NEW_LADDER, ladder, fields)
    atomic_text(
        SUMMARY,
        summary_markdown(ladder, invariance, measure_manifest),
    )
    target_rows = [
        row
        for row in read_csv(RUN_MEASUREMENTS)
        if row["record_role"] == "supplement_target"
    ]
    unresolved = [
        row
        for row in target_rows
        if row["anchor_status_after"] == "unmeasurable"
    ]
    source_paths = required_sources() + (
        RUN_PAIRS,
        RUN_MEASUREMENTS,
        RUN_RELIABILITY,
        RUN_MEASURE_MANIFEST,
        DOC_PAIRS,
        DOC_MEASUREMENTS,
        DOC_RELIABILITY,
    )
    old_public = json.loads(
        OLD_PUBLIC_MANIFEST.read_text(encoding="utf-8")
    )
    old_figure_expected = old_public["output_sha256"][rel(OLD_FIGURE)]
    old_figure_actual = sha256_file(OLD_FIGURE)
    if old_figure_actual != old_figure_expected:
        raise RuntimeError("boundary_map_v4 figure changed before v4.1 finalize")
    public = {
        "schema": "jointbuildgs.anchor_census_supplement.boundary_map_v4_1.v1",
        "created_utc": now(),
        "status": (
            "complete_with_unmeasurable" if unresolved else "complete"
        ),
        "branch": git_value("branch", "--show-current"),
        "git_head_at_finalize": git_value("rev-parse", "HEAD"),
        "scope": measure_manifest["task_scope"],
        "set_validation": measure_manifest["set_validation"],
        "source_address_validation": measure_manifest[
            "source_address_validation"
        ],
        "only_changed_measurement_rule": measure_manifest[
            "only_changed_measurement_rule"
        ],
        "assignment_rule": {
            CELL_1: "dense_assembled=true",
            CELL_2: (
                "dense failure and measured footprint-inside count>=1; "
                "same-block supplement rows retain low_independence"
            ),
            CELL_3: (
                "dense failure and measured footprint-inside count=0 with "
                "outline_observable=true, or unmeasurable with outline"
            ),
            CELL_4: (
                "dense failure and no measured anchor assignment and "
                "outline_observable=false"
            ),
        },
        "ladder_invariance": invariance,
        "cell_counts": invariance["new_cell_counts"],
        "cell_counts_small_split": invariance[
            "new_cell_counts_small_split"
        ],
        "target_results": measure_manifest["target_results"],
        "unmeasurable_after_supplement": [
            row["building_id"] for row in unresolved
        ],
        "reproduction_check": measure_manifest["reproduction_check"],
        "same_block_reliability_comparison": measure_manifest[
            "same_block_reliability_comparison"
        ],
        "environment_lock": measure_manifest["environment_lock"],
        "inference_accounting": measure_manifest["inference_accounting"],
        "low_independence_contract": {
            "pair_value": PAIR_INDEPENDENCE,
            "building_same_block_only": True,
            "preregister_section_2_primary_list_eligible": False,
            "applies_to_buildings": list(TARGET_IDS),
        },
        "reference_lod2_role": LOD2_ROLE,
        "map_figure": {
            "regenerated": False,
            "reason": "figure subtask deferred by 2026-07-20 order",
            "existing_v4_figure": rel(OLD_FIGURE),
            "existing_v4_figure_sha256": old_figure_actual,
        },
        "issues_sync_contract": {
            "path": "phases/p2-gsjso/docs/issues.md",
            "same_output_commit_required": True,
            "note": (
                "the detached driver stages the new issues.md version with "
                "each synchronized artifact batch"
            ),
        },
        "source_sha256": output_hashes(source_paths),
        "output_sha256": output_hashes(
            (
                RUN_PAIRS,
                RUN_MEASUREMENTS,
                RUN_RELIABILITY,
                RUN_MEASURE_MANIFEST,
                DOC_PAIRS,
                DOC_MEASUREMENTS,
                DOC_RELIABILITY,
                NEW_LADDER,
                SUMMARY,
            )
        ),
        "learning_runs_started": 0,
        "new_mast3r_inference_runs": 0,
        "new_inference_allowlist": [ALLOWLIST],
        "interpretation_or_verdict": None,
    }
    atomic_json(PUBLIC_MANIFEST, public)
    print(
        json.dumps(
            {
                "status": public["status"],
                "ladder": len(ladder),
                "cell_counts": public["cell_counts"],
                "unmeasurable_after": len(unresolved),
                "map_regenerated": False,
                "learning_runs_started": 0,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )


def verify_measurement_rows(
    rows: Sequence[Mapping[str, str]],
) -> None:
    if len(rows) != 10:
        raise RuntimeError("supplement measurements are not 10 rows")
    if [row["building_id"] for row in rows[:9]] != list(TARGET_IDS):
        raise RuntimeError("supplement target order drift")
    if rows[-1]["building_id"] != REPRODUCTION_ID:
        raise RuntimeError("supplement reproduction tail row drift")
    if any(row["learning_runs_started"] != "0" for row in rows):
        raise RuntimeError("supplement measurement learning-zero drift")
    if any(
        row["new_mast3r_inference_runs"] != "0" for row in rows
    ):
        raise RuntimeError("supplement measurement inference-zero drift")
    for row in rows[:9]:
        if (
            row["same_block_only"] != "true"
            or row["pair_independence"] != PAIR_INDEPENDENCE
            or row["low_independence"] != "true"
            or row["preregister_primary_list_eligible"] != "false"
        ):
            raise RuntimeError(
                f"{row['building_id']} low-independence contract drift"
            )
    reproduction = rows[-1]
    if (
        reproduction["reproduction_check_passed"] != "true"
        or as_int(reproduction["footprint_inside_point_count"]) != 3364
        or abs(
            (as_float(reproduction["inside_z_median_m"]) or 0.0)
            - (-43.161802)
        )
        > 5e-7
        or abs(
            (as_float(reproduction["inside_z_mad_m"]) or 0.0)
            - 0.071273
        )
        > 5e-7
    ):
        raise RuntimeError("104586480 reproduction row drift")


def qa_measure() -> None:
    required = (
        RUN_PAIRS,
        RUN_MEASUREMENTS,
        RUN_RELIABILITY,
        RUN_MEASURE_MANIFEST,
        DOC_PAIRS,
        DOC_MEASUREMENTS,
        DOC_RELIABILITY,
    )
    missing = [rel(path) for path in required if not path.is_file()]
    if missing:
        raise RuntimeError(f"missing supplement measurement outputs: {missing}")
    run_pairs = read_csv(RUN_PAIRS)
    doc_pairs = read_csv(DOC_PAIRS)
    run_measurements = read_csv(RUN_MEASUREMENTS)
    doc_measurements = read_csv(DOC_MEASUREMENTS)
    run_reliability = read_csv(RUN_RELIABILITY)
    doc_reliability = read_csv(DOC_RELIABILITY)
    manifest = json.loads(
        RUN_MEASURE_MANIFEST.read_text(encoding="utf-8")
    )
    if run_pairs != doc_pairs:
        raise RuntimeError("run/docs supplement pair values differ")
    if run_measurements != doc_measurements:
        raise RuntimeError("run/docs supplement measurement values differ")
    if run_reliability != doc_reliability:
        raise RuntimeError("run/docs supplement reliability values differ")
    verify_measurement_rows(run_measurements)
    if len(run_pairs) != 90:
        raise RuntimeError("supplement target pair rows are not 90")
    if any(
        row["same_block_only"] != "true"
        or row["pair_independence"] != PAIR_INDEPENDENCE
        or row["learning_runs_started"] != "0"
        or row["new_mast3r_inference_runs"] != "0"
        or row["cache_reuse_runs"] != "1"
        or row["source_pair_metrics_reproduced"] != "true"
        for row in run_pairs
    ):
        raise RuntimeError("supplement pair contract drift")
    if len(run_reliability) != RELIABILITY_EXPECTED["pair_count"]:
        raise RuntimeError("same-block reliability pair count drift")
    if any(row["learning_runs_started"] != "0" for row in run_reliability):
        raise RuntimeError("reliability rows learning-zero drift")
    if manifest["learning_runs_started"] != 0:
        raise RuntimeError("measurement manifest learning-zero drift")
    if manifest["inference_accounting"]["new_mast3r_inference_runs"] != 0:
        raise RuntimeError("measurement manifest inference-zero drift")
    if manifest["set_validation"]["derived_equals_fixed"] is not True:
        raise RuntimeError("measurement manifest fixed set mismatch")
    if manifest["reproduction_check"]["passed"] is not True:
        raise RuntimeError("measurement manifest reproduction mismatch")
    reliability = manifest["same_block_reliability_comparison"]
    for key, expected in RELIABILITY_EXPECTED.items():
        actual = reliability[key]
        if isinstance(expected, float):
            if abs(float(actual) - expected) > 5e-7:
                raise RuntimeError(f"reliability manifest {key} drift")
        elif actual != expected:
            raise RuntimeError(f"reliability manifest {key} drift")
    verify_hash_map(manifest["source_sha256"], "measure source")
    verify_hash_map(manifest["raw_cache_sha256"], "measure raw cache")
    verify_hash_map(manifest["output_sha256"], "measure output")
    print(
        json.dumps(
            {
                "status": manifest["status"],
                "measurements": len(run_measurements),
                "pairs": len(run_pairs),
                "reliability_pairs": len(run_reliability),
                "new_mast3r_inference_runs": 0,
                "learning_runs_started": 0,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )


def qa() -> None:
    qa_measure()
    required = (NEW_LADDER, PUBLIC_MANIFEST, SUMMARY)
    missing = [rel(path) for path in required if not path.is_file()]
    if missing:
        raise RuntimeError(f"missing supplement public outputs: {missing}")
    public = json.loads(PUBLIC_MANIFEST.read_text(encoding="utf-8"))
    old_fields, old_by_id = old_ladder_inventory()
    new_fields = read_csv_fields(NEW_LADDER)
    rows = read_csv(NEW_LADDER)
    new_by_id = {row["building_id"]: row for row in rows}
    if len(rows) != 178 or len(new_by_id) != 178:
        raise RuntimeError("boundary_map_v4_1 is not 178 unique rows")
    if set(new_by_id) != set(old_by_id):
        raise RuntimeError("boundary_map_v4_1 population drift")
    if new_fields != old_fields + list(NEW_LADDER_FIELDS):
        raise RuntimeError("boundary_map_v4_1 field order drift")
    for building_id, old in old_by_id.items():
        new = new_by_id[building_id]
        changed = [
            field
            for field in old_fields
            if new.get(field, "") != old.get(field, "")
        ]
        if building_id not in set(TARGET_IDS) and changed:
            raise RuntimeError(
                f"{building_id} non-target old fields changed: {changed}"
            )
        if building_id in set(TARGET_IDS):
            unexpected = set(changed) - ALLOWED_TARGET_OLD_FIELD_CHANGES
            if unexpected:
                raise RuntimeError(
                    f"{building_id} unexpected old-field changes: "
                    f"{sorted(unexpected)}"
                )
            if (
                new["same_block_only"] != "true"
                or new["pair_independence"] != PAIR_INDEPENDENCE
                or new["low_independence"] != "true"
                or new["preregister_primary_list_eligible"] != "false"
            ):
                raise RuntimeError(
                    f"{building_id} v4.1 low-independence fields drift"
                )
    if new_by_id[REPRODUCTION_ID] != {
        **old_by_id[REPRODUCTION_ID],
        "same_block_only": "false",
        "pair_independence": "not_supplement_target_original_value",
        "low_independence": "false",
        "supplement_measurement_source": "",
        "supplement_measurement_lineage": "",
        "supplement_cache_reuse_runs": "0",
        "supplement_new_mast3r_inference_runs": "0",
        "supplement_new_inference_allowlist": "",
        "preregister_primary_list_eligible": (
            "unchanged_not_evaluated_by_supplement"
        ),
    }:
        raise RuntimeError("104586480 ladder value changed outside new fields")
    if any(row["learning_runs_started"] != "0" for row in rows):
        raise RuntimeError("boundary_map_v4_1 learning-zero drift")
    actual_counts = cell_counts(rows)
    if actual_counts != public["cell_counts"]:
        raise RuntimeError("boundary_map_v4_1 cell-count manifest drift")
    if public["ladder_invariance"][
        "non_target_rows_old_fields_value_identical"
    ] != 169:
        raise RuntimeError("v4.1 non-target invariance count drift")
    if public["map_figure"]["regenerated"] is not False:
        raise RuntimeError("supplement map regeneration flag drift")
    if sha256_file(OLD_FIGURE) != public["map_figure"][
        "existing_v4_figure_sha256"
    ]:
        raise RuntimeError("existing v4 map hash drift")
    if public["learning_runs_started"] != 0:
        raise RuntimeError("public manifest learning-zero drift")
    if public["new_mast3r_inference_runs"] != 0:
        raise RuntimeError("public manifest inference-zero drift")
    verify_hash_map(public["source_sha256"], "public source")
    verify_hash_map(public["output_sha256"], "public output")
    summary = SUMMARY.read_text(encoding="utf-8")
    required_summary_tokens = (
        "# 앵커 census 보강 측정 및 boundary_map_v4.1 요약",
        "low_same_block",
        "104586480",
        "numpy.quantile(method=lower)",
        "지도 그림: 재생성하지 않음",
    )
    missing_tokens = [
        token for token in required_summary_tokens if token not in summary
    ]
    if missing_tokens:
        raise RuntimeError(
            f"supplement summary missing tokens: {missing_tokens}"
        )
    print(
        json.dumps(
            {
                "status": public["status"],
                "ladder": len(rows),
                "cell_counts": actual_counts,
                "target_rows": 9,
                "non_target_old_fields_identical": 169,
                "new_mast3r_inference_runs": 0,
                "learning_runs_started": 0,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )


def preflight() -> None:
    bundle = build_measure_bundle()
    target_rows = bundle["measurements"][:9]
    print(
        json.dumps(
            {
                "target_set_equal": bundle["set_validation"][
                    "derived_equals_fixed"
                ],
                "target_measurements": len(bundle["measurements"]) - 1,
                "target_pairs": len(bundle["pairs"]),
                "reproduction_passed": bundle["reproduction_check"]["passed"],
                "reliability": bundle["reliability_summary"],
                "raw_cache_files": len(bundle["raw_cache_sha256"]),
                "target_results": [
                    {
                        key: row[key]
                        for key in (
                            "building_id",
                            "eligible_pair_count",
                            "selected_dlt_point_count",
                            "footprint_inside_point_count",
                            "inside_z_median_m",
                            "inside_z_mad_m",
                            "coverage_ratio",
                            "cell_before",
                            "cell_after",
                        )
                    }
                    for row in target_rows
                ],
                "new_mast3r_inference_runs": 0,
                "gpu_required": False,
                "learning_runs_started": 0,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "command",
        choices=("preflight", "measure", "qa-measure", "finalize", "qa"),
    )
    args = parser.parse_args()
    if args.command == "preflight":
        preflight()
    elif args.command == "measure":
        measure()
    elif args.command == "qa-measure":
        qa_measure()
    elif args.command == "finalize":
        finalize()
    else:
        qa()


if __name__ == "__main__":
    main()
