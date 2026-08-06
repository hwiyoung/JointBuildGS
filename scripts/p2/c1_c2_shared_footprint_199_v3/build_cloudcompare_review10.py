#!/usr/bin/env python3
"""Build a deterministic, frozen-v3-only CloudCompare review package for 10 buildings."""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import io
import json
from pathlib import Path
import struct
from typing import Any, Iterable, Mapping, Sequence

import laspy
import numpy as np
from shapely.geometry import shape

from scripts.p2.c1_c2_shared_footprint_199_v3.verify_frozen_replay import verify
from scripts.p2.qualitative_199_cloudcompare_scene_v1.add_shared_footprint_roofer import (
    triangulate_surface,
)
from scripts.p2.qualitative_199_cloudcompare_scene_v1.build_scene import (
    REPO,
    canonical_json_bytes,
    file_record,
    sha256_file,
    write_new,
)


DEFAULT_CONFIG = REPO / "configs/p2/c1_c2_shared_footprint_199_v3/cloudcompare_review10_v1.json"
METHODS = ("C1_L_upper", "C2_MVS")


def load_config(path: Path) -> dict[str, Any]:
    config = json.loads(path.read_text(encoding="utf-8"))
    if config.get("schema") != "jointbuildgs.p2.c1_c2_original_global_v3.cloudcompare_review10.v1":
        raise RuntimeError("unexpected CloudCompare review10 config schema")
    if config.get("status") != "USER_APPROVED_FOR_EXECUTION":
        raise RuntimeError("CloudCompare review10 execution is not approved")
    if config.get("scientific_verdict", "missing") is not None:
        raise RuntimeError("scientific_verdict must remain null")
    execution = config.get("execution", {})
    if any(int(execution.get(key, -1)) != 0 for key in ("roofer_invocations", "reconstruction_invocations", "gs_training_invocations")):
        raise RuntimeError("review package must not invoke reconstruction")
    indices = list(config["selection"]["population_indices"])
    ids = list(config["selection"]["building_ids"])
    if indices != [1, 23, 45, 67, 89, 111, 133, 155, 177, 199] or len(ids) != 10 or len(set(ids)) != 10:
        raise RuntimeError("review10 membership drifted")
    return config


def verify_git_file(path: Path, expected_sha256: str) -> dict[str, Any]:
    size, digest = sha256_file(path)
    if digest != expected_sha256:
        raise RuntimeError(f"Git-owned input identity drift: {path}")
    return {"path": path.relative_to(REPO).as_posix(), "bytes": size, "sha256": digest}


def load_footprints(path: Path, wanted: Sequence[str]) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    selected = {
        str(feature["properties"]["stable_id"]): feature
        for feature in data.get("features", [])
        if str(feature.get("properties", {}).get("stable_id")) in set(wanted)
    }
    if set(selected) != set(wanted):
        raise RuntimeError("frozen footprint membership does not cover review10")
    return selected


def load_status_rows(path: Path, ids: Sequence[str]) -> dict[tuple[str, str], dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    selected = {
        (row["condition_id"], row["stable_id"]): row
        for row in rows
        if row["stable_id"] in set(ids)
    }
    if set(selected) != {(method, stable_id) for method in METHODS for stable_id in ids}:
        raise RuntimeError("frozen status table does not cover review10")
    return selected


def bbox_for_feature(feature: Mapping[str, Any], buffer_m: float) -> tuple[float, float, float, float]:
    minx, miny, maxx, maxy = shape(feature["geometry"]).bounds
    return minx - buffer_m, miny - buffer_m, maxx + buffer_m, maxy + buffer_m


def deterministic_voxel_points(
    path: Path,
    bboxes: Mapping[str, tuple[float, float, float, float]],
    voxel_size: float,
    included_classes: set[int],
) -> dict[str, np.ndarray]:
    """Keep the first input-order point in each fixed world-coordinate voxel."""
    seen: dict[str, set[tuple[int, int, int]]] = {key: set() for key in bboxes}
    chunks: dict[str, list[np.ndarray]] = {key: [] for key in bboxes}
    with laspy.open(path) as reader:
        for points in reader.chunk_iterator(2_000_000):
            x = np.asarray(points.x, dtype=np.float64)
            y = np.asarray(points.y, dtype=np.float64)
            z = np.asarray(points.z, dtype=np.float64)
            classification = np.asarray(points.classification, dtype=np.uint8)
            class_mask = np.isin(classification, np.asarray(sorted(included_classes), dtype=np.uint8))
            for stable_id, (minx, miny, maxx, maxy) in bboxes.items():
                mask = class_mask & (x >= minx) & (x <= maxx) & (y >= miny) & (y <= maxy)
                indices = np.flatnonzero(mask)
                if not len(indices):
                    continue
                xyz = np.column_stack((x[indices], y[indices], z[indices]))
                keys = np.floor(xyz / voxel_size).astype(np.int64)
                _, first = np.unique(keys, axis=0, return_index=True)
                order = np.sort(first)
                kept_rows = []
                local_seen = seen[stable_id]
                for position in order:
                    key = tuple(int(value) for value in keys[position])
                    if key in local_seen:
                        continue
                    local_seen.add(key)
                    kept_rows.append((xyz[position, 0], xyz[position, 1], xyz[position, 2], int(classification[indices[position]])))
                if kept_rows:
                    chunks[stable_id].append(np.asarray(kept_rows, dtype=np.float64))
    result = {}
    for stable_id in bboxes:
        result[stable_id] = np.concatenate(chunks[stable_id], axis=0) if chunks[stable_id] else np.empty((0, 4), dtype=np.float64)
    return result


def write_binary_ply(
    path: Path,
    points: np.ndarray,
    origin: np.ndarray,
    method_rgb: Sequence[int],
    ground_rgb: Sequence[int],
) -> None:
    dtype = np.dtype([
        ("x", "<f4"), ("y", "<f4"), ("z", "<f4"),
        ("red", "u1"), ("green", "u1"), ("blue", "u1"),
    ])
    body = np.empty(len(points), dtype=dtype)
    if len(points):
        xyz = points[:, :3] - origin
        body["x"], body["y"], body["z"] = xyz[:, 0], xyz[:, 1], xyz[:, 2]
        ground = points[:, 3].astype(np.uint8) == 2
        colors = np.tile(np.asarray(method_rgb, dtype=np.uint8), (len(points), 1))
        colors[ground] = np.asarray(ground_rgb, dtype=np.uint8)
        body["red"], body["green"], body["blue"] = colors[:, 0], colors[:, 1], colors[:, 2]
    header = (
        "ply\nformat binary_little_endian 1.0\n"
        "comment JointBuildGS frozen v3 visualization-only crop\n"
        f"element vertex {len(points)}\n"
        "property float x\nproperty float y\nproperty float z\n"
        "property uchar red\nproperty uchar green\nproperty uchar blue\nend_header\n"
    ).encode("ascii")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(header)
        stream.write(body.tobytes())


def transformed_vertices(cityjson: Mapping[str, Any]) -> np.ndarray:
    transform = cityjson["transform"]
    scale = np.asarray(transform["scale"], dtype=np.float64)
    translate = np.asarray(transform["translate"], dtype=np.float64)
    return np.asarray(cityjson["vertices"], dtype=np.float64) * scale + translate


def descendant_ids(city_objects: Mapping[str, Any], stable_id: str) -> list[str]:
    if stable_id not in city_objects:
        return []
    output, pending = [], [stable_id]
    while pending:
        object_id = pending.pop(0)
        if object_id in output:
            continue
        output.append(object_id)
        pending.extend(str(value) for value in city_objects[object_id].get("children", []))
    return output


def lod22_triangles(cityjson: Mapping[str, Any], stable_id: str) -> list[np.ndarray]:
    vertices = transformed_vertices(cityjson)
    city_objects = cityjson["CityObjects"]
    output: list[np.ndarray] = []
    for object_id in descendant_ids(city_objects, stable_id):
        for geometry in city_objects[object_id].get("geometry", []):
            if str(geometry.get("lod")) != "2.2":
                continue
            if geometry.get("type") != "Solid":
                raise RuntimeError(f"unexpected LoD2.2 geometry type for {stable_id}")
            for shell in geometry.get("boundaries", []):
                for rings in shell:
                    output.extend(triangulate_surface(vertices, rings))
    return output


def material_text(name: str, rgb: Sequence[int], opacity: float = 1.0) -> bytes:
    color = [float(value) / 255.0 for value in rgb]
    return (
        f"newmtl {name}\nKd {color[0]:.6f} {color[1]:.6f} {color[2]:.6f}\n"
        f"Ka 0.050000 0.050000 0.050000\nKs 0.100000 0.100000 0.100000\n"
        f"d {opacity:.3f}\nillum 2\n"
    ).encode("ascii")


def triangles_obj(name: str, mtl_file: str, material: str, triangles: Sequence[np.ndarray], origin: np.ndarray) -> bytes:
    lines = [f"# {name}", f"mtllib {mtl_file}", f"o {name}", f"g {name}", f"usemtl {material}"]
    offset = 1
    for triangle in triangles:
        for xyz in triangle - origin:
            lines.append(f"v {xyz[0]:.6f} {xyz[1]:.6f} {xyz[2]:.6f}")
        lines.append(f"f {offset} {offset + 1} {offset + 2}")
        offset += 3
    return ("\n".join(lines) + "\n").encode("ascii")


def polygon_rings(feature: Mapping[str, Any]) -> Iterable[np.ndarray]:
    geometry = shape(feature["geometry"])
    polygons = [geometry] if geometry.geom_type == "Polygon" else list(geometry.geoms)
    for polygon in polygons:
        yield np.asarray(polygon.exterior.coords[:-1], dtype=np.float64)
        for interior in polygon.interiors:
            yield np.asarray(interior.coords[:-1], dtype=np.float64)


def footprint_line_obj(stable_id: str, feature: Mapping[str, Any], z: float, origin: np.ndarray) -> bytes:
    lines = [f"# {stable_id} footprint", f"o 02_FOOTPRINT_{stable_id}", f"g 02_FOOTPRINT_{stable_id}"]
    offset = 1
    for ring in polygon_rings(feature):
        for xy in ring:
            xyz = np.asarray([xy[0], xy[1], z]) - origin
            lines.append(f"v {xyz[0]:.6f} {xyz[1]:.6f} {xyz[2]:.6f}")
        indices = list(range(offset, offset + len(ring))) + [offset]
        lines.append("l " + " ".join(map(str, indices)))
        offset += len(ring)
    return ("\n".join(lines) + "\n").encode("ascii")


def curtain_obj(stable_id: str, feature: Mapping[str, Any], lower: float, upper: float, origin: np.ndarray) -> bytes:
    lines = [
        f"# {stable_id} display-only footprint curtain",
        "mtllib 03_FOOTPRINT_CURTAIN.mtl",
        f"o 03_FOOTPRINT_CURTAIN_{stable_id}",
        f"g 03_FOOTPRINT_CURTAIN_{stable_id}",
        "usemtl footprint_curtain",
    ]
    offset = 1
    for ring in polygon_rings(feature):
        for xy in ring:
            for z in (lower, upper):
                xyz = np.asarray([xy[0], xy[1], z]) - origin
                lines.append(f"v {xyz[0]:.6f} {xyz[1]:.6f} {xyz[2]:.6f}")
        for index in range(len(ring)):
            nxt = (index + 1) % len(ring)
            a, b = offset + 2 * index, offset + 2 * nxt
            lines.append(f"f {a} {b} {b + 1} {a + 1}")
        offset += 2 * len(ring)
    return ("\n".join(lines) + "\n").encode("ascii")


def csv_data(fieldnames: Sequence[str], rows: Sequence[Mapping[str, Any]]) -> bytes:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=fieldnames, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode("utf-8")


def display_z(points_by_method: Mapping[str, np.ndarray]) -> tuple[float, float, float]:
    arrays = [value for value in points_by_method.values() if len(value)]
    if not arrays:
        return 0.0, 0.0, 1.0
    points = np.concatenate(arrays, axis=0)
    ground = points[points[:, 3] == 2, 2]
    building = points[points[:, 3] == 6, 2]
    lower = float(np.percentile(ground, 5)) if len(ground) else float(points[:, 2].min())
    upper = float(np.percentile(building, 99)) if len(building) else float(points[:, 2].max())
    return lower, upper, upper + 0.15


def build(config_path: Path, artifact_root: Path, output_root: Path) -> Path:
    config = load_config(config_path)
    if output_root.exists() and any(output_root.iterdir()):
        raise RuntimeError("fresh add-once review10 output root required")
    output_root.mkdir(parents=True, exist_ok=True)
    freeze_spec = config["frozen_source"]
    freeze_manifest_path = REPO / freeze_spec["manifest_git_path"]
    freeze_manifest_record = verify_git_file(freeze_manifest_path, freeze_spec["manifest_sha256"])
    frozen_verification = verify(freeze_manifest_path, artifact_root)
    freeze_manifest = json.loads(freeze_manifest_path.read_text(encoding="utf-8"))
    if freeze_manifest["freeze_id"] != freeze_spec["required_freeze_id"]:
        raise RuntimeError("unexpected frozen replay identity")
    source_root = artifact_root / freeze_manifest["artifact_relative_root"]

    ids = list(config["selection"]["building_ids"])
    indices = list(config["selection"]["population_indices"])
    footprints = load_footprints(source_root / "freeze/shared_footprints_199.geojson", ids)
    status_rows = load_status_rows(source_root / "results/building_method_status_v3.csv", ids)
    cityjson = {
        method: json.loads((source_root / f"work/{method}/assembled.city.json").read_text(encoding="utf-8"))
        for method in METHODS
    }
    buffer_m = float(config["point_display"]["xy_crop_buffer_m"])
    bboxes = {stable_id: bbox_for_feature(footprints[stable_id], buffer_m) for stable_id in ids}
    voxel_size = float(config["point_display"]["voxel_size_m"])
    included = set(map(int, config["point_display"]["included_classifications"]))
    points = {
        method: deterministic_voxel_points(source_root / f"work/{method}/classified_scene.laz", bboxes, voxel_size, included)
        for method in METHODS
    }
    origin = np.asarray(config["frame"]["scene_local_origin_xyz"], dtype=np.float64)
    review_rows, building_records = [], []
    for population_index, stable_id in zip(indices, ids):
        directory = output_root / f"B{population_index:03d}_{stable_id}"
        directory.mkdir(parents=True, exist_ok=False)
        method_points = {method: points[method][stable_id] for method in METHODS}
        lower, upper, outline_z = display_z(method_points)
        lower -= float(config["mesh_display"]["curtain_padding_below_ground_m"])
        upper += float(config["mesh_display"]["curtain_padding_above_roof_m"])

        lidar_ply = directory / "01_LIDAR_POINTS_visual_crop.ply"
        mvs_ply = directory / "04_MVS_POINTS_visual_crop.ply"
        write_binary_ply(lidar_ply, method_points["C1_L_upper"], origin, config["point_display"]["C1_L_upper_rgb"], config["point_display"]["ground_rgb"])
        write_binary_ply(mvs_ply, method_points["C2_MVS"], origin, config["point_display"]["C2_MVS_rgb"], config["point_display"]["ground_rgb"])
        footprint_path = directory / "02_FOOTPRINT_outline.obj"
        write_new(footprint_path, footprint_line_obj(stable_id, footprints[stable_id], outline_z, origin))
        curtain_path = directory / "03_FOOTPRINT_CURTAIN.obj"
        curtain_mtl = directory / "03_FOOTPRINT_CURTAIN.mtl"
        write_new(curtain_path, curtain_obj(stable_id, footprints[stable_id], lower, upper, origin))
        write_new(curtain_mtl, material_text("footprint_curtain", config["mesh_display"]["footprint_curtain_rgb"], 0.35))

        mesh_files: dict[str, str] = {}
        triangle_counts: dict[str, int] = {}
        for method, prefix, material in (("C1_L_upper", "05_LIDAR_ROOFER", "lidar_roofer"), ("C2_MVS", "06_MVS_ROOFER", "mvs_roofer")):
            triangles = lod22_triangles(cityjson[method], stable_id)
            triangle_counts[method] = len(triangles)
            if triangles:
                obj = directory / f"{prefix}.obj"
                mtl = directory / f"{prefix}.mtl"
                write_new(obj, triangles_obj(f"{prefix}_{stable_id}", mtl.name, material, triangles, origin))
                write_new(mtl, material_text(material, config["mesh_display"][f"{method}_rgb"]))
                mesh_files[method] = obj.name
            else:
                missing = directory / f"{prefix}_MISSING.txt"
                status = status_rows[(method, stable_id)]
                write_new(missing, f"{method} has no frozen LoD2.2 mesh. status={status['status']} reason={status['reason']}\n".encode("utf-8"))
                mesh_files[method] = missing.name

        load_files = [lidar_ply.name, footprint_path.name, curtain_path.name, mvs_ply.name]
        load_files.extend(mesh_files[method] for method in METHODS if mesh_files[method].endswith(".obj"))
        readme = directory / "OPEN_IN_CLOUDCOMPARE.txt"
        write_new(
            readme,
            (
                f"Building: B{population_index:03d}_{stable_id}\n"
                "Open every .ply and .obj file in this directory together in CloudCompare.\n"
                "All layers already share one local origin; do not apply another coordinate shift.\n"
                "Suggested review: TOP -> OBLIQUE -> SIDE, toggling LiDAR and MVS Roofer layers.\n"
                "MTL files provide colors where supported. Missing Roofer layers are explicit TXT files.\n"
                f"Loadable files: {', '.join(load_files)}\n"
            ).encode("utf-8"),
        )
        lidar_status, mvs_status = status_rows[("C1_L_upper", stable_id)], status_rows[("C2_MVS", stable_id)]
        review_rows.append({
            "population_index": population_index,
            "stable_id": stable_id,
            "folder": directory.name,
            "lidar_technical_status": lidar_status["status"],
            "mvs_technical_status": mvs_status["status"],
            "lidar_visual_point_count": len(method_points["C1_L_upper"]),
            "mvs_visual_point_count": len(method_points["C2_MVS"]),
            "lidar_roofer_triangles": triangle_counts["C1_L_upper"],
            "mvs_roofer_triangles": triangle_counts["C2_MVS"],
            "lidar_human_review": "",
            "mvs_human_review": "",
            "reviewer_note": "",
        })
        files = sorted(path for path in directory.iterdir() if path.is_file())
        building_records.append({
            "population_index": population_index,
            "stable_id": stable_id,
            "folder": directory.name,
            "bbox_world_xy": list(bboxes[stable_id]),
            "visual_point_counts": {method: len(method_points[method]) for method in METHODS},
            "roofer_triangle_counts": triangle_counts,
            "files": [file_record(path, output_root) for path in files],
        })

    review_fields = [
        "population_index", "stable_id", "folder",
        "lidar_technical_status", "mvs_technical_status",
        "lidar_visual_point_count", "mvs_visual_point_count",
        "lidar_roofer_triangles", "mvs_roofer_triangles",
        "lidar_human_review", "mvs_human_review", "reviewer_note",
    ]
    review_csv = output_root / "REVIEW10_FORM.csv"
    write_new(review_csv, csv_data(review_fields, review_rows))
    readme = output_root / "README_CLOUDCOMPARE_REVIEW10.txt"
    write_new(
        readme,
        (
            "JointBuildGS frozen original-global v3 CloudCompare review10\n\n"
            "This package contains only the frozen replay-20260806a result. Historical v1/v2 OBJ files are absent.\n"
            "Open one B### directory at a time and load its .ply and .obj files together.\n"
            "Point crops are deterministic visualization-only derivatives; Roofer meshes are converted from frozen CityJSON.\n"
            "Colors: LiDAR points blue, MVS points orange, ground gray, LiDAR Roofer green, MVS Roofer magenta.\n"
            "Review TOP, OBLIQUE, and SIDE views and record the human assessment in REVIEW10_FORM.csv.\n"
            "Allowed labels: GOOD, OVER_SEGMENTED, MISSING_ROOF_PART, HEIGHT_OR_SLOPE_ERROR, WARPED_OR_COLLAPSED, UNDECIDABLE.\n"
            "This package performs zero Roofer, reconstruction, GS-training, or scientific-verdict operations.\n"
        ).encode("utf-8"),
    )
    manifest = {
        "schema": "jointbuildgs.p2.c1_c2_original_global_v3.cloudcompare_review10_manifest.v1",
        "task_id": config["task_id"],
        "status": "COMPLETE_FROZEN_V3_CLOUDCOMPARE_REVIEW10",
        "frozen_verification": {key: frozen_verification[key] for key in ("freeze_id", "status", "verified_record_count", "roofer_invocations")},
        "freeze_manifest": freeze_manifest_record,
        "selection": config["selection"],
        "frame": config["frame"],
        "display": {"point_display": config["point_display"], "mesh_display": config["mesh_display"]},
        "buildings": building_records,
        "review_form": file_record(review_csv, output_root),
        "readme": file_record(readme, output_root),
        "execution": config["execution"],
        "scientific_verdict": None,
    }
    manifest_path = output_root / "manifest_cloudcompare_review10_v1.json"
    write_new(manifest_path, canonical_json_bytes(manifest))
    receipt = {
        "schema": "jointbuildgs.p2.c1_c2_original_global_v3.cloudcompare_review10_receipt.v1",
        "task_id": config["task_id"],
        "completed_at_utc": datetime.now(timezone.utc).isoformat(),
        "config": file_record(config_path, REPO),
        "script": file_record(Path(__file__).resolve(), REPO),
        "manifest": file_record(manifest_path, output_root),
        "building_count": len(building_records),
        "roofer_invocations": 0,
        "reconstruction_invocations": 0,
        "scientific_verdict": None,
    }
    receipt_path = output_root / "receipt_cloudcompare_review10_v1.json"
    write_new(receipt_path, canonical_json_bytes(receipt))
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
