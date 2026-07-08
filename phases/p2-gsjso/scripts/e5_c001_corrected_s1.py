#!/usr/bin/env python3
"""E5 C001 corrected-S1 readout/evaluation wrapper.

Keeps the ③b-S1 readout/evaluation machinery unchanged, but redirects
checkpoint, readout, P0-eval, docs, and figure paths to corrected-S1 outputs.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import e5_c001_3b_s1 as s1
from e5_pilot_gate_tools import P0_RUNS, sha256_file


REPO = Path(__file__).resolve().parents[3]
RUN_ID = "20260709_e5_c001_corrected_s1"
P2_RUN_DIR = REPO / "phases/p2-gsjso/runs" / RUN_ID
P0_RUN_ID = "e5p_corrected_s1_20260709_C001"
P0_RUN_DIR = P0_RUNS / P0_RUN_ID
RESULTS_ROOT = REPO / "results/tum_transfer/e5_corrected_s1/C001/readout_ablation"
CKPT_ROOT = REPO / "results/tum_transfer/e5_corrected_s1/C001/runs"
DATA_ROOT = "results/tum_transfer/e5_pilot/C001/data_geoidfix_C001_buf20"
TORCH_EXTENSIONS = "results/tum_transfer/e5_corrected_s1/C001/torch_extensions_eval"
FIG_DIR = REPO / "docs/figs/e5_c001_corrected_s1"
READOUT_FIG_DIR = FIG_DIR / "readout"
REPORT_PATH = REPO / "docs/W_E5_C001_corrected_S1.md"
TEMP_READOUT_REPORT = REPO / "docs/W_E5_C001_corrected_S1_readout_tmp.md"

RUN_NAMES = [
    "gs_e5_C001_corrected_s1_sparse_r1",
    "gs_e5_C001_corrected_s1_dense_r1",
    "gs_e5_C001_corrected_s1_acmp_r1",
]
GPU_BY_ARM = {"sparse": "0", "dense": "1", "acmp": "1"}


def rel(path: Path | str) -> str:
    p = Path(path)
    try:
        return str(p.relative_to(REPO))
    except ValueError:
        return str(p)


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
    s1.S1_RUN_NAMES = RUN_NAMES
    s1.configure_ablation_module()
    s1.ab.COVERAGE_CSV = REPO / "docs/e5_c001_corrected_s1_coverage.csv"
    s1.ab.FILTER_CSV = REPO / "docs/e5_c001_corrected_s1_filter_contrib.csv"
    s1.ab.METRICS_CSV = REPO / "docs/e5_c001_corrected_s1_building_8way.csv"
    s1.ab.SUMMARY_CSV = REPO / "docs/e5_c001_corrected_s1_summary.csv"
    s1.ab.TRADEOFF_CSV = REPO / "docs/e5_c001_corrected_s1_tradeoff.csv"
    s1.ab.CASE_CSV = REPO / "docs/e5_c001_corrected_s1_representative_buildings.csv"
    s1.ab.INVENTORY_CSV = REPO / "docs/e5_c001_corrected_s1_inventory.csv"
    s1.ab.ISSUES_CSV = REPO / "docs/e5_c001_corrected_s1_issues.csv"
    s1.ab.RENDER_COVERAGE = REPO / "docs/e5_c001_corrected_s1_render_readout_coverage.csv"


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields: list[str] = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def elapsed_min_from_log(path: Path) -> str:
    if not path.exists():
        return ""
    marker = "[done] 30000 iter in "
    for line in reversed(path.read_text(encoding="utf-8", errors="replace").splitlines()):
        if marker in line:
            tail = line.split(marker, 1)[1]
            return tail.split(" min", 1)[0].strip()
    return ""


def train_fingerprints() -> None:
    import torch
    import yaml

    rows: list[dict[str, object]] = []
    for run_name in RUN_NAMES:
        arm = run_name.split("_")[-2]
        cfg = REPO / "configs/tum_mob/e5_corrected_s1" / f"{run_name}.yaml"
        eff = CKPT_ROOT / run_name / "effective_config.json"
        ckpt = CKPT_ROOT / run_name / "ckpt/final.pt"
        log = P2_RUN_DIR / "logs" / f"train_{arm}.log"
        cfg_data = yaml.safe_load(cfg.read_text(encoding="utf-8")) if cfg.exists() else {}
        effective = json.loads(eff.read_text(encoding="utf-8")) if eff.exists() else {}
        state = torch.load(ckpt, map_location="cpu", weights_only=False)
        rows.append(
            {
                "run_name": run_name,
                "arm": arm,
                "replicate": "r1",
                "seed": cfg_data.get("seed", ""),
                "config": rel(cfg),
                "config_sha256": sha256_file(cfg) if cfg.exists() else "missing",
                "effective_config": rel(eff),
                "effective_config_sha256": sha256_file(eff) if eff.exists() else "missing",
                "ckpt": rel(ckpt),
                "ckpt_sha256": sha256_file(ckpt) if ckpt.exists() else "missing",
                "log": rel(log),
                "elapsed_min": elapsed_min_from_log(log),
                "gpu_device": GPU_BY_ARM.get(arm, ""),
                "max_iter": cfg_data.get("max_iter", ""),
                "final_n_gaussians": state.get("n_prim", ""),
                "final_prune_opa": state.get("final_prune_opa", ""),
                "final_pruned": state.get("final_pruned", ""),
                "distort_normalization": effective.get("distort_normalization", ""),
                "distort_norm_denominator": effective.get("distort_norm_denominator", ""),
                "w_distort": effective.get("w_distort", ""),
                "seed_protect_until_iter": effective.get("seed_protect_until_iter", ""),
                "prune_opa": effective.get("prune_opa", ""),
                "readout": "corrected-S1 base readout(gssem; semantic-TSDF[minobs3, voxel0.05]; Roofer eps0.3/minpts15/complexity0.888)",
                "z_datum_history": "E5 C001 corrected-S1 uses zeta -558.3 linked constants; output P_utm in EPSG:25832 ellipsoidal frame",
            }
        )
    write_csv(P2_RUN_DIR / "train_fingerprints.csv", rows)
    print(json.dumps({"train_fingerprints": rel(P2_RUN_DIR / "train_fingerprints.csv"), "rows": len(rows)}, ensure_ascii=False))


def versions() -> None:
    P2_RUN_DIR.mkdir(parents=True, exist_ok=True)
    lines = [
        f"run_id: {RUN_ID}",
        f"timestamp_utc: {datetime.now(timezone.utc).isoformat()}",
        f"git_head: {s1.run_text(['git', 'rev-parse', 'HEAD'])}",
        f"git_branch: {s1.run_text(['git', 'branch', '--show-current'])}",
        "canonical_changed: no",
        "training: corrected-S1 3 arms, seed 2001",
        "verdict: none",
        f"train_fingerprints: {rel(P2_RUN_DIR / 'train_fingerprints.csv')}",
    ]
    (P2_RUN_DIR / "versions.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"versions": rel(P2_RUN_DIR / "versions.txt")}, ensure_ascii=False))


def evaluate_or_container(args: argparse.Namespace) -> None:
    configure()
    if os.environ.get("E5_CORRECTED_S1_EVAL_CONTAINER") == "1":
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
            "E5_CORRECTED_S1_EVAL_CONTAINER=1",
            "-e",
            "MPLCONFIGDIR=/tmp/matplotlib",
            "-v",
            f"{REPO}:/workspace/JointBuildGS",
            "-w",
            "/workspace/JointBuildGS",
            "jointbuildgs-p0-tools:t0",
            "python3",
            "phases/p2-gsjso/scripts/e5_c001_corrected_s1.py",
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
    sub.add_parser("fingerprint-training")
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
    if args.cmd == "fingerprint-training":
        train_fingerprints()
    if args.cmd == "versions":
        versions()


if __name__ == "__main__":
    main()
