#!/usr/bin/env python3
"""Build one deterministic CloudCompare scene for the full 199-building census."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
from typing import Any, Iterable, Mapping, Sequence
import xml.etree.ElementTree as ET

import laspy
import numpy as np
from shapely.geometry import MultiPolygon, Polygon
from shapely.ops import unary_union


REPO = Path(__file__).resolve().parents[3]
DEFAULT_CONFIG = REPO / "configs/p2/qualitative_199_cloudcompare_scene_v1/build_v1.json"
POINT_DTYPE = np.dtype(
    [
        ("x", "<f4"),
        ("y", "<f4"),
        ("z", "<f4"),
        ("red", "u1"),
        ("green", "u1"),
        ("blue", "u1"),
    ]
)


def canonical_json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def sha256_file(path: Path) -> tuple[int, str]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
            size += len(chunk)
    return size, digest.hexdigest()


def file_record(path: Path, root: Path) -> dict[str, Any]:
    size, digest = sha256_file(path)
    return {"path": path.relative_to(root).as_posix(), "bytes": size, "sha256": digest}


def verify_file(path: Path, spec: Mapping[str, Any], label: str) -> dict[str, Any]:
    if not path.is_file():
        raise RuntimeError(f"missing {label}: {path}")
    size = path.stat().st_size
    if size != int(spec["bytes"]):
        raise RuntimeError(f"{label} byte drift: {size} != {spec['bytes']}")
    _, digest = sha256_file(path)
    if digest != str(spec["sha256"]):
        raise RuntimeError(f"{label} hash drift: {digest} != {spec['sha256']}")
    return {"path": str(path), "bytes": size, "sha256": digest, "verification": "sha256_rehash"}


def write_new(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(data)


def load_config(path: Path) -> dict[str, Any]:
    config = json.loads(path.read_text(encoding="utf-8"))
    if config.get("schema") != "jointbuildgs.p2.qualitative_199_cloudcompare_scene.v1":
        raise RuntimeError("unexpected scene config schema")
    if config.get("status") != "USER_APPROVED_FOR_EXECUTION":
        raise RuntimeError("scene construction is not user-approved")
    if config.get("scientific_verdict", "missing") is not None:
        raise RuntimeError("scientific_verdict must remain null")
    if config["execution"].get("scientific_verdict", "missing") is not None:
        raise RuntimeError("execution scientific_verdict must remain null")
    if int(config["population"]["building_count"]) != 199:
        raise RuntimeError("population must remain exactly 199 buildings")
    if config["display"].get("roofsurface_geometry_access_allowed") is not False:
        raise RuntimeError("RoofSurface geometry must remain inaccessible")
    if float(config["inputs"]["current_uas_lidar"]["applied_vertical_shift_m"]) != 0.0:
        raise RuntimeError("current UAS LiDAR must not receive a vertical shift")
    if float(config["inputs"]["current_mvs_dense"]["applied_vertical_shift_m"]) != 0.0:
        raise RuntimeError("current MVS must not receive a vertical shift")
    return config


def resolve_artifact(artifact_root: Path, relative: str) -> Path:
    path = artifact_root / relative
    if not path.exists():
        raise RuntimeError(f"missing artifact: {path}")
    return path


def read_common_manifest(path: Path, expected_count: int) -> list[dict[str, Any]]:
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if len(rows) != expected_count:
        raise RuntimeError(f"common manifest count drift: {len(rows)} != {expected_count}")
    ids = [str(row["building_id"]) for row in rows]
    if len(set(ids)) != len(ids):
        raise RuntimeError("duplicate building ID in common manifest")
    indices = [int(row["population_index"]) for row in rows]
    if indices != list(range(1, expected_count + 1)):
        raise RuntimeError("population_index is not the frozen 1..199 order")
    return rows


def union_extent(rows: Sequence[Mapping[str, Any]], margin: float) -> list[float]:
    boxes = [tuple(map(float, row["viewport_bbox_xy"])) for row in rows]
    return [
        min(box[0] for box in boxes) - margin,
        min(box[1] for box in boxes) - margin,
        max(box[2] for box in boxes) + margin,
        max(box[3] for box in boxes) + margin,
    ]


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _element_id(element: ET.Element) -> str | None:
    for key, value in element.attrib.items():
        if key == "id" or key.endswith("}id"):
            return str(value)
    return None


def _ring_from_boundary(boundary: ET.Element) -> np.ndarray | None:
    pos_list = next((node for node in boundary.iter() if _local_name(node.tag) == "posList"), None)
    if pos_list is None or not pos_list.text:
        return None
    values = np.fromstring(pos_list.text, sep=" ", dtype=np.float64)
    dimension = int(pos_list.attrib.get("srsDimension", "3"))
    if dimension not in (2, 3) or len(values) < dimension * 3 or len(values) % dimension:
        raise RuntimeError("invalid GroundSurface GML polygon boundary")
    ring = values.reshape((-1, dimension))
    if dimension == 2:
        ring = np.column_stack((ring, np.zeros(len(ring), dtype=np.float64)))
    if not np.allclose(ring[0], ring[-1]):
        ring = np.vstack((ring, ring[0]))
    return ring


def load_groundsurface_only(paths: Sequence[Path], building_ids: Sequence[str]) -> dict[str, dict[str, Any]]:
    """Read GroundSurface only; RoofSurface and WallSurface geometry are never traversed."""

    wanted = set(map(str, building_ids))
    found: dict[str, dict[str, Any]] = {}
    for path in paths:
        remaining = wanted - set(found)
        if not remaining:
            break
        for _event, building in ET.iterparse(path, events=("end",)):
            if _local_name(building.tag) != "Building":
                continue
            stable_id = _element_id(building)
            if stable_id in remaining:
                polygons: list[Polygon] = []
                z_values: list[float] = []
                for surface in building.iter():
                    if _local_name(surface.tag) != "GroundSurface":
                        continue
                    for polygon_element in surface.iter():
                        if _local_name(polygon_element.tag) != "Polygon":
                            continue
                        exterior_node = next(
                            (node for node in polygon_element if _local_name(node.tag) == "exterior"), None
                        )
                        if exterior_node is None:
                            continue
                        exterior = _ring_from_boundary(exterior_node)
                        if exterior is None:
                            continue
                        interiors = []
                        for node in polygon_element:
                            if _local_name(node.tag) == "interior":
                                interior = _ring_from_boundary(node)
                                if interior is not None:
                                    interiors.append(interior[:, :2])
                                    z_values.extend(interior[:, 2].tolist())
                        polygon = Polygon(exterior[:, :2], interiors)
                        if not polygon.is_valid:
                            polygon = polygon.buffer(0)
                        if polygon.is_empty:
                            raise RuntimeError(f"empty GroundSurface footprint: {stable_id}")
                        polygons.append(polygon)
                        z_values.extend(exterior[:, 2].tolist())
                if not polygons or not z_values:
                    raise RuntimeError(f"GroundSurface footprint missing: {stable_id}")
                footprint = unary_union(polygons)
                if not isinstance(footprint, (Polygon, MultiPolygon)):
                    raise RuntimeError(f"unsupported footprint geometry: {stable_id} {footprint.geom_type}")
                found[str(stable_id)] = {
                    "geometry": footprint,
                    "ground_z_orthometric_m": float(np.median(np.asarray(z_values, dtype=np.float64))),
                }
            building.clear()
    missing = sorted(wanted - set(found))
    if missing:
        raise RuntimeError(f"GroundSurface references missing: {missing}")
    return found


def polygon_rings(geometry: Polygon | MultiPolygon) -> Iterable[np.ndarray]:
    polygons = list(geometry.geoms) if isinstance(geometry, MultiPolygon) else [geometry]
    for polygon in polygons:
        yield np.asarray(polygon.exterior.coords, dtype=np.float64)
        for interior in polygon.interiors:
            yield np.asarray(interior.coords, dtype=np.float64)


def read_mvs_header(path: Path) -> tuple[int, int]:
    with path.open("rb") as stream:
        lines = []
        while True:
            raw = stream.readline()
            if not raw:
                raise RuntimeError("MVS PLY is missing end_header")
            line = raw.decode("ascii").rstrip("\r\n")
            lines.append(line)
            if line == "end_header":
                break
        offset = stream.tell()
    if lines[:2] != ["ply", "format binary_little_endian 1.0"]:
        raise RuntimeError("MVS PLY format drifted")
    counts = [line for line in lines if line.startswith("element vertex ")]
    if len(counts) != 1:
        raise RuntimeError("MVS PLY vertex declaration drifted")
    properties = [line for line in lines if line.startswith("property ")]
    expected = [
        "property float32 x",
        "property float32 y",
        "property float32 z",
        "property uint8 red",
        "property uint8 green",
        "property uint8 blue",
    ]
    if properties != expected:
        raise RuntimeError("MVS PLY property contract drifted")
    count = int(counts[0].split()[-1])
    if path.stat().st_size != offset + count * POINT_DTYPE.itemsize:
        raise RuntimeError("MVS PLY byte count is inconsistent with its header")
    return offset, count


def crop_mvs_to_local_ply(
    source: Path,
    output: Path,
    extent_world: Sequence[float],
    dense_shift: np.ndarray,
    scene_origin: np.ndarray,
    chunk_points: int,
) -> dict[str, Any]:
    offset, count = read_mvs_header(source)
    points = np.memmap(source, mode="r", dtype=POINT_DTYPE, offset=offset, shape=(count,))
    local_min_x = float(extent_world[0]) - dense_shift[0]
    local_min_y = float(extent_world[1]) - dense_shift[1]
    local_max_x = float(extent_world[2]) - dense_shift[0]
    local_max_y = float(extent_world[3]) - dense_shift[1]
    selected_count = 0
    input_finite_count = 0
    for start in range(0, count, chunk_points):
        chunk = points[start : min(start + chunk_points, count)]
        finite = np.isfinite(chunk["x"]) & np.isfinite(chunk["y"]) & np.isfinite(chunk["z"])
        inside = finite & (chunk["x"] >= local_min_x) & (chunk["x"] <= local_max_x)
        inside &= (chunk["y"] >= local_min_y) & (chunk["y"] <= local_max_y)
        input_finite_count += int(np.count_nonzero(finite))
        selected_count += int(np.count_nonzero(inside))
    header = (
        "ply\n"
        "format binary_little_endian 1.0\n"
        "comment JointBuildGS CloudCompare display layer\n"
        "comment coordinates are scene-local; see scene_manifest.json\n"
        f"element vertex {selected_count}\n"
        "property float32 x\n"
        "property float32 y\n"
        "property float32 z\n"
        "property uint8 red\n"
        "property uint8 green\n"
        "property uint8 blue\n"
        "end_header\n"
    ).encode("ascii")
    output.parent.mkdir(parents=True, exist_ok=True)
    bounds_min = np.full(3, np.inf, dtype=np.float64)
    bounds_max = np.full(3, -np.inf, dtype=np.float64)
    written = 0
    with output.open("xb") as stream:
        stream.write(header)
        for start in range(0, count, chunk_points):
            chunk = points[start : min(start + chunk_points, count)]
            finite = np.isfinite(chunk["x"]) & np.isfinite(chunk["y"]) & np.isfinite(chunk["z"])
            inside = finite & (chunk["x"] >= local_min_x) & (chunk["x"] <= local_max_x)
            inside &= (chunk["y"] >= local_min_y) & (chunk["y"] <= local_max_y)
            if not np.any(inside):
                continue
            selected = np.array(chunk[inside], dtype=POINT_DTYPE, copy=True)
            selected["x"] += np.float32(dense_shift[0] - scene_origin[0])
            selected["y"] += np.float32(dense_shift[1] - scene_origin[1])
            selected["z"] += np.float32(dense_shift[2] - scene_origin[2])
            xyz = np.column_stack((selected["x"], selected["y"], selected["z"])).astype(np.float64)
            bounds_min = np.minimum(bounds_min, xyz.min(axis=0))
            bounds_max = np.maximum(bounds_max, xyz.max(axis=0))
            stream.write(selected.tobytes(order="C"))
            written += len(selected)
    if written != selected_count:
        raise RuntimeError(f"MVS output count drift: {written} != {selected_count}")
    return {
        "source_point_count": count,
        "source_finite_point_count": input_finite_count,
        "output_point_count": written,
        "local_bounds_xyz": [bounds_min.tolist(), bounds_max.tolist()] if written else None,
        "rgb_preserved": True,
    }


def crop_lidar_to_local_laz(
    source: Path,
    output: Path,
    extent_world: Sequence[float],
    scene_origin: np.ndarray,
    chunk_points: int,
) -> dict[str, Any]:
    output.parent.mkdir(parents=True, exist_ok=True)
    selected_count = 0
    bounds_min = np.full(3, np.inf, dtype=np.float64)
    bounds_max = np.full(3, -np.inf, dtype=np.float64)
    with laspy.open(source) as reader:
        source_count = int(reader.header.point_count)
        output_header = laspy.LasHeader(point_format=reader.header.point_format, version=reader.header.version)
        output_header.scales = np.asarray(reader.header.scales, dtype=np.float64)
        output_header.offsets = np.zeros(3, dtype=np.float64)
        output_header.system_identifier = "JBGS LOCAL DISPLAY"
        output_header.generating_software = "JointBuildGS"
        with laspy.open(output, mode="w", header=output_header, do_compress=True) as writer:
            for chunk in reader.chunk_iterator(chunk_points):
                x = np.asarray(chunk.x, dtype=np.float64)
                y = np.asarray(chunk.y, dtype=np.float64)
                keep = (x >= float(extent_world[0])) & (x <= float(extent_world[2]))
                keep &= (y >= float(extent_world[1])) & (y <= float(extent_world[3]))
                if not np.any(keep):
                    continue
                selected = chunk[keep]
                local_xyz = np.column_stack(
                    (
                        np.asarray(selected.x, dtype=np.float64) - scene_origin[0],
                        np.asarray(selected.y, dtype=np.float64) - scene_origin[1],
                        np.asarray(selected.z, dtype=np.float64) - scene_origin[2],
                    )
                )
                output_points = laspy.ScaleAwarePointRecord(
                    selected.array.copy(), output_header.point_format, output_header.scales, output_header.offsets
                )
                output_points.x, output_points.y, output_points.z = local_xyz.T
                writer.write_points(output_points)
                selected_count += len(output_points)
                bounds_min = np.minimum(bounds_min, local_xyz.min(axis=0))
                bounds_max = np.maximum(bounds_max, local_xyz.max(axis=0))
    with laspy.open(output) as check:
        if int(check.header.point_count) != selected_count:
            raise RuntimeError("LiDAR output header point count drift")
        dimensions = list(check.header.point_format.dimension_names)
    return {
        "source_point_count": source_count,
        "output_point_count": selected_count,
        "local_bounds_xyz": [bounds_min.tolist(), bounds_max.tolist()] if selected_count else None,
        "point_dimensions_preserved": dimensions,
        "rgb_preserved": all(name in dimensions for name in ("red", "green", "blue")),
        "source_crs_removed_because_coordinates_are_scene_local": True,
    }


def dxf_polyline(layer: str, coordinates: np.ndarray, z: float, color_index: int = 30) -> list[str]:
    lines = ["0", "POLYLINE", "8", layer, "62", str(color_index), "66", "1", "70", "9"]
    for x, y in coordinates[:-1] if np.allclose(coordinates[0], coordinates[-1]) else coordinates:
        lines.extend(["0", "VERTEX", "8", layer, "10", f"{x:.6f}", "20", f"{y:.6f}", "30", f"{z:.6f}", "70", "32"])
    lines.extend(["0", "SEQEND", "8", layer])
    return lines


def dxf_tables(layer_names: Sequence[str], color_index: int = 30) -> list[str]:
    """Declare every entity layer so DXF readers can retain its building name."""

    names = list(map(str, layer_names))
    if len(names) != len(set(names)):
        raise RuntimeError("DXF layer names must be unique")
    if any(not name or any(character in name for character in "<>/\\\":;?*|=,") for name in names):
        raise RuntimeError("DXF layer name contains an unsupported character")
    lines = [
        "0", "SECTION", "2", "TABLES",
        "0", "TABLE", "2", "LTYPE", "70", "1",
        "0", "LTYPE", "2", "CONTINUOUS", "70", "0", "3", "Solid line", "72", "65", "73", "0", "40", "0.0",
        "0", "ENDTAB",
        "0", "TABLE", "2", "LAYER", "70", str(len(names) + 1),
        "0", "LAYER", "2", "0", "70", "0", "62", "7", "6", "CONTINUOUS",
    ]
    for name in names:
        lines.extend(["0", "LAYER", "2", name, "70", "0", "62", str(color_index), "6", "CONTINUOUS"])
    lines.extend(["0", "ENDTAB", "0", "ENDSEC"])
    return lines


def write_footprint_dxf(
    output: Path,
    rows: Sequence[Mapping[str, Any]],
    references: Mapping[str, Mapping[str, Any]],
    scene_origin: np.ndarray,
    geoid_m: float,
) -> dict[str, Any]:
    layer_names = [f"B{int(row['population_index']):03d}_{row['building_id']}" for row in rows]
    lines = ["0", "SECTION", "2", "HEADER", "9", "$ACADVER", "1", "AC1009", "0", "ENDSEC"]
    lines.extend(dxf_tables(layer_names))
    lines.extend(["0", "SECTION", "2", "ENTITIES"])
    ring_count = 0
    vertex_count = 0
    index_rows = []
    for row in rows:
        index = int(row["population_index"])
        building_id = str(row["building_id"])
        reference = references[building_id]
        z = float(reference["ground_z_orthometric_m"]) + geoid_m - scene_origin[2]
        layer = layer_names[len(index_rows)]
        building_rings = 0
        building_vertices = 0
        for ring in polygon_rings(reference["geometry"]):
            local_xy = ring[:, :2] - scene_origin[:2]
            lines.extend(dxf_polyline(layer, local_xy, z))
            ring_count += 1
            building_rings += 1
            count = len(local_xy) - int(np.allclose(local_xy[0], local_xy[-1]))
            vertex_count += count
            building_vertices += count
        index_rows.append(
            {
                "population_index": index,
                "building_id": building_id,
                "dxf_layer": layer,
                "ring_count": building_rings,
                "vertex_count": building_vertices,
                "ground_z_scene_local_m": z,
            }
        )
    lines.extend(["0", "ENDSEC", "0", "EOF"])
    write_new(output, ("\n".join(lines) + "\n").encode("ascii"))
    return {"building_count": len(rows), "ring_count": ring_count, "vertex_count": vertex_count, "building_index": index_rows}


def write_curtain_ply(
    output: Path,
    rows: Sequence[Mapping[str, Any]],
    references: Mapping[str, Mapping[str, Any]],
    scene_origin: np.ndarray,
    geoid_m: float,
    height_m: float,
    rgb: Sequence[int],
) -> dict[str, Any]:
    vertex_rows: list[tuple[float, float, float, int, int, int, int]] = []
    face_rows: list[tuple[int, int, int, int, int]] = []
    ring_count = 0
    for row in rows:
        index = int(row["population_index"])
        building_id = str(row["building_id"])
        reference = references[building_id]
        base_z = float(reference["ground_z_orthometric_m"]) + geoid_m - scene_origin[2]
        for ring in polygon_rings(reference["geometry"]):
            closed = ring if np.allclose(ring[0], ring[-1]) else np.vstack((ring, ring[0]))
            coordinates = closed[:-1, :2] - scene_origin[:2]
            if len(coordinates) < 3:
                raise RuntimeError(f"degenerate footprint ring: {building_id}")
            start = len(vertex_rows)
            for x, y in coordinates:
                vertex_rows.append((x, y, base_z, int(rgb[0]), int(rgb[1]), int(rgb[2]), index))
                vertex_rows.append((x, y, base_z + height_m, int(rgb[0]), int(rgb[1]), int(rgb[2]), index))
            for vertex_index in range(len(coordinates)):
                next_index = (vertex_index + 1) % len(coordinates)
                lower_a = start + 2 * vertex_index
                upper_a = lower_a + 1
                lower_b = start + 2 * next_index
                upper_b = lower_b + 1
                face_rows.append((lower_a, lower_b, upper_b, index, 3))
                face_rows.append((lower_a, upper_b, upper_a, index, 3))
            ring_count += 1
    vertex_dtype = np.dtype(
        [("x", "<f4"), ("y", "<f4"), ("z", "<f4"), ("red", "u1"), ("green", "u1"), ("blue", "u1"), ("building_index", "<u2")]
    )
    face_dtype = np.dtype([("count", "u1"), ("v0", "<i4"), ("v1", "<i4"), ("v2", "<i4"), ("building_index", "<u2")])
    vertices = np.empty(len(vertex_rows), dtype=vertex_dtype)
    for i, item in enumerate(vertex_rows):
        vertices[i] = item
    faces = np.empty(len(face_rows), dtype=face_dtype)
    for i, (v0, v1, v2, index, count) in enumerate(face_rows):
        faces[i] = (count, v0, v1, v2, index)
    header = (
        "ply\n"
        "format binary_little_endian 1.0\n"
        "comment JointBuildGS display-only constant-height footprint curtains\n"
        f"element vertex {len(vertices)}\n"
        "property float x\nproperty float y\nproperty float z\n"
        "property uchar red\nproperty uchar green\nproperty uchar blue\n"
        "property ushort building_index\n"
        f"element face {len(faces)}\n"
        "property list uchar int vertex_indices\n"
        "property ushort building_index\n"
        "end_header\n"
    ).encode("ascii")
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("xb") as stream:
        stream.write(header)
        stream.write(vertices.tobytes(order="C"))
        stream.write(faces.tobytes(order="C"))
    return {
        "building_count": len(rows),
        "ring_count": ring_count,
        "vertex_count": len(vertices),
        "triangle_count": len(faces),
        "constant_height_m": height_m,
        "rgb": list(map(int, rgb)),
    }


def git_value(*args: str) -> str:
    process = subprocess.run(["git", *args], cwd=REPO, text=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    return process.stdout.strip() if process.returncode == 0 else "UNKNOWN"


def build_scene(config_path: Path, artifact_root: Path, output_root: Path | None = None) -> Path:
    config = load_config(config_path)
    destination = output_root or artifact_root / str(config["output_relative_root"])
    if destination.exists():
        raise RuntimeError(f"refusing to overwrite existing scene: {destination}")
    partial = destination.with_name(destination.name + ".partial")
    if partial.exists():
        raise RuntimeError(f"partial scene already exists and requires review: {partial}")
    partial.mkdir(parents=True)
    try:
        common_spec = config["population"]
        common_path = resolve_artifact(artifact_root, str(common_spec["common_manifest_relative_path"]))
        common_file_spec = {
            "bytes": common_spec["common_manifest_bytes"],
            "sha256": common_spec["common_manifest_sha256"],
        }
        source_records = {"common_manifest": verify_file(common_path, common_file_spec, "common manifest")}
        rows = read_common_manifest(common_path, int(common_spec["building_count"]))
        extent = union_extent(rows, float(config["extent"]["additional_margin_m"]))
        scene_origin = np.asarray(config["frame"]["scene_local_origin_xyz"], dtype=np.float64)
        dense_shift = np.asarray(config["frame"]["dense_world_shift_xyz"], dtype=np.float64)

        lidar_spec = config["inputs"]["current_uas_lidar"]
        lidar_source = resolve_artifact(artifact_root, str(lidar_spec["relative_path"]))
        source_records["current_uas_lidar"] = verify_file(lidar_source, lidar_spec, "current UAS LiDAR")
        mvs_spec = config["inputs"]["current_mvs_dense"]
        mvs_source = resolve_artifact(artifact_root, str(mvs_spec["relative_path"]))
        source_records["current_mvs_dense"] = verify_file(mvs_source, mvs_spec, "current MVS dense")
        lod2_paths = []
        for index, spec in enumerate(config["inputs"]["lod2_groundsurface"], start=1):
            path = resolve_artifact(artifact_root, str(spec["relative_path"]))
            source_records[f"lod2_groundsurface_{index}"] = verify_file(path, spec, f"LoD2 GroundSurface source {index}")
            lod2_paths.append(path)

        building_ids = [str(row["building_id"]) for row in rows]
        references = load_groundsurface_only(lod2_paths, building_ids)
        layers = partial / "layers"
        lidar_output = layers / "lidar_199_extent_local.laz"
        mvs_output = layers / "mvs_199_extent_local_rgb.ply"
        footprint_output = layers / "footprints_199_local.dxf"
        curtain_output = layers / "footprint_curtains_199_local.ply"
        lidar_stats = crop_lidar_to_local_laz(
            lidar_source,
            lidar_output,
            extent,
            scene_origin,
            int(config["execution"]["lidar_chunk_points"]),
        )
        if int(lidar_stats["source_point_count"]) != int(lidar_spec["point_count"]):
            raise RuntimeError("LiDAR source point count drift")
        mvs_stats = crop_mvs_to_local_ply(
            mvs_source,
            mvs_output,
            extent,
            dense_shift,
            scene_origin,
            int(config["execution"]["mvs_chunk_points"]),
        )
        if int(mvs_stats["source_point_count"]) != int(mvs_spec["point_count"]):
            raise RuntimeError("MVS source point count drift")
        geoid_m = float(config["frame"]["lod2_groundsurface_orthometric_to_current_ellipsoidal_m"])
        footprint_stats = write_footprint_dxf(footprint_output, rows, references, scene_origin, geoid_m)
        curtain_stats = write_curtain_ply(
            curtain_output,
            rows,
            references,
            scene_origin,
            geoid_m,
            float(config["display"]["footprint_curtain_height_m"]),
            config["display"]["footprint_rgb"],
        )

        index_path = partial / "control/building_index_v1.csv"
        index_lines = ["population_index,building_id,dxf_layer,ring_count,vertex_count,ground_z_scene_local_m"]
        for row in footprint_stats.pop("building_index"):
            index_lines.append(
                f"{row['population_index']},{row['building_id']},{row['dxf_layer']},{row['ring_count']},{row['vertex_count']},{row['ground_z_scene_local_m']:.6f}"
            )
        write_new(index_path, ("\n".join(index_lines) + "\n").encode("utf-8"))

        layer_records = {
            "current_uas_lidar": {**file_record(lidar_output, partial), **lidar_stats},
            "current_mvs_dense": {**file_record(mvs_output, partial), **mvs_stats},
            "footprints": {**file_record(footprint_output, partial), **footprint_stats},
            "footprint_curtains": {**file_record(curtain_output, partial), **curtain_stats},
        }
        scene_manifest = {
            "schema": "jointbuildgs.p2.qualitative_199_cloudcompare_scene.manifest.v1",
            "task_id": config["task_id"],
            "decision_id": config["decision_id"],
            "status": "COMPLETE_TECHNICAL_DISPLAY_BUNDLE",
            "population": {"name": "U_target", "building_count": len(rows)},
            "extent_world_xy": extent,
            "extent_scene_local_xy": [extent[0] - scene_origin[0], extent[1] - scene_origin[1], extent[2] - scene_origin[0], extent[3] - scene_origin[1]],
            "frame": config["frame"],
            "source_records": source_records,
            "layers": layer_records,
            "display_policy": config["display"],
            "gt_separation": {
                "GroundSurface_XY_and_Z": "EVALUATION_ONLY_DISPLAY",
                "RoofSurface_geometry_accessed": False,
                "used_for_point_cloud_crop": False,
                "used_for_reconstruction_or_Roofer": False,
            },
            "next_stage_authorized": False,
            "scientific_verdict": None,
        }
        scene_manifest_path = partial / "scene_manifest.json"
        write_new(scene_manifest_path, canonical_json_bytes(scene_manifest))
        readme = f"""JointBuildGS 199-building CloudCompare scene v1

Load these files together from the layers directory:
1. lidar_199_extent_local.laz
2. mvs_199_extent_local_rgb.ply
3. footprints_199_local.dxf
4. footprint_curtains_199_local.ply

All coordinates are already in the same scene-local frame. Do not apply an additional
Global Shift when CloudCompare asks; the coordinate magnitudes are intentionally small.

World reconstruction:
  p_world_EPSG25832_ellipsoidal = p_scene_local + {scene_origin.tolist()}

Current UAS LiDAR vertical shift: 0.0 m
Current MVS vertical shift: 0.0 m
LoD2 GroundSurface display conversion: orthometric + {geoid_m:.1f} m
Footprint curtains: constant {float(config['display']['footprint_curtain_height_m']):.1f} m display extrusion; no RoofSurface geometry used.

The footprints and curtains are evaluation-only display layers. They are not inputs to
MVS, reconstruction, Roofer, camera selection, or crop selection.
See scene_manifest.json and control/building_index_v1.csv for provenance and ID mapping.
"""
        readme_path = partial / "README.txt"
        write_new(readme_path, readme.encode("utf-8"))
        receipt = {
            "schema": "jointbuildgs.p2.qualitative_199_cloudcompare_scene.run_receipt.v1",
            "task_id": config["task_id"],
            "started_or_completed_at_utc": datetime.now(timezone.utc).isoformat(),
            "git_commit": git_value("rev-parse", "HEAD"),
            "git_status_porcelain": git_value("status", "--porcelain"),
            "config": file_record(config_path, REPO),
            "script": file_record(Path(__file__).resolve(), REPO),
            "docker_image": os.environ.get("JBGS_DOCKER_IMAGE", "jointbuildgs:dev"),
            "reconstruction_invocations": 0,
            "roofer_invocations": 0,
            "gs_training_invocations": 0,
            "scientific_verdict": None,
        }
        receipt_path = partial / "control/run_receipt_v1.json"
        write_new(receipt_path, canonical_json_bytes(receipt))
        artifact_manifest = {
            "schema": "jointbuildgs.p2.qualitative_199_cloudcompare_scene.artifact_manifest.v1",
            "task_id": config["task_id"],
            "records": [
                file_record(path, partial)
                for path in (lidar_output, mvs_output, footprint_output, curtain_output, index_path, scene_manifest_path, readme_path, receipt_path)
            ],
            "scientific_verdict": None,
        }
        write_new(partial / "control/artifact_manifest_v1.json", canonical_json_bytes(artifact_manifest))
        destination.parent.mkdir(parents=True, exist_ok=True)
        partial.rename(destination)
        return destination
    except Exception:
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--artifact-root", type=Path, default=Path(os.environ.get("JBGS_ARTIFACT_ROOT", "../JointBuildGS-artifacts")))
    parser.add_argument("--output-root", type=Path)
    args = parser.parse_args()
    output = build_scene(args.config.resolve(), args.artifact_root.resolve(), args.output_root.resolve() if args.output_root else None)
    print(output)


if __name__ == "__main__":
    main()
