#!/usr/bin/env python3
"""Add a display-only Current-UAS LiDAR surface proxy to the live 8876 viewer."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path

import laspy
import numpy as np


REPO = Path("/workspace/JointBuildGS")
AR = Path("/artifacts/JointBuildGS")
CONFIG = REPO / "configs/p2/viewer_8876_e1_lidar_surface_v1/viewer.json"
SOURCE = REPO / "scripts/p2/viewer_8876_e1_lidar_surface_v1/build.py"
TASK = AR / "phase-payloads/p2/viewer_8876_e1_lidar_surface_v1/P2-VIEWER-8876-E1-LIDAR-SURFACE-v1"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def atomic_bytes(path: Path, body: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(body)
    os.replace(temporary, path)


def atomic_text(path: Path, body: str) -> None:
    atomic_bytes(path, body.encode("utf-8"))


def atomic_json(path: Path, body: object) -> None:
    atomic_text(path, json.dumps(body, indent=2, sort_keys=True) + "\n")


def verify(path: Path, expected_hash: str, expected_bytes: int | None = None) -> dict:
    if not path.is_file():
        raise RuntimeError(f"missing input: {path}")
    size = path.stat().st_size
    if expected_bytes is not None and size != expected_bytes:
        raise RuntimeError(f"byte drift: {path}: {size} != {expected_bytes}")
    actual = sha256(path)
    if actual != expected_hash:
        raise RuntimeError(f"sha256 drift: {path}: {actual} != {expected_hash}")
    return {"path": str(path), "bytes": size, "sha256": actual}


def surface_triangles(cfg: dict, source: Path) -> tuple[np.ndarray, dict]:
    min_x, min_y, max_x, max_y = map(float, cfg["crop_bbox_xy"])
    resolution = float(cfg["grid_resolution_m"])
    nx = int(np.ceil((max_x - min_x) / resolution))
    ny = int(np.ceil((max_y - min_y) / resolution))
    top = np.full(nx * ny, -np.inf, dtype=np.float64)
    accepted = scanned = 0
    wanted = np.asarray(cfg["classification_codes"], dtype=np.uint8)
    with laspy.open(source) as reader:
        for chunk in reader.chunk_iterator(int(cfg["las_chunk_points"])):
            scanned += len(chunk)
            classes = np.asarray(chunk.classification, dtype=np.uint8)
            mask = np.isin(classes, wanted)
            if not np.any(mask):
                continue
            x = np.asarray(chunk.x)[mask]
            y = np.asarray(chunk.y)[mask]
            z = np.asarray(chunk.z)[mask]
            inside = (x >= min_x) & (x < max_x) & (y >= min_y) & (y < max_y)
            if not np.any(inside):
                continue
            x, y, z = x[inside], y[inside], z[inside]
            col = np.floor((x - min_x) / resolution).astype(np.int64)
            row = np.floor((y - min_y) / resolution).astype(np.int64)
            np.maximum.at(top, row * nx + col, z)
            accepted += len(z)
    grid = top.reshape(ny, nx)
    shift = np.asarray(cfg["world_shift_xyz"], dtype=np.float64)
    max_span = float(cfg["maximum_triangle_z_span_m"])
    triangles: list[np.ndarray] = []

    def vertex(row: int, col: int) -> np.ndarray:
        return np.asarray(
            [min_x + (col + 0.5) * resolution, min_y + (row + 0.5) * resolution, grid[row, col]],
            dtype=np.float64,
        ) - shift

    for row in range(ny - 1):
        for col in range(nx - 1):
            cells = ((row, col), (row, col + 1), (row + 1, col), (row + 1, col + 1))
            values = np.asarray([grid[r, c] for r, c in cells])
            candidates = (((0, 1, 3), (0, 3, 2)), ((0, 1, 2), (1, 3, 2)))
            diag_a = abs(values[0] - values[3]) if np.isfinite(values[[0, 3]]).all() else np.inf
            diag_b = abs(values[1] - values[2]) if np.isfinite(values[[1, 2]]).all() else np.inf
            for tri in candidates[0 if diag_a <= diag_b else 1]:
                z = values[list(tri)]
                if not np.isfinite(z).all() or float(np.ptp(z)) > max_span:
                    continue
                triangles.append(np.stack([vertex(*cells[index]) for index in tri]))
    if not triangles:
        raise RuntimeError("LiDAR surface proxy produced no triangles")
    expanded = np.ascontiguousarray(np.stack(triangles).reshape(-1, 3), dtype="<f4")
    return expanded, {
        "source_point_count_scanned": scanned,
        "class_2_6_crop_point_count": accepted,
        "occupied_grid_cell_count": int(np.isfinite(grid).sum()),
        "grid_shape_yx": [ny, nx],
        "display_triangle_count": int(len(expanded) // 3),
    }


def main() -> None:
    cfg = json.loads(CONFIG.read_text())
    viewer = AR / cfg["viewer_root"]
    source = AR / cfg["source_laz"]
    before = {}
    for name, expected in cfg["expected_before"].items():
        before[name] = verify(viewer / name, expected)
    source_record = verify(source, cfg["source_laz_sha256"], int(cfg["source_laz_bytes"]))
    if TASK.exists():
        raise RuntimeError(f"add-once task exists: {TASK}")

    triangles, stats = surface_triangles(cfg, source)
    asset = viewer / cfg["output_asset"]
    if asset.exists():
        raise RuntimeError(f"output asset already exists: {asset}")
    atomic_bytes(asset, triangles.tobytes())
    asset_record = {"path": cfg["output_asset"], "bytes": asset.stat().st_size, "sha256": sha256(asset)}
    surface = {
        "asset": cfg["output_asset"],
        "asset_sha256": asset_record["sha256"],
        "display_proxy_method": cfg["display_proxy_method"],
        "display_triangle_count": stats["display_triangle_count"],
        "source": "/artifacts/JointBuildGS/" + cfg["source_laz"],
        "source_coordinate_frame": "EPSG25832_WORLD",
        "source_role": cfg["source_role"],
        "source_sha256": source_record["sha256"],
        "source_classification_codes": cfg["classification_codes"],
        "crop_bbox_xy": cfg["crop_bbox_xy"],
        "building_id": cfg["building_id"],
        "display_only": True,
    }

    manifest_path = viewer / "viewer_manifest.json"
    manifest = json.loads(manifest_path.read_text())
    e1 = next(panel for panel in manifest["panels"] if panel.get("condition") == "E1")
    if e1.get("surface_mesh") is not None:
        raise RuntimeError("E1 surface_mesh already exists")
    e1["surface_mesh"] = surface
    manifest["E1_lidar_surface_display_proxy"] = surface
    manifest["roofer_inputs_modified"] = False
    manifest["scientific_verdict"] = None
    atomic_json(manifest_path, manifest)

    surfaces_path = viewer / "surface_meshes.json"
    surfaces = json.loads(surfaces_path.read_text())
    surfaces["source_identity"]["E1"] = source_record["sha256"]
    surfaces["conditions"]["E1"] = surface
    surfaces["E1_surface_mesh"] = surface
    surfaces["E1_reason"] = "DISPLAY_ONLY_CLASS_2_6_MAX_Z_SURFACE_PROXY_ADDED_FOR_TARGET_VIEWPORT"
    surfaces["roofer_inputs_modified"] = False
    surfaces["scientific_verdict"] = None
    atomic_json(surfaces_path, surfaces)

    app_path = viewer / "app.js"
    app = app_path.read_text()
    app = app.replace(
        "E2 OpenMVS mesh + E3-E6 TSDF mesh 표시 · E1은 고정 surface mesh 없음",
        "E1 UAS LiDAR + E2 OpenMVS + E3-E6 TSDF 표면 mesh 표시",
    ).replace(
        "E2 OpenMVS + E3-E6 TSDF 표면 mesh 로드 완료 · E1 고정 mesh 없음",
        "E1 UAS LiDAR + E2 OpenMVS + E3-E6 TSDF 표면 mesh 로드 완료",
    )
    atomic_text(app_path, app)

    index_path = viewer / "index.html"
    index = index_path.read_text().replace(
        "app.js?v=e1e6-20260810-wireframe-v1",
        "app.js?v=e1e6-20260810-e1-lidar-surface-v1",
    )
    atomic_text(index_path, index)

    after = {name: {"bytes": (viewer / name).stat().st_size, "sha256": sha256(viewer / name)} for name in cfg["expected_before"]}
    TASK.mkdir(parents=True)
    receipt = {
        "schema": "jointbuildgs.p2.viewer_8876_e1_lidar_surface.receipt.v1",
        "task_id": cfg["task_id"],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "config": {"path": str(CONFIG), "sha256": sha256(CONFIG)},
        "script": {"path": str(SOURCE), "sha256": sha256(SOURCE)},
        "source": source_record,
        "surface_asset": asset_record,
        "surface_stats": stats,
        "viewer_before": before,
        "viewer_after": after,
        "display_only": True,
        "roofer_inputs_modified": False,
        "scientific_verdict": None,
    }
    atomic_json(TASK / "receipt.json", receipt)
    print(json.dumps(receipt, indent=2))


if __name__ == "__main__":
    main()
