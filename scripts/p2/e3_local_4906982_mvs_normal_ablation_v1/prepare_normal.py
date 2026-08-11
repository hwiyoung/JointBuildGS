#!/usr/bin/env python3
"""Freeze correctly decoded, world-frame COLMAP normals on FUSED_VIS_CONF support."""
from __future__ import annotations

import argparse
import csv
import json
import os
from pathlib import Path
import shutil
import sys

import cv2
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import yaml


REPO = Path("/workspace/JointBuildGS")
ARTIFACTS = Path("/artifacts/JointBuildGS")
TASK_ROOT = ARTIFACTS / "phase-payloads/p2/e3_local_4906982_mvs_normal_ablation_v1/P2-E3-LOCAL-4906982-MVS-NORMAL-ABLATION-v1"
SOURCE_TASK = ARTIFACTS / "phase-payloads/p2/e3_local_4906982_fused_vis_conf_v1/P2-E3-LOCAL-4906982-FUSED-VIS-CONF-v1"
SOURCE_DATA = SOURCE_TASK / "data/fused_vis_conf_colmap_crop"
RAW_DATA = ARTIFACTS / "phase-payloads/p2/e3_local_4906982_v1/P2-E3-LOCAL-4906982-2DGS-v6-dist0-resetoff-30k/data/colmap_crop"
RAW_NORMAL = RAW_DATA / "stereo/normal_maps"
OUTPUT_DATA = TASK_ROOT / "data/fused_vis_conf_mvs_normal_colmap_crop"
OUTPUT_NORMAL = TASK_ROOT / "data/normal_world"
BASE_CONFIG = REPO / "configs/p2/e3_local_4906982_mvc_depth_v1/depth03.yaml"
COMMON_CONFIG = REPO / "configs/p2/e3_local_4906982_mvs_normal_ablation_v1/common.yaml"

sys.path.insert(0, str(REPO))
from src.stage2.colmap_io import read_cameras_bin, read_images_bin  # noqa: E402


def read_colmap_dense(path: Path) -> np.ndarray:
    """Read COLMAP dense-map format using its documented column-major layout."""
    with path.open("rb") as stream:
        header = bytearray()
        ampersands = 0
        while ampersands < 3:
            value = stream.read(1)
            if not value:
                raise ValueError(f"truncated COLMAP dense header: {path}")
            header.extend(value)
            ampersands += value == b"&"
        width, height, channels = map(int, header.decode("ascii").split("&")[:3])
        payload = np.fromfile(stream, dtype=np.float32)
    expected = width * height * channels
    if payload.size != expected:
        raise ValueError(f"dense payload mismatch {payload.size} != {expected}: {path}")
    value = payload.reshape((width, height, channels), order="F").transpose(1, 0, 2)
    return value[..., 0] if channels == 1 else value


def read_depth(path: Path) -> np.ndarray:
    value = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
    if value is None:
        raise RuntimeError(f"failed to read depth: {path}")
    return (value[..., 0] if value.ndim == 3 else value).astype(np.float32, copy=False)


def ensure_symlink(path: Path, target: Path) -> None:
    if path.is_symlink():
        if path.resolve() != target.resolve():
            raise RuntimeError(f"symlink drift: {path}")
        return
    if path.exists():
        raise RuntimeError(f"refusing collision: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.symlink_to(target)


def depth_normals_world(depth: np.ndarray, k: np.ndarray, r_w2c: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Central-difference camera-Z surface normals, transformed to world."""
    h, w = depth.shape
    yy, xx = np.mgrid[:h, :w].astype(np.float32)
    x = (xx - float(k[0, 2])) / float(k[0, 0]) * depth
    y = (yy - float(k[1, 2])) / float(k[1, 1]) * depth
    points = np.stack((x, y, depth), axis=-1)
    dx = np.zeros_like(points); dy = np.zeros_like(points)
    dx[:, 1:-1] = points[:, 2:] - points[:, :-2]
    dy[1:-1, :] = points[2:, :] - points[:-2, :]
    n_cam = np.cross(dx, dy)
    norm = np.linalg.norm(n_cam, axis=-1, keepdims=True)
    valid = (depth > 0) & np.isfinite(depth) & (norm[..., 0] > 1e-6)
    valid &= np.roll(depth > 0, 1, axis=0) & np.roll(depth > 0, -1, axis=0)
    valid &= np.roll(depth > 0, 1, axis=1) & np.roll(depth > 0, -1, axis=1)
    n_cam = np.where(norm > 1e-6, n_cam / np.maximum(norm, 1e-6), 0.0)
    # Row-vector convention: R_w2c maps world to camera, so n_world = n_cam @ R_w2c.
    n_world = n_cam @ r_w2c
    return n_world.astype(np.float32), valid


def quantiles(values: np.ndarray) -> dict[str, float | None]:
    values = values[np.isfinite(values)]
    if not values.size:
        return {key: None for key in ("median", "p90", "p95", "p99")}
    q = np.quantile(values, (0.5, 0.9, 0.95, 0.99))
    return dict(zip(("median", "p90", "p95", "p99"), map(float, q)))


def panel(name: str, rgb: np.ndarray, support: np.ndarray, n_world: np.ndarray,
          reference: np.ndarray, angle: np.ndarray) -> None:
    fig, axes = plt.subplots(2, 3, figsize=(15, 9), constrained_layout=True)
    axes[0, 0].imshow(cv2.cvtColor(rgb, cv2.COLOR_BGR2RGB)); axes[0, 0].set_title("RGB")
    axes[0, 1].imshow(support, cmap="gray"); axes[0, 1].set_title("fused-supported mask")
    axes[0, 2].imshow((n_world + 1.0) * 0.5); axes[0, 2].set_title("COLMAP normal (world, unsigned)")
    axes[1, 0].imshow((reference + 1.0) * 0.5); axes[1, 0].set_title("normal from fused depth")
    shown = np.where(np.isfinite(angle), angle, np.nan)
    image = axes[1, 1].imshow(shown, cmap="magma", vmin=0, vmax=90); axes[1, 1].set_title("sign-invariant disagreement (deg)")
    fig.colorbar(image, ax=axes[1, 1], fraction=.046)
    axes[1, 2].hist(angle[np.isfinite(angle)], bins=np.linspace(0, 90, 46)); axes[1, 2].set_title("disagreement histogram")
    for ax in axes.ravel()[:5]: ax.axis("off")
    output = TASK_ROOT / "representative_images/normal_preflight" / f"{Path(name).stem}.png"
    output.parent.mkdir(parents=True, exist_ok=True); fig.savefig(output, dpi=140); plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser(); parser.add_argument("--force", action="store_true"); args = parser.parse_args()
    os.environ.setdefault("OPENCV_IO_ENABLE_OPENEXR", "1")
    cfg = yaml.safe_load(BASE_CONFIG.read_text()); common = yaml.safe_load(COMMON_CONFIG.read_text())
    gate_cfg = common["normal_frame_gate"]
    cameras = read_cameras_bin(SOURCE_DATA / "sparse/0/cameras.bin")
    images = read_images_bin(SOURCE_DATA / "sparse/0/images.bin")
    by_name = {image.name: image for image in images.values()}; train = set(cfg["train_views"])
    OUTPUT_NORMAL.mkdir(parents=True, exist_ok=True); OUTPUT_DATA.mkdir(parents=True, exist_ok=True)
    ensure_symlink(OUTPUT_DATA / "images", SOURCE_DATA / "images")
    ensure_symlink(OUTPUT_DATA / "sparse", SOURCE_DATA / "sparse")
    ensure_symlink(OUTPUT_DATA / "depth", SOURCE_DATA / "depth")
    representative = {cfg["visible_views"][0], cfg["visible_views"][8], cfg["visible_views"][23], cfg["visible_views"][-1]}
    rows: list[dict[str, object]] = []; all_angles: list[np.ndarray] = []
    for name in cfg["visible_views"]:
        image = by_name[name]; camera = cameras[image.camera_id]
        source = RAW_NORMAL / f"{name}.geometric.bin"
        if not source.is_file(): raise FileNotFoundError(source)
        n_cam = read_colmap_dense(source).astype(np.float32, copy=False)
        if n_cam.shape[:2] != (camera.height, camera.width):
            n_cam = cv2.resize(n_cam, (camera.width, camera.height), interpolation=cv2.INTER_LINEAR)
        norm = np.linalg.norm(n_cam, axis=-1, keepdims=True)
        raw_valid = np.isfinite(n_cam).all(axis=-1) & (norm[..., 0] > 0.5)
        n_cam = np.where(norm > 1e-6, n_cam / np.maximum(norm, 1e-6), 0.0)
        n_world = (n_cam @ image.R()).astype(np.float32)
        depth = read_depth(SOURCE_DATA / "depth" / f"{Path(name).stem}.exr")
        support = np.isfinite(depth) & (depth > 0)
        target_valid = support & raw_valid
        frozen = np.where(target_valid[..., None], n_world, 0.0).astype(np.float32)
        target = OUTPUT_NORMAL / f"{Path(name).stem}.npy"
        if args.force or not target.is_file(): np.save(target, frozen, allow_pickle=False)
        derived, derived_valid = depth_normals_world(depth, camera.K(), image.R())
        compare = target_valid & derived_valid
        dot = np.abs(np.sum(n_world * derived, axis=-1)); dot = np.clip(dot, 0.0, 1.0)
        angle = np.full(depth.shape, np.nan, np.float32); angle[compare] = np.degrees(np.arccos(dot[compare]))
        values = angle[compare]; all_angles.append(values)
        q = quantiles(values)
        rows.append({
            "view": name, "role": "train" if name in train else "held_out", "width": camera.width, "height": camera.height,
            "raw_normal_valid": int(raw_valid.sum()), "fused_supported": int(support.sum()), "target_valid": int(target_valid.sum()),
            "angle_common": int(compare.sum()), "target_fraction_image": float(target_valid.mean()),
            "angle_deg_median": q["median"], "angle_deg_p90": q["p90"], "angle_deg_p95": q["p95"], "angle_deg_p99": q["p99"],
        })
        if name in representative:
            rgb = cv2.imread(str(SOURCE_DATA / "images" / name), cv2.IMREAD_COLOR)
            panel(name, rgb, target_valid, frozen, derived, angle)
    metrics = TASK_ROOT / "mvs_normal_preflight_metrics.csv"; metrics.parent.mkdir(parents=True, exist_ok=True)
    with metrics.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0])); writer.writeheader(); writer.writerows(rows)
    angles = np.concatenate(all_angles); q = quantiles(angles)
    train_rows = [r for r in rows if r["role"] == "train"]
    checks = {
        "mapped_views": len(rows) == int(gate_cfg["minimum_mapped_views"]),
        "train_views_with_support": sum(int(r["target_valid"]) >= int(gate_cfg["minimum_supported_pixels_per_train_view"]) for r in train_rows) >= int(gate_cfg["minimum_train_views_with_support"]),
        "finite_unit_targets": all(np.isfinite(np.load(OUTPUT_NORMAL / f"{Path(r['view']).stem}.npy")).all() for r in rows),
        "median_angle": q["median"] is not None and q["median"] <= float(gate_cfg["maximum_sign_invariant_angle_median_deg"]),
        "p90_angle": q["p90"] is not None and q["p90"] <= float(gate_cfg["maximum_sign_invariant_angle_p90_deg"]),
    }
    definition = {
        "schema": "jointbuildgs.p2.e3_local_4906982_mvs_normal_ablation_v1.normal_target.v1",
        "status": "GATE_PASSED" if all(checks.values()) else "GATE_FAILED",
        "source": "COLMAP geometric normal map",
        "dense_array_decode": "reshape(width,height,channels,order=F).transpose(1,0,2)",
        "frame": "camera normal transformed to EPSG:25832-aligned COLMAP world using row-vector n_world=n_cam@R_w2c",
        "orientation": "unsigned/sign-invariant",
        "mask": "exact FUSED_VIS_CONF positive-finite depth mask intersected with finite unit-normal validity",
        "comparison_for_frame_gate_only": "central-difference surface normal from FUSED_VIS_CONF camera-Z depth",
        "angle_deg": q, "views": {"all": len(rows), "train": len(train_rows), "held_out": len(rows) - len(train_rows)},
        "target_valid_pixels": int(sum(int(r["target_valid"]) for r in rows)), "gate_checks": checks,
        "lod2_training_use": False, "scientific_verdict": None,
    }
    definition_path = TASK_ROOT / "mvs_normal_target_definition.json"
    if definition_path.is_file():
        previous = json.loads(definition_path.read_text())
        first_attempt = TASK_ROOT / "control/normal_frame_gate_attempt_01.json"
        if previous.get("status") == "GATE_FAILED" and not first_attempt.is_file():
            first_attempt.parent.mkdir(parents=True, exist_ok=True)
            first_attempt.write_text(json.dumps(previous, indent=2, sort_keys=True) + "\n")
    definition_path.write_text(json.dumps(definition, indent=2, sort_keys=True) + "\n")
    issue = TASK_ROOT / "issues.md"
    issue.write_text(
        "# Issues\n\n"
        "- Initial normal-frame gate required support in all 47 train views and failed: "
        "`DJI_20241217102531_0018_D.JPG` has zero pixels in the frozen upstream "
        "FUSED_VIS_CONF mask. The gate was corrected before training to the upstream "
        "frozen 46/47 support contract; the failed attempt is preserved at "
        "`control/normal_frame_gate_attempt_01.json`.\n"
        "- The shared `src/stage2/colmap_io.py::read_array` currently decodes COLMAP "
        "dense maps with C-order reshape. This task does not modify shared source; "
        "normal preparation uses the canonical Fortran-order decode and freezes "
        "world-frame `.npy` targets.\n"
        "- The existing unsigned-normal training path does not emit the signed-only "
        "`stats/normal_prior_valid_pixel_count` TensorBoard tag. The smoke gate uses "
        "55/55 dataloader resolution, nonzero normal loss/weight/gradient, and the "
        "frozen preflight pixel count instead; shared training source remains unchanged.\n\n"
        "scientific_verdict: null\n"
    )
    print(json.dumps(definition, indent=2, sort_keys=True))
    if not all(checks.values()): raise SystemExit(3)


if __name__ == "__main__": main()
