#!/usr/bin/env python3
"""Post-process the paired C3 roof extraction into five bounded diagnostics."""
from __future__ import annotations

import argparse
import csv
import io
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

import cv2
import numpy as np
from shapely import contains_xy
from shapely.geometry import Polygon

from scripts.p2.c1_c2_oracle_c3_extract_v1.contract import load_building_references
from scripts.p2.c1_c2_oracle_c3_extract_v1.prepare_c1_c2 import collect_laz, collect_mvs
from scripts.p2.c3_tsdf_roof_diagnostic_v1.contract import (
    canonical_json_bytes,
    file_record,
    load_config,
    require_regular,
    resolve_artifact,
    validate_config,
    write_new,
)
from src.stage2.dataloader import ColmapDataset
from src.visualization.fixed_view_qualitative import load_cityjsonseq, load_las_points


def _visible_names(config: Mapping[str, Any], repo_root: Path) -> list[str]:
    value = json.loads((repo_root / config["source"]["exact_view_manifest_git_path"]).read_text(encoding="utf-8"))
    names = [str(row["basename"]) for row in value["rows"]]
    if len(names) != int(config["source"]["exact_view_count"]):
        raise RuntimeError("exact view count drifted")
    return names


def _plane(surface_xyz: np.ndarray) -> tuple[np.ndarray, float]:
    points = np.asarray(surface_xyz, dtype=np.float64)
    center = points.mean(axis=0)
    _u, _s, vh = np.linalg.svd(points - center, full_matrices=False)
    normal = vh[-1]
    normal /= max(np.linalg.norm(normal), 1e-12)
    if normal[2] < 0:
        normal = -normal
    return normal, float(-normal @ center)


def roofer_plane_diagnostic(v13_root: Path, condition_id: str, stable_id: str) -> dict[str, Any]:
    operation = v13_root / f"operations/{condition_id}_GT_FOOTPRINT_ORACLE/{stable_id}/work"
    prepared = json.loads((operation / "prepared_v1.json").read_text(encoding="utf-8"))
    if not prepared.get("roofer_eligible"):
        return {
            "condition_id": condition_id,
            "stable_id": stable_id,
            "status": "ROOFER_NOT_RUN_INSUFFICIENT_ROOF_EVIDENCE",
            "class6_point_count": int(prepared["classification"]["building_class6_count"]),
            "scientific_verdict": None,
        }
    terminal = json.loads((operation / "roofer_terminal_v1.json").read_text(encoding="utf-8"))
    if terminal.get("status") != "COMPLETED" or len(terminal.get("outputs") or ()) != 1:
        raise RuntimeError(f"incomplete inherited Roofer operation: {condition_id} {stable_id}")
    points = load_las_points(operation / "input.las")
    building = points.xyz[np.asarray(points.classification) == 6]
    surfaces = load_cityjsonseq(v13_root / terminal["outputs"][0]["path"])
    roof_surfaces = [surface for surface in surfaces if surface.semantic == "RoofSurface"]
    planes: list[dict[str, Any]] = []
    membership: list[np.ndarray] = []
    residuals: list[np.ndarray] = []
    for index, surface in enumerate(roof_surfaces):
        polygon = Polygon(surface.xyz[:, :2])
        if not polygon.is_valid:
            polygon = polygon.buffer(0)
        normal, offset = _plane(surface.xyz)
        inside = contains_xy(polygon.buffer(0.05), building[:, 0], building[:, 1])
        distance = np.abs(building @ normal + offset)
        membership.append(inside)
        residuals.append(distance)
        planes.append({
            "plane_index": int(index),
            "area_xy_m2": float(polygon.area),
            "normal_xyz": normal.tolist(),
            "slope_deg": float(np.degrees(np.arccos(np.clip(normal[2], -1, 1)))),
        })
    if roof_surfaces:
        inside_matrix = np.column_stack(membership)
        distance_matrix = np.column_stack(residuals)
        distance_matrix[~inside_matrix] = np.inf
        assigned = np.isfinite(distance_matrix).any(axis=1)
        assignment = np.argmin(distance_matrix, axis=1)
        assigned_residual = distance_matrix[np.arange(len(building)), assignment]
        for index, row in enumerate(planes):
            selected = assigned & (assignment == index)
            values = assigned_residual[selected]
            row.update({
                "support_point_count": int(np.count_nonzero(selected)),
                "support_density_per_m2": float(np.count_nonzero(selected) / max(row["area_xy_m2"], 1e-9)),
                "point_to_plane_residual_m": None if not len(values) else {
                    "median": float(np.median(values)),
                    "p95": float(np.quantile(values, 0.95)),
                    "maximum": float(np.max(values)),
                },
            })
        global_values = assigned_residual[assigned]
    else:
        assigned = np.zeros(len(building), dtype=bool)
        global_values = np.empty((0,), dtype=np.float64)
    return {
        "condition_id": condition_id,
        "stable_id": stable_id,
        "status": "COMPLETED_INHERITED_ROOFER_PLANE_DIAGNOSTIC",
        "class6_point_count": int(len(building)),
        "roof_surface_count": int(len(roof_surfaces)),
        "assigned_point_count": int(np.count_nonzero(assigned)),
        "assigned_point_fraction": float(np.mean(assigned)) if len(assigned) else 0.0,
        "small_surface_count_area_lt_1m2": int(sum(row["area_xy_m2"] < 1.0 for row in planes)),
        "weak_surface_count_support_lt_100": int(sum(row.get("support_point_count", 0) < 100 for row in planes)),
        "global_assigned_residual_m": None if not len(global_values) else {
            "median": float(np.median(global_values)),
            "p95": float(np.quantile(global_values, 0.95)),
            "maximum": float(np.max(global_values)),
        },
        "planes": planes,
        "oracle_diagnostic": True,
        "official_honest_stage3": False,
        "scientific_verdict": None,
    }


def _quantiles(values: np.ndarray) -> dict[str, float] | None:
    values = np.asarray(values, dtype=np.float64)
    if not len(values):
        return None
    return {
        "minimum": float(np.min(values)),
        "p10": float(np.quantile(values, 0.1)),
        "median": float(np.median(values)),
        "p90": float(np.quantile(values, 0.9)),
        "maximum": float(np.max(values)),
    }


def current_source_presence(
    artifact_root: Path,
    v13_root: Path,
    references: Mapping[str, Any],
    config: Mapping[str, Any],
) -> dict[str, Any]:
    stable_id = "DEBY_LOD2_4907177"
    reference = references[stable_id]
    buffer_m = float(config["diagnostics"]["source_crop_buffer_m"])
    c1 = collect_laz(
        resolve_artifact(artifact_root, config["source"]["c1_relative_path"], "C1 source"),
        {stable_id: reference}, buffer_m,
    )[stable_id]
    c2 = collect_mvs(
        resolve_artifact(artifact_root, config["source"]["c2_relative_path"], "C2 source"),
        {stable_id: reference}, buffer_m, config["frame"]["world_shift_xyz"],
    )[stable_id]
    rows = {}
    for method, xyz in (("C1_CURRENT_UAS_LIDAR", c1), ("C2_EXACT_COMMON_MVS", c2)):
        prepared = json.loads((v13_root / f"operations/{'C1_LIDAR_GT_FOOTPRINT_ORACLE' if method.startswith('C1') else 'C2_MVS_GT_FOOTPRINT_ORACLE'}/{stable_id}/work/prepared_v1.json").read_text(encoding="utf-8"))
        ground = float(prepared["classification"]["local_ground_z"])
        by_buffer = []
        for radius in map(float, config["diagnostics"]["presence_buffers_m"]):
            polygon = reference.footprint if radius == 0 else reference.footprint.buffer(radius)
            inside = contains_xy(polygon, xyz[:, 0], xyz[:, 1])
            values = xyz[inside, 2]
            by_buffer.append({
                "buffer_m": radius,
                "point_count": int(len(values)),
                "z_m": _quantiles(values),
                "above_current_ground_plus_2p5m_count": int(np.count_nonzero(values >= ground + 2.5)),
                "above_current_ground_plus_2p5m_fraction": float(np.mean(values >= ground + 2.5)) if len(values) else 0.0,
            })
        rows[method] = {
            "source_crop_point_count": int(len(xyz)),
            "source_crop_buffer_m": buffer_m,
            "current_local_ground_z_m": ground,
            "buffer_profiles": by_buffer,
        }
    geoid = float(config["frame"]["lod2_orthometric_to_camera_ellipsoidal_m"])
    roof = np.vstack(reference.roof_rings_xyz)
    ground = np.vstack(reference.ground_rings_xyz)
    footprint_buffer = reference.footprint.buffer(0.05)
    roof_inside = contains_xy(footprint_buffer, roof[:, 0], roof[:, 1])
    return {
        "schema": "jointbuildgs.c3_4907177_current_source_presence.v1",
        "stable_id": stable_id,
        "reference_internal_xy_consistency": {
            "roof_vertex_count": int(len(roof)),
            "roof_vertices_inside_groundsurface_xy_fraction": float(np.mean(roof_inside)),
            "groundsurface_area_m2": float(reference.footprint.area),
            "roof_orthometric_z_m": _quantiles(roof[:, 2]),
            "roof_camera_ellipsoidal_z_m": _quantiles(roof[:, 2] + geoid),
            "ground_orthometric_z_m": _quantiles(ground[:, 2]),
        },
        "current_sources": rows,
        "interpretation_boundary": "SOURCE_PRESENCE_DIAGNOSTIC_NOT_DEMOLITION_VERDICT",
        "scientific_verdict": None,
    }


def _project_ring(
    ring: np.ndarray,
    frame: Any,
    shift: np.ndarray,
    vertical_add_m: float,
) -> tuple[np.ndarray, np.ndarray]:
    world = np.asarray(ring, dtype=np.float64).copy()
    world[:, 2] += vertical_add_m
    local = world - shift
    camera = local @ frame.R.T + frame.t
    front = camera[:, 2] > 0.1
    uvw = camera @ frame.K.T
    uv = np.full((len(world), 2), np.nan, dtype=np.float64)
    uv[front] = uvw[front, :2] / uvw[front, 2:3]
    inside = front & np.isfinite(uv).all(axis=1)
    inside &= (uv[:, 0] >= 0) & (uv[:, 0] < frame.width) & (uv[:, 1] >= 0) & (uv[:, 1] < frame.height)
    return uv, inside


def _roof_projection_record(
    frame: Any,
    rings: Sequence[np.ndarray],
    semantic_path: Path,
    shift: np.ndarray,
    vertical_add_m: float,
    minimum_area: float,
) -> dict[str, Any] | None:
    projected = [_project_ring(ring, frame, shift, vertical_add_m) for ring in rings]
    if not all(np.all(inside) for _uv, inside in projected):
        return None
    mask = np.zeros((frame.height, frame.width), dtype=np.uint8)
    for uv, _inside in projected:
        cv2.fillPoly(mask, [np.rint(uv).astype(np.int32)], 1)
    area = int(np.count_nonzero(mask))
    if area < minimum_area:
        return None
    semantic = cv2.imread(str(semantic_path), cv2.IMREAD_UNCHANGED)
    if semantic is None:
        raise RuntimeError(f"semantic mask unreadable: {semantic_path}")
    if semantic.ndim == 3:
        semantic = semantic[..., 0]
    if semantic.shape != mask.shape:
        semantic = cv2.resize(semantic, (frame.width, frame.height), interpolation=cv2.INTER_NEAREST)
    roof_fraction = float(np.mean(semantic[mask.astype(bool)] == 1))
    return {
        "image_name": str(frame.name),
        "projected_roof_area_px": area,
        "image_semantic_roof_fraction_inside_projected_2022_roof": roof_fraction,
        "projected_rings": [uv.tolist() for uv, _inside in projected],
    }


def roofline_image_diagnostic(
    output_root: Path,
    dataset: ColmapDataset,
    semantic_root: Path,
    reference: Any,
    current_ground_z: float,
    config: Mapping[str, Any],
) -> dict[str, Any]:
    shift = np.asarray(config["frame"]["world_shift_xyz"], dtype=np.float64)
    geoid = float(config["frame"]["lod2_orthometric_to_camera_ellipsoidal_m"])
    minimum_area = float(config["diagnostics"]["roofline_min_projected_area_px"])
    by_datum: dict[str, list[dict[str, Any]]] = {"ORTHOMETRIC_PLUS_45P7": [], "NO_VERTICAL_SHIFT": []}
    for frame in dataset.frames:
        semantic_path = semantic_root / f"{Path(frame.name).stem}.png"
        for label, vertical in (("ORTHOMETRIC_PLUS_45P7", geoid), ("NO_VERTICAL_SHIFT", 0.0)):
            row = _roof_projection_record(frame, reference.roof_rings_xyz, semantic_path, shift, vertical, minimum_area)
            if row is not None:
                by_datum[label].append(row)
    summaries = {}
    for label, rows in by_datum.items():
        fractions = np.asarray([row["image_semantic_roof_fraction_inside_projected_2022_roof"] for row in rows])
        summaries[label] = {
            "fully_visible_camera_count": int(len(rows)),
            "semantic_roof_fraction": _quantiles(fractions),
            "maximum_semantic_roof_fraction": float(np.max(fractions)) if len(fractions) else None,
        }
    candidates = sorted(
        by_datum["ORTHOMETRIC_PLUS_45P7"],
        key=lambda row: (-row["projected_roof_area_px"], row["image_name"]),
    )
    count = int(config["diagnostics"]["roofline_montage_view_count"])
    selected = candidates[:count]
    panels = []
    frame_by_name = {frame.name: frame for frame in dataset.frames}
    image_root = dataset.root / "images"
    for index, row in enumerate(selected, 1):
        frame = frame_by_name[row["image_name"]]
        image = cv2.imread(str(image_root / frame.name), cv2.IMREAD_COLOR)
        if image is None:
            raise RuntimeError(f"undistorted RGB unreadable: {frame.name}")
        if image.shape[:2] != (frame.height, frame.width):
            image = cv2.resize(image, (frame.width, frame.height), interpolation=cv2.INTER_AREA)
        semantic = cv2.imread(str(semantic_root / f"{Path(frame.name).stem}.png"), cv2.IMREAD_UNCHANGED)
        if semantic.ndim == 3:
            semantic = semantic[..., 0]
        if semantic.shape != image.shape[:2]:
            semantic = cv2.resize(semantic, (frame.width, frame.height), interpolation=cv2.INTER_NEAREST)
        overlay = image.copy()
        roof_pixels = semantic == 1
        overlay[roof_pixels] = np.rint(0.55 * overlay[roof_pixels] + 0.45 * np.asarray([255, 210, 30])).astype(np.uint8)
        rings = [np.asarray(value, dtype=np.float64) for value in row["projected_rings"]]
        all_uv = np.vstack(rings)
        left = max(0, int(np.floor(np.min(all_uv[:, 0])) - 160))
        right = min(frame.width, int(np.ceil(np.max(all_uv[:, 0])) + 160))
        top = max(0, int(np.floor(np.min(all_uv[:, 1])) - 120))
        bottom = min(frame.height, int(np.ceil(np.max(all_uv[:, 1])) + 120))
        for uv in rings:
            ring = np.rint(uv).astype(np.int32).reshape((-1, 1, 2))
            cv2.polylines(overlay, [ring], True, (20, 20, 20), 8, cv2.LINE_AA)
            cv2.polylines(overlay, [ring], True, (30, 205, 255), 4, cv2.LINE_AA)
        crop = overlay[top:bottom, left:right].copy()
        cv2.rectangle(crop, (0, 0), (crop.shape[1], 64), (20, 20, 20), -1)
        title = f"{frame.name} | projected-old-roof semantic overlap={row['image_semantic_roof_fraction_inside_projected_2022_roof']:.3f}"
        cv2.putText(crop, title, (14, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.68, (245, 245, 245), 2, cv2.LINE_AA)
        path = output_root / f"qualitative/4907177_presence/panels/view_{index:02d}.png"
        ok, encoded = cv2.imencode(".png", crop)
        if not ok:
            raise RuntimeError("presence panel encoding failed")
        write_new(path, encoded.tobytes())
        panels.append(file_record(path, output_root))
    if panels:
        images = [cv2.imread(str(output_root / row["path"]), cv2.IMREAD_COLOR) for row in panels]
        cell_w, cell_h = 900, 675
        canvas = np.full((2 * cell_h, 3 * cell_w, 3), 245, dtype=np.uint8)
        for index, image in enumerate(images):
            scale = min(cell_w / image.shape[1], cell_h / image.shape[0])
            resized = cv2.resize(image, (int(image.shape[1] * scale), int(image.shape[0] * scale)))
            y = (index // 3) * cell_h + (cell_h - resized.shape[0]) // 2
            x = (index % 3) * cell_w + (cell_w - resized.shape[1]) // 2
            canvas[y:y + resized.shape[0], x:x + resized.shape[1]] = resized
        montage_path = output_root / "qualitative/4907177_presence/2024_rgb_2022_roofline_semantic_montage_v1.png"
        ok, encoded = cv2.imencode(".png", canvas)
        if not ok:
            raise RuntimeError("presence montage encoding failed")
        write_new(montage_path, encoded.tobytes())
        montage = file_record(montage_path, output_root)
    else:
        montage = None
    return {
        "schema": "jointbuildgs.c3_4907177_roofline_image_presence.v1",
        "status": "COMPLETE" if montage is not None else "NO_FULLY_VISIBLE_REFERENCE_CAMERA",
        "current_ground_z_m": current_ground_z,
        "datum_comparison": summaries,
        "panel_count": len(panels),
        "panels": panels,
        "montage": montage,
        "yellow_role": "2022 LoD2 RoofSurface projection",
        "cyan_role": "2024 image-only semantic roof pixels",
        "interpretation_boundary": "VISIBILITY_AND_ALIGNMENT_DIAGNOSTIC_NOT_DEMOLITION_VERDICT",
        "scientific_verdict": None,
    }


def _comparison_rows(output_root: Path, conditions: Sequence[str], buildings: Sequence[str]) -> list[dict[str, Any]]:
    rows = []
    for condition_id in conditions:
        for stable_id in buildings:
            result = json.loads((output_root / f"conditions/{condition_id}/buildings/{stable_id}/result_v1.json").read_text(encoding="utf-8"))
            row = {
                "condition_id": condition_id,
                "stable_id": stable_id,
                "status": result["status"],
                "consensus_roof_point_count": result.get("consensus_roof_point_count", 0),
                "footprint_coverage_fraction": (result.get("footprint_roof_coverage") or {}).get("coverage_fraction"),
            }
            for method in ("poisson", "tsdf"):
                quality = (result.get(method) or {}).get("quality") or {}
                distance = quality.get("nearest_evidence_distance_m") or {}
                row.update({
                    f"{method}_triangle_count": quality.get("mesh_triangle_count"),
                    f"{method}_component_count": quality.get("connected_component_count"),
                    f"{method}_largest_component_fraction": quality.get("largest_component_triangle_fraction"),
                    f"{method}_boundary_loop_count": quality.get("boundary_loop_count"),
                    f"{method}_hole_like_loop_count": quality.get("hole_like_loop_count"),
                    f"{method}_evidence_distance_p95_m": distance.get("p95"),
                    f"{method}_far_gt_0p3m_fraction": (distance.get("far_fraction_by_threshold") or {}).get("0.300"),
                })
            rows.append(row)
    return rows


def run(output_root: Path, artifact_root: Path, repo_root: Path) -> dict[str, Any]:
    config = load_config()
    validate_config(config)
    pair = require_regular(output_root / "control/extraction_pair_complete_v1.json", "paired extraction receipt")
    if json.loads(pair.read_text(encoding="utf-8")).get("status") != "COMPLETE_TWO_CONDITIONS":
        raise RuntimeError("paired extraction is incomplete")
    v13_root = resolve_artifact(artifact_root, config["source"]["v13_relative_root"], "v13")
    lod2 = resolve_artifact(artifact_root, config["source"]["lod2_relative_path"], "LoD2")
    references = load_building_references(lod2, config["scope"]["building_ids"])
    plane_rows = []
    for condition_id in config["scope"]["condition_ids"]:
        for stable_id in config["scope"]["building_ids"]:
            plane_rows.append(roofer_plane_diagnostic(v13_root, condition_id, stable_id))
    plane_body = {
        "schema": "jointbuildgs.c3_inherited_roofer_plane_diagnostic.v1",
        "status": "COMPLETE_FOUR_OUTPUTS_TWO_PREFAILURES",
        "rows": plane_rows,
        "roofer_invocations": 0,
        "metric_recomputations": 0,
        "scientific_verdict": None,
    }
    write_new(output_root / "diagnostics/roofer_plane_diagnostic_v1.json", canonical_json_bytes(plane_body))
    presence = current_source_presence(artifact_root, v13_root, references, config)
    write_new(output_root / "diagnostics/4907177_current_source_presence_v1.json", canonical_json_bytes(presence))
    dataset = ColmapDataset(
        resolve_artifact(artifact_root, config["source"]["colmap_relative_root"], "COLMAP"),
        downscale=1.0, load_depth=False, load_normal=False, load_semantic=False,
        visible_views=_visible_names(config, repo_root),
    )
    semantic_root = resolve_artifact(artifact_root, config["source"]["semantic_relative_root"], "semantic masks")
    current_ground = float(
        json.loads((v13_root / "operations/C2_MVS_GT_FOOTPRINT_ORACLE/DEBY_LOD2_4907177/work/prepared_v1.json").read_text(encoding="utf-8"))["classification"]["local_ground_z"]
    )
    image_presence = roofline_image_diagnostic(
        output_root, dataset, semantic_root, references["DEBY_LOD2_4907177"], current_ground, config
    )
    write_new(output_root / "diagnostics/4907177_roofline_image_presence_v1.json", canonical_json_bytes(image_presence))
    comparison = _comparison_rows(output_root, config["scope"]["condition_ids"], config["scope"]["building_ids"])
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=list(comparison[0]))
    writer.writeheader()
    writer.writerows(comparison)
    write_new(output_root / "tables/poisson_tsdf_mesh_quality_v1.csv", buffer.getvalue().encode("utf-8"))
    plane_flat = []
    for row in plane_rows:
        plane_flat.append({
            "condition_id": row["condition_id"], "stable_id": row["stable_id"], "status": row["status"],
            "class6_point_count": row.get("class6_point_count"), "roof_surface_count": row.get("roof_surface_count"),
            "assigned_point_fraction": row.get("assigned_point_fraction"),
            "residual_median_m": (row.get("global_assigned_residual_m") or {}).get("median"),
            "residual_p95_m": (row.get("global_assigned_residual_m") or {}).get("p95"),
            "small_surface_count_area_lt_1m2": row.get("small_surface_count_area_lt_1m2"),
            "weak_surface_count_support_lt_100": row.get("weak_surface_count_support_lt_100"),
        })
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=list(plane_flat[0]))
    writer.writeheader()
    writer.writerows(plane_flat)
    write_new(output_root / "tables/roofer_plane_diagnostic_v1.csv", buffer.getvalue().encode("utf-8"))
    body = {
        "schema": "jointbuildgs.c3_five_question_diagnostic.v1",
        "status": "COMPLETE",
        "question_count": 5,
        "poisson_tsdf_row_count": len(comparison),
        "roofer_plane_row_count": len(plane_rows),
        "presence_source_profile_count": 2,
        "presence_image_panel_count": image_presence["panel_count"],
        "execution_counters": {
            "gs_training_invocations": 0, "roofer_invocations": 0,
            "g2_invocations": 0, "metric_recomputations": 0, "c4_c5_accesses": 0,
        },
        "scientific_verdict": None,
    }
    write_new(output_root / "control/five_question_diagnostic_complete_v1.json", canonical_json_bytes(body))
    return body


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--repo-root", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.output_root, args.artifact_root, args.repo_root), ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
