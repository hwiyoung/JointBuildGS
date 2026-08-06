#!/usr/bin/env python3
"""Project ordered closed 3D roof-boundary loops for ten review buildings."""

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
from scripts.p2.utarget199_presentation_v5.render import load_references


REPO = Path(__file__).resolve().parents[3]
DEFAULT_CONFIG = REPO / "configs/p2/qualitative_row1_current_raw_v5/preview10_v1.json"


def ordered_boundary_loops(
    rings: Sequence[np.ndarray], tolerance: float, require_even_degree: bool = True
) -> tuple[list[np.ndarray], dict[str, Any]]:
    """Create deterministic closed Eulerian walks over all unmatched shell edges."""
    counts: Counter[tuple[tuple[int, int, int], tuple[int, int, int]]] = Counter()
    values: dict[
        tuple[tuple[int, int, int], tuple[int, int, int]], tuple[np.ndarray, np.ndarray]
    ] = {}
    node_values: defaultdict[tuple[int, int, int], list[np.ndarray]] = defaultdict(list)

    def node(point: np.ndarray) -> tuple[int, int, int]:
        return tuple(int(round(float(value) / tolerance)) for value in point)

    input_edge_count = 0
    for raw_ring in rings:
        ring = np.asarray(raw_ring, dtype=np.float64)
        if len(ring) < 2:
            continue
        pairs = [(ring[index], ring[index + 1]) for index in range(len(ring) - 1)]
        if not np.allclose(ring[0], ring[-1], atol=tolerance):
            pairs.append((ring[-1], ring[0]))
        for start, end in pairs:
            if np.linalg.norm(end - start) <= tolerance:
                continue
            input_edge_count += 1
            first, second = node(start), node(end)
            key = tuple(sorted((first, second)))
            counts[key] += 1
            values.setdefault(key, (start.copy(), end.copy()))
            node_values[first].append(start.copy())
            node_values[second].append(end.copy())
    boundary_keys = sorted(key for key, count in counts.items() if count == 1)
    edge_nodes = {index: key for index, key in enumerate(boundary_keys)}
    adjacency: defaultdict[tuple[int, int, int], list[tuple[int, tuple[int, int, int]]]] = defaultdict(list)
    for edge_id, (first, second) in edge_nodes.items():
        adjacency[first].append((edge_id, second))
        adjacency[second].append((edge_id, first))
    degree_histogram = Counter(len(neighbours) for neighbours in adjacency.values())
    odd_nodes = sorted(node_id for node_id, neighbours in adjacency.items() if len(neighbours) % 2)
    if require_even_degree and odd_nodes:
        raise RuntimeError(f"roof boundary graph has {len(odd_nodes)} odd-degree nodes")
    representative = {
        node_id: np.mean(np.asarray(points, dtype=np.float64), axis=0)
        for node_id, points in node_values.items()
    }
    for neighbours in adjacency.values():
        neighbours.sort(key=lambda item: (item[0], item[1]), reverse=True)
    unused = set(edge_nodes)
    loops: list[np.ndarray] = []
    used_edge_ids: list[int] = []
    while unused:
        start_edge = min(unused)
        start = min(edge_nodes[start_edge])
        stack_nodes = [start]
        stack_edges: list[int] = []
        circuit_nodes: list[tuple[int, int, int]] = []
        circuit_edges: list[int] = []
        while stack_nodes:
            current = stack_nodes[-1]
            while adjacency[current] and adjacency[current][-1][0] not in unused:
                adjacency[current].pop()
            if adjacency[current]:
                edge_id, neighbour = adjacency[current].pop()
                if edge_id not in unused:
                    continue
                unused.remove(edge_id)
                stack_nodes.append(neighbour)
                stack_edges.append(edge_id)
            else:
                circuit_nodes.append(stack_nodes.pop())
                if stack_edges:
                    circuit_edges.append(stack_edges.pop())
        circuit_nodes.reverse()
        circuit_edges.reverse()
        if len(circuit_nodes) < 2 or circuit_nodes[0] != circuit_nodes[-1]:
            raise RuntimeError("roof boundary walk is not closed")
        if len(circuit_edges) != len(circuit_nodes) - 1:
            raise RuntimeError("roof boundary edge and vertex counts disagree")
        loops.append(np.asarray([representative[node_id] for node_id in circuit_nodes], dtype=np.float64))
        used_edge_ids.extend(circuit_edges)
    if sorted(used_edge_ids) != sorted(edge_nodes):
        raise RuntimeError("ordered roof loops did not consume every exterior edge exactly once")
    topology = "SIMPLE_CLOSED_LOOPS" if set(degree_histogram) <= {2} else "TOUCHING_EULERIAN_BOUNDARY"
    return loops, {
        "input_roof_surface_ring_count": len(rings),
        "input_roof_surface_edge_count": input_edge_count,
        "boundary_edge_count": len(boundary_keys),
        "boundary_node_count": len(adjacency),
        "boundary_loop_count": len(loops),
        "degree_histogram": {str(key): value for key, value in sorted(degree_histogram.items())},
        "topology_status": topology,
        "all_boundary_edges_consumed_once": True,
    }


def project_loops(
    loops: Sequence[np.ndarray],
    camera: Any,
    model: tuple[int, int, np.ndarray],
    scene_reference: Mapping[str, Any],
) -> tuple[list[np.ndarray], dict[str, Any]]:
    width, height, params = model
    projected_loops: list[np.ndarray] = []
    all_inside = True
    all_front = True
    flattened: list[np.ndarray] = []
    for loop in loops:
        uv, front = projection.project(loop, camera, width, height, params, scene_reference)
        finite_front = front & np.isfinite(uv).all(axis=1)
        inside = finite_front & (uv[:, 0] >= 0) & (uv[:, 0] < width) & (uv[:, 1] >= 0) & (uv[:, 1] < height)
        all_front = all_front and bool(np.all(finite_front))
        all_inside = all_inside and bool(np.all(inside))
        projected_loops.append(uv)
        if len(uv):
            flattened.append(uv)
    all_uv = np.vstack(flattened) if flattened else np.empty((0, 2), dtype=np.float64)
    area = float(np.ptp(all_uv[:, 0]) * np.ptp(all_uv[:, 1])) if len(all_uv) else 0.0
    return projected_loops, {
        "all_boundary_vertices_front_finite": all_front,
        "all_boundary_vertices_inside_raw_image": all_inside,
        "projected_roof_bbox_area_px2": area,
        "projected_boundary_vertex_count": int(len(all_uv)),
    }


def enrich_candidate(
    candidate: dict[str, Any],
    loops: Sequence[np.ndarray],
    camera: Any,
    model: tuple[int, int, np.ndarray],
    scene_reference: Mapping[str, Any],
    visibility: Mapping[str, Any],
    crop_spec: Mapping[str, Any],
) -> dict[str, Any]:
    projected_loops, diagnostic = project_loops(loops, camera, model, scene_reference)
    all_uv = np.vstack(projected_loops) if projected_loops else np.empty((0, 2), dtype=np.float64)
    roof_crop = None
    if len(all_uv) and np.isfinite(all_uv).all():
        roof_crop = crop_xyxy(
            all_uv,
            model[0],
            model[1],
            float(crop_spec["margin_scale"]),
            float(crop_spec["margin_constant_px"]),
        )
    reasons = list(candidate["rejection_reasons"])
    if not diagnostic["all_boundary_vertices_front_finite"]:
        reasons.append("ROOF_BOUNDARY_NOT_IN_FRONT")
    if not diagnostic["all_boundary_vertices_inside_raw_image"]:
        reasons.append("ROOF_BOUNDARY_NOT_FULLY_INSIDE_RAW_IMAGE")
    if diagnostic["projected_roof_bbox_area_px2"] < float(visibility["minimum_projected_roof_bbox_area_px2"]):
        reasons.append("PROJECTED_ROOF_TOO_SMALL")
    if roof_crop is None:
        reasons.append("ROOF_BOUNDARY_CROP_UNAVAILABLE")
    candidate.update(
        {
            "eligible": not reasons,
            "rejection_reasons": reasons,
            "crop_xyxy": roof_crop,
            **diagnostic,
            "_projected_roof_loops": projected_loops,
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
            {"role": role, "status": "FULL_ROOF_LOOP_CAMERA_MISSING", "camera": None}
            for role in roles
        ], "FULL_ROOF_LOOP_CAMERA_MISSING", seed, pool_hash
    top = min(
        eligible,
        key=lambda row: (
            row["nadir_deg"],
            -row["projected_roof_bbox_area_px2"],
            -row["valid_actual_observation_count"],
            row["camera_name"],
        ),
    )
    top_status = (
        "NEAR_NADIR" if top["nadir_deg"] <= float(selection["near_nadir_max_deg"])
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
                "source": "DETERMINISTIC_POSE_DIVERSE_RANDOM_FULL_ROOF_LOOP",
                "camera": public_candidate(candidate),
            }
        )
    for role in roles[len(views) :]:
        views.append({"role": role, "status": "FULL_ROOF_LOOP_CAMERA_MISSING", "camera": None})
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
    draw.text((width / 2, height / 2), "FULL ROOF LOOP CAMERA MISSING", font=bold, fill=(255, 156, 80), anchor="mm")
    draw.text((width / 2, height / 2 + 50), "No partial roofline camera substituted", font=regular, fill=tuple(render["muted_text_rgb"]), anchor="mm")
    return cell


def render_panel(
    raw_crop: Image.Image,
    crop: Sequence[int],
    projected_loops: Sequence[np.ndarray],
    role: str,
    note: str,
    loop_count: int,
    base_render: Mapping[str, Any],
    v5_render: Mapping[str, Any],
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
    for uv in projected_loops:
        points = [
            (
                offset_x + (float(point[0]) - crop[0]) * scale_x,
                offset_y + (float(point[1]) - crop[1]) * scale_y,
            )
            for point in uv
        ]
        draw.line(points, fill=outline, width=int(v5_render["roof_boundary_outline_width_px_final"]), joint="curve")
        draw.line(points, fill=color, width=int(v5_render["roof_boundary_width_px_final"]), joint="curve")
    draw.text((24, 12), role, font=bold, fill=tuple(base_render["text_rgb"]))
    draw.text((24, 59), note, font=regular, fill=tuple(base_render["muted_text_rgb"]))
    status = "ROOFLINE PROJECTED" if loop_count == 1 else f"ROOFLINE PROJECTED | {loop_count} LOOPS"
    draw.text((cell_width - 24, 18), status, font=regular, fill=(255, 214, 10), anchor="ra")
    return cell


def render_building(
    building: Mapping[str, Any],
    selection_record: Mapping[str, Any],
    runtime_candidates: Mapping[str, Mapping[str, Any]],
    topology: Mapping[str, Any],
    image_dir: Path,
    base_render: Mapping[str, Any],
    v5_render: Mapping[str, Any],
) -> tuple[bytes, list[dict[str, Any]]]:
    views = selection_record["views"]
    width = int(base_render["cell_width_px"]) * len(views)
    height = int(base_render["row_header_height_px"]) + int(base_render["cell_header_height_px"]) + int(base_render["cell_image_height_px"])
    canvas = Image.new("RGB", (width, height), tuple(base_render["background_rgb"]))
    regular = ImageFont.truetype(str(base_render["font_regular_path"]), 23)
    bold = ImageFont.truetype(str(base_render["font_bold_path"]), 34)
    title_font = ImageFont.truetype(str(base_render["font_bold_path"]), 38)
    draw = ImageDraw.Draw(canvas)
    title = "ROW 1 v5 — ORDERED 3D ROOF POLYGON BOUNDARY"
    if int(topology["boundary_loop_count"]) > 1:
        title += f" | MULTIPART {int(topology['boundary_loop_count'])}"
    draw.text((26, 18), title, font=title_font, fill=tuple(base_render["text_rgb"]))
    draw.text((width - 26, 25), f"{int(building['population_index']):03d}/199  {building['building_id']}", font=bold, fill=tuple(base_render["text_rgb"]), anchor="ra")
    diagnostics = []
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
            with Image.open(image_dir / name) as raw:
                raw_crop = raw.convert("RGB").crop(tuple(crop))
            display_role = role
            if view["role"] == "TOP" and view["source"] == "BEST_AVAILABLE_NO_NEAR_NADIR":
                display_role = "BEST AVAILABLE"
            note = f"{name} | nadir={float(camera_record['nadir_deg']):.1f}°"
            cell = render_panel(
                raw_crop,
                crop,
                runtime["_projected_roof_loops"],
                display_role,
                note,
                int(topology["boundary_loop_count"]),
                base_render,
                v5_render,
                regular,
                bold,
            )
            projected_edge_count = sum(len(loop) - 1 for loop in runtime["_projected_roof_loops"])
            if projected_edge_count != int(topology["boundary_edge_count"]):
                raise RuntimeError("selected camera changed roof boundary topology")
            diagnostics.append(
                {
                    "role": view["role"],
                    "display_role": display_role,
                    "camera_name": name,
                    "selection_source": view["source"],
                    "roofline_status": "FULL_ORDERED_LOOP_PROJECTED",
                    "projected_boundary_edge_count": projected_edge_count,
                    "projected_boundary_loop_count": len(runtime["_projected_roof_loops"]),
                    "same_topology_as_source": True,
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
        "<!doctype html><html lang=ko><meta charset=utf-8><style>body{font-family:Arial,sans-serif;max-width:1960px;margin:auto;background:#111820;color:#f5f7fa}article{border-top:4px solid #607080;margin:40px 0}img{width:100%}</style><h1>Row 1 v5 ordered roof polygon boundary preview</h1>" + cards + "</html>"
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
        config.get("status") != "USER_APPROVED_ORDERED_POLYGON_LOOP_PREVIEW10"
        or int(config["preview"]["building_count"]) != 10
        or config["preview"]["full_199_render_authorized"]
        or config["render"]["keypoints_rendered"]
    ):
        raise RuntimeError("only the approved ordered-loop ten-building preview is authorized")
    if output_root.exists() or output_root.with_name(output_root.name + ".partial").exists():
        raise RuntimeError(f"add-once output exists: {output_root}")
    partial = output_root.with_name(output_root.name + ".partial")
    partial.mkdir(parents=True)
    base_path = repo_root / config["base_contract"]["git_path"]
    helper_path = repo_root / config["implementation_dependency"]["git_path"]
    base_binding = verify_file(base_path, config["base_contract"]["sha256"], "v4 base contract", int(config["base_contract"]["bytes"]))
    helper_binding = verify_file(helper_path, config["implementation_dependency"]["sha256"], "v4 implementation dependency", int(config["implementation_dependency"]["bytes"]))
    base = json.loads(base_path.read_text(encoding="utf-8"))
    if base["preview"]["population_indices"] != config["preview"]["population_indices"] or base["preview"]["building_ids"] != config["preview"]["building_ids"]:
        raise RuntimeError("v5 ten-building membership differs from v4")
    inputs = base["inputs"]
    common_root = artifact_root / inputs["common_manifest_relative_root"]
    building_path = common_root / inputs["building_manifest_relative_path"]
    bindings = {
        "v4_base_contract": base_binding,
        "v4_implementation_dependency": helper_binding,
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
            raise RuntimeError("v5 ten-building membership drifted")
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
    selection_records = []
    candidate_audit = []
    rejection_counts: Counter[str] = Counter()
    top_status_counts: Counter[str] = Counter()
    missing_count = 0
    for building in selected_buildings:
        building_id = str(building["building_id"])
        loops, topology = ordered_boundary_loops(
            references[building_id].roof_rings_xyz,
            float(config["boundary_topology"]["edge_snap_tolerance_m"]),
            bool(config["boundary_topology"]["require_even_boundary_graph_degree"]),
        )
        topology_by_building[building_id] = topology
        candidates = []
        for sparse_image_id, rows in support[building_id]["image_observations"].items():
            name = image_id_to_name[sparse_image_id]
            candidate = candidate_record(
                sparse_image_id, name, rows, observed, cameras[name], building, model, scene_reference, base["selection"], base["crop"]
            )
            enrich_candidate(candidate, loops, cameras[name], model, scene_reference, config["camera_visibility"], config["crop"])
            candidates.append(candidate)
            for reason in candidate["rejection_reasons"]:
                rejection_counts[str(reason)] += 1
            candidate_audit.append({"schema": "jointbuildgs.p2.qualitative_row1_current_raw.camera_candidate_audit.v5", "population_index": int(building["population_index"]), "building_id": building_id, **public_candidate(candidate), "scientific_verdict": None})
        views, top_status, seed, pool_hash = choose_views(building_id, candidates, base["selection"])
        top_status_counts[top_status] += 1
        missing_count += sum(view["status"] != "SELECTED" for view in views)
        runtime_by_building[building_id] = {str(row["camera_name"]): row for row in candidates}
        selection_records.append({"schema": "jointbuildgs.p2.qualitative_row1_current_raw.camera_selection.v5", "population_index": int(building["population_index"]), "building_id": building_id, "topology": topology, "track_confirmed_image_count": len(candidates), "full_loop_validated_image_count": sum(row["eligible"] for row in candidates), "eligible_candidate_pool_sha256": pool_hash, "seed_uint64": seed, "top_status": top_status, "views": views, "actual_point2d_used_for_internal_pose_validation": True, "roof_boundary_used_for_full_visibility_filter_and_crop": True, "keypoints_rendered": False, "scientific_verdict": None})
    write_new(partial / "selection/camera_candidate_audit_v5.jsonl", b"".join(canonical_json_bytes(row) for row in candidate_audit))
    write_new(partial / "selection/row1_camera_selection_v5.jsonl", b"".join(canonical_json_bytes(row) for row in selection_records))

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
    for building in selected_buildings:
        building_id = str(building["building_id"])
        topology = topology_by_building[building_id]
        topology_counts[str(topology["topology_status"])] += 1
        payload, diagnostics = render_building(building, selection_by_id[building_id], runtime_by_building[building_id], topology, image_dir, base_render, config["render"])
        filename = f"{int(building['population_index']):03d}_{building_id}.png"
        write_new(partial / "preview/rows" / filename, payload)
        preview_rows.append({"population_index": int(building["population_index"]), "building_id": building_id, "filename": filename, "output_sha256": hashlib.sha256(payload).hexdigest(), "topology": topology, "panels": diagnostics, "keypoints_rendered": False, "scientific_verdict": None})
    write_new(partial / "preview/preview_manifest_v5.json", canonical_json_bytes({"schema": "jointbuildgs.p2.qualitative_row1_current_raw.preview_manifest.v5", "rows": preview_rows, "scientific_verdict": None}))
    write_new(partial / "preview/index.html", html_page(preview_rows))
    write_new(partial / "control/source_bindings_v5.json", canonical_json_bytes({"schema": "jointbuildgs.p2.qualitative_row1_current_raw.source_bindings.v5", **bindings, "selected_raw_images": image_bindings, "scientific_verdict": None}))
    summary = {"schema": "jointbuildgs.p2.qualitative_row1_current_raw.preview_summary.v5", "task_id": config["task_id"], "preview_building_count": len(preview_rows), "panel_slot_count": len(preview_rows) * len(base["selection"]["roles"]), "selected_panel_count": len(preview_rows) * len(base["selection"]["roles"]) - missing_count, "missing_panel_count": missing_count, "selected_unique_raw_image_count": len(selected_names), "top_status_counts": dict(sorted(top_status_counts.items())), "topology_status_counts": dict(sorted(topology_counts.items())), "camera_rejection_reason_counts": dict(sorted(rejection_counts.items())), **sparse_summary, **observation_summary, "all_selected_panels_full_ordered_loops": True, "same_source_edge_ids_required_across_cameras": True, "roofline_drawn_after_final_resize": True, "keypoints_rendered": False, "full_199_render_authorized": False, "next_row_authorized": False, "scientific_verdict": None}
    write_new(partial / "control/summary_v5.json", canonical_json_bytes(summary))
    config_size, config_sha = sha256_file(config_path)
    script_size, script_sha = sha256_file(Path(__file__))
    write_new(partial / "control/run_receipt_v5.json", canonical_json_bytes({"schema": "jointbuildgs.p2.qualitative_row1_current_raw.receipt.v5", "task_id": config["task_id"], "state": "complete", "generated_utc": datetime.now(timezone.utc).isoformat(), "repository_base_commit": source_commit, "runtime_image_id": image_id, "config": {"bytes": config_size, "sha256": config_sha}, "script": {"bytes": script_size, "sha256": script_sha}, "summary": summary, "scientific_verdict": None}))
    material = sorted(path for path in partial.rglob("*") if path.is_file())
    manifest = {"schema": "jointbuildgs.p2.qualitative_row1_current_raw.artifact_manifest.v5", "task_id": config["task_id"], "records": [file_record(path, partial) for path in material], "scientific_verdict": None}
    manifest["record_count"] = len(manifest["records"])
    write_new(partial / "control/artifact_manifest_v5.json", canonical_json_bytes(manifest))
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
