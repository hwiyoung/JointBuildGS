#!/usr/bin/env python3
"""S3-A Track-0 T0-2 seed inventory and T0-3 multiview normal audit.

This is a measurement-only harness.  It reuses the frozen Arm 1-prime inputs
and the already-generated full-frame Omnidata world-normal arrays; it does not
train a model or infer a new prior.

Canonical invocation (from the repository root)::

    docker run --rm --user "$(id -u):$(id -g)" \
      -e HOME=/tmp -e MPLCONFIGDIR=/tmp/matplotlib \
      -e XDG_CACHE_HOME=/tmp \
      -e S3_DOCKER_IMAGE_ID="$(docker image inspect --format '{{.Id}}' jointbuildgs:dev)" \
      -v "$PWD:/workspace/JointBuildGS" -w /workspace/JointBuildGS \
      jointbuildgs:dev python \
      scripts/e5_c001/p2_gsjso/e5_c001_s3_track0_measurements.py

Spatial convention
------------------
Footprints and LoD2 references are EPSG:25832.  SfM and dense initialisation
points use the C001 GS-local frame.  XY is translated by the frozen world
offset.  Orthometric LoD2 roof heights are projected into the ellipsoidal
camera frame with ``z_local = H_ortho + geoid - world_offset_z``.  The geoid
value is read from ``configs/input_and_alignment/projection_datum.json`` and is asserted to be
45.7 m for this locked audit.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import numpy as np


SCRIPT_DIR = Path(__file__).resolve().parent
REPO = Path(__file__).resolve().parents[3]
PYDEPS = REPO / "results/tum_transfer/e5_s1_full_factor/C001/python_deps/timm_0_4_12"
for path in (PYDEPS, SCRIPT_DIR, REPO):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

# These imports deliberately happen after the frozen local dependency path is
# added.  e5_c001_8way imports laspy, which is recorded in that dependency tree.
import shapely  # noqa: E402
from shapely import contains_xy, intersects_xy, make_valid  # noqa: E402
from shapely.geometry import MultiPolygon, Polygon, shape  # noqa: E402
from shapely.ops import unary_union  # noqa: E402

import e5_c001_8way as eight  # noqa: E402
from src.stage2.colmap_io import read_points3d_bin  # noqa: E402
from src.stage2.dataloader import ColmapDataset  # noqa: E402


RUN_ID = "20260713_e5_c001_s3_track0"
RUN_DIR = REPO / "phases/p2-gsjso/runs" / RUN_ID

DATA_ROOT = REPO / "results/tum_transfer/e5_pilot/C001/data_geoidfix_C001_buf20"
SPARSE_POINTS = DATA_ROOT / "sparse/0/points3D.bin"
DENSE_INIT = REPO / "results/tum_transfer/e5_pilot/C001/seeds/seed_dense_C001_buf20.ply"
FOOTPRINTS = REPO / "results/tum_transfer/analysis/footprints_aoi.geojson"
TRAIN_MANIFEST = REPO / "results/tum_transfer/e5_pilot/C001/C001_train_prep_manifest.json"
ARM1P_CONFIG = REPO / "configs/e5_c001/e5_s2p_interaction/gs_e5_C001_s2p_arm1p_dense_r1.yaml"
DATUM_CONFIG = REPO / "configs/input_and_alignment/projection_datum.json"
NORMAL_DIR = REPO / "results/tum_transfer/e5_s2_direction_position/C001/mono_priors/normal_omnidata_world_npy"

CSV_SEED = REPO / "docs/experiments/joint-optimization/e5_c001_s3/tables/e5_c001_s3_seed_inventory.csv"
CSV_NORMAL = REPO / "docs/experiments/joint-optimization/e5_c001_s3/tables/e5_c001_s3_normal_multiview.csv"
MANIFEST = RUN_DIR / "t0_2_t0_3_manifest.json"

SEED_TARGETS = ["4907199", "8568391", "8568392", "4907202", "4908168", "4908178"]
TEXTURELESS3 = {"4907199", "8568391", "8568392"}
COLLAPSE3 = {"4907202", "4908168", "4908178"}

CORE9 = [
    "4907184",
    "4907185",
    "4907198",
    "4907202",
    "4908168",
    "4908178",
    "4907199",
    "8568391",
    "8568392",
]
PREVIOUS10 = [
    "4907199",
    "8568391",
    "8568392",
    "60098",
    "4907186",
    "4907188",
    "4907194",
    "4907195",
    "4907184",
    "4907202",
]
NORMAL_TARGETS = list(dict.fromkeys(CORE9 + PREVIOUS10))

# Locked independent recount used as a drift detector, not as the source of the
# published values.  All published counts are recomputed from the input files.
EXPECTED_SEED_COUNTS = {
    "4907199": (2, 30),
    "8568391": (0, 9),
    "8568392": (0, 29),
    "4907202": (70, 955),
    "4908168": (2, 91),
    "4908178": (24, 395),
}


def full_id(short_id: str) -> str:
    return short_id if short_id.startswith("DEBY_LOD2_") else f"DEBY_LOD2_{short_id}"


def rel(path: Path | str) -> str:
    path = Path(path)
    try:
        return str(path.relative_to(REPO))
    except ValueError:
        return str(path)


def sha256_file(path: Path, block_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(block_size), b""):
            digest.update(block)
    return digest.hexdigest()


def sha256_records(records: Iterable[tuple[str, str]]) -> str:
    digest = hashlib.sha256()
    for name, value in sorted(records):
        digest.update(name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(value.encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest()


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if fields is None:
        fields = []
        for row in rows:
            for key in row:
                if key not in fields:
                    fields.append(key)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def git_value(*args: str) -> str:
    try:
        return subprocess.check_output(["git", *args], cwd=REPO, text=True, stderr=subprocess.STDOUT).strip()
    except Exception as exc:  # noqa: BLE001 - provenance preserves the failure.
        return f"not_available:{exc}"


def load_world_offset() -> np.ndarray:
    payload = json.loads(TRAIN_MANIFEST.read_text(encoding="utf-8"))
    offset = np.asarray(payload["world_offset"], dtype=np.float64)
    if offset.shape != (3,) or not np.all(np.isfinite(offset)):
        raise RuntimeError(f"invalid world_offset in {rel(TRAIN_MANIFEST)}: {offset!r}")
    return offset


def load_datum(expected_geoid_m: float) -> tuple[float, str]:
    payload = json.loads(DATUM_CONFIG.read_text(encoding="utf-8"))
    crs = str(payload.get("geo_crs", ""))
    geoid = float(payload["orthometric_geoid_m"])
    if crs != "EPSG:25832":
        raise RuntimeError(f"T0 spatial CRS must be EPSG:25832, got {crs!r}")
    if not math.isclose(geoid, expected_geoid_m, rel_tol=0.0, abs_tol=1e-9):
        raise RuntimeError(f"locked geoid is {expected_geoid_m:.3f} m, config contains {geoid:.6f} m")
    return geoid, crs


def load_footprints(ids: Iterable[str]) -> tuple[dict[str, Any], str]:
    wanted = {full_id(short_id) for short_id in ids}
    payload = json.loads(FOOTPRINTS.read_text(encoding="utf-8"))
    crs_name = str(payload.get("crs", {}).get("properties", {}).get("name", ""))
    if "25832" not in crs_name:
        raise RuntimeError(f"footprint CRS is not explicitly EPSG:25832: {crs_name!r}")
    parts: dict[str, list[Any]] = {building_id: [] for building_id in wanted}
    for feature in payload.get("features", []):
        building_id = str((feature.get("properties") or {}).get("building_id", ""))
        if building_id in wanted:
            geom = make_valid(shape(feature["geometry"]))
            if not geom.is_empty:
                parts[building_id].append(geom)
    merged: dict[str, Any] = {}
    for building_id in wanted:
        if not parts[building_id]:
            raise RuntimeError(f"missing footprint: {building_id}")
        geom = make_valid(unary_union(parts[building_id]))
        if geom.is_empty:
            raise RuntimeError(f"empty footprint after union: {building_id}")
        merged[building_id] = geom
    return merged, crs_name


def read_ply_xyz_ascii(path: Path) -> tuple[np.ndarray, int]:
    vertex_count: int | None = None
    header_lines = 0
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            header_lines += 1
            if line.startswith("element vertex "):
                vertex_count = int(line.split()[-1])
            if line.strip() == "end_header":
                break
    if vertex_count is None:
        raise RuntimeError(f"ASCII PLY vertex count missing: {rel(path)}")
    # Training's read_init_pointcloud returns float32, so inventory the exact
    # 0-iteration coordinates seen by GaussianModel2D rather than higher-
    # precision text literals that are discarded at load time.
    xyz = np.loadtxt(path, skiprows=header_lines, max_rows=vertex_count, usecols=(0, 1, 2), dtype=np.float32)
    xyz = np.asarray(xyz, dtype=np.float32).reshape(-1, 3)
    if len(xyz) != vertex_count:
        raise RuntimeError(f"PLY declared {vertex_count} vertices but read {len(xyz)}")
    return xyz, vertex_count


def exact_polygon_count(points_local: np.ndarray, footprint: Any, offset: np.ndarray) -> tuple[int, int]:
    """Count GS-local points strictly inside an EPSG:25832 polygon.

    Boundary points are reported separately and excluded from the inventory so
    a seed lying on a shared footprint edge cannot be assigned twice.
    """

    minx, miny, maxx, maxy = footprint.bounds
    # Promote the local float32 coordinates before restoring the large UTM
    # offset; adding in float32 would quantise EPSG:25832 XY to centimetres or
    # worse and move edge-near points across the polygon.
    x = points_local[:, 0].astype(np.float64) + float(offset[0])
    y = points_local[:, 1].astype(np.float64) + float(offset[1])
    candidate = (x >= minx) & (x <= maxx) & (y >= miny) & (y <= maxy)
    indices = np.flatnonzero(candidate)
    if not len(indices):
        return 0, 0
    inside = contains_xy(footprint, x[indices], y[indices])
    covered = intersects_xy(footprint, x[indices], y[indices])
    boundary = covered & ~inside
    return int(np.count_nonzero(inside)), int(np.count_nonzero(boundary))


def seed_group(short_id: str) -> str:
    if short_id in TEXTURELESS3:
        return "textureless_observed_3"
    if short_id in COLLAPSE3:
        return "collapse_3"
    return ""


def measure_seed_inventory(offset: np.ndarray, strict_expected: bool) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    footprints, footprint_crs = load_footprints(SEED_TARGETS)
    # ColmapDataset likewise casts SfM centres to float32 before model init.
    sparse = read_points3d_bin(SPARSE_POINTS)[:, :3].astype(np.float32)
    dense, dense_declared = read_ply_xyz_ascii(DENSE_INIT)
    source_hashes = {
        rel(SPARSE_POINTS): sha256_file(SPARSE_POINTS),
        rel(DENSE_INIT): sha256_file(DENSE_INIT),
        rel(FOOTPRINTS): sha256_file(FOOTPRINTS),
        rel(TRAIN_MANIFEST): sha256_file(TRAIN_MANIFEST),
        rel(ARM1P_CONFIG): sha256_file(ARM1P_CONFIG),
    }
    rows: list[dict[str, Any]] = []
    mismatches: list[str] = []
    for short_id in SEED_TARGETS:
        building_id = full_id(short_id)
        footprint = footprints[building_id]
        sfm_count, sfm_boundary = exact_polygon_count(sparse, footprint, offset)
        dense_count, dense_boundary = exact_polygon_count(dense, footprint, offset)
        expected_sfm, expected_dense = EXPECTED_SEED_COUNTS[short_id]
        qa_match = sfm_count == expected_sfm and dense_count == expected_dense
        if not qa_match:
            mismatches.append(
                f"{building_id}: computed=({sfm_count},{dense_count}) expected=({expected_sfm},{expected_dense})"
            )
        rows.append(
            {
                "building_id": building_id,
                "group": seed_group(short_id),
                "footprint_area_m2": f"{float(footprint.area):.4f}",
                "sfm_seed_points_in_footprint": sfm_count,
                "dense_init_points_in_footprint": dense_count,
                "initial_gaussians_in_footprint": sfm_count + dense_count,
                "sfm_boundary_points_excluded": sfm_boundary,
                "dense_boundary_points_excluded": dense_boundary,
                "init_pointcloud_mode": "concat_sfm_plus_dense",
                "sfm_scene_points_total": len(sparse),
                "dense_init_scene_points_total": len(dense),
                "initial_scene_gaussians_total": len(sparse) + len(dense),
                "same_pointcloud": "false",
                "expected_sfm_count_locked_qa": expected_sfm,
                "expected_dense_count_locked_qa": expected_dense,
                "qa_match_expected": str(qa_match).lower(),
                "point_frame": "GS-local (EPSG:25832 XY minus world_offset; ellipsoidal Z local)",
                "footprint_crs": "EPSG:25832",
                "count_rule": "exact polygon contains_xy; boundary excluded and logged; no buffer",
                "sfm_source": rel(SPARSE_POINTS),
                "sfm_source_sha256": source_hashes[rel(SPARSE_POINTS)],
                "dense_init_source": rel(DENSE_INIT),
                "dense_init_source_sha256": source_hashes[rel(DENSE_INIT)],
                "footprint_source": rel(FOOTPRINTS),
                "footprint_source_sha256": source_hashes[rel(FOOTPRINTS)],
                "arm1p_config": rel(ARM1P_CONFIG),
                "arm1p_config_sha256": source_hashes[rel(ARM1P_CONFIG)],
            }
        )
    if dense_declared != len(dense):
        raise RuntimeError("dense PLY vertex-count QA failed")
    if strict_expected and mismatches:
        raise RuntimeError("seed inventory drift:\n" + "\n".join(mismatches))
    meta = {
        "rows": len(rows),
        "sfm_scene_points_total": len(sparse),
        "dense_init_scene_points_total": len(dense),
        "initial_scene_gaussians_total": len(sparse) + len(dense),
        "footprint_crs_source": footprint_crs,
        "strict_expected": strict_expected,
        "mismatches": mismatches,
        "source_hashes": source_hashes,
    }
    return rows, meta


def iter_polygons(geometry: Polygon | MultiPolygon) -> Iterable[Polygon]:
    if isinstance(geometry, Polygon):
        yield geometry
    elif isinstance(geometry, MultiPolygon):
        yield from geometry.geoms


def reference_roof_points(surfaces: list[eight.RoofSurface]) -> np.ndarray:
    chunks: list[np.ndarray] = []
    for surface in surfaces:
        for polygon in iter_polygons(surface.polygon):
            xy = np.asarray(polygon.exterior.coords, dtype=np.float64)[:, :2]
            if len(xy):
                z = surface.z_at(xy[:, 0], xy[:, 1])
                chunks.append(np.column_stack([xy, z]))
    if not chunks:
        return np.zeros((0, 3), dtype=np.float64)
    return np.vstack(chunks)


def roof_normal_world(surface: eight.RoofSurface) -> np.ndarray:
    normal = np.asarray([-surface.ax, -surface.by, 1.0], dtype=np.float64)
    normal /= max(float(np.linalg.norm(normal)), 1e-12)
    if normal[2] < 0:
        normal = -normal
    return normal


def project_ortho_points(
    points_utm_ortho: np.ndarray,
    frame: Any,
    world_offset: np.ndarray,
    geoid_m: float,
) -> tuple[np.ndarray, np.ndarray]:
    local = np.asarray(points_utm_ortho, dtype=np.float64).copy()
    local[:, 0] -= world_offset[0]
    local[:, 1] -= world_offset[1]
    local[:, 2] += geoid_m - world_offset[2]
    camera = (frame.R @ local.T).T + frame.t.reshape(1, 3)
    depth = camera[:, 2]
    projected = (frame.K @ camera.T).T
    uv = projected[:, :2] / np.maximum(projected[:, 2:3], 1e-12)
    return uv, depth


def square_crop(crop: tuple[int, int, int, int], width: int, height: int) -> tuple[int, int, int, int]:
    x0, y0, x1, y1 = crop
    cx = (x0 + x1) / 2.0
    cy = (y0 + y1) / 2.0
    side = min(max(x1 - x0, y1 - y0, 128), width, height)
    x0 = int(round(cx - side / 2.0))
    y0 = int(round(cy - side / 2.0))
    x1 = x0 + int(side)
    y1 = y0 + int(side)
    if x0 < 0:
        x1 -= x0
        x0 = 0
    if y0 < 0:
        y1 -= y0
        y0 = 0
    if x1 > width:
        x0 -= x1 - width
        x1 = width
    if y1 > height:
        y0 -= y1 - height
        y1 = height
    return max(0, x0), max(0, y0), min(width, x1), min(height, y1)


def visible_views(
    frames: list[Any],
    roof_points: np.ndarray,
    world_offset: np.ndarray,
    geoid_m: float,
    limit: int,
) -> tuple[list[dict[str, Any]], int]:
    candidates: list[dict[str, Any]] = []
    for view_idx, frame in enumerate(frames):
        uv, depth = project_ortho_points(roof_points, frame, world_offset, geoid_m)
        valid = np.isfinite(uv).all(axis=1) & np.isfinite(depth) & (depth > 0)
        if np.count_nonzero(valid) < 4:
            continue
        xy = uv[valid]
        u0, v0 = np.min(xy, axis=0)
        u1, v1 = np.max(xy, axis=0)
        width, height = int(frame.width), int(frame.height)
        if u1 < 0 or v1 < 0 or u0 >= width or v0 >= height:
            continue
        clipped_area = max(0.0, min(u1, width - 1) - max(u0, 0.0)) * max(
            0.0, min(v1, height - 1) - max(v0, 0.0)
        )
        if clipped_area <= 20.0:
            continue
        margin = 36
        crop0 = (
            max(0, int(math.floor(u0)) - margin),
            max(0, int(math.floor(v0)) - margin),
            min(width, int(math.ceil(u1)) + margin),
            min(height, int(math.ceil(v1)) + margin),
        )
        crop = square_crop(crop0, width, height)
        crop_area = max(1, (crop[2] - crop[0]) * (crop[3] - crop[1]))
        candidates.append(
            {
                "view_idx": view_idx,
                "crop": crop,
                "projected_bbox_area_px2": clipped_area,
                "visibility_score": clipped_area / crop_area,
            }
        )
    candidates.sort(
        key=lambda row: (float(row["visibility_score"]), float(row["projected_bbox_area_px2"])),
        reverse=True,
    )
    return candidates[:limit], len(candidates)


def central_crop_bounds(crop: tuple[int, int, int, int], central_fraction: float) -> tuple[int, int, int, int]:
    x0, y0, x1, y1 = crop
    margin_fraction = (1.0 - central_fraction) / 2.0
    mx = int(round((x1 - x0) * margin_fraction))
    my = int(round((y1 - y0) * margin_fraction))
    return x0 + mx, y0 + my, x1 - mx, y1 - my


def quality_bin(angle_deg: float) -> str:
    if angle_deg < 15.0:
        return "good_lt15"
    if angle_deg <= 30.0:
        return "borderline_15_30"
    return "bad_gt30"


def target_membership(short_id: str) -> str:
    groups = []
    if short_id in CORE9:
        groups.append("core9")
    if short_id in PREVIOUS10:
        groups.append("previous10")
    return "+".join(groups)


def measure_normal_multiview(
    offset: np.ndarray,
    geoid_m: float,
    views_per_building: int,
    min_views: int,
    central_fraction: float,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    references = eight.parse_lod2_roofs(eight.LOD2_DIR, {full_id(short_id) for short_id in NORMAL_TARGETS})
    dataset = ColmapDataset(
        root=str(DATA_ROOT),
        downscale=1.0,
        load_depth=False,
        load_normal=False,
        load_semantic=False,
    )
    rows: list[dict[str, Any]] = []
    selected_normal_hashes: dict[str, str] = {}
    building_meta: dict[str, Any] = {}
    for short_id in NORMAL_TARGETS:
        building_id = full_id(short_id)
        surfaces = references.get(building_id, [])
        if not surfaces:
            raise RuntimeError(f"reference roof missing: {building_id}")
        roof_points = reference_roof_points(surfaces)
        if len(roof_points) < 4:
            raise RuntimeError(f"too few reference roof vertices: {building_id}")
        selected, candidate_count = visible_views(
            dataset.frames, roof_points, offset, geoid_m, views_per_building
        )
        if len(selected) < min_views:
            raise RuntimeError(
                f"{building_id} has {len(selected)} selected visible views; locked minimum is {min_views}"
            )
        ref_normals = np.vstack([roof_normal_world(surface) for surface in surfaces])
        part: list[dict[str, Any]] = []
        for rank, candidate in enumerate(selected, start=1):
            view_idx = int(candidate["view_idx"])
            frame = dataset.frames[view_idx]
            normal_path = NORMAL_DIR / f"{Path(frame.name).stem}.npy"
            if not normal_path.exists():
                raise RuntimeError(f"world-normal array missing: {rel(normal_path)}")
            normal = np.load(normal_path, mmap_mode="r")
            if normal.shape != (int(frame.height), int(frame.width), 3):
                raise RuntimeError(
                    f"normal/image shape mismatch for {frame.name}: {normal.shape} vs "
                    f"{(frame.height, frame.width, 3)}"
                )
            crop = tuple(candidate["crop"])
            central = central_crop_bounds(crop, central_fraction)
            cx0, cy0, cx1, cy1 = central
            pixels = np.asarray(normal[cy0:cy1, cx0:cx1], dtype=np.float64).reshape(-1, 3)
            finite = np.isfinite(pixels).all(axis=1)
            norm = np.linalg.norm(pixels, axis=1)
            valid = finite & (norm > 1e-6)
            pixels = pixels[valid]
            if not len(pixels):
                raise RuntimeError(f"no valid central normal pixels: {building_id} view {view_idx}")
            pixels /= np.linalg.norm(pixels, axis=1, keepdims=True)
            closest_dot = np.max(np.abs(pixels @ ref_normals.T), axis=1)
            angles = np.degrees(np.arccos(np.clip(closest_dot, -1.0, 1.0)))
            normal_key = rel(normal_path)
            normal_hash = selected_normal_hashes.get(normal_key)
            if normal_hash is None:
                normal_hash = sha256_file(normal_path)
                selected_normal_hashes[normal_key] = normal_hash
            part.append(
                {
                    "building_id": building_id,
                    "target_membership": target_membership(short_id),
                    "view_rank": rank,
                    "view_idx": view_idx,
                    "image_name": frame.name,
                    "visible_view_candidates": candidate_count,
                    "visibility_score": f"{float(candidate['visibility_score']):.8f}",
                    "projected_bbox_area_px2": f"{float(candidate['projected_bbox_area_px2']):.2f}",
                    "crop_xyxy": ",".join(str(value) for value in crop),
                    "central64_xyxy": ",".join(str(value) for value in central),
                    "central_fraction": f"{central_fraction:.2f}",
                    "valid_normal_pixels": len(pixels),
                    "view_angle_error_median_deg_absdot": f"{float(np.median(angles)):.4f}",
                    "view_angle_error_p75_deg_absdot": f"{float(np.percentile(angles, 75)):.4f}",
                    "view_angle_error_p90_deg_absdot": f"{float(np.percentile(angles, 90)):.4f}",
                    "normal_model": "Omnidata DPT-Hybrid surface_normal_dpt_hybrid_384",
                    "normal_frame": "world",
                    "normal_path": normal_key,
                    "normal_sha256": normal_hash,
                    "reference_roof_faces": len(surfaces),
                    "reference_lod2_dir": rel(eight.LOD2_DIR),
                    "reference_crs": "EPSG:25832",
                    "projection_geoid_m": f"{geoid_m:.3f}",
                    "projection_z_formula": "z_local=H_ortho+geoid-world_offset_z",
                    "pixel_score_rule": "central 64% crop; abs-dot to closest LoD2 roof-face normal",
                }
            )
        view_medians = [float(row["view_angle_error_median_deg_absdot"]) for row in part]
        building_median = float(np.median(view_medians))
        building_bin = quality_bin(building_median)
        for row in part:
            row["building_view_count"] = len(part)
            row["building_angle_error_median_deg_absdot"] = f"{building_median:.4f}"
            row["building_quality_bin_locked"] = building_bin
        rows.extend(part)
        building_meta[building_id] = {
            "views": len(part),
            "candidate_views": candidate_count,
            "building_angle_median_deg_absdot": building_median,
            "quality_bin": building_bin,
        }
        print(
            json.dumps(
                {
                    "stage": "T0-3",
                    "building_id": building_id,
                    "views": len(part),
                    "angle_median_deg_absdot": round(building_median, 4),
                    "quality_bin": building_bin,
                },
                ensure_ascii=False,
            ),
            flush=True,
        )
    if len(building_meta) != len(NORMAL_TARGETS):
        raise RuntimeError(f"normal target count QA failed: {len(building_meta)} != {len(NORMAL_TARGETS)}")
    if any(int(meta["views"]) < min_views for meta in building_meta.values()):
        raise RuntimeError("normal minimum-view QA failed")
    meta = {
        "target_buildings": len(building_meta),
        "view_rows": len(rows),
        "views_per_building_requested": views_per_building,
        "min_views_locked": min_views,
        "central_fraction": central_fraction,
        "world_normal_files_selected": len(selected_normal_hashes),
        "selected_normal_tree_sha256": sha256_records(selected_normal_hashes.items()),
        "selected_normal_hashes": selected_normal_hashes,
        "buildings": building_meta,
    }
    return rows, meta


def input_hashes_common() -> dict[str, str]:
    paths = [
        DATUM_CONFIG,
        DATA_ROOT / "sparse/0/cameras.bin",
        DATA_ROOT / "sparse/0/images.bin",
        *sorted(eight.LOD2_DIR.glob("*.gml")),
    ]
    return {rel(path): sha256_file(path) for path in paths}


def build_manifest(
    args: argparse.Namespace,
    offset: np.ndarray,
    geoid_m: float,
    crs: str,
    seed_meta: dict[str, Any] | None,
    normal_meta: dict[str, Any] | None,
) -> dict[str, Any]:
    import torch

    output_hashes: dict[str, str] = {}
    for path in (CSV_SEED, CSV_NORMAL):
        if path.exists():
            output_hashes[rel(path)] = sha256_file(path)
    canonical_command = (
        'docker run --rm --user "$(id -u):$(id -g)" '
        "-e HOME=/tmp -e MPLCONFIGDIR=/tmp/matplotlib -e XDG_CACHE_HOME=/tmp "
        '-e S3_DOCKER_IMAGE_ID="$(docker image inspect --format \'{{.Id}}\' jointbuildgs:dev)" '
        '-v "$PWD:/workspace/JointBuildGS" -w /workspace/JointBuildGS '
        "jointbuildgs:dev python scripts/e5_c001/p2_gsjso/e5_c001_s3_track0_measurements.py"
    )
    return {
        "run_id": RUN_ID,
        "task": "S3-A Track 0 T0-2 seed inventory + T0-3 normal multiview audit",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "training_started": False,
        "git_head": git_value("rev-parse", "HEAD"),
        "git_branch": git_value("branch", "--show-current"),
        "docker_image": "jointbuildgs:dev",
        "docker_image_id": os.environ.get("S3_DOCKER_IMAGE_ID", "not_provided"),
        "canonical_command": canonical_command,
        "runtime": {
            "python": platform.python_version(),
            "numpy": np.__version__,
            "shapely": shapely.__version__,
            "torch": torch.__version__,
            "platform": platform.platform(),
            "uid": os.getuid(),
            "gid": os.getgid(),
        },
        "spatial": {
            "crs": crs,
            "world_offset": offset.tolist(),
            "orthometric_geoid_m": geoid_m,
            "projection_formula": "x_local=E-world_offset_x; y_local=N-world_offset_y; z_local=H_ortho+geoid-world_offset_z",
        },
        "parameters": {
            "only": args.only,
            "views_per_building": args.views_per_building,
            "min_views": args.min_views,
            "central_fraction": args.central_fraction,
            "strict_seed_expected": args.strict_seed_expected,
        },
        "input_hashes_common": input_hashes_common(),
        "t0_2": seed_meta,
        "t0_3": normal_meta,
        "output_hashes": output_hashes,
    }


def run(args: argparse.Namespace) -> None:
    offset = load_world_offset()
    geoid_m, crs = load_datum(args.expected_geoid_m)
    seed_meta: dict[str, Any] | None = None
    normal_meta: dict[str, Any] | None = None

    if args.only in {"all", "seed"}:
        seed_rows, seed_meta = measure_seed_inventory(offset, args.strict_seed_expected)
        write_csv(CSV_SEED, seed_rows)
        print(
            json.dumps(
                {
                    "stage": "T0-2",
                    "output": rel(CSV_SEED),
                    "rows": len(seed_rows),
                    "counts": {
                        row["building_id"]: row["initial_gaussians_in_footprint"] for row in seed_rows
                    },
                },
                ensure_ascii=False,
            ),
            flush=True,
        )

    if args.only in {"all", "normal"}:
        normal_rows, normal_meta = measure_normal_multiview(
            offset,
            geoid_m,
            args.views_per_building,
            args.min_views,
            args.central_fraction,
        )
        write_csv(CSV_NORMAL, normal_rows)
        print(
            json.dumps(
                {"stage": "T0-3", "output": rel(CSV_NORMAL), "rows": len(normal_rows)},
                ensure_ascii=False,
            ),
            flush=True,
        )

    manifest = build_manifest(args, offset, geoid_m, crs, seed_meta, normal_meta)
    RUN_DIR.mkdir(parents=True, exist_ok=True)
    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "manifest": rel(MANIFEST),
                "seed_rows": 0 if seed_meta is None else seed_meta["rows"],
                "normal_buildings": 0 if normal_meta is None else normal_meta["target_buildings"],
                "qa": "pass",
            },
            ensure_ascii=False,
        ),
        flush=True,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--only", choices=("all", "seed", "normal"), default="all")
    parser.add_argument("--views-per-building", type=int, default=5)
    parser.add_argument("--min-views", type=int, default=3)
    parser.add_argument("--central-fraction", type=float, default=0.64)
    parser.add_argument("--expected-geoid-m", type=float, default=45.7)
    parser.add_argument(
        "--strict-seed-expected",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Fail if the independent locked recount differs from recomputed counts.",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if args.views_per_building < args.min_views:
        raise SystemExit("--views-per-building must be >= --min-views")
    if not (0.0 < args.central_fraction <= 1.0):
        raise SystemExit("--central-fraction must be in (0, 1]")
    run(args)


if __name__ == "__main__":
    main()
