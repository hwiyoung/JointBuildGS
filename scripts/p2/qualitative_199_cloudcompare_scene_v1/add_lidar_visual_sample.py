#!/usr/bin/env python3
"""Create an exact-size deterministic LiDAR sample for CloudCompare visualization."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import subprocess
from typing import Any, Mapping

import laspy
import numpy as np

from scripts.p2.qualitative_199_cloudcompare_scene_v1.build_scene import (
    REPO,
    canonical_json_bytes,
    file_record,
    sha256_file,
    write_new,
)


DEFAULT_CONFIG = REPO / "configs/p2/qualitative_199_cloudcompare_scene_v1/lidar_visual_sample_v1.json"


def load_config(path: Path) -> dict[str, Any]:
    config = json.loads(path.read_text(encoding="utf-8"))
    if config.get("schema") != "jointbuildgs.p2.qualitative_199_cloudcompare_scene.lidar_visual_sample.v1":
        raise RuntimeError("unexpected LiDAR visual sample config schema")
    if config.get("status") != "USER_APPROVED_FOR_EXECUTION":
        raise RuntimeError("LiDAR visual sample is not user-approved")
    if config.get("scientific_use_allowed") is not False or config.get("scientific_verdict", "missing") is not None:
        raise RuntimeError("LiDAR sample must remain visualization-only and non-verdict")
    sampling = config["sampling"]
    source_points = int(config["source"]["points"])
    target_points = int(sampling["target_points"])
    multiplier = int(sampling["source_index_multiplier"])
    if not 0 < target_points < source_points or math.gcd(multiplier, source_points) != 1:
        raise RuntimeError("sampling parameters do not define an exact affine permutation sample")
    if multiplier * source_points >= 2**63:
        raise RuntimeError("sampling multiplication exceeds signed int64")
    return config


def verify_bound(path: Path, spec: Mapping[str, Any], label: str) -> dict[str, Any]:
    if not path.is_file() or path.is_symlink():
        raise RuntimeError(f"missing or non-regular {label}: {path}")
    size, digest = sha256_file(path)
    if size != int(spec["bytes"]) or digest != str(spec["sha256"]):
        raise RuntimeError(f"{label} identity drift: {size}/{digest}")
    return {"path": str(path), "bytes": size, "sha256": digest, "verification": "sha256_rehash"}


def selected_mask(
    start_index: int,
    count: int,
    source_points: int,
    target_points: int,
    multiplier: int,
    offset: int,
) -> np.ndarray:
    indices = np.arange(start_index, start_index + count, dtype=np.int64)
    return ((indices * multiplier + offset) % source_points) < target_points


def write_sample(source: Path, output: Path, sampling: Mapping[str, Any]) -> dict[str, Any]:
    target = int(sampling["target_points"])
    multiplier = int(sampling["source_index_multiplier"])
    offset = int(sampling["source_index_offset"])
    chunk_points = int(sampling["chunk_points"])
    output.parent.mkdir(parents=True, exist_ok=True)
    with laspy.open(source) as reader:
        source_points = int(reader.header.point_count)
        header = laspy.LasHeader(point_format=reader.header.point_format, version=reader.header.version)
        header.scales = reader.header.scales.copy()
        header.offsets = reader.header.offsets.copy()
        header.vlrs = reader.header.vlrs.copy()
        header.evlrs = reader.header.evlrs.copy() if reader.header.evlrs else None
        written = 0
        scanned = 0
        with laspy.open(output, mode="w", header=header, do_compress=True) as writer:
            for chunk in reader.chunk_iterator(chunk_points):
                count = len(chunk)
                mask = selected_mask(scanned, count, source_points, target, multiplier, offset)
                if np.any(mask):
                    selected = chunk[mask]
                    writer.write_points(selected)
                    written += len(selected)
                scanned += count
    if scanned != source_points or written != target:
        raise RuntimeError(f"LiDAR sample count drift: scanned={scanned}, written={written}, target={target}")
    with laspy.open(output) as check:
        if int(check.header.point_count) != target:
            raise RuntimeError("written LiDAR header point count drift")
        dimensions = list(check.header.point_format.dimension_names)
        bounds = [check.header.mins.tolist(), check.header.maxs.tolist()]
    return {
        "source_point_count": source_points,
        "sample_point_count": target,
        "sampling_fraction": target / source_points,
        "point_dimensions_preserved": dimensions,
        "local_bounds_xyz": bounds,
    }


def git_value(*args: str) -> str:
    process = subprocess.run(["git", *args], cwd=REPO, text=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    return process.stdout.strip() if process.returncode == 0 else "UNKNOWN"


def build(config_path: Path, artifact_root: Path) -> Path:
    config = load_config(config_path)
    scene_root = artifact_root / str(config["scene_relative_root"])
    source_path = scene_root / str(config["source"]["path"])
    parent_path = scene_root / str(config["parent_manifest"]["path"])
    source_record = verify_bound(source_path, config["source"], "full LiDAR scene layer")
    parent_record = verify_bound(parent_path, config["parent_manifest"], "shared-footprint Roofer scene manifest")
    output_path = scene_root / str(config["output_file"])
    stats = write_sample(source_path, output_path, config["sampling"])
    output_record = {**file_record(output_path, scene_root), **stats}

    parent = json.loads(parent_path.read_text(encoding="utf-8"))
    load_order = list(parent["cloudcompare_layer_order"])
    if load_order[0] != "layers/lidar_199_extent_local.laz":
        raise RuntimeError("parent CloudCompare LiDAR load order drift")
    load_order[0] = str(config["output_file"])
    manifest = {
        "schema": "jointbuildgs.p2.qualitative_199_cloudcompare_scene.sampled_lidar_manifest.v1",
        "task_id": config["task_id"],
        "status": "COMPLETE_VISUALIZATION_ONLY_10M_LIDAR_SAMPLE",
        "parent_manifest": parent_record,
        "source_full_lidar": source_record,
        "sampled_lidar": output_record,
        "sampling": config["sampling"],
        "cloudcompare_layer_order": load_order,
        "scientific_use_allowed": False,
        "scientific_verdict": None,
    }
    manifest_path = scene_root / "scene_manifest_shared_footprint_roofer_sampled_lidar_v1.json"
    write_new(manifest_path, canonical_json_bytes(manifest))
    readme_path = scene_root / "README_SHARED_FOOTPRINT_ROOFER_SAMPLED_LIDAR_V1.txt"
    readme = """JointBuildGS CloudCompare scene with deterministic 10M-point LiDAR sample

Load these files together, in this order:
1. layers/lidar_199_extent_local_sample10m.laz
2. layers/lidar_roofer_199_shared_footprint_named_local.obj
3. layers/mvs_199_extent_local_rgb.ply
4. layers/mvs_roofer_199_shared_footprint_named_local.obj
5. layers/footprints_199_cloudcompare_named_local.obj
6. layers/footprint_curtains_199_local.ply

Do not add another coordinate shift. The sampled LAZ is visualization-only and must
not be used as Roofer, metric, or scientific-analysis input. Roofer used the frozen
full-resolution source recorded in the run receipt.
"""
    write_new(readme_path, readme.encode("utf-8"))
    receipt_path = scene_root / "control/lidar_visual_sample_receipt_v1.json"
    receipt = {
        "schema": "jointbuildgs.p2.qualitative_199_cloudcompare_scene.lidar_visual_sample_receipt.v1",
        "task_id": config["task_id"],
        "completed_at_utc": datetime.now(timezone.utc).isoformat(),
        "git_commit": git_value("rev-parse", "HEAD"),
        "git_status_porcelain": git_value("status", "--porcelain"),
        "config": file_record(config_path, REPO),
        "script": file_record(Path(__file__).resolve(), REPO),
        "source": source_record,
        "output": output_record,
        "scientific_use_allowed": False,
        "scientific_verdict": None,
    }
    write_new(receipt_path, canonical_json_bytes(receipt))
    artifact_manifest_path = scene_root / "control/lidar_visual_sample_artifact_manifest_v1.json"
    write_new(
        artifact_manifest_path,
        canonical_json_bytes({
            "schema": "jointbuildgs.p2.qualitative_199_cloudcompare_scene.lidar_visual_sample_artifacts.v1",
            "task_id": config["task_id"],
            "records": [output_record, file_record(manifest_path, scene_root), file_record(readme_path, scene_root), file_record(receipt_path, scene_root)],
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
