#!/usr/bin/env python3
"""Point-cloud input attributes v1.2.

Observation only: no reconstruction, no retraining, and no image projection.
The v1.2 change is deliberately narrow: repair the dense fallback height frame
and regenerate the read-only comparison material requested with it.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import re
import subprocess
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from lxml import etree

os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib")
import matplotlib

matplotlib.use("Agg")

import pointcloud_attributes_v1 as base
import pointcloud_attributes_v1_1 as v11


RUN_ID = "20260706_attr_v1_2"
ARMS = base.ARMS
HEIGHT_CONSTANT_M = 45.760
HEIGHT_CONSTANT_LABEL = "v1.14_section_1.6_zeta_45.7_QA_45.760"
W2_DIM_EXTRA_REMOVED_M = 0.174
DENSE_FALLBACK_SHIFT_M = HEIGHT_CONSTANT_M + W2_DIM_EXTRA_REMOVED_M
SOURCE_DIM = v11.SOURCE_DIM
SOURCE_ALS = v11.SOURCE_ALS
W2_RUN = v11.W2_RUN
W3_RUN = v11.W3_RUN
REF104_REASON = (
    "104586480 material: ALS footprint interior is dominated by ground-label, "
    "ground-height points while DIM contains a higher structure component; "
    "date/reference/label alternatives are recorded as material only"
)

METRIC_COLS = [
    "n_points_footprint",
    "pt_density_m2",
    "coverage_frac",
    "hole_frac",
    "roof_point_count",
    "ground_point_count",
    "local_plane_rms_m",
    "local_plane_core_count",
    "m3c2_core_count",
    "m3c2_mean_m",
    "m3c2_median_abs_m",
    "m3c2_rms_m",
    "m3c2_valid",
    "m3c2_reason",
    "floater_count",
    "floater_frac",
    "floater_valid",
    "floater_reason",
    "ground_high_count",
    "label_proxy_frac_all",
    "label_proxy_frac_ground",
    "label_proxy_valid",
    "label_proxy_reason",
]

HEIGHT_DEPENDENT_COLS = [
    "m3c2_core_count",
    "m3c2_mean_m",
    "m3c2_median_abs_m",
    "m3c2_rms_m",
    "m3c2_valid",
    "m3c2_reason",
    "floater_count",
    "floater_frac",
    "floater_valid",
    "floater_reason",
    "ground_high_count",
    "label_proxy_frac_all",
    "label_proxy_frac_ground",
    "label_proxy_valid",
    "label_proxy_reason",
]

PRESERVE_DENSE_COLS = [
    "n_points_footprint",
    "pt_density_m2",
    "grid_n_cells",
    "grid_occupied_cells",
    "coverage_frac",
    "hole_frac",
    "roof_point_count",
    "ground_point_count",
    "local_plane_rms_m",
    "local_plane_core_count",
]


def read_rows(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return list(reader.fieldnames or []), list(reader)


def write_rows(path: Path, fieldnames: list[str], rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({k: base.fmt(row.get(k)) for k in fieldnames})


def sha256_file(path: Path, block_size: int = 1024 * 1024) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(block_size), b""):
            h.update(block)
    return h.hexdigest()


def float_or_none(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float, np.integer, np.floating)):
        x = float(value)
        return x if math.isfinite(x) else None
    s = str(value).strip()
    if not s or s.lower() == "none":
        return None
    try:
        x = float(s)
    except ValueError:
        return None
    return x if math.isfinite(x) else None


def bool_or_none(value: object) -> bool | None:
    if isinstance(value, bool):
        return value
    s = str(value).strip().lower()
    if s in {"true", "1", "yes"}:
        return True
    if s in {"false", "0", "no"}:
        return False
    return None


def cell_text(value: object, digits: int = 4) -> str:
    if value is None:
        return "none"
    if isinstance(value, str):
        x = float_or_none(value)
        if x is None:
            return value
        value = x
    if isinstance(value, (int, np.integer)):
        return str(int(value))
    if isinstance(value, (float, np.floating)):
        if not math.isfinite(float(value)):
            return "none"
        return f"{float(value):.{digits}f}"
    return str(value)


def same_value(a: object, b: object, tol: float = 5e-6) -> bool:
    af = float_or_none(a)
    bf = float_or_none(b)
    if af is not None or bf is not None:
        if af is None or bf is None:
            return False
        return abs(af - bf) <= tol
    ab = bool_or_none(a)
    bb = bool_or_none(b)
    if ab is not None or bb is not None:
        return ab == bb
    return str(a) == str(b)


def numeric_rows(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    out: list[dict[str, object]] = []
    for row in rows:
        nr: dict[str, object] = dict(row)
        for key, value in list(nr.items()):
            if key in {"building_id", "arm", "clip_source", "clip_path", "clip_note", "crs_xy", "z_datum_history"}:
                continue
            b = bool_or_none(value)
            if b is not None and str(value).strip().lower() in {"true", "false"}:
                nr[key] = b
                continue
            x = float_or_none(value)
            if x is not None:
                nr[key] = x
        out.append(nr)
    return out


def median_iqr(vals: list[float]) -> tuple[float | None, float | None, float | None]:
    return base.median_iqr(vals)


def metric_values(rows: list[dict[str, object]], arm: str, col: str) -> list[float]:
    vals: list[float] = []
    for row in rows:
        if row.get("arm") != arm:
            continue
        x = float_or_none(row.get(col))
        if x is not None:
            vals.append(x)
    return vals


def median_iqr_label(vals: list[float], digits: int = 4) -> tuple[str, str, str]:
    med, q1, q3 = median_iqr(vals)
    if med is None:
        return "none", "none", "0"
    return f"{med:.{digits}f}", f"{q1:.{digits}f}-{q3:.{digits}f}", str(len(vals))


def recompute_height_axes(
    bid: str,
    row: dict[str, object],
    dense_xyz: np.ndarray,
    dense_cls: np.ndarray,
    lidar_xyz: np.ndarray,
    lidar_cls: np.ndarray,
    roofs: list[base.RoofSurface],
    args,
) -> dict[str, object]:
    out: dict[str, object] = {}
    roof_xyz = dense_xyz[dense_cls == 6]
    lidar_roof = lidar_xyz[lidar_cls == 6]
    if len(lidar_roof) < args.m3c2_min_neighbors:
        out.update(
            {
                "m3c2_core_count": None,
                "m3c2_mean_m": None,
                "m3c2_median_abs_m": None,
                "m3c2_rms_m": None,
                "m3c2_valid": False,
                "m3c2_reason": "insufficient_lidar_roof_points",
            }
        )
    else:
        m3, reason = base.m3c2_against_lidar(
            roof_xyz,
            lidar_roof,
            args.m3c2_normal_radius_m,
            args.m3c2_proj_radius_m,
            args.m3c2_min_neighbors,
            args.m3c2_max_cores,
            seed=base.stable_seed(bid, "raw_dense", "m3c2"),
        )
        for key in ("m3c2_core_count", "m3c2_mean_m", "m3c2_median_abs_m", "m3c2_rms_m"):
            out[key] = m3.get(key)
        out["m3c2_valid"] = reason == "ok"
        out["m3c2_reason"] = reason

    fallback_ref = max((s.z_max for s in roofs), default=None)
    old_geoid = base.GEOID_MED_M
    base.GEOID_MED_M = HEIGHT_CONSTANT_M
    try:
        zref, miss_frac = base.local_ref_z(dense_xyz[:, 0], dense_xyz[:, 1], roofs, fallback_ref)
    finally:
        base.GEOID_MED_M = old_geoid
    out["ref_lookup_miss_frac"] = miss_frac
    if len(dense_xyz) == 0:
        out.update(
            {
                "floater_count": 0,
                "floater_frac": None,
                "floater_valid": False,
                "floater_reason": "no_points",
                "ground_high_count": 0,
                "label_proxy_frac_all": None,
                "label_proxy_frac_ground": None,
                "label_proxy_valid": False,
                "label_proxy_reason": "no_points",
            }
        )
    elif zref is None:
        out.update(
            {
                "floater_count": None,
                "floater_frac": None,
                "floater_valid": False,
                "floater_reason": "missing_ref_roof",
                "ground_high_count": None,
                "label_proxy_frac_all": None,
                "label_proxy_frac_ground": None,
                "label_proxy_valid": False,
                "label_proxy_reason": "missing_ref_roof",
            }
        )
    else:
        ground = dense_cls == 2
        floater = dense_xyz[:, 2] > (zref + args.floater_margin_m)
        high_ground = ground & (dense_xyz[:, 2] > (zref - args.label_proxy_roof_minus_m))
        ground_count = int(np.sum(ground))
        out.update(
            {
                "floater_count": int(np.sum(floater)),
                "floater_frac": float(np.mean(floater)),
                "floater_valid": True,
                "floater_reason": "ok",
                "ground_high_count": int(np.sum(high_ground)),
                "label_proxy_frac_all": float(np.sum(high_ground) / len(dense_xyz)),
                "label_proxy_frac_ground": (float(np.sum(high_ground) / ground_count) if ground_count else None),
                "label_proxy_valid": True,
                "label_proxy_reason": "ok" if ground_count else "ok_no_ground_points",
            }
        )
    return out


def build_run_delta(repo: Path, out_csv: Path) -> tuple[dict[str, object], list[dict[str, object]]]:
    w2_path = repo / W2_RUN / "building_reconstruction_status.csv"
    w3_paths = {
        "ALS": repo / W3_RUN / "status/run_2/als_default.csv",
        "DIM": repo / W3_RUN / "status/run_2/dim_default.csv",
    }
    w2_rows = base.read_csv_rows(w2_path)
    w3_rows: list[dict[str, str]] = []
    for path in w3_paths.values():
        w3_rows.extend(base.read_csv_rows(path))
    w2_by = {(r["input"], r["building_id"]): r for r in w2_rows}
    w3_by = {(r["input"], r["building_id"]): r for r in w3_rows}

    rows: list[dict[str, object]] = []
    for key in sorted(set(w2_by).intersection(w3_by)):
        input_label, bid = key
        a = w2_by[key]
        b = w3_by[key]
        row: dict[str, object] = {
            "input": input_label,
            "building_id": bid,
            "w2_status": a.get("status"),
            "run2_status": b.get("status"),
            "status_flip": a.get("status") != b.get("status"),
            "w2_has_lod22": a.get("has_lod22"),
            "run2_has_lod22": b.get("has_lod22"),
            "has_lod22_flip": bool_or_none(a.get("has_lod22")) != bool_or_none(b.get("has_lod22")),
            "w2_val3dity_valid": a.get("val3dity_valid"),
            "run2_val3dity_valid": b.get("val3dity_valid"),
            "val3dity_flip": bool_or_none(a.get("val3dity_valid")) != bool_or_none(b.get("val3dity_valid")),
            "w2_rf_rmse_lod22": a.get("rf_rmse_lod22") or "none",
            "run2_rf_rmse_lod22": b.get("rf_rmse_lod22") or "none",
            "w2_rf_roof_planes": a.get("rf_roof_planes") or "none",
            "run2_rf_roof_planes": b.get("rf_roof_planes") or "none",
        }
        av = float_or_none(a.get("rf_rmse_lod22"))
        bv = float_or_none(b.get("rf_rmse_lod22"))
        row["rf_rmse_lod22_delta"] = None if av is None or bv is None else bv - av
        ap = float_or_none(a.get("rf_roof_planes"))
        bp = float_or_none(b.get("rf_roof_planes"))
        row["rf_roof_planes_delta"] = None if ap is None or bp is None else bp - ap
        rows.append(row)

    fieldnames = [
        "input",
        "building_id",
        "w2_status",
        "run2_status",
        "status_flip",
        "w2_has_lod22",
        "run2_has_lod22",
        "has_lod22_flip",
        "w2_val3dity_valid",
        "run2_val3dity_valid",
        "val3dity_flip",
        "w2_rf_rmse_lod22",
        "run2_rf_rmse_lod22",
        "rf_rmse_lod22_delta",
        "w2_rf_roof_planes",
        "run2_rf_roof_planes",
        "rf_roof_planes_delta",
    ]
    write_rows(out_csv, fieldnames, rows)

    coverage: dict[str, dict[str, int]] = {}
    for input_label in ("ALS", "DIM"):
        coverage[input_label] = {
            "w2_rows": sum(1 for r in w2_rows if r["input"] == input_label),
            "run2_rows": sum(1 for r in w3_rows if r["input"] == input_label),
            "overlap_rows": sum(1 for r in rows if r["input"] == input_label),
        }
    return {"coverage": coverage}, rows


def delta_stats(rows: list[dict[str, object]], input_label: str, col: str) -> dict[str, object]:
    vals = [float_or_none(r.get(col)) for r in rows if r["input"] == input_label]
    vals = [v for v in vals if v is not None]
    med, q1, q3 = median_iqr(vals)
    return {
        "n": len(vals),
        "nonzero": sum(abs(v) > 1e-9 for v in vals),
        "median": med,
        "q1": q1,
        "q3": q3,
        "min": min(vals) if vals else None,
        "max": max(vals) if vals else None,
    }


def density_qa(rows: list[dict[str, object]]) -> dict[str, object]:
    vals: list[float] = []
    outliers: list[dict[str, object]] = []
    for row in rows:
        if row["arm"] != "raw_dense" or row["clip_source"] != "fallback_dim_footprint_clip":
            continue
        delta = float_or_none(row.get("status_density_delta"))
        status_density = float_or_none(row.get("status_rf_pt_density"))
        if delta is None:
            continue
        vals.append(delta)
        threshold = max(5.0, 0.25 * abs(status_density or 0.0))
        if abs(delta) > threshold:
            note = (
                "fallback footprint all-point density below status rf_pt_density; metric definition/source selection differs"
                if delta < 0
                else "fallback footprint all-point density above status rf_pt_density; metric definition/source selection differs"
            )
            outliers.append(
                {
                    "building_id": row["building_id"],
                    "delta": delta,
                    "attr": float_or_none(row.get("pt_density_m2")),
                    "status": status_density,
                    "threshold": threshold,
                    "note": note,
                }
            )
    med, q1, q3 = median_iqr(vals)
    return {"n": len(vals), "median": med, "q1": q1, "q3": q3, "outliers": outliers}


def gate_stats(before_rows: list[dict[str, object]], after_rows: list[dict[str, object]]) -> dict[str, object]:
    def subset(rows: list[dict[str, object]], source: str) -> list[dict[str, object]]:
        return [r for r in rows if r["arm"] == "raw_dense" and r["clip_source"] == source]

    def med_abs(rows: list[dict[str, object]], col: str) -> float | None:
        vals = [float_or_none(r.get(col)) for r in rows]
        vals = [abs(v) for v in vals if v is not None]
        med, _, _ = median_iqr(vals)
        return med

    def med_signed(rows: list[dict[str, object]], col: str) -> float | None:
        vals = [float_or_none(r.get(col)) for r in rows]
        vals = [v for v in vals if v is not None]
        med, _, _ = median_iqr(vals)
        return med

    before_fb = subset(before_rows, "fallback_dim_footprint_clip")
    after_fb = subset(after_rows, "fallback_dim_footprint_clip")
    existing = subset(after_rows, "existing_mob_eval_clip")
    fallback_m3 = med_abs(after_fb, "m3c2_mean_m")
    fallback_m3_signed = med_signed(after_fb, "m3c2_mean_m")
    fallback_m3_rms = med_signed(after_fb, "m3c2_rms_m")
    unchanged_metric_diffs = 0
    by_key_before = {(r["building_id"], r["arm"]): r for r in before_rows}
    for row in after_rows:
        if row["arm"] == "raw_dense" and row["clip_source"] == "fallback_dim_footprint_clip":
            continue
        old = by_key_before[(row["building_id"], row["arm"])]
        for col in METRIC_COLS:
            if not same_value(old.get(col), row.get(col)):
                unchanged_metric_diffs += 1
                break

    dense_preserve_diffs = 0
    for row in after_fb:
        old = by_key_before[(row["building_id"], row["arm"])]
        for col in PRESERVE_DENSE_COLS:
            if not same_value(old.get(col), row.get(col)):
                dense_preserve_diffs += 1
                break

    fallback_floater_tail = sum((float_or_none(r.get("floater_frac")) or 0.0) > 0 for r in after_fb)
    fallback_label_tail = sum((float_or_none(r.get("label_proxy_frac_all")) or 0.0) > 0 for r in after_fb)
    existing_floater_tail = sum((float_or_none(r.get("floater_frac")) or 0.0) > 0 for r in existing)
    existing_label_tail = sum((float_or_none(r.get("label_proxy_frac_all")) or 0.0) > 0 for r in existing)
    return {
        "before_fb_m3c2_mean_median_abs": med_abs(before_fb, "m3c2_mean_m"),
        "after_fb_m3c2_mean_median_abs": fallback_m3,
        "before_fb_m3c2_mean_median": med_signed(before_fb, "m3c2_mean_m"),
        "after_fb_m3c2_mean_median": fallback_m3_signed,
        "before_fb_m3c2_rms_median": med_signed(before_fb, "m3c2_rms_m"),
        "after_fb_m3c2_rms_median": fallback_m3_rms,
        "before_fb_floater_tail": sum((float_or_none(r.get("floater_frac")) or 0.0) > 0 for r in before_fb),
        "after_fb_floater_tail": fallback_floater_tail,
        "before_fb_label_tail": sum((float_or_none(r.get("label_proxy_frac_all")) or 0.0) > 0 for r in before_fb),
        "after_fb_label_tail": fallback_label_tail,
        "existing_floater_tail": existing_floater_tail,
        "existing_label_tail": existing_label_tail,
        "existing_rows": len(existing),
        "fallback_rows": len(after_fb),
        "fallback_m3c2_valid": sum(float_or_none(r.get("m3c2_mean_m")) is not None for r in after_fb),
        "unchanged_metric_diffs": unchanged_metric_diffs,
        "dense_preserve_diffs": dense_preserve_diffs,
        "gate_a": fallback_m3_rms is not None and 0.2 <= fallback_m3_rms <= 3.0,
        "gate_a_mean_abs_range": fallback_m3 is not None and 0.2 <= fallback_m3 <= 3.0,
        "gate_b": fallback_floater_tail > 0 and fallback_label_tail > 0,
        "gate_c": unchanged_metric_diffs == 0 and dense_preserve_diffs == 0,
    }


def load_104586480_points(repo: Path, footprints: dict[str, object], rows: list[dict[str, object]], args) -> tuple[dict[str, base.ArmPoints], dict[str, dict[str, object]]]:
    bid = "DEBY_LOD2_104586480"
    poly = footprints[bid]
    fallbacks = {
        "raw_lidar": v11.FallbackSource(
            repo / SOURCE_ALS,
            "fallback_als_footprint_clip",
            HEIGHT_CONSTANT_M,
            f"ALS classified LAZ orthometric +{HEIGHT_CONSTANT_M:.3f} m ({HEIGHT_CONSTANT_LABEL})",
        )
    }
    loaded = {
        arm: v11.load_arm(repo, arm, bid, poly, fallbacks)
        for arm in ("raw_lidar", "raw_dense")
    }
    by = {(r["building_id"], r["arm"]): r for r in rows}
    out_rows: dict[str, dict[str, object]] = {}
    for arm in ("raw_lidar", "raw_dense"):
        row = dict(by[(bid, arm)])
        z = loaded[arm].points.xyz[:, 2]
        row["ground_label_frac_all"] = float(np.mean(loaded[arm].points.cls == 2)) if len(loaded[arm].points.cls) else None
        if len(z):
            row["z_p05"], row["z_p50"], row["z_p95"] = [float(v) for v in np.percentile(z, [5, 50, 95])]
        out_rows[arm] = row
    return {arm: loaded[arm].points for arm in loaded}, out_rows


def find_lod2_creation_date(repo: Path, bid: str, gml_dir: Path) -> tuple[str, str]:
    ns_gml = "http://www.opengis.net/gml"
    for path in sorted(gml_dir.glob("*.gml")):
        tree = etree.parse(str(path))
        for building in tree.xpath(".//*[local-name()='Building']"):
            if building.get(f"{{{ns_gml}}}id") != bid:
                continue
            vals = [e.text for e in building.xpath(".//*[local-name()='creationDate']") if e.text]
            return vals[0] if vals else "none", str(path.relative_to(repo))
    return "none", "missing"


def date_material(repo: Path, args) -> dict[str, str]:
    creation_date, creation_path = find_lod2_creation_date(
        repo, "DEBY_LOD2_104586480", repo / args.lod2_gml_dir
    )
    return {
        "building_id": "DEBY_LOD2_104586480",
        "lod2_creationDate": creation_date,
        "lod2_source": creation_path,
        "als_date_material": "LAZ header creation date 2022-06-16; adjusted GPS time 2022-02-27",
        "als_source": "phases/p0-audit/docs/data_inventory.md",
        "uav_capture_date": "2024-12-17",
        "uav_source": "docs/flight_meta_summary.md",
    }


def source_fingerprints(repo: Path, args) -> dict[str, tuple[str, str]]:
    paths = {
        "v1_1_csv": repo / args.v1_1_csv,
        "v1_2_script": Path(__file__).resolve(),
        "dim_fallback_source_w2_minus0p174": repo / SOURCE_DIM,
        "als_fallback_source": repo / SOURCE_ALS,
        "w1_diagnosis": repo / "phases/p0-audit/docs/W1_diagnosis.md",
        "w1_vertical_align_script": repo / "phases/p0-audit/scripts/07_vertical_align.py",
        "w2_roofer_script": repo / "phases/p0-audit/scripts/08_roofer_w2.py",
        "w2_config": repo / W2_RUN / "config.yaml",
        "w2_versions": repo / W2_RUN / "versions.txt",
        "w2_status": repo / W2_RUN / "building_reconstruction_status.csv",
        "w3_run2_als_status": repo / W3_RUN / "status/run_2/als_default.csv",
        "w3_run2_dim_status": repo / W3_RUN / "status/run_2/dim_default.csv",
        "population_aux_v4": repo / args.population,
        "manual_review_judgments": repo / "docs/manual_review_judgments.csv",
        "gen_8way_results_path": repo / "results/tum_transfer/mob/overseg_lever/gen_8way.csv",
        "flight_meta_summary": repo / "docs/flight_meta_summary.md",
        "data_inventory": repo / "phases/p0-audit/docs/data_inventory.md",
    }
    out: dict[str, tuple[str, str]] = {}
    for label, path in paths.items():
        if path.exists():
            rel = str(path.relative_to(repo)) if path.is_absolute() and path.is_relative_to(repo) else str(path)
            out[label] = (rel, sha256_file(path))
    return out


def md_table(rows: list[list[object]]) -> list[str]:
    if not rows:
        return []
    header = [str(v) for v in rows[0]]
    out = ["| " + " | ".join(header) + " |", "| " + " | ".join(["---"] * len(header)) + " |"]
    for row in rows[1:]:
        out.append("| " + " | ".join(str(v) for v in row) + " |")
    return out


def build_report_section(
    rows: list[dict[str, object]],
    gate: dict[str, object],
    density: dict[str, object],
    run_summary: dict[str, object],
    delta_rows: list[dict[str, object]],
    date_row: dict[str, str],
    b104_rows: dict[str, dict[str, object]],
    fps: dict[str, tuple[str, str]],
) -> str:
    clip_counts = Counter((r["arm"], r["clip_source"]) for r in rows)
    summary = base.make_summary_table(numeric_rows(rows))
    lines: list[str] = [
        "---",
        "",
        "# W pointcloud attributes v1.2",
        "",
        "> 재구성/재학습 없음. 이미지-투영 불사용. 수치와 관찰만 기록한다. CRS는 EPSG:25832.",
        "",
        "## v1.2 입력·수리 범위",
        "",
        "- 기준문서 확인: 루트 기준문서 v1.14 (2026-07-05).",
        "- 본 수리는 `raw_dense`의 `fallback_dim_footprint_clip` 149행만 대상으로 했다. 밀도·완전성·국소 평면 RMS는 v1.1 값을 보존했다.",
        f"- W1 기록: `dim_v1_classified_z.laz`는 GCG2016 보정본이고, W2 기록: `dim_v1_classified_z_minus0p174.laz`는 `Z := Z - {W2_DIM_EXTRA_REMOVED_M:.3f} m`로 만든 입력이다.",
        f"- v1.2 dense fallback 높이 이동: +{DENSE_FALLBACK_SHIFT_M:.3f} m (= {HEIGHT_CONSTANT_M:.3f} + {W2_DIM_EXTRA_REMOVED_M:.3f}). 근거 파일은 `W1_diagnosis.md`, `07_vertical_align.py`, `08_roofer_w2.py`, W2 config이며, W2 config의 기록 커밋은 `d61ff0f7386ba4df3e61a75443d9b84346c44387`이다.",
        "- `z_datum_history`에는 W1 GCG2016 보정, W2 `-0.174 m`, v1.2 `+45.934 m` 이동을 남겼다.",
        "",
        "## v1.2 클립 출처",
        "",
        "| arm | source | n_rows |",
        "|---|---|---:|",
    ]
    for arm in ARMS:
        for source in sorted({s for (a, s) in clip_counts if a == arm}):
            lines.append(f"| {arm} | {source} | {clip_counts[(arm, source)]} |")
    lines += [
        "",
        "## v1.2 축별·입력 종류별 분포",
        "",
        "| 축 | 입력 종류 | n | median | IQR |",
        "|---|---|---:|---:|---:|",
    ]
    for label, arm, n, med, q1, q3 in summary:
        iqr = "none" if q1 is None else f"{q1:.4g}-{q3:.4g}"
        lines.append(f"| {label} | {arm} | {n} | {base.fmt(med, 4)} | {iqr} |")
    lines += [
        "",
        "그림:",
        "",
        "- 입력 종류 대조 분포: `docs/figs/pointcloud_attributes_v1_2/arm_distribution.png`",
        "- ALS 대비 산점: `docs/figs/pointcloud_attributes_v1_2/als_scatter.png`",
        "",
        "## v1.2 자가 게이트",
        "",
        "| 항목 | 수리 전 | 수리 후 | 기존 dense clip | 통과 |",
        "|---|---:|---:|---:|---|",
        (
            f"| dense fallback M3C2 RMS median m | {cell_text(gate['before_fb_m3c2_rms_median'])} | "
            f"{cell_text(gate['after_fb_m3c2_rms_median'])} | existing n/a | {gate['gate_a']} |"
        ),
        (
            f"| dense fallback M3C2 mean median_abs m | {cell_text(gate['before_fb_m3c2_mean_median_abs'])} | "
            f"{cell_text(gate['after_fb_m3c2_mean_median_abs'])} | existing n/a | {gate['gate_a_mean_abs_range']} |"
        ),
        (
            f"| dense fallback M3C2 mean median m | {cell_text(gate['before_fb_m3c2_mean_median'])} | "
            f"{cell_text(gate['after_fb_m3c2_mean_median'])} | existing n/a | 기록 |"
        ),
        (
            f"| 부유점 0 아닌 행 수 | {gate['before_fb_floater_tail']} | {gate['after_fb_floater_tail']} | "
            f"{gate['existing_floater_tail']}/{gate['existing_rows']} | {gate['gate_b']} |"
        ),
        (
            f"| 라벨 프록시 0 아닌 행 수 | {gate['before_fb_label_tail']} | {gate['after_fb_label_tail']} | "
            f"{gate['existing_label_tail']}/{gate['existing_rows']} | {gate['gate_b']} |"
        ),
        (
            f"| 기존 유효 행 metric 변경 수 | n/a | {gate['unchanged_metric_diffs']} | n/a | {gate['gate_c']} |"
        ),
        (
            f"| dense fallback 보존 축 변경 수 | n/a | {gate['dense_preserve_diffs']} | n/a | {gate['gate_c']} |"
        ),
        "",
        f"- 게이트 요약: A={gate['gate_a']}, B={gate['gate_b']}, C={gate['gate_c']}.",
        "- A는 v1/v1.1 분포표와 같은 `M3C2 RMS median` 기준이다. `M3C2 mean median_abs`는 보조 기록으로 함께 남겼다.",
        "",
        "## v1.2 변경 로그",
        "",
        f"- dense fallback 149행 중 `n_points_footprint>0` 행의 부유점·라벨·M3C2 축을 재계산했다. no_points 행의 metric 값은 그대로 두고 높이 이력 열만 갱신했다.",
        "- 기존 유효 행의 metric 변경 수는 위 게이트 표에 기록했다.",
        "",
        "## 104586480 ref_invalid 후보 재료",
        "",
        "| 입력 종류 | n | coverage | ground_label_frac_all | roof_points | z_p05 | z_p50 | z_p95 | pt_density | local_RMS |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for arm, label in [("raw_lidar", "ALS"), ("raw_dense", "DIM")]:
        row = b104_rows[arm]
        lines.append(
            f"| {label} | {cell_text(row.get('n_points_footprint'), 0)} | {cell_text(row.get('coverage_frac'), 4)} | "
            f"{cell_text(row.get('ground_label_frac_all'), 4)} | {cell_text(row.get('roof_point_count'), 0)} | "
            f"{cell_text(row.get('z_p05'), 3)} | {cell_text(row.get('z_p50'), 3)} | {cell_text(row.get('z_p95'), 3)} | "
            f"{cell_text(row.get('pt_density_m2'), 3)} | {cell_text(row.get('local_plane_rms_m'), 3)} |"
        )
    lines += [
        "",
        "- 그림: `docs/figs/pointcloud_attributes_v1_2/ref_invalid_104586480_topview.png`",
        "- §2.4 본문 명시 ID 42364663·42364667과 대조하면 104586480은 그 두 본문 명시 ID가 아니다. v1.1과 같은 P0 기록에는 후보 재료로 남아 있다.",
        "- 관찰 재료: ALS 내부는 지면 라벨 우세·지면 높이 분포이고, DIM은 더 높은 구조물 성분을 포함한다. 시간차·참조 형상·점군 라벨 오류 중 어느 쪽인지는 여기서 판정하지 않는다.",
        "",
        "## dense fallback status-density QA",
        "",
        f"- 새 raw_dense fallback의 status density delta: n={density['n']}, median={cell_text(density['median'])}, IQR={cell_text(density['q1'])}-{cell_text(density['q3'])}.",
        f"- 큰 density delta 기준: abs(delta)>max(5 pt/m2, 25% status_density). v1.1 보고서는 {len(density['outliers'])}동 중 앞 20동만 출력했으므로, v1.2에서는 전체 {len(density['outliers'])}동을 같은 기준으로 적는다.",
    ]
    if density["outliers"]:
        lines.append("")
        lines.append("| building_id | delta | attr_density | status_density | note |")
        lines.append("|---|---:|---:|---:|---|")
        for item in density["outliers"]:
            lines.append(
                f"| {item['building_id']} | {item['delta']:.3f} | {item['attr']:.3f} | "
                f"{item['status']:.3f} | {item['note']} |"
            )
    lines += [
        "",
        "## 결과 정본 런 델타 재료",
        "",
        "| 입력 종류 | w2_1 rows | run_2 rows | overlap rows | has_lod22 flips | val3dity flips | rmse nonzero/median/IQR/min/max | roof_planes nonzero/median/IQR/min/max |",
        "|---|---:|---:|---:|---:|---:|---|---|",
    ]
    coverage = run_summary["coverage"]
    for input_label in ("ALS", "DIM"):
        sub = [r for r in delta_rows if r["input"] == input_label]
        has_flips = [r for r in sub if bool_or_none(r["has_lod22_flip"]) is True]
        val_flips = [r for r in sub if bool_or_none(r["val3dity_flip"]) is True]
        rmse = delta_stats(delta_rows, input_label, "rf_rmse_lod22_delta")
        planes = delta_stats(delta_rows, input_label, "rf_roof_planes_delta")
        rmse_txt = (
            f"{rmse['nonzero']}/{cell_text(rmse['median'])}/{cell_text(rmse['q1'])}-{cell_text(rmse['q3'])}/"
            f"{cell_text(rmse['min'])}/{cell_text(rmse['max'])}"
        )
        planes_txt = (
            f"{planes['nonzero']}/{cell_text(planes['median'])}/{cell_text(planes['q1'])}-{cell_text(planes['q3'])}/"
            f"{cell_text(planes['min'])}/{cell_text(planes['max'])}"
        )
        lines.append(
            f"| {input_label} | {coverage[input_label]['w2_rows']} | {coverage[input_label]['run2_rows']} | "
            f"{coverage[input_label]['overlap_rows']} | {len(has_flips)} | {len(val_flips)} | {rmse_txt} | {planes_txt} |"
        )
    lines += [
        "",
        "- 겹치는 동별 델타 CSV: `docs/W_canonical_run_delta.csv`.",
    ]
    for flip_col, label in [("has_lod22_flip", "조립 성공"), ("val3dity_flip", "유효성")]:
        flips = [r for r in delta_rows if bool_or_none(r[flip_col]) is True]
        if flips:
            lines.append(f"- {label} flip IDs:")
            for r in flips:
                if flip_col == "has_lod22_flip":
                    lines.append(
                        f"  - {r['input']} {r['building_id']}: w2={r['w2_has_lod22']}, run_2={r['run2_has_lod22']}"
                    )
                else:
                    lines.append(
                        f"  - {r['input']} {r['building_id']}: w2={r['w2_val3dity_valid']}, run_2={r['run2_val3dity_valid']}"
                    )
        else:
            lines.append(f"- {label} flip IDs: none.")
    lines += [
        "- 관찰: w2_1은 입력 종류별 199동 전수이고, run_2는 입력 종류별 93동 coverage-control 부분집합이다. 위 표는 겹치는 93동 기준의 수치 차이다.",
        "",
        "## 104586480 날짜 재료",
        "",
        "| building_id | LoD2 creationDate | LoD2 source | ALS date material | ALS source | UAV capture date | UAV source |",
        "|---|---|---|---|---|---|---|",
        (
            f"| {date_row['building_id']} | {date_row['lod2_creationDate']} | `{date_row['lod2_source']}` | "
            f"{date_row['als_date_material']} | `{date_row['als_source']}` | {date_row['uav_capture_date']} | `{date_row['uav_source']}` |"
        ),
        "",
        "## 입력 지문",
        "",
        "| 항목 | 경로 | sha256 |",
        "|---|---|---|",
    ]
    for label in [
        "v1_1_csv",
        "dim_fallback_source_w2_minus0p174",
        "als_fallback_source",
        "w1_diagnosis",
        "w1_vertical_align_script",
        "w2_roofer_script",
        "w2_config",
        "w2_status",
        "w3_run2_als_status",
        "w3_run2_dim_status",
    ]:
        rel, sha = fps.get(label, ("missing", "missing"))
        lines.append(f"| {label} | `{rel}` | `{sha}` |")
    lines += [
        "",
        "## 판정 필요 지점",
        "",
        "- 부유점 여유 3 m 유지 여부.",
        "- 라벨 프록시 정의: 전체 점 대비 `label_proxy_frac_all`과 ground 내부 `label_proxy_frac_ground` 중 회귀 주지표 선택.",
        "- `none` 행 처리: no_points 재코딩은 회귀 사양에서 처리.",
        "- 결과 정본 런 선택과 회귀 사양은 B단계 판정 뒤 실행.",
    ]
    return "\n".join(lines) + "\n"


def write_versions(path: Path, args, rows: list[dict[str, object]], gate: dict[str, object], fps: dict[str, tuple[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    def cmd_out(cmd: list[str]) -> str:
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, check=False)
        except FileNotFoundError as exc:
            return f"not_available:{exc.filename}"
        return (r.stdout or r.stderr).strip()

    clip_counts = Counter((r["arm"], r["clip_source"]) for r in rows)
    lines = [
        f"run_id: {RUN_ID}",
        "task: attr-v1.2",
        f"created_utc: {datetime.now(timezone.utc).isoformat()}",
        "mode: observation only; no reconstruction; no retraining; no image projection",
        "crs_xy: EPSG:25832",
        f"git_head: {cmd_out(['git', 'rev-parse', 'HEAD'])}",
        f"git_branch: {cmd_out(['git', 'branch', '--show-current'])}",
        "docker_image: jointbuildgs-p0-tools:t0",
        'run_command: docker run --rm --user "$(id -u):$(id -g)" -v "$PWD":/workspace/JointBuildGS -w /workspace/JointBuildGS jointbuildgs-p0-tools:t0 python3 phases/p2-gsjso/scripts/pointcloud_attributes_v1_2.py',
        f"python: {cmd_out(['python3', '--version'])}",
        "",
        "height_datum:",
        f"  v1_14_selected_constant_m: {HEIGHT_CONSTANT_M:.3f}",
        f"  selected_constant_source: {HEIGHT_CONSTANT_LABEL}",
        f"  dense_fallback_w2_extra_removed_m: {W2_DIM_EXTRA_REMOVED_M:.3f}",
        f"  dense_fallback_shift_m: {DENSE_FALLBACK_SHIFT_M:.3f}",
        "  dense_fallback_shift_formula: 45.760 + 0.174",
        "  dense_fallback_history: W1 GCG2016 corrected dim_v1_classified_z.laz; W2 used Z := Z - 0.174 m; v1.2 adds +45.934 m for the ref-dependent axes",
        "",
        "gate:",
        f"  gate_a_m3c2_rms_median_range_0p2_3m: {gate['gate_a']}",
        f"  gate_b_nonzero_floater_label_tail: {gate['gate_b']}",
        f"  gate_c_existing_metric_change_zero: {gate['gate_c']}",
        f"  after_fallback_m3c2_rms_median_m: {base.fmt(gate['after_fb_m3c2_rms_median'])}",
        f"  after_fallback_m3c2_mean_median_abs_m: {base.fmt(gate['after_fb_m3c2_mean_median_abs'])}",
        f"  gate_a_mean_abs_range_0p2_3m_recorded: {gate['gate_a_mean_abs_range']}",
        f"  existing_metric_diff_rows: {gate['unchanged_metric_diffs']}",
        f"  dense_preserved_metric_diff_rows: {gate['dense_preserve_diffs']}",
        "",
        "inputs_with_sha256:",
    ]
    for label, (rel, sha) in fps.items():
        lines.append(f"  {label}: {rel} sha256={sha}")
    lines += ["", "clip_source_counts:"]
    for arm in ARMS:
        for source in sorted({s for (a, s) in clip_counts if a == arm}):
            lines.append(f"  {arm}.{source}: {clip_counts[(arm, source)]}")
    lines += [
        "",
        "parameters:",
        f"  grid_cell_m: {args.grid_cell_m}",
        f"  local_plane_radius_m: {args.local_plane_radius_m}",
        f"  m3c2_normal_radius_m: {args.m3c2_normal_radius_m}",
        f"  m3c2_proj_radius_m: {args.m3c2_proj_radius_m}",
        f"  floater_margin_m: {args.floater_margin_m}",
        f"  label_proxy_roof_minus_m: {args.label_proxy_roof_minus_m}",
        "",
        "outputs:",
        "  docs/pointcloud_attributes_v1_2.csv",
        "  docs/W_pointcloud_attributes.md",
        "  docs/W_canonical_run_delta.csv",
        "  docs/figs/pointcloud_attributes_v1_2/arm_distribution.png",
        "  docs/figs/pointcloud_attributes_v1_2/als_scatter.png",
        "  docs/figs/pointcloud_attributes_v1_2/ref_invalid_104586480_topview.png",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_argparser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser()
    ap.add_argument("--population", default="docs/population_aux_v4.csv")
    ap.add_argument("--footprints", default="phases/p0-audit/data/work/w2/footprints_scene_aoi.gpkg")
    ap.add_argument("--lod2-gml-dir", default="phases/p0-audit/data/raw/lod2")
    ap.add_argument("--v1-1-csv", default="docs/pointcloud_attributes_v1_1.csv")
    ap.add_argument("--out-csv", default="docs/pointcloud_attributes_v1_2.csv")
    ap.add_argument("--out-report", default="docs/W_pointcloud_attributes.md")
    ap.add_argument("--out-delta-csv", default="docs/W_canonical_run_delta.csv")
    ap.add_argument("--fig-dir", default="docs/figs/pointcloud_attributes_v1_2")
    ap.add_argument("--versions", default=f"runs/{RUN_ID}/versions.txt")
    ap.add_argument("--grid-cell-m", type=float, default=0.5)
    ap.add_argument("--local-plane-radius-m", type=float, default=0.75)
    ap.add_argument("--m3c2-normal-radius-m", type=float, default=1.0)
    ap.add_argument("--m3c2-proj-radius-m", type=float, default=0.75)
    ap.add_argument("--m3c2-min-neighbors", type=int, default=8)
    ap.add_argument("--m3c2-max-cores", type=int, default=2500)
    ap.add_argument("--floater-margin-m", type=float, default=3.0)
    ap.add_argument("--label-proxy-roof-minus-m", type=float, default=1.0)
    return ap


def main() -> None:
    args = build_argparser().parse_args()
    repo = Path.cwd()
    base.GEOID_MED_M = HEIGHT_CONSTANT_M
    fields, before_rows_raw = read_rows(repo / args.v1_1_csv)
    before_rows = [dict(r) for r in before_rows_raw]
    rows: list[dict[str, object]] = [dict(r) for r in before_rows_raw]
    for extra in [
        "v1_2_changed_axes",
        "v1_2_change_reason",
        "v1_2_dense_fallback_shift_m",
        "v1_2_shift_source",
    ]:
        if extra not in fields:
            fields.append(extra)

    pop = base.read_population(repo / args.population)
    pop_set = set(pop)
    footprints = base.load_footprints(repo / args.footprints, pop_set)
    roofs = base.load_roof_surfaces(repo / args.lod2_gml_dir, pop_set)

    dense_source = v11.FallbackSource(
        repo / SOURCE_DIM,
        "fallback_dim_footprint_clip",
        DENSE_FALLBACK_SHIFT_M,
        (
            "canonical Roofer DIM classified LAZ w2_1 input; W1 GCG2016-corrected "
            f"dim_v1_classified_z.laz then W2 Z:=Z-{W2_DIM_EXTRA_REMOVED_M:.3f} m; "
            f"v1.2 applies +{DENSE_FALLBACK_SHIFT_M:.3f} m (=45.760+0.174) for "
            f"{HEIGHT_CONSTANT_LABEL}; EPSG:25832"
        ),
    )
    lidar_source = v11.FallbackSource(
        repo / SOURCE_ALS,
        "fallback_als_footprint_clip",
        HEIGHT_CONSTANT_M,
        f"ALS classified LAZ orthometric +{HEIGHT_CONSTANT_M:.3f} m ({HEIGHT_CONSTANT_LABEL})",
    )
    lidar_fallbacks = {"raw_lidar": lidar_source}

    for i, row in enumerate(rows):
        row["v1_2_changed_axes"] = "none"
        row["v1_2_change_reason"] = "unchanged_from_v1_1"
        row["v1_2_dense_fallback_shift_m"] = "none"
        row["v1_2_shift_source"] = "none"
        if row.get("building_id") == "DEBY_LOD2_104586480":
            row["ref_invalid_reason"] = REF104_REASON
        if row["arm"] != "raw_dense" or row["clip_source"] != "fallback_dim_footprint_clip":
            continue

        bid = str(row["building_id"])
        row["z_datum_history"] = dense_source.z_history
        row["datum_shift_from_v1_m"] = DENSE_FALLBACK_SHIFT_M
        row["source_laz_path"] = str(SOURCE_DIM)
        row["v1_2_dense_fallback_shift_m"] = DENSE_FALLBACK_SHIFT_M
        row["v1_2_shift_source"] = "W1_GCG2016_corrected_DIM_plus_W2_minus0p174_chain"
        if int(float_or_none(row.get("n_points_footprint")) or 0) == 0:
            row["v1_2_changed_axes"] = "z_datum_history"
            row["v1_2_change_reason"] = "dense_fallback_height_history_repaired_no_points_metrics_unchanged"
            continue

        poly = footprints[bid]
        dense_xyz, dense_cls = dense_source.clip(poly)
        lidar_loaded = v11.load_arm(repo, "raw_lidar", bid, poly, lidar_fallbacks)
        updated = recompute_height_axes(
            bid,
            row,
            dense_xyz,
            dense_cls,
            lidar_loaded.points.xyz,
            lidar_loaded.points.cls,
            roofs.get(bid, []),
            args,
        )
        changed: list[str] = ["z_datum_history"]
        old = before_rows_raw[i]
        for col, value in updated.items():
            if col in PRESERVE_DENSE_COLS:
                continue
            if col in row and not same_value(row.get(col), value):
                changed.append(col)
            row[col] = value
        row["v1_2_changed_axes"] = ";".join(dict.fromkeys(changed))
        row["v1_2_change_reason"] = "dense_fallback_height_frame_repaired_ref_dependent_axes"

    after_rows = rows
    out_csv = repo / args.out_csv
    write_rows(out_csv, fields, after_rows)

    fig_dir = repo / args.fig_dir
    plot_rows = numeric_rows(after_rows)
    base.plot_distributions(plot_rows, fig_dir / "arm_distribution.png")
    base.plot_als_scatter(plot_rows, fig_dir / "als_scatter.png")
    b104_points, b104_rows = load_104586480_points(repo, footprints, after_rows, args)
    v11.plot_104586480_topview(
        b104_points,
        b104_rows,
        footprints["DEBY_LOD2_104586480"],
        fig_dir / "ref_invalid_104586480_topview.png",
    )

    run_summary, delta_rows = build_run_delta(repo, repo / args.out_delta_csv)
    dqa = density_qa(after_rows)
    gate = gate_stats(before_rows, after_rows)
    dates = date_material(repo, args)
    fps = source_fingerprints(repo, args)

    old_report = (repo / args.out_report).read_text(encoding="utf-8")
    prefix = old_report.split("\n---\n\n# W pointcloud attributes v1.2", 1)[0].rstrip()
    section = build_report_section(after_rows, gate, dqa, run_summary, delta_rows, dates, b104_rows, fps)
    (repo / args.out_report).write_text(prefix + "\n\n" + section, encoding="utf-8")
    write_versions(repo / args.versions, args, after_rows, gate, fps)

    print(json.dumps({
        "rows": len(after_rows),
        "gate": gate,
        "density_outliers": len(dqa["outliers"]),
        "delta_rows": len(delta_rows),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
