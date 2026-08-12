#!/usr/bin/env python3
"""Extract per-building qualitative assets for the redesign arms.

For each of the 199 shared-footprint buildings and each S2 arm, writes the FULL
(un-capped) roofer-input point crop as a binary PLY (xyz+rgb+classification)
plus the per-building roofer LoD2.2 mesh as OBJ, for lazy-loading in the
8876-family viewer. Read-only inputs; outputs under the S3 namespace.
"""
from __future__ import annotations

import json
import struct
from datetime import datetime, timezone
from pathlib import Path

import laspy
import numpy as np
from shapely.geometry import shape

import sys
sys.path.insert(0, "/workspace/JointBuildGS")
from scripts.p2.c1_c2_shared_footprint_199_v3.build_cloudcompare_review10 import lod22_triangles

ART = Path("/artifacts/JointBuildGS")
S3 = ART / "phase-payloads/p2/e4_e6_redesign_s3_v1/P2-E4-E6-REDESIGN-S3-v1"
V22 = ART / "phase-payloads/p2/e1_e6_roofer_ox_review_v1/P2-E1-E6-ROOFER-AUTO-OX-v22-ROBUST-PLANE-MATCH"
ARMS = ("E4_V2_STATIC", "E5_V2_F1")
BUFFER_M = 8.0


def write_ply(path: Path, xyz: np.ndarray, rgb: np.ndarray, cls: np.ndarray) -> None:
    header = (
        "ply\nformat binary_little_endian 1.0\n"
        f"element vertex {len(xyz)}\n"
        "property float x\nproperty float y\nproperty float z\n"
        "property uchar red\nproperty uchar green\nproperty uchar blue\n"
        "property uchar classification\nend_header\n"
    ).encode("ascii")
    body = np.empty(len(xyz), dtype=[("xyz", "<f4", 3), ("rgb", "u1", 3), ("c", "u1")])
    body["xyz"] = xyz.astype(np.float32)
    body["rgb"] = rgb
    body["c"] = cls
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as handle:
        handle.write(header)
        body.tofile(handle)


def obj_bytes(name: str, triangles: np.ndarray) -> bytes:
    lines = [f"o {name}"]
    index = 1
    for tri in triangles:
        for v in tri:
            lines.append(f"v {v[0]:.3f} {v[1]:.3f} {v[2]:.3f}")
        lines.append(f"f {index} {index + 1} {index + 2}")
        index += 3
    return ("\n".join(lines) + "\n").encode("ascii")


def main() -> None:
    started = datetime.now(timezone.utc).isoformat()
    viewer = json.loads((V22 / "viewer_manifest.json").read_text())
    origin = np.asarray(viewer["scene_local_origin_xyz"], dtype=np.float64)
    geo = json.loads((S3 / "freeze/shared_footprints.geojson").read_text())
    boxes = {}
    for f in geo["features"]:
        sid = str(f["properties"]["stable_id"])
        minx, miny, maxx, maxy = shape(f["geometry"]).bounds
        boxes[sid] = (minx - BUFFER_M, miny - BUFFER_M, maxx + BUFFER_M, maxy + BUFFER_M)
    index_of = {b["stable_id"]: int(b["population_index"]) for b in viewer["buildings"]}

    out_root = S3 / "viewer_assets"
    receipt_rows = []
    for arm in ARMS:
        las = laspy.read(S3 / "work" / arm / "classified_scene.laz")
        xyz = np.column_stack((np.asarray(las.x), np.asarray(las.y), np.asarray(las.z)))
        rgb = np.column_stack((np.asarray(las.red), np.asarray(las.green), np.asarray(las.blue)))
        rgb = (rgb / 257.0).clip(0, 255).astype(np.uint8)
        cls = np.asarray(las.classification).astype(np.uint8)
        cityjson = json.loads((S3 / "work" / arm / "assembled.city.json").read_text())
        for sid, (x0, y0, x1, y1) in boxes.items():
            keep = (xyz[:, 0] >= x0) & (xyz[:, 0] <= x1) & (xyz[:, 1] >= y0) & (xyz[:, 1] <= y1)
            idx = index_of[sid]
            base = out_root / arm / f"B{idx:03d}_{sid}"
            local = xyz[keep] - origin
            write_ply(base.with_suffix(".points.ply"), local, rgb[keep], cls[keep])
            triangles = lod22_triangles(cityjson, sid)
            tri_local = (np.asarray(triangles) - origin) if triangles else np.empty((0, 3, 3))
            base.with_suffix(".roofer.obj").parent.mkdir(parents=True, exist_ok=True)
            base.with_suffix(".roofer.obj").write_bytes(obj_bytes(f"{arm}_{sid}", tri_local))
            receipt_rows.append({"arm": arm, "stable_id": sid, "points": int(keep.sum()), "triangles": int(len(tri_local))})
        print(f"[assets] {arm} done", flush=True)

    receipt = {
        "schema": "jointbuildgs.p2.e4_e6_redesign_s3_v1.viewer_assets.v1",
        "task_id": "P2-E4-E6-REDESIGN-S3-v1",
        "started_utc": started,
        "ended_utc": datetime.now(timezone.utc).isoformat(),
        "coordinate_frame": "viewer_local (world minus scene_local_origin_xyz)",
        "buffer_m": BUFFER_M,
        "display_cap": None,
        "rows": receipt_rows,
        "scientific_verdict": None,
    }
    (out_root / "assets_receipt.json").write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    total = sum(r["points"] for r in receipt_rows)
    print(json.dumps({"buildings": len(boxes), "arms": len(ARMS), "total_points": total}))


if __name__ == "__main__":
    main()
