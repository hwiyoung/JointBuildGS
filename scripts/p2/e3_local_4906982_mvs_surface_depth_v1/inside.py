#!/usr/bin/env python3
"""Container-only OpenMVS mesh-depth preparation for DEBY_LOD2_4906982."""
from __future__ import annotations

import csv
import hashlib
import json
import os
from pathlib import Path
from typing import Any

os.environ.setdefault("OPENCV_IO_ENABLE_OPENEXR", "1")
import cv2  # noqa: E402
import matplotlib  # noqa: E402
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import open3d as o3d  # noqa: E402
import yaml  # noqa: E402

from src.stage2.dataloader import ColmapDataset


REPO = Path("/workspace/JointBuildGS")
AR = Path("/artifacts/JointBuildGS")
TASK_ID = "P2-E3-LOCAL-4906982-MVS-SURFACE-DEPTH-v1"
ROOT = AR / "phase-payloads/p2/e3_local_4906982_mvs_surface_depth_v1" / TASK_ID
SOURCE_DATA = AR / "phase-payloads/p2/e3_local_4906982_v1/P2-E3-LOCAL-4906982-2DGS-v6-dist0-resetoff-30k/data/colmap_crop"
DATA = ROOT / "data/mvs_surface_colmap_crop"
DEPTH_DIR = DATA / "depth"
BASE_CONFIG = REPO / "configs/p2/e3_local_4906982_mvc_depth_v1/depth03.yaml"
PROJECTION_CONFIG = REPO / "configs/p2/e3_local_4906982_mvs_surface_depth_v1/projection.yaml"
REPRESENTATIVE = {
    "DJI_20241217084805_0166_D.JPG",
    "DJI_20241217084815_0171_D.JPG",
    "DJI_20241217095023_0038_D.JPG",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def atomic_json(path: Path, body: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(body, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, path)


def ensure_symlink(path: Path, target: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        if os.readlink(path) != str(target):
            raise RuntimeError(f"symlink drift: {path} -> {os.readlink(path)}")
        return
    if path.exists():
        raise RuntimeError(f"task-local data binding is not the expected symlink: {path}")
    path.symlink_to(target, target_is_directory=True)


def write_exr(path: Path, depth: np.ndarray) -> None:
    temporary = path.with_name(path.stem + ".tmp.exr")
    if temporary.exists():
        temporary.unlink()
    if not cv2.imwrite(str(temporary), np.asarray(depth, dtype=np.float32)):
        raise RuntimeError(f"OpenEXR write failed: {path}")
    os.replace(temporary, path)


def save_panel(path: Path, rgb: np.ndarray, raw: np.ndarray, mesh: np.ndarray) -> None:
    raw_valid = np.isfinite(raw) & (raw > 0)
    mesh_valid = np.isfinite(mesh) & (mesh > 0)
    both = raw_valid & mesh_valid
    values = np.concatenate((raw[raw_valid], mesh[mesh_valid]))
    lo, hi = np.quantile(values, [0.02, 0.98])
    residual = np.full_like(mesh, np.nan, dtype=np.float32)
    residual[both] = np.abs(mesh[both] - raw[both])
    fig, axes = plt.subplots(1, 5, figsize=(18, 4), dpi=130, constrained_layout=True)
    panels = [rgb, np.where(raw_valid, raw, np.nan), np.where(mesh_valid, mesh, np.nan), residual, mesh_valid]
    labels = ["RGB", "raw COLMAP depth", "OpenMVS mesh depth", "|mesh-raw|", "mesh hit mask"]
    for axis, value, label in zip(axes, panels, labels):
        kwargs: dict[str, Any] = {}
        if "depth" in label:
            kwargs = {"cmap": "turbo", "vmin": lo, "vmax": hi}
        elif label == "|mesh-raw|":
            kwargs = {"cmap": "magma", "vmin": 0, "vmax": 10}
        elif label == "mesh hit mask":
            kwargs = {"cmap": "gray_r", "vmin": 0, "vmax": 1}
        axis.imshow(value, **kwargs)
        axis.set_title(label)
        axis.axis("off")
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path)
    plt.close(fig)


def project() -> None:
    cfg = yaml.safe_load(BASE_CONFIG.read_text())
    projection = yaml.safe_load(PROJECTION_CONFIG.read_text())
    mesh_path = Path(projection["source_mesh"])
    manifest_path = ROOT / "mvs_surface_depth_definition.json"
    csv_path = ROOT / "mvs_surface_depth_metrics.csv"
    if manifest_path.is_file() and csv_path.is_file() and os.environ.get("JBGS_REBUILD_PANELS") != "1":
        manifest = json.loads(manifest_path.read_text())
        if manifest.get("status") == "COMPLETE" and all(
            (DEPTH_DIR / row["file"]).is_file()
            and sha256(DEPTH_DIR / row["file"]) == row["sha256"]
            for row in manifest["views"]
        ):
            print(json.dumps({"status": "ALREADY_COMPLETE", "views": len(manifest["views"])}))
            return

    ensure_symlink(DATA / "images", SOURCE_DATA / "images")
    ensure_symlink(DATA / "sparse", SOURCE_DATA / "sparse")
    DEPTH_DIR.mkdir(parents=True, exist_ok=True)
    dataset = ColmapDataset(
        SOURCE_DATA,
        downscale=float(cfg["downscale"]),
        load_depth=True,
        load_normal=False,
        load_semantic=False,
        visible_views=cfg["visible_views"],
    )
    if [frame.name for frame in dataset.frames] != cfg["visible_views"]:
        raise RuntimeError("frozen 55-view order drift")

    legacy = o3d.io.read_triangle_mesh(str(mesh_path))
    vertices = np.asarray(legacy.vertices)
    faces = np.asarray(legacy.triangles)
    if len(vertices) != 1_956_560 or len(faces) != 3_911_218:
        raise RuntimeError(f"OpenMVS mesh count drift: {len(vertices)}/{len(faces)}")
    scene = o3d.t.geometry.RaycastingScene()
    scene.add_triangles(o3d.t.geometry.TriangleMesh.from_legacy(legacy))

    rows: list[dict[str, Any]] = []
    for index, frame in enumerate(dataset.frames):
        height, width = dataset.image_size(index)
        intrinsic = dataset.scaled_K(index)
        uu, vv = np.meshgrid(
            np.arange(width, dtype=np.float32) + float(projection["ray_pixel_center_offset"]),
            np.arange(height, dtype=np.float32) + float(projection["ray_pixel_center_offset"]),
        )
        camera_direction = np.stack(
            (
                (uu - intrinsic[0, 2]) / intrinsic[0, 0],
                (vv - intrinsic[1, 2]) / intrinsic[1, 1],
                np.ones_like(uu),
            ),
            axis=-1,
        )
        world_direction = camera_direction @ frame.R
        origin = (-frame.R.T @ frame.t).astype(np.float32)
        rays = np.concatenate(
            (np.broadcast_to(origin, camera_direction.shape), world_direction.astype(np.float32)),
            axis=-1,
        )
        hit = scene.cast_rays(o3d.core.Tensor(rays))["t_hit"].numpy()
        valid = np.isfinite(hit) & (hit > 0)
        depth = np.where(valid, hit, 0.0).astype(np.float32)
        target = DEPTH_DIR / f"{Path(frame.name).stem}.exr"
        if not target.is_file():
            write_exr(target, depth)
        else:
            prior = cv2.imread(str(target), cv2.IMREAD_UNCHANGED)
            if prior is None or prior.shape[:2] != depth.shape or not np.array_equal(prior, depth):
                raise RuntimeError(f"existing task-local depth drift: {target}")

        batch = dataset[index]
        raw = batch["depth"].numpy().astype(np.float32)
        raw_valid = batch["depth_mask"].numpy().astype(bool) & np.isfinite(raw) & (raw > 0)
        both = valid & raw_valid
        residual = np.abs(depth[both] - raw[both])
        mesh_values = depth[valid]
        row = {
            "view_index": index,
            "view": frame.name,
            "file": target.name,
            "sha256": sha256(target),
            "height": height,
            "width": width,
            "mesh_valid_pixels": int(valid.sum()),
            "mesh_valid_fraction": float(valid.mean()),
            "raw_valid_pixels": int(raw_valid.sum()),
            "raw_valid_fraction": float(raw_valid.mean()),
            "overlap_pixels": int(both.sum()),
            "overlap_fraction": float(both.mean()),
            "mesh_depth_median_m": float(np.median(mesh_values)),
            "mesh_depth_p95_m": float(np.quantile(mesh_values, 0.95)),
            "mesh_depth_p99_m": float(np.quantile(mesh_values, 0.99)),
            "mesh_depth_max_m": float(mesh_values.max()),
            "raw_mesh_abs_median_m": float(np.median(residual)) if len(residual) else None,
            "raw_mesh_abs_p90_m": float(np.quantile(residual, 0.90)) if len(residual) else None,
            "raw_mesh_abs_p95_m": float(np.quantile(residual, 0.95)) if len(residual) else None,
            "raw_mesh_abs_p99_m": float(np.quantile(residual, 0.99)) if len(residual) else None,
        }
        rows.append(row)
        if frame.name in REPRESENTATIVE:
            save_panel(
                ROOT / "representative_images/input_depth" / f"{Path(frame.name).stem}.png",
                batch["rgb"].numpy(),
                raw,
                depth,
            )
        print(json.dumps({"view": frame.name, "mesh_valid_fraction": row["mesh_valid_fraction"], "raw_mesh_abs_median_m": row["raw_mesh_abs_median_m"]}), flush=True)

    with csv_path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    body = {
        "schema": "jointbuildgs.p2.e3_local_4906982_mvs_surface_depth_v1.depth_definition.v1",
        "task_id": TASK_ID,
        "status": "COMPLETE",
        "source_mesh": str(mesh_path),
        "source_mesh_sha256": sha256(mesh_path),
        "source_mesh_vertices": len(vertices),
        "source_mesh_faces": len(faces),
        "definition": projection,
        "view_count": len(rows),
        "mesh_valid_fraction": {
            "min": float(min(row["mesh_valid_fraction"] for row in rows)),
            "median": float(np.median([row["mesh_valid_fraction"] for row in rows])),
            "max": float(max(row["mesh_valid_fraction"] for row in rows)),
        },
        "raw_mesh_abs_median_m_across_views": float(np.median([row["raw_mesh_abs_median_m"] for row in rows])),
        "views": rows,
        "scientific_verdict": None,
    }
    atomic_json(manifest_path, body)
    print(json.dumps({key: value for key, value in body.items() if key != "views"}, indent=2))


if __name__ == "__main__":
    project()
