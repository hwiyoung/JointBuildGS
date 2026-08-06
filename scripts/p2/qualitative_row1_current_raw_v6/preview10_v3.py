#!/usr/bin/env python3
"""Add a labeled geometry-only fallback when validated camera count is zero."""

from __future__ import annotations

import argparse
from io import BytesIO
import hashlib
import json
from pathlib import Path
import random
from typing import Any, Mapping, Sequence

from PIL import Image, ImageDraw, ImageFont

from scripts.p2.qualitative_row1_current_raw_v3.preview import (
    canonical_json_bytes,
    stable_seed,
    verify_file,
)
from scripts.p2.qualitative_row1_current_raw_v4 import preview10 as v4
from scripts.p2.qualitative_row1_current_raw_v4.preview10 import public_candidate
from scripts.p2.qualitative_row1_current_raw_v6 import preview10 as delegate
from scripts.p2.qualitative_row1_current_raw_v6 import preview10_v2 as validated_selection


REPO = Path(__file__).resolve().parents[3]
DEFAULT_CONFIG = REPO / "configs/p2/qualitative_row1_current_raw_v6/preview10_v3.json"
GEOMETRY_FALLBACK_SOURCE = "GEOMETRY_ONLY_NO_BUILDING_SPARSE_CONFIRMATION"
_TERMINAL_BUILDING_IDS: set[str] = set()
_ORIGINAL_RENDER_BUILDING = delegate.render_building


def scan_sparse_observations(
    path: Path,
    buildings: Sequence[Mapping[str, Any]],
    exact_image_ids: set[int],
    shift: Sequence[float],
    expected_point_count: int,
    cell_size: float = 10.0,
) -> tuple[dict[str, dict[str, Any]], dict[str, int]]:
    support, summary = v4.scan_sparse_observations(
        path, buildings, exact_image_ids, shift, expected_point_count, cell_size
    )
    for building_id in _TERMINAL_BUILDING_IDS:
        if building_id not in support:
            raise RuntimeError(f"terminal fallback building is not in preview: {building_id}")
        observations = support[building_id]["image_observations"]
        for image_id in exact_image_ids:
            observations.setdefault(image_id, [])
    return support, summary


def candidate_record(
    image_id: int,
    image_name: str,
    rows: Sequence[tuple[int, int, Any]],
    observed: Mapping[tuple[int, int], tuple[Any, int]],
    camera: Any,
    building: Mapping[str, Any],
    model: tuple[int, int, Any],
    scene_reference: Mapping[str, Any],
    selection: Mapping[str, Any],
    crop_spec: Mapping[str, Any],
) -> dict[str, Any]:
    record = v4.candidate_record(
        image_id,
        image_name,
        rows,
        observed,
        camera,
        building,
        model,
        scene_reference,
        selection,
        crop_spec,
    )
    record["building_sparse_track_linked"] = bool(rows)
    return record


def geometry_fallback_candidates(
    candidates: Sequence[dict[str, Any]],
) -> list[dict[str, Any]]:
    result = []
    for candidate in candidates:
        representative_id = int(candidate["representative_component_id"])
        if representative_id not in candidate["visible_component_ids_in_crop"]:
            continue
        if "PROJECTED_REPRESENTATIVE_BOUNDARY_TOO_SMALL" in candidate["rejection_reasons"]:
            continue
        result.append(candidate)
    return result


def choose_views(
    building_id: str,
    candidates: Sequence[dict[str, Any]],
    selection: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], str, int, str]:
    if any(candidate["eligible"] for candidate in candidates):
        return validated_selection.choose_views(building_id, candidates, selection)

    roles = [str(value) for value in selection["roles"]]
    seed = stable_seed(str(selection["random_seed_namespace"]), building_id)
    geometry_candidates = geometry_fallback_candidates(candidates)
    pool = [
        public_candidate(row)
        for row in sorted(geometry_candidates, key=lambda row: row["camera_name"])
    ]
    pool_hash = hashlib.sha256(canonical_json_bytes(pool)).hexdigest()
    if not geometry_candidates:
        return [
            {"role": role, "status": "REPRESENTATIVE_ROOF_CAMERA_MISSING", "camera": None}
            for role in roles
        ], "REPRESENTATIVE_ROOF_CAMERA_MISSING", seed, pool_hash

    top = min(
        geometry_candidates,
        key=lambda row: (
            row["nadir_deg"],
            -row["representative_projected_bbox_area_px2"],
            row["camera_name"],
        ),
    )
    remaining = [row for row in geometry_candidates if row is not top]
    random.Random(seed).shuffle(remaining)
    chosen = [top, *remaining[: len(roles) - 1]]
    views = [
        {
            "role": role,
            "status": "SELECTED",
            "source": GEOMETRY_FALLBACK_SOURCE,
            "camera": public_candidate(candidate),
        }
        for role, candidate in zip(roles, chosen)
    ]
    for role in roles[len(views) :]:
        views.append({"role": role, "status": "REPRESENTATIVE_ROOF_CAMERA_MISSING", "camera": None})
    return views, GEOMETRY_FALLBACK_SOURCE, seed, pool_hash


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
    payload, diagnostics = _ORIGINAL_RENDER_BUILDING(
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
    fallback_roles = {
        str(view["role"])
        for view in selection_record["views"]
        if view.get("source") == GEOMETRY_FALLBACK_SOURCE
    }
    if not fallback_roles:
        return payload, diagnostics

    with Image.open(BytesIO(payload)) as opened:
        canvas = opened.convert("RGB")
    draw = ImageDraw.Draw(canvas)
    font = ImageFont.truetype(str(base_render["font_bold_path"]), 20)
    row_header = int(base_render["row_header_height_px"])
    cell_width = int(base_render["cell_width_px"])
    warning = "GEOMETRY-ONLY FALLBACK - NO BUILDING-SPARSE CONFIRMATION"
    for column, view in enumerate(selection_record["views"]):
        if str(view["role"]) not in fallback_roles:
            continue
        x0 = column * cell_width
        draw.rectangle(
            (x0, row_header + 82, x0 + cell_width, row_header + 115),
            fill=tuple(base_render["cell_background_rgb"]),
        )
        draw.text(
            (x0 + cell_width / 2, row_header + 98),
            warning,
            font=font,
            fill=(255, 156, 80),
            anchor="mm",
        )
    for diagnostic in diagnostics:
        if str(diagnostic.get("role")) in fallback_roles:
            diagnostic["geometry_only_fallback"] = True
            diagnostic["building_sparse_confirmation"] = False
            diagnostic["scientific_verdict"] = None
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
    if (
        fallback.get("terminal_fallback_trigger") != "ZERO_VALIDATED_CAMERAS"
        or fallback.get("terminal_fallback_pool")
        != "ALL_EXACT_937_SFM_CAMERAS_WITH_COMPLETE_REPRESENTATIVE_BOUNDARY_IN_FRAME"
        or not fallback.get("terminal_fallback_is_deterministic")
        or not fallback.get("terminal_fallback_has_no_building_sparse_confirmation")
    ):
        raise RuntimeError("v6-v3 terminal fallback contract is not frozen")
    for dependency_name in ("v6_delegate_dependency", "v6_v2_selection_dependency"):
        dependency = config[dependency_name]
        verify_file(
            repo_root / dependency["git_path"],
            dependency["sha256"],
            dependency_name,
            int(dependency["bytes"]),
        )

    global _TERMINAL_BUILDING_IDS
    original_terminal_ids = _TERMINAL_BUILDING_IDS
    _TERMINAL_BUILDING_IDS = set(fallback["preview_zero_validated_building_ids"])
    original_scan = delegate.scan_sparse_observations
    original_candidate = delegate.candidate_record
    original_choose = delegate.choose_views
    original_render = delegate.render_building
    original_file = delegate.__file__
    delegate.scan_sparse_observations = scan_sparse_observations
    delegate.candidate_record = candidate_record
    delegate.choose_views = choose_views
    delegate.render_building = render_building
    delegate.__file__ = str(Path(__file__).resolve())
    try:
        return delegate.run(
            config_path,
            repo_root,
            artifact_root,
            output_root,
            source_commit,
            image_id,
        )
    finally:
        _TERMINAL_BUILDING_IDS = original_terminal_ids
        delegate.scan_sparse_observations = original_scan
        delegate.candidate_record = original_candidate
        delegate.choose_views = original_choose
        delegate.render_building = original_render
        delegate.__file__ = original_file


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
