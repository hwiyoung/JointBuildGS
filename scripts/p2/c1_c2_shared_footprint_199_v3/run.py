#!/usr/bin/env python3
"""Run the 199-building C1/C2 baseline with the original scene-wide Roofer pattern.

The only condition adapter is the historical scene classifier: PDAL SMRF assigns
ground=2 and the shared GroundSurface-XY footprint overlay assigns non-ground
points inside a footprint to building=6.  Roofer then receives one classified
scene cloud plus the same 199-feature footprint source in one invocation per
condition.  No per-building crop, point gate, voxel thinning, or retry is used.
"""

from __future__ import annotations

import argparse
from collections import Counter
import csv
from datetime import datetime, timezone
import io
import json
import math
from pathlib import Path
import subprocess
from typing import Any, Mapping, Sequence

import laspy
import numpy as np
from shapely.geometry import mapping

from scripts.p2.c1_c2_shared_footprint_199_v1.run import (
    REPO,
    FootprintReference,
    canonical_json_bytes,
    exact_file,
    file_record,
    load_groundsurface_xy,
    read_population,
    sha256_file,
    write_new,
)


CONFIG_PATH = REPO / "configs/p2/c1_c2_shared_footprint_199_v3/original_global_v3.json"
METHODS = ("C1_L_upper", "C2_MVS")


def load_config(path: Path = CONFIG_PATH) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def validate_config(config: Mapping[str, Any]) -> None:
    if config.get("schema") != "jointbuildgs.p2.c1_c2_shared_footprint_199.original_global.v3":
        raise RuntimeError("original-global v3 schema drifted")
    if config.get("status") != "USER_APPROVED_FOR_EXECUTION":
        raise RuntimeError("original-global v3 is not user-approved")
    if int(config["population"]["building_count"]) != 199:
        raise RuntimeError("U_target must contain 199 buildings")
    classification = config["classification"]
    if classification["method"] != "PDAL_SMRF_THEN_SHARED_FOOTPRINT_OVERLAY_ON_NON_GROUND":
        raise RuntimeError("historical scene-classification recipe drifted")
    if not classification.get("same_adapter_for_both_conditions"):
        raise RuntimeError("C1 and C2 must use the same classification adapter")
    if classification.get("voxel_downsampling") is not False:
        raise RuntimeError("original-global v3 forbids voxel downsampling")
    if int(config["roofer"]["expected_invocations"]) != 2:
        raise RuntimeError("original-global v3 requires one Roofer call per condition")
    if config["roofer"]["quality_parameters"] != "ROOFER_DEFAULTS":
        raise RuntimeError("Roofer quality parameters must remain at defaults")
    if config.get("official_PASS_usable", "missing") is not None:
        raise RuntimeError("PASS_usable must remain null before threshold freeze")
    if config.get("scientific_verdict", "missing") is not None:
        raise RuntimeError("scientific verdict must remain null")


def _all_footprints_geojson(
    population: Sequence[Mapping[str, Any]],
    references: Mapping[str, FootprintReference],
) -> dict[str, Any]:
    features = []
    for item in population:
        stable_id = str(item["building_id"])
        features.append(
            {
                "type": "Feature",
                "properties": {
                    "stable_id": stable_id,
                    "class": 6,
                    "population_index": int(item["population_index"]),
                    "input_role": "SHARED_STANDARD_GROUNDSURFACE_XY_CONTROL",
                    "lod2_z_used": False,
                    "roofsurface_used": False,
                },
                "geometry": mapping(references[stable_id].footprint),
            }
        )
    return {
        "type": "FeatureCollection",
        "name": "R_SHARED_GROUNDSURFACE_XY_199_V3",
        "crs": {"type": "name", "properties": {"name": "urn:ogc:def:crs:EPSG::25832"}},
        "features": features,
    }


def _crop_bounds(config: Mapping[str, Any]) -> str:
    x0, y0, x1, y1 = map(float, config["scene"]["roofer_aoi_bbox"])
    buffer_m = float(config["scene"]["classification_context_buffer_m"])
    return f"([{x0-buffer_m:.3f},{x1+buffer_m:.3f}],[{y0-buffer_m:.3f},{y1+buffer_m:.3f}])"


def _common_stages(config: Mapping[str, Any], footprint_path: Path, output_path: Path) -> list[dict[str, Any]]:
    classification = config["classification"]
    return [
        {"type": "filters.crop", "bounds": _crop_bounds(config)},
        {
            "type": "filters.smrf",
            **classification["smrf"],
            "ground_class": int(classification["ground_class"]),
            "other_class": int(classification["unclassified_class"]),
        },
        {
            "type": "filters.overlay",
            "dimension": "Classification",
            "datasource": footprint_path.as_posix(),
            "column": "class",
            "where": f"Classification != {int(classification['ground_class'])}",
            "threads": 1,
        },
        {
            "type": "writers.las",
            "filename": output_path.as_posix(),
            "a_srs": config["scene"]["crs"],
            "minor_version": 4,
            "dataformat_id": 3,
            "compression": "lazperf",
        },
    ]


def _classification_pipeline(
    method: str,
    source: Path,
    footprint_path: Path,
    output_path: Path,
    config: Mapping[str, Any],
) -> dict[str, Any]:
    spec = config["inputs"][method]
    if method == "C1_L_upper":
        # The Gate-S0 contract froze the numeric UTM32 alignment against the
        # cameras/LoD2.  The source WKT says 32632, so override_srs retags the
        # already-aligned numeric coordinates without moving XYZ.
        initial: list[dict[str, Any]] = [
            {
                "type": "readers.las",
                "filename": source.as_posix(),
                "override_srs": config["scene"]["crs"],
            }
        ]
    elif method == "C2_MVS":
        sx, sy, sz = map(float, spec["world_shift_xyz"])
        initial = [
            {"type": "readers.ply", "filename": source.as_posix()},
            {
                "type": "filters.transformation",
                "matrix": f"1 0 0 {sx:.9f} 0 1 0 {sy:.9f} 0 0 1 {sz:.9f} 0 0 0 1",
            },
        ]
    else:
        raise RuntimeError(f"unknown condition: {method}")
    return {"pipeline": [*initial, *_common_stages(config, footprint_path, output_path)]}


def prepare(output_root: Path, artifact_root: Path, config_path: Path = CONFIG_PATH) -> dict[str, Any]:
    config = load_config(config_path)
    validate_config(config)
    if output_root.exists() and any(output_root.iterdir()):
        raise RuntimeError("fresh add-once original-global namespace required")
    output_root.mkdir(parents=True, exist_ok=True)

    population_spec = config["population"]
    population_path = artifact_root / population_spec["common_manifest_relative_path"]
    population = read_population(population_path, population_spec)
    source_records: dict[str, Any] = {
        "population": exact_file(
            population_path,
            {"bytes": population_spec["common_manifest_bytes"], "sha256": population_spec["common_manifest_sha256"]},
        ),
        "conditions": {},
        "shared_footprints": [],
    }
    for method in METHODS:
        spec = config["inputs"][method]
        source = artifact_root / spec["relative_path"]
        source_records["conditions"][method] = exact_file(source, spec)

    footprint_paths = []
    for spec in config["inputs"]["shared_standard_footprints"]:
        path = artifact_root / spec["relative_path"]
        source_records["shared_footprints"].append(exact_file(path, spec))
        footprint_paths.append(path)
    ids = [str(item["building_id"]) for item in population]
    references = load_groundsurface_xy(footprint_paths, ids)
    footprint_path = output_root / "freeze/shared_footprints_199.geojson"
    write_new(footprint_path, canonical_json_bytes(_all_footprints_geojson(population, references)))

    pipelines: dict[str, Any] = {}
    for method in METHODS:
        work = output_root / "work" / method
        work.mkdir(parents=True, exist_ok=True)
        source = artifact_root / config["inputs"][method]["relative_path"]
        classified = work / "classified_scene.laz"
        pipeline_path = work / "classification_pipeline.json"
        pipeline = _classification_pipeline(method, source, footprint_path, classified, config)
        write_new(pipeline_path, canonical_json_bytes(pipeline))
        pipelines[method] = {
            "pipeline": file_record(pipeline_path, output_root),
            "classified_scene_path": classified.relative_to(output_root).as_posix(),
            "roofer_output_directory": (work / "roofer_output").relative_to(output_root).as_posix(),
        }

    receipt = {
        "schema": "jointbuildgs.p2.c1_c2_shared_footprint_199.original_global.prepared.v3",
        "task_id": config["task_id"],
        "decision_id": config["decision_id"],
        "status": "PREPARED_FOR_TWO_GLOBAL_CLASSIFICATIONS_AND_TWO_ROOFER_CALLS",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "source_records": source_records,
        "population_count": len(population),
        "ordered_building_ids": ids,
        "shared_footprints": file_record(footprint_path, output_root),
        "classification_pipelines": pipelines,
        "method_contract": {
            "scene_wide_cloud_per_condition": True,
            "single_199_feature_footprint_source": True,
            "per_building_pre_crop": False,
            "voxel_downsampling": False,
            "roofer_invocations_expected": 2,
            "roofer_quality_parameters": "defaults",
        },
        "config": file_record(config_path, REPO),
        "script": file_record(Path(__file__).resolve(), REPO),
        "official_PASS_usable": None,
        "scientific_verdict": None,
    }
    write_new(output_root / "control/prepared_v3.json", canonical_json_bytes(receipt))
    return receipt


def _class_counts(path: Path) -> tuple[int, dict[str, int], int | None]:
    counts: Counter[int] = Counter()
    with laspy.open(path) as reader:
        total = int(reader.header.point_count)
        crs = reader.header.parse_crs()
        epsg = crs.to_epsg() if crs is not None else None
        for chunk in reader.chunk_iterator(2_000_000):
            values, numbers = np.unique(np.asarray(chunk.classification), return_counts=True)
            counts.update({int(value): int(number) for value, number in zip(values, numbers)})
    return total, {str(key): counts[key] for key in sorted(counts)}, epsg


def verify_classified(output_root: Path, method: str, config_path: Path = CONFIG_PATH) -> dict[str, Any]:
    config = load_config(config_path)
    validate_config(config)
    if method not in METHODS:
        raise RuntimeError(f"unknown condition: {method}")
    path = output_root / "work" / method / "classified_scene.laz"
    if not path.is_file():
        raise FileNotFoundError(path)
    total, counts, epsg = _class_counts(path)
    for required in (str(config["classification"]["ground_class"]), str(config["classification"]["building_class"])):
        if counts.get(required, 0) <= 0:
            raise RuntimeError(f"{method} classified scene lacks required class {required}: {counts}")
    if epsg != 25832:
        raise RuntimeError(f"{method} classified scene CRS drifted: {epsg}")
    receipt = {
        "schema": "jointbuildgs.p2.c1_c2_shared_footprint_199.classified_scene.v3",
        "condition_id": method,
        "status": "CLASSIFIED_SCENE_READY",
        "classified_scene": file_record(path, output_root),
        "point_count": total,
        "class_counts": counts,
        "epsg": epsg,
        "point_deletion_after_fixed_aoi_context_crop": False,
        "voxel_downsampling": False,
        "official_PASS_usable": None,
        "scientific_verdict": None,
    }
    receipt_path = output_root / "work" / method / "classified_scene_receipt.json"
    write_new(receipt_path, canonical_json_bytes(receipt))
    return receipt


def record_roofer(output_root: Path, method: str, exit_code: int, runtime_seconds: int) -> dict[str, Any]:
    if method not in METHODS:
        raise RuntimeError(f"unknown condition: {method}")
    work = output_root / "work" / method
    marker = work / "roofer_terminal.json"
    if marker.exists():
        raise RuntimeError(f"Roofer terminal marker already exists: {marker}")
    files = sorted((work / "roofer_output").glob("*.city.jsonl"))
    receipt = {
        "schema": "jointbuildgs.p2.c1_c2_shared_footprint_199.roofer_terminal.v3",
        "condition_id": method,
        "status": "COMPLETED" if int(exit_code) == 0 and files else "FAILED",
        "exit_code": int(exit_code),
        "runtime_seconds": int(runtime_seconds),
        "roofer_invocation_count": 1,
        "outputs": [file_record(path, output_root) for path in files],
        "quality_driven_retry": False,
        "official_PASS_usable": None,
        "scientific_verdict": None,
    }
    write_new(marker, canonical_json_bytes(receipt))
    return receipt


def _shift_indices(value: Any, offset: int) -> Any:
    if isinstance(value, int):
        return value + offset
    if isinstance(value, list):
        return [_shift_indices(item, offset) for item in value]
    return value


def _absolute_vertex(vertex: Sequence[float], transform: Mapping[str, Sequence[float]]) -> list[float]:
    return [float(vertex[i]) * float(transform["scale"][i]) + float(transform["translate"][i]) for i in range(3)]


def combine_cityjsonseq(paths: Sequence[Path], output: Path) -> None:
    top: dict[str, Any] | None = None
    cityobjects: dict[str, Any] = {}
    vertices: list[list[int]] = []
    for path in paths:
        with path.open(encoding="utf-8") as stream:
            header = json.loads(stream.readline())
            if top is None:
                top = header
                top["CityObjects"] = {}
                top["vertices"] = []
            source_transform = header["transform"]
            target_transform = top["transform"]
            for line in stream:
                if not line.strip():
                    continue
                feature = json.loads(line)
                converted = []
                for vertex in feature.get("vertices", []):
                    absolute = _absolute_vertex(vertex, source_transform)
                    converted.append([
                        int(round((absolute[i] - float(target_transform["translate"][i])) / float(target_transform["scale"][i])))
                        for i in range(3)
                    ])
                offset = len(vertices)
                vertices.extend(converted)
                for object_id, cityobject in feature.get("CityObjects", {}).items():
                    if object_id in cityobjects:
                        raise RuntimeError(f"duplicate CityObject id: {object_id}")
                    for geometry in cityobject.get("geometry", []):
                        geometry["boundaries"] = _shift_indices(geometry.get("boundaries", []), offset)
                    cityobjects[object_id] = cityobject
    if top is None:
        raise RuntimeError("no CityJSONSequence files to combine")
    top["CityObjects"] = cityobjects
    top["vertices"] = vertices
    write_new(output, (json.dumps(top, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8"))


def _parse_features(paths: Sequence[Path]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for path in paths:
        with path.open(encoding="utf-8") as stream:
            next(stream)
            for line in stream:
                if not line.strip():
                    continue
                feature = json.loads(line)
                feature_id = str(feature.get("id", ""))
                objects = feature.get("CityObjects", {})
                building = objects.get(feature_id) or next(
                    (obj for obj in objects.values() if obj.get("type") == "Building"), None
                )
                if building is None:
                    continue
                lods = sorted({
                    str(geometry.get("lod"))
                    for obj in objects.values()
                    for geometry in obj.get("geometry", [])
                    if geometry.get("lod") is not None
                })
                result[feature_id] = {
                    "attributes": building.get("attributes", {}),
                    "lods": lods,
                    "source_file": path.name,
                }
    return result


def _val_by_id(report: Mapping[str, Any]) -> dict[str, bool]:
    return {
        str(feature["id"]): bool(feature.get("validity"))
        for feature in report.get("features", [])
        if feature.get("id") is not None
    }


def _status(feature: Mapping[str, Any] | None, valid: bool | None) -> tuple[str, str]:
    if feature is None:
        return "MISSING", "missing_roofer_feature"
    attrs = feature["attributes"]
    if attrs.get("rf_success") is False:
        return "FAILED", "rf_success_false"
    if attrs.get("rf_pointcloud_unusable") is True:
        return "FAILED", "rf_pointcloud_unusable"
    if "2.2" not in feature["lods"]:
        return "FAILED", "missing_lod22_geometry"
    if valid is None:
        return "FAILED", "missing_val3dity_feature"
    if not valid:
        return "FAILED", "val3dity_invalid"
    return "TECHNICAL_VALID_LOD22", "technical_valid_lod22"


def finalize(output_root: Path, config_path: Path = CONFIG_PATH) -> dict[str, Any]:
    config = load_config(config_path)
    validate_config(config)
    prepared = json.loads((output_root / "control/prepared_v3.json").read_text(encoding="utf-8"))
    ids = [str(value) for value in prepared["ordered_building_ids"]]
    rows: list[dict[str, Any]] = []
    summaries: dict[str, Counter[str]] = {}
    for method in METHODS:
        work = output_root / "work" / method
        terminal = json.loads((work / "roofer_terminal.json").read_text(encoding="utf-8"))
        raw_files = sorted((work / "roofer_output").glob("*.city.jsonl"))
        features = _parse_features(raw_files) if raw_files else {}
        val_by_id: dict[str, bool] = {}
        assembled_record = None
        val_record = None
        val_exit_code = None
        if raw_files:
            assembled = work / "assembled.city.json"
            combine_cityjsonseq(raw_files, assembled)
            val_report = work / "val3dity_report.json"
            process = subprocess.run(
                ["val3dity", assembled.as_posix(), "--report", val_report.as_posix()],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                check=False,
            )
            (work / "val3dity.log").write_text(process.stdout or "", encoding="utf-8")
            val_exit_code = int(process.returncode)
            if val_report.is_file():
                val_by_id = _val_by_id(json.loads(val_report.read_text(encoding="utf-8")))
                val_record = file_record(val_report, output_root)
            assembled_record = file_record(assembled, output_root)
        reasons: Counter[str] = Counter()
        for population_index, stable_id in enumerate(ids, start=1):
            feature = features.get(stable_id)
            valid = val_by_id.get(stable_id)
            status, reason = _status(feature, valid)
            reasons[reason] += 1
            attrs = feature["attributes"] if feature else {}
            rows.append({
                "population_index": population_index,
                "stable_id": stable_id,
                "condition_id": method,
                "status": status,
                "reason": reason,
                "lods": feature["lods"] if feature else [],
                "has_lod22": bool(feature and "2.2" in feature["lods"]),
                "val3dity_valid": valid,
                "rf_success": attrs.get("rf_success"),
                "rf_pointcloud_unusable": attrs.get("rf_pointcloud_unusable"),
                "rf_extrusion_mode": attrs.get("rf_extrusion_mode"),
                "rf_roof_type": attrs.get("rf_roof_type"),
                "rf_pt_density": attrs.get("rf_pt_density"),
                "rf_nodata_frac": attrs.get("rf_nodata_frac"),
                "rf_rmse_lod22": attrs.get("rf_rmse_lod22"),
                "rf_roof_planes": attrs.get("rf_roof_planes"),
                "source_file": feature.get("source_file") if feature else None,
                "official_PASS_usable": None,
                "scientific_verdict": None,
            })
        summaries[method] = reasons
        method_receipt = {
            "condition_id": method,
            "terminal": terminal,
            "raw_cityjsonseq_files": [file_record(path, output_root) for path in raw_files],
            "assembled_cityjson": assembled_record,
            "val3dity_report": val_record,
            "val3dity_exit_code": val_exit_code,
            "feature_count": len(features),
            "val3dity_feature_count": len(val_by_id),
            "reason_counts": dict(reasons),
        }
        write_new(work / "postprocess_receipt.json", canonical_json_bytes(method_receipt))

    if len(rows) != 398:
        raise RuntimeError(f"expected 398 building-method rows, got {len(rows)}")
    results_path = output_root / "results/building_method_results_v3.jsonl"
    write_new(results_path, b"".join(canonical_json_bytes(row) for row in rows))
    stream = io.StringIO(newline="")
    fields = [
        "population_index", "stable_id", "condition_id", "status", "reason", "has_lod22",
        "val3dity_valid", "rf_success", "rf_pointcloud_unusable", "rf_extrusion_mode",
        "rf_roof_type", "rf_pt_density", "rf_nodata_frac", "rf_rmse_lod22", "rf_roof_planes",
    ]
    writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    writer.writerows({field: row.get(field) for field in fields} for row in rows)
    csv_path = output_root / "results/building_method_status_v3.csv"
    write_new(csv_path, stream.getvalue().encode("utf-8"))
    receipt = {
        "schema": "jointbuildgs.p2.c1_c2_shared_footprint_199.original_global.finalized.v3",
        "task_id": config["task_id"],
        "status": "TECHNICAL_COMPLETE_WITH_EXPLICIT_MISSINGNESS",
        "completed_utc": datetime.now(timezone.utc).isoformat(),
        "building_count": 199,
        "building_method_rows": 398,
        "roofer_invocation_count": 2,
        "counts_by_method": {method: dict(summaries[method]) for method in METHODS},
        "result_jsonl": file_record(results_path, output_root),
        "result_csv": file_record(csv_path, output_root),
        "quality_interpretation": "diagnostic dimensions only; no frozen PASS_usable threshold",
        "official_PASS_usable": None,
        "scientific_verdict": None,
    }
    write_new(output_root / "control/finalized_v3.json", canonical_json_bytes(receipt))
    return receipt


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="mode", required=True)
    prep = sub.add_parser("prepare")
    prep.add_argument("--output-root", type=Path, required=True)
    prep.add_argument("--artifact-root", type=Path, required=True)
    prep.add_argument("--config", type=Path, default=CONFIG_PATH)
    verify = sub.add_parser("verify-classified")
    verify.add_argument("--output-root", type=Path, required=True)
    verify.add_argument("--method", choices=METHODS, required=True)
    verify.add_argument("--config", type=Path, default=CONFIG_PATH)
    terminal = sub.add_parser("record-roofer")
    terminal.add_argument("--output-root", type=Path, required=True)
    terminal.add_argument("--method", choices=METHODS, required=True)
    terminal.add_argument("--exit-code", type=int, required=True)
    terminal.add_argument("--runtime-seconds", type=int, required=True)
    close = sub.add_parser("finalize")
    close.add_argument("--output-root", type=Path, required=True)
    close.add_argument("--config", type=Path, default=CONFIG_PATH)
    args = parser.parse_args()
    if args.mode == "prepare":
        result = prepare(args.output_root, args.artifact_root, args.config)
    elif args.mode == "verify-classified":
        result = verify_classified(args.output_root, args.method, args.config)
    elif args.mode == "record-roofer":
        result = record_roofer(args.output_root, args.method, args.exit_code, args.runtime_seconds)
    else:
        result = finalize(args.output_root, args.config)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
