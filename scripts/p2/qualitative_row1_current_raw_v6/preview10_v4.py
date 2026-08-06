#!/usr/bin/env python3
"""Render terminal no-sparse-confirmation fallback panels without rooflines."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from PIL import Image, ImageDraw, ImageFont, ImageOps

from scripts.p2.qualitative_row1_current_raw_v3.preview import verify_file
from scripts.p2.qualitative_row1_current_raw_v6 import preview10 as delegate
from scripts.p2.qualitative_row1_current_raw_v6 import preview10_v3 as terminal_fallback


REPO = Path(__file__).resolve().parents[3]
DEFAULT_CONFIG = REPO / "configs/p2/qualitative_row1_current_raw_v6/preview10_v4.json"
_BASE_RENDER_BUILDING = delegate.render_building


def photo_only_panel(
    raw_crop: Image.Image,
    role: str,
    note: str,
    base_render: Mapping[str, Any],
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
    draw = ImageDraw.Draw(cell)
    draw.text((24, 12), role, font=bold, fill=tuple(base_render["text_rgb"]))
    draw.text((24, 59), note, font=regular, fill=tuple(base_render["muted_text_rgb"]))
    draw.text(
        (cell_width - 24, 18),
        "PHOTO ONLY - ROOFLINE OMITTED",
        font=regular,
        fill=(255, 156, 80),
        anchor="ra",
    )
    draw.text(
        (cell_width / 2, 98),
        "NO BUILDING-SPARSE CONFIRMATION",
        font=regular,
        fill=(255, 156, 80),
        anchor="mm",
    )
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
    fallback_views = [
        view
        for view in selection_record["views"]
        if view.get("source") == terminal_fallback.GEOMETRY_FALLBACK_SOURCE
    ]
    if not fallback_views:
        return _BASE_RENDER_BUILDING(
            building,
            selection_record,
            runtime_candidates,
            topology,
            components,
            representative_component_id,
            image_dir,
            base_render,
            v6_render,
        )

    views = selection_record["views"]
    width = int(base_render["cell_width_px"]) * len(views)
    height = int(base_render["row_header_height_px"]) + int(base_render["cell_header_height_px"]) + int(base_render["cell_image_height_px"])
    canvas = Image.new("RGB", (width, height), tuple(base_render["background_rgb"]))
    regular = ImageFont.truetype(str(base_render["font_regular_path"]), 23)
    bold = ImageFont.truetype(str(base_render["font_bold_path"]), 34)
    title_font = ImageFont.truetype(str(base_render["font_bold_path"]), 38)
    draw = ImageDraw.Draw(canvas)
    draw.text((26, 18), "ROW 1 v6 — PHOTO-ONLY UNVALIDATED FALLBACK", font=title_font, fill=tuple(base_render["text_rgb"]))
    draw.text(
        (width - 26, 25),
        f"{int(building['population_index']):03d}/199  {building['building_id']}",
        font=bold,
        fill=tuple(base_render["text_rgb"]),
        anchor="ra",
    )
    diagnostics = []
    for column, view in enumerate(views):
        role = str(view["role"]).replace("_", " ")
        if view["status"] != "SELECTED":
            cell = delegate.missing_panel(role, base_render, regular, bold)
            diagnostics.append({"role": view["role"], "status": view["status"], **topology})
        else:
            camera_record = view["camera"]
            name = str(camera_record["camera_name"])
            crop = list(map(int, camera_record["crop_xyxy"]))
            with Image.open(image_dir / name) as raw:
                raw_crop = raw.convert("RGB").crop(tuple(crop))
            display_role = role
            if view["role"] == "TOP":
                display_role = "TOP"
            note = f"{name} | nadir={float(camera_record['nadir_deg']):.1f}°"
            cell = photo_only_panel(raw_crop, display_role, note, base_render, regular, bold)
            diagnostics.append(
                {
                    "role": view["role"],
                    "display_role": display_role,
                    "camera_name": name,
                    "selection_source": view["source"],
                    "photo_only_fallback": True,
                    "roofline_rendered": False,
                    "roofline_omission_reason": "NO_BUILDING_SPARSE_CONFIRMATION",
                    "building_sparse_confirmation": False,
                    "crop_source": "PROJECTED_REPRESENTATIVE_ROOF_BOUNDARY_LOOP",
                    "representative_component_id": representative_component_id,
                    "visible_component_ids": [],
                    "visible_component_count": 0,
                    "source_component_count": len(components),
                    "scientific_verdict": None,
                    **topology,
                }
            )
        canvas.paste(cell, (column * int(base_render["cell_width_px"]), int(base_render["row_header_height_px"])))
    return delegate.png_bytes(canvas, base_render), diagnostics


def run(
    config_path: Path,
    repo_root: Path,
    artifact_root: Path,
    output_root: Path,
    source_commit: str,
    image_id: str,
) -> dict[str, Any]:
    config = json.loads(config_path.read_text(encoding="utf-8"))
    fallback = config.get("selection_fallback", {})
    if fallback.get("terminal_fallback_render") != "PHOTO_ONLY_NO_ROOFLINE":
        raise RuntimeError("v6-v4 photo-only terminal fallback contract is not frozen")
    dependency = config["v6_v3_terminal_fallback_dependency"]
    verify_file(
        repo_root / dependency["git_path"],
        dependency["sha256"],
        "v6-v3 terminal fallback dependency",
        int(dependency["bytes"]),
    )

    original_render = terminal_fallback.render_building
    original_file = terminal_fallback.__file__
    terminal_fallback.render_building = render_building
    terminal_fallback.__file__ = str(Path(__file__).resolve())
    try:
        return terminal_fallback.run(
            config_path,
            repo_root,
            artifact_root,
            output_root,
            source_commit,
            image_id,
        )
    finally:
        terminal_fallback.render_building = original_render
        terminal_fallback.__file__ = original_file


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
