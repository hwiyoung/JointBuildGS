#!/usr/bin/env python3
"""Build S1 occlusion-aware ALS prior maps for the exact 55 crop cameras.

Real (non-synthetic) class-2/6 ALS -> 0.5 m DSM TIN -> per-camera raycast.
Three confidence variants are written as separate per-view npz sets sharing the
identical depth/normal payload: E4_STATIC (registration x density x planarity x
visibility), E5_F1 (x pixel current-consistency), E5_F1F2 (x box-smoothed
current-consistency). A leak-QA + registration receipt closes the preflight.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import laspy
import numpy as np
import open3d as o3d
import yaml
from scipy.ndimage import label, uniform_filter

from scripts.p2.c4_existing_als_v1.prepare_prior import ALS_DATUM_SHIFT_M, ALS_HASHES, WORLD_SHIFT, registration_gate
from src.stage2.colmap_io import read_images_bin
from src.stage2.dataloader import ColmapDataset

REPO = Path(__file__).resolve().parents[3]
COMMON = REPO / "configs/p2/e4_e6_redesign_s1_v1/s1_v1.yaml"
ARTIFACTS = Path("/artifacts/JointBuildGS")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def materialized_base(common: dict[str, Any]) -> dict[str, Any]:
    config = yaml.safe_load((REPO / common["base_training_config"]).read_text(encoding="utf-8"))
    config.update(yaml.safe_load((REPO / common["fused_arm_config"]).read_text(encoding="utf-8"))["overrides"])
    return config


def load_scene_als(als_root: Path, low: np.ndarray, high: np.ndarray, classes: set[int]) -> np.ndarray:
    parts: list[np.ndarray] = []
    for name, expected in ALS_HASHES.items():
        path = als_root / name
        if sha256(path) != expected:
            raise RuntimeError(f"raw ALS hash drift: {name}")
        with laspy.open(path) as reader:
            for chunk in reader.chunk_iterator(2_000_000):
                x = np.asarray(chunk.x)
                y = np.asarray(chunk.y)
                keep = (
                    np.isin(np.asarray(chunk.classification), list(classes))
                    & (x >= low[0]) & (x <= high[0]) & (y >= low[1]) & (y <= high[1])
                )
                if bool(keep.any()):
                    z = np.asarray(chunk.z)[keep] + ALS_DATUM_SHIFT_M
                    parts.append(np.column_stack((x[keep], y[keep], z)) - WORLD_SHIFT)
    if not parts:
        raise RuntimeError("no class-2/6 ALS points inside the scene bbox")
    return np.concatenate(parts)


def dsm_tin(points_local: np.ndarray, cell_m: float):
    """Return (scene, per-face density gate, per-face planarity gate, counts)."""
    xy_min = points_local[:, :2].min(axis=0)
    cols = np.floor((points_local[:, 0] - xy_min[0]) / cell_m).astype(np.int64)
    rows = np.floor((points_local[:, 1] - xy_min[1]) / cell_m).astype(np.int64)
    n_cols = int(cols.max()) + 1
    n_rows = int(rows.max()) + 1
    flat = rows * n_cols + cols
    top = np.full(n_rows * n_cols, -np.inf, dtype=np.float64)
    np.maximum.at(top, flat, points_local[:, 2])
    count = np.bincount(flat, minlength=n_rows * n_cols).astype(np.float64)
    z_sum = np.bincount(flat, weights=points_local[:, 2], minlength=n_rows * n_cols)
    z_sq = np.bincount(flat, weights=points_local[:, 2] ** 2, minlength=n_rows * n_cols)
    with np.errstate(invalid="ignore", divide="ignore"):
        z_var = np.maximum(z_sq / np.maximum(count, 1) - (z_sum / np.maximum(count, 1)) ** 2, 0.0)
    z_std = np.sqrt(z_var)
    top = top.reshape(n_rows, n_cols)
    count = count.reshape(n_rows, n_cols)
    z_std = z_std.reshape(n_rows, n_cols)
    # Interior-void fill: class-2/6 DSMs have holes at canopies/glass roofs, and
    # oblique rays escaping through them land on far terrain as confident wrong
    # support. Filled cells exist for OCCLUSION only — their point count stays 0,
    # so the density gate zeroes their supervision confidence.
    empty = ~np.isfinite(top)
    labels, _ = label(empty)
    border = np.unique(np.concatenate([labels[0], labels[-1], labels[:, 0], labels[:, -1]]))
    interior = empty & ~np.isin(labels, border[border > 0])
    grid = np.where(np.isfinite(top), top, 0.0)
    mask = np.isfinite(top).astype(np.float64)
    for _ in range(200):
        if not interior.any():
            break
        neighbor_sum = uniform_filter(grid * mask, size=3) * 9.0
        neighbor_count = uniform_filter(mask, size=3) * 9.0
        fill = interior & (neighbor_count >= 3.0)
        if not fill.any():
            break
        grid[fill] = neighbor_sum[fill] / neighbor_count[fill]
        mask[fill] = 1.0
        interior[fill] = False
    top = np.where(mask > 0, grid, -np.inf)
    valid = np.isfinite(top)
    index = np.full(top.shape, -1, dtype=np.int64)
    vertex_count = int(valid.sum())
    index[valid] = np.arange(vertex_count)
    grid_rows, grid_cols = np.nonzero(valid)
    vertices = np.column_stack((
        xy_min[0] + (grid_cols + 0.5) * cell_m,
        xy_min[1] + (grid_rows + 0.5) * cell_m,
        top[valid],
    ))
    vertex_density = np.clip((count[valid] - 1.0) / 5.0, 0.0, 1.0)
    vertex_planarity = np.exp(-z_std[valid] / 0.2)
    a, b = index[:-1, :-1], index[:-1, 1:]
    c, d = index[1:, :-1], index[1:, 1:]
    quad = (a >= 0) & (b >= 0) & (c >= 0) & (d >= 0)
    triangles = np.concatenate([
        np.column_stack((a[quad], b[quad], c[quad])),
        np.column_stack((b[quad], d[quad], c[quad])),
    ])
    face_density = vertex_density[triangles].min(axis=1).astype(np.float32)
    face_planarity = vertex_planarity[triangles].min(axis=1).astype(np.float32)
    legacy = o3d.geometry.TriangleMesh(
        o3d.utility.Vector3dVector(vertices),
        o3d.utility.Vector3iVector(triangles.astype(np.int32)),
    )
    scene = o3d.t.geometry.RaycastingScene()
    scene.add_triangles(o3d.t.geometry.TriangleMesh.from_legacy(legacy))
    return scene, face_density, face_planarity, vertex_count, int(len(triangles))


def main() -> None:
    started = datetime.now(timezone.utc).isoformat()
    common = yaml.safe_load(COMMON.read_text(encoding="utf-8"))
    proj = common["projection_v2"]
    out_root = Path(common["output_root"])
    prior_root = out_root / "prior"
    receipt_path = out_root / "control/200-s1-prior-preflight-passed.json"
    if receipt_path.is_file():
        print(json.dumps({"status": "IDEMPOTENT_ALREADY_COMPLETE"}))
        return
    prior_root.mkdir(parents=True, exist_ok=True)

    base = materialized_base(common)
    names = list(base["visible_views"])
    if len(names) != 55:
        raise RuntimeError("frozen 55-view roles drifted")
    dataset = ColmapDataset(base["data_root"], downscale=1.0, load_depth=True, load_normal=False, load_semantic=False, visible_views=names)
    seed = dataset.points_xyz.astype(np.float64)
    if len(seed) != 25683:
        raise RuntimeError(f"exact sparse seed drifted: {len(seed)}")
    # The TIN must cover the full camera-to-scene corridor: several crop
    # cameras sit ~300 m from the building, and without foreground terrain in
    # the TIN nothing occludes their rays, so target-area hits masquerade as
    # visible support. bbox = union(sparse seed XY, camera centres XY) + 20 m.
    sparse_dir = Path(base["data_root"]) / "sparse"
    if (sparse_dir / "0").is_dir():
        sparse_dir = sparse_dir / "0"
    visible = set(names)
    centers = []
    for image in read_images_bin(sparse_dir / "images.bin").values():
        if image.name in visible:
            w2c = image.world_to_camera()
            centers.append(-w2c[:3, :3].T @ w2c[:3, 3])
    if len(centers) != 55:
        raise RuntimeError(f"expected 55 camera centres, got {len(centers)}")
    corridor_xy = np.vstack([seed[:, :2], np.asarray(centers)[:, :2]])
    low = corridor_xy.min(axis=0) + WORLD_SHIFT[:2] - 20.0
    high = corridor_xy.max(axis=0) + WORLD_SHIFT[:2] + 20.0
    als_local = load_scene_als(ARTIFACTS / common["als_raw_root"], low, high, set(proj["classes"]))
    registration = registration_gate(seed, als_local)
    g_reg = float(registration["registration_confidence"])
    scene, face_density, face_planarity, vertex_count, triangle_count = dsm_tin(als_local, float(proj["dsm_cell_m"]))

    variants = list(common["prior_variants"])
    for variant in variants:
        (prior_root / variant).mkdir(parents=True, exist_ok=True)

    leak = {variant: {"gt2": 0, "n": 0, "abs": [], "pool": []} for variant in ("RAW", "E4_STATIC")}
    view_rows = []
    for view_index, frame in enumerate(dataset.frames):
        sample = dataset[view_index]
        height, width = int(sample["height"]), int(sample["width"])
        k_inv = np.linalg.inv(sample["K"].numpy().astype(np.float64))
        w2c = sample["w2c"].numpy().astype(np.float64)
        rotation = w2c[:3, :3]
        center = -rotation.T @ w2c[:3, 3]
        us, vs = np.meshgrid(np.arange(width) + 0.5, np.arange(height) + 0.5)
        pixels = np.column_stack((us.ravel(), vs.ravel(), np.ones(us.size)))
        directions = (pixels @ k_inv.T) @ rotation
        rays = o3d.core.Tensor(
            np.concatenate([np.broadcast_to(center, directions.shape), directions], axis=1).astype(np.float32)
        )
        cast = scene.cast_rays(rays)
        depth = cast["t_hit"].numpy().astype(np.float32)
        primitive = cast["primitive_ids"].numpy()
        normals = cast["primitive_normals"].numpy().astype(np.float32)
        hit = np.isfinite(depth) & (primitive != o3d.t.geometry.RaycastingScene.INVALID_ID)
        # Occlusion guards: interior-void fill (in dsm_tin) closes canopy/glass
        # holes, and the static working-range cut removes far-horizon rays that
        # exit to distant TIN cells irrelevant to this building crop. An absolute
        # neighbour-jump guard is intentionally NOT used: at oblique grazing
        # angles adjacent pixel rays legitimately land >1 m apart on a smooth
        # roof, so it would erase entire oblique views. Neither guard references
        # current evidence.
        hit &= depth <= float(proj["occlusion_guards"]["max_prior_depth_m"])
        cos = np.zeros(len(depth), dtype=np.float32)
        norm_dir = directions / np.linalg.norm(directions, axis=1, keepdims=True)
        cos[hit] = np.abs(np.einsum("ij,ij->i", norm_dir[hit], normals[hit].astype(np.float64))).astype(np.float32)
        g_den = np.zeros(len(depth), np.float32)
        g_pla = np.zeros(len(depth), np.float32)
        g_den[hit] = face_density[primitive[hit]]
        g_pla[hit] = face_planarity[primitive[hit]]
        static_conf = (g_reg * g_den * g_pla * cos).astype(np.float32)

        fused = sample["depth"].numpy().astype(np.float32)
        fused_mask = sample["depth_mask"].numpy().astype(bool).ravel()
        fused_flat = fused.ravel()
        residual = np.abs(depth - fused_flat)
        supported = hit & fused_mask & (fused_flat > 0)
        f1 = np.ones(len(depth), np.float32)
        f1[supported] = np.exp(-residual[supported] / 2.0).astype(np.float32)
        residual_map = np.full(height * width, np.nan, np.float32)
        residual_map[supported] = residual[supported]
        residual_img = residual_map.reshape(height, width)
        valid_img = np.isfinite(residual_img).astype(np.float32)
        smoothed = uniform_filter(np.nan_to_num(residual_img, nan=0.0), size=39)
        weight_sum = uniform_filter(valid_img, size=39)
        with np.errstate(invalid="ignore", divide="ignore"):
            box_mean = np.where(weight_sum > 1e-6, smoothed / weight_sum, np.nan)
        f2 = np.ones(len(depth), np.float32)
        box_flat = box_mean.ravel()
        has_box = np.isfinite(box_flat)
        f2[has_box] = np.exp(-box_flat[has_box] / 2.0).astype(np.float32)

        yy, xx = np.divmod(np.arange(height * width), width)
        stem = Path(frame.name).stem
        confidences = {
            "E4_STATIC": static_conf,
            "E5_F1": static_conf * f1,
            "E5_F1F2": static_conf * f1 * f2,
        }
        row = {"name": frame.name, "shape": [height, width], "tin_hit_fraction": float(hit.mean())}
        for variant in variants:
            conf = confidences[variant]
            keep = hit & (conf >= float(proj["confidence_min"]))
            np.savez_compressed(
                prior_root / variant / f"{stem}.npz",
                height=np.int32(height), width=np.int32(width),
                pixel_y=yy[keep].astype(np.int32), pixel_x=xx[keep].astype(np.int32),
                depth=depth[keep], normal=normals[keep], confidence=conf[keep],
            )
            row[f"{variant}_pixels"] = int(keep.sum())
            row[f"{variant}_confidence_mean"] = float(conf[keep].mean()) if keep.any() else 0.0
        for key, keep_mask in (
            ("RAW", supported),
            ("E4_STATIC", supported & (confidences["E4_STATIC"] >= float(proj["confidence_min"]))),
        ):
            leak[key]["gt2"] += int((residual[keep_mask] > 2.0).sum())
            leak[key]["n"] += int(keep_mask.sum())
            leak[key]["abs"].append(float(np.median(residual[keep_mask])) if keep_mask.any() else np.nan)
            leak[key]["pool"].append(residual[keep_mask].astype(np.float32))
        view_rows.append(row)
        print(f"[s1 prior] {view_index + 1}/55 {stem}", flush=True)

    qa = {}
    for key, block in leak.items():
        pooled = np.concatenate(block["pool"]) if block["pool"] else np.empty(0, np.float32)
        qa[key] = {
            "gt2m_fraction": block["gt2"] / block["n"] if block["n"] else None,
            "global_median_abs_m": float(np.median(pooled)) if len(pooled) else None,
            "global_p95_abs_m": float(np.quantile(pooled, 0.95)) if len(pooled) else None,
            "per_view_median_abs_m": [None if np.isnan(v) else round(v, 4) for v in block["abs"]],
            "supported_pixels": block["n"],
        }
    targets = proj["leak_qa_targets"]
    passed = (
        qa["E4_STATIC"]["gt2m_fraction"] is not None
        and qa["E4_STATIC"]["gt2m_fraction"] <= float(targets["gt2m_fraction_max"])
        and qa["E4_STATIC"]["global_median_abs_m"] is not None
        and qa["E4_STATIC"]["global_median_abs_m"] <= float(targets["median_max_m"])
    )
    receipt = {
        "schema": "jointbuildgs.p2.e4_e6_redesign_s1_v1.prior_preflight.v1",
        "task_id": common["task_id"],
        "status": "200-PASSED_S1_TIN_PRIOR_PREFLIGHT" if passed else "100-FAILED_LEAK_QA",
        "started_utc": started,
        "ended_utc": datetime.now(timezone.utc).isoformat(),
        "projection": {key: proj[key] for key in ("method", "dsm_cell_m", "classes", "confidence_min", "static_gates", "occlusion_guards", "conflict_f1", "conflict_f2")},
        "scene_als_point_count": int(len(als_local)),
        "tin_vertex_count": vertex_count,
        "tin_triangle_count": triangle_count,
        "registration": registration,
        "leak_qa": qa,
        "leak_qa_targets": targets,
        "leak_qa_passed": bool(passed),
        "view_count": len(view_rows),
        "views": view_rows,
        "synthetic_changes": None,
        "lod2_training_use": False,
        "official_PASS_usable": None,
        "scientific_verdict": None,
    }
    target_path = receipt_path if passed else out_root / "control/100-s1-prior-preflight-failed.json"
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if not passed:
        raise RuntimeError(f"S1 prior leak QA failed: {json.dumps({k: {kk: vv for kk, vv in v.items() if kk != 'per_view_median_abs_m'} for k, v in qa.items()})}")
    print(json.dumps({"status": receipt["status"], "leak_qa": qa}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
