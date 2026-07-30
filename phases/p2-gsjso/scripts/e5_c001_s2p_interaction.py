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
REPORT_PATH = REPO / "docs/experiments/e5_c001_s2p/reports/W_E5_C001_S2p_상호작용.md"
CSV_INVENTORY = REPO / "docs/experiments/e5_c001_s2p/tables/e5_c001_s2p_inventory.csv"
CSV_TIMELINE = REPO / "docs/experiments/e5_c001_s2p/tables/e5_c001_s2p_timeline_roofcrop.csv"
CSV_DENSIFY = REPO / "docs/experiments/e5_c001_s2p/tables/e5_c001_s2p_densify_log.csv"
CSV_ISSUES = REPO / "docs/experiments/e5_c001_s2p/tables/e5_c001_s2p_issues.csv"
CSV_MONO_V2 = REPO / "docs/experiments/e5_c001_s2p/tables/e5_c001_s2p_monodepth_precheck_v2.csv"
CSV_MONO_V2_IMAGE = REPO / "docs/experiments/e5_c001_s2p/tables/e5_c001_s2p_monodepth_precheck_v2_image.csv"
CSV_MONO_V2_VIEW = REPO / "docs/experiments/e5_c001_s2p/tables/e5_c001_s2p_monodepth_precheck_v2_view.csv"
CSV_MONO_V2_RUNTIME = REPO / "docs/experiments/e5_c001_s2p/tables/e5_c001_s2p_monodepth_runtime_v2.csv"
CSV_SHEET_OPACITY = REPO / "docs/experiments/e5_c001_s2p/tables/e5_c001_s2p_sheet_opacity_dist.csv"
CSV_TWIN_REND = REPO / "docs/experiments/e5_c001_s2p/tables/e5_c001_s2p_twin_rend_dist.csv"
CSV_COVERAGE = REPO / "docs/experiments/e5_c001_s2p/tables/e5_c001_s2p_coverage.csv"
CSV_FILTER = REPO / "docs/experiments/e5_c001_s2p/tables/e5_c001_s2p_filter_contrib.csv"
CSV_405_BUILDING = REPO / "docs/experiments/e5_c001_s2p/tables/e5_c001_s2p_405_rescore_building.csv"
CSV_405_REPAIR = REPO / "docs/experiments/e5_c001_s2p/tables/e5_c001_s2p_405_rescore.csv"
CSV_READOUT_SUMMARY = REPO / "docs/experiments/e5_c001_s2p/tables/e5_c001_s2p_summary.csv"
CSV_READOUT_TRADEOFF = REPO / "docs/experiments/e5_c001_s2p/tables/e5_c001_s2p_tradeoff.csv"
CSV_READOUT_CASES = REPO / "docs/experiments/e5_c001_s2p/tables/e5_c001_s2p_representative_buildings.csv"
CSV_READOUT_INVENTORY = REPO / "docs/experiments/e5_c001_s2p/tables/e5_c001_s2p_readout_inventory.csv"
CSV_READOUT_ISSUES = REPO / "docs/experiments/e5_c001_s2p/tables/e5_c001_s2p_readout_issues.csv"
CSV_GABLE_MODE = REPO / "docs/experiments/e5_c001_s2p/tables/e5_c001_s2p_gable_mode.csv"
CSV_PANEL_INVENTORY = REPO / "docs/experiments/e5_c001_s2p/tables/e5_c001_s2p_8way_panel_inventory.csv"
CSV_PIPELINE_STRIPS = REPO / "docs/experiments/e5_c001_s2p/tables/e5_c001_s2p_pipeline_strips.csv"
CSV_PIPELINE_STRIP_ISSUES = REPO / "docs/experiments/e5_c001_s2p/tables/e5_c001_s2p_pipeline_strips_issues.csv"
CSV_ARM_CELLS = REPO / "docs/experiments/e5_c001_s2p/tables/e5_c001_s2p_arm_cells.csv"
CSV_REND_DIST = REPO / "docs/experiments/e5_c001_s2p/tables/e5_c001_s2p_rend_dist.csv"
CSV_GLOBAL_Z = REPO / "docs/experiments/e5_c001_s2p/tables/e5_c001_s2p_global_z_hist.csv"

TIMELINE_IDS = ["4907202", "4908168", "4908178", "4907184"]
TIMELINE_FULL_IDS = [f"DEBY_LOD2_{sid}" for sid in TIMELINE_IDS]
SOURCE_DOCS = [
    REPO / "docs/experiments/e5_c001_s2/reports/W_E5_C001_S2_중간검수·Arm3회부_20260710.md",
    REPO / "docs/원격프롬프트_S2_방향자리_사슬4arm·선행묶음_20260710.md",
    REPO / "docs/experiments/e5_c001_s2/reports/W_S2설계_손실비교·실험계획_20260710.md",
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
        "training_implementation_commit": "d58774809d665b196fa62683df6ecbe947a04118",
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
        "outputs": [
            rel(REPORT_PATH),
            rel(CSV_ARM_CELLS),
            rel(CSV_TIMELINE),
            rel(CSV_DENSIFY),
            rel(CSV_MONO_V2),
            rel(CSV_SHEET_OPACITY),
            rel(CSV_TWIN_REND),
            rel(CSV_GABLE_MODE),
            rel(CSV_REND_DIST),
            rel(CSV_GLOBAL_Z),
            rel(CSV_405_BUILDING),
            rel(FIG_DIR),
            rel(RUN_DIR / "train_fingerprints.csv"),
            rel(RUN_DIR / "readout_fingerprints.csv"),
            rel(RUN_DIR / "versions.txt"),
        ],
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
    repair.CSV_BUILDING = REPO / "docs/experiments/e5_c001_s2p/tables/e5_c001_s2p_405_repair_status_building.csv"
    repair.CSV_ISSUES = REPO / "docs/experiments/e5_c001_s2p/tables/e5_c001_s2p_405_repair_issues.csv"
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
    _plot_timeline(rows)
    print(json.dumps({"timeline": rel(CSV_TIMELINE), "rows": len(rows)}, ensure_ascii=False))


def _plot_timeline(rows: list[dict[str, Any]]) -> None:
    output_dir = FIG_DIR / "timeline"
    output_dir.mkdir(parents=True, exist_ok=True)
    colors = {"r1": "#1F4E79", "r2": "#B7831B"}
    for short_id in TIMELINE_IDS:
        building_id = s2.full_id(short_id)
        part = [row for row in rows if row.get("building_id") == building_id]
        if not part:
            continue
        fig, axes = plt.subplots(1, 3, figsize=(10.8, 3.5), constrained_layout=True)
        for replicate in ["r1", "r2"]:
            group = sorted(
                [row for row in part if row.get("replicate") == replicate],
                key=lambda row: int(row["step"]),
            )
            if not group:
                continue
            x = [int(row["step"]) / 1000.0 for row in group]
            axes[0].plot(
                x,
                [_finite_float(row.get("n_gaussians_in_footprint")) or 0 for row in group],
                marker="o",
                color=colors[replicate],
                label=replicate,
            )
            axes[1].plot(
                x,
                [
                    _finite_float(row.get("z_p50"))
                    if _finite_float(row.get("z_p50")) is not None
                    else np.nan
                    for row in group
                ],
                marker="o",
                color=colors[replicate],
                label=replicate,
            )
            axes[2].plot(
                x,
                [
                    _finite_float(row.get("opacity_p50"))
                    if _finite_float(row.get("opacity_p50")) is not None
                    else np.nan
                    for row in group
                ],
                marker="o",
                color=colors[replicate],
                label=replicate,
            )
        axes[0].set_ylabel("Gaussians in footprint")
        axes[1].set_ylabel("z p50 (m)")
        axes[2].set_ylabel("opacity p50")
        for axis in axes:
            axis.set_xlabel("iteration (k)")
            axis.grid(color="#DDDDDD", linewidth=0.6)
        axes[0].legend(fontsize=8)
        fig.suptitle(f"Arm 1p roof-crop timeline: {short_id}", fontsize=11)
        fig.savefig(output_dir / f"timeline_{short_id}.png", dpi=190)
        plt.close(fig)


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


def _circular_distance_deg(a: float, b: float) -> float:
    return abs((a - b + 180.0) % 360.0 - 180.0)


def _roof_mode_summary(surfaces: list[Any]) -> dict[str, Any]:
    candidates: list[tuple[float, float]] = []
    total_roof_area = 0.0
    for surface in surfaces:
        normal = s2.roof_normal_world(surface)
        area = max(float(surface.polygon.area), 0.0)
        total_roof_area += area
        tilt = math.degrees(math.acos(float(np.clip(abs(normal[2]), 0.0, 1.0))))
        if tilt <= 10.0 or area <= 0.0:
            continue
        azimuth = math.degrees(math.atan2(float(normal[1]), float(normal[0]))) % 360.0
        candidates.append((azimuth, area))
    clusters: list[dict[str, float]] = []
    for azimuth, area in sorted(candidates, key=lambda item: item[1], reverse=True):
        nearest = None
        nearest_distance = float("inf")
        for cluster in clusters:
            distance = _circular_distance_deg(azimuth, cluster["azimuth"])
            if distance < nearest_distance:
                nearest, nearest_distance = cluster, distance
        if nearest is None or nearest_distance > 25.0:
            clusters.append({"azimuth": azimuth, "weight": area})
            continue
        old_weight = nearest["weight"]
        x = old_weight * math.cos(math.radians(nearest["azimuth"])) + area * math.cos(math.radians(azimuth))
        y = old_weight * math.sin(math.radians(nearest["azimuth"])) + area * math.sin(math.radians(azimuth))
        nearest["azimuth"] = math.degrees(math.atan2(y, x)) % 360.0
        nearest["weight"] = old_weight + area
    sloped_area = sum(cluster["weight"] for cluster in clusters)
    retained = [
        cluster for cluster in clusters if sloped_area > 0 and cluster["weight"] / sloped_area >= 0.05
    ]
    retained.sort(key=lambda cluster: cluster["azimuth"])
    return {
        "roof_face_count": len(surfaces),
        "sloped_face_count": len(candidates),
        "direction_mode_count": len(retained),
        "direction_mode_azimuths_deg": ";".join(f"{cluster['azimuth']:.1f}" for cluster in retained),
        "sloped_area_m2": s2.fmt(sloped_area),
        "roof_area_m2": s2.fmt(total_roof_area),
    }


def _assembled_cityjson_sources() -> list[tuple[str, str, str, Path]]:
    sources: list[tuple[str, str, str, Path]] = []
    s2_repaired = (
        REPO
        / "phases/p0-audit/runs/e5p_s2_405_repair_20260710_C001/e5p_s2_direction_position_20260710_C001/base/cityjson"
    )
    for arm in ["arm0", "arm1", "arm2"]:
        for rep in [1, 2]:
            run_name = f"gs_e5_C001_s2_{arm}_dense_r{rep}"
            sources.append(("s2", arm, f"r{rep}", s2_repaired / f"{run_name}_run_1.city.json"))
    for rep in [1, 2]:
        run_name = arm1p_run_name(rep)
        sources.append(
            (
                "s2p",
                "arm1p",
                f"r{rep}",
                REPAIRED_P0_RUN_DIR / "base/cityjson" / f"{run_name}_run_1.city.json",
            )
        )
    return sources


def gable_mode(_args: argparse.Namespace) -> None:
    target_ids = ["4907184", "4907202", "60098", "4907186"]
    all_ids = list(s2.C001_IDS)
    references = s2.eight.parse_lod2_roofs(s2.eight.LOD2_DIR, set(all_ids))
    reference_summary = {
        building_id: _roof_mode_summary(surfaces) for building_id, surfaces in references.items()
    }
    rows: list[dict[str, Any]] = []
    for family, arm, replicate, cityjson in _assembled_cityjson_sources():
        if not cityjson.exists():
            continue
        predictions = s2.eight.parse_cityjson_roofs(cityjson, set(all_ids))
        run_name = cityjson.name.removesuffix("_run_1.city.json")
        for building_id in all_ids:
            predicted = _roof_mode_summary(predictions.get(building_id, []))
            reference = reference_summary.get(building_id, _roof_mode_summary([]))
            rows.append(
                {
                    "family": family,
                    "arm": arm,
                    "replicate": replicate,
                    "run_name": run_name,
                    "building_id": building_id,
                    "target_four": str(s2.short_id(building_id) in target_ids).lower(),
                    "has_lod22": str(bool(predictions.get(building_id))).lower(),
                    "pred_direction_mode_count": predicted["direction_mode_count"],
                    "ref_direction_mode_count": reference["direction_mode_count"],
                    "mode_count_delta": predicted["direction_mode_count"] - reference["direction_mode_count"],
                    "pred_mode_azimuths_deg": predicted["direction_mode_azimuths_deg"],
                    "ref_mode_azimuths_deg": reference["direction_mode_azimuths_deg"],
                    "pred_roof_face_count": predicted["roof_face_count"],
                    "ref_roof_face_count": reference["roof_face_count"],
                    "pred_sloped_face_count": predicted["sloped_face_count"],
                    "ref_sloped_face_count": reference["sloped_face_count"],
                    "mode_definition": "3D roof normals; tilt>10deg; circular merge<=25deg; retain>=5% sloped area",
                    "cityjson": rel(cityjson),
                }
            )
    write_csv(CSV_GABLE_MODE, rows)
    print(json.dumps({"gable_mode": rel(CSV_GABLE_MODE), "rows": len(rows)}, ensure_ascii=False))


def _panel_sources() -> list[Any]:
    eight = s2.eight
    base_sources = {source.source_run: source for source in eight.sources()}
    base_sources["reference"].display_label = "Reference LoD2"
    base_sources["lidar"].display_label = "LiDAR"
    sources = [
        base_sources["reference"],
        base_sources["lidar"],
        base_sources["raw_dense"],
        base_sources["raw_sparse"],
        base_sources["raw_acmp"],
    ]
    s2_repaired = (
        REPO
        / "phases/p0-audit/runs/e5p_s2_405_repair_20260710_C001/e5p_s2_direction_position_20260710_C001/base"
    )
    s2_original = REPO / "phases/p0-audit/runs/e5p_s2_direction_position_20260710_C001/base"
    arm1_name = "gs_e5_C001_s2_arm1_dense_r1"
    sources.append(
        eight.Source(
            "gs_arm1",
            "s2_arm1_r1",
            "S2 Arm 1 r1",
            "gs",
            s2_repaired / "status" / f"{arm1_name}_run_1.csv",
            None,
            s2_repaired / "cityjson" / f"{arm1_name}_run_1.city.json",
            None,
            pointcloud_template=str(
                s2_original / "roofer" / arm1_name / "run_1" / "{bid}_run_1_classified.las"
            ),
            run_name=arm1_name,
            z_shift_to_reference_m=s2.ELLIP_TO_REF_SHIFT_M,
        )
    )
    for rep in [1, 2]:
        run_name = arm1p_run_name(rep)
        sources.append(
            eight.Source(
                "gs_arm1p",
                f"s2p_arm1p_r{rep}",
                f"S2p Arm 1' r{rep}",
                "gs",
                REPAIRED_P0_RUN_DIR / "base/status" / f"{run_name}_run_1.csv",
                None,
                REPAIRED_P0_RUN_DIR / "base/cityjson" / f"{run_name}_run_1.city.json",
                None,
                pointcloud_template=str(
                    P0_RUN_DIR / "base/roofer" / run_name / "run_1" / "{bid}_run_1_classified.las"
                ),
                run_name=run_name,
                z_shift_to_reference_m=s2.ELLIP_TO_REF_SHIFT_M,
            )
        )
    return sources


def _footprint_polygons(ids: list[str]) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    from shapely.geometry import Polygon
    from shapely.ops import unary_union

    footprint_rows = s2.strips.load_footprints(ids)
    polygons = {
        building_id: unary_union([Polygon(ring) for ring in footprint["rings"]])
        for building_id, footprint in footprint_rows.items()
    }
    return polygons, footprint_rows


def _reference_cloud(surfaces: list[Any]) -> np.ndarray:
    samples: list[np.ndarray] = []
    for surface in surfaces:
        xy = s2.eight.sample_polygon_points(surface.polygon, spacing=0.35, limit=1200)
        if len(xy):
            samples.append(np.column_stack([xy[:, 0], xy[:, 1], surface.z_at(xy[:, 0], xy[:, 1])]))
    return np.vstack(samples) if samples else np.zeros((0, 3), dtype=np.float64)


def _panel_axis(footprint: dict[str, Any]) -> np.ndarray:
    points = np.concatenate(footprint["rings"], axis=0).astype(np.float64)
    centered = points - points.mean(axis=0, keepdims=True)
    covariance = centered.T @ centered
    values, vectors = np.linalg.eigh(covariance)
    axis = vectors[:, int(np.argmax(values))]
    if axis[0] < 0:
        axis = -axis
    return axis / max(float(np.linalg.norm(axis)), 1e-9)


def _draw_panel_top(ax: Any, points: np.ndarray, footprint: dict[str, Any], title: str) -> None:
    ax.set_title(title, fontsize=7)
    if len(points):
        selected = points
        if len(selected) > 18000:
            rng = np.random.default_rng(20260710)
            selected = selected[rng.choice(len(selected), 18000, replace=False)]
        color = selected[:, 2] - np.median(selected[:, 2])
        ax.scatter(selected[:, 0], selected[:, 1], c=color, cmap="viridis", s=0.7, linewidths=0)
    else:
        ax.text(0.5, 0.5, "no points", ha="center", va="center", transform=ax.transAxes, fontsize=7)
    for ring in footprint["rings"]:
        ax.plot(ring[:, 0], ring[:, 1], color="#202020", linewidth=0.8)
    x0, y0, x1, y1 = footprint["bbox"]
    pad = max(x1 - x0, y1 - y0) * 0.12 + 0.5
    ax.set_xlim(x0 - pad, x1 + pad)
    ax.set_ylim(y0 - pad, y1 + pad)
    ax.set_aspect("equal", adjustable="box")
    ax.set_xticks([])
    ax.set_yticks([])


def _draw_panel_side(
    ax: Any,
    points: np.ndarray,
    footprint: dict[str, Any],
    axis: np.ndarray,
    z_limits: tuple[float, float],
) -> None:
    if len(points):
        selected = points
        if len(selected) > 18000:
            rng = np.random.default_rng(20260710)
            selected = selected[rng.choice(len(selected), 18000, replace=False)]
        origin = np.mean(np.concatenate(footprint["rings"], axis=0), axis=0)
        horizontal = (selected[:, :2] - origin) @ axis
        ax.scatter(horizontal, selected[:, 2], c=selected[:, 2], cmap="viridis", s=0.7, linewidths=0)
    else:
        ax.text(0.5, 0.5, "no points", ha="center", va="center", transform=ax.transAxes, fontsize=7)
    x0, y0, x1, y1 = footprint["bbox"]
    span = math.hypot(x1 - x0, y1 - y0) * 0.58 + 0.5
    ax.set_xlim(-span, span)
    ax.set_ylim(*z_limits)
    ax.set_xlabel("principal axis (m)", fontsize=6)
    ax.set_ylabel("z (m)", fontsize=6)
    ax.tick_params(labelsize=5)
    ax.grid(color="#DDDDDD", linewidth=0.5)


def panels_8way(_args: argparse.Namespace) -> None:
    core_ids = ["4907202", "4908168", "4907185", "4907184", "60098", "8568392"]
    full_ids = [s2.full_id(short_id) for short_id in core_ids]
    sources = _panel_sources()
    polygons, footprint_rows = _footprint_polygons(core_ids)
    references = s2.eight.parse_lod2_roofs(s2.eight.LOD2_DIR, set(full_ids))
    predictions: dict[str, dict[str, list[Any]]] = {}
    for source in sources:
        if source.source_run == "reference":
            predictions[source.source_run] = references
        elif source.cityjson_path and source.cityjson_path.exists():
            parsed = s2.eight.parse_cityjson_roofs(source.cityjson_path, set(full_ids))
            predictions[source.source_run] = {
                building_id: s2.eight.shift_surface_z(surfaces, source.z_shift_to_reference_m)
                for building_id, surfaces in parsed.items()
            }
        else:
            predictions[source.source_run] = {}
    cache = s2.eight.PointCloudCache(polygons)
    out_dir = FIG_DIR / "8way_panels"
    out_dir.mkdir(parents=True, exist_ok=True)
    inventory: list[dict[str, Any]] = []
    for short_id in core_ids:
        building_id = s2.full_id(short_id)
        footprint = footprint_rows[building_id]
        axis = _panel_axis(footprint)
        reference_surfaces = references.get(building_id, [])
        reference_points = _reference_cloud(reference_surfaces)
        if len(reference_points):
            z_limits = (
                float(np.percentile(reference_points[:, 2], 1)) - 3.0,
                float(np.percentile(reference_points[:, 2], 99)) + 3.0,
            )
        else:
            z_limits = (560.0, 590.0)
        clouds: dict[str, np.ndarray] = {}
        for source in sources:
            if source.source_run == "reference":
                points = reference_points
            else:
                points = cache.read_roof_points(source, building_id)
                if len(points) and source.z_shift_to_reference_m:
                    points = points.copy()
                    points[:, 2] += float(source.z_shift_to_reference_m)
            clouds[source.source_run] = points
        n_columns = len(sources)
        figure = plt.figure(figsize=(2.25 * n_columns, 8.0), constrained_layout=True)
        for column, source in enumerate(sources, start=1):
            points = clouds[source.source_run]
            surfaces = predictions[source.source_run].get(building_id, [])
            _draw_panel_top(
                figure.add_subplot(3, n_columns, column),
                points,
                footprint,
                source.display_label,
            )
            _draw_panel_side(
                figure.add_subplot(3, n_columns, n_columns + column),
                points,
                footprint,
                axis,
                z_limits,
            )
            s2.eight.draw_model(
                figure.add_subplot(3, n_columns, 2 * n_columns + column, projection="3d"),
                surfaces,
                polygons[building_id],
                "assembled model" if source.source_run != "reference" else "reference LoD2",
                f"roof faces {len(surfaces)}",
            )
            inventory.append(
                {
                    "building_id": building_id,
                    "source_run": source.source_run,
                    "display_label": source.display_label,
                    "point_count_in_footprint": len(points),
                    "roof_face_count": len(surfaces),
                    "pointcloud_source": source.pointcloud_template or rel(source.pointcloud_path) if source.pointcloud_path else source.pointcloud_template or "reference samples",
                    "cityjson": rel(source.cityjson_path) if source.cityjson_path else "reference LoD2",
                    "z_shift_to_reference_m": source.z_shift_to_reference_m,
                }
            )
        figure.suptitle(f"C001 S2p source panel: {building_id}", fontsize=12)
        output = out_dir / f"8way_{short_id}.png"
        figure.savefig(output, dpi=170)
        plt.close(figure)
        for row in inventory[-len(sources) :]:
            row["figure"] = rel(output)
        print(json.dumps({"panel": rel(output), "building_id": building_id}, ensure_ascii=False), flush=True)
    write_csv(CSV_PANEL_INVENTORY, inventory)
    print(json.dumps({"panel_inventory": rel(CSV_PANEL_INVENTORY), "rows": len(inventory)}, ensure_ascii=False))


def pipeline_strips(args: argparse.Namespace) -> None:
    from src.stage2.dataloader import ColmapDataset

    os.environ.setdefault("TORCH_HOME", "/tmp/torch")
    configure_readout()
    reps = [1, 2] if args.rep == "all" else [int(args.rep)]
    conditions = [
        s2.strips.StripCondition(
            key=f"arm1p_r{rep}",
            label=f"Arm 1' r{rep}",
            run_name=arm1p_run_name(rep),
            ckpt=checkpoint_path(arm1p_run_name(rep), "final"),
            coverage_csv=CSV_COVERAGE,
            metrics_csv=CSV_405_BUILDING,
            p0_run_id=P0_RUN_ID,
        )
        for rep in reps
    ]
    s2.strips.REPAIR_ROOT = s2.P0_RUNS / REPAIR_RUN_ID
    footprints = s2.strips.load_footprints(TIMELINE_IDS)
    references = s2.eight.parse_lod2_roofs(
        s2.eight.LOD2_DIR, {s2.full_id(short_id) for short_id in TIMELINE_IDS}
    )
    dataset = ColmapDataset(
        root=str(DATA_ROOT),
        downscale=args.downscale,
        load_depth=True,
        load_normal=False,
        load_semantic=False,
    )
    s2.strips.render_crop.dataset = dataset
    render_cache: dict[tuple[str, int], dict[str, np.ndarray]] = {}
    rows: list[dict[str, Any]] = []
    issues: list[dict[str, Any]] = []
    out_dir = FIG_DIR / "pipeline_strips"
    out_dir.mkdir(parents=True, exist_ok=True)
    for condition in conditions:
        if not condition.ckpt.exists():
            issues.append(
                {
                    "condition": condition.key,
                    "building_id": "",
                    "message": "checkpoint missing",
                    "path": rel(condition.ckpt),
                }
            )
            continue
        gaussians = s2.strips.load_gaussians(condition.ckpt)
        parsed = s2.eight.parse_cityjson_roofs(
            s2.strips.cityjson_path(condition), {s2.full_id(short_id) for short_id in TIMELINE_IDS}
        )
        predictions = {
            building_id: s2.eight.shift_surface_z(surfaces, condition.z_shift_to_reference_m)
            for building_id, surfaces in parsed.items()
        }
        for short_id in TIMELINE_IDS:
            building_id = s2.full_id(short_id)
            footprint = footprints.get(building_id)
            reference = references.get(building_id, [])
            if footprint is None or not reference:
                issues.append(
                    {
                        "condition": condition.key,
                        "building_id": building_id,
                        "message": "footprint or reference missing",
                        "path": "",
                    }
                )
                continue
            view_idx, crop = s2.strips.select_view(dataset, footprint, reference)
            rendered = None
            try:
                rendered = s2.strips.render_crop(
                    condition, view_idx, crop, args.device, render_cache
                )
            except Exception as exc:  # noqa: BLE001
                issues.append(
                    {
                        "condition": condition.key,
                        "building_id": building_id,
                        "message": f"render failed: {type(exc).__name__}: {exc}",
                        "path": rel(condition.ckpt),
                    }
                )
            counts = s2.strips.coverage_counts(condition, building_id)
            status = s2.strips.status_for(condition, building_id)
            output = out_dir / f"{short_id}_{condition.key}.png"
            s2.strips.plot_strip(
                condition,
                building_id,
                footprint,
                reference,
                predictions.get(building_id, []),
                gaussians,
                rendered,
                counts,
                status,
                output,
            )
            stats = s2.strips.gaussian_stats(gaussians["means"], gaussians["opacity"], footprint)
            rows.append(
                {
                    "condition": condition.key,
                    "arm": "arm1p",
                    "replicate": f"r{condition.key[-1]}",
                    "run_name": condition.run_name,
                    "building_id": building_id,
                    "figure": rel(output),
                    "view_idx": view_idx,
                    "crop_xyxy": ",".join(str(value) for value in crop),
                    "ckpt": rel(condition.ckpt),
                    "cityjson": rel(s2.strips.cityjson_path(condition)),
                    "status_reason": status.get("reason", ""),
                    "has_lod22": status.get("has_lod22", ""),
                    "val3dity_valid": status.get("val3dity_valid", ""),
                    **{key: "" if value is None else value for key, value in stats.items()},
                    **{f"readout_{key}": value for key, value in counts.items()},
                }
            )
            print(json.dumps({"strip": rel(output), "building_id": building_id}, ensure_ascii=False), flush=True)
    write_csv(CSV_PIPELINE_STRIPS, rows)
    write_csv(
        CSV_PIPELINE_STRIP_ISSUES,
        issues,
        ["condition", "building_id", "message", "path"],
    )
    print(json.dumps({"pipeline_strips": rel(CSV_PIPELINE_STRIPS), "rows": len(rows), "issues": len(issues)}, ensure_ascii=False))


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


def fingerprint_training(_args: argparse.Namespace) -> None:
    import torch

    rows: list[dict[str, Any]] = []
    for rep in [1, 2]:
        run_name = arm1p_run_name(rep)
        config = CONFIG_DIR / f"{run_name}.yaml"
        effective_config = CKPT_ROOT / run_name / "effective_config.json"
        checkpoint = checkpoint_path(run_name, "final")
        log = TRAIN_LOG_ROOT / f"{run_name}.log"
        log_info = s2.parse_train_log(log)
        payload = (
            torch.load(checkpoint, map_location="cpu", weights_only=False)
            if checkpoint.exists()
            else {}
        )
        effective = (
            json.loads(effective_config.read_text(encoding="utf-8"))
            if effective_config.exists()
            else {}
        )
        rows.append(
            {
                "arm": "arm1p",
                "replicate": f"r{rep}",
                "run_name": run_name,
                "seed": effective.get("seed", 2001),
                "config": rel(config),
                "config_sha256": sha256_file(config) if config.exists() else "",
                "effective_config": rel(effective_config),
                "effective_config_sha256": (
                    sha256_file(effective_config) if effective_config.exists() else ""
                ),
                "ckpt": rel(checkpoint),
                "ckpt_sha256": sha256_file(checkpoint) if checkpoint.exists() else "",
                "start_utc": log_info.get("start_utc", ""),
                "end_utc": log_info.get("end_utc", ""),
                "return_code": log_info.get("return_code", ""),
                "elapsed_min": log_info.get("elapsed_min", ""),
                "host_gpu": log_info.get("host_gpu", ""),
                "max_iter": payload.get("it", ""),
                "final_n_gaussians": payload.get("n_prim", ""),
                "w_normal": effective.get("w_normal", ""),
                "prune_opa": effective.get("prune_opa", ""),
                "final_prune_opa": effective.get("final_prune_opa", ""),
                "depth_weight_floor": effective.get("depth_weight_floor", ""),
                "audit_csv": rel(CKPT_ROOT / run_name / "audit/loss_grad_norms.csv"),
                "densify_audit": rel(CKPT_ROOT / run_name / "audit/densify_events.csv"),
            }
        )
    write_csv(RUN_DIR / "train_fingerprints.csv", rows)
    print(
        json.dumps(
            {"train_fingerprints": rel(RUN_DIR / "train_fingerprints.csv"), "rows": len(rows)},
            ensure_ascii=False,
        )
    )


def rend_dist_summary(_args: argparse.Namespace) -> None:
    rows: list[dict[str, Any]] = []
    for rep in [1, 2]:
        run_name = arm1p_run_name(rep)
        rows.append(
            {
                "arm": "arm1p",
                "replicate": f"r{rep}",
                "run_name": run_name,
                **_rend_dist_from_audit(run_name, CKPT_ROOT),
                "reconstruction": "tail raw_loss * distort_norm_denominator; same S2 method",
            }
        )
    write_csv(CSV_REND_DIST, rows)
    print(json.dumps({"rend_dist": rel(CSV_REND_DIST), "rows": len(rows)}, ensure_ascii=False))


def global_z_hist(_args: argparse.Namespace) -> None:
    import torch

    rows: list[dict[str, Any]] = []
    edges = np.arange(520.0, 702.0, 2.0)
    for rep in [1, 2]:
        run_name = arm1p_run_name(rep)
        checkpoint = checkpoint_path(run_name, "final")
        if not checkpoint.exists():
            continue
        state = torch.load(checkpoint, map_location="cpu", weights_only=False)["state_dict"]
        z = state["means"].detach().cpu().numpy()[:, 2].astype(np.float64) + s2.SHIFT_UTM[2]
        opacity = torch.sigmoid(state["opacities_raw"].detach().cpu().float()).numpy()
        hist, _ = np.histogram(z, bins=edges)
        for index, count in enumerate(hist):
            in_bin = (z >= edges[index]) & (z < edges[index + 1])
            rows.append(
                {
                    "arm": "arm1p",
                    "replicate": f"r{rep}",
                    "run_name": run_name,
                    "z_min": s2.fmt(edges[index]),
                    "z_max": s2.fmt(edges[index + 1]),
                    "n_gaussians": int(count),
                    "fraction_of_all": s2.fmt(int(count) / len(z) if len(z) else None, 8),
                    "opacity_p50": s2.fmt(
                        float(np.quantile(opacity[in_bin], 0.5)) if np.any(in_bin) else None
                    ),
                    "ckpt": rel(checkpoint),
                }
            )
    write_csv(CSV_GLOBAL_Z, rows)
    print(json.dumps({"global_z_hist": rel(CSV_GLOBAL_Z), "rows": len(rows)}, ensure_ascii=False))


def _source_summary(metrics: list[dict[str, str]], run_name: str) -> dict[str, Any]:
    part = [
        row
        for row in metrics
        if row.get("setting") == "base" and row.get("run_name") == run_name
    ]
    rms_values = [
        value
        for value in (_finite_float(row.get("ref_rms_m")) for row in part)
        if value is not None
    ]
    return {
        "has_lod22": sum(s2.tf(row.get("has_lod22")) for row in part),
        "valid_assembled": sum(
            s2.tf(row.get("has_lod22")) and s2.tf(row.get("val3dity_valid"))
            for row in part
        ),
        "invalid_assembled": sum(
            s2.tf(row.get("has_lod22")) and not s2.tf(row.get("val3dity_valid"))
            for row in part
        ),
        "median_ref_rms_m": float(np.median(rms_values)) if rms_values else None,
    }


def _s0_dense_count() -> int:
    source = REPO / "phases/p2-gsjso/runs/e5p_train_20260707_C001/train_fingerprints.csv"
    for row in read_csv(source):
        if row.get("run_name") == "gs_e5_C001_dense_r1":
            value = _finite_float(row.get("final_n") or row.get("final_n_gaussians"))
            if value is not None:
                return int(value)
    return 575318


def build_arm_cells(_args: argparse.Namespace) -> None:
    metrics = read_csv(CSV_405_BUILDING)
    raw_metrics = read_csv(REPO / "docs/experiments/e5_c001_8way/tables/e5_c001_8way_metrics.csv")
    s1_metrics = read_csv(REPO / "docs/experiments/e5_c001_3b_s1/tables/e5_c001_3b_s1_metrics.csv")
    fingerprints = read_csv(RUN_DIR / "train_fingerprints.csv")
    rend_dist = read_csv(CSV_REND_DIST)
    raw_by = {
        (row.get("source_run", ""), row.get("building_id", "")): row
        for row in raw_metrics
    }
    s1_by = {
        (row.get("source_run", ""), row.get("building_id", "")): row
        for row in s1_metrics
    }
    metric_by = {
        (row.get("run_name", ""), row.get("building_id", "")): row
        for row in metrics
        if row.get("setting") == "base"
    }
    fingerprint_by = {row.get("run_name", ""): row for row in fingerprints}
    rend_by = {row.get("run_name", ""): row for row in rend_dist}
    s0_x2 = 2 * _s0_dense_count()
    rows: list[dict[str, Any]] = []
    for rep in [1, 2]:
        run_name = arm1p_run_name(rep)
        source = _source_summary(metrics, run_name)
        good6: list[dict[str, Any]] = []
        for short_id in s2.GOOD6:
            building_id = s2.full_id(short_id)
            row = metric_by.get((run_name, building_id), {})
            raw_row = raw_by.get(("raw_dense", building_id), {})
            s1_row = s1_by.get(("base__gs_e5_C001_s1_dense_r1", building_id), {})
            rms = _finite_float(row.get("ref_rms_m"))
            raw_rms = _finite_float(raw_row.get("ref_rms_m"))
            s1_rms = _finite_float(s1_row.get("ref_rms_m"))
            good6.append(
                {
                    "built": s2.tf(row.get("has_lod22")),
                    "raw_anchor_ok": (
                        rms is not None and raw_rms is not None and rms <= raw_rms + 0.5
                    ),
                    "delta_vs_s1": (
                        None if rms is None or s1_rms is None else rms - s1_rms
                    ),
                }
            )
        deltas = [
            item["delta_vs_s1"]
            for item in good6
            if item["delta_vs_s1"] is not None
        ]
        final_n = _finite_float(fingerprint_by.get(run_name, {}).get("final_n_gaussians"))
        rend_value = _finite_float(rend_by.get(run_name, {}).get("rend_dist_mean_tail_m"))
        guardrail = all(item["built"] for item in good6) and sum(
            bool(item["raw_anchor_ok"]) for item in good6
        ) >= 5
        accuracy = (
            bool(deltas)
            and float(np.median(deltas)) <= 0.3
            and not any(value > 1.5 for value in deltas)
        )
        count_ok = final_n is not None and final_n <= s0_x2
        if rend_value is None:
            rend_status = "missing"
        elif rend_value < 0.4:
            rend_status = "pass"
        elif rend_value <= 0.6:
            rend_status = "boundary"
        else:
            rend_status = "fail"
        cleaning_status = rend_status if count_ok else "fail"
        validity = source["valid_assembled"] >= 10
        if cleaning_status == "boundary" and guardrail and accuracy and validity:
            all4_status = "boundary"
        elif cleaning_status == "pass" and guardrail and accuracy and validity:
            all4_status = "pass"
        else:
            all4_status = "fail"
        rows.append(
            {
                "arm": "arm1p",
                "replicate": f"r{rep}",
                "run_name": run_name,
                "configuration": "arm1 + prune_opa 0.05 (normal fixed)",
                "has_lod22": source["has_lod22"],
                "valid_assembled": source["valid_assembled"],
                "invalid_assembled": source["invalid_assembled"],
                "median_ref_rms_m": s2.fmt(source["median_ref_rms_m"]),
                "good6_all_built": str(all(item["built"] for item in good6)).lower(),
                "good6_raw_anchor_count": sum(
                    bool(item["raw_anchor_ok"]) for item in good6
                ),
                "good6_median_delta_vs_s1_m": s2.fmt(
                    float(np.median(deltas)) if deltas else None
                ),
                "good6_max_delta_vs_s1_m": s2.fmt(max(deltas) if deltas else None),
                "good6_catastrophe_count": sum(value > 1.5 for value in deltas),
                "final_n_gaussians": s2.fmt(final_n),
                "s0_dense_x2_threshold": s0_x2,
                "count_le_s0_x2": str(count_ok).lower(),
                "rend_dist_mean_tail_m": s2.fmt(rend_value),
                "rend_dist_status": rend_status,
                "pareto_guardrail": "pass" if guardrail else "fail",
                "pareto_accuracy_nonregression": "pass" if accuracy else "fail",
                "pareto_cleaning": cleaning_status,
                "pareto_validity_nonregression": "pass" if validity else "fail",
                "pareto_all4": all4_status,
                "ckpt": fingerprint_by.get(run_name, {}).get(
                    "ckpt", rel(checkpoint_path(run_name, "final"))
                ),
                "readout": "gssem; minobs3; voxel0.05; SORstd2; 405 repair overlay",
                "arm3_scoring": "excluded by A-1p >8 m branch",
            }
        )
    write_csv(CSV_ARM_CELLS, rows)
    _plot_arm_cells(rows)
    print(json.dumps({"arm_cells": rel(CSV_ARM_CELLS), "rows": len(rows)}, ensure_ascii=False))


def _plot_arm_cells(rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    output_dir = FIG_DIR / "summary"
    output_dir.mkdir(parents=True, exist_ok=True)
    labels = [row["replicate"] for row in rows]
    x = np.arange(len(rows))
    fig, axes = plt.subplots(1, 3, figsize=(10.5, 3.6), constrained_layout=True)
    axes[0].bar(x, [int(row["good6_raw_anchor_count"]) for row in rows], color="#1F4E79")
    axes[1].bar(x, [_finite_float(row["valid_assembled"]) or 0 for row in rows], color="#4F7C5B")
    axes[2].bar(x, [_finite_float(row["rend_dist_mean_tail_m"]) or 0 for row in rows], color="#B7831B")
    axes[0].axhline(5, color="#555555", linestyle="--", linewidth=1)
    axes[1].axhline(10, color="#555555", linestyle="--", linewidth=1)
    axes[2].axhspan(0.4, 0.6, color="#D9D9D9", alpha=0.55)
    axes[0].set_title("Good6 raw anchors")
    axes[1].set_title("Valid assembled")
    axes[2].set_title("rend_dist tail (m)")
    for axis in axes:
        axis.set_xticks(x)
        axis.set_xticklabels(labels)
        axis.grid(axis="y", color="#DDDDDD", linewidth=0.6)
    fig.suptitle("Arm 1p replicate metrics", fontsize=11)
    fig.savefig(output_dir / "arm1p_cell_summary.png", dpi=190)
    plt.close(fig)


def versions(_args: argparse.Namespace) -> None:
    write_manifest()
    large_checkpoint = MONO_V2_ROOT / "checkpoints/depth_anything_v2_vitl.pth"
    decision = RUN_DIR / "monodepth_decision_v2.json"
    lines = [
        f"run_id: {RUN_ID}",
        f"timestamp_utc: {datetime.now(timezone.utc).isoformat()}",
        f"git_head: {s2.capture(['git', 'rev-parse', 'HEAD'])}",
        f"git_branch: {s2.capture(['git', 'branch', '--show-current'])}",
        "crs: EPSG:25832",
        "canonical_changed: no",
        "mode: S2p observation material; no human verdict",
        "arm3: excluded by locked A-1p branch; no Pearson implementation or training",
        f"monodepth_decision: {rel(decision)}",
        f"monodepth_large_checkpoint: {rel(large_checkpoint)}",
        f"monodepth_large_checkpoint_sha256: {sha256_file(large_checkpoint) if large_checkpoint.exists() else ''}",
        f"train_fingerprints: {rel(RUN_DIR / 'train_fingerprints.csv')}",
        f"readout_fingerprints: {rel(RUN_DIR / 'readout_fingerprints.csv')}",
        f"arm_cells_csv: {rel(CSV_ARM_CELLS)}",
        f"issues_csv: {rel(CSV_ISSUES)}",
        "issues_md: phases/p2-gsjso/docs/issues.md",
    ]
    (RUN_DIR / "versions.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"versions": rel(RUN_DIR / "versions.txt")}, ensure_ascii=False))


def _report_group(building_id: str) -> str:
    short = s2.short_id(building_id)
    if short in s2.GOOD6:
        return "양쪽 성공 6동"
    if short in s2.GS_FAIL5:
        return "GS만 실패 5동"
    if short in s2.TEXTURELESS_OBS3:
        return "입력 한계 5동/무늬없음·관측됨 3"
    return ""


def _join_metric(values: list[Any], digits: int = 4) -> str:
    return "/".join(s2.fmt(_finite_float(value), digits) for value in values)


def report(_args: argparse.Namespace) -> None:
    arm_cells = read_csv(CSV_ARM_CELLS)
    metrics = [
        row
        for row in read_csv(CSV_405_BUILDING)
        if row.get("run_name") in {arm1p_run_name(1), arm1p_run_name(2)}
        and row.get("setting") == "base"
    ]
    timeline = read_csv(CSV_TIMELINE)
    densify = read_csv(CSV_DENSIFY)
    mono = read_csv(CSV_MONO_V2)
    opacity = read_csv(CSV_SHEET_OPACITY)
    twin = read_csv(CSV_TWIN_REND)
    gable = read_csv(CSV_GABLE_MODE)
    old_cells = [
        row for row in read_csv(REPO / "docs/experiments/e5_c001_s2/tables/e5_c001_s2_arm_cells.csv")
        if row.get("arm") == "arm1"
    ]
    issues = read_csv(CSV_ISSUES)

    building_rows: list[dict[str, Any]] = []
    named_ids = set(s2.GOOD6 + s2.GS_FAIL5 + s2.TEXTURELESS_OBS3)
    for row in sorted(
        metrics,
        key=lambda item: (item.get("replicate", ""), s2.short_id(item.get("building_id", ""))),
    ):
        if s2.short_id(row.get("building_id", "")) not in named_ids:
            continue
        building_rows.append(
            {
                "run": row.get("replicate", ""),
                "분류": _report_group(row.get("building_id", "")),
                "building": s2.short_id(row.get("building_id", "")),
                "조립": row.get("has_lod22", ""),
                "유효": row.get("val3dity_valid", ""),
                "상태": row.get("status_reason", ""),
                "RMS_m": row.get("ref_rms_m", ""),
                "면수": row.get("roof_planes", ""),
                "참조면수": row.get("ref_roof_planes", ""),
            }
        )

    adjacent_rows: list[dict[str, Any]] = []
    for rep in ["r1", "r2"]:
        old = next((row for row in old_cells if row.get("replicate") == rep), {})
        new = next((row for row in arm_cells if row.get("replicate") == rep), {})
        adjacent_rows.append(
            {
                "run": rep,
                "cell": "Arm 1 (p=0.005)",
                "good6조립": old.get("good6_all_built", ""),
                "anchor": old.get("good6_raw_anchor_count", ""),
                "valid": old.get("valid_assembled", ""),
                "N": old.get("final_n_gaussians", ""),
                "rend_dist": old.get("rend_dist_mean_tail_m", ""),
                "4항": "pass" if s2.tf(old.get("pareto_all4")) else "fail",
            }
        )
        adjacent_rows.append(
            {
                "run": rep,
                "cell": "Arm 1p (p=0.05)",
                "good6조립": new.get("good6_all_built", ""),
                "anchor": new.get("good6_raw_anchor_count", ""),
                "valid": new.get("valid_assembled", ""),
                "N": new.get("final_n_gaussians", ""),
                "rend_dist": new.get("rend_dist_mean_tail_m", ""),
                "4항": new.get("pareto_all4", ""),
            }
        )

    five_k = {
        (row.get("replicate", ""), s2.short_id(row.get("building_id", ""))): row
        for row in timeline
        if row.get("step") == "5000"
    }
    final_timeline = {
        (row.get("replicate", ""), s2.short_id(row.get("building_id", ""))): row
        for row in timeline
        if row.get("step") == "30000"
    }
    timeline_summary = [
        {
            "run": row.get("replicate", ""),
            "building": s2.short_id(row.get("building_id", "")),
            "step": row.get("step", ""),
            "재료수": row.get("n_gaussians_in_footprint", ""),
            "z_p50": row.get("z_p50", ""),
            "opacity_p50": row.get("opacity_p50", ""),
        }
        for row in timeline
        if row.get("step") in {"5000", "30000"}
    ]
    collapse_ids = ["4907202", "4908168", "4908178"]
    collapse_built: list[str] = []
    for rep in ["r1", "r2"]:
        run_name = arm1p_run_name(int(rep[-1]))
        built = sum(
            s2.tf(row.get("has_lod22"))
            for row in metrics
            if row.get("run_name") == run_name
            and s2.short_id(row.get("building_id", "")) in collapse_ids
        )
        collapse_built.append(f"{rep}:{built}/3")
    five_k_text = "; ".join(
        f"{rep} "
        + "/".join(
            f"{short}={five_k.get((rep, short), {}).get('n_gaussians_in_footprint', '')}"
            for short in TIMELINE_IDS
        )
        for rep in ["r1", "r2"]
    )
    final_z_text = "; ".join(
        f"{rep} "
        + "/".join(
            f"{short}={final_timeline.get((rep, short), {}).get('z_p50', '')}"
            for short in collapse_ids
        )
        for rep in ["r1", "r2"]
    )
    rend_text = "/".join(row.get("rend_dist_mean_tail_m", "") for row in arm_cells)

    arm1p_opacity = [
        row
        for row in opacity
        if row.get("family") == "s2p"
        and row.get("cell") == "arm1p_p050_normal"
        and row.get("band") == "floater_595_615"
        and row.get("opacity_bin") == "gt_0p5"
    ]
    opacity_text = "/".join(
        f"{row.get('replicate')}:{row.get('fraction_of_band')} ({row.get('n_gaussians')}/{row.get('band_total')})"
        for row in arm1p_opacity
    ) or "산출 없음"
    prediction_rows = [
        {
            "예측": "P-F 5k 재료",
            "잠금": "수백 개 회복",
            "관찰": five_k_text,
        },
        {
            "예측": "P-F 붕괴 3동",
            "잠금": "3동 중 >=2동 조립 회복; 2런 요동 병기",
            "관찰": "; ".join(collapse_built),
        },
        {
            "예측": "P-F 청소",
            "잠금": "rend_dist <=0.5",
            "관찰": rend_text,
        },
        {
            "예측": "P-Fp 갈래 A/B",
            "잠금": "A=실물 층에도 이동 억제; B=이동 재발",
            "관찰": f">0.5 층 비율 {opacity_text}; 최종 z {final_z_text}",
        },
        {
            "예측": "P-G Arm 3",
            "잠금": "무늬없음 3채 형성 신호+양쪽 성공 비퇴행",
            "관찰": "A-1p >8 m 자동 분기로 Arm 3 미실행",
        },
        {
            "예측": "P-H 쌍둥이 청소",
            "잠금": "w100_p005가 0.5 부근이면 법선 청소 몫 없음; >=1이면 몫 실재",
            "관찰": "; ".join(
                f"{row.get('normal_state')}:{row.get('cell')}:{row.get('replicate')}={row.get('rend_dist_mean_tail_m')}"
                for row in twin
            ),
        },
    ]

    opacity_summary = [
        row
        for row in opacity
        if row.get("band") == "floater_595_615"
        and row.get("opacity_bin") == "gt_0p5"
    ]
    gable_summary = [
        row for row in gable
        if row.get("family") == "s2p" and row.get("target_four") == "true"
    ]
    densify_summary = [
        row for row in densify
        if row.get("interval_start_exclusive") == "0"
        and row.get("interval_end_inclusive") == "5000"
    ]

    lines = [
        "# W_E5_C001 S2p 법선×걸러내기 상호작용",
        "",
        "> 관찰 자료. 판정 0. C001 dense 18동, seed 2001, 30k, Arm 1p 2런. 정본 S0/S1/S2 산출물은 덮어쓰지 않았다.",
        "",
        "## 실행 범위",
        "",
        "- Arm 1p: Arm 1의 단안 법선 0.05를 유지하고 `prune_opa`만 0.005에서 0.05로 변경.",
        "- A-1p: Depth Anything V2 Large, 14동, 건물당 5뷰. 전체 건물 중앙 `8.10335 m`, 건물 분해 Pearson `0.77734`.",
        "- 잠금 자동 분기: `>8 m`이므로 Arm 3 제외. Pearson 구현·1k 게이트·Arm 3 학습은 수행하지 않음.",
        "- 파레토 ③: `rend_dist <0.4` pass, `0.4~0.6` boundary, `>0.6` fail로 기록. boundary는 통과/탈락으로 강제하지 않음.",
        "",
        "## 파레토 4항 v2.2",
        "",
        s2.md_table(
            arm_cells,
            [
                "replicate", "good6_all_built", "good6_raw_anchor_count",
                "good6_median_delta_vs_s1_m", "final_n_gaussians",
                "rend_dist_mean_tail_m", "rend_dist_status", "valid_assembled",
                "pareto_guardrail", "pareto_accuracy_nonregression",
                "pareto_cleaning", "pareto_validity_nonregression", "pareto_all4",
            ],
            4,
        ) if arm_cells else "_산출 없음_",
        "",
        "## 건물별 정답 채점",
        "",
        "> 표 머리는 확정 신표기다. 입력 한계 5동 중 여기에는 무늬없음·관측됨 3동만 포함하고, 파레토 전체 유효성 집계는 C001 18동 전부를 사용한다.",
        "",
        s2.md_table(
            building_rows,
            ["run", "분류", "building", "조립", "유효", "상태", "RMS_m", "면수", "참조면수"],
            40,
        ) if building_rows else "_산출 없음_",
        "",
        "- 양쪽 성공 6동 조립은 r1 `5/6`, r2 `4/6`; 유효 조립은 C001 전체 r1 `7/18`, r2 `6/18`이다.",
        "- 정확도 항은 r1/r2 짝 중앙 `+0.4987/+1.2135 m`, 파국 수 `1/2`로 기록됐다.",
        "",
        "## 사전 예측 대조",
        "",
        s2.md_table(prediction_rows, ["예측", "잠금", "관찰"], 10),
        "",
        "- 예측 장부는 연속 빗나감 2에서 출발했다. P-F의 '크게 빗나감' 해당 여부와 3연속·재프레임 기본 안건 전환은 김휘영 판정으로 남긴다.",
        "",
        "## 인접 셀 대조",
        "",
        "> Arm 1과 Arm 1p는 법선·모으기·깊이 설정을 고정하고 걸러내기 문턱만 0.005/0.05로 달리한다. Arm 3과 Arm 1의 대조는 A-1p 자동 기각으로 미실행이다.",
        "",
        s2.md_table(adjacent_rows, ["run", "cell", "good6조립", "anchor", "valid", "N", "rend_dist", "4항"], 8),
        "",
        "## 핵심 4동 시계열",
        "",
        s2.md_table(
            timeline_summary,
            ["run", "building", "step", "재료수", "z_p50", "opacity_p50"],
            20,
        ),
        "",
        "- 5k→final 재료수: 202 `463→15 / 368→11`, 168 `3→2 / 1→1`, 178 `239→6 / 71→0`(r1/r2). 5k 형성 신호와 final 생존은 분리해 기록한다.",
        "",
        "## 학습 0 확인",
        "",
        "### A-1p 단안 깊이",
        "",
        s2.md_table(
            mono,
            ["building_id", "group_new", "views_scored", "roof_height_error_abs_median_m", "roof_height_error_abs_p90_viewmedian_m", "mono_crop_depth_step_viewmedian_m"],
            20,
        ) if mono else "_산출 없음_",
        "",
        "### A-2p 플로터 층 불투명도",
        "",
        s2.md_table(
            opacity_summary,
            ["family", "cell", "replicate", "n_gaussians", "fraction_of_band", "band_total", "opacity_p50", "high_opacity_core_present"],
            24,
        ) if opacity_summary else "_산출 없음_",
        "",
        "- 중앙값 희석 확인: w100_p005 무법선 층은 중앙 `0.0370`이지만 `>0.5`가 `15,598/46,367=33.64%`로 고불투명 심이 존재한다. Arm 1p는 r1/r2 중앙 `0.6805/0.6256`, `>0.5` 비율 `54.16/53.23%`다.",
        "",
        "### A-3p 쌍둥이 rend_dist",
        "",
        s2.md_table(twin, ["normal_state", "cell", "replicate", "rend_dist_mean_tail_m", "rend_dist_p50_tail_m"], 8),
        "",
        "- w100_p005 무법선 `0.4070`은 법선 Arm 1 `0.4156/0.3577` 범위와 겹친다. 이 쌍둥이 지표에서는 Arm 1 청소 통과 중 법선 고유 몫이 분리되지 않는다.",
        "",
        "### A-5p 지붕 방향 모드",
        "",
        "> 정의: 3D 지붕면 법선, tilt>10도, 원형 거리 25도 이내 병합, 전체 경사면적 5% 이상 모드 유지. 따라서 저경사 4907202 참조는 이 정의에서 0모드다.",
        "",
        s2.md_table(
            gable_summary,
            ["replicate", "building_id", "has_lod22", "pred_direction_mode_count", "ref_direction_mode_count", "pred_mode_azimuths_deg", "ref_mode_azimuths_deg"],
            12,
        ) if gable_summary else "_산출 없음_",
        "",
        "- 4907184는 두 런 모두 참조 4모드를 4모드로 재현했다. 60098·4907186은 두 런 모두 참조 2모드 대비 1모드이며, 4907202는 저경사 참조 0모드 정의 아래 r1 0·r2 1모드다.",
        "",
        "## Densify 기록",
        "",
        s2.md_table(
            densify_summary,
            ["replicate", "building_id", "interval_start_exclusive", "interval_end_inclusive", "duplicate_events", "split_events", "total_events"],
            12,
        ) if densify_summary else "_산출 없음_",
        "",
        "## 정성 패널",
        "",
        "- 핵심 6동 다중소스 8way: `docs/figs/e5_c001_s2p/8way_panels/`.",
        "- 핵심 4동 Arm 1p 단계별 띠: `docs/figs/e5_c001_s2p/pipeline_strips/`.",
        "- 시계열: `docs/figs/e5_c001_s2p/timeline/`.",
        "- 플로터 층 분포: `docs/figs/e5_c001_s2p/sheet_opacity_dist/sheet_opacity_distribution.png`.",
        "",
        "## 기록된 이슈",
        "",
        s2.md_table(issues, ["part", "severity", "message", "path"], 20) if issues else "_기록된 실험 이슈 없음_",
        "",
        "## 산출",
        "",
        "- CSV: `docs/experiments/e5_c001_s2p/tables/e5_c001_s2p_arm_cells.csv`, `docs/experiments/e5_c001_s2p/tables/e5_c001_s2p_timeline_roofcrop.csv`, `docs/experiments/e5_c001_s2p/tables/e5_c001_s2p_densify_log.csv`, `docs/experiments/e5_c001_s2p/tables/e5_c001_s2p_monodepth_precheck_v2.csv`, `docs/experiments/e5_c001_s2p/tables/e5_c001_s2p_sheet_opacity_dist.csv`, `docs/experiments/e5_c001_s2p/tables/e5_c001_s2p_twin_rend_dist.csv`, `docs/experiments/e5_c001_s2p/tables/e5_c001_s2p_gable_mode.csv`, `docs/experiments/e5_c001_s2p/tables/e5_c001_s2p_rend_dist.csv`, `docs/experiments/e5_c001_s2p/tables/e5_c001_s2p_global_z_hist.csv`, `docs/experiments/e5_c001_s2p/tables/e5_c001_s2p_405_rescore_building.csv`, `docs/experiments/e5_c001_s2p/tables/e5_c001_s2p_inventory.csv`, `docs/experiments/e5_c001_s2p/tables/e5_c001_s2p_issues.csv`.",
        "- 런 지문: `phases/p2-gsjso/runs/20260710_e5_c001_s2p_interaction/train_fingerprints.csv`, `versions.txt`.",
        "- 실패·예외 장부: `phases/p2-gsjso/docs/issues.md`와 태스크 CSV를 함께 사용.",
        "",
    ]
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"report": rel(REPORT_PATH), "lines": len(lines)}, ensure_ascii=False))


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
    sub.add_parser("gable-mode")
    sub.add_parser("panels-8way")
    sub.add_parser("fingerprint-training")
    sub.add_parser("rend-dist")
    sub.add_parser("global-z-hist")
    sub.add_parser("arm-cells")
    sub.add_parser("versions")
    sub.add_parser("report")
    strips = sub.add_parser("pipeline-strips")
    strips.add_argument("--rep", choices=["1", "2", "all"], default="all")
    strips.add_argument("--device", default="cuda:0")
    strips.add_argument("--downscale", type=float, default=0.35)
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
    elif args.cmd == "gable-mode":
        gable_mode(args)
    elif args.cmd == "panels-8way":
        panels_8way(args)
    elif args.cmd == "fingerprint-training":
        fingerprint_training(args)
    elif args.cmd == "rend-dist":
        rend_dist_summary(args)
    elif args.cmd == "global-z-hist":
        global_z_hist(args)
    elif args.cmd == "arm-cells":
        build_arm_cells(args)
    elif args.cmd == "versions":
        versions(args)
    elif args.cmd == "report":
        report(args)
    elif args.cmd == "pipeline-strips":
        pipeline_strips(args)
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
