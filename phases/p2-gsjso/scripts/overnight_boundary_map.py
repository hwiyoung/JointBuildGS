#!/usr/bin/env python3
"""C wave CPU preparation and finalization for the 178-building boundary map.

This script never starts GS optimization.  ``prepare`` reuses frozen texture,
point-count, and dense-assembly tables and measures only projection geometry.
``finalize`` merges the separately produced MASt3R correspondence counts,
applies the fixed ladder formula, writes confusion tables, and renders the map.
LoD2 height is used only to project the scoring/classification support region.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import itertools
import json
import math
import os
import random
import subprocess
import sys
import xml.etree.ElementTree as ET
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence

os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib")
os.environ.setdefault("XDG_CACHE_HOME", "/tmp")

import matplotlib
import numpy as np
from shapely.geometry import MultiPolygon, Polygon, shape
from shapely.ops import unary_union

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import Patch  # noqa: E402


REPO = Path(__file__).resolve().parents[3]
SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import population_aux_v3 as aux  # noqa: E402
from e5_pilot_gate_tools import C001_IDS  # noqa: E402


RUN_ID = "20260716_boundary_map"
RUN_DIR = REPO / "phases/p2-gsjso/runs" / RUN_ID
JOBS_JSON = RUN_DIR / "mast3r_jobs.json"
SUPPORT_CSV = RUN_DIR / "boundary_map_support_metrics.csv"
MATCH_CSV = RUN_DIR / "mast3r_correspondence.csv"
PREP_MANIFEST = RUN_DIR / "prepare_manifest.json"
LOG = RUN_DIR / "run.log"

DOCS = REPO / "docs"
METRICS_CSV = DOCS / "boundary_map_metrics.csv"
LADDER_CSV = DOCS / "boundary_map_ladder.csv"
CONFUSION_CSV = DOCS / "boundary_map_confusion.csv"
CASES_CSV = DOCS / "boundary_map_boundary_cases.csv"
MANIFEST = DOCS / "boundary_map_manifest.json"
FIGURE = DOCS / "figs/boundary_map/boundary_map_ladder.png"

FOOTPRINTS = REPO / "results/tum_transfer/analysis/footprints_aoi.geojson"
LOWTEX = DOCS / "lowtex_v5.csv"
POINTS = DOCS / "pointcloud_attributes_v1_3.csv"
DENSE = DOCS / "regression_input_snapshot.csv"
MANUAL = DOCS / "manual_review_judgments.csv"
PRIORITY = DOCS / "bucket_crosswalk.csv"
LOD2_DIR = REPO / "phases/p0-audit/data/raw/lod2"
DATA = REPO / "phases/p0-audit/data"
IMAGE_DIR = DATA / "work/images/Images"
SCENE_REF = DATA / "work/opf/opf/scene_reference_frame.json"
CAMERAS = DATA / "work/colmap/sparse/0/cameras.txt"
IMAGES = DATA / "work/colmap/sparse/0/images.txt"

EVALUATION_MIN_AREA_M2 = 30.0
SMALL_AREA_M2 = 50.0
BOUNDARY_STEP_M = 0.5
CALIBRATION_SEED = 20260716
MODEL_REVISION = "06e7259f34c3060f322df5cb0c7b9094f57e41fc"
MODEL_SHA256 = "0a615eb05fa9db654050aa655945ee5696e7c6c1b7f93f1ee8c37249010f6feb"
MODEL_BYTES = 2_754_661_648


METRIC_FIELDS = [
    "building_id",
    "evaluation_scope",
    "priority_group",
    "priority_rank",
    "footprint_area_m2",
    "small_lt50_candidate",
    "texture_low_gradient_fraction",
    "texture_grad_p10",
    "texture_valid",
    "texture_view",
    "texture_source",
    "texture_projection_reference_height_used",
    "sfm_point_count",
    "dense_point_count",
    "point_count_source",
    "dense_assembled",
    "dense_outcome_source",
    "mast3r_correspondence_count",
    "mast3r_reciprocal_raw_count",
    "mast3r_border_count",
    "mast3r_status",
    "mast3r_view_a",
    "mast3r_view_b",
    "mast3r_crop_a_xyxy",
    "mast3r_crop_b_xyxy",
    "mast3r_model_revision",
    "mast3r_model_sha256",
    "mast3r_result_source",
    "outline_inframe_frac_max",
    "outline_inframe_frac_median",
    "outline_valid_pixel_count_max",
    "outline_valid_pixel_count_median",
    "representative_view_count",
    "representative_views_json",
    "projection_reference_height_m",
    "projection_reference_height_used",
    "projection_reference_source",
    "projection_status",
    "crs",
    "learning_runs_started",
    "new_inference_type",
]

LADDER_FIELDS = [
    "building_id",
    "footprint_area_m2",
    "small_lt50_candidate",
    "texture_low_gradient_fraction",
    "texture_threshold",
    "texture_sufficient",
    "mast3r_correspondence_count",
    "correspondence_threshold",
    "correspondence_at_or_above_threshold",
    "outline_inframe_frac_max",
    "outline_valid_pixel_count_max",
    "outline_inframe_threshold",
    "outline_pixel_threshold",
    "outline_observable",
    "formula_assignment",
    "map_assignment",
    "assignment_record_status",
    "calibration_seed",
    "calibration_or_validation",
    "dense_assembled",
    "projection_reference_height_used",
    "crs",
    "learning_runs_started",
]

CONFUSION_FIELDS = [
    "comparison",
    "subset",
    "actual_label",
    "recorded_label",
    "count",
    "n_records",
    "calibration_seed",
    "thresholds_json",
    "learning_runs_started",
]

CASE_FIELDS = [
    "building_id",
    "map_assignment",
    "footprint_area_m2",
    "texture_low_gradient_fraction",
    "mast3r_correspondence_count",
    "outline_inframe_frac_max",
    "outline_valid_pixel_count_max",
    "threshold_distance",
    "spotcheck_reason",
    "learning_runs_started",
]


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def rel(path: Path | str) -> str:
    value = Path(path)
    try:
        return str(value.resolve().relative_to(REPO.resolve()))
    except ValueError:
        return str(value.resolve())


def sha256_file(path: Path, block_size: int = 1 << 20) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(block_size), b""):
            digest.update(block)
    return digest.hexdigest()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def atomic_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(text, encoding="utf-8")
    temporary.replace(path)


def atomic_csv(path: Path, rows: Sequence[dict[str, Any]], fields: Sequence[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    with temporary.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=list(fields),
            extrasaction="ignore",
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows([{key: fmt(row.get(key)) for key in fields} for row in rows])
    temporary.replace(path)


def log(message: str) -> None:
    line = f"{now()} {message}"
    print(line, flush=True)
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")


def fmt(value: Any) -> Any:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        if not math.isfinite(value):
            return ""
        return f"{value:.6f}"
    return value


def as_float(value: Any) -> float | None:
    if value in (None, "", "none", "None"):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def as_int(value: Any) -> int | None:
    number = as_float(value)
    return int(round(number)) if number is not None else None


def bool_value(value: Any) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "y", "pass"}


def full_id(value: str) -> str:
    return value if value.startswith("DEBY_LOD2_") else f"DEBY_LOD2_{value}"


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def load_footprints() -> tuple[dict[str, Polygon | MultiPolygon], dict[str, float]]:
    payload = json.loads(FOOTPRINTS.read_text(encoding="utf-8"))
    crs = str(payload.get("crs", {}).get("properties", {}).get("name", ""))
    if "25832" not in crs:
        raise RuntimeError(f"footprint CRS mismatch: {crs!r}")
    pieces: dict[str, list[Any]] = defaultdict(list)
    source_area: dict[str, float] = {}
    for feature in payload["features"]:
        properties = feature.get("properties") or {}
        bid = full_id(str(properties["building_id"]).removeprefix("DEBY_LOD2_"))
        geom = shape(feature["geometry"])
        if not geom.is_empty:
            pieces[bid].append(geom)
        area = as_float(properties.get("area_m2"))
        if area is not None:
            source_area[bid] = source_area.get(bid, 0.0) + area
    geometries = {
        bid: unary_union(items)
        for bid, items in pieces.items()
        if items
    }
    areas = {
        bid: source_area.get(bid, float(geom.area))
        for bid, geom in geometries.items()
    }
    if len(geometries) != 199:
        raise RuntimeError(f"expected 199 footprint buildings, found {len(geometries)}")
    return geometries, areas


def load_reference_heights(wanted: set[str]) -> dict[str, float]:
    values: dict[str, list[float]] = defaultdict(list)
    for path in sorted(LOD2_DIR.glob("*.gml")):
        for _event, element in ET.iterparse(path, events=("end",)):
            if local_name(element.tag) != "Building":
                continue
            bid = next(
                (value for key, value in element.attrib.items() if local_name(key) == "id"),
                "",
            )
            if bid in wanted:
                for surface in element.iter():
                    if local_name(surface.tag) != "RoofSurface":
                        continue
                    for pos_list in surface.iter():
                        if local_name(pos_list.tag) != "posList" or not pos_list.text:
                            continue
                        numbers = np.asarray(
                            [float(item) for item in pos_list.text.split()],
                            dtype=np.float64,
                        )
                        if len(numbers) >= 3 and len(numbers) % 3 == 0:
                            values[bid].extend(numbers.reshape(-1, 3)[:, 2].tolist())
            element.clear()
    result = {
        bid: float(np.median(np.asarray(z_values, dtype=np.float64)))
        for bid, z_values in values.items()
        if z_values
    }
    missing = sorted(wanted - set(result))
    if missing:
        raise RuntimeError(f"missing LoD2 projection heights for {len(missing)} buildings: {missing[:5]}")
    return result


def polygon_exteriors(geom: Polygon | MultiPolygon) -> list[np.ndarray]:
    polygons = [geom] if isinstance(geom, Polygon) else list(geom.geoms)
    rings: list[np.ndarray] = []
    for polygon in polygons:
        ring = np.asarray(polygon.exterior.coords, dtype=np.float64)
        if len(ring) > 1 and np.allclose(ring[0], ring[-1]):
            ring = ring[:-1]
        if len(ring) >= 3:
            rings.append(ring)
    return rings


def boundary_samples(geom: Polygon | MultiPolygon, step_m: float) -> np.ndarray:
    polygons = [geom] if isinstance(geom, Polygon) else list(geom.geoms)
    output: list[tuple[float, float]] = []
    for polygon in polygons:
        line = polygon.exterior
        distances = np.arange(0.0, max(line.length, step_m), step_m)
        output.extend((line.interpolate(float(distance)).x, line.interpolate(float(distance)).y) for distance in distances)
    return np.asarray(output, dtype=np.float64)


def projected_view(
    geom: Polygon | MultiPolygon,
    roof_z: float,
    samples_xy: np.ndarray,
    cam: Any,
    width: int,
    height: int,
    params: np.ndarray,
    scene_ref: dict[str, Any],
) -> dict[str, Any] | None:
    projected_rings: list[list[list[float]]] = []
    all_uv: list[np.ndarray] = []
    for ring in polygon_exteriors(geom):
        xyz = np.column_stack([ring, np.full(len(ring), roof_z)])
        uv, front = aux.project(xyz, cam, width, height, params, scene_ref)
        finite = front & np.isfinite(uv).all(axis=1)
        if np.count_nonzero(finite) < 3:
            continue
        ring_uv = uv[finite]
        projected_rings.append(ring_uv.tolist())
        all_uv.append(ring_uv)
    if not projected_rings:
        return None
    sample_xyz = np.column_stack([samples_xy, np.full(len(samples_xy), roof_z)])
    sample_uv, sample_front = aux.project(sample_xyz, cam, width, height, params, scene_ref)
    inframe = (
        sample_front
        & np.isfinite(sample_uv).all(axis=1)
        & (sample_uv[:, 0] >= 0)
        & (sample_uv[:, 0] < width)
        & (sample_uv[:, 1] >= 0)
        & (sample_uv[:, 1] < height)
    )
    fraction = float(np.count_nonzero(inframe) / max(len(sample_uv), 1))
    rounded = np.rint(sample_uv[inframe]).astype(np.int64)
    pixel_count = int(len(np.unique(rounded, axis=0))) if len(rounded) else 0
    centroid = np.asarray([[geom.centroid.x, geom.centroid.y, roof_z]], dtype=np.float64)
    centroid_ellipsoid = aux.as_ellipsoidal_points(centroid)[0]
    vector = np.asarray(cam.center, dtype=np.float64) - centroid_ellipsoid
    distance = float(np.linalg.norm(vector))
    zenith = (
        float(np.degrees(np.arccos(np.clip(vector[2] / distance, -1.0, 1.0))))
        if distance > 1e-9
        else 180.0
    )
    return {
        "name": cam.name,
        "image_path": rel(IMAGE_DIR / cam.name),
        "inframe_frac": fraction,
        "valid_pixel_count": pixel_count,
        "zenith_deg": zenith,
        "camera_center": [float(value) for value in cam.center],
        "projected_rings": projected_rings,
        "all_uv": np.vstack(all_uv).tolist(),
    }


def crop_box_4x3(
    uv_values: Iterable[Iterable[float]],
    image_width: int,
    image_height: int,
    margin_px: int = 32,
    minimum_width: int = 256,
) -> tuple[int, int, int, int]:
    uv = np.asarray(list(uv_values), dtype=np.float64)
    finite = np.isfinite(uv).all(axis=1)
    uv = uv[finite]
    if not len(uv):
        raise RuntimeError("no projected polygon pixels")
    target_width = int(math.ceil(float(np.ptp(uv[:, 0])) + 1 + 2 * margin_px))
    target_height = int(math.ceil(float(np.ptp(uv[:, 1])) + 1 + 2 * margin_px))
    width = max(minimum_width, target_width, int(math.ceil(target_height * 4.0 / 3.0)))
    width = int(math.ceil(width / 16.0) * 16)
    maximum_width = min(image_width, int(math.floor(image_height * 4.0 / 3.0)))
    maximum_width = max(16, maximum_width - maximum_width % 16)
    width = min(width, maximum_width)
    height = width * 3 // 4
    center_x = float(np.mean([np.min(uv[:, 0]), np.max(uv[:, 0])]))
    center_y = float(np.mean([np.min(uv[:, 1]), np.max(uv[:, 1])]))
    x0 = min(max(0, int(round(center_x - width / 2))), image_width - width)
    y0 = min(max(0, int(round(center_y - height / 2))), image_height - height)
    return x0, y0, x0 + width, y0 + height


def select_views(candidates: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], str]:
    usable = [
        row
        for row in candidates
        if row["inframe_frac"] > 0.0 and row["valid_pixel_count"] >= 3
    ]
    usable.sort(
        key=lambda row: (
            -row["inframe_frac"],
            -row["valid_pixel_count"],
            row["zenith_deg"],
            row["name"],
        )
    )
    pool = usable[:12]
    if len(pool) < 2:
        return pool[:1], "fewer_than_two_projectable_views"
    pairs = []
    for left, right in itertools.combinations(pool, 2):
        baseline = float(
            np.linalg.norm(
                np.asarray(left["camera_center"], dtype=np.float64)[:2]
                - np.asarray(right["camera_center"], dtype=np.float64)[:2]
            )
        )
        pairs.append(
            (
                (
                    -min(left["inframe_frac"], right["inframe_frac"]),
                    -min(left["valid_pixel_count"], right["valid_pixel_count"]),
                    -baseline,
                    max(left["zenith_deg"], right["zenith_deg"]),
                    left["name"],
                    right["name"],
                ),
                left,
                right,
            )
        )
    pairs.sort(key=lambda item: item[0])
    _key, left, right = pairs[0]
    selected = [left, right]
    selected.extend(row for row in usable if row["name"] not in {left["name"], right["name"]})
    return selected[:3], "pair=max(min in-frame,min pixels,horizontal baseline); third=single-view rank"


def source_tables() -> tuple[
    dict[str, dict[str, str]],
    dict[tuple[str, str], dict[str, str]],
    dict[str, dict[str, str]],
    list[dict[str, str]],
    list[str],
]:
    texture = {row["building_id"]: row for row in read_csv(LOWTEX)}
    points = {(row["building_id"], row["arm"]): row for row in read_csv(POINTS)}
    dense = {
        row["building_id"]: row
        for row in read_csv(DENSE)
        if row.get("arm") == "raw_dense"
    }
    manual = read_csv(MANUAL)
    priority = [row["building_id"] for row in read_csv(PRIORITY)]
    if len(texture) != 199 or len({bid for bid, _arm in points}) != 199 or len(dense) != 199:
        raise RuntimeError("source table population drift")
    if len(manual) != 44 or len(priority) != 48:
        raise RuntimeError("manual-label or priority-table count drift")
    return texture, points, dense, manual, priority


def priority_order(
    evaluation: set[str],
    manual_ids: set[str],
    priority_ids: list[str],
) -> tuple[list[str], dict[str, tuple[str, int]]]:
    support = evaluation | manual_ids | set(C001_IDS) | set(priority_ids)
    ordered: list[str] = []
    groups: dict[str, tuple[str, int]] = {}

    def add(values: Iterable[str], group: str) -> None:
        for bid in values:
            if bid in support and bid not in groups:
                ordered.append(bid)
                groups[bid] = (group, len(ordered))

    add(priority_ids, "surface_failure_48")
    add(C001_IDS, "c001_18")
    add(sorted(evaluation), "evaluation_remainder")
    add(sorted(support), "support_remainder")
    return ordered, groups


def prepare() -> None:
    RUN_DIR.mkdir(parents=True, exist_ok=True)
    atomic_text(LOG, "")
    log("prepare start learning_runs_started=0")
    geometries, areas = load_footprints()
    evaluation = {bid for bid, area in areas.items() if area >= EVALUATION_MIN_AREA_M2}
    if len(evaluation) != 178:
        raise RuntimeError(f"evaluation population drift: {len(evaluation)} != 178")
    texture, point_rows, dense_rows, manual_rows, priority_ids = source_tables()
    manual_ids = {row["building_id"] for row in manual_rows}
    ordered, groups = priority_order(evaluation, manual_ids, priority_ids)
    if len(ordered) != 185:
        raise RuntimeError(f"support population drift: {len(ordered)} != 185")
    heights = load_reference_heights(set(ordered))

    scene_ref = json.loads(SCENE_REF.read_text(encoding="utf-8"))
    width, height, params = aux.parse_cam_model(CAMERAS)
    cameras = [
        camera
        for camera in aux.parse_cameras(IMAGES, scene_ref)
        if (IMAGE_DIR / camera.name).is_file()
    ]
    if len(cameras) < 2:
        raise RuntimeError("insufficient camera/image records")
    log(f"prepare population evaluation=178 support={len(ordered)} cameras={len(cameras)}")

    support_rows: list[dict[str, Any]] = []
    jobs: list[dict[str, Any]] = []
    for index, bid in enumerate(ordered, start=1):
        geom = geometries[bid]
        roof_z = heights[bid]
        samples = boundary_samples(geom, BOUNDARY_STEP_M)
        candidates: list[dict[str, Any]] = []
        for camera in cameras:
            row = projected_view(
                geom,
                roof_z,
                samples,
                camera,
                width,
                height,
                params,
                scene_ref,
            )
            if row is not None:
                candidates.append(row)
        selected, selection_status = select_views(candidates)
        representative = [
            {
                "name": row["name"],
                "zenith_deg": round(row["zenith_deg"], 6),
                "outline_inframe_frac": round(row["inframe_frac"], 6),
                "outline_valid_pixel_count": row["valid_pixel_count"],
            }
            for row in selected
        ]
        fractions = [row["inframe_frac"] for row in selected]
        pixels = [row["valid_pixel_count"] for row in selected]
        projection_status = "prepared" if len(selected) >= 2 else selection_status
        job_status = "pending" if len(selected) >= 2 else "prepare_failed"
        if len(selected) >= 2:
            left, right = selected[:2]
            crop_left = crop_box_4x3(left["all_uv"], width, height)
            crop_right = crop_box_4x3(right["all_uv"], width, height)
            jobs.append(
                {
                    "building_id": bid,
                    "evaluation_scope": "evaluation_178" if bid in evaluation else "calibration_support_only",
                    "priority_group": groups[bid][0],
                    "priority_rank": groups[bid][1],
                    "view_a": left["name"],
                    "view_b": right["name"],
                    "image_a": left["image_path"],
                    "image_b": right["image_path"],
                    "crop_a_xyxy": list(crop_left),
                    "crop_b_xyxy": list(crop_right),
                    "projected_rings_a": left["projected_rings"],
                    "projected_rings_b": right["projected_rings"],
                    "source_width": width,
                    "source_height": height,
                    "projection_reference_height_m": roof_z,
                    "projection_reference_source": "LoD2 CityGML; measurement/classification projection only",
                    "learning_runs_started": 0,
                }
            )
        tex = texture.get(bid, {})
        sparse = point_rows.get((bid, "raw_sparse_e5p"), {})
        dense_point = point_rows.get((bid, "raw_dense"), {})
        dense_outcome = dense_rows.get(bid, {})
        support_rows.append(
            {
                "building_id": bid,
                "evaluation_scope": "evaluation_178" if bid in evaluation else "calibration_support_only",
                "priority_group": groups[bid][0],
                "priority_rank": groups[bid][1],
                "footprint_area_m2": areas[bid],
                "small_lt50_candidate": areas[bid] < SMALL_AREA_M2,
                "texture_low_gradient_fraction": as_float(tex.get("roof_lowtex_v5")),
                "texture_grad_p10": as_float(tex.get("roof_grad_p10_v5")),
                "texture_valid": tex.get("lowtex_valid", ""),
                "texture_view": tex.get("lowtex_v5_view", ""),
                "texture_source": rel(LOWTEX),
                "texture_projection_reference_height_used": True,
                "sfm_point_count": as_int(sparse.get("n_points_footprint")),
                "dense_point_count": as_int(dense_point.get("n_points_footprint")),
                "point_count_source": rel(POINTS),
                "dense_assembled": as_int(dense_outcome.get("assembled")),
                "dense_outcome_source": rel(DENSE),
                "mast3r_correspondence_count": None,
                "mast3r_reciprocal_raw_count": None,
                "mast3r_border_count": None,
                "mast3r_status": job_status,
                "mast3r_view_a": selected[0]["name"] if len(selected) >= 1 else "",
                "mast3r_view_b": selected[1]["name"] if len(selected) >= 2 else "",
                "mast3r_crop_a_xyxy": (
                    ";".join(str(value) for value in jobs[-1]["crop_a_xyxy"])
                    if len(selected) >= 2
                    else ""
                ),
                "mast3r_crop_b_xyxy": (
                    ";".join(str(value) for value in jobs[-1]["crop_b_xyxy"])
                    if len(selected) >= 2
                    else ""
                ),
                "mast3r_model_revision": MODEL_REVISION,
                "mast3r_model_sha256": MODEL_SHA256,
                "mast3r_result_source": rel(MATCH_CSV),
                "outline_inframe_frac_max": max(fractions) if fractions else None,
                "outline_inframe_frac_median": float(np.median(fractions)) if fractions else None,
                "outline_valid_pixel_count_max": max(pixels) if pixels else None,
                "outline_valid_pixel_count_median": float(np.median(pixels)) if pixels else None,
                "representative_view_count": len(selected),
                "representative_views_json": json.dumps(
                    representative,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ),
                "projection_reference_height_m": roof_z,
                "projection_reference_height_used": True,
                "projection_reference_source": "LoD2 CityGML; measurement/classification projection only",
                "projection_status": projection_status,
                "crs": "EPSG:25832",
                "learning_runs_started": 0,
                "new_inference_type": "MASt3R correspondence only",
            }
        )
        if index % 10 == 0 or index == len(ordered):
            atomic_csv(SUPPORT_CSV, support_rows, METRIC_FIELDS)
            atomic_csv(
                METRICS_CSV,
                [row for row in support_rows if row["evaluation_scope"] == "evaluation_178"],
                METRIC_FIELDS,
            )
            log(f"prepare progress {index}/{len(ordered)} jobs={len(jobs)}")

    jobs_payload = {
        "schema": "jointbuildgs.boundary_map.mast3r_jobs.v1",
        "created_utc": now(),
        "evaluation_population": 178,
        "support_population": len(ordered),
        "priority_rule": "surface-failure 48, then C001 18 not already listed, then evaluation remainder",
        "crop_rule": "projected footprint at LoD2 median roof height; 32px margin; exact 4:3; min 256x192; resize 512x384",
        "pair_rule": "maximize minimum outline in-frame fraction, then minimum valid outline pixels, then horizontal camera baseline",
        "jobs": jobs,
        "learning_runs_started": 0,
        "new_inference_type": "MASt3R correspondence only",
    }
    atomic_text(JOBS_JSON, json.dumps(jobs_payload, ensure_ascii=False, indent=2) + "\n")
    source_paths = [FOOTPRINTS, LOWTEX, POINTS, DENSE, MANUAL, PRIORITY, SCENE_REF, CAMERAS, IMAGES, Path(__file__)]
    manifest = {
        "schema": "jointbuildgs.boundary_map.prepare.v1",
        "created_utc": now(),
        "git_head_at_measurement": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=REPO, text=True
        ).strip(),
        "evaluation_rule": f"footprint_area_m2 >= {EVALUATION_MIN_AREA_M2}",
        "evaluation_population": len(evaluation),
        "support_population": len(ordered),
        "support_only_buildings": sorted(set(ordered) - evaluation),
        "manual_label_population": len(manual_ids),
        "priority_population": len(priority_ids),
        "mast3r_job_count": len(jobs),
        "projection_reference_height_used": True,
        "projection_reference_source": "LoD2 CityGML; measurement/classification projection only",
        "source_sha256": {
            rel(path): sha256_file(path)
            for path in source_paths
        },
        "output_sha256": {
            rel(path): sha256_file(path)
            for path in [SUPPORT_CSV, METRICS_CSV, JOBS_JSON, LOG]
        },
        "learning_runs_started": 0,
        "new_inference_runs": 0,
        "interpretation_or_verdict": None,
    }
    atomic_text(PREP_MANIFEST, json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    log(f"prepare complete evaluation=178 support={len(ordered)} jobs={len(jobs)} learning_runs_started=0")


def merge_matches(rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    matches = {
        row["building_id"]: row
        for row in read_csv(MATCH_CSV)
    } if MATCH_CSV.is_file() else {}
    merged: list[dict[str, Any]] = []
    for row in rows:
        output: dict[str, Any] = dict(row)
        match = matches.get(row["building_id"])
        if match:
            output.update(
                {
                    "mast3r_correspondence_count": as_int(match.get("roof_correspondence_count")),
                    "mast3r_reciprocal_raw_count": as_int(match.get("reciprocal_raw_count")),
                    "mast3r_border_count": as_int(match.get("border_match_count")),
                    "mast3r_status": match.get("status", ""),
                    "mast3r_view_a": match.get("view_a", output.get("mast3r_view_a", "")),
                    "mast3r_view_b": match.get("view_b", output.get("mast3r_view_b", "")),
                    "mast3r_crop_a_xyxy": match.get("crop_a_xyxy", output.get("mast3r_crop_a_xyxy", "")),
                    "mast3r_crop_b_xyxy": match.get("crop_b_xyxy", output.get("mast3r_crop_b_xyxy", "")),
                }
            )
        merged.append(output)
    return merged


def manual_expected(label: str) -> str:
    if label == "무텍스처":
        return "2층"
    if "재질" in label or "저조도" in label:
        return "2층-경계"
    return "1층"


def assign_formula(
    row: dict[str, Any],
    thresholds: dict[str, float],
) -> tuple[str, dict[str, bool | None]]:
    texture = as_float(row.get("texture_low_gradient_fraction"))
    correspondence = as_int(row.get("mast3r_correspondence_count"))
    outline_fraction = as_float(row.get("outline_inframe_frac_max"))
    outline_pixels = as_float(row.get("outline_valid_pixel_count_max"))
    texture_sufficient = (
        texture < thresholds["texture_low_gradient_fraction"]
        if texture is not None
        else None
    )
    correspondence_sufficient = (
        correspondence >= thresholds["mast3r_correspondence_count"]
        if correspondence is not None
        else None
    )
    outline_observable = (
        outline_fraction >= thresholds["outline_inframe_frac"]
        and outline_pixels >= thresholds["outline_valid_pixel_count"]
        if outline_fraction is not None and outline_pixels is not None
        else None
    )
    if texture_sufficient is True:
        assignment = "1층"
    elif texture_sufficient is None:
        assignment = "미측정(2파 예약)"
    elif correspondence_sufficient is True:
        assignment = "2층"
    elif correspondence_sufficient is None:
        assignment = "미측정(2파 예약)"
    elif outline_observable is True:
        assignment = "2층-경계"
    elif outline_observable is False:
        assignment = "3층"
    else:
        assignment = "미측정(2파 예약)"
    return assignment, {
        "texture_sufficient": texture_sufficient,
        "correspondence_sufficient": correspondence_sufficient,
        "outline_observable": outline_observable,
    }


def candidate_thresholds(values: Sequence[float], integer: bool = False) -> list[float]:
    unique = sorted(set(float(value) for value in values if math.isfinite(float(value))))
    if not unique:
        return [0.0]
    candidates = [unique[0] - (1.0 if integer else 1e-6)]
    candidates.extend((left + right) / 2.0 for left, right in zip(unique, unique[1:]))
    candidates.append(unique[-1] + (1.0 if integer else 1e-6))
    if integer:
        candidates = sorted(set(float(max(0, math.ceil(value))) for value in candidates))
    return candidates


def calibrate_thresholds(
    support_rows: list[dict[str, Any]],
    manual_rows: list[dict[str, str]],
) -> tuple[dict[str, float], set[str], set[str], dict[str, str]]:
    manual_by_id = {row["building_id"]: row for row in manual_rows}
    ids = sorted(manual_by_id)
    rng = random.Random(CALIBRATION_SEED)
    rng.shuffle(ids)
    calibration = set(ids[: len(ids) // 2])
    validation = set(ids[len(ids) // 2 :])
    if len(calibration) != 22 or len(validation) != 22:
        raise RuntimeError("manual split drift")
    by_id = {row["building_id"]: row for row in support_rows}
    expected = {bid: manual_expected(manual_by_id[bid]["label"]) for bid in ids}
    calibration_rows = [by_id[bid] for bid in sorted(calibration)]

    texture_candidates = candidate_thresholds(
        [
            value
            for row in calibration_rows
            if (value := as_float(row.get("texture_low_gradient_fraction"))) is not None
        ]
    )
    match_candidates = candidate_thresholds(
        [
            float(value)
            for row in calibration_rows
            if (value := as_int(row.get("mast3r_correspondence_count"))) is not None
        ],
        integer=True,
    )
    outline_fraction_candidates = candidate_thresholds(
        [
            value
            for row in calibration_rows
            if (value := as_float(row.get("outline_inframe_frac_max"))) is not None
        ]
    )
    outline_pixel_candidates = candidate_thresholds(
        [
            float(value)
            for row in calibration_rows
            if (value := as_int(row.get("outline_valid_pixel_count_max"))) is not None
        ],
        integer=True,
    )

    best_key: tuple[Any, ...] | None = None
    best_thresholds: dict[str, float] | None = None
    for texture_threshold, match_threshold, fraction_threshold, pixel_threshold in itertools.product(
        texture_candidates,
        match_candidates,
        outline_fraction_candidates,
        outline_pixel_candidates,
    ):
        thresholds = {
            "texture_low_gradient_fraction": float(texture_threshold),
            "mast3r_correspondence_count": float(match_threshold),
            "outline_inframe_frac": float(fraction_threshold),
            "outline_valid_pixel_count": float(pixel_threshold),
        }
        exact = 0
        binary = 0
        usable = 0
        for row in calibration_rows:
            assignment, flags = assign_formula(row, thresholds)
            if assignment == "미측정(2파 예약)":
                continue
            usable += 1
            actual = expected[row["building_id"]]
            exact += int(assignment == actual)
            binary += int(
                (flags["texture_sufficient"] is True)
                == (actual == "1층")
            )
        key = (
            -exact,
            -binary,
            -usable,
            texture_threshold,
            match_threshold,
            fraction_threshold,
            pixel_threshold,
        )
        if best_key is None or key < best_key:
            best_key = key
            best_thresholds = thresholds
    if best_thresholds is None:
        raise RuntimeError("threshold calibration produced no candidate")
    return best_thresholds, calibration, validation, expected


def confusion_rows(
    ladder: list[dict[str, Any]],
    support_rows: list[dict[str, Any]],
    manual_rows: list[dict[str, str]],
    calibration: set[str],
    validation: set[str],
    expected: dict[str, str],
    thresholds: dict[str, float],
) -> list[dict[str, Any]]:
    threshold_json = json.dumps(thresholds, sort_keys=True, separators=(",", ":"))
    support_by_id = {row["building_id"]: row for row in support_rows}
    output: list[dict[str, Any]] = []

    def matrix(
        comparison: str,
        subset: str,
        pairs: Sequence[tuple[str, str]],
    ) -> None:
        counts: dict[tuple[str, str], int] = defaultdict(int)
        for actual, recorded in pairs:
            counts[(actual, recorded)] += 1
        for (actual, recorded), count in sorted(counts.items()):
            output.append(
                {
                    "comparison": comparison,
                    "subset": subset,
                    "actual_label": actual,
                    "recorded_label": recorded,
                    "count": count,
                    "n_records": len(pairs),
                    "calibration_seed": CALIBRATION_SEED,
                    "thresholds_json": threshold_json,
                    "learning_runs_started": 0,
                }
            )

    manual_pairs: list[tuple[str, str]] = []
    texture_pairs: list[tuple[str, str]] = []
    for bid in sorted(validation):
        row = support_by_id[bid]
        assignment, flags = assign_formula(row, thresholds)
        manual_pairs.append((expected[bid], assignment))
        actual_texture = "texture_sufficient" if expected[bid] == "1층" else "texture_insufficient"
        recorded_texture = (
            "texture_sufficient"
            if flags["texture_sufficient"] is True
            else ("texture_insufficient" if flags["texture_sufficient"] is False else "unmeasured")
        )
        texture_pairs.append((actual_texture, recorded_texture))
    matrix("manual_ladder_validation", "manual_validation_22", manual_pairs)
    matrix("manual_texture_validation", "manual_validation_22", texture_pairs)

    dense_pairs = []
    for row in ladder:
        dense = as_int(row.get("dense_assembled"))
        if dense is None:
            continue
        dense_pairs.append(
            (
                "dense_success" if dense == 1 else "dense_not_success",
                "tier1" if row["formula_assignment"] == "1층" else "not_tier1",
            )
        )
    matrix("tier1_vs_dense_success", "evaluation_178", dense_pairs)

    split_pairs = []
    for bid in sorted(calibration):
        split_pairs.append(("calibration", expected[bid]))
    for bid in sorted(validation):
        split_pairs.append(("validation", expected[bid]))
    matrix("manual_split_inventory", "manual_44", split_pairs)
    return output


def make_map(
    geometries: dict[str, Polygon | MultiPolygon],
    ladder: list[dict[str, Any]],
) -> None:
    colors = {
        "1층": "#2ca25f",
        "2층": "#3182bd",
        "2층-경계": "#fdae6b",
        "3층": "#de2d26",
        "판별불가": "#969696",
        "미측정(2파 예약)": "#d9d9d9",
    }
    display_labels = {
        "1층": "Tier 1",
        "2층": "Tier 2",
        "2층-경계": "Tier 2-boundary",
        "3층": "Tier 3",
        "판별불가": "indeterminate",
        "미측정(2파 예약)": "unmeasured (wave 2)",
    }
    figure, axis = plt.subplots(figsize=(13, 10), dpi=190)
    for row in ladder:
        geom = geometries[row["building_id"]]
        polygons = [geom] if isinstance(geom, Polygon) else list(geom.geoms)
        color = colors.get(row["map_assignment"], "#ffffff")
        for polygon in polygons:
            x, y = polygon.exterior.xy
            axis.fill(x, y, facecolor=color, edgecolor="#303030", linewidth=0.28)
    axis.set_aspect("equal")
    axis.ticklabel_format(style="plain", useOffset=False)
    axis.set_xlabel("Easting [m], EPSG:25832")
    axis.set_ylabel("Northing [m], EPSG:25832")
    axis.set_title("Boundary-map ladder records (178 buildings)")
    counts: dict[str, int] = defaultdict(int)
    for row in ladder:
        counts[row["map_assignment"]] += 1
    order = ["1층", "2층", "2층-경계", "3층", "판별불가", "미측정(2파 예약)"]
    axis.legend(
        handles=[
            Patch(
                facecolor=colors[label],
                edgecolor="#303030",
                label=f"{display_labels[label]} (n={counts[label]})",
            )
            for label in order
            if counts[label]
        ],
        loc="best",
        fontsize=8,
    )
    axis.grid(alpha=0.12)
    figure.tight_layout()
    FIGURE.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(FIGURE)
    plt.close(figure)


def boundary_cases(
    ladder: list[dict[str, Any]],
    thresholds: dict[str, float],
) -> list[dict[str, Any]]:
    candidates: list[tuple[float, dict[str, Any], str]] = []
    for row in ladder:
        texture = as_float(row.get("texture_low_gradient_fraction"))
        match = as_float(row.get("mast3r_correspondence_count"))
        outline_fraction = as_float(row.get("outline_inframe_frac_max"))
        outline_pixels = as_float(row.get("outline_valid_pixel_count_max"))
        distances = []
        reasons = []
        if texture is not None:
            distances.append(abs(texture - thresholds["texture_low_gradient_fraction"]))
            reasons.append(
                f"low-gradient={texture:.3f}, threshold={thresholds['texture_low_gradient_fraction']:.3f}"
            )
        if match is not None:
            scale = max(thresholds["mast3r_correspondence_count"], 1.0)
            distances.append(abs(match - thresholds["mast3r_correspondence_count"]) / scale)
            reasons.append(
                f"correspondence={int(match)}, threshold={int(thresholds['mast3r_correspondence_count'])}"
            )
        if outline_fraction is not None:
            distances.append(abs(outline_fraction - thresholds["outline_inframe_frac"]))
            reasons.append(
                f"outline-inframe={outline_fraction:.3f}, threshold={thresholds['outline_inframe_frac']:.3f}"
            )
        if outline_pixels is not None:
            scale = max(thresholds["outline_valid_pixel_count"], 1.0)
            distances.append(abs(outline_pixels - thresholds["outline_valid_pixel_count"]) / scale)
        if row["formula_assignment"] == "미측정(2파 예약)":
            distance = -1.0
            reason = "MASt3R correspondence pending or projection metric missing"
        else:
            distance = min(distances) if distances else math.inf
            reason = "; ".join(reasons)
        candidates.append((distance, row, reason))
    candidates.sort(key=lambda item: (item[0], item[1]["building_id"]))
    output = []
    for distance, row, reason in candidates[:15]:
        output.append(
            {
                "building_id": row["building_id"],
                "map_assignment": row["map_assignment"],
                "footprint_area_m2": as_float(row.get("footprint_area_m2")),
                "texture_low_gradient_fraction": as_float(row.get("texture_low_gradient_fraction")),
                "mast3r_correspondence_count": as_int(row.get("mast3r_correspondence_count")),
                "outline_inframe_frac_max": as_float(row.get("outline_inframe_frac_max")),
                "outline_valid_pixel_count_max": as_int(row.get("outline_valid_pixel_count_max")),
                "threshold_distance": distance,
                "spotcheck_reason": reason,
                "learning_runs_started": 0,
            }
        )
    return output


def finalize() -> None:
    log("finalize start learning_runs_started=0")
    support_rows = merge_matches(read_csv(SUPPORT_CSV))
    manual_rows = read_csv(MANUAL)
    thresholds, calibration, validation, expected = calibrate_thresholds(support_rows, manual_rows)
    support_by_id = {row["building_id"]: row for row in support_rows}
    evaluation_rows = [
        row
        for row in support_rows
        if row["evaluation_scope"] == "evaluation_178"
    ]
    if len(evaluation_rows) != 178:
        raise RuntimeError(f"final evaluation row drift: {len(evaluation_rows)}")
    ladder: list[dict[str, Any]] = []
    for row in sorted(evaluation_rows, key=lambda item: item["building_id"]):
        assignment, flags = assign_formula(row, thresholds)
        small = bool_value(row.get("small_lt50_candidate"))
        map_assignment = "판별불가" if small else assignment
        split = (
            "calibration"
            if row["building_id"] in calibration
            else ("validation" if row["building_id"] in validation else "not_manual")
        )
        ladder.append(
            {
                "building_id": row["building_id"],
                "footprint_area_m2": as_float(row.get("footprint_area_m2")),
                "small_lt50_candidate": small,
                "texture_low_gradient_fraction": as_float(row.get("texture_low_gradient_fraction")),
                "texture_threshold": thresholds["texture_low_gradient_fraction"],
                "texture_sufficient": flags["texture_sufficient"],
                "mast3r_correspondence_count": as_int(row.get("mast3r_correspondence_count")),
                "correspondence_threshold": thresholds["mast3r_correspondence_count"],
                "correspondence_at_or_above_threshold": flags["correspondence_sufficient"],
                "outline_inframe_frac_max": as_float(row.get("outline_inframe_frac_max")),
                "outline_valid_pixel_count_max": as_int(row.get("outline_valid_pixel_count_max")),
                "outline_inframe_threshold": thresholds["outline_inframe_frac"],
                "outline_pixel_threshold": thresholds["outline_valid_pixel_count"],
                "outline_observable": flags["outline_observable"],
                "formula_assignment": assignment,
                "map_assignment": map_assignment,
                "assignment_record_status": (
                    "complete"
                    if assignment != "미측정(2파 예약)"
                    else "unmeasured_second_wave_reserved"
                ),
                "calibration_seed": CALIBRATION_SEED,
                "calibration_or_validation": split,
                "dense_assembled": as_int(row.get("dense_assembled")),
                "projection_reference_height_used": True,
                "crs": "EPSG:25832",
                "learning_runs_started": 0,
            }
        )
    confusion = confusion_rows(
        ladder,
        support_rows,
        manual_rows,
        calibration,
        validation,
        expected,
        thresholds,
    )
    cases = boundary_cases(ladder, thresholds)
    geometries, _areas = load_footprints()
    make_map(geometries, ladder)
    atomic_csv(SUPPORT_CSV, support_rows, METRIC_FIELDS)
    atomic_csv(METRICS_CSV, evaluation_rows, METRIC_FIELDS)
    atomic_csv(LADDER_CSV, ladder, LADDER_FIELDS)
    atomic_csv(CONFUSION_CSV, confusion, CONFUSION_FIELDS)
    atomic_csv(CASES_CSV, cases, CASE_FIELDS)

    outputs = [METRICS_CSV, LADDER_CSV, CONFUSION_CSV, CASES_CSV, FIGURE, SUPPORT_CSV, MATCH_CSV, JOBS_JSON, LOG]
    source_paths = [FOOTPRINTS, LOWTEX, POINTS, DENSE, MANUAL, PRIORITY, PREP_MANIFEST, Path(__file__)]
    match_rows = read_csv(MATCH_CSV) if MATCH_CSV.is_file() else []
    payload = {
        "schema": "jointbuildgs.boundary_map.v1",
        "created_utc": now(),
        "git_head_at_measurement": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=REPO, text=True
        ).strip(),
        "branch": subprocess.check_output(
            ["git", "branch", "--show-current"], cwd=REPO, text=True
        ).strip(),
        "evaluation_population": 178,
        "support_population": len(support_rows),
        "manual_split_seed": CALIBRATION_SEED,
        "manual_calibration_buildings": sorted(calibration),
        "manual_validation_buildings": sorted(validation),
        "manual_expected_mapping": {
            "무텍스처": "2층",
            "label containing 재질 or 저조도": "2층-경계",
            "remaining manual labels": "1층",
        },
        "threshold_selection": (
            "grid search on calibration 22; maximize exact mapped-tier records, then texture-binary records, "
            "then measured records; numeric threshold tuple ascending"
        ),
        "thresholds": thresholds,
        "ladder_formula": (
            "texture sufficient -> 1층; texture insufficient and correspondence >= threshold -> 2층; "
            "texture insufficient and correspondence < threshold and outline observable -> 2층-경계; "
            "all three below -> 3층"
        ),
        "small_rule": "area < 50 m2 retained in formula_assignment and recorded as map_assignment=판별불가",
        "second_wave_buildings": sorted(
            row["building_id"]
            for row in ladder
            if row["assignment_record_status"] == "unmeasured_second_wave_reserved"
        ),
        "mast3r_completed_rows": sum(row.get("status") == "complete" for row in match_rows),
        "mast3r_result_rows": len(match_rows),
        "mast3r_model": {
            "revision": MODEL_REVISION,
            "weights_sha256": MODEL_SHA256,
            "weights_bytes": MODEL_BYTES,
        },
        "projection_reference_height_used": True,
        "projection_reference_source": "LoD2 CityGML; measurement/classification projection only",
        "source_sha256": {
            rel(path): sha256_file(path)
            for path in source_paths
            if path.is_file()
        },
        "output_sha256": {
            rel(path): sha256_file(path)
            for path in outputs
            if path.is_file()
        },
        "learning_runs_started": 0,
        "new_inference_type": "MASt3R correspondence only",
        "interpretation_or_verdict": None,
    }
    atomic_text(MANIFEST, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    log(
        f"finalize complete metrics={len(evaluation_rows)} ladder={len(ladder)} "
        f"match_rows={len(match_rows)} second_wave={len(payload['second_wave_buildings'])} "
        "learning_runs_started=0"
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("prepare", "finalize"))
    args = parser.parse_args()
    if args.command == "prepare":
        prepare()
    else:
        finalize()


if __name__ == "__main__":
    main()
