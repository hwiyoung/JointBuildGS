#!/usr/bin/env python3
"""Audit every S0 camera pose relative to 4906982 without changing selection."""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import numpy as np

from scripts.p2.e3_local_review_v1.build_review import (
    camera_center,
    load_building,
    load_footprint,
    polygon_rings,
)
from scripts.p2.qualitative_199_common_manifest_v1.build_manifest import prism_points
from src.stage2.colmap_io import read_cameras_bin, read_images_bin
from src.stage2.image_projection import base_to_canonical, canonical_to_base, in_frame_mask, project_canonical_points


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = args.artifact_root
    manifest = root / (
        "phase-payloads/p2/qualitative_199_common_manifest_v1/"
        "P2-QUALITATIVE-199-COMMON-MANIFEST-v1/manifest/"
        "building_camera_view_crop_manifest_v1.jsonl"
    )
    scene_path = root / "phase-payloads/p0-audit/data/work/opf/opf/scene_reference_frame.json"
    colmap = root / "phase-payloads/p0-audit/data/work/mvs/colmap_dense"
    building = load_building(manifest, "DEBY_LOD2_4906982")
    footprint = load_footprint(
        root
        / "phase-payloads/p2/c1_c2_shared_footprint_199_v3/"
        "P2-C1-C2-SHARED-FOOTPRINT-199-ORIGINAL-GLOBAL-v3-replay-20260806a/"
        "freeze/shared_footprints_199.geojson",
        "DEBY_LOD2_4906982",
    )
    scene = json.loads(scene_path.read_text(encoding="utf-8"))
    cameras = read_cameras_bin(colmap / "sparse/cameras.bin")
    images = read_images_bin(colmap / "sparse/images.bin")
    center_base = np.asarray(
        [*building["principal_frame"]["center_xy"], np.mean(building["z_range_ellipsoidal_m"])],
        dtype=np.float64,
    )
    volume = base_to_canonical(
        prism_points(building["viewport_bbox_xy"], building["z_range_ellipsoidal_m"]),
        scene,
        input_datum="ellipsoidal",
    )
    roof_base = np.vstack(
        [
            np.column_stack(
                (ring[:, :2], np.full(len(ring), building["z_range_ellipsoidal_m"][1]))
            )
            for ring in polygon_rings(footprint)
        ]
    )
    roof = base_to_canonical(roof_base, scene, input_datum="ellipsoidal")
    rows = []
    for image in sorted(images.values(), key=lambda value: value.name):
        camera = cameras[image.camera_id]
        center_world = canonical_to_base(camera_center(image), scene, output_datum="ellipsoidal")[0]
        delta = center_world - center_base
        direction = delta / max(float(np.linalg.norm(delta)), 1.0e-12)
        nadir = math.degrees(math.acos(float(np.clip(direction[2], -1.0, 1.0))))
        projection = project_canonical_points(volume, image, camera)
        inside = in_frame_mask(projection, camera)
        roof_projection = project_canonical_points(roof, image, camera)
        roof_inside = in_frame_mask(roof_projection, camera)
        valid_roof_uv = roof_projection.uv[
            roof_projection.valid & np.isfinite(roof_projection.uv).all(axis=1)
        ]
        roof_area = (
            float(np.ptp(valid_roof_uv[:, 0]) * np.ptp(valid_roof_uv[:, 1]))
            if len(valid_roof_uv)
            else 0.0
        )
        rows.append(
            {
                "view_name": image.name,
                "nadir_deg": nadir,
                "near_nadir_lt35": nadir < 35.0,
                "moderate_lt70": nadir < 70.0,
                "target_prism_any_corner_in_frame": bool(np.any(inside)),
                "target_prism_coverage": float(np.mean(inside)),
                "roof_vertex_coverage": float(np.mean(roof_inside)),
                "roof_projected_bbox_area_px2": roof_area,
                "roof_projected_bbox_area_fraction": roof_area / (camera.width * camera.height),
            }
        )
    visible = [row for row in rows if row["target_prism_any_corner_in_frame"]]
    summary = {
        "schema": "jointbuildgs.p2.e3_local_4906982.all_camera_pose_audit.v1",
        "all_camera_count": len(rows),
        "target_prism_any_corner_in_frame_count": len(visible),
        "near_nadir_lt35_all_count": sum(row["near_nadir_lt35"] for row in rows),
        "near_nadir_lt35_target_visible_count": sum(row["near_nadir_lt35"] for row in visible),
        "moderate_lt70_target_visible_count": sum(row["moderate_lt70"] for row in visible),
        "near_nadir_full_roof_visible_count": sum(
            row["near_nadir_lt35"] and row["roof_vertex_coverage"] >= 0.999 for row in rows
        ),
        "target_visible_nadir_min_deg": min(row["nadir_deg"] for row in visible),
        "target_visible_nadir_max_deg": max(row["nadir_deg"] for row in visible),
        "rows": rows,
        "scientific_verdict": None,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in summary.items() if key != "rows"}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
