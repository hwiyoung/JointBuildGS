#!/usr/bin/env python3
"""S3-A-prime learning-zero fixed-COLMAP-pose retriangulation.

MASt3R contributes reciprocal 2D correspondences only.  Its pointmaps, crop
gauge, PnP output, and similarity alignment are never read by this task.
Candidate generation ends before footprint/LoD2 scoring begins.
"""
from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import math
import os
import subprocess
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence

os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib")
os.environ.setdefault("XDG_CACHE_HOME", "/tmp")

import matplotlib
import numpy as np
import torch
from PIL import Image as PILImage
from shapely import contains_xy

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

REPO = Path(__file__).resolve().parents[3]
BASE_PATH = REPO / "phases/p2-gsjso/scripts/e5_c001_s3ap_fm_rescore.py"
spec = importlib.util.spec_from_file_location("s3ap_fm_base", BASE_PATH)
if spec is None or spec.loader is None:
    raise RuntimeError(f"cannot import {BASE_PATH}")
base = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base)

RUN_ID = "20260714_e5_c001_s3ap_fm_retriangulation"
RUN_DIR = REPO / "phases/p2-gsjso/runs" / RUN_ID
PAIR_DIR = RUN_DIR / "pairs"
PROGRESS = RUN_DIR / "progress.json"
RUN_LOG = RUN_DIR / "run.log"
VERSIONS = RUN_DIR / "versions.txt"
MANIFEST = RUN_DIR / "manifest.json"
OUT_CSV = REPO / "docs/e5_c001_s3ap_fm_retriangulation.csv"
REPORT = REPO / "docs/W_E5_C001_S3Ap_FM재삼각측량_20260714.md"
FIG_DIR = REPO / "docs/figs/e5_c001_s3ap_fm_retri"
OLD_CSV = REPO / "docs/e5_c001_s3ap_fm_rescore.csv"

REPROJECTION_THRESHOLD_PX = 2.0
DEGENERATE_BASELINE_MAX_M = 0.06
PAIR_TIME_LIMIT_S = 600
BUILDING_TIME_LIMIT_S = 7200

FIELDS = [
    "row_type", "building_id", "pair_rank", "view_a", "view_b",
    "address_support_a", "address_support_b", "crop_box_a_xyxy", "crop_box_b_xyxy",
    "known_colmap_baseline_m", "baseline_class", "reciprocal_match_count",
    "border_match_count", "dlt_finite_count", "cheirality_pass_count",
    "reprojection_pass_count", "reprojection_pass_rate", "reprojection_error_median_px",
    "reconstructed_candidate_count", "footprint_inside_count", "roof_candidate_count",
    "abs_delta_z_median_m", "abs_delta_z_within_pair_mad_m", "abs_delta_z_within_pair_std_m",
    "abs_delta_z_across_pair_mad_m", "footprint_outside_count", "footprint_outside_rate",
    "old_footprint_inside_count", "old_roof_candidate_count", "old_abs_delta_z_median_m",
    "old_footprint_outside_rate", "old_status", "origin_separation_class",
    "ground_z_q10_local_m", "reference_roof_z_local_m", "selected_pair_count",
    "completed_pair_count", "nondegenerate_completed_pair_count", "status", "failure_reason",
    "pair_elapsed_s", "pair_time_limit_s", "building_elapsed_s", "building_time_limit_s",
    "view_pair_selection_rule", "match_rule", "triangulation_rule", "score_rule", "gt_role",
    "learning_runs_started",
]


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


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


def fmt(value: Any) -> Any:
    if value is None:
        return ""
    if isinstance(value, (float, np.floating)):
        return "" if not math.isfinite(float(value)) else f"{float(value):.6f}"
    return value


def atomic_csv(rows: Sequence[dict[str, Any]]) -> None:
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    tmp = OUT_CSV.with_name(OUT_CSV.name + ".tmp")
    with tmp.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS, lineterminator="\n", extrasaction="ignore")
        writer.writeheader()
        writer.writerows({key: fmt(row.get(key)) for key in FIELDS} for row in rows)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, OUT_CSV)


def median(rows: Sequence[dict[str, Any]], key: str) -> float | None:
    values = [float(row[key]) for row in rows if row.get(key) not in (None, "")]
    return float(np.median(values)) if values else None


def stats(values: np.ndarray) -> tuple[float | None, float | None, float | None]:
    values = np.asarray(values, dtype=np.float64)
    values = values[np.isfinite(values)]
    if not len(values):
        return None, None, None
    centre = float(np.median(values))
    return centre, float(np.median(np.abs(values - centre))), float(np.std(values))


def original_pixels(matches: np.ndarray, box: tuple[int, int, int, int]) -> np.ndarray:
    x0, y0, x1, y1 = box
    out = matches.astype(np.float64).copy()
    out[:, 0] = x0 + out[:, 0] / (base.LOAD_WIDTH / float(x1 - x0))
    out[:, 1] = y0 + out[:, 1] / (base.LOAD_HEIGHT / float(y1 - y0))
    return out


def dlt_one(pixel_a: np.ndarray, pixel_b: np.ndarray, P_a: np.ndarray, P_b: np.ndarray) -> np.ndarray:
    A = np.stack([
        pixel_a[0] * P_a[2] - P_a[0],
        pixel_a[1] * P_a[2] - P_a[1],
        pixel_b[0] * P_b[2] - P_b[0],
        pixel_b[1] * P_b[2] - P_b[1],
    ])
    _, _, vt = np.linalg.svd(A.astype(np.float64), full_matrices=False)
    homogeneous = vt[-1]
    if not np.isfinite(homogeneous).all() or abs(homogeneous[3]) <= 1e-12:
        return np.full(3, np.nan, dtype=np.float64)
    return homogeneous[:3] / homogeneous[3]


def project(points: np.ndarray, frame: dict[str, Any]) -> tuple[np.ndarray, np.ndarray]:
    camera = (frame["R"] @ points.T).T + frame["t"][None, :]
    pixels_h = (frame["K"] @ camera.T).T
    pixels = np.full((len(points), 2), np.nan, dtype=np.float64)
    forward = camera[:, 2] > 1e-12
    pixels[forward] = pixels_h[forward, :2] / pixels_h[forward, 2:3]
    return pixels, camera[:, 2]


def triangulate(
    pixels_a: np.ndarray, pixels_b: np.ndarray, frame_a: dict[str, Any], frame_b: dict[str, Any]
) -> dict[str, np.ndarray]:
    if len(pixels_a) == 0:
        return {
            "world_all": np.zeros((0, 3), dtype=np.float64), "finite": np.zeros(0, dtype=bool),
            "cheirality": np.zeros(0, dtype=bool), "reprojection": np.zeros(0, dtype=bool),
            "max_error": np.zeros(0, dtype=np.float64), "pixels_a": pixels_a, "pixels_b": pixels_b,
        }
    P_a = frame_a["K"] @ np.column_stack([frame_a["R"], frame_a["t"]])
    P_b = frame_b["K"] @ np.column_stack([frame_b["R"], frame_b["t"]])
    world = np.stack([dlt_one(a, b, P_a, P_b) for a, b in zip(pixels_a, pixels_b)], axis=0)
    finite = np.isfinite(world).all(axis=1)
    reproj_a, depth_a = project(world, frame_a)
    reproj_b, depth_b = project(world, frame_b)
    cheirality = finite & (depth_a > 0) & (depth_b > 0)
    err_a = np.linalg.norm(reproj_a - pixels_a, axis=1)
    err_b = np.linalg.norm(reproj_b - pixels_b, axis=1)
    max_error = np.maximum(err_a, err_b)
    reprojection = cheirality & np.isfinite(max_error) & (max_error <= REPROJECTION_THRESHOLD_PX)
    return {
        "world_all": world,
        "finite": finite,
        "cheirality": cheirality,
        "reprojection": reprojection,
        "max_error": max_error,
        "pixels_a": pixels_a,
        "pixels_b": pixels_b,
    }


def old_rows() -> tuple[dict[tuple[str, int], dict[str, str]], dict[str, dict[str, str]]]:
    pairs: dict[tuple[str, int], dict[str, str]] = {}
    summaries: dict[str, dict[str, str]] = {}
    for row in base.read_csv(OLD_CSV):
        short = row["building_id"].removeprefix("DEBY_LOD2_")
        if row["row_type"] == "view_pair":
            pairs[(short, int(row["pair_rank"]))] = row
        elif row["row_type"] == "building_summary":
            summaries[short] = row
    return pairs, summaries


def compare_class(baseline_class: str, new_roof: Any, new_error: Any, old_error: Any) -> str:
    if baseline_class == "same_strip_degenerate_baseline_le_0.06m":
        return "baseline_degenerate_excluded"
    if new_roof not in (None, "") and float(new_roof) >= 1 and new_error not in (None, "") and old_error not in (None, ""):
        if float(new_error) < float(old_error):
            return "recovered_by_fixed_pose_retriangulation"
    return "still_bad_after_fixed_pose_retriangulation"


def common_row(short: str, rank: Any, ground: float, reference: float) -> dict[str, Any]:
    return {
        "row_type": "view_pair", "building_id": base.full_id(short), "pair_rank": rank,
        "ground_z_q10_local_m": ground, "reference_roof_z_local_m": reference,
        "pair_time_limit_s": PAIR_TIME_LIMIT_S, "building_time_limit_s": BUILDING_TIME_LIMIT_S,
        "view_pair_selection_rule": (
            "all locked P-J/P-L visible-view combinations; sort by minimum frozen address support desc, "
            "then sum desc, stems asc; cap 10"
        ),
        "match_rule": "MASt3R reciprocal descriptor NN stride8; 3px crop border; raw 2D only",
        "triangulation_rule": (
            "crop pixels inverted to source pixels without half-pixel shift; float64 linear DLT with fixed "
            "COLMAP K,R,t; both depths >0; max(each-view source-pixel reprojection error)<=2.0px"
        ),
        "score_rule": "after DLT only: footprint containment; roof z>=observed ground q10+1.5m; LoD2 abs z error",
        "gt_role": "footprint and LoD2 roof z used only after fixed-pose DLT for scoring/overlay",
        "learning_runs_started": 0,
    }


def measure_pair(
    model: Any,
    short: str,
    rank: int,
    pair: dict[str, Any],
    frames: dict[str, dict[str, Any]],
    footprint: Any,
    offset: np.ndarray,
    ground: float,
    reference: float,
    old: dict[str, str],
    device: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    started = time.monotonic()
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
        desc_a, desc_b, subsample_or_initxy1=base.MATCH_SUBSAMPLE, device=device, dist="dot", block_size=2**13
    )
    reciprocal_count = int(len(match_a))
    border = (
        (match_a[:, 0] >= base.MATCH_BORDER_PX) & (match_a[:, 0] < base.LOAD_WIDTH - base.MATCH_BORDER_PX)
        & (match_a[:, 1] >= base.MATCH_BORDER_PX) & (match_a[:, 1] < base.LOAD_HEIGHT - base.MATCH_BORDER_PX)
        & (match_b[:, 0] >= base.MATCH_BORDER_PX) & (match_b[:, 0] < base.LOAD_WIDTH - base.MATCH_BORDER_PX)
        & (match_b[:, 1] >= base.MATCH_BORDER_PX) & (match_b[:, 1] < base.LOAD_HEIGHT - base.MATCH_BORDER_PX)
    )
    match_a, match_b = match_a[border], match_b[border]
    pixels_a, pixels_b = original_pixels(match_a, box_a), original_pixels(match_b, box_b)
    tri = triangulate(pixels_a, pixels_b, frame_a, frame_b)
    keep = tri["reprojection"]
    world = tri["world_all"][keep]
    kept_a, kept_b = pixels_a[keep], pixels_b[keep]
    max_error = tri["max_error"][keep]
    centre_a = -frame_a["R"].T @ frame_a["t"]
    centre_b = -frame_b["R"].T @ frame_b["t"]
    baseline = float(np.linalg.norm(centre_b - centre_a))
    baseline_class = (
        "same_strip_degenerate_baseline_le_0.06m"
        if baseline <= DEGENERATE_BASELINE_MAX_M
        else "nondegenerate_baseline_gt_0.06m"
    )
    if len(world):
        inside = contains_xy(footprint, world[:, 0] + offset[0], world[:, 1] + offset[1])
    else:
        inside = np.zeros(0, dtype=bool)
    roof = inside & (world[:, 2] >= ground + base.UPPER_OFFSET_M) if len(world) else inside
    errors = np.abs(world[roof, 2] - reference) if len(world) else np.zeros(0)
    error_median, error_mad, error_std = stats(errors)
    outside_count = int(np.count_nonzero(~inside))
    elapsed = time.monotonic() - started
    row = common_row(short, rank, ground, reference)
    row.update({
        "view_a": a["stem"], "view_b": b["stem"],
        "address_support_a": a["support"], "address_support_b": b["support"],
        "crop_box_a_xyxy": ";".join(map(str, box_a)), "crop_box_b_xyxy": ";".join(map(str, box_b)),
        "known_colmap_baseline_m": baseline, "baseline_class": baseline_class,
        "reciprocal_match_count": reciprocal_count, "border_match_count": len(match_a),
        "dlt_finite_count": int(np.count_nonzero(tri["finite"])),
        "cheirality_pass_count": int(np.count_nonzero(tri["cheirality"])),
        "reprojection_pass_count": len(world),
        "reprojection_pass_rate": float(len(world) / len(match_a)) if len(match_a) else None,
        "reprojection_error_median_px": float(np.median(max_error)) if len(max_error) else None,
        "reconstructed_candidate_count": len(world), "footprint_inside_count": int(np.count_nonzero(inside)),
        "roof_candidate_count": int(np.count_nonzero(roof)), "abs_delta_z_median_m": error_median,
        "abs_delta_z_within_pair_mad_m": error_mad, "abs_delta_z_within_pair_std_m": error_std,
        "footprint_outside_count": outside_count,
        "footprint_outside_rate": float(outside_count / len(world)) if len(world) else None,
        "old_footprint_inside_count": old.get("footprint_inside_count", ""),
        "old_roof_candidate_count": old.get("roof_candidate_count", ""),
        "old_abs_delta_z_median_m": old.get("abs_delta_z_median_m", ""),
        "old_footprint_outside_rate": old.get("footprint_outside_rate", ""), "old_status": old.get("status", ""),
        "origin_separation_class": compare_class(baseline_class, int(np.count_nonzero(roof)), error_median, old.get("abs_delta_z_median_m")),
        "status": "pass" if elapsed <= PAIR_TIME_LIMIT_S else "pass_over_time_limit",
        "failure_reason": "" if elapsed <= PAIR_TIME_LIMIT_S else f"elapsed={elapsed:.3f}>{PAIR_TIME_LIMIT_S}",
        "pair_elapsed_s": elapsed,
    })
    detail = {
        "short": short, "rank": rank, "view_a": a["stem"], "view_b": b["stem"],
        "pixels_a": kept_a, "pixels_b": kept_b, "world": world, "inside": inside, "roof": roof,
        "max_error": max_error, "row": row,
    }
    return row, detail


def failed_pair(short: str, rank: int, pair: dict[str, Any], ground: float, reference: float, exc: Exception, elapsed: float) -> dict[str, Any]:
    row = common_row(short, rank, ground, reference)
    row.update({
        "view_a": pair["a"]["stem"], "view_b": pair["b"]["stem"],
        "address_support_a": pair["a"]["support"], "address_support_b": pair["b"]["support"],
        "status": "failed_pair", "failure_reason": f"{type(exc).__name__}: {exc}", "pair_elapsed_s": elapsed,
    })
    return row


def summary_row(
    short: str, rows: list[dict[str, Any]], ground: float, reference: float, old_summary: dict[str, str], building_elapsed: float
) -> dict[str, Any]:
    completed = [row for row in rows if str(row["status"]).startswith("pass")]
    nondeg = [row for row in completed if row.get("baseline_class") == "nondegenerate_baseline_gt_0.06m"]
    pair_errors = [float(row["abs_delta_z_median_m"]) for row in nondeg if row.get("abs_delta_z_median_m") not in (None, "")]
    error_median = float(np.median(pair_errors)) if pair_errors else None
    across_mad = float(np.median(np.abs(np.asarray(pair_errors) - error_median))) if pair_errors else None
    roof_median = median(nondeg, "roof_candidate_count")
    classification = compare_class(
        "nondegenerate_baseline_gt_0.06m" if nondeg else "same_strip_degenerate_baseline_le_0.06m",
        roof_median,
        error_median,
        old_summary.get("abs_delta_z_median_m"),
    )
    row = common_row(short, "MEDIAN_NONDEGENERATE_PAIRS", ground, reference)
    row.update({
        "row_type": "building_summary", "known_colmap_baseline_m": median(nondeg, "known_colmap_baseline_m"),
        "baseline_class": "nondegenerate_pairs_only; baseline<=0.06m excluded",
        "reciprocal_match_count": median(nondeg, "reciprocal_match_count"),
        "border_match_count": median(nondeg, "border_match_count"), "dlt_finite_count": median(nondeg, "dlt_finite_count"),
        "cheirality_pass_count": median(nondeg, "cheirality_pass_count"),
        "reprojection_pass_count": median(nondeg, "reprojection_pass_count"),
        "reprojection_pass_rate": median(nondeg, "reprojection_pass_rate"),
        "reprojection_error_median_px": median(nondeg, "reprojection_error_median_px"),
        "reconstructed_candidate_count": median(nondeg, "reconstructed_candidate_count"),
        "footprint_inside_count": median(nondeg, "footprint_inside_count"), "roof_candidate_count": roof_median,
        "abs_delta_z_median_m": error_median, "abs_delta_z_within_pair_mad_m": median(nondeg, "abs_delta_z_within_pair_mad_m"),
        "abs_delta_z_within_pair_std_m": median(nondeg, "abs_delta_z_within_pair_std_m"),
        "abs_delta_z_across_pair_mad_m": across_mad, "footprint_outside_count": median(nondeg, "footprint_outside_count"),
        "footprint_outside_rate": median(nondeg, "footprint_outside_rate"),
        "old_footprint_inside_count": old_summary.get("footprint_inside_count", ""),
        "old_roof_candidate_count": old_summary.get("roof_candidate_count", ""),
        "old_abs_delta_z_median_m": old_summary.get("abs_delta_z_median_m", ""),
        "old_footprint_outside_rate": old_summary.get("footprint_outside_rate", ""),
        "old_status": old_summary.get("status", ""), "origin_separation_class": classification,
        "selected_pair_count": len(rows), "completed_pair_count": len(completed),
        "nondegenerate_completed_pair_count": len(nondeg), "status": "summary",
        "failure_reason": ";".join(f"rank{r['pair_rank']}:{r['failure_reason']}" for r in rows if not str(r["status"]).startswith("pass")),
        "building_elapsed_s": building_elapsed,
    })
    return row


def save_pair_detail(detail: dict[str, Any]) -> Path:
    path = PAIR_DIR / f"{detail['short']}_rank{int(detail['rank']):02d}.npz"
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp.npz")
    np.savez_compressed(
        tmp,
        pixels_a=detail["pixels_a"], pixels_b=detail["pixels_b"], world_local_xyz=detail["world"],
        inside_footprint_score_mask=detail["inside"], roof_candidate_score_mask=detail["roof"],
        max_reprojection_error_px=detail["max_error"], metadata_json=json.dumps({
            "short": detail["short"], "rank": detail["rank"], "view_a": detail["view_a"],
            "view_b": detail["view_b"], "row": {key: base.json_number(value) for key, value in detail["row"].items()},
        }, ensure_ascii=False),
    )
    os.replace(tmp, path)
    return path


def load_pair_detail(path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    archive = np.load(path, allow_pickle=False)
    metadata = json.loads(str(archive["metadata_json"]))
    row = metadata["row"]
    detail = {
        "short": metadata["short"], "rank": int(metadata["rank"]),
        "view_a": metadata["view_a"], "view_b": metadata["view_b"],
        "pixels_a": np.asarray(archive["pixels_a"], dtype=np.float64),
        "pixels_b": np.asarray(archive["pixels_b"], dtype=np.float64),
        "world": np.asarray(archive["world_local_xyz"], dtype=np.float64),
        "inside": np.asarray(archive["inside_footprint_score_mask"], dtype=bool),
        "roof": np.asarray(archive["roof_candidate_score_mask"], dtype=bool),
        "max_error": np.asarray(archive["max_reprojection_error_px"], dtype=np.float64), "row": row,
    }
    return row, detail


def update_progress(
    pair_rows: Sequence[dict[str, Any]], completed_buildings: Sequence[str], active: dict[str, Any] | None
) -> None:
    payload = {
        "schema": "jointbuildgs.s3ap.fm_retriangulation.progress.v1", "updated_utc": now(),
        "total_pair_count": 16, "recorded_pair_count": len(pair_rows),
        "pass_pair_count": sum(str(row.get("status", "")).startswith("pass") for row in pair_rows),
        "failed_pair_count": sum(row.get("status") == "failed_pair" for row in pair_rows),
        "completed_buildings": list(completed_buildings), "active": active, "learning_runs_started": 0,
    }
    atomic_text(PROGRESS, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


def footprint_lines(footprint: Any, offset: np.ndarray, z: float, frame: dict[str, Any]) -> list[np.ndarray]:
    lines: list[np.ndarray] = []
    for polygon in base.iter_polygons(footprint):
        rings = [polygon.exterior, *polygon.interiors]
        for ring in rings:
            xy = np.asarray(ring.coords, dtype=np.float64)
            local = np.column_stack([xy[:, 0] - offset[0], xy[:, 1] - offset[1], np.full(len(xy), z)])
            pixels, depths = project(local, frame)
            if np.all(depths > 0) and np.isfinite(pixels).all():
                lines.append(pixels)
    return lines


def choose_overlay_views(views: Sequence[dict[str, Any]], frames: dict[str, dict[str, Any]]) -> list[tuple[str, str]]:
    scored = []
    for view in views:
        direction = frames[view["stem"]]["R"].T @ np.asarray([0.0, 0.0, 1.0])
        nadir_score = float(abs(direction[2]) / max(np.linalg.norm(direction), 1e-12))
        scored.append((nadir_score, view["stem"]))
    scored.sort()
    if len(scored) == 1:
        return [(scored[0][1], "single")]
    return [(scored[-1][1], "nadir_like"), (scored[0][1], "oblique_like")]


def make_overlays(
    short: str,
    views: Sequence[dict[str, Any]],
    frames: dict[str, dict[str, Any]],
    footprint: Any,
    offset: np.ndarray,
    reference_z: float,
    details: Sequence[dict[str, Any]],
) -> list[Path]:
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    for stem, role in choose_overlay_views(views, frames):
        frame = frames[stem]
        with PILImage.open(frame["path"]) as source:
            rgb = np.asarray(source.convert("RGB"))
        pixels: list[np.ndarray] = []
        inside_values: list[np.ndarray] = []
        for detail in details:
            if detail["view_a"] == stem:
                pixels.append(detail["pixels_a"]); inside_values.append(detail["inside"])
            elif detail["view_b"] == stem:
                pixels.append(detail["pixels_b"]); inside_values.append(detail["inside"])
        points = np.concatenate(pixels) if pixels else np.zeros((0, 2))
        inside = np.concatenate(inside_values) if inside_values else np.zeros(0, dtype=bool)
        fig, ax = plt.subplots(figsize=(12, 8), dpi=180)
        ax.imshow(rgb)
        for line in footprint_lines(footprint, offset, reference_z, frame):
            ax.plot(line[:, 0], line[:, 1], color="#00ffff", linewidth=2.0, label="footprint @ LoD2 z (score overlay)")
        if len(points):
            ax.scatter(points[~inside, 0], points[~inside, 1], s=13, c="#ff7f0e", alpha=0.65, label="DLT survivor outside")
            ax.scatter(points[inside, 0], points[inside, 1], s=17, c="#00ff66", alpha=0.85, label="DLT survivor inside")
        ax.set_xlim(0, frame["width"]); ax.set_ylim(frame["height"], 0)
        ax.set_title(f"{base.full_id(short)} | {role} | {stem} | survivors={len(points)}")
        ax.set_xlabel("source image x [px]"); ax.set_ylabel("source image y [px]")
        handles, labels = ax.get_legend_handles_labels()
        unique = dict(zip(labels, handles))
        if unique:
            ax.legend(unique.values(), unique.keys(), loc="best", fontsize=8)
        fig.tight_layout()
        path = FIG_DIR / f"fm_retri_{short}_{role}.png"
        fig.savefig(path); plt.close(fig); paths.append(path)
    return paths


def report_text(summaries: Sequence[dict[str, Any]], figures: Sequence[Path]) -> str:
    recovered = sum(row["origin_separation_class"] == "recovered_by_fixed_pose_retriangulation" for row in summaries)
    still = sum(row["origin_separation_class"] == "still_bad_after_fixed_pose_retriangulation" for row in summaries)
    lines = [
        "# W — E5 C001 S3-A′ FM 고정 포즈 재삼각측량 (2026-07-14)", "",
        "> 학습 0회. MASt3R 2D reciprocal 대응점만 사용. MASt3R 3D·crop gauge·유사변환 미사용.",
        "> 발자국과 LoD2 지붕 z는 고정 COLMAP DLT가 끝난 뒤 채점·오버레이에만 사용.", "",
        "## 잠금 규칙", "",
        f"- DLT: 원본 픽셀 + 고정 COLMAP `K[R|t]`, float64 선형 SVD.",
        f"- 필터: 양 카메라 cheirality + 각 뷰 재투영 오차 최대 `{REPROJECTION_THRESHOLD_PX:.1f}px`.",
        f"- 기선 축퇴 사전 라벨: 카메라 중심 거리 `<= {DEGENERATE_BASELINE_MAX_M:.2f}m`; 건물 요약에서 제외.",
        "- 원인 분류: 비축퇴 요약에서 신법 지붕 후보 >=1, 신·구 |Δz| 유한, 신법 |Δz|가 구법보다 작으면 `recovered`; 그 외 `still_bad`.", "",
        "## 구법–신법 건물 요약", "",
        "| 건물 | 쌍 선택/완료/비축퇴 | 구법 안/지붕/|Δz|/유출 | 신법 안/지붕/|Δz|/쌍간 MAD/유출 | 분류 |",
        "|---|---:|---|---|---|",
    ]
    for row in summaries:
        def show(key: str) -> str:
            value = row.get(key)
            return "—" if value in (None, "") else fmt(value)
        lines.append(
            f"| {row['building_id']} | {row['selected_pair_count']}/{row['completed_pair_count']}/{row['nondegenerate_completed_pair_count']} "
            f"| {show('old_footprint_inside_count')}/{show('old_roof_candidate_count')}/{show('old_abs_delta_z_median_m')}/{show('old_footprint_outside_rate')} "
            f"| {show('footprint_inside_count')}/{show('roof_candidate_count')}/{show('abs_delta_z_median_m')}/{show('abs_delta_z_across_pair_mad_m')}/{show('footprint_outside_rate')} "
            f"| `{row['origin_separation_class']}` |"
        )
    lines.extend(["", "## 발자국 투영·생존 대응점", ""])
    for path in figures:
        lines.append(f"![{path.stem}](figs/e5_c001_s3ap_fm_retri/{path.name})")
    lines.extend(["", "## 한 줄 관찰", "", f"{recovered}/3 회복·{still}/3 여전 실패·축퇴 쌍 제외", ""])
    return "\n".join(lines)


def write_versions(args: argparse.Namespace) -> None:
    env = json.loads(base.ENV_MANIFEST.read_text(encoding="utf-8"))
    text = "\n".join([
        f"created_utc={now()}", f"git_head={base.git_value('rev-parse', 'HEAD')}",
        f"branch={base.git_value('branch', '--show-current')}",
        f"docker_tag={env['runtime_lock']['docker_image_tag']}",
        f"docker_image_id={env['runtime_lock']['docker_image_id']}",
        f"mast3r_code_commit={env['code']['mast3r_commit']}",
        f"dust3r_code_commit={env['code']['dust3r_commit']}",
        f"croco_code_commit={env['code']['croco_commit']}", f"model_revision={base.MODEL_REVISION}",
        f"weights_sha256={base.MODEL_SHA256}", f"torch={torch.__version__}",
        f"numpy={np.__version__}", f"device={args.device}",
    ]) + "\n"
    atomic_text(VERSIONS, text)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-dir", type=Path, required=True)
    parser.add_argument("--device", default="cuda:0")
    args = parser.parse_args()
    weights = args.model_dir / "model.safetensors"
    if args.model_dir.name != base.MODEL_REVISION or base.sha256_file(weights) != base.MODEL_SHA256 or weights.stat().st_size != base.MODEL_BYTES:
        raise RuntimeError("MASt3R model lock mismatch")
    env = json.loads(base.ENV_MANIFEST.read_text(encoding="utf-8"))
    if env["status"] != "environment_locked_smoke_pass":
        raise RuntimeError("MASt3R environment lock is not passing")
    if args.device.startswith("cuda") and not torch.cuda.is_available():
        raise RuntimeError("CUDA requested but unavailable")

    RUN_DIR.mkdir(parents=True, exist_ok=True); PAIR_DIR.mkdir(parents=True, exist_ok=True)
    write_versions(args)
    log("START learning_runs_started=0 raw_reciprocal_2d_only=true")
    offset = base.load_offset(); footprints = base.load_footprints(); ground, reference = base.load_anchor_scores()
    frames = base.load_frames(); views = base.load_view_rows(); old_pairs, old_summaries = old_rows()
    model = base.AsymmetricMASt3R.from_pretrained(str(args.model_dir)).to(args.device).eval()

    pair_rows: list[dict[str, Any]] = []
    all_details: dict[str, list[dict[str, Any]]] = defaultdict(list)
    summaries: list[dict[str, Any]] = []
    completed_buildings: list[str] = []
    for short in base.TARGETS:
        building_started = time.monotonic()
        selected = base.select_pairs(views[short])
        local_rows: list[dict[str, Any]] = []
        for rank, pair in enumerate(selected, start=1):
            update_progress(pair_rows, completed_buildings, {"building": short, "pair_rank": rank, "started_utc": now()})
            pair_started = time.monotonic()
            try:
                path = PAIR_DIR / f"{short}_rank{rank:02d}.npz"
                if path.exists():
                    row, detail = load_pair_detail(path)
                    log(f"PAIR_CACHE_REUSED building={short} rank={rank} cache={base.rel(path)}")
                else:
                    row, detail = measure_pair(
                        model, short, rank, pair, frames, footprints[base.full_id(short)], offset,
                        ground[short], reference[short], old_pairs[(short, rank)], args.device,
                    )
                    path = save_pair_detail(detail)
                all_details[short].append(detail)
                log(
                    f"PAIR_DONE building={short} rank={rank} status={row['status']} baseline={row['known_colmap_baseline_m']:.6f} "
                    f"matches={row['reciprocal_match_count']} reproj_pass={row['reprojection_pass_count']} "
                    f"inside={row['footprint_inside_count']} cache={base.rel(path)}"
                )
            except Exception as exc:  # continue-on-pair-failure is a locked unattended rule
                row = failed_pair(short, rank, pair, ground[short], reference[short], exc, time.monotonic() - pair_started)
                log(f"PAIR_FAILED building={short} rank={rank} reason={row['failure_reason']}")
            local_rows.append(row); pair_rows.append(row)
            atomic_csv(pair_rows)
            update_progress(pair_rows, completed_buildings, None)
        building_elapsed = time.monotonic() - building_started
        summary = summary_row(short, local_rows, ground[short], reference[short], old_summaries[short], building_elapsed)
        summaries.append(summary); completed_buildings.append(short)
        atomic_csv([*pair_rows, *summaries])
        update_progress(pair_rows, completed_buildings, None)
        log(f"BUILDING_DONE building={short} elapsed_s={building_elapsed:.3f} class={summary['origin_separation_class']}")

    figures: list[Path] = []
    for short in base.TARGETS:
        figures.extend(make_overlays(
            short, views[short], frames, footprints[base.full_id(short)], offset, reference[short], all_details[short]
        ))
    atomic_text(REPORT, report_text(summaries, figures))
    final_rows = [*pair_rows, *summaries]
    atomic_csv(final_rows)
    log(f"FINALIZING rows={len(final_rows)} figures={len(figures)}")
    output_paths = [OUT_CSV, REPORT, PROGRESS, RUN_LOG, VERSIONS, *figures, *sorted(PAIR_DIR.glob("*.npz"))]
    source_paths = [
        BASE_PATH, OLD_CSV, base.PJPL, base.FOOTPRINTS, base.TRAIN_MANIFEST, base.ANCHOR_CSV,
        base.ENV_MANIFEST, base.SPARSE_DIR / "cameras.bin", base.SPARSE_DIR / "images.bin",
        *[frames[item["stem"]]["path"] for items in views.values() for item in items],
        *[base.REGION_DIR / f"{item['stem']}.npz" for items in views.values() for item in items],
    ]
    manifest = {
        "schema": "jointbuildgs.s3ap.fm_retriangulation.v1", "created_utc": now(),
        "git_head_at_measurement": base.git_value("rev-parse", "HEAD"),
        "branch": base.git_value("branch", "--show-current"), "learning_runs_started": 0,
        "time_limits_s": {"pair": PAIR_TIME_LIMIT_S, "building": BUILDING_TIME_LIMIT_S},
        "model": {"revision": base.MODEL_REVISION, "weights_sha256": base.MODEL_SHA256, "weights_bytes": base.MODEL_BYTES},
        "docker": {
            "tag": env["runtime_lock"]["docker_image_tag"],
            "image_id": env["runtime_lock"]["docker_image_id"],
        }, "locked_visible_views": views,
        "pair_selection_rule": final_rows[0]["view_pair_selection_rule"],
        "match_rule": final_rows[0]["match_rule"], "triangulation_rule": final_rows[0]["triangulation_rule"],
        "baseline_class_rule": f"camera-centre baseline <= {DEGENERATE_BASELINE_MAX_M:.2f}m is prelabelled degenerate and excluded from building summary",
        "classification_rule": (
            "nondegenerate summary is recovered iff new roof candidates>=1, old/new abs-dz are finite, "
            "and new abs-dz median < old; otherwise still_bad; no extra threshold"
        ),
        "gt_separation": "footprint and LoD2 roof z are first applied after fixed-pose DLT, for score/overlay only",
        "forbidden_inputs_used": {"mast3r_3d": False, "crop_gauge": False, "similarity": False, "old_pair_details_matches": False},
        "source_sha256": {base.rel(path): base.sha256_file(path) for path in sorted(set(source_paths))},
        "script_sha256": base.sha256_file(Path(__file__).resolve()),
        "output_sha256": {base.rel(path): base.sha256_file(path) for path in output_paths},
        "row_count": len(final_rows), "pair_row_count": len(pair_rows), "summary_row_count": len(summaries),
        "pass_pair_count": sum(str(row["status"]).startswith("pass") for row in pair_rows),
        "failed_pair_count": sum(row["status"] == "failed_pair" for row in pair_rows),
        "figures": [base.rel(path) for path in figures], "interpretation_or_verdict": None,
        "no_seed_or_training_use": True,
    }
    atomic_text(MANIFEST, json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")


if __name__ == "__main__":
    main()
