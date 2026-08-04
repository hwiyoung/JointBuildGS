#!/usr/bin/env python3
"""Prepare and receipt building-specific C3 GT-footprint oracle Roofer diagnostics."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np
from shapely import contains_xy

from scripts.p2.c1_c2_oracle_c3_extract_v1.contract import (
    canonical_json_bytes,
    deterministic_voxel_one,
    file_record,
    footprint_geojson,
    load_building_references,
    load_config,
    validate_config,
    write_las,
    write_new,
)
from scripts.p2.c1_c2_oracle_c3_extract_v1.render_results import _read_binary_vertex_ply
from src.visualization.fixed_view_qualitative import load_las_points


def _roof_points(output_root: Path, condition_id: str, stable_id: str, footprint: Any, voxel_m: float) -> tuple[np.ndarray, int]:
    source = output_root / f"c3/{condition_id}/buildings/{stable_id}/rendered_depth_fused_surface_points_v1.ply"
    rows = _read_binary_vertex_ply(source)
    xyz = np.column_stack((rows["x"], rows["y"], rows["z"])).astype(np.float64)
    labels = np.asarray(rows["semantic_class"], dtype=np.uint8)
    selected = (labels == 1) & contains_xy(footprint, xyz[:, 0], xyz[:, 1])
    return deterministic_voxel_one(xyz[selected], voxel_m), int(np.count_nonzero(selected))


def _shared_c2_ground(output_root: Path, stable_id: str) -> tuple[np.ndarray, dict[str, Any]]:
    source = output_root / f"operations/C2_MVS_GT_FOOTPRINT_ORACLE/{stable_id}/work/input.las"
    points = load_las_points(source)
    if points.classification is None:
        raise RuntimeError(f"C2 shared terrain classifications missing: {stable_id}")
    ground = points.xyz[points.classification == 2]
    if not len(ground):
        raise RuntimeError(f"C2 shared terrain class 2 is empty: {stable_id}")
    return ground, file_record(source, output_root)


def prepare(output_root: Path, lod2_path: Path) -> dict[str, Any]:
    config = load_config()
    validate_config(config, require_activation=True)
    policy = config["c3_roofer_oracle"]
    references = load_building_references(lod2_path, config["scope"]["building_ids"])
    rows = []
    for condition in config["c3_training_provenance"]["conditions"]:
        condition_id = condition["condition_id"]
        for stable_id in config["scope"]["building_ids"]:
            reference = references[stable_id]
            building, prevoxel_count = _roof_points(
                output_root,
                condition_id,
                stable_id,
                reference.footprint,
                float(policy["deterministic_voxel_m"]),
            )
            ground, terrain_source = _shared_c2_ground(output_root, stable_id)
            work = output_root / "operations" / f"{condition_id}_GT_FOOTPRINT_ORACLE" / stable_id / "work"
            input_path = work / "input.las"
            footprint_path = work / "gt_footprint_oracle.geojson"
            write_las(input_path, building, ground)
            write_new(footprint_path, canonical_json_bytes(footprint_geojson(reference)))
            minimum = int(policy["minimum_class6_points"])
            eligible = len(building) >= minimum
            row = {
                "operation_unit_id": f"{condition_id}|{stable_id}",
                "condition_id": condition_id,
                "stable_id": stable_id,
                "work_directory": work.relative_to(output_root).as_posix(),
                "output_directory": (work / "out").relative_to(output_root).as_posix(),
                "input": file_record(input_path, output_root),
                "footprint": file_record(footprint_path, output_root),
                "rendered_depth_fused_source": file_record(
                    output_root / f"c3/{condition_id}/buildings/{stable_id}/rendered_depth_fused_surface_points_v1.ply",
                    output_root,
                ),
                "shared_terrain_source": terrain_source,
                "classification": {
                    "roof_semantic_inside_footprint_prevoxel_count": prevoxel_count,
                    "building_class6_count": int(len(building)),
                    "ground_class2_count": int(len(ground)),
                    "deterministic_voxel_m": float(policy["deterministic_voxel_m"]),
                },
                "roofer_eligible": eligible,
                "pre_roofer_failure": None if eligible else {
                    "code": "INSUFFICIENT_C3_ROOF_SEMANTIC_EVIDENCE",
                    "observed_class6_points": int(len(building)),
                    "minimum_class6_points": minimum,
                },
                "oracle_diagnostic": True,
                "official_honest_stage3": False,
                "roofsurface_reference_used_as_input": False,
                "scientific_verdict": None,
            }
            write_new(work / "prepared_v1.json", canonical_json_bytes(row))
            rows.append(row)
    eligible = [row for row in rows if row["roofer_eligible"]]
    failures = [row for row in rows if not row["roofer_eligible"]]
    if len(rows) != 6 or len(eligible) != int(policy["expected_invocations"]) or len(failures) != int(policy["expected_pre_roofer_failures"]):
        raise RuntimeError(f"C3 oracle Roofer eligibility drift: rows={len(rows)} jobs={len(eligible)} failures={len(failures)}")
    if {(row["condition_id"], row["stable_id"]) for row in failures} != {
        ("C3_1_SEM", "DEBY_LOD2_4907177"),
        ("C3_2_SEM_DEPTH", "DEBY_LOD2_4907177"),
    }:
        raise RuntimeError("unexpected C3 pre-Roofer failure identities")
    write_new(output_root / "freeze/c3_roofer_execution_units_v1.jsonl", b"".join(canonical_json_bytes(row) for row in rows))
    tsv = "operation_unit_id\twork_directory\n" + "".join(
        f"{row['operation_unit_id']}\t{row['work_directory']}\n" for row in eligible
    )
    write_new(output_root / "freeze/c3_roofer_execution_units_v1.tsv", tsv.encode("utf-8"))
    body = {
        "schema": "jointbuildgs.c3_oracle_roofer_preparation.v1",
        "status": "PREPARED_FOUR_ROOFER_OPERATIONS_TWO_INSUFFICIENT_EVIDENCE_FAILURES",
        "building_method_record_count": 6,
        "roofer_operation_count": 4,
        "pre_roofer_failure_count": 2,
        "operation_ids": [row["operation_unit_id"] for row in eligible],
        "failure_ids": [row["operation_unit_id"] for row in failures],
        "building_source": policy["building_source"],
        "shared_terrain_source": policy["shared_terrain_source"],
        "roofer_invocations_so_far": 0,
        "official_honest_stage3": False,
        "scientific_verdict": None,
    }
    write_new(output_root / "control/c3_roofer_prepared_v1.json", canonical_json_bytes(body))
    return body


def record_terminal(output_root: Path, operation_unit_id: str, exit_code: int, runtime_seconds: int) -> dict[str, Any]:
    rows = [
        json.loads(line)
        for line in (output_root / "freeze/c3_roofer_execution_units_v1.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    matches = [row for row in rows if row["operation_unit_id"] == operation_unit_id]
    if len(matches) != 1 or not matches[0]["roofer_eligible"]:
        raise RuntimeError(f"unknown or ineligible C3 Roofer operation: {operation_unit_id}")
    row = matches[0]
    work = output_root / row["work_directory"]
    terminal_path = work / "roofer_terminal_v1.json"
    outputs = sorted((work / "out").glob("*.city.jsonl")) if (work / "out").is_dir() else []
    status = "COMPLETED" if exit_code == 0 and len(outputs) == 1 else "FAILED"
    body = {
        "schema": "jointbuildgs.c3_oracle_roofer_terminal.v1",
        "status": status,
        "operation_unit_id": operation_unit_id,
        "condition_id": row["condition_id"],
        "stable_id": row["stable_id"],
        "exit_code": int(exit_code),
        "runtime_seconds": int(runtime_seconds),
        "input": row["input"],
        "footprint": row["footprint"],
        "outputs": [file_record(path, output_root) for path in outputs],
        "oracle_diagnostic": True,
        "official_honest_stage3": False,
        "scientific_verdict": None,
    }
    write_new(terminal_path, canonical_json_bytes(body))
    if status != "COMPLETED":
        raise RuntimeError(f"C3 Roofer failed: {operation_unit_id} exit={exit_code} outputs={len(outputs)}")
    return body


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="mode", required=True)
    prep = sub.add_parser("prepare")
    prep.add_argument("--output-root", type=Path, required=True)
    prep.add_argument("--lod2", type=Path, required=True)
    terminal = sub.add_parser("record-terminal")
    terminal.add_argument("--output-root", type=Path, required=True)
    terminal.add_argument("--operation-unit-id", required=True)
    terminal.add_argument("--exit-code", type=int, required=True)
    terminal.add_argument("--runtime-seconds", type=int, required=True)
    args = parser.parse_args()
    if args.mode == "prepare":
        result = prepare(args.output_root, args.lod2)
    else:
        result = record_terminal(args.output_root, args.operation_unit_id, args.exit_code, args.runtime_seconds)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
