#!/usr/bin/env python3
"""Render ten roofline-only panels after validating real COLMAP 2D observations."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import html
import json
import math
import os
from pathlib import Path
import random
from typing import Any, Mapping, Sequence

import numpy as np
import PIL
from PIL import Image, ImageDraw, ImageFont, ImageOps

from scripts.evidence_and_attributes.population_analysis import population_aux_v3 as projection
from scripts.p2.qualitative_199_common_manifest_v1.build_manifest import crop_xyxy
from scripts.p2.qualitative_row1_current_raw_v3.preview import (
    canonical_json_bytes,
    draw_segments,
    file_record,
    image_inventory,
    outer_roof_shell_edges,
    png_bytes,
    project_edges,
    sha256_file,
    sparse_building_grid,
    stable_seed,
    verify_file,
    write_new,
)
from scripts.p2.utarget199_presentation_v5.render import load_references


REPO = Path(__file__).resolve().parents[3]
DEFAULT_CONFIG = REPO / "configs/p2/qualitative_row1_current_raw_v4/preview10_v1.json"


def scan_sparse_observations(
    path: Path,
    buildings: Sequence[Mapping[str, Any]],
    exact_image_ids: set[int],
    shift: Sequence[float],
    expected_point_count: int,
    cell_size: float = 10.0,
) -> tuple[dict[str, dict[str, Any]], dict[str, int]]:
    """Keep the full COLMAP (image id, POINT2D_IDX) track for the ten buildings."""
    shift_xyz = np.asarray(shift, dtype=np.float64)
    by_id = {str(row["building_id"]): row for row in buildings}
    grid = sparse_building_grid(buildings, cell_size)
    support: dict[str, dict[str, Any]] = {
        building_id: {
            "xy_point_count_all_z": 0,
            "xyz_point_count": 0,
            "image_observations": defaultdict(list),
        }
        for building_id in by_id
    }
    scanned = assigned = retained = 0
    with path.open("r", encoding="utf-8") as stream:
        for line in stream:
            if not line or line[0] == "#":
                continue
            fields = line.split()
            if len(fields) < 8 or (len(fields) - 8) % 2:
                raise RuntimeError("COLMAP sparse point row is malformed")
            scanned += 1
            point_id = int(fields[0])
            xyz = np.asarray(fields[1:4], dtype=np.float64) + shift_xyz
            key = (math.floor(float(xyz[0]) / cell_size), math.floor(float(xyz[1]) / cell_size))
            candidate_ids = grid.get(key, ())
            if not candidate_ids:
                continue
            tracks = [
                (int(fields[index]), int(fields[index + 1]))
                for index in range(8, len(fields), 2)
                if int(fields[index]) in exact_image_ids
            ]
            for building_id in candidate_ids:
                building = by_id[building_id]
                min_x, min_y, max_x, max_y = map(float, building["building_bbox_xy"])
                if not (min_x <= xyz[0] <= max_x and min_y <= xyz[1] <= max_y):
                    continue
                entry = support[building_id]
                entry["xy_point_count_all_z"] += 1
                min_z, max_z = map(float, building["z_range_ellipsoidal_m"])
                if not (min_z <= xyz[2] <= max_z):
                    continue
                entry["xyz_point_count"] += 1
                assigned += 1
                for image_id, point2d_index in tracks:
                    entry["image_observations"][image_id].append(
                        (point_id, point2d_index, xyz.copy())
                    )
                    retained += 1
    if scanned != int(expected_point_count):
        raise RuntimeError(f"sparse point count drifted: {scanned} != {expected_point_count}")
    return support, {
        "sparse_points_scanned": scanned,
        "selected_building_prism_point_assignments": assigned,
        "selected_building_exact_937_track_observations": retained,
        "spatial_grid_cell_size_m": int(cell_size),
    }


def load_actual_point2d_observations(
    images_path: Path,
    support: Mapping[str, Mapping[str, Any]],
) -> tuple[dict[tuple[int, int], tuple[np.ndarray, int]], dict[str, int]]:
    needed: defaultdict[int, set[int]] = defaultdict(set)
    for building in support.values():
        for image_id, rows in building["image_observations"].items():
            needed[int(image_id)].update(int(row[1]) for row in rows)
    observed: dict[tuple[int, int], tuple[np.ndarray, int]] = {}
    image_rows_seen = 0
    expect_metadata = True
    current_image_id: int | None = None
    with images_path.open("r", encoding="utf-8") as stream:
        for line in stream:
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            if expect_metadata:
                current_image_id = int(stripped.split()[0])
                expect_metadata = False
                continue
            image_rows_seen += 1
            if current_image_id in needed:
                fields = stripped.split()
                if len(fields) % 3:
                    raise RuntimeError(f"COLMAP image observation row malformed: {current_image_id}")
                count = len(fields) // 3
                for point2d_index in needed[current_image_id]:
                    if point2d_index < 0 or point2d_index >= count:
                        continue
                    offset = point2d_index * 3
                    observed[(current_image_id, point2d_index)] = (
                        np.asarray([float(fields[offset]), float(fields[offset + 1])], dtype=np.float64),
                        int(fields[offset + 2]),
                    )
            expect_metadata = True
    if not expect_metadata:
        raise RuntimeError("COLMAP images.txt ended between metadata and observation rows")
    return observed, {
        "colmap_image_observation_rows_scanned": image_rows_seen,
        "requested_point2d_observations": sum(len(indices) for indices in needed.values()),
        "loaded_point2d_observations": len(observed),
    }


def candidate_record(
    image_id: int,
    image_name: str,
    rows: Sequence[tuple[int, int, np.ndarray]],
    observed: Mapping[tuple[int, int], tuple[np.ndarray, int]],
    camera: Any,
    building: Mapping[str, Any],
    model: tuple[int, int, np.ndarray],
    scene_reference: Mapping[str, Any],
    selection: Mapping[str, Any],
    crop_spec: Mapping[str, Any],
) -> dict[str, Any]:
    matched_xyz: list[np.ndarray] = []
    actual_uv: list[np.ndarray] = []
    loaded_count = integrity_count = 0
    for point_id, point2d_index, xyz in rows:
        value = observed.get((image_id, point2d_index))
        if value is None:
            continue
        loaded_count += 1
        uv, observed_point_id = value
        if observed_point_id != point_id:
            continue
        integrity_count += 1
        matched_xyz.append(xyz)
        actual_uv.append(uv)
    xyz_array = np.asarray(matched_xyz, dtype=np.float64).reshape((-1, 3))
    actual_array = np.asarray(actual_uv, dtype=np.float64).reshape((-1, 2))
    width, height, params = model
    projected, front = projection.project(
        xyz_array,
        camera,
        width,
        height,
        params,
        scene_reference,
        input_datum="ellipsoidal",
    ) if len(xyz_array) else (np.empty((0, 2)), np.empty((0,), dtype=bool))
    valid = front & np.isfinite(projected).all(axis=1) if len(projected) else np.empty((0,), dtype=bool)
    residual = np.linalg.norm(projected[valid] - actual_array[valid], axis=1) if len(projected) else np.empty((0,))
    actual_valid = actual_array[valid] if len(actual_array) else np.empty((0, 2))
    spread_xy = np.ptp(actual_valid, axis=0) if len(actual_valid) else np.zeros(2)
    spread_diagonal = float(np.linalg.norm(spread_xy))
    integrity_fraction = float(integrity_count / len(rows)) if rows else 0.0
    median_error = float(np.median(residual)) if len(residual) else None
    p95_error = float(np.quantile(residual, 0.95)) if len(residual) else None
    frozen_crop = crop_xyxy(
        actual_valid,
        width,
        height,
        float(crop_spec["actual_observation_margin_scale"]),
        float(crop_spec["actual_observation_margin_constant_px"]),
    )
    center = np.asarray(
        [
            building["principal_frame"]["center_xy"][0],
            building["principal_frame"]["center_xy"][1],
            float(np.mean(building["z_range_ellipsoidal_m"])),
        ],
        dtype=np.float64,
    )
    view_vector = np.asarray(camera.center, dtype=np.float64) - center
    view_vector /= max(float(np.linalg.norm(view_vector)), 1e-12)
    nadir_deg = math.degrees(math.acos(float(np.clip(view_vector[2], -1.0, 1.0))))
    rejection_reasons = []
    if len(rows) < int(selection["minimum_track_point_count"]):
        rejection_reasons.append("INSUFFICIENT_TRACK_POINTS")
    if integrity_fraction < float(selection["minimum_track_index_integrity_fraction"]):
        rejection_reasons.append("POINT2D_INDEX_INTEGRITY_FAILURE")
    if len(residual) < int(selection["minimum_track_point_count"]):
        rejection_reasons.append("INSUFFICIENT_VALID_ACTUAL_OBSERVATIONS")
    if spread_diagonal < float(selection["minimum_actual_observation_spread_diagonal_px"]):
        rejection_reasons.append("INSUFFICIENT_ACTUAL_OBSERVATION_SPREAD")
    if median_error is None or median_error > float(selection["maximum_median_reprojection_error_px"]):
        rejection_reasons.append("MEDIAN_REPROJECTION_ERROR_EXCEEDED")
    if p95_error is None or p95_error > float(selection["maximum_p95_reprojection_error_px"]):
        rejection_reasons.append("P95_REPROJECTION_ERROR_EXCEEDED")
    if frozen_crop is None:
        rejection_reasons.append("ACTUAL_OBSERVATION_CROP_UNAVAILABLE")
    return {
        "image_id": int(image_id),
        "camera_name": image_name,
        "track_point_count": int(len(rows)),
        "loaded_point2d_count": loaded_count,
        "point2d_index_integrity_count": integrity_count,
        "point2d_index_integrity_fraction": integrity_fraction,
        "valid_actual_observation_count": int(len(residual)),
        "actual_observation_spread_diagonal_px": spread_diagonal,
        "median_reprojection_error_px": median_error,
        "p95_reprojection_error_px": p95_error,
        "nadir_deg": nadir_deg,
        "crop_xyxy": frozen_crop,
        "eligible": not rejection_reasons,
        "rejection_reasons": rejection_reasons,
        "_actual_uv": actual_valid,
        "_view_vector": view_vector,
        "_camera_center": np.asarray(camera.center, dtype=np.float64),
    }


def public_candidate(candidate: Mapping[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in candidate.items() if not str(key).startswith("_")}


def separated(
    candidate: Mapping[str, Any],
    chosen: Sequence[Mapping[str, Any]],
    minimum_angle_deg: float,
    minimum_baseline_m: float,
) -> bool:
    for other in chosen:
        angle = math.degrees(
            math.acos(
                float(
                    np.clip(
                        np.asarray(candidate["_view_vector"]) @ np.asarray(other["_view_vector"]),
                        -1.0,
                        1.0,
                    )
                )
            )
        )
        baseline = float(
            np.linalg.norm(np.asarray(candidate["_camera_center"]) - np.asarray(other["_camera_center"]))
        )
        if angle < minimum_angle_deg and baseline < minimum_baseline_m:
            return False
    return True


def choose_views(
    building_id: str,
    candidates: Sequence[dict[str, Any]],
    selection: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], str, int, str]:
    eligible = [row for row in candidates if row["eligible"]]
    roles = [str(value) for value in selection["roles"]]
    seed = stable_seed(str(selection["random_seed_namespace"]), building_id)
    pool = [public_candidate(row) for row in sorted(eligible, key=lambda row: row["camera_name"])]
    pool_hash = hashlib.sha256(canonical_json_bytes(pool)).hexdigest()
    if not eligible:
        return [
            {"role": role, "status": "OBSERVED_TRACK_SUPPORT_MISSING", "camera": None}
            for role in roles
        ], "OBSERVED_TRACK_SUPPORT_MISSING", seed, pool_hash
    top = min(
        eligible,
        key=lambda row: (
            row["nadir_deg"],
            -row["valid_actual_observation_count"],
            row["camera_name"],
        ),
    )
    if top["nadir_deg"] <= float(selection["near_nadir_max_deg"]):
        top_status = "NEAR_NADIR"
    else:
        top_status = "BEST_AVAILABLE_NO_NEAR_NADIR"
    remaining = [row for row in eligible if row is not top]
    random.Random(seed).shuffle(remaining)
    chosen = [top]
    random_views = []
    for candidate in remaining:
        if separated(
            candidate,
            chosen,
            float(selection["minimum_view_direction_separation_deg"]),
            float(selection["minimum_camera_center_separation_m"]),
        ):
            random_views.append(candidate)
            chosen.append(candidate)
            if len(random_views) == len(roles) - 1:
                break
    views = [
        {
            "role": roles[0],
            "status": "SELECTED",
            "source": top_status,
            "camera": public_candidate(top),
        }
    ]
    for role, candidate in zip(roles[1:], random_views):
        views.append(
            {
                "role": role,
                "status": "SELECTED",
                "source": "DETERMINISTIC_POSE_DIVERSE_RANDOM",
                "camera": public_candidate(candidate),
            }
        )
    for role in roles[len(views) :]:
        views.append({"role": role, "status": "OBSERVED_TRACK_SUPPORT_MISSING", "camera": None})
    return views, top_status, seed, pool_hash


def roofline_status(roof_uv: np.ndarray, crop: Sequence[int]) -> str:
    if not len(roof_uv):
        return "ROOFLINE_NOT_PROJECTABLE"
    inside = (
        (roof_uv[:, 0] >= crop[0])
        & (roof_uv[:, 0] < crop[2])
        & (roof_uv[:, 1] >= crop[1])
        & (roof_uv[:, 1] < crop[3])
    )
    if bool(np.all(inside)):
        return "ROOFLINE_PROJECTED"
    if bool(np.any(inside)):
        return "ROOFLINE_PARTIAL"
    return "ROOFLINE_OUTSIDE_CROP"


def panel(
    image: Image.Image,
    role: str,
    note: str,
    status: str,
    render: Mapping[str, Any],
    regular: ImageFont.FreeTypeFont,
    bold: ImageFont.FreeTypeFont,
) -> Image.Image:
    width = int(render["cell_width_px"])
    header = int(render["cell_header_height_px"])
    image_height = int(render["cell_image_height_px"])
    cell = Image.new("RGB", (width, header + image_height), tuple(render["cell_background_rgb"]))
    fitted = ImageOps.contain(image.convert("RGB"), (width, image_height), Image.Resampling.LANCZOS)
    cell.paste(fitted, ((width - fitted.width) // 2, header + (image_height - fitted.height) // 2))
    draw = ImageDraw.Draw(cell)
    draw.text((24, 12), role, font=bold, fill=tuple(render["text_rgb"]))
    draw.text((24, 59), note, font=regular, fill=tuple(render["muted_text_rgb"]))
    color = (255, 214, 10) if status == "ROOFLINE_PROJECTED" else (255, 156, 80)
    draw.text((width - 24, 18), status, font=regular, fill=color, anchor="ra")
    return cell


def missing_panel(
    role: str,
    render: Mapping[str, Any],
    regular: ImageFont.FreeTypeFont,
    bold: ImageFont.FreeTypeFont,
) -> Image.Image:
    width = int(render["cell_width_px"])
    height = int(render["cell_header_height_px"]) + int(render["cell_image_height_px"])
    cell = Image.new("RGB", (width, height), tuple(render["cell_background_rgb"]))
    draw = ImageDraw.Draw(cell)
    draw.text((24, 12), role, font=bold, fill=tuple(render["text_rgb"]))
    draw.text((width / 2, height / 2), "OBSERVED TRACK SUPPORT MISSING", font=bold, fill=(255, 156, 80), anchor="mm")
    draw.text((width / 2, height / 2 + 50), "No unvalidated camera substituted", font=regular, fill=tuple(render["muted_text_rgb"]), anchor="mm")
    return cell


def render_building(
    building: Mapping[str, Any],
    selection_record: Mapping[str, Any],
    roof_edges: Sequence[np.ndarray],
    shell_diagnostic: Mapping[str, Any],
    cameras: Mapping[str, Any],
    model: tuple[int, int, np.ndarray],
    scene_reference: Mapping[str, Any],
    image_dir: Path,
    render: Mapping[str, Any],
) -> tuple[bytes, list[dict[str, Any]]]:
    views = selection_record["views"]
    width = int(render["cell_width_px"]) * len(views)
    height = int(render["row_header_height_px"]) + int(render["cell_header_height_px"]) + int(render["cell_image_height_px"])
    canvas = Image.new("RGB", (width, height), tuple(render["background_rgb"]))
    regular = ImageFont.truetype(str(render["font_regular_path"]), 23)
    bold = ImageFont.truetype(str(render["font_bold_path"]), 34)
    title_font = ImageFont.truetype(str(render["font_bold_path"]), 38)
    draw = ImageDraw.Draw(canvas)
    draw.text((26, 18), "ROW 1 v4 — PHOTO + OUTER ROOFLINE", font=title_font, fill=tuple(render["text_rgb"]))
    draw.text(
        (width - 26, 25),
        f"{int(building['population_index']):03d}/199  {building['building_id']}",
        font=bold,
        fill=tuple(render["text_rgb"]),
        anchor="ra",
    )
    diagnostics = []
    for column, view in enumerate(views):
        role = str(view["role"]).replace("_", " ")
        if view["status"] != "SELECTED":
            cell = missing_panel(role, render, regular, bold)
            diagnostics.append({"role": view["role"], "status": view["status"]})
        else:
            camera_record = view["camera"]
            camera_name = str(camera_record["camera_name"])
            crop = list(map(int, camera_record["crop_xyxy"]))
            with Image.open(image_dir / camera_name) as raw:
                crop_image = raw.convert("RGB").crop(tuple(crop))
            segments, roof_uv = project_edges(
                roof_edges, cameras[camera_name], model, scene_reference, crop
            )
            draw_segments(crop_image, segments, render)
            status = roofline_status(roof_uv, crop)
            display_role = role
            if view["role"] == "TOP" and view["source"] == "BEST_AVAILABLE_NO_NEAR_NADIR":
                display_role = "BEST AVAILABLE"
            note = f"{camera_name} | nadir={float(camera_record['nadir_deg']):.1f}°"
            cell = panel(crop_image, display_role, note, status, render, regular, bold)
            diagnostics.append(
                {
                    "role": view["role"],
                    "display_role": display_role,
                    "camera_name": camera_name,
                    "selection_source": view["source"],
                    "roofline_status": status,
                    "outer_roof_projected_segment_count": len(segments),
                    "internal_pose_validation": {
                        "point2d_index_integrity_fraction": camera_record["point2d_index_integrity_fraction"],
                        "valid_actual_observation_count": camera_record["valid_actual_observation_count"],
                        "median_reprojection_error_px": camera_record["median_reprojection_error_px"],
                        "p95_reprojection_error_px": camera_record["p95_reprojection_error_px"],
                    },
                    **shell_diagnostic,
                }
            )
        canvas.paste(
            cell,
            (column * int(render["cell_width_px"]), int(render["row_header_height_px"])),
        )
    return png_bytes(canvas, render), diagnostics


def html_page(rows: Sequence[Mapping[str, Any]]) -> bytes:
    cards = "".join(
        f'<article><h2>{int(row["population_index"]):03d}/199 — {html.escape(str(row["building_id"]))}</h2>'
        f'<img src="rows/{html.escape(str(row["filename"]))}"></article>'
        for row in rows
    )
    return (
        "<!doctype html><html lang=ko><meta charset=utf-8><style>body{font-family:Arial,sans-serif;"
        "max-width:1960px;margin:auto;background:#111820;color:#f5f7fa}article{border-top:4px solid #607080;"
        "margin:40px 0}img{width:100%}</style><h1>Row 1 v4 ten-building roofline preview</h1>" + cards + "</html>"
    ).encode()


def run(
    config_path: Path,
    repo_root: Path,
    artifact_root: Path,
    output_root: Path,
    source_commit: str,
    image_id: str,
) -> dict[str, Any]:
    config = json.loads(config_path.read_text(encoding="utf-8"))
    if (
        config.get("status") != "USER_APPROVED_ROW1_SCRIPT_REVIEW_AND_TEN_BUILDING_PREVIEW"
        or int(config["preview"]["building_count"]) != 10
        or config["preview"]["full_199_render_authorized"]
        or config["selection"]["keypoints_rendered"]
    ):
        raise RuntimeError("only the approved ten-building roofline-only preview is authorized")
    if output_root.exists() or output_root.with_name(output_root.name + ".partial").exists():
        raise RuntimeError(f"add-once output exists: {output_root}")
    partial = output_root.with_name(output_root.name + ".partial")
    partial.mkdir(parents=True)
    inputs = config["inputs"]
    common_root = artifact_root / inputs["common_manifest_relative_root"]
    building_path = common_root / inputs["building_manifest_relative_path"]
    bindings = {
        "building_manifest": verify_file(building_path, inputs["building_manifest_sha256"], "building manifest"),
        "image_inventory": verify_file(repo_root / inputs["image_inventory_git_path"], inputs["image_inventory_sha256"], "image inventory"),
        "exact_937_crosswalk": verify_file(repo_root / inputs["exact_937_crosswalk_git_path"], inputs["exact_937_crosswalk_sha256"], "exact crosswalk"),
        "cameras": verify_file(artifact_root / inputs["cameras_relative_path"], inputs["cameras_sha256"], "cameras"),
        "images": verify_file(artifact_root / inputs["images_relative_path"], inputs["images_sha256"], "images"),
        "points3D": verify_file(artifact_root / inputs["points3d_relative_path"], inputs["points3d_sha256"], "points3D", int(inputs["points3d_bytes"])),
        "scene_reference": verify_file(artifact_root / inputs["scene_reference_relative_path"], inputs["scene_reference_sha256"], "scene reference"),
        "v3_helper": verify_file(repo_root / inputs["v3_helper_git_path"], inputs["v3_helper_sha256"], "v3 helper", int(inputs["v3_helper_bytes"])),
    }
    for index, relative in enumerate(inputs["lod2_relative_paths"]):
        bindings[f"lod2_{index + 1}"] = verify_file(
            artifact_root / relative, inputs["lod2_sha256"][index], f"LoD2 {index + 1}"
        )
    render = config["render"]
    bindings["font_regular"] = verify_file(Path(render["font_regular_path"]), render["font_regular_sha256"], "regular font")
    bindings["font_bold"] = verify_file(Path(render["font_bold_path"]), render["font_bold_sha256"], "bold font")
    if PIL.__version__ != render["pillow_version"]:
        raise RuntimeError("Pillow version drifted")

    population = [json.loads(line) for line in building_path.read_text(encoding="utf-8").splitlines() if line]
    indices = [int(value) for value in config["preview"]["population_indices"]]
    building_ids = [str(value) for value in config["preview"]["building_ids"]]
    selected_buildings = []
    for index, expected_id in zip(indices, building_ids):
        building = population[index - 1]
        if str(building["building_id"]) != expected_id:
            raise RuntimeError("ten-building membership drifted")
        selected_buildings.append(building)

    exact = json.loads((repo_root / inputs["exact_937_crosswalk_git_path"]).read_text(encoding="utf-8"))
    image_id_to_name = {int(row["colmap_image_id"]): str(row["basename"]) for row in exact["rows"]}
    scene_reference = json.loads((artifact_root / inputs["scene_reference_relative_path"]).read_text(encoding="utf-8"))
    model = projection.parse_cam_model(artifact_root / inputs["cameras_relative_path"])
    images_path = artifact_root / inputs["images_relative_path"]
    cameras = {camera.name: camera for camera in projection.parse_cameras(images_path, scene_reference)}
    support, sparse_summary = scan_sparse_observations(
        artifact_root / inputs["points3d_relative_path"],
        selected_buildings,
        set(image_id_to_name),
        config["frame"]["sparse_local_shift_xyz"],
        int(inputs["points3d_count"]),
    )
    observed, observation_summary = load_actual_point2d_observations(images_path, support)

    selection_records = []
    candidate_audit = []
    top_status_counts: Counter[str] = Counter()
    rejection_reason_counts: Counter[str] = Counter()
    missing_role_count = 0
    for building in selected_buildings:
        building_id = str(building["building_id"])
        candidates = []
        for sparse_image_id, rows in support[building_id]["image_observations"].items():
            candidate = candidate_record(
                sparse_image_id,
                image_id_to_name[sparse_image_id],
                rows,
                observed,
                cameras[image_id_to_name[sparse_image_id]],
                building,
                model,
                scene_reference,
                config["selection"],
                config["crop"],
            )
            candidates.append(candidate)
            for reason in candidate["rejection_reasons"]:
                rejection_reason_counts[str(reason)] += 1
            candidate_audit.append(
                {
                    "schema": "jointbuildgs.p2.qualitative_row1_current_raw.camera_candidate_audit.v4",
                    "population_index": int(building["population_index"]),
                    "building_id": building_id,
                    **public_candidate(candidate),
                    "scientific_verdict": None,
                }
            )
        views, top_status, seed, pool_hash = choose_views(building_id, candidates, config["selection"])
        top_status_counts[top_status] += 1
        missing_role_count += sum(view["status"] != "SELECTED" for view in views)
        selection_records.append(
            {
                "schema": "jointbuildgs.p2.qualitative_row1_current_raw.camera_selection.v4",
                "population_index": int(building["population_index"]),
                "building_id": building_id,
                "sparse_points_xy_bbox_all_z": int(support[building_id]["xy_point_count_all_z"]),
                "sparse_points_xy_bbox_z_prism": int(support[building_id]["xyz_point_count"]),
                "track_confirmed_image_count": len(candidates),
                "internally_validated_image_count": sum(row["eligible"] for row in candidates),
                "eligible_candidate_pool_sha256": pool_hash,
                "seed_uint64": seed,
                "top_status": top_status,
                "views": views,
                "actual_point2d_used_for_internal_validation": True,
                "keypoints_rendered": False,
                "roof_boundary_used_for_camera_selection": False,
                "scientific_verdict": None,
            }
        )
    write_new(partial / "selection/camera_candidate_audit_v4.jsonl", b"".join(canonical_json_bytes(row) for row in candidate_audit))
    write_new(partial / "selection/row1_camera_selection_v4.jsonl", b"".join(canonical_json_bytes(row) for row in selection_records))

    references = load_references(
        [artifact_root / path for path in inputs["lod2_relative_paths"]], building_ids
    )
    selection_by_id = {str(row["building_id"]): row for row in selection_records}
    inventory = image_inventory(repo_root / inputs["image_inventory_git_path"])
    image_dir = artifact_root / inputs["image_directory_relative_path"]
    selected_image_names = sorted(
        {
            str(view["camera"]["camera_name"])
            for row in selection_records
            for view in row["views"]
            if view["status"] == "SELECTED"
        }
    )
    image_bindings = []
    for name in selected_image_names:
        expected = inventory[name]
        image_bindings.append(
            {"basename": name, **verify_file(image_dir / name, expected["sha256"], f"raw image {name}", expected["bytes"])}
        )

    preview_rows = []
    roofline_status_counts: Counter[str] = Counter()
    for building in selected_buildings:
        building_id = str(building["building_id"])
        roof_edges, shell_diagnostic = outer_roof_shell_edges(
            references[building_id].roof_rings_xyz,
            float(config["roofline"]["edge_snap_tolerance_m"]),
        )
        payload, diagnostics = render_building(
            building,
            selection_by_id[building_id],
            roof_edges,
            shell_diagnostic,
            cameras,
            model,
            scene_reference,
            image_dir,
            render,
        )
        for diagnostic in diagnostics:
            status = diagnostic.get("roofline_status")
            if status is None:
                status = diagnostic.get("status", "UNKNOWN")
            roofline_status_counts[str(status)] += 1
        filename = f"{int(building['population_index']):03d}_{building_id}.png"
        write_new(partial / "preview/rows" / filename, payload)
        preview_rows.append(
            {
                "population_index": int(building["population_index"]),
                "building_id": building_id,
                "filename": filename,
                "output_sha256": hashlib.sha256(payload).hexdigest(),
                "roof_shell": shell_diagnostic,
                "panels": diagnostics,
                "keypoints_rendered": False,
                "scientific_verdict": None,
            }
        )
    write_new(partial / "preview/preview_manifest_v4.json", canonical_json_bytes({"schema": "jointbuildgs.p2.qualitative_row1_current_raw.preview_manifest.v4", "rows": preview_rows, "scientific_verdict": None}))
    write_new(partial / "preview/index.html", html_page(preview_rows))
    write_new(partial / "control/source_bindings_v4.json", canonical_json_bytes({"schema": "jointbuildgs.p2.qualitative_row1_current_raw.source_bindings.v4", **bindings, "selected_raw_images": image_bindings, "scientific_verdict": None}))
    summary = {
        "schema": "jointbuildgs.p2.qualitative_row1_current_raw.preview_summary.v4",
        "task_id": config["task_id"],
        "preview_building_count": len(preview_rows),
        "panel_slot_count": len(preview_rows) * len(config["selection"]["roles"]),
        "selected_panel_count": len(preview_rows) * len(config["selection"]["roles"]) - missing_role_count,
        "missing_panel_count": missing_role_count,
        "selected_unique_raw_image_count": len(selected_image_names),
        "top_status_counts": dict(sorted(top_status_counts.items())),
        "camera_rejection_reason_counts": dict(sorted(rejection_reason_counts.items())),
        "roofline_status_counts": dict(sorted(roofline_status_counts.items())),
        **sparse_summary,
        **observation_summary,
        "actual_point2d_used_for_internal_validation": True,
        "keypoints_rendered": False,
        "selection_frozen_before_roofline_projection": True,
        "full_199_render_authorized": False,
        "next_row_authorized": False,
        "scientific_verdict": None,
    }
    write_new(partial / "control/summary_v4.json", canonical_json_bytes(summary))
    config_size, config_sha = sha256_file(config_path)
    script_size, script_sha = sha256_file(Path(__file__))
    write_new(partial / "control/run_receipt_v4.json", canonical_json_bytes({"schema": "jointbuildgs.p2.qualitative_row1_current_raw.receipt.v4", "task_id": config["task_id"], "state": "complete", "generated_utc": datetime.now(timezone.utc).isoformat(), "repository_base_commit": source_commit, "runtime_image_id": image_id, "config": {"bytes": config_size, "sha256": config_sha}, "script": {"bytes": script_size, "sha256": script_sha}, "summary": summary, "scientific_verdict": None}))
    material = sorted(path for path in partial.rglob("*") if path.is_file())
    manifest = {"schema": "jointbuildgs.p2.qualitative_row1_current_raw.artifact_manifest.v4", "task_id": config["task_id"], "records": [file_record(path, partial) for path in material], "scientific_verdict": None}
    manifest["record_count"] = len(manifest["records"])
    write_new(partial / "control/artifact_manifest_v4.json", canonical_json_bytes(manifest))
    os.rename(partial, output_root)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--repo-root", type=Path, default=REPO)
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--image-id", required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.config, args.repo_root, args.artifact_root, args.output_root, args.source_commit, args.image_id), ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
