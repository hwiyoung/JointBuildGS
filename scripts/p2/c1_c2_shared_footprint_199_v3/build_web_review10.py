#!/usr/bin/env python3
"""Package the frozen 199-building C1/C2 assets into an offline 3D web reviewer."""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
from typing import Any, Mapping

import laspy
import numpy as np
from shapely.geometry import shape

from scripts.p2.c1_c2_shared_footprint_199_v3.build_cloudcompare_review10 import (
    bbox_for_feature,
    curtain_obj,
    display_z,
    footprint_line_obj,
    lod22_triangles,
    material_text,
    polygon_rings,
    triangles_obj,
)
from scripts.p2.c1_c2_shared_footprint_199_v3.verify_frozen_replay import verify
from scripts.p2.qualitative_199_cloudcompare_scene_v1.build_scene import (
    REPO,
    canonical_json_bytes,
    file_record,
    sha256_file,
    write_new,
)


DEFAULT_CONFIG = REPO / "configs/p2/c1_c2_shared_footprint_199_v3/web_review10_v1.json"
EXPECTED_SCHEMA = "jointbuildgs.p2.c1_c2_original_global_v3.web_review199.v1"


def load_config(path: Path) -> dict[str, Any]:
    config = json.loads(path.read_text(encoding="utf-8"))
    if config.get("schema") != EXPECTED_SCHEMA or config.get("status") != "USER_APPROVED_FOR_EXECUTION":
        raise RuntimeError("web review199 config is not approved")
    if config.get("scientific_verdict", "missing") is not None:
        raise RuntimeError("scientific_verdict must remain null")
    execution = config.get("execution", {})
    if any(int(execution.get(key, -1)) != 0 for key in ("roofer_invocations", "reconstruction_invocations", "gs_training_invocations", "metric_recomputations")):
        raise RuntimeError("web packaging must not execute scientific processing")
    if int(config["features"]["building_count"]) != 199:
        raise RuntimeError("web reviewer building count drift")
    if config["features"].get("review_labels") != ["", "O", "X"]:
        raise RuntimeError("human review labels must remain blank/O/X")
    if config["features"].get("review_input_ui") != "TWO_TOGGLE_BUTTONS_O_X":
        raise RuntimeError("human review input must remain O/X toggle buttons")
    if not config["features"].get("whole_scene_overview") or int(config["features"].get("overview_building_count", -1)) != 199:
        raise RuntimeError("whole-scene overview contract drift")
    if config["features"].get("detail_overview_minimap") != "TOP_VIEW_199_BUILDINGS_WITH_POINT_AVAILABILITY":
        raise RuntimeError("detail overview minimap contract drift")
    point_display = config.get("point_display", {})
    if float(point_display.get("detail_voxel_size_m", -1)) != 0.2 or float(point_display.get("overview_voxel_size_m", -1)) != 1.0:
        raise RuntimeError("deterministic display voxel contract drift")
    if float(point_display.get("default_point_size_px", -1)) != 3.5:
        raise RuntimeError("default point size drift")
    if point_display.get("rgb_divisor") != {"C1_L_upper": 256, "C2_MVS": 1}:
        raise RuntimeError("fixed RGB normalization drift")
    if float(point_display.get("detail_spatial_index_tile_m", -1)) != 32.0:
        raise RuntimeError("detail spatial index contract drift")
    mesh_display = config.get("mesh_display", {})
    if mesh_display.get("C1_L_upper_rgb") != [25, 220, 100] or mesh_display.get("C2_MVS_rgb") != [230, 45, 210]:
        raise RuntimeError("Roofer display color drift")
    return config


def verify_record(root: Path, record: Mapping[str, Any]) -> Path:
    relative = Path(str(record["path"]))
    if relative.is_absolute() or ".." in relative.parts:
        raise RuntimeError(f"unsafe source record: {relative}")
    path = root / relative
    if not path.is_file() or path.is_symlink():
        raise RuntimeError(f"missing source record: {relative}")
    size, digest = sha256_file(path)
    if size != int(record["bytes"]) or digest != str(record["sha256"]):
        raise RuntimeError(f"source record drift: {relative}")
    return path


def copy_new(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        raise RuntimeError(f"refuse overwrite: {destination}")
    shutil.copyfile(source, destination)


def status_table(path: Path) -> dict[str, dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    return {row["stable_id"]: row for row in rows}


def named_record(records: Mapping[str, Path], prefix: str, suffix: str) -> Path | None:
    matches = [path for name, path in records.items() if Path(name).name.startswith(prefix) and Path(name).name.endswith(suffix)]
    if len(matches) > 1:
        raise RuntimeError(f"ambiguous asset {prefix}*{suffix}")
    return matches[0] if matches else None


def deterministic_voxel_rows(
    xyz: np.ndarray,
    classification: np.ndarray,
    rgb: np.ndarray,
    voxel_size: float,
    seen: set[tuple[int, int, int]],
) -> np.ndarray:
    if not len(xyz):
        return np.empty((0, 7), dtype=np.float64)
    keys = np.floor(xyz / voxel_size).astype(np.int64)
    _, first = np.unique(keys, axis=0, return_index=True)
    kept: list[int] = []
    for position in np.sort(first):
        key = tuple(int(value) for value in keys[position])
        if key in seen:
            continue
        seen.add(key)
        kept.append(int(position))
    if not kept:
        return np.empty((0, 7), dtype=np.float64)
    indices = np.asarray(kept, dtype=np.int64)
    return np.column_stack((xyz[indices], classification[indices], rgb[indices])).astype(np.float64, copy=False)


def sample_rgb_points(
    path: Path,
    bboxes: Mapping[str, tuple[float, float, float, float]],
    detail_voxel_size: float,
    overview_voxel_size: float,
    included_classes: set[int],
    rgb_divisor: int,
    spatial_index_tile_m: float,
) -> tuple[dict[str, np.ndarray], np.ndarray]:
    """Sample overview and per-building crops without changing input-order voxel selection."""
    detail_seen = {stable_id: set() for stable_id in bboxes}
    detail_chunks: dict[str, list[np.ndarray]] = {stable_id: [] for stable_id in bboxes}
    overview_seen: set[tuple[int, int, int]] = set()
    overview_chunks: list[np.ndarray] = []
    tile_to_ids: dict[tuple[int, int], list[str]] = {}
    for stable_id, (minx, miny, maxx, maxy) in bboxes.items():
        tile_minx, tile_miny = np.floor([minx / spatial_index_tile_m, miny / spatial_index_tile_m]).astype(np.int64)
        tile_maxx, tile_maxy = np.floor([maxx / spatial_index_tile_m, maxy / spatial_index_tile_m]).astype(np.int64)
        for tile_x in range(int(tile_minx), int(tile_maxx) + 1):
            for tile_y in range(int(tile_miny), int(tile_maxy) + 1):
                tile_to_ids.setdefault((tile_x, tile_y), []).append(stable_id)
    with laspy.open(path) as reader:
        dimensions = set(reader.header.point_format.dimension_names)
        if not {"red", "green", "blue", "classification"}.issubset(dimensions):
            raise RuntimeError(f"RGB/classification dimensions are missing: {path}")
        for points in reader.chunk_iterator(2_000_000):
            classification = np.asarray(points.classification, dtype=np.uint8)
            mask = np.isin(classification, np.asarray(sorted(included_classes), dtype=np.uint8))
            if not np.any(mask):
                continue
            xyz = np.column_stack((np.asarray(points.x)[mask], np.asarray(points.y)[mask], np.asarray(points.z)[mask])).astype(np.float64)
            selected_class = classification[mask]
            raw_rgb = np.column_stack((np.asarray(points.red)[mask], np.asarray(points.green)[mask], np.asarray(points.blue)[mask])).astype(np.uint32)
            rgb = np.clip(raw_rgb // rgb_divisor, 0, 255).astype(np.uint8)
            overview_rows = deterministic_voxel_rows(xyz, selected_class, rgb, overview_voxel_size, overview_seen)
            if len(overview_rows):
                overview_chunks.append(overview_rows)

            tile_xy = np.floor(xyz[:, :2] / spatial_index_tile_m).astype(np.int64)
            order = np.lexsort((tile_xy[:, 1], tile_xy[:, 0]))
            sorted_tiles = tile_xy[order]
            boundaries = np.flatnonzero(np.any(sorted_tiles[1:] != sorted_tiles[:-1], axis=1)) + 1
            candidate_indices: dict[str, list[np.ndarray]] = {}
            for positions in np.split(order, boundaries):
                if not len(positions):
                    continue
                tile = tuple(int(value) for value in tile_xy[positions[0]])
                for stable_id in tile_to_ids.get(tile, ()):
                    candidate_indices.setdefault(stable_id, []).append(positions)
            for stable_id, parts in candidate_indices.items():
                indices = np.sort(np.concatenate(parts))
                minx, miny, maxx, maxy = bboxes[stable_id]
                candidate_xyz = xyz[indices]
                local = (
                    (candidate_xyz[:, 0] >= minx) & (candidate_xyz[:, 0] <= maxx)
                    & (candidate_xyz[:, 1] >= miny) & (candidate_xyz[:, 1] <= maxy)
                )
                if not np.any(local):
                    continue
                selected = indices[local]
                rows = deterministic_voxel_rows(
                    xyz[selected], selected_class[selected], rgb[selected], detail_voxel_size, detail_seen[stable_id]
                )
                if len(rows):
                    detail_chunks[stable_id].append(rows)
    detail = {
        stable_id: np.concatenate(chunks, axis=0) if chunks else np.empty((0, 7), dtype=np.float64)
        for stable_id, chunks in detail_chunks.items()
    }
    overview = np.concatenate(overview_chunks, axis=0) if overview_chunks else np.empty((0, 7), dtype=np.float64)
    return detail, overview


def write_rgb_class_ply(path: Path, rows: np.ndarray, origin: np.ndarray, comment: str) -> None:
    dtype = np.dtype([
        ("x", "<f4"), ("y", "<f4"), ("z", "<f4"),
        ("red", "u1"), ("green", "u1"), ("blue", "u1"), ("classification", "u1"),
    ])
    body = np.empty(len(rows), dtype=dtype)
    if len(rows):
        xyz = rows[:, :3] - origin
        body["x"], body["y"], body["z"] = xyz[:, 0], xyz[:, 1], xyz[:, 2]
        body["red"], body["green"], body["blue"] = rows[:, 4].astype(np.uint8), rows[:, 5].astype(np.uint8), rows[:, 6].astype(np.uint8)
        body["classification"] = rows[:, 3].astype(np.uint8)
    header = (
        "ply\nformat binary_little_endian 1.0\n"
        f"comment {comment}\n"
        f"element vertex {len(rows)}\n"
        "property float x\nproperty float y\nproperty float z\n"
        "property uchar red\nproperty uchar green\nproperty uchar blue\n"
        "property uchar classification\nend_header\n"
    ).encode("ascii")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(header)
        stream.write(body.tobytes())


def source_ply_count(path: Path) -> int:
    with path.open("rb") as stream:
        header = stream.read(2048).split(b"end_header\n", 1)[0].decode("ascii")
    for line in header.splitlines():
        if line.startswith("element vertex "):
            return int(line.split()[-1])
    raise RuntimeError(f"PLY vertex count is missing: {path}")


def all_footprints(path: Path) -> list[dict[str, Any]]:
    features = json.loads(path.read_text(encoding="utf-8")).get("features", [])
    ordered = sorted(features, key=lambda feature: int(feature["properties"]["population_index"]))
    if len(ordered) != 199 or [int(feature["properties"]["population_index"]) for feature in ordered] != list(range(1, 200)):
        raise RuntimeError("overview footprint population drift")
    return ordered


def footprint_support_z(rows: np.ndarray, bbox: tuple[float, float, float, float]) -> float | None:
    if not len(rows):
        return None
    minx, miny, maxx, maxy = bbox
    mask = (
        (rows[:, 0] >= minx) & (rows[:, 0] <= maxx)
        & (rows[:, 1] >= miny) & (rows[:, 1] <= maxy)
        & (rows[:, 3] == 6)
    )
    values = rows[mask, 2]
    return float(np.percentile(values, 75)) if len(values) else None


def footprint_any_z(rows: np.ndarray, bbox: tuple[float, float, float, float]) -> float | None:
    if not len(rows):
        return None
    minx, miny, maxx, maxy = bbox
    mask = (
        (rows[:, 0] >= minx) & (rows[:, 0] <= maxx)
        & (rows[:, 1] >= miny) & (rows[:, 1] <= maxy)
    )
    values = rows[mask, 2]
    return float(np.percentile(values, 75)) if len(values) else None


def overview_footprint_obj(features: list[dict[str, Any]], z_by_id: Mapping[str, float], origin: np.ndarray) -> bytes:
    lines = ["# 199 shared footprint outlines at display-only roof focus Z"]
    offset = 1
    for feature in features:
        stable_id = str(feature["properties"]["stable_id"])
        lines.extend((f"o B_{stable_id}", f"g B_{stable_id}"))
        for ring in polygon_rings(feature):
            for xy in ring:
                xyz = np.asarray([xy[0], xy[1], z_by_id[stable_id]], dtype=np.float64) - origin
                lines.append(f"v {xyz[0]:.6f} {xyz[1]:.6f} {xyz[2]:.6f}")
            indices = list(range(offset, offset + len(ring))) + [offset]
            lines.append("l " + " ".join(map(str, indices)))
            offset += len(ring)
    return ("\n".join(lines) + "\n").encode("ascii")


def build(config_path: Path, artifact_root: Path, output_root: Path) -> Path:
    config = load_config(config_path)
    if output_root.exists() and any(output_root.iterdir()):
        raise RuntimeError("fresh add-once web review199 output root required")
    output_root.mkdir(parents=True, exist_ok=True)
    source_spec = config["source"]
    source_root = artifact_root / source_spec["relative_root"]
    source_manifest_path = source_root / source_spec["manifest_path"]
    source_size, source_hash = sha256_file(source_manifest_path)
    if source_size != int(source_spec["manifest_bytes"]) or source_hash != source_spec["manifest_sha256"]:
        raise RuntimeError("CloudCompare review10 source manifest drift")
    source_manifest = json.loads(source_manifest_path.read_text(encoding="utf-8"))
    if source_manifest.get("status") != source_spec["required_status"]:
        raise RuntimeError("CloudCompare review10 source status drift")
    if source_manifest.get("frozen_verification", {}).get("status") != "EXACT_FROZEN_REPLAY_VERIFIED":
        raise RuntimeError("web source is not bound to the exact frozen replay")

    freeze_spec = config["frozen_replay"]
    freeze_manifest_path = REPO / freeze_spec["manifest_git_path"]
    freeze_size, freeze_hash = sha256_file(freeze_manifest_path)
    if freeze_hash != freeze_spec["manifest_sha256"]:
        raise RuntimeError("frozen replay manifest drift")
    frozen_verification = verify(freeze_manifest_path, artifact_root)
    freeze_manifest = json.loads(freeze_manifest_path.read_text(encoding="utf-8"))
    if frozen_verification.get("status") != "EXACT_FROZEN_REPLAY_VERIFIED" or freeze_manifest["freeze_id"] != freeze_spec["required_freeze_id"]:
        raise RuntimeError("frozen replay verification failed")
    frozen_root = artifact_root / freeze_manifest["artifact_relative_root"]

    criterion_path = REPO / config["review"]["criterion_git_path"]
    criterion_size, criterion_hash = sha256_file(criterion_path)
    if criterion_hash != config["review"]["criterion_sha256"]:
        raise RuntimeError("O/X review criterion drift")
    criterion = json.loads(criterion_path.read_text(encoding="utf-8"))
    if criterion.get("status") != "USER_APPROVED_FROZEN" or criterion.get("allowed_labels") != ["", "O", "X"]:
        raise RuntimeError("O/X review criterion is not frozen")

    app_spec = config["application"]
    app_sources = {
        "index.html": REPO / app_spec["index_git_path"],
        "app.js": REPO / app_spec["javascript_git_path"],
        "overview.html": REPO / app_spec["overview_index_git_path"],
        "overview.js": REPO / app_spec["overview_javascript_git_path"],
        "three.module.min.js": REPO / app_spec["three_module_git_path"],
    }
    three_size, three_hash = sha256_file(app_sources["three.module.min.js"])
    if three_hash != app_spec["three_module_sha256"]:
        raise RuntimeError("Three.js module identity drift")
    for name, source in app_sources.items():
        if not source.is_file() or source.is_symlink():
            raise RuntimeError(f"missing web application source: {source}")
        copy_new(source, output_root / name)

    origin = np.asarray(source_manifest["frame"]["scene_local_origin_xyz"], dtype=np.float64)
    footprint_path = frozen_root / "freeze/shared_footprints_199.geojson"
    features = all_footprints(footprint_path)
    feature_by_id = {str(feature["properties"]["stable_id"]): feature for feature in features}
    detail_ids = [str(feature["properties"]["stable_id"]) for feature in features]
    validation_ids = [str(building["stable_id"]) for building in source_manifest["buildings"]]
    detail_buffer = float(config["point_display"]["detail_xy_crop_buffer_m"])
    detail_bboxes = {stable_id: bbox_for_feature(feature_by_id[stable_id], detail_buffer) for stable_id in detail_ids}
    included_classes = set(map(int, config["point_display"]["included_classifications"]))
    detail_points: dict[str, dict[str, np.ndarray]] = {}
    overview_points: dict[str, np.ndarray] = {}
    for method in ("C1_L_upper", "C2_MVS"):
        detail, overview = sample_rgb_points(
            frozen_root / f"work/{method}/classified_scene.laz",
            detail_bboxes,
            float(config["point_display"]["detail_voxel_size_m"]),
            float(config["point_display"]["overview_voxel_size_m"]),
            included_classes,
            int(config["point_display"]["rgb_divisor"][method]),
            float(config["point_display"]["detail_spatial_index_tile_m"]),
        )
        detail_points[method] = detail
        overview_points[method] = overview

    with (frozen_root / "results/building_method_status_v3.csv").open(newline="", encoding="utf-8") as stream:
        full_status = {(row["condition_id"], row["stable_id"]): row for row in csv.DictReader(stream)}
    cityjson = {
        method: json.loads((frozen_root / f"work/{method}/assembled.city.json").read_text(encoding="utf-8"))
        for method in ("C1_L_upper", "C2_MVS")
    }
    triangles_by_method: dict[str, dict[str, list[np.ndarray]]] = {
        method: {str(feature["properties"]["stable_id"]): lod22_triangles(cityjson[method], str(feature["properties"]["stable_id"])) for feature in features}
        for method in ("C1_L_upper", "C2_MVS")
    }

    validation_assets: dict[str, dict[str, Path | None]] = {}
    for building in source_manifest["buildings"]:
        stable_id = str(building["stable_id"])
        records = {str(record["path"]): verify_record(source_root, record) for record in building["files"]}
        validation_assets[stable_id] = {
            "lidar_points": named_record(records, "01_LIDAR_POINTS", ".ply"),
            "footprint": named_record(records, "02_FOOTPRINT", ".obj"),
            "curtain": named_record(records, "03_FOOTPRINT_CURTAIN", ".obj"),
            "mvs_points": named_record(records, "04_MVS_POINTS", ".ply"),
            "lidar_roofer": named_record(records, "05_LIDAR_ROOFER", ".obj"),
            "mvs_roofer": named_record(records, "06_MVS_ROOFER", ".obj"),
        }

    viewer_buildings = []
    copied_records = []
    geometry_validation_records = []
    for feature in features:
        properties = feature["properties"]
        population_index = int(properties["population_index"])
        stable_id = str(properties["stable_id"])
        folder = f"B{population_index:03d}_{stable_id}"
        directory = output_root / "assets" / folder
        directory.mkdir(parents=True, exist_ok=False)
        method_points = {method: detail_points[method][stable_id] for method in ("C1_L_upper", "C2_MVS")}
        lower, upper, outline_z = display_z(method_points)
        lower -= float(config["mesh_display"]["curtain_padding_below_ground_m"])
        upper += float(config["mesh_display"]["curtain_padding_above_roof_m"])

        footprint = directory / "02_FOOTPRINT_outline.obj"
        curtain = directory / "03_FOOTPRINT_CURTAIN.obj"
        curtain_mtl = directory / "03_FOOTPRINT_CURTAIN.mtl"
        write_new(footprint, footprint_line_obj(stable_id, feature, outline_z, origin))
        write_new(curtain, curtain_obj(stable_id, feature, lower, upper, origin))
        write_new(curtain_mtl, material_text("footprint_curtain", config["mesh_display"]["footprint_curtain_rgb"], 0.35))

        lidar_rgb = output_root / "assets" / folder / "01_LIDAR_POINTS_rgb_class.ply"
        mvs_rgb = output_root / "assets" / folder / "04_MVS_POINTS_rgb_class.ply"
        write_rgb_class_ply(lidar_rgb, detail_points["C1_L_upper"][stable_id], origin, "frozen LiDAR detail RGB and class")
        write_rgb_class_ply(mvs_rgb, detail_points["C2_MVS"][stable_id], origin, "frozen MVS detail RGB and class")
        roofer_paths: dict[str, Path | None] = {}
        triangle_counts: dict[str, int] = {}
        for method, prefix, material in (
            ("C1_L_upper", "05_LIDAR_ROOFER", "lidar_roofer"),
            ("C2_MVS", "06_MVS_ROOFER", "mvs_roofer"),
        ):
            triangles = triangles_by_method[method][stable_id]
            triangle_counts[method] = len(triangles)
            if triangles:
                obj = directory / f"{prefix}.obj"
                mtl = directory / f"{prefix}.mtl"
                write_new(obj, triangles_obj(f"{prefix}_{stable_id}", mtl.name, material, triangles, origin))
                write_new(mtl, material_text(material, config["mesh_display"][f"{method}_rgb"]))
                roofer_paths[method] = obj
            else:
                status = full_status[(method, stable_id)]
                write_new(
                    directory / f"{prefix}_MISSING.txt",
                    f"{method} has no frozen LoD2.2 mesh. status={status['status']} reason={status['reason']}\n".encode("utf-8"),
                )
                roofer_paths[method] = None

        for path in sorted(directory.iterdir()):
            copied_records.append(file_record(path, output_root))

        if stable_id in validation_assets:
            anchor = validation_assets[stable_id]
            if anchor["lidar_points"] is None or anchor["mvs_points"] is None:
                raise RuntimeError(f"incomplete point-count validation anchor for {stable_id}")
            if len(detail_points["C1_L_upper"][stable_id]) != source_ply_count(anchor["lidar_points"]):
                raise RuntimeError(f"LiDAR detail sample membership drift: {stable_id}")
            if len(detail_points["C2_MVS"][stable_id]) != source_ply_count(anchor["mvs_points"]):
                raise RuntimeError(f"MVS detail sample membership drift: {stable_id}")
            generated = {
                "footprint": footprint,
                "curtain": curtain,
                "lidar_roofer": roofer_paths["C1_L_upper"],
                "mvs_roofer": roofer_paths["C2_MVS"],
            }
            for name, generated_path in generated.items():
                source_path = anchor[name]
                if (source_path is None) != (generated_path is None):
                    raise RuntimeError(f"review10 geometry presence drift: {stable_id} {name}")
                if source_path is not None and sha256_file(source_path) != sha256_file(generated_path):
                    raise RuntimeError(f"review10 geometry bytes drift: {stable_id} {name}")
            geometry_validation_records.append({
                "stable_id": stable_id,
                "lidar_point_count": len(detail_points["C1_L_upper"][stable_id]),
                "mvs_point_count": len(detail_points["C2_MVS"][stable_id]),
                "geometry_identity": "BYTE_IDENTICAL_TO_FROZEN_REVIEW10",
            })

        lidar_status = full_status[("C1_L_upper", stable_id)]
        mvs_status = full_status[("C2_MVS", stable_id)]
        viewer_buildings.append({
            "population_index": population_index,
            "stable_id": stable_id,
            "bbox_world_xy": list(detail_bboxes[stable_id]),
            "footprint": footprint.relative_to(output_root).as_posix(),
            "curtain": curtain.relative_to(output_root).as_posix(),
            "lidar": {
                "technical_status": lidar_status["status"],
                "points": lidar_rgb.relative_to(output_root).as_posix(),
                "point_count": len(detail_points["C1_L_upper"][stable_id]),
                "roofer": roofer_paths["C1_L_upper"].relative_to(output_root).as_posix() if roofer_paths["C1_L_upper"] else None,
                "roofer_triangles": triangle_counts["C1_L_upper"],
            },
            "mvs": {
                "technical_status": mvs_status["status"],
                "points": mvs_rgb.relative_to(output_root).as_posix(),
                "point_count": len(detail_points["C2_MVS"][stable_id]),
                "roofer": roofer_paths["C2_MVS"].relative_to(output_root).as_posix() if roofer_paths["C2_MVS"] else None,
                "roofer_triangles": triangle_counts["C2_MVS"],
            },
        })
    if len(viewer_buildings) != 199 or len(geometry_validation_records) != len(validation_ids):
        raise RuntimeError("web reviewer did not package and validate the required building population")

    overview_root = output_root / "overview"
    overview_root.mkdir(parents=True, exist_ok=False)
    overview_method_records = {}
    for method, short_name in (("C1_L_upper", "lidar"), ("C2_MVS", "mvs")):
        points_path = overview_root / f"{short_name}_scene_rgb_class_lod.ply"
        write_rgb_class_ply(points_path, overview_points[method], origin, f"frozen {short_name} whole-scene deterministic overview LOD")
        all_triangles = [triangle for feature in features for triangle in triangles_by_method[method][str(feature["properties"]["stable_id"])] ]
        roofer_path = overview_root / f"{short_name}_roofer_199.obj"
        write_new(roofer_path, triangles_obj(f"OVERVIEW_{method}", "unused.mtl", f"overview_{short_name}", all_triangles, origin))
        copied_records.extend((file_record(points_path, output_root), file_record(roofer_path, output_root)))
        overview_method_records[short_name] = {
            "points": points_path.relative_to(output_root).as_posix(),
            "point_count": len(overview_points[method]),
            "roofer": roofer_path.relative_to(output_root).as_posix(),
            "roofer_triangles": len(all_triangles),
        }

    z_by_id: dict[str, float] = {}
    overview_buildings = []
    detail_set = set(detail_ids)
    for feature in features:
        properties = feature["properties"]
        stable_id = str(properties["stable_id"])
        population_index = int(properties["population_index"])
        bbox = tuple(map(float, shape(feature["geometry"]).bounds))
        roof_z = footprint_support_z(overview_points["C1_L_upper"], bbox)
        if roof_z is None:
            roof_z = footprint_support_z(overview_points["C2_MVS"], bbox)
        if roof_z is None:
            mesh_z = [float(triangle[:, 2].max()) for method in ("C1_L_upper", "C2_MVS") for triangle in triangles_by_method[method][stable_id]]
            roof_z = max(mesh_z) if mesh_z else None
        if roof_z is None:
            roof_z = footprint_any_z(overview_points["C1_L_upper"], bbox)
        if roof_z is None:
            roof_z = footprint_any_z(overview_points["C2_MVS"], bbox)
        if roof_z is None:
            roof_z = float(origin[2])
        z_by_id[stable_id] = roof_z
        centroid = shape(feature["geometry"]).centroid
        overview_buildings.append({
            "population_index": population_index,
            "stable_id": stable_id,
            "center_local_xyz": [float(centroid.x - origin[0]), float(centroid.y - origin[1]), float(roof_z - origin[2])],
            "bbox_local_xy": [float(bbox[0] - origin[0]), float(bbox[1] - origin[1]), float(bbox[2] - origin[0]), float(bbox[3] - origin[1])],
            "detail_available": stable_id in detail_set,
            "lidar": {"technical_status": full_status[("C1_L_upper", stable_id)]["status"]},
            "mvs": {"technical_status": full_status[("C2_MVS", stable_id)]["status"]},
        })
    overview_footprints = overview_root / "shared_footprints_199_roof_focus.obj"
    write_new(overview_footprints, overview_footprint_obj(features, z_by_id, origin))
    copied_records.append(file_record(overview_footprints, output_root))

    viewer_manifest = {
        "schema": "jointbuildgs.p2.c1_c2_original_global_v3.web_viewer_manifest.v3",
        "task_id": config["task_id"],
        "status": "READY_FOR_HUMAN_WEB_REVIEW",
        "source_freeze_id": source_manifest["frozen_verification"]["freeze_id"],
        "scene_local_origin_xyz": source_manifest["frame"]["scene_local_origin_xyz"],
        "review_criterion_id": criterion["criterion_id"],
        "review_categories": criterion["allowed_labels"],
        "features": config["features"],
        "buildings": viewer_buildings,
        "overview": {
            "voxel_size_m": float(config["point_display"]["overview_voxel_size_m"]),
            "footprints": overview_footprints.relative_to(output_root).as_posix(),
            "methods": overview_method_records,
            "buildings": overview_buildings,
        },
        "scientific_verdict": None,
    }
    viewer_manifest_path = output_root / "viewer_manifest.json"
    write_new(viewer_manifest_path, canonical_json_bytes(viewer_manifest))
    readme = output_root / "README_WEB_REVIEW199.txt"
    write_new(
        readme,
        (
            "JointBuildGS frozen v3 LiDAR/MVS web review199\n\n"
            "Start with:\n"
            "scripts/p2/c1_c2_shared_footprint_199_v3/serve_web_review10_host.sh ARTIFACT_ROOT [PORT]\n\n"
            "Open the printed URL. index.html is the synchronized 199-building reviewer; overview.html is the full-scene navigator.\n"
            "Point display switches between fixed-normalized source RGB and condition solid color without changing point membership.\n"
            "Human review is frozen to blank/O/X and is saved in browser localStorage for CSV export.\n"
            "Distance and delta-Z measurement use two selected point/mesh positions in scene-local metres.\n"
            "Fit is roof-centric: the footprint XY and the 75th percentile of non-ground points inside it set the display focus.\n"
            "The footprint line is moved only in display Z to that per-method focus height; source XY and all scientific assets are unchanged.\n"
            "If one method has zero direct footprint support, the other method's focus Z is shared only for side-by-side display and labeled as shared.\n"
            "Z clipping is display-only. This package invokes no Roofer, reconstruction, training, or metric calculation.\n"
        ).encode("utf-8"),
    )
    manifest = {
        "schema": "jointbuildgs.p2.c1_c2_original_global_v3.web_review199_artifacts.v1",
        "task_id": config["task_id"],
        "status": "COMPLETE_OFFLINE_WEB_REVIEW199",
        "source_manifest": {"path": source_spec["manifest_path"], "bytes": source_size, "sha256": source_hash},
        "frozen_replay_manifest": {"path": freeze_manifest_path.relative_to(REPO).as_posix(), "bytes": freeze_size, "sha256": freeze_hash},
        "review_criterion": {"path": criterion_path.relative_to(REPO).as_posix(), "bytes": criterion_size, "sha256": criterion_hash},
        "application_records": [file_record(output_root / name, output_root) for name in app_sources],
        "viewer_manifest": file_record(viewer_manifest_path, output_root),
        "readme": file_record(readme, output_root),
        "asset_record_count": len(copied_records),
        "asset_records": copied_records,
        "review10_identity_validation": {
            "status": "POINT_MEMBERSHIP_AND_GEOMETRY_IDENTICAL",
            "building_count": len(geometry_validation_records),
            "records": geometry_validation_records,
        },
        "execution": config["execution"],
        "scientific_verdict": None,
    }
    manifest_path = output_root / "manifest_web_review199_v1.json"
    write_new(manifest_path, canonical_json_bytes(manifest))
    receipt = {
        "schema": "jointbuildgs.p2.c1_c2_original_global_v3.web_review199_receipt.v1",
        "task_id": config["task_id"],
        "completed_at_utc": datetime.now(timezone.utc).isoformat(),
        "config": file_record(config_path, REPO),
        "script": file_record(Path(__file__).resolve(), REPO),
        "manifest": file_record(manifest_path, output_root),
        "building_count": 199,
        "overview_building_count": 199,
        "roofer_invocations": 0,
        "reconstruction_invocations": 0,
        "scientific_verdict": None,
    }
    write_new(output_root / "receipt_web_review199_v1.json", canonical_json_bytes(receipt))
    return manifest_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    print(build(args.config.resolve(), args.artifact_root.resolve(), args.output_root.resolve()))


if __name__ == "__main__":
    main()
