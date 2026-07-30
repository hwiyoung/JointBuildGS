#!/usr/bin/env python3
"""Prepare read-only point/roof caches for the TUM2TWIN R_v1 pipeline.

Run this script in ``jointbuildgs-p0-tools:t0``.  It reuses the repository's
chunked LAS crop pattern and E5 roof parser while keeping all writes under the
new nightly report root.  Source size/mtime snapshots are asserted unchanged.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import os
import sys
from collections import defaultdict, deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import laspy
import numpy as np
from lxml import etree
from shapely import contains_xy
from shapely.geometry import Polygon, shape


REPO = Path(__file__).resolve().parents[3]
E5_DIR = REPO / "scripts/e5_c001"
for import_path in (REPO, E5_DIR):
    if str(import_path) not in sys.path:
        sys.path.insert(0, str(import_path))

import e5_c001_8way as e5  # noqa: E402


def now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat()


def atomic_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=True) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def atomic_npz(path: Path, **arrays: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("wb") as handle:
        np.savez_compressed(handle, **arrays)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def read_config(path: Path) -> dict[str, Any]:
    # The checked-in .yaml is deliberately JSON-compatible YAML, so the P0
    # image does not need PyYAML or any newly installed dependency.
    return json.loads(path.read_text(encoding="utf-8"))


def source_snapshot(paths: Iterable[Path]) -> dict[str, dict[str, int]]:
    result: dict[str, dict[str, int]] = {}
    for path in paths:
        stat = path.stat()
        result[str(path)] = {"size": int(stat.st_size), "mtime_ns": int(stat.st_mtime_ns)}
    return result


def load_population(config: dict[str, Any]) -> list[str]:
    source = REPO / config["sources"]["population_manifest"]
    arm = config["sources"]["population_arm"]
    rows = list(csv.DictReader(source.open(newline="", encoding="utf-8")))
    ids = sorted(
        row["building_id"]
        for row in rows
        if row.get("arm") == arm
        and str(row.get("assembled", "")).strip().lower() in {"true", "1", "yes"}
    )
    if len(ids) != 178 or len(set(ids)) != 178:
        raise RuntimeError(f"canonical population drift: rows={len(ids)} unique={len(set(ids))}")
    return ids


def load_footprints(config: dict[str, Any], ids: list[str]) -> dict[str, Polygon]:
    source = REPO / config["sources"]["footprints"]
    id_field = config["sources"]["footprint_id_field"]
    payload = json.loads(source.read_text(encoding="utf-8"))
    wanted = set(ids)
    footprints: dict[str, Polygon] = {}
    for feature in payload.get("features", []):
        building_id = str((feature.get("properties") or {}).get(id_field, ""))
        if building_id not in wanted:
            continue
        geometry = shape(feature["geometry"])
        if geometry.geom_type == "MultiPolygon":
            geometry = max(geometry.geoms, key=lambda value: value.area)
        if geometry.geom_type != "Polygon" or geometry.is_empty or geometry.area <= 0:
            continue
        footprints[building_id] = geometry
    missing = sorted(wanted - set(footprints))
    if missing:
        raise RuntimeError(f"missing canonical footprints: {missing}")
    return footprints


def bool_value(value: Any) -> bool:
    return str(value).strip().lower() in {"true", "1", "yes", "y"}


def load_dim_status(config: dict[str, Any], ids: list[str]) -> dict[str, dict[str, str]]:
    path = REPO / config["sources"]["roofer_status"]
    label = config["sources"]["roofer_input_label"]
    wanted = set(ids)
    result: dict[str, dict[str, str]] = {}
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if row.get("input") == label and row.get("building_id") in wanted:
                result[row["building_id"]] = row
    return result


def global_bounds(footprints: dict[str, Polygon], buffer_m: float) -> tuple[float, float, float, float]:
    bounds = [polygon.bounds for polygon in footprints.values()]
    return (
        min(value[0] for value in bounds) - buffer_m,
        min(value[1] for value in bounds) - buffer_m,
        max(value[2] for value in bounds) + buffer_m,
        max(value[3] for value in bounds) + buffer_m,
    )


def load_scene(
    paths: list[Path],
    bounds: tuple[float, float, float, float],
    chunk_size: int,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    minx, miny, maxx, maxy = bounds
    xs: list[np.ndarray] = []
    ys: list[np.ndarray] = []
    zs: list[np.ndarray] = []
    classes: list[np.ndarray] = []
    for path in paths:
        with laspy.open(path) as reader:
            for points in reader.chunk_iterator(chunk_size):
                x = np.asarray(points.x, dtype=np.float64)
                y = np.asarray(points.y, dtype=np.float64)
                classification = np.asarray(points.classification, dtype=np.uint8)
                mask = (
                    (x >= minx)
                    & (x <= maxx)
                    & (y >= miny)
                    & (y <= maxy)
                    & ((classification == 2) | (classification == 6))
                )
                if not np.any(mask):
                    continue
                xs.append(x[mask])
                ys.append(y[mask])
                zs.append(np.asarray(points.z, dtype=np.float64)[mask])
                classes.append(classification[mask])
    if not xs:
        return (
            np.empty(0, dtype=np.float64),
            np.empty(0, dtype=np.float64),
            np.empty(0, dtype=np.float64),
            np.empty(0, dtype=np.uint8),
        )
    x = np.concatenate(xs)
    order = np.argsort(x, kind="mergesort")
    return x[order], np.concatenate(ys)[order], np.concatenate(zs)[order], np.concatenate(classes)[order]


def crop_building(
    scene: tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray],
    polygon: Polygon,
    buffer_m: float,
) -> dict[str, np.ndarray]:
    x, y, z, classification = scene
    buffered = polygon.buffer(buffer_m)
    minx, miny, maxx, maxy = buffered.bounds
    left = int(np.searchsorted(x, minx, side="left"))
    right = int(np.searchsorted(x, maxx, side="right"))
    if right <= left:
        return {
            "xyz": np.empty((0, 3), dtype=np.float64),
            "classification": np.empty(0, dtype=np.uint8),
            "inside": np.empty(0, dtype=bool),
        }
    local_y = y[left:right]
    bbox = (local_y >= miny) & (local_y <= maxy)
    idx = np.nonzero(bbox)[0] + left
    if not len(idx):
        return {
            "xyz": np.empty((0, 3), dtype=np.float64),
            "classification": np.empty(0, dtype=np.uint8),
            "inside": np.empty(0, dtype=bool),
        }
    keep = contains_xy(buffered, x[idx], y[idx])
    idx = idx[keep]
    xyz = np.column_stack([x[idx], y[idx], z[idx]])
    inside = contains_xy(polygon, xyz[:, 0], xyz[:, 1]) if len(xyz) else np.empty(0, dtype=bool)
    return {"xyz": xyz, "classification": classification[idx], "inside": inside}


def parse_reference_roofs(
    lod2_dir: Path, target_ids: set[str]
) -> dict[str, list[e5.RoofSurface]]:
    # Same parser/extractor as e5_c001_8way, but missing roofs remain empty so
    # one malformed reference cannot abort the unattended population batch.
    output: dict[str, list[e5.RoofSurface]] = {building_id: [] for building_id in target_ids}
    for path in sorted(lod2_dir.glob("*.gml")):
        for _event, elem in etree.iterparse(str(path), events=("end",), recover=True):
            if e5.local_name(elem.tag) != "Building":
                continue
            building_id = e5.gml_id(elem)
            if building_id in target_ids:
                output[building_id].extend(e5.extract_gml_roof_surfaces(building_id, elem))
            elem.clear()
            parent = elem.getparent()
            while parent is not None and elem.getprevious() is not None:
                del parent[0]
    return output


def strict_overlap_edges(
    refs: list[e5.RoofSurface],
    preds: list[e5.RoofSurface],
    threshold: float,
) -> list[dict[str, Any]]:
    edges: list[dict[str, Any]] = []
    for ref_idx, ref in enumerate(refs):
        ref_area = float(ref.polygon.area)
        for pred_idx, pred in enumerate(preds):
            pred_area = float(pred.polygon.area)
            if ref_area <= 0 or pred_area <= 0:
                continue
            intersection = ref.polygon.intersection(pred.polygon)
            overlap = float(intersection.area)
            ref_fraction = overlap / ref_area
            pred_fraction = overlap / pred_area
            if ref_fraction < threshold or pred_fraction < threshold:
                continue
            union = float(ref.polygon.union(pred.polygon).area)
            iou = overlap / union if union > 0 else 0.0
            edges.append(
                {
                    "ref_idx": ref_idx,
                    "pred_idx": pred_idx,
                    "overlap_m2": overlap,
                    "ref_overlap_fraction": ref_fraction,
                    "pred_overlap_fraction": pred_fraction,
                    "iou": iou,
                }
            )
    return edges


def greedy_matches(edges: list[dict[str, Any]]) -> list[dict[str, Any]]:
    used_ref: set[int] = set()
    used_pred: set[int] = set()
    matches: list[dict[str, Any]] = []
    for edge in sorted(edges, key=lambda value: (value["iou"], value["overlap_m2"]), reverse=True):
        if edge["ref_idx"] in used_ref or edge["pred_idx"] in used_pred:
            continue
        used_ref.add(edge["ref_idx"])
        used_pred.add(edge["pred_idx"])
        matches.append(edge)
    return matches


def topology_counts(edges: list[dict[str, Any]], ref_n: int, pred_n: int) -> dict[str, Any]:
    ref_degree = [0] * ref_n
    pred_degree = [0] * pred_n
    adjacency: dict[tuple[str, int], list[tuple[str, int]]] = defaultdict(list)
    for edge in edges:
        ref_idx, pred_idx = int(edge["ref_idx"]), int(edge["pred_idx"])
        ref_degree[ref_idx] += 1
        pred_degree[pred_idx] += 1
        adjacency[("r", ref_idx)].append(("p", pred_idx))
        adjacency[("p", pred_idx)].append(("r", ref_idx))
    over_count = sum(value > 1 for value in ref_degree)
    under_count = sum(value > 1 for value in pred_degree)
    mixed_count = 0
    seen: set[tuple[str, int]] = set()
    for node in list(adjacency):
        if node in seen:
            continue
        queue = deque([node])
        component: set[tuple[str, int]] = set()
        while queue:
            current = queue.popleft()
            if current in component:
                continue
            component.add(current)
            queue.extend(adjacency[current])
        seen.update(component)
        n_ref = sum(kind == "r" for kind, _idx in component)
        n_pred = sum(kind == "p" for kind, _idx in component)
        if n_ref > 1 and n_pred > 1:
            mixed_count += 1
    return {
        "overseg_1_to_m_count": over_count,
        "overseg_1_to_m_rate": over_count / ref_n if ref_n else math.nan,
        "underseg_n_to_1_count": under_count,
        "underseg_n_to_1_rate": under_count / pred_n if pred_n else math.nan,
        "mixed_n_to_m_count": mixed_count,
        "mixed_n_to_m_rate": mixed_count / max(ref_n, 1),
    }


def roof_metrics(
    refs: list[e5.RoofSurface],
    preds: list[e5.RoofSurface],
    threshold: float,
) -> dict[str, Any]:
    edges = strict_overlap_edges(refs, preds, threshold)
    matches = greedy_matches(edges)
    ref_n, pred_n, match_n = len(refs), len(preds), len(matches)
    completeness = match_n / ref_n if ref_n else math.nan
    correctness = match_n / pred_n if pred_n else math.nan
    f1 = (
        2.0 * completeness * correctness / (completeness + correctness)
        if math.isfinite(completeness)
        and math.isfinite(correctness)
        and completeness + correctness > 0
        else (0.0 if ref_n and pred_n else math.nan)
    )
    distance = e5.reference_distance(preds, refs) if refs and preds else {
        "ref_rms_m": None,
        "ref_hausdorff_m": None,
        "ref_distance_samples": 0,
    }
    xy_values = [
        refs[int(edge["ref_idx"])].polygon.hausdorff_distance(
            preds[int(edge["pred_idx"])].polygon
        )
        for edge in matches
    ]
    result = {
        "reference_roof_plane_count": ref_n,
        "reconstructed_roof_plane_count": pred_n,
        "roof_plane_match_count": match_n,
        "roof_plane_completeness": completeness,
        "roof_plane_correctness": correctness,
        "roof_plane_f1": f1,
        "roof_plane_quality": f1,
        "rmsz_m": distance.get("ref_rms_m"),
        "roof_hausdorff_z_m": distance.get("ref_hausdorff_m"),
        "roof_distance_samples": distance.get("ref_distance_samples", 0),
        "rmsxy_m": float(np.sqrt(np.mean(np.square(xy_values)))) if xy_values else math.nan,
        "ridge_position_error_m": math.nan,
        "ridge_position_error_reason": "explicit ridge correspondence evaluator not found",
        "output_reference_roof_face_ratio": pred_n / ref_n if ref_n else math.nan,
        "correspondence_overlap_threshold": threshold,
        "correspondence_definition": "intersection/reference_area>=q and intersection/reconstruction_area>=q",
        **topology_counts(edges, ref_n, pred_n),
    }
    return result


def prepare_roof_cache(
    config: dict[str, Any],
    ids: list[str],
    cache_root: Path,
    footprints: dict[str, Polygon],
) -> None:
    del footprints  # footprint geometry is already encoded in parsed roof polygons
    source = config["sources"]
    threshold = float(config["processing"]["roof_plane_overlap_threshold"])
    target = set(ids)
    refs = parse_reference_roofs(REPO / source["reference_lod2_directory"], target)
    preds = e5.parse_cityjson_roofs(REPO / source["roofer_cityjson"], target)
    status = load_dim_status(config, ids)
    for building_id in ids:
        row = status.get(building_id, {})
        has_lod22 = bool_value(row.get("has_lod22"))
        model_roofs = preds.get(building_id, []) if has_lod22 else []
        values = roof_metrics(refs.get(building_id, []), model_roofs, threshold)
        roofer_success = bool_value(row.get("rf_success")) and not bool_value(
            row.get("rf_pointcloud_unusable")
        )
        values.update(
            {
                "building_id": building_id,
                "roofer_success": roofer_success,
                "roofer_status": row.get("status", "unknown"),
                "roofer_reason": row.get("reason", "missing status row"),
                "has_lod22": has_lod22,
                "val3dity_lod22_valid": (
                    bool_value(row.get("val3dity_valid"))
                    if row.get("val3dity_valid") not in (None, "")
                    else None
                ),
                "rf_pt_density": number_or_nan(row.get("rf_pt_density")),
                "rf_nodata_frac": number_or_nan(row.get("rf_nodata_frac")),
                "rf_rmse_lod22_existing": number_or_nan(row.get("rf_rmse_lod22")),
                "rf_roof_planes_existing": number_or_nan(row.get("rf_roof_planes")),
                "input_provenance": source["roofer_cityjson"],
                "reference_provenance": source["reference_lod2_directory"],
                "adapter_reuse": "e5_c001_8way roof parser, plane fit, and reference_distance",
            }
        )
        atomic_json(cache_root / building_id / "lod2.json", values)


def number_or_nan(value: Any) -> float:
    try:
        parsed = float(value)
        return parsed if math.isfinite(parsed) else math.nan
    except (TypeError, ValueError):
        return math.nan


def cache_complete(cache_root: Path, building_id: str) -> bool:
    root = cache_root / building_id
    return all((root / name).is_file() for name in ("dense.npz", "reference.npz", "lod2.json", "complete.json"))


def prepare(args: argparse.Namespace) -> None:
    config_path = (REPO / args.config).resolve()
    config = read_config(config_path)
    population = load_population(config)
    if args.all:
        ids = population
    else:
        unknown = sorted(set(args.ids) - set(population))
        if unknown:
            raise RuntimeError(f"ids outside canonical population: {unknown}")
        ids = sorted(dict.fromkeys(args.ids))
    if not ids:
        raise RuntimeError("no target building ids")
    output_root = REPO / config["outputs"]["root"]
    cache_root = REPO / config["outputs"]["cache_root"]
    cache_root.mkdir(parents=True, exist_ok=True)
    pending = [building_id for building_id in ids if not (args.resume and cache_complete(cache_root, building_id))]
    if not pending:
        print(f"cache already complete for {len(ids)} buildings", flush=True)
        return
    footprints = load_footprints(config, pending)
    source = config["sources"]
    source_paths = [
        REPO / source["population_manifest"],
        REPO / source["footprints"],
        REPO / source["dense_mvs_pointcloud"],
        *(REPO / value for value in source["surface_reference_pointclouds"]),
        REPO / source["roofer_status"],
        REPO / source["roofer_cityjson"],
        *(REPO / source["reference_lod2_directory"]).glob("*.gml"),
    ]
    missing = [str(path) for path in source_paths if not path.is_file()]
    if missing:
        raise RuntimeError(f"missing source paths: {missing}")
    before = source_snapshot(source_paths)
    processing = config["processing"]
    buffer_m = float(processing["crop_buffer_m"])
    bounds = global_bounds(footprints, buffer_m)
    chunk_size = int(processing["chunk_size_points"])

    print(f"loading dense scene for {len(pending)} buildings bounds={bounds}", flush=True)
    dense_scene = load_scene([REPO / source["dense_mvs_pointcloud"]], bounds, chunk_size)
    for building_id in pending:
        cropped = crop_building(dense_scene, footprints[building_id], buffer_m)
        atomic_npz(cache_root / building_id / "dense.npz", **cropped)
    del dense_scene

    print(f"loading reference scene for {len(pending)} buildings bounds={bounds}", flush=True)
    reference_scene = load_scene(
        [REPO / value for value in source["surface_reference_pointclouds"]],
        bounds,
        chunk_size,
    )
    for building_id in pending:
        cropped = crop_building(reference_scene, footprints[building_id], buffer_m)
        atomic_npz(cache_root / building_id / "reference.npz", **cropped)
        atomic_json(
            cache_root / building_id / "footprint.json",
            {
                "building_id": building_id,
                "area_m2": float(footprints[building_id].area),
                "bounds": list(map(float, footprints[building_id].bounds)),
                "wkt": footprints[building_id].wkt,
                "crs": config["crs"],
                "crop_buffer_m": buffer_m,
            },
        )
    del reference_scene

    print(f"preparing LoD2 adapter cache for {len(pending)} buildings", flush=True)
    prepare_roof_cache(config, pending, cache_root, footprints)
    after = source_snapshot(source_paths)
    if before != after:
        changed = sorted(path for path in before if before[path] != after.get(path))
        raise RuntimeError(f"source file modification detected: {changed}")
    for building_id in pending:
        atomic_json(
            cache_root / building_id / "complete.json",
            {
                "schema": "jointbuildgs.tum2twin_rv1.cache.v1",
                "run_id": config["run_id"],
                "building_id": building_id,
                "created_at": now(),
                "source_files_unchanged": True,
                "source_snapshot": before,
                "cache_role": "derived read-only metric cache",
            },
        )
    atomic_json(
        output_root / "cache_manifest.json",
        {
            "schema": "jointbuildgs.tum2twin_rv1.cache_manifest.v1",
            "run_id": config["run_id"],
            "updated_at": now(),
            "prepared_buildings": pending,
            "requested_buildings": ids,
            "source_files_unchanged": True,
            "source_snapshot": before,
            "container": "jointbuildgs-p0-tools:t0",
            "crs": config["crs"],
        },
    )
    print(f"cache prepared for {len(pending)} buildings", flush=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--all", action="store_true")
    mode.add_argument("--ids", nargs="+")
    parser.add_argument("--resume", action="store_true")
    return parser.parse_args()


if __name__ == "__main__":
    prepare(parse_args())
