#!/usr/bin/env python3
"""Publish dense qualitative v4 with truthful photo evidence and reference-only row 4.

The v2 input-only nine-building sample remains frozen.  Row 1 projects both the
evaluation-only reference LoD2 RoofSurface exterior boundary and the exact
target-clipped raw dense class-2 and class-6 arrays used in row 2.  Only datum-correct,
full-frame, surrounding-LoD2-raycast-visible views are eligible; nadir angle is
the primary ranking key.  Dense dots additionally pass positive-depth,
in-frame, full-scene first-hit depth consistency and deterministic pixel-cell
thinning.  Row 3 is the canonical Roofer result, while row 4 is reference LoD2
alone so an output face cannot hide the reference roof shape.

This is an observational publication only: no learning run and no verdict.
"""
from __future__ import annotations

import argparse
import copy
import importlib.util
import json
import math
import os
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any, Mapping, Sequence

os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib")
os.environ.setdefault("XDG_CACHE_HOME", "/tmp/cache")

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import colors as mpl_colors, patheffects
from matplotlib.backends.backend_pdf import PdfPages
from mpl_toolkits.mplot3d.art3d import Poly3DCollection
import numpy as np
from PIL import Image


REPO = Path(__file__).resolve().parents[4]
SCRIPT_DIR = Path(__file__).resolve().parent
for import_root in (SCRIPT_DIR, REPO):
    if str(import_root) not in sys.path:
        sys.path.insert(0, str(import_root))

from src.stage2.image_projection import canonical_to_base  # noqa: E402


def _load_module(path: Path, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot import helper: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


V3 = _load_module(
    SCRIPT_DIR / "fusion_w1_dense_baseline_qualitative_v3_20260728.py",
    "dense_baseline_qualitative_v3_base_for_v4",
)
BASE = V3.BASE

DEFAULT_CONFIG = (
    REPO / "phases/p2-gsjso/configs/fusion_w1/fusion_w1_dense_baseline_qualitative_v4_20260728.json"
)
CONFIG_SCHEMA = "jointbuildgs.fusion_w1.dense_baseline_qualitative.config.v4"
MANIFEST_SCHEMA = "jointbuildgs.fusion_w1.dense_baseline_qualitative.manifest.v4"
EXPECTED_SELECTED = V3.EXPECTED_SELECTED
ROW1_PRIMITIVES = [
    "reference_RoofSurface_exterior_boundary",
    "raw_dense_DIM_MVS_target_class6_points",
    "raw_dense_DIM_MVS_target_class2_points",
]


class DenseBaselineV4Error(V3.DenseBaselineV3Error):
    """A v4 source, visibility, rendering, or publication invariant failed."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise DenseBaselineV4Error(message)


def load_config(path: Path = DEFAULT_CONFIG, *, verify_sources: bool = True) -> dict[str, Any]:
    raw = BASE.read_json(path)
    require(raw.get("schema") == CONFIG_SCHEMA, "v4 config schema drift")
    require(raw.get("branch") == "exp/fusion-w1", "branch contract drift")
    base_spec = raw.get("base_config") or {}
    base_path = BASE.repo_path(str(base_spec.get("path", "")))
    require(base_path.is_file(), "v4 base config absent")
    if verify_sources:
        require(BASE.sha256_file(base_path) == base_spec.get("sha256"), "v4 base config hash drift")
    config = copy.deepcopy(V3.load_config(base_path, verify_sources=verify_sources))
    for key in (
        "schema", "task_id", "run_id", "purpose", "base_config", "implementation_files",
        "sample_freeze", "photo_projection_contract", "visual_overrides", "outputs", "publication",
    ):
        config[key] = copy.deepcopy(raw[key])
    config["visual_contract"]["row_order"][0] = raw["visual_overrides"]["row_1"]
    config["visual_contract"]["row_order"][3] = raw["visual_overrides"]["row_4"]
    config["selection_contract"]["representative_photo_binding"] = (
        "after the input-only nine-building sample freeze: require the surrounding-LoD2 "
        "target-visibility gate and a full-frame minimum-area reference boundary, then rank "
        "primarily by nadir angle; reference geometry does not change the frozen population"
    )
    config["population_contract"]["display_name"] = (
        "dense LoD2 output exists (has_lod22); quality not implied"
    )
    config["population_contract"]["success_definition"] = (
        "has_lod22 means an output exists only; geometric quality is not implied"
    )

    expected_implementation = [
        "phases/p2-gsjso/configs/fusion_w1/fusion_w1_dense_baseline_qualitative_v4_20260728.json",
        "phases/p2-gsjso/scripts/fusion_w1/fusion_w1_dense_baseline_qualitative_v4_20260728.py",
        "phases/p2-gsjso/scripts/fusion_w1/run_fusion_w1_dense_baseline_qualitative_v4_20260728.sh",
        "tests/fusion_w1/test_fusion_w1_dense_baseline_qualitative_v4_20260728.py",
        "phases/p2-gsjso/configs/fusion_w1/fusion_w1_dense_baseline_qualitative_v3_20260728.json",
        "phases/p2-gsjso/scripts/fusion_w1/fusion_w1_dense_baseline_qualitative_v3_20260728.py",
        "phases/p2-gsjso/configs/fusion_w1/fusion_w1_dense_baseline_qualitative_v2_20260728.json",
        "phases/p2-gsjso/scripts/fusion_w1/fusion_w1_dense_baseline_qualitative_v2_20260728.py",
        "scripts/e5_c001/e5_c001_8way.py",
        "phases/p2-gsjso/scripts/fusion_w1/fusion_w1_aprime_job_panel_v4_20260727.py",
        "src/artifact_paths.py",
        "src/stage2/image_projection.py",
    ]
    require(config["implementation_files"] == expected_implementation, "v4 implementation closure drift")
    for value in expected_implementation:
        require(BASE.repo_path(value).is_file(), f"v4 implementation absent: {value}")
    require(tuple(config["sample_freeze"]["selected_building_ids"]) == EXPECTED_SELECTED, "sample freeze drift")
    require(
        BASE.set_sha256(config["sample_freeze"]["selected_building_ids"])
        == config["sample_freeze"]["selected_set_sha256"],
        "sample freeze SHA drift",
    )
    contract = config["photo_projection_contract"]
    require(contract["input_vertical_datum"] == BASE.ORTHOMETRIC, "photo datum drift")
    require(int(contract["additional_pose_transform_application_count"]) == 0, "pose reapplication drift")
    require(contract["allowed_photo_overlays"] == ROW1_PRIMITIVES, "row-1 overlay contract drift")
    for key in (
        "dense_tin_boundary_overlay_forbidden", "footprint_overlay_forbidden",
        "filled_polygon_overlay_forbidden", "interior_ring_overlay_forbidden",
    ):
        require(contract.get(key) is True, f"photo overlay prohibition absent: {key}")
    visibility = contract["visibility_gate"]
    require("first-intersection" in visibility["raycast_engine"], "full-scene visibility engine drift")
    dense = contract["dense_point_visibility"]
    require(int(dense["maximum_source_points_before_raycast"]) >= 1000, "dense raycast budget too small")
    require(float(dense["occlusion_depth_tolerance_m"]) > 0.0, "dense depth tolerance absent")
    require(int(dense["pixel_cell_size"]) >= 1, "dense pixel cell invalid")
    require(int(dense["maximum_display_points"]) >= 100, "dense display budget too small")
    require(config["publication"]["reference_role"] == "evaluation_only", "reference role drift")
    require(config["publication"]["learning_runs_started"] == 0, "learning count drift")
    require(config["publication"]["scientific_verdict"] is None, "scientific verdict must be null")
    return config


def _target_center_canonical(
    reference_rings: Sequence[np.ndarray], scene_reference: Mapping[str, Any], config: Mapping[str, Any]
) -> np.ndarray:
    xyz = np.vstack([V3._closed_ring(ring)[:-1] for ring in reference_rings])
    datum, geoid_m, datum_path = BASE.projection_parameters(config)
    return BASE.base_to_canonical(
        np.median(xyz, axis=0).reshape(1, 3), scene_reference,
        input_datum=datum, geoid_m=geoid_m, config_path=datum_path,
    )[0]


def select_reference_photo_views(
    building_id: str,
    reference_rings: Sequence[np.ndarray],
    views_by_name: Mapping[str, Any],
    scene_reference: Mapping[str, Any],
    image_directory: Path,
    scene: V3.LoD2RaycastScene,
    config: Mapping[str, Any],
) -> list[dict[str, Any]]:
    """Select visible, full-frame photos with near-nadir as the primary rank."""
    contract = config["photo_projection_contract"]
    target = _target_center_canonical(reference_rings, scene_reference, config)
    candidates: list[dict[str, Any]] = []
    for name in sorted(views_by_name):
        view = views_by_name[name]
        image_path = image_directory / name
        if not image_path.is_file():
            continue
        expected_size = (int(view.camera.width), int(view.camera.height))
        with Image.open(image_path) as source:
            observed_size = tuple(int(value) for value in source.size)
        require(observed_size == expected_size, f"camera/image dimensions differ for {name}")
        _rings_uv, receipt = V3.project_reference_roof_boundaries(
            reference_rings, view, scene_reference, config
        )
        if not receipt["all_vertices_valid"] or not receipt["all_vertices_inside_full_frame"]:
            continue
        area = float(receipt["bbox_area_px2"])
        minimum_area = max(
            float(contract["minimum_projected_boundary_bbox_area_px2"]),
            float(contract["minimum_projected_boundary_bbox_fraction"])
            * float(expected_size[0] * expected_size[1]),
        )
        if not math.isfinite(area) or area < minimum_area:
            continue
        visibility = V3.raycast_target_roof_visibility(
            building_id, reference_rings, view, scene_reference, scene, config
        )
        if not visibility["passes_target_roof_visibility_gate"]:
            continue
        delta = np.asarray(view.center_canonical, dtype=np.float64) - target
        horizontal = float(np.linalg.norm(delta[:2]))
        vertical = abs(float(delta[2]))
        nadir = float(math.degrees(math.atan2(horizontal, max(vertical, 1.0e-9))))
        candidates.append(
            {
                "name": name,
                "nadir_deg": nadir,
                "projected_boundary_bbox_area_px2": area,
                "projected_boundary_bbox_area_fraction": float(receipt["bbox_area_fraction"]),
                "projected_boundary_polygon_area_px2": float(receipt["projected_polygon_area_px2"]),
                "frame_center_radius": float(receipt["frame_center_radius"]),
                "all_boundary_vertices_valid": True,
                "all_boundary_vertices_inside_full_frame": True,
                "all_boundary_vertices_inside_margin": bool(receipt["all_vertices_inside_margin"]),
                "reference_roof_exterior_rings_n": int(receipt["rings_n"]),
                "reference_roof_boundary_vertices_n": int(receipt["vertices_n"]),
                "camera_bound_image_dimensions": list(observed_size),
                "visibility": visibility,
            }
        )
    require(bool(candidates), f"no full-frame, minimum-area, raycast-visible photo: {building_id}")
    ranked = sorted(
        candidates,
        key=lambda item: (
            float(item["nadir_deg"]),
            -float(item["visibility"]["visible_target_fraction"]),
            -float(item["projected_boundary_bbox_area_px2"]),
            float(item["frame_center_radius"]),
            str(item["name"]),
        ),
    )
    selected = ranked[:1]
    for index, item in enumerate(selected, start=1):
        item.update(
            {
                "selection_order": index,
                "candidate_count": len(candidates),
                "selection_method": "full_scene_raycast_visible_then_nadir_primary",
                "reference_role": "evaluation_only",
                "reference_geometry_used_for_population_or_sample_selection": False,
                "reference_geometry_used_for_postfreeze_photo_binding": True,
                "image_pixels_used_for_ranking": False,
                "overlay_primitives": list(ROW1_PRIMITIVES),
                "near_nadir_threshold_deg": float(contract["near_nadir_threshold_deg"]),
                "near_nadir_available": bool(
                    float(item["nadir_deg"]) <= float(contract["near_nadir_threshold_deg"])
                ),
            }
        )
    return selected


def _local_scene_triangles(
    building_id: str,
    reference_rings: Sequence[np.ndarray],
    scene: V3.LoD2RaycastScene,
    config: Mapping[str, Any],
) -> tuple[np.ndarray, int]:
    target = np.vstack([V3._closed_ring(ring)[:-1] for ring in reference_rings])
    margin = float(config["photo_projection_contract"]["visibility_gate"]["surrounding_scene_aoi_margin_m"])
    lower = np.min(target[:, :2], axis=0) - margin
    upper = np.max(target[:, :2], axis=0) + margin
    tri_lower = np.min(scene.triangles_xyz[:, :, :2], axis=1)
    tri_upper = np.max(scene.triangles_xyz[:, :, :2], axis=1)
    spatial_mask = (
        (tri_upper[:, 0] >= lower[0]) & (tri_lower[:, 0] <= upper[0])
        & (tri_upper[:, 1] >= lower[1]) & (tri_lower[:, 1] <= upper[1])
    )
    target_mask = np.asarray(scene.building_ids, dtype=object) == str(building_id)
    excluded_n = int(np.count_nonzero(spatial_mask & target_mask))
    mask = spatial_mask & ~target_mask
    values = scene.triangles_xyz[mask]
    require(excluded_n > 0, f"target reference triangles were not found for exclusion: {building_id}")
    require(len(values) > 0, "local non-target LoD2 dense-point visibility mesh empty")
    return values, excluded_n


def project_visible_dense_points(
    building_id: str,
    points: np.ndarray,
    classification: int,
    view: Any,
    scene_reference: Mapping[str, Any],
    reference_rings: Sequence[np.ndarray],
    scene: V3.LoD2RaycastScene,
    config: Mapping[str, Any],
) -> tuple[np.ndarray, dict[str, Any]]:
    """Project the row-2 point source and hide points behind the first LoD2 hit."""
    values = np.asarray(points, dtype=np.float64)[:, :3]
    require(len(values) > 0 and np.all(np.isfinite(values)), "dense points malformed")
    require(int(classification) in {2, 6}, "dense classification must be 2 or 6")
    policy = config["photo_projection_contract"]["dense_point_visibility"]
    considered = BASE.downsample(values, int(policy["maximum_source_points_before_raycast"]))
    datum, geoid_m, datum_path = BASE.projection_parameters(config)
    projection = BASE.project_base_points(
        considered, view.pose, view.camera, scene_reference,
        input_datum=datum, geoid_m=geoid_m, config_path=datum_path,
    )
    in_frame = BASE.in_frame_mask(projection, view.camera)
    candidate_indices = np.flatnonzero(in_frame)
    if not len(candidate_indices):
        return np.empty((0, 2), dtype=np.float64), {
            "source_points_n": len(values), "raycast_input_points_n": len(considered),
            "positive_depth_inframe_points_n": 0, "first_hit_visible_points_n": 0,
            "pixel_thinned_points_n": 0,
            "classification": int(classification),
            "source_identity": (
                f"same in-memory target-clipped raw DIM/MVS class-{int(classification)} "
                "array passed to row 2"
            ),
        }
    camera_base = canonical_to_base(
        np.asarray(view.center_canonical, dtype=np.float64).reshape(1, 3),
        scene_reference, output_datum=datum, geoid_m=geoid_m, config_path=datum_path,
    )[0]
    target_points = considered[candidate_indices]
    vectors = target_points - camera_base[None, :]
    distances = np.linalg.norm(vectors, axis=1)
    valid_distance = np.isfinite(distances) & (distances > 1.0)
    directions = np.zeros_like(vectors)
    directions[valid_distance] = vectors[valid_distance] / distances[valid_distance, None]
    triangles, target_triangles_excluded_n = _local_scene_triangles(
        building_id, reference_rings, scene, config
    )
    nearest = np.full(len(target_points), np.inf, dtype=np.float64)
    if np.any(valid_distance):
        nearest[valid_distance] = V3._nearest_intersection_distances(
            camera_base,
            directions[valid_distance],
            triangles,
            int(config["photo_projection_contract"]["visibility_gate"]["triangle_chunk_size"]),
        )
    tolerance = float(policy["occlusion_depth_tolerance_m"])
    first_hit_visible = valid_distance & (nearest >= distances - tolerance)
    visible_indices = candidate_indices[first_hit_visible]
    visible_uv = np.asarray(projection.uv[visible_indices], dtype=np.float64)
    visible_depth = np.asarray(projection.depth[visible_indices], dtype=np.float64)
    cell_size = int(policy["pixel_cell_size"])
    if len(visible_uv):
        cells = np.floor(visible_uv / float(cell_size)).astype(np.int64)
        order = np.argsort(visible_depth, kind="stable")
        kept: list[int] = []
        occupied: set[tuple[int, int]] = set()
        for offset in order:
            cell = (int(cells[offset, 0]), int(cells[offset, 1]))
            if cell in occupied:
                continue
            occupied.add(cell)
            kept.append(int(offset))
        visible_uv = visible_uv[np.asarray(kept, dtype=np.int64)]
    visible_uv = BASE.downsample(visible_uv, int(policy["maximum_display_points"]))
    return visible_uv, {
        "source_points_n": int(len(values)),
        "classification": int(classification),
        "source_identity": (
            f"same in-memory target-clipped raw DIM/MVS class-{int(classification)} "
            "array passed to row 2"
        ),
        "raycast_input_points_n": int(len(considered)),
        "positive_depth_inframe_points_n": int(len(candidate_indices)),
        "first_hit_visible_points_n": int(np.count_nonzero(first_hit_visible)),
        "pixel_thinned_points_n": int(len(visible_uv)),
        "occlusion_depth_tolerance_m": tolerance,
        "pixel_cell_size": cell_size,
        "local_scene_triangles_n": int(len(triangles)),
        "target_reference_triangles_excluded_n": target_triangles_excluded_n,
        "target_reference_depth_quality_filter_used": False,
        "visibility_method": policy["method"],
        "reference_role_for_occlusion_only": policy["reference_role_for_occlusion_only"],
        "reference_geometry_changes_dense_point_coordinates": False,
    }


def _crop_box(
    projection: Mapping[str, Any], crop_profile: str, config: Mapping[str, Any]
) -> tuple[int, int, int, int]:
    width, height = (int(value) for value in projection["image_size"])
    if crop_profile == "full":
        return (0, 0, width, height)
    lower_x, lower_y, upper_x, upper_y = (float(value) for value in projection["bbox_xyxy"])
    profile = config["photo_projection_contract"]["crop_profiles"][crop_profile]
    span_x, span_y = max(1.0, upper_x - lower_x), max(1.0, upper_y - lower_y)
    padding = float(profile["padding_fraction"])
    desired_width = min(width, max(float(profile["minimum_width_pixels"]), span_x * (1 + 2 * padding)))
    desired_height = min(height, max(float(profile["minimum_height_pixels"]), span_y * (1 + 2 * padding)))
    center_x, center_y = 0.5 * (lower_x + upper_x), 0.5 * (lower_y + upper_y)
    x0, y0 = int(math.floor(center_x - desired_width / 2)), int(math.floor(center_y - desired_height / 2))
    x1, y1 = int(math.ceil(center_x + desired_width / 2)), int(math.ceil(center_y + desired_height / 2))
    if x0 < 0: x1, x0 = x1 - x0, 0
    if y0 < 0: y1, y0 = y1 - y0, 0
    if x1 > width: x0, x1 = x0 - (x1 - width), width
    if y1 > height: y0, y1 = y0 - (y1 - height), height
    box = (max(0, x0), max(0, y0), min(width, x1), min(height, y1))
    require(box[2] > box[0] and box[3] > box[1], "photo crop is empty")
    return box


def projected_photo_panel(
    ax: Any,
    building_id: str,
    image_path: Path,
    view: Any,
    scene_reference: Mapping[str, Any],
    reference_rings: Sequence[np.ndarray],
    class6_points: np.ndarray,
    class2_points: np.ndarray,
    scene: V3.LoD2RaycastScene,
    config: Mapping[str, Any],
    font: Any,
    index: int,
    crop_profile: str,
    view_selection: Mapping[str, Any],
) -> dict[str, Any]:
    uv_rings, projection = V3.project_reference_roof_boundaries(
        reference_rings, view, scene_reference, config
    )
    require(projection["all_vertices_valid"], f"reference projection invalid: {image_path.name}")
    require(projection["all_vertices_inside_full_frame"], f"reference leaves frame: {image_path.name}")
    class6_uv, class6_receipt = project_visible_dense_points(
        building_id, class6_points, 6, view, scene_reference, reference_rings, scene, config
    )
    class2_uv, class2_receipt = project_visible_dense_points(
        building_id, class2_points, 2, view, scene_reference, reference_rings, scene, config
    ) if len(class2_points) else (np.empty((0, 2), dtype=np.float64), {
        "source_points_n": 0, "raycast_input_points_n": 0,
        "positive_depth_inframe_points_n": 0, "first_hit_visible_points_n": 0,
        "pixel_thinned_points_n": 0,
        "classification": 2,
        "source_identity": "same empty target-clipped raw DIM/MVS class-2 array passed to row 2",
    })
    require(
        class6_receipt["first_hit_visible_points_n"] + class2_receipt["first_hit_visible_points_n"]
        >= int(config["photo_projection_contract"]["dense_point_visibility"]["minimum_visible_points"]),
        f"no visible dense point in selected view: {image_path.name}",
    )
    box = _crop_box(projection, crop_profile, config)
    with Image.open(image_path) as source:
        image = source.convert("RGB")
        require(image.size == tuple(projection["image_size"]), "camera/image size drift")
        cropped = np.asarray(image.crop(box))
    ax.imshow(cropped)
    offset = np.asarray([box[0], box[1]], dtype=np.float64)
    visual = config["visual_overrides"]
    class6_inside = (
        (class6_uv[:, 0] >= box[0]) & (class6_uv[:, 0] < box[2])
        & (class6_uv[:, 1] >= box[1]) & (class6_uv[:, 1] < box[3])
    ) if len(class6_uv) else np.zeros(0, dtype=bool)
    class2_inside = (
        (class2_uv[:, 0] >= box[0]) & (class2_uv[:, 0] < box[2])
        & (class2_uv[:, 1] >= box[1]) & (class2_uv[:, 1] < box[3])
    ) if len(class2_uv) else np.zeros(0, dtype=bool)
    local_class6 = class6_uv[class6_inside] - offset
    local_class2 = class2_uv[class2_inside] - offset
    if len(local_class2):
        ax.scatter(
            local_class2[:, 0], local_class2[:, 1],
            s=float(visual["dense_point_size"]) * 0.82,
            c=visual["ground_label_point_color"],
            edgecolors=visual["ground_label_point_edge_color"], linewidths=0.18,
            alpha=float(visual["dense_point_alpha"]) * 0.76, rasterized=True,
            label="raw dense class 2 (ground-labelled, target-clipped)", zorder=2,
        )
    if len(local_class6):
        ax.scatter(
            local_class6[:, 0], local_class6[:, 1],
            s=float(visual["dense_point_size"]), c=visual["dense_point_color"],
            edgecolors=visual["dense_point_edge_color"], linewidths=0.22,
            alpha=float(visual["dense_point_alpha"]), rasterized=True,
            label="raw dense DIM/MVS class 6 (target-clipped)", zorder=3,
        )
    for ring_index, ring_uv in enumerate(uv_rings):
        local = np.asarray(ring_uv, dtype=np.float64) - offset
        line = ax.plot(
            local[:, 0], local[:, 1], color=visual["reference_boundary_color"],
            linewidth=float(visual["reference_boundary_linewidth"]), solid_capstyle="round",
            solid_joinstyle="round", zorder=4,
            label="reference LoD2 roof boundary (evaluation only)" if ring_index == 0 else None,
        )[0]
        line.set_path_effects([
            patheffects.Stroke(
                linewidth=float(visual["reference_boundary_halo_linewidth"]),
                foreground=visual["reference_boundary_halo_color"], alpha=0.80,
            ),
            patheffects.Normal(),
        ])
    ax.axis("off")
    nadir_deg = float(view_selection["nadir_deg"])
    threshold_deg = float(view_selection["near_nadir_threshold_deg"])
    nadir_note = (
        f"near-nadir {nadir_deg:.1f}°"
        if bool(view_selection["near_nadir_available"])
        else f"nadir view unavailable; least-oblique usable={nadir_deg:.1f}°"
    )
    ax.set_title(
        f"사진 {index} · {image_path.name} · {crop_profile}\n"
        f"{nadir_note} · cyan=class 6 · magenta=class 2 · yellow=reference",
        fontproperties=font, fontsize=7.6, color="#252a31", pad=5,
    )
    ax.legend(loc="lower left", fontsize=4.8, framealpha=0.88, markerscale=0.8)
    return {
        "image_name": image_path.name,
        "image_record": BASE.file_record(image_path),
        "crop_xyxy": list(box),
        "crop_profile": crop_profile,
        "nadir_deg": nadir_deg,
        "near_nadir_threshold_deg": threshold_deg,
        "near_nadir_available": bool(view_selection["near_nadir_available"]),
        "overlay_primitives": list(ROW1_PRIMITIVES),
        "reference_role": "evaluation_only",
        "reference_roof_exterior_rings_n": int(projection["rings_n"]),
        "all_boundary_vertices_valid": bool(projection["all_vertices_valid"]),
        "all_boundary_vertices_inside_full_frame": bool(projection["all_vertices_inside_full_frame"]),
        "projected_boundary_bbox_area_px2": float(projection["bbox_area_px2"]),
        "projector": "src/stage2/image_projection.py",
        "input_vertical_datum": projection["input_vertical_datum"],
        "geoid_m": projection["geoid_m"],
        "dense_point_overlay_used": True,
        "dense_points_visible_in_crop_n": int(np.count_nonzero(class6_inside) + np.count_nonzero(class2_inside)),
        "dense_class6_points_visible_in_crop_n": int(np.count_nonzero(class6_inside)),
        "dense_class2_points_visible_in_crop_n": int(np.count_nonzero(class2_inside)),
        "dense_projection_by_class": {"2": class2_receipt, "6": class6_receipt},
        "dense_tin_boundary_overlay_used": False,
        "footprint_overlay_used": False,
        "filled_polygon_overlay_used": False,
        "interior_ring_overlay_used": False,
    }


def plot_reference_only(
    ax: Any, reference_rings: Sequence[np.ndarray], frame: Mapping[str, Any], config: Mapping[str, Any]
) -> int:
    """Render reference RoofSurface faces alone, with shaded planes and strong edges."""
    visual = config["visual_overrides"]
    base_rgb = np.asarray(mpl_colors.to_rgb(visual["reference_surface_face_color"]), dtype=np.float64)
    edge = visual["reference_surface_edge_color"]
    light = np.asarray([0.30, -0.40, 0.85], dtype=np.float64)
    light /= np.linalg.norm(light)
    origin = np.asarray(frame["local_origin_epsg25832_xyz"], dtype=np.float64)
    faces_n = 0
    for ring in reference_rings:
        closed = V3._closed_ring(ring)
        local = closed[:, :3] - origin
        plane = local[:-1]
        normal = np.cross(plane[1] - plane[0], plane[2] - plane[0]) if len(plane) >= 3 else np.zeros(3)
        norm = float(np.linalg.norm(normal))
        illumination = abs(float(np.dot(normal / norm, light))) if norm > 1.0e-12 else 0.5
        shade = 0.63 + 0.32 * illumination
        face = np.clip(base_rgb * shade + (1.0 - shade), 0.0, 1.0)
        collection = Poly3DCollection(
            [plane], facecolors=[face], edgecolors=edge, linewidths=1.15,
            alpha=float(visual["reference_surface_alpha"]), antialiased=True,
        )
        collection.set_zsort("average")
        ax.add_collection3d(collection)
        ax.plot(local[:, 0], local[:, 1], local[:, 2], color=edge, linewidth=1.45)
        faces_n += 1
    return faces_n


def reference_only_frame(
    reference_rings: Sequence[np.ndarray],
    shared_frame: Mapping[str, Any],
    config: Mapping[str, Any],
) -> dict[str, Any]:
    """Fit bounds to reference alone while preserving the four shared camera directions."""
    xyz = np.vstack([V3._closed_ring(ring)[:-1, :3] for ring in reference_rings])
    require(len(xyz) >= 3 and np.all(np.isfinite(xyz)), "reference-only frame source malformed")
    minimum, maximum = xyz.min(axis=0), xyz.max(axis=0)
    origin = np.asarray([
        round(float((minimum[0] + maximum[0]) / 2.0), 3),
        round(float((minimum[1] + maximum[1]) / 2.0), 3),
        round(float(minimum[2]), 3),
    ])
    local_minimum, local_maximum = minimum - origin, maximum - origin
    actual_span = local_maximum - local_minimum
    horizontal_scale = max(float(actual_span[0]), float(actual_span[1]), 1.0)
    display_span = np.maximum(actual_span, np.asarray([0.25, 0.25, max(0.5, horizontal_scale * 0.04)]))
    padding = display_span * float(config["visual_contract"]["camera_contract"]["bounds_padding_fraction"])
    bounds = np.column_stack((local_minimum - padding, local_maximum + padding))
    return {
        "crs": "EPSG:25832",
        "bounds_source": "evaluation_only_reference_RoofSurface_exterior_XYZ_only",
        "view_orientation_source": "copied_from_rows_2_and_3_for_directional_comparability",
        "reference_view_orientation_influence": False,
        "reference_shared_bounds_influence": False,
        "local_origin_epsg25832_xyz": [float(value) for value in origin],
        "local_bounds_xyz": [[float(value) for value in pair] for pair in bounds],
        "source_minimum_xyz": [float(value) for value in minimum],
        "source_maximum_xyz": [float(value) for value in maximum],
        "source_actual_span_xyz": [float(value) for value in actual_span],
        "z_exaggeration": 1.0,
        "axis": copy.deepcopy(shared_frame["axis"]),
        "cameras": copy.deepcopy(shared_frame["cameras"]),
    }


def render_building(
    staging: Path,
    pdf: PdfPages,
    config: Mapping[str, Any],
    selection_row: Mapping[str, Any],
    quality_row: Mapping[str, str],
    class6_points: np.ndarray,
    class2_points: np.ndarray,
    surfaces: Sequence[Mapping[str, Any]],
    surface_stats: Mapping[str, Any],
    reference_rings: Sequence[np.ndarray],
    status_row: Mapping[str, str],
    photo_views: Sequence[Mapping[str, Any]],
    projection_views_by_name: Mapping[str, Any],
    scene_reference: Mapping[str, Any],
    raycast_scene: V3.LoD2RaycastScene,
    font: Any,
) -> dict[str, Any]:
    building_id = str(selection_row["building_id"])
    require(len(class6_points) > 0 and bool(reference_rings), f"missing evidence: {building_id}")
    all_points = np.vstack((class2_points, class6_points)) if len(class2_points) else class6_points
    frame = BASE.scene_frame(all_points, surfaces, reference_rings, config)
    evidence = {"cityjson_surfaces": surfaces, "reference_rings": reference_rings}
    helper_config = BASE.render_config(config)
    comparison = BASE.output_reference_facts(surfaces, reference_rings)
    visual = config["visual_contract"]
    fig = plt.figure(figsize=tuple(visual["panel_inches"]))
    grid = fig.add_gridspec(4, 5, left=0.043, right=0.987, bottom=0.060, top=0.902, wspace=0.16, hspace=0.25)
    size_field, obs_field = "stratum_size_area", "stratum_observation_recon_score"
    fig.suptitle(
        f"{building_id} | size={selection_row[size_field]} × observation={selection_row[obs_field]}\n"
        "P0 raw dense DIM/MVS -> Roofer | LoD2 output exists (has_lod22); quality not implied | scientific_verdict: null",
        fontproperties=font, fontsize=14.2, color="#252a31",
    )
    for y, label in (
        (0.790, "1  사진+입력점+참조경계 / Photo + dense + ref boundary"),
        (0.575, "2  DIM class 2+6 / Classified dense"),
        (0.360, "3  P0 Roofer / Canonical output"),
        (0.145, "4  참조 LoD2 단독 / Reference LoD2 only"),
    ):
        fig.text(0.008, y, label, rotation=90, va="center", ha="center", fontsize=7.5, color="#252a31", fontproperties=font)

    image_directory = BASE.repo_path(config["sources"]["image_directory"]["path"])
    slots = V3.photo_slot_plan(photo_views)
    photo_receipts: list[dict[str, Any]] = []
    for column, slot in enumerate(slots):
        view_receipt = slot["view"]
        image_name = str(view_receipt["name"])
        receipt = projected_photo_panel(
            fig.add_subplot(grid[0, column]), building_id, image_directory / image_name,
            projection_views_by_name[image_name], scene_reference, reference_rings,
            class6_points, class2_points, raycast_scene, config, font,
            column + 1, str(slot["crop_profile"]), view_receipt,
        )
        receipt["photo_selection"] = dict(view_receipt)
        receipt["slot_policy"] = {
            "slot_order": int(slot["slot_order"]), "crop_profile": str(slot["crop_profile"]),
            "unique_visible_views_n": int(slot["unique_visible_views_n"]),
            "occluded_view_substitution_used": False,
        }
        photo_receipts.append(receipt)

    input_lines = [
        "표본 모집단: LoD2 output exists (has_lod22); quality not implied",
        f"coverage_frac: {float(selection_row['coverage_frac']):.6f}",
        f"nodata_fraction: {1.0 - float(selection_row['coverage_frac']):.6f}",
        f"n_views_nadir: {float(selection_row['n_views_nadir']):.6f}",
        f"rf_rmse_lod22: {float(quality_row['rf_rmse_lod22']):.6f} m",
        f"raw dense target points: class 6={len(class6_points)}, class 2={len(class2_points)}",
        f"reference RoofSurface exterior rings: {len(reference_rings)}",
        "cyan/magenta: exact row-2 class 6/class 2 sources projected",
        "yellow/black: reference roof boundary (evaluation only)",
        "one view only: least-oblique usable after full-frame + area + raycast visibility",
        f"selected angle: {float(photo_views[0]['nadir_deg']):.2f}°; near-nadir threshold: {float(photo_views[0]['near_nadir_threshold_deg']):.1f}°",
        "no occluded-view substitution",
        "no TIN boundary, footprint, polygon fill, or interior ring in row 1",
        "sample frozen before reference GML access",
        "reference affects photo address/visibility only after sample freeze",
        "NO GS TRAINING | learning_runs=0 | scientific_verdict: null",
    ]
    BASE.text_panel(fig.add_subplot(grid[0, 3:5]), "사진·입력 이력 / Photo and input provenance", input_lines, font)

    displayed_points_class6 = 0
    displayed_points_class2 = 0
    for column, camera in enumerate(frame["cameras"]):
        ax = fig.add_subplot(grid[1, column], projection="3d")
        shown2 = BASE.downsample(class2_points, int(visual["maximum_scatter_points"]))
        shown6 = BASE.downsample(class6_points, int(visual["maximum_scatter_points"]))
        if len(shown2):
            local2 = BASE.PANEL_V4.local_xyz(shown2, frame)
            ax.scatter(
                local2[:, 0], local2[:, 1], local2[:, 2], s=2.6,
                c=config["visual_overrides"]["ground_label_point_color"],
                linewidths=0, alpha=0.62, depthshade=False, rasterized=True,
                label="class 2 ground-labelled",
            )
        local6 = BASE.PANEL_V4.local_xyz(shown6, frame)
        ax.scatter(
            local6[:, 0], local6[:, 1], local6[:, 2], s=3.0,
            c=config["visual_overrides"]["dense_point_color"],
            linewidths=0, alpha=0.88, depthshade=False, rasterized=True,
            label="class 6 building",
        )
        displayed_points_class2, displayed_points_class6 = len(shown2), len(shown6)
        BASE.PANEL_V4.configure_3d_axis(ax, frame, camera)
        BASE.PANEL_V4.short_title(ax, f"DIM/MVS class 2+6 · {camera['title_ko']}", f"Target-clipped classified dense · {camera['title_en']}", font, fontsize=8.0)
        ax.legend(loc="lower left", fontsize=4.7, framealpha=0.82)
    ax = fig.add_subplot(grid[1, 4])
    origin = np.asarray(frame["local_origin_epsg25832_xyz"], dtype=np.float64)
    principal = np.asarray(frame["axis"]["vector_east_north"], dtype=np.float64)
    for shown, color, label, alpha in (
        (BASE.downsample(class2_points, int(visual["maximum_scatter_points"])), config["visual_overrides"]["ground_label_point_color"], "class 2", 0.62),
        (BASE.downsample(class6_points, int(visual["maximum_scatter_points"])), config["visual_overrides"]["dense_point_color"], "class 6", 0.88),
    ):
        if not len(shown):
            continue
        horizontal = (shown[:, :2] - origin[:2]) @ principal
        ax.scatter(horizontal, shown[:, 2] - origin[2], s=2.0, color=color, linewidths=0, alpha=alpha, rasterized=True, label=label)
    ax.set_xlabel("principal horizontal (m)", fontsize=7); ax.set_ylabel("ΔZ (m)", fontsize=7)
    ax.grid(True, color=visual["palette"]["light_grey"], linewidth=0.45); ax.tick_params(labelsize=6)
    ax.set_aspect("equal", adjustable="datalim")
    ax.legend(loc="lower left", fontsize=5.0, framealpha=0.82)
    BASE.PANEL_V4.short_title(ax, "DIM class 2+6 주축 단면", "Principal section · classified dense", font, fontsize=8.0)

    cityjson_render = BASE.PANEL_V4.cityjson_render_parts(surfaces, frame)["stats"]
    for column, camera in enumerate(frame["cameras"]):
        ax = fig.add_subplot(grid[2, column], projection="3d")
        BASE.PANEL_V4.plot_cityjson(ax, evidence, frame, helper_config, alpha=0.92)
        BASE.PANEL_V4.configure_3d_axis(ax, frame, camera)
        BASE.PANEL_V4.short_title(ax, f"P0 DIM Roofer · {camera['title_ko']}", f"Canonical CityJSON · {camera['title_en']}", font, fontsize=8.0)
    semantic = surface_stats["semantic_counts"]
    output_lines = [
        "canonical P0 DIM Roofer CityJSON LoD2.2",
        "IMPORTANT: Roofer input includes approved/reference-derived",
        "LoD2 GroundSurface XY footprint",
        "assembled/valid shell != geometric quality",
        f"coverage_frac / n_views_nadir: {float(selection_row['coverage_frac']):.6f} / {float(selection_row['n_views_nadir']):.6f}",
        f"rf_rmse_lod22: {float(quality_row['rf_rmse_lod22']):.6f} m",
        f"LoD / surfaces / vertices: {surface_stats['lod']:.1f} / {surface_stats['surfaces_n']} / {surface_stats['vertices_n']}",
        f"Roof / Wall / Ground: {semantic.get('RoofSurface', 0)} / {semantic.get('WallSurface', 0)} / {semantic.get('GroundSurface', 0)}",
        f"wireframe-only hole surfaces: {cityjson_render['wireframe_only_surfaces_n']}",
        f"status / has_lod22: {status_row.get('status', 'n/a')} / {status_row.get('has_lod22', 'n/a')}",
        f"val3dity valid: {status_row.get('val3dity_valid', 'n/a')}",
        "scientific_verdict: null",
    ]
    BASE.text_panel(fig.add_subplot(grid[2, 4]), "정본 출력·품질 주의 / Output and quality caveat", output_lines, font)

    reference_faces = 0
    reference_frame = reference_only_frame(reference_rings, frame, config)
    for column, camera in enumerate(frame["cameras"]):
        ax = fig.add_subplot(grid[3, column], projection="3d")
        reference_faces = plot_reference_only(ax, reference_rings, reference_frame, config)
        BASE.PANEL_V4.configure_3d_axis(ax, reference_frame, camera)
        BASE.PANEL_V4.short_title(ax, f"참조 LoD2만 · {camera['title_ko']} (평가 전용)", f"Reference LoD2 ONLY · {camera['title_en']}", font, fontsize=8.0)
    comparison_lines = [
        "THIS ROW: reference LoD2 RoofSurface ONLY",
        "no Roofer output faces or lines in the four view cells",
        "light orange faces + dark orange exterior edges",
        f"reference roof faces: {reference_faces}",
        "bounds: reference RoofSurface XYZ only",
        "camera directions: copied unchanged from rows 2-3",
        "reference role: evaluation only",
        "projection: orthographic | Z exaggeration: 1.0×",
        "",
        f"exact XY coordinate set equal: {comparison['exact_XY_coordinate_set_equal']}",
        f"exact XYZ coordinate set equal: {comparison['exact_XYZ_coordinate_set_equal']}",
        f"unique XY output/ref: {comparison['output_unique_xy_n']} / {comparison['reference_unique_xy_n']}",
        f"output Z: {comparison['output_z_min_m']:.3f}–{comparison['output_z_max_m']:.3f} m",
        f"reference Z: {comparison['reference_z_min_m']:.3f}–{comparison['reference_z_max_m']:.3f} m",
        "comparison facts only; output remains displayed in row 3",
        "CRS: EPSG:25832 | scientific_verdict: null",
    ]
    BASE.text_panel(fig.add_subplot(grid[3, 4]), "참조 단독·비교 이력 / Reference-only and comparison receipt", comparison_lines, font)
    fig.text(
        0.5, 0.022,
        "P0 raw dense DIM/MVS -> Roofer · approved/reference-derived GroundSurface XY footprint used by Roofer · reference roof is evaluation only · scientific_verdict: null",
        ha="center", va="center", fontsize=7.2, color="#252a31", fontproperties=font,
    )
    panel_directory = staging / config["outputs"]["panel_directory"]
    panel_directory.mkdir(parents=True, exist_ok=True)
    panel_path = panel_directory / config["outputs"]["panel_template"].format(building_id=building_id)
    require(not panel_path.exists(), f"panel overwrite refused: {panel_path}")
    fig.savefig(panel_path, dpi=int(visual["panel_dpi"]), facecolor="white", metadata={"Software": "JointBuildGS dense qualitative v4"})
    pdf.savefig(fig, facecolor="white")
    plt.close(fig)
    with Image.open(panel_path) as rendered:
        width, height = rendered.size
    return {
        "building_id": building_id,
        "cell": {size_field: selection_row[size_field], obs_field: selection_row[obs_field]},
        "quality_observations": {
            "coverage_frac": float(selection_row["coverage_frac"]),
            "n_views_nadir": float(selection_row["n_views_nadir"]),
            "rf_rmse_lod22_m": float(quality_row["rf_rmse_lod22"]),
            "assembled_shell_is_not_geometric_quality": True,
        },
        "roofer_input_disclosure": "approved/reference-derived LoD2 GroundSurface XY footprint",
        "panel": BASE.bundle_record(staging, panel_path),
        "photo_receipts": photo_receipts,
        "unique_raycast_visible_photo_views_n": len(photo_views),
        "occluded_view_substitution_used": False,
        "row_1_overlay_primitives": list(ROW1_PRIMITIVES),
        "row_1_dense_sources_same_arrays_as_row_2": {"class_2": True, "class_6": True},
        "row_4_primitives": ["evaluation_only_reference_LoD2_RoofSurface_faces_and_exterior_edges"],
        "row_4_roofer_output_used": False,
        "row_4_reference_only_frame": reference_frame,
        "dense_class6_points_n": len(class6_points),
        "dense_class2_points_n": len(class2_points),
        "dense_target_points_n": len(all_points),
        "dense_class6_points_displayed_per_geometry_view": displayed_points_class6,
        "dense_class2_points_displayed_per_geometry_view": displayed_points_class2,
        "classification_leakage_observation": {
            "class2_inside_target_footprint_n": len(class2_points),
            "class6_inside_target_footprint_n": len(class6_points),
            "class2_median_z_m": float(np.median(class2_points[:, 2])) if len(class2_points) else None,
            "class6_median_z_m": float(np.median(class6_points[:, 2])),
            "interpretation": None,
        },
        "cityjson": dict(surface_stats),
        "comparison": comparison,
        "frame": frame,
        "render_pixels": [width, height],
        "scientific_verdict": None,
        "interpretation": None,
    }


def read_target_points_by_class(
    cloud_cache: Any,
    source: Any,
    building_id: str,
    classifications: Sequence[int] = (2, 6),
) -> dict[int, np.ndarray]:
    """Use the same locked point source/footprint clip, retaining class labels."""
    path = cloud_cache.pointcloud_path(source, building_id)
    require(path is not None and path.is_file(), f"dense point source absent: {building_id}")
    x, y, z, cls = cloud_cache._read(path)
    polygon = cloud_cache.footprints[building_id]
    min_x, min_y, max_x, max_y = polygon.bounds
    bbox = (x >= min_x) & (x <= max_x) & (y >= min_y) & (y <= max_y)
    indices = np.flatnonzero(bbox)
    if len(indices):
        indices = indices[BASE.E5.contains_xy(polygon, x[indices], y[indices])]
    result: dict[int, np.ndarray] = {}
    for classification in classifications:
        chosen = indices[cls[indices] == int(classification)] if len(indices) else indices
        result[int(classification)] = (
            np.column_stack((x[chosen], y[chosen], z[chosen]))
            if len(chosen) else np.empty((0, 3), dtype=np.float64)
        )
    return result


def load_raw_reference_roof_exterior_rings(
    reference_paths: Sequence[Path], building_ids: Sequence[str] | set[str]
) -> dict[str, list[np.ndarray]]:
    """Extract original GML RoofSurface exterior XYZ without plane refitting."""
    wanted = {str(value) for value in building_ids}
    output: dict[str, list[np.ndarray]] = {value: [] for value in wanted}
    for path in reference_paths:
        try:
            for _event, building in V3.ET.iterparse(path, events=("end",)):
                if V3._local_name(building.tag) != "Building":
                    continue
                building_id = V3._element_id(building)
                if building_id in wanted:
                    for surface in building.iter():
                        if V3._local_name(surface.tag) != "RoofSurface":
                            continue
                        for polygon in surface.iter():
                            if V3._local_name(polygon.tag) != "Polygon":
                                continue
                            exteriors = [
                                child for child in polygon.iter()
                                if V3._local_name(child.tag) == "exterior"
                            ]
                            require(len(exteriors) == 1, f"RoofSurface exterior count drift: {building_id}")
                            ring = V3._poslist_ring(exteriors[0])
                            if ring is not None:
                                output[building_id].append(V3._closed_ring(ring))
                building.clear()
        except (OSError, V3.ET.ParseError) as exc:
            raise DenseBaselineV4Error(f"cannot parse raw reference roof rings {path}: {exc}") from exc
    missing = sorted(building_id for building_id, rings in output.items() if not rings)
    require(not missing, f"raw reference RoofSurface exterior XYZ absent: {missing}")
    return output


def _prepare(config: Mapping[str, Any]) -> dict[str, Any]:
    result = BASE.select_sample(config)
    selected_order = tuple(str(row["building_id"]) for row in result.selected)
    require(selected_order == EXPECTED_SELECTED, "v4 selected sample differs from freeze")
    selected_ids = set(selected_order)
    footprints, footprint_record = BASE.load_locked_footprints(config, selected_ids)
    dense_source = BASE.E5.Source(
        source_group="raw_dense", source_run="raw_dense", display_label="raw dense (DIM/MVS)",
        status_role="baseline", status_path=None, status_input="DIM", cityjson_path=None,
        pointcloud_path=BASE.repo_path(config["sources"]["dense_classified_laz"]["path"]),
    )
    cloud_cache = BASE.E5.PointCloudCache(footprints)
    points_by_class_by_id = {
        bid: read_target_points_by_class(cloud_cache, dense_source, bid) for bid in selected_order
    }
    points_by_id = {bid: values[6] for bid, values in points_by_class_by_id.items()}
    for building_id, points in points_by_id.items():
        require(len(points) > 0, f"selected building has no class-6 points: {building_id}")
    cityjson_payload = BASE.read_json(BASE.repo_path(config["sources"]["canonical_roofer_cityjson"]["path"]))
    output_by_id = {bid: BASE.load_cityjson_surfaces_for_building(cityjson_payload, bid) for bid in selected_order}

    reference_directory = BASE.repo_path(config["sources"]["reference_gml_directory"]["path"])
    reference_paths = sorted(reference_directory.glob("*.gml"))
    require(bool(reference_paths), "reference GML files absent")
    reference_rings_by_id = load_raw_reference_roof_exterior_rings(reference_paths, selected_ids)
    raycast_scene = V3.build_surrounding_lod2_scene(reference_paths, reference_rings_by_id, config)
    scene_reference = BASE.read_json(BASE.repo_path(config["sources"]["scene_reference_frame"]["path"]))
    projection_views = BASE.load_projection_views(config)
    image_directory = BASE.repo_path(config["sources"]["image_directory"]["path"])
    photo_views_by_id = {
        bid: select_reference_photo_views(
            bid, reference_rings_by_id[bid], projection_views, scene_reference,
            image_directory, raycast_scene, config,
        )
        for bid in selected_order
    }
    selected_image_paths = [image_directory / view["name"] for bid in selected_order for view in photo_views_by_id[bid]]
    status_rows = [
        row for row in BASE.read_csv(BASE.repo_path(config["sources"]["canonical_roofer_status"]["path"]))
        if row.get("input") == "DIM" and row.get("building_id") in selected_ids
    ]
    status_by_id = BASE._unique_by(status_rows, "building_id", 9, "canonical DIM Roofer status sample")
    quality_by_id = {bid: result.raw_dense_by_id[bid] for bid in selected_order}
    for bid, row in quality_by_id.items():
        require(math.isfinite(float(row["rf_rmse_lod22"])), f"rf_rmse_lod22 absent: {bid}")
    return {
        "result": result, "selected_order": selected_order, "footprint_record": footprint_record,
        "points_by_id": points_by_id, "points_by_class_by_id": points_by_class_by_id,
        "output_by_id": output_by_id,
        "reference_rings_by_id": reference_rings_by_id, "reference_paths": reference_paths,
        "raycast_scene": raycast_scene, "scene_reference": scene_reference,
        "projection_views": projection_views, "photo_views_by_id": photo_views_by_id,
        "selected_image_paths": selected_image_paths, "status_by_id": status_by_id,
        "quality_by_id": quality_by_id,
    }


def publish(config: Mapping[str, Any], output_root: Path | None = None) -> dict[str, Any]:
    prepared = _prepare(config)
    result = prepared["result"]
    root = BASE.repo_path(config["outputs"]["root"]) if output_root is None else output_root.resolve()
    require(not root.exists(), f"output root exists; overwrite refused: {root}")
    root.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{root.name}.staging.", dir=root.parent))
    try:
        font, font_record = BASE.load_font(config)
        BASE.write_csv_new(staging / config["outputs"]["selection_audit_csv"], result.audit_rows)
        selection_payload = BASE.selection_audit_payload(config, result)
        selection_payload["schema"] = "jointbuildgs.fusion_w1.dense_baseline_qualitative.selection_audit.v4"
        selection_payload["postfreeze_photo_binding"] = {
            "input": "evaluation-only reference RoofSurface boundary and full-scene visibility",
            "ranking": "nadir angle primary after eligibility",
            "population_or_sample_selection_influence": False,
        }
        BASE.write_json_new(staging / config["outputs"]["selection_audit_json"], selection_payload)
        sources_before = BASE.fixed_source_snapshot(config, prepared["selected_image_paths"], prepared["reference_paths"])
        panel_receipts: list[dict[str, Any]] = []
        pdf_path = staging / config["outputs"]["multipage_pdf"]
        with PdfPages(pdf_path, metadata={
            "Title": "P0 dense qualitative v4 truthful photo evidence",
            "Subject": "NO GS TRAINING; dense photo projection; reference-only row 4; verdict null",
            "Creator": "JointBuildGS",
        }) as pdf:
            for row in result.selected:
                bid = str(row["building_id"])
                surfaces, stats = prepared["output_by_id"][bid]
                panel_receipts.append(render_building(
                    staging, pdf, config, row, prepared["quality_by_id"][bid],
                    prepared["points_by_class_by_id"][bid][6],
                    prepared["points_by_class_by_id"][bid][2], surfaces, stats,
                    prepared["reference_rings_by_id"][bid], prepared["status_by_id"][bid],
                    prepared["photo_views_by_id"][bid], prepared["projection_views"],
                    prepared["scene_reference"], prepared["raycast_scene"], font,
                ))
        require(pdf_path.is_file() and pdf_path.stat().st_size > 0, "multipage PDF absent")
        overview_record = BASE.render_overview(staging, config, panel_receipts, font)
        sources_after = BASE.fixed_source_snapshot(config, prepared["selected_image_paths"], prepared["reference_paths"])
        require(sources_after == sources_before, "source inputs changed while rendering")
        outputs = BASE.output_records(staging, config["outputs"]["manifest"])
        output_set_hash = BASE.set_sha256(f"{r['path']}|{r['sha256']}|{r['bytes']}" for r in outputs)
        manifest = {
            "schema": MANIFEST_SCHEMA, "created_utc": BASE.utc_now(), "state": "COMPLETE",
            "task_id": config["task_id"], "run_id": config["run_id"], "branch": config["branch"],
            "population": {
                "count": len(result.population_ids), "set_sha256": result.population_set_sha256,
                "display_name": "dense LoD2 output exists (has_lod22); quality not implied",
                "success_definition": "has_lod22 only; assembled/valid shell is not geometric quality",
            },
            "selection": {
                "sample_count": len(result.selected), "selected_building_ids": list(prepared["selected_order"]),
                "selected_set_sha256": BASE.set_sha256(prepared["selected_order"]),
                "population_or_sample_selector_reference_influence": False,
                "postfreeze_photo_binding_input": "evaluation-only reference roof plus full-scene visibility",
                "postfreeze_view_ranking": "nadir_primary",
            },
            "render_contract": {
                "layout": "4_rows_x_5_columns", "individual_panel_count": len(panel_receipts),
                "single_multipage_pdf": True, "overview": overview_record,
                "row_1_overlay_primitives": list(ROW1_PRIMITIVES),
                "row_1_dense_source": "exact target-clipped raw DIM/MVS class-2 and class-6 arrays used in row 2, labels retained",
                "row_1_dense_visibility": config["photo_projection_contract"]["dense_point_visibility"],
                "row_1_forbidden_overlays": ["dense_TIN_boundary", "footprint", "polygon_fill", "interior_rings"],
                "row_2": "raw dense DIM/MVS target class-2 and class-6 points as separate layers",
                "row_3": "canonical P0 DIM Roofer CityJSON output",
                "row_4": "evaluation-only reference LoD2 RoofSurface faces and exterior edges ONLY",
                "row_4_roofer_output_used": False,
                "row_4_bounds": "reference RoofSurface original XYZ only; camera directions copied from rows 2-3",
                "reference_roof_geometry_source": "direct raw GML RoofSurface exterior XYZ; no plane refit",
                "geometry_rows_camera_projection": "orthographic", "geometry_rows_z_exaggeration": 1.0,
                "photo_projection": config["photo_projection_contract"],
            },
            "roofer_input_disclosure": {
                "approved_reference_derived_lod2_groundsurface_xy_footprint_used": True,
                "assembled_or_valid_shell_equals_geometric_quality": False,
            },
            "per_building_quality_observations": {
                receipt["building_id"]: receipt["quality_observations"] for receipt in panel_receipts
            },
            "per_building_classification_observations": {
                receipt["building_id"]: receipt["classification_leakage_observation"]
                for receipt in panel_receipts
            },
            "surrounding_lod2_raycast_scene": dict(prepared["raycast_scene"].stats),
            "panel_receipts": panel_receipts, "source_records": list(sources_before.values()),
            "footprint_GeoPackage_record": prepared["footprint_record"],
            "footprint_role": "target clipping and Roofer input provenance; never overlaid on row-1 photos",
            "font": font_record, "outputs": outputs, "output_set_sha256": output_set_hash,
            "reference_role": "evaluation_only", "learning_runs_started": 0,
            "new_training_runs": 0, "scientific_verdict": None, "interpretation": None,
        }
        BASE.write_json_new(staging / config["outputs"]["manifest"], manifest)
        require(not root.exists(), "output appeared before atomic publication")
        os.replace(staging, root)
        return manifest
    except Exception:
        if staging.exists() and staging.parent == root.parent and staging.name.startswith(f".{root.name}.staging."):
            shutil.rmtree(staging)
        raise


def verify_bundle(config: Mapping[str, Any], output_root: Path | None = None) -> dict[str, Any]:
    root = BASE.repo_path(config["outputs"]["root"]) if output_root is None else output_root.resolve()
    require(root.is_dir(), f"output bundle absent: {root}")
    manifest = BASE.read_json(root / config["outputs"]["manifest"])
    require(manifest.get("schema") == MANIFEST_SCHEMA, "v4 manifest schema drift")
    require(manifest.get("state") == "COMPLETE", "v4 manifest is not COMPLETE")
    require(manifest.get("scientific_verdict") is None, "manifest contains a verdict")
    require(tuple(manifest["selection"]["selected_building_ids"]) == EXPECTED_SELECTED, "manifest sample drift")
    render = manifest.get("render_contract") or {}
    require(render.get("row_1_overlay_primitives") == ROW1_PRIMITIVES, "row-1 primitive drift")
    require(render.get("row_4_roofer_output_used") is False, "Roofer leaked into reference-only row")
    require((manifest.get("roofer_input_disclosure") or {}).get("approved_reference_derived_lod2_groundsurface_xy_footprint_used") is True, "Roofer footprint disclosure absent")
    source_records_n = BASE.verify_source_records(manifest.get("source_records"))
    records = manifest.get("outputs") or []
    for record in records:
        path = root / record["path"]
        require(path.is_file(), f"published output absent: {record['path']}")
        require(path.stat().st_size == int(record["bytes"]), f"published size drift: {record['path']}")
        require(BASE.sha256_file(path) == record["sha256"], f"published hash drift: {record['path']}")
    observed_hash = BASE.set_sha256(f"{r['path']}|{r['sha256']}|{r['bytes']}" for r in records)
    require(observed_hash == manifest.get("output_set_sha256"), "output set hash drift")
    for receipt in manifest.get("panel_receipts", []):
        require(receipt.get("row_1_overlay_primitives") == ROW1_PRIMITIVES, "panel row-1 drift")
        require(
            receipt.get("row_1_dense_sources_same_arrays_as_row_2")
            == {"class_2": True, "class_6": True},
            "dense source identity drift",
        )
        require(receipt.get("row_4_roofer_output_used") is False, "panel row-4 output leak")
        require(len(receipt.get("photo_receipts", [])) == 3, "photo slot count drift")
        for photo in receipt["photo_receipts"]:
            require(photo.get("dense_point_overlay_used") is True, "dense photo overlay absent")
            require(photo.get("dense_points_visible_in_crop_n", 0) >= 1, "dense overlay crop empty")
            require((photo.get("photo_selection") or {}).get("visibility", {}).get("passes_target_roof_visibility_gate") is True, "occluded photo published")
            require(photo.get("dense_tin_boundary_overlay_used") is False, "TIN boundary used")
    panels = sorted((root / config["outputs"]["panel_directory"]).glob("*.png"))
    require(len(panels) == 9, "published panel count drift")
    return {
        "state": "VERIFIED", "root": str(root), "panels": len(panels),
        "outputs": len(records), "source_records": source_records_n,
        "row_1_overlay_primitives": list(ROW1_PRIMITIVES),
        "row_4": "reference_LoD2_only", "scientific_verdict": None,
    }


def check(config: Mapping[str, Any]) -> dict[str, Any]:
    prepared = _prepare(config)
    return {
        "state": "CHECKED_READ_ONLY", "population_count": len(prepared["result"].population_ids),
        "population_label": "LoD2 output exists (has_lod22); quality not implied",
        "selected_building_ids": list(prepared["selected_order"]),
        "photo_binding": {
            "eligibility": "full-frame, minimum area, surrounding-LoD2 first-hit target visible",
            "ranking": "nadir angle primary",
            "row_1_overlay_primitives": list(ROW1_PRIMITIVES),
            "views": {
                bid: [{
                    "name": view["name"], "nadir_deg": view["nadir_deg"],
                    "visible_target_fraction": view["visibility"]["visible_target_fraction"],
                    "bbox_area_px2": view["projected_boundary_bbox_area_px2"],
                } for view in prepared["photo_views_by_id"][bid]]
                for bid in prepared["selected_order"]
            },
        },
        "row_4": "evaluation-only reference LoD2 RoofSurface only; no Roofer output",
        "per_building_quality_observations": {
            bid: {
                "coverage_frac": float(next(row for row in prepared["result"].selected if row["building_id"] == bid)["coverage_frac"]),
                "n_views_nadir": float(next(row for row in prepared["result"].selected if row["building_id"] == bid)["n_views_nadir"]),
                "rf_rmse_lod22_m": float(prepared["quality_by_id"][bid]["rf_rmse_lod22"]),
            } for bid in prepared["selected_order"]
        },
        "learning_runs_started": 0, "scientific_verdict": None,
    }


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--output-root", type=Path)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("check", help="validate sources, selection and views; write nothing")
    subparsers.add_parser("render", help="atomically publish the v4 nine-panel bundle")
    subparsers.add_parser("verify", help="rehash and validate the published v4 bundle")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    config = load_config(args.config.resolve())
    if args.command == "check": payload = check(config)
    elif args.command == "render": payload = publish(config, args.output_root)
    else: payload = verify_bundle(config, args.output_root)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
