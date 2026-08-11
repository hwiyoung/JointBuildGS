#!/usr/bin/env python3
"""Derive full-source E1/E2/image support boundaries and add them to viewer 8876."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import io
import json
import math
import os
from pathlib import Path
import struct
from typing import Any, Sequence

import laspy
import numpy as np
from scipy import ndimage
from shapely.geometry import Polygon, box, shape
from skimage.draw import polygon as raster_polygon
from skimage.measure import find_contours


REPO = Path("/workspace/JointBuildGS")
AR = Path("/artifacts/JointBuildGS")
CONFIG = REPO / "configs/p2/viewer_8876_full_source_coverage_boundaries_v1/viewer.json"
SOURCE = REPO / "scripts/p2/viewer_8876_full_source_coverage_boundaries_v1/build.py"
TASK = AR / "phase-payloads/p2/viewer_8876_full_source_coverage_boundaries_v1/P2-VIEWER-8876-FULL-SOURCE-COVERAGE-BOUNDARIES-v1"
CAMERA_MODEL_PARAMS = {0: 3, 1: 4, 2: 4, 3: 5, 4: 8, 5: 8, 6: 12, 7: 5, 8: 4, 9: 5, 10: 12}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def atomic_bytes(path: Path, body: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(body)
    os.replace(temporary, path)


def atomic_text(path: Path, body: str) -> None:
    atomic_bytes(path, body.encode("utf-8"))


def atomic_json(path: Path, body: object) -> None:
    atomic_text(path, json.dumps(body, indent=2, sort_keys=True) + "\n")


def file_record(path: Path, relative_path: str | None = None) -> dict[str, Any]:
    return {"path": relative_path or str(path), "bytes": path.stat().st_size, "sha256": sha256(path)}


def verify(path: Path, expected: dict[str, Any] | str) -> dict[str, Any]:
    if not path.is_file() or path.is_symlink():
        raise RuntimeError(f"missing or invalid regular input: {path}")
    record = file_record(path)
    expected_hash = expected if isinstance(expected, str) else expected["sha256"]
    expected_bytes = None if isinstance(expected, str) else int(expected["bytes"])
    if expected_bytes is not None and record["bytes"] != expected_bytes:
        raise RuntimeError(f"byte drift: {path}: {record['bytes']} != {expected_bytes}")
    if record["sha256"] != expected_hash:
        raise RuntimeError(f"sha256 drift: {path}: {record['sha256']} != {expected_hash}")
    return record


def qvec_rotation(q: Sequence[float]) -> np.ndarray:
    w, x, y, z = q
    return np.array(
        [
            [1 - 2 * y * y - 2 * z * z, 2 * x * y - 2 * w * z, 2 * x * z + 2 * w * y],
            [2 * x * y + 2 * w * z, 1 - 2 * x * x - 2 * z * z, 2 * y * z - 2 * w * x],
            [2 * x * z - 2 * w * y, 2 * y * z + 2 * w * x, 1 - 2 * x * x - 2 * y * y],
        ],
        dtype=np.float64,
    )


def parse_cameras(path: Path) -> dict[int, dict[str, Any]]:
    stream = io.BytesIO(path.read_bytes())
    count = struct.unpack("<Q", stream.read(8))[0]
    cameras: dict[int, dict[str, Any]] = {}
    for _ in range(count):
        camera_id, model_id = struct.unpack("<ii", stream.read(8))
        width, height = struct.unpack("<QQ", stream.read(16))
        nparams = CAMERA_MODEL_PARAMS[model_id]
        params = struct.unpack(f"<{nparams}d", stream.read(8 * nparams))
        cameras[camera_id] = {"model_id": model_id, "width": width, "height": height, "params": params}
    if stream.tell() != len(stream.getbuffer()):
        raise RuntimeError("unexpected trailing cameras.bin bytes")
    return cameras


def parse_images(path: Path) -> list[dict[str, Any]]:
    stream = io.BytesIO(path.read_bytes())
    count = struct.unpack("<Q", stream.read(8))[0]
    images: list[dict[str, Any]] = []
    for _ in range(count):
        image_id = struct.unpack("<i", stream.read(4))[0]
        qvec = struct.unpack("<4d", stream.read(32))
        tvec = np.asarray(struct.unpack("<3d", stream.read(24)), dtype=np.float64)
        camera_id = struct.unpack("<i", stream.read(4))[0]
        while True:
            value = stream.read(1)
            if value == b"\0":
                break
            if not value:
                raise RuntimeError("truncated images.bin name")
        points = struct.unpack("<Q", stream.read(8))[0]
        stream.seek(points * 24, io.SEEK_CUR)
        rotation = qvec_rotation(qvec)
        images.append(
            {
                "image_id": image_id,
                "camera_id": camera_id,
                "rotation": rotation,
                "center": -(rotation.T @ tvec),
            }
        )
    if stream.tell() != len(stream.getbuffer()):
        raise RuntimeError("unexpected trailing images.bin bytes")
    return images


def utm_inverse(easting: np.ndarray, northing: np.ndarray, *, a: float, inv_f: float) -> tuple[np.ndarray, np.ndarray]:
    f = 1.0 / inv_f
    e2 = f * (2.0 - f)
    ep2 = e2 / (1.0 - e2)
    k0 = 0.9996
    x = easting - 500000.0
    m = northing / k0
    mu = m / (a * (1 - e2 / 4 - 3 * e2**2 / 64 - 5 * e2**3 / 256))
    e1 = (1 - math.sqrt(1 - e2)) / (1 + math.sqrt(1 - e2))
    j1 = 3 * e1 / 2 - 27 * e1**3 / 32
    j2 = 21 * e1**2 / 16 - 55 * e1**4 / 32
    j3 = 151 * e1**3 / 96
    j4 = 1097 * e1**4 / 512
    fp = mu + j1 * np.sin(2 * mu) + j2 * np.sin(4 * mu) + j3 * np.sin(6 * mu) + j4 * np.sin(8 * mu)
    sin_fp, cos_fp, tan_fp = np.sin(fp), np.cos(fp), np.tan(fp)
    c1, t1 = ep2 * cos_fp**2, tan_fp**2
    n1 = a / np.sqrt(1 - e2 * sin_fp**2)
    r1 = a * (1 - e2) / (1 - e2 * sin_fp**2) ** 1.5
    d = x / (n1 * k0)
    lat = fp - (n1 * tan_fp / r1) * (
        d**2 / 2 - (5 + 3 * t1 + 10 * c1 - 4 * c1**2 - 9 * ep2) * d**4 / 24
        + (61 + 90 * t1 + 298 * c1 + 45 * t1**2 - 252 * ep2 - 3 * c1**2) * d**6 / 720
    )
    lon = math.radians(9.0) + (
        d - (1 + 2 * t1 + c1) * d**3 / 6
        + (5 - 2 * c1 + 28 * t1 - 3 * c1**2 + 8 * ep2 + 24 * t1**2) * d**5 / 120
    ) / cos_fp
    return lat, lon


def utm_forward(lat: np.ndarray, lon: np.ndarray, *, a: float, inv_f: float) -> tuple[np.ndarray, np.ndarray]:
    f = 1.0 / inv_f
    e2 = f * (2.0 - f)
    ep2 = e2 / (1.0 - e2)
    k0 = 0.9996
    lon0 = math.radians(9.0)
    n = a / np.sqrt(1 - e2 * np.sin(lat) ** 2)
    t = np.tan(lat) ** 2
    c = ep2 * np.cos(lat) ** 2
    aa = np.cos(lat) * (lon - lon0)
    m = a * (
        (1 - e2 / 4 - 3 * e2**2 / 64 - 5 * e2**3 / 256) * lat
        - (3 * e2 / 8 + 3 * e2**2 / 32 + 45 * e2**3 / 1024) * np.sin(2 * lat)
        + (15 * e2**2 / 256 + 45 * e2**3 / 1024) * np.sin(4 * lat)
        - (35 * e2**3 / 3072) * np.sin(6 * lat)
    )
    easting = 500000 + k0 * n * (
        aa + (1 - t + c) * aa**3 / 6 + (5 - 18 * t + t**2 + 72 * c - 58 * ep2) * aa**5 / 120
    )
    northing = k0 * (
        m + n * np.tan(lat) * (
            aa**2 / 2 + (5 - t + 9 * c + 4 * c**2) * aa**4 / 24
            + (61 - 58 * t + t**2 + 600 * c - 330 * ep2) * aa**6 / 720
        )
    )
    return easting, northing


def epsg32632_to_25832(x: np.ndarray, y: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    lat, lon = utm_inverse(x, y, a=6378137.0, inv_f=298.257223563)
    return utm_forward(lat, lon, a=6378137.0, inv_f=298.257222101)


def mark_xy(mask: np.ndarray, x: np.ndarray, y: np.ndarray, grid: dict[str, Any]) -> int:
    resolution = float(grid["resolution_m"])
    col = np.floor((x - grid["x0"]) / resolution).astype(np.int64)
    row = np.floor((y - grid["y0"]) / resolution).astype(np.int64)
    inside = (col >= 0) & (col < grid["nx"]) & (row >= 0) & (row < grid["ny"])
    if np.any(inside):
        mask[row[inside], col[inside]] = True
    return int(np.count_nonzero(inside))


def lidar_mask(path: Path, grid: dict[str, Any]) -> tuple[np.ndarray, dict[str, Any]]:
    mask = np.zeros((grid["ny"], grid["nx"]), dtype=bool)
    scanned = accepted = chunks = 0
    with laspy.open(path) as reader:
        for points in reader.chunk_iterator(1_000_000):
            x, y = epsg32632_to_25832(
                np.asarray(points.x, dtype=np.float64),
                np.asarray(points.y, dtype=np.float64),
            )
            scanned += len(points)
            accepted += mark_xy(mask, x, y, grid)
            chunks += 1
    return mask, {"source_points_scanned": scanned, "points_inside_analysis_grid": accepted, "chunks": chunks}


def ply_vertex_layout(path: Path) -> tuple[int, int, np.dtype]:
    type_map = {
        "char": "i1", "int8": "i1", "uchar": "u1", "uint8": "u1",
        "short": "<i2", "int16": "<i2", "ushort": "<u2", "uint16": "<u2",
        "int": "<i4", "int32": "<i4", "uint": "<u4", "uint32": "<u4",
        "float": "<f4", "float32": "<f4", "double": "<f8", "float64": "<f8",
    }
    with path.open("rb") as stream:
        lines: list[str] = []
        while True:
            line = stream.readline()
            if not line:
                raise RuntimeError("truncated PLY header")
            lines.append(line.decode("ascii").strip())
            if lines[-1] == "end_header":
                break
        offset = stream.tell()
    if "format binary_little_endian 1.0" not in lines:
        raise RuntimeError("only binary little-endian PLY is supported")
    vertex_count = 0
    in_vertex = False
    fields: list[tuple[str, str]] = []
    for line in lines:
        parts = line.split()
        if parts[:1] == ["element"]:
            in_vertex = len(parts) == 3 and parts[1] == "vertex"
            if in_vertex:
                vertex_count = int(parts[2])
        elif in_vertex and parts[:1] == ["property"]:
            if len(parts) != 3 or parts[1] == "list":
                raise RuntimeError("unsupported vertex property")
            fields.append((parts[2], type_map[parts[1]]))
    dtype = np.dtype(fields, align=False)
    for field in ("x", "y", "z"):
        if field not in dtype.names:
            raise RuntimeError(f"missing PLY vertex field: {field}")
    return offset, vertex_count, dtype


def mvs_mask(path: Path, grid: dict[str, Any], shift: Sequence[float]) -> tuple[np.ndarray, dict[str, Any]]:
    mask = np.zeros((grid["ny"], grid["nx"]), dtype=bool)
    offset, count, dtype = ply_vertex_layout(path)
    vertices = np.memmap(path, mode="r", dtype=dtype, offset=offset, shape=(count,))
    accepted = 0
    chunk_size = 4_000_000
    for start in range(0, count, chunk_size):
        chunk = vertices[start : start + chunk_size]
        x = np.asarray(chunk["x"], dtype=np.float64) + float(shift[0])
        y = np.asarray(chunk["y"], dtype=np.float64) + float(shift[1])
        finite = np.isfinite(x) & np.isfinite(y)
        accepted += mark_xy(mask, x[finite], y[finite], grid)
    return mask, {
        "source_vertices_scanned": count,
        "vertices_inside_analysis_grid": accepted,
        "ply_header_bytes": offset,
        "vertex_stride_bytes": dtype.itemsize,
    }


def pinhole(camera: dict[str, Any]) -> tuple[float, float, float, float]:
    params = camera["params"]
    if camera["model_id"] == 0:
        return float(params[0]), float(params[0]), float(params[1]), float(params[2])
    if camera["model_id"] in {1, 2, 3, 4, 5, 6, 8, 9, 10}:
        return float(params[0]), float(params[1]), float(params[2]), float(params[3])
    raise RuntimeError(f"unsupported camera model for diagnostic projection: {camera['model_id']}")


def paint_geometry(counts: np.ndarray, geometry: Any, grid: dict[str, Any]) -> None:
    geometries = [geometry] if geometry.geom_type == "Polygon" else list(getattr(geometry, "geoms", []))
    for polygon in geometries:
        if polygon.is_empty or polygon.geom_type != "Polygon":
            continue
        exterior = np.asarray(polygon.exterior.coords)
        rows = (exterior[:, 1] - grid["y0"]) / grid["resolution_m"]
        cols = (exterior[:, 0] - grid["x0"]) / grid["resolution_m"]
        rr, cc = raster_polygon(rows, cols, shape=counts.shape)
        counts[rr, cc] += 1
        for interior in polygon.interiors:
            ring = np.asarray(interior.coords)
            rr, cc = raster_polygon(
                (ring[:, 1] - grid["y0"]) / grid["resolution_m"],
                (ring[:, 0] - grid["x0"]) / grid["resolution_m"],
                shape=counts.shape,
            )
            counts[rr, cc] -= 1


def image_support_mask(
    cameras_path: Path,
    images_path: Path,
    grid: dict[str, Any],
    cfg: dict[str, Any],
    shift: Sequence[float],
) -> tuple[np.ndarray, dict[str, Any]]:
    cameras = parse_cameras(cameras_path)
    images = parse_images(images_path)
    views = np.zeros((grid["ny"], grid["nx"]), dtype=np.uint16)
    oblique = np.zeros_like(views)
    local_z = float(cfg["projection_plane_local_z_m"])
    off_nadir_threshold = float(cfg["minimum_oblique_off_nadir_deg"])
    clip = box(grid["x0"], grid["y0"], grid["x1"], grid["y1"])
    accepted = oblique_accepted = rejected = 0
    for image in images:
        camera = cameras[image["camera_id"]]
        fx, fy, cx, cy = pinhole(camera)
        rotation = image["rotation"]
        center = image["center"]
        axis = rotation.T @ np.asarray([0.0, 0.0, 1.0])
        axis /= np.linalg.norm(axis)
        if axis[2] >= -1e-6:
            rejected += 1
            continue
        points = []
        valid = True
        for u, v in ((0.0, 0.0), (camera["width"], 0.0), (camera["width"], camera["height"]), (0.0, camera["height"])):
            ray = rotation.T @ np.asarray([(u - cx) / fx, (v - cy) / fy, 1.0])
            if abs(ray[2]) < 1e-9:
                valid = False
                break
            scale = (local_z - center[2]) / ray[2]
            if scale <= 0:
                valid = False
                break
            point = center + scale * ray
            points.append((float(point[0] + shift[0]), float(point[1] + shift[1])))
        if not valid:
            rejected += 1
            continue
        footprint = Polygon(points)
        if not footprint.is_valid:
            footprint = footprint.buffer(0)
        footprint = footprint.intersection(clip)
        if footprint.is_empty:
            rejected += 1
            continue
        paint_geometry(views, footprint, grid)
        accepted += 1
        off_nadir = math.degrees(math.acos(float(np.clip(-axis[2], -1.0, 1.0))))
        if off_nadir >= off_nadir_threshold:
            paint_geometry(oblique, footprint, grid)
            oblique_accepted += 1
    support = (views >= int(cfg["minimum_view_count"])) & (oblique >= int(cfg["minimum_oblique_view_count"]))
    return support, {
        "calibrated_images": len(images),
        "projected_images_intersecting_grid": accepted,
        "projected_oblique_images_intersecting_grid": oblique_accepted,
        "rejected_or_nonintersecting_images": rejected,
        "view_count_max": int(views.max()),
        "oblique_view_count_max": int(oblique.max()),
    }


def clean_mask(mask: np.ndarray, cfg: dict[str, Any], *, close_and_fill: bool = True) -> tuple[np.ndarray, dict[str, Any]]:
    original = int(mask.sum())
    result = mask.copy()
    structure = ndimage.generate_binary_structure(2, 1)
    if close_and_fill:
        result = ndimage.binary_closing(result, structure=structure, iterations=int(cfg["closing_iterations"]))
    labels, count = ndimage.label(result, structure=structure)
    sizes = np.bincount(labels.ravel())
    keep = sizes >= int(cfg["minimum_component_cells"])
    keep[0] = False
    result = keep[labels]
    removed_components = int(count - np.count_nonzero(keep))
    holes_filled = 0
    if close_and_fill:
        holes, hole_count = ndimage.label(~result, structure=structure)
        hole_sizes = np.bincount(holes.ravel())
        boundary_labels = np.unique(np.concatenate((holes[0], holes[-1], holes[:, 0], holes[:, -1])))
        fill = (hole_sizes <= int(cfg["maximum_filled_hole_cells"]))
        fill[boundary_labels] = False
        fill[0] = False
        holes_filled = int(np.count_nonzero(fill))
        result |= fill[holes]
    final_components = int(ndimage.label(result, structure=structure)[1])
    return result, {
        "occupied_cells_before_cleanup": original,
        "occupied_cells_after_cleanup": int(result.sum()),
        "removed_small_components": removed_components,
        "filled_small_holes": holes_filled,
        "connected_components_after_cleanup": final_components,
    }


def mask_rings(mask: np.ndarray, grid: dict[str, Any], shift: Sequence[float]) -> tuple[list[list[list[float]]], list[list[list[float]]]]:
    padded = np.pad(mask.astype(np.uint8), 1)
    rings_world: list[list[list[float]]] = []
    rings_local: list[list[list[float]]] = []
    for contour in find_contours(padded, 0.5, fully_connected="low", positive_orientation="low"):
        if len(contour) < 4:
            continue
        world = [
            [
                round(float(grid["x0"] + (col - 0.5) * grid["resolution_m"]), 3),
                round(float(grid["y0"] + (row - 0.5) * grid["resolution_m"]), 3),
            ]
            for row, col in contour
        ]
        if world[0] != world[-1]:
            world.append(world[0])
        simplified = Polygon(world).buffer(0).boundary.simplify(0.25, preserve_topology=True)
        lines = [simplified] if simplified.geom_type == "LineString" else list(getattr(simplified, "geoms", []))
        for line in lines:
            coordinates = [[round(float(x), 3), round(float(y), 3)] for x, y in line.coords]
            if len(coordinates) < 4:
                continue
            if coordinates[0] != coordinates[-1]:
                coordinates.append(coordinates[0])
            rings_world.append(coordinates)
            rings_local.append([[round(x - float(shift[0]), 3), round(y - float(shift[1]), 3)] for x, y in coordinates])
    return rings_world, rings_local


def building_coverage(mask: np.ndarray, features: list[dict[str, Any]], grid: dict[str, Any]) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for feature in features:
        geometry = shape(feature["geometry"])
        minx, miny, maxx, maxy = geometry.bounds
        c0 = max(0, int(math.floor((minx - grid["x0"]) / grid["resolution_m"])))
        c1 = min(grid["nx"], int(math.ceil((maxx - grid["x0"]) / grid["resolution_m"])))
        r0 = max(0, int(math.floor((miny - grid["y0"]) / grid["resolution_m"])))
        r1 = min(grid["ny"], int(math.ceil((maxy - grid["y0"]) / grid["resolution_m"])))
        inside_cells: list[tuple[int, int]] = []
        for row in range(r0, r1):
            for col in range(c0, c1):
                cell = box(
                    grid["x0"] + col * grid["resolution_m"],
                    grid["y0"] + row * grid["resolution_m"],
                    grid["x0"] + (col + 1) * grid["resolution_m"],
                    grid["y0"] + (row + 1) * grid["resolution_m"],
                )
                if geometry.intersects(cell):
                    inside_cells.append((row, col))
        fraction = float(np.mean([mask[row, col] for row, col in inside_cells])) if inside_cells else 0.0
        properties = feature.get("properties", {})
        stable_id = str(properties.get("stable_id") or properties.get("id") or properties.get("gml_id") or properties.get("identificatie") or "UNKNOWN")
        rows.append({"stable_id": stable_id, "coverage_fraction": round(fraction, 6), "intersected_grid_cells": len(inside_cells)})
    values = np.asarray([row["coverage_fraction"] for row in rows], dtype=np.float64)
    return {
        "building_count": len(rows),
        "full_100pct": int(np.count_nonzero(values >= 1.0 - 1e-12)),
        "at_least_95pct": int(np.count_nonzero(values >= 0.95)),
        "at_least_90pct": int(np.count_nonzero(values >= 0.90)),
        "at_least_80pct": int(np.count_nonzero(values >= 0.80)),
        "any_support": int(np.count_nonzero(values > 0.0)),
        "per_building": rows,
    }


def replace_once(body: str, old: str, new: str, label: str) -> str:
    count = body.count(old)
    if count != 1:
        raise RuntimeError(f"expected one {label} replacement, found {count}")
    return body.replace(old, new)


def main() -> None:
    cfg = json.loads(CONFIG.read_text())
    if TASK.exists():
        raise RuntimeError(f"add-once task exists: {TASK}")
    viewer = AR / cfg["viewer_root"]
    output_path = viewer / cfg["output_json"]
    before: dict[str, Any] = {}
    resumed_partial_state: dict[str, Any] | None = None
    for name, expected in cfg["expected_before"].items():
        path = viewer / name
        if name != "viewer_manifest.json" or sha256(path) == expected:
            before[name] = verify(path, expected)
            continue
        current = file_record(path)
        if not output_path.is_file():
            raise RuntimeError(f"viewer manifest drift without resumable output: {current['sha256']} != {expected}")
        partial_manifest = json.loads(path.read_text())
        contract = partial_manifest.get("coverage_boundary_contract", {})
        if contract.get("source") != cfg["output_json"] or contract.get("source_sha256") != sha256(output_path):
            raise RuntimeError("viewer manifest drift is not the bound partial coverage-boundary state")
        resumed_partial_state = {
            "reason": "PREVIOUS_RUN_WROTE_BOUNDARY_JSON_AND_MANIFEST_BEFORE_SAFE_APP_INSERTION_STOPPED",
            "expected_baseline_sha256": expected,
            "observed_partial_manifest": current,
            "observed_boundary_json": file_record(output_path, cfg["output_json"]),
        }
        before[name] = {"path": str(path), "sha256": expected, "role": "BOUND_EXPECTED_BASELINE_BEFORE_PARTIAL_RUN"}
    input_paths = {name: AR / spec["path"] for name, spec in cfg["inputs"].items()}
    inputs = {name: verify(input_paths[name], spec) for name, spec in cfg["inputs"].items()}

    footprints_doc = json.loads(input_paths["shared_footprints_199"].read_text())
    features = footprints_doc["features"]
    if len(features) != 199:
        raise RuntimeError(f"expected 199 shared footprints, found {len(features)}")
    geometries = [shape(feature["geometry"]) for feature in features]
    minx = min(geometry.bounds[0] for geometry in geometries)
    miny = min(geometry.bounds[1] for geometry in geometries)
    maxx = max(geometry.bounds[2] for geometry in geometries)
    maxy = max(geometry.bounds[3] for geometry in geometries)
    resolution = float(cfg["grid"]["resolution_m"])
    padding = float(cfg["grid"]["footprint_union_padding_m"])
    x0, y0 = math.floor((minx - padding) / resolution) * resolution, math.floor((miny - padding) / resolution) * resolution
    x1, y1 = math.ceil((maxx + padding) / resolution) * resolution, math.ceil((maxy + padding) / resolution) * resolution
    grid = {
        "x0": x0, "y0": y0, "x1": x1, "y1": y1,
        "nx": int(round((x1 - x0) / resolution)), "ny": int(round((y1 - y0) / resolution)),
        "resolution_m": resolution,
    }
    shift = cfg["inputs"]["e2_dense_mvs"]["world_shift_xyz"]

    if output_path.exists():
        if resumed_partial_state is None:
            raise RuntimeError(f"unbound pre-existing output: {output_path}")
        boundary_doc = json.loads(output_path.read_text())
        if boundary_doc.get("source_records") != inputs or boundary_doc.get("grid") != grid:
            raise RuntimeError("partial coverage output source or grid contract drift")
        layers = boundary_doc["layers"]
    else:
        raw_lidar, lidar_io = lidar_mask(input_paths["e1_raw_lidar"], grid)
        dense_mvs, mvs_io = mvs_mask(input_paths["e2_dense_mvs"], grid, shift)
        image_support, image_io = image_support_mask(
            input_paths["colmap_cameras"], input_paths["colmap_images"], grid, cfg["image_support"], shift
        )
        raw_lidar, lidar_clean = clean_mask(raw_lidar, cfg["grid"])
        dense_mvs, mvs_clean = clean_mask(dense_mvs, cfg["grid"])
        image_support, image_clean = clean_mask(image_support, cfg["grid"])
        strict_common, common_clean = clean_mask(raw_lidar & dense_mvs & image_support, cfg["grid"], close_and_fill=False)

        masks = {
            "E1_RAW_LIDAR": (raw_lidar, {**lidar_io, **lidar_clean}),
            "IMAGE_MULTIVIEW": (image_support, {**image_io, **image_clean}),
            "E2_DENSE_MVS": (dense_mvs, {**mvs_io, **mvs_clean}),
            "STRICT_DIRECT_COMMON": (strict_common, common_clean),
        }
        definitions = {row["id"]: row for row in cfg["layers"]}
        layers = []
        building_summaries: dict[str, Any] = {}
        for index, (layer_id, (mask, stats)) in enumerate(masks.items()):
            rings_world, rings_local = mask_rings(mask, grid, shift)
            coverage = building_coverage(mask, features, grid)
            building_summaries[layer_id] = coverage
            definition = definitions[layer_id]
            layers.append(
                {
                    "id": layer_id,
                    "label_ko": definition["label_ko"],
                    "color": definition["color"],
                    "display_z_local_m": -44.0 + index * 0.45,
                    "outline_width_m": 0.85,
                    "rings_world_xy": rings_world,
                    "rings_local_xy": rings_local,
                    "ring_count": len(rings_local),
                    "occupied_area_m2": float(mask.sum()) * resolution * resolution,
                    "grid_stats": stats,
                    "building_coverage_summary": {key: value for key, value in coverage.items() if key != "per_building"},
                    "display_only": True,
                }
            )

        boundary_doc = {
            "schema": "jointbuildgs.p2.viewer_8876.coverage_boundaries.v1",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "role": "DISPLAY_ONLY_FULL_SOURCE_SUPPORT_DIAGNOSTIC_NOT_TARGET_FREEZE",
            "grid": grid,
            "mask_cleanup": cfg["grid"],
            "image_projection_contract": {
                **cfg["image_support"],
                "limitation": "FIXED_HORIZONTAL_LOCAL_Z_PLANE; NO_3D_OCCLUSION_OR_ROOF_VISIBILITY TEST",
            },
            "strict_common_definition": "CLEAN_E1_RAW_LIDAR_AND_CLEAN_E2_DENSE_MVS_AND_IMAGE_MULTIVIEW",
            "layers": layers,
            "building_coverage": building_summaries,
            "source_records": inputs,
            "target_membership_modified": False,
            "roofer_inputs_modified": False,
            "scientific_verdict": None,
        }
        atomic_json(output_path, boundary_doc)

    manifest_path = viewer / "viewer_manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["coverage_boundary_contract"] = {
        "role": boundary_doc["role"],
        "source": cfg["output_json"],
        "source_sha256": sha256(output_path),
        "default_visible": True,
        "layer_count": len(layers),
        "image_projection_limitation": boundary_doc["image_projection_contract"]["limitation"],
        "target_membership_modified": False,
        "roofer_inputs_modified": False,
        "scientific_verdict": None,
    }
    manifest["coverage_boundary_layers"] = layers
    manifest["roofer_inputs_modified"] = False
    manifest["scientific_verdict"] = None
    atomic_json(manifest_path, manifest)

    app_path = viewer / "app.js"
    app = app_path.read_text()
    app = replace_once(app, "let targetFootprintsVisible = true;", "let targetFootprintsVisible = true;\nlet coverageBoundariesVisible = true;", "coverage state")
    overlay_function = r'''
function coverageBoundaryOverlay(layers) {
  const group = new THREE.Group();
  group.name = 'full-source-coverage-boundaries-display-diagnostic';
  for (const layer of layers || []) {
    const width = Number(layer.outline_width_m || 0.85);
    const z = Number(layer.display_z_local_m || -44);
    const positions = [];
    for (const ring of layer.rings_local_xy || []) {
      for (let index = 0; index + 1 < ring.length; index++) {
        const [x0, y0] = ring[index];
        const [x1, y1] = ring[index + 1];
        const dx = x1 - x0;
        const dy = y1 - y0;
        const length = Math.hypot(dx, dy);
        if (length <= 1e-9) continue;
        const nx = -dy / length * width / 2;
        const ny = dx / length * width / 2;
        positions.push(
          x0 + nx, y0 + ny, z, x0 - nx, y0 - ny, z, x1 - nx, y1 - ny, z,
          x0 + nx, y0 + ny, z, x1 - nx, y1 - ny, z, x1 + nx, y1 + ny, z,
        );
      }
    }
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute('position', new THREE.Float32BufferAttribute(positions, 3));
    const mesh = new THREE.Mesh(geometry, new THREE.MeshBasicMaterial({
      color: layer.color,
      side: THREE.DoubleSide,
      transparent: true,
      opacity: 0.95,
      depthTest: false,
      depthWrite: false,
    }));
    mesh.renderOrder = 24;
    mesh.userData.coverageBoundary = layer;
    group.add(mesh);
  }
  return group;
}
'''
    app = replace_once(app, "\nasync function rooferPointcloud(spec) {", overlay_function + "\nasync function rooferPointcloud(spec) {", "coverage overlay function")
    app = replace_once(
        app,
        "  scene.add(targetFootprints);\n  const realCandidates",
        "  scene.add(targetFootprints);\n  const coverageBoundaries = coverageBoundaryOverlay(manifest.coverage_boundary_layers);\n  coverageBoundaries.visible = coverageBoundariesVisible;\n  scene.add(coverageBoundaries);\n  const realCandidates",
        "coverage overlay creation",
    )
    app = replace_once(
        app,
        "surface, targetFootprints, realCandidates, syntheticRegions, spec};",
        "surface, targetFootprints, coverageBoundaries, realCandidates, syntheticRegions, spec};",
        "viewer coverage member",
    )
    handler = r'''
document.getElementById('toggleCoverageBoundaries').addEventListener('click', event => {
  coverageBoundariesVisible = !coverageBoundariesVisible;
  for (const viewer of viewers) viewer.coverageBoundaries.visible = coverageBoundariesVisible;
  event.currentTarget.textContent = `관측영역 ${coverageBoundariesVisible ? 'ON' : 'OFF'}`;
  info.textContent = coverageBoundariesVisible
    ? '파랑 E1 LiDAR · 주황 영상 다중시점 · 빨강 E2 dense MVS · 초록 엄격 공통지원'
    : '원본 입력 관측영역 경계 숨김';
});
'''
    app = replace_once(
        app,
        "\ndocument.getElementById('toggleRealChanges').addEventListener",
        handler + "\ndocument.getElementById('toggleRealChanges').addEventListener",
        "coverage toggle handler",
    )
    app = replace_once(
        app,
        "document.getElementById('toggleTargetFootprints').textContent = `대상72 footprint ${targetFootprintsVisible ? 'ON' : 'OFF'}`;",
        "document.getElementById('toggleTargetFootprints').textContent = `대상72 footprint ${targetFootprintsVisible ? 'ON' : 'OFF'}`;\ndocument.getElementById('toggleCoverageBoundaries').textContent = `관측영역 ${coverageBoundariesVisible ? 'ON' : 'OFF'}`;",
        "coverage initial button text",
    )
    app = replace_once(
        app,
        "'표면 mesh 로드 완료 · image/LiDAR 공통 대상 E_paired 72동 footprint ON'",
        "'표면 mesh 로드 완료 · full-source 불규칙 관측영역 4종 ON · 대상 membership 미변경'",
        "surface initial status",
    )
    app = replace_once(
        app,
        "'8개 패널 로드 완료 · image/LiDAR 공통 대상 E_paired 72동 footprint ON'",
        "'8개 패널 로드 완료 · full-source 불규칙 관측영역 4종 ON · 대상 membership 미변경'",
        "default initial status",
    )
    atomic_text(app_path, app)

    index_path = viewer / "index.html"
    index = index_path.read_text()
    index = replace_once(
        index,
        '<button id="toggleTargetFootprints" type="button">대상72 footprint ON</button>',
        '<button id="toggleTargetFootprints" type="button">대상72 footprint ON</button><button id="toggleCoverageBoundaries" type="button">관측영역 ON</button>',
        "coverage button",
    )
    index = replace_once(
        index,
        '<span class="legend"><span><i style="background:#00e5ff"></i>image/LiDAR 공통 대상 72</span>',
        '<span class="legend"><span><i style="background:#3b82f6"></i>E1 LiDAR</span><span><i style="background:#f59e0b"></i>영상 3+경사1+</span><span><i style="background:#ef4444"></i>E2 dense MVS</span><span><i style="background:#22c55e"></i>엄격 공통</span><span><i style="background:#00e5ff"></i>현 표시 대상72</span>',
        "coverage legend",
    )
    index = replace_once(
        index,
        "app.js?v=e1e6-20260810-e1-lidar-fullscene-surface-v1",
        "app.js?v=e1e6-20260810-full-source-coverage-boundaries-v1",
        "app cache token",
    )
    atomic_text(index_path, index)

    after = {name: file_record(viewer / name) for name in cfg["expected_before"]}
    TASK.mkdir(parents=True)
    receipt = {
        "schema": "jointbuildgs.p2.viewer_8876_full_source_coverage_boundaries.receipt.v1",
        "task_id": cfg["task_id"],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "config": file_record(CONFIG),
        "script": file_record(SOURCE),
        "inputs": inputs,
        "coverage_boundaries": file_record(output_path, cfg["output_json"]),
        "grid": grid,
        "layer_summary": [
            {
                "id": layer["id"],
                "occupied_area_m2": layer["occupied_area_m2"],
                "ring_count": layer["ring_count"],
                **layer["building_coverage_summary"],
            }
            for layer in layers
        ],
        "viewer_before": before,
        "resumed_partial_state": resumed_partial_state,
        "viewer_after": after,
        "display_only": True,
        "target_membership_modified": False,
        "roofer_inputs_modified": False,
        "scientific_verdict": None,
    }
    atomic_json(TASK / "receipt.json", receipt)
    print(json.dumps({"task_id": cfg["task_id"], "grid": grid, "layers": receipt["layer_summary"], "viewer_after": after}, indent=2))


if __name__ == "__main__":
    main()
