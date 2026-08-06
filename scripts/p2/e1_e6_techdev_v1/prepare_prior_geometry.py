from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import laspy
import numpy as np
import open3d as o3d
from shapely import contains_xy
from shapely.geometry import shape


AOI = np.asarray([690791.74, 5335864.05, 691154.65, 5336353.85])
WORLD_SHIFT = np.asarray([690953.0, 5336071.0, 604.0])
ALS_Z_SHIFT = 45.7


def sha256(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def assign_buildings(
    points_world: np.ndarray, footprints: list[tuple[str, object]]
) -> np.ndarray:
    assignment = np.full(len(points_world), -1, dtype=np.int32)
    x = points_world[:, 0]
    y = points_world[:, 1]
    for index, (_stable_id, geometry) in enumerate(footprints):
        minx, miny, maxx, maxy = geometry.bounds
        candidate = np.flatnonzero(
            (assignment < 0)
            & (x >= minx)
            & (x <= maxx)
            & (y >= miny)
            & (y <= maxy)
        )
        if len(candidate):
            inside = contains_xy(geometry, x[candidate], y[candidate])
            assignment[candidate[inside]] = index
    return assignment


def load_scene_als(paths: list[Path]) -> tuple[np.ndarray, np.ndarray, list[dict]]:
    xyz_parts: list[np.ndarray] = []
    class_parts: list[np.ndarray] = []
    receipts: list[dict] = []
    for path in paths:
        selected = 0
        source = 0
        with laspy.open(path) as reader:
            for chunk in reader.chunk_iterator(2_000_000):
                source += len(chunk)
                x = np.asarray(chunk.x)
                y = np.asarray(chunk.y)
                z = np.asarray(chunk.z) + ALS_Z_SHIFT
                classification = np.asarray(chunk.classification, dtype=np.uint8)
                keep = (
                    ((classification == 2) | (classification == 6))
                    & (x >= AOI[0] - 20.0)
                    & (x <= AOI[2] + 20.0)
                    & (y >= AOI[1] - 20.0)
                    & (y <= AOI[3] + 20.0)
                )
                if keep.any():
                    xyz_parts.append(np.column_stack((x[keep], y[keep], z[keep])))
                    class_parts.append(classification[keep])
                    selected += int(keep.sum())
        receipts.append(
            {
                "path": str(path),
                "sha256": sha256(path),
                "source_point_count": source,
                "class_2_or_6_scene_point_count": selected,
            }
        )
    if not xyz_parts:
        raise RuntimeError("Existing ALS has no class 2/6 support in the scene")
    return np.concatenate(xyz_parts), np.concatenate(class_parts), receipts


def apply_synthetic(
    xyz_world: np.ndarray,
    classification: np.ndarray,
    footprints: list[tuple[str, object]],
    changes: dict,
) -> tuple[np.ndarray, np.ndarray, list[dict]]:
    assignment = assign_buildings(xyz_world, footprints)
    index_by_id = {stable_id: index for index, (stable_id, _geom) in enumerate(footprints)}
    original_xyz = xyz_world.copy()
    original_class = classification.copy()
    original_assignment = assignment.copy()
    keep = np.ones(len(xyz_world), dtype=bool)
    inserted_xyz: list[np.ndarray] = []
    inserted_class: list[np.ndarray] = []
    receipts: list[dict] = []
    for change in changes["changes"]:
        stable_id = str(change["stable_id"])
        target_index = index_by_id[stable_id]
        target = assignment == target_index
        operation = change["operation"]
        if operation == "REMOVE_PRIOR_GEOMETRY":
            affected = target & (classification == 6)
            keep[affected] = False
            receipts.append({**change, "affected_point_count": int(affected.sum())})
        elif operation == "SCALE_PRIOR_HEIGHT":
            affected = target & (classification == 6)
            if affected.any():
                base = float(np.quantile(xyz_world[affected, 2], 0.02))
                xyz_world[affected, 2] = base + float(change["scale"]) * (
                    xyz_world[affected, 2] - base
                )
            receipts.append({**change, "affected_point_count": int(affected.sum())})
        elif operation == "INSERT_DONOR_PRIOR_GEOMETRY":
            donor_id = str(change["donor_stable_id"])
            donor_index = index_by_id[donor_id]
            donor = (original_assignment == donor_index) & (original_class == 6)
            source = original_xyz[donor].copy()
            if len(source):
                donor_centre = np.asarray(footprints[donor_index][1].centroid.coords[0])
                target_centre = np.asarray(footprints[target_index][1].centroid.coords[0])
                source[:, :2] += target_centre - donor_centre
                inserted_xyz.append(source)
                inserted_class.append(original_class[donor].copy())
            receipts.append({**change, "inserted_point_count": int(len(source))})
        else:
            raise RuntimeError(f"unknown synthetic operation: {operation}")
    output_xyz = xyz_world[keep]
    output_class = classification[keep]
    if inserted_xyz:
        output_xyz = np.concatenate([output_xyz, *inserted_xyz])
        output_class = np.concatenate([output_class, *inserted_class])
    return output_xyz, output_class, receipts


def voxel_cloud(points_local: np.ndarray, voxel: float) -> o3d.geometry.PointCloud:
    cloud = o3d.geometry.PointCloud(o3d.utility.Vector3dVector(points_local))
    return cloud.voxel_down_sample(voxel)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--prep-root", type=Path, required=True)
    args = parser.parse_args()
    artifacts = args.artifact_root.resolve()
    prep = args.prep_root.resolve()
    prep.mkdir(parents=True, exist_ok=True)
    output = prep / "existing_als_synthetic_local_voxel030.ply"
    receipt_path = prep / "existing_als_synthetic_receipt.json"
    if output.is_file() and receipt_path.is_file():
        return 0
    footprint_path = artifacts / (
        "phase-payloads/p2/c1_c2_shared_footprint_199_v3/"
        "P2-C1-C2-SHARED-FOOTPRINT-199-ORIGINAL-GLOBAL-v3-replay-20260806a/"
        "freeze/shared_footprints_199.geojson"
    )
    footprint_data = json.loads(footprint_path.read_text(encoding="utf-8"))
    footprints = [
        (str(feature["properties"]["stable_id"]), shape(feature["geometry"]))
        for feature in footprint_data["features"]
    ]
    changes = json.loads((prep / "synthetic_changes.json").read_text(encoding="utf-8"))
    als_paths = [
        artifacts / f"phase-payloads/p0-audit/data/raw/als/{tile}.laz"
        for tile in ("690_5335", "690_5336", "691_5335", "691_5336")
    ]
    xyz_world, classification, sources = load_scene_als(als_paths)
    raw_selected_count = len(xyz_world)
    xyz_world, classification, change_receipts = apply_synthetic(
        xyz_world, classification, footprints, changes
    )
    local = xyz_world - WORLD_SHIFT
    cloud = voxel_cloud(local, 0.30)
    if not o3d.io.write_point_cloud(str(output), cloud, write_ascii=False):
        raise RuntimeError(f"failed to write {output}")
    receipt = {
        "schema": "jointbuildgs.p2.e1_e6.synthetic_existing_als.v1",
        "crs": "EPSG:25832",
        "world_to_local_shift": (-WORLD_SHIFT).tolist(),
        "vertical_shift_m": ALS_Z_SHIFT,
        "classes": [2, 6],
        "raw_selected_point_count": raw_selected_count,
        "synthetic_point_count_before_voxel": int(len(local)),
        "voxel_size_m": 0.30,
        "voxel_point_count": int(len(cloud.points)),
        "sources": sources,
        "changes": change_receipts,
        "output": {"path": str(output), "sha256": sha256(output)},
        "raw_inputs_modified": False,
        "scientific_verdict": None,
    }
    receipt_path.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
