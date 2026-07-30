#!/usr/bin/env python3
"""S3-A Track 0 semantic-region cache and reference-only label QA.

This script has three deliberately separate provenance tracks:

* The S3-A loss address is the fixed C001 clean roof mask (class 1), split by
  the raycast building-ID map generated with the *same observed datum as that
  mask* (48.0 m geoid, ``shift_z = 556.0``).  Only the discrete building ID is
  retained in ``region_ids``.  Ray distance, intersection XYZ, LoD2 z, and
  LoD2 height are never stored as a loss-value input.
* The current clean-label raster is first reproduced with its observed legacy
  generation datum.  Exact per-view class reproduction is a precondition for
  using its building ID as the class+instance oracle address.
* The former +20 m projected-footprint rule is still evaluated and written as
  a one-time defect baseline.  The official 45.7 m datum is likewise retained
  only as an audit.  Neither audit changes the oracle address.

For every C001 image stem, the cache contains:

* ``region_ids``: HxW int32, zero means excluded;
* ``cutline_mask``: HxW bool, the two-sided 7 px instance cut band;
* ``metadata_json``: scalar JSON with the locked constants, input hashes,
  region-to-building mapping, and both raycast assignment checks.

T0-1 is emitted as ``reference_only/self_consistency``.  It never emits a GO
or rejection verdict.  This is explicitly an oracle class+instance-address
mechanism upper bound, not a model-free S3-B claim.  S3-B must not reuse the
raycast building-ID address.
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
import subprocess
import sys
import time
from collections import defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable, Iterator, Sequence

import cv2
import numpy as np
import open3d as o3d
import scipy
import yaml
from PIL import Image as PILImage
from PIL import ImageDraw, ImageFont
from scipy import ndimage
from shapely import contains_xy
from shapely.geometry import MultiPolygon, Polygon, shape
from shapely.ops import unary_union

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

from src.stage2.colmap_io import (  # noqa: E402
    Camera,
    Image,
    read_cameras_bin,
    read_images_bin,
    read_points3d_bin,
)


def _load_clean_label_module():
    path = REPO / "phases/p2-gsjso/scripts/make_clean_labels.py"
    spec = importlib.util.spec_from_file_location("s3_make_clean_labels", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


MCL = _load_clean_label_module()

DEFAULT_DATA_ROOT = REPO / "results/tum_transfer/e5_pilot/C001/data_geoidfix_C001_buf20"
DEFAULT_FOOTPRINTS = REPO / "results/tum_transfer/analysis/footprints_aoi.geojson"
DEFAULT_DATUM_CONFIG = REPO / "configs/input_and_alignment/projection_datum.json"
DEFAULT_GML = [
    REPO / "phases/p0-audit/data/raw/lod2/690_5334.gml",
    REPO / "phases/p0-audit/data/raw/lod2/690_5336.gml",
]
DEFAULT_CACHE = REPO / "results/tum_transfer/e5_s3/C001/semantic_regions"
DEFAULT_FIG_DIR = REPO / "docs/figs/e5_c001_s3/semantic_gate"
DEFAULT_RUN_DIR = REPO / "phases/p2-gsjso/runs/20260713_e5_c001_s3_track0"
DEFAULT_DENSE_INIT = REPO / "results/tum_transfer/e5_pilot/C001/seeds/seed_dense_C001_buf20.ply"
DEFAULT_ARM1P_CONFIG = (
    REPO / "configs/e5_c001/e5_s2p_interaction/gs_e5_C001_s2p_arm1p_dense_r1.yaml"
)

CORE9 = [
    "DEBY_LOD2_8568391",
    "DEBY_LOD2_8568392",
    "DEBY_LOD2_4907199",
    "DEBY_LOD2_4907184",
    "DEBY_LOD2_4907185",
    "DEBY_LOD2_4907198",
    "DEBY_LOD2_4907202",
    "DEBY_LOD2_4908168",
    "DEBY_LOD2_4908178",
]
TEXTURELESS3 = CORE9[:3]

CANONICAL_VIEW_COUNT = 428
SOURCE_COMPONENT_MIN_PIXELS = 256
FRAGMENT_MEASURE_MIN_PIXELS = 64
PLANE_MIN_PIXELS = 64
REGION_FOOTPRINT_BUFFER_M = 20.0
CUTLINE_HALF_WIDTH_PX = 7
QA_FOOTPRINT_BUFFER_M = 1.0
LEGACY_LABEL_GEOID_M = 48.0
DOCKER_IMAGE_ID_ENV = "S3_DOCKER_IMAGE_ID"
PRIORITY_CROP_MARGIN_PX = 32
PRIORITY_CROP_MIN_SIDE_PX = 256
PRIORITY_CONTACT_TILE_WH = (480, 360)

ASSIGNMENT_RULE = (
    "eligible class-1 8-connected source component pixels are assigned to "
    "the exact Arm1-prime C00118 projected +20m footprint candidates at the "
    "per-building Arm1-prime zero-iteration input-point median z; source_count=0 "
    "candidates are zero-source exclusion-only owners at global-median z; all overlap "
    "pixels choose one winner by projected unbuffered-footprint pixel distance with "
    "lexical building_id tie-break; active winners become positive regions and inactive "
    "winners map to region 0"
)
ORACLE_ADDRESS_RULE = (
    "fixed clean class-1 mask; discard source 8-connected components below 256 px; "
    "within each retained component assign only the discrete building ID from the "
    "actual clean-label-source raycast (geoid 48.0 m, shift_z 556.0); restrict IDs "
    "to exact Arm1-prime C00118; exclude exactly 7 px on both sides of ID cuts"
)
EXPERIMENT_SCOPE = (
    "S3-A oracle class label plus oracle instance-address mechanism upper bound; "
    "not model-free and not an S3-B/FM result; S3-B forbids the oracle ID address"
)
FOOTPRINT_ROLE = (
    "footprint XY is retained only to reproduce the pre-adjudication +20 m rule's "
    "assignment-defect baseline and T0-1 crop; it is not the v3 loss address"
)
QA_BUFFER_RATIONALE = (
    "1.0 m absorbs footprint/roof-eave and sub-pixel projection rounding while remaining "
    "far below the locked 20.0 m loss-region split buffer and avoiding adjacent-roof capture"
)
QA_BUFFER_ROLE = (
    "T0-1 audit-only implementation choice; not a loss address, training prior, "
    "or pass/fail threshold"
)


@dataclass(frozen=True)
class Frame:
    name: str
    stem: str
    camera: Camera
    image: Image
    R: np.ndarray
    t: np.ndarray


@dataclass
class GateMeasurement:
    building_id: str
    view_stem: str
    view_name: str
    ref_pixels: int
    clean_clipped_pixels: int
    intersection_pixels: int
    union_pixels: int
    iou: float
    fragment_count_ge64: int
    boundary_offset_px: float
    boundary_offset_defined: bool
    boundary_offset_status: str
    jacobian_m_per_px_x: float
    jacobian_m_per_px_y: float
    jacobian_m_per_px: float
    boundary_offset_m: float
    roof_height_local_m: float


def sha256_file(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            block = f.read(chunk)
            if not block:
                break
            h.update(block)
    return h.hexdigest()


def sha256_json(value: Any) -> str:
    payload = json.dumps(
        value, sort_keys=True, ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(REPO.resolve()))
    except ValueError:
        return str(path.resolve())


def json_number(value: float | int | np.number | None) -> float | int | None:
    if value is None:
        return None
    out = value.item() if isinstance(value, np.generic) else value
    if isinstance(out, float) and not math.isfinite(out):
        return None
    return out


def write_csv(path: Path, rows: list[dict[str, Any]], fields: Sequence[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if fields is None:
        fields = []
        seen: set[str] = set()
        for row in rows:
            for key in row:
                if key not in seen:
                    seen.add(key)
                    fields.append(key)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=list(fields),
            extrasaction="ignore",
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(rows)


def git_value(*args: str) -> str:
    try:
        return subprocess.check_output(["git", *args], cwd=REPO, text=True).strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def load_frames(data_root: Path) -> list[Frame]:
    sparse = data_root / "sparse"
    if (sparse / "0/cameras.bin").exists():
        sparse = sparse / "0"
    cameras = read_cameras_bin(sparse / "cameras.bin")
    images = read_images_bin(sparse / "images.bin")
    frames: list[Frame] = []
    for image in images.values():
        if not (data_root / "images" / image.name).exists():
            continue
        camera = cameras[image.camera_id]
        frames.append(
            Frame(
                name=image.name,
                stem=Path(image.name).stem,
                camera=camera,
                image=image,
                R=image.R(),
                t=image.tvec.copy(),
            )
        )
    frames.sort(key=lambda f: f.name)
    if not frames:
        raise RuntimeError(f"no COLMAP/image intersection under {data_root}")
    return frames


def load_footprints(path: Path) -> tuple[dict[str, Polygon | MultiPolygon], dict[str, int]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    parts: dict[str, list[Polygon | MultiPolygon]] = defaultdict(list)
    for feature in payload.get("features", []):
        building_id = str(feature.get("properties", {}).get("building_id", ""))
        if not building_id:
            continue
        geom = shape(feature["geometry"])
        if geom.is_empty:
            continue
        if not geom.is_valid:
            geom = geom.buffer(0)
        if isinstance(geom, (Polygon, MultiPolygon)) and not geom.is_empty:
            parts[building_id].append(geom)
    merged: dict[str, Polygon | MultiPolygon] = {}
    part_counts: dict[str, int] = {}
    for building_id, geoms in parts.items():
        geom = unary_union(geoms)
        if not isinstance(geom, (Polygon, MultiPolygon)):
            polygonal = [g for g in getattr(geom, "geoms", []) if isinstance(g, (Polygon, MultiPolygon))]
            geom = unary_union(polygonal)
        if isinstance(geom, (Polygon, MultiPolygon)) and not geom.is_empty:
            merged[building_id] = geom
            part_counts[building_id] = len(geoms)
    return merged, part_counts


def arm1p_candidate_buildings(path: Path) -> list[str]:
    """Load the exact loss-address candidate set from the locked Arm 1' base."""

    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Arm1-prime config must be a YAML object: {path}")
    raw = payload.get("seed_log_buildings")
    if not isinstance(raw, list) or not all(isinstance(v, str) and v for v in raw):
        raise ValueError(f"{path}: seed_log_buildings must be a non-empty string list")
    building_ids = list(raw)
    if len(building_ids) != 18 or len(set(building_ids)) != 18:
        raise AssertionError(
            f"S3-A loss address requires exact unique C00118 from Arm1-prime config; "
            f"got len={len(building_ids)}, unique={len(set(building_ids))}"
        )
    return building_ids


def load_xyz_ply(path: Path) -> np.ndarray:
    cloud = o3d.io.read_point_cloud(str(path))
    # Training initializes means as float32; quantize before any footprint clip
    # or z statistic so this audit follows the identical input precision.
    xyz = np.asarray(cloud.points).astype(np.float32, copy=False)
    if xyz.ndim != 2 or xyz.shape[1] != 3 or len(xyz) == 0:
        raise RuntimeError(f"empty or invalid point cloud: {path}")
    return xyz


def points_strictly_in_footprint(
    xyz_local: np.ndarray,
    geom: Polygon | MultiPolygon,
    xy_shift: np.ndarray,
) -> np.ndarray:
    """Strict 2D footprint clip; boundary points are intentionally excluded."""

    minx, miny, maxx, maxy = geom.bounds
    # The training centres are float32, but restoring the large EPSG:25832
    # offset in float32 quantises Y by roughly 0.5 m.  Promote first so this
    # clip is identical to the locked T0-2 inventory definition and does not
    # move edge-near seeds across a footprint merely through UTM arithmetic.
    x_utm = xyz_local[:, 0].astype(np.float64) + float(xy_shift[0])
    y_utm = xyz_local[:, 1].astype(np.float64) + float(xy_shift[1])
    bbox = (x_utm >= minx) & (x_utm <= maxx) & (y_utm >= miny) & (y_utm <= maxy)
    selected = np.flatnonzero(bbox)
    if len(selected) == 0:
        return np.zeros(len(xyz_local), dtype=bool)
    inside = np.zeros(len(xyz_local), dtype=bool)
    inside[selected] = contains_xy(geom, x_utm[selected], y_utm[selected])
    return inside


def input_derived_projection_heights(
    footprints: dict[str, Polygon | MultiPolygon],
    sparse_xyz: np.ndarray,
    dense_xyz: np.ndarray,
    xy_shift: np.ndarray,
) -> tuple[dict[str, dict[str, Any]], float]:
    """Arm 1' zero-iteration input median z per unbuffered footprint.

    The estimator is locked and untuned.  A building with zero combined input
    points is *inactive* for positive loss addressing.  The global initial-point
    median places an exclusion-only competition candidate and never creates a
    positive region.
    """

    if sparse_xyz.dtype != np.float32 or dense_xyz.dtype != np.float32:
        raise AssertionError(
            f"projection-height inputs must match training float32; "
            f"got sparse={sparse_xyz.dtype}, dense={dense_xyz.dtype}"
        )
    initial_xyz = np.vstack([sparse_xyz, dense_xyz])
    global_median = float(np.median(initial_xyz[:, 2]))
    inventory: dict[str, dict[str, Any]] = {}
    for building_id in sorted(footprints):
        geom = footprints[building_id]
        sparse_mask = points_strictly_in_footprint(sparse_xyz, geom, xy_shift)
        dense_mask = points_strictly_in_footprint(dense_xyz, geom, xy_shift)
        sparse_z = sparse_xyz[sparse_mask, 2]
        dense_z = dense_xyz[dense_mask, 2]
        count = int(len(sparse_z) + len(dense_z))
        if count:
            source_z = np.concatenate([sparse_z, dense_z]).astype(np.float32, copy=False)
            q10, q50, q90 = (float(v) for v in np.quantile(source_z, [0.10, 0.50, 0.90]))
            mad = float(np.median(np.abs(source_z - np.float32(q50))))
            estimated: float | None = q50
            active = True
            estimator = "median(combined Arm1-prime 0-iter sparse points3D + dense-init points inside unbuffered footprint)"
            inactive_reason = None
            exclusion_only_global = None
        else:
            q10 = q50 = q90 = mad = None
            estimated = None
            active = False
            estimator = "none; candidate inactive because no Arm1-prime initial point lies in footprint"
            inactive_reason = "zero Arm1p initial points; P-L-style no-material branch"
            exclusion_only_global = global_median
        inventory[building_id] = {
            "estimated_z_local_m": estimated,
            "source_z_q10_local_m": q10,
            "source_z_q50_local_m": q50,
            "source_z_q90_local_m": q90,
            "source_z_mad_m": mad,
            "sparse_points3d_count": int(len(sparse_z)),
            "dense_init_point_count": int(len(dense_z)),
            "source_count": count,
            "active_for_loss_address": active,
            "inactive_reason": inactive_reason,
            "fallback_used": False,
            "zero_source_exclusion_only_global_median_z_local_m": exclusion_only_global,
            "estimator": estimator,
            "xy_clip": "strict unbuffered footprint contains_xy; boundary excluded",
            "input_dtype": (
                "float32 training centres; promoted to float64 before EPSG:25832 "
                "offset restoration and footprint clip"
            ),
            "height_source_role": (
                "existing Arm1-prime zero-iteration training input; no LoD2 z; "
                "global median may place only the source_count=0 exclusion/veto and "
                "never activates a positive loss region"
            ),
        }
    return inventory, global_median


def polygons(geom: Polygon | MultiPolygon) -> Iterator[Polygon]:
    if isinstance(geom, Polygon):
        yield geom
    elif isinstance(geom, MultiPolygon):
        yield from geom.geoms


def densify_ring(coords: Iterable[Sequence[float]], max_step_m: float = 0.5) -> np.ndarray:
    pts = np.asarray([(float(p[0]), float(p[1])) for p in coords], dtype=np.float64)
    if len(pts) < 3:
        return pts
    if not np.allclose(pts[0], pts[-1]):
        pts = np.vstack([pts, pts[0]])
    out: list[np.ndarray] = []
    for a, b in zip(pts[:-1], pts[1:]):
        length = float(np.linalg.norm(b - a))
        n = max(1, int(math.ceil(length / max_step_m)))
        for k in range(n):
            out.append(a + (b - a) * (k / n))
    return np.asarray(out, dtype=np.float64)


def project_xy(
    xy_utm: np.ndarray,
    z_local: float,
    frame: Frame,
    xy_shift: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    xyz = np.column_stack(
        [xy_utm[:, 0] - xy_shift[0], xy_utm[:, 1] - xy_shift[1], np.full(len(xy_utm), z_local)]
    )
    cam_xyz = xyz @ frame.R.T + frame.t[None, :]
    z = cam_xyz[:, 2]
    K = frame.camera.K()
    uv = np.empty((len(xy_utm), 2), dtype=np.float64)
    uv[:, 0] = K[0, 0] * cam_xyz[:, 0] / z + K[0, 2]
    uv[:, 1] = K[1, 1] * cam_xyz[:, 1] / z + K[1, 2]
    return uv, z


def rasterize_geometry(
    geom: Polygon | MultiPolygon,
    z_local: float,
    frame: Frame,
    xy_shift: np.ndarray,
) -> np.ndarray:
    H, W = int(frame.camera.height), int(frame.camera.width)
    result = np.zeros((H, W), dtype=np.uint8)
    for poly in polygons(geom):
        exterior = densify_ring(poly.exterior.coords)
        if len(exterior) < 3:
            continue
        uv, z = project_xy(exterior, z_local, frame, xy_shift)
        if np.any(z <= 1e-6) or not np.all(np.isfinite(uv)):
            continue
        if uv[:, 0].max() < -1 or uv[:, 0].min() > W or uv[:, 1].max() < -1 or uv[:, 1].min() > H:
            continue
        if float(np.max(np.abs(uv))) > 1e7:
            continue
        local = np.zeros((H, W), dtype=np.uint8)
        cv2.fillPoly(local, [np.rint(uv).astype(np.int32)], 1)
        for interior in poly.interiors:
            hole = densify_ring(interior.coords)
            if len(hole) < 3:
                continue
            huv, hz = project_xy(hole, z_local, frame, xy_shift)
            if np.any(hz <= 1e-6) or not np.all(np.isfinite(huv)):
                continue
            cv2.fillPoly(local, [np.rint(huv).astype(np.int32)], 0)
        result |= local
    return result.astype(bool)


def roof_heights(rings: Sequence[tuple[str, int, np.ndarray]]) -> dict[str, float]:
    z_by_bid: dict[str, list[np.ndarray]] = defaultdict(list)
    for building_id, class_id, ring in rings:
        if class_id == 1:
            z_by_bid[building_id].append(np.asarray(ring[:, 2], dtype=np.float64))
    return {
        building_id: float(np.median(np.concatenate(values)))
        for building_id, values in z_by_bid.items()
        if values
    }


def class_alignment(current: np.ndarray, regenerated: np.ndarray) -> dict[str, Any]:
    if current.shape != regenerated.shape:
        raise AssertionError(f"class alignment shape mismatch: {current.shape} vs {regenerated.shape}")
    roof_current = current == 1
    roof_regen = regenerated == 1
    union = int(np.logical_or(roof_current, roof_regen).sum())
    intersection = int(np.logical_and(roof_current, roof_regen).sum())
    return {
        "class_agreement": float(np.mean(current == regenerated)),
        "roof_iou": float(intersection / union) if union else 1.0,
        "mismatch_pixels": int(np.sum(current != regenerated)),
        "total_pixels": int(current.size),
        "current_roof_pixels": int(roof_current.sum()),
        "regenerated_roof_pixels": int(roof_regen.sum()),
    }


def shifted_rays(rays_official: np.ndarray, shift_z: float, official_shift_z: float) -> np.ndarray:
    if abs(shift_z - official_shift_z) < 1e-12:
        return rays_official
    rays = rays_official.copy()
    rays[:, 2] += float(shift_z - official_shift_z)
    return rays


def source_components(roof_mask: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    labels, _ = ndimage.label(roof_mask, structure=np.ones((3, 3), dtype=np.uint8))
    counts = np.bincount(labels.ravel())
    eligible = (labels > 0) & (counts[labels] >= SOURCE_COMPONENT_MIN_PIXELS)
    return labels.astype(np.int32), counts.astype(np.int64), eligible


def different_owner_boundary(owner: np.ndarray) -> np.ndarray:
    seed = np.zeros(owner.shape, dtype=bool)
    H, W = owner.shape
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            if dx == 0 and dy == 0:
                continue
            y0a, y1a = max(0, dy), min(H, H + dy)
            x0a, x1a = max(0, dx), min(W, W + dx)
            y0b, y1b = max(0, -dy), min(H, H - dy)
            x0b, x1b = max(0, -dx), min(W, W - dx)
            a = owner[y0a:y1a, x0a:x1a]
            b = owner[y0b:y1b, x0b:x1b]
            diff = (a > 0) & (b > 0) & (a != b)
            seed[y0a:y1a, x0a:x1a] |= diff
            seed[y0b:y1b, x0b:x1b] |= diff
    return seed


def two_sided_cutline_band(owner: np.ndarray, half_width_px: int) -> np.ndarray:
    """Return exactly ``half_width_px`` pixels inside each owner at a cut.

    A discrete cut lies *between* two pixel centres.  ``different_owner_boundary``
    therefore marks one pixel on each side.  Dilating that two-column seed with
    a literal 15x15 kernel would remove 8+8 columns, not the locked 7+7.  We use
    the equivalent sub-pixel-cut definition: on each owner independently keep
    Chebyshev distances 0..half_width-1 from its boundary-side seed.  A straight
    cut consequently removes exactly seven columns per owner (14 total) while
    preserving a deterministic square-band metric at corners.
    """

    if half_width_px <= 0:
        return np.zeros(owner.shape, dtype=bool)
    boundary = different_owner_boundary(owner)
    cutline = np.zeros(owner.shape, dtype=bool)
    for owner_id in (int(v) for v in np.unique(owner) if int(v) > 0):
        side_seed = boundary & (owner == owner_id)
        if not np.any(side_seed):
            continue
        distance = ndimage.distance_transform_cdt(~side_seed, metric="chessboard")
        cutline |= (owner == owner_id) & (distance >= 0) & (distance < half_width_px)
    return cutline


def validate_cutline_exactness() -> dict[str, Any]:
    """Synthetic straight-cut QA for the locked exactly-7-pixels-per-side rule."""

    owner = np.zeros((31, 40), dtype=np.int32)
    owner[:, :20] = 1
    owner[:, 20:] = 2
    cutline = two_sided_cutline_band(owner, CUTLINE_HALF_WIDTH_PX)
    owner1_columns = np.flatnonzero(np.any(cutline & (owner == 1), axis=0))
    owner2_columns = np.flatnonzero(np.any(cutline & (owner == 2), axis=0))
    metrics = {
        "synthetic_shape_hw": [31, 40],
        "straight_cut_between_columns": [19, 20],
        "owner1_cut_columns": owner1_columns.tolist(),
        "owner2_cut_columns": owner2_columns.tolist(),
        "owner1_width_px": int(len(owner1_columns)),
        "owner2_width_px": int(len(owner2_columns)),
        "total_width_px": int(len(np.union1d(owner1_columns, owner2_columns))),
        "expected_each_side_px": CUTLINE_HALF_WIDTH_PX,
        "status": "pass",
    }
    if (
        metrics["owner1_width_px"] != CUTLINE_HALF_WIDTH_PX
        or metrics["owner2_width_px"] != CUTLINE_HALF_WIDTH_PX
        or metrics["total_width_px"] != 2 * CUTLINE_HALF_WIDTH_PX
    ):
        metrics["status"] = "fail"
        raise AssertionError(f"straight-cut exact-width QA failed: {metrics}")
    return metrics


def build_footprint_regions(
    clean_roof: np.ndarray,
    frame: Frame,
    footprints: dict[str, Polygon | MultiPolygon],
    buffered_footprints: dict[str, Polygon | MultiPolygon],
    projection_heights: dict[str, dict[str, Any]],
    xy_shift: np.ndarray,
    building_ids: list[str],
) -> tuple[
    np.ndarray,
    np.ndarray,
    list[dict[str, Any]],
    dict[str, Any],
    np.ndarray,
    np.ndarray,
    np.ndarray,
]:
    component_ids, component_counts, eligible = source_components(clean_roof)
    H, W = clean_roof.shape
    # Active and zero-material candidates participate in the *same* buffered
    # overlap competition.  Distance to the projected unbuffered footprint
    # selects one winner per pixel.  An inactive winner becomes exclusion-only
    # (region id 0); it never blankets the full +20 m mask before competition.
    candidates: list[tuple[int, str, bool, np.ndarray, np.ndarray]] = []
    inactive_veto_buildings_projected: list[str] = []
    for owner_id, building_id in enumerate(building_ids, start=1):
        height_row = projection_heights[building_id]
        active = bool(height_row["active_for_loss_address"])
        z_value = (
            height_row["estimated_z_local_m"]
            if active
            else height_row["zero_source_exclusion_only_global_median_z_local_m"]
        )
        if z_value is None:
            continue
        z_local = float(z_value)
        buffered = rasterize_geometry(buffered_footprints[building_id], z_local, frame, xy_shift)
        intersects = buffered & eligible
        if not np.any(intersects):
            continue
        unbuffered = rasterize_geometry(footprints[building_id], z_local, frame, xy_shift)
        candidates.append((owner_id, building_id, active, buffered, unbuffered))
        if not active:
            inactive_veto_buildings_projected.append(building_id)

    candidate_count = np.zeros((H, W), dtype=np.uint16)
    for _, _, _, buffered, _ in candidates:
        candidate_count += (buffered & eligible).astype(np.uint16)

    winner_owner = np.zeros((H, W), dtype=np.int32)
    single = eligible & (candidate_count == 1)
    for owner_id, _, _, buffered, _ in candidates:
        winner_owner[single & buffered] = owner_id

    multiple = eligible & (candidate_count > 1)
    if np.any(multiple):
        best_distance = np.full((H, W), np.inf, dtype=np.float32)
        # candidates are in lexical building-id order; strict less-than keeps that tie-break.
        for owner_id, _, _, buffered, unbuffered in candidates:
            relevant = multiple & buffered
            if not np.any(relevant):
                continue
            distance = ndimage.distance_transform_edt(~unbuffered).astype(np.float32)
            take = relevant & (distance < best_distance)
            winner_owner[take] = owner_id
            best_distance[take] = distance[take]

    active_owner_ids = {
        owner_id for owner_id, _, active, _, _ in candidates if active
    }
    inactive_owner_ids = {
        owner_id for owner_id, _, active, _, _ in candidates if not active
    }
    inactive_veto_mask = np.isin(winner_owner, list(inactive_owner_ids)) & eligible
    owner = winner_owner.copy()
    owner[~np.isin(owner, list(active_owner_ids))] = 0

    overlap_counts: dict[int, int] = {}
    positive_components = np.unique(component_ids[eligible])
    for source_component_id in positive_components.tolist():
        component = component_ids == source_component_id
        overlap_counts[int(source_component_id)] = int(
            sum(bool(np.any(buffered & component)) for _, _, _, buffered, _ in candidates)
        )

    raw_cutline_mask = two_sided_cutline_band(winner_owner, CUTLINE_HALF_WIDTH_PX)
    # Inactive winners remain veto (including their side of the nominal cut);
    # only active winner pixels need the explicit smooth/plane cutline mask.
    cutline_mask = raw_cutline_mask & (~inactive_veto_mask)
    owner_after_cut = owner.copy()
    owner_after_cut[cutline_mask] = 0

    region_ids = np.zeros((H, W), dtype=np.int32)
    regions: list[dict[str, Any]] = []
    next_region_id = 1
    owner_to_bid = {i + 1: b for i, b in enumerate(building_ids)}
    for source_component_id in sorted(int(v) for v in positive_components):
        source_mask = component_ids == source_component_id
        source_pixel_count = int(component_counts[source_component_id])
        for owner_id in sorted(int(v) for v in np.unique(owner[source_mask]) if int(v) > 0):
            pair_before_cut = source_mask & (owner == owner_id)
            pair_after_cut = source_mask & (owner_after_cut == owner_id)
            fragments, n_fragments = ndimage.label(pair_after_cut, structure=np.ones((3, 3), dtype=np.uint8))
            for fragment_index in range(1, int(n_fragments) + 1):
                fragment = fragments == fragment_index
                pixel_count = int(fragment.sum())
                if pixel_count == 0:
                    continue
                region_ids[fragment] = next_region_id
                regions.append(
                    {
                        "region_id": next_region_id,
                        "building_id": owner_to_bid[owner_id],
                        "source_component_id": source_component_id,
                        "source_component_pixel_count": source_pixel_count,
                        "pre_split_overlap_count": overlap_counts[source_component_id],
                        "pre_cut_pair_pixel_count": int(pair_before_cut.sum()),
                        "post_cut_fragment_pixel_count": pixel_count,
                        "fragment_index": fragment_index,
                        "post_split_fragment_min_pixels": None,
                        "plane_loss_min_valid_pixels": PLANE_MIN_PIXELS,
                        "projection_z_local_m": float(
                            projection_heights[owner_to_bid[owner_id]]["estimated_z_local_m"]
                        ),
                        "projection_height_source_count": int(
                            projection_heights[owner_to_bid[owner_id]]["source_count"]
                        ),
                        "projection_height_sparse_points3d_count": int(
                            projection_heights[owner_to_bid[owner_id]]["sparse_points3d_count"]
                        ),
                        "projection_height_dense_init_point_count": int(
                            projection_heights[owner_to_bid[owner_id]]["dense_init_point_count"]
                        ),
                        "projection_height_fallback_used": bool(
                            projection_heights[owner_to_bid[owner_id]]["fallback_used"]
                        ),
                        "projection_height_active_for_loss_address": bool(
                            projection_heights[owner_to_bid[owner_id]]["active_for_loss_address"]
                        ),
                        "projection_height_source_z_q10_local_m": projection_heights[
                            owner_to_bid[owner_id]
                        ]["source_z_q10_local_m"],
                        "projection_height_source_z_q50_local_m": projection_heights[
                            owner_to_bid[owner_id]
                        ]["source_z_q50_local_m"],
                        "projection_height_source_z_q90_local_m": projection_heights[
                            owner_to_bid[owner_id]
                        ]["source_z_q90_local_m"],
                        "projection_height_source_z_mad_m": projection_heights[
                            owner_to_bid[owner_id]
                        ]["source_z_mad_m"],
                        "projection_height_estimator": projection_heights[owner_to_bid[owner_id]][
                            "estimator"
                        ],
                        "projection_height_source_role": projection_heights[owner_to_bid[owner_id]][
                            "height_source_role"
                        ],
                    }
                )
                next_region_id += 1

    stats = {
        "source_components_total": int(len(component_counts) - 1),
        "source_components_eligible_ge256": int(len(positive_components)),
        "source_components_excluded_lt256": int(
            sum(1 for c in component_counts[1:] if int(c) < SOURCE_COMPONENT_MIN_PIXELS)
        ),
        "source_roof_pixels": int(clean_roof.sum()),
        "eligible_source_pixels": int(eligible.sum()),
        "unassigned_eligible_pixels_excluding_inactive_veto": int(
            (eligible & (~inactive_veto_mask) & (owner == 0)).sum()
        ),
        "inactive_veto_pixels": int(inactive_veto_mask.sum()),
        "inactive_veto_buildings_projected": inactive_veto_buildings_projected,
        "inactive_veto_rule": (
            "source_count=0 competes once with active +20m candidates by nearest "
            "projected unbuffered footprint; inactive winner is region_id=0/exclusion-only"
        ),
        "candidate_footprints_projected": int(len(candidates)),
        "candidate_footprints_active_projected": int(
            sum(int(active) for _, _, active, _, _ in candidates)
        ),
        "candidate_footprints_inactive_veto_projected": int(
            sum(int(not active) for _, _, active, _, _ in candidates)
        ),
        "candidate_footprints_configured": int(len(building_ids)),
        "candidate_footprints_inactive_zero_source": int(
            sum(not bool(projection_heights[building_id]["active_for_loss_address"]) for building_id in building_ids)
        ),
        "candidate_footprints_using_global_height_fallback": 0,
        "candidate_overlap_pixels": int(multiple.sum()),
        "source_component_footprint_overlap_counts": {
            str(component_id): int(count)
            for component_id, count in sorted(overlap_counts.items())
        },
        "raw_two_sided_cutline_pixels_before_inactive_veto_precedence": int(
            raw_cutline_mask.sum()
        ),
        "cutline_pixels": int(cutline_mask.sum()),
        "effective_depth_loss_excluded_pixels_cutline_or_inactive_veto": int(
            np.logical_or(cutline_mask, inactive_veto_mask).sum()
        ),
        "regions_after_cut": int(len(regions)),
        "region_pixels_after_cut": int((region_ids > 0).sum()),
    }
    return (
        region_ids,
        cutline_mask.astype(bool),
        regions,
        stats,
        owner,
        eligible,
        inactive_veto_mask,
    )


def raycast_owner_map(
    address_mask: np.ndarray,
    ray_bidmap: np.ndarray,
    bid_owner_lookup: np.ndarray,
) -> np.ndarray:
    """Map a raycast building index to the locked C00118 owner id.

    The result is a discrete address only.  No hit distance, intersection XYZ,
    roof z, or height is accepted by this function or returned from it.
    """

    if address_mask.shape != ray_bidmap.shape:
        raise ValueError("address_mask and ray_bidmap must have the same HxW shape")
    owner = np.zeros(ray_bidmap.shape, dtype=np.int32)
    valid_hit = (
        address_mask.astype(bool, copy=False)
        & (ray_bidmap >= 0)
        & (ray_bidmap < int(len(bid_owner_lookup)))
    )
    owner[valid_hit] = bid_owner_lookup[ray_bidmap[valid_hit]]
    return owner


def build_oracle_id_regions(
    clean_roof: np.ndarray,
    actual_label: np.ndarray,
    actual_bidmap: np.ndarray,
    bid_owner_lookup: np.ndarray,
    building_ids: list[str],
    footprint_overlap_counts: dict[int, int],
) -> tuple[
    np.ndarray,
    np.ndarray,
    list[dict[str, Any]],
    dict[str, Any],
    np.ndarray,
    np.ndarray,
    np.ndarray,
]:
    """Split retained clean-label components by the actual-source building ID.

    This is the adjudicated S3-A B rule.  ``actual_bidmap`` supplies only a
    categorical owner address.  The output contains no geometric value from
    the LoD2 raycast.  The former footprint candidate overlap count is carried
    into each region strictly as audit metadata.
    """

    if clean_roof.shape != actual_label.shape or clean_roof.shape != actual_bidmap.shape:
        raise ValueError("clean mask and actual-source raycast arrays must share HxW")
    alignment = class_alignment(clean_roof.astype(np.uint8), (actual_label == 1).astype(np.uint8))

    component_ids, component_counts, eligible = source_components(clean_roof)
    # The saved clean PNG remains authoritative for class membership.  The
    # same-datum raycast contributes only its discrete building ID; it never
    # replaces the class mask, even at a raster-edge rounding mismatch.
    owner = raycast_owner_map(clean_roof, actual_bidmap, bid_owner_lookup)
    owner[~eligible] = 0
    cutline_mask = two_sided_cutline_band(owner, CUTLINE_HALF_WIDTH_PX)
    owner_after_cut = owner.copy()
    owner_after_cut[cutline_mask] = 0

    positive_components = np.unique(component_ids[eligible])
    owner_to_bid = {i + 1: b for i, b in enumerate(building_ids)}
    region_ids = np.zeros(clean_roof.shape, dtype=np.int32)
    regions: list[dict[str, Any]] = []
    next_region_id = 1
    for source_component_id in sorted(int(v) for v in positive_components):
        source_mask = component_ids == source_component_id
        source_pixel_count = int(component_counts[source_component_id])
        source_owner_ids = sorted(
            int(v) for v in np.unique(owner[source_mask]) if int(v) > 0
        )
        oracle_instance_count = len(source_owner_ids)
        for owner_id in source_owner_ids:
            pair_before_cut = source_mask & (owner == owner_id)
            pair_after_cut = source_mask & (owner_after_cut == owner_id)
            fragments, n_fragments = ndimage.label(
                pair_after_cut, structure=np.ones((3, 3), dtype=np.uint8)
            )
            for fragment_index in range(1, int(n_fragments) + 1):
                fragment = fragments == fragment_index
                pixel_count = int(fragment.sum())
                if pixel_count == 0:
                    continue
                region_ids[fragment] = next_region_id
                regions.append(
                    {
                        "region_id": next_region_id,
                        "building_id": owner_to_bid[owner_id],
                        "source_component_id": source_component_id,
                        "source_component_pixel_count": source_pixel_count,
                        "pre_split_overlap_count": int(
                            footprint_overlap_counts.get(source_component_id, 0)
                        ),
                        "pre_split_oracle_instance_count": oracle_instance_count,
                        "pre_cut_pair_pixel_count": int(pair_before_cut.sum()),
                        "post_cut_fragment_pixel_count": pixel_count,
                        "fragment_index": fragment_index,
                        "post_split_fragment_min_pixels": None,
                        "plane_loss_min_valid_pixels": PLANE_MIN_PIXELS,
                        "address_source": "actual_label_source_raycast_building_id_only",
                        "address_geoid_m": LEGACY_LABEL_GEOID_M,
                        "address_shift_z_m": 556.0,
                        "lod2_depth_or_height_loss_input": False,
                    }
                )
                next_region_id += 1

    unassigned = eligible & (owner == 0)
    stats = {
        "source_components_total": int(len(component_counts) - 1),
        "source_components_eligible_ge256": int(len(positive_components)),
        "source_components_excluded_lt256": int(
            sum(1 for count in component_counts[1:] if int(count) < SOURCE_COMPONENT_MIN_PIXELS)
        ),
        "source_roof_pixels": int(clean_roof.sum()),
        "eligible_source_pixels": int(eligible.sum()),
        "unassigned_eligible_pixels_outside_c00118_or_missing_id": int(unassigned.sum()),
        "oracle_owner_pixels_before_cut": int((owner > 0).sum()),
        "cutline_pixels": int(cutline_mask.sum()),
        "regions_after_cut": int(len(regions)),
        "region_pixels_after_cut": int((region_ids > 0).sum()),
        "address_mode": "oracle_class_plus_raycast_building_id",
        "address_datum_geoid_m": LEGACY_LABEL_GEOID_M,
        "address_datum_shift_z_m": 556.0,
        "actual_source_class_agreement": alignment["class_agreement"],
        "actual_source_roof_iou": alignment["roof_iou"],
        "actual_source_class_mismatch_pixels": alignment["mismatch_pixels"],
        "fixed_clean_class_mask_is_authoritative": True,
        "lod2_depth_or_height_loss_input": False,
    }
    # Kept in the common return position for assignment_check compatibility.
    no_inactive_veto = np.zeros(clean_roof.shape, dtype=bool)
    return (
        region_ids,
        cutline_mask.astype(bool),
        regions,
        stats,
        owner,
        eligible,
        no_inactive_veto,
    )


def mesh_bid_to_owner(bids: Sequence[str], building_ids: Sequence[str]) -> np.ndarray:
    owner_of = {building_id: i + 1 for i, building_id in enumerate(building_ids)}
    return np.asarray([owner_of.get(building_id, 0) for building_id in bids], dtype=np.int32)


def assignment_check(
    owner: np.ndarray,
    cutline_mask: np.ndarray,
    eligible: np.ndarray,
    inactive_veto_mask: np.ndarray,
    ray_label: np.ndarray,
    ray_bidmap: np.ndarray,
    bid_owner_lookup: np.ndarray,
    building_ids: Sequence[str],
    provenance: str,
    shift_z_m: float,
    *,
    raycast_building_id_is_loss_input: bool = False,
) -> dict[str, Any]:
    """Audit an owner assignment against one raycast building-ID map.

    Counts are emitted per C00118 building as well as pooled.  The partition is
    exact on eligible true-roof pixels:

    ``eligible = correct + wrong + unassigned(no owner) + cutline_excluded +
    inactive_veto_excluded``.
    """

    true_owner = np.zeros(ray_bidmap.shape, dtype=np.int32)
    hit = ray_bidmap >= 0
    true_owner[hit] = bid_owner_lookup[ray_bidmap[hit]]

    def counts_for(expected_owner: int | None) -> dict[str, Any]:
        if expected_owner is None:
            true_roof = (ray_label == 1) & (true_owner > 0)
            true_owner_values = true_owner
        else:
            true_roof = (ray_label == 1) & (true_owner == expected_owner)
            true_owner_values = np.full(true_owner.shape, expected_owner, dtype=np.int32)
        eligible_true = true_roof & eligible
        cut = eligible_true & cutline_mask
        veto = eligible_true & inactive_veto_mask
        if np.any(cut & veto):
            raise AssertionError("cutline and inactive-veto masks must be disjoint")
        comparable = eligible_true & (~cutline_mask) & (~inactive_veto_mask)
        correct = comparable & (owner == true_owner_values)
        wrong = comparable & (owner > 0) & (owner != true_owner_values)
        unassigned = comparable & (owner == 0)
        true_n = int(true_roof.sum())
        eligible_n = int(eligible_true.sum())
        cut_n = int(cut.sum())
        veto_n = int(veto.sum())
        correct_n = int(correct.sum())
        wrong_n = int(wrong.sum())
        unassigned_n = int(unassigned.sum())
        assigned_n = correct_n + wrong_n
        if eligible_n != correct_n + wrong_n + unassigned_n + cut_n + veto_n:
            raise AssertionError(
                "raycast assignment partition failed: "
                f"eligible={eligible_n}, correct={correct_n}, wrong={wrong_n}, "
                f"unassigned={unassigned_n}, cutline={cut_n}, veto={veto_n}"
            )
        eligible_after_exclusions = eligible_n - cut_n - veto_n
        wrong_owner_values, wrong_owner_counts = np.unique(owner[wrong], return_counts=True)
        wrong_confusion = {
            building_ids[int(owner_id) - 1]: int(count)
            for owner_id, count in zip(wrong_owner_values.tolist(), wrong_owner_counts.tolist())
            if int(owner_id) > 0
        }
        return {
            "true_roof_total": true_n,
            "eligible_ge256_true_roof": eligible_n,
            "correct": correct_n,
            "wrong": wrong_n,
            "unassigned_no_owner": unassigned_n,
            "cutline_excluded": cut_n,
            "inactive_veto_excluded": veto_n,
            "assigned": assigned_n,
            "assigned_coverage_of_eligible": (
                float(assigned_n / eligible_n) if eligible_n else None
            ),
            "assigned_coverage_excluding_cutline_and_veto": (
                float(assigned_n / eligible_after_exclusions)
                if eligible_after_exclusions
                else None
            ),
            "conditional_misassignment_rate": (
                float(wrong_n / assigned_n) if assigned_n else None
            ),
            "wrong_assigned_owner_confusion": wrong_confusion,
        }

    by_building = {
        building_id: counts_for(owner_id)
        for owner_id, building_id in enumerate(building_ids, start=1)
    }
    return {
        "provenance": provenance,
        "shift_z_m": float(shift_z_m),
        "totals": counts_for(None),
        "by_building": by_building,
        "raycast_building_id_is_loss_input": bool(raycast_building_id_is_loss_input),
    }


def binary_boundary(mask: np.ndarray) -> np.ndarray:
    if not np.any(mask):
        return np.zeros(mask.shape, dtype=bool)
    eroded = ndimage.binary_erosion(mask, structure=np.ones((3, 3), dtype=bool), border_value=0)
    return mask & ~eroded


def local_projection_jacobian(
    frame: Frame,
    z_local: float,
    u: float,
    v: float,
) -> tuple[float, float, float]:
    K = frame.camera.K()
    C = -frame.R.T @ frame.t

    def intersect(px: float, py: float) -> np.ndarray | None:
        d_cam = np.array([(px + 0.5 - K[0, 2]) / K[0, 0], (py + 0.5 - K[1, 2]) / K[1, 1], 1.0])
        d_world = frame.R.T @ d_cam
        if abs(float(d_world[2])) < 1e-12:
            return None
        scale = (z_local - C[2]) / d_world[2]
        if scale <= 0:
            return None
        return C + scale * d_world

    p = intersect(u, v)
    px = intersect(u + 1.0, v)
    py = intersect(u, v + 1.0)
    if p is None or px is None or py is None:
        return float("nan"), float("nan"), float("nan")
    mx = float(np.linalg.norm(px[:2] - p[:2]))
    my = float(np.linalg.norm(py[:2] - p[:2]))
    return mx, my, math.sqrt(mx * my)


def gate_measurement(
    building_id: str,
    frame: Frame,
    clean_roof: np.ndarray,
    ref_mask: np.ndarray,
    qa_mask: np.ndarray,
    roof_height_local: float,
) -> GateMeasurement:
    measured = clean_roof & qa_mask
    intersection = int(np.logical_and(measured, ref_mask).sum())
    union = int(np.logical_or(measured, ref_mask).sum())
    iou = float(intersection / union) if union else float("nan")

    fragments, n_fragments = ndimage.label(measured, structure=np.ones((3, 3), dtype=np.uint8))
    fragment_count = 0
    for fragment_id in range(1, int(n_fragments) + 1):
        fragment = fragments == fragment_id
        if int(fragment.sum()) >= FRAGMENT_MEASURE_MIN_PIXELS and np.any(fragment & ref_mask):
            fragment_count += 1

    ref_boundary = binary_boundary(ref_mask)
    measured_boundary = binary_boundary(measured)
    if np.any(ref_boundary) and np.any(measured_boundary):
        distance = ndimage.distance_transform_edt(~measured_boundary)
        boundary_offset_px = float(np.median(distance[ref_boundary]))
        boundary_offset_defined = True
        boundary_offset_status = "defined"
    else:
        boundary_offset_px = float("nan")
        boundary_offset_defined = False
        if not np.any(ref_boundary) and not np.any(measured_boundary):
            boundary_offset_status = "undefined_no_reference_or_measured_boundary"
        elif not np.any(ref_boundary):
            boundary_offset_status = "undefined_no_reference_boundary"
        else:
            boundary_offset_status = "undefined_no_measured_boundary"

    ys, xs = np.nonzero(ref_mask)
    if len(xs):
        u = float(np.median(xs))
        v = float(np.median(ys))
        mx, my, mpp = local_projection_jacobian(frame, roof_height_local, u, v)
    else:
        mx = my = mpp = float("nan")
    offset_m = boundary_offset_px * mpp if math.isfinite(boundary_offset_px) and math.isfinite(mpp) else float("nan")
    return GateMeasurement(
        building_id=building_id,
        view_stem=frame.stem,
        view_name=frame.name,
        ref_pixels=int(ref_mask.sum()),
        clean_clipped_pixels=int(measured.sum()),
        intersection_pixels=intersection,
        union_pixels=union,
        iou=iou,
        fragment_count_ge64=fragment_count,
        boundary_offset_px=boundary_offset_px,
        boundary_offset_defined=boundary_offset_defined,
        boundary_offset_status=boundary_offset_status,
        jacobian_m_per_px_x=mx,
        jacobian_m_per_px_y=my,
        jacobian_m_per_px=mpp,
        boundary_offset_m=offset_m,
        roof_height_local_m=roof_height_local,
    )


def select_gate_candidates(
    measurements: Sequence[GateMeasurement],
    core_buildings: Sequence[str],
    selected_count: int,
    *,
    official_geoid_m: float,
    official_shift_z_m: float,
    label_actual_source_shift_z_m: float,
) -> tuple[dict[str, list[GateMeasurement]], list[dict[str, Any]]]:
    """Select deterministic primary views and retain the full candidate audit."""

    if selected_count < 0:
        raise ValueError("selected_count must be nonnegative")
    selected_by_building: dict[str, list[GateMeasurement]] = {}
    candidate_rows: list[dict[str, Any]] = []
    for building_id in core_buildings:
        candidates = [
            m
            for m in measurements
            if m.building_id == building_id and int(m.ref_pixels) > 0
        ]
        candidates.sort(key=lambda m: (-m.ref_pixels, m.view_stem))
        selected = candidates[:selected_count]
        if len(selected) < selected_count:
            raise AssertionError(
                f"{building_id}: only {len(selected)} visible views with P_ref > 0; "
                f"need {selected_count}"
            )
        selected_by_building[building_id] = selected
        selected_low_support_count = sum(
            int(measurement.ref_pixels) < FRAGMENT_MEASURE_MIN_PIXELS
            for measurement in selected
        )
        for rank, measurement in enumerate(candidates, start=1):
            payload = asdict(measurement)
            candidate_rows.append(
                {
                    "measurement_role": "reference_only",
                    "gate_role": "self_consistency_not_a_gate",
                    "decision": "not_applicable",
                    "row_type": "view_candidate",
                    "building_id": building_id,
                    "view_stem": measurement.view_stem,
                    "view_name": measurement.view_name,
                    "rank_by_ref_area": rank,
                    "selected_for_primary": rank <= selected_count,
                    "selected_top3_by_reference_area": (
                        selected_count == 3 and rank <= 3
                    ),
                    "ref_support_ge64": (
                        int(measurement.ref_pixels) >= FRAGMENT_MEASURE_MIN_PIXELS
                    ),
                    "ref_support_scope": "this_view",
                    "selected_low_support_count": selected_low_support_count,
                    "visible_view_count_available": len(candidates),
                    **{
                        key: json_number(value)
                        for key, value in payload.items()
                        if key not in {"building_id", "view_stem", "view_name"}
                    },
                    "qa_footprint_buffer_m": QA_FOOTPRINT_BUFFER_M,
                    "qa_buffer_rationale": QA_BUFFER_RATIONALE,
                    "qa_buffer_role": QA_BUFFER_ROLE,
                    "view_selection_rule": (
                        "visible iff official P_ref > 0; top 3 deterministic views by "
                        "official P_ref roof pixel area; tie by view stem"
                    ),
                    "official_geoid_m": official_geoid_m,
                    "official_shift_z_m": official_shift_z_m,
                    "label_actual_source_shift_z_m": label_actual_source_shift_z_m,
                }
            )
    return selected_by_building, candidate_rows


def mask_centroid_xy(mask: np.ndarray) -> tuple[float, float] | None:
    ys, xs = np.nonzero(mask)
    if not len(xs):
        return None
    return float(np.mean(xs)), float(np.mean(ys))


def projection_height_view_audit(
    building_id: str,
    frame: Frame,
    footprint: Polygon | MultiPolygon,
    projection_height: dict[str, Any],
    reference_z_local_m: float,
    xy_shift: np.ndarray,
) -> dict[str, Any] | None:
    """Compare locked input-z and audit-only LoD2-z footprint projections."""

    active = bool(projection_height["active_for_loss_address"])
    input_z = projection_height["estimated_z_local_m"]
    exclusion_only_z = projection_height[
        "zero_source_exclusion_only_global_median_z_local_m"
    ]
    projection_z = input_z if active else exclusion_only_z
    if projection_z is None:
        return None
    input_mask = rasterize_geometry(footprint, float(projection_z), frame, xy_shift)
    reference_mask = rasterize_geometry(footprint, float(reference_z_local_m), frame, xy_shift)
    ref_pixels = int(reference_mask.sum())
    if ref_pixels < FRAGMENT_MEASURE_MIN_PIXELS:
        return None
    input_pixels = int(input_mask.sum())
    intersection = int(np.logical_and(input_mask, reference_mask).sum())
    union = int(np.logical_or(input_mask, reference_mask).sum())
    input_centroid = mask_centroid_xy(input_mask)
    reference_centroid = mask_centroid_xy(reference_mask)
    if input_centroid is None or reference_centroid is None:
        centroid_shift = None
    else:
        centroid_shift = float(np.linalg.norm(np.subtract(input_centroid, reference_centroid)))
    return {
        "row_type": "view_candidate",
        "building_id": building_id,
        "view_stem": frame.stem,
        "loss_address_active": active,
        "projection_role": (
            "loss_address_locked_input_median_z"
            if active
            else (
                "global-median candidate places exclusion/veto only; building remains "
                "unassigned and receives no positive loss region"
            )
        ),
        "source_count": int(projection_height["source_count"]),
        "input_projection_z_local_m": input_z,
        "zero_source_exclusion_only_global_median_z_local_m": exclusion_only_z,
        "reference_projection_z_local_m": float(reference_z_local_m),
        "projection_z_minus_reference_m": float(projection_z - reference_z_local_m),
        "reference_mask_pixels": ref_pixels,
        "input_mask_pixels": input_pixels,
        "intersection_pixels": intersection,
        "union_pixels": union,
        "footprint_mask_iou": float(intersection / union) if union else None,
        "centroid_shift_px": centroid_shift,
        "input_over_reference_pixel_coverage": (
            float(input_pixels / ref_pixels) if ref_pixels else None
        ),
        "tuning": "none; input median locked before reference comparison",
        "reference_role": "audit only; LoD2 z is never a loss-address input",
    }


def _ui_font(size: int) -> ImageFont.ImageFont:
    try:
        return ImageFont.truetype("DejaVuSans.ttf", size=size)
    except OSError:
        return ImageFont.load_default()


def ref_support_label(ref_pixels: int) -> str:
    if int(ref_pixels) < FRAGMENT_MEASURE_MIN_PIXELS:
        return (
            f"LOW SUPPORT | P_ref {int(ref_pixels)} px "
            f"(<{FRAGMENT_MEASURE_MIN_PIXELS}; audit-only)"
        )
    return f"P_ref support: {int(ref_pixels)} px (>={FRAGMENT_MEASURE_MIN_PIXELS})"


def boundary_offset_label(measurement: GateMeasurement) -> str:
    if measurement.boundary_offset_defined:
        return (
            f"Boundary offset: {measurement.boundary_offset_px:.3f} px / "
            f"{measurement.boundary_offset_m:.3f} m"
        )
    return f"Boundary offset: UNDEFINED ({measurement.boundary_offset_status})"


def render_overlay(
    out_path: Path,
    image_path: Path,
    measured: np.ndarray,
    ref_mask: np.ndarray,
    measurement: GateMeasurement,
    *,
    selected_low_support_count: int,
) -> PILImage.Image:
    image = np.asarray(PILImage.open(image_path).convert("RGB"), dtype=np.uint8)
    blend = image.astype(np.float32)
    blend[measured] = 0.60 * blend[measured] + 0.40 * np.array([230, 55, 55], dtype=np.float32)
    ref_boundary = binary_boundary(ref_mask)
    measured_boundary = binary_boundary(measured)
    blend[measured_boundary] = np.array([255, 80, 80], dtype=np.float32)
    blend[ref_boundary] = np.array([0, 235, 255], dtype=np.float32)
    canvas = PILImage.fromarray(np.clip(blend, 0, 255).astype(np.uint8))
    draw = ImageDraw.Draw(canvas)
    font = _ui_font(13)
    lines = [
        "S3-A T0-1 | reference only / self-consistency",
        f"Building: {measurement.building_id} | View: {measurement.view_stem}",
        (
            f"{ref_support_label(measurement.ref_pixels)} | "
            f"Selected low-support views: {selected_low_support_count}"
        ),
        f"IoU: {measurement.iou:.4f} | Fragments >=64 px: {measurement.fragment_count_ge64}",
        boundary_offset_label(measurement),
        "Red: fixed clean roof (legacy 48.0 source) | Cyan: official 45.7 LoD2 reference",
        "+1.0 m footprint clip: T0-1 audit-only implementation choice",
    ]
    y = 5
    for line in lines:
        bbox = draw.textbbox((5, y), line, font=font)
        draw.rectangle((bbox[0] - 2, bbox[1] - 1, bbox[2] + 2, bbox[3] + 1), fill=(0, 0, 0))
        draw.text((5, y), line, fill=(255, 255, 255), font=font)
        y = bbox[3] + 4
    out_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(out_path)
    return canvas


def priority_crop_box(
    measured: np.ndarray,
    ref_mask: np.ndarray,
    *,
    margin_px: int = PRIORITY_CROP_MARGIN_PX,
    min_side_px: int = PRIORITY_CROP_MIN_SIDE_PX,
) -> tuple[tuple[int, int, int, int], bool]:
    """Return a deterministic padded union crop and whether the target hits a frame edge."""

    if measured.shape != ref_mask.shape or measured.ndim != 2:
        raise ValueError("measured and ref_mask must share one HxW shape")
    if margin_px < 0 or min_side_px <= 0:
        raise ValueError("margin_px must be nonnegative and min_side_px positive")
    union = measured.astype(bool, copy=False) | ref_mask.astype(bool, copy=False)
    ys, xs = np.nonzero(union)
    if not len(xs):
        raise ValueError("priority crop requires a nonempty measured/reference union")
    height, width = union.shape
    target_touches_frame = bool(
        np.any(xs == 0)
        or np.any(xs == width - 1)
        or np.any(ys == 0)
        or np.any(ys == height - 1)
    )

    def bounds(lo: int, hi_exclusive: int, limit: int) -> tuple[int, int]:
        desired = min(limit, max(hi_exclusive - lo + 2 * margin_px, min_side_px))
        center = 0.5 * (lo + hi_exclusive)
        start = int(math.floor(center - 0.5 * desired))
        start = max(0, min(start, limit - desired))
        return start, start + desired

    x0, x1 = bounds(int(xs.min()), int(xs.max()) + 1, width)
    y0, y1 = bounds(int(ys.min()), int(ys.max()) + 1, height)
    return (x0, y0, x1, y1), target_touches_frame


def render_priority_crop(
    out_path: Path,
    overlay: PILImage.Image,
    crop_box: tuple[int, int, int, int],
    measurement: GateMeasurement,
    rank: int,
    *,
    target_touches_frame: bool,
    selected_low_support_count: int,
) -> PILImage.Image:
    crop = overlay.crop(crop_box)
    header_height = 82
    canvas_width = max(crop.width, 520)
    canvas = PILImage.new(
        "RGB", (canvas_width, crop.height + header_height), color=(12, 12, 12)
    )
    canvas.paste(crop, ((canvas_width - crop.width) // 2, header_height))
    draw = ImageDraw.Draw(canvas)
    font = _ui_font(14)
    short_id = measurement.building_id.removeprefix("DEBY_LOD2_")
    lines = [
        f"Building {short_id} | Rank {rank} | {measurement.view_stem}",
        (
            f"{ref_support_label(measurement.ref_pixels)} | "
            f"Selected low-support views: {selected_low_support_count}"
        ),
        (
            f"IoU {measurement.iou:.4f} | Fragments {measurement.fragment_count_ge64} | "
            + (
                f"Offset {measurement.boundary_offset_px:.3f} px / "
                f"{measurement.boundary_offset_m:.3f} m"
                if measurement.boundary_offset_defined
                else f"Offset UNDEFINED ({measurement.boundary_offset_status})"
            )
            + (" | FRAME EDGE" if target_touches_frame else "")
        ),
    ]
    y = 5
    for line in lines:
        draw.text((7, y), line, fill=(255, 255, 255), font=font)
        bbox = draw.textbbox((7, y), line, font=font)
        y = bbox[3] + 4
    out_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(out_path)
    return canvas


def make_textureless_contact_sheet(
    priority_paths: dict[tuple[str, int], Path],
    out_path: Path,
    *,
    selected_low_support_count: int = 0,
) -> PILImage.Image:
    """Create the locked 3-buildings by 3-ranked-views visual QA sheet."""

    expected = {(building_id, rank) for building_id in TEXTURELESS3 for rank in (1, 2, 3)}
    if set(priority_paths) != expected:
        missing = sorted(expected - set(priority_paths))
        extra = sorted(set(priority_paths) - expected)
        raise AssertionError(f"priority contact sheet key mismatch: missing={missing}, extra={extra}")
    tile_width, tile_height = PRIORITY_CONTACT_TILE_WH
    title_height = 84
    sheet = PILImage.new(
        "RGB", (tile_width * 3, title_height + tile_height * 3), color=(245, 245, 245)
    )
    draw = ImageDraw.Draw(sheet)
    title_font = _ui_font(18)
    draw.text(
        (10, 7),
        "S3-A T0-1 textureless priority gallery (reference-only; no gate verdict)",
        fill=(0, 0, 0),
        font=title_font,
    )
    draw.text(
        (10, 33),
        "Red = fixed clean roof (legacy 48.0 source); Cyan = official 45.7 LoD2 reference",
        fill=(0, 0, 0),
        font=_ui_font(13),
    )
    draw.text(
        (10, 55),
        (
            f"LOW SUPPORT = P_ref <{FRAGMENT_MEASURE_MIN_PIXELS} px; audit-only | "
            f"Selected low-support views: {selected_low_support_count}"
        ),
        fill=(0, 0, 0),
        font=_ui_font(13),
    )
    resampling = getattr(PILImage, "Resampling", PILImage).LANCZOS
    for row_index, building_id in enumerate(TEXTURELESS3):
        for column_index, rank in enumerate((1, 2, 3)):
            path = priority_paths[(building_id, rank)]
            with PILImage.open(path) as source:
                tile = source.convert("RGB")
            tile.thumbnail((tile_width - 12, tile_height - 12), resampling)
            x = column_index * tile_width + (tile_width - tile.width) // 2
            y = title_height + row_index * tile_height + (tile_height - tile.height) // 2
            sheet.paste(tile, (x, y))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out_path)
    return sheet


def image_artifact(
    path: Path,
    *,
    kind: str,
    building_id: str | None = None,
    view_stem: str | None = None,
    rank: int | None = None,
    crop_box_xyxy: tuple[int, int, int, int] | None = None,
    target_touches_frame: bool | None = None,
    ref_support_ge64: bool | None = None,
    selected_low_support_count: int | None = None,
    support_label: str | None = None,
) -> dict[str, Any]:
    with PILImage.open(path) as image:
        image.load()
        width, height = image.size
        image_format = image.format
    if image_format != "PNG" or width <= 0 or height <= 0:
        raise AssertionError(f"invalid PNG artifact: {path}")
    return {
        "kind": kind,
        "building_id": building_id,
        "view_stem": view_stem,
        "rank": rank,
        "path": rel(path),
        "sha256": sha256_file(path),
        "width_px": int(width),
        "height_px": int(height),
        "crop_box_xyxy": list(crop_box_xyxy) if crop_box_xyxy is not None else None,
        "target_touches_frame": target_touches_frame,
        "ref_support_ge64": ref_support_ge64,
        "selected_low_support_count": selected_low_support_count,
        "support_label": support_label,
    }


def validate_run_mode_contract(
    *,
    debug_subset: bool,
    frame_count: int,
    core_buildings: Sequence[str],
    views_per_building: int,
    skip_overlays: bool,
    legacy_label_geoid_m: float,
) -> dict[str, Any]:
    """Keep canonical production strict while preserving explicit debug/smoke modes."""

    if not math.isclose(legacy_label_geoid_m, LEGACY_LABEL_GEOID_M, abs_tol=1e-9):
        raise AssertionError("actual label-source geoid must remain 48.0 m")
    if debug_subset:
        return {
            "mode": "debug_subset",
            "canonical_guards_applied": False,
            "frame_count": int(frame_count),
            "core_buildings": list(core_buildings),
            "views_per_building": int(views_per_building),
            "overlays_enabled": not skip_overlays,
        }
    errors: list[str] = []
    if frame_count != CANONICAL_VIEW_COUNT:
        errors.append(f"frame_count={frame_count}, expected={CANONICAL_VIEW_COUNT}")
    if list(core_buildings) != CORE9:
        errors.append("core_buildings must equal the locked ordered CORE9")
    if views_per_building != 3:
        errors.append(f"views_per_building={views_per_building}, expected=3")
    if skip_overlays:
        errors.append("canonical T0-1 forbids --skip-overlays")
    if errors:
        raise AssertionError("canonical S3-A T0-1 contract failed: " + "; ".join(errors))
    return {
        "mode": "canonical_full",
        "canonical_guards_applied": True,
        "frame_count": int(frame_count),
        "core_buildings": list(core_buildings),
        "views_per_building": int(views_per_building),
        "overlays_enabled": True,
        "label_source_geoid_m": float(legacy_label_geoid_m),
    }


def validate_t0_1_outputs(
    *,
    gate_rows: Sequence[dict[str, Any]],
    candidate_rows: Sequence[dict[str, Any]],
    core_buildings: Sequence[str],
    views_per_building: int,
    overlay_artifacts: Sequence[dict[str, Any]],
    fig_dir: Path,
    debug_subset: bool,
    skip_overlays: bool,
) -> dict[str, Any]:
    """Self-validate quantitative/qualitative T0-1 outputs before gate use."""

    metric_names = [
        "ref_pixels",
        "clean_clipped_pixels",
        "intersection_pixels",
        "union_pixels",
        "iou",
        "fragment_count_ge64",
        "boundary_offset_px",
        "jacobian_m_per_px_x",
        "jacobian_m_per_px_y",
        "jacobian_m_per_px",
        "boundary_offset_m",
        "roof_height_local_m",
    ]

    candidate_by_building: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in candidate_rows:
        candidate_by_building[str(row["building_id"])].append(dict(row))
    expected_selected: set[tuple[str, str]] = set()
    selected_low_support_by_building: dict[str, int] = {}
    for building_id in core_buildings:
        rows = sorted(
            candidate_by_building.get(building_id, []),
            key=lambda row: int(row["rank_by_ref_area"]),
        )
        expected_order = sorted(
            rows, key=lambda row: (-int(row["ref_pixels"]), str(row["view_stem"]))
        )
        if [row["view_stem"] for row in rows] != [
            row["view_stem"] for row in expected_order
        ]:
            raise AssertionError(f"{building_id}: candidate area/stem ordering mismatch")
        selected_rows = rows[:views_per_building]
        selected_low_support_count = sum(
            int(row["ref_pixels"]) < FRAGMENT_MEASURE_MIN_PIXELS
            for row in selected_rows
        )
        selected_low_support_by_building[building_id] = selected_low_support_count
        for expected_rank, row in enumerate(rows, start=1):
            ref_pixels = int(row["ref_pixels"])
            if ref_pixels <= 0:
                raise AssertionError(
                    f"{building_id}: candidate visibility requires official P_ref > 0"
                )
            expected_support = ref_pixels >= FRAGMENT_MEASURE_MIN_PIXELS
            if bool(row.get("ref_support_ge64")) is not expected_support:
                raise AssertionError(f"{building_id}: candidate ref-support flag mismatch")
            if row.get("ref_support_scope") != "this_view":
                raise AssertionError(f"{building_id}: candidate ref-support scope mismatch")
            if int(row.get("selected_low_support_count", -1)) != selected_low_support_count:
                raise AssertionError(
                    f"{building_id}: candidate selected-low-support count mismatch"
                )
            boundary_defined = bool(row.get("boundary_offset_defined"))
            boundary_status = str(row.get("boundary_offset_status"))
            boundary_px = row.get("boundary_offset_px")
            boundary_m = row.get("boundary_offset_m")
            if boundary_defined:
                if boundary_status != "defined":
                    raise AssertionError(f"{building_id}: defined candidate boundary status mismatch")
                for value in (boundary_px, boundary_m):
                    if value is None or not math.isfinite(float(value)) or float(value) < 0:
                        raise AssertionError(f"{building_id}: defined candidate boundary is invalid")
            elif not boundary_status.startswith("undefined_"):
                raise AssertionError(f"{building_id}: undefined candidate boundary status mismatch")
            elif boundary_px is not None or boundary_m is not None:
                raise AssertionError(f"{building_id}: undefined candidate boundary must stay null")
            if int(row["rank_by_ref_area"]) != expected_rank:
                raise AssertionError(f"{building_id}: candidate ranks are not contiguous")
            expected_flag = expected_rank <= views_per_building
            if bool(row["selected_for_primary"]) is not expected_flag:
                raise AssertionError(f"{building_id}: selected_for_primary disagrees with rank")
            if expected_flag:
                expected_selected.add((building_id, str(row["view_stem"])))
        if len(rows) < views_per_building:
            raise AssertionError(f"{building_id}: candidate audit has fewer than selected views")

    view_rows = [dict(row) for row in gate_rows if row.get("row_type") == "view"]
    median_rows = [
        dict(row) for row in gate_rows if row.get("row_type") == "building_median"
    ]
    observed_selected = {(str(row["building_id"]), str(row["view_stem"])) for row in view_rows}
    if observed_selected != expected_selected:
        raise AssertionError("primary gate rows do not match candidate selected flags")
    for row in view_rows:
        if (
            row.get("measurement_role") != "reference_only"
            or row.get("gate_role") != "self_consistency_not_a_gate"
            or row.get("decision") != "not_applicable"
        ):
            raise AssertionError("T0-1 rows must remain reference-only and non-gating")
        ref_pixels = int(row["ref_pixels"])
        measured_pixels = int(row["clean_clipped_pixels"])
        intersection = int(row["intersection_pixels"])
        union = int(row["union_pixels"])
        if ref_pixels <= 0 or measured_pixels < 0:
            raise AssertionError("selected T0-1 view has invalid pixel support")
        expected_support = ref_pixels >= FRAGMENT_MEASURE_MIN_PIXELS
        if bool(row.get("ref_support_ge64")) is not expected_support:
            raise AssertionError("selected T0-1 ref-support flag mismatch")
        if row.get("ref_support_scope") != "this_view":
            raise AssertionError("selected T0-1 ref-support scope mismatch")
        building_id = str(row["building_id"])
        if int(row.get("selected_low_support_count", -1)) != (
            selected_low_support_by_building[building_id]
        ):
            raise AssertionError("selected T0-1 low-support count mismatch")
        if intersection < 0 or intersection > min(ref_pixels, measured_pixels):
            raise AssertionError("selected T0-1 intersection is inconsistent")
        if union != ref_pixels + measured_pixels - intersection:
            raise AssertionError("selected T0-1 union is inconsistent")
        iou = float(row["iou"])
        if not math.isfinite(iou) or not 0.0 <= iou <= 1.0:
            raise AssertionError("selected T0-1 IoU is not finite in [0,1]")
        fragments = float(row["fragment_count_ge64"])
        if fragments < 0 or not fragments.is_integer():
            raise AssertionError("selected T0-1 fragment count is not a nonnegative integer")
        for key in (
            "jacobian_m_per_px_x",
            "jacobian_m_per_px_y",
            "jacobian_m_per_px",
        ):
            value = float(row[key])
            if not math.isfinite(value) or value < 0:
                raise AssertionError(f"selected T0-1 {key} is not finite/nonnegative")
        boundary_defined = bool(row.get("boundary_offset_defined"))
        boundary_status = str(row.get("boundary_offset_status"))
        boundary_px = row.get("boundary_offset_px")
        boundary_m = row.get("boundary_offset_m")
        if boundary_defined:
            if boundary_status != "defined":
                raise AssertionError("defined T0-1 boundary status mismatch")
            for key, value in (
                ("boundary_offset_px", boundary_px),
                ("boundary_offset_m", boundary_m),
            ):
                if value is None or not math.isfinite(float(value)) or float(value) < 0:
                    raise AssertionError(f"defined T0-1 {key} is invalid")
        else:
            if not boundary_status.startswith("undefined_"):
                raise AssertionError("undefined T0-1 boundary status mismatch")
            if boundary_px is not None or boundary_m is not None:
                raise AssertionError("undefined T0-1 boundary values must stay null")

    if views_per_building > 0:
        medians_by_building = {str(row["building_id"]): row for row in median_rows}
        if set(medians_by_building) != set(core_buildings):
            raise AssertionError("T0-1 building median coverage mismatch")
        for building_id in core_buildings:
            selected = [row for row in view_rows if row["building_id"] == building_id]
            if len(selected) != views_per_building:
                raise AssertionError(f"{building_id}: primary selected-view count mismatch")
            median = medians_by_building[building_id]
            for key in metric_names:
                finite_values = [
                    float(row[key])
                    for row in selected
                    if row.get(key) is not None and math.isfinite(float(row[key]))
                ]
                expected = float(np.median(finite_values)) if finite_values else None
                actual = median.get(key)
                if expected is None:
                    matches = actual is None
                else:
                    matches = actual is not None and math.isclose(
                        float(actual), expected, rel_tol=1e-9, abs_tol=1e-12
                    )
                if not matches:
                    raise AssertionError(f"{building_id}: median mismatch for {key}")
            selected_low_support_count = selected_low_support_by_building[building_id]
            if int(median.get("selected_low_support_count", -1)) != selected_low_support_count:
                raise AssertionError(f"{building_id}: median low-support count mismatch")
            if bool(median.get("ref_support_ge64")) is not (
                selected_low_support_count == 0
            ):
                raise AssertionError(f"{building_id}: median ref-support flag mismatch")
            if median.get("ref_support_scope") != "all_selected_views":
                raise AssertionError(f"{building_id}: median ref-support scope mismatch")
            boundary_defined_count = sum(
                bool(row["boundary_offset_defined"]) for row in selected
            )
            boundary_undefined_count = len(selected) - boundary_defined_count
            if int(median.get("boundary_offset_defined_view_count", -1)) != (
                boundary_defined_count
            ):
                raise AssertionError(f"{building_id}: median boundary-defined count mismatch")
            if int(median.get("boundary_offset_undefined_view_count", -1)) != (
                boundary_undefined_count
            ):
                raise AssertionError(f"{building_id}: median boundary-undefined count mismatch")
            expected_boundary_defined = boundary_defined_count > 0
            if bool(median.get("boundary_offset_defined")) is not expected_boundary_defined:
                raise AssertionError(f"{building_id}: median boundary-defined flag mismatch")
            expected_boundary_status = (
                f"median_defined_from_{boundary_defined_count}_of_{len(selected)}_selected_views"
                if expected_boundary_defined
                else "undefined_all_selected_views"
            )
            if median.get("boundary_offset_status") != expected_boundary_status:
                raise AssertionError(f"{building_id}: median boundary status mismatch")
    elif gate_rows:
        raise AssertionError("views_per_building=0 must not emit primary gate rows")

    artifacts = [dict(row) for row in overlay_artifacts]
    for artifact in artifacts:
        path = REPO / str(artifact["path"])
        if not path.is_file():
            path = Path(str(artifact["path"]))
        current = image_artifact(
            path,
            kind=str(artifact["kind"]),
            building_id=artifact.get("building_id"),
            view_stem=artifact.get("view_stem"),
            rank=artifact.get("rank"),
            crop_box_xyxy=(
                tuple(int(value) for value in artifact["crop_box_xyxy"])
                if artifact.get("crop_box_xyxy") is not None
                else None
            ),
            target_touches_frame=artifact.get("target_touches_frame"),
            ref_support_ge64=artifact.get("ref_support_ge64"),
            selected_low_support_count=artifact.get("selected_low_support_count"),
            support_label=artifact.get("support_label"),
        )
        if current["sha256"] != artifact.get("sha256"):
            raise AssertionError(f"overlay hash changed during output QA: {path}")

    by_kind: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for artifact in artifacts:
        by_kind[str(artifact["kind"])].append(artifact)
    selected_row_by_key = {
        (str(row["building_id"]), str(row["view_stem"])): row for row in view_rows
    }
    for artifact in [*by_kind["full_overlay"], *by_kind["priority_crop"]]:
        key = (str(artifact["building_id"]), str(artifact["view_stem"]))
        if key not in selected_row_by_key:
            raise AssertionError("overlay artifact does not map to a selected T0-1 view")
        selected_row = selected_row_by_key[key]
        expected_support = bool(selected_row["ref_support_ge64"])
        expected_count = int(selected_row["selected_low_support_count"])
        if artifact.get("ref_support_ge64") is not expected_support:
            raise AssertionError("overlay ref-support flag mismatch")
        if int(artifact.get("selected_low_support_count", -1)) != expected_count:
            raise AssertionError("overlay selected-low-support count mismatch")
        expected_label = ref_support_label(int(selected_row["ref_pixels"]))
        if artifact.get("support_label") != expected_label:
            raise AssertionError("overlay support label mismatch")
    total_selected_low_support = sum(selected_low_support_by_building.values())
    textureless_selected_low_support = sum(
        selected_low_support_by_building.get(building_id, 0)
        for building_id in TEXTURELESS3
    )
    for artifact in by_kind["priority_contact_sheet"]:
        if artifact.get("ref_support_ge64") is not (
            textureless_selected_low_support == 0
        ):
            raise AssertionError("contact-sheet aggregate ref-support flag mismatch")
        if int(artifact.get("selected_low_support_count", -1)) != (
            textureless_selected_low_support
        ):
            raise AssertionError("contact-sheet aggregate low-support count mismatch")
        if artifact.get("support_label") != (
            f"LOW SUPPORT = P_ref <{FRAGMENT_MEASURE_MIN_PIXELS} px; audit-only"
        ):
            raise AssertionError("contact-sheet support label mismatch")
    if skip_overlays:
        if artifacts:
            raise AssertionError("--skip-overlays produced unexpected image artifacts")
    else:
        if len(by_kind["full_overlay"]) != len(expected_selected):
            raise AssertionError("full overlay count does not match selected primary views")

    if not debug_subset:
        if list(core_buildings) != CORE9 or views_per_building != 3:
            raise AssertionError("canonical T0-1 QA requires exact CORE9 x 3")
        if len(candidate_rows) < 27 or len(view_rows) != 27 or len(median_rows) != 9:
            raise AssertionError("canonical T0-1 row contract is not 27 views + 9 medians")
        expected_full_paths = {
            (fig_dir / f"{building_id}__{stem}.png").resolve()
            for building_id, stem in expected_selected
        }
        observed_full_paths = {
            (REPO / str(row["path"])).resolve() for row in by_kind["full_overlay"]
        }
        if observed_full_paths != expected_full_paths:
            raise AssertionError("canonical full overlay path set mismatch")
        immediate_pngs = {path.resolve() for path in fig_dir.glob("*.png")}
        if immediate_pngs != expected_full_paths:
            raise AssertionError("canonical overlay directory has missing/stale immediate PNGs")
        if len(by_kind["priority_crop"]) != 9 or len(by_kind["priority_contact_sheet"]) != 1:
            raise AssertionError("canonical priority gallery must contain 9 crops + 1 contact sheet")
        expected_priority = {
            (building_id, rank) for building_id in TEXTURELESS3 for rank in (1, 2, 3)
        }
        observed_priority = {
            (str(row["building_id"]), int(row["rank"]))
            for row in by_kind["priority_crop"]
        }
        if observed_priority != expected_priority:
            raise AssertionError("canonical priority crop building/rank grid mismatch")
        expected_priority_paths = {
            (REPO / str(row["path"])).resolve()
            for row in [*by_kind["priority_crop"], *by_kind["priority_contact_sheet"]]
        }
        observed_priority_paths = {
            path.resolve() for path in (fig_dir / "priority").glob("*.png")
        }
        if observed_priority_paths != expected_priority_paths:
            raise AssertionError("canonical priority directory has missing/stale PNGs")

    artifact_fingerprint = [
        [str(row["kind"]), str(row["path"]), str(row["sha256"])]
        for row in sorted(artifacts, key=lambda row: (str(row["kind"]), str(row["path"])))
    ]
    return {
        "status": "pass",
        "mode": "debug_subset" if debug_subset else "canonical_full",
        "candidate_rows": len(candidate_rows),
        "primary_view_rows": len(view_rows),
        "building_median_rows": len(median_rows),
        "full_overlay_count": len(by_kind["full_overlay"]),
        "priority_crop_count": len(by_kind["priority_crop"]),
        "priority_contact_sheet_count": len(by_kind["priority_contact_sheet"]),
        "visibility_rule": "official P_ref > 0",
        "ref_support_ge64_threshold_px": FRAGMENT_MEASURE_MIN_PIXELS,
        "selected_low_support_count": total_selected_low_support,
        "selected_low_support_by_building": selected_low_support_by_building,
        "overlay_artifact_aggregate_sha256": sha256_json(artifact_fingerprint),
        "qa_buffer_role": QA_BUFFER_ROLE,
    }


ASSIGNMENT_COUNT_FIELDS = [
    "true_roof_total",
    "eligible_ge256_true_roof",
    "correct",
    "wrong",
    "unassigned_no_owner",
    "cutline_excluded",
    "inactive_veto_excluded",
    "assigned",
]


def assignment_derived(counts: dict[str, int]) -> dict[str, Any]:
    eligible_n = int(counts["eligible_ge256_true_roof"])
    cut_n = int(counts["cutline_excluded"])
    veto_n = int(counts["inactive_veto_excluded"])
    assigned_n = int(counts["assigned"])
    eligible_after_exclusions = eligible_n - cut_n - veto_n
    return {
        **counts,
        "assigned_coverage_of_eligible": float(assigned_n / eligible_n) if eligible_n else None,
        "assigned_coverage_excluding_cutline_and_veto": (
            float(assigned_n / eligible_after_exclusions)
            if eligible_after_exclusions
            else None
        ),
        "conditional_misassignment_rate": (
            float(counts["wrong"] / assigned_n) if assigned_n else None
        ),
    }


def assignment_csv_fields(metrics: dict[str, Any]) -> dict[str, Any]:
    """Flatten one assignment metric block without losing confusion provenance."""

    confusion = dict(metrics.get("wrong_assigned_owner_confusion", {}))
    ranked = sorted(confusion.items(), key=lambda item: (-int(item[1]), item[0]))
    return {
        **{key: value for key, value in metrics.items() if key != "wrong_assigned_owner_confusion"},
        "wrong_assigned_owner_confusion_json": json.dumps(
            confusion, sort_keys=True, ensure_ascii=False, separators=(",", ":")
        ),
        "wrong_top_assigned_owner_id": ranked[0][0] if ranked else None,
        "wrong_top_assigned_owner_count": int(ranked[0][1]) if ranked else 0,
    }


def sum_assignment_counts(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    counts = {field: sum(int(row[field]) for row in rows) for field in ASSIGNMENT_COUNT_FIELDS}
    if counts["eligible_ge256_true_roof"] != (
        counts["correct"]
        + counts["wrong"]
        + counts["unassigned_no_owner"]
        + counts["cutline_excluded"]
        + counts["inactive_veto_excluded"]
    ):
        raise AssertionError(f"aggregate raycast partition failed: {counts}")
    if counts["assigned"] != counts["correct"] + counts["wrong"]:
        raise AssertionError(f"aggregate assigned count failed: {counts}")
    confusion: dict[str, int] = defaultdict(int)
    for row in rows:
        payload = row.get("wrong_assigned_owner_confusion_json", "")
        if not payload:
            continue
        for building_id, count in json.loads(str(payload)).items():
            confusion[str(building_id)] += int(count)
    return {
        **assignment_derived(counts),
        "wrong_assigned_owner_confusion": dict(sorted(confusion.items())),
    }


def upsert_issue(path: Path, issue: dict[str, Any]) -> None:
    rows: list[dict[str, Any]] = []
    if path.exists():
        with path.open(newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
    rows = [r for r in rows if r.get("issue_id") != issue["issue_id"]]
    rows.append(issue)
    fields = [
        "issue_id",
        "date",
        "task",
        "severity",
        "status",
        "summary",
        "evidence",
        "impact",
        "handling",
    ]
    write_csv(path, rows, fields)


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data-root", type=Path, default=DEFAULT_DATA_ROOT)
    ap.add_argument("--footprints", type=Path, default=DEFAULT_FOOTPRINTS)
    ap.add_argument("--datum-config", type=Path, default=DEFAULT_DATUM_CONFIG)
    ap.add_argument("--gml", nargs="+", type=Path, default=DEFAULT_GML)
    ap.add_argument("--dense-init", type=Path, default=DEFAULT_DENSE_INIT)
    ap.add_argument("--arm1p-config", type=Path, default=DEFAULT_ARM1P_CONFIG)
    ap.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE)
    ap.add_argument("--fig-dir", type=Path, default=DEFAULT_FIG_DIR)
    ap.add_argument("--run-dir", type=Path, default=DEFAULT_RUN_DIR)
    ap.add_argument("--docs-dir", type=Path, default=REPO / "docs")
    ap.add_argument("--region-buffer-m", type=float, default=REGION_FOOTPRINT_BUFFER_M)
    ap.add_argument("--qa-buffer-m", type=float, default=QA_FOOTPRINT_BUFFER_M)
    ap.add_argument("--cutline-half-width-px", type=int, default=CUTLINE_HALF_WIDTH_PX)
    ap.add_argument("--source-component-min-pixels", type=int, default=SOURCE_COMPONENT_MIN_PIXELS)
    ap.add_argument("--legacy-label-geoid-m", type=float, default=LEGACY_LABEL_GEOID_M)
    ap.add_argument("--views-per-building", type=int, default=3)
    ap.add_argument("--core-buildings", nargs="+", default=CORE9)
    ap.add_argument("--aoi-margin-m", type=float, default=200.0)
    ap.add_argument("--limit", type=int, default=0, help="debug only: process first N frames")
    ap.add_argument(
        "--view-stems",
        nargs="+",
        default=None,
        help="debug/smoke only: process these exact image stems (mutually exclusive with --limit)",
    )
    ap.add_argument("--skip-overlays", action="store_true")
    return ap.parse_args()


def main() -> int:
    args = parse_args()
    started = time.time()
    debug_subset = bool(args.limit or args.view_stems)
    docker_image_id = os.environ.get(DOCKER_IMAGE_ID_ENV, "").strip()
    docker_digest = docker_image_id.removeprefix("sha256:")
    valid_docker_digest = (
        docker_image_id.startswith("sha256:")
        and len(docker_digest) == 64
        and all(character in "0123456789abcdef" for character in docker_digest.lower())
    )
    if not debug_subset and not valid_docker_digest:
        raise RuntimeError(
            f"canonical producer requires {DOCKER_IMAGE_ID_ENV}=sha256:<64 hex>; "
            "pass the host `docker image inspect --format {{.Id}} jointbuildgs:dev` result"
        )
    # These are implementation locks, not tunable CLI knobs for this order.
    if args.source_component_min_pixels != SOURCE_COMPONENT_MIN_PIXELS:
        raise ValueError("S3-A v3 locks source_component_min_pixels=256")
    if not math.isclose(args.region_buffer_m, REGION_FOOTPRINT_BUFFER_M):
        raise ValueError("S3-A v3 locks footprint-audit buffer=20.0 m")
    if args.cutline_half_width_px != CUTLINE_HALF_WIDTH_PX:
        raise ValueError("S3-A v3 locks cutline half-width=7 px")
    if not math.isclose(args.legacy_label_geoid_m, LEGACY_LABEL_GEOID_M, abs_tol=1e-9):
        raise ValueError("S3-A v3 locks the loss-address label-source geoid to 48.0 m")
    if not math.isclose(args.qa_buffer_m, QA_FOOTPRINT_BUFFER_M):
        raise ValueError(
            "this reproducible T0-1 audit fixes the implementation-choice QA buffer=1.0 m; "
            "it is not a loss address or pass/fail threshold"
        )
    if args.limit and args.view_stems:
        raise ValueError("--limit and --view-stems are mutually exclusive")

    cutline_exactness_qa = validate_cutline_exactness()
    print("[cutline-exactness] " + json.dumps(cutline_exactness_qa, ensure_ascii=False))

    data_root = args.data_root.resolve()
    footprints_path = args.footprints.resolve()
    datum_path = args.datum_config.resolve()
    dense_init_path = args.dense_init.resolve()
    arm1p_config_path = args.arm1p_config.resolve()
    gml_paths = [p.resolve() for p in args.gml]
    for path in [data_root, footprints_path, datum_path, dense_init_path, arm1p_config_path, *gml_paths]:
        if not path.exists():
            raise FileNotFoundError(path)

    datum = json.loads(datum_path.read_text(encoding="utf-8"))
    crs = str(datum["geo_crs"])
    if crs != "EPSG:25832":
        raise AssertionError(f"expected EPSG:25832, got {crs}")
    official_geoid = float(datum["orthometric_geoid_m"])
    ellipsoid_shift = float(datum["ellipsoid_shift_z_m"])
    official_shift_z = ellipsoid_shift - official_geoid
    legacy_shift_z = ellipsoid_shift - float(args.legacy_label_geoid_m)
    if not math.isclose(official_geoid, 45.7, abs_tol=1e-9) or not math.isclose(official_shift_z, 558.3):
        raise AssertionError(f"official datum lock changed: geoid={official_geoid}, shift_z={official_shift_z}")
    if not math.isclose(legacy_shift_z, 556.0, abs_tol=1e-9):
        raise AssertionError(
            f"actual clean-label source loss-address shift_z must be 556.0, got {legacy_shift_z}"
        )
    xy_shift = np.array([690953.0, 5336071.0], dtype=np.float64)
    shift_official = np.array([xy_shift[0], xy_shift[1], official_shift_z], dtype=np.float64)

    all_frames = load_frames(data_root)
    run_mode_contract = validate_run_mode_contract(
        debug_subset=debug_subset,
        frame_count=len(all_frames),
        core_buildings=args.core_buildings,
        views_per_building=args.views_per_building,
        skip_overlays=args.skip_overlays,
        legacy_label_geoid_m=args.legacy_label_geoid_m,
    )
    frames = all_frames
    if args.view_stems:
        by_stem = {frame.stem: frame for frame in all_frames}
        missing_views = sorted(set(args.view_stems) - set(by_stem))
        if missing_views:
            raise AssertionError(f"requested view stems absent from C001: {missing_views}")
        if len(set(args.view_stems)) != len(args.view_stems):
            raise AssertionError("--view-stems must be unique")
        frames = [by_stem[stem] for stem in args.view_stems]
    elif args.limit:
        frames = frames[: args.limit]
    print(f"[frames] {len(frames)} C001 frames")

    configured_building_ids = arm1p_candidate_buildings(arm1p_config_path)
    candidate_list_sha256 = hashlib.sha256(
        json.dumps(configured_building_ids, ensure_ascii=False, separators=(",", ":")).encode(
            "utf-8"
        )
    ).hexdigest()
    all_footprints, all_footprint_part_counts = load_footprints(footprints_path)
    missing_configured_fp = sorted(set(configured_building_ids) - set(all_footprints))
    if missing_configured_fp:
        raise AssertionError(f"Arm1-prime C00118 missing footprint: {missing_configured_fp}")
    # Assignment tie-breaking is lexical, while the config-order list and hash
    # are both preserved in provenance.
    building_ids = sorted(configured_building_ids)
    footprints = {building_id: all_footprints[building_id] for building_id in building_ids}
    footprint_part_counts = {
        building_id: all_footprint_part_counts[building_id] for building_id in building_ids
    }
    if set(footprints) != set(configured_building_ids) or len(footprints) != 18:
        raise AssertionError("loss-address footprint candidates must be exactly Arm1-prime C00118")
    print(
        f"[footprints] configured_C00118={len(building_ids)} "
        f"source_inventory={len(all_footprints)} buffer={args.region_buffer_m:.1f} m"
    )
    missing_core_fp = sorted(set(args.core_buildings) - set(footprints))
    if missing_core_fp:
        raise AssertionError(f"core buildings missing footprint: {missing_core_fp}")

    # Mesh/AOI provenance is independent of --limit so debug caches use the
    # identical scene and building index as the full 428-view run.
    centers = np.asarray([-frame.R.T @ frame.t for frame in all_frames])
    aoi_min = centers[:, :2].min(axis=0) - float(args.aoi_margin_m)
    aoi_max = centers[:, :2].max(axis=0) + float(args.aoi_margin_m)
    rings, ring_counts, buildings_scanned = MCL.extract_rings(gml_paths, shift_official, aoi_min, aoi_max)
    scene, tri_class, tri_bid, mesh_bids, n_degenerate = MCL.build_scene(rings)
    reference_heights = roof_heights(rings)
    mesh_bid_index = {building_id: i for i, building_id in enumerate(mesh_bids)}
    missing_c00118_mesh = sorted(set(building_ids) - set(mesh_bid_index))
    if missing_c00118_mesh:
        raise AssertionError(f"Arm1-prime C00118 missing official LoD2 mesh: {missing_c00118_mesh}")
    missing_core_mesh = sorted(set(args.core_buildings) - set(mesh_bid_index))
    if missing_core_mesh:
        raise AssertionError(f"core buildings missing official LoD2 mesh: {missing_core_mesh}")
    missing_fp_height = sorted(set(building_ids) - set(reference_heights))
    print(
        f"[mesh] triangles={len(tri_class)} buildings={len(mesh_bids)} "
        f"reference_roof_heights={len(reference_heights)} degenerate={n_degenerate} "
        f"missing_fp_reference_height={len(missing_fp_height)}"
    )

    sparse_points_path = data_root / "sparse/0/points3D.bin"
    sparse_xyz = read_points3d_bin(sparse_points_path)[:, :3].astype(np.float32, copy=False)
    dense_xyz = load_xyz_ply(dense_init_path)
    projection_heights, global_initial_z_median = input_derived_projection_heights(
        footprints, sparse_xyz, dense_xyz, xy_shift
    )
    print(
        f"[projection-height] source=sparse+dense-init N={len(sparse_xyz) + len(dense_xyz)} "
        f"global_median={global_initial_z_median:.6f} "
        f"inactive_zero_source={sum(int(not v['active_for_loss_address']) for v in projection_heights.values())}"
    )
    height_audit_rows: list[dict[str, Any]] = []
    for building_id in building_ids:
        source = projection_heights[building_id]
        reference_z = reference_heights.get(building_id)
        height_audit_rows.append(
            {
                "building_id": building_id,
                "core9": building_id in set(args.core_buildings),
                "estimated_z_local_m": source["estimated_z_local_m"],
                "sparse_points3d_count": source["sparse_points3d_count"],
                "dense_init_point_count": source["dense_init_point_count"],
                "source_count": source["source_count"],
                "source_z_q10_local_m": source["source_z_q10_local_m"],
                "source_z_q50_local_m": source["source_z_q50_local_m"],
                "source_z_q90_local_m": source["source_z_q90_local_m"],
                "source_z_mad_m": source["source_z_mad_m"],
                "active_for_loss_address": source["active_for_loss_address"],
                "inactive_reason": source["inactive_reason"],
                "fallback_used": source["fallback_used"],
                "zero_source_exclusion_only_global_median_z_local_m": source[
                    "zero_source_exclusion_only_global_median_z_local_m"
                ],
                "estimator": source["estimator"],
                "xy_clip": source["xy_clip"],
                "reference_roof_z_local_m": reference_z,
                "estimated_minus_reference_m": (
                    float(source["estimated_z_local_m"] - reference_z)
                    if reference_z is not None and source["estimated_z_local_m"] is not None
                    else None
                ),
                "reference_role": "T0-1/evaluation audit only; never loss-address input",
                "tuning": "none",
            }
        )
    print(
        "[projection-height-core9] "
        + json.dumps(
            [
                {
                    "building_id": row["building_id"],
                    "source_count": row["source_count"],
                    "active": row["active_for_loss_address"],
                    "estimated_z": (
                        round(float(row["estimated_z_local_m"]), 4)
                        if row["estimated_z_local_m"] is not None
                        else None
                    ),
                    "reference_z": json_number(row["reference_roof_z_local_m"]),
                    "delta_m": (
                        round(float(row["estimated_minus_reference_m"]), 4)
                        if row["estimated_minus_reference_m"] is not None
                        else None
                    ),
                }
                for row in height_audit_rows
                if row["core9"]
            ],
            ensure_ascii=False,
        )
    )

    buffered_footprints = {building_id: geom.buffer(args.region_buffer_m) for building_id, geom in footprints.items()}
    qa_footprints = {building_id: footprints[building_id].buffer(args.qa_buffer_m) for building_id in args.core_buildings}
    bid_owner_lookup = mesh_bid_to_owner(mesh_bids, building_ids)

    sparse_dir = data_root / "sparse/0"
    global_hashes = {
        rel(footprints_path): sha256_file(footprints_path),
        rel(datum_path): sha256_file(datum_path),
        rel(sparse_dir / "cameras.bin"): sha256_file(sparse_dir / "cameras.bin"),
        rel(sparse_dir / "images.bin"): sha256_file(sparse_dir / "images.bin"),
        rel(sparse_points_path): sha256_file(sparse_points_path),
        rel(dense_init_path): sha256_file(dense_init_path),
        rel(arm1p_config_path): sha256_file(arm1p_config_path),
    }
    for gml in gml_paths:
        global_hashes[rel(gml)] = sha256_file(gml)

    # Mandatory first-sample regeneration: actual source must reproduce exactly;
    # official-datum divergence is retained as the data-defect/reference metric.
    # Keep the provenance preflight invariant under smoke/debug view subsets.
    # This canonical first C001 frame is the known exact legacy-datum replay.
    sample = all_frames[0]
    sample_current = np.asarray(PILImage.open(data_root / "semantic" / f"{sample.stem}.png"), dtype=np.uint8)
    sample_rays = MCL.frame_rays(
        sample.camera.K(), sample.R, sample.t, sample.camera.width, sample.camera.height
    )
    sample_official, _ = MCL.cast_labels(
        scene, tri_class, tri_bid, sample_rays, sample.camera.height, sample.camera.width
    )
    sample_actual, _ = MCL.cast_labels(
        scene,
        tri_class,
        tri_bid,
        shifted_rays(sample_rays, legacy_shift_z, official_shift_z),
        sample.camera.height,
        sample.camera.width,
    )
    official_alignment = class_alignment(sample_current, sample_official)
    actual_alignment = class_alignment(sample_current, sample_actual)
    alignment_preflight = {
        "sample_view": sample.stem,
        "fixed_clean_mask_path": rel(data_root / "semantic" / f"{sample.stem}.png"),
        "actual_label_source": {
            "provenance": "observed clean_labels_geoidfix generation; legacy geoid 48.0 m",
            "geoid_m": float(args.legacy_label_geoid_m),
            "shift_z_m": legacy_shift_z,
            **actual_alignment,
            "assertion": "class_agreement==1 and roof_iou==1",
        },
        "official_v2_projection": {
            "provenance": rel(datum_path),
            "geoid_m": official_geoid,
            "shift_z_m": official_shift_z,
            **official_alignment,
            "assertion": "reference metric only; mismatch is recorded as a datum provenance defect",
        },
    }
    if actual_alignment["class_agreement"] < 0.999999 or actual_alignment["roof_iou"] < 0.999999:
        raise AssertionError(f"current clean mask does not reproduce from observed actual source: {actual_alignment}")
    print("[alignment_preflight] " + json.dumps(alignment_preflight, ensure_ascii=False))

    args.cache_dir.mkdir(parents=True, exist_ok=True)
    args.fig_dir.mkdir(parents=True, exist_ok=True)
    args.run_dir.mkdir(parents=True, exist_ok=True)

    inventory_rows: list[dict[str, Any]] = []
    mapping_rows: list[dict[str, Any]] = []
    validation_rows: list[dict[str, Any]] = []
    oracle_integrity_rows: list[dict[str, Any]] = []
    projection_height_view_rows: list[dict[str, Any]] = []
    all_gate_measurements: list[GateMeasurement] = []

    for frame_index, frame in enumerate(frames, start=1):
        semantic_path = data_root / "semantic" / f"{frame.stem}.png"
        clean_class = np.asarray(PILImage.open(semantic_path), dtype=np.uint8)
        expected_shape = (int(frame.camera.height), int(frame.camera.width))
        if clean_class.shape != expected_shape:
            raise AssertionError(f"{frame.stem}: semantic {clean_class.shape} != camera {expected_shape}")
        clean_roof = clean_class == 1

        rays_official = MCL.frame_rays(
            frame.camera.K(), frame.R, frame.t, frame.camera.width, frame.camera.height
        )
        official_label, official_bidmap = MCL.cast_labels(
            scene, tri_class, tri_bid, rays_official, frame.camera.height, frame.camera.width
        )
        actual_label, actual_bidmap = MCL.cast_labels(
            scene,
            tri_class,
            tri_bid,
            shifted_rays(rays_official, legacy_shift_z, official_shift_z),
            frame.camera.height,
            frame.camera.width,
        )

        # Preserve the pre-adjudication footprint rule as a one-time defect
        # baseline.  Its owner raster is never written as the v3 loss address.
        (
            _footprint_region_ids,
            footprint_cutline_mask,
            _footprint_regions,
            footprint_region_stats,
            footprint_owner,
            footprint_eligible,
            footprint_inactive_veto_mask,
        ) = build_footprint_regions(
            clean_roof,
            frame,
            footprints,
            buffered_footprints,
            projection_heights,
            xy_shift,
            building_ids,
        )
        footprint_overlap_counts = {
            int(component_id): int(count)
            for component_id, count in footprint_region_stats[
                "source_component_footprint_overlap_counts"
            ].items()
        }
        (
            region_ids,
            cutline_mask,
            regions,
            region_stats,
            owner,
            eligible,
            inactive_veto_mask,
        ) = build_oracle_id_regions(
            clean_roof,
            actual_label,
            actual_bidmap,
            bid_owner_lookup,
            building_ids,
            footprint_overlap_counts,
        )
        oracle_check_actual = assignment_check(
            owner,
            cutline_mask,
            eligible,
            inactive_veto_mask,
            actual_label,
            actual_bidmap,
            bid_owner_lookup,
            building_ids,
            "actual_label_source_legacy48p0_oracle_address",
            legacy_shift_z,
            raycast_building_id_is_loss_input=True,
        )
        oracle_integrity_rows.append(oracle_check_actual["totals"])
        check_actual = assignment_check(
            footprint_owner,
            footprint_cutline_mask,
            footprint_eligible,
            footprint_inactive_veto_mask,
            actual_label,
            actual_bidmap,
            bid_owner_lookup,
            building_ids,
            "actual_label_source_legacy48p0",
            legacy_shift_z,
        )
        check_official = assignment_check(
            footprint_owner,
            footprint_cutline_mask,
            footprint_eligible,
            footprint_inactive_veto_mask,
            official_label,
            official_bidmap,
            bid_owner_lookup,
            building_ids,
            "official_v2_datum45p7",
            official_shift_z,
        )

        semantic_hash = sha256_file(semantic_path)
        metadata = {
            "schema": "jointbuildgs.s3a.semantic_regions.v3",
            "image_stem": frame.stem,
            "image_name": frame.name,
            "shape_hw": [int(frame.camera.height), int(frame.camera.width)],
            "loss_address_source": (
                "fixed C001 clean semantic class-1 mask plus discrete building ID from the "
                "exactly aligned actual clean-label-source raycast; exact Arm1-prime C00118 only"
            ),
            "experiment_scope": EXPERIMENT_SCOPE,
            "claim_boundary": (
                "oracle class+instance-address mechanism upper bound only; not a battlefield "
                "win, not model-free, and not S3-B/FM; S3-B forbids this ID map"
            ),
            "footprint_xy_role": FOOTPRINT_ROLE,
            "candidate_building_source": rel(arm1p_config_path),
            "candidate_building_ids_config_order": configured_building_ids,
            "candidate_building_ids_assignment_order": building_ids,
            "candidate_building_list_sha256": candidate_list_sha256,
            "candidate_buildings_inactive_for_loss_address": [],
            "zero_initial_point_buildings_audit_only": [
                building_id
                for building_id in building_ids
                if not projection_heights[building_id]["active_for_loss_address"]
            ],
            "loss_address_mode": "oracle_class_plus_raycast_building_id",
            "raycast_building_id_is_loss_input": True,
            "raycast_building_id_loss_role": "region address only",
            "loss_address_datum": {
                "provenance": "actual_clean_label_source_legacy48p0",
                "orthometric_geoid_m": float(args.legacy_label_geoid_m),
                "shift_z_m": legacy_shift_z,
                "class_mask_alignment": (
                    "fixed clean PNG is authoritative; actual-source datum ID map only; "
                    "per-view raster-edge mismatch audited"
                ),
            },
            "official_datum_audit": {
                "provenance": rel(datum_path),
                "orthometric_geoid_m": official_geoid,
                "shift_z_m": official_shift_z,
                "role": "audit_only",
                "is_loss_input": False,
            },
            "loss_value_contract": {
                "raycast_building_id_role": "region membership only",
                "raycast_hit_distance_stored": False,
                "raycast_intersection_xyz_stored": False,
                "lod2_depth_or_height_loss_input": False,
                "official_datum_is_loss_input": False,
                "absolute_height_source": "existing L_depth supervision only",
                "npz_loss_address_arrays": ["region_ids", "cutline_mask"],
            },
            "cache_contract": {
                "cutline_half_width_px": CUTLINE_HALF_WIDTH_PX,
                "source_component_min_pixels": SOURCE_COMPONENT_MIN_PIXELS,
                "connectivity": 8,
                "footprint_buffer_m": REGION_FOOTPRINT_BUFFER_M,
                "loss_address_mode": "oracle_class_plus_raycast_building_id",
                "loss_address_geoid_m": float(args.legacy_label_geoid_m),
                "loss_address_shift_z_m": legacy_shift_z,
            },
            "connectivity": 8,
            "source_component_connectivity": 8,
            "source_component_min_pixels": SOURCE_COMPONENT_MIN_PIXELS,
            "post_split_fragment_min_pixels": None,
            "plane_loss_min_valid_pixels": PLANE_MIN_PIXELS,
            "footprint_buffer_m": REGION_FOOTPRINT_BUFFER_M,
            "cutline_half_width_px": CUTLINE_HALF_WIDTH_PX,
            "cutline_nominal_kernel_px": 2 * CUTLINE_HALF_WIDTH_PX + 1,
            "cutline_discrete_rule": (
                "subpixel cut; exactly 7 owner pixels each side via per-owner Chebyshev distance 0..6"
            ),
            "cutline_exactness_qa": cutline_exactness_qa,
            "assignment_rule": ORACLE_ADDRESS_RULE,
            "footprint_rule_defect_baseline": {
                "role": "audit_only; retained pre-adjudication S3-B address-delta baseline",
                "assignment_rule": ASSIGNMENT_RULE,
                "footprint_buffer_m": REGION_FOOTPRINT_BUFFER_M,
                "projection_height_policy": {
                    "estimator": (
                        "per-building median z of Arm1-prime zero-iteration sparse points3D "
                        "plus dense-init points strictly inside the unbuffered footprint"
                    ),
                    "global_initial_point_z_median": global_initial_z_median,
                    "uses_lod2_height": False,
                    "is_loss_address_input": False,
                },
                "projection_height_candidate_inventory_c00118": projection_heights,
                "region_stats": footprint_region_stats,
                "raycast_assignment_check": {
                    "primary_actual_label_source": check_actual,
                    "secondary_official_v2": check_official,
                },
            },
            "crs": crs,
            "ellipsoid_shift_z_m": ellipsoid_shift,
            "l_nb_boundary_source": "class boundary only; cutline_mask is forbidden for L_nb",
            "alignment_preflight": alignment_preflight,
            "input_hashes": {
                "global": global_hashes,
                "semantic_mask": {rel(semantic_path): semantic_hash},
            },
            "regions": {str(region["region_id"]): region for region in regions},
            "region_stats": region_stats,
            "oracle_address_check": oracle_check_actual,
            "raycast_assignment_check": {
                "primary_actual_label_source": check_actual,
                "secondary_official_v2": check_official,
            },
        }
        cache_path = args.cache_dir / f"{frame.stem}.npz"
        np.savez_compressed(
            cache_path,
            region_ids=region_ids.astype(np.int32, copy=False),
            cutline_mask=cutline_mask.astype(bool, copy=False),
            metadata_json=np.asarray(json.dumps(metadata, sort_keys=True, ensure_ascii=False)),
        )
        cache_hash = sha256_file(cache_path)

        for region in regions:
            mapping_rows.append(
                {
                    "view_stem": frame.stem,
                    **region,
                    "footprint_buffer_m": REGION_FOOTPRINT_BUFFER_M,
                    "footprint_buffer_role": "pre-adjudication overlap audit only",
                    "cutline_half_width_px": CUTLINE_HALF_WIDTH_PX,
                    "source_component_min_pixels": SOURCE_COMPONENT_MIN_PIXELS,
                    "cache_path": rel(cache_path),
                }
            )
        inventory_rows.append(
            {
                "view_stem": frame.stem,
                "image_name": frame.name,
                "height_px": frame.camera.height,
                "width_px": frame.camera.width,
                **region_stats,
                "cache_path": rel(cache_path),
                "cache_sha256": cache_hash,
                "semantic_mask_path": rel(semantic_path),
                "semantic_mask_sha256": semantic_hash,
                "status": "ok",
            }
        )
        for check in (check_actual, check_official):
            validation_rows.append(
                {
                    "row_type": "view",
                    "view_stem": frame.stem,
                    "provenance": check["provenance"],
                    "shift_z_m": check["shift_z_m"],
                    "building_id": "__ALL_C00118__",
                    "active_for_loss_address": "mixed",
                    **assignment_csv_fields(check["totals"]),
                    "raycast_id_is_loss_input": False,
                }
            )
            for building_id in building_ids:
                validation_rows.append(
                    {
                        "row_type": "view",
                        "view_stem": frame.stem,
                        "provenance": check["provenance"],
                        "shift_z_m": check["shift_z_m"],
                        "building_id": building_id,
                        "active_for_loss_address": projection_heights[building_id][
                            "active_for_loss_address"
                        ],
                        **assignment_csv_fields(check["by_building"][building_id]),
                        "raycast_id_is_loss_input": False,
                    }
                )

        for building_id in building_ids:
            reference_z = reference_heights.get(building_id)
            if reference_z is None:
                continue
            audit_row = projection_height_view_audit(
                building_id,
                frame,
                footprints[building_id],
                projection_heights[building_id],
                reference_z,
                xy_shift,
            )
            if audit_row is not None:
                projection_height_view_rows.append(audit_row)

        for building_id in args.core_buildings:
            mesh_index = mesh_bid_index[building_id]
            ref_mask = (official_label == 1) & (official_bidmap == mesh_index)
            if int(ref_mask.sum()) <= 0:
                continue
            qa_mask = rasterize_geometry(
                qa_footprints[building_id], reference_heights[building_id], frame, xy_shift
            )
            all_gate_measurements.append(
                gate_measurement(
                    building_id,
                    frame,
                    clean_roof,
                    ref_mask,
                    qa_mask,
                    reference_heights[building_id],
                )
            )

        if frame_index % 25 == 0 or frame_index == len(frames):
            elapsed = time.time() - started
            print(f"[cache] {frame_index}/{len(frames)} elapsed={elapsed:.1f}s")

    validation_view_rows = list(validation_rows)
    aggregate_checks: dict[str, dict[str, Any]] = {}
    for provenance, shift_z in [
        ("actual_label_source_legacy48p0", legacy_shift_z),
        ("official_v2_datum45p7", official_shift_z),
    ]:
        by_building: dict[str, Any] = {}
        for building_id in ["__ALL_C00118__", *building_ids]:
            source_rows = [
                row
                for row in validation_view_rows
                if row["provenance"] == provenance and row["building_id"] == building_id
            ]
            aggregate = sum_assignment_counts(source_rows)
            if building_id != "__ALL_C00118__":
                by_building[building_id] = aggregate
            validation_rows.append(
                {
                    "row_type": "building_aggregate" if building_id != "__ALL_C00118__" else "pooled_aggregate",
                    "view_stem": "ALL_PROCESSED_VIEWS",
                    "provenance": provenance,
                    "shift_z_m": shift_z,
                    "building_id": building_id,
                    "active_for_loss_address": (
                        projection_heights[building_id]["active_for_loss_address"]
                        if building_id != "__ALL_C00118__"
                        else "mixed"
                    ),
                    **assignment_csv_fields(aggregate),
                    "raycast_id_is_loss_input": False,
                }
            )
        aggregate_checks[provenance] = {
            "provenance": provenance,
            "shift_z_m": shift_z,
            "totals": next(
                row
                for row in validation_rows
                if row["row_type"] == "pooled_aggregate" and row["provenance"] == provenance
            ),
            "by_building": by_building,
            "raycast_building_id_is_loss_input": False,
        }

    aggregate_primary = aggregate_checks["actual_label_source_legacy48p0"]
    aggregate_secondary = aggregate_checks["official_v2_datum45p7"]
    aggregate_oracle_integrity = sum_assignment_counts(oracle_integrity_rows)
    if int(aggregate_oracle_integrity["wrong"]) != 0:
        raise AssertionError(
            "actual-source oracle ID address must have zero misassigned pixels; "
            f"got {aggregate_oracle_integrity['wrong']}"
        )

    # Input-height versus audit-only LoD2-height projection coverage.  Full runs
    # require >=3 visible views for every C00118 building.  Explicit smoke/debug
    # subsets retain however many are visible and mark the aggregate accordingly.
    projection_height_rows: list[dict[str, Any]] = []
    projection_audit_by_building: dict[str, Any] = {}
    for building_id in building_ids:
        candidates = [
            row for row in projection_height_view_rows if row["building_id"] == building_id
        ]
        candidates.sort(key=lambda row: (-int(row["reference_mask_pixels"]), row["view_stem"]))
        if not debug_subset and len(candidates) < 3:
            raise AssertionError(
                f"{building_id}: input-z/reference-z footprint audit has only "
                f"{len(candidates)} visible views; need >=3"
            )
        selected = candidates[:3]
        selected_stems = {row["view_stem"] for row in selected}
        for row in candidates:
            projection_height_rows.append(
                {
                    **row,
                    "row_type": "view",
                    "selected_top3_by_reference_area": row["view_stem"] in selected_stems,
                    "visible_view_count_available": len(candidates),
                }
            )
        metrics = [
            "reference_mask_pixels",
            "input_mask_pixels",
            "intersection_pixels",
            "union_pixels",
            "footprint_mask_iou",
            "centroid_shift_px",
            "input_over_reference_pixel_coverage",
            "projection_z_minus_reference_m",
        ]
        median_values: dict[str, Any] = {}
        for metric in metrics:
            values = np.asarray(
                [row[metric] for row in selected if row[metric] is not None], dtype=np.float64
            )
            median_values[metric] = (
                json_number(float(np.median(values))) if len(values) else None
            )
        aggregate = {
            "row_type": "building_median",
            "building_id": building_id,
            "view_stem": "MEDIAN_TOP3",
            "loss_address_active": projection_heights[building_id]["active_for_loss_address"],
            "projection_role": (
                "loss_address_locked_input_median_z"
                if projection_heights[building_id]["active_for_loss_address"]
                else (
                    "global-median candidate places exclusion/veto only; building remains "
                    "unassigned and receives no positive loss region"
                )
            ),
            "source_count": projection_heights[building_id]["source_count"],
            "input_projection_z_local_m": projection_heights[building_id]["estimated_z_local_m"],
            "zero_source_exclusion_only_global_median_z_local_m": projection_heights[
                building_id
            ][
                "zero_source_exclusion_only_global_median_z_local_m"
            ],
            "reference_projection_z_local_m": reference_heights.get(building_id),
            **median_values,
            "selected_top3_by_reference_area": True,
            "visible_view_count_available": len(candidates),
            "selected_view_count": len(selected),
            "selected_view_stems": ";".join(row["view_stem"] for row in selected),
            "coverage_requirement": (
                "smoke/debug subset; >=3 assertion deferred to full run"
                if debug_subset
                else ">=3 visible views passed"
            ),
            "tuning": "none; input median locked before reference comparison",
            "reference_role": "audit only; LoD2 z is never a loss-address input",
        }
        projection_height_rows.append(aggregate)
        projection_audit_by_building[building_id] = aggregate

    selected_by_building, gate_candidate_rows = select_gate_candidates(
        all_gate_measurements,
        args.core_buildings,
        args.views_per_building,
        official_geoid_m=official_geoid,
        official_shift_z_m=official_shift_z,
        label_actual_source_shift_z_m=legacy_shift_z,
    )

    frame_by_stem = {frame.stem: frame for frame in frames}
    gate_rows: list[dict[str, Any]] = []
    for building_id in args.core_buildings:
        selected = selected_by_building[building_id]
        if not selected:
            continue
        selected_low_support_count = sum(
            int(measurement.ref_pixels) < FRAGMENT_MEASURE_MIN_PIXELS
            for measurement in selected
        )
        for rank, measurement in enumerate(selected, start=1):
            gate_rows.append(
                {
                    "measurement_role": "reference_only",
                    "gate_role": "self_consistency_not_a_gate",
                    "decision": "not_applicable",
                    "row_type": "view",
                    "aggregation": "selected_view",
                    "building_id": building_id,
                    "view_stem": measurement.view_stem,
                    "view_rank_by_ref_area": rank,
                    "ref_support_ge64": (
                        int(measurement.ref_pixels) >= FRAGMENT_MEASURE_MIN_PIXELS
                    ),
                    "ref_support_scope": "this_view",
                    "selected_low_support_count": selected_low_support_count,
                    "visible_view_count_available": sum(
                        1 for m in all_gate_measurements if m.building_id == building_id
                    ),
                    **{k: json_number(v) for k, v in asdict(measurement).items() if k not in {"building_id", "view_stem", "view_name"}},
                    "qa_footprint_buffer_m": QA_FOOTPRINT_BUFFER_M,
                    "qa_buffer_rationale": QA_BUFFER_RATIONALE,
                    "qa_buffer_role": QA_BUFFER_ROLE,
                    "view_selection_rule": (
                        "visible iff official P_ref > 0; top 3 deterministic views by "
                        "official P_ref roof pixel area; tie by view stem"
                    ),
                    "official_geoid_m": official_geoid,
                    "official_shift_z_m": official_shift_z,
                    "label_actual_source_shift_z_m": legacy_shift_z,
                }
            )

        metric_names = [
            "ref_pixels",
            "clean_clipped_pixels",
            "intersection_pixels",
            "union_pixels",
            "iou",
            "fragment_count_ge64",
            "boundary_offset_px",
            "jacobian_m_per_px_x",
            "jacobian_m_per_px_y",
            "jacobian_m_per_px",
            "boundary_offset_m",
            "roof_height_local_m",
        ]
        medians: dict[str, Any] = {}
        for name in metric_names:
            values = np.asarray([getattr(m, name) for m in selected], dtype=np.float64)
            medians[name] = json_number(float(np.nanmedian(values))) if np.any(np.isfinite(values)) else None
        boundary_offset_defined_view_count = sum(
            bool(measurement.boundary_offset_defined) for measurement in selected
        )
        boundary_offset_undefined_view_count = (
            len(selected) - boundary_offset_defined_view_count
        )
        gate_rows.append(
            {
                "measurement_role": "reference_only",
                "gate_role": "self_consistency_not_a_gate",
                "decision": "not_applicable",
                "row_type": "building_median",
                "aggregation": "median_of_3_selected_views",
                "building_id": building_id,
                "view_stem": "MEDIAN",
                "view_rank_by_ref_area": "",
                "ref_support_ge64": selected_low_support_count == 0,
                "ref_support_scope": "all_selected_views",
                "selected_low_support_count": selected_low_support_count,
                "boundary_offset_defined": boundary_offset_defined_view_count > 0,
                "boundary_offset_status": (
                    f"median_defined_from_{boundary_offset_defined_view_count}_of_{len(selected)}_selected_views"
                    if boundary_offset_defined_view_count > 0
                    else "undefined_all_selected_views"
                ),
                "boundary_offset_defined_view_count": boundary_offset_defined_view_count,
                "boundary_offset_undefined_view_count": boundary_offset_undefined_view_count,
                "visible_view_count_available": sum(
                    1 for m in all_gate_measurements if m.building_id == building_id
                ),
                **medians,
                "qa_footprint_buffer_m": QA_FOOTPRINT_BUFFER_M,
                "qa_buffer_rationale": QA_BUFFER_RATIONALE,
                "qa_buffer_role": QA_BUFFER_ROLE,
                "view_selection_rule": (
                    "visible iff official P_ref > 0; top 3 deterministic views by "
                    "official P_ref roof pixel area; tie by view stem"
                ),
                "official_geoid_m": official_geoid,
                "official_shift_z_m": official_shift_z,
                "label_actual_source_shift_z_m": legacy_shift_z,
            }
        )

    overlay_artifacts: list[dict[str, Any]] = []
    priority_paths: dict[tuple[str, int], Path] = {}
    if not args.skip_overlays:
        for building_id, selected in selected_by_building.items():
            selected_low_support_count = sum(
                int(measurement.ref_pixels) < FRAGMENT_MEASURE_MIN_PIXELS
                for measurement in selected
            )
            for rank, measurement in enumerate(selected, start=1):
                frame = frame_by_stem[measurement.view_stem]
                semantic_path = data_root / "semantic" / f"{frame.stem}.png"
                clean_roof = np.asarray(PILImage.open(semantic_path), dtype=np.uint8) == 1
                rays = MCL.frame_rays(
                    frame.camera.K(), frame.R, frame.t, frame.camera.width, frame.camera.height
                )
                label, bidmap = MCL.cast_labels(
                    scene, tri_class, tri_bid, rays, frame.camera.height, frame.camera.width
                )
                ref_mask = (label == 1) & (bidmap == mesh_bid_index[building_id])
                qa_mask = rasterize_geometry(
                    qa_footprints[building_id], reference_heights[building_id], frame, xy_shift
                )
                measured = clean_roof & qa_mask
                full_path = args.fig_dir / f"{building_id}__{frame.stem}.png"
                overlay = render_overlay(
                    full_path,
                    data_root / "images" / frame.name,
                    measured,
                    ref_mask,
                    measurement,
                    selected_low_support_count=selected_low_support_count,
                )
                overlay_artifacts.append(
                    image_artifact(
                        full_path,
                        kind="full_overlay",
                        building_id=building_id,
                        view_stem=frame.stem,
                        rank=rank,
                        ref_support_ge64=(
                            int(measurement.ref_pixels) >= FRAGMENT_MEASURE_MIN_PIXELS
                        ),
                        selected_low_support_count=selected_low_support_count,
                        support_label=ref_support_label(measurement.ref_pixels),
                    )
                )
                if building_id in TEXTURELESS3:
                    crop_box, target_touches_frame = priority_crop_box(measured, ref_mask)
                    priority_path = (
                        args.fig_dir
                        / "priority"
                        / f"{building_id}__rank{rank}__{frame.stem}.png"
                    )
                    render_priority_crop(
                        priority_path,
                        overlay,
                        crop_box,
                        measurement,
                        rank,
                        target_touches_frame=target_touches_frame,
                        selected_low_support_count=selected_low_support_count,
                    )
                    priority_paths[(building_id, rank)] = priority_path
                    overlay_artifacts.append(
                        image_artifact(
                            priority_path,
                            kind="priority_crop",
                            building_id=building_id,
                            view_stem=frame.stem,
                            rank=rank,
                            crop_box_xyxy=crop_box,
                            target_touches_frame=target_touches_frame,
                            ref_support_ge64=(
                                int(measurement.ref_pixels) >= FRAGMENT_MEASURE_MIN_PIXELS
                            ),
                            selected_low_support_count=selected_low_support_count,
                            support_label=ref_support_label(measurement.ref_pixels),
                        )
                    )
        expected_priority_keys = {
            (building_id, rank) for building_id in TEXTURELESS3 for rank in (1, 2, 3)
        }
        if set(priority_paths) == expected_priority_keys:
            contact_sheet_path = args.fig_dir / "priority" / "textureless3_contact_sheet.png"
            textureless_low_support_count = sum(
                int(measurement.ref_pixels) < FRAGMENT_MEASURE_MIN_PIXELS
                for building_id in TEXTURELESS3
                for measurement in selected_by_building.get(building_id, [])
            )
            make_textureless_contact_sheet(
                priority_paths,
                contact_sheet_path,
                selected_low_support_count=textureless_low_support_count,
            )
            overlay_artifacts.append(
                image_artifact(
                    contact_sheet_path,
                    kind="priority_contact_sheet",
                    ref_support_ge64=textureless_low_support_count == 0,
                    selected_low_support_count=textureless_low_support_count,
                    support_label=(
                        f"LOW SUPPORT = P_ref <{FRAGMENT_MEASURE_MIN_PIXELS} px; audit-only"
                    ),
                )
            )

    semantic_gate_path = args.docs_dir / "e5_c001_s3_semantic_gate.csv"
    semantic_gate_candidates_path = (
        args.docs_dir / "e5_c001_s3_semantic_gate_candidates.csv"
    )
    mapping_path = args.docs_dir / "e5_c001_s3_semantic_region_mapping.csv"
    inventory_path = args.docs_dir / "e5_c001_s3_semantic_region_inventory.csv"
    validation_path = args.docs_dir / "e5_c001_s3_raycast_assignment_check.csv"
    height_audit_path = args.docs_dir / "e5_c001_s3_semantic_region_height_audit.csv"
    projection_height_audit_path = (
        args.docs_dir / "e5_c001_s3_semantic_region_projection_height_audit.csv"
    )
    issue_path = args.docs_dir / "e5_c001_s3_issues.csv"
    write_csv(semantic_gate_path, gate_rows)
    write_csv(semantic_gate_candidates_path, gate_candidate_rows)
    write_csv(mapping_path, mapping_rows)
    write_csv(inventory_path, inventory_rows)
    write_csv(validation_path, validation_rows)
    write_csv(height_audit_path, height_audit_rows)
    write_csv(projection_height_audit_path, projection_height_rows)

    upsert_issue(
        issue_path,
        {
            "issue_id": "S3A-T0-DATUM-001",
            "date": "2026-07-13",
            "task": "S3-A T0-1 / semantic-region cache",
            "severity": "high",
            "status": "observed_open",
            "summary": "Current clean-label raster provenance is legacy geoid 48.0 m (shift_z 556.0), not official config 45.7 m (shift_z 558.3).",
            "evidence": (
                f"sample={sample.stem}; actual556 class_agreement={actual_alignment['class_agreement']:.6f}, "
                f"roof_iou={actual_alignment['roof_iou']:.6f}; official558.3 "
                f"class_agreement={official_alignment['class_agreement']:.6f}, "
                f"roof_iou={official_alignment['roof_iou']:.6f}, mismatch_px={official_alignment['mismatch_pixels']}"
            ),
            "impact": "T0-1 remains reference-only; official-datum self-consistency includes a 2.3 m vertical provenance mismatch.",
            "handling": (
                "S3-A B adjudication uses only the actual-source 48.0/556.0 discrete building "
                "ID as the region address; ray distance/XYZ/LoD2 depth or height are forbidden "
                "loss values. Official 45.7/558.3 remains audit-only; the old footprint rule "
                "is retained only as the S3-B address-defect baseline."
            ),
        },
    )

    t0_1_output_qa = validate_t0_1_outputs(
        gate_rows=gate_rows,
        candidate_rows=gate_candidate_rows,
        core_buildings=args.core_buildings,
        views_per_building=args.views_per_building,
        overlay_artifacts=overlay_artifacts,
        fig_dir=args.fig_dir,
        debug_subset=debug_subset,
        skip_overlays=args.skip_overlays,
    )
    hashed_output_paths = [
        semantic_gate_path,
        semantic_gate_candidates_path,
        mapping_path,
        inventory_path,
        validation_path,
        height_audit_path,
        projection_height_audit_path,
        issue_path,
    ]
    output_hashes = {rel(path): sha256_file(path) for path in hashed_output_paths}
    output_hashes.update(
        {str(row["path"]): str(row["sha256"]) for row in overlay_artifacts}
    )

    elapsed = time.time() - started
    partial_cache_inventory = []
    for partial_name in [
        "semantic_regions_partial_precontract_20260713",
        "semantic_regions_partial_pre_oracleheight_fix_20260713",
        "semantic_regions_partial_pre_c00118_auditfix_20260713",
    ]:
        partial_path = args.cache_dir.parent / partial_name
        if partial_path.is_dir():
            partial_cache_inventory.append(
                {
                    "path": rel(partial_path),
                    "npz_count": sum(1 for _ in partial_path.glob("*.npz")),
                    "role": "quarantined noncanonical partial; forbidden for training",
                }
            )
    manifest = {
        "run_id": "20260713_e5_c001_s3a_semantic_regions",
        "created_local_date": "2026-07-13",
        "script": rel(Path(__file__)),
        "script_sha256": sha256_file(Path(__file__)),
        "command": [sys.executable, *sys.argv],
        "git_head": git_value("rev-parse", "HEAD"),
        "git_branch": git_value("branch", "--show-current"),
        "container_image": "jointbuildgs:dev",
        "container_image_id": docker_image_id or "unrecorded_debug_subset",
        "container_image_id_source": (
            "required S3_DOCKER_IMAGE_ID passed from host docker image inspect"
            if docker_image_id
            else "debug subset exemption"
        ),
        "host_uid_gid": f"{os.getuid()}:{os.getgid()}",
        "python": platform.python_version(),
        "versions": {
            "numpy": np.__version__,
            "scipy": scipy.__version__,
            "open3d": o3d.__version__,
            "opencv": cv2.__version__,
        },
        "runtime_seconds": elapsed,
        "experiment_scope": EXPERIMENT_SCOPE,
        "claim_boundary": (
            "oracle class+instance-address mechanism upper bound only; not a battlefield win, "
            "not model-free, and not S3-B/FM; S3-B forbids the oracle ID address"
        ),
        "footprint_xy_role": FOOTPRINT_ROLE,
        "inputs": {
            "data_root": rel(data_root),
            "footprints": rel(footprints_path),
            "gml": [rel(p) for p in gml_paths],
            "datum_config": rel(datum_path),
            "sparse_points3d": rel(sparse_points_path),
            "dense_init": rel(dense_init_path),
            "arm1p_base_config": rel(arm1p_config_path),
            "arm1p_candidate_buildings_config_order": configured_building_ids,
            "arm1p_candidate_buildings_assignment_order": building_ids,
            "arm1p_candidate_building_list_sha256": candidate_list_sha256,
            "hashes": global_hashes,
        },
        "locks": {
            "crs": crs,
            "source_component_connectivity": 8,
            "source_component_min_pixels": SOURCE_COMPONENT_MIN_PIXELS,
            "post_split_fragment_min_pixels": None,
            "plane_loss_min_valid_pixels": PLANE_MIN_PIXELS,
            "footprint_buffer_m": REGION_FOOTPRINT_BUFFER_M,
            "cutline_half_width_px": CUTLINE_HALF_WIDTH_PX,
            "cutline_nominal_kernel_px": 2 * CUTLINE_HALF_WIDTH_PX + 1,
            "cutline_discrete_rule": (
                "subpixel cut; exactly 7 owner pixels each side via per-owner Chebyshev distance 0..6"
            ),
            "cutline_exactness_qa": cutline_exactness_qa,
            "qa_footprint_buffer_m": QA_FOOTPRINT_BUFFER_M,
            "qa_buffer_rationale": QA_BUFFER_RATIONALE,
            "qa_buffer_role": QA_BUFFER_ROLE,
            "run_mode_contract": run_mode_contract,
            "loss_address_mode": "oracle_class_plus_raycast_building_id",
            "assignment_rule": ORACLE_ADDRESS_RULE,
            "raycast_building_id_loss_role": "region address only",
            "loss_value_contract": {
                "raycast_hit_distance_stored": False,
                "raycast_intersection_xyz_stored": False,
                "lod2_depth_or_height_loss_input": False,
                "absolute_height_source": "existing L_depth supervision only",
            },
            "footprint_rule_defect_baseline": {
                "role": "audit_only",
                "buffer_m": REGION_FOOTPRINT_BUFFER_M,
                "assignment_rule": ASSIGNMENT_RULE,
            },
            "projection_height_estimator": (
                "per-building median z of Arm1-prime zero-iteration sparse points3D+dense-init "
                "points strictly inside unbuffered footprint"
            ),
            "projection_height_fallback": (
                "none; source_count=0 remains inactive; global median places an exclusion-only "
                "+20m candidate in the same nearest-distance competition, never a positive region"
            ),
            "projection_height_zero_source_reason": (
                "zero Arm1p initial points; P-L-style no-material branch"
            ),
            "projection_height_uses_lod2_z": False,
            "projection_height_role": "footprint-rule defect baseline audit only",
            "l_nb_boundary_source": "class boundary only; no instance cutline",
        },
        "datum_provenance": {
            "official": {
                "geoid_m": official_geoid,
                "shift_z_m": official_shift_z,
                "role": "audit_only",
                "is_loss_input": False,
            },
            "actual_label_source": {
                "geoid_m": float(args.legacy_label_geoid_m),
                "shift_z_m": legacy_shift_z,
                "building_id_role": "region address only",
            },
            "alignment_preflight": alignment_preflight,
        },
        "projection_height": {
            "source_role": "footprint-rule defect baseline audit only",
            "uses_lod2_height": False,
            "global_initial_point_z_median": global_initial_z_median,
            "total_sparse_points3d": int(len(sparse_xyz)),
            "total_dense_init_points": int(len(dense_xyz)),
            "inactive_zero_source_building_count": int(
                sum(not bool(row["active_for_loss_address"]) for row in projection_heights.values())
            ),
            "inactive_zero_source_building_ids": [
                building_id
                for building_id in building_ids
                if not projection_heights[building_id]["active_for_loss_address"]
            ],
            "building_inventory": projection_heights,
            "core9_reference_audit": [row for row in height_audit_rows if row["core9"]],
            "reference_scope": "audit only; no tuning and no loss-address input",
            "input_z_vs_reference_z_projection_audit": projection_audit_by_building,
        },
        "mesh": {
            "buildings_scanned": buildings_scanned,
            "rings_kept": {str(k): int(v) for k, v in ring_counts.items()},
            "triangles": int(len(tri_class)),
            "mesh_buildings": int(len(mesh_bids)),
            "degenerate_rings": int(n_degenerate),
            "footprint_audit_candidates_exact_c00118": int(len(footprints)),
            "footprint_source_inventory_total": int(len(all_footprints)),
            "footprint_parts": int(sum(footprint_part_counts.values())),
            "missing_footprint_roof_height_count": int(len(missing_fp_height)),
            "missing_footprint_roof_height_ids": missing_fp_height,
        },
        "outputs": {
            "cache_dir": rel(args.cache_dir),
            "cache_files": len(inventory_rows),
            "semantic_gate_csv": rel(semantic_gate_path),
            "semantic_gate_candidates_csv": rel(semantic_gate_candidates_path),
            "mapping_csv": rel(mapping_path),
            "inventory_csv": rel(inventory_path),
            "raycast_assignment_csv": rel(validation_path),
            "projection_height_audit_csv": rel(height_audit_path),
            "input_z_vs_reference_z_projection_audit_csv": rel(projection_height_audit_path),
            "issues_csv": rel(issue_path),
            "overlay_dir": rel(args.fig_dir),
            "overlay_count": sum(
                row["kind"] == "full_overlay" for row in overlay_artifacts
            ),
            "priority_crop_count": sum(
                row["kind"] == "priority_crop" for row in overlay_artifacts
            ),
            "priority_contact_sheet_count": sum(
                row["kind"] == "priority_contact_sheet" for row in overlay_artifacts
            ),
            "overlay_artifacts": overlay_artifacts,
            "output_sha256": output_hashes,
            "quarantined_partial_caches": partial_cache_inventory,
        },
        "oracle_id_address_aggregate": {
            "provenance": "actual_label_source_legacy48p0_oracle_address",
            "geoid_m": float(args.legacy_label_geoid_m),
            "shift_z_m": legacy_shift_z,
            "building_id_is_loss_input": True,
            "loss_role": "region address only",
            "lod2_depth_or_height_loss_input": False,
            "totals": aggregate_oracle_integrity,
        },
        "footprint_rule_defect_baseline_aggregate": {
            "primary_actual_label_source": aggregate_primary,
            "secondary_official_v2": aggregate_secondary,
            "raycast_building_id_is_loss_input": False,
            "required_counts": [
                "true_roof_total",
                "eligible_ge256_true_roof",
                "correct",
                "wrong",
                "unassigned_no_owner",
                "cutline_excluded",
                "inactive_veto_excluded",
                "assigned_coverage_of_eligible",
                "wrong_assigned_owner_confusion_json",
            ],
        },
        "t0_1": {
            "measurement_role": "reference_only",
            "gate_role": "self_consistency_not_a_gate",
            "decision": "not_applicable",
            "core_buildings": list(args.core_buildings),
            "views_per_building": args.views_per_building,
            "visibility_rule": "official P_ref > 0",
            "view_selection": (
                "visible iff official P_ref > 0; top official-P_ref area, "
                "deterministic tie by view stem"
            ),
            "ref_support_ge64_threshold_px": FRAGMENT_MEASURE_MIN_PIXELS,
            "selected_low_support_count": t0_1_output_qa[
                "selected_low_support_count"
            ],
            "selected_low_support_by_building": t0_1_output_qa[
                "selected_low_support_by_building"
            ],
            "rows": len(gate_rows),
            "candidate_rows": len(gate_candidate_rows),
            "candidate_csv": rel(semantic_gate_candidates_path),
            "qa_footprint_buffer_m": QA_FOOTPRINT_BUFFER_M,
            "qa_buffer_role": QA_BUFFER_ROLE,
            "output_qa": t0_1_output_qa,
        },
    }
    manifest_path = args.run_dir / "semantic_region_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print(
        "[done] "
        + json.dumps(
            {
                "runtime_seconds": round(elapsed, 3),
                "cache_files": len(inventory_rows),
                "regions": len(mapping_rows),
                "gate_view_rows": sum(r["row_type"] == "view" for r in gate_rows),
                "overlays": manifest["outputs"]["overlay_count"],
                "primary_assigned_coverage": aggregate_primary["totals"][
                    "assigned_coverage_of_eligible"
                ],
                "primary_conditional_misassignment_rate": aggregate_primary["totals"][
                    "conditional_misassignment_rate"
                ],
                "secondary_assigned_coverage": aggregate_secondary["totals"][
                    "assigned_coverage_of_eligible"
                ],
                "secondary_conditional_misassignment_rate": aggregate_secondary["totals"][
                    "conditional_misassignment_rate"
                ],
                "manifest": rel(manifest_path),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
