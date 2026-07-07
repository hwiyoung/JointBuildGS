#!/usr/bin/env python3
"""E5 C001 GS input/readout diagnostic.

Observation-only over existing C001 products.  This script does not train,
change recipes, or rerun Roofer.  It extends the existing 8-way material with
point-cloud root metrics, video-layer proxies, generation/quality/validity
tables, and figures for the C001 hard block.
"""

from __future__ import annotations

import csv
import json
import math
import os
import shutil
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import matplotlib
import numpy as np
from shapely import contains_xy

matplotlib.use("Agg")
import matplotlib.pyplot as plt

import e5_c001_8way as eight
import pointcloud_attributes_v1 as base
from e5_pilot_gate_tools import C001_IDS, READOUT_STRING


REPO = Path(__file__).resolve().parents[3]
RUN_ID = "20260707_e5_c001_gsdiag"
RUN_DIR = Path("phases/p2-gsjso/runs") / RUN_ID
REPORT_PATH = Path("docs/W_E5_C001_GS진단.md")
FIG_DIR = Path("docs/figs/e5_c001_gsdiag")

PC_METRICS_CSV = Path("docs/e5_c001_gsdiag_pointcloud_metrics.csv")
PC_SUMMARY_CSV = Path("docs/e5_c001_gsdiag_pointcloud_source_summary.csv")
PAIR_DELTA_CSV = Path("docs/e5_c001_gsdiag_pair_deltas.csv")
VIDEO_CSV = Path("docs/e5_c001_gsdiag_video_layer.csv")
GEN_FAILURE_CSV = Path("docs/e5_c001_gsdiag_generation_failures.csv")
SHAPE_CSV = Path("docs/e5_c001_gsdiag_shape_metrics.csv")
FLATTENING_CSV = Path("docs/e5_c001_gsdiag_flattening_location.csv")
VALIDITY_CSV = Path("docs/e5_c001_gsdiag_validity_errors.csv")
VALIDITY_SUMMARY_CSV = Path("docs/e5_c001_gsdiag_validity_error_summary.csv")
ROUTING_CSV = Path("docs/e5_c001_gsdiag_routing.csv")
SUMMARY_CSV = Path("docs/e5_c001_gsdiag_headline_summary.csv")

RNG = np.random.default_rng(20260707)
GRID_CELL_M = 0.50
MAX_DIST_POINTS = 6000
MAX_NORMAL_POINTS = 700
NORMAL_K = 14
FLAT_TILT_DEG = 5.0
LOW_COVERAGE = 0.20
LOW_DENSITY = 1.0
FLAT_CASES = ["DEBY_LOD2_60098", "DEBY_LOD2_4908178", "DEBY_LOD2_4908168"]


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fields: list[str] = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def fmt(value: Any, digits: int = 4) -> str:
    return eight.fmt(value, digits)


def num(value: Any) -> float | None:
    return eight.num(value)


def tf(value: Any) -> bool:
    return eight.tf(value)


def rel(path: Path | str | None) -> str:
    return eight.rel(path)


def safe_float(value: Any, default: float | None = None) -> float | None:
    out = num(value)
    return default if out is None else out


def source_run_order(source_run: str) -> tuple[int, str]:
    return eight.source_order(source_run)


def load_material() -> dict[str, Any]:
    srcs = eight.sources()
    inventory = eight.inventory_rows(srcs)
    missing = [r for r in inventory if r.get("status") == "missing"]
    if missing:
        write_csv(Path("docs/e5_c001_gsdiag_inventory.csv"), inventory)
        raise RuntimeError(f"missing existing C001 products: {missing[:3]}")

    refs, pred = eight.load_reference_and_predictions(srcs)
    status_maps = eight.load_status_maps(srcs)
    lenses = eight.build_lenses()
    metrics = eight.build_metric_rows(srcs, refs, pred, status_maps, lenses)
    source_summary = eight.build_source_summary(metrics)
    footprints = base.load_footprints(eight.FOOTPRINTS_GPKG, set(C001_IDS))
    return {
        "srcs": srcs,
        "inventory": inventory,
        "refs": refs,
        "pred": pred,
        "status_maps": status_maps,
        "lenses": lenses,
        "metrics": metrics,
        "source_summary": source_summary,
        "footprints": footprints,
    }


def grid_coverage(points: np.ndarray, footprint: Any, cell: float = GRID_CELL_M) -> tuple[float | None, int, int]:
    minx, miny, maxx, maxy = footprint.bounds
    xs = np.arange(minx + cell / 2.0, maxx, cell)
    ys = np.arange(miny + cell / 2.0, maxy, cell)
    if not len(xs) or not len(ys):
        return None, 0, 0
    xx, yy = np.meshgrid(xs, ys)
    in_poly = contains_xy(footprint, xx.ravel(), yy.ravel())
    total = int(np.count_nonzero(in_poly))
    if total == 0:
        return None, 0, 0
    nx = len(xs)
    valid_cells = {(int(flat % nx), int(flat // nx)) for flat in np.nonzero(in_poly)[0]}
    if len(points) == 0:
        return 0.0, 0, total
    ix = np.floor((points[:, 0] - minx) / cell).astype(int)
    iy = np.floor((points[:, 1] - miny) / cell).astype(int)
    occupied = {(int(a), int(b)) for a, b in zip(ix, iy)} & valid_cells
    return len(occupied) / total, len(occupied), total


def reference_point_diffs(points: np.ndarray, refs: list[eight.RoofSurface], z_shift: float) -> tuple[np.ndarray, float]:
    if len(points) == 0:
        return np.empty(0, dtype=float), 1.0
    pts = points
    if len(pts) > MAX_DIST_POINTS:
        idx = RNG.choice(len(pts), MAX_DIST_POINTS, replace=False)
        pts = pts[idx]
    pred_z = pts[:, 2] + z_shift
    best_abs = np.full(len(pts), np.inf, dtype=float)
    best_diff = np.full(len(pts), np.nan, dtype=float)
    hit = np.zeros(len(pts), dtype=bool)
    for surf in refs:
        mask = np.zeros(len(pts), dtype=bool)
        for poly in eight.flatten_polygons(surf.polygon):
            mask |= contains_xy(poly, pts[:, 0], pts[:, 1])
        if not np.any(mask):
            continue
        ref_z = surf.z_at(pts[mask, 0], pts[mask, 1])
        diff = pred_z[mask] - ref_z
        absdiff = np.abs(diff)
        sub = np.nonzero(mask)[0]
        take = absdiff < best_abs[sub]
        best_abs[sub[take]] = absdiff[take]
        best_diff[sub[take]] = diff[take]
        hit[sub[take]] = True
    return best_diff[hit], 1.0 - float(np.mean(hit))


def fit_plane_normal(points: np.ndarray) -> np.ndarray | None:
    if len(points) < 3:
        return None
    centered = points - np.mean(points, axis=0)
    try:
        _, _, vh = np.linalg.svd(centered, full_matrices=False)
    except np.linalg.LinAlgError:
        return None
    n = vh[-1]
    norm = np.linalg.norm(n)
    if norm <= 0:
        return None
    n = n / norm
    if n[2] < 0:
        n = -n
    return n


def estimate_normals(points: np.ndarray) -> np.ndarray:
    if len(points) < NORMAL_K:
        return np.empty((0, 3), dtype=float)
    pts = points
    if len(pts) > MAX_NORMAL_POINTS:
        idx = RNG.choice(len(pts), MAX_NORMAL_POINTS, replace=False)
        pts = pts[idx]
    xy = pts[:, :2]
    normals: list[np.ndarray] = []
    for i in range(len(pts)):
        d2 = np.sum((xy - xy[i]) ** 2, axis=1)
        nn = np.argpartition(d2, min(NORMAL_K, len(pts) - 1))[:NORMAL_K]
        normal = fit_plane_normal(pts[nn])
        if normal is not None and np.isfinite(normal).all():
            normals.append(normal)
    if not normals:
        return np.empty((0, 3), dtype=float)
    return np.vstack(normals)


def normal_stats(points: np.ndarray) -> dict[str, Any]:
    if len(points) < NORMAL_K:
        return {
            "normal_count": 0,
            "tilt_p50_deg": "",
            "tilt_p90_deg": "",
            "normal_mode_count": 0,
            "normal_structure": "too_few_points",
        }
    normals = estimate_normals(points)
    if len(normals) == 0:
        return {
            "normal_count": 0,
            "tilt_p50_deg": "",
            "tilt_p90_deg": "",
            "normal_mode_count": 0,
            "normal_structure": "normal_unstable",
        }
    nz = np.clip(normals[:, 2], -1.0, 1.0)
    tilt = np.degrees(np.arccos(nz))
    sloped = tilt >= FLAT_TILT_DEG
    mode_count = 0
    if np.count_nonzero(sloped) >= 20:
        az = (np.degrees(np.arctan2(normals[sloped, 1], normals[sloped, 0])) + 360.0) % 360.0
        hist, _ = np.histogram(az, bins=np.linspace(0, 360, 19))
        threshold = max(5, 0.14 * np.max(hist))
        for j, val in enumerate(hist):
            if val >= threshold and val >= hist[(j - 1) % len(hist)] and val >= hist[(j + 1) % len(hist)]:
                mode_count += 1
    tilt_p50 = float(np.median(tilt))
    tilt_p90 = float(np.percentile(tilt, 90))
    zspan = float(np.percentile(points[:, 2], 90) - np.percentile(points[:, 2], 10))
    if tilt_p90 < 5.0 and zspan < 0.80:
        structure = "flat_single"
    elif mode_count >= 2 and zspan >= 0.80:
        structure = "multi_slope"
    elif tilt_p50 >= 5.0 and zspan >= 0.80:
        structure = "single_slope"
    else:
        structure = "weak_structure"
    return {
        "normal_count": len(normals),
        "tilt_p50_deg": fmt(tilt_p50, 3),
        "tilt_p90_deg": fmt(tilt_p90, 3),
        "normal_mode_count": mode_count,
        "normal_structure": structure,
    }


def pointcloud_metrics(srcs: list[eight.Source], refs: dict[str, list[eight.RoofSurface]], footprints: dict[str, Any]) -> list[dict[str, Any]]:
    cache = eight.PointCloudCache(footprints)
    rows: list[dict[str, Any]] = []
    for src in srcs:
        if src.status_role == "reference":
            continue
        for bid in C001_IDS:
            pts = cache.read_roof_points(src, bid)
            area = float(footprints[bid].area)
            coverage, occupied, total = grid_coverage(pts, footprints[bid])
            diffs, miss_frac = reference_point_diffs(pts, refs[bid], src.z_shift_to_reference_m)
            absdiff = np.abs(diffs)
            nstats = normal_stats(pts)
            zspan = float(np.percentile(pts[:, 2], 90) - np.percentile(pts[:, 2], 10)) if len(pts) else None
            row = {
                "building_id": bid,
                "source_run": src.source_run,
                "source_group": src.source_group,
                "display_label": src.display_label,
                "pair_raw": src.pair_raw or "",
                "seed": src.seed or "",
                "replicate": src.replicate or "",
                "footprint_area_m2": fmt(area, 4),
                "roof_point_count": int(len(pts)),
                "density_pts_m2": fmt(len(pts) / area if area > 0 else None),
                "coverage_frac": fmt(coverage),
                "grid_occupied_cells": occupied,
                "grid_total_cells": total,
                "ref_lookup_miss_frac": fmt(miss_frac),
                "ref_abs_dist_p50_m": fmt(float(np.median(absdiff)) if len(absdiff) else None),
                "ref_abs_dist_p90_m": fmt(float(np.percentile(absdiff, 90)) if len(absdiff) else None),
                "ref_dist_rms_m": fmt(float(np.sqrt(np.mean(diffs * diffs))) if len(diffs) else None),
                "z_p10_p90_span_m": fmt(zspan),
                "z_shift_to_reference_m": fmt(src.z_shift_to_reference_m),
                "crs": "EPSG:25832",
            }
            row.update(nstats)
            rows.append(row)
    return rows


def summarize_pointcloud(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for source_run, group in group_by(rows, "source_run").items():
        dens = vals(group, "density_pts_m2")
        cov = vals(group, "coverage_frac")
        noise = vals(group, "ref_dist_rms_m")
        modes = vals(group, "normal_mode_count")
        structures = Counter(r["normal_structure"] for r in group)
        out.append(
            {
                "source_run": source_run,
                "n": len(group),
                "median_density_pts_m2": fmt(np.median(dens) if dens else None),
                "median_coverage_frac": fmt(np.median(cov) if cov else None),
                "median_ref_dist_rms_m": fmt(np.median(noise) if noise else None),
                "median_normal_mode_count": fmt(np.median(modes) if modes else None),
                "flat_single": structures["flat_single"],
                "multi_slope": structures["multi_slope"],
                "single_slope": structures["single_slope"],
                "weak_or_sparse": structures["weak_structure"] + structures["too_few_points"] + structures["normal_unstable"],
            }
        )
    return sorted(out, key=lambda r: source_run_order(r["source_run"]))


def vals(rows: list[dict[str, Any]], key: str) -> list[float]:
    out = []
    for r in rows:
        v = num(r.get(key))
        if v is not None:
            out.append(v)
    return out


def group_by(rows: list[dict[str, Any]], key: str) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        out[str(row.get(key, ""))].append(row)
    return out


def build_pair_deltas(pc_rows: list[dict[str, Any]], metric_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    pc = {(r["source_run"], r["building_id"]): r for r in pc_rows}
    mr = {(r["source_run"], r["building_id"]): r for r in metric_rows}
    rows: list[dict[str, Any]] = []
    for arm in ("sparse", "dense", "acmp"):
        raw_key = f"raw_{arm}"
        for rep in ("r1", "r2"):
            gs_key = f"gs_{arm}_{rep}"
            for bid in C001_IDS:
                raw = pc[(raw_key, bid)]
                gs = pc[(gs_key, bid)]
                raw_m = mr[(raw_key, bid)]
                gs_m = mr[(gs_key, bid)]
                density_delta = diff(gs.get("density_pts_m2"), raw.get("density_pts_m2"))
                coverage_delta = diff(gs.get("coverage_frac"), raw.get("coverage_frac"))
                noise_gain = diff(raw.get("ref_dist_rms_m"), gs.get("ref_dist_rms_m"))
                modes_delta = diff(gs.get("normal_mode_count"), raw.get("normal_mode_count"))
                rows.append(
                    {
                        "arm": arm,
                        "replicate": rep,
                        "building_id": bid,
                        "raw_source": raw_key,
                        "gs_source": gs_key,
                        "raw_density_pts_m2": raw["density_pts_m2"],
                        "gs_density_pts_m2": gs["density_pts_m2"],
                        "delta_density_gs_minus_raw": density_delta,
                        "raw_coverage_frac": raw["coverage_frac"],
                        "gs_coverage_frac": gs["coverage_frac"],
                        "delta_coverage_gs_minus_raw": coverage_delta,
                        "raw_ref_dist_rms_m": raw["ref_dist_rms_m"],
                        "gs_ref_dist_rms_m": gs["ref_dist_rms_m"],
                        "noise_gain_raw_minus_gs_m": noise_gain,
                        "raw_normal_structure": raw["normal_structure"],
                        "gs_normal_structure": gs["normal_structure"],
                        "delta_normal_modes_gs_minus_raw": modes_delta,
                        "raw_has_lod22": raw_m["has_lod22"],
                        "gs_has_lod22": gs_m["has_lod22"],
                        "raw_shell_bucket": raw_m["shell_bucket"],
                        "gs_shell_bucket": gs_m["shell_bucket"],
                        "gs_vs_raw_observation": improvement_label(density_delta, coverage_delta, noise_gain),
                    }
                )
    return rows


def diff(a: Any, b: Any) -> str:
    av = num(a)
    bv = num(b)
    if av is None or bv is None:
        return ""
    return fmt(av - bv)


def improvement_label(density_delta: str, coverage_delta: str, noise_gain: str) -> str:
    d = safe_float(density_delta)
    c = safe_float(coverage_delta)
    n = safe_float(noise_gain)
    good = sum(v is not None and v > 0 for v in [d, c, n])
    bad = sum(v is not None and v < 0 for v in [d, c, n])
    if good > bad:
        return "improved_more_axes"
    if bad > good:
        return "worsened_more_axes"
    return "mixed_or_tie"


def model_shape_metrics(srcs: list[eight.Source], pred: dict[str, dict[str, list[eight.RoofSurface]]], refs: dict[str, list[eight.RoofSurface]], metric_rows: list[dict[str, Any]], footprints: dict[str, Any]) -> list[dict[str, Any]]:
    metric = {(r["source_run"], r["building_id"]): r for r in metric_rows}
    rows: list[dict[str, Any]] = []
    for src in srcs:
        if src.status_role == "reference":
            continue
        for bid in C001_IDS:
            surfaces = pred[src.source_run][bid]
            ref_surfaces = refs[bid]
            sample = model_sample(surfaces, footprints[bid])
            mode_count, tilt_p50, tilt_p90 = surface_normal_modes(surfaces)
            zspan = float(np.percentile(sample[:, 2], 90) - np.percentile(sample[:, 2], 10)) if len(sample) else None
            ref_mode_count, _, _ = surface_normal_modes(ref_surfaces)
            shape_class = model_shape_class(len(surfaces), mode_count, zspan)
            r = metric[(src.source_run, bid)]
            rows.append(
                {
                    "building_id": bid,
                    "source_run": src.source_run,
                    "source_group": src.source_group,
                    "roof_planes": len(surfaces),
                    "ref_roof_planes": len(ref_surfaces),
                    "model_normal_mode_count": mode_count,
                    "ref_normal_mode_count": ref_mode_count,
                    "model_tilt_p50_deg": fmt(tilt_p50),
                    "model_tilt_p90_deg": fmt(tilt_p90),
                    "model_z_p10_p90_span_m": fmt(zspan),
                    "shape_class": shape_class,
                    "has_lod22": r["has_lod22"],
                    "shell_bucket": r["shell_bucket"],
                    "completeness": r["completeness"],
                    "correctness": r["correctness"],
                    "ref_rms_m": r["ref_rms_m"],
                    "shape_note": shape_note(shape_class, len(ref_surfaces), r),
                }
            )
    return rows


def model_sample(surfaces: list[eight.RoofSurface], footprint: Any) -> np.ndarray:
    pts: list[np.ndarray] = []
    for surf in surfaces:
        xy = eight.sample_polygon_points(surf.polygon.intersection(footprint), GRID_CELL_M, limit=1200)
        if len(xy):
            pts.append(np.column_stack([xy[:, 0], xy[:, 1], surf.z_at(xy[:, 0], xy[:, 1])]))
    if not pts:
        return np.empty((0, 3), dtype=float)
    return np.vstack(pts)


def surface_normal_modes(surfaces: list[eight.RoofSurface]) -> tuple[int, float | None, float | None]:
    normals = []
    for surf in surfaces:
        n = np.asarray([-surf.ax, -surf.by, 1.0], dtype=float)
        n = n / np.linalg.norm(n)
        normals.append(n)
    if not normals:
        return 0, None, None
    arr = np.vstack(normals)
    tilt = np.degrees(np.arccos(np.clip(arr[:, 2], -1.0, 1.0)))
    sloped = tilt >= FLAT_TILT_DEG
    if np.count_nonzero(sloped) == 0:
        return 0, float(np.median(tilt)), float(np.percentile(tilt, 90))
    az = (np.degrees(np.arctan2(arr[sloped, 1], arr[sloped, 0])) + 360.0) % 360.0
    if len(az) <= 2:
        mode_count = len(az)
    else:
        hist, _ = np.histogram(az, bins=np.linspace(0, 360, 13))
        mode_count = int(np.count_nonzero(hist))
    return mode_count, float(np.median(tilt)), float(np.percentile(tilt, 90))


def model_shape_class(roof_planes: int, mode_count: int, zspan: float | None) -> str:
    if roof_planes == 0:
        return "no_model"
    if roof_planes == 1 and (zspan is None or zspan < 0.8 or mode_count <= 1):
        return "flat_or_single_plane"
    if mode_count >= 2 or roof_planes >= 2:
        return "multi_plane"
    return "weak_shape"


def shape_note(shape_class: str, ref_planes: int, metric: dict[str, Any]) -> str:
    if metric["shell_bucket"] == "무효·붕괴":
        return "invalid_or_collapse"
    if shape_class == "flat_or_single_plane" and ref_planes >= 2:
        return "flat_relative_to_reference"
    if metric["has_lod22"] != "true":
        return metric.get("status_reason", "not_built")
    return "observed"


def build_flattening_table(pc_rows: list[dict[str, Any]], shape_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    pc = {(r["source_run"], r["building_id"]): r for r in pc_rows}
    shape = {(r["source_run"], r["building_id"]): r for r in shape_rows}
    rows: list[dict[str, Any]] = []
    gs_sources = [f"gs_{arm}_{rep}" for arm in ("sparse", "dense", "acmp") for rep in ("r1", "r2")]
    for bid in FLAT_CASES:
        acmp = pc.get(("raw_acmp", bid), {})
        raw_dense = pc.get(("raw_dense", bid), {})
        for source_run in gs_sources:
            p = pc.get((source_run, bid), {})
            s = shape.get((source_run, bid), {})
            if not p or not s:
                continue
            point_has_structure = p.get("normal_structure") in {"multi_slope", "single_slope"} and (num(p.get("z_p10_p90_span_m")) or 0) >= 0.8
            acmp_has_structure = acmp.get("normal_structure") in {"multi_slope", "single_slope"} and (num(acmp.get("z_p10_p90_span_m")) or 0) >= 0.8
            dense_has_structure = raw_dense.get("normal_structure") in {"multi_slope", "single_slope"} and (num(raw_dense.get("z_p10_p90_span_m")) or 0) >= 0.8
            model_flat = s.get("shape_class") == "flat_or_single_plane" or s.get("shape_note") == "flat_relative_to_reference"
            if s.get("has_lod22") != "true":
                location = "not_built_no_flattening_localization"
            elif model_flat and point_has_structure:
                location = "readout_roofer_proxy"
            elif model_flat and not point_has_structure and (acmp_has_structure or dense_has_structure):
                location = "gs_depth_or_gs_readout_proxy"
            elif not model_flat and point_has_structure:
                location = "structure_survived_proxy"
            else:
                location = "unresolved_proxy"
            rows.append(
                {
                    "building_id": bid,
                    "source_run": source_run,
                    "model_shape_class": s.get("shape_class", ""),
                    "model_roof_planes": s.get("roof_planes", ""),
                    "point_normal_structure": p.get("normal_structure", ""),
                    "point_z_span_m": p.get("z_p10_p90_span_m", ""),
                    "acmp_point_structure": acmp.get("normal_structure", ""),
                    "raw_dense_point_structure": raw_dense.get("normal_structure", ""),
                    "flattening_location_proxy": location,
                    "render_depth_note": "rendered_depth_not_saved; classified_pointcloud_plus_acmp_proxy",
                }
            )
    return rows


def build_video_layer(metric_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    snap = {
        r["building_id"]: r
        for r in read_csv(Path("docs/regression_input_snapshot.csv"))
        if r.get("building_id") in C001_IDS and r.get("arm") == "raw_dense"
    }
    manual = {r["building_id"]: r for r in read_csv(Path("docs/manual_review_judgments.csv")) if r.get("building_id") in C001_IDS}
    by = {(r["source_run"], r["building_id"]): r for r in metric_rows}
    rows: list[dict[str, Any]] = []
    for bid in C001_IDS:
        s = snap.get(bid, {})
        m = manual.get(bid, {})
        gs_rows = [by[(f"gs_{arm}_{rep}", bid)] for arm in ("sparse", "dense", "acmp") for rep in ("r1", "r2")]
        gs_success_count = sum(tf(r["has_lod22"]) and r["shell_bucket"] != "무효·붕괴" for r in gs_rows)
        gs_any_model_count = sum(tf(r["has_lod22"]) for r in gs_rows)
        acmp_success = tf(by[("raw_acmp", bid)]["has_lod22"]) and by[("raw_acmp", bid)]["shell_bucket"] != "무효·붕괴"
        raw_dense_success = tf(by[("raw_dense", bid)]["has_lod22"]) and by[("raw_dense", bid)]["shell_bucket"] != "무효·붕괴"
        lowtex = safe_float(m.get("roof_lowtex_v5"))
        if lowtex is None:
            texture_class = by[("raw_dense", bid)].get("texture_lens", "not_reviewed")
            texture_sufficient = "unknown"
        elif lowtex >= 0.50:
            texture_class = "texture_poor"
            texture_sufficient = "false"
        else:
            texture_class = "texture_sufficient_proxy"
            texture_sufficient = "true"
        if texture_sufficient == "true" and acmp_success and gs_success_count == 0:
            mechanism_bucket = "method_proxy"
        elif texture_sufficient == "false" and not acmp_success and gs_success_count == 0:
            mechanism_bucket = "common_texture_limit_proxy"
        elif texture_sufficient == "false" and acmp_success and gs_success_count == 0:
            mechanism_bucket = "acmp_propagation_proxy"
        elif acmp_success and gs_success_count == 0:
            mechanism_bucket = "method_or_acmp_proxy_texture_unknown"
        elif acmp_success and gs_success_count > 0:
            mechanism_bucket = "both_have_success"
        elif not acmp_success and gs_success_count > 0:
            mechanism_bucket = "gs_only_success"
        else:
            mechanism_bucket = "both_fail_or_invalid"
        rows.append(
            {
                "building_id": bid,
                "roof_lowtex_v5": fmt(lowtex),
                "texture_class": texture_class,
                "texture_sufficient_proxy": texture_sufficient,
                "n_views_nadir": s.get("n_views_nadir", m.get("n_views_nadir", "")),
                "recon_score_median": s.get("recon_score_median", m.get("recon_score_median", "")),
                "manual_label": s.get("manual_label", m.get("label", "none")),
                "raw_dense_success": fmt(raw_dense_success),
                "acmp_success": fmt(acmp_success),
                "gs_success_count_clean": gs_success_count,
                "gs_any_lod22_count": gs_any_model_count,
                "mechanism_bucket": mechanism_bucket,
            }
        )
    return rows


def build_generation_failures(pair_rows: list[dict[str, Any]], pc_rows: list[dict[str, Any]], metric_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    pc = {(r["source_run"], r["building_id"]): r for r in pc_rows}
    mr = {(r["source_run"], r["building_id"]): r for r in metric_rows}
    flips = read_csv(Path("docs/e5_pilot_seed_pair_status.csv"))
    flip_map = {(r["arm"], r["building_id"]): tf(r.get("r1_r2_flip")) for r in flips}
    rows: list[dict[str, Any]] = []
    for pair in pair_rows:
        gs_key = pair["gs_source"]
        raw_key = pair["raw_source"]
        bid = pair["building_id"]
        arm = pair["arm"]
        g = mr[(gs_key, bid)]
        raw = mr[(raw_key, bid)]
        p = pc[(gs_key, bid)]
        cause = "not_failure"
        if tf(g["has_lod22"]) and g["shell_bucket"] == "무효·붕괴":
            cause = "collapse_invalid_or_rms_tail"
        elif not tf(g["has_lod22"]):
            reason = g.get("status_reason", "")
            density = safe_float(p.get("density_pts_m2"), 0.0) or 0.0
            cov = safe_float(p.get("coverage_frac"), 0.0) or 0.0
            if "no_points" in reason or int(p.get("roof_point_count") or 0) == 0:
                cause = "no_points"
            elif "no_planes" in reason:
                cause = "no_planes"
            elif cov < LOW_COVERAGE:
                cause = "coverage_threshold"
            elif density < LOW_DENSITY:
                cause = "density_threshold"
            else:
                cause = "unbuilt_other"
        if flip_map.get((arm, bid)):
            seed_flag = "seed_flip"
        else:
            seed_flag = ""
        rows.append(
            {
                "arm": arm,
                "replicate": pair["replicate"],
                "building_id": bid,
                "raw_source": raw_key,
                "gs_source": gs_key,
                "raw_has_lod22": raw["has_lod22"],
                "gs_has_lod22": g["has_lod22"],
                "gs_shell_bucket": g["shell_bucket"],
                "gs_status_reason": g.get("status_reason", ""),
                "gs_density_pts_m2": p["density_pts_m2"],
                "gs_coverage_frac": p["coverage_frac"],
                "gs_ref_dist_rms_m": p["ref_dist_rms_m"],
                "root_cause_proxy": cause,
                "seed_flag": seed_flag,
            }
        )
    return rows


def validity_report_paths(srcs: list[eight.Source]) -> dict[str, Path]:
    out = {
        "raw_sparse": eight.SPARSE_RUN / "val3dity/raw_sparse_val3dity_report.json",
        "raw_dense": eight.W2_RUN / "val3dity/dim_val3dity_report.json",
        "raw_acmp": eight.ACMP_RUN / "val3dity/raw_acmp_val3dity_report.json",
        "lidar": eight.W2_RUN / "val3dity/als_val3dity_report.json",
    }
    for src in srcs:
        if src.status_role == "gs" and src.run_name:
            out[src.source_run] = eight.GATE_RUN_DIR / "val3dity" / f"{src.run_name}_run_1_val3dity.json"
    return out


def parse_validity(srcs: list[eight.Source]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    detail: list[dict[str, Any]] = []
    paths = validity_report_paths(srcs)
    for source_run, path in paths.items():
        if not path.exists():
            detail.append({"source_run": source_run, "building_id": "", "error_code": "", "description": "missing_report", "category": "missing_report", "count": 1})
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        for feat in data.get("features", []):
            bid = feat.get("id", "").split("-0", 1)[0]
            if bid not in C001_IDS:
                continue
            errors = feat.get("errors") or []
            if not errors:
                detail.append({"source_run": source_run, "building_id": bid, "error_code": "", "description": "valid", "category": "valid", "count": 0})
                continue
            counts = Counter((str(e.get("code", "")), e.get("description", "")) for e in errors)
            for (code, desc), count in counts.items():
                detail.append(
                    {
                        "source_run": source_run,
                        "building_id": bid,
                        "error_code": code,
                        "description": desc,
                        "category": error_category(desc),
                        "count": count,
                    }
                )
    summary_counter: dict[tuple[str, str], dict[str, Any]] = {}
    for row in detail:
        key = (row["source_run"], row["category"])
        item = summary_counter.setdefault(
            key,
            {"source_run": row["source_run"], "category": row["category"], "buildings_with_category": set(), "error_instances": 0},
        )
        if row.get("building_id"):
            item["buildings_with_category"].add(row["building_id"])
        item["error_instances"] += int(row.get("count") or 0)
    summary = []
    for item in summary_counter.values():
        summary.append(
            {
                "source_run": item["source_run"],
                "category": item["category"],
                "buildings_with_category": len(item["buildings_with_category"]),
                "error_instances": item["error_instances"],
            }
        )
    return detail, sorted(summary, key=lambda r: (source_run_order(r["source_run"]), r["category"]))


def error_category(desc: str) -> str:
    d = (desc or "").upper()
    if "VALID" == d:
        return "valid"
    if "SELF_INTERSECTION" in d or "INTERSECTION" in d:
        return "self_intersection"
    if "ORIENTATION" in d or "WRONG" in d:
        return "face_orientation"
    if "NOT_CLOSED" in d or "UNCLOSED" in d or "OPEN" in d or "SHELL" in d and "INTERSECTION" not in d:
        return "non_closed_shell"
    if "CONSECUTIVE" in d or "DUPLICATE" in d or "DEGENERATE" in d or "TOO_FEW" in d:
        return "duplicate_degenerate"
    return "other"


def build_routing(video: list[dict[str, Any]], flattening: list[dict[str, Any]], pair_rows: list[dict[str, Any]], generation: list[dict[str, Any]], validity_summary: list[dict[str, Any]]) -> list[dict[str, Any]]:
    dense_pairs = [r for r in pair_rows if r["arm"] == "dense"]
    noise_gains = vals(dense_pairs, "noise_gain_raw_minus_gs_m")
    coverage_d = vals(dense_pairs, "delta_coverage_gs_minus_raw")
    density_d = vals(dense_pairs, "delta_density_gs_minus_raw")
    method_counts = Counter(r["mechanism_bucket"] for r in video)
    flat_counts = Counter(r["flattening_location_proxy"] for r in flattening)
    cause_counts = Counter(r["root_cause_proxy"] for r in generation if r["root_cause_proxy"] != "not_failure")
    validity_counts = Counter()
    for row in validity_summary:
        if row["category"] != "valid" and row["source_run"].startswith(("gs_", "raw_")):
            validity_counts[row["category"]] += int(row["buildings_with_category"])
    return [
        {
            "question": "GS가 자기 입력을 개선하나",
            "observation": "GS-dense vs raw-dense median/mean pair deltas",
            "density_delta_mean": fmt(np.mean(density_d) if density_d else None),
            "coverage_delta_mean": fmt(np.mean(coverage_d) if coverage_d else None),
            "noise_gain_m_median": fmt(np.median(noise_gains) if noise_gains else None),
            "routing": "negative_noise_gain_or_mixed_density_coverage_observed" if noise_gains and np.median(noise_gains) < 0 else "mixed",
        },
        {
            "question": "영상 탓인가 방법 탓인가",
            "observation": "; ".join(f"{k}={v}" for k, v in sorted(method_counts.items())),
            "routing": "proxy_video_layer_only",
        },
        {
            "question": "평판화는 깊이인가 readout인가",
            "observation": "; ".join(f"{k}={v}" for k, v in sorted(flat_counts.items())),
            "routing": "render_depth_absent_proxy",
        },
        {
            "question": "생성 실패 뿌리",
            "observation": "; ".join(f"{k}={v}" for k, v in sorted(cause_counts.items())),
            "routing": "root_pointcloud_status_linked",
        },
        {
            "question": "유효성 오류",
            "observation": "; ".join(f"{k}={v}" for k, v in sorted(validity_counts.items())),
            "routing": "val3dity_report_reparsed",
        },
    ]


def headline_summary(pair_rows: list[dict[str, Any]], video: list[dict[str, Any]], flattening: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for arm in ("sparse", "dense", "acmp"):
        subset = [r for r in pair_rows if r["arm"] == arm]
        rows.append(
            {
                "headline": f"GS-{arm} vs raw-{arm}",
                "n_pairs": len(subset),
                "mean_delta_density": fmt(np.mean(vals(subset, "delta_density_gs_minus_raw")) if vals(subset, "delta_density_gs_minus_raw") else None),
                "mean_delta_coverage": fmt(np.mean(vals(subset, "delta_coverage_gs_minus_raw")) if vals(subset, "delta_coverage_gs_minus_raw") else None),
                "median_noise_gain_raw_minus_gs_m": fmt(np.median(vals(subset, "noise_gain_raw_minus_gs_m")) if vals(subset, "noise_gain_raw_minus_gs_m") else None),
                "worsened_more_axes": sum(r["gs_vs_raw_observation"] == "worsened_more_axes" for r in subset),
                "improved_more_axes": sum(r["gs_vs_raw_observation"] == "improved_more_axes" for r in subset),
            }
        )
    buckets = Counter(r["mechanism_bucket"] for r in video)
    rows.append({"headline": "video_method_split", **{k: v for k, v in sorted(buckets.items())}})
    flat = Counter(r["flattening_location_proxy"] for r in flattening)
    rows.append({"headline": "flattening_location_proxy", **{k: v for k, v in sorted(flat.items())}})
    return rows


def md_table(rows: list[dict[str, Any]], columns: list[str], max_rows: int | None = None) -> list[str]:
    return eight.md_table(rows, columns, max_rows)


def write_report(
    inventory: list[dict[str, Any]],
    pc_summary: list[dict[str, Any]],
    pair_rows: list[dict[str, Any]],
    video: list[dict[str, Any]],
    generation: list[dict[str, Any]],
    shape_rows: list[dict[str, Any]],
    flattening: list[dict[str, Any]],
    validity_summary: list[dict[str, Any]],
    routing: list[dict[str, Any]],
    figs: list[Path],
) -> None:
    branch = eight.capture(["git", "branch", "--show-current"])
    head = eight.capture(["git", "rev-parse", "HEAD"])
    dense_pairs = [r for r in pair_rows if r["arm"] == "dense"]
    dense_noise = vals(dense_pairs, "noise_gain_raw_minus_gs_m")
    dense_cov = vals(dense_pairs, "delta_coverage_gs_minus_raw")
    dense_density = vals(dense_pairs, "delta_density_gs_minus_raw")
    video_counts = Counter(r["mechanism_bucket"] for r in video)
    flat_counts = Counter(r["flattening_location_proxy"] for r in flattening)
    gen_counts = Counter(r["root_cause_proxy"] for r in generation if r["root_cause_proxy"] != "not_failure")
    gs_dense_priority = [
        {
            "metric": "GS-dense vs raw-dense",
            "mean_delta_density": fmt(np.mean(dense_density) if dense_density else None),
            "mean_delta_coverage": fmt(np.mean(dense_cov) if dense_cov else None),
            "median_noise_gain_raw_minus_gs_m": fmt(np.median(dense_noise) if dense_noise else None),
        }
    ]
    flat_show = [r for r in flattening if r["building_id"] in FLAT_CASES and r["source_run"] in {"gs_dense_r1", "gs_dense_r2", "gs_acmp_r1", "gs_acmp_r2"}]
    lines = [
        "# W_E5_C001_GS진단",
        "",
        "> 재확인: 학습 0 · 레시피 0 · Roofer 0 · 판정 0. 기존 C001 GS 6런, raw 3, LiDAR, 참조 LoD2, val3dity 보고서, 기존 관측 스냅샷만 읽었다. CRS는 EPSG:25832.",
        "",
        "## 데이터 의존성",
        "",
        f"- 브랜치·HEAD: `{branch}` · `{head}`.",
        "- 한계: C001 18동 최악 블록, 2씨드, 영상 텍스처는 기존 수동/관측 스냅샷 기반 근사, ACMP는 정답이 아니라 이겨야 할 기준선이다.",
        "- 정답 계열: 형태는 참조 LoD2, 거리 상한은 LiDAR. ACMP는 목표 막대와 메커니즘 단서로만 사용했다.",
        "- 높이 프레임: raw-sparse/raw-acmp/GS는 참조 대비 -45.7 m, raw-dense/LiDAR는 0 m로 계산했다. 원본은 수정하지 않았다.",
        "- 렌더 깊이: 학습 체크포인트와 RGB 렌더, readout TSDF/분류 LAS는 있으나 GS 렌더 깊이 래스터는 저장본을 확인하지 못했다. 평판화 위치는 `분류 LAS 점군 구조 + ACMP/raw-dense 점군 구조` 대체 프록시다.",
        "",
        "## 입력 재고",
        "",
        *md_table(inventory, ["source_run", "source_group", "status", "cityjson_path", "pointcloud_path", "z_shift_to_reference_m", "missing_count"], max_rows=None),
        "",
        "## 헤드라인 답",
        "",
        *md_table(gs_dense_priority, ["metric", "mean_delta_density", "mean_delta_coverage", "median_noise_gain_raw_minus_gs_m"]),
        "",
        f"- GS 입력 개선/악화: GS-dense vs raw-dense의 `raw RMS - GS RMS` 중앙값은 {fmt(np.median(dense_noise) if dense_noise else None)} m로 관찰됐다. 양수는 개선, 음수는 악화다.",
        "- 영상 탓 vs 방법 탓: " + ", ".join(f"{k} {v}" for k, v in sorted(video_counts.items())) + ".",
        "- 평판화 위치: " + ", ".join(f"{k} {v}" for k, v in sorted(flat_counts.items())) + ". 렌더 깊이 부재로 직접 인과가 아니라 프록시다.",
        "",
        "## 공유 뿌리: 점군 진단",
        "",
        *md_table(pc_summary, ["source_run", "n", "median_density_pts_m2", "median_coverage_frac", "median_ref_dist_rms_m", "median_normal_mode_count", "flat_single", "multi_slope", "single_slope", "weak_or_sparse"]),
        "",
        f"- 점군 행 단위: `{PC_METRICS_CSV}`.",
        f"- GS-x vs raw-x 짝 델타: `{PAIR_DELTA_CSV}`.",
        "",
        "## 영상층",
        "",
        *md_table(video, ["building_id", "texture_class", "texture_sufficient_proxy", "n_views_nadir", "recon_score_median", "acmp_success", "gs_success_count_clean", "mechanism_bucket"], max_rows=18),
        "",
        "## 생성",
        "",
        "- 생성 실패 원인 프록시: " + ", ".join(f"{k} {v}" for k, v in sorted(gen_counts.items())) + ".",
        f"- 상세표: `{GEN_FAILURE_CSV}`.",
        "",
        "## 품질",
        "",
        *md_table(flat_show, ["building_id", "source_run", "model_shape_class", "point_normal_structure", "acmp_point_structure", "raw_dense_point_structure", "flattening_location_proxy"], max_rows=24),
        "",
        f"- 모델 형태 지표: `{SHAPE_CSV}`.",
        f"- 평판화 위치 프록시: `{FLATTENING_CSV}`.",
        "",
        "## 유효성",
        "",
        *md_table(validity_summary, ["source_run", "category", "buildings_with_category", "error_instances"], max_rows=80),
        "",
        "## 조건·불안정성",
        "",
        "- 조건 층화는 영상층 표의 텍스처/관측 열과 `docs/e5_c001_8way_strata_summary.csv`를 같이 읽는다.",
        "- 씨드 불안정성은 `docs/e5_pilot_seed_pair_status.csv`의 r1/r2 flip과 생성 상세표의 `seed_flag`로 연결했다. 2씨드라 방향만 기록했다.",
        "",
        "## 종합·라우팅",
        "",
        *md_table(routing, ["question", "observation", "routing"], max_rows=None),
        "",
        "## 인용",
        "",
        "- `사전등록서_본비교실험E5·기준레시피_v1_20260706.md` §4(측정)·§5(생성/유효성/품질 축)·§10(규약).",
        "- `기준문서_방법론·모집단·비교설계_v1.md` 부록 A/D.",
        "- `docs/W_E5_C001_8way.md`, `docs/e5_baselines_199_manifest.json`.",
        "- P0 텍스처/유효성 진단: `phases/p0-audit/docs/G1_package/t9_failure_surface_cause_building_metrics.csv`, `phases/p0-audit/docs/G1_package/t11_survivor_texture_refine_building_metrics.csv`, `phases/p0-audit/docs/G1_package/t13_validity_error_breakdown_type_by_input.csv`.",
        "- 요청문에 적힌 `docs/W_E5_C001_8way_분석·199판단_20260707.md`는 현재 checkout에서 발견하지 못했다. 잠금본과 어긋나는 경우 잠금본을 우선한다.",
        "",
        "## 산출물",
        "",
        f"- 보고서: `{REPORT_PATH}`.",
        f"- 표: `{PC_METRICS_CSV}`, `{PC_SUMMARY_CSV}`, `{PAIR_DELTA_CSV}`, `{VIDEO_CSV}`, `{GEN_FAILURE_CSV}`, `{SHAPE_CSV}`, `{FLATTENING_CSV}`, `{VALIDITY_CSV}`, `{VALIDITY_SUMMARY_CSV}`, `{ROUTING_CSV}`, `{SUMMARY_CSV}`.",
        f"- 그림: `{FIG_DIR}/`.",
        *[f"- `{p}`" for p in figs],
        f"- 버전: `{RUN_DIR / 'versions.txt'}`.",
        "",
        "## 관찰",
        "",
        "- 데이터는 GS-dense의 거리·형태 축이 raw-dense보다 불리하게 나온 사례가 섞여 있고, ACMP가 같은 블록에서 더 넓은 커버리지와 전파 이점을 보이는 패턴으로 관찰된다.",
        "- 평판화는 일부 사례에서 모델만 단순화된 readout/Roofer 프록시와, 점군 단계부터 구조가 약한 GS 깊이/readout 프록시가 함께 관찰된다. 이는 판정이 아니라 다음 라우팅을 위한 관찰이다.",
    ]
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def plot_pair_delta(pair_rows: list[dict[str, Any]]) -> Path:
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    labels = []
    noise = []
    cov = []
    dens = []
    for arm in ("sparse", "dense", "acmp"):
        for rep in ("r1", "r2"):
            subset = [r for r in pair_rows if r["arm"] == arm and r["replicate"] == rep]
            labels.append(f"{arm}-{rep}")
            noise.append(np.nanmedian(vals(subset, "noise_gain_raw_minus_gs_m")) if vals(subset, "noise_gain_raw_minus_gs_m") else np.nan)
            cov.append(np.nanmean(vals(subset, "delta_coverage_gs_minus_raw")) if vals(subset, "delta_coverage_gs_minus_raw") else np.nan)
            dens.append(np.nanmean(vals(subset, "delta_density_gs_minus_raw")) if vals(subset, "delta_density_gs_minus_raw") else np.nan)
    x = np.arange(len(labels))
    fig, ax = plt.subplots(figsize=(10, 4.6))
    ax.bar(x - 0.25, dens, width=0.25, label="density delta")
    ax.bar(x, cov, width=0.25, label="coverage delta")
    ax.bar(x + 0.25, noise, width=0.25, label="noise gain m")
    ax.axhline(0, color="black", linewidth=0.8)
    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=35, ha="right")
    ax.set_title("GS-x vs raw-x pair deltas")
    ax.grid(True, axis="y", alpha=0.25)
    ax.legend()
    fig.tight_layout()
    out = FIG_DIR / "pair_delta_gs_vs_raw.png"
    fig.savefig(out, dpi=170)
    plt.close(fig)
    return out


def plot_texture_success(video: list[dict[str, Any]]) -> Path:
    counts: dict[tuple[str, str], int] = Counter((r["texture_class"], r["mechanism_bucket"]) for r in video)
    textures = sorted({r["texture_class"] for r in video})
    buckets = sorted({r["mechanism_bucket"] for r in video})
    mat = np.array([[counts[(t, b)] for b in buckets] for t in textures], dtype=float)
    fig, ax = plt.subplots(figsize=(11, max(4, 0.45 * len(textures) + 2)))
    im = ax.imshow(mat, cmap="Blues")
    ax.set_xticks(np.arange(len(buckets)))
    ax.set_xticklabels(buckets, rotation=35, ha="right")
    ax.set_yticks(np.arange(len(textures)))
    ax.set_yticklabels(textures)
    for i in range(mat.shape[0]):
        for j in range(mat.shape[1]):
            ax.text(j, i, int(mat[i, j]), ha="center", va="center", color="black")
    ax.set_title("Texture proxy x success mechanism")
    fig.colorbar(im, ax=ax, shrink=0.75)
    fig.tight_layout()
    out = FIG_DIR / "texture_success_heatmap.png"
    fig.savefig(out, dpi=170)
    plt.close(fig)
    return out


def plot_normal_distribution(pc_rows: list[dict[str, Any]]) -> Path:
    focus = [r for r in pc_rows if r["building_id"] in FLAT_CASES and r["source_run"] in {"raw_dense", "raw_acmp", "gs_dense_r1", "gs_dense_r2", "lidar"}]
    labels = [f"{eight.short_id(r['building_id'])}\n{r['source_run']}" for r in focus]
    tilts = [safe_float(r.get("tilt_p90_deg"), 0.0) or 0.0 for r in focus]
    modes = [safe_float(r.get("normal_mode_count"), 0.0) or 0.0 for r in focus]
    x = np.arange(len(labels))
    fig, ax1 = plt.subplots(figsize=(max(11, 0.45 * len(labels)), 4.8))
    ax1.bar(x - 0.2, tilts, width=0.4, color="#4C78A8", label="tilt p90 deg")
    ax2 = ax1.twinx()
    ax2.bar(x + 0.2, modes, width=0.4, color="#F58518", label="normal modes")
    ax1.set_xticks(x)
    ax1.set_xticklabels(labels, rotation=55, ha="right")
    ax1.set_ylabel("tilt p90 deg")
    ax2.set_ylabel("normal mode count")
    ax1.set_title("Normal distribution proxy on flat-case buildings")
    ax1.grid(True, axis="y", alpha=0.25)
    fig.tight_layout()
    out = FIG_DIR / "normal_distribution_flat_cases.png"
    fig.savefig(out, dpi=170)
    plt.close(fig)
    return out


def plot_shape_scatter(shape_rows: list[dict[str, Any]]) -> Path:
    use = [r for r in shape_rows if r["source_run"] != "lidar" and num(r.get("ref_rms_m")) is not None]
    colors = {"raw_sparse": "#B279A2", "raw_dense": "#4C78A8", "raw_acmp": "#F58518", "gs_sparse": "#54A24B", "gs_dense": "#E45756", "gs_acmp": "#72B7B2"}
    fig, ax = plt.subplots(figsize=(8.4, 5.6))
    for group in sorted({r["source_group"] for r in use}):
        sub = [r for r in use if r["source_group"] == group]
        x = [safe_float(r.get("ref_rms_m"), np.nan) for r in sub]
        y = [safe_float(r.get("model_normal_mode_count"), np.nan) for r in sub]
        ax.scatter(x, y, s=36, alpha=0.75, label=group, color=colors.get(group))
    ax.set_xscale("symlog", linthresh=1)
    ax.set_xlabel("reference RMS m")
    ax.set_ylabel("model normal mode count")
    ax.set_title("Shape similarity proxy scatter")
    ax.grid(True, alpha=0.25)
    ax.legend(ncol=2, fontsize=8)
    fig.tight_layout()
    out = FIG_DIR / "shape_similarity_scatter.png"
    fig.savefig(out, dpi=170)
    plt.close(fig)
    return out


def plot_flattening(flattening: list[dict[str, Any]]) -> Path:
    counts = Counter(r["flattening_location_proxy"] for r in flattening)
    labels = list(counts)
    values = [counts[k] for k in labels]
    fig, ax = plt.subplots(figsize=(8.5, 4.5))
    ax.bar(labels, values, color="#59A14F")
    ax.set_ylabel("case count")
    ax.set_title("Flattening location proxy")
    ax.tick_params(axis="x", labelrotation=25)
    ax.grid(True, axis="y", alpha=0.25)
    fig.tight_layout()
    out = FIG_DIR / "flattening_location_cases.png"
    fig.savefig(out, dpi=170)
    plt.close(fig)
    return out


def plot_density_coverage(pc_summary: list[dict[str, Any]]) -> Path:
    labels = [r["source_run"] for r in pc_summary]
    dens = [safe_float(r.get("median_density_pts_m2"), 0.0) or 0.0 for r in pc_summary]
    cov = [safe_float(r.get("median_coverage_frac"), 0.0) or 0.0 for r in pc_summary]
    x = np.arange(len(labels))
    fig, ax1 = plt.subplots(figsize=(12, 4.8))
    ax1.bar(x - 0.2, dens, width=0.4, color="#4C78A8", label="density")
    ax2 = ax1.twinx()
    ax2.bar(x + 0.2, cov, width=0.4, color="#F58518", label="coverage")
    ax1.set_xticks(x)
    ax1.set_xticklabels(labels, rotation=45, ha="right")
    ax1.set_ylabel("median pts/m2")
    ax2.set_ylabel("median coverage")
    ax1.set_title("Density and coverage summary")
    ax1.grid(True, axis="y", alpha=0.25)
    fig.tight_layout()
    out = FIG_DIR / "density_coverage_summary.png"
    fig.savefig(out, dpi=170)
    plt.close(fig)
    return out


def make_figures(pair_rows: list[dict[str, Any]], video: list[dict[str, Any]], pc_rows: list[dict[str, Any]], pc_summary: list[dict[str, Any]], shape_rows: list[dict[str, Any]], flattening: list[dict[str, Any]]) -> list[Path]:
    return [
        plot_pair_delta(pair_rows),
        plot_texture_success(video),
        plot_normal_distribution(pc_rows),
        plot_shape_scatter(shape_rows),
        plot_flattening(flattening),
        plot_density_coverage(pc_summary),
    ]


def write_versions(figs: list[Path]) -> None:
    RUN_DIR.mkdir(parents=True, exist_ok=True)
    lines = [
        f"run_id: {RUN_ID}",
        f"created_utc: {datetime.now(timezone.utc).isoformat()}",
        "task: E5 C001 GS diagnostic",
        "mode: read-only; no training; no recipe change; no Roofer rerun; no verdict",
        "crs: EPSG:25832",
        f"git_branch: {eight.capture(['git', 'branch', '--show-current'])}",
        f"git_head: {eight.capture(['git', 'rev-parse', 'HEAD'])}",
        "docker_image: jointbuildgs-p0-tools:t0",
        f"script: phases/p2-gsjso/scripts/{Path(__file__).name}",
        f"readout: {READOUT_STRING}",
        f"height_frame_gs_raw_sparse_raw_acmp_shift_m: {eight.ELLIP_TO_REF_SHIFT_M}",
        "height_frame_raw_dense_lidar_shift_m: 0",
        "render_depth_saved: false",
        "gaussian_ckpt_available: true",
        "flattening_attribution: proxy_only_classified_pointcloud_plus_acmp",
        f"figures: {len(figs)}",
    ]
    (RUN_DIR / "versions.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    manifest = {
        "run_id": RUN_ID,
        "outputs": [rel(p) for p in [REPORT_PATH, PC_METRICS_CSV, PC_SUMMARY_CSV, PAIR_DELTA_CSV, VIDEO_CSV, GEN_FAILURE_CSV, SHAPE_CSV, FLATTENING_CSV, VALIDITY_CSV, VALIDITY_SUMMARY_CSV, ROUTING_CSV, SUMMARY_CSV, FIG_DIR]],
    }
    (RUN_DIR / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def copy_snapshots() -> None:
    snapshot = RUN_DIR / "snapshots"
    snapshot.mkdir(parents=True, exist_ok=True)
    for path in [REPORT_PATH, PC_METRICS_CSV, PC_SUMMARY_CSV, PAIR_DELTA_CSV, VIDEO_CSV, GEN_FAILURE_CSV, SHAPE_CSV, FLATTENING_CSV, VALIDITY_CSV, VALIDITY_SUMMARY_CSV, ROUTING_CSV, SUMMARY_CSV]:
        if path.exists():
            shutil.copy2(path, snapshot / path.name)


def main() -> None:
    os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib")
    eight.configure_korean_font()
    material = load_material()
    srcs = material["srcs"]
    refs = material["refs"]
    pred = material["pred"]
    metrics = material["metrics"]
    footprints = material["footprints"]
    inventory = material["inventory"]

    pc_rows = pointcloud_metrics(srcs, refs, footprints)
    pc_summary = summarize_pointcloud(pc_rows)
    pair_rows = build_pair_deltas(pc_rows, metrics)
    video = build_video_layer(metrics)
    generation = build_generation_failures(pair_rows, pc_rows, metrics)
    shape_rows = model_shape_metrics(srcs, pred, refs, metrics, footprints)
    flattening = build_flattening_table(pc_rows, shape_rows)
    validity_detail, validity_summary = parse_validity(srcs)
    routing = build_routing(video, flattening, pair_rows, generation, validity_summary)
    summary = headline_summary(pair_rows, video, flattening)

    write_csv(PC_METRICS_CSV, pc_rows)
    write_csv(PC_SUMMARY_CSV, pc_summary)
    write_csv(PAIR_DELTA_CSV, pair_rows)
    write_csv(VIDEO_CSV, video)
    write_csv(GEN_FAILURE_CSV, generation)
    write_csv(SHAPE_CSV, shape_rows)
    write_csv(FLATTENING_CSV, flattening)
    write_csv(VALIDITY_CSV, validity_detail)
    write_csv(VALIDITY_SUMMARY_CSV, validity_summary)
    write_csv(ROUTING_CSV, routing)
    write_csv(SUMMARY_CSV, summary)

    figs = make_figures(pair_rows, video, pc_rows, pc_summary, shape_rows, flattening)
    write_versions(figs)
    write_report(inventory, pc_summary, pair_rows, video, generation, shape_rows, flattening, validity_summary, routing, figs)
    copy_snapshots()
    print(json.dumps({"report": rel(REPORT_PATH), "figures": len(figs), "pointcloud_rows": len(pc_rows)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
