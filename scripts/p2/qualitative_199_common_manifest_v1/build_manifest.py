#!/usr/bin/env python3
"""Build the outcome-free 199-building camera/view/crop manifest."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np

from scripts.evidence_and_attributes.population_analysis import population_aux_v3 as projection
from scripts.p2.utarget199_presentation_v5.render import load_references


REPO = Path(__file__).resolve().parents[3]
DEFAULT_CONFIG = REPO / "configs/p2/qualitative_199_common_manifest_v1/contract_v1.json"
POINT_DTYPE = np.dtype(
    [
        ("x", "<f4"),
        ("y", "<f4"),
        ("z", "<f4"),
        ("red", "u1"),
        ("green", "u1"),
        ("blue", "u1"),
    ]
)


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


def verify_hash(path: Path, expected: str, label: str) -> dict[str, Any]:
    size, actual = sha256_file(path)
    if actual != expected:
        raise RuntimeError(f"{label} hash mismatch: expected {expected}, got {actual}")
    return {"path": str(path), "bytes": size, "sha256": actual, "verification": "sha256_rehash"}


def verify_size(path: Path, expected: int, label: str) -> None:
    actual = path.stat().st_size
    if actual != expected:
        raise RuntimeError(f"{label} size mismatch: expected {expected}, got {actual}")


def write_new(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(data)


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def load_roster(path: Path, expected_count: int) -> list[dict[str, Any]]:
    by_building: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in read_jsonl(path):
        by_building[str(row["building_id"])].append(row)
    if len(by_building) != expected_count:
        raise RuntimeError(f"expected {expected_count} buildings, found {len(by_building)}")
    expected_methods = {"C1_L_upper", "C2_MVS", "C3_GS_image"}
    records = []
    for building_id in sorted(by_building):
        rows = by_building[building_id]
        if {str(row["method_id"]) for row in rows} != expected_methods:
            raise RuntimeError(f"three-method roster drifted: {building_id}")
        bboxes = {
            tuple(float(row[key]) for key in ("bbox_min_x", "bbox_min_y", "bbox_max_x", "bbox_max_y"))
            for row in rows
        }
        if len(bboxes) != 1:
            raise RuntimeError(f"building bbox drifted across methods: {building_id}")
        bbox = next(iter(bboxes))
        records.append({"building_id": building_id, "bbox_xy": list(bbox)})
    return records


def load_xyzrgb_ply(path: Path) -> tuple[np.memmap, int]:
    with path.open("rb") as stream:
        lines = []
        while True:
            raw = stream.readline()
            if not raw:
                raise RuntimeError("dense PLY is missing end_header")
            line = raw.decode("ascii").rstrip("\r\n")
            lines.append(line)
            if line == "end_header":
                break
        offset = stream.tell()
    if lines[:2] != ["ply", "format binary_little_endian 1.0"]:
        raise RuntimeError("dense PLY format drifted")
    count_rows = [line for line in lines if line.startswith("element vertex ")]
    if len(count_rows) != 1:
        raise RuntimeError("dense PLY vertex declaration drifted")
    count = int(count_rows[0].split()[-1])
    properties = [line for line in lines if line.startswith("property ")]
    expected = [
        "property float32 x",
        "property float32 y",
        "property float32 z",
        "property uint8 red",
        "property uint8 green",
        "property uint8 blue",
    ]
    if properties != expected:
        raise RuntimeError("dense PLY property contract drifted")
    if path.stat().st_size != offset + count * POINT_DTYPE.itemsize:
        raise RuntimeError("dense PLY byte count is inconsistent with its header")
    return np.memmap(path, mode="r", dtype=POINT_DTYPE, offset=offset, shape=(count,)), count


def padded_bbox(bbox: Sequence[float], ratio: float, minimum: float) -> list[float]:
    min_x, min_y, max_x, max_y = map(float, bbox)
    margin = max(max(max_x - min_x, max_y - min_y) * ratio, minimum)
    return [min_x - margin, min_y - margin, max_x + margin, max_y + margin]


def principal_frame(reference: Any) -> tuple[np.ndarray, np.ndarray, np.ndarray, float]:
    polygons = list(reference.footprint.geoms) if reference.footprint.geom_type == "MultiPolygon" else [reference.footprint]
    coordinates = np.concatenate([np.asarray(polygon.exterior.coords[:-1], dtype=np.float64) for polygon in polygons])
    center = np.asarray([reference.footprint.centroid.x, reference.footprint.centroid.y], dtype=np.float64)
    centered = coordinates - center
    if len(centered) < 2 or np.allclose(centered, 0.0):
        principal = np.asarray([1.0, 0.0], dtype=np.float64)
    else:
        eigenvalues, eigenvectors = np.linalg.eigh(np.cov(centered.T))
        principal = eigenvectors[:, int(np.argmax(eigenvalues))]
        if principal[0] < 0 or (abs(principal[0]) < 1e-12 and principal[1] < 0):
            principal = -principal
        principal /= max(float(np.linalg.norm(principal)), 1e-12)
    cross = np.asarray([-principal[1], principal[0]], dtype=np.float64)
    cross_extent = float(np.ptp(centered @ cross)) if len(centered) else 0.0
    return center, principal, cross, cross_extent


def dense_ranges(
    points: np.memmap,
    roster: Sequence[Mapping[str, Any]],
    shift: np.ndarray,
    margin_ratio: float,
    minimum_margin: float,
    percentiles: Sequence[float],
    vertical_padding: float,
    minimum_points: int,
) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    finite = np.isfinite(points["x"]) & np.isfinite(points["y"]) & np.isfinite(points["z"])
    finite_indices = np.flatnonzero(finite)
    order_local = np.argsort(points["x"][finite_indices], kind="quicksort")
    order = finite_indices[order_local]
    sorted_x = np.asarray(points["x"][order], dtype=np.float64)
    global_z = np.asarray(points["z"][finite_indices], dtype=np.float64) + shift[2]
    fallback_center = float(np.median(global_z))
    result: dict[str, dict[str, Any]] = {}
    for row in roster:
        building_id = str(row["building_id"])
        viewport = padded_bbox(row["bbox_xy"], margin_ratio, minimum_margin)
        local_min_x, local_max_x = viewport[0] - shift[0], viewport[2] - shift[0]
        lo = int(np.searchsorted(sorted_x, local_min_x, side="left"))
        hi = int(np.searchsorted(sorted_x, local_max_x, side="right"))
        candidate_indices = order[lo:hi]
        local_min_y, local_max_y = viewport[1] - shift[1], viewport[3] - shift[1]
        candidate_y = np.asarray(points["y"][candidate_indices], dtype=np.float64)
        inside = (candidate_y >= local_min_y) & (candidate_y <= local_max_y)
        selected = candidate_indices[inside]
        z = np.asarray(points["z"][selected], dtype=np.float64) + shift[2]
        z = z[np.isfinite(z)]
        if len(z) >= minimum_points:
            low, high = np.percentile(z, percentiles)
            status = "CURRENT_MVS_DENSE_RANGE"
        else:
            low, high = fallback_center - 15.0, fallback_center + 15.0
            status = "FALLBACK_GLOBAL_MVS_MEDIAN"
        if high - low < 4.0:
            center_z = 0.5 * (low + high)
            low, high = center_z - 2.0, center_z + 2.0
        result[building_id] = {
            "viewport_bbox_xy": viewport,
            "dense_point_count_in_viewport": int(len(z)),
            "z_range_status": status,
            "z_range_ellipsoidal_m": [float(low - vertical_padding), float(high + vertical_padding)],
        }
    return result, {
        "finite_dense_point_count": int(len(finite_indices)),
        "global_dense_z_median_ellipsoidal_m": fallback_center,
    }


def prism_points(bbox: Sequence[float], z_range: Sequence[float]) -> np.ndarray:
    min_x, min_y, max_x, max_y = map(float, bbox)
    low, high = map(float, z_range)
    points = [[x, y, z] for z in (low, high) for x, y in ((min_x, min_y), (max_x, min_y), (max_x, max_y), (min_x, max_y))]
    points.append([(min_x + max_x) / 2.0, (min_y + max_y) / 2.0, (low + high) / 2.0])
    return np.asarray(points, dtype=np.float64)


def camera_candidates(
    selection_points: np.ndarray,
    center: np.ndarray,
    principal: np.ndarray,
    cross: np.ndarray,
    cameras: Mapping[str, Any],
    model: tuple[int, int, np.ndarray],
    scene_reference: Mapping[str, Any],
    visible: set[str],
    minimum_coverage: float,
    minimum_area: float,
) -> list[dict[str, Any]]:
    width, height, params = model
    candidates = []
    for camera in cameras.values():
        if camera.name not in visible:
            continue
        uv, front = projection.project(
            selection_points, camera, width, height, params, scene_reference, input_datum="ellipsoidal"
        )
        finite_front = front & np.isfinite(uv).all(axis=1)
        inside = finite_front & (uv[:, 0] >= 0) & (uv[:, 0] < width) & (uv[:, 1] >= 0) & (uv[:, 1] < height)
        coverage = float(np.mean(inside))
        if coverage < minimum_coverage:
            continue
        valid = uv[inside]
        area = float(np.ptp(valid[:, 0]) * np.ptp(valid[:, 1])) if len(valid) else 0.0
        if area < minimum_area:
            continue
        vector = np.asarray(camera.center, dtype=np.float64) - center
        vector /= max(float(np.linalg.norm(vector)), 1e-12)
        nadir = math.degrees(math.acos(float(np.clip(vector[2], -1.0, 1.0))))
        horizontal = vector[:2]
        horizontal /= max(float(np.linalg.norm(horizontal)), 1e-12)
        candidates.append(
            {
                "camera": camera,
                "coverage": coverage,
                "area_px2": area,
                "nadir_deg": nadir,
                "principal_dot": float(horizontal @ principal),
                "cross_dot": float(horizontal @ cross),
                "full_selection_prism": bool(np.all(inside)),
                "selection_uv": uv[finite_front],
            }
        )
    return candidates


def select_cameras(candidates: Sequence[dict[str, Any]], target_nadir: float, moderate: Sequence[float]) -> dict[str, dict[str, Any]]:
    remaining = list(candidates)
    selected: dict[str, dict[str, Any]] = {}
    if not remaining:
        return selected
    low, high = map(float, moderate)
    top = min(remaining, key=lambda row: (not row["full_selection_prism"], row["nadir_deg"], -row["area_px2"], row["camera"].name))
    selected["TOP"] = top
    remaining = [row for row in remaining if row is not top]
    if remaining:
        full = [row for row in remaining if row["full_selection_prism"]]
        moderate_full = [row for row in full if low <= row["nadir_deg"] <= high]
        section = max(
            moderate_full or full or remaining,
            key=lambda row: (row["full_selection_prism"], abs(row["cross_dot"]), -abs(row["nadir_deg"] - target_nadir), row["area_px2"], row["camera"].name),
        )
        selected["PRINCIPAL_SECTION"] = section
        remaining = [row for row in remaining if row is not section]
    if remaining:
        positive = [row for row in remaining if row["principal_dot"] >= 0]
        positive_full = [row for row in positive if row["full_selection_prism"]]
        positive_moderate = [row for row in positive_full if low <= row["nadir_deg"] <= high]
        any_full = [row for row in remaining if row["full_selection_prism"]]
        first = max(
            positive_moderate or positive_full or any_full or positive or remaining,
            key=lambda row: (row["full_selection_prism"], -abs(row["nadir_deg"] - target_nadir), row["area_px2"], row["camera"].name),
        )
        selected["OBLIQUE_1"] = first
        remaining = [row for row in remaining if row is not first]
    if remaining:
        negative = [row for row in remaining if row["principal_dot"] < 0]
        negative_full = [row for row in negative if row["full_selection_prism"]]
        negative_moderate = [row for row in negative_full if low <= row["nadir_deg"] <= high]
        any_full = [row for row in remaining if row["full_selection_prism"]]
        second = max(
            negative_moderate or negative_full or any_full or negative or remaining,
            key=lambda row: (row["full_selection_prism"], -abs(row["nadir_deg"] - target_nadir), row["area_px2"], row["camera"].name),
        )
        selected["OBLIQUE_2"] = second
    return selected


def crop_xyxy(uv: np.ndarray, width: int, height: int, scale: float, constant: float) -> list[int] | None:
    if not len(uv):
        return None
    x0, y0 = np.min(uv, axis=0)
    x1, y1 = np.max(uv, axis=0)
    margin = max(x1 - x0, y1 - y0) * scale + constant
    crop = [
        max(0, int(math.floor(x0 - margin))),
        max(0, int(math.floor(y0 - margin))),
        min(width, int(math.ceil(x1 + margin))),
        min(height, int(math.ceil(y1 + margin))),
    ]
    return crop if crop[2] > crop[0] and crop[3] > crop[1] else None


def overlay_diagnostic(
    reference: Any,
    camera: Any,
    crop: Sequence[int] | None,
    model: tuple[int, int, np.ndarray],
    scene_reference: Mapping[str, Any],
) -> dict[str, Any]:
    width, height, params = model
    visible_vertices = 0
    total_vertices = 0
    full_ring_count = 0
    crop_vertices = 0
    for ring in reference.roof_rings_xyz:
        uv, front = projection.project(np.asarray(ring, dtype=np.float64), camera, width, height, params, scene_reference)
        inside = front & np.isfinite(uv).all(axis=1)
        inside &= (uv[:, 0] >= 0) & (uv[:, 0] < width) & (uv[:, 1] >= 0) & (uv[:, 1] < height)
        visible_vertices += int(inside.sum())
        total_vertices += len(inside)
        full_ring_count += int(np.all(inside))
        if crop is not None:
            crop_inside = inside & (uv[:, 0] >= crop[0]) & (uv[:, 0] < crop[2]) & (uv[:, 1] >= crop[1]) & (uv[:, 1] < crop[3])
            crop_vertices += int(crop_inside.sum())
    if full_ring_count:
        status = "FULL_ROOF_RING_PROJECTABLE"
    elif visible_vertices:
        status = "PARTIAL_ROOF_BOUNDARY_PROJECTABLE"
    else:
        status = "ROOF_BOUNDARY_NOT_PROJECTABLE"
    return {
        "status": status,
        "roof_ring_count": len(reference.roof_rings_xyz),
        "full_roof_ring_count": full_ring_count,
        "visible_roof_vertex_count": visible_vertices,
        "total_roof_vertex_count": total_vertices,
        "roof_vertex_count_inside_frozen_crop": crop_vertices,
        "used_for_camera_or_crop_selection": False,
    }


def view_geometry(config: Mapping[str, Any], view: str, center: np.ndarray, principal: np.ndarray, cross: np.ndarray, cross_extent: float) -> dict[str, Any]:
    spec = dict(config["views"][view])
    if view == "PRINCIPAL_SECTION":
        spec.update(
            {
                "center_xy": center.tolist(),
                "axis_xy": principal.tolist(),
                "normal_xy": cross.tolist(),
                "half_band_m": max(cross_extent * float(spec["band_ratio"]), float(spec["minimum_half_band_m"])),
                "role": "DISPLAY_ONLY_EVALUATION_FRAME",
            }
        )
    return spec


def build(config: Mapping[str, Any], repo_root: Path, artifact_root: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    inputs = config["inputs"]
    dense = config["dense_lineage"]
    dense_root = artifact_root / dense["recovery_relative_root"]
    source_bindings = {
        "utarget_metrics": verify_hash(artifact_root / inputs["utarget_metrics_relative_path"], inputs["utarget_metrics_sha256"], "U_target metrics"),
        "cameras": verify_hash(artifact_root / inputs["cameras_relative_path"], inputs["cameras_sha256"], "COLMAP cameras"),
        "images": verify_hash(artifact_root / inputs["images_relative_path"], inputs["images_sha256"], "COLMAP images"),
        "scene_reference": verify_hash(artifact_root / inputs["scene_reference_relative_path"], inputs["scene_reference_sha256"], "scene reference"),
        "exact_937_crosswalk": verify_hash(repo_root / inputs["exact_937_crosswalk_git_path"], inputs["exact_937_crosswalk_sha256"], "exact-937 crosswalk"),
        "dense_recovery_receipt": verify_hash(dense_root / dense["receipt_relative_path"], dense["receipt_sha256"], "dense recovery receipt"),
    }
    for index, relative in enumerate(inputs["lod2_relative_paths"]):
        source_bindings[f"lod2_{index + 1}"] = verify_hash(artifact_root / relative, inputs["lod2_sha256"][index], f"LoD2 {index + 1}")
    dense_ply = dense_root / dense["ply_relative_path"]
    dense_mvs = dense_root / dense["mvs_relative_path"]
    verify_size(dense_ply, int(dense["ply_bytes"]), "recovered dense PLY")
    verify_size(dense_mvs, int(dense["mvs_bytes"]), "recovered dense MVS")
    source_bindings["dense_ply"] = {"path": str(dense_ply), "bytes": dense["ply_bytes"], "sha256": dense["ply_sha256"], "verification": "bound_recovery_receipt_plus_size"}
    source_bindings["dense_mvs"] = {"path": str(dense_mvs), "bytes": dense["mvs_bytes"], "sha256": dense["mvs_sha256"], "verification": "bound_recovery_receipt_plus_size"}

    roster = load_roster(artifact_root / inputs["utarget_metrics_relative_path"], int(config["population"]["building_count"]))
    building_ids = [row["building_id"] for row in roster]
    references = load_references([artifact_root / relative for relative in inputs["lod2_relative_paths"]], building_ids)
    crosswalk = json.loads((repo_root / inputs["exact_937_crosswalk_git_path"]).read_text(encoding="utf-8"))
    if crosswalk.get("member_count") != 937 or len(crosswalk.get("rows", [])) != 937:
        raise RuntimeError("exact-937 crosswalk membership drifted")
    crosswalk_by_name = {str(row["basename"]): row for row in crosswalk["rows"]}
    visible = set(crosswalk_by_name)
    image_directory = artifact_root / inputs["image_directory_relative_path"]
    missing_images = sorted(name for name in visible if not (image_directory / name).is_file())
    if missing_images:
        raise RuntimeError(f"exact-937 retained images missing: {missing_images[:5]}")
    scene_reference = json.loads((artifact_root / inputs["scene_reference_relative_path"]).read_text(encoding="utf-8"))
    model = projection.parse_cam_model(artifact_root / inputs["cameras_relative_path"])
    camera_list = projection.parse_cameras(artifact_root / inputs["images_relative_path"], scene_reference)
    cameras = {camera.name: camera for camera in camera_list}
    if set(cameras) != visible:
        raise RuntimeError("COLMAP cameras and exact-937 membership differ")

    points, point_count = load_xyzrgb_ply(dense_ply)
    if point_count != int(dense["ply_point_count"]):
        raise RuntimeError("recovered dense PLY point count drifted")
    crop_spec = config["crop"]
    shift = np.asarray(config["frame"]["dense_local_shift_xyz"], dtype=np.float64)
    ranges, dense_summary = dense_ranges(
        points,
        roster,
        shift,
        float(crop_spec["world_viewport_margin_ratio"]),
        float(crop_spec["world_viewport_minimum_margin_m"]),
        crop_spec["dense_z_percentiles"],
        float(crop_spec["dense_z_vertical_padding_m"]),
        int(crop_spec["minimum_dense_points"]),
    )

    selection_spec = config["camera_selection"]
    width, height, _params = model
    view_order = list(config["views"]["order"])
    records = []
    view_rows = []
    for population_index, roster_row in enumerate(roster, 1):
        building_id = roster_row["building_id"]
        reference = references[building_id]
        center_xy, principal, cross, cross_extent = principal_frame(reference)
        dense_range = ranges[building_id]
        selection = prism_points(roster_row["bbox_xy"], dense_range["z_range_ellipsoidal_m"])
        center = selection[-1]
        candidates = camera_candidates(
            selection,
            center,
            principal,
            cross,
            cameras,
            model,
            scene_reference,
            visible,
            float(selection_spec["minimum_projection_coverage"]),
            float(selection_spec["minimum_projected_area_px2"]),
        )
        selected = select_cameras(candidates, float(selection_spec["target_oblique_nadir_deg"]), selection_spec["moderate_oblique_nadir_range_deg"])
        views = []
        for view in view_order:
            candidate = selected.get(view)
            geometry = view_geometry(config, view, center_xy, principal, cross, cross_extent)
            if candidate is None:
                camera_record = {"status": "NO_VALID_CAMERA", "camera_name": None, "crop_xyxy": None}
                overlay = {"status": "NOT_EVALUATED_NO_CAMERA", "used_for_camera_or_crop_selection": False}
            else:
                camera = candidate["camera"]
                crop = crop_xyxy(candidate["selection_uv"], width, height, float(crop_spec["image_margin_scale"]), float(crop_spec["image_margin_constant_px"]))
                member = crosswalk_by_name[camera.name]
                status = "SELECTED" if crop is not None else "EMPTY_CROP"
                camera_record = {
                    "status": status,
                    "camera_name": camera.name,
                    "colmap_image_id": member["colmap_image_id"],
                    "source_camera_uid": member["source_camera_uid"],
                    "image_size_wh": [width, height],
                    "image_exists": True,
                    "crop_xyxy": crop,
                    "selection_coverage_fraction": candidate["coverage"],
                    "selection_projected_area_px2": candidate["area_px2"],
                    "selection_nadir_deg": candidate["nadir_deg"],
                    "selection_principal_dot": candidate["principal_dot"],
                    "selection_cross_dot": candidate["cross_dot"],
                    "selection_full_prism": candidate["full_selection_prism"],
                    "selection_geometry": "CURRENT_MVS_DENSE_Z_PRISM",
                }
                overlay = overlay_diagnostic(reference, camera, crop, model, scene_reference)
            view_row = {
                "schema": "jointbuildgs.p2.qualitative_199_camera_view_crop_row.v1",
                "building_id": building_id,
                "population_index": population_index,
                "view_id": view,
                "camera": camera_record,
                "view_geometry": geometry,
                "evaluation_roof_boundary": overlay,
                "scientific_verdict": None,
            }
            views.append(view_row)
            view_rows.append(view_row)
        records.append(
            {
                "schema": "jointbuildgs.p2.qualitative_199_building_manifest.v1",
                "building_id": building_id,
                "population_index": population_index,
                "building_bbox_xy": roster_row["bbox_xy"],
                **dense_range,
                "principal_frame": {"center_xy": center_xy.tolist(), "axis_xy": principal.tolist(), "cross_axis_xy": cross.tolist()},
                "views": views,
                "all_four_cameras_selected": all(row["camera"]["status"] == "SELECTED" for row in views),
                "row_contract_ids": [row["row_id"] for row in config["row_order"]],
                "scientific_verdict": None,
            }
        )
    return records, view_rows, {"source_bindings": source_bindings, "dense_summary": dense_summary}


def file_record(path: Path, root: Path) -> dict[str, Any]:
    size, digest = sha256_file(path)
    return {"path": path.relative_to(root).as_posix(), "bytes": size, "sha256": digest}


def run(config_path: Path, repo_root: Path, artifact_root: Path, output_root: Path, source_commit: str, image_id: str) -> dict[str, Any]:
    config = json.loads(config_path.read_text(encoding="utf-8"))
    if config.get("status") != "USER_APPROVED_STAGE2_COMMON_MANIFEST":
        raise RuntimeError("stage-2 common manifest is not approved")
    if [row["row"] for row in config["row_order"]] != list(range(1, 7)):
        raise RuntimeError("six-row order drifted")
    if output_root.exists() or output_root.with_name(output_root.name + ".partial").exists():
        raise RuntimeError(f"add-once output exists: {output_root}")
    partial = output_root.with_name(output_root.name + ".partial")
    partial.mkdir(parents=True)
    records, view_rows, support = build(config, repo_root, artifact_root)
    building_path = partial / "manifest/building_camera_view_crop_manifest_v1.jsonl"
    view_path = partial / "manifest/camera_view_rows_v1.jsonl"
    write_new(building_path, b"".join(canonical_json_bytes(row) for row in records))
    write_new(view_path, b"".join(canonical_json_bytes(row) for row in view_rows))
    source_path = partial / "control/source_bindings_v1.json"
    write_new(source_path, canonical_json_bytes({"schema": "jointbuildgs.p2.qualitative_199_source_bindings.v1", **support["source_bindings"], "scientific_verdict": None}))
    row_contract_path = partial / "control/six_row_contract_v1.json"
    write_new(row_contract_path, canonical_json_bytes({"schema": config["schema"], "decision_id": config["decision_id"], "row_order": config["row_order"], "dense_lineage": config["dense_lineage"], "scientific_verdict": None}))
    camera_status = Counter(row["camera"]["status"] for row in view_rows)
    overlay_status = Counter(row["evaluation_roof_boundary"]["status"] for row in view_rows)
    dense_status = Counter(row["z_range_status"] for row in records)
    summary = {
        "schema": "jointbuildgs.p2.qualitative_199_common_manifest.summary.v1",
        "task_id": config["task_id"],
        "building_count": len(records),
        "view_row_count": len(view_rows),
        "expected_view_row_count": int(config["population"]["building_count"]) * 4,
        "all_population_members_retained": len(records) == int(config["population"]["building_count"]),
        "buildings_with_all_four_cameras": sum(bool(row["all_four_cameras_selected"]) for row in records),
        "camera_status_counts": dict(sorted(camera_status.items())),
        "roof_boundary_status_counts": dict(sorted(overlay_status.items())),
        "dense_range_status_counts": dict(sorted(dense_status.items())),
        **support["dense_summary"],
        "next_stage_authorized": False,
        "scientific_verdict": None,
    }
    summary_path = partial / "control/summary_v1.json"
    write_new(summary_path, canonical_json_bytes(summary))
    config_size, config_sha = sha256_file(config_path)
    script_size, script_sha = sha256_file(Path(__file__))
    receipt = {
        "schema": "jointbuildgs.p2.qualitative_199_common_manifest.receipt.v1",
        "task_id": config["task_id"],
        "state": "complete",
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "source_commit": source_commit,
        "runtime_image_id": image_id,
        "config": {"path": str(config_path), "bytes": config_size, "sha256": config_sha},
        "script": {"path": str(Path(__file__)), "bytes": script_size, "sha256": script_sha},
        "summary": summary,
        "scientific_verdict": None,
    }
    receipt_path = partial / "control/run_receipt_v1.json"
    write_new(receipt_path, canonical_json_bytes(receipt))
    material = sorted(path for path in partial.rglob("*") if path.is_file())
    manifest = {
        "schema": "jointbuildgs.p2.qualitative_199_common_manifest.artifact_manifest.v1",
        "task_id": config["task_id"],
        "records": [file_record(path, partial) for path in material],
        "scientific_verdict": None,
    }
    manifest["record_count"] = len(manifest["records"])
    write_new(partial / "control/artifact_manifest_v1.json", canonical_json_bytes(manifest))
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
