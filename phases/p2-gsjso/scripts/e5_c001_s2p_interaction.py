#!/usr/bin/env python3
"""E5 C001 S2 follow-up: normal x prune interaction and conditional mono depth.

This task-scoped harness keeps canonical S1/S2 artifacts read-only.  The first
implementation slice owns Arm 1-prime config generation, training, roof-crop
timeline extraction, and recording-only densification audit aggregation.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import subprocess
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib")
os.environ.setdefault("XDG_CACHE_HOME", "/tmp")

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt

SCRIPT_DIR = Path(__file__).resolve().parent
REPO = Path(__file__).resolve().parents[3]
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

import e5_c001_s2_direction_position as s2  # noqa: E402
from e5_pilot_gate_tools import DEV_IMAGE, sha256_file  # noqa: E402

RUN_ID = "20260710_e5_c001_s2p_interaction"
RUN_DIR = REPO / "phases/p2-gsjso/runs" / RUN_ID
P0_RUN_ID = "e5p_s2p_interaction_20260710_C001"
P0_RUN_DIR = s2.P0_RUNS / P0_RUN_ID
REPAIR_RUN_ID = "e5p_s2p_405_repair_20260710_C001"
REPAIRED_P0_RUN_DIR = s2.P0_RUNS / REPAIR_RUN_ID / P0_RUN_ID
CONFIG_DIR = REPO / "configs/tum_mob/e5_s2p_interaction"
RESULTS_ROOT = REPO / "results/tum_transfer/e5_s2p_interaction/C001"
READOUT_ROOT = RESULTS_ROOT / "readout"
CKPT_ROOT = RESULTS_ROOT / "runs"
TRAIN_LOG_ROOT = RESULTS_ROOT / "train_logs"
TORCH_EXTENSIONS = RESULTS_ROOT / "torch_extensions"
BASE_CONFIG = REPO / "configs/tum_mob/e5_s2_direction_position/gs_e5_C001_s2_arm1_dense_r1.yaml"
DATA_ROOT = REPO / "results/tum_transfer/e5_pilot/C001/data_geoidfix_C001_buf20"
MONO_V2_ROOT = RESULTS_ROOT / "mono_priors_v2"
MONO_V2_DEPTH_DIR = MONO_V2_ROOT / "depth_aligned_npy"
DA_REPO = REPO / "results/tum_transfer/e5_s2_direction_position/C001/mono_priors/Depth-Anything-V2"

FIG_DIR = REPO / "docs/figs/e5_c001_s2p"
CSV_INVENTORY = REPO / "docs/e5_c001_s2p_inventory.csv"
CSV_TIMELINE = REPO / "docs/e5_c001_s2p_timeline_roofcrop.csv"
CSV_DENSIFY = REPO / "docs/e5_c001_s2p_densify_log.csv"
CSV_ISSUES = REPO / "docs/e5_c001_s2p_issues.csv"
CSV_MONO_V2 = REPO / "docs/e5_c001_s2p_monodepth_precheck_v2.csv"
CSV_MONO_V2_IMAGE = REPO / "docs/e5_c001_s2p_monodepth_precheck_v2_image.csv"
CSV_MONO_V2_VIEW = REPO / "docs/e5_c001_s2p_monodepth_precheck_v2_view.csv"
CSV_MONO_V2_RUNTIME = REPO / "docs/e5_c001_s2p_monodepth_runtime_v2.csv"
CSV_SHEET_OPACITY = REPO / "docs/e5_c001_s2p_sheet_opacity_dist.csv"
CSV_TWIN_REND = REPO / "docs/e5_c001_s2p_twin_rend_dist.csv"
CSV_COVERAGE = REPO / "docs/e5_c001_s2p_coverage.csv"
CSV_FILTER = REPO / "docs/e5_c001_s2p_filter_contrib.csv"
CSV_405_BUILDING = REPO / "docs/e5_c001_s2p_405_rescore_building.csv"
CSV_405_REPAIR = REPO / "docs/e5_c001_s2p_405_rescore.csv"
CSV_READOUT_SUMMARY = REPO / "docs/e5_c001_s2p_summary.csv"
CSV_READOUT_TRADEOFF = REPO / "docs/e5_c001_s2p_tradeoff.csv"
CSV_READOUT_CASES = REPO / "docs/e5_c001_s2p_representative_buildings.csv"
CSV_READOUT_INVENTORY = REPO / "docs/e5_c001_s2p_readout_inventory.csv"
CSV_READOUT_ISSUES = REPO / "docs/e5_c001_s2p_readout_issues.csv"

TIMELINE_IDS = ["4907202", "4908168", "4908178", "4907184"]
TIMELINE_FULL_IDS = [f"DEBY_LOD2_{sid}" for sid in TIMELINE_IDS]
SOURCE_DOCS = [
    REPO / "docs/W_E5_C001_S2_중간검수·Arm3회부_20260710.md",
    REPO / "docs/원격프롬프트_S2_방향자리_사슬4arm·선행묶음_20260710.md",
    REPO / "docs/W_S2설계_손실비교·실험계획_20260710.md",
]


def rel(path: Path | str) -> str:
    return s2.rel(path)


def ws(path: Path) -> str:
    return f"/workspace/JointBuildGS/{rel(path)}"


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if fields is None:
        fields = list(rows[0].keys()) if rows else []
    with path.open("w", newline="", encoding="utf-8") as f:
        if not fields:
            return
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists() or path.stat().st_size == 0:
        return []
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def append_issue(part: str, severity: str, message: str, path: Path | str | None = None) -> None:
    rows: list[dict[str, Any]] = list(read_csv(CSV_ISSUES))
    rows.append(
        {
            "part": part,
            "severity": severity,
            "message": message,
            "path": rel(path) if path else "",
            "created_utc": datetime.now(timezone.utc).isoformat(),
        }
    )
    write_csv(CSV_ISSUES, rows, ["part", "severity", "message", "path", "created_utc"])


def arm1p_run_name(rep: int) -> str:
    return f"gs_e5_C001_s2p_arm1p_dense_r{rep}"


def checkpoint_path(run_name: str, step: int | str) -> Path:
    if step == "final" or step == 30000:
        return CKPT_ROOT / run_name / "ckpt/final.pt"
    return CKPT_ROOT / run_name / "ckpt" / f"step_{int(step):06d}.pt"


def docker_base(gpu: str) -> list[str]:
    return [
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
        "MPLCONFIGDIR=/tmp/matplotlib",
        "-e",
        "XDG_CACHE_HOME=/tmp",
        "-e",
        f"CUDA_VISIBLE_DEVICES={gpu}",
        "-e",
        f"TORCH_EXTENSIONS_DIR={ws(TORCH_EXTENSIONS)}",
        "-v",
        f"{REPO}:/workspace/JointBuildGS",
        "-w",
        "/workspace/JointBuildGS",
        DEV_IMAGE,
    ]


def write_manifest() -> None:
    RUN_DIR.mkdir(parents=True, exist_ok=True)
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=REPO, text=True, stdout=subprocess.PIPE, check=True
    ).stdout.strip()
    payload = {
        "run_id": RUN_ID,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "git_head": head,
        "branch": subprocess.run(
            ["git", "branch", "--show-current"], cwd=REPO, text=True, stdout=subprocess.PIPE, check=True
        ).stdout.strip(),
        "canonical_artifacts_mutated": False,
        "crs": "EPSG:25832",
        "arm1p_semantic_delta": {"base": rel(BASE_CONFIG), "prune_opa": [0.005, 0.05]},
        "arm1p_recording_only": {
            "densify_audit_buildings": TIMELINE_FULL_IDS,
            "event_types": ["duplicate", "split"],
        },
        "source_docs": [
            {"path": rel(path), "sha256": sha256_file(path)} for path in SOURCE_DOCS
        ],
        "predictions_locked": ["P-F", "P-F-prime", "P-G", "P-H"],
    }
    (RUN_DIR / "manifest.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def generate_configs(_args: argparse.Namespace) -> None:
    base = s2.yaml_load(BASE_CONFIG)
    if float(base.get("w_normal", -1)) != 0.05 or float(base.get("prune_opa", -1)) != 0.005:
        raise RuntimeError("Arm 1 base config no longer matches locked w_normal=0.05/prune_opa=0.005")
    rows: list[dict[str, Any]] = []
    for rep in [1, 2]:
        run_name = arm1p_run_name(rep)
        cfg = dict(base)
        cfg["prune_opa"] = 0.05
        cfg["final_prune_opa"] = 0.0
        cfg["out_dir"] = ws(CKPT_ROOT / run_name)
        cfg["densify_audit_footprints"] = cfg.get("seed_log_footprints")
        cfg["densify_audit_buildings"] = TIMELINE_FULL_IDS
        path = CONFIG_DIR / f"{run_name}.yaml"
        s2.yaml_dump(path, cfg)
        rows.append(
            {
                "config": rel(path),
                "run_name": run_name,
                "arm": "arm1p",
                "replicate": f"r{rep}",
                "seed": cfg.get("seed"),
                "max_iter": cfg.get("max_iter"),
                "w_normal": cfg.get("w_normal"),
                "w_distort": cfg.get("w_distort"),
                "prune_opa": cfg.get("prune_opa"),
                "final_prune_opa": cfg.get("final_prune_opa"),
                "depth_weight_floor": cfg.get("depth_weight_floor", ""),
                "w_mono_depth": cfg.get("w_mono_depth", 0.0),
                "semantic_delta_keys": "prune_opa",
                "recording_only_keys": "densify_audit_footprints;densify_audit_buildings;out_dir",
                "sha256": sha256_file(path),
            }
        )
    write_csv(CSV_INVENTORY, rows)
    write_csv(CSV_ISSUES, [], ["part", "severity", "message", "path", "created_utc"])
    write_manifest()
    print(json.dumps({"configs": len(rows), "inventory": rel(CSV_INVENTORY)}, ensure_ascii=False))


def configure_readout() -> None:
    ab = s2.ab
    ab.RUN_ID = RUN_ID
    ab.P2_RUN_DIR = RUN_DIR
    ab.P0_RUN_ID = P0_RUN_ID
    ab.P0_RUN_DIR = P0_RUN_DIR
    ab.RESULTS_ROOT = READOUT_ROOT
    ab.CKPT_ROOT = CKPT_ROOT
    ab.TRAIN_RUN_DIR = RUN_DIR
    ab.CANON_GATE_DIR = REPO / "phases/p0-audit/runs/e5p_gate_20260707_C001"
    ab.DATA_ROOT = rel(DATA_ROOT)
    ab.TORCH_EXTENSIONS = rel(TORCH_EXTENSIONS)
    ab.FIG_DIR = FIG_DIR / "readout"
    ab.REPORT_PATH = RUN_DIR / "readout_tmp.md"
    ab.COVERAGE_CSV = CSV_COVERAGE
    ab.FILTER_CSV = CSV_FILTER
    ab.METRICS_CSV = CSV_405_BUILDING
    ab.SUMMARY_CSV = CSV_READOUT_SUMMARY
    ab.TRADEOFF_CSV = CSV_READOUT_TRADEOFF
    ab.CASE_CSV = CSV_READOUT_CASES
    ab.INVENTORY_CSV = CSV_READOUT_INVENTORY
    ab.ISSUES_CSV = CSV_READOUT_ISSUES
    ab.RENDER_COVERAGE = REPO / "docs/e5_c001_s2p_render_readout_coverage.csv"
    ab.SETTINGS = [
        ab.Setting("base", "S2p canonical readout", min_obs=3, voxel=0.05, sor="on", sor_std=2.0)
    ]

    def selected_run_names(args: argparse.Namespace) -> list[str]:
        names = [arm1p_run_name(rep) for rep in [1, 2]]
        selected = getattr(args, "runs", None)
        if not selected:
            return names
        missing = sorted(set(selected) - set(names))
        if missing:
            raise RuntimeError(f"unknown S2p run names: {missing}")
        return [name for name in names if name in set(selected)]

    def source_for(setting: Any, run_name: str) -> Any:
        source = s2.ORIGINAL_AB_SOURCE_FOR(setting, run_name)
        repaired_root = REPAIRED_P0_RUN_DIR / setting.key
        repaired_status = repaired_root / "status" / f"{run_name}_run_1.csv"
        repaired_cityjson = repaired_root / "cityjson" / f"{run_name}_run_1.city.json"
        if repaired_status.exists() and repaired_cityjson.exists():
            source.status_path = repaired_status
            source.cityjson_path = repaired_cityjson
            source.source_badge = f"{setting.key}_405repair"
            source.readout = source.readout + "; 405 winding repair overlay"
        return source

    def write_readout_report(*_args: Any, **_kwargs: Any) -> None:
        ab.REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
        ab.REPORT_PATH.write_text(
            "# S2p readout tmp\n\nGenerated by redirected C001 readout harness.\n",
            encoding="utf-8",
        )

    ab.selected_run_names = selected_run_names
    ab.source_for = source_for
    ab.write_report = write_readout_report


def _evaluation_container(args: argparse.Namespace) -> None:
    configure_readout()
    if os.environ.get("E5_S2P_EVAL_CONTAINER") == "1":
        s2.ab.evaluate(args)
        return
    cmd = [
        "docker",
        "run",
        "--rm",
        "-i",
        "--user",
        f"{os.getuid()}:{os.getgid()}",
        "-e",
        "HOME=/tmp",
        "-e",
        "MPLCONFIGDIR=/tmp/matplotlib",
        "-e",
        "XDG_CACHE_HOME=/tmp",
        "-e",
        "E5_S2P_EVAL_CONTAINER=1",
        "-v",
        f"{REPO}:/workspace/JointBuildGS",
        "-w",
        "/workspace/JointBuildGS",
        "jointbuildgs-p0-tools:t0",
        "python3",
        "phases/p2-gsjso/scripts/e5_c001_s2p_interaction.py",
        "evaluate",
    ]
    if args.force:
        cmd.append("--force")
    if args.runs:
        cmd.extend(["--runs", *args.runs])
    s2.ab.run(cmd, log_path=RUN_DIR / "evaluate_container.log", check=True, quiet=False)


def readout_like(args: argparse.Namespace) -> None:
    configure_readout()
    if args.cmd in {"readout", "all"}:
        s2.ab.run_readout(args)
    if args.cmd in {"assemble", "all"}:
        s2.ab.run_assemble(args)
    if args.cmd in {"evaluate", "all"}:
        _evaluation_container(args)


def repair_405(args: argparse.Namespace) -> None:
    import e5_c001_405_repair as repair

    repair.RUN_ID = REPAIR_RUN_ID
    repair.REPAIR_ROOT = s2.P0_RUNS / REPAIR_RUN_ID
    repair.CSV_SUMMARY = CSV_405_REPAIR
    repair.CSV_BUILDING = REPO / "docs/e5_c001_s2p_405_repair_status_building.csv"
    repair.CSV_ISSUES = REPO / "docs/e5_c001_s2p_405_repair_issues.csv"
    repair.process(
        argparse.Namespace(
            source_run_id=[P0_RUN_ID],
            settings=["base"],
            include_factor=False,
            append=False,
            force=args.force,
        )
    )
    print(json.dumps({"repair_405": rel(CSV_405_REPAIR)}, ensure_ascii=False))


def train_one(args: argparse.Namespace) -> None:
    config = CONFIG_DIR / f"{args.run_name}.yaml"
    if not config.exists():
        raise FileNotFoundError(config)
    cmd = docker_base(args.gpu) + ["python", "-m", "src.stage2.train", "--config", rel(config)]
    log_path = TRAIN_LOG_ROOT / f"{args.run_name}.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    started = datetime.now(timezone.utc).isoformat()
    with log_path.open("w", encoding="utf-8") as log:
        header = (
            f"START_UTC={started}\nHOST_GPU={args.gpu}\nCONFIG={rel(config)}\n"
            f"COMMAND={' '.join(cmd)}\n"
        )
        log.write(header)
        log.flush()
        proc = subprocess.Popen(
            cmd,
            cwd=REPO,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            bufsize=1,
        )
        assert proc.stdout is not None
        for line in proc.stdout:
            print(line, end="", flush=True)
            log.write(line)
            log.flush()
        rc = int(proc.wait())
        ended = datetime.now(timezone.utc).isoformat()
        log.write(f"\nEND_UTC={ended}\nRETURN_CODE={rc}\n")
    print(json.dumps({"run_name": args.run_name, "gpu": args.gpu, "return_code": rc}, ensure_ascii=False))
    if rc != 0:
        raise SystemExit(rc)


def timeline_roofcrop(_args: argparse.Namespace) -> None:
    fps = s2.load_footprints(TIMELINE_IDS)
    rows: list[dict[str, Any]] = []
    for rep in [1, 2]:
        run_name = arm1p_run_name(rep)
        for step in [5000, 10000, 15000, 20000, 25000, "final"]:
            ckpt = checkpoint_path(run_name, step)
            for item in s2.gaussian_stats_for_ckpt(ckpt, fps, TIMELINE_IDS):
                rows.append(
                    {
                        "arm": "arm1p",
                        "replicate": f"r{rep}",
                        "run_name": run_name,
                        "step": 30000 if step == "final" else step,
                        "ckpt": rel(ckpt),
                        **{key: s2.fmt(value) for key, value in item.items()},
                    }
                )
    write_csv(
        CSV_TIMELINE,
        rows,
        [
            "arm",
            "replicate",
            "run_name",
            "step",
            "ckpt",
            "building_id",
            "n_gaussians_in_footprint",
            "z_p50",
            "z_std",
            "opacity_p50",
        ],
    )
    print(json.dumps({"timeline": rel(CSV_TIMELINE), "rows": len(rows)}, ensure_ascii=False))


def densify_log(_args: argparse.Namespace) -> None:
    sums: dict[tuple[str, str, int, str], dict[str, int]] = defaultdict(
        lambda: {"duplicate_events": 0, "split_events": 0, "total_events": 0, "audit_steps": 0}
    )
    for rep in [1, 2]:
        run_name = arm1p_run_name(rep)
        source = CKPT_ROOT / run_name / "audit/densify_events.csv"
        for row in read_csv(source):
            iteration = int(row["iteration"])
            interval_end = max(5000, int(math.ceil(iteration / 5000.0) * 5000))
            key = (run_name, f"r{rep}", interval_end, row["building_id"])
            for field in ["duplicate_events", "split_events", "total_events"]:
                sums[key][field] += int(row[field])
            sums[key]["audit_steps"] += 1
    rows = []
    for (run_name, replicate, interval_end, building_id), values in sorted(sums.items()):
        rows.append(
            {
                "arm": "arm1p",
                "replicate": replicate,
                "run_name": run_name,
                "interval_start_exclusive": interval_end - 5000,
                "interval_end_inclusive": interval_end,
                "building_id": building_id,
                **values,
                "source": rel(CKPT_ROOT / run_name / "audit/densify_events.csv"),
            }
        )
    write_csv(
        CSV_DENSIFY,
        rows,
        [
            "arm",
            "replicate",
            "run_name",
            "interval_start_exclusive",
            "interval_end_inclusive",
            "building_id",
            "duplicate_events",
            "split_events",
            "total_events",
            "audit_steps",
            "source",
        ],
    )
    print(json.dumps({"densify_log": rel(CSV_DENSIFY), "rows": len(rows)}, ensure_ascii=False))


def _opacity_sources() -> list[tuple[str, str, str, Path]]:
    sources = [
        (
            "corrected_recheck",
            "w100_p050_no_normal",
            "r1",
            REPO
            / "results/tum_transfer/e5_corrected_s1_recheck/C001/runs/gs_e5_C001_corrected_s1_preprune_keepall_dense_r1/ckpt/final.pt",
        ),
        (
            "s1_full",
            "w100_p005_no_normal",
            "r1",
            REPO
            / "results/tum_transfer/e5_s1_full_factor/C001/runs/gs_e5_C001_s1fac_w100_p005_dense_r1/ckpt/final.pt",
        ),
        (
            "s1_full",
            "w240_p050_no_normal",
            "r1",
            REPO
            / "results/tum_transfer/e5_s1_full_factor/C001/runs/gs_e5_C001_s1fac_w240_p050_dense_r1/ckpt/final.pt",
        ),
        (
            "s1_full",
            "w240_p005_no_normal",
            "r1",
            REPO
            / "results/tum_transfer/e5_s1_full_factor/C001/runs/gs_e5_C001_s1fac_w240_p005_dense_r1/ckpt/final.pt",
        ),
    ]
    s2_root = REPO / "results/tum_transfer/e5_s2_direction_position/C001/runs"
    for arm in ["arm0", "arm1", "arm2"]:
        for rep in [1, 2]:
            run_name = f"gs_e5_C001_s2_{arm}_dense_r{rep}"
            sources.append(("s2", f"{arm}_p005_normal", f"r{rep}", s2_root / run_name / "ckpt/final.pt"))
    for rep in [1, 2]:
        run_name = arm1p_run_name(rep)
        sources.append(("s2p", "arm1p_p050_normal", f"r{rep}", checkpoint_path(run_name, "final")))
        arm3_name = f"gs_e5_C001_s2p_arm3_dense_r{rep}"
        sources.append(("s2p", "arm3_p005_normal_mono", f"r{rep}", CKPT_ROOT / arm3_name / "ckpt/final.pt"))
    return sources


def sheet_opacity_dist(_args: argparse.Namespace) -> None:
    import torch

    rows: list[dict[str, Any]] = []
    for family, cell, replicate, checkpoint in _opacity_sources():
        if not checkpoint.exists():
            continue
        state = torch.load(checkpoint, map_location="cpu", weights_only=False)["state_dict"]
        z = state["means"].detach().cpu().numpy()[:, 2].astype(np.float64) + s2.SHIFT_UTM[2]
        opacity = torch.sigmoid(state["opacities_raw"].detach().cpu().float()).numpy()
        for band, z_min, z_max in [("floater_595_615", 595.0, 615.0), ("high_655_670", 655.0, 670.0)]:
            in_band = (z >= z_min) & (z <= z_max)
            values = opacity[in_band]
            bins = [
                ("gt_0p5", values > 0.5),
                ("0p1_to_0p5", (values >= 0.1) & (values <= 0.5)),
                ("lt_0p1", values < 0.1),
            ]
            total = int(len(values))
            for opacity_bin, mask in bins:
                count = int(np.count_nonzero(mask))
                rows.append(
                    {
                        "family": family,
                        "cell": cell,
                        "replicate": replicate,
                        "band": band,
                        "z_min": z_min,
                        "z_max": z_max,
                        "opacity_bin": opacity_bin,
                        "n_gaussians": count,
                        "fraction_of_band": s2.fmt(count / total if total else None, 8),
                        "band_total": total,
                        "opacity_p50": s2.fmt(float(np.median(values)) if total else None),
                        "high_opacity_core_present": str(bool(np.any(values > 0.5))).lower(),
                        "ckpt": rel(checkpoint),
                    }
                )
    write_csv(CSV_SHEET_OPACITY, rows)
    _plot_sheet_opacity(rows)
    print(json.dumps({"sheet_opacity_dist": rel(CSV_SHEET_OPACITY), "rows": len(rows)}, ensure_ascii=False))


def _plot_sheet_opacity(rows: list[dict[str, Any]]) -> None:
    part = [row for row in rows if row["band"] == "floater_595_615"]
    keys = sorted({(row["family"], row["cell"], row["replicate"]) for row in part})
    if not keys:
        return
    figure_dir = FIG_DIR / "sheet_opacity_dist"
    figure_dir.mkdir(parents=True, exist_ok=True)
    bins = ["gt_0p5", "0p1_to_0p5", "lt_0p1"]
    colors = {"gt_0p5": "#1F4E79", "0p1_to_0p5": "#D6A33A", "lt_0p1": "#C9CDD2"}
    labels = {"gt_0p5": ">0.5", "0p1_to_0p5": "0.1-0.5", "lt_0p1": "<0.1"}
    fig, ax = plt.subplots(figsize=(10.5, max(5.0, 0.42 * len(keys))), constrained_layout=True)
    left = np.zeros(len(keys), dtype=np.float64)
    for opacity_bin in bins:
        values = []
        for key in keys:
            match = [
                row
                for row in part
                if (row["family"], row["cell"], row["replicate"]) == key
                and row["opacity_bin"] == opacity_bin
            ]
            values.append(_finite_float(match[0]["fraction_of_band"]) if match else 0.0)
        ax.barh(range(len(keys)), values, left=left, color=colors[opacity_bin], label=labels[opacity_bin])
        left += np.asarray(values, dtype=np.float64)
    ax.set_yticks(range(len(keys)))
    ax.set_yticklabels([f"{family}:{cell}:{rep}" for family, cell, rep in keys], fontsize=7)
    ax.set_xlim(0, 1)
    ax.set_xlabel("fraction of Gaussians in z=595-615 m band")
    ax.set_title("Floater-layer opacity distribution")
    ax.grid(axis="x", color="#DDDDDD", linewidth=0.6)
    ax.legend(loc="lower right", fontsize=8)
    fig.savefig(figure_dir / "sheet_opacity_distribution.png", dpi=190)
    plt.close(fig)


def _rend_dist_from_audit(run_name: str, run_root: Path) -> dict[str, Any]:
    audit_path = run_root / run_name / "audit/loss_grad_norms.csv"
    effective_path = run_root / run_name / "effective_config.json"
    audit = read_csv(audit_path)
    denominator = 1.0
    if effective_path.exists():
        denominator = float(
            json.loads(effective_path.read_text(encoding="utf-8")).get("distort_norm_denominator", 1.0)
            or 1.0
        )
    values = [
        value * denominator
        for value in (_finite_float(row.get("raw_loss")) for row in audit if row.get("component") == "distort")
        if value is not None
    ][-10:]
    return {
        "rend_dist_mean_tail_m": s2.fmt(float(np.mean(values)) if values else None),
        "rend_dist_p50_tail_m": s2.fmt(float(np.median(values)) if values else None),
        "audit_rows_tail": len(values),
        "denominator": s2.fmt(denominator),
        "audit_csv": rel(audit_path),
    }


def twin_rend_dist(_args: argparse.Namespace) -> None:
    s1_root = REPO / "results/tum_transfer/e5_s1_full_factor/C001/runs"
    s2_root = REPO / "results/tum_transfer/e5_s2_direction_position/C001/runs"
    specs = [
        ("no_normal", "w100_p005", "r1", "gs_e5_C001_s1fac_w100_p005_dense_r1", s1_root),
        ("no_normal", "w240_p005", "r1", "gs_e5_C001_s1fac_w240_p005_dense_r1", s1_root),
        ("normal", "arm1", "r1", "gs_e5_C001_s2_arm1_dense_r1", s2_root),
        ("normal", "arm1", "r2", "gs_e5_C001_s2_arm1_dense_r2", s2_root),
    ]
    rows = []
    for normal_state, cell, replicate, run_name, root in specs:
        rows.append(
            {
                "normal_state": normal_state,
                "cell": cell,
                "replicate": replicate,
                "run_name": run_name,
                **_rend_dist_from_audit(run_name, root),
                "reconstruction": "tail raw_loss * distort_norm_denominator; same S2 method",
            }
        )
    write_csv(CSV_TWIN_REND, rows)
    print(json.dumps({"twin_rend_dist": rel(CSV_TWIN_REND), "rows": len(rows)}, ensure_ascii=False))


def _load_depth_anything_v2(device: Any) -> tuple[Any, str]:
    import torch

    if not DA_REPO.exists():
        raise FileNotFoundError(f"Depth Anything V2 repository missing: {DA_REPO}")
    if str(DA_REPO) not in sys.path:
        sys.path.insert(0, str(DA_REPO))
    from depth_anything_v2.dpt import DepthAnythingV2

    candidates = [
        {
            "encoder": "vitl",
            "features": 256,
            "out_channels": [256, 512, 1024, 1024],
            "label": "Depth Anything V2 Large vitl",
            "file": "depth_anything_v2_vitl.pth",
            "url": "https://huggingface.co/depth-anything/Depth-Anything-V2-Large/resolve/main/depth_anything_v2_vitl.pth",
        },
        {
            "encoder": "vitb",
            "features": 128,
            "out_channels": [96, 192, 384, 768],
            "label": "Depth Anything V2 Base vitb",
            "file": "depth_anything_v2_vitb.pth",
            "url": "https://huggingface.co/depth-anything/Depth-Anything-V2-Base/resolve/main/depth_anything_v2_vitb.pth",
        },
    ]
    errors: list[str] = []
    checkpoint_dir = MONO_V2_ROOT / "checkpoints"
    checkpoint_dir.mkdir(parents=True, exist_ok=True)
    for index, spec in enumerate(candidates):
        try:
            checkpoint = checkpoint_dir / str(spec["file"])
            if checkpoint.exists():
                state = torch.load(checkpoint, map_location="cpu", weights_only=False)
            else:
                state = torch.hub.load_state_dict_from_url(
                    str(spec["url"]),
                    model_dir=str(checkpoint_dir),
                    file_name=checkpoint.name,
                    map_location="cpu",
                )
            model = DepthAnythingV2(
                encoder=str(spec["encoder"]),
                features=int(spec["features"]),
                out_channels=list(spec["out_channels"]),
            )
            model.load_state_dict(state)
            model.to(device).eval()
            if index == 1:
                append_issue("A-1p", "warn", "Depth Anything V2 Large unavailable; used Base fallback", checkpoint)
            return model, str(spec["label"])
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{spec['label']}: {type(exc).__name__}: {exc}")
            if index == 0:
                append_issue("A-1p", "warn", f"Large load/download failed; trying Base: {exc}")
    raise RuntimeError("; ".join(errors))


def _write_monodepth_reject(reason: str) -> None:
    RUN_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "decision": "exclude_arm3",
        "arm3_mode": "excluded",
        "reason": reason,
        "created_utc": datetime.now(timezone.utc).isoformat(),
    }
    (RUN_DIR / "monodepth_decision_v2.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def _infer_monodepth_v2_container(args: argparse.Namespace) -> None:
    import cv2
    import torch

    from src.stage2.dataloader import ColmapDataset

    device = torch.device(args.device if torch.cuda.is_available() else "cpu")
    MONO_V2_DEPTH_DIR.mkdir(parents=True, exist_ok=True)
    figure_dir = FIG_DIR / "monodepth_precheck_v2"
    figure_dir.mkdir(parents=True, exist_ok=True)
    try:
        model, backend = _load_depth_anything_v2(device)
    except Exception as exc:  # noqa: BLE001
        reason = f"Depth Anything V2 Large and Base unavailable: {type(exc).__name__}: {exc}"
        append_issue("A-1p", "error", reason, MONO_V2_ROOT)
        _write_monodepth_reject(reason)
        print(json.dumps({"decision": "exclude_arm3", "reason": reason}, ensure_ascii=False))
        return

    ds = ColmapDataset(
        root=str(DATA_ROOT),
        downscale=1.0,
        load_depth=True,
        load_normal=False,
        load_semantic=False,
    )
    rows: list[dict[str, Any]] = []
    gallery: list[tuple[str, np.ndarray]] = []
    for idx in range(len(ds)):
        batch = ds[idx]
        image_name = str(batch["name"])
        stem = Path(image_name).stem
        image_path = DATA_ROOT / "images" / image_name
        image_bgr = cv2.imread(str(image_path), cv2.IMREAD_COLOR)
        if image_bgr is None:
            append_issue("A-1p", "warn", "image read failed", image_path)
            continue
        raw = model.infer_image(image_bgr, input_size=518).astype(np.float32)
        h, w = image_bgr.shape[:2]
        if raw.shape != (h, w):
            raw = cv2.resize(raw, (w, h), interpolation=cv2.INTER_CUBIC)
        mvs = batch["depth"].numpy().astype(np.float32)
        mvs_mask = batch["depth_mask"].numpy().astype(bool)
        align_a, align_b, aligned = s2._fit_scale_shift(raw, mvs, mvs_mask)
        residual = aligned - mvs
        valid = mvs_mask & np.isfinite(residual)
        output = MONO_V2_DEPTH_DIR / f"{stem}.npy"
        np.save(output, np.where(np.isfinite(aligned) & (aligned > 0), aligned, 0).astype(np.float32))
        rows.append(
            {
                "image_idx": idx,
                "image_name": image_name,
                "backend": backend,
                "align_a": s2.fmt(align_a, 8),
                "align_b": s2.fmt(align_b, 8),
                "mvs_valid_pixels": int(np.count_nonzero(mvs_mask)),
                "residual_abs_median_m": s2.fmt(float(np.median(np.abs(residual[valid]))) if np.any(valid) else None),
                "residual_abs_p90_m": s2.fmt(float(np.percentile(np.abs(residual[valid]), 90)) if np.any(valid) else None),
                "warp_amp_plane_m": s2.fmt(s2._polyfit_amp(residual, valid, 1)),
                "warp_amp_quadratic_m": s2.fmt(s2._polyfit_amp(residual, valid, 2)),
                "metric_depth": rel(output),
            }
        )
        if len(gallery) < 8 and np.any(valid):
            lo, hi = np.percentile(residual[valid], [2, 98])
            vis = np.full_like(residual, np.nan, dtype=np.float32)
            vis[valid] = np.clip(residual[valid], lo, hi)
            gallery.append((stem, vis))
        if (idx + 1) % 25 == 0:
            print(
                json.dumps({"stage": "A-1p-large", "done": idx + 1, "total": len(ds)}, ensure_ascii=False),
                flush=True,
            )

    write_csv(CSV_MONO_V2_IMAGE, rows)
    write_csv(
        CSV_MONO_V2_RUNTIME,
        [
            {
                "requested_backend": "Depth Anything V2 Large vitl",
                "actual_backend": backend,
                "device": str(device),
                "torch": torch.__version__,
                "frames": len(rows),
                "depth_dir": rel(MONO_V2_DEPTH_DIR),
            }
        ],
    )
    if gallery:
        fig, axes = plt.subplots(2, 4, figsize=(12, 6), constrained_layout=True)
        for ax, (stem, residual) in zip(axes.ravel(), gallery):
            finite = residual[np.isfinite(residual)]
            limit = float(np.percentile(np.abs(finite), 98)) if finite.size else 1.0
            ax.imshow(residual, cmap="coolwarm", vmin=-max(limit, 1e-6), vmax=max(limit, 1e-6))
            ax.set_title(stem[-16:], fontsize=8)
            ax.axis("off")
        fig.suptitle("A-1p aligned mono-depth residuals (m)", fontsize=11)
        fig.savefig(figure_dir / "alignment_residual_gallery.png", dpi=180)
        plt.close(fig)
    score_monodepth_v2(argparse.Namespace(views_per_building=args.views_per_building))
    print(json.dumps({"monodepth_images": len(rows), "backend": backend}, ensure_ascii=False))


def infer_monodepth_v2(args: argparse.Namespace) -> None:
    if os.environ.get("E5_S2P_MONO_CONTAINER") == "1":
        _infer_monodepth_v2_container(args)
        return
    cmd = docker_base(args.gpu)
    cmd[cmd.index(DEV_IMAGE):cmd.index(DEV_IMAGE)] = ["-e", "E5_S2P_MONO_CONTAINER=1"]
    cmd += [
        "python",
        "phases/p2-gsjso/scripts/e5_c001_s2p_interaction.py",
        "infer-monodepth-v2",
        "--device",
        "cuda:0",
        "--views-per-building",
        str(args.views_per_building),
    ]
    log_path = RUN_DIR / "monodepth_precheck_v2.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("w", encoding="utf-8") as log:
        proc = subprocess.Popen(
            cmd,
            cwd=REPO,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            bufsize=1,
        )
        assert proc.stdout is not None
        for line in proc.stdout:
            print(line, end="", flush=True)
            log.write(line)
            log.flush()
        rc = int(proc.wait())
    if rc != 0:
        append_issue("A-1p", "error", f"mono-depth v2 container returned {rc}", log_path)
        raise SystemExit(rc)


def _visible_views(ds: Any, fp: dict[str, Any], refs: list[Any], limit: int) -> list[dict[str, Any]]:
    x0, y0, x1, y1 = fp["bbox"]
    z = s2.strips.reference_z(refs, fp)
    points_utm = np.asarray(
        [
            [x0, y0, z],
            [x0, y1, z],
            [x1, y1, z],
            [x1, y0, z],
            [(x0 + x1) / 2.0, (y0 + y1) / 2.0, z],
        ],
        dtype=np.float64,
    )
    candidates: list[dict[str, Any]] = []
    for view_idx in range(len(ds)):
        batch = ds[view_idx]
        height, width = int(batch["height"]), int(batch["width"])
        uv, depth = s2._project_local(
            points_utm - s2.SHIFT_UTM,
            batch["w2c"].numpy(),
            batch["K"].numpy(),
        )
        if np.count_nonzero(depth > 0) < 4:
            continue
        u0, v0 = np.nanmin(uv[:, 0]), np.nanmin(uv[:, 1])
        u1, v1 = np.nanmax(uv[:, 0]), np.nanmax(uv[:, 1])
        if u1 < 0 or v1 < 0 or u0 >= width or v0 >= height:
            continue
        clipped_area = max(0.0, min(u1, width - 1) - max(u0, 0)) * max(
            0.0, min(v1, height - 1) - max(v0, 0)
        )
        if clipped_area <= 20.0:
            continue
        margin = 36
        crop = (
            max(0, int(u0) - margin),
            max(0, int(v0) - margin),
            min(width, int(u1) + margin),
            min(height, int(v1) + margin),
        )
        crop_area = max(1, (crop[2] - crop[0]) * (crop[3] - crop[1]))
        candidates.append(
            {
                "view_idx": view_idx,
                "crop": crop,
                "projected_area_px2": clipped_area,
                "visibility_score": clipped_area / crop_area,
            }
        )
    candidates.sort(
        key=lambda row: (float(row["visibility_score"]), float(row["projected_area_px2"])),
        reverse=True,
    )
    return candidates[:limit]


def _roof_samples(refs: list[Any]) -> np.ndarray:
    samples: list[np.ndarray] = []
    for surface in refs:
        xy = s2.eight.sample_polygon_points(surface.polygon, spacing=0.75, limit=250)
        if len(xy):
            samples.append(np.column_stack([xy[:, 0], xy[:, 1], surface.z_at(xy[:, 0], xy[:, 1])]))
    return np.vstack(samples) if samples else np.zeros((0, 3), dtype=np.float64)


def _finite_float(value: Any) -> float | None:
    parsed = s2.num(value)
    return parsed if parsed is not None and math.isfinite(parsed) else None


def score_monodepth_v2(args: argparse.Namespace) -> None:
    from src.stage2.dataloader import ColmapDataset

    target_ids = s2.GOOD6 + s2.TEXTURELESS_OBS3 + s2.GS_FAIL5
    references = s2.eight.parse_lod2_roofs(
        s2.eight.LOD2_DIR, {s2.full_id(short_id) for short_id in target_ids}
    )
    footprints = s2.strips.load_footprints(target_ids)
    ds = ColmapDataset(
        root=str(DATA_ROOT),
        downscale=1.0,
        load_depth=True,
        load_normal=False,
        load_semantic=False,
    )
    view_rows: list[dict[str, Any]] = []
    building_rows: list[dict[str, Any]] = []
    for short_id in target_ids:
        building_id = s2.full_id(short_id)
        refs = references.get(building_id, [])
        footprint = footprints.get(building_id)
        if not refs or footprint is None:
            append_issue("A-1p", "warn", "reference roof or footprint missing", building_id)
            continue
        samples_utm = _roof_samples(refs)
        visible = _visible_views(ds, footprint, refs, int(args.views_per_building))
        ref_span = (
            float(np.percentile(samples_utm[:, 2], 90) - np.percentile(samples_utm[:, 2], 10))
            if len(samples_utm)
            else None
        )
        for rank, candidate in enumerate(visible, start=1):
            view_idx = int(candidate["view_idx"])
            crop = tuple(candidate["crop"])
            batch = ds[view_idx]
            image_name = str(batch["name"])
            depth_path = MONO_V2_DEPTH_DIR / f"{Path(image_name).stem}.npy"
            if not depth_path.exists() or not len(samples_utm):
                continue
            mono = np.load(depth_path)
            uv, roof_depth = s2._project_local(
                samples_utm - s2.SHIFT_UTM,
                batch["w2c"].numpy(),
                batch["K"].numpy(),
            )
            height, width = mono.shape
            u = np.rint(uv[:, 0]).astype(int)
            v = np.rint(uv[:, 1]).astype(int)
            inside = (
                (roof_depth > 0)
                & (u >= 0)
                & (u < width)
                & (v >= 0)
                & (v < height)
            )
            if np.any(inside):
                sampled_depth = mono[v[inside], u[inside]]
                finite = np.isfinite(sampled_depth) & (sampled_depth > 0)
                selected = np.where(inside)[0][finite]
                sampled_depth = sampled_depth[finite]
            else:
                selected = np.asarray([], dtype=int)
                sampled_depth = np.asarray([], dtype=np.float32)
            if not len(sampled_depth):
                continue
            mono_world = s2.camera_depth_to_world(
                uv[selected], sampled_depth, batch["w2c"].numpy(), batch["K"].numpy()
            )
            mono_ref_z = mono_world[:, 2] + s2.ELLIP_TO_REF_SHIFT_M
            height_error = mono_ref_z - samples_utm[selected, 2]
            depth_error = sampled_depth - roof_depth[selected]
            crop_depth = mono[crop[1] : crop[3], crop[0] : crop[2]]
            crop_valid = crop_depth[np.isfinite(crop_depth) & (crop_depth > 0)]
            view_rows.append(
                {
                    "building_id": building_id,
                    "group_new": s2.group_label(short_id),
                    "view_rank": rank,
                    "view_idx": view_idx,
                    "image_name": image_name,
                    "visibility_score": s2.fmt(candidate["visibility_score"], 8),
                    "projected_area_px2": s2.fmt(candidate["projected_area_px2"], 2),
                    "projected_roof_samples": len(sampled_depth),
                    "roof_height_error_abs_median_m": s2.fmt(float(np.median(np.abs(height_error)))),
                    "roof_height_error_abs_p90_m": s2.fmt(float(np.percentile(np.abs(height_error), 90))),
                    "signed_height_error_median_m": s2.fmt(float(np.median(height_error))),
                    "roof_depth_error_abs_median_m": s2.fmt(float(np.median(np.abs(depth_error)))),
                    "mono_crop_depth_step_p90_p10_m": s2.fmt(
                        float(np.percentile(crop_valid, 90) - np.percentile(crop_valid, 10))
                        if len(crop_valid)
                        else None
                    ),
                    "ref_roof_z_span_p90_p10_m": s2.fmt(ref_span),
                    "metric_depth": rel(depth_path),
                }
            )
        part = [row for row in view_rows if row["building_id"] == building_id]
        height_medians = [
            value
            for value in (_finite_float(row["roof_height_error_abs_median_m"]) for row in part)
            if value is not None
        ]
        height_p90s = [
            value
            for value in (_finite_float(row["roof_height_error_abs_p90_m"]) for row in part)
            if value is not None
        ]
        signed = [
            value
            for value in (_finite_float(row["signed_height_error_median_m"]) for row in part)
            if value is not None
        ]
        mono_steps = [
            value
            for value in (_finite_float(row["mono_crop_depth_step_p90_p10_m"]) for row in part)
            if value is not None
        ]
        building_rows.append(
            {
                "building_id": building_id,
                "group_new": s2.group_label(short_id),
                "views_requested": int(args.views_per_building),
                "visible_views_selected": len(visible),
                "views_scored": len(height_medians),
                "roof_height_error_abs_median_m": s2.fmt(float(np.median(height_medians)) if height_medians else None),
                "roof_height_error_abs_p90_viewmedian_m": s2.fmt(float(np.median(height_p90s)) if height_p90s else None),
                "signed_height_error_viewmedian_m": s2.fmt(float(np.median(signed)) if signed else None),
                "mono_crop_depth_step_viewmedian_m": s2.fmt(float(np.median(mono_steps)) if mono_steps else None),
                "ref_roof_z_span_p90_p10_m": s2.fmt(ref_span),
                "view_indices": ";".join(str(row["view_idx"]) for row in part),
            }
        )

    write_csv(CSV_MONO_V2_VIEW, view_rows)
    values = [
        value
        for value in (_finite_float(row["roof_height_error_abs_median_m"]) for row in building_rows)
        if value is not None
    ]
    pairs = [
        (
            _finite_float(row["mono_crop_depth_step_viewmedian_m"]),
            _finite_float(row["ref_roof_z_span_p90_p10_m"]),
        )
        for row in building_rows
    ]
    pairs = [(x, y) for x, y in pairs if x is not None and y is not None]
    resolution_corr: float | None = None
    if len(pairs) >= 3:
        x = np.asarray([pair[0] for pair in pairs], dtype=np.float64)
        y = np.asarray([pair[1] for pair in pairs], dtype=np.float64)
        if float(np.std(x)) > 1e-9 and float(np.std(y)) > 1e-9:
            resolution_corr = float(np.corrcoef(x, y)[0, 1])
    under_observed = [
        str(row["building_id"]) for row in building_rows if int(row["views_scored"]) < 3
    ]
    resolution_failed = bool(under_observed) or resolution_corr is None or resolution_corr <= 0.0
    overall_median = float(np.median(values)) if values else None
    if overall_median is None:
        decision = "exclude_arm3"
        arm3_mode = "excluded"
        reason = "no finite building-level direct scores"
    elif resolution_failed:
        decision = "exclude_arm3"
        arm3_mode = "excluded"
        reason = (
            f"building resolution failed: corr={resolution_corr}; "
            f"buildings_with_lt3_views={under_observed}"
        )
    elif overall_median <= 3.0:
        decision = "arm3_absolute_go"
        arm3_mode = "absolute_aligned_depth"
        reason = f"building-level roof direct-score median {overall_median:.3f} m <= 3 m"
    elif overall_median <= 8.0:
        decision = "arm3_pearson_go"
        arm3_mode = "pearson_patch"
        reason = f"building-level roof direct-score median {overall_median:.3f} m in 3-8 m band"
    else:
        decision = "exclude_arm3"
        arm3_mode = "excluded"
        reason = f"building-level roof direct-score median {overall_median:.3f} m > 8 m"
    for row in building_rows:
        row["overall_building_median_m"] = s2.fmt(overall_median)
        row["building_resolution_pearson"] = s2.fmt(resolution_corr)
        row["resolution_failure_operationalization"] = "any building <3 scored views OR nonfinite/nonpositive Pearson"
        row["arm3_decision"] = decision
        row["arm3_mode"] = arm3_mode
    write_csv(CSV_MONO_V2, building_rows)
    payload = {
        "decision": decision,
        "arm3_mode": arm3_mode,
        "reason": reason,
        "overall_building_median_m": overall_median,
        "building_resolution_pearson": resolution_corr,
        "buildings_with_lt3_scored_views": under_observed,
        "views_per_building": int(args.views_per_building),
        "building_count": len(values),
        "resolution_failure_operationalization": "any building <3 scored views OR nonfinite/nonpositive Pearson",
        "created_utc": datetime.now(timezone.utc).isoformat(),
    }
    RUN_DIR.mkdir(parents=True, exist_ok=True)
    (RUN_DIR / "monodepth_decision_v2.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    _plot_monodepth_v2(building_rows, view_rows, overall_median)
    print(json.dumps(payload, ensure_ascii=False))


def _plot_monodepth_v2(
    building_rows: list[dict[str, Any]], view_rows: list[dict[str, Any]], overall_median: float | None
) -> None:
    figure_dir = FIG_DIR / "monodepth_precheck_v2"
    figure_dir.mkdir(parents=True, exist_ok=True)
    ordered = sorted(
        building_rows,
        key=lambda row: _finite_float(row["roof_height_error_abs_median_m"]) or float("inf"),
    )
    fig, ax = plt.subplots(figsize=(9.5, 6.6), constrained_layout=True)
    for y_index, row in enumerate(ordered):
        building_id = str(row["building_id"])
        views = [item for item in view_rows if item["building_id"] == building_id]
        x_views = [
            value
            for value in (_finite_float(item["roof_height_error_abs_median_m"]) for item in views)
            if value is not None
        ]
        ax.scatter(x_views, [y_index] * len(x_views), color="#9DB7D5", s=20, alpha=0.8)
        median = _finite_float(row["roof_height_error_abs_median_m"])
        if median is not None:
            ax.scatter([median], [y_index], color="#1F4E79", s=46, marker="D", zorder=3)
    ax.axvline(3.0, color="#B7831B", linestyle="--", linewidth=1.2, label="3 m branch")
    ax.axvline(8.0, color="#7A7A7A", linestyle=":", linewidth=1.2, label="8 m branch")
    if overall_median is not None:
        ax.axvline(overall_median, color="#202020", linewidth=1.4, label=f"all-building median {overall_median:.2f} m")
    ax.set_yticks(range(len(ordered)))
    ax.set_yticklabels([s2.short_id(str(row["building_id"])) for row in ordered], fontsize=8)
    ax.set_xlim(left=0)
    ax.set_xlabel("absolute roof-height error per view (m)")
    ax.set_ylabel("building")
    ax.set_title("A-1p multi-view roof direct score")
    ax.grid(axis="x", color="#D9D9D9", linewidth=0.6)
    ax.legend(fontsize=8, loc="lower right")
    fig.savefig(figure_dir / "roof_direct_score_multiview.png", dpi=190)
    plt.close(fig)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("generate-configs")
    train = sub.add_parser("train-one")
    train.add_argument("--run-name", required=True)
    train.add_argument("--gpu", default="0")
    sub.add_parser("timeline-roofcrop")
    sub.add_parser("densify-log")
    sub.add_parser("sheet-opacity-dist")
    sub.add_parser("twin-rend-dist")
    mono = sub.add_parser("infer-monodepth-v2")
    mono.add_argument("--gpu", default="1")
    mono.add_argument("--device", default="cuda:0")
    mono.add_argument("--views-per-building", type=int, default=5)
    score = sub.add_parser("score-monodepth-v2")
    score.add_argument("--views-per-building", type=int, default=5)
    for name in ["readout", "assemble", "evaluate", "all"]:
        readout = sub.add_parser(name)
        readout.add_argument("--settings", nargs="*", default=["base"])
        readout.add_argument("--runs", nargs="*", default=None)
        readout.add_argument("--force", action="store_true")
        readout.add_argument("--data-root", default=rel(DATA_ROOT))
        readout.add_argument("--torch-extensions", default=rel(TORCH_EXTENSIONS))
        readout.add_argument("--gpu", default="0")
        readout.add_argument("--buffer-m", type=float, default=20.0)
    repair = sub.add_parser("repair-405")
    repair.add_argument("--force", action="store_true")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if args.cmd == "generate-configs":
        generate_configs(args)
    elif args.cmd == "train-one":
        train_one(args)
    elif args.cmd == "timeline-roofcrop":
        timeline_roofcrop(args)
    elif args.cmd == "densify-log":
        densify_log(args)
    elif args.cmd == "sheet-opacity-dist":
        sheet_opacity_dist(args)
    elif args.cmd == "twin-rend-dist":
        twin_rend_dist(args)
    elif args.cmd == "infer-monodepth-v2":
        infer_monodepth_v2(args)
    elif args.cmd == "score-monodepth-v2":
        score_monodepth_v2(args)
    elif args.cmd in {"readout", "assemble", "evaluate", "all"}:
        readout_like(args)
    elif args.cmd == "repair-405":
        repair_405(args)


if __name__ == "__main__":
    main()
