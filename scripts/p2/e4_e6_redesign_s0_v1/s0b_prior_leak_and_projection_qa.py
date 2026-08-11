#!/usr/bin/env python3
"""S0-b: full-view legacy ALS-prior leak census + occlusion-aware projection QA.

Part 1 measures |legacy prior depth - COLMAP geometric depth| over all 937
techdev prior views (the maps that actually supervised legacy E4/E5).
Part 2 prototypes the redesign projection (class-2/6 DSM TIN raycast) on a
fixed 15-view sample and evaluates the section-4.4 QA targets against the
point-projection baseline. Read-only inputs; outputs only under the S0 root.
"""
from __future__ import annotations

import csv
import glob
import hashlib
import json
import random
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import laspy
import numpy as np
import open3d as o3d
import yaml

from scripts.p2.c4_existing_als_v1.prepare_prior import ALS_DATUM_SHIFT_M, ALS_HASHES, WORLD_SHIFT
from src.stage2.colmap_io import read_array, read_cameras_bin, read_images_bin, read_points3d_bin

REPO = Path(__file__).resolve().parents[3]
COMMON = REPO / "configs/p2/e4_e6_redesign_s0_v1/s0_v1.yaml"
ARTIFACTS = Path("/artifacts/JointBuildGS")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def view_leak_stats(npz_path: Path, depth_dir: Path) -> dict[str, Any] | None:
    stem = npz_path.stem
    depth_path = depth_dir / f"{stem}.JPG.geometric.bin"
    if not depth_path.is_file():
        return None
    mvs = read_array(depth_path)
    with np.load(npz_path, allow_pickle=False) as payload:
        height, width = int(payload["height"]), int(payload["width"])
        y = payload["pixel_y"].astype(np.int64)
        x = payload["pixel_x"].astype(np.int64)
        prior = payload["depth"].astype(np.float64)
    if mvs.shape != (height, width):
        yy = np.clip((y * (mvs.shape[0] / height)).astype(np.int64), 0, mvs.shape[0] - 1)
        xx = np.clip((x * (mvs.shape[1] / width)).astype(np.int64), 0, mvs.shape[1] - 1)
    else:
        yy, xx = y, x
    reference = mvs[yy, xx]
    supported = reference > 0
    residual = np.abs(prior[supported] - reference[supported])
    return {
        "view": stem,
        "prior_pixel_count": int(len(prior)),
        "mvs_supported_count": int(supported.sum()),
        "unsupported_fraction": float((~supported).mean()) if len(prior) else 0.0,
        "median_abs_m": float(np.median(residual)) if len(residual) else None,
        "p95_abs_m": float(np.quantile(residual, 0.95)) if len(residual) else None,
        "gt2m_fraction": float((residual > 2.0).mean()) if len(residual) else None,
        "gt5m_fraction": float((residual > 5.0).mean()) if len(residual) else None,
        "gt2m_count": int((residual > 2.0).sum()),
        "residual_sum_count": int(len(residual)),
    }


def load_scene_als(als_root: Path, low: np.ndarray, high: np.ndarray, classes: set[int]) -> np.ndarray:
    parts: list[np.ndarray] = []
    for name, expected in ALS_HASHES.items():
        path = als_root / name
        if sha256(path) != expected:
            raise RuntimeError(f"raw ALS hash drift: {name}")
        with laspy.open(path) as reader:
            for chunk in reader.chunk_iterator(2_000_000):
                x = np.asarray(chunk.x)
                y = np.asarray(chunk.y)
                keep = (
                    np.isin(np.asarray(chunk.classification), list(classes))
                    & (x >= low[0]) & (x <= high[0])
                    & (y >= low[1]) & (y <= high[1])
                )
                if bool(keep.any()):
                    z = np.asarray(chunk.z)[keep] + ALS_DATUM_SHIFT_M
                    parts.append(np.column_stack((x[keep], y[keep], z)) - WORLD_SHIFT)
    if not parts:
        raise RuntimeError("no class-2/6 ALS points inside the scene bbox")
    return np.concatenate(parts)


def dsm_tin(points_local: np.ndarray, cell_m: float) -> o3d.t.geometry.RaycastingScene:
    xy_min = points_local[:, :2].min(axis=0)
    cols = np.floor((points_local[:, 0] - xy_min[0]) / cell_m).astype(np.int64)
    rows = np.floor((points_local[:, 1] - xy_min[1]) / cell_m).astype(np.int64)
    n_cols = int(cols.max()) + 1
    n_rows = int(rows.max()) + 1
    top = np.full(n_rows * n_cols, -np.inf, dtype=np.float64)
    np.maximum.at(top, rows * n_cols + cols, points_local[:, 2])
    top = top.reshape(n_rows, n_cols)
    valid = np.isfinite(top)
    index = np.full(top.shape, -1, dtype=np.int64)
    index[valid] = np.arange(int(valid.sum()))
    grid_rows, grid_cols = np.nonzero(valid)
    vertices = np.column_stack((
        xy_min[0] + (grid_cols + 0.5) * cell_m,
        xy_min[1] + (grid_rows + 0.5) * cell_m,
        top[valid],
    ))
    a = index[:-1, :-1]
    b = index[:-1, 1:]
    c = index[1:, :-1]
    d = index[1:, 1:]
    quad = (a >= 0) & (b >= 0) & (c >= 0) & (d >= 0)
    triangles = np.concatenate([
        np.column_stack((a[quad], b[quad], c[quad])),
        np.column_stack((b[quad], d[quad], c[quad])),
    ])
    legacy = o3d.geometry.TriangleMesh(
        o3d.utility.Vector3dVector(vertices),
        o3d.utility.Vector3iVector(triangles.astype(np.int32)),
    )
    scene = o3d.t.geometry.RaycastingScene()
    scene.add_triangles(o3d.t.geometry.TriangleMesh.from_legacy(legacy))
    return scene, int(len(vertices)), int(len(triangles))


def main() -> None:
    started = datetime.now(timezone.utc).isoformat()
    common = yaml.safe_load(COMMON.read_text(encoding="utf-8"))
    out_root = Path(common["output_root"]) / "s0b"
    out_root.mkdir(parents=True, exist_ok=True)
    proto = common["projection_prototype"]

    views_dir = ARTIFACTS / common["techdev_prior_views"]
    depth_dir = ARTIFACTS / common["colmap_depth_maps"]
    npz_paths = sorted(views_dir.glob("*.npz"))
    if len(npz_paths) != 937:
        raise RuntimeError(f"expected 937 legacy prior views, got {len(npz_paths)}")

    per_view = []
    for index, path in enumerate(npz_paths):
        stats = view_leak_stats(path, depth_dir)
        if stats is not None:
            per_view.append(stats)
        if (index + 1) % 200 == 0:
            print(f"[s0b part1] {index + 1}/937", flush=True)
    total_res = sum(row["residual_sum_count"] for row in per_view)
    total_gt2 = sum(row["gt2m_count"] for row in per_view)
    medians = [row["median_abs_m"] for row in per_view if row["median_abs_m"] is not None]
    part1 = {
        "view_count_with_mvs_depth": len(per_view),
        "total_prior_pixels": sum(row["prior_pixel_count"] for row in per_view),
        "total_mvs_supported_pixels": total_res,
        "gt2m_fraction_overall": total_gt2 / total_res if total_res else None,
        "per_view_median_abs_m_median": float(np.median(medians)) if medians else None,
        "per_view_gt2m_fraction_median": float(np.median([r["gt2m_fraction"] for r in per_view if r["gt2m_fraction"] is not None])),
    }
    with (out_root / "legacy_leak_per_view_v1.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(per_view[0].keys()))
        writer.writeheader()
        writer.writerows(per_view)

    random.seed(int(proto["sample_seed"]))
    sample = random.sample(npz_paths, int(proto["sample_view_count"]))
    sample_stems = {path.stem for path in sample}
    baseline_rows = [row for row in per_view if row["view"] in sample_stems]
    baseline_res = sum(row["residual_sum_count"] for row in baseline_rows)
    baseline_gt2 = sum(row["gt2m_count"] for row in baseline_rows)
    baseline_gt2_fraction = baseline_gt2 / baseline_res if baseline_res else None

    sparse_dir = ARTIFACTS / common["colmap_sparse"]
    if (sparse_dir / "0").is_dir():
        sparse_dir = sparse_dir / "0"
    points = read_points3d_bin(sparse_dir / "points3D.bin")[:, :3]
    low = np.quantile(points[:, :2], 0.001, axis=0) + WORLD_SHIFT[:2] - 10.0
    high = np.quantile(points[:, :2], 0.999, axis=0) + WORLD_SHIFT[:2] + 10.0
    als_local = load_scene_als(ARTIFACTS / common["als_raw_root"], low, high, set(proto["classes"]))
    scene, vertex_count, triangle_count = dsm_tin(als_local, float(proto["dsm_cell_m"]))

    cameras = read_cameras_bin(sparse_dir / "cameras.bin")
    images = {image.name: image for image in read_images_bin(sparse_dir / "images.bin").values()}

    stride = int(proto["ray_stride_px"])
    proto_rows = []
    for npz_path in sorted(sample):
        stem = npz_path.stem
        image = images.get(f"{stem}.JPG")
        if image is None:
            raise RuntimeError(f"sample view missing in sparse model: {stem}")
        camera = cameras[image.camera_id]
        k_inv = np.linalg.inv(camera.K())
        w2c = image.world_to_camera()
        rotation = w2c[:3, :3]
        center = -rotation.T @ w2c[:3, 3]
        mvs = read_array(depth_dir / f"{stem}.JPG.geometric.bin")
        height, width = int(camera.height), int(camera.width)
        us = np.arange(0, width, stride, dtype=np.float64) + 0.5
        vs = np.arange(0, height, stride, dtype=np.float64) + 0.5
        uu, vv = np.meshgrid(us, vs)
        pixels = np.column_stack((uu.ravel(), vv.ravel(), np.ones(uu.size)))
        directions_cam = pixels @ k_inv.T
        directions = directions_cam @ rotation
        origins = np.broadcast_to(center, directions.shape)
        rays = o3d.core.Tensor(
            np.concatenate([origins, directions], axis=1).astype(np.float32)
        )
        cast = scene.cast_rays(rays)
        tin_depth = cast["t_hit"].numpy().astype(np.float64)
        hit = np.isfinite(tin_depth)
        yy = np.clip((pixels[:, 1] * (mvs.shape[0] / height)).astype(np.int64), 0, mvs.shape[0] - 1)
        xx = np.clip((pixels[:, 0] * (mvs.shape[1] / width)).astype(np.int64), 0, mvs.shape[1] - 1)
        reference = mvs[yy, xx]
        supported = (reference > 0) & hit
        residual = np.abs(tin_depth[supported] - reference[supported])
        proto_rows.append({
            "view": stem,
            "ray_count": int(len(tin_depth)),
            "tin_hit_fraction": float(hit.mean()),
            "mvs_supported_count": int(supported.sum()),
            "median_abs_m": float(np.median(residual)) if len(residual) else None,
            "p95_abs_m": float(np.quantile(residual, 0.95)) if len(residual) else None,
            "gt2m_fraction": float((residual > 2.0).mean()) if len(residual) else None,
            "gt2m_count": int((residual > 2.0).sum()),
            "residual_sum_count": int(len(residual)),
        })
        print(f"[s0b part2] {stem} done", flush=True)

    proto_res = sum(row["residual_sum_count"] for row in proto_rows)
    proto_gt2 = sum(row["gt2m_count"] for row in proto_rows)
    proto_gt2_fraction = proto_gt2 / proto_res if proto_res else None
    proto_median = float(np.median([row["median_abs_m"] for row in proto_rows if row["median_abs_m"] is not None]))
    targets = proto["qa_targets"]
    qa = {
        "median_abs_m": proto_median,
        "gt2m_fraction": proto_gt2_fraction,
        "baseline_gt2m_fraction_same_views": baseline_gt2_fraction,
        "ratio_vs_baseline": (proto_gt2_fraction / baseline_gt2_fraction) if (proto_gt2_fraction is not None and baseline_gt2_fraction) else None,
        "pass_median": proto_median <= float(targets["median_max_m"]),
        "pass_gt2m": proto_gt2_fraction is not None and proto_gt2_fraction <= float(targets["gt2m_fraction_max"]),
        "pass_ratio": (
            proto_gt2_fraction is not None
            and baseline_gt2_fraction
            and proto_gt2_fraction / baseline_gt2_fraction <= float(targets["gt2m_fraction_vs_point_projection_max_ratio"])
        ),
    }
    receipt = {
        "schema": "jointbuildgs.p2.e4_e6_redesign_s0_v1.s0b.v1",
        "task_id": common["task_id"],
        "started_utc": started,
        "ended_utc": datetime.now(timezone.utc).isoformat(),
        "part1_legacy_leak_all_views": part1,
        "part2_projection_prototype": {
            "method": "CLASS_2_6_DSM_TIN_RAYCAST",
            "dsm_cell_m": proto["dsm_cell_m"],
            "ray_stride_px": stride,
            "scene_als_point_count": int(len(als_local)),
            "tin_vertex_count": vertex_count,
            "tin_triangle_count": triangle_count,
            "sample_views": sorted(sample_stems),
            "per_view": proto_rows,
            "qa": qa,
            "qa_targets": targets,
            "note": "prototype uses real (non-synthetic) class-2/6 ALS; residuals include real temporal change, so QA compares against the same-view point-projection baseline.",
        },
        "official_PASS_usable": None,
        "scientific_verdict": None,
    }
    (out_root / "leak_and_projection_qa_v1.json").write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps({"part1": part1, "qa": qa}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
