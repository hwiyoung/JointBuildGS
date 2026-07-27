#!/usr/bin/env python3
"""Publish one measured A-prime job as one high-resolution review panel.

The panel keeps the input-to-assembly flow in one PNG and adds four locked
3D views for both the filtered TSDF mesh and the canonical Roofer CityJSON
LoD2.2 solid.  Reference GML is opened only for the final evaluation-only
overlay.  Scientific interpretation and verdict fields remain null.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import os
import shutil
import sqlite3
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import colors as mpl_colors
from matplotlib import font_manager, patches
from matplotlib.path import Path as MplPath
from mpl_toolkits.mplot3d.art3d import Poly3DCollection
import numpy as np
from PIL import Image

_REPO_IMPORT_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_IMPORT_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_IMPORT_ROOT))
from src.stage2.colmap_io import read_cameras_bin, read_images_bin


REPO = Path(__file__).resolve().parents[3]
DEFAULT_CONFIG = (
    REPO
    / "phases/p2-gsjso/configs/fusion_w1_aprime_job_panel_v4_20260727.json"
)
BASE_RENDERER = (
    REPO
    / "phases/p2-gsjso/scripts/fusion_w1_aprime_job_qualitative_v3_20260727.py"
)
CONFIG_SCHEMA = "jointbuildgs.fusion_w1_aprime.job_panel.config.v4"
RECEIPT_SCHEMA = "jointbuildgs.fusion_w1_aprime.job_panel.complete.v4"


def load_module(path: Path, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot import {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


base = load_module(BASE_RENDERER, "fusion_w1_aprime_job_qualitative_v3_for_panel_v4")
PanelError = base.JobQualitativeError


def require(condition: bool, message: str) -> None:
    if not condition:
        raise PanelError(message)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_panel_config(path: Path = DEFAULT_CONFIG) -> tuple[dict[str, Any], dict[str, Any]]:
    config = base.load_json(path)
    require(config.get("schema") == CONFIG_SCHEMA, "panel v4 config schema drift")
    require(config.get("run_id") == "20260726_fusion_w1_aprime", "run ID drift")
    require(config.get("branch") == "exp/fusion-w1", "branch drift")
    base_contract = config.get("base_contract", {})
    require(
        base_contract.get("config")
        == "phases/p2-gsjso/configs/fusion_w1_aprime_job_qualitative_v3_20260727.json",
        "base config path drift",
    )
    require(
        base_contract.get("renderer")
        == "phases/p2-gsjso/scripts/fusion_w1_aprime_job_qualitative_v3_20260727.py",
        "base renderer path drift",
    )
    implementation = config.get("implementation_files")
    expected_implementation = [
        "phases/p2-gsjso/configs/fusion_w1_aprime_job_panel_v4_20260727.json",
        "phases/p2-gsjso/scripts/fusion_w1_aprime_job_panel_v4_20260727.py",
        "phases/p2-gsjso/scripts/run_fusion_w1_aprime_job_panel_v4_20260727.sh",
        "phases/p2-gsjso/scripts/test_fusion_w1_aprime_job_panel_v4_20260727.py",
        str(base_contract["config"]),
        str(base_contract["renderer"]),
        "src/stage2/colmap_io.py",
    ]
    require(
        implementation == expected_implementation,
        "implementation dependency closure drift",
    )
    for value in implementation:
        require(not Path(str(value)).is_absolute(), "implementation path must be relative")
        require(base.repo_path(str(value)).is_file(), f"implementation absent: {value}")

    visual = config.get("visual_contract", {})
    require(visual.get("rows") == 5 and visual.get("columns") == 5, "panel grid drift")
    require(visual.get("single_visual_file") is True, "single-file panel contract drift")
    require(visual.get("placeholders_allowed_for_measured") is False, "placeholder policy drift")
    require(
        visual.get("camera_contract", {}).get("projection") == "orthographic",
        "projection contract drift",
    )
    require(
        float(visual["camera_contract"].get("z_exaggeration", 0.0)) == 1.0,
        "Z exaggeration must be 1.0",
    )
    views = visual["camera_contract"].get("views")
    require(
        isinstance(views, list)
        and [item.get("key") for item in views]
        == ["top", "oblique_a", "oblique_b", "principal_side"],
        "camera view order drift",
    )
    outputs = config.get("outputs", {})
    require(
        outputs.get("root")
        == "phases/p2-gsjso/runs/20260726_fusion_w1_aprime/review_v4",
        "review v4 root drift",
    )
    publication = config.get("publication", {})
    require(publication.get("one_visual_panel_per_job") is True, "one-panel policy drift")
    require(publication.get("overwrite_allowed") is False, "overwrite policy drift")
    require(publication.get("scientific_verdict") is None, "scientific verdict must be null")
    require(publication.get("interpretation") is None, "interpretation must be null")
    execution = config.get("execution", {})
    require(execution.get("network") == "none", "network contract drift")
    require(execution.get("gpus_required") is False, "panel renderer must be CPU-only")
    require(execution.get("nonroot") is True, "panel renderer must be nonroot")

    locator = config.get("input_locator_contract", {})
    require(
        locator.get("footprint_role")
        == "approved GroundSurface XY target locator only; no reference Z, roof faces, roof type, semantics, or final model",
        "input locator role drift",
    )
    require(
        int(locator.get("pose_transform_reapplication_count", -1)) == 0,
        "input locator would reapply the corrected-pose transform",
    )
    for key, hash_key in (
        ("footprint_xy", "footprint_sha256"),
        ("scene_reference_frame", "scene_reference_sha256"),
    ):
        path_value = locator.get(key)
        require(isinstance(path_value, str), f"input locator {key} absent")
        path = base.repo_path(path_value)
        require(path.is_file(), f"input locator source absent: {path_value}")
        require(sha256_file(path) == locator.get(hash_key), f"input locator {key} hash drift")
    view_selection = locator.get("view_selection", {})
    require(
        view_selection.get("image_pixels_or_M_j_pixels_used_for_ranking") is False,
        "input-view selection must be geometry-only",
    )

    base_config = base.load_config(base.repo_path(base_contract["config"]))
    return config, base_config


def implementation_records(config: Mapping[str, Any]) -> list[dict[str, Any]]:
    return [base.file_record(base.repo_path(value)) for value in config["implementation_files"]]


def output_job_dir(
    config: Mapping[str, Any],
    building_id: str,
    arm: str,
    replicate: str,
    output_root: Path | None,
) -> Path:
    root = base.repo_path(config["outputs"]["root"]) if output_root is None else output_root.resolve()
    return root / "by_building" / building_id / f"arm_{arm}" / replicate


def numeric_lod(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return -math.inf


def load_cityjson_surfaces(path: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    payload = base.load_json(path)
    require(payload.get("type") == "CityJSON", "canonical Roofer artifact is not CityJSON")
    vertices = np.asarray(payload.get("vertices") or [], dtype=np.float64)
    require(vertices.ndim == 2 and vertices.shape[1] == 3 and len(vertices) >= 4, "CityJSON vertices malformed")
    transform = payload.get("transform") or {}
    vertices = vertices * np.asarray(transform.get("scale", [1, 1, 1]), dtype=np.float64)
    vertices = vertices + np.asarray(transform.get("translate", [0, 0, 0]), dtype=np.float64)

    candidates: list[tuple[float, str, Mapping[str, Any]]] = []
    for object_id, city_object in (payload.get("CityObjects") or {}).items():
        for geometry in city_object.get("geometry") or []:
            lod = numeric_lod(geometry.get("lod"))
            if geometry.get("type") == "Solid" and lod >= 2.0:
                candidates.append((lod, str(object_id), geometry))
    require(bool(candidates), "canonical Roofer CityJSON has no LoD2 Solid")
    selected_lod = max(item[0] for item in candidates)

    surfaces: list[dict[str, Any]] = []
    for lod, object_id, geometry in candidates:
        if lod != selected_lod:
            continue
        semantics = geometry.get("semantics") or {}
        semantic_surfaces = semantics.get("surfaces") or []
        semantic_values = semantics.get("values") or []
        boundaries = geometry.get("boundaries") or []
        for shell_index, shell in enumerate(boundaries):
            if not isinstance(shell, list):
                continue
            shell_values = (
                semantic_values[shell_index]
                if isinstance(semantic_values, list) and shell_index < len(semantic_values)
                else []
            )
            for surface_index, rings in enumerate(shell):
                if not isinstance(rings, list) or not rings:
                    continue
                rings_xyz: list[np.ndarray] = []
                for ring_index, ring in enumerate(rings):
                    require(
                        isinstance(ring, list) and len(ring) >= 3,
                        f"CityJSON face ring malformed at {shell_index}/{surface_index}/{ring_index}",
                    )
                    indices = [int(value) for value in ring]
                    require(
                        min(indices) >= 0 and max(indices) < len(vertices),
                        "CityJSON face index out of range",
                    )
                    rings_xyz.append(vertices[indices])
                semantic_index = (
                    shell_values[surface_index]
                    if isinstance(shell_values, list) and surface_index < len(shell_values)
                    else None
                )
                semantic_type = "UnknownSurface"
                if isinstance(semantic_index, int) and 0 <= semantic_index < len(semantic_surfaces):
                    semantic_type = str(semantic_surfaces[semantic_index].get("type", semantic_type))
                surfaces.append(
                    {
                        "xyz": rings_xyz[0],
                        "rings_xyz": rings_xyz,
                        "semantic_type": semantic_type,
                        "object_id": object_id,
                        "lod": lod,
                    }
                )
    require(bool(surfaces), "canonical Roofer LoD2 Solid has no renderable surfaces")
    counts: dict[str, int] = {}
    for surface in surfaces:
        key = str(surface["semantic_type"])
        counts[key] = counts.get(key, 0) + 1
    rings_n = sum(len(surface["rings_xyz"]) for surface in surfaces)
    surfaces_with_interior_rings_n = sum(
        len(surface["rings_xyz"]) > 1 for surface in surfaces
    )
    return surfaces, {
        "lod": selected_lod,
        "surfaces_n": len(surfaces),
        "semantic_counts": counts,
        "vertices_n": len(vertices),
        "rings_n": int(rings_n),
        "interior_rings_n": int(rings_n - len(surfaces)),
        "surfaces_with_interior_rings_n": int(surfaces_with_interior_rings_n),
        "interior_ring_render_policy": "unfilled_surface_with_all_boundary_rings",
    }


def primary_score(evidence: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    readout = evidence["readout"]
    primary = readout.get("primary", {})
    record = dict(primary.get("receipt") or {})
    actual = base.verify_record(record, "primary score")
    require(
        any(candidate == record for candidate in base.ledger_records(readout)),
        "primary score is not bound into the readout artifact ledger",
    )
    payload = base.load_json(base.repo_path(record["path"]))
    require(payload.get("state") == "MEASURED", "primary score is not MEASURED")
    require(payload.get("interpretation_or_verdict") is None, "primary score contains interpretation")
    identity = payload.get("identity", {})
    expected_identity = evidence["identity"]
    for key in ("building_id", "arm", "replicate"):
        require(
            identity.get(key) == expected_identity[key],
            f"primary score {key} identity drift",
        )
    require(payload.get("mode") == "primary", "primary score mode is not primary")
    require(payload.get("comparison_only") is False, "primary score is comparison-only")
    require(
        payload.get("readout_role") == primary.get("readout_role"),
        "primary score/readout role drift",
    )
    require(
        payload.get("measurements") == primary.get("measurements"),
        "primary score/readout measurements drift",
    )
    canonical_row = payload.get("canonical_score_row")
    require(isinstance(canonical_row, Mapping), "primary canonical score row absent")
    require(
        canonical_row.get("building_id") == expected_identity["building_id"],
        "primary canonical score building drift",
    )
    require(canonical_row.get("status") == "MEASURED", "primary canonical score is not MEASURED")
    return payload, actual


def polygon_area_xy(values: np.ndarray) -> float:
    ring = np.asarray(values, dtype=np.float64)
    require(ring.ndim == 2 and ring.shape[1] == 2 and len(ring) >= 3, "polygon ring malformed")
    return 0.5 * abs(
        float(
            np.dot(ring[:, 0], np.roll(ring[:, 1], -1))
            - np.dot(ring[:, 1], np.roll(ring[:, 0], -1))
        )
    )


def load_approved_footprint_xy(
    config: Mapping[str, Any], building_id: str
) -> tuple[np.ndarray, dict[str, Any]]:
    contract = config["input_locator_contract"]
    path = base.repo_path(contract["footprint_xy"])
    record = base.file_record(path)
    require(record["sha256"] == contract["footprint_sha256"], "footprint locator hash drift")
    layer = str(contract["footprint_layer"])
    id_field = str(contract["footprint_id_field"])
    try:
        from shapely import wkb

        connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        geometry_row = connection.execute(
            "SELECT column_name, srs_id FROM gpkg_geometry_columns WHERE table_name = ?",
            (layer,),
        ).fetchone()
        require(geometry_row is not None, "footprint locator layer metadata absent")
        geometry_column, srs_id = geometry_row
        require(int(srs_id) == 25832, "footprint locator CRS is not EPSG:25832")
        quoted_layer = '"' + layer.replace('"', '""') + '"'
        quoted_geometry = '"' + str(geometry_column).replace('"', '""') + '"'
        quoted_id = '"' + id_field.replace('"', '""') + '"'
        rows = connection.execute(
            f"SELECT {quoted_id}, {quoted_geometry} FROM {quoted_layer}"
        ).fetchall()
        connection.close()
    except (sqlite3.Error, ImportError) as exc:
        raise PanelError(f"cannot read approved footprint locator: {exc}") from exc

    rings: list[np.ndarray] = []
    for identifier, blob_value in rows:
        value = str(identifier).strip()
        canonical = value if value.startswith("DEBY_LOD2_") else f"DEBY_LOD2_{value}"
        if canonical != building_id:
            continue
        blob = bytes(blob_value)
        require(len(blob) >= 8 and blob[:2] == b"GP", "invalid GeoPackage geometry header")
        flags = blob[3]
        envelope_code = (flags >> 1) & 0b111
        envelope_doubles = {0: 0, 1: 4, 2: 6, 3: 6, 4: 8}.get(envelope_code)
        require(envelope_doubles is not None, "unsupported GeoPackage envelope code")
        geometry = wkb.loads(blob[8 + int(envelope_doubles) * 8 :])
        require(not bool(getattr(geometry, "has_z", False)), "footprint locator exposes forbidden Z")
        if geometry.geom_type == "Polygon":
            geometries = [geometry]
        elif geometry.geom_type == "MultiPolygon":
            geometries = list(geometry.geoms)
        else:
            raise PanelError(f"unsupported footprint locator geometry: {geometry.geom_type}")
        for polygon in geometries:
            ring = np.asarray(polygon.exterior.coords, dtype=np.float64)
            require(
                ring.ndim == 2 and ring.shape[1] == 2 and len(ring) >= 4,
                "footprint locator must expose XY only",
            )
            if not np.allclose(ring[0], ring[-1]):
                ring = np.vstack((ring, ring[0]))
            rings.append(ring)
    require(bool(rings), f"approved footprint locator absent for {building_id}")
    return max(rings, key=polygon_area_xy), record


def base_xy_to_canonical_at_z(
    ring_xy: np.ndarray, canonical_z: float, scene_reference: Mapping[str, Any]
) -> np.ndarray:
    transform = scene_reference.get("base_to_canonical") or {}
    values = np.column_stack((np.asarray(ring_xy, dtype=np.float64), np.zeros(len(ring_xy))))
    if transform.get("swap_xy", False):
        values[:, [0, 1]] = values[:, [1, 0]]
    shift = np.asarray(transform.get("shift", [0.0, 0.0, 0.0]), dtype=np.float64)
    scale = np.asarray(transform.get("scale", [1.0, 1.0, 1.0]), dtype=np.float64)
    require(shift.shape == (3,) and scale.shape == (3,), "scene reference transform malformed")
    canonical = (values + shift) * scale
    canonical[:, 2] = float(canonical_z)
    return canonical


def project_canonical_points(
    points: np.ndarray, image_pose: Any, camera: Any
) -> tuple[np.ndarray, np.ndarray]:
    xyz = np.asarray(points, dtype=np.float64)
    camera_xyz = (image_pose.R() @ xyz.T).T + np.asarray(image_pose.tvec, dtype=np.float64)
    depth = camera_xyz[:, 2]
    uv = np.full((len(xyz), 2), np.nan, dtype=np.float64)
    front = depth > 1.0
    parameters = np.asarray(camera.params, dtype=np.float64)
    if camera.model == "PINHOLE":
        fx, fy, cx, cy = parameters[:4]
    elif camera.model == "SIMPLE_PINHOLE":
        focal, cx, cy = parameters[:3]
        fx = fy = focal
    else:
        raise PanelError(f"unsupported locked input-locator camera model: {camera.model}")
    if np.any(front):
        normalized = camera_xyz[front, :2] / camera_xyz[front, 2:3]
        uv[front, 0] = fx * normalized[:, 0] + cx
        uv[front, 1] = fy * normalized[:, 1] + cy
    return uv, depth


def points_in_frame(uv: np.ndarray, depth: np.ndarray, width: int, height: int) -> np.ndarray:
    return (
        np.isfinite(uv).all(axis=1)
        & np.isfinite(depth)
        & (depth > 1.0)
        & (uv[:, 0] >= 0.0)
        & (uv[:, 0] < int(width))
        & (uv[:, 1] >= 0.0)
        & (uv[:, 1] < int(height))
    )


def mask_containment(mask: np.ndarray, footprint_uv: np.ndarray) -> float | None:
    y, x = np.nonzero(mask)
    if not len(x):
        return None
    centers = np.column_stack((x.astype(np.float64) + 0.5, y.astype(np.float64) + 0.5))
    inside = MplPath(np.asarray(footprint_uv, dtype=np.float64)).contains_points(
        centers, radius=1.0e-9
    )
    return float(np.mean(inside))


def manifest_bound_record(
    path: Path, preprocess: Mapping[str, Any], label: str
) -> dict[str, Any]:
    record = base.file_record(path)
    expected = (preprocess.get("artifact_sha256") or {}).get(record["path"])
    require(expected == record["sha256"], f"{label} is not hash-bound by preprocess manifest")
    return record


def projected_input_view(
    evidence: Mapping[str, Any], config: Mapping[str, Any]
) -> dict[str, Any]:
    identity = evidence["identity"]
    building_id = str(identity["building_id"])
    preprocess_path = base.repo_path(evidence["source_records"]["preprocess_manifest"]["path"])
    preprocess_root = preprocess_path.parent
    preprocess = base.load_json(preprocess_path)
    locator = config["input_locator_contract"]

    source_hashes = preprocess.get("source_inputs", {}).get("sha256", {})
    for path_key, hash_key in (
        ("footprint_xy", "footprint_sha256"),
        ("scene_reference_frame", "scene_reference_sha256"),
    ):
        path_value = str(locator[path_key])
        require(
            source_hashes.get(path_value) == locator[hash_key],
            f"preprocess did not bind input locator source: {path_value}",
        )
    require(
        preprocess.get("source_inputs", {}).get("footprint_role")
        == "approved GroundSurface XY crop/address only",
        "preprocess footprint role drift",
    )
    require(
        preprocess.get("source_inputs", {}).get("forbidden_lod2_components_read") == [],
        "preprocess read forbidden LoD2 components",
    )

    footprint_xy, footprint_record = load_approved_footprint_xy(config, building_id)
    scene_path = base.repo_path(locator["scene_reference_frame"])
    scene_record = base.file_record(scene_path)
    require(scene_record["sha256"] == locator["scene_reference_sha256"], "scene reference hash drift")
    scene_reference = base.load_json(scene_path)

    seed_path = base.repo_path(evidence["source_records"]["pretraining_seed"]["path"])
    with np.load(seed_path, allow_pickle=False) as archive:
        require("xyz" in archive.files, "canonical filtered ALS seed coordinates absent")
        seed_canonical = np.asarray(archive["xyz"], dtype=np.float64)
    require(
        seed_canonical.ndim == 2 and seed_canonical.shape[1] == 3 and len(seed_canonical),
        "canonical filtered ALS seed malformed",
    )
    q80 = float(np.quantile(seed_canonical[:, 2], 0.80))
    upper = seed_canonical[seed_canonical[:, 2] >= q80, 2]
    require(bool(len(upper)), "filtered ALS q80-upper height sample is empty")
    locator_z = float(np.median(upper))
    footprint_canonical = base_xy_to_canonical_at_z(footprint_xy, locator_z, scene_reference)

    cameras_path = preprocess_root / "sparse/0/cameras.bin"
    images_path = preprocess_root / "sparse/0/images.bin"
    views_path = preprocess_root / "views.csv"
    index_path = preprocess_root / "supervision_index.csv"
    cameras_record = manifest_bound_record(cameras_path, preprocess, "corrected cameras")
    images_record = manifest_bound_record(images_path, preprocess, "corrected poses")
    views_record = manifest_bound_record(views_path, preprocess, "selected views")
    index_record = manifest_bound_record(index_path, preprocess, "supervision index")
    require(
        int(preprocess.get("pose_binding", {}).get("additional_transform_application_count", -1)) == 0,
        "panel input locator would consume a re-transformed pose",
    )
    cameras = read_cameras_bin(cameras_path)
    images = read_images_bin(images_path)
    images_by_name = {image.name: image for image in images.values()}
    view_rows = {row["image_name"]: row for row in base.read_csv(views_path)}
    corrected_source_hash = preprocess.get("pose_binding", {}).get("corrected_images_sha256")
    require(
        bool(view_rows)
        and all(
            row.get("corrected_pose_source_sha256") == corrected_source_hash
            for row in view_rows.values()
        ),
        "selected views are not bound to the adopted corrected pose source",
    )
    supervision_rows = base.read_csv(index_path)
    require(bool(supervision_rows), "supervision index is empty")

    candidates: list[dict[str, Any]] = []
    for row in supervision_rows:
        image_name = row["image_name"]
        require(image_name in images_by_name and image_name in view_rows, f"input view pose absent: {image_name}")
        pose = images_by_name[image_name]
        require(pose.camera_id in cameras, f"input view camera absent: {image_name}")
        camera = cameras[pose.camera_id]
        seed_uv, seed_depth = project_canonical_points(seed_canonical, pose, camera)
        footprint_uv, footprint_depth = project_canonical_points(footprint_canonical, pose, camera)
        seed_inframe = points_in_frame(seed_uv, seed_depth, camera.width, camera.height)
        footprint_inframe = points_in_frame(
            footprint_uv, footprint_depth, camera.width, camera.height
        )
        prior_path = base.repo_path(row["class6_npz_path"])
        with np.load(prior_path, allow_pickle=False) as archive:
            require("valid_M_j" in archive.files, f"valid_M_j absent: {image_name}")
            mask = np.asarray(archive["valid_M_j"], dtype=bool)
        require(mask.shape == (camera.height, camera.width), f"M_j/camera shape drift: {image_name}")
        require(int(mask.sum()) == int(row["mask_pixels_n"]), f"M_j cardinality drift: {image_name}")
        view_row = view_rows[image_name]
        candidates.append(
            {
                "row": row,
                "view_row": view_row,
                "pose": pose,
                "camera": camera,
                "seed_uv": seed_uv,
                "seed_inframe": seed_inframe,
                "footprint_uv": footprint_uv,
                "footprint_fully_inframe": bool(np.all(footprint_inframe)),
                "footprint_area_px2": polygon_area_xy(footprint_uv),
                "seed_inframe_fraction": float(np.mean(seed_inframe)),
                "M_j_containment_in_locator": mask_containment(mask, footprint_uv),
            }
        )
    view_contract = locator["view_selection"]
    eligible = [
        candidate
        for candidate in candidates
        if candidate["footprint_fully_inframe"]
        and candidate["seed_inframe_fraction"]
        >= float(view_contract["minimum_seed_inframe_fraction"])
    ]
    require(bool(eligible), "no geometry-valid input locator view")
    maximum_area = max(candidate["footprint_area_px2"] for candidate in eligible)
    area_floor = maximum_area * float(
        view_contract["minimum_projected_footprint_area_ratio_to_best"]
    )
    eligible = [candidate for candidate in eligible if candidate["footprint_area_px2"] >= area_floor]
    selected = min(
        eligible,
        key=lambda candidate: (
            float(candidate["view_row"]["nadir_deg"]),
            float(candidate["view_row"]["frame_radius"]),
            -float(candidate["footprint_area_px2"]),
            int(candidate["row"]["selection_order"]),
        ),
    )
    row = selected["row"]
    image_path = preprocess_root / "images" / row["image_name"]
    prior_path = base.repo_path(row["class6_npz_path"])
    require(image_path.is_file() and prior_path.is_file(), "selected input source absent")
    with Image.open(image_path) as source:
        image = source.convert("RGB")
        image.load()
    with np.load(prior_path, allow_pickle=False) as archive:
        mask = np.asarray(archive["valid_M_j"], dtype=bool)
    require(mask.shape == (image.height, image.width), "selected M_j/image shape mismatch")

    footprint_uv = np.asarray(selected["footprint_uv"], dtype=np.float64)
    seed_uv = np.asarray(selected["seed_uv"], dtype=np.float64)
    seed_inframe = np.asarray(selected["seed_inframe"], dtype=bool)
    y_mask, x_mask = np.nonzero(mask)
    crop_points = [footprint_uv, seed_uv[seed_inframe]]
    if len(x_mask):
        crop_points.append(np.column_stack((x_mask, y_mask)))
    crop_values = np.vstack(crop_points)
    x0, y0 = np.floor(crop_values.min(axis=0)).astype(int)
    x1, y1 = np.ceil(crop_values.max(axis=0)).astype(int) + 1
    padding_fraction = float(config["visual_contract"]["crop_padding_fraction"])
    pad_x = max(12, int((x1 - x0) * padding_fraction))
    pad_y = max(12, int((y1 - y0) * padding_fraction))
    crop_box = (
        max(0, x0 - pad_x),
        max(0, y0 - pad_y),
        min(image.width, x1 + pad_x),
        min(image.height, y1 + pad_y),
    )
    containment_values = [
        float(candidate["M_j_containment_in_locator"])
        for candidate in candidates
        if candidate["M_j_containment_in_locator"] is not None
    ]
    worst = min(
        (candidate for candidate in candidates if candidate["M_j_containment_in_locator"] is not None),
        key=lambda candidate: float(candidate["M_j_containment_in_locator"]),
    )
    return {
        "row": row,
        "view_row": selected["view_row"],
        "image": image,
        "mask": mask,
        "crop_box": crop_box,
        "seed_uv": seed_uv,
        "seed_inframe": seed_inframe,
        "footprint_uv": footprint_uv,
        "locator_canonical_z": locator_z,
        "seed_contract": {
            "source": "ALS classification 6 only",
            "unfiltered_points_n": int(preprocess["seed"]["source_unfiltered_points_n"]),
            "filtered_points_n": int(preprocess["seed"]["filtered_points_n"]),
            "visibility_epsilon_m": float(preprocess["seed"]["visibility"]["epsilon_m"]),
            "visibility_minimum_views_k": int(
                preprocess["seed"]["visibility"]["minimum_views_k"]
            ),
            "class2_rows_n": int(preprocess["seed"]["class2_rows_n"]),
            "sfm_rows_n": int(preprocess["seed"]["sfm_rows_n"]),
        },
        "selection": {
            "method": view_contract["rank"],
            "M_j_or_image_pixels_used_for_ranking": False,
            "candidates_n": len(candidates),
            "geometry_eligible_n": len(eligible),
            "projected_footprint_area_px2": float(selected["footprint_area_px2"]),
            "seed_inframe_fraction": float(selected["seed_inframe_fraction"]),
            "nadir_deg": float(selected["view_row"]["nadir_deg"]),
            "frame_radius": float(selected["view_row"]["frame_radius"]),
        },
        "mask_alignment": {
            "selected_containment_in_projected_locator": selected["M_j_containment_in_locator"],
            "all_views_min": min(containment_values),
            "all_views_median": float(np.median(containment_values)),
            "all_views_max": max(containment_values),
            "worst_image_name": worst["row"]["image_name"],
            "worst_containment": worst["M_j_containment_in_locator"],
        },
        "records": {
            "supervision_index": index_record,
            "selected_full_image": base.file_record(image_path),
            "selected_M_j": base.file_record(prior_path),
            "selected_views": views_record,
            "corrected_cameras": cameras_record,
            "corrected_poses": images_record,
            "approved_footprint_XY": footprint_record,
            "scene_reference_frame": scene_record,
        },
    }


def roofer_prepare_provenance(
    evidence: Mapping[str, Any], config: Mapping[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    record = base.select_ledger_record(
        base.ledger_records(evidence["readout"]),
        "primary Roofer prepare receipt",
        lambda path: path.endswith("/primary/prepare_receipt.json"),
    )
    base.require_binding(evidence["readout"], record, "readout to primary prepare receipt")
    actual = base.verify_record(record, "primary Roofer prepare receipt")
    payload = base.load_json(base.repo_path(record["path"]))
    identity = payload.get("identity", {})
    for key in ("building_id", "arm", "replicate"):
        require(identity.get(key) == evidence["identity"][key], f"Roofer prepare {key} drift")
    footprint = payload.get("footprint", {})
    locator = config["input_locator_contract"]
    require(
        footprint.get("source_role") == "approved_LoD2_GroundSurface_XY_only",
        "Roofer footprint source role drift",
    )
    require(footprint.get("source_path") == locator["footprint_xy"], "Roofer footprint source path drift")
    require(
        footprint.get("source_sha256") == locator["footprint_sha256"],
        "Roofer footprint source hash drift",
    )
    return payload, actual


def augment_evidence(
    evidence: dict[str, Any], config: Mapping[str, Any]
) -> dict[str, Any]:
    result = dict(evidence)
    surfaces, surface_stats = load_cityjson_surfaces(evidence["cityjson_path"])
    score, score_record = primary_score(evidence)
    input_view = projected_input_view(evidence, config)
    roofer_prepare, roofer_prepare_record = roofer_prepare_provenance(evidence, config)
    source_records = dict(evidence["source_records"])
    source_records["primary_score"] = score_record
    source_records["primary_roofer_prepare"] = roofer_prepare_record
    for role, record in input_view["records"].items():
        source_records[role] = record
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


def mesh_topology_stats(faces: np.ndarray) -> dict[str, int]:
    values = np.asarray(faces, dtype=np.int64)
    edges = np.vstack((values[:, [0, 1]], values[:, [1, 2]], values[:, [2, 0]]))
    edges.sort(axis=1)
    _, counts = np.unique(edges, axis=0, return_counts=True)
    return {
        "faces_n": int(len(values)),
        "edges_n": int(len(counts)),
        "boundary_edges_n": int(np.count_nonzero(counts == 1)),
        "manifold_edges_n": int(np.count_nonzero(counts == 2)),
        "nonmanifold_edges_n": int(np.count_nonzero(counts > 2)),
    }


def principal_axis(surfaces: Sequence[Mapping[str, Any]], config: Mapping[str, Any]) -> dict[str, Any]:
    ground = [np.asarray(item["xyz"], dtype=np.float64)[:, :2] for item in surfaces if item["semantic_type"] == "GroundSurface"]
    source = "canonical_roofer_cityjson_GroundSurface"
    if not ground:
        ground = [np.asarray(item["xyz"], dtype=np.float64)[:, :2] for item in surfaces]
        source = "canonical_roofer_cityjson_all_output_surfaces"
    xy = np.unique(np.vstack(ground), axis=0)
    require(len(xy) >= 3, "output surfaces cannot define a principal axis")
    centered = xy - xy.mean(axis=0)
    covariance = centered.T @ centered / max(1, len(centered) - 1)
    eigenvalues, eigenvectors = np.linalg.eigh(covariance)
    order = np.argsort(eigenvalues)[::-1]
    principal = eigenvectors[:, order[0]]
    if principal[1] < 0 or (abs(float(principal[1])) < 1e-12 and principal[0] < 0):
        principal = -principal
    ratio = float(eigenvalues[order[0]] / max(float(eigenvalues[order[1]]), 1e-12))
    threshold = float(config["visual_contract"]["camera_contract"]["near_isotropic_ratio_threshold"])
    fallback = ratio < threshold
    if fallback:
        principal = np.asarray([1.0, 0.0])
        source = "near_isotropic_east_axis_fallback"
    azimuth = math.degrees(math.atan2(float(principal[1]), float(principal[0])))
    return {
        "source": source,
        "vector_east_north": [float(principal[0]), float(principal[1])],
        "azimuth_deg_from_east": float(azimuth),
        "eigenvalue_ratio": ratio,
        "near_isotropic_fallback": fallback,
    }


def scene_frame(evidence: Mapping[str, Any], config: Mapping[str, Any]) -> dict[str, Any]:
    arrays = [
        np.asarray(evidence["seed_xyz"], dtype=np.float64),
        np.asarray(evidence["mesh_xyz"], dtype=np.float64),
    ]
    arrays.extend(np.asarray(item["xyz"], dtype=np.float64) for item in evidence["cityjson_surfaces"])
    arrays.extend(np.asarray(ring, dtype=np.float64)[:, :3] for ring in evidence["reference_rings"])
    xyz = np.vstack(arrays)
    require(np.isfinite(xyz).all(), "scene contains non-finite coordinates")
    minimum = xyz.min(axis=0)
    maximum = xyz.max(axis=0)
    origin = np.asarray(
        [
            round(float((minimum[0] + maximum[0]) / 2.0), 3),
            round(float((minimum[1] + maximum[1]) / 2.0), 3),
            round(float(minimum[2]), 3),
        ]
    )
    local_minimum = minimum - origin
    local_maximum = maximum - origin
    span = local_maximum - local_minimum
    require(np.all(span > 1e-8), "scene has a degenerate XYZ span")
    padding_fraction = float(config["visual_contract"]["camera_contract"]["bounds_padding_fraction"])
    padding = span * padding_fraction
    bounds = np.column_stack((local_minimum - padding, local_maximum + padding))
    axis = principal_axis(evidence["cityjson_surfaces"], config)
    cameras: list[dict[str, Any]] = []
    for view in config["visual_contract"]["camera_contract"]["views"]:
        if view["azimuth_mode"] == "fixed":
            azimuth = float(view["azimuth_deg"])
        else:
            azimuth = axis["azimuth_deg_from_east"] + float(view["azimuth_offset_deg"])
        cameras.append(
            {
                "key": view["key"],
                "title_ko": view["title_ko"],
                "title_en": view["title_en"],
                "elevation_deg": float(view["elevation_deg"]),
                "azimuth_deg": float(azimuth % 360.0),
                "projection": "orthographic",
            }
        )
    return {
        "crs": "EPSG:25832",
        "bounds_source": "frozen_filtered_ALS_seed_plus_TSDF_plus_output_plus_evaluation_only_reference",
        "view_orientation_source": axis["source"],
        "reference_view_orientation_influence": False,
        "reference_shared_bounds_influence": True,
        "local_origin_epsg25832_xyz": [float(value) for value in origin],
        "source_minimum_xyz": [float(value) for value in minimum],
        "source_maximum_xyz": [float(value) for value in maximum],
        "local_bounds_xyz": [[float(value) for value in pair] for pair in bounds],
        "z_exaggeration": 1.0,
        "axis": axis,
        "cameras": cameras,
    }


def local_xyz(values: np.ndarray, frame: Mapping[str, Any]) -> np.ndarray:
    origin = np.asarray(frame["local_origin_epsg25832_xyz"], dtype=np.float64)
    return np.asarray(values, dtype=np.float64)[:, :3] - origin


def cityjson_render_parts(
    surfaces: Sequence[Mapping[str, Any]], frame: Mapping[str, Any]
) -> dict[str, Any]:
    """Separate truthful filled faces from surfaces that contain interior rings.

    ``Poly3DCollection`` cannot represent polygon holes.  Filling the exterior
    ring would therefore invent geometry across each hole.  Such surfaces are
    rendered as all-ring wireframes; only single-ring surfaces are filled.
    """
    filled: list[dict[str, Any]] = []
    wireframe_rings: list[dict[str, Any]] = []
    surfaces_with_interior_rings_n = 0
    interior_rings_n = 0
    for surface in surfaces:
        raw_rings = surface.get("rings_xyz")
        rings = (
            [np.asarray(ring, dtype=np.float64) for ring in raw_rings]
            if isinstance(raw_rings, list) and raw_rings
            else [np.asarray(surface["xyz"], dtype=np.float64)]
        )
        local_rings = [local_xyz(ring, frame) for ring in rings]
        if len(local_rings) == 1:
            filled.append(
                {
                    "xyz": local_rings[0],
                    "semantic_type": str(surface["semantic_type"]),
                }
            )
            continue
        surfaces_with_interior_rings_n += 1
        interior_rings_n += len(local_rings) - 1
        for ring_index, ring in enumerate(local_rings):
            wireframe_rings.append(
                {
                    "xyz": ring,
                    "semantic_type": str(surface["semantic_type"]),
                    "interior": ring_index > 0,
                }
            )
    return {
        "filled": filled,
        "wireframe_rings": wireframe_rings,
        "stats": {
            "filled_surfaces_n": len(filled),
            "wireframe_only_surfaces_n": surfaces_with_interior_rings_n,
            "interior_rings_n": interior_rings_n,
            "hole_policy": "unfilled_surface_with_all_boundary_rings",
        },
    }


def configure_3d_axis(ax: Any, frame: Mapping[str, Any], camera: Mapping[str, Any]) -> None:
    bounds = np.asarray(frame["local_bounds_xyz"], dtype=np.float64)
    ax.set_xlim(bounds[0])
    ax.set_ylim(bounds[1])
    ax.set_zlim(bounds[2])
    spans = bounds[:, 1] - bounds[:, 0]
    ax.set_box_aspect(tuple(float(value) for value in spans))
    ax.set_proj_type("ortho")
    ax.view_init(elev=float(camera["elevation_deg"]), azim=float(camera["azimuth_deg"]), roll=0)
    ax.set_xlabel("ΔE (m)", fontsize=6, labelpad=-1)
    ax.set_ylabel("ΔN (m)", fontsize=6, labelpad=-1)
    ax.set_zlabel("ΔZ (m)", fontsize=6, labelpad=-2)
    ax.tick_params(labelsize=5, pad=-2)
    ax.grid(True, color="#e3e7eb", linewidth=0.35)
    for axis in (ax.xaxis, ax.yaxis, ax.zaxis):
        axis.pane.set_facecolor((0.98, 0.98, 0.98, 1.0))
        axis.pane.set_edgecolor((0.82, 0.84, 0.87, 1.0))


def selected_faces(faces: np.ndarray, limit: int) -> np.ndarray:
    values = np.asarray(faces, dtype=np.int64)
    require(
        len(values) <= limit,
        "TSDF mesh exceeds truthful full-face panel limit; topology-preserving decimation is required",
    )
    return values


def shaded_tsdf_colors(triangles: np.ndarray, light: str) -> np.ndarray:
    vectors_a = triangles[:, 1] - triangles[:, 0]
    vectors_b = triangles[:, 2] - triangles[:, 0]
    normals = np.cross(vectors_a, vectors_b)
    lengths = np.linalg.norm(normals, axis=1)
    normals = normals / np.maximum(lengths[:, None], 1e-12)
    light_direction = np.asarray([0.35, -0.25, 0.90], dtype=np.float64)
    light_direction /= np.linalg.norm(light_direction)
    intensity = 0.52 + 0.48 * np.abs(normals @ light_direction)
    base_rgb = np.asarray(mpl_colors.to_rgb(light), dtype=np.float64)
    colors = np.clip(intensity[:, None] * base_rgb[None, :], 0.0, 1.0)
    return np.column_stack((colors, np.full(len(colors), 0.90)))


def plot_tsdf(
    ax: Any,
    evidence: Mapping[str, Any],
    frame: Mapping[str, Any],
    config: Mapping[str, Any],
) -> int:
    faces = selected_faces(
        evidence["mesh_faces"], int(config["visual_contract"]["maximum_mesh_faces"])
    )
    xyz = local_xyz(evidence["mesh_xyz"], frame)
    triangles = xyz[faces]
    palette = config["visual_contract"]["semantic_palette"]
    collection = Poly3DCollection(
        triangles,
        facecolors=shaded_tsdf_colors(triangles, palette["tsdf_light"]),
        edgecolors=palette["tsdf_dark"],
        linewidths=0.035,
        antialiased=False,
        rasterized=True,
    )
    collection.set_zsort("average")
    ax.add_collection3d(collection)
    return int(len(faces))


def plot_seed(
    ax: Any,
    evidence: Mapping[str, Any],
    frame: Mapping[str, Any],
    config: Mapping[str, Any],
) -> int:
    palette = config["visual_contract"]["semantic_palette"]
    values, colors = base.downsample_xyz_rgb(
        np.asarray(evidence["seed_xyz"], dtype=np.float64),
        evidence["seed_rgb"],
        int(config["visual_contract"]["maximum_scatter_points"]),
    )
    local = local_xyz(values, frame)
    ax.scatter(
        local[:, 0],
        local[:, 1],
        local[:, 2],
        s=3.2,
        c=base.rgb_colors(colors, len(values), palette["seed_projection"]),
        edgecolors="none",
        depthshade=False,
        rasterized=True,
    )
    return int(len(values))


def plot_cityjson(
    ax: Any,
    evidence: Mapping[str, Any],
    frame: Mapping[str, Any],
    config: Mapping[str, Any],
    *,
    alpha: float,
) -> dict[str, Any]:
    palette = config["visual_contract"]["semantic_palette"]
    parts = cityjson_render_parts(evidence["cityjson_surfaces"], frame)
    if parts["filled"]:
        collection = Poly3DCollection(
            [item["xyz"] for item in parts["filled"]],
            facecolors=[
                palette.get(item["semantic_type"], palette["UnknownSurface"])
                for item in parts["filled"]
            ],
            edgecolors=palette["charcoal"],
            linewidths=0.55,
            alpha=alpha,
            antialiased=True,
        )
        collection.set_zsort("average")
        ax.add_collection3d(collection)
    for item in parts["wireframe_rings"]:
        values = item["xyz"]
        if not np.array_equal(values[0], values[-1]):
            values = np.vstack((values, values[0]))
        ax.plot(
            values[:, 0],
            values[:, 1],
            values[:, 2],
            color=palette.get(item["semantic_type"], palette["UnknownSurface"]),
            linestyle="--" if item["interior"] else "-",
            linewidth=1.15 if item["interior"] else 0.8,
            alpha=max(alpha, 0.75),
        )
    return parts["stats"]


def plot_reference(
    ax: Any,
    evidence: Mapping[str, Any],
    frame: Mapping[str, Any],
    config: Mapping[str, Any],
) -> None:
    color = config["visual_contract"]["semantic_palette"]["reference"]
    for ring in evidence["reference_rings"]:
        values = np.asarray(ring, dtype=np.float64)[:, :3]
        if not np.array_equal(values[0], values[-1]):
            values = np.vstack((values, values[0]))
        values = local_xyz(values, frame)
        ax.plot(
            values[:, 0],
            values[:, 1],
            values[:, 2],
            color=color,
            linestyle="--",
            linewidth=1.45,
            marker="o",
            markersize=1.8,
            markerfacecolor="white",
            markeredgewidth=0.65,
        )


def unique_coordinate_rows(values: np.ndarray, dimensions: int) -> np.ndarray:
    array = np.asarray(values, dtype=np.float64)[:, :dimensions]
    return np.unique(np.round(array, decimals=9), axis=0)


def output_reference_comparison(evidence: Mapping[str, Any]) -> dict[str, Any]:
    output_xyz = np.vstack(
        [np.asarray(item["xyz"], dtype=np.float64) for item in evidence["cityjson_surfaces"]]
    )
    reference_xyz = np.vstack(
        [np.asarray(item, dtype=np.float64)[:, :3] for item in evidence["reference_rings"]]
    )
    output_unique_xyz = unique_coordinate_rows(output_xyz, 3)
    reference_unique_xyz = unique_coordinate_rows(reference_xyz, 3)
    output_unique_xy = unique_coordinate_rows(output_xyz, 2)
    reference_unique_xy = unique_coordinate_rows(reference_xyz, 2)
    xyz_equal = (
        output_unique_xyz.shape == reference_unique_xyz.shape
        and np.array_equal(output_unique_xyz, reference_unique_xyz)
    )
    xy_equal = (
        output_unique_xy.shape == reference_unique_xy.shape
        and np.array_equal(output_unique_xy, reference_unique_xy)
    )
    return {
        "output_xyz": output_xyz,
        "reference_xyz": reference_xyz,
        "output_unique_xyz_n": len(output_unique_xyz),
        "reference_unique_xyz_n": len(reference_unique_xyz),
        "exact_XY_coordinate_set_equal": bool(xy_equal),
        "exact_XYZ_coordinate_set_equal": bool(xyz_equal),
        "output_cityjson_sha256": evidence["source_records"]["canonical_roofer_cityjson"]["sha256"],
        "reference_gml_sha256": [record["sha256"] for record in evidence["reference_records"]],
        "roofer_footprint_source_role": evidence["roofer_prepare"]["footprint"]["source_role"],
        "roofer_footprint_source_sha256": evidence["roofer_prepare"]["footprint"]["source_sha256"],
    }


def short_title(
    ax: Any,
    title_ko: str,
    title_en: str,
    font: font_manager.FontProperties,
    *,
    fontsize: float = 9.0,
) -> None:
    ax.set_title(
        f"{title_ko}\n{title_en}",
        fontproperties=font,
        fontsize=fontsize,
        color="#252a31",
        pad=6,
    )


def plot_opacity(
    ax: plt.Axes,
    evidence: Mapping[str, Any],
    config: Mapping[str, Any],
) -> None:
    rows = evidence["opacity_rows"]
    base_visual = evidence["base_config"]["visual_contract"]
    initial = [row for row in rows if row.get("observation_phase") == base_visual["opacity_initial_observation_phase"]]
    dynamics = [row for row in rows if row.get("observation_phase") == base_visual["opacity_line_observation_phase"]]
    palette = config["visual_contract"]["semantic_palette"]
    ax.plot(
        [int(row["iteration"]) for row in dynamics],
        [float(row["opacity_median"]) for row in dynamics],
        color=palette["tsdf_dark"],
        marker="o",
        markersize=2.1,
        linewidth=1.4,
    )
    ax.scatter(
        [int(row["iteration"]) for row in initial],
        [float(row["opacity_median"]) for row in initial],
        marker="D",
        s=28,
        facecolors="white",
        edgecolors=palette["charcoal"],
        linewidths=1.0,
        zorder=4,
    )
    ax.axvline(int(base_visual["transition_iteration"]), color=palette["reference"], linestyle="--", linewidth=1.2)
    ax.axvline(int(base_visual["surface_ramp_end_iteration"]), color=palette["gold"], linestyle=":", linewidth=1.2)
    ax.set_ylim(bottom=0.0)
    ax.set_xlabel("optimizer iteration", fontsize=7)
    ax.set_ylabel("median opacity", fontsize=7)
    ax.grid(True, color=palette["light_grey"], linewidth=0.45)
    ax.tick_params(labelsize=6)


def format_bool(value: Any) -> str:
    if value is True:
        return "true"
    if value is False:
        return "false"
    return "n/a"


def format_number(value: Any, digits: int = 4) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "n/a"
    return f"{number:.{digits}f}" if math.isfinite(number) else "n/a"


def score_row(evidence: Mapping[str, Any]) -> Mapping[str, Any]:
    payload = evidence["primary_score"]
    row = payload.get("canonical_score_row")
    return row if isinstance(row, Mapping) else payload.get("measurements", {})


def text_panel(
    ax: plt.Axes,
    title_ko: str,
    title_en: str,
    lines: Sequence[str],
    font: font_manager.FontProperties,
) -> None:
    ax.axis("off")
    short_title(ax, title_ko, title_en, font)
    ax.text(
        0.04,
        0.94,
        "\n".join(lines),
        transform=ax.transAxes,
        va="top",
        ha="left",
        fontsize=8.0,
        color="#252a31",
        fontproperties=font,
        linespacing=1.45,
    )
    ax.add_patch(
        patches.Rectangle(
            (0.015, 0.015),
            0.97,
            0.97,
            transform=ax.transAxes,
            fill=False,
            edgecolor="#d7dce1",
            linewidth=0.8,
        )
    )


def render_panel(
    staging: Path,
    config: Mapping[str, Any],
    evidence: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    font, font_record = base.load_cjk_font(evidence["base_config"])
    visual = config["visual_contract"]
    palette = visual["semantic_palette"]
    frame = scene_frame(evidence, config)
    topology = mesh_topology_stats(evidence["mesh_faces"])
    cityjson_render = cityjson_render_parts(evidence["cityjson_surfaces"], frame)["stats"]
    score = score_row(evidence)

    fig = plt.figure(figsize=tuple(visual["panel_inches"]))
    grid = fig.add_gridspec(
        5,
        5,
        left=0.045,
        right=0.987,
        bottom=0.055,
        top=0.925,
        wspace=0.17,
        hspace=0.25,
    )
    identity = evidence["identity"]
    fig.suptitle(
        f"{identity['building_id']} | arm {identity['arm']} | {identity['replicate']}\n"
        "입력·실제 투영 → ALS class 6 시드 → 학습 관찰·TSDF/MC → Roofer CityJSON LoD2.2 → 평가 전용 참조 중첩",
        fontproperties=font,
        fontsize=15,
        color=palette["charcoal"],
    )
    row_labels = [
        (0.840, "1  입력·투영 / Input & projection"),
        (0.670, "2  ALS 시드 / Filtered ALS seed"),
        (0.500, "3  TSDF 메시 / TSDF mesh"),
        (0.330, "4  조립 / Roofer CityJSON"),
        (0.160, "5  평가 전용 / Evaluation-only overlay"),
    ]
    for y, label in row_labels:
        fig.text(
            0.008,
            y,
            label,
            rotation=90,
            va="center",
            ha="center",
            fontsize=8.0,
            color=palette["charcoal"],
            fontproperties=font,
        )

    image_mask = evidence["image_mask"]
    image = np.asarray(image_mask["image"])
    mask = np.asarray(image_mask["mask"])
    x0, y0, x1, y1 = image_mask["crop_box"]
    footprint_uv = np.asarray(image_mask["footprint_uv"], dtype=np.float64)
    seed_uv = np.asarray(image_mask["seed_uv"], dtype=np.float64)
    seed_inframe = np.asarray(image_mask["seed_inframe"], dtype=bool)

    ax = fig.add_subplot(grid[0, 0])
    ax.imshow(image)
    ax.plot(
        footprint_uv[:, 0],
        footprint_uv[:, 1],
        color=palette["target_locator"],
        linewidth=2.2,
        label="approved footprint XY @ ALS height",
    )
    ax.scatter(
        seed_uv[seed_inframe, 0],
        seed_uv[seed_inframe, 1],
        s=5.0,
        c=palette["seed_projection"],
        linewidths=0,
        alpha=0.86,
        label="actual filtered ALS seed projection",
    )
    ax.add_patch(
        patches.Rectangle((x0, y0), x1 - x0, y1 - y0, fill=False, edgecolor="white", linewidth=1.6, linestyle="--")
    )
    ax.legend(loc="lower left", fontsize=5.2, framealpha=0.86, markerscale=1.2)
    ax.axis("off")
    short_title(ax, "A. 원본 전체·대상 위치", "Full image · target locator", font)

    ax = fig.add_subplot(grid[0, 1])
    crop = image[y0:y1, x0:x1]
    crop_mask = mask[y0:y1, x0:x1]
    crop_footprint = footprint_uv - np.asarray([x0, y0], dtype=np.float64)
    crop_seed = seed_uv[seed_inframe] - np.asarray([x0, y0], dtype=np.float64)
    ax.imshow(crop)
    ax.plot(
        crop_footprint[:, 0],
        crop_footprint[:, 1],
        color=palette["target_locator"],
        linewidth=2.0,
    )
    ax.scatter(
        crop_seed[:, 0],
        crop_seed[:, 1],
        s=7.0,
        c=palette["seed_projection"],
        linewidths=0,
        alpha=0.9,
    )
    ax.axis("off")
    short_title(
        ax,
        "B. 확대·실제 ALS 시드 투영",
        "Crop · actual filtered ALS seed projection",
        font,
    )

    ax = fig.add_subplot(grid[0, 2])
    ax.imshow(crop)
    overlay = np.zeros((*crop_mask.shape, 4), dtype=np.float32)
    overlay[crop_mask] = (*mpl_colors.to_rgb(palette["mask"]), 0.38)
    ax.imshow(overlay)
    ax.plot(
        crop_footprint[:, 0],
        crop_footprint[:, 1],
        color=palette["target_locator"],
        linewidth=1.8,
    )
    ax.scatter(
        crop_seed[:, 0],
        crop_seed[:, 1],
        s=5.0,
        c=palette["seed_projection"],
        linewidths=0,
        alpha=0.72,
    )
    if bool(crop_mask.any()):
        ax.contour(
            crop_mask.astype(np.uint8),
            levels=[0.5],
            colors=[palette["mask"]],
            linewidths=1.0,
        )
    ax.axis("off")
    short_title(
        ax,
        "C. 실제 학습 감독 지지 M_j",
        "Actual valid supervision support M_j",
        font,
    )

    ax = fig.add_subplot(grid[0, 3])
    plot_opacity(ax, evidence, config)
    short_title(ax, "D. 지붕 시드 계보 opacity", "Roof seed-lineage opacity trajectory", font)

    measurement_lines = [
        "측정값 / Measurements (판정 없음 / no verdict)",
        f"assembly LoD2: {format_bool(score.get('assembly_lod2_success'))}",
        f"LoD1 fallback: {format_bool(score.get('lod1_fallback'))}",
        f"roof RMS: {format_number(score.get('roof_rms_m'), 3)} m",
        f"Δ RMS vs P0′: {format_number(score.get('delta_roof_rms_vs_p0_refl_m'), 3)} m",
        f"roof Hausdorff: {format_number(score.get('roof_hausdorff_m'), 3)} m",
        f"roof completeness: {format_number(score.get('roof_completeness'), 6)}",
        f"plane P/R/F1: {format_number(score.get('plane_precision'), 3)} / "
        f"{format_number(score.get('plane_recall'), 3)} / {format_number(score.get('plane_f1'), 3)}",
        f"XY overlap: {format_number(score.get('xy_overlap_ratio'), 6)}",
        f"val3dity valid: {format_bool(score.get('val3dity_valid'))}",
    ]
    text_panel(fig.add_subplot(grid[0, 4]), "E. 정량 관찰", "Quantitative observations", measurement_lines, font)

    rendered_seed_points = 0
    for column, camera in enumerate(frame["cameras"]):
        ax = fig.add_subplot(grid[1, column], projection="3d")
        rendered_seed_points = plot_seed(ax, evidence, frame, config)
        configure_3d_axis(ax, frame, camera)
        short_title(
            ax,
            f"ALS class 6 시드 · {camera['title_ko']}",
            f"Filtered ALS seed · {camera['title_en']}",
            font,
            fontsize=8.4,
        )

    seed_xyz = np.asarray(evidence["seed_xyz"], dtype=np.float64)
    seed_contract = image_mask["seed_contract"]
    selection = image_mask["selection"]
    mask_alignment = image_mask["mask_alignment"]
    seed_lines = [
        "학습 전 prior / pre-training prior",
        "ALS class 6 only; class 2/SfM excluded",
        f"unfiltered → k≥{seed_contract['visibility_minimum_views_k']}: "
        f"{seed_contract['unfiltered_points_n']} → {seed_contract['filtered_points_n']}",
        f"visibility ε: {seed_contract['visibility_epsilon_m']:.3f} m",
        f"seed Z: {seed_xyz[:, 2].min():.3f}–{seed_xyz[:, 2].max():.3f} m",
        f"displayed points/view: {rendered_seed_points}",
        "",
        f"input view: {image_mask['row']['image_name']}",
        f"nadir / frame radius: {selection['nadir_deg']:.2f}° / {selection['frame_radius']:.3f}",
        f"locator Z source: ALS q80-upper median ({image_mask['locator_canonical_z']:.3f})",
        f"selected M_j in locator: {format_number(mask_alignment['selected_containment_in_projected_locator'], 4)}",
        f"all-view M_j containment min/med/max: "
        f"{mask_alignment['all_views_min']:.4f} / {mask_alignment['all_views_median']:.4f} / "
        f"{mask_alignment['all_views_max']:.4f}",
        f"worst view: {mask_alignment['worst_image_name']} ({mask_alignment['worst_containment']:.4f})",
        "view ranking uses geometry only; M_j excluded",
    ]
    text_panel(
        fig.add_subplot(grid[1, 4]),
        "시드·입력 투영 영수증",
        "Seed & input-projection receipt",
        seed_lines,
        font,
    )

    rendered_faces = 0
    for column, camera in enumerate(frame["cameras"]):
        ax = fig.add_subplot(grid[2, column], projection="3d")
        rendered_faces = plot_tsdf(ax, evidence, frame, config)
        configure_3d_axis(ax, frame, camera)
        short_title(ax, f"TSDF · {camera['title_ko']}", f"TSDF · {camera['title_en']}", font, fontsize=8.4)

    ax = fig.add_subplot(grid[2, 4])
    values, colors = base.downsample_xyz_rgb(
        np.asarray(evidence["samples_xyz"]),
        evidence["samples_rgb"],
        int(visual["maximum_scatter_points"]),
    )
    principal = np.asarray(frame["axis"]["vector_east_north"], dtype=np.float64)
    origin = np.asarray(frame["local_origin_epsg25832_xyz"], dtype=np.float64)
    horizontal = (values[:, :2] - origin[:2]) @ principal
    ax.scatter(
        horizontal,
        values[:, 2] - origin[2],
        s=1.0,
        c=base.rgb_colors(colors, len(values), palette["tsdf_dark"]),
        linewidths=0,
        rasterized=True,
    )
    ax.set_xlabel("principal horizontal (m)", fontsize=7)
    ax.set_ylabel("ΔZ (m)", fontsize=7)
    ax.set_aspect("equal", adjustable="datalim")
    ax.grid(True, color=palette["light_grey"], linewidth=0.45)
    ax.tick_params(labelsize=6)
    short_title(ax, "TSDF 표면 샘플 주축 단면", "Principal section of TSDF surface samples", font, fontsize=8.4)

    for column, camera in enumerate(frame["cameras"]):
        ax = fig.add_subplot(grid[3, column], projection="3d")
        plot_cityjson(ax, evidence, frame, config, alpha=0.92)
        configure_3d_axis(ax, frame, camera)
        short_title(ax, f"CityJSON · {camera['title_ko']}", f"LoD2.2 solid · {camera['title_en']}", font, fontsize=8.4)

    semantic = evidence["cityjson_surface_stats"]
    semantic_lines = [
        "canonical Roofer CityJSON",
        f"LoD: {format_number(semantic['lod'], 1)} Solid",
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
    text_panel(fig.add_subplot(grid[3, 4]), "조립·메시 구조", "Assembly & mesh structure", semantic_lines, font)

    for column, camera in enumerate(frame["cameras"]):
        ax = fig.add_subplot(grid[4, column], projection="3d")
        plot_cityjson(ax, evidence, frame, config, alpha=0.38)
        plot_reference(ax, evidence, frame, config)
        configure_3d_axis(ax, frame, camera)
        if camera["key"] == "top":
            title_ko = "출력+참조 · 탑뷰 (공통 승인 XY 외곽)"
            title_en = "Top overlay · shared approved XY outline expected"
        else:
            title_ko = f"출력+참조 · {camera['title_ko']} (평가 전용)"
            title_en = f"Output + reference · {camera['title_en']} (evaluation only)"
        short_title(ax, title_ko, title_en, font, fontsize=8.1)

    comparison = output_reference_comparison(evidence)
    output_xyz = comparison["output_xyz"]
    reference_xyz = comparison["reference_xyz"]
    origin_values = frame["local_origin_epsg25832_xyz"]
    comparison_lines = [
        "파랑/회색/갈색 면: Roofer output",
        "주황 점선+원: reference GML (evaluation only)",
        "공통 승인 GroundSurface XY → 탑 외곽 일치 예상",
        f"exact XY set equal: {format_bool(comparison['exact_XY_coordinate_set_equal'])}",
        f"exact XYZ set equal: {format_bool(comparison['exact_XYZ_coordinate_set_equal'])}",
        f"unique XYZ output/ref: {comparison['output_unique_xyz_n']} / "
        f"{comparison['reference_unique_xyz_n']}",
        f"output SHA: {comparison['output_cityjson_sha256'][:12]}…",
        "reference SHA: "
        + ", ".join(value[:8] + "…" for value in comparison["reference_gml_sha256"]),
        f"Roofer footprint role: {comparison['roofer_footprint_source_role']}",
        "view orientation: output only; reference excluded",
        "shared bounds: seed + TSDF + output + eval reference",
        "projection: orthographic",
        "Z exaggeration: 1.0×",
        f"output Z: {output_xyz[:, 2].min():.3f}–{output_xyz[:, 2].max():.3f} m",
        f"reference Z: {reference_xyz[:, 2].min():.3f}–{reference_xyz[:, 2].max():.3f} m",
        f"origin E/N/Z: {origin_values[0]:.3f} / {origin_values[1]:.3f} / {origin_values[2]:.3f}",
        "CRS: EPSG:25832",
        "scientific verdict: null",
    ]
    text_panel(fig.add_subplot(grid[4, 4]), "중첩 범례·카메라", "Overlay legend & camera receipt", comparison_lines, font)

    fig.text(
        0.5,
        0.018,
        "정본 출력: Roofer canonical CityJSON LoD2.2 · XML CityGML export unavailable · 참조 GML은 출력 동결 후 평가 전용으로 열람",
        ha="center",
        va="center",
        fontsize=7.5,
        color=palette["charcoal"],
        fontproperties=font,
    )
    path = staging / config["outputs"]["panel"]
    fig.savefig(
        path,
        dpi=int(visual["panel_dpi"]),
        facecolor="white",
        metadata={"Software": "JointBuildGS A-prime one-file panel v4"},
    )
    plt.close(fig)
    quality = base.png_stats(path, visual["minimum_panel_pixels"])
    comparison_receipt = {
        key: value
        for key, value in comparison.items()
        if key not in {"output_xyz", "reference_xyz"}
    }
    render = {
        "layout": "5_rows_x_5_columns_single_png",
        "row_order": visual["row_order"],
        "column_order": visual["column_order"],
        "frame": frame,
        "input_locator": {
            "selected_image": image_mask["row"]["image_name"],
            "selection": image_mask["selection"],
            "mask_alignment": image_mask["mask_alignment"],
            "projection_height_canonical_z": image_mask["locator_canonical_z"],
            "footprint_role": config["input_locator_contract"]["footprint_role"],
            "pose_transform_reapplication_count": 0,
            "overlay_layers": [
                "approved_GroundSurface_XY_at_filtered_ALS_q80_upper_median_Z",
                "actual_filtered_ALS_class6_seed_projection",
                "actual_valid_supervision_support_M_j",
            ],
        },
        "seed_points_displayed_per_view": rendered_seed_points,
        "mesh_topology": topology,
        "mesh_faces_displayed_per_view": rendered_faces,
        "cityjson": evidence["cityjson_surface_stats"],
        "cityjson_render": cityjson_render,
        "output_reference_comparison": comparison_receipt,
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
    base.validate_identity(base_config, building_id, arm, replicate)
    root = output_job_dir(config, building_id, arm, replicate, output_root)
    receipt = base.load_json(root / config["outputs"]["complete"])
    require(receipt.get("schema") == RECEIPT_SCHEMA, "panel receipt schema drift")
    require(receipt.get("state") == "COMPLETE", "panel receipt is not COMPLETE")
    require(receipt.get("measurement_state") == "MEASURED", "panel receipt is not MEASURED")
    require(
        receipt.get("identity")
        == {
            "run_id": config["run_id"],
            "building_id": building_id,
            "arm": arm,
            "replicate": replicate,
        },
        "panel receipt identity drift",
    )
    require(receipt.get("scientific_verdict") is None, "receipt contains scientific verdict")
    require(receipt.get("interpretation") is None, "receipt contains interpretation")
    require(receipt.get("implementation") == implementation_records(config), "implementation hash drift")
    current_sources = {
        role: base.verify_record(record, f"receipt source {role}")
        for role, record in receipt.get("source_records", {}).items()
    }
    require(current_sources == receipt["source_records"], "source record drift")
    current_readout = base.file_record(
        base.resolve_readout_complete(base_config, building_id, arm, replicate)
    )
    require(
        receipt.get("source_readout_complete") == current_readout,
        "source readout is not the current canonical/override receipt",
    )
    locked_references = [
        base.verify_large_locked_record(record, f"reference_gml[{index}]")
        for index, record in enumerate(base_config["locked_inputs"]["reference_gml"])
    ]
    reference_receipt = receipt.get("reference_gml", {})
    require(reference_receipt.get("role") == "evaluation_only", "reference role drift")
    require(reference_receipt.get("records") == locked_references, "reference record/hash drift")
    require(
        reference_receipt.get("view_orientation_influence") is False,
        "reference changed view orientation",
    )
    require(
        reference_receipt.get("shared_bounds_influence") is True,
        "reference shared-bounds disclosure absent",
    )
    expected_files = {
        config["outputs"]["panel"],
        config["outputs"]["opacity_csv"],
        config["outputs"]["canonical_roofer_cityjson"],
        config["outputs"]["complete"],
    }
    require({path.name for path in root.iterdir()} == expected_files, "panel bundle file set drift")
    for role, filename in (
        ("panel", config["outputs"]["panel"]),
        ("opacity_csv", config["outputs"]["opacity_csv"]),
        ("canonical_roofer_cityjson", config["outputs"]["canonical_roofer_cityjson"]),
    ):
        require(receipt["outputs"][role] == output_record(root / filename), f"{role} output drift")
    base.png_stats(root / config["outputs"]["panel"], config["visual_contract"]["minimum_panel_pixels"])
    require(
        receipt["outputs"]["canonical_roofer_cityjson"]["sha256"]
        == receipt["source_records"]["canonical_roofer_cityjson"]["sha256"],
        "bundled CityJSON is not canonical",
    )
    require(receipt["publication"]["one_visual_panel_per_job"] is True, "one-panel flag absent")
    require(receipt["publication"]["receipt_written_last"] is True, "receipt-last flag absent")
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
    destination = output_job_dir(config, building_id, arm, replicate, output_root)
    receipt_path = destination / config["outputs"]["complete"]
    if receipt_path.is_file():
        return verify_bundle(config, base_config, building_id, arm, replicate, output_root)
    require(not destination.exists(), f"refusing incomplete/nonempty panel bundle: {base.display_path(destination)}")

    implementation_before = implementation_records(config)
    evidence = base.resolve_evidence(base_config, report, building_id, arm, replicate)
    evidence = augment_evidence(evidence, config)
    evidence["base_config"] = base_config
    sources_before = source_snapshot(evidence)
    references_before = [
        base.verify_large_locked_record(record, f"reference_gml[{index}]")
        for index, record in enumerate(base_config["locked_inputs"]["reference_gml"])
    ]
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{replicate}.panel-v4-staging-", dir=destination.parent))
    try:
        quality, render, font_record = render_panel(staging, config, evidence)
        opacity_path = staging / config["outputs"]["opacity_csv"]
        base.write_opacity_csv(opacity_path, evidence["opacity_rows"])
        cityjson_copy = staging / config["outputs"]["canonical_roofer_cityjson"]
        shutil.copyfile(evidence["cityjson_path"], cityjson_copy)
        with cityjson_copy.open("rb") as stream:
            os.fsync(stream.fileno())
        sources_after = source_snapshot(evidence)
        require(sources_after == sources_before, "source inputs changed during panel render")
        require(
            implementation_records(config) == implementation_before,
            "implementation dependency closure changed during panel render",
        )
        require(
            sha256_file(cityjson_copy) == sources_before["canonical_roofer_cityjson"]["sha256"],
            "canonical CityJSON copy drift",
        )
        outputs = {
            "panel": output_record(staging / config["outputs"]["panel"], destination),
            "opacity_csv": output_record(opacity_path, destination),
            "canonical_roofer_cityjson": output_record(cityjson_copy, destination),
        }
        score = score_row(evidence)
        receipt = {
            "schema": RECEIPT_SCHEMA,
            "task_id": config["task_id"],
            "state": "COMPLETE",
            "measurement_state": "MEASURED",
            "created_at": utc_now(),
            "identity": evidence["identity"],
            "source_readout_complete": evidence["source_readout_complete"],
            "source_records": sources_before,
            "reference_gml": {
                "role": "evaluation_only",
                "records": references_before,
                "opened_after_primary_readout_complete": True,
                "view_orientation_influence": False,
                "shared_bounds_influence": True,
            },
            "panel_contract": {
                "single_visual_file": True,
                "visual_filename": config["outputs"]["panel"],
                "placeholders": 0,
                "render": render,
            },
            "render_quality": quality,
            "font": font_record,
            "primary_measurements": evidence["readout"]["primary"]["measurements"],
            "p0prime_deltas": {
                "delta_roof_rms_vs_p0_refl_m": score.get("delta_roof_rms_vs_p0_refl_m"),
                "delta_roof_completeness_vs_p0_refl": score.get("delta_roof_completeness_vs_p0_refl"),
                "delta_face_count_ratio_vs_p0_refl": score.get("delta_face_count_ratio_vs_p0_refl"),
            },
            "citygml_export": evidence["serialization_capability"],
            "implementation": implementation_before,
            "outputs": outputs,
            "publication": {
                "measured_job_only": True,
                "one_visual_panel_per_job": True,
                "job_directory_atomic_publish": True,
                "overwrite_allowed": False,
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
    evidence = augment_evidence(
        base.resolve_evidence(base_config, report, building_id, arm, replicate),
        config,
    )
    evidence["base_config"] = base_config
    return {
        "state": "READY",
        "identity": evidence["identity"],
        "cityjson": evidence["cityjson_surface_stats"],
        "mesh_topology": mesh_topology_stats(evidence["mesh_faces"]),
        "frame": scene_frame(evidence, config),
        "scientific_verdict": None,
        "interpretation": None,
    }


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    result.add_argument("--output-root", type=Path)
    subparsers = result.add_subparsers(dest="command", required=True)
    for command in ("one", "check", "verify"):
        child = subparsers.add_parser(command)
        child.add_argument("building_id")
        child.add_argument("arm")
        child.add_argument("replicate")
    return result


def main(argv: Sequence[str] | None = None) -> int:
    args = parser().parse_args(argv)
    config, base_config = load_panel_config(args.config)
    report = base.load_report_module(base_config)
    if args.command == "one":
        payload = publish_job(
            config,
            base_config,
            report,
            args.building_id,
            args.arm,
            args.replicate,
            output_root=args.output_root,
        )
    elif args.command == "check":
        payload = check_job(
            config, base_config, report, args.building_id, args.arm, args.replicate
        )
    else:
        payload = verify_bundle(
            config,
            base_config,
            args.building_id,
            args.arm,
            args.replicate,
            output_root=args.output_root,
        )
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except PanelError as exc:
        print(f"[FAILED] PanelError: {exc}", file=sys.stderr)
        raise SystemExit(2)
