#!/usr/bin/env python3
"""Prepare and close 199 building-specific C1/C2 Roofer operations with one shared footprint."""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from datetime import datetime, timezone
import io
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
from typing import Any, BinaryIO, Mapping, Sequence
import xml.etree.ElementTree as ET

import laspy
import numpy as np
from shapely import contains_xy, prepare as prepare_geometry
from shapely.geometry import MultiPolygon, Polygon, mapping
from shapely.ops import unary_union

from scripts.p2.qualitative_199_cloudcompare_scene_v1.build_scene import (
    POINT_DTYPE,
    REPO,
    canonical_json_bytes,
    file_record,
    read_mvs_header,
    sha256_file,
    write_new,
)


CONFIG_PATH = REPO / "configs/p2/c1_c2_shared_footprint_199_v1/run_v1.json"
METHODS = ("C1_L_upper", "C2_MVS")


@dataclass(frozen=True)
class FootprintReference:
    stable_id: str
    footprint: Polygon | MultiPolygon


@dataclass(frozen=True)
class SpatialBins:
    bin_m: float
    min_bx: int
    min_by: int
    stride_y: int
    global_bounds: tuple[float, float, float, float]
    building_bounds: Mapping[str, tuple[float, float, float, float]]
    candidates: Mapping[int, tuple[str, ...]]


def jsonl_bytes(rows: Sequence[Mapping[str, Any]]) -> bytes:
    return b"".join(canonical_json_bytes(row) for row in rows)


def load_config(path: Path = CONFIG_PATH) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def validate_config(config: Mapping[str, Any]) -> None:
    identities = {
        "jointbuildgs.p2.c1_c2_shared_footprint_199.v1": "P2-C1-C2-SHARED-FOOTPRINT-199-v1",
        "jointbuildgs.p2.c1_c2_shared_footprint_199.all_invocations.v2": "P2-C1-C2-SHARED-FOOTPRINT-199-ALL-INVOCATIONS-v2",
    }
    if config.get("schema") not in identities:
        raise RuntimeError("shared-footprint config schema drifted")
    if config.get("task_id") != identities[config["schema"]] or config.get("decision_id") != "DEC-P1-019":
        raise RuntimeError("shared-footprint task/decision identity drifted")
    if config.get("status") != "USER_APPROVED_FOR_EXECUTION":
        raise RuntimeError("shared-footprint execution is not user-approved")
    if int(config["population"]["building_count"]) != 199:
        raise RuntimeError("population must be exact U_target 199")
    if tuple(config.get("methods") or ()) != METHODS:
        raise RuntimeError("method order must be exact C1 then C2")
    if config["inputs"]["shared_footprint_allowed_fields"] != ["gml:id", "GroundSurface exterior/interior XY"]:
        raise RuntimeError("shared footprint allowed-field boundary drifted")
    prohibited = set(config["inputs"]["shared_footprint_prohibited_fields"])
    if not {"GroundSurface Z", "RoofSurface XYZ", "roof type", "final roof model"}.issubset(prohibited):
        raise RuntimeError("shared footprint prohibited-field boundary drifted")
    if int(config["execution"]["expected_building_method_rows"]) != 398:
        raise RuntimeError("expected result row count must be 398")
    if config["schema"].endswith("all_invocations.v2"):
        if config["execution"].get("attempt_all_building_method_rows") is not True:
            raise RuntimeError("v2 must invoke Roofer for all 398 building-method rows")
        if int(config["execution"].get("expected_roofer_invocations", 0)) != 398:
            raise RuntimeError("v2 must expect exact 398 Roofer invocations")
    if config.get("official_PASS_usable", "missing") is not None or config.get("scientific_verdict", "missing") is not None:
        raise RuntimeError("official PASS and scientific verdict must remain null")


def exact_file(path: Path, spec: Mapping[str, Any]) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise RuntimeError(f"exact input missing or non-regular: {path}")
    size, digest = sha256_file(path)
    if size != int(spec["bytes"]) or digest != str(spec["sha256"]):
        raise RuntimeError(f"exact input drift: {path} bytes={size} sha256={digest}")
    return {"path": path.as_posix(), "bytes": size, "sha256": digest, "full_hash_passes": 1}


def read_population(path: Path, expected: Mapping[str, Any]) -> list[dict[str, Any]]:
    exact_file(path, {"bytes": expected["common_manifest_bytes"], "sha256": expected["common_manifest_sha256"]})
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if len(rows) != 199 or len({str(row["building_id"]) for row in rows}) != 199:
        raise RuntimeError("common manifest is not exact 199 unique buildings")
    if [int(row["population_index"]) for row in rows] != list(range(1, 200)):
        raise RuntimeError("common manifest population order drifted")
    return rows


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _element_id(element: ET.Element) -> str | None:
    for key, value in element.attrib.items():
        if key == "id" or key.endswith("}id"):
            return str(value)
    return None


def _ring_xy(boundary: ET.Element) -> np.ndarray | None:
    pos_list = next((node for node in boundary.iter() if _local_name(node.tag) == "posList"), None)
    if pos_list is None or not pos_list.text:
        return None
    values = np.fromstring(pos_list.text, sep=" ", dtype=np.float64)
    dimension = int(pos_list.attrib.get("srsDimension", "3"))
    if dimension not in (2, 3) or len(values) < dimension * 3 or len(values) % dimension:
        raise RuntimeError("invalid GroundSurface polygon boundary")
    xy = values.reshape((-1, dimension))[:, :2]
    if not np.allclose(xy[0], xy[-1]):
        xy = np.vstack((xy, xy[0]))
    return xy


def load_groundsurface_xy(paths: Sequence[Path], building_ids: Sequence[str]) -> dict[str, FootprintReference]:
    wanted = set(map(str, building_ids))
    found: dict[str, FootprintReference] = {}
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
                for surface in building.iter():
                    if _local_name(surface.tag) != "GroundSurface":
                        continue
                    for polygon_element in surface.iter():
                        if _local_name(polygon_element.tag) != "Polygon":
                            continue
                        exterior_node = next((node for node in polygon_element if _local_name(node.tag) == "exterior"), None)
                        if exterior_node is None:
                            continue
                        exterior = _ring_xy(exterior_node)
                        if exterior is None:
                            continue
                        interiors = []
                        for node in polygon_element:
                            if _local_name(node.tag) == "interior":
                                ring = _ring_xy(node)
                                if ring is not None:
                                    interiors.append(ring)
                        polygon = Polygon(exterior, interiors)
                        if not polygon.is_valid:
                            polygon = polygon.buffer(0)
                        if polygon.is_empty:
                            raise RuntimeError(f"empty GroundSurface XY: {stable_id}")
                        polygons.append(polygon)
                if not polygons:
                    raise RuntimeError(f"GroundSurface XY missing: {stable_id}")
                footprint = unary_union(polygons)
                if not isinstance(footprint, (Polygon, MultiPolygon)):
                    raise RuntimeError(f"unsupported GroundSurface geometry: {stable_id} {footprint.geom_type}")
                found[str(stable_id)] = FootprintReference(str(stable_id), footprint)
            building.clear()
    missing = sorted(wanted - set(found))
    if missing:
        raise RuntimeError(f"GroundSurface XY missing for {len(missing)} buildings: {missing[:5]}")
    return found


def shared_footprint_geojson(reference: FootprintReference) -> dict[str, Any]:
    return {
        "type": "FeatureCollection",
        "name": "R_SHARED_GROUNDSURFACE_XY_V1",
        "crs": {"type": "name", "properties": {"name": "urn:ogc:def:crs:EPSG::25832"}},
        "features": [{
            "type": "Feature",
            "properties": {
                "stable_id": reference.stable_id,
                "input_role": "SHARED_STANDARD_GROUNDSURFACE_XY_CONTROL",
                "lod2_z_used": False,
                "roofsurface_used": False,
            },
            "geometry": mapping(reference.footprint),
        }],
    }


def build_spatial_bins(references: Mapping[str, FootprintReference], buffer_m: float, bin_m: float) -> SpatialBins:
    bounds = {
        stable_id: tuple(float(value) for value in reference.footprint.buffer(buffer_m).bounds)
        for stable_id, reference in references.items()
    }
    min_bx = min(math.floor(value[0] / bin_m) for value in bounds.values())
    max_bx = max(math.floor(value[2] / bin_m) for value in bounds.values())
    min_by = min(math.floor(value[1] / bin_m) for value in bounds.values())
    max_by = max(math.floor(value[3] / bin_m) for value in bounds.values())
    stride_y = max_by - min_by + 1
    candidates: dict[int, list[str]] = {}
    for stable_id, (x0, y0, x1, y1) in bounds.items():
        for bx in range(math.floor(x0 / bin_m), math.floor(x1 / bin_m) + 1):
            for by in range(math.floor(y0 / bin_m), math.floor(y1 / bin_m) + 1):
                key = (bx - min_bx) * stride_y + (by - min_by)
                candidates.setdefault(key, []).append(stable_id)
    return SpatialBins(
        bin_m=bin_m,
        min_bx=min_bx,
        min_by=min_by,
        stride_y=stride_y,
        global_bounds=(
            min(value[0] for value in bounds.values()),
            min(value[1] for value in bounds.values()),
            max(value[2] for value in bounds.values()),
            max(value[3] for value in bounds.values()),
        ),
        building_bounds=bounds,
        candidates={key: tuple(sorted(values)) for key, values in candidates.items()},
    )


def scatter_chunk(xyz: np.ndarray, bins: SpatialBins, handles: Mapping[str, BinaryIO]) -> int:
    values = np.asarray(xyz, dtype=np.float64)
    x0, y0, x1, y1 = bins.global_bounds
    keep = (
        np.isfinite(values).all(axis=1)
        & (values[:, 0] >= x0) & (values[:, 0] <= x1)
        & (values[:, 1] >= y0) & (values[:, 1] <= y1)
    )
    values = values[keep]
    if not len(values):
        return 0
    bx = np.floor(values[:, 0] / bins.bin_m).astype(np.int64)
    by = np.floor(values[:, 1] / bins.bin_m).astype(np.int64)
    keys = (bx - bins.min_bx) * bins.stride_y + (by - bins.min_by)
    order = np.argsort(keys, kind="stable")
    sorted_keys = keys[order]
    starts = np.r_[0, np.flatnonzero(sorted_keys[1:] != sorted_keys[:-1]) + 1]
    ends = np.r_[starts[1:], len(order)]
    written = 0
    for start, end in zip(starts, ends):
        candidates = bins.candidates.get(int(sorted_keys[start]))
        if not candidates:
            continue
        group = values[order[start:end]]
        for stable_id in candidates:
            bx0, by0, bx1, by1 = bins.building_bounds[stable_id]
            local = group[
                (group[:, 0] >= bx0) & (group[:, 0] <= bx1)
                & (group[:, 1] >= by0) & (group[:, 1] <= by1)
            ]
            if len(local):
                handles[stable_id].write(np.asarray(local, dtype="<f8").tobytes())
                written += len(local)
    return written


def _open_scratch_handles(scratch: Path, building_ids: Sequence[str]) -> dict[str, BinaryIO]:
    scratch.mkdir(parents=True)
    return {stable_id: (scratch / f"{stable_id}.xyzf64").open("xb") for stable_id in building_ids}


def collect_lidar(path: Path, scratch: Path, references: Mapping[str, FootprintReference], bins: SpatialBins) -> dict[str, Any]:
    handles = _open_scratch_handles(scratch, sorted(references))
    source_count = 0
    duplicated_crop_rows = 0
    try:
        with laspy.open(path) as stream:
            for points in stream.chunk_iterator(2_000_000):
                xyz = np.column_stack((np.asarray(points.x), np.asarray(points.y), np.asarray(points.z)))
                source_count += len(xyz)
                duplicated_crop_rows += scatter_chunk(xyz, bins, handles)
    finally:
        for handle in handles.values():
            handle.close()
    return {"source_point_count": source_count, "duplicated_bbox_crop_row_count": duplicated_crop_rows, "source_scan_passes": 1}


def collect_mvs(path: Path, scratch: Path, references: Mapping[str, FootprintReference], bins: SpatialBins, shift_xyz: Sequence[float]) -> dict[str, Any]:
    offset, count = read_mvs_header(path)
    data = np.memmap(path, mode="r", dtype=POINT_DTYPE, offset=offset, shape=(count,))
    shift = np.asarray(shift_xyz, dtype=np.float64)
    handles = _open_scratch_handles(scratch, sorted(references))
    duplicated_crop_rows = 0
    try:
        for start in range(0, count, 2_000_000):
            rows = data[start:min(count, start + 2_000_000)]
            xyz = np.column_stack((rows["x"], rows["y"], rows["z"])).astype(np.float64) + shift
            duplicated_crop_rows += scatter_chunk(xyz, bins, handles)
    finally:
        for handle in handles.values():
            handle.close()
    return {"source_point_count": count, "duplicated_bbox_crop_row_count": duplicated_crop_rows, "source_scan_passes": 1}


def deterministic_voxel_one(points: np.ndarray, voxel_m: float) -> np.ndarray:
    values = np.asarray(points, dtype=np.float64).reshape((-1, 3))
    if not len(values):
        return values
    keys = np.floor(values / voxel_m).astype(np.int64)
    shifted = keys - keys.min(axis=0)
    spans = shifted.max(axis=0) + 1
    if int(spans[0]) * int(spans[1]) * int(spans[2]) > np.iinfo(np.int64).max:
        raise RuntimeError("voxel key range exceeds collision-free int64 packing")
    packed = (shifted[:, 0] * spans[1] + shifted[:, 1]) * spans[2] + shifted[:, 2]
    _unique, first = np.unique(packed, return_index=True)
    return values[np.sort(first)]


def classify_points(points: np.ndarray, reference: FootprintReference, preparation: Mapping[str, Any]) -> tuple[np.ndarray, np.ndarray, dict[str, Any], dict[str, Any] | None]:
    values = np.asarray(points, dtype=np.float64).reshape((-1, 3))
    if not len(values):
        return values, values, {"source_bbox_crop_point_count": 0}, {"code": "PRE_ROOFER_EMPTY_SOURCE_CROP"}
    footprint = reference.footprint
    inner_buffer = footprint.buffer(float(preparation["ground_ring_inner_buffer_m"]))
    prepare_geometry(footprint)
    prepare_geometry(inner_buffer)
    inside = contains_xy(footprint, values[:, 0], values[:, 1])
    outside_inner = ~contains_xy(inner_buffer, values[:, 0], values[:, 1])
    ground_candidates = values[outside_inner]
    if len(ground_candidates) < 10:
        return values[inside][:0], ground_candidates, {
            "source_bbox_crop_point_count": int(len(values)),
            "inside_footprint_point_count": int(np.count_nonzero(inside)),
            "ground_candidate_point_count": int(len(ground_candidates)),
        }, {"code": "PRE_ROOFER_INSUFFICIENT_GROUND_CANDIDATES", "observed": int(len(ground_candidates)), "minimum": 10}
    keys = np.floor(ground_candidates[:, :2] / float(preparation["ground_height_cell_m"])).astype(np.int64)
    _, inverse = np.unique(keys, axis=0, return_inverse=True)
    minima = np.full(int(inverse.max()) + 1, np.inf, dtype=np.float64)
    np.minimum.at(minima, inverse, ground_candidates[:, 2])
    ground_z = float(np.median(minima[np.isfinite(minima)]))
    building = values[inside & (values[:, 2] >= ground_z + float(preparation["minimum_building_height_above_local_ground_m"]))]
    ground = values[(~inside) & outside_inner & (values[:, 2] <= ground_z + float(preparation["ground_keep_above_local_ground_m"]))]
    building = deterministic_voxel_one(building, float(preparation["deterministic_voxel_m"]))
    ground = deterministic_voxel_one(ground, float(preparation["deterministic_voxel_m"]))
    stats = {
        "source_bbox_crop_point_count": int(len(values)),
        "inside_footprint_point_count": int(np.count_nonzero(inside)),
        "building_class6_count": int(len(building)),
        "ground_class2_count": int(len(ground)),
        "local_ground_z_from_point_evidence": ground_z,
        "footprint_area_m2": float(footprint.area),
    }
    minimum = int(preparation["minimum_roofer_class6_points"])
    if not len(ground):
        return building, ground, stats, {"code": "PRE_ROOFER_EMPTY_CLASS2_GROUND"}
    if len(building) < minimum:
        return building, ground, stats, {"code": "PRE_ROOFER_INSUFFICIENT_CLASS6_EVIDENCE", "observed": int(len(building)), "minimum": minimum}
    return building, ground, stats, None


def write_classified_las(
    path: Path,
    building: np.ndarray,
    ground: np.ndarray,
    empty_offset_xyz: Sequence[float] | None = None,
) -> None:
    xyz = np.vstack((building, ground))
    classes = np.concatenate((np.full(len(building), 6, dtype=np.uint8), np.full(len(ground), 2, dtype=np.uint8)))
    header = laspy.LasHeader(point_format=3, version="1.2")
    header.scales = np.asarray([0.001, 0.001, 0.001])
    if len(xyz):
        header.offsets = np.floor(np.min(xyz, axis=0) / 1000.0) * 1000.0
    else:
        if empty_offset_xyz is None:
            raise RuntimeError("empty Roofer LAS requires an explicit deterministic offset")
        header.offsets = np.floor(np.asarray(empty_offset_xyz, dtype=np.float64) / 1000.0) * 1000.0
    header.system_identifier = "JOINTBUILDGS"
    header.generating_software = "C1C2-RSHARED-v1"
    las = laspy.LasData(header)
    if len(xyz):
        las.x, las.y, las.z = xyz.T
        las.classification = classes
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise RuntimeError(f"refusing to overwrite LAS: {path}")
    las.write(path)


def prepare_method(
    output_root: Path,
    scratch: Path,
    method: str,
    population: Sequence[Mapping[str, Any]],
    references: Mapping[str, FootprintReference],
    preparation: Mapping[str, Any],
    attempt_all: bool,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in population:
        index = int(item["population_index"])
        stable_id = str(item["building_id"])
        raw_path = scratch / f"{stable_id}.xyzf64"
        if raw_path.stat().st_size % 24:
            raise RuntimeError(f"scratch XYZ byte drift: {raw_path}")
        points = np.fromfile(raw_path, dtype="<f8").reshape((-1, 3))
        building, ground, stats, failure = classify_points(points, references[stable_id], preparation)
        work = output_root / "operations" / method / f"B{index:03d}_{stable_id}" / "work"
        footprint_path = work / "shared_footprint.geojson"
        write_new(footprint_path, canonical_json_bytes(shared_footprint_geojson(references[stable_id])))
        input_record = None
        if len(building) + len(ground) or attempt_all:
            input_path = work / "input.las"
            centroid = references[stable_id].footprint.centroid
            write_classified_las(input_path, building, ground, [centroid.x, centroid.y, 0.0])
            input_record = file_record(input_path, output_root)
        row = {
            "operation_unit_id": f"{method}|{stable_id}",
            "condition_id": method,
            "population_index": index,
            "stable_id": stable_id,
            "work_directory": work.relative_to(output_root).as_posix(),
            "output_directory": (work / "out").relative_to(output_root).as_posix(),
            "input": input_record,
            "shared_footprint": file_record(footprint_path, output_root),
            "classification": stats,
            "roofer_eligible": attempt_all or failure is None,
            "pre_roofer_failure": None if attempt_all else failure,
            "pre_invocation_input_diagnostic": failure,
            "all_building_method_invocation_required": attempt_all,
            "shared_standard_footprint": True,
            "shared_footprint_input_fields": ["stable_id", "GroundSurface exterior/interior XY"],
            "lod2_z_used": False,
            "roofsurface_used": False,
            "official_PASS_usable": None,
            "scientific_verdict": None,
        }
        write_new(work / "prepared_v1.json", canonical_json_bytes(row))
        rows.append(row)
    return rows


def git_value(*args: str) -> str:
    try:
        return subprocess.check_output(["git", *args], cwd=REPO, text=True, stderr=subprocess.DEVNULL).strip()
    except Exception:
        return "UNKNOWN"


def prepare(output_root: Path, artifact_root: Path, config_path: Path = CONFIG_PATH) -> dict[str, Any]:
    config = load_config(config_path)
    validate_config(config)
    if output_root.exists() and any(output_root.iterdir()):
        raise RuntimeError("fresh add-once shared-footprint namespace required")
    output_root.mkdir(parents=True, exist_ok=True)
    population_spec = config["population"]
    population_path = artifact_root / population_spec["common_manifest_relative_path"]
    population = read_population(population_path, population_spec)
    input_config = config["inputs"]
    c1_path = artifact_root / input_config["c1_current_uas_lidar"]["relative_path"]
    c2_path = artifact_root / input_config["c2_recovered_common_mvs_dense"]["relative_path"]
    source_records = {
        "population": exact_file(population_path, {"bytes": population_spec["common_manifest_bytes"], "sha256": population_spec["common_manifest_sha256"]}),
        "c1": exact_file(c1_path, input_config["c1_current_uas_lidar"]),
        "c2": exact_file(c2_path, input_config["c2_recovered_common_mvs_dense"]),
        "shared_footprints": [],
    }
    footprint_paths = []
    for spec in input_config["shared_standard_footprints"]:
        path = artifact_root / spec["relative_path"]
        source_records["shared_footprints"].append(exact_file(path, spec))
        footprint_paths.append(path)
    building_ids = [str(row["building_id"]) for row in population]
    references = load_groundsurface_xy(footprint_paths, building_ids)
    footprint_hashes = []
    for row in population:
        stable_id = str(row["building_id"])
        data = canonical_json_bytes(shared_footprint_geojson(references[stable_id]))
        footprint_hashes.append({"population_index": int(row["population_index"]), "stable_id": stable_id, "bytes": len(data), "sha256": __import__("hashlib").sha256(data).hexdigest()})
    write_new(output_root / "freeze/shared_footprint_199_v1.jsonl", jsonl_bytes(footprint_hashes))

    prep = config["preparation"]
    attempt_all = config["execution"].get("attempt_all_building_method_rows") is True
    bins = build_spatial_bins(references, float(prep["crop_buffer_m"]), float(prep["spatial_bin_m"]))
    all_rows: list[dict[str, Any]] = []
    scan_stats = {}
    scratch_root = output_root / ".scratch"
    c1_scratch = scratch_root / METHODS[0]
    scan_stats[METHODS[0]] = collect_lidar(c1_path, c1_scratch, references, bins)
    if scan_stats[METHODS[0]]["source_point_count"] != int(input_config["c1_current_uas_lidar"]["point_count"]):
        raise RuntimeError("C1 source point count drifted")
    all_rows.extend(prepare_method(output_root, c1_scratch, METHODS[0], population, references, prep, attempt_all))
    shutil.rmtree(c1_scratch)
    c2_scratch = scratch_root / METHODS[1]
    scan_stats[METHODS[1]] = collect_mvs(c2_path, c2_scratch, references, bins, config["frame"]["mvs_world_shift_xyz"])
    if scan_stats[METHODS[1]]["source_point_count"] != int(input_config["c2_recovered_common_mvs_dense"]["point_count"]):
        raise RuntimeError("C2 source point count drifted")
    all_rows.extend(prepare_method(output_root, c2_scratch, METHODS[1], population, references, prep, attempt_all))
    shutil.rmtree(scratch_root)

    if len(all_rows) != 398 or len({row["operation_unit_id"] for row in all_rows}) != 398:
        raise RuntimeError("expected exact 398 unique building-method rows")
    write_new(output_root / "freeze/execution_units_v1.jsonl", jsonl_bytes(all_rows))
    eligible = [row for row in all_rows if row["roofer_eligible"]]
    tsv = "operation_unit_id\twork_directory\n" + "".join(
        f"{row['operation_unit_id']}\t{row['work_directory']}\n" for row in eligible
    )
    write_new(output_root / "freeze/execution_units_v1.tsv", tsv.encode("utf-8"))
    by_method = {
        method: {
            "building_rows": sum(row["condition_id"] == method for row in all_rows),
            "roofer_eligible": sum(row["condition_id"] == method and row["roofer_eligible"] for row in all_rows),
            "pre_roofer_failure": sum(row["condition_id"] == method and not row["roofer_eligible"] for row in all_rows),
            "pre_invocation_input_diagnostic": sum(row["condition_id"] == method and row["pre_invocation_input_diagnostic"] is not None for row in all_rows),
        }
        for method in METHODS
    }
    body = {
        "schema": "jointbuildgs.p2.c1_c2_shared_footprint_199.prepared.v1",
        "task_id": config["task_id"],
        "decision_id": config["decision_id"],
        "status": "PREPARED_398_BUILDING_METHOD_ROWS",
        "source_records": source_records,
        "source_scan_stats": scan_stats,
        "counts_by_method": by_method,
        "building_count": 199,
        "building_method_row_count": 398,
        "roofer_eligible_count": len(eligible),
        "pre_roofer_failure_count": 398 - len(eligible),
        "git_commit": git_value("rev-parse", "HEAD"),
        "git_status_porcelain": git_value("status", "--porcelain=v1", "--untracked-files=all"),
        "config": file_record(config_path, REPO),
        "script": file_record(Path(__file__).resolve(), REPO),
        "roofer_invocations_so_far": 0,
        "official_PASS_usable": None,
        "scientific_verdict": None,
    }
    write_new(output_root / "control/prepared_v1.json", canonical_json_bytes(body))
    return body


def load_units(output_root: Path) -> dict[str, dict[str, Any]]:
    rows = [json.loads(line) for line in (output_root / "freeze/execution_units_v1.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    return {str(row["operation_unit_id"]): row for row in rows}


def record_terminal(output_root: Path, operation_id: str, exit_code: int, runtime_seconds: int) -> dict[str, Any]:
    unit = load_units(output_root).get(operation_id)
    if unit is None or not unit["roofer_eligible"]:
        raise RuntimeError(f"unknown or ineligible Roofer operation: {operation_id}")
    work = output_root / unit["work_directory"]
    terminal_path = work / "roofer_terminal_v1.json"
    if terminal_path.exists():
        raise RuntimeError(f"terminal already exists: {terminal_path}")
    outputs = sorted((work / "out").glob("*.city.jsonl")) if (work / "out").is_dir() else []
    completed = int(exit_code) == 0 and len(outputs) == 1
    lod22_present = False
    if completed:
        for line in outputs[0].read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            record = json.loads(line)
            if any(
                str(geometry.get("lod")) == "2.2"
                for city_object in (record.get("CityObjects") or {}).values()
                for geometry in city_object.get("geometry", [])
            ):
                lod22_present = True
                break
    body = {
        "schema": "jointbuildgs.p2.c1_c2_shared_footprint_199.roofer_terminal.v1",
        "status": "COMPLETED" if completed else "FAILED",
        "operation_unit_id": operation_id,
        "condition_id": unit["condition_id"],
        "population_index": unit["population_index"],
        "stable_id": unit["stable_id"],
        "exit_code": int(exit_code),
        "runtime_seconds": int(runtime_seconds),
        "input": unit["input"],
        "shared_footprint": unit["shared_footprint"],
        "outputs": [file_record(path, output_root) for path in outputs],
        "lod22_present": lod22_present,
        "shared_standard_footprint": True,
        "lod2_z_used": False,
        "roofsurface_used": False,
        "quality_driven_retry": False,
        "official_PASS_usable": None,
        "scientific_verdict": None,
    }
    write_new(terminal_path, canonical_json_bytes(body))
    return body


def finalize(output_root: Path, config_path: Path = CONFIG_PATH) -> dict[str, Any]:
    config = load_config(config_path)
    validate_config(config)
    units = list(load_units(output_root).values())
    if len(units) != 398:
        raise RuntimeError("finalize requires exact 398 unit rows")
    results = []
    for unit in sorted(units, key=lambda row: (METHODS.index(row["condition_id"]), int(row["population_index"]))):
        terminal_path = output_root / unit["work_directory"] / "roofer_terminal_v1.json"
        if unit["roofer_eligible"]:
            if not terminal_path.is_file():
                raise RuntimeError(f"eligible operation missing terminal: {unit['operation_unit_id']}")
            terminal = json.loads(terminal_path.read_text(encoding="utf-8"))
            status = terminal["status"]
            output_records = terminal["outputs"]
            exit_code = terminal["exit_code"]
            runtime_seconds = terminal["runtime_seconds"]
            lod22_present = bool(terminal.get("lod22_present", False))
        else:
            if terminal_path.exists():
                raise RuntimeError(f"ineligible operation unexpectedly has terminal: {unit['operation_unit_id']}")
            status = "PRE_ROOFER_FAILED"
            output_records = []
            exit_code = None
            runtime_seconds = 0
            lod22_present = False
        results.append({
            "population_index": unit["population_index"],
            "stable_id": unit["stable_id"],
            "condition_id": unit["condition_id"],
            "operation_unit_id": unit["operation_unit_id"],
            "status": status,
            "pre_roofer_failure": unit["pre_roofer_failure"],
            "pre_invocation_input_diagnostic": unit.get("pre_invocation_input_diagnostic"),
            "classification": unit["classification"],
            "input": unit["input"],
            "shared_footprint": unit["shared_footprint"],
            "outputs": output_records,
            "exit_code": exit_code,
            "runtime_seconds": runtime_seconds,
            "lod22_present": lod22_present,
            "shared_standard_footprint": True,
            "lod2_z_used": False,
            "roofsurface_used": False,
            "official_PASS_usable": None,
            "scientific_verdict": None,
        })
    write_new(output_root / "results/building_method_results_v1.jsonl", jsonl_bytes(results))
    stream = io.StringIO(newline="")
    fields = ["population_index", "stable_id", "condition_id", "status", "lod22_present", "class6_points", "class2_points", "runtime_seconds", "failure_code", "input_diagnostic_code"]
    writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    for row in results:
        writer.writerow({
            "population_index": row["population_index"],
            "stable_id": row["stable_id"],
            "condition_id": row["condition_id"],
            "status": row["status"],
            "lod22_present": row["lod22_present"],
            "class6_points": row["classification"].get("building_class6_count", 0),
            "class2_points": row["classification"].get("ground_class2_count", 0),
            "runtime_seconds": row["runtime_seconds"],
            "failure_code": (row["pre_roofer_failure"] or {}).get("code", "") if row["status"] == "PRE_ROOFER_FAILED" else ("ROOFER_OUTPUT_NO_LOD22_GEOMETRY" if row["status"] == "COMPLETED" and not row["lod22_present"] else ("" if row["status"] == "COMPLETED" else "ROOFER_PROCESS_OR_OUTPUT_FAILURE")),
            "input_diagnostic_code": (row["pre_invocation_input_diagnostic"] or {}).get("code", ""),
        })
    write_new(output_root / "results/building_method_status_v1.csv", stream.getvalue().encode("utf-8"))
    counts = {
        method: {
            "rows": sum(row["condition_id"] == method for row in results),
            "completed": sum(row["condition_id"] == method and row["status"] == "COMPLETED" for row in results),
            "roofer_failed": sum(row["condition_id"] == method and row["status"] == "FAILED" for row in results),
            "pre_roofer_failed": sum(row["condition_id"] == method and row["status"] == "PRE_ROOFER_FAILED" for row in results),
            "lod22_generated": sum(row["condition_id"] == method and row["lod22_present"] for row in results),
            "completed_without_lod22": sum(row["condition_id"] == method and row["status"] == "COMPLETED" and not row["lod22_present"] for row in results),
        }
        for method in METHODS
    }
    finalized = {
        "schema": "jointbuildgs.p2.c1_c2_shared_footprint_199.finalized.v1",
        "task_id": config["task_id"],
        "decision_id": config["decision_id"],
        "status": "TECHNICAL_COMPLETE_WITH_EXPLICIT_MISSINGNESS",
        "completed_at_utc": datetime.now(timezone.utc).isoformat(),
        "building_count": 199,
        "building_method_row_count": 398,
        "counts_by_method": counts,
        "roofer_invocation_count": sum(row["status"] in {"COMPLETED", "FAILED"} for row in results),
        "gs_training_invocations": 0,
        "reconstruction_invocations": 0,
        "result_jsonl": file_record(output_root / "results/building_method_results_v1.jsonl", output_root),
        "result_csv": file_record(output_root / "results/building_method_status_v1.csv", output_root),
        "shared_standard_footprint": True,
        "lod2_z_used": False,
        "roofsurface_used": False,
        "official_PASS_usable": None,
        "scientific_verdict": None,
    }
    write_new(output_root / "control/finalized_v1.json", canonical_json_bytes(finalized))
    records = []
    for path in sorted(item for item in output_root.rglob("*") if item.is_file() and item.name != "artifact_manifest_v1.json"):
        records.append(file_record(path, output_root))
    manifest = {
        "schema": "jointbuildgs.p2.c1_c2_shared_footprint_199.artifact_manifest.v1",
        "task_id": config["task_id"],
        "status": "COMPLETE_HASHED_BUILDING_LEVEL_C1_C2_ROOFER",
        "record_count": len(records),
        "records": records,
        "counts_by_method": counts,
        "official_PASS_usable": None,
        "scientific_verdict": None,
    }
    write_new(output_root / "control/artifact_manifest_v1.json", canonical_json_bytes(manifest))
    return finalized


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="mode", required=True)
    prepare_parser = sub.add_parser("prepare")
    prepare_parser.add_argument("--output-root", type=Path, required=True)
    prepare_parser.add_argument("--artifact-root", type=Path, required=True)
    prepare_parser.add_argument("--config", type=Path, default=CONFIG_PATH)
    terminal_parser = sub.add_parser("record-terminal")
    terminal_parser.add_argument("--output-root", type=Path, required=True)
    terminal_parser.add_argument("--operation-id", required=True)
    terminal_parser.add_argument("--exit-code", type=int, required=True)
    terminal_parser.add_argument("--runtime-seconds", type=int, required=True)
    finalize_parser = sub.add_parser("finalize")
    finalize_parser.add_argument("--output-root", type=Path, required=True)
    finalize_parser.add_argument("--config", type=Path, default=CONFIG_PATH)
    args = parser.parse_args()
    if args.mode == "prepare":
        result = prepare(args.output_root, args.artifact_root, args.config)
    elif args.mode == "record-terminal":
        result = record_terminal(args.output_root, args.operation_id, args.exit_code, args.runtime_seconds)
    else:
        result = finalize(args.output_root, args.config)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
