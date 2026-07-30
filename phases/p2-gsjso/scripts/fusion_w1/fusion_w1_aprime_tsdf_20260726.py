#!/usr/bin/env python3
"""Real TSDF + Marching Cubes read-out for FUS-W1 arm A-prime.

This implementation deliberately does not use ``tum_mob_tsdf_extract.py``:
that historical path backprojects depth, votes in voxels, and applies SOR but
does not construct a TSDF volume or extract a mesh.  Here each training view's
2DGS surface depth is masked by the exact roof-TIN mask M_j, integrated into an
Open3D ``ScalableTSDFVolume``, and extracted through Open3D's Marching Cubes
mesh path.

The T2 default invocation rehearses the path on the completed arm-A smoke
checkpoint.  The CLI overrides make the same implementation reusable for A'
checkpoints after training.  This script performs extraction and measurement;
it emits no scientific verdict.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import fcntl
import hashlib
import json
import math
import os
import platform
import subprocess
import sys
import traceback
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np
import torch
import yaml


REPO = Path(__file__).resolve().parents[4]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from gsplat import rasterization_2dgs  # noqa: E402
from src.stage2.colmap_io import read_cameras_bin, read_images_bin  # noqa: E402


DEFAULT_CONFIG = REPO / "phases/p2-gsjso/configs/fusion_w1/fusion_w1_aprime_tsdf_20260726.json"
RECEIPT_SCHEMA = "jointbuildgs.fusion_w1_aprime.tsdf.receipt.v1"


class TsdfReadoutError(RuntimeError):
    """Fail-closed input, mask, render, or extraction error."""


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def repo_path(value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else REPO / path


def relative(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(REPO.resolve()))
    except ValueError:
        return str(path.resolve())


def sha256_file(path: Path, chunk_size: int = 8 * 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(chunk_size)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def sha256_named_files(paths: Sequence[Path]) -> str:
    """Hash an ordered inventory including names, sizes, and content hashes."""

    digest = hashlib.sha256()
    for path in sorted((item.resolve() for item in paths), key=str):
        digest.update(relative(path).encode("utf-8"))
        digest.update(b"\0")
        digest.update(str(path.stat().st_size).encode("ascii"))
        digest.update(b"\0")
        digest.update(sha256_file(path).encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest()


def atomic_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + f".tmp.{os.getpid()}")
    with temporary.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def atomic_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    if not rows:
        raise TsdfReadoutError(f"refusing to publish empty CSV: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + f".tmp.{os.getpid()}")
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def archive_existing_receipt(output_dir: Path, name: str) -> dict[str, Any] | None:
    path = output_dir / name
    if not path.is_file():
        return None
    digest = sha256_file(path)
    history = output_dir / "receipt_history"
    history.mkdir(parents=True, exist_ok=True)
    timestamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    destination = history / f"{path.stem}.{timestamp}.{digest[:12]}{path.suffix}"
    os.replace(path, destination)
    fsync_directory(history)
    fsync_directory(output_dir)
    return {
        "source_name": name,
        "archived_path": relative(destination),
        "sha256": digest,
    }


def load_config(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        config = json.load(handle)
    if config.get("schema") != "jointbuildgs.fusion_w1_aprime.tsdf.config.v1":
        raise TsdfReadoutError("unexpected TSDF config schema")
    if config.get("branch") != "exp/fusion-w1":
        raise TsdfReadoutError("TSDF branch lock drift")
    if len(config.get("implementation_files", [])) != 4:
        raise TsdfReadoutError("TSDF implementation-file lock is incomplete")
    method = config.get("method", {})
    locked = {
        "rendered_depth": "gsplat_2dgs_surf_depth_render_median",
        "integration_mask": "exact_class6_roof_TIN_M_j",
        "alpha_threshold": None,
        "tsdf_implementation": "Open3D_ScalableTSDFVolume",
        "marching_cubes": "Open3D_extract_triangle_mesh",
        "voxel_size_m": 0.05,
        "sdf_trunc_m": 0.25,
        "depth_truncation": "max(2*minimum_camera_radius,max_valid_prior_depth_m+1.0)",
        "color_type": "RGB8",
        "minimum_component_triangles": 50,
        "mesh_sample_spacing_m": 0.1,
        "mesh_sample_classification": 6,
        "near_plane_m": 0.01,
        "far_plane_m": 10000000000.0,
        "downscale": 1.0,
        "random_seed": 20260726,
    }
    for key, expected in locked.items():
        if method.get(key) != expected:
            raise TsdfReadoutError(
                f"preregistered TSDF parameter drift: method.{key}="
                f"{method.get(key)!r}, expected {expected!r}"
            )
    coordinate = config.get("coordinate_contract", {})
    if coordinate.get("output_crs") != "EPSG:25832":
        raise TsdfReadoutError("TSDF output CRS must be EPSG:25832")
    if coordinate.get("output_vertical_datum") != "orthometric":
        raise TsdfReadoutError("TSDF readout output must be orthometric")
    if int(coordinate.get("vertical_conversion_application_count", -1)) != 1:
        raise TsdfReadoutError("vertical conversion application count must be one")
    if coordinate.get("canonical_frame") != "COLMAP_canonical_local_ellipsoidal":
        raise TsdfReadoutError("canonical coordinate frame lock drift")
    if coordinate.get("scene_reference_frame") != (
        "phases/p0-audit/data/work/opf/opf/scene_reference_frame.json"
    ):
        raise TsdfReadoutError("scene-reference path lock drift")
    if coordinate.get("projection_datum_config") != "configs/input_and_alignment/projection_datum.json":
        raise TsdfReadoutError("projection-datum path lock drift")
    for path_key, hash_key in (
        ("scene_reference_frame", "scene_reference_sha256"),
        ("projection_datum_config", "projection_datum_sha256"),
    ):
        locked_path = repo_path(str(coordinate[path_key]))
        if not locked_path.is_file() or sha256_file(locked_path) != coordinate.get(
            hash_key
        ):
            raise TsdfReadoutError(f"coordinate input SHA drift: {path_key}")
    if not math.isclose(float(coordinate.get("orthometric_geoid_m", math.nan)), 45.7):
        raise TsdfReadoutError("orthometric geoid lock drift")
    prereg = config.get("prereg_binding", {})
    prereg_path = repo_path(str(prereg.get("path", "")))
    if (
        prereg.get("P5")
        != "TSDF_fusion_plus_Marching_Cubes_then_0p1m_class6_surface_samples"
        or not prereg_path.is_file()
        or sha256_file(prereg_path) != prereg.get("sha256")
    ):
        raise TsdfReadoutError("A-prime prereg P5 binding drift")
    custom = config.get("aprime_custom_input_contract", {})
    if (
        custom.get("required_cache_namespace")
        != "aprime_pose_28b38383a0b6d826_class6_e005_k3_rooftin_v2"
        or custom.get("training_classes") != [6]
        or custom.get("ground_or_sfm_training_rows") != 0
    ):
        raise TsdfReadoutError("A-prime custom input lock drift")
    return config


def git(*arguments: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    process = subprocess.run(
        [
            "git",
            "-c",
            f"safe.directory={REPO}",
            "-C",
            str(REPO),
            *arguments,
        ],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if check and process.returncode:
        raise TsdfReadoutError(
            process.stderr.strip() or process.stdout.strip() or "git command failed"
        )
    return process


def verify_git_runtime(config: Mapping[str, Any]) -> dict[str, Any]:
    branch = git("branch", "--show-current").stdout.strip()
    head = git("rev-parse", "HEAD").stdout.strip()
    if branch != config["branch"]:
        raise TsdfReadoutError(f"branch mismatch: {branch}")
    records: list[dict[str, Any]] = []
    for logical in config["implementation_files"]:
        tracked = bool(git("ls-files", "--", logical).stdout.strip())
        at_head = git("cat-file", "-e", f"{head}:{logical}", check=False).returncode == 0
        worktree = git("hash-object", "--", logical).stdout.strip()
        head_blob = git("rev-parse", f"{head}:{logical}", check=False)
        unchanged = head_blob.returncode == 0 and worktree == head_blob.stdout.strip()
        if not tracked or not at_head or not unchanged:
            raise TsdfReadoutError(f"implementation not committed at HEAD: {logical}")
        records.append(
            {
                "path": logical,
                "sha256": sha256_file(repo_path(logical)),
                "git_blob": worktree,
                "tracked_at_head": True,
                "worktree_matches_head": True,
            }
        )
    return {"branch": branch, "head": head, "implementation_files": records}


def checkpoint_state(payload: Mapping[str, Any]) -> tuple[Mapping[str, torch.Tensor], dict[str, Any]]:
    """Accept the trainer's legacy final snapshot and atomic full-state format."""

    if payload.get("checkpoint_format") == "jointbuildgs.stage2.full_state":
        model = payload.get("model")
        if not isinstance(model, Mapping) or not isinstance(model.get("state_dict"), Mapping):
            raise TsdfReadoutError("full-state checkpoint lacks model.state_dict")
        return model["state_dict"], {
            "format": str(payload["checkpoint_format"]),
            "completed_steps": int(payload.get("completed_steps", -1)),
            "step_semantics": payload.get("step_semantics"),
        }
    state = payload.get("state_dict")
    if not isinstance(state, Mapping):
        raise TsdfReadoutError("checkpoint lacks state_dict")
    return state, {
        "format": "legacy_final_state_dict",
        "completed_steps": int(payload.get("it", -1)),
        "step_semantics": "legacy_final_iteration",
    }


def load_exact_mask_prior(path: Path) -> tuple[np.ndarray, np.ndarray, str]:
    """Load one roof prior and require one explicit exact M_j array."""

    with np.load(path) as bundle:
        if "depth_camera_z_m" not in bundle.files:
            raise TsdfReadoutError(f"prior has no depth_camera_z_m: {path}")
        candidates = [name for name in ("valid_M_j", "valid") if name in bundle.files]
        if not candidates:
            raise TsdfReadoutError(f"prior has no exact M_j field: {path}")
        masks = [np.asarray(bundle[name], dtype=bool) for name in candidates]
        if len(masks) == 2 and not np.array_equal(masks[0], masks[1]):
            raise TsdfReadoutError(f"valid and valid_M_j disagree: {path}")
        depth = np.asarray(bundle["depth_camera_z_m"], dtype=np.float32)
        mask = masks[0]
    if depth.ndim != 2 or mask.shape != depth.shape:
        raise TsdfReadoutError(f"prior depth/M_j shape mismatch: {path}")
    invalid_prior = mask & (~np.isfinite(depth) | (depth <= 0.0))
    if invalid_prior.any():
        raise TsdfReadoutError(
            f"exact M_j includes {int(invalid_prior.sum())} invalid prior depths: {path}"
        )
    return depth, mask, candidates[0]


def masked_surface_depth(
    surface_depth: np.ndarray,
    exact_mask: np.ndarray,
    depth_trunc_m: float,
) -> tuple[np.ndarray, dict[str, int]]:
    """Apply only M_j and RGBD depth validity; no alpha threshold is accepted."""

    depth = np.asarray(surface_depth, dtype=np.float32)
    mask = np.asarray(exact_mask, dtype=bool)
    if depth.ndim != 2 or depth.shape != mask.shape:
        raise TsdfReadoutError("surface depth and exact M_j shapes differ")
    finite_positive = np.isfinite(depth) & (depth > 0.0)
    below_trunc = depth <= float(depth_trunc_m)
    integrated = mask & finite_positive & below_trunc
    output = np.zeros_like(depth, dtype=np.float32)
    output[integrated] = depth[integrated]
    return output, {
        "M_j_pixels_n": int(mask.sum()),
        "integrated_pixels_n": int(integrated.sum()),
        "invalid_surface_depth_inside_M_j_n": int((mask & ~finite_positive).sum()),
        "over_depth_trunc_inside_M_j_n": int((mask & finite_positive & ~below_trunc).sum()),
        "outside_M_j_nonzero_after_mask_n": int(np.count_nonzero(output[~mask])),
        "alpha_threshold_exclusions_n": 0,
    }


def compute_depth_truncation(
    camera_centers: np.ndarray,
    scene_center: np.ndarray,
    max_valid_prior_depth_m: float,
) -> tuple[float, dict[str, float]]:
    centers = np.asarray(camera_centers, dtype=np.float64)
    center = np.asarray(scene_center, dtype=np.float64)
    if centers.ndim != 2 or centers.shape[1] != 3 or center.shape != (3,):
        raise TsdfReadoutError("camera centers/scene center have invalid shape")
    radii = np.linalg.norm(centers - center[None, :], axis=1)
    if not np.isfinite(radii).all() or np.any(radii <= 0.0):
        raise TsdfReadoutError("camera radii are nonfinite or nonpositive")
    if not math.isfinite(max_valid_prior_depth_m) or max_valid_prior_depth_m <= 0.0:
        raise TsdfReadoutError("max valid prior depth is nonfinite or nonpositive")
    minimum = float(radii.min())
    camera_term = 2.0 * minimum
    prior_term = float(max_valid_prior_depth_m) + 1.0
    selected = max(camera_term, prior_term)
    return selected, {
        "minimum_camera_radius_m": minimum,
        "maximum_camera_radius_m": float(radii.max()),
        "camera_radius_term_m": camera_term,
        "maximum_valid_prior_depth_m": float(max_valid_prior_depth_m),
        "prior_depth_term_m": prior_term,
        "selected_depth_trunc_m": selected,
    }


def filter_small_components(mesh: Any, minimum_triangles: int) -> dict[str, Any]:
    """Remove connected triangle components with fewer than the locked count."""

    triangle_count = len(mesh.triangles)
    if triangle_count == 0:
        return {
            "components_before_n": 0,
            "components_removed_n": 0,
            "triangles_before_n": 0,
            "triangles_removed_n": 0,
            "triangles_after_n": 0,
        }
    labels, counts, _areas = mesh.cluster_connected_triangles()
    label_array = np.asarray(labels, dtype=np.int64)
    count_array = np.asarray(counts, dtype=np.int64)
    removal = count_array[label_array] < int(minimum_triangles)
    mesh.remove_triangles_by_mask(removal.tolist())
    mesh.remove_unreferenced_vertices()
    mesh.remove_degenerate_triangles()
    mesh.remove_duplicated_triangles()
    mesh.remove_duplicated_vertices()
    return {
        "components_before_n": int(len(count_array)),
        "components_removed_n": int((count_array < int(minimum_triangles)).sum()),
        "triangles_before_n": int(triangle_count),
        "triangles_removed_n": int(removal.sum()),
        "triangles_after_n": int(len(mesh.triangles)),
        "component_triangle_count_min": int(count_array.min()),
        "component_triangle_count_median": float(np.median(count_array)),
        "component_triangle_count_max": int(count_array.max()),
    }


def infer_sh_degree(state: Mapping[str, torch.Tensor]) -> int:
    count = int(state["sh0"].shape[1] + state["shN"].shape[1])
    degree = int(round(math.sqrt(count) - 1.0))
    if (degree + 1) ** 2 != count:
        raise TsdfReadoutError(f"cannot infer SH degree from {count} coefficients")
    return degree


def camera_intrinsic_o3d(o3d: Any, camera: Any) -> Any:
    matrix = camera.K()
    return o3d.camera.PinholeCameraIntrinsic(
        int(camera.width),
        int(camera.height),
        float(matrix[0, 0]),
        float(matrix[1, 1]),
        float(matrix[0, 2]),
        float(matrix[1, 2]),
    )


def create_tsdf_volume(o3d: Any, voxel_size_m: float, sdf_trunc_m: float) -> Any:
    return o3d.pipelines.integration.ScalableTSDFVolume(
        voxel_length=float(voxel_size_m),
        sdf_trunc=float(sdf_trunc_m),
        color_type=o3d.pipelines.integration.TSDFVolumeColorType.RGB8,
    )


def integrate_open3d_frame(
    o3d: Any,
    volume: Any,
    rgb8: np.ndarray,
    depth_m: np.ndarray,
    intrinsic: Any,
    world_to_camera: np.ndarray,
    depth_trunc_m: float,
) -> None:
    color = np.ascontiguousarray(rgb8, dtype=np.uint8)
    depth = np.ascontiguousarray(depth_m, dtype=np.float32)
    if color.shape != (*depth.shape, 3):
        raise TsdfReadoutError("RGB/depth integration shapes differ")
    rgbd = o3d.geometry.RGBDImage.create_from_color_and_depth(
        o3d.geometry.Image(color),
        o3d.geometry.Image(depth),
        depth_scale=1.0,
        depth_trunc=float(depth_trunc_m),
        convert_rgb_to_intensity=False,
    )
    volume.integrate(rgbd, intrinsic, np.asarray(world_to_camera, dtype=np.float64))


def canonical_to_orthometric(
    points: np.ndarray,
    scene_reference: Mapping[str, Any],
    geoid_m: float,
) -> np.ndarray:
    transform = scene_reference.get("base_to_canonical", scene_reference)
    scale = np.asarray(transform.get("scale", [1.0, 1.0, 1.0]), dtype=np.float64)
    shift = np.asarray(transform.get("shift", [0.0, 0.0, 0.0]), dtype=np.float64)
    output = np.asarray(points, dtype=np.float64) / scale - shift
    if bool(transform.get("swap_xy", False)):
        output[:, [0, 1]] = output[:, [1, 0]]
    output[:, 2] -= float(geoid_m)
    return output


def load_scene_center(data_root: Path) -> tuple[np.ndarray, Path, int]:
    candidates = [
        data_root / "seed_class6_filtered_canonical.npz",
        data_root / "seed_canonical.npz",
    ]
    for path in candidates:
        if not path.exists():
            continue
        with np.load(path) as bundle:
            xyz_key = "xyz" if "xyz" in bundle.files else "xyz_canonical"
            if xyz_key not in bundle.files:
                continue
            xyz = np.asarray(bundle[xyz_key], dtype=np.float64)
            if "classification" in bundle.files:
                classification = np.asarray(bundle["classification"])
                class6 = xyz[classification == 6]
                if len(class6):
                    xyz = class6
        if xyz.ndim != 2 or xyz.shape[1] != 3 or len(xyz) == 0:
            raise TsdfReadoutError(f"invalid canonical seed geometry: {path}")
        return np.median(xyz, axis=0), path, int(len(xyz))
    raise TsdfReadoutError(f"no canonical class-6 seed bundle under {data_root}")


def git_value(*args: str) -> str | None:
    process = git(*args, check=False)
    return process.stdout.strip() if process.returncode == 0 else None


def software_inventory(o3d: Any) -> dict[str, Any]:
    import gsplat

    return {
        "python": platform.python_version(),
        "numpy": np.__version__,
        "torch": torch.__version__,
        "torch_cuda": torch.version.cuda,
        "cuda_available": bool(torch.cuda.is_available()),
        "cuda_device": torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,
        "gsplat": getattr(gsplat, "__version__", "unknown"),
        "open3d": o3d.__version__,
        "git_head": git_value("rev-parse", "HEAD"),
        "git_branch": git_value("branch", "--show-current"),
        "container_image_ref": os.environ.get("APRIME_CONTAINER_IMAGE"),
        "container_image_id": os.environ.get("APRIME_CONTAINER_IMAGE_ID"),
    }


def write_point_outputs(
    o3d: Any,
    mesh: Any,
    spacing_m: float,
    classification: int,
    random_seed: int,
    scene_reference: Mapping[str, Any],
    geoid_m: float,
    output_dir: Path,
) -> dict[str, Any]:
    area = float(mesh.get_surface_area())
    sample_count = max(1, int(math.ceil(area / (float(spacing_m) ** 2))))
    o3d.utility.random.seed(int(random_seed))
    cloud_canonical = mesh.sample_points_uniformly(
        number_of_points=sample_count,
        use_triangle_normal=True,
    )
    xyz_canonical = np.asarray(cloud_canonical.points, dtype=np.float64)
    xyz_orthometric = canonical_to_orthometric(
        xyz_canonical, scene_reference, geoid_m
    )
    normals = np.asarray(cloud_canonical.normals, dtype=np.float64)
    colors = np.asarray(cloud_canonical.colors, dtype=np.float64)
    if colors.shape != xyz_canonical.shape:
        colors = np.zeros_like(xyz_canonical)
    cloud_orthometric = o3d.geometry.PointCloud()
    cloud_orthometric.points = o3d.utility.Vector3dVector(xyz_orthometric)
    cloud_orthometric.normals = o3d.utility.Vector3dVector(normals)
    cloud_orthometric.colors = o3d.utility.Vector3dVector(colors)

    canonical_path = output_dir / "tsdf_surface_samples_canonical.ply"
    orthometric_path = output_dir / "tsdf_surface_samples_epsg25832_orthometric.ply"
    npz_path = output_dir / "tsdf_surface_samples.npz"
    if not o3d.io.write_point_cloud(str(canonical_path), cloud_canonical, write_ascii=False):
        raise TsdfReadoutError(f"failed to write {canonical_path}")
    if not o3d.io.write_point_cloud(str(orthometric_path), cloud_orthometric, write_ascii=False):
        raise TsdfReadoutError(f"failed to write {orthometric_path}")
    np.savez_compressed(
        npz_path,
        xyz_canonical_ellipsoidal=xyz_canonical,
        xyz_epsg25832_orthometric=xyz_orthometric,
        normal_canonical=normals,
        rgb=np.clip(np.rint(colors * 255.0), 0, 255).astype(np.uint8),
        classification=np.full(
            len(xyz_canonical), int(classification), dtype=np.uint8
        ),
        mesh_sample_spacing_m=np.array(float(spacing_m), dtype=np.float64),
        crs=np.array("EPSG:25832"),
        vertical_datum=np.array("orthometric"),
    )
    return {
        "surface_area_m2": area,
        "sample_points_n": int(len(xyz_canonical)),
        "requested_spacing_m": float(spacing_m),
        "area_derived_nominal_spacing_m": float(math.sqrt(area / sample_count)),
        "classification": int(classification),
        "artifacts": [canonical_path, orthometric_path, npz_path],
    }


def render_and_integrate(
    *,
    state: Mapping[str, torch.Tensor],
    images: Sequence[Any],
    cameras: Mapping[int, Any],
    masks: Mapping[str, tuple[np.ndarray, np.ndarray, str, Path]],
    volume: Any,
    o3d: Any,
    depth_trunc_m: float,
    near_plane_m: float,
    far_plane_m: float,
    device: str,
) -> list[dict[str, Any]]:
    required = ("means", "quats", "log_scales", "opacities_raw", "sh0", "shN")
    missing = [key for key in required if key not in state]
    if missing:
        raise TsdfReadoutError(f"checkpoint state lacks tensors: {missing}")
    means = state["means"].to(device)
    quats = state["quats"].to(device)
    scales = torch.exp(state["log_scales"]).to(device)
    opacities = torch.sigmoid(state["opacities_raw"]).to(device).reshape(-1)
    colors = torch.cat([state["sh0"], state["shN"]], dim=1).to(device)
    sh_degree = infer_sh_degree(state)
    rows: list[dict[str, Any]] = []
    for index, image in enumerate(images, 1):
        camera = cameras.get(image.camera_id)
        if camera is None:
            raise TsdfReadoutError(f"missing camera {image.camera_id}: {image.name}")
        _prior, exact_mask, mask_field, mask_path = masks[image.name]
        if exact_mask.shape != (int(camera.height), int(camera.width)):
            raise TsdfReadoutError(
                f"camera/M_j shape mismatch for {image.name}: "
                f"{camera.height}x{camera.width} vs {exact_mask.shape}"
            )
        k_mat = torch.tensor(camera.K(), dtype=torch.float32, device=device)
        world_to_camera = np.eye(4, dtype=np.float64)
        world_to_camera[:3, :3] = image.R()
        world_to_camera[:3, 3] = image.tvec
        center = -image.R().T @ image.tvec
        if not exact_mask.any():
            rows.append(
                {
                    "view_order": index,
                    "image_name": image.name,
                    "camera_id": int(image.camera_id),
                    "width": int(camera.width),
                    "height": int(camera.height),
                    "mask_field": mask_field,
                    "mask_path": relative(mask_path),
                    "mask_sha256": sha256_file(mask_path),
                    "M_j_pixels_n": 0,
                    "integrated_pixels_n": 0,
                    "invalid_surface_depth_inside_M_j_n": 0,
                    "over_depth_trunc_inside_M_j_n": 0,
                    "outside_M_j_nonzero_after_mask_n": 0,
                    "alpha_threshold_exclusions_n": 0,
                    "surf_depth_min_m": None,
                    "surf_depth_median_m": None,
                    "surf_depth_max_m": None,
                    "camera_center_x": float(center[0]),
                    "camera_center_y": float(center[1]),
                    "camera_center_z": float(center[2]),
                    "render_depth_source": "not_rendered_empty_exact_M_j",
                    "alpha_threshold": "none",
                }
            )
            print(
                f"[integrate] {index}/{len(images)} {image.name} "
                "M_j=0 integrated=0 (empty exact mask)",
                flush=True,
            )
            continue
        viewmat = torch.tensor(world_to_camera, dtype=torch.float32, device=device)
        with torch.no_grad():
            result = rasterization_2dgs(
                means=means,
                quats=quats,
                scales=scales,
                opacities=opacities,
                colors=colors,
                viewmats=viewmat.unsqueeze(0),
                Ks=k_mat.unsqueeze(0),
                width=int(camera.width),
                height=int(camera.height),
                near_plane=float(near_plane_m),
                far_plane=float(far_plane_m),
                render_mode="RGB+ED",
                depth_mode="expected",
                sh_degree=sh_degree,
            )
        # 2DGS names return[5] render_median; its public TSDF path calls this
        # surface depth (surf_depth). Expected depth in result[0][...,3] is not
        # used for the volume.
        surf_depth = result[5][0, ..., 0].detach().float().cpu().numpy()
        rgb = result[0][0, ..., :3].detach().float().cpu().numpy()
        depth_masked, mask_stats = masked_surface_depth(
            surf_depth, exact_mask, depth_trunc_m
        )
        rgb8 = np.clip(np.rint(np.clip(rgb, 0.0, 1.0) * 255.0), 0, 255).astype(np.uint8)
        rgb8[~exact_mask] = 0
        selected = depth_masked[depth_masked > 0.0]
        if len(selected):
            integrate_open3d_frame(
                o3d,
                volume,
                rgb8,
                depth_masked,
                camera_intrinsic_o3d(o3d, camera),
                world_to_camera,
                depth_trunc_m,
            )
            depth_min = float(selected.min())
            depth_median = float(np.median(selected))
            depth_max = float(selected.max())
        else:
            # An old ghosted checkpoint can have M_j support but no positive
            # surf_depth there.  Preserve M_j in the counts and record the
            # zero-contribution view; do not invent depth or redefine M_j.
            depth_min = None
            depth_median = None
            depth_max = None
        rows.append(
            {
                "view_order": index,
                "image_name": image.name,
                "camera_id": int(image.camera_id),
                "width": int(camera.width),
                "height": int(camera.height),
                "mask_field": mask_field,
                "mask_path": relative(mask_path),
                "mask_sha256": sha256_file(mask_path),
                **mask_stats,
                "surf_depth_min_m": depth_min,
                "surf_depth_median_m": depth_median,
                "surf_depth_max_m": depth_max,
                "camera_center_x": float(center[0]),
                "camera_center_y": float(center[1]),
                "camera_center_z": float(center[2]),
                "render_depth_source": "rasterization_2dgs_return_5_surf_depth",
                "alpha_threshold": "none",
            }
        )
        print(
            f"[integrate] {index}/{len(images)} {image.name} "
            f"M_j={mask_stats['M_j_pixels_n']} "
            f"integrated={mask_stats['integrated_pixels_n']}",
            flush=True,
        )
        del result, surf_depth, rgb, rgb8, depth_masked
    del means, quats, scales, opacities, colors
    torch.cuda.empty_cache()
    return rows


def write_mesh_pair(
    o3d: Any,
    mesh: Any,
    canonical_path: Path,
    orthometric_path: Path,
    scene_reference: Mapping[str, Any],
    geoid_m: float,
) -> None:
    if not o3d.io.write_triangle_mesh(str(canonical_path), mesh, write_ascii=False):
        raise TsdfReadoutError(f"failed to write {canonical_path}")
    transformed = o3d.geometry.TriangleMesh(mesh)
    vertices = np.asarray(transformed.vertices, dtype=np.float64)
    transformed.vertices = o3d.utility.Vector3dVector(
        canonical_to_orthometric(vertices, scene_reference, geoid_m)
    )
    if not o3d.io.write_triangle_mesh(str(orthometric_path), transformed, write_ascii=False):
        raise TsdfReadoutError(f"failed to write {orthometric_path}")


def resolved_arguments(args: argparse.Namespace, config: Mapping[str, Any]) -> dict[str, Any]:
    rehearsal = config["rehearsal"]
    overrides = (
        args.checkpoint,
        args.training_config,
        args.data_root,
        args.preprocess_manifest,
        args.output_dir,
        args.building_id,
        args.condition,
        args.replicate,
    )
    if any(overrides) and not all(overrides):
        raise TsdfReadoutError(
            "custom TSDF invocation must override checkpoint, training config, data root, "
            "preprocess manifest, output dir, building, condition, and replicate together"
        )
    return {
        "building_id": args.building_id or rehearsal["building_id"],
        "condition": args.condition or rehearsal["condition"],
        "replicate": args.replicate or rehearsal["replicate"],
        "checkpoint": repo_path(args.checkpoint or rehearsal["checkpoint"]),
        "training_config": repo_path(args.training_config or rehearsal["training_config"]),
        "data_root": repo_path(args.data_root or rehearsal["data_root"]),
        "preprocess_manifest": repo_path(
            args.preprocess_manifest or rehearsal["preprocess_manifest"]
        ),
        "output_dir": repo_path(args.output_dir or rehearsal["output_dir"]),
        "rehearsal_defaults": not any(overrides),
    }


def append_failure_issue(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        handle.seek(0, os.SEEK_END)
        if handle.tell() > 0:
            handle.write("\n")
        handle.write(
            "## FUS-W1-APRIME-T2-RUNTIME-FAILURE — TSDF rehearsal/extraction exception\n\n"
        )
        handle.write(f"- timestamp_utc: `{payload['created_at_utc']}`\n")
        handle.write(f"- error_type: `{payload['error_type']}`\n")
        handle.write(f"- output_dir: `{payload.get('output_dir')}`\n")
        handle.write(f"- message: `{payload['message']}`\n")
        handle.write("- action: exception receipt and traceback retained; no verdict emitted.\n")
        handle.flush()
        os.fsync(handle.fileno())
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def run(args: argparse.Namespace) -> Path:
    import open3d as o3d

    config_path = repo_path(args.config)
    config = load_config(config_path)
    git_lock = verify_git_runtime(config)
    values = resolved_arguments(args, config)
    output_dir: Path = values["output_dir"]
    output_dir.mkdir(parents=True, exist_ok=True)
    receipt_name = (
        "t2_tsdf_rehearsal_receipt.json"
        if values["rehearsal_defaults"]
        else "tsdf_receipt.json"
    )
    archived_receipts = [
        record
        for record in (
            archive_existing_receipt(output_dir, receipt_name),
            archive_existing_receipt(output_dir, "t2_tsdf_failure_receipt.json"),
        )
        if record is not None
    ]
    attempt_id = dt.datetime.now(dt.timezone.utc).strftime(
        "%Y%m%dT%H%M%S%fZ"
    ) + f"_pid{os.getpid()}"
    work_dir = output_dir / ".staging" / attempt_id
    work_dir.mkdir(parents=True, exist_ok=False)
    checkpoint: Path = values["checkpoint"]
    training_config: Path = values["training_config"]
    data_root: Path = values["data_root"]
    preprocess_manifest: Path = values["preprocess_manifest"]
    for path in (checkpoint, training_config, preprocess_manifest):
        if not path.is_file():
            raise TsdfReadoutError(f"required input missing: {path}")
    sparse = data_root / "sparse" / "0"
    for path in (sparse / "cameras.bin", sparse / "images.bin"):
        if not path.is_file():
            raise TsdfReadoutError(f"COLMAP input missing: {path}")

    rehearsal = config["rehearsal"]
    if values["rehearsal_defaults"]:
        if sha256_file(checkpoint) != rehearsal["checkpoint_sha256"]:
            raise TsdfReadoutError("arm-A rehearsal checkpoint SHA drift")
        if sha256_file(preprocess_manifest) != rehearsal["preprocess_manifest_sha256"]:
            raise TsdfReadoutError("arm-A rehearsal preprocess manifest SHA drift")
        if sha256_file(training_config) != rehearsal["training_config_sha256"]:
            raise TsdfReadoutError("arm-A rehearsal training config SHA drift")

    with training_config.open(encoding="utf-8") as handle:
        train_config = yaml.safe_load(handle)
    if not isinstance(train_config, Mapping):
        raise TsdfReadoutError("training config root is not a mapping")
    train_views = train_config.get("train_views")
    if not isinstance(train_views, list) or not train_views or len(train_views) != len(set(train_views)):
        raise TsdfReadoutError("training config has no unique explicit train_views")

    declared_data_root = repo_path(str(train_config.get("data_root", ""))).resolve()
    if declared_data_root != data_root.resolve():
        raise TsdfReadoutError("training config/data-root binding mismatch")
    declared_out_dir = repo_path(str(train_config.get("out_dir", ""))).resolve()
    try:
        checkpoint.resolve().relative_to(declared_out_dir)
    except ValueError as exc:
        raise TsdfReadoutError("checkpoint is outside the training output directory") from exc
    for identity_token in (
        values["building_id"],
        values["condition"],
        values["replicate"],
    ):
        if identity_token not in declared_out_dir.parts:
            raise TsdfReadoutError(
                f"training output directory does not bind identity token {identity_token}"
            )

    with preprocess_manifest.open(encoding="utf-8") as handle:
        preprocess_payload = json.load(handle)
    if not isinstance(preprocess_payload, Mapping):
        raise TsdfReadoutError("preprocess manifest root is not a mapping")
    if preprocess_payload.get("status") != "PASSED":
        raise TsdfReadoutError("preprocess manifest status is not PASSED")
    declared_manifest_root = repo_path(str(preprocess_payload.get("data_root", ""))).resolve()
    if declared_manifest_root != data_root.resolve():
        raise TsdfReadoutError("preprocess manifest/data-root binding mismatch")
    manifest_building = preprocess_payload.get("building") or {}
    if manifest_building.get("building_id") != values["building_id"]:
        raise TsdfReadoutError("preprocess manifest/building identity mismatch")
    manifest_views = preprocess_payload.get("views") or {}
    manifest_training = manifest_views.get("training_names")
    if isinstance(manifest_training, list):
        if len(manifest_training) != len(set(manifest_training)) or set(
            manifest_training
        ) != set(train_views):
            raise TsdfReadoutError("A-prime manifest/training-view inventory mismatch")
    else:
        manifest_selected = manifest_views.get("selected_names")
        if not isinstance(manifest_selected, list) or not set(train_views).issubset(
            set(manifest_selected)
        ):
            raise TsdfReadoutError("legacy manifest does not contain all training views")
    if not values["rehearsal_defaults"]:
        custom = config["aprime_custom_input_contract"]
        cache_namespace = (preprocess_payload.get("cache_policy") or {}).get(
            "namespace"
        )
        if cache_namespace != custom["required_cache_namespace"]:
            raise TsdfReadoutError("custom readout does not consume A-prime v2 cache")
        pose = preprocess_payload.get("pose_binding") or {}
        if (
            pose.get("corrected_images_sha256")
            != custom["required_pose_sha256"]
            or int(pose.get("transform_application_count", -1)) != 1
            or int(pose.get("additional_transform_application_count", -1)) != 0
        ):
            raise TsdfReadoutError("custom readout corrected-pose binding drift")
        seed_manifest = preprocess_payload.get("seed") or {}
        if (
            seed_manifest.get("classification_counts")
            != {"6": int(seed_manifest.get("filtered_points_n", -1))}
            or int(seed_manifest.get("class2_rows_n", -1)) != 0
            or int(seed_manifest.get("sfm_rows_n", -1)) != 0
        ):
            raise TsdfReadoutError("custom readout training seed is not class-6-only")

    cameras = read_cameras_bin(sparse / "cameras.bin")
    images_by_name = {
        image.name: image for image in read_images_bin(sparse / "images.bin").values()
    }
    absent = sorted(set(train_views) - set(images_by_name))
    if absent:
        raise TsdfReadoutError(f"training views absent from COLMAP subset: {absent}")
    images = [images_by_name[name] for name in train_views]

    masks: dict[str, tuple[np.ndarray, np.ndarray, str, Path]] = {}
    prior_paths: list[Path] = []
    max_valid_prior_depth = 0.0
    for image in images:
        path = data_root / "supervision" / "class6" / f"{image.name}.npz"
        if not path.is_file():
            raise TsdfReadoutError(f"missing exact-M_j class6 prior: {path}")
        prior, mask, field = load_exact_mask_prior(path)
        masks[image.name] = (prior, mask, field, path)
        prior_paths.append(path)
        if mask.any():
            max_valid_prior_depth = max(
                max_valid_prior_depth, float(prior[mask].max())
            )

    scene_center, seed_path, center_points_n = load_scene_center(data_root)
    declared_seed = repo_path(str(train_config.get("init_pointcloud", ""))).resolve()
    if declared_seed != seed_path.resolve():
        raise TsdfReadoutError("training init-pointcloud/preprocess seed binding mismatch")
    artifact_manifest = preprocess_payload.get("artifact_sha256") or {}
    consumed_preprocess_artifacts: list[dict[str, Any]] = []
    for consumed_path in [
        sparse / "cameras.bin",
        sparse / "images.bin",
        seed_path,
        *prior_paths,
    ]:
        logical = relative(consumed_path)
        expected = artifact_manifest.get(logical)
        actual = sha256_file(consumed_path)
        if expected != actual:
            raise TsdfReadoutError(
                f"consumed preprocess artifact SHA drift: {logical}"
            )
        consumed_preprocess_artifacts.append(
            {"path": logical, "sha256": actual, "bytes": consumed_path.stat().st_size}
        )
    camera_centers = np.asarray(
        [-image.R().T @ image.tvec for image in images], dtype=np.float64
    )
    depth_trunc_m, depth_trunc_stats = compute_depth_truncation(
        camera_centers, scene_center, max_valid_prior_depth
    )
    method = config["method"]
    voxel_size_m = float(method["voxel_size_m"])
    sdf_trunc_m = float(method["sdf_trunc_m"])
    volume = create_tsdf_volume(o3d, voxel_size_m, sdf_trunc_m)

    checkpoint_payload = torch.load(checkpoint, map_location="cpu", weights_only=False)
    state, checkpoint_meta = checkpoint_state(checkpoint_payload)
    if int(checkpoint_meta["completed_steps"]) != int(train_config.get("max_iter", -1)):
        raise TsdfReadoutError("final checkpoint/training max_iter binding mismatch")
    device = args.device
    if device.startswith("cuda") and not torch.cuda.is_available():
        raise TsdfReadoutError("CUDA device requested but unavailable")
    rows = render_and_integrate(
        state=state,
        images=images,
        cameras=cameras,
        masks=masks,
        volume=volume,
        o3d=o3d,
        depth_trunc_m=depth_trunc_m,
        near_plane_m=float(method["near_plane_m"]),
        far_plane_m=float(method["far_plane_m"]),
        device=device,
    )
    per_view_path = work_dir / "per_view_integration.csv"
    atomic_csv(per_view_path, rows)

    mesh_raw = volume.extract_triangle_mesh()
    mesh_raw.compute_vertex_normals()
    raw_vertices = int(len(mesh_raw.vertices))
    raw_triangles = int(len(mesh_raw.triangles))
    if raw_vertices == 0 or raw_triangles == 0:
        raise TsdfReadoutError(
            f"Marching Cubes produced empty mesh: vertices={raw_vertices}, triangles={raw_triangles}"
        )

    coordinate = config["coordinate_contract"]
    scene_reference_path = repo_path(coordinate["scene_reference_frame"])
    projection_config_path = repo_path(coordinate["projection_datum_config"])
    with scene_reference_path.open(encoding="utf-8") as handle:
        scene_reference = json.load(handle)
    with projection_config_path.open(encoding="utf-8") as handle:
        projection_config = json.load(handle)
    geoid_m = float(coordinate["orthometric_geoid_m"])
    if float(projection_config["orthometric_geoid_m"]) != geoid_m:
        raise TsdfReadoutError("projection datum/config geoid mismatch")

    raw_canonical = work_dir / "tsdf_mesh_raw_canonical.ply"
    raw_orthometric = work_dir / "tsdf_mesh_raw_epsg25832_orthometric.ply"
    write_mesh_pair(
        o3d, mesh_raw, raw_canonical, raw_orthometric, scene_reference, geoid_m
    )
    component_stats = filter_small_components(
        mesh_raw, int(method["minimum_component_triangles"])
    )
    mesh_raw.compute_vertex_normals()
    filtered_vertices = int(len(mesh_raw.vertices))
    filtered_triangles = int(len(mesh_raw.triangles))
    if filtered_vertices == 0 or filtered_triangles == 0:
        raise TsdfReadoutError(
            "component filtering removed every Marching Cubes triangle "
            f"(<{method['minimum_component_triangles']} triangles per component)"
        )
    mesh_canonical = work_dir / "tsdf_mesh_filtered_canonical.ply"
    mesh_orthometric = work_dir / "tsdf_mesh_filtered_epsg25832_orthometric.ply"
    write_mesh_pair(
        o3d, mesh_raw, mesh_canonical, mesh_orthometric, scene_reference, geoid_m
    )
    sampling = write_point_outputs(
        o3d,
        mesh_raw,
        float(method["mesh_sample_spacing_m"]),
        int(method["mesh_sample_classification"]),
        int(method["random_seed"]),
        scene_reference,
        geoid_m,
        work_dir,
    )
    sample_artifacts = sampling.pop("artifacts")

    artifact_paths = [
        per_view_path,
        raw_canonical,
        raw_orthometric,
        mesh_canonical,
        mesh_orthometric,
        *sample_artifacts,
    ]
    receipt_path = output_dir / receipt_name
    final_artifacts = [(path, output_dir / path.name) for path in artifact_paths]
    receipt = {
        "schema": RECEIPT_SCHEMA,
        "task_id": config["task_id"],
        "run_id": config["run_id"],
        "created_at_utc": utc_now(),
        "status": "COMPLETED",
        "verdict": None,
        "purpose": (
            "T2 TSDF plus Marching Cubes path rehearsal/measurement"
            if values["rehearsal_defaults"]
            else "A-prime TSDF plus Marching Cubes per-job extraction/measurement"
        ),
        "identity": {
            "building_id": values["building_id"],
            "condition": values["condition"],
            "replicate": values["replicate"],
            "rehearsal_defaults": bool(values["rehearsal_defaults"]),
        },
        "attempt": {
            "attempt_id": attempt_id,
            "archived_prior_receipts": archived_receipts,
            "staging_not_authoritative": True,
        },
        "git_lock": git_lock,
        "method": {
            **method,
            "depth_trunc_m_realized": depth_trunc_m,
            "render_call_depth_mode": "expected_for_RGB_plus_ED_api",
            "volume_depth_source": "rasterization_2dgs_return_5_render_median_surf_depth",
            "alpha_read_for_masking": False,
            "mask_application": "outside_exact_M_j_set_to_zero_before_RGBD_integration",
        },
        "depth_truncation_measurement": {
            **depth_trunc_stats,
            "scene_center_definition": "median_class6_canonical_seed",
            "scene_center_canonical": scene_center.tolist(),
            "scene_center_points_n": center_points_n,
        },
        "integration": {
            "training_views_n": len(images),
            "nonempty_M_j_views_n": int(
                sum(row["M_j_pixels_n"] > 0 for row in rows)
            ),
            "empty_M_j_views_n": int(
                sum(row["M_j_pixels_n"] == 0 for row in rows)
            ),
            "M_j_pixels_total_n": int(sum(row["M_j_pixels_n"] for row in rows)),
            "integrated_pixels_total_n": int(
                sum(row["integrated_pixels_n"] for row in rows)
            ),
            "invalid_surface_depth_inside_M_j_total_n": int(
                sum(row["invalid_surface_depth_inside_M_j_n"] for row in rows)
            ),
            "over_depth_trunc_inside_M_j_total_n": int(
                sum(row["over_depth_trunc_inside_M_j_n"] for row in rows)
            ),
            "outside_M_j_nonzero_after_mask_total_n": int(
                sum(row["outside_M_j_nonzero_after_mask_n"] for row in rows)
            ),
            "alpha_threshold_exclusions_total_n": 0,
            "exact_M_j_inventory_sha256": sha256_named_files(prior_paths),
            "per_view_csv": relative(output_dir / per_view_path.name),
            "per_view_csv_sha256": sha256_file(per_view_path),
        },
        "marching_cubes": {
            "implementation": "Open3D ScalableTSDFVolume.extract_triangle_mesh",
            "raw_vertices_n": raw_vertices,
            "raw_triangles_n": raw_triangles,
            "filtered_vertices_n": filtered_vertices,
            "filtered_triangles_n": filtered_triangles,
            **component_stats,
        },
        "surface_sampling": sampling,
        "coordinate_output": {
            "canonical_frame": coordinate["canonical_frame"],
            "crs": coordinate["output_crs"],
            "vertical_datum": coordinate["output_vertical_datum"],
            "orthometric_geoid_m": geoid_m,
            "vertical_conversion_application_count": 1,
        },
        "inputs": {
            "config": {"path": relative(config_path), "sha256": sha256_file(config_path)},
            "script": {
                "path": relative(Path(__file__)),
                "sha256": sha256_file(Path(__file__)),
            },
            "checkpoint": {
                "path": relative(checkpoint),
                "sha256": sha256_file(checkpoint),
                **checkpoint_meta,
                "primitives_n": int(state["means"].shape[0]),
            },
            "training_config": {
                "path": relative(training_config),
                "sha256": sha256_file(training_config),
            },
            "preprocess_manifest": {
                "path": relative(preprocess_manifest),
                "sha256": sha256_file(preprocess_manifest),
            },
            "class6_seed": {
                "path": relative(seed_path),
                "sha256": sha256_file(seed_path),
            },
            "cameras_bin": {
                "path": relative(sparse / "cameras.bin"),
                "sha256": sha256_file(sparse / "cameras.bin"),
            },
            "images_bin": {
                "path": relative(sparse / "images.bin"),
                "sha256": sha256_file(sparse / "images.bin"),
            },
            "scene_reference_frame": {
                "path": relative(scene_reference_path),
                "sha256": sha256_file(scene_reference_path),
            },
            "projection_datum_config": {
                "path": relative(projection_config_path),
                "sha256": sha256_file(projection_config_path),
            },
            "consumed_preprocess_artifacts": consumed_preprocess_artifacts,
        },
        "software": software_inventory(o3d),
        "artifacts": [
            {
                "path": relative(final_path),
                "sha256": sha256_file(staging_path),
                "bytes": staging_path.stat().st_size,
            }
            for staging_path, final_path in final_artifacts
        ],
        "checks": {
            "real_scalable_tsdf_volume": True,
            "marching_cubes_mesh_nonempty": True,
            "component_filter_applied": True,
            "surface_sample_nonempty": sampling["sample_points_n"] > 0,
            "only_exact_M_j_support": all(
                row["outside_M_j_nonzero_after_mask_n"] == 0 for row in rows
            ),
            "no_alpha_threshold": True,
            "training_view_inventory_exact": len(rows) == len(train_views),
            "checkpoint_equals_training_final_step": int(
                checkpoint_meta["completed_steps"]
            )
            == int(train_config["max_iter"]),
            "training_data_root_equals_preprocess_data_root": True,
            "building_identity_bound": True,
            "staged_artifacts_published_before_receipt": True,
            "receipt_written_last": True,
        },
    }
    for staging_path, final_path in final_artifacts:
        os.replace(staging_path, final_path)
    fsync_directory(output_dir)
    atomic_json(receipt_path, receipt)
    fsync_directory(output_dir)
    work_dir.rmdir()
    try:
        work_dir.parent.rmdir()
    except OSError:
        pass
    print(
        f"[done] TSDF+MC vertices={filtered_vertices} triangles={filtered_triangles} "
        f"samples={sampling['sample_points_n']} receipt={relative(receipt_path)}",
        flush=True,
    )
    return receipt_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    parser.add_argument("--checkpoint")
    parser.add_argument("--training-config")
    parser.add_argument("--data-root")
    parser.add_argument("--preprocess-manifest")
    parser.add_argument("--output-dir")
    parser.add_argument("--building-id")
    parser.add_argument("--condition")
    parser.add_argument("--replicate")
    parser.add_argument("--device", default="cuda")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config_path = repo_path(args.config)
    output_dir: Path | None = None
    issues_path: Path | None = None
    try:
        config = load_config(config_path)
        # No run-namespace mutation is allowed before the implementation is
        # tracked and unchanged at the current branch HEAD. ``run`` repeats
        # this gate and stores the resulting binding in the success receipt.
        verify_git_runtime(config)
        values = resolved_arguments(args, config)
        output_dir = values["output_dir"]
        issues_path = repo_path(config["issues_path"])
        run(args)
        return 0
    except Exception as exc:
        failure = {
            "schema": RECEIPT_SCHEMA,
            "task_id": "FUS-W1-APRIME-T2-001",
            "created_at_utc": utc_now(),
            "status": "FAILED",
            "verdict": None,
            "error_type": type(exc).__name__,
            "message": str(exc),
            "output_dir": relative(output_dir) if output_dir is not None else None,
            "traceback": traceback.format_exc(),
        }
        if output_dir is not None:
            atomic_json(output_dir / "t2_tsdf_failure_receipt.json", failure)
        if issues_path is not None:
            append_failure_issue(issues_path, failure)
        print(f"[FAILED] {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
