#!/usr/bin/env python3
"""R1 boundary-map v2 isolated MASt3R measurement runner.

``crop-pair`` measures the fourteen requested projected-roof crop pairs.
``fm`` uses MASt3R only for reciprocal 2D correspondences, then performs
float64 DLT with the frozen COLMAP camera poses.  The global source camera is
FULL_OPENCV: crop pixels are mapped to raw pixels, undistorted for DLT, and
checked by reprojection in the original distorted pixel coordinates.

No optimizer, training loop, checkpoint write, or model-weight update is
present in this module.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib")
os.environ.setdefault("XDG_CACHE_HOME", "/tmp")

import cv2
import numpy as np
import torch
from PIL import Image as PILImage
from shapely.geometry import Point, shape
from shapely.ops import unary_union
from shapely.prepared import prep

import mast3r.utils.path_to_dust3r  # noqa: F401,E402
from dust3r.inference import inference  # noqa: E402
from dust3r.utils.image import ImgNorm  # noqa: E402
from mast3r.fast_nn import fast_reciprocal_NNs  # noqa: E402
from mast3r.model import AsymmetricMASt3R  # noqa: E402


REPO = Path(__file__).resolve().parents[3]
SCRIPT_DIR = Path(__file__).resolve().parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from scripts.evidence_and_attributes.population_analysis import population_aux_v3 as aux  # noqa: E402
from src.geospatial import projection_datum as datum  # noqa: E402


RUN_DIR = REPO / "phases/p2-gsjso/runs/boundary_and_robustness/20260718_boundary_map_v2"
CROP_JOBS = RUN_DIR / "crop_pair_jobs.json"
FM_JOBS = RUN_DIR / "fm_jobs.json"
CROP_RESULTS = RUN_DIR / "crop_pair_results.csv"
FM_RESULTS = RUN_DIR / "fm_retriangulation.csv"
CROP_PROGRESS = RUN_DIR / "crop_pair_progress.json"
FM_PROGRESS = RUN_DIR / "fm_progress.json"
CROP_MANIFEST = RUN_DIR / "crop_pair_manifest.json"
FM_MANIFEST = RUN_DIR / "fm_manifest.json"
CROP_LOG = RUN_DIR / "crop_pair.log"
FM_LOG = RUN_DIR / "fm.log"

FOOTPRINTS = REPO / "results/tum_transfer/analysis/footprints_aoi.geojson"
DATA = REPO / "phases/p0-audit/data"
IMAGE_DIR = DATA / "work/images/Images"
SCENE_REF = DATA / "work/opf/opf/scene_reference_frame.json"
CAMERAS = DATA / "work/colmap/sparse/0/cameras.txt"
IMAGES = DATA / "work/colmap/sparse/0/images.txt"
PROJECTION_DATUM = REPO / "configs/input_and_alignment/projection_datum.json"
ENV_MANIFEST = REPO / "docs/experiments/input-and-alignment/e5_c001_s3ap/manifests/e5_c001_s3ap_fm_env_manifest.json"
AUX_SCRIPT = REPO / "scripts/evidence_and_attributes/population_analysis/population_aux_v3.py"
DATUM_SCRIPT = REPO / "src/geospatial/projection_datum.py"

MODEL_REVISION = "06e7259f34c3060f322df5cb0c7b9094f57e41fc"
MODEL_SHA256 = "0a615eb05fa9db654050aa655945ee5696e7c6c1b7f93f1ee8c37249010f6feb"
MODEL_BYTES = 2_754_661_648
MODEL_CONFIG_SHA256 = "718eb93dc4f9e4332b60cc0041af962d712cbd346d7770ce35c5b22cff68eae4"
LOAD_WIDTH = 512
LOAD_HEIGHT = 384
MATCH_SUBSAMPLE = 8
MATCH_BORDER_PX = 3
REPROJECTION_THRESHOLD_PX = 2.0
DEGENERATE_BASELINE_MAX_M = 0.06

CROP_FIELDS = [
    "building_id", "priority_group", "priority_rank", "status",
    "failure_reason", "view_a", "view_b", "crop_a_xyxy", "crop_b_xyxy",
    "reciprocal_raw_count", "border_match_count", "roof_correspondence_count",
    "roof_correspondence_fraction_of_border", "model_revision",
    "model_sha256", "model_bytes", "match_rule",
    "projection_reference_height_used", "projection_reference_source",
    "elapsed_seconds", "completed_utc", "learning_runs_started",
    "new_inference_type", "job_sha256", "input_fingerprint",
]

FM_FIELDS = [
    "building_id", "priority_group", "priority_rank", "primary_assignment",
    "status", "failure_reason", "view_a", "view_b", "crop_a_xyxy",
    "crop_b_xyxy", "selected_pair_count", "completed_pair_count",
    "successful_pair_count", "excluded_pair_count", "failed_pair_count",
    "pending_pair_count",
    "baseline_m", "baseline_min_m", "baseline_median_m", "baseline_class",
    "reciprocal_raw_count", "border_match_count", "finite_dlt_count",
    "positive_depth_count", "reprojection_pass_count",
    "reprojection_pass_fraction_of_border",
    "reprojection_error_median_px", "footprint_inside_count",
    "footprint_inside_fraction_of_border", "footprint_z_median_m",
    "footprint_z_mad_m", "footprint_z_std_m", "model_revision",
    "model_sha256", "model_bytes", "match_rule", "triangulation_rule",
    "score_rule", "crs", "vertical_datum", "projection_geoid_m",
    "projection_datum_config", "projection_datum_config_sha256",
    "projection_reference_height_used",
    "projection_reference_source", "elapsed_seconds", "completed_utc",
    "pair_status_json", "pooling_rule",
    "learning_runs_started", "new_inference_type", "job_sha256",
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
            ["git", *args], cwd=REPO, text=True
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


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def fmt(value: Any) -> Any:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        return f"{value:.6f}" if math.isfinite(value) else ""
    return value


def atomic_csv(
    path: Path, rows: Sequence[dict[str, Any]], fields: Sequence[str]
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    with temporary.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=list(fields), extrasaction="ignore", lineterminator="\n"
        )
        writer.writeheader()
        writer.writerows([{key: fmt(row.get(key)) for key in fields} for row in rows])
    temporary.replace(path)


def atomic_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def log(path: Path, message: str) -> None:
    line = f"{now()} {message}"
    print(line, flush=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")


def verify_model(model_dir: Path, device: str) -> Path:
    weights = model_dir / "model.safetensors"
    config = model_dir / "config.json"
    if model_dir.name != MODEL_REVISION:
        raise RuntimeError(f"model revision mismatch: {model_dir.name}")
    if not weights.is_file() or weights.stat().st_size != MODEL_BYTES:
        raise RuntimeError("MASt3R model byte lock mismatch")
    if sha256_file(weights) != MODEL_SHA256:
        raise RuntimeError("MASt3R model SHA256 lock mismatch")
    if not config.is_file() or sha256_file(config) != MODEL_CONFIG_SHA256:
        raise RuntimeError("MASt3R model config SHA256 lock mismatch")
    environment = json.loads(ENV_MANIFEST.read_text(encoding="utf-8"))
    expected_image_id = environment.get("runtime_lock", {}).get(
        "docker_image_id"
    )
    actual_image_id = os.environ.get("MAST3R_DOCKER_IMAGE_ID", "")
    if (
        environment.get("model", {}).get("config_sha256")
        != MODEL_CONFIG_SHA256
        or environment.get("model", {}).get("weights_sha256")
        != MODEL_SHA256
    ):
        raise RuntimeError("S3Ap environment manifest model lock mismatch")
    if not actual_image_id or actual_image_id != expected_image_id:
        raise RuntimeError(
            "S3Ap Docker image ID mismatch: "
            f"actual={actual_image_id!r} expected={expected_image_id!r}"
        )
    if device.startswith("cuda") and not torch.cuda.is_available():
        raise RuntimeError("CUDA requested but unavailable")
    return weights


def prepare_image(
    path: Path, box: Sequence[int], index: int
) -> dict[str, Any]:
    with PILImage.open(path) as source:
        crop = source.convert("RGB").crop(tuple(box)).resize(
            (LOAD_WIDTH, LOAD_HEIGHT), PILImage.Resampling.LANCZOS
        )
    return {
        "img": ImgNorm(crop)[None],
        "true_shape": np.int32([[LOAD_HEIGHT, LOAD_WIDTH]]),
        "idx": index,
        "instance": str(index),
    }


def infer_matches(
    model: Any, job: dict[str, Any], device: str
) -> tuple[np.ndarray, np.ndarray, int, int]:
    image_a = prepare_image(REPO / job["image_a"], job["crop_a_xyxy"], 0)
    image_b = prepare_image(REPO / job["image_b"], job["crop_b_xyxy"], 1)
    with torch.inference_mode():
        output = inference(
            [(image_a, image_b)], model, device, batch_size=1, verbose=False
        )
    descriptor_a = output["pred1"]["desc"].squeeze(0).detach()
    descriptor_b = output["pred2"]["desc"].squeeze(0).detach()
    matches_a, matches_b = fast_reciprocal_NNs(
        descriptor_a,
        descriptor_b,
        subsample_or_initxy1=MATCH_SUBSAMPLE,
        device=device,
        dist="dot",
        block_size=2**13,
    )
    matches_a = np.asarray(matches_a, dtype=np.int64)
    matches_b = np.asarray(matches_b, dtype=np.int64)
    raw_count = int(len(matches_a))
    border = (
        (matches_a[:, 0] >= MATCH_BORDER_PX)
        & (matches_a[:, 0] < LOAD_WIDTH - MATCH_BORDER_PX)
        & (matches_a[:, 1] >= MATCH_BORDER_PX)
        & (matches_a[:, 1] < LOAD_HEIGHT - MATCH_BORDER_PX)
        & (matches_b[:, 0] >= MATCH_BORDER_PX)
        & (matches_b[:, 0] < LOAD_WIDTH - MATCH_BORDER_PX)
        & (matches_b[:, 1] >= MATCH_BORDER_PX)
        & (matches_b[:, 1] < LOAD_HEIGHT - MATCH_BORDER_PX)
    )
    return matches_a[border], matches_b[border], raw_count, int(np.count_nonzero(border))


def projected_mask(
    rings: Sequence[Sequence[Sequence[float]]], box: Sequence[int]
) -> np.ndarray:
    x0, y0, x1, y1 = [float(value) for value in box]
    scale_x = LOAD_WIDTH / max(x1 - x0, 1.0)
    scale_y = LOAD_HEIGHT / max(y1 - y0, 1.0)
    mask = np.zeros((LOAD_HEIGHT, LOAD_WIDTH), dtype=np.uint8)
    polygons = []
    for ring in rings:
        array = np.asarray(ring, dtype=np.float64)
        if len(array) < 3:
            continue
        output = array.copy()
        output[:, 0] = (output[:, 0] - x0) * scale_x
        output[:, 1] = (output[:, 1] - y0) * scale_y
        polygons.append(np.rint(output).astype(np.int32))
    if polygons:
        cv2.fillPoly(mask, polygons, 1)
    return mask.astype(bool)


def crop_measurement(
    model: Any, job: dict[str, Any], device: str
) -> dict[str, Any]:
    started = time.monotonic()
    matches_a, matches_b, raw_count, border_count = infer_matches(
        model, job, device
    )
    mask_a = projected_mask(job["projected_rings_a"], job["crop_a_xyxy"])
    mask_b = projected_mask(job["projected_rings_b"], job["crop_b_xyxy"])
    if not np.any(mask_a) or not np.any(mask_b):
        raise RuntimeError("projected roof mask empty after crop resize")
    inside = (
        mask_a[matches_a[:, 1], matches_a[:, 0]]
        & mask_b[matches_b[:, 1], matches_b[:, 0]]
    )
    roof_count = int(np.count_nonzero(inside))
    return {
        "building_id": job["building_id"],
        "priority_group": job.get("priority_group", "repair_14"),
        "priority_rank": job["priority_rank"],
        "status": "complete",
        "failure_reason": "",
        "view_a": job["view_a"],
        "view_b": job["view_b"],
        "crop_a_xyxy": ";".join(str(value) for value in job["crop_a_xyxy"]),
        "crop_b_xyxy": ";".join(str(value) for value in job["crop_b_xyxy"]),
        "reciprocal_raw_count": raw_count,
        "border_match_count": border_count,
        "roof_correspondence_count": roof_count,
        "roof_correspondence_fraction_of_border": (
            roof_count / border_count if border_count else 0.0
        ),
        "model_revision": MODEL_REVISION,
        "model_sha256": MODEL_SHA256,
        "model_bytes": MODEL_BYTES,
        "match_rule": (
            "reciprocal descriptor NN stride8; 3px crop border; "
            "both projected roof masks"
        ),
        "projection_reference_height_used": True,
        "projection_reference_source": job["projection_reference_source"],
        "elapsed_seconds": time.monotonic() - started,
        "completed_utc": now(),
        "learning_runs_started": 0,
        "new_inference_type": "R1-2 MASt3R crop-pair correspondence only",
    }


def source_pixels(matches: np.ndarray, box: Sequence[int]) -> np.ndarray:
    x0, y0, x1, y1 = [float(value) for value in box]
    output = matches.astype(np.float64).copy()
    output[:, 0] = x0 + output[:, 0] / (LOAD_WIDTH / (x1 - x0))
    output[:, 1] = y0 + output[:, 1] / (LOAD_HEIGHT / (y1 - y0))
    return output


def camera_matrices(params: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    if len(params) < 12:
        raise RuntimeError("FULL_OPENCV camera requires 12 parameters")
    fx, fy, cx, cy = params[:4]
    camera = np.asarray(
        [[fx, 0.0, cx], [0.0, fy, cy], [0.0, 0.0, 1.0]],
        dtype=np.float64,
    )
    distortion = np.asarray(
        [
            params[4], params[5], params[6], params[7],
            params[8], params[9], params[10], params[11],
        ],
        dtype=np.float64,
    )
    return camera, distortion


def camera_model_name(path: Path) -> str:
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            stripped = line.strip()
            if stripped and not stripped.startswith("#"):
                parts = stripped.split()
                return parts[1] if len(parts) > 1 else ""
    raise RuntimeError(f"no camera row in {path}")


def undistort(
    pixels: np.ndarray, camera: np.ndarray, distortion: np.ndarray
) -> np.ndarray:
    if not len(pixels):
        return np.zeros((0, 2), dtype=np.float64)
    return cv2.undistortPoints(
        pixels.reshape(-1, 1, 2), camera, distortion
    ).reshape(-1, 2)


def dlt_one(
    point_a: np.ndarray,
    point_b: np.ndarray,
    projection_a: np.ndarray,
    projection_b: np.ndarray,
) -> np.ndarray:
    matrix = np.stack(
        [
            point_a[0] * projection_a[2] - projection_a[0],
            point_a[1] * projection_a[2] - projection_a[1],
            point_b[0] * projection_b[2] - projection_b[0],
            point_b[1] * projection_b[2] - projection_b[1],
        ]
    )
    _u, _s, vt = np.linalg.svd(
        matrix.astype(np.float64), full_matrices=False
    )
    homogeneous = vt[-1]
    if not np.isfinite(homogeneous).all() or abs(homogeneous[3]) <= 1e-12:
        return np.full(3, np.nan, dtype=np.float64)
    return homogeneous[:3] / homogeneous[3]


def project_full_opencv(
    world: np.ndarray, frame: Any, params: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    camera_points = (frame.rot @ world.T).T + frame.tvec[None, :]
    pixels = np.full((len(world), 2), np.nan, dtype=np.float64)
    forward = camera_points[:, 2] > 1e-12
    if not np.any(forward):
        return pixels, camera_points[:, 2]
    fx, fy, cx, cy, k1, k2, p1, p2, k3, k4, k5, k6 = params[:12]
    x = camera_points[forward, 0] / camera_points[forward, 2]
    y = camera_points[forward, 1] / camera_points[forward, 2]
    r2 = x * x + y * y
    r4 = r2 * r2
    r6 = r4 * r2
    denominator = 1.0 + k4 * r2 + k5 * r4 + k6 * r6
    denominator = np.where(
        np.abs(denominator) < 1e-12, np.nan, denominator
    )
    radial = (1.0 + k1 * r2 + k2 * r4 + k3 * r6) / denominator
    xd = x * radial + 2.0 * p1 * x * y + p2 * (r2 + 2.0 * x * x)
    yd = y * radial + p1 * (r2 + 2.0 * y * y) + 2.0 * p2 * x * y
    pixels[forward, 0] = fx * xd + cx
    pixels[forward, 1] = fy * yd + cy
    return pixels, camera_points[:, 2]


def triangulate_full_opencv(
    raw_a: np.ndarray,
    raw_b: np.ndarray,
    frame_a: Any,
    frame_b: Any,
    params: np.ndarray,
) -> dict[str, np.ndarray]:
    camera, distortion = camera_matrices(params)
    normalized_a = undistort(raw_a, camera, distortion)
    normalized_b = undistort(raw_b, camera, distortion)
    projection_a = np.column_stack([frame_a.rot, frame_a.tvec])
    projection_b = np.column_stack([frame_b.rot, frame_b.tvec])
    if not len(normalized_a):
        world = np.zeros((0, 3), dtype=np.float64)
    else:
        world = np.stack(
            [
                dlt_one(left, right, projection_a, projection_b)
                for left, right in zip(normalized_a, normalized_b)
            ],
            axis=0,
        )
    finite = np.isfinite(world).all(axis=1)
    reprojection_a, depth_a = project_full_opencv(world, frame_a, params)
    reprojection_b, depth_b = project_full_opencv(world, frame_b, params)
    positive = finite & (depth_a > 0.0) & (depth_b > 0.0)
    error_a = np.linalg.norm(reprojection_a - raw_a, axis=1)
    error_b = np.linalg.norm(reprojection_b - raw_b, axis=1)
    max_error = np.maximum(error_a, error_b)
    reprojection = (
        positive
        & np.isfinite(max_error)
        & (max_error <= REPROJECTION_THRESHOLD_PX)
    )
    return {
        "world": world,
        "finite": finite,
        "positive": positive,
        "reprojection": reprojection,
        "max_error": max_error,
    }


def load_footprints() -> dict[str, Any]:
    payload = json.loads(FOOTPRINTS.read_text(encoding="utf-8"))
    pieces: dict[str, list[Any]] = {}
    for feature in payload["features"]:
        bid = str(feature["properties"]["building_id"])
        if not bid.startswith("DEBY_LOD2_"):
            bid = f"DEBY_LOD2_{bid}"
        geometry = shape(feature["geometry"])
        if not geometry.is_empty:
            pieces.setdefault(bid, []).append(geometry)
    return {bid: unary_union(values) for bid, values in pieces.items()}


def finite_stats(values: np.ndarray) -> tuple[float | None, float | None, float | None]:
    finite = np.asarray(values, dtype=np.float64)
    finite = finite[np.isfinite(finite)]
    if not len(finite):
        return None, None, None
    median = float(np.median(finite))
    return (
        median,
        float(np.median(np.abs(finite - median))),
        float(np.std(finite)),
    )


def fm_measurement(
    model: Any,
    job: dict[str, Any],
    device: str,
    frames: dict[str, Any],
    params: np.ndarray,
    scene_ref: dict[str, Any],
    footprints: dict[str, Any],
    geoid_m: float,
    deadline: float,
) -> dict[str, Any]:
    started = time.monotonic()
    prepared = prep(footprints[job["building_id"]])
    pairs = list(job.get("pairs", []))
    if not pairs:
        raise RuntimeError("FM building job has no projected-footprint pairs")
    pair_status: list[dict[str, Any]] = []
    pooled_z: list[np.ndarray] = []
    pooled_errors: list[np.ndarray] = []
    baselines: list[float] = []
    totals = {
        "raw": 0,
        "border": 0,
        "finite": 0,
        "positive": 0,
        "reprojection": 0,
        "inside": 0,
    }
    for pair in pairs:
        if time.monotonic() >= deadline:
            break
        pair_started = time.monotonic()
        detail: dict[str, Any] = {
            "pair_rank": int(pair["pair_rank"]),
            "view_a": pair["view_a"],
            "view_b": pair["view_b"],
        }
        try:
            matches_a, matches_b, raw_count, border_count = infer_matches(
                model, pair, device
            )
            frame_a = frames[pair["view_a"]]
            frame_b = frames[pair["view_b"]]
            centre_a = -frame_a.rot.T @ frame_a.tvec
            centre_b = -frame_b.rot.T @ frame_b.tvec
            baseline = float(np.linalg.norm(centre_a - centre_b))
            detail.update(
                {
                    "baseline_m": baseline,
                    "reciprocal_raw_count": raw_count,
                    "border_match_count": border_count,
                }
            )
            if baseline <= DEGENERATE_BASELINE_MAX_M:
                detail.update(
                    {
                        "status": "excluded_degenerate",
                        "failure_reason": (
                            f"baseline<={DEGENERATE_BASELINE_MAX_M:.2f}m"
                        ),
                        "elapsed_seconds": time.monotonic() - pair_started,
                    }
                )
                pair_status.append(detail)
                continue
            raw_a = source_pixels(matches_a, pair["crop_a_xyxy"])
            raw_b = source_pixels(matches_b, pair["crop_b_xyxy"])
            triangulated = triangulate_full_opencv(
                raw_a, raw_b, frame_a, frame_b, params
            )
            accepted = triangulated["reprojection"]
            world_canonical = triangulated["world"][accepted]
            world_base_ellipsoidal = (
                aux.canonical_to_base(world_canonical, scene_ref)
                if len(world_canonical)
                else np.zeros((0, 3), dtype=np.float64)
            )
            world_base = world_base_ellipsoidal.copy()
            if len(world_base):
                world_base[:, 2] -= geoid_m
            inside = np.asarray(
                [
                    prepared.covers(Point(float(x), float(y)))
                    for x, y in world_base[:, :2]
                ],
                dtype=bool,
            )
            inside_world = world_base[inside]
            accepted_errors = triangulated["max_error"][accepted]
            baselines.append(baseline)
            pooled_z.append(inside_world[:, 2])
            pooled_errors.append(accepted_errors)
            pair_inside = int(len(inside_world))
            pair_reprojection = int(np.count_nonzero(accepted))
            totals["raw"] += raw_count
            totals["border"] += border_count
            totals["finite"] += int(np.count_nonzero(triangulated["finite"]))
            totals["positive"] += int(np.count_nonzero(triangulated["positive"]))
            totals["reprojection"] += pair_reprojection
            totals["inside"] += pair_inside
            pair_z, _pair_mad, _pair_std = finite_stats(inside_world[:, 2])
            detail.update(
                {
                    "status": "complete",
                    "failure_reason": "",
                    "finite_dlt_count": int(
                        np.count_nonzero(triangulated["finite"])
                    ),
                    "positive_depth_count": int(
                        np.count_nonzero(triangulated["positive"])
                    ),
                    "reprojection_pass_count": pair_reprojection,
                    "footprint_inside_count": pair_inside,
                    "footprint_z_median_m": pair_z,
                    "elapsed_seconds": time.monotonic() - pair_started,
                }
            )
        except Exception as error:
            detail.update(
                {
                    "status": "failed",
                    "failure_reason": f"{type(error).__name__}: {error}",
                    "elapsed_seconds": time.monotonic() - pair_started,
                }
            )
        pair_status.append(detail)

    selected_pair_count = len(pairs)
    completed_pair_count = len(pair_status)
    successful_pair_count = sum(
        row["status"] == "complete" for row in pair_status
    )
    excluded_pair_count = sum(
        row["status"] == "excluded_degenerate" for row in pair_status
    )
    failed_pair_count = sum(
        row["status"] == "failed" for row in pair_status
    )
    pending_pair_count = selected_pair_count - completed_pair_count
    if pending_pair_count:
        status = (
            "partial_time_budget"
            if successful_pair_count else "time_budget_reached"
        )
    elif failed_pair_count:
        status = (
            "partial_with_failures"
            if successful_pair_count else "failed"
        )
    elif successful_pair_count == 0:
        status = "no_eligible_pairs"
    else:
        status = "complete"
    pooled_z_values = (
        np.concatenate(pooled_z)
        if pooled_z else np.zeros(0, dtype=np.float64)
    )
    pooled_error_values = (
        np.concatenate(pooled_errors)
        if pooled_errors else np.zeros(0, dtype=np.float64)
    )
    z_median, z_mad, z_std = finite_stats(pooled_z_values)
    error_median, _error_mad, _error_std = finite_stats(pooled_error_values)
    baseline_median, _baseline_mad, _baseline_std = finite_stats(
        np.asarray(baselines, dtype=np.float64)
    )
    failures = [
        f"rank{row['pair_rank']}:{row.get('status')}:{row.get('failure_reason', '')}"
        for row in pair_status
        if row.get("status") not in {"complete", "excluded_degenerate"}
    ]
    if pending_pair_count:
        failures.append(f"pending_pairs={pending_pair_count}")
    return {
        "building_id": job["building_id"],
        "priority_group": job["priority_group"],
        "priority_rank": job["priority_rank"],
        "primary_assignment": job["primary_assignment"],
        "status": status,
        "failure_reason": ";".join(failures),
        "view_a": "|".join(pair["view_a"] for pair in pairs),
        "view_b": "|".join(pair["view_b"] for pair in pairs),
        "crop_a_xyxy": json.dumps(
            [pair["crop_a_xyxy"] for pair in pairs], separators=(",", ":")
        ),
        "crop_b_xyxy": json.dumps(
            [pair["crop_b_xyxy"] for pair in pairs], separators=(",", ":")
        ),
        "selected_pair_count": selected_pair_count,
        "completed_pair_count": completed_pair_count,
        "successful_pair_count": successful_pair_count,
        "excluded_pair_count": excluded_pair_count,
        "failed_pair_count": failed_pair_count,
        "pending_pair_count": pending_pair_count,
        "baseline_m": baseline_median,
        "baseline_min_m": min(baselines) if baselines else None,
        "baseline_median_m": baseline_median,
        "baseline_class": (
            "all_nondegenerate"
            if successful_pair_count == selected_pair_count
            else (
                "complete_with_degenerate_exclusions"
                if status == "complete" and excluded_pair_count
                else ("mixed_or_incomplete" if successful_pair_count else "none")
            )
        ),
        "reciprocal_raw_count": totals["raw"],
        "border_match_count": totals["border"],
        "finite_dlt_count": totals["finite"],
        "positive_depth_count": totals["positive"],
        "reprojection_pass_count": totals["reprojection"],
        "reprojection_pass_fraction_of_border": (
            totals["reprojection"] / totals["border"]
            if totals["border"] else 0.0
        ),
        "reprojection_error_median_px": error_median,
        "footprint_inside_count": totals["inside"],
        "footprint_inside_fraction_of_border": (
            totals["inside"] / totals["border"]
            if totals["border"] else 0.0
        ),
        "footprint_z_median_m": z_median,
        "footprint_z_mad_m": z_mad,
        "footprint_z_std_m": z_std,
        "model_revision": MODEL_REVISION,
        "model_sha256": MODEL_SHA256,
        "model_bytes": MODEL_BYTES,
        "match_rule": (
            "MASt3R reciprocal descriptor NN stride8; 3px crop border; raw 2D only"
        ),
        "triangulation_rule": (
            "crop pixels inverted to raw FULL_OPENCV pixels without half-pixel "
            "shift; cv2 undistortPoints; float64 DLT with fixed COLMAP R,t; "
            "both depths >0; max original distorted source-pixel reprojection "
            "error <=2.0px; baseline >0.06m"
        ),
        "score_rule": (
            "after DLT only: EPSG:25832 footprint containment; z median/MAD; "
            "score=footprint_inside_count/border_match_count"
        ),
        "crs": "EPSG:25832",
        "vertical_datum": "DHHN orthometric",
        "projection_geoid_m": geoid_m,
        "projection_datum_config": rel(PROJECTION_DATUM),
        "projection_datum_config_sha256": sha256_file(PROJECTION_DATUM),
        "projection_reference_height_used": True,
        "projection_reference_source": job["projection_reference_source"],
        "elapsed_seconds": time.monotonic() - started,
        "completed_utc": now(),
        "pair_status_json": json.dumps(
            pair_status, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ),
        "pooling_rule": (
            "sum counts and concatenate footprint-inside orthometric z from all "
            "completed nondegenerate pairs; building z=pooled median; "
            "building score=pooled inside count/pooled border count"
        ),
        "learning_runs_started": 0,
        "new_inference_type": "R1-4 FM fixed-pose retriangulation only",
    }


def failed_row(
    mode: str, job: dict[str, Any], error: Exception, elapsed: float
) -> dict[str, Any]:
    common = {
        "building_id": job["building_id"],
        "priority_group": job.get("priority_group", ""),
        "priority_rank": job.get("priority_rank", ""),
        "status": "failed",
        "failure_reason": f"{type(error).__name__}: {error}",
        "view_a": job.get("view_a", ""),
        "view_b": job.get("view_b", ""),
        "crop_a_xyxy": ";".join(
            str(value) for value in job.get("crop_a_xyxy", [])
        ),
        "crop_b_xyxy": ";".join(
            str(value) for value in job.get("crop_b_xyxy", [])
        ),
        "model_revision": MODEL_REVISION,
        "model_sha256": MODEL_SHA256,
        "model_bytes": MODEL_BYTES,
        "projection_reference_height_used": True,
        "projection_reference_source": job.get(
            "projection_reference_source", ""
        ),
        "elapsed_seconds": elapsed,
        "completed_utc": now(),
        "learning_runs_started": 0,
    }
    if mode == "crop-pair":
        common.update(
            {
                "match_rule": (
                    "reciprocal descriptor NN stride8; 3px crop border; "
                    "both projected roof masks"
                ),
                "new_inference_type": (
                    "R1-2 MASt3R crop-pair correspondence only"
                ),
            }
        )
    else:
        common.update(
            {
                "primary_assignment": job.get("primary_assignment", ""),
                "selected_pair_count": len(job.get("pairs", [])),
                "completed_pair_count": 0,
                "successful_pair_count": 0,
                "excluded_pair_count": 0,
                "failed_pair_count": 0,
                "pending_pair_count": len(job.get("pairs", [])),
                "match_rule": (
                    "MASt3R reciprocal descriptor NN stride8; "
                    "3px crop border; raw 2D only"
                ),
                "triangulation_rule": (
                    "FULL_OPENCV undistortion; fixed COLMAP-pose DLT; "
                    "positive depth; distorted reprojection <=2px"
                ),
                "score_rule": "footprint-inside z median and count",
                "pair_status_json": "[]",
                "pooling_rule": (
                    "no pooled record; building-level exception before pair completion"
                ),
                "crs": "EPSG:25832",
                "vertical_datum": "DHHN orthometric",
                "projection_geoid_m": datum.projection_geoid_m(
                    config_path=PROJECTION_DATUM
                ),
                "projection_datum_config": rel(PROJECTION_DATUM),
                "projection_datum_config_sha256": sha256_file(PROJECTION_DATUM),
                "new_inference_type": (
                    "R1-4 FM fixed-pose retriangulation only"
                ),
            }
        )
    return common


def run_queue(args: argparse.Namespace) -> None:
    mode = args.command
    is_crop = mode == "crop-pair"
    jobs_path = CROP_JOBS if is_crop else FM_JOBS
    result_path = CROP_RESULTS if is_crop else FM_RESULTS
    progress_path = CROP_PROGRESS if is_crop else FM_PROGRESS
    manifest_path = CROP_MANIFEST if is_crop else FM_MANIFEST
    log_path = CROP_LOG if is_crop else FM_LOG
    fields = CROP_FIELDS if is_crop else FM_FIELDS
    default_budget = 3600.0 if is_crop else 21600.0
    max_seconds = args.max_seconds if args.max_seconds is not None else default_budget

    verify_model(args.model_dir, args.device)
    jobs_payload = json.loads(jobs_path.read_text(encoding="utf-8"))
    expected_model = {
        "revision": MODEL_REVISION,
        "weights_sha256": MODEL_SHA256,
        "weights_bytes": MODEL_BYTES,
        "config_sha256": MODEL_CONFIG_SHA256,
    }
    if jobs_payload.get("model") != expected_model:
        raise RuntimeError(
            f"job/model lock mismatch: {jobs_payload.get('model')!r}"
        )
    jobs = list(jobs_payload["jobs"])
    full_job_count = len(jobs)
    job_ids = [job["building_id"] for job in jobs]
    if len(job_ids) != len(set(job_ids)):
        raise RuntimeError("duplicate building ids in inference queue")
    if is_crop and len(jobs) > 14:
        raise RuntimeError(f"crop-pair queue exceeds requested 14: {len(jobs)}")
    if args.limit > 0:
        jobs = jobs[: args.limit]
    job_hash_by_id = {
        job["building_id"]: sha256_json(job) for job in jobs
    }
    jobs_array_sha256 = sha256_json(jobs_payload["jobs"])
    fingerprint_paths = [
        Path(__file__),
        AUX_SCRIPT,
        DATUM_SCRIPT,
        ENV_MANIFEST,
        args.model_dir / "config.json",
    ]
    if not is_crop:
        fingerprint_paths.extend(
            [FOOTPRINTS, SCENE_REF, CAMERAS, IMAGES, PROJECTION_DATUM]
        )
    pair_inputs = (
        jobs
        if is_crop
        else [pair for job in jobs for pair in job.get("pairs", [])]
    )
    used_images = sorted(
        {
            REPO / pair[key]
            for pair in pair_inputs
            for key in ("image_a", "image_b")
        },
        key=str,
    )
    missing_images = [str(path) for path in used_images if not path.is_file()]
    if missing_images:
        raise RuntimeError(f"missing selected source images: {missing_images[:5]}")
    fingerprint_paths.extend(used_images)
    input_source_sha256 = {
        rel(path): sha256_file(path)
        for path in fingerprint_paths
        if path.is_file()
    }
    input_fingerprint = sha256_json(
        {
            "mode": mode,
            "jobs_array_sha256": jobs_array_sha256,
            "model_revision": MODEL_REVISION,
            "model_weights_sha256": MODEL_SHA256,
            "docker_image_id": os.environ["MAST3R_DOCKER_IMAGE_ID"],
            "source_sha256": input_source_sha256,
        }
    )
    existing = read_csv(result_path)
    existing_ids = [row["building_id"] for row in existing]
    if len(existing_ids) != len(set(existing_ids)):
        raise RuntimeError("duplicate building ids in resume result")
    stale = [
        row["building_id"]
        for row in existing
        if row["building_id"] not in job_hash_by_id
        or row.get("job_sha256") != job_hash_by_id.get(row["building_id"])
        or row.get("input_fingerprint") != input_fingerprint
    ]
    if stale:
        raise RuntimeError(f"stale resume rows rejected: {sorted(stale)}")
    completed_ids = {
        row["building_id"] for row in existing if row.get("status") == "complete"
    }
    results: list[dict[str, Any]] = list(existing)
    start = time.monotonic()
    finalize_margin = min(120.0, max(5.0, max_seconds * 0.05))
    internal_deadline = start + max(1.0, max_seconds - finalize_margin)
    atomic_json(
        progress_path,
        {
            "status": "loading_model",
            "created_utc": now(),
            "mode": mode,
            "queue_count": len(jobs),
            "existing_result_count": len(existing),
            "max_seconds": max_seconds,
            "jobs_array_sha256": jobs_array_sha256,
            "input_fingerprint": input_fingerprint,
            "learning_runs_started": 0,
        },
    )
    log(
        log_path,
        f"start mode={mode} jobs={len(jobs)} resume={len(existing)} "
        f"device={args.device} max_seconds={max_seconds} learning_runs_started=0",
    )
    model = AsymmetricMASt3R.from_pretrained(str(args.model_dir)).to(args.device)
    model.eval()
    log(log_path, f"model loaded elapsed_seconds={time.monotonic() - start:.3f}")

    frames: dict[str, Any] = {}
    params = np.zeros(12, dtype=np.float64)
    scene_ref: dict[str, Any] = {}
    footprints: dict[str, Any] = {}
    geoid_m = datum.projection_geoid_m(config_path=PROJECTION_DATUM)
    if not is_crop:
        scene_ref = json.loads(SCENE_REF.read_text(encoding="utf-8"))
        if camera_model_name(CAMERAS) != "FULL_OPENCV":
            raise RuntimeError("global camera model is not FULL_OPENCV")
        width, height, params = aux.parse_cam_model(CAMERAS)
        if width <= 0 or height <= 0 or len(params) < 12:
            raise RuntimeError("global FULL_OPENCV camera model is incomplete")
        frames = {
            frame.name: frame for frame in aux.parse_cameras(IMAGES, scene_ref)
        }
        footprints = load_footprints()
        missing_views = sorted(
            {
                pair[key]
                for job in jobs
                for pair in job.get("pairs", [])
                for key in ("view_a", "view_b")
                if pair[key] not in frames
            }
        )
        if missing_views:
            raise RuntimeError(f"missing fixed COLMAP frames: {missing_views[:5]}")

    timed_out = False
    for index, job in enumerate(jobs, start=1):
        bid = job["building_id"]
        if bid in completed_ids:
            continue
        if time.monotonic() >= internal_deadline:
            timed_out = True
            log(log_path, f"time budget reached before {bid}")
            break
        row_start = time.monotonic()
        try:
            if is_crop:
                row = crop_measurement(model, job, args.device)
            else:
                row = fm_measurement(
                    model, job, args.device, frames, params, scene_ref,
                    footprints, geoid_m, internal_deadline,
                )
        except Exception as error:
            row = failed_row(mode, job, error, time.monotonic() - row_start)
            log(log_path, f"failed building={bid} error={row['failure_reason']}")
        row["job_sha256"] = job_hash_by_id[bid]
        row["input_fingerprint"] = input_fingerprint
        results = [item for item in results if item["building_id"] != bid]
        results.append(row)
        completed_ids.add(bid)
        results.sort(
            key=lambda item: (
                int(float(item.get("priority_rank") or 10**9)),
                item["building_id"],
            )
        )
        atomic_csv(result_path, results, fields)
        pending = [
            item["building_id"]
            for item in jobs
            if item["building_id"] not in completed_ids
        ]
        atomic_json(
            progress_path,
            {
                "status": "running",
                "updated_utc": now(),
                "mode": mode,
                "completed_count": len(completed_ids),
                "queue_count": len(jobs),
                "pending_count": len(pending),
                "pending_buildings": pending,
                "last_building": bid,
                "elapsed_seconds": time.monotonic() - start,
                "max_seconds": max_seconds,
                "jobs_array_sha256": jobs_array_sha256,
                "input_fingerprint": input_fingerprint,
                "learning_runs_started": 0,
            },
        )
        log(
            log_path,
            f"progress {index}/{len(jobs)} building={bid} "
            f"status={row['status']} elapsed_seconds={time.monotonic() - start:.3f}",
        )
        if "time_budget" in str(row.get("status", "")):
            timed_out = True
            break

    pending = [
        item["building_id"]
        for item in jobs
        if item["building_id"] not in completed_ids
    ]
    failed_ids = sorted(
        row["building_id"] for row in results if row.get("status") != "complete"
    )
    status = (
        "time_budget_reached" if timed_out or pending
        else ("complete_with_failures" if failed_ids else "complete")
    )
    if args.limit > 0 and len(jobs) < full_job_count and status == "complete":
        status = "limited_complete"
    elapsed = time.monotonic() - start
    atomic_json(
        progress_path,
        {
            "status": status,
            "updated_utc": now(),
            "mode": mode,
            "completed_count": len(completed_ids),
            "queue_count": len(jobs),
            "pending_count": len(pending),
            "pending_buildings": pending,
            "failed_count": len(failed_ids),
            "failed_buildings": failed_ids,
            "elapsed_seconds": elapsed,
            "max_seconds": max_seconds,
            "internal_finalize_margin_seconds": finalize_margin,
            "jobs_array_sha256": jobs_array_sha256,
            "input_fingerprint": input_fingerprint,
            "learning_runs_started": 0,
        },
    )
    log(
        log_path,
        f"finish status={status} results={len(results)} pending={len(pending)} "
        f"elapsed_seconds={elapsed:.3f} learning_runs_started=0",
    )
    source_paths = fingerprint_paths
    pair_summary = None
    if not is_crop:
        pair_summary = {
            "selected_pair_count": sum(
                int(float(row.get("selected_pair_count") or 0))
                for row in results
            ),
            "completed_pair_count": sum(
                int(float(row.get("completed_pair_count") or 0))
                for row in results
            ),
            "successful_pair_count": sum(
                int(float(row.get("successful_pair_count") or 0))
                for row in results
            ),
            "excluded_pair_count": sum(
                int(float(row.get("excluded_pair_count") or 0))
                for row in results
            ),
            "failed_pair_count": sum(
                int(float(row.get("failed_pair_count") or 0))
                for row in results
            ),
            "pending_pair_count": sum(
                int(float(row.get("pending_pair_count") or 0))
                for row in results
            ),
            "pooling_rule": (
                "per building: sum counts and concatenate footprint-inside "
                "orthometric z across completed nondegenerate pairs"
            ),
        }
    manifest = {
        "schema": f"jointbuildgs.boundary_map_v2.{mode}.v1",
        "created_utc": now(),
        "git_head_at_measurement": git_value("rev-parse", "HEAD"),
        "branch": git_value("branch", "--show-current"),
        "status": status,
        "device": args.device,
        "cuda_device_name": (
            torch.cuda.get_device_name(torch.cuda.current_device())
            if args.device.startswith("cuda") and torch.cuda.is_available() else ""
        ),
        "max_seconds": max_seconds,
        "internal_finalize_margin_seconds": finalize_margin,
        "elapsed_seconds": elapsed,
        "full_job_count": full_job_count,
        "job_count": len(jobs),
        "limit": args.limit,
        "result_count": len(results),
        "pending_buildings": pending,
        "failed_buildings": failed_ids,
        "pair_summary": pair_summary,
        "model": {
            "revision": MODEL_REVISION,
            "weights_sha256": MODEL_SHA256,
            "weights_bytes": MODEL_BYTES,
            "config_sha256": MODEL_CONFIG_SHA256,
        },
        "s3ap_environment_lock": {
            "manifest": rel(ENV_MANIFEST),
            "manifest_sha256": sha256_file(ENV_MANIFEST),
            "docker_image_id": os.environ["MAST3R_DOCKER_IMAGE_ID"],
            "mast3r_commit": json.loads(
                ENV_MANIFEST.read_text(encoding="utf-8")
            )["code"]["mast3r_commit"],
            "dust3r_commit": json.loads(
                ENV_MANIFEST.read_text(encoding="utf-8")
            )["code"]["dust3r_commit"],
            "croco_commit": json.loads(
                ENV_MANIFEST.read_text(encoding="utf-8")
            )["code"]["croco_commit"],
        },
        "jobs_sha256": sha256_file(jobs_path),
        "jobs_array_sha256": jobs_array_sha256,
        "input_fingerprint": input_fingerprint,
        "source_sha256": {
            rel(path): sha256_file(path)
            for path in source_paths
            if path.is_file()
        },
        "camera_model": (
            "global FULL_OPENCV; raw pixels undistorted before fixed-pose DLT "
            "and reprojected with original distortion"
            if not is_crop else "not used for crop-pair count"
        ),
        "vertical_datum": (
            {
                "recorded_z": "DHHN orthometric",
                "fixed_pose_base_z": "ellipsoidal",
                "conversion": "z_orthometric=z_base_ellipsoidal-projection_geoid_m",
                "projection_geoid_m": geoid_m,
                "config": rel(PROJECTION_DATUM),
                "config_sha256": sha256_file(PROJECTION_DATUM),
            }
            if not is_crop else None
        ),
        "output_sha256": {
            rel(path): sha256_file(path)
            for path in (result_path, progress_path, log_path)
            if path.is_file()
        },
        "learning_runs_started": 0,
        "new_inference_type": (
            "R1-2 MASt3R crop-pair correspondence only"
            if is_crop else "R1-4 FM fixed-pose retriangulation only"
        ),
        "interpretation_or_verdict": None,
    }
    atomic_json(manifest_path, manifest)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("crop-pair", "fm"))
    parser.add_argument("--model-dir", type=Path, required=True)
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--max-seconds", type=float)
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()
    run_queue(args)


if __name__ == "__main__":
    main()
