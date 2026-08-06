from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

import numpy as np
import open3d as o3d
from shapely import contains_xy
from shapely.geometry import shape

from src.stage2.dataloader import ColmapDataset
from src.stage2.pilot_plane_mask_producer import SURFACE_CLASS, load_lod2_citygml_scene


TASK_REL = Path("phase-payloads/p2/e1_e6_techdev_v1/P2-E1-E6-PRIOR-FUSION-TECHDEV-v1")


def sha256(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def sample_triangles(
    triangles: np.ndarray, classes: np.ndarray, area_per_point: float = 0.5
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    edge1 = triangles[:, 1] - triangles[:, 0]
    edge2 = triangles[:, 2] - triangles[:, 0]
    cross = np.cross(edge1, edge2)
    double_area = np.linalg.norm(cross, axis=1)
    normals = cross / np.maximum(double_area[:, None], 1.0e-12)
    points: list[np.ndarray] = []
    point_normals: list[np.ndarray] = []
    kinds: list[np.ndarray] = []
    phi = (math.sqrt(5.0) - 1.0) / 2.0
    for index, triangle in enumerate(triangles):
        class_id = int(classes[index])
        if class_id not in (SURFACE_CLASS["WallSurface"], SURFACE_CLASS["RoofSurface"]):
            continue
        count = max(1, int(math.ceil(0.5 * double_area[index] / area_per_point)))
        sequence = np.arange(count, dtype=np.float64) + 0.5
        u = np.mod(sequence * phi, 1.0)
        v = np.mod(sequence * phi * phi, 1.0)
        reflect = u + v > 1.0
        u[reflect] = 1.0 - u[reflect]
        v[reflect] = 1.0 - v[reflect]
        sampled = triangle[0] + u[:, None] * (triangle[1] - triangle[0]) + v[:, None] * (triangle[2] - triangle[0])
        points.append(sampled)
        point_normals.append(np.broadcast_to(normals[index], sampled.shape).copy())
        # E6 cache convention: wall=1, roof=2.
        kind = 1 if class_id == SURFACE_CLASS["WallSurface"] else 2
        kinds.append(np.full(count, kind, dtype=np.uint8))
    return np.concatenate(points), np.concatenate(point_normals), np.concatenate(kinds)


def assign_buildings(points_world_xy: np.ndarray, footprints: list[tuple[str, object]]) -> np.ndarray:
    assignment = np.full(len(points_world_xy), -1, dtype=np.int32)
    x, y = points_world_xy.T
    for index, (_stable_id, geometry) in enumerate(footprints):
        expanded = geometry.buffer(0.10)
        minx, miny, maxx, maxy = expanded.bounds
        candidate = np.flatnonzero(
            (assignment < 0) & (x >= minx) & (x <= maxx) & (y >= miny) & (y <= maxy)
        )
        if len(candidate):
            assignment[candidate[contains_xy(expanded, x[candidate], y[candidate])]] = index
    return assignment


def apply_synthetic(
    points: np.ndarray,
    normals: np.ndarray,
    kinds: np.ndarray,
    assignment: np.ndarray,
    footprints: list[tuple[str, object]],
    changes: dict,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, list[dict]]:
    index_by_id = {stable_id: index for index, (stable_id, _geom) in enumerate(footprints)}
    original = points.copy(), normals.copy(), kinds.copy(), assignment.copy()
    keep = np.ones(len(points), dtype=bool)
    additions: list[tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]] = []
    receipts: list[dict] = []
    for change in changes["changes"]:
        target_index = index_by_id[str(change["stable_id"])]
        selected = assignment == target_index
        operation = change["operation"]
        if operation == "REMOVE_PRIOR_GEOMETRY":
            keep[selected] = False
            receipts.append({**change, "affected_sample_count": int(selected.sum())})
        elif operation == "SCALE_PRIOR_HEIGHT":
            scale = float(change["scale"])
            if selected.any():
                base = float(points[selected, 2].min())
                points[selected, 2] = base + scale * (points[selected, 2] - base)
                normals[selected, 2] /= scale
                normals[selected] /= np.linalg.norm(normals[selected], axis=1, keepdims=True) + 1.0e-12
            receipts.append({**change, "affected_sample_count": int(selected.sum())})
        elif operation == "INSERT_DONOR_PRIOR_GEOMETRY":
            donor_index = index_by_id[str(change["donor_stable_id"])]
            donor = original[3] == donor_index
            copied = original[0][donor].copy()
            donor_centre = np.asarray(footprints[donor_index][1].centroid.coords[0])
            target_centre = np.asarray(footprints[target_index][1].centroid.coords[0])
            copied[:, :2] += target_centre - donor_centre
            additions.append(
                (
                    copied,
                    original[1][donor].copy(),
                    original[2][donor].copy(),
                    np.full(len(copied), target_index, dtype=np.int32),
                )
            )
            receipts.append({**change, "inserted_sample_count": int(len(copied))})
        else:
            raise RuntimeError(f"unknown synthetic operation: {operation}")
    values = [points[keep]], [normals[keep]], [kinds[keep]], [assignment[keep]]
    for addition in additions:
        for target, value in zip(values, addition):
            target.append(value)
    return (
        np.concatenate(values[0]),
        np.concatenate(values[1]),
        np.concatenate(values[2]),
        np.concatenate(values[3]),
        receipts,
    )


def project_view(
    points: np.ndarray,
    normals: np.ndarray,
    kinds: np.ndarray,
    weights: np.ndarray,
    sample: dict,
) -> dict[str, np.ndarray]:
    k = sample["K"].numpy().astype(np.float64)
    w2c = sample["w2c"].numpy().astype(np.float64)
    camera = points @ w2c[:3, :3].T + w2c[:3, 3]
    normal_camera = normals @ w2c[:3, :3].T
    front = camera[:, 2] > 0.1
    uvw = camera @ k.T
    uv = np.zeros((len(points), 2), dtype=np.float64)
    uv[front] = uvw[front, :2] / uvw[front, 2:3]
    height, width = int(sample["height"]), int(sample["width"])
    inside = front & (uv[:, 0] >= 0) & (uv[:, 0] < width) & (uv[:, 1] >= 0) & (uv[:, 1] < height)
    selected = np.flatnonzero(inside)
    if not len(selected):
        empty = np.empty(0, np.float32)
        return {
            "pixel_y": np.empty(0, np.int32), "pixel_x": np.empty(0, np.int32),
            "plane_point_camera": np.empty((0, 3), np.float32),
            "plane_normal_camera": np.empty((0, 3), np.float32),
            "plane_kind": np.empty(0, np.uint8), "building_weight": empty,
        }
    x = np.rint(uv[selected, 0]).astype(np.int32).clip(0, width - 1)
    y = np.rint(uv[selected, 1]).astype(np.int32).clip(0, height - 1)
    key = y.astype(np.int64) * width + x
    order = np.lexsort((camera[selected, 2], key))
    first = np.r_[True, key[order][1:] != key[order][:-1]]
    chosen = selected[order[first]]
    return {
        "pixel_y": np.rint(uv[chosen, 1]).astype(np.int32).clip(0, height - 1),
        "pixel_x": np.rint(uv[chosen, 0]).astype(np.int32).clip(0, width - 1),
        "plane_point_camera": camera[chosen].astype(np.float32),
        "plane_normal_camera": normal_camera[chosen].astype(np.float32),
        "plane_kind": kinds[chosen],
        "building_weight": weights[chosen].astype(np.float32),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository-root", type=Path, required=True)
    parser.add_argument("--artifact-root", type=Path, required=True)
    args = parser.parse_args()
    repo = args.repository_root.resolve()
    artifacts = args.artifact_root.resolve()
    task = artifacts / TASK_REL
    prep = task / "prep"
    views_dir = prep / "lod_prior/views"
    sample_path = prep / "lod_surface_samples_synthetic_local.ply"
    receipt_path = prep / "lod_prior/receipt.json"
    if sample_path.is_file() and receipt_path.is_file() and len(list(views_dir.glob("*.npz"))) == 937:
        return 0
    footprints_path = artifacts / (
        "phase-payloads/p2/c1_c2_shared_footprint_199_v3/"
        "P2-C1-C2-SHARED-FOOTPRINT-199-ORIGINAL-GLOBAL-v3-replay-20260806a/"
        "freeze/shared_footprints_199.geojson"
    )
    data = json.loads(footprints_path.read_text(encoding="utf-8"))
    footprints = [(str(row["properties"]["stable_id"]), shape(row["geometry"])) for row in data["features"]]
    ids = [stable_id for stable_id, _geometry in footprints]
    gml = [artifacts / f"phase-payloads/p0-audit/data/raw/lod2/{tile}.gml" for tile in ("690_5334", "690_5336")]
    scene = load_lod2_citygml_scene(gml, ids, include_unselected=False)
    points, normals, kinds = sample_triangles(scene.triangles_local, scene.triangle_class)
    world_xy = points[:, :2] + np.asarray([690953.0, 5336071.0])
    assignment = assign_buildings(world_xy, footprints)
    changes = json.loads((prep / "synthetic_changes.json").read_text(encoding="utf-8"))
    points, normals, kinds, assignment, change_receipts = apply_synthetic(
        points, normals, kinds, assignment, footprints, changes
    )
    wb = json.loads((prep / "w_b.json").read_text(encoding="utf-8"))["buildings"]
    weights = np.ones(len(points), dtype=np.float32)
    for index, (stable_id, _geometry) in enumerate(footprints):
        weights[assignment == index] = float(wb[stable_id]["w_b"])
    cloud = o3d.geometry.PointCloud(o3d.utility.Vector3dVector(points))
    if not o3d.io.write_point_cloud(str(sample_path), cloud, write_ascii=False):
        raise RuntimeError(f"failed to write {sample_path}")
    roles = json.loads((prep / "view_roles.json").read_text(encoding="utf-8"))
    visible = roles["train_views"] + roles["eval_views"]
    dataset = ColmapDataset(
        artifacts / "phase-payloads/p0-audit/data/work/mvs/colmap_dense",
        downscale=1.0,
        load_depth=False,
        load_normal=False,
        load_semantic=False,
        visible_views=visible,
    )
    views_dir.mkdir(parents=True, exist_ok=True)
    support = 0
    for index, frame in enumerate(dataset.frames):
        output = views_dir / f"{Path(frame.name).stem}.npz"
        if not output.is_file():
            sample = dataset[index]
            projected = project_view(points, normals, kinds, weights, sample)
            np.savez_compressed(
                output,
                height=np.int32(sample["height"]),
                width=np.int32(sample["width"]),
                **projected,
            )
        with np.load(output, allow_pickle=False) as payload:
            support += len(payload["pixel_x"])
        if (index + 1) % 50 == 0:
            print(f"[E6 LoD cache] {index + 1}/937", flush=True)
    receipt = {
        "schema": "jointbuildgs.p2.e1_e6.lod_prior.v1",
        "source_gml": [{"path": str(path), "sha256": sha256(path)} for path in gml],
        "surface_area_per_sample_m2": 0.5,
        "sample_count": int(len(points)),
        "wall_sample_count": int((kinds == 1).sum()),
        "roof_sample_count": int((kinds == 2).sum()),
        "unassigned_sample_count": int((assignment < 0).sum()),
        "synthetic_changes": change_receipts,
        "view_count": len(dataset),
        "total_projected_support": support,
        "sample_output": {"path": str(sample_path), "sha256": sha256(sample_path)},
        "reference_role": "REFERENCE_DERIVED_DIAGNOSTIC_ONLY",
        "scientific_verdict": None,
    }
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
