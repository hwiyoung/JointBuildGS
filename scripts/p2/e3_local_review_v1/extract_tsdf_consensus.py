#!/usr/bin/env python3
"""Fuse E3 rendered depth after current-image depth bounds and view consensus.

This is the local-E3 adapter of the repository's established per-view voxel
consensus followed by TSDF integration.  It deliberately keeps the baseline
expected-depth renderer, alpha gate, TSDF voxel/truncation, train-view set and
direct ``extract_point_cloud`` Roofer lineage unchanged.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from typing import Any

import numpy as np
import open3d as o3d
import torch
from gsplat import rasterization_2dgs

from src.stage2.colmap_io import (
    Camera,
    Image,
    read_cameras_bin,
    read_images_bin,
    read_points3d_bin,
)


SCHEMA = "jointbuildgs.p2.e3_local_4906982.tsdf_consensus_extraction.v1"
WORLD_SHIFT = np.asarray([690953.0, 5336071.0, 604.0])
GSD_M = 0.40 / 3.0
TSDF_VOXEL_M = GSD_M * 4.0
TSDF_TRUNCATION_M = TSDF_VOXEL_M * 4.0


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def sparse_depth_bounds(
    image: Image,
    camera: Camera,
    xyz: np.ndarray,
    quantile_low: float,
    quantile_high: float,
    margin_m: float,
    minimum_points: int,
) -> tuple[float, float, int, bool]:
    camera_xyz = xyz @ image.R().T + image.tvec
    z = camera_xyz[:, 2]
    positive = z > 0.01
    x = camera_xyz[:, 0] / np.maximum(z, 1e-12)
    y = camera_xyz[:, 1] / np.maximum(z, 1e-12)
    k = camera.K()
    u = k[0, 0] * x + k[0, 2]
    v = k[1, 1] * y + k[1, 2]
    inside = positive & (u >= 0) & (u < camera.width) & (v >= 0) & (v < camera.height)
    visible = z[inside]
    if len(visible) < minimum_points:
        return 0.01, 500.0, int(len(visible)), True
    low, high = np.quantile(visible, [quantile_low, quantile_high])
    return max(0.01, float(low) - margin_m), min(500.0, float(high) + margin_m), int(len(visible)), False


def pack_voxels(points: np.ndarray, voxel_m: float) -> np.ndarray:
    q = np.floor(np.asarray(points, dtype=np.float64) / float(voxel_m)).astype(np.int64)
    offset = np.int64(1 << 20)
    multiplier = np.int64(1 << 21)
    if np.any(np.abs(q) >= offset):
        raise RuntimeError("consensus voxel index exceeds packed range")
    return ((q[:, 0] + offset) * multiplier + (q[:, 1] + offset)) * multiplier + (q[:, 2] + offset)


def render_depth(
    state: dict[str, torch.Tensor],
    image: Image,
    camera: Camera,
) -> tuple[torch.Tensor, torch.Tensor, np.ndarray, torch.Tensor, torch.Tensor]:
    device = state["means"].device
    k = torch.tensor(camera.K(), dtype=torch.float32, device=device)
    view = torch.eye(4, dtype=torch.float32, device=device)
    view[:3, :3] = torch.tensor(image.R(), dtype=torch.float32, device=device)
    view[:3, 3] = torch.tensor(image.tvec, dtype=torch.float32, device=device)
    with torch.no_grad():
        output = rasterization_2dgs(
            means=state["means"],
            quats=state["quats"],
            scales=state["scales"],
            opacities=state["opacities"],
            colors=state["colors"],
            viewmats=view[None],
            Ks=k[None],
            width=int(camera.width),
            height=int(camera.height),
            near_plane=0.01,
            far_plane=500.0,
            render_mode="RGB+ED",
            depth_mode="expected",
            sh_degree=3,
        )
    rgba_depth = output[0][0]
    alpha = output[1][0, ..., 0]
    rgb = (rgba_depth[..., :3].clamp(0, 1) * 255).byte().cpu().numpy()
    return rgba_depth[..., 3], alpha, rgb, k, view


def backproject_valid(
    depth: torch.Tensor,
    valid: torch.Tensor,
    k: torch.Tensor,
    view: torch.Tensor,
) -> tuple[np.ndarray, np.ndarray]:
    height, width = depth.shape
    vv, uu = torch.meshgrid(
        torch.arange(height, dtype=torch.float32, device=depth.device),
        torch.arange(width, dtype=torch.float32, device=depth.device),
        indexing="ij",
    )
    z = depth[valid]
    camera_xyz = torch.stack(
        (
            (uu[valid] - k[0, 2]) / k[0, 0] * z,
            (vv[valid] - k[1, 2]) / k[1, 1] * z,
            z,
        ),
        dim=1,
    )
    world_local = (camera_xyz - view[:3, 3]) @ view[:3, :3]
    flat = torch.nonzero(valid.reshape(-1), as_tuple=False).reshape(-1)
    return world_local.cpu().numpy().astype(np.float64), flat.cpu().numpy().astype(np.int64)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--view-roles", type=Path, required=True)
    parser.add_argument("--depth-bound-points", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--condition", required=True)
    parser.add_argument("--alpha", type=float, default=0.5)
    parser.add_argument("--minimum-views", type=int, default=3)
    parser.add_argument("--consensus-voxel-m", type=float, default=TSDF_VOXEL_M * 2.0)
    parser.add_argument("--depth-quantile-low", type=float, default=0.01)
    parser.add_argument("--depth-quantile-high", type=float, default=0.99)
    parser.add_argument("--depth-margin-m", type=float, default=10.0)
    parser.add_argument("--minimum-sparse-points", type=int, default=100)
    args = parser.parse_args()
    if args.minimum_views < 2:
        raise ValueError("minimum-views must be at least 2")
    if not 0 <= args.depth_quantile_low < args.depth_quantile_high <= 1:
        raise ValueError("invalid depth quantiles")

    output = args.output_root.resolve()
    mesh_path = output / "mesh/tsdf_mesh.ply"
    cloud_path = output / "pointcloud/depth_fusion.ply"
    receipt_path = output / "pointcloud/extraction_receipt.json"
    if mesh_path.is_file() and cloud_path.is_file() and receipt_path.is_file():
        print(json.dumps({"status": "reused", "receipt": str(receipt_path)}))
        return 0
    mesh_path.parent.mkdir(parents=True, exist_ok=True)
    cloud_path.parent.mkdir(parents=True, exist_ok=True)

    checkpoint = torch.load(args.checkpoint, map_location="cuda", weights_only=False)
    raw = checkpoint["state_dict"]
    state = {
        "means": raw["means"].cuda(),
        "quats": raw["quats"].cuda(),
        "scales": torch.exp(raw["log_scales"]).cuda(),
        "opacities": torch.sigmoid(raw["opacities_raw"]).flatten().cuda(),
        "colors": torch.cat([raw["sh0"], raw["shN"]], dim=1).cuda(),
    }
    sparse = args.data_root / "sparse"
    if (sparse / "0/cameras.bin").is_file():
        sparse = sparse / "0"
    cameras = read_cameras_bin(sparse / "cameras.bin")
    roles = json.loads(args.view_roles.read_text(encoding="utf-8"))
    train_names = set(roles["train_views"])
    images = sorted(
        (image for image in read_images_bin(sparse / "images.bin").values() if image.name in train_names),
        key=lambda image: image.name,
    )
    if len(images) != len(train_names):
        raise RuntimeError(f"training view mismatch: {len(images)} != {len(train_names)}")
    bound_xyz = read_points3d_bin(args.depth_bound_points)[:, :3]

    bounds: dict[str, tuple[float, float]] = {}
    bound_rows: list[dict[str, Any]] = []
    per_view_keys: list[np.ndarray] = []
    raw_valid_pixels = 0
    bounded_pixels = 0
    for index, image in enumerate(images):
        camera = cameras[image.camera_id]
        low, high, count, fallback = sparse_depth_bounds(
            image,
            camera,
            bound_xyz,
            args.depth_quantile_low,
            args.depth_quantile_high,
            args.depth_margin_m,
            args.minimum_sparse_points,
        )
        bounds[image.name] = (low, high)
        bound_rows.append({
            "image_name": image.name,
            "near_m": low,
            "far_m": high,
            "visible_current_sfm_point_count": count,
            "fallback_0p01_500": fallback,
        })
        depth, alpha, _rgb, k, view = render_depth(state, image, camera)
        base = (alpha >= args.alpha) & torch.isfinite(depth) & (depth > 0.01) & (depth < 500.0)
        valid = base & (depth >= low) & (depth <= high)
        raw_valid_pixels += int(base.sum().item())
        bounded_pixels += int(valid.sum().item())
        points, _flat = backproject_valid(depth, valid, k, view)
        keys = np.unique(pack_voxels(points, args.consensus_voxel_m)) if len(points) else np.empty(0, dtype=np.int64)
        per_view_keys.append(keys)
        if (index + 1) % 10 == 0:
            print(f"[consensus pass] {index + 1}/{len(images)}", flush=True)

    all_keys = np.concatenate(per_view_keys)
    unique_keys, counts = np.unique(all_keys, return_counts=True)
    kept_keys = unique_keys[counts >= args.minimum_views]
    if not len(kept_keys):
        raise RuntimeError("no consensus voxels survived")
    print(
        f"[consensus] minimum_views={args.minimum_views} kept={len(kept_keys)}/{len(unique_keys)}",
        flush=True,
    )

    volume = o3d.pipelines.integration.ScalableTSDFVolume(
        voxel_length=TSDF_VOXEL_M,
        sdf_trunc=TSDF_TRUNCATION_M,
        color_type=o3d.pipelines.integration.TSDFVolumeColorType.RGB8,
    )
    integrated_pixels = 0
    integrated_views = 0
    for index, image in enumerate(images):
        camera = cameras[image.camera_id]
        low, high = bounds[image.name]
        depth, alpha, rgb, k, view = render_depth(state, image, camera)
        valid = (
            (alpha >= args.alpha)
            & torch.isfinite(depth)
            & (depth >= low)
            & (depth <= high)
            & (depth > 0.01)
            & (depth < 500.0)
        )
        points, flat = backproject_valid(depth, valid, k, view)
        keys = pack_voxels(points, args.consensus_voxel_m) if len(points) else np.empty(0, dtype=np.int64)
        selected = np.isin(keys, kept_keys, assume_unique=False)
        if not np.any(selected):
            continue
        depth_np = np.zeros((camera.height, camera.width), dtype=np.float32)
        depth_values = depth.reshape(-1).detach().cpu().numpy().astype(np.float32)
        depth_np.reshape(-1)[flat[selected]] = depth_values[flat[selected]]
        rgbd = o3d.geometry.RGBDImage.create_from_color_and_depth(
            o3d.geometry.Image(np.ascontiguousarray(rgb)),
            o3d.geometry.Image(np.ascontiguousarray(depth_np)),
            depth_scale=1.0,
            depth_trunc=500.0,
            convert_rgb_to_intensity=False,
        )
        intrinsic = o3d.camera.PinholeCameraIntrinsic(
            int(camera.width),
            int(camera.height),
            float(k[0, 0]),
            float(k[1, 1]),
            float(k[0, 2]),
            float(k[1, 2]),
        )
        volume.integrate(rgbd, intrinsic, view.cpu().numpy())
        integrated_views += 1
        integrated_pixels += int(np.count_nonzero(selected))
        if (index + 1) % 10 == 0:
            print(f"[TSDF pass] {index + 1}/{len(images)}", flush=True)

    mesh = volume.extract_triangle_mesh()
    mesh.compute_vertex_normals()
    cloud = volume.extract_point_cloud()
    if not len(mesh.triangles) or not len(cloud.points):
        raise RuntimeError("filtered TSDF extraction produced empty geometry")
    mesh.translate(WORLD_SHIFT)
    cloud.translate(WORLD_SHIFT)
    if not o3d.io.write_triangle_mesh(str(mesh_path), mesh, write_ascii=False):
        raise RuntimeError(f"failed to write {mesh_path}")
    if not o3d.io.write_point_cloud(str(cloud_path), cloud, write_ascii=False):
        raise RuntimeError(f"failed to write {cloud_path}")

    vertices = np.asarray(mesh.vertices)
    triangles = np.asarray(mesh.triangles)
    triangle_xyz = vertices[triangles]
    surface_area = float(
        (0.5 * np.linalg.norm(np.cross(
            triangle_xyz[:, 1] - triangle_xyz[:, 0],
            triangle_xyz[:, 2] - triangle_xyz[:, 0],
        ), axis=1)).sum()
    )
    receipt = {
        "schema": SCHEMA,
        "condition": args.condition,
        "checkpoint": {"path": str(args.checkpoint), "sha256": sha256(args.checkpoint)},
        "training_view_count": len(images),
        "held_out_views_integrated": 0,
        "depth_mode": "expected",
        "alpha_threshold": args.alpha,
        "depth_bound_source": {
            "role": "CURRENT_IMAGE_SFM_ONLY",
            "path": str(args.depth_bound_points),
            "sha256": sha256(args.depth_bound_points),
            "quantiles": [args.depth_quantile_low, args.depth_quantile_high],
            "margin_m": args.depth_margin_m,
            "views": bound_rows,
        },
        "raw_alpha_valid_pixel_count": raw_valid_pixels,
        "depth_bounded_pixel_count": bounded_pixels,
        "consensus": {
            "method": "DISTINCT_VIEW_VOXEL_SUPPORT_REUSED_FROM_C3_TSDF_DIAGNOSTIC",
            "voxel_m": args.consensus_voxel_m,
            "minimum_distinct_views": args.minimum_views,
            "candidate_voxel_count": int(len(unique_keys)),
            "kept_voxel_count": int(len(kept_keys)),
        },
        "integrated_view_count": integrated_views,
        "integrated_pixel_count": integrated_pixels,
        "tsdf_voxel_m": TSDF_VOXEL_M,
        "tsdf_truncation_m": TSDF_TRUNCATION_M,
        "point_count": int(len(cloud.points)),
        "mesh_polygon_count": int(len(triangles)),
        "mesh_surface_area_m2": surface_area,
        "roofer_pointcloud_source": "CONSENSUS_FILTERED_TSDF_VOLUME_EXTRACT_POINT_CLOUD_DIRECT",
        "mesh_used_to_create_roofer_pointcloud": False,
        "mesh": {"path": str(mesh_path), "sha256": sha256(mesh_path)},
        "pointcloud": {"path": str(cloud_path), "sha256": sha256(cloud_path)},
        "scientific_verdict": None,
    }
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = receipt_path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, receipt_path)
    print(json.dumps({"status": "complete", "point_count": len(cloud.points), "receipt": str(receipt_path)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
