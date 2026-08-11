#!/usr/bin/env python3
"""Freeze full-scene fused depth and confidence-gated fused-normal targets.

This runs in the project evaluation container.  It consumes current-image-derived
OpenMVS products only.  LoD2 geometry, roof labels, and condition outcomes are not
opened or used.
"""
from __future__ import annotations

import csv
import hashlib
import json
import os
from pathlib import Path
import sys
from typing import Any

os.environ.setdefault("OPENCV_IO_ENABLE_OPENEXR", "1")
import cv2  # noqa: E402
import numpy as np  # noqa: E402
import open3d as o3d  # noqa: E402
import yaml  # noqa: E402


REPO = Path("/workspace/JointBuildGS")
AR = Path("/artifacts/JointBuildGS")
TASK_ID = "P2-E3-FULL-SCENE-FUSED-NORMAL-CONFIDENCE-v1"
ROOT = AR / "phase-payloads/p2/e3_full_scene_fused_normal_confidence_v1" / TASK_ID
CONFIG = REPO / "configs/p2/e3_full_scene_fused_normal_confidence_v1/common.yaml"
NATIVE = ROOT / "native_dmap"
DATA = ROOT / "data/fused_normal_confidence_colmap_full"
DEPTH_DIR = DATA / "depth"
NORMAL_DIR = ROOT / "data/fused_surface_normal_confidence_world"
VIEW_RECEIPTS = ROOT / "target_view_receipts"

sys.path.insert(0, str(REPO))
from src.stage2.colmap_io import read_cameras_bin, read_images_bin  # noqa: E402


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def atomic_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(value, encoding="utf-8")
    os.replace(temporary, path)


def atomic_json(path: Path, value: Any) -> None:
    atomic_text(path, json.dumps(value, indent=2, sort_keys=True) + "\n")


def atomic_npy(path: Path, value: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("wb") as stream:
        np.save(stream, value, allow_pickle=False)
    os.replace(temporary, path)


def atomic_exr(path: Path, value: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.stem + ".tmp.exr")
    if not cv2.imwrite(str(temporary), np.asarray(value, dtype=np.float32)):
        raise RuntimeError(f"OpenEXR write failed: {path}")
    os.replace(temporary, path)


def ensure_symlink(path: Path, target: Path) -> None:
    if path.is_symlink():
        if path.resolve() != target.resolve():
            raise RuntimeError(f"symlink drift: {path}")
        return
    if path.exists():
        raise RuntimeError(f"refusing task-local collision: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.symlink_to(target, target_is_directory=True)


def normalize(value: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    length = np.linalg.norm(value, axis=-1, keepdims=True)
    valid = np.isfinite(value).all(axis=-1) & (length[..., 0] > 0.5)
    normalized = np.where(length > 1.0e-8, value / np.maximum(length, 1.0e-8), 0)
    return normalized.astype(np.float32), valid


def quantiles(values: np.ndarray) -> dict[str, float | None]:
    values = values[np.isfinite(values)]
    if not values.size:
        return {key: None for key in ("median", "p90", "p95", "p99")}
    result = np.quantile(values, (0.5, 0.9, 0.95, 0.99))
    return dict(zip(("median", "p90", "p95", "p99"), map(float, result)))


def exact_names(path: Path, expected_sha256: str) -> list[str]:
    if sha256(path) != expected_sha256:
        raise RuntimeError("exact-937 manifest identity drift")
    body = json.loads(path.read_text(encoding="utf-8"))
    names = [str(row["basename"]) for row in body["rows"]]
    if len(names) != 937 or len(set(names)) != 937:
        raise RuntimeError("exact-937 membership drift")
    return names


def load_native_index(path: Path) -> tuple[dict[str, int], list[str]]:
    body = json.loads(path.read_text(encoding="utf-8"))
    rows = body["mapped"]
    mapping = {str(row["image_name"]): int(row["dmap_index"]) for row in rows}
    missing = list(map(str, body["missing_image_names"]))
    if len(mapping) != 924 or len(missing) != 13 or set(mapping) & set(missing):
        raise RuntimeError("native DMap mapping inventory drift")
    return mapping, missing


def existing_row(receipt: Path, depth_path: Path, normal_path: Path) -> dict[str, Any] | None:
    if not (receipt.is_file() and depth_path.is_file() and normal_path.is_file()):
        return None
    row = json.loads(receipt.read_text(encoding="utf-8"))
    if row.get("depth_sha256") != sha256(depth_path) or row.get("normal_sha256") != sha256(normal_path):
        raise RuntimeError(f"sealed per-view target drift: {receipt}")
    return row


def main() -> None:
    cfg = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    manifest = Path(cfg["exact_view_manifest"])
    names = exact_names(manifest, cfg["exact_view_manifest_sha256"])
    raw = Path(cfg["data_root"])
    mesh_path = Path(cfg["source_mesh"])
    if mesh_path.stat().st_size != int(cfg["source_mesh_bytes"]) or sha256(mesh_path) != cfg["source_mesh_sha256"]:
        raise RuntimeError("fused OpenMVS mesh identity drift")
    mapping, missing = load_native_index(ROOT / "control/native_dmap_mapping.json")
    if set(names) != set(mapping) | set(missing):
        raise RuntimeError("native mapping does not partition exact-937")

    ensure_symlink(DATA / "images", raw / "images")
    ensure_symlink(DATA / "sparse", raw / "sparse")
    DEPTH_DIR.mkdir(parents=True, exist_ok=True)
    NORMAL_DIR.mkdir(parents=True, exist_ok=True)
    VIEW_RECEIPTS.mkdir(parents=True, exist_ok=True)

    cameras = read_cameras_bin(raw / "sparse/cameras.bin")
    images = read_images_bin(raw / "sparse/images.bin")
    by_name = {item.name: item for item in images.values()}
    if set(names) - set(by_name):
        raise RuntimeError("exact images missing from COLMAP sparse model")
    if len({item.camera_id for item in by_name.values() if item.name in set(names)}) != 1:
        raise RuntimeError("full-scene target generation expects one frozen camera model")
    camera = cameras[by_name[names[0]].camera_id]
    if [camera.width, camera.height] != list(cfg["alignment"]["full_resolution"]):
        raise RuntimeError("full-resolution camera contract drift")

    legacy = o3d.io.read_triangle_mesh(str(mesh_path))
    vertices = np.asarray(legacy.vertices)
    faces = np.asarray(legacy.triangles)
    if len(vertices) != 1_956_560 or len(faces) != 3_911_218:
        raise RuntimeError(f"OpenMVS mesh topology drift: {len(vertices)}/{len(faces)}")
    scene = o3d.t.geometry.RaycastingScene()
    scene.add_triangles(o3d.t.geometry.TriangleMesh.from_legacy(legacy))

    rule = cfg["normal_confidence_gate"]
    gate = cfg["target_gate"]
    relative_max = float(cfg["depth_support"]["native_fused_relative_difference_max"])
    normal_cos = float(np.cos(np.deg2rad(rule["native_fused_unsigned_angle_max_deg"])))
    local_cos = float(np.cos(np.deg2rad(rule["local_fused_unsigned_angle_max_deg"])))
    depth_jump = float(rule["depth_neighbor_jump_max_m"])
    kernel = np.ones((3, 3), np.uint8)
    scale = float(cfg["alignment"]["scale"])
    representatives = {names[0], names[len(names) // 3], names[2 * len(names) // 3], names[-1]}
    rows: list[dict[str, Any]] = []

    for order, name in enumerate(names):
        stem = Path(name).stem
        depth_path = DEPTH_DIR / f"{stem}.exr"
        normal_path = NORMAL_DIR / f"{stem}.npy"
        receipt_path = VIEW_RECEIPTS / f"{order:04d}_{stem}.json"
        prior = existing_row(receipt_path, depth_path, normal_path)
        if prior is not None:
            rows.append(prior)
            print(json.dumps({"view": order + 1, "views": len(names), "name": name, "status": "REUSED"}), flush=True)
            continue

        item = by_name[name]
        this_camera = cameras[item.camera_id]
        height, width = int(this_camera.height), int(this_camera.width)
        intrinsic = this_camera.K()
        uu, vv = np.meshgrid(np.arange(width, dtype=np.float32) + 0.5, np.arange(height, dtype=np.float32) + 0.5)
        camera_direction = np.stack(
            ((uu - intrinsic[0, 2]) / intrinsic[0, 0], (vv - intrinsic[1, 2]) / intrinsic[1, 1], np.ones_like(uu)), axis=-1
        )
        world_direction = camera_direction @ item.R()
        origin = (-item.R().T @ item.tvec).astype(np.float32)
        rays = np.concatenate((np.broadcast_to(origin, camera_direction.shape), world_direction.astype(np.float32)), axis=-1)
        cast = scene.cast_rays(o3d.core.Tensor(rays))
        hit = cast["t_hit"].numpy()
        fused_normal, fused_normal_valid = normalize(cast["primitive_normals"].numpy().astype(np.float32))
        fused_hit = np.isfinite(hit) & (hit > 0) & fused_normal_valid

        has_native = name in mapping
        if has_native:
            native_depth = np.load(NATIVE / f"{stem}.depth.npy", allow_pickle=False)
            native_confidence = np.load(NATIVE / f"{stem}.confidence.npy", allow_pickle=False)
            native_camera_normal = np.load(NATIVE / f"{stem}.normal.npy", allow_pickle=False)
            if list(native_depth.shape[::-1]) != list(cfg["alignment"]["native_resolution"]):
                raise RuntimeError(f"native DMap resolution drift: {name} {native_depth.shape}")
            yy, xx = np.mgrid[:height, :width].astype(np.float32)
            map_x = scale * (xx + 0.5) - 0.5
            map_y = scale * (yy + 0.5) - 0.5
            native_depth = cv2.remap(native_depth, map_x, map_y, cv2.INTER_NEAREST, borderMode=cv2.BORDER_CONSTANT, borderValue=0)
            native_confidence = cv2.remap(native_confidence, map_x, map_y, cv2.INTER_NEAREST, borderMode=cv2.BORDER_CONSTANT, borderValue=0)
            native_camera_normal = cv2.remap(native_camera_normal, map_x, map_y, cv2.INTER_NEAREST, borderMode=cv2.BORDER_CONSTANT, borderValue=0)
            native_camera_normal, native_normal_valid = normalize(native_camera_normal)
            native_world_normal = (native_camera_normal @ item.R()).astype(np.float32)
            native_valid = (
                np.isfinite(native_depth) & (native_depth > 0) &
                np.isfinite(native_confidence) & (native_confidence > 0)
            )
            common = fused_hit & native_valid
            relative = np.full((height, width), np.inf, np.float32)
            relative[common] = np.abs(native_depth[common] - hit[common]) / native_depth[common]
            depth_support = common & (relative < relative_max)
            dot = np.clip(np.abs(np.sum(native_world_normal * fused_normal, axis=-1)), 0, 1)
            agreement = native_normal_valid & native_valid & (dot >= normal_cos)
        else:
            native_valid = np.zeros((height, width), bool)
            depth_support = np.zeros((height, width), bool)
            agreement = np.zeros((height, width), bool)
            dot = np.zeros((height, width), np.float32)

        eroded = cv2.erode(depth_support.astype(np.uint8), kernel, iterations=1).astype(bool)
        supported_depth = np.where(depth_support, hit, 0).astype(np.float32)
        depth_range = cv2.dilate(supported_depth, kernel) - cv2.erode(supported_depth, kernel)
        depth_stable = eroded & np.isfinite(depth_range) & (depth_range <= depth_jump)
        minimum_neighbor_dot = np.ones((height, width), np.float32)
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                if dy == 0 and dx == 0:
                    continue
                neighbor = np.roll(fused_normal, shift=(dy, dx), axis=(0, 1))
                neighbor_dot = np.clip(np.abs(np.sum(fused_normal * neighbor, axis=-1)), 0, 1)
                minimum_neighbor_dot = np.minimum(minimum_neighbor_dot, neighbor_dot)
        local_stable = eroded & (minimum_neighbor_dot >= local_cos)
        normal_support = depth_support & agreement & depth_stable & local_stable
        frozen_normal = np.where(normal_support[..., None], fused_normal, 0).astype(np.float32)
        atomic_exr(depth_path, supported_depth)
        atomic_npy(normal_path, frozen_normal)

        angle_values = np.degrees(np.arccos(np.clip(dot[depth_support & native_valid], 0, 1)))
        row = {
            "view_order": order,
            "view": name,
            "native_dmap_index": mapping.get(name),
            "native_available": has_native,
            "width": width,
            "height": height,
            "fused_hit_pixels": int(fused_hit.sum()),
            "native_valid_pixels": int(native_valid.sum()),
            "depth_support_pixels": int(depth_support.sum()),
            "normal_support_pixels": int(normal_support.sum()),
            "depth_support_fraction_of_fused_hits": float(depth_support.sum() / max(int(fused_hit.sum()), 1)),
            "normal_fraction_of_depth_support": float(normal_support.sum() / max(int(depth_support.sum()), 1)),
            "native_fused_unsigned_angle_deg": quantiles(angle_values),
            "depth_sha256": sha256(depth_path),
            "normal_sha256": sha256(normal_path),
            "scientific_verdict": None,
        }
        atomic_json(receipt_path, row)
        rows.append(row)
        print(json.dumps({"view": order + 1, "views": len(names), "name": name, "depth": row["depth_support_pixels"], "normal": row["normal_support_pixels"]}), flush=True)

        if name in representatives:
            rgb = cv2.imread(str(raw / "images" / name), cv2.IMREAD_COLOR)
            if rgb is not None:
                shown = rgb.copy()
                shown[depth_support] = (0.55 * shown[depth_support] + 0.45 * np.asarray([235, 210, 20])).astype(np.uint8)
                shown[normal_support] = (0.35 * shown[normal_support] + 0.65 * np.asarray([210, 65, 220])).astype(np.uint8)
                cv2.imwrite(str(ROOT / "representative_images" / f"{stem}_support.png"), shown)

    if len(rows) != len(names):
        raise RuntimeError("target row count drift")
    metrics_path = ROOT / "target_metrics.csv"
    fields = [key for key in rows[0] if key not in {"native_fused_unsigned_angle_deg", "scientific_verdict"}]
    with metrics_path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows({key: row[key] for key in fields} for row in rows)

    depth_views = sum(row["depth_support_pixels"] >= int(gate["minimum_pixels_per_supported_view"]) for row in rows)
    normal_views = sum(row["normal_support_pixels"] >= int(gate["minimum_pixels_per_supported_view"]) for row in rows)
    fused_total = sum(row["fused_hit_pixels"] for row in rows)
    depth_total = sum(row["depth_support_pixels"] for row in rows)
    normal_total = sum(row["normal_support_pixels"] for row in rows)
    depth_fraction = depth_total / max(fused_total, 1)
    normal_fraction = normal_total / max(depth_total, 1)
    checks = {
        "exact_rgb_views": len(rows) == int(gate["require_exact_rgb_views"]),
        "native_dmap_views": len(mapping) == int(gate["require_native_dmap_views"]),
        "missing_native_views": len(missing) == int(gate["require_missing_native_views"]),
        "depth_supported_views": depth_views >= int(gate["minimum_depth_supported_views"]),
        "normal_supported_views": normal_views >= int(gate["minimum_normal_supported_views"]),
        "depth_support_fraction": depth_fraction >= float(gate["minimum_depth_support_fraction_of_fused_hits"]),
        "normal_fraction_min": normal_fraction >= float(gate["minimum_normal_fraction_of_depth_support"]),
        "normal_fraction_max": normal_fraction <= float(gate["maximum_normal_fraction_of_depth_support"]),
        "all_normal_inside_depth": all(row["normal_support_pixels"] <= row["depth_support_pixels"] for row in rows),
        "lod2_geometry_unused": True,
    }
    definition = {
        "schema": "jointbuildgs.p2.e3_full_scene_fused_normal_confidence_v1.targets.v1",
        "task_id": TASK_ID,
        "status": "GATE_PASSED" if all(checks.values()) else "GATE_FAILED",
        "exact_rgb_view_count": len(rows),
        "native_dmap_view_count": len(mapping),
        "missing_native_view_count": len(missing),
        "missing_native_image_names": missing,
        "depth_supported_view_count": depth_views,
        "normal_supported_view_count": normal_views,
        "fused_hit_pixels": fused_total,
        "depth_support_pixels": depth_total,
        "normal_support_pixels": normal_total,
        "depth_support_fraction_of_fused_hits": depth_fraction,
        "normal_fraction_of_depth_support": normal_fraction,
        "depth_mask_formula": "fused_hit & native_depth_positive & native_confidence_positive & abs(native-fused)/native < 0.01",
        "normal_mask_formula": "depth_mask & native_normal_valid & unsigned_angle(native,fused)<=15deg & erode(depth_mask,1px) & local_max_angle<=15deg & local_depth_range<=1m",
        "zero_supervision_policy": "13 missing native DMap views remain in RGB/MVC membership with all-zero depth and normal targets",
        "gate_checks": checks,
        "source_mesh": str(mesh_path),
        "source_mesh_sha256": cfg["source_mesh_sha256"],
        "lod2_training_use": False,
        "official_PASS_usable": None,
        "scientific_verdict": None,
    }
    atomic_json(ROOT / "target_definition.json", definition)
    print(json.dumps(definition, indent=2, sort_keys=True))
    if not all(checks.values()):
        raise SystemExit(3)


if __name__ == "__main__":
    main()
