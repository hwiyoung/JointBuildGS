#!/usr/bin/env python3
"""Align native OpenMVS filtered depth/confidence and freeze a fused support mask."""
from __future__ import annotations

import argparse
import csv
import json
import os
from pathlib import Path
import sys

import cv2
import matplotlib.pyplot as plt
import numpy as np
import yaml

REPO = Path("/workspace/JointBuildGS")
ARTIFACTS = Path("/artifacts/JointBuildGS")
TASK_ROOT = ARTIFACTS / "phase-payloads/p2/e3_local_4906982_fused_vis_conf_v1/P2-E3-LOCAL-4906982-FUSED-VIS-CONF-v1"
LOCAL_ROOT = ARTIFACTS / "phase-payloads/p2/e3_local_4906982_v1/P2-E3-LOCAL-4906982-2DGS-v6-dist0-resetoff-30k/data/colmap_crop"
RAW_DEPTH = LOCAL_ROOT / "stereo/depth_maps"
FUSED_ROOT = ARTIFACTS / "phase-payloads/p2/e3_local_4906982_mvs_surface_depth_v1/P2-E3-LOCAL-4906982-MVS-SURFACE-DEPTH-v1/data/mvs_surface_colmap_crop"
FUSED_DEPTH = FUSED_ROOT / "depth"
NATIVE = TASK_ROOT / "native_dmap"
OUTPUT_DATA = TASK_ROOT / "data/fused_vis_conf_colmap_crop"
BASE_CONFIG = REPO / "configs/p2/e3_local_4906982_mvc_depth_v1/depth03.yaml"
SUPPORT_CONFIG = REPO / "configs/p2/e3_local_4906982_fused_vis_conf_v1/support.yaml"

sys.path.insert(0, str(REPO))
from src.stage2.colmap_io import read_array, read_cameras_bin, read_images_bin  # noqa: E402


def read_exr(path: Path) -> np.ndarray:
    value = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
    if value is None:
        raise RuntimeError(f"failed to read {path}")
    if value.ndim == 3:
        value = value[..., 0]
    return value.astype(np.float32, copy=False)


def ensure_symlink(path: Path, target: Path) -> None:
    if path.is_symlink():
        if path.resolve() != target.resolve():
            raise RuntimeError(f"symlink drift: {path} -> {path.resolve()} != {target.resolve()}")
        return
    if path.exists():
        raise RuntimeError(f"refusing to replace existing path: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.symlink_to(target)


def quantiles(values: np.ndarray) -> dict[str, float | None]:
    values = values[np.isfinite(values)]
    if not values.size:
        return {key: None for key in ("median", "p90", "p95", "p99")}
    q = np.quantile(values, [0.5, 0.9, 0.95, 0.99])
    return dict(zip(("median", "p90", "p95", "p99"), map(float, q)))


def render_panel(name: str, rgb: np.ndarray, raw: np.ndarray, fused: np.ndarray,
                 native: np.ndarray, confidence: np.ndarray, state: np.ndarray) -> None:
    valid = np.concatenate([
        raw[np.isfinite(raw) & (raw > 0)], fused[np.isfinite(fused) & (fused > 0)],
        native[np.isfinite(native) & (native > 0)],
    ])
    lo, hi = np.quantile(valid, [0.02, 0.98]) if valid.size else (0.0, 1.0)
    fig, axes = plt.subplots(2, 3, figsize=(15, 9), constrained_layout=True)
    axes[0, 0].imshow(cv2.cvtColor(rgb, cv2.COLOR_BGR2RGB)); axes[0, 0].set_title("RGB")
    for ax, image, title in (
        (axes[0, 1], raw, "raw COLMAP depth"),
        (axes[0, 2], fused, "fused mesh target"),
        (axes[1, 0], native, "native OpenMVS filtered depth"),
    ):
        shown=np.where(np.isfinite(image) & (image > 0), image, np.nan)
        ax.imshow(shown, cmap="turbo", vmin=lo, vmax=hi); ax.set_title(title)
    conf_show=np.where(np.isfinite(confidence) & (confidence > 0), confidence, np.nan)
    axes[1, 1].imshow(conf_show, cmap="magma"); axes[1, 1].set_title("native confidence")
    axes[1, 2].imshow(state, cmap="viridis", vmin=0, vmax=3)
    axes[1, 2].set_title("state: 0 none, 1 support, 2 mismatch, 3 fused-only")
    for ax in axes.ravel(): ax.axis("off")
    out = TASK_ROOT / "representative_images/support" / f"{Path(name).stem}.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=140)
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    os.environ.setdefault("OPENCV_IO_ENABLE_OPENEXR", "1")
    cfg = yaml.safe_load(BASE_CONFIG.read_text())
    support_cfg = yaml.safe_load(SUPPORT_CONFIG.read_text())
    train = set(cfg["train_views"])
    cameras = read_cameras_bin(LOCAL_ROOT / "sparse/0/cameras.bin")
    images = read_images_bin(LOCAL_ROOT / "sparse/0/images.bin")
    by_name = {image.name: image for image in images.values()}
    base_camera = next(c for c in cameras.values() if (c.width, c.height) == (1400, 1013))
    base_k = base_camera.K()
    scale = float(support_cfg["alignment"]["scale"])
    tolerance = 0.01

    OUTPUT_DATA.mkdir(parents=True, exist_ok=True)
    (OUTPUT_DATA / "depth").mkdir(exist_ok=True)
    ensure_symlink(OUTPUT_DATA / "images", LOCAL_ROOT / "images")
    ensure_symlink(OUTPUT_DATA / "sparse", LOCAL_ROOT / "sparse")

    representative = {
        "DJI_20241217084805_0166_D.JPG",
        "DJI_20241217094917_0005_D.JPG",
        "DJI_20241217095023_0038_D.JPG",
        "DJI_20241217102531_0018_D.JPG",
    }
    rows: list[dict[str, object]] = []
    for name in cfg["visible_views"]:
        image = by_name[name]
        camera = cameras[image.camera_id]
        k = camera.K()
        stem = Path(name).stem
        native_depth = np.load(NATIVE / f"{stem}.depth.npy")
        native_conf = np.load(NATIVE / f"{stem}.confidence.npy")
        fused = read_exr(FUSED_DEPTH / f"{stem}.exr")
        raw = read_array(RAW_DEPTH / f"{name}.geometric.bin").astype(np.float32, copy=False)
        if raw.shape != (camera.height, camera.width):
            raw = cv2.resize(raw, (camera.width, camera.height), interpolation=cv2.INTER_LINEAR)
        yy, xx = np.mgrid[:camera.height, :camera.width].astype(np.float32)
        offset_x = float(base_k[0, 2] - k[0, 2])
        offset_y = float(base_k[1, 2] - k[1, 2])
        map_x = scale * (xx + offset_x + 0.5) - 0.5
        map_y = scale * (yy + offset_y + 0.5) - 0.5
        aligned_depth = cv2.remap(native_depth, map_x, map_y, cv2.INTER_NEAREST,
                                  borderMode=cv2.BORDER_CONSTANT, borderValue=0)
        aligned_conf = cv2.remap(native_conf, map_x, map_y, cv2.INTER_NEAREST,
                                 borderMode=cv2.BORDER_CONSTANT, borderValue=0)
        raw_valid = np.isfinite(raw) & (raw > 0)
        fused_valid = np.isfinite(fused) & (fused > 0)
        native_valid = (np.isfinite(aligned_depth) & (aligned_depth > 0) &
                        np.isfinite(aligned_conf) & (aligned_conf > 0))
        common = fused_valid & native_valid
        relative = np.full(fused.shape, np.nan, np.float32)
        relative[common] = np.abs(aligned_depth[common] - fused[common]) / aligned_depth[common]
        supported = common & (relative < tolerance)
        contradicted = common & ~supported
        fused_only = fused_valid & ~native_valid
        masked = np.where(supported, fused, 0.0).astype(np.float32)
        target = OUTPUT_DATA / "depth" / f"{stem}.exr"
        if args.force or not target.exists():
            if not cv2.imwrite(str(target), masked):
                raise RuntimeError(f"failed to write {target}")
        state = np.zeros(fused.shape, np.uint8)
        state[supported] = 1; state[contradicted] = 2; state[fused_only] = 3
        residual = np.abs(aligned_depth[common] - fused[common])
        relative_values = relative[common]
        row = {
            "view": name,
            "role": "train" if name in train else "held_out",
            "width": camera.width, "height": camera.height,
            "crop_offset_x": offset_x, "crop_offset_y": offset_y,
            "pixels": int(fused.size),
            "raw_valid": int(raw_valid.sum()), "fused_valid": int(fused_valid.sum()),
            "native_valid": int(native_valid.sum()), "common_native_fused": int(common.sum()),
            "supported": int(supported.sum()), "contradicted": int(contradicted.sum()),
            "fused_only": int(fused_only.sum()),
            "supported_fraction_pixels": float(supported.mean()),
            "supported_fraction_fused": float(supported.sum() / max(int(fused_valid.sum()), 1)),
            "native_fused_abs_median": quantiles(residual)["median"],
            "native_fused_abs_p90": quantiles(residual)["p90"],
            "native_fused_rel_median": quantiles(relative_values)["median"],
            "native_fused_rel_p90": quantiles(relative_values)["p90"],
        }
        rows.append(row)
        if name in representative:
            rgb = cv2.imread(str(LOCAL_ROOT / "images" / name), cv2.IMREAD_COLOR)
            render_panel(name, rgb, raw, fused, aligned_depth, aligned_conf, state)

    metrics_path = TASK_ROOT / "fusion_support_metrics.csv"
    with metrics_path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader(); writer.writerows(rows)

    groups = {}
    for role, selected in (("train", [r for r in rows if r["role"] == "train"]),
                           ("held_out", [r for r in rows if r["role"] == "held_out"]),
                           ("all", rows)):
        totals = {key: sum(int(r[key]) for r in selected) for key in
                  ("pixels", "raw_valid", "fused_valid", "native_valid", "common_native_fused", "supported", "contradicted", "fused_only")}
        totals.update({
            "views": len(selected),
            "views_with_support": sum(int(r["supported"]) > 0 for r in selected),
            "supported_fraction_pixels": totals["supported"] / totals["pixels"],
            "supported_fraction_fused": totals["supported"] / totals["fused_valid"],
            "supported_fraction_native": totals["supported"] / totals["native_valid"],
        })
        groups[role] = totals
    gate_cfg = support_cfg["gate"]
    checks = {
        "mapped_views": len(rows) >= int(gate_cfg["minimum_mapped_views"]),
        "train_views_with_support": groups["train"]["views_with_support"] >= int(gate_cfg["minimum_train_views_with_support"]),
        "train_supported_fraction_fused": groups["train"]["supported_fraction_fused"] >= float(gate_cfg["minimum_train_supported_fraction_of_fused"]),
    }
    definition = {
        "schema": "jointbuildgs.p2.e3_local_4906982_fused_vis_conf_v1.definition.v1",
        "status": "GATE_PASSED" if all(checks.values()) else "GATE_FAILED",
        "target": "nearest OpenMVS mesh ray-hit camera-Z, unchanged from MVS_SURFACE_METRIC",
        "mask": "fused positive-finite AND native filtered dmap positive-finite AND native confidence positive AND abs(D_native-D_fused)/D_native < 0.01",
        "tolerance_source": "OpenMVS fDepthDiffThreshold=0.01; recovered run used optimize=7 and number-views-fuse=2",
        "confidence_threshold": "positive finite only; no outcome-tuned quantile",
        "alignment": support_cfg["alignment"],
        "groups": groups,
        "gate_checks": checks,
        "lod2_training_use": False,
        "scientific_verdict": None,
    }
    (TASK_ROOT / "fusion_support_definition.json").write_text(json.dumps(definition, indent=2) + "\n")
    print(json.dumps(definition, indent=2))
    if not all(checks.values()):
        raise SystemExit(3)


if __name__ == "__main__":
    main()
