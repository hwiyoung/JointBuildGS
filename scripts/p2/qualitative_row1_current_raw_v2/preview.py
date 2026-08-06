#!/usr/bin/env python3
"""Freeze TOP + deterministic-random row-1 cameras and render five review cases."""

from __future__ import annotations

import argparse
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
from PIL import Image, ImageDraw, ImageFont

from scripts.evidence_and_attributes.population_analysis import population_aux_v3 as projection
from scripts.p2.qualitative_199_common_manifest_v1.build_manifest import (
    camera_candidates,
    crop_xyxy,
    load_xyzrgb_ply,
    overlay_diagnostic,
    prism_points,
)
from scripts.p2.qualitative_row1_current_raw_v1.render import (
    draw_roof_segments,
    png_bytes,
    projected_ring_segments,
    render_cell,
)
from scripts.p2.utarget199_presentation_v5.render import load_references


REPO = Path(__file__).resolve().parents[3]
DEFAULT_CONFIG = REPO / "configs/p2/qualitative_row1_current_raw_v2/preview_v1.json"


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
    return {"path": str(path), "bytes": actual_size, "sha256": actual_digest, "verification": "sha256_rehash"}


def write_new(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(data)


def stable_seed(namespace: str, building_id: str) -> int:
    digest = hashlib.sha256(namespace.encode() + b"\0" + building_id.encode()).digest()
    return int.from_bytes(digest[:8], "big")


def deterministic_sample(names: Sequence[str], count: int, seed: int) -> list[str]:
    ordered = sorted(set(str(name) for name in names))
    if len(ordered) < count:
        raise RuntimeError(f"only {len(ordered)} candidates for deterministic sample of {count}")
    return random.Random(seed).sample(ordered, count)


def deterministic_preferred_sample(
    preferred: Sequence[str], fallback: Sequence[str], count: int, seed: int
) -> tuple[list[str], str]:
    preferred_ordered = sorted(set(map(str, preferred)))
    fallback_ordered = sorted(set(map(str, fallback)) - set(preferred_ordered))
    rng = random.Random(seed)
    if len(preferred_ordered) >= count:
        return rng.sample(preferred_ordered, count), "FULL_PRISM_ONLY"
    missing = count - len(preferred_ordered)
    if len(fallback_ordered) < missing:
        raise RuntimeError(
            f"only {len(preferred_ordered)} preferred and {len(fallback_ordered)} fallback candidates for {count} slots"
        )
    chosen = list(preferred_ordered) + rng.sample(fallback_ordered, missing)
    rng.shuffle(chosen)
    return chosen, "SUPPLEMENTED_PARTIAL_PRISM"


def image_inventory(path: Path) -> dict[str, dict[str, Any]]:
    with path.open(newline="", encoding="utf-8") as stream:
        return {
            str(row["basename"]): {
                "bytes": int(row["uncompressed_bytes"]),
                "sha256": str(row["sha256"]),
            }
            for row in csv.DictReader(stream)
        }


def camera_record(candidate: Mapping[str, Any], crop: Sequence[int], center_xy: np.ndarray) -> dict[str, Any]:
    camera = candidate["camera"]
    vector = np.asarray(camera.center[:2], dtype=np.float64) - center_xy
    azimuth = math.degrees(math.atan2(float(vector[1]), float(vector[0]))) % 360.0
    return {
        "camera_name": camera.name,
        "crop_xyxy": list(map(int, crop)),
        "selection_geometry": "FROZEN_CURRENT_MVS_DENSE_Z_PRISM",
        "selection_full_prism": bool(candidate["full_selection_prism"]),
        "selection_coverage_fraction": float(candidate["coverage"]),
        "selection_projected_area_px2": float(candidate["area_px2"]),
        "selection_nadir_deg": float(candidate["nadir_deg"]),
        "camera_azimuth_from_building_deg": azimuth,
    }


def dense_points_for_building(points: np.memmap, building: Mapping[str, Any], shift: np.ndarray, maximum: int) -> np.ndarray:
    bbox = np.asarray(building["building_bbox_xy"], dtype=np.float64)
    z_range = np.asarray(building["z_range_ellipsoidal_m"], dtype=np.float64)
    x = np.asarray(points["x"], dtype=np.float64) + shift[0]
    y = np.asarray(points["y"], dtype=np.float64) + shift[1]
    z = np.asarray(points["z"], dtype=np.float64) + shift[2]
    inside = (x >= bbox[0]) & (x <= bbox[2]) & (y >= bbox[1]) & (y <= bbox[3]) & (z >= z_range[0]) & (z <= z_range[1])
    indices = np.flatnonzero(inside)
    if len(indices) > maximum:
        step = int(math.ceil(len(indices) / maximum))
        indices = indices[::step][:maximum]
    return np.column_stack((x[indices], y[indices], z[indices]))


def draw_dense_audit(image: Image.Image, uv: np.ndarray, crop: Sequence[int], render: Mapping[str, Any]) -> int:
    if not len(uv):
        return 0
    draw = ImageDraw.Draw(image)
    color = tuple(int(value) for value in render["dense_audit_rgb"])
    radius = int(render["dense_audit_point_radius_px_before_resize"])
    count = 0
    for x, y in uv:
        px, py = float(x - crop[0]), float(y - crop[1])
        if -radius <= px < image.width + radius and -radius <= py < image.height + radius:
            draw.ellipse((px - radius, py - radius, px + radius, py + radius), fill=color)
            count += 1
    return count


def centroid_residual(roof_uv: np.ndarray, dense_uv: np.ndarray) -> float | None:
    if not len(roof_uv) or not len(dense_uv):
        return None
    return float(np.linalg.norm(np.median(roof_uv, axis=0) - np.median(dense_uv, axis=0)))


def render_preview_row(
    building: Mapping[str, Any],
    selection: Mapping[str, Any],
    reference: Any,
    cameras: Mapping[str, Any],
    model: tuple[int, int, np.ndarray],
    scene_reference: Mapping[str, Any],
    image_dir: Path,
    dense_points: np.ndarray,
    render: Mapping[str, Any],
    audit: bool,
) -> tuple[bytes, list[dict[str, Any]]]:
    roles = ["TOP", "RANDOM_1", "RANDOM_2", "RANDOM_3"]
    row_width = int(render["cell_width_px"]) * len(roles)
    row_height = int(render["row_header_height_px"]) + int(render["cell_header_height_px"]) + int(render["cell_image_height_px"])
    canvas = Image.new("RGB", (row_width, row_height), tuple(render["background_rgb"]))
    regular = ImageFont.truetype(str(render["font_regular_path"]), 25)
    bold = ImageFont.truetype(str(render["font_bold_path"]), 36)
    title_font = ImageFont.truetype(str(render["font_bold_path"]), 40)
    draw = ImageDraw.Draw(canvas)
    suffix = " + MVS DENSE AUDIT" if audit else ""
    draw.text((26, 18), f"ROW 1 v2 — FIXED TOP + DETERMINISTIC RANDOM{suffix}", font=title_font, fill=tuple(render["text_rgb"]))
    draw.text((row_width - 26, 25), f"{int(building['population_index']):03d}/199  {building['building_id']}", font=bold, fill=tuple(render["text_rgb"]), anchor="ra")
    diagnostics = []
    for column, view in enumerate(selection["views"]):
        camera_name = str(view["camera"]["camera_name"])
        crop = [int(value) for value in view["camera"]["crop_xyxy"]]
        camera = cameras[camera_name]
        with Image.open(image_dir / camera_name) as raw:
            crop_image = raw.convert("RGB").crop(tuple(crop))
        segments, _ = projected_ring_segments(reference.roof_rings_xyz, camera, model, scene_reference, crop)
        draw_roof_segments(crop_image, segments, render)
        roof_xyz = np.vstack(reference.roof_rings_xyz)
        roof_uv, roof_front = projection.project(roof_xyz, camera, *model, scene_reference)
        roof_uv = roof_uv[roof_front & np.isfinite(roof_uv).all(axis=1)]
        dense_uv, dense_front = projection.project(dense_points, camera, *model, scene_reference, input_datum="ellipsoidal")
        dense_uv = dense_uv[dense_front & np.isfinite(dense_uv).all(axis=1)]
        audit_point_count = draw_dense_audit(crop_image, dense_uv, crop, render) if audit else 0
        diagnostic = overlay_diagnostic(reference, camera, crop, model, scene_reference)
        residual = centroid_residual(roof_uv, dense_uv)
        note = f"{camera_name} | dense={len(dense_uv)}"
        if residual is not None:
            note += f" | median delta={residual:.1f}px"
        cell = render_cell(crop_image, str(view["role"]), note, str(diagnostic["status"]), render, regular, bold)
        canvas.paste(cell, (column * int(render["cell_width_px"]), int(render["row_header_height_px"])))
        diagnostics.append({"role": view["role"], "camera_name": camera_name, "roof_overlay": diagnostic, "dense_projected_count": len(dense_uv), "dense_audit_drawn_count": audit_point_count, "roof_vs_dense_median_residual_px": residual})
    return png_bytes(canvas, render), diagnostics


def page(rows: Sequence[Mapping[str, Any]]) -> bytes:
    cards = "".join(
        f'<article><h2>{int(row["population_index"]):03d}/199 — {html.escape(str(row["building_id"]))}</h2>'
        f'<h3>Roofline only</h3><img src="roofline/{html.escape(str(row["filename"]))}">'
        f'<h3>Projection audit: yellow=LoD2 roofline, cyan=current MVS dense support</h3><img src="audit/{html.escape(str(row["filename"]))}"></article>'
        for row in rows
    )
    return ("<!doctype html><html lang=ko><meta charset=utf-8><style>body{font-family:Arial,sans-serif;max-width:1960px;margin:auto;background:#111820;color:#f5f7fa}article{border-top:4px solid #607080;margin:40px 0}img{width:100%}</style><h1>Row 1 v2 deterministic preview</h1>" + cards + "</html>").encode()


def file_record(path: Path, root: Path) -> dict[str, Any]:
    size, digest = sha256_file(path)
    return {"path": path.relative_to(root).as_posix(), "bytes": size, "sha256": digest}


def run(config_path: Path, repo_root: Path, artifact_root: Path, output_root: Path, source_commit: str, image_id: str) -> dict[str, Any]:
    config = json.loads(config_path.read_text(encoding="utf-8"))
    if config.get("status") != "USER_APPROVED_TOP_PLUS_DETERMINISTIC_RANDOM_PREVIEW" or config["preview"]["full_199_render_authorized"]:
        raise RuntimeError("only the five-building v2 preview is authorized")
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
        "scene_reference": verify_file(artifact_root / inputs["scene_reference_relative_path"], inputs["scene_reference_sha256"], "scene reference"),
        "dense_ply": verify_file(artifact_root / inputs["recovered_dense_ply_relative_path"], inputs["recovered_dense_ply_sha256"], "dense PLY", int(inputs["recovered_dense_ply_bytes"])),
    }
    for index, relative in enumerate(inputs["lod2_relative_paths"]):
        bindings[f"lod2_{index + 1}"] = verify_file(artifact_root / relative, inputs["lod2_sha256"][index], f"LoD2 {index + 1}")
    render = config["render"]
    bindings["font_regular"] = verify_file(Path(render["font_regular_path"]), render["font_regular_sha256"], "regular font")
    bindings["font_bold"] = verify_file(Path(render["font_bold_path"]), render["font_bold_sha256"], "bold font")
    if PIL.__version__ != render["pillow_version"]:
        raise RuntimeError("Pillow version drifted")
    buildings = [json.loads(line) for line in building_path.read_text(encoding="utf-8").splitlines()]
    by_id = {str(row["building_id"]): row for row in buildings}
    preview_ids = [str(value) for value in config["preview"]["building_ids"]]
    for index, building_id in zip(config["preview"]["population_indices"], preview_ids):
        if str(buildings[int(index) - 1]["building_id"]) != building_id:
            raise RuntimeError("preview membership drifted")
    scene_reference = json.loads((artifact_root / inputs["scene_reference_relative_path"]).read_text(encoding="utf-8"))
    model = projection.parse_cam_model(artifact_root / inputs["cameras_relative_path"])
    cameras = {camera.name: camera for camera in projection.parse_cameras(artifact_root / inputs["images_relative_path"], scene_reference)}
    exact = json.loads((repo_root / inputs["exact_937_crosswalk_git_path"]).read_text(encoding="utf-8"))
    visible = {str(row["basename"]) for row in exact["rows"]}
    references = load_references([artifact_root / path for path in inputs["lod2_relative_paths"]], [str(row["building_id"]) for row in buildings])
    inventory = image_inventory(repo_root / inputs["image_inventory_git_path"])
    image_dir = artifact_root / inputs["image_directory_relative_path"]
    selection_records = []
    selected_image_names: set[str] = set()
    minimum_candidates = int(config["selection"]["minimum_random_candidates"])
    for building in buildings:
        building_id = str(building["building_id"])
        center_xy = np.asarray(building["principal_frame"]["center_xy"], dtype=np.float64)
        principal = np.asarray(building["principal_frame"]["axis_xy"], dtype=np.float64)
        cross = np.asarray(building["principal_frame"]["cross_axis_xy"], dtype=np.float64)
        candidates = camera_candidates(prism_points(building["viewport_bbox_xy"], building["z_range_ellipsoidal_m"]), np.asarray([center_xy[0], center_xy[1], np.mean(building["z_range_ellipsoidal_m"])], dtype=np.float64), principal, cross, cameras, model, scene_reference, visible, float(config["selection"]["minimum_projection_coverage"]), float(config["selection"]["minimum_projected_area_px2"]))
        top = building["views"][0]["camera"]
        eligible = {row["camera"].name: row for row in candidates if row["camera"].name != top["camera_name"]}
        full = {name: row for name, row in eligible.items() if row["full_selection_prism"]}
        seed = stable_seed(str(config["selection"]["random_seed_namespace"]), building_id)
        chosen_names, pool_status = deterministic_preferred_sample(list(full), list(eligible), minimum_candidates, seed)
        views = [{"role": "TOP", "source": "COMMON_MANIFEST_V1_FIXED_TOP", "camera": dict(top)}]
        for index, name in enumerate(chosen_names, start=1):
            candidate = eligible[name]
            crop = crop_xyxy(candidate["selection_uv"], model[0], model[1], float(config["crop"]["image_margin_scale"]), float(config["crop"]["image_margin_constant_px"]))
            if crop is None:
                raise RuntimeError(f"random crop failed: {building_id} {name}")
            views.append({"role": f"RANDOM_{index}", "source": "DETERMINISTIC_RANDOM_FROM_SORTED_FULL_PRISM_POOL", "camera": camera_record(candidate, crop, center_xy)})
        selected_image_names.update(str(view["camera"]["camera_name"]) for view in views)
        pool_payload = canonical_json_bytes(sorted(eligible))
        selection_records.append({"schema": "jointbuildgs.p2.qualitative_row1_current_raw.camera_selection.v2", "population_index": int(building["population_index"]), "building_id": building_id, "seed_uint64": seed, "selection_pool_status": pool_status, "eligible_candidate_count_excluding_top": len(eligible), "full_prism_candidate_count_excluding_top": len(full), "candidate_name_list_sha256": hashlib.sha256(pool_payload).hexdigest(), "views": views, "roof_boundary_used_for_selection": False, "scientific_verdict": None})
    selected_image_bindings = []
    for name in sorted(selected_image_names):
        expected = inventory[name]
        selected_image_bindings.append({"basename": name, **verify_file(image_dir / name, expected["sha256"], f"raw image {name}", expected["bytes"])})
    write_new(partial / "selection/row1_camera_selection_v2.jsonl", b"".join(canonical_json_bytes(row) for row in selection_records))
    points, point_count = load_xyzrgb_ply(artifact_root / inputs["recovered_dense_ply_relative_path"])
    shift = np.asarray(config["frame"]["dense_local_shift_xyz"], dtype=np.float64)
    selection_by_id = {row["building_id"]: row for row in selection_records}
    preview_rows = []
    for building_id in preview_ids:
        building = by_id[building_id]
        selection = selection_by_id[building_id]
        dense = dense_points_for_building(points, building, shift, int(render["dense_audit_max_points"]))
        roofline_payload, roofline_diagnostics = render_preview_row(building, selection, references[building_id], cameras, model, scene_reference, image_dir, dense, render, False)
        audit_payload, audit_diagnostics = render_preview_row(building, selection, references[building_id], cameras, model, scene_reference, image_dir, dense, render, True)
        filename = f"{int(building['population_index']):03d}_{building_id}.png"
        write_new(partial / "preview/roofline" / filename, roofline_payload)
        write_new(partial / "preview/audit" / filename, audit_payload)
        preview_rows.append({"population_index": int(building["population_index"]), "building_id": building_id, "filename": filename, "dense_points_in_exact_building_bbox": len(dense), "roofline_output_sha256": hashlib.sha256(roofline_payload).hexdigest(), "audit_output_sha256": hashlib.sha256(audit_payload).hexdigest(), "roofline_diagnostics": roofline_diagnostics, "audit_diagnostics": audit_diagnostics, "scientific_verdict": None})
    write_new(partial / "preview/preview_manifest_v1.json", canonical_json_bytes({"schema": "jointbuildgs.p2.qualitative_row1_current_raw.preview_manifest.v2", "rows": preview_rows, "scientific_verdict": None}))
    write_new(partial / "preview/index.html", page(preview_rows))
    source = {"schema": "jointbuildgs.p2.qualitative_row1_current_raw.source_bindings.v2", **bindings, "selected_raw_images": selected_image_bindings, "scientific_verdict": None}
    write_new(partial / "control/source_bindings_v2.json", canonical_json_bytes(source))
    min_candidates = min(row["full_prism_candidate_count_excluding_top"] for row in selection_records)
    summary = {"schema": "jointbuildgs.p2.qualitative_row1_current_raw.preview_summary.v2", "task_id": config["task_id"], "selection_building_count": len(selection_records), "preview_building_count": len(preview_rows), "selected_unique_raw_image_count": len(selected_image_names), "minimum_full_prism_random_candidate_count_excluding_top": min_candidates, "selection_pool_status_counts": {status: sum(row["selection_pool_status"] == status for row in selection_records) for status in sorted({row["selection_pool_status"] for row in selection_records})}, "dense_source_point_count": point_count, "top_reused_exactly": True, "random_seeded_deterministically": True, "full_199_render_authorized": False, "next_row_authorized": False, "scientific_verdict": None}
    write_new(partial / "control/summary_v2.json", canonical_json_bytes(summary))
    config_size, config_sha = sha256_file(config_path); script_size, script_sha = sha256_file(Path(__file__))
    write_new(partial / "control/run_receipt_v2.json", canonical_json_bytes({"schema": "jointbuildgs.p2.qualitative_row1_current_raw.receipt.v2", "task_id": config["task_id"], "state": "complete", "generated_utc": datetime.now(timezone.utc).isoformat(), "repository_base_commit": source_commit, "runtime_image_id": image_id, "config": {"bytes": config_size, "sha256": config_sha}, "script": {"bytes": script_size, "sha256": script_sha}, "summary": summary, "scientific_verdict": None}))
    material = sorted(path for path in partial.rglob("*") if path.is_file())
    manifest = {"schema": "jointbuildgs.p2.qualitative_row1_current_raw.artifact_manifest.v2", "task_id": config["task_id"], "records": [file_record(path, partial) for path in material], "scientific_verdict": None}
    manifest["record_count"] = len(manifest["records"])
    write_new(partial / "control/artifact_manifest_v2.json", canonical_json_bytes(manifest))
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
