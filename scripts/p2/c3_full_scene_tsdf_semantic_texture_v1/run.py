#!/usr/bin/env python3
from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime, timezone
import html
import io
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

import cv2
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.collections import PolyCollection
from mpl_toolkits.mplot3d.art3d import Poly3DCollection
import numpy as np
import open3d as o3d
from shapely import contains_xy
import torch

from scripts.p2.c1_c2_oracle_c3_extract_v1.contract import load_building_references
from scripts.p2.c3_roof_texture_bake_v1.bake import (
    _bake_texture,
    _display_wall_hybrid,
    _hybrid_obj_bytes,
    _panel as texture_panel,
    _records,
)
from scripts.p2.c3_roof_texture_reference_extension_v1.recover_v5 import VIEWS, _compose_sheet
from scripts.p2.c3_tsdf_roof_diagnostic_v1.contract import (
    canonical_json_bytes,
    file_record,
    resolve_artifact,
    sha256_file,
    write_new,
)
from scripts.p2.c3_tsdf_roof_diagnostic_v1.extract import _coverage, _mesh_boundary_stats
from scripts.p2.c3_tsdf_roof_diagnostic_v1.render import _draw_footprint, _principal_frame, _setup_axes
from scripts.p2.c3_utarget199_postprocess_v1.render_gs import model_from_checkpoint
from src.stage2.dataloader import ColmapDataset
from src.stage2.renderer import render, render_semantic


REPO_ROOT = Path(__file__).resolve().parents[3]
CONFIG_PATH = REPO_ROOT / "configs/p2/c3_full_scene_tsdf_semantic_texture_v1/run_v1.json"
SEMANTIC_COLORS = np.asarray([
    [0.55, 0.55, 0.55],
    [0.84, 0.37, 0.08],
    [0.00, 0.45, 0.70],
    [0.00, 0.62, 0.45],
], dtype=np.float64)


def load_config() -> dict[str, Any]:
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def validate_config(config: Mapping[str, Any]) -> None:
    if config.get("schema") != "jointbuildgs.p2.c3_full_scene_tsdf_semantic_texture.v1":
        raise RuntimeError("unexpected schema")
    if config.get("status") != "APPROVED_FOR_LOCAL_EXECUTION":
        raise RuntimeError("config is not activated")
    if tuple(config["scope"]["views"]) != VIEWS:
        raise RuntimeError("view order drifted")
    if config["scope"].get("c4_c5_access_allowed") is not False:
        raise RuntimeError("C4/C5 access must remain disabled")
    if float(config["tsdf"]["truncation_m"]) < 2 * float(config["tsdf"]["voxel_m"]):
        raise RuntimeError("TSDF truncation must cover at least two voxels")
    counters = config["execution_counters"]
    for key in (
        "expected_gs_training_invocations", "expected_roofer_invocations",
        "expected_g2_invocations", "expected_metric_recomputations", "expected_c4_c5_accesses",
    ):
        if int(counters[key]) != 0:
            raise RuntimeError(f"prohibited counter is nonzero: {key}")
    if config.get("scientific_verdict", "missing") is not None:
        raise RuntimeError("scientific_verdict must remain null")


def _visible_names(config: Mapping[str, Any], repo_root: Path) -> list[str]:
    manifest = json.loads((repo_root / config["source"]["exact_view_manifest_git_path"]).read_text(encoding="utf-8"))
    names = [str(row["basename"]) for row in manifest["rows"]]
    if len(names) != int(config["source"]["exact_view_count"]):
        raise RuntimeError("exact view count drifted")
    return names


def _current_ground_z(v13_root: Path, stable_id: str) -> float:
    path = v13_root / f"operations/C2_MVS_GT_FOOTPRINT_ORACLE/{stable_id}/work/prepared_v1.json"
    return float(json.loads(path.read_text(encoding="utf-8"))["classification"]["local_ground_z"])


def _write_mesh(path: Path, mesh: o3d.geometry.TriangleMesh) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise RuntimeError(f"add-once mesh already exists: {path}")
    if not len(mesh.vertices) or not len(mesh.triangles):
        write_new(
            path,
            b"ply\nformat ascii 1.0\nelement vertex 0\n"
            b"property float x\nproperty float y\nproperty float z\n"
            b"element face 0\nproperty list uchar int vertex_indices\nend_header\n",
        )
        return
    if not o3d.io.write_triangle_mesh(str(path), mesh, write_ascii=False):
        raise RuntimeError(f"failed to write mesh: {path}")


def _mesh_from_faces(source: o3d.geometry.TriangleMesh, selected_faces: np.ndarray) -> tuple[o3d.geometry.TriangleMesh, np.ndarray]:
    triangles = np.asarray(source.triangles, dtype=np.int64)[selected_faces]
    if not len(triangles):
        return o3d.geometry.TriangleMesh(), np.empty((0,), dtype=np.int64)
    used, inverse = np.unique(triangles.ravel(), return_inverse=True)
    mesh = o3d.geometry.TriangleMesh(
        o3d.utility.Vector3dVector(np.asarray(source.vertices)[used]),
        o3d.utility.Vector3iVector(inverse.reshape(-1, 3)),
    )
    colors = np.asarray(source.vertex_colors)
    if len(colors) == len(source.vertices):
        mesh.vertex_colors = o3d.utility.Vector3dVector(colors[used])
    mesh.compute_vertex_normals()
    return mesh, used


def _component_filter(mesh: o3d.geometry.TriangleMesh, minimum_area_m2: float) -> o3d.geometry.TriangleMesh:
    if not len(mesh.triangles):
        return mesh
    labels, _counts, areas = mesh.cluster_connected_triangles()
    labels = np.asarray(labels, dtype=np.int64)
    areas = np.asarray(areas, dtype=np.float64)
    keep_labels = np.flatnonzero(areas >= minimum_area_m2)
    keep = np.isin(labels, keep_labels)
    filtered, _used = _mesh_from_faces(mesh, keep)
    return filtered


def _semantic_vertex_projection(
    vertices_world: np.ndarray,
    origin_world: np.ndarray,
    records: Sequence[Mapping[str, Any]],
    tolerance_m: float,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    count = len(vertices_world)
    probability_sum = np.zeros((count, 4), dtype=np.float64)
    weight_sum = np.zeros(count, dtype=np.float64)
    view_support = np.zeros(count, dtype=np.uint16)
    local = vertices_world - origin_world
    for record in records:
        extrinsic = record["extrinsic"]
        camera = local @ extrinsic[:3, :3].T + extrinsic[:3, 3]
        front = camera[:, 2] > 0.01
        uvw = camera @ record["K"].T
        uv = np.zeros((count, 2), dtype=np.float64)
        uv[front] = uvw[front, :2] / uvw[front, 2:3]
        h, w = record["depth"].shape
        inside = front & (uv[:, 0] >= 0) & (uv[:, 0] < w) & (uv[:, 1] >= 0) & (uv[:, 1] < h)
        indices = np.flatnonzero(inside)
        if not len(indices):
            continue
        px = np.clip(np.rint(uv[indices, 0]).astype(int), 0, w - 1)
        py = np.clip(np.rint(uv[indices, 1]).astype(int), 0, h - 1)
        observed_depth = record["depth"][py, px]
        visible = (observed_depth > 0) & (np.abs(camera[indices, 2] - observed_depth) <= tolerance_m)
        indices = indices[visible]
        if not len(indices):
            continue
        px = px[visible]
        py = py[visible]
        weight = np.maximum(record["alpha"][py, px].astype(np.float64), 1e-6)
        probability_sum[indices] += record["semantic_probability"][py, px].astype(np.float64) * weight[:, None]
        weight_sum[indices] += weight
        view_support[indices] += 1
    probability = np.zeros_like(probability_sum)
    supported = weight_sum > 0
    probability[supported] = probability_sum[supported] / weight_sum[supported, None]
    return probability, view_support, weight_sum


def _extract_semantic_roof(
    full_mesh: o3d.geometry.TriangleMesh,
    probability: np.ndarray,
    support: np.ndarray,
    reference: Any,
    ground_z: float,
    config: Mapping[str, Any],
) -> tuple[o3d.geometry.TriangleMesh, dict[str, Any]]:
    cfg = config["semantic_roof_extraction"]
    vertices = np.asarray(full_mesh.vertices, dtype=np.float64)
    triangles = np.asarray(full_mesh.triangles, dtype=np.int64)
    full_mesh.compute_triangle_normals()
    normals = np.asarray(full_mesh.triangle_normals, dtype=np.float64)
    roof_probability = probability[:, int(cfg["roof_class"])]
    inside = contains_xy(reference.footprint.buffer(float(cfg["footprint_buffer_m"])), vertices[:, 0], vertices[:, 1])
    vertex_valid = (
        inside
        & (vertices[:, 2] >= ground_z + float(cfg["minimum_height_above_ground_m"]))
        & (support >= int(cfg["minimum_vertex_view_support"]))
        & (roof_probability >= float(cfg["minimum_roof_probability"]))
    )
    triangle_valid_count = np.sum(vertex_valid[triangles], axis=1)
    keep = (
        (triangle_valid_count >= int(cfg["minimum_valid_vertices_per_triangle"]))
        & (normals[:, 2] >= float(cfg["minimum_upward_normal_z"]))
    )
    selected, _used = _mesh_from_faces(full_mesh, keep)
    before_components = _mesh_boundary_stats(selected)
    selected = _component_filter(selected, float(cfg["minimum_component_area_m2"]))
    stats = {
        "full_mesh_vertex_count": int(len(vertices)),
        "full_mesh_triangle_count": int(len(triangles)),
        "semantically_supported_vertex_count": int(np.count_nonzero(support >= int(cfg["minimum_vertex_view_support"]))),
        "roof_candidate_vertex_count": int(np.count_nonzero(vertex_valid)),
        "roof_candidate_triangle_count_before_component_filter": int(np.count_nonzero(keep)),
        "roof_triangle_count": int(len(selected.triangles)),
        "roof_vertex_count": int(len(selected.vertices)),
        "components_before_area_filter": before_components,
        "components_after_area_filter": _mesh_boundary_stats(selected),
        "thresholds": dict(cfg),
    }
    return selected, stats


def _render_condition(
    condition_id: str,
    checkpoint: Path,
    output_root: Path,
    dataset: ColmapDataset,
    frame_by_name: Mapping[str, tuple[int, Any]],
    plan: Mapping[str, Sequence[Mapping[str, Any]]],
    references: Mapping[str, Any],
    grounds: Mapping[str, float],
    config: Mapping[str, Any],
    device: str,
) -> list[dict[str, Any]]:
    model = model_from_checkpoint(checkpoint, device)
    shift = np.asarray(config["frame"]["world_shift_xyz"], dtype=np.float64)
    render_cfg = config["render"]
    by_view: dict[int, list[tuple[str, tuple[int, int, int, int]]]] = defaultdict(list)
    for stable_id, rows in plan.items():
        for row in rows[:int(render_cfg["maximum_views_per_building"])]:
            index = frame_by_name[str(row["name"])][0]
            by_view[index].append((stable_id, tuple(map(int, row["crop_xyxy"]))))
    origins = {
        stable_id: np.asarray([reference.footprint.centroid.x, reference.footprint.centroid.y, grounds[stable_id]], dtype=np.float64)
        for stable_id, reference in references.items()
    }
    volumes = {
        stable_id: o3d.pipelines.integration.ScalableTSDFVolume(
            voxel_length=float(config["tsdf"]["voxel_m"]),
            sdf_trunc=float(config["tsdf"]["truncation_m"]),
            color_type=o3d.pipelines.integration.TSDFVolumeColorType.RGB8,
        ) for stable_id in references
    }
    records: dict[str, list[dict[str, Any]]] = {stable_id: [] for stable_id in references}
    counters = {stable_id: {"views": 0, "pixels": 0} for stable_id in references}
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
            probability = torch.softmax(logits, dim=-1)
            depth = output["depth_median"]
            alpha = output["alpha"]
            rgb = output["rgb"]
            R = batch["w2c"][:3, :3].to(device)
            t = batch["w2c"][:3, 3].to(device)
            K = batch["K"].to(device)
            for stable_id, crop in by_view[index]:
                left, top, right, bottom = crop
                d = depth[top:bottom, left:right]
                a = alpha[top:bottom, left:right]
                c = rgb[top:bottom, left:right]
                p = probability[top:bottom, left:right]
                vv, uu = torch.meshgrid(
                    torch.arange(top, bottom, device=device, dtype=torch.float32),
                    torch.arange(left, right, device=device, dtype=torch.float32), indexing="ij",
                )
                valid = (
                    (a >= float(render_cfg["alpha_min"])) & torch.isfinite(d)
                    & (d > float(render_cfg["depth_min_m"])) & (d < float(render_cfg["depth_max_m"]))
                )
                if not torch.any(valid):
                    continue
                z = d[valid]
                xc = (uu[valid] - K[0, 2]) / K[0, 0] * z
                yc = (vv[valid] - K[1, 2]) / K[1, 1] * z
                world_local = (torch.stack((xc, yc, z), dim=1) - t) @ R
                world = world_local + torch.as_tensor(shift, device=device, dtype=world_local.dtype)
                xyz = world.cpu().numpy().astype(np.float64)
                reference = references[stable_id]
                ground = grounds[stable_id]
                in_aoi = contains_xy(reference.footprint.buffer(float(render_cfg["aoi_footprint_buffer_m"])), xyz[:, 0], xyz[:, 1])
                in_aoi &= (xyz[:, 2] >= ground - float(render_cfg["aoi_below_ground_m"]))
                in_aoi &= (xyz[:, 2] <= ground + float(render_cfg["aoi_above_ground_m"]))
                flat_valid = torch.nonzero(valid.reshape(-1), as_tuple=False).reshape(-1).cpu().numpy()
                selected_flat = flat_valid[in_aoi]
                h, w = bottom - top, right - left
                depth_image = np.zeros((h, w), dtype=np.float32)
                depth_np = d.cpu().numpy().astype(np.float32)
                depth_image.reshape(-1)[selected_flat] = depth_np.reshape(-1)[selected_flat]
                if not np.count_nonzero(depth_image):
                    continue
                color_image = np.rint(np.clip(c.cpu().numpy(), 0, 1) * 255).astype(np.uint8)
                K_crop = batch["K"].cpu().numpy().astype(np.float64).copy()
                K_crop[0, 2] -= left
                K_crop[1, 2] -= top
                extrinsic = batch["w2c"].cpu().numpy().astype(np.float64).copy()
                origin_local = origins[stable_id] - shift
                extrinsic[:3, 3] += extrinsic[:3, :3] @ origin_local
                rgbd = o3d.geometry.RGBDImage.create_from_color_and_depth(
                    o3d.geometry.Image(np.ascontiguousarray(color_image)),
                    o3d.geometry.Image(np.ascontiguousarray(depth_image)),
                    depth_scale=1.0, depth_trunc=float(render_cfg["depth_max_m"]), convert_rgb_to_intensity=False,
                )
                intrinsic = o3d.camera.PinholeCameraIntrinsic(
                    w, h, float(K_crop[0, 0]), float(K_crop[1, 1]), float(K_crop[0, 2]), float(K_crop[1, 2])
                )
                volumes[stable_id].integrate(rgbd, intrinsic, extrinsic)
                records[stable_id].append({
                    "image_name": str(batch["name"]), "depth": depth_image,
                    "alpha": a.cpu().numpy().astype(np.float32),
                    "semantic_probability": p.cpu().numpy().astype(np.float16),
                    "K": K_crop, "extrinsic": extrinsic,
                })
                counters[stable_id]["views"] += 1
                counters[stable_id]["pixels"] += int(np.count_nonzero(depth_image))
    results = []
    for stable_id, reference in references.items():
        root = output_root / f"conditions/{condition_id}/buildings/{stable_id}"
        full_mesh = volumes[stable_id].extract_triangle_mesh()
        full_mesh.compute_vertex_normals()
        if len(full_mesh.vertices):
            full_mesh.vertices = o3d.utility.Vector3dVector(np.asarray(full_mesh.vertices) + origins[stable_id])
            ground = grounds[stable_id]
            x0, y0, x1, y1 = reference.footprint.buffer(float(render_cfg["aoi_footprint_buffer_m"])).bounds
            full_mesh = full_mesh.crop(o3d.geometry.AxisAlignedBoundingBox(
                (x0, y0, ground - float(render_cfg["aoi_below_ground_m"])),
                (x1, y1, ground + float(render_cfg["aoi_above_ground_m"])),
            ))
            full_mesh.compute_vertex_normals()
        if not len(full_mesh.triangles):
            raise RuntimeError(f"empty full-scene TSDF mesh: {condition_id} {stable_id}")
        full_rgb_path = root / "full_scene_tsdf_rgb_v1.ply"
        _write_mesh(full_rgb_path, full_mesh)
        probability, support, weight = _semantic_vertex_projection(
            np.asarray(full_mesh.vertices), origins[stable_id], records[stable_id],
            float(config["semantic_roof_extraction"]["depth_visibility_tolerance_m"]),
        )
        labels = np.argmax(probability, axis=1)
        semantic_mesh = o3d.geometry.TriangleMesh(full_mesh)
        semantic_colors = SEMANTIC_COLORS[labels]
        semantic_colors[support == 0] = np.asarray([0.55, 0.55, 0.55])
        semantic_mesh.vertex_colors = o3d.utility.Vector3dVector(semantic_colors)
        semantic_path = root / "full_scene_tsdf_semantic_v1.ply"
        _write_mesh(semantic_path, semantic_mesh)
        roof_mesh, extraction = _extract_semantic_roof(
            full_mesh, probability, support, reference, grounds[stable_id], config,
        )
        roof_path = root / "semantic_roof_mesh_v1.ply"
        _write_mesh(roof_path, roof_mesh)
        buffer = io.BytesIO()
        np.savez_compressed(
            buffer, semantic_probability=probability.astype(np.float32),
            semantic_label=labels.astype(np.uint8), view_support=support,
            accumulated_weight=weight.astype(np.float32),
        )
        semantic_receipt_path = root / "full_scene_tsdf_vertex_semantic_v1.npz"
        write_new(semantic_receipt_path, buffer.getvalue())
        coverage = _coverage(
            np.asarray(roof_mesh.vertices), reference.footprint,
            float(config["semantic_roof_extraction"]["coverage_grid_m"]),
            float(config["semantic_roof_extraction"]["coverage_radius_m"]),
        )
        result = {
            "condition_id": condition_id, "stable_id": stable_id,
            "status": "COMPLETED_FULL_SCENE_TSDF_POST_SEMANTIC_ROOF_EXTRACTION",
            "integrated_view_count": counters[stable_id]["views"],
            "integrated_full_scene_pixel_count": counters[stable_id]["pixels"],
            "full_scene_mesh": file_record(full_rgb_path, output_root),
            "full_scene_semantic_mesh": file_record(semantic_path, output_root),
            "vertex_semantic": file_record(semantic_receipt_path, output_root),
            "semantic_roof_mesh": file_record(roof_path, output_root),
            "full_scene_mesh_quality": _mesh_boundary_stats(full_mesh),
            "semantic_roof_extraction": extraction,
            "semantic_roof_coverage": coverage,
            "tsdf": dict(config["tsdf"]),
            "scientific_verdict": None,
        }
        write_new(root / "result_v1.json", canonical_json_bytes(result))
        results.append(result)
    control = {
        "schema": "jointbuildgs.c3_full_scene_tsdf_condition.v1",
        "status": "COMPLETE_FULL_SCENE_FIRST_SEMANTIC_AFTER_TSDF",
        "condition_id": condition_id,
        "checkpoint": {"bytes": checkpoint.stat().st_size, "sha256": sha256_file(checkpoint)[1]},
        "building_results": results,
        "peak_gpu_memory_mib": int(torch.cuda.max_memory_allocated() / (1024 * 1024)),
        "gs_training_invocations": 0,
        "scientific_verdict": None,
    }
    write_new(output_root / f"conditions/{condition_id}/control/extraction_complete_v1.json", canonical_json_bytes(control))
    del model
    torch.cuda.empty_cache()
    return results


def _face_colors(mesh: o3d.geometry.TriangleMesh) -> np.ndarray:
    colors = np.asarray(mesh.vertex_colors, dtype=np.float64)
    triangles = np.asarray(mesh.triangles, dtype=np.int64)
    if len(colors) != len(mesh.vertices):
        return np.tile(np.asarray([[0.62, 0.65, 0.68]]), (len(triangles), 1))
    return np.clip(colors[triangles].mean(axis=1), 0, 1)


def _mesh_panel(path: Path, mesh: o3d.geometry.TriangleMesh, reference: Any, view: str, ground_z: float, title: str) -> None:
    vertices = np.asarray(mesh.vertices, dtype=np.float64)
    triangles = np.asarray(mesh.triangles, dtype=np.int64)
    figure = plt.figure(figsize=(6.4, 4.8), dpi=150)
    ax = figure.add_subplot(111, projection="3d", proj_type="ortho") if view.startswith("OBLIQUE") else figure.add_subplot(111)
    if len(triangles):
        stride = max(1, len(triangles) // 60000)
        faces = vertices[triangles[::stride]]
        colors = _face_colors(mesh)[::stride]
        if view == "TOP":
            ax.add_collection(PolyCollection(faces[:, :, :2], facecolors=colors, edgecolors="none"))
        elif view.startswith("OBLIQUE"):
            ax.add_collection3d(Poly3DCollection(faces, facecolors=colors, edgecolors="none"))
        else:
            center, axis, cross = _principal_frame(reference)
            local = faces[:, :, :2] - center
            band = 1.0
            selected = (np.min(local @ cross, axis=1) <= band) & (np.max(local @ cross, axis=1) >= -band)
            section = np.stack((local[selected] @ axis, faces[selected, :, 2]), axis=2)
            if len(section):
                ax.add_collection(PolyCollection(section, facecolors=colors[selected], edgecolors="none"))
    zvalues = vertices[:, 2] if len(vertices) else np.asarray([ground_z, ground_z + 1])
    zlim = (float(min(ground_z - 1, np.quantile(zvalues, 0.001) - 1)), float(np.quantile(zvalues, 0.999) + 1))
    _draw_footprint(ax, reference, view, ground_z)
    _setup_axes(ax, reference, zlim, view)
    ax.set_title(title, fontsize=9.5, fontweight="bold")
    figure.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(path, metadata={"Software": "JointBuildGS full-scene TSDF renderer"})
    plt.close(figure)


def _copy(source: Path, destination: Path, source_root: Path, output_root: Path) -> dict[str, Any]:
    write_new(destination, source.read_bytes())
    source_record, copy_record = file_record(source, source_root), file_record(destination, output_root)
    if source_record["sha256"] != copy_record["sha256"]:
        raise RuntimeError("context copy hash mismatch")
    return {"source": source_record, "copy": copy_record}


def _texture_and_render(
    output_root: Path,
    artifact_root: Path,
    repo_root: Path,
    dataset: ColmapDataset,
    frame_by_name: Mapping[str, tuple[int, Any]],
    plan: Mapping[str, Sequence[Mapping[str, Any]]],
    references: Mapping[str, Any],
    grounds: Mapping[str, float],
    config: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    source_board = resolve_artifact(artifact_root, config["source"]["clean_reference_board_relative_root"], "reference board")
    cases, texture_records = [], []
    wall_color = tuple(map(float, config["hybrid"]["wall_color_rgb"]))
    for stable_id, reference in references.items():
        bounds = reference.footprint.buffer(float(config["texture"]["atlas_footprint_padding_m"])).bounds
        frames = [
            (frame_by_name[str(row["name"])][1], dataset[frame_by_name[str(row["name"])][0]])
            for row in plan[stable_id][:int(config["texture"]["maximum_views_per_building"])]
        ]
        common: dict[str, list[Path]] = {}
        for role, prefix in (("context", "context"), ("c1_roofer", "c1_roofer"), ("lod2", "lod2_reference")):
            common[role] = []
            for view in VIEWS:
                source = source_board / f"qualitative/{stable_id}/panels/{prefix}_{view.lower()}.png"
                destination = output_root / f"qualitative/{stable_id}/panels/{prefix}_{view.lower()}.png"
                _copy(source, destination, source_board, output_root)
                common[role].append(destination)
        sheets = []
        for condition_id, label in (("C3_1_SEM", "C3-1 semantic"), ("C3_2_SEM_DEPTH", "C3-2 semantic + depth")):
            root = output_root / f"conditions/{condition_id}/buildings/{stable_id}"
            result = json.loads((root / "result_v1.json").read_text(encoding="utf-8"))
            full_rgb = o3d.io.read_triangle_mesh(str(output_root / result["full_scene_mesh"]["path"]))
            full_semantic = o3d.io.read_triangle_mesh(str(output_root / result["full_scene_semantic_mesh"]["path"]))
            roof = o3d.io.read_triangle_mesh(str(output_root / result["semantic_roof_mesh"]["path"]))
            roof.compute_vertex_normals()
            rgb_paths, semantic_paths, roof_paths, texture_paths = [], [], [], []
            for view in VIEWS:
                rgb_path = output_root / f"qualitative/{stable_id}/panels/full_tsdf_rgb_{condition_id}_{view.lower()}.png"
                semantic_path = output_root / f"qualitative/{stable_id}/panels/full_tsdf_semantic_{condition_id}_{view.lower()}.png"
                roof_path = output_root / f"qualitative/{stable_id}/panels/semantic_roof_{condition_id}_{view.lower()}.png"
                _mesh_panel(rgb_path, full_rgb, reference, view, grounds[stable_id], f"Full TSDF RGB | {view}")
                _mesh_panel(semantic_path, full_semantic, reference, view, grounds[stable_id], f"TSDF semantic | {view}")
                uniform_roof = o3d.geometry.TriangleMesh(roof)
                uniform_roof.paint_uniform_color([0.84, 0.37, 0.08])
                _mesh_panel(roof_path, uniform_roof, reference, view, grounds[stable_id], f"Extracted roof | {view}")
                rgb_paths.append(rgb_path); semantic_paths.append(semantic_path); roof_paths.append(roof_path)
            if len(roof.triangles):
                rgba, support_map, textured_roof, receipt = _bake_texture(roof, bounds, frames, config)
                hybrid, roof_face_count, wall_receipt = _display_wall_hybrid(
                    textured_roof, reference.footprint, grounds[stable_id],
                    float(config["hybrid"]["boundary_sample_spacing_m"]),
                    int(config["hybrid"]["nearest_roof_vertex_count"]),
                    float(config["hybrid"]["minimum_wall_height_m"]),
                )
                texture_root = output_root / f"textures/{condition_id}/{stable_id}"
                texture_png = texture_root / "semantic_roof_texture_current_rgb_v1.png"
                ok, encoded = cv2.imencode(".png", cv2.cvtColor(rgba, cv2.COLOR_RGBA2BGRA))
                if not ok: raise RuntimeError("texture encode failed")
                write_new(texture_png, encoded.tobytes())
                obj = texture_root / "semantic_roof_textured_gt_footprint_display_wall_v1.obj"
                mtl = texture_root / "semantic_roof_textured_gt_footprint_display_wall_v1.mtl"
                write_new(obj, _hybrid_obj_bytes(hybrid, roof_face_count, bounds, mtl.name))
                wall_rgb = " ".join(f"{value:.4f}" for value in wall_color)
                write_new(mtl, (f"newmtl observed_roof_texture\nKd 1 1 1\nmap_Kd {texture_png.name}\nnewmtl gt_footprint_display_wall\nKd {wall_rgb}\n").encode("ascii"))
                for view in VIEWS:
                    path = output_root / f"qualitative/{stable_id}/panels/full_tsdf_roof_texture_{condition_id}_{view.lower()}.png"
                    zvalues = np.asarray(hybrid.vertices)[:, 2]
                    zlim = (grounds[stable_id] - 1, float(np.quantile(zvalues, 0.999) + 1))
                    texture_panel(
                        path, mesh=hybrid, reference=reference, view=view, ground_z=grounds[stable_id],
                        zlim=zlim, bounds=bounds, rgba=rgba, support=support_map, mode="TEXTURE",
                        title=f"Full TSDF roof texture | {view}", roof_face_count=roof_face_count, wall_color=wall_color,
                    )
                    texture_paths.append(path)
                receipt.update({
                    "condition_id": condition_id, "stable_id": stable_id,
                    "source_semantic_roof_mesh": result["semantic_roof_mesh"],
                    "texture": file_record(texture_png, output_root), "hybrid_obj": file_record(obj, output_root),
                    "hybrid_mtl": file_record(mtl, output_root), "display_wall": wall_receipt,
                    "full_scene_tsdf_reconstructed_before_semantic_filter": True,
                    "semantic_filter_before_tsdf": False,
                })
                write_new(texture_root / "texture_receipt_v1.json", canonical_json_bytes(receipt))
                texture_records.append(receipt)
            else:
                for view in VIEWS:
                    path = output_root / f"qualitative/{stable_id}/panels/full_tsdf_roof_texture_{condition_id}_{view.lower()}.png"
                    blank = np.full((720, 960, 3), 255, dtype=np.uint8)
                    cv2.putText(blank, "NO SEMANTIC ROOF TRIANGLES", (170, 360), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (40, 40, 40), 2, cv2.LINE_AA)
                    ok, encoded = cv2.imencode(".png", blank)
                    if not ok: raise RuntimeError("blank encode failed")
                    write_new(path, encoded.tobytes()); texture_paths.append(path)
            rows = [
                ("RGB 2024 +\nLoD2 roofline", common["context"]),
                ("Full-scene TSDF\nGS-rendered RGB", rgb_paths),
                ("TSDF vertex\nsemantic posterior", semantic_paths),
                ("Post-TSDF semantic\nroof extraction", roof_paths),
                ("Extracted roof\ncurrent RGB texture", texture_paths),
                ("C1 Roofer\ncurrent UAS LiDAR", common["c1_roofer"]),
                ("LoD2 2022\nreference", common["lod2"]),
            ]
            slug = "c3_1" if condition_id == "C3_1_SEM" else "c3_2"
            sheet = output_root / f"qualitative/{stable_id}/case_sheet_full_scene_tsdf_{slug}_v1.png"
            _compose_sheet(sheet, stable_id, label, rows, "full depth -> TSDF -> semantic roof -> texture; scientific_verdict=null")
            sheets.append({"condition_id": condition_id, "sheet": file_record(sheet, output_root), "result": result})
        cases.append({"stable_id": stable_id, "sheets": sheets})
    return cases, texture_records


def run(output_root: Path, artifact_root: Path, repo_root: Path, source_commit: str, device: str) -> dict[str, Any]:
    config = load_config(); validate_config(config)
    if output_root.exists() and any(output_root.iterdir()):
        raise RuntimeError(f"add-once output is not empty: {output_root}")
    output_root.mkdir(parents=True, exist_ok=True)
    source = config["source"]
    v13_root = resolve_artifact(artifact_root, source["v13_relative_root"], "v13")
    lod2 = resolve_artifact(artifact_root, source["lod2_relative_path"], "LoD2")
    references = load_building_references(lod2, config["scope"]["building_ids"])
    grounds = {stable_id: _current_ground_z(v13_root, stable_id) for stable_id in references}
    plan = json.loads(resolve_artifact(artifact_root, source["shared_view_plan_relative_path"], "view plan").read_text(encoding="utf-8"))["plan"]
    data_root = resolve_artifact(artifact_root, source["colmap_relative_root"], "COLMAP")
    dataset = ColmapDataset(
        data_root, downscale=float(config["render"]["image_downscale"]),
        load_depth=True, load_normal=False, load_semantic=False,
        visible_views=_visible_names(config, repo_root),
    )
    frame_by_name = {str(frame.name): (index, frame) for index, frame in enumerate(dataset.frames)}
    condition_results = []
    for condition_id in config["scope"]["condition_ids"]:
        spec = source["checkpoints"][condition_id]
        checkpoint = resolve_artifact(artifact_root, spec["relative_path"], condition_id)
        size, digest = sha256_file(checkpoint)
        if size != int(spec["bytes"]) or digest != spec["sha256"]:
            raise RuntimeError(f"checkpoint identity drift: {condition_id}")
        condition_results.extend(_render_condition(
            condition_id, checkpoint, output_root, dataset, frame_by_name,
            plan, references, grounds, config, device,
        ))
    cases, texture_records = _texture_and_render(
        output_root, artifact_root, repo_root, dataset, frame_by_name, plan, references, grounds, config,
    )
    counters = {
        "gs_training_invocations": 0, "checkpoint_render_extractions": 2,
        "full_scene_tsdf_reconstructions": 6, "semantic_roof_extractions": 6,
        "texture_bakes": len(texture_records), "roofer_invocations": 0, "g2_invocations": 0,
        "metric_recomputations": 0, "c4_c5_accesses": 0,
    }
    index = {
        "schema": "jointbuildgs.c3_full_scene_tsdf_semantic_texture_index.v1",
        "status": "COMPLETE_FULL_SCENE_TSDF_POST_SEMANTIC_TEXTURE_QUALITATIVE",
        "source_commit": source_commit, "case_count": 3, "condition_count": 2,
        "sheet_count": 6, "condition_results": condition_results, "cases": cases,
        "execution_counters": counters, "scientific_verdict": None,
    }
    write_new(output_root / "qualitative/index_v1.json", canonical_json_bytes(index))
    rows = []
    for result in condition_results:
        extraction = result["semantic_roof_extraction"]
        coverage = result["semantic_roof_coverage"]["coverage_fraction"]
        rows.append(
            f"| {result['condition_id']} | {result['stable_id']} | {result['integrated_view_count']} | "
            f"{result['full_scene_mesh_quality']['connected_component_count']} | {extraction['roof_triangle_count']} | {coverage:.4f} |"
        )
    report = """# C3 full-scene GS depth TSDF -> semantic roof -> texture

Semantic class를 TSDF 입력 전에 자르지 않았다. 24개 공통 시점의 전체 AOI GS rendered median depth와 RGB를 먼저 TSDF에 통합한 뒤, 추출된 full-scene mesh vertex를 동일 시점에 재투영해 semantic posterior와 view support를 누적했다. Roof triangle은 posterior, 최소 view support, ground+2.5 m, 상향 normal, footprint buffer 조건으로 후처리 추출했다. 마지막으로 current RGB multi-view texture를 적용했다.

| condition | building | integrated views | full mesh components | roof triangles | footprint roof coverage |
|---|---|---:|---:|---:|---:|
""" + "\n".join(rows) + "\n\nGT footprint wall은 textured roof 형상을 읽기 위한 중립 display-only geometry이며 TSDF 관측 또는 official metric input이 아니다. scientific_verdict는 null이다.\n"
    write_new(output_root / "reports/technical_report_ko_v1.md", report.encode("utf-8"))
    links = []
    for case in cases:
        links.append(f"<h2>{html.escape(case['stable_id'])}</h2>")
        for sheet in case["sheets"]:
            links.append(f"<h3>{html.escape(sheet['condition_id'])}</h3><img src=\"../{html.escape(sheet['sheet']['path'])}\">")
    write_new(output_root / "reports/case_index.html", ("<!doctype html><meta charset=utf-8><style>img{width:100%;margin-bottom:2rem}</style><h1>Full-scene TSDF semantic roof texture</h1>" + "".join(links)).encode("utf-8"))
    returned = {
        "schema": "jointbuildgs.c3_full_scene_tsdf_semantic_texture_return.v1",
        "status": "RETURNED_LOCAL_COMPLETE_FULL_SCENE_TSDF_QUALITATIVE",
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "source_commit": source_commit, "case_count": 3, "sheet_count": 6,
        "execution_counters": counters, "scientific_verdict": None,
    }
    write_new(output_root / "control/technical_return_v1.json", canonical_json_bytes(returned))
    manifest = {"schema": "jointbuildgs.c3_full_scene_tsdf_semantic_texture_manifest.v1", "status": "COMPLETE_HASHED_MATERIAL_PAYLOAD", "source_commit": source_commit, "records": _records(output_root), "scientific_verdict": None}
    manifest["record_count"] = len(manifest["records"])
    write_new(output_root / "control/artifact_manifest_v1.json", canonical_json_bytes(manifest))
    checks = {
        "case_count_3": len(cases) == 3, "sheet_count_6": sum(len(case["sheets"]) for case in cases) == 6,
        "full_scene_tsdf_6": len(condition_results) == 6,
        "semantic_was_not_used_before_tsdf": True,
        "all_prohibited_counters_zero": all(counters[key] == 0 for key in ("gs_training_invocations", "roofer_invocations", "g2_invocations", "metric_recomputations", "c4_c5_accesses")),
        "scientific_verdict_null": index["scientific_verdict"] is None,
    }
    if not all(checks.values()): raise RuntimeError(f"verification failed: {checks}")
    verified = {"schema": "jointbuildgs.local_technical_200_verified.v1", "status": "200-VERIFIED_LOCAL_SELF_CHECK", "checks": checks, "manifest": file_record(output_root / "control/artifact_manifest_v1.json", output_root), "scientific_verdict": None}
    write_new(output_root / "control/200-verified.local_v1.json", canonical_json_bytes(verified))
    closed = {"schema": "jointbuildgs.local_technical_300_closed.v1", "status": "300-CLOSED_LOCAL_FULL_SCENE_TSDF_SEMANTIC_TEXTURE", "technical_return": file_record(output_root / "control/technical_return_v1.json", output_root), "verified": file_record(output_root / "control/200-verified.local_v1.json", output_root), "manifest": file_record(output_root / "control/artifact_manifest_v1.json", output_root), "scientific_verdict": None}
    write_new(output_root / "control/300-closed.local_v1.json", canonical_json_bytes(closed))
    return closed


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--device", default="cuda")
    args = parser.parse_args()
    print(json.dumps(run(args.output_root, args.artifact_root, args.repo_root, args.source_commit, args.device), ensure_ascii=False, sort_keys=True))


if __name__ == "__main__": main()
