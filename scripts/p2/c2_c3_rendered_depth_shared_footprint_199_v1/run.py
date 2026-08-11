#!/usr/bin/env python3
"""Fuse exact-view C3 rendered median depth and run the shared C2/C3 adapter.

The scientific input is a surface cloud reconstructed from checkpoint renders.
Raw Gaussian centres and semantic labels are never used to decide geometry or
PDAL Classification.  Semantic probabilities survive only as audit dimensions.
"""
from __future__ import annotations

import argparse
from collections import Counter
import csv
from datetime import datetime, timezone
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
from typing import Any, Mapping, Sequence

import laspy
import numpy as np

from scripts.p2.c1_c2_shared_footprint_199_v1.run import (
    canonical_json_bytes,
    exact_file,
    file_record,
    read_population,
    sha256_file,
    write_new,
)
from scripts.p2.c1_c2_shared_footprint_199_v3.run import (
    _parse_features,
    _status,
    _val_by_id,
    combine_cityjsonseq,
)
from src.stage3.common_classification_adapter_v1 import pipeline as classification_pipeline


REPO = Path(__file__).resolve().parents[3]
CONFIG_PATH = REPO / "configs/p2/c2_c3_rendered_depth_shared_footprint_199_v1/run_v1.json"
CONDITIONS = ("C3_1", "C3_2")
EPSG25832_WKT = 'PROJCS["ETRS89 / UTM zone 32N",GEOGCS["ETRS89",DATUM["European_Terrestrial_Reference_System_1989",SPHEROID["GRS 1980",6378137,298.257222101,AUTHORITY["EPSG","7019"]],AUTHORITY["EPSG","6258"]],PRIMEM["Greenwich",0,AUTHORITY["EPSG","8901"]],UNIT["degree",0.0174532925199433,AUTHORITY["EPSG","9122"]],AUTHORITY["EPSG","4258"]],PROJECTION["Transverse_Mercator"],PARAMETER["latitude_of_origin",0],PARAMETER["central_meridian",9],PARAMETER["scale_factor",0.9996],PARAMETER["false_easting",500000],PARAMETER["false_northing",0],UNIT["metre",1,AUTHORITY["EPSG","9001"]],AXIS["Easting",EAST],AXIS["Northing",NORTH],AUTHORITY["EPSG","25832"]]'
SHARD_DTYPE = np.dtype([
    ("qx", "<i4"), ("qy", "<i4"), ("qz", "<i4"),
    ("sx", "<f8"), ("sy", "<f8"), ("sz", "<f8"),
    ("sr", "<f8"), ("sg", "<f8"), ("sb", "<f8"),
    ("sp0", "<f8"), ("sp1", "<f8"), ("sp2", "<f8"), ("sp3", "<f8"),
    ("pixel_count", "<u4"),
])


def load_config(path: Path = CONFIG_PATH) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def validate_config(config: Mapping[str, Any]) -> None:
    if config.get("schema") != "jointbuildgs.p2.c2_c3_rendered_depth_shared_footprint_199.v1":
        raise RuntimeError("rendered-depth direct-comparison schema drifted")
    if config.get("status") != "USER_APPROVED_FOR_EXECUTION":
        raise RuntimeError("execution is not user-approved")
    if config["comparison_definition"]["label"] != "shared-footprint technical diagnostic":
        raise RuntimeError("shared-footprint diagnostic label drifted")
    fusion = config["fusion"]
    expected = {
        "source": "checkpoint_rendered_median_depth",
        "render_downscale": 0.25,
        "alpha_min": 0.5,
        "valid_depth_m": [0.01, 500.0],
        "voxel_m": 0.15,
        "minimum_distinct_view_support": 2,
        "post_fusion_voxel_downsampling": False,
        "semantic_role": "audit_and_display_only",
        "semantic_class_count": 4,
        "shard_count": 64,
        "fixed_view_order": "exact_manifest_row_order",
    }
    if fusion != expected:
        raise RuntimeError("fusion parameter block drifted")
    classification = config["classification"]
    if not classification.get("same_adapter_for_c2_c3") or classification.get("semantic_used_for_classification"):
        raise RuntimeError("C2/C3 common-classification boundary drifted")
    if classification["smrf"] != {"cell": 1.0, "slope": 0.15, "scalar": 1.25, "threshold": 0.5, "window": 18.0}:
        raise RuntimeError("SMRF parameter block drifted")
    if (classification["ground_class"], classification["building_class"], classification["unclassified_class"]) != (2, 6, 1):
        raise RuntimeError("classification values drifted")
    if config["roofer"]["quality_parameters"] != "ROOFER_DEFAULTS" or config["roofer"]["quality_driven_retry_allowed"]:
        raise RuntimeError("Roofer defaults/no-retry contract drifted")
    if config.get("official_PASS_usable", "missing") is not None or config.get("scientific_verdict", "missing") is not None:
        raise RuntimeError("verdict fields must remain null")


def _condition_spec(config: Mapping[str, Any], condition_id: str) -> Mapping[str, Any]:
    if condition_id not in CONDITIONS:
        raise RuntimeError(f"unknown condition: {condition_id}")
    return next(row for row in config["inputs"]["conditions"] if row["condition_id"] == condition_id)


def _visible_names(config: Mapping[str, Any], repo_root: Path) -> tuple[list[str], dict[str, Any]]:
    spec = config["inputs"]
    path = repo_root / spec["exact_view_manifest_git_path"]
    record = exact_file(path, {"bytes": spec["exact_view_manifest_bytes"], "sha256": spec["exact_view_manifest_sha256"]})
    body = json.loads(path.read_text(encoding="utf-8"))
    names = [str(row["basename"]) for row in body["rows"]]
    if len(names) != int(spec["exact_view_count"]) or len(set(names)) != len(names):
        raise RuntimeError("exact view membership/order drifted")
    return names, record


def _selected_population(config: Mapping[str, Any], population: Sequence[Mapping[str, Any]], scope: str) -> list[dict[str, Any]]:
    spec = config["scopes"][scope]
    indices = spec["population_indices"]
    if indices == "ALL_1_TO_199":
        selected = list(population)
    else:
        wanted = set(map(int, indices))
        selected = [row for row in population if int(row["population_index"]) in wanted]
    if len(selected) != int(spec["building_count"]):
        raise RuntimeError(f"scope population drifted: {scope}")
    return selected


def _freeze_footprints(source: Path, destination: Path, selected_ids: set[str], full: bool) -> dict[str, Any]:
    if full:
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            raise FileExistsError(destination)
        shutil.copyfile(source, destination)
        return json.loads(destination.read_text(encoding="utf-8"))
    body = json.loads(source.read_text(encoding="utf-8"))
    body["features"] = [row for row in body["features"] if str(row["properties"]["stable_id"]) in selected_ids]
    if len(body["features"]) != len(selected_ids):
        raise RuntimeError("pilot footprint membership drifted")
    write_new(destination, canonical_json_bytes(body))
    return body


def _fusion_filter(scope: str, config: Mapping[str, Any], footprint_body: Mapping[str, Any]):
    from shapely.geometry import box, shape
    from shapely.ops import unary_union

    if scope == "full199":
        x0, y0, x1, y1 = map(float, config["scene"]["roofer_aoi_bbox"])
        value = float(config["scene"]["classification_context_buffer_m"])
        return box(x0 - value, y0 - value, x1 + value, y1 + value)
    buffer_m = float(config["scopes"][scope]["buffer_m"])
    return unary_union([shape(row["geometry"]) for row in footprint_body["features"]]).buffer(buffer_m)


def prepare(
    *, output_root: Path, artifact_root: Path, repo_root: Path, scope: str, config_path: Path = CONFIG_PATH,
) -> dict[str, Any]:
    config = load_config(config_path)
    validate_config(config)
    if scope not in config["scopes"]:
        raise RuntimeError(f"unknown scope: {scope}")
    marker = output_root / "control/prepared_v1.json"
    if marker.is_file():
        return json.loads(marker.read_text(encoding="utf-8"))
    if output_root.exists() and any(output_root.iterdir()):
        raise RuntimeError("nonempty namespace lacks prepared receipt")
    output_root.mkdir(parents=True, exist_ok=True)
    inputs = config["inputs"]
    population_path = artifact_root / inputs["common_manifest_relative_path"] if "common_manifest_relative_path" in inputs else artifact_root / config["population"]["common_manifest_relative_path"]
    population = read_population(population_path, config["population"])
    selected = _selected_population(config, population, scope)
    names, view_record = _visible_names(config, repo_root)
    source_records: dict[str, Any] = {
        "population": exact_file(population_path, {"bytes": config["population"]["common_manifest_bytes"], "sha256": config["population"]["common_manifest_sha256"]}),
        "exact_view_manifest": view_record,
        "camera_files": [],
        "checkpoints": {},
        "c2_native_source": exact_file(artifact_root / inputs["c2_native_source"]["relative_path"], inputs["c2_native_source"]),
        "c2_classified_source": exact_file(artifact_root / inputs["c2_classified_source"]["relative_path"], inputs["c2_classified_source"]),
        "shared_footprints_source": exact_file(artifact_root / inputs["shared_footprints"]["relative_path"], inputs["shared_footprints"]),
    }
    if "training_completion" in inputs:
        source_records["training_completion"] = exact_file(
            artifact_root / inputs["training_completion"]["relative_path"],
            inputs["training_completion"],
        )
    for row in inputs["camera_files"]:
        source_records["camera_files"].append(exact_file(artifact_root / row["relative_path"], row))
    checkpoint_root = artifact_root / inputs["checkpoint_root_relative_path"]
    for condition_id in CONDITIONS:
        row = _condition_spec(config, condition_id)
        source_records["checkpoints"][condition_id] = exact_file(checkpoint_root / row["checkpoint_relative_path"], row)
    footprint_path = output_root / "freeze/shared_footprints.geojson"
    footprint_body = _freeze_footprints(
        artifact_root / inputs["shared_footprints"]["relative_path"], footprint_path,
        {str(row["building_id"]) for row in selected}, scope == "full199",
    )
    filter_geometry = _fusion_filter(scope, config, footprint_body)
    filter_path = output_root / "freeze/fusion_xy_filter.geojson"
    from shapely.geometry import mapping
    write_new(filter_path, canonical_json_bytes({
        "type": "FeatureCollection",
        "crs": {"type": "name", "properties": {"name": "urn:ogc:def:crs:EPSG::25832"}},
        "features": [{"type": "Feature", "properties": {"scope": scope, "outcome_selected": False}, "geometry": mapping(filter_geometry)}],
    }))
    for condition_id in CONDITIONS:
        work = output_root / "work" / condition_id
        work.mkdir(parents=True, exist_ok=True)
        pipeline_path = work / "classification_pipeline.json"
        classified = work / "classified_scene.laz"
        body = classification_pipeline(
            source_stages=[{"type": "readers.las", "filename": (work / "fused_surface.laz").as_posix()}],
            scene=config["scene"], classification=config["classification"],
            footprint_path=footprint_path, output_path=classified,
        )
        write_new(pipeline_path, canonical_json_bytes(body))
    receipt = {
        "schema": "jointbuildgs.p2.c2_c3_rendered_depth_shared_footprint_199.prepared.v1",
        "task_id": config["task_id"], "scope": scope,
        "status": "PREPARED_FOR_EXACT_VIEW_FUSION",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "source_records": source_records,
        "exact_view_count": len(names),
        "ordered_building_ids": [str(row["building_id"]) for row in selected],
        "shared_footprints": file_record(footprint_path, output_root),
        "fusion_xy_filter": file_record(filter_path, output_root),
        "fusion_parameters": config["fusion"],
        "classification_parameters": config["classification"],
        "comparison_label": "shared-footprint technical diagnostic",
        "official_PASS_usable": None, "scientific_verdict": None,
    }
    write_new(marker, canonical_json_bytes(receipt))
    return receipt


def _atomic_json(path: Path, body: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(canonical_json_bytes(body))
    os.replace(temporary, path)


def _shard_index(q: np.ndarray, count: int) -> np.ndarray:
    values = q.astype(np.int64, copy=False).astype(np.uint64, copy=False)
    hashed = (values[:, 0] * np.uint64(73856093)) ^ (values[:, 1] * np.uint64(19349663)) ^ (values[:, 2] * np.uint64(83492791))
    return np.asarray(hashed & np.uint64(count - 1), dtype=np.int64)


def _collapse_view(
    xyz: np.ndarray, rgb: np.ndarray, probabilities: np.ndarray, shift: np.ndarray, voxel_m: float,
) -> np.ndarray:
    q = np.floor((xyz - shift) / voxel_m).astype(np.int32)
    order = np.lexsort((q[:, 2], q[:, 1], q[:, 0]))
    q = q[order]
    xyz, rgb, probabilities = xyz[order], rgb[order], probabilities[order]
    starts = np.r_[0, np.flatnonzero(np.any(q[1:] != q[:-1], axis=1)) + 1]
    counts = np.diff(np.r_[starts, len(q)]).astype(np.uint32)
    rows = np.empty(len(starts), dtype=SHARD_DTYPE)
    rows["qx"], rows["qy"], rows["qz"] = q[starts].T
    for key, values in zip(("sx", "sy", "sz"), xyz.T):
        rows[key] = np.add.reduceat(values.astype(np.float64), starts)
    for key, values in zip(("sr", "sg", "sb"), rgb.T):
        rows[key] = np.add.reduceat(values.astype(np.float64), starts)
    for key, values in zip(("sp0", "sp1", "sp2", "sp3"), probabilities.T):
        rows[key] = np.add.reduceat(values.astype(np.float64), starts)
    rows["pixel_count"] = counts
    return rows


def _truncate_for_resume(shard_paths: Sequence[Path], sizes: Sequence[int]) -> None:
    if len(shard_paths) != len(sizes):
        raise RuntimeError("fusion progress shard inventory drifted")
    for path, size in zip(shard_paths, sizes):
        if path.stat().st_size < int(size):
            raise RuntimeError(f"fusion shard shorter than sealed progress: {path}")
        with path.open("r+b") as stream:
            stream.truncate(int(size))


def _write_fused_laz(
    *, shard_paths: Sequence[Path], destination: Path, minimum_support: int,
) -> tuple[int, dict[str, int], int, int]:
    header = laspy.LasHeader(point_format=3, version="1.4")
    from laspy.vlrs.known import WktCoordinateSystemVlr
    header.vlrs.append(WktCoordinateSystemVlr(EPSG25832_WKT))
    header.global_encoding.wkt = True
    header.scales = np.asarray([0.001, 0.001, 0.001])
    header.offsets = np.asarray([690000.0, 5335000.0, 0.0])
    header.add_extra_dim(laspy.ExtraBytesParams(name="view_support", type=np.uint16))
    header.add_extra_dim(laspy.ExtraBytesParams(name="semantic_argmax", type=np.uint8))
    for index in range(4):
        header.add_extra_dim(laspy.ExtraBytesParams(name=f"semantic_prob_{index}", type=np.float32))
    destination.parent.mkdir(parents=True, exist_ok=True)
    total = 0
    support_histogram: Counter[int] = Counter()
    rejected = 0
    input_rows = 0
    with laspy.open(destination, mode="w", header=header, do_compress=True) as writer:
        for path in shard_paths:
            rows = np.fromfile(path, dtype=SHARD_DTYPE)
            input_rows += len(rows)
            if not len(rows):
                continue
            order = np.lexsort((rows["qz"], rows["qy"], rows["qx"]))
            rows = rows[order]
            changed = (rows["qx"][1:] != rows["qx"][:-1]) | (rows["qy"][1:] != rows["qy"][:-1]) | (rows["qz"][1:] != rows["qz"][:-1])
            starts = np.r_[0, np.flatnonzero(changed) + 1]
            support = np.diff(np.r_[starts, len(rows)]).astype(np.uint16)
            keep = support >= minimum_support
            rejected += int(np.count_nonzero(~keep))
            for value, count in zip(*np.unique(support[keep], return_counts=True)):
                support_histogram[int(value)] += int(count)
            if not np.any(keep):
                continue
            pixel_count = np.add.reduceat(rows["pixel_count"].astype(np.float64), starts)[keep]
            sums = {
                key: np.add.reduceat(rows[key], starts)[keep]
                for key in ("sx", "sy", "sz", "sr", "sg", "sb", "sp0", "sp1", "sp2", "sp3")
            }
            n = len(pixel_count)
            points = laspy.ScaleAwarePointRecord.zeros(n, header=header)
            points.x = sums["sx"] / pixel_count
            points.y = sums["sy"] / pixel_count
            points.z = sums["sz"] / pixel_count
            points.red = np.rint(np.clip(sums["sr"] / pixel_count, 0, 1) * 65535).astype(np.uint16)
            points.green = np.rint(np.clip(sums["sg"] / pixel_count, 0, 1) * 65535).astype(np.uint16)
            points.blue = np.rint(np.clip(sums["sb"] / pixel_count, 0, 1) * 65535).astype(np.uint16)
            points.classification = np.ones(n, dtype=np.uint8)
            points.view_support = support[keep]
            probabilities = np.column_stack([sums[f"sp{i}"] / pixel_count for i in range(4)]).astype(np.float32)
            points.semantic_argmax = np.argmax(probabilities, axis=1).astype(np.uint8)
            for index in range(4):
                points[f"semantic_prob_{index}"] = probabilities[:, index]
            writer.write_points(points)
            total += n
    return total, {str(key): support_histogram[key] for key in sorted(support_histogram)}, rejected, input_rows


def fuse(
    *, output_root: Path, artifact_root: Path, repo_root: Path, condition_id: str,
    device: str, config_path: Path = CONFIG_PATH,
) -> dict[str, Any]:
    config = load_config(config_path)
    validate_config(config)
    import torch
    from scripts.p2.c3_utarget199_postprocess_v1.render_gs import model_from_checkpoint
    from src.stage2.dataloader import ColmapDataset
    from src.stage2.renderer import render, render_semantic
    prepared = json.loads((output_root / "control/prepared_v1.json").read_text(encoding="utf-8"))
    receipt_path = output_root / "work" / condition_id / "fused_surface_receipt.json"
    if receipt_path.is_file():
        return json.loads(receipt_path.read_text(encoding="utf-8"))
    names, _ = _visible_names(config, repo_root)
    data_root = artifact_root / config["inputs"]["data_root_relative_path"]
    dataset = ColmapDataset(
        data_root, downscale=float(config["fusion"]["render_downscale"]),
        load_depth=False, load_normal=False, load_semantic=False, visible_views=names,
    )
    if [frame.name for frame in dataset.frames] != names:
        raise RuntimeError("dataset did not preserve exact manifest order")
    condition = _condition_spec(config, condition_id)
    checkpoint = artifact_root / config["inputs"]["checkpoint_root_relative_path"] / condition["checkpoint_relative_path"]
    exact_file(checkpoint, condition)
    model = model_from_checkpoint(checkpoint, device)
    filter_body = json.loads((output_root / "freeze/fusion_xy_filter.geojson").read_text(encoding="utf-8"))
    from shapely.geometry import shape
    from shapely import contains_xy
    filter_geometry = shape(filter_body["features"][0]["geometry"])
    fusion = config["fusion"]
    work = output_root / "work" / condition_id
    shard_dir = work / "fusion_shards"
    shard_dir.mkdir(parents=True, exist_ok=True)
    shard_count = int(fusion["shard_count"])
    if shard_count <= 0 or shard_count & (shard_count - 1):
        raise RuntimeError("shard count must be a power of two")
    shard_paths = [shard_dir / f"shard_{index:02d}.bin" for index in range(shard_count)]
    for path in shard_paths:
        path.touch(exist_ok=True)
    progress_path = work / "fusion_progress.json"
    if progress_path.is_file():
        progress = json.loads(progress_path.read_text(encoding="utf-8"))
        if progress["condition_id"] != condition_id or progress["view_names"] != names:
            raise RuntimeError("fusion resume identity drifted")
        _truncate_for_resume(shard_paths, progress["shard_sizes"])
        start_index = int(progress["completed_view_count"])
        view_records = list(progress["view_records"])
    else:
        if any(path.stat().st_size for path in shard_paths):
            raise RuntimeError("unsealed nonempty fusion shards")
        start_index = 0
        view_records = []
    shift = np.asarray(config["scene"]["world_shift_xyz"], dtype=np.float64)
    depth_min, depth_max = map(float, fusion["valid_depth_m"])
    torch.cuda.reset_peak_memory_stats() if str(device).startswith("cuda") else None
    handles = [path.open("ab") for path in shard_paths]
    try:
        with torch.no_grad():
            for index in range(start_index, len(dataset)):
                batch = dataset[index]
                width, height = int(batch["width"]), int(batch["height"])
                w2c = batch["w2c"].to(device)
                intrinsics = batch["K"].to(device)
                output = render(
                    model, w2c, intrinsics, width, height, sh_degree=3,
                    render_mode="RGB+ED", near_plane=depth_min, far_plane=depth_max,
                    bg_color=torch.ones(3, device=device), depth_mode="median",
                )
                depth = output["depth_median"]
                mask = torch.isfinite(depth) & (depth >= depth_min) & (depth <= depth_max) & (output["alpha"] >= float(fusion["alpha_min"]))
                valid_pixels = int(mask.sum().item())
                retained = 0
                unique_voxels = 0
                if valid_pixels:
                    yy, xx = torch.nonzero(mask, as_tuple=True)
                    z = depth[yy, xx]
                    camera_xyz = torch.stack(((xx - intrinsics[0, 2]) / intrinsics[0, 0] * z, (yy - intrinsics[1, 2]) / intrinsics[1, 1] * z, z), dim=1)
                    c2w = torch.linalg.inv(w2c)
                    xyz_local = camera_xyz @ c2w[:3, :3].T + c2w[:3, 3]
                    xyz = xyz_local.cpu().numpy().astype(np.float64) + shift
                    spatial = contains_xy(filter_geometry, xyz[:, 0], xyz[:, 1])
                    retained = int(np.count_nonzero(spatial))
                    if retained:
                        rgb = output["rgb"][yy, xx].cpu().numpy()[spatial]
                        logits = render_semantic(model, w2c, intrinsics, width, height)[yy, xx]
                        probabilities = torch.softmax(logits, dim=-1).cpu().numpy()[spatial]
                        rows = _collapse_view(xyz[spatial], rgb, probabilities, shift, float(fusion["voxel_m"]))
                        unique_voxels = len(rows)
                        shard_ids = _shard_index(np.column_stack((rows["qx"], rows["qy"], rows["qz"])), shard_count)
                        for shard_id in np.unique(shard_ids):
                            rows[shard_ids == shard_id].tofile(handles[int(shard_id)])
                for handle in handles:
                    handle.flush()
                view_records.append({
                    "view_order": index, "image_name": str(batch["name"]),
                    "render_width": width, "render_height": height,
                    "valid_geometry_pixels": valid_pixels, "retained_xy_pixels": retained,
                    "distinct_view_voxel_records": unique_voxels,
                })
                _atomic_json(progress_path, {
                    "schema": "jointbuildgs.c3_rendered_depth_fusion.progress.v1",
                    "condition_id": condition_id, "view_names": names,
                    "completed_view_count": index + 1, "view_records": view_records,
                    "shard_sizes": [path.stat().st_size for path in shard_paths],
                })
                print(json.dumps({"condition_id": condition_id, "view": index + 1, "views": len(dataset), "name": batch["name"], "valid": valid_pixels, "retained": retained, "voxels": unique_voxels}), flush=True)
    finally:
        for handle in handles:
            handle.close()
    fused_path = work / "fused_surface.laz"
    if fused_path.exists():
        raise RuntimeError("unsealed fused output refuses overwrite")
    total, support_histogram, rejected, input_rows = _write_fused_laz(
        shard_paths=shard_paths, destination=fused_path,
        minimum_support=int(fusion["minimum_distinct_view_support"]),
    )
    if total <= 0:
        raise RuntimeError(f"no fused surface points survived: {condition_id}")
    peak = int(torch.cuda.max_memory_allocated() / (1024 * 1024)) if str(device).startswith("cuda") else None
    receipt = {
        "schema": "jointbuildgs.p2.c3_rendered_depth_fused_surface.v1",
        "condition_id": condition_id, "status": "FUSED_SURFACE_READY",
        "source_checkpoint": exact_file(checkpoint, condition),
        "source_kind": "checkpoint_rendered_median_depth",
        "raw_gaussian_centres_used": False, "semantic_geometry_gate_used": False,
        "semantic_classification_gate_used": False, "semantic_role": "audit_and_display_only",
        "exact_view_count": len(dataset), "view_order": "exact_manifest_row_order",
        "rendered_pixel_count": int(sum(row["render_width"] * row["render_height"] for row in view_records)),
        "valid_geometry_pixel_count": int(sum(row["valid_geometry_pixels"] for row in view_records)),
        "retained_xy_pixel_count": int(sum(row["retained_xy_pixels"] for row in view_records)),
        "per_view_unique_voxel_record_count": int(input_rows),
        "support_rejected_voxel_count": int(rejected), "point_count": int(total),
        "support_histogram": support_histogram, "parameters": fusion,
        "peak_gpu_memory_mib": peak,
        "fused_surface": file_record(fused_path, output_root),
        "progress_audit": file_record(progress_path, output_root),
        "post_fusion_voxel_downsampling": False,
        "comparison_label": "shared-footprint technical diagnostic",
        "official_PASS_usable": None, "scientific_verdict": None,
    }
    write_new(receipt_path, canonical_json_bytes(receipt))
    return receipt


def verify_classified(output_root: Path, condition_id: str, config_path: Path = CONFIG_PATH) -> dict[str, Any]:
    config = load_config(config_path)
    validate_config(config)
    path = output_root / "work" / condition_id / "classified_scene.laz"
    counts: Counter[int] = Counter()
    semantic_dims = {"view_support", "semantic_argmax", "semantic_prob_0", "semantic_prob_1", "semantic_prob_2", "semantic_prob_3"}
    with laspy.open(path) as reader:
        total = int(reader.header.point_count)
        crs = reader.header.parse_crs()
        epsg = crs.to_epsg() if crs is not None else None
        dimensions = set(reader.header.point_format.dimension_names)
        for chunk in reader.chunk_iterator(2_000_000):
            values, numbers = np.unique(np.asarray(chunk.classification), return_counts=True)
            counts.update({int(value): int(number) for value, number in zip(values, numbers)})
    if total <= 0 or counts[2] <= 0 or counts[6] <= 0 or epsg != 25832:
        raise RuntimeError(f"classified scene invariant failed: total={total} counts={counts} epsg={epsg}")
    if not semantic_dims.issubset(dimensions):
        raise RuntimeError(f"audit dimensions lost through PDAL: {sorted(semantic_dims - dimensions)}")
    receipt = {
        "schema": "jointbuildgs.p2.c3_rendered_depth_classified_scene.v1",
        "condition_id": condition_id, "status": "CLASSIFIED_SCENE_READY",
        "classified_scene": file_record(path, output_root), "point_count": total,
        "class_counts": {str(key): counts[key] for key in sorted(counts)}, "epsg": epsg,
        "preserved_audit_dimensions": sorted(semantic_dims),
        "classification_adapter": "src/stage3/common_classification_adapter_v1.py",
        "semantic_used_for_classification": False,
        "official_PASS_usable": None, "scientific_verdict": None,
    }
    write_new(output_root / "work" / condition_id / "classified_scene_receipt.json", canonical_json_bytes(receipt))
    return receipt


def record_roofer(output_root: Path, condition_id: str, exit_code: int, runtime_seconds: int) -> dict[str, Any]:
    work = output_root / "work" / condition_id
    files = sorted((work / "roofer_output").glob("*.city.jsonl"))
    receipt = {
        "schema": "jointbuildgs.p2.c3_rendered_depth_roofer_terminal.v1",
        "condition_id": condition_id,
        "status": "COMPLETED" if int(exit_code) == 0 and files else "FAILED",
        "exit_code": int(exit_code), "runtime_seconds": int(runtime_seconds),
        "roofer_invocation_count": 1, "quality_parameters": "defaults",
        "quality_driven_retry": False,
        "outputs": [file_record(path, output_root) for path in files],
        "official_PASS_usable": None, "scientific_verdict": None,
    }
    write_new(work / "roofer_terminal.json", canonical_json_bytes(receipt))
    return receipt


def finalize(output_root: Path, config_path: Path = CONFIG_PATH) -> dict[str, Any]:
    config = load_config(config_path)
    validate_config(config)
    prepared = json.loads((output_root / "control/prepared_v1.json").read_text(encoding="utf-8"))
    ids = list(prepared["ordered_building_ids"])
    rows: list[dict[str, Any]] = []
    summaries: dict[str, dict[str, int]] = {}
    for condition_id in CONDITIONS:
        work = output_root / "work" / condition_id
        raw_files = sorted((work / "roofer_output").glob("*.city.jsonl"))
        features = _parse_features(raw_files) if raw_files else {}
        valid_by_id: dict[str, bool] = {}
        val_exit_code = None
        if raw_files:
            assembled = work / "assembled.city.json"
            combine_cityjsonseq(raw_files, assembled)
            report = work / "val3dity_report.json"
            process = subprocess.run(["val3dity", assembled.as_posix(), "--report", report.as_posix()], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, check=False)
            (work / "val3dity.log").write_text(process.stdout or "", encoding="utf-8")
            val_exit_code = int(process.returncode)
            if report.is_file():
                valid_by_id = _val_by_id(json.loads(report.read_text(encoding="utf-8")))
        reasons: Counter[str] = Counter()
        for population_index, stable_id in enumerate(ids, start=1):
            feature = features.get(stable_id)
            valid = valid_by_id.get(stable_id)
            status, reason = _status(feature, valid)
            reasons[reason] += 1
            attrs = feature["attributes"] if feature else {}
            rows.append({
                "population_index": population_index, "stable_id": stable_id,
                "condition_id": condition_id, "status": status, "reason": reason,
                "lods": feature["lods"] if feature else [], "has_lod22": bool(feature and "2.2" in feature["lods"]),
                "val3dity_valid": valid, "rf_success": attrs.get("rf_success"),
                "rf_pointcloud_unusable": attrs.get("rf_pointcloud_unusable"),
                "rf_extrusion_mode": attrs.get("rf_extrusion_mode"), "rf_roof_type": attrs.get("rf_roof_type"),
                "rf_pt_density": attrs.get("rf_pt_density"), "rf_nodata_frac": attrs.get("rf_nodata_frac"),
                "rf_rmse_lod22": attrs.get("rf_rmse_lod22"), "rf_roof_planes": attrs.get("rf_roof_planes"),
                "official_PASS_usable": None, "scientific_verdict": None,
            })
        summaries[condition_id] = dict(reasons)
        write_new(work / "postprocess_receipt.json", canonical_json_bytes({
            "condition_id": condition_id, "feature_count": len(features),
            "val3dity_feature_count": len(valid_by_id), "val3dity_exit_code": val_exit_code,
            "reason_counts": dict(reasons), "official_PASS_usable": None, "scientific_verdict": None,
        }))
    jsonl_path = output_root / "results/building_method_results_v1.jsonl"
    write_new(jsonl_path, b"".join(canonical_json_bytes(row) for row in rows))
    fields = ["population_index", "stable_id", "condition_id", "status", "reason", "has_lod22", "val3dity_valid", "rf_success", "rf_pointcloud_unusable", "rf_extrusion_mode", "rf_roof_type", "rf_pt_density", "rf_nodata_frac", "rf_rmse_lod22", "rf_roof_planes"]
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    writer.writerows({key: row.get(key) for key in fields} for row in rows)
    csv_path = output_root / "results/building_method_status_v1.csv"
    write_new(csv_path, stream.getvalue().encode("utf-8"))
    receipt = {
        "schema": "jointbuildgs.p2.c2_c3_rendered_depth_shared_footprint_199.finalized.v1",
        "task_id": config["task_id"], "scope": prepared["scope"],
        "status": "TECHNICAL_COMPLETE_WITH_EXPLICIT_MISSINGNESS",
        "completed_utc": datetime.now(timezone.utc).isoformat(),
        "building_count": len(ids), "building_method_rows": len(rows),
        "roofer_invocation_count": len(CONDITIONS), "counts_by_method": summaries,
        "result_jsonl": file_record(jsonl_path, output_root), "result_csv": file_record(csv_path, output_root),
        "comparison_label": "shared-footprint technical diagnostic",
        "official_PASS_usable": None, "scientific_verdict": None,
    }
    write_new(output_root / "control/finalized_v1.json", canonical_json_bytes(receipt))
    return receipt


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=CONFIG_PATH)
    sub = parser.add_subparsers(dest="mode", required=True)
    validate = sub.add_parser("validate-config")
    prep = sub.add_parser("prepare")
    prep.add_argument("--output-root", type=Path, required=True); prep.add_argument("--artifact-root", type=Path, required=True); prep.add_argument("--repo-root", type=Path, default=REPO); prep.add_argument("--scope", choices=("pilot10", "full199"), required=True)
    fusion = sub.add_parser("fuse")
    fusion.add_argument("--output-root", type=Path, required=True); fusion.add_argument("--artifact-root", type=Path, required=True); fusion.add_argument("--repo-root", type=Path, default=REPO); fusion.add_argument("--condition-id", choices=CONDITIONS, required=True); fusion.add_argument("--device", default="cuda")
    classified = sub.add_parser("verify-classified")
    classified.add_argument("--output-root", type=Path, required=True); classified.add_argument("--condition-id", choices=CONDITIONS, required=True)
    roofer = sub.add_parser("record-roofer")
    roofer.add_argument("--output-root", type=Path, required=True); roofer.add_argument("--condition-id", choices=CONDITIONS, required=True); roofer.add_argument("--exit-code", type=int, required=True); roofer.add_argument("--runtime-seconds", type=int, required=True)
    close = sub.add_parser("finalize"); close.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    if args.mode == "validate-config":
        config = load_config(args.config); validate_config(config); result = {"status": "VALID", "task_id": config["task_id"]}
    elif args.mode == "prepare":
        result = prepare(output_root=args.output_root, artifact_root=args.artifact_root, repo_root=args.repo_root, scope=args.scope, config_path=args.config)
    elif args.mode == "fuse":
        result = fuse(output_root=args.output_root, artifact_root=args.artifact_root, repo_root=args.repo_root, condition_id=args.condition_id, device=args.device, config_path=args.config)
    elif args.mode == "verify-classified":
        result = verify_classified(args.output_root, args.condition_id, args.config)
    elif args.mode == "record-roofer":
        result = record_roofer(args.output_root, args.condition_id, args.exit_code, args.runtime_seconds)
    else:
        result = finalize(args.output_root, args.config)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
