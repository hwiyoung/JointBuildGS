#!/usr/bin/env python3
"""Add previous LiDAR/MVS Roofer meshes to the full CloudCompare scene."""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
from typing import Any, Mapping, Sequence

import numpy as np
from shapely.geometry import Polygon
from shapely.ops import triangulate

from scripts.p2.qualitative_199_cloudcompare_scene_v1.build_scene import (
    REPO,
    canonical_json_bytes,
    file_record,
    sha256_file,
    write_new,
)


DEFAULT_CONFIG = REPO / "configs/p2/qualitative_199_cloudcompare_scene_v1/add_previous_roofer_v1.json"


def load_config(path: Path) -> dict[str, Any]:
    config = json.loads(path.read_text(encoding="utf-8"))
    if config.get("schema") != "jointbuildgs.p2.qualitative_199_cloudcompare_scene.previous_roofer_extension.v1":
        raise RuntimeError("unexpected Roofer extension config schema")
    if config.get("status") != "USER_APPROVED_VISUAL_DIAGNOSTIC_REUSE":
        raise RuntimeError("previous Roofer visual reuse is not user-approved")
    if config.get("formal_six_row_reuse_allowed") is not False:
        raise RuntimeError("historical MVS Roofer must not be authorized for the formal six-row result")
    if config.get("scientific_verdict", "missing") is not None:
        raise RuntimeError("scientific_verdict must remain null")
    execution = config["execution"]
    if any(int(execution[name]) != 0 for name in ("roofer_invocations", "reconstruction_invocations", "gs_training_invocations")):
        raise RuntimeError("extension must reuse outputs without execution")
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


def transformed_vertices(feature: Mapping[str, Any], transform: Mapping[str, Any], scene_origin: np.ndarray) -> np.ndarray:
    scale = np.asarray(transform.get("scale"), dtype=np.float64)
    translate = np.asarray(transform.get("translate"), dtype=np.float64)
    vertices = np.asarray(feature.get("vertices"), dtype=np.float64)
    if scale.shape != (3,) or translate.shape != (3,) or vertices.ndim != 2 or vertices.shape[1] != 3:
        raise RuntimeError("invalid CityJSONSeq transform or vertices")
    result = vertices * scale + translate - scene_origin
    if not np.isfinite(result).all():
        raise RuntimeError("non-finite transformed Roofer vertex")
    return result


def triangulate_ring(vertices: np.ndarray, ring: Sequence[int]) -> list[np.ndarray]:
    indices = list(map(int, ring))
    if len(indices) >= 2 and indices[0] == indices[-1]:
        indices = indices[:-1]
    if len(indices) < 3 or min(indices) < 0 or max(indices) >= len(vertices):
        raise RuntimeError("invalid Roofer surface ring")
    xyz = vertices[indices]
    normal = np.zeros(3, dtype=np.float64)
    for index in range(len(xyz)):
        current = xyz[index]
        following = xyz[(index + 1) % len(xyz)]
        normal += np.cross(current, following)
    drop_axis = int(np.argmax(np.abs(normal)))
    keep_axes = [axis for axis in range(3) if axis != drop_axis]
    xy = xyz[:, keep_axes]
    polygon = Polygon(xy)
    if not polygon.is_valid:
        polygon = polygon.buffer(0)
    if polygon.is_empty or polygon.geom_type != "Polygon":
        raise RuntimeError("invalid projected Roofer surface polygon")
    output = []
    for triangle in triangulate(polygon):
        if not polygon.covers(triangle):
            continue
        tri_xy = np.asarray(triangle.exterior.coords[:-1], dtype=np.float64)
        tri_xyz = []
        for point in tri_xy:
            distances = np.linalg.norm(xy - point, axis=1)
            nearest = int(np.argmin(distances))
            if float(distances[nearest]) > 1.0e-7:
                raise RuntimeError("triangulation introduced a non-source Roofer vertex")
            tri_xyz.append(xyz[nearest])
        triangle_xyz = np.asarray(tri_xyz, dtype=np.float64)
        if np.linalg.norm(np.cross(triangle_xyz[1] - triangle_xyz[0], triangle_xyz[2] - triangle_xyz[0])) > 1.0e-12:
            output.append(triangle_xyz)
    if not output:
        raise RuntimeError("Roofer surface produced no triangles")
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
            raise RuntimeError("expected one Roofer feature per component output")
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
                    raise RuntimeError("previous Roofer output is not a LoD2.2 Solid")
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
                        if len(rings) != 1:
                            raise RuntimeError("Roofer display exporter does not accept holes")
                        semantic_index = semantic_values[shell_index][surface_index]
                        if semantic_index is None or not 0 <= int(semantic_index) < len(surface_specs):
                            raise RuntimeError("Roofer semantic index invalid")
                        surface_type = str(surface_specs[int(semantic_index)].get("type", "UnknownSurface"))
                        for triangle in triangulate_ring(vertices, rings[0]):
                            output.append((surface_type, triangle))
    if header_count != 1 or feature_count != 1 or not feature_id or not output:
        raise RuntimeError("CityJSONSeq output is incomplete")
    return feature_id, output


def source_components(
    source_root: Path,
    units: Sequence[Mapping[str, Any]],
    metrics: Sequence[Mapping[str, Any]],
    method: str,
    expected_components: int,
    expected_associated: int,
) -> list[dict[str, Any]]:
    usage = Counter(str(row["component_id"]) for row in metrics if row.get("method_id") == method and row.get("component_id"))
    associated = sum(usage.values())
    if associated != expected_associated:
        raise RuntimeError(f"{method} associated-building count drift: {associated} != {expected_associated}")
    selected = sorted((row for row in units if row.get("condition_id") == method), key=lambda row: str(row["component_id"]))
    if len(selected) != expected_components:
        raise RuntimeError(f"{method} component count drift: {len(selected)} != {expected_components}")
    records = []
    for unit in selected:
        terminal_path = source_root / str(unit["terminal_record"])
        terminal = json.loads(terminal_path.read_text(encoding="utf-8"))
        if terminal.get("operation_unit_id") != unit.get("operation_unit_id") or not str(terminal.get("status", "")).startswith("COMPLETED"):
            raise RuntimeError(f"invalid previous Roofer terminal: {terminal_path}")
        outputs = terminal.get("output_records") or []
        if len(outputs) != 1:
            raise RuntimeError(f"previous Roofer terminal must bind one output: {terminal_path}")
        output_spec = outputs[0]
        city_path = source_root / str(output_spec["path"])
        city_record = verify_bound(city_path, output_spec, "previous Roofer CityJSONSeq")
        terminal_record = file_record(terminal_path, source_root)
        component_id = str(unit["component_id"])
        records.append(
            {
                "method_id": method,
                "component_id": component_id,
                "operation_unit_id": unit["operation_unit_id"],
                "associated_building_count": int(usage.get(component_id, 0)),
                "terminal": terminal_record,
                "cityjsonseq": city_record,
                "cityjsonseq_path": city_path,
            }
        )
    return records


def write_mesh(
    output: Path,
    components: Sequence[Mapping[str, Any]],
    scene_origin: np.ndarray,
    colors: Mapping[str, Sequence[int]],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    vertex_dtype = np.dtype(
        [
            ("x", "<f4"), ("y", "<f4"), ("z", "<f4"),
            ("red", "u1"), ("green", "u1"), ("blue", "u1"),
            ("surface_code", "u1"), ("component_index", "<u2"),
        ]
    )
    face_dtype = np.dtype(
        [("count", "u1"), ("v0", "<i4"), ("v1", "<i4"), ("v2", "<i4"), ("surface_code", "u1"), ("component_index", "<u2")]
    )
    surface_codes = {"GroundSurface": 0, "WallSurface": 1, "RoofSurface": 2}
    vertex_rows = []
    face_rows = []
    index_rows = []
    type_counts: Counter[str] = Counter()
    bounds_min = np.full(3, np.inf, dtype=np.float64)
    bounds_max = np.full(3, -np.inf, dtype=np.float64)
    for component_index, component in enumerate(components, start=1):
        data = Path(component["cityjsonseq_path"]).read_bytes()
        feature_id, surfaces = cityjsonseq_surfaces(data, scene_origin)
        if feature_id != component["component_id"]:
            raise RuntimeError(f"CityJSONSeq feature/component mismatch: {feature_id}")
        component_triangles = 0
        for surface_type, triangle in surfaces:
            if surface_type not in surface_codes or surface_type not in colors:
                raise RuntimeError(f"unsupported Roofer surface type: {surface_type}")
            rgb = list(map(int, colors[surface_type]))
            start = len(vertex_rows)
            code = surface_codes[surface_type]
            for xyz in triangle:
                vertex_rows.append((xyz[0], xyz[1], xyz[2], rgb[0], rgb[1], rgb[2], code, component_index))
            face_rows.append((3, start, start + 1, start + 2, code, component_index))
            type_counts[surface_type] += 1
            component_triangles += 1
            bounds_min = np.minimum(bounds_min, triangle.min(axis=0))
            bounds_max = np.maximum(bounds_max, triangle.max(axis=0))
        index_rows.append(
            {
                "component_index": component_index,
                "method_id": component["method_id"],
                "component_id": component["component_id"],
                "associated_building_count": component["associated_building_count"],
                "triangle_count": component_triangles,
                "cityjsonseq_path": component["cityjsonseq"]["path"],
                "cityjsonseq_sha256": component["cityjsonseq"]["sha256"],
            }
        )
    vertices = np.asarray(vertex_rows, dtype=vertex_dtype)
    faces = np.asarray(face_rows, dtype=face_dtype)
    header = (
        "ply\nformat binary_little_endian 1.0\n"
        "comment JointBuildGS previous Roofer visual diagnostic\n"
        "comment coordinates are scene-local; see scene_manifest_6layers.json\n"
        f"element vertex {len(vertices)}\n"
        "property float x\nproperty float y\nproperty float z\n"
        "property uchar red\nproperty uchar green\nproperty uchar blue\n"
        "property uchar surface_code\nproperty ushort component_index\n"
        f"element face {len(faces)}\n"
        "property list uchar int vertex_indices\n"
        "property uchar surface_code\nproperty ushort component_index\nend_header\n"
    ).encode("ascii")
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("xb") as stream:
        stream.write(header)
        stream.write(vertices.tobytes(order="C"))
        stream.write(faces.tobytes(order="C"))
    return (
        {
            "component_count": len(components),
            "associated_building_count": sum(int(row["associated_building_count"]) for row in components),
            "vertex_count": len(vertices),
            "triangle_count": len(faces),
            "triangle_count_by_surface": dict(sorted(type_counts.items())),
            "local_bounds_xyz": [bounds_min.tolist(), bounds_max.tolist()],
            "surface_code_map": surface_codes,
        },
        index_rows,
    )


def git_value(*args: str) -> str:
    process = subprocess.run(["git", *args], cwd=REPO, text=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    return process.stdout.strip() if process.returncode == 0 else "UNKNOWN"


def extend_scene(config_path: Path, artifact_root: Path) -> Path:
    config = load_config(config_path)
    parent_spec = config["parent_scene"]
    parent_root = artifact_root / str(parent_spec["relative_root"])
    parent_manifest_path = parent_root / str(parent_spec["manifest_path"])
    parent_record = verify_bound(
        parent_manifest_path,
        {"bytes": parent_spec["manifest_bytes"], "sha256": parent_spec["manifest_sha256"]},
        "parent four-layer scene manifest",
    )
    parent_manifest = json.loads(parent_manifest_path.read_text(encoding="utf-8"))
    if parent_manifest.get("task_id") != config["parent_task_id"] or parent_manifest.get("population", {}).get("building_count") != 199:
        raise RuntimeError("parent scene identity drift")

    source_root = artifact_root / str(config["source"]["relative_root"])
    source_records = {}
    for key in ("prepared", "finalized", "execution_units", "building_method_metrics"):
        spec = config["source"][key]
        source_records[key] = verify_bound(source_root / str(spec["path"]), spec, key)
    units = read_jsonl(source_root / str(config["source"]["execution_units"]["path"]))
    metrics = read_jsonl(source_root / str(config["source"]["building_method_metrics"]["path"]))
    if len(metrics) != 597:
        raise RuntimeError("historical building-method metrics row count drift")
    scene_origin = np.asarray(parent_manifest["frame"]["scene_local_origin_xyz"], dtype=np.float64)

    new_layers = {}
    all_index_rows = []
    for method, method_spec in config["methods"].items():
        components = source_components(
            source_root,
            units,
            metrics,
            method,
            int(method_spec["expected_component_count"]),
            int(method_spec["expected_associated_building_count"]),
        )
        output = parent_root / "layers" / str(method_spec["output_file"])
        stats, index_rows = write_mesh(output, components, scene_origin, method_spec["colors"])
        key = "previous_lidar_roofer" if method == "C1_L_upper" else "previous_mvs_roofer"
        new_layers[key] = {
            **file_record(output, parent_root),
            **stats,
            "method_id": method,
            "role": method_spec["role"],
            "lineage_compatibility_with_parent_cloud": method_spec["lineage_compatibility_with_parent_cloud"],
            "formal_six_row_reuse_allowed": False,
        }
        all_index_rows.extend(index_rows)

    index_path = parent_root / "control/historical_roofer_component_index_v1.csv"
    index_lines = ["component_index,method_id,component_id,associated_building_count,triangle_count,cityjsonseq_path,cityjsonseq_sha256"]
    for row in all_index_rows:
        index_lines.append(
            f"{row['component_index']},{row['method_id']},{row['component_id']},{row['associated_building_count']},{row['triangle_count']},{row['cityjsonseq_path']},{row['cityjsonseq_sha256']}"
        )
    write_new(index_path, ("\n".join(index_lines) + "\n").encode("utf-8"))

    six_layers = dict(parent_manifest["layers"])
    six_layers.update(new_layers)
    layer_order = [
        "layers/lidar_199_extent_local.laz",
        "layers/lidar_roofer_previous_local.ply",
        "layers/mvs_199_extent_local_rgb.ply",
        "layers/mvs_roofer_previous_local.ply",
        "layers/footprints_199_local.dxf",
        "layers/footprint_curtains_199_local.ply",
    ]
    extension_manifest = {
        **parent_manifest,
        "schema": "jointbuildgs.p2.qualitative_199_cloudcompare_scene.six_layer_visual_manifest.v1",
        "task_id": config["task_id"],
        "parent_task_id": config["parent_task_id"],
        "status": "COMPLETE_SIX_LAYER_VISUAL_DIAGNOSTIC_BUNDLE",
        "parent_scene_manifest": parent_record,
        "historical_roofer_source_records": source_records,
        "layers": six_layers,
        "cloudcompare_layer_order": layer_order,
        "historical_roofer_policy": {
            "LiDAR_Roofer": "same current UAS LiDAR source; previous component output reused",
            "MVS_Roofer": "historical C2 dense lineage; visual diagnostic only and not row-5 authority",
            "new_Roofer_invocations": 0,
            "missingness_preserved": True,
            "formal_six_row_reuse_allowed": False,
        },
        "next_stage_authorized": False,
        "scientific_verdict": None,
    }
    manifest_path = parent_root / "scene_manifest_6layers.json"
    write_new(manifest_path, canonical_json_bytes(extension_manifest))
    readme = """JointBuildGS 199-building CloudCompare six-layer visual scene

Load these six files together, in this order:
1. layers/lidar_199_extent_local.laz
2. layers/lidar_roofer_previous_local.ply
3. layers/mvs_199_extent_local_rgb.ply
4. layers/mvs_roofer_previous_local.ply
5. layers/footprints_199_local.dxf
6. layers/footprint_curtains_199_local.ply

All files already share the same scene-local coordinates. Do not add another shift.

Important lineage label:
- lidar_roofer_previous_local.ply reuses the previous current-UAS-LiDAR Roofer output.
- mvs_roofer_previous_local.ply reuses historical C2 output for visual diagnosis only.
  It was not derived from the recovered-v2 MVS PLY displayed in this bundle and must
  not be used as the formal row-5 result.
- Missing/unassociated buildings remain missing. No Roofer process was run here.

See scene_manifest_6layers.json and control/historical_roofer_component_index_v1.csv.
"""
    readme_path = parent_root / "README_6LAYERS.txt"
    write_new(readme_path, readme.encode("utf-8"))
    receipt = {
        "schema": "jointbuildgs.p2.qualitative_199_cloudcompare_scene.previous_roofer_extension.run_receipt.v1",
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
    receipt_path = parent_root / "control/roofer_extension_run_receipt_v1.json"
    write_new(receipt_path, canonical_json_bytes(receipt))
    artifact_manifest = {
        "schema": "jointbuildgs.p2.qualitative_199_cloudcompare_scene.previous_roofer_extension.artifact_manifest.v1",
        "task_id": config["task_id"],
        "records": [
            new_layers["previous_lidar_roofer"],
            new_layers["previous_mvs_roofer"],
            file_record(index_path, parent_root),
            file_record(manifest_path, parent_root),
            file_record(readme_path, parent_root),
            file_record(receipt_path, parent_root),
        ],
        "scientific_verdict": None,
    }
    artifact_manifest_path = parent_root / "control/roofer_extension_artifact_manifest_v1.json"
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
