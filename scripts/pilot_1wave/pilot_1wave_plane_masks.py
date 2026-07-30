#!/usr/bin/env python3
"""Preflight or explicitly produce the locked P1W 04a/04b plane masks.

The default ``preflight`` command is offline and read-only.  Model inference or
LoD2 raycasting requires an explicit execution acknowledgement and writes into
an empty output directory through the immutable binary-mask schema.  No command
starts GS learning or edits ``src/stage2/train.py``.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import tempfile
from typing import Any, Mapping

import numpy as np
from PIL import Image as PILImage
import yaml


REPO = Path(__file__).resolve().parents[3]
import sys

if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from src.stage2.colmap_io import (  # noqa: E402
    read_array,
    read_cameras_bin,
    read_images_bin,
)
from src.stage2.pilot_mask_schema import (  # noqa: E402
    BinaryMaskSet,
    MaskPurpose,
    MaskSource,
    canonical_json_bytes,
    sha256_bytes,
    write_binary_mask_set,
)
from src.stage2.pilot_plane_mask_producer import (  # noqa: E402
    CrossViewParameters,
    GroundedSamRoofInference,
    MaskProducerError,
    ViewFrame,
    audit_grounded_sam_runtime,
    cross_view_consistent_masks,
    fetch_asset_bundle,
    fuse_vision_roof_mask,
    inference_attempt_audit,
    load_lod2_citygml_scene,
    load_producer_lock,
    raycast_lod2_roof_bool_mask,
    resize_mvs_depth_to_camera,
    sha256_file,
    validate_04a_04b_control_pair,
    verify_asset_receipt,
)
from src.stage2.pilot_scene_prep import (  # noqa: E402
    HeightEstimate,
    load_selected_footprints,
    rasterize_photo_support_mask,
)


RUN_ID = "20260721_pilot_1wave"
LOCK = REPO / "phases/p2-gsjso/configs/pilot_1wave_mask_producer_lock.json"
REFERENCE_LOCK = REPO / "phases/p2-gsjso/configs/pilot_1wave_reference_lock.json"
DEFAULT_PREP = REPO / "phases/p2-gsjso/runs" / RUN_ID / "prep_artifacts"
DEFAULT_DATA = DEFAULT_PREP / "data"
DEFAULT_PHOTO_MASK = DEFAULT_PREP / "photo_support_masks/mask_manifest.json"
DEFAULT_HEIGHT_AUDIT = DEFAULT_PREP / "sfm_mvs_height_audit.json"
DEFAULT_FOOTPRINTS = REPO / "results/tum_transfer/analysis/footprints_aoi.geojson"
DEFAULT_DATUM = REPO / "configs/input_and_alignment/projection_datum.json"
RECEIPT_SCHEMA = "jointbuildgs.pilot_1wave.mask_producer_asset_receipt.v1"


def require_docker() -> None:
    if not Path("/.dockerenv").exists():
        raise MaskProducerError("P1W plane-mask producer must run in the pinned Docker image")


def rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(REPO.resolve()))
    except ValueError:
        return str(path.resolve())


def atomic_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f".{path.name}.",
        delete=False,
    ) as stream:
        temporary = Path(stream.name)
        json.dump(payload, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)
    os.chmod(path, 0o444)


def load_heights(path: Path) -> tuple[list[str], dict[str, HeightEstimate]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = payload.get("estimates")
    if not isinstance(rows, list) or not rows:
        raise MaskProducerError("SfM/MVS height audit contains no estimates")
    output: dict[str, HeightEstimate] = {}
    order: list[str] = []
    for row in rows:
        estimate = HeightEstimate(
            building_id=str(row["building_id"]),
            local_z_m=float(row["local_z_m"]),
            seed_point_count=int(row["seed_point_count"]),
            upper_quantile=float(row["upper_quantile"]),
            upper_point_count=int(row["upper_point_count"]),
            method=str(row.get("method", "")),
        )
        if estimate.building_id in output:
            raise MaskProducerError(f"duplicate height building: {estimate.building_id}")
        output[estimate.building_id] = estimate
        order.append(estimate.building_id)
    return order, output


def load_common_inventory(
    data_root: Path,
    photo_manifest: Path,
    height_audit: Path,
    footprint_path: Path,
) -> dict[str, Any]:
    photo = BinaryMaskSet(photo_manifest)
    if (
        photo.purpose is not MaskPurpose.PHOTO_SUPPORT
        or photo.source is not MaskSource.LOD2_GROUNDSURFACE_XY_SFM_HEIGHT
    ):
        raise MaskProducerError("common mask is not the locked footprint photo-support set")
    score_ids, heights = load_heights(height_audit)
    footprints = load_selected_footprints(footprint_path, score_ids)
    sparse = data_root / "sparse/0"
    cameras = read_cameras_bin(sparse / "cameras.bin")
    images = read_images_bin(sparse / "images.bin")
    by_name = {image.name: image for image in images.values()}
    if set(by_name) != set(photo.records):
        raise MaskProducerError("COLMAP and common photo-mask view inventories differ")
    for view_id, record in photo.records.items():
        image = by_name[view_id]
        camera = cameras[image.camera_id]
        if record.shape != (camera.height, camera.width):
            raise MaskProducerError(f"{view_id}: common mask and camera shapes differ")
        if not (data_root / "images" / view_id).is_file():
            raise MaskProducerError(f"RGB view is missing: {view_id}")
        depth_path = data_root / "stereo/depth_maps" / f"{view_id}.geometric.bin"
        if not depth_path.is_file():
            raise MaskProducerError(f"geometric MVS depth is missing: {view_id}")
    return {
        "photo": photo,
        "score_ids": score_ids,
        "heights": heights,
        "footprints": footprints,
        "cameras": cameras,
        "images_by_name": by_name,
        "view_ids": sorted(photo.records),
    }


def per_building_projected_footprints(
    common: Mapping[str, Any], view_id: str
) -> list[np.ndarray]:
    image = common["images_by_name"][view_id]
    camera = common["cameras"][image.camera_id]
    masks: list[np.ndarray] = []
    for building_id in common["score_ids"]:
        try:
            mask, _ = rasterize_photo_support_mask(
                camera.width,
                camera.height,
                image,
                camera,
                {building_id: common["footprints"][building_id]},
                {building_id: common["heights"][building_id]},
            )
        except RuntimeError as exc:
            if "empty footprint photo-support mask" not in str(exc):
                raise
            mask = np.zeros((camera.height, camera.width), dtype=bool)
        masks.append(mask)
    return masks


def common_geometry_sha(common: Mapping[str, Any]) -> dict[str, str]:
    return {
        view_id: common["photo"].records[view_id].geometry_sha256
        for view_id in common["view_ids"]
    }


def producer_input_sha(
    data_root: Path,
    photo_manifest: Path,
    height_audit: Path,
    footprint_path: Path,
    *,
    extra_sources: Mapping[str, str] | None = None,
) -> str:
    payload = {
        "photo_mask_manifest": sha256_file(photo_manifest),
        "height_audit": sha256_file(height_audit),
        "footprint_xy": sha256_file(footprint_path),
        "cameras_bin": sha256_file(data_root / "sparse/0/cameras.bin"),
        "images_bin": sha256_file(data_root / "sparse/0/images.bin"),
        "extra_sources": dict(extra_sources or {}),
    }
    return sha256_bytes(canonical_json_bytes(payload))


def build_preflight(args: argparse.Namespace) -> tuple[dict[str, Any], dict[str, Any] | None]:
    lock = load_producer_lock(args.lock)
    if sha256_file(args.datum) != lock["gt_upperbound"]["projection_datum_sha256"]:
        raise MaskProducerError("projection datum SHA differs from producer lock")
    datum = json.loads(args.datum.read_text(encoding="utf-8"))
    if (
        datum.get("geo_crs") != "EPSG:25832"
        or float(datum.get("orthometric_geoid_m", float("nan"))) != 45.7
    ):
        raise MaskProducerError("projection datum CRS/geoid differs from producer lock")
    reference = json.loads(REFERENCE_LOCK.read_text(encoding="utf-8"))
    references_ok = (
        reference.get("code_references", {}).get("groundingdino", {}).get("revision")
        == lock["runtime_assets"]["groundingdino_source"]["revision"]
        and reference.get("code_references", {}).get("segment_anything", {}).get("revision")
        == lock["runtime_assets"]["segment_anything_source"]["revision"]
    )
    if not references_ok:
        raise MaskProducerError("producer source pins differ from the common reference lock")
    common: dict[str, Any] | None = None
    common_error: str | None = None
    try:
        common = load_common_inventory(
            args.data_root,
            args.photo_mask_manifest,
            args.height_audit,
            args.footprints,
        )
    except (FileNotFoundError, MaskProducerError) as exc:
        common_error = str(exc)
    assets: dict[str, Path] | None = None
    asset_error: str | None = None
    if args.asset_root is not None:
        if args.asset_receipt is None:
            args.asset_receipt = args.asset_root / "asset_receipt.json"
        try:
            assets = verify_asset_receipt(
                lock, args.lock, args.asset_root, args.asset_receipt
            )
        except (FileNotFoundError, MaskProducerError) as exc:
            asset_error = str(exc)
    else:
        asset_error = "asset root/receipt not supplied; no download attempted"
    runtime_dependencies = audit_grounded_sam_runtime(lock, assets)
    cross = lock["cross_view_consistency"]
    report = {
        "schema": "jointbuildgs.pilot_1wave.mask_producer_preflight.v1",
        "run_id": RUN_ID,
        "mode": "offline_read_only_preflight",
        "network_accessed": False,
        "model_downloads": 0,
        "inference_runs_started": 0,
        "learning_runs_started": 0,
        "producer_lock": rel(args.lock),
        "producer_lock_sha256": sha256_file(args.lock),
        "reference_lock": rel(REFERENCE_LOCK),
        "reference_lock_sha256": sha256_file(REFERENCE_LOCK),
        "bert_repository": lock["runtime_assets"]["bert_base_uncased"]["repository"],
        "bert_revision": lock["runtime_assets"]["bert_base_uncased"]["revision"],
        "bert_official_config_value_verified": "bert-base-uncased",
        "cross_view_lock": cross,
        "common_inventory_ready": common is not None,
        "common_inventory_error": common_error,
        "common_view_count": 0 if common is None else len(common["view_ids"]),
        "selected_building_count": 0 if common is None else len(common["score_ids"]),
        "assets_ready": assets is not None,
        "asset_error": asset_error,
        "runtime_dependency_gate": runtime_dependencies,
        "ready_for_04a_inference": (
            common is not None and assets is not None and runtime_dependencies["ready"]
        ),
        "ready_for_04b_raycast": common is not None,
        "gt_archive_contract": lock["gt_upperbound"]["archive_contract"],
    }
    runtime = None if common is None else {
        "lock": lock,
        "common": common,
        "assets": assets,
        "04a_runtime_ready": runtime_dependencies["ready"],
    }
    return report, runtime


def _output_root_guard(path: Path) -> None:
    if path.is_symlink():
        raise MaskProducerError("plane-mask output root must not be a symlink")
    if path.exists() and any(path.iterdir()):
        raise MaskProducerError(f"plane-mask output root must be empty: {path}")


def produce_04a(args: argparse.Namespace, runtime: Mapping[str, Any]) -> dict[str, Any]:
    attempt_audit = inference_attempt_audit(args.prior_inference_runs_started)
    if runtime["assets"] is None:
        raise MaskProducerError("04a requires a verified complete asset receipt")
    if not runtime["04a_runtime_ready"]:
        raise MaskProducerError(
            "04a GroundedSAM runtime dependency gate is not ready; rebuild and repin "
            "the Docker/source runtime before inference"
        )
    _output_root_guard(args.output)
    common = runtime["common"]
    lock = runtime["lock"]
    infer = GroundedSamRoofInference(lock, runtime["assets"], device=args.device)
    frames: dict[str, ViewFrame] = {}
    candidates: dict[str, np.ndarray] = {}
    candidate_audit: dict[str, dict[str, Any]] = {}
    per_view_footprints: dict[str, list[np.ndarray]] = {}
    rgb_sha: dict[str, str] = {}
    depth_sha: dict[str, str] = {}
    for view_id in common["view_ids"]:
        image = common["images_by_name"][view_id]
        camera = common["cameras"][image.camera_id]
        rgb_path = args.data_root / "images" / view_id
        depth_path = args.data_root / "stereo/depth_maps" / f"{view_id}.geometric.bin"
        with PILImage.open(rgb_path) as source:
            rgb = np.asarray(source.convert("RGB"), dtype=np.uint8)
        if rgb.shape[:2] != (camera.height, camera.width):
            raise MaskProducerError(f"{view_id}: RGB/camera shape mismatch")
        result = infer(rgb)
        depth = resize_mvs_depth_to_camera(read_array(depth_path), camera)
        frames[view_id] = ViewFrame(view_id, camera, image, depth)
        candidates[view_id] = result.mask
        per_view_footprints[view_id] = per_building_projected_footprints(
            common, view_id
        )
        rgb_sha[view_id] = sha256_file(rgb_path)
        depth_sha[view_id] = sha256_file(depth_path)
        candidate_audit[view_id] = {
            "box_count_after_nms": int(len(result.boxes_xyxy)),
            "candidate_pixels": int(result.mask.sum()),
            "score_min": None if len(result.scores) == 0 else float(result.scores.min()),
            "score_max": None if len(result.scores) == 0 else float(result.scores.max()),
            "phrases": list(result.phrases),
        }
    parameters = CrossViewParameters()
    consistent, cross_audit = cross_view_consistent_masks(
        frames, candidates, parameters
    )
    masks: dict[str, np.ndarray] = {}
    fusion_audit: dict[str, dict[str, Any]] = {}
    for view_id in common["view_ids"]:
        masks[view_id], fusion_audit[view_id] = fuse_vision_roof_mask(
            candidates[view_id],
            consistent[view_id],
            per_view_footprints[view_id],
            footprint_ids=common["score_ids"],
        )
    source_hashes = {
        "producer_lock": sha256_file(args.lock),
        "asset_receipt": sha256_file(args.asset_receipt),
        "rgb_inventory": sha256_bytes(canonical_json_bytes(rgb_sha)),
        "mvs_depth_inventory": sha256_bytes(canonical_json_bytes(depth_sha)),
    }
    input_sha = producer_input_sha(
        args.data_root,
        args.photo_mask_manifest,
        args.height_audit,
        args.footprints,
        extra_sources=source_hashes,
    )
    config_sha = sha256_file(args.lock)
    mask_manifest = write_binary_mask_set(
        args.output,
        masks,
        purpose=MaskPurpose.PLANE_REGION,
        source=MaskSource.VISION_GROUNDEDSAM_ROOF,
        source_disclosure=(
            "GroundingDINO roof prompt plus SAM ViT-H, GT-free MVS-depth/COLMAP "
            "cross-view consistency, and the scoped GroundSurface-XY footprint core"
        ),
        input_sha256=input_sha,
        config_sha256=config_sha,
        geometry_sha256_by_view=common_geometry_sha(common),
    )
    audit_rows = []
    for view_id in common["view_ids"]:
        audit_rows.append(
            {
                "view_id": view_id,
                **candidate_audit[view_id],
                **asdict(cross_audit[view_id]),
                **fusion_audit[view_id],
            }
        )
    one_px_fallback_view_ids = [
        view_id
        for view_id in common["view_ids"]
        if fusion_audit[view_id]["small_core_1px_fallback_count"] > 0
    ]
    zero_px_fallback_view_ids = [
        view_id
        for view_id in common["view_ids"]
        if fusion_audit[view_id]["small_core_0px_fallback_count"] > 0
    ]
    manifest = {
        "schema": "jointbuildgs.pilot_1wave.04a_mask_producer_manifest.v1",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "run_id": RUN_ID,
        "condition": "04a_plane_medium_vision",
        "source": MaskSource.VISION_GROUNDEDSAM_ROOF.value,
        "mask_manifest": "mask_manifest.json",
        "mask_manifest_sha256": sha256_file(mask_manifest),
        "producer_lock_sha256": config_sha,
        "input_sha256": input_sha,
        "view_count": len(masks),
        "selected_building_count": len(common["score_ids"]),
        "cross_view_parameters": asdict(parameters),
        "gt_read_for_selection": False,
        "gt_iou_computed": False,
        "small_core_fallback_order_px": [5, 1, 0],
        "small_core_1px_fallback_view_count": len(one_px_fallback_view_ids),
        "small_core_1px_fallback_view_ids": one_px_fallback_view_ids,
        "small_core_1px_fallback_building_event_count": sum(
            fusion_audit[view_id]["small_core_1px_fallback_count"]
            for view_id in common["view_ids"]
        ),
        "small_core_0px_fallback_view_count": len(zero_px_fallback_view_ids),
        "small_core_0px_fallback_view_ids": zero_px_fallback_view_ids,
        "small_core_0px_fallback_building_event_count": sum(
            fusion_audit[view_id]["small_core_0px_fallback_count"]
            for view_id in common["view_ids"]
        ),
        **attempt_audit,
        "learning_runs_started": 0,
        "audit": audit_rows,
    }
    atomic_json(args.output / "producer_manifest.json", manifest)
    return manifest


def produce_04b(args: argparse.Namespace, runtime: Mapping[str, Any]) -> dict[str, Any]:
    _output_root_guard(args.output)
    common = runtime["common"]
    lock = runtime["lock"]
    datum = json.loads(args.datum.read_text(encoding="utf-8"))
    centres = np.asarray(
        [
            -image.R().T @ image.tvec
            for image in common["images_by_name"].values()
        ],
        dtype=np.float64,
    )
    margin = 250.0
    aoi = [
        float(centres[:, 0].min() - margin),
        float(centres[:, 1].min() - margin),
        float(centres[:, 0].max() + margin),
        float(centres[:, 1].max() + margin),
    ]
    scene = load_lod2_citygml_scene(
        args.gml,
        common["score_ids"],
        world_offset=lock["gt_upperbound"]["world_offset"],
        orthometric_geoid_m=float(datum["orthometric_geoid_m"]),
        aoi_xy_local=aoi,
    )
    masks: dict[str, np.ndarray] = {}
    audit: list[dict[str, Any]] = []
    empty_view_ids: list[str] = []
    total_roof_mask_pixels = 0
    for view_id in common["view_ids"]:
        image = common["images_by_name"][view_id]
        camera = common["cameras"][image.camera_id]
        mask = raycast_lod2_roof_bool_mask(scene, camera, image)
        if not mask.any():
            empty_view_ids.append(view_id)
        masks[view_id] = mask
        roof_mask_pixels = int(mask.sum())
        total_roof_mask_pixels += roof_mask_pixels
        audit.append(
            {
                "view_id": view_id,
                "roof_mask_pixels": roof_mask_pixels,
                "empty_view": roof_mask_pixels == 0,
            }
        )
    if total_roof_mask_pixels <= 0:
        raise MaskProducerError(
            "04b selected-building LoD2 roof raycast is empty over the complete view inventory"
        )
    gml_hashes = {rel(Path(path)): sha256_file(path) for path in sorted(args.gml)}
    input_sha = producer_input_sha(
        args.data_root,
        args.photo_mask_manifest,
        args.height_audit,
        args.footprints,
        extra_sources={
            "producer_lock": sha256_file(args.lock),
            "projection_datum": sha256_file(args.datum),
            "lod2_citygml_inventory": sha256_bytes(canonical_json_bytes(gml_hashes)),
        },
    )
    config_sha = sha256_file(args.lock)
    mask_manifest = write_binary_mask_set(
        args.output,
        masks,
        purpose=MaskPurpose.PLANE_REGION,
        source=MaskSource.LOD2_ROOFSURFACE_GT_UPPERBOUND,
        source_disclosure=(
            "LoD2 CityGML semantic roof-class raycast; GT upper-bound only and "
            "excluded from honest winner selection"
        ),
        input_sha256=input_sha,
        config_sha256=config_sha,
        geometry_sha256_by_view=common_geometry_sha(common),
    )
    manifest = {
        "schema": "jointbuildgs.pilot_1wave.04b_mask_producer_manifest.v1",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "run_id": RUN_ID,
        "condition": "04b_plane_medium_gt_upperbound",
        "source": MaskSource.LOD2_ROOFSURFACE_GT_UPPERBOUND.value,
        "mask_manifest": "mask_manifest.json",
        "mask_manifest_sha256": sha256_file(mask_manifest),
        "producer_lock_sha256": config_sha,
        "input_sha256": input_sha,
        "view_count": len(masks),
        "empty_view_count": len(empty_view_ids),
        "empty_view_ids": empty_view_ids,
        "total_roof_mask_pixels": total_roof_mask_pixels,
        "selected_building_count": len(common["score_ids"]),
        "selected_building_roof_geometry_coverage_count": len(
            scene.selected_building_ids
        ),
        "selected_building_roof_geometry_coverage_complete": (
            len(scene.selected_building_ids) == len(common["score_ids"])
        ),
        "triangle_count_internal_not_archived": int(len(scene.triangles_local)),
        "archive_arrays": ["mask:bool"],
        "forbidden_archive_arrays": [
            "roof_z",
            "hit_depth",
            "face_ids",
            "building_ids",
            "semantic_class",
            "primitive_ids",
        ],
        "inference_runs_started": 1,
        "learning_runs_started": 0,
        "audit": audit,
    }
    atomic_json(args.output / "producer_manifest.json", manifest)
    return manifest


def load_structured(path: Path) -> dict[str, Any]:
    if path.suffix.lower() in {".yaml", ".yml"}:
        value = yaml.safe_load(path.read_text(encoding="utf-8"))
    else:
        value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise MaskProducerError(f"resolved config must be an object: {path}")
    return value


def add_common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--lock", type=Path, default=LOCK)
    parser.add_argument("--data-root", type=Path, default=DEFAULT_DATA)
    parser.add_argument("--photo-mask-manifest", type=Path, default=DEFAULT_PHOTO_MASK)
    parser.add_argument("--height-audit", type=Path, default=DEFAULT_HEIGHT_AUDIT)
    parser.add_argument("--footprints", type=Path, default=DEFAULT_FOOTPRINTS)
    parser.add_argument("--datum", type=Path, default=DEFAULT_DATUM)
    parser.add_argument("--asset-root", type=Path)
    parser.add_argument("--asset-receipt", type=Path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    preflight = sub.add_parser("preflight")
    add_common(preflight)
    preflight.add_argument("--strict-ready-04a", action="store_true")

    fetch = sub.add_parser(
        "fetch-assets",
        help="explicitly fetch pinned source/weight/BERT assets into a new immutable cache",
    )
    fetch.add_argument("--lock", type=Path, default=LOCK)
    fetch.add_argument("--asset-root", type=Path, required=True)
    fetch.add_argument("--execute-fetch", action="store_true")
    fetch.add_argument("--acknowledge-network-and-licenses", action="store_true")

    vision = sub.add_parser("produce-04a")
    add_common(vision)
    vision.add_argument("--output", type=Path, required=True)
    vision.add_argument("--device", default="cuda")
    vision.add_argument(
        "--prior-inference-runs-started",
        type=int,
        required=True,
        help=(
            "explicit count of prior failed 04a inference attempts in this run chain; "
            "use 0 for a first attempt"
        ),
    )
    vision.add_argument("--execute-inference", action="store_true")

    upper = sub.add_parser("produce-04b")
    add_common(upper)
    upper.add_argument("--output", type=Path, required=True)
    upper.add_argument("--gml", type=Path, nargs="+", required=True)
    upper.add_argument("--execute-raycast", action="store_true")

    pair = sub.add_parser("validate-pair")
    pair.add_argument("--config-04a", type=Path, required=True)
    pair.add_argument("--config-04b", type=Path, required=True)
    pair.add_argument("--repository-root", type=Path, default=REPO)
    args = parser.parse_args(argv)
    require_docker()
    if args.command == "fetch-assets":
        if not args.execute_fetch or not args.acknowledge_network_and_licenses:
            parser.error(
                "fetch-assets requires --execute-fetch and "
                "--acknowledge-network-and-licenses"
            )
        result = fetch_asset_bundle(
            load_producer_lock(args.lock),
            args.lock,
            args.asset_root,
            REPO,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
        return 0
    if args.command == "validate-pair":
        result = validate_04a_04b_control_pair(
            load_structured(args.config_04a),
            load_structured(args.config_04b),
            repository_root=args.repository_root,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
        return 0
    report, runtime = build_preflight(args)
    if args.command == "preflight":
        print(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False))
        if args.strict_ready_04a and not report["ready_for_04a_inference"]:
            return 2
        return 0
    if runtime is None:
        raise MaskProducerError(report["common_inventory_error"] or "common inventory unavailable")
    if args.command == "produce-04a":
        if not args.execute_inference:
            parser.error("produce-04a requires --execute-inference")
        result = produce_04a(args, runtime)
    elif args.command == "produce-04b":
        if not args.execute_raycast:
            parser.error("produce-04b requires --execute-raycast")
        result = produce_04b(args, runtime)
    else:  # pragma: no cover
        raise AssertionError(args.command)
    print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
