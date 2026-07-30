#!/usr/bin/env python3
"""E5 C001 corrected-S1 recheck.

This is a diagnostic wrapper for the corrected-S1 follow-up order.  It keeps
the canonical S0/S1/corrected-S1 artifacts read-only and redirects the existing
C001 readout/Roofer/val3dity/reference harness to post-hoc opacity-thresholded
copies of the allowed pre-final-prune fallback checkpoints.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import shutil
import subprocess
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.path import Path as MplPath

SCRIPT_DIR = Path(__file__).resolve().parent
REPO = Path(__file__).resolve().parents[3]
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

import e5_c001_3b_s1 as s1  # noqa: E402
from e5_pilot_gate_tools import C001_IDS, P0_RUNS, sha256_file  # noqa: E402


RUN_ID = "20260709_e5_c001_corrected_s1_recheck"
P2_RUN_DIR = REPO / "phases/p2-gsjso/runs" / RUN_ID
SNAP_DIR = P2_RUN_DIR / "snapshots"
P0_RUN_ID = "e5p_corrected_s1_recheck_20260709_C001"
P0_RUN_DIR = P0_RUNS / P0_RUN_ID
RESULTS_ROOT = REPO / "results/tum_transfer/e5_corrected_s1_recheck/C001/readout_ablation"
CKPT_ROOT = REPO / "results/tum_transfer/e5_corrected_s1_recheck/C001/runs"
SOURCE_PREPRUNE_ROOT = CKPT_ROOT
DATA_ROOT = "results/tum_transfer/e5_pilot/C001/data_geoidfix_C001_buf20"
TORCH_EXTENSIONS = "results/tum_transfer/e5_corrected_s1_recheck/C001/torch_extensions_eval"
FIG_DIR = REPO / "docs/figs/e5_c001_corrected_s1_recheck"
READOUT_FIG_DIR = FIG_DIR / "readout"
REPORT_PATH = REPO / "docs/experiments/joint-optimization/e5_c001_corrected_s1_recheck/reports/W_E5_C001_corrected_S1_재점검.md"
TEMP_READOUT_REPORT = REPO / "docs/W_E5_C001_corrected_S1_recheck_readout_tmp.md"

CONFIG_DIR = REPO / "configs/tum_mob/e5_corrected_s1_recheck"
FOOTPRINTS_GEOJSON = REPO / "phases/p0-audit/data/work/footprints/lod2_ground_plan.geojson"
SHIFT_UTM = np.array([690953.0, 5336071.0, 604.0], dtype=np.float64)

ARMS = ["sparse", "dense", "acmp"]
GPU_BY_ARM = {"sparse": "0", "dense": "1", "acmp": "1"}
THRESHOLDS = [
    ("keepall", 0.0),
    ("opa001", 0.01),
    ("opa002", 0.02),
    ("opa005", 0.05),
]
THRESHOLD_LABEL = {key: key for key, _ in THRESHOLDS}
NORMAL6 = ["4907184", "4908168", "4907202", "4907198", "4907185", "4908178"]
DEFECT_POLLUTED = ["60098", "4907186"]
DEFECT_THIN = ["4907188", "4907194", "4907195"]
TEXTURELESS_OBS = ["4907199", "8568391", "8568392"]
ROOFCROP_IDS = ["4907202", "4908168", "4907185", "4907184", "8568392"]
PANEL_IDS = ["4907184", "60098", "8568391"]

PREPRUNE_RUN = {arm: f"gs_e5_C001_corrected_s1_preprune_{arm}_r1" for arm in ARMS}
THRESHOLD_RUNS = [
    f"gs_e5_C001_corrected_s1_preprune_{threshold}_{arm}_r1"
    for threshold, _value in THRESHOLDS
    for arm in ARMS
]
MID20K_RUNS = [
    f"gs_e5_C001_corrected_s1_preprune_mid20k_{arm}_r1"
    for arm in ARMS
]
S1_SOURCE_BY_ARM = {
    "sparse": "base__gs_e5_C001_s1_sparse_r1",
    "dense": "base__gs_e5_C001_s1_dense_r1",
    "acmp": "base__gs_e5_C001_s1_acmp_r1",
}
CORRECTED_SOURCE_BY_ARM = {
    "sparse": "base__gs_e5_C001_corrected_s1_sparse_r1",
    "dense": "base__gs_e5_C001_corrected_s1_dense_r1",
    "acmp": "base__gs_e5_C001_corrected_s1_acmp_r1",
}

CSV_SNAPSHOT_INVENTORY = REPO / "docs/experiments/joint-optimization/e5_c001_corrected_s1_recheck/tables/e5_c001_corrected_s1_recheck_snapshot_inventory.csv"
CSV_CKPT_THRESHOLDS = REPO / "docs/experiments/joint-optimization/e5_c001_corrected_s1_recheck/tables/e5_c001_corrected_s1_recheck_ckpt_thresholds.csv"
CSV_PRUNE_SWEEP = REPO / "docs/experiments/joint-optimization/e5_c001_corrected_s1_recheck/tables/e5_c001_corrected_s1_recheck_prune_sweep.csv"
CSV_PREPRUNE_COVERAGE = REPO / "docs/experiments/joint-optimization/e5_c001_corrected_s1_recheck/tables/e5_c001_corrected_s1_recheck_preprune_coverage.csv"
CSV_GAUSSIAN_ROOFCROP = REPO / "docs/experiments/joint-optimization/e5_c001_corrected_s1_recheck/tables/e5_c001_corrected_s1_recheck_gaussian_roofcrop.csv"
CSV_VAL3DITY_TYPES = REPO / "docs/experiments/joint-optimization/e5_c001_corrected_s1_recheck/tables/e5_c001_corrected_s1_recheck_val3dity_types.csv"
CSV_FLOATER_RENDER = REPO / "docs/experiments/joint-optimization/e5_c001_corrected_s1_recheck/tables/e5_c001_corrected_s1_recheck_floater_render.csv"
CSV_MONO_NORMAL = REPO / "docs/experiments/joint-optimization/e5_c001_corrected_s1_recheck/tables/e5_c001_corrected_s1_recheck_mono_normal_stats.csv"
CSV_ISSUES = REPO / "docs/experiments/joint-optimization/e5_c001_corrected_s1_recheck/tables/e5_c001_corrected_s1_recheck_issues.csv"
CSV_CONFIG_DIFF = REPO / "docs/experiments/joint-optimization/e5_c001_corrected_s1_recheck/tables/e5_c001_corrected_s1_recheck_config_diff.csv"


def rel(path: Path | str | None) -> str:
    if path is None:
        return ""
    p = Path(path)
    for root in (REPO, Path("/workspace/JointBuildGS")):
        try:
            return str(p.relative_to(root))
        except ValueError:
            pass
    text = str(p)
    prefix = "/workspace/JointBuildGS/"
    return text[len(prefix) :] if text.startswith(prefix) else text


def full_id(short: str) -> str:
    return short if short.startswith("DEBY_LOD2_") else f"DEBY_LOD2_{short}"


def short_id(bid: str) -> str:
    return bid.replace("DEBY_LOD2_", "")


def num(value: Any) -> float | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() in {"nan", "none", "null", "na"}:
        return None
    try:
        out = float(text)
    except ValueError:
        return None
    return out if math.isfinite(out) else None


def tf(value: Any) -> bool:
    return str(value).strip().lower() in {"true", "1", "yes", "y"}


def fmt(value: Any, digits: int = 4) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, np.integer)):
        return str(int(value))
    if isinstance(value, (float, np.floating)):
        v = float(value)
        return f"{v:.{digits}f}" if math.isfinite(v) else ""
    return str(value)


def mean(values: list[float]) -> float | None:
    return float(np.mean(values)) if values else None


def median(values: list[float]) -> float | None:
    return float(np.median(values)) if values else None


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if fields is None:
        fields = []
        for row in rows:
            for key in row:
                if key not in fields:
                    fields.append(key)
    with path.open("w", newline="", encoding="utf-8") as fh:
        if not fields:
            return
        writer = csv.DictWriter(fh, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def append_issue(part: str, severity: str, message: str, path: Path | str | None = None) -> None:
    rows = read_csv(CSV_ISSUES)
    rows.append(
        {
            "part": part,
            "severity": severity,
            "message": message,
            "path": rel(path),
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        }
    )
    write_csv(CSV_ISSUES, rows, ["part", "severity", "message", "path", "timestamp_utc"])
    issue_md = REPO / "phases/p2-gsjso/docs/issues.md"
    if issue_md.exists():
        line = f"- 2026-07-09 corrected-S1 recheck {part}: {severity} - {message}"
        if path:
            line += f" ({rel(path)})"
        text = issue_md.read_text(encoding="utf-8")
        if line not in text:
            with issue_md.open("a", encoding="utf-8") as fh:
                fh.write(line + "\n")


def run_text(cmd: list[str]) -> str:
    try:
        proc = subprocess.run(cmd, cwd=REPO, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
        return (proc.stdout or "").strip()
    except FileNotFoundError as exc:
        return f"not_available:{exc.filename}"


def configure() -> None:
    s1.RUN_ID = RUN_ID
    s1.P2_RUN_DIR = P2_RUN_DIR
    s1.P0_RUN_ID = P0_RUN_ID
    s1.P0_RUN_DIR = P0_RUN_DIR
    s1.RESULTS_ROOT = RESULTS_ROOT
    s1.CKPT_ROOT = CKPT_ROOT
    s1.TRAIN_RUN_DIR = P2_RUN_DIR
    s1.DATA_ROOT = DATA_ROOT
    s1.TORCH_EXTENSIONS = TORCH_EXTENSIONS
    s1.FIG_DIR = FIG_DIR
    s1.READOUT_FIG_DIR = READOUT_FIG_DIR
    s1.REPORT_PATH = REPORT_PATH
    s1.TEMP_READOUT_REPORT = TEMP_READOUT_REPORT
    s1.S1_RUN_NAMES = THRESHOLD_RUNS + MID20K_RUNS
    s1.configure_ablation_module()
    s1.ab.RESULTS_ROOT = RESULTS_ROOT
    s1.ab.CKPT_ROOT = CKPT_ROOT
    s1.ab.P2_RUN_DIR = P2_RUN_DIR
    s1.ab.P0_RUN_ID = P0_RUN_ID
    s1.ab.P0_RUN_DIR = P0_RUN_DIR
    s1.ab.DATA_ROOT = DATA_ROOT
    s1.ab.TORCH_EXTENSIONS = TORCH_EXTENSIONS
    s1.ab.FIG_DIR = READOUT_FIG_DIR
    s1.ab.SETTINGS = [
        s1.ab.Setting("base", "preprune threshold sweep base readout", min_obs=3, voxel=0.05, sor="on", sor_std=2.0),
        s1.ab.Setting("voxel02", "best-threshold voxel0.02 ceiling test", min_obs=3, voxel=0.02, sor="on", sor_std=2.0),
    ]
    s1.ab.COVERAGE_CSV = CSV_PREPRUNE_COVERAGE
    s1.ab.FILTER_CSV = REPO / "docs/experiments/joint-optimization/e5_c001_corrected_s1_recheck/tables/e5_c001_corrected_s1_recheck_filter_contrib.csv"
    s1.ab.METRICS_CSV = REPO / "docs/experiments/joint-optimization/e5_c001_corrected_s1_recheck/tables/e5_c001_corrected_s1_recheck_building_8way.csv"
    s1.ab.SUMMARY_CSV = REPO / "docs/experiments/joint-optimization/e5_c001_corrected_s1_recheck/tables/e5_c001_corrected_s1_recheck_summary.csv"
    s1.ab.TRADEOFF_CSV = REPO / "docs/experiments/joint-optimization/e5_c001_corrected_s1_recheck/tables/e5_c001_corrected_s1_recheck_tradeoff.csv"
    s1.ab.CASE_CSV = REPO / "docs/experiments/joint-optimization/e5_c001_corrected_s1_recheck/tables/e5_c001_corrected_s1_recheck_representative_buildings.csv"
    s1.ab.INVENTORY_CSV = REPO / "docs/experiments/joint-optimization/e5_c001_corrected_s1_recheck/tables/e5_c001_corrected_s1_recheck_inventory.csv"
    s1.ab.ISSUES_CSV = REPO / "docs/experiments/joint-optimization/e5_c001_corrected_s1_recheck/tables/e5_c001_corrected_s1_recheck_readout_issues.csv"
    s1.ab.RENDER_COVERAGE = REPO / "docs/e5_c001_corrected_s1_recheck_render_readout_coverage.csv"
    s1.ab.selected_run_names = selected_run_names
    s1.ab.write_report = write_readout_temp_report


def threshold_from_run(run_name: str) -> str:
    parts = run_name.split("_")
    if len(parts) < 4:
        return ""
    return parts[-3]


def threshold_value(label: str) -> float:
    return dict(THRESHOLDS).get(label, float("nan"))


def selected_run_names(args: argparse.Namespace) -> list[str]:
    selected = getattr(args, "runs", None)
    all_runs = THRESHOLD_RUNS + MID20K_RUNS
    if not selected:
        return all_runs
    missing = sorted(set(selected) - set(all_runs))
    if missing:
        raise RuntimeError(f"unknown recheck run names: {missing}")
    selected_set = set(selected)
    return [name for name in all_runs if name in selected_set]


def write_readout_temp_report(*_args: Any, **_kwargs: Any) -> None:
    TEMP_READOUT_REPORT.parent.mkdir(parents=True, exist_ok=True)
    TEMP_READOUT_REPORT.write_text(
        "# corrected-S1 recheck readout tmp\n\n"
        "> Generated by the unchanged C001 ablation harness redirected to post-hoc opacity-threshold checkpoints.\n",
        encoding="utf-8",
    )


def inventory_snapshots(_args: argparse.Namespace) -> None:
    rows: list[dict[str, Any]] = []
    for family, root, runs in [
        ("corrected_s1", REPO / "results/tum_transfer/e5_corrected_s1/C001/runs", [f"gs_e5_C001_corrected_s1_{a}_r1" for a in ARMS]),
        ("recheck_preprune_fallback", SOURCE_PREPRUNE_ROOT, [PREPRUNE_RUN[a] for a in ARMS]),
    ]:
        for run_name in runs:
            run_dir = root / run_name
            ckpt_dir = run_dir / "ckpt"
            files = sorted(ckpt_dir.glob("*.pt")) if ckpt_dir.exists() else []
            rows.append(
                {
                    "family": family,
                    "run_name": run_name,
                    "arm": run_name.split("_")[-2],
                    "run_dir": rel(run_dir),
                    "effective_config": rel(run_dir / "effective_config.json") if (run_dir / "effective_config.json").exists() else "",
                    "has_final": str((ckpt_dir / "final.pt").exists()).lower(),
                    "has_final_preprune": "false",
                    "available_ckpts": ";".join(p.name for p in files),
                    "ckpt_count": len(files),
                    "step_ckpts": ";".join(p.name for p in files if p.name.startswith("step_")),
                    "notes": "final-prune-pre state absent in corrected-S1; fallback final has final_prune_opa=0" if family == "recheck_preprune_fallback" else "no explicit pre-final-prune ckpt found",
                }
            )
    write_csv(CSV_SNAPSHOT_INVENTORY, rows)
    print(json.dumps({"inventory": rel(CSV_SNAPSHOT_INVENTORY), "rows": len(rows)}, ensure_ascii=False))


def filter_checkpoint_state(payload: dict[str, Any], keep: Any) -> dict[str, Any]:
    import torch

    n = int(payload["state_dict"]["means"].shape[0])
    out: dict[str, Any] = {}
    for key, value in payload.items():
        if key == "state_dict":
            state: dict[str, Any] = {}
            for s_key, tensor in value.items():
                if hasattr(tensor, "shape") and len(tensor.shape) >= 1 and int(tensor.shape[0]) == n:
                    state[s_key] = tensor[keep].contiguous()
                else:
                    state[s_key] = tensor
            out[key] = state
        elif key == "stage2_group_ids" and hasattr(value, "shape") and len(value.shape) >= 1 and int(value.shape[0]) == n:
            out[key] = value[keep].contiguous()
        elif key in {"final_prune_candidates"} and hasattr(value, "shape") and len(value.shape) >= 1 and int(value.shape[0]) == n:
            out[key] = value[keep].contiguous()
        else:
            out[key] = value
    out["n_prim"] = int(keep.sum().item() if hasattr(keep, "sum") else len(keep))
    out["posthoc_thresholded"] = True
    return out


def make_threshold_ckpts(_args: argparse.Namespace) -> None:
    import torch

    rows: list[dict[str, Any]] = []
    for arm in ARMS:
        source_run = PREPRUNE_RUN[arm]
        source_dir = SOURCE_PREPRUNE_ROOT / source_run
        source_ckpt = source_dir / "ckpt/final.pt"
        if not source_ckpt.exists():
            raise FileNotFoundError(source_ckpt)
        payload = torch.load(source_ckpt, map_location="cpu", weights_only=False)
        op = torch.sigmoid(payload["state_dict"]["opacities_raw"].float())
        n_before = int(op.numel())
        for label, theta in THRESHOLDS:
            out_run = f"gs_e5_C001_corrected_s1_preprune_{label}_{arm}_r1"
            out_dir = CKPT_ROOT / out_run
            out_ckpt = out_dir / "ckpt/final.pt"
            out_ckpt.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_dir / "effective_config.json", out_dir / "effective_config.json")
            if theta <= 0:
                shutil.copy2(source_ckpt, out_ckpt)
                n_after = n_before
                keep_frac = 1.0
                low_count = 0
            else:
                keep = op >= float(theta)
                filtered = filter_checkpoint_state(payload, keep)
                filtered["posthoc_opacity_threshold"] = float(theta)
                filtered["posthoc_source_ckpt"] = rel(source_ckpt)
                torch.save(filtered, out_ckpt)
                n_after = int(keep.sum().item())
                keep_frac = float(n_after / max(1, n_before))
                low_count = int(n_before - n_after)
            rows.append(
                {
                    "arm": arm,
                    "threshold": label,
                    "threshold_value": theta,
                    "source_run": source_run,
                    "out_run": out_run,
                    "source_ckpt": rel(source_ckpt),
                    "out_ckpt": rel(out_ckpt),
                    "source_sha256": sha256_file(source_ckpt),
                    "out_sha256": sha256_file(out_ckpt),
                    "n_before": n_before,
                    "n_after": n_after,
                    "removed_count": low_count,
                    "keep_frac": fmt(keep_frac),
                    "opacity_p01": fmt(float(torch.quantile(op, 0.01))),
                    "opacity_p05": fmt(float(torch.quantile(op, 0.05))),
                    "opacity_p50": fmt(float(torch.quantile(op, 0.50))),
                    "opacity_lt_001_count": int((op < 0.01).sum().item()),
                    "opacity_lt_002_count": int((op < 0.02).sum().item()),
                    "opacity_lt_005_count": int((op < 0.05).sum().item()),
                }
            )
        mid_ckpt = source_dir / "ckpt/step_020000.pt"
        if mid_ckpt.exists():
            out_run = f"gs_e5_C001_corrected_s1_preprune_mid20k_{arm}_r1"
            out_dir = CKPT_ROOT / out_run
            out_ckpt = out_dir / "ckpt/final.pt"
            out_ckpt.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_dir / "effective_config.json", out_dir / "effective_config.json")
            shutil.copy2(mid_ckpt, out_ckpt)
            mid_payload = torch.load(mid_ckpt, map_location="cpu", weights_only=False)
            mid_op = torch.sigmoid(mid_payload["state_dict"]["opacities_raw"].float())
            rows.append(
                {
                    "arm": arm,
                    "threshold": "mid20k",
                    "threshold_value": "",
                    "source_run": source_run,
                    "out_run": out_run,
                    "source_ckpt": rel(mid_ckpt),
                    "out_ckpt": rel(out_ckpt),
                    "source_sha256": sha256_file(mid_ckpt),
                    "out_sha256": sha256_file(out_ckpt),
                    "n_before": int(mid_op.numel()),
                    "n_after": int(mid_op.numel()),
                    "removed_count": 0,
                    "keep_frac": "1.0000",
                    "opacity_p01": fmt(float(torch.quantile(mid_op, 0.01))),
                    "opacity_p05": fmt(float(torch.quantile(mid_op, 0.05))),
                    "opacity_p50": fmt(float(torch.quantile(mid_op, 0.50))),
                    "opacity_lt_001_count": int((mid_op < 0.01).sum().item()),
                    "opacity_lt_002_count": int((mid_op < 0.02).sum().item()),
                    "opacity_lt_005_count": int((mid_op < 0.05).sum().item()),
                    "note": "mid-training 20k snapshot copied for Step 1-B; not a final threshold sweep row",
                }
            )
    write_csv(CSV_CKPT_THRESHOLDS, rows)
    print(json.dumps({"threshold_ckpts": rel(CSV_CKPT_THRESHOLDS), "rows": len(rows)}, ensure_ascii=False))


def parse_train_elapsed(log_path: Path) -> str:
    if not log_path.exists():
        return ""
    marker = "[done] 30000 iter in "
    for line in reversed(log_path.read_text(encoding="utf-8", errors="replace").splitlines()):
        if marker in line:
            return line.split(marker, 1)[1].split(" min", 1)[0].strip()
    return ""


def train_fingerprints(_args: argparse.Namespace) -> None:
    import torch
    import yaml

    rows: list[dict[str, Any]] = []
    for arm in ARMS:
        run_name = PREPRUNE_RUN[arm]
        cfg = CONFIG_DIR / f"{run_name}.yaml"
        eff = SOURCE_PREPRUNE_ROOT / run_name / "effective_config.json"
        ckpt = SOURCE_PREPRUNE_ROOT / run_name / "ckpt/final.pt"
        log = P2_RUN_DIR / "logs" / f"train_preprune_{arm}.log"
        cfg_data = yaml.safe_load(cfg.read_text(encoding="utf-8")) if cfg.exists() else {}
        effective = json.loads(eff.read_text(encoding="utf-8")) if eff.exists() else {}
        state = torch.load(ckpt, map_location="cpu", weights_only=False) if ckpt.exists() else {}
        rows.append(
            {
                "run_name": run_name,
                "arm": arm,
                "replicate": "r1",
                "seed": cfg_data.get("seed", ""),
                "fallback_reason": "corrected-S1 has no explicit final-prune-pre checkpoint",
                "changed_from_corrected_s1": "final_prune_opa=0; ckpt_every=5000 only",
                "config": rel(cfg),
                "config_sha256": sha256_file(cfg) if cfg.exists() else "missing",
                "effective_config": rel(eff),
                "effective_config_sha256": sha256_file(eff) if eff.exists() else "missing",
                "ckpt": rel(ckpt),
                "ckpt_sha256": sha256_file(ckpt) if ckpt.exists() else "missing",
                "log": rel(log),
                "elapsed_min": parse_train_elapsed(log),
                "gpu_device": GPU_BY_ARM[arm],
                "max_iter": cfg_data.get("max_iter", ""),
                "final_n_gaussians": state.get("n_prim", "") if state else "",
                "final_prune_opa": state.get("final_prune_opa", "") if state else "",
                "final_pruned": state.get("final_pruned", "") if state else "",
                "distort_normalization": effective.get("distort_normalization", ""),
                "distort_norm_denominator": effective.get("distort_norm_denominator", ""),
                "w_distort": effective.get("w_distort", ""),
                "seed_protect_until_iter": effective.get("seed_protect_until_iter", ""),
                "prune_opa": effective.get("prune_opa", ""),
            }
        )
    write_csv(P2_RUN_DIR / "train_fingerprints.csv", rows)
    print(json.dumps({"train_fingerprints": rel(P2_RUN_DIR / "train_fingerprints.csv"), "rows": len(rows)}, ensure_ascii=False))


def evaluate_or_container(args: argparse.Namespace) -> None:
    configure()
    if os.environ.get("E5_RECHECK_EVAL_CONTAINER") == "1":
        s1.ab.evaluate(args)
        return
    try:
        s1.ab.load_eight_module()
    except ModuleNotFoundError:
        cmd = [
            "docker",
            "run",
            "--rm",
            "-i",
            "--user",
            f"{os.getuid()}:{os.getgid()}",
            "-e",
            "E5_RECHECK_EVAL_CONTAINER=1",
            "-e",
            "MPLCONFIGDIR=/tmp/matplotlib",
            "-v",
            f"{REPO}:/workspace/JointBuildGS",
            "-w",
            "/workspace/JointBuildGS",
            "jointbuildgs-p0-tools:t0",
            "python3",
            "scripts/e5_c001/p2_gsjso/e5_c001_corrected_s1_recheck.py",
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
        s1.ab.run(cmd, log_path=P2_RUN_DIR / "evaluate_container.log", check=True, quiet=False)
        return
    s1.ab.evaluate(args)


def arm_threshold_from_source(source_run: str, run_name: str | None = None) -> tuple[str, str]:
    rn = run_name or source_run.split("__", 1)[-1]
    parts = rn.split("_")
    return parts[-2], parts[-3]


def build_metric_indices() -> dict[str, dict[tuple[str, str, str], dict[str, str]]]:
    out: dict[str, dict[tuple[str, str, str], dict[str, str]]] = {}
    paths = {
        "raw_s0": REPO / "docs/experiments/evaluation/e5_c001_8way/tables/e5_c001_8way_metrics.csv",
        "s1": REPO / "docs/experiments/joint-optimization/e5_c001_3b_s1/tables/e5_c001_3b_s1_metrics.csv",
        "corrected": REPO / "docs/experiments/joint-optimization/e5_c001_corrected_s1/tables/e5_c001_corrected_s1_building_8way.csv",
        "recheck": REPO / "docs/experiments/joint-optimization/e5_c001_corrected_s1_recheck/tables/e5_c001_corrected_s1_recheck_building_8way.csv",
    }
    for label, path in paths.items():
        rows = {}
        for row in read_csv(path):
            key = (row.get("source_run", ""), row.get("building_id", ""), row.get("setting", ""))
            rows[key] = row
        out[label] = rows
    return out


def get_metric(metrics: dict[tuple[str, str, str], dict[str, str]], source_run: str, bid: str, setting: str = "base") -> dict[str, str] | None:
    return metrics.get((source_run, full_id(bid), setting))


def source_metrics(metrics_rows: list[dict[str, str]], setting: str, run_name: str) -> dict[str, Any]:
    part = [r for r in metrics_rows if r.get("setting") == setting and r.get("run_name") == run_name]
    rms = [num(r.get("ref_rms_m")) for r in part]
    rms_vals = [v for v in rms if v is not None]
    return {
        "has_lod22": sum(tf(r.get("has_lod22")) for r in part),
        "valid_assembled": sum(tf(r.get("has_lod22")) and tf(r.get("val3dity_valid")) for r in part),
        "invalid_assembled": sum(tf(r.get("has_lod22")) and not tf(r.get("val3dity_valid")) for r in part),
        "median_ref_rms_m": median(rms_vals),
        "mean_ref_rms_m": mean(rms_vals),
    }


def coverage_summary(coverage_rows: list[dict[str, str]], setting: str, run_name: str) -> dict[str, Any]:
    stages = defaultdict(list)
    for r in coverage_rows:
        if r.get("setting") == setting and r.get("run_name") == run_name:
            v = num(r.get("coverage_frac"))
            if v is not None:
                stages[r.get("stage", "")].append(v)
    return {f"mean_coverage_{stage}": mean(vals) for stage, vals in stages.items()}


def build_prune_sweep(_args: argparse.Namespace) -> None:
    metrics = read_csv(REPO / "docs/experiments/joint-optimization/e5_c001_corrected_s1_recheck/tables/e5_c001_corrected_s1_recheck_building_8way.csv")
    coverage = read_csv(CSV_PREPRUNE_COVERAGE)
    thresholds = read_csv(CSV_CKPT_THRESHOLDS)
    threshold_by = {(r["arm"], r["threshold"]): r for r in thresholds}
    s1 = read_csv(REPO / "docs/experiments/joint-optimization/e5_c001_3b_s1/tables/e5_c001_3b_s1_metrics.csv")
    raw = read_csv(REPO / "docs/experiments/evaluation/e5_c001_8way/tables/e5_c001_8way_metrics.csv")
    s1_by = {(r["source_run"], r["building_id"]): r for r in s1}
    raw_by = {(r["source_run"], r["building_id"]): r for r in raw}
    rows: list[dict[str, Any]] = []
    for threshold, theta in THRESHOLDS:
        for arm in ARMS:
            run_name = f"gs_e5_C001_corrected_s1_preprune_{threshold}_{arm}_r1"
            source_run = f"base__{run_name}"
            sm = source_metrics(metrics, "base", run_name)
            cov = coverage_summary(coverage, "base", run_name)
            normal_eval: list[dict[str, Any]] = []
            for sid in NORMAL6:
                bid = full_id(sid)
                row = next((r for r in metrics if r.get("setting") == "base" and r.get("run_name") == run_name and r.get("building_id") == bid), {})
                raw_row = raw_by.get(("raw_dense", bid), {})
                s1_row = s1_by.get((S1_SOURCE_BY_ARM["dense"], bid), {}) if arm == "dense" else s1_by.get((S1_SOURCE_BY_ARM[arm], bid), {})
                rms = num(row.get("ref_rms_m"))
                raw_rms = num(raw_row.get("ref_rms_m"))
                s1_rms = num(s1_row.get("ref_rms_m"))
                normal_eval.append(
                    {
                        "bid": sid,
                        "built": tf(row.get("has_lod22")),
                        "rms": rms,
                        "raw_rms": raw_rms,
                        "s1_rms": s1_rms,
                        "raw_anchor_ok": rms is not None and raw_rms is not None and rms <= raw_rms + 0.5,
                        "delta_vs_s1": None if rms is None or s1_rms is None else rms - s1_rms,
                    }
                )
            deltas = [x["delta_vs_s1"] for x in normal_eval if x["delta_vs_s1"] is not None]
            all_built = all(x["built"] for x in normal_eval)
            raw_anchor_count = sum(bool(x["raw_anchor_ok"]) for x in normal_eval)
            median_delta = median([float(x) for x in deltas])
            max_delta = max([float(x) for x in deltas], default=float("inf"))
            ck = threshold_by.get((arm, threshold), {})
            # S0 counts from corrected-S1 검수 (§2): sparse/dense/acmp.
            s0_count = {"sparse": 409546, "dense": 575318, "acmp": 627259}[arm]
            count_ok = num(ck.get("n_after")) is not None and float(ck["n_after"]) <= s0_count * 2
            dense_sparse_valid_baseline = {"dense": 10, "sparse": 11}.get(arm)
            valid_nonreg = True
            if dense_sparse_valid_baseline is not None:
                valid_nonreg = int(sm["valid_assembled"]) >= dense_sparse_valid_baseline - 1
            # Collapse-view depth was not recoverable from prior docs; keep it out of A-clean boolean.
            guardrail_ok = all_built and raw_anchor_count >= 5
            accuracy_nonreg = (median_delta is not None and median_delta <= 0.3 and max_delta <= 1.5)
            clean_count_ok = bool(count_ok)
            valid_gate_ok = bool(valid_nonreg)
            a_clean = arm == "dense" and guardrail_ok and accuracy_nonreg and clean_count_ok and valid_gate_ok
            rows.append(
                {
                    "setting": "base",
                    "threshold": threshold,
                    "threshold_value": theta,
                    "arm": arm,
                    "run_name": run_name,
                    "has_lod22": sm["has_lod22"],
                    "valid_assembled": sm["valid_assembled"],
                    "invalid_assembled": sm["invalid_assembled"],
                    "median_ref_rms_m": fmt(sm["median_ref_rms_m"]),
                    "mean_ref_rms_m": fmt(sm["mean_ref_rms_m"]),
                    "mean_coverage_pre_minobs": fmt(cov.get("mean_coverage_voxel_all_pre_minobs")),
                    "mean_coverage_post_minobs": fmt(cov.get("mean_coverage_minobs_post_gate_pre_sor")),
                    "mean_coverage_post_sor": fmt(cov.get("mean_coverage_sor_post_clean")),
                    "n_gaussians_after_threshold": ck.get("n_after", ""),
                    "removed_count": ck.get("removed_count", ""),
                    "keep_frac": ck.get("keep_frac", ""),
                    "normal6_all_built": str(all_built).lower(),
                    "normal6_raw_anchor_count": raw_anchor_count,
                    "normal6_median_delta_vs_s1_m": fmt(median_delta),
                    "normal6_max_delta_vs_s1_m": fmt(max_delta if math.isfinite(max_delta) else None),
                    "guardrail_ok": str(guardrail_ok).lower(),
                    "accuracy_nonreg_ok": str(accuracy_nonreg).lower(),
                    "clean_count_ok": str(clean_count_ok).lower(),
                    "validity_nonreg_dense_sparse_ok": str(valid_gate_ok).lower(),
                    "collapse_depth_gate": "not_scored_recheck_render_proxy_only",
                    "a_clean_candidate_dense_primary": str(a_clean).lower(),
                }
            )
    write_csv(CSV_PRUNE_SWEEP, rows)
    plot_prune_sweep(rows)
    print(json.dumps({"prune_sweep": rel(CSV_PRUNE_SWEEP), "rows": len(rows)}, ensure_ascii=False))


def plot_prune_sweep(rows: list[dict[str, Any]]) -> None:
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    dense = [r for r in rows if r["arm"] == "dense"]
    labels = [r["threshold"] for r in dense]
    x = np.arange(len(labels))
    cov = [num(r["mean_coverage_post_sor"]) or 0 for r in dense]
    rms = [num(r["median_ref_rms_m"]) or 0 for r in dense]
    anchor = [int(r["normal6_raw_anchor_count"]) for r in dense]
    fig, axes = plt.subplots(1, 3, figsize=(10.8, 3.5))
    axes[0].bar(x, cov, color="#457b9d")
    axes[1].bar(x, rms, color="#e76f51")
    axes[2].bar(x, anchor, color="#2a9d8f")
    axes[0].set_ylabel("mean coverage")
    axes[1].set_ylabel("median RMS (m)")
    axes[2].set_ylabel("normal6 raw anchor count")
    for ax in axes:
        ax.set_xticks(x)
        ax.set_xticklabels(labels, rotation=25, ha="right")
        ax.grid(axis="y", alpha=0.25)
    axes[0].set_title("dense threshold coverage")
    axes[1].set_title("dense threshold RMS")
    axes[2].set_title("guardrail anchor")
    fig.tight_layout()
    out = FIG_DIR / "prune_sweep_dense_gate.png"
    fig.savefig(out, dpi=180)
    plt.close(fig)

    arms = ARMS
    fig, ax = plt.subplots(figsize=(8.2, 3.8))
    width = 0.22
    for idx, arm in enumerate(arms):
        part = [r for r in rows if r["arm"] == arm]
        vals = [num(r["mean_coverage_post_sor"]) or 0 for r in part]
        ax.bar(x + (idx - 1) * width, vals, width=width, label=arm)
    ax.set_xticks(x)
    ax.set_xticklabels(labels)
    ax.set_ylabel("mean coverage post-SOR")
    ax.set_title("threshold x arm coverage")
    ax.legend()
    ax.grid(axis="y", alpha=0.25)
    fig.tight_layout()
    out = FIG_DIR / "prune_sweep_threshold_arm_coverage.png"
    fig.savefig(out, dpi=180)
    plt.close(fig)


def load_footprints(ids: list[str]) -> dict[str, dict[str, Any]]:
    wanted = {full_id(x) for x in ids}
    payload = json.loads(FOOTPRINTS_GEOJSON.read_text(encoding="utf-8"))
    out: dict[str, dict[str, Any]] = {}
    for feat in payload["features"]:
        bid = feat.get("properties", {}).get("building_id")
        if bid not in wanted:
            continue
        geom = feat["geometry"]
        rings = []
        if geom["type"] == "Polygon":
            rings = [np.asarray(geom["coordinates"][0], dtype=np.float64)]
        elif geom["type"] == "MultiPolygon":
            rings = [np.asarray(poly[0], dtype=np.float64) for poly in geom["coordinates"]]
        if not rings:
            continue
        xy = np.concatenate([r[:, :2] for r in rings], axis=0)
        out[bid] = {
            "rings": [r[:, :2] for r in rings],
            "paths": [MplPath(r[:, :2], closed=True) for r in rings],
            "bbox": (float(xy[:, 0].min()), float(xy[:, 1].min()), float(xy[:, 0].max()), float(xy[:, 1].max())),
            "area_m2": feat.get("properties", {}).get("area_m2", ""),
        }
    return out


def checkpoint_sets_for_roofcrop() -> list[tuple[str, str, Path]]:
    out = []
    for arm in ARMS:
        out.append(("s1", arm, REPO / "results/tum_transfer/e5_3b_s1/C001/runs" / f"gs_e5_C001_s1_{arm}_r1/ckpt/final.pt"))
        out.append(("corrected", arm, REPO / "results/tum_transfer/e5_corrected_s1/C001/runs" / f"gs_e5_C001_corrected_s1_{arm}_r1/ckpt/final.pt"))
        out.append(("preprune_keepall", arm, CKPT_ROOT / f"gs_e5_C001_corrected_s1_preprune_keepall_{arm}_r1/ckpt/final.pt"))
        out.append(("preprune_opa005", arm, CKPT_ROOT / f"gs_e5_C001_corrected_s1_preprune_opa005_{arm}_r1/ckpt/final.pt"))
    return out


def gaussian_roofcrop(_args: argparse.Namespace) -> None:
    import torch

    footprints = load_footprints(ROOFCROP_IDS)
    rows: list[dict[str, Any]] = []
    for condition, arm, ckpt in checkpoint_sets_for_roofcrop():
        if not ckpt.exists():
            append_issue("H2", "warn", "checkpoint missing for roofcrop stats", ckpt)
            continue
        payload = torch.load(ckpt, map_location="cpu", weights_only=False)
        state = payload["state_dict"]
        means = state["means"].detach().cpu().numpy().astype(np.float64) + SHIFT_UTM
        opa = torch.sigmoid(state["opacities_raw"].detach().cpu().float()).numpy()
        scales = np.exp(state["log_scales"].detach().cpu().numpy())
        inplane = np.maximum(scales[:, 0], scales[:, 1]) / np.maximum(np.minimum(scales[:, 0], scales[:, 1]), 1e-9)
        for bid, fp in footprints.items():
            x0, y0, x1, y1 = fp["bbox"]
            m = (means[:, 0] >= x0 - 2.0) & (means[:, 0] <= x1 + 2.0) & (means[:, 1] >= y0 - 2.0) & (means[:, 1] <= y1 + 2.0)
            if np.any(m):
                cand = means[m]
                inside = np.zeros(cand.shape[0], dtype=bool)
                for path in fp["paths"]:
                    inside |= path.contains_points(cand[:, :2])
                idx = np.where(m)[0][inside]
            else:
                idx = np.array([], dtype=np.int64)
            z = means[idx, 2] if idx.size else np.array([], dtype=float)
            op = opa[idx] if idx.size else np.array([], dtype=float)
            ar = inplane[idx] if idx.size else np.array([], dtype=float)
            rows.append(
                {
                    "condition": condition,
                    "arm": arm,
                    "building_id": bid,
                    "ckpt": rel(ckpt),
                    "n_gaussians_in_footprint": int(idx.size),
                    "z_p05": fmt(float(np.quantile(z, 0.05)) if z.size else None),
                    "z_p50": fmt(float(np.quantile(z, 0.50)) if z.size else None),
                    "z_p95": fmt(float(np.quantile(z, 0.95)) if z.size else None),
                    "z_std": fmt(float(np.std(z)) if z.size else None),
                    "opacity_p05": fmt(float(np.quantile(op, 0.05)) if op.size else None),
                    "opacity_p50": fmt(float(np.quantile(op, 0.50)) if op.size else None),
                    "opacity_p95": fmt(float(np.quantile(op, 0.95)) if op.size else None),
                    "opacity_lt_005_count": int((op < 0.005).sum()) if op.size else 0,
                    "opacity_lt_005_frac": fmt(float((op < 0.005).mean()) if op.size else None),
                    "opacity_lt_005_abs": int((op < 0.005).sum()) if op.size else 0,
                    "opacity_lt_005_ratio": fmt(float((op < 0.005).mean()) if op.size else None),
                    "opacity_lt_0050_count": int((op < 0.05).sum()) if op.size else 0,
                    "opacity_lt_0050_frac": fmt(float((op < 0.05).mean()) if op.size else None),
                    "opacity_lt_005_note": "ratio+count both reported",
                    "axis_ratio_gt10_count": int((ar > 10).sum()) if ar.size else 0,
                    "axis_ratio_gt10_frac": fmt(float((ar > 10).mean()) if ar.size else None),
                }
            )
    write_csv(CSV_GAUSSIAN_ROOFCROP, rows)
    plot_roofcrop(rows)
    print(json.dumps({"gaussian_roofcrop": rel(CSV_GAUSSIAN_ROOFCROP), "rows": len(rows)}, ensure_ascii=False))


def plot_roofcrop(rows: list[dict[str, Any]]) -> None:
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    for sid in ["4907202", "4908168", "4907184", "8568392"]:
        bid = full_id(sid)
        part = [r for r in rows if r["building_id"] == bid and r["arm"] == "dense"]
        if not part:
            continue
        labels = [r["condition"] for r in part]
        x = np.arange(len(labels))
        n = [int(r["n_gaussians_in_footprint"]) for r in part]
        zp50 = [num(r["z_p50"]) or 0 for r in part]
        op50 = [num(r["opacity_p50"]) or 0 for r in part]
        fig, axes = plt.subplots(1, 3, figsize=(10.5, 3.4))
        axes[0].bar(x, n, color="#577590")
        axes[1].bar(x, zp50, color="#f3722c")
        axes[2].bar(x, op50, color="#43aa8b")
        for ax in axes:
            ax.set_xticks(x)
            ax.set_xticklabels(labels, rotation=25, ha="right", fontsize=8)
            ax.grid(axis="y", alpha=0.25)
        axes[0].set_title("n in footprint")
        axes[1].set_title("z p50")
        axes[2].set_title("opacity p50")
        fig.suptitle(f"dense Gaussian roofcrop {sid}", fontsize=11)
        fig.tight_layout()
        out = FIG_DIR / f"gaussian_roofcrop_dense_{sid}.png"
        fig.savefig(out, dpi=180)
        plt.close(fig)


def val3dity_types(_args: argparse.Namespace) -> None:
    rows: list[dict[str, Any]] = []
    roots = [
        ("s1", REPO / "phases/p0-audit/runs/e5p_3b_s1_20260708_C001/base"),
        ("corrected", REPO / "phases/p0-audit/runs/e5p_corrected_s1_20260709_C001/base"),
        ("recheck", P0_RUN_DIR / "base"),
    ]
    for condition, root in roots:
        for arm in ARMS:
            pattern = f"*_{arm}_r1_run_1.csv"
            status_files = sorted((root / "status").glob(pattern))
            for status_file in status_files:
                run_name = status_file.name.removesuffix("_run_1.csv")
                for row in read_csv(status_file):
                    errors_text = row.get("val3dity_errors", "[]")
                    try:
                        errors = json.loads(errors_text)
                    except json.JSONDecodeError:
                        errors = []
                    codes = [str(err.get("code", "")) for err in errors if isinstance(err, dict)]
                    desc = [str(err.get("description", "")) for err in errors if isinstance(err, dict)]
                    rows.append(
                        {
                            "condition": condition,
                            "setting": "base",
                            "arm": arm,
                            "run_name": run_name,
                            "building_id": row.get("building_id", ""),
                            "has_lod22": row.get("has_lod22", ""),
                            "val3dity_valid": row.get("val3dity_valid", ""),
                            "status": row.get("status", ""),
                            "status_reason": row.get("reason", row.get("status_reason", "")),
                            "val3dity_error_codes": ";".join(codes),
                            "val3dity_error_descriptions": ";".join(desc),
                            "n_val3dity_errors": len(codes),
                        }
                    )
    write_csv(CSV_VAL3DITY_TYPES, rows)
    plot_val3dity_types(rows)
    print(json.dumps({"val3dity_types": rel(CSV_VAL3DITY_TYPES), "rows": len(rows)}, ensure_ascii=False))


def plot_val3dity_types(rows: list[dict[str, Any]]) -> None:
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    counts = Counter()
    for row in rows:
        key = (row["condition"], row["arm"], row["val3dity_error_codes"] or "valid_or_not_built")
        counts[key] += 1
    conditions = ["s1", "corrected", "recheck"]
    arms = ARMS
    fig, axes = plt.subplots(1, 3, figsize=(11.5, 3.8), sharey=True)
    for ax, arm in zip(axes, arms):
        vals = []
        labels = []
        for cond in conditions:
            invalid = sum(v for (c, a, code), v in counts.items() if c == cond and a == arm and code != "valid_or_not_built")
            valid = sum(v for (c, a, code), v in counts.items() if c == cond and a == arm and code == "valid_or_not_built")
            vals.append([valid, invalid])
            labels.append(cond)
        x = np.arange(len(labels))
        valid_vals = [v[0] for v in vals]
        invalid_vals = [v[1] for v in vals]
        ax.bar(x, valid_vals, color="#90be6d", label="valid/not-built")
        ax.bar(x, invalid_vals, bottom=valid_vals, color="#f94144", label="invalid")
        ax.set_xticks(x)
        ax.set_xticklabels(labels, rotation=20, ha="right")
        ax.set_title(arm)
        ax.grid(axis="y", alpha=0.25)
    axes[0].legend(fontsize=8)
    axes[0].set_ylabel("buildings")
    fig.tight_layout()
    out = FIG_DIR / "val3dity_type_breakdown.png"
    fig.savefig(out, dpi=180)
    plt.close(fig)


def make_model_from_state(state: dict[str, Any], device: Any) -> Any:
    import torch
    from src.stage2.model import GaussianModel2D

    model = GaussianModel2D.__new__(GaussianModel2D)
    torch.nn.Module.__init__(model)
    n_sh = int(state["sh0"].shape[1] + state["shN"].shape[1])
    sh_degree = int(round(math.sqrt(n_sh) - 1))
    model.sh_degree = sh_degree
    model.max_sh_degree = sh_degree
    model.active_sh_degree = sh_degree
    model.num_classes = int(state.get("sem_logits").shape[-1]) if "sem_logits" in state else 4
    for key in ["means", "quats", "log_scales", "opacities_raw", "sh0", "shN", "sem_logits"]:
        if key in state:
            setattr(model, key, torch.nn.Parameter(state[key].to(device).float(), requires_grad=False))
    model.eval()
    return model


def floater_render(args: argparse.Namespace) -> None:
    try:
        import torch
        from src.stage2.dataloader import ColmapDataset
        from src.stage2.renderer import render
    except Exception as exc:  # noqa: BLE001
        append_issue("Step4/5A", "warn", f"render imports failed: {type(exc).__name__}: {exc}")
        write_csv(CSV_FLOATER_RENDER, [{"status": "render_import_failed", "message": str(exc)}])
        return
    device = torch.device(args.device if args.device == "cpu" or torch.cuda.is_available() else "cpu")
    rows: list[dict[str, Any]] = []
    try:
        ds = ColmapDataset(root=str(REPO / DATA_ROOT), downscale=0.5, load_depth=True, load_normal=True, load_semantic=True)
    except Exception as exc:  # noqa: BLE001
        append_issue("Step4/5A", "warn", f"dataset load failed: {type(exc).__name__}: {exc}")
        write_csv(CSV_FLOATER_RENDER, [{"status": "dataset_load_failed", "message": str(exc)}])
        return
    view_indices = [0, 10, 30, 60]
    ckpts = [
        ("s1_dense", REPO / "results/tum_transfer/e5_3b_s1/C001/runs/gs_e5_C001_s1_dense_r1/ckpt/final.pt"),
        ("corrected_dense", REPO / "results/tum_transfer/e5_corrected_s1/C001/runs/gs_e5_C001_corrected_s1_dense_r1/ckpt/final.pt"),
        ("preprune_keepall_dense", CKPT_ROOT / "gs_e5_C001_corrected_s1_preprune_keepall_dense_r1/ckpt/final.pt"),
    ]
    for label, ckpt in ckpts:
        if not ckpt.exists():
            continue
        try:
            payload = torch.load(ckpt, map_location="cpu", weights_only=False)
            model = make_model_from_state(payload["state_dict"], device)
        except Exception as exc:  # noqa: BLE001
            append_issue("Step4", "warn", f"model load failed for {label}: {exc}", ckpt)
            continue
        for view_idx in view_indices:
            batch = ds[view_idx]
            with torch.no_grad():
                out = render(model, batch["w2c"].to(device), batch["K"].to(device), batch["width"], batch["height"], sh_degree=model.active_sh_degree, render_mode="RGB+ED")
            depth = out["depth"].detach().cpu().numpy()
            alpha = out["alpha"].detach().cpu().numpy()
            dist = out["distort"].detach().cpu().numpy()
            valid = np.isfinite(depth) & (depth > 0) & (alpha > 0.2)
            rows.append(
                {
                    "condition": label,
                    "view_idx": view_idx,
                    "image_name": getattr(ds.frames[view_idx], "name", ""),
                    "valid_pixel_frac_alpha02": fmt(float(valid.mean())),
                    "depth_p50": fmt(float(np.quantile(depth[valid], 0.50)) if np.any(valid) else None),
                    "depth_p95": fmt(float(np.quantile(depth[valid], 0.95)) if np.any(valid) else None),
                    "rend_dist_mean_alpha02": fmt(float(dist[valid].mean()) if np.any(valid) else None),
                    "rend_dist_p95_alpha02": fmt(float(np.quantile(dist[valid], 0.95)) if np.any(valid) else None),
                    "note": "render proxy; not the historical collapse-view metric",
                }
            )
    unit_rows = render_dist_scale_test(ds, device, args.device)
    rows.extend(unit_rows)
    write_csv(CSV_FLOATER_RENDER, rows)
    plot_floater_render(rows)
    print(json.dumps({"floater_render": rel(CSV_FLOATER_RENDER), "rows": len(rows)}, ensure_ascii=False))


def render_dist_scale_test(ds: Any, device: Any, device_name: str) -> list[dict[str, Any]]:
    try:
        import torch
        from src.stage2.renderer import render
    except Exception:
        return []
    ckpt = CKPT_ROOT / "gs_e5_C001_corrected_s1_preprune_keepall_dense_r1/ckpt/final.pt"
    if not ckpt.exists():
        return []
    payload = torch.load(ckpt, map_location="cpu", weights_only=False)
    batch = ds[10]
    rows = []
    variants = [
        ("original", 1.0, False),
        ("x2_centers_camera", 2.0, False),
        ("x2_centers_camera_scales", 2.0, True),
    ]
    for variant, scale, scale_scales in variants:
        state = {k: v.clone() if hasattr(v, "clone") else v for k, v in payload["state_dict"].items()}
        if scale != 1.0:
            state["means"] = state["means"] * scale
            if scale_scales:
                state["log_scales"] = state["log_scales"].clone()
                state["log_scales"][:, :2] = state["log_scales"][:, :2] + math.log(scale)
        model = make_model_from_state(state, device)
        w2c = batch["w2c"].clone()
        if scale != 1.0:
            w2c[:3, 3] = w2c[:3, 3] * scale
        with torch.no_grad():
            out = render(model, w2c.to(device), batch["K"].to(device), batch["width"], batch["height"], sh_degree=model.active_sh_degree, render_mode="RGB+ED")
        depth = out["depth"].detach().cpu().numpy()
        alpha = out["alpha"].detach().cpu().numpy()
        dist = out["distort"].detach().cpu().numpy()
        valid = np.isfinite(depth) & (depth > 0) & (alpha > 0.2)
        rows.append(
            {
                "condition": "rend_dist_unit_test",
                "view_idx": 10,
                "image_name": getattr(ds.frames[10], "name", ""),
                "scale_variant": variant,
                "scale_factor": scale,
                "scale_scales": str(scale_scales).lower(),
                "device": device_name,
                "valid_pixel_frac_alpha02": fmt(float(valid.mean())),
                "depth_p50": fmt(float(np.quantile(depth[valid], 0.50)) if np.any(valid) else None),
                "rend_dist_mean_alpha02": fmt(float(dist[valid].mean()) if np.any(valid) else None),
                "rend_dist_p50_alpha02": fmt(float(np.quantile(dist[valid], 0.50)) if np.any(valid) else None),
                "rend_dist_p95_alpha02": fmt(float(np.quantile(dist[valid], 0.95)) if np.any(valid) else None),
                "note": "x2 camera+Gaussian scale test for rend_dist units",
            }
        )
    return rows


def plot_floater_render(rows: list[dict[str, Any]]) -> None:
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    part = [r for r in rows if r.get("condition") in {"s1_dense", "corrected_dense", "preprune_keepall_dense"}]
    if part:
        labels = sorted({r["condition"] for r in part})
        vals = []
        for label in labels:
            depths = [num(r.get("depth_p95")) for r in part if r["condition"] == label]
            vals.append(mean([v for v in depths if v is not None]) or 0)
        fig, ax = plt.subplots(figsize=(6.4, 3.5))
        ax.bar(labels, vals, color="#577590")
        ax.set_ylabel("mean p95 render depth (m)")
        ax.set_title("render proxy for collapse-depth check")
        ax.grid(axis="y", alpha=0.25)
        fig.tight_layout()
        out = FIG_DIR / "floater_render_depth_proxy.png"
        fig.savefig(out, dpi=180)
        plt.close(fig)
    unit = [r for r in rows if r.get("condition") == "rend_dist_unit_test"]
    if unit:
        labels = [r["scale_variant"] for r in unit]
        vals = [num(r.get("rend_dist_mean_alpha02")) or 0 for r in unit]
        fig, ax = plt.subplots(figsize=(6.4, 3.5))
        ax.bar(labels, vals, color="#f9844a")
        ax.set_ylabel("mean rend_dist")
        ax.set_title("rend_dist x2 scale test")
        ax.tick_params(axis="x", rotation=20)
        ax.grid(axis="y", alpha=0.25)
        fig.tight_layout()
        out = FIG_DIR / "rend_dist_x2_scale_test.png"
        fig.savefig(out, dpi=180)
        plt.close(fig)


def mono_normal_stats(_args: argparse.Namespace) -> None:
    rows = []
    for sid in TEXTURELESS_OBS + DEFECT_POLLUTED + DEFECT_THIN + ["4907184", "4907198"]:
        rows.append(
            {
                "building_id": full_id(sid),
                "status": "not_run",
                "reason": "no local Omnidata/DSINE/mono-normal runtime or model weights found in repo",
                "fallback_used": "none",
                "note": "COLMAP PatchMatch normal maps exist but are texture-dependent MVS normals, not the requested mono-normal prior",
            }
        )
    write_csv(CSV_MONO_NORMAL, rows)
    append_issue("Step5-B", "warn", "mono-normal precheck not run; local 2D foundation normal runtime absent")
    print(json.dumps({"mono_normal_stats": rel(CSV_MONO_NORMAL), "rows": len(rows)}, ensure_ascii=False))


def config_diff(_args: argparse.Namespace) -> None:
    rows: list[dict[str, Any]] = []
    for arm in ARMS:
        s1_eff = REPO / "results/tum_transfer/e5_3b_s1/C001/runs" / f"gs_e5_C001_s1_{arm}_r1/effective_config.json"
        corr_eff = REPO / "results/tum_transfer/e5_corrected_s1/C001/runs" / f"gs_e5_C001_corrected_s1_{arm}_r1/effective_config.json"
        pre_eff = CKPT_ROOT / PREPRUNE_RUN[arm] / "effective_config.json"
        payloads = {}
        for label, path in [("s1", s1_eff), ("corrected", corr_eff), ("preprune_fallback", pre_eff)]:
            payloads[label] = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        keys = sorted(set().union(*(p.keys() for p in payloads.values())))
        for key in keys:
            vals = {label: payloads[label].get(key, "") for label in payloads}
            changed = len({json.dumps(v, sort_keys=True, ensure_ascii=False) for v in vals.values()}) > 1
            if changed:
                rows.append({"arm": arm, "key": key, **{f"{label}_value": vals[label] for label in vals}})
    write_csv(CSV_CONFIG_DIFF, rows)
    print(json.dumps({"config_diff": rel(CSV_CONFIG_DIFF), "rows": len(rows)}, ensure_ascii=False))


def best_threshold_for_voxel02() -> str:
    rows = read_csv(CSV_PRUNE_SWEEP)
    dense = [r for r in rows if r.get("arm") == "dense"]
    aclean = [r for r in dense if tf(r.get("a_clean_candidate_dense_primary"))]
    if aclean:
        return aclean[0]["threshold"]
    # fallback: choose best guardrail count, then lowest median RMS, then lower threshold.
    order = {k: i for i, (k, _v) in enumerate(THRESHOLDS)}
    def key(row: dict[str, str]) -> tuple[int, float, int]:
        return (-int(row.get("normal6_raw_anchor_count") or 0), num(row.get("median_ref_rms_m")) or 1e9, order.get(row["threshold"], 99))
    if dense:
        return sorted(dense, key=key)[0]["threshold"]
    return "keepall"


def copy_snapshots() -> None:
    SNAP_DIR.mkdir(parents=True, exist_ok=True)
    for path in [
        REPORT_PATH,
        CSV_SNAPSHOT_INVENTORY,
        CSV_CKPT_THRESHOLDS,
        CSV_PRUNE_SWEEP,
        CSV_PREPRUNE_COVERAGE,
        CSV_GAUSSIAN_ROOFCROP,
        CSV_VAL3DITY_TYPES,
        CSV_FLOATER_RENDER,
        CSV_MONO_NORMAL,
        CSV_ISSUES,
        CSV_CONFIG_DIFF,
        REPO / "docs/experiments/joint-optimization/e5_c001_corrected_s1_recheck/tables/e5_c001_corrected_s1_recheck_building_8way.csv",
        REPO / "docs/experiments/joint-optimization/e5_c001_corrected_s1_recheck/tables/e5_c001_corrected_s1_recheck_summary.csv",
        REPO / "docs/experiments/joint-optimization/e5_c001_corrected_s1_recheck/tables/e5_c001_corrected_s1_recheck_filter_contrib.csv",
        P2_RUN_DIR / "train_fingerprints.csv",
        P2_RUN_DIR / "readout_fingerprints.csv",
        P2_RUN_DIR / "versions.txt",
    ]:
        if path.exists() and path.is_file():
            (SNAP_DIR / path.name).write_bytes(path.read_bytes())


def md_table(rows: list[dict[str, Any]], columns: list[str], max_rows: int | None = None) -> str:
    use = rows if max_rows is None else rows[:max_rows]
    out = ["| " + " | ".join(columns) + " |", "|" + "|".join("---" for _ in columns) + "|"]
    for row in use:
        out.append("| " + " | ".join(str(row.get(col, "")) for col in columns) + " |")
    if max_rows is not None and len(rows) > max_rows:
        out.append("| ... | " + f"{len(rows) - max_rows} rows omitted |" + " | ".join("" for _ in columns[2:]) + " |")
    return "\n".join(out)


def build_report(_args: argparse.Namespace) -> None:
    prune = read_csv(CSV_PRUNE_SWEEP)
    ckpts = read_csv(CSV_CKPT_THRESHOLDS)
    roof = read_csv(CSV_GAUSSIAN_ROOFCROP)
    val = read_csv(CSV_VAL3DITY_TYPES)
    floater = read_csv(CSV_FLOATER_RENDER)
    mono = read_csv(CSV_MONO_NORMAL)
    issues = read_csv(CSV_ISSUES)
    metrics = read_csv(REPO / "docs/experiments/joint-optimization/e5_c001_corrected_s1_recheck/tables/e5_c001_corrected_s1_recheck_building_8way.csv")
    coverage = read_csv(CSV_PREPRUNE_COVERAGE)
    best = best_threshold_for_voxel02() if CSV_PRUNE_SWEEP.exists() else ""
    aclean = [r for r in prune if tf(r.get("a_clean_candidate_dense_primary"))]
    dense_rows = [r for r in prune if r.get("arm") == "dense"]
    mid_rows: list[dict[str, Any]] = []
    for rn in MID20K_RUNS:
        sm = source_metrics(metrics, "base", rn)
        cov = coverage_summary(coverage, "base", rn)
        mid_rows.append(
            {
                "arm": rn.split("_")[-2],
                "run_name": rn,
                "has_lod22": sm["has_lod22"],
                "valid_assembled": sm["valid_assembled"],
                "median_ref_rms_m": fmt(sm["median_ref_rms_m"]),
                "mean_coverage_post_sor": fmt(cov.get("mean_coverage_sor_post_clean")),
            }
        )
    voxel_rows = [r for r in metrics if r.get("setting") == "voxel02"]
    voxel_summary = source_metrics(voxel_rows, "voxel02", f"gs_e5_C001_corrected_s1_preprune_{best}_dense_r1") if best else {}
    train_fp = read_csv(P2_RUN_DIR / "train_fingerprints.csv")
    issue_md = md_table(issues, ["part", "severity", "message", "path"], 12) if issues else "| part | severity | message | path |\n|---|---|---|---|"
    lines = [
        "# E5 C001 corrected-S1 재점검",
        "",
        "> 관찰 자료. 학습 0 원칙을 따랐고, 예외는 Step 0에서 허용된 `final_prune_opa=0` 폴백 3 arm뿐이다. 정본 S0/S1/corrected-S1은 수정하지 않았고 판정 0이다.",
        "",
        "## Step 0 · 스냅샷 재고",
        "",
        "- corrected-S1 기존 run에는 `final.pt`, `step_010000.pt`, `step_020000.pt`만 있었고 final prune 직전 상태는 없었다.",
        "- 그래서 발주문 폴백을 사용했다: corrected-S1과 동일 config/seed(2001), 변경은 `final_prune_opa=0` 및 `ckpt_every=5000`뿐.",
        f"- snapshot inventory: `{rel(CSV_SNAPSHOT_INVENTORY)}`.",
        "",
        "## Step 1 · 문턱 스윕",
        "",
        f"- thresholded ckpt: `{rel(CSV_CKPT_THRESHOLDS)}`.",
        f"- sweep table: `{rel(CSV_PRUNE_SWEEP)}`.",
        f"- best threshold for voxel02 follow-up by pre-registered fallback ranking: `{best}`.",
        f"- A-clean 후보 존재: `{bool(aclean)}`. 단 collapse-view depth는 역사적 기준과 같은 방식으로 재현하지 못해 gate 밖 보조 proxy로 분리했다.",
        f"- 짝 그림: `{rel(FIG_DIR / 'prune_sweep_dense_gate.png')}`, `{rel(FIG_DIR / 'prune_sweep_threshold_arm_coverage.png')}`.",
        "",
        md_table(
            dense_rows,
            [
                "threshold",
                "has_lod22",
                "valid_assembled",
                "median_ref_rms_m",
                "mean_coverage_post_sor",
                "normal6_raw_anchor_count",
                "normal6_median_delta_vs_s1_m",
                "a_clean_candidate_dense_primary",
            ],
        ),
        "",
        "### Step 1-B · 20k 중간 스냅샷",
        "",
        "최종 prune 전후만이 아니라 학습 중간에도 표면이 있었는지 보기 위해 20k 스냅샷을 같은 base readout으로 처리했다.",
        "",
        md_table(
            mid_rows,
            ["arm", "has_lod22", "valid_assembled", "median_ref_rms_m", "mean_coverage_post_sor", "run_name"],
        ),
        "",
        "## Step 2 · H2 물질 추적",
        "",
        f"- Gaussian roofcrop CSV: `{rel(CSV_GAUSSIAN_ROOFCROP)}`.",
        f"- 짝 그림: `{rel(FIG_DIR / 'gaussian_roofcrop_dense_4907202.png')}`, `{rel(FIG_DIR / 'gaussian_roofcrop_dense_4908168.png')}`, `{rel(FIG_DIR / 'gaussian_roofcrop_dense_8568392.png')}`.",
        "",
        md_table(
            [r for r in roof if r.get("arm") == "dense" and short_id(r.get("building_id", "")) in {"4907202", "4908168", "4907184", "8568392"}],
            ["condition", "building_id", "n_gaussians_in_footprint", "z_p50", "z_std", "opacity_p50", "opacity_lt_005_abs", "opacity_lt_0050_count", "axis_ratio_gt10_count"],
            24,
        ),
        "",
        "## Step 3 · H3 val3dity 유형",
        "",
        f"- val3dity/status type CSV: `{rel(CSV_VAL3DITY_TYPES)}`.",
        f"- 짝 그림: `{rel(FIG_DIR / 'val3dity_type_breakdown.png')}`.",
        "",
        md_table(
            [r for r in val if r.get("condition") == "recheck" and r.get("arm") == "acmp" and r.get("building_id") == "DEBY_LOD2_4907184"][:4],
            ["condition", "arm", "run_name", "building_id", "has_lod22", "val3dity_valid", "status_reason", "val3dity_error_codes"],
        ),
        "",
        "## Step 4 · 결손 메움",
        "",
        f"- render/depth proxy CSV: `{rel(CSV_FLOATER_RENDER)}`.",
        f"- 짝 그림: `{rel(FIG_DIR / 'floater_render_depth_proxy.png')}`, `{rel(FIG_DIR / 'rend_dist_x2_scale_test.png')}`.",
        "- 주의: 이 값은 검수 문서의 S0 9~13 m / S1 20~44 m collapse-view metric을 동일 방식으로 재현한 것이 아니라, 같은 스크립트에서 새로 뽑은 render proxy다.",
        "",
        md_table(
            [r for r in floater if r.get("condition") in {"s1_dense", "corrected_dense", "preprune_keepall_dense", "rend_dist_unit_test"}],
            ["condition", "view_idx", "scale_variant", "depth_p50", "depth_p95", "rend_dist_mean_alpha02", "note"],
            20,
        ),
        "",
        "## Step 5 · 사다리 선행 재료",
        "",
        f"- mono-normal stats CSV: `{rel(CSV_MONO_NORMAL)}`.",
        "- 로컬 repo에는 Omnidata/DSINE 실행 경로와 model weight가 없어 Step 5-B는 실행하지 않았다. COLMAP PatchMatch normal은 존재하지만 mono-normal이 아니므로 대체하지 않았다.",
        md_table(mono[:6], ["building_id", "status", "reason", "note"]),
        "",
        "## voxel02 천장 보조",
        "",
        f"- voxel02은 best threshold `{best}` dense arm에만 추가 실행했다.",
        f"- dense voxel02 has_lod22={voxel_summary.get('has_lod22', '')}, valid_assembled={voxel_summary.get('valid_assembled', '')}, median RMS={fmt(voxel_summary.get('median_ref_rms_m'))}.",
        "",
        "## 이슈·지문",
        "",
        issue_md,
        "",
        md_table(train_fp, ["arm", "gpu_device", "elapsed_min", "seed", "final_prune_opa", "ckpt_sha256"], 3),
        "",
        f"- config diff: `{rel(CSV_CONFIG_DIFF)}`.",
        f"- train fingerprints: `{rel(P2_RUN_DIR / 'train_fingerprints.csv')}`.",
        f"- readout fingerprints: `{rel(P2_RUN_DIR / 'readout_fingerprints.csv')}`.",
        f"- versions: `{rel(P2_RUN_DIR / 'versions.txt')}`.",
        f"- snapshots: `{rel(SNAP_DIR)}`.",
        "- 재확인: 학습 0 원칙(예외=Step 0 폴백뿐), 정본 미변경, 판정 0.",
        "",
    ]
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")
    copy_snapshots()
    print(json.dumps({"report": rel(REPORT_PATH)}, ensure_ascii=False))


def versions(_args: argparse.Namespace) -> None:
    P2_RUN_DIR.mkdir(parents=True, exist_ok=True)
    lines = [
        f"run_id: {RUN_ID}",
        f"timestamp_utc: {datetime.now(timezone.utc).isoformat()}",
        f"git_head: {run_text(['git', 'rev-parse', 'HEAD'])}",
        f"git_branch: {run_text(['git', 'branch', '--show-current'])}",
        "canonical_changed: no",
        "training: zero principle; exception is final_prune_opa=0 fallback only",
        "verdict: none",
        f"report: {rel(REPORT_PATH)}",
        f"docs_issues_exists: {(REPO / 'phases/p2-gsjso/docs/issues.md').exists()}",
        f"train_fingerprints: {rel(P2_RUN_DIR / 'train_fingerprints.csv')}",
        f"readout_fingerprints: {rel(P2_RUN_DIR / 'readout_fingerprints.csv')}",
    ]
    (P2_RUN_DIR / "versions.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"versions": rel(P2_RUN_DIR / "versions.txt")}, ensure_ascii=False))


def build_parser() -> argparse.ArgumentParser:
    configure()
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
    sub.add_parser("inventory-snapshots")
    sub.add_parser("make-threshold-ckpts")
    sub.add_parser("fingerprint-training")
    sub.add_parser("build-prune-sweep")
    sub.add_parser("gaussian-roofcrop")
    sub.add_parser("val3dity-types")
    fr = sub.add_parser("floater-render")
    fr.add_argument("--device", default="cuda")
    sub.add_parser("mono-normal-stats")
    sub.add_parser("config-diff")
    sub.add_parser("report")
    sub.add_parser("versions")
    return parser


def main() -> None:
    os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib")
    args = build_parser().parse_args()
    configure()
    if args.cmd in {"readout", "all"}:
        s1.ab.run_readout(args)
    if args.cmd in {"assemble", "all"}:
        s1.ab.run_assemble(args)
    if args.cmd in {"evaluate", "all"}:
        evaluate_or_container(args)
    if args.cmd == "inventory-snapshots":
        inventory_snapshots(args)
    elif args.cmd == "make-threshold-ckpts":
        make_threshold_ckpts(args)
    elif args.cmd == "fingerprint-training":
        train_fingerprints(args)
    elif args.cmd == "build-prune-sweep":
        build_prune_sweep(args)
    elif args.cmd == "gaussian-roofcrop":
        gaussian_roofcrop(args)
    elif args.cmd == "val3dity-types":
        val3dity_types(args)
    elif args.cmd == "floater-render":
        floater_render(args)
    elif args.cmd == "mono-normal-stats":
        mono_normal_stats(args)
    elif args.cmd == "config-diff":
        config_diff(args)
    elif args.cmd == "report":
        build_report(args)
    elif args.cmd == "versions":
        versions(args)


if __name__ == "__main__":
    main()
