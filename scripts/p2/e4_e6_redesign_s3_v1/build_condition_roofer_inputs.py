#!/usr/bin/env python3
"""Per-building roofer-input views for all six sealed conditions.

Extracts footprint(+3 m) class-2/6 crops — the effective per-building Roofer
reconstruction input — from each condition's sealed classified scene, in the
same viewer-local frame and PLY layout as the redesign assets, for the 8880
detail 3D panels.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import laspy
import numpy as np
from shapely import contains_xy
from shapely.geometry import shape

import sys
sys.path.insert(0, "/workspace/JointBuildGS")
from scripts.p2.e4_e6_redesign_s3_v1.build_viewer_assets import write_ply

ART = Path("/artifacts/JointBuildGS")
S3 = ART / "phase-payloads/p2/e4_e6_redesign_s3_v1/P2-E4-E6-REDESIGN-S3-v1"
V22 = ART / "phase-payloads/p2/e1_e6_roofer_ox_review_v1/P2-E1-E6-ROOFER-AUTO-OX-v22-ROBUST-PLANE-MATCH"
SF3 = ART / "phase-payloads/p2/c1_c2_shared_footprint_199_v3/P2-C1-C2-SHARED-FOOTPRINT-199-ORIGINAL-GLOBAL-v3/work"
TD = ART / "phase-payloads/p2/e1_e6_techdev_v1/P2-E1-E6-PRIOR-FUSION-TECHDEV-v1"
E3N = ART / "phase-payloads/p2/e3_full_scene_roofer_shared_footprint_199_v1/P2-E3-FULL-SCENE-ROOFER-SHARED-FOOTPRINT-199-v1"
CONDITIONS = {
    "E1": SF3 / "C1_L_upper/classified_scene.laz",
    "E2": SF3 / "C2_MVS/classified_scene.laz",
    "E3": E3N / "work/E3_GS_image/classified_scene.laz",
    "E4": TD / "runs/E4_GS_ALS_UNWEIGHTED/roofer/classified_scene.laz",
    "E5": TD / "runs/E5_GS_ALS_WB/roofer/classified_scene.laz",
    "E6": TD / "runs/E6_GS_LOD2_PLANES_DIAGNOSTIC/roofer/classified_scene.laz",
}
BUFFER_M = 3.0
KEEP_CLASSES = (2, 6)


def main() -> None:
    started = datetime.now(timezone.utc).isoformat()
    viewer = json.loads((V22 / "viewer_manifest.json").read_text())
    origin = np.asarray(viewer["scene_local_origin_xyz"], dtype=np.float64)
    index_of = {b["stable_id"]: int(b["population_index"]) for b in viewer["buildings"]}
    geo = json.loads((S3 / "freeze/shared_footprints.geojson").read_text())
    polys = {str(f["properties"]["stable_id"]): shape(f["geometry"]).buffer(BUFFER_M) for f in geo["features"]}

    out_root = S3 / "viewer_assets_conditions"
    receipt_rows = []
    for label, laz_path in CONDITIONS.items():
        if not laz_path.is_file():
            print(f"[cond-assets] MISSING {label}: {laz_path}", flush=True)
            continue
        las = laspy.read(laz_path)
        xyz = np.column_stack((np.asarray(las.x), np.asarray(las.y), np.asarray(las.z)))
        try:
            rgb = np.column_stack((np.asarray(las.red), np.asarray(las.green), np.asarray(las.blue)))
            rgb = (rgb / 257.0).clip(0, 255).astype(np.uint8)
        except Exception:
            rgb = np.full((len(xyz), 3), 180, dtype=np.uint8)
        cls = np.asarray(las.classification).astype(np.uint8)
        class_ok = np.isin(cls, KEEP_CLASSES)
        for sid, poly in polys.items():
            x0, y0, x1, y1 = poly.bounds
            keep = class_ok & (xyz[:, 0] >= x0) & (xyz[:, 0] <= x1) & (xyz[:, 1] >= y0) & (xyz[:, 1] <= y1)
            idx_in = np.flatnonzero(keep)
            if len(idx_in):
                inside = contains_xy(poly, xyz[idx_in, 0], xyz[idx_in, 1])
                idx_in = idx_in[inside]
            idx = index_of[sid]
            base = out_root / label / f"B{idx:03d}_{sid}"
            write_ply(base.with_suffix(".points.ply"), xyz[idx_in] - origin, rgb[idx_in], cls[idx_in])
            receipt_rows.append({"condition": label, "stable_id": sid, "points": int(len(idx_in))})
        print(f"[cond-assets] {label} done ({len(xyz)} scene pts)", flush=True)

    receipt = {
        "schema": "jointbuildgs.p2.e4_e6_redesign_s3_v1.condition_roofer_inputs.v1",
        "task_id": "P2-E4-E6-REDESIGN-S3-v1",
        "started_utc": started,
        "ended_utc": datetime.now(timezone.utc).isoformat(),
        "definition": "footprint+3m class-2/6 crop of each condition's sealed classified scene (viewer-local frame)",
        "sources": {k: str(v) for k, v in CONDITIONS.items()},
        "rows": receipt_rows,
        "scientific_verdict": None,
    }
    (out_root / "receipt.json").write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"conditions": len(CONDITIONS), "rows": len(receipt_rows)}))


if __name__ == "__main__":
    main()
