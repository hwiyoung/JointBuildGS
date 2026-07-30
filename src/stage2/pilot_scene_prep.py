"""Reusable scene-crop and footprint-projection utilities for pilot P1W.

This module generalizes the mechanics in
``scripts/e5_c001/p2_gsjso/e5_pilot_train_prep.py`` without changing that
historical script.  Its inputs are the existing COLMAP SfM/MVS scene, a dense
MVS-derived seed cloud, an EPSG:25832 XY footprint set, and an already locked
training bbox.  It never reads LoD2 Z, roof faces, roof type, or semantics.
"""
from __future__ import annotations

import csv
import json
import math
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

import cv2
import numpy as np
from PIL import Image as PILImage
from plyfile import PlyData, PlyElement
from shapely import contains_xy
from shapely.geometry import MultiPolygon, Polygon, box, shape
from shapely.geometry.base import BaseGeometry

from .colmap_io import (
    CAMERA_MODEL_NAMES,
    Camera,
    Image,
    read_array,
    read_cameras_bin,
    read_images_bin,
    read_points3d_bin,
)


CRS = "EPSG:25832"
WORLD_SHIFT = np.asarray([690953.0, 5336071.0, 604.0], dtype=np.float64)
MASK_HEIGHT_QUANTILE = 0.80
MIN_HEIGHT_POINTS = 16
Z_PERCENTILES = (1.0, 99.0)
Z_PAD_M = 15.0
VIEW_PAD_PX = 96


@dataclass(frozen=True)
class HeightEstimate:
    building_id: str
    local_z_m: float
    seed_point_count: int
    upper_quantile: float
    upper_point_count: int
    method: str = "median of dense-MVS seed z values at/above per-building q80"


@dataclass(frozen=True)
class ViewCrop:
    image_id: int
    name: str
    source_camera_id: int
    crop: tuple[int, int, int, int]
    visible_building_count: int

    @property
    def width(self) -> int:
        return self.crop[2] - self.crop[0]

    @property
    def height(self) -> int:
        return self.crop[3] - self.crop[1]


def read_ply_xyz(path: str | Path) -> np.ndarray:
    """Read an XYZ-only PLY into float64 without inventing attributes."""

    path = Path(path)
    ply = PlyData.read(str(path))
    if "vertex" not in ply:
        raise RuntimeError(f"PLY has no vertex element: {path}")
    vertices = ply["vertex"].data
    names = set(vertices.dtype.names or ())
    if not {"x", "y", "z"}.issubset(names):
        raise RuntimeError(f"PLY lacks xyz fields: {path}")
    xyz = np.column_stack(
        [
            np.asarray(vertices[axis], dtype=np.float64)
            for axis in ("x", "y", "z")
        ]
    )
    if xyz.ndim != 2 or xyz.shape[1] != 3 or len(xyz) == 0:
        raise RuntimeError(f"empty or invalid XYZ PLY: {path}")
    if not np.isfinite(xyz).all():
        raise RuntimeError(f"non-finite XYZ value in PLY: {path}")
    return xyz


def write_ply_xyz(path: str | Path, xyz: np.ndarray) -> None:
    value = np.asarray(xyz, dtype=np.float64)
    if value.ndim != 2 or value.shape[1] != 3 or len(value) == 0:
        raise ValueError("XYZ output must be a non-empty Nx3 array")
    vertices = np.empty(
        len(value), dtype=[("x", "<f8"), ("y", "<f8"), ("z", "<f8")]
    )
    vertices["x"], vertices["y"], vertices["z"] = value.T
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    PlyData([PlyElement.describe(vertices, "vertex")], text=False).write(str(path))


def load_selected_footprints(
    path: str | Path, building_ids: Sequence[str]
) -> dict[str, BaseGeometry]:
    """Load exactly the selected 2D GroundSurface geometries."""

    wanted = set(building_ids)
    if len(wanted) != len(building_ids):
        raise ValueError("selected building IDs must be unique")
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if payload.get("type") != "FeatureCollection":
        raise RuntimeError("footprint input must be a GeoJSON FeatureCollection")
    output: dict[str, BaseGeometry] = {}
    for feature in payload.get("features", []):
        building_id = str(feature.get("properties", {}).get("building_id", ""))
        if building_id not in wanted:
            continue
        if building_id in output:
            raise RuntimeError(f"duplicate footprint building_id: {building_id}")
        geometry = shape(feature["geometry"])
        if geometry.geom_type not in {"Polygon", "MultiPolygon"}:
            raise RuntimeError(f"unsupported footprint geometry for {building_id}")
        if geometry.is_empty or not geometry.is_valid:
            raise RuntimeError(f"empty/invalid footprint geometry for {building_id}")
        if geometry.has_z:
            raise RuntimeError(
                f"footprint geometry must be XY-only; Z leakage detected for {building_id}"
            )
        output[building_id] = geometry
    missing = sorted(wanted - set(output))
    if missing:
        raise RuntimeError(f"missing selected footprints: {missing}")
    return {building_id: output[building_id] for building_id in building_ids}


def clip_local_xyz_to_utm_bbox(
    xyz_local: np.ndarray,
    bbox_utm: Sequence[float],
    shift: np.ndarray = WORLD_SHIFT,
) -> np.ndarray:
    x0, y0, x1, y1 = map(float, bbox_utm)
    if not (x0 < x1 and y0 < y1):
        raise ValueError("invalid EPSG:25832 crop bbox")
    xyz = np.asarray(xyz_local, dtype=np.float64)
    local_x0, local_y0 = x0 - shift[0], y0 - shift[1]
    local_x1, local_y1 = x1 - shift[0], y1 - shift[1]
    keep = (
        (xyz[:, 0] >= local_x0)
        & (xyz[:, 0] <= local_x1)
        & (xyz[:, 1] >= local_y0)
        & (xyz[:, 1] <= local_y1)
    )
    return np.ascontiguousarray(xyz[keep])


def infer_local_z_range(xyz_local: np.ndarray) -> tuple[float, float]:
    if len(xyz_local) < MIN_HEIGHT_POINTS:
        raise RuntimeError("too few dense-MVS seed points in the training crop")
    low, high = np.percentile(xyz_local[:, 2], Z_PERCENTILES)
    return float(low - Z_PAD_M), float(high + Z_PAD_M)


def derive_sfm_mvs_footprint_heights(
    footprints: Mapping[str, BaseGeometry],
    xyz_local: np.ndarray,
    *,
    shift: np.ndarray = WORLD_SHIFT,
    upper_quantile: float = MASK_HEIGHT_QUANTILE,
    min_points: int = MIN_HEIGHT_POINTS,
) -> dict[str, HeightEstimate]:
    """Estimate one projection Z per footprint from dense MVS points only."""

    if not 0.5 <= upper_quantile < 1.0:
        raise ValueError("upper_quantile must be in [0.5, 1.0)")
    if min_points < 1:
        raise ValueError("min_points must be positive")
    xyz = np.asarray(xyz_local, dtype=np.float64)
    x_utm = xyz[:, 0] + shift[0]
    y_utm = xyz[:, 1] + shift[1]
    estimates: dict[str, HeightEstimate] = {}
    for building_id, geometry in footprints.items():
        minx, miny, maxx, maxy = geometry.bounds
        bbox_keep = (
            (x_utm >= minx)
            & (x_utm <= maxx)
            & (y_utm >= miny)
            & (y_utm <= maxy)
        )
        candidate = np.flatnonzero(bbox_keep)
        if len(candidate):
            inside = contains_xy(geometry, x_utm[candidate], y_utm[candidate])
            candidate = candidate[np.asarray(inside, dtype=bool)]
        values = xyz[candidate, 2]
        values = values[np.isfinite(values)]
        if len(values) < min_points:
            raise RuntimeError(
                f"{building_id}: only {len(values)} dense-MVS points inside footprint; "
                f"need {min_points}"
            )
        threshold = float(np.quantile(values, upper_quantile))
        upper = values[values >= threshold]
        if len(upper) == 0:
            raise RuntimeError(f"{building_id}: empty upper dense-MVS height band")
        estimates[building_id] = HeightEstimate(
            building_id=building_id,
            local_z_m=float(np.median(upper)),
            seed_point_count=int(len(values)),
            upper_quantile=float(upper_quantile),
            upper_point_count=int(len(upper)),
        )
    return estimates


def project_points(points_local: np.ndarray, image: Image, camera: Camera) -> np.ndarray:
    points = np.asarray(points_local, dtype=np.float64)
    camera_xyz = (image.R() @ points.T).T + image.tvec.reshape(1, 3)
    z = camera_xyz[:, 2]
    projected = np.full((len(points), 3), np.nan, dtype=np.float64)
    valid = z > 1e-3
    if np.any(valid):
        uvw = (camera.K() @ camera_xyz[valid].T).T
        projected[valid, 0] = uvw[:, 0] / uvw[:, 2]
        projected[valid, 1] = uvw[:, 1] / uvw[:, 2]
        projected[valid, 2] = z[valid]
    return projected


def sample_training_volume(
    bbox_utm: Sequence[float],
    z_range_local: Sequence[float],
    *,
    shift: np.ndarray = WORLD_SHIFT,
    steps: int = 5,
) -> np.ndarray:
    x0, y0, x1, y1 = map(float, bbox_utm)
    z0, z1 = map(float, z_range_local)
    xs = np.linspace(x0 - shift[0], x1 - shift[0], steps)
    ys = np.linspace(y0 - shift[1], y1 - shift[1], steps)
    zs = np.linspace(z0, z1, steps)
    return np.asarray([[x, y, z] for x in xs for y in ys for z in zs])


def _polygons(geometry: BaseGeometry) -> list[Polygon]:
    if isinstance(geometry, Polygon):
        return [geometry]
    if isinstance(geometry, MultiPolygon):
        return list(geometry.geoms)
    raise ValueError(f"expected Polygon/MultiPolygon, got {geometry.geom_type}")


def _ring_local_xyz(
    coordinates: Any, local_z: float, shift: np.ndarray = WORLD_SHIFT
) -> np.ndarray:
    xy = np.asarray(coordinates, dtype=np.float64)[:, :2]
    return np.column_stack(
        [xy[:, 0] - shift[0], xy[:, 1] - shift[1], np.full(len(xy), local_z)]
    )


def projected_footprint_geometry(
    geometry: BaseGeometry,
    local_z: float,
    image: Image,
    camera: Camera,
    *,
    pixel_offset: tuple[float, float] = (0.0, 0.0),
) -> BaseGeometry:
    """Project one horizontal XY footprint into image pixels."""

    output: BaseGeometry | None = None
    for polygon in _polygons(geometry):
        projected_rings: list[np.ndarray] = []
        for ring in [polygon.exterior, *polygon.interiors]:
            uvz = project_points(_ring_local_xyz(ring.coords, local_z), image, camera)
            if not np.isfinite(uvz).all() or np.any(uvz[:, 2] <= 0):
                projected_rings = []
                break
            uv = uvz[:, :2].copy()
            uv[:, 0] -= pixel_offset[0]
            uv[:, 1] -= pixel_offset[1]
            projected_rings.append(uv)
        if not projected_rings:
            continue
        candidate = Polygon(projected_rings[0], projected_rings[1:])
        if not candidate.is_valid:
            candidate = candidate.buffer(0)
        if candidate.is_empty:
            continue
        output = candidate if output is None else output.union(candidate)
    return Polygon() if output is None else output


def plan_view_crops(
    cameras: Mapping[int, Camera],
    images: Mapping[int, Image],
    footprints: Mapping[str, BaseGeometry],
    heights: Mapping[str, HeightEstimate],
    training_bbox_utm: Sequence[float],
    z_range_local: Sequence[float],
    *,
    pad_px: int = VIEW_PAD_PX,
    min_crop_px: int = 128,
) -> list[ViewCrop]:
    """Reproduce the historical block-volume crop with exact roof visibility."""

    volume = sample_training_volume(training_bbox_utm, z_range_local)
    plans: list[ViewCrop] = []
    for image_id, image in sorted(images.items(), key=lambda item: item[1].name):
        camera = cameras[image.camera_id]
        frame = box(0.0, 0.0, float(camera.width), float(camera.height))
        visible_geometries: list[BaseGeometry] = []
        for building_id, geometry in footprints.items():
            projected = projected_footprint_geometry(
                geometry, heights[building_id].local_z_m, image, camera
            )
            if not projected.is_empty and projected.intersects(frame):
                visible_geometries.append(projected.intersection(frame))
        if not visible_geometries:
            continue

        uvz = project_points(volume, image, camera)
        finite = np.isfinite(uvz[:, 0]) & np.isfinite(uvz[:, 1]) & (uvz[:, 2] > 0)
        uv = uvz[finite, :2]
        near = (
            (uv[:, 0] >= -100)
            & (uv[:, 0] <= camera.width + 100)
            & (uv[:, 1] >= -100)
            & (uv[:, 1] <= camera.height + 100)
        )
        uv = uv[near]
        bounds = [geometry.bounds for geometry in visible_geometries]
        x_values = [value for bounds4 in bounds for value in (bounds4[0], bounds4[2])]
        y_values = [value for bounds4 in bounds for value in (bounds4[1], bounds4[3])]
        if len(uv):
            x_values.extend(uv[:, 0].tolist())
            y_values.extend(uv[:, 1].tolist())
        x0 = max(0, int(math.floor(min(x_values) - pad_px)))
        y0 = max(0, int(math.floor(min(y_values) - pad_px)))
        x1 = min(camera.width, int(math.ceil(max(x_values) + pad_px)))
        y1 = min(camera.height, int(math.ceil(max(y_values) + pad_px)))
        if x1 - x0 < min_crop_px or y1 - y0 < min_crop_px:
            continue
        plans.append(
            ViewCrop(
                image_id=int(image_id),
                name=image.name,
                source_camera_id=int(image.camera_id),
                crop=(x0, y0, x1, y1),
                visible_building_count=len(visible_geometries),
            )
        )
    if len(plans) < 10:
        raise RuntimeError(f"too few expanded pilot crop views: {len(plans)}")
    return plans


def adjust_camera(camera: Camera, camera_id: int, crop: Sequence[int]) -> Camera:
    x0, y0, x1, y1 = map(int, crop)
    params = np.asarray(camera.params, dtype=np.float64).copy()
    if camera.model == "SIMPLE_PINHOLE":
        params[1] -= x0
        params[2] -= y0
    elif camera.model == "PINHOLE":
        params[2] -= x0
        params[3] -= y0
    elif camera.model in {"SIMPLE_RADIAL", "SIMPLE_RADIAL_FISHEYE"}:
        params[1] -= x0
        params[2] -= y0
    elif camera.model in {"RADIAL", "RADIAL_FISHEYE"}:
        params[1] -= x0
        params[2] -= y0
    elif camera.model in {"OPENCV", "OPENCV_FISHEYE", "FULL_OPENCV"}:
        params[2] -= x0
        params[3] -= y0
    else:
        raise RuntimeError(f"unsupported camera model for crop: {camera.model}")
    return Camera(camera_id, camera.model, x1 - x0, y1 - y0, params)


def write_cameras_bin(path: str | Path, cameras: Mapping[int, Camera]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as handle:
        handle.write(struct.pack("<Q", len(cameras)))
        for camera_id in sorted(cameras):
            camera = cameras[camera_id]
            model_id, expected = CAMERA_MODEL_NAMES[camera.model]
            params = np.asarray(camera.params, dtype=np.float64)
            if len(params) != expected:
                raise RuntimeError(f"{camera.model} expected {expected} params")
            handle.write(
                struct.pack(
                    "<iiQQ",
                    int(camera.id),
                    int(model_id),
                    int(camera.width),
                    int(camera.height),
                )
            )
            handle.write(struct.pack("<" + "d" * expected, *params.tolist()))


def write_images_bin(path: str | Path, images: Mapping[int, Image]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as handle:
        handle.write(struct.pack("<Q", len(images)))
        for image_id in sorted(images):
            image = images[image_id]
            handle.write(struct.pack("<I", int(image.id)))
            handle.write(struct.pack("<dddd", *image.qvec.astype(float).tolist()))
            handle.write(struct.pack("<ddd", *image.tvec.astype(float).tolist()))
            handle.write(struct.pack("<I", int(image.camera_id)))
            handle.write(image.name.encode("utf-8") + b"\x00")
            handle.write(struct.pack("<Q", 0))


def write_points3d_bin(path: str | Path, xyzrgb: np.ndarray) -> None:
    value = np.asarray(xyzrgb)
    if value.ndim != 2 or value.shape[1] != 6 or len(value) == 0:
        raise ValueError("points3D output must be non-empty Nx6 xyzrgb")
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as handle:
        handle.write(struct.pack("<Q", len(value)))
        for point_id, row in enumerate(value, start=1):
            x, y, z, red, green, blue = row
            handle.write(struct.pack("<Q", point_id))
            handle.write(struct.pack("<ddd", float(x), float(y), float(z)))
            handle.write(struct.pack("<BBB", int(red), int(green), int(blue)))
            handle.write(struct.pack("<d", 0.0))
            handle.write(struct.pack("<Q", 0))


def write_colmap_array(path: str | Path, array: np.ndarray) -> None:
    value = np.asarray(array, dtype=np.float32)
    height, width = value.shape[:2]
    channels = 1 if value.ndim == 2 else value.shape[2]
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as handle:
        handle.write(f"{width}&{height}&{channels}&".encode("ascii"))
        value.tofile(handle)


def _scaled_map_crop(
    array: np.ndarray,
    crop: Sequence[int],
    image_size_wh: Sequence[int],
) -> np.ndarray:
    x0, y0, x1, y1 = map(int, crop)
    image_width, image_height = map(int, image_size_wh)
    map_height, map_width = array.shape[:2]
    map_x0 = max(0, min(map_width - 1, int(math.floor(x0 * map_width / image_width))))
    map_y0 = max(0, min(map_height - 1, int(math.floor(y0 * map_height / image_height))))
    map_x1 = max(
        map_x0 + 1, min(map_width, int(math.ceil(x1 * map_width / image_width)))
    )
    map_y1 = max(
        map_y0 + 1, min(map_height, int(math.ceil(y1 * map_height / image_height)))
    )
    return np.ascontiguousarray(array[map_y0:map_y1, map_x0:map_x1, ...])


def required_mvs_paths(data_root: str | Path, image_name: str) -> dict[str, Path]:
    root = Path(data_root)
    return {
        "depth_geometric": root
        / "stereo/depth_maps"
        / f"{image_name}.geometric.bin",
        "normal_geometric": root
        / "stereo/normal_maps"
        / f"{image_name}.geometric.bin",
    }


def preflight_view_sources(
    data_root: str | Path, plans: Sequence[ViewCrop]
) -> dict[str, Any]:
    root = Path(data_root)
    missing_images: list[str] = []
    missing_mvs: list[str] = []
    optional_counts = {"depth_photometric": 0, "normal_photometric": 0}
    for plan in plans:
        if not (root / "images" / plan.name).is_file():
            missing_images.append(plan.name)
        for kind, path in required_mvs_paths(root, plan.name).items():
            if not path.is_file():
                missing_mvs.append(f"{kind}:{plan.name}")
        for kind, subdir in (
            ("depth_photometric", "depth_maps"),
            ("normal_photometric", "normal_maps"),
        ):
            path = root / "stereo" / subdir / f"{plan.name}.photometric.bin"
            optional_counts[kind] += int(path.is_file())
    if missing_images or missing_mvs:
        raise RuntimeError(
            f"expanded prep source preflight failed: missing_images={missing_images[:5]}, "
            f"missing_mvs={missing_mvs[:5]}"
        )
    return {
        "selected_view_count": len(plans),
        "required_rgb_present": len(plans),
        "required_depth_geometric_present": len(plans),
        "required_normal_geometric_present": len(plans),
        **optional_counts,
        "all_required_mvs_depth_normal_present": True,
    }


def materialize_scene_crop(
    source_data_root: str | Path,
    source_sparse_root: str | Path,
    output_data_root: str | Path,
    plans: Sequence[ViewCrop],
    training_bbox_utm: Sequence[float],
) -> dict[str, Any]:
    """Materialize RGB, sparse SfM, and both MVS map kinds for locked views."""

    source_data_root = Path(source_data_root)
    source_sparse_root = Path(source_sparse_root)
    output_data_root = Path(output_data_root)
    if output_data_root.exists() and any(output_data_root.iterdir()):
        raise RuntimeError(f"output data root must be empty: {output_data_root}")
    cameras = read_cameras_bin(source_sparse_root / "cameras.bin")
    images = read_images_bin(source_sparse_root / "images.bin")
    output_cameras: dict[int, Camera] = {}
    output_images: dict[int, Image] = {}
    map_counts = {
        "depth_geometric": 0,
        "depth_photometric": 0,
        "normal_geometric": 0,
        "normal_photometric": 0,
    }
    rows: list[dict[str, Any]] = []
    for plan in plans:
        image = images[plan.image_id]
        camera = cameras[image.camera_id]
        source_image = source_data_root / "images" / plan.name
        destination_image = output_data_root / "images" / plan.name
        destination_image.parent.mkdir(parents=True, exist_ok=True)
        with PILImage.open(source_image) as rgb:
            rgb.crop(plan.crop).save(destination_image)
        output_cameras[plan.image_id] = adjust_camera(camera, plan.image_id, plan.crop)
        output_images[plan.image_id] = Image(
            image.id,
            image.qvec.copy(),
            image.tvec.copy(),
            plan.image_id,
            image.name,
        )
        row = {
            "image_id": plan.image_id,
            "view_id": plan.name,
            "crop_x0": plan.crop[0],
            "crop_y0": plan.crop[1],
            "crop_x1": plan.crop[2],
            "crop_y1": plan.crop[3],
            "crop_width": plan.width,
            "crop_height": plan.height,
            "visible_selected_buildings": plan.visible_building_count,
        }
        for kind, subdir in (("depth", "depth_maps"), ("normal", "normal_maps")):
            for suffix in ("geometric", "photometric"):
                source = (
                    source_data_root
                    / "stereo"
                    / subdir
                    / f"{plan.name}.{suffix}.bin"
                )
                key = f"{kind}_{suffix}"
                if not source.is_file():
                    if suffix == "geometric":
                        raise RuntimeError(f"required MVS map disappeared: {source}")
                    row[key] = False
                    continue
                value = read_array(source)
                cropped = _scaled_map_crop(
                    value, plan.crop, (camera.width, camera.height)
                )
                destination = output_data_root / "stereo" / subdir / source.name
                write_colmap_array(destination, cropped)
                map_counts[key] += 1
                row[key] = True
        rows.append(row)

    sparse_output = output_data_root / "sparse/0"
    write_cameras_bin(sparse_output / "cameras.bin", output_cameras)
    write_images_bin(sparse_output / "images.bin", output_images)
    points = read_points3d_bin(source_sparse_root / "points3D.bin")
    clipped_xyz = clip_local_xyz_to_utm_bbox(points[:, :3], training_bbox_utm)
    x0, y0, x1, y1 = map(float, training_bbox_utm)
    keep = (
        (points[:, 0] >= x0 - WORLD_SHIFT[0])
        & (points[:, 0] <= x1 - WORLD_SHIFT[0])
        & (points[:, 1] >= y0 - WORLD_SHIFT[1])
        & (points[:, 1] <= y1 - WORLD_SHIFT[1])
    )
    clipped_points = points[keep]
    if len(clipped_points) < 10 or len(clipped_points) != len(clipped_xyz):
        raise RuntimeError("too few/inconsistent real SfM points in expanded crop")
    write_points3d_bin(sparse_output / "points3D.bin", clipped_points)

    view_csv = output_data_root.parent / "view_crops.csv"
    with view_csv.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    return {
        "view_count": len(plans),
        "sfm_points_clipped": int(len(clipped_points)),
        "mvs_map_counts": map_counts,
        # The staging directory is atomically renamed at publication time, so
        # persisting its absolute name would leave a dead path in the final
        # manifest.  This path is relative to the prep-artifact root.
        "view_crop_csv": "view_crops.csv",
        "semantic_directory_created": False,
    }


def rasterize_photo_support_mask(
    width: int,
    height: int,
    image: Image,
    camera: Camera,
    footprints: Mapping[str, BaseGeometry],
    heights: Mapping[str, HeightEstimate],
) -> tuple[np.ndarray, dict[str, Any]]:
    """Rasterize the selected footprint union at dense-MVS-derived heights."""

    frame = box(0.0, 0.0, float(width), float(height))
    mask = np.zeros((height, width), dtype=np.uint8)
    visible_ids: list[str] = []
    for building_id, geometry in footprints.items():
        projected = projected_footprint_geometry(
            geometry, heights[building_id].local_z_m, image, camera
        )
        clipped = projected.intersection(frame)
        if clipped.is_empty:
            continue
        visible_ids.append(building_id)
        parts = _polygons(clipped) if clipped.geom_type in {"Polygon", "MultiPolygon"} else []
        for polygon in parts:
            polygon_mask = np.zeros_like(mask)
            exterior = np.rint(np.asarray(polygon.exterior.coords)).astype(np.int32)
            cv2.fillPoly(polygon_mask, [exterior], color=1)
            for interior in polygon.interiors:
                hole = np.rint(np.asarray(interior.coords)).astype(np.int32)
                cv2.fillPoly(polygon_mask, [hole], color=0)
            mask |= polygon_mask
    binary = mask.astype(bool)
    if not bool(binary.any()):
        raise RuntimeError("empty footprint photo-support mask is forbidden")
    return binary, {
        "visible_selected_building_count": len(visible_ids),
        "visible_selected_building_ids": visible_ids,
        "true_pixel_count": int(binary.sum()),
        "true_pixel_fraction": float(binary.mean()),
    }
