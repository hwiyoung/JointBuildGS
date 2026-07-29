#!/usr/bin/env python3
"""R1-prime-3 locked S3Ap FM dense-dial measurement queue.

This module starts no optimizer and performs no learning.  MASt3R contributes
only reciprocal descriptor correspondences.  Metric points are obtained with
the S3Ap locked fixed-pose float64 DLT chain, realized for each frozen source
camera:

* reciprocal descriptor NN, stride 8;
* reject a 3 px border in the 512 x 384 crop;
* invert crop coordinates to source pixels without a half-pixel shift;
* C001 semantic crops: fixed COLMAP PINHOLE K[R|t];
* P0 projected crops: raw FULL_OPENCV pixels undistorted before fixed
  COLMAP [R|t] DLT and reprojected with the original distortion;
* finite homogeneous DLT and positive depth in both cameras;
* retain max(source-pixel reprojection error in either view) <= 2 px;
* pool only cross-acquisition-minute-block pairs with baseline > 0.06 m.

The supplied EPSG:25832 footprint is first applied after DLT for inside-point
counts and 0.5 m cell coverage.  A frozen semantic-region crop can carry the
locked S3Ap oracle/raycast address; a projected-footprint crop can carry a
reference projection.  Those crop-address roles are recorded explicitly and
are not described as reference-free candidate generation.

Raw post-cheirality caches are resumable and deliberately live below the run
directory.  Cache fingerprints include the complete jobs payload, this
script, the reused S3Ap kernels, the environment lock, and every addressed
image/semantic-region source.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
import math
import os
import platform
import re
import subprocess
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib")
os.environ.setdefault("XDG_CACHE_HOME", "/tmp")

import numpy as np
import torch
from PIL import Image as PILImage
from shapely import contains_xy, make_valid
from shapely.geometry import MultiPolygon, Polygon, shape
from shapely.ops import unary_union


REPO = Path(__file__).resolve().parents[3]
SCRIPT_DIR = Path(__file__).resolve().parent
P2_SHARED_SCRIPT_DIR = REPO / "phases/p2-gsjso/scripts"
RUN_ID = "20260719_boundary_map_v3"
RUN_DIR = REPO / "phases/p2-gsjso/runs" / RUN_ID
JOBS = RUN_DIR / "fm_dense_jobs.json"
BUILDING_CSV = RUN_DIR / "fm_dense_measurements.csv"
PAIR_CSV = RUN_DIR / "fm_dense_pairs.csv"
PROGRESS = RUN_DIR / "fm_dense_progress.json"
MANIFEST = RUN_DIR / "fm_dense_manifest.json"
RUN_LOG = RUN_DIR / "fm_dense.log"
RAW_DIR = RUN_DIR / "fm_dense_raw"

ENV_MANIFEST = REPO / "docs/experiments/e5_c001_s3ap/manifests/e5_c001_s3ap_fm_env_manifest.json"
S3AP_DIAL_CONFIG = (
    REPO / "phases/p2-gsjso/configs/e5_c001_s3ap_fm_dense_dial.json"
)
V2_METRICS = REPO / "docs/archive/boundary_map/v2/tables/boundary_map_v2_metrics.csv"
V2_MAST3R_SCRIPT = SCRIPT_DIR / "boundary_map_v2_mast3r.py"
P0_AUX_SCRIPT = P2_SHARED_SCRIPT_DIR / "population_aux_v3.py"
P0_DATUM_SCRIPT = P2_SHARED_SCRIPT_DIR / "projection_datum.py"
P0_PROJECTION_CONFIG = REPO / "configs/projection_datum.json"
RETRI_SCRIPT = P2_SHARED_SCRIPT_DIR / "e5_c001_s3ap_fm_retriangulation.py"
RESCORE_SCRIPT = P2_SHARED_SCRIPT_DIR / "e5_c001_s3ap_fm_retri_rescore.py"
BASE_SCRIPT = P2_SHARED_SCRIPT_DIR / "e5_c001_s3ap_fm_rescore.py"
JOB_PRODUCER = SCRIPT_DIR / "boundary_map_v3.py"
P0_IMAGE_DIR = REPO / "phases/p0-audit/data/work/images/Images"
P0_CAMERAS = REPO / "phases/p0-audit/data/work/colmap/sparse/0/cameras.txt"
P0_IMAGES = REPO / "phases/p0-audit/data/work/colmap/sparse/0/images.txt"
P0_SCENE_REFERENCE = (
    REPO / "phases/p0-audit/data/work/opf/opf/scene_reference_frame.json"
)

ENV_MANIFEST_SHA256 = (
    "7246a77569a7af1b931ad60eda7012e6e3e8f4ff81b5e10f2e3c1a2efea80d68"
)
MODEL_ID = "naver/MASt3R_ViTLarge_BaseDecoder_512_catmlpdpt_metric"
MODEL_REVISION = "06e7259f34c3060f322df5cb0c7b9094f57e41fc"
MODEL_SHA256 = (
    "0a615eb05fa9db654050aa655945ee5696e7c6c1b7f93f1ee8c37249010f6feb"
)
MODEL_BYTES = 2_754_661_648
MODEL_CONFIG_SHA256 = (
    "718eb93dc4f9e4332b60cc0041af962d712cbd346d7770ce35c5b22cff68eae4"
)
DOCKER_IMAGE_TAG = "jointbuildgs-s3ap-mast3r:20260714-f5209af"
DOCKER_IMAGE_ID = (
    "sha256:89d64b4c7112cc55db0d42d562e2a0208858658c0c67ab1bd48424175c50f501"
)
MAST3R_COMMIT = "f5209afc300cec36239a7ac992263f36847bbba0"
DUST3R_COMMIT = "3cc8c88c413bb9e34c41db0e0eef99c2ee010b12"
CROCO_COMMIT = "d7de0705845239092414480bd829228723bf20de"
DOCKERFILE_SHA256 = (
    "2ada6809de7e5d8e66a9c62875edaf47fe9ee584c4a1aec228732b7e3e0fc3fc"
)
PIP_FREEZE_SHA256 = (
    "1c556c3be3304703a2971d82b4fd320fc96d2dd682787388123130db0a586b77"
)

LOAD_WIDTH = 512
LOAD_HEIGHT = 384
MATCH_SUBSAMPLE = 8
MATCH_BORDER_PX = 3
REPROJECTION_THRESHOLD_PX = 2.0
DEGENERATE_BASELINE_MAX_M = 0.06
COVERAGE_GRID_M = 0.5
MAX_BUDGET_SECONDS = 6 * 60 * 60
FINALIZATION_RESERVE_MAX_SECONDS = 60.0
NEW_INFERENCE_TYPE = "R1prime-3_FM_dense_dial_2px"
RAW_DEFINITION = (
    "MASt3R reciprocal descriptor-NN matches after the locked 3-pixel crop "
    "border, linearly triangulated with fixed COLMAP K[R|t], finite "
    "homogeneous DLT, and positive depth in both cameras; no "
    "reprojection-error ceiling"
)
SOURCE_SPECIFIC_RAW_DEFINITION = (
    "MASt3R reciprocal descriptor-NN matches after the locked 3-pixel crop "
    "border, linearly triangulated with the source-specific fixed COLMAP "
    "camera realization (PINHOLE K[R|t], or FULL_OPENCV raw pixels "
    "undistorted before [R|t] DLT), finite homogeneous DLT, and positive "
    "depth in both cameras; no reprojection-error ceiling"
)
MATCH_RULE = (
    "MASt3R reciprocal descriptor NN; stride8; dot distance; block_size=8192; "
    "3px border in 512x384 crop"
)
TRIANGULATION_RULE = (
    "source-specific fixed-COLMAP-camera float64 linear DLT; finite "
    "homogeneous solution; positive depth in both cameras; max per-view "
    "reprojection error in original source pixels <=2.0px"
)
C001_TRIANGULATION_RULE = (
    "crop pixels mapped to source pixels without half-pixel shift; float64 "
    "linear DLT with fixed PINHOLE COLMAP K[R|t]; finite homogeneous "
    "solution; positive depth in both cameras; max per-view source-pixel "
    "reprojection error <=2.0px"
)
P0_TRIANGULATION_RULE = (
    "crop pixels mapped to raw source pixels without half-pixel shift; "
    "FULL_OPENCV raw pixels undistorted with the frozen 12 camera parameters; "
    "float64 linear DLT with fixed COLMAP [R|t]; finite homogeneous solution; "
    "positive depth in both cameras; reprojection with the original "
    "FULL_OPENCV distortion; max per-view raw source-pixel reprojection error "
    "<=2.0px"
)
C001_CAMERA_BRANCH = "c001_pinhole_binary"
P0_CAMERA_BRANCH = "p0_full_opencv_text"
WORLD_FRAME = "canonical_local_xyz"
POOLING_RULE = (
    "concatenate 2px DLT survivors only from cross-acquisition-minute-block "
    "pairs with fixed-COLMAP camera-centre baseline >0.06m"
)
FOOTPRINT_ROLE = (
    "post-DLT footprint-XY containment and EPSG:25832 0.5m intersect-cell "
    "coverage denominator only"
)
LOD2_ROLE = "not read by this runner; downstream classification/scoring only"
REPRODUCTION_EXPECTED = {
    "DEBY_LOD2_4907199": {
        "selected_dlt_point_count": 538,
        "footprint_inside_point_count": 373,
        "inside_z_median_m": -34.347425,
    }
}
LOCKED_PRIORITY_PREFIX = [
    "DEBY_LOD2_4907199",
    "DEBY_LOD2_8568391",
    "DEBY_LOD2_4908049",
    "DEBY_LOD2_4908162",
]


def load_module(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot import {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
if str(P2_SHARED_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(P2_SHARED_SCRIPT_DIR))

retri = load_module("boundary_map_v3_s3ap_retri", RETRI_SCRIPT)
rescore = load_module("boundary_map_v3_s3ap_rescore", RESCORE_SCRIPT)
v2_mast3r = load_module("boundary_map_v3_v2_mast3r", V2_MAST3R_SCRIPT)
p0_aux = load_module("boundary_map_v3_p0_aux", P0_AUX_SCRIPT)
p0_datum = load_module("boundary_map_v3_p0_datum", P0_DATUM_SCRIPT)
base = retri.base


BUILDING_FIELDS = [
    "building_id",
    "priority_rank",
    "priority_group",
    "primary_assignment",
    "queue_inclusion_reason",
    "status",
    "failure_reason",
    "measurement_complete",
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
    "failed_pair_count",
    "pending_pair_count",
    "reciprocal_match_count",
    "border_match_count",
    "dlt_finite_count",
    "positive_depth_count",
    "reprojection_2px_count",
    "crop_source_inventory",
    "camera_branch_inventory",
    "frame_source_inventory",
    "camera_model_inventory",
    "world_frame_inventory",
    "triangulation_rule_inventory",
    "sparse_v2_status",
    "sparse_v2_selected_dlt_point_count",
    "sparse_v2_footprint_inside_point_count",
    "sparse_v2_inside_z_median_m",
    "sparse_v2_inside_z_mad_m",
    "sparse_v2_score",
    "sparse_v2_reference_json",
    "reproduction_check_required",
    "reproduction_expected_selected_dlt_point_count",
    "reproduction_expected_footprint_inside_point_count",
    "reproduction_expected_inside_z_median_m",
    "reproduction_check_passed",
    "elapsed_seconds",
    "elapsed_seconds_this_invocation",
    "completed_utc",
    "model_id",
    "model_revision",
    "model_sha256",
    "docker_image_id",
    "raw_definition",
    "match_rule",
    "triangulation_rule",
    "pooling_rule",
    "footprint_role",
    "lod2_role",
    "crs",
    "new_mast3r_inference_runs",
    "cache_reuse_runs",
    "learning_runs_started",
    "new_inference_type",
    "job_sha256",
    "input_fingerprint",
]

PAIR_FIELDS = [
    "building_id",
    "priority_rank",
    "pair_rank",
    "view_a",
    "view_b",
    "crop_source",
    "camera_branch",
    "frame_source",
    "camera_model",
    "camera_source",
    "pose_source",
    "scene_reference_source",
    "world_frame",
    "triangulation_rule",
    "crop_a_xyxy",
    "crop_b_xyxy",
    "acquisition_block_a",
    "acquisition_block_b",
    "pair_relation",
    "known_colmap_baseline_m",
    "eligible_summary_pair",
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
    "inside_z_median_local_m",
    "inside_z_mad_local_m",
    "elapsed_seconds",
    "cache_path",
    "cache_sha256",
    "new_mast3r_inference_runs",
    "cache_reuse_runs",
    "learning_runs_started",
    "new_inference_type",
    "pair_fingerprint",
    "input_fingerprint",
]


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def rel(path: Path | str) -> str:
    value = Path(path)
    try:
        return str(value.resolve().relative_to(REPO.resolve()))
    except ValueError:
        return str(value.resolve())


def git_value(*args: str) -> str:
    try:
        return subprocess.check_output(
            ["git", *args], cwd=REPO, text=True, stderr=subprocess.DEVNULL
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return ""


def sha256_file(path: Path, block_size: int = 1 << 20) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(block_size), b""):
            digest.update(block)
    return digest.hexdigest()


def sha256_json(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    ).hexdigest()


def atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def fmt(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (bool, np.bool_)):
        return "true" if bool(value) else "false"
    if isinstance(value, (float, np.floating)):
        return "" if not math.isfinite(float(value)) else f"{float(value):.6f}"
    return str(value)


def atomic_csv(
    path: Path, rows: Sequence[dict[str, Any]], fields: Sequence[str]
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
        writer.writerows(
            [{key: fmt(row.get(key)) for key in fields} for row in rows]
        )
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def log(message: str) -> None:
    RUN_DIR.mkdir(parents=True, exist_ok=True)
    line = f"{now()} {message}"
    print(line, flush=True)
    with RUN_LOG.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def full_id(value: Any) -> str:
    text = str(value).strip()
    if not text:
        raise RuntimeError("empty building_id")
    return text if text.startswith("DEBY_LOD2_") else f"DEBY_LOD2_{text}"


def short_id(value: Any) -> str:
    return full_id(value).removeprefix("DEBY_LOD2_")


def view_stem(value: Any) -> str:
    text = str(value).strip()
    if not text:
        raise RuntimeError("empty view stem")
    return Path(text).stem


def parse_box(value: Any, label: str) -> list[int]:
    if not isinstance(value, (list, tuple)) or len(value) != 4:
        raise RuntimeError(f"{label} must be an xyxy array of four integers")
    raw = [float(item) for item in value]
    if not all(math.isfinite(item) and item.is_integer() for item in raw):
        raise RuntimeError(f"{label} is not integer-valued: {value!r}")
    box = [int(item) for item in raw]
    if box[2] <= box[0] or box[3] <= box[1]:
        raise RuntimeError(f"{label} is empty or reversed: {box!r}")
    return box


def acquisition_block(stem: str) -> str:
    try:
        return rescore.acquisition_block(stem)
    except (IndexError, AttributeError) as exc:
        raise RuntimeError(f"cannot derive acquisition block from {stem!r}") from exc


def camera_branch(pair: dict[str, Any]) -> str:
    if pair["crop_source"] == "s3ap_locked_or_frozen_region":
        return C001_CAMERA_BRANCH
    if pair["crop_source"] == "projected_footprint":
        return P0_CAMERA_BRANCH
    raise RuntimeError(
        f"unsupported crop source for camera branch: {pair['crop_source']!r}"
    )


def branch_provenance(pair: dict[str, Any]) -> dict[str, str]:
    branch = camera_branch(pair)
    if branch == C001_CAMERA_BRANCH:
        return {
            "camera_branch": branch,
            "frame_source": rel(base.IMAGE_DIR),
            "camera_model": "PINHOLE",
            "camera_source": rel(base.SPARSE_DIR / "cameras.bin"),
            "pose_source": rel(base.SPARSE_DIR / "images.bin"),
            "scene_reference_source": "",
            "world_frame": WORLD_FRAME,
            "triangulation_rule": C001_TRIANGULATION_RULE,
        }
    return {
        "camera_branch": branch,
        "frame_source": rel(P0_IMAGE_DIR),
        "camera_model": "FULL_OPENCV",
        "camera_source": rel(P0_CAMERAS),
        "pose_source": rel(P0_IMAGES),
        "scene_reference_source": rel(P0_SCENE_REFERENCE),
        "world_frame": WORLD_FRAME,
        "triangulation_rule": P0_TRIANGULATION_RULE,
    }


def finite_stats(values: np.ndarray) -> tuple[float | None, float | None]:
    selected = np.asarray(values, dtype=np.float64)
    selected = selected[np.isfinite(selected)]
    if not len(selected):
        return None, None
    median = float(np.median(selected))
    return median, float(np.median(np.abs(selected - median)))


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def load_sparse_v2() -> dict[str, dict[str, str]]:
    rows = read_csv(V2_METRICS)
    output: dict[str, dict[str, str]] = {}
    for row in rows:
        building_id = full_id(row["building_id"])
        if building_id in output:
            raise RuntimeError(f"duplicate v2 metric row: {building_id}")
        output[building_id] = {
            "fm_status": row.get("fm_status", ""),
            "fm_reprojection_pass_count": row.get(
                "fm_reprojection_pass_count", ""
            ),
            "fm_correspondence_count": row.get("fm_correspondence_count", ""),
            "fm_z_median_m": row.get("fm_z_median_m", ""),
            "fm_z_mad_m": row.get("fm_z_mad_m", ""),
            "fm_score": row.get("fm_score", ""),
            "fm_selected_pair_count": row.get("fm_selected_pair_count", ""),
            "fm_completed_pair_count": row.get("fm_completed_pair_count", ""),
            "fm_pooling_rule": row.get("fm_pooling_rule", ""),
        }
    return output


def normalize_jobs(payload: Any) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    if not isinstance(payload, dict) or set(payload) != {"model", "jobs"}:
        raise RuntimeError("jobs JSON top-level keys must be exactly model and jobs")
    model = payload["model"]
    if not isinstance(model, dict):
        raise RuntimeError("jobs model must be an object")
    expected_model = {
        "model_id": MODEL_ID,
        "model_revision": MODEL_REVISION,
        "weights_sha256": MODEL_SHA256,
        "weights_bytes": MODEL_BYTES,
        "model_config_sha256": MODEL_CONFIG_SHA256,
        "docker_image_tag": DOCKER_IMAGE_TAG,
        "docker_image_id": DOCKER_IMAGE_ID,
        "mast3r_commit": MAST3R_COMMIT,
        "dust3r_commit": DUST3R_COMMIT,
        "croco_commit": CROCO_COMMIT,
        "environment_manifest": rel(ENV_MANIFEST),
        "environment_manifest_sha256": ENV_MANIFEST_SHA256,
        "dense_dial_config": rel(S3AP_DIAL_CONFIG),
        "dense_dial_config_sha256": sha256_file(S3AP_DIAL_CONFIG),
        "raw_definition": RAW_DEFINITION,
        "reprojection_threshold_px": REPROJECTION_THRESHOLD_PX,
        "learning_runs_started": 0,
        "new_inference_type": NEW_INFERENCE_TYPE,
    }
    for key, expected in expected_model.items():
        if model.get(key) != expected:
            raise RuntimeError(
                f"jobs model lock mismatch for {key}: "
                f"{model.get(key)!r} != {expected!r}"
            )
    if not all(bool(value) for value in model.get("lock_checks", {}).values()):
        raise RuntimeError("jobs model lock_checks contain a false value")
    raw_jobs = payload["jobs"]
    if not isinstance(raw_jobs, list) or not raw_jobs:
        raise RuntimeError("jobs must be a non-empty array")
    jobs: list[dict[str, Any]] = []
    building_ids: set[str] = set()
    priority_ranks: set[int] = set()
    for queue_index, raw_job in enumerate(raw_jobs, start=1):
        if not isinstance(raw_job, dict):
            raise RuntimeError(f"job {queue_index} is not an object")
        building_id = full_id(raw_job.get("building_id"))
        if building_id in building_ids:
            raise RuntimeError(f"duplicate building job: {building_id}")
        building_ids.add(building_id)
        priority_rank = int(raw_job.get("priority_rank", queue_index))
        if priority_rank in priority_ranks:
            raise RuntimeError(f"duplicate priority_rank: {priority_rank}")
        priority_ranks.add(priority_rank)
        raw_pairs = raw_job.get("pairs")
        if not isinstance(raw_pairs, list) or not raw_pairs:
            raise RuntimeError(f"{building_id} has no pair jobs")
        pairs: list[dict[str, Any]] = []
        pair_ranks: set[int] = set()
        for pair_index, raw_pair in enumerate(raw_pairs, start=1):
            if not isinstance(raw_pair, dict):
                raise RuntimeError(
                    f"{building_id} pair {pair_index} is not an object"
                )
            pair_rank = int(raw_pair.get("pair_rank", pair_index))
            if pair_rank in pair_ranks:
                raise RuntimeError(
                    f"{building_id} duplicate pair_rank={pair_rank}"
                )
            pair_ranks.add(pair_rank)
            crop_source_label = str(
                raw_pair.get("crop_source", "")
            ).strip()
            crop_source_aliases = {
                "s3ap_locked_or_frozen_region": (
                    "s3ap_locked_or_frozen_region"
                ),
                "s3ap_locked_pjpl_semantic_region": (
                    "s3ap_locked_or_frozen_region"
                ),
                "c001_frozen_semantic_region": (
                    "s3ap_locked_or_frozen_region"
                ),
                "projected_footprint": "projected_footprint",
                (
                    "v2_projected_footprint_at_LoD2_height_"
                    "projection_classification_only"
                ): "projected_footprint",
            }
            crop_source = crop_source_aliases.get(crop_source_label)
            if crop_source is None:
                raise RuntimeError(
                    f"{building_id} rank {pair_rank} unsupported crop_source="
                    f"{crop_source_label!r}"
                )
            pair = {
                "pair_rank": pair_rank,
                "view_a": view_stem(raw_pair.get("view_a")),
                "view_b": view_stem(raw_pair.get("view_b")),
                "crop_source": crop_source,
                "crop_source_job_label": crop_source_label,
                "crop_a_xyxy": (
                    parse_box(raw_pair.get("crop_a_xyxy"), "crop_a_xyxy")
                    if crop_source == "projected_footprint"
                    else None
                ),
                "crop_b_xyxy": (
                    parse_box(raw_pair.get("crop_b_xyxy"), "crop_b_xyxy")
                    if crop_source == "projected_footprint"
                    else None
                ),
            }
            if pair["view_a"] == pair["view_b"]:
                raise RuntimeError(
                    f"{building_id} rank {pair_rank} repeats one view"
                )
            pairs.append(pair)
        pairs.sort(key=lambda item: int(item["pair_rank"]))
        normalized = {
            "building_id": building_id,
            "priority_rank": priority_rank,
            "priority_group": str(raw_job.get("priority_group", "")),
            "primary_assignment": str(raw_job.get("primary_assignment", "")),
            "queue_inclusion_reason": str(
                raw_job.get("queue_inclusion_reason", "")
            ),
            "pairs": pairs,
        }
        normalized["job_sha256"] = sha256_json(normalized)
        jobs.append(normalized)
    jobs.sort(key=lambda item: (int(item["priority_rank"]), item["building_id"]))
    present_locked = [item for item in LOCKED_PRIORITY_PREFIX if item in building_ids]
    actual_prefix = [
        item["building_id"] for item in jobs[: len(present_locked)]
    ]
    if actual_prefix != present_locked:
        raise RuntimeError(
            "manual textureless priority prefix drift: "
            f"actual={actual_prefix} expected={present_locked}"
        )
    return model, jobs


def verify_environment(
    model_dir: Path, device: str
) -> tuple[dict[str, Any], Path, dict[str, str]]:
    required = [
        ENV_MANIFEST,
        S3AP_DIAL_CONFIG,
        BASE_SCRIPT,
        RETRI_SCRIPT,
        RESCORE_SCRIPT,
        JOB_PRODUCER,
        base.FOOTPRINTS,
        base.TRAIN_MANIFEST,
        base.SPARSE_DIR / "cameras.bin",
        base.SPARSE_DIR / "images.bin",
        V2_METRICS,
    ]
    for path in required:
        if not path.is_file():
            raise RuntimeError(f"missing locked source: {rel(path)}")
    if sha256_file(ENV_MANIFEST) != ENV_MANIFEST_SHA256:
        raise RuntimeError("S3Ap environment manifest SHA256 mismatch")
    environment = json.loads(ENV_MANIFEST.read_text(encoding="utf-8"))
    model_lock = environment.get("model", {})
    runtime_lock = environment.get("runtime_lock", {})
    code_lock = environment.get("code", {})
    expected = {
        "model.id": (model_lock.get("id"), MODEL_ID),
        "model.revision": (model_lock.get("revision"), MODEL_REVISION),
        "model.weights_sha256": (
            model_lock.get("weights_sha256"),
            MODEL_SHA256,
        ),
        "model.weights_bytes": (model_lock.get("weights_bytes"), MODEL_BYTES),
        "model.config_sha256": (
            model_lock.get("config_sha256"),
            MODEL_CONFIG_SHA256,
        ),
        "runtime.docker_image_tag": (
            runtime_lock.get("docker_image_tag"),
            DOCKER_IMAGE_TAG,
        ),
        "runtime.docker_image_id": (
            runtime_lock.get("docker_image_id"),
            DOCKER_IMAGE_ID,
        ),
        "code.mast3r_commit": (
            code_lock.get("mast3r_commit"),
            MAST3R_COMMIT,
        ),
        "code.dust3r_commit": (
            code_lock.get("dust3r_commit"),
            DUST3R_COMMIT,
        ),
        "code.croco_commit": (code_lock.get("croco_commit"), CROCO_COMMIT),
    }
    for label, (actual, locked) in expected.items():
        if actual != locked:
            raise RuntimeError(
                f"environment manifest {label} mismatch: "
                f"{actual!r} != {locked!r}"
            )
    actual_image = os.environ.get("MAST3R_DOCKER_IMAGE_ID", "")
    if actual_image != DOCKER_IMAGE_ID:
        raise RuntimeError(
            "S3Ap Docker image ID mismatch: "
            f"actual={actual_image!r} expected={DOCKER_IMAGE_ID!r}"
        )
    dockerfile = REPO / str(runtime_lock["dockerfile"])
    pip_freeze = REPO / str(runtime_lock["pip_freeze"])
    if sha256_file(dockerfile) != DOCKERFILE_SHA256:
        raise RuntimeError("S3Ap Dockerfile SHA256 mismatch")
    if sha256_file(pip_freeze) != PIP_FREEZE_SHA256:
        raise RuntimeError("S3Ap pip-freeze SHA256 mismatch")
    weights = model_dir / "model.safetensors"
    config = model_dir / "config.json"
    if model_dir.name != MODEL_REVISION:
        raise RuntimeError(
            f"model revision path mismatch: {model_dir.name!r}"
        )
    if not weights.is_file() or weights.stat().st_size != MODEL_BYTES:
        raise RuntimeError("MASt3R weight byte lock mismatch")
    if sha256_file(weights) != MODEL_SHA256:
        raise RuntimeError("MASt3R weight SHA256 mismatch")
    if not config.is_file() or sha256_file(config) != MODEL_CONFIG_SHA256:
        raise RuntimeError("MASt3R config SHA256 mismatch")
    if device.startswith("cuda") and not torch.cuda.is_available():
        raise RuntimeError("CUDA requested but unavailable")
    if platform.python_version() != str(runtime_lock["python"]):
        raise RuntimeError(
            "Python runtime drift: "
            f"{platform.python_version()} != {runtime_lock['python']}"
        )
    if torch.__version__ != str(runtime_lock["torch"]):
        raise RuntimeError(
            f"torch runtime drift: {torch.__version__} != "
            f"{runtime_lock['torch']}"
        )
    if str(torch.version.cuda) != str(runtime_lock["torch_cuda"]):
        raise RuntimeError(
            f"torch CUDA drift: {torch.version.cuda} != "
            f"{runtime_lock['torch_cuda']}"
        )
    if device.startswith("cuda"):
        gpu_name = torch.cuda.get_device_name(torch.device(device))
        if gpu_name != str(runtime_lock["gpu_name"]):
            raise RuntimeError(
                f"GPU runtime drift: {gpu_name!r} != "
                f"{runtime_lock['gpu_name']!r}"
            )
    repository_paths = {
        "mast3r": Path("/opt/mast3r"),
        "dust3r": Path("/opt/mast3r/dust3r"),
        "croco": Path("/opt/mast3r/dust3r/croco"),
    }
    commit_expected = {
        "mast3r": MAST3R_COMMIT,
        "dust3r": DUST3R_COMMIT,
        "croco": CROCO_COMMIT,
    }
    commits: dict[str, str] = {}
    for name, path in repository_paths.items():
        if not path.is_dir():
            raise RuntimeError(f"locked code directory missing: {path}")
        try:
            commit = subprocess.check_output(
                [
                    "git",
                    "-c",
                    f"safe.directory={path}",
                    "-C",
                    str(path),
                    "rev-parse",
                    "HEAD",
                ],
                text=True,
                stderr=subprocess.STDOUT,
            ).strip()
        except (OSError, subprocess.CalledProcessError) as exc:
            raise RuntimeError(
                f"cannot verify {name} commit at {path}"
            ) from exc
        if commit != commit_expected[name]:
            raise RuntimeError(
                f"{name} commit drift: {commit} != {commit_expected[name]}"
            )
        commits[name] = commit
    return environment, weights, commits


def required_stems(
    jobs: Sequence[dict[str, Any]], branch: str
) -> set[str]:
    return {
        pair[side]
        for job in jobs
        for pair in job["pairs"]
        if camera_branch(pair) == branch
        for side in ("view_a", "view_b")
    }


def load_frames_for_jobs(
    jobs: Sequence[dict[str, Any]], offset: np.ndarray
) -> dict[str, dict[str, Any]]:
    inventories: dict[str, dict[str, Any]] = {}
    c001_stems = required_stems(jobs, C001_CAMERA_BRANCH)
    if c001_stems:
        frames = base.load_frames()
        cameras = base.read_cameras_bin(base.SPARSE_DIR / "cameras.bin")
        images = base.read_images_bin(base.SPARSE_DIR / "images.bin")
        camera_model_by_stem = {
            Path(image.name).stem: cameras[image.camera_id].model
            for image in images.values()
        }
        missing = sorted(c001_stems - set(frames))
        if missing:
            raise RuntimeError(
                "locked C001 PINHOLE frames missing: " + "|".join(missing)
            )
        non_pinhole = {
            stem: camera_model_by_stem.get(stem, "MISSING")
            for stem in sorted(c001_stems)
            if camera_model_by_stem.get(stem) != "PINHOLE"
        }
        if non_pinhole:
            raise RuntimeError(
                f"fixed S3Ap C001 DLT requires PINHOLE cameras: {non_pinhole}"
            )
        for stem in sorted(c001_stems):
            frame = frames[stem]
            for key, expected_shape in (
                ("K", (3, 3)),
                ("R", (3, 3)),
                ("t", (3,)),
            ):
                value = np.asarray(frame[key], dtype=np.float64)
                if (
                    value.shape != expected_shape
                    or not np.isfinite(value).all()
                ):
                    raise RuntimeError(
                        f"invalid locked C001 frame {stem} {key}: "
                        f"shape={value.shape}"
                    )
        inventories[C001_CAMERA_BRANCH] = {
            "frames": {stem: frames[stem] for stem in sorted(c001_stems)},
            "camera_model": "PINHOLE",
        }

    p0_stems = required_stems(jobs, P0_CAMERA_BRANCH)
    if p0_stems:
        model_name = v2_mast3r.camera_model_name(P0_CAMERAS)
        if model_name != "FULL_OPENCV":
            raise RuntimeError(
                f"frozen P0 camera model drift: {model_name!r}"
            )
        width, height, params = p0_aux.parse_cam_model(P0_CAMERAS)
        params = np.asarray(params, dtype=np.float64)
        if (
            (width, height) != (5280, 3956)
            or params.shape != (12,)
            or not np.isfinite(params).all()
        ):
            raise RuntimeError(
                "invalid frozen P0 FULL_OPENCV camera: "
                f"size={(width, height)} params_shape={params.shape}"
            )
        scene_reference = json.loads(
            P0_SCENE_REFERENCE.read_text(encoding="utf-8")
        )
        transform = p0_datum.scene_transform(scene_reference)
        scale = np.asarray(transform.get("scale"), dtype=np.float64)
        shift = np.asarray(transform.get("shift"), dtype=np.float64)
        if (
            scale.shape != (3,)
            or shift.shape != (3,)
            or not np.allclose(scale, np.ones(3), rtol=0.0, atol=0.0)
            or not np.allclose(shift, -offset, rtol=0.0, atol=0.0)
            or bool(transform.get("swap_xy", False))
        ):
            raise RuntimeError(
                "P0 canonical-local transform does not match the locked "
                f"C001 world offset: scale={scale.tolist()} "
                f"shift={shift.tolist()} offset={offset.tolist()} "
                f"swap_xy={transform.get('swap_xy', False)!r}"
            )
        zero_base = np.asarray(
            p0_aux.canonical_to_base(
                np.zeros((1, 3), dtype=np.float64), scene_reference
            ),
            dtype=np.float64,
        )
        if (
            zero_base.shape != (1, 3)
            or not np.allclose(
                zero_base[0], offset, rtol=0.0, atol=1e-12
            )
        ):
            raise RuntimeError(
                "P0 canonical_to_base does not reproduce the locked "
                f"world offset: {zero_base!r}"
            )
        parsed = p0_aux.parse_cameras(P0_IMAGES, scene_reference)
        cameras_by_stem: dict[str, Any] = {}
        for frame in parsed:
            stem = Path(frame.name).stem
            if stem in cameras_by_stem:
                raise RuntimeError(f"duplicate frozen P0 pose: {stem}")
            cameras_by_stem[stem] = frame
        missing = sorted(p0_stems - set(cameras_by_stem))
        if missing:
            raise RuntimeError(
                "frozen P0 FULL_OPENCV poses missing: " + "|".join(missing)
            )
        frames: dict[str, dict[str, Any]] = {}
        for stem in sorted(p0_stems):
            frame = cameras_by_stem[stem]
            image_path = P0_IMAGE_DIR / frame.name
            if not image_path.is_file():
                raise RuntimeError(
                    f"frozen P0 source image missing: {rel(image_path)}"
                )
            with PILImage.open(image_path) as image:
                image_size = image.size
            if image_size != (width, height):
                raise RuntimeError(
                    f"frozen P0 source dimensions drift for {stem}: "
                    f"{image_size} != {(width, height)}"
                )
            frames[stem] = {
                "name": frame.name,
                "path": image_path,
                "camera": frame,
                "width": width,
                "height": height,
            }
        inventories[P0_CAMERA_BRANCH] = {
            "frames": frames,
            "camera_model": "FULL_OPENCV",
            "camera_parameters": params,
            "scene_reference": scene_reference,
        }
    return inventories


def crop_boxes(
    building_id: str,
    pair: dict[str, Any],
    frame_inventories: dict[str, dict[str, Any]],
) -> tuple[list[int], list[int]]:
    branch = camera_branch(pair)
    frames = frame_inventories[branch]["frames"]
    frame_a = frames[pair["view_a"]]
    frame_b = frames[pair["view_b"]]
    if pair["crop_source"] == "s3ap_locked_or_frozen_region":
        mask_a, _meta_a = base.target_region_mask(
            short_id(building_id), pair["view_a"]
        )
        mask_b, _meta_b = base.target_region_mask(
            short_id(building_id), pair["view_b"]
        )
        box_a = list(
            base.crop_box_4x3(
                mask_a, int(frame_a["width"]), int(frame_a["height"])
            )
        )
        box_b = list(
            base.crop_box_4x3(
                mask_b, int(frame_b["width"]), int(frame_b["height"])
            )
        )
    else:
        box_a = list(pair["crop_a_xyxy"])
        box_b = list(pair["crop_b_xyxy"])
    for label, box, frame in (
        ("crop_a_xyxy", box_a, frame_a),
        ("crop_b_xyxy", box_b, frame_b),
    ):
        if (
            box[0] < 0
            or box[1] < 0
            or box[2] > int(frame["width"])
            or box[3] > int(frame["height"])
        ):
            raise RuntimeError(
                f"{building_id} {label} outside source frame: {box}"
            )
        width, height = box[2] - box[0], box[3] - box[1]
        if width * 3 != height * 4:
            raise RuntimeError(
                f"{building_id} {label} is not exact 4:3: {box}"
            )
    return box_a, box_b


def source_paths(
    jobs_path: Path,
    jobs: Sequence[dict[str, Any]],
    frame_inventories: dict[str, dict[str, Any]],
    model_dir: Path,
    environment: dict[str, Any],
) -> list[Path]:
    paths: set[Path] = {
        Path(__file__).resolve(),
        jobs_path,
        ENV_MANIFEST,
        S3AP_DIAL_CONFIG,
        V2_METRICS,
        BASE_SCRIPT,
        RETRI_SCRIPT,
        RESCORE_SCRIPT,
        V2_MAST3R_SCRIPT,
        P0_AUX_SCRIPT,
        P0_DATUM_SCRIPT,
        P0_PROJECTION_CONFIG,
        base.FOOTPRINTS,
        base.TRAIN_MANIFEST,
        base.SPARSE_DIR / "cameras.bin",
        base.SPARSE_DIR / "images.bin",
        REPO / str(environment["runtime_lock"]["dockerfile"]),
        REPO / str(environment["runtime_lock"]["pip_freeze"]),
        model_dir / "model.safetensors",
        model_dir / "config.json",
    }
    if any(
        pair["crop_source"] == "projected_footprint"
        for job in jobs
        for pair in job["pairs"]
    ):
        paths.update({P0_CAMERAS, P0_IMAGES, P0_SCENE_REFERENCE})
    for job in jobs:
        for pair in job["pairs"]:
            branch = camera_branch(pair)
            frames = frame_inventories[branch]["frames"]
            for side in ("view_a", "view_b"):
                paths.add(Path(frames[pair[side]]["path"]))
                if pair["crop_source"] == "s3ap_locked_or_frozen_region":
                    region = base.REGION_DIR / f"{pair[side]}.npz"
                    if region.is_file():
                        paths.add(region)
    missing = [rel(path) for path in paths if not path.is_file()]
    if missing:
        raise RuntimeError(f"source inventory has missing files: {missing}")
    return sorted(paths, key=lambda path: rel(path))


def input_fingerprint(
    jobs_payload: dict[str, Any],
    source_hashes: dict[str, str],
) -> str:
    return sha256_json(
        {
            "schema": "jointbuildgs.boundary_map_v3.fm_dense.input.v2",
            "run_id": RUN_ID,
            "jobs": jobs_payload,
            "source_sha256": source_hashes,
            "model": {
                "id": MODEL_ID,
                "revision": MODEL_REVISION,
                "weights_sha256": MODEL_SHA256,
                "weights_bytes": MODEL_BYTES,
                "config_sha256": MODEL_CONFIG_SHA256,
            },
            "docker_image_id": DOCKER_IMAGE_ID,
            "raw_definition": RAW_DEFINITION,
            "source_specific_raw_definition": (
                SOURCE_SPECIFIC_RAW_DEFINITION
            ),
            "pooling_rule": POOLING_RULE,
            "learning_runs_started": 0,
            "new_inference_type": NEW_INFERENCE_TYPE,
        }
    )


def cache_path(building_id: str, pair_rank: int) -> Path:
    short = short_id(building_id)
    if not re.fullmatch(r"[A-Za-z0-9_-]+", short):
        raise RuntimeError(f"unsafe building id for cache path: {building_id}")
    return RAW_DIR / f"{short}_rank{pair_rank:02d}_raw_cheirality.npz"


def pair_fingerprint(
    job: dict[str, Any],
    pair: dict[str, Any],
    box_a: Sequence[int],
    box_b: Sequence[int],
    fingerprint: str,
) -> str:
    return sha256_json(
        {
            "schema": "jointbuildgs.boundary_map_v3.fm_dense.pair_input.v2",
            "building_id": job["building_id"],
            "job_sha256": job["job_sha256"],
            "pair": pair,
            "camera_provenance": branch_provenance(pair),
            "derived_crop_a_xyxy": list(box_a),
            "derived_crop_b_xyxy": list(box_b),
            "input_fingerprint": fingerprint,
        }
    )


def save_cache(
    path: Path,
    detail: dict[str, Any],
    pair_fp: str,
    fingerprint: str,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    metadata = {
        "schema": "jointbuildgs.boundary_map_v3.fm_dense.raw_pair.v2",
        "building_id": detail["building_id"],
        "pair_rank": detail["pair_rank"],
        "view_a": detail["view_a"],
        "view_b": detail["view_b"],
        "crop_source": detail["crop_source"],
        "camera_branch": detail["camera_branch"],
        "frame_source": detail["frame_source"],
        "camera_model": detail["camera_model"],
        "camera_source": detail["camera_source"],
        "pose_source": detail["pose_source"],
        "scene_reference_source": detail["scene_reference_source"],
        "world_frame": detail["world_frame"],
        "triangulation_rule": detail["triangulation_rule"],
        "crop_a_xyxy": detail["crop_a_xyxy"],
        "crop_b_xyxy": detail["crop_b_xyxy"],
        "known_colmap_baseline_m": detail["known_colmap_baseline_m"],
        "reciprocal_match_count": detail["reciprocal_match_count"],
        "border_match_count": detail["border_match_count"],
        "dlt_finite_count": detail["dlt_finite_count"],
        "positive_depth_count": detail["positive_depth_count"],
        "pair_elapsed_seconds": detail["pair_elapsed_seconds"],
        "raw_definition": RAW_DEFINITION,
        "source_specific_raw_definition": SOURCE_SPECIFIC_RAW_DEFINITION,
        "pair_fingerprint": pair_fp,
        "input_fingerprint": fingerprint,
        "model_revision": MODEL_REVISION,
        "model_sha256": MODEL_SHA256,
        "docker_image_id": DOCKER_IMAGE_ID,
        "candidate_generation_reference_role": (
            "crop address only; footprint containment and coverage occur "
            "after fixed-pose DLT"
        ),
        "learning_runs_started": 0,
        "new_inference_type": NEW_INFERENCE_TYPE,
        "created_utc": now(),
    }
    temporary = path.with_name(f".{path.name}.tmp.npz")
    np.savez_compressed(
        temporary,
        world_local_xyz=detail["world"],
        pixels_a=detail["pixels_a"],
        pixels_b=detail["pixels_b"],
        max_reprojection_error_px=detail["max_error"],
        metadata_json=json.dumps(metadata, ensure_ascii=False),
    )
    os.replace(temporary, path)


def load_cache(
    path: Path, pair_fp: str, fingerprint: str
) -> dict[str, Any]:
    with np.load(path, allow_pickle=False) as archive:
        metadata = json.loads(str(archive["metadata_json"]))
        if (
            metadata.get("schema")
            != "jointbuildgs.boundary_map_v3.fm_dense.raw_pair.v2"
        ):
            raise RuntimeError(f"raw cache schema mismatch: {rel(path)}")
        if metadata.get("pair_fingerprint") != pair_fp:
            raise RuntimeError(
                f"raw cache pair fingerprint mismatch: {rel(path)}"
            )
        if metadata.get("input_fingerprint") != fingerprint:
            raise RuntimeError(
                f"raw cache input fingerprint mismatch: {rel(path)}"
            )
        if metadata.get("model_sha256") != MODEL_SHA256:
            raise RuntimeError(f"raw cache model lock mismatch: {rel(path)}")
        detail = {
            **metadata,
            "world": np.asarray(archive["world_local_xyz"], dtype=np.float64),
            "pixels_a": np.asarray(archive["pixels_a"], dtype=np.float64),
            "pixels_b": np.asarray(archive["pixels_b"], dtype=np.float64),
            "max_error": np.asarray(
                archive["max_reprojection_error_px"], dtype=np.float64
            ),
        }
    lengths = {
        len(detail[key])
        for key in ("world", "pixels_a", "pixels_b", "max_error")
    }
    if lengths != {int(detail["positive_depth_count"])}:
        raise RuntimeError(f"raw cache array-length mismatch: {rel(path)}")
    if not np.isfinite(detail["world"]).all():
        raise RuntimeError(f"raw cache has non-finite world points: {rel(path)}")
    return detail


def infer_pair(
    model: Any,
    job: dict[str, Any],
    pair: dict[str, Any],
    frame_inventories: dict[str, dict[str, Any]],
    box_a: Sequence[int],
    box_b: Sequence[int],
    device: str,
    inference_attempt: dict[str, bool],
) -> dict[str, Any]:
    started = time.monotonic()
    branch = camera_branch(pair)
    inventory = frame_inventories[branch]
    frames = inventory["frames"]
    frame_a = frames[pair["view_a"]]
    frame_b = frames[pair["view_b"]]
    if branch == C001_CAMERA_BRANCH:
        image_a, _rgb_a, _crop_k_a = base.prepare_view(
            frame_a, tuple(box_a), 0
        )
        image_b, _rgb_b, _crop_k_b = base.prepare_view(
            frame_b, tuple(box_b), 1
        )
    else:
        image_a = v2_mast3r.prepare_image(
            Path(frame_a["path"]), tuple(box_a), 0
        )
        image_b = v2_mast3r.prepare_image(
            Path(frame_b["path"]), tuple(box_b), 1
        )
    with torch.inference_mode():
        inference_attempt["started"] = True
        output = base.inference(
            [(image_a, image_b)],
            model,
            device,
            batch_size=1,
            verbose=False,
        )
    descriptor_a = output["pred1"]["desc"].squeeze(0).detach()
    descriptor_b = output["pred2"]["desc"].squeeze(0).detach()
    match_a, match_b = base.fast_reciprocal_NNs(
        descriptor_a,
        descriptor_b,
        subsample_or_initxy1=MATCH_SUBSAMPLE,
        device=device,
        dist="dot",
        block_size=2**13,
    )
    match_a = np.asarray(match_a, dtype=np.int64)
    match_b = np.asarray(match_b, dtype=np.int64)
    reciprocal_count = int(len(match_a))
    border = (
        (match_a[:, 0] >= MATCH_BORDER_PX)
        & (match_a[:, 0] < LOAD_WIDTH - MATCH_BORDER_PX)
        & (match_a[:, 1] >= MATCH_BORDER_PX)
        & (match_a[:, 1] < LOAD_HEIGHT - MATCH_BORDER_PX)
        & (match_b[:, 0] >= MATCH_BORDER_PX)
        & (match_b[:, 0] < LOAD_WIDTH - MATCH_BORDER_PX)
        & (match_b[:, 1] >= MATCH_BORDER_PX)
        & (match_b[:, 1] < LOAD_HEIGHT - MATCH_BORDER_PX)
    )
    match_a = match_a[border]
    match_b = match_b[border]
    if branch == C001_CAMERA_BRANCH:
        pixels_a = retri.original_pixels(match_a, tuple(box_a))
        pixels_b = retri.original_pixels(match_b, tuple(box_b))
        triangulated = retri.triangulate(
            pixels_a, pixels_b, frame_a, frame_b
        )
        finite = triangulated["finite"]
        keep = triangulated["cheirality"]
        world_all = triangulated["world_all"]
        max_error = triangulated["max_error"]
        centre_a = -frame_a["R"].T @ frame_a["t"]
        centre_b = -frame_b["R"].T @ frame_b["t"]
    else:
        pixels_a = v2_mast3r.source_pixels(match_a, tuple(box_a))
        pixels_b = v2_mast3r.source_pixels(match_b, tuple(box_b))
        camera_a = frame_a["camera"]
        camera_b = frame_b["camera"]
        triangulated = v2_mast3r.triangulate_full_opencv(
            pixels_a,
            pixels_b,
            camera_a,
            camera_b,
            inventory["camera_parameters"],
        )
        finite = triangulated["finite"]
        keep = triangulated["positive"]
        world_all = triangulated["world"]
        max_error = triangulated["max_error"]
        centre_a = -camera_a.rot.T @ camera_a.tvec
        centre_b = -camera_b.rot.T @ camera_b.tvec
    elapsed = time.monotonic() - started
    return {
        "building_id": job["building_id"],
        "pair_rank": int(pair["pair_rank"]),
        "view_a": pair["view_a"],
        "view_b": pair["view_b"],
        "crop_source": pair["crop_source"],
        **branch_provenance(pair),
        "crop_a_xyxy": list(box_a),
        "crop_b_xyxy": list(box_b),
        "known_colmap_baseline_m": float(
            np.linalg.norm(centre_a - centre_b)
        ),
        "reciprocal_match_count": reciprocal_count,
        "border_match_count": int(len(match_a)),
        "dlt_finite_count": int(np.count_nonzero(finite)),
        "positive_depth_count": int(np.count_nonzero(keep)),
        "world": world_all[keep],
        "pixels_a": pixels_a[keep],
        "pixels_b": pixels_b[keep],
        "max_error": max_error[keep],
        "pair_elapsed_seconds": elapsed,
    }


def load_footprints(
    wanted: set[str],
) -> dict[str, Polygon | MultiPolygon]:
    payload = json.loads(base.FOOTPRINTS.read_text(encoding="utf-8"))
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
    output: dict[str, Polygon | MultiPolygon] = {}
    for building_id in sorted(wanted):
        if not pieces.get(building_id):
            raise RuntimeError(f"missing footprint: {building_id}")
        geometry = make_valid(unary_union(pieces[building_id]))
        if (
            geometry.is_empty
            or not isinstance(geometry, (Polygon, MultiPolygon))
        ):
            raise RuntimeError(f"invalid footprint: {building_id}")
        output[building_id] = geometry
    return output


def pair_relation(detail: dict[str, Any]) -> tuple[str, str, str, bool]:
    block_a = acquisition_block(str(detail["view_a"]))
    block_b = acquisition_block(str(detail["view_b"]))
    relation = (
        "cross_acquisition_minute_block"
        if block_a != block_b
        else "same_acquisition_minute_block"
    )
    eligible = bool(
        block_a != block_b
        and float(detail["known_colmap_baseline_m"])
        > DEGENERATE_BASELINE_MAX_M
    )
    return block_a, block_b, relation, eligible


def score_pair(
    detail: dict[str, Any],
    footprint: Polygon | MultiPolygon,
    offset: np.ndarray,
    path: Path,
    pair_fp: str,
    fingerprint: str,
    new_inference: bool,
) -> dict[str, Any]:
    block_a, block_b, relation, eligible = pair_relation(detail)
    selected = detail["world"][
        detail["max_error"] <= REPROJECTION_THRESHOLD_PX
    ]
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
    return {
        "building_id": full_id(detail["building_id"]),
        "pair_rank": int(detail["pair_rank"]),
        "view_a": detail["view_a"],
        "view_b": detail["view_b"],
        "crop_source": detail["crop_source"],
        "camera_branch": detail["camera_branch"],
        "frame_source": detail["frame_source"],
        "camera_model": detail["camera_model"],
        "camera_source": detail["camera_source"],
        "pose_source": detail["pose_source"],
        "scene_reference_source": detail["scene_reference_source"],
        "world_frame": detail["world_frame"],
        "triangulation_rule": detail["triangulation_rule"],
        "crop_a_xyxy": ";".join(map(str, detail["crop_a_xyxy"])),
        "crop_b_xyxy": ";".join(map(str, detail["crop_b_xyxy"])),
        "acquisition_block_a": block_a,
        "acquisition_block_b": block_b,
        "pair_relation": relation,
        "known_colmap_baseline_m": detail["known_colmap_baseline_m"],
        "eligible_summary_pair": eligible,
        "status": "complete" if eligible else "excluded_pair",
        "failure_reason": (
            ""
            if eligible
            else (
                "same_acquisition_minute_block"
                if block_a == block_b
                else f"baseline<={DEGENERATE_BASELINE_MAX_M:.2f}m"
            )
        ),
        "reciprocal_match_count": detail["reciprocal_match_count"],
        "border_match_count": detail["border_match_count"],
        "dlt_finite_count": detail["dlt_finite_count"],
        "positive_depth_count": detail["positive_depth_count"],
        "reprojection_2px_count": len(selected),
        "footprint_inside_count": len(inside),
        "inside_z_median_m": z_median,
        "inside_z_mad_m": z_mad,
        "inside_z_median_local_m": z_median,
        "inside_z_mad_local_m": z_mad,
        "elapsed_seconds": detail["pair_elapsed_seconds"],
        "cache_path": rel(path),
        "cache_sha256": sha256_file(path),
        "new_mast3r_inference_runs": int(new_inference),
        "cache_reuse_runs": int(not new_inference),
        "learning_runs_started": 0,
        "new_inference_type": NEW_INFERENCE_TYPE,
        "pair_fingerprint": pair_fp,
        "input_fingerprint": fingerprint,
        "_selected": selected,
        "_inside": inside,
    }


def pending_pair_row(
    job: dict[str, Any],
    pair: dict[str, Any],
    pair_fp: str,
    fingerprint: str,
    status: str,
    failure_reason: str,
) -> dict[str, Any]:
    return {
        "building_id": job["building_id"],
        "priority_rank": job["priority_rank"],
        "pair_rank": pair["pair_rank"],
        "view_a": pair["view_a"],
        "view_b": pair["view_b"],
        "crop_source": pair["crop_source"],
        **branch_provenance(pair),
        "crop_a_xyxy": (
            ";".join(map(str, pair["crop_a_xyxy"]))
            if pair["crop_a_xyxy"] is not None
            else ""
        ),
        "crop_b_xyxy": (
            ";".join(map(str, pair["crop_b_xyxy"]))
            if pair["crop_b_xyxy"] is not None
            else ""
        ),
        "status": status,
        "failure_reason": failure_reason,
        "new_mast3r_inference_runs": 0,
        "cache_reuse_runs": 0,
        "elapsed_seconds": 0.0,
        "learning_runs_started": 0,
        "new_inference_type": NEW_INFERENCE_TYPE,
        "pair_fingerprint": pair_fp,
        "input_fingerprint": fingerprint,
    }


def sparse_fields(
    building_id: str, inventory: dict[str, dict[str, str]]
) -> dict[str, Any]:
    if building_id not in inventory:
        raise RuntimeError(f"missing sparse v2 reference: {building_id}")
    sparse = inventory[building_id]
    return {
        "sparse_v2_status": sparse["fm_status"],
        "sparse_v2_selected_dlt_point_count": sparse[
            "fm_reprojection_pass_count"
        ],
        "sparse_v2_footprint_inside_point_count": sparse[
            "fm_correspondence_count"
        ],
        "sparse_v2_inside_z_median_m": sparse["fm_z_median_m"],
        "sparse_v2_inside_z_mad_m": sparse["fm_z_mad_m"],
        "sparse_v2_score": sparse["fm_score"],
        "sparse_v2_reference_json": json.dumps(
            sparse, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ),
    }


def score_building(
    job: dict[str, Any],
    pair_rows: Sequence[dict[str, Any]],
    footprint: Polygon | MultiPolygon,
    offset: np.ndarray,
    sparse_inventory: dict[str, dict[str, str]],
    fingerprint: str,
    building_elapsed_this_invocation: float,
) -> dict[str, Any]:
    complete_rows = [
        row
        for row in pair_rows
        if row.get("status") in {"complete", "excluded_pair"}
    ]
    eligible_rows = [
        row for row in complete_rows if bool(row["eligible_summary_pair"])
    ]
    selected_parts = [row["_selected"] for row in eligible_rows]
    inside_parts = [row["_inside"] for row in eligible_rows]
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
    coverage = rescore.grid_coverage(
        inside, footprint, offset, COVERAGE_GRID_M
    )
    prerequisite_missing = [
        row
        for row in pair_rows
        if row.get("status") == "prerequisite_missing"
    ]
    failed = [
        row
        for row in pair_rows
        if row.get("status") in {"failed", "prerequisite_missing"}
    ]
    pending = [row for row in pair_rows if row.get("status") == "pending"]
    no_eligible_summary_pair = bool(
        not failed and not pending and not eligible_rows
    )
    measurement_complete = bool(
        not failed and not pending and eligible_rows
    )
    if pending:
        status = "partial_time_budget"
    elif prerequisite_missing and len(prerequisite_missing) == len(failed):
        status = "prerequisite_missing"
    elif failed:
        status = "partial_with_failures"
    elif no_eligible_summary_pair:
        status = "ineligible_no_summary_pair"
    else:
        status = "complete"
    failure_reason = ";".join(
        [
            *[
                f"rank{row['pair_rank']}:{row.get('failure_reason', '')}"
                for row in failed
            ],
            *(["pending_pairs=" + str(len(pending))] if pending else []),
            *(
                ["eligible_nondegenerate_completed_pairs=0"]
                if no_eligible_summary_pair
                else []
            ),
        ]
    )
    expected = REPRODUCTION_EXPECTED.get(job["building_id"])
    reproduction_passed: bool | None = None
    if expected is not None and measurement_complete:
        reproduction_passed = bool(
            len(selected) == expected["selected_dlt_point_count"]
            and len(inside) == expected["footprint_inside_point_count"]
            and z_median is not None
            and abs(float(z_median) - expected["inside_z_median_m"])
            <= 5e-7
        )
        if not reproduction_passed:
            raise RuntimeError(
                f"{job['building_id']} S3Ap 2px reproduction drift: "
                f"selected={len(selected)} expected="
                f"{expected['selected_dlt_point_count']}; "
                f"inside={len(inside)} expected="
                f"{expected['footprint_inside_point_count']}; "
                f"z={z_median} expected={expected['inside_z_median_m']}"
            )
    elapsed_total = sum(
        float(row.get("elapsed_seconds") or 0.0) for row in complete_rows
    )
    row = {
        "building_id": job["building_id"],
        "priority_rank": job["priority_rank"],
        "priority_group": job["priority_group"],
        "primary_assignment": job["primary_assignment"],
        "queue_inclusion_reason": job["queue_inclusion_reason"],
        "status": status,
        "failure_reason": failure_reason,
        "measurement_complete": measurement_complete,
        "selected_dlt_point_count": len(selected),
        "footprint_inside_point_count": len(inside),
        "inside_z_median_m": z_median,
        "inside_z_mad_m": z_mad,
        "inside_z_median_local_m": z_median,
        "inside_z_mad_local_m": z_mad,
        "coverage_grid_m": coverage["coverage_grid_m"],
        "coverage_eligible_cell_count": coverage[
            "coverage_eligible_cell_count"
        ],
        "coverage_occupied_cell_count": coverage[
            "coverage_occupied_cell_count"
        ],
        "coverage_ratio": coverage["coverage_ratio"],
        "selected_pair_count": len(pair_rows),
        "completed_pair_count": len(complete_rows),
        "eligible_pair_count": len(eligible_rows),
        "nonzero_inside_pair_count": sum(
            int(row["footprint_inside_count"]) > 0 for row in eligible_rows
        ),
        "failed_pair_count": len(failed),
        "pending_pair_count": len(pending),
        "reciprocal_match_count": sum(
            int(row["reciprocal_match_count"]) for row in eligible_rows
        ),
        "border_match_count": sum(
            int(row["border_match_count"]) for row in eligible_rows
        ),
        "dlt_finite_count": sum(
            int(row["dlt_finite_count"]) for row in eligible_rows
        ),
        "positive_depth_count": sum(
            int(row["positive_depth_count"]) for row in eligible_rows
        ),
        "reprojection_2px_count": len(selected),
        "crop_source_inventory": "|".join(
            sorted({str(row["crop_source"]) for row in pair_rows})
        ),
        "camera_branch_inventory": "|".join(
            sorted({str(row["camera_branch"]) for row in pair_rows})
        ),
        "frame_source_inventory": "|".join(
            sorted({str(row["frame_source"]) for row in pair_rows})
        ),
        "camera_model_inventory": "|".join(
            sorted({str(row["camera_model"]) for row in pair_rows})
        ),
        "world_frame_inventory": "|".join(
            sorted({str(row["world_frame"]) for row in pair_rows})
        ),
        "triangulation_rule_inventory": "|".join(
            sorted({str(row["triangulation_rule"]) for row in pair_rows})
        ),
        **sparse_fields(job["building_id"], sparse_inventory),
        "reproduction_check_required": expected is not None,
        "reproduction_expected_selected_dlt_point_count": (
            expected["selected_dlt_point_count"] if expected else None
        ),
        "reproduction_expected_footprint_inside_point_count": (
            expected["footprint_inside_point_count"] if expected else None
        ),
        "reproduction_expected_inside_z_median_m": (
            expected["inside_z_median_m"] if expected else None
        ),
        "reproduction_check_passed": reproduction_passed,
        "elapsed_seconds": elapsed_total,
        "elapsed_seconds_this_invocation": building_elapsed_this_invocation,
        "completed_utc": now() if measurement_complete else "",
        "model_id": MODEL_ID,
        "model_revision": MODEL_REVISION,
        "model_sha256": MODEL_SHA256,
        "docker_image_id": DOCKER_IMAGE_ID,
        "raw_definition": RAW_DEFINITION,
        "match_rule": MATCH_RULE,
        "triangulation_rule": TRIANGULATION_RULE,
        "pooling_rule": POOLING_RULE,
        "footprint_role": FOOTPRINT_ROLE,
        "lod2_role": LOD2_ROLE,
        "crs": "EPSG:25832",
        "new_mast3r_inference_runs": sum(
            int(row.get("new_mast3r_inference_runs", 0))
            for row in pair_rows
        ),
        "cache_reuse_runs": sum(
            int(row.get("cache_reuse_runs", 0)) for row in pair_rows
        ),
        "learning_runs_started": 0,
        "new_inference_type": NEW_INFERENCE_TYPE,
        "job_sha256": job["job_sha256"],
        "input_fingerprint": fingerprint,
    }
    return row


def public_pair_rows(
    rows: Sequence[dict[str, Any]]
) -> list[dict[str, Any]]:
    return [
        {key: row.get(key) for key in PAIR_FIELDS}
        for row in sorted(
            rows,
            key=lambda item: (
                int(item.get("priority_rank") or 0),
                int(item.get("pair_rank") or 0),
            ),
        )
    ]


def update_progress(
    jobs: Sequence[dict[str, Any]],
    building_rows: Sequence[dict[str, Any]],
    pair_rows: Sequence[dict[str, Any]],
    fingerprint: str,
    started_monotonic: float,
    max_seconds: float,
    finalization_reserve_seconds: float,
    active: dict[str, Any] | None,
    status: str,
) -> None:
    complete_ids = {
        row["building_id"]
        for row in building_rows
        if bool(row.get("measurement_complete"))
    }
    incomplete = [
        {
            "building_id": row["building_id"],
            "status": row["status"],
            "failed_pair_count": row["failed_pair_count"],
            "pending_pair_count": row["pending_pair_count"],
            "elapsed_seconds": row["elapsed_seconds"],
            "elapsed_seconds_this_invocation": row[
                "elapsed_seconds_this_invocation"
            ],
            "failure_reason": row["failure_reason"],
        }
        for row in building_rows
        if not bool(row.get("measurement_complete"))
    ]
    recorded_buildings = {row["building_id"] for row in building_rows}
    incomplete.extend(
        {
            "building_id": job["building_id"],
            "status": "not_started",
            "failed_pair_count": 0,
            "pending_pair_count": len(job["pairs"]),
            "elapsed_seconds": 0.0,
            "elapsed_seconds_this_invocation": 0.0,
            "failure_reason": "not_started",
        }
        for job in jobs
        if job["building_id"] not in recorded_buildings
    )
    payload = {
        "schema": "jointbuildgs.boundary_map_v3.fm_dense.progress.v1",
        "run_id": RUN_ID,
        "updated_utc": now(),
        "status": status,
        "input_fingerprint": fingerprint,
        "max_seconds": max_seconds,
        "finalization_reserve_seconds": finalization_reserve_seconds,
        "elapsed_seconds_this_invocation": (
            time.monotonic() - started_monotonic
        ),
        "target_building_count": len(jobs),
        "complete_building_count": len(complete_ids),
        "completed_building_ids": sorted(complete_ids),
        "incomplete_building_count": len(jobs) - len(complete_ids),
        "incomplete_building_ids": sorted(
            item["building_id"] for item in incomplete
        ),
        "target_pair_count": sum(len(job["pairs"]) for job in jobs),
        "complete_or_excluded_pair_count": sum(
            row.get("status") in {"complete", "excluded_pair"}
            for row in pair_rows
        ),
        "failed_pair_count": sum(
            row.get("status") in {"failed", "prerequisite_missing"}
            for row in pair_rows
        ),
        "prerequisite_missing_pair_count": sum(
            row.get("status") == "prerequisite_missing"
            for row in pair_rows
        ),
        "pending_pair_count": sum(
            row.get("status") == "pending" for row in pair_rows
        ),
        "new_mast3r_inference_runs": sum(
            int(row.get("new_mast3r_inference_runs", 0))
            for row in pair_rows
        ),
        "cache_reuse_runs": sum(
            int(row.get("cache_reuse_runs", 0)) for row in pair_rows
        ),
        "active": active,
        "incomplete_buildings": incomplete,
        "learning_runs_started": 0,
        "new_inference_type": NEW_INFERENCE_TYPE,
    }
    atomic_json(PROGRESS, payload)


def output_hashes() -> dict[str, str]:
    paths = [
        BUILDING_CSV,
        PAIR_CSV,
        PROGRESS,
        RUN_LOG,
        *sorted(RAW_DIR.glob("*.npz")),
    ]
    return {rel(path): sha256_file(path) for path in paths if path.is_file()}


def write_manifest(
    jobs_path: Path,
    jobs: Sequence[dict[str, Any]],
    building_rows: Sequence[dict[str, Any]],
    pair_rows: Sequence[dict[str, Any]],
    source_hashes: dict[str, str],
    fingerprint: str,
    environment: dict[str, Any],
    commits: dict[str, str],
    max_seconds: float,
    finalization_reserve_seconds: float,
    started_monotonic: float,
    final_status: str,
) -> None:
    pair_camera_branch_counts = {
        branch: sum(
            row.get("camera_branch") == branch for row in pair_rows
        )
        for branch in (C001_CAMERA_BRANCH, P0_CAMERA_BRANCH)
    }
    building_camera_branch_inventory = {
        row["building_id"]: row["camera_branch_inventory"]
        for row in building_rows
    }
    reproduction_rows = [
        {
            "building_id": row["building_id"],
            "selected_dlt_point_count": row[
                "selected_dlt_point_count"
            ],
            "expected_selected_dlt_point_count": row[
                "reproduction_expected_selected_dlt_point_count"
            ],
            "footprint_inside_point_count": row[
                "footprint_inside_point_count"
            ],
            "expected_footprint_inside_point_count": row[
                "reproduction_expected_footprint_inside_point_count"
            ],
            "inside_z_median_m": row["inside_z_median_m"],
            "expected_inside_z_median_m": row[
                "reproduction_expected_inside_z_median_m"
            ],
            "passed": row["reproduction_check_passed"],
        }
        for row in building_rows
        if bool(row.get("reproduction_check_required"))
    ]
    incomplete = [
        {
            "building_id": row["building_id"],
            "status": row["status"],
            "failed_pair_count": row["failed_pair_count"],
            "pending_pair_count": row["pending_pair_count"],
            "elapsed_seconds": row["elapsed_seconds"],
            "elapsed_seconds_this_invocation": row[
                "elapsed_seconds_this_invocation"
            ],
            "failure_reason": row["failure_reason"],
        }
        for row in building_rows
        if not bool(row["measurement_complete"])
    ]
    complete_ids = sorted(
        row["building_id"]
        for row in building_rows
        if bool(row["measurement_complete"])
    )
    prerequisite_missing_ids = sorted(
        row["building_id"]
        for row in building_rows
        if row["status"] == "prerequisite_missing"
    )
    prerequisite_failures = [
        {
            "building_id": row["building_id"],
            "pair_rank": row["pair_rank"],
            "view_a": row["view_a"],
            "view_b": row["view_b"],
            "crop_source": row["crop_source"],
            "failure_reason": row["failure_reason"],
        }
        for row in pair_rows
        if row.get("status") == "prerequisite_missing"
    ]
    raw_hashes = {
        key: value
        for key, value in output_hashes().items()
        if key.startswith(rel(RAW_DIR) + "/")
    }
    manifest = {
        "schema": "jointbuildgs.boundary_map_v3.fm_dense.manifest.v1",
        "run_id": RUN_ID,
        "created_utc": now(),
        "status": final_status,
        "git_head_at_measurement": git_value("rev-parse", "HEAD"),
        "branch": git_value("branch", "--show-current"),
        "jobs": rel(jobs_path),
        "input_fingerprint": fingerprint,
        "budget": {
            "maximum_seconds": max_seconds,
            "locked_upper_bound_seconds": MAX_BUDGET_SECONDS,
            "finalization_reserve_seconds": finalization_reserve_seconds,
            "elapsed_seconds_this_invocation": (
                time.monotonic() - started_monotonic
            ),
        },
        "runtime_lock": {
            "docker_image_tag": DOCKER_IMAGE_TAG,
            "docker_image_id": DOCKER_IMAGE_ID,
            "model_id": MODEL_ID,
            "model_revision": MODEL_REVISION,
            "weights_sha256": MODEL_SHA256,
            "weights_bytes": MODEL_BYTES,
            "config_sha256": MODEL_CONFIG_SHA256,
            "environment_manifest": rel(ENV_MANIFEST),
            "environment_manifest_sha256": ENV_MANIFEST_SHA256,
            "mast3r_commit": commits["mast3r"],
            "dust3r_commit": commits["dust3r"],
            "croco_commit": commits["croco"],
            "python": environment["runtime_lock"]["python"],
            "torch": environment["runtime_lock"]["torch"],
            "torch_cuda": environment["runtime_lock"]["torch_cuda"],
        },
        "kernel": {
            "raw_definition": RAW_DEFINITION,
            "source_specific_raw_definition": (
                SOURCE_SPECIFIC_RAW_DEFINITION
            ),
            "match_rule": MATCH_RULE,
            "triangulation_rule": TRIANGULATION_RULE,
            "summary_pair_rule": POOLING_RULE,
            "coverage": {
                "grid_m": COVERAGE_GRID_M,
                "denominator": (
                    "EPSG:25832 cells whose closed square intersects the "
                    "supplied footprint"
                ),
                "numerator": (
                    "eligible denominator cells containing at least one "
                    "footprint-inside selected DLT point"
                ),
            },
        },
        "camera_branches": {
            C001_CAMERA_BRANCH: {
                "camera_model": "PINHOLE",
                "frame_source": rel(base.IMAGE_DIR),
                "camera_source": rel(
                    base.SPARSE_DIR / "cameras.bin"
                ),
                "pose_source": rel(base.SPARSE_DIR / "images.bin"),
                "scene_reference_source": None,
                "world_frame": WORLD_FRAME,
                "triangulation_rule": C001_TRIANGULATION_RULE,
                "crop_source": "s3ap_locked_or_frozen_region",
                "addressed_pair_count": pair_camera_branch_counts[
                    C001_CAMERA_BRANCH
                ],
            },
            P0_CAMERA_BRANCH: {
                "camera_model": "FULL_OPENCV",
                "frame_source": rel(P0_IMAGE_DIR),
                "camera_source": rel(P0_CAMERAS),
                "pose_source": rel(P0_IMAGES),
                "scene_reference_source": rel(P0_SCENE_REFERENCE),
                "projection_datum_config": rel(P0_PROJECTION_CONFIG),
                "world_frame": WORLD_FRAME,
                "triangulation_rule": P0_TRIANGULATION_RULE,
                "crop_source": "projected_footprint",
                "addressed_pair_count": pair_camera_branch_counts[
                    P0_CAMERA_BRANCH
                ],
                "same_stem_c001_fallback_allowed": False,
            },
        },
        "camera_branch_counts": pair_camera_branch_counts,
        "building_camera_branch_inventory": (
            building_camera_branch_inventory
        ),
        "coordinate_frame": {
            "world_frame": WORLD_FRAME,
            "stored_xyz": (
                "fixed-COLMAP canonical local coordinates for both camera "
                "branches"
            ),
            "footprint_xy": (
                "EPSG:25832 XY = canonical local XY + locked C001 "
                "world_offset XY"
            ),
            "stored_z": (
                "ellipsoidal canonical local z; no geoid subtraction"
            ),
            "p0_scene_transform_equals_negative_c001_world_offset": True,
        },
        "reused_p0_code": {
            "full_opencv_kernel": {
                "path": rel(V2_MAST3R_SCRIPT),
                "sha256": source_hashes[rel(V2_MAST3R_SCRIPT)],
                "functions": [
                    "source_pixels",
                    "camera_model_name",
                    "triangulate_full_opencv",
                ],
            },
            "pose_and_frame_conversion": {
                "path": rel(P0_AUX_SCRIPT),
                "sha256": source_hashes[rel(P0_AUX_SCRIPT)],
                "functions": [
                    "parse_cam_model",
                    "parse_cameras",
                    "canonical_to_base",
                ],
            },
            "projection_datum": {
                "path": rel(P0_DATUM_SCRIPT),
                "sha256": source_hashes[rel(P0_DATUM_SCRIPT)],
                "config": rel(P0_PROJECTION_CONFIG),
                "config_sha256": source_hashes[
                    rel(P0_PROJECTION_CONFIG)
                ],
            },
        },
        "reference_role_separation": {
            "crop_sources_allowed": [
                "s3ap_locked_or_frozen_region",
                "projected_footprint",
            ],
            "s3ap_locked_or_frozen_region": (
                "frozen S3Ap semantic-region address; metadata can derive "
                "from locked oracle/raycast building classification"
            ),
            "projected_footprint": (
                "job-supplied reference-projection crop address"
            ),
            "fixed_pose_dlt": (
                "uses only reciprocal image coordinates and the locked "
                "source camera: C001 PINHOLE K[R|t], or P0 FULL_OPENCV "
                "undistortion plus fixed [R|t] and original-distortion "
                "source-pixel reprojection"
            ),
            "footprint": FOOTPRINT_ROLE,
            "lod2": LOD2_ROLE,
        },
        "priority": {
            "locked_manual_textureless_prefix": LOCKED_PRIORITY_PREFIX,
            "queue": [
                {
                    "building_id": job["building_id"],
                    "priority_rank": job["priority_rank"],
                    "priority_group": job["priority_group"],
                    "queue_inclusion_reason": job[
                        "queue_inclusion_reason"
                    ],
                }
                for job in jobs
            ],
        },
        "counts": {
            "target_buildings": len(jobs),
            "complete_buildings": sum(
                bool(row["measurement_complete"]) for row in building_rows
            ),
            "incomplete_buildings": len(incomplete),
            "target_pairs": sum(len(job["pairs"]) for job in jobs),
            "complete_or_excluded_pairs": sum(
                row.get("status") in {"complete", "excluded_pair"}
                for row in pair_rows
            ),
            "failed_pairs": sum(
                row.get("status") in {"failed", "prerequisite_missing"}
                for row in pair_rows
            ),
            "prerequisite_missing_pairs": sum(
                row.get("status") == "prerequisite_missing"
                for row in pair_rows
            ),
            "pending_pairs": sum(
                row.get("status") == "pending" for row in pair_rows
            ),
        },
        "completed_building_ids": complete_ids,
        "incomplete_building_ids": sorted(
            row["building_id"] for row in incomplete
        ),
        "prerequisite_missing_building_ids": prerequisite_missing_ids,
        "prerequisite_failures": prerequisite_failures,
        "incomplete_buildings": incomplete,
        "reproduction_check": reproduction_rows,
        "sparse_v2_reference_source": rel(V2_METRICS),
        "new_mast3r_inference_runs": sum(
            int(row.get("new_mast3r_inference_runs", 0))
            for row in pair_rows
        ),
        "cache_reuse_runs": sum(
            int(row.get("cache_reuse_runs", 0)) for row in pair_rows
        ),
        "learning_runs_started": 0,
        "new_inference_type": NEW_INFERENCE_TYPE,
        "resume_policy": (
            "valid pair caches with exact pair/input fingerprints are reused; "
            "building rows are deterministically reconstructed without new "
            "inference"
        ),
        "source_sha256": source_hashes,
        "raw_cache_sha256": raw_hashes,
        "output_sha256": output_hashes(),
        "interpretation_or_verdict": None,
        "no_seed_or_training_use": True,
    }
    atomic_json(MANIFEST, manifest)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Boundary-map v3 locked S3Ap FM dense measurement queue"
    )
    parser.add_argument("--model-dir", type=Path, required=True)
    parser.add_argument("--device", default="cuda:0")
    parser.add_argument("--max-seconds", type=float, default=MAX_BUDGET_SECONDS)
    parser.add_argument("--jobs", type=Path, default=JOBS)
    args = parser.parse_args()
    if not math.isfinite(args.max_seconds) or not (
        0 < args.max_seconds <= MAX_BUDGET_SECONDS
    ):
        raise RuntimeError(
            f"--max-seconds must be in (0,{MAX_BUDGET_SECONDS}]"
        )
    started_monotonic = time.monotonic()
    finalization_reserve_seconds = min(
        FINALIZATION_RESERVE_MAX_SECONDS, args.max_seconds * 0.02
    )
    deadline = (
        started_monotonic
        + args.max_seconds
        - finalization_reserve_seconds
    )
    jobs_path = args.jobs.resolve()
    if not jobs_path.is_file():
        raise RuntimeError(f"missing jobs JSON: {jobs_path}")
    jobs_payload = json.loads(jobs_path.read_text(encoding="utf-8"))
    _model_job, jobs = normalize_jobs(jobs_payload)
    environment, _weights, commits = verify_environment(
        args.model_dir.resolve(), args.device
    )
    offset = base.load_offset()
    frame_inventories = load_frames_for_jobs(jobs, offset)
    sources = source_paths(
        jobs_path,
        jobs,
        frame_inventories,
        args.model_dir.resolve(),
        environment,
    )
    source_hashes = {rel(path): sha256_file(path) for path in sources}
    fingerprint = input_fingerprint(jobs_payload, source_hashes)
    footprints = load_footprints(
        {job["building_id"] for job in jobs}
    )
    sparse_inventory = load_sparse_v2()

    RUN_DIR.mkdir(parents=True, exist_ok=True)
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    log(
        "START boundary_map_v3_fm_dense "
        f"buildings={len(jobs)} pairs="
        f"{sum(len(job['pairs']) for job in jobs)} "
        f"max_seconds={args.max_seconds:.3f} "
        "learning_runs_started=0 new_inference=R1prime-3"
    )
    building_rows: list[dict[str, Any]] = []
    all_pair_rows: list[dict[str, Any]] = []
    model = None

    for job in jobs:
        building_started = time.monotonic()
        local_rows: list[dict[str, Any]] = []
        for pair in job["pairs"]:
            branch = camera_branch(pair)
            frames = frame_inventories[branch]["frames"]
            missing_stems = sorted(
                {
                    pair[side]
                    for side in ("view_a", "view_b")
                    if pair[side] not in frames
                }
            )
            try:
                if missing_stems:
                    raise RuntimeError(
                        f"locked_camera_frame_missing:{branch}:"
                        + "|".join(missing_stems)
                    )
                box_a, box_b = crop_boxes(
                    job["building_id"], pair, frame_inventories
                )
            except (KeyError, OSError, RuntimeError, ValueError) as exc:
                provisional_a = pair.get("crop_a_xyxy") or []
                provisional_b = pair.get("crop_b_xyxy") or []
                pair_fp = pair_fingerprint(
                    job,
                    pair,
                    provisional_a,
                    provisional_b,
                    fingerprint,
                )
                row = pending_pair_row(
                    job,
                    pair,
                    pair_fp,
                    fingerprint,
                    "prerequisite_missing",
                    f"{type(exc).__name__}: {exc}",
                )
                row["priority_rank"] = job["priority_rank"]
                local_rows.append(row)
                log(
                    f"PAIR_PREREQUISITE_MISSING "
                    f"building={job['building_id']} "
                    f"rank={pair['pair_rank']} "
                    f"reason={row['failure_reason']}"
                )
                atomic_csv(
                    PAIR_CSV,
                    public_pair_rows([*all_pair_rows, *local_rows]),
                    PAIR_FIELDS,
                )
                update_progress(
                    jobs,
                    building_rows,
                    [*all_pair_rows, *local_rows],
                    fingerprint,
                    started_monotonic,
                    args.max_seconds,
                    finalization_reserve_seconds,
                    None,
                    "running",
                )
                continue
            pair_fp = pair_fingerprint(
                job, pair, box_a, box_b, fingerprint
            )
            path = cache_path(job["building_id"], int(pair["pair_rank"]))
            new_inference = False
            inference_attempt = {"started": False}
            active = {
                "building_id": job["building_id"],
                "pair_rank": pair["pair_rank"],
                "camera_branch": branch,
                "started_utc": now(),
            }
            if path.is_file():
                detail = load_cache(path, pair_fp, fingerprint)
                row = score_pair(
                    detail,
                    footprints[job["building_id"]],
                    offset,
                    path,
                    pair_fp,
                    fingerprint,
                    new_inference=False,
                )
                log(
                    f"PAIR_CACHE_REUSED building={job['building_id']} "
                    f"rank={pair['pair_rank']} cache={rel(path)}"
                )
            elif time.monotonic() >= deadline:
                row = pending_pair_row(
                    job,
                    pair,
                    pair_fp,
                    fingerprint,
                    "pending",
                    "global_6h_budget_reached",
                )
            else:
                update_progress(
                    jobs,
                    building_rows,
                    [*all_pair_rows, *local_rows],
                    fingerprint,
                    started_monotonic,
                    args.max_seconds,
                    finalization_reserve_seconds,
                    active,
                    "running",
                )
                try:
                    if model is None:
                        model = (
                            base.AsymmetricMASt3R.from_pretrained(
                                str(args.model_dir.resolve())
                            )
                            .to(args.device)
                            .eval()
                        )
                    detail = infer_pair(
                        model,
                        job,
                        pair,
                        frame_inventories,
                        box_a,
                        box_b,
                        args.device,
                        inference_attempt,
                    )
                    new_inference = inference_attempt["started"]
                    save_cache(path, detail, pair_fp, fingerprint)
                    row = score_pair(
                        detail,
                        footprints[job["building_id"]],
                        offset,
                        path,
                        pair_fp,
                        fingerprint,
                        new_inference=True,
                    )
                    log(
                        f"PAIR_DONE building={job['building_id']} "
                        f"rank={pair['pair_rank']} "
                        f"camera_branch={branch} "
                        f"raw={row['reciprocal_match_count']} "
                        f"positive={row['positive_depth_count']} "
                        f"n2={row['reprojection_2px_count']} "
                        f"inside={row['footprint_inside_count']} "
                        f"eligible={row['eligible_summary_pair']} "
                        f"elapsed_s={row['elapsed_seconds']:.3f}"
                    )
                except Exception as exc:
                    new_inference = inference_attempt["started"]
                    row = pending_pair_row(
                        job,
                        pair,
                        pair_fp,
                        fingerprint,
                        "failed",
                        f"{type(exc).__name__}: {exc}",
                    )
                    row["new_mast3r_inference_runs"] = int(new_inference)
                    log(
                        f"PAIR_FAILED building={job['building_id']} "
                        f"rank={pair['pair_rank']} "
                        f"reason={row['failure_reason']}"
                    )
            row["priority_rank"] = job["priority_rank"]
            local_rows.append(row)
            atomic_csv(
                PAIR_CSV,
                public_pair_rows([*all_pair_rows, *local_rows]),
                PAIR_FIELDS,
            )
            update_progress(
                jobs,
                building_rows,
                [*all_pair_rows, *local_rows],
                fingerprint,
                started_monotonic,
                args.max_seconds,
                finalization_reserve_seconds,
                None,
                "running",
            )
        building_row = score_building(
            job,
            local_rows,
            footprints[job["building_id"]],
            offset,
            sparse_inventory,
            fingerprint,
            time.monotonic() - building_started,
        )
        building_rows.append(building_row)
        all_pair_rows.extend(local_rows)
        atomic_csv(BUILDING_CSV, building_rows, BUILDING_FIELDS)
        atomic_csv(PAIR_CSV, public_pair_rows(all_pair_rows), PAIR_FIELDS)
        log(
            f"BUILDING_RECORDED building={job['building_id']} "
            f"status={building_row['status']} "
            f"selected={building_row['selected_dlt_point_count']} "
            f"inside={building_row['footprint_inside_point_count']} "
            f"z={building_row['inside_z_median_m']} "
            f"pending={building_row['pending_pair_count']} "
            f"failed={building_row['failed_pair_count']} "
            f"elapsed_s={building_row['elapsed_seconds']:.3f}"
        )

    complete = all(
        bool(row["measurement_complete"]) for row in building_rows
    )
    budget_exhausted = any(
        int(row["pending_pair_count"]) > 0 for row in building_rows
    )
    final_status = (
        "complete"
        if complete
        else ("budget_exhausted" if budget_exhausted else "partial")
    )
    log(
        f"FINAL status={final_status} buildings={len(building_rows)} "
        f"complete={sum(bool(row['measurement_complete']) for row in building_rows)} "
        f"pairs={len(all_pair_rows)} "
        f"new_inference={sum(int(row.get('new_mast3r_inference_runs', 0)) for row in all_pair_rows)} "
        "learning_runs_started=0"
    )
    atomic_csv(BUILDING_CSV, building_rows, BUILDING_FIELDS)
    atomic_csv(PAIR_CSV, public_pair_rows(all_pair_rows), PAIR_FIELDS)
    update_progress(
        jobs,
        building_rows,
        all_pair_rows,
        fingerprint,
        started_monotonic,
        args.max_seconds,
        finalization_reserve_seconds,
        None,
        final_status,
    )
    write_manifest(
        jobs_path,
        jobs,
        building_rows,
        all_pair_rows,
        source_hashes,
        fingerprint,
        environment,
        commits,
        args.max_seconds,
        finalization_reserve_seconds,
        started_monotonic,
        final_status,
    )


if __name__ == "__main__":
    main()
