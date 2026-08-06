#!/usr/bin/env python3
"""Render deterministic row-1 current-image panels from the frozen common manifest."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
from datetime import datetime, timezone
import hashlib
import html
import json
import os
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np
import PIL
from PIL import Image, ImageDraw, ImageFont, ImageOps

from scripts.evidence_and_attributes.population_analysis import population_aux_v3 as projection
from scripts.p2.qualitative_199_common_manifest_v1.build_manifest import overlay_diagnostic
from scripts.p2.utarget199_presentation_v5.render import load_references


REPO = Path(__file__).resolve().parents[3]
DEFAULT_CONFIG = REPO / "configs/p2/qualitative_row1_current_raw_v1/render_v1.json"


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


def verify_file(path: Path, expected_sha256: str, label: str, expected_bytes: int | None = None) -> dict[str, Any]:
    size, digest = sha256_file(path)
    if digest != expected_sha256:
        raise RuntimeError(f"{label} hash mismatch: expected {expected_sha256}, got {digest}")
    if expected_bytes is not None and size != expected_bytes:
        raise RuntimeError(f"{label} byte mismatch: expected {expected_bytes}, got {size}")
    return {"path": str(path), "bytes": size, "sha256": digest, "verification": "sha256_rehash"}


def write_new(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(data)


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def load_image_inventory(path: Path) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    with path.open(newline="", encoding="utf-8") as stream:
        for row in csv.DictReader(stream):
            basename = str(row["basename"])
            if basename in rows:
                raise RuntimeError(f"duplicate image inventory basename: {basename}")
            rows[basename] = {
                "basename": basename,
                "uncompressed_bytes": int(row["uncompressed_bytes"]),
                "sha256": str(row["sha256"]),
            }
    return rows


def validate_review_selection(buildings: Sequence[Mapping[str, Any]], spec: Mapping[str, Any]) -> list[dict[str, Any]]:
    indices = [int(value) for value in spec["population_indices"]]
    ids = [str(value) for value in spec["building_ids"]]
    if len(indices) != len(ids) or len(set(indices)) != len(indices):
        raise RuntimeError("outcome-free review selection is malformed")
    selected = []
    for index, expected_id in zip(indices, ids):
        if index < 1 or index > len(buildings):
            raise RuntimeError(f"outcome-free population index is out of range: {index}")
        actual_id = str(buildings[index - 1]["building_id"])
        if actual_id != expected_id:
            raise RuntimeError(f"outcome-free review binding drifted at {index}: {actual_id} != {expected_id}")
        selected.append({"population_index": index, "building_id": actual_id})
    return selected


def projected_ring_segments(
    rings: Sequence[np.ndarray],
    camera: Any,
    model: tuple[int, int, np.ndarray],
    scene_reference: Mapping[str, Any],
    crop: Sequence[int],
) -> tuple[list[list[tuple[float, float]]], int]:
    width, height, params = model
    segments: list[list[tuple[float, float]]] = []
    valid_vertices = 0
    for ring in rings:
        uv, front = projection.project(
            np.asarray(ring, dtype=np.float64), camera, width, height, params, scene_reference
        )
        valid = front & np.isfinite(uv).all(axis=1)
        valid_vertices += int(valid.sum())
        for index in range(max(0, len(uv) - 1)):
            if valid[index] and valid[index + 1]:
                segments.append(
                    [
                        (float(uv[index, 0] - crop[0]), float(uv[index, 1] - crop[1])),
                        (float(uv[index + 1, 0] - crop[0]), float(uv[index + 1, 1] - crop[1])),
                    ]
                )
    return segments, valid_vertices


def draw_roof_segments(image: Image.Image, segments: Sequence[Sequence[tuple[float, float]]], render: Mapping[str, Any]) -> None:
    draw = ImageDraw.Draw(image)
    outline = tuple(int(value) for value in render["roof_boundary_outline_rgb"])
    color = tuple(int(value) for value in render["roof_boundary_rgb"])
    outline_width = int(render["roof_boundary_outline_width_px_before_resize"])
    width = int(render["roof_boundary_width_px_before_resize"])
    for segment in segments:
        draw.line(list(segment), fill=outline, width=outline_width)
        draw.line(list(segment), fill=color, width=width)


def render_cell(
    crop_image: Image.Image,
    view_id: str,
    camera_name: str,
    overlay_status: str,
    render: Mapping[str, Any],
    regular_font: ImageFont.FreeTypeFont,
    bold_font: ImageFont.FreeTypeFont,
) -> Image.Image:
    cell_width = int(render["cell_width_px"])
    header_height = int(render["cell_header_height_px"])
    image_height = int(render["cell_image_height_px"])
    background = tuple(int(value) for value in render["cell_background_rgb"])
    cell = Image.new("RGB", (cell_width, header_height + image_height), background)
    fitted = ImageOps.contain(crop_image.convert("RGB"), (cell_width, image_height), Image.Resampling.LANCZOS)
    cell.paste(fitted, ((cell_width - fitted.width) // 2, header_height + (image_height - fitted.height) // 2))
    draw = ImageDraw.Draw(cell)
    text = tuple(int(value) for value in render["text_rgb"])
    muted = tuple(int(value) for value in render["muted_text_rgb"])
    draw.text((24, 14), view_id.replace("_", " "), font=bold_font, fill=text)
    draw.text((24, 57), camera_name, font=regular_font, fill=muted)
    status_color = (255, 214, 10) if overlay_status == "FULL_ROOF_RING_PROJECTABLE" else (255, 156, 80)
    draw.text((cell_width - 24, 18), overlay_status, font=regular_font, fill=status_color, anchor="ra")
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


def page_html(title: str, rows: Sequence[Mapping[str, Any]], relative_prefix: str = "../rows") -> bytes:
    cards = "".join(
        f'<article><h2>{int(row["population_index"]):03d}/199 — {html.escape(str(row["building_id"]))}</h2>'
        f'<img loading="lazy" src="{relative_prefix}/{html.escape(str(row["filename"]))}" '
        f'alt="{html.escape(str(row["building_id"]))}"></article>'
        for row in rows
    )
    document = f"""<!doctype html><html lang="ko"><meta charset="utf-8"><title>{html.escape(title)}</title>
<style>body{{font-family:Arial,sans-serif;max-width:1960px;margin:24px auto;background:#111820;color:#f5f7fa}}
article{{border-top:3px solid #607080;margin:36px 0;padding-top:16px}}img{{width:100%;height:auto;display:block}}code{{color:#ffd60a}}</style>
<h1>{html.escape(title)}</h1><p>Frozen manifest cameras/crops. Yellow line: evaluation-only LoD2 roof boundary. scientific_verdict: <code>null</code>.</p>{cards}</html>"""
    return document.encode("utf-8")


def file_record(path: Path, root: Path) -> dict[str, Any]:
    size, digest = sha256_file(path)
    return {"path": path.relative_to(root).as_posix(), "bytes": size, "sha256": digest}


def render_all(
    config: Mapping[str, Any],
    repo_root: Path,
    artifact_root: Path,
    partial: Path,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    inputs = config["inputs"]
    common_root = artifact_root / inputs["common_manifest_relative_root"]
    building_path = common_root / inputs["building_manifest_relative_path"]
    view_path = common_root / inputs["camera_view_manifest_relative_path"]
    source_bindings: dict[str, Any] = {
        "building_manifest": verify_file(building_path, inputs["building_manifest_sha256"], "building manifest", int(inputs["building_manifest_bytes"])),
        "camera_view_manifest": verify_file(view_path, inputs["camera_view_manifest_sha256"], "camera view manifest", int(inputs["camera_view_manifest_bytes"])),
        "common_source_bindings": verify_file(common_root / inputs["common_source_bindings_relative_path"], inputs["common_source_bindings_sha256"], "common source bindings"),
        "image_inventory": verify_file(repo_root / inputs["image_inventory_git_path"], inputs["image_inventory_sha256"], "image inventory"),
        "exact_937_crosswalk": verify_file(repo_root / inputs["exact_937_crosswalk_git_path"], inputs["exact_937_crosswalk_sha256"], "exact-937 crosswalk"),
        "cameras": verify_file(artifact_root / inputs["cameras_relative_path"], inputs["cameras_sha256"], "COLMAP cameras"),
        "images": verify_file(artifact_root / inputs["images_relative_path"], inputs["images_sha256"], "COLMAP images"),
        "scene_reference": verify_file(artifact_root / inputs["scene_reference_relative_path"], inputs["scene_reference_sha256"], "scene reference"),
    }
    for index, relative in enumerate(inputs["lod2_relative_paths"]):
        source_bindings[f"lod2_{index + 1}"] = verify_file(artifact_root / relative, inputs["lod2_sha256"][index], f"LoD2 {index + 1}")
    render = config["render"]
    source_bindings["font_regular"] = verify_file(Path(render["font_regular_path"]), render["font_regular_sha256"], "regular font")
    source_bindings["font_bold"] = verify_file(Path(render["font_bold_path"]), render["font_bold_sha256"], "bold font")
    if PIL.__version__ != str(render["pillow_version"]):
        raise RuntimeError(f"Pillow version drifted: {PIL.__version__}")

    buildings = read_jsonl(building_path)
    views = read_jsonl(view_path)
    expected_count = int(config["population"]["building_count"])
    expected_view_count = int(config["population"]["view_rows"])
    if len(buildings) != expected_count or len(views) != expected_view_count:
        raise RuntimeError(f"manifest population drifted: {len(buildings)} buildings, {len(views)} views")
    view_order = [str(value) for value in config["population"]["view_order"]]
    by_building: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in views:
        by_building[str(row["building_id"])].append(row)
    for building in buildings:
        building_id = str(building["building_id"])
        rows = sorted(by_building[building_id], key=lambda row: view_order.index(str(row["view_id"])))
        if rows != building["views"]:
            raise RuntimeError(f"building and view manifests disagree: {building_id}")
        if [str(row["view_id"]) for row in rows] != view_order:
            raise RuntimeError(f"view order drifted: {building_id}")
    review = validate_review_selection(buildings, config["outcome_free_review"])

    crosswalk = json.loads((repo_root / inputs["exact_937_crosswalk_git_path"]).read_text(encoding="utf-8"))
    exact_names = {str(row["basename"]) for row in crosswalk["rows"]}
    inventory = load_image_inventory(repo_root / inputs["image_inventory_git_path"])
    selected_names = sorted({str(row["camera"]["camera_name"]) for row in views})
    if not set(selected_names) <= exact_names:
        raise RuntimeError("selected camera is outside exact-937 membership")
    image_dir = artifact_root / inputs["image_directory_relative_path"]
    image_bindings = []
    for name in selected_names:
        expected = inventory.get(name)
        if expected is None:
            raise RuntimeError(f"selected image is absent from Gate S0 inventory: {name}")
        binding = verify_file(image_dir / name, expected["sha256"], f"raw image {name}", expected["uncompressed_bytes"])
        image_bindings.append({"basename": name, **binding})

    scene_reference = json.loads((artifact_root / inputs["scene_reference_relative_path"]).read_text(encoding="utf-8"))
    model = projection.parse_cam_model(artifact_root / inputs["cameras_relative_path"])
    cameras = {camera.name: camera for camera in projection.parse_cameras(artifact_root / inputs["images_relative_path"], scene_reference)}
    references = load_references([artifact_root / path for path in inputs["lod2_relative_paths"]], [str(row["building_id"]) for row in buildings])
    regular = ImageFont.truetype(str(render["font_regular_path"]), 25)
    bold = ImageFont.truetype(str(render["font_bold_path"]), 36)
    title_font = ImageFont.truetype(str(render["font_bold_path"]), 40)

    row_records: list[dict[str, Any]] = []
    panel_records: list[dict[str, Any]] = []
    overlay_counts: Counter[str] = Counter()
    row_width = int(render["cell_width_px"]) * len(view_order)
    row_height = int(render["row_header_height_px"]) + int(render["cell_header_height_px"]) + int(render["cell_image_height_px"])
    row_background = tuple(int(value) for value in render["background_rgb"])
    text_color = tuple(int(value) for value in render["text_rgb"])
    for building in buildings:
        building_id = str(building["building_id"])
        population_index = int(building["population_index"])
        canvas = Image.new("RGB", (row_width, row_height), row_background)
        title_draw = ImageDraw.Draw(canvas)
        title_draw.text((26, 18), f"ROW 1 — CURRENT RAW IMAGES + EVALUATION ROOF BOUNDARY", font=title_font, fill=text_color)
        title_draw.text((row_width - 26, 25), f"{population_index:03d}/199  {building_id}", font=bold, fill=text_color, anchor="ra")
        building_panels = sorted(by_building[building_id], key=lambda row: view_order.index(str(row["view_id"])))
        logical_panels = []
        for column, view_row in enumerate(building_panels):
            camera_record = view_row["camera"]
            if camera_record["status"] != "SELECTED" or camera_record["crop_xyxy"] is None:
                raise RuntimeError(f"row-1 camera/crop is unavailable: {building_id} {view_row['view_id']}")
            camera_name = str(camera_record["camera_name"])
            camera = cameras.get(camera_name)
            if camera is None:
                raise RuntimeError(f"selected camera pose is unavailable: {camera_name}")
            crop = [int(value) for value in camera_record["crop_xyxy"]]
            with Image.open(image_dir / camera_name) as raw:
                if list(raw.size) != [int(value) for value in camera_record["image_size_wh"]]:
                    raise RuntimeError(f"raw image dimensions drifted: {camera_name}")
                crop_image = raw.convert("RGB").crop(tuple(crop))
            recomputed = overlay_diagnostic(references[building_id], camera, crop, model, scene_reference)
            if recomputed != view_row["evaluation_roof_boundary"]:
                raise RuntimeError(f"roof overlay diagnostic drifted: {building_id} {view_row['view_id']}")
            segments, valid_vertices = projected_ring_segments(
                references[building_id].roof_rings_xyz, camera, model, scene_reference, crop
            )
            draw_roof_segments(crop_image, segments, render)
            status = str(recomputed["status"])
            overlay_counts[status] += 1
            cell = render_cell(crop_image, str(view_row["view_id"]), camera_name, status, render, regular, bold)
            canvas.paste(cell, (column * int(render["cell_width_px"]), int(render["row_header_height_px"])))
            logical_panels.append(
                {
                    "view_id": str(view_row["view_id"]),
                    "camera_name": camera_name,
                    "source_image_sha256": inventory[camera_name]["sha256"],
                    "crop_xyxy": crop,
                    "overlay_status": status,
                    "projected_segment_count": len(segments),
                    "front_finite_roof_vertex_count": valid_vertices,
                    "roof_boundary_used_for_camera_or_crop_selection": False,
                }
            )
        filename = f"{population_index:03d}_{building_id}.png"
        row_path = partial / "rows" / filename
        payload = png_bytes(canvas, render)
        write_new(row_path, payload)
        row_sha = hashlib.sha256(payload).hexdigest()
        row_record = {
            "schema": "jointbuildgs.p2.qualitative_row1_current_raw.row_result.v1",
            "population_index": population_index,
            "building_id": building_id,
            "filename": filename,
            "output": {"path": f"rows/{filename}", "bytes": len(payload), "sha256": row_sha, "size_wh": [row_width, row_height]},
            "panels": logical_panels,
            "scientific_verdict": None,
        }
        row_records.append(row_record)
        for panel in logical_panels:
            panel_records.append(
                {
                    "schema": "jointbuildgs.p2.qualitative_row1_current_raw.panel_binding.v1",
                    "population_index": population_index,
                    "building_id": building_id,
                    **panel,
                    "row_output_path": row_record["output"]["path"],
                    "row_output_sha256": row_sha,
                    "scientific_verdict": None,
                }
            )
    return row_records, panel_records, {
        "source_bindings": source_bindings,
        "image_bindings": image_bindings,
        "review_selection": review,
        "overlay_status_counts": dict(sorted(overlay_counts.items())),
    }


def run(config_path: Path, repo_root: Path, artifact_root: Path, output_root: Path, source_commit: str, image_id: str) -> dict[str, Any]:
    config = json.loads(config_path.read_text(encoding="utf-8"))
    if config.get("status") != "USER_APPROVED_ROW1_ONLY" or int(config["row"]["number"]) != 1:
        raise RuntimeError("row-1-only execution is not approved")
    if bool(config["row"]["camera_reselection_allowed"]) or bool(config["row"]["crop_recomputation_allowed"]):
        raise RuntimeError("row-1 contract permits camera or crop drift")
    if output_root.exists() or output_root.with_name(output_root.name + ".partial").exists():
        raise RuntimeError(f"add-once output exists: {output_root}")
    partial = output_root.with_name(output_root.name + ".partial")
    partial.mkdir(parents=True)
    row_records, panel_records, support = render_all(config, repo_root, artifact_root, partial)
    write_new(partial / "manifest/row1_building_results_v1.jsonl", b"".join(canonical_json_bytes(row) for row in row_records))
    write_new(partial / "manifest/row1_panel_bindings_v1.jsonl", b"".join(canonical_json_bytes(row) for row in panel_records))
    write_new(partial / "control/source_bindings_v1.json", canonical_json_bytes({"schema": "jointbuildgs.p2.qualitative_row1_current_raw.source_bindings.v1", **support["source_bindings"], "selected_raw_images": support["image_bindings"], "scientific_verdict": None}))
    write_new(partial / "control/outcome_free_review_selection_v1.json", canonical_json_bytes({"schema": "jointbuildgs.p2.qualitative_row1_current_raw.review_selection.v1", "rule": config["outcome_free_review"]["rule"], "rows": support["review_selection"], "selected_before_rendering": True, "scientific_verdict": None}))
    review_ids = {row["building_id"] for row in support["review_selection"]}
    review_rows = [row for row in row_records if row["building_id"] in review_ids]
    write_new(partial / "review/outcome_free_5.html", page_html("Row 1 outcome-free five-building review", review_rows))
    write_new(partial / "review/all_199.html", page_html("Row 1 all-199 review", row_records))
    summary = {
        "schema": "jointbuildgs.p2.qualitative_row1_current_raw.summary.v1",
        "task_id": config["task_id"],
        "row_number": 1,
        "building_count": len(row_records),
        "panel_count": len(panel_records),
        "unique_raw_image_count": len(support["image_bindings"]),
        "row_png_count": len(row_records),
        "outcome_free_review_count": len(review_rows),
        "overlay_status_counts": support["overlay_status_counts"],
        "all_cameras_and_crops_reused_exactly": True,
        "next_row_authorized": False,
        "scientific_verdict": None,
    }
    write_new(partial / "control/summary_v1.json", canonical_json_bytes(summary))
    config_size, config_sha = sha256_file(config_path)
    script_size, script_sha = sha256_file(Path(__file__))
    receipt = {
        "schema": "jointbuildgs.p2.qualitative_row1_current_raw.receipt.v1",
        "task_id": config["task_id"],
        "state": "complete",
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "repository_base_commit": source_commit,
        "runtime_image_id": image_id,
        "config": {"path": str(config_path), "bytes": config_size, "sha256": config_sha},
        "script": {"path": str(Path(__file__)), "bytes": script_size, "sha256": script_sha},
        "summary": summary,
        "scientific_verdict": None,
    }
    write_new(partial / "control/run_receipt_v1.json", canonical_json_bytes(receipt))
    material = sorted(path for path in partial.rglob("*") if path.is_file())
    artifact_manifest = {
        "schema": "jointbuildgs.p2.qualitative_row1_current_raw.artifact_manifest.v1",
        "task_id": config["task_id"],
        "records": [file_record(path, partial) for path in material],
        "scientific_verdict": None,
    }
    artifact_manifest["record_count"] = len(artifact_manifest["records"])
    write_new(partial / "control/artifact_manifest_v1.json", canonical_json_bytes(artifact_manifest))
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
