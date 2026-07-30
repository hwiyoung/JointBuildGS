#!/usr/bin/env python3
"""Publish dense qualitative v3 with a reference-LoD2-only photo locator.

The nine-building population sample is frozen by the v2 input-only selector
before any reference GML is opened.  After that freeze, the evaluation-only
reference LoD2 ``RoofSurface`` exterior rings are projected with the adopted
COLMAP poses and the explicit orthometric datum.  The first row contains only
those boundary lines over camera-bound pixels: no footprint, fill, DIM points,
or class-6 TIN boundary.  Rows 2--4 retain the v2 meanings.

This is a qualitative publication only.  It starts no learning run and emits
no scientific verdict.
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
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib")
os.environ.setdefault("XDG_CACHE_HOME", "/tmp/cache")

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import patheffects
from matplotlib.backends.backend_pdf import PdfPages
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


BASE = _load_module(
    SCRIPT_DIR / "fusion_w1_dense_baseline_qualitative_v2_20260728.py",
    "dense_baseline_qualitative_v2_base_for_v3",
)

DEFAULT_CONFIG = (
    REPO
    / "phases/p2-gsjso/configs/fusion_w1/fusion_w1_dense_baseline_qualitative_v3_20260728.json"
)
CONFIG_SCHEMA = "jointbuildgs.fusion_w1.dense_baseline_qualitative.config.v3"
MANIFEST_SCHEMA = "jointbuildgs.fusion_w1.dense_baseline_qualitative.manifest.v3"
EXPECTED_SELECTED = (
    "DEBY_LOD2_4908178",
    "DEBY_LOD2_104583447",
    "DEBY_LOD2_4959753",
    "DEBY_LOD2_60097",
    "DEBY_LOD2_4907023",
    "DEBY_LOD2_4908353",
    "DEBY_LOD2_4907207",
    "DEBY_LOD2_4959461",
    "DEBY_LOD2_60042",
)


class DenseBaselineV3Error(BASE.DenseBaselineError):
    """A v3 source, overlay, or publication invariant failed."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise DenseBaselineV3Error(message)


def load_config(path: Path = DEFAULT_CONFIG, *, verify_sources: bool = True) -> dict[str, Any]:
    v3 = BASE.read_json(path)
    require(v3.get("schema") == CONFIG_SCHEMA, "v3 config schema drift")
    require(v3.get("branch") == "exp/fusion-w1", "branch contract drift")
    base_spec = v3.get("base_config") or {}
    base_path = BASE.repo_path(str(base_spec.get("path", "")))
    require(base_path.is_file(), "v3 base config absent")
    if verify_sources:
        require(
            BASE.sha256_file(base_path) == base_spec.get("sha256"),
            "v3 base config hash drift",
        )
    config = copy.deepcopy(BASE.load_config(base_path, verify_sources=verify_sources))
    config["schema"] = CONFIG_SCHEMA
    config["task_id"] = v3["task_id"]
    config["run_id"] = v3["run_id"]
    config["purpose"] = v3["purpose"]
    config["base_config"] = base_spec
    config["implementation_files"] = list(v3["implementation_files"])
    config["sample_freeze"] = copy.deepcopy(v3["sample_freeze"])
    config["photo_projection_contract"] = copy.deepcopy(v3["photo_projection_contract"])
    config["visual_overrides"] = copy.deepcopy(v3["visual_overrides"])
    config["outputs"] = copy.deepcopy(v3["outputs"])
    config["publication"] = copy.deepcopy(v3["publication"])
    config["visual_contract"]["row_order"][0] = v3["visual_overrides"]["row_1"]
    config["selection_contract"]["representative_photo_binding"] = (
        "after the input-only nine-building sample is frozen: project only evaluation-only "
        "reference LoD2 RoofSurface exterior boundaries; require every boundary vertex "
        "inside a fixed image margin; rank by area, centrality, nadir, then image name"
    )

    expected_implementation = [
        "phases/p2-gsjso/configs/fusion_w1/fusion_w1_dense_baseline_qualitative_v3_20260728.json",
        "phases/p2-gsjso/scripts/fusion_w1/fusion_w1_dense_baseline_qualitative_v3_20260728.py",
        "phases/p2-gsjso/scripts/fusion_w1/run_fusion_w1_dense_baseline_qualitative_v3_20260728.sh",
        "tests/fusion_w1/test_fusion_w1_dense_baseline_qualitative_v3_20260728.py",
        "phases/p2-gsjso/configs/fusion_w1/fusion_w1_dense_baseline_qualitative_v2_20260728.json",
        "phases/p2-gsjso/scripts/fusion_w1/fusion_w1_dense_baseline_qualitative_v2_20260728.py",
        "scripts/e5_c001/e5_c001_8way.py",
        "phases/p2-gsjso/scripts/fusion_w1/fusion_w1_aprime_job_panel_v4_20260727.py",
        "src/artifact_paths.py",
        "src/stage2/image_projection.py",
    ]
    require(config["implementation_files"] == expected_implementation, "v3 implementation closure drift")
    for value in expected_implementation:
        require(BASE.repo_path(value).is_file(), f"v3 implementation absent: {value}")

    freeze = config["sample_freeze"]
    require(tuple(freeze["selected_building_ids"]) == EXPECTED_SELECTED, "sample freeze drift")
    require(
        BASE.set_sha256(freeze["selected_building_ids"]) == freeze["selected_set_sha256"],
        "sample freeze SHA drift",
    )
    contract = config["photo_projection_contract"]
    require(contract["input_vertical_datum"] == BASE.ORTHOMETRIC, "photo datum drift")
    require(int(contract["additional_pose_transform_application_count"]) == 0, "pose reapplication drift")
    for key in (
        "dense_point_overlay_forbidden",
        "dense_tin_boundary_overlay_forbidden",
        "footprint_overlay_forbidden",
        "filled_polygon_overlay_forbidden",
        "interior_ring_overlay_forbidden",
    ):
        require(contract.get(key) is True, f"photo overlay prohibition absent: {key}")
    margin = float(contract["minimum_frame_margin_fraction"])
    require(0.0 < margin < 0.25, "photo frame margin is invalid")
    visibility = contract.get("visibility_gate") or {}
    require(
        visibility.get("raycast_engine")
        == "deterministic chunked NumPy Moller-Trumbore first-intersection test",
        "photo visibility raycast engine drift",
    )
    require(int(visibility.get("maximum_target_samples", 0)) >= 16, "visibility sample budget too small")
    require(int(visibility.get("minimum_visible_samples", 0)) >= 1, "visible sample minimum absent")
    require(0.0 < float(visibility.get("minimum_visible_fraction", 0.0)) <= 1.0, "visible fraction invalid")
    require(float(visibility.get("occlusion_epsilon_m", 0.0)) > 0.0, "occlusion epsilon invalid")
    require(float(visibility.get("surrounding_scene_aoi_margin_m", 0.0)) >= 50.0, "scene AOI too small")
    require(
        contract.get("eligibility_tiers")
        == [
            "tier_1_all_boundary_vertices_inside_5_percent_margin_and_target_roof_raycast_visible",
            "tier_2_fallback_all_boundary_vertices_inside_full_frame_and_target_roof_raycast_visible",
        ],
        "photo eligibility tier drift",
    )
    require("never substitute an occluded view" in contract.get("slot_policy", ""), "occluded slot fill enabled")
    require(config["publication"]["reference_role"] == "evaluation_only", "reference role drift")
    require(config["publication"]["learning_runs_started"] == 0, "learning count drift")
    require(config["publication"]["scientific_verdict"] is None, "scientific verdict must be null")
    return config


def _closed_ring(ring: np.ndarray) -> np.ndarray:
    values = np.asarray(ring, dtype=np.float64)
    require(values.ndim == 2 and values.shape[1] >= 3 and len(values) >= 3, "reference ring malformed")
    values = values[:, :3]
    require(np.all(np.isfinite(values)), "reference ring contains non-finite coordinates")
    if not np.allclose(values[0], values[-1], rtol=0.0, atol=1.0e-9):
        values = np.vstack((values, values[0]))
    require(len(values) >= 4, "closed reference ring has fewer than four vertices")
    return values


@dataclass(frozen=True)
class LoD2RaycastScene:
    """Triangulated surrounding reference LoD2 semantic surfaces in base XYZ."""

    triangles_xyz: np.ndarray
    building_ids: np.ndarray
    semantic_types: np.ndarray
    source_records: tuple[dict[str, Any], ...]
    stats: Mapping[str, Any]


def _local_name(tag: str) -> str:
    return str(tag).rsplit("}", 1)[-1]


def _element_id(element: ET.Element) -> str:
    return next(
        (str(value) for key, value in element.attrib.items() if _local_name(key) == "id"),
        "",
    )


def _poslist_ring(element: ET.Element) -> np.ndarray | None:
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
        if len(values) % dimension:
            continue
        points = values.reshape(-1, dimension)
        if dimension == 2:
            points = np.column_stack((points, np.zeros(len(points), dtype=np.float64)))
        if len(points) >= 3:
            return _closed_ring(points[:, :3])
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
    return _closed_ring(np.asarray(positions, dtype=np.float64)) if len(positions) >= 3 else None


def _point_in_triangle_2d(point: np.ndarray, first: np.ndarray, second: np.ndarray, third: np.ndarray) -> bool:
    denominator = (
        (second[1] - third[1]) * (first[0] - third[0])
        + (third[0] - second[0]) * (first[1] - third[1])
    )
    if abs(float(denominator)) < 1.0e-18:
        return False
    s = (
        (second[1] - third[1]) * (point[0] - third[0])
        + (third[0] - second[0]) * (point[1] - third[1])
    ) / denominator
    t = (
        (third[1] - first[1]) * (point[0] - third[0])
        + (first[0] - third[0]) * (point[1] - third[1])
    ) / denominator
    return bool(s >= -1.0e-9 and t >= -1.0e-9 and s + t <= 1.0 + 1.0e-9)


def _earclip_indices(polygon: np.ndarray) -> list[tuple[int, int, int]]:
    values = np.asarray(polygon, dtype=np.float64)
    if len(values) < 3:
        return []
    area = 0.5 * float(
        np.sum(
            values[:, 0] * np.roll(values[:, 1], -1)
            - np.roll(values[:, 0], -1) * values[:, 1]
        )
    )
    indices = list(range(len(values)))
    if area < 0.0:
        indices.reverse()
    triangles: list[tuple[int, int, int]] = []
    guard = 0
    while len(indices) > 3 and guard < 100000:
        guard += 1
        ear_found = False
        for index in range(len(indices)):
            first_i = indices[(index - 1) % len(indices)]
            middle_i = indices[index]
            last_i = indices[(index + 1) % len(indices)]
            first, middle, last = values[first_i], values[middle_i], values[last_i]
            cross = (
                (middle[0] - first[0]) * (last[1] - first[1])
                - (middle[1] - first[1]) * (last[0] - first[0])
            )
            if cross <= 1.0e-12:
                continue
            if any(
                _point_in_triangle_2d(values[other], first, middle, last)
                for other in indices
                if other not in {first_i, middle_i, last_i}
            ):
                continue
            triangles.append((first_i, middle_i, last_i))
            del indices[index]
            ear_found = True
            break
        if not ear_found:
            break
    if len(indices) == 3:
        triangles.append((indices[0], indices[1], indices[2]))
    elif len(indices) > 3:
        triangles.extend(
            (indices[0], indices[index], indices[index + 1])
            for index in range(1, len(indices) - 1)
        )
    return triangles


def _triangulate_ring_xyz(ring: np.ndarray) -> list[np.ndarray]:
    values = _closed_ring(ring)[:-1]
    normal = np.zeros(3, dtype=np.float64)
    for index, current in enumerate(values):
        following = values[(index + 1) % len(values)]
        normal[0] += (current[1] - following[1]) * (current[2] + following[2])
        normal[1] += (current[2] - following[2]) * (current[0] + following[0])
        normal[2] += (current[0] - following[0]) * (current[1] + following[1])
    drop_axis = int(np.argmax(np.abs(normal)))
    keep_axes = [axis for axis in range(3) if axis != drop_axis]
    output = [values[np.asarray(indices, dtype=np.int64)] for indices in _earclip_indices(values[:, keep_axes])]
    return [triangle for triangle in output if np.linalg.norm(np.cross(triangle[1] - triangle[0], triangle[2] - triangle[0])) > 1.0e-10]


def _target_aoi_boxes(
    reference_rings_by_id: Mapping[str, Sequence[np.ndarray]], margin_m: float
) -> dict[str, np.ndarray]:
    output: dict[str, np.ndarray] = {}
    for building_id, rings in reference_rings_by_id.items():
        values = np.vstack([_closed_ring(ring)[:-1, :2] for ring in rings])
        output[building_id] = np.asarray(
            [
                float(values[:, 0].min() - margin_m),
                float(values[:, 1].min() - margin_m),
                float(values[:, 0].max() + margin_m),
                float(values[:, 1].max() + margin_m),
            ],
            dtype=np.float64,
        )
    return output


def _bbox_intersects_any(values_xy: np.ndarray, boxes: Iterable[np.ndarray]) -> bool:
    lower = np.min(values_xy, axis=0)
    upper = np.max(values_xy, axis=0)
    return any(
        upper[0] >= box[0]
        and lower[0] <= box[2]
        and upper[1] >= box[1]
        and lower[1] <= box[3]
        for box in boxes
    )


def build_surrounding_lod2_scene(
    reference_paths: Sequence[Path],
    reference_rings_by_id: Mapping[str, Sequence[np.ndarray]],
    config: Mapping[str, Any],
) -> LoD2RaycastScene:
    """Stream all semantic LoD2 surfaces, retaining surrounding target AOIs."""
    visibility = config["photo_projection_contract"]["visibility_gate"]
    boxes = _target_aoi_boxes(
        reference_rings_by_id,
        float(visibility["surrounding_scene_aoi_margin_m"]),
    )
    semantic_names = {"RoofSurface", "WallSurface", "GroundSurface"}
    triangles: list[np.ndarray] = []
    owners: list[str] = []
    semantics: list[str] = []
    retained_buildings: set[str] = set()
    rings_by_semantic = {name: 0 for name in semantic_names}
    buildings_scanned = 0
    degenerate_rings = 0
    for path in reference_paths:
        try:
            for _event, building in ET.iterparse(path, events=("end",)):
                if _local_name(building.tag) != "Building":
                    continue
                buildings_scanned += 1
                building_id = _element_id(building)
                surface_rings: list[tuple[str, np.ndarray]] = []
                for surface in building.iter():
                    semantic = _local_name(surface.tag)
                    if semantic not in semantic_names:
                        continue
                    for polygon in surface.iter():
                        if _local_name(polygon.tag) != "Polygon":
                            continue
                        exteriors = [
                            child for child in polygon.iter() if _local_name(child.tag) == "exterior"
                        ]
                        if len(exteriors) != 1:
                            continue
                        ring = _poslist_ring(exteriors[0])
                        if ring is not None:
                            surface_rings.append((semantic, ring))
                if surface_rings and _bbox_intersects_any(
                    np.vstack([ring[:-1, :2] for _semantic, ring in surface_rings]),
                    boxes.values(),
                ):
                    retained_buildings.add(building_id)
                    for semantic, ring in surface_rings:
                        ring_triangles = _triangulate_ring_xyz(ring)
                        if not ring_triangles:
                            degenerate_rings += 1
                            continue
                        for triangle in ring_triangles:
                            triangles.append(triangle)
                            owners.append(building_id)
                            semantics.append(semantic)
                        rings_by_semantic[semantic] += 1
                building.clear()
        except (OSError, ET.ParseError) as exc:
            raise DenseBaselineV3Error(f"cannot parse surrounding LoD2 scene {path}: {exc}") from exc
    require(bool(triangles), "surrounding LoD2 raycast scene is empty")
    triangle_array = np.asarray(triangles, dtype=np.float64)
    require(triangle_array.ndim == 3 and triangle_array.shape[1:] == (3, 3), "scene triangles malformed")
    missing_targets = sorted(set(reference_rings_by_id) - set(owners))
    require(not missing_targets, f"frozen targets absent from surrounding LoD2 mesh: {missing_targets}")
    return LoD2RaycastScene(
        triangles_xyz=triangle_array,
        building_ids=np.asarray(owners, dtype=object),
        semantic_types=np.asarray(semantics, dtype=object),
        source_records=tuple(BASE.file_record(path) for path in reference_paths),
        stats={
            "buildings_scanned": buildings_scanned,
            "buildings_retained_in_surrounding_AOIs": len(retained_buildings),
            "triangles_n": int(len(triangle_array)),
            "rings_by_semantic": {key: int(value) for key, value in sorted(rings_by_semantic.items())},
            "degenerate_rings_skipped": int(degenerate_rings),
            "target_AOI_boxes_xy": {key: value.tolist() for key, value in sorted(boxes.items())},
            "surrounding_scene_aoi_margin_m": float(visibility["surrounding_scene_aoi_margin_m"]),
            "coordinate_frame": "EPSG:25832 orthometric base XYZ",
        },
    )


def _target_visibility_samples(
    reference_rings: Sequence[np.ndarray], maximum_samples: int
) -> np.ndarray:
    triangles = [
        triangle
        for ring in reference_rings
        for triangle in _triangulate_ring_xyz(ring)
    ]
    require(bool(triangles), "target reference RoofSurface triangulation is empty")
    barycentric = np.asarray(
        [[1.0 / 3.0, 1.0 / 3.0, 1.0 / 3.0], [0.60, 0.20, 0.20], [0.20, 0.60, 0.20], [0.20, 0.20, 0.60]],
        dtype=np.float64,
    )
    samples = np.vstack(
        [weights @ np.asarray(triangle, dtype=np.float64) for triangle in triangles for weights in barycentric]
    )
    if len(samples) > maximum_samples:
        indices = np.linspace(0, len(samples) - 1, maximum_samples, dtype=np.int64)
        samples = samples[indices]
    require(len(samples) >= 1 and np.all(np.isfinite(samples)), "target visibility samples invalid")
    return samples


def _nearest_intersection_distances(
    origin: np.ndarray,
    directions: np.ndarray,
    triangles: np.ndarray,
    chunk_size: int,
) -> np.ndarray:
    """Chunked vectorized Moller-Trumbore nearest-hit distance per unit ray."""
    origin = np.asarray(origin, dtype=np.float64)
    directions = np.asarray(directions, dtype=np.float64)
    triangles = np.asarray(triangles, dtype=np.float64)
    require(origin.shape == (3,), "ray origin malformed")
    require(directions.ndim == 2 and directions.shape[1] == 3, "ray directions malformed")
    require(triangles.ndim == 3 and triangles.shape[1:] == (3, 3), "ray triangles malformed")
    nearest = np.full(len(directions), np.inf, dtype=np.float64)
    for start in range(0, len(triangles), chunk_size):
        chunk = triangles[start : start + chunk_size]
        first = chunk[:, 0]
        edge_1 = chunk[:, 1] - first
        edge_2 = chunk[:, 2] - first
        h = np.cross(directions[:, None, :], edge_2[None, :, :])
        determinant = np.einsum("tj,rtj->rt", edge_1, h)
        parallel = np.abs(determinant) <= 1.0e-10
        inverse = np.zeros_like(determinant)
        inverse[~parallel] = 1.0 / determinant[~parallel]
        s = origin[None, :] - first
        u = inverse * np.einsum("tj,rtj->rt", s, h)
        q = np.cross(s, edge_1)
        v = inverse * np.einsum("rj,tj->rt", directions, q)
        t_numerator = np.einsum("tj,tj->t", edge_2, q)
        distance = inverse * t_numerator[None, :]
        hits = (
            ~parallel
            & (u >= -1.0e-9)
            & (v >= -1.0e-9)
            & (u + v <= 1.0 + 1.0e-9)
            & (distance > 1.0e-7)
        )
        distance[~hits] = np.inf
        nearest = np.minimum(nearest, np.min(distance, axis=1))
    return nearest


def raycast_target_roof_visibility(
    building_id: str,
    reference_rings: Sequence[np.ndarray],
    view: Any,
    scene_reference: Mapping[str, Any],
    scene: LoD2RaycastScene,
    config: Mapping[str, Any],
) -> dict[str, Any]:
    visibility = config["photo_projection_contract"]["visibility_gate"]
    samples = _target_visibility_samples(reference_rings, int(visibility["maximum_target_samples"]))
    datum, geoid_m, datum_path = BASE.projection_parameters(config)
    camera_base = canonical_to_base(
        np.asarray(view.center_canonical, dtype=np.float64).reshape(1, 3),
        scene_reference,
        output_datum=datum,
        geoid_m=geoid_m,
        config_path=datum_path,
    )[0]
    target_values = np.vstack([_closed_ring(ring)[:-1] for ring in reference_rings])
    margin = float(visibility["surrounding_scene_aoi_margin_m"])
    lower = np.min(target_values[:, :2], axis=0) - margin
    upper = np.max(target_values[:, :2], axis=0) + margin
    triangle_lower = np.min(scene.triangles_xyz[:, :, :2], axis=1)
    triangle_upper = np.max(scene.triangles_xyz[:, :, :2], axis=1)
    local_mask = (
        (triangle_upper[:, 0] >= lower[0])
        & (triangle_lower[:, 0] <= upper[0])
        & (triangle_upper[:, 1] >= lower[1])
        & (triangle_lower[:, 1] <= upper[1])
    )
    local_triangles = scene.triangles_xyz[local_mask]
    require(len(local_triangles) > 0, f"local LoD2 visibility mesh empty: {building_id}")
    vectors = samples - camera_base[None, :]
    target_distances = np.linalg.norm(vectors, axis=1)
    require(np.all(target_distances > 1.0), f"camera lies on target roof samples: {building_id}")
    directions = vectors / target_distances[:, None]
    nearest = _nearest_intersection_distances(
        camera_base,
        directions,
        local_triangles,
        int(visibility["triangle_chunk_size"]),
    )
    epsilon = float(visibility["occlusion_epsilon_m"])
    visible = nearest >= target_distances - epsilon
    visible_n = int(np.count_nonzero(visible))
    visible_fraction = float(np.mean(visible))
    passes = (
        visible_n >= int(visibility["minimum_visible_samples"])
        and visible_fraction >= float(visibility["minimum_visible_fraction"])
    )
    return {
        "passes_target_roof_visibility_gate": bool(passes),
        "target_samples_n": int(len(samples)),
        "visible_target_samples_n": visible_n,
        "visible_target_fraction": visible_fraction,
        "occluded_target_samples_n": int(len(samples) - visible_n),
        "local_scene_triangles_n": int(len(local_triangles)),
        "occlusion_epsilon_m": epsilon,
        "raycast_engine": visibility["raycast_engine"],
        "reference_role": visibility["reference_role"],
    }


def project_reference_roof_boundaries(
    reference_rings: Sequence[np.ndarray],
    view: Any,
    scene_reference: Mapping[str, Any],
    config: Mapping[str, Any],
) -> tuple[list[np.ndarray], dict[str, Any]]:
    """Project reference RoofSurface exterior rings without synthetic geometry."""
    require(bool(reference_rings), "reference RoofSurface exterior rings absent")
    datum, geoid_m, datum_path = BASE.projection_parameters(config)
    uv_rings: list[np.ndarray] = []
    valid_rings: list[np.ndarray] = []
    for ring in reference_rings:
        xyz = _closed_ring(ring)
        result = BASE.project_base_points(
            xyz,
            view.pose,
            view.camera,
            scene_reference,
            input_datum=datum,
            geoid_m=geoid_m,
            config_path=datum_path,
        )
        uv_rings.append(np.asarray(result.uv, dtype=np.float64))
        valid_rings.append(np.asarray(result.valid, dtype=bool))
    all_uv = np.vstack(uv_rings)
    all_valid = np.concatenate(valid_rings)
    width, height = int(view.camera.width), int(view.camera.height)
    margin_fraction = float(config["photo_projection_contract"]["minimum_frame_margin_fraction"])
    margin_x = width * margin_fraction
    margin_y = height * margin_fraction
    inside_frame = (
        all_valid
        & (all_uv[:, 0] >= 0.0)
        & (all_uv[:, 0] < width)
        & (all_uv[:, 1] >= 0.0)
        & (all_uv[:, 1] < height)
    )
    inside_margin = (
        all_valid
        & (all_uv[:, 0] >= margin_x)
        & (all_uv[:, 0] <= width - margin_x)
        & (all_uv[:, 1] >= margin_y)
        & (all_uv[:, 1] <= height - margin_y)
    )
    frame_center = np.asarray([width / 2.0, height / 2.0], dtype=np.float64)
    frame_scale = float(np.hypot(width / 2.0, height / 2.0))
    finite_uv = all_uv[np.all(np.isfinite(all_uv), axis=1)]
    if len(finite_uv):
        lower = finite_uv.min(axis=0)
        upper = finite_uv.max(axis=0)
        bbox_area = float(np.prod(np.maximum(upper - lower, 0.0)))
        polygon_area = float(
            sum(
                BASE.polygon_area_uv(values[:-1])
                for values in uv_rings
                if np.all(np.isfinite(values))
            )
        )
        center = (lower + upper) / 2.0
        frame_center_radius = float(np.linalg.norm(center - frame_center) / frame_scale)
    else:
        lower = np.asarray([math.nan, math.nan], dtype=np.float64)
        upper = np.asarray([math.nan, math.nan], dtype=np.float64)
        bbox_area = 0.0
        polygon_area = 0.0
        frame_center_radius = math.inf
    return uv_rings, {
        "all_vertices_valid": bool(np.all(all_valid)),
        "all_vertices_inside_full_frame": bool(np.all(inside_frame)),
        "all_vertices_inside_margin": bool(np.all(inside_margin)),
        "vertices_n": int(len(all_uv)),
        "rings_n": int(len(uv_rings)),
        "bbox_xyxy": [float(lower[0]), float(lower[1]), float(upper[0]), float(upper[1])],
        "bbox_area_px2": bbox_area,
        "bbox_area_fraction": bbox_area / float(width * height),
        "projected_polygon_area_px2": polygon_area,
        "frame_center_radius": frame_center_radius,
        "minimum_frame_margin_fraction": margin_fraction,
        "image_size": [width, height],
        "input_vertical_datum": datum,
        "geoid_m": geoid_m,
    }


def select_reference_photo_views(
    building_id: str,
    reference_rings: Sequence[np.ndarray],
    views_by_name: Mapping[str, Any],
    scene_reference: Mapping[str, Any],
    image_directory: Path,
    scene: LoD2RaycastScene,
    config: Mapping[str, Any],
) -> list[dict[str, Any]]:
    """Select three clear photo addresses after sample freeze using reference roof rings."""
    contract = config["photo_projection_contract"]
    datum, geoid_m, datum_path = BASE.projection_parameters(config)
    all_xyz = np.vstack([_closed_ring(ring)[:-1] for ring in reference_rings])
    target_base = np.median(all_xyz, axis=0).reshape(1, 3)
    target_canonical = BASE.base_to_canonical(
        target_base,
        scene_reference,
        input_datum=datum,
        geoid_m=geoid_m,
        config_path=datum_path,
    )[0]
    candidates: list[dict[str, Any]] = []
    for name in sorted(views_by_name):
        view = views_by_name[name]
        image_path = image_directory / name
        if not image_path.is_file():
            continue
        expected_size = (int(view.camera.width), int(view.camera.height))
        with Image.open(image_path) as source:
            observed_size = tuple(int(value) for value in source.size)
        require(
            observed_size == expected_size,
            f"COLMAP-bound image dimensions differ for {name}: image={observed_size}, camera={expected_size}",
        )
        _uv_rings, receipt = project_reference_roof_boundaries(
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
        visibility = raycast_target_roof_visibility(
            building_id,
            reference_rings,
            view,
            scene_reference,
            scene,
            config,
        )
        delta = np.asarray(view.center_canonical, dtype=np.float64) - target_canonical
        horizontal = float(np.linalg.norm(delta[:2]))
        vertical = abs(float(delta[2]))
        nadir = float(math.degrees(math.atan2(horizontal, max(vertical, 1.0e-9))))
        candidates.append(
            {
                "name": name,
                "projected_boundary_bbox_area_px2": area,
                "projected_boundary_bbox_area_fraction": float(receipt["bbox_area_fraction"]),
                "projected_boundary_polygon_area_px2": float(receipt["projected_polygon_area_px2"]),
                "frame_center_radius": float(receipt["frame_center_radius"]),
                "nadir_deg": nadir,
                "all_boundary_vertices_valid": True,
                "all_boundary_vertices_inside_full_frame": True,
                "all_boundary_vertices_inside_margin": bool(receipt["all_vertices_inside_margin"]),
                "minimum_frame_margin_fraction": float(receipt["minimum_frame_margin_fraction"]),
                "reference_roof_exterior_rings_n": int(receipt["rings_n"]),
                "reference_roof_boundary_vertices_n": int(receipt["vertices_n"]),
                "camera_bound_image_dimensions": list(observed_size),
                "visibility": visibility,
            }
        )
    require(bool(candidates), "no full-frame reference-boundary photo candidates")
    visible_candidates = [
        item
        for item in candidates
        if item["visibility"]["passes_target_roof_visibility_gate"]
    ]
    require(bool(visible_candidates), "no raycast-visible target-roof photo candidates")
    maximum_area = max(float(item["projected_boundary_bbox_area_px2"]) for item in visible_candidates)

    def rank(values: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
        return sorted(
            (dict(item) for item in values),
            key=lambda item: (
                -float(item["visibility"]["visible_target_fraction"]),
                float(item["frame_center_radius"]),
                -float(item["projected_boundary_bbox_area_px2"]),
                float(item["nadir_deg"]),
                str(item["name"]),
            ),
        )

    margin_ranked = rank(
        [item for item in visible_candidates if item["all_boundary_vertices_inside_margin"]]
    )
    frame_ranked = rank(
        [item for item in visible_candidates if not item["all_boundary_vertices_inside_margin"]]
    )
    selected: list[dict[str, Any]] = []
    for item in margin_ranked:
        item["eligibility_tier"] = "tier_1_full_margin"
        selected.append(item)
        if len(selected) == 3:
            break
    if len(selected) < 3:
        for item in frame_ranked:
            item["eligibility_tier"] = "tier_2_full_frame_fallback"
            selected.append(item)
            if len(selected) == 3:
                break
    require(bool(selected), "raycast visibility selection produced no photo")
    for index, item in enumerate(selected, start=1):
        item["selection_order"] = index
        item["candidate_count"] = len(candidates)
        item["maximum_projected_boundary_bbox_area_px2"] = maximum_area
        item["unique_visible_views_n"] = len(selected)
        item["visibility_eligible_candidate_count"] = len(visible_candidates)
        item["margin_visibility_eligible_candidate_count"] = len(margin_ranked)
        item["full_frame_fallback_visibility_eligible_candidate_count"] = len(frame_ranked)
        item["selection_method"] = (
            "post_sample_freeze_surrounding_LoD2_raycast_visibility_then_"
            "full_margin_to_full_frame_tiers_then_visibility_centrality_area_nadir"
        )
        item["reference_role"] = "evaluation_only"
        item["reference_geometry_used_for_population_or_sample_selection"] = False
        item["reference_geometry_used_for_postfreeze_photo_binding"] = True
        item["image_pixels_used_for_ranking"] = False
        item["overlay_primitives"] = ["reference_RoofSurface_exterior_boundary"]
    return selected


def photo_slot_plan(photo_views: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Fill three visual slots without ever adding an occluded unique view."""
    require(1 <= len(photo_views) <= 3, "unique visible photo count must be one to three")
    if len(photo_views) == 3:
        pairs = [(photo_views[0], "medium"), (photo_views[1], "medium"), (photo_views[2], "medium")]
    elif len(photo_views) == 2:
        pairs = [(photo_views[0], "medium"), (photo_views[1], "medium"), (photo_views[0], "tight")]
    else:
        pairs = [(photo_views[0], "full"), (photo_views[0], "medium"), (photo_views[0], "tight")]
    return [
        {
            "view": dict(view),
            "crop_profile": profile,
            "slot_order": index,
            "unique_visible_views_n": len(photo_views),
        }
        for index, (view, profile) in enumerate(pairs, start=1)
    ]


def projected_reference_photo_panel(
    ax: Any,
    image_path: Path,
    view: Any,
    scene_reference: Mapping[str, Any],
    reference_rings: Sequence[np.ndarray],
    config: Mapping[str, Any],
    font: Any,
    index: int,
    crop_profile: str,
) -> dict[str, Any]:
    uv_rings, projection = project_reference_roof_boundaries(
        reference_rings, view, scene_reference, config
    )
    require(projection["all_vertices_valid"], f"reference roof projection invalid in {image_path.name}")
    require(
        projection["all_vertices_inside_full_frame"],
        f"reference roof boundary leaves full image frame in {image_path.name}",
    )
    width, height = int(view.camera.width), int(view.camera.height)
    lower_x, lower_y, upper_x, upper_y = projection["bbox_xyxy"]
    profiles = config["photo_projection_contract"]["crop_profiles"]
    require(crop_profile in profiles, f"unknown photo crop profile: {crop_profile}")
    profile = profiles[crop_profile]
    if crop_profile == "full":
        box = (0, 0, width, height)
    else:
        span_x = max(1.0, upper_x - lower_x)
        span_y = max(1.0, upper_y - lower_y)
        center_x = 0.5 * (lower_x + upper_x)
        center_y = 0.5 * (lower_y + upper_y)
        padding = float(profile["padding_fraction"])
        desired_width = min(
            float(width),
            max(float(profile["minimum_width_pixels"]), span_x * (1.0 + 2.0 * padding)),
        )
        desired_height = min(
            float(height),
            max(float(profile["minimum_height_pixels"]), span_y * (1.0 + 2.0 * padding)),
        )
        x0 = int(math.floor(center_x - desired_width / 2.0))
        y0 = int(math.floor(center_y - desired_height / 2.0))
        x1 = int(math.ceil(center_x + desired_width / 2.0))
        y1 = int(math.ceil(center_y + desired_height / 2.0))
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
        box = (max(0, x0), max(0, y0), min(width, x1), min(height, y1))
    require(box[2] > box[0] and box[3] > box[1], "reference-boundary photo crop is empty")
    with Image.open(image_path) as source:
        image = source.convert("RGB")
        require(image.size == (width, height), f"camera/image dimensions differ for {image_path.name}")
        cropped = np.asarray(image.crop(box))
    ax.imshow(cropped)
    offset = np.asarray([box[0], box[1]], dtype=np.float64)
    visual = config["visual_overrides"]
    for ring_index, ring_uv in enumerate(uv_rings):
        local = np.asarray(ring_uv, dtype=np.float64) - offset
        line = ax.plot(
            local[:, 0],
            local[:, 1],
            color=visual["reference_boundary_color"],
            linewidth=float(visual["reference_boundary_linewidth"]),
            linestyle="-",
            solid_capstyle="round",
            solid_joinstyle="round",
            label=(
                "reference LoD2 RoofSurface exterior boundary (evaluation only)"
                if ring_index == 0
                else None
            ),
        )[0]
        line.set_path_effects(
            [
                patheffects.Stroke(
                    linewidth=float(visual["reference_boundary_halo_linewidth"]),
                    foreground=visual["reference_boundary_halo_color"],
                    alpha=0.82,
                ),
                patheffects.Normal(),
            ]
        )
    ax.axis("off")
    ax.set_title(
        f"참조 지붕 경계 사진 {index} · {image_path.name} · {crop_profile}\n"
        "Reference LoD2 RoofSurface exterior boundary only · evaluation only",
        fontproperties=font,
        fontsize=8.2,
        color="#252a31",
        pad=5,
    )
    ax.legend(loc="lower left", fontsize=5.2, framealpha=0.88)
    return {
        "image_name": image_path.name,
        "image_record": BASE.file_record(image_path),
        "crop_xyxy": list(box),
        "crop_profile": crop_profile,
        "overlay_primitives": ["reference_RoofSurface_exterior_boundary"],
        "reference_role": "evaluation_only",
        "reference_roof_exterior_rings_n": int(projection["rings_n"]),
        "reference_roof_boundary_vertices_n": int(projection["vertices_n"]),
        "all_boundary_vertices_valid": bool(projection["all_vertices_valid"]),
        "all_boundary_vertices_inside_full_frame": bool(projection["all_vertices_inside_full_frame"]),
        "all_boundary_vertices_inside_margin": bool(projection["all_vertices_inside_margin"]),
        "minimum_frame_margin_fraction": float(projection["minimum_frame_margin_fraction"]),
        "projected_boundary_bbox_area_px2": float(projection["bbox_area_px2"]),
        "projected_boundary_bbox_area_fraction": float(projection["bbox_area_fraction"]),
        "frame_center_radius": float(projection["frame_center_radius"]),
        "projector": "src/stage2/image_projection.py",
        "input_vertical_datum": projection["input_vertical_datum"],
        "geoid_m": projection["geoid_m"],
        "dense_point_overlay_used": False,
        "dense_tin_boundary_overlay_used": False,
        "footprint_overlay_used": False,
        "filled_polygon_overlay_used": False,
        "interior_ring_overlay_used": False,
    }


def render_building(
    staging: Path,
    pdf: PdfPages,
    config: Mapping[str, Any],
    selection_row: Mapping[str, Any],
    points: np.ndarray,
    surfaces: Sequence[Mapping[str, Any]],
    surface_stats: Mapping[str, Any],
    reference_rings: Sequence[np.ndarray],
    status_row: Mapping[str, str],
    photo_views: Sequence[Mapping[str, Any]],
    projection_views_by_name: Mapping[str, Any],
    scene_reference: Mapping[str, Any],
    font: Any,
) -> dict[str, Any]:
    """Render the v3 first row and unchanged-meaning v2 rows 2--4."""
    building_id = str(selection_row["building_id"])
    require(len(points) > 0, f"{building_id} has no DIM class-6 points")
    require(bool(reference_rings), f"{building_id} has no reference roof rings")
    frame = BASE.scene_frame(points, surfaces, reference_rings, config)
    evidence = {"cityjson_surfaces": surfaces, "reference_rings": reference_rings}
    helper_config = BASE.render_config(config)
    comparison = BASE.output_reference_facts(surfaces, reference_rings)
    visual = config["visual_contract"]
    fig = plt.figure(figsize=tuple(visual["panel_inches"]))
    grid = fig.add_gridspec(
        4, 5, left=0.043, right=0.987, bottom=0.060, top=0.902, wspace=0.16, hspace=0.25
    )
    size_field = "stratum_size_area"
    obs_field = "stratum_observation_recon_score"
    fig.suptitle(
        f"{building_id} | size={selection_row[size_field]} × observation={selection_row[obs_field]}\n"
        "P0 raw dense DIM/MVS -> Roofer | NO GS TRAINING | learning_runs=0 | scientific_verdict: null",
        fontproperties=font,
        fontsize=15,
        color="#252a31",
    )
    for y, label in (
        (0.790, "1  참조 지붕 경계 사진 / Reference roof boundary photos"),
        (0.575, "2  DIM class 6 / Dense points"),
        (0.360, "3  P0 Roofer / Canonical output"),
        (0.145, "4  평가 전용 / Evaluation-only overlay"),
    ):
        fig.text(
            0.008, y, label, rotation=90, va="center", ha="center", fontsize=8.0,
            color="#252a31", fontproperties=font,
        )

    image_directory = BASE.repo_path(config["sources"]["image_directory"]["path"])
    require(1 <= len(photo_views) <= 3, f"{building_id} unique visible photo count is outside one to three")
    slots = photo_slot_plan(photo_views)
    photo_receipts: list[dict[str, Any]] = []
    for column, slot in enumerate(slots):
        view_receipt = slot["view"]
        image_name = str(view_receipt.get("name", ""))
        require(image_name in projection_views_by_name, f"camera absent for frozen view: {image_name}")
        image_path = image_directory / image_name
        receipt = projected_reference_photo_panel(
            fig.add_subplot(grid[0, column]),
            image_path,
            projection_views_by_name[image_name],
            scene_reference,
            reference_rings,
            config,
            font,
            column + 1,
            str(slot["crop_profile"]),
        )
        receipt["photo_selection"] = dict(view_receipt)
        receipt["slot_policy"] = {
            "slot_order": int(slot["slot_order"]),
            "crop_profile": str(slot["crop_profile"]),
            "unique_visible_views_n": int(slot["unique_visible_views_n"]),
            "occluded_view_substitution_used": False,
        }
        photo_receipts.append(receipt)

    covariates = [item["field"] for item in config["selection_contract"]["covariates"]]
    input_lines = [
        "표본선정 입력 / selection inputs only",
        f"cell: size={selection_row[size_field]}, observation={selection_row[obs_field]}",
        f"cell candidates: {selection_row['cell_candidate_count']}",
        f"global-rank L2 to cell median: {selection_row['distance_to_cell_median_l2']:.6f}",
        "",
    ]
    input_lines.extend(
        f"{field}: {BASE.format_number(selection_row[field], 4)}  "
        f"(rank {BASE.format_number(selection_row['rank_' + field], 4)})"
        for field in covariates
    )
    input_lines.extend(
        [
            "",
            f"DIM class 6 points (row 2 only): {len(points)}",
            f"reference RoofSurface exterior rings: {len(reference_rings)}",
            "sample frozen before reference GML was opened",
            "photo binding after freeze: adopted pose + explicit orthometric datum",
            "eligibility: target roof visible by surrounding LoD2 first-hit raycast",
            "tiers: full 5% margin, then full-frame fallback",
            f"unique visible views: {len(photo_views)}; visual slots: 3",
            "1 view fallback: same visible photo full / medium / tight; no occluded fill",
            "rank: visibility, centrality, boundary area, nadir, image name",
            "yellow/black line: reference LoD2 roof exterior boundary (evaluation only)",
            "row-1 overlay ONLY: no DIM points, no TIN boundary, no footprint, no fill",
            "reference did not affect population or nine-building sample selection",
            "NO GS TRAINING | learning_runs=0",
            "scientific_verdict: null",
        ]
    )
    BASE.text_panel(
        fig.add_subplot(grid[0, 3:5]),
        "입력·참조경계 투영 이력 / Input and reference-boundary provenance",
        input_lines,
        font,
    )

    displayed_points = 0
    for column, camera in enumerate(frame["cameras"]):
        ax = fig.add_subplot(grid[1, column], projection="3d")
        displayed_points = BASE.plot_dense_points(ax, points, frame, config)
        BASE.PANEL_V4.configure_3d_axis(ax, frame, camera)
        BASE.PANEL_V4.short_title(
            ax,
            f"DIM/MVS class 6 · {camera['title_ko']}",
            f"Raw dense building points · {camera['title_en']}",
            font,
            fontsize=8.2,
        )
    ax = fig.add_subplot(grid[1, 4])
    shown = BASE.downsample(points, int(visual["maximum_scatter_points"]))
    origin = np.asarray(frame["local_origin_epsg25832_xyz"], dtype=np.float64)
    principal = np.asarray(frame["axis"]["vector_east_north"], dtype=np.float64)
    horizontal = (shown[:, :2] - origin[:2]) @ principal
    vertical = shown[:, 2] - origin[2]
    ax.scatter(
        horizontal, vertical, s=2.0, color=visual["palette"]["dense_points"],
        linewidths=0, rasterized=True,
    )
    ax.set_xlabel("principal horizontal (m)", fontsize=7)
    ax.set_ylabel("ΔZ (m)", fontsize=7)
    ax.grid(True, color=visual["palette"]["light_grey"], linewidth=0.45)
    ax.tick_params(labelsize=6)
    ax.set_aspect("equal", adjustable="datalim")
    BASE.PANEL_V4.short_title(
        ax, "DIM class 6 주축 단면", "Principal section · raw dense points", font, fontsize=8.2
    )

    cityjson_render = BASE.PANEL_V4.cityjson_render_parts(surfaces, frame)["stats"]
    for column, camera in enumerate(frame["cameras"]):
        ax = fig.add_subplot(grid[2, column], projection="3d")
        BASE.PANEL_V4.plot_cityjson(ax, evidence, frame, helper_config, alpha=0.92)
        BASE.PANEL_V4.configure_3d_axis(ax, frame, camera)
        BASE.PANEL_V4.short_title(
            ax,
            f"P0 DIM Roofer · {camera['title_ko']}",
            f"Canonical CityJSON · {camera['title_en']}",
            font,
            fontsize=8.2,
        )
    semantic = surface_stats["semantic_counts"]
    output_lines = [
        "canonical P0 DIM Roofer CityJSON LoD2.2",
        "source_model_id: canonical_dense_w2_1",
        "raw dense DIM/MVS -> Roofer",
        "NO GS TRAINING | learning_runs=0",
        "",
        f"LoD: {BASE.format_number(surface_stats['lod'], 1)} Solid",
        f"surfaces / vertices: {surface_stats['surfaces_n']} / {surface_stats['vertices_n']}",
        f"RoofSurface: {semantic.get('RoofSurface', 0)}",
        f"WallSurface: {semantic.get('WallSurface', 0)}",
        f"GroundSurface: {semantic.get('GroundSurface', 0)}",
        f"interior rings: {surface_stats['interior_rings_n']}",
        f"wireframe-only hole surfaces: {cityjson_render['wireframe_only_surfaces_n']}",
        f"canonical status / has_lod22: {status_row.get('status', 'n/a')} / {status_row.get('has_lod22', 'n/a')}",
        f"val3dity valid: {status_row.get('val3dity_valid', 'n/a')}",
        "scientific_verdict: null",
    ]
    BASE.text_panel(
        fig.add_subplot(grid[2, 4]), "정본 출력 요약 / Canonical output summary", output_lines, font
    )

    for column, camera in enumerate(frame["cameras"]):
        ax = fig.add_subplot(grid[3, column], projection="3d")
        BASE.PANEL_V4.plot_cityjson(ax, evidence, frame, helper_config, alpha=0.38)
        BASE.PANEL_V4.plot_reference(ax, evidence, frame, helper_config)
        BASE.PANEL_V4.configure_3d_axis(ax, frame, camera)
        BASE.PANEL_V4.short_title(
            ax,
            f"출력+참조 · {camera['title_ko']} (평가 전용)",
            f"Output + reference · {camera['title_en']} (evaluation only)",
            font,
            fontsize=8.0,
        )
    comparison_lines = [
        "filled blue/grey/brown: canonical Roofer output",
        "orange dashed rings: reference GML (evaluation only)",
        "reference opened after nine-building sample freeze",
        "reference does not select row 2-4 3D camera orientation",
        "reference affects shared comparison bounds only",
        "projection: orthographic | Z exaggeration: 1.0×",
        "",
        f"exact XY coordinate set equal: {comparison['exact_XY_coordinate_set_equal']}",
        f"exact XYZ coordinate set equal: {comparison['exact_XYZ_coordinate_set_equal']}",
        f"unique XY output/ref: {comparison['output_unique_xy_n']} / {comparison['reference_unique_xy_n']}",
        f"unique XYZ output/ref: {comparison['output_unique_xyz_n']} / {comparison['reference_unique_xyz_n']}",
        f"output Z: {comparison['output_z_min_m']:.3f}–{comparison['output_z_max_m']:.3f} m",
        f"reference Z: {comparison['reference_z_min_m']:.3f}–{comparison['reference_z_max_m']:.3f} m",
        "CRS: EPSG:25832",
        "NO GS TRAINING | learning_runs=0",
        "scientific_verdict: null",
    ]
    BASE.text_panel(
        fig.add_subplot(grid[3, 4]),
        "중첩·카메라 요약 / Overlay and camera receipt",
        comparison_lines,
        font,
    )
    fig.text(
        0.5, 0.022,
        "P0 raw dense DIM/MVS -> Roofer · reference GML is evaluation only · no interpretation · scientific_verdict: null",
        ha="center", va="center", fontsize=7.6, color="#252a31", fontproperties=font,
    )
    panel_directory = staging / config["outputs"]["panel_directory"]
    panel_directory.mkdir(parents=True, exist_ok=True)
    panel_path = panel_directory / config["outputs"]["panel_template"].format(building_id=building_id)
    require(not panel_path.exists(), f"panel overwrite refused: {panel_path}")
    fig.savefig(
        panel_path,
        dpi=int(visual["panel_dpi"]),
        facecolor="white",
        metadata={"Software": "JointBuildGS P0 dense baseline qualitative v3"},
    )
    pdf.savefig(fig, facecolor="white")
    plt.close(fig)
    with Image.open(panel_path) as rendered:
        width, height = rendered.size
    minimum = visual["minimum_panel_pixels"]
    require(width >= int(minimum[0]) and height >= int(minimum[1]), "panel resolution below contract")
    return {
        "building_id": building_id,
        "cell": {size_field: selection_row[size_field], obs_field: selection_row[obs_field]},
        "panel": BASE.bundle_record(staging, panel_path),
        "photo_receipts": photo_receipts,
        "unique_raycast_visible_photo_views_n": len(photo_views),
        "visual_photo_slots_n": len(slots),
        "occluded_view_substitution_used": False,
        "row_1_overlay_primitives": ["reference_RoofSurface_exterior_boundary"],
        "row_1_reference_role": "evaluation_only",
        "dense_class6_points_n": len(points),
        "dense_class6_points_displayed_per_geometry_view": displayed_points,
        "cityjson": dict(surface_stats),
        "comparison": comparison,
        "frame": frame,
        "render_pixels": [width, height],
        "mandatory_labels": list(BASE.MANDATORY_LABELS),
        "scientific_verdict": None,
        "interpretation": None,
    }


def _prepare(config: Mapping[str, Any]) -> dict[str, Any]:
    """Freeze the input-only sample, then bind dense/output/reference evidence."""
    result = BASE.select_sample(config)
    selected_order = tuple(str(row["building_id"]) for row in result.selected)
    require(selected_order == EXPECTED_SELECTED, "v3 selected sample differs from freeze")
    selected_ids = set(selected_order)
    footprints, footprint_record = BASE.load_locked_footprints(config, selected_ids)
    dense_source = BASE.E5.Source(
        source_group="raw_dense",
        source_run="raw_dense",
        display_label="raw dense (DIM/MVS)",
        status_role="baseline",
        status_path=None,
        status_input="DIM",
        cityjson_path=None,
        pointcloud_path=BASE.repo_path(config["sources"]["dense_classified_laz"]["path"]),
    )
    cloud_cache = BASE.E5.PointCloudCache(footprints)
    points_by_id = {
        building_id: cloud_cache.read_roof_points(dense_source, building_id)
        for building_id in selected_order
    }
    for building_id, points in points_by_id.items():
        require(len(points) > 0, f"selected building has no class-6 points: {building_id}")
    cityjson_path = BASE.repo_path(config["sources"]["canonical_roofer_cityjson"]["path"])
    cityjson_payload = BASE.read_json(cityjson_path)
    output_by_id = {
        building_id: BASE.load_cityjson_surfaces_for_building(cityjson_payload, building_id)
        for building_id in selected_order
    }

    # Reference GML access begins only here, after the input-only sample freeze.
    reference_directory = BASE.repo_path(config["sources"]["reference_gml_directory"]["path"])
    reference_surfaces = BASE.E5.parse_lod2_roofs(reference_directory, selected_ids)
    reference_rings_by_id = {
        building_id: BASE.E5.surface_polys_3d(reference_surfaces[building_id])
        for building_id in selected_order
    }
    for building_id, rings in reference_rings_by_id.items():
        require(bool(rings), f"reference RoofSurface exterior rings absent: {building_id}")
    reference_paths = sorted(reference_directory.glob("*.gml"))
    require(bool(reference_paths), "reference GML files absent")
    raycast_scene = build_surrounding_lod2_scene(
        reference_paths,
        reference_rings_by_id,
        config,
    )

    scene_reference = BASE.read_json(
        BASE.repo_path(config["sources"]["scene_reference_frame"]["path"])
    )
    projection_views = BASE.load_projection_views(config)
    image_directory = BASE.repo_path(config["sources"]["image_directory"]["path"])
    require(image_directory.is_dir(), "image directory absent")
    photo_views_by_id = {
        building_id: select_reference_photo_views(
            building_id,
            reference_rings_by_id[building_id],
            projection_views,
            scene_reference,
            image_directory,
            raycast_scene,
            config,
        )
        for building_id in selected_order
    }
    selected_image_paths = [
        image_directory / str(view["name"])
        for building_id in selected_order
        for view in photo_views_by_id[building_id]
    ]
    status_rows = [
        row
        for row in BASE.read_csv(BASE.repo_path(config["sources"]["canonical_roofer_status"]["path"]))
        if row.get("input") == "DIM" and row.get("building_id") in selected_ids
    ]
    status_by_id = BASE._unique_by(status_rows, "building_id", 9, "canonical DIM Roofer status sample")
    return {
        "result": result,
        "selected_order": selected_order,
        "footprint_record": footprint_record,
        "points_by_id": points_by_id,
        "output_by_id": output_by_id,
        "reference_rings_by_id": reference_rings_by_id,
        "reference_paths": reference_paths,
        "raycast_scene": raycast_scene,
        "scene_reference": scene_reference,
        "projection_views": projection_views,
        "photo_views_by_id": photo_views_by_id,
        "selected_image_paths": selected_image_paths,
        "status_by_id": status_by_id,
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
        selection_payload["schema"] = "jointbuildgs.fusion_w1.dense_baseline_qualitative.selection_audit.v3"
        selection_payload["postfreeze_photo_binding"] = {
            "input": "evaluation-only reference LoD2 RoofSurface exterior boundary",
            "population_or_sample_selection_influence": False,
            "photo_address_influence_after_freeze": True,
        }
        BASE.write_json_new(staging / config["outputs"]["selection_audit_json"], selection_payload)

        sources_before = BASE.fixed_source_snapshot(
            config, prepared["selected_image_paths"], prepared["reference_paths"]
        )
        pdf_path = staging / config["outputs"]["multipage_pdf"]
        panel_receipts: list[dict[str, Any]] = []
        with PdfPages(
            pdf_path,
            metadata={
                "Title": "P0 dense qualitative v3 reference RoofSurface photo locator",
                "Subject": "NO GS TRAINING; evaluation-only reference boundary; scientific_verdict null",
                "Creator": "JointBuildGS",
            },
        ) as pdf:
            for row in result.selected:
                building_id = str(row["building_id"])
                surfaces, stats = prepared["output_by_id"][building_id]
                panel_receipts.append(
                    render_building(
                        staging,
                        pdf,
                        config,
                        row,
                        prepared["points_by_id"][building_id],
                        surfaces,
                        stats,
                        prepared["reference_rings_by_id"][building_id],
                        prepared["status_by_id"][building_id],
                        prepared["photo_views_by_id"][building_id],
                        prepared["projection_views"],
                        prepared["scene_reference"],
                        font,
                    )
                )
        require(pdf_path.is_file() and pdf_path.stat().st_size > 0, "multipage PDF absent")
        overview_record = BASE.render_overview(staging, config, panel_receipts, font)
        sources_after = BASE.fixed_source_snapshot(
            config, prepared["selected_image_paths"], prepared["reference_paths"]
        )
        require(sources_after == sources_before, "source inputs changed while rendering")
        outputs = BASE.output_records(staging, config["outputs"]["manifest"])
        output_set_hash = BASE.set_sha256(
            f"{record['path']}|{record['sha256']}|{record['bytes']}" for record in outputs
        )
        manifest = {
            "schema": MANIFEST_SCHEMA,
            "created_utc": BASE.utc_now(),
            "state": "COMPLETE",
            "task_id": config["task_id"],
            "run_id": config["run_id"],
            "branch": config["branch"],
            "population": {
                "count": len(result.population_ids),
                "set_sha256": result.population_set_sha256,
                "display_name": config["population_contract"]["display_name"],
                "success_definition": config["population_contract"]["success_definition"],
            },
            "selection": {
                "sample_count": len(result.selected),
                "selected_building_ids": list(prepared["selected_order"]),
                "selected_set_sha256": BASE.set_sha256(prepared["selected_order"]),
                "population_or_sample_selector_reference_influence": False,
                "reference_open_stage": "after_input_only_population_and_nine_building_sample_freeze",
                "postfreeze_photo_binding_input": "evaluation_only_reference_RoofSurface_exterior_boundary",
                "postfreeze_photo_address_reference_influence": True,
                "postfreeze_visibility_gate": "surrounding_reference_LoD2_first_intersection_raycast",
            },
            "render_contract": {
                "layout": "4_rows_x_5_columns",
                "individual_panel_count": len(panel_receipts),
                "single_multipage_pdf": True,
                "overview": overview_record,
                "row_1_overlay_primitives": ["reference_RoofSurface_exterior_boundary"],
                "row_1_forbidden_overlays": [
                    "dense_points", "dense_TIN_boundary", "footprint", "polygon_fill", "interior_rings"
                ],
                "rows_2_to_4_meanings": "unchanged_from_v2",
                "geometry_rows_camera_projection": "orthographic",
                "geometry_rows_z_exaggeration": 1.0,
                "geometry_rows_reference_view_orientation_influence": False,
                "photo_projection": config["photo_projection_contract"],
                "mandatory_labels": list(BASE.MANDATORY_LABELS),
            },
            "surrounding_lod2_raycast_scene": dict(prepared["raycast_scene"].stats),
            "panel_receipts": panel_receipts,
            "source_records": list(sources_before.values()),
            "footprint_GeoPackage_record": prepared["footprint_record"],
            "footprint_role": "row_2_dense_point_clipping_only; never overlaid on row_1 photos",
            "font": font_record,
            "outputs": outputs,
            "output_set_sha256": output_set_hash,
            "reference_role": "evaluation_only",
            "learning_runs_started": 0,
            "new_training_runs": 0,
            "scientific_verdict": None,
            "interpretation": None,
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
    require(manifest.get("schema") == MANIFEST_SCHEMA, "v3 manifest schema drift")
    require(manifest.get("state") == "COMPLETE", "v3 manifest is not COMPLETE")
    require(manifest.get("scientific_verdict") is None, "manifest contains a verdict")
    require(manifest.get("learning_runs_started") == 0, "manifest learning count drift")
    require(
        tuple(manifest.get("selection", {}).get("selected_building_ids", [])) == EXPECTED_SELECTED,
        "manifest sample freeze drift",
    )
    require(
        manifest.get("render_contract", {}).get("row_1_overlay_primitives")
        == ["reference_RoofSurface_exterior_boundary"],
        "row-1 overlay contract drift",
    )
    source_records_n = BASE.verify_source_records(manifest.get("source_records"))
    records = manifest.get("outputs") or []
    require(isinstance(records, list) and records, "manifest output ledger absent")
    for record in records:
        path = root / str(record["path"])
        require(path.is_file(), f"published output absent: {record['path']}")
        require(path.stat().st_size == int(record["bytes"]), f"published size drift: {record['path']}")
        require(BASE.sha256_file(path) == record["sha256"], f"published hash drift: {record['path']}")
    observed_set_hash = BASE.set_sha256(
        f"{record['path']}|{record['sha256']}|{record['bytes']}" for record in records
    )
    require(observed_set_hash == manifest.get("output_set_sha256"), "output set hash drift")
    for receipt in manifest.get("panel_receipts", []):
        require(
            receipt.get("row_1_overlay_primitives") == ["reference_RoofSurface_exterior_boundary"],
            f"row-1 primitive drift: {receipt.get('building_id')}",
        )
        require(len(receipt.get("photo_receipts", [])) == 3, "photo receipt count drift")
        unique_visible = int(receipt.get("unique_raycast_visible_photo_views_n", 0))
        require(1 <= unique_visible <= 3, "unique visible view count drift")
        require(receipt.get("occluded_view_substitution_used") is False, "occluded view substituted")
        for photo in receipt["photo_receipts"]:
            require(photo.get("overlay_primitives") == ["reference_RoofSurface_exterior_boundary"], "photo overlay drift")
            require(photo.get("all_boundary_vertices_inside_full_frame") is True, "photo full-frame gate drift")
            selection = photo.get("photo_selection") or {}
            require(
                (selection.get("visibility") or {}).get("passes_target_roof_visibility_gate") is True,
                "occluded target-roof photo published",
            )
            require(
                (photo.get("slot_policy") or {}).get("occluded_view_substitution_used") is False,
                "slot used occluded substitute",
            )
            for key in (
                "dense_point_overlay_used", "dense_tin_boundary_overlay_used", "footprint_overlay_used",
                "filled_polygon_overlay_used", "interior_ring_overlay_used",
            ):
                require(photo.get(key) is False, f"forbidden row-1 overlay used: {key}")
    panels = sorted((root / config["outputs"]["panel_directory"]).glob("*.png"))
    require(len(panels) == 9, "published panel count drift")
    for name in (
        config["outputs"]["multipage_pdf"],
        config["outputs"]["overview"],
        config["outputs"]["selection_audit_csv"],
        config["outputs"]["selection_audit_json"],
    ):
        require((root / name).is_file(), f"published required output absent: {name}")
    return {
        "state": "VERIFIED",
        "root": str(root),
        "panels": len(panels),
        "outputs": len(records),
        "source_records": source_records_n,
        "selected_building_ids": list(EXPECTED_SELECTED),
        "row_1_overlay_primitives": ["reference_RoofSurface_exterior_boundary"],
        "scientific_verdict": None,
    }


def check(config: Mapping[str, Any]) -> dict[str, Any]:
    prepared = _prepare(config)
    return {
        "state": "CHECKED_READ_ONLY",
        "population_count": len(prepared["result"].population_ids),
        "population_set_sha256": prepared["result"].population_set_sha256,
        "selected_building_ids": list(prepared["selected_order"]),
        "sample_frozen_before_reference_open": True,
        "photo_binding": {
            "stage": "after_input_only_nine_building_sample_freeze",
            "input": "evaluation_only_reference_LoD2_RoofSurface_exterior_boundary",
            "method": "surrounding_LoD2_raycast_visibility_then_full_margin_to_full_frame_tiers",
            "row_1_overlay_primitives": ["reference_RoofSurface_exterior_boundary"],
            "forbidden_row_1_overlays_used": [],
            "views": {
                building_id: {
                    "unique_visible_views_n": len(prepared["photo_views_by_id"][building_id]),
                    "occluded_view_substitution_used": False,
                    "slot_plan": [
                        {
                            "image_name": slot["view"]["name"],
                            "crop_profile": slot["crop_profile"],
                        }
                        for slot in photo_slot_plan(prepared["photo_views_by_id"][building_id])
                    ],
                    "unique_views": [
                        {
                            "name": view["name"],
                            "eligibility_tier": view["eligibility_tier"],
                            "visible_target_fraction": view["visibility"]["visible_target_fraction"],
                            "visible_target_samples_n": view["visibility"]["visible_target_samples_n"],
                            "target_samples_n": view["visibility"]["target_samples_n"],
                            "bbox_area_px2": view["projected_boundary_bbox_area_px2"],
                            "frame_center_radius": view["frame_center_radius"],
                            "nadir_deg": view["nadir_deg"],
                        }
                        for view in prepared["photo_views_by_id"][building_id]
                    ],
                }
                for building_id in prepared["selected_order"]
            },
        },
        "surrounding_lod2_raycast_scene": dict(prepared["raycast_scene"].stats),
        "learning_runs_started": 0,
        "scientific_verdict": None,
    }


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--output-root", type=Path)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("check", help="validate and report the frozen sample and photo binding; write nothing")
    subparsers.add_parser("render", help="atomically publish the complete v3 nine-panel bundle")
    subparsers.add_parser("verify", help="verify a previously published v3 bundle; write nothing")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    config = load_config(args.config.resolve())
    if args.command == "check":
        payload = check(config)
    elif args.command == "render":
        payload = publish(config, args.output_root)
    else:
        payload = verify_bundle(config, args.output_root)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
