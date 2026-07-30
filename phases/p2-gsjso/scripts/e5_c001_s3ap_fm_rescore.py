#!/usr/bin/env python3
"""S3-A-prime MASt3R learning-zero rescore on the locked textureless three.

The candidate pipeline is independent of LoD2 and footprint scoring:

1. crop each already-locked P-J/P-L visible view from its frozen T0-1 oracle
   region address (32 px margin, minimum 256x192, exact 4:3);
2. infer the pinned metric MASt3R model and retain reciprocal descriptor
   matches away from a 3 px image border;
3. recover both physical-camera poses in the MASt3R crop gauge with PnP;
4. align those two predicted camera centers and orientations to the two fixed
   COLMAP poses with one similarity (baseline-ratio scale, averaged rotation,
   least-squares translation), then transform joint PnP inlier points.

Only after step 5 are footprint containment, exterior leakage, upper-roof
selection, and LoD2 z errors computed.  No candidate is generated or rejected
using LoD2 roof geometry or its reference height.  No output becomes a seed or
training input in this wave.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import itertools
import json
import math
import os
import subprocess
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Iterator, Sequence

os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib")
os.environ.setdefault("XDG_CACHE_HOME", "/tmp")

import cv2
import matplotlib
import numpy as np
import torch
from PIL import Image as PILImage
from shapely import contains_xy, make_valid
from shapely.geometry import MultiPolygon, Polygon, shape
from shapely.ops import unary_union

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

import mast3r.utils.path_to_dust3r  # noqa: F401,E402
from dust3r.inference import inference  # noqa: E402
from dust3r.utils.image import ImgNorm  # noqa: E402
from mast3r.fast_nn import fast_reciprocal_NNs  # noqa: E402
from mast3r.model import AsymmetricMASt3R  # noqa: E402

REPO = Path(__file__).resolve().parents[3]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))
from src.stage2.colmap_io import read_cameras_bin, read_images_bin  # noqa: E402


RUN_ID = "20260714_e5_c001_s3ap_fm_rescore"
RUN_DIR = REPO / "phases/p2-gsjso/runs" / RUN_ID
DATA_ROOT = REPO / "results/tum_transfer/e5_pilot/C001/data_geoidfix_C001_buf20"
SPARSE_DIR = DATA_ROOT / "sparse/0"
IMAGE_DIR = DATA_ROOT / "images"
REGION_DIR = REPO / "results/tum_transfer/e5_s3/C001/semantic_regions"
PJPL = (
    REPO
    / "results/tum_transfer/e5_s3_semantic_guided/C001/runs"
    / "gs_e5_C001_s3a_semantic_guided_gate/audit/pjpl_depth_anchor_views.csv"
)
FOOTPRINTS = REPO / "results/tum_transfer/analysis/footprints_aoi.geojson"
TRAIN_MANIFEST = REPO / "results/tum_transfer/e5_pilot/C001/C001_train_prep_manifest.json"
ANCHOR_CSV = REPO / "docs/experiments/input-and-alignment/e5_c001_s3ap/tables/e5_c001_s3ap_anchor_inventory.csv"
ENV_MANIFEST = REPO / "docs/experiments/input-and-alignment/e5_c001_s3ap/manifests/e5_c001_s3ap_fm_env_manifest.json"
OUT_CSV = REPO / "docs/experiments/input-and-alignment/e5_c001_s3ap/tables/e5_c001_s3ap_fm_rescore.csv"
FIG_DIR = REPO / "docs/figs/e5_c001_s3ap_fm_rescore"
PAIR_JSON = RUN_DIR / "pair_details.json"
MANIFEST = RUN_DIR / "manifest.json"

TARGETS = ["4907199", "8568391", "8568392"]
MAX_PAIRS = 10
MODEL_REVISION = "06e7259f34c3060f322df5cb0c7b9094f57e41fc"
MODEL_SHA256 = "0a615eb05fa9db654050aa655945ee5696e7c6c1b7f93f1ee8c37249010f6feb"
MODEL_BYTES = 2_754_661_648
LOAD_WIDTH = 512
LOAD_HEIGHT = 384
CROP_MARGIN_PX = 32
CROP_MIN_WIDTH = 256
MATCH_SUBSAMPLE = 8
MATCH_BORDER_PX = 3
GAUGE_PNP_REPROJECTION_PX = 4.0
GAUGE_PNP_ITERATIONS = 1000
GAUGE_PNP_CONFIDENCE = 0.999
UPPER_OFFSET_M = 1.5


def full_id(short: str) -> str:
    return short if short.startswith("DEBY_LOD2_") else f"DEBY_LOD2_{short}"


def rel(path: Path | str) -> str:
    path = Path(path)
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


def sha256_json(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, Any]], fields: Sequence[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(fields), extrasaction="ignore", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def git_value(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=REPO, text=True).strip()


def load_offset() -> np.ndarray:
    value = np.asarray(json.loads(TRAIN_MANIFEST.read_text(encoding="utf-8"))["world_offset"], dtype=np.float64)
    if value.shape != (3,) or not np.all(np.isfinite(value)):
        raise RuntimeError(f"invalid world offset: {value!r}")
    return value


def load_footprints() -> dict[str, Polygon | MultiPolygon]:
    payload = json.loads(FOOTPRINTS.read_text(encoding="utf-8"))
    crs = str(payload.get("crs", {}).get("properties", {}).get("name", ""))
    if "25832" not in crs:
        raise RuntimeError(f"footprint CRS is not EPSG:25832: {crs!r}")
    pieces: dict[str, list[Any]] = defaultdict(list)
    wanted = {full_id(short) for short in TARGETS}
    for feature in payload["features"]:
        bid = str((feature.get("properties") or {}).get("building_id", ""))
        if bid in wanted:
            geom = make_valid(shape(feature["geometry"]))
            if not geom.is_empty:
                pieces[bid].append(geom)
    out: dict[str, Polygon | MultiPolygon] = {}
    for bid in sorted(wanted):
        geom = make_valid(unary_union(pieces[bid]))
        if not isinstance(geom, (Polygon, MultiPolygon)) or geom.is_empty:
            raise RuntimeError(f"missing footprint: {bid}")
        out[bid] = geom
    return out


def load_anchor_scores() -> tuple[dict[str, float], dict[str, float]]:
    ground: dict[str, float] = {}
    reference: dict[str, float] = {}
    for row in read_csv(ANCHOR_CSV):
        if row["source"] != "observed_sfm_plus_dense" or row["band_width_m"] != "1.000000":
            continue
        short = row["building_id"].removeprefix("DEBY_LOD2_")
        if short in TARGETS:
            ground[short] = float(row["ground_z_q10_local_m"])
            reference[short] = float(row["reference_roof_z_local_m"])
    if set(ground) != set(TARGETS) or set(reference) != set(TARGETS):
        raise RuntimeError("anchor ground/reference rows are incomplete")
    return ground, reference


def load_frames() -> dict[str, dict[str, Any]]:
    cameras = read_cameras_bin(SPARSE_DIR / "cameras.bin")
    images = read_images_bin(SPARSE_DIR / "images.bin")
    out: dict[str, dict[str, Any]] = {}
    for image in images.values():
        path = IMAGE_DIR / image.name
        if not path.exists():
            continue
        camera = cameras[image.camera_id]
        out[Path(image.name).stem] = {
            "name": image.name,
            "path": path,
            "K": camera.K(),
            "R": image.R(),
            "t": image.tvec.astype(np.float64),
            "width": int(camera.width),
            "height": int(camera.height),
        }
    return out


def load_view_rows() -> dict[str, list[dict[str, Any]]]:
    by_building: dict[str, list[dict[str, Any]]] = {short: [] for short in TARGETS}
    for row in read_csv(PJPL):
        short = row["building_id"]
        if short not in by_building:
            continue
        by_building[short].append(
            {
                "stem": row["view_stem"],
                "view": row["view"],
                "support": int(row["address_pixel_count"]),
                "oracle_visible_support": int(row["oracle_visible_roof_pixel_count"]),
            }
        )
    expected = {"4907199": 6, "8568391": 3, "8568392": 3}
    for short, count in expected.items():
        if len(by_building[short]) != count:
            raise RuntimeError(f"P-J/P-L view drift for {short}: {len(by_building[short])} != {count}")
    return by_building


def select_pairs(views: list[dict[str, Any]]) -> list[dict[str, Any]]:
    pairs: list[dict[str, Any]] = []
    for left, right in itertools.combinations(views, 2):
        pairs.append(
            {
                "a": left,
                "b": right,
                "selection_min_address_support": min(left["support"], right["support"]),
                "selection_sum_address_support": left["support"] + right["support"],
            }
        )
    pairs.sort(
        key=lambda item: (
            -item["selection_min_address_support"],
            -item["selection_sum_address_support"],
            item["a"]["stem"],
            item["b"]["stem"],
        )
    )
    return pairs[:MAX_PAIRS]


def target_region_mask(short: str, stem: str) -> tuple[np.ndarray, dict[str, Any]]:
    path = REGION_DIR / f"{stem}.npz"
    archive = np.load(path, allow_pickle=False)
    region_ids = np.asarray(archive["region_ids"], dtype=np.int32)
    metadata = json.loads(str(archive["metadata_json"]))
    ids = [int(rid) for rid, item in metadata["regions"].items() if item["building_id"] == full_id(short)]
    if not ids:
        raise RuntimeError(f"no frozen region for {short} in {stem}")
    mask = np.isin(region_ids, np.asarray(ids, dtype=np.int32))
    if not np.any(mask):
        raise RuntimeError(f"empty frozen region for {short} in {stem}")
    return mask, metadata


def crop_box_4x3(mask: np.ndarray, image_width: int, image_height: int) -> tuple[int, int, int, int]:
    y, x = np.nonzero(mask[:image_height, :image_width])
    if not len(x):
        raise RuntimeError("target region lies outside source image")
    target_w = int(x.max() - x.min() + 1 + 2 * CROP_MARGIN_PX)
    target_h = int(y.max() - y.min() + 1 + 2 * CROP_MARGIN_PX)
    width = max(CROP_MIN_WIDTH, target_w, int(math.ceil(target_h * 4.0 / 3.0)))
    width = int(math.ceil(width / 16.0) * 16)
    max_width = min(image_width, int(math.floor(image_height * 4.0 / 3.0)))
    max_width = max(16, max_width - (max_width % 16))
    width = min(width, max_width)
    height = int(width * 3 // 4)
    cx = float(x.min() + x.max()) / 2.0
    cy = float(y.min() + y.max()) / 2.0
    x0 = int(round(cx - width / 2.0))
    y0 = int(round(cy - height / 2.0))
    x0 = min(max(0, x0), image_width - width)
    y0 = min(max(0, y0), image_height - height)
    return x0, y0, x0 + width, y0 + height


def prepare_view(frame: dict[str, Any], box: tuple[int, int, int, int], idx: int) -> tuple[dict[str, Any], np.ndarray, np.ndarray]:
    with PILImage.open(frame["path"]) as source:
        crop = source.convert("RGB").crop(box).resize((LOAD_WIDTH, LOAD_HEIGHT), PILImage.Resampling.LANCZOS)
    rgb = np.asarray(crop, dtype=np.uint8)
    image = {
        "img": ImgNorm(crop)[None],
        "true_shape": np.int32([[LOAD_HEIGHT, LOAD_WIDTH]]),
        "idx": idx,
        "instance": str(idx),
    }
    x0, y0, x1, y1 = box
    sx = LOAD_WIDTH / float(x1 - x0)
    sy = LOAD_HEIGHT / float(y1 - y0)
    K = frame["K"].copy().astype(np.float64)
    K[0, 2] -= x0
    K[1, 2] -= y0
    K[0, :] *= sx
    K[1, :] *= sy
    return image, rgb, K


def solve_gauge_camera(
    points: np.ndarray, pixels: np.ndarray, K: np.ndarray
) -> tuple[bool, np.ndarray | None, np.ndarray | None, np.ndarray]:
    ok, rvec, tvec, inliers = cv2.solvePnPRansac(
        points.astype(np.float64),
        pixels.astype(np.float64),
        K.astype(np.float64),
        None,
        iterationsCount=GAUGE_PNP_ITERATIONS,
        reprojectionError=GAUGE_PNP_REPROJECTION_PX,
        confidence=GAUGE_PNP_CONFIDENCE,
        flags=cv2.SOLVEPNP_EPNP,
    )
    if not ok or inliers is None or len(inliers) < 4:
        return False, None, None, np.zeros(0, dtype=np.int64)
    R, _ = cv2.Rodrigues(rvec)
    return True, R, np.asarray(tvec, dtype=np.float64).reshape(3), np.asarray(inliers).reshape(-1)


def average_rotation(rotations: Sequence[np.ndarray]) -> np.ndarray:
    matrix = np.sum(np.stack(rotations), axis=0)
    u, _, vt = np.linalg.svd(matrix)
    correction = np.eye(3)
    correction[-1, -1] = np.linalg.det(u @ vt)
    return u @ correction @ vt


def rotation_error_deg(a: np.ndarray, b: np.ndarray) -> float:
    delta = a @ b.T
    cosine = float(np.clip((np.trace(delta) - 1.0) / 2.0, -1.0, 1.0))
    return float(np.degrees(np.arccos(cosine)))


def finite_stats(values: Iterable[float]) -> tuple[float | None, float | None, float | None]:
    array = np.asarray(list(values), dtype=np.float64)
    array = array[np.isfinite(array)]
    if not len(array):
        return None, None, None
    median = float(np.median(array))
    return median, float(np.median(np.abs(array - median))), float(np.std(array))


def json_number(value: Any) -> Any:
    if isinstance(value, np.generic):
        value = value.item()
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def measure_pair(
    model: Any,
    short: str,
    pair_rank: int,
    pair: dict[str, Any],
    frames: dict[str, dict[str, Any]],
    footprint: Any,
    offset: np.ndarray,
    ground_z: float,
    reference_z: float,
    device: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    a, b = pair["a"], pair["b"]
    frame_a, frame_b = frames[a["stem"]], frames[b["stem"]]
    mask_a, meta_a = target_region_mask(short, a["stem"])
    mask_b, meta_b = target_region_mask(short, b["stem"])
    box_a = crop_box_4x3(mask_a, frame_a["width"], frame_a["height"])
    box_b = crop_box_4x3(mask_b, frame_b["width"], frame_b["height"])
    image_a, rgb_a, K_a = prepare_view(frame_a, box_a, 0)
    image_b, rgb_b, K_b = prepare_view(frame_b, box_b, 1)
    with torch.inference_mode():
        output = inference([(image_a, image_b)], model, device, batch_size=1, verbose=False)
    pred1, pred2 = output["pred1"], output["pred2"]
    desc1 = pred1["desc"].squeeze(0).detach()
    desc2 = pred2["desc"].squeeze(0).detach()
    matches_a, matches_b = fast_reciprocal_NNs(
        desc1,
        desc2,
        subsample_or_initxy1=MATCH_SUBSAMPLE,
        device=device,
        dist="dot",
        block_size=2**13,
    )
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
    matches_a = matches_a[border]
    matches_b = matches_b[border]
    border_count = int(len(matches_a))
    p1_map = pred1["pts3d"].squeeze(0).detach().float().cpu().numpy()
    p2_in_1_map = pred2["pts3d_in_other_view"].squeeze(0).detach().float().cpu().numpy()
    p1 = p1_map[matches_a[:, 1], matches_a[:, 0]]
    p2_in_1 = p2_in_1_map[matches_b[:, 1], matches_b[:, 0]]
    finite = np.isfinite(p1).all(axis=1) & np.isfinite(p2_in_1).all(axis=1)
    finite &= (p1[:, 2] > 0) & (p2_in_1[:, 2] > 0)
    matches_a = matches_a[finite]
    matches_b = matches_b[finite]
    p1 = p1[finite].astype(np.float64)
    p2_in_1 = p2_in_1[finite].astype(np.float64)
    finite_count = int(len(p1))
    status = "pass"
    reason = ""
    if finite_count < 6:
        status = "failed_insufficient_finite_matches"
        reason = f"finite_matches={finite_count}<6"
        inlier_idx = np.zeros(0, dtype=np.int64)
        scale = predicted_baseline = known_baseline = rotation_consistency = center_residual = None
        pnp_inlier_a_count = pnp_inlier_b_count = 0
        world = np.zeros((0, 3), dtype=np.float64)
    else:
        ok_a, R_pred_a, t_pred_a, inliers_a = solve_gauge_camera(p1, matches_a, K_a)
        ok_b, R_pred_b, t_pred_b, inliers_b = solve_gauge_camera(p2_in_1, matches_b, K_b)
        pnp_inlier_a_count, pnp_inlier_b_count = len(inliers_a), len(inliers_b)
        inlier_idx = np.intersect1d(inliers_a, inliers_b, assume_unique=False)
        if not ok_a or not ok_b or len(inlier_idx) < 4:
            status = "failed_crop_gauge_alignment"
            reason = (
                f"pnp_a={pnp_inlier_a_count};pnp_b={pnp_inlier_b_count};"
                f"joint_inliers={len(inlier_idx)}<4"
            )
            inlier_idx = np.zeros(0, dtype=np.int64)
            scale = predicted_baseline = known_baseline = rotation_consistency = center_residual = None
            world = np.zeros((0, 3), dtype=np.float64)
        else:
            pred_center_a = -R_pred_a.T @ t_pred_a
            pred_center_b = -R_pred_b.T @ t_pred_b
            known_center_a = -frame_a["R"].T @ frame_a["t"]
            known_center_b = -frame_b["R"].T @ frame_b["t"]
            predicted_baseline = float(np.linalg.norm(pred_center_b - pred_center_a))
            known_baseline = float(np.linalg.norm(known_center_b - known_center_a))
            if predicted_baseline <= 1e-9 or known_baseline <= 1e-9:
                status = "failed_degenerate_camera_baseline"
                reason = f"predicted={predicted_baseline};known={known_baseline}"
                scale = rotation_consistency = center_residual = None
                inlier_idx = np.zeros(0, dtype=np.int64)
                world = np.zeros((0, 3), dtype=np.float64)
            else:
                scale = known_baseline / predicted_baseline
                world_from_pred_a = frame_a["R"].T @ R_pred_a
                world_from_pred_b = frame_b["R"].T @ R_pred_b
                rotation_consistency = rotation_error_deg(world_from_pred_a, world_from_pred_b)
                world_from_pred = average_rotation([world_from_pred_a, world_from_pred_b])
                translation_a = known_center_a - scale * (world_from_pred @ pred_center_a)
                translation_b = known_center_b - scale * (world_from_pred @ pred_center_b)
                translation = 0.5 * (translation_a + translation_b)
                aligned_a = scale * (world_from_pred @ pred_center_a) + translation
                aligned_b = scale * (world_from_pred @ pred_center_b) + translation
                center_residual = float(
                    0.5 * (np.linalg.norm(aligned_a - known_center_a) + np.linalg.norm(aligned_b - known_center_b))
                )
                points_pred = 0.5 * (p1[inlier_idx] + p2_in_1[inlier_idx])
                world = (scale * (world_from_pred @ points_pred.T)).T + translation[None, :]

    if len(world):
        x_utm = world[:, 0] + offset[0]
        y_utm = world[:, 1] + offset[1]
        inside = contains_xy(footprint, x_utm, y_utm)
    else:
        inside = np.zeros(0, dtype=bool)
    upper = inside & (world[:, 2] >= ground_z + UPPER_OFFSET_M) if len(world) else inside
    errors = np.abs(world[upper, 2] - reference_z) if len(world) else np.zeros(0)
    error_median, error_mad, error_std = finite_stats(errors)
    leakage_count = int(np.count_nonzero(~inside)) if len(world) else 0
    leakage_rate = float(leakage_count / len(world)) if len(world) else None
    row = {
        "row_type": "view_pair",
        "building_id": full_id(short),
        "pair_rank": pair_rank,
        "view_a": a["stem"],
        "view_b": b["stem"],
        "address_support_a": a["support"],
        "address_support_b": b["support"],
        "pair_selection_min_address_support": pair["selection_min_address_support"],
        "pair_selection_sum_address_support": pair["selection_sum_address_support"],
        "crop_box_a_xyxy": ";".join(str(v) for v in box_a),
        "crop_box_b_xyxy": ";".join(str(v) for v in box_b),
        "reciprocal_match_count": raw_count,
        "border_finite_match_count": finite_count,
        "crop_gauge_pnp_inlier_a_count": pnp_inlier_a_count,
        "crop_gauge_pnp_inlier_b_count": pnp_inlier_b_count,
        "joint_pnp_inlier_count": int(len(inlier_idx)),
        "joint_pnp_inlier_fraction": float(len(inlier_idx) / finite_count) if finite_count else None,
        "predicted_camera_baseline_model_units": predicted_baseline,
        "known_colmap_baseline_m": known_baseline,
        "similarity_scale_m_per_model_unit": scale,
        "camera_rotation_consistency_deg_qa": rotation_consistency,
        "aligned_camera_center_residual_m_qa": center_residual,
        "pose_alignment_method": (
            "PnP recovers each physical camera in MASt3R crop gauge; known COLMAP poses fixed; "
            "scale=known/predicted camera-center baseline; rotation=SO(3) mean of pose-implied "
            "world rotations; translation=mean center alignment"
        ),
        "reconstructed_candidate_count": int(len(world)),
        "footprint_inside_count": int(np.count_nonzero(inside)),
        "roof_candidate_count": int(np.count_nonzero(upper)),
        "abs_delta_z_median_m": error_median,
        "abs_delta_z_within_pair_mad_m": error_mad,
        "abs_delta_z_within_pair_std_m": error_std,
        "abs_delta_z_across_pair_mad_m": "",
        "footprint_outside_count": leakage_count,
        "footprint_outside_rate": leakage_rate,
        "ground_z_q10_local_m": ground_z,
        "reference_roof_z_local_m": reference_z,
        "selected_pair_count": "",
        "completed_pair_count": "",
        "status": status,
        "failure_reason": reason,
        "view_pair_selection_rule": (
            "all locked visible-view combinations; sort by min frozen address pixels desc, "
            "then sum desc, stems asc; keep at most 10"
        ),
        "candidate_rule": (
            "MASt3R reciprocal desc NN stride8; 3px border; finite positive pointmaps; "
            "joint 4px crop-gauge PnP inliers only; no footprint or LoD2 filter"
        ),
        "score_rule": (
            "yield=points inside exact footprint after reconstruction; roof candidate=inside and "
            "z>=observed exterior-ring ground q10+1.5m; abs dz versus LoD2 only here"
        ),
        "gt_role": "LoD2 reference z and footprint containment used only after reconstruction for scoring",
        "learning_runs_started": 0,
    }
    detail = {
        "row": {key: json_number(value) for key, value in row.items()},
        "rgb_a": rgb_a,
        "rgb_b": rgb_b,
        "matches_a": matches_a[inlier_idx] if len(inlier_idx) else np.zeros((0, 2), dtype=np.int32),
        "matches_b": matches_b[inlier_idx] if len(inlier_idx) else np.zeros((0, 2), dtype=np.int32),
        "world": world,
        "inside": inside,
        "upper": upper,
        "region_cache_a_sha256": sha256_file(REGION_DIR / f"{a['stem']}.npz"),
        "region_cache_b_sha256": sha256_file(REGION_DIR / f"{b['stem']}.npz"),
        "region_address_mode_a": meta_a["loss_address_mode"],
        "region_address_mode_b": meta_b["loss_address_mode"],
    }
    return row, detail


def summary_row(short: str, rows: list[dict[str, Any]], ground_z: float, reference_z: float) -> dict[str, Any]:
    completed = [row for row in rows if row["status"] == "pass"]

    def med(key: str) -> float | None:
        values = [float(row[key]) for row in completed if row[key] not in (None, "")]
        return float(np.median(values)) if values else None

    pair_error_medians = [float(row["abs_delta_z_median_m"]) for row in completed if row["abs_delta_z_median_m"] is not None]
    error_summary = float(np.median(pair_error_medians)) if pair_error_medians else None
    error_across_mad = (
        float(np.median(np.abs(np.asarray(pair_error_medians) - error_summary)))
        if pair_error_medians and error_summary is not None
        else None
    )
    return {
        "row_type": "building_summary",
        "building_id": full_id(short),
        "pair_rank": "MEDIAN_SELECTED_PAIRS",
        "view_a": "",
        "view_b": "",
        "address_support_a": "",
        "address_support_b": "",
        "pair_selection_min_address_support": "",
        "pair_selection_sum_address_support": "",
        "crop_box_a_xyxy": "",
        "crop_box_b_xyxy": "",
        "reciprocal_match_count": med("reciprocal_match_count"),
        "border_finite_match_count": med("border_finite_match_count"),
        "crop_gauge_pnp_inlier_a_count": med("crop_gauge_pnp_inlier_a_count"),
        "crop_gauge_pnp_inlier_b_count": med("crop_gauge_pnp_inlier_b_count"),
        "joint_pnp_inlier_count": med("joint_pnp_inlier_count"),
        "joint_pnp_inlier_fraction": med("joint_pnp_inlier_fraction"),
        "predicted_camera_baseline_model_units": med("predicted_camera_baseline_model_units"),
        "known_colmap_baseline_m": med("known_colmap_baseline_m"),
        "similarity_scale_m_per_model_unit": med("similarity_scale_m_per_model_unit"),
        "camera_rotation_consistency_deg_qa": med("camera_rotation_consistency_deg_qa"),
        "aligned_camera_center_residual_m_qa": med("aligned_camera_center_residual_m_qa"),
        "pose_alignment_method": "same locked crop-gauge-to-fixed-COLMAP similarity method as pair rows",
        "reconstructed_candidate_count": med("reconstructed_candidate_count"),
        "footprint_inside_count": med("footprint_inside_count"),
        "roof_candidate_count": med("roof_candidate_count"),
        "abs_delta_z_median_m": error_summary,
        "abs_delta_z_within_pair_mad_m": med("abs_delta_z_within_pair_mad_m"),
        "abs_delta_z_within_pair_std_m": med("abs_delta_z_within_pair_std_m"),
        "abs_delta_z_across_pair_mad_m": error_across_mad,
        "footprint_outside_count": med("footprint_outside_count"),
        "footprint_outside_rate": med("footprint_outside_rate"),
        "ground_z_q10_local_m": ground_z,
        "reference_roof_z_local_m": reference_z,
        "selected_pair_count": len(rows),
        "completed_pair_count": len(completed),
        "status": "summary",
        "failure_reason": ";".join(f"rank{r['pair_rank']}:{r['status']}" for r in rows if r["status"] != "pass"),
        "view_pair_selection_rule": rows[0]["view_pair_selection_rule"] if rows else "",
        "candidate_rule": rows[0]["candidate_rule"] if rows else "",
        "score_rule": "building value = median of completed pair values; across-pair MAD is MAD of pair |dz| medians",
        "gt_role": "LoD2 reference z and footprint containment used only after reconstruction for scoring",
        "learning_runs_started": 0,
    }


def iter_polygons(geom: Polygon | MultiPolygon) -> Iterator[Polygon]:
    if isinstance(geom, Polygon):
        yield geom
    else:
        yield from geom.geoms


def make_figure(short: str, detail: dict[str, Any], footprint: Any, offset: np.ndarray, reference_z: float) -> Path:
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    fig = plt.figure(figsize=(16, 5.3), dpi=180)
    ax_a = fig.add_subplot(1, 3, 1)
    ax_b = fig.add_subplot(1, 3, 2)
    ax_xy = fig.add_subplot(1, 3, 3)
    ax_a.imshow(detail["rgb_a"])
    ax_b.imshow(detail["rgb_b"])
    ma, mb = detail["matches_a"], detail["matches_b"]
    if len(ma):
        stride = max(1, int(math.ceil(len(ma) / 160)))
        colors = plt.cm.turbo(np.linspace(0, 1, len(ma[::stride])))
        ax_a.scatter(ma[::stride, 0], ma[::stride, 1], s=9, c=colors, edgecolors="black", linewidths=0.15)
        ax_b.scatter(mb[::stride, 0], mb[::stride, 1], s=9, c=colors, edgecolors="black", linewidths=0.15)
    ax_a.set_title(detail["row"]["view_a"])
    ax_b.set_title(detail["row"]["view_b"])
    ax_a.axis("off")
    ax_b.axis("off")
    world, inside, upper = detail["world"], detail["inside"], detail["upper"]
    for polygon in iter_polygons(footprint):
        ring = np.asarray(polygon.exterior.coords, dtype=np.float64)
        ax_xy.plot(ring[:, 0], ring[:, 1], color="black", linewidth=1.6, label="footprint (score only)")
    if len(world):
        x, y = world[:, 0] + offset[0], world[:, 1] + offset[1]
        if np.any(~inside):
            ax_xy.scatter(x[~inside], y[~inside], s=10, c="#8c8c8c", alpha=0.65, label="outside")
        if np.any(inside & ~upper):
            ax_xy.scatter(x[inside & ~upper], y[inside & ~upper], s=12, c="#1f77b4", alpha=0.70, label="inside non-upper")
        if np.any(upper):
            errors = np.abs(world[upper, 2] - reference_z)
            scatter = ax_xy.scatter(x[upper], y[upper], s=18, c=errors, cmap="magma", alpha=0.85, label="roof candidate")
            fig.colorbar(scatter, ax=ax_xy, fraction=0.046, pad=0.04, label="|dz| ref (m), score only")
    ax_xy.set_aspect("equal", adjustable="box")
    ax_xy.set_title("camera-aligned reconstructed candidates")
    ax_xy.set_xlabel("Easting (EPSG:25832)")
    ax_xy.set_ylabel("Northing (EPSG:25832)")
    ax_xy.legend(loc="best", fontsize=7)
    fig.suptitle(
        f"{full_id(short)} | selected pair rank {detail['row']['pair_rank']} | "
        f"joint gauge-PnP inliers {detail['row']['joint_pnp_inlier_count']}",
        fontsize=12,
    )
    fig.tight_layout(rect=[0, 0, 1, 0.95])
    path = FIG_DIR / f"fm_rescore_{short}.png"
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)
    return path


def fmt(value: Any, digits: int = 6) -> Any:
    if value is None:
        return ""
    if isinstance(value, (float, np.floating)):
        if not math.isfinite(float(value)):
            return ""
        return f"{float(value):.{digits}f}"
    return value


def serializable_detail(detail: dict[str, Any]) -> dict[str, Any]:
    return {
        "row": detail["row"],
        "region_cache_a_sha256": detail["region_cache_a_sha256"],
        "region_cache_b_sha256": detail["region_cache_b_sha256"],
        "region_address_mode_a": detail["region_address_mode_a"],
        "region_address_mode_b": detail["region_address_mode_b"],
        "matches_a": detail["matches_a"].tolist(),
        "matches_b": detail["matches_b"].tolist(),
        "world_local_xyz": detail["world"].tolist(),
        "inside_footprint_score_mask": detail["inside"].astype(bool).tolist(),
        "upper_roof_candidate_score_mask": detail["upper"].astype(bool).tolist(),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-dir", type=Path, required=True)
    parser.add_argument("--device", default="cuda")
    args = parser.parse_args()
    weights = args.model_dir / "model.safetensors"
    if args.model_dir.name != MODEL_REVISION or sha256_file(weights) != MODEL_SHA256 or weights.stat().st_size != MODEL_BYTES:
        raise RuntimeError("MASt3R model lock mismatch")
    env = json.loads(ENV_MANIFEST.read_text(encoding="utf-8"))
    if env["status"] != "environment_locked_smoke_pass":
        raise RuntimeError("MASt3R environment is not locked/passing")
    if not torch.cuda.is_available() and args.device.startswith("cuda"):
        raise RuntimeError("CUDA requested but unavailable")

    offset = load_offset()
    footprints = load_footprints()
    ground, reference = load_anchor_scores()
    frames = load_frames()
    views = load_view_rows()
    model = AsymmetricMASt3R.from_pretrained(str(args.model_dir)).to(args.device)
    model.eval()

    rows: list[dict[str, Any]] = []
    details: dict[str, list[dict[str, Any]]] = {}
    figures: list[Path] = []
    for short in TARGETS:
        pair_rows: list[dict[str, Any]] = []
        pair_details: list[dict[str, Any]] = []
        selected = select_pairs(views[short])
        for rank, pair in enumerate(selected, start=1):
            row, detail = measure_pair(
                model,
                short,
                rank,
                pair,
                frames,
                footprints[full_id(short)],
                offset,
                ground[short],
                reference[short],
                args.device,
            )
            pair_rows.append(row)
            pair_details.append(detail)
            print(
                f"{short} rank={rank} {row['view_a']}->{row['view_b']} "
                f"status={row['status']} inliers={row['joint_pnp_inlier_count']} "
                f"inside={row['footprint_inside_count']}"
            )
        rows.extend(pair_rows)
        rows.append(summary_row(short, pair_rows, ground[short], reference[short]))
        details[short] = pair_details
        figures.append(make_figure(short, pair_details[0], footprints[full_id(short)], offset, reference[short]))

    fields = [
        "row_type", "building_id", "pair_rank", "view_a", "view_b", "address_support_a",
        "address_support_b", "pair_selection_min_address_support", "pair_selection_sum_address_support",
        "crop_box_a_xyxy", "crop_box_b_xyxy", "reciprocal_match_count", "border_finite_match_count",
        "crop_gauge_pnp_inlier_a_count", "crop_gauge_pnp_inlier_b_count", "joint_pnp_inlier_count",
        "joint_pnp_inlier_fraction", "predicted_camera_baseline_model_units", "known_colmap_baseline_m",
        "similarity_scale_m_per_model_unit", "camera_rotation_consistency_deg_qa",
        "aligned_camera_center_residual_m_qa",
        "pose_alignment_method", "reconstructed_candidate_count", "footprint_inside_count",
        "roof_candidate_count", "abs_delta_z_median_m", "abs_delta_z_within_pair_mad_m",
        "abs_delta_z_within_pair_std_m", "abs_delta_z_across_pair_mad_m", "footprint_outside_count",
        "footprint_outside_rate", "ground_z_q10_local_m", "reference_roof_z_local_m",
        "selected_pair_count", "completed_pair_count", "status", "failure_reason",
        "view_pair_selection_rule", "candidate_rule", "score_rule", "gt_role", "learning_runs_started",
    ]
    write_csv(OUT_CSV, [{key: fmt(row.get(key)) for key in fields} for row in rows], fields)
    RUN_DIR.mkdir(parents=True, exist_ok=True)
    serializable = {short: [serializable_detail(item) for item in items] for short, items in details.items()}
    PAIR_JSON.write_text(json.dumps(serializable, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    source_paths = [
        PJPL, FOOTPRINTS, TRAIN_MANIFEST, ANCHOR_CSV, ENV_MANIFEST,
        SPARSE_DIR / "cameras.bin", SPARSE_DIR / "images.bin",
        *[frames[view["stem"]]["path"] for per_building in views.values() for view in per_building],
        *[REGION_DIR / f"{view['stem']}.npz" for per_building in views.values() for view in per_building],
    ]
    source_hashes = {rel(path): sha256_file(path) for path in sorted(set(source_paths))}
    output_hashes = {rel(path): sha256_file(path) for path in [OUT_CSV, PAIR_JSON, *figures]}
    payload = {
        "schema": "jointbuildgs.s3ap.fm_rescore.v1",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "git_head_at_measurement": git_value("rev-parse", "HEAD"),
        "branch": git_value("branch", "--show-current"),
        "learning_runs_started": 0,
        "model": {"revision": MODEL_REVISION, "weights_sha256": MODEL_SHA256, "weights_bytes": MODEL_BYTES},
        "environment_manifest": rel(ENV_MANIFEST),
        "environment_manifest_sha256": sha256_file(ENV_MANIFEST),
        "targets": TARGETS,
        "locked_visible_views": views,
        "pair_selection_rule": (
            "all locked visible-view combinations; sort by minimum frozen address pixels descending, "
            "then sum descending, view stems ascending; cap 10 per building"
        ),
        "crop_rule": (
            "frozen T0-1 target region bbox only; 32px margin; exact 4:3; min 256x192; "
            "resize exactly 512x384; no result-dependent crop"
        ),
        "match_rule": "reciprocal descriptor NN stride8; 3px border; finite positive pointmaps",
        "pose_and_scale_rule": (
            "PnP recovers both physical cameras in the centered MASt3R crop gauge; COLMAP poses remain fixed; "
            "scale=known/predicted camera-center baseline; rotation=SO(3) mean of the two pose-implied "
            "world rotations; translation=least-squares mean camera-center alignment"
        ),
        "candidate_rule": "joint crop-gauge PnP-inlier paired pointmap mean transformed by the camera-aligned similarity; no footprint/LoD2 filter",
        "scoring_rule": (
            "footprint containment and exterior leakage after reconstruction; roof candidates additionally "
            "z>=observed exterior-ring ground q10+1.5m; LoD2 used only for absolute z error"
        ),
        "source_sha256": source_hashes,
        "script_sha256": sha256_file(Path(__file__).resolve()),
        "output_sha256": output_hashes,
        "row_count": len(rows),
        "pair_row_count": sum(row["row_type"] == "view_pair" for row in rows),
        "building_summary_count": sum(row["row_type"] == "building_summary" for row in rows),
        "gt_separation": (
            "The frozen gate region selects the requested input crop. Footprint and LoD2 reference z are first "
            "applied after camera-aligned reconstruction and only produce score columns/figure overlays."
        ),
        "no_seed_or_training_use": True,
        "interpretation_or_verdict": None,
    }
    MANIFEST.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {rel(OUT_CSV)} rows={len(rows)}")
    for figure in figures:
        print(f"wrote {rel(figure)}")
    print(f"wrote {rel(PAIR_JSON)}")
    print(f"wrote {rel(MANIFEST)}")


if __name__ == "__main__":
    main()
