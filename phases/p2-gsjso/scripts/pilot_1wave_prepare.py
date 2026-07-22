#!/usr/bin/env python3
"""P1W-PREP: preflight or materialize the locked expanded pilot scene.

``preflight`` is read-only and is the only mode intended for the implementation
gate.  ``materialize --execute`` is an explicit later operation: it crops the
common dense seed, RGB views, sparse SfM, geometric/photometric MVS depth and
normal maps, and the common footprint photo-support masks.  It does not start
training or inference and never creates a semantic directory.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import shutil
import sys
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np


REPO = Path(__file__).resolve().parents[3]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from src.stage2.colmap_io import read_cameras_bin, read_images_bin  # noqa: E402
from src.stage2.pilot_mask_schema import (  # noqa: E402
    MaskPurpose,
    MaskSource,
    canonical_json_bytes,
    sha256_bytes,
    sha256_file,
    write_binary_mask_set,
)
from src.stage2.pilot_scene_prep import (  # noqa: E402
    CRS,
    MASK_HEIGHT_QUANTILE,
    MIN_HEIGHT_POINTS,
    VIEW_PAD_PX,
    WORLD_SHIFT,
    clip_local_xyz_to_utm_bbox,
    derive_sfm_mvs_footprint_heights,
    infer_local_z_range,
    load_selected_footprints,
    materialize_scene_crop,
    plan_view_crops,
    preflight_view_sources,
    rasterize_photo_support_mask,
    read_ply_xyz,
    write_ply_xyz,
)


RUN_ID = "20260721_pilot_1wave"
TASK_ID = "P1W-PREP"
PILOT_COMMIT = "6502fa9"
EXPECTED_SELECTION_SHA256 = (
    "e98daa670a0753198e8a54502b260a07bcefe2bca42976931c0a08b766c5b3cd"
)
RUN_ROOT = REPO / "phases/p2-gsjso/runs" / RUN_ID
PILOT_MANIFEST = RUN_ROOT / "pilot_1wave_pilot_set_manifest.json"
PILOT_CSV = RUN_ROOT / "pilot_1wave_pilot_set.csv"
DEDICATED_OUTPUT = RUN_ROOT / "prep_artifacts"
MARKER_NAME = ".pilot_1wave_prep_root.json"
MARKER_SCHEMA = "jointbuildgs.pilot_1wave.prep_root.v1"

SOURCE_DATA = REPO / "results/tum_transfer/data_geoidfix"
SOURCE_SPARSE = SOURCE_DATA / "sparse/0"
SOURCE_SEED = REPO / "results/tum_transfer/mob_analysis/seed/seed_dense.ply"
SOURCE_FOOTPRINTS = REPO / "results/tum_transfer/analysis/footprints_aoi.geojson"

MASK_CONFIG = {
    "schema": "jointbuildgs.pilot_1wave.photo_support_config.v1",
    "purpose": "photo_support",
    "source": "lod2_groundsurface_xy_sfm_height",
    "footprint_xy": "selected 30 LoD2 GroundSurface XY under approved scoped exception",
    "height_source": "dense MVS seed points only",
    "height_estimator": "median z at/above per-building q80",
    "height_upper_quantile": MASK_HEIGHT_QUANTILE,
    "height_min_points": MIN_HEIGHT_POINTS,
    "projection": "COLMAP pinhole-equivalent K, same convention as historical E5 prep",
    "binary_mask": "union of selected footprint projections; no dilation",
    "empty_mask": "hard_fail",
}


def require_docker() -> None:
    if not Path("/.dockerenv").exists():
        raise RuntimeError("P1W-PREP must run inside the pinned Docker image")


def rel(path: Path) -> str:
    return str(path.resolve().relative_to(REPO.resolve()))


def load_locked_contract() -> dict[str, Any]:
    payload = json.loads(PILOT_MANIFEST.read_text(encoding="utf-8"))
    selection = payload.get("selection", {})
    if selection.get("selection_sha256") != EXPECTED_SELECTION_SHA256:
        raise RuntimeError("pilot selection SHA does not match commit 6502fa9")
    ids = selection.get("selected_ids_in_rank_order")
    bbox = selection.get("training_crop_bbox")
    if not isinstance(ids, list) or len(ids) != 30 or len(set(ids)) != 30:
        raise RuntimeError("pilot manifest must lock exactly 30 unique score IDs")
    if not isinstance(bbox, list) or len(bbox) != 4:
        raise RuntimeError("pilot manifest has no locked training crop bbox")
    expected_csv_sha = payload.get("outputs", {}).get(
        "pilot_1wave_pilot_set.csv", {}
    ).get("sha256")
    if sha256_file(PILOT_CSV) != expected_csv_sha:
        raise RuntimeError("pilot-set CSV SHA mismatch")
    with PILOT_CSV.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    csv_ids = [row["building_id"] for row in rows]
    if csv_ids != ids:
        raise RuntimeError("pilot manifest and CSV score ID order differ")
    expected_footprint_sha = payload.get("source_sha256", {}).get(
        rel(SOURCE_FOOTPRINTS)
    )
    if sha256_file(SOURCE_FOOTPRINTS) != expected_footprint_sha:
        raise RuntimeError("approved footprint XY source SHA mismatch")
    return {
        "payload": payload,
        "score_ids": ids,
        "training_bbox_utm": [float(value) for value in bbox],
        "selection_sha256": selection["selection_sha256"],
        "pilot_manifest_sha256": sha256_file(PILOT_MANIFEST),
        "pilot_csv_sha256": sha256_file(PILOT_CSV),
        "footprint_sha256": expected_footprint_sha,
    }


def build_preflight() -> tuple[dict[str, Any], dict[str, Any]]:
    contract = load_locked_contract()
    footprints = load_selected_footprints(SOURCE_FOOTPRINTS, contract["score_ids"])
    source_seed_xyz = read_ply_xyz(SOURCE_SEED)
    clipped_seed_xyz = clip_local_xyz_to_utm_bbox(
        source_seed_xyz, contract["training_bbox_utm"]
    )
    if len(clipped_seed_xyz) == 0:
        raise RuntimeError("expanded training crop produced an empty dense seed")
    z_range = infer_local_z_range(clipped_seed_xyz)
    heights = derive_sfm_mvs_footprint_heights(footprints, clipped_seed_xyz)
    cameras = read_cameras_bin(SOURCE_SPARSE / "cameras.bin")
    images = read_images_bin(SOURCE_SPARSE / "images.bin")
    plans = plan_view_crops(
        cameras,
        images,
        footprints,
        heights,
        contract["training_bbox_utm"],
        z_range,
    )
    source_inventory = preflight_view_sources(SOURCE_DATA, plans)
    source_sha256 = {
        rel(PILOT_MANIFEST): contract["pilot_manifest_sha256"],
        rel(PILOT_CSV): contract["pilot_csv_sha256"],
        rel(SOURCE_FOOTPRINTS): contract["footprint_sha256"],
        rel(SOURCE_SEED): sha256_file(SOURCE_SEED),
        rel(SOURCE_SPARSE / "cameras.bin"): sha256_file(
            SOURCE_SPARSE / "cameras.bin"
        ),
        rel(SOURCE_SPARSE / "images.bin"): sha256_file(
            SOURCE_SPARSE / "images.bin"
        ),
        rel(SOURCE_SPARSE / "points3D.bin"): sha256_file(
            SOURCE_SPARSE / "points3D.bin"
        ),
    }
    report = {
        "schema": "jointbuildgs.pilot_1wave.preflight.v1",
        "run_id": RUN_ID,
        "task_id": TASK_ID,
        "mode": "read_only_preflight",
        "docker_required": True,
        "pilot_commit": PILOT_COMMIT,
        "selection_sha256": contract["selection_sha256"],
        "score_building_count": len(contract["score_ids"]),
        "score_building_ids_rank_order": contract["score_ids"],
        "training_crop_bbox_utm": contract["training_bbox_utm"],
        "crs": CRS,
        "world_shift": WORLD_SHIFT.tolist(),
        "source_dense_seed_points": int(len(source_seed_xyz)),
        "clipped_dense_seed_points": int(len(clipped_seed_xyz)),
        "local_z_range_m": list(z_range),
        "height_source": "dense MVS seed only; no LoD2 Z",
        "height_building_count": len(heights),
        "height_seed_point_count_min": min(
            estimate.seed_point_count for estimate in heights.values()
        ),
        "height_seed_point_count_max": max(
            estimate.seed_point_count for estimate in heights.values()
        ),
        "view_source_inventory": source_inventory,
        "source_sha256": source_sha256,
        "view_crop_width_median_px": float(np.median([plan.width for plan in plans])),
        "view_crop_height_median_px": float(np.median([plan.height for plan in plans])),
        "view_visible_buildings_min": min(
            plan.visible_building_count for plan in plans
        ),
        "view_visible_buildings_max": max(
            plan.visible_building_count for plan in plans
        ),
        "footprint_source_disclosure": (
            "LoD2 GroundSurface XY is GT-derived and is used only under the approved "
            "(iii) first-wave scoped exception; it is not reclassified as non-GT"
        ),
        "forbidden_inputs_read": [],
        "semantic_source_read": False,
        "lod2_z_read": False,
        "roofsurface_read": False,
        "learning_runs_started": 0,
        "new_inference_runs": 0,
        "materialized": False,
        "dedicated_output_if_later_executed": rel(DEDICATED_OUTPUT),
    }
    runtime = {
        "contract": contract,
        "footprints": footprints,
        "source_seed_xyz": source_seed_xyz,
        "clipped_seed_xyz": clipped_seed_xyz,
        "z_range": z_range,
        "heights": heights,
        "cameras": cameras,
        "images": images,
        "plans": plans,
        "source_sha256": source_sha256,
    }
    return report, runtime


def validate_dedicated_output(path: Path) -> None:
    if path.is_symlink():
        raise RuntimeError("dedicated prep output must not be a symlink")
    if path.resolve(strict=False) != DEDICATED_OUTPUT.resolve(strict=False):
        raise RuntimeError("refusing output outside the single dedicated prep root")


def validate_existing_marker(path: Path) -> None:
    marker = path / MARKER_NAME
    if not marker.is_file() or marker.is_symlink():
        raise RuntimeError("refusing replacement: dedicated output marker is absent")
    payload = json.loads(marker.read_text(encoding="utf-8"))
    if payload != {
        "schema": MARKER_SCHEMA,
        "run_id": RUN_ID,
        "dedicated_output": rel(DEDICATED_OUTPUT),
    }:
        raise RuntimeError("refusing replacement: dedicated output marker mismatch")


def write_marker(path: Path) -> None:
    payload = {
        "schema": MARKER_SCHEMA,
        "run_id": RUN_ID,
        "dedicated_output": rel(DEDICATED_OUTPUT),
    }
    (path / MARKER_NAME).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def publish_staged_output(staging: Path, *, replace: bool) -> None:
    """Publish a complete staging tree, retaining the old tree until success."""

    if not DEDICATED_OUTPUT.exists():
        os.replace(staging, DEDICATED_OUTPUT)
        return
    if not replace:
        raise RuntimeError("replacement was not authorized")
    validate_existing_marker(DEDICATED_OUTPUT)
    backup = RUN_ROOT / f".prep_artifacts.replaced.{os.getpid()}"
    if backup.exists():
        raise RuntimeError(f"replacement backup path already exists: {backup}")
    os.replace(DEDICATED_OUTPUT, backup)
    try:
        os.replace(staging, DEDICATED_OUTPUT)
    except Exception:
        os.replace(backup, DEDICATED_OUTPUT)
        raise
    validate_existing_marker(backup)
    shutil.rmtree(backup)


def materialize(report: dict[str, Any], runtime: dict[str, Any], replace: bool) -> dict[str, Any]:
    validate_dedicated_output(DEDICATED_OUTPUT)
    if DEDICATED_OUTPUT.exists():
        if not replace:
            raise RuntimeError(
                f"dedicated prep output already exists; pass --replace only after review: "
                f"{rel(DEDICATED_OUTPUT)}"
            )
        validate_existing_marker(DEDICATED_OUTPUT)

    staging = RUN_ROOT / f".prep_artifacts.staging.{os.getpid()}"
    if staging.exists():
        raise RuntimeError(f"staging path already exists: {staging}")
    staging.mkdir(parents=False)
    write_marker(staging)
    try:
        clipped_seed_path = staging / "seeds/seed_dense_expanded_pilot.ply"
        write_ply_xyz(clipped_seed_path, runtime["clipped_seed_xyz"])
        data_root = staging / "data"
        data_stats = materialize_scene_crop(
            SOURCE_DATA,
            SOURCE_SPARSE,
            data_root,
            runtime["plans"],
            runtime["contract"]["training_bbox_utm"],
        )

        height_rows = [asdict(runtime["heights"][building_id]) for building_id in runtime["contract"]["score_ids"]]
        height_audit_path = staging / "sfm_mvs_height_audit.json"
        height_audit_path.write_text(
            json.dumps(
                {
                    "schema": "jointbuildgs.pilot_1wave.sfm_mvs_height_audit.v1",
                    "source": rel(SOURCE_SEED),
                    "source_sha256": sha256_file(SOURCE_SEED),
                    "forbidden_lod2_z_read": False,
                    "estimates": height_rows,
                },
                ensure_ascii=False,
                indent=2,
                allow_nan=False,
            )
            + "\n",
            encoding="utf-8",
        )

        output_cameras = read_cameras_bin(data_root / "sparse/0/cameras.bin")
        output_images = read_images_bin(data_root / "sparse/0/images.bin")
        masks: dict[str, np.ndarray] = {}
        geometry_sha_by_view: dict[str, str] = {}
        mask_audit: list[dict[str, Any]] = []
        height_payload = {
            building_id: asdict(runtime["heights"][building_id])
            for building_id in runtime["contract"]["score_ids"]
        }
        for plan in runtime["plans"]:
            image = output_images[plan.image_id]
            camera = output_cameras[image.camera_id]
            mask, audit = rasterize_photo_support_mask(
                camera.width,
                camera.height,
                image,
                camera,
                runtime["footprints"],
                runtime["heights"],
            )
            masks[plan.name] = mask
            geometry_payload = {
                "schema": "jointbuildgs.pilot_1wave.projected_geometry.v1",
                "view_id": plan.name,
                "image_id": plan.image_id,
                "camera_model": camera.model,
                "camera_width": camera.width,
                "camera_height": camera.height,
                "camera_params": camera.params.tolist(),
                "qvec": image.qvec.tolist(),
                "tvec": image.tvec.tolist(),
                "crop": list(plan.crop),
                "footprint_source_sha256": runtime["contract"]["footprint_sha256"],
                "height_estimates": height_payload,
            }
            geometry_sha_by_view[plan.name] = sha256_bytes(
                canonical_json_bytes(geometry_payload)
            )
            mask_audit.append({"view_id": plan.name, **audit})

        source_hashes = {
            "pilot_manifest": runtime["source_sha256"][rel(PILOT_MANIFEST)],
            "pilot_csv": runtime["source_sha256"][rel(PILOT_CSV)],
            "footprint_xy": runtime["source_sha256"][rel(SOURCE_FOOTPRINTS)],
            "dense_seed": runtime["source_sha256"][rel(SOURCE_SEED)],
            "cameras_bin": runtime["source_sha256"][
                rel(SOURCE_SPARSE / "cameras.bin")
            ],
            "images_bin": runtime["source_sha256"][
                rel(SOURCE_SPARSE / "images.bin")
            ],
        }
        mask_input_sha = sha256_bytes(canonical_json_bytes(source_hashes))
        mask_config_sha = sha256_bytes(canonical_json_bytes(MASK_CONFIG))
        mask_manifest = write_binary_mask_set(
            staging / "photo_support_masks",
            masks,
            purpose=MaskPurpose.PHOTO_SUPPORT,
            source=MaskSource.LOD2_GROUNDSURFACE_XY_SFM_HEIGHT,
            source_disclosure=(
                "LoD2 GroundSurface XY is GT-derived under the approved scoped "
                "exception; projection height is derived only from the dense MVS seed"
            ),
            input_sha256=mask_input_sha,
            config_sha256=mask_config_sha,
            geometry_sha256_by_view=geometry_sha_by_view,
        )
        (staging / "photo_support_mask_audit.json").write_text(
            json.dumps(mask_audit, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
            encoding="utf-8",
        )
        manifest = {
            **report,
            "schema": "jointbuildgs.pilot_1wave.prep_manifest.v1",
            "mode": "materialized_without_training_or_inference",
            "created_utc": datetime.now(timezone.utc).isoformat(),
            "materialized": True,
            "data_stats": data_stats,
            "dense_seed_output": rel(clipped_seed_path).replace(
                rel(staging), rel(DEDICATED_OUTPUT), 1
            ),
            "dense_seed_output_sha256": sha256_file(clipped_seed_path),
            "height_audit": "sfm_mvs_height_audit.json",
            "height_audit_sha256": sha256_file(height_audit_path),
            "photo_support_mask_manifest": "photo_support_masks/mask_manifest.json",
            "photo_support_mask_manifest_sha256": sha256_file(mask_manifest),
            "photo_support_mask_config": MASK_CONFIG,
            "photo_support_mask_input_sha256": mask_input_sha,
            "photo_support_mask_config_sha256": mask_config_sha,
            "semantic_directory_created": False,
            "learning_runs_started": 0,
            "new_inference_runs": 0,
        }
        (staging / "prep_manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
            encoding="utf-8",
        )
        publish_staged_output(staging, replace=replace)
        return manifest
    except Exception:
        if staging.exists():
            validate_existing_marker(staging)
            shutil.rmtree(staging)
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("preflight", "materialize"))
    parser.add_argument(
        "--execute",
        action="store_true",
        help="required with materialize; never implied by preflight",
    )
    parser.add_argument(
        "--replace",
        action="store_true",
        help="replace only the marker-validated dedicated prep root",
    )
    args = parser.parse_args()
    require_docker()
    if args.mode == "preflight":
        if args.execute or args.replace:
            parser.error("preflight does not accept --execute/--replace")
        report, _ = build_preflight()
        print(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False))
        return
    if not args.execute:
        parser.error("materialize requires explicit --execute")
    report, runtime = build_preflight()
    result = materialize(report, runtime, replace=args.replace)
    print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
