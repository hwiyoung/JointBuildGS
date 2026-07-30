#!/usr/bin/env python3
"""Compute W3-1 paired Roofer roof quality metrics.

Run from phases/p0-audit/. Host mode rebuilds/uses the P0 tools image and executes the
metric computation inside the container. Metrics are computed for the 67 W2-1c
Roofer-default ALS/DIM both-success buildings.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from lxml import etree
from shapely import contains_xy, make_valid
from shapely.geometry import GeometryCollection, LineString, MultiLineString, MultiPolygon, Point, Polygon
from shapely.ops import unary_union

from p0_paths import P0_EVIDENCE


TASK_ID = "W3-1"
BASE_W2_RUN_ID = "w2_1_roofer_default_20260612_152729"
PAIRED_STATUS = str(P0_EVIDENCE / "W2_1c_paired_status.csv")
ALS_CITYJSON = f"/workspace/runs/{BASE_W2_RUN_ID}/cityjson/als_roofer.city.json"
DIM_CITYJSON = f"/workspace/runs/{BASE_W2_RUN_ID}/cityjson/dim_roofer.city.json"
LOD2_DIR = "/workspace/data/raw/lod2"
IOU_THRESHOLD = 0.50
BOUNDARY_SAMPLE_SPACING_M = 0.50
HEIGHT_SAMPLE_SPACING_M = 0.50
PLANE_F1_DROP_THRESHOLD = 0.10
BOUNDARY_RATIO_THRESHOLD = 1.50


@dataclass
class RoofSurface:
    surface_id: str
    polygon: Polygon | MultiPolygon
    x0: float
    y0: float
    z0: float
    ax: float
    by: float
    vertex_count: int

    def z_at(self, x: np.ndarray, y: np.ndarray) -> np.ndarray:
        return self.z0 + self.ax * (x - self.x0) + self.by * (y - self.y0)


def host_entrypoint() -> None:
    repo = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env.setdefault("P0_UID", str(os.getuid()))
    env.setdefault("P0_GID", str(os.getgid()))
    run_id = env.get("RUN_ID") or datetime.now().strftime("w3_1_roofer_quality_%Y%m%d_%H%M%S")
    git_commit = capture(["git", "rev-parse", "--short", "HEAD"], cwd=repo.parent).strip()
    run_dir = repo / "runs" / run_id
    logs_dir = run_dir / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    compose = ["docker", "compose", "-f", str(repo / "env/docker-compose.p0.yml")]

    write_host_config(run_dir, run_id, git_commit)
    if env.get("SKIP_BUILD") != "1":
        run(compose + ["build", "tools"], cwd=repo, env=env, log_path=logs_dir / "build_tools.log")
    write_host_versions(repo, run_dir, compose, env, git_commit)
    run(
        compose
        + [
            "run",
            "-T",
            "--rm",
            "-e",
            f"RUN_ID={run_id}",
            "-e",
            f"P0_GIT_COMMIT={git_commit}",
            "tools",
            "python",
            "/workspace/scripts/15_roofer_quality_w3.py",
            "--mode",
            "compute",
        ],
        cwd=repo,
        env=env,
        log_path=logs_dir / "compute.log",
    )
    print(f"run_id={run_id}")
    print(f"run_dir=runs/{run_id}")
    print("report=docs/W3_1_roofer_quality.md")


def compute_entrypoint() -> None:
    root = Path("/workspace")
    docs = P0_EVIDENCE
    figs = docs.figs("W3")
    figs.mkdir(parents=True, exist_ok=True)
    run_id = os.environ["RUN_ID"]
    run_dir = root / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    paired_rows = read_csv(Path(PAIRED_STATUS))
    building_ids = [
        row["building_id"]
        for row in paired_rows
        if row["coverage_control_population"] == "yes" and row["paired_category"] == "both_success"
    ]
    if len(building_ids) != 67:
        raise RuntimeError(f"Expected 67 Roofer-default both_success buildings, got {len(building_ids)}")

    reference = parse_lod2_roofs(Path(LOD2_DIR), set(building_ids))
    als_pred = parse_cityjson_roofs(Path(ALS_CITYJSON), set(building_ids))
    dim_pred = parse_cityjson_roofs(Path(DIM_CITYJSON), set(building_ids))

    rows = []
    for building_id in building_ids:
        ref_surfaces = reference.get(building_id, [])
        als_metrics = compare_building(ref_surfaces, als_pred.get(building_id, []))
        dim_metrics = compare_building(ref_surfaces, dim_pred.get(building_id, []))
        rows.append(building_metric_row(building_id, ref_surfaces, als_metrics, dim_metrics))

    metrics_csv = docs / "W3_1_roofer_quality_metrics.csv"
    summary_csv = docs / "W3_1_roofer_quality_summary.csv"
    threshold_csv = docs / "W3_1_threshold_position.csv"
    write_csv(metrics_csv, rows)
    summary_rows = build_summary(rows)
    threshold_rows = build_threshold_rows(summary_rows)
    write_csv(summary_csv, summary_rows)
    write_csv(threshold_csv, threshold_rows)

    fig_paths = {
        "plane": figs / "w3_1_plane_f1_boxplot.png",
        "boundary": figs / "w3_1_boundary_error_boxplots.png",
        "height": figs / "w3_1_height_error_boxplots.png",
    }
    plot_plane_f1(rows, fig_paths["plane"])
    plot_boundary(rows, fig_paths["boundary"])
    plot_height(rows, fig_paths["height"])

    report = docs / "W3_1_roofer_quality.md"
    write_report(report, run_id, len(building_ids), summary_rows, threshold_rows, fig_paths)
    snapshot_paths = [metrics_csv, summary_csv, threshold_csv, report, *fig_paths.values()]
    copy_outputs(run_dir, snapshot_paths)
    write_run_summary(run_dir / "w3_1_summary.json", building_ids, summary_rows, threshold_rows, fig_paths)

    print(f"buildings={len(building_ids)}")
    print(f"metrics={rel(metrics_csv)}")
    print(f"summary={rel(summary_csv)}")
    print(f"thresholds={rel(threshold_csv)}")
    print(f"report={rel(report)}")


def parse_lod2_roofs(lod2_dir: Path, target_ids: set[str]) -> dict[str, list[RoofSurface]]:
    output: dict[str, list[RoofSurface]] = {building_id: [] for building_id in target_ids}
    for path in sorted(lod2_dir.glob("*.gml")):
        for _event, elem in etree.iterparse(str(path), events=("end",), recover=True):
            if local_name(elem.tag) != "Building":
                continue
            building_id = gml_id(elem)
            if building_id in target_ids:
                output[building_id].extend(extract_gml_roof_surfaces(building_id, elem))
            elem.clear()
            parent = elem.getparent()
            while parent is not None and elem.getprevious() is not None:
                del parent[0]
    missing = [building_id for building_id, surfaces in output.items() if not surfaces]
    if missing:
        raise RuntimeError(f"Reference RoofSurface polygons missing for {len(missing)} buildings: {missing[:5]}")
    return output


def extract_gml_roof_surfaces(building_id: str, building: etree._Element) -> list[RoofSurface]:
    surfaces = []
    roof_idx = 0
    for roof in building.iter():
        if local_name(roof.tag) != "RoofSurface":
            continue
        roof_idx += 1
        roof_id = gml_id(roof) or f"{building_id}_roof_{roof_idx}"
        poly_idx = 0
        for polygon in roof.iter():
            if local_name(polygon.tag) != "Polygon":
                continue
            poly_idx += 1
            rings = parse_gml_polygon_rings(polygon)
            if not rings:
                continue
            surface = roof_surface_from_rings(f"{roof_id}_{poly_idx}", rings)
            if surface:
                surfaces.append(surface)
    return surfaces


def parse_gml_polygon_rings(polygon: etree._Element) -> list[np.ndarray]:
    exterior: np.ndarray | None = None
    interiors: list[np.ndarray] = []
    for child in polygon:
        lname = local_name(child.tag)
        if lname == "exterior":
            exterior = first_poslist_ring(child)
        elif lname == "interior":
            ring = first_poslist_ring(child)
            if ring is not None:
                interiors.append(ring)
    if exterior is None:
        rings = [parse_poslist(elem.text) for elem in polygon.iter() if local_name(elem.tag) == "posList" and elem.text]
        return rings
    return [exterior, *interiors]


def first_poslist_ring(elem: etree._Element) -> np.ndarray | None:
    for child in elem.iter():
        if local_name(child.tag) == "posList" and child.text:
            return parse_poslist(child.text)
    return None


def parse_cityjson_roofs(path: Path, target_ids: set[str]) -> dict[str, list[RoofSurface]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    transform = payload.get("transform") or {}
    vertices = absolute_vertices(payload.get("vertices", []), transform)
    cityobjects = payload.get("CityObjects", {})
    output: dict[str, list[RoofSurface]] = {building_id: [] for building_id in target_ids}
    for building_id in target_ids:
        object_ids = [building_id, *cityobjects.get(building_id, {}).get("children", [])]
        surfaces = []
        for object_id in object_ids:
            obj = cityobjects.get(object_id)
            if not obj:
                continue
            surfaces.extend(extract_cityjson_roof_surfaces(object_id, obj, vertices))
        output[building_id] = surfaces
    missing = [building_id for building_id, surfaces in output.items() if not surfaces]
    if missing:
        raise RuntimeError(f"Predicted RoofSurface polygons missing in {path} for {len(missing)} buildings: {missing[:5]}")
    return output


def absolute_vertices(vertices: list[list[int | float]], transform: dict[str, list[float]]) -> np.ndarray:
    arr = np.asarray(vertices, dtype=float)
    if not len(arr):
        return arr.reshape((0, 3))
    scale = np.asarray(transform.get("scale", [1.0, 1.0, 1.0]), dtype=float)
    translate = np.asarray(transform.get("translate", [0.0, 0.0, 0.0]), dtype=float)
    return arr * scale + translate


def extract_cityjson_roof_surfaces(object_id: str, obj: dict[str, Any], vertices: np.ndarray) -> list[RoofSurface]:
    surfaces = []
    for geom_idx, geom in enumerate(obj.get("geometry", [])):
        if str(geom.get("lod")) != "2.2":
            continue
        semantics = geom.get("semantics") or {}
        semantic_surfaces = semantics.get("surfaces") or []
        values = semantics.get("values")
        for face_idx, (rings, sem_idx) in enumerate(iter_cityjson_faces(geom.get("type"), geom.get("boundaries"), values)):
            if sem_idx is None or sem_idx >= len(semantic_surfaces):
                continue
            if semantic_surfaces[sem_idx].get("type") != "RoofSurface":
                continue
            ring_coords = []
            for ring in rings:
                if not ring:
                    continue
                ring_coords.append(np.asarray([vertices[int(idx)] for idx in ring], dtype=float))
            if not ring_coords:
                continue
            surface = roof_surface_from_rings(f"{object_id}_g{geom_idx}_f{face_idx}", ring_coords)
            if surface:
                surfaces.append(surface)
    return surfaces


def iter_cityjson_faces(
    geom_type: str | None,
    boundaries: Any,
    values: Any,
) -> list[tuple[list[list[int]], int | None]]:
    faces: list[tuple[list[list[int]], int | None]] = []
    if boundaries is None:
        return faces
    if geom_type == "Solid":
        for shell_idx, shell in enumerate(boundaries):
            shell_values = values[shell_idx] if isinstance(values, list) and shell_idx < len(values) else []
            for face_idx, rings in enumerate(shell):
                sem_idx = shell_values[face_idx] if isinstance(shell_values, list) and face_idx < len(shell_values) else None
                faces.append((rings, sem_idx))
    elif geom_type in {"MultiSurface", "CompositeSurface"}:
        for face_idx, rings in enumerate(boundaries):
            sem_idx = values[face_idx] if isinstance(values, list) and face_idx < len(values) else None
            faces.append((rings, sem_idx))
    elif geom_type == "MultiSolid":
        for solid_idx, solid in enumerate(boundaries):
            solid_values = values[solid_idx] if isinstance(values, list) and solid_idx < len(values) else []
            for shell_idx, shell in enumerate(solid):
                shell_values = solid_values[shell_idx] if isinstance(solid_values, list) and shell_idx < len(solid_values) else []
                for face_idx, rings in enumerate(shell):
                    sem_idx = shell_values[face_idx] if isinstance(shell_values, list) and face_idx < len(shell_values) else None
                    faces.append((rings, sem_idx))
    return faces


def roof_surface_from_rings(surface_id: str, rings: list[np.ndarray]) -> RoofSurface | None:
    exterior = normalize_ring_3d(rings[0])
    if exterior is None:
        return None
    holes = []
    for ring in rings[1:]:
        normalized = normalize_ring_3d(ring)
        if normalized is not None:
            holes.append(normalized[:, :2])
    polygon = repair_polygon(Polygon(exterior[:, :2], holes))
    if polygon is None or polygon.area <= 0.05:
        return None
    x0, y0, z0, ax, by = fit_z_plane(exterior)
    return RoofSurface(
        surface_id=surface_id,
        polygon=polygon,
        x0=x0,
        y0=y0,
        z0=z0,
        ax=ax,
        by=by,
        vertex_count=int(exterior.shape[0]),
    )


def normalize_ring_3d(coords: np.ndarray) -> np.ndarray | None:
    arr = np.asarray(coords, dtype=float)
    if arr.ndim != 2 or arr.shape[1] != 3 or arr.shape[0] < 4:
        return None
    if not np.all(np.isfinite(arr)):
        return None
    if not np.allclose(arr[0], arr[-1]):
        arr = np.vstack([arr, arr[0]])
    if polygon_area_xy(arr[:, :2]) <= 0.05:
        return None
    return arr


def repair_polygon(poly: Polygon) -> Polygon | MultiPolygon | None:
    if poly.is_empty:
        return None
    if not poly.is_valid:
        poly = make_valid(poly)
    polygons = []
    for geom in flatten_polygons(poly):
        if geom.area > 0.05:
            polygons.append(geom)
    if not polygons:
        return None
    if len(polygons) == 1:
        return polygons[0]
    return MultiPolygon(polygons)


def flatten_polygons(geom: Any) -> list[Polygon]:
    if geom.is_empty:
        return []
    if isinstance(geom, Polygon):
        return [geom]
    if isinstance(geom, MultiPolygon):
        return list(geom.geoms)
    if isinstance(geom, GeometryCollection):
        out = []
        for item in geom.geoms:
            out.extend(flatten_polygons(item))
        return out
    return []


def fit_z_plane(coords: np.ndarray) -> tuple[float, float, float, float, float]:
    points = coords[:-1] if np.allclose(coords[0], coords[-1]) else coords
    x0 = float(np.mean(points[:, 0]))
    y0 = float(np.mean(points[:, 1]))
    z0 = float(np.mean(points[:, 2]))
    a = np.column_stack([points[:, 0] - x0, points[:, 1] - y0])
    b = points[:, 2] - z0
    if len(points) < 3:
        return x0, y0, z0, 0.0, 0.0
    try:
        ax, by = np.linalg.lstsq(a, b, rcond=None)[0]
    except np.linalg.LinAlgError:
        ax, by = 0.0, 0.0
    return x0, y0, z0, float(ax), float(by)


def compare_building(ref_surfaces: list[RoofSurface], pred_surfaces: list[RoofSurface]) -> dict[str, Any]:
    matches = match_surfaces(ref_surfaces, pred_surfaces)
    ref_n = len(ref_surfaces)
    pred_n = len(pred_surfaces)
    tp = len(matches)
    precision = tp / pred_n if pred_n else math.nan
    recall = tp / ref_n if ref_n else math.nan
    f1 = 2 * precision * recall / (precision + recall) if precision + recall > 0 else 0.0

    boundary = boundary_metrics(ref_surfaces, pred_surfaces)
    height = height_metrics(matches)
    return {
        "pred_roof_planes": pred_n,
        "plane_tp": tp,
        "plane_precision": precision,
        "plane_recall": recall,
        "plane_f1": f1,
        "mean_matched_iou": float(np.mean([m["iou"] for m in matches])) if matches else math.nan,
        **boundary,
        **height,
    }


def match_surfaces(ref_surfaces: list[RoofSurface], pred_surfaces: list[RoofSurface]) -> list[dict[str, Any]]:
    candidates = []
    for ref_idx, ref in enumerate(ref_surfaces):
        for pred_idx, pred in enumerate(pred_surfaces):
            union_area = ref.polygon.union(pred.polygon).area
            if union_area <= 0:
                continue
            iou = ref.polygon.intersection(pred.polygon).area / union_area
            if iou >= IOU_THRESHOLD:
                candidates.append((iou, ref_idx, pred_idx))
    candidates.sort(reverse=True)
    used_ref: set[int] = set()
    used_pred: set[int] = set()
    matches = []
    for iou, ref_idx, pred_idx in candidates:
        if ref_idx in used_ref or pred_idx in used_pred:
            continue
        used_ref.add(ref_idx)
        used_pred.add(pred_idx)
        matches.append({"ref": ref_surfaces[ref_idx], "pred": pred_surfaces[pred_idx], "iou": iou})
    return matches


def boundary_metrics(ref_surfaces: list[RoofSurface], pred_surfaces: list[RoofSurface]) -> dict[str, Any]:
    ref_union = surface_union(ref_surfaces)
    pred_union = surface_union(pred_surfaces)
    ref_points = sample_boundary_points(ref_union, BOUNDARY_SAMPLE_SPACING_M)
    pred_points = sample_boundary_points(pred_union, BOUNDARY_SAMPLE_SPACING_M)
    if len(ref_points) == 0 or len(pred_points) == 0:
        return {
            "boundary_chamfer_m": math.nan,
            "boundary_hausdorff_m": math.nan,
            "boundary_ref_samples": len(ref_points),
            "boundary_pred_samples": len(pred_points),
        }
    ref_to_pred = min_distances(ref_points, pred_points)
    pred_to_ref = min_distances(pred_points, ref_points)
    return {
        "boundary_chamfer_m": float((np.mean(ref_to_pred) + np.mean(pred_to_ref)) / 2.0),
        "boundary_hausdorff_m": float(max(np.max(ref_to_pred), np.max(pred_to_ref))),
        "boundary_ref_samples": len(ref_points),
        "boundary_pred_samples": len(pred_points),
    }


def surface_union(surfaces: list[RoofSurface]) -> Polygon | MultiPolygon | GeometryCollection:
    polygons = [surface.polygon for surface in surfaces if not surface.polygon.is_empty]
    if not polygons:
        return GeometryCollection()
    return unary_union(polygons)


def sample_boundary_points(geom: Any, spacing: float) -> np.ndarray:
    if geom.is_empty:
        return np.empty((0, 2), dtype=float)
    boundary = geom.boundary
    lines = flatten_lines(boundary)
    points = []
    for line in lines:
        length = float(line.length)
        if length <= 0:
            continue
        n = max(2, int(math.ceil(length / spacing)) + 1)
        for distance in np.linspace(0.0, length, n):
            pt = line.interpolate(float(distance))
            points.append((pt.x, pt.y))
    return np.asarray(points, dtype=float) if points else np.empty((0, 2), dtype=float)


def flatten_lines(geom: Any) -> list[LineString]:
    if geom.is_empty:
        return []
    if isinstance(geom, LineString):
        return [geom]
    if isinstance(geom, MultiLineString):
        return list(geom.geoms)
    if isinstance(geom, GeometryCollection):
        out = []
        for item in geom.geoms:
            out.extend(flatten_lines(item))
        return out
    return []


def min_distances(source: np.ndarray, target: np.ndarray, chunk_size: int = 2048) -> np.ndarray:
    mins = np.empty(source.shape[0], dtype=float)
    target_x = target[:, 0][None, :]
    target_y = target[:, 1][None, :]
    for start in range(0, source.shape[0], chunk_size):
        chunk = source[start : start + chunk_size]
        dx = chunk[:, 0][:, None] - target_x
        dy = chunk[:, 1][:, None] - target_y
        mins[start : start + chunk.shape[0]] = np.sqrt(np.min(dx * dx + dy * dy, axis=1))
    return mins


def height_metrics(matches: list[dict[str, Any]]) -> dict[str, Any]:
    diffs: list[np.ndarray] = []
    for match in matches:
        intersection = match["ref"].polygon.intersection(match["pred"].polygon)
        samples = sample_polygon_points(intersection, HEIGHT_SAMPLE_SPACING_M)
        if len(samples) == 0:
            continue
        ref_z = match["ref"].z_at(samples[:, 0], samples[:, 1])
        pred_z = match["pred"].z_at(samples[:, 0], samples[:, 1])
        diffs.append(pred_z - ref_z)
    if not diffs:
        return {"height_bias_m": math.nan, "height_nmad_m": math.nan, "height_sample_count": 0}
    values = np.concatenate(diffs)
    median = float(np.median(values))
    nmad = float(1.4826 * np.median(np.abs(values - median)))
    return {"height_bias_m": median, "height_nmad_m": nmad, "height_sample_count": int(values.size)}


def sample_polygon_points(geom: Any, spacing: float) -> np.ndarray:
    polygons = flatten_polygons(geom)
    points: list[tuple[float, float]] = []
    for polygon in polygons:
        if polygon.area <= 0:
            continue
        min_x, min_y, max_x, max_y = polygon.bounds
        xs = np.arange(min_x + spacing / 2.0, max_x, spacing)
        ys = np.arange(min_y + spacing / 2.0, max_y, spacing)
        if xs.size and ys.size:
            xx, yy = np.meshgrid(xs, ys)
            mask = contains_xy(polygon, xx.ravel(), yy.ravel())
            points.extend(zip(xx.ravel()[mask], yy.ravel()[mask]))
        if not points:
            pt = polygon.representative_point()
            points.append((pt.x, pt.y))
    return np.asarray(points, dtype=float) if points else np.empty((0, 2), dtype=float)


def building_metric_row(
    building_id: str,
    ref_surfaces: list[RoofSurface],
    als: dict[str, Any],
    dim: dict[str, Any],
) -> dict[str, str]:
    row: dict[str, str] = {
        "building_id": building_id,
        "ref_roof_planes": str(len(ref_surfaces)),
        "als_pred_roof_planes": str(als["pred_roof_planes"]),
        "dim_pred_roof_planes": str(dim["pred_roof_planes"]),
    }
    for label, metrics in (("als", als), ("dim", dim)):
        for key in [
            "plane_tp",
            "plane_precision",
            "plane_recall",
            "plane_f1",
            "mean_matched_iou",
            "boundary_chamfer_m",
            "boundary_hausdorff_m",
            "boundary_ref_samples",
            "boundary_pred_samples",
            "height_bias_m",
            "height_nmad_m",
            "height_sample_count",
        ]:
            row[f"{label}_{key}"] = format_value(metrics[key])
    row["dim_minus_als_plane_f1"] = format_value(dim["plane_f1"] - als["plane_f1"])
    row["dim_over_als_boundary_chamfer"] = format_value(safe_ratio(dim["boundary_chamfer_m"], als["boundary_chamfer_m"]))
    row["dim_over_als_boundary_hausdorff"] = format_value(
        safe_ratio(dim["boundary_hausdorff_m"], als["boundary_hausdorff_m"])
    )
    row["dim_minus_als_height_bias_m"] = format_value(dim["height_bias_m"] - als["height_bias_m"])
    row["dim_over_als_height_nmad"] = format_value(safe_ratio(dim["height_nmad_m"], als["height_nmad_m"]))
    return row


def build_summary(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    metrics = [
        ("plane_f1", "higher_is_better"),
        ("boundary_chamfer_m", "lower_is_better"),
        ("boundary_hausdorff_m", "lower_is_better"),
        ("height_bias_m", "signed_median_pred_minus_ref"),
        ("height_nmad_m", "lower_is_better"),
    ]
    summary = []
    for metric, interpretation in metrics:
        als_values, dim_values = paired_numeric_columns(rows, f"als_{metric}", f"dim_{metric}")
        als_median = median(als_values)
        dim_median = median(dim_values)
        ratio = "" if interpretation == "signed_median_pred_minus_ref" else format_value(safe_ratio(dim_median, als_median))
        summary.append(
            {
                "metric": metric,
                "n": str(len(als_values)),
                "als_median": format_value(als_median),
                "dim_median": format_value(dim_median),
                "dim_minus_als": format_value(dim_median - als_median),
                "dim_over_als": ratio,
                "interpretation": interpretation,
            }
        )
    return summary


def build_threshold_rows(summary_rows: list[dict[str, str]]) -> list[dict[str, str]]:
    by_metric = {row["metric"]: row for row in summary_rows}
    plane_drop = parse_float(by_metric["plane_f1"]["als_median"]) - parse_float(by_metric["plane_f1"]["dim_median"])
    chamfer_ratio = parse_float(by_metric["boundary_chamfer_m"]["dim_over_als"])
    hausdorff_ratio = parse_float(by_metric["boundary_hausdorff_m"]["dim_over_als"])
    return [
        {
            "p0_section6_item": "plane_f1_drop",
            "observed_value": format_value(plane_drop),
            "threshold_value": format_value(PLANE_F1_DROP_THRESHOLD),
            "observed_minus_threshold": format_value(plane_drop - PLANE_F1_DROP_THRESHOLD),
            "definition": "ALS median plane_f1 - DIM median plane_f1",
        },
        {
            "p0_section6_item": "boundary_chamfer_ratio",
            "observed_value": format_value(chamfer_ratio),
            "threshold_value": format_value(BOUNDARY_RATIO_THRESHOLD),
            "observed_minus_threshold": format_value(chamfer_ratio - BOUNDARY_RATIO_THRESHOLD),
            "definition": "DIM median boundary_chamfer_m / ALS median boundary_chamfer_m",
        },
        {
            "p0_section6_item": "boundary_hausdorff_ratio",
            "observed_value": format_value(hausdorff_ratio),
            "threshold_value": format_value(BOUNDARY_RATIO_THRESHOLD),
            "observed_minus_threshold": format_value(hausdorff_ratio - BOUNDARY_RATIO_THRESHOLD),
            "definition": "DIM median boundary_hausdorff_m / ALS median boundary_hausdorff_m",
        },
    ]


def plot_plane_f1(rows: list[dict[str, str]], path: Path) -> None:
    paired_boxplot(
        rows,
        [("als_plane_f1", "ALS"), ("dim_plane_f1", "DIM")],
        "Plane Instance F1",
        "F1",
        path,
    )


def plot_boundary(rows: list[dict[str, str]], path: Path) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(10, 4), dpi=160)
    paired_boxplot_on_axis(rows, [("als_boundary_chamfer_m", "ALS"), ("dim_boundary_chamfer_m", "DIM")], axes[0])
    axes[0].set_title("Chamfer")
    axes[0].set_ylabel("meters")
    paired_boxplot_on_axis(
        rows,
        [("als_boundary_hausdorff_m", "ALS"), ("dim_boundary_hausdorff_m", "DIM")],
        axes[1],
    )
    axes[1].set_title("Hausdorff")
    axes[1].set_ylabel("meters")
    fig.suptitle("Roof Outline Boundary Error")
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path)
    plt.close(fig)


def plot_height(rows: list[dict[str, str]], path: Path) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(10, 4), dpi=160)
    paired_boxplot_on_axis(rows, [("als_height_bias_m", "ALS"), ("dim_height_bias_m", "DIM")], axes[0])
    axes[0].axhline(0.0, color="0.4", linewidth=0.8)
    axes[0].set_title("Signed Bias")
    axes[0].set_ylabel("meters")
    paired_boxplot_on_axis(rows, [("als_height_nmad_m", "ALS"), ("dim_height_nmad_m", "DIM")], axes[1])
    axes[1].set_title("NMAD Spread")
    axes[1].set_ylabel("meters")
    fig.suptitle("Roof Height Error")
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path)
    plt.close(fig)


def paired_boxplot(rows: list[dict[str, str]], columns: list[tuple[str, str]], title: str, ylabel: str, path: Path) -> None:
    fig, ax = plt.subplots(figsize=(5, 4), dpi=160)
    paired_boxplot_on_axis(rows, columns, ax)
    ax.set_title(title)
    ax.set_ylabel(ylabel)
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path)
    plt.close(fig)


def paired_boxplot_on_axis(rows: list[dict[str, str]], columns: list[tuple[str, str]], ax: Any) -> None:
    values = [numeric_column(rows, column) for column, _label in columns]
    ax.boxplot(values, tick_labels=[label for _column, label in columns], showfliers=False)
    for idx, vals in enumerate(values, start=1):
        jitter = np.linspace(-0.06, 0.06, len(vals)) if vals else []
        ax.scatter(np.full(len(vals), idx) + jitter, vals, s=9, alpha=0.45, zorder=3)
    if len(columns) == 2:
        left = [parse_float(row[columns[0][0]]) for row in rows]
        right = [parse_float(row[columns[1][0]]) for row in rows]
        for a, b in zip(left, right):
            if a is not None and b is not None:
                ax.plot([1, 2], [a, b], color="0.7", linewidth=0.4, alpha=0.45, zorder=1)
    ax.grid(axis="y", color="0.9", linewidth=0.8)


def write_report(
    path: Path,
    run_id: str,
    n_buildings: int,
    summary_rows: list[dict[str, str]],
    threshold_rows: list[dict[str, str]],
    fig_paths: dict[str, Path],
) -> None:
    lines = [
        "# W3-1 Roofer Roof Quality Metrics",
        "",
        f"- Run ID: `{run_id}`",
        f"- Population: Roofer default both_success paired set, {n_buildings} buildings from `docs/W2_1c_paired_status.csv`.",
        "- Reference: LoD2 CityGML `RoofSurface` polygons from `data/raw/lod2/*.gml`.",
        "- Predictions: Roofer default ALS/DIM CityJSON from `runs/w2_1_roofer_default_20260612_152729/cityjson/`.",
        f"- Plane matching: XY projected roof polygons, one-to-one greedy matching, IoU >= {IOU_THRESHOLD:.2f}.",
        f"- Boundary metrics: roof-union outline sampled every {BOUNDARY_SAMPLE_SPACING_M:.2f} m; symmetric Chamfer and Hausdorff in meters.",
        f"- Height metrics: matched roof intersection samples every {HEIGHT_SAMPLE_SPACING_M:.2f} m; `pred_z - ref_z` median bias and NMAD spread.",
        "",
        "## Median Summary",
        "",
    ]
    lines.extend(markdown_table(summary_rows))
    lines.extend(["", "## P0 Section 6 Threshold Position", ""])
    lines.extend(markdown_table(threshold_rows))
    lines.extend(
        [
            "",
            "## Figures",
            "",
            f"![Plane F1](figs/{fig_paths['plane'].name})",
            "",
            f"![Boundary errors](figs/{fig_paths['boundary'].name})",
            "",
            f"![Height errors](figs/{fig_paths['height'].name})",
            "",
            "## Files",
            "",
            "- Building metrics: `docs/W3_1_roofer_quality_metrics.csv`",
            "- Median summary: `docs/W3_1_roofer_quality_summary.csv`",
            "- Threshold position table: `docs/W3_1_threshold_position.csv`",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_run_summary(
    path: Path,
    building_ids: list[str],
    summary_rows: list[dict[str, str]],
    threshold_rows: list[dict[str, str]],
    fig_paths: dict[str, Path],
) -> None:
    payload = {
        "task": TASK_ID,
        "run_id": os.environ["RUN_ID"],
        "base_w2_run_id": BASE_W2_RUN_ID,
        "building_count": len(building_ids),
        "iou_threshold": IOU_THRESHOLD,
        "boundary_sample_spacing_m": BOUNDARY_SAMPLE_SPACING_M,
        "height_sample_spacing_m": HEIGHT_SAMPLE_SPACING_M,
        "summary": summary_rows,
        "threshold_position": threshold_rows,
        "figures": {key: rel(path) for key, path in fig_paths.items()},
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_host_config(run_dir: Path, run_id: str, git_commit: str) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    config = {
        "task": "W3-1_roofer_quality_metrics",
        "run_id": run_id,
        "git_commit": git_commit,
        "base_w2_run_id": BASE_W2_RUN_ID,
        "population": "W2-1c coverage_control_population=yes and paired_category=both_success",
        "expected_population_n": 67,
        "reference_lod2": "data/raw/lod2/*.gml",
        "als_cityjson": ALS_CITYJSON.replace("/workspace/", ""),
        "dim_cityjson": DIM_CITYJSON.replace("/workspace/", ""),
        "plane_matching": {"projected_iou_threshold": IOU_THRESHOLD, "matching": "greedy one-to-one"},
        "boundary_sample_spacing_m": BOUNDARY_SAMPLE_SPACING_M,
        "height_sample_spacing_m": HEIGHT_SAMPLE_SPACING_M,
        "p0_section6_thresholds": {
            "plane_f1_drop": PLANE_F1_DROP_THRESHOLD,
            "boundary_error_ratio": BOUNDARY_RATIO_THRESHOLD,
        },
    }
    (run_dir / "config.yaml").write_text(to_yaml(config), encoding="utf-8")


def write_host_versions(
    repo: Path,
    run_dir: Path,
    compose: list[str],
    env: dict[str, str],
    git_commit: str,
) -> None:
    lines = [
        "# W3-1 Tool Versions",
        "",
        f"- Generated: {datetime.now(timezone.utc).astimezone().isoformat(timespec='seconds')}",
        f"- Run ID: {run_dir.name}",
        f"- Repository commit: {git_commit}",
        "",
        "```console",
    ]
    commands = [
        ["git", "status", "--short", "--branch"],
        [
            *compose,
            "run",
            "-T",
            "--rm",
            "tools",
            "python",
            "-c",
            "import numpy, matplotlib, shapely, lxml; print('numpy ' + numpy.__version__); print('matplotlib ' + matplotlib.__version__); print('shapely ' + shapely.__version__); print('lxml ' + lxml.__version__)",
        ],
    ]
    for cmd in commands:
        lines.append("$ " + " ".join(cmd))
        lines.append(capture(cmd, cwd=repo if cmd[0] != "git" else repo.parent, env=env))
    lines.append("```")
    (run_dir / "versions.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")


def run(
    cmd: list[str],
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
    log_path: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    print("+ " + " ".join(cmd), flush=True)
    if log_path:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("w", encoding="utf-8") as log:
            log.write("+ " + " ".join(cmd) + "\n")
            proc = subprocess.run(
                cmd,
                cwd=cwd,
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
            )
            log.write(proc.stdout)
            print(proc.stdout, end="", flush=True)
            proc.check_returncode()
            return proc
    return subprocess.run(cmd, cwd=cwd, env=env, text=True, check=True)


def capture(cmd: list[str], cwd: Path | None = None, env: dict[str, str] | None = None) -> str:
    proc = subprocess.run(cmd, cwd=cwd, env=env, text=True, capture_output=True, check=False)
    return ((proc.stdout or "") + (proc.stderr or "")).strip()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    if not rows:
        raise RuntimeError(f"No rows for {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def copy_outputs(run_dir: Path, paths: list[Path]) -> None:
    snapshot = run_dir / "docs_snapshot"
    snapshot.mkdir(parents=True, exist_ok=True)
    for path in paths:
        shutil.copy2(path, snapshot / path.name)


def markdown_table(rows: list[dict[str, str]]) -> list[str]:
    if not rows:
        return ["_No rows._"]
    headers = list(rows[0].keys())
    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"]
    for row in rows:
        lines.append("| " + " | ".join(str(row.get(header, "")) for header in headers) + " |")
    return lines


def numeric_column(rows: list[dict[str, str]], key: str) -> list[float]:
    values = []
    for row in rows:
        value = parse_float(row.get(key, ""))
        if value is not None and math.isfinite(value):
            values.append(value)
    return values


def paired_numeric_columns(rows: list[dict[str, str]], left_key: str, right_key: str) -> tuple[list[float], list[float]]:
    left_values = []
    right_values = []
    for row in rows:
        left = parse_float(row.get(left_key, ""))
        right = parse_float(row.get(right_key, ""))
        if left is None or right is None:
            continue
        if math.isfinite(left) and math.isfinite(right):
            left_values.append(left)
            right_values.append(right)
    return left_values, right_values


def parse_float(value: str | float | None) -> float | None:
    if value is None or value == "":
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(result):
        return None
    return result


def median(values: list[float]) -> float:
    if not values:
        return math.nan
    return float(np.median(np.asarray(values, dtype=float)))


def safe_ratio(numerator: float, denominator: float) -> float:
    if denominator is None or not math.isfinite(denominator) or abs(denominator) < 1e-12:
        return math.nan
    return float(numerator / denominator)


def format_value(value: Any) -> str:
    if isinstance(value, (int, np.integer)):
        return str(int(value))
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return str(value)
    if not math.isfinite(numeric):
        return ""
    return f"{numeric:.6f}"


def polygon_area_xy(xy: np.ndarray) -> float:
    x = xy[:, 0]
    y = xy[:, 1]
    return float(0.5 * abs(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1))))


def parse_poslist(text: str) -> np.ndarray:
    values = [float(value) for value in text.split()]
    if len(values) % 3 == 0:
        return np.asarray(values, dtype=float).reshape((-1, 3))
    if len(values) % 2 == 0:
        xy = np.asarray(values, dtype=float).reshape((-1, 2))
        return np.column_stack([xy, np.zeros(xy.shape[0])])
    raise ValueError("gml:posList has neither 2D nor 3D coordinate stride")


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def gml_id(elem: etree._Element) -> str:
    return elem.get("{http://www.opengis.net/gml}id") or elem.get("id") or ""


def rel(path: Path) -> str:
    return path.as_posix().replace("/workspace/", "").replace("phases/p0-audit/", "")


def to_yaml(value: Any, indent: int = 0) -> str:
    space = " " * indent
    if isinstance(value, dict):
        lines = []
        for key, item in value.items():
            if isinstance(item, (dict, list)):
                lines.append(f"{space}{key}:")
                lines.append(to_yaml(item, indent + 2))
            else:
                lines.append(f"{space}{key}: {yaml_scalar(item)}")
        return "\n".join(lines) + ("\n" if indent == 0 else "")
    if isinstance(value, list):
        lines = []
        for item in value:
            if isinstance(item, (dict, list)):
                lines.append(f"{space}-")
                lines.append(to_yaml(item, indent + 2))
            else:
                lines.append(f"{space}- {yaml_scalar(item)}")
        return "\n".join(lines)
    return f"{space}{yaml_scalar(value)}"


def yaml_scalar(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return "null"
    if isinstance(value, (int, float)):
        return str(value)
    text = str(value)
    if not text or any(ch in text for ch in [":", "#", "{", "}", "[", "]", ",", "\n"]):
        return json.dumps(text, ensure_ascii=False)
    return text


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("host", "compute"), default="host")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.mode == "host":
        host_entrypoint()
    elif args.mode == "compute":
        compute_entrypoint()
    else:
        raise AssertionError(args.mode)


if __name__ == "__main__":
    main()
