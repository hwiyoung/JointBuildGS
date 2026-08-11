#!/usr/bin/env python3
"""Freeze a LoD2-blind, quantity-specific fused-normal confidence mask."""
from __future__ import annotations

import csv
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys

os.environ.setdefault("OPENCV_IO_ENABLE_OPENEXR", "1")
import cv2  # noqa: E402
import matplotlib  # noqa: E402
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import yaml  # noqa: E402


REPO = Path("/workspace/JointBuildGS")
AR = Path("/artifacts/JointBuildGS")
TASK_ID = "P2-E3-LOCAL-4906982-FUSED-NORMAL-CONFIDENCE-v1"
ROOT = AR / "phase-payloads/p2/e3_local_4906982_fused_normal_confidence_v1" / TASK_ID
COMMON_TASK = AR / "phase-payloads/p2/e3_local_4906982_fused_dn_common_support_v1/P2-E3-LOCAL-4906982-FUSED-DN-COMMON-SUPPORT-v1"
FIXED_TASK = AR / "phase-payloads/p2/e3_local_4906982_fused_surface_normal_v1/P2-E3-LOCAL-4906982-FUSED-SURFACE-NORMAL-v1"
FUSED_TASK = AR / "phase-payloads/p2/e3_local_4906982_fused_vis_conf_v1/P2-E3-LOCAL-4906982-FUSED-VIS-CONF-v1"
RAW = AR / "phase-payloads/p2/e3_local_4906982_v1/P2-E3-LOCAL-4906982-2DGS-v6-dist0-resetoff-30k/data/colmap_crop"
SOURCE_DATA = FUSED_TASK / "data/fused_vis_conf_colmap_crop"
SOURCE_NORMAL = COMMON_TASK / "data/fused_surface_normal_common_support_world"
PREVIOUS_NORMAL = FIXED_TASK / "data/fused_surface_normal_world"
NATIVE = FUSED_TASK / "native_dmap"
NATIVE_NORMAL = FIXED_TASK / "native_dmap_normal"
OUT_DATA = ROOT / "data/fused_normal_confidence_colmap_crop"
OUT_NORMAL = ROOT / "data/fused_surface_normal_confidence_world"
OVERLAYS = ROOT / "representative_images/mask_overlays"
CONFIG = REPO / "configs/p2/e3_local_4906982_fused_normal_confidence_v1/common.yaml"
BASE_CONFIG = REPO / "configs/p2/e3_local_4906982_mvc_depth_v1/depth03.yaml"
SUPPORT_CONFIG = REPO / "configs/p2/e3_local_4906982_fused_vis_conf_v1/support.yaml"

sys.path.insert(0, str(REPO))
from src.stage2.colmap_io import read_cameras_bin, read_images_bin  # noqa: E402


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def atomic_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, path)


def atomic_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader(); writer.writerows(rows)
    os.replace(temporary, path)


def atomic_npy(path: Path, value: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("wb") as stream:
        np.save(stream, value, allow_pickle=False)
    if path.is_file() and np.array_equal(np.load(path), value):
        temporary.unlink(); return
    os.replace(temporary, path)


def link(path: Path, target: Path) -> None:
    if path.is_symlink():
        if path.resolve() != target.resolve():
            raise RuntimeError(f"symlink drift: {path}")
        return
    if path.exists():
        raise RuntimeError(f"refusing collision: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.symlink_to(target)


def read_exr(path: Path) -> np.ndarray:
    value = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
    if value is None:
        raise RuntimeError(f"failed to read {path}")
    return (value[..., 0] if value.ndim == 3 else value).astype(np.float32, copy=False)


def normalize(value: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    length = np.linalg.norm(value, axis=-1, keepdims=True)
    valid = np.isfinite(value).all(axis=-1) & (length[..., 0] > 0.5)
    normalized = np.where(length > 1.0e-8, value / np.maximum(length, 1.0e-8), 0)
    return normalized.astype(np.float32), valid


def blend(rgb: np.ndarray, mask: np.ndarray, color: tuple[int, int, int], alpha: float = 0.42) -> np.ndarray:
    result = rgb.astype(np.float32).copy()
    result[mask] = (1.0 - alpha) * result[mask] + alpha * np.asarray(color, np.float32)
    return np.clip(result, 0, 255).astype(np.uint8)


def difference_overlay(rgb: np.ndarray, depth: np.ndarray, previous: np.ndarray, current: np.ndarray) -> np.ndarray:
    result = rgb.copy()
    # RGB colors: depth-only blue, retained green, removed orange, newly added magenta.
    categories = (
        (depth & ~previous & ~current, (45, 120, 235)),
        (previous & current, (35, 205, 95)),
        (previous & ~current, (245, 145, 35)),
        (current & ~previous, (220, 65, 210)),
    )
    for mask, color in categories:
        result = blend(result, mask, color, 0.52)
    return result


def save_png(path: Path, rgb: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp.png")
    if not cv2.imwrite(str(temporary), cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)):
        raise RuntimeError(f"failed to write {temporary}")
    os.replace(temporary, path)


def save_panel(path: Path, rgb: np.ndarray, depth: np.ndarray, previous: np.ndarray, current: np.ndarray) -> None:
    depth_image = blend(rgb, depth, (20, 210, 235))
    previous_image = blend(rgb, previous, (245, 145, 35))
    current_image = blend(rgb, current, (220, 65, 210))
    diff = difference_overlay(rgb, depth, previous, current)
    fig, axes = plt.subplots(2, 3, figsize=(16, 9), constrained_layout=True)
    panels = (
        (rgb, "RGB"),
        (depth_image, f"Depth mask · {depth.sum():,} px"),
        (previous_image, f"Previous normal mask · {previous.sum():,} px"),
        (current_image, f"New confidence normal mask · {current.sum():,} px"),
        (diff, "Difference: blue depth-only · green retained\norange removed · magenta added"),
    )
    for axis, (image, title) in zip(axes.ravel(), panels):
        axis.imshow(image); axis.set_title(title); axis.axis("off")
    axes.ravel()[-1].axis("off")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp.png")
    fig.savefig(temporary, dpi=140); plt.close(fig); os.replace(temporary, path)


def main() -> None:
    common = yaml.safe_load(CONFIG.read_text())
    rule = common["normal_confidence_gate"]
    gate = common["target_gate"]
    base = yaml.safe_load(BASE_CONFIG.read_text())
    support_cfg = yaml.safe_load(SUPPORT_CONFIG.read_text())
    names = list(base["visible_views"]); train = set(base["train_views"])
    if len(names) != 55 or len(train) != 47:
        raise RuntimeError("frozen view membership drift")
    cameras = read_cameras_bin(RAW / "sparse/0/cameras.bin")
    images = read_images_bin(RAW / "sparse/0/images.bin")
    by_name = {item.name: item for item in images.values()}
    base_camera = next(camera for camera in cameras.values() if (camera.width, camera.height) == (1400, 1013))
    base_k = base_camera.K(); scale = float(support_cfg["alignment"]["scale"])
    threshold = float(rule["native_fused_unsigned_angle_max_deg"])
    local_threshold = float(rule["local_fused_unsigned_angle_max_deg"])
    depth_jump = float(rule["depth_neighbor_jump_max_m"])
    radius = int(rule["local_radius_px"])
    erosion = int(rule["support_erosion_radius_px"])
    if radius != 1 or erosion != 1:
        raise RuntimeError("v1 implementation locks radius and erosion to one pixel")
    kernel = np.ones((3, 3), np.uint8)
    OUT_DATA.mkdir(parents=True, exist_ok=True); OUT_NORMAL.mkdir(parents=True, exist_ok=True)
    link(OUT_DATA / "images", SOURCE_DATA / "images")
    link(OUT_DATA / "sparse", SOURCE_DATA / "sparse")
    link(OUT_DATA / "depth", SOURCE_DATA / "depth")
    representatives = {names[0], names[8], names[23], names[-1]}
    rows: list[dict] = []
    totals = {key: 0 for key in ("depth", "previous", "current", "retained", "removed", "added")}
    all_angles: list[np.ndarray] = []
    for name in names:
        item = by_name[name]; camera = cameras[item.camera_id]; h, w = camera.height, camera.width
        stem = Path(name).stem
        depth = read_exr(SOURCE_DATA / "depth" / f"{stem}.exr")
        depth_mask = np.isfinite(depth) & (depth > 0)
        fused, fused_valid = normalize(np.load(SOURCE_NORMAL / f"{stem}.npy"))
        previous, previous_mask = normalize(np.load(PREVIOUS_NORMAL / f"{stem}.npy"))
        if not np.array_equal(fused_valid, depth_mask):
            raise RuntimeError(f"common fused normal/depth mask drift: {name}")
        if np.any(previous_mask & ~depth_mask):
            raise RuntimeError(f"previous normal mask exceeds depth mask: {name}")
        native_cam = np.load(NATIVE_NORMAL / f"{stem}.normal.npy")
        native_depth = np.load(NATIVE / f"{stem}.depth.npy")
        native_confidence = np.load(NATIVE / f"{stem}.confidence.npy")
        yy, xx = np.mgrid[:h, :w].astype(np.float32)
        k = camera.K(); offset_x = float(base_k[0, 2] - k[0, 2]); offset_y = float(base_k[1, 2] - k[1, 2])
        map_x = scale * (xx + offset_x + 0.5) - 0.5
        map_y = scale * (yy + offset_y + 0.5) - 0.5
        native_cam = cv2.remap(native_cam, map_x, map_y, cv2.INTER_NEAREST, borderMode=cv2.BORDER_CONSTANT, borderValue=0)
        native_depth = cv2.remap(native_depth, map_x, map_y, cv2.INTER_NEAREST, borderMode=cv2.BORDER_CONSTANT, borderValue=0)
        native_confidence = cv2.remap(native_confidence, map_x, map_y, cv2.INTER_NEAREST, borderMode=cv2.BORDER_CONSTANT, borderValue=0)
        native_cam, native_valid = normalize(native_cam)
        native_world = (native_cam @ item.R()).astype(np.float32)
        native_valid &= np.isfinite(native_depth) & (native_depth > 0) & np.isfinite(native_confidence) & (native_confidence > 0)
        unsigned_dot = np.clip(np.abs(np.sum(native_world * fused, axis=-1)), 0, 1)
        agreement = native_valid & (unsigned_dot >= np.cos(np.deg2rad(threshold)))
        eroded = cv2.erode(depth_mask.astype(np.uint8), kernel, iterations=1).astype(bool)
        depth_range = cv2.dilate(depth, kernel) - cv2.erode(depth, kernel)
        depth_stable = eroded & np.isfinite(depth_range) & (depth_range <= depth_jump)
        minimum_neighbor_dot = np.ones((h, w), np.float32)
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                if dy == 0 and dx == 0:
                    continue
                neighbor = np.roll(fused, shift=(dy, dx), axis=(0, 1))
                dot = np.clip(np.abs(np.sum(fused * neighbor, axis=-1)), 0, 1)
                minimum_neighbor_dot = np.minimum(minimum_neighbor_dot, dot)
        local_stable = eroded & (minimum_neighbor_dot >= np.cos(np.deg2rad(local_threshold)))
        current = depth_mask & agreement & depth_stable & local_stable
        frozen = np.where(current[..., None], fused, 0).astype(np.float32)
        atomic_npy(OUT_NORMAL / f"{stem}.npy", frozen)
        retained = previous_mask & current; removed = previous_mask & ~current; added = current & ~previous_mask
        angle_values = np.degrees(np.arccos(unsigned_dot[depth_mask & native_valid]))
        all_angles.append(angle_values.astype(np.float32))
        row = {
            "view": name, "role": "train" if name in train else "held_out", "width": w, "height": h,
            "depth_mask_pixels": int(depth_mask.sum()), "previous_normal_mask_pixels": int(previous_mask.sum()),
            "new_normal_mask_pixels": int(current.sum()), "retained_from_previous": int(retained.sum()),
            "removed_from_previous": int(removed.sum()), "added_vs_previous": int(added.sum()),
            "new_fraction_of_depth": float(current.sum() / max(depth_mask.sum(), 1)),
            "native_valid_on_depth": int((native_valid & depth_mask).sum()),
            "native_agreement_pass": int((agreement & depth_mask).sum()),
            "depth_edge_pass": int((depth_stable & depth_mask).sum()),
            "local_normal_stability_pass": int((local_stable & depth_mask).sum()),
        }
        rows.append(row)
        for key, value in (("depth", depth_mask), ("previous", previous_mask), ("current", current), ("retained", retained), ("removed", removed), ("added", added)):
            totals[key] += int(value.sum())
        rgb_bgr = cv2.imread(str(RAW / "images" / name), cv2.IMREAD_COLOR)
        if rgb_bgr is None:
            raise RuntimeError(f"failed to read RGB: {name}")
        rgb = cv2.cvtColor(rgb_bgr, cv2.COLOR_BGR2RGB)
        view_dir = ROOT / "mask_overlay_views" / stem
        save_png(view_dir / "rgb.png", rgb)
        save_png(view_dir / "depth.png", blend(rgb, depth_mask, (20, 210, 235)))
        save_png(view_dir / "previous.png", blend(rgb, previous_mask, (245, 145, 35)))
        save_png(view_dir / "confidence.png", blend(rgb, current, (220, 65, 210)))
        save_png(view_dir / "difference.png", difference_overlay(rgb, depth_mask, previous_mask, current))
        if name in representatives:
            save_panel(OVERLAYS / f"{stem}.png", rgb, depth_mask, previous_mask, current)
    atomic_csv(ROOT / "normal_confidence_mask_metrics.csv", rows)
    supported_train = sum(row["new_normal_mask_pixels"] >= int(gate["minimum_pixels_per_supported_train_view"]) for row in rows if row["role"] == "train")
    fraction = totals["current"] / max(totals["depth"], 1)
    all_angle = np.concatenate(all_angles) if all_angles else np.empty(0, np.float32)
    checks = {
        "mapped_views": len(rows) == int(gate["minimum_mapped_views"]),
        "train_views_with_support": supported_train >= int(gate["minimum_train_views_with_support"]),
        "coverage_above_minimum": fraction >= float(gate["minimum_fraction_of_depth_support"]),
        "coverage_below_maximum": fraction <= float(gate["maximum_fraction_of_depth_support"]),
        "strict_subset_of_depth_mask": totals["current"] < totals["depth"],
        "all_current_pixels_inside_depth_mask": all(row["new_normal_mask_pixels"] <= row["depth_mask_pixels"] for row in rows),
        "lod2_geometry_unused": True,
    }
    definition = {
        "schema": "jointbuildgs.p2.e3_local_4906982_fused_normal_confidence_v1.target.v1",
        "task_id": TASK_ID, "status": "GATE_PASSED" if all(checks.values()) else "GATE_FAILED",
        "mask_formula": "M_depth & native_valid & angle(native,fused)<=15deg & erode(M_depth,1px) & local_max_angle<=15deg & local_depth_range<=1m",
        "thresholds": rule, "depth_mask_pixels": totals["depth"],
        "previous_normal_mask_pixels": totals["previous"], "target_valid_pixels": totals["current"],
        "retained_from_previous": totals["retained"], "removed_from_previous": totals["removed"],
        "added_vs_previous": totals["added"], "new_fraction_of_depth": fraction,
        "train_views_with_support": supported_train, "gate_checks": checks,
        "native_fused_unsigned_angle_deg_on_depth_native_valid": {
            "median": float(np.quantile(all_angle, 0.5)), "p90": float(np.quantile(all_angle, 0.9)),
            "p95": float(np.quantile(all_angle, 0.95)), "p99": float(np.quantile(all_angle, 0.99)),
        },
        "sources": {
            "depth": str(SOURCE_DATA / "depth"), "fused_normal": str(SOURCE_NORMAL),
            "previous_normal_mask": str(PREVIOUS_NORMAL), "native_normal": str(NATIVE_NORMAL),
        },
        "source_definition_sha256": {
            "common_support": sha256(COMMON_TASK / "fused_dn_common_support_target_definition.json"),
            "fixed_mask": sha256(FIXED_TASK / "fused_surface_normal_target_definition.json"),
        },
        "lod2_training_use": False, "scientific_verdict": None,
    }
    atomic_json(ROOT / "fused_normal_confidence_definition.json", definition)
    atomic_json(ROOT / "mask_visualization_receipt.json", {
        "schema": "jointbuildgs.p2.e3_local_4906982_fused_normal_confidence_v1.mask_visualization.v1",
        "view_count": len(rows), "representative_panels": sorted(str(path.relative_to(ROOT)) for path in OVERLAYS.glob("*.png")),
        "per_view_overlays": 5 * len(rows), "generated_before_training": True,
        "training_checkpoint_directory_absent_at_generation": not (ROOT / "arms/FUSED_VIS_CONF_FUSED_NORMAL_CONFIDENCE/R1/ckpt").exists(),
        "scientific_verdict": None,
    })
    print(json.dumps(definition, indent=2, sort_keys=True))
    if not all(checks.values()):
        raise SystemExit(2)


if __name__ == "__main__":
    main()
