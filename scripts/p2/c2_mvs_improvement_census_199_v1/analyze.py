#!/usr/bin/env python3
"""Build the 199-building C2 MVS improvement census from frozen outputs."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Iterable, Mapping

import numpy as np
from shapely.geometry import Polygon
from shapely.ops import triangulate

from scripts.p2_baselines.c1_c2_feasibility_pilot_v1.contract import score_continuous


REPO = Path(__file__).resolve().parents[3]
DEFAULT_CONFIG = REPO / "configs/p2/c2_mvs_improvement_census_199_v1/census_v1.json"


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read_bound(root: Path, spec: Mapping[str, Any]) -> bytes:
    path = root / str(spec["path"])
    data = path.read_bytes()
    if len(data) != int(spec["bytes"]) or sha256(data) != spec["sha256"]:
        raise RuntimeError(f"bound input differs: {path}")
    return data


def parse_bool(value: str) -> bool:
    return value.strip().lower() == "true"


def number(value: str) -> float | None:
    return float(value) if value.strip() else None


def transformed_vertices(feature: Mapping[str, Any], transform: Mapping[str, Any]) -> np.ndarray:
    vertices = np.asarray(feature["vertices"], dtype=np.float64)
    scale = np.asarray(transform["scale"], dtype=np.float64)
    translate = np.asarray(transform["translate"], dtype=np.float64)
    if vertices.ndim != 2 or vertices.shape[1] != 3 or scale.shape != (3,) or translate.shape != (3,):
        raise RuntimeError("invalid CityJSONSeq vertex/transform shape")
    return vertices * scale + translate


def roof_triangles_by_building(data: bytes) -> dict[str, list[np.ndarray]]:
    transform: Mapping[str, Any] | None = None
    output: defaultdict[str, list[np.ndarray]] = defaultdict(list)
    header_count = 0
    for line in data.decode("utf-8").splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        if record.get("type") == "CityJSON":
            header_count += 1
            transform = record.get("transform")
            continue
        if record.get("type") != "CityJSONFeature" or transform is None:
            raise RuntimeError("invalid CityJSONSeq inheritance sequence")
        vertices = transformed_vertices(record, transform)
        city_objects = record.get("CityObjects") or {}
        building_ids = [key for key, value in city_objects.items() if value.get("type") == "Building"]
        if len(building_ids) != 1:
            raise RuntimeError("CityJSONFeature must contain exactly one Building")
        stable_id = building_ids[0]
        for city_object in city_objects.values():
            for geometry in city_object.get("geometry") or []:
                if str(geometry.get("lod")) != "2.2":
                    continue
                semantics = geometry.get("semantics") or {}
                surfaces = semantics.get("surfaces") or []
                roof_indices = {
                    index for index, value in enumerate(surfaces)
                    if isinstance(value, Mapping) and value.get("type") == "RoofSurface"
                }
                boundaries = geometry.get("boundaries") or []
                values = semantics.get("values") or []
                candidates: list[tuple[Any, Any]] = []
                if geometry.get("type") in ("MultiSurface", "CompositeSurface"):
                    candidates = list(zip(boundaries, values))
                elif geometry.get("type") == "Solid":
                    candidates = [
                        (surface, semantic)
                        for shell, shell_values in zip(boundaries, values)
                        for surface, semantic in zip(shell, shell_values)
                    ]
                elif geometry.get("type") in ("MultiSolid", "CompositeSolid"):
                    candidates = [
                        (surface, semantic)
                        for solid, solid_values in zip(boundaries, values)
                        for shell, shell_values in zip(solid, solid_values)
                        for surface, semantic in zip(shell, shell_values)
                    ]
                for rings, semantic in candidates:
                    if semantic not in roof_indices or not isinstance(rings, list) or not rings:
                        continue
                    index_rings: list[list[int]] = []
                    for raw_ring in rings:
                        ring = [int(value) for value in raw_ring]
                        if len(ring) >= 2 and ring[0] == ring[-1]:
                            ring = ring[:-1]
                        if len(ring) >= 3:
                            index_rings.append(ring)
                    if not index_rings:
                        continue
                    points = np.vstack([vertices[ring] for ring in index_rings])
                    design = np.column_stack((points[:, 0], points[:, 1], np.ones(len(points))))
                    coefficients, *_ = np.linalg.lstsq(design, points[:, 2], rcond=None)
                    polygon = Polygon(
                        vertices[index_rings[0], :2],
                        [vertices[ring, :2] for ring in index_rings[1:]],
                    )
                    if not polygon.is_valid:
                        polygon = polygon.buffer(0)
                    polygons = [polygon] if polygon.geom_type == "Polygon" else list(polygon.geoms)
                    for part in polygons:
                        for triangle_2d in triangulate(part):
                            if not part.covers(triangle_2d):
                                continue
                            xy = np.asarray(triangle_2d.exterior.coords[:3], dtype=np.float64)
                            z = xy[:, 0] * coefficients[0] + xy[:, 1] * coefficients[1] + coefficients[2]
                            triangle = np.column_stack((xy, z))
                            if np.linalg.norm(np.cross(triangle[1] - triangle[0], triangle[2] - triangle[0])) > 1e-12:
                                output[stable_id].append(triangle)
    if header_count != 1:
        raise RuntimeError("CityJSONSeq must contain exactly one header")
    return dict(output)


def candidate_accuracy(metrics: Mapping[str, Any], thresholds: Mapping[str, float]) -> bool | None:
    values = {
        "reference_vertical_coverage_min": metrics.get("reference_vertical_coverage"),
        "height_error_mae_m_max": metrics.get("height_error_mae_m"),
        "RMSZ_m_max": metrics.get("RMSZ_m"),
        "RMSXY_m_max": metrics.get("RMSXY_m"),
        "surface_distance_rmse_m_max": metrics.get("surface_distance_rmse_m"),
        "surface_distance_p95_m_max": metrics.get("surface_distance_p95_m"),
    }
    if any(value is None or not math.isfinite(float(value)) for value in values.values()):
        return None
    return all(
        float(values[name]) >= float(limit) if name.endswith("_min") else float(values[name]) <= float(limit)
        for name, limit in thresholds.items()
    )


def primary_track(flags: set[str], reference_accuracy: bool | None) -> str:
    if "AOI_BOUNDARY_CONFOUNDED" in flags:
        return "AOI_BOUNDARY_REPLAY"
    if "RAW_MVS_SUPPORT_LOW" in flags:
        return "MVS_RAW_GEOMETRY_SUPPORT"
    if "ROOFER_POINTCLOUD_UNUSABLE" in flags and "CLASS6_SUPPORT_LOSS" in flags:
        return "CLASSIFICATION_SUPPORT"
    if "ROOFER_POINTCLOUD_UNUSABLE" in flags:
        return "ROOFER_POINT_SUPPORT"
    if "NO_CLIP_LOD22_MISSING" in flags:
        return "ROOFER_LOD22_GENERATION"
    if "NO_CLIP_TOPOLOGY_INVALID" in flags:
        return "ROOFER_ASSEMBLY_TOPOLOGY"
    if reference_accuracy is False:
        return "GEOMETRY_REFERENCE_ACCURACY"
    if "INPUT_FIT_RMSE_HIGH" in flags:
        return "GEOMETRY_INPUT_FIT"
    if "CLIP_SENSITIVE" in flags or "CLASS6_SUPPORT_LOSS" in flags:
        return "CLASSIFICATION_CLIPPING"
    return "NO_MAJOR_TECHNICAL_FLAG"


def csv_bytes(rows: Iterable[Mapping[str, Any]], fields: list[str]) -> bytes:
    import io
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore", lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode("utf-8")


def file_record(path: Path) -> dict[str, Any]:
    data = path.read_bytes()
    return {"path": path.as_posix(), "bytes": len(data), "sha256": sha256(data)}


def run(config_path: Path, artifact_root: Path, output_root: Path) -> dict[str, Any]:
    if output_root.exists():
        raise RuntimeError(f"add-once output already exists: {output_root}")
    config = json.loads(config_path.read_text(encoding="utf-8"))
    if config["interpretation"]["scientific_verdict"] is not None:
        raise RuntimeError("scientific_verdict must remain null")
    source = config["sources"]
    census_rows = list(csv.DictReader(read_bound(artifact_root, source["clip_census_csv"]).decode("utf-8").splitlines()))
    if len(census_rows) != 199 or len({row["stable_id"] for row in census_rows}) != 199:
        raise RuntimeError("clip census is not exact 199 unique buildings")
    triangles = roof_triangles_by_building(read_bound(artifact_root, source["no_clip_cityjsonseq"]))
    reference_rows = [json.loads(line) for line in read_bound(artifact_root, source["current_uas_reference_cells"]).decode("utf-8").splitlines()]
    reference_by_id: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in reference_rows:
        reference_by_id[str(row["stable_id"])].append(row)
    temporal = {
        row["building_id"]: row
        for row in (json.loads(line) for line in read_bound(artifact_root, source["temporal_reference_diagnostics"]).decode("utf-8").splitlines())
    }
    if len(temporal) != 199:
        raise RuntimeError("temporal reference ledger is not exact 199")

    bands = config["diagnostic_bands"]
    output_rows: list[dict[str, Any]] = []
    for row in census_rows:
        stable_id = row["stable_id"]
        all_support = number(row["all_point_coverage_0p5m"])
        class6_support = number(row["class6_coverage_0p5m"])
        support_gap = number(row["classification_coverage_gap"])
        clip_delta = number(row["clip_coverage_delta"])
        input_rmse = number(row["clip_false_rf_rmse_lod22"])
        inside = parse_bool(row["fully_inside_roofer_aoi"])
        reason = row["clip_false_reason"]
        flags: set[str] = set()
        if not inside:
            flags.add("AOI_BOUNDARY_CONFOUNDED")
        if all_support is not None and all_support < float(bands["raw_support_low_below"]):
            flags.add("RAW_MVS_SUPPORT_LOW")
        if support_gap is not None and support_gap >= float(bands["class6_support_gap_at_least"]):
            flags.add("CLASS6_SUPPORT_LOSS")
        if clip_delta is not None and clip_delta >= float(bands["clip_coverage_gain_at_least"]):
            flags.add("CLIP_SENSITIVE")
        if reason == "rf_pointcloud_unusable":
            flags.add("ROOFER_POINTCLOUD_UNUSABLE")
        if not parse_bool(row["clip_false_has_lod22"]):
            flags.add("NO_CLIP_LOD22_MISSING")
        if reason == "val3dity_invalid":
            flags.add("NO_CLIP_TOPOLOGY_INVALID")
        if input_rmse is not None and input_rmse >= float(bands["input_fit_rmse_high_m_at_least"]):
            flags.add("INPUT_FIT_RMSE_HIGH")
        if input_rmse is not None and input_rmse >= float(bands["input_fit_rmse_severe_m_at_least"]):
            flags.add("INPUT_FIT_RMSE_SEVERE")

        refs = reference_by_id.get(stable_id, [])
        temporal_status = temporal[stable_id]["status"]
        reference_eligible = (
            inside
            and temporal_status == "UNCHANGED_CONFIDENT"
            and len(refs) >= int(bands["minimum_current_reference_cells"])
            and bool(triangles.get(stable_id))
        )
        metrics = score_continuous(refs, triangles.get(stable_id, [])) if reference_eligible else {}
        accuracy = candidate_accuracy(metrics, bands["candidate_reference_accuracy"]) if reference_eligible else None
        if reference_eligible and accuracy is False:
            flags.add("CURRENT_UAS_ACCURACY_CANDIDATE_FAIL")
        if not reference_eligible:
            flags.add("CURRENT_REFERENCE_ASSESSMENT_GAP")
        output_rows.append({
            "population_index": int(row["population_index"]),
            "stable_id": stable_id,
            "fully_inside_roofer_aoi": inside,
            "all_point_coverage_0p5m": all_support,
            "class6_coverage_0p5m": class6_support,
            "classification_coverage_gap": support_gap,
            "clip_coverage_delta": clip_delta,
            "clip_true_building_part_count": number(row["clip_true_building_part_count"]),
            "no_clip_building_part_count": number(row["clip_false_building_part_count"]),
            "no_clip_reason": reason,
            "no_clip_lod22_xy_coverage": number(row["clip_false_lod22_xy_coverage"]),
            "no_clip_input_fit_rmse_m": input_rmse,
            "temporal_reference_status": temporal_status,
            "current_uas_reference_cell_count": len(refs),
            "current_uas_reference_eligible": reference_eligible,
            "current_uas_vertical_coverage": metrics.get("reference_vertical_coverage"),
            "current_uas_height_mae_m": metrics.get("height_error_mae_m"),
            "current_uas_rmsz_m": metrics.get("RMSZ_m"),
            "current_uas_rmsxy_m": metrics.get("RMSXY_m"),
            "current_uas_surface_rmse_m": metrics.get("surface_distance_rmse_m"),
            "current_uas_surface_p95_m": metrics.get("surface_distance_p95_m"),
            "current_uas_accuracy_candidate": accuracy,
            "primary_improvement_track": primary_track(flags, accuracy),
            "improvement_flags": ";".join(sorted(flags)),
            "official_PASS_usable": None,
            "scientific_verdict": None,
        })

    internal = [row for row in output_rows if row["fully_inside_roofer_aoi"]]
    track_counts = Counter(row["primary_improvement_track"] for row in output_rows)
    internal_track_counts = Counter(row["primary_improvement_track"] for row in internal)
    flag_counts = Counter(flag for row in output_rows for flag in row["improvement_flags"].split(";") if flag)
    internal_flag_counts = Counter(flag for row in internal for flag in row["improvement_flags"].split(";") if flag)
    eligible = [row for row in internal if row["current_uas_reference_eligible"]]
    summary = {
        "schema": config["schema"],
        "task_id": config["task_id"],
        "status": "TECHNICAL_CENSUS_COMPLETE",
        "population_count": len(output_rows),
        "fully_inside_roofer_aoi_count": len(internal),
        "aoi_boundary_confounding_count": len(output_rows) - len(internal),
        "primary_improvement_track_counts_all_199": dict(sorted(track_counts.items())),
        "primary_improvement_track_counts_full_aoi_152": dict(sorted(internal_track_counts.items())),
        "nonexclusive_flag_counts_all_199": dict(sorted(flag_counts.items())),
        "nonexclusive_flag_counts_full_aoi_152": dict(sorted(internal_flag_counts.items())),
        "current_uas_reference": {
            "raw_reference_building_count": len(reference_by_id),
            "unchanged_confident_count": sum(row["status"] == "UNCHANGED_CONFIDENT" for row in temporal.values()),
            "exact_no_clip_reference_eligible_count_full_aoi": len(eligible),
            "accuracy_candidate_pass_count": sum(row["current_uas_accuracy_candidate"] is True for row in eligible),
            "accuracy_candidate_fail_count": sum(row["current_uas_accuracy_candidate"] is False for row in eligible),
            "accuracy_candidate_null_count": sum(row["current_uas_accuracy_candidate"] is None for row in eligible),
            "role": "EVALUATION_ONLY_NON_CONFIRMATORY",
        },
        "diagnostic_bands": bands,
        "official_PASS_usable": None,
        "scientific_verdict": None,
    }
    fields = list(output_rows[0])
    output_root.mkdir(parents=True)
    (output_root / "results").mkdir()
    csv_path = output_root / "results/c2_mvs_improvement_census_199_v1.csv"
    summary_path = output_root / "results/summary_v1.json"
    csv_path.write_bytes(csv_bytes(output_rows, fields))
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    receipt = {
        "schema": "jointbuildgs.p2.c2_mvs_improvement_census_receipt.v1",
        "status": summary["status"],
        "inputs": source,
        "outputs": {"census": file_record(csv_path), "summary": file_record(summary_path)},
        "official_PASS_usable": None,
        "scientific_verdict": None,
    }
    (output_root / "control").mkdir()
    (output_root / "control/final_v1.json").write_text(json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.config.resolve(), args.artifact_root.resolve(), args.output_root.resolve()), ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
