#!/usr/bin/env python3
"""Extract paired roof-only Poisson/TSDF surfaces from identical C3 views.

No training, Roofer, G2, evaluation metric, or C4/C5 input is invoked.  The
TSDF and Poisson branches start from the same checkpoint-rendered median-depth
pixels, GS semantic roof mask, camera set, footprint buffer and two-view voxel
consensus.  Poisson consumes the oriented consensus points; TSDF retains the
camera rays and truncation band for those same consensus-supported pixels.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import json
from pathlib import Path
from typing import Any, Mapping

import numpy as np
import open3d as o3d
from scipy.spatial import cKDTree
from shapely import contains_xy
import torch

from scripts.p2.c1_c2_oracle_c3_extract_v1.contract import load_building_references
from scripts.p2.c1_c2_oracle_c3_extract_v1.extract_c3 import _project_box
from scripts.p2.c3_tsdf_roof_diagnostic_v1.contract import (
    canonical_json_bytes,
    file_record,
    load_config,
    require_regular,
    resolve_artifact,
    sha256_file,
    validate_config,
    write_new,
)
from scripts.p2.c3_utarget199_postprocess_v1.render_gs import model_from_checkpoint
from src.stage2.dataloader import ColmapDataset
from src.stage2.renderer import render, render_semantic


def _visible_names(config: Mapping[str, Any], repo_root: Path) -> list[str]:
    path = repo_root / config["source"]["exact_view_manifest_git_path"]
    manifest = json.loads(path.read_text(encoding="utf-8"))
    names = [str(row["basename"]) for row in manifest["rows"]]
    if len(names) != int(config["source"]["exact_view_count"]):
        raise RuntimeError("exact view membership drifted")
    return names


def _current_ground_z(v13_root: Path, stable_id: str) -> float:
    path = v13_root / f"operations/C2_MVS_GT_FOOTPRINT_ORACLE/{stable_id}/work/prepared_v1.json"
    value = json.loads(path.read_text(encoding="utf-8"))["classification"]["local_ground_z"]
    if value is None or not np.isfinite(float(value)):
        raise RuntimeError(f"current C2 terrain ground is unavailable: {stable_id}")
    return float(value)


def shared_view_plan(
    dataset: ColmapDataset,
    references: Mapping[str, Any],
    config: Mapping[str, Any],
    v13_root: Path,
) -> dict[str, list[dict[str, Any]]]:
    plan_cfg = config["shared_view_plan"]
    shift = np.asarray(config["frame"]["world_shift_xyz"], dtype=np.float64)
    downscale = float(plan_cfg["render_downscale"])
    buffer_m = float(plan_cfg["footprint_crop_buffer_m"])
    below = float(plan_cfg["prism_below_current_ground_m"])
    above = float(plan_cfg["prism_above_current_ground_m"])
    limit = int(plan_cfg["maximum_views_per_building"])
    output: dict[str, list[dict[str, Any]]] = {}
    for stable_id, reference in references.items():
        x0, y0, x1, y1 = reference.footprint.bounds
        bbox_local = (
            x0 - shift[0] - buffer_m,
            y0 - shift[1] - buffer_m,
            x1 - shift[0] + buffer_m,
            y1 - shift[1] + buffer_m,
        )
        ground = _current_ground_z(v13_root, stable_id)
        z0 = ground - shift[2] - below
        z1 = ground - shift[2] + above
        candidates: list[dict[str, Any]] = []
        for index, frame in enumerate(dataset.frames):
            projected = _project_box(frame, bbox_local, z0, z1, downscale)
            if projected is None:
                continue
            area, crop = projected
            candidates.append({
                "index": int(index),
                "name": str(frame.name),
                "projected_area_px": float(area),
                "crop_xyxy": list(map(int, crop)),
            })
        candidates.sort(key=lambda row: (-row["projected_area_px"], row["name"]))
        if len(candidates) < limit:
            raise RuntimeError(f"fewer than {limit} shared views: {stable_id}")
        output[stable_id] = candidates[:limit]
    return output


def _pack_voxels(xyz_local: np.ndarray, voxel_m: float) -> tuple[np.ndarray, np.ndarray]:
    q = np.floor(np.asarray(xyz_local, dtype=np.float64) / float(voxel_m)).astype(np.int64)
    offset = np.int64(1 << 20)
    mul = np.int64(1 << 21)
    if np.any(np.abs(q) >= offset):
        raise RuntimeError("building-local voxel index exceeded packed range")
    packed = ((q[:, 0] + offset) * mul + (q[:, 1] + offset)) * mul + (q[:, 2] + offset)
    return packed, q


def _point_ply(
    xyz: np.ndarray,
    normals: np.ndarray,
    rgb: np.ndarray,
    view_count: np.ndarray,
) -> bytes:
    rows = np.empty(len(xyz), dtype=np.dtype([
        ("x", "<f8"), ("y", "<f8"), ("z", "<f8"),
        ("nx", "<f4"), ("ny", "<f4"), ("nz", "<f4"),
        ("red", "u1"), ("green", "u1"), ("blue", "u1"),
        ("semantic_class", "u1"), ("view_count", "<u2"),
    ]))
    rows["x"], rows["y"], rows["z"] = np.asarray(xyz, dtype=np.float64).T
    rows["nx"], rows["ny"], rows["nz"] = np.asarray(normals, dtype=np.float32).T
    color = np.rint(np.clip(rgb, 0, 1) * 255).astype(np.uint8)
    rows["red"], rows["green"], rows["blue"] = color.T
    rows["semantic_class"] = 1
    rows["view_count"] = np.asarray(view_count, dtype=np.uint16)
    header = (
        "ply\nformat binary_little_endian 1.0\n"
        "comment JointBuildGS shared-view roof semantic consensus; EPSG:25832\n"
        f"element vertex {len(rows)}\n"
        "property double x\nproperty double y\nproperty double z\n"
        "property float nx\nproperty float ny\nproperty float nz\n"
        "property uchar red\nproperty uchar green\nproperty uchar blue\n"
        "property uchar semantic_class\nproperty ushort view_count\nend_header\n"
    ).encode("ascii")
    return header + rows.tobytes()


def _mesh_boundary_stats(mesh: o3d.geometry.TriangleMesh) -> dict[str, Any]:
    triangles = np.asarray(mesh.triangles, dtype=np.int64)
    if not len(triangles):
        return {
            "connected_component_count": 0,
            "largest_component_triangle_fraction": 0.0,
            "boundary_edge_count": 0,
            "boundary_edge_fraction": 0.0,
            "boundary_loop_count": 0,
            "hole_like_loop_count": 0,
            "watertight": False,
        }
    labels, counts, _areas = mesh.cluster_connected_triangles()
    counts_np = np.asarray(counts, dtype=np.int64)
    edges = np.sort(np.vstack((triangles[:, [0, 1]], triangles[:, [1, 2]], triangles[:, [2, 0]])), axis=1)
    unique, edge_counts = np.unique(edges, axis=0, return_counts=True)
    boundary = unique[edge_counts == 1]
    graph: dict[int, set[int]] = defaultdict(set)
    for left, right in boundary:
        graph[int(left)].add(int(right))
        graph[int(right)].add(int(left))
    unseen = set(graph)
    loops = 0
    while unseen:
        loops += 1
        stack = [unseen.pop()]
        while stack:
            for node in graph[stack.pop()]:
                if node in unseen:
                    unseen.remove(node)
                    stack.append(node)
    components = int(len(counts_np))
    return {
        "connected_component_count": components,
        "largest_component_triangle_fraction": float(counts_np.max() / counts_np.sum()),
        "boundary_edge_count": int(len(boundary)),
        "boundary_edge_fraction": float(len(boundary) / max(len(unique), 1)),
        "boundary_loop_count": int(loops),
        "hole_like_loop_count": int(max(0, loops - components)),
        "watertight": bool(mesh.is_watertight()),
    }


def _coverage(xyz: np.ndarray, footprint: Any, cell_m: float, radius_m: float) -> dict[str, Any]:
    x0, y0, x1, y1 = footprint.bounds
    xs = np.arange(x0 + cell_m / 2, x1, cell_m)
    ys = np.arange(y0 + cell_m / 2, y1, cell_m)
    xx, yy = np.meshgrid(xs, ys)
    grid = np.column_stack((xx.ravel(), yy.ravel()))
    inside = contains_xy(footprint, grid[:, 0], grid[:, 1])
    grid = grid[inside]
    if not len(grid) or not len(xyz):
        return {"grid_cell_count": int(len(grid)), "covered_cell_count": 0, "coverage_fraction": 0.0}
    distances, _ = cKDTree(np.asarray(xyz)[:, :2]).query(grid, k=1)
    covered = distances <= radius_m
    return {
        "grid_cell_count": int(len(grid)),
        "covered_cell_count": int(np.count_nonzero(covered)),
        "coverage_fraction": float(np.mean(covered)),
    }


def _mesh_evidence_stats(
    mesh: o3d.geometry.TriangleMesh,
    evidence_xyz: np.ndarray,
    thresholds: list[float],
) -> dict[str, Any]:
    vertices = np.asarray(mesh.vertices, dtype=np.float64)
    base = {
        "mesh_vertex_count": int(len(vertices)),
        "mesh_triangle_count": int(len(mesh.triangles)),
        "surface_area_m2": float(mesh.get_surface_area()) if len(mesh.triangles) else 0.0,
        **_mesh_boundary_stats(mesh),
    }
    if not len(vertices) or not len(evidence_xyz):
        base["nearest_evidence_distance_m"] = None
        return base
    distances, _ = cKDTree(np.asarray(evidence_xyz, dtype=np.float64)).query(vertices, k=1)
    base["nearest_evidence_distance_m"] = {
        "median": float(np.median(distances)),
        "p95": float(np.quantile(distances, 0.95)),
        "maximum": float(np.max(distances)),
        "far_fraction_by_threshold": {
            f"{value:.3f}": float(np.mean(distances > value)) for value in thresholds
        },
    }
    return base


def _write_mesh(path: Path, mesh: o3d.geometry.TriangleMesh) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() or not o3d.io.write_triangle_mesh(str(path), mesh, write_ascii=False):
        raise RuntimeError(f"failed to write mesh: {path}")


def _crop_mesh(
    mesh: o3d.geometry.TriangleMesh,
    footprint: Any,
    evidence_xyz: np.ndarray,
    buffer_m: float,
    vertical_margin_m: float,
) -> o3d.geometry.TriangleMesh:
    if not len(evidence_xyz) or not len(mesh.vertices):
        return mesh
    x0, y0, x1, y1 = footprint.bounds
    z0 = float(np.quantile(evidence_xyz[:, 2], 0.005) - vertical_margin_m)
    z1 = float(np.quantile(evidence_xyz[:, 2], 0.995) + vertical_margin_m)
    mesh = mesh.crop(o3d.geometry.AxisAlignedBoundingBox(
        min_bound=(x0 - buffer_m, y0 - buffer_m, z0),
        max_bound=(x1 + buffer_m, y1 + buffer_m, z1),
    ))
    mesh.remove_unreferenced_vertices()
    mesh.compute_vertex_normals()
    return mesh


def _condition_gaussian_stats(
    state: Mapping[str, torch.Tensor],
    references: Mapping[str, Any],
    config: Mapping[str, Any],
) -> dict[str, Any]:
    shift = np.asarray(config["frame"]["world_shift_xyz"], dtype=np.float64)
    means = state["means"].detach().cpu().numpy().astype(np.float64) + shift
    labels = torch.argmax(state["sem_logits"].detach().cpu(), dim=-1).numpy().astype(np.uint8)
    scales = torch.exp(state["log_scales"].detach().cpu()).numpy().astype(np.float64)
    opacity = torch.sigmoid(state["opacities_raw"].detach().cpu()).numpy().reshape(-1)
    buffer_m = float(config["diagnostics"]["gaussian_crop_buffer_m"])
    large = float(config["diagnostics"]["large_in_plane_scale_m"])
    names = ["BACKGROUND", "ROOF", "WALL", "TERRAIN"]
    output: dict[str, Any] = {}
    for stable_id, reference in references.items():
        x0, y0, x1, y1 = reference.footprint.bounds
        keep = (
            (means[:, 0] >= x0 - buffer_m) & (means[:, 0] <= x1 + buffer_m)
            & (means[:, 1] >= y0 - buffer_m) & (means[:, 1] <= y1 + buffer_m)
        )
        rows = {}
        in_plane = np.max(scales[:, :2], axis=1)
        for class_id, name in enumerate(names):
            selected = keep & (labels == class_id)
            values = in_plane[selected]
            op = opacity[selected]
            z = means[selected, 2]
            rows[name] = {
                "count": int(np.count_nonzero(selected)),
                "in_plane_scale_m": None if not len(values) else {
                    "median": float(np.median(values)),
                    "p95": float(np.quantile(values, 0.95)),
                    "maximum": float(np.max(values)),
                    "above_large_threshold_count": int(np.count_nonzero(values > large)),
                    "above_large_threshold_fraction": float(np.mean(values > large)),
                },
                "opacity": None if not len(op) else {
                    "median": float(np.median(op)), "p95": float(np.quantile(op, 0.95))
                },
                "z_m": None if not len(z) else {
                    "minimum": float(np.min(z)), "median": float(np.median(z)), "maximum": float(np.max(z))
                },
            }
        output[stable_id] = rows
    return output


def extract_condition(
    *,
    condition_id: str,
    checkpoint: Path,
    output_root: Path,
    dataset: ColmapDataset,
    plan: Mapping[str, list[dict[str, Any]]],
    references: Mapping[str, Any],
    config: Mapping[str, Any],
    device: str,
) -> dict[str, Any]:
    payload = torch.load(checkpoint, map_location="cpu", weights_only=True)
    state = payload["state_dict"]
    gaussian_stats = _condition_gaussian_stats(state, references, config)
    model = model_from_checkpoint(checkpoint, device)
    plan_cfg = config["shared_view_plan"]
    surf_cfg = config["surface"]
    shift = np.asarray(config["frame"]["world_shift_xyz"], dtype=np.float64)
    buffer_m = float(surf_cfg["footprint_buffer_m"])
    voxel_m = float(surf_cfg["fusion_voxel_m"])
    minimum_views = int(surf_cfg["minimum_distinct_views"])
    alpha_min = float(surf_cfg["alpha_min"])
    by_view: dict[int, list[tuple[str, tuple[int, int, int, int]]]] = defaultdict(list)
    for stable_id, rows in plan.items():
        for row in rows:
            by_view[int(row["index"])].append((stable_id, tuple(map(int, row["crop_xyxy"]))))
    origins: dict[str, np.ndarray] = {}
    for stable_id, reference in references.items():
        cx, cy = reference.footprint.centroid.coords[0]
        origins[stable_id] = np.asarray(
            [cx, cy, float(plan[stable_id][0]["current_ground_z"])], dtype=np.float64
        )
    accumulators: dict[str, dict[int, list[Any]]] = {stable_id: {} for stable_id in references}
    view_records: dict[str, list[dict[str, Any]]] = {stable_id: [] for stable_id in references}
    rendered_views: list[dict[str, Any]] = []
    torch.cuda.reset_peak_memory_stats()
    with torch.no_grad():
        for index in sorted(by_view):
            batch = dataset[index]
            width, height = int(batch["width"]), int(batch["height"])
            output = render(
                model, batch["w2c"].to(device), batch["K"].to(device), width, height,
                sh_degree=3, render_mode="RGB+ED", bg_color=torch.ones(3, device=device), depth_mode="expected",
            )
            logits = render_semantic(model, batch["w2c"].to(device), batch["K"].to(device), width, height)
            depth = output["depth_median"]
            alpha = output["alpha"]
            normals = output["normal_render"]
            rgb = output["rgb"]
            labels = torch.argmax(logits, dim=-1)
            R = batch["w2c"][:3, :3].to(device)
            t = batch["w2c"][:3, 3].to(device)
            K = batch["K"].to(device)
            for stable_id, crop in by_view[index]:
                left, top, right, bottom = crop
                d = depth[top:bottom, left:right]
                a = alpha[top:bottom, left:right]
                n = normals[top:bottom, left:right]
                c = rgb[top:bottom, left:right]
                lab = labels[top:bottom, left:right]
                vv, uu = torch.meshgrid(
                    torch.arange(top, bottom, device=device, dtype=torch.float32),
                    torch.arange(left, right, device=device, dtype=torch.float32),
                    indexing="ij",
                )
                valid = (
                    (a >= alpha_min) & (lab == int(surf_cfg["semantic_roof_class"]))
                    & torch.isfinite(d) & (d > float(surf_cfg["depth_min_m"]))
                    & (d < float(surf_cfg["depth_max_m"]))
                )
                if not torch.any(valid):
                    continue
                z = d[valid]
                xc = (uu[valid] - K[0, 2]) / K[0, 0] * z
                yc = (vv[valid] - K[1, 2]) / K[1, 1] * z
                world_local = (torch.stack((xc, yc, z), dim=1) - t) @ R
                world = world_local + torch.as_tensor(shift, device=device, dtype=world_local.dtype)
                xyz = world.cpu().numpy().astype(np.float64)
                footprint = references[stable_id].footprint.buffer(buffer_m)
                inside = contains_xy(footprint, xyz[:, 0], xyz[:, 1])
                if not np.any(inside):
                    continue
                xyz = xyz[inside]
                normal = n[valid].cpu().numpy().astype(np.float64)[inside]
                color = c[valid].cpu().numpy().astype(np.float64)[inside]
                origin = origins[stable_id]
                packed, _q = _pack_voxels(xyz - origin, voxel_m)
                unique, inverse = np.unique(packed, return_inverse=True)
                counts = np.bincount(inverse).astype(np.float64)
                xyz_sum = np.vstack([np.bincount(inverse, weights=xyz[:, axis]) for axis in range(3)]).T
                n_sum = np.vstack([np.bincount(inverse, weights=normal[:, axis]) for axis in range(3)]).T
                c_sum = np.vstack([np.bincount(inverse, weights=color[:, axis]) for axis in range(3)]).T
                accumulator = accumulators[stable_id]
                for row_index, key in enumerate(unique.tolist()):
                    old = accumulator.get(int(key))
                    if old is None:
                        accumulator[int(key)] = [1, counts[row_index], xyz_sum[row_index], n_sum[row_index], c_sum[row_index]]
                    else:
                        old[0] += 1
                        old[1] += counts[row_index]
                        old[2] += xyz_sum[row_index]
                        old[3] += n_sum[row_index]
                        old[4] += c_sum[row_index]
                valid_indices = torch.nonzero(valid.reshape(-1), as_tuple=False).reshape(-1).cpu().numpy()
                valid_indices = valid_indices[inside]
                K_crop = batch["K"].cpu().numpy().astype(np.float64).copy()
                K_crop[0, 2] -= left
                K_crop[1, 2] -= top
                extrinsic = batch["w2c"].cpu().numpy().astype(np.float64).copy()
                origin_local = origin - shift
                extrinsic[:3, 3] += extrinsic[:3, :3] @ origin_local
                view_records[stable_id].append({
                    "image_name": str(batch["name"]),
                    "shape": (bottom - top, right - left),
                    "depth": d.cpu().numpy().astype(np.float32),
                    "rgb": c.cpu().numpy().astype(np.float32),
                    "valid_flat_indices": valid_indices,
                    "packed": packed,
                    "K": K_crop,
                    "extrinsic": extrinsic,
                })
            rendered_views.append({"index": int(index), "name": str(batch["name"]), "building_ids": [x[0] for x in by_view[index]]})
    results: list[dict[str, Any]] = []
    thresholds = list(map(float, surf_cfg["mesh_evidence_distance_thresholds_m"]))
    for stable_id, reference in references.items():
        kept = [(key, row) for key, row in accumulators[stable_id].items() if int(row[0]) >= minimum_views]
        kept.sort(key=lambda item: item[0])
        building_root = output_root / f"conditions/{condition_id}/buildings/{stable_id}"
        result: dict[str, Any] = {
            "condition_id": condition_id,
            "stable_id": stable_id,
            "shared_view_count": len(plan[stable_id]),
            "rendered_roof_view_count": len(view_records[stable_id]),
            "minimum_distinct_views": minimum_views,
            "scientific_verdict": None,
        }
        if not kept:
            result.update({"status": "INSUFFICIENT_SHARED_VIEW_ROOF_EVIDENCE", "consensus_roof_point_count": 0})
            write_new(building_root / "result_v1.json", canonical_json_bytes(result))
            results.append(result)
            continue
        xyz = np.asarray([row[1][2] / row[1][1] for row in kept], dtype=np.float64)
        normals = np.asarray([row[1][3] for row in kept], dtype=np.float64)
        normals /= np.maximum(np.linalg.norm(normals, axis=1, keepdims=True), 1e-12)
        colors = np.asarray([row[1][4] / row[1][1] for row in kept], dtype=np.float64)
        view_count = np.asarray([row[1][0] for row in kept], dtype=np.uint16)
        kept_keys = np.asarray([row[0] for row in kept], dtype=np.int64)
        points_path = building_root / "shared_view_roof_consensus_points_v1.ply"
        write_new(points_path, _point_ply(xyz, normals, colors, view_count))
        coverage = _coverage(
            xyz, reference.footprint,
            float(config["diagnostics"]["coverage_grid_m"]),
            float(config["diagnostics"]["coverage_radius_m"]),
        )
        result.update({
            "status": "COMPLETED_SHARED_VIEW_SURFACE_COMPARISON",
            "consensus_roof_point_count": int(len(xyz)),
            "view_count_distribution": {
                "minimum": int(np.min(view_count)), "median": float(np.median(view_count)),
                "p95": float(np.quantile(view_count, 0.95)), "maximum": int(np.max(view_count)),
            },
            "footprint_roof_coverage": coverage,
            "roof_points": file_record(points_path, output_root),
        })
        pc = o3d.geometry.PointCloud()
        pc.points = o3d.utility.Vector3dVector(xyz)
        pc.normals = o3d.utility.Vector3dVector(normals)
        pc.colors = o3d.utility.Vector3dVector(np.clip(colors, 0, 1))
        poisson, _density = o3d.geometry.TriangleMesh.create_from_point_cloud_poisson(
            pc, depth=int(surf_cfg["poisson_depth"]), n_threads=2,
        )
        poisson = _crop_mesh(
            poisson, reference.footprint, xyz, float(surf_cfg["footprint_buffer_m"]),
            float(surf_cfg["mesh_crop_vertical_margin_m"]),
        )
        poisson_path = building_root / "poisson_same_evidence_roof_mesh_v1.ply"
        _write_mesh(poisson_path, poisson)
        volume = o3d.pipelines.integration.ScalableTSDFVolume(
            voxel_length=float(surf_cfg["tsdf_voxel_m"]),
            sdf_trunc=float(surf_cfg["tsdf_truncation_m"]),
            color_type=o3d.pipelines.integration.TSDFVolumeColorType.RGB8,
        )
        integrated_views = 0
        integrated_pixels = 0
        for record in view_records[stable_id]:
            selected = np.isin(record["packed"], kept_keys, assume_unique=False)
            if not np.any(selected):
                continue
            h, w = record["shape"]
            depth_image = np.zeros((h, w), dtype=np.float32)
            flat = record["valid_flat_indices"][selected]
            depth_image.reshape(-1)[flat] = record["depth"].reshape(-1)[flat]
            color_image = np.rint(np.clip(record["rgb"], 0, 1) * 255).astype(np.uint8)
            rgbd = o3d.geometry.RGBDImage.create_from_color_and_depth(
                o3d.geometry.Image(np.ascontiguousarray(color_image)),
                o3d.geometry.Image(np.ascontiguousarray(depth_image)),
                depth_scale=1.0,
                depth_trunc=float(surf_cfg["depth_max_m"]),
                convert_rgb_to_intensity=False,
            )
            Kc = record["K"]
            intrinsic = o3d.camera.PinholeCameraIntrinsic(
                w, h, float(Kc[0, 0]), float(Kc[1, 1]), float(Kc[0, 2]), float(Kc[1, 2])
            )
            volume.integrate(rgbd, intrinsic, record["extrinsic"])
            integrated_views += 1
            integrated_pixels += int(np.count_nonzero(selected))
        tsdf = volume.extract_triangle_mesh()
        origin = origins[stable_id]
        if len(tsdf.vertices):
            tsdf.vertices = o3d.utility.Vector3dVector(np.asarray(tsdf.vertices) + origin)
            tsdf = _crop_mesh(
                tsdf, reference.footprint, xyz, float(surf_cfg["footprint_buffer_m"]),
                float(surf_cfg["mesh_crop_vertical_margin_m"]),
            )
        tsdf_path = building_root / "tsdf_roof_mesh_v1.ply"
        _write_mesh(tsdf_path, tsdf)
        result.update({
            "poisson": {
                "mesh": file_record(poisson_path, output_root),
                "quality": _mesh_evidence_stats(poisson, xyz, thresholds),
            },
            "tsdf": {
                "mesh": file_record(tsdf_path, output_root),
                "integrated_view_count": int(integrated_views),
                "integrated_consensus_pixel_count": int(integrated_pixels),
                "voxel_m": float(surf_cfg["tsdf_voxel_m"]),
                "truncation_m": float(surf_cfg["tsdf_truncation_m"]),
                "quality": _mesh_evidence_stats(tsdf, xyz, thresholds),
            },
        })
        write_new(building_root / "result_v1.json", canonical_json_bytes(result))
        results.append(result)
    control = {
        "schema": "jointbuildgs.c3_shared_view_roof_poisson_tsdf.v1",
        "status": "COMPLETE_NO_TRAINING",
        "condition_id": condition_id,
        "checkpoint_sha256": sha256_file(checkpoint)[1],
        "shared_view_plan": plan,
        "unique_rendered_view_count": len(rendered_views),
        "rendered_views": rendered_views,
        "gaussian_semantic_scale_diagnostics": gaussian_stats,
        "building_results": results,
        "peak_gpu_memory_mib": int(torch.cuda.max_memory_allocated() / (1024 * 1024)),
        "gs_training_invocations": 0,
        "roofer_invocations": 0,
        "g2_invocations": 0,
        "metric_recomputations": 0,
        "scientific_verdict": None,
    }
    write_new(output_root / f"conditions/{condition_id}/control/extraction_complete_v1.json", canonical_json_bytes(control))
    del model
    torch.cuda.empty_cache()
    return control


def run(output_root: Path, artifact_root: Path, repo_root: Path, device: str, source_commit: str) -> dict[str, Any]:
    config = load_config()
    validate_config(config)
    if output_root.exists():
        if output_root.is_symlink() or any(output_root.iterdir()):
            raise RuntimeError(f"add-once output namespace exists/non-empty: {output_root}")
    else:
        output_root.mkdir(parents=True)
    if len(source_commit) != 40 or any(char not in "0123456789abcdef" for char in source_commit):
        raise RuntimeError("source commit must be a lowercase 40-character SHA-1")
    write_new(output_root / "control/source_commit.txt", (source_commit + "\n").encode("ascii"))
    source = config["source"]
    v13_root = resolve_artifact(artifact_root, source["v13_relative_root"], "v13 source")
    require_regular(v13_root / "artifact_manifest_v1.json", "v13 manifest")
    lod2 = require_regular(resolve_artifact(artifact_root, source["lod2_relative_path"], "LoD2"), "LoD2")
    references = load_building_references(lod2, config["scope"]["building_ids"])
    data_root = resolve_artifact(artifact_root, source["colmap_relative_root"], "COLMAP root")
    dataset = ColmapDataset(
        data_root,
        downscale=float(config["shared_view_plan"]["render_downscale"]),
        load_depth=False, load_normal=False, load_semantic=False,
        visible_views=_visible_names(config, repo_root),
    )
    plan = shared_view_plan(dataset, references, config, v13_root)
    for stable_id, rows in plan.items():
        ground = _current_ground_z(v13_root, stable_id)
        for row in rows:
            row["current_ground_z"] = ground
    write_new(output_root / "control/shared_view_plan_v1.json", canonical_json_bytes({
        "schema": "jointbuildgs.c3_shared_view_plan.v1",
        "selection": config["shared_view_plan"]["selection"],
        "plan": plan,
        "same_view_names_across_conditions": True,
        "scientific_verdict": None,
    }))
    controls = []
    for condition_id in config["scope"]["condition_ids"]:
        spec = source["checkpoints"][condition_id]
        checkpoint = require_regular(resolve_artifact(artifact_root, spec["relative_path"], condition_id), condition_id)
        size, digest = sha256_file(checkpoint)
        if size != int(spec["bytes"]) or digest != spec["sha256"]:
            raise RuntimeError(f"checkpoint identity drift: {condition_id}")
        controls.append(extract_condition(
            condition_id=condition_id, checkpoint=checkpoint, output_root=output_root,
            dataset=dataset, plan=plan, references=references, config=config, device=device,
        ))
    body = {
        "schema": "jointbuildgs.c3_tsdf_roof_extraction_pair.v1",
        "status": "COMPLETE_TWO_CONDITIONS",
        "task_id": config["task_id"],
        "source_commit": source_commit,
        "condition_ids": list(config["scope"]["condition_ids"]),
        "shared_view_plan_identical": True,
        "poisson_tsdf_same_rendered_roof_evidence": True,
        "condition_controls": [
            file_record(output_root / f"conditions/{row['condition_id']}/control/extraction_complete_v1.json", output_root)
            for row in controls
        ],
        "execution_counters": {
            "gs_training_invocations": 0,
            "checkpoint_render_extractions": 2,
            "roofer_invocations": 0,
            "g2_invocations": 0,
            "metric_recomputations": 0,
            "c4_c5_accesses": 0,
        },
        "scientific_verdict": None,
    }
    write_new(output_root / "control/extraction_pair_complete_v1.json", canonical_json_bytes(body))
    return body


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--source-commit", required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.output_root, args.artifact_root, args.repo_root, args.device, args.source_commit), ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
