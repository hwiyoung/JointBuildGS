#!/usr/bin/env python3
"""E5 C001 ③a readout re-run ablation.

Runs readout-only ablations over the existing six C001 checkpoints, then reruns
the unchanged GS-semantic LAS prep, Roofer, val3dity, and reference matching.
No GS training, loss, densification, or canonical readout file is changed.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import shutil
import subprocess
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from e5_baseline_tools import classify_buildings, combine_cityjsonseq, parse_roofer_features, write_status_csv
from e5_pilot_gate_tools import (
    C001_IDS,
    C001_SHORT_IDS,
    DEV_IMAGE,
    FOOTPRINTS_GEOJSON,
    FOOTPRINTS_GPKG_CT,
    P0_COMPOSE,
    P0_RUNS,
    TOOLS_RUN,
    filtered_cityjsonseq_files,
    footprint_bboxes,
    patch_prep_no_las,
    run_names,
    sha256_file,
)


REPO = Path(__file__).resolve().parents[3]
RUN_ID = "20260708_e5_c001_readout_ablation"
P2_RUN_DIR = REPO / "phases/p2-gsjso/runs" / RUN_ID
P0_RUN_ID = "e5p_readout_ablation_20260708_C001"
P0_RUN_DIR = P0_RUNS / P0_RUN_ID
RESULTS_ROOT = REPO / "results/tum_transfer/e5_pilot/C001/readout_ablation"
CKPT_ROOT = REPO / "results/tum_transfer/e5_pilot/C001/runs"
TRAIN_RUN_DIR = REPO / "phases/p2-gsjso/runs/e5p_train_20260707_C001"
CANON_GATE_DIR = REPO / "phases/p0-audit/runs/e5p_gate_20260707_C001"
DATA_ROOT = "results/tum_transfer/e5_pilot/C001/data_geoidfix_C001_buf20"
TORCH_EXTENSIONS = "results/tum_transfer/e5_pilot/C001/torch_extensions"
FIG_DIR = REPO / "docs/figs/e5_c001_readout_ablation"
REPORT_PATH = REPO / "docs/experiments/e5_c001_readout_ablation/reports/W_E5_C001_③a_readout재실행.md"
COVERAGE_CSV = REPO / "docs/experiments/e5_c001_readout_ablation/tables/e5_c001_readout_ablation_coverage.csv"
FILTER_CSV = REPO / "docs/experiments/e5_c001_readout_ablation/tables/e5_c001_readout_ablation_filter_contrib.csv"
METRICS_CSV = REPO / "docs/experiments/e5_c001_readout_ablation/tables/e5_c001_readout_ablation_metrics.csv"
SUMMARY_CSV = REPO / "docs/experiments/e5_c001_readout_ablation/tables/e5_c001_readout_ablation_summary.csv"
TRADEOFF_CSV = REPO / "docs/experiments/e5_c001_readout_ablation/tables/e5_c001_readout_ablation_tradeoff.csv"
CASE_CSV = REPO / "docs/experiments/e5_c001_readout_ablation/tables/e5_c001_readout_ablation_representative_buildings.csv"
INVENTORY_CSV = REPO / "docs/experiments/e5_c001_readout_ablation/tables/e5_c001_readout_ablation_inventory.csv"
ISSUES_CSV = REPO / "docs/experiments/e5_c001_readout_ablation/tables/e5_c001_readout_ablation_issues.csv"
BASELINE_METRICS = REPO / "docs/experiments/e5_c001_8way/tables/e5_c001_8way_metrics.csv"
RENDER_COVERAGE = REPO / "docs/experiments/e5_c001_render/tables/e5_c001_render_readout_coverage.csv"
Z_SHIFT_TO_REF_M = -45.7
eight = None


@dataclass(frozen=True)
class Setting:
    key: str
    purpose: str
    min_obs: int
    voxel: float
    alpha: float = 0.5
    sor: str = "on"
    sor_std: float = 2.0

    @property
    def readout_label(self) -> str:
        sor_part = "SORoff" if self.sor == "off" else f"SORstd{self.sor_std:g}"
        return f"readout_ablation({self.key}; minobs{self.min_obs}; voxel{self.voxel:g}; alpha{self.alpha:g}; {sor_part})"


SETTINGS = [
    Setting("base", "정본 기준선 재현", min_obs=3, voxel=0.05, sor="on", sor_std=2.0),
    Setting("minobs2", "minobs 3->2 관측 게이트 완화", min_obs=2, voxel=0.05, sor="on", sor_std=2.0),
    Setting("minobs1", "minobs 3->1 게이트 최대 완화", min_obs=1, voxel=0.05, sor="on", sor_std=2.0),
    Setting("sor_weak", "SOR std 비율 완화", min_obs=3, voxel=0.05, sor="on", sor_std=4.0),
    Setting("sor_off", "SOR 생략", min_obs=3, voxel=0.05, sor="off", sor_std=2.0),
    Setting("voxel03", "voxel 0.05->0.03 해상도 기여", min_obs=3, voxel=0.03, sor="on", sor_std=2.0),
    Setting("voxel02", "voxel 0.05->0.02 해상도 기여(강)", min_obs=3, voxel=0.02, sor="on", sor_std=2.0),
    Setting("relaxed", "minobs1 + SOR off + voxel0.03 완화 조합", min_obs=1, voxel=0.03, sor="off", sor_std=2.0),
]


def rel(path: Path | str) -> str:
    p = Path(path)
    for root in (REPO, Path("/workspace/JointBuildGS")):
        try:
            return str(p.relative_to(root))
        except ValueError:
            pass
    text = str(p)
    prefix = "/workspace/JointBuildGS/"
    if text.startswith(prefix):
        return text[len(prefix) :]
    return text


def capture(cmd: list[str]) -> str:
    try:
        proc = subprocess.run(cmd, cwd=REPO, text=True, capture_output=True, check=False)
    except FileNotFoundError as exc:
        return f"not_available:{exc.filename}"
    return ((proc.stdout or "") + (proc.stderr or "")).strip()


def load_eight_module():
    global eight
    if eight is None:
        import e5_c001_8way as eight_mod

        eight = eight_mod
    return eight


def run(cmd: list[str], log_path: Path | None = None, check: bool = True, quiet: bool = True) -> subprocess.CompletedProcess[str]:
    if log_path is not None:
        log_path.parent.mkdir(parents=True, exist_ok=True)
    print("+ " + " ".join(cmd[:8]) + (" ..." if len(cmd) > 8 else ""), flush=True)
    proc = subprocess.run(cmd, cwd=REPO, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if log_path is not None:
        log_path.write_text("+ " + " ".join(cmd) + "\n" + (proc.stdout or ""), encoding="utf-8")
    if (not quiet) or (check and proc.returncode != 0):
        print(proc.stdout or "", end="", flush=True)
    if check:
        proc.check_returncode()
    return proc


def read_csv(path: Path) -> list[dict[str, str]]:
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
            fh.write("")
            return
        writer = csv.DictWriter(fh, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def setting_map(selected: list[str] | None = None) -> list[Setting]:
    if not selected:
        return SETTINGS
    lookup = {s.key: s for s in SETTINGS}
    missing = sorted(set(selected) - set(lookup))
    if missing:
        raise RuntimeError(f"unknown settings: {missing}")
    return [lookup[key] for key in selected]


def selected_run_names(args: argparse.Namespace) -> list[str]:
    names = run_names()
    selected = getattr(args, "runs", None)
    if not selected:
        return names
    missing = sorted(set(selected) - set(names))
    if missing:
        raise RuntimeError(f"unknown run names: {missing}")
    selected_set = set(selected)
    return [name for name in names if name in selected_set]


def dev_docker_base(args: argparse.Namespace) -> list[str]:
    cmd = [
        "docker",
        "run",
        "--rm",
        "--user",
        f"{os.getuid()}:{os.getgid()}",
        "--gpus",
        "all",
        "-e",
        "HOME=/tmp",
        "-e",
        f"TORCH_EXTENSIONS_DIR=/workspace/JointBuildGS/{args.torch_extensions}",
        "-v",
        f"{REPO}:/workspace/JointBuildGS",
        "-w",
        "/workspace/JointBuildGS",
    ]
    if args.gpu:
        cmd.extend(["-e", f"CUDA_VISIBLE_DEVICES={args.gpu}"])
    cmd.append(DEV_IMAGE)
    return cmd


def readout_paths(setting: Setting, run_name: str) -> dict[str, Path]:
    root = RESULTS_ROOT / setting.key / run_name
    return {
        "npz": root / "tsdf_gssem.npz",
        "coverage": root / "stage_coverage.csv",
        "metrics": root / "readout_metrics.json",
        "log": root / "readout.log",
    }


def run_readout(args: argparse.Namespace) -> None:
    rows: list[dict[str, Any]] = []
    for setting in setting_map(args.settings):
        for name in selected_run_names(args):
            paths = readout_paths(setting, name)
            if paths["npz"].exists() and paths["coverage"].exists() and not args.force:
                print(json.dumps({"stage": "readout", "setting": setting.key, "run_name": name, "status": "skip_existing"}, ensure_ascii=False), flush=True)
            else:
                ckpt = CKPT_ROOT / name / "ckpt/final.pt"
                if not ckpt.exists():
                    raise FileNotFoundError(ckpt)
                cmd = dev_docker_base(args) + [
                    "python",
                    "phases/p2-gsjso/scripts/e5_c001_readout_extract_ablation.py",
                    "--ckpt",
                    rel(ckpt),
                    "--out",
                    rel(paths["npz"]),
                    "--data-root",
                    args.data_root,
                    "--geojson",
                    rel(FOOTPRINTS_GEOJSON),
                    "--buffer",
                    str(args.buffer_m),
                    "--min-obs",
                    str(setting.min_obs),
                    "--voxel",
                    str(setting.voxel),
                    "--alpha",
                    str(setting.alpha),
                    "--sor",
                    setting.sor,
                    "--sor-std",
                    str(setting.sor_std),
                    "--coverage-csv",
                    rel(paths["coverage"]),
                    "--metrics-json",
                    rel(paths["metrics"]),
                    "--targets",
                    *C001_SHORT_IDS,
                ]
                run(cmd, log_path=paths["log"], check=True, quiet=True)
                print(json.dumps({"stage": "readout", "setting": setting.key, "run_name": name, "status": "done"}, ensure_ascii=False), flush=True)
            rows.append(readout_fingerprint(setting, name, paths))
    write_csv(P2_RUN_DIR / "readout_fingerprints.csv", rows)


def readout_fingerprint(setting: Setting, run_name: str, paths: dict[str, Path]) -> dict[str, Any]:
    metrics = {}
    if paths["metrics"].exists():
        metrics = json.loads(paths["metrics"].read_text(encoding="utf-8"))
    return {
        "setting": setting.key,
        "run_name": run_name,
        "arm": run_name.split("_")[-2],
        "replicate": run_name.split("_")[-1],
        "tsdf_npz": rel(paths["npz"]),
        "tsdf_sha256": sha256_file(paths["npz"]) if paths["npz"].exists() else "missing",
        "coverage_csv": rel(paths["coverage"]),
        "metrics_json": rel(paths["metrics"]),
        "log": rel(paths["log"]),
        "min_obs": setting.min_obs,
        "voxel": setting.voxel,
        "alpha": setting.alpha,
        "sor": setting.sor,
        "sor_std": setting.sor_std,
        "surf_backproj": metrics.get("surf_backproj", ""),
        "fused_all": metrics.get("fused_all", ""),
        "minobs_kept": metrics.get("minobs_kept", ""),
        "sor_kept": metrics.get("sor_kept", ""),
        "readout": setting.readout_label,
    }


def run_assemble(args: argparse.Namespace) -> None:
    bboxes = footprint_bboxes()
    settings = setting_map(args.settings)
    names = selected_run_names(args)
    all_status_rows: list[dict[str, Any]] = []
    prep_metric_rows: list[dict[str, Any]] = []
    issues: list[dict[str, Any]] = []
    for setting in settings:
        gate_dir = P0_RUN_DIR / setting.key
        for name in names:
            npz = readout_paths(setting, name)["npz"]
            if not npz.exists():
                raise FileNotFoundError(npz)
            rep_name = "run_1"
            status_csv = gate_dir / "status" / f"{name}_{rep_name}.csv"
            cityjson = gate_dir / "cityjson" / f"{name}_{rep_name}.city.json"
            if status_csv.exists() and cityjson.exists() and not args.force:
                print(json.dumps({"stage": "assemble", "setting": setting.key, "run_name": name, "status": "skip_existing"}, ensure_ascii=False), flush=True)
                all_status_rows.extend(existing_status_rows(setting, name, status_csv))
                continue
            label = f"GS-{name.split('_')[-2]}-{name.split('_')[-1]}-{setting.key}"
            outdir_host = gate_dir / "roofer" / name / rep_name
            outdir_ct = f"/workspace/JointBuildGS/{rel(outdir_host)}"
            outdir_roofer = f"/workspace/runs/{P0_RUN_ID}/{setting.key}/roofer/{name}/{rep_name}"
            outdir_host.mkdir(parents=True, exist_ok=True)
            logs = gate_dir / "logs" / name / rep_name
            prep_metrics_by_bid: dict[str, dict[str, Any] | None] = {}
            for bid in C001_IDS:
                prep_log = logs / f"{bid}_prep.log"
                prep_cmd = TOOLS_RUN + [
                    "python3",
                    "phases/p2-gsjso/scripts/_mob_prep_las_gssem.py",
                    "--tsdf",
                    f"/workspace/JointBuildGS/{rel(npz)}",
                    "--bid",
                    bid,
                    "--geojson",
                    "/workspace/JointBuildGS/results/tum_transfer/analysis/footprints_aoi.geojson",
                    "--buffer",
                    str(args.buffer_m),
                    "--target-density",
                    "0.0",
                    "--outdir",
                    outdir_ct,
                    "--tag",
                    rep_name,
                ]
                prep_proc = run(prep_cmd, log_path=prep_log, check=False, quiet=True)
                metrics_path = outdir_host / f"{bid}_{rep_name}_metrics.json"
                metrics = json.loads(metrics_path.read_text(encoding="utf-8")) if metrics_path.exists() else None
                prep_metrics_by_bid[bid] = metrics
                prep_metric_rows.append(
                    {
                        "setting": setting.key,
                        "run_name": name,
                        "roofer_repeat": rep_name,
                        "building_id": bid,
                        "prep_returncode": prep_proc.returncode,
                        "n_clip": "" if metrics is None else metrics.get("n_clip", ""),
                        "n_used": "" if metrics is None else metrics.get("n_used", ""),
                        "n_building": "" if metrics is None else metrics.get("n_building", ""),
                        "n_building_in_fp": "" if metrics is None else metrics.get("n_building_in_fp", ""),
                        "classified_las": "" if metrics is None else metrics.get("classified_las", ""),
                    }
                )
                clf = None if metrics is None else metrics.get("classified_las")
                if prep_proc.returncode != 0:
                    issues.append({"setting": setting.key, "run_name": name, "building_id": bid, "stage": "prep", "returncode": prep_proc.returncode, "log": rel(prep_log)})
                if not clf:
                    continue
                clf_roofer = str(clf).replace("/workspace/JointBuildGS/phases/p0-audit/runs", "/workspace/runs")
                x0, y0, x1, y1 = bboxes[bid]
                roofer_cmd = P0_COMPOSE + [
                    "run",
                    "-T",
                    "--rm",
                    "roofer",
                    "--id-attribute",
                    "building_id",
                    "--box",
                    f"{x0:.3f}",
                    f"{y0:.3f}",
                    f"{x1:.3f}",
                    f"{y1:.3f}",
                    clf_roofer,
                    FOOTPRINTS_GPKG_CT,
                    f"{outdir_roofer}/roofer_{bid}_{rep_name}",
                ]
                roofer_proc = run(roofer_cmd, log_path=logs / f"{bid}_roofer.log", check=False, quiet=True)
                if roofer_proc.returncode != 0:
                    issues.append({"setting": setting.key, "run_name": name, "building_id": bid, "stage": "roofer", "returncode": roofer_proc.returncode, "log": rel(logs / f"{bid}_roofer.log")})

            jsonl_files = filtered_cityjsonseq_files(sorted(outdir_host.glob("roofer_*/*.city.jsonl")), gate_dir, name, rep_name)
            val_report = gate_dir / "val3dity" / f"{name}_{rep_name}_val3dity.json"
            val_by_id: dict[str, dict[str, Any]] = {}
            roofer_by_id: dict[str, dict[str, Any]] = {}
            if jsonl_files:
                combine_cityjsonseq(jsonl_files, cityjson)
                cj_ct = f"/workspace/runs/{P0_RUN_ID}/{setting.key}/cityjson/{cityjson.name}"
                rep_ct = f"/workspace/runs/{P0_RUN_ID}/{setting.key}/val3dity/{val_report.name}"
                val_report.parent.mkdir(parents=True, exist_ok=True)
                val_proc = run(P0_COMPOSE + ["run", "-T", "--rm", "tools", "val3dity", cj_ct, "--report", rep_ct], log_path=logs / "val3dity.log", check=False, quiet=True)
                if val_proc.returncode != 0:
                    issues.append({"setting": setting.key, "run_name": name, "building_id": "", "stage": "val3dity", "returncode": val_proc.returncode, "log": rel(logs / "val3dity.log")})
                roofer_by_id = parse_roofer_features(jsonl_files)
                if val_report.exists():
                    val_payload = json.loads(val_report.read_text(encoding="utf-8"))
                    val_by_id = {str(feature.get("id")): feature for feature in val_payload.get("features", []) if feature.get("id") is not None}
            rows = classify_buildings(label, C001_IDS, roofer_by_id, val_by_id)
            for row in rows:
                patch_prep_no_las(row, prep_metrics_by_bid.get(row["building_id"]))
            enriched = enrich_status_rows(rows, setting, name, rep_name)
            write_status_csv(status_csv, enriched)
            all_status_rows.extend(enriched)
            print(
                json.dumps(
                    {
                        "stage": "assemble",
                        "setting": setting.key,
                        "run_name": name,
                        "has_lod22": sum(r["has_lod22"] == "True" for r in rows),
                        "valid": sum(r["val3dity_valid"] == "True" for r in rows),
                        "status": "done",
                    },
                    ensure_ascii=False,
                ),
                flush=True,
            )
    expected_prep_rows = len(settings) * len(names) * len(C001_IDS)
    if len(prep_metric_rows) < expected_prep_rows:
        prep_metric_rows = collect_existing_prep_metrics(settings, names)
    write_csv(P0_RUN_DIR / "building_reconstruction_status.csv", all_status_rows)
    write_csv(P0_RUN_DIR / "prep_metrics.csv", prep_metric_rows)
    write_csv(ISSUES_CSV, issues, ["setting", "run_name", "building_id", "stage", "returncode", "log"])
    write_p0_versions()


def collect_existing_prep_metrics(settings: list[Setting], names: list[str]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for setting in settings:
        for name in names:
            outdir = P0_RUN_DIR / setting.key / "roofer" / name / "run_1"
            for bid in C001_IDS:
                metrics_path = outdir / f"{bid}_run_1_metrics.json"
                metrics = json.loads(metrics_path.read_text(encoding="utf-8")) if metrics_path.exists() else None
                rows.append(
                    {
                        "setting": setting.key,
                        "run_name": name,
                        "roofer_repeat": "run_1",
                        "building_id": bid,
                        "prep_returncode": "" if metrics is None else 0,
                        "n_clip": "" if metrics is None else metrics.get("n_clip", ""),
                        "n_used": "" if metrics is None else metrics.get("n_used", ""),
                        "n_building": "" if metrics is None else metrics.get("n_building", ""),
                        "n_building_in_fp": "" if metrics is None else metrics.get("n_building_in_fp", ""),
                        "classified_las": "" if metrics is None else metrics.get("classified_las", ""),
                    }
                )
    return rows


def existing_status_rows(setting: Setting, run_name: str, status_csv: Path) -> list[dict[str, Any]]:
    rows = read_csv(status_csv)
    rep_name = "run_1"
    out = []
    for row in rows:
        if row.get("setting") and row.get("run_name"):
            out.append(row)
        else:
            out.append({**row, "setting": setting.key, "run_name": run_name, "arm": run_name.split("_")[-2], "replicate": run_name.split("_")[-1], "roofer_repeat": rep_name})
    return out


def enrich_status_rows(rows: list[dict[str, str]], setting: Setting, run_name: str, rep_name: str) -> list[dict[str, Any]]:
    return [
        {
            "setting": setting.key,
            "run_name": run_name,
            "arm": run_name.split("_")[-2],
            "replicate": run_name.split("_")[-1],
            "roofer_repeat": rep_name,
            **row,
        }
        for row in rows
    ]


def source_for(setting: Setting, run_name: str) -> eight.Source:
    e = load_eight_module()
    arm = run_name.split("_")[-2]
    rep = run_name.split("_")[-1]
    gate_dir = P0_RUN_DIR / setting.key
    source_run = f"{setting.key}__{run_name}"
    return e.Source(
        source_group=f"gs_{arm}",
        source_run=source_run,
        display_label=f"{setting.key} {arm} {rep}",
        status_role="gs",
        status_path=gate_dir / "status" / f"{run_name}_run_1.csv",
        status_input=None,
        cityjson_path=gate_dir / "cityjson" / f"{run_name}_run_1.city.json",
        pointcloud_path=None,
        pointcloud_template=str(gate_dir / "roofer" / run_name / "run_1" / "{bid}_run_1_classified.las"),
        pair_raw=f"raw_{arm}",
        run_name=run_name,
        seed=arm,
        replicate=rep,
        readout=setting.readout_label,
        source_badge=setting.key,
        z_shift_to_reference_m=Z_SHIFT_TO_REF_M,
    )


def inventory_rows(settings: list[Setting], names: list[str]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for setting in settings:
        for name in names:
            ckpt = CKPT_ROOT / name / "ckpt/final.pt"
            paths = readout_paths(setting, name)
            src = source_for(setting, name)
            required = [ckpt, paths["npz"], paths["coverage"], src.status_path, src.cityjson_path]
            missing = [rel(p) for p in required if p is not None and not Path(p).exists()]
            rows.append(
                {
                    "setting": setting.key,
                    "run_name": name,
                    "status": "present" if not missing else "missing",
                    "ckpt": rel(ckpt),
                    "tsdf_npz": rel(paths["npz"]),
                    "coverage_csv": rel(paths["coverage"]),
                    "status_csv": rel(src.status_path),
                    "cityjson": rel(src.cityjson_path),
                    "missing_count": len(missing),
                    "missing_examples": ";".join(missing[:5]),
                    "readout": setting.readout_label,
                }
            )
    return rows


def load_status_maps(srcs: list[eight.Source]) -> dict[str, dict[str, dict[str, str]]]:
    maps: dict[str, dict[str, dict[str, str]]] = {}
    for src in srcs:
        if src.status_path is None or not src.status_path.exists():
            maps[src.source_run] = {}
            continue
        selected = {}
        for row in read_csv(src.status_path):
            bid = row.get("building_id")
            if bid in C001_IDS:
                selected[bid] = row
        maps[src.source_run] = selected
    return maps


def load_predictions(srcs: list[eight.Source]) -> tuple[dict[str, list[eight.RoofSurface]], dict[str, dict[str, list[eight.RoofSurface]]]]:
    e = load_eight_module()
    refs = e.parse_lod2_roofs(e.LOD2_DIR, set(C001_IDS))
    pred: dict[str, dict[str, list[eight.RoofSurface]]] = {}
    for src in srcs:
        parsed = e.parse_cityjson_roofs(src.cityjson_path, set(C001_IDS))
        pred[src.source_run] = {bid: e.shift_surface_z(surfaces, src.z_shift_to_reference_m) for bid, surfaces in parsed.items()}
    return refs, pred


def evaluate(args: argparse.Namespace) -> None:
    e = load_eight_module()
    settings = setting_map(args.settings)
    names = selected_run_names(args)
    srcs = [source_for(setting, name) for setting in settings for name in names]
    inventory = inventory_rows(settings, names)
    write_csv(INVENTORY_CSV, inventory)
    missing = [r for r in inventory if r["status"] == "missing"]
    if missing:
        raise RuntimeError(f"missing ablation products: {missing[:3]}")
    e.configure_korean_font()
    refs, pred_by_source = load_predictions(srcs)
    status_maps = load_status_maps(srcs)
    lenses = e.build_lenses()
    metrics = e.build_metric_rows(srcs, refs, pred_by_source, status_maps, lenses)
    augment_metric_rows(metrics)
    coverage_rows = collect_coverage(settings, names)
    filter_rows = build_filter_contrib(coverage_rows)
    summary = build_summary(metrics, coverage_rows)
    tradeoff = build_tradeoff(summary)
    cases = representative_rows(metrics, coverage_rows)

    write_csv(COVERAGE_CSV, coverage_rows)
    write_csv(FILTER_CSV, filter_rows)
    write_csv(METRICS_CSV, metrics)
    write_csv(SUMMARY_CSV, summary)
    write_csv(TRADEOFF_CSV, tradeoff)
    write_csv(CASE_CSV, cases)

    footprints = e.base.load_footprints(e.FOOTPRINTS_GPKG, set(C001_IDS))
    figures = plot_figures(settings, summary, tradeoff, coverage_rows, metrics, srcs, refs, pred_by_source, footprints)
    write_versions(settings, inventory, figures)
    write_report(settings, inventory, summary, tradeoff, filter_rows, cases, figures)
    copy_snapshots()
    print(json.dumps({"report": rel(REPORT_PATH), "metrics_rows": len(metrics), "coverage_rows": len(coverage_rows), "figures": len(figures)}, ensure_ascii=False))


def augment_metric_rows(rows: list[dict[str, Any]]) -> None:
    lookup = {s.key: s for s in SETTINGS}
    for row in rows:
        source_run = str(row.get("source_run", ""))
        setting_key, run_name = source_run.split("__", 1)
        setting = lookup[setting_key]
        row["setting"] = setting_key
        row["run_name"] = run_name
        row["arm"] = run_name.split("_")[-2]
        row["replicate"] = run_name.split("_")[-1]
        row["readout_min_obs"] = setting.min_obs
        row["readout_voxel_m"] = setting.voxel
        row["readout_alpha"] = setting.alpha
        row["readout_sor"] = setting.sor
        row["readout_sor_std"] = setting.sor_std


def collect_coverage(settings: list[Setting], names: list[str]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for setting in settings:
        for name in names:
            path = readout_paths(setting, name)["coverage"]
            for row in read_csv(path):
                rows.append(
                    {
                        "setting": setting.key,
                        "run_name": name,
                        "arm": name.split("_")[-2],
                        "replicate": name.split("_")[-1],
                        "min_obs": setting.min_obs,
                        "voxel_m": setting.voxel,
                        "sor": setting.sor,
                        "sor_std": setting.sor_std,
                        **row,
                    }
                )
    return rows


def float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        v = float(text)
    except ValueError:
        return None
    return v if math.isfinite(v) else None


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


def build_filter_contrib(coverage: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str, str], list[float]] = defaultdict(list)
    for row in coverage:
        v = float_or_none(row.get("coverage_frac"))
        if v is not None:
            grouped[(row["setting"], row["run_name"], row["stage"])].append(v)
    rows = []
    for setting in [s.key for s in SETTINGS]:
        run_set = sorted({key[1] for key in grouped if key[0] == setting})
        for name in run_set:
            all_cov = mean(grouped.get((setting, name, "voxel_all_pre_minobs"), []))
            minobs_cov = mean(grouped.get((setting, name, "minobs_post_gate_pre_sor"), []))
            sor_cov = mean(grouped.get((setting, name, "sor_post_clean"), []))
            rows.append(
                {
                    "setting": setting,
                    "run_name": name,
                    "arm": name.split("_")[-2],
                    "replicate": name.split("_")[-1],
                    "coverage_pre_minobs": fmt(all_cov),
                    "coverage_post_minobs": fmt(minobs_cov),
                    "coverage_post_sor": fmt(sor_cov),
                    "drop_pre_to_minobs": fmt((all_cov - minobs_cov) if all_cov is not None and minobs_cov is not None else None),
                    "drop_minobs_to_sor": fmt((minobs_cov - sor_cov) if minobs_cov is not None and sor_cov is not None else None),
                    "drop_pre_to_final": fmt((all_cov - sor_cov) if all_cov is not None and sor_cov is not None else None),
                }
            )
    return rows


def build_summary(metrics: list[dict[str, Any]], coverage: list[dict[str, Any]]) -> list[dict[str, Any]]:
    cov_by_setting: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    case_cov: dict[tuple[str, str, str], float] = {}
    for row in coverage:
        v = float_or_none(row.get("coverage_frac"))
        if v is None:
            continue
        cov_by_setting[row["setting"]][row["stage"]].append(v)
        if row["stage"] == "sor_post_clean":
            case_cov[(row["setting"], row["run_name"], row["building_id"])] = v
    rows = []
    base_by_item = {
        (row["run_name"], row["building_id"]): row
        for row in metrics
        if row["setting"] == "base"
    }
    base_cov = {
        (run_name, bid): cov
        for (setting, run_name, bid), cov in case_cov.items()
        if setting == "base"
    }
    for setting in [s.key for s in SETTINGS]:
        group = [row for row in metrics if row["setting"] == setting]
        comp = [float(row["completeness"]) for row in group if float_or_none(row.get("completeness")) is not None]
        corr = [float(row["correctness"]) for row in group if float_or_none(row.get("correctness")) is not None]
        rms = [float(row["ref_rms_m"]) for row in group if float_or_none(row.get("ref_rms_m")) is not None]
        deltas_cov = []
        deltas_corr = []
        deltas_rms = []
        for row in group:
            key = (row["run_name"], row["building_id"])
            if setting != "base":
                this_cov = case_cov.get((setting, row["run_name"], row["building_id"]))
                base_c = base_cov.get(key)
                if this_cov is not None and base_c is not None:
                    deltas_cov.append(this_cov - base_c)
                base_row = base_by_item.get(key)
                if base_row:
                    c0 = float_or_none(base_row.get("correctness"))
                    c1 = float_or_none(row.get("correctness"))
                    if c0 is not None and c1 is not None:
                        deltas_corr.append(c1 - c0)
                    r0 = float_or_none(base_row.get("ref_rms_m"))
                    r1 = float_or_none(row.get("ref_rms_m"))
                    if r0 is not None and r1 is not None:
                        deltas_rms.append(r1 - r0)
        buckets = Counter(row.get("shell_bucket", "") for row in group)
        rows.append(
            {
                "setting": setting,
                "n": len(group),
                "has_lod22": sum(eight.tf(row.get("has_lod22")) for row in group),
                "val3dity_valid": sum(eight.tf(row.get("val3dity_valid")) for row in group),
                "not_built": buckets["미조립"],
                "roof0_success": buckets["지붕면0 성공"],
                "invalid_or_collapse": buckets["무효·붕괴"],
                "assembled": buckets["조립"],
                "mean_coverage_pre_minobs": fmt(mean(cov_by_setting[setting]["voxel_all_pre_minobs"])),
                "mean_coverage_post_minobs": fmt(mean(cov_by_setting[setting]["minobs_post_gate_pre_sor"])),
                "mean_coverage_post_sor": fmt(mean(cov_by_setting[setting]["sor_post_clean"])),
                "mean_completeness": fmt(mean(comp)),
                "mean_correctness": fmt(mean(corr)),
                "median_ref_rms_m": fmt(median(rms)),
                "mean_ref_rms_m": fmt(mean(rms)),
                "delta_coverage_post_sor_vs_base": fmt(mean(deltas_cov)),
                "delta_correctness_vs_base": fmt(mean(deltas_corr)),
                "delta_ref_rms_m_vs_base": fmt(mean(deltas_rms)),
            }
        )
    return rows


def build_tradeoff(summary: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    base = next((row for row in summary if row["setting"] == "base"), None)
    base_cov = float_or_none(base.get("mean_coverage_post_sor")) if base else None
    base_corr = float_or_none(base.get("mean_correctness")) if base else None
    base_rms = float_or_none(base.get("median_ref_rms_m")) if base else None
    for row in summary:
        cov = float_or_none(row.get("mean_coverage_post_sor"))
        corr = float_or_none(row.get("mean_correctness"))
        rms = float_or_none(row.get("median_ref_rms_m"))
        out.append(
            {
                "setting": row["setting"],
                "mean_coverage_post_sor": row["mean_coverage_post_sor"],
                "mean_correctness": row["mean_correctness"],
                "median_ref_rms_m": row["median_ref_rms_m"],
                "has_lod22": row["has_lod22"],
                "val3dity_valid": row["val3dity_valid"],
                "coverage_delta_vs_base": fmt(cov - base_cov if cov is not None and base_cov is not None else None),
                "correctness_delta_vs_base": fmt(corr - base_corr if corr is not None and base_corr is not None else None),
                "median_ref_rms_delta_vs_base": fmt(rms - base_rms if rms is not None and base_rms is not None else None),
                "tradeoff_note": tradeoff_note(cov, corr, rms, base_cov, base_corr, base_rms),
            }
        )
    return out


def tradeoff_note(cov: float | None, corr: float | None, rms: float | None, base_cov: float | None, base_corr: float | None, base_rms: float | None) -> str:
    if None in (cov, corr, rms, base_cov, base_corr, base_rms):
        return "insufficient"
    cov_gain = cov - base_cov
    corr_loss = base_corr - corr
    rms_cost = rms - base_rms
    if cov_gain > 0.03 and corr_loss <= 0.02 and rms_cost <= 0.5:
        return "coverage_gain_small_accuracy_cost"
    if cov_gain > 0.03 and (corr_loss > 0.02 or rms_cost > 0.5):
        return "coverage_gain_with_accuracy_cost"
    if cov_gain <= 0.03:
        return "little_coverage_gain"
    return "mixed"


def representative_rows(metrics: list[dict[str, Any]], coverage: list[dict[str, Any]]) -> list[dict[str, Any]]:
    metric_by = {(row["setting"], row["run_name"], row["building_id"]): row for row in metrics}
    cov_by = {
        (row["setting"], row["run_name"], row["building_id"], row["stage"]): row
        for row in coverage
        if row["building_id"] in {"DEBY_LOD2_60098", "DEBY_LOD2_8568391"}
    }
    rows = []
    for bid in ["DEBY_LOD2_60098", "DEBY_LOD2_8568391"]:
        for setting in [s.key for s in SETTINGS]:
            for name in run_names():
                m = metric_by.get((setting, name, bid), {})
                rows.append(
                    {
                        "building_id": bid,
                        "setting": setting,
                        "run_name": name,
                        "coverage_pre_minobs": (cov_by.get((setting, name, bid, "voxel_all_pre_minobs")) or {}).get("coverage_frac", ""),
                        "coverage_post_minobs": (cov_by.get((setting, name, bid, "minobs_post_gate_pre_sor")) or {}).get("coverage_frac", ""),
                        "coverage_post_sor": (cov_by.get((setting, name, bid, "sor_post_clean")) or {}).get("coverage_frac", ""),
                        "has_lod22": m.get("has_lod22", ""),
                        "val3dity_valid": m.get("val3dity_valid", ""),
                        "completeness": m.get("completeness", ""),
                        "correctness": m.get("correctness", ""),
                        "ref_rms_m": m.get("ref_rms_m", ""),
                        "shell_bucket": m.get("shell_bucket", ""),
                    }
                )
    return rows


def plot_figures(
    settings: list[Setting],
    summary: list[dict[str, Any]],
    tradeoff: list[dict[str, Any]],
    coverage: list[dict[str, Any]],
    metrics: list[dict[str, Any]],
    srcs: list[eight.Source],
    refs: dict[str, list[eight.RoofSurface]],
    pred_by_source: dict[str, dict[str, list[eight.RoofSurface]]],
    footprints: dict[str, Any],
) -> list[Path]:
    e = load_eight_module()
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    labels = [s.key for s in settings]
    x = np.arange(len(labels))
    cov = [float_or_none(next(r for r in summary if r["setting"] == lab)["mean_coverage_post_sor"]) or 0 for lab in labels]
    comp = [float_or_none(next(r for r in summary if r["setting"] == lab)["mean_completeness"]) or 0 for lab in labels]
    corr = [float_or_none(next(r for r in summary if r["setting"] == lab)["mean_correctness"]) or 0 for lab in labels]
    fig, ax = plt.subplots(figsize=(10.5, 4.2))
    ax.bar(x - 0.24, cov, width=0.24, label="coverage")
    ax.bar(x, comp, width=0.24, label="completeness")
    ax.bar(x + 0.24, corr, width=0.24, label="correctness")
    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=35, ha="right")
    ax.set_ylim(0, 1.05)
    ax.set_ylabel("mean rate")
    ax.set_title("Readout ablation recovery and roof-match tradeoff")
    ax.grid(axis="y", alpha=0.25)
    ax.legend()
    fig.tight_layout()
    out = FIG_DIR / "coverage_recovery_summary.png"
    fig.savefig(out, dpi=170)
    plt.close(fig)
    paths.append(out)

    fig, ax = plt.subplots(figsize=(6.6, 4.8))
    for row in tradeoff:
        xval = float_or_none(row.get("mean_coverage_post_sor"))
        yval = float_or_none(row.get("median_ref_rms_m"))
        if xval is None or yval is None:
            continue
        ax.scatter(xval, yval, s=70)
        ax.text(xval + 0.004, yval, row["setting"], fontsize=8)
    ax.set_xlabel("mean final readout coverage")
    ax.set_ylabel("median reference RMS (m)")
    ax.set_title("Coverage vs reference-distance cost")
    ax.grid(alpha=0.25)
    fig.tight_layout()
    out = FIG_DIR / "coverage_accuracy_scatter.png"
    fig.savefig(out, dpi=170)
    plt.close(fig)
    paths.append(out)

    stage_order = ["voxel_all_pre_minobs", "minobs_post_gate_pre_sor", "sor_post_clean"]
    fig, ax = plt.subplots(figsize=(10.5, 4.2))
    width = 0.23
    for idx, stage in enumerate(stage_order):
        vals = []
        for label in labels:
            group = [float(row["coverage_frac"]) for row in coverage if row["setting"] == label and row["stage"] == stage and float_or_none(row.get("coverage_frac")) is not None]
            vals.append(float(np.mean(group)) if group else 0)
        ax.bar(x + (idx - 1) * width, vals, width=width, label=stage)
    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=35, ha="right")
    ax.set_ylim(0, 1.05)
    ax.set_ylabel("mean coverage")
    ax.set_title("Filter-stage retention")
    ax.grid(axis="y", alpha=0.25)
    ax.legend(fontsize=8)
    fig.tight_layout()
    out = FIG_DIR / "filter_stage_contribution.png"
    fig.savefig(out, dpi=170)
    plt.close(fig)
    paths.append(out)

    metric_by = {(row["source_run"], row["building_id"]): row for row in metrics}
    source_by = {src.source_run: src for src in srcs}
    cache = e.PointCloudCache(footprints)
    names_for_case = [name for name in run_names() if f"base__{name}" in source_by and f"relaxed__{name}" in source_by]
    if not names_for_case:
        return paths
    for bid in ["DEBY_LOD2_60098", "DEBY_LOD2_8568391"]:
        fig = plt.figure(figsize=(10.8, max(4.0, 2.15 * len(names_for_case))))
        for row_idx, name in enumerate(names_for_case, start=0):
            for setting_key, col_base in [("base", 1), ("relaxed", 3)]:
                src_key = f"{setting_key}__{name}"
                src = source_by[src_key]
                row = metric_by.get((src_key, bid), {})
                pts = cache.read_roof_points(src, bid)
                title = f"{setting_key} {name.split('_')[-2]} {name.split('_')[-1]}"
                e.draw_cloud(fig.add_subplot(len(names_for_case), 4, row_idx * 4 + col_base), pts, footprints[bid], title)
                note = f"C {row.get('completeness', '-')}\nR {row.get('correctness', '-')}\nRMS {row.get('ref_rms_m', '-')}"
                e.draw_model(fig.add_subplot(len(names_for_case), 4, row_idx * 4 + col_base + 1, projection="3d"), pred_by_source[src_key][bid], footprints[bid], setting_key, note)
        fig.suptitle(f"Readout ablation case: {bid}", fontsize=12)
        fig.tight_layout(rect=(0, 0, 1, 0.97))
        out = FIG_DIR / f"case_{bid.replace('DEBY_LOD2_', '')}_base_vs_relaxed.png"
        fig.savefig(out, dpi=150)
        plt.close(fig)
        paths.append(out)
    return paths


def md_table(rows: list[dict[str, Any]], columns: list[str], max_rows: int | None = None) -> list[str]:
    use = rows if max_rows is None else rows[:max_rows]
    out = ["| " + " | ".join(columns) + " |", "|" + "|".join("---" for _ in columns) + "|"]
    for row in use:
        out.append("| " + " | ".join(str(row.get(col, "")) for col in columns) + " |")
    if max_rows is not None and len(rows) > max_rows:
        out.append("| ... | " + f"{len(rows) - max_rows} rows omitted |" + " | ".join("" for _ in columns[2:]) + " |")
    return out


def write_report(
    settings: list[Setting],
    inventory: list[dict[str, Any]],
    summary: list[dict[str, Any]],
    tradeoff: list[dict[str, Any]],
    filter_rows: list[dict[str, Any]],
    cases: list[dict[str, Any]],
    figures: list[Path],
) -> None:
    branch = capture(["git", "branch", "--show-current"])
    head = capture(["git", "rev-parse", "HEAD"])
    base = next(row for row in summary if row["setting"] == "base")
    relaxed = next(row for row in summary if row["setting"] == "relaxed")
    base_cov = float_or_none(base["mean_coverage_post_sor"])
    relaxed_cov = float_or_none(relaxed["mean_coverage_post_sor"])
    relaxed_corr_delta = next(row for row in tradeoff if row["setting"] == "relaxed")["correctness_delta_vs_base"]
    relaxed_rms_delta = next(row for row in tradeoff if row["setting"] == "relaxed")["median_ref_rms_delta_vs_base"]
    matrix = [
        {
            "setting": s.key,
            "minobs": s.min_obs,
            "SOR": "off" if s.sor == "off" else f"on std{s.sor_std:g}",
            "voxel": s.voxel,
            "alpha": s.alpha,
            "purpose": s.purpose,
        }
        for s in settings
    ]
    filter_setting_summary = []
    for setting in [s.key for s in settings]:
        group = [row for row in filter_rows if row["setting"] == setting]
        filter_setting_summary.append(
            {
                "setting": setting,
                "pre": fmt(mean([float(row["coverage_pre_minobs"]) for row in group if float_or_none(row.get("coverage_pre_minobs")) is not None])),
                "post_minobs": fmt(mean([float(row["coverage_post_minobs"]) for row in group if float_or_none(row.get("coverage_post_minobs")) is not None])),
                "post_sor": fmt(mean([float(row["coverage_post_sor"]) for row in group if float_or_none(row.get("coverage_post_sor")) is not None])),
                "drop_minobs": fmt(mean([float(row["drop_pre_to_minobs"]) for row in group if float_or_none(row.get("drop_pre_to_minobs")) is not None])),
                "drop_sor": fmt(mean([float(row["drop_minobs_to_sor"]) for row in group if float_or_none(row.get("drop_minobs_to_sor")) is not None])),
            }
        )
    lines = [
        "# E5 C001 ③a readout 재실행 ablation",
        "",
        "> 재확인: GS 학습 0 · GS 레시피 변경 0 · 정본 readout 미변경 · 판정 0. 기존 C001 6런 체크포인트에 readout 파라미터만 바꿔 재점군화, Roofer 재조립, 8-way 재측정했다. CRS는 EPSG:25832.",
        "",
        "## 한계",
        "",
        "- readout만 본다. 플로터 근원 수리는 ③b(재학습) 대상이다.",
        "- C001 18동·2씨드다. 완화 조합이 순이득으로 보여도 정본 채택은 §11 변경 절차 대상이다.",
        "- 완화는 플로터 유입 대가가 있을 수 있어 coverage와 correctness/ref RMS를 함께 본다.",
        "- `base`도 ③a 산출 경로에서 다시 추출·조립했다. 정본 canonical 산출은 비교 기준으로만 남기고 수정하지 않았다.",
        "",
        "## 시작 전 확인",
        "",
        f"- 브랜치·HEAD: `{branch}` · `{head}`.",
        f"- 체크포인트: `{rel(CKPT_ROOT)}/gs_e5_C001_*_*/ckpt/final.pt` 6개.",
        f"- 기존 학습 지문: `{rel(TRAIN_RUN_DIR / 'train_fingerprints.csv')}`.",
        f"- 정본 조립 입력/기준선: `{rel(CANON_GATE_DIR)}`와 `docs/experiments/e5_c001_8way/tables/e5_c001_8way_metrics.csv`.",
        f"- ② readout 귀속 근거: `docs/experiments/e5_c001_render/reports/W_E5_C001_렌더플로터점검.md`, `docs/experiments/e5_c001_render/tables/e5_c001_render_readout_coverage.csv`.",
        "- 변경한 것은 extractor의 `min_obs`, `voxel`, `SOR`뿐이다. Roofer 설정과 GS-semantic LAS prep은 기존 경로를 그대로 썼다.",
        "",
        "## ablation 매트릭스",
        "",
        *md_table(matrix, ["setting", "minobs", "SOR", "voxel", "alpha", "purpose"]),
        "",
        "## 커버리지 회복",
        "",
        *md_table(filter_setting_summary, ["setting", "pre", "post_minobs", "post_sor", "drop_minobs", "drop_sor"]),
        "",
        "## 트레이드오프",
        "",
        *md_table(
            tradeoff,
            [
                "setting",
                "mean_coverage_post_sor",
                "mean_correctness",
                "median_ref_rms_m",
                "has_lod22",
                "val3dity_valid",
                "coverage_delta_vs_base",
                "correctness_delta_vs_base",
                "median_ref_rms_delta_vs_base",
                "tradeoff_note",
            ],
        ),
        "",
        "## 대표 건물",
        "",
        "- 60098과 8568391은 ②에서 readout 폐기가 큰 사례로 지정된 두 동이다. 전체 행은 `docs/experiments/e5_c001_readout_ablation/tables/e5_c001_readout_ablation_representative_buildings.csv`에 둔다.",
        "",
        *md_table(
            [row for row in cases if row["setting"] in {"base", "relaxed"}],
            ["building_id", "setting", "run_name", "coverage_pre_minobs", "coverage_post_minobs", "coverage_post_sor", "has_lod22", "correctness", "ref_rms_m", "shell_bucket"],
            max_rows=24,
        ),
        "",
        "## 판별 한 줄",
        "",
        f"- 판정 아님: readout 완화 조합(relaxed)은 최종 coverage를 {fmt(base_cov)}에서 {fmt(relaxed_cov)}로 바꿨고, correctness delta={relaxed_corr_delta}, median ref RMS delta={relaxed_rms_delta}로 관찰된다.",
        "",
        "## ③b 필요 폭",
        "",
        "- coverage가 회복되면서 correctness/RMS 대가가 함께 나타난 설정은 readout 단독 완화보다 플로터 근원 수리(distortion 복원, depth 감독 강화, floater/elongation 제어)를 ③b 후보로 남긴다.",
        "- coverage 회복이 작고 품질도 비슷한 설정은 minobs/SOR가 단독 지배 원인이 아니라 렌더 깊이·플로터·SH 흡수와 복합이라는 관찰 재료로 남긴다.",
        "- 어떤 완화 설정이 순이득으로 보이더라도 §11 정본 변경 절차로만 채택 여부를 검토한다.",
        "",
        "## 산출",
        "",
        f"- coverage: `{rel(COVERAGE_CSV)}`.",
        f"- filter contribution: `{rel(FILTER_CSV)}`.",
        f"- metrics: `{rel(METRICS_CSV)}`.",
        f"- summary/tradeoff: `{rel(SUMMARY_CSV)}`, `{rel(TRADEOFF_CSV)}`.",
        f"- inventory/issues: `{rel(INVENTORY_CSV)}`, `{rel(ISSUES_CSV)}`.",
        f"- versions: `{rel(P2_RUN_DIR / 'versions.txt')}`, `{rel(P0_RUN_DIR / 'versions.txt')}`.",
        f"- figures: `{rel(FIG_DIR)}/`.",
        "",
        *[f"- `{rel(path)}`" for path in figures],
        "",
        "## 인용",
        "",
        "- ② 회신: `docs/experiments/e5_c001_render/reports/W_E5_C001_렌더플로터점검.md`.",
        "- 분석 연결: `docs/W_E5_C001_렌더플로터_분석·③라우팅_20260707.md`(파일이 있으면 잠금본 우선).",
        "- config 감사: `docs/experiments/w_d4/reports/W_D4_손실config_감사.md` §6.",
        "- 2DGS: [arXiv 2403.17888](https://arxiv.org/abs/2403.17888).",
        "- CityGaussianV2: [arXiv 2411.00771](https://arxiv.org/abs/2411.00771).",
    ]
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_versions(settings: list[Setting], inventory: list[dict[str, Any]], figures: list[Path]) -> None:
    P2_RUN_DIR.mkdir(parents=True, exist_ok=True)
    matrix = [
        {
            "setting": s.key,
            "min_obs": s.min_obs,
            "voxel": s.voxel,
            "alpha": s.alpha,
            "sor": s.sor,
            "sor_std": s.sor_std,
            "purpose": s.purpose,
        }
        for s in settings
    ]
    lines = [
        f"run_id: {RUN_ID}",
        f"created_utc: {datetime.now(timezone.utc).isoformat()}",
        "task: E5 C001 ③a readout rerun ablation",
        "mode: readout-only ablation; no GS training; no GS recipe/loss/densification change; canonical readout unchanged; no verdict",
        "crs: EPSG:25832",
        f"git_branch: {capture(['git', 'branch', '--show-current'])}",
        f"git_head: {capture(['git', 'rev-parse', 'HEAD'])}",
        "docker_images:",
        f"  gs_readout: {DEV_IMAGE}",
        "  roofer_tools: jointbuildgs-p0-tools:t0 and P0 roofer compose service",
        f"script: {rel(Path(__file__))}",
        f"extractor_script: phases/p2-gsjso/scripts/e5_c001_readout_extract_ablation.py",
        f"settings: {json.dumps(matrix, ensure_ascii=False)}",
        f"input_checkpoints: {rel(CKPT_ROOT)}/gs_e5_C001_*_*/ckpt/final.pt",
        f"input_train_fingerprints: {rel(TRAIN_RUN_DIR / 'train_fingerprints.csv')}",
        f"canonical_gate_reference_unchanged: {rel(CANON_GATE_DIR)}",
        f"p0_assembly_run: {rel(P0_RUN_DIR)}",
        "outputs:",
        f"  report: {rel(REPORT_PATH)}",
        f"  coverage: {rel(COVERAGE_CSV)}",
        f"  metrics: {rel(METRICS_CSV)}",
        f"  summary: {rel(SUMMARY_CSV)}",
        f"  figures: {rel(FIG_DIR)}",
        f"inventory_rows: {len(inventory)}",
        f"figures: {len(figures)}",
    ]
    (P2_RUN_DIR / "versions.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    manifest = {
        "run_id": RUN_ID,
        "outputs": [
            rel(REPORT_PATH),
            rel(COVERAGE_CSV),
            rel(FILTER_CSV),
            rel(METRICS_CSV),
            rel(SUMMARY_CSV),
            rel(TRADEOFF_CSV),
            rel(CASE_CSV),
            rel(INVENTORY_CSV),
            rel(ISSUES_CSV),
            rel(FIG_DIR),
            rel(P2_RUN_DIR / "versions.txt"),
            rel(P0_RUN_DIR / "versions.txt"),
        ],
    }
    (P2_RUN_DIR / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_p0_versions() -> None:
    P0_RUN_DIR.mkdir(parents=True, exist_ok=True)
    lines = [
        f"run_id: {P0_RUN_ID}",
        f"created_utc: {datetime.now(timezone.utc).isoformat()}",
        "task: E5 C001 ③a Roofer assembly for readout ablation",
        "mode: Roofer rerun from ablated readout point clouds; no GS training; canonical readout unchanged; no verdict",
        "crs: EPSG:25832",
        f"git_branch: {capture(['git', 'branch', '--show-current'])}",
        f"git_head: {capture(['git', 'rev-parse', 'HEAD'])}",
        "roofer_defaults: unchanged P0 compose Roofer defaults",
        f"settings: {','.join(s.key for s in SETTINGS)}",
        f"status: {rel(P0_RUN_DIR / 'building_reconstruction_status.csv')}",
        f"prep_metrics: {rel(P0_RUN_DIR / 'prep_metrics.csv')}",
    ]
    (P0_RUN_DIR / "versions.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")


def copy_snapshots() -> None:
    snap = P2_RUN_DIR / "snapshots"
    snap.mkdir(parents=True, exist_ok=True)
    for path in [REPORT_PATH, COVERAGE_CSV, FILTER_CSV, METRICS_CSV, SUMMARY_CSV, TRADEOFF_CSV, CASE_CSV, INVENTORY_CSV, ISSUES_CSV]:
        if path.exists():
            shutil.copy2(path, snap / path.name)


def build_parser() -> argparse.ArgumentParser:
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
    return parser


def evaluate_or_container(args: argparse.Namespace) -> None:
    if os.environ.get("E5_READOUT_ABLATION_EVAL_CONTAINER") == "1":
        evaluate(args)
        return
    try:
        load_eight_module()
    except ModuleNotFoundError:
        cmd = [
            "docker",
            "run",
            "--rm",
            "-i",
            "--user",
            f"{os.getuid()}:{os.getgid()}",
            "-e",
            "E5_READOUT_ABLATION_EVAL_CONTAINER=1",
            "-e",
            "MPLCONFIGDIR=/tmp/matplotlib",
            "-v",
            f"{REPO}:/workspace/JointBuildGS",
            "-w",
            "/workspace/JointBuildGS",
            "jointbuildgs-p0-tools:t0",
            "python3",
            "phases/p2-gsjso/scripts/e5_c001_readout_ablation.py",
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
        run(cmd, log_path=P2_RUN_DIR / "evaluate_container.log", check=True, quiet=False)
        return
    evaluate(args)


def main() -> None:
    os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib")
    args = build_parser().parse_args()
    if args.cmd in {"readout", "all"}:
        run_readout(args)
    if args.cmd in {"assemble", "all"}:
        run_assemble(args)
    if args.cmd in {"evaluate", "all"}:
        evaluate_or_container(args)


if __name__ == "__main__":
    main()
