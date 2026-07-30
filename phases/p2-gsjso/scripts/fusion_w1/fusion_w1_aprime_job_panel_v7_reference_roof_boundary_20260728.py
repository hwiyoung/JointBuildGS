#!/usr/bin/env python3
"""Publish A-prime r1 panel-v7 with a reference LoD2 roof-boundary photo row.

This is a post-hoc qualitative adapter.  The first row uses only exterior
LinearRings of evaluation-only reference ``RoofSurface`` polygons.  It never
uses the reference during training, read-out, assembly, or scoring.  ALS seed,
class-6 TIN geometry, M_j, and Roofer output are excluded from first-row view
selection, crop bounds, and image overlay.  The remaining rows reuse frozen
measured evidence and preserve the seed -> TSDF -> Roofer -> reference flow.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import math
import os
import shutil
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np
from matplotlib import patheffects
from PIL import Image


REPO = Path(__file__).resolve().parents[4]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from src.stage2 import image_projection  # noqa: E402
from src.stage2 import pilot_plane_mask_producer  # noqa: E402
from src.stage2.colmap_io import read_cameras_bin, read_images_bin  # noqa: E402


V4_RENDERER = REPO / "phases/p2-gsjso/scripts/fusion_w1/fusion_w1_aprime_job_panel_v4_20260727.py"
DEFAULT_CONFIG = (
    REPO
    / "phases/p2-gsjso/configs/fusion_w1/fusion_w1_aprime_job_panel_v7_reference_roof_boundary_20260728.json"
)
CONFIG_SCHEMA = "jointbuildgs.fusion_w1_aprime.job_panel_reference_roof_boundary.config.v7"
RECEIPT_SCHEMA = "jointbuildgs.fusion_w1_aprime.job_panel_reference_roof_boundary.complete.v7"


def load_module(path: Path, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot import {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


v4 = load_module(V4_RENDERER, "fusion_w1_aprime_job_panel_v4_for_v7_reference_roof")
base = v4.base
PanelError = v4.PanelError


def require(condition: bool, message: str) -> None:
    if not condition:
        raise PanelError(message)


def allowed_identities(config: Mapping[str, Any]) -> list[tuple[str, str, str]]:
    records = config["backfill_contract"]["allowed_identities"]
    require(isinstance(records, list) and len(records) == 9, "v7 must lock nine r1 identities")
    values = [
        (str(record["building_id"]), str(record["arm"]), str(record["replicate"]))
        for record in records
    ]
    require(len(set(values)) == len(values), "v7 identities are not unique")
    require(all(arm == "Aprime" and replicate == "r1" for _, arm, replicate in values), "v7 is A-prime r1 only")
    return values


def validate_identity(
    config: Mapping[str, Any],
    base_config: Mapping[str, Any],
    building_id: str,
    arm: str,
    replicate: str,
) -> None:
    base.validate_identity(base_config, building_id, arm, replicate)
    require(
        (building_id, arm, replicate) in allowed_identities(config),
        "identity is outside the locked A-prime r1 panel-v7 scope",
    )


def implementation_records(config: Mapping[str, Any]) -> list[dict[str, Any]]:
    return [base.file_record(base.repo_path(path)) for path in config["implementation_files"]]


def load_config(path: Path = DEFAULT_CONFIG) -> tuple[dict[str, Any], dict[str, Any]]:
    config = base.load_json(path)
    require(config.get("schema") == CONFIG_SCHEMA, "panel v7 config schema drift")
    require(config.get("run_id") == "20260726_fusion_w1_aprime", "run ID drift")
    require(config.get("branch") == "exp/fusion-w1", "branch drift")
    expected_ids = [
        "DEBY_LOD2_42364609",
        "DEBY_LOD2_42364659",
        "DEBY_LOD2_42364663",
        "DEBY_LOD2_4907182",
        "DEBY_LOD2_4907510",
        "DEBY_LOD2_4908050",
        "DEBY_LOD2_4908166",
        "DEBY_LOD2_4908176",
        "DEBY_LOD2_4908023",
    ]
    require([value[0] for value in allowed_identities(config)] == expected_ids, "v7 target order drift")

    expected_implementation = [
        "phases/p2-gsjso/configs/fusion_w1/fusion_w1_aprime_job_panel_v7_reference_roof_boundary_20260728.json",
        "phases/p2-gsjso/scripts/fusion_w1/fusion_w1_aprime_job_panel_v7_reference_roof_boundary_20260728.py",
        "phases/p2-gsjso/scripts/fusion_w1/run_fusion_w1_aprime_job_panel_v7_reference_roof_boundary_20260728.sh",
        "tests/fusion_w1/test_fusion_w1_aprime_job_panel_v7_reference_roof_boundary_20260728.py",
        "phases/p2-gsjso/scripts/fusion_w1/fusion_w1_aprime_job_panel_v4_20260727.py",
        "phases/p2-gsjso/configs/fusion_w1/fusion_w1_aprime_job_qualitative_v3_20260727.json",
        "phases/p2-gsjso/scripts/fusion_w1/fusion_w1_aprime_job_qualitative_v3_20260727.py",
        "src/artifact_paths.py",
        "src/stage2/image_projection.py",
        "src/stage2/pilot_plane_mask_producer.py",
        "src/stage2/pilot_mask_schema.py",
        "src/geospatial/projection_datum.py",
        "src/stage2/colmap_io.py",
    ]
    require(config.get("implementation_files") == expected_implementation, "v7 dependency closure drift")
    for value in expected_implementation:
        require(not Path(value).is_absolute(), "implementation path must be relative")
        require(base.repo_path(value).is_file(), f"implementation absent: {value}")

    base_contract = config["base_contract"]
    require(base_contract.get("layout_reuse_only") is True, "layout-only disclosure drift")
    require(base_contract.get("v4_flat_locator_used") is False, "v4 flat locator enabled")
    require(base_contract.get("v6_class6_tin_locator_used") is False, "v6 TIN locator enabled")

    resolver = config["resolver_disclosure"]
    require(resolver.get("reference_RoofSurface_used_for_post_hoc_visual_selection_crop_and_overlay") is True, "reference visual-selection disclosure absent")
    require(resolver.get("reference_used_for_training_supervision_readout_assembly_or_scoring") is False, "reference leaked into experiment")
    for key in (
        "M_j_used_for_v7_view_selection_crop_or_overlay",
        "ALS_seed_used_for_v7_view_selection_crop_or_overlay",
        "class6_TIN_used_for_v7_view_selection_crop_or_overlay",
        "output_CityJSON_used_for_v7_view_selection_crop_or_overlay",
    ):
        require(resolver.get(key) is False, f"first-row leakage: {key}")

    first = config["first_row_reference_contract"]
    require(first.get("geometry") == "evaluation-only reference GML Building RoofSurface Polygon exterior LinearRing only", "reference roof geometry drift")
    require(first.get("overlay_style") == "unfilled boundary line only", "boundary-only style drift")
    exclusions = set(first["geometry_exclusions"])
    require(
        {"ALS seed points", "class6 TIN points", "class6 TIN boundary", "M_j mask", "Roofer output"}.issubset(exclusions),
        "first-row exclusions incomplete",
    )
    coordinate = first["coordinate_contract"]
    require(coordinate.get("input_vertical_datum") == image_projection.ORTHOMETRIC, "projection datum drift")
    require(float(coordinate.get("orthometric_to_ellipsoidal_geoid_m")) == 45.7, "projection geoid drift")
    require(coordinate.get("projection_engine") == "src.stage2.image_projection.project_base_points", "shared projector drift")
    require(int(coordinate.get("additional_transform_application_count", -1)) == 0, "additional pose transform must stay zero")
    for path_key, hash_key in (
        ("projection_config", "projection_config_sha256"),
        ("scene_reference_frame", "scene_reference_sha256"),
    ):
        source = base.repo_path(coordinate[path_key])
        require(source.is_file(), f"coordinate source absent: {coordinate[path_key]}")
        require(v4.sha256_file(source) == coordinate[hash_key], f"coordinate source hash drift: {path_key}")

    selection = first["view_selection"]
    require(selection.get("reference_GML_used_for_post_hoc_visual_ranking") is True, "reference ranking disclosure absent")
    require(selection.get("image_pixels_used_for_ranking") is False, "RGB pixel ranking enabled")
    require(selection.get("M_j_used_for_ranking_or_eligibility") is False, "M_j ranking enabled")
    require(selection.get("ALS_or_TIN_used_for_ranking_or_eligibility") is False, "ALS/TIN ranking enabled")
    require(selection.get("output_CityJSON_used_for_ranking_or_eligibility") is False, "output ranking enabled")
    visibility = selection["visibility_gate"]
    require(
        visibility.get("source_scene_loader")
        == "src.stage2.pilot_plane_mask_producer.load_lod2_citygml_scene",
        "visibility implementation drift",
    )
    require(visibility.get("all_scene_surfaces_are_occluders") is True, "full-scene occlusion disabled")
    require(visibility.get("positive_hit") == "selected-building RoofSurface only", "visibility positive class drift")
    require(float(visibility.get("aoi_padding_m", 0.0)) == 180.0, "visibility AOI padding drift")
    require(int(visibility.get("open3d_scene_builds_per_job", 0)) == 1, "visibility scene cache drift")
    require(int(selection.get("unique_visible_views_required", 0)) == 1, "unique visible-view requirement drift")

    visual = config["visual_contract"]
    require((visual.get("rows"), visual.get("columns")) == (5, 5), "panel grid drift")
    require(visual.get("single_visual_file") is True, "single panel contract drift")
    require(float(visual["camera_contract"].get("z_exaggeration", 0.0)) == 1.0, "Z exaggeration drift")
    require(config["outputs"].get("root") == "phases/p2-gsjso/runs/fusion_w1/20260726_fusion_w1_aprime/review_v7_reference_roof_boundary", "review v7 root drift")
    require(set(config["outputs"]) == {"root", "panel", "complete"}, "v7 output set drift")
    publication = config["publication"]
    require(publication.get("overwrite_allowed") is False, "overwrite policy drift")
    require(publication.get("historical_v4_v5_v6_overwrite_or_delete_forbidden") is True, "historical output protection absent")
    execution = config["execution"]
    require(execution.get("network") == "none", "network contract drift")
    require(execution.get("gpus_required") is False and execution.get("gpu_devices_used") == [], "v7 must be CPU-only")
    require(execution.get("nonroot") is True, "v7 must be nonroot")
    require(execution.get("unrelated_queue_allowed") is True, "queue coexistence drift")
    require(execution.get("output_namespace_isolated_from_training") is True, "output isolation absent")

    base_config = base.load_config(base.repo_path(base_contract["config"]))
    for identity in allowed_identities(config):
        validate_identity(config, base_config, *identity)
    return config, base_config


def output_job_dir(
    config: Mapping[str, Any],
    building_id: str,
    arm: str,
    replicate: str,
    output_root: Path | None = None,
) -> Path:
    root = base.repo_path(config["outputs"]["root"]) if output_root is None else output_root.resolve()
    return root / "by_building" / building_id / f"arm_{arm}" / replicate


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _element_id(element: ET.Element) -> str:
    return next((str(value) for key, value in element.attrib.items() if _local_name(key) == "id"), "")


def _poslist_points(element: ET.Element) -> np.ndarray | None:
    for child in element.iter():
        if _local_name(child.tag) != "posList" or not child.text:
            continue
        try:
            values = np.asarray([float(value) for value in child.text.split()], dtype=np.float64)
        except ValueError:
            continue
        dimension = int(child.attrib.get("srsDimension", element.attrib.get("srsDimension", 3)))
        if dimension not in {2, 3} or len(values) % dimension:
            dimension = 3 if len(values) % 3 == 0 else 2
        require(len(values) % dimension == 0, "reference exterior posList dimension is invalid")
        points = values.reshape(-1, dimension)
        if dimension == 2:
            points = np.column_stack((points, np.zeros(len(points))))
        if len(points) >= 3:
            return np.asarray(points[:, :3], dtype=np.float64)

    positions: list[list[float]] = []
    for child in element.iter():
        if _local_name(child.tag) != "pos" or not child.text:
            continue
        try:
            values = [float(value) for value in child.text.split()]
        except ValueError:
            continue
        if len(values) == 2:
            values.append(0.0)
        if len(values) >= 3:
            positions.append(values[:3])
    if len(positions) >= 3:
        return np.asarray(positions, dtype=np.float64)
    return None


def reference_roof_exterior_rings(
    paths: Sequence[Path], building_id: str
) -> tuple[list[np.ndarray], dict[str, Any]]:
    """Load only exterior rings of reference LoD2 RoofSurface polygons."""

    for path in paths:
        try:
            iterator = ET.iterparse(path, events=("end",))
            for _, element in iterator:
                name = _local_name(element.tag)
                if name == "cityObjectMember":
                    element.clear()
                    continue
                if name != "Building":
                    continue
                if _element_id(element) != building_id and building_id not in {str(value) for value in element.attrib.values()}:
                    element.clear()
                    continue
                rings: list[np.ndarray] = []
                roof_surfaces_n = 0
                polygons_n = 0
                for roof in element.iter():
                    if _local_name(roof.tag) != "RoofSurface":
                        continue
                    surface_has_ring = False
                    for polygon in roof.iter():
                        if _local_name(polygon.tag) != "Polygon":
                            continue
                        polygons_n += 1
                        exteriors = [child for child in polygon.iter() if _local_name(child.tag) == "exterior"]
                        require(len(exteriors) == 1, "reference RoofSurface Polygon must have exactly one exterior")
                        ring = _poslist_points(exteriors[0])
                        require(ring is not None and len(ring) >= 3, "reference RoofSurface exterior ring absent")
                        require(np.isfinite(ring).all(), "reference RoofSurface exterior is nonfinite")
                        if not np.allclose(ring[0], ring[-1], rtol=0.0, atol=1.0e-9):
                            ring = np.vstack((ring, ring[0]))
                        require(len(ring) >= 4, "reference RoofSurface exterior ring is too short")
                        rings.append(ring)
                        surface_has_ring = True
                    if surface_has_ring:
                        roof_surfaces_n += 1
                require(bool(rings), f"reference RoofSurface exterior absent for {building_id}")
                source = base.file_record(path)
                return rings, {
                    "building_id": building_id,
                    "source": source,
                    "roof_surfaces_n": int(roof_surfaces_n),
                    "polygons_n": int(polygons_n),
                    "exterior_rings_n": int(len(rings)),
                    "vertices_with_closure_n": int(sum(len(ring) for ring in rings)),
                    "z_min_m": float(min(ring[:, 2].min() for ring in rings)),
                    "z_max_m": float(max(ring[:, 2].max() for ring in rings)),
                    "included_semantics": ["RoofSurface"],
                    "ring_role": "Polygon exterior only",
                    "interior_rings_used": False,
                }
        except (OSError, ET.ParseError) as exc:
            raise PanelError(f"cannot parse reference GML {base.display_path(path)}: {exc}") from exc
    raise PanelError(f"reference building absent: {building_id}")


def _project_rings(
    rings_base: Sequence[np.ndarray],
    pose: Any,
    camera: Any,
    scene_reference: Mapping[str, Any],
    coordinate: Mapping[str, Any],
) -> tuple[list[np.ndarray], np.ndarray, np.ndarray]:
    lengths: list[int] = []
    open_rings: list[np.ndarray] = []
    for ring in rings_base:
        values = np.asarray(ring, dtype=np.float64)
        open_ring = values[:-1] if np.allclose(values[0], values[-1], rtol=0.0, atol=1.0e-9) else values
        require(len(open_ring) >= 3, "reference roof ring has fewer than three unique vertices")
        open_rings.append(open_ring)
        lengths.append(len(open_ring))
    flat = np.vstack(open_rings)
    result = image_projection.project_base_points(
        flat,
        pose,
        camera,
        scene_reference,
        input_datum=str(coordinate["input_vertical_datum"]),
        geoid_m=float(coordinate["orthometric_to_ellipsoidal_geoid_m"]),
        config_path=base.repo_path(coordinate["projection_config"]),
        min_depth_m=1.0,
    )
    projected: list[np.ndarray] = []
    offset = 0
    for length in lengths:
        uv = np.asarray(result.uv[offset : offset + length], dtype=np.float64)
        projected.append(np.vstack((uv, uv[0])))
        offset += length
    return projected, result.depth, result.valid


def _boundary_values(rings_uv: Sequence[np.ndarray]) -> np.ndarray:
    values = [np.asarray(ring, dtype=np.float64)[:-1] for ring in rings_uv]
    require(bool(values), "projected roof boundary is empty")
    result = np.vstack(values)
    require(result.ndim == 2 and result.shape[1] == 2, "projected roof boundary is malformed")
    return result


def _nan_separated_rings(rings_uv: Sequence[np.ndarray]) -> np.ndarray:
    values: list[np.ndarray] = []
    for ring in rings_uv:
        values.append(np.asarray(ring, dtype=np.float64))
        values.append(np.full((1, 2), np.nan, dtype=np.float64))
    return np.vstack(values)


def _crop_box(
    rings_uv: Sequence[np.ndarray],
    width: int,
    height: int,
    crop: Mapping[str, Any],
    *,
    padding_fraction: float,
) -> tuple[int, int, int, int]:
    values = _boundary_values(rings_uv)
    minimum = values.min(axis=0)
    maximum = values.max(axis=0)
    center = 0.5 * (minimum + maximum)
    span = maximum - minimum
    padding = float(padding_fraction)
    desired_width = max(float(crop["minimum_width_pixels"]), float(span[0] * (1.0 + 2.0 * padding)))
    desired_height = max(float(crop["minimum_height_pixels"]), float(span[1] * (1.0 + 2.0 * padding)))
    desired_width = min(desired_width, float(width))
    desired_height = min(desired_height, float(height))
    x0 = int(math.floor(center[0] - desired_width / 2.0))
    y0 = int(math.floor(center[1] - desired_height / 2.0))
    x1 = int(math.ceil(center[0] + desired_width / 2.0))
    y1 = int(math.ceil(center[1] + desired_height / 2.0))
    if x0 < 0:
        x1 -= x0
        x0 = 0
    if y0 < 0:
        y1 -= y0
        y0 = 0
    if x1 > width:
        x0 -= x1 - width
        x1 = width
    if y1 > height:
        y0 -= y1 - height
        y1 = height
    x0, y0 = max(0, x0), max(0, y0)
    require(x0 < x1 and y0 < y1, "reference roof crop is empty")
    require(np.all(values[:, 0] >= x0) and np.all(values[:, 0] < x1), "reference roof leaves crop horizontally")
    require(np.all(values[:, 1] >= y0) and np.all(values[:, 1] < y1), "reference roof leaves crop vertically")
    return x0, y0, x1, y1


def _dilate_bool(mask: np.ndarray, radius: int) -> np.ndarray:
    values = np.asarray(mask, dtype=bool)
    require(values.ndim == 2, "visibility mask must be HxW")
    require(radius >= 0, "visibility dilation radius must be nonnegative")
    if radius == 0:
        return values.copy()
    height, width = values.shape
    padded = np.pad(values, radius, mode="constant", constant_values=False)
    output = np.zeros_like(values)
    for dy in range(2 * radius + 1):
        for dx in range(2 * radius + 1):
            output |= padded[dy : dy + height, dx : dx + width]
    return output


def _visible_boundary_polylines(
    rings_uv: Sequence[np.ndarray], visibility_mask: np.ndarray
) -> tuple[list[np.ndarray], dict[str, int]]:
    """Clip projected roof-ring lines to the exact target-roof first-hit mask."""

    mask = np.asarray(visibility_mask, dtype=bool)
    height, width = mask.shape
    polylines: list[np.ndarray] = []
    samples_n = 0
    visible_samples_n = 0
    for ring in rings_uv:
        values = np.asarray(ring, dtype=np.float64)
        for start, stop in zip(values[:-1], values[1:]):
            if not np.isfinite(start).all() or not np.isfinite(stop).all():
                continue
            steps = max(2, int(math.ceil(float(np.max(np.abs(stop - start))))) + 1)
            samples = np.linspace(start, stop, steps, endpoint=True, dtype=np.float64)
            pixels = np.rint(samples).astype(np.int64)
            in_frame = (
                (pixels[:, 0] >= 0)
                & (pixels[:, 0] < width)
                & (pixels[:, 1] >= 0)
                & (pixels[:, 1] < height)
            )
            visible = np.zeros(steps, dtype=bool)
            visible[in_frame] = mask[pixels[in_frame, 1], pixels[in_frame, 0]]
            samples_n += int(steps)
            visible_samples_n += int(visible.sum())
            run_start: int | None = None
            for index, keep in enumerate(np.append(visible, False)):
                if keep and run_start is None:
                    run_start = index
                elif not keep and run_start is not None:
                    if index - run_start >= 2:
                        polylines.append(samples[run_start:index])
                    run_start = None
    return polylines, {
        "boundary_samples_n": int(samples_n),
        "visible_boundary_samples_n": int(visible_samples_n),
        "visible_boundary_polylines_n": int(len(polylines)),
    }


def _scene_world_offset(scene_reference: Mapping[str, Any]) -> np.ndarray:
    transform = scene_reference.get("base_to_canonical") or {}
    shift = np.asarray(transform.get("shift"), dtype=np.float64)
    scale = np.asarray(transform.get("scale"), dtype=np.float64)
    require(shift.shape == (3,) and scale.shape == (3,), "scene reference transform malformed")
    require(np.allclose(scale, np.ones(3), rtol=0.0, atol=0.0), "LoD2 visibility requires unit scene scale")
    require(transform.get("swap_xy") is False, "LoD2 visibility requires unswapped scene axes")
    return -shift


def _build_cached_lod2_raycaster(scene_data: Any) -> dict[str, Any]:
    """Build the formal LoD2 primitive-ID ray scene once per panel job."""

    try:
        import open3d as o3d
    except ImportError as exc:  # pragma: no cover - pinned Docker includes Open3D
        raise PanelError("v7 LoD2 visibility requires pinned Docker Open3D") from exc
    triangles = np.asarray(scene_data.triangles_local, dtype=np.float32)
    vertices = triangles.reshape(-1, 3)
    indices = np.arange(len(vertices), dtype=np.uint32).reshape(-1, 3)
    ray_scene = o3d.t.geometry.RaycastingScene()
    ray_scene.add_triangles(o3d.core.Tensor(vertices), o3d.core.Tensor(indices))
    positive_triangle = (
        (np.asarray(scene_data.triangle_class) == pilot_plane_mask_producer.SURFACE_CLASS["RoofSurface"])
        & np.asarray(scene_data.triangle_selected_building, dtype=bool)
    )
    return {
        "o3d": o3d,
        "scene": ray_scene,
        "positive_triangle": positive_triangle,
    }


def _raycast_cached_lod2_roof_bool_mask(
    cached: Mapping[str, Any], camera: Any, pose: Any, *, ray_chunk_size: int
) -> np.ndarray:
    """Exact first-primitive mask, equivalent to the formal producer helper."""

    total = int(camera.width) * int(camera.height)
    output = np.zeros(total, dtype=bool)
    o3d = cached["o3d"]
    invalid = o3d.t.geometry.RaycastingScene.INVALID_ID
    positive_triangle = np.asarray(cached["positive_triangle"], dtype=bool)
    ray_scene = cached["scene"]
    for start in range(0, total, ray_chunk_size):
        stop = min(total, start + ray_chunk_size)
        rays = pilot_plane_mask_producer._camera_ray_chunk(camera, pose, start, stop)
        primitive = ray_scene.cast_rays(o3d.core.Tensor(rays))["primitive_ids"].numpy()
        hit = primitive != invalid
        local = np.zeros(stop - start, dtype=bool)
        local[hit] = positive_triangle[primitive[hit].astype(np.int64)]
        output[start:stop] = local
    return np.ascontiguousarray(output.reshape(camera.height, camera.width))


def projected_reference_views(evidence: Mapping[str, Any], config: Mapping[str, Any]) -> dict[str, Any]:
    preprocess_path = base.repo_path(evidence["source_records"]["preprocess_manifest"]["path"])
    preprocess_root = preprocess_path.parent
    preprocess = base.load_json(preprocess_path)
    contract = config["first_row_reference_contract"]
    coordinate = contract["coordinate_contract"]
    building_id = str(evidence["identity"]["building_id"])

    require(int(preprocess.get("pose_binding", {}).get("additional_transform_application_count", -1)) == 0, "preprocess pose has an additional transform application")
    corrected_source_hash = preprocess.get("pose_binding", {}).get("corrected_images_sha256")
    require(corrected_source_hash == coordinate["adopted_corrected_images_sha256"], "adopted corrected-pose hash drift")
    source_hashes = preprocess.get("source_inputs", {}).get("sha256", {})
    base.verify_projection_config_migration(
        source_hashes, coordinate["projection_config_migration"]
    )
    require(
        source_hashes.get(coordinate["scene_reference_frame"])
        == coordinate["scene_reference_sha256"],
        f"preprocess did not bind coordinate source: {coordinate['scene_reference_frame']}",
    )

    reference_paths = [base.repo_path(record["path"]) for record in evidence["reference_records"]]
    rings_base, roof_receipt = reference_roof_exterior_rings(reference_paths, building_id)
    scene_path = base.repo_path(coordinate["scene_reference_frame"])
    scene_record = base.file_record(scene_path)
    require(scene_record["sha256"] == coordinate["scene_reference_sha256"], "scene reference drift")
    scene_reference = base.load_json(scene_path)
    projection_config_record = base.file_record(base.repo_path(coordinate["projection_config"]))
    require(projection_config_record["sha256"] == coordinate["projection_config_sha256"], "projection config drift")

    cameras_path = preprocess_root / "sparse/0/cameras.bin"
    images_path = preprocess_root / "sparse/0/images.bin"
    views_path = preprocess_root / "views.csv"
    index_path = preprocess_root / "supervision_index.csv"
    cameras_record = v4.manifest_bound_record(cameras_path, preprocess, "corrected cameras")
    images_record = v4.manifest_bound_record(images_path, preprocess, "corrected poses")
    views_record = v4.manifest_bound_record(views_path, preprocess, "selected views")
    index_record = v4.manifest_bound_record(index_path, preprocess, "supervision index")
    cameras = read_cameras_bin(cameras_path)
    images = read_images_bin(images_path)
    images_by_name = {image.name: image for image in images.values()}
    view_rows = {row["image_name"]: row for row in base.read_csv(views_path)}
    require(bool(view_rows) and all(row.get("corrected_pose_source_sha256") == corrected_source_hash for row in view_rows.values()), "selected views are not bound to adopted corrected poses")
    supervision_rows = base.read_csv(index_path)
    require(bool(supervision_rows), "supervision index is empty")

    selection = contract["view_selection"]
    visibility_contract = selection["visibility_gate"]
    world_offset = _scene_world_offset(scene_reference)
    target_xy_local = np.vstack(rings_base)[:, :2] - world_offset[:2]
    aoi_padding_m = float(visibility_contract["aoi_padding_m"])
    aoi_xy_local = [
        float(target_xy_local[:, 0].min() - aoi_padding_m),
        float(target_xy_local[:, 1].min() - aoi_padding_m),
        float(target_xy_local[:, 0].max() + aoi_padding_m),
        float(target_xy_local[:, 1].max() + aoi_padding_m),
    ]
    lod2_scene = pilot_plane_mask_producer.load_lod2_citygml_scene(
        reference_paths,
        [building_id],
        world_offset=world_offset,
        orthometric_geoid_m=float(coordinate["orthometric_to_ellipsoidal_geoid_m"]),
        aoi_xy_local=aoi_xy_local,
    )
    cached_raycaster = _build_cached_lod2_raycaster(lod2_scene)
    scene_receipt = {
        "method": visibility_contract["method"],
        "implementation": visibility_contract["implementation"],
        "triangles_n": int(len(lod2_scene.triangles_local)),
        "selected_building_roof_triangles_n": int(
            np.sum(
                (lod2_scene.triangle_class == pilot_plane_mask_producer.SURFACE_CLASS["RoofSurface"])
                & lod2_scene.triangle_selected_building
            )
        ),
        "all_scene_surfaces_are_occluders": True,
        "positive_hit": visibility_contract["positive_hit"],
        "world_offset": world_offset.tolist(),
        "orthometric_geoid_m": float(coordinate["orthometric_to_ellipsoidal_geoid_m"]),
        "aoi_definition": visibility_contract["aoi_definition"],
        "aoi_padding_m": aoi_padding_m,
        "aoi_xy_local": aoi_xy_local,
        "ray_chunk_size": int(visibility_contract["ray_chunk_size"]),
        "open3d_scene_builds_per_job": 1,
        "projection_prefilter": visibility_contract["projection_prefilter_before_raycast"],
    }
    candidates: list[dict[str, Any]] = []
    for row in supervision_rows:
        image_name = row["image_name"]
        require(image_name in images_by_name and image_name in view_rows, f"training view pose absent: {image_name}")
        pose = images_by_name[image_name]
        require(pose.camera_id in cameras, f"training view camera absent: {image_name}")
        camera = cameras[pose.camera_id]
        require(camera.model in {"PINHOLE", "SIMPLE_PINHOLE"}, f"exact LoD2 ray gate requires an undistorted pinhole camera: {image_name}={camera.model}")
        rings_uv, depth, valid = _project_rings(rings_base, pose, camera, scene_reference, coordinate)
        values = _boundary_values(rings_uv)
        margin_x = max(int(selection["minimum_margin_pixels"]), int(round(camera.width * float(selection["required_boundary_margin_fraction"]))))
        margin_y = max(int(selection["minimum_margin_pixels"]), int(round(camera.height * float(selection["required_boundary_margin_fraction"]))))
        in_frame = (
            valid
            & (values[:, 0] >= 0.0)
            & (values[:, 0] < camera.width)
            & (values[:, 1] >= 0.0)
            & (values[:, 1] < camera.height)
        )
        in_margin = (
            in_frame
            & (values[:, 0] >= margin_x)
            & (values[:, 0] < camera.width - margin_x)
            & (values[:, 1] >= margin_y)
            & (values[:, 1] < camera.height - margin_y)
        )
        minimum = values.min(axis=0) if np.isfinite(values).all() else np.asarray([math.nan, math.nan])
        maximum = values.max(axis=0) if np.isfinite(values).all() else np.asarray([math.nan, math.nan])
        span = maximum - minimum
        bbox_area = float(span[0] * span[1]) if np.isfinite(span).all() else 0.0
        boundary_center = 0.5 * (minimum + maximum)
        image_center = np.asarray([camera.width / 2.0, camera.height / 2.0], dtype=np.float64)
        half_diagonal = float(np.linalg.norm(image_center))
        centrality = float(np.linalg.norm(boundary_center - image_center) / half_diagonal) if np.isfinite(boundary_center).all() else math.inf
        projection_prefilter_passed = bool(
            np.all(in_frame)
            and bbox_area >= float(selection["minimum_projected_bbox_area_px2"])
        )
        if projection_prefilter_passed:
            visible_mask = _raycast_cached_lod2_roof_bool_mask(
                cached_raycaster,
                camera,
                pose,
                ray_chunk_size=int(visibility_contract["ray_chunk_size"]),
            )
        else:
            visible_mask = np.zeros((camera.height, camera.width), dtype=bool)
        visible_pixels_n = int(visible_mask.sum())
        if visible_pixels_n:
            visible_y, visible_x = np.nonzero(visible_mask)
            visible_mask_bbox = [
                int(visible_x.min()),
                int(visible_y.min()),
                int(visible_x.max()) + 1,
                int(visible_y.max()) + 1,
            ]
        else:
            visible_mask_bbox = None
        dilated_visibility = _dilate_bool(
            visible_mask,
            int(visibility_contract["visible_boundary_mask_dilation_pixels"]),
        )
        visible_polylines, visible_boundary = _visible_boundary_polylines(
            rings_uv, dilated_visibility
        )
        candidates.append(
            {
                "row": row,
                "view_row": view_rows[image_name],
                "pose": pose,
                "camera": camera,
                "rings_uv": rings_uv,
                "depth": depth,
                "boundary_full_in_frame": bool(np.all(in_frame)),
                "vertices_in_frame_n": int(in_frame.sum()),
                "all_valid_and_inside_margin": bool(np.all(in_margin)),
                "vertices_inside_margin_n": int(in_margin.sum()),
                "vertices_n": int(len(in_margin)),
                "margin_pixels_xy": [int(margin_x), int(margin_y)],
                "bbox_area_px2": bbox_area,
                "bbox_width_px": float(span[0]) if np.isfinite(span[0]) else 0.0,
                "bbox_height_px": float(span[1]) if np.isfinite(span[1]) else 0.0,
                "centrality_normalized": centrality,
                "projection_prefilter_passed": projection_prefilter_passed,
                "raycast_performed": projection_prefilter_passed,
                "visible_target_roof_pixels_n": visible_pixels_n,
                "visible_target_roof_bbox_xyxy": visible_mask_bbox,
                "visible_boundary_polylines": visible_polylines,
                **visible_boundary,
            }
        )

    minimum_pixels = int(visibility_contract["minimum_visible_target_roof_pixels"])
    scene_receipt["candidate_views_n"] = int(len(candidates))
    scene_receipt["projection_prefilter_passed_views_n"] = int(
        sum(candidate["projection_prefilter_passed"] for candidate in candidates)
    )
    scene_receipt["raycasted_views_n"] = int(
        sum(candidate["raycast_performed"] for candidate in candidates)
    )
    common_eligible = [
        candidate for candidate in candidates
        if candidate["boundary_full_in_frame"]
        and candidate["visible_target_roof_pixels_n"] >= minimum_pixels
        and candidate["visible_boundary_polylines_n"] > 0
        and candidate["bbox_area_px2"] >= float(selection["minimum_projected_bbox_area_px2"])
    ]
    margin_eligible = [candidate for candidate in common_eligible if candidate["all_valid_and_inside_margin"]]
    if margin_eligible:
        eligible = margin_eligible
        selected_tier = "A_margin_full_in_frame_and_target_roof_visible"
    else:
        eligible = common_eligible
        selected_tier = "B_fallback_full_in_frame_and_target_roof_visible"
    require(bool(eligible), "no full-in-frame training view has a visible target RoofSurface first hit")
    ranked = sorted(
        eligible,
        key=lambda candidate: (
            -float(candidate["bbox_area_px2"]),
            float(candidate["centrality_normalized"]),
            float(candidate["view_row"]["nadir_deg"]),
            float(candidate["view_row"]["frame_radius"]),
            int(candidate["row"]["selection_order"]),
            str(candidate["row"]["image_name"]),
        ),
    )
    require(len(ranked) >= int(selection["unique_visible_views_required"]), "no unique visible reference-roof view")

    records: dict[str, Any] = {
        "projection_config": projection_config_record,
        "scene_reference_frame": scene_record,
        "supervision_index": index_record,
        "selected_views": views_record,
        "corrected_cameras": cameras_record,
        "corrected_poses": images_record,
    }
    primary = ranked[0]
    row = primary["row"]
    image_path = preprocess_root / "images" / row["image_name"]
    image_record = base.file_record(image_path)
    with Image.open(image_path) as source:
        image = source.convert("RGB")
        image.load()
    camera = primary["camera"]
    require(image.size == (camera.width, camera.height), f"selected image/camera dimensions drift: {row['image_name']}")
    medium_crop_box = _crop_box(
        primary["rings_uv"],
        camera.width,
        camera.height,
        contract["crop"],
        padding_fraction=float(contract["crop"]["medium_padding_fraction"]),
    )
    tight_crop_box = _crop_box(
        primary["rings_uv"],
        camera.width,
        camera.height,
        contract["crop"],
        padding_fraction=float(contract["crop"]["tight_padding_fraction"]),
    )
    primary = {
        **primary,
        "image": image,
        "image_record": image_record,
        "medium_crop_box": medium_crop_box,
        "tight_crop_box": tight_crop_box,
    }
    records["selected_full_image_primary"] = image_record

    candidate_receipts = [
        {
            "image_name": candidate["row"]["image_name"],
            "selection_order": int(candidate["row"]["selection_order"]),
            "boundary_full_in_frame": candidate["boundary_full_in_frame"],
            "vertices_in_frame_n": candidate["vertices_in_frame_n"],
            "all_valid_and_inside_margin": candidate["all_valid_and_inside_margin"],
            "vertices_inside_margin_n": candidate["vertices_inside_margin_n"],
            "vertices_n": candidate["vertices_n"],
            "margin_pixels_xy": candidate["margin_pixels_xy"],
            "bbox_area_px2": candidate["bbox_area_px2"],
            "bbox_width_px": candidate["bbox_width_px"],
            "bbox_height_px": candidate["bbox_height_px"],
            "centrality_normalized": candidate["centrality_normalized"],
            "projection_prefilter_passed": candidate["projection_prefilter_passed"],
            "raycast_performed": candidate["raycast_performed"],
            "visible_target_roof_pixels_n": candidate["visible_target_roof_pixels_n"],
            "visible_target_roof_bbox_xyxy": candidate["visible_target_roof_bbox_xyxy"],
            "boundary_samples_n": candidate["boundary_samples_n"],
            "visible_boundary_samples_n": candidate["visible_boundary_samples_n"],
            "visible_boundary_polylines_n": candidate["visible_boundary_polylines_n"],
            "nadir_deg": float(candidate["view_row"]["nadir_deg"]),
            "frame_radius": float(candidate["view_row"]["frame_radius"]),
        }
        for candidate in candidates
    ]
    seed_manifest = preprocess["seed"]
    return {
        "row": primary["row"],
        "view_row": primary["view_row"],
        "image": primary["image"],
        "mask": np.zeros((primary["camera"].height, primary["camera"].width), dtype=bool),
        "crop_box": primary["medium_crop_box"],
        "seed_uv": np.empty((0, 2), dtype=np.float64),
        "seed_inframe": np.empty((0,), dtype=bool),
        "footprint_uv": _nan_separated_rings(primary["visible_boundary_polylines"]),
        "locator_canonical_z": float("nan"),
        "mask_alignment": {
            "selected_containment_in_projected_locator": float("nan"),
            "all_views_min": float("nan"),
            "all_views_median": float("nan"),
            "all_views_max": float("nan"),
            "worst_image_name": "not_applicable_reference_boundary_only",
            "worst_containment": float("nan"),
        },
        "primary": primary,
        "reference_roof_rings_base": rings_base,
        "reference_roof": roof_receipt,
        "seed_contract": {
            "source": "ALS classification 6 only; displayed in row 2, never in row 1",
            "unfiltered_points_n": int(seed_manifest["source_unfiltered_points_n"]),
            "filtered_points_n": int(seed_manifest["filtered_points_n"]),
            "visibility_epsilon_m": float(seed_manifest["visibility"]["epsilon_m"]),
            "visibility_minimum_views_k": int(seed_manifest["visibility"]["minimum_views_k"]),
            "class2_rows_n": int(seed_manifest["class2_rows_n"]),
            "sfm_rows_n": int(seed_manifest["sfm_rows_n"]),
        },
        "selection": {
            "mode": "post-hoc evaluation-only reference roof visual selection",
            "method": selection["rank"],
            "candidates_n": len(candidates),
            "target_roof_visible_views_n": int(sum(candidate["visible_target_roof_pixels_n"] >= minimum_pixels for candidate in candidates)),
            "usable_visible_views_n": len(common_eligible),
            "margin_visible_views_n": len(margin_eligible),
            "selected_tier": selected_tier,
            "primary_image": primary["row"]["image_name"],
            "additional_usable_visible_image": ranked[1]["row"]["image_name"] if len(ranked) > 1 else None,
            "primary_rank_metrics": {
                "centrality_normalized": primary["centrality_normalized"],
                "bbox_area_px2": primary["bbox_area_px2"],
                "nadir_deg": float(primary["view_row"]["nadir_deg"]),
                "frame_radius": float(primary["view_row"]["frame_radius"]),
                "visible_target_roof_pixels_n": primary["visible_target_roof_pixels_n"],
                "visible_boundary_samples_n": primary["visible_boundary_samples_n"],
                "boundary_samples_n": primary["boundary_samples_n"],
            },
            "image_pixels_used_for_ranking": False,
            "M_j_used_for_ranking_or_eligibility": False,
            "ALS_or_TIN_used_for_ranking_or_eligibility": False,
            "output_CityJSON_used_for_ranking_or_eligibility": False,
            "reference_GML_used_for_post_hoc_visual_ranking": True,
            "visibility_scene": scene_receipt,
            "candidates": candidate_receipts,
        },
        "coordinate_contract": {
            **coordinate,
            "observed_corrected_cameras_sha256": cameras_record["sha256"],
            "observed_corrected_images_sha256": corrected_source_hash,
            "per_building_subset_images_bin_sha256": images_record["sha256"],
        },
        "first_row_exclusions": list(contract["geometry_exclusions"]),
        "records": records,
    }


def augment_evidence(evidence: dict[str, Any], config: Mapping[str, Any]) -> dict[str, Any]:
    result = dict(evidence)
    surfaces, surface_stats = v4.load_cityjson_surfaces(evidence["cityjson_path"])
    score, score_record = v4.primary_score(evidence)
    input_view = projected_reference_views(evidence, config)
    roofer_adapter = {
        "input_locator_contract": {
            "footprint_xy": "phases/p0-audit/data/work/footprints/lod2_ground_plan.gpkg",
            "footprint_sha256": "259cf04ec0c9411e669e75f61c37ea634290fcd40b230f6ed9b67328041c87fa",
            "footprint_role": "approved GroundSurface XY used by frozen Roofer output only; not used by v7 first row",
        }
    }
    roofer_prepare, roofer_prepare_record = v4.roofer_prepare_provenance(evidence, roofer_adapter)
    source_records = dict(evidence["source_records"])
    if "selected_full_image" in source_records:
        source_records["base_resolver_selected_full_image_unused_by_v7"] = source_records.pop("selected_full_image")
    if "selected_M_j" in source_records:
        source_records["base_resolver_selected_M_j_unused_by_v7"] = source_records.pop("selected_M_j")
    source_records["primary_score"] = score_record
    source_records["primary_roofer_prepare"] = roofer_prepare_record
    source_records.update(input_view["records"])
    result.update(
        {
            "cityjson_surfaces": surfaces,
            "cityjson_surface_stats": surface_stats,
            "primary_score": score,
            "image_mask": input_view,
            "roofer_prepare": roofer_prepare,
            "source_records": source_records,
        }
    )
    return result


def _plot_reference_boundary(ax: Any, image: Image.Image, rings_uv: Sequence[np.ndarray], offset: tuple[int, int] = (0, 0)) -> None:
    ax.imshow(np.asarray(image))
    dx, dy = offset
    for ring in rings_uv:
        values = np.asarray(ring, dtype=np.float64) - np.asarray([dx, dy], dtype=np.float64)
        line = ax.plot(values[:, 0], values[:, 1], color="#ff7a00", linewidth=2.25, solid_capstyle="round", solid_joinstyle="round")[0]
        line.set_path_effects([patheffects.Stroke(linewidth=3.8, foreground="white"), patheffects.Normal()])
    ax.axis("off")


def render_panel(
    staging: Path,
    config: Mapping[str, Any],
    evidence: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    font, font_record = base.load_cjk_font(evidence["base_config"])
    visual = config["visual_contract"]
    palette = visual["semantic_palette"]
    frame = v4.scene_frame(evidence, config)
    topology = v4.mesh_topology_stats(evidence["mesh_faces"])
    cityjson_render = v4.cityjson_render_parts(evidence["cityjson_surfaces"], frame)["stats"]
    score = v4.score_row(evidence)
    view = evidence["image_mask"]
    primary = view["primary"]

    fig = v4.plt.figure(figsize=tuple(visual["panel_inches"]))
    grid = fig.add_gridspec(5, 5, left=0.045, right=0.987, bottom=0.055, top=0.925, wspace=0.17, hspace=0.25)
    identity = evidence["identity"]
    fig.suptitle(
        f"{identity['building_id']} | arm {identity['arm']} | {identity['replicate']}\n"
        "평가용 LoD2 지붕 경계로 입력 위치 확인 → ALS class 6 시드 → 학습 관찰·TSDF/MC → Roofer CityJSON LoD2.2 → 평가 전용 참조 중첩",
        fontproperties=font,
        fontsize=15,
        color=palette["charcoal"],
    )
    row_labels = [
        (0.840, "1  입력 사진·참조 경계 / Photo locator (evaluation only)"),
        (0.670, "2  ALS 시드 / Filtered ALS seed"),
        (0.500, "3  TSDF 메시 / TSDF mesh"),
        (0.330, "4  조립 / Roofer CityJSON"),
        (0.160, "5  평가 전용 / Evaluation-only overlay"),
    ]
    for y, label in row_labels:
        fig.text(0.008, y, label, rotation=90, va="center", ha="center", fontsize=8.0, color=palette["charcoal"], fontproperties=font)

    ax = fig.add_subplot(grid[0, 0])
    _plot_reference_boundary(ax, primary["image"], primary["visible_boundary_polylines"])
    v4.short_title(ax, "A. 원본 전체·보이는 참조 LoD2 지붕 경계", "Full training photo · visible reference roof boundary", font, fontsize=8.2)

    x0, y0, x1, y1 = primary["medium_crop_box"]
    primary_crop = primary["image"].crop((x0, y0, x1, y1))
    ax = fig.add_subplot(grid[0, 1])
    _plot_reference_boundary(ax, primary_crop, primary["visible_boundary_polylines"], (x0, y0))
    v4.short_title(ax, "B. 문맥 확대·보이는 경계만", f"Context crop {primary['row']['image_name']} · visible boundary only", font, fontsize=8.2)

    tx0, ty0, tx1, ty1 = primary["tight_crop_box"]
    tight_crop = primary["image"].crop((tx0, ty0, tx1, ty1))
    ax = fig.add_subplot(grid[0, 2])
    _plot_reference_boundary(ax, tight_crop, primary["visible_boundary_polylines"], (tx0, ty0))
    v4.short_title(ax, "C. 밀착 확대·보이는 경계만", f"Tight crop {primary['row']['image_name']} · visible boundary only", font, fontsize=8.2)

    ax = fig.add_subplot(grid[0, 3])
    v4.plot_opacity(ax, evidence, config)
    v4.short_title(ax, "D. 지붕 시드 계보 opacity", "Roof seed-lineage opacity trajectory", font)

    measurement_lines = [
        "측정값 / Measurements (판정 없음 / no verdict)",
        f"assembly LoD2: {v4.format_bool(score.get('assembly_lod2_success'))}",
        f"LoD1 fallback: {v4.format_bool(score.get('lod1_fallback'))}",
        f"roof RMS: {v4.format_number(score.get('roof_rms_m'), 3)} m",
        f"Δ RMS vs P0′: {v4.format_number(score.get('delta_roof_rms_vs_p0_refl_m'), 3)} m",
        f"roof Hausdorff: {v4.format_number(score.get('roof_hausdorff_m'), 3)} m",
        f"roof completeness: {v4.format_number(score.get('roof_completeness'), 6)}",
        f"plane P/R/F1: {v4.format_number(score.get('plane_precision'), 3)} / {v4.format_number(score.get('plane_recall'), 3)} / {v4.format_number(score.get('plane_f1'), 3)}",
        f"XY overlap: {v4.format_number(score.get('xy_overlap_ratio'), 6)}",
        f"val3dity valid: {v4.format_bool(score.get('val3dity_valid'))}",
    ]
    v4.text_panel(fig.add_subplot(grid[0, 4]), "E. 정량 관찰", "Quantitative observations", measurement_lines, font)

    rendered_seed_points = 0
    for column, camera in enumerate(frame["cameras"]):
        ax = fig.add_subplot(grid[1, column], projection="3d")
        rendered_seed_points = v4.plot_seed(ax, evidence, frame, config)
        v4.configure_3d_axis(ax, frame, camera)
        v4.short_title(ax, f"ALS class 6 시드 · {camera['title_ko']}", f"Filtered ALS seed · {camera['title_en']}", font, fontsize=8.4)

    seed_xyz = np.asarray(evidence["seed_xyz"], dtype=np.float64)
    seed_contract = view["seed_contract"]
    selection = view["selection"]
    roof = view["reference_roof"]
    seed_lines = [
        "학습 전 prior / pre-training prior",
        "ALS class 6 only; class 2/SfM excluded",
        f"unfiltered → k≥{seed_contract['visibility_minimum_views_k']}: {seed_contract['unfiltered_points_n']} → {seed_contract['filtered_points_n']}",
        f"visibility ε: {seed_contract['visibility_epsilon_m']:.3f} m",
        f"seed Z: {seed_xyz[:, 2].min():.3f}–{seed_xyz[:, 2].max():.3f} m",
        f"displayed points/view: {rendered_seed_points}",
        "",
        f"photo view: {selection['primary_image']}",
        f"visible usable views: {selection['usable_visible_views_n']} (tier {selection['selected_tier']})",
        f"reference RoofSurface exteriors: {roof['exterior_rings_n']} rings",
        f"primary visible pixels: {selection['primary_rank_metrics']['visible_target_roof_pixels_n']}",
        f"area/centrality/nadir: {selection['primary_rank_metrics']['bbox_area_px2']:.0f}px² / {selection['primary_rank_metrics']['centrality_normalized']:.3f} / {selection['primary_rank_metrics']['nadir_deg']:.2f}°",
        "photo locator: evaluation-only reference after output freeze",
        "first-row overlay: boundary lines only",
        "ALS/TIN/M_j/Roofer output excluded from first row",
        "reference excluded from training/readout/assembly/scoring",
    ]
    v4.text_panel(fig.add_subplot(grid[1, 4]), "시드·사진 위치 영수증", "Seed & photo-locator receipt", seed_lines, font)

    rendered_faces = 0
    for column, camera in enumerate(frame["cameras"]):
        ax = fig.add_subplot(grid[2, column], projection="3d")
        rendered_faces = v4.plot_tsdf(ax, evidence, frame, config)
        v4.configure_3d_axis(ax, frame, camera)
        v4.short_title(ax, f"TSDF · {camera['title_ko']}", f"TSDF · {camera['title_en']}", font, fontsize=8.4)

    ax = fig.add_subplot(grid[2, 4])
    values, colors = base.downsample_xyz_rgb(np.asarray(evidence["samples_xyz"]), evidence["samples_rgb"], int(visual["maximum_scatter_points"]))
    principal = np.asarray(frame["axis"]["vector_east_north"], dtype=np.float64)
    origin = np.asarray(frame["local_origin_epsg25832_xyz"], dtype=np.float64)
    horizontal = (values[:, :2] - origin[:2]) @ principal
    ax.scatter(horizontal, values[:, 2] - origin[2], s=1.0, c=base.rgb_colors(colors, len(values), palette["tsdf_dark"]), linewidths=0, rasterized=True)
    ax.set_xlabel("principal horizontal (m)", fontsize=7)
    ax.set_ylabel("ΔZ (m)", fontsize=7)
    ax.set_aspect("equal", adjustable="datalim")
    ax.grid(True, color=palette["light_grey"], linewidth=0.45)
    ax.tick_params(labelsize=6)
    v4.short_title(ax, "TSDF 표면 샘플 주축 단면", "Principal section of TSDF surface samples", font, fontsize=8.4)

    for column, camera in enumerate(frame["cameras"]):
        ax = fig.add_subplot(grid[3, column], projection="3d")
        v4.plot_cityjson(ax, evidence, frame, config, alpha=0.92)
        v4.configure_3d_axis(ax, frame, camera)
        v4.short_title(ax, f"CityJSON · {camera['title_ko']}", f"LoD2.2 solid · {camera['title_en']}", font, fontsize=8.4)

    semantic = evidence["cityjson_surface_stats"]
    semantic_lines = [
        "canonical Roofer CityJSON",
        f"LoD: {v4.format_number(semantic['lod'], 1)} Solid",
        f"surfaces: {semantic['surfaces_n']}",
        f"vertices: {semantic['vertices_n']}",
        f"RoofSurface: {semantic['semantic_counts'].get('RoofSurface', 0)}",
        f"WallSurface: {semantic['semantic_counts'].get('WallSurface', 0)}",
        f"GroundSurface: {semantic['semantic_counts'].get('GroundSurface', 0)}",
        f"interior rings: {semantic['interior_rings_n']}",
        f"hole surfaces (wireframe): {cityjson_render['wireframe_only_surfaces_n']}",
        "",
        f"TSDF vertices: {len(evidence['mesh_xyz'])}",
        f"TSDF faces: {topology['faces_n']}",
        f"displayed faces/view: {rendered_faces}",
        f"boundary edges: {topology['boundary_edges_n']}",
        f"nonmanifold edges: {topology['nonmanifold_edges_n']}",
    ]
    v4.text_panel(fig.add_subplot(grid[3, 4]), "조립·메시 구조", "Assembly & mesh structure", semantic_lines, font)

    for column, camera in enumerate(frame["cameras"]):
        ax = fig.add_subplot(grid[4, column], projection="3d")
        v4.plot_cityjson(ax, evidence, frame, config, alpha=0.38)
        v4.plot_reference(ax, evidence, frame, config)
        v4.configure_3d_axis(ax, frame, camera)
        title_ko = "출력+참조 · 탑뷰 (평가 전용)" if camera["key"] == "top" else f"출력+참조 · {camera['title_ko']} (평가 전용)"
        title_en = "Top output + reference (evaluation only)" if camera["key"] == "top" else f"Output + reference · {camera['title_en']} (evaluation only)"
        v4.short_title(ax, title_ko, title_en, font, fontsize=8.1)

    comparison = v4.output_reference_comparison(evidence)
    output_xyz = comparison["output_xyz"]
    reference_xyz = comparison["reference_xyz"]
    origin_values = frame["local_origin_epsg25832_xyz"]
    comparison_lines = [
        "파랑/회색/갈색 면: Roofer output",
        "주황 점선+원: reference GML (evaluation only)",
        f"exact XY set equal: {v4.format_bool(comparison['exact_XY_coordinate_set_equal'])}",
        f"exact XYZ set equal: {v4.format_bool(comparison['exact_XYZ_coordinate_set_equal'])}",
        f"unique XYZ output/ref: {comparison['output_unique_xyz_n']} / {comparison['reference_unique_xyz_n']}",
        f"output SHA: {comparison['output_cityjson_sha256'][:12]}…",
        "reference SHA: " + ", ".join(value[:8] + "…" for value in comparison["reference_gml_sha256"]),
        "photo row uses reference RoofSurface only after output freeze",
        "3D view orientation: output only; reference excluded",
        "shared 3D bounds: seed + TSDF + output + eval reference",
        "projection: orthographic",
        "Z exaggeration: 1.0×",
        f"output Z: {output_xyz[:, 2].min():.3f}–{output_xyz[:, 2].max():.3f} m",
        f"reference Z: {reference_xyz[:, 2].min():.3f}–{reference_xyz[:, 2].max():.3f} m",
        f"origin E/N/Z: {origin_values[0]:.3f} / {origin_values[1]:.3f} / {origin_values[2]:.3f}",
        "CRS: EPSG:25832",
        "scientific verdict: null",
    ]
    v4.text_panel(fig.add_subplot(grid[4, 4]), "중첩 범례·카메라", "Overlay legend & camera receipt", comparison_lines, font)

    fig.text(0.5, 0.018, "첫 행 주황선: 평가 전용 reference LoD2 RoofSurface exterior boundary · 학습/조립/채점 입력 아님", ha="center", va="center", fontsize=7.5, color=palette["charcoal"], fontproperties=font)
    path = staging / config["outputs"]["panel"]
    fig.savefig(path, dpi=int(visual["panel_dpi"]), facecolor="white", metadata={"Software": "JointBuildGS A-prime panel v7 reference roof boundary"})
    v4.plt.close(fig)
    quality = base.png_stats(path, visual["minimum_panel_pixels"])
    comparison_receipt = {key: value for key, value in comparison.items() if key not in {"output_xyz", "reference_xyz"}}
    render = {
        "layout": "5_rows_x_5_columns_single_png",
        "row_order": visual["row_order"],
        "column_order": visual["column_order"],
        "frame": frame,
        "input_reference_roof_overlay": {
            "role": "evaluation_only_post_hoc_visual_locator",
            "primary_image": selection["primary_image"],
            "selection": selection,
            "reference_roof": roof,
            "coordinate_contract": view["coordinate_contract"],
            "medium_crop_box_xyxy": list(primary["medium_crop_box"]),
            "tight_crop_box_xyxy": list(primary["tight_crop_box"]),
            "overlay_layers": ["evaluation_only_reference_LoD2_RoofSurface_exterior_boundary_lines"],
            "visibility_policy": "only line samples inside the 2px-dilated exact first-hit target RoofSurface mask are drawn",
            "visible_target_roof_pixels_n": primary["visible_target_roof_pixels_n"],
            "visible_boundary_samples_n": primary["visible_boundary_samples_n"],
            "boundary_samples_n": primary["boundary_samples_n"],
            "filled_regions": 0,
            "points": 0,
            "first_row_exclusions": view["first_row_exclusions"],
            "used_for_training_supervision_readout_assembly_or_scoring": False,
        },
        "seed_points_displayed_per_view": rendered_seed_points,
        "mesh_topology": topology,
        "mesh_faces_displayed_per_view": rendered_faces,
        "cityjson": evidence["cityjson_surface_stats"],
        "cityjson_render": cityjson_render,
        "output_reference_comparison": comparison_receipt,
        "visual_backfill": {
            "version": "v7",
            "scope": "post_hoc_qualitative_visual_only",
            "training_readout_assembly_score_changed": False,
            "historical_v4_v5_v6_unchanged": True,
        },
    }
    return quality, render, font_record


def source_snapshot(evidence: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    return {role: base.verify_record(record, role) for role, record in evidence["source_records"].items()}


def output_record(path: Path, destination: Path | None = None) -> dict[str, Any]:
    record = base.file_record(path)
    if destination is not None:
        record["path"] = base.display_path(destination / path.name)
    return record


def verify_bundle(
    config: Mapping[str, Any],
    base_config: Mapping[str, Any],
    building_id: str,
    arm: str,
    replicate: str,
    output_root: Path | None = None,
) -> dict[str, Any]:
    validate_identity(config, base_config, building_id, arm, replicate)
    root = output_job_dir(config, building_id, arm, replicate, output_root)
    receipt = base.load_json(root / config["outputs"]["complete"])
    require(receipt.get("schema") == RECEIPT_SCHEMA, "v7 receipt schema drift")
    require(receipt.get("state") == "COMPLETE", "v7 receipt is not COMPLETE")
    require(receipt.get("measurement_state") == "MEASURED_REUSED_VISUAL_BACKFILL", "v7 measurement state drift")
    require(receipt.get("identity") == {"run_id": config["run_id"], "building_id": building_id, "arm": arm, "replicate": replicate}, "v7 receipt identity drift")
    require(receipt.get("scientific_verdict") is None and receipt.get("interpretation") is None, "v7 receipt contains a verdict")
    require(receipt.get("implementation") == implementation_records(config), "v7 implementation hash drift")
    current_sources = {role: base.verify_record(record, f"v7 receipt source {role}") for role, record in receipt.get("source_records", {}).items()}
    require(current_sources == receipt["source_records"], "v7 source record drift")
    current_readout = base.file_record(base.resolve_readout_complete(base_config, building_id, arm, replicate))
    require(receipt.get("source_readout_complete") == current_readout, "v7 source readout is not canonical")
    require({path.name for path in root.iterdir()} == {"panel.png", "complete.json"}, "v7 bundle file set drift")
    require(receipt["outputs"]["panel"] == output_record(root / "panel.png"), "v7 panel output drift")
    base.png_stats(root / "panel.png", config["visual_contract"]["minimum_panel_pixels"])
    overlay = receipt["panel_contract"]["render"]["input_reference_roof_overlay"]
    require(overlay["overlay_layers"] == ["evaluation_only_reference_LoD2_RoofSurface_exterior_boundary_lines"], "v7 first-row overlay layer drift")
    require(overlay["filled_regions"] == 0 and overlay["points"] == 0, "v7 first row is not boundary-only")
    exclusions = set(overlay["first_row_exclusions"])
    require({"ALS seed points", "class6 TIN points", "class6 TIN boundary", "M_j mask", "Roofer output"}.issubset(exclusions), "v7 first-row exclusions drift")
    require(overlay["used_for_training_supervision_readout_assembly_or_scoring"] is False, "reference leaked into experiment")
    require(overlay["coordinate_contract"]["observed_corrected_images_sha256"] == config["first_row_reference_contract"]["coordinate_contract"]["adopted_corrected_images_sha256"], "v7 observed pose hash drift")
    require(overlay["coordinate_contract"]["additional_transform_application_count"] == 0, "v7 additional transform drift")
    require(receipt["publication"]["gpu_devices_used"] == [], "v7 receipt bound a GPU")
    require(receipt["publication"]["receipt_written_last"] is True, "v7 receipt-last flag absent")
    return receipt


def publish_job(
    config: Mapping[str, Any],
    base_config: Mapping[str, Any],
    report: Any,
    building_id: str,
    arm: str,
    replicate: str,
    output_root: Path | None = None,
) -> dict[str, Any]:
    validate_identity(config, base_config, building_id, arm, replicate)
    destination = output_job_dir(config, building_id, arm, replicate, output_root)
    receipt_path = destination / config["outputs"]["complete"]
    if receipt_path.is_file():
        return verify_bundle(config, base_config, building_id, arm, replicate, output_root)
    require(not destination.exists(), f"refusing incomplete/nonempty v7 bundle: {base.display_path(destination)}")

    implementation_before = implementation_records(config)
    evidence = base.resolve_evidence(base_config, report, building_id, arm, replicate)
    evidence = augment_evidence(evidence, config)
    evidence["base_config"] = base_config
    sources_before = source_snapshot(evidence)
    references_before = [base.verify_large_locked_record(record, f"reference_gml[{index}]") for index, record in enumerate(base_config["locked_inputs"]["reference_gml"])]
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{replicate}.panel-v7-reference-roof-staging-", dir=destination.parent))
    try:
        quality, render, font_record = render_panel(staging, config, evidence)
        require(source_snapshot(evidence) == sources_before, "source inputs changed during v7 render")
        require(implementation_records(config) == implementation_before, "v7 implementation changed during render")
        score = v4.score_row(evidence)
        receipt = {
            "schema": RECEIPT_SCHEMA,
            "task_id": config["task_id"],
            "state": "COMPLETE",
            "measurement_state": "MEASURED_REUSED_VISUAL_BACKFILL",
            "created_at": v4.utc_now(),
            "identity": evidence["identity"],
            "backfill_contract": config["backfill_contract"],
            "resolver_disclosure": config["resolver_disclosure"],
            "source_readout_complete": evidence["source_readout_complete"],
            "source_records": sources_before,
            "reference_gml": {
                "role": "evaluation_only_after_output_freeze",
                "records": references_before,
                "used_for_post_hoc_photo_selection_crop_and_boundary_overlay": True,
                "used_for_training_supervision_readout_assembly_or_scoring": False,
                "used_for_3d_view_orientation": False,
                "shared_bounds_influence_for_geometry_rows_only": True,
            },
            "panel_contract": {"single_visual_file": True, "visual_filename": config["outputs"]["panel"], "placeholders": 0, "render": render},
            "render_quality": quality,
            "font": font_record,
            "primary_measurements_reused": evidence["readout"]["primary"]["measurements"],
            "p0prime_deltas_reused": {
                "delta_roof_rms_vs_p0_refl_m": score.get("delta_roof_rms_vs_p0_refl_m"),
                "delta_roof_completeness_vs_p0_refl": score.get("delta_roof_completeness_vs_p0_refl"),
                "delta_face_count_ratio_vs_p0_refl": score.get("delta_face_count_ratio_vs_p0_refl"),
            },
            "citygml_export_reused": evidence["serialization_capability"],
            "implementation": implementation_before,
            "outputs": {"panel": output_record(staging / config["outputs"]["panel"], destination)},
            "publication": {
                "visual_backfill_only": True,
                "one_visual_panel_per_job": True,
                "job_directory_atomic_publish": True,
                "overwrite_allowed": False,
                "historical_v4_v5_v6_unchanged": True,
                "unrelated_queue_allowed": True,
                "gpu_devices_used": [],
                "output_namespace_isolated_from_training": True,
                "source_inputs_rehashed_after_render": True,
                "source_inputs_unchanged": True,
                "receipt_written_last": True,
            },
            "scientific_verdict": None,
            "interpretation": None,
        }
        base.write_json_exclusive(staging / config["outputs"]["complete"], receipt)
        os.replace(staging, destination)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return verify_bundle(config, base_config, building_id, arm, replicate, output_root)


def check_job(
    config: Mapping[str, Any],
    base_config: Mapping[str, Any],
    report: Any,
    building_id: str,
    arm: str,
    replicate: str,
) -> dict[str, Any]:
    validate_identity(config, base_config, building_id, arm, replicate)
    evidence = augment_evidence(base.resolve_evidence(base_config, report, building_id, arm, replicate), config)
    view = evidence["image_mask"]
    return {
        "state": "READY",
        "identity": evidence["identity"],
        "scope": "post_hoc_qualitative_visual_only",
        "primary_image": view["selection"]["primary_image"],
        "reference_roof": view["reference_roof"],
        "selection": view["selection"],
        "coordinate_contract": view["coordinate_contract"],
        "first_row_overlay_layers": ["evaluation_only_reference_LoD2_RoofSurface_exterior_boundary_lines"],
        "first_row_points": 0,
        "first_row_filled_regions": 0,
        "training_readout_assembly_score_changed": False,
        "scientific_verdict": None,
        "interpretation": None,
    }


def _identity_for_building(config: Mapping[str, Any], building_id: str) -> tuple[str, str, str]:
    matches = [identity for identity in allowed_identities(config) if identity[0] == building_id]
    require(len(matches) == 1, f"building is outside v7 scope: {building_id}")
    return matches[0]


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    result.add_argument("--output-root", type=Path)
    result.add_argument("command", choices=("check-one", "backfill-one", "verify-one", "check-all", "backfill-all", "verify-all"))
    result.add_argument("building_id", nargs="?")
    return result


def main(argv: Sequence[str] | None = None) -> int:
    args = parser().parse_args(argv)
    config, base_config = load_config(args.config)
    report = base.load_report_module(base_config)
    if args.command.endswith("-one"):
        require(args.building_id is not None, f"{args.command} requires building_id")
        identities = [_identity_for_building(config, args.building_id)]
    else:
        require(args.building_id is None, f"{args.command} does not accept building_id")
        identities = allowed_identities(config)

    results: list[dict[str, Any]] = []
    for identity in identities:
        if args.command.startswith("check"):
            payload = check_job(config, base_config, report, *identity)
        elif args.command.startswith("backfill"):
            payload = publish_job(config, base_config, report, *identity, output_root=args.output_root)
        else:
            payload = verify_bundle(config, base_config, *identity, output_root=args.output_root)
        results.append(payload)
    output: Any = results[0] if len(results) == 1 else {
        "state": "COMPLETE",
        "jobs_n": len(results),
        "identities": [payload["identity"] for payload in results],
        "scientific_verdict": None,
        "interpretation": None,
    }
    print(json.dumps(output, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (PanelError, image_projection.ProjectionError) as exc:
        print(f"[FAILED] {type(exc).__name__}: {exc}", file=sys.stderr)
        raise SystemExit(2)
