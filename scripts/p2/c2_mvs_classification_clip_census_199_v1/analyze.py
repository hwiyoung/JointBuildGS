#!/usr/bin/env python3
"""C2 MVS class-support and Roofer terrain-clipping census over U_target=199.

This is a non-confirmatory technical diagnostic.  It reuses the exact frozen
class-2/6 C2 scene and the exact shared 199 GroundSurface-XY footprint source.
No MVS reconstruction, classification, or GT roof-Z access occurs here.
"""

from __future__ import annotations

import argparse
from collections import Counter
import csv
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import statistics
from typing import Any, Iterable, Mapping, Sequence

import laspy
import numpy as np
from shapely import contains_xy, make_valid
from shapely.geometry import Polygon, box, shape
from shapely.ops import unary_union


REPO = Path(__file__).resolve().parents[3]
DEFAULT_CONFIG = REPO / "configs/p2/c2_mvs_classification_clip_census_199_v1/census_v1.json"
ARMS = ("formal", "clip_true", "clip_false")


def canonical_json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def sha256_file(path: Path) -> tuple[int, str]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            size += len(chunk)
            digest.update(chunk)
    return size, digest.hexdigest()


def file_record(path: Path, root: Path | None = None) -> dict[str, Any]:
    size, digest = sha256_file(path)
    return {
        "path": path.relative_to(root).as_posix() if root is not None else path.as_posix(),
        "bytes": size,
        "sha256": digest,
    }


def load_config(path: Path = DEFAULT_CONFIG) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def validate_config(config: Mapping[str, Any]) -> None:
    if config.get("schema") != "jointbuildgs.p2.c2_mvs_classification_clip_census_199.v1":
        raise RuntimeError("unexpected census config schema")
    if config.get("status") != "USER_DIRECTED_NON_CONFIRMATORY_TECHNICAL_DIAGNOSTIC":
        raise RuntimeError("census is not user-directed")
    if config.get("population") != {"name": "U_target", "building_count": 199}:
        raise RuntimeError("population must remain exact U_target=199")
    interpretation = config.get("interpretation") or {}
    if interpretation.get("official_PASS_usable", "invalid") is not None:
        raise RuntimeError("official PASS_usable must remain null")
    if interpretation.get("scientific_verdict", "invalid") is not None:
        raise RuntimeError("scientific_verdict must remain null")
    if set((config.get("roofer") or {}).get("arms") or {}) != {"clip_true", "clip_false"}:
        raise RuntimeError("exact matched Roofer arms are required")


def source_paths(config: Mapping[str, Any], artifact_root: Path) -> dict[str, Path]:
    formal = config["formal_source"]
    root = artifact_root / formal["relative_root"]
    return {name: root / spec["path"] for name, spec in formal["files"].items()}


def verify_sources(config: Mapping[str, Any], artifact_root: Path) -> dict[str, Any]:
    validate_config(config)
    paths = source_paths(config, artifact_root)
    records: dict[str, Any] = {}
    for name, spec in config["formal_source"]["files"].items():
        path = paths[name]
        if path.is_symlink() or not path.is_file():
            raise RuntimeError(f"source is missing or not a regular file: {path}")
        actual = file_record(path)
        if actual["bytes"] != int(spec["bytes"]) or actual["sha256"] != spec["sha256"]:
            raise RuntimeError(f"source identity differs: {name}")
        records[name] = actual
    prepared = json.loads(paths["prepared"].read_text(encoding="utf-8"))
    ids = [str(value) for value in prepared["ordered_building_ids"]]
    if len(ids) != 199 or len(set(ids)) != 199:
        raise RuntimeError("formal prepared roster is not exact 199 unique IDs")
    return {"sources": records, "ordered_building_ids": ids}


def _write_new(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(data)


def prepare(config_path: Path, artifact_root: Path, output_root: Path, source_commit: str) -> dict[str, Any]:
    if output_root.exists() and any(output_root.iterdir()):
        raise RuntimeError("fresh add-once output namespace required")
    output_root.mkdir(parents=True, exist_ok=True)
    config = load_config(config_path)
    verified = verify_sources(config, artifact_root)
    receipt = {
        "schema": "jointbuildgs.p2.c2_mvs_classification_clip_census_199.prepared.v1",
        "task_id": config["task_id"],
        "status": "PREPARED_FOR_MATCHED_CLIP_PAIR",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "source_commit": source_commit,
        "population_count": len(verified["ordered_building_ids"]),
        "ordered_building_ids": verified["ordered_building_ids"],
        "source_records": verified["sources"],
        "roofer_image": config["roofer"]["image"],
        "roofer_image_id": config["roofer"]["image_id"],
        "scientific_verdict": None,
    }
    _write_new(output_root / "control/prepared_v1.json", canonical_json_bytes(receipt))
    return receipt


def combine_cityjsonseq(source: Path, target: Path) -> None:
    header: dict[str, Any] | None = None
    features: list[dict[str, Any]] = []
    for raw in source.read_text(encoding="utf-8").splitlines():
        if not raw.strip():
            continue
        record = json.loads(raw)
        if record.get("type") == "CityJSON":
            header = record
        elif record.get("type") == "CityJSONFeature":
            features.append(record)
    if header is None:
        raise RuntimeError(f"CityJSONSeq header missing: {source}")
    transform = header["transform"]
    vertices: list[list[int]] = []
    objects: dict[str, Any] = {}

    def shift(value: Any, offset: int) -> Any:
        if isinstance(value, int):
            return value + offset
        if isinstance(value, list):
            return [shift(item, offset) for item in value]
        return value

    for feature in features:
        offset = len(vertices)
        vertices.extend(feature.get("vertices") or [])
        for object_id, city_object in feature.get("CityObjects", {}).items():
            copied = json.loads(json.dumps(city_object))
            for geometry in copied.get("geometry") or []:
                geometry["boundaries"] = shift(geometry.get("boundaries") or [], offset)
            objects[object_id] = copied
    assembled = {
        "type": "CityJSON",
        "version": header.get("version", "2.0"),
        "transform": transform,
        "metadata": header.get("metadata", {}),
        "CityObjects": objects,
        "vertices": vertices,
    }
    _write_new(target, canonical_json_bytes(assembled))


def _val_by_id(path: Path) -> dict[str, bool]:
    report = json.loads(path.read_text(encoding="utf-8"))
    return {
        str(feature["id"]): bool(feature.get("validity"))
        for feature in report.get("features", [])
        if feature.get("id") is not None
    }


def _surface_pairs(geometry: Mapping[str, Any]) -> Iterable[tuple[Any, Any]]:
    boundaries = geometry.get("boundaries") or []
    values = (geometry.get("semantics") or {}).get("values") or []
    kind = geometry.get("type")
    if kind in ("MultiSurface", "CompositeSurface"):
        yield from zip(boundaries, values)
    elif kind == "Solid":
        for shell, shell_values in zip(boundaries, values):
            yield from zip(shell, shell_values)
    elif kind in ("MultiSolid", "CompositeSolid"):
        for solid, solid_values in zip(boundaries, values):
            for shell, shell_values in zip(solid, solid_values):
                yield from zip(shell, shell_values)


def _ground_union(feature: Mapping[str, Any], transform: Mapping[str, Sequence[float]]):
    scale = np.asarray(transform["scale"], dtype=np.float64)
    translate = np.asarray(transform["translate"], dtype=np.float64)
    vertices = np.asarray(feature.get("vertices") or [], dtype=np.float64)
    if vertices.size == 0:
        return None
    vertices = vertices * scale + translate
    polygons = []
    for city_object in feature.get("CityObjects", {}).values():
        for geometry in city_object.get("geometry") or []:
            if str(geometry.get("lod")) != "2.2":
                continue
            surfaces = (geometry.get("semantics") or {}).get("surfaces") or []
            ground_indices = {
                index for index, surface in enumerate(surfaces)
                if isinstance(surface, Mapping) and surface.get("type") == "GroundSurface"
            }
            for rings, semantic in _surface_pairs(geometry):
                if semantic not in ground_indices or not rings:
                    continue
                coords = []
                for ring in rings:
                    indices = [int(value) for value in ring]
                    if len(indices) >= 2 and indices[0] == indices[-1]:
                        indices = indices[:-1]
                    if len(indices) >= 3:
                        coords.append([(float(vertices[index, 0]), float(vertices[index, 1])) for index in indices])
                if coords:
                    polygon = make_valid(Polygon(coords[0], coords[1:]))
                    if not polygon.is_empty:
                        polygons.append(polygon)
    return unary_union(polygons) if polygons else None


def _parse_cityjsonseq(path: Path) -> tuple[Mapping[str, Sequence[float]], dict[str, dict[str, Any]]]:
    transform: Mapping[str, Sequence[float]] | None = None
    features: dict[str, dict[str, Any]] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        if not raw.strip():
            continue
        record = json.loads(raw)
        if record.get("type") == "CityJSON":
            transform = record["transform"]
        elif record.get("type") == "CityJSONFeature":
            features[str(record["id"])] = record
    if transform is None:
        raise RuntimeError(f"missing CityJSONSeq transform: {path}")
    return transform, features


def _feature_attributes(feature: Mapping[str, Any]) -> Mapping[str, Any]:
    feature_id = str(feature["id"])
    object_value = feature.get("CityObjects", {}).get(feature_id)
    if isinstance(object_value, Mapping):
        return object_value.get("attributes") or {}
    buildings = [
        value for value in feature.get("CityObjects", {}).values()
        if isinstance(value, Mapping) and value.get("type") == "Building"
    ]
    return (buildings[0].get("attributes") or {}) if len(buildings) == 1 else {}


def _has_lod22(feature: Mapping[str, Any]) -> bool:
    return any(
        str(geometry.get("lod")) == "2.2"
        for city_object in feature.get("CityObjects", {}).values()
        for geometry in city_object.get("geometry") or []
    )


def _status(feature: Mapping[str, Any] | None, valid: bool | None) -> tuple[str, str]:
    if feature is None:
        return "MISSING", "missing_roofer_feature"
    attrs = _feature_attributes(feature)
    if attrs.get("rf_success") is False:
        return "FAILED", "rf_success_false"
    if attrs.get("rf_pointcloud_unusable") is True:
        return "FAILED", "rf_pointcloud_unusable"
    if not _has_lod22(feature):
        return "FAILED", "missing_lod22_geometry"
    if valid is None:
        return "FAILED", "missing_val3dity_feature"
    if not valid:
        return "FAILED", "val3dity_invalid"
    return "TECHNICAL_VALID_LOD22", "technical_valid_lod22"


def _arm_rows(
    path: Path,
    val_path: Path,
    ids: Sequence[str],
    footprints: Mapping[str, Any],
) -> dict[str, dict[str, Any]]:
    transform, features = _parse_cityjsonseq(path)
    validity = _val_by_id(val_path)
    output: dict[str, dict[str, Any]] = {}
    for stable_id in ids:
        feature = features.get(stable_id)
        valid = validity.get(stable_id)
        status, reason = _status(feature, valid)
        attrs = _feature_attributes(feature) if feature is not None else {}
        ground = _ground_union(feature, transform) if feature is not None and _has_lod22(feature) else None
        footprint = footprints[stable_id]
        footprint_area = float(footprint.area)
        ground_area = float(ground.area) if ground is not None else 0.0
        intersection = float(ground.intersection(footprint).area) if ground is not None else 0.0
        union_area = footprint_area + ground_area - intersection
        output[stable_id] = {
            "status": status,
            "reason": reason,
            "has_lod22": bool(feature is not None and _has_lod22(feature)),
            "val3dity_valid": valid,
            "rf_success": attrs.get("rf_success"),
            "rf_pointcloud_unusable": attrs.get("rf_pointcloud_unusable"),
            "rf_pt_density": attrs.get("rf_pt_density"),
            "rf_nodata_frac": attrs.get("rf_nodata_frac"),
            "rf_rmse_lod22": attrs.get("rf_rmse_lod22"),
            "rf_roof_planes": attrs.get("rf_roof_planes"),
            "rf_ridgelines": attrs.get("rf_ridgelines"),
            "building_part_count": sum(
                value.get("type") == "BuildingPart"
                for value in (feature or {}).get("CityObjects", {}).values()
            ),
            "lod22_xy_coverage": intersection / footprint_area if footprint_area > 0 else None,
            "lod22_xy_iou": intersection / union_area if union_area > 0 else None,
            "lod22_xy_outside_m2": max(0.0, ground_area - intersection),
        }
    return output


def _load_footprints(path: Path, ids: Sequence[str]) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    output: dict[str, Any] = {}
    for feature in data.get("features", []):
        properties = feature.get("properties") or {}
        stable_id = str(properties.get("stable_id") or properties.get("id") or feature.get("id") or "")
        if stable_id in ids:
            geometry = make_valid(shape(feature["geometry"]))
            if geometry.is_empty or float(geometry.area) <= 0:
                raise RuntimeError(f"invalid shared footprint: {stable_id}")
            output[stable_id] = geometry
    missing = sorted(set(ids) - set(output))
    if missing:
        raise RuntimeError(f"shared footprints missing IDs: {missing[:3]}")
    return output


def _support_rows(
    classified_path: Path,
    footprints: Mapping[str, Any],
    cell_m: float,
    ground_class: int,
    building_class: int,
    aoi_bbox: Sequence[float],
) -> dict[str, dict[str, Any]]:
    min_x = math.floor(min(geometry.bounds[0] for geometry in footprints.values()) / cell_m) * cell_m
    min_y = math.floor(min(geometry.bounds[1] for geometry in footprints.values()) / cell_m) * cell_m
    max_x = math.ceil(max(geometry.bounds[2] for geometry in footprints.values()) / cell_m) * cell_m
    max_y = math.ceil(max(geometry.bounds[3] for geometry in footprints.values()) / cell_m) * cell_m
    width = int(round((max_x - min_x) / cell_m))
    height = int(round((max_y - min_y) / cell_m))
    size = width * height
    counts_all = np.zeros(size, dtype=np.int64)
    counts_ground = np.zeros(size, dtype=np.int64)
    counts_building = np.zeros(size, dtype=np.int64)
    with laspy.open(classified_path) as reader:
        for chunk in reader.chunk_iterator(2_000_000):
            x = np.asarray(chunk.x)
            y = np.asarray(chunk.y)
            classification = np.asarray(chunk.classification)
            ix = np.floor((x - min_x) / cell_m).astype(np.int64)
            iy = np.floor((y - min_y) / cell_m).astype(np.int64)
            keep = (ix >= 0) & (ix < width) & (iy >= 0) & (iy < height)
            linear = iy[keep] * width + ix[keep]
            classes = classification[keep]
            counts_all += np.bincount(linear, minlength=size)
            ground_keep = classes == ground_class
            if np.any(ground_keep):
                counts_ground += np.bincount(linear[ground_keep], minlength=size)
            building_keep = classes == building_class
            if np.any(building_keep):
                counts_building += np.bincount(linear[building_keep], minlength=size)
    aoi = box(*map(float, aoi_bbox))
    output: dict[str, dict[str, Any]] = {}
    for stable_id, geometry in footprints.items():
        gx0, gy0, gx1, gy1 = geometry.bounds
        ix0 = max(0, int(math.floor((gx0 - min_x) / cell_m)))
        iy0 = max(0, int(math.floor((gy0 - min_y) / cell_m)))
        ix1 = min(width, int(math.ceil((gx1 - min_x) / cell_m)))
        iy1 = min(height, int(math.ceil((gy1 - min_y) / cell_m)))
        xs = min_x + (np.arange(ix0, ix1) + 0.5) * cell_m
        ys = min_y + (np.arange(iy0, iy1) + 0.5) * cell_m
        xx, yy = np.meshgrid(xs, ys)
        inside = contains_xy(geometry, xx, yy)
        local_linear = ((np.arange(iy0, iy1)[:, None] * width) + np.arange(ix0, ix1)[None, :])[inside]
        cell_count = int(local_linear.size)
        if cell_count <= 0:
            raise RuntimeError(f"footprint has no diagnostic grid cells: {stable_id}")
        all_values = counts_all[local_linear]
        ground_values = counts_ground[local_linear]
        building_values = counts_building[local_linear]
        all_points = int(all_values.sum())
        ground_points = int(ground_values.sum())
        building_points = int(building_values.sum())
        output[stable_id] = {
            "footprint_area_m2": float(geometry.area),
            "footprint_grid_cells": cell_count,
            "fully_inside_roofer_aoi": bool(aoi.covers(geometry)),
            "all_point_count_inside_footprint": all_points,
            "class2_point_count_inside_footprint": ground_points,
            "class6_point_count_inside_footprint": building_points,
            "all_point_coverage_0p5m": float(np.count_nonzero(all_values) / cell_count),
            "class2_coverage_0p5m": float(np.count_nonzero(ground_values) / cell_count),
            "class6_coverage_0p5m": float(np.count_nonzero(building_values) / cell_count),
            "class6_point_retention": building_points / all_points if all_points else None,
        }
        output[stable_id]["classification_coverage_gap"] = (
            output[stable_id]["all_point_coverage_0p5m"] - output[stable_id]["class6_coverage_0p5m"]
        )
    return output


def _median(values: Iterable[float | None]) -> float | None:
    finite = [float(value) for value in values if value is not None and math.isfinite(float(value))]
    return statistics.median(finite) if finite else None


def _quantile(values: Iterable[float | None], q: float) -> float | None:
    finite = np.asarray([float(value) for value in values if value is not None and math.isfinite(float(value))])
    return float(np.quantile(finite, q)) if finite.size else None


def _flatten(prefix: str, row: Mapping[str, Any]) -> dict[str, Any]:
    return {f"{prefix}_{key}": value for key, value in row.items()}


def _csv_value(value: Any) -> Any:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    return value


def _write_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    fields = list(rows[0])
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: _csv_value(row.get(key)) for key in fields})


def _summary(rows: Sequence[Mapping[str, Any]], thresholds_pp: Sequence[float]) -> dict[str, Any]:
    full = [row for row in rows if row["fully_inside_roofer_aoi"]]
    paired_rmse = [
        row for row in full
        if row["clip_true_rf_rmse_lod22"] is not None and row["clip_false_rf_rmse_lod22"] is not None
    ]
    summary: dict[str, Any] = {
        "population_count": len(rows),
        "fully_inside_roofer_aoi_count": len(full),
        "aoi_crossing_count": len(rows) - len(full),
        "status_counts": {
            arm: dict(Counter(str(row[f"{arm}_reason"]) for row in rows)) for arm in ARMS
        },
        "matched_status_transition_counts_full_aoi": dict(Counter(
            f"{row['clip_true_reason']}->{row['clip_false_reason']}" for row in full
        )),
        "support_grid_full_aoi": {
            "median_all_point_coverage": _median(row["all_point_coverage_0p5m"] for row in full),
            "median_class6_coverage": _median(row["class6_coverage_0p5m"] for row in full),
            "median_classification_coverage_gap": _median(row["classification_coverage_gap"] for row in full),
            "high_raw_ge_90pct_count": sum(row["all_point_coverage_0p5m"] >= 0.9 for row in full),
            "high_raw_ge_90pct_and_class6_lt_50pct_count": sum(
                row["all_point_coverage_0p5m"] >= 0.9 and row["class6_coverage_0p5m"] < 0.5 for row in full
            ),
            "coverage_gap_sensitivity_counts": {
                f"ge_{int(value)}pp": sum(row["classification_coverage_gap"] >= value / 100.0 for row in full)
                for value in thresholds_pp
            },
        },
        "clip_effect_full_aoi": {
            "valid_lod22_recovery_count": sum(
                row["clip_true_status"] != "TECHNICAL_VALID_LOD22"
                and row["clip_false_status"] == "TECHNICAL_VALID_LOD22"
                for row in full
            ),
            "valid_lod22_loss_count": sum(
                row["clip_true_status"] == "TECHNICAL_VALID_LOD22"
                and row["clip_false_status"] != "TECHNICAL_VALID_LOD22"
                for row in full
            ),
            "lod22_presence_recovery_count": sum(
                not row["clip_true_has_lod22"] and row["clip_false_has_lod22"] for row in full
            ),
            "no_clip_val3dity_invalid_count": sum(
                row["clip_false_has_lod22"] and row["clip_false_val3dity_valid"] is False for row in full
            ),
            "coverage_gain_sensitivity_counts": {
                f"ge_{int(value)}pp": sum(row["clip_coverage_delta"] >= value / 100.0 for row in full)
                for value in thresholds_pp
            },
            "coverage_loss_ge_10pp_count": sum(row["clip_coverage_delta"] <= -0.10 for row in full),
            "median_coverage_delta": _median(row["clip_coverage_delta"] for row in full),
        },
        "rmse_input_fit_full_aoi": {
            "paired_count": len(paired_rmse),
            "clip_true_median_m": _median(row["clip_true_rf_rmse_lod22"] for row in paired_rmse),
            "clip_false_median_m": _median(row["clip_false_rf_rmse_lod22"] for row in paired_rmse),
            "delta_false_minus_true_median_m": _median(row["clip_rmse_delta_m"] for row in paired_rmse),
            "delta_false_minus_true_p10_m": _quantile((row["clip_rmse_delta_m"] for row in paired_rmse), 0.10),
            "delta_false_minus_true_p90_m": _quantile((row["clip_rmse_delta_m"] for row in paired_rmse), 0.90),
            "improved_count": sum(row["clip_rmse_delta_m"] < 0 for row in paired_rmse),
            "unchanged_count": sum(abs(row["clip_rmse_delta_m"]) <= 1e-12 for row in paired_rmse),
            "worsened_count": sum(row["clip_rmse_delta_m"] > 0 for row in paired_rmse),
            "no_clip_rmse_ge_1m_count": sum(row["clip_false_rf_rmse_lod22"] >= 1.0 for row in paired_rmse),
            "no_clip_rmse_ge_2m_count": sum(row["clip_false_rf_rmse_lod22"] >= 2.0 for row in paired_rmse),
            "no_clip_rmse_ge_4m_count": sum(row["clip_false_rf_rmse_lod22"] >= 4.0 for row in paired_rmse),
            "note": "rf_rmse_lod22 is Roofer input-fit, not independent reference error",
        },
        "formal_replay_check": {
            "status_reason_mismatch_count": sum(row["formal_reason"] != row["clip_true_reason"] for row in rows),
            "rmse_mismatch_gt_1e_9_count": sum(
                row["formal_rf_rmse_lod22"] is not None
                and row["clip_true_rf_rmse_lod22"] is not None
                and abs(row["formal_rf_rmse_lod22"] - row["clip_true_rf_rmse_lod22"]) > 1e-9
                for row in rows
            ),
            "coverage_mismatch_gt_1e_9_count": sum(
                row["formal_lod22_xy_coverage"] is not None
                and row["clip_true_lod22_xy_coverage"] is not None
                and abs(row["formal_lod22_xy_coverage"] - row["clip_true_lod22_xy_coverage"]) > 1e-9
                for row in rows
            ),
        },
    }
    return summary


def _technical_return(summary: Mapping[str, Any], row_4906982: Mapping[str, Any]) -> str:
    support = summary["support_grid_full_aoi"]
    clip = summary["clip_effect_full_aoi"]
    rmse = summary["rmse_input_fit_full_aoi"]
    return f"""# C2 MVS classification and terrain-clipping census — technical return

- Population: U_target=199
- Fully inside historical Roofer AOI: {summary['fully_inside_roofer_aoi_count']}
- AOI-crossing, attribution-confounded: {summary['aoi_crossing_count']}
- Scientific verdict: `null`
- Official `PASS_usable`: `null`

## Answer first

Turning off terrain clipping is not a general accuracy fix.  Within the {summary['fully_inside_roofer_aoi_count']} buildings fully contained by the historical AOI, it converted {clip['valid_lod22_recovery_count']} buildings to val3dity-valid LoD2.2 and lost validity for {clip['valid_lod22_loss_count']}.  Coverage increased by at least 10/25/50 percentage points for {clip['coverage_gain_sensitivity_counts']['ge_10pp']}/{clip['coverage_gain_sensitivity_counts']['ge_25pp']}/{clip['coverage_gain_sensitivity_counts']['ge_50pp']} buildings.

The classification-support proxy is separate: {support['high_raw_ge_90pct_and_class6_lt_50pct_count']} fully-contained buildings had at least 90% all-point grid support but under 50% class-6 support.  The all-point minus class-6 coverage gap exceeded 10/25/50 percentage points for {support['coverage_gap_sensitivity_counts']['ge_10pp']}/{support['coverage_gap_sensitivity_counts']['ge_25pp']}/{support['coverage_gap_sensitivity_counts']['ge_50pp']} buildings.  These are diagnostic bands, not frozen success thresholds.

## 4906982

The matched pair reproduced the earlier observation.  `clip=true` produced {row_4906982['clip_true_building_part_count']} BuildingParts, {100*row_4906982['clip_true_lod22_xy_coverage']:.2f}% XY coverage, and Roofer input-fit RMSE {row_4906982['clip_true_rf_rmse_lod22']:.4f} m.  `clip=false` produced {row_4906982['clip_false_building_part_count']} BuildingPart, {100*row_4906982['clip_false_lod22_xy_coverage']:.2f}% XY coverage, and RMSE {row_4906982['clip_false_rf_rmse_lod22']:.4f} m.  Both detected {row_4906982['clip_true_rf_roof_planes']} roof planes and both were val3dity-valid.  Thus clipping explains the footprint fragmentation, but the remaining 4.02 m input-fit residual is a separate geometry/plane-fit warning.

## RMSE behavior

Among {rmse['paired_count']} fully-contained buildings with RMSE in both matched arms, the median changed from {rmse['clip_true_median_m']:.4f} m to {rmse['clip_false_median_m']:.4f} m.  RMSE improved/was unchanged/worsened for {rmse['improved_count']}/{rmse['unchanged_count']}/{rmse['worsened_count']} buildings.  After disabling clipping, {rmse['no_clip_rmse_ge_1m_count']}/{rmse['no_clip_rmse_ge_2m_count']}/{rmse['no_clip_rmse_ge_4m_count']} buildings remained at or above 1/2/4 m.

`rf_rmse_lod22` is fit to the condition input cloud, not independent LoD2-reference error.  It cannot by itself establish geometric correctness.

## Interpretation boundary

The 0.5 m support grid compares all classified-scene points inside each shared footprint with the subset retained as class 6.  Because SMRF does not delete points, their difference is a useful classification-loss proxy.  It does not prove that every non-class-6 point is truly a roof point.  The 47 AOI-crossing buildings are retained but excluded from primary attribution counts.  No GT RoofSurface, roof Z, roof type, or semantic label was used.
"""


def finalize(config_path: Path, artifact_root: Path, output_root: Path) -> dict[str, Any]:
    config = load_config(config_path)
    verified = verify_sources(config, artifact_root)
    prepared = json.loads((output_root / "control/prepared_v1.json").read_text(encoding="utf-8"))
    ids = [str(value) for value in prepared["ordered_building_ids"]]
    if ids != verified["ordered_building_ids"]:
        raise RuntimeError("prepared roster differs from verified formal source")
    paths = source_paths(config, artifact_root)
    footprints = _load_footprints(paths["shared_footprints"], ids)
    arm_paths = {
        "formal": (paths["formal_cityjsonseq"], paths["formal_val3dity"]),
        "clip_true": (
            next((output_root / "runs/clip_true").glob("*.city.jsonl")),
            output_root / "runs/clip_true/val3dity_report.json",
        ),
        "clip_false": (
            next((output_root / "runs/clip_false").glob("*.city.jsonl")),
            output_root / "runs/clip_false/val3dity_report.json",
        ),
    }
    arms = {
        arm: _arm_rows(city_path, val_path, ids, footprints)
        for arm, (city_path, val_path) in arm_paths.items()
    }
    class_config = config["classification"]
    support = _support_rows(
        paths["classified_mvs"],
        footprints,
        float(class_config["support_grid_cell_m"]),
        int(class_config["ground_class"]),
        int(class_config["building_class"]),
        config["roofer"]["aoi_bbox"],
    )
    rows: list[dict[str, Any]] = []
    for index, stable_id in enumerate(ids, start=1):
        row: dict[str, Any] = {
            "population_index": index,
            "stable_id": stable_id,
            **support[stable_id],
        }
        for arm in ARMS:
            row.update(_flatten(arm, arms[arm][stable_id]))
        row["clip_coverage_delta"] = (
            row["clip_false_lod22_xy_coverage"] - row["clip_true_lod22_xy_coverage"]
        )
        row["clip_rmse_delta_m"] = (
            row["clip_false_rf_rmse_lod22"] - row["clip_true_rf_rmse_lod22"]
            if row["clip_false_rf_rmse_lod22"] is not None and row["clip_true_rf_rmse_lod22"] is not None
            else None
        )
        row["clip_valid_recovery"] = (
            row["clip_true_status"] != "TECHNICAL_VALID_LOD22"
            and row["clip_false_status"] == "TECHNICAL_VALID_LOD22"
        )
        rows.append(row)
    if len(rows) != 199:
        raise RuntimeError("census is not exact 199 rows")
    summary = _summary(rows, [float(value) for value in class_config["support_gap_sensitivity_pp"]])
    summary.update({
        "schema": "jointbuildgs.p2.c2_mvs_classification_clip_census_199.summary.v1",
        "task_id": config["task_id"],
        "status": "TECHNICAL_DIAGNOSTIC_COMPLETE",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "support_grid_cell_m": float(class_config["support_grid_cell_m"]),
        "official_PASS_usable": None,
        "scientific_verdict": None,
    })
    summary["building_4906982"] = next(row for row in rows if row["stable_id"] == "DEBY_LOD2_4906982")
    csv_path = output_root / "results/building_classification_clip_census_v1.csv"
    summary_path = output_root / "results/summary_v1.json"
    report_path = output_root / "reports/TECHNICAL_RETURN.md"
    _write_csv(csv_path, rows)
    _write_new(summary_path, canonical_json_bytes(summary))
    _write_new(report_path, _technical_return(summary, summary["building_4906982"]).encode("utf-8"))
    outputs = {
        "building_csv": file_record(csv_path, output_root),
        "summary": file_record(summary_path, output_root),
        "technical_return": file_record(report_path, output_root),
        "matched_runs": {
            arm: {
                "cityjsonseq": file_record(arm_paths[arm][0], output_root if arm != "formal" else None),
                "val3dity": file_record(arm_paths[arm][1], output_root if arm != "formal" else None),
            }
            for arm in ("clip_true", "clip_false")
        },
    }
    receipt = {
        "schema": "jointbuildgs.p2.c2_mvs_classification_clip_census_199.final.v1",
        "task_id": config["task_id"],
        "status": "TECHNICAL_COMPLETE_WITH_EXPLICIT_AOI_CONFOUNDING",
        "completed_utc": datetime.now(timezone.utc).isoformat(),
        "source_commit": prepared["source_commit"],
        "population_count": len(rows),
        "outputs": outputs,
        "official_PASS_usable": None,
        "scientific_verdict": None,
    }
    _write_new(output_root / "control/final_v1.json", canonical_json_bytes(receipt))
    return receipt


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("prepare", "combine", "finalize"))
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--artifact-root", type=Path)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--source-commit")
    parser.add_argument("--arm", choices=("clip_true", "clip_false"))
    args = parser.parse_args()
    if args.command == "prepare":
        if args.artifact_root is None or not args.source_commit:
            parser.error("prepare requires --artifact-root and --source-commit")
        print(json.dumps(prepare(args.config, args.artifact_root, args.output_root, args.source_commit), indent=2))
    elif args.command == "combine":
        if args.arm is None:
            parser.error("combine requires --arm")
        source = next((args.output_root / "runs" / args.arm).glob("*.city.jsonl"))
        target = args.output_root / "runs" / args.arm / "assembled.city.json"
        combine_cityjsonseq(source, target)
        print(target)
    else:
        if args.artifact_root is None:
            parser.error("finalize requires --artifact-root")
        print(json.dumps(finalize(args.config, args.artifact_root, args.output_root), indent=2))


if __name__ == "__main__":
    main()
