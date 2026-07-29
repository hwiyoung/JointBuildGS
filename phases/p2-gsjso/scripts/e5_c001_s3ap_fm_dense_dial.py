#!/usr/bin/env python3
"""S3-A-prime Phase-0 FM fixed-pose reprojection dense dial.

This is a learning-zero measurement. MASt3R supplies reciprocal 2D matches;
fixed COLMAP cameras supply metric DLT.  Footprints and LoD2 are first read
after raw finite/positive-depth DLT caches have been written and are used only
for spatial and height scoring.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
import math
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib")
os.environ.setdefault("XDG_CACHE_HOME", "/tmp")

import matplotlib
import numpy as np
import torch
from shapely import contains_xy

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402


REPO = Path(__file__).resolve().parents[3]
CONFIG = REPO / "phases/p2-gsjso/configs/e5_c001_s3ap_fm_dense_dial.json"
RUN_DIR = REPO / "phases/p2-gsjso/runs/20260715_e5_c001_s3ap_phase0_fm_dense"
RAW_DIR = RUN_DIR / "raw_pairs"
PROGRESS = RUN_DIR / "progress.json"
PAIR_CSV = RUN_DIR / "pair_progress.csv"
RUN_LOG = RUN_DIR / "run.log"
VERSIONS = RUN_DIR / "versions.txt"
MANIFEST = RUN_DIR / "manifest.json"
OUT_CSV = REPO / "docs/experiments/e5_c001_s3ap/tables/e5_c001_s3ap_fm_dense_dial.csv"
FIGURE = REPO / "docs/figs/e5_c001_s3ap_phase0/fm_dense_curve.png"
OLD_RUN = REPO / "phases/p2-gsjso/runs/20260714_e5_c001_s3ap_fm_retriangulation"
OLD_PAIR_DIR = OLD_RUN / "pairs"
OLD_MANIFEST = OLD_RUN / "manifest.json"
OLD_RESCORE_CSV = REPO / "docs/experiments/e5_c001_s3ap/tables/e5_c001_s3ap_fm_retri_rescore.csv"
ENV_MANIFEST = REPO / "docs/experiments/e5_c001_s3ap/manifests/e5_c001_s3ap_fm_env_manifest.json"
PROJECTION_DATUM = REPO / "configs/projection_datum.json"


def load_module(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot import {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


retri = load_module(
    "s3ap_fm_retriangulation_dense_dial",
    REPO / "phases/p2-gsjso/scripts/e5_c001_s3ap_fm_retriangulation.py",
)
rescore = load_module(
    "s3ap_fm_retri_rescore_dense_dial",
    REPO / "phases/p2-gsjso/scripts/e5_c001_s3ap_fm_retri_rescore.py",
)
base = retri.base


PAIR_FIELDS = [
    "building_id", "pair_rank", "view_a", "view_b", "acquisition_block_a", "acquisition_block_b",
    "pair_relation", "known_colmap_baseline_m", "eligible_summary_pair", "reciprocal_match_count",
    "border_match_count", "dlt_finite_count", "cheirality_pass_count", "reprojection_2px_count",
    "reprojection_4px_count", "reprojection_8px_count", "raw_count", "old_2px_count",
    "two_px_count_matches_old", "two_px_world_max_abs_diff_m", "crop_box_a_xyxy", "crop_box_b_xyxy",
    "status", "failure_reason", "elapsed_s", "pair_time_limit_s", "cache_path", "cache_sha256",
    "new_mast3r_inference_runs", "cache_reuse_runs", "learning_runs_started",
]

DIAL_FIELDS = [
    "building_id", "threshold_label", "threshold_order", "max_reprojection_error_px", "raw_definition",
    "selected_dlt_point_count", "footprint_inside_point_count", "finite_lod2_height_score_count",
    "inside_z_median_local_m", "inside_z_mad_m", "reference_roof_z_median_local_m",
    "abs_delta_z_median_m", "abs_delta_z_mad_m", "point_to_lod2_rms_m", "coverage_grid_m",
    "coverage_eligible_cell_count", "coverage_occupied_cell_count", "coverage_ratio",
    "selected_pair_count", "eligible_pair_count", "nonzero_inside_pair_count", "two_px_expected_inside_count",
    "two_px_inside_count_matches_locked_cache", "meets_locked_operating_bounds", "selected_good_operating_point",
    "building_operating_point", "operating_point_rule", "summary_aggregation", "raw_cache_status",
    "new_mast3r_inference_runs", "cache_reuse_runs", "candidate_generation_gt_used", "footprint_role",
    "lod2_role", "crs", "learning_runs_started", "status",
]


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(REPO.resolve()))
    except ValueError:
        return str(path.resolve())


def sha256_file(path: Path, block_size: int = 1 << 20) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(block_size), b""):
            digest.update(block)
    return digest.hexdigest()


def git_value(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=REPO, text=True).strip()


def log(message: str) -> None:
    RUN_DIR.mkdir(parents=True, exist_ok=True)
    line = f"{now()} {message}"
    with RUN_LOG.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    print(line, flush=True)


def atomic_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def fmt(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (bool, np.bool_)):
        return "true" if bool(value) else "false"
    if isinstance(value, (float, np.floating)):
        return "" if not math.isfinite(float(value)) else f"{float(value):.6f}"
    return str(value)


def atomic_csv(path: Path, rows: Sequence[dict[str, Any]], fields: Sequence[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    with tmp.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(fields), extrasaction="ignore", lineterminator="\n")
        writer.writeheader()
        writer.writerows({key: fmt(row.get(key)) for key in fields} for row in rows)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, path)


def finite_stats(values: np.ndarray) -> dict[str, float | None]:
    values = np.asarray(values, dtype=np.float64)
    values = values[np.isfinite(values)]
    if not len(values):
        return {"median": None, "mad": None, "rms": None}
    median = float(np.median(values))
    return {
        "median": median,
        "mad": float(np.median(np.abs(values - median))),
        "rms": float(np.sqrt(np.mean(values**2))),
    }


def update_progress(
    config: dict[str, Any], pair_rows: Sequence[dict[str, Any]], dial_rows: Sequence[dict[str, Any]],
    active: dict[str, Any] | None, status: str,
) -> None:
    payload = {
        "schema": "jointbuildgs.s3ap.fm_dense_dial.progress.v1",
        "updated_utc": now(),
        "status": status,
        "target_pair_count": sum(len(base.select_pairs(base.load_view_rows()[short])) for short in config["targets"]),
        "recorded_pair_count": len(pair_rows),
        "completed_building_count": len({row["building_id"] for row in dial_rows}),
        "dial_row_count": len(dial_rows),
        "active": active,
        "new_mast3r_inference_runs": sum(int(row.get("new_mast3r_inference_runs", 0)) for row in pair_rows),
        "cache_reuse_runs": sum(int(row.get("cache_reuse_runs", 0)) for row in pair_rows),
        "learning_runs_started": 0,
    }
    atomic_text(PROGRESS, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


def cache_path(short: str, rank: int) -> Path:
    return RAW_DIR / f"{short}_rank{rank:02d}_raw_cheirality.npz"


def save_raw_cache(path: Path, detail: dict[str, Any], config_sha256: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    metadata = {
        "schema": "jointbuildgs.s3ap.fm_dense_dial.raw_pair.v1",
        "building_id": detail["building_id"],
        "pair_rank": detail["pair_rank"],
        "view_a": detail["view_a"],
        "view_b": detail["view_b"],
        "crop_box_a_xyxy": detail["crop_box_a_xyxy"],
        "crop_box_b_xyxy": detail["crop_box_b_xyxy"],
        "known_colmap_baseline_m": detail["known_colmap_baseline_m"],
        "reciprocal_match_count": detail["reciprocal_match_count"],
        "border_match_count": detail["border_match_count"],
        "dlt_finite_count": detail["dlt_finite_count"],
        "cheirality_pass_count": detail["cheirality_pass_count"],
        "raw_definition": detail["raw_definition"],
        "config_sha256": config_sha256,
        "candidate_generation_gt_used": False,
        "learning_runs_started": 0,
    }
    tmp = path.with_name(path.name + ".tmp.npz")
    np.savez_compressed(
        tmp,
        world_local_xyz=detail["world"],
        pixels_a=detail["pixels_a"],
        pixels_b=detail["pixels_b"],
        max_reprojection_error_px=detail["max_error"],
        metadata_json=json.dumps(metadata, ensure_ascii=False),
    )
    os.replace(tmp, path)


def load_raw_cache(path: Path, config_sha256: str) -> dict[str, Any]:
    with np.load(path, allow_pickle=False) as archive:
        metadata = json.loads(str(archive["metadata_json"]))
        if metadata.get("schema") != "jointbuildgs.s3ap.fm_dense_dial.raw_pair.v1":
            raise RuntimeError(f"raw cache schema mismatch: {path}")
        if metadata.get("config_sha256") != config_sha256:
            raise RuntimeError(f"raw cache config mismatch: {path}")
        detail = {
            **metadata,
            "world": np.asarray(archive["world_local_xyz"], dtype=np.float64),
            "pixels_a": np.asarray(archive["pixels_a"], dtype=np.float64),
            "pixels_b": np.asarray(archive["pixels_b"], dtype=np.float64),
            "max_error": np.asarray(archive["max_reprojection_error_px"], dtype=np.float64),
        }
    lengths = {len(detail[key]) for key in ("world", "pixels_a", "pixels_b", "max_error")}
    if lengths != {int(detail["cheirality_pass_count"])}:
        raise RuntimeError(f"raw cache array length mismatch: {path}")
    return detail


def infer_raw_pair(
    model: Any, short: str, rank: int, pair: dict[str, Any], frames: dict[str, dict[str, Any]],
    device: str, raw_definition: str,
) -> dict[str, Any]:
    a, b = pair["a"], pair["b"]
    frame_a, frame_b = frames[a["stem"]], frames[b["stem"]]
    mask_a, _ = base.target_region_mask(short, a["stem"])
    mask_b, _ = base.target_region_mask(short, b["stem"])
    box_a = base.crop_box_4x3(mask_a, frame_a["width"], frame_a["height"])
    box_b = base.crop_box_4x3(mask_b, frame_b["width"], frame_b["height"])
    image_a, _, _ = base.prepare_view(frame_a, box_a, 0)
    image_b, _, _ = base.prepare_view(frame_b, box_b, 1)
    with torch.inference_mode():
        output = base.inference([(image_a, image_b)], model, device, batch_size=1, verbose=False)
    desc_a = output["pred1"]["desc"].squeeze(0).detach()
    desc_b = output["pred2"]["desc"].squeeze(0).detach()
    match_a, match_b = base.fast_reciprocal_NNs(
        desc_a, desc_b, subsample_or_initxy1=base.MATCH_SUBSAMPLE,
        device=device, dist="dot", block_size=2**13,
    )
    reciprocal_count = int(len(match_a))
    border = (
        (match_a[:, 0] >= base.MATCH_BORDER_PX)
        & (match_a[:, 0] < base.LOAD_WIDTH - base.MATCH_BORDER_PX)
        & (match_a[:, 1] >= base.MATCH_BORDER_PX)
        & (match_a[:, 1] < base.LOAD_HEIGHT - base.MATCH_BORDER_PX)
        & (match_b[:, 0] >= base.MATCH_BORDER_PX)
        & (match_b[:, 0] < base.LOAD_WIDTH - base.MATCH_BORDER_PX)
        & (match_b[:, 1] >= base.MATCH_BORDER_PX)
        & (match_b[:, 1] < base.LOAD_HEIGHT - base.MATCH_BORDER_PX)
    )
    match_a, match_b = match_a[border], match_b[border]
    pixels_a = retri.original_pixels(match_a, box_a)
    pixels_b = retri.original_pixels(match_b, box_b)
    tri = retri.triangulate(pixels_a, pixels_b, frame_a, frame_b)
    keep = tri["cheirality"]
    centre_a = -frame_a["R"].T @ frame_a["t"]
    centre_b = -frame_b["R"].T @ frame_b["t"]
    return {
        "building_id": short,
        "pair_rank": rank,
        "view_a": a["stem"],
        "view_b": b["stem"],
        "crop_box_a_xyxy": list(box_a),
        "crop_box_b_xyxy": list(box_b),
        "known_colmap_baseline_m": float(np.linalg.norm(centre_a - centre_b)),
        "reciprocal_match_count": reciprocal_count,
        "border_match_count": int(len(match_a)),
        "dlt_finite_count": int(np.count_nonzero(tri["finite"])),
        "cheirality_pass_count": int(np.count_nonzero(keep)),
        "world": tri["world_all"][keep],
        "pixels_a": pixels_a[keep],
        "pixels_b": pixels_b[keep],
        "max_error": tri["max_error"][keep],
        "raw_definition": raw_definition,
    }


def old_pair_2px(short: str, rank: int) -> np.ndarray:
    path = OLD_PAIR_DIR / f"{short}_rank{rank:02d}.npz"
    with np.load(path, allow_pickle=False) as archive:
        return np.asarray(archive["world_local_xyz"], dtype=np.float64)


def pair_progress_row(
    detail: dict[str, Any], path: Path, config: dict[str, Any], elapsed: float,
    new_inference: bool,
) -> dict[str, Any]:
    block_a = rescore.acquisition_block(detail["view_a"])
    block_b = rescore.acquisition_block(detail["view_b"])
    relation = "cross_acquisition_block" if block_a != block_b else "same_acquisition_block"
    eligible = relation == "cross_acquisition_block" and float(detail["known_colmap_baseline_m"]) > 0.06
    counts = {
        f"reprojection_{label}_count": int(np.count_nonzero(detail["max_error"] <= limit))
        for label, limit in (("2px", 2.0), ("4px", 4.0), ("8px", 8.0))
    }
    old_world = old_pair_2px(detail["building_id"], int(detail["pair_rank"]))
    new_world = detail["world"][detail["max_error"] <= 2.0]
    exact_count = len(old_world) == len(new_world)
    max_diff = float(np.max(np.abs(old_world - new_world))) if exact_count and len(old_world) else (0.0 if exact_count else None)
    matches_old = bool(exact_count and (max_diff is not None) and max_diff <= 1e-9)
    return {
        "building_id": f"DEBY_LOD2_{detail['building_id']}",
        "pair_rank": detail["pair_rank"],
        "view_a": detail["view_a"],
        "view_b": detail["view_b"],
        "acquisition_block_a": block_a,
        "acquisition_block_b": block_b,
        "pair_relation": relation,
        "known_colmap_baseline_m": detail["known_colmap_baseline_m"],
        "eligible_summary_pair": eligible,
        "reciprocal_match_count": detail["reciprocal_match_count"],
        "border_match_count": detail["border_match_count"],
        "dlt_finite_count": detail["dlt_finite_count"],
        "cheirality_pass_count": detail["cheirality_pass_count"],
        **counts,
        "raw_count": detail["cheirality_pass_count"],
        "old_2px_count": len(old_world),
        "two_px_count_matches_old": matches_old,
        "two_px_world_max_abs_diff_m": max_diff,
        "crop_box_a_xyxy": ";".join(map(str, detail["crop_box_a_xyxy"])),
        "crop_box_b_xyxy": ";".join(map(str, detail["crop_box_b_xyxy"])),
        "status": "pass" if elapsed <= float(config["time_limits_s"]["pair"]) else "pass_over_time_limit",
        "failure_reason": "" if elapsed <= float(config["time_limits_s"]["pair"]) else f"elapsed>{config['time_limits_s']['pair']}",
        "elapsed_s": elapsed,
        "pair_time_limit_s": config["time_limits_s"]["pair"],
        "cache_path": rel(path),
        "cache_sha256": sha256_file(path),
        "new_mast3r_inference_runs": int(new_inference),
        "cache_reuse_runs": int(not new_inference),
        "learning_runs_started": 0,
    }


def expected_two_px_counts() -> dict[str, int]:
    with OLD_RESCORE_CSV.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    return {
        row["building_id"].removeprefix("DEBY_LOD2_"): int(row["inside_point_count"])
        for row in rows
        if row["row_type"] == "building_summary"
    }


def score_building(
    short: str, details: Sequence[dict[str, Any]], pair_rows: Sequence[dict[str, Any]],
    config: dict[str, Any], footprint: Any, roof: Sequence[Any], offset: np.ndarray, geoid: float,
    expected_two_px: int,
) -> list[dict[str, Any]]:
    row_by_rank = {int(row["pair_rank"]): row for row in pair_rows}
    eligible = [detail for detail in details if bool(row_by_rank[int(detail["pair_rank"])]["eligible_summary_pair"])]
    output: list[dict[str, Any]] = []
    for order, dial in enumerate(config["reprojection_dial"]):
        limit = dial["max_reprojection_error_px"]
        selected_parts = [
            detail["world"] if limit is None else detail["world"][detail["max_error"] <= float(limit)]
            for detail in eligible
        ]
        selected = np.concatenate(selected_parts, axis=0) if selected_parts else np.zeros((0, 3), dtype=np.float64)
        if len(selected):
            inside_mask = contains_xy(
                footprint, selected[:, 0] + offset[0], selected[:, 1] + offset[1]
            )
            inside = selected[inside_mask]
        else:
            inside = np.zeros((0, 3), dtype=np.float64)
        references = rescore.reference_z_for_points(inside, roof, offset, geoid)
        finite_reference = np.isfinite(references)
        errors = np.abs(inside[finite_reference, 2] - references[finite_reference])
        z_stats = finite_stats(inside[:, 2] if len(inside) else np.zeros(0))
        ref_stats = finite_stats(references)
        error_stats = finite_stats(errors)
        coverage = rescore.grid_coverage(inside, footprint, offset, float(config["coverage"]["grid_m"]))
        nonzero = 0
        for detail in eligible:
            world = detail["world"] if limit is None else detail["world"][detail["max_error"] <= float(limit)]
            if len(world) and np.any(contains_xy(footprint, world[:, 0] + offset[0], world[:, 1] + offset[1])):
                nonzero += 1
        coverage_ratio = coverage["coverage_ratio"]
        dz = error_stats["median"]
        meets = bool(
            coverage_ratio is not None
            and float(coverage_ratio) >= float(config["good_operating_point"]["minimum_coverage"])
            and dz is not None
            and float(dz) <= float(config["good_operating_point"]["maximum_median_abs_delta_z_m"])
        )
        output.append({
            "building_id": f"DEBY_LOD2_{short}",
            "threshold_label": dial["label"],
            "threshold_order": order,
            "max_reprojection_error_px": limit,
            "raw_definition": config["raw_definition"],
            "selected_dlt_point_count": len(selected),
            "footprint_inside_point_count": len(inside),
            "finite_lod2_height_score_count": int(np.count_nonzero(finite_reference)),
            "inside_z_median_local_m": z_stats["median"],
            "inside_z_mad_m": z_stats["mad"],
            "reference_roof_z_median_local_m": ref_stats["median"],
            "abs_delta_z_median_m": error_stats["median"],
            "abs_delta_z_mad_m": error_stats["mad"],
            "point_to_lod2_rms_m": error_stats["rms"],
            "coverage_grid_m": coverage["coverage_grid_m"],
            "coverage_eligible_cell_count": coverage["coverage_eligible_cell_count"],
            "coverage_occupied_cell_count": coverage["coverage_occupied_cell_count"],
            "coverage_ratio": coverage_ratio,
            "selected_pair_count": len(details),
            "eligible_pair_count": len(eligible),
            "nonzero_inside_pair_count": nonzero,
            "two_px_expected_inside_count": expected_two_px,
            "two_px_inside_count_matches_locked_cache": (
                len(inside) == expected_two_px if dial["label"] == "2px" else None
            ),
            "meets_locked_operating_bounds": meets,
            "selected_good_operating_point": False,
            "building_operating_point": "PENDING",
            "operating_point_rule": config["good_operating_point"]["selection_rule"],
            "summary_aggregation": config["summary_pair_rule"],
            "raw_cache_status": "complete",
            "new_mast3r_inference_runs": sum(int(row["new_mast3r_inference_runs"]) for row in pair_rows),
            "cache_reuse_runs": sum(int(row["cache_reuse_runs"]) for row in pair_rows),
            "candidate_generation_gt_used": False,
            "footprint_role": config["execution_lock"]["footprint_role"],
            "lod2_role": config["execution_lock"]["lod2_role"],
            "crs": "EPSG:25832",
            "learning_runs_started": 0,
            "status": "scored",
        })
    qualifying = [row for row in output if row["meets_locked_operating_bounds"]]
    if qualifying:
        chosen = min(
            qualifying,
            key=lambda row: (
                -float(row["coverage_ratio"]),
                float(row["abs_delta_z_median_m"]),
                int(row["threshold_order"]),
            ),
        )
        operating_point = str(chosen["threshold_label"])
        chosen["selected_good_operating_point"] = True
    else:
        operating_point = "INSUFFICIENT_INSIDE_POINTS"
    for row in output:
        row["building_operating_point"] = operating_point
    two_px = next(row for row in output if row["threshold_label"] == "2px")
    if not bool(two_px["two_px_inside_count_matches_locked_cache"]):
        raise RuntimeError(
            f"2px pooled inside-count drift for {short}: "
            f"{two_px['footprint_inside_point_count']} != {expected_two_px}"
        )
    return output


def make_figure(rows: Sequence[dict[str, Any]], config: dict[str, Any]) -> None:
    FIGURE.parent.mkdir(parents=True, exist_ok=True)
    labels = [item["label"] for item in config["reprojection_dial"]]
    x = np.arange(len(labels), dtype=np.float64)
    styles = {
        "4907199": {"color": "#2458A6", "marker": "o", "linestyle": "-"},
        "8568392": {"color": "#7698C9", "marker": "s", "linestyle": "--"},
    }
    fig, axes = plt.subplots(1, 2, figsize=(12.5, 5.5), dpi=180)
    for short, style in styles.items():
        selected = sorted(
            [row for row in rows if row["building_id"] == f"DEBY_LOD2_{short}"],
            key=lambda row: int(row["threshold_order"]),
        )
        coverage = np.asarray([float(row["coverage_ratio"]) for row in selected], dtype=np.float64)
        dz = np.asarray([
            float(row["abs_delta_z_median_m"]) if row["abs_delta_z_median_m"] is not None else np.nan
            for row in selected
        ])
        axes[0].plot(x, coverage, linewidth=1.8, markersize=6, label=short, **style)
        axes[1].plot(x, dz, linewidth=1.8, markersize=6, label=short, **style)
        for index, value in enumerate(coverage):
            axes[0].annotate(f"{value:.3f}", (x[index], value), xytext=(0, 7), textcoords="offset points", ha="center", fontsize=8)
        for index, value in enumerate(dz):
            if math.isfinite(float(value)):
                axes[1].annotate(f"{value:.3f}", (x[index], value), xytext=(0, 7), textcoords="offset points", ha="center", fontsize=8)
    axes[0].axhline(
        float(config["good_operating_point"]["minimum_coverage"]),
        color="#555555", linestyle=":", linewidth=1.2, label="locked bound",
    )
    axes[1].axhline(
        float(config["good_operating_point"]["maximum_median_abs_delta_z_m"]),
        color="#555555", linestyle=":", linewidth=1.2, label="locked bound",
    )
    axes[0].set_title("Footprint-intersecting 0.5 m cell coverage")
    axes[1].set_title("Median vertical absolute error to LoD2")
    axes[0].set_ylabel("coverage ratio")
    axes[1].set_ylabel("median |delta z| [m]")
    for ax in axes:
        ax.set_xticks(x, labels)
        ax.set_xlabel("maximum fixed-pose reprojection error")
        ax.grid(axis="y", color="#D9DDE3", linewidth=0.7)
        ax.spines[["top", "right"]].set_visible(False)
        ax.legend(loc="best", fontsize=8)
    axes[0].set_ylim(bottom=0.0)
    axes[1].set_ylim(bottom=0.0)
    fig.suptitle("S3-A-prime FM fixed-pose reprojection dial", fontsize=13, color="#222222")
    fig.text(
        0.5, 0.915,
        "Pooled cross-acquisition-block pairs; footprint/LoD2 applied only after finite positive-depth DLT",
        ha="center", fontsize=9, color="#4A4A4A",
    )
    fig.subplots_adjust(left=0.08, right=0.98, bottom=0.14, top=0.84, wspace=0.25)
    fig.savefig(FIGURE, facecolor="white")
    plt.close(fig)


def write_versions(args: argparse.Namespace, env: dict[str, Any]) -> None:
    values = [
        f"created_utc={now()}",
        f"git_head={git_value('rev-parse', 'HEAD')}",
        f"branch={git_value('branch', '--show-current')}",
        f"docker_tag={env['runtime_lock']['docker_image_tag']}",
        f"docker_image_id={env['runtime_lock']['docker_image_id']}",
        f"mast3r_commit={env['code']['mast3r_commit']}",
        f"dust3r_commit={env['code']['dust3r_commit']}",
        f"croco_commit={env['code']['croco_commit']}",
        f"model_revision={base.MODEL_REVISION}",
        f"weights_sha256={base.MODEL_SHA256}",
        f"torch={torch.__version__}",
        f"numpy={np.__version__}",
        f"device={args.device}",
        "learning_runs_started=0",
    ]
    atomic_text(VERSIONS, "\n".join(values) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-dir", type=Path, required=True)
    parser.add_argument("--device", default="cuda:0")
    args = parser.parse_args()
    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    config_sha256 = sha256_file(CONFIG)
    env = json.loads(ENV_MANIFEST.read_text(encoding="utf-8"))
    lock = config["runtime_lock"]
    weights = args.model_dir / "model.safetensors"
    if config["execution_lock"]["learning_runs_allowed"] != 0:
        raise RuntimeError("learning lock mismatch")
    if (
        args.model_dir.name != lock["model_revision"]
        or weights.stat().st_size != int(lock["weights_bytes"])
        or sha256_file(weights) != lock["weights_sha256"]
    ):
        raise RuntimeError("MASt3R model lock mismatch")
    if env["runtime_lock"]["docker_image_id"] != lock["docker_image_id"]:
        raise RuntimeError("Docker image lock mismatch")
    if args.device.startswith("cuda") and not torch.cuda.is_available():
        raise RuntimeError("CUDA requested but unavailable")

    RUN_DIR.mkdir(parents=True, exist_ok=True)
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    write_versions(args, env)
    log("START phase0_fm_dense_dial learning_runs_started=0 candidate_generation_gt_used=false")
    update_progress(config, [], [], None, "running")

    frames = base.load_frames()
    views = base.load_view_rows()
    expected = expected_two_px_counts()
    offset = base.load_offset()
    geoid = float(json.loads(PROJECTION_DATUM.read_text(encoding="utf-8"))["orthometric_geoid_m"])
    model = None
    pair_rows: list[dict[str, Any]] = []
    details_by_building: dict[str, list[dict[str, Any]]] = {short: [] for short in config["targets"]}
    dial_rows: list[dict[str, Any]] = []

    # Candidate generation ends here; no footprint or LoD2 object has yet been loaded.
    for short in config["targets"]:
        building_started = time.monotonic()
        selected_pairs = base.select_pairs(views[short])
        local_rows: list[dict[str, Any]] = []
        for rank, pair in enumerate(selected_pairs, start=1):
            active = {"building_id": short, "pair_rank": rank, "started_utc": now()}
            update_progress(config, pair_rows, dial_rows, active, "running")
            started = time.monotonic()
            path = cache_path(short, rank)
            new_inference = False
            try:
                if time.monotonic() - building_started > float(config["time_limits_s"]["building"]):
                    raise TimeoutError(f"building elapsed>{config['time_limits_s']['building']}s")
                if path.exists():
                    detail = load_raw_cache(path, config_sha256)
                    log(f"PAIR_CACHE_REUSED building={short} rank={rank} cache={rel(path)}")
                else:
                    if model is None:
                        model = base.AsymmetricMASt3R.from_pretrained(str(args.model_dir)).to(args.device).eval()
                    detail = infer_raw_pair(model, short, rank, pair, frames, args.device, config["raw_definition"])
                    save_raw_cache(path, detail, config_sha256)
                    new_inference = True
                elapsed = time.monotonic() - started
                row = pair_progress_row(detail, path, config, elapsed, new_inference)
                if not row["two_px_count_matches_old"]:
                    raise RuntimeError(
                        f"2px cache drift building={short} rank={rank} "
                        f"new={row['reprojection_2px_count']} old={row['old_2px_count']} "
                        f"maxdiff={row['two_px_world_max_abs_diff_m']}"
                    )
                details_by_building[short].append(detail)
                log(
                    f"PAIR_DONE building={short} rank={rank} reciprocal={row['reciprocal_match_count']} "
                    f"raw={row['raw_count']} n2={row['reprojection_2px_count']} n4={row['reprojection_4px_count']} "
                    f"n8={row['reprojection_8px_count']} exact2=true elapsed_s={elapsed:.3f}"
                )
            except Exception as exc:
                elapsed = time.monotonic() - started
                row = {
                    "building_id": f"DEBY_LOD2_{short}", "pair_rank": rank,
                    "view_a": pair["a"]["stem"], "view_b": pair["b"]["stem"],
                    "status": "failed_pair", "failure_reason": f"{type(exc).__name__}: {exc}",
                    "elapsed_s": elapsed, "pair_time_limit_s": config["time_limits_s"]["pair"],
                    "new_mast3r_inference_runs": int(new_inference), "cache_reuse_runs": 0,
                    "learning_runs_started": 0,
                }
                log(f"PAIR_FAILED building={short} rank={rank} reason={row['failure_reason']}")
            local_rows.append(row)
            pair_rows.append(row)
            atomic_csv(PAIR_CSV, pair_rows, PAIR_FIELDS)
            update_progress(config, pair_rows, dial_rows, None, "running")
        if any(row["status"] == "failed_pair" for row in local_rows):
            log(f"BUILDING_PARTIAL building={short} failed_pairs={sum(row['status'] == 'failed_pair' for row in local_rows)}")
            continue

        # Scoring objects are deliberately loaded only after raw DLT caches for the building exist.
        footprints = base.load_footprints()
        lod2 = rescore.load_lod2()
        local_dial = score_building(
            short, details_by_building[short], local_rows, config,
            footprints[base.full_id(short)], lod2[short]["RoofSurface"], offset, geoid, expected[short],
        )
        dial_rows.extend(local_dial)
        atomic_csv(OUT_CSV, dial_rows, DIAL_FIELDS)
        update_progress(config, pair_rows, dial_rows, None, "running")
        chosen = local_dial[0]["building_operating_point"]
        log(
            f"BUILDING_DONE building={short} dial_rows={len(local_dial)} operating_point={chosen} "
            f"elapsed_s={time.monotonic() - building_started:.3f}"
        )

    if len(dial_rows) != len(config["targets"]) * len(config["reprojection_dial"]):
        update_progress(config, pair_rows, dial_rows, None, "partial")
        raise RuntimeError(f"incomplete dial rows: {len(dial_rows)}")
    make_figure(dial_rows, config)
    atomic_csv(OUT_CSV, dial_rows, DIAL_FIELDS)
    update_progress(config, pair_rows, dial_rows, None, "complete")
    log(f"FINAL rows={len(dial_rows)} pair_rows={len(pair_rows)} figure={rel(FIGURE)}")

    source_paths = [
        CONFIG, Path(__file__).resolve(), ENV_MANIFEST, PROJECTION_DATUM, base.PJPL, base.FOOTPRINTS,
        base.TRAIN_MANIFEST, base.SPARSE_DIR / "cameras.bin", base.SPARSE_DIR / "images.bin",
        OLD_MANIFEST, OLD_RESCORE_CSV,
        REPO / "phases/p2-gsjso/scripts/e5_c001_s3ap_fm_retriangulation.py",
        REPO / "phases/p2-gsjso/scripts/e5_c001_s3ap_fm_rescore.py",
        REPO / "phases/p2-gsjso/scripts/e5_c001_s3ap_fm_retri_rescore.py",
        *sorted(rescore.LOD2_DIR.glob("*.gml")),
        *[frames[item["stem"]]["path"] for short in config["targets"] for item in views[short]],
        *[base.REGION_DIR / f"{item['stem']}.npz" for short in config["targets"] for item in views[short]],
        *[OLD_PAIR_DIR / f"{short}_rank{rank:02d}.npz" for short in config["targets"] for rank in range(1, len(base.select_pairs(views[short])) + 1)],
    ]
    output_paths = [OUT_CSV, FIGURE, PROGRESS, PAIR_CSV, RUN_LOG, VERSIONS, *sorted(RAW_DIR.glob("*.npz"))]
    manifest = {
        "schema": "jointbuildgs.s3ap.fm_dense_dial.manifest.v1",
        "created_utc": now(),
        "git_head_at_measurement": git_value("rev-parse", "HEAD"),
        "branch": git_value("branch", "--show-current"),
        "config": rel(CONFIG),
        "config_sha256": config_sha256,
        "runtime_lock": config["runtime_lock"],
        "raw_definition": config["raw_definition"],
        "pair_selection_rule": config["pair_selection_rule"],
        "summary_pair_rule": config["summary_pair_rule"],
        "coverage_rule": config["coverage"],
        "good_operating_point_rule": config["good_operating_point"],
        "gt_separation": {
            "candidate_generation_gt_used": False,
            "footprint": config["execution_lock"]["footprint_role"],
            "lod2": config["execution_lock"]["lod2_role"],
        },
        "learning_runs_started": 0,
        "new_mast3r_inference_runs": sum(int(row.get("new_mast3r_inference_runs", 0)) for row in pair_rows),
        "cache_reuse_runs": sum(int(row.get("cache_reuse_runs", 0)) for row in pair_rows),
        "pair_row_count": len(pair_rows),
        "dial_row_count": len(dial_rows),
        "two_px_pair_exact_reproduction_count": sum(bool(row.get("two_px_count_matches_old")) for row in pair_rows),
        "two_px_pair_expected_count": len(pair_rows),
        "source_sha256": {rel(path): sha256_file(path) for path in sorted(set(source_paths))},
        "model_weights_sha256_verified": sha256_file(weights),
        "output_sha256": {rel(path): sha256_file(path) for path in output_paths},
        "outputs": [rel(path) for path in output_paths],
        "interpretation_or_verdict": None,
        "no_seed_or_training_use": True,
    }
    atomic_text(MANIFEST, json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")


if __name__ == "__main__":
    main()
