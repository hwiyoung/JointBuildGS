#!/usr/bin/env python3
"""Close preflight after the preserved first-pass gradient-indexing failure."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

import numpy as np
import open3d as o3d
import yaml

from scripts.p2.c4_existing_als_v1.prepare_prior import (
    ALS_DATUM_SHIFT_M,
    CONFIG_PATH,
    WORLD_SHIFT,
    atomic_json,
    digest,
    geometry_confidence,
    gradient_and_memory_preflight,
    load_als,
    registration_gate,
    validate_matched_control,
    visible_names,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--als-root", type=Path, required=True)
    args = parser.parse_args()
    failure_path = args.artifact_root / "control/100-c4-preflight-failed.json"
    failure = json.loads(failure_path.read_text(encoding="utf-8"))
    if failure.get("error_type") != "IndexError":
        raise RuntimeError("recovery only accepts the preserved normal-indexing failure")
    config = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
    matched = validate_matched_control(config)
    names = visible_names(config)
    view_paths = sorted((args.artifact_root / "prior/views").glob("*.npz"))
    if len(view_paths) != len(names) or {path.stem for path in view_paths} != {Path(name).stem for name in names}:
        raise RuntimeError("recovery prior inventory is not exact 937-view membership")
    seed = np.asarray(o3d.io.read_point_cloud(config["init_pointcloud"]).points)
    low = np.quantile(seed[:, :2], 0.001, axis=0) + WORLD_SHIFT[:2] - 10.0
    high = np.quantile(seed[:, :2], 0.999, axis=0) + WORLD_SHIFT[:2] + 10.0
    raw_als, raw_sources = load_als(args.als_root, (low, high))
    xyz, _, geometry = geometry_confidence(raw_als)
    registration = registration_gate(seed, xyz)
    rows = []
    first_nonempty = None
    for path in view_paths:
        with np.load(path, allow_pickle=False) as payload:
            count = int(len(payload["depth"]))
            confidence_mean = float(payload["confidence"].mean()) if count else 0.0
        if first_nonempty is None and count:
            first_nonempty = path
        rows.append({"path": str(path.relative_to(args.artifact_root)), "support_pixel_count": count, "confidence_mean": confidence_mean, "sha256": digest(path)})
    if first_nonempty is None:
        raise RuntimeError("recovery found no nonempty prior view")
    gradient = gradient_and_memory_preflight(first_nonempty)
    receipt = {
        "schema": "jointbuildgs.p2.c4_existing_als_preflight_recovery.v1",
        "status": "200-PASSED_ALIGNMENT_GRADIENT_AND_GPU_MEMORY_PREFLIGHT",
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "recovered_from_failure": {"path": str(failure_path), "sha256": digest(failure_path), "error_type": failure["error_type"]},
        "matched_control": matched,
        "raw_als_sources": raw_sources,
        "datum_transform": {"z_shift_m": ALS_DATUM_SHIFT_M},
        "alignment": registration,
        "confidence_gates": ["registration", "density", "planarity", "visibility", "current_consistency"],
        "current_conflict_policy": "LOWER_ALS_CONFIDENCE_ONLY",
        "view_count": len(rows),
        "nonempty_view_count": sum(row["support_pixel_count"] > 0 for row in rows),
        "total_support_pixel_count": sum(row["support_pixel_count"] for row in rows),
        "gradient_and_gpu_memory": gradient,
        "view_receipts": rows,
        "c5_executed": False,
        "scientific_verdict": None,
    }
    atomic_json(args.artifact_root / "control/200-c4-preflight-passed.json", receipt)
    print(json.dumps({key: receipt[key] for key in ("status", "view_count", "nonempty_view_count", "total_support_pixel_count")}, sort_keys=True))


if __name__ == "__main__":
    main()
