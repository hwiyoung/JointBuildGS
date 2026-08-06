#!/usr/bin/env python3
"""Build named CloudCompare meshes from the all-398-invocations Roofer result."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
from typing import Any

import numpy as np

from scripts.p2.qualitative_199_cloudcompare_scene_v1.add_shared_footprint_roofer import (
    build_named_obj,
    csv_bytes,
    read_jsonl,
    validate_rows,
    verify_bound,
)
from scripts.p2.qualitative_199_cloudcompare_scene_v1.build_scene import (
    REPO,
    canonical_json_bytes,
    file_record,
    write_new,
)


DEFAULT_CONFIG = REPO / "configs/p2/c1_c2_shared_footprint_199_v2/cloudcompare_v2.json"


def load_config(path: Path) -> dict[str, Any]:
    config = json.loads(path.read_text(encoding="utf-8"))
    if config.get("schema") != "jointbuildgs.p2.c1_c2_shared_footprint_199.all_invocations_cloudcompare.v2":
        raise RuntimeError("unexpected all-invocations CloudCompare config schema")
    if config.get("status") != "USER_APPROVED_FOR_EXECUTION" or config.get("decision_id") != "DEC-P1-019":
        raise RuntimeError("all-invocations CloudCompare conversion is not approved")
    if config.get("scientific_verdict", "missing") is not None:
        raise RuntimeError("scientific_verdict must remain null")
    return config


def git_value(*args: str) -> str:
    process = subprocess.run(["git", *args], cwd=REPO, text=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    return process.stdout.strip() if process.returncode == 0 else "UNKNOWN"


def build(config_path: Path, artifact_root: Path) -> Path:
    config = load_config(config_path)
    source_root = artifact_root / config["source"]["relative_root"]
    scene_root = artifact_root / config["scene"]["relative_root"]
    source_records = {
        key: verify_bound(source_root / spec["path"], spec, f"v2 {key}")
        for key, spec in config["source"].items()
        if key != "relative_root"
    }
    scene_records = {
        key: verify_bound(scene_root / spec["path"], spec, f"scene {key}")
        for key, spec in config["scene"].items()
        if key != "relative_root"
    }
    finalized = json.loads((source_root / config["source"]["finalized"]["path"]).read_text(encoding="utf-8"))
    if finalized.get("task_id") != config["source_task_id"] or finalized.get("roofer_invocation_count") != 398:
        raise RuntimeError("source is not the exact all-398-invocations result")
    rows = read_jsonl(source_root / config["source"]["results"]["path"])
    grouped = validate_rows(rows, config)
    scene_origin = np.asarray(config["frame"]["scene_local_origin_xyz"], dtype=np.float64)
    layers = {}
    index_rows = []
    lod22_sets = {}
    for method, method_rows in grouped.items():
        method_spec = config["methods"][method]
        data, method_index, stats = build_named_obj(method_rows, source_root, scene_origin)
        if stats["completed_building_group_count"] != int(method_spec["expected_lod22_groups"]):
            raise RuntimeError(f"{method} LoD2.2 group count drift")
        if stats["no_lod22_geometry_building_count"] != int(method_spec["expected_no_lod22"]):
            raise RuntimeError(f"{method} no-LoD2.2 count drift")
        output = scene_root / "layers" / method_spec["output_file"]
        write_new(output, data)
        layers[method] = {
            **file_record(output, scene_root),
            **stats,
            "role": method_spec["role"],
            "roofer_invocations": 199,
            "shared_standard_footprint": True,
        }
        index_rows.extend(method_index)
        lod22_sets[method] = {row["stable_id"] for row in method_rows if row.get("lod22_present") is True}
    paired = len(lod22_sets["C1_L_upper"] & lod22_sets["C2_MVS"])
    if paired != int(config["expected_paired_lod22"]):
        raise RuntimeError("paired LoD2.2 count drift")

    index_path = scene_root / "control/all_invocations_v2_roofer_building_index.csv"
    write_new(index_path, csv_bytes(sorted(index_rows, key=lambda row: (row["condition_id"], row["population_index"]))))
    load_order = [
        "layers/lidar_199_extent_local_sample10m.laz",
        "layers/lidar_roofer_199_all_invocations_v2_named_local.obj",
        "layers/mvs_199_extent_local_rgb.ply",
        "layers/mvs_roofer_199_all_invocations_v2_named_local.obj",
        "layers/footprints_199_cloudcompare_named_local.obj",
        "layers/footprint_curtains_199_local.ply",
    ]
    manifest = {
        "schema": "jointbuildgs.p2.c1_c2_shared_footprint_199.all_invocations_cloudcompare_manifest.v2",
        "task_id": config["task_id"],
        "source_task_id": config["source_task_id"],
        "decision_id": config["decision_id"],
        "status": "COMPLETE_ALL_398_INVOCATIONS_BUILDING_NAMED_BUNDLE",
        "population": {"buildings": 199, "building_method_rows": 398, "roofer_invocations": 398},
        "lod22_counts": {"C1_L_upper": len(lod22_sets["C1_L_upper"]), "C2_MVS": len(lod22_sets["C2_MVS"]), "paired": paired},
        "source_records": source_records,
        "scene_records": scene_records,
        "layers": layers,
        "cloudcompare_layer_order": load_order,
        "scientific_verdict": None,
    }
    manifest_path = scene_root / "scene_manifest_all_invocations_roofer_v2.json"
    write_new(manifest_path, canonical_json_bytes(manifest))
    readme_path = scene_root / "README_ALL_INVOCATIONS_ROOFER_V2.txt"
    readme = """JointBuildGS CloudCompare scene from all 398 Roofer invocations

Load in this order:
1. layers/lidar_199_extent_local_sample10m.laz
2. layers/lidar_roofer_199_all_invocations_v2_named_local.obj
3. layers/mvs_199_extent_local_rgb.ply
4. layers/mvs_roofer_199_all_invocations_v2_named_local.obj
5. layers/footprints_199_cloudcompare_named_local.obj
6. layers/footprint_curtains_199_local.ply

Do not add another coordinate shift. Roofer was invoked for all 199 buildings per
method. The OBJ files contain only buildings with actual LoD2.2 geometry: LiDAR 106,
MVS 126. See control/all_invocations_v2_roofer_building_index.csv for all 398 rows.
"""
    write_new(readme_path, readme.encode("utf-8"))
    receipt_path = scene_root / "control/all_invocations_v2_cloudcompare_receipt.json"
    receipt = {
        "schema": "jointbuildgs.p2.c1_c2_shared_footprint_199.all_invocations_cloudcompare_receipt.v2",
        "task_id": config["task_id"],
        "completed_at_utc": datetime.now(timezone.utc).isoformat(),
        "git_commit": git_value("rev-parse", "HEAD"),
        "git_status_porcelain": git_value("status", "--porcelain"),
        "config": file_record(config_path, REPO),
        "script": file_record(Path(__file__).resolve(), REPO),
        "roofer_invocations": 0,
        "scientific_verdict": None,
    }
    write_new(receipt_path, canonical_json_bytes(receipt))
    artifact_manifest_path = scene_root / "control/all_invocations_v2_cloudcompare_artifacts.json"
    write_new(
        artifact_manifest_path,
        canonical_json_bytes({
            "schema": "jointbuildgs.p2.c1_c2_shared_footprint_199.all_invocations_cloudcompare_artifacts.v2",
            "task_id": config["task_id"],
            "records": [layers["C1_L_upper"], layers["C2_MVS"], file_record(index_path, scene_root), file_record(manifest_path, scene_root), file_record(readme_path, scene_root), file_record(receipt_path, scene_root)],
            "scientific_verdict": None,
        }),
    )
    return manifest_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--artifact-root", type=Path, default=Path(os.environ.get("JBGS_ARTIFACT_ROOT", "../JointBuildGS-artifacts")))
    args = parser.parse_args()
    print(build(args.config.resolve(), args.artifact_root.resolve()))


if __name__ == "__main__":
    main()
