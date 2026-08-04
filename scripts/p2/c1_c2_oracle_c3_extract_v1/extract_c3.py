#!/usr/bin/env python3
"""Extract faithful 3D Gaussian records and depth-fused Poisson surfaces without training."""

from __future__ import annotations

import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np
import open3d as o3d
import torch

from scripts.p2.c1_c2_oracle_c3_extract_v1.contract import (
    canonical_json_bytes,
    display_proxy_mask,
    file_record,
    gaussian_full_ply,
    load_building_references,
    load_config,
    sha256_file,
    validate_config,
    write_new,
)
from scripts.p2.c3_utarget199_postprocess_v1.render_gs import model_from_checkpoint
from src.stage2.dataloader import ColmapDataset
from src.stage2.renderer import render, render_semantic


SEMANTIC_COLORS = np.asarray(
    [[0.18, 0.18, 0.18], [0.835, 0.369, 0.0], [0.0, 0.447, 0.698], [0.0, 0.62, 0.45]],
    dtype=np.float64,
)


def _checkpoint_spec(config: Mapping[str, Any], condition_id: str) -> Mapping[str, Any]:
    rows = [row for row in config["c3_training_provenance"]["conditions"] if row["condition_id"] == condition_id]
    if len(rows) != 1:
        raise RuntimeError(f"ambiguous C3 condition: {condition_id}")
    return rows[0]


def _subset_state(state: Mapping[str, torch.Tensor], mask: np.ndarray) -> dict[str, torch.Tensor]:
    index = torch.from_numpy(np.flatnonzero(mask)).to(torch.long)
    output = {}
    primitive_count = len(mask)
    for key, value in state.items():
        output[key] = value[index] if isinstance(value, torch.Tensor) and value.ndim and len(value) == primitive_count else value
    return output


def _simple_point_ply(xyz: np.ndarray, rgb: np.ndarray, normals: np.ndarray, labels: np.ndarray) -> bytes:
    rows = np.empty(
        len(xyz),
        dtype=np.dtype([
            ("x", "<f8"), ("y", "<f8"), ("z", "<f8"),
            ("nx", "<f4"), ("ny", "<f4"), ("nz", "<f4"),
            ("red", "u1"), ("green", "u1"), ("blue", "u1"), ("semantic_class", "u1"),
        ]),
    )
    rows["x"], rows["y"], rows["z"] = np.asarray(xyz, dtype=np.float64).T
    rows["nx"], rows["ny"], rows["nz"] = np.asarray(normals, dtype=np.float32).T
    colors = np.rint(np.clip(rgb, 0, 1) * 255).astype(np.uint8)
    rows["red"], rows["green"], rows["blue"] = colors.T
    rows["semantic_class"] = np.asarray(labels, dtype=np.uint8)
    header = (
        "ply\nformat binary_little_endian 1.0\n"
        "comment JointBuildGS rendered-depth multi-view fused surface points; EPSG:25832\n"
        f"element vertex {len(rows)}\n"
        "property double x\nproperty double y\nproperty double z\n"
        "property float nx\nproperty float ny\nproperty float nz\n"
        "property uchar red\nproperty uchar green\nproperty uchar blue\n"
        "property uchar semantic_class\nend_header\n"
    ).encode("ascii")
    return header + rows.tobytes()


def prepare_condition(
    output_root: Path,
    checkpoint: Path,
    condition_id: str,
    *,
    hash_checkpoint: bool,
) -> dict[str, Any]:
    config = load_config()
    validate_config(config, require_activation=True)
    spec = _checkpoint_spec(config, condition_id)
    if checkpoint.is_symlink() or not checkpoint.is_file() or checkpoint.stat().st_size != int(spec["bytes"]):
        raise RuntimeError(f"checkpoint missing/size drift: {checkpoint}")
    if hash_checkpoint:
        size, digest = sha256_file(checkpoint)
        if size != int(spec["bytes"]) or digest != spec["sha256"]:
            raise RuntimeError(f"checkpoint digest drift: {condition_id}")
    payload = torch.load(checkpoint, map_location="cpu", weights_only=True)
    if int(payload.get("iteration", spec["iteration"])) != int(spec["iteration"]):
        raise RuntimeError(f"checkpoint iteration drift: {condition_id}")
    state = payload["state_dict"]
    required = {"means", "quats", "log_scales", "opacities_raw", "sh0", "shN", "sem_logits"}
    if not required.issubset(state):
        raise RuntimeError(f"checkpoint state incomplete: {condition_id}")
    condition_root = output_root / "c3" / condition_id
    full_path = condition_root / "gaussians/exact_full_gaussian_parameters_v1.ply"
    write_new(full_path, gaussian_full_ply(state, config["frame"]["world_shift_xyz"]))
    proxy_cfg = config["c3_extraction"]["display_proxy_filter"]
    aoi = [690791.74, 5335864.05, 691154.65, 5336353.85]
    mask = display_proxy_mask(
        state,
        config["frame"]["world_shift_xyz"],
        opacity_min=float(proxy_cfg["opacity_min"]),
        maximum_in_plane_scale_m=float(proxy_cfg["maximum_in_plane_scale_m"]),
        aoi_bbox=aoi,
    )
    proxy_state = _subset_state(state, mask)
    proxy_path = condition_root / "gaussians/display_proxy_gaussian_parameters_v1.ply"
    write_new(proxy_path, gaussian_full_ply(proxy_state, config["frame"]["world_shift_xyz"]))
    scales = torch.exp(state["log_scales"].detach().cpu()).numpy()
    opacity = torch.sigmoid(state["opacities_raw"].detach().cpu()).numpy().reshape(-1)
    body = {
        "schema": "jointbuildgs.c3_exact_gaussian_export.v1",
        "status": "COMPLETE_NO_TRAINING",
        "condition_id": condition_id,
        "checkpoint": {
            "path": checkpoint.as_posix(),
            "bytes": int(spec["bytes"]),
            "sha256": spec["sha256"],
            "iteration": int(spec["iteration"]),
            "full_hash_passes_this_process": 1 if hash_checkpoint else 0,
        },
        "primitive_count_full": int(len(mask)),
        "primitive_count_display_proxy": int(mask.sum()),
        "display_proxy_fraction": float(mask.mean()),
        "opacity_below_0p1_count": int(np.count_nonzero(opacity < 0.1)),
        "maximum_scale_xyz_m": [float(value) for value in np.max(scales, axis=0)],
        "exact_full_export": file_record(full_path, output_root),
        "display_proxy_export": file_record(proxy_path, output_root),
        "training_invocations": 0,
        "scientific_verdict": None,
    }
    write_new(condition_root / "control/gaussian_export_complete_v1.json", canonical_json_bytes(body))
    return body


def _visible_names(config: Mapping[str, Any]) -> list[str]:
    manifest = json.loads(Path(config["inputs"]["current_rgb"]["exact_view_manifest_git_path"]).read_text(encoding="utf-8"))
    names = [str(row["basename"]) for row in manifest["rows"]]
    if len(names) != int(config["inputs"]["current_rgb"]["exact_view_count"]):
        raise RuntimeError("exact 937 view inventory drifted")
    return names


def _project_box(frame: Any, bbox_local: Sequence[float], z0: float, z1: float, downscale: float) -> tuple[float, tuple[int, int, int, int]] | None:
    x0, y0, x1, y1 = map(float, bbox_local)
    corners = np.asarray([[x, y, z] for z in (z0, z1) for y in (y0, y1) for x in (x0, x1)], dtype=np.float64)
    camera = corners @ frame.R.T + frame.t
    if np.any(camera[:, 2] <= 0):
        return None
    K = frame.K.copy()
    K[:2, :] *= float(downscale)
    uvw = camera @ K.T
    uv = uvw[:, :2] / uvw[:, 2:3]
    width = int(round(frame.width * downscale))
    height = int(round(frame.height * downscale))
    lo = np.floor(np.min(uv, axis=0)).astype(int)
    hi = np.ceil(np.max(uv, axis=0)).astype(int)
    left, top = max(0, int(lo[0])), max(0, int(lo[1]))
    right, bottom = min(width, int(hi[0]) + 1), min(height, int(hi[1]) + 1)
    if right <= left or bottom <= top:
        return None
    area = float((right - left) * (bottom - top))
    return area, (left, top, right, bottom)


def _view_plan(
    dataset: ColmapDataset,
    references: Mapping[str, Any],
    state: Mapping[str, torch.Tensor],
    config: Mapping[str, Any],
) -> dict[str, list[dict[str, Any]]]:
    shift = np.asarray(config["frame"]["world_shift_xyz"], dtype=np.float64)
    means = state["means"].detach().cpu().numpy().astype(np.float64)
    extraction = config["c3_extraction"]["surface_extraction"]
    buffer_m = float(extraction["diagnostic_crop_buffer_m"])
    downscale = float(extraction["render_downscale"])
    limit = int(extraction["maximum_views_per_building"])
    output = {}
    for stable_id, reference in references.items():
        x0, y0, x1, y1 = reference.footprint.bounds
        local_bbox = [x0 - shift[0] - buffer_m, y0 - shift[1] - buffer_m, x1 - shift[0] + buffer_m, y1 - shift[1] + buffer_m]
        local_keep = (
            (means[:, 0] >= local_bbox[0]) & (means[:, 0] <= local_bbox[2])
            & (means[:, 1] >= local_bbox[1]) & (means[:, 1] <= local_bbox[3])
        )
        if not np.any(local_keep):
            raise RuntimeError(f"checkpoint has no Gaussian centers near {stable_id}")
        z_values = means[local_keep, 2]
        z0, z1 = float(np.quantile(z_values, 0.01) - 5.0), float(np.quantile(z_values, 0.99) + 5.0)
        candidates = []
        for index, frame in enumerate(dataset.frames):
            projected = _project_box(frame, local_bbox, z0, z1, downscale)
            if projected is not None:
                area, crop = projected
                candidates.append({"index": index, "name": frame.name, "projected_area_px": area, "crop_xyxy": crop})
        candidates.sort(key=lambda row: (-row["projected_area_px"], row["name"]))
        if not candidates:
            raise RuntimeError(f"no current views cover {stable_id}")
        output[stable_id] = candidates[:limit]
    return output


def _accumulate_view_voxels(
    accumulator: dict[tuple[int, int, int], list[Any]],
    xyz: np.ndarray,
    normals: np.ndarray,
    rgb: np.ndarray,
    labels: np.ndarray,
    voxel_m: float,
) -> None:
    if not len(xyz):
        return
    keys = np.floor(xyz / float(voxel_m)).astype(np.int64)
    unique, inverse = np.unique(keys, axis=0, return_inverse=True)
    counts = np.bincount(inverse).astype(np.float64)
    xyz_sum = np.vstack([np.bincount(inverse, weights=xyz[:, axis]) for axis in range(3)]).T
    normal_sum = np.vstack([np.bincount(inverse, weights=normals[:, axis]) for axis in range(3)]).T
    rgb_sum = np.vstack([np.bincount(inverse, weights=rgb[:, axis]) for axis in range(3)]).T
    hist = np.vstack([np.bincount(inverse, weights=(labels == cls).astype(float)) for cls in range(4)]).T
    for index, key in enumerate(map(tuple, unique.tolist())):
        row = accumulator.get(key)
        if row is None:
            accumulator[key] = [1, counts[index], xyz_sum[index], normal_sum[index], rgb_sum[index], hist[index]]
        else:
            row[0] += 1
            row[1] += counts[index]
            row[2] += xyz_sum[index]
            row[3] += normal_sum[index]
            row[4] += rgb_sum[index]
            row[5] += hist[index]


def extract_surfaces(
    output_root: Path,
    artifact_root: Path,
    checkpoint: Path,
    lod2_path: Path,
    condition_id: str,
    device: str,
) -> dict[str, Any]:
    config = load_config()
    validate_config(config, require_activation=True)
    references = load_building_references(lod2_path, config["scope"]["building_ids"])
    payload = torch.load(checkpoint, map_location="cpu", weights_only=True)
    state = payload["state_dict"]
    names = _visible_names(config)
    data_root = artifact_root / config["inputs"]["current_rgb"]["data_root_relative_path"]
    extraction = config["c3_extraction"]["surface_extraction"]
    downscale = float(extraction["render_downscale"])
    dataset = ColmapDataset(
        data_root,
        downscale=downscale,
        load_depth=False,
        load_normal=False,
        load_semantic=False,
        visible_views=names,
    )
    plan = _view_plan(dataset, references, state, config)
    by_view: dict[int, list[tuple[str, tuple[int, int, int, int]]]] = defaultdict(list)
    for stable_id, rows in plan.items():
        for row in rows:
            by_view[int(row["index"])].append((stable_id, tuple(row["crop_xyxy"])))
    model = model_from_checkpoint(checkpoint, device)
    accumulators: dict[str, dict[tuple[int, int, int], list[Any]]] = {stable_id: {} for stable_id in references}
    shift = np.asarray(config["frame"]["world_shift_xyz"], dtype=np.float64)
    alpha_min = float(extraction["alpha_min"])
    voxel_m = float(extraction["voxel_m"])
    buffer_m = float(extraction["diagnostic_crop_buffer_m"])
    rendered_views = []
    torch.cuda.reset_peak_memory_stats()
    with torch.no_grad():
        for index in sorted(by_view):
            batch = dataset[index]
            width, height = int(batch["width"]), int(batch["height"])
            output = render(
                model,
                batch["w2c"].to(device),
                batch["K"].to(device),
                width,
                height,
                sh_degree=3,
                render_mode="RGB+ED",
                bg_color=torch.ones(3, device=device),
                depth_mode="expected",
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
                valid = (a >= alpha_min) & torch.isfinite(d) & (d > 0.01) & (d < 500.0)
                if not torch.any(valid):
                    continue
                z = d[valid]
                xc = (uu[valid] - K[0, 2]) / K[0, 0] * z
                yc = (vv[valid] - K[1, 2]) / K[1, 1] * z
                world_local = (torch.stack((xc, yc, z), dim=1) - t) @ R
                world = world_local + torch.as_tensor(shift, device=device, dtype=world_local.dtype)
                xyz = world.cpu().numpy().astype(np.float64)
                ref = references[stable_id]
                x0, y0, x1, y1 = ref.footprint.bounds
                keep = (
                    (xyz[:, 0] >= x0 - buffer_m) & (xyz[:, 0] <= x1 + buffer_m)
                    & (xyz[:, 1] >= y0 - buffer_m) & (xyz[:, 1] <= y1 + buffer_m)
                )
                if not np.any(keep):
                    continue
                _accumulate_view_voxels(
                    accumulators[stable_id],
                    xyz[keep],
                    n[valid].cpu().numpy()[keep],
                    c[valid].cpu().numpy()[keep],
                    lab[valid].cpu().numpy()[keep],
                    voxel_m,
                )
            rendered_views.append({"view_index": index, "image_name": batch["name"], "building_ids": [row[0] for row in by_view[index]]})
    minimum_views = int(extraction["minimum_distinct_view_observations"])
    results = []
    for stable_id, accumulator in accumulators.items():
        kept = [(key, row) for key, row in accumulator.items() if int(row[0]) >= minimum_views]
        if len(kept) < 100:
            raise RuntimeError(f"insufficient fused C3 surface points: {condition_id} {stable_id} {len(kept)}")
        xyz = np.asarray([row[1][2] / row[1][1] for row in kept], dtype=np.float64)
        normals = np.asarray([row[1][3] for row in kept], dtype=np.float64)
        normal_length = np.linalg.norm(normals, axis=1, keepdims=True)
        normals = normals / np.maximum(normal_length, 1e-12)
        rgb = np.asarray([row[1][4] / row[1][1] for row in kept], dtype=np.float64)
        labels = np.asarray([np.argmax(row[1][5]) for row in kept], dtype=np.uint8)
        building_root = output_root / "c3" / condition_id / "buildings" / stable_id
        points_path = building_root / "rendered_depth_fused_surface_points_v1.ply"
        write_new(points_path, _simple_point_ply(xyz, rgb, normals, labels))
        point_cloud = o3d.geometry.PointCloud()
        point_cloud.points = o3d.utility.Vector3dVector(xyz)
        point_cloud.normals = o3d.utility.Vector3dVector(normals)
        point_cloud.colors = o3d.utility.Vector3dVector(np.clip(rgb, 0, 1))
        mesh, densities = o3d.geometry.TriangleMesh.create_from_point_cloud_poisson(
            point_cloud,
            depth=int(extraction["poisson_depth"]),
            n_threads=2,
        )
        ref = references[stable_id]
        x0, y0, x1, y1 = ref.footprint.bounds
        z0, z1 = float(np.quantile(xyz[:, 2], 0.005) - 2.0), float(np.quantile(xyz[:, 2], 0.995) + 2.0)
        crop_box = o3d.geometry.AxisAlignedBoundingBox(
            min_bound=(x0 - buffer_m, y0 - buffer_m, z0),
            max_bound=(x1 + buffer_m, y1 + buffer_m, z1),
        )
        mesh = mesh.crop(crop_box)
        mesh.compute_vertex_normals()
        mesh_path = building_root / "poisson_surface_mesh_v1.ply"
        mesh_path.parent.mkdir(parents=True, exist_ok=True)
        if mesh_path.exists() or not o3d.io.write_triangle_mesh(str(mesh_path), mesh, write_ascii=False):
            raise RuntimeError(f"failed to write Poisson mesh: {mesh_path}")
        result = {
            "condition_id": condition_id,
            "stable_id": stable_id,
            "selected_view_count": len(plan[stable_id]),
            "fused_point_count": len(xyz),
            "mesh_vertex_count": len(mesh.vertices),
            "mesh_triangle_count": len(mesh.triangles),
            "surface_points": file_record(points_path, output_root),
            "poisson_mesh": file_record(mesh_path, output_root),
            "scientific_verdict": None,
        }
        write_new(building_root / "surface_extraction_v1.json", canonical_json_bytes(result))
        results.append(result)
    body = {
        "schema": "jointbuildgs.c3_surface_extraction.v1",
        "status": "COMPLETE_NO_TRAINING",
        "condition_id": condition_id,
        "checkpoint_sha256": _checkpoint_spec(config, condition_id)["sha256"],
        "view_plan": plan,
        "unique_rendered_view_count": len(rendered_views),
        "rendered_views": rendered_views,
        "building_results": results,
        "peak_gpu_memory_mib": int(torch.cuda.max_memory_allocated() / (1024 * 1024)),
        "training_invocations": 0,
        "mesh_method": "RENDERED_MEDIAN_DEPTH_MULTI_VIEW_VOXEL_FUSION_THEN_POISSON",
        "not_tsdf": True,
        "scientific_verdict": None,
    }
    write_new(output_root / f"c3/{condition_id}/control/surface_extraction_complete_v1.json", canonical_json_bytes(body))
    return body


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="mode", required=True)
    prepare = sub.add_parser("prepare-condition")
    prepare.add_argument("--output-root", type=Path, required=True)
    prepare.add_argument("--checkpoint", type=Path, required=True)
    prepare.add_argument("--condition-id", required=True)
    prepare.add_argument("--hash-checkpoint", action="store_true")
    surface = sub.add_parser("extract-surfaces")
    surface.add_argument("--output-root", type=Path, required=True)
    surface.add_argument("--artifact-root", type=Path, required=True)
    surface.add_argument("--checkpoint", type=Path, required=True)
    surface.add_argument("--lod2", type=Path, required=True)
    surface.add_argument("--condition-id", required=True)
    surface.add_argument("--device", default="cuda")
    args = parser.parse_args()
    if args.mode == "prepare-condition":
        result = prepare_condition(
            args.output_root,
            args.checkpoint,
            args.condition_id,
            hash_checkpoint=args.hash_checkpoint,
        )
    else:
        result = extract_surfaces(
            args.output_root,
            args.artifact_root,
            args.checkpoint,
            args.lod2,
            args.condition_id,
            args.device,
        )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
