#!/usr/bin/env python3
"""Freeze sparse-track-confirmed row-1 cameras and render five review cases."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
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
from scripts.p2.utarget199_presentation_v5.render import load_references


REPO = Path(__file__).resolve().parents[3]
DEFAULT_CONFIG = REPO / "configs/p2/qualitative_row1_current_raw_v3/preview_v1.json"


def canonical_json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()


def sha256_file(path: Path) -> tuple[int, str]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
            size += len(chunk)
    return size, digest.hexdigest()


def verify_file(path: Path, digest: str, label: str, size: int | None = None) -> dict[str, Any]:
    actual_size, actual_digest = sha256_file(path)
    if actual_digest != digest or (size is not None and actual_size != size):
        raise RuntimeError(f"{label} binding drifted")
    return {
        "path": str(path),
        "bytes": actual_size,
        "sha256": actual_digest,
        "verification": "sha256_rehash",
    }


def write_new(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(data)


def stable_seed(namespace: str, building_id: str) -> int:
    digest = hashlib.sha256(namespace.encode() + b"\0" + building_id.encode()).digest()
    return int.from_bytes(digest[:8], "big")


def deterministic_sample(names: Sequence[str], count: int, seed: int) -> list[str]:
    ordered = sorted(set(map(str, names)))
    return random.Random(seed).sample(ordered, min(len(ordered), int(count)))


def image_inventory(path: Path) -> dict[str, dict[str, Any]]:
    with path.open(newline="", encoding="utf-8") as stream:
        return {
            str(row["basename"]): {
                "bytes": int(row["uncompressed_bytes"]),
                "sha256": str(row["sha256"]),
            }
            for row in csv.DictReader(stream)
        }


def sparse_building_grid(
    buildings: Sequence[Mapping[str, Any]], cell_size: float = 10.0
) -> dict[tuple[int, int], list[str]]:
    grid: defaultdict[tuple[int, int], list[str]] = defaultdict(list)
    for building in buildings:
        building_id = str(building["building_id"])
        min_x, min_y, max_x, max_y = map(float, building["building_bbox_xy"])
        for ix in range(math.floor(min_x / cell_size), math.floor(max_x / cell_size) + 1):
            for iy in range(math.floor(min_y / cell_size), math.floor(max_y / cell_size) + 1):
                grid[(ix, iy)].append(building_id)
    return dict(grid)


def scan_sparse_tracks(
    path: Path,
    buildings: Sequence[Mapping[str, Any]],
    exact_image_ids: set[int],
    shift: Sequence[float],
    expected_point_count: int,
    cell_size: float = 10.0,
) -> tuple[dict[str, dict[str, Any]], dict[str, int]]:
    """Assign sparse 3D points to frozen building prisms and retain exact-937 tracks."""
    shift_xyz = np.asarray(shift, dtype=np.float64)
    by_id = {str(row["building_id"]): row for row in buildings}
    grid = sparse_building_grid(buildings, cell_size)
    support: dict[str, dict[str, Any]] = {
        building_id: {
            "xy_point_count_all_z": 0,
            "xyz_point_count": 0,
            "image_points": defaultdict(list),
        }
        for building_id in by_id
    }
    scanned = 0
    assigned_xyz = 0
    retained_observations = 0
    with path.open("r", encoding="utf-8") as stream:
        for line in stream:
            if not line or line[0] == "#":
                continue
            fields = line.split()
            if len(fields) < 8 or (len(fields) - 8) % 2:
                raise RuntimeError("COLMAP sparse point row is malformed")
            scanned += 1
            xyz = np.asarray(fields[1:4], dtype=np.float64) + shift_xyz
            key = (math.floor(float(xyz[0]) / cell_size), math.floor(float(xyz[1]) / cell_size))
            candidate_ids = grid.get(key, ())
            if not candidate_ids:
                continue
            track_ids = {int(fields[index]) for index in range(8, len(fields), 2)} & exact_image_ids
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
                assigned_xyz += 1
                for image_id in track_ids:
                    entry["image_points"][image_id].append(xyz.copy())
                    retained_observations += 1
    if scanned != int(expected_point_count):
        raise RuntimeError(f"sparse point count drifted: {scanned} != {expected_point_count}")
    for entry in support.values():
        entry["image_points"] = {
            int(image_id): np.asarray(points, dtype=np.float64)
            for image_id, points in entry["image_points"].items()
        }
    return support, {
        "sparse_points_scanned": scanned,
        "building_prism_point_assignments": assigned_xyz,
        "exact_937_track_observations_retained": retained_observations,
        "spatial_grid_cell_size_m": int(cell_size),
    }


def track_candidate(
    image_id: int,
    image_name: str,
    points: np.ndarray,
    camera: Any,
    building: Mapping[str, Any],
    model: tuple[int, int, np.ndarray],
    scene_reference: Mapping[str, Any],
    selection: Mapping[str, Any],
    crop_spec: Mapping[str, Any],
) -> dict[str, Any]:
    width, height, params = model
    uv, front = projection.project(
        points, camera, width, height, params, scene_reference, input_datum="ellipsoidal"
    )
    finite = front & np.isfinite(uv).all(axis=1)
    inside = finite & (uv[:, 0] >= 0) & (uv[:, 0] < width) & (uv[:, 1] >= 0) & (uv[:, 1] < height)
    inside_uv = uv[inside]
    coverage = float(np.mean(inside)) if len(inside) else 0.0
    spread_xy = np.ptp(inside_uv, axis=0) if len(inside_uv) else np.zeros(2, dtype=np.float64)
    spread_diagonal = float(np.linalg.norm(spread_xy))
    spread_area = float(spread_xy[0] * spread_xy[1])
    center = np.asarray(
        [
            building["principal_frame"]["center_xy"][0],
            building["principal_frame"]["center_xy"][1],
            float(np.mean(building["z_range_ellipsoidal_m"])),
        ],
        dtype=np.float64,
    )
    vector = np.asarray(camera.center, dtype=np.float64) - center
    vector /= max(float(np.linalg.norm(vector)), 1e-12)
    nadir_deg = math.degrees(math.acos(float(np.clip(vector[2], -1.0, 1.0))))
    frozen_crop = crop_xyxy(
        inside_uv,
        width,
        height,
        float(crop_spec["track_margin_scale"]),
        float(crop_spec["track_margin_constant_px"]),
    )
    eligible = (
        len(points) >= int(selection["minimum_track_point_count"])
        and coverage >= float(selection["minimum_in_frame_track_fraction"])
        and spread_diagonal >= float(selection["minimum_track_spread_diagonal_px"])
        and frozen_crop is not None
    )
    return {
        "image_id": int(image_id),
        "camera_name": image_name,
        "track_point_count": int(len(points)),
        "in_frame_track_point_count": int(inside.sum()),
        "in_frame_track_fraction": coverage,
        "track_spread_diagonal_px": spread_diagonal,
        "track_spread_bbox_area_px2": spread_area,
        "nadir_deg": nadir_deg,
        "crop_xyxy": frozen_crop,
        "eligible": bool(eligible),
        "_inside_uv": inside_uv,
    }


def public_candidate(candidate: Mapping[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in candidate.items() if not str(key).startswith("_")}


def choose_views(
    building_id: str,
    candidates: Sequence[dict[str, Any]],
    selection: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], str, int, str]:
    eligible = [row for row in candidates if row["eligible"]]
    seed = stable_seed(str(selection["random_seed_namespace"]), building_id)
    roles = [str(value) for value in selection["roles"]]
    if not eligible:
        return [
            {"role": role, "status": "SPARSE_SUPPORT_MISSING", "camera": None}
            for role in roles
        ], "SPARSE_SUPPORT_MISSING", seed, hashlib.sha256(canonical_json_bytes([])).hexdigest()
    near = [row for row in eligible if row["nadir_deg"] <= float(selection["near_nadir_max_deg"])]
    if near:
        top = min(
            near,
            key=lambda row: (
                row["nadir_deg"],
                -row["track_point_count"],
                -row["track_spread_diagonal_px"],
                row["camera_name"],
            ),
        )
        top_status = "NEAR_NADIR_TRACK_CONFIRMED"
    else:
        top = min(
            eligible,
            key=lambda row: (
                -row["track_point_count"],
                row["nadir_deg"],
                -row["track_spread_diagonal_px"],
                row["camera_name"],
            ),
        )
        top_status = "NO_NEAR_NADIR_BEST_TRACK_SUPPORT"
    by_name = {str(row["camera_name"]): row for row in eligible}
    remaining = [name for name in by_name if name != top["camera_name"]]
    chosen = deterministic_sample(remaining, len(roles) - 1, seed)
    views = [
        {
            "role": roles[0],
            "status": "SELECTED",
            "source": top_status,
            "camera": public_candidate(top),
        }
    ]
    for role, name in zip(roles[1:], chosen):
        views.append(
            {
                "role": role,
                "status": "SELECTED",
                "source": "DETERMINISTIC_RANDOM_FROM_SPARSE_TRACK_POOL",
                "camera": public_candidate(by_name[name]),
            }
        )
    for role in roles[len(views) :]:
        views.append({"role": role, "status": "SPARSE_SUPPORT_MISSING", "camera": None})
    pool = [public_candidate(row) for row in sorted(eligible, key=lambda row: row["camera_name"])]
    return views, top_status, seed, hashlib.sha256(canonical_json_bytes(pool)).hexdigest()


def outer_roof_shell_edges(
    rings: Sequence[np.ndarray], tolerance: float
) -> tuple[list[np.ndarray], dict[str, int | str]]:
    """Remove edges shared by RoofSurface rings and retain the target shell exterior."""
    counts: Counter[tuple[tuple[int, int, int], tuple[int, int, int]]] = Counter()
    values: dict[tuple[tuple[int, int, int], tuple[int, int, int]], np.ndarray] = {}

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
            a, b = node(start), node(end)
            key = tuple(sorted((a, b)))
            counts[key] += 1
            values.setdefault(key, np.vstack((start, end)))
    boundary_keys = [key for key, count in counts.items() if count == 1]
    edges = [values[key] for key in sorted(boundary_keys)]
    adjacency: defaultdict[tuple[int, int, int], set[tuple[int, int, int]]] = defaultdict(set)
    for a, b in boundary_keys:
        adjacency[a].add(b)
        adjacency[b].add(a)
    components = 0
    unseen = set(adjacency)
    while unseen:
        components += 1
        stack = [unseen.pop()]
        while stack:
            current = stack.pop()
            for neighbour in adjacency[current]:
                if neighbour in unseen:
                    unseen.remove(neighbour)
                    stack.append(neighbour)
    return edges, {
        "input_roof_surface_ring_count": int(len(rings)),
        "input_roof_surface_edge_count": input_edge_count,
        "outer_roof_shell_edge_count": len(edges),
        "outer_roof_shell_component_count": components,
        "shell_status": "MULTIPART_ROOF_SHELL" if components > 1 else "SINGLE_ROOF_SHELL",
    }


def project_edges(
    edges: Sequence[np.ndarray],
    camera: Any,
    model: tuple[int, int, np.ndarray],
    scene_reference: Mapping[str, Any],
    crop: Sequence[int],
) -> tuple[list[list[tuple[float, float]]], np.ndarray]:
    width, height, params = model
    segments: list[list[tuple[float, float]]] = []
    endpoints: list[np.ndarray] = []
    for edge in edges:
        uv, front = projection.project(edge, camera, width, height, params, scene_reference)
        valid = front & np.isfinite(uv).all(axis=1)
        if bool(np.all(valid)):
            endpoints.extend([uv[0], uv[1]])
            segments.append(
                [
                    (float(uv[0, 0] - crop[0]), float(uv[0, 1] - crop[1])),
                    (float(uv[1, 0] - crop[0]), float(uv[1, 1] - crop[1])),
                ]
            )
    return segments, np.asarray(endpoints, dtype=np.float64).reshape((-1, 2))


def projection_qc(
    roof_uv: np.ndarray, sparse_uv: np.ndarray, threshold: float
) -> tuple[str, float | None]:
    if not len(sparse_uv):
        return "SPARSE_SUPPORT_MISSING", None
    if not len(roof_uv):
        return "ROOF_SHELL_NOT_PROJECTABLE", None
    delta = float(np.linalg.norm(np.median(roof_uv, axis=0) - np.median(sparse_uv, axis=0)))
    return ("PROJECTION_ALIGNED" if delta <= threshold else "PROJECTION_MISMATCH"), delta


def draw_segments(
    image: Image.Image, segments: Sequence[Sequence[tuple[float, float]]], render: Mapping[str, Any]
) -> None:
    draw = ImageDraw.Draw(image)
    outline = tuple(map(int, render["roof_boundary_outline_rgb"]))
    color = tuple(map(int, render["roof_boundary_rgb"]))
    for segment in segments:
        draw.line(segment, fill=outline, width=int(render["roof_boundary_outline_width_px_before_resize"]))
        draw.line(segment, fill=color, width=int(render["roof_boundary_width_px_before_resize"]))


def draw_sparse_audit(
    image: Image.Image, uv: np.ndarray, crop: Sequence[int], render: Mapping[str, Any]
) -> int:
    draw = ImageDraw.Draw(image)
    radius = int(render["sparse_audit_point_radius_px_before_resize"])
    color = tuple(map(int, render["sparse_audit_rgb"]))
    count = 0
    for x, y in uv:
        px, py = float(x - crop[0]), float(y - crop[1])
        if -radius <= px <= image.width + radius and -radius <= py <= image.height + radius:
            draw.ellipse((px - radius, py - radius, px + radius, py + radius), fill=color)
            count += 1
    return count


def render_cell(
    crop_image: Image.Image,
    role: str,
    note: str,
    status: str,
    render: Mapping[str, Any],
    regular: ImageFont.FreeTypeFont,
    bold: ImageFont.FreeTypeFont,
) -> Image.Image:
    cell_width = int(render["cell_width_px"])
    header_height = int(render["cell_header_height_px"])
    image_height = int(render["cell_image_height_px"])
    background = tuple(map(int, render["cell_background_rgb"]))
    cell = Image.new("RGB", (cell_width, header_height + image_height), background)
    fitted = ImageOps.contain(crop_image.convert("RGB"), (cell_width, image_height), Image.Resampling.LANCZOS)
    cell.paste(fitted, ((cell_width - fitted.width) // 2, header_height + (image_height - fitted.height) // 2))
    draw = ImageDraw.Draw(cell)
    draw.text((24, 12), role.replace("_", " "), font=bold, fill=tuple(render["text_rgb"]))
    draw.text((24, 58), note, font=regular, fill=tuple(render["muted_text_rgb"]))
    color = (255, 214, 10) if status == "PROJECTION_ALIGNED" else (255, 156, 80)
    draw.text((cell_width - 24, 17), status, font=regular, fill=color, anchor="ra")
    return cell


def missing_cell(
    role: str,
    render: Mapping[str, Any],
    regular: ImageFont.FreeTypeFont,
    bold: ImageFont.FreeTypeFont,
) -> Image.Image:
    width = int(render["cell_width_px"])
    height = int(render["cell_header_height_px"]) + int(render["cell_image_height_px"])
    cell = Image.new("RGB", (width, height), tuple(render["cell_background_rgb"]))
    draw = ImageDraw.Draw(cell)
    draw.text((24, 12), role.replace("_", " "), font=bold, fill=tuple(render["text_rgb"]))
    draw.text((width / 2, height / 2), "SPARSE SUPPORT MISSING", font=bold, fill=(255, 156, 80), anchor="mm")
    draw.text((width / 2, height / 2 + 52), "No projection-only substitute", font=regular, fill=tuple(render["muted_text_rgb"]), anchor="mm")
    return cell


def png_bytes(image: Image.Image, render: Mapping[str, Any]) -> bytes:
    from io import BytesIO

    stream = BytesIO()
    image.convert(str(render["png_mode"])).save(
        stream,
        format="PNG",
        compress_level=int(render["png_compress_level"]),
        optimize=bool(render["png_optimize"]),
    )
    return stream.getvalue()


def render_preview_row(
    building: Mapping[str, Any],
    selection_record: Mapping[str, Any],
    runtime_candidates: Mapping[str, Mapping[str, Any]],
    roof_edges: Sequence[np.ndarray],
    shell_diagnostic: Mapping[str, Any],
    cameras: Mapping[str, Any],
    model: tuple[int, int, np.ndarray],
    scene_reference: Mapping[str, Any],
    image_dir: Path,
    render: Mapping[str, Any],
    qc_threshold: float,
    audit: bool,
) -> tuple[bytes, list[dict[str, Any]]]:
    roles = [str(view["role"]) for view in selection_record["views"]]
    row_width = int(render["cell_width_px"]) * len(roles)
    row_height = int(render["row_header_height_px"]) + int(render["cell_header_height_px"]) + int(render["cell_image_height_px"])
    canvas = Image.new("RGB", (row_width, row_height), tuple(render["background_rgb"]))
    regular = ImageFont.truetype(str(render["font_regular_path"]), 23)
    bold = ImageFont.truetype(str(render["font_bold_path"]), 34)
    title_font = ImageFont.truetype(str(render["font_bold_path"]), 38)
    draw = ImageDraw.Draw(canvas)
    suffix = " + SPARSE TRACK AUDIT" if audit else ""
    draw.text((26, 18), f"ROW 1 v3 — SPARSE-TRACK-CONFIRMED{suffix}", font=title_font, fill=tuple(render["text_rgb"]))
    draw.text(
        (row_width - 26, 25),
        f"{int(building['population_index']):03d}/199  {building['building_id']}",
        font=bold,
        fill=tuple(render["text_rgb"]),
        anchor="ra",
    )
    diagnostics: list[dict[str, Any]] = []
    for column, view in enumerate(selection_record["views"]):
        if view["status"] != "SELECTED":
            cell = missing_cell(str(view["role"]), render, regular, bold)
            canvas.paste(cell, (column * int(render["cell_width_px"]), int(render["row_header_height_px"])))
            diagnostics.append({"role": view["role"], "status": "SPARSE_SUPPORT_MISSING"})
            continue
        camera_record = view["camera"]
        camera_name = str(camera_record["camera_name"])
        crop = list(map(int, camera_record["crop_xyxy"]))
        runtime = runtime_candidates[camera_name]
        with Image.open(image_dir / camera_name) as raw:
            crop_image = raw.convert("RGB").crop(tuple(crop))
        segments, roof_uv = project_edges(roof_edges, cameras[camera_name], model, scene_reference, crop)
        draw_segments(crop_image, segments, render)
        sparse_uv = np.asarray(runtime["_inside_uv"], dtype=np.float64)
        audit_count = draw_sparse_audit(crop_image, sparse_uv, crop, render) if audit else 0
        qc_status, delta = projection_qc(roof_uv, sparse_uv, qc_threshold)
        note = (
            f"{camera_name} | track={int(camera_record['track_point_count'])}"
            f" | nadir={float(camera_record['nadir_deg']):.1f}°"
        )
        cell = render_cell(crop_image, str(view["role"]), note, qc_status, render, regular, bold)
        canvas.paste(cell, (column * int(render["cell_width_px"]), int(render["row_header_height_px"])))
        diagnostics.append(
            {
                "role": view["role"],
                "camera_name": camera_name,
                "selection_source": view["source"],
                "track_point_count": int(camera_record["track_point_count"]),
                "outer_roof_projected_segment_count": len(segments),
                "sparse_audit_drawn_count": audit_count,
                "roof_vs_sparse_median_delta_px": delta,
                "projection_qc_status": qc_status,
                **shell_diagnostic,
            }
        )
    return png_bytes(canvas, render), diagnostics


def page(rows: Sequence[Mapping[str, Any]]) -> bytes:
    cards = "".join(
        f'<article><h2>{int(row["population_index"]):03d}/199 — {html.escape(str(row["building_id"]))}</h2>'
        f'<h3>Outer roof shell only</h3><img src="roofline/{html.escape(str(row["filename"]))}">'
        f'<h3>Audit: yellow=outer roof shell, cyan=sparse points tracked by that image</h3>'
        f'<img src="audit/{html.escape(str(row["filename"]))}"></article>'
        for row in rows
    )
    return (
        "<!doctype html><html lang=ko><meta charset=utf-8><style>body{font-family:Arial,sans-serif;"
        "max-width:1960px;margin:auto;background:#111820;color:#f5f7fa}article{border-top:4px solid #607080;"
        "margin:40px 0}img{width:100%}</style><h1>Row 1 v3 sparse-track-confirmed preview</h1>" + cards + "</html>"
    ).encode()


def file_record(path: Path, root: Path) -> dict[str, Any]:
    size, digest = sha256_file(path)
    return {"path": path.relative_to(root).as_posix(), "bytes": size, "sha256": digest}


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
        config.get("status") != "USER_APPROVED_SPARSE_TRACK_ROW1_PREVIEW"
        or config["preview"]["full_199_render_authorized"]
        or int(config["preview"]["render_building_count"]) != 5
    ):
        raise RuntimeError("only the approved five-building sparse-track preview is authorized")
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

    buildings = [json.loads(line) for line in building_path.read_text(encoding="utf-8").splitlines() if line]
    if len(buildings) != int(config["preview"]["selection_manifest_building_count"]):
        raise RuntimeError("selection population drifted")
    by_id = {str(row["building_id"]): row for row in buildings}
    preview_ids = [str(value) for value in config["preview"]["building_ids"]]
    for index, building_id in zip(config["preview"]["population_indices"], preview_ids):
        if str(buildings[int(index) - 1]["building_id"]) != building_id:
            raise RuntimeError("preview membership drifted")

    exact = json.loads((repo_root / inputs["exact_937_crosswalk_git_path"]).read_text(encoding="utf-8"))
    image_id_to_name = {int(row["colmap_image_id"]): str(row["basename"]) for row in exact["rows"]}
    scene_reference = json.loads((artifact_root / inputs["scene_reference_relative_path"]).read_text(encoding="utf-8"))
    model = projection.parse_cam_model(artifact_root / inputs["cameras_relative_path"])
    cameras = {
        camera.name: camera
        for camera in projection.parse_cameras(artifact_root / inputs["images_relative_path"], scene_reference)
    }
    sparse_support, sparse_summary = scan_sparse_tracks(
        artifact_root / inputs["points3d_relative_path"],
        buildings,
        set(image_id_to_name),
        config["frame"]["sparse_local_shift_xyz"],
        int(inputs["points3d_count"]),
    )

    selection_records: list[dict[str, Any]] = []
    runtime_by_building: dict[str, dict[str, dict[str, Any]]] = {}
    top_status_counts: Counter[str] = Counter()
    missing_role_count = 0
    for building in buildings:
        building_id = str(building["building_id"])
        candidates = []
        for sparse_image_id, points in sparse_support[building_id]["image_points"].items():
            name = image_id_to_name[sparse_image_id]
            candidate = track_candidate(
                sparse_image_id,
                name,
                points,
                cameras[name],
                building,
                model,
                scene_reference,
                config["selection"],
                config["crop"],
            )
            candidates.append(candidate)
        views, top_status, seed, pool_hash = choose_views(building_id, candidates, config["selection"])
        top_status_counts[top_status] += 1
        missing_role_count += sum(view["status"] != "SELECTED" for view in views)
        runtime_by_building[building_id] = {str(row["camera_name"]): row for row in candidates}
        selection_records.append(
            {
                "schema": "jointbuildgs.p2.qualitative_row1_current_raw.camera_selection.v3",
                "population_index": int(building["population_index"]),
                "building_id": building_id,
                "sparse_points_xy_bbox_all_z": int(sparse_support[building_id]["xy_point_count_all_z"]),
                "sparse_points_xy_bbox_z_prism": int(sparse_support[building_id]["xyz_point_count"]),
                "track_confirmed_exact_937_image_count": len(candidates),
                "eligible_track_confirmed_image_count": sum(row["eligible"] for row in candidates),
                "eligible_candidate_pool_sha256": pool_hash,
                "seed_uint64": seed,
                "top_status": top_status,
                "views": views,
                "roof_boundary_used_for_selection": False,
                "projection_qc_used_for_selection": False,
                "scientific_verdict": None,
            }
        )
    write_new(
        partial / "selection/row1_camera_selection_v3.jsonl",
        b"".join(canonical_json_bytes(row) for row in selection_records),
    )

    references = load_references(
        [artifact_root / path for path in inputs["lod2_relative_paths"]],
        [str(row["building_id"]) for row in buildings],
    )
    inventory = image_inventory(repo_root / inputs["image_inventory_git_path"])
    image_dir = artifact_root / inputs["image_directory_relative_path"]
    selection_by_id = {str(row["building_id"]): row for row in selection_records}
    preview_image_names = sorted(
        {
            str(view["camera"]["camera_name"])
            for building_id in preview_ids
            for view in selection_by_id[building_id]["views"]
            if view["status"] == "SELECTED"
        }
    )
    selected_image_bindings = []
    for name in preview_image_names:
        expected = inventory[name]
        selected_image_bindings.append(
            {
                "basename": name,
                **verify_file(image_dir / name, expected["sha256"], f"preview raw image {name}", expected["bytes"]),
            }
        )

    preview_rows = []
    qc_counts: Counter[str] = Counter()
    shell_counts: Counter[str] = Counter()
    for building_id in preview_ids:
        building = by_id[building_id]
        selection_record = selection_by_id[building_id]
        roof_edges, shell_diagnostic = outer_roof_shell_edges(
            references[building_id].roof_rings_xyz,
            float(config["roofline"]["edge_snap_tolerance_m"]),
        )
        shell_counts[str(shell_diagnostic["shell_status"])] += 1
        roofline_payload, roofline_diagnostics = render_preview_row(
            building,
            selection_record,
            runtime_by_building[building_id],
            roof_edges,
            shell_diagnostic,
            cameras,
            model,
            scene_reference,
            image_dir,
            render,
            float(config["projection_qc"]["maximum_median_delta_px"]),
            False,
        )
        audit_payload, audit_diagnostics = render_preview_row(
            building,
            selection_record,
            runtime_by_building[building_id],
            roof_edges,
            shell_diagnostic,
            cameras,
            model,
            scene_reference,
            image_dir,
            render,
            float(config["projection_qc"]["maximum_median_delta_px"]),
            True,
        )
        for diagnostic in roofline_diagnostics:
            qc_status = diagnostic.get("projection_qc_status")
            if qc_status is None:
                qc_status = diagnostic.get("status", "UNKNOWN")
            qc_counts[str(qc_status)] += 1
        filename = f"{int(building['population_index']):03d}_{building_id}.png"
        write_new(partial / "preview/roofline" / filename, roofline_payload)
        write_new(partial / "preview/audit" / filename, audit_payload)
        preview_rows.append(
            {
                "population_index": int(building["population_index"]),
                "building_id": building_id,
                "filename": filename,
                "roofline_output_sha256": hashlib.sha256(roofline_payload).hexdigest(),
                "audit_output_sha256": hashlib.sha256(audit_payload).hexdigest(),
                "roof_shell": shell_diagnostic,
                "roofline_diagnostics": roofline_diagnostics,
                "audit_diagnostics": audit_diagnostics,
                "scientific_verdict": None,
            }
        )
    write_new(
        partial / "preview/preview_manifest_v3.json",
        canonical_json_bytes(
            {
                "schema": "jointbuildgs.p2.qualitative_row1_current_raw.preview_manifest.v3",
                "rows": preview_rows,
                "scientific_verdict": None,
            }
        ),
    )
    write_new(partial / "preview/index.html", page(preview_rows))
    write_new(
        partial / "control/source_bindings_v3.json",
        canonical_json_bytes(
            {
                "schema": "jointbuildgs.p2.qualitative_row1_current_raw.source_bindings.v3",
                **bindings,
                "preview_raw_images": selected_image_bindings,
                "scientific_verdict": None,
            }
        ),
    )
    summary = {
        "schema": "jointbuildgs.p2.qualitative_row1_current_raw.preview_summary.v3",
        "task_id": config["task_id"],
        "selection_building_count": len(selection_records),
        "preview_building_count": len(preview_rows),
        "preview_unique_raw_image_count": len(preview_image_names),
        "top_status_counts": dict(sorted(top_status_counts.items())),
        "missing_selection_role_count": missing_role_count,
        "preview_projection_qc_status_counts": dict(sorted(qc_counts.items())),
        "preview_roof_shell_status_counts": dict(sorted(shell_counts.items())),
        **sparse_summary,
        "camera_and_crop_selected_before_roofline_projection": True,
        "random_seeded_deterministically": True,
        "individual_roof_surface_rings_rendered_in_main_panel": False,
        "full_199_render_authorized": False,
        "next_row_authorized": False,
        "scientific_verdict": None,
    }
    write_new(partial / "control/summary_v3.json", canonical_json_bytes(summary))
    config_size, config_sha = sha256_file(config_path)
    script_size, script_sha = sha256_file(Path(__file__))
    write_new(
        partial / "control/run_receipt_v3.json",
        canonical_json_bytes(
            {
                "schema": "jointbuildgs.p2.qualitative_row1_current_raw.receipt.v3",
                "task_id": config["task_id"],
                "state": "complete",
                "generated_utc": datetime.now(timezone.utc).isoformat(),
                "repository_base_commit": source_commit,
                "runtime_image_id": image_id,
                "config": {"bytes": config_size, "sha256": config_sha},
                "script": {"bytes": script_size, "sha256": script_sha},
                "summary": summary,
                "scientific_verdict": None,
            }
        ),
    )
    material = sorted(path for path in partial.rglob("*") if path.is_file())
    manifest = {
        "schema": "jointbuildgs.p2.qualitative_row1_current_raw.artifact_manifest.v3",
        "task_id": config["task_id"],
        "records": [file_record(path, partial) for path in material],
        "scientific_verdict": None,
    }
    manifest["record_count"] = len(manifest["records"])
    write_new(partial / "control/artifact_manifest_v3.json", canonical_json_bytes(manifest))
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
    print(
        json.dumps(
            run(
                args.config,
                args.repo_root,
                args.artifact_root,
                args.output_root,
                args.source_commit,
                args.image_id,
            ),
            ensure_ascii=False,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
