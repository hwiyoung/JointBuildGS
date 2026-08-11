#!/usr/bin/env python3
"""Build S2 full-scene ALS prior maps for the exact 937 cameras.

Same frozen projection as S1 (corridor DSM-TIN raycast, interior void fill,
500 m range cut, static gates, 0.05 confidence cut) applied to the full-scene
fused-normal-confidence dataset. Two variants only, per the frozen decisions:
E4_STATIC (registration x density x planarity x |cos|) and E5_F1 (x pixel
current-consistency against the sealed full-scene fused depth targets).
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import open3d as o3d
import yaml

from scripts.p2.c4_existing_als_v1.prepare_prior import WORLD_SHIFT, registration_gate
from scripts.p2.e4_e6_redesign_s1_v1.prepare_prior_v2 import dsm_tin, load_scene_als
from src.stage2.colmap_io import read_images_bin
from src.stage2.dataloader import ColmapDataset

REPO = Path(__file__).resolve().parents[3]
COMMON = REPO / "configs/p2/e4_e6_redesign_s2_v1/s2_v1.yaml"
ARTIFACTS = Path("/artifacts/JointBuildGS")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    started = datetime.now(timezone.utc).isoformat()
    common = yaml.safe_load(COMMON.read_text(encoding="utf-8"))
    proj = common["projection_v2"]
    stride = int(proj["pixel_stride"])
    out_root = Path(common["output_root"])
    prior_root = out_root / "prior"
    receipt_path = out_root / "control/200-s2-prior-preflight-passed.json"
    if receipt_path.is_file():
        print(json.dumps({"status": "IDEMPOTENT_ALREADY_COMPLETE"}))
        return
    prior_root.mkdir(parents=True, exist_ok=True)

    base = yaml.safe_load((REPO / common["base_training_config"]).read_text(encoding="utf-8"))
    manifest = json.loads((REPO / common["exact_view_manifest"]).read_text(encoding="utf-8"))
    names = [str(row["basename"]) for row in manifest["rows"]]
    if len(names) != 937:
        raise RuntimeError(f"expected 937 exact views, got {len(names)}")
    dataset = ColmapDataset(base["data_root"], downscale=1.0, load_depth=True, load_normal=False, load_semantic=False, visible_views=names)
    seed = dataset.points_xyz.astype(np.float64)
    if len(seed) < 100_000:
        raise RuntimeError(f"full-scene sparse seed unexpectedly small: {len(seed)}")

    sparse_dir = Path(base["data_root"]) / "sparse"
    if (sparse_dir / "0").is_dir():
        sparse_dir = sparse_dir / "0"
    visible = set(names)
    centers = []
    for image in read_images_bin(sparse_dir / "images.bin").values():
        if image.name in visible:
            w2c = image.world_to_camera()
            centers.append(-w2c[:3, :3].T @ w2c[:3, 3])
    if len(centers) != 937:
        raise RuntimeError(f"expected 937 camera centres, got {len(centers)}")
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

    leak = {key: {"gt2": 0, "n": 0, "pool": []} for key in ("RAW", "E4_STATIC")}
    view_rows = []
    for view_index, frame in enumerate(dataset.frames):
        sample = dataset[view_index]
        height, width = int(sample["height"]), int(sample["width"])
        k_inv = np.linalg.inv(sample["K"].numpy().astype(np.float64))
        w2c = sample["w2c"].numpy().astype(np.float64)
        rotation = w2c[:3, :3]
        center = -rotation.T @ w2c[:3, 3]
        ys = np.arange(0, height, stride)
        xs = np.arange(0, width, stride)
        uu, vv = np.meshgrid(xs + 0.5, ys + 0.5)
        pixels = np.column_stack((uu.ravel(), vv.ravel(), np.ones(uu.size)))
        directions = (pixels @ k_inv.T) @ rotation
        rays = o3d.core.Tensor(
            np.concatenate([np.broadcast_to(center, directions.shape), directions], axis=1).astype(np.float32)
        )
        cast = scene.cast_rays(rays)
        depth = cast["t_hit"].numpy().astype(np.float32)
        primitive = cast["primitive_ids"].numpy()
        normals = cast["primitive_normals"].numpy().astype(np.float32)
        hit = np.isfinite(depth) & (primitive != o3d.t.geometry.RaycastingScene.INVALID_ID)
        hit &= depth <= float(proj["occlusion_guards"]["max_prior_depth_m"])
        cos = np.zeros(len(depth), dtype=np.float32)
        norm_dir = directions / np.linalg.norm(directions, axis=1, keepdims=True)
        cos[hit] = np.abs(np.einsum("ij,ij->i", norm_dir[hit], normals[hit].astype(np.float64))).astype(np.float32)
        g_den = np.zeros(len(depth), np.float32)
        g_pla = np.zeros(len(depth), np.float32)
        g_den[hit] = face_density[primitive[hit]]
        g_pla[hit] = face_planarity[primitive[hit]]
        static_conf = (g_reg * g_den * g_pla * cos).astype(np.float32)

        fused = sample["depth"].numpy().astype(np.float32)[ys][:, xs].ravel()
        fused_mask = sample["depth_mask"].numpy().astype(bool)[ys][:, xs].ravel()
        residual = np.abs(depth - fused)
        supported = hit & fused_mask & (fused > 0)
        f1 = np.ones(len(depth), np.float32)
        f1[supported] = np.exp(-residual[supported] / 2.0).astype(np.float32)

        grid_y, grid_x = np.divmod(np.arange(len(depth)), len(xs))
        pixel_y = ys[grid_y].astype(np.int32)
        pixel_x = xs[grid_x].astype(np.int32)
        stem = Path(frame.name).stem
        confidences = {"E4_STATIC": static_conf, "E5_F1": static_conf * f1}
        row = {"name": frame.name, "tin_hit_fraction": float(hit.mean())}
        for variant in variants:
            conf = confidences[variant]
            keep = hit & (conf >= float(proj["confidence_min"]))
            np.savez_compressed(
                prior_root / variant / f"{stem}.npz",
                height=np.int32(height), width=np.int32(width),
                pixel_y=pixel_y[keep], pixel_x=pixel_x[keep],
                depth=depth[keep], normal=normals[keep], confidence=conf[keep],
            )
            row[f"{variant}_pixels"] = int(keep.sum())
        for key, keep_mask in (("RAW", supported), ("E4_STATIC", supported & (static_conf >= float(proj["confidence_min"])))):
            leak[key]["gt2"] += int((residual[keep_mask] > 2.0).sum())
            leak[key]["n"] += int(keep_mask.sum())
            leak[key]["pool"].append(residual[keep_mask][::7].astype(np.float32))
        view_rows.append(row)
        if (view_index + 1) % 100 == 0:
            print(f"[s2 prior] {view_index + 1}/937", flush=True)

    qa = {}
    for key, block in leak.items():
        pooled = np.concatenate(block["pool"]) if block["pool"] else np.empty(0, np.float32)
        qa[key] = {
            "gt2m_fraction": block["gt2"] / block["n"] if block["n"] else None,
            "global_median_abs_m_sampled": float(np.median(pooled)) if len(pooled) else None,
            "global_p95_abs_m_sampled": float(np.quantile(pooled, 0.95)) if len(pooled) else None,
            "supported_pixels": block["n"],
        }
    targets = proj["leak_qa_targets"]
    passed = (
        qa["E4_STATIC"]["gt2m_fraction"] is not None
        and qa["E4_STATIC"]["gt2m_fraction"] <= float(targets["gt2m_fraction_max"])
        and qa["E4_STATIC"]["global_median_abs_m_sampled"] is not None
        and qa["E4_STATIC"]["global_median_abs_m_sampled"] <= float(targets["median_max_m"])
    )
    empty_views = {variant: sum(1 for row in view_rows if row[f"{variant}_pixels"] == 0) for variant in variants}
    receipt = {
        "schema": "jointbuildgs.p2.e4_e6_redesign_s2_v1.prior_preflight.v1",
        "task_id": common["task_id"],
        "status": "200-PASSED_S2_TIN_PRIOR_PREFLIGHT" if passed else "100-FAILED_LEAK_QA",
        "started_utc": started,
        "ended_utc": datetime.now(timezone.utc).isoformat(),
        "projection": proj,
        "scene_als_point_count": int(len(als_local)),
        "tin_vertex_count": vertex_count,
        "tin_triangle_count": triangle_count,
        "registration": registration,
        "leak_qa": qa,
        "leak_qa_passed": bool(passed),
        "view_count": len(view_rows),
        "empty_views_per_variant": empty_views,
        "views": view_rows,
        "synthetic_changes": None,
        "lod2_training_use": False,
        "official_PASS_usable": None,
        "scientific_verdict": None,
    }
    target_path = receipt_path if passed else out_root / "control/100-s2-prior-preflight-failed.json"
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": receipt["status"], "leak_qa": qa, "empty_views": empty_views}, indent=2, sort_keys=True))
    if not passed:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
