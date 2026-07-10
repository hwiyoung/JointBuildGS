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
CONFIG_DIR = REPO / "configs/tum_mob/e5_s2p_interaction"
RESULTS_ROOT = REPO / "results/tum_transfer/e5_s2p_interaction/C001"
CKPT_ROOT = RESULTS_ROOT / "runs"
TRAIN_LOG_ROOT = RESULTS_ROOT / "train_logs"
TORCH_EXTENSIONS = RESULTS_ROOT / "torch_extensions"
BASE_CONFIG = REPO / "configs/tum_mob/e5_s2_direction_position/gs_e5_C001_s2_arm1_dense_r1.yaml"

FIG_DIR = REPO / "docs/figs/e5_c001_s2p"
CSV_INVENTORY = REPO / "docs/e5_c001_s2p_inventory.csv"
CSV_TIMELINE = REPO / "docs/e5_c001_s2p_timeline_roofcrop.csv"
CSV_DENSIFY = REPO / "docs/e5_c001_s2p_densify_log.csv"
CSV_ISSUES = REPO / "docs/e5_c001_s2p_issues.csv"

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
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists() or path.stat().st_size == 0:
        return []
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("generate-configs")
    train = sub.add_parser("train-one")
    train.add_argument("--run-name", required=True)
    train.add_argument("--gpu", default="0")
    sub.add_parser("timeline-roofcrop")
    sub.add_parser("densify-log")
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


if __name__ == "__main__":
    main()
