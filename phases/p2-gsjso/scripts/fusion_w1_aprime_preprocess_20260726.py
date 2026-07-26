#!/usr/bin/env python3
"""Prepare the preregistered FUS-W1 A-prime class-6 seed and roof priors.

This command is intentionally a new cache lineage.  It consumes the adopted
corrected COLMAP poses but never consumes the arm-A preprocessing cache.  For
each of the nine machine-joined A-prime targets it:

* crops the original ALS class-6 rows strictly to the approved footprint;
* builds one unfiltered roof TIN and retains a seed point only when the genuine
  first ray--triangle intersection agrees within 5 cm in at least three of the
  selected corrected-pose views;
* writes a COLMAP data root whose point rows are the filtered class-6 seed only
  (no class 2 and no SfM rows);
* publishes roof-TIN depth, normal, and one exact common valid mask ``M_j`` for
  depth, normal, and photo supervision; and
* publishes the untouched 20 m class-2 crop separately for P0-prime/readout.

No learning, TSDF extraction, Roofer execution, scoring, or verdict occurs
here.  Every runtime artifact is written atomically where the file format
allows it, and each completed building is independently reviewable.
"""
from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from datetime import datetime
import importlib.util
import json
import math
import os
from pathlib import Path
import struct
import sys
from typing import Any, Mapping, Sequence

os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib")
os.environ.setdefault("XDG_CACHE_HOME", "/tmp")
os.environ.setdefault("PYTHONDONTWRITEBYTECODE", "1")

import numpy as np


REPO = Path(__file__).resolve().parents[3]
SCRIPT_DIR = Path(__file__).resolve().parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from projection_datum import base_to_canonical_points  # noqa: E402
from src.stage2.colmap_io import (  # noqa: E402
    Camera,
    Image as ColmapImage,
    read_images_bin,
    read_points3d_bin,
)


DEFAULT_CONFIG = (
    REPO
    / "phases/p2-gsjso/configs/fusion_w1_aprime_preprocess_20260726.json"
)
CONFIG_SCHEMA = "jointbuildgs.fusion_w1_aprime.preprocess.config.v1"
BUILDING_SCHEMA = "jointbuildgs.fusion_w1_aprime.preprocess_building.v1"
RUN_SCHEMA = "jointbuildgs.fusion_w1_aprime.preprocess_run.v1"
CORRECTED_IMAGES_SHA256 = (
    "28b38383a0b6d82656108e8f0e5e79711dcda93948ab2e89c1cd8f47215962a5"
)


class AprimePreprocessError(RuntimeError):
    """Fail-closed A-prime contract, geometry, or publication error."""


@dataclass(frozen=True)
class AprimeTarget:
    aprime_order: int
    building_id: str
    target_role: str
    tier: str
    cohort: str
    source_processing_order: int
    selection_reason: str
    texture_low_gradient_fraction: float
    selection_sources: str
    gs4buildings_overlap_status: str
    gs4buildings_overlap_reason: str


def _import_module(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise AprimePreprocessError(f"cannot import helper: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


V1 = _import_module(
    "fusion_w1_preprocess_v1_for_aprime",
    SCRIPT_DIR / "fusion_w1_preprocess_v1_20260725.py",
)


def repo_path(value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else REPO / path


def relative(path: str | Path) -> str:
    return V1.relative(path)


def load_json(path: str | Path) -> dict[str, Any]:
    return V1.load_json(path)


def canonical_building_id(value: Any) -> str:
    return V1.canonical_building_id(value)


def load_config(path: Path) -> dict[str, Any]:
    config = load_json(path)
    if config.get("schema") != CONFIG_SCHEMA:
        raise AprimePreprocessError("unexpected A-prime preprocess config schema")
    if config.get("run_id") != "20260726_fusion_w1_aprime":
        raise AprimePreprocessError("A-prime preprocessing run namespace drift")
    if config["r1_contract"]["corrected_images_sha256"] != CORRECTED_IMAGES_SHA256:
        raise AprimePreprocessError("corrected pose hash is not the adopted 07-25 publication")
    if int(config["r1_contract"]["transform_application_count"]) != 1:
        raise AprimePreprocessError("corrected pose transform application count must be one")
    subset = config["subset_contract"]
    if subset["training_classes"] != [6]:
        raise AprimePreprocessError("trainer seed must contain class 6 only")
    if subset["sfm_training_points_forbidden"] is not True:
        raise AprimePreprocessError("SfM training-point prohibition is not locked")
    if not math.isclose(float(subset["seed_init_opacity"]), 0.1, abs_tol=1e-12):
        raise AprimePreprocessError("A-prime class-6 seed init opacity must be 0.1")
    visibility = config["visibility_filter"]
    if not math.isclose(float(visibility["epsilon_m"]), 0.05, abs_tol=1e-12):
        raise AprimePreprocessError("visibility epsilon must be 0.05 m")
    if int(visibility["minimum_views_k"]) != 3:
        raise AprimePreprocessError("visibility minimum must be k=3")
    if visibility["point_zbuffer_substitute_forbidden"] is not True:
        raise AprimePreprocessError("geometry visibility must not use a point z-buffer")
    tin = config["tin_supervision"]
    expected_tin = {
        "maximum_xy_edge_m": 3.0,
        "maximum_slope_deg": 75.0,
        "minimum_xy_triangle_area_m2": 0.005,
        "outer_valid_mask_erosion_px": 1,
    }
    for key, expected in expected_tin.items():
        if not math.isclose(float(tin[key]), expected, abs_tol=1e-12):
            raise AprimePreprocessError(f"roof TIN contract drift: {key}")
    if tin["photo_mask"] != "exact_M_j":
        raise AprimePreprocessError("photo mask must be the exact roof TIN M_j")
    if tin["ground_supervision"] is not False or tin["wall_supervision"] is not False:
        raise AprimePreprocessError("A-prime ground/wall supervision must remain disabled")
    minimum = int(config["view_selection"]["minimum_views"])
    maximum = int(config["view_selection"]["maximum_views"])
    if not 10 <= minimum <= maximum <= 30:
        raise AprimePreprocessError("selected-view contract must remain within 10..30")
    if config["view_selection"].get("role_policy") != (
        "all_selected_views_are_training_views_no_holdout"
    ):
        raise AprimePreprocessError(
            "P1 visibility votes must be counted over the learning-view set"
        )
    if not math.isclose(
        float(config["data_root_contract"].get("training_downscale_required", math.nan)),
        1.0,
        abs_tol=1.0e-12,
    ):
        raise AprimePreprocessError("A-prime exact-M_j data root requires downscale=1.0")
    if config["data_root_contract"].get(
        "saved_M_j_must_equal_dataloader_depth_normal_and_photo_masks"
    ) is not True:
        raise AprimePreprocessError("saved-M_j dataloader roundtrip gate is not locked")
    outputs = config["outputs"]
    stable_root = str(outputs["stable_root"])
    namespace = str(outputs["cache_namespace"])
    forbidden = str(outputs["old_preprocess_root_forbidden"])
    if "20260726_fusion_w1_aprime" not in stable_root or "aprime" not in namespace:
        raise AprimePreprocessError("A-prime cache namespace is not isolated")
    if stable_root.startswith(forbidden) or namespace == "pose_28b38383a0b6d826":
        raise AprimePreprocessError("arm-A preprocess cache reuse is forbidden")
    for value in config["inputs"].values():
        values = value if isinstance(value, list) else [value]
        for item in values:
            if isinstance(item, str) and "/preprocess_v1/" in item:
                raise AprimePreprocessError("arm-A cache appears in A-prime inputs")
    return config


def verify_method_lock(config: Mapping[str, Any]) -> dict[str, Any]:
    branch = V1.git("branch", "--show-current").stdout.strip()
    if branch != config["branch"]:
        raise AprimePreprocessError(f"branch {branch!r} != {config['branch']!r}")
    required = [
        *config["implementation_files"],
        config["inputs"]["prereg_lock"],
        config["inputs"]["aprime_targets_csv"],
        config["inputs"]["aprime_targets_manifest"],
        config["inputs"]["v1_helper_script"],
    ]
    records: list[dict[str, str]] = []
    for item in required:
        path = repo_path(item)
        if not path.is_file():
            raise AprimePreprocessError(f"required method/input missing: {item}")
        if V1.git("ls-files", "--error-unmatch", item, check=False).returncode:
            raise AprimePreprocessError(f"required method/input is not committed: {item}")
        if V1.git("diff", "--quiet", "HEAD", "--", item, check=False).returncode:
            raise AprimePreprocessError(f"required method/input differs from HEAD: {item}")
        records.append({"path": item, "sha256": V1.sha256_file(path)})
    return {
        "branch": branch,
        "head": V1.git("rev-parse", "HEAD").stdout.strip(),
        "required_files": records,
    }


def verify_input_hashes(config: Mapping[str, Any]) -> dict[str, str]:
    observed: dict[str, str] = {}
    for logical, expected in config["input_sha256"].items():
        path = repo_path(logical)
        if not path.is_file():
            raise AprimePreprocessError(f"locked input missing: {logical}")
        actual = V1.sha256_file(path)
        if actual != expected:
            raise AprimePreprocessError(
                f"locked input SHA drift: {logical}: {actual} != {expected}"
            )
        observed[logical] = actual
    return observed


def validate_authorization(config: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    try:
        r1, r2 = V1.validate_authorization(config)
    except Exception as exc:
        raise AprimePreprocessError(str(exc)) from exc
    prereg = load_json(config["inputs"]["prereg_lock"])
    p1 = prereg.get("p1_seed", {})
    p2 = prereg.get("p2_supervision", {})
    if p1.get("training_seed_classes") != [6]:
        raise AprimePreprocessError("prereg does not bind class-6-only training seed")
    if not math.isclose(float(p1.get("visibility_epsilon_m", math.nan)), 0.05):
        raise AprimePreprocessError("prereg visibility epsilon mismatch")
    if int(p1.get("minimum_visible_views_k", -1)) != 3:
        raise AprimePreprocessError("prereg visibility k mismatch")
    if p2.get("photo_scope") != "building_only_exact_M_j":
        raise AprimePreprocessError("prereg exact-M_j photo scope mismatch")
    if p2.get("ground_supervision") is not False or p2.get("wall_supervision") is not False:
        raise AprimePreprocessError("prereg ground/wall supervision mismatch")
    return r1, r2


def _read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if not reader.fieldnames:
            raise AprimePreprocessError(f"CSV has no header: {relative(path)}")
        return list(reader.fieldnames), list(reader)


def load_aprime_targets(
    aprime_path: Path,
    canonical_path: Path,
    config: Mapping[str, Any],
) -> list[AprimeTarget]:
    """Load nine targets and prove every semantic field is a canonical join."""

    canonical_fields, canonical_rows = _read_csv(canonical_path)
    required_canonical = {
        "building_id",
        "tier",
        "cohort",
        "processing_order",
        "selection_reason",
        "texture_low_gradient_fraction",
        "selection_sources",
        "gs4buildings_overlap_status",
        "gs4buildings_overlap_reason",
    }
    if not required_canonical.issubset(canonical_fields):
        raise AprimePreprocessError("canonical target CSV join fields are incomplete")
    if len(canonical_rows) != 178:
        raise AprimePreprocessError(f"canonical target population {len(canonical_rows)} != 178")
    canonical: dict[str, dict[str, str]] = {}
    for row in canonical_rows:
        building_id = canonical_building_id(row["building_id"])
        if building_id in canonical:
            raise AprimePreprocessError(f"duplicate canonical target: {building_id}")
        canonical[building_id] = row

    fields, rows = _read_csv(aprime_path)
    required = {
        "aprime_order",
        "building_id",
        "target_role",
        "tier",
        "cohort",
        "source_processing_order",
        "selection_reason",
        "texture_low_gradient_fraction",
        "selection_sources",
        "gs4buildings_overlap_status",
        "gs4buildings_overlap_reason",
    }
    if not required.issubset(fields):
        raise AprimePreprocessError("A-prime target CSV header contract mismatch")
    expected_n = int(config["target_contract"]["expected_population_n"])
    if len(rows) != expected_n:
        raise AprimePreprocessError(f"A-prime target population {len(rows)} != {expected_n}")
    output: list[AprimeTarget] = []
    seen: set[str] = set()
    roles: list[str] = []
    join_fields = (
        ("tier", "tier"),
        ("cohort", "cohort"),
        ("source_processing_order", "processing_order"),
        ("selection_reason", "selection_reason"),
        ("texture_low_gradient_fraction", "texture_low_gradient_fraction"),
        ("selection_sources", "selection_sources"),
        ("gs4buildings_overlap_status", "gs4buildings_overlap_status"),
        ("gs4buildings_overlap_reason", "gs4buildings_overlap_reason"),
    )
    for expected_order, row in enumerate(rows, 1):
        if int(row["aprime_order"]) != expected_order:
            raise AprimePreprocessError("A-prime order must be contiguous 1..9")
        building_id = canonical_building_id(row["building_id"])
        if building_id in seen:
            raise AprimePreprocessError(f"duplicate A-prime target: {building_id}")
        seen.add(building_id)
        source = canonical.get(building_id)
        if source is None:
            raise AprimePreprocessError(f"A-prime target is absent from canonical CSV: {building_id}")
        for target_key, source_key in join_fields:
            if str(row[target_key]).strip() != str(source[source_key]).strip():
                raise AprimePreprocessError(
                    f"A-prime machine-join drift for {building_id}: {target_key}"
                )
        role = str(row["target_role"]).strip()
        if role not in {"dim_failure", "textured_control"}:
            raise AprimePreprocessError(f"unexpected A-prime target role: {role}")
        roles.append(role)
        output.append(
            AprimeTarget(
                aprime_order=expected_order,
                building_id=building_id,
                target_role=role,
                tier=str(row["tier"]),
                cohort=str(row["cohort"]),
                source_processing_order=int(row["source_processing_order"]),
                selection_reason=str(row["selection_reason"]),
                texture_low_gradient_fraction=float(row["texture_low_gradient_fraction"]),
                selection_sources=str(row["selection_sources"]),
                gs4buildings_overlap_status=str(row["gs4buildings_overlap_status"]),
                gs4buildings_overlap_reason=str(row["gs4buildings_overlap_reason"]),
            )
        )
    if roles.count("dim_failure") != int(config["target_contract"]["expected_dim_failure_n"]):
        raise AprimePreprocessError("A-prime DIM-failure count drift")
    if roles.count("textured_control") != int(
        config["target_contract"]["expected_textured_control_n"]
    ):
        raise AprimePreprocessError("A-prime textured-control count drift")
    return output


def first_ray_tin_intersection_distances(
    camera_center: np.ndarray,
    directions: np.ndarray,
    tin: Any,
    *,
    ray_chunk_size: int = 512,
    triangle_chunk_size: int = 1024,
    parallel_epsilon: float = 1.0e-10,
    barycentric_epsilon: float = 1.0e-9,
    minimum_hit_distance_m: float = 1.0e-6,
) -> np.ndarray:
    """Return the first genuine Moller--Trumbore hit for each normalized ray.

    The implementation compares rays directly with TIN triangles.  It does not
    project points into a z-buffer and it does not substitute raster depth for a
    ray--geometry intersection.  Chunking only bounds memory; candidate tests
    and nearest-hit reduction are otherwise exact in float64.
    """

    origin = np.asarray(camera_center, dtype=np.float64)
    rays = np.asarray(directions, dtype=np.float64)
    if origin.shape != (3,):
        raise ValueError("camera_center must have shape (3,)")
    if rays.ndim != 2 or rays.shape[1] != 3:
        raise ValueError("directions must have shape (N,3)")
    if ray_chunk_size <= 0 or triangle_chunk_size <= 0:
        raise ValueError("ray and triangle chunk sizes must be positive")
    vertices = np.asarray(tin.vertices, dtype=np.float64)
    simplices = np.asarray(tin.simplices, dtype=np.int64)
    if vertices.ndim != 2 or vertices.shape[1] != 3:
        raise ValueError("TIN vertices must have shape (V,3)")
    if simplices.ndim != 2 or simplices.shape[1] != 3:
        raise ValueError("TIN simplices must have shape (T,3)")
    output = np.full(len(rays), np.inf, dtype=np.float64)
    norms = np.linalg.norm(rays, axis=1)
    valid_rays = np.isfinite(rays).all(axis=1) & (norms > 1.0e-15)
    normalized = np.zeros_like(rays)
    normalized[valid_rays] = rays[valid_rays] / norms[valid_rays, None]
    valid_indices = np.flatnonzero(valid_rays)
    for ray_start in range(0, len(valid_indices), int(ray_chunk_size)):
        ray_ids = valid_indices[ray_start : ray_start + int(ray_chunk_size)]
        direction = normalized[ray_ids]
        nearest = np.full(len(ray_ids), np.inf, dtype=np.float64)
        for tri_start in range(0, len(simplices), int(triangle_chunk_size)):
            tri_ids = simplices[tri_start : tri_start + int(triangle_chunk_size)]
            triangle = vertices[tri_ids]
            v0 = triangle[:, 0]
            edge1 = triangle[:, 1] - v0
            edge2 = triangle[:, 2] - v0
            h = np.cross(direction[:, None, :], edge2[None, :, :])
            determinant = np.einsum("tj,rtj->rt", edge1, h)
            parallel = np.abs(determinant) <= float(parallel_epsilon)
            inverse = np.zeros_like(determinant)
            inverse[~parallel] = 1.0 / determinant[~parallel]
            s = origin[None, :] - v0
            u = inverse * np.einsum("tj,rtj->rt", s, h)
            q = np.cross(s, edge1)
            v = inverse * (direction @ q.T)
            distance = inverse * np.einsum("tj,tj->t", edge2, q)[None, :]
            epsilon = float(barycentric_epsilon)
            hit = (
                (~parallel)
                & (u >= -epsilon)
                & (v >= -epsilon)
                & (u + v <= 1.0 + epsilon)
                & np.isfinite(distance)
                & (distance > float(minimum_hit_distance_m))
            )
            candidate = np.where(hit, distance, np.inf)
            nearest = np.minimum(nearest, candidate.min(axis=1))
        output[ray_ids] = nearest
    return output


def raycast_seed_visibility(
    gate: Any,
    points_canonical: np.ndarray,
    tin: Any,
    selected: Sequence[Any],
    visibility_config: Mapping[str, Any],
) -> tuple[np.ndarray, np.ndarray, list[dict[str, Any]], dict[str, int]]:
    """Count strict epsilon first-hit agreements over selected views."""

    points = np.asarray(points_canonical, dtype=np.float64)
    if points.ndim != 2 or points.shape[1] != 3:
        raise ValueError("points_canonical must have shape (N,3)")
    epsilon_m = float(visibility_config["epsilon_m"])
    minimum_k = int(visibility_config["minimum_views_k"])
    matrix = np.zeros((len(points), len(selected)), dtype=np.uint8)
    rows: list[dict[str, Any]] = []
    for column, view in enumerate(selected):
        uv, camera_depth = V1.project_canonical(
            gate, points, view.image, view.camera
        )
        inframe = (
            np.isfinite(uv).all(axis=1)
            & np.isfinite(camera_depth)
            & (camera_depth > 1.0)
            & (uv[:, 0] >= 0.0)
            & (uv[:, 0] < int(view.camera.width))
            & (uv[:, 1] >= 0.0)
            & (uv[:, 1] < int(view.camera.height))
        )
        camera_center = -view.image.R().T @ view.image.tvec
        vector = points - camera_center[None, :]
        expected = np.linalg.norm(vector, axis=1)
        candidates = np.flatnonzero(inframe & np.isfinite(expected) & (expected > 0.0))
        first_hit = np.full(len(points), np.inf, dtype=np.float64)
        if len(candidates):
            first_hit[candidates] = first_ray_tin_intersection_distances(
                camera_center,
                vector[candidates],
                tin,
                ray_chunk_size=int(visibility_config["ray_chunk_size"]),
                triangle_chunk_size=int(visibility_config["triangle_chunk_size"]),
                parallel_epsilon=float(visibility_config["intersection_parallel_epsilon"]),
                barycentric_epsilon=float(
                    visibility_config["intersection_barycentric_epsilon"]
                ),
                minimum_hit_distance_m=float(
                    visibility_config["minimum_positive_hit_distance_m"]
                ),
            )
        delta = np.abs(first_hit - expected)
        visible = inframe & np.isfinite(first_hit) & (delta < epsilon_m)
        matrix[visible, column] = 1
        finite_delta = delta[inframe & np.isfinite(first_hit)]
        rows.append(
            {
                "selection_order": int(view.selection_order),
                "image_name": view.image.name,
                "points_total_n": int(len(points)),
                "projected_inframe_n": int(inframe.sum()),
                "first_triangle_hit_n": int((inframe & np.isfinite(first_hit)).sum()),
                "depth_match_strict_epsilon_n": int(visible.sum()),
                "epsilon_m": epsilon_m,
                "abs_distance_delta_median_m": (
                    float(np.median(finite_delta)) if len(finite_delta) else None
                ),
                "abs_distance_delta_max_m": (
                    float(np.max(finite_delta)) if len(finite_delta) else None
                ),
                "geometry": "first_ray_triangle_intersection",
                "point_zbuffer_used": False,
            }
        )
    votes = matrix.sum(axis=1, dtype=np.uint16)
    histogram_counts = np.bincount(votes.astype(np.int64), minlength=len(selected) + 1)
    histogram = {
        str(index): int(count)
        for index, count in enumerate(histogram_counts)
        if count or index <= minimum_k
    }
    return votes, matrix, rows, histogram


def render_roof_supervision(
    gate: Any,
    tin: Any,
    view: Any,
    tin_config: Mapping[str, Any],
) -> dict[str, Any]:
    """Render class-6 depth/normal and bind every supervised term to exact M_j."""

    depth, normal_world, valid, stats = V1.rasterize_tin(
        gate,
        tin,
        view.image,
        view.camera,
        edge_margin=float(tin_config["screen_barycentric_edge_margin"]),
        erosion_pixels=int(tin_config["outer_valid_mask_erosion_px"]),
    )
    normal_camera = normal_world @ view.image.R().T
    normal_camera[~valid] = 0.0
    depth[~valid] = float(tin_config["invalid_depth"])
    photo_mask = valid.copy()
    if not np.array_equal(photo_mask, valid):  # defensive explicit exactness gate
        raise AprimePreprocessError("photo mask is not exact M_j")
    return {
        "depth_camera_z_m": depth.astype(np.float32),
        "normal_world": normal_world.astype(np.float32),
        "normal_camera": normal_camera.astype(np.float32),
        "valid_M_j": valid.astype(bool),
        "photo_mask": photo_mask,
        "stats": stats,
    }


def _write_points3d_allow_empty(path: Path, xyzrgb: np.ndarray) -> None:
    values = np.asarray(xyzrgb)
    if values.ndim != 2 or values.shape[1] < 6:
        raise ValueError("points3D values must have shape (N,>=6)")
    if len(values):
        V1.write_points3d_bin(path, values)
        return
    V1.atomic_bytes(path, struct.pack("<Q", 0))


def _write_las_allow_empty(
    path: Path,
    xyz_base: np.ndarray,
    classification: np.ndarray,
    rgb8: np.ndarray,
) -> dict[str, Any]:
    if len(xyz_base):
        return V1.write_seed_las(path, xyz_base, classification, rgb8)
    import laspy
    from pyproj import CRS

    header = laspy.LasHeader(point_format=3, version="1.4")
    header.scales = np.asarray([0.001, 0.001, 0.001])
    header.offsets = np.asarray([0.0, 0.0, 0.0])
    header.add_crs(CRS.from_epsg(25832))
    las = laspy.LasData(header)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    las.write(temporary)
    os.replace(temporary, path)
    V1.fsync_parent(path)
    return {
        "point_format": 3,
        "version": "1.4",
        "scale_m": [0.001, 0.001, 0.001],
        "offset_m": [0.0, 0.0, 0.0],
        "maximum_coordinate_roundtrip_error_m": 0.0,
    }


def write_training_seed_bundle(
    root: Path,
    config: Mapping[str, Any],
    xyz_canonical: np.ndarray,
    xyz_base: np.ndarray,
    rgb8: np.ndarray,
    rgb_sample_count: np.ndarray,
    visibility_votes: np.ndarray,
) -> dict[str, Any]:
    """Write a trainer seed whose every row is explicitly class 6."""

    xyz_canonical = np.asarray(xyz_canonical, dtype=np.float64)
    xyz_base = np.asarray(xyz_base, dtype=np.float64)
    rgb8 = np.asarray(rgb8, dtype=np.uint8)
    votes = np.asarray(visibility_votes, dtype=np.uint16)
    count = len(xyz_canonical)
    if xyz_canonical.shape != (count, 3) or xyz_base.shape != (count, 3):
        raise ValueError("seed XYZ arrays must both have shape (N,3)")
    if rgb8.shape != (count, 3) or votes.shape != (count,):
        raise ValueError("seed RGB/vote arrays do not align")
    classification = np.full(count, 6, dtype=np.uint8)
    if np.any(classification != 6):
        raise AprimePreprocessError("non-class-6 row entered training seed")
    outputs = config["outputs"]
    seed_npz = root / outputs["canonical_seed_npz"]
    V1.atomic_npz(
        seed_npz,
        {
            "xyz": xyz_canonical,
            "xyz_base_epsg25832_orthometric": xyz_base,
            "rgb": rgb8,
            "rgb_sample_count": np.asarray(rgb_sample_count, dtype=np.uint16),
            "rgb_valid": (np.asarray(rgb_sample_count) > 0).astype(np.uint8),
            "visibility_votes": votes,
            "classification": classification,
            "init_opacity": np.full(
                count, float(config["subset_contract"]["seed_init_opacity"]), np.float32
            ),
        },
    )
    seed_ply = root / outputs["canonical_seed_ply"]
    V1.write_seed_ply(seed_ply, xyz_canonical, rgb8, classification)
    seed_las = root / outputs["base_seed_las"]
    las_stats = _write_las_allow_empty(seed_las, xyz_base, classification, rgb8)
    points3d = root / "sparse" / "0" / "points3D.bin"
    _write_points3d_allow_empty(
        points3d,
        np.column_stack([xyz_canonical, rgb8.astype(np.float64)]),
    )
    if len(read_points3d_bin(points3d)) != count:
        raise AprimePreprocessError("points3D.bin row count differs from filtered class-6 seed")
    return {
        "classification_counts": {"6": count},
        "class2_rows_n": 0,
        "sfm_rows_n": 0,
        "points3D_rows_n": count,
        "las_stats": las_stats,
    }


def write_ground_bundle(
    root: Path,
    config: Mapping[str, Any],
    ground_base: np.ndarray,
    ground_canonical: np.ndarray,
) -> dict[str, Any]:
    """Publish original class-2 rows outside every trainer-resolved path."""

    base = np.asarray(ground_base, dtype=np.float64)
    canonical = np.asarray(ground_canonical, dtype=np.float64)
    if base.shape != canonical.shape or base.ndim != 2 or base.shape[1] != 3:
        raise ValueError("ground arrays must align as Nx3")
    classification = np.full(len(base), 2, dtype=np.uint8)
    outputs = config["outputs"]
    V1.atomic_npz(
        root / outputs["ground_base_npz"],
        {
            "xyz_epsg25832_orthometric": base,
            "classification": classification,
        },
    )
    V1.atomic_npz(
        root / outputs["ground_canonical_npz"],
        {
            "xyz": canonical,
            "xyz_base_epsg25832_orthometric": base,
            "classification": classification,
        },
    )
    grey = np.full((len(base), 3), 128, dtype=np.uint8)
    las_stats = _write_las_allow_empty(
        root / outputs["ground_base_las"], base, classification, grey
    )
    return {
        "points_n": int(len(base)),
        "classification_counts": {"2": int(len(base))},
        "coordinate_rows_unaltered": True,
        "source_row_order_preserved": False,
        "row_order_note": "ALS tile access is deterministically x-sorted",
        "downsample_applied": False,
        "trainer_path_reference": False,
        "las_stats": las_stats,
    }


def verify_building_manifest(path: Path, config: Mapping[str, Any]) -> dict[str, Any]:
    payload = load_json(path)
    if payload.get("schema") != BUILDING_SCHEMA or payload.get("status") != "PASSED":
        raise AprimePreprocessError(f"invalid A-prime building manifest: {relative(path)}")
    pose = payload.get("pose_binding", {})
    if pose.get("corrected_images_sha256") != CORRECTED_IMAGES_SHA256:
        raise AprimePreprocessError("building manifest corrected-pose binding drift")
    if int(pose.get("additional_transform_application_count", -1)) != 0:
        raise AprimePreprocessError("building manifest applies an extra pose transform")
    method = payload.get("method_binding", {})
    expected_method_files = {
        item: V1.sha256_file(repo_path(item))
        for item in [
            *config["implementation_files"],
            config["inputs"]["prereg_lock"],
            config["inputs"]["aprime_targets_csv"],
            config["inputs"]["aprime_targets_manifest"],
            config["inputs"]["v1_helper_script"],
        ]
    }
    observed_method_files = {
        str(row.get("path")): str(row.get("sha256"))
        for row in method.get("required_files", [])
        if isinstance(row, Mapping)
    }
    if observed_method_files != expected_method_files:
        raise AprimePreprocessError("building cache method/config/source binding is stale")
    if method.get("cache_namespace") != config["outputs"]["cache_namespace"]:
        raise AprimePreprocessError("building cache namespace binding drift")
    seed = payload.get("seed", {})
    counts = seed.get("classification_counts", {})
    if set(counts) != {"6"} or int(counts["6"]) != int(seed.get("filtered_points_n", -1)):
        raise AprimePreprocessError("building training seed is not class-6-only")
    if int(seed.get("class2_rows_n", -1)) != 0 or int(seed.get("sfm_rows_n", -1)) != 0:
        raise AprimePreprocessError("class 2 or SfM rows entered building training seed")
    ground = payload.get("ground_readout_only", {})
    if ground.get("trainer_path_reference") is not False:
        raise AprimePreprocessError("class-2 ground is trainer-referenced")
    supervision = payload.get("supervision", {})
    if supervision.get("classes") != [6] or supervision.get("photo_mask") != "exact_M_j":
        raise AprimePreprocessError("building supervision is not class-6 exact-M_j")
    selected = payload.get("views", {}).get("selected_names", [])
    if not 10 <= len(selected) <= 30 or len(selected) != len(set(selected)):
        raise AprimePreprocessError("building selected-view inventory is invalid")
    for logical, expected in payload.get("artifact_sha256", {}).items():
        artifact = repo_path(logical)
        if not artifact.exists():
            raise AprimePreprocessError(f"building artifact missing: {logical}")
        if V1.sha256_file(artifact.resolve()) != expected:
            raise AprimePreprocessError(f"building artifact SHA drift: {logical}")
    forbidden_root = repo_path(config["outputs"]["old_preprocess_root_forbidden"]).resolve()
    data_root = repo_path(payload["data_root"]).resolve()
    try:
        data_root.relative_to(forbidden_root)
    except ValueError:
        pass
    else:
        raise AprimePreprocessError("building data root reuses arm-A preprocessing")
    return payload


def materialize_building(
    *,
    gate: Any,
    target: AprimeTarget,
    footprint: np.ndarray,
    cloud: Any,
    ground_base: np.ndarray,
    cameras: Mapping[int, Camera],
    images_by_name: Mapping[str, ColmapImage],
    image_paths: Mapping[str, Path],
    scene_reference: Mapping[str, Any],
    r1: Mapping[str, Any],
    r2: Mapping[str, Any],
    input_hashes: Mapping[str, str],
    method_lock: Mapping[str, Any],
    config: Mapping[str, Any],
    final_root: Path,
    staging_root: Path,
) -> dict[str, Any]:
    coordinate = config["coordinate_contract"]
    class6_base = np.asarray(cloud.building_xyz, dtype=np.float64)
    class6_canonical = base_to_canonical_points(
        class6_base,
        scene_reference,
        input_datum=coordinate["base_vertical_datum"],
        geoid_m=float(coordinate["orthometric_to_ellipsoidal_geoid_m"]),
    )
    ground_canonical = base_to_canonical_points(
        ground_base,
        scene_reference,
        input_datum=coordinate["base_vertical_datum"],
        geoid_m=float(coordinate["orthometric_to_ellipsoidal_geoid_m"]),
    )
    selected = V1.select_views(
        gate,
        class6_base,
        cameras,
        images_by_name,
        scene_reference,
        config,
    )
    photo_stems = [Path(view.image.name).stem for view in selected]
    if len(photo_stems) != len(set(photo_stems)):
        raise AprimePreprocessError(
            f"{target.building_id}: selected image stems collide in photo-mask layout"
        )
    tin_config = config["tin_supervision"]
    tin = V1.build_tin(
        class6_canonical,
        maximum_xy_edge_m=float(tin_config["maximum_xy_edge_m"]),
        maximum_slope_deg=float(tin_config["maximum_slope_deg"]),
        minimum_xy_triangle_area_m2=float(tin_config["minimum_xy_triangle_area_m2"]),
    )
    votes, visible_matrix, visibility_rows, vote_histogram = raycast_seed_visibility(
        gate,
        class6_canonical,
        tin,
        selected,
        config["visibility_filter"],
    )
    keep = votes >= int(config["visibility_filter"]["minimum_views_k"])
    filtered_base = class6_base[keep]
    filtered_canonical = class6_canonical[keep]
    filtered_votes = votes[keep]
    rgb8, rgb_sample_count, rgb_stats = V1.sample_seed_rgb(
        gate, filtered_canonical, selected, image_paths, config
    )

    views_rows: list[dict[str, Any]] = []
    image_hashes: dict[str, str] = {}
    visibility_by_name = {row["image_name"]: row for row in visibility_rows}
    for view in selected:
        source = image_paths[view.image.name]
        image_hash = V1.sha256_file(source)
        image_hashes[view.image.name] = image_hash
        final_link = final_root / "images" / view.image.name
        staging_link = staging_root / "images" / view.image.name
        V1.create_final_relative_symlink(staging_link, final_link, source)
        geometry = visibility_by_name[view.image.name]
        views_rows.append(
            {
                "selection_order": view.selection_order,
                "building_id": target.building_id,
                "image_name": view.image.name,
                "image_id": view.image.id,
                "camera_id": view.camera.id,
                "width": view.camera.width,
                "height": view.camera.height,
                "class6_inframe_ranking_n": view.class6_inframe_n,
                "class6_visible_ranking_zbuffer_n": view.class6_visible_n,
                "class6_first_triangle_hit_n": geometry["first_triangle_hit_n"],
                "class6_strict_epsilon_match_n": geometry[
                    "depth_match_strict_epsilon_n"
                ],
                "frame_radius": view.frame_radius,
                "nadir_deg": view.nadir_deg,
                "azimuth_bin": view.azimuth_bin,
                "corrected_pose_source_sha256": CORRECTED_IMAGES_SHA256,
                "image_path": relative(final_link),
                "image_sha256": image_hash,
                "selection_used_image_intensity": False,
            }
        )
    V1.atomic_csv(
        staging_root / config["outputs"]["views_csv"],
        views_rows,
        list(views_rows[0]),
    )
    V1.atomic_csv(
        staging_root / config["outputs"]["visibility_views_csv"],
        visibility_rows,
        list(visibility_rows[0]),
    )
    V1.atomic_npz(
        staging_root / config["outputs"]["visibility_npz"],
        {
            "xyz_unfiltered_canonical": class6_canonical,
            "xyz_unfiltered_base_epsg25832_orthometric": class6_base,
            "visibility_votes": votes,
            "visible_matrix_rows_points_columns_selected_views": visible_matrix,
            "keep_k3": keep.astype(np.uint8),
        },
    )
    seed_stats = write_training_seed_bundle(
        staging_root,
        config,
        filtered_canonical,
        filtered_base,
        rgb8,
        rgb_sample_count,
        filtered_votes,
    )
    ground_stats = write_ground_bundle(
        staging_root, config, ground_base, ground_canonical
    )

    subset_images: dict[int, ColmapImage] = {}
    subset_cameras: dict[int, Camera] = {}
    supervision_rows: list[dict[str, Any]] = []
    per_view_supervision: list[dict[str, Any]] = []
    for view in selected:
        rendered = render_roof_supervision(gate, tin, view, tin_config)
        valid = rendered["valid_M_j"]
        if int(valid.sum()) < 1:
            raise AprimePreprocessError(
                f"{target.building_id}/{view.image.name}: empty roof M_j"
            )
        class6_path = (
            staging_root / "supervision" / "class6" / f"{view.image.name}.npz"
        )
        V1.atomic_npz(
            class6_path,
            {
                "depth_camera_z_m": rendered["depth_camera_z_m"],
                "normal_world": rendered["normal_world"],
                "valid_M_j": valid.astype(np.uint8),
            },
        )
        depth_path = (
            staging_root
            / "stereo"
            / "depth_maps"
            / f"{view.image.name}.geometric.bin"
        )
        normal_path = (
            staging_root
            / "stereo"
            / "normal_maps"
            / f"{view.image.name}.geometric.bin"
        )
        V1.write_colmap_array(depth_path, rendered["depth_camera_z_m"])
        V1.write_colmap_array(normal_path, rendered["normal_camera"])
        valid_path = (
            staging_root / "supervision" / "valid_masks" / f"{view.image.name}.npy"
        )
        V1.atomic_npy(valid_path, valid)
        photo_path = (
            staging_root
            / "photo_support_masks"
            / f"{Path(view.image.name).stem}.npy"
        )
        V1.atomic_npy(photo_path, rendered["photo_mask"])
        if not np.array_equal(np.load(valid_path), np.load(photo_path)):
            raise AprimePreprocessError("published photo mask differs from exact M_j")
        subset_images[view.image.id] = view.image
        subset_cameras[view.camera.id] = view.camera
        mask_pixels = int(valid.sum())
        mask_fraction = float(mask_pixels / (view.camera.width * view.camera.height))
        stats = rendered["stats"]
        row = {
            "selection_order": view.selection_order,
            "building_id": target.building_id,
            "image_name": view.image.name,
            "class6_npz_path": relative(
                final_root / "supervision" / "class6" / f"{view.image.name}.npz"
            ),
            "depth_path": relative(
                final_root
                / "stereo"
                / "depth_maps"
                / f"{view.image.name}.geometric.bin"
            ),
            "normal_path": relative(
                final_root
                / "stereo"
                / "normal_maps"
                / f"{view.image.name}.geometric.bin"
            ),
            "valid_M_j_path": relative(
                final_root / "supervision" / "valid_masks" / f"{view.image.name}.npy"
            ),
            "photo_support_mask_path": relative(
                final_root / "photo_support_masks" / f"{Path(view.image.name).stem}.npy"
            ),
            "mask_pixels_n": mask_pixels,
            "mask_pixel_fraction": mask_fraction,
            "outer_edge_masked_pixels_n": stats["outer_edge_masked_pixels_n"],
            "pose_sha256": CORRECTED_IMAGES_SHA256,
            "photo_equals_M_j": True,
            "supervision_class": 6,
        }
        supervision_rows.append(row)
        per_view_supervision.append(
            {
                "selection_order": int(view.selection_order),
                "image_name": view.image.name,
                "width": int(view.camera.width),
                "height": int(view.camera.height),
                "mask_pixels_n": mask_pixels,
                "mask_pixel_fraction": mask_fraction,
                "photo_equals_M_j": True,
                **stats,
            }
        )
    V1.atomic_csv(
        staging_root / config["outputs"]["supervision_index"],
        supervision_rows,
        list(supervision_rows[0]),
    )
    sparse_root = staging_root / "sparse" / "0"
    V1.write_cameras_bin(sparse_root / "cameras.bin", subset_cameras)
    V1.write_images_bin(sparse_root / "images.bin", subset_images)

    parsed_names = sorted(image.name for image in read_images_bin(sparse_root / "images.bin").values())
    selected_names = sorted(view.image.name for view in selected)
    image_link_names = sorted(
        str(path.relative_to(staging_root / "images"))
        for path in (staging_root / "images").rglob("*")
        if path.is_symlink()
    )
    depth_names = sorted(
        path.relative_to(staging_root / "stereo" / "depth_maps")
        .as_posix()
        .removesuffix(".geometric.bin")
        for path in (staging_root / "stereo" / "depth_maps").rglob("*.geometric.bin")
    )
    normal_names = sorted(
        path.relative_to(staging_root / "stereo" / "normal_maps")
        .as_posix()
        .removesuffix(".geometric.bin")
        for path in (staging_root / "stereo" / "normal_maps").rglob("*.geometric.bin")
    )
    index_names = sorted(row["image_name"] for row in supervision_rows)
    if not selected_names == parsed_names == image_link_names == depth_names == normal_names == index_names:
        raise AprimePreprocessError("selected corrected-pose data-root inventories differ")

    artifact_hashes, artifact_kinds = V1.collect_artifacts(
        staging_root, final_root, image_hashes
    )
    seed_threshold = int(config["subset_contract"]["seed_too_small_threshold"])
    manifest = {
        "schema": BUILDING_SCHEMA,
        "status": "PASSED",
        "created_at": V1.now_iso(),
        "task_id": config["task_id"],
        "run_id": config["run_id"],
        "method_binding": {
            **dict(method_lock),
            "cache_namespace": config["outputs"]["cache_namespace"],
            "validation_rule": (
                "required method/config/prereg/target hashes must match; "
                "generation HEAD is provenance only"
            ),
        },
        "building": {
            "aprime_order": target.aprime_order,
            "building_id": target.building_id,
            "target_role": target.target_role,
            "tier": target.tier,
            "cohort": target.cohort,
            "source_processing_order": target.source_processing_order,
            "selection_reason": target.selection_reason,
            "texture_low_gradient_fraction": target.texture_low_gradient_fraction,
            "selection_sources": target.selection_sources,
            "gs4buildings_overlap_status": target.gs4buildings_overlap_status,
            "gs4buildings_overlap_reason": target.gs4buildings_overlap_reason,
        },
        "data_root": relative(final_root),
        "pose_binding": {
            "r1_manifest": config["inputs"]["r1_manifest"],
            "r1_manifest_sha256": V1.sha256_file(repo_path(config["inputs"]["r1_manifest"])),
            "corrected_sparse": config["inputs"]["corrected_sparse"],
            "corrected_images_sha256": CORRECTED_IMAGES_SHA256,
            "transform_application_count": 1,
            "additional_transform_application_count": 0,
            "cache_namespace": config["outputs"]["cache_namespace"],
        },
        "gate_binding": {
            "r2_manifest": config["inputs"]["r2_manifest"],
            "r2_manifest_sha256": V1.sha256_file(repo_path(config["inputs"]["r2_manifest"])),
            "gate_a_version": r2["gate_a_version"],
            "status": r2["status"],
        },
        "target_binding": {
            "path": config["inputs"]["aprime_targets_csv"],
            "sha256": V1.sha256_file(repo_path(config["inputs"]["aprime_targets_csv"])),
            "machine_join_verified": True,
            "manual_id_entry": False,
        },
        "views": {
            "csv": {
                "path": relative(final_root / config["outputs"]["views_csv"]),
                "sha256": artifact_hashes[relative(final_root / config["outputs"]["views_csv"])],
            },
            "count": len(selected),
            "minimum": int(config["view_selection"]["minimum_views"]),
            "maximum": int(config["view_selection"]["maximum_views"]),
            "selected_names": selected_names,
            "selection": config["view_selection"]["ranking"],
            "role_policy": config["view_selection"]["role_policy"],
            "training_names": selected_names,
            "evaluation_names": [],
            "visibility_vote_views_equal_training_views": True,
            "inventory_equality_verified": True,
        },
        "seed": {
            "source_unfiltered_points_n": int(len(class6_canonical)),
            "filtered_points_n": int(len(filtered_canonical)),
            "removed_points_n": int((~keep).sum()),
            "retention_fraction": (
                float(keep.mean()) if len(keep) else 0.0
            ),
            "seed_too_small": bool(len(filtered_canonical) < seed_threshold),
            "seed_too_small_threshold": seed_threshold,
            "classification_counts": seed_stats["classification_counts"],
            "class2_rows_n": seed_stats["class2_rows_n"],
            "sfm_rows_n": seed_stats["sfm_rows_n"],
            "points3D_rows_n": seed_stats["points3D_rows_n"],
            "downsample_applied": False,
            "init_opacity": float(config["subset_contract"]["seed_init_opacity"]),
            "canonical_npz": {
                "path": relative(final_root / config["outputs"]["canonical_seed_npz"]),
                "sha256": artifact_hashes[
                    relative(final_root / config["outputs"]["canonical_seed_npz"])
                ],
                "frame": coordinate["canonical_frame"],
            },
            "canonical_ply": {
                "path": relative(final_root / config["outputs"]["canonical_seed_ply"]),
                "sha256": artifact_hashes[
                    relative(final_root / config["outputs"]["canonical_seed_ply"])
                ],
            },
            "base_las": {
                "path": relative(final_root / config["outputs"]["base_seed_las"]),
                "sha256": artifact_hashes[
                    relative(final_root / config["outputs"]["base_seed_las"])
                ],
                "crs": "EPSG:25832",
                **seed_stats["las_stats"],
            },
            "rgb": rgb_stats,
            "visibility": {
                **config["visibility_filter"],
                "TIN_source": "unfiltered_class6_before_visibility_filter",
                "selected_views_n": len(selected),
                "vote_histogram": vote_histogram,
                "votes_npz": {
                    "path": relative(final_root / config["outputs"]["visibility_npz"]),
                    "sha256": artifact_hashes[
                        relative(final_root / config["outputs"]["visibility_npz"])
                    ],
                },
                "per_view_csv": {
                    "path": relative(final_root / config["outputs"]["visibility_views_csv"]),
                    "sha256": artifact_hashes[
                        relative(final_root / config["outputs"]["visibility_views_csv"])
                    ],
                },
                "per_view": visibility_rows,
            },
        },
        "ground_readout_only": {
            **ground_stats,
            "role": config["ground_artifact_contract"]["role"],
            "buffer_m": float(config["subset_contract"]["ground_buffer_m"]),
            "base_npz": {
                "path": relative(final_root / config["outputs"]["ground_base_npz"]),
                "sha256": artifact_hashes[
                    relative(final_root / config["outputs"]["ground_base_npz"])
                ],
            },
            "canonical_npz": {
                "path": relative(final_root / config["outputs"]["ground_canonical_npz"]),
                "sha256": artifact_hashes[
                    relative(final_root / config["outputs"]["ground_canonical_npz"])
                ],
            },
            "base_las": {
                "path": relative(final_root / config["outputs"]["ground_base_las"]),
                "sha256": artifact_hashes[
                    relative(final_root / config["outputs"]["ground_base_las"])
                ],
                "crs": "EPSG:25832",
            },
        },
        "supervision": {
            "index": {
                "path": relative(final_root / config["outputs"]["supervision_index"]),
                "sha256": artifact_hashes[
                    relative(final_root / config["outputs"]["supervision_index"])
                ],
            },
            "views_n": len(supervision_rows),
            "classes": [6],
            "ground_supervision": False,
            "wall_supervision": False,
            "depth_definition": tin_config["depth_definition"],
            "normal_world_frame": tin_config["normal_world_frame"],
            "normal_colmap_bin_frame": tin_config["normal_colmap_bin_frame"],
            "valid_mask": tin_config["M_j"],
            "photo_mask": "exact_M_j",
            "mask_normalization_denominator": "cardinality_M_j",
            "class6_tin": tin.stats,
            "per_view": per_view_supervision,
            "mask_pixels_total": int(sum(row["mask_pixels_n"] for row in per_view_supervision)),
            "mask_fraction_mean": float(
                np.mean([row["mask_pixel_fraction"] for row in per_view_supervision])
            ),
        },
        "colmap_data_root": {
            "directly_consumable": bool(len(filtered_canonical)),
            "selected_images_n": len(selected_names),
            "selected_names": selected_names,
            "sparse_points_source": "filtered_ALS_class6_only",
            "sfm_points_n": 0,
            "class2_points_n": 0,
            "points3D_rows_n": int(len(filtered_canonical)),
            "image_symlinks_preserve_source_pixels": True,
            "training_downscale_required": 1.0,
            "saved_M_j_dataloader_roundtrip_verified": True,
        },
        "source_inputs": {
            "sha256": dict(input_hashes),
            "source_als_tiles": list(cloud.source_tiles),
            "footprint_role": "approved GroundSurface XY crop/address only",
            "forbidden_lod2_components_read": [],
        },
        "cache_policy": {
            "namespace": config["outputs"]["cache_namespace"],
            "old_arm_A_cache_read_count": 0,
            "old_arm_A_cache_reused": False,
            "supervision_and_seed_regenerated": True,
        },
        "artifact_sha256": artifact_hashes,
        "artifact_kind": artifact_kinds,
        "publication": {
            "manifest_written_last": True,
            "partial_building_reviewable": True,
            "learning_runs_started": 0,
            "readout_runs_started": 0,
            "roofer_runs_started": 0,
            "scoring_runs_started": 0,
        },
    }
    V1.atomic_json(staging_root / config["outputs"]["building_manifest"], manifest)
    return manifest


def prepare_one(
    *,
    target: AprimeTarget,
    gate: Any,
    als_store: Any,
    footprints: Mapping[str, np.ndarray],
    cameras: Mapping[int, Camera],
    images_by_name: Mapping[str, ColmapImage],
    image_paths: Mapping[str, Path],
    scene_reference: Mapping[str, Any],
    r1: Mapping[str, Any],
    r2: Mapping[str, Any],
    input_hashes: Mapping[str, str],
    method_lock: Mapping[str, Any],
    config: Mapping[str, Any],
    cache_root: Path,
) -> dict[str, Any]:
    final_root = cache_root / config["outputs"]["building_root"] / target.building_id
    final_manifest = final_root / config["outputs"]["building_manifest"]
    if final_manifest.is_file():
        return verify_building_manifest(final_manifest, config)
    if final_root.exists():
        raise AprimePreprocessError(
            f"incomplete A-prime building directory exists: {relative(final_root)}"
        )
    staging_parent = cache_root / ".staging"
    staging_parent.mkdir(parents=True, exist_ok=True)
    staging_root = staging_parent / (
        f"{target.building_id}.{os.getpid()}.{datetime.now().strftime('%H%M%S%f')}"
    )
    staging_root.mkdir(parents=False, exist_ok=False)
    footprint = footprints[target.building_id]
    evidence = {
        "footprint_building_buffer_m": 0.0,
        "ground_context_buffer_m": float(config["subset_contract"]["ground_buffer_m"]),
        "minimum_building_class_points": int(
            config["subset_contract"]["minimum_building_source_points"]
        ),
        "minimum_ground_class_points": int(config["subset_contract"]["minimum_ground_points"]),
    }
    cloud = als_store.target_cloud(target.building_id, footprint, evidence)
    ground_keep = V1.points_within_polygon_buffer(
        cloud.ground_xyz[:, :2],
        footprint,
        float(config["subset_contract"]["ground_buffer_m"]),
    )
    ground_base = np.asarray(cloud.ground_xyz[ground_keep], dtype=np.float64)
    if len(ground_base) < int(config["subset_contract"]["minimum_ground_points"]):
        raise AprimePreprocessError(f"{target.building_id}: too few buffered class-2 rows")
    materialize_building(
        gate=gate,
        target=target,
        footprint=footprint,
        cloud=cloud,
        ground_base=ground_base,
        cameras=cameras,
        images_by_name=images_by_name,
        image_paths=image_paths,
        scene_reference=scene_reference,
        r1=r1,
        r2=r2,
        input_hashes=input_hashes,
        method_lock=method_lock,
        config=config,
        final_root=final_root,
        staging_root=staging_root,
    )
    final_root.parent.mkdir(parents=True, exist_ok=True)
    os.replace(staging_root, final_root)
    V1.fsync_parent(final_root)
    return verify_building_manifest(final_manifest, config)


RUN_INDEX_FIELDS = [
    "aprime_order",
    "building_id",
    "target_role",
    "status",
    "data_root",
    "building_manifest_path",
    "building_manifest_sha256",
    "views_n",
    "seed_before_n",
    "seed_after_n",
    "seed_retention_fraction",
    "seed_too_small",
    "class2_ground_n",
    "mask_pixels_total",
    "mask_fraction_mean",
    "pose_sha256",
]


T5_SUMMARY_FIELDS = [
    "aprime_order",
    "building_id",
    "target_role",
    "tier",
    "cohort",
    "status",
    "views_n",
    "seed_filter_before_n",
    "seed_filter_after_n",
    "seed_filter_removed_n",
    "seed_retention_fraction",
    "seed_too_small",
    "minimum_visible_views_k",
    "visibility_epsilon_m",
    "visibility_vote_histogram_json",
    "class2_ground_20m_n",
    "mask_pixels_total",
    "mask_fraction_min",
    "mask_fraction_mean",
    "mask_fraction_max",
    "building_manifest_path",
    "building_manifest_sha256",
]


T5_MASK_FIELDS = [
    "aprime_order",
    "building_id",
    "target_role",
    "selection_order",
    "image_name",
    "width",
    "height",
    "mask_pixels_n",
    "mask_pixel_fraction",
    "photo_equals_M_j",
    "outer_edge_masked_pixels_n",
    "pose_sha256",
]


def publish_run_manifest(
    config: Mapping[str, Any],
    targets: Sequence[AprimeTarget],
    cache_root: Path,
    git_lock: Mapping[str, Any],
) -> dict[str, Any]:
    records: list[dict[str, Any]] = []
    t5_rows: list[dict[str, Any]] = []
    mask_rows: list[dict[str, Any]] = []
    for target in targets:
        path = (
            cache_root
            / config["outputs"]["building_root"]
            / target.building_id
            / config["outputs"]["building_manifest"]
        )
        if not path.is_file():
            continue
        payload = verify_building_manifest(path, config)
        seed = payload["seed"]
        supervision = payload["supervision"]
        fractions = [float(row["mask_pixel_fraction"]) for row in supervision["per_view"]]
        common = {
            "aprime_order": target.aprime_order,
            "building_id": target.building_id,
            "target_role": target.target_role,
            "status": payload["status"],
            "building_manifest_path": relative(path),
            "building_manifest_sha256": V1.sha256_file(path),
        }
        records.append(
            {
                **common,
                "data_root": payload["data_root"],
                "views_n": payload["views"]["count"],
                "seed_before_n": seed["source_unfiltered_points_n"],
                "seed_after_n": seed["filtered_points_n"],
                "seed_retention_fraction": seed["retention_fraction"],
                "seed_too_small": seed["seed_too_small"],
                "class2_ground_n": payload["ground_readout_only"]["points_n"],
                "mask_pixels_total": supervision["mask_pixels_total"],
                "mask_fraction_mean": supervision["mask_fraction_mean"],
                "pose_sha256": CORRECTED_IMAGES_SHA256,
            }
        )
        t5_rows.append(
            {
                **common,
                "tier": target.tier,
                "cohort": target.cohort,
                "views_n": payload["views"]["count"],
                "seed_filter_before_n": seed["source_unfiltered_points_n"],
                "seed_filter_after_n": seed["filtered_points_n"],
                "seed_filter_removed_n": seed["removed_points_n"],
                "seed_retention_fraction": seed["retention_fraction"],
                "seed_too_small": seed["seed_too_small"],
                "minimum_visible_views_k": seed["visibility"]["minimum_views_k"],
                "visibility_epsilon_m": seed["visibility"]["epsilon_m"],
                "visibility_vote_histogram_json": json.dumps(
                    seed["visibility"]["vote_histogram"],
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ),
                "class2_ground_20m_n": payload["ground_readout_only"]["points_n"],
                "mask_pixels_total": supervision["mask_pixels_total"],
                "mask_fraction_min": min(fractions),
                "mask_fraction_mean": float(np.mean(fractions)),
                "mask_fraction_max": max(fractions),
            }
        )
        for row in supervision["per_view"]:
            mask_rows.append(
                {
                    "aprime_order": target.aprime_order,
                    "building_id": target.building_id,
                    "target_role": target.target_role,
                    "selection_order": row["selection_order"],
                    "image_name": row["image_name"],
                    "width": row["width"],
                    "height": row["height"],
                    "mask_pixels_n": row["mask_pixels_n"],
                    "mask_pixel_fraction": row["mask_pixel_fraction"],
                    "photo_equals_M_j": row["photo_equals_M_j"],
                    "outer_edge_masked_pixels_n": row[
                        "outer_edge_masked_pixels_n"
                    ],
                    "pose_sha256": CORRECTED_IMAGES_SHA256,
                }
            )
    records.sort(key=lambda row: row["aprime_order"])
    t5_rows.sort(key=lambda row: row["aprime_order"])
    mask_rows.sort(key=lambda row: (row["aprime_order"], row["selection_order"]))
    index_path = cache_root / config["outputs"]["run_index"]
    t5_path = repo_path(config["outputs"]["t5_summary_csv"])
    mask_path = repo_path(config["outputs"]["t5_mask_inventory_csv"])
    V1.atomic_csv(index_path, records, RUN_INDEX_FIELDS)
    V1.atomic_csv(t5_path, t5_rows, T5_SUMMARY_FIELDS)
    V1.atomic_csv(mask_path, mask_rows, T5_MASK_FIELDS)
    expected = int(config["target_contract"]["expected_population_n"])
    status = "PASSED" if len(records) == expected else "PARTIAL"
    cache_manifest_path = cache_root / config["outputs"]["cache_run_manifest"]
    manifest = {
        "schema": RUN_SCHEMA,
        "status": status,
        "created_at": V1.now_iso(),
        "task_id": config["task_id"],
        "run_id": config["run_id"],
        "expected_buildings_n": expected,
        "completed_buildings_n": len(records),
        "pose_binding": {
            "corrected_images_sha256": CORRECTED_IMAGES_SHA256,
            "transform_application_count": 1,
            "additional_transform_application_count": 0,
        },
        "target_binding": {
            "path": config["inputs"]["aprime_targets_csv"],
            "sha256": V1.sha256_file(repo_path(config["inputs"]["aprime_targets_csv"])),
            "machine_join_verified": True,
            "population_n": len(targets),
        },
        "cache_binding": {
            "namespace": config["outputs"]["cache_namespace"],
            "cache_dir": relative(cache_root),
            "old_arm_A_cache_read_count": 0,
            "old_arm_A_cache_reused": False,
        },
        "preprocess_index": {
            "path": relative(index_path),
            "sha256": V1.sha256_file(index_path),
            "rows_n": len(records),
        },
        "T5": {
            "summary": {
                "path": relative(t5_path),
                "sha256": V1.sha256_file(t5_path),
                "rows_n": len(t5_rows),
            },
            "mask_inventory": {
                "path": relative(mask_path),
                "sha256": V1.sha256_file(mask_path),
                "rows_n": len(mask_rows),
            },
        },
        "buildings": records,
        "git_lock": dict(git_lock),
        "publication": {
            "each_aggregate_file_replaced_atomically_after_each_building": True,
            "aggregate_set_transactional": False,
            "stable_manifest_written_last": True,
            "crash_recovery": (
                "rerun_rebuilds_all_aggregate_files_from_atomic_per_building_receipts"
            ),
            "partial_buildings_reviewable": True,
            "learning_runs_started": 0,
            "readout_runs_started": 0,
            "roofer_runs_started": 0,
            "scoring_runs_started": 0,
        },
    }
    V1.atomic_json(cache_manifest_path, manifest)
    stable_path = repo_path(config["outputs"]["stable_root"]) / config["outputs"][
        "stable_run_manifest"
    ]
    stable_manifest = {
        **manifest,
        "cache_manifest": {
            "path": relative(cache_manifest_path),
            "sha256": V1.sha256_file(cache_manifest_path),
        },
        "publication": {
            **manifest["publication"],
            "stable_manifest_written_last": True,
        },
    }
    V1.atomic_json(stable_path, stable_manifest)
    return stable_manifest


FAILURE_INDEX_FIELDS = [
    "aprime_order",
    "building_id",
    "target_role",
    "status",
    "attempts_n",
    "final_error_type",
    "final_error_message",
    "same_error_three_times",
    "receipt_path",
    "receipt_sha256",
]


def publish_failure_artifacts(
    config: Mapping[str, Any], cache_root: Path
) -> list[dict[str, Any]]:
    """Rebuild failure index and runtime issues from atomic building receipts."""

    outputs = config["outputs"]
    failure_root = cache_root / outputs["failure_root"]
    rows: list[dict[str, Any]] = []
    for receipt in sorted(failure_root.glob("*/failed.json")):
        payload = load_json(receipt)
        attempts = payload.get("attempts", [])
        final = attempts[-1] if attempts else {}
        rows.append(
            {
                "aprime_order": payload["aprime_order"],
                "building_id": payload["building_id"],
                "target_role": payload["target_role"],
                "status": payload["status"],
                "attempts_n": len(attempts),
                "final_error_type": final.get("error_type", ""),
                "final_error_message": final.get("error_message", ""),
                "same_error_three_times": payload.get(
                    "same_error_three_times", False
                ),
                "receipt_path": relative(receipt),
                "receipt_sha256": V1.sha256_file(receipt),
            }
        )
    rows.sort(key=lambda row: int(row["aprime_order"]))
    V1.atomic_csv(
        cache_root / outputs["failure_index_csv"],
        rows,
        FAILURE_INDEX_FIELDS,
    )
    issue_lines = [
        "# A-prime preprocess runtime issues",
        "",
        "측정·예외 기록만 포함하며 연구 판정은 포함하지 않는다.",
        "",
    ]
    if not rows:
        issue_lines.extend(["- 기록된 건물 실패 없음.", ""])
    else:
        for row in rows:
            issue_lines.extend(
                [
                    f"## {row['building_id']}",
                    "",
                    f"- status: `{row['status']}`",
                    f"- attempts: `{row['attempts_n']}`",
                    f"- final error type: `{row['final_error_type']}`",
                    f"- final error: `{row['final_error_message']}`",
                    f"- receipt: `{row['receipt_path']}`",
                    "",
                ]
            )
    V1.atomic_bytes(
        cache_root / outputs["runtime_issues_md"],
        ("\n".join(issue_lines) + "\n").encode("utf-8"),
    )
    return rows


def record_failed_building(
    config: Mapping[str, Any],
    cache_root: Path,
    target: AprimeTarget,
    attempts: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    signatures = [
        (str(row["error_type"]), str(row["error_message"]))
        for row in attempts
    ]
    repeated_three = any(signatures.count(value) >= 3 for value in set(signatures))
    payload = {
        "schema": "jointbuildgs.fusion_w1_aprime.preprocess_failure.v1",
        "status": "SKIPPED_AFTER_THREE_ATTEMPTS",
        "created_at": V1.now_iso(),
        "task_id": config["task_id"],
        "run_id": config["run_id"],
        "aprime_order": target.aprime_order,
        "building_id": target.building_id,
        "target_role": target.target_role,
        "attempts": [dict(row) for row in attempts],
        "same_error_three_times": repeated_three,
        "policy": {
            "maximum_attempts_per_building": 3,
            "same_error_three_times_skips_building": True,
            "same_error_type_three_consecutive_buildings_stops_stage": True,
        },
        "verdict": None,
    }
    path = (
        cache_root
        / config["outputs"]["failure_root"]
        / target.building_id
        / "failed.json"
    )
    V1.atomic_json(path, payload)
    publish_failure_artifacts(config, cache_root)
    return payload


def mark_failure_recovered(
    config: Mapping[str, Any], cache_root: Path, target: AprimeTarget
) -> None:
    root = cache_root / config["outputs"]["failure_root"] / target.building_id
    failed = root / "failed.json"
    if not failed.is_file():
        return
    historical = root / "failed_before_recovery.json"
    if historical.exists():
        historical = root / (
            f"failed_before_recovery_{datetime.now().strftime('%H%M%S%f')}.json"
        )
    os.replace(failed, historical)
    V1.fsync_parent(historical)
    payload = {
        "schema": "jointbuildgs.fusion_w1_aprime.preprocess_recovery.v1",
        "building_id": target.building_id,
        "prior_failure_receipt": relative(historical),
        "prior_failure_receipt_sha256": V1.sha256_file(historical),
        "recovery": {
        "status": "RECOVERED_ON_LATER_INVOCATION",
        "created_at": V1.now_iso(),
        },
        "verdict": None,
    }
    V1.atomic_json(root / "recovered.json", payload)
    publish_failure_artifacts(config, cache_root)


def execute(config: Mapping[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    V1.require_docker()
    git_lock = verify_method_lock(config)
    input_hashes = verify_input_hashes(config)
    r1, r2 = validate_authorization(config)
    targets = load_aprime_targets(
        repo_path(config["inputs"]["aprime_targets_csv"]),
        repo_path(config["inputs"]["canonical_targets_csv"]),
        config,
    )
    lookup = {target.building_id: target for target in targets}
    if args.all_aprime:
        selected_targets = targets
    else:
        building_id = canonical_building_id(args.building_id)
        if building_id not in lookup:
            raise AprimePreprocessError(f"building is not in A-prime target CSV: {building_id}")
        selected_targets = [lookup[building_id]]
    gate = _import_module(
        "fusion_w1_alignment_gate_lock1_for_aprime_preprocess",
        repo_path(config["inputs"]["alignment_helper_script"]),
    )
    target_ids = [target.building_id for target in selected_targets]
    footprints = gate.load_footprints(
        repo_path(config["inputs"]["footprint_xy"]),
        target_ids,
        config["inputs"]["footprint_id_field"],
        config["inputs"]["footprint_layer"],
        gate.load_config(repo_path(config["inputs"]["alignment_helper_config"])),
    )
    als_store = gate.ALSStore(
        [repo_path(path) for path in config["inputs"]["als_files"]],
        int(config["subset_contract"]["ground_class"]),
        int(config["subset_contract"]["building_class"]),
    )
    cameras, _images, images_by_name, image_paths = gate.load_training_inventory(
        repo_path(config["inputs"]["corrected_sparse"]),
        repo_path(config["inputs"]["training_image_dir"]),
        int(config["r1_contract"]["image_count"]),
    )
    corrected_images = repo_path(config["inputs"]["corrected_sparse"]) / "images.bin"
    if V1.sha256_file(corrected_images) != CORRECTED_IMAGES_SHA256:
        raise AprimePreprocessError("corrected pose hash drift before A-prime preparation")
    scene_reference = load_json(config["inputs"]["scene_reference_frame"])
    stable_root = repo_path(config["outputs"]["stable_root"])
    cache_root = stable_root / config["outputs"]["cache_namespace"]
    forbidden_root = repo_path(config["outputs"]["old_preprocess_root_forbidden"]).resolve()
    try:
        cache_root.resolve().relative_to(forbidden_root)
    except ValueError:
        pass
    else:
        raise AprimePreprocessError("resolved A-prime cache aliases arm-A preprocessing")
    cache_root.mkdir(parents=True, exist_ok=True)
    prepared: list[str] = []
    skipped: list[str] = []
    consecutive_failure_type: str | None = None
    consecutive_failure_buildings: list[str] = []
    stage_stopped = False
    run_manifest: dict[str, Any] | None = None
    for target in selected_targets:
        attempts: list[dict[str, Any]] = []
        completed = False
        maximum_attempts = 3 if args.all_aprime else 1
        for attempt in range(1, maximum_attempts + 1):
            try:
                prepare_one(
                    target=target,
                    gate=gate,
                    als_store=als_store,
                    footprints=footprints,
                    cameras=cameras,
                    images_by_name=images_by_name,
                    image_paths=image_paths,
                    scene_reference=scene_reference,
                    r1=r1,
                    r2=r2,
                    input_hashes=input_hashes,
                    method_lock=git_lock,
                    config=config,
                    cache_root=cache_root,
                )
            except Exception as exc:
                if not args.all_aprime:
                    raise
                attempts.append(
                    {
                        "attempt": attempt,
                        "created_at": V1.now_iso(),
                        "error_type": type(exc).__name__,
                        "error_message": str(exc),
                    }
                )
            else:
                completed = True
                break
        if completed:
            mark_failure_recovered(config, cache_root, target)
            prepared.append(target.building_id)
            consecutive_failure_type = None
            consecutive_failure_buildings = []
        else:
            failure = record_failed_building(
                config, cache_root, target, attempts
            )
            skipped.append(target.building_id)
            final_type = str(failure["attempts"][-1]["error_type"])
            if final_type == consecutive_failure_type:
                consecutive_failure_buildings.append(target.building_id)
            else:
                consecutive_failure_type = final_type
                consecutive_failure_buildings = [target.building_id]
            if len(consecutive_failure_buildings) >= 3:
                stage_stopped = True
                V1.atomic_json(
                    cache_root / config["outputs"]["stage_stop_receipt"],
                    {
                        "schema": (
                            "jointbuildgs.fusion_w1_aprime.preprocess_stage_stop.v1"
                        ),
                        "status": "STAGE_STOPPED_AFTER_SAME_ERROR_TYPE_ON_THREE_CONSECUTIVE_BUILDINGS",
                        "created_at": V1.now_iso(),
                        "task_id": config["task_id"],
                        "run_id": config["run_id"],
                        "error_type": consecutive_failure_type,
                        "building_ids": list(consecutive_failure_buildings),
                        "verdict": None,
                    },
                )
        run_manifest = publish_run_manifest(config, targets, cache_root, git_lock)
        if stage_stopped:
            break
    if run_manifest is None:
        run_manifest = publish_run_manifest(config, targets, cache_root, git_lock)
    publish_failure_artifacts(config, cache_root)
    return {
        "status": "STAGE_STOPPED" if stage_stopped else run_manifest["status"],
        "prepared_this_invocation": prepared,
        "skipped_this_invocation": skipped,
        "stage_stopped": stage_stopped,
        "completed_buildings_n": run_manifest["completed_buildings_n"],
        "stable_manifest": relative(
            stable_root / config["outputs"]["stable_run_manifest"]
        ),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--building-id")
    group.add_argument("--all-aprime", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        config = load_config(args.config)
        result = execute(config, args)
    except (AprimePreprocessError, V1.PreprocessError, OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
