from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import open3d as o3d
from scipy.spatial import cKDTree
from shapely import contains_xy
from shapely.geometry import shape

from src.stage2.dataloader import ColmapDataset


TASK_REL = Path("phase-payloads/p2/e1_e6_techdev_v1/P2-E1-E6-PRIOR-FUSION-TECHDEV-v1")
WORLD_SHIFT = np.asarray([690953.0, 5336071.0, 604.0])


def sha256(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def normals_and_curvature(points: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    tree = cKDTree(points)
    normals = np.empty_like(points, dtype=np.float32)
    curvature = np.empty(len(points), dtype=np.float32)
    batch_size = 50_000
    for start in range(0, len(points), batch_size):
        stop = min(start + batch_size, len(points))
        _distance, neighbors = tree.query(points[start:stop], k=min(20, len(points)), workers=-1)
        local = points[neighbors]
        delta = local - local.mean(axis=1, keepdims=True)
        covariance = np.einsum("bni,bnj->bij", delta, delta) / max(1, local.shape[1] - 1)
        eigenvalues, eigenvectors = np.linalg.eigh(covariance)
        normals[start:stop] = eigenvectors[:, :, 0].astype(np.float32)
        curvature[start:stop] = (
            eigenvalues[:, 0] / np.maximum(eigenvalues.sum(axis=1), 1.0e-12)
        ).astype(np.float32)
        print(f"[ALS PCA] {stop}/{len(points)}", flush=True)
    return normals, curvature


def building_weights(points: np.ndarray, footprint_data: dict, wb: dict) -> np.ndarray:
    world = points + WORLD_SHIFT
    output = np.ones(len(points), dtype=np.float32)
    assigned = np.zeros(len(points), dtype=bool)
    for feature in footprint_data["features"]:
        geometry = shape(feature["geometry"])
        stable_id = str(feature["properties"]["stable_id"])
        minx, miny, maxx, maxy = geometry.bounds
        candidate = np.flatnonzero(
            (~assigned)
            & (world[:, 0] >= minx)
            & (world[:, 0] <= maxx)
            & (world[:, 1] >= miny)
            & (world[:, 1] <= maxy)
        )
        if len(candidate):
            inside = contains_xy(geometry, world[candidate, 0], world[candidate, 1])
            chosen = candidate[inside]
            output[chosen] = float(wb[stable_id]["w_b"])
            assigned[chosen] = True
    return output


def project_view(
    points: np.ndarray,
    normals: np.ndarray,
    planar: np.ndarray,
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
        return {
            "pixel_y": np.empty(0, np.int32), "pixel_x": np.empty(0, np.int32),
            "depth": np.empty(0, np.float32), "normal": np.empty((0, 3), np.float32),
            "confidence": np.empty(0, np.float32), "building_weight": np.empty(0, np.float32),
            "normal_valid": np.empty(0, np.bool_),
        }
    x = np.rint(uv[selected, 0]).astype(np.int32).clip(0, width - 1)
    y = np.rint(uv[selected, 1]).astype(np.int32).clip(0, height - 1)
    key = y.astype(np.int64) * width + x
    order = np.lexsort((camera[selected, 2], key))
    first = np.r_[True, key[order][1:] != key[order][:-1]]
    chosen = selected[order[first]]
    chosen_normal_camera = normal_camera[chosen].copy()
    # PCA normal signs are arbitrary.  Orient every projected prior normal toward
    # the camera so the registered signed 1-dot loss is well-defined.
    flip = np.einsum("ij,ij->i", chosen_normal_camera, camera[chosen]) > 0
    chosen_normal_camera[flip] *= -1.0
    return {
        "pixel_y": np.rint(uv[chosen, 1]).astype(np.int32).clip(0, height - 1),
        "pixel_x": np.rint(uv[chosen, 0]).astype(np.int32).clip(0, width - 1),
        "depth": camera[chosen, 2].astype(np.float32),
        "normal": chosen_normal_camera.astype(np.float32),
        "confidence": np.ones(len(chosen), dtype=np.float32),
        "building_weight": weights[chosen].astype(np.float32),
        "normal_valid": planar[chosen],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact-root", type=Path, required=True)
    args = parser.parse_args()
    artifacts = args.artifact_root.resolve()
    task = artifacts / TASK_REL
    prep = task / "prep"
    source = prep / "existing_als_synthetic_local_voxel030.ply"
    prior_root = prep / "als_prior"
    views = prior_root / "views"
    receipt_path = prior_root / "receipt.json"
    if receipt_path.is_file() and len(list(views.glob("*.npz"))) == 937:
        return 0
    cloud = o3d.io.read_point_cloud(str(source)).voxel_down_sample(0.75)
    points = np.asarray(cloud.points, dtype=np.float64)
    normals, curvature = normals_and_curvature(points)
    planar = curvature < 0.02
    footprint_path = artifacts / (
        "phase-payloads/p2/c1_c2_shared_footprint_199_v3/"
        "P2-C1-C2-SHARED-FOOTPRINT-199-ORIGINAL-GLOBAL-v3-replay-20260806a/"
        "freeze/shared_footprints_199.geojson"
    )
    footprint_data = json.loads(footprint_path.read_text(encoding="utf-8"))
    wb = json.loads((prep / "w_b.json").read_text(encoding="utf-8"))["buildings"]
    weights = building_weights(points, footprint_data, wb)
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
    views.mkdir(parents=True, exist_ok=True)
    support = 0
    normal_support = 0
    for index, frame in enumerate(dataset.frames):
        output = views / f"{Path(frame.name).stem}.npz"
        if not output.is_file():
            sample = dataset[index]
            projected = project_view(points, normals, planar, weights, sample)
            np.savez_compressed(
                output,
                height=np.int32(sample["height"]),
                width=np.int32(sample["width"]),
                **projected,
            )
        with np.load(output, allow_pickle=False) as payload:
            support += len(payload["pixel_x"])
            normal_support += int(payload["normal_valid"].sum())
        if (index + 1) % 50 == 0:
            print(f"[E4/E5 ALS cache] {index + 1}/937", flush=True)
    receipt = {
        "schema": "jointbuildgs.p2.e1_e6.als_prior.v1",
        "source": {"path": str(source), "sha256": sha256(source)},
        "prior_voxel_size_m": 0.75,
        "point_count": int(len(points)),
        "normal_method": "PCA_K20",
        "normal_frame": "CAMERA",
        "normal_orientation": "TOWARD_CAMERA",
        "normal_curvature_threshold": 0.02,
        "planar_point_count": int(planar.sum()),
        "depth_base_confidence": "ONE_ON_ALL_PROJECTED_CLASS_2_OR_6_POINTS",
        "view_count": len(dataset),
        "total_depth_support": support,
        "total_normal_support": normal_support,
        "e4_e5_cache_is_identical": True,
        "scientific_verdict": None,
    }
    receipt_path.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
