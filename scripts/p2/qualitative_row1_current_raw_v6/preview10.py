#!/usr/bin/env python3
"""Render representative ordered roof-boundary components for ten buildings."""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import html
import json
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
    file_record,
    image_inventory,
    png_bytes,
    sha256_file,
    stable_seed,
    verify_file,
    write_new,
)
from scripts.p2.qualitative_row1_current_raw_v4.preview10 import (
    candidate_record,
    load_actual_point2d_observations,
    public_candidate,
    scan_sparse_observations,
    separated,
)
from scripts.p2.qualitative_row1_current_raw_v5.preview10 import ordered_boundary_loops
from scripts.p2.utarget199_presentation_v5.render import load_references


REPO = Path(__file__).resolve().parents[3]
DEFAULT_CONFIG = REPO / "configs/p2/qualitative_row1_current_raw_v6/preview10_v1.json"


def loop_xy_area(loop: np.ndarray) -> float:
    points = np.asarray(loop, dtype=np.float64)
    if len(points) < 4:
        return 0.0
    return abs(
        float(
            np.sum(
                points[:-1, 0] * points[1:, 1]
                - points[1:, 0] * points[:-1, 1]
            )
        )
        / 2.0
    )


def component_records(loops: Sequence[np.ndarray]) -> tuple[list[dict[str, Any]], int]:
    if not loops:
        raise RuntimeError("roof boundary has no closed component")
    records = [
        {
            "component_id": index + 1,
            "xy_area_m2": loop_xy_area(loop),
            "source_edge_count": len(loop) - 1,
            "_loop": np.asarray(loop, dtype=np.float64),
        }
        for index, loop in enumerate(loops)
    ]
    representative = max(
        records,
        key=lambda row: (float(row["xy_area_m2"]), -int(row["component_id"])),
    )
    return records, int(representative["component_id"])


def project_components(
    components: Sequence[Mapping[str, Any]],
    camera: Any,
    model: tuple[int, int, np.ndarray],
    scene_reference: Mapping[str, Any],
) -> list[dict[str, Any]]:
    width, height, params = model
    projected = []
    for component in components:
        uv, front = projection.project(
            component["_loop"], camera, width, height, params, scene_reference
        )
        finite = np.isfinite(uv).all(axis=1)
        front_finite = front & finite
        inside_raw = (
            front_finite
            & (uv[:, 0] >= 0)
            & (uv[:, 0] < width)
            & (uv[:, 1] >= 0)
            & (uv[:, 1] < height)
        )
        bbox_area = (
            float(np.ptp(uv[:, 0]) * np.ptp(uv[:, 1]))
            if len(uv) and bool(np.all(finite))
            else 0.0
        )
        projected.append(
            {
                "component_id": int(component["component_id"]),
                "xy_area_m2": float(component["xy_area_m2"]),
                "source_edge_count": int(component["source_edge_count"]),
                "all_vertices_front_finite": bool(np.all(front_finite)),
                "all_vertices_inside_raw_image": bool(np.all(inside_raw)),
                "projected_bbox_area_px2": bbox_area,
                "_uv": uv,
            }
        )
    return projected


def enrich_candidate(
    candidate: dict[str, Any],
    components: Sequence[Mapping[str, Any]],
    representative_component_id: int,
    camera: Any,
    model: tuple[int, int, np.ndarray],
    scene_reference: Mapping[str, Any],
    representative_spec: Mapping[str, Any],
    crop_spec: Mapping[str, Any],
) -> dict[str, Any]:
    projected = project_components(components, camera, model, scene_reference)
    representative = next(
        row for row in projected if row["component_id"] == representative_component_id
    )
    representative_uv = representative["_uv"]
    roof_crop = None
    if len(representative_uv) and np.isfinite(representative_uv).all():
        roof_crop = crop_xyxy(
            representative_uv,
            model[0],
            model[1],
            float(crop_spec["margin_scale"]),
            float(crop_spec["margin_constant_px"]),
        )
    reasons = list(candidate["rejection_reasons"])
    if not representative["all_vertices_front_finite"]:
        reasons.append("REPRESENTATIVE_BOUNDARY_NOT_IN_FRONT")
    if not representative["all_vertices_inside_raw_image"]:
        reasons.append("REPRESENTATIVE_BOUNDARY_NOT_FULLY_INSIDE_RAW_IMAGE")
    if representative["projected_bbox_area_px2"] < float(
        representative_spec["minimum_projected_representative_bbox_area_px2"]
    ):
        reasons.append("PROJECTED_REPRESENTATIVE_BOUNDARY_TOO_SMALL")
    if roof_crop is None:
        reasons.append("REPRESENTATIVE_BOUNDARY_CROP_UNAVAILABLE")

    visible_ids = []
    if roof_crop is not None:
        x0, y0, x1, y1 = roof_crop
        for component in projected:
            uv = component["_uv"]
            inside_crop = (
                component["all_vertices_inside_raw_image"]
                and len(uv)
                and bool(
                    np.all(
                        (uv[:, 0] >= x0)
                        & (uv[:, 0] < x1)
                        & (uv[:, 1] >= y0)
                        & (uv[:, 1] < y1)
                    )
                )
            )
            component["all_vertices_inside_final_crop"] = inside_crop
            if inside_crop:
                visible_ids.append(int(component["component_id"]))
    else:
        for component in projected:
            component["all_vertices_inside_final_crop"] = False

    candidate.update(
        {
            "eligible": not reasons,
            "rejection_reasons": reasons,
            "crop_xyxy": roof_crop,
            "representative_component_id": representative_component_id,
            "representative_projected_bbox_area_px2": representative[
                "projected_bbox_area_px2"
            ],
            "source_component_count": len(components),
            "visible_component_ids_in_crop": visible_ids,
            "visible_component_count_in_crop": len(visible_ids),
            "_projected_components": projected,
        }
    )
    return candidate


def choose_views(
    building_id: str,
    candidates: Sequence[dict[str, Any]],
    selection: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], str, int, str]:
    eligible = [candidate for candidate in candidates if candidate["eligible"]]
    roles = [str(value) for value in selection["roles"]]
    seed = stable_seed(str(selection["random_seed_namespace"]), building_id)
    pool = [public_candidate(row) for row in sorted(eligible, key=lambda row: row["camera_name"])]
    pool_hash = hashlib.sha256(canonical_json_bytes(pool)).hexdigest()
    if not eligible:
        return [
            {"role": role, "status": "REPRESENTATIVE_ROOF_CAMERA_MISSING", "camera": None}
            for role in roles
        ], "REPRESENTATIVE_ROOF_CAMERA_MISSING", seed, pool_hash
    top = min(
        eligible,
        key=lambda row: (
            row["nadir_deg"],
            -row["representative_projected_bbox_area_px2"],
            -row["valid_actual_observation_count"],
            row["camera_name"],
        ),
    )
    top_status = (
        "NEAR_NADIR"
        if top["nadir_deg"] <= float(selection["near_nadir_max_deg"])
        else "BEST_AVAILABLE_NO_NEAR_NADIR"
    )
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
            chosen.append(candidate)
            random_views.append(candidate)
            if len(random_views) == len(roles) - 1:
                break
    views = [
        {"role": roles[0], "status": "SELECTED", "source": top_status, "camera": public_candidate(top)}
    ]
    for role, candidate in zip(roles[1:], random_views):
        views.append(
            {
                "role": role,
                "status": "SELECTED",
                "source": "DETERMINISTIC_POSE_DIVERSE_RANDOM_REPRESENTATIVE_COMPONENT",
                "camera": public_candidate(candidate),
            }
        )
    for role in roles[len(views) :]:
        views.append({"role": role, "status": "REPRESENTATIVE_ROOF_CAMERA_MISSING", "camera": None})
    return views, top_status, seed, pool_hash


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
    draw.text(
        (width / 2, height / 2),
        "REPRESENTATIVE ROOF CAMERA MISSING",
        font=bold,
        fill=(255, 156, 80),
        anchor="mm",
    )
    draw.text(
        (width / 2, height / 2 + 50),
        "No unvalidated camera substituted",
        font=regular,
        fill=tuple(render["muted_text_rgb"]),
        anchor="mm",
    )
    return cell


def render_panel(
    raw_crop: Image.Image,
    crop: Sequence[int],
    projected_components: Sequence[Mapping[str, Any]],
    visible_component_ids: Sequence[int],
    role: str,
    note: str,
    source_component_count: int,
    base_render: Mapping[str, Any],
    v6_render: Mapping[str, Any],
    regular: ImageFont.FreeTypeFont,
    bold: ImageFont.FreeTypeFont,
) -> Image.Image:
    cell_width = int(base_render["cell_width_px"])
    header = int(base_render["cell_header_height_px"])
    image_height = int(base_render["cell_image_height_px"])
    cell = Image.new("RGB", (cell_width, header + image_height), tuple(base_render["cell_background_rgb"]))
    fitted = ImageOps.contain(raw_crop.convert("RGB"), (cell_width, image_height), Image.Resampling.LANCZOS)
    offset_x = (cell_width - fitted.width) // 2
    offset_y = header + (image_height - fitted.height) // 2
    cell.paste(fitted, (offset_x, offset_y))
    scale_x = fitted.width / max(raw_crop.width, 1)
    scale_y = fitted.height / max(raw_crop.height, 1)
    draw = ImageDraw.Draw(cell)
    outline = tuple(map(int, base_render["roof_boundary_outline_rgb"]))
    color = tuple(map(int, base_render["roof_boundary_rgb"]))
    visible_set = set(map(int, visible_component_ids))
    for component in projected_components:
        if int(component["component_id"]) not in visible_set:
            continue
        points = [
            (
                offset_x + (float(point[0]) - crop[0]) * scale_x,
                offset_y + (float(point[1]) - crop[1]) * scale_y,
            )
            for point in component["_uv"]
        ]
        draw.line(points, fill=outline, width=int(v6_render["roof_boundary_outline_width_px_final"]), joint="curve")
        draw.line(points, fill=color, width=int(v6_render["roof_boundary_width_px_final"]), joint="curve")
    draw.text((24, 12), role, font=bold, fill=tuple(base_render["text_rgb"]))
    draw.text((24, 59), note, font=regular, fill=tuple(base_render["muted_text_rgb"]))
    status = f"VISIBLE LOOPS {len(visible_set)}/{source_component_count}"
    draw.text((cell_width - 24, 18), status, font=regular, fill=(255, 214, 10), anchor="ra")
    return cell


def render_building(
    building: Mapping[str, Any],
    selection_record: Mapping[str, Any],
    runtime_candidates: Mapping[str, Mapping[str, Any]],
    topology: Mapping[str, Any],
    components: Sequence[Mapping[str, Any]],
    representative_component_id: int,
    image_dir: Path,
    base_render: Mapping[str, Any],
    v6_render: Mapping[str, Any],
) -> tuple[bytes, list[dict[str, Any]]]:
    views = selection_record["views"]
    width = int(base_render["cell_width_px"]) * len(views)
    height = int(base_render["row_header_height_px"]) + int(base_render["cell_header_height_px"]) + int(base_render["cell_image_height_px"])
    canvas = Image.new("RGB", (width, height), tuple(base_render["background_rgb"]))
    regular = ImageFont.truetype(str(base_render["font_regular_path"]), 23)
    bold = ImageFont.truetype(str(base_render["font_bold_path"]), 34)
    title_font = ImageFont.truetype(str(base_render["font_bold_path"]), 38)
    draw = ImageDraw.Draw(canvas)
    title = "ROW 1 v6 — REPRESENTATIVE ROOF COMPONENT"
    if len(components) > 1:
        title += f" | SOURCE MULTIPART {len(components)}"
    draw.text((26, 18), title, font=title_font, fill=tuple(base_render["text_rgb"]))
    draw.text((width - 26, 25), f"{int(building['population_index']):03d}/199  {building['building_id']}", font=bold, fill=tuple(base_render["text_rgb"]), anchor="ra")
    diagnostics = []
    component_edge_counts = {
        int(component["component_id"]): int(component["source_edge_count"])
        for component in components
    }
    for column, view in enumerate(views):
        role = str(view["role"]).replace("_", " ")
        if view["status"] != "SELECTED":
            cell = missing_panel(role, base_render, regular, bold)
            diagnostics.append({"role": view["role"], "status": view["status"], **topology})
        else:
            camera_record = view["camera"]
            name = str(camera_record["camera_name"])
            runtime = runtime_candidates[name]
            crop = list(map(int, camera_record["crop_xyxy"]))
            visible_ids = list(map(int, camera_record["visible_component_ids_in_crop"]))
            if representative_component_id not in visible_ids:
                raise RuntimeError("selected camera does not render the representative component")
            for component in runtime["_projected_components"]:
                component_id = int(component["component_id"])
                if component_id in visible_ids and len(component["_uv"]) - 1 != component_edge_counts[component_id]:
                    raise RuntimeError("visible component changed source edge count")
            with Image.open(image_dir / name) as raw:
                raw_crop = raw.convert("RGB").crop(tuple(crop))
            display_role = role
            if view["role"] == "TOP" and view["source"] == "BEST_AVAILABLE_NO_NEAR_NADIR":
                display_role = "BEST AVAILABLE"
            note = f"{name} | nadir={float(camera_record['nadir_deg']):.1f}°"
            cell = render_panel(
                raw_crop,
                crop,
                runtime["_projected_components"],
                visible_ids,
                display_role,
                note,
                len(components),
                base_render,
                v6_render,
                regular,
                bold,
            )
            diagnostics.append(
                {
                    "role": view["role"],
                    "display_role": display_role,
                    "camera_name": name,
                    "selection_source": view["source"],
                    "representative_component_id": representative_component_id,
                    "visible_component_ids": visible_ids,
                    "visible_component_count": len(visible_ids),
                    "source_component_count": len(components),
                    "visible_source_edge_counts": {
                        str(component_id): component_edge_counts[component_id]
                        for component_id in visible_ids
                    },
                    "partial_component_rendered": False,
                    "stable_source_component_ids_preserved": True,
                    "internal_pose_validation": {
                        "valid_actual_observation_count": camera_record["valid_actual_observation_count"],
                        "median_reprojection_error_px": camera_record["median_reprojection_error_px"],
                        "p95_reprojection_error_px": camera_record["p95_reprojection_error_px"],
                    },
                    **topology,
                }
            )
        canvas.paste(cell, (column * int(base_render["cell_width_px"]), int(base_render["row_header_height_px"])))
    return png_bytes(canvas, base_render), diagnostics


def html_page(rows: Sequence[Mapping[str, Any]]) -> bytes:
    cards = "".join(
        f'<article><h2>{int(row["population_index"]):03d}/199 — {html.escape(str(row["building_id"]))}</h2>'
        f'<img src="rows/{html.escape(str(row["filename"]))}"></article>'
        for row in rows
    )
    return (
        "<!doctype html><html lang=ko><meta charset=utf-8><style>body{font-family:Arial,sans-serif;max-width:1960px;margin:auto;background:#111820;color:#f5f7fa}article{border-top:4px solid #607080;margin:40px 0}img{width:100%}</style><h1>Row 1 v6 representative roof component preview</h1>"
        + cards
        + "</html>"
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
        config.get("status") != "USER_APPROVED_REPRESENTATIVE_COMPONENT_PREVIEW10"
        or int(config["preview"]["building_count"]) != 10
        or config["preview"]["full_199_render_authorized"]
        or config["render"]["keypoints_rendered"]
        or config["visible_component"]["partial_component_rendering"]
    ):
        raise RuntimeError("only the approved representative-component ten-building preview is authorized")
    if output_root.exists() or output_root.with_name(output_root.name + ".partial").exists():
        raise RuntimeError(f"add-once output exists: {output_root}")
    partial = output_root.with_name(output_root.name + ".partial")
    partial.mkdir(parents=True)

    v5_path = repo_root / config["base_contract"]["git_path"]
    v5_helper_path = repo_root / config["implementation_dependency"]["git_path"]
    bindings = {
        "v5_base_contract": verify_file(v5_path, config["base_contract"]["sha256"], "v5 base contract", int(config["base_contract"]["bytes"])),
        "v5_implementation_dependency": verify_file(v5_helper_path, config["implementation_dependency"]["sha256"], "v5 implementation dependency", int(config["implementation_dependency"]["bytes"])),
    }
    v5 = json.loads(v5_path.read_text(encoding="utf-8"))
    v4_path = repo_root / v5["base_contract"]["git_path"]
    v4_helper_path = repo_root / v5["implementation_dependency"]["git_path"]
    bindings["v4_base_contract"] = verify_file(v4_path, v5["base_contract"]["sha256"], "v4 base contract", int(v5["base_contract"]["bytes"]))
    bindings["v4_implementation_dependency"] = verify_file(v4_helper_path, v5["implementation_dependency"]["sha256"], "v4 implementation dependency", int(v5["implementation_dependency"]["bytes"]))
    base = json.loads(v4_path.read_text(encoding="utf-8"))
    if base["preview"]["population_indices"] != config["preview"]["population_indices"] or base["preview"]["building_ids"] != config["preview"]["building_ids"]:
        raise RuntimeError("v6 ten-building membership differs from v4/v5")

    inputs = base["inputs"]
    common_root = artifact_root / inputs["common_manifest_relative_root"]
    building_path = common_root / inputs["building_manifest_relative_path"]
    bindings.update(
        {
            "building_manifest": verify_file(building_path, inputs["building_manifest_sha256"], "building manifest"),
            "image_inventory": verify_file(repo_root / inputs["image_inventory_git_path"], inputs["image_inventory_sha256"], "image inventory"),
            "exact_937_crosswalk": verify_file(repo_root / inputs["exact_937_crosswalk_git_path"], inputs["exact_937_crosswalk_sha256"], "exact crosswalk"),
            "cameras": verify_file(artifact_root / inputs["cameras_relative_path"], inputs["cameras_sha256"], "cameras"),
            "images": verify_file(artifact_root / inputs["images_relative_path"], inputs["images_sha256"], "images"),
            "points3D": verify_file(artifact_root / inputs["points3d_relative_path"], inputs["points3d_sha256"], "points3D", int(inputs["points3d_bytes"])),
            "scene_reference": verify_file(artifact_root / inputs["scene_reference_relative_path"], inputs["scene_reference_sha256"], "scene reference"),
            "v3_helper": verify_file(repo_root / inputs["v3_helper_git_path"], inputs["v3_helper_sha256"], "v3 helper", int(inputs["v3_helper_bytes"])),
        }
    )
    for index, relative in enumerate(inputs["lod2_relative_paths"]):
        bindings[f"lod2_{index + 1}"] = verify_file(artifact_root / relative, inputs["lod2_sha256"][index], f"LoD2 {index + 1}")
    base_render = base["render"]
    bindings["font_regular"] = verify_file(Path(base_render["font_regular_path"]), base_render["font_regular_sha256"], "regular font")
    bindings["font_bold"] = verify_file(Path(base_render["font_bold_path"]), base_render["font_bold_sha256"], "bold font")
    if PIL.__version__ != base_render["pillow_version"]:
        raise RuntimeError("Pillow version drifted")

    population = [json.loads(line) for line in building_path.read_text(encoding="utf-8").splitlines() if line]
    indices = [int(value) for value in config["preview"]["population_indices"]]
    building_ids = [str(value) for value in config["preview"]["building_ids"]]
    selected_buildings = []
    for index, expected_id in zip(indices, building_ids):
        building = population[index - 1]
        if str(building["building_id"]) != expected_id:
            raise RuntimeError("v6 ten-building membership drifted")
        selected_buildings.append(building)

    exact = json.loads((repo_root / inputs["exact_937_crosswalk_git_path"]).read_text(encoding="utf-8"))
    image_id_to_name = {int(row["colmap_image_id"]): str(row["basename"]) for row in exact["rows"]}
    scene_reference = json.loads((artifact_root / inputs["scene_reference_relative_path"]).read_text(encoding="utf-8"))
    model = projection.parse_cam_model(artifact_root / inputs["cameras_relative_path"])
    images_path = artifact_root / inputs["images_relative_path"]
    cameras = {camera.name: camera for camera in projection.parse_cameras(images_path, scene_reference)}
    support, sparse_summary = scan_sparse_observations(
        artifact_root / inputs["points3d_relative_path"], selected_buildings, set(image_id_to_name), base["frame"]["sparse_local_shift_xyz"], int(inputs["points3d_count"])
    )
    observed, observation_summary = load_actual_point2d_observations(images_path, support)
    references = load_references([artifact_root / path for path in inputs["lod2_relative_paths"]], building_ids)

    runtime_by_building: dict[str, dict[str, dict[str, Any]]] = {}
    topology_by_building: dict[str, dict[str, Any]] = {}
    components_by_building: dict[str, list[dict[str, Any]]] = {}
    representative_by_building: dict[str, int] = {}
    selection_records = []
    candidate_audit = []
    rejection_counts: Counter[str] = Counter()
    top_status_counts: Counter[str] = Counter()
    missing_count = 0
    for building in selected_buildings:
        building_id = str(building["building_id"])
        loops, topology = ordered_boundary_loops(
            references[building_id].roof_rings_xyz,
            float(v5["boundary_topology"]["edge_snap_tolerance_m"]),
            bool(v5["boundary_topology"]["require_even_boundary_graph_degree"]),
        )
        components, representative_component_id = component_records(loops)
        public_components = [public_candidate(component) for component in components]
        topology = {
            **topology,
            "component_xy_area_m2": {str(row["component_id"]): row["xy_area_m2"] for row in public_components},
            "component_source_edge_count": {str(row["component_id"]): row["source_edge_count"] for row in public_components},
            "representative_component_id": representative_component_id,
            "representative_selection_rule": config["representative_component"]["selection_rule"],
        }
        topology_by_building[building_id] = topology
        components_by_building[building_id] = components
        representative_by_building[building_id] = representative_component_id
        candidates = []
        for sparse_image_id, rows in support[building_id]["image_observations"].items():
            name = image_id_to_name[sparse_image_id]
            candidate = candidate_record(
                sparse_image_id, name, rows, observed, cameras[name], building, model, scene_reference, base["selection"], base["crop"]
            )
            enrich_candidate(
                candidate, components, representative_component_id, cameras[name], model, scene_reference, config["representative_component"], config["crop"]
            )
            candidates.append(candidate)
            for reason in candidate["rejection_reasons"]:
                rejection_counts[str(reason)] += 1
            candidate_audit.append(
                {"schema": "jointbuildgs.p2.qualitative_row1_current_raw.camera_candidate_audit.v6", "population_index": int(building["population_index"]), "building_id": building_id, **public_candidate(candidate), "scientific_verdict": None}
            )
        views, top_status, seed, pool_hash = choose_views(building_id, candidates, base["selection"])
        top_status_counts[top_status] += 1
        missing_count += sum(view["status"] != "SELECTED" for view in views)
        runtime_by_building[building_id] = {str(row["camera_name"]): row for row in candidates}
        selection_records.append(
            {
                "schema": "jointbuildgs.p2.qualitative_row1_current_raw.camera_selection.v6",
                "population_index": int(building["population_index"]),
                "building_id": building_id,
                "topology": topology,
                "track_confirmed_image_count": len(candidates),
                "representative_validated_image_count": sum(row["eligible"] for row in candidates),
                "eligible_candidate_pool_sha256": pool_hash,
                "seed_uint64": seed,
                "top_status": top_status,
                "views": views,
                "actual_point2d_used_for_internal_pose_validation": True,
                "representative_boundary_used_for_visibility_filter_and_crop": True,
                "other_components_may_be_absent": True,
                "partial_component_rendered": False,
                "keypoints_rendered": False,
                "scientific_verdict": None,
            }
        )

    write_new(partial / "selection/camera_candidate_audit_v6.jsonl", b"".join(canonical_json_bytes(row) for row in candidate_audit))
    write_new(partial / "selection/row1_camera_selection_v6.jsonl", b"".join(canonical_json_bytes(row) for row in selection_records))

    inventory = image_inventory(repo_root / inputs["image_inventory_git_path"])
    image_dir = artifact_root / inputs["image_directory_relative_path"]
    selected_names = sorted({str(view["camera"]["camera_name"]) for row in selection_records for view in row["views"] if view["status"] == "SELECTED"})
    image_bindings = []
    for name in selected_names:
        expected = inventory[name]
        image_bindings.append({"basename": name, **verify_file(image_dir / name, expected["sha256"], f"raw image {name}", expected["bytes"])})
    selection_by_id = {str(row["building_id"]): row for row in selection_records}
    preview_rows = []
    topology_counts: Counter[str] = Counter()
    visible_fraction_counts: Counter[str] = Counter()
    for building in selected_buildings:
        building_id = str(building["building_id"])
        topology = topology_by_building[building_id]
        topology_counts[str(topology["topology_status"])] += 1
        payload, diagnostics = render_building(
            building,
            selection_by_id[building_id],
            runtime_by_building[building_id],
            topology,
            components_by_building[building_id],
            representative_by_building[building_id],
            image_dir,
            base_render,
            config["render"],
        )
        for panel_record in diagnostics:
            if panel_record.get("status") is None:
                visible_fraction_counts[f"{panel_record['visible_component_count']}/{panel_record['source_component_count']}"] += 1
        filename = f"{int(building['population_index']):03d}_{building_id}.png"
        write_new(partial / "preview/rows" / filename, payload)
        preview_rows.append(
            {"population_index": int(building["population_index"]), "building_id": building_id, "filename": filename, "output_sha256": hashlib.sha256(payload).hexdigest(), "topology": topology, "panels": diagnostics, "keypoints_rendered": False, "scientific_verdict": None}
        )
    write_new(partial / "preview/preview_manifest_v6.json", canonical_json_bytes({"schema": "jointbuildgs.p2.qualitative_row1_current_raw.preview_manifest.v6", "rows": preview_rows, "scientific_verdict": None}))
    write_new(partial / "preview/index.html", html_page(preview_rows))
    write_new(partial / "control/source_bindings_v6.json", canonical_json_bytes({"schema": "jointbuildgs.p2.qualitative_row1_current_raw.source_bindings.v6", **bindings, "selected_raw_images": image_bindings, "scientific_verdict": None}))
    summary = {
        "schema": "jointbuildgs.p2.qualitative_row1_current_raw.preview_summary.v6",
        "task_id": config["task_id"],
        "preview_building_count": len(preview_rows),
        "panel_slot_count": len(preview_rows) * len(base["selection"]["roles"]),
        "selected_panel_count": len(preview_rows) * len(base["selection"]["roles"]) - missing_count,
        "missing_panel_count": missing_count,
        "selected_unique_raw_image_count": len(selected_names),
        "top_status_counts": dict(sorted(top_status_counts.items())),
        "topology_status_counts": dict(sorted(topology_counts.items())),
        "visible_component_fraction_counts": dict(sorted(visible_fraction_counts.items())),
        "camera_rejection_reason_counts": dict(sorted(rejection_counts.items())),
        **sparse_summary,
        **observation_summary,
        "all_selected_panels_include_complete_representative_component": True,
        "partial_component_rendered": False,
        "stable_source_component_ids_preserved": True,
        "roofline_drawn_after_final_resize": True,
        "keypoints_rendered": False,
        "full_199_render_authorized": False,
        "next_row_authorized": False,
        "scientific_verdict": None,
    }
    write_new(partial / "control/summary_v6.json", canonical_json_bytes(summary))
    config_size, config_sha = sha256_file(config_path)
    script_size, script_sha = sha256_file(Path(__file__))
    write_new(partial / "control/run_receipt_v6.json", canonical_json_bytes({"schema": "jointbuildgs.p2.qualitative_row1_current_raw.receipt.v6", "task_id": config["task_id"], "state": "complete", "generated_utc": datetime.now(timezone.utc).isoformat(), "repository_base_commit": source_commit, "runtime_image_id": image_id, "config": {"bytes": config_size, "sha256": config_sha}, "script": {"bytes": script_size, "sha256": script_sha}, "summary": summary, "scientific_verdict": None}))
    material = sorted(path for path in partial.rglob("*") if path.is_file())
    manifest = {"schema": "jointbuildgs.p2.qualitative_row1_current_raw.artifact_manifest.v6", "task_id": config["task_id"], "records": [file_record(path, partial) for path in material], "scientific_verdict": None}
    manifest["record_count"] = len(manifest["records"])
    write_new(partial / "control/artifact_manifest_v6.json", canonical_json_bytes(manifest))
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
