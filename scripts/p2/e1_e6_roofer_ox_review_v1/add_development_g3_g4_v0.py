#!/usr/bin/env python3
"""Add non-confirmatory G3/G4 development diagnostics to the E1-E6 viewer.

This add-on reads the frozen v14 viewer assets. It does not run Roofer, train a
model, or rewrite a source artifact. G3 uses the current-UAS E1 Roofer result as
a method-derived structure proxy. G4 uses the current-UAS building point sample
already bound to the viewer. All results are explicitly development candidates;
official PASS_usable and scientific_verdict remain null.
"""
from __future__ import annotations

import argparse
from collections import Counter
import csv
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
from typing import Any

import numpy as np
from shapely import contains_xy
from shapely.affinity import translate
from shapely.geometry import Polygon, box, shape
from shapely.ops import unary_union


REPO = Path(__file__).resolve().parents[3]
CONFIG = REPO / "configs/p2/e1_e6_roofer_ox_review_v1/development_g3_g4_v0.json"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def exact_file(path: Path, spec: dict[str, Any]) -> None:
    if not path.is_file():
        raise RuntimeError(f"missing bound source: {path}")
    if path.stat().st_size != int(spec["bytes"]) or sha256(path) != spec["sha256"]:
        raise RuntimeError(f"bound source drifted: {path}")


def canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def write_new(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as handle:
        handle.write(payload)


def file_record(path: Path, root: Path) -> dict[str, Any]:
    return {"path": path.relative_to(root).as_posix(), "bytes": path.stat().st_size, "sha256": sha256(path)}


def load_config(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if value.get("schema") != "jointbuildgs.p2.e1_e6_roofer_development_g3_g4.v0":
        raise RuntimeError("development criterion schema drifted")
    if value.get("status") != "USER_APPROVED_DEVELOPMENT_DIAGNOSTIC":
        raise RuntimeError("development diagnostic is not approved")
    if value.get("official_PASS_usable", "missing") is not None or value.get("scientific_verdict", "missing") is not None:
        raise RuntimeError("official verdict fields must remain null")
    if value.get("criterion_version") != "ROOFER_G3G4_DEVELOPMENT_V0P1_NOT_FROZEN":
        raise RuntimeError("criterion must remain visibly non-frozen")
    return value


def parse_obj_triangles(path: Path | None) -> np.ndarray:
    if path is None or not path.is_file():
        return np.empty((0, 3, 3), dtype=np.float64)
    vertices: list[list[float]] = []
    triangles: list[np.ndarray] = []
    for line in path.read_text(encoding="ascii").splitlines():
        if line.startswith("v "):
            vertices.append([float(value) for value in line.split()[1:4]])
        elif line.startswith("f "):
            indices = [int(token.split("/")[0]) - 1 for token in line.split()[1:]]
            for index in range(1, len(indices) - 1):
                triangles.append(np.asarray([vertices[indices[0]], vertices[indices[index]], vertices[indices[index + 1]]]))
    return np.asarray(triangles, dtype=np.float64).reshape(-1, 3, 3)


def roof_triangles(triangles: np.ndarray) -> np.ndarray:
    if len(triangles) == 0:
        return triangles
    normals = np.cross(triangles[:, 1] - triangles[:, 0], triangles[:, 2] - triangles[:, 0])
    norm = np.linalg.norm(normals, axis=1)
    valid = norm > 1e-8
    unit_z = np.zeros(len(triangles), dtype=np.float64)
    unit_z[valid] = np.abs(normals[valid, 2] / norm[valid])
    floor = float(np.percentile(triangles[:, :, 2], 5))
    ceiling = float(np.percentile(triangles[:, :, 2], 95))
    center_z = triangles[:, :, 2].mean(axis=1)
    above_floor = center_z > floor + 1.0 if ceiling - floor > 1.0 else np.ones(len(triangles), dtype=bool)
    return triangles[valid & (unit_z >= 0.15) & above_floor]


def triangle_plane(triangle: np.ndarray, center_xy: np.ndarray) -> tuple[np.ndarray, float] | None:
    normal = np.cross(triangle[1] - triangle[0], triangle[2] - triangle[0])
    norm = float(np.linalg.norm(normal))
    if norm <= 1e-8:
        return None
    normal /= norm
    if normal[2] < 0:
        normal = -normal
    if normal[2] <= 1e-6:
        return None
    d = -float(np.dot(normal, triangle[0]))
    z_center = -(normal[0] * center_xy[0] + normal[1] * center_xy[1] + d) / normal[2]
    return normal, float(z_center)


def cluster_roof_planes(triangles: np.ndarray, angle_deg: float, height_m: float) -> list[dict[str, Any]]:
    roofs = roof_triangles(triangles)
    if len(roofs) == 0:
        return []
    center_xy = roofs[:, :, :2].reshape(-1, 2).mean(axis=0)
    cos_min = math.cos(math.radians(angle_deg))
    clusters: list[dict[str, Any]] = []
    for triangle in roofs:
        plane = triangle_plane(triangle, center_xy)
        if plane is None:
            continue
        normal, z_center = plane
        polygon = Polygon(triangle[:, :2])
        if polygon.is_empty or polygon.area <= 1e-6:
            continue
        selected = None
        for cluster in clusters:
            if float(np.dot(cluster["normal"], normal)) >= cos_min and abs(cluster["z_center"] - z_center) <= height_m:
                selected = cluster
                break
        if selected is None:
            clusters.append({
                "normal": normal,
                "z_center": z_center,
                "polygons": [polygon],
                "points_xyz": [triangle],
            })
        else:
            selected["polygons"].append(polygon)
            selected["points_xyz"].append(triangle)
    result = []
    for cluster in clusters:
        geometry = unary_union(cluster["polygons"])
        if not geometry.is_empty and geometry.area > 1e-6:
            points = np.concatenate(cluster["points_xyz"], axis=0)
            design = np.column_stack((points[:, 0], points[:, 1], np.ones(len(points))))
            coefficients, *_ = np.linalg.lstsq(design, points[:, 2], rcond=None)
            a, b, c = map(float, coefficients)
            normal = np.asarray([-a, -b, 1.0], dtype=np.float64)
            normal /= np.linalg.norm(normal)
            center = geometry.centroid
            result.append({
                "polygon": geometry,
                "area_m2": float(geometry.area),
                "normal": normal,
                "z_center": float(a * center.x + b * center.y + c),
                "plane_coefficients": (a, b, c),
            })
    return result


def major_planes(planes: list[dict[str, Any]], area_min: float) -> list[dict[str, Any]]:
    chosen = [plane for plane in planes if plane["area_m2"] >= area_min]
    if chosen or not planes:
        return chosen
    return [max(planes, key=lambda value: value["area_m2"])]


def g3_metrics(reference: list[dict[str, Any]], prediction: list[dict[str, Any]], overlap_threshold: float) -> dict[str, Any]:
    if not reference or not prediction:
        return {"reference_plane_count": len(reference), "prediction_plane_count": len(prediction), "match_count": 0}
    edges = []
    for ref_index, ref in enumerate(reference):
        for pred_index, pred in enumerate(prediction):
            intersection = ref["polygon"].intersection(pred["polygon"])
            overlap = float(intersection.area)
            if overlap <= 0:
                continue
            ref_fraction = overlap / ref["area_m2"]
            pred_fraction = overlap / pred["area_m2"]
            if ref_fraction >= overlap_threshold and pred_fraction >= overlap_threshold:
                union = ref["area_m2"] + pred["area_m2"] - overlap
                edges.append((overlap / union if union > 0 else 0.0, overlap, ref_index, pred_index))
    used_ref: set[int] = set()
    used_pred: set[int] = set()
    matches = []
    for iou, overlap, ref_index, pred_index in sorted(edges, reverse=True):
        if ref_index in used_ref or pred_index in used_pred:
            continue
        used_ref.add(ref_index)
        used_pred.add(pred_index)
        matches.append((iou, overlap, ref_index, pred_index))
    ref_area = sum(value["area_m2"] for value in reference)
    pred_area = sum(value["area_m2"] for value in prediction)
    overlap_area = sum(value[1] for value in matches)
    union_area = ref_area + pred_area - overlap_area
    return {
        "reference_plane_count": len(reference),
        "prediction_plane_count": len(prediction),
        "match_count": len(matches),
        "area_completeness": overlap_area / ref_area if ref_area > 0 else None,
        "area_correctness": overlap_area / pred_area if pred_area > 0 else None,
        "area_quality": overlap_area / union_area if union_area > 0 else None,
        "dominant_plane_ratio": len(prediction) / len(reference) if reference else None,
    }


def classify_g3(metrics: dict[str, Any], thresholds: dict[str, Any]) -> tuple[str, list[str]]:
    required = ("area_completeness", "area_correctness", "area_quality")
    if any(metrics.get(key) is None for key in required):
        return "NOT_ASSESSED", ["structure_reference_or_prediction_missing"]
    ref_n = int(metrics["reference_plane_count"])
    pred_n = int(metrics["prediction_plane_count"])
    gross_topology = ref_n >= 2 and (pred_n / ref_n < 0.75 or pred_n / ref_n > 1.5)
    o = thresholds["g3_o"]
    x = thresholds["g3_x"]
    reasons = []
    if gross_topology:
        reasons.append(f"gross_plane_count_mismatch_{ref_n}_to_{pred_n}")
    if metrics["area_completeness"] < x["area_completeness_below"]:
        reasons.append("area_completeness_low")
    if metrics["area_correctness"] < x["area_correctness_below"]:
        reasons.append("area_correctness_low")
    if metrics["area_quality"] < x["area_quality_below"]:
        reasons.append("area_quality_low")
    if reasons:
        return "X_CANDIDATE", reasons
    if (
        metrics["area_completeness"] >= o["area_completeness_min"]
        and metrics["area_correctness"] >= o["area_correctness_min"]
        and metrics["area_quality"] >= o["area_quality_min"]
    ):
        return "O_CANDIDATE", ["development_thresholds_met"]
    return "REVIEW", ["ambiguous_zone"]


def read_ply_xyz_class(path: Path) -> tuple[np.ndarray, np.ndarray]:
    payload = path.read_bytes()
    marker = b"end_header\n"
    offset = payload.find(marker)
    if offset < 0:
        raise RuntimeError(f"PLY header terminator missing: {path}")
    header = payload[: offset + len(marker)].decode("ascii")
    if "format binary_little_endian 1.0" not in header:
        raise RuntimeError(f"unsupported PLY format: {path}")
    count_line = next(line for line in header.splitlines() if line.startswith("element vertex "))
    count = int(count_line.split()[-1])
    dtype = np.dtype([("x", "<f4"), ("y", "<f4"), ("z", "<f4"), ("red", "u1"), ("green", "u1"), ("blue", "u1"), ("classification", "u1")])
    data = np.frombuffer(payload, dtype=dtype, count=count, offset=offset + len(marker))
    xyz = np.column_stack((data["x"], data["y"], data["z"])).astype(np.float64)
    return xyz, np.asarray(data["classification"], dtype=np.uint8)


def roof_reference_cells(path: Path, cell_size: float, evaluation_polygon: Any) -> np.ndarray:
    xyz, classification = read_ply_xyz_class(path)
    xyz = xyz[classification == 6]
    if len(xyz):
        xyz = xyz[contains_xy(evaluation_polygon, xyz[:, 0], xyz[:, 1])]
    if len(xyz) == 0:
        return np.empty((0, 3), dtype=np.float64)
    cells = np.floor(xyz[:, :2] / cell_size).astype(np.int64)
    order = np.lexsort((xyz[:, 2], cells[:, 1], cells[:, 0]))
    cells = cells[order]
    xyz = xyz[order]
    boundaries = np.flatnonzero(np.any(cells[1:] != cells[:-1], axis=1)) + 1
    result = []
    for indices in np.split(np.arange(len(xyz)), boundaries):
        points = xyz[indices]
        result.append([float(np.median(points[:, 0])), float(np.median(points[:, 1])), float(np.percentile(points[:, 2], 90))])
    return np.asarray(result, dtype=np.float64)


def top_surface_z(triangles: np.ndarray, xy: np.ndarray, *, roof_only: bool = True) -> np.ndarray:
    result = np.full(len(xy), np.nan, dtype=np.float64)
    surface_triangles = roof_triangles(triangles) if roof_only else triangles
    for triangle in surface_triangles:
        p0, p1, p2 = triangle
        denominator = (p1[1] - p2[1]) * (p0[0] - p2[0]) + (p2[0] - p1[0]) * (p0[1] - p2[1])
        if abs(denominator) <= 1e-10:
            continue
        bbox = (xy[:, 0] >= triangle[:, 0].min() - 1e-9) & (xy[:, 0] <= triangle[:, 0].max() + 1e-9) & (xy[:, 1] >= triangle[:, 1].min() - 1e-9) & (xy[:, 1] <= triangle[:, 1].max() + 1e-9)
        indices = np.flatnonzero(bbox)
        if not len(indices):
            continue
        q = xy[indices]
        a = ((p1[1] - p2[1]) * (q[:, 0] - p2[0]) + (p2[0] - p1[0]) * (q[:, 1] - p2[1])) / denominator
        b = ((p2[1] - p0[1]) * (q[:, 0] - p2[0]) + (p0[0] - p2[0]) * (q[:, 1] - p2[1])) / denominator
        c = 1.0 - a - b
        inside = (a >= -1e-8) & (b >= -1e-8) & (c >= -1e-8)
        if not np.any(inside):
            continue
        selected = indices[inside]
        z = a[inside] * p0[2] + b[inside] * p1[2] + c[inside] * p2[2]
        current = result[selected]
        result[selected] = np.where(np.isnan(current), z, np.maximum(current, z))
    return result


def g4_metrics(reference_cells: np.ndarray, prediction: np.ndarray) -> dict[str, Any]:
    if len(reference_cells) == 0 or len(prediction) == 0:
        return {"reference_cell_count": int(len(reference_cells)), "scored_cell_count": 0}
    predicted_z = top_surface_z(prediction, reference_cells[:, :2])
    finite = np.isfinite(predicted_z)
    errors = predicted_z[finite] - reference_cells[finite, 2]
    return {
        "reference_cell_count": int(len(reference_cells)),
        "scored_cell_count": int(np.count_nonzero(finite)),
        "coverage": float(np.mean(finite)),
        "rmse_z_m": float(np.sqrt(np.mean(errors**2))) if len(errors) else None,
        "p95_abs_z_m": float(np.percentile(np.abs(errors), 95)) if len(errors) else None,
        "median_bias_z_m": float(np.median(errors)) if len(errors) else None,
    }


def classify_g4(metrics: dict[str, Any], thresholds: dict[str, Any], minimum_cells: int) -> tuple[str, list[str]]:
    if int(metrics.get("reference_cell_count", 0)) < minimum_cells:
        return "NOT_ASSESSED", ["insufficient_current_uas_reference_cells"]
    required = ("coverage", "rmse_z_m", "p95_abs_z_m", "median_bias_z_m")
    if any(metrics.get(key) is None for key in required):
        return "NOT_ASSESSED", ["prediction_surface_not_measurable"]
    o = thresholds["g4_o"]
    x = thresholds["g4_x"]
    reasons = []
    if metrics["coverage"] < x["coverage_below"]:
        reasons.append("coverage_low")
    if metrics["rmse_z_m"] > x["rmse_z_m_above"]:
        reasons.append("rmse_z_high")
    if metrics["p95_abs_z_m"] > x["p95_abs_z_m_above"]:
        reasons.append("p95_abs_z_high")
    if abs(metrics["median_bias_z_m"]) > x["abs_median_bias_z_m_above"]:
        reasons.append("median_bias_high")
    if reasons:
        return "X_CANDIDATE", reasons
    if (
        metrics["coverage"] >= o["coverage_min"]
        and metrics["rmse_z_m"] <= o["rmse_z_m_max"]
        and metrics["p95_abs_z_m"] <= o["p95_abs_z_m_max"]
        and abs(metrics["median_bias_z_m"]) <= o["abs_median_bias_z_m_max"]
    ):
        return "O_CANDIDATE", ["development_thresholds_met"]
    return "REVIEW", ["ambiguous_zone"]


def condition_spec(building: dict[str, Any], condition: str) -> dict[str, Any]:
    if condition == "E1":
        return building["lidar"]
    if condition == "E2":
        return building["mvs"]
    return building["conditions"][condition]


def label(value: str | None) -> str:
    return {"O_CANDIDATE": "O*", "X_CANDIDATE": "X*", "REVIEW": "R*", "NOT_ASSESSED": "NA"}.get(value or "", "?")


def patch_app(source: str) -> str:
    old = """function compactGateSummary(spec, hasRoofer) {
  if (spec.asset_role) return compactReason(spec, hasRoofer);
  const g0 = hasRoofer && Number(spec.roofer_triangles || 0) > 0 ? 'O' : 'X';
  let g1 = '?';
  let g2 = '?';
  if (g0 === 'X') {
    g1 = '–';
    g2 = '–';
  } else if (spec.technical_status === 'TECHNICAL_VALID_LOD22') {
    g1 = 'O';
    g2 = 'O';
  } else if (spec.metrics && typeof spec.metrics.val3dity_valid === 'boolean') {
    g1 = 'O';
    g2 = spec.metrics.val3dity_valid ? 'O' : 'X';
  }
  return `G0 ${g0} · G1 ${g1} · G2 ${g2} · G3 ? · G4 ? · ${compactReason(spec, hasRoofer)}`;
}"""
    new = """function developmentLabel(value) {
  return value === 'O_CANDIDATE' ? 'O*' : value === 'X_CANDIDATE' ? 'X*' : value === 'REVIEW' ? 'R*' : value === 'NOT_ASSESSED' ? 'NA' : '?';
}

function metricNumber(value, digits = 2) {
  return Number.isFinite(Number(value)) ? Number(value).toFixed(digits) : '-';
}

function compactGateSummary(spec, hasRoofer) {
  if (spec.asset_role) return compactReason(spec, hasRoofer);
  const dev = spec.development_g3_g4 || {};
  if (dev.assessment_status === 'NOT_ASSESSED_AOI') return 'AOI 밖 · G3 NA · G4 NA · 조건 실패로 집계 안 함';
  const g0 = hasRoofer && Number(spec.roofer_triangles || 0) > 0 ? 'O' : 'X';
  let g1 = '?';
  let g2 = '?';
  if (g0 === 'X') {
    g1 = '–';
    g2 = '–';
  } else if (spec.technical_status === 'TECHNICAL_VALID_LOD22') {
    g1 = 'O';
    g2 = 'O';
  } else if (spec.metrics && typeof spec.metrics.val3dity_valid === 'boolean') {
    g1 = 'O';
    g2 = spec.metrics.val3dity_valid ? 'O' : 'X';
  }
  const g3 = dev.g3 || {};
  const g4 = dev.g4 || {};
  const structural = `C${metricNumber(g3.area_completeness)}/P${metricNumber(g3.area_correctness)}/Q${metricNumber(g3.area_quality)}`;
  const geometric = `cov${metricNumber(g4.coverage)}/z${metricNumber(g4.rmse_z_m)}m/p95${metricNumber(g4.p95_abs_z_m)}m`;
  return `G0 ${g0} · G1 ${g1} · G2 ${g2} · G3 ${developmentLabel(dev.g3_candidate)} ${structural} · G4 ${developmentLabel(dev.g4_candidate)} ${geometric}`;
}"""
    if old not in source:
        raise RuntimeError("v14 compactGateSummary block drifted")
    source = source.replace(old, new)
    source = source.replace("if (spec.automatic_candidate) this.stats.classList.add(spec.automatic_candidate === 'AUTO_O_CANDIDATE' ? 'auto-o' : 'auto-x');", "if (spec.development_g3_g4 && spec.development_g3_g4.overall_candidate) { const value = spec.development_g3_g4.overall_candidate; this.stats.classList.add(value === 'O_CANDIDATE' ? 'auto-o' : value === 'X_CANDIDATE' ? 'auto-x' : 'auto-review'); } else if (spec.automatic_candidate) this.stats.classList.add(spec.automatic_candidate === 'AUTO_O_CANDIDATE' ? 'auto-o' : 'auto-x');")
    source = source.replace("this.stats.classList.remove('auto-o', 'auto-x');", "this.stats.classList.remove('auto-o', 'auto-x', 'auto-review');")
    source = source.replace("const candidate = spec.automatic_candidate === 'AUTO_O_CANDIDATE' ? '자동 O' : '자동 X';\n    return `${id} <strong>${candidate}</strong>`;", "const dev = spec.development_g3_g4 || {}; const candidate = dev.assessment_status === 'NOT_ASSESSED_AOI' ? 'AOI NA' : `${developmentLabel(dev.g3_candidate)}/${developmentLabel(dev.g4_candidate)}`;\n    return `${id} <strong>${candidate}</strong>`;")
    return source


def patch_index(source: str) -> str:
    source = source.replace("G3/G4는 threshold 미동결이라 <strong>?</strong>이며", "G3/G4는 <strong>development v0 후보(O*/R*/X*)</strong>이며")
    source = source.replace("자동 후보가 공식 PASS", "별표 후보가 공식 PASS")
    source = source.replace(".panel-stats.auto-x::before { content:'자동 후보 X';", ".panel-stats.auto-review::before { content:'검토'; color:#1a1300; background:var(--warn); }\n  .panel-stats.auto-x::before { content:'개발 후보 X';")
    source = source.replace(".panel-stats.auto-o::before { content:'자동 후보 O';", ".panel-stats.auto-o::before { content:'개발 후보 O';")
    source = source.replace("app.js?v=e1e6-roofer-ox-v14", "app.js?v=e1e6-roofer-ox-v16-g3g4-dev0p1")
    return source


def build(config_path: Path, artifact_root: Path) -> dict[str, Any]:
    config = load_config(config_path)
    source_spec = config["source_viewer"]
    source_root = artifact_root / source_spec["relative_root"]
    source_manifest_path = source_root / source_spec["viewer_manifest_path"]
    source_receipt_path = source_root / source_spec["receipt_path"]
    exact_file(source_manifest_path, {"bytes": source_spec["viewer_manifest_bytes"], "sha256": source_spec["viewer_manifest_sha256"]})
    exact_file(source_receipt_path, {"bytes": source_spec["receipt_bytes"], "sha256": source_spec["receipt_sha256"]})
    footprint_path = artifact_root / config["shared_footprints"]["path"]
    exact_file(footprint_path, config["shared_footprints"])
    source_manifest = json.loads(source_manifest_path.read_text(encoding="utf-8"))
    source_receipt = json.loads(source_receipt_path.read_text(encoding="utf-8"))
    if len(source_manifest.get("buildings", [])) != 199 or source_manifest.get("scientific_verdict", "missing") is not None:
        raise RuntimeError("v14 viewer population/verdict drifted")
    footprint_payload = json.loads(footprint_path.read_text(encoding="utf-8"))
    footprints = {str(feature["properties"][config["shared_footprints"]["id_field"]]): shape(feature["geometry"]) for feature in footprint_payload["features"]}
    if len(footprints) != 199:
        raise RuntimeError("shared footprint population drifted")
    target_aoi = box(*map(float, config["roofer_target_aoi_epsg25832"]))
    output = artifact_root / config["output_relative_root"]
    partial = output.with_name(output.name + ".partial")
    if output.exists() or partial.exists():
        raise RuntimeError("fresh add-once development viewer namespace required")
    shutil.copytree(source_root, partial, copy_function=os.link)
    for name in ("viewer_manifest.json", "web_receipt_v1.json", "app.js", "index.html", "README.md"):
        (partial / name).unlink()

    criterion = config["structure_reference"]
    geometry = config["geometry_reference"]
    rows = []
    counts: dict[str, Counter[str]] = {condition: Counter() for condition in config["conditions"]}
    for building in source_manifest["buildings"]:
        stable_id = building["stable_id"]
        footprint = footprints[stable_id]
        outside_aoi = not target_aoi.covers(footprint.centroid)
        origin = np.asarray(source_manifest["scene_local_origin_xyz"], dtype=np.float64)
        footprint_local = translate(footprint, xoff=-origin[0], yoff=-origin[1])
        inset = footprint_local.buffer(-float(geometry["evaluation_inset_m"]))
        evaluation_polygon = inset if not inset.is_empty else footprint_local
        e1_spec = building["lidar"]
        e1_roofer_path = source_root / e1_spec["roofer"] if e1_spec.get("roofer") else None
        structure_reference = major_planes(
            cluster_roof_planes(parse_obj_triangles(e1_roofer_path), criterion["plane_angle_tolerance_deg"], criterion["plane_height_tolerance_m"]),
            criterion["minimum_plane_area_m2"],
        ) if e1_spec.get("technical_status") == "TECHNICAL_VALID_LOD22" else []
        uas_path = source_root / e1_spec["points"]
        reference_cells = roof_reference_cells(uas_path, geometry["cell_size_m"], evaluation_polygon) if e1_spec.get("point_count", 0) > 0 else np.empty((0, 3), dtype=np.float64)
        for condition in config["conditions"]:
            spec = condition_spec(building, condition)
            prediction_path = source_root / spec["roofer"] if spec.get("roofer") else None
            prediction_triangles = parse_obj_triangles(prediction_path)
            if outside_aoi and not len(prediction_triangles):
                development = {
                    "criterion_version": config["criterion_version"],
                    "assessment_status": "NOT_ASSESSED_AOI",
                    "g3_candidate": "NOT_ASSESSED",
                    "g4_candidate": "NOT_ASSESSED",
                    "overall_candidate": "NOT_ASSESSED",
                    "g3": {}, "g4": {},
                    "reason": "exact_footprint_centroid_outside_frozen_roofer_target_aoi",
                }
            elif not len(prediction_triangles):
                development = {
                    "criterion_version": config["criterion_version"],
                    "assessment_status": "ASSESSED_OUTPUT_MISSING",
                    "g3_candidate": "X_CANDIDATE",
                    "g4_candidate": "X_CANDIDATE",
                    "overall_candidate": "X_CANDIDATE",
                    "g3": {}, "g4": {},
                    "reason": "roofer_lod2_output_missing_inside_target_aoi",
                }
            else:
                prediction_planes = major_planes(
                    cluster_roof_planes(prediction_triangles, criterion["plane_angle_tolerance_deg"], criterion["plane_height_tolerance_m"]),
                    criterion["minimum_plane_area_m2"],
                )
                g3 = g3_metrics(structure_reference, prediction_planes, criterion["matching_overlap_fraction"])
                g3_candidate, g3_reasons = classify_g3(g3, config["thresholds"])
                g4 = g4_metrics(reference_cells, prediction_triangles)
                g4_candidate, g4_reasons = classify_g4(g4, config["thresholds"], geometry["minimum_reference_cells"])
                candidates = {g3_candidate, g4_candidate}
                if "X_CANDIDATE" in candidates:
                    overall = "X_CANDIDATE"
                elif "NOT_ASSESSED" in candidates:
                    overall = "NOT_ASSESSED"
                elif "REVIEW" in candidates:
                    overall = "REVIEW"
                else:
                    overall = "O_CANDIDATE"
                development = {
                    "criterion_version": config["criterion_version"],
                    "assessment_status": "ASSESSED_DEVELOPMENT_PROXY" if overall != "NOT_ASSESSED" else "NOT_ASSESSED_REFERENCE_GAP",
                    "g3_candidate": g3_candidate,
                    "g4_candidate": g4_candidate,
                    "overall_candidate": overall,
                    "g3": g3, "g4": g4,
                    "g3_reasons": g3_reasons, "g4_reasons": g4_reasons,
                    "structure_reference_role": config["structure_reference"]["role"],
                    "geometry_reference_role": config["geometry_reference"]["role"],
                    "reference_independence_note": "E1 is self-reference; E2-E6 use method-derived E1 structure proxy and current-UAS viewer point proxy",
                }
            spec["development_g3_g4"] = development
            counts[condition][development["overall_candidate"]] += 1
            rows.append({
                "population_index": building["population_index"], "stable_id": stable_id, "condition_id": condition,
                "assessment_status": development["assessment_status"], "g3_candidate": development["g3_candidate"],
                "g4_candidate": development["g4_candidate"], "overall_candidate": development["overall_candidate"],
                **{f"g3_{key}": value for key, value in development.get("g3", {}).items()},
                **{f"g4_{key}": value for key, value in development.get("g4", {}).items()},
                "reason": development.get("reason", ""),
            })

    source_manifest.update({
        "task_id": config["task_id"],
        "status": "READY_FOR_DEVELOPMENT_G3_G4_REVIEW",
        "development_criterion": {key: config[key] for key in ("criterion_version", "structure_reference", "geometry_reference", "thresholds")},
        "official_PASS_usable": None,
        "scientific_verdict": None,
    })
    write_new(partial / "viewer_manifest.json", canonical_bytes(source_manifest))
    app = patch_app((source_root / "app.js").read_text(encoding="utf-8"))
    index = patch_index((source_root / "index.html").read_text(encoding="utf-8"))
    write_new(partial / "app.js", app.encode("utf-8"))
    write_new(partial / "index.html", index.encode("utf-8"))
    csv_path = partial / "development_g3_g4_building_condition_v0.csv"
    fields = list(rows[0])
    with csv_path.open("x", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    summary = {
        "schema": "jointbuildgs.p2.e1_e6_roofer_development_g3_g4.summary.v0",
        "task_id": config["task_id"],
        "criterion_version": config["criterion_version"],
        "building_count": 199,
        "row_count": len(rows),
        "condition_counts": {condition: dict(sorted(counter.items())) for condition, counter in counts.items()},
        "official_PASS_usable": None,
        "scientific_verdict": None,
    }
    write_new(partial / "development_g3_g4_summary_v0.json", canonical_bytes(summary))
    write_new(partial / "README.md", ("# E1-E6 Roofer G3/G4 development viewer v0.1\n\nThis additive v16 viewer reuses the exact v14 display assets and adds non-frozen O*/REVIEW*/X* development diagnostics. G3 uses E1 current-UAS Roofer as a method-derived structure proxy. G4 uses class-6 current-UAS viewer points clipped to the exact shared footprint with a 0.5 m evaluation inset. AOI/reference gaps remain NOT_ASSESSED. No Roofer, training, extraction, or source-artifact rewrite was performed. official_PASS_usable and scientific_verdict remain null.\n").encode("utf-8"))
    receipt = {
        "schema": "jointbuildgs.p2.e1_e6_roofer_development_g3_g4.receipt.v0",
        "task_id": config["task_id"],
        "status": "READY_FOR_DEVELOPMENT_G3_G4_REVIEW",
        "source_viewer_manifest": file_record(source_manifest_path, artifact_root),
        "source_viewer_receipt": file_record(source_receipt_path, artifact_root),
        "reuse_method": "SAME_FILESYSTEM_HARDLINK_EXACT_V14_ASSETS",
        "roofer_invocations": 0, "training_invocations": 0,
        "viewer_manifest": file_record(partial / "viewer_manifest.json", partial),
        "application": {name: file_record(partial / name, partial) for name in ("app.js", "index.html")},
        "metrics_csv": file_record(csv_path, partial),
        "summary": file_record(partial / "development_g3_g4_summary_v0.json", partial),
        "official_PASS_usable": None,
        "scientific_verdict": None,
    }
    write_new(partial / "web_receipt_v1.json", canonical_bytes(receipt))
    os.rename(partial, output)
    return receipt


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=CONFIG)
    parser.add_argument("--artifact-root", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(build(args.config, args.artifact_root), ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
