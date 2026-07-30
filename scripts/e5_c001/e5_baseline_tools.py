#!/usr/bin/env python3
"""E5 A4 raw baseline reinforcement helpers.

Runs inside ``jointbuildgs-p0-tools:t0`` from the repository root.  The script
keeps the P0/W2 Roofer path intact: SMRF ground classification, footprint
overlay to building class 6, Roofer default parameters, and val3dity parsing.
Observation only; no training and no verdict wording.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import subprocess
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


RUN_ROOT = Path("phases/p0-audit/runs")
P2_RUN_ROOT = Path("phases/p2-gsjso/runs")
POPULATION = Path("docs/experiments/input-and-alignment/population_aux/tables/population_aux_v4.csv")
FOOTPRINTS_GPKG = Path("phases/p0-audit/data/work/w2/footprints_scene_aoi.gpkg")
FOOTPRINTS_GEOJSON = Path("results/tum_transfer/analysis/footprints_aoi.geojson")
ROOFER_BBOX = (690766.0, 5335839.0, 691180.0, 5336379.0)
GROUND = 2
BUILDING = 6
UNCLASSIFIED = 1
ARM_LABELS = {"raw_acmp": "raw-ACMP", "raw_sparse": "raw-sparse"}
ARM_PRETTY = {"raw_acmp": "raw-ACMP", "raw_sparse": "raw-sparse"}
SMRF = {
    "cell": 1.0,
    "slope": 0.15,
    "scalar": 1.25,
    "threshold": 0.5,
    "window": 18.0,
    "ground_class": GROUND,
    "other_class": UNCLASSIFIED,
}
ACMP_SOURCE = Path("results/tum_transfer/mob_analysis/p0c_step2/acmp_aoi_utm.laz")
ALS_SOURCE = Path("results/tum_transfer/mob_analysis/p0c_step2/als_aoi.laz")
SPARSE_SOURCE = Path("phases/p0-audit/data/work/mvs/openmvs/colmap_txt/sparse/points3D.txt")


def repo_root() -> Path:
    return Path.cwd()


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def read_population() -> list[str]:
    rows = read_csv_rows(POPULATION)
    return [row["building_id"] for row in rows]


def run(cmd: list[str], log_path: Path | None = None, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    if log_path is not None:
        log_path.parent.mkdir(parents=True, exist_ok=True)
    print("+ " + " ".join(cmd), flush=True)
    proc = subprocess.run(cmd, cwd=cwd, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if log_path is not None:
        log_path.write_text("+ " + " ".join(cmd) + "\n" + proc.stdout, encoding="utf-8")
    print(proc.stdout, end="", flush=True)
    proc.check_returncode()
    return proc


def capture(cmd: list[str]) -> str:
    try:
        proc = subprocess.run(cmd, text=True, capture_output=True, check=False)
    except FileNotFoundError as exc:
        return f"not_available:{exc.filename}"
    return ((proc.stdout or "") + (proc.stderr or "")).strip()


def sha256_file(path: Path, block_size: int = 1024 * 1024) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(block_size), b""):
            h.update(block)
    return h.hexdigest()


def fmt(value: Any, digits: int = 6) -> str:
    if value is None:
        return "none"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int,)):
        return str(value)
    if isinstance(value, float):
        if not math.isfinite(value):
            return "none"
        return f"{value:.{digits}f}"
    return str(value)


def yaml_scalar(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return "null"
    if isinstance(value, (int, float)):
        return str(value)
    text = str(value)
    if not text or any(ch in text for ch in ":#[]{}*,&!|>'\"%@`"):
        return json.dumps(text, ensure_ascii=False)
    return text


def to_yaml(value: Any, indent: int = 0) -> str:
    space = " " * indent
    if isinstance(value, dict):
        lines: list[str] = []
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


def write_overlay_geojson(target: Path, population: set[str]) -> int:
    source = json.loads(FOOTPRINTS_GEOJSON.read_text(encoding="utf-8"))
    features = []
    for feat in source["features"]:
        props = dict(feat.get("properties") or {})
        bid = props.get("building_id")
        if bid not in population:
            continue
        props["class"] = BUILDING
        features.append({"type": "Feature", "properties": props, "geometry": feat["geometry"]})
    if len(features) != len(population):
        got = {f["properties"]["building_id"] for f in features}
        missing = sorted(population - got)
        raise RuntimeError(f"footprint overlay missing {len(missing)} buildings: {missing[:5]}")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps({"type": "FeatureCollection", "features": features}, ensure_ascii=False),
        encoding="utf-8",
    )
    return len(features)


def npz_to_laz(npz_path: Path, laz_path: Path) -> dict[str, Any]:
    import laspy
    import numpy as np

    with np.load(npz_path) as data:
        if "P_utm" not in data:
            raise RuntimeError(f"{npz_path} has no P_utm array")
        points = np.asarray(data["P_utm"], dtype=np.float64)
    if points.ndim != 2 or points.shape[1] != 3:
        raise RuntimeError(f"{npz_path} P_utm shape is {points.shape}, expected Nx3")
    laz_path.parent.mkdir(parents=True, exist_ok=True)
    hdr = laspy.LasHeader(point_format=6, version="1.4")
    mins = points.min(axis=0)
    hdr.offsets = [float(math.floor(v)) for v in mins]
    hdr.scales = [0.001, 0.001, 0.001]
    las = laspy.LasData(hdr)
    las.x = points[:, 0]
    las.y = points[:, 1]
    las.z = points[:, 2]
    las.write(str(laz_path))
    return {
        "n_points": int(len(points)),
        "z_min": float(points[:, 2].min()) if len(points) else None,
        "z_max": float(points[:, 2].max()) if len(points) else None,
        "x_min": float(points[:, 0].min()) if len(points) else None,
        "x_max": float(points[:, 0].max()) if len(points) else None,
        "y_min": float(points[:, 1].min()) if len(points) else None,
        "y_max": float(points[:, 1].max()) if len(points) else None,
    }


def classify_laz(raw_laz: Path, overlay_geojson: Path, classified_laz: Path, pipeline_json: Path, log_path: Path) -> dict[str, int]:
    import laspy
    import numpy as np

    pipe = {
        "pipeline": [
            {"type": "readers.las", "filename": str(raw_laz)},
            {"type": "filters.smrf", **SMRF},
            {
                "type": "filters.overlay",
                "dimension": "Classification",
                "datasource": str(overlay_geojson),
                "column": "class",
                "where": f"Classification != {GROUND}",
            },
            {
                "type": "writers.las",
                "filename": str(classified_laz),
                "a_srs": "EPSG:25832",
                "minor_version": 4,
                "dataformat_id": 3,
            },
        ]
    }
    pipeline_json.parent.mkdir(parents=True, exist_ok=True)
    pipeline_json.write_text(json.dumps(pipe, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    run(["pdal", "pipeline", str(pipeline_json)], log_path=log_path)
    las = laspy.read(str(classified_laz))
    values, counts = np.unique(np.asarray(las.classification, dtype=np.uint8), return_counts=True)
    return {str(int(k)): int(v) for k, v in zip(values, counts)}


def write_config(run_dir: Path, arm: str, npz_path: Path, raw_stats: dict[str, Any], class_counts: dict[str, int]) -> None:
    config = {
        "task": "E5-A4-baseline-reinforcement",
        "arm": arm,
        "input_label": ARM_LABELS[arm],
        "crs": "EPSG:25832",
        "run_dir": str(run_dir),
        "population": str(POPULATION),
        "building_count": len(read_population()),
        "npz_input": str(npz_path),
        "npz_sha256": sha256_file(npz_path),
        "raw_laz": str(run_dir / "input" / f"{arm}_raw.laz"),
        "classified_laz": str(run_dir / "classified" / f"{arm}_classified.laz"),
        "footprint_overlay": str(run_dir / "input" / "footprints_overlay_class6.geojson"),
        "roofer_footprints": str(FOOTPRINTS_GPKG),
        "roofer_bbox_epsg25832": list(ROOFER_BBOX),
        "pointcloudification": "raw point cloud -> LAS -> SMRF ground -> footprint overlay building class 6",
        "label_method": "SMRF + boundary rule (P0 T4); non-ground inside footprint becomes building class 6",
        "roofer": {
            "mode": "default parameter family",
            "only_plumbing_options": ["--id-attribute building_id", "--box full E5 AOI"],
            "expected_default_readout": "eps0.3/minpts15/complexity0.888 계열",
        },
        "geoid_flag": "E5 canonical +45.7 for raw orthometric sources; sparse local+604 uses no geoid",
        "z_datum_history": z_history_for_arm(arm),
        "smrf": SMRF,
        "raw_stats": raw_stats,
        "class_counts_after_overlay": class_counts,
    }
    (run_dir / "config.yaml").write_text(to_yaml(config), encoding="utf-8")


def z_history_for_arm(arm: str) -> str:
    if arm == "raw_acmp":
        return "ACMP source acmp_aoi_utm.laz orthometric; tum_mob_raw_to_npz.py E5 adds +45.7 m; classified LAS uses ellipsoidal UTM"
    if arm == "raw_sparse":
        return "COLMAP sparse points3D local frame + [690953,5336071,604]; no geoid term; classified LAS uses ellipsoidal UTM"
    raise AssertionError(arm)


def write_versions(run_dir: Path, arm: str, phase: str) -> None:
    lines = [
        f"run_id: {run_dir.name}",
        f"task: E5-A4-baseline-{arm}",
        f"phase: {phase}",
        f"created_utc: {datetime.now(timezone.utc).isoformat()}",
        "crs: EPSG:25832",
        f"git_head: {capture(['git', 'rev-parse', 'HEAD'])}",
        f"git_branch: {capture(['git', 'branch', '--show-current'])}",
        "docker_image: jointbuildgs-p0-tools:t0",
        f"python: {capture(['python3', '--version'])}",
        f"pdal: {capture(['pdal', '--version'])}",
        f"val3dity: {capture(['val3dity', '--version'])}",
        "",
        "fingerprint:",
        f"  config: {run_dir / 'config.yaml'}",
        "  ckpt_sha256: not_applicable_baseline_no_training",
        "  pointcloudification: raw point cloud -> LAS -> SMRF + footprint overlay",
        "  label_method: original point cloud + SMRF/boundary rule",
        f"  geoid_flag: {z_history_for_arm(arm)}",
        f"  timestamp_utc: {datetime.now(timezone.utc).isoformat()}",
    ]
    (run_dir / "versions.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")


def prepare(args: argparse.Namespace) -> None:
    arm = args.arm
    run_dir = RUN_ROOT / args.run_id
    npz_path = Path(args.npz)
    if arm not in ARM_LABELS:
        raise RuntimeError(f"unknown arm: {arm}")
    if not npz_path.exists():
        raise FileNotFoundError(npz_path)
    for sub in ("input", "classified", "logs", "roofer", "cityjson", "val3dity"):
        (run_dir / sub).mkdir(parents=True, exist_ok=True)
    overlay = run_dir / "input/footprints_overlay_class6.geojson"
    n_features = write_overlay_geojson(overlay, set(read_population()))
    print(f"[overlay] features={n_features} -> {overlay}")
    raw_laz = run_dir / "input" / f"{arm}_raw.laz"
    classified_laz = run_dir / "classified" / f"{arm}_classified.laz"
    raw_stats = npz_to_laz(npz_path, raw_laz)
    class_counts = classify_laz(
        raw_laz,
        overlay,
        classified_laz,
        run_dir / "classified" / f"{arm}_classify_pipeline.json",
        run_dir / "logs" / "pdal_classify.log",
    )
    write_config(run_dir, arm, npz_path, raw_stats, class_counts)
    write_versions(run_dir, arm, "prepare")
    print(json.dumps({"run_dir": str(run_dir), "raw_stats": raw_stats, "class_counts": class_counts}, indent=2))


def combine_cityjsonseq(jsonl_files: list[Path], output: Path) -> None:
    top: dict[str, Any] | None = None
    cityobjects: dict[str, Any] = {}
    vertices: list[list[int]] = []
    extent = [math.inf, math.inf, math.inf, -math.inf, -math.inf, -math.inf]
    for path in jsonl_files:
        with path.open("r", encoding="utf-8") as fh:
            header = json.loads(fh.readline())
            if top is None:
                top = header
                top["CityObjects"] = {}
                top["vertices"] = []
            source_transform = header.get("transform")
            target_transform = top.get("transform")
            for line in fh:
                if not line.strip():
                    continue
                feature = json.loads(line)
                converted_vertices = convert_vertices(feature.get("vertices", []), source_transform, target_transform)
                offset = len(vertices)
                vertices.extend(converted_vertices)
                for obj_id, obj in feature.get("CityObjects", {}).items():
                    if obj_id in cityobjects:
                        raise RuntimeError(f"Duplicate CityObject id while merging Roofer output: {obj_id}")
                    shift_cityobject_boundaries(obj, offset)
                    cityobjects[obj_id] = obj
                    obj_extent = obj.get("geographicalExtent")
                    if obj_extent and len(obj_extent) == 6:
                        extent = [
                            min(extent[0], float(obj_extent[0])),
                            min(extent[1], float(obj_extent[1])),
                            min(extent[2], float(obj_extent[2])),
                            max(extent[3], float(obj_extent[3])),
                            max(extent[4], float(obj_extent[4])),
                            max(extent[5], float(obj_extent[5])),
                        ]
    if top is None:
        raise RuntimeError("No CityJSONSeq input files were provided")
    top["CityObjects"] = cityobjects
    top["vertices"] = vertices
    if all(math.isfinite(v) for v in extent):
        top.setdefault("metadata", {})["geographicalExtent"] = extent
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(top, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")


def convert_vertices(
    vertices: list[list[int | float]],
    source_transform: dict[str, list[float]] | None,
    target_transform: dict[str, list[float]] | None,
) -> list[list[int]]:
    if source_transform == target_transform:
        return [[int(round(coord)) for coord in vertex] for vertex in vertices]
    if not source_transform or not target_transform:
        raise RuntimeError("Cannot merge CityJSONSeq tiles with missing transform metadata")
    src_scale = source_transform["scale"]
    src_translate = source_transform["translate"]
    dst_scale = target_transform["scale"]
    dst_translate = target_transform["translate"]
    converted = []
    for vertex in vertices:
        absolute = [float(vertex[i]) * src_scale[i] + src_translate[i] for i in range(3)]
        converted.append([int(round((absolute[i] - dst_translate[i]) / dst_scale[i])) for i in range(3)])
    return converted


def shift_cityobject_boundaries(obj: dict[str, Any], offset: int) -> None:
    for geom in obj.get("geometry", []):
        if "boundaries" in geom:
            geom["boundaries"] = shift_boundary_indices(geom["boundaries"], offset)


def shift_boundary_indices(value: Any, offset: int) -> Any:
    if isinstance(value, int):
        return value + offset
    if isinstance(value, list):
        return [shift_boundary_indices(item, offset) for item in value]
    return value


def parse_roofer_features(jsonl_files: list[Path]) -> dict[str, dict[str, Any]]:
    by_id: dict[str, dict[str, Any]] = {}
    for path in jsonl_files:
        with path.open("r", encoding="utf-8") as fh:
            next(fh)
            for line in fh:
                if not line.strip():
                    continue
                feature = json.loads(line)
                feature_id = str(feature.get("id", ""))
                objects = feature.get("CityObjects", {})
                building = objects.get(feature_id)
                if not building:
                    building = next((obj for obj in objects.values() if obj.get("type") == "Building"), None)
                if not building:
                    continue
                attrs = building.get("attributes", {})
                by_id[feature_id] = {
                    "attributes": attrs,
                    "has_lod22": has_lod22_geometry(objects),
                    "jsonl_file": path.name,
                }
    return by_id


def has_lod22_geometry(objects: dict[str, Any]) -> bool:
    for obj in objects.values():
        for geom in obj.get("geometry", []):
            if str(geom.get("lod")) == "2.2":
                return True
    return False


def classify_reason(
    attrs: dict[str, Any],
    has_roofer: bool,
    val_valid: bool,
    has_val_report: bool,
    has_lod22: bool,
) -> tuple[str, str]:
    if not has_roofer:
        return "failure", "missing_roofer_output"
    if attrs.get("rf_success") is False:
        return "failure", "roofer_unsuccessful"
    if attrs.get("rf_pointcloud_unusable") is True:
        roof_type = str(attrs.get("rf_roof_type", ""))
        if roof_type == "no points":
            return "failure", "pointcloud_unusable_no_points"
        if roof_type == "no planes":
            return "failure", "pointcloud_unusable_no_planes"
        return "failure", "pointcloud_unusable"
    extrusion = str(attrs.get("rf_extrusion_mode", ""))
    if extrusion == "skip":
        return "failure", "roofer_skip_no_3d_geometry"
    if extrusion == "lod11_fallback":
        return "failure", "lod11_fallback"
    if not has_lod22:
        return "failure", "missing_lod22_geometry"
    if not has_val_report:
        return "failure", "missing_val3dity_report"
    if not val_valid:
        return "failure", "val3dity_invalid"
    return "success", "success"


def format_float(value: Any) -> str:
    if value is None or value == "":
        return ""
    try:
        return f"{float(value):.6f}"
    except (TypeError, ValueError):
        return str(value)


def classify_buildings(
    label: str,
    expected_ids: list[str],
    roofer_by_id: dict[str, dict[str, Any]],
    val_by_id: dict[str, dict[str, Any]],
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for building_id in expected_ids:
        roofer = roofer_by_id.get(building_id)
        val = val_by_id.get(building_id)
        attrs = roofer["attributes"] if roofer else {}
        val_valid = bool(val.get("validity")) if val else False
        val_errors = json.dumps(val.get("errors", []), ensure_ascii=False, separators=(",", ":")) if val else ""
        has_lod22 = bool(roofer.get("has_lod22")) if roofer else False
        status, reason = classify_reason(attrs, bool(roofer), val_valid, bool(val), has_lod22)
        rows.append(
            {
                "input": label,
                "building_id": building_id,
                "status": status,
                "reason": reason,
                "rf_success": str(attrs.get("rf_success", "")),
                "rf_extrusion_mode": str(attrs.get("rf_extrusion_mode", "")),
                "rf_pointcloud_unusable": str(attrs.get("rf_pointcloud_unusable", "")),
                "rf_roof_type": str(attrs.get("rf_roof_type", "")),
                "rf_pt_density": format_float(attrs.get("rf_pt_density")),
                "rf_nodata_frac": format_float(attrs.get("rf_nodata_frac")),
                "rf_rmse_lod22": format_float(attrs.get("rf_rmse_lod22")),
                "rf_roof_planes": str(attrs.get("rf_roof_planes", "")),
                "has_lod22": str(has_lod22),
                "val3dity_valid": str(val_valid) if val else "",
                "val3dity_errors": val_errors,
            }
        )
    return rows


def write_status_csv(path: Path, rows: list[dict[str, str]]) -> None:
    if not rows:
        raise RuntimeError("No building status rows to write")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def postprocess(args: argparse.Namespace) -> None:
    arm = args.arm
    run_dir = RUN_ROOT / args.run_id
    label = ARM_LABELS[arm]
    jsonl_dir = run_dir / "roofer" / arm
    jsonl_files = sorted(jsonl_dir.glob("*.city.jsonl"))
    if not jsonl_files:
        raise RuntimeError(f"No Roofer CityJSONSeq files found in {jsonl_dir}")
    cityjson = run_dir / "cityjson" / f"{arm}_roofer.city.json"
    val_report = run_dir / "val3dity" / f"{arm}_val3dity_report.json"
    val_log = run_dir / "logs" / "val3dity.log"
    combine_cityjsonseq(jsonl_files, cityjson)
    run(["val3dity", str(cityjson), "--report", str(val_report)], log_path=val_log)
    val_payload = json.loads(val_report.read_text(encoding="utf-8"))
    val_by_id = {
        str(feature.get("id")): feature
        for feature in val_payload.get("features", [])
        if feature.get("id") is not None
    }
    roofer_by_id = parse_roofer_features(jsonl_files)
    rows = classify_buildings(label, read_population(), roofer_by_id, val_by_id)
    status_csv = run_dir / "building_reconstruction_status.csv"
    write_status_csv(status_csv, rows)
    summary = {
        "run_id": run_dir.name,
        "arm": arm,
        "input_label": label,
        "status_csv": str(status_csv),
        "cityjson": str(cityjson),
        "val3dity_report": str(val_report),
        "reason_counts": dict(Counter(row["reason"] for row in rows)),
        "status_counts": dict(Counter(row["status"] for row in rows)),
        "val3dity": {
            "validity": bool(val_payload.get("validity", False)),
            "feature_total": int(sum(item.get("total", 0) for item in val_payload.get("features_overview", []))),
            "feature_valid": int(sum(item.get("valid", 0) for item in val_payload.get("features_overview", []))),
        },
    }
    (run_dir / f"{arm}_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_versions(run_dir, arm, "postprocess")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


def manifest(args: argparse.Namespace) -> None:
    import numpy as np

    rows = read_csv_rows(POPULATION)
    attr = read_csv_rows(Path(args.attributes))
    by_key = {(r["building_id"], r["arm"]): r for r in attr}
    out = []
    for row in rows:
        bid = row["building_id"]
        dense = by_key.get((bid, "raw_dense"), {})
        lidar = by_key.get((bid, "raw_lidar"), {})
        out.append(
            {
                "building_id": bid,
                "footprint_area_m2": float(row["footprint_area_m2"]),
                "n_views_total": int(float(row.get("n_views_total") or 0)),
                "dense_has_points": int(float(dense.get("n_points_footprint") or 0)) > 0,
                "dense_status_reason": dense.get("density_reason", "missing_attr"),
                "raw_lidar_roof_density_pps_m2": none_float(lidar.get("pt_density_m2")),
                "ref_roof_surface_count": int(float(lidar.get("ref_roof_surface_count") or 0)),
            }
        )
    Path(args.out).write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"rows": len(out), "out": args.out}, ensure_ascii=False))
    _ = np  # keeps numpy import visible in versions when run under py_compile checks


def none_float(value: str | None) -> float | None:
    if value is None or value == "" or str(value).lower() == "none":
        return None
    try:
        return float(value)
    except ValueError:
        return None


def collect_cell_samples(
    path: Path,
    z_add: float,
    ground_only: bool,
    max_per_cell: int = 600,
    max_chunk_samples: int = 40_000,
) -> dict[tuple[int, int], list[float]]:
    import laspy
    import numpy as np

    cells: dict[tuple[int, int], list[float]] = {}
    with laspy.open(str(path)) as reader:
        for points in reader.chunk_iterator(1_000_000):
            x = np.asarray(points.x)
            y = np.asarray(points.y)
            z = np.asarray(points.z) + z_add
            if ground_only:
                cls = np.asarray(points.classification)
                mask = cls == GROUND
                x, y, z = x[mask], y[mask], z[mask]
            if len(z) > max_chunk_samples:
                pick = np.linspace(0, len(z) - 1, max_chunk_samples, dtype=np.int64)
                x, y, z = x[pick], y[pick], z[pick]
            ix = np.floor(x / 5.0).astype(np.int64)
            iy = np.floor(y / 5.0).astype(np.int64)
            for cx, cy, zz in zip(ix.tolist(), iy.tolist(), z.tolist()):
                key = (cx, cy)
                bucket = cells.setdefault(key, [])
                if len(bucket) < max_per_cell:
                    bucket.append(float(zz))
    return cells


def preflight(args: argparse.Namespace) -> None:
    import numpy as np

    acmp_cells = collect_cell_samples(ACMP_SOURCE, 45.7, ground_only=False)
    als_cells = collect_cell_samples(ALS_SOURCE, 45.7, ground_only=True)
    rows = []
    diffs = []
    for key in sorted(set(acmp_cells).intersection(als_cells)):
        if len(acmp_cells[key]) < 40 or len(als_cells[key]) < 20:
            continue
        acmp_q10 = float(np.percentile(acmp_cells[key], 10))
        als_med = float(np.median(als_cells[key]))
        diff = acmp_q10 - als_med
        rows.append((key, acmp_q10, als_med, diff, len(acmp_cells[key]), len(als_cells[key])))
        diffs.append(diff)
    if not rows:
        raise RuntimeError("no overlapping ACMP/ALS ground-patch cells for preflight")
    rows.sort(key=lambda item: abs(item[3]))
    best = rows[:8]
    diffs_arr = np.asarray(diffs, dtype=np.float64)
    lines = [
        "# E5 A4 Baseline Preflight",
        "",
        "> 분류·관찰 재료만 기록한다. CRS는 EPSG:25832.",
        "",
        "## 높이 이력",
        "",
        "| 입력 | 원천 | 신규 실행 높이 처리 | 이중 적용 확인 |",
        "|---|---|---|---|",
        f"| raw-ACMP | `{ACMP_SOURCE}` | orthometric source +45.7 m in `tum_mob_raw_to_npz.py` | 신규 NPZ 생성 경로에서만 적용 |",
        f"| raw-sparse | `{SPARSE_SOURCE}` | COLMAP local +604 m, geoid 미개입 | +45.7 미적용 |",
        f"| ALS reference patch | `{ALS_SOURCE}` | orthometric source +45.7 m for patch comparison | 조립 입력 아님 |",
        "",
        "## 지면 패치 확인",
        "",
        f"- 격자: 5 m cell. ACMP는 cell z 10 분위, ALS는 ground(class 2) median을 비교했다.",
        f"- 전체 겹침 cell 수: {len(diffs)}. diff median={float(np.median(diffs_arr)):.3f} m, "
        f"IQR={float(np.percentile(diffs_arr,25)):.3f}..{float(np.percentile(diffs_arr,75)):.3f} m.",
        "",
        "| cell_ix | cell_iy | ACMP q10 z | ALS ground median z | diff m | n_acmp_sample | n_als_ground |",
        "|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for (cx, cy), acmp_q10, als_med, diff, na, nl in best:
        lines.append(f"| {cx} | {cy} | {acmp_q10:.3f} | {als_med:.3f} | {diff:.3f} | {na} | {nl} |")
    lines += [
        "",
        "## 관찰",
        "",
        "- 위 표의 best patch들은 +45.7 m 적용 후 ACMP 낮은 표면과 ALS 지면이 서브미터 범위에서 맞는 위치다.",
        "- 전체 cell diff는 지붕·수목·매칭 잡음이 섞인 관찰 재료이며, 여기서 판정하지 않는다.",
    ]
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"out": args.out, "cells": len(diffs), "best_abs_diff_m": abs(best[0][3])}, ensure_ascii=False))


def build_argparser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    m = sub.add_parser("manifest")
    m.add_argument("--attributes", default="docs/evidence/archive/pointcloud_attributes/v1_2/tables/pointcloud_attributes_v1_2.csv")
    m.add_argument("--out", default="docs/experiments/pilots/e5_pilot/manifests/e5_baselines_199_manifest.json")

    pf = sub.add_parser("preflight")
    pf.add_argument("--out", default="docs/experiments/pilots/e5_pilot/reports/e5_baseline_preflight.md")

    prep = sub.add_parser("prepare")
    prep.add_argument("--arm", required=True, choices=sorted(ARM_LABELS))
    prep.add_argument("--run-id", required=True)
    prep.add_argument("--npz", required=True)

    post = sub.add_parser("postprocess")
    post.add_argument("--arm", required=True, choices=sorted(ARM_LABELS))
    post.add_argument("--run-id", required=True)
    return parser


def main() -> None:
    args = build_argparser().parse_args()
    if args.cmd == "manifest":
        manifest(args)
    elif args.cmd == "preflight":
        preflight(args)
    elif args.cmd == "prepare":
        prepare(args)
    elif args.cmd == "postprocess":
        postprocess(args)
    else:
        raise AssertionError(args.cmd)


if __name__ == "__main__":
    main()
