#!/usr/bin/env python3
"""Publish the 4907182 A-prime r1 panel-v6 roof-boundary backfill.

The first row is rebuilt from the actual ALS class-6 supervision support:
the incidence-one 3D boundary segments of the unfiltered-point TIN and the
recorded k>=3 seed subset.  Both are projected by the shared datum-explicit
COLMAP API.  The historical flat-height footprint locator is never called.
M_j, reference GML, and output CityJSON do not participate in first-row view
selection, eligibility, or crop bounds.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np
from PIL import Image


REPO = Path(__file__).resolve().parents[4]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from src.artifact_paths import receipt_compatible_path  # noqa: E402
from src.stage2 import image_projection  # noqa: E402
from src.stage2.colmap_io import read_cameras_bin, read_images_bin  # noqa: E402


V4_RENDERER = REPO / "phases/p2-gsjso/scripts/fusion_w1/fusion_w1_aprime_job_panel_v4_20260727.py"
ROOF_BOUNDARY_MODULE = REPO / "phases/p2-gsjso/scripts/fusion_w1/roof_boundary_overlay.py"
DEFAULT_CONFIG = (
    REPO
    / "phases/p2-gsjso/configs/fusion_w1/fusion_w1_aprime_job_panel_v6_roof_boundary_20260728.json"
)
CONFIG_SCHEMA = "jointbuildgs.fusion_w1_aprime.job_panel_roof_boundary.config.v6"
RECEIPT_SCHEMA = "jointbuildgs.fusion_w1_aprime.job_panel_roof_boundary.complete.v6"


def load_module(path: Path, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot import {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


v4 = load_module(V4_RENDERER, "fusion_w1_aprime_job_panel_v4_for_v6_roof_boundary")
roof_boundary_overlay = load_module(
    ROOF_BOUNDARY_MODULE, "roof_boundary_overlay_for_v6_roof_boundary"
)
base = v4.base
PanelError = v4.PanelError


def require(condition: bool, message: str) -> None:
    if not condition:
        raise PanelError(message)


def allowed_identity(config: Mapping[str, Any]) -> tuple[str, str, str]:
    records = config["backfill_contract"]["allowed_identities"]
    require(isinstance(records, list) and len(records) == 1, "v6 must allow exactly one identity")
    record = records[0]
    return str(record["building_id"]), str(record["arm"]), str(record["replicate"])


def validate_identity(
    config: Mapping[str, Any],
    base_config: Mapping[str, Any],
    building_id: str,
    arm: str,
    replicate: str,
) -> None:
    base.validate_identity(base_config, building_id, arm, replicate)
    require(
        (building_id, arm, replicate) == allowed_identity(config),
        "identity is outside the locked 4907182 A-prime r1 panel-v6 scope",
    )


def implementation_records(config: Mapping[str, Any]) -> list[dict[str, Any]]:
    return [base.file_record(base.repo_path(path)) for path in config["implementation_files"]]


def historical_bundle_snapshot(config: Mapping[str, Any]) -> dict[str, Any]:
    snapshot: dict[str, Any] = {}
    for version, contract in config["historical_bundles"].items():
        root = base.repo_path(contract["root"])
        records: dict[str, Any] = {}
        for filename, expected_sha256 in contract["records"].items():
            record = base.file_record(root / filename)
            require(
                record["sha256"] == expected_sha256,
                f"historical {version} bundle drift: {filename}",
            )
            records[filename] = record
        snapshot[version] = {"status": contract["status"], "records": records}
    return snapshot


def load_config(path: Path = DEFAULT_CONFIG) -> tuple[dict[str, Any], dict[str, Any]]:
    config = base.load_json(path)
    require(config.get("schema") == CONFIG_SCHEMA, "panel v6 config schema drift")
    require(config.get("run_id") == "20260726_fusion_w1_aprime", "run ID drift")
    require(config.get("branch") == "exp/fusion-w1", "branch drift")
    require(
        allowed_identity(config) == ("DEBY_LOD2_4907182", "Aprime", "r1"),
        "v6 exact identity lock drift",
    )
    expected_implementation = [
        "phases/p2-gsjso/configs/fusion_w1/fusion_w1_aprime_job_panel_v6_roof_boundary_20260728.json",
        "phases/p2-gsjso/scripts/fusion_w1/fusion_w1_aprime_job_panel_v6_roof_boundary_20260728.py",
        "phases/p2-gsjso/scripts/fusion_w1/run_fusion_w1_aprime_job_panel_v6_roof_boundary_20260728.sh",
        "tests/fusion_w1/test_fusion_w1_aprime_job_panel_v6_roof_boundary_20260728.py",
        "phases/p2-gsjso/scripts/fusion_w1/fusion_w1_aprime_job_panel_v4_20260727.py",
        "phases/p2-gsjso/configs/fusion_w1/fusion_w1_aprime_job_qualitative_v3_20260727.json",
        "phases/p2-gsjso/scripts/fusion_w1/fusion_w1_aprime_job_qualitative_v3_20260727.py",
        "phases/p2-gsjso/scripts/fusion_w1/roof_boundary_overlay.py",
        "src/artifact_paths.py",
        "src/stage2/image_projection.py",
        "src/geospatial/projection_datum.py",
        "src/stage2/colmap_io.py",
    ]
    require(config.get("implementation_files") == expected_implementation, "v6 dependency closure drift")
    for value in expected_implementation:
        require(not Path(value).is_absolute(), "implementation path must be relative")
        require(base.repo_path(value).is_file(), f"implementation absent: {value}")

    base_contract = config["base_contract"]
    require(base_contract.get("layout_reuse_only") is True, "v4 layout-only disclosure drift")
    require(base_contract.get("v4_v5_projection_helpers_used") is False, "stale projection helper enabled")
    resolver = config["resolver_disclosure"]
    require(
        resolver.get("inherited_base_resolver_reads_M_j_before_v6_geometry_selection") is True,
        "inherited M_j read disclosure drift",
    )
    require(
        resolver.get("inherited_base_resolver_reads_reference_GML_before_v6_geometry_selection") is True,
        "inherited reference read disclosure drift",
    )
    require(
        resolver.get("inherited_values_used_for_v6_view_ranking_eligibility_or_crop") is False,
        "inherited alignment input leakage",
    )

    contract = config["backfill_contract"]
    for key in (
        "training_reused_unchanged",
        "readout_reused_unchanged",
        "assembly_reused_unchanged",
        "score_reused_unchanged",
    ):
        require(contract.get(key) is True, f"v6 reuse disclosure drift: {key}")
    require(contract.get("scientific_verdict") is None, "scientific verdict must be null")
    require(contract.get("interpretation") is None, "interpretation must be null")

    geometry = config["first_row_geometry_contract"]
    coordinate = geometry["coordinate_contract"]
    require(
        geometry.get("unfiltered_xyz_key") == "xyz_unfiltered_base_epsg25832_orthometric",
        "unfiltered ALS XYZ key drift",
    )
    require(geometry.get("filtered_seed_keep_key") == "keep_k3", "filtered seed key drift")
    require(
        coordinate.get("input_vertical_datum") == image_projection.ORTHOMETRIC,
        "projection input datum drift",
    )
    require(float(coordinate.get("orthometric_to_ellipsoidal_geoid_m")) == 45.7, "geoid drift")
    require(
        coordinate.get("projection_engine")
        == "src.stage2.image_projection.project_base_points",
        "shared projection engine drift",
    )
    require(
        int(coordinate.get("additional_transform_application_count", -1)) == 0,
        "additional pose transform must stay zero",
    )
    for path_key, hash_key in (
        ("projection_config", "projection_config_sha256"),
        ("scene_reference_frame", "scene_reference_sha256"),
    ):
        source = base.repo_path(coordinate[path_key])
        require(source.is_file(), f"coordinate source absent: {coordinate[path_key]}")
        require(v4.sha256_file(source) == coordinate[hash_key], f"coordinate source hash drift: {path_key}")
    votes = base.repo_path(geometry["visibility_npz"])
    require(votes.is_file(), "visibility votes NPZ absent")
    require(v4.sha256_file(votes) == geometry["visibility_npz_sha256"], "visibility votes hash drift")

    selection = geometry["view_selection"]
    for key in (
        "image_pixels_used_for_ranking",
        "M_j_used_for_ranking_or_eligibility",
        "reference_GML_used_for_ranking_or_eligibility",
        "output_CityJSON_used_for_ranking_or_eligibility",
    ):
        require(selection.get(key) is False, f"geometry-only selection leakage: {key}")
    require(
        selection.get("require_all_boundary_endpoints_valid_and_in_frame") is True,
        "boundary in-frame fail-closed contract absent",
    )
    require(
        selection.get("require_all_filtered_seed_points_valid_and_in_frame") is True,
        "seed in-frame fail-closed contract absent",
    )
    independence = geometry["alignment_independence"]
    require(all(value is False for value in independence.values()), "alignment independence drift")

    visual = config["visual_contract"]
    require((visual.get("rows"), visual.get("columns")) == (5, 5), "panel grid drift")
    require(visual.get("single_visual_file") is True, "single visual contract drift")
    require(visual.get("placeholders_allowed_for_measured") is False, "placeholder policy drift")
    require(float(visual["camera_contract"].get("z_exaggeration", 0.0)) == 1.0, "Z exaggeration drift")
    require(
        config["outputs"].get("root")
        == "phases/p2-gsjso/runs/fusion_w1/20260726_fusion_w1_aprime/review_v6_roof_boundary",
        "review v6 root drift",
    )
    require(set(config["outputs"]) == {"root", "panel", "complete"}, "v6 output set drift")
    publication = config["publication"]
    require(publication.get("overwrite_allowed") is False, "overwrite policy drift")
    require(
        publication.get("historical_v4_v5_overwrite_or_delete_forbidden") is True,
        "historical bundle protection absent",
    )
    execution = config["execution"]
    require(execution.get("network") == "none", "network contract drift")
    require(execution.get("gpus_required") is False, "v6 panel must be CPU-only")
    require(execution.get("gpu_devices_used") == [], "v6 panel must not bind GPU devices")
    require(execution.get("nonroot") is True, "v6 panel must be nonroot")
    require(execution.get("unrelated_queue_allowed") is True, "unrelated queue concurrency drift")
    require(
        execution.get("target_source_hashes_verified_before_and_after_render") is True,
        "target source pre/post hash contract absent",
    )
    require(
        execution.get("output_namespace_isolated_from_training") is True,
        "isolated output namespace contract absent",
    )
    historical_bundle_snapshot(config)

    base_config = base.load_config(base.repo_path(base_contract["config"]))
    validate_identity(config, base_config, *allowed_identity(config))
    return config, base_config


def output_job_dir(
    config: Mapping[str, Any],
    building_id: str,
    arm: str,
    replicate: str,
    output_root: Path | None = None,
) -> Path:
    root = base.repo_path(config["outputs"]["root"]) if output_root is None else output_root.resolve()
    return root / "by_building" / building_id / f"arm_{arm}" / replicate


def _nan_separated_segments(segments_uv: np.ndarray) -> np.ndarray:
    segments = np.asarray(segments_uv, dtype=np.float64)
    require(segments.ndim == 3 and segments.shape[1:] == (2, 2) and len(segments), "boundary UV malformed")
    output = np.full((len(segments) * 3, 2), np.nan, dtype=np.float64)
    output[0::3] = segments[:, 0]
    output[1::3] = segments[:, 1]
    return output


def _bbox_area(points_uv: np.ndarray) -> float:
    values = np.asarray(points_uv, dtype=np.float64).reshape(-1, 2)
    require(len(values) and np.isfinite(values).all(), "projected geometry contains nonfinite pixels")
    span = values.max(axis=0) - values.min(axis=0)
    return float(span[0] * span[1])


def _project_geometry(
    points_base: np.ndarray,
    pose: Any,
    camera: Any,
    scene_reference: Mapping[str, Any],
    coordinate: Mapping[str, Any],
) -> image_projection.ProjectionResult:
    return image_projection.project_base_points(
        points_base,
        pose,
        camera,
        scene_reference,
        input_datum=str(coordinate["input_vertical_datum"]),
        geoid_m=float(coordinate["orthometric_to_ellipsoidal_geoid_m"]),
        config_path=base.repo_path(coordinate["projection_config"]),
        min_depth_m=1.0,
    )


def projected_input_view(evidence: Mapping[str, Any], config: Mapping[str, Any]) -> dict[str, Any]:
    preprocess_path = base.repo_path(evidence["source_records"]["preprocess_manifest"]["path"])
    preprocess_root = preprocess_path.parent
    preprocess = base.load_json(preprocess_path)
    geometry = config["first_row_geometry_contract"]
    coordinate = geometry["coordinate_contract"]

    require(
        int(preprocess.get("pose_binding", {}).get("additional_transform_application_count", -1)) == 0,
        "preprocess pose has an additional transform application",
    )
    require(
        preprocess.get("pose_binding", {}).get("corrected_images_sha256")
        == coordinate["adopted_corrected_images_sha256"],
        "adopted corrected-pose hash drift",
    )
    source_hashes = preprocess.get("source_inputs", {}).get("sha256", {})
    base.verify_projection_config_migration(
        source_hashes, coordinate["projection_config_migration"]
    )
    require(
        source_hashes.get(coordinate["scene_reference_frame"])
        == coordinate["scene_reference_sha256"],
        f"preprocess did not bind coordinate source: {coordinate['scene_reference_frame']}",
    )

    votes_contract = preprocess.get("seed", {}).get("visibility", {}).get("votes_npz", {})
    require(
        receipt_compatible_path(str(votes_contract.get("path", "")))
        == receipt_compatible_path(str(geometry["visibility_npz"])),
        "manifest visibility NPZ path drift",
    )
    require(
        votes_contract.get("sha256") == geometry["visibility_npz_sha256"],
        "manifest visibility NPZ hash drift",
    )
    votes_path = base.repo_path(geometry["visibility_npz"])
    votes_record = base.file_record(votes_path)
    require(votes_record["sha256"] == geometry["visibility_npz_sha256"], "visibility NPZ changed")
    with np.load(votes_path, allow_pickle=False) as archive:
        require(geometry["unfiltered_xyz_key"] in archive.files, "unfiltered ALS XYZ absent")
        require(geometry["filtered_seed_keep_key"] in archive.files, "recorded keep_k3 absent")
        unfiltered_base = np.asarray(archive[geometry["unfiltered_xyz_key"]], dtype=np.float64)
        keep_k3 = np.asarray(archive[geometry["filtered_seed_keep_key"]], dtype=bool)
    require(
        unfiltered_base.ndim == 2 and unfiltered_base.shape[1] == 3 and len(unfiltered_base) >= 3,
        "unfiltered ALS class-6 XYZ malformed",
    )
    require(np.isfinite(unfiltered_base).all(), "unfiltered ALS class-6 XYZ is nonfinite")
    require(keep_k3.shape == (len(unfiltered_base),), "keep_k3 shape drift")
    filtered_seed_base = unfiltered_base[keep_k3]
    seed_manifest = preprocess["seed"]
    require(len(unfiltered_base) == int(seed_manifest["source_unfiltered_points_n"]), "unfiltered count drift")
    require(len(filtered_seed_base) == int(seed_manifest["filtered_points_n"]), "filtered seed count drift")

    scene_path = base.repo_path(coordinate["scene_reference_frame"])
    scene_record = base.file_record(scene_path)
    require(scene_record["sha256"] == coordinate["scene_reference_sha256"], "scene reference drift")
    scene_reference = base.load_json(scene_path)
    projection_config_record = base.file_record(base.repo_path(coordinate["projection_config"]))
    require(
        projection_config_record["sha256"] == coordinate["projection_config_sha256"],
        "projection config drift",
    )

    seed_path = base.repo_path(evidence["source_records"]["pretraining_seed"]["path"])
    seed_record = base.file_record(seed_path)
    with np.load(seed_path, allow_pickle=False) as archive:
        require("xyz" in archive.files, "canonical filtered ALS seed coordinates absent")
        seed_canonical = np.asarray(archive["xyz"], dtype=np.float64)
    canonical_from_votes = image_projection.base_to_canonical(
        filtered_seed_base,
        scene_reference,
        input_datum=str(coordinate["input_vertical_datum"]),
        geoid_m=float(coordinate["orthometric_to_ellipsoidal_geoid_m"]),
        config_path=base.repo_path(coordinate["projection_config"]),
    )
    require(seed_canonical.shape == canonical_from_votes.shape, "filtered seed canonical shape drift")
    maximum_seed_delta = float(np.max(np.abs(seed_canonical - canonical_from_votes)))
    require(maximum_seed_delta <= 1.0e-9, "keep_k3 seed coordinates differ from frozen pretraining seed")

    manifest_tin = preprocess.get("supervision", {}).get("class6_tin", {})
    filter_contract = geometry["tin_filters_from_preprocess_manifest"]
    for key in ("maximum_xy_edge_m", "maximum_slope_deg", "minimum_xy_triangle_area_m2"):
        require(float(manifest_tin.get(key)) == float(filter_contract[key]), f"TIN filter drift: {key}")
    boundary = roof_boundary_overlay.build_roof_boundary(
        unfiltered_base,
        maximum_xy_edge_m=float(filter_contract["maximum_xy_edge_m"]),
        maximum_slope_deg=float(filter_contract["maximum_slope_deg"]),
        minimum_xy_triangle_area_m2=float(filter_contract["minimum_xy_triangle_area_m2"]),
    )
    boundary_segments_base = np.asarray(boundary.boundary_segments_xyz, dtype=np.float64)
    require(len(boundary_segments_base), "actual roof TIN has no boundary segments")
    require(
        int(boundary.tin_stats["source_points_n"]) == int(manifest_tin["source_points_n"]),
        "boundary TIN source count differs from supervision TIN",
    )
    require(
        int(boundary.tin_stats["triangles_valid_n"]) == int(manifest_tin["triangles_valid_n"]),
        "boundary TIN triangle count differs from supervision TIN",
    )

    cameras_path = preprocess_root / "sparse/0/cameras.bin"
    images_path = preprocess_root / "sparse/0/images.bin"
    views_path = preprocess_root / "views.csv"
    index_path = preprocess_root / "supervision_index.csv"
    cameras_record = v4.manifest_bound_record(cameras_path, preprocess, "corrected cameras")
    images_record = v4.manifest_bound_record(images_path, preprocess, "corrected poses")
    views_record = v4.manifest_bound_record(views_path, preprocess, "selected views")
    index_record = v4.manifest_bound_record(index_path, preprocess, "supervision index")
    cameras = read_cameras_bin(cameras_path)
    images = read_images_bin(images_path)
    images_by_name = {image.name: image for image in images.values()}
    view_rows = {row["image_name"]: row for row in base.read_csv(views_path)}
    corrected_source_hash = preprocess["pose_binding"]["corrected_images_sha256"]
    require(
        bool(view_rows)
        and all(row.get("corrected_pose_source_sha256") == corrected_source_hash for row in view_rows.values()),
        "selected views are not bound to the adopted corrected pose",
    )
    supervision_rows = base.read_csv(index_path)
    require(bool(supervision_rows), "supervision index is empty")

    selection_contract = geometry["view_selection"]
    candidates: list[dict[str, Any]] = []
    flat_boundary_base = boundary_segments_base.reshape(-1, 3)
    for row in supervision_rows:
        image_name = row["image_name"]
        require(image_name in images_by_name and image_name in view_rows, f"training view pose absent: {image_name}")
        pose = images_by_name[image_name]
        camera = cameras[pose.camera_id]
        boundary_result = _project_geometry(
            flat_boundary_base, pose, camera, scene_reference, coordinate
        )
        seed_result = _project_geometry(
            filtered_seed_base, pose, camera, scene_reference, coordinate
        )
        boundary_in_frame = image_projection.in_frame_mask(boundary_result, camera)
        seed_in_frame = image_projection.in_frame_mask(seed_result, camera)
        boundary_all = bool(np.all(boundary_in_frame))
        seed_all = bool(np.all(seed_in_frame))
        boundary_segments_uv = boundary_result.uv.reshape((-1, 2, 2))
        boundary_length_px = float(
            np.linalg.norm(boundary_segments_uv[:, 1] - boundary_segments_uv[:, 0], axis=1).sum()
        ) if boundary_all else 0.0
        boundary_bbox_area_px2 = _bbox_area(boundary_segments_uv) if boundary_all else 0.0
        candidates.append(
            {
                "row": row,
                "view_row": view_rows[image_name],
                "pose": pose,
                "camera": camera,
                "boundary_segments_uv": boundary_segments_uv,
                "boundary_depth": boundary_result.depth.reshape((-1, 2)),
                "boundary_all_valid_and_in_frame": boundary_all,
                "boundary_endpoints_in_frame_n": int(boundary_in_frame.sum()),
                "boundary_endpoints_n": int(len(boundary_in_frame)),
                "seed_uv": seed_result.uv,
                "seed_depth": seed_result.depth,
                "seed_all_valid_and_in_frame": seed_all,
                "seed_in_frame_n": int(seed_in_frame.sum()),
                "seed_points_n": int(len(seed_in_frame)),
                "boundary_length_px": boundary_length_px,
                "boundary_bbox_area_px2": boundary_bbox_area_px2,
            }
        )

    eligible = [
        candidate
        for candidate in candidates
        if candidate["boundary_all_valid_and_in_frame"]
        and candidate["seed_all_valid_and_in_frame"]
    ]
    require(bool(eligible), "no training view keeps every boundary endpoint and seed valid/in-frame")
    selected = min(
        eligible,
        key=lambda candidate: (
            -float(candidate["boundary_bbox_area_px2"]),
            -float(candidate["boundary_length_px"]),
            float(candidate["view_row"]["nadir_deg"]),
            float(candidate["view_row"]["frame_radius"]),
            int(candidate["row"]["selection_order"]),
            str(candidate["row"]["image_name"]),
        ),
    )
    require(selected["boundary_all_valid_and_in_frame"], "selected boundary failed closed")
    require(selected["seed_all_valid_and_in_frame"], "selected seed failed closed")

    row = selected["row"]
    image_path = preprocess_root / "images" / row["image_name"]
    image_record = base.file_record(image_path)
    with Image.open(image_path) as source:
        image = source.convert("RGB")
        image.load()
    camera = selected["camera"]
    require(image.size == (camera.width, camera.height), "selected image/camera dimensions drift")

    boundary_segments_uv = np.asarray(selected["boundary_segments_uv"], dtype=np.float64)
    seed_uv = np.asarray(selected["seed_uv"], dtype=np.float64)
    crop_values = np.vstack((boundary_segments_uv.reshape(-1, 2), seed_uv))
    require(np.isfinite(crop_values).all(), "selected crop geometry is nonfinite")
    x0, y0 = np.floor(crop_values.min(axis=0)).astype(int)
    x1, y1 = np.ceil(crop_values.max(axis=0)).astype(int) + 1
    padding_fraction = float(geometry["crop"]["padding_fraction"])
    pad_x = max(12, int((x1 - x0) * padding_fraction))
    pad_y = max(12, int((y1 - y0) * padding_fraction))
    crop_box = (
        int(max(0, x0 - pad_x)),
        int(max(0, y0 - pad_y)),
        int(min(image.width, x1 + pad_x)),
        int(min(image.height, y1 + pad_y)),
    )
    require(crop_box[0] < crop_box[2] and crop_box[1] < crop_box[3], "geometry crop is empty")

    candidate_receipts = [
        {
            "image_name": candidate["row"]["image_name"],
            "selection_order": int(candidate["row"]["selection_order"]),
            "boundary_all_valid_and_in_frame": candidate["boundary_all_valid_and_in_frame"],
            "boundary_endpoints_in_frame_n": candidate["boundary_endpoints_in_frame_n"],
            "boundary_endpoints_n": candidate["boundary_endpoints_n"],
            "seed_all_valid_and_in_frame": candidate["seed_all_valid_and_in_frame"],
            "seed_in_frame_n": candidate["seed_in_frame_n"],
            "seed_points_n": candidate["seed_points_n"],
            "boundary_length_px": candidate["boundary_length_px"],
            "boundary_bbox_area_px2": candidate["boundary_bbox_area_px2"],
            "nadir_deg": float(candidate["view_row"]["nadir_deg"]),
            "frame_radius": float(candidate["view_row"]["frame_radius"]),
        }
        for candidate in candidates
    ]
    return {
        "row": row,
        "view_row": selected["view_row"],
        "image": image,
        "mask": np.zeros((camera.height, camera.width), dtype=bool),
        "crop_box": crop_box,
        "seed_uv": seed_uv,
        "seed_inframe": np.ones(len(seed_uv), dtype=bool),
        "footprint_uv": _nan_separated_segments(boundary_segments_uv),
        "locator_canonical_z": float("nan"),
        "mask_alignment": {
            "selected_containment_in_projected_locator": float("nan"),
            "all_views_min": float("nan"),
            "all_views_median": float("nan"),
            "all_views_max": float("nan"),
            "worst_image_name": "not_applicable_M_j_excluded",
            "worst_containment": float("nan"),
        },
        "boundary_segments_base": boundary_segments_base,
        "boundary_segments_uv": boundary_segments_uv,
        "filtered_seed_base": filtered_seed_base,
        "roof_boundary": {
            "method": geometry["roof_boundary_method"],
            "segments_n": int(len(boundary_segments_base)),
            "endpoints_n": int(boundary_segments_base.size // 3),
            "components_n": int(len(boundary.components)),
            "z_min_m": float(boundary_segments_base[:, :, 2].min()),
            "z_max_m": float(boundary_segments_base[:, :, 2].max()),
            "tin_stats": dict(boundary.tin_stats),
        },
        "seed_contract": {
            "source": "ALS classification 6 only",
            "unfiltered_points_n": int(len(unfiltered_base)),
            "filtered_points_n": int(len(filtered_seed_base)),
            "visibility_epsilon_m": float(seed_manifest["visibility"]["epsilon_m"]),
            "visibility_minimum_views_k": int(seed_manifest["visibility"]["minimum_views_k"]),
            "class2_rows_n": int(seed_manifest["class2_rows_n"]),
            "sfm_rows_n": int(seed_manifest["sfm_rows_n"]),
            "maximum_canonical_roundtrip_delta_m": maximum_seed_delta,
        },
        "selection": {
            "mode": selection_contract["mode"],
            "method": "geometry-only; maximize boundary bbox area, then boundary length, then pose/order/name tie-breaks",
            "candidates_n": len(candidates),
            "geometry_eligible_n": len(eligible),
            "boundary_all_valid_and_in_frame": True,
            "boundary_endpoints_in_frame_n": selected["boundary_endpoints_in_frame_n"],
            "boundary_endpoints_n": selected["boundary_endpoints_n"],
            "seed_all_valid_and_in_frame": True,
            "seed_in_frame_n": selected["seed_in_frame_n"],
            "seed_points_n": selected["seed_points_n"],
            "boundary_length_px": selected["boundary_length_px"],
            "boundary_bbox_area_px2": selected["boundary_bbox_area_px2"],
            "nadir_deg": float(selected["view_row"]["nadir_deg"]),
            "frame_radius": float(selected["view_row"]["frame_radius"]),
            "selection_order": int(row["selection_order"]),
            "image_pixels_used_for_ranking": False,
            "M_j_used_for_ranking_or_eligibility": False,
            "reference_GML_used_for_ranking_or_eligibility": False,
            "output_CityJSON_used_for_ranking_or_eligibility": False,
            "candidates": candidate_receipts,
        },
        "coordinate_contract": {
            **coordinate,
            "observed_corrected_cameras_sha256": cameras_record["sha256"],
            "observed_corrected_images_sha256": corrected_source_hash,
            "per_building_subset_images_bin_sha256": images_record["sha256"],
        },
        "alignment_independence": dict(geometry["alignment_independence"]),
        "records": {
            "visibility_unfiltered_votes": votes_record,
            "pretraining_seed_crosscheck": seed_record,
            "projection_config": projection_config_record,
            "scene_reference_frame": scene_record,
            "supervision_index": index_record,
            "selected_views": views_record,
            "corrected_cameras": cameras_record,
            "corrected_poses": images_record,
            "selected_full_image": image_record,
        },
    }


def augment_evidence(evidence: dict[str, Any], config: Mapping[str, Any]) -> dict[str, Any]:
    result = dict(evidence)
    surfaces, surface_stats = v4.load_cityjson_surfaces(evidence["cityjson_path"])
    score, score_record = v4.primary_score(evidence)
    input_view = projected_input_view(evidence, config)
    roofer_adapter = {"input_locator_contract": config["roofer_output_provenance"]}
    roofer_prepare, roofer_prepare_record = v4.roofer_prepare_provenance(evidence, roofer_adapter)
    source_records = dict(evidence["source_records"])
    source_records["primary_score"] = score_record
    source_records["primary_roofer_prepare"] = roofer_prepare_record
    source_records.update(input_view["records"])
    result.update(
        {
            "cityjson_surfaces": surfaces,
            "cityjson_surface_stats": surface_stats,
            "primary_score": score,
            "image_mask": input_view,
            "roofer_prepare": roofer_prepare,
            "source_records": source_records,
        }
    )
    return result


def render_panel(
    staging: Path,
    config: Mapping[str, Any],
    evidence: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Reuse the 5x5 renderer while replacing only its obsolete first-row adapter."""

    view = evidence["image_mask"]
    boundary = view["roof_boundary"]
    selection = view["selection"]
    coordinate = view["coordinate_contract"]
    original_text_panel = v4.text_panel
    original_short_title = v4.short_title
    original_axes_plot = v4.plt.Axes.plot

    title_map = {
        "Full image · target locator": (
            "A. 원본 전체·실제 지붕 경계",
            "Full image · actual 3D TIN roof boundary",
        ),
        "Crop · actual filtered ALS seed projection": (
            "B. 실제 경계 기준 확대·시드",
            "Geometry crop · actual boundary and filtered seed",
        ),
        "Actual valid supervision support M_j": (
            "C. 실제 경계·시드만 (M_j 제외)",
            "Actual boundary and seed only · M_j excluded",
        ),
    }

    def v6_short_title(
        ax: Any,
        title_ko: str,
        title_en: str,
        font: Any,
        *,
        fontsize: float = 9.0,
    ) -> None:
        replacement = title_map.get(title_en)
        if replacement is not None:
            title_ko, title_en = replacement
        original_short_title(ax, title_ko, title_en, font, fontsize=fontsize)

    def v6_text_panel(ax: Any, title_ko: str, title_en: str, lines: Sequence[str], font: Any) -> None:
        values = list(lines)
        if title_en == "Seed & input-projection receipt":
            values = [
                "학습 전 prior / pre-training prior",
                "ALS class 6 only; class 2/SfM excluded",
                f"unfiltered → k≥{view['seed_contract']['visibility_minimum_views_k']}: "
                f"{view['seed_contract']['unfiltered_points_n']} → {view['seed_contract']['filtered_points_n']}",
                f"actual TIN boundary: {boundary['segments_n']} segments / "
                f"{boundary['components_n']} components",
                f"boundary Z: {boundary['z_min_m']:.3f}–{boundary['z_max_m']:.3f} m (not flat)",
                "",
                f"input view: {view['row']['image_name']}",
                f"nadir / frame radius: {selection['nadir_deg']:.2f}° / {selection['frame_radius']:.3f}",
                f"boundary endpoints in frame: {selection['boundary_endpoints_in_frame_n']} / "
                f"{selection['boundary_endpoints_n']}",
                f"seed points in frame: {selection['seed_in_frame_n']} / {selection['seed_points_n']}",
                "view ranking + crop: boundary/seed geometry only",
                f"datum/geoid: {coordinate['input_vertical_datum']} / "
                f"{coordinate['orthometric_to_ellipsoidal_geoid_m']:.3f} m",
                f"adopted pose SHA: {coordinate['adopted_corrected_images_sha256'][:12]}…",
                "additional pose transform: 0",
                "M_j/reference/output model: excluded from first-row alignment",
            ]
        original_text_panel(ax, title_ko, title_en, values, font)

    def v6_axes_plot(self: Any, *args: Any, **kwargs: Any) -> Any:
        values = dict(kwargs)
        if values.get("label") == "approved footprint XY @ ALS height":
            values["label"] = "actual-Z class-6 TIN boundary"
        return original_axes_plot(self, *args, **values)

    render_config = dict(config)
    render_config["input_locator_contract"] = config["roofer_output_provenance"]
    v4.short_title = v6_short_title
    v4.text_panel = v6_text_panel
    v4.plt.Axes.plot = v6_axes_plot
    try:
        quality, render, font_record = v4.render_panel(staging, render_config, evidence)
    finally:
        v4.plt.Axes.plot = original_axes_plot
        v4.text_panel = original_text_panel
        v4.short_title = original_short_title

    render.pop("input_locator", None)
    render["input_roof_geometry_overlay"] = {
        "selected_image": view["row"]["image_name"],
        "selection": selection,
        "boundary": boundary,
        "seed_contract": view["seed_contract"],
        "coordinate_contract": coordinate,
        "alignment_independence": view["alignment_independence"],
        "crop_box_xyxy": list(view["crop_box"]),
        "crop_geometry": config["first_row_geometry_contract"]["crop"]["geometry"],
        "overlay_layers": [
            "actual_Z_incidence_one_class6_TIN_boundary_segments",
            "actual_filtered_ALS_class6_seed_projection",
        ],
    }
    render["visual_backfill"] = {
        "version": "v6",
        "scope": "post_hoc_qualitative_visual_only",
        "training_readout_assembly_score_changed": False,
        "v4_status": config["historical_bundles"]["v4"]["status"],
        "v5_status": config["historical_bundles"]["v5"]["status"],
        "flat_median_height_locator_used": False,
    }
    return quality, render, font_record


def source_snapshot(evidence: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    return {role: base.verify_record(record, role) for role, record in evidence["source_records"].items()}


def output_record(path: Path, destination: Path | None = None) -> dict[str, Any]:
    record = base.file_record(path)
    if destination is not None:
        record["path"] = base.display_path(destination / path.name)
    return record


def verify_bundle(
    config: Mapping[str, Any],
    base_config: Mapping[str, Any],
    building_id: str,
    arm: str,
    replicate: str,
    output_root: Path | None = None,
) -> dict[str, Any]:
    validate_identity(config, base_config, building_id, arm, replicate)
    root = output_job_dir(config, building_id, arm, replicate, output_root)
    receipt = base.load_json(root / config["outputs"]["complete"])
    require(receipt.get("schema") == RECEIPT_SCHEMA, "v6 receipt schema drift")
    require(receipt.get("state") == "COMPLETE", "v6 receipt is not COMPLETE")
    require(
        receipt.get("measurement_state") == "MEASURED_REUSED_VISUAL_BACKFILL",
        "v6 measurement state drift",
    )
    require(
        receipt.get("identity")
        == {"run_id": config["run_id"], "building_id": building_id, "arm": arm, "replicate": replicate},
        "v6 receipt identity drift",
    )
    require(receipt.get("scientific_verdict") is None, "v6 receipt contains verdict")
    require(receipt.get("interpretation") is None, "v6 receipt contains interpretation")
    require(receipt.get("implementation") == implementation_records(config), "v6 implementation hash drift")
    require(
        receipt.get("historical_bundles") == historical_bundle_snapshot(config),
        "historical bundles changed after v6 publication",
    )
    current_sources = {
        role: base.verify_record(record, f"v6 receipt source {role}")
        for role, record in receipt.get("source_records", {}).items()
    }
    require(current_sources == receipt["source_records"], "v6 source record drift")
    current_readout = base.file_record(base.resolve_readout_complete(base_config, building_id, arm, replicate))
    require(receipt.get("source_readout_complete") == current_readout, "v6 source readout is not canonical")
    require({path.name for path in root.iterdir()} == {"panel.png", "complete.json"}, "v6 bundle file set drift")
    require(receipt["outputs"]["panel"] == output_record(root / "panel.png"), "v6 panel output drift")
    base.png_stats(root / "panel.png", config["visual_contract"]["minimum_panel_pixels"])
    render = receipt["panel_contract"]["render"]
    require("input_locator" not in render, "obsolete flat locator leaked into v6 receipt")
    overlay = render["input_roof_geometry_overlay"]
    require(overlay["selection"]["boundary_all_valid_and_in_frame"] is True, "v6 boundary not fail-closed")
    require(overlay["selection"]["seed_all_valid_and_in_frame"] is True, "v6 seed not fail-closed")
    require(
        overlay["coordinate_contract"]["observed_corrected_images_sha256"]
        == config["first_row_geometry_contract"]["coordinate_contract"]["adopted_corrected_images_sha256"],
        "v6 observed pose hash drift",
    )
    require(
        overlay["coordinate_contract"]["additional_transform_application_count"] == 0,
        "v6 additional transform drift",
    )
    require(
        all(value is False for value in overlay["alignment_independence"].values()),
        "v6 first-row alignment is not independent",
    )
    require(receipt["publication"]["gpu_devices_used"] == [], "v6 receipt bound a GPU")
    require(
        receipt["publication"]["unrelated_queue_allowed"] is True,
        "v6 receipt unrelated-queue policy drift",
    )
    require(receipt["publication"]["receipt_written_last"] is True, "v6 receipt-last flag absent")
    return receipt


def publish_job(
    config: Mapping[str, Any],
    base_config: Mapping[str, Any],
    report: Any,
    building_id: str,
    arm: str,
    replicate: str,
    output_root: Path | None = None,
) -> dict[str, Any]:
    validate_identity(config, base_config, building_id, arm, replicate)
    destination = output_job_dir(config, building_id, arm, replicate, output_root)
    receipt_path = destination / config["outputs"]["complete"]
    if receipt_path.is_file():
        return verify_bundle(config, base_config, building_id, arm, replicate, output_root)
    require(not destination.exists(), f"refusing incomplete/nonempty v6 bundle: {base.display_path(destination)}")

    implementation_before = implementation_records(config)
    historical_before = historical_bundle_snapshot(config)
    evidence = base.resolve_evidence(base_config, report, building_id, arm, replicate)
    evidence = augment_evidence(evidence, config)
    evidence["base_config"] = base_config
    sources_before = source_snapshot(evidence)
    references_before = [
        base.verify_large_locked_record(record, f"reference_gml[{index}]")
        for index, record in enumerate(base_config["locked_inputs"]["reference_gml"])
    ]
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{replicate}.panel-v6-roof-boundary-staging-", dir=destination.parent))
    try:
        quality, render, font_record = render_panel(staging, config, evidence)
        require(source_snapshot(evidence) == sources_before, "source inputs changed during v6 render")
        require(
            historical_bundle_snapshot(config) == historical_before,
            "historical v4/v5 bundle changed during v6 render",
        )
        require(implementation_records(config) == implementation_before, "v6 implementation changed during render")
        score = v4.score_row(evidence)
        receipt = {
            "schema": RECEIPT_SCHEMA,
            "task_id": config["task_id"],
            "state": "COMPLETE",
            "measurement_state": "MEASURED_REUSED_VISUAL_BACKFILL",
            "created_at": v4.utc_now(),
            "identity": evidence["identity"],
            "backfill_contract": config["backfill_contract"],
            "resolver_disclosure": config["resolver_disclosure"],
            "historical_bundles": historical_before,
            "source_readout_complete": evidence["source_readout_complete"],
            "source_records": sources_before,
            "reference_gml": {
                "role": "evaluation_only_final_row_after_output_freeze",
                "records": references_before,
                "used_for_first_row_alignment_selection_or_crop": False,
                "view_orientation_influence": False,
                "shared_bounds_influence_for_geometry_rows_only": True,
            },
            "panel_contract": {
                "single_visual_file": True,
                "visual_filename": config["outputs"]["panel"],
                "placeholders": 0,
                "render": render,
            },
            "render_quality": quality,
            "font": font_record,
            "primary_measurements_reused": evidence["readout"]["primary"]["measurements"],
            "p0prime_deltas_reused": {
                "delta_roof_rms_vs_p0_refl_m": score.get("delta_roof_rms_vs_p0_refl_m"),
                "delta_roof_completeness_vs_p0_refl": score.get("delta_roof_completeness_vs_p0_refl"),
                "delta_face_count_ratio_vs_p0_refl": score.get("delta_face_count_ratio_vs_p0_refl"),
            },
            "citygml_export_reused": evidence["serialization_capability"],
            "implementation": implementation_before,
            "outputs": {"panel": output_record(staging / config["outputs"]["panel"], destination)},
            "publication": {
                "visual_backfill_only": True,
                "one_visual_panel_per_job": True,
                "job_directory_atomic_publish": True,
                "overwrite_allowed": False,
                "historical_v4_v5_unchanged": True,
                "unrelated_queue_allowed": True,
                "gpu_devices_used": [],
                "output_namespace_isolated_from_training": True,
                "source_inputs_rehashed_after_render": True,
                "source_inputs_unchanged": True,
                "receipt_written_last": True,
            },
            "scientific_verdict": None,
            "interpretation": None,
        }
        base.write_json_exclusive(staging / config["outputs"]["complete"], receipt)
        os.replace(staging, destination)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return verify_bundle(config, base_config, building_id, arm, replicate, output_root)


def check_job(
    config: Mapping[str, Any],
    base_config: Mapping[str, Any],
    report: Any,
    building_id: str,
    arm: str,
    replicate: str,
) -> dict[str, Any]:
    validate_identity(config, base_config, building_id, arm, replicate)
    evidence = augment_evidence(
        base.resolve_evidence(base_config, report, building_id, arm, replicate),
        config,
    )
    view = evidence["image_mask"]
    return {
        "state": "READY",
        "identity": evidence["identity"],
        "scope": "post_hoc_qualitative_visual_only",
        "selected_image": view["row"]["image_name"],
        "roof_boundary": view["roof_boundary"],
        "seed_contract": view["seed_contract"],
        "selection": view["selection"],
        "coordinate_contract": view["coordinate_contract"],
        "alignment_independence": view["alignment_independence"],
        "historical_bundles": historical_bundle_snapshot(config),
        "training_readout_assembly_score_changed": False,
        "scientific_verdict": None,
        "interpretation": None,
    }


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    result.add_argument("--output-root", type=Path)
    result.add_argument("command", choices=("check", "backfill", "verify"))
    return result


def main(argv: Sequence[str] | None = None) -> int:
    args = parser().parse_args(argv)
    config, base_config = load_config(args.config)
    identity = allowed_identity(config)
    report = base.load_report_module(base_config)
    if args.command == "check":
        payload = check_job(config, base_config, report, *identity)
    elif args.command == "backfill":
        payload = publish_job(config, base_config, report, *identity, output_root=args.output_root)
    else:
        payload = verify_bundle(config, base_config, *identity, output_root=args.output_root)
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (PanelError, image_projection.ProjectionError, roof_boundary_overlay.RoofBoundaryError) as exc:
        print(f"[FAILED] {type(exc).__name__}: {exc}", file=sys.stderr)
        raise SystemExit(2)
