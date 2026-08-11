#!/usr/bin/env python3
"""Replace the target-crop E1 display proxy with a full-scene LiDAR surface."""
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
CONFIG = REPO / "configs/p2/viewer_8876_e1_lidar_fullscene_surface_v1/viewer.json"
SOURCE = REPO / "scripts/p2/viewer_8876_e1_lidar_fullscene_surface_v1/build.py"
TASK = AR / "phase-payloads/p2/viewer_8876_e1_lidar_fullscene_surface_v1/P2-VIEWER-8876-E1-LIDAR-FULLSCENE-SURFACE-v1"


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


def file_record(path: Path, relative_path: str | None = None) -> dict:
    return {
        "path": relative_path or str(path),
        "bytes": path.stat().st_size,
        "sha256": sha256(path),
    }


def verify(path: Path, expected_hash: str, expected_bytes: int | None = None) -> dict:
    if not path.is_file():
        raise RuntimeError(f"missing input: {path}")
    record = file_record(path)
    if expected_bytes is not None and record["bytes"] != expected_bytes:
        raise RuntimeError(f"byte drift: {path}: {record['bytes']} != {expected_bytes}")
    if record["sha256"] != expected_hash:
        raise RuntimeError(f"sha256 drift: {path}: {record['sha256']} != {expected_hash}")
    return record


def append_triangles(
    pieces: list[np.ndarray],
    mask: np.ndarray,
    offsets: tuple[tuple[int, int], tuple[int, int], tuple[int, int]],
    grid: np.ndarray,
    cfg: dict,
) -> None:
    rows, cols = np.nonzero(mask)
    if len(rows) == 0:
        return
    min_x, min_y, _, _ = map(float, cfg["source_bounds_xy"])
    resolution = float(cfg["grid_resolution_m"])
    shift = np.asarray(cfg["world_shift_xyz"], dtype=np.float64)
    triangles = np.empty((len(rows), 3, 3), dtype="<f4")
    for index, (dr, dc) in enumerate(offsets):
        triangles[:, index, 0] = min_x + (cols + dc + 0.5) * resolution - shift[0]
        triangles[:, index, 1] = min_y + (rows + dr + 0.5) * resolution - shift[1]
        triangles[:, index, 2] = grid[rows + dr, cols + dc] - shift[2]
    pieces.append(triangles.reshape(-1, 3))


def surface_triangles(cfg: dict, source: Path) -> tuple[np.ndarray, dict]:
    min_x, min_y, max_x, max_y = map(float, cfg["source_bounds_xy"])
    resolution = float(cfg["grid_resolution_m"])
    nx = int(np.ceil((max_x - min_x) / resolution)) + 1
    ny = int(np.ceil((max_y - min_y) / resolution)) + 1
    top = np.full(nx * ny, -np.inf, dtype=np.float64)
    accepted = scanned = 0
    wanted = np.asarray(cfg["classification_codes"], dtype=np.uint8)

    with laspy.open(source) as reader:
        header_bounds = [
            float(reader.header.mins[0]),
            float(reader.header.mins[1]),
            float(reader.header.maxs[0]),
            float(reader.header.maxs[1]),
        ]
        if not np.allclose(header_bounds, cfg["source_bounds_xy"], atol=0.011, rtol=0.0):
            raise RuntimeError(f"LAZ XY bounds drift: {header_bounds} != {cfg['source_bounds_xy']}")
        for chunk in reader.chunk_iterator(int(cfg["las_chunk_points"])):
            scanned += len(chunk)
            classes = np.asarray(chunk.classification, dtype=np.uint8)
            mask = np.isin(classes, wanted)
            if not np.any(mask):
                continue
            x = np.asarray(chunk.x)[mask]
            y = np.asarray(chunk.y)[mask]
            z = np.asarray(chunk.z)[mask]
            inside = (x >= min_x) & (x <= max_x) & (y >= min_y) & (y <= max_y)
            if not np.any(inside):
                continue
            x, y, z = x[inside], y[inside], z[inside]
            cols = np.floor((x - min_x) / resolution).astype(np.int64)
            rows = np.floor((y - min_y) / resolution).astype(np.int64)
            cols = np.clip(cols, 0, nx - 1)
            rows = np.clip(rows, 0, ny - 1)
            np.maximum.at(top, rows * nx + cols, z)
            accepted += len(z)

    grid = top.reshape(ny, nx)
    z00, z01 = grid[:-1, :-1], grid[:-1, 1:]
    z10, z11 = grid[1:, :-1], grid[1:, 1:]
    finite00, finite01 = np.isfinite(z00), np.isfinite(z01)
    finite10, finite11 = np.isfinite(z10), np.isfinite(z11)
    diagonal_a = np.where(finite00 & finite11, np.abs(z00 - z11), np.inf)
    diagonal_b = np.where(finite01 & finite10, np.abs(z01 - z10), np.inf)
    use_a = diagonal_a <= diagonal_b
    max_span = float(cfg["maximum_triangle_z_span_m"])

    def valid(a: np.ndarray, b: np.ndarray, c: np.ndarray) -> np.ndarray:
        return (
            np.isfinite(a) & np.isfinite(b) & np.isfinite(c)
            & ((np.maximum(np.maximum(a, b), c) - np.minimum(np.minimum(a, b), c)) <= max_span)
        )

    pieces: list[np.ndarray] = []
    append_triangles(pieces, use_a & valid(z00, z01, z11), ((0, 0), (0, 1), (1, 1)), grid, cfg)
    append_triangles(pieces, use_a & valid(z00, z11, z10), ((0, 0), (1, 1), (1, 0)), grid, cfg)
    append_triangles(pieces, ~use_a & valid(z00, z01, z10), ((0, 0), (0, 1), (1, 0)), grid, cfg)
    append_triangles(pieces, ~use_a & valid(z01, z11, z10), ((0, 1), (1, 1), (1, 0)), grid, cfg)
    if not pieces:
        raise RuntimeError("full-scene LiDAR surface proxy produced no triangles")
    expanded = np.ascontiguousarray(np.concatenate(pieces, axis=0), dtype="<f4")
    return expanded, {
        "source_point_count_scanned": scanned,
        "class_2_6_full_scene_point_count": accepted,
        "occupied_grid_cell_count": int(np.isfinite(grid).sum()),
        "grid_shape_yx": [ny, nx],
        "display_triangle_count": int(len(expanded) // 3),
        "covered_xy_area_m2": float((max_x - min_x) * (max_y - min_y)),
    }


def main() -> None:
    cfg = json.loads(CONFIG.read_text())
    viewer = AR / cfg["viewer_root"]
    source = AR / cfg["source_laz"]
    before = {name: verify(viewer / name, expected) for name, expected in cfg["expected_before"].items()}
    source_record = verify(source, cfg["source_laz_sha256"], int(cfg["source_laz_bytes"]))
    previous_cfg = cfg["expected_previous_surface_asset"]
    previous_record = verify(
        viewer / previous_cfg["path"],
        previous_cfg["sha256"],
        int(previous_cfg["bytes"]),
    )
    if TASK.exists():
        raise RuntimeError(f"add-once task exists: {TASK}")

    manifest_path = viewer / "viewer_manifest.json"
    manifest = json.loads(manifest_path.read_text())
    e1 = next(panel for panel in manifest["panels"] if panel.get("condition") == "E1")
    previous_surface = e1.get("surface_mesh")
    if not isinstance(previous_surface, dict):
        raise RuntimeError("expected existing E1 target-view surface proxy")
    if previous_surface.get("asset") != previous_cfg["path"]:
        raise RuntimeError("existing E1 surface asset is not the bound target-view proxy")
    if previous_surface.get("building_id") != previous_cfg["building_id"]:
        raise RuntimeError("existing E1 surface building identity drift")

    triangles, stats = surface_triangles(cfg, source)
    asset = viewer / cfg["output_asset"]
    if asset.exists():
        raise RuntimeError(f"output asset already exists: {asset}")
    atomic_bytes(asset, triangles.tobytes())
    asset_record = file_record(asset, cfg["output_asset"])
    surface = {
        "asset": cfg["output_asset"],
        "asset_sha256": asset_record["sha256"],
        "coverage_scope": "FULL_SOURCE_XY_BOUNDS",
        "source_bounds_xy": cfg["source_bounds_xy"],
        "grid_resolution_m": cfg["grid_resolution_m"],
        "maximum_triangle_z_span_m": cfg["maximum_triangle_z_span_m"],
        "hole_fill": False,
        "display_proxy_method": cfg["display_proxy_method"],
        "display_triangle_count": stats["display_triangle_count"],
        "source": "/artifacts/JointBuildGS/" + cfg["source_laz"],
        "source_coordinate_frame": "EPSG25832_WORLD",
        "source_role": cfg["source_role"],
        "source_sha256": source_record["sha256"],
        "source_classification_codes": cfg["classification_codes"],
        "display_only": True,
    }

    manifest["E1_lidar_target_viewport_surface_display_proxy_v1"] = previous_surface
    e1["surface_mesh"] = surface
    manifest["E1_lidar_surface_display_proxy"] = surface
    manifest["roofer_inputs_modified"] = False
    manifest["scientific_verdict"] = None
    atomic_json(manifest_path, manifest)

    surfaces_path = viewer / "surface_meshes.json"
    surfaces = json.loads(surfaces_path.read_text())
    surfaces["E1_target_viewport_surface_mesh_v1"] = surfaces.get("conditions", {}).get("E1", previous_surface)
    surfaces["source_identity"]["E1"] = source_record["sha256"]
    surfaces["conditions"]["E1"] = surface
    surfaces["E1_surface_mesh"] = surface
    surfaces["E1_reason"] = "DISPLAY_ONLY_CLASS_2_6_MAX_Z_SURFACE_PROXY_FOR_FULL_LIDAR_SOURCE_XY"
    surfaces["roofer_inputs_modified"] = False
    surfaces["scientific_verdict"] = None
    atomic_json(surfaces_path, surfaces)

    app_path = viewer / "app.js"
    app = app_path.read_text().replace(
        "E1 UAS LiDAR + E2 OpenMVS + E3-E6 TSDF 표면 mesh 표시",
        "E1 UAS LiDAR 전체 범위 + E2 OpenMVS + E3-E6 TSDF 표면 mesh 표시",
    )
    atomic_text(app_path, app)

    index_path = viewer / "index.html"
    index = index_path.read_text().replace(
        "app.js?v=e1e6-20260810-epaired-72-footprints-v1",
        "app.js?v=e1e6-20260810-e1-lidar-fullscene-surface-v1",
    )
    atomic_text(index_path, index)

    after = {name: file_record(viewer / name) for name in cfg["expected_before"]}
    TASK.mkdir(parents=True)
    receipt = {
        "schema": "jointbuildgs.p2.viewer_8876_e1_lidar_fullscene_surface.receipt.v1",
        "task_id": cfg["task_id"],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "config": file_record(CONFIG),
        "script": file_record(SOURCE),
        "source": source_record,
        "previous_target_viewport_surface_asset_preserved": previous_record,
        "full_scene_surface_asset": asset_record,
        "surface_stats": stats,
        "viewer_before": before,
        "viewer_after": after,
        "full_source_xy_covered": True,
        "display_only": True,
        "roofer_inputs_modified": False,
        "scientific_verdict": None,
    }
    atomic_json(TASK / "receipt.json", receipt)
    print(json.dumps(receipt, indent=2))


if __name__ == "__main__":
    main()
