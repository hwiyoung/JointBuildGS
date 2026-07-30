#!/usr/bin/env python3
"""Publish dense qualitative v5 with canonical-equivalent Roofer crop evidence.

The frozen nine-building sample and v4 photo binding are unchanged.  Roofer receives
one classified DIM/MVS LAZ plus one XY footprint source.  Its default class roles are
6=building and 2=ground.  It reruns all canonical footprint features without a filter,
adding only ``--crop-only --crop-output``.  It then selects the frozen nine crop
LAS/GPKG artifacts, projects those same points in row 1, and renders them
together as one input in row 2.  Row 3 is the frozen canonical output; row 4 is the
evaluation-only reference roof.  No learning or scientific verdict occurs here.

The historical W2 run did not save crop artifacts.  V5 therefore claims command-
contract equivalence, not byte identity with a historical crop file.
"""
from __future__ import annotations

import argparse
import copy
import importlib.util
import json
import math
import os
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path
from typing import Any, Mapping, Sequence

os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib")
os.environ.setdefault("XDG_CACHE_HOME", "/tmp/cache")

import laspy
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import patches, patheffects
from matplotlib.backends.backend_pdf import PdfPages
import numpy as np
from PIL import Image
from shapely import wkb


REPO = Path(__file__).resolve().parents[4]
SCRIPT_DIR = Path(__file__).resolve().parent
for import_root in (SCRIPT_DIR, REPO):
    if str(import_root) not in sys.path:
        sys.path.insert(0, str(import_root))


def _load_module(path: Path, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot import helper: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


V4 = _load_module(
    SCRIPT_DIR / "fusion_w1_dense_baseline_qualitative_v4_20260728.py",
    "dense_baseline_qualitative_v4_base_for_v5",
)
BASE = V4.BASE
V3 = V4.V3

DEFAULT_CONFIG = REPO / "phases/p2-gsjso/configs/fusion_w1/fusion_w1_dense_baseline_qualitative_v5_20260728.json"
CONFIG_SCHEMA = "jointbuildgs.fusion_w1.dense_baseline_qualitative.config.v5"
MANIFEST_SCHEMA = "jointbuildgs.fusion_w1.dense_baseline_qualitative.manifest.v5"
EXPECTED_SELECTED = V4.EXPECTED_SELECTED
ROW1_PRIMITIVES = [
    "reference_RoofSurface_exterior_boundary",
    "roofer_crop_stage_class6_building_points",
    "roofer_crop_stage_class2_ground_points",
]
ROW2_PRIMITIVES = [
    "one_roofer_crop_stage_LAS_colored_by_class_role",
    "class6_building_points",
    "class2_ground_points",
    "roofer_crop_stage_footprint_XY",
]


class DenseBaselineV5Error(V4.DenseBaselineV4Error):
    """A v5 crop, rendering, provenance, or publication invariant failed."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise DenseBaselineV5Error(message)


def load_config(path: Path = DEFAULT_CONFIG, *, verify_sources: bool = True) -> dict[str, Any]:
    raw = BASE.read_json(path)
    require(raw.get("schema") == CONFIG_SCHEMA, "v5 config schema drift")
    require(raw.get("branch") == "exp/fusion-w1", "branch contract drift")
    base_spec = raw.get("base_config") or {}
    base_path = BASE.repo_path(str(base_spec.get("path", "")))
    require(base_path.is_file(), "v5 base config absent")
    if verify_sources:
        require(BASE.sha256_file(base_path) == base_spec.get("sha256"), "v5 base config hash drift")
    config = copy.deepcopy(V4.load_config(base_path, verify_sources=verify_sources))
    for key in (
        "schema", "task_id", "run_id", "purpose", "base_config", "implementation_files",
        "sample_freeze", "canonical_roofer_crop_contract", "visual_overrides", "outputs", "publication",
    ):
        config[key] = copy.deepcopy(raw[key])
    for key, value in raw["photo_projection_contract_overrides"].items():
        if key != "note":
            config["photo_projection_contract"][key] = copy.deepcopy(value)
    config["visual_contract"]["row_order"][0] = raw["visual_overrides"]["row_1"]
    config["visual_contract"]["row_order"][1] = raw["visual_overrides"]["row_2"]
    config["visual_contract"]["row_order"][2] = raw["visual_overrides"]["row_3"]
    config["visual_contract"]["row_order"][3] = raw["visual_overrides"]["row_4"]
    crop = config["canonical_roofer_crop_contract"]
    config["sources"]["canonical_roofer_footprints"] = {
        "path": crop["footprint_path"], "sha256": crop["footprint_sha256"],
        "layer": crop["footprint_layer"], "id_field": crop["footprint_id_field"],
    }
    config["sources"]["canonical_roofer_command_log"] = {
        "path": crop["canonical_recorded_command_source"],
        "sha256": "69e61bb10f3f569bc9be90b15b4a9148031dbb7969819122228f11df6a176de1",
    }
    expected_implementation = [
        "phases/p2-gsjso/configs/fusion_w1/fusion_w1_dense_baseline_qualitative_v5_20260728.json",
        "phases/p2-gsjso/scripts/fusion_w1/fusion_w1_dense_baseline_qualitative_v5_20260728.py",
        "phases/p2-gsjso/scripts/fusion_w1/run_fusion_w1_dense_baseline_qualitative_v5_20260728.sh",
        "tests/fusion_w1/test_fusion_w1_dense_baseline_qualitative_v5_20260728.py",
        "phases/p2-gsjso/configs/fusion_w1/fusion_w1_dense_baseline_qualitative_v4_20260728.json",
        "phases/p2-gsjso/scripts/fusion_w1/fusion_w1_dense_baseline_qualitative_v4_20260728.py",
        "phases/p2-gsjso/configs/fusion_w1/fusion_w1_dense_baseline_qualitative_v3_20260728.json",
        "phases/p2-gsjso/scripts/fusion_w1/fusion_w1_dense_baseline_qualitative_v3_20260728.py",
        "phases/p2-gsjso/configs/fusion_w1/fusion_w1_dense_baseline_qualitative_v2_20260728.json",
        "phases/p2-gsjso/scripts/fusion_w1/fusion_w1_dense_baseline_qualitative_v2_20260728.py",
        "scripts/e5_c001/e5_c001_8way.py",
        "phases/p2-gsjso/scripts/fusion_w1/fusion_w1_aprime_job_panel_v4_20260727.py",
        "src/artifact_paths.py",
        "src/stage2/image_projection.py",
    ]
    require(config["implementation_files"] == expected_implementation, "v5 implementation closure drift")
    for value in expected_implementation:
        require(BASE.repo_path(value).is_file(), f"v5 implementation absent: {value}")
    require(tuple(config["sample_freeze"]["selected_building_ids"]) == EXPECTED_SELECTED, "sample freeze drift")
    require(BASE.set_sha256(EXPECTED_SELECTED) == config["sample_freeze"]["selected_set_sha256"], "sample SHA drift")
    require(config["photo_projection_contract"]["allowed_photo_overlays"] == ROW1_PRIMITIVES, "row-1 contract drift")
    defaults = crop["defaults_verified_from_roofer_help_all"]
    require(defaults["bld_class"] == 6 and defaults["grnd_class"] == 2, "Roofer class defaults drift")
    require(float(defaults["ceil_point_density"]) == 20.0, "Roofer density ceiling drift")
    require(defaults["h_terrain_strategy"] == "buffer_tile", "Roofer terrain strategy drift")
    require(float(defaults["terrain_buffer_m"]) == 4.0, "Roofer terrain buffer drift")
    for key in ("pointcloud_path", "footprint_path"):
        source = BASE.repo_path(crop[key])
        require(source.is_file(), f"Roofer crop source absent: {key}")
        if verify_sources:
            require(BASE.sha256_file(source) == crop[key.replace("path", "sha256")], f"Roofer crop source hash drift: {key}")
    require(config["publication"]["reference_role"] == "evaluation_only", "reference role drift")
    require(config["publication"]["learning_runs_started"] == 0, "learning count drift")
    require(config["publication"]["scientific_verdict"] is None, "scientific verdict must be null")
    return config


def _load_crop_footprint(path: Path, building_id: str) -> tuple[np.ndarray, bool]:
    require(path.is_file(), f"crop footprint absent: {path}")
    connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        layer_row = connection.execute("SELECT table_name FROM gpkg_contents WHERE data_type='features'").fetchall()
        require(len(layer_row) == 1, f"crop footprint layer count drift: {path}")
        layer = str(layer_row[0][0])
        geometry_row = connection.execute(
            "SELECT column_name, srs_id FROM gpkg_geometry_columns WHERE table_name=?", (layer,)
        ).fetchone()
        require(geometry_row is not None and int(geometry_row[1]) == 25832, "crop footprint CRS drift")
        geometry_column = str(geometry_row[0])
        q_layer = '"' + layer.replace('"', '""') + '"'
        q_geom = '"' + geometry_column.replace('"', '""') + '"'
        rows = connection.execute(f"SELECT building_id,{q_geom} FROM {q_layer}").fetchall()
    finally:
        connection.close()
    rings: list[np.ndarray] = []
    source_has_z = False
    for identifier, blob_value in rows:
        if str(identifier) != building_id:
            continue
        blob = bytes(blob_value)
        require(len(blob) >= 8 and blob[:2] == b"GP", "invalid crop GeoPackage geometry header")
        envelope_code = (blob[3] >> 1) & 0b111
        envelope_doubles = {0: 0, 1: 4, 2: 6, 3: 6, 4: 8}.get(envelope_code)
        require(envelope_doubles is not None, "unsupported crop GeoPackage envelope")
        geometry = wkb.loads(blob[8 + int(envelope_doubles) * 8 :])
        source_has_z = source_has_z or bool(getattr(geometry, "has_z", False))
        polygons = [geometry] if geometry.geom_type == "Polygon" else list(geometry.geoms)
        for polygon in polygons:
            ring_xyz = np.asarray(polygon.exterior.coords, dtype=np.float64)
            require(ring_xyz.ndim == 2 and ring_xyz.shape[1] in {2, 3} and len(ring_xyz) >= 4, "crop footprint malformed")
            rings.append(ring_xyz[:, :2])
    require(bool(rings), f"crop footprint building absent: {building_id}")
    return max(rings, key=BASE.polygon_area_uv), source_has_z


def load_crop_bundle(crop_root: Path, building_ids: Sequence[str]) -> dict[str, Any]:
    root = crop_root.resolve()
    require(root.is_dir(), f"Roofer crop root absent: {root}")
    log_path = root / "roofer.log.json"
    features_path = root / "result/features.txt"
    require(log_path.is_file() and features_path.is_file(), "Roofer crop log/features absent")
    points_by_id: dict[str, dict[int, np.ndarray]] = {}
    footprints: dict[str, np.ndarray] = {}
    records: dict[str, dict[str, Any]] = {}
    counts: dict[str, dict[str, int]] = {}
    footprint_source_has_z: dict[str, bool] = {}
    for building_id in building_ids:
        directory = root / "result/objects" / building_id / "crop"
        las_path = directory / f"{building_id}_.las"
        gpkg_path = directory / f"{building_id}.gpkg"
        require(las_path.is_file() and gpkg_path.is_file(), f"crop outputs absent: {building_id}")
        cloud = laspy.read(str(las_path))
        xyz = np.column_stack((
            np.asarray(cloud.x, dtype=np.float64),
            np.asarray(cloud.y, dtype=np.float64),
            np.asarray(cloud.z, dtype=np.float64),
        ))
        cls = np.asarray(cloud.classification, dtype=np.uint8)
        observed_classes = {int(value) for value in np.unique(cls)}
        require(observed_classes <= {2, 6}, f"unexpected Roofer crop classes {observed_classes}: {building_id}")
        by_class = {value: xyz[cls == value] for value in (2, 6)}
        require(len(by_class[6]) > 0, f"Roofer crop building class absent: {building_id}")
        points_by_id[building_id] = by_class
        footprints[building_id], footprint_source_has_z[building_id] = _load_crop_footprint(gpkg_path, building_id)
        counts[building_id] = {"total": int(len(xyz)), "class_2": int(len(by_class[2])), "class_6": int(len(by_class[6]))}
        records[building_id] = {
            "las": BASE.file_record(las_path), "footprint_gpkg": BASE.file_record(gpkg_path),
            "classes_present": sorted(observed_classes), "counts": counts[building_id],
            "footprint_source_geometry_has_z": footprint_source_has_z[building_id],
            "footprint_render_and_input_role": "XY only; any crop-export Z is stripped and unused",
        }
    require(set(points_by_id) == set(building_ids), "Roofer crop sample set drift")
    return {
        "root": root, "points_by_id": points_by_id, "footprints": footprints,
        "counts": counts, "records": records, "footprint_source_has_z": footprint_source_has_z,
        "log": BASE.file_record(log_path), "features": BASE.file_record(features_path),
    }


def _prepare(config: Mapping[str, Any], crop_root: Path) -> dict[str, Any]:
    prepared = V4._prepare(config)
    require(tuple(prepared["selected_order"]) == EXPECTED_SELECTED, "v5 selected sample differs from freeze")
    crop = load_crop_bundle(crop_root, prepared["selected_order"])
    require(
        crop["counts"] == config["canonical_roofer_crop_contract"]["expected_frozen_nine_crop_counts"],
        "canonical-equivalent frozen-nine crop counts drift",
    )
    prepared["crop"] = crop
    prepared["points_by_class_by_id"] = crop["points_by_id"]
    prepared["points_by_id"] = {bid: values[6] for bid, values in crop["points_by_id"].items()}
    prepared["crop_footprints_by_id"] = crop["footprints"]
    return prepared


def copy_selected_crop_bundle(
    source_root: Path, target_root: Path, building_ids: Sequence[str], expected_objects_n: int
) -> dict[str, Any]:
    """Retain all-run receipts and only the frozen-nine object artifacts."""
    source = source_root.resolve()
    require(source.is_dir() and not target_root.exists(), "crop copy source/target invalid")
    source_objects = sorted(path for path in (source / "result/objects").iterdir() if path.is_dir())
    require(len(source_objects) == int(expected_objects_n), f"full-context crop object count {len(source_objects)} != {expected_objects_n}")
    features = source / "result/features.txt"
    log = source / "roofer.log.json"
    console = source / "roofer.console.log"
    require(features.is_file() and log.is_file() and console.is_file(), "full-context crop receipts absent")
    feature_lines = [line for line in features.read_text(encoding="utf-8").splitlines() if line.strip()]
    require(len(feature_lines) == int(expected_objects_n), "full-context feature receipt count drift")
    log_text = log.read_text(encoding="utf-8")
    require('Number of source footprints: 199' in log_text, "full-context source footprint receipt absent")
    require(f"cropped {int(expected_objects_n)} buildings" in log_text, "full-context crop count receipt absent")
    target_objects = target_root / "result/objects"
    target_objects.mkdir(parents=True)
    shutil.copy2(log, target_root / "roofer.log.json")
    shutil.copy2(console, target_root / "roofer.console.log")
    (target_root / "result").mkdir(exist_ok=True)
    shutil.copy2(features, target_root / "result/features.txt")
    for building_id in building_ids:
        source_object = source / "result/objects" / building_id
        require(source_object.is_dir(), f"selected full-context crop object absent: {building_id}")
        shutil.copytree(source_object, target_objects / building_id)
    features_record = BASE.file_record(features)
    features_record["path"] = "full_context_crop/result/features.txt"
    log_record = BASE.file_record(log)
    log_record["path"] = "full_context_crop/roofer.log.json"
    console_record = BASE.file_record(console)
    console_record["path"] = "full_context_crop/roofer.console.log"
    return {
        "source_footprints_n": 199,
        "source_crop_objects_n": len(source_objects),
        "selected_objects_copied_n": len(building_ids),
        "filter_used": False,
        "full_context_features_record": features_record,
        "full_context_log_record": log_record,
        "full_context_console_record": console_record,
    }


def projected_photo_panel(
    ax: Any, building_id: str, image_path: Path, view: Any,
    scene_reference: Mapping[str, Any], reference_rings: Sequence[np.ndarray],
    class6_points: np.ndarray, class2_points: np.ndarray, scene: Any,
    config: Mapping[str, Any], font: Any, index: int, crop_profile: str,
    view_selection: Mapping[str, Any],
) -> dict[str, Any]:
    uv_rings, projection = V3.project_reference_roof_boundaries(reference_rings, view, scene_reference, config)
    require(projection["all_vertices_valid"], f"reference projection invalid: {image_path.name}")
    require(projection["all_vertices_inside_full_frame"], f"reference leaves frame: {image_path.name}")
    class6_uv, receipt6 = V4.project_visible_dense_points(
        building_id, class6_points, 6, view, scene_reference, reference_rings, scene, config
    )
    if len(class2_points):
        class2_uv, receipt2 = V4.project_visible_dense_points(
            building_id, class2_points, 2, view, scene_reference, reference_rings, scene, config
        )
    else:
        class2_uv = np.empty((0, 2), dtype=np.float64)
        receipt2 = {
            "source_points_n": 0, "raycast_input_points_n": 0,
            "positive_depth_inframe_points_n": 0, "first_hit_visible_points_n": 0,
            "pixel_thinned_points_n": 0, "classification": 2,
            "source_identity": "canonical-equivalent Roofer crop LAS contains zero class-2 points",
        }
    receipt6["source_identity"] = "class 6 view of the same canonical-equivalent Roofer crop LAS rendered in row 2"
    if len(class2_points):
        receipt2["source_identity"] = "class 2 view of the same canonical-equivalent Roofer crop LAS rendered in row 2"
    require(receipt6["first_hit_visible_points_n"] + receipt2["first_hit_visible_points_n"] >= 1, "no visible crop point")
    box = V4._crop_box(projection, crop_profile, config)
    with Image.open(image_path) as source:
        image = source.convert("RGB")
        require(image.size == tuple(projection["image_size"]), "camera/image size drift")
        cropped = np.asarray(image.crop(box))
    ax.imshow(cropped)
    offset = np.asarray([box[0], box[1]], dtype=np.float64)
    visual = config["visual_overrides"]
    inside6 = ((class6_uv[:, 0] >= box[0]) & (class6_uv[:, 0] < box[2]) & (class6_uv[:, 1] >= box[1]) & (class6_uv[:, 1] < box[3])) if len(class6_uv) else np.zeros(0, dtype=bool)
    inside2 = ((class2_uv[:, 0] >= box[0]) & (class2_uv[:, 0] < box[2]) & (class2_uv[:, 1] >= box[1]) & (class2_uv[:, 1] < box[3])) if len(class2_uv) else np.zeros(0, dtype=bool)
    local2, local6 = class2_uv[inside2] - offset, class6_uv[inside6] - offset
    if len(local2):
        ax.scatter(local2[:, 0], local2[:, 1], s=float(visual["dense_point_size"]) * 0.82,
                   c=visual["ground_label_point_color"], edgecolors=visual["ground_label_point_edge_color"],
                   linewidths=0.18, alpha=float(visual["dense_point_alpha"]) * 0.72,
                   rasterized=True, label="same Roofer input LAS: class 2 ground role", zorder=2)
    if len(local6):
        ax.scatter(local6[:, 0], local6[:, 1], s=float(visual["dense_point_size"]),
                   c=visual["dense_point_color"], edgecolors=visual["dense_point_edge_color"],
                   linewidths=0.22, alpha=float(visual["dense_point_alpha"]),
                   rasterized=True, label="same Roofer input LAS: class 6 building role", zorder=3)
    for ring_index, ring_uv in enumerate(uv_rings):
        local = np.asarray(ring_uv, dtype=np.float64) - offset
        line = ax.plot(local[:, 0], local[:, 1], color=visual["reference_boundary_color"],
                       linewidth=float(visual["reference_boundary_linewidth"]), zorder=4,
                       label="reference roof boundary (evaluation only)" if ring_index == 0 else None)[0]
        line.set_path_effects([patheffects.Stroke(linewidth=float(visual["reference_boundary_halo_linewidth"]),
                                                  foreground=visual["reference_boundary_halo_color"], alpha=0.8),
                               patheffects.Normal()])
    ax.axis("off")
    nadir_deg, threshold = float(view_selection["nadir_deg"]), float(view_selection["near_nadir_threshold_deg"])
    nadir_note = f"near-nadir {nadir_deg:.1f}°" if view_selection["near_nadir_available"] else f"nadir unavailable; least-oblique usable={nadir_deg:.1f}°"
    ax.set_title(
        f"사진 {index} · {image_path.name} · {crop_profile}\n{nadir_note} · one Roofer input: cyan=c6, magenta=c2 · yellow=reference",
        fontproperties=font, fontsize=7.3, color="#252a31", pad=5,
    )
    ax.legend(loc="lower left", fontsize=4.6, framealpha=0.88, markerscale=0.8)
    return {
        "image_name": image_path.name, "image_record": BASE.file_record(image_path),
        "crop_xyxy": list(box), "crop_profile": crop_profile,
        "nadir_deg": nadir_deg, "near_nadir_threshold_deg": threshold,
        "near_nadir_available": bool(view_selection["near_nadir_available"]),
        "overlay_primitives": list(ROW1_PRIMITIVES), "reference_role": "evaluation_only",
        "reference_roof_exterior_rings_n": int(projection["rings_n"]),
        "all_boundary_vertices_valid": bool(projection["all_vertices_valid"]),
        "all_boundary_vertices_inside_full_frame": bool(projection["all_vertices_inside_full_frame"]),
        "projected_boundary_bbox_area_px2": float(projection["bbox_area_px2"]),
        "projector": "src/stage2/image_projection.py", "input_vertical_datum": projection["input_vertical_datum"],
        "geoid_m": projection["geoid_m"], "dense_point_overlay_used": True,
        "dense_points_visible_in_crop_n": int(np.count_nonzero(inside6) + np.count_nonzero(inside2)),
        "dense_class6_points_visible_in_crop_n": int(np.count_nonzero(inside6)),
        "dense_class2_points_visible_in_crop_n": int(np.count_nonzero(inside2)),
        "dense_projection_by_class": {"2": receipt2, "6": receipt6},
        "both_colors_are_one_roofer_input_las": True,
        "dense_tin_boundary_overlay_used": False, "footprint_overlay_used": False,
        "filled_polygon_overlay_used": False, "interior_ring_overlay_used": False,
    }


def _plot_footprint_xy(ax: Any, ring_xy: np.ndarray, display_z: float, frame: Mapping[str, Any], config: Mapping[str, Any]) -> None:
    xyz = np.column_stack((np.asarray(ring_xy, dtype=np.float64), np.full(len(ring_xy), float(display_z))))
    local = BASE.PANEL_V4.local_xyz(xyz, frame)
    visual = config["visual_overrides"]
    ax.plot(local[:, 0], local[:, 1], local[:, 2], color=visual["footprint_xy_color"],
            linewidth=float(visual["footprint_xy_linewidth"]), linestyle=visual["footprint_xy_linestyle"],
            label="Roofer footprint XY (display Z only)")


def _opaque_text_panel(fig: Any, subplot_spec: Any, title: str, lines: Sequence[str], font: Any) -> Any:
    """Keep adjacent 3D artists from obscuring the receipt column."""
    ax = fig.add_subplot(subplot_spec)
    BASE.text_panel(ax, title, lines, font)
    ax.set_zorder(20)
    ax.patch.set_visible(True)
    ax.patch.set_facecolor("white")
    ax.patch.set_alpha(1.0)
    ax.add_patch(
        patches.Rectangle(
            (0.0, 0.0), 1.0, 1.0,
            transform=ax.transAxes,
            facecolor="white",
            edgecolor="none",
            zorder=-100,
            clip_on=False,
        )
    )
    return ax


def render_building(
    staging: Path, pdf: PdfPages, config: Mapping[str, Any], selection_row: Mapping[str, Any],
    quality_row: Mapping[str, str], class6_points: np.ndarray, class2_points: np.ndarray,
    footprint_xy: np.ndarray, crop_record: Mapping[str, Any], surfaces: Sequence[Mapping[str, Any]],
    surface_stats: Mapping[str, Any], reference_rings: Sequence[np.ndarray], status_row: Mapping[str, str],
    photo_views: Sequence[Mapping[str, Any]], projection_views_by_name: Mapping[str, Any],
    scene_reference: Mapping[str, Any], raycast_scene: Any, font: Any,
) -> dict[str, Any]:
    building_id = str(selection_row["building_id"])
    require(len(class6_points) and len(footprint_xy), f"missing crop evidence: {building_id}")
    all_points = np.vstack((class2_points, class6_points))
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
        "P0 dense DIM/MVS -> Roofer | row 2 is one canonical-equivalent crop input, colored by role | verdict: null",
        fontproperties=font, fontsize=14.0, color="#252a31",
    )
    for y, label in (
        (0.790, "1  사진+Roofer 입력점+참조경계 / Photo + input points + ref"),
        (0.575, "2  단일 Roofer 입력 / One canonical-equivalent Roofer input, colored by role"),
        (0.360, "3  Roofer 출력 / Canonical output"),
        (0.145, "4  참조 LoD2 단독 / Reference LoD2 only"),
    ):
        fig.text(0.008, y, label, rotation=90, va="center", ha="center", fontsize=7.3, color="#252a31", fontproperties=font)
    image_directory = BASE.repo_path(config["sources"]["image_directory"]["path"])
    slots = V3.photo_slot_plan(photo_views)
    photo_receipts: list[dict[str, Any]] = []
    for column, slot in enumerate(slots):
        selected = slot["view"]
        image_name = str(selected["name"])
        receipt = projected_photo_panel(
            fig.add_subplot(grid[0, column]), building_id, image_directory / image_name,
            projection_views_by_name[image_name], scene_reference, reference_rings,
            class6_points, class2_points, raycast_scene, config, font,
            column + 1, str(slot["crop_profile"]), selected,
        )
        receipt["photo_selection"] = dict(selected)
        receipt["slot_policy"] = {"slot_order": int(slot["slot_order"]), "crop_profile": str(slot["crop_profile"]),
                                  "unique_visible_views_n": int(slot["unique_visible_views_n"]),
                                  "occluded_view_substitution_used": False}
        photo_receipts.append(receipt)
    input_lines = [
        "ONE canonical-equivalent Roofer crop LAS; colors indicate class roles",
        f"crop-stage points: total={len(all_points)}, class 6={len(class6_points)}, class 2={len(class2_points)}",
        "cyan class 6: building/roof-plane evidence",
        "magenta class 2: ground/terrain-height evidence",
        "source LAZ also contains class 1; Roofer defaults consume only 6 and 2",
        "all canonical footprint features rerun; no filter; frozen nine selected after crop",
        "historical crop artifact unavailable: command-contract equivalent, not byte-identical",
        "row 2 uses Roofer --crop-output LAS + crop-stage footprint GPKG",
        "default ceil density=20 pts/m²; terrain=buffer_tile; buffer=4 m",
        f"coverage / nodata: {float(selection_row['coverage_frac']):.6f} / {1.0-float(selection_row['coverage_frac']):.6f}",
        f"n_views_nadir / rf_rmse: {float(selection_row['n_views_nadir']):.6f} / {float(quality_row['rf_rmse_lod22']):.6f} m",
        "yellow: evaluation-only reference roof boundary",
        "row-1 footprint overlay: none; sample frozen before reference access",
        "NO GS TRAINING | scientific_verdict: null",
    ]
    _opaque_text_panel(fig, grid[0, 3:5], "입력 이력 / Input provenance", input_lines, font)

    shown2 = BASE.downsample(class2_points, int(visual["maximum_scatter_points"]))
    shown6 = BASE.downsample(class6_points, int(visual["maximum_scatter_points"]))
    display_z = float(np.quantile(class2_points[:, 2], 0.05)) if len(class2_points) else float(np.quantile(class6_points[:, 2], 0.01))
    for column, camera in enumerate(frame["cameras"]):
        ax = fig.add_subplot(grid[1, column], projection="3d")
        local2, local6 = BASE.PANEL_V4.local_xyz(shown2, frame), BASE.PANEL_V4.local_xyz(shown6, frame)
        ax.scatter(local2[:, 0], local2[:, 1], local2[:, 2], s=2.6, c=config["visual_overrides"]["ground_label_point_color"],
                   linewidths=0, alpha=0.62, depthshade=False, rasterized=True, label="same LAS: class 2 ground")
        ax.scatter(local6[:, 0], local6[:, 1], local6[:, 2], s=3.0, c=config["visual_overrides"]["dense_point_color"],
                   linewidths=0, alpha=0.88, depthshade=False, rasterized=True, label="same LAS: class 6 building")
        _plot_footprint_xy(ax, footprint_xy, display_z, frame, config)
        BASE.PANEL_V4.configure_3d_axis(ax, frame, camera)
        BASE.PANEL_V4.short_title(ax, f"단일 Roofer 입력 · {camera['title_ko']}",
                                  f"One canonical-equivalent input, colored by role · {camera['title_en']}", font, fontsize=7.7)
        ax.legend(loc="lower left", fontsize=4.2, framealpha=0.82)
    ax = fig.add_subplot(grid[1, 4])
    origin = np.asarray(frame["local_origin_epsg25832_xyz"], dtype=np.float64)
    principal = np.asarray(frame["axis"]["vector_east_north"], dtype=np.float64)
    for shown, color, label, alpha in (
        (shown2, config["visual_overrides"]["ground_label_point_color"], "same LAS: c2 ground", 0.62),
        (shown6, config["visual_overrides"]["dense_point_color"], "same LAS: c6 building", 0.88),
    ):
        horizontal = (shown[:, :2] - origin[:2]) @ principal
        ax.scatter(horizontal, shown[:, 2] - origin[2], s=2.0, color=color, linewidths=0, alpha=alpha, rasterized=True, label=label)
    footprint_h = (footprint_xy - origin[:2]) @ principal
    ax.plot([float(np.min(footprint_h)), float(np.max(footprint_h))], [display_z-origin[2], display_z-origin[2]],
            color=config["visual_overrides"]["footprint_xy_color"], linestyle=config["visual_overrides"]["footprint_xy_linestyle"],
            linewidth=float(config["visual_overrides"]["footprint_xy_linewidth"]), label="footprint XY span (display Z)")
    ax.set_xlabel("principal horizontal (m)", fontsize=7); ax.set_ylabel("ΔZ (m)", fontsize=7)
    ax.grid(True, color=visual["palette"]["light_grey"], linewidth=0.45); ax.tick_params(labelsize=6)
    ax.set_aspect("equal", adjustable="datalim"); ax.legend(loc="lower left", fontsize=4.5, framealpha=0.82)
    BASE.PANEL_V4.short_title(ax, "단일 Roofer 입력 주축 단면", "One canonical-equivalent input · principal section", font, fontsize=7.7)

    cityjson_render = BASE.PANEL_V4.cityjson_render_parts(surfaces, frame)["stats"]
    for column, camera in enumerate(frame["cameras"]):
        ax = fig.add_subplot(grid[2, column], projection="3d")
        BASE.PANEL_V4.plot_cityjson(ax, evidence, frame, helper_config, alpha=0.92)
        BASE.PANEL_V4.configure_3d_axis(ax, frame, camera)
        BASE.PANEL_V4.short_title(ax, f"P0 DIM Roofer 출력 · {camera['title_ko']}", f"Canonical CityJSON output · {camera['title_en']}", font, fontsize=8.0)
    semantic = surface_stats["semantic_counts"]
    output_lines = [
        "canonical P0 DIM Roofer CityJSON LoD2.2",
        "row 2 -> Roofer -> this row",
        "approved/reference-derived GroundSurface XY footprint was input",
        "assembled/valid shell != geometric quality",
        f"coverage / n_views_nadir: {float(selection_row['coverage_frac']):.6f} / {float(selection_row['n_views_nadir']):.6f}",
        f"rf_rmse_lod22: {float(quality_row['rf_rmse_lod22']):.6f} m",
        f"LoD / surfaces / vertices: {surface_stats['lod']:.1f} / {surface_stats['surfaces_n']} / {surface_stats['vertices_n']}",
        f"Roof / Wall / Ground: {semantic.get('RoofSurface',0)} / {semantic.get('WallSurface',0)} / {semantic.get('GroundSurface',0)}",
        f"wireframe-only hole surfaces: {cityjson_render['wireframe_only_surfaces_n']}",
        f"status / has_lod22: {status_row.get('status','n/a')} / {status_row.get('has_lod22','n/a')}",
        f"val3dity valid: {status_row.get('val3dity_valid','n/a')}",
        "scientific_verdict: null",
    ]
    _opaque_text_panel(fig, grid[2, 4], "정본 출력·품질 주의 / Output and quality caveat", output_lines, font)

    reference_faces = 0
    reference_frame = V4.reference_only_frame(reference_rings, frame, config)
    for column, camera in enumerate(frame["cameras"]):
        ax = fig.add_subplot(grid[3, column], projection="3d")
        reference_faces = V4.plot_reference_only(ax, reference_rings, reference_frame, config)
        BASE.PANEL_V4.configure_3d_axis(ax, reference_frame, camera)
        BASE.PANEL_V4.short_title(ax, f"참조 LoD2만 · {camera['title_ko']} (평가 전용)", f"Reference LoD2 ONLY · {camera['title_en']}", font, fontsize=8.0)
    comparison_lines = [
        "THIS ROW: reference LoD2 RoofSurface ONLY", "no Roofer output faces or lines",
        f"reference roof faces: {reference_faces}", "bounds: raw reference RoofSurface XYZ only",
        "reference role: evaluation only", "projection: orthographic | Z exaggeration: 1.0×", "",
        f"exact XY coordinate set equal: {comparison['exact_XY_coordinate_set_equal']}",
        f"exact XYZ coordinate set equal: {comparison['exact_XYZ_coordinate_set_equal']}",
        f"unique XY output/ref: {comparison['output_unique_xy_n']} / {comparison['reference_unique_xy_n']}",
        f"output Z: {comparison['output_z_min_m']:.3f}–{comparison['output_z_max_m']:.3f} m",
        f"reference Z: {comparison['reference_z_min_m']:.3f}–{comparison['reference_z_max_m']:.3f} m",
        "comparison facts only; output remains in row 3", "CRS: EPSG:25832 | scientific_verdict: null",
    ]
    _opaque_text_panel(fig, grid[3, 4], "참조 단독·비교 이력 / Reference-only receipt", comparison_lines, font)
    fig.text(0.5, 0.022, "row 2: one Roofer crop-stage input (c6 building + c2 ground + footprint XY) -> row 3: canonical output -> row 4: evaluation-only reference",
             ha="center", va="center", fontsize=7.1, color="#252a31", fontproperties=font)
    panel_directory = staging / config["outputs"]["panel_directory"]
    panel_directory.mkdir(parents=True, exist_ok=True)
    panel_path = panel_directory / config["outputs"]["panel_template"].format(building_id=building_id)
    require(not panel_path.exists(), f"panel overwrite refused: {panel_path}")
    fig.savefig(panel_path, dpi=int(visual["panel_dpi"]), facecolor="white", metadata={"Software": "JointBuildGS dense qualitative v5"})
    pdf.savefig(fig, facecolor="white"); plt.close(fig)
    with Image.open(panel_path) as rendered:
        pixels = list(rendered.size)
    return {
        "building_id": building_id, "panel": BASE.bundle_record(staging, panel_path),
        "cell": {size_field: selection_row[size_field], obs_field: selection_row[obs_field]},
        "quality_observations": {"coverage_frac": float(selection_row["coverage_frac"]),
                                 "n_views_nadir": float(selection_row["n_views_nadir"]),
                                 "rf_rmse_lod22_m": float(quality_row["rf_rmse_lod22"]),
                                 "assembled_shell_is_not_geometric_quality": True},
        "photo_receipts": photo_receipts, "unique_raycast_visible_photo_views_n": len(photo_views),
        "row_1_overlay_primitives": list(ROW1_PRIMITIVES),
        "row_1_sources_same_crop_stage_arrays_as_row_2": {"class_2": True, "class_6": True},
        "row_2_primitives": list(ROW2_PRIMITIVES), "row_2_is_one_roofer_input": True,
        "row_2_class_roles": {"2": "ground", "6": "building"},
        "row_2_footprint_display_z_m": display_z, "row_2_footprint_Z_is_input": False,
        "row_2_crop_record": dict(crop_record),
        "roofer_crop_points_n": {"total": len(all_points), "class_2": len(class2_points), "class_6": len(class6_points)},
        "row_3": "canonical_P0_DIM_Roofer_CityJSON_output", "row_4_roofer_output_used": False,
        "row_4_primitives": ["evaluation_only_reference_LoD2_RoofSurface_faces_and_exterior_edges"],
        "cityjson": dict(surface_stats), "comparison": comparison, "frame": frame,
        "render_pixels": pixels, "scientific_verdict": None, "interpretation": None,
    }


def publish(config: Mapping[str, Any], crop_root: Path, output_root: Path | None = None) -> dict[str, Any]:
    root = BASE.repo_path(config["outputs"]["root"]) if output_root is None else output_root.resolve()
    require(not root.exists(), f"output root exists; overwrite refused: {root}")
    root.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{root.name}.staging.", dir=root.parent))
    try:
        crop_copy = staging / config["outputs"]["roofer_crop_directory"]
        crop_copy_receipt = copy_selected_crop_bundle(
            crop_root, crop_copy, EXPECTED_SELECTED,
            int(config["canonical_roofer_crop_contract"]["expected_crop_objects_n"]),
        )
        prepared = _prepare(config, crop_copy)
        result = prepared["result"]
        invocation = {
            "schema": "jointbuildgs.fusion_w1.roofer_crop_invocation.v1",
            "roofer_image": config["canonical_roofer_crop_contract"]["roofer_image"],
            "roofer_image_id": config["canonical_roofer_crop_contract"]["roofer_image_id"],
            "source_pointcloud": BASE.file_record(BASE.repo_path(config["canonical_roofer_crop_contract"]["pointcloud_path"])),
            "source_footprint": BASE.file_record(BASE.repo_path(config["canonical_roofer_crop_contract"]["footprint_path"])),
            "selected_building_ids": list(EXPECTED_SELECTED),
            "canonical_aoi_bbox": config["canonical_roofer_crop_contract"]["canonical_aoi_bbox"],
            "diagnostic_additions": config["canonical_roofer_crop_contract"]["diagnostic_additions"],
            "defaults": config["canonical_roofer_crop_contract"]["defaults_verified_from_roofer_help_all"],
            "source_laz_classes_present": [1, 2, 6], "roofer_consumed_classes": [2, 6],
            "full_context_crop_receipt": crop_copy_receipt,
            "filter_used": False,
            "historical_crop_artifact_available": False,
            "equivalence_claim": config["canonical_roofer_crop_contract"]["equivalence_claim"],
            "crop_only_equivalence_validated": True,
            "crop_only_equivalence_scope": "frozen selected nine buildings",
            "crop_only_vs_full_reconstruction_selected_las": "9 of 9 byte-identical",
            "meaning": "class 2 and class 6 are roles in one input LAZ; they are not separate Roofer runs",
        }
        invocation_path = staging / config["outputs"]["crop_invocation_receipt"]
        BASE.write_json_new(invocation_path, invocation)
        font, font_record = BASE.load_font(config)
        BASE.write_csv_new(staging / config["outputs"]["selection_audit_csv"], result.audit_rows)
        selection_payload = BASE.selection_audit_payload(config, result)
        selection_payload["schema"] = "jointbuildgs.fusion_w1.dense_baseline_qualitative.selection_audit.v5"
        selection_payload["row_2_input_binding"] = "post-freeze Roofer crop output only; selector unchanged"
        BASE.write_json_new(staging / config["outputs"]["selection_audit_json"], selection_payload)
        sources_before = BASE.fixed_source_snapshot(config, prepared["selected_image_paths"], prepared["reference_paths"])
        panel_receipts: list[dict[str, Any]] = []
        pdf_path = staging / config["outputs"]["multipage_pdf"]
        with PdfPages(pdf_path, metadata={"Title": "P0 dense qualitative v5 canonical-equivalent Roofer input",
                                          "Subject": "row2 canonical-equivalent crop evidence; row3 output; row4 reference; verdict null",
                                          "Creator": "JointBuildGS"}) as pdf:
            for row in result.selected:
                bid = str(row["building_id"])
                surfaces, stats = prepared["output_by_id"][bid]
                points = prepared["points_by_class_by_id"][bid]
                panel_receipts.append(render_building(
                    staging, pdf, config, row, prepared["quality_by_id"][bid], points[6], points[2],
                    prepared["crop_footprints_by_id"][bid], prepared["crop"]["records"][bid],
                    surfaces, stats, prepared["reference_rings_by_id"][bid], prepared["status_by_id"][bid],
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
            "population": {"count": len(result.population_ids), "set_sha256": result.population_set_sha256,
                           "display_name": "dense LoD2 output exists (has_lod22); quality not implied",
                           "success_definition": "has_lod22 only; assembled/valid shell is not geometric quality"},
            "selection": {"sample_count": len(result.selected), "selected_building_ids": list(prepared["selected_order"]),
                          "selected_set_sha256": BASE.set_sha256(prepared["selected_order"]),
                          "selector_changes_from_v4": False},
            "render_contract": {"layout": "4_rows_x_5_columns", "individual_panel_count": len(panel_receipts),
                                "single_multipage_pdf": True, "overview": overview_record,
                                "row_1_overlay_primitives": list(ROW1_PRIMITIVES),
                                "row_1_source": "same canonical-equivalent Roofer crop-stage class arrays as row 2",
                                "row_2_primitives": list(ROW2_PRIMITIVES), "row_2_is_one_roofer_input": True,
                                "row_2_color_meaning": {"cyan": "class 6 building role", "magenta": "class 2 ground role"},
                                "row_3": "canonical P0 DIM Roofer CityJSON output",
                                "row_4": "evaluation-only reference LoD2 RoofSurface only",
                                "row_4_roofer_output_used": False},
            "roofer_input_contract": config["canonical_roofer_crop_contract"],
            "roofer_crop_invocation": BASE.bundle_record(staging, invocation_path),
            "full_context_crop_receipt": crop_copy_receipt,
            "per_building_crop_counts": prepared["crop"]["counts"],
            "per_building_quality_observations": {r["building_id"]: r["quality_observations"] for r in panel_receipts},
            "panel_receipts": panel_receipts, "source_records": list(sources_before.values()),
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
    require(manifest.get("schema") == MANIFEST_SCHEMA and manifest.get("state") == "COMPLETE", "v5 manifest drift")
    require(manifest.get("scientific_verdict") is None, "manifest contains a verdict")
    require(tuple(manifest["selection"]["selected_building_ids"]) == EXPECTED_SELECTED, "manifest sample drift")
    render = manifest["render_contract"]
    require(render.get("row_2_is_one_roofer_input") is True, "row 2 is not bound as one input")
    require(render.get("row_2_primitives") == ROW2_PRIMITIVES, "row-2 primitive drift")
    require(render.get("row_3") == "canonical P0 DIM Roofer CityJSON output", "row-3 output drift")
    require(render.get("row_4_roofer_output_used") is False, "Roofer leaked into row 4")
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
        require(receipt.get("row_2_is_one_roofer_input") is True, "panel row-2 input drift")
        require(receipt.get("row_1_sources_same_crop_stage_arrays_as_row_2") == {"class_2": True, "class_6": True}, "row1/2 identity drift")
        require(receipt.get("row_4_roofer_output_used") is False, "panel row-4 output leak")
    panels = sorted((root / config["outputs"]["panel_directory"]).glob("*.png"))
    require(len(panels) == 9, "published panel count drift")
    crop_las = sorted((root / config["outputs"]["roofer_crop_directory"]).glob("result/objects/*/crop/*.las"))
    require(len(crop_las) == 9, "embedded Roofer crop LAS count drift")
    return {"state": "VERIFIED", "root": str(root), "panels": len(panels), "crop_las": len(crop_las),
            "outputs": len(records), "source_records": source_records_n,
            "row_2": "one_roofer_input_colored_by_role", "row_3": "canonical_output",
            "row_4": "reference_only", "scientific_verdict": None}


def check(config: Mapping[str, Any]) -> dict[str, Any]:
    prepared = V4._prepare(config)
    crop = config["canonical_roofer_crop_contract"]
    return {"state": "CHECKED_READ_ONLY", "selected_building_ids": list(prepared["selected_order"]),
            "canonical_input": {"pointcloud": crop["pointcloud_path"], "footprint": crop["footprint_path"],
                                "one_laz": True, "source_classes_present": [1, 2, 6],
                                "roofer_consumed_class_roles": {"2": "ground", "6": "building"},
                                "defaults": crop["defaults_verified_from_roofer_help_all"]},
            "row_2": "canonical-equivalent full-context Roofer --crop-output LAS/GPKG required at render time",
            "row_3": "canonical P0 DIM Roofer CityJSON output", "row_4": "reference only",
            "learning_runs_started": 0, "scientific_verdict": None}


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--output-root", type=Path)
    parser.add_argument("--crop-root", type=Path)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("check"); subparsers.add_parser("render"); subparsers.add_parser("verify")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    config = load_config(args.config.resolve())
    if args.command == "check":
        payload = check(config)
    elif args.command == "render":
        require(args.crop_root is not None, "render requires --crop-root")
        payload = publish(config, args.crop_root, args.output_root)
    else:
        payload = verify_bundle(config, args.output_root)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
