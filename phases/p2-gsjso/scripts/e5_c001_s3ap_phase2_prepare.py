#!/usr/bin/env python3
"""Prepare deterministic S3-A-prime crop roots and locked Phase-2 configs.

This script never starts training.  It stages native-pixel crops, fixed COLMAP
camera records, crop-visible observed SfM points, image-derived priors, and the
locked 42-job inventory.  LoD2 roof geometry, ALS, and depth GT are not loaded.
"""
from __future__ import annotations

import argparse
import copy
import csv
import hashlib
import heapq
import json
import math
import os
import struct
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence

import numpy as np
import yaml
from PIL import Image as PILImage
from shapely import make_valid
from shapely.geometry import MultiPolygon, Polygon, box, shape
from shapely.ops import unary_union

from src.stage2.colmap_io import (
    CAMERA_MODEL_NAMES,
    Camera,
    Image,
    read_cameras_bin,
    read_images_bin,
    read_points3d_bin,
)


REPO = Path(__file__).resolve().parents[3]
DEFAULT_LOCK = REPO / "phases/p2-gsjso/configs/e5_c001_s3ap_phase2_lock.json"

PROGRESS_FIELDS = [
    "sequence", "stage", "building_id", "view_stem", "status", "detail", "updated_utc"
]
JOB_FIELDS = [
    "sequence", "job_id", "job_class", "building_id", "arm", "replicate", "random_seed",
    "height_delta_m", "tilt_deg", "config_path", "config_sha256", "data_root",
    "surface_seed_npz", "surface_seed_sha256", "out_dir", "final_checkpoint",
    "iterations", "gt_used", "lod2_used", "als_used", "status",
]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def resolve(value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else REPO / path


def relative(path: str | Path) -> str:
    path = resolve(path)
    try:
        return str(path.resolve().relative_to(REPO.resolve()))
    except ValueError:
        return str(path.resolve())


def container_path(path: str | Path, lock: dict[str, Any]) -> str:
    rel = relative(path)
    if Path(rel).is_absolute():
        raise ValueError(f"path is outside repository and cannot be container-addressed: {path}")
    return f"{lock['container_repo_root'].rstrip('/')}/{rel}"


def sha256_file(path: str | Path, block_size: int = 1 << 20) -> str:
    digest = hashlib.sha256()
    with resolve(path).open("rb") as handle:
        for block in iter(lambda: handle.read(block_size), b""):
            digest.update(block)
    return digest.hexdigest()


def sha256_json(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def git_value(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=REPO, text=True).strip()


def atomic_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(value, encoding="utf-8")
    os.replace(temporary, path)


def atomic_json(path: Path, value: Any) -> None:
    atomic_text(path, json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n")


def atomic_yaml(path: Path, value: Any) -> None:
    atomic_text(path, yaml.safe_dump(value, sort_keys=False, allow_unicode=True))


def atomic_csv(path: Path, rows: Sequence[dict[str, Any]], fields: Sequence[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    with temporary.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(fields), extrasaction="ignore", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def atomic_npy(path: Path, array: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    with temporary.open("wb") as handle:
        np.save(handle, array, allow_pickle=False)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def atomic_npz(path: Path, arrays: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    with temporary.open("wb") as handle:
        np.savez_compressed(handle, **arrays)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def atomic_png(path: Path, array: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.stem}.tmp.png")
    PILImage.fromarray(array).save(temporary, format="PNG", compress_level=6)
    os.replace(temporary, path)


def read_metadata_scalar(value: np.ndarray | str | bytes) -> dict[str, Any]:
    if isinstance(value, np.ndarray):
        value = value.item()
    if isinstance(value, bytes):
        value = value.decode("utf-8")
    result = json.loads(str(value))
    if not isinstance(result, dict):
        raise ValueError("metadata_json must decode to an object")
    return result


def load_lock(path: str | Path = DEFAULT_LOCK) -> dict[str, Any]:
    lock = json.loads(resolve(path).read_text(encoding="utf-8"))
    if lock.get("schema") != "jointbuildgs.s3ap.phase2.lock.v1":
        raise ValueError("unexpected Phase-2 lock schema")
    if lock["safety"].get("gt_lod2_or_als_allowed_for_input_generation") is not False:
        raise ValueError("GT/LoD2/ALS input generation must be disabled")
    if lock["safety"].get("mvs_initialization_allowed") is not False:
        raise ValueError("MVS initialization must be disabled")
    if int(lock["training"]["iterations"]) != 30000:
        raise ValueError("Phase-2 iteration lock drift")
    expected = {"4907199": 6, "8568391": 3, "8568392": 3}
    actual = {key: len(value["visible_views"]) for key, value in lock["targets"].items()}
    if actual != expected:
        raise ValueError(f"locked visible-view count drift: {actual}")
    return lock


def validate_runtime_attestation(lock: dict[str, Any]) -> dict[str, Any]:
    """Require the host launcher to attest the locked image and --user mapping."""

    if not (Path("/.dockerenv").exists() or bool(os.environ.get("container"))):
        raise RuntimeError("Phase-2 preparation must execute inside Docker")
    names = lock["runtime"]["attestation_env"]
    image_id = os.environ.get(names["image_id"], "")
    uid_text = os.environ.get(names["host_uid"], "")
    gid_text = os.environ.get(names["host_gid"], "")
    if image_id != lock["runtime"]["docker_image_id"]:
        raise RuntimeError("locked Docker image ID attestation is absent or mismatched")
    if not uid_text.isdigit() or not gid_text.isdigit():
        raise RuntimeError("host UID/GID attestation is absent")
    if os.getuid() != int(uid_text) or os.getgid() != int(gid_text):
        raise RuntimeError(
            f"--user mapping mismatch: container={os.getuid()}:{os.getgid()} "
            f"host={uid_text}:{gid_text}"
        )
    cache_env = lock["runtime"].get("writable_cache_env") or {}
    if set(cache_env) != {"HOME", "XDG_CACHE_HOME", "TORCH_EXTENSIONS_DIR"}:
        raise RuntimeError("writable cache environment lock is incomplete")
    cache_audit: dict[str, dict[str, Any]] = {}
    for name, expected in cache_env.items():
        actual = os.environ.get(name)
        if actual != expected:
            raise RuntimeError(f"{name} cache attestation mismatch: {actual!r} != {expected!r}")
        path = Path(actual)
        if not path.is_dir() or not os.access(path, os.W_OK | os.X_OK):
            raise RuntimeError(f"{name} cache path is not a writable directory: {path}")
        cache_audit[name] = {"path": str(path), "writable": True}
    return {
        "docker_image": lock["runtime"]["docker_image"],
        "docker_image_id": image_id,
        "container_uid": os.getuid(), "container_gid": os.getgid(),
        "host_uid": int(uid_text), "host_gid": int(gid_text),
        "user_mapping_exact": True,
        "writable_cache_env": cache_audit,
    }


def crop_box_4x3(
    mask: np.ndarray,
    image_width: int,
    image_height: int,
    *,
    margin_px: int = 32,
    minimum_width_px: int = 256,
    width_multiple_px: int = 16,
) -> tuple[int, int, int, int]:
    """Exact deterministic crop rule reused by the frozen FM pair pipeline."""
    y, x = np.nonzero(mask[:image_height, :image_width])
    if not len(x):
        raise RuntimeError("target region lies outside source image")
    target_w = int(x.max() - x.min() + 1 + 2 * margin_px)
    target_h = int(y.max() - y.min() + 1 + 2 * margin_px)
    width = max(minimum_width_px, target_w, int(math.ceil(target_h * 4.0 / 3.0)))
    width = int(math.ceil(width / width_multiple_px) * width_multiple_px)
    max_width = min(image_width, int(math.floor(image_height * 4.0 / 3.0)))
    max_width = max(width_multiple_px, max_width - (max_width % width_multiple_px))
    width = min(width, max_width)
    height = int(width * 3 // 4)
    cx = float(x.min() + x.max()) / 2.0
    cy = float(y.min() + y.max()) / 2.0
    x0 = int(round(cx - width / 2.0))
    y0 = int(round(cy - height / 2.0))
    x0 = min(max(0, x0), image_width - width)
    y0 = min(max(0, y0), image_height - height)
    return x0, y0, x0 + width, y0 + height


def adjust_camera(camera: Camera, camera_id: int, crop: tuple[int, int, int, int]) -> Camera:
    """Shift only the principal point; preserve focal/distortion parameters."""
    x0, y0, x1, y1 = crop
    params = np.asarray(camera.params, dtype=np.float64).copy()
    if camera.model in {"SIMPLE_PINHOLE", "SIMPLE_RADIAL", "SIMPLE_RADIAL_FISHEYE", "RADIAL", "RADIAL_FISHEYE"}:
        params[1] -= x0
        params[2] -= y0
    elif camera.model in {"PINHOLE", "OPENCV", "OPENCV_FISHEYE", "FULL_OPENCV"}:
        params[2] -= x0
        params[3] -= y0
    else:
        raise RuntimeError(f"unsupported camera model for native crop: {camera.model}")
    return Camera(camera_id, camera.model, x1 - x0, y1 - y0, params)


def write_cameras_bin(path: Path, cameras: dict[int, Camera]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    with temporary.open("wb") as handle:
        handle.write(struct.pack("<Q", len(cameras)))
        for camera_id in sorted(cameras):
            camera = cameras[camera_id]
            model_id, nparams = CAMERA_MODEL_NAMES[camera.model]
            params = np.asarray(camera.params, dtype=np.float64)
            if len(params) != nparams:
                raise RuntimeError(f"{camera.model}: expected {nparams} parameters, got {len(params)}")
            handle.write(struct.pack("<iiQQ", int(camera.id), int(model_id), int(camera.width), int(camera.height)))
            handle.write(struct.pack("<" + "d" * nparams, *params.tolist()))
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def write_images_bin(path: Path, images: dict[int, Image]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    with temporary.open("wb") as handle:
        handle.write(struct.pack("<Q", len(images)))
        for image_id in sorted(images):
            image = images[image_id]
            handle.write(struct.pack("<I", int(image.id)))
            handle.write(struct.pack("<dddd", *np.asarray(image.qvec, dtype=np.float64).tolist()))
            handle.write(struct.pack("<ddd", *np.asarray(image.tvec, dtype=np.float64).tolist()))
            handle.write(struct.pack("<I", int(image.camera_id)))
            handle.write(image.name.encode("utf-8") + b"\x00")
            handle.write(struct.pack("<Q", 0))
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def write_points3d_bin(path: Path, points: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    with temporary.open("wb") as handle:
        handle.write(struct.pack("<Q", len(points)))
        for point_id, row in enumerate(points, 1):
            x, y, z, r, g, b = row[:6]
            handle.write(struct.pack("<Q", point_id))
            handle.write(struct.pack("<ddd", float(x), float(y), float(z)))
            handle.write(struct.pack("<BBB", int(r), int(g), int(b)))
            handle.write(struct.pack("<d", 0.0))
            handle.write(struct.pack("<Q", 0))
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def project_points(points_xyz: np.ndarray, image: Image, camera: Camera) -> tuple[np.ndarray, np.ndarray]:
    camera_xyz = (image.R() @ points_xyz.T).T + np.asarray(image.tvec, dtype=np.float64)[None, :]
    homogeneous = (camera.K() @ camera_xyz.T).T
    depth = camera_xyz[:, 2]
    pixels = np.full((len(points_xyz), 2), np.nan, dtype=np.float64)
    valid = depth > 1e-9
    pixels[valid] = homogeneous[valid, :2] / homogeneous[valid, 2:3]
    return pixels, depth


def crop_visible_sfm_subset(
    points: np.ndarray,
    frames: Sequence[tuple[Image, Camera, tuple[int, int, int, int]]],
) -> tuple[np.ndarray, dict[str, int]]:
    """Union of observed SfM points projecting into at least one source crop."""
    union = np.zeros(len(points), dtype=bool)
    counts: dict[str, int] = {}
    xyz = np.asarray(points[:, :3], dtype=np.float64)
    for image, camera, box in frames:
        pixels, depth = project_points(xyz, image, camera)
        x0, y0, x1, y1 = box
        mask = (
            np.isfinite(pixels).all(axis=1)
            & (depth > 0)
            & (pixels[:, 0] >= x0)
            & (pixels[:, 0] < x1)
            & (pixels[:, 1] >= y0)
            & (pixels[:, 1] < y1)
        )
        counts[Path(image.name).stem] = int(mask.sum())
        union |= mask
    return np.asarray(points[union, :6]), counts


def load_target_mask(path: Path, building_id: str) -> tuple[np.ndarray, np.ndarray, dict[str, Any]]:
    with np.load(path, allow_pickle=False) as archive:
        if set(archive.files) != {"region_ids", "cutline_mask", "metadata_json"}:
            raise ValueError(f"semantic-region keys drift: {path}: {archive.files}")
        region_ids = np.asarray(archive["region_ids"], dtype=np.int32)
        cutline = np.asarray(archive["cutline_mask"], dtype=np.bool_)
        metadata = read_metadata_scalar(archive["metadata_json"])
    full_id = building_id if building_id.startswith("DEBY_LOD2_") else f"DEBY_LOD2_{building_id}"
    wanted = [int(key) for key, row in metadata.get("regions", {}).items() if row.get("building_id") == full_id]
    mask = np.isin(region_ids, np.asarray(wanted, dtype=np.int32))
    if not wanted or not np.any(mask):
        raise RuntimeError(f"no target semantic region for {full_id} in {path.name}")
    if region_ids.shape != cutline.shape:
        raise ValueError(f"semantic-region shape mismatch: {path}")
    return mask, cutline, metadata


def mono_target_prior_support(
    target_mask: np.ndarray,
    cutline_mask: np.ndarray,
    normal: np.ndarray,
    depth: np.ndarray,
    *,
    min_pixels: int = 64,
) -> dict[str, Any]:
    """Count image-derived target support after cutline and prior-valid masks.

    This is an observation-only QA count.  It neither removes a locked view nor
    changes the configured target-region loss; the trainer independently skips
    a view's target mono loss when the same support is below ``min_pixels``.
    """
    target = np.asarray(target_mask, dtype=np.bool_)
    cutline = np.asarray(cutline_mask, dtype=np.bool_)
    normal_array = np.asarray(normal)
    depth_array = np.asarray(depth)
    if target.shape != cutline.shape or normal_array.shape != (*target.shape, 3) or depth_array.shape != target.shape:
        raise ValueError(
            "mono target support shape mismatch: "
            f"target={target.shape}, cutline={cutline.shape}, normal={normal_array.shape}, depth={depth_array.shape}"
        )
    cutline_excluded = target & ~cutline
    normal_valid = np.isfinite(normal_array).all(axis=-1) & (np.linalg.norm(normal_array, axis=-1) > 0.5)
    depth_valid = np.isfinite(depth_array) & (depth_array > 0)
    prior_valid = cutline_excluded & normal_valid & depth_valid
    count = int(prior_valid.sum())
    return {
        "mono_target_region_pixel_count": int(target.sum()),
        "mono_target_cutline_excluded_pixel_count": int(cutline_excluded.sum()),
        "mono_target_prior_valid_pixel_count": count,
        "mono_target_min_pixels": int(min_pixels),
        "mono_target_loss_active": bool(count >= int(min_pixels)),
    }


def discover_pair_crop_boxes(pair_dir: Path) -> tuple[dict[tuple[str, str], tuple[int, int, int, int]], dict[str, str]]:
    candidates: dict[tuple[str, str], set[tuple[int, int, int, int]]] = {}
    hashes: dict[str, str] = {}
    for path in sorted(pair_dir.glob("*.npz")):
        hashes[relative(path)] = sha256_file(path)
        with np.load(path, allow_pickle=False) as archive:
            metadata = read_metadata_scalar(archive["metadata_json"])
        short = str(metadata["short"])
        row = metadata["row"]
        for suffix in ("a", "b"):
            stem = str(metadata[f"view_{suffix}"])
            box = tuple(int(value) for value in str(row[f"crop_box_{suffix}_xyxy"]).split(";"))
            if len(box) != 4:
                raise ValueError(f"invalid cached crop box in {path}")
            candidates.setdefault((short, stem), set()).add(box)
    resolved: dict[tuple[str, str], tuple[int, int, int, int]] = {}
    for key, boxes in candidates.items():
        if len(boxes) != 1:
            raise RuntimeError(f"cached pair crop drift for {key}: {sorted(boxes)}")
        resolved[key] = next(iter(boxes))
    return resolved, hashes


def validate_crop(box: tuple[int, int, int, int], width: int, height: int) -> None:
    x0, y0, x1, y1 = box
    if not (0 <= x0 < x1 <= width and 0 <= y0 < y1 <= height):
        raise ValueError(f"crop outside frame: {box} vs {width}x{height}")
    if (x1 - x0) * 3 != (y1 - y0) * 4:
        raise ValueError(f"crop is not exact 4:3: {box}")


def validate_seed_archive(path: Path, building: str, contract: dict[str, Any]) -> dict[str, Any]:
    expected = set(contract["exact_npz_keys"])
    with np.load(path, allow_pickle=False) as archive:
        if set(archive.files) != expected:
            raise ValueError(f"surface seed keys must be exactly {sorted(expected)}: {path}: {archive.files}")
        xyz = np.asarray(archive["xyz"])
        rgb = np.asarray(archive["rgb"])
        sem = np.asarray(archive["sem"])
        metadata = read_metadata_scalar(archive["metadata_json"])
    if xyz.dtype != np.float32 or xyz.ndim != 2 or xyz.shape[1] != 3 or len(xyz) == 0:
        raise ValueError(f"invalid seed xyz: {path}: {xyz.dtype}/{xyz.shape}")
    if rgb.dtype != np.float32 or rgb.shape != xyz.shape:
        raise ValueError(f"invalid seed rgb: {path}: {rgb.dtype}/{rgb.shape}")
    if sem.dtype != np.int64 or sem.shape != (len(xyz),) or not np.all(sem == 1):
        raise ValueError(f"invalid seed sem: {path}: {sem.dtype}/{sem.shape}")
    if not np.isfinite(xyz).all() or not np.isfinite(rgb).all():
        raise ValueError(f"non-finite surface seed: {path}")
    required = {
        "schema": contract["schema"],
        "seed_type": "surface",
        "coordinate_frame": contract["coordinate_frame"],
        "crs": "EPSG:25832",
        "gt_used_for_seed_generation": False,
        "lod2_used_for_seed_generation": False,
        "als_used_for_seed_generation": False,
    }
    for key, expected_value in required.items():
        if metadata.get(key) != expected_value:
            raise ValueError(f"seed metadata {key} drift in {path}: {metadata.get(key)!r}")
    if str(metadata.get("building_id", "")).removeprefix("DEBY_LOD2_") != building:
        raise ValueError(f"surface seed building mismatch: {path}")
    spacing = metadata.get("grid_spacing_m", metadata.get("grid_m"))
    if not math.isclose(float(spacing), float(contract["grid_spacing_m"]), abs_tol=1e-9):
        raise ValueError(f"surface seed grid spacing drift: {path}: {spacing}")
    if not isinstance(metadata.get("lineage"), dict):
        raise ValueError(f"surface seed lineage must be an object: {path}")
    return {
        "path": relative(path), "sha256": sha256_file(path), "count": int(len(xyz)),
        "xyz": xyz, "rgb": rgb, "sem": sem, "metadata": metadata,
    }


BC_LINEAGE_FIELDS = [
    "sequence", "building_id", "source_index", "source_x_local_m", "source_y_local_m",
    "source_z_local_m", "cell_ix", "cell_iy", "graph_distance_cells",
    "target_x_local_m", "target_y_local_m", "target_z_local_m",
]


def build_boundary_graph_propagation(
    *,
    p0: dict[str, Any],
    auxiliary: dict[str, Any] | None,
    footprint: Polygon | MultiPolygon,
    world_offset: Sequence[float],
    destination: Path,
    lineage_path: Path,
    building: str,
    contract: dict[str, Any],
    propagation: dict[str, Any],
) -> dict[str, Any] | None:
    """Materialize the locked offline boundary-frontier propagation surrogate.

    Eligible B-c points only activate and own a deterministic 4-neighbour graph
    expansion.  Every generated Z comes from the FM-anchored P0 plane; boundary
    Z is never copied or fitted.  A half-cell-shifted lattice makes the inserted
    material distinct from the canonical P0 grid while keeping the same 0.5 m
    spatial scale and target-footprint scope.
    """

    if auxiliary is None or int(auxiliary["count"]) == 0:
        return None
    if propagation.get("name") != "offline_boundary_gated_plane_consistent_graph_propagation_surrogate":
        raise ValueError("unexpected B-c propagation lock")
    grid = float(propagation["grid_spacing_m"])
    shift = np.asarray(propagation["lattice_shift_xy_m"], dtype=np.float64)
    if not math.isclose(grid, float(contract["grid_spacing_m"]), abs_tol=1e-12):
        raise ValueError("B-c propagation grid must equal the surface-seed grid")
    if shift.shape != (2,) or not np.allclose(shift, [grid / 2.0, grid / 2.0], atol=1e-12):
        raise ValueError("B-c propagation requires the locked half-cell XY shift")
    if int(propagation["connectivity"]) != 4:
        raise ValueError("B-c propagation connectivity must be four")

    offset = np.asarray(world_offset, dtype=np.float64)
    if offset.shape != (3,) or not np.isfinite(offset).all():
        raise ValueError("world_offset must be a finite XYZ vector")
    minx, miny, maxx, maxy = footprint.bounds
    ix0 = math.floor((minx - shift[0]) / grid)
    ix1 = math.ceil((maxx - shift[0]) / grid)
    iy0 = math.floor((miny - shift[1]) / grid)
    iy1 = math.ceil((maxy - shift[1]) / grid)
    representatives: dict[tuple[int, int], tuple[float, float]] = {}
    for ix in range(ix0, ix1):
        for iy in range(iy0, iy1):
            cell = box(
                ix * grid + shift[0], iy * grid + shift[1],
                (ix + 1) * grid + shift[0], (iy + 1) * grid + shift[1],
            )
            overlap = footprint.intersection(cell)
            if overlap.is_empty or float(overlap.area) <= 1e-10:
                continue
            point = overlap.representative_point()
            representatives[(ix, iy)] = (float(point.x), float(point.y))
    if not representatives:
        raise RuntimeError(f"B-c propagation footprint lattice is empty for {building}")

    source_world = np.asarray(auxiliary["xyz"], dtype=np.float64)[:, :2] + offset[:2]
    source_cells: list[tuple[int, int]] = []
    ordered_cells = sorted(representatives)
    for xy in source_world:
        candidate = (
            math.floor((float(xy[0]) - shift[0]) / grid),
            math.floor((float(xy[1]) - shift[1]) / grid),
        )
        if candidate not in representatives:
            candidate = min(
                ordered_cells,
                key=lambda cell: (
                    (representatives[cell][0] - float(xy[0])) ** 2
                    + (representatives[cell][1] - float(xy[1])) ** 2,
                    cell,
                ),
            )
        source_cells.append(candidate)

    # Heap ordering supplies the locked tie break: distance, then source index,
    # then cell coordinate.  Re-visits replace ownership only with a smaller
    # (distance, source) pair.
    ownership: dict[tuple[int, int], tuple[int, int]] = {}
    frontier: list[tuple[int, int, int, int]] = []
    for source_index, (ix, iy) in enumerate(source_cells):
        heapq.heappush(frontier, (0, source_index, ix, iy))
    neighbours = ((-1, 0), (0, -1), (0, 1), (1, 0))
    while frontier:
        distance, source_index, ix, iy = heapq.heappop(frontier)
        cell = (ix, iy)
        candidate_owner = (distance, source_index)
        if cell not in representatives:
            continue
        if cell in ownership and ownership[cell] <= candidate_owner:
            continue
        ownership[cell] = candidate_owner
        for dx, dy in neighbours:
            neighbour = (ix + dx, iy + dy)
            if neighbour in representatives:
                heapq.heappush(
                    frontier, (distance + 1, source_index, neighbour[0], neighbour[1])
                )
    if not ownership:
        raise RuntimeError(f"B-c propagation reached no target cell for {building}")

    plane = p0["metadata"]
    a = float(plane["plane_ax_local"])
    b = float(plane["plane_by_local"])
    c = float(plane["plane_c_local"])
    existing_xyz = np.concatenate([p0["xyz"], auxiliary["xyz"]], axis=0).astype(np.float64)
    existing_keys = {
        tuple(np.rint(row * 1_000_000.0).astype(np.int64).tolist()) for row in existing_xyz
    }
    generated_xyz: list[list[float]] = []
    lineage_rows: list[dict[str, Any]] = []
    for cell in sorted(ownership):
        distance, source_index = ownership[cell]
        world_x, world_y = representatives[cell]
        local_x, local_y = world_x - offset[0], world_y - offset[1]
        local_z = a * local_x + b * local_y + c
        xyz = np.asarray([local_x, local_y, local_z], dtype=np.float64)
        key = tuple(np.rint(xyz * 1_000_000.0).astype(np.int64).tolist())
        if key in existing_keys:
            continue
        existing_keys.add(key)
        generated_xyz.append(xyz.tolist())
        source = np.asarray(auxiliary["xyz"][source_index], dtype=np.float64)
        lineage_rows.append({
            "sequence": len(lineage_rows) + 1,
            "building_id": f"DEBY_LOD2_{building}",
            "source_index": source_index,
            "source_x_local_m": float(source[0]),
            "source_y_local_m": float(source[1]),
            "source_z_local_m": float(source[2]),
            "cell_ix": cell[0], "cell_iy": cell[1],
            "graph_distance_cells": distance,
            "target_x_local_m": float(local_x),
            "target_y_local_m": float(local_y),
            "target_z_local_m": float(local_z),
        })
    if not generated_xyz:
        raise RuntimeError(f"B-c propagation produced only duplicate P0/source rows for {building}")
    atomic_csv(lineage_path, lineage_rows, BC_LINEAGE_FIELDS)

    xyz = np.ascontiguousarray(np.asarray(generated_xyz, dtype=np.float32))
    rgb_mean = np.asarray(p0["rgb"], dtype=np.float64).mean(axis=0).astype(np.float32)
    rgb = np.repeat(rgb_mean[None, :], len(xyz), axis=0).astype(np.float32, copy=False)
    sem = np.ones(len(xyz), dtype=np.int64)
    metadata = {
        "schema": contract["schema"],
        "seed_type": "surface",
        "coordinate_frame": contract["coordinate_frame"],
        "crs": "EPSG:25832",
        "building_id": f"DEBY_LOD2_{building}",
        "grid_spacing_m": grid,
        "initial_opacity": float(contract["initial_opacity"]),
        "gt_used_for_seed_generation": False,
        "lod2_used_for_seed_generation": False,
        "als_used_for_seed_generation": False,
        "height_anchor_source": "FM-anchored canonical P0 plane only",
        "lineage": {
            "kind": propagation["name"],
            "claim_boundary": propagation["claim_boundary"],
            "activation_source_path": auxiliary["path"],
            "activation_source_sha256": auxiliary["sha256"],
            "activation_source_count": int(auxiliary["count"]),
            "source_role": propagation["source_role"],
            "height_rule": propagation["height_rule"],
            "spatial_scope": propagation["spatial_scope"],
            "lattice_shift_xy_m": shift.tolist(),
            "connectivity": int(propagation["connectivity"]),
            "owner_rule": propagation["owner_rule"],
            "eligible_cell_count": len(representatives),
            "reached_cell_count": len(ownership),
            "unreached_cell_count": len(representatives) - len(ownership),
            "generated_nonduplicate_count": len(xyz),
            "lineage_csv": relative(lineage_path),
            "lineage_csv_sha256": sha256_file(lineage_path),
        },
    }
    atomic_npz(destination, {
        "xyz": xyz, "rgb": rgb, "sem": sem,
        "metadata_json": np.asarray(json.dumps(metadata, sort_keys=True, separators=(",", ":"))),
    })
    validated = validate_seed_archive(destination, building, contract)
    validated["role"] = "bc_graph_propagation"
    validated["lineage_csv"] = relative(lineage_path)
    validated["lineage_csv_sha256"] = sha256_file(lineage_path)
    validated["eligible_cell_count"] = len(representatives)
    validated["reached_cell_count"] = len(ownership)
    validated["unreached_cell_count"] = len(representatives) - len(ownership)
    return validated


def merge_surface_seeds(
    p0: dict[str, Any],
    auxiliary: dict[str, Any] | None,
    propagation: dict[str, Any] | None,
    destination: Path,
    building: str,
    contract: dict[str, Any],
) -> dict[str, Any]:
    sources = [p0] + ([auxiliary] if auxiliary is not None else []) + (
        [propagation] if propagation is not None else []
    )
    xyz = np.concatenate([row["xyz"] for row in sources], axis=0).astype(np.float32, copy=False)
    rgb = np.concatenate([row["rgb"] for row in sources], axis=0).astype(np.float32, copy=False)
    sem = np.concatenate([row["sem"] for row in sources], axis=0).astype(np.int64, copy=False)
    quantized = np.rint(xyz.astype(np.float64) * 1_000_000.0).astype(np.int64)
    seen: set[tuple[int, int, int]] = set()
    keep: list[int] = []
    for index, row in enumerate(quantized):
        key = tuple(int(value) for value in row)
        if key not in seen:
            seen.add(key)
            keep.append(index)
    keep_array = np.asarray(keep, dtype=np.int64)
    source_rows = [{
        "role": row.get(
            "role", "p0_surface" if index == 0 else "bc_aux"
        ),
        "path": row["path"], "sha256": row["sha256"], "count": row["count"],
    } for index, row in enumerate(sources)]
    metadata = {
        "schema": contract["schema"],
        "seed_type": "surface",
        "coordinate_frame": contract["coordinate_frame"],
        "crs": "EPSG:25832",
        "building_id": f"DEBY_LOD2_{building}",
        "grid_spacing_m": float(contract["grid_spacing_m"]),
        "initial_opacity": float(contract["initial_opacity"]),
        "gt_used_for_seed_generation": False,
        "lod2_used_for_seed_generation": False,
        "als_used_for_seed_generation": False,
        "lineage": {
            "operation": "deterministic_surface_seed_union",
            "sources": source_rows,
            "merge_order": list(contract["merge_order"]),
            "duplicate_rule": contract["merge_duplicate_rule"],
            "input_count": int(len(xyz)),
            "duplicate_count": int(len(xyz) - len(keep_array)),
            "output_count": int(len(keep_array)),
        },
    }
    atomic_npz(destination, {
        "xyz": xyz[keep_array], "rgb": rgb[keep_array], "sem": sem[keep_array],
        "metadata_json": np.asarray(json.dumps(metadata, sort_keys=True, separators=(",", ":"))),
    })
    validated = validate_seed_archive(destination, building, contract)
    return {key: value for key, value in validated.items() if key not in {"xyz", "rgb", "sem", "metadata"}} | {
        "source_count": len(sources), "duplicate_count": metadata["lineage"]["duplicate_count"],
        "sources": source_rows,
    }


def load_footprints(path: Path, buildings: Iterable[str]) -> dict[str, Polygon | MultiPolygon]:
    wanted = {f"DEBY_LOD2_{value}" for value in buildings}
    pieces: dict[str, list[Any]] = {value: [] for value in wanted}
    payload = json.loads(path.read_text(encoding="utf-8"))
    crs = str(((payload.get("crs") or {}).get("properties") or {}).get("name", ""))
    if "25832" not in crs:
        raise ValueError(f"footprint CRS is not EPSG:25832: {crs!r}")
    for feature in payload["features"]:
        building_id = str((feature.get("properties") or {}).get("building_id", ""))
        if building_id in pieces:
            geometry = make_valid(shape(feature["geometry"]))
            if not geometry.is_empty:
                pieces[building_id].append(geometry)
    result: dict[str, Polygon | MultiPolygon] = {}
    for building_id in sorted(wanted):
        geometry = make_valid(unary_union(pieces[building_id]))
        if geometry.is_empty or not isinstance(geometry, (Polygon, MultiPolygon)):
            raise RuntimeError(f"missing footprint: {building_id}")
        result[building_id.removeprefix("DEBY_LOD2_")] = geometry
    return result


def footprint_pca_axis(geometry: Polygon | MultiPolygon, world_offset: Sequence[float]) -> tuple[list[float], list[float]]:
    polygons = [geometry] if isinstance(geometry, Polygon) else list(geometry.geoms)
    coordinates = np.concatenate([np.asarray(polygon.exterior.coords[:-1], dtype=np.float64)[:, :2] for polygon in polygons])
    centered = coordinates - coordinates.mean(axis=0, keepdims=True)
    covariance = centered.T @ centered / max(1, len(centered))
    values, vectors = np.linalg.eigh(covariance)
    axis = vectors[:, int(np.argmax(values))]
    if axis[0] < 0 or (abs(axis[0]) <= 1e-12 and axis[1] < 0):
        axis = -axis
    axis = axis / np.linalg.norm(axis)
    centroid = np.asarray(geometry.centroid.coords[0], dtype=np.float64) - np.asarray(world_offset[:2], dtype=np.float64)
    return axis.tolist(), centroid.tolist()


def build_arm(lock: dict[str, Any], arm: str) -> dict[str, Any]:
    arms = lock["training"]["arms"]
    raw = copy.deepcopy(arms[arm])
    parent = raw.pop("inherits", None)
    if parent:
        inherited = build_arm(lock, str(parent))
        inherited.update(raw)
        raw = inherited
    return raw


def perturb_slug(value: float, *, tilt: bool = False) -> str:
    sign = "p" if value > 0 else "m"
    magnitude = abs(float(value))
    if tilt:
        token = f"{int(round(magnitude)):02d}"
    elif math.isclose(magnitude, 0.5):
        token = "0p5"
    else:
        token = str(int(round(magnitude)))
    return f"{sign}{token}"


def base_job_specs(lock: dict[str, Any]) -> list[dict[str, Any]]:
    jobs: list[dict[str, Any]] = []
    for building in lock["targets"]:
        for arm in ("a0", "a1", "a2"):
            for replicate, random_seed in lock["training"]["replicates"].items():
                jobs.append({
                    "job_id": f"gs_e5_C001_s3ap_b{building}_{arm}_{replicate}",
                    "job_class": "base", "building_id": building, "arm": arm,
                    "replicate": replicate, "random_seed": int(random_seed),
                    "height_delta_m": 0.0, "tilt_deg": 0.0,
                })
    first_rep, first_seed = next(iter(lock["training"]["replicates"].items()))
    for building in lock["targets"]:
        for delta in lock["training"]["height_perturbation_m"]:
            jobs.append({
                "job_id": f"gs_e5_C001_s3ap_b{building}_a1_dz_{perturb_slug(float(delta))}_{first_rep}",
                "job_class": "height", "building_id": building, "arm": "a1",
                "replicate": first_rep, "random_seed": int(first_seed),
                "height_delta_m": float(delta), "tilt_deg": 0.0,
            })
    if len(jobs) != 42 or len({job["job_id"] for job in jobs}) != 42:
        raise RuntimeError(f"base Phase-2 job inventory must contain 42 unique rows, got {len(jobs)}")
    return jobs


def tilt_job_specs(lock: dict[str, Any], footprints: dict[str, Any], world_offset: Sequence[float]) -> list[dict[str, Any]]:
    replicate, random_seed = next(iter(lock["training"]["replicates"].items()))
    jobs: list[dict[str, Any]] = []
    for building in lock["targets"]:
        axis, pivot = footprint_pca_axis(footprints[building], world_offset)
        for tilt in lock["training"]["tilt_perturbation_deg"]:
            jobs.append({
                "job_id": f"gs_e5_C001_s3ap_b{building}_a1_tilt_{perturb_slug(float(tilt), tilt=True)}_{replicate}",
                "job_class": "tilt", "building_id": building, "arm": "a1",
                "replicate": replicate, "random_seed": int(random_seed),
                "height_delta_m": 0.0, "tilt_deg": float(tilt),
                "tilt_axis_xy": axis, "tilt_pivot_xy": pivot,
            })
    if len(jobs) != 18 or len({job["job_id"] for job in jobs}) != 18:
        raise RuntimeError(f"tilt inventory must contain 18 unique rows, got {len(jobs)}")
    return jobs


def load_world_offset(lock: dict[str, Any]) -> list[float]:
    manifest = json.loads(resolve(lock["sources"]["world_offset_manifest"]).read_text(encoding="utf-8"))
    offset = [float(value) for value in manifest["world_offset"]]
    if len(offset) != 3 or not np.isfinite(offset).all():
        raise ValueError(f"invalid world offset: {offset}")
    return offset


def validate_locked_views(lock: dict[str, Any]) -> dict[str, Any]:
    path = resolve(lock["sources"]["locked_visible_manifest"])
    manifest = json.loads(path.read_text(encoding="utf-8"))
    for building, target in lock["targets"].items():
        source = [row["stem"] for row in manifest["locked_visible_views"][building]]
        if source != target["visible_views"]:
            raise RuntimeError(f"visible-view order drift for {building}: {source} != {target['visible_views']}")
    return {"path": relative(path), "sha256": sha256_file(path)}


def stage_building(
    lock: dict[str, Any],
    building: str,
    cameras: dict[int, Camera],
    images: dict[int, Image],
    image_by_stem: dict[str, Image],
    source_points: np.ndarray,
    pair_boxes: dict[tuple[str, str], tuple[int, int, int, int]],
    footprint: Polygon | MultiPolygon,
    world_offset: Sequence[float],
    progress: list[dict[str, Any]],
    progress_path: Path,
) -> dict[str, Any]:
    sources = lock["sources"]
    output_root = resolve(lock["outputs"]["prepared_root"]) / f"DEBY_LOD2_{building}"
    image_root = output_root / "images"
    semantic_root = output_root / "semantic"
    normal_root = output_root / "mono_normal"
    depth_root = output_root / "mono_depth"
    region_root = output_root / "semantic_regions"
    sparse_root = output_root / "sparse/0"
    for path in (image_root, semantic_root, normal_root, depth_root, region_root, sparse_root):
        path.mkdir(parents=True, exist_ok=True)

    output_cameras: dict[int, Camera] = {}
    output_images: dict[int, Image] = {}
    projection_frames: list[tuple[Image, Camera, tuple[int, int, int, int]]] = []
    view_rows: list[dict[str, Any]] = []
    data_root = resolve(sources["data_root"])
    crop_rule = lock["crop_rule"]

    for sequence, stem in enumerate(lock["targets"][building]["visible_views"], 1):
        source_image = image_by_stem.get(stem)
        if source_image is None:
            raise FileNotFoundError(f"locked view is absent from source COLMAP model: {stem}")
        source_camera = cameras[source_image.camera_id]
        source_path = data_root / "images" / source_image.name
        region_path = resolve(sources["semantic_region_root"]) / f"{stem}.npz"
        normal_path = resolve(sources["mono_normal_root"]) / f"{stem}.npy"
        depth_path = resolve(sources["mono_depth_root"]) / f"{stem}.npy"
        semantic_path = resolve(sources["semantic_png_root"]) / f"{stem}.png"
        for path in (source_path, region_path, normal_path, depth_path, semantic_path):
            if not path.is_file():
                raise FileNotFoundError(path)
        with PILImage.open(source_path) as source_pil:
            source_rgb = np.asarray(source_pil.convert("RGB"))
        height, width = source_rgb.shape[:2]
        if (width, height) != (int(source_camera.width), int(source_camera.height)):
            raise RuntimeError(f"source image/camera dimension mismatch for {stem}")
        target_mask, cutline, region_metadata = load_target_mask(region_path, building)
        if target_mask.shape != (height, width):
            raise RuntimeError(f"semantic-region/image shape mismatch for {stem}")
        cached = pair_boxes.get((building, stem))
        if cached is not None:
            box = cached
            box_source = "existing_pair_crop"
        else:
            box = crop_box_4x3(
                target_mask, width, height,
                margin_px=int(crop_rule["margin_px"]),
                minimum_width_px=int(crop_rule["minimum_width_px"]),
                width_multiple_px=int(crop_rule["width_multiple_px"]),
            )
            box_source = "deterministic_target_mask_fallback"
        validate_crop(box, width, height)
        x0, y0, x1, y1 = box
        output_name = f"{stem}.png"
        image_crop = np.ascontiguousarray(source_rgb[y0:y1, x0:x1])
        output_image_path = image_root / output_name
        atomic_png(output_image_path, image_crop)
        with PILImage.open(output_image_path) as check_image:
            if not np.array_equal(np.asarray(check_image.convert("RGB")), image_crop):
                raise RuntimeError(f"native pixel crop equality failed for {stem}")

        semantic = np.asarray(PILImage.open(semantic_path))
        if semantic.shape[:2] != (height, width):
            raise RuntimeError(f"semantic/image shape mismatch for {stem}")
        semantic_crop = np.ascontiguousarray(semantic[y0:y1, x0:x1])
        output_semantic_path = semantic_root / f"{stem}.png"
        atomic_png(output_semantic_path, semantic_crop)
        if not np.array_equal(np.asarray(PILImage.open(output_semantic_path)), semantic_crop):
            raise RuntimeError(f"semantic crop equality failed for {stem}")

        normal = np.load(normal_path, allow_pickle=False)
        depth = np.load(depth_path, allow_pickle=False)
        if normal.shape != (height, width, 3) or depth.shape != (height, width):
            raise RuntimeError(f"mono-prior/image shape mismatch for {stem}: {normal.shape}/{depth.shape}")
        normal_crop = np.ascontiguousarray(normal[y0:y1, x0:x1])
        depth_crop = np.ascontiguousarray(depth[y0:y1, x0:x1])
        target_crop = np.ascontiguousarray(target_mask[y0:y1, x0:x1]).astype(np.bool_, copy=False)
        cutline_crop = np.ascontiguousarray(cutline[y0:y1, x0:x1]).astype(np.bool_, copy=False)
        mono_support = mono_target_prior_support(
            target_crop, cutline_crop, normal_crop, depth_crop,
            min_pixels=int(lock["training"]["arms"]["a1"]["mono_target_min_pixels"]),
        )
        output_normal_path = normal_root / f"{stem}.npy"
        output_depth_path = depth_root / f"{stem}.npy"
        atomic_npy(output_normal_path, normal_crop)
        atomic_npy(output_depth_path, depth_crop)
        if not np.array_equal(np.load(output_normal_path, allow_pickle=False), normal_crop):
            raise RuntimeError(f"normal crop equality failed for {stem}")
        if not np.array_equal(np.load(output_depth_path, allow_pickle=False), depth_crop):
            raise RuntimeError(f"mono-depth crop equality failed for {stem}")

        region_ids = np.load(region_path, allow_pickle=False)["region_ids"]
        region_crop = np.ascontiguousarray(region_ids[y0:y1, x0:x1]).astype(np.int32, copy=False)
        crop_lineage = {
            "source_path": relative(region_path), "source_sha256": sha256_file(region_path),
            "crop_box_xyxy": list(box), "source_shape_hw": [height, width],
            "output_shape_hw": [y1 - y0, x1 - x0], "resize": False,
            "cutline_half_width_px_preserved": int(crop_rule["semantic_cutline_half_width_px"]),
            "gt_used": False, "lod2_used": False, "als_used": False,
        }
        region_metadata = copy.deepcopy(region_metadata)
        region_metadata["phase2_crop_lineage"] = crop_lineage
        output_region_path = region_root / f"{stem}.npz"
        atomic_npz(output_region_path, {
            "region_ids": region_crop,
            "cutline_mask": cutline_crop,
            "metadata_json": np.asarray(json.dumps(region_metadata, sort_keys=True, separators=(",", ":"))),
        })
        with np.load(output_region_path, allow_pickle=False) as check_region:
            if set(check_region.files) != {"region_ids", "cutline_mask", "metadata_json"}:
                raise RuntimeError(f"cropped region key drift for {stem}")
            if not np.array_equal(check_region["region_ids"], region_crop) or not np.array_equal(check_region["cutline_mask"], cutline_crop):
                raise RuntimeError(f"semantic-region crop equality failed for {stem}")

        camera_id = sequence
        output_camera = adjust_camera(source_camera, camera_id, box)
        output_image = Image(
            source_image.id, source_image.qvec.copy(), source_image.tvec.copy(), camera_id, output_name
        )
        output_cameras[camera_id] = output_camera
        output_images[source_image.id] = output_image
        projection_frames.append((source_image, source_camera, box))
        view_row = {
            "building_id": f"DEBY_LOD2_{building}", "view_stem": stem,
            "source_image_name": source_image.name, "output_image_name": output_name,
            "crop_box_xyxy": list(box), "crop_source": box_source,
            "source_size_wh": [width, height], "output_size_wh": [x1 - x0, y1 - y0],
            "resize": False, "source_camera_id": int(source_camera.id), "output_camera_id": camera_id,
            "K_source": source_camera.K().tolist(), "K_crop": output_camera.K().tolist(),
            "R_w2c": source_image.R().tolist(), "t_w2c": source_image.tvec.tolist(),
            "source_sha256": {
                "image": sha256_file(source_path), "semantic": sha256_file(semantic_path),
                "normal": sha256_file(normal_path), "mono_depth": sha256_file(depth_path),
                "semantic_region": sha256_file(region_path),
            },
            "output_sha256": {
                "image": sha256_file(output_image_path), "semantic": sha256_file(output_semantic_path),
                "normal": sha256_file(output_normal_path), "mono_depth": sha256_file(output_depth_path),
                "semantic_region": sha256_file(output_region_path),
            },
            **mono_support,
            "gt_used": False, "lod2_used": False, "als_used": False,
        }
        view_rows.append(view_row)
        progress.append({
            "sequence": len(progress) + 1, "stage": "crop", "building_id": building,
            "view_stem": stem, "status": "complete", "detail": box_source, "updated_utc": utc_now(),
        })
        atomic_csv(progress_path, progress, PROGRESS_FIELDS)

    write_cameras_bin(sparse_root / "cameras.bin", output_cameras)
    write_images_bin(sparse_root / "images.bin", output_images)
    subset, per_view_counts = crop_visible_sfm_subset(source_points, projection_frames)
    if len(subset) == 0:
        raise RuntimeError(f"crop-projected observed SfM subset is empty for {building}")
    write_points3d_bin(sparse_root / "points3D.bin", subset)

    p0_path = resolve(sources["p0_surface_seed_pattern"].format(building=building))
    aux_path = resolve(sources["bc_aux_seed_pattern"].format(building=building))
    contract = lock["surface_seed_contract"]
    p0 = validate_seed_archive(p0_path, building, contract)
    p0["role"] = "p0_surface"
    auxiliary = validate_seed_archive(aux_path, building, contract) if aux_path.is_file() else None
    if auxiliary is not None:
        auxiliary["role"] = "bc_aux"
    propagation_path = output_root / "seeds" / f"DEBY_LOD2_{building}_bc_graph_propagation_seed.npz"
    propagation_lineage_path = output_root / "seeds" / f"DEBY_LOD2_{building}_bc_graph_propagation_lineage.csv"
    propagation = build_boundary_graph_propagation(
        p0=p0,
        auxiliary=auxiliary,
        footprint=footprint,
        world_offset=world_offset,
        destination=propagation_path,
        lineage_path=propagation_lineage_path,
        building=building,
        contract=contract,
        propagation=lock["boundary_propagation"],
    )
    merged_path = output_root / "seeds" / f"DEBY_LOD2_{building}_a1a2_surface_seed.npz"
    merged = merge_surface_seeds(p0, auxiliary, propagation, merged_path, building, contract)

    camera_manifest_path = output_root / "camera_crop_manifest.json"
    camera_manifest = {
        "schema": "jointbuildgs.s3ap.phase2.camera_crops.v1", "building_id": f"DEBY_LOD2_{building}",
        "crs": "EPSG:25832", "crop_rule": lock["crop_rule"], "views": view_rows,
        "source_sparse_sha256": {
            name: sha256_file(resolve(sources["sparse_root"]) / name)
            for name in ("cameras.bin", "images.bin", "points3D.bin")
        },
        "output_sparse_sha256": {
            name: sha256_file(sparse_root / name) for name in ("cameras.bin", "images.bin", "points3D.bin")
        },
        "observed_sfm_source_count": int(len(source_points)),
        "observed_sfm_subset_count": int(len(subset)),
        "observed_sfm_projected_count_by_view": per_view_counts,
        "sfm_subset_rule": lock["crop_rule"]["sfm_subset_rule"],
        "gt_used": False, "lod2_used": False, "als_used": False,
    }
    atomic_json(camera_manifest_path, camera_manifest)
    min_pixels = int(lock["training"]["arms"]["a1"]["mono_target_min_pixels"])
    active_views = [row["view_stem"] for row in view_rows if row["mono_target_loss_active"]]
    skipped_views = [row["view_stem"] for row in view_rows if not row["mono_target_loss_active"]]
    mono_target_support = {
        "schema": "jointbuildgs.s3ap.phase2.mono_target_support.v1",
        "role": "observation_only_not_gate",
        "pixel_rule": (
            "target_region & ~semantic_cutline & finite(normal_xyz) & "
            "norm(normal_xyz)>0.5 & finite(mono_depth) & mono_depth>0"
        ),
        "mono_target_min_pixels": min_pixels,
        "ordered_view_counts": [
            {
                "view_stem": row["view_stem"],
                "mono_target_prior_valid_pixel_count": row["mono_target_prior_valid_pixel_count"],
                "mono_target_loss_active": row["mono_target_loss_active"],
            }
            for row in view_rows
        ],
        "active_view_count": len(active_views),
        "active_views": active_views,
        "below_min_view_count": len(skipped_views),
        "below_min_views": skipped_views,
        "locked_views_removed": False,
    }
    data_manifest_path = output_root / "data_manifest.json"
    result = {
        "schema": "jointbuildgs.s3ap.phase2.prepared_data.v1",
        "building_id": f"DEBY_LOD2_{building}", "data_root": relative(output_root),
        "visible_view_count": len(view_rows), "views": view_rows,
        "mono_target_support": mono_target_support,
        "camera_manifest": relative(camera_manifest_path), "camera_manifest_sha256": sha256_file(camera_manifest_path),
        "observed_sfm_subset_count": int(len(subset)),
        "p0_surface_seed": {key: p0[key] for key in ("path", "sha256", "count")},
        "bc_aux_surface_seed": None if auxiliary is None else {key: auxiliary[key] for key in ("path", "sha256", "count")},
        "bc_graph_propagation": None if propagation is None else {
            key: propagation[key] for key in (
                "path", "sha256", "count", "lineage_csv", "lineage_csv_sha256",
                "eligible_cell_count", "reached_cell_count", "unreached_cell_count",
            )
        },
        "boundary_propagation_contract": lock["boundary_propagation"],
        "a1a2_surface_seed": merged,
        "gt_used": False, "lod2_used": False, "als_used": False,
        "created_utc": utc_now(),
    }
    atomic_json(data_manifest_path, result)
    result["data_manifest"] = relative(data_manifest_path)
    result["data_manifest_sha256"] = sha256_file(data_manifest_path)
    progress.append({
        "sequence": len(progress) + 1, "stage": "building", "building_id": building,
        "view_stem": "", "status": "complete", "detail": f"sfm_subset={len(subset)}",
        "updated_utc": utc_now(),
    })
    atomic_csv(progress_path, progress, PROGRESS_FIELDS)
    return result


def make_training_config(
    lock: dict[str, Any],
    job: dict[str, Any],
    prepared: dict[str, Any],
    world_offset: Sequence[float],
) -> dict[str, Any]:
    arm = job["arm"]
    config = copy.deepcopy(lock["training"]["common"])
    config.update(build_arm(lock, arm))
    output_data_root = resolve(prepared["data_root"])
    if arm == "a0":
        seed_path = resolve(prepared["p0_surface_seed"]["path"])
    else:
        seed_path = resolve(prepared["a1a2_surface_seed"]["path"])
    output_names = [f"{stem}.png" for stem in lock["targets"][job["building_id"]]["visible_views"]]
    output_dir = resolve(lock["outputs"]["training_root"]) / job["job_id"]
    config.update({
        "seed": int(job["random_seed"]), "device": "cuda", "data_root": container_path(output_data_root, lock),
        "out_dir": container_path(output_dir, lock), "max_iter": int(lock["training"]["iterations"]),
        "downscale": float(lock["training"]["downscale"]),
        "surface_seed_npz": container_path(seed_path, lock),
        "surface_seed_initial_opacity": float(lock["surface_seed_contract"]["initial_opacity"]),
        "surface_seed_height_delta_m": float(job.get("height_delta_m", 0.0)),
        "surface_seed_tilt_deg": float(job.get("tilt_deg", 0.0)),
        "surface_seed_tilt_axis_xy": list(job.get("tilt_axis_xy", [1.0, 0.0])),
        "surface_seed_tilt_pivot_xy": list(job.get("tilt_pivot_xy", [0.0, 0.0])),
        "visible_views": output_names, "train_views": output_names, "eval_views": [],
        "mono_target_buildings": [job["building_id"]],
        "semantic_pi_target_buildings": [job["building_id"]],
        "world_offset": [float(value) for value in world_offset],
        "phase2_input_contract": {
            "observed_sfm": True, "external_surface_seed": True, "mvs_init": False,
            "gt_used": False, "lod2_used": False, "als_used": False,
            "job_class": job["job_class"], "building_id": job["building_id"],
        },
    })
    config.pop("description", None)
    if arm in {"a1", "a2"}:
        config.update({
            "normal_dir": container_path(output_data_root / "mono_normal", lock),
            "mono_depth_dir": container_path(output_data_root / "mono_depth", lock),
            "semantic_region_cache": container_path(output_data_root / "semantic_regions", lock),
        })
    else:
        for key in ("normal_dir", "mono_depth_dir", "semantic_region_cache"):
            config.pop(key, None)
    if "init_pointcloud" in config or "init_pointcloud_mode" in config:
        raise RuntimeError("MVS/init_pointcloud keys are forbidden in Phase-2 generated configs")
    validate_generated_config(config, arm, job["building_id"])
    return config


def validate_generated_config(config: dict[str, Any], arm: str, building: str) -> None:
    """Fail closed on arm wiring instead of relying on trainer defaults."""
    if int(config.get("max_iter", -1)) != 30000:
        raise RuntimeError("generated config must lock max_iter=30000")
    if config.get("visible_views") != config.get("train_views") or config.get("eval_views") != []:
        raise RuntimeError("all locked visible views must be explicit train views with eval_views=[]")
    if config.get("init_pointcloud") or config.get("init_pointcloud_mode"):
        raise RuntimeError("generated config contains forbidden MVS initialization")
    if arm == "a0":
        zero_terms = (
            "w_depth", "w_normal", "w_mono_depth", "w_nc", "w_sem", "w_semdepth_smooth",
            "w_semdepth_plane", "w_boundary_normal", "w_structure", "w_mutual", "w_mvc", "w_distort",
            "loss_grad_audit_every", "semantic_geometry_audit_every",
        )
        drift = {key: config.get(key) for key in zero_terms if float(config.get(key, float("nan"))) != 0.0}
        if drift:
            raise RuntimeError(f"A0 is not photo-only: {drift}")
        if config.get("load_depth") is not False or config.get("load_normal") is not False or config.get("load_semantic") is not False:
            raise RuntimeError("A0 data-prior loading must be disabled")
        if any(key in config for key in ("normal_dir", "mono_depth_dir", "semantic_region_cache")):
            raise RuntimeError("A0 must not carry mono/semantic cache paths")
        return
    required = {
        "mono_normal_loss": "target_region", "mono_depth_loss": "ssi",
        "mono_target_buildings": [building], "mono_target_min_pixels": 64,
        "load_depth": False, "load_normal": True, "load_semantic": True,
        "w_normal": 0.05, "w_mono_depth": 0.05, "w_nc": 0.05, "w_sem": 0.1,
        "sem_detach_geometry": False, "w_semdepth_smooth": 0.125,
        "w_semdepth_plane": 0.125, "w_boundary_normal": 0.01,
        "semantic_geometry_warmup": 1500, "loss_grad_audit_every": 500,
        "semantic_geometry_audit_every": 5000, "structure_grouping": "g2",
        "w_structure": 1.0, "w_structure_na": 0.08, "w_structure_cp": 0.01,
        "structure_warmup": 15000,
    }
    mismatch = {key: (config.get(key), expected) for key, expected in required.items() if config.get(key) != expected}
    if mismatch:
        raise RuntimeError(f"{arm.upper()} target-signal wiring drift: {mismatch}")
    for key in ("normal_dir", "mono_depth_dir", "semantic_region_cache"):
        if not isinstance(config.get(key), str) or not config[key]:
            raise RuntimeError(f"{arm.upper()} misses {key}")
    if arm == "a2":
        protect = {
            "surface_seed_protect": True, "surface_seed_protect_until_iter": 10000,
            "surface_seed_prune_opa_initial": 0.05, "surface_seed_prune_opa_final": 0.01,
            "surface_seed_prune_switch_iter": 10000,
        }
        mismatch = {key: (config.get(key), expected) for key, expected in protect.items() if config.get(key) != expected}
        if mismatch:
            raise RuntimeError(f"A2 protection wiring drift: {mismatch}")


def generate_configs(
    lock: dict[str, Any],
    jobs: list[dict[str, Any]],
    prepared: dict[str, dict[str, Any]],
    world_offset: Sequence[float],
    inventory_path: Path,
    progress: list[dict[str, Any]],
    progress_path: Path,
) -> list[dict[str, Any]]:
    config_dir = resolve(lock["outputs"]["generated_config_dir"])
    rows: list[dict[str, Any]] = []
    for sequence, job in enumerate(jobs, 1):
        config = make_training_config(lock, job, prepared[job["building_id"]], world_offset)
        config_path = config_dir / f"{job['job_id']}.yaml"
        atomic_yaml(config_path, config)
        seed_path = Path(config["surface_seed_npz"].replace(lock["container_repo_root"].rstrip("/") + "/", ""))
        seed_path = resolve(seed_path)
        out_dir = resolve(lock["outputs"]["training_root"]) / job["job_id"]
        row = {
            "sequence": sequence, **job, "config_path": relative(config_path),
            "config_sha256": sha256_file(config_path), "data_root": prepared[job["building_id"]]["data_root"],
            "surface_seed_npz": relative(seed_path), "surface_seed_sha256": sha256_file(seed_path),
            "out_dir": relative(out_dir), "final_checkpoint": relative(out_dir / "ckpt/final.pt"),
            "iterations": int(lock["training"]["iterations"]), "gt_used": False,
            "lod2_used": False, "als_used": False, "status": "prepared",
        }
        rows.append(row)
        atomic_csv(inventory_path, rows, JOB_FIELDS)
        progress.append({
            "sequence": len(progress) + 1, "stage": "config", "building_id": job["building_id"],
            "view_stem": "", "status": "complete", "detail": job["job_id"], "updated_utc": utc_now(),
        })
        atomic_csv(progress_path, progress, PROGRESS_FIELDS)
    return rows


def validate_tilt_trigger(path: Path, lock: dict[str, Any]) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema") != lock["training"]["tilt_trigger_schema"]:
        raise RuntimeError("tilt trigger schema mismatch")
    if payload.get("return_signal") is not True:
        raise RuntimeError("tilt configs are locked until return_signal=true")
    source_hash = payload.get("source_score_sha256")
    if not isinstance(source_hash, str) or len(source_hash) != 64 or any(ch not in "0123456789abcdef" for ch in source_hash):
        raise RuntimeError("tilt trigger must carry a lowercase 64-hex source_score_sha256")
    source = lock["tilt_score_source"]
    if payload.get("scores_csv") != source["scores_csv"]:
        raise RuntimeError("tilt trigger score path differs from the locked Phase-3 score path")
    if payload.get("perturbation_csv") != source["perturbation_csv"]:
        raise RuntimeError("tilt trigger perturbation path differs from the locked Phase-3 path")
    score_path = resolve(source["scores_csv"])
    perturbation_path = resolve(source["perturbation_csv"])
    if not score_path.is_file() or sha256_file(score_path) != source_hash:
        raise RuntimeError("tilt trigger source score file/hash mismatch")
    perturbation_hash = payload.get("source_perturbation_sha256")
    if not isinstance(perturbation_hash, str) or sha256_file(perturbation_path) != perturbation_hash:
        raise RuntimeError("tilt trigger source perturbation file/hash mismatch")
    expected = int(source["expected_nonzero_height_rows"])
    if int(payload.get("expected_nonzero_height_rows", -1)) != expected:
        raise RuntimeError("tilt trigger expected nonzero-row count drift")
    if int(payload.get("observed_nonzero_height_rows", -1)) < expected:
        raise RuntimeError("tilt trigger is based on an incomplete height wave")
    if source.get("require_evaluation_complete") and payload.get("evaluation_complete") is not True:
        raise RuntimeError("tilt trigger evaluation_complete must be true")
    return payload


def load_existing_prepared(lock: dict[str, Any], lock_path: str | Path) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    """Load and hash-check the base prepared roots without rewriting them."""
    base_manifest_path = resolve(lock["outputs"]["prepare_manifest"])
    base_manifest = json.loads(base_manifest_path.read_text(encoding="utf-8"))
    if base_manifest.get("status") != "complete" or base_manifest.get("mode") != "base":
        raise RuntimeError("conditional tilt generation requires a complete base prepare manifest")
    current_lock_hash = sha256_file(lock_path)
    if base_manifest.get("lock_sha256") != current_lock_hash:
        raise RuntimeError("base prepare manifest lock hash differs from the current tilt lock")
    prepared = base_manifest.get("prepared_buildings") or {}
    if set(prepared) != set(lock["targets"]):
        raise RuntimeError("base prepared-building inventory is incomplete")
    for building, row in prepared.items():
        data_manifest = resolve(row["data_manifest"])
        if sha256_file(data_manifest) != row["data_manifest_sha256"]:
            raise RuntimeError(f"prepared data manifest hash drift for {building}")
        for key in ("p0_surface_seed", "a1a2_surface_seed"):
            seed = resolve(row[key]["path"])
            if sha256_file(seed) != row[key]["sha256"]:
                raise RuntimeError(f"prepared seed hash drift for {building}/{key}")
    return prepared, {
        "path": relative(base_manifest_path), "sha256": sha256_file(base_manifest_path),
        "inventory": base_manifest["inventory"], "inventory_sha256": base_manifest["inventory_sha256"],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lock", default=str(DEFAULT_LOCK))
    parser.add_argument("--mode", choices=("base", "tilt"), default="base")
    parser.add_argument(
        "--trigger-file",
        help="conditional tilt trigger; defaults to outputs.tilt_trigger from the lock",
    )
    args = parser.parse_args()

    lock = load_lock(args.lock)
    runtime_attestation = validate_runtime_attestation(lock)
    if args.mode == "tilt":
        trigger_path = resolve(args.trigger_file or lock["outputs"]["tilt_trigger"])
        trigger = validate_tilt_trigger(trigger_path, lock)
    else:
        trigger_path = None
        trigger = None

    visible_manifest = validate_locked_views(lock)
    world_offset = load_world_offset(lock)
    footprints = load_footprints(resolve(lock["sources"]["footprints"]), lock["targets"])
    progress_path = resolve(
        lock["outputs"]["prepare_progress" if args.mode == "base" else "tilt_prepare_progress"]
    )
    progress: list[dict[str, Any]] = []
    prepared: dict[str, dict[str, Any]] = {}
    manifest_path = resolve(
        lock["outputs"]["prepare_manifest" if args.mode == "base" else "tilt_prepare_manifest"]
    )
    manifest: dict[str, Any] = {
        "schema": "jointbuildgs.s3ap.phase2.prepare_manifest.v1", "status": "running",
        "created_utc": utc_now(), "mode": args.mode, "git_head": git_value("rev-parse", "HEAD"),
        "git_branch": git_value("branch", "--show-current"), "lock_path": relative(args.lock),
        "lock_sha256": sha256_file(args.lock), "visible_manifest": visible_manifest,
        "runtime_attestation": runtime_attestation,
        "gt_used": False, "lod2_used": False, "als_used": False,
        "training_started": False, "prepared_buildings": {}, "jobs": [],
    }
    if trigger is not None:
        manifest["tilt_trigger"] = {
            "path": relative(trigger_path), "sha256": sha256_file(trigger_path), "payload": trigger,
        }
    if args.mode == "base":
        source_sparse = resolve(lock["sources"]["sparse_root"])
        cameras = read_cameras_bin(source_sparse / "cameras.bin")
        images = read_images_bin(source_sparse / "images.bin")
        image_by_stem = {Path(image.name).stem: image for image in images.values()}
        source_points = read_points3d_bin(source_sparse / "points3D.bin")
        pair_boxes, pair_hashes = discover_pair_crop_boxes(resolve(lock["sources"]["pair_cache_dir"]))
        manifest.update({
            "pair_cache_sha256": pair_hashes,
            "source_sparse_sha256": {
                name: sha256_file(source_sparse / name) for name in ("cameras.bin", "images.bin", "points3D.bin")
            },
            "mono_prior_provenance": {
                **lock["mono_prior_provenance"],
                "source_sha256": {
                    key: {"path": relative(lock["sources"][key]), "sha256": sha256_file(lock["sources"][key])}
                    for key in (
                        "mono_prior_generator", "mono_prior_generation_log", "mono_runtime_csv",
                        "mono_depth_alignment_csv", "mono_depth_weights", "mono_normal_pin_manifest",
                    )
                },
                "selected_map_hash_location": "prepared_buildings.<id>.views[].source_sha256.normal/mono_depth",
            },
        })
        atomic_json(manifest_path, manifest)
        for building in lock["targets"]:
            prepared[building] = stage_building(
                lock, building, cameras, images, image_by_stem, source_points, pair_boxes,
                footprints[building], world_offset, progress, progress_path,
            )
            manifest["prepared_buildings"][building] = prepared[building]
            manifest.setdefault("mono_target_support", {})[building] = prepared[building]["mono_target_support"]
            atomic_json(manifest_path, manifest)
        jobs = base_job_specs(lock)
        inventory_path = resolve(lock["outputs"]["base_inventory"])
    else:
        prepared, base_reference = load_existing_prepared(lock, args.lock)
        manifest["prepared_buildings"] = prepared
        manifest["base_prepare_reference"] = base_reference
        manifest["prepared_data_rewritten"] = False
        atomic_json(manifest_path, manifest)
        jobs = tilt_job_specs(lock, footprints, world_offset)
        inventory_path = resolve(lock["outputs"]["tilt_inventory"])
    rows = generate_configs(lock, jobs, prepared, world_offset, inventory_path, progress, progress_path)
    manifest.update({
        "status": "complete", "completed_utc": utc_now(), "inventory": relative(inventory_path),
        "inventory_sha256": sha256_file(inventory_path), "job_count": len(rows),
        "jobs": [{key: row[key] for key in ("job_id", "config_path", "config_sha256", "final_checkpoint")} for row in rows],
        "training_started": False,
    })
    atomic_json(manifest_path, manifest)
    print(json.dumps({
        "status": "complete", "mode": args.mode, "prepared_buildings": len(prepared),
        "job_count": len(rows), "inventory": relative(inventory_path), "training_started": False,
    }, sort_keys=True))


if __name__ == "__main__":
    main()
