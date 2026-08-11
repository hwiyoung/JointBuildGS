#!/usr/bin/env python3
"""Project the frozen Existing-ALS source into the exact frozen 55 crop cameras."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import yaml

from scripts.p2.c4_existing_als_v1 import prepare_prior as official
from src.stage2.dataloader import ColmapDataset


REPO = Path("/workspace/JointBuildGS")
TASK_ID = "P2-E4-LOCAL-4906982-55V-ALS-PRIOR-v1"
TASK_ROOT = Path(
    "/artifacts/JointBuildGS/phase-payloads/p2/e4_local_4906982_55v_als_prior_v1/"
    "P2-E4-LOCAL-4906982-55V-ALS-PRIOR-v1"
)
COMMON = REPO / "configs/p2/e4_local_4906982_55v_als_prior_v1/common.yaml"
BASE = REPO / "configs/p2/e3_local_4906982_mvc_depth_v1/depth03.yaml"
FUSED = REPO / "configs/p2/e3_local_4906982_fused_vis_conf_v1/fused_vis_conf.yaml"
OLD_PRIOR = Path(
    "/artifacts/JointBuildGS/phase-payloads/p2/c4_existing_als_v1/"
    "P2-C4-EXISTING-ALS-BOUNDED-TECHDEV-v1/prior/views"
)
ALS_ROOT = Path("/artifacts/JointBuildGS/phase-payloads/p0-audit/data/raw/als")


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def materialized() -> dict[str, Any]:
    config = yaml.safe_load(BASE.read_text())
    config.update(yaml.safe_load(FUSED.read_text())["overrides"])
    return config


def shape_mismatch(names: list[str], dataset: ColmapDataset) -> dict[str, Any]:
    old = {path.stem: path for path in OLD_PRIOR.glob("*.npz")}
    rows = []
    for frame in dataset.frames:
        path = old.get(Path(frame.name).stem)
        if path is None:
            rows.append({"name": frame.name, "state": "missing_old_prior"})
            continue
        with np.load(path, allow_pickle=False) as payload:
            old_shape = [int(payload["height"]), int(payload["width"])]
        new_shape = [int(frame.height), int(frame.width)]
        rows.append({"name": frame.name, "old_shape": old_shape, "exact_55_crop_shape": new_shape, "matches": old_shape == new_shape})
    return {
        "old_prior_view_names_present": sum(row.get("state") is None for row in rows),
        "shape_match_count": sum(bool(row.get("matches")) for row in rows),
        "shape_mismatch_count": sum(row.get("matches") is False for row in rows),
        "missing_count": sum(row.get("state") == "missing_old_prior" for row in rows),
        "reuse_decision": "REPROJECT_SAME_ALS_TO_EXACT_55_CAMERAS_DO_NOT_RESIZE",
        "rows": rows,
    }


def render_prior_panel(dataset: ColmapDataset, rows: list[dict[str, Any]], prior_root: Path) -> Path:
    candidate = max(rows, key=lambda row: row["support_pixel_count"])
    index = next(i for i, frame in enumerate(dataset.frames) if frame.name == candidate["name"])
    sample = dataset[index]
    with np.load(prior_root / f"{Path(candidate['name']).stem}.npz", allow_pickle=False) as prior:
        yy = prior["pixel_y"].astype(int)
        xx = prior["pixel_x"].astype(int)
        als_depth = prior["depth"].astype(float)
        confidence = prior["confidence"].astype(float)
    height, width = int(sample["height"]), int(sample["width"])
    als_image = np.full((height, width), np.nan, np.float32)
    confidence_image = np.full((height, width), np.nan, np.float32)
    als_image[yy, xx] = als_depth
    confidence_image[yy, xx] = confidence
    current = sample["depth"].numpy().astype(float)
    current_mask = sample["depth_mask"].numpy().astype(bool)
    residual = np.full((height, width), np.nan, np.float32)
    common = np.isfinite(als_image) & current_mask
    residual[common] = np.abs(als_image[common] - current[common])
    rgb = sample["rgb"].numpy()

    figure, axes = plt.subplots(1, 5, figsize=(22, 5))
    axes[0].imshow(np.clip(rgb, 0, 1)); axes[0].set_title("RGB")
    im1 = axes[1].imshow(np.where(current_mask, current, np.nan), cmap="viridis"); axes[1].set_title("Fused MVS camera-Z"); figure.colorbar(im1, ax=axes[1], fraction=.046)
    im2 = axes[2].imshow(als_image, cmap="viridis"); axes[2].set_title("Reprojected Existing ALS camera-Z"); figure.colorbar(im2, ax=axes[2], fraction=.046)
    im3 = axes[3].imshow(residual, cmap="magma", vmin=0, vmax=5); axes[3].set_title("|ALS - fused MVS| (0..5 m)"); figure.colorbar(im3, ax=axes[3], fraction=.046)
    im4 = axes[4].imshow(confidence_image, cmap="plasma", vmin=0, vmax=1); axes[4].set_title("ALS confidence"); figure.colorbar(im4, ax=axes[4], fraction=.046)
    for axis in axes:
        axis.axis("off")
    figure.suptitle(f"Exact 55-camera ALS prior preflight — {candidate['name']}", fontsize=15, fontweight="bold")
    figure.tight_layout()
    output = TASK_ROOT / "representative_images/als_prior_preflight.png"
    output.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(output, dpi=160, bbox_inches="tight")
    plt.close(figure)
    return output


def main() -> None:
    started = datetime.now(timezone.utc).isoformat()
    prior_root = TASK_ROOT / "prior/views"
    passed = TASK_ROOT / "control/200-55v-als-prior-preflight-passed.json"
    if passed.is_file():
        receipt = json.loads(passed.read_text())
        for row in receipt["view_receipts"]:
            path = TASK_ROOT / row["path"]
            if not path.is_file() or digest(path) != row["sha256"]:
                raise RuntimeError(f"existing prior hash drift: {path}")
        print(json.dumps({"status": "IDEMPOTENT_ALREADY_COMPLETE", "view_count": receipt["view_count"]}))
        return
    failure_path = TASK_ROOT / "control/100-55v-als-prior-preflight-failed.json"
    recover_panel_failure = False
    if prior_root.exists() and any(prior_root.iterdir()):
        if failure_path.is_file():
            failure = json.loads(failure_path.read_text())
            recover_panel_failure = (
                failure.get("error_type") == "KeyError"
                and failure.get("error") == "'image'"
                and len(list(prior_root.glob("*.npz"))) == 55
            )
        if not recover_panel_failure:
            raise RuntimeError("nonempty unreceipted exact-55 ALS prior namespace")
    prior_root.mkdir(parents=True, exist_ok=True)
    try:
        cfg = materialized()
        names = list(cfg["visible_views"])
        if len(names) != 55 or len(cfg["train_views"]) != 47 or len(cfg["eval_views"]) != 8:
            raise RuntimeError("frozen 55-view roles drifted")
        dataset = ColmapDataset(cfg["data_root"], downscale=1.0, load_depth=True, load_normal=False, load_semantic=False, visible_views=names)
        mismatch = shape_mismatch(names, dataset)
        if mismatch["shape_mismatch_count"] != 46 or mismatch["missing_count"] != 0:
            raise RuntimeError(f"unexpected old-prior shape inventory: {mismatch}")

        seed = dataset.points_xyz.astype(np.float64)
        if len(seed) != 25683:
            raise RuntimeError(f"exact sparse seed drifted: {len(seed)}")
        low = np.quantile(seed[:, :2], 0.001, axis=0) + official.WORLD_SHIFT[:2] - 10.0
        high = np.quantile(seed[:, :2], 0.999, axis=0) + official.WORLD_SHIFT[:2] + 10.0
        raw_als, raw_sources = official.load_als(ALS_ROOT, (low, high))
        xyz, normals, geometry = official.geometry_confidence(raw_als)
        registration = official.registration_gate(seed, xyz)
        registration["method"] = "NEAREST_XY_ROBUST_SIGNED_MEDIAN_ON_EXACT_55_SPARSE_SFM_SEED"

        rows = []
        first_nonempty = None
        for index, frame in enumerate(dataset.frames):
            sample = dataset[index]
            path = prior_root / f"{Path(frame.name).stem}.npz"
            if recover_panel_failure:
                with np.load(path, allow_pickle=False) as payload:
                    stored_shape = [int(payload["height"]), int(payload["width"])]
                    expected_shape = [int(sample["height"]), int(sample["width"])]
                    if stored_shape != expected_shape:
                        raise RuntimeError(f"recovery prior shape drift: {frame.name} {stored_shape} != {expected_shape}")
                    count = int(len(payload["depth"]))
                    confidence_mean = float(payload["confidence"].mean()) if count else 0.0
            else:
                projected = official.project_view(
                    xyz,
                    normals,
                    geometry["combined_geometry"],
                    registration["registration_confidence"],
                    sample,
                )
                np.savez_compressed(path, height=np.int32(sample["height"]), width=np.int32(sample["width"]), **projected)
                count = int(len(projected["depth"]))
                confidence_mean = float(projected["confidence"].mean()) if count else 0.0
            if first_nonempty is None and count:
                first_nonempty = path
            rows.append({
                "name": frame.name,
                "path": str(path.relative_to(TASK_ROOT)),
                "shape": [int(sample["height"]), int(sample["width"])],
                "support_pixel_count": count,
                "confidence_mean": confidence_mean,
                "sha256": digest(path),
            })
        if first_nonempty is None or sum(row["support_pixel_count"] > 0 for row in rows) != 55:
            raise RuntimeError("exact 55 ALS prior has empty view(s)")
        gradient = official.gradient_and_memory_preflight(first_nonempty)
        panel = render_prior_panel(dataset, rows, prior_root)
        receipt = {
            "schema": "jointbuildgs.p2.e4_local_4906982_55v_als_prior_preflight.v1",
            "task_id": TASK_ID,
            "status": "200-PASSED_EXACT55_ALIGNMENT_PROJECTION_GRADIENT_AND_GPU_MEMORY_PREFLIGHT",
            "started_at": started,
            "ended_at": datetime.now(timezone.utc).isoformat(),
            "source_camera_inventory": mismatch,
            "recovered_from_preserved_failure": {
                "path": str(failure_path),
                "sha256": digest(failure_path),
                "error_type": "KeyError",
                "scope": "representative_panel_only",
            } if recover_panel_failure else None,
            "camera_crop_or_roles_regenerated": False,
            "sparse_seed_point_count": int(len(seed)),
            "sparse_seed_source": str(Path(cfg["data_root"]) / "sparse/0/points3D.bin"),
            "scene_bbox_world_xy": {"min": low.tolist(), "max": high.tolist()},
            "raw_scene_point_count": int(len(raw_als)),
            "raw_als_sources": raw_sources,
            "datum_transform": {"source": "2022_ALS_ORTHOMETRIC", "target": "2024_CAMERA_ELLIPSOIDAL", "z_shift_m": official.ALS_DATUM_SHIFT_M},
            "geometry_confidence": {key: value for key, value in geometry.items() if key not in {"density", "planarity", "combined_geometry"}},
            "alignment": registration,
            "confidence_gates": ["registration", "density", "planarity", "visibility", "current_consistency"],
            "current_consistency_target": "FUSED_VIS_CONF_OPENMVS_CAMERA_Z",
            "current_conflict_policy": "EXP_NEG_ABS_DEPTH_RESIDUAL_OVER_2M_LOWERS_ALS_CONFIDENCE_ONLY",
            "view_count": len(rows),
            "nonempty_view_count": sum(row["support_pixel_count"] > 0 for row in rows),
            "total_support_pixel_count": sum(row["support_pixel_count"] for row in rows),
            "gradient_and_gpu_memory": gradient,
            "view_receipts": rows,
            "representative_image": {"path": str(panel.relative_to(TASK_ROOT)), "sha256": digest(panel)},
            "lod2_training_use": False,
            "scientific_verdict": None,
        }
        atomic_json(passed, receipt)
        print(json.dumps({key: receipt[key] for key in ("status", "view_count", "nonempty_view_count", "total_support_pixel_count")}, indent=2))
    except Exception as exc:
        atomic_json(TASK_ROOT / "control/100-55v-als-prior-preflight-failed.json", {
            "schema": "jointbuildgs.p2.e4_local_4906982_55v_als_prior_preflight_failure.v1",
            "task_id": TASK_ID,
            "status": "100-FAILED_BEFORE_TRAINING",
            "error_type": type(exc).__name__,
            "error": str(exc),
            "training_started": False,
            "scientific_verdict": None,
        })
        raise


if __name__ == "__main__":
    main()
