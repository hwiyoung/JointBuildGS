from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import open3d as o3d
import torch
from gsplat import rasterization_2dgs

from src.stage2.colmap_io import read_cameras_bin, read_images_bin


WORLD_SHIFT = np.asarray([690953.0, 5336071.0, 604.0])
GSD_M = 0.40 / 3.0
VOXEL_M = GSD_M * 4.0
TRUNCATION_M = VOXEL_M * 4.0


def sha256(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--view-roles", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--condition", required=True)
    args = parser.parse_args()
    output = args.output_root.resolve()
    mesh_path = output / "mesh/tsdf_mesh.ply"
    cloud_path = output / "pointcloud/depth_fusion.ply"
    receipt_path = output / "pointcloud/extraction_receipt.json"
    if mesh_path.is_file() and cloud_path.is_file() and receipt_path.is_file():
        return 0
    mesh_path.parent.mkdir(parents=True, exist_ok=True)
    cloud_path.parent.mkdir(parents=True, exist_ok=True)
    checkpoint = torch.load(args.checkpoint, map_location="cuda", weights_only=False)
    state = checkpoint["state_dict"]
    means = state["means"].cuda()
    quats = state["quats"].cuda()
    scales = torch.exp(state["log_scales"]).cuda()
    opacities = torch.sigmoid(state["opacities_raw"]).flatten().cuda()
    colors = torch.cat([state["sh0"], state["shN"]], dim=1).cuda()
    roles = json.loads(args.view_roles.read_text(encoding="utf-8"))
    train_names = set(roles["train_views"])
    sparse = args.data_root / "sparse"
    if (sparse / "0/cameras.bin").is_file():
        sparse = sparse / "0"
    cameras = read_cameras_bin(sparse / "cameras.bin")
    images = [image for image in read_images_bin(sparse / "images.bin").values() if image.name in train_names]
    if len(images) != len(train_names):
        raise RuntimeError(f"training view mismatch: {len(images)} != {len(train_names)}")
    volume = o3d.pipelines.integration.ScalableTSDFVolume(
        voxel_length=VOXEL_M,
        sdf_trunc=TRUNCATION_M,
        color_type=o3d.pipelines.integration.TSDFVolumeColorType.RGB8,
    )
    integrated_pixels = 0
    for index, image in enumerate(sorted(images, key=lambda item: item.name)):
        camera = cameras[image.camera_id]
        width, height = int(camera.width), int(camera.height)
        k = torch.tensor(camera.K(), dtype=torch.float32, device="cuda")
        view = torch.eye(4, dtype=torch.float32, device="cuda")
        view[:3, :3] = torch.tensor(image.R(), dtype=torch.float32, device="cuda")
        view[:3, 3] = torch.tensor(image.tvec, dtype=torch.float32, device="cuda")
        with torch.no_grad():
            rendered = rasterization_2dgs(
                means=means,
                quats=quats,
                scales=scales,
                opacities=opacities,
                colors=colors,
                viewmats=view[None],
                Ks=k[None],
                width=width,
                height=height,
                near_plane=0.01,
                far_plane=500.0,
                render_mode="RGB+ED",
                depth_mode="expected",
                sh_degree=3,
            )
        rgba_depth = rendered[0][0]
        alpha = rendered[1][0, ..., 0]
        rgb = (rgba_depth[..., :3].clamp(0, 1) * 255).byte().cpu().numpy()
        depth = rgba_depth[..., 3]
        valid = (alpha >= 0.5) & torch.isfinite(depth) & (depth > 0.01) & (depth < 500.0)
        depth_np = torch.where(valid, depth, 0.0).float().cpu().numpy()
        integrated_pixels += int(valid.sum().item())
        rgbd = o3d.geometry.RGBDImage.create_from_color_and_depth(
            o3d.geometry.Image(rgb),
            o3d.geometry.Image(depth_np),
            depth_scale=1.0,
            depth_trunc=500.0,
            convert_rgb_to_intensity=False,
        )
        intrinsic = o3d.camera.PinholeCameraIntrinsic(
            width, height, float(k[0, 0]), float(k[1, 1]), float(k[0, 2]), float(k[1, 2])
        )
        volume.integrate(rgbd, intrinsic, view.cpu().numpy())
        if (index + 1) % 25 == 0:
            print(f"[TSDF {args.condition}] {index + 1}/{len(images)}", flush=True)
    mesh = volume.extract_triangle_mesh()
    mesh.compute_vertex_normals()
    if len(mesh.triangles) == 0:
        raise RuntimeError("TSDF extraction produced an empty mesh")
    mesh.translate(WORLD_SHIFT)
    if not o3d.io.write_triangle_mesh(str(mesh_path), mesh, write_ascii=False):
        raise RuntimeError(f"failed to write {mesh_path}")
    vertices = np.asarray(mesh.vertices)
    triangles = np.asarray(mesh.triangles)
    triangle_xyz = vertices[triangles]
    area = float((0.5 * np.linalg.norm(np.cross(triangle_xyz[:, 1] - triangle_xyz[:, 0], triangle_xyz[:, 2] - triangle_xyz[:, 0]), axis=1)).sum())
    # Roofer consumes the point cloud extracted directly from the fused TSDF
    # volume.  The mesh is retained only for geometric evaluation; it must not
    # be resampled into the Roofer evidence path.
    cloud = volume.extract_point_cloud()
    if len(cloud.points) == 0:
        raise RuntimeError("TSDF extraction produced an empty point cloud")
    cloud.translate(WORLD_SHIFT)
    if not o3d.io.write_point_cloud(str(cloud_path), cloud, write_ascii=False):
        raise RuntimeError(f"failed to write {cloud_path}")
    receipt = {
        "schema": "jointbuildgs.p2.e1_e6.tsdf_extraction.v2",
        "condition": args.condition,
        "checkpoint": {"path": str(args.checkpoint), "sha256": sha256(args.checkpoint)},
        "training_view_count": len(images),
        "held_out_views_integrated": 0,
        "alpha_threshold": 0.5,
        "effective_training_gsd_m": GSD_M,
        "tsdf_voxel_rule": "GSD_X_4",
        "tsdf_voxel_m": VOXEL_M,
        "tsdf_truncation_rule": "VOXEL_X_4",
        "tsdf_truncation_m": TRUNCATION_M,
        "integrated_pixel_count": integrated_pixels,
        "mesh_surface_area_m2": area,
        "mesh_polygon_count": int(len(triangles)),
        "roofer_pointcloud_source": "TSDF_VOLUME_EXTRACT_POINT_CLOUD_DIRECT",
        "mesh_used_to_create_roofer_pointcloud": False,
        "point_count": int(len(cloud.points)),
        "mesh": {"path": str(mesh_path), "sha256": sha256(mesh_path)},
        "pointcloud": {"path": str(cloud_path), "sha256": sha256(cloud_path)},
        "scientific_verdict": None,
    }
    receipt_path.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
