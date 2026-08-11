#!/usr/bin/env python3
"""Cross-tab frozen sparse SfM building-prism support with the C2 raw-support census."""
from __future__ import annotations

from collections import Counter, defaultdict
import csv
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path

import numpy as np


REPO = Path("/workspace/JointBuildGS")
AR = Path("/artifacts/JointBuildGS")
CONFIG = REPO / "configs/p2/sparse_seed_dense_support_census_199_v1/census.json"
SOURCE = REPO / "scripts/p2/sparse_seed_dense_support_census_199_v1/run.py"
TASK = AR / "phase-payloads/p2/sparse_seed_dense_support_census_199_v1/P2-SPARSE-SEED-DENSE-SUPPORT-CENSUS-199-v1"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def verify(path: Path, expected: str) -> dict:
    if not path.is_file() or sha256(path) != expected:
        raise RuntimeError(f"input missing or drifted: {path}")
    return {"path": str(path), "bytes": path.stat().st_size, "sha256": expected}


def write_json(path: Path, body: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(body, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, path)


def main() -> None:
    cfg = json.loads(CONFIG.read_text())
    if TASK.exists():
        raise RuntimeError(f"add-once task exists: {TASK}")
    building_path = AR / cfg["building_manifest"]
    census_path = AR / cfg["mvs_improvement_census"]
    points_path = AR / cfg["points3d"]
    crosswalk_path = REPO / cfg["exact_937_crosswalk"]
    bindings = {
        "building_manifest": verify(building_path, cfg["building_manifest_sha256"]),
        "mvs_improvement_census": verify(census_path, cfg["mvs_improvement_census_sha256"]),
        "points3D": verify(points_path, cfg["points3d_sha256"]),
        "exact_937_crosswalk": verify(crosswalk_path, cfg["exact_937_crosswalk_sha256"]),
    }
    buildings = [json.loads(line) for line in building_path.read_text().splitlines() if line]
    by_id = {str(row["building_id"]): row for row in buildings}
    with census_path.open(newline="") as stream:
        census = list(csv.DictReader(stream))
    candidates = [row for row in census if row["primary_improvement_track"] == cfg["candidate_primary_track"]]
    candidate_ids = {row["stable_id"] for row in candidates}
    exact_ids = {int(row["colmap_image_id"]) for row in json.loads(crosswalk_path.read_text())["rows"]}

    cell_size = 10.0
    grid: defaultdict[tuple[int, int], list[str]] = defaultdict(list)
    for building_id in candidate_ids:
        min_x, min_y, max_x, max_y = map(float, by_id[building_id]["building_bbox_xy"])
        for gx in range(math.floor(min_x / cell_size), math.floor(max_x / cell_size) + 1):
            for gy in range(math.floor(min_y / cell_size), math.floor(max_y / cell_size) + 1):
                grid[(gx, gy)].append(building_id)
    counts = {building_id: {"xy": 0, "xyz": 0, "camera_tracks": Counter()} for building_id in candidate_ids}
    shift = np.asarray(cfg["sparse_local_shift_xyz"], dtype=np.float64)
    scanned = 0
    with points_path.open() as stream:
        for line in stream:
            if not line or line[0] == "#":
                continue
            fields = line.split()
            scanned += 1
            xyz = np.asarray(fields[1:4], dtype=np.float64) + shift
            key = (math.floor(float(xyz[0]) / cell_size), math.floor(float(xyz[1]) / cell_size))
            for building_id in grid.get(key, ()):
                building = by_id[building_id]
                min_x, min_y, max_x, max_y = map(float, building["building_bbox_xy"])
                if not (min_x <= xyz[0] <= max_x and min_y <= xyz[1] <= max_y):
                    continue
                entry = counts[building_id]
                entry["xy"] += 1
                min_z, max_z = map(float, building["z_range_ellipsoidal_m"])
                if not (min_z <= xyz[2] <= max_z):
                    continue
                entry["xyz"] += 1
                for index in range(8, len(fields), 2):
                    image_id = int(fields[index])
                    if image_id in exact_ids:
                        entry["camera_tracks"][image_id] += 1
    if scanned != int(cfg["points3d_count"]):
        raise RuntimeError(f"points3D count drifted: {scanned}")

    output_rows = []
    status_counts: Counter[str] = Counter()
    for row in candidates:
        building_id = row["stable_id"]
        value = counts[building_id]
        cameras_ge3 = sum(count >= 3 for count in value["camera_tracks"].values())
        max_track = max(value["camera_tracks"].values(), default=0)
        if value["xyz"] == 0:
            status = "NO_SPARSE_BUILDING_PRISM_SEED"
        elif value["xyz"] < int(cfg["weak_sparse_point_threshold"]):
            status = "SPARSE_SEED_PRESENT_BUT_LT3_POINTS"
        elif cameras_ge3 < int(cfg["minimum_cameras_with_three_tracks_for_strong_proxy"]):
            status = "SPARSE_SEED_PRESENT_BUT_WEAK_MULTI_VIEW_TRACK_PROXY"
        else:
            status = "SPARSE_SEED_PRESENT_STRONG_MULTI_VIEW_TRACK_PROXY"
        status_counts[status] += 1
        output_rows.append({
            "population_index": row["population_index"],
            "stable_id": building_id,
            "dense_mvs_all_point_coverage_0p5m": row["all_point_coverage_0p5m"],
            "dense_mvs_primary_improvement_track": row["primary_improvement_track"],
            "sparse_bbox_xy_point_count_all_z": value["xy"],
            "sparse_building_prism_point_count": value["xyz"],
            "sparse_exact937_camera_count": len(value["camera_tracks"]),
            "sparse_exact937_camera_count_with_ge3_tracks": cameras_ge3,
            "sparse_max_track_points_in_one_camera": max_track,
            "sparse_seed_status": status,
            "support_interpretation": "BUILDING_BBOX_XY_AND_EVALUATION_Z_RANGE_DIAGNOSTIC_ONLY",
            "scientific_verdict": "",
        })
    output_rows.sort(key=lambda row: int(row["population_index"]))
    partial = TASK.with_name(TASK.name + ".partial")
    partial.mkdir(parents=True)
    csv_path = partial / "sparse_seed_dense_support_candidates_73.csv"
    with csv_path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(output_rows[0]))
        writer.writeheader()
        writer.writerows(output_rows)
    summary = {
        "schema": "jointbuildgs.p2.sparse_seed_dense_support_census_199.summary.v1",
        "task_id": cfg["task_id"],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "population_count": len(census),
        "mvs_raw_geometry_support_candidate_count": len(candidates),
        "sparse_seed_status_counts": dict(status_counts),
        "sparse_seed_present_count": sum(value["xyz"] > 0 for value in counts.values()),
        "definition": {
            "dense_support_low": "primary_improvement_track == MVS_RAW_GEOMETRY_SUPPORT from the frozen 199-building technical census",
            "sparse_seed_present": "at least one frozen common-base COLMAP point inside the building XY bounding box and evaluation Z range",
            "strong_multi_view_track_proxy": "at least three prism points and at least two exact-937 cameras each observing at least three of those points",
        },
        "limitations": [
            "Sparse-seed presence is not proof that dense reconstruction or GS initialization will succeed.",
            "The evaluation Z range is used only for this diagnostic census and is not an honest-arm training input.",
            "No scientific or PASS_usable verdict is assigned.",
        ],
        "scientific_verdict": None,
    }
    write_json(partial / "summary.json", summary)
    receipt = {
        "schema": "jointbuildgs.p2.sparse_seed_dense_support_census_199.receipt.v1",
        "task_id": cfg["task_id"],
        "config": {"path": str(CONFIG), "sha256": sha256(CONFIG)},
        "script": {"path": str(SOURCE), "sha256": sha256(SOURCE)},
        "bindings": bindings,
        "outputs": {
            "csv": {"path": csv_path.name, "bytes": csv_path.stat().st_size, "sha256": sha256(csv_path)},
            "summary": {"path": "summary.json", "bytes": (partial / "summary.json").stat().st_size, "sha256": sha256(partial / "summary.json")},
        },
        "scientific_verdict": None,
    }
    write_json(partial / "receipt.json", receipt)
    os.replace(partial, TASK)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
