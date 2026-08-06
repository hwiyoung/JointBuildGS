#!/usr/bin/env python3
"""Add the DEC-P1-019 building-level Roofer outputs as named CloudCompare OBJ groups."""

from __future__ import annotations

import argparse
from collections import Counter
import csv
from datetime import datetime, timezone
import io
import json
import os
from pathlib import Path
import subprocess
from typing import Any, Mapping, Sequence

import numpy as np
from shapely.geometry import Polygon
from shapely.ops import triangulate

from scripts.p2.qualitative_199_cloudcompare_scene_v1.add_previous_roofer import transformed_vertices
from scripts.p2.qualitative_199_cloudcompare_scene_v1.build_scene import (
    REPO,
    canonical_json_bytes,
    file_record,
    sha256_file,
    write_new,
)


DEFAULT_CONFIG = REPO / "configs/p2/qualitative_199_cloudcompare_scene_v1/add_shared_footprint_roofer_v1.json"


def load_config(path: Path) -> dict[str, Any]:
    config = json.loads(path.read_text(encoding="utf-8"))
    if config.get("schema") != "jointbuildgs.p2.qualitative_199_cloudcompare_scene.shared_footprint_roofer_extension.v1":
        raise RuntimeError("unexpected shared-footprint Roofer extension schema")
    if config.get("status") != "USER_APPROVED_FOR_EXECUTION" or config.get("decision_id") != "DEC-P1-019":
        raise RuntimeError("shared-footprint Roofer extension is not approved by DEC-P1-019")
    if config.get("scientific_verdict", "missing") is not None:
        raise RuntimeError("scientific_verdict must remain null")
    if any(int(config["execution"][key]) != 0 for key in ("roofer_invocations", "reconstruction_invocations", "gs_training_invocations")):
        raise RuntimeError("this extension may only convert already completed outputs")
    return config


def verify_bound(path: Path, spec: Mapping[str, Any], label: str) -> dict[str, Any]:
    if not path.is_file() or path.is_symlink():
        raise RuntimeError(f"missing or non-regular {label}: {path}")
    size, digest = sha256_file(path)
    if size != int(spec["bytes"]) or digest != str(spec["sha256"]):
        raise RuntimeError(f"{label} identity drift: {size}/{digest}")
    return {"path": str(path), "bytes": size, "sha256": digest, "verification": "sha256_rehash"}


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def validate_rows(rows: Sequence[Mapping[str, Any]], config: Mapping[str, Any]) -> dict[str, list[Mapping[str, Any]]]:
    methods = set(config["methods"])
    if len(rows) != 398:
        raise RuntimeError(f"expected 398 building-method rows, received {len(rows)}")
    keys = [(str(row["condition_id"]), str(row["stable_id"])) for row in rows]
    if len(set(keys)) != 398 or {method for method, _stable_id in keys} != methods:
        raise RuntimeError("building-method result keys are incomplete or duplicated")
    grouped: dict[str, list[Mapping[str, Any]]] = {}
    population_by_method: dict[str, list[tuple[int, str]]] = {}
    for method in sorted(methods):
        selected = sorted((row for row in rows if row["condition_id"] == method), key=lambda row: int(row["population_index"]))
        if len(selected) != 199 or [int(row["population_index"]) for row in selected] != list(range(1, 200)):
            raise RuntimeError(f"{method} does not contain the ordered 199-building population")
        completed = sum(row["status"] == "COMPLETED" for row in selected)
        missing = len(selected) - completed
        expected = config["methods"][method]
        if completed != int(expected["expected_process_completed"]) or missing != int(expected["expected_pre_roofer_missing"]):
            raise RuntimeError(f"{method} completion/missingness count drift")
        if any(row.get("shared_standard_footprint") is not True for row in selected):
            raise RuntimeError(f"{method} contains a row without the shared standard footprint")
        if any(row.get("lod2_z_used") is not False or row.get("roofsurface_used") is not False for row in selected):
            raise RuntimeError(f"{method} contains prohibited LoD2 Z or RoofSurface input use")
        grouped[method] = selected
        population_by_method[method] = [(int(row["population_index"]), str(row["stable_id"])) for row in selected]
    if len({tuple(value) for value in population_by_method.values()}) != 1:
        raise RuntimeError("LiDAR and MVS population order differs")
    return grouped


def group_name(row: Mapping[str, Any]) -> str:
    return f"B{int(row['population_index']):03d}_{row['stable_id']}"


def triangulate_surface(vertices: np.ndarray, rings: Sequence[Sequence[int]]) -> list[np.ndarray]:
    normalized_rings: list[list[int]] = []
    for ring in rings:
        indices = list(map(int, ring))
        if len(indices) >= 2 and indices[0] == indices[-1]:
            indices = indices[:-1]
        if len(indices) < 3 or min(indices) < 0 or max(indices) >= len(vertices):
            raise RuntimeError("invalid Roofer surface ring")
        normalized_rings.append(indices)
    if not normalized_rings:
        raise RuntimeError("Roofer surface has no rings")
    outer_xyz = vertices[normalized_rings[0]]
    normal = np.zeros(3, dtype=np.float64)
    for index in range(len(outer_xyz)):
        normal += np.cross(outer_xyz[index], outer_xyz[(index + 1) % len(outer_xyz)])
    if float(np.linalg.norm(normal)) <= 1.0e-12:
        return []
    drop_axis = int(np.argmax(np.abs(normal)))
    keep_axes = [axis for axis in range(3) if axis != drop_axis]
    all_indices = [index for ring in normalized_rings for index in ring]
    all_xyz = vertices[all_indices]
    all_xy = all_xyz[:, keep_axes]
    projected_rings = [vertices[ring][:, keep_axes] for ring in normalized_rings]
    polygon = Polygon(projected_rings[0], projected_rings[1:])
    if not polygon.is_valid:
        polygon = polygon.buffer(0)
    if polygon.is_empty:
        return []
    if polygon.geom_type == "Polygon":
        polygons = [polygon]
    elif polygon.geom_type == "MultiPolygon":
        polygons = list(polygon.geoms)
    elif polygon.geom_type == "GeometryCollection":
        polygons = [geometry for geometry in polygon.geoms if geometry.geom_type == "Polygon" and not geometry.is_empty]
    else:
        return []
    output: list[np.ndarray] = []
    for polygon_part in polygons:
        for triangle in triangulate(polygon_part):
            if not polygon_part.covers(triangle):
                continue
            triangle_xyz = []
            for point in np.asarray(triangle.exterior.coords[:-1], dtype=np.float64):
                distances = np.linalg.norm(all_xy - point, axis=1)
                nearest = int(np.argmin(distances))
                if float(distances[nearest]) <= 1.0e-7:
                    triangle_xyz.append(all_xyz[nearest])
                else:
                    # Polygon repair may insert a 2D intersection vertex. Lift it back
                    # onto the original planar Roofer surface instead of discarding it.
                    lifted = np.empty(3, dtype=np.float64)
                    lifted[keep_axes] = point
                    lifted[drop_axis] = outer_xyz[0, drop_axis] - float(
                        np.dot(normal[keep_axes], point - outer_xyz[0, keep_axes]) / normal[drop_axis]
                    )
                    triangle_xyz.append(lifted)
            xyz = np.asarray(triangle_xyz, dtype=np.float64)
            if np.linalg.norm(np.cross(xyz[1] - xyz[0], xyz[2] - xyz[0])) > 1.0e-12:
                output.append(xyz)
    return output


def cityjsonseq_surfaces(data: bytes, scene_origin: np.ndarray) -> tuple[str, list[tuple[str, np.ndarray]]]:
    inherited: Mapping[str, Any] | None = None
    feature_id = ""
    output: list[tuple[str, np.ndarray]] = []
    header_count = 0
    feature_count = 0
    for line in data.decode("utf-8").splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        if record.get("type") == "CityJSON":
            header_count += 1
            if header_count != 1 or feature_count or record.get("vertices") != [] or record.get("CityObjects") != {}:
                raise RuntimeError("invalid CityJSONSeq inheritance header")
            inherited = record.get("transform")
            continue
        if record.get("type") != "CityJSONFeature" or inherited is None or "transform" in record:
            raise RuntimeError("invalid CityJSONSeq feature")
        feature_count += 1
        if feature_count != 1:
            raise RuntimeError("expected one Roofer feature per building output")
        feature_id = str(record.get("id", ""))
        vertices = transformed_vertices(record, inherited, scene_origin)
        city_objects = record.get("CityObjects")
        if not isinstance(city_objects, Mapping):
            raise RuntimeError("CityJSONFeature CityObjects missing")
        for city_object in city_objects.values():
            for geometry in city_object.get("geometry", []):
                if str(geometry.get("lod")) != "2.2":
                    continue
                if geometry.get("type") != "Solid":
                    raise RuntimeError("Roofer output is not a LoD2.2 Solid")
                semantics = geometry.get("semantics") or {}
                surface_specs = semantics.get("surfaces") or []
                semantic_values = semantics.get("values") or []
                boundaries = geometry.get("boundaries") or []
                if len(boundaries) != len(semantic_values):
                    raise RuntimeError("Roofer semantic shell count mismatch")
                for shell_index, shell in enumerate(boundaries):
                    if len(shell) != len(semantic_values[shell_index]):
                        raise RuntimeError("Roofer semantic surface count mismatch")
                    for surface_index, rings in enumerate(shell):
                        semantic_index = semantic_values[shell_index][surface_index]
                        if semantic_index is None or not 0 <= int(semantic_index) < len(surface_specs):
                            raise RuntimeError("Roofer semantic index invalid")
                        surface_type = str(surface_specs[int(semantic_index)].get("type", "UnknownSurface"))
                        for triangle in triangulate_surface(vertices, rings):
                            output.append((surface_type, triangle))
    if header_count != 1 or feature_count != 1 or not feature_id:
        raise RuntimeError("CityJSONSeq output is incomplete")
    return feature_id, output


def build_named_obj(
    method_rows: Sequence[Mapping[str, Any]],
    source_root: Path,
    scene_origin: np.ndarray,
) -> tuple[bytes, list[dict[str, Any]], dict[str, Any]]:
    lines = [
        "# JointBuildGS DEC-P1-019 building-level Roofer mesh",
        "# Scene-local coordinates; each OBJ group is B###_DEBY_LOD2_...",
    ]
    index_rows: list[dict[str, Any]] = []
    surface_counts: Counter[str] = Counter()
    vertex_offset = 1
    bounds_min = np.full(3, np.inf, dtype=np.float64)
    bounds_max = np.full(3, -np.inf, dtype=np.float64)
    completed_group_names: list[str] = []
    for row in method_rows:
        name = group_name(row)
        status = str(row["status"])
        index_row = {
            "population_index": int(row["population_index"]),
            "group_name": name,
            "condition_id": str(row["condition_id"]),
            "stable_id": str(row["stable_id"]),
            "status": status,
            "failure_code": "",
            "triangle_count": 0,
            "cityjsonseq_path": "",
            "cityjsonseq_sha256": "",
        }
        if status != "COMPLETED":
            failure = row.get("pre_roofer_failure") or {}
            index_row["failure_code"] = str(failure.get("code", "UNKNOWN_MISSING_REASON"))
            index_rows.append(index_row)
            continue
        outputs = row.get("outputs") or []
        if len(outputs) != 1:
            raise RuntimeError(f"completed row must bind one CityJSONSeq output: {name}")
        output_spec = outputs[0]
        city_path = source_root / str(output_spec["path"])
        verified = verify_bound(city_path, output_spec, f"{name} CityJSONSeq")
        try:
            feature_id, surfaces = cityjsonseq_surfaces(city_path.read_bytes(), scene_origin)
        except Exception as error:
            raise RuntimeError(f"{name} CityJSONSeq conversion failed: {error}") from error
        if feature_id != row["stable_id"]:
            raise RuntimeError(f"CityJSONSeq feature/building mismatch: {feature_id} != {row['stable_id']}")
        index_row["cityjsonseq_path"] = str(output_spec["path"])
        index_row["cityjsonseq_sha256"] = verified["sha256"]
        if not surfaces:
            index_row["status"] = "COMPLETED_NO_LOD22_GEOMETRY"
            index_row["failure_code"] = "ROOFER_OUTPUT_NO_LOD22_GEOMETRY"
            index_rows.append(index_row)
            continue
        completed_group_names.append(name)
        lines.append(f"g {name}")
        for surface_type, triangle in surfaces:
            if surface_type not in {"GroundSurface", "WallSurface", "RoofSurface"}:
                raise RuntimeError(f"unsupported Roofer surface type: {surface_type}")
            surface_counts[surface_type] += 1
            for xyz in triangle:
                lines.append(f"v {xyz[0]:.9f} {xyz[1]:.9f} {xyz[2]:.9f}")
            lines.append(f"f {vertex_offset} {vertex_offset + 1} {vertex_offset + 2}")
            vertex_offset += 3
            index_row["triangle_count"] += 1
            bounds_min = np.minimum(bounds_min, triangle.min(axis=0))
            bounds_max = np.maximum(bounds_max, triangle.max(axis=0))
        index_rows.append(index_row)
    if len(completed_group_names) != len(set(completed_group_names)) or not completed_group_names:
        raise RuntimeError("completed OBJ group names are empty or duplicated")
    stats = {
        "building_row_count": len(method_rows),
        "completed_building_group_count": len(completed_group_names),
        "explicit_missing_building_count": len(method_rows) - len(completed_group_names),
        "pre_roofer_missing_building_count": sum(row["status"] == "PRE_ROOFER_FAILED" for row in index_rows),
        "no_lod22_geometry_building_count": sum(row["status"] == "COMPLETED_NO_LOD22_GEOMETRY" for row in index_rows),
        "vertex_count": vertex_offset - 1,
        "triangle_count": (vertex_offset - 1) // 3,
        "triangle_count_by_surface": dict(sorted(surface_counts.items())),
        "local_bounds_xyz": [bounds_min.tolist(), bounds_max.tolist()],
        "group_name_pattern": "B###_DEBY_LOD2_...",
    }
    return ("\n".join(lines) + "\n").encode("ascii"), index_rows, stats


def csv_bytes(rows: Sequence[Mapping[str, Any]]) -> bytes:
    fields = [
        "population_index", "group_name", "condition_id", "stable_id", "status", "failure_code",
        "triangle_count", "cityjsonseq_path", "cityjsonseq_sha256",
    ]
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode("utf-8")


def git_value(*args: str) -> str:
    process = subprocess.run(["git", *args], cwd=REPO, text=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    return process.stdout.strip() if process.returncode == 0 else "UNKNOWN"


def extend_scene(config_path: Path, artifact_root: Path) -> Path:
    config = load_config(config_path)
    source_root = artifact_root / str(config["source"]["relative_root"])
    scene_root = artifact_root / str(config["scene"]["relative_root"])
    source_records = {
        key: verify_bound(source_root / str(config["source"][key]["path"]), config["source"][key], key)
        for key in ("finalized", "building_method_results")
    }
    scene_records = {
        key: verify_bound(scene_root / str(config["scene"][key]["path"]), config["scene"][key], key)
        for key in ("parent_manifest", "named_footprint")
    }
    finalized = json.loads((source_root / str(config["source"]["finalized"]["path"])).read_text(encoding="utf-8"))
    if finalized.get("task_id") != "P2-C1-C2-SHARED-FOOTPRINT-199-v1" or finalized.get("building_method_row_count") != 398:
        raise RuntimeError("source finalized receipt identity drift")
    rows = read_jsonl(source_root / str(config["source"]["building_method_results"]["path"]))
    grouped = validate_rows(rows, config)
    scene_origin = np.asarray(config["frame"]["scene_local_origin_xyz"], dtype=np.float64)

    layers: dict[str, Any] = {}
    all_index_rows: list[dict[str, Any]] = []
    for method, method_rows in grouped.items():
        method_spec = config["methods"][method]
        data, index_rows, stats = build_named_obj(method_rows, source_root, scene_origin)
        output_path = scene_root / "layers" / str(method_spec["output_file"])
        write_new(output_path, data)
        key = "lidar_roofer_shared_footprint" if method == "C1_L_upper" else "mvs_roofer_shared_footprint"
        if stats["completed_building_group_count"] != int(method_spec["expected_lod22_groups"]):
            raise RuntimeError(f"{method} LoD2.2 group count drift")
        if stats["no_lod22_geometry_building_count"] != int(method_spec["expected_no_lod22"]):
            raise RuntimeError(f"{method} no-LoD2.2 count drift")
        layers[key] = {
            **file_record(output_path, scene_root),
            **stats,
            "condition_id": method,
            "role": method_spec["role"],
            "shared_standard_footprint": True,
            "roofsurface_input_used": False,
            "lod2_z_used": False,
        }
        all_index_rows.extend(index_rows)

    index_path = scene_root / "control/shared_footprint_roofer_building_index_v1.csv"
    write_new(index_path, csv_bytes(sorted(all_index_rows, key=lambda row: (row["condition_id"], row["population_index"]))))
    load_order = [
        "layers/lidar_199_extent_local.laz",
        "layers/lidar_roofer_199_shared_footprint_named_local.obj",
        "layers/mvs_199_extent_local_rgb.ply",
        "layers/mvs_roofer_199_shared_footprint_named_local.obj",
        "layers/footprints_199_cloudcompare_named_local.obj",
        "layers/footprint_curtains_199_local.ply",
    ]
    manifest = {
        "schema": "jointbuildgs.p2.qualitative_199_cloudcompare_scene.shared_footprint_roofer_manifest.v1",
        "task_id": config["task_id"],
        "decision_id": config["decision_id"],
        "status": "COMPLETE_BUILDING_NAMED_SHARED_FOOTPRINT_ROOFER_BUNDLE",
        "population": {"building_count": 199, "building_method_row_count": 398},
        "frame": {
            "crs": config["frame"]["crs"],
            "scene_local_origin_xyz": config["frame"]["scene_local_origin_xyz"],
            "world_to_scene_local": "p_local = p_world - scene_local_origin_xyz",
        },
        "source_records": source_records,
        "parent_scene_records": scene_records,
        "layers": layers,
        "cloudcompare_layer_order": load_order,
        "missingness_policy": "Each method retains all 199 rows; only COMPLETED rows have an OBJ group.",
        "shared_standard_footprint": True,
        "lod2_z_used": False,
        "roofsurface_input_used": False,
        "scientific_verdict": None,
    }
    manifest_path = scene_root / "scene_manifest_shared_footprint_roofer_v1.json"
    write_new(manifest_path, canonical_json_bytes(manifest))
    readme_path = scene_root / "README_SHARED_FOOTPRINT_ROOFER_V1.txt"
    readme = """JointBuildGS 199-building shared-footprint Roofer CloudCompare scene

Load these files together, in this order:
1. layers/lidar_199_extent_local.laz
2. layers/lidar_roofer_199_shared_footprint_named_local.obj
3. layers/mvs_199_extent_local_rgb.ply
4. layers/mvs_roofer_199_shared_footprint_named_local.obj
5. layers/footprints_199_cloudcompare_named_local.obj
6. layers/footprint_curtains_199_local.ply

All files already use the same scene-local coordinates. Do not add another shift.
Expand the two Roofer OBJ files and the footprint OBJ in the DB Tree. Building groups
are named B###_DEBY_LOD2_.... CloudCompare 2.13.x imports DXF entities as generic
Polyline names, so do not use footprints_199_local.dxf for building-name lookup.

The Roofer OBJ files contain only completed buildings. Missing rows remain explicit in
control/shared_footprint_roofer_building_index_v1.csv and are never replaced or faked.
"""
    write_new(readme_path, readme.encode("utf-8"))
    receipt_path = scene_root / "control/shared_footprint_roofer_extension_receipt_v1.json"
    receipt = {
        "schema": "jointbuildgs.p2.qualitative_199_cloudcompare_scene.shared_footprint_roofer_receipt.v1",
        "task_id": config["task_id"],
        "completed_at_utc": datetime.now(timezone.utc).isoformat(),
        "git_commit": git_value("rev-parse", "HEAD"),
        "git_status_porcelain": git_value("status", "--porcelain"),
        "config": file_record(config_path, REPO),
        "script": file_record(Path(__file__).resolve(), REPO),
        "roofer_invocations": 0,
        "reconstruction_invocations": 0,
        "gs_training_invocations": 0,
        "scientific_verdict": None,
    }
    write_new(receipt_path, canonical_json_bytes(receipt))
    artifact_manifest_path = scene_root / "control/shared_footprint_roofer_artifact_manifest_v1.json"
    artifact_manifest = {
        "schema": "jointbuildgs.p2.qualitative_199_cloudcompare_scene.shared_footprint_roofer_artifacts.v1",
        "task_id": config["task_id"],
        "records": [
            layers["lidar_roofer_shared_footprint"],
            layers["mvs_roofer_shared_footprint"],
            file_record(index_path, scene_root),
            file_record(manifest_path, scene_root),
            file_record(readme_path, scene_root),
            file_record(receipt_path, scene_root),
        ],
        "scientific_verdict": None,
    }
    write_new(artifact_manifest_path, canonical_json_bytes(artifact_manifest))
    return manifest_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--artifact-root", type=Path, default=Path(os.environ.get("JBGS_ARTIFACT_ROOT", "../JointBuildGS-artifacts")))
    args = parser.parse_args()
    print(extend_scene(args.config.resolve(), args.artifact_root.resolve()))


if __name__ == "__main__":
    main()
