#!/usr/bin/env python3
"""D2a corridor smoke: exact-55 ALS prior with an injected +X delta (in-container).

Mirrors `e4_local_4906982_55v_als_prior_v1/prepare_als_prior.py` byte-for-byte in
procedure — same ALS bytes/hashes, same confidence gates, same projection and
gradient preflight — with two differences: the scene-local ALS points are
translated by the synthetic delta before confidence/projection, and the receipt
carries a `delta_injection` block. The representative panel is skipped (smoke).
The registration gate is recorded as measurement only. Non-confirmatory;
scientific_verdict stays null. Run inside the project container with a GPU.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import yaml

from scripts.p2.c4_existing_als_v1 import prepare_prior as official
from src.stage2.dataloader import ColmapDataset

REPO = Path("/workspace/JointBuildGS")
BASE = REPO / "configs/p2/e3_local_4906982_mvc_depth_v1/depth03.yaml"
FUSED = REPO / "configs/p2/e3_local_4906982_fused_vis_conf_v1/fused_vis_conf.yaml"
ALS_ROOT = Path("/artifacts/JointBuildGS/phase-payloads/p0-audit/data/raw/als")
PASSED_STATUS = "200-PASSED_EXACT55_ALIGNMENT_PROJECTION_GRADIENT_AND_GPU_MEMORY_PREFLIGHT"


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


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--smoke-root", required=True, help="container path of the smoke task root")
    parser.add_argument("--delta-xy-east-m", type=float, required=True)
    args = parser.parse_args()
    task_root = Path(args.smoke_root)
    delta = float(args.delta_xy_east_m)
    started = datetime.now(timezone.utc).isoformat()
    prior_root = task_root / "prior/views"
    passed = task_root / "control/200-55v-als-prior-preflight-passed.json"
    if passed.is_file():
        print(json.dumps({"status": "IDEMPOTENT_ALREADY_COMPLETE"}))
        return
    if prior_root.exists() and any(prior_root.iterdir()):
        raise RuntimeError("nonempty unreceipted smoke prior namespace")
    prior_root.mkdir(parents=True, exist_ok=True)

    cfg = yaml.safe_load(BASE.read_text())
    cfg.update(yaml.safe_load(FUSED.read_text())["overrides"])
    names = list(cfg["visible_views"])
    if len(names) != 55 or len(cfg["train_views"]) != 47 or len(cfg["eval_views"]) != 8:
        raise RuntimeError("frozen 55-view roles drifted")
    dataset = ColmapDataset(cfg["data_root"], downscale=1.0, load_depth=True,
                            load_normal=False, load_semantic=False, visible_views=names)
    seed = dataset.points_xyz.astype(np.float64)
    if len(seed) != 25683:
        raise RuntimeError(f"exact sparse seed drifted: {len(seed)}")
    low = np.quantile(seed[:, :2], 0.001, axis=0) + official.WORLD_SHIFT[:2] - 10.0
    high = np.quantile(seed[:, :2], 0.999, axis=0) + official.WORLD_SHIFT[:2] + 10.0
    raw_als, raw_sources = official.load_als(ALS_ROOT, (low, high))
    # Phase-D synthetic registration-residual injection (scene-local frame;
    # translation is frame-invariant). Everything downstream is the sealed path.
    raw_als = raw_als + np.asarray([delta, 0.0, 0.0], dtype=np.float64)
    xyz, normals, geometry = official.geometry_confidence(raw_als)
    try:
        registration = official.registration_gate(seed, xyz)
    except RuntimeError as exc:
        registration = {"passed": False, "measurement_failure": str(exc),
                        "registration_confidence": 0.0}
    registration["method"] = "NEAREST_XY_ROBUST_SIGNED_MEDIAN_ON_EXACT_55_SPARSE_SFM_SEED"
    registration["gate_role"] = "MEASUREMENT_ONLY_UNDER_INJECTED_DELTA"
    if not registration.get("passed"):
        raise RuntimeError(f"smoke stops: corridor gate measured failure under delta: {registration}")

    rows = []
    first_nonempty = None
    for index, frame in enumerate(dataset.frames):
        sample = dataset[index]
        projected = official.project_view(
            xyz, normals, geometry["combined_geometry"],
            registration["registration_confidence"], sample,
        )
        path = prior_root / f"{Path(frame.name).stem}.npz"
        np.savez_compressed(path, height=np.int32(sample["height"]),
                            width=np.int32(sample["width"]), **projected)
        count = int(len(projected["depth"]))
        if first_nonempty is None and count:
            first_nonempty = path
        rows.append({
            "name": frame.name,
            "path": str(path.relative_to(task_root)),
            "shape": [int(sample["height"]), int(sample["width"])],
            "support_pixel_count": count,
            "confidence_mean": float(projected["confidence"].mean()) if count else 0.0,
            "sha256": digest(path),
        })
    if first_nonempty is None or sum(r["support_pixel_count"] > 0 for r in rows) != 55:
        raise RuntimeError("smoke delta prior has empty view(s)")
    gradient = official.gradient_and_memory_preflight(first_nonempty)
    receipt = {
        "schema": "jointbuildgs.p2.journal1_phase_d_v1.d2a_delta_prior_preflight.v1",
        "task_id": "P2-JOURNAL1-PHASE-D-v1-D2A",
        "status": PASSED_STATUS,
        "started_at": started,
        "ended_at": datetime.now(timezone.utc).isoformat(),
        "delta_injection": {"dx_east_m": delta, "dz_m": 0.0, "synthetic": True,
                            "purpose": "PHASE_D_DELTA_SHIFT_REGISTRATION_RESIDUAL_PROBE",
                            "not_real_als_lineage": True},
        "sparse_seed_point_count": int(len(seed)),
        "scene_bbox_world_xy": {"min": low.tolist(), "max": high.tolist()},
        "raw_scene_point_count": int(len(raw_als)),
        "raw_als_sources": raw_sources,
        "datum_transform": {"source": "2022_ALS_ORTHOMETRIC", "target": "2024_CAMERA_ELLIPSOIDAL",
                             "z_shift_m": official.ALS_DATUM_SHIFT_M},
        "geometry_confidence": {k: v for k, v in geometry.items()
                                 if k not in {"density", "planarity", "combined_geometry"}},
        "alignment": registration,
        "confidence_gates": ["registration", "density", "planarity", "visibility", "current_consistency"],
        "current_conflict_policy": "EXP_NEG_ABS_DEPTH_RESIDUAL_OVER_2M_LOWERS_ALS_CONFIDENCE_ONLY",
        "view_count": len(rows),
        "nonempty_view_count": sum(r["support_pixel_count"] > 0 for r in rows),
        "total_support_pixel_count": sum(r["support_pixel_count"] for r in rows),
        "gradient_and_gpu_memory": gradient,
        "view_receipts": rows,
        "lod2_training_use": False,
        "scientific_verdict": None,
    }
    atomic_json(passed, receipt)
    print(json.dumps({k: receipt[k] for k in ("status", "view_count", "nonempty_view_count",
                                                "total_support_pixel_count")}, indent=2))


if __name__ == "__main__":
    main()
