#!/usr/bin/env python3
"""Freeze same-ray OpenMVS mesh depth/normal targets and raw/native/fused panels."""
from __future__ import annotations

import csv
import hashlib
import json
import os
from pathlib import Path
import sys

os.environ.setdefault("OPENCV_IO_ENABLE_OPENEXR", "1")
import cv2  # noqa: E402
import matplotlib  # noqa: E402
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import open3d as o3d  # noqa: E402
import yaml  # noqa: E402


REPO = Path("/workspace/JointBuildGS")
AR = Path("/artifacts/JointBuildGS")
TASK_ID = "P2-E3-LOCAL-4906982-FUSED-SURFACE-NORMAL-v1"
ROOT = AR / "phase-payloads/p2/e3_local_4906982_fused_surface_normal_v1" / TASK_ID
RAW = AR / "phase-payloads/p2/e3_local_4906982_v1/P2-E3-LOCAL-4906982-2DGS-v6-dist0-resetoff-30k/data/colmap_crop"
FUSED_TASK = AR / "phase-payloads/p2/e3_local_4906982_fused_vis_conf_v1/P2-E3-LOCAL-4906982-FUSED-VIS-CONF-v1"
FUSED_DATA = FUSED_TASK / "data/fused_vis_conf_colmap_crop"
RAW_NORMAL_TASK = AR / "phase-payloads/p2/e3_local_4906982_mvs_normal_ablation_v1/P2-E3-LOCAL-4906982-MVS-NORMAL-ABLATION-v1"
RAW_NORMAL_TARGET = RAW_NORMAL_TASK / "data/normal_world"
FULL_MESH_DEPTH = AR / "phase-payloads/p2/e3_local_4906982_mvs_surface_depth_v1/P2-E3-LOCAL-4906982-MVS-SURFACE-DEPTH-v1/data/mvs_surface_colmap_crop/depth"
NATIVE = FUSED_TASK / "native_dmap"
NATIVE_NORMAL = ROOT / "native_dmap_normal"
NATIVE_INDEX = NATIVE / "image_index.tsv"
OUT_DATA = ROOT / "data/fused_vis_conf_fused_normal_colmap_crop"
OUT_NORMAL = ROOT / "data/fused_surface_normal_world"
BASE_CONFIG = REPO / "configs/p2/e3_local_4906982_mvc_depth_v1/depth03.yaml"
COMMON_CONFIG = REPO / "configs/p2/e3_local_4906982_fused_surface_normal_v1/common.yaml"
SUPPORT_CONFIG = REPO / "configs/p2/e3_local_4906982_fused_vis_conf_v1/support.yaml"
PROJECTION_CONFIG = REPO / "configs/p2/e3_local_4906982_mvs_surface_depth_v1/projection.yaml"

sys.path.insert(0, str(REPO))
from src.stage2.colmap_io import read_cameras_bin, read_images_bin  # noqa: E402


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def atomic_json(path: Path, body: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(body, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, path)


def read_colmap_dense(path: Path) -> np.ndarray:
    with path.open("rb") as stream:
        header = bytearray(); ampersands = 0
        while ampersands < 3:
            value = stream.read(1)
            if not value: raise ValueError(f"truncated COLMAP dense header: {path}")
            header.extend(value); ampersands += value == b"&"
        width, height, channels = map(int, header.decode("ascii").split("&")[:3])
        payload = np.fromfile(stream, dtype=np.float32)
    if payload.size != width * height * channels: raise ValueError(f"payload size drift: {path}")
    value = payload.reshape((width, height, channels), order="F").transpose(1, 0, 2)
    return value[..., 0] if channels == 1 else value


def read_exr(path: Path) -> np.ndarray:
    value = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
    if value is None: raise RuntimeError(f"failed to read {path}")
    return (value[..., 0] if value.ndim == 3 else value).astype(np.float32, copy=False)


def ensure_symlink(path: Path, target: Path) -> None:
    if path.is_symlink():
        if path.resolve() != target.resolve(): raise RuntimeError(f"symlink drift: {path}")
        return
    if path.exists(): raise RuntimeError(f"refusing collision: {path}")
    path.parent.mkdir(parents=True, exist_ok=True); path.symlink_to(target)


def normalize(value: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    length = np.linalg.norm(value, axis=-1, keepdims=True)
    valid = np.isfinite(value).all(axis=-1) & (length[..., 0] > 0.5)
    return np.where(length > 1e-8, value / np.maximum(length, 1e-8), 0).astype(np.float32), valid


def angle(a: np.ndarray, b: np.ndarray, valid: np.ndarray) -> np.ndarray:
    dot = np.clip(np.abs(np.sum(a * b, axis=-1)), 0, 1)
    result = np.full(valid.shape, np.nan, np.float32)
    result[valid] = np.degrees(np.arccos(dot[valid]))
    return result


def q(values: np.ndarray) -> dict[str, float | None]:
    values = values[np.isfinite(values)]
    if not values.size: return {name: None for name in ("median", "p90", "p95", "p99", "max")}
    points = np.quantile(values, (.5, .9, .95, .99))
    return {"median": float(points[0]), "p90": float(points[1]), "p95": float(points[2]), "p99": float(points[3]), "max": float(values.max())}


def normal_rgb(value: np.ndarray, valid: np.ndarray) -> np.ndarray:
    # Unsigned orientation is trained; abs() gives a stable visualization independent of face winding.
    shown = np.clip(np.abs(value), 0, 1)
    return np.where(valid[..., None], shown, .08)


def panel(path: Path, rgb: np.ndarray, raw_d: np.ndarray, native_d: np.ndarray,
          fused_d: np.ndarray, confidence: np.ndarray, support: np.ndarray,
          raw_n: np.ndarray, raw_ok: np.ndarray, native_n: np.ndarray,
          native_ok: np.ndarray, fused_n: np.ndarray, fused_ok: np.ndarray,
          raw_fused_angle: np.ndarray, native_fused_angle: np.ndarray) -> None:
    valid_depths = np.concatenate([x[np.isfinite(x) & (x > 0)] for x in (raw_d, native_d, fused_d)])
    lo, hi = np.quantile(valid_depths, (.02, .98))
    fig, axes = plt.subplots(3, 4, figsize=(18, 13), constrained_layout=True)
    axes[0, 0].imshow(cv2.cvtColor(rgb, cv2.COLOR_BGR2RGB)); axes[0, 0].set_title("RGB")
    for axis, value, title in (
        (axes[0, 1], raw_d, "1 raw COLMAP depth\nper-view candidates"),
        (axes[0, 2], native_d, "2 OpenMVS native filtered depth\nview-local filtered evidence"),
        (axes[0, 3], fused_d, "3 fused mesh first-hit depth\nmulti-view fused surface"),
    ):
        axis.imshow(np.where(np.isfinite(value) & (value > 0), value, np.nan), cmap="turbo", vmin=lo, vmax=hi); axis.set_title(title)
    axes[1, 0].imshow(np.isfinite(raw_d) & (raw_d > 0), cmap="gray", vmin=0, vmax=1); axes[1, 0].set_title("raw valid mask")
    axes[1, 1].imshow(np.where(confidence > 0, confidence, np.nan), cmap="magma"); axes[1, 1].set_title("native confidence")
    axes[1, 2].imshow(support, cmap="gray", vmin=0, vmax=1); axes[1, 2].set_title("frozen training support\nnative agrees with fused")
    residual = np.where((native_d > 0) & (fused_d > 0), np.abs(native_d - fused_d), np.nan)
    axes[1, 3].imshow(residual, cmap="magma", vmin=0, vmax=min(5., float(np.nanquantile(residual, .99)))); axes[1, 3].set_title("|native - fused| depth")
    axes[2, 0].imshow(normal_rgb(raw_n, raw_ok)); axes[2, 0].set_title("raw COLMAP normal")
    axes[2, 1].imshow(normal_rgb(native_n, native_ok)); axes[2, 1].set_title("native filtered normal")
    axes[2, 2].imshow(normal_rgb(fused_n, fused_ok)); axes[2, 2].set_title("fused mesh triangle normal\nNEW training target")
    disagreement = np.where(np.isfinite(raw_fused_angle), raw_fused_angle, native_fused_angle)
    im = axes[2, 3].imshow(disagreement, cmap="magma", vmin=0, vmax=90); axes[2, 3].set_title("normal disagreement to fused (deg)")
    fig.colorbar(im, ax=axes[2, 3], fraction=.046)
    for axis in axes.ravel(): axis.axis("off")
    path.parent.mkdir(parents=True, exist_ok=True); fig.savefig(path, dpi=150); plt.close(fig)


def main() -> None:
    cfg = yaml.safe_load(BASE_CONFIG.read_text())
    common = yaml.safe_load(COMMON_CONFIG.read_text()); gate = common["target_gate"]
    support_cfg = yaml.safe_load(SUPPORT_CONFIG.read_text())
    projection = yaml.safe_load(PROJECTION_CONFIG.read_text())
    native_outputs = sorted(NATIVE_NORMAL.glob("*.normal.npy"))
    if len(native_outputs) != 55: raise RuntimeError(f"expected 55 extracted native normal maps, got {len(native_outputs)}")
    extractor_binary = ROOT / "control/bin/extract_native_normal"
    atomic_json(ROOT / "control/native_normal_extraction_receipt.json", {
        "schema": "jointbuildgs.p2.e3_local_4906982_fused_surface_normal_v1.native_extract.v1",
        "source": "OpenMVS native DMAP normalMap in camera space", "image_index": {"path": str(NATIVE_INDEX), "sha256": sha256(NATIVE_INDEX)},
        "extractor_binary_sha256": sha256(extractor_binary), "count": len(native_outputs),
        "outputs_sha256": {path.name: sha256(path) for path in native_outputs}, "passed": True, "scientific_verdict": None,
    })
    cameras = read_cameras_bin(RAW / "sparse/0/cameras.bin")
    images = read_images_bin(RAW / "sparse/0/images.bin"); by_name = {item.name: item for item in images.values()}
    base_camera = next(camera for camera in cameras.values() if (camera.width, camera.height) == (1400, 1013))
    base_k = base_camera.K(); scale = float(support_cfg["alignment"]["scale"])
    mesh_path = Path(projection["source_mesh"])
    mesh = o3d.io.read_triangle_mesh(str(mesh_path))
    vertices, faces = np.asarray(mesh.vertices), np.asarray(mesh.triangles)
    if len(vertices) != 1_956_560 or len(faces) != 3_911_218: raise RuntimeError("OpenMVS mesh count drift")
    scene = o3d.t.geometry.RaycastingScene(); scene.add_triangles(o3d.t.geometry.TriangleMesh.from_legacy(mesh))
    OUT_DATA.mkdir(parents=True, exist_ok=True); OUT_NORMAL.mkdir(parents=True, exist_ok=True)
    ensure_symlink(OUT_DATA / "images", FUSED_DATA / "images")
    ensure_symlink(OUT_DATA / "sparse", FUSED_DATA / "sparse")
    ensure_symlink(OUT_DATA / "depth", FUSED_DATA / "depth")
    representatives = {cfg["visible_views"][0], cfg["visible_views"][8], cfg["visible_views"][23], cfg["visible_views"][-1]}
    train = set(cfg["train_views"]); rows = []; all_raw_fused = []; all_native_fused = []; all_depth_residual = []
    for name in cfg["visible_views"]:
        item = by_name[name]; camera = cameras[item.camera_id]; h, w = camera.height, camera.width; stem = Path(name).stem
        uu, vv = np.meshgrid(np.arange(w, dtype=np.float32) + float(projection["ray_pixel_center_offset"]), np.arange(h, dtype=np.float32) + float(projection["ray_pixel_center_offset"]))
        k = camera.K(); camera_direction = np.stack(((uu-k[0,2])/k[0,0], (vv-k[1,2])/k[1,1], np.ones_like(uu)), axis=-1)
        world_direction = camera_direction @ item.R(); origin = (-item.R().T @ item.tvec).astype(np.float32)
        rays = np.concatenate((np.broadcast_to(origin, camera_direction.shape), world_direction.astype(np.float32)), axis=-1)
        cast = scene.cast_rays(o3d.core.Tensor(rays)); hit = cast["t_hit"].numpy(); primitive = cast["primitive_normals"].numpy().astype(np.float32)
        hit_ok = np.isfinite(hit) & (hit > 0); fused_normal, primitive_ok = normalize(primitive); fused_ok = hit_ok & primitive_ok
        full_depth = read_exr(FULL_MESH_DEPTH / f"{stem}.exr"); depth_compare = hit_ok & (full_depth > 0)
        depth_residual = np.abs(hit[depth_compare] - full_depth[depth_compare]); all_depth_residual.append(depth_residual)
        supported_depth = read_exr(FUSED_DATA / "depth" / f"{stem}.exr"); support = np.isfinite(supported_depth) & (supported_depth > 0)
        raw_depth = read_colmap_dense(RAW / "stereo/depth_maps" / f"{name}.geometric.bin").astype(np.float32)
        raw_cam = read_colmap_dense(RAW / "stereo/normal_maps" / f"{name}.geometric.bin").astype(np.float32)
        if raw_depth.shape != (h, w): raw_depth = cv2.resize(raw_depth, (w, h), interpolation=cv2.INTER_LINEAR)
        if raw_cam.shape[:2] != (h, w): raw_cam = cv2.resize(raw_cam, (w, h), interpolation=cv2.INTER_LINEAR)
        raw_cam, raw_ok = normalize(raw_cam); raw_world = (raw_cam @ item.R()).astype(np.float32)
        prior_raw_target, prior_raw_ok = normalize(np.load(RAW_NORMAL_TARGET / f"{stem}.npy"))
        if np.any(prior_raw_ok & ~support): raise RuntimeError(f"prior raw-normal mask exceeds frozen depth support: {name}")
        target_ok = prior_raw_ok & fused_ok
        frozen = np.where(target_ok[..., None], fused_normal, 0).astype(np.float32)
        target = OUT_NORMAL / f"{stem}.npy"
        if target.is_file():
            if not np.array_equal(np.load(target), frozen):
                target.unlink(); np.save(target, frozen, allow_pickle=False)
        else: np.save(target, frozen, allow_pickle=False)
        native_depth = np.load(NATIVE / f"{stem}.depth.npy"); confidence = np.load(NATIVE / f"{stem}.confidence.npy")
        native_cam = np.load(NATIVE_NORMAL / f"{stem}.normal.npy")
        yy, xx = np.mgrid[:h, :w].astype(np.float32); offset_x = float(base_k[0,2]-k[0,2]); offset_y = float(base_k[1,2]-k[1,2])
        map_x = scale * (xx + offset_x + .5) - .5; map_y = scale * (yy + offset_y + .5) - .5
        native_depth = cv2.remap(native_depth, map_x, map_y, cv2.INTER_NEAREST, borderMode=cv2.BORDER_CONSTANT, borderValue=0)
        confidence = cv2.remap(confidence, map_x, map_y, cv2.INTER_NEAREST, borderMode=cv2.BORDER_CONSTANT, borderValue=0)
        native_cam = cv2.remap(native_cam, map_x, map_y, cv2.INTER_NEAREST, borderMode=cv2.BORDER_CONSTANT, borderValue=0)
        native_cam, native_ok = normalize(native_cam); native_world = (native_cam @ item.R()).astype(np.float32)
        native_ok &= np.isfinite(native_depth) & (native_depth > 0) & np.isfinite(confidence) & (confidence > 0)
        raw_common = prior_raw_ok & fused_ok; native_common = prior_raw_ok & native_ok & fused_ok
        raw_angle = angle(prior_raw_target, fused_normal, raw_common); native_angle = angle(native_world, fused_normal, native_common)
        all_raw_fused.append(raw_angle[raw_common]); all_native_fused.append(native_angle[native_common])
        row = {
            "view": name, "role": "train" if name in train else "held_out", "width": w, "height": h,
            "raw_depth_valid": int((np.isfinite(raw_depth) & (raw_depth > 0)).sum()),
            "native_filtered_depth_valid": int((native_depth > 0).sum()), "full_fused_mesh_hit": int(hit_ok.sum()),
            "frozen_supported": int(support.sum()), "fused_normal_target_valid": int(target_ok.sum()),
            "raycast_depth_abs_p99_m": q(depth_residual)["p99"],
            "raw_vs_fused_normal_median_deg": q(raw_angle[raw_common])["median"],
            "native_vs_fused_normal_median_deg": q(native_angle[native_common])["median"],
        }
        rows.append(row)
        if name in representatives:
            rgb = cv2.imread(str(RAW / "images" / name), cv2.IMREAD_COLOR)
            panel(ROOT / "representative_images/raw_native_fused" / f"{stem}.png", rgb, raw_depth, native_depth, full_depth, confidence, support, prior_raw_target, prior_raw_ok, native_world, native_ok, fused_normal, target_ok, raw_angle, native_angle)
        print(json.dumps({"view": name, "support": row["frozen_supported"], "depth_p99": row["raycast_depth_abs_p99_m"]}), flush=True)
    metrics = ROOT / "raw_native_fused_metrics.csv"
    with metrics.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0])); writer.writeheader(); writer.writerows(rows)
    depth_stats = q(np.concatenate(all_depth_residual)); raw_stats = q(np.concatenate(all_raw_fused)); native_stats = q(np.concatenate(all_native_fused))
    train_rows = [row for row in rows if row["role"] == "train"]
    target_count = sum(int(row["fused_normal_target_valid"]) for row in rows)
    support_count = sum(int(row["frozen_supported"]) for row in rows)
    prior_definition = json.loads((RAW_NORMAL_TASK / "mvs_normal_target_definition.json").read_text())
    prior_target_count = int(prior_definition["target_valid_pixels"])
    checks = {
        "mapped_views": len(rows) == int(gate["minimum_mapped_views"]),
        "train_views_with_support": sum(int(row["fused_normal_target_valid"]) >= int(gate["minimum_supported_pixels_per_train_view"]) for row in train_rows) >= int(gate["minimum_train_views_with_support"]),
        "raycast_depth_matches_frozen_fused_source": depth_stats["p99"] is not None and depth_stats["p99"] <= float(gate["maximum_raycast_depth_abs_p99_m"]),
        "normal_mask_exactly_matches_raw_normal_arm": target_count == prior_target_count,
        "unit_normal_coverage_on_frozen_normal_mask": target_count / max(prior_target_count, 1) >= float(gate["minimum_same_normal_mask_fraction"]),
    }
    definition = {
        "schema": "jointbuildgs.p2.e3_local_4906982_fused_surface_normal_v1.target.v1", "task_id": TASK_ID,
        "status": "GATE_PASSED" if all(checks.values()) else "GATE_FAILED",
        "depth_target": "unchanged frozen FUSED_VIS_CONF OpenMVS mesh camera-Z depth",
        "normal_target": "world-frame primitive normal of the exact first-hit OpenMVS mesh triangle",
        "normal_orientation": "unsigned/sign-invariant", "depth_mask": "unchanged positive-finite FUSED_VIS_CONF depth mask",
        "normal_mask": "exact prior FUSED_VIS_CONF_MVS_NORMAL nonzero target mask; only normal values change",
        "source_mesh": str(mesh_path), "source_mesh_sha256": sha256(mesh_path),
        "target_valid_pixels": target_count, "prior_raw_normal_target_valid_pixels": prior_target_count,
        "depth_support_pixels": support_count, "view_count": len(rows),
        "raycast_vs_existing_full_mesh_depth_abs_m": depth_stats,
        "raw_colmap_vs_fused_surface_normal_angle_deg": raw_stats,
        "native_filtered_vs_fused_surface_normal_angle_deg": native_stats,
        "gate_checks": checks, "lod2_training_use": False, "scientific_verdict": None,
    }
    atomic_json(ROOT / "fused_surface_normal_target_definition.json", definition)
    (ROOT / "issues.md").write_text(
        "# Issues\n\n"
        "- Frozen upstream FUSED_VIS_CONF support is absent in one of 47 train views; the inherited 46/47 support contract is unchanged.\n"
        "- `native filtered` is view-local OpenMVS DMAP evidence, while the new training target is the normal of the fused mesh first-hit triangle. They are compared but not mixed.\n"
        "- LoD2 Z, RoofSurface, roof type, semantic labels were not used to create targets or select views.\n\n"
        "scientific_verdict: null\n"
    )
    print(json.dumps(definition, indent=2, sort_keys=True))
    if not all(checks.values()): raise SystemExit(3)


if __name__ == "__main__": main()
