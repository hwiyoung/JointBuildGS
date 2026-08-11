#!/usr/bin/env python3
"""Build the additive E1-E6 reference-based binary Roofer O/X viewer.

The builder reads sealed Roofer/CityJSON outputs and the v16 display assets. It
runs only evaluation validation and metric computation. It never trains a model,
extracts GS geometry, or invokes Roofer. O50 is the primary development setting;
O60/O70/O80 are sensitivity settings. REVIEW is not an output, and NA is used
only when the evaluation reference itself is absent.
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
import subprocess
from typing import Any
import xml.etree.ElementTree as ET

import numpy as np
from shapely import contains_xy
from shapely.affinity import translate
from shapely.geometry import shape
from shapely.geometry import Polygon
from shapely.ops import triangulate, unary_union

from scripts.p2.e1_e6_roofer_ox_review_v1.add_development_g3_g4_v0 import (
    cluster_roof_planes,
    g4_metrics,
    major_planes,
    parse_obj_triangles,
    roof_reference_cells,
    top_surface_z,
)
from scripts.p2.c1_c2_shared_footprint_199_v1.run import (
    canonical_json_bytes,
    exact_file,
    file_record,
    write_new,
)


REPO = Path(__file__).resolve().parents[3]
CONFIG = REPO / "configs/p2/e1_e6_roofer_ox_review_v1/reference_auto_ox_v1.json"
CONDITIONS = ("E1", "E2", "E3", "E4", "E5", "E6")
SENSITIVITY = ("O50", "O60", "O70", "O80")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_config(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if value.get("schema") != "jointbuildgs.p2.e1_e6_roofer_reference_auto_ox.v1":
        raise RuntimeError("reference auto O/X schema drifted")
    if value.get("status") != "USER_APPROVED_FOR_EXECUTION":
        raise RuntimeError("reference auto O/X build is not approved")
    if value.get("primary_threshold") != "O50":
        raise RuntimeError("O50 must remain the primary development threshold")
    if value.get("classification_labels") != ["O", "X", "NA"]:
        raise RuntimeError("classification labels drifted")
    if value.get("review_is_outcome") is not False:
        raise RuntimeError("REVIEW must not be an outcome")
    if value.get("official_PASS_usable", "missing") is not None:
        raise RuntimeError("official_PASS_usable must remain null")
    if value.get("scientific_verdict", "missing") is not None:
        raise RuntimeError("scientific_verdict must remain null")
    return value


def condition_spec(building: dict[str, Any], condition: str) -> dict[str, Any]:
    if condition == "E1":
        return building["lidar"]
    if condition == "E2":
        return building["mvs"]
    return building["conditions"][condition]


def object_family(cityjson: dict[str, Any], stable_id: str) -> list[dict[str, Any]]:
    objects = cityjson.get("CityObjects", {})
    result: list[dict[str, Any]] = []
    pending = [stable_id]
    seen: set[str] = set()
    while pending:
        object_id = pending.pop()
        if object_id in seen:
            continue
        seen.add(object_id)
        obj = objects.get(object_id)
        if obj is None:
            continue
        result.append(obj)
        pending.extend(str(value) for value in obj.get("children", []))
    if result:
        return result
    # Roofer sometimes serializes parts with the stable ID as a prefix while the
    # parent object is absent. Keep this deterministic and ID-bound.
    return [obj for object_id, obj in objects.items() if object_id.startswith(f"{stable_id}-")]


def cityjson_g0_g1(cityjson: dict[str, Any], stable_id: str) -> tuple[bool, bool, list[str]]:
    family = object_family(cityjson, stable_id)
    lod2_geometries = []
    semantic_types: set[str] = set()
    for obj in family:
        for geometry in obj.get("geometry", []):
            if str(geometry.get("lod")) not in {"2", "2.0", "2.1", "2.2"}:
                continue
            if not geometry.get("boundaries"):
                continue
            lod2_geometries.append(geometry)
            semantics = geometry.get("semantics") or {}
            semantic_types.update(
                str(surface.get("type"))
                for surface in semantics.get("surfaces", [])
                if isinstance(surface, dict) and surface.get("type")
            )
    g0 = bool(lod2_geometries)
    required = {"RoofSurface", "WallSurface", "GroundSurface"}
    g1 = g0 and required.issubset(semantic_types)
    reasons = []
    if not g0:
        reasons.append("G0_OUTPUT_MISSING")
    elif not g1:
        reasons.append("G1_CITYJSON_CONTRACT_FAILED")
    return g0, g1, reasons


def val3dity_feature_map(report: dict[str, Any]) -> dict[str, tuple[bool, list[str]]]:
    result = {}
    for feature in report.get("features", []):
        errors = [str(value.get("description") or value.get("code")) for value in feature.get("errors", [])]
        result[str(feature["id"])] = (bool(feature.get("validity")), errors)
    return result


def feature_validity(mapping: dict[str, tuple[bool, list[str]]], stable_id: str, g0: bool) -> tuple[bool, list[str]]:
    if not g0:
        return False, []
    if stable_id in mapping:
        return mapping[stable_id]
    candidates = [value for key, value in mapping.items() if key.startswith(f"{stable_id}-")]
    if not candidates:
        return False, ["FEATURE_NOT_REPORTED"]
    return all(value[0] for value in candidates), [item for value in candidates for item in value[1]]


def plane_match_metrics(
    reference: list[dict[str, Any]],
    prediction: list[dict[str, Any]],
    overlap_threshold: float,
    normal_tolerance_deg: float,
    height_tolerance_m: float,
) -> dict[str, Any]:
    base = {
        "reference_plane_count": len(reference),
        "prediction_plane_count": len(prediction),
        "match_count": 0,
        "area_completeness": None,
        "area_correctness": None,
        "area_quality": None,
        "plane_area_recall": None,
        "plane_area_precision": None,
        "matched_normal_angle_median_deg": None,
        "matched_height_delta_median_m": None,
    }
    if not reference or not prediction:
        return base
    reference_union = unary_union([value["polygon"] for value in reference])
    prediction_union = unary_union([value["polygon"] for value in prediction])
    support_overlap = float(reference_union.intersection(prediction_union).area)
    support_union = float(reference_union.union(prediction_union).area)
    edges = []
    for ref_index, ref in enumerate(reference):
        for pred_index, pred in enumerate(prediction):
            overlap = float(ref["polygon"].intersection(pred["polygon"]).area)
            if overlap <= 0:
                continue
            ref_fraction = overlap / ref["area_m2"]
            pred_fraction = overlap / pred["area_m2"]
            dot = float(np.clip(np.dot(ref["normal"], pred["normal"]), -1.0, 1.0))
            angle = math.degrees(math.acos(abs(dot)))
            center = ref["polygon"].intersection(pred["polygon"]).representative_point()
            ref_a, ref_b, ref_c = ref["plane_coefficients"]
            pred_a, pred_b, pred_c = pred["plane_coefficients"]
            ref_z = ref_a * center.x + ref_b * center.y + ref_c
            pred_z = pred_a * center.x + pred_b * center.y + pred_c
            height = abs(float(ref_z - pred_z))
            if ref_fraction < overlap_threshold or pred_fraction < overlap_threshold:
                continue
            if angle > normal_tolerance_deg or height > height_tolerance_m:
                continue
            union = ref["area_m2"] + pred["area_m2"] - overlap
            edges.append((overlap / union if union else 0.0, overlap, angle, height, ref_index, pred_index))
    used_ref: set[int] = set()
    used_pred: set[int] = set()
    matches = []
    for edge in sorted(edges, reverse=True):
        ref_index, pred_index = edge[4], edge[5]
        if ref_index in used_ref or pred_index in used_pred:
            continue
        used_ref.add(ref_index)
        used_pred.add(pred_index)
        matches.append(edge)
    ref_area = sum(value["area_m2"] for value in reference)
    pred_area = sum(value["area_m2"] for value in prediction)
    matched_ref_area = sum(reference[value[4]]["area_m2"] for value in matches)
    matched_pred_area = sum(prediction[value[5]]["area_m2"] for value in matches)
    return {
        **base,
        "match_count": len(matches),
        "area_completeness": support_overlap / reference_union.area if reference_union.area else None,
        "area_correctness": support_overlap / prediction_union.area if prediction_union.area else None,
        "area_quality": support_overlap / support_union if support_union else None,
        "plane_area_recall": matched_ref_area / ref_area if ref_area else None,
        "plane_area_precision": matched_pred_area / pred_area if pred_area else None,
        "matched_normal_angle_median_deg": float(np.median([value[2] for value in matches])) if matches else None,
        "matched_height_delta_median_m": float(np.median([value[3] for value in matches])) if matches else None,
    }


def reference_grid_from_lod2(triangles: np.ndarray, polygon: Any, cell_size: float) -> np.ndarray:
    if len(triangles) == 0 or polygon.is_empty:
        return np.empty((0, 3), dtype=np.float64)
    minx, miny, maxx, maxy = polygon.bounds
    xs = np.arange(minx + cell_size / 2.0, maxx, cell_size)
    ys = np.arange(miny + cell_size / 2.0, maxy, cell_size)
    if len(xs) and len(ys):
        xx, yy = np.meshgrid(xs, ys)
        xy = np.column_stack((xx.ravel(), yy.ravel()))
        xy = xy[contains_xy(polygon, xy[:, 0], xy[:, 1])]
        if len(xy):
            z = top_surface_z(triangles, xy, roof_only=False)
            finite = np.isfinite(z)
            if np.any(finite):
                return np.column_stack((xy[finite], z[finite]))
    # Tiny or narrow footprints may contain no regular cell centre. The
    # reference still exists, so fall back deterministically to roof-triangle
    # representative points rather than mislabelling the building as NA.
    xy = triangles[:, :, :2].mean(axis=1)
    inside = contains_xy(polygon, xy[:, 0], xy[:, 1])
    candidates = xy[inside] if np.any(inside) else xy
    z = top_surface_z(triangles, candidates, roof_only=False)
    finite = np.isfinite(z)
    return np.column_stack((candidates[finite], z[finite]))


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def gml_id(element: Any) -> str | None:
    for key, value in element.attrib.items():
        if local_name(key) == "id":
            return str(value)
    return None


def fitted_surface(points: np.ndarray, surface_id: str) -> dict[str, Any] | None:
    if len(points) < 3:
        return None
    if np.allclose(points[0], points[-1]):
        points = points[:-1]
    if len(points) < 3:
        return None
    polygon = Polygon(points[:, :2])
    if not polygon.is_valid:
        polygon = polygon.buffer(0)
    if polygon.is_empty or polygon.area <= 1e-6:
        return None
    design = np.column_stack((points[:, 0], points[:, 1], np.ones(len(points))))
    coefficients, *_ = np.linalg.lstsq(design, points[:, 2], rcond=None)
    a, b, c = map(float, coefficients)
    normal = np.asarray([-a, -b, 1.0], dtype=np.float64)
    normal /= np.linalg.norm(normal)
    center = polygon.centroid
    z_center = a * center.x + b * center.y + c
    return {
        "surface_id": surface_id,
        "polygon": polygon,
        "area_m2": float(polygon.area),
        "normal": normal,
        "z_center": float(z_center),
        "plane_coefficients": (a, b, c),
    }


def parse_reference_roofs(
    paths: list[Path],
    stable_ids: set[str],
    origin: np.ndarray,
    z_shift_m: float,
) -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = {stable_id: [] for stable_id in stable_ids}
    for path in paths:
        for _, element in ET.iterparse(path, events=("end",)):
            if local_name(element.tag) != "Building":
                continue
            stable_id = gml_id(element)
            if stable_id in stable_ids:
                surfaces = []
                for roof in element.iter():
                    if local_name(roof.tag) != "RoofSurface":
                        continue
                    surface_id = gml_id(roof) or f"{stable_id}_roof_{len(surfaces)}"
                    for polygon in roof.iter():
                        if local_name(polygon.tag) != "Polygon":
                            continue
                        exterior = next((child for child in polygon if local_name(child.tag) == "exterior"), None)
                        if exterior is None:
                            continue
                        pos_list = next((child for child in exterior.iter() if local_name(child.tag) == "posList"), None)
                        if pos_list is None or not pos_list.text:
                            continue
                        values = np.fromstring(pos_list.text, sep=" ", dtype=np.float64)
                        if values.size % 3:
                            raise RuntimeError(f"{stable_id}: malformed RoofSurface posList")
                        points = values.reshape(-1, 3)
                        points[:, :2] -= origin[:2]
                        points[:, 2] = points[:, 2] - origin[2] + z_shift_m
                        surface = fitted_surface(points, surface_id)
                        if surface is not None:
                            surfaces.append(surface)
                result[stable_id].extend(surfaces)
            element.clear()
    return result


def reference_triangles(surfaces: list[dict[str, Any]]) -> np.ndarray:
    output = []
    for surface in surfaces:
        a, b, c = surface["plane_coefficients"]
        for triangle in triangulate(surface["polygon"]):
            if not surface["polygon"].covers(triangle.representative_point()):
                continue
            xy = np.asarray(triangle.exterior.coords[:3], dtype=np.float64)
            z = a * xy[:, 0] + b * xy[:, 1] + c
            output.append(np.column_stack((xy, z)))
    return np.asarray(output, dtype=np.float64).reshape(-1, 3, 3)


def obj_bytes(name: str, triangles: np.ndarray) -> bytes:
    lines = [f"# {name}", f"o {name}", f"g {name}"]
    index = 1
    for triangle in triangles:
        for vertex in triangle:
            lines.append(f"v {vertex[0]:.6f} {vertex[1]:.6f} {vertex[2]:.6f}")
        lines.append(f"f {index} {index + 1} {index + 2}")
        index += 3
    return ("\n".join(lines) + "\n").encode("ascii")


def classify_binary(
    *,
    g0: bool,
    g1: bool,
    g2: bool,
    g3: dict[str, Any],
    g4: dict[str, Any],
    reference_available: bool,
    thresholds: dict[str, Any],
) -> dict[str, Any]:
    if not g0:
        return {"verdict": "X", "gates": {"G0": "X", "G1": "-", "G2": "-", "G3": "-", "G4": "-"}, "failure_reasons": ["G0_OUTPUT_MISSING"], "g3": g3, "g4": g4}
    if not reference_available:
        return {"verdict": "NA", "gates": {"G0": "O", "G1": "O" if g1 else "X", "G2": "O" if g2 else "X", "G3": "NA", "G4": "NA"}, "failure_reasons": ["G3_REFERENCE_MISSING", "G4_REFERENCE_MISSING"], "g3": g3, "g4": g4}
    reasons = []
    if not g1:
        reasons.append("G1_CITYJSON_CONTRACT_FAILED")
    if not g2:
        reasons.append("G2_VAL3DITY_FAILED")
    required_g3 = ("area_completeness", "area_correctness", "area_quality", "plane_area_recall", "plane_area_precision")
    g3_values_present = all(g3.get(key) is not None for key in required_g3)
    g3_pass = g3_values_present
    if not g3_values_present:
        reasons.append("G3_REFERENCE_MISSING")
    else:
        if g3["area_completeness"] < thresholds["g3"]["area_completeness_min"]:
            reasons.append("G3_COMPLETENESS_LOW")
            g3_pass = False
        if g3["area_correctness"] < thresholds["g3"]["area_correctness_min"]:
            reasons.append("G3_CORRECTNESS_LOW")
            g3_pass = False
        if g3["area_quality"] < thresholds["g3"]["area_quality_min"]:
            reasons.append("G3_QUALITY_LOW")
            g3_pass = False
        if g3["plane_area_recall"] < thresholds["g3"]["plane_area_recall_min"]:
            reasons.append("G3_PLANE_RECALL_LOW")
            g3_pass = False
        if g3["plane_area_precision"] < thresholds["g3"]["plane_area_precision_min"]:
            reasons.append("G3_PLANE_PRECISION_LOW")
            g3_pass = False
        ref_count = int(g3.get("reference_plane_count", 0))
        pred_count = int(g3.get("prediction_plane_count", 0))
        count_ratio = pred_count / ref_count if ref_count else 0.0
        if count_ratio < thresholds["g3"]["prediction_reference_count_ratio_min"] or count_ratio > thresholds["g3"]["prediction_reference_count_ratio_max"]:
            reasons.append("G3_MAJOR_PLANE_MISMATCH")
            g3_pass = False
    required_g4 = ("coverage", "rmse_z_m", "p95_abs_z_m", "median_bias_z_m")
    g4_values_present = all(g4.get(key) is not None for key in required_g4)
    g4_pass = g4_values_present
    if not g4_values_present and int(g4.get("reference_cell_count", 0)) == 0:
        reasons.append("G4_REFERENCE_MISSING")
    elif not g4_values_present:
        reasons.append("G4_COVERAGE_LOW")
    else:
        if g4["coverage"] < thresholds["g4"]["coverage_min"]:
            reasons.append("G4_COVERAGE_LOW")
            g4_pass = False
        if g4["rmse_z_m"] > thresholds["g4"]["rmse_z_m_max"]:
            reasons.append("G4_RMSZ_HIGH")
            g4_pass = False
        if g4["p95_abs_z_m"] > thresholds["g4"]["p95_abs_z_m_max"]:
            reasons.append("G4_P95_HIGH")
            g4_pass = False
        if abs(g4["median_bias_z_m"]) > thresholds["g4"]["abs_median_bias_z_m_max"]:
            reasons.append("G4_BIAS_HIGH")
            g4_pass = False
    gates = {"G0": "O", "G1": "O" if g1 else "X", "G2": "O" if g2 else "X", "G3": "O" if g3_pass else "X", "G4": "O" if g4_pass else "X"}
    return {"verdict": "O" if all(value == "O" for value in gates.values()) else "X", "gates": gates, "failure_reasons": list(dict.fromkeys(reasons)), "g3": g3, "g4": g4}


def patch_index(source: str) -> str:
    source = source.replace(
        "<title>JointBuildGS E1-E6 Roofer O/X Review</title>",
        "<title>JointBuildGS E1-E6 Roofer reference auto O/X</title>",
    )
    marker = "</style>\n</head>"
    if marker not in source:
        raise RuntimeError("parent index style marker drifted")
    source = source.replace(marker, '</style>\n<link rel="stylesheet" href="./auto_ox.css?v=reference-v1">\n</head>', 1)
    marker = "</body>"
    if marker not in source:
        raise RuntimeError("parent body marker drifted")
    return source.replace(marker, '<script type="module" src="./auto_ox.js?v=reference-v1"></script>\n</body>', 1)


def run_val3dity(cityjson_path: Path, report_path: Path, log_path: Path) -> dict[str, Any]:
    completed = subprocess.run(
        ["val3dity", cityjson_path.as_posix(), "--report", report_path.as_posix()],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        check=False,
    )
    write_new(log_path, completed.stdout.encode("utf-8"))
    if not report_path.is_file():
        raise RuntimeError(f"val3dity did not create report for {cityjson_path}; exit={completed.returncode}")
    report = json.loads(report_path.read_text(encoding="utf-8"))
    if report.get("val3dity_version") != "2.6.0":
        raise RuntimeError("val3dity version drifted")
    return report


def build(config_path: Path, repo_root: Path, artifact_root: Path) -> dict[str, Any]:
    config = load_config(config_path)
    parent_spec = config["parent_viewer"]
    parent = artifact_root / parent_spec["relative_root"]
    for prefix, field in (("viewer_manifest", "viewer_manifest_path"), ("receipt", "receipt_path"), ("index", "index_path"), ("app", "app_path")):
        exact_file(parent / parent_spec[field], {"bytes": parent_spec[f"{prefix}_bytes"], "sha256": parent_spec[f"{prefix}_sha256"]})
    for source in config["cityjson_sources"].values():
        exact_file(artifact_root / source["path"], source)
    for source in config["lod2_reference_sources"]:
        exact_file(artifact_root / source["path"], source)
    footprint_spec = config["shared_footprints"]
    exact_file(artifact_root / footprint_spec["path"], footprint_spec)
    for source in config["application_sources"].values():
        exact_file(repo_root / source["path"], source)
    exact_file(repo_root / config["plane_cluster_source"]["path"], config["plane_cluster_source"])
    exact_file(repo_root / config["builder_source"]["path"], config["builder_source"])

    output = artifact_root / config["output_relative_root"]
    partial = output.with_name(output.name + ".partial")
    if output.exists() or partial.exists():
        raise RuntimeError("fresh add-once reference auto O/X namespace required")
    partial.mkdir(parents=True)
    replaced = {"viewer_manifest.json", "web_receipt_v1.json", "index.html", "README.md"}
    for source in parent.iterdir():
        if source.name in replaced:
            continue
        target = partial / source.name
        relative = os.path.relpath(source, start=partial)
        os.symlink(relative, target, target_is_directory=source.is_dir())

    viewer = json.loads((parent / parent_spec["viewer_manifest_path"]).read_text(encoding="utf-8"))
    if len(viewer.get("buildings", [])) != 199:
        raise RuntimeError("parent viewer population drifted")
    footprint_payload = json.loads((artifact_root / footprint_spec["path"]).read_text(encoding="utf-8"))
    footprints = {
        str(feature["properties"][footprint_spec["id_field"]]): shape(feature["geometry"])
        for feature in footprint_payload["features"]
    }
    if len(footprints) != 199:
        raise RuntimeError("shared footprint population drifted")
    stable_ids = {building["stable_id"] for building in viewer["buildings"]}
    reference_surfaces = parse_reference_roofs(
        [artifact_root / source["path"] for source in config["lod2_reference_sources"]],
        stable_ids,
        np.asarray(viewer["scene_local_origin_xyz"], dtype=np.float64),
        float(config["structure_metric"]["lod2_reference_z_shift_to_viewer_m"]),
    )
    missing_reference = sorted(stable_id for stable_id, surfaces in reference_surfaces.items() if not surfaces)
    if missing_reference:
        raise RuntimeError(f"stable-ID RoofSurface reference missing: {missing_reference[:10]}")
    cityjsons: dict[str, dict[str, Any]] = {}
    validity: dict[str, dict[str, tuple[bool, list[str]]]] = {}
    val_records = {}
    for condition in CONDITIONS:
        path = artifact_root / config["cityjson_sources"][condition]["path"]
        cityjsons[condition] = json.loads(path.read_text(encoding="utf-8"))
        report_path = partial / f"validation/{condition}_val3dity_report.json"
        log_path = partial / f"validation/{condition}_val3dity.log"
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report = run_val3dity(path, report_path, log_path)
        validity[condition] = val3dity_feature_map(report)
        val_records[condition] = {"report": file_record(report_path, partial), "log": file_record(log_path, partial)}

    origin = np.asarray(viewer["scene_local_origin_xyz"], dtype=np.float64)
    structure = config["structure_metric"]
    geometry = config["geometry_metric"]
    counts = {key: {condition: Counter() for condition in CONDITIONS} for key in SENSITIVITY}
    rows = []
    for building in viewer["buildings"]:
        stable_id = building["stable_id"]
        footprint_local = translate(footprints[stable_id], xoff=-origin[0], yoff=-origin[1])
        inset = footprint_local.buffer(-float(geometry["evaluation_inset_m"]))
        evaluation_polygon = inset if not inset.is_empty else footprint_local
        reference_planes = major_planes(reference_surfaces[stable_id], structure["minimum_plane_area_m2"])
        lod_triangles = reference_triangles(reference_surfaces[stable_id])
        reference_path = partial / f"reference_lod2/{int(building['population_index']):03d}_{stable_id}_RoofSurface.obj"
        write_new(reference_path, obj_bytes(f"{stable_id}_RoofSurface", lod_triangles))
        lod_spec = building["comparison_priors"]["PRIOR_LOD2"]
        lod_spec.update({
            "roofer": reference_path.relative_to(partial).as_posix(),
            "roofer_triangles": int(len(lod_triangles)),
            "diagnostic_summary": "stable-ID exact CityGML RoofSurface · evaluation-only",
            "selection_rule": "GML_BUILDING_ID_EXACT_ROOFSURFACE_ONLY",
        })
        uas_path = parent / building["lidar"]["points"]
        uas_cells = roof_reference_cells(uas_path, geometry["cell_size_m"], evaluation_polygon) if building["lidar"].get("point_count", 0) > 0 else np.empty((0, 3), dtype=np.float64)
        if len(uas_cells):
            geometry_cells = uas_cells
            geometry_role = "CURRENT_UAS_CLASS6_ANY_SUPPORT"
        else:
            geometry_cells = reference_grid_from_lod2(lod_triangles, evaluation_polygon, geometry["cell_size_m"])
            geometry_role = "LOD2_ROOFSURFACE_FALLBACK"
        reference_available = bool(reference_planes) and bool(len(geometry_cells))
        for condition in CONDITIONS:
            spec = condition_spec(building, condition)
            g0, g1, contract_reasons = cityjson_g0_g1(cityjsons[condition], stable_id)
            g2, val_errors = feature_validity(validity[condition], stable_id, g0)
            prediction_path = parent / spec["roofer"] if spec.get("roofer") else None
            prediction_triangles = parse_obj_triangles(prediction_path)
            prediction_planes = major_planes(
                cluster_roof_planes(prediction_triangles, structure["cluster_angle_deg"], structure["cluster_height_m"]),
                structure["minimum_plane_area_m2"],
            )
            g4 = g4_metrics(geometry_cells, prediction_triangles)
            if len(geometry_cells) and g4.get("coverage") is None:
                g4["coverage"] = 0.0
            sensitivity = {}
            for key in SENSITIVITY:
                overlap = float(key[1:]) / 100.0
                g3 = plane_match_metrics(reference_planes, prediction_planes, overlap, structure["normal_tolerance_deg"], structure["height_tolerance_m"])
                result = classify_binary(
                    g0=g0,
                    g1=g1,
                    g2=g2,
                    g3=g3,
                    g4=g4,
                    reference_available=reference_available,
                    thresholds=config["acceptance_thresholds"],
                )
                result.update({
                    "criterion": key,
                    "matching_overlap_fraction": overlap,
                    "geometry_reference_role": geometry_role,
                    "structure_reference_role": "EXISTING_LOD2_ROOFSURFACE_EVALUATION_ONLY",
                    "g1_reasons": contract_reasons,
                    "g2_errors": val_errors,
                })
                sensitivity[key] = result
                counts[key][condition][result["verdict"]] += 1
                rows.append({
                    "population_index": building["population_index"],
                    "stable_id": stable_id,
                    "condition_id": condition,
                    "criterion": key,
                    "verdict": result["verdict"],
                    **{f"{gate}_status": result["gates"][gate] for gate in ("G0", "G1", "G2", "G3", "G4")},
                    "failure_reasons": "|".join(result["failure_reasons"]),
                    "g3_reference_plane_count": g3.get("reference_plane_count"),
                    "g3_prediction_plane_count": g3.get("prediction_plane_count"),
                    "g3_area_completeness": g3.get("area_completeness"),
                    "g3_area_correctness": g3.get("area_correctness"),
                    "g3_area_quality": g3.get("area_quality"),
                    "g3_plane_area_recall": g3.get("plane_area_recall"),
                    "g3_plane_area_precision": g3.get("plane_area_precision"),
                    "g3_match_count": g3.get("match_count"),
                    "g3_matched_normal_angle_median_deg": g3.get("matched_normal_angle_median_deg"),
                    "g3_matched_height_delta_median_m": g3.get("matched_height_delta_median_m"),
                    "g4_reference_role": geometry_role,
                    "g4_reference_cell_count": g4.get("reference_cell_count"),
                    "g4_coverage": g4.get("coverage"),
                    "g4_rmse_z_m": g4.get("rmse_z_m"),
                    "g4_p95_abs_z_m": g4.get("p95_abs_z_m"),
                    "g4_median_bias_z_m": g4.get("median_bias_z_m"),
                })
            spec["reference_auto_ox"] = {"primary": sensitivity[config["primary_threshold"]], "sensitivity": sensitivity}

    viewer.update({
        "task_id": config["task_id"],
        "status": "READY_FOR_REFERENCE_BASED_BINARY_AUTO_OX_REVIEW",
        "reference_auto_ox_contract": {
            "criterion_version": config["criterion_version"],
            "primary_threshold": config["primary_threshold"],
            "sensitivity_thresholds": list(SENSITIVITY),
            "normal_tolerance_deg": structure["normal_tolerance_deg"],
            "height_tolerance_m": structure["height_tolerance_m"],
            "acceptance_thresholds": config["acceptance_thresholds"],
            "classification_labels": ["O", "X", "NA"],
            "review_is_outcome": False,
            "prediction_missing_policy": "X",
            "reference_missing_policy": "NA_ONLY_IF_STRUCTURE_AND_GEOMETRY_REFERENCE_UNAVAILABLE",
            "e6_interpretation": "SIMILARITY_DIAGNOSTIC_NOT_INDEPENDENT_PERFORMANCE",
        },
        "reference_auto_ox_counts": {
            key: {condition: dict(sorted(counter.items())) for condition, counter in per_condition.items()}
            for key, per_condition in counts.items()
        },
        "official_PASS_usable": None,
        "scientific_verdict": None,
    })
    write_new(partial / "viewer_manifest.json", canonical_json_bytes(viewer))
    write_new(partial / "index.html", patch_index((parent / parent_spec["index_path"]).read_text(encoding="utf-8")).encode("utf-8"))
    for name, key in (("auto_ox.css", "css"), ("auto_ox.js", "js")):
        shutil.copyfile(repo_root / config["application_sources"][key]["path"], partial / name)
    csv_path = partial / "reference_auto_ox_building_condition_v1.csv"
    with csv_path.open("x", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    summary = {
        "schema": "jointbuildgs.p2.e1_e6_roofer_reference_auto_ox.summary.v1",
        "task_id": config["task_id"],
        "building_count": len(viewer["buildings"]),
        "row_count": len(rows),
        "primary_threshold": config["primary_threshold"],
        "counts": viewer["reference_auto_ox_counts"],
        "official_PASS_usable": None,
        "scientific_verdict": None,
    }
    write_new(partial / "reference_auto_ox_summary_v1.json", canonical_json_bytes(summary))
    write_new(partial / "README.md", (
        "# E1-E6 Roofer reference auto O/X v1\n\n"
        "This additive viewer evaluates sealed E1-E6 Roofer outputs against exact stable-ID Existing LoD2 RoofSurface and current UAS class-6 support, with LoD2 geometry fallback when UAS reference support is empty. G3 separates roof-support overlap from one-to-one major-plane count, direction, and height agreement. O50 is primary; O60/O70/O80 are sensitivity settings. Missing prediction is X. NA is reserved for missing evaluation reference. REVIEW is not an outcome. E6 is similarity diagnostic only. No training, extraction, or Roofer invocation occurred. official_PASS_usable and scientific_verdict remain null.\n"
    ).encode("utf-8"))
    receipt = {
        "schema": "jointbuildgs.p2.e1_e6_roofer_reference_auto_ox.receipt.v1",
        "task_id": config["task_id"],
        "status": "READY_FOR_REFERENCE_BASED_BINARY_AUTO_OX_REVIEW",
        "parent_viewer_manifest": file_record(parent / parent_spec["viewer_manifest_path"], artifact_root),
        "parent_receipt": file_record(parent / parent_spec["receipt_path"], artifact_root),
        "cityjson_sources": {condition: file_record(artifact_root / source["path"], artifact_root) for condition, source in config["cityjson_sources"].items()},
        "lod2_reference_sources": [file_record(artifact_root / source["path"], artifact_root) for source in config["lod2_reference_sources"]],
        "shared_footprints": file_record(artifact_root / footprint_spec["path"], artifact_root),
        "val3dity": val_records,
        "reuse_method": "PARENT_BOUND_RELATIVE_SYMLINK_V16_DISPLAY_ASSETS",
        "application_sources": {key: file_record(repo_root / source["path"], repo_root) for key, source in config["application_sources"].items()},
        "builder_source": file_record(repo_root / config["builder_source"]["path"], repo_root),
        "plane_cluster_source": file_record(repo_root / config["plane_cluster_source"]["path"], repo_root),
        "application": {name: file_record(partial / name, partial) for name in ("index.html", "app.js", "auto_ox.css", "auto_ox.js")},
        "viewer_manifest": file_record(partial / "viewer_manifest.json", partial),
        "metrics_csv": file_record(csv_path, partial),
        "summary": file_record(partial / "reference_auto_ox_summary_v1.json", partial),
        "execution_counts": {"training": 0, "extraction": 0, "roofer": 0, "metric_evaluation": len(rows), "val3dity": 6},
        "official_PASS_usable": None,
        "scientific_verdict": None,
    }
    write_new(partial / "web_receipt_v1.json", canonical_json_bytes(receipt))
    os.rename(partial, output)
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=CONFIG)
    parser.add_argument("--repo-root", type=Path, default=REPO)
    parser.add_argument("--artifact-root", type=Path, default=REPO.parent / "JointBuildGS-artifacts")
    args = parser.parse_args()
    print(json.dumps(build(args.config.resolve(), args.repo_root.resolve(), args.artifact_root.resolve()), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
