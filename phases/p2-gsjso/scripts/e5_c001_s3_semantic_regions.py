#!/usr/bin/env python3
"""S3-A Track 0 semantic-region cache and reference-only label QA.

This script has two deliberately separate provenance tracks:

* The S3-A loss address is the fixed C001 clean roof mask (class 1), split by
  the exact 18 ``seed_log_buildings`` footprints from the Arm 1' base config.
  Footprint XY is reused from the read-out crop but is newly used here as a
  loss address.  Its projection height is estimated only from the Arm 1'
  zero-iteration inputs (C001 SfM points3D plus dense-init points).  A building
  with no initial point is inactive/unassigned; the global median can only
  place its conservative +20 m exclusion/veto mask and never creates a positive
  loss region.  No LoD2 height is used by the loss-address cache.
* The current clean-label raster is first reproduced with its observed legacy
  generation datum (48.0 m geoid, ``shift_z = 556.0``).  That raycast is used
  only as the primary building-ID assignment audit.  An official-datum ID
  audit is recorded separately.  Neither raycast ID map is a training input.

For every C001 image stem, the cache contains:

* ``region_ids``: HxW int32, zero means excluded;
* ``cutline_mask``: HxW bool, the two-sided 7 px instance cut band;
* ``metadata_json``: scalar JSON with the locked constants, input hashes,
  region-to-building mapping, and both raycast assignment checks.

T0-1 is emitted as ``reference_only/self_consistency``.  It never emits a GO
or rejection verdict.  This is explicitly an oracle-label +
reference-footprint-assisted mechanism upper bound, not a model-free S3-B
claim.
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
DEFAULT_DATUM_CONFIG = REPO / "configs/projection_datum.json"
DEFAULT_GML = [
    REPO / "phases/p0-audit/data/raw/lod2/690_5334.gml",
    REPO / "phases/p0-audit/data/raw/lod2/690_5336.gml",
]
DEFAULT_CACHE = REPO / "results/tum_transfer/e5_s3/C001/semantic_regions"
DEFAULT_FIG_DIR = REPO / "docs/figs/e5_c001_s3/semantic_gate"
DEFAULT_RUN_DIR = REPO / "phases/p2-gsjso/runs/20260713_e5_c001_s3_track0"
DEFAULT_DENSE_INIT = REPO / "results/tum_transfer/e5_pilot/C001/seeds/seed_dense_C001_buf20.ply"
DEFAULT_ARM1P_CONFIG = (
    REPO / "configs/tum_mob/e5_s2p_interaction/gs_e5_C001_s2p_arm1p_dense_r1.yaml"
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

SOURCE_COMPONENT_MIN_PIXELS = 256
FRAGMENT_MEASURE_MIN_PIXELS = 64
PLANE_MIN_PIXELS = 64
REGION_FOOTPRINT_BUFFER_M = 20.0
CUTLINE_HALF_WIDTH_PX = 7
QA_FOOTPRINT_BUFFER_M = 1.0
LEGACY_LABEL_GEOID_M = 48.0

ASSIGNMENT_RULE = (
    "eligible class-1 8-connected source component pixels are assigned to "
    "the exact Arm1-prime C00118 projected +20m footprint candidates at the "
    "per-building Arm1-prime zero-iteration input-point median z; source_count=0 "
    "candidates are zero-source exclusion-only owners at global-median z; all overlap "
    "pixels choose one winner by projected unbuffered-footprint pixel distance with "
    "lexical building_id tie-break; active winners become positive regions and inactive "
    "winners map to region 0"
)
EXPERIMENT_SCOPE = (
    "S3-A oracle-label plus reference-footprint-assisted mechanism upper bound; "
    "not model-free and not an S3-B/FM result"
)
FOOTPRINT_ROLE = (
    "footprint XY source is reused from the Arm1-prime/Roofer crop inventory, "
    "but its use as a semantic geometry loss address is new in S3-A"
)
QA_BUFFER_RATIONALE = (
    "1.0 m absorbs footprint/roof-eave and sub-pixel projection rounding while remaining "
    "far below the locked 20.0 m loss-region split buffer and avoiding adjacent-roof capture"
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
        writer = csv.DictWriter(f, fieldnames=list(fields), extrasaction="ignore")
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


def build_regions(
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
) -> dict[str, Any]:
    """Audit footprint owner assignment against one raycast building-ID map.

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
        "raycast_building_id_is_loss_input": False,
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
    else:
        boundary_offset_px = float("nan")

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
        jacobian_m_per_px_x=mx,
        jacobian_m_per_px_y=my,
        jacobian_m_per_px=mpp,
        boundary_offset_m=offset_m,
        roof_height_local_m=roof_height_local,
    )


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


def render_overlay(
    out_path: Path,
    image_path: Path,
    measured: np.ndarray,
    ref_mask: np.ndarray,
    measurement: GateMeasurement,
) -> None:
    image = np.asarray(PILImage.open(image_path).convert("RGB"), dtype=np.uint8)
    blend = image.astype(np.float32)
    blend[measured] = 0.60 * blend[measured] + 0.40 * np.array([230, 55, 55], dtype=np.float32)
    ref_boundary = binary_boundary(ref_mask)
    measured_boundary = binary_boundary(measured)
    blend[measured_boundary] = np.array([255, 80, 80], dtype=np.float32)
    blend[ref_boundary] = np.array([0, 235, 255], dtype=np.float32)
    canvas = PILImage.fromarray(np.clip(blend, 0, 255).astype(np.uint8))
    draw = ImageDraw.Draw(canvas)
    font = ImageFont.load_default()
    lines = [
        "S3-A T0-1 | reference only / self-consistency",
        f"Building: {measurement.building_id} | View: {measurement.view_stem}",
        f"IoU: {measurement.iou:.4f} | Fragments >=64 px: {measurement.fragment_count_ge64}",
        f"Boundary offset: {measurement.boundary_offset_px:.3f} px / {measurement.boundary_offset_m:.3f} m",
        "Red: clean roof clipped by +1.0 m footprint | Cyan: official-datum LoD2 roof",
    ]
    y = 5
    for line in lines:
        bbox = draw.textbbox((5, y), line, font=font)
        draw.rectangle((bbox[0] - 2, bbox[1] - 1, bbox[2] + 2, bbox[3] + 1), fill=(0, 0, 0))
        draw.text((5, y), line, fill=(255, 255, 255), font=font)
        y = bbox[3] + 4
    out_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(out_path)


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
    # These are implementation locks, not tunable CLI knobs for this order.
    if args.source_component_min_pixels != SOURCE_COMPONENT_MIN_PIXELS:
        raise ValueError("S3-A v2 locks source_component_min_pixels=256")
    if not math.isclose(args.region_buffer_m, REGION_FOOTPRINT_BUFFER_M):
        raise ValueError("S3-A v2 locks region footprint buffer=20.0 m")
    if args.cutline_half_width_px != CUTLINE_HALF_WIDTH_PX:
        raise ValueError("S3-A v2 locks cutline half-width=7 px")
    if not math.isclose(args.qa_buffer_m, QA_FOOTPRINT_BUFFER_M):
        raise ValueError("this reproducible T0-1 run locks the documented QA buffer=1.0 m")
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
    xy_shift = np.array([690953.0, 5336071.0], dtype=np.float64)
    shift_official = np.array([xy_shift[0], xy_shift[1], official_shift_z], dtype=np.float64)

    all_frames = load_frames(data_root)
    frames = all_frames
    if not args.limit and not args.view_stems:
        raise RuntimeError(
            "BLOCKED: 428-view cache generation is disabled until the footprint-split "
            "address rule is adjudicated. The preregistered +20 m projection cannot "
            "simultaneously preserve 4907199 and keep zero-source 4908179 unassigned; "
            "use --view-stems/--limit for diagnostic smoke only."
        )
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

        (
            region_ids,
            cutline_mask,
            regions,
            region_stats,
            owner,
            eligible,
            inactive_veto_mask,
        ) = build_regions(
            clean_roof,
            frame,
            footprints,
            buffered_footprints,
            projection_heights,
            xy_shift,
            building_ids,
        )
        check_actual = assignment_check(
            owner,
            cutline_mask,
            eligible,
            inactive_veto_mask,
            actual_label,
            actual_bidmap,
            bid_owner_lookup,
            building_ids,
            "actual_label_source_legacy48p0",
            legacy_shift_z,
        )
        check_official = assignment_check(
            owner,
            cutline_mask,
            eligible,
            inactive_veto_mask,
            official_label,
            official_bidmap,
            bid_owner_lookup,
            building_ids,
            "official_v2_datum45p7",
            official_shift_z,
        )

        semantic_hash = sha256_file(semantic_path)
        metadata = {
            "schema": "jointbuildgs.s3a.semantic_regions.v2",
            "image_stem": frame.stem,
            "image_name": frame.name,
            "shape_hw": [int(frame.camera.height), int(frame.camera.width)],
            "loss_address_source": (
                "fixed C001 clean semantic class-1 mask plus exact Arm1-prime C00118 footprint "
                "split projected at zero-iteration sparse+dense-init point median z; "
                "source_count=0 candidate inactive; no LoD2 height"
            ),
            "experiment_scope": EXPERIMENT_SCOPE,
            "claim_boundary": "mechanism upper bound only; not model-free and not S3-B/FM",
            "footprint_xy_role": FOOTPRINT_ROLE,
            "candidate_building_source": rel(arm1p_config_path),
            "candidate_building_ids_config_order": configured_building_ids,
            "candidate_building_ids_assignment_order": building_ids,
            "candidate_building_list_sha256": candidate_list_sha256,
            "candidate_buildings_inactive_for_loss_address": [
                building_id
                for building_id in building_ids
                if not projection_heights[building_id]["active_for_loss_address"]
            ],
            "raycast_building_id_is_loss_input": False,
            "raycast_validation_scope": "audit only; neither actual nor official building-ID map enters training",
            "cache_contract": {
                "cutline_half_width_px": CUTLINE_HALF_WIDTH_PX,
                "source_component_min_pixels": SOURCE_COMPONENT_MIN_PIXELS,
                "connectivity": 8,
                "footprint_buffer_m": REGION_FOOTPRINT_BUFFER_M,
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
            "assignment_rule": ASSIGNMENT_RULE,
            "projection_height_policy": {
                "estimator": (
                    "per-building median z of combined Arm1-prime zero-iteration sparse points3D "
                    "and dense-init points strictly inside the unbuffered footprint"
                ),
                "fallback": "none; source_count=0 remains inactive/unassigned",
                "zero_source_policy": (
                    "global-median +20m exclusion-only candidate enters the same nearest-"
                    "unbuffered-distance competition as active candidates; only an inactive "
                    "winner becomes veto/region0 and never a positive region; reason=zero "
                    "Arm1p initial points; P-L-style no-material branch"
                ),
                "global_initial_point_z_median": global_initial_z_median,
                "sparse_points3d_path": rel(sparse_points_path),
                "dense_init_path": rel(dense_init_path),
                "uses_lod2_height": False,
                "lod2_height_scope": "T0-1 P_ref and raycast audit only",
            },
            "projection_height_buildings_used": {
                building_id: projection_heights[building_id]
                for building_id in sorted({region["building_id"] for region in regions})
            },
            "projection_height_candidate_inventory_c00118": projection_heights,
            "inactive_zero_source_veto": {
                "building_ids": region_stats["inactive_veto_buildings_projected"],
                "eligible_pixels_excluded": region_stats["inactive_veto_pixels"],
                "buffer_m": REGION_FOOTPRINT_BUFFER_M,
                "projection_height": "global initial-point median; exclusion/veto only",
                "competition_rule": (
                    "same +20m candidate set and nearest-unbuffered-distance winner as active; "
                    "no blanket pre-exclusion"
                ),
                "positive_region_created": False,
                "reason": "zero Arm1p initial points; P-L-style no-material branch",
            },
            "crs": crs,
            "orthometric_geoid_m": official_geoid,
            "ellipsoid_shift_z_m": ellipsoid_shift,
            "official_local_shift_xyz_m": shift_official.tolist(),
            "l_nb_boundary_source": "class boundary only; cutline_mask is forbidden for L_nb",
            "alignment_preflight": alignment_preflight,
            "input_hashes": {
                "global": global_hashes,
                "semantic_mask": {rel(semantic_path): semantic_hash},
            },
            "regions": {str(region["region_id"]): region for region in regions},
            "region_stats": region_stats,
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
            if int(ref_mask.sum()) < FRAGMENT_MEASURE_MIN_PIXELS:
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

    # Input-height versus audit-only LoD2-height projection coverage.  Full runs
    # require >=3 visible views for every C00118 building.  Explicit smoke/debug
    # subsets retain however many are visible and mark the aggregate accordingly.
    projection_height_rows: list[dict[str, Any]] = []
    projection_audit_by_building: dict[str, Any] = {}
    debug_subset = bool(args.limit or args.view_stems)
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

    selected_by_building: dict[str, list[GateMeasurement]] = {}
    for building_id in args.core_buildings:
        if args.views_per_building == 0:
            selected_by_building[building_id] = []
            continue
        candidates = [m for m in all_gate_measurements if m.building_id == building_id]
        candidates.sort(key=lambda m: (-m.ref_pixels, m.view_stem))
        selected = candidates[: args.views_per_building]
        if len(selected) < args.views_per_building:
            raise AssertionError(
                f"{building_id}: only {len(selected)} visible views with >=64 P_ref pixels; "
                f"need {args.views_per_building}"
            )
        selected_by_building[building_id] = selected

    frame_by_stem = {frame.stem: frame for frame in frames}
    gate_rows: list[dict[str, Any]] = []
    for building_id in args.core_buildings:
        selected = selected_by_building[building_id]
        if not selected:
            continue
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
                    "visible_view_count_available": sum(
                        1 for m in all_gate_measurements if m.building_id == building_id
                    ),
                    **{k: json_number(v) for k, v in asdict(measurement).items() if k not in {"building_id", "view_stem", "view_name"}},
                    "qa_footprint_buffer_m": QA_FOOTPRINT_BUFFER_M,
                    "qa_buffer_rationale": QA_BUFFER_RATIONALE,
                    "view_selection_rule": "top 3 deterministic views by official P_ref roof pixel area; tie by view stem",
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
                "visible_view_count_available": sum(
                    1 for m in all_gate_measurements if m.building_id == building_id
                ),
                **medians,
                "qa_footprint_buffer_m": QA_FOOTPRINT_BUFFER_M,
                "qa_buffer_rationale": QA_BUFFER_RATIONALE,
                "view_selection_rule": "top 3 deterministic views by official P_ref roof pixel area; tie by view stem",
                "official_geoid_m": official_geoid,
                "official_shift_z_m": official_shift_z,
                "label_actual_source_shift_z_m": legacy_shift_z,
            }
        )

    if not args.skip_overlays:
        for building_id, selected in selected_by_building.items():
            for measurement in selected:
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
                render_overlay(
                    args.fig_dir / f"{building_id}__{frame.stem}.png",
                    data_root / "images" / frame.name,
                    measured,
                    ref_mask,
                    measurement,
                )

    semantic_gate_path = args.docs_dir / "e5_c001_s3_semantic_gate.csv"
    mapping_path = args.docs_dir / "e5_c001_s3_semantic_region_mapping.csv"
    inventory_path = args.docs_dir / "e5_c001_s3_semantic_region_inventory.csv"
    validation_path = args.docs_dir / "e5_c001_s3_raycast_assignment_check.csv"
    height_audit_path = args.docs_dir / "e5_c001_s3_semantic_region_height_audit.csv"
    projection_height_audit_path = (
        args.docs_dir / "e5_c001_s3_semantic_region_projection_height_audit.csv"
    )
    issue_path = args.docs_dir / "e5_c001_s3_issues.csv"
    write_csv(semantic_gate_path, gate_rows)
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
            "handling": "Loss address keeps the fixed clean class mask but projects footprint instances at Arm1-prime zero-iteration input-point median z; LoD2 z is restricted to T0-1/raycast audit. Building-ID audits report actual-source primary and official secondary; raycast IDs are not training inputs.",
        },
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
        "command": [sys.executable, *sys.argv],
        "git_head": git_value("rev-parse", "HEAD"),
        "git_branch": git_value("branch", "--show-current"),
        "container_image": "jointbuildgs:dev",
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
        "claim_boundary": "mechanism upper bound only; not model-free and not S3-B/FM",
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
            "assignment_rule": ASSIGNMENT_RULE,
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
            "l_nb_boundary_source": "class boundary only; no instance cutline",
        },
        "datum_provenance": {
            "official": {"geoid_m": official_geoid, "shift_z_m": official_shift_z},
            "actual_label_source": {
                "geoid_m": float(args.legacy_label_geoid_m),
                "shift_z_m": legacy_shift_z,
            },
            "alignment_preflight": alignment_preflight,
        },
        "projection_height": {
            "source_role": "existing Arm1-prime zero-iteration training input",
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
            "loss_address_footprints_exact_c00118": int(len(footprints)),
            "footprint_source_inventory_total": int(len(all_footprints)),
            "footprint_parts": int(sum(footprint_part_counts.values())),
            "missing_footprint_roof_height_count": int(len(missing_fp_height)),
            "missing_footprint_roof_height_ids": missing_fp_height,
        },
        "outputs": {
            "cache_dir": rel(args.cache_dir),
            "cache_files": len(inventory_rows),
            "semantic_gate_csv": rel(semantic_gate_path),
            "mapping_csv": rel(mapping_path),
            "inventory_csv": rel(inventory_path),
            "raycast_assignment_csv": rel(validation_path),
            "projection_height_audit_csv": rel(height_audit_path),
            "input_z_vs_reference_z_projection_audit_csv": rel(projection_height_audit_path),
            "issues_csv": rel(issue_path),
            "overlay_dir": rel(args.fig_dir),
            "overlay_count": 0 if args.skip_overlays else sum(len(v) for v in selected_by_building.values()),
            "quarantined_partial_caches": partial_cache_inventory,
        },
        "raycast_assignment_aggregate": {
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
            "view_selection": "top official-P_ref area, deterministic tie by view stem",
            "rows": len(gate_rows),
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
