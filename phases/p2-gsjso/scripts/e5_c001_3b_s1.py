#!/usr/bin/env python3
"""E5 C001 ③b-S1 surface-restoration retrain material.

This is an experiment-line orchestrator. It reuses the existing C001 readout,
Roofer, val3dity, and 8-way code, but redirects every output to S1-only paths.
The canonical S0 checkpoint/readout products are read-only comparison inputs.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d.art3d import Poly3DCollection

import e5_c001_readout_ablation as ab
from e5_pilot_gate_tools import C001_IDS, DEV_IMAGE, P0_RUNS, sha256_file


REPO = Path(__file__).resolve().parents[3]
RUN_ID = "20260708_e5_c001_3b_s1"
P2_RUN_DIR = REPO / "phases/p2-gsjso/runs" / RUN_ID
P0_RUN_ID = "e5p_3b_s1_20260708_C001"
P0_RUN_DIR = P0_RUNS / P0_RUN_ID
RESULTS_ROOT = REPO / "results/tum_transfer/e5_3b_s1/C001/readout_ablation"
CKPT_ROOT = REPO / "results/tum_transfer/e5_3b_s1/C001/runs"
TRAIN_RUN_DIR = P2_RUN_DIR
DATA_ROOT = "results/tum_transfer/e5_pilot/C001/data_geoidfix_C001_buf20"
TORCH_EXTENSIONS = "results/tum_transfer/e5_3b_s1/C001/torch_extensions_eval"
FIG_DIR = REPO / "docs/figs/e5_c001_3b_s1"
READOUT_FIG_DIR = FIG_DIR / "readout"
REPORT_PATH = REPO / "docs/experiments/e5_c001_3b_s1/reports/W_E5_C001_③b_S1_표면복원.md"
TEMP_READOUT_REPORT = REPO / "docs/archive/e5_c001_3b_s1/temporary/reports/W_E5_C001_3b_S1_readout_tmp.md"

S1_RUN_NAMES = [
    "gs_e5_C001_s1_sparse_r1",
    "gs_e5_C001_s1_dense_r1",
    "gs_e5_C001_s1_acmp_r1",
]
S0_RUN_BY_ARM = {
    "sparse": "gs_e5_C001_sparse_r1",
    "dense": "gs_e5_C001_dense_r1",
    "acmp": "gs_e5_C001_acmp_r1",
}
S0_SOURCE_BY_ARM = {"sparse": "gs_sparse_r1", "dense": "gs_dense_r1", "acmp": "gs_acmp_r1"}
TEXTURE_CASES = ["DEBY_LOD2_4907184", "DEBY_LOD2_60098", "DEBY_LOD2_8568391"]
TEXTURE_LABEL = {
    "DEBY_LOD2_4907184": "textured",
    "DEBY_LOD2_60098": "textureless",
    "DEBY_LOD2_8568391": "textureless",
}
CITYGSV2_SOURCE = {
    "repo": "https://github.com/DekuLiuTesla/CityGaussian",
    "commit": "1c0759eece7f428caa65a86f4ca8dd76749bce87",
    "tag": "CityGaussian_V2.0",
    "depth_scheduler_default": "init=1.0, final_factor=0.01, max_steps=30000",
    "citygsv2_trim_depth": "init=0.5, final_factor=0.05, max_steps=60000(MatrixCity aerial trim)",
    "citygsv2_trim_depth_loss": "l1+ssim, depth_loss_ssim_weight=1.0",
    "elongation_axis_ratio_threshold": "scale_min/scale_max > 0.01",
    "prune_opacity_threshold": "cull_opacity_threshold=0.05 in vanilla_2dgs/appearance 2DGS configs",
}
DESIGN_MEMO_PATH = REPO / "docs/experiments/e5_c001_3b_s1/reports/W_③b_레시피설계_레퍼런스기반_20260707.md"


def configure_ablation_module() -> None:
    ab.RUN_ID = RUN_ID
    ab.P2_RUN_DIR = P2_RUN_DIR
    ab.P0_RUN_ID = P0_RUN_ID
    ab.P0_RUN_DIR = P0_RUN_DIR
    ab.RESULTS_ROOT = RESULTS_ROOT
    ab.CKPT_ROOT = CKPT_ROOT
    ab.TRAIN_RUN_DIR = TRAIN_RUN_DIR
    ab.CANON_GATE_DIR = REPO / "phases/p0-audit/runs/e5p_gate_20260707_C001"
    ab.DATA_ROOT = DATA_ROOT
    ab.TORCH_EXTENSIONS = TORCH_EXTENSIONS
    ab.FIG_DIR = READOUT_FIG_DIR
    ab.REPORT_PATH = TEMP_READOUT_REPORT
    ab.COVERAGE_CSV = REPO / "docs/experiments/e5_c001_3b_s1/tables/e5_c001_3b_s1_coverage.csv"
    ab.FILTER_CSV = REPO / "docs/experiments/e5_c001_3b_s1/tables/e5_c001_3b_s1_filter_contrib.csv"
    ab.METRICS_CSV = REPO / "docs/experiments/e5_c001_3b_s1/tables/e5_c001_3b_s1_metrics.csv"
    ab.SUMMARY_CSV = REPO / "docs/experiments/e5_c001_3b_s1/tables/e5_c001_3b_s1_summary.csv"
    ab.TRADEOFF_CSV = REPO / "docs/experiments/e5_c001_3b_s1/tables/e5_c001_3b_s1_tradeoff.csv"
    ab.CASE_CSV = REPO / "docs/experiments/e5_c001_3b_s1/tables/e5_c001_3b_s1_representative_buildings.csv"
    ab.INVENTORY_CSV = REPO / "docs/experiments/e5_c001_3b_s1/tables/e5_c001_3b_s1_inventory.csv"
    ab.ISSUES_CSV = REPO / "docs/experiments/e5_c001_3b_s1/tables/e5_c001_3b_s1_issues.csv"
    ab.RENDER_COVERAGE = REPO / "docs/experiments/e5_c001_3b_s1/tables/e5_c001_3b_s1_render_readout_coverage.csv"
    ab.SETTINGS = [
        ab.Setting("base", "S1 정본 readout 재현", min_obs=3, voxel=0.05, sor="on", sor_std=2.0),
        ab.Setting("voxel02", "S1 voxel0.02 천장 시험", min_obs=3, voxel=0.02, sor="on", sor_std=2.0),
    ]
    ab.selected_run_names = selected_run_names
    ab.write_report = write_readout_temp_report


def selected_run_names(args: argparse.Namespace) -> list[str]:
    selected = getattr(args, "runs", None)
    if not selected:
        return S1_RUN_NAMES
    missing = sorted(set(selected) - set(S1_RUN_NAMES))
    if missing:
        raise RuntimeError(f"unknown S1 run names: {missing}")
    selected_set = set(selected)
    return [name for name in S1_RUN_NAMES if name in selected_set]


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


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


def rel(path: Path | str) -> str:
    p = Path(path)
    try:
        return str(p.relative_to(REPO))
    except ValueError:
        return str(p)


def num(value: Any) -> float | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() in {"nan", "none", "na"}:
        return None
    try:
        out = float(text)
    except ValueError:
        return None
    return out if math.isfinite(out) else None


def mean(values: list[float]) -> float | None:
    return float(np.mean(values)) if values else None


def median(values: list[float]) -> float | None:
    return float(np.median(values)) if values else None


def fmt(value: Any, digits: int = 4) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, (int, np.integer)):
        return str(int(value))
    if isinstance(value, (float, np.floating)):
        v = float(value)
        return f"{v:.{digits}f}" if math.isfinite(v) else ""
    return str(value)


def tf(value: Any) -> bool:
    return str(value).strip().lower() in {"true", "1", "yes", "y"}


def run_text(cmd: list[str]) -> str:
    try:
        proc = subprocess.run(cmd, cwd=REPO, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
        return (proc.stdout or "").strip()
    except FileNotFoundError as exc:
        return f"not_available:{exc.filename}"


def parse_train_log(path: Path) -> dict[str, str]:
    out = {"start_utc": "", "end_utc": "", "host_gpu": "", "return_code": ""}
    if not path.exists():
        return out
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.startswith("START_UTC="):
            out["start_utc"] = line.split("=", 1)[1].strip()
        elif line.startswith("END_UTC="):
            out["end_utc"] = line.split("=", 1)[1].strip()
        elif line.startswith("HOST_GPU="):
            out["host_gpu"] = line.split("=", 1)[1].strip()
        elif line.startswith("RETURN_CODE="):
            out["return_code"] = line.split("=", 1)[1].strip()
    return out


def elapsed_minutes(start: str, end: str) -> str:
    if not start or not end:
        return ""
    try:
        s = datetime.fromisoformat(start.replace("Z", "+00:00"))
        e = datetime.fromisoformat(end.replace("Z", "+00:00"))
    except ValueError:
        return ""
    return fmt((e - s).total_seconds() / 60.0, 1)


def first_success_log(run_name: str) -> tuple[Path, str]:
    root = REPO / "results/tum_transfer/e5_3b_s1/C001/train_logs"
    candidates = [
        root / f"{run_name}.log",
        root / f"{run_name}.retry1.log",
        root / f"{run_name}.retry2.log",
    ]
    failed = []
    for path in candidates:
        info = parse_train_log(path)
        if info.get("return_code") == "0":
            return path, ";".join(failed)
        if path.exists():
            failed.append(f"{rel(path)} return_code={info.get('return_code') or 'missing'}")
    existing = next((p for p in candidates if p.exists()), candidates[0])
    return existing, ";".join(failed)


def checkpoint_gaussian_count(path: Path) -> str:
    if not path.exists():
        return ""
    import torch

    ckpt = torch.load(path, map_location="cpu", weights_only=False)
    state = ckpt.get("state_dict", ckpt)
    for key in ["means", "means3D", "xyz"]:
        if key in state:
            return str(int(state[key].shape[0]))
    for value in state.values():
        if hasattr(value, "shape") and len(value.shape) >= 1:
            return str(int(value.shape[0]))
    return ""


def read_yaml(path: Path) -> dict[str, Any]:
    import yaml

    with path.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def write_train_fingerprints() -> None:
    rows: list[dict[str, Any]] = []
    for run_name in S1_RUN_NAMES:
        arm = arm_from_s1_run(run_name)
        cfg = REPO / "configs/tum_mob/e5_3b_s1" / f"{run_name}.yaml"
        cfg_data = read_yaml(cfg)
        ckpt = CKPT_ROOT / run_name / "ckpt/final.pt"
        eff = CKPT_ROOT / run_name / "effective_config.json"
        log, failed_note = first_success_log(run_name)
        info = parse_train_log(log)
        effective = json.loads(eff.read_text(encoding="utf-8")) if eff.exists() else {}
        rows.append(
            {
                "run_name": run_name,
                "arm": arm,
                "replicate": run_name.split("_")[-1],
                "seed": cfg_data.get("seed", ""),
                "config": rel(cfg),
                "config_sha256": sha256_file(cfg) if cfg.exists() else "missing",
                "effective_config": rel(eff),
                "effective_config_sha256": sha256_file(eff) if eff.exists() else "missing",
                "ckpt": rel(ckpt),
                "ckpt_sha256": sha256_file(ckpt) if ckpt.exists() else "missing",
                "log": rel(log),
                "host_gpu": info.get("host_gpu", ""),
                "start_utc": info.get("start_utc", ""),
                "end_utc": info.get("end_utc", ""),
                "elapsed_min": elapsed_minutes(info.get("start_utc", ""), info.get("end_utc", "")),
                "return_code": info.get("return_code", ""),
                "max_iter": cfg_data.get("max_iter", ""),
                "final_n_gaussians": checkpoint_gaussian_count(ckpt) if ckpt.exists() else "",
                "readout": "S1 base readout(gssem; semantic-TSDF[minobs3, voxel0.05]; Roofer eps0.3/minpts15/complexity0.888)",
                "z_datum_history": "E5 pilot GS: C001 cropped scene uses zeta -558.3 linked constants; output P_utm in EPSG:25832 ellipsoidal frame",
                "distortion_formula": effective.get("distort_formula", "loss_distort = mean(rend_dist) / scene_extent_bbox^2"),
                "distortion_denom": effective.get("distort_norm_denominator", ""),
                "scene_extent_bbox_m": effective.get("scene_extent_bbox_m", ""),
                "citygsv2_commit": CITYGSV2_SOURCE["commit"],
                "citygsv2_depth": CITYGSV2_SOURCE["citygsv2_trim_depth"],
                "citygsv2_elongation": CITYGSV2_SOURCE["elongation_axis_ratio_threshold"],
                "failed_attempts": failed_note,
            }
        )
    write_csv(P2_RUN_DIR / "train_fingerprints.csv", rows)
    print(json.dumps({"train_fingerprints": rel(P2_RUN_DIR / "train_fingerprints.csv"), "rows": len(rows)}, ensure_ascii=False))


def arm_from_s1_run(run_name: str) -> str:
    return run_name.split("_")[-2]


def summarize_metrics(rows: list[dict[str, str]], source_run: str) -> dict[str, Any]:
    group = [r for r in rows if r.get("source_run") == source_run]
    comp = [v for v in (num(r.get("completeness")) for r in group) if v is not None]
    corr = [v for v in (num(r.get("correctness")) for r in group) if v is not None]
    rms = [v for v in (num(r.get("ref_rms_m")) for r in group) if v is not None]
    return {
        "n_buildings": len(group),
        "has_lod22": sum(tf(r.get("has_lod22")) for r in group),
        "val3dity_valid": sum(tf(r.get("val3dity_valid")) for r in group),
        "mean_completeness": mean(comp),
        "mean_correctness": mean(corr),
        "median_ref_rms_m": median(rms),
        "mean_ref_rms_m": mean(rms),
    }


def coverage_mean(rows: list[dict[str, str]], *, run_name: str | None = None, source_run: str | None = None, stage: str, setting: str | None = None) -> float | None:
    vals = []
    for row in rows:
        if run_name is not None and row.get("run_name") != run_name:
            continue
        if source_run is not None and row.get("source_run") != source_run:
            continue
        if setting is not None and row.get("setting") != setting:
            continue
        if row.get("stage") != stage:
            continue
        v = num(row.get("coverage_frac"))
        if v is not None:
            vals.append(v)
    return mean(vals)


def build_delta_rows() -> list[dict[str, Any]]:
    s0_metrics = read_csv(REPO / "docs/experiments/e5_c001_8way/tables/e5_c001_8way_metrics.csv")
    s1_metrics = read_csv(ab.METRICS_CSV)
    s0_cov = read_csv(REPO / "docs/experiments/e5_c001_render/tables/e5_c001_render_readout_coverage.csv")
    s1_cov = read_csv(ab.COVERAGE_CSV)
    rows: list[dict[str, Any]] = []
    for arm, s1_run in [(arm_from_s1_run(r), r) for r in S1_RUN_NAMES]:
        s0_source = S0_SOURCE_BY_ARM[arm]
        s1_source = f"base__{s1_run}"
        s0 = summarize_metrics(s0_metrics, s0_source)
        s1 = summarize_metrics(s1_metrics, s1_source)
        s0_coverage = coverage_mean(s0_cov, source_run=S0_RUN_BY_ARM[arm], stage="tsdf_minobs_voxel_post_sor")
        s1_coverage = coverage_mean(s1_cov, run_name=s1_run, setting="base", stage="sor_post_clean")
        row = {
            "arm": arm,
            "s0_run": S0_RUN_BY_ARM[arm],
            "s1_run": s1_run,
            "s0_coverage": fmt(s0_coverage),
            "s1_coverage": fmt(s1_coverage),
            "delta_coverage": fmt((s1_coverage - s0_coverage) if s0_coverage is not None and s1_coverage is not None else None),
            "s0_completeness": fmt(s0["mean_completeness"]),
            "s1_completeness": fmt(s1["mean_completeness"]),
            "delta_completeness": fmt((s1["mean_completeness"] - s0["mean_completeness"]) if s0["mean_completeness"] is not None and s1["mean_completeness"] is not None else None),
            "s0_correctness": fmt(s0["mean_correctness"]),
            "s1_correctness": fmt(s1["mean_correctness"]),
            "delta_correctness": fmt((s1["mean_correctness"] - s0["mean_correctness"]) if s0["mean_correctness"] is not None and s1["mean_correctness"] is not None else None),
            "s0_median_ref_rms_m": fmt(s0["median_ref_rms_m"]),
            "s1_median_ref_rms_m": fmt(s1["median_ref_rms_m"]),
            "delta_median_ref_rms_m": fmt((s1["median_ref_rms_m"] - s0["median_ref_rms_m"]) if s0["median_ref_rms_m"] is not None and s1["median_ref_rms_m"] is not None else None),
            "s0_has_lod22": s0["has_lod22"],
            "s1_has_lod22": s1["has_lod22"],
            "s0_val3dity_valid": s0["val3dity_valid"],
            "s1_val3dity_valid": s1["val3dity_valid"],
        }
        rows.append(row)
    write_csv(REPO / "docs/experiments/e5_c001_3b_s1/tables/e5_c001_3b_s1_delta.csv", rows)
    return rows


def build_texture_rows() -> list[dict[str, Any]]:
    s0_metrics = read_csv(REPO / "docs/experiments/e5_c001_8way/tables/e5_c001_8way_metrics.csv")
    s1_metrics = read_csv(ab.METRICS_CSV)
    s1_cov = read_csv(ab.COVERAGE_CSV)
    rows: list[dict[str, Any]] = []
    s0_lookup = {(r["source_run"], r["building_id"]): r for r in s0_metrics}
    s1_lookup = {(r["source_run"], r["building_id"]): r for r in s1_metrics}
    cov_lookup = {
        (r["run_name"], r["building_id"], r["setting"], r["stage"]): r
        for r in s1_cov
    }
    for bid in TEXTURE_CASES:
        for arm, s1_run in [(arm_from_s1_run(r), r) for r in S1_RUN_NAMES]:
            s0 = s0_lookup.get((S0_SOURCE_BY_ARM[arm], bid), {})
            s1 = s1_lookup.get((f"base__{s1_run}", bid), {})
            cov = (cov_lookup.get((s1_run, bid, "base", "sor_post_clean")) or {}).get("coverage_frac", "")
            rows.append(
                {
                    "building_id": bid,
                    "texture_bucket": TEXTURE_LABEL[bid],
                    "arm": arm,
                    "s0_completeness": s0.get("completeness", ""),
                    "s1_completeness": s1.get("completeness", ""),
                    "s0_correctness": s0.get("correctness", ""),
                    "s1_correctness": s1.get("correctness", ""),
                    "s0_ref_rms_m": s0.get("ref_rms_m", ""),
                    "s1_ref_rms_m": s1.get("ref_rms_m", ""),
                    "s1_coverage": cov,
                    "s0_has_lod22": s0.get("has_lod22", ""),
                    "s1_has_lod22": s1.get("has_lod22", ""),
                    "s0_shell_bucket": s0.get("shell_bucket", ""),
                    "s1_shell_bucket": s1.get("shell_bucket", ""),
                }
            )
    write_csv(REPO / "docs/experiments/e5_c001_3b_s1/tables/e5_c001_3b_s1_texture_strata.csv", rows)
    return rows


def build_voxel_rows() -> list[dict[str, Any]]:
    metrics = read_csv(ab.METRICS_CSV)
    lookup = {(r["source_run"], r["building_id"]): r for r in metrics}
    rows: list[dict[str, Any]] = []
    for run_name in S1_RUN_NAMES:
        arm = arm_from_s1_run(run_name)
        for bid in C001_IDS:
            base = lookup.get((f"base__{run_name}", bid), {})
            vox = lookup.get((f"voxel02__{run_name}", bid), {})
            rows.append(
                {
                    "building_id": bid,
                    "arm": arm,
                    "base_correctness": base.get("correctness", ""),
                    "voxel02_correctness": vox.get("correctness", ""),
                    "delta_correctness": fmt((num(vox.get("correctness")) or 0) - (num(base.get("correctness")) or 0)) if num(vox.get("correctness")) is not None and num(base.get("correctness")) is not None else "",
                    "base_ref_rms_m": base.get("ref_rms_m", ""),
                    "voxel02_ref_rms_m": vox.get("ref_rms_m", ""),
                    "delta_ref_rms_m": fmt((num(vox.get("ref_rms_m")) or 0) - (num(base.get("ref_rms_m")) or 0)) if num(vox.get("ref_rms_m")) is not None and num(base.get("ref_rms_m")) is not None else "",
                    "base_has_lod22": base.get("has_lod22", ""),
                    "voxel02_has_lod22": vox.get("has_lod22", ""),
                }
            )
    write_csv(REPO / "docs/experiments/e5_c001_3b_s1/tables/e5_c001_3b_s1_voxel02.csv", rows)
    return rows


def plot_delta(rows: list[dict[str, Any]]) -> Path:
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    labels = [r["arm"] for r in rows]
    x = np.arange(len(labels))
    fig, axes = plt.subplots(2, 2, figsize=(10.5, 7.0))
    specs = [
        ("coverage", "s0_coverage", "s1_coverage"),
        ("completeness", "s0_completeness", "s1_completeness"),
        ("correctness", "s0_correctness", "s1_correctness"),
        ("median ref RMS (m)", "s0_median_ref_rms_m", "s1_median_ref_rms_m"),
    ]
    for ax, (title, s0_key, s1_key) in zip(axes.flat, specs):
        s0 = [num(r[s0_key]) or 0 for r in rows]
        s1 = [num(r[s1_key]) or 0 for r in rows]
        ax.bar(x - 0.18, s0, width=0.36, label="S0")
        ax.bar(x + 0.18, s1, width=0.36, label="S1")
        ax.set_xticks(x)
        ax.set_xticklabels(labels)
        ax.set_title(title)
        ax.grid(axis="y", alpha=0.25)
    axes.flat[0].legend()
    fig.tight_layout()
    out = FIG_DIR / "s0_s1_delta_summary.png"
    fig.savefig(out, dpi=170)
    plt.close(fig)
    return out


def plot_texture(rows: list[dict[str, Any]]) -> Path:
    bids = TEXTURE_CASES
    fig, axes = plt.subplots(1, len(bids), figsize=(12.2, 3.8), sharey=True)
    for ax, bid in zip(axes, bids):
        group = [r for r in rows if r["building_id"] == bid]
        labels = [r["arm"] for r in group]
        x = np.arange(len(labels))
        s0 = [num(r["s0_ref_rms_m"]) or np.nan for r in group]
        s1 = [num(r["s1_ref_rms_m"]) or np.nan for r in group]
        ax.bar(x - 0.18, s0, width=0.36, label="S0")
        ax.bar(x + 0.18, s1, width=0.36, label="S1")
        ax.set_xticks(x)
        ax.set_xticklabels(labels, rotation=25, ha="right")
        ax.set_title(f"{bid.replace('DEBY_LOD2_', '')}\n{TEXTURE_LABEL[bid]}", fontsize=9)
        ax.grid(axis="y", alpha=0.25)
    axes[0].set_ylabel("ref RMS (m)")
    axes[0].legend()
    fig.tight_layout()
    out = FIG_DIR / "texture_strata_ref_rms.png"
    fig.savefig(out, dpi=170)
    plt.close(fig)
    return out


def plot_floater() -> Path | None:
    s0_path = REPO / "docs/experiments/e5_c001_render/tables/e5_c001_render_floater_metrics.csv"
    s1_path = REPO / "docs/experiments/e5_c001_3b_s1/tables/e5_c001_3b_s1_render_floater_metrics.csv"
    s1_render_path = REPO / "docs/experiments/e5_c001_3b_s1/tables/e5_c001_3b_s1_render_eval_metrics.csv"
    if not (s0_path.exists() and s1_path.exists() and s1_render_path.exists()):
        return None
    s0 = [r for r in read_csv(s0_path) if r.get("replicate") == "r1"]
    s1 = read_csv(s1_path)
    labels = ["sparse", "dense", "acmp"]
    x = np.arange(len(labels))
    fig, axes = plt.subplots(1, 3, figsize=(12.5, 3.8))
    for ax, col, title in [
        (axes[0], "opacity_below_prune005_frac", "opacity < 0.005"),
        (axes[1], "elongated_ratio_gt10_frac", "in-plane ratio > 10"),
        (axes[2], "off_seed_gt1m_proxy_frac", "off-seed > 1m proxy"),
    ]:
        vals0 = [mean([v for v in (num(r.get(col)) for r in s0 if r.get("arm") == a) if v is not None]) or 0.0 for a in labels]
        vals1 = [mean([v for v in (num(r.get(col)) for r in s1 if r.get("arm") == a) if v is not None]) or 0.0 for a in labels]
        ax.bar(x - 0.18, vals0, width=0.36, label="S0")
        ax.bar(x + 0.18, vals1, width=0.36, label="S1")
        ax.set_xticks(x)
        ax.set_xticklabels(labels)
        ax.set_title(title)
        ax.grid(axis="y", alpha=0.25)
    axes[0].legend()
    fig.tight_layout()
    out = FIG_DIR / "floater_s0_s1_metrics.png"
    fig.savefig(out, dpi=170)
    plt.close(fig)
    return out


def plot_voxel(rows: list[dict[str, Any]]) -> Path:
    fig, ax = plt.subplots(figsize=(5.8, 5.2))
    colors = {"sparse": "tab:blue", "dense": "tab:green", "acmp": "tab:red"}
    for arm in ["sparse", "dense", "acmp"]:
        group = [r for r in rows if r["arm"] == arm]
        x = [num(r["base_ref_rms_m"]) for r in group]
        y = [num(r["voxel02_ref_rms_m"]) for r in group]
        pts = [(a, b) for a, b in zip(x, y) if a is not None and b is not None]
        if pts:
            ax.scatter([p[0] for p in pts], [p[1] for p in pts], s=28, label=arm, alpha=0.75, c=colors[arm])
    ax.axhline(2.5, color="k", linestyle="--", linewidth=1, label="③a voxel02 2.5m note")
    ax.axline((0, 0), slope=1, color="0.5", linewidth=1, linestyle=":")
    ax.set_xlabel("S1 base ref RMS (m)")
    ax.set_ylabel("S1 voxel02 ref RMS (m)")
    ax.set_title("S1 base vs voxel02 ceiling probe")
    ax.grid(alpha=0.25)
    ax.legend(fontsize=8)
    fig.tight_layout()
    out = FIG_DIR / "voxel02_ref_rms_scatter.png"
    fig.savefig(out, dpi=170)
    plt.close(fig)
    return out


def plot_render_tsdf() -> Path | None:
    s0_path = REPO / "docs/experiments/e5_c001_render/tables/e5_c001_render_readout_coverage.csv"
    s1_path = REPO / "docs/experiments/e5_c001_3b_s1/tables/e5_c001_3b_s1_render_readout_coverage.csv"
    if not (s0_path.exists() and s1_path.exists()):
        return None
    s0 = read_csv(s0_path)
    s1 = read_csv(s1_path)
    stage_order = ["render_depth_backproj_sample_pre_readout", "tsdf_minobs_voxel_pre_sor", "tsdf_minobs_voxel_post_sor"]
    fig, axes = plt.subplots(1, 3, figsize=(12.6, 3.8), sharey=True)
    for ax, arm in zip(axes, ["sparse", "dense", "acmp"]):
        x = np.arange(len(stage_order))
        vals0 = [
            mean([v for v in (num(r.get("coverage_frac")) for r in s0 if r.get("source_run") == S0_RUN_BY_ARM[arm] and r.get("stage") == stage) if v is not None]) or 0.0
            for stage in stage_order
        ]
        s1_run = next(r for r in S1_RUN_NAMES if arm_from_s1_run(r) == arm)
        vals1 = [
            mean([v for v in (num(r.get("coverage_frac")) for r in s1 if r.get("source_run") == s1_run and r.get("stage") == stage) if v is not None]) or 0.0
            for stage in stage_order
        ]
        ax.bar(x - 0.18, vals0, width=0.36, label="S0")
        ax.bar(x + 0.18, vals1, width=0.36, label="S1")
        ax.set_xticks(x)
        ax.set_xticklabels(["render", "TSDF preSOR", "TSDF postSOR"], rotation=25, ha="right")
        ax.set_title(arm)
        ax.grid(axis="y", alpha=0.25)
    axes[0].set_ylabel("coverage")
    axes[0].legend()
    fig.tight_layout()
    out = FIG_DIR / "render_vs_tsdf_coverage.png"
    fig.savefig(out, dpi=170)
    plt.close(fig)
    return out


def median_surface_distance(pred: Any, refs: list[Any]) -> float | None:
    e = load_eight_module()
    pts = e.sample_polygon_points(pred.polygon, e.SAMPLE_SPACING_M, limit=600)
    if len(pts) == 0:
        return None
    pred_z = pred.z_at(pts[:, 0], pts[:, 1])
    nearest = []
    for x, y, z in zip(pts[:, 0], pts[:, 1], pred_z):
        candidates = [ref for ref in refs if any(poly.covers(e.shape_point(x, y)) for poly in e.flatten_polygons(ref.polygon))]
        if not candidates:
            candidates = sorted(refs, key=lambda r: min(poly.distance(e.shape_point(x, y)) for poly in e.flatten_polygons(r.polygon)))[:1]
        if candidates:
            ref_z = np.asarray([ref.z_at(np.asarray([x]), np.asarray([y]))[0] for ref in candidates], dtype=float)
            nearest.append(float(z - ref_z[int(np.argmin(np.abs(z - ref_z)))]))
    return float(np.median(np.abs(nearest))) if nearest else None


def draw_distance_model(ax: Any, surfaces: list[Any], refs: list[Any], footprint: Any, title: str, note: str = "") -> None:
    e = load_eight_module()
    ax.set_title(title, fontsize=7)
    polys = e.surface_polys_3d(surfaces)
    if not polys:
        ax.text2D(0.5, 0.5, "no model", ha="center", va="center", transform=ax.transAxes, fontsize=7)
        ax.set_axis_off()
        return
    dists = [median_surface_distance(s, refs) for s in surfaces]
    vals = np.asarray([0.0 if d is None else min(d, 8.0) for d in dists], dtype=float)
    poly_colors = []
    for surface_idx, surface in enumerate(surfaces):
        n_polys = len(e.surface_polys_3d([surface]))
        for _ in range(n_polys):
            poly_colors.append(plt.cm.viridis(vals[surface_idx] / 8.0))
    allpts = np.vstack(polys)
    zmin = float(np.nanmin(allpts[:, 2]))
    shifted = []
    for poly in polys:
        p = poly.copy()
        p[:, 2] -= zmin
        shifted.append(p)
    ax.add_collection3d(Poly3DCollection(shifted, facecolor=poly_colors, edgecolor="k", linewidths=0.22, alpha=0.92))
    minx, miny, maxx, maxy = footprint.bounds
    pad = max(maxx - minx, maxy - miny) * 0.15
    ax.set_xlim(minx - pad, maxx + pad)
    ax.set_ylim(miny - pad, maxy + pad)
    ax.set_zlim(0, max(float(np.nanmax(allpts[:, 2]) - zmin) * 1.2, 1.0))
    ax.view_init(elev=32, azim=-58)
    ax.set_xticks([])
    ax.set_yticks([])
    ax.set_zticks([])
    ax.set_box_aspect((1, 1, 0.45))
    if note:
        ax.text2D(0.02, 0.92, note, transform=ax.transAxes, fontsize=5.8)


def load_eight_module():
    import e5_c001_8way as e

    e.configure_korean_font()
    return e


def make_case_panels() -> list[Path]:
    e = load_eight_module()
    src_all = e.sources()
    raw_dense = next(src for src in src_all if src.source_run == "raw_dense")
    s0_dense = next(src for src in src_all if src.source_run == "gs_dense_r1")
    s0_dense.display_label = "GS-S0 dense r1"
    s1_dense = e.Source(
        "gs_dense",
        "base__gs_e5_C001_s1_dense_r1",
        "GS-S1 dense r1",
        "gs",
        P0_RUN_DIR / "base/status/gs_e5_C001_s1_dense_r1_run_1.csv",
        None,
        P0_RUN_DIR / "base/cityjson/gs_e5_C001_s1_dense_r1_run_1.city.json",
        None,
        pointcloud_template=str(P0_RUN_DIR / "base/roofer/gs_e5_C001_s1_dense_r1/run_1/{bid}_run_1_classified.las"),
        pair_raw="raw_dense",
        run_name="gs_e5_C001_s1_dense_r1",
        seed="dense",
        replicate="r1",
        readout="S1 base readout(minobs3, voxel0.05, SOR)",
        source_badge="S1",
        z_shift_to_reference_m=-45.7,
    )
    ref_src = e.Source("reference", "reference", "참조 LoD2", "reference", None, None, None, None)
    srcs = [raw_dense, s0_dense, s1_dense, ref_src]
    refs = e.parse_lod2_roofs(e.LOD2_DIR, set(TEXTURE_CASES))
    pred: dict[str, dict[str, list[Any]]] = {}
    for src in srcs:
        if src.status_role == "reference":
            pred[src.source_run] = {bid: refs[bid] for bid in TEXTURE_CASES}
        else:
            parsed = e.parse_cityjson_roofs(src.cityjson_path, set(TEXTURE_CASES))
            pred[src.source_run] = {bid: e.shift_surface_z(surfaces, src.z_shift_to_reference_m) for bid, surfaces in parsed.items()}
    metric_rows = read_csv(REPO / "docs/experiments/e5_c001_8way/tables/e5_c001_8way_metrics.csv") + read_csv(ab.METRICS_CSV)
    metric_by = {(r["source_run"], r["building_id"]): r for r in metric_rows}
    footprints = e.base.load_footprints(e.FOOTPRINTS_GPKG, set(TEXTURE_CASES))
    cache = e.PointCloudCache(footprints)
    out_paths: list[Path] = []
    for bid in TEXTURE_CASES:
        fig = plt.figure(figsize=(10.5, 5.2))
        cols = [raw_dense, s0_dense, s1_dense, ref_src]
        for i, src in enumerate(cols, start=1):
            if src.status_role == "reference":
                e.draw_model(fig.add_subplot(2, 4, i, projection="3d"), refs[bid], footprints[bid], "reference", f"roof {len(refs[bid])}")
                e.draw_model(fig.add_subplot(2, 4, 4 + i, projection="3d"), refs[bid], footprints[bid], "per-facet ref", f"roof {len(refs[bid])}")
                continue
            row = metric_by.get((src.source_run, bid), {})
            pts = cache.read_roof_points(src, bid)
            e.draw_cloud(fig.add_subplot(2, 4, i), pts, footprints[bid], f"{src.display_label}\nC {row.get('completeness', '-')} R {row.get('correctness', '-')}")
            note = f"roof {row.get('roof_planes', '-')}/{row.get('ref_roof_planes', '-')}\nRMS {row.get('ref_rms_m', '-')}"
            draw_distance_model(fig.add_subplot(2, 4, 4 + i, projection="3d"), pred[src.source_run][bid], refs[bid], footprints[bid], "facet distance", note)
        fig.suptitle(f"S1 texture case panel: {bid} ({TEXTURE_LABEL[bid]})", fontsize=11)
        fig.tight_layout(rect=(0, 0, 1, 0.95))
        out = FIG_DIR / f"case_panel_{bid.replace('DEBY_LOD2_', '')}.png"
        fig.savefig(out, dpi=160)
        plt.close(fig)
        out_paths.append(out)
    return out_paths


def md_table(rows: list[dict[str, Any]], columns: list[str], max_rows: int | None = None) -> str:
    use = rows if max_rows is None else rows[:max_rows]
    lines = ["| " + " | ".join(columns) + " |", "|" + "|".join("---" for _ in columns) + "|"]
    for row in use:
        lines.append("| " + " | ".join(str(row.get(col, "")) for col in columns) + " |")
    if max_rows is not None and len(rows) > max_rows:
        lines.append("| ... | " + f"{len(rows) - max_rows} rows omitted |" + " | ".join("" for _ in columns[2:]) + " |")
    return "\n".join(lines)


def write_versions(figures: list[Path]) -> None:
    P2_RUN_DIR.mkdir(parents=True, exist_ok=True)
    lines = [
        "# E5 C001 ③b-S1 surface-restoration versions",
        f"created_utc={datetime.now(timezone.utc).isoformat()}",
        f"branch={run_text(['git', 'branch', '--show-current'])}",
        f"head={run_text(['git', 'rev-parse', 'HEAD'])}",
        "mode=S1 retrain experiment line; canonical S0 unchanged; no verdict",
        f"data_root={DATA_ROOT}",
        "seed_z_constant=-558.3",
        "random_seed=2001",
        "distortion_normalization=loss_distort = mean(rend_dist) / ||bbox_max-bbox_min||_2^2; total += 100 * loss_distort",
        "S1_recipe=w_distort=100 scene_extent_sq; prune_opa=0.05; w_depth exp_decay 0.5->0.05 over 30000 iters; in-plane elongation densify gate min/max>0.01; D4 semantic/structure terms unchanged",
        f"design_memo={rel(DESIGN_MEMO_PATH)} status={'present' if DESIGN_MEMO_PATH.exists() else 'missing_in_checkout; applied dispatch §6/§0.5 plus fixed CityGaussianV2 read values'}",
        "CityGaussianV2_read=" + json.dumps(CITYGSV2_SOURCE, ensure_ascii=False, sort_keys=True),
        "",
        "outputs:",
        f"- {rel(REPORT_PATH)}",
        "- docs/experiments/e5_c001_3b_s1/tables/e5_c001_3b_s1_delta.csv",
        "- docs/experiments/e5_c001_3b_s1/tables/e5_c001_3b_s1_texture_strata.csv",
        "- docs/experiments/e5_c001_3b_s1/tables/e5_c001_3b_s1_voxel02.csv",
        f"- {rel(ab.METRICS_CSV)}",
        f"- {rel(ab.COVERAGE_CSV)}",
        f"- {rel(P2_RUN_DIR / 'train_fingerprints.csv')}",
        f"- {rel(P2_RUN_DIR / 'readout_fingerprints.csv')}",
        f"- {rel(P0_RUN_DIR / 'versions.txt')}",
    ]
    for fig in figures:
        lines.append(f"- {rel(fig)}")
    (P2_RUN_DIR / "versions.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_readout_temp_report(
    settings: list[Any],
    inventory: list[dict[str, Any]],
    summary: list[dict[str, Any]],
    tradeoff: list[dict[str, Any]],
    filter_rows: list[dict[str, Any]],
    cases: list[dict[str, Any]],
    figures: list[Path],
) -> None:
    """S1 only runs base/voxel02, so avoid the ③a report's relaxed-setting assumption."""

    lines = [
        "# E5 C001 ③b-S1 readout/evaluation temporary report",
        "",
        "S1 wrapper executed base and voxel02 only. Final interpretation material is written to `docs/experiments/e5_c001_3b_s1/reports/W_E5_C001_③b_S1_표면복원.md`.",
        "",
        "## Summary",
        "",
        md_table(summary, ["setting", "mean_coverage_post_sor", "mean_completeness", "mean_correctness", "median_ref_rms_m", "has_lod22", "val3dity_valid"]),
        "",
        "## Outputs",
        "",
        f"- metrics: `{rel(ab.METRICS_CSV)}`",
        f"- coverage: `{rel(ab.COVERAGE_CSV)}`",
        f"- inventory rows: {len(inventory)}",
        f"- tradeoff rows: {len(tradeoff)}",
        f"- filter rows: {len(filter_rows)}",
        f"- case rows: {len(cases)}",
        f"- figures: {', '.join('`' + rel(p) + '`' for p in figures)}",
    ]
    TEMP_READOUT_REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_report() -> None:
    configure_ablation_module()
    P2_RUN_DIR.mkdir(parents=True, exist_ok=True)
    delta_rows = build_delta_rows()
    texture_rows = build_texture_rows()
    voxel_rows = build_voxel_rows()
    figures: list[Path] = [
        plot_delta(delta_rows),
        plot_texture(texture_rows),
        plot_voxel(voxel_rows),
    ]
    for maybe in [plot_floater(), plot_render_tsdf()]:
        if maybe is not None:
            figures.append(maybe)
    try:
        figures.extend(make_case_panels())
    except Exception as exc:  # noqa: BLE001 - keep report material even if a panel fails.
        (P2_RUN_DIR / "case_panel_issue.txt").write_text(str(exc) + "\n", encoding="utf-8")

    readout_summary = read_csv(ab.SUMMARY_CSV) if ab.SUMMARY_CSV.exists() else []
    floater_note = "S1 render/floater CSV가 있으면 `docs/e5_c001_3b_s1_render_*`로 병기했다."
    floater_gate_note = "플로터 지표는 render audit CSV 미생성으로 별도 gate 관찰을 비워 둔다."
    if (REPO / "docs/experiments/e5_c001_3b_s1/tables/e5_c001_3b_s1_render_floater_metrics.csv").exists():
        s1f = read_csv(REPO / "docs/experiments/e5_c001_3b_s1/tables/e5_c001_3b_s1_render_floater_metrics.csv")
        s0f = [r for r in read_csv(REPO / "docs/experiments/e5_c001_render/tables/e5_c001_render_floater_metrics.csv") if r.get("replicate") == "r1"]
        s0_op = mean([v for v in (num(r.get("opacity_below_prune005_frac")) for r in s0f) if v is not None])
        s1_op = mean([v for v in (num(r.get("opacity_below_prune005_frac")) for r in s1f) if v is not None])
        s0_el = mean([v for v in (num(r.get("elongated_ratio_gt10_frac")) for r in s0f) if v is not None])
        s1_el = mean([v for v in (num(r.get("elongated_ratio_gt10_frac")) for r in s1f) if v is not None])
        s0_off = mean([v for v in (num(r.get("off_seed_gt1m_proxy_frac")) for r in s0f) if v is not None])
        s1_off = mean([v for v in (num(r.get("off_seed_gt1m_proxy_frac")) for r in s1f) if v is not None])
        floater_note = (
            f"opacity<0.005 mean S0={s0_op or 0.0:.3f}, "
            f"S1={s1_op or 0.0:.3f}; "
            f"elongated>10 mean S0={s0_el or 0.0:.3f}, "
            f"S1={s1_el or 0.0:.3f}; "
            f"off-seed>1m proxy mean S0={s0_off or 0.0:.3f}, "
            f"S1={s1_off or 0.0:.3f}."
        )
        floater_gate_note = (
            "opacity 지표는 감소했지만 elongated/off-seed proxy는 증가해 "
            "2씨드 확장 gate(플로터↓·정확도↑)는 혼합 관찰로 남겼다."
        )
    cov_delta = [v for v in (num(r.get("delta_coverage")) for r in delta_rows) if v is not None]
    corr_delta = [v for v in (num(r.get("delta_correctness")) for r in delta_rows) if v is not None]
    rms_delta = [v for v in (num(r.get("delta_median_ref_rms_m")) for r in delta_rows) if v is not None]
    textured = [r for r in texture_rows if r.get("building_id") == "DEBY_LOD2_4907184"]
    textured_s0 = mean([v for v in (num(r.get("s0_ref_rms_m")) for r in textured) if v is not None])
    textured_s1 = mean([v for v in (num(r.get("s1_ref_rms_m")) for r in textured) if v is not None])
    textureless_s1 = [v for v in (num(r.get("s1_ref_rms_m")) for r in texture_rows if r.get("texture_bucket") == "textureless") if v is not None]
    observation_line = (
        f"S1 1씨드에서 coverage delta {min(cov_delta):.3f}~{max(cov_delta):.3f}, "
        f"correctness delta {min(corr_delta):.3f}~{max(corr_delta):.3f}, "
        f"median RMS delta {min(rms_delta):.2f}~{max(rms_delta):.2f}m; "
        f"textured 4907184 RMS {textured_s0 or 0.0:.2f}->{textured_s1 or 0.0:.2f}m; "
        f"textureless available S1 RMS mean {mean(textureless_s1) or 0.0:.2f}m with 8568391 sparse/dense 미조립 잔차."
    )
    lines = [
        "# E5 C001 ③b-S1 표면 복원 재학습",
        "",
        "> 재확인: S1 재학습 3런 · 정본(canonical) S0 미변경 · 별도 브랜치/실험선 · 판정 0. 산출물 CRS는 EPSG:25832, readout/Roofer/8-way는 기존 정본 절차를 S1 체크포인트에 재적용했다.",
        "",
        "## 실행 지문",
        "",
        f"- 브랜치/HEAD: `{run_text(['git', 'branch', '--show-current'])}` / `{run_text(['git', 'rev-parse', '--short', 'HEAD'])}`.",
        f"- 학습 지문: `{rel(P2_RUN_DIR / 'train_fingerprints.csv')}`.",
        f"- readout/Roofer 지문: `{rel(P2_RUN_DIR / 'readout_fingerprints.csv')}`, `{rel(P0_RUN_DIR / 'versions.txt')}`.",
        "- seed z 상수: `-558.3`; 난수 seed: `2001`.",
        f"- 설계 메모: `{rel(DESIGN_MEMO_PATH)}`는 현 checkout에서 발견되지 않아, 발주문 §6/§0.5와 CityGaussianV2 고정 커밋 읽은 값을 적용했다.",
        "- distortion 정규화: `loss_distort = mean(rend_dist) / ||bbox_max-bbox_min||_2^2`, S1 가중 `100`.",
        f"- CityGaussianV2 읽은 값: `{CITYGSV2_SOURCE['repo']}` `{CITYGSV2_SOURCE['commit']}`; depth scheduler `{CITYGSV2_SOURCE['citygsv2_trim_depth']}`, elongation `{CITYGSV2_SOURCE['elongation_axis_ratio_threshold']}`, prune `{CITYGSV2_SOURCE['prune_opacity_threshold']}`.",
        "",
        "## 관찰 한 줄",
        "",
        f"- {observation_line}",
        f"- 확장 메모: 2씨드(+3런)는 자동 실행하지 않았다. {floater_gate_note}",
        "",
        "## S0↔S1 델타",
        "",
        md_table(delta_rows, ["arm", "s0_coverage", "s1_coverage", "delta_coverage", "s0_completeness", "s1_completeness", "s0_correctness", "s1_correctness", "s0_median_ref_rms_m", "s1_median_ref_rms_m", "s0_has_lod22", "s1_has_lod22"]),
        "",
        f"- 짝 그림: `{rel(FIG_DIR / 's0_s1_delta_summary.png')}`.",
        "",
        "## 텍스처 층화",
        "",
        md_table(texture_rows, ["building_id", "texture_bucket", "arm", "s0_ref_rms_m", "s1_ref_rms_m", "s0_completeness", "s1_completeness", "s0_correctness", "s1_correctness", "s1_shell_bucket"], max_rows=12),
        "",
        f"- 짝 그림: `{rel(FIG_DIR / 'texture_strata_ref_rms.png')}`.",
        f"- 대표 건물 패널: `{rel(FIG_DIR / 'case_panel_4907184.png')}`, `{rel(FIG_DIR / 'case_panel_60098.png')}`, `{rel(FIG_DIR / 'case_panel_8568391.png')}`.",
        "",
        "## 플로터 지표",
        "",
        f"- 관찰: {floater_note}",
        f"- 짝 그림: `{rel(FIG_DIR / 'floater_s0_s1_metrics.png')}`.",
        "",
        "## 천장 시험",
        "",
        md_table(readout_summary, ["setting", "mean_coverage_post_sor", "mean_correctness", "median_ref_rms_m", "has_lod22", "val3dity_valid"], max_rows=4),
        "",
        f"- S1 base↔voxel02 건물별 표: `docs/experiments/e5_c001_3b_s1/tables/e5_c001_3b_s1_voxel02.csv`.",
        f"- 짝 그림: `{rel(FIG_DIR / 'voxel02_ref_rms_scatter.png')}`.",
        "",
        "## GS 학습 vs TSDF 분리",
        "",
        "- render-depth backprojection coverage, TSDF pre-SOR, TSDF post-SOR를 S0/S1 arm별로 분리했다.",
        f"- 짝 그림: `{rel(FIG_DIR / 'render_vs_tsdf_coverage.png')}`.",
        "",
        "## 관찰 라우팅 재료",
        "",
        "- 판정 문구는 두지 않았다. 위 표와 그림은 S2(mono-normal) 진입 여부와 textureless 잔차 표적 폭 판단을 위한 재료다.",
        "- 한계: C001·1씨드·첫 재학습이며, S1 단독으로 프레임 전환을 결정하지 않는다.",
        "",
        "## 산출물",
        "",
        f"- 수치표: `{rel(ab.METRICS_CSV)}`, `{rel(ab.COVERAGE_CSV)}`, `docs/experiments/e5_c001_3b_s1/tables/e5_c001_3b_s1_delta.csv`, `docs/experiments/e5_c001_3b_s1/tables/e5_c001_3b_s1_texture_strata.csv`, `docs/experiments/e5_c001_3b_s1/tables/e5_c001_3b_s1_voxel02.csv`.",
        f"- 그림 디렉터리: `{rel(FIG_DIR)}/`.",
        f"- versions: `{rel(P2_RUN_DIR / 'versions.txt')}`.",
    ]
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    write_versions(figures)
    print(json.dumps({"report": rel(REPORT_PATH), "figures": [rel(p) for p in figures]}, ensure_ascii=False))


def evaluate_or_container(args: argparse.Namespace) -> None:
    configure_ablation_module()
    if os.environ.get("E5_3B_S1_EVAL_CONTAINER") == "1":
        ab.evaluate(args)
        return
    try:
        ab.load_eight_module()
    except ModuleNotFoundError:
        cmd = [
            "docker",
            "run",
            "--rm",
            "-i",
            "--user",
            f"{os.getuid()}:{os.getgid()}",
            "-e",
            "E5_3B_S1_EVAL_CONTAINER=1",
            "-e",
            "MPLCONFIGDIR=/tmp/matplotlib",
            "-v",
            f"{REPO}:/workspace/JointBuildGS",
            "-w",
            "/workspace/JointBuildGS",
            "jointbuildgs-p0-tools:t0",
            "python3",
            "phases/p2-gsjso/scripts/e5_c001_3b_s1.py",
            "evaluate",
        ]
        if args.settings:
            cmd.append("--settings")
            cmd.extend(args.settings)
        if args.runs:
            cmd.append("--runs")
            cmd.extend(args.runs)
        if args.force:
            cmd.append("--force")
        ab.run(cmd, log_path=P2_RUN_DIR / "evaluate_container.log", check=True, quiet=False)
        return
    ab.evaluate(args)


def build_parser() -> argparse.ArgumentParser:
    configure_ablation_module()
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    for name in ["readout", "assemble", "evaluate", "all"]:
        p = sub.add_parser(name)
        p.add_argument("--settings", nargs="*", default=None)
        p.add_argument("--runs", nargs="*", default=None)
        p.add_argument("--force", action="store_true")
        p.add_argument("--data-root", default=DATA_ROOT)
        p.add_argument("--torch-extensions", default=TORCH_EXTENSIONS)
        p.add_argument("--gpu", default="0")
        p.add_argument("--buffer-m", type=float, default=20.0)
    sub.add_parser("report")
    sub.add_parser("fingerprint-training")
    return parser


def main() -> None:
    os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib")
    args = build_parser().parse_args()
    configure_ablation_module()
    if args.cmd in {"readout", "all"}:
        ab.run_readout(args)
    if args.cmd in {"assemble", "all"}:
        ab.run_assemble(args)
    if args.cmd in {"evaluate", "all"}:
        evaluate_or_container(args)
    if args.cmd == "report":
        build_report()
    if args.cmd == "fingerprint-training":
        write_train_fingerprints()


if __name__ == "__main__":
    main()
