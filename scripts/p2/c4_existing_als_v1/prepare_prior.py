#!/usr/bin/env python3
"""Prepare confidence-gated Existing-ALS priors and close the C4 preflight."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any

import laspy
import numpy as np
import open3d as o3d
from scipy.spatial import cKDTree
import torch
import yaml

from src.stage2.dataloader import ColmapDataset
from src.stage2.external_als_prior import robust_als_depth_loss, sign_invariant_als_normal_loss


REPO_ROOT = Path(__file__).resolve().parents[3]
CONFIG_PATH = REPO_ROOT / "configs/p2/c4_existing_als_v1/c4_existing_als_seed0_gpu0.yaml"
ALS_HASHES = {
    "690_5335.laz": "01602b7385aaf7324f89da6183df3dbdeffa237f85bf57dc27208b554b4fc0b3",
    "690_5336.laz": "98ab7ad7f4c5108ebf41bc62186b336c6cd8a70b82fceec57136a56c0188b566",
    "691_5335.laz": "9e14119bb0af7d5a300aa3a2a19074219b4d6d290923b4b90277c317e8b33720",
    "691_5336.laz": "63c64002fc55d8b99a49749b5a2e36d802186186a950c89779463274e3cb950d",
}
WORLD_SHIFT = np.asarray([690953.0, 5336071.0, 604.0], dtype=np.float64)
ALS_DATUM_SHIFT_M = 45.7


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def visible_names(config: dict[str, Any]) -> list[str]:
    manifest = json.loads(Path(config["exact_view_manifest"]).read_text(encoding="utf-8"))
    if digest(Path(config["exact_view_manifest"])) != config["exact_view_manifest_sha256"]:
        raise RuntimeError("exact 937-member manifest hash drifted")
    names = [str(row["basename"]) for row in manifest["rows"]]
    if len(names) != 937:
        raise RuntimeError(f"expected 937 exact views, got {len(names)}")
    return names


def validate_matched_control(c4: dict[str, Any]) -> dict[str, Any]:
    matched_path = Path(c4["matched_c3_config"])
    if digest(matched_path) != c4["matched_c3_config_sha256"]:
        raise RuntimeError("matched C3 config hash drifted")
    c3 = yaml.safe_load(matched_path.read_text(encoding="utf-8"))
    differences = []
    for key, value in c3.items():
        if key == "out_dir":
            continue
        if key not in c4 or c4[key] != value:
            differences.append({"key": key, "c3": value, "c4": c4.get(key, "MISSING")})
    if differences:
        raise RuntimeError(f"C4 base differs from exact C3-2 control: {differences}")
    if int(c4["seed"]) != 0 or int(c4["max_iter"]) != 30000:
        raise RuntimeError("C4 seed/iteration drifted")
    if digest(Path(c4["init_pointcloud"])) != c4["init_pointcloud_sha256"]:
        raise RuntimeError("C4 initialization pointcloud hash drifted")
    return {
        "matched_c3_config": str(matched_path),
        "matched_c3_config_sha256": digest(matched_path),
        "same_seed": True,
        "same_initialization": True,
        "same_iteration_count": True,
        "base_key_count_compared": len(c3) - 1,
        "only_additional_training_channels": ["external_als_depth", "external_als_normal", "external_als_confidence"],
    }


def load_als(als_root: Path, bbox_world: tuple[np.ndarray, np.ndarray]) -> tuple[np.ndarray, list[dict[str, Any]]]:
    low, high = bbox_world
    parts: list[np.ndarray] = []
    source_rows = []
    for name, expected in ALS_HASHES.items():
        path = als_root / name
        actual = digest(path)
        if actual != expected:
            raise RuntimeError(f"raw ALS hash drift: {name} {actual}")
        selected = 0
        with laspy.open(path) as reader:
            source_count = int(reader.header.point_count)
            for chunk in reader.chunk_iterator(2_000_000):
                x = np.asarray(chunk.x)
                y = np.asarray(chunk.y)
                z = np.asarray(chunk.z) + ALS_DATUM_SHIFT_M
                keep = (x >= low[0]) & (x <= high[0]) & (y >= low[1]) & (y <= high[1])
                if bool(keep.any()):
                    part = np.column_stack((x[keep], y[keep], z[keep])) - WORLD_SHIFT
                    parts.append(part)
                    selected += len(part)
        source_rows.append({"path": str(path), "sha256": actual, "source_point_count": source_count, "scene_selected_point_count": selected})
    if not parts:
        raise RuntimeError("raw ALS has no points in the exact C3 scene bounds")
    return np.concatenate(parts), source_rows


def geometry_confidence(points: np.ndarray) -> tuple[np.ndarray, np.ndarray, dict[str, Any]]:
    cloud = o3d.geometry.PointCloud(o3d.utility.Vector3dVector(points))
    cloud = cloud.voxel_down_sample(voxel_size=0.75)
    cloud.estimate_normals(o3d.geometry.KDTreeSearchParamHybrid(radius=2.0, max_nn=30))
    xyz = np.asarray(cloud.points)
    normals = np.asarray(cloud.normals)
    tree = cKDTree(xyz)
    density_count = tree.query_ball_point(xyz, r=1.5, return_length=True, workers=-1)
    density = np.clip((density_count.astype(np.float32) - 2.0) / 18.0, 0.0, 1.0)
    planarity = np.empty(len(xyz), dtype=np.float32)
    batch_size = 100_000
    for start in range(0, len(xyz), batch_size):
        stop = min(start + batch_size, len(xyz))
        _, neighbors = tree.query(xyz[start:stop], k=min(12, len(xyz)), workers=-1)
        delta = xyz[neighbors] - xyz[start:stop, None, :]
        signed = np.abs(np.einsum("bki,bi->bk", delta, normals[start:stop]))
        roughness = np.median(signed, axis=1)
        planarity[start:stop] = np.exp(-roughness / 0.20).astype(np.float32)
    confidence = density * planarity
    return xyz, normals.astype(np.float32), {
        "density": density,
        "planarity": planarity,
        "combined_geometry": confidence,
        "voxel_point_count": int(len(xyz)),
        "density_mean": float(density.mean()),
        "planarity_mean": float(planarity.mean()),
    }


def registration_gate(seed_xyz: np.ndarray, als_xyz: np.ndarray) -> dict[str, Any]:
    tree = cKDTree(als_xyz[:, :2])
    distance, index = tree.query(seed_xyz[:, :2], k=1, workers=-1)
    match = distance < 0.75
    if int(match.sum()) < 1000:
        raise RuntimeError("insufficient ALS/current-image XY registration support")
    signed_z = seed_xyz[match, 2] - als_xyz[index[match], 2]
    median_z = float(np.median(signed_z))
    xy_p95 = float(np.quantile(distance[match], 0.95))
    passed = abs(median_z) <= 0.50 and xy_p95 <= 0.50
    confidence = float(np.exp(-abs(median_z) / 0.50)) if passed else 0.0
    receipt = {
        "method": "NEAREST_XY_ROBUST_SIGNED_MEDIAN_ON_EXACT_C3_NEUTRAL_DENSE_SEED",
        "matched_point_count": int(match.sum()),
        "xy_distance_median_m": float(np.median(distance[match])),
        "xy_distance_p95_m": xy_p95,
        "signed_z_residual_median_m": median_z,
        "absolute_z_residual_median_m": float(np.median(np.abs(signed_z))),
        "absolute_z_residual_p95_m": float(np.quantile(np.abs(signed_z), 0.95)),
        "gate_thresholds": {"abs_signed_z_median_max_m": 0.50, "xy_p95_max_m": 0.50},
        "passed": passed,
        "registration_confidence": confidence,
        "note": "absolute residual tails include real surface/temporal differences and are not used as a rigid-registration offset",
    }
    if not passed:
        raise RuntimeError(f"ALS alignment gate failed: {receipt}")
    return receipt


def project_view(
    xyz: np.ndarray,
    normals: np.ndarray,
    geometry_confidence_value: np.ndarray,
    registration_confidence: float,
    sample: dict[str, Any],
) -> dict[str, np.ndarray]:
    k = sample["K"].numpy().astype(np.float64)
    w2c = sample["w2c"].numpy().astype(np.float64)
    camera = xyz @ w2c[:3, :3].T + w2c[:3, 3]
    front = camera[:, 2] > 0.1
    uvw = camera @ k.T
    uv = np.zeros((len(xyz), 2), dtype=np.float64)
    uv[front] = uvw[front, :2] / uvw[front, 2:3]
    height, width = int(sample["height"]), int(sample["width"])
    inside = front & (uv[:, 0] >= 0) & (uv[:, 0] < width) & (uv[:, 1] >= 0) & (uv[:, 1] < height)
    selected = np.flatnonzero(inside)
    if not len(selected):
        return {"pixel_y": np.empty(0, np.int32), "pixel_x": np.empty(0, np.int32), "depth": np.empty(0, np.float32), "normal": np.empty((0, 3), np.float32), "confidence": np.empty(0, np.float32)}
    pixel_x = np.rint(uv[selected, 0]).astype(np.int32).clip(0, width - 1)
    pixel_y = np.rint(uv[selected, 1]).astype(np.int32).clip(0, height - 1)
    key = pixel_y.astype(np.int64) * width + pixel_x
    order = np.lexsort((camera[selected, 2], key))
    sorted_key = key[order]
    first = np.r_[True, sorted_key[1:] != sorted_key[:-1]]
    chosen = selected[order[first]]
    x = np.rint(uv[chosen, 0]).astype(np.int32).clip(0, width - 1)
    y = np.rint(uv[chosen, 1]).astype(np.int32).clip(0, height - 1)
    depth = camera[chosen, 2].astype(np.float32)
    confidence = geometry_confidence_value[chosen].astype(np.float32) * float(registration_confidence)
    current_depth = sample.get("depth")
    current_mask = sample.get("depth_mask")
    if current_depth is not None and current_mask is not None:
        current_depth_np = current_depth.numpy()
        current_mask_np = current_mask.numpy()[y, x]
        residual = np.abs(current_depth_np[y, x] - depth)
        consistency = np.where(current_mask_np, np.exp(-residual / 2.0), 0.50).astype(np.float32)
    else:
        consistency = np.full(len(chosen), 0.50, dtype=np.float32)
    confidence *= consistency
    keep = confidence >= 0.05
    return {"pixel_y": y[keep], "pixel_x": x[keep], "depth": depth[keep], "normal": normals[chosen][keep].astype(np.float32), "confidence": confidence[keep].astype(np.float32)}


def gradient_and_memory_preflight(view_path: Path) -> dict[str, Any]:
    with np.load(view_path, allow_pickle=False) as payload:
        depth_value = payload["depth"].astype(np.float32)
        normal_value = payload["normal"].astype(np.float32)
        confidence_value = payload["confidence"].astype(np.float32)
    if len(depth_value) == 0:
        raise RuntimeError("gradient preflight selected an empty ALS view")
    count = min(len(depth_value), 10000)
    device = torch.device("cuda")
    depth_prior = torch.from_numpy(depth_value[:count]).to(device).reshape(1, count)
    confidence = torch.from_numpy(confidence_value[:count]).to(device).reshape(1, count)
    mask = torch.ones((1, count), dtype=torch.bool, device=device)
    depth_pred = (depth_prior + 0.25).detach().requires_grad_(True)
    normal_prior = torch.from_numpy(normal_value[:count]).to(device).reshape(1, count, 3)
    normal_pred = (normal_prior + torch.tensor([0.1, -0.05, 0.02], device=device)).detach().requires_grad_(True)
    depth_loss, _ = robust_als_depth_loss(depth_pred, depth_prior, confidence, mask, huber_delta_m=1.0)
    normal_loss, _ = sign_invariant_als_normal_loss(normal_pred, normal_prior, confidence, mask)
    total = 0.01 * depth_loss + 0.005 * normal_loss
    total.backward()
    free, total_memory = torch.cuda.mem_get_info()
    receipt = {
        "sample_pixel_count": count,
        "weighted_depth_loss": float((0.01 * depth_loss).detach().cpu()),
        "weighted_normal_loss": float((0.005 * normal_loss).detach().cpu()),
        "depth_gradient_l1": float(depth_pred.grad.abs().sum().detach().cpu()),
        "normal_gradient_l1": float(normal_pred.grad.abs().sum().detach().cpu()),
        "gpu_name": torch.cuda.get_device_name(0),
        "gpu_total_bytes": int(total_memory),
        "gpu_free_bytes_before_training": int(free),
    }
    receipt["passed"] = receipt["depth_gradient_l1"] > 0 and receipt["normal_gradient_l1"] > 0 and free >= 22_000 * 1024**2
    if not receipt["passed"]:
        raise RuntimeError(f"gradient/GPU-memory preflight failed: {receipt}")
    return receipt


def run(output_root: Path, als_root: Path) -> dict[str, Any]:
    if output_root.exists() and any(output_root.iterdir()):
        raise RuntimeError("add-once C4 prior namespace is not empty")
    output_root.mkdir(parents=True, exist_ok=True)
    config = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
    try:
        matched = validate_matched_control(config)
        names = visible_names(config)
        dataset = ColmapDataset(config["data_root"], downscale=1.0, load_depth=True, load_normal=False, load_semantic=False, visible_views=names)
        seed = np.asarray(o3d.io.read_point_cloud(config["init_pointcloud"]).points)
        low = np.quantile(seed[:, :2], 0.001, axis=0) + WORLD_SHIFT[:2] - 10.0
        high = np.quantile(seed[:, :2], 0.999, axis=0) + WORLD_SHIFT[:2] + 10.0
        raw_als, raw_sources = load_als(als_root, (low, high))
        xyz, normals, geometry = geometry_confidence(raw_als)
        registration = registration_gate(seed, xyz)
        prior_root = output_root / "prior/views"
        prior_root.mkdir(parents=True, exist_ok=True)
        view_receipts = []
        first_nonempty = None
        for index, frame in enumerate(dataset.frames):
            sample = dataset[index]
            projected = project_view(xyz, normals, geometry["combined_geometry"], registration["registration_confidence"], sample)
            path = prior_root / f"{Path(frame.name).stem}.npz"
            np.savez_compressed(path, height=np.int32(sample["height"]), width=np.int32(sample["width"]), **projected)
            if first_nonempty is None and len(projected["depth"]):
                first_nonempty = path
            view_receipts.append({"name": frame.name, "path": str(path.relative_to(output_root)), "support_pixel_count": int(len(projected["depth"])), "confidence_mean": float(projected["confidence"].mean()) if len(projected["confidence"]) else 0.0, "sha256": digest(path)})
            if (index + 1) % 50 == 0:
                print(f"[C4 prior] views={index + 1}/937", flush=True)
        if first_nonempty is None:
            raise RuntimeError("all projected ALS prior views are empty")
        gradient = gradient_and_memory_preflight(first_nonempty)
        receipt = {
            "schema": "jointbuildgs.p2.c4_existing_als_preflight.v1",
            "status": "200-PASSED_ALIGNMENT_GRADIENT_AND_GPU_MEMORY_PREFLIGHT",
            "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "task_id": config["task_id"],
            "decision": config["decision"],
            "matched_control": matched,
            "raw_als_sources": raw_sources,
            "datum_transform": {"source": "2022_ALS_ORTHOMETRIC", "target": "2024_CAMERA_ELLIPSOIDAL", "z_shift_m": ALS_DATUM_SHIFT_M},
            "scene_bbox_world_xy": {"min": low.tolist(), "max": high.tolist()},
            "raw_scene_point_count": int(len(raw_als)),
            "geometry_confidence": {key: value for key, value in geometry.items() if key not in {"density", "planarity", "combined_geometry"}},
            "alignment": registration,
            "confidence_gates": ["registration", "density", "planarity", "visibility", "current_consistency"],
            "current_conflict_policy": "EXP_NEG_ABS_DEPTH_RESIDUAL_OVER_2M_LOWERS_ALS_CONFIDENCE_ONLY",
            "view_count": len(view_receipts),
            "nonempty_view_count": sum(row["support_pixel_count"] > 0 for row in view_receipts),
            "total_support_pixel_count": sum(row["support_pixel_count"] for row in view_receipts),
            "gradient_and_gpu_memory": gradient,
            "view_receipts": view_receipts,
            "c5_executed": False,
            "scientific_verdict": None,
        }
        atomic_json(output_root / "control/200-c4-preflight-passed.json", receipt)
        return receipt
    except Exception as exc:
        atomic_json(output_root / "control/100-c4-preflight-failed.json", {"schema": "jointbuildgs.p2.c4_existing_als_preflight_failure.v1", "status": "100-FAILED_C4_PREFLIGHT", "error_type": type(exc).__name__, "error": str(exc), "checkpoint_preserved": True, "scientific_verdict": None})
        raise


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--als-root", type=Path, required=True)
    args = parser.parse_args()
    result = run(args.output_root, args.als_root)
    print(json.dumps({"status": result["status"], "view_count": result["view_count"], "nonempty_view_count": result["nonempty_view_count"], "total_support_pixel_count": result["total_support_pixel_count"]}, sort_keys=True))


if __name__ == "__main__":
    main()
