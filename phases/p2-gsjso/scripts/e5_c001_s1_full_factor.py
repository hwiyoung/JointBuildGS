#!/usr/bin/env python3
"""E5 C001 S1 full-factor experiment line.

Observation-only orchestration for the 2026-07-09 S1 factor order:
preview-gated dense training, dense 3-cell factor runs, existing corrected
recheck reuse, timeline/sheet diagnostics, unchanged readout/Roofer/evaluation,
and report tables.  Canonical S0/S1/corrected artifacts are not overwritten.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
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

import e5_c001_readout_ablation as ab  # noqa: E402
from e5_pilot_gate_tools import C001_IDS, DEV_IMAGE, P0_RUNS, sha256_file  # noqa: E402

ORIGINAL_AB_SOURCE_FOR = ab.source_for

RUN_ID = "20260709_e5_c001_s1_full_factor"
P2_RUN_DIR = REPO / "phases/p2-gsjso/runs" / RUN_ID
P0_RUN_ID = "e5p_s1_full_factor_20260709_C001"
P0_RUN_DIR = P0_RUNS / P0_RUN_ID
REPAIR_RUN_ID = "e5p_405_repair_20260709_C001"
REPAIRED_P0_RUN_DIR = P0_RUNS / REPAIR_RUN_ID / P0_RUN_ID
CONFIG_DIR = REPO / "configs/tum_mob/e5_s1_full_factor"
RESULTS_ROOT = REPO / "results/tum_transfer/e5_s1_full_factor/C001/readout_ablation"
CKPT_ROOT = REPO / "results/tum_transfer/e5_s1_full_factor/C001/runs"
TRAIN_LOG_ROOT = REPO / "results/tum_transfer/e5_s1_full_factor/C001/train_logs"
DATA_ROOT = "results/tum_transfer/e5_pilot/C001/data_geoidfix_C001_buf20"
TORCH_EXTENSIONS = "results/tum_transfer/e5_s1_full_factor/C001/torch_extensions_eval"
FIG_DIR = REPO / "docs/figs/e5_c001_s1_full_factor"
READOUT_FIG_DIR = FIG_DIR / "readout"
REPORT_PATH = REPO / "docs/W_E5_C001_S1완성판_요인.md"
TEMP_READOUT_REPORT = REPO / "docs/W_E5_C001_S1_full_factor_readout_tmp.md"

BASE_CONFIG = REPO / "configs/tum_mob/e5_corrected_s1_recheck/gs_e5_C001_corrected_s1_preprune_dense_r1.yaml"
REUSE_SOURCE_RUN = "gs_e5_C001_corrected_s1_preprune_keepall_dense_r1"
REUSE_SOURCE_DIR = REPO / "results/tum_transfer/e5_corrected_s1_recheck/C001/runs" / REUSE_SOURCE_RUN
REUSE_RUN = "gs_e5_C001_s1fac_w100_p050_dense_reuse"
SHIFT_UTM = np.array([690953.0, 5336071.0, 604.0], dtype=np.float64)
FOOTPRINTS_GEOJSON = REPO / "phases/p0-audit/data/work/footprints/lod2_ground_plan.geojson"

CSV_GRAD_SHARE = REPO / "docs/e5_c001_s1_full_grad_share.csv"
CSV_TIMELINE = REPO / "docs/e5_c001_s1_full_timeline_roofcrop.csv"
CSV_SHEET = REPO / "docs/e5_c001_s1_full_sheet_identity.csv"
CSV_FACTOR = REPO / "docs/e5_c001_s1_full_factor_cells.csv"
CSV_DEPTH_SOURCE = REPO / "docs/e5_c001_s1_full_depth_source.csv"
CSV_INVENTORY = REPO / "docs/e5_c001_s1_full_inventory.csv"
CSV_ISSUES = REPO / "docs/e5_c001_s1_full_issues.csv"
CSV_405_REPAIR = REPO / "docs/e5_c001_s1_full_405_rescore.csv"

TIMELINE_IDS_DENSE = ["4907202", "4908178", "4908168", "4907184"]
TIMELINE_IDS_OTHER = ["4907202"]
STRIP_IDS = ["4907202", "4908168", "4907185", "4907184", "60098", "8568392"]
NORMAL6 = ["4907184", "4908168", "4907202", "4907198", "4907185", "4908178"]


@dataclass(frozen=True)
class Cell:
    key: str
    run_name: str
    w_distort: float
    prune_opa: float
    role: str
    reuse: bool = False


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
            fh.write("")
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
    write_csv(CSV_ISSUES, rows)
    issue_md = REPO / "docs/issues.md"
    if issue_md.exists():
        line = f"- 2026-07-09 S1 full factor {part}: {severity} - {message}"
        if path:
            line += f" ({rel(path)})"
        text = issue_md.read_text(encoding="utf-8")
        if line not in text:
            with issue_md.open("a", encoding="utf-8") as fh:
                fh.write(line + "\n")


def capture(cmd: list[str]) -> str:
    try:
        proc = subprocess.run(cmd, cwd=REPO, text=True, capture_output=True, check=False)
    except FileNotFoundError as exc:
        return f"not_available:{exc.filename}"
    return ((proc.stdout or "") + (proc.stderr or "")).strip()


def run(cmd: list[str], log_path: Path | None = None, check: bool = True, quiet: bool = False) -> subprocess.CompletedProcess[str]:
    if log_path:
        log_path.parent.mkdir(parents=True, exist_ok=True)
    print("+ " + " ".join(cmd[:10]) + (" ..." if len(cmd) > 10 else ""), flush=True)
    proc = subprocess.run(cmd, cwd=REPO, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if log_path:
        log_path.write_text("+ " + " ".join(cmd) + "\n" + (proc.stdout or ""), encoding="utf-8")
    if proc.stdout and not quiet:
        print(proc.stdout, end="", flush=True)
    if check:
        proc.check_returncode()
    return proc


def yaml_load(path: Path) -> dict[str, Any]:
    import yaml

    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def yaml_dump(path: Path, payload: dict[str, Any]) -> None:
    import yaml

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(payload, allow_unicode=True, sort_keys=False), encoding="utf-8")


def preview_run_name(w_distort: int) -> str:
    return f"gs_e5_C001_s1fac_preview_w{w_distort}_p050_dense_r1"


def trained_run_name(w_distort: int, prune_opa: float) -> str:
    p = "p005" if abs(prune_opa - 0.005) < 1e-9 else "p050"
    return f"gs_e5_C001_s1fac_w{w_distort}_{p}_dense_r1"


def selected_path() -> Path:
    return P2_RUN_DIR / "selected_distort_weight.json"


def selected_w(default: int | None = None) -> int:
    path = selected_path()
    if path.exists():
        payload = json.loads(path.read_text(encoding="utf-8"))
        return int(payload["selected_w_distort"])
    if default is not None:
        return int(default)
    raise RuntimeError(f"missing selected weight file: {rel(path)}; run summarize-preview first")


def cells_for_weight(w: int) -> list[Cell]:
    return [
        Cell("w100_p050_reuse", REUSE_RUN, 100.0, 0.05, "reused corrected recheck baseline", reuse=True),
        Cell("w100_p005", trained_run_name(100, 0.005), 100.0, 0.005, "prune relaxation only"),
        Cell(f"w{w}_p050", trained_run_name(w, 0.05), float(w), 0.05, "distortion strength only"),
        Cell(f"w{w}_p005", trained_run_name(w, 0.005), float(w), 0.005, "combined full S1 cell"),
    ]


def all_candidate_cells() -> list[Cell]:
    out = [Cell("w100_p050_reuse", REUSE_RUN, 100.0, 0.05, "reused corrected recheck baseline", reuse=True)]
    seen = {REUSE_RUN}
    for w in [240, 480]:
        for cell in cells_for_weight(w):
            if cell.run_name not in seen:
                out.append(cell)
                seen.add(cell.run_name)
    return out


def write_config(run_name: str, *, w_distort: float, prune_opa: float, max_iter: int, preview: bool) -> Path:
    cfg = yaml_load(BASE_CONFIG)
    cfg["w_distort"] = float(w_distort)
    cfg["prune_opa"] = float(prune_opa)
    cfg["final_prune_opa"] = 0.0
    cfg["ckpt_every"] = 500 if preview else 5000
    cfg["max_iter"] = int(max_iter)
    cfg["eval_every"] = 2000 if not preview else 999999
    cfg["loss_grad_audit_every"] = 50 if preview else 500
    cfg["loss_grad_audit_params"] = "geometry"
    cfg["out_dir"] = f"/workspace/JointBuildGS/{rel(CKPT_ROOT / run_name)}"
    path = CONFIG_DIR / f"{run_name}.yaml"
    yaml_dump(path, cfg)
    return path


def link_reuse_alias() -> None:
    alias = CKPT_ROOT / REUSE_RUN
    (alias / "ckpt").mkdir(parents=True, exist_ok=True)
    links = [
        (REUSE_SOURCE_DIR / "ckpt/final.pt", alias / "ckpt/final.pt"),
        (REUSE_SOURCE_DIR / "effective_config.json", alias / "effective_config.json"),
    ]
    for src, dst in links:
        if not src.exists():
            raise FileNotFoundError(src)
        if dst.exists() or dst.is_symlink():
            dst.unlink()
        os.symlink(os.path.relpath(src, dst.parent), dst)


def generate_configs(_args: argparse.Namespace) -> None:
    P2_RUN_DIR.mkdir(parents=True, exist_ok=True)
    for w in [240, 480]:
        write_config(preview_run_name(w), w_distort=w, prune_opa=0.05, max_iter=1000, preview=True)
    for cell in all_candidate_cells():
        if not cell.reuse:
            write_config(cell.run_name, w_distort=cell.w_distort, prune_opa=cell.prune_opa, max_iter=30000, preview=False)
    link_reuse_alias()
    rows = []
    for path in sorted(CONFIG_DIR.glob("*.yaml")):
        cfg = yaml_load(path)
        rows.append(
            {
                "config": rel(path),
                "run_name": path.stem,
                "w_distort": cfg.get("w_distort", ""),
                "prune_opa": cfg.get("prune_opa", ""),
                "final_prune_opa": cfg.get("final_prune_opa", ""),
                "max_iter": cfg.get("max_iter", ""),
                "ckpt_every": cfg.get("ckpt_every", ""),
                "loss_grad_audit_every": cfg.get("loss_grad_audit_every", ""),
                "out_dir": cfg.get("out_dir", ""),
                "sha256": sha256_file(path),
            }
        )
    write_csv(CSV_INVENTORY, rows)
    print(json.dumps({"configs": len(rows), "inventory": rel(CSV_INVENTORY)}, ensure_ascii=False))


def docker_train(config: Path, gpu: str, log_path: Path) -> int:
    log_path.parent.mkdir(parents=True, exist_ok=True)
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
        f"CUDA_VISIBLE_DEVICES={gpu}",
        "-e",
        f"TORCH_EXTENSIONS_DIR=/workspace/JointBuildGS/{TORCH_EXTENSIONS}",
        "-v",
        f"{REPO}:/workspace/JointBuildGS",
        "-w",
        "/workspace/JointBuildGS",
        DEV_IMAGE,
        "python",
        "-m",
        "src.stage2.train",
        "--config",
        rel(config),
    ]
    start = datetime.now(timezone.utc).isoformat()
    proc = subprocess.run(cmd, cwd=REPO, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    end = datetime.now(timezone.utc).isoformat()
    log_path.write_text(
        f"START_UTC={start}\nHOST_GPU={gpu}\nCONFIG={rel(config)}\n"
        f"COMMAND={' '.join(cmd)}\n"
        + (proc.stdout or "")
        + f"\nEND_UTC={end}\nRETURN_CODE={proc.returncode}\n",
        encoding="utf-8",
    )
    print(proc.stdout or "", end="", flush=True)
    print(json.dumps({"config": rel(config), "gpu": gpu, "return_code": proc.returncode, "log": rel(log_path)}, ensure_ascii=False), flush=True)
    return int(proc.returncode)


def train_one(args: argparse.Namespace) -> None:
    config = CONFIG_DIR / f"{args.run_name}.yaml"
    if not config.exists():
        raise FileNotFoundError(config)
    rc = docker_train(config, args.gpu, TRAIN_LOG_ROOT / f"{args.run_name}.log")
    if rc != 0 and args.check:
        raise SystemExit(rc)


def parse_train_log(path: Path) -> dict[str, str]:
    out = {"start_utc": "", "end_utc": "", "host_gpu": "", "return_code": "", "elapsed_min": ""}
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
        elif "[done]" in line and " iter in " in line:
            out["elapsed_min"] = line.split(" iter in ", 1)[1].split(" min", 1)[0].strip()
    return out


def audit_csv_for(run_name: str) -> Path:
    return CKPT_ROOT / run_name / "audit/loss_grad_norms.csv"


def summarize_audit(run_name: str) -> dict[str, Any]:
    rows = read_csv(audit_csv_for(run_name))
    by_comp: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        by_comp.setdefault(row.get("component", ""), []).append(row)
    dist = by_comp.get("distort", [])
    vals_loss = [num(r.get("weighted_loss_share")) for r in dist]
    vals_grad = [num(r.get("grad_norm_share")) for r in dist]
    vals_total = [num(r.get("total_loss")) for r in rows if r.get("component") == "photo"]
    finite = all(v is not None and math.isfinite(v) for v in vals_total)
    return {
        "run_name": run_name,
        "audit_csv": rel(audit_csv_for(run_name)) if audit_csv_for(run_name).exists() else "",
        "audit_rows": len(rows),
        "max_total_loss": max(vals_total) if vals_total else None,
        "last_total_loss": vals_total[-1] if vals_total else None,
        "all_total_loss_finite": finite,
        "distort_weighted_loss_share_max": max([v for v in vals_loss if v is not None], default=None),
        "distort_grad_norm_share_max": max([v for v in vals_grad if v is not None], default=None),
        "distort_weighted_loss_share_last": vals_loss[-1] if vals_loss else None,
        "distort_grad_norm_share_last": vals_grad[-1] if vals_grad else None,
    }


def summarize_preview(_args: argparse.Namespace) -> None:
    rows: list[dict[str, Any]] = []
    ok_by_w: dict[int, bool] = {}
    for w in [240, 480]:
        rn = preview_run_name(w)
        log = TRAIN_LOG_ROOT / f"{rn}.log"
        info = parse_train_log(log)
        s = summarize_audit(rn)
        final_ckpt = CKPT_ROOT / rn / "ckpt/final.pt"
        return_ok = info.get("return_code") == "0"
        finite_ok = bool(s["all_total_loss_finite"])
        loss_share = s["distort_weighted_loss_share_max"]
        grad_share = s["distort_grad_norm_share_max"]
        share_ok = (loss_share is not None and loss_share <= 0.40) and (grad_share is not None and grad_share <= 0.40)
        ok = return_ok and finite_ok and share_ok and final_ckpt.exists()
        ok_by_w[w] = ok
        rows.append(
            {
                "stage": "B-0-preview",
                "w_distort": w,
                "linear_equiv_note": "w=240≈50, w=480≈100 under locked interpretation",
                "run_name": rn,
                "return_code": info.get("return_code", ""),
                "elapsed_min": info.get("elapsed_min", ""),
                "final_ckpt_exists": str(final_ckpt.exists()).lower(),
                "gate_return_ok": str(return_ok).lower(),
                "gate_finite_ok": str(finite_ok).lower(),
                "gate_share_le_040": str(share_ok).lower(),
                "preview_gate_ok": str(ok).lower(),
                **{k: fmt(v) for k, v in s.items() if k not in {"run_name", "audit_csv"}},
                "audit_csv": s["audit_csv"],
                "log": rel(log),
            }
        )
    if ok_by_w.get(480):
        selected = 480
        reason = "480 preview completed and did not exceed 40% weighted-loss/gradient-share gates"
    elif ok_by_w.get(240):
        selected = 240
        reason = "480 preview failed or exceeded share gate; 240 preview accepted"
    else:
        selected = None
        reason = "240 and 480 previews failed or exceeded gates; main training must not start"
        append_issue("B-0", "error", reason, CSV_GRAD_SHARE)
    for row in rows:
        row["selected_w_distort"] = selected if selected is not None else ""
        row["selection_reason"] = reason
    write_csv(CSV_GRAD_SHARE, rows)
    if selected is not None:
        selected_path().parent.mkdir(parents=True, exist_ok=True)
        selected_path().write_text(
            json.dumps({"selected_w_distort": selected, "reason": reason, "created_utc": datetime.now(timezone.utc).isoformat()}, ensure_ascii=False, indent=2)
            + "\n",
            encoding="utf-8",
        )
    print(json.dumps({"grad_share": rel(CSV_GRAD_SHARE), "selected_w_distort": selected, "reason": reason}, ensure_ascii=False))


def configure_ablation_module(weight: int | None = None) -> list[Cell]:
    cells = cells_for_weight(selected_w(weight))
    ab.RUN_ID = RUN_ID
    ab.P2_RUN_DIR = P2_RUN_DIR
    ab.P0_RUN_ID = P0_RUN_ID
    ab.P0_RUN_DIR = P0_RUN_DIR
    ab.RESULTS_ROOT = RESULTS_ROOT
    ab.CKPT_ROOT = CKPT_ROOT
    ab.TRAIN_RUN_DIR = P2_RUN_DIR
    ab.CANON_GATE_DIR = REPO / "phases/p0-audit/runs/e5p_gate_20260707_C001"
    ab.DATA_ROOT = DATA_ROOT
    ab.TORCH_EXTENSIONS = TORCH_EXTENSIONS
    ab.FIG_DIR = READOUT_FIG_DIR
    ab.REPORT_PATH = TEMP_READOUT_REPORT
    ab.COVERAGE_CSV = REPO / "docs/e5_c001_s1_full_coverage.csv"
    ab.FILTER_CSV = REPO / "docs/e5_c001_s1_full_filter_contrib.csv"
    ab.METRICS_CSV = REPO / "docs/e5_c001_s1_full_building_8way.csv"
    ab.SUMMARY_CSV = REPO / "docs/e5_c001_s1_full_summary.csv"
    ab.TRADEOFF_CSV = REPO / "docs/e5_c001_s1_full_tradeoff.csv"
    ab.CASE_CSV = REPO / "docs/e5_c001_s1_full_representative_buildings.csv"
    ab.INVENTORY_CSV = REPO / "docs/e5_c001_s1_full_readout_inventory.csv"
    ab.ISSUES_CSV = REPO / "docs/e5_c001_s1_full_readout_issues.csv"
    ab.RENDER_COVERAGE = REPO / "docs/e5_c001_s1_full_render_readout_coverage.csv"
    ab.SETTINGS = [ab.Setting("base", "S1 factor-cell canonical readout", min_obs=3, voxel=0.05, sor="on", sor_std=2.0)]

    def source_for(setting: ab.Setting, run_name: str) -> Any:
        src = ORIGINAL_AB_SOURCE_FOR(setting, run_name)
        repaired_root = REPAIRED_P0_RUN_DIR / setting.key
        repaired_status = repaired_root / "status" / f"{run_name}_run_1.csv"
        repaired_cityjson = repaired_root / "cityjson" / f"{run_name}_run_1.city.json"
        if repaired_status.exists() and repaired_cityjson.exists():
            src.status_path = repaired_status
            src.cityjson_path = repaired_cityjson
            src.source_badge = f"{setting.key}_405repair"
            src.readout = src.readout + "; 405 winding repair overlay"
        return src

    def selected_run_names(args: argparse.Namespace) -> list[str]:
        names = [cell.run_name for cell in cells]
        selected = getattr(args, "runs", None)
        if not selected:
            return names
        missing = sorted(set(selected) - set(names))
        if missing:
            raise RuntimeError(f"unknown factor run names: {missing}")
        selected_set = set(selected)
        return [name for name in names if name in selected_set]

    def write_readout_report(*_args: Any, **_kwargs: Any) -> None:
        TEMP_READOUT_REPORT.parent.mkdir(parents=True, exist_ok=True)
        TEMP_READOUT_REPORT.write_text(
            "# E5 C001 S1 full-factor readout tmp\n\n"
            "Generated by the unchanged C001 ablation harness redirected to S1 factor cells.\n",
            encoding="utf-8",
        )

    ab.selected_run_names = selected_run_names
    ab.source_for = source_for
    ab.write_report = write_readout_report
    link_reuse_alias()
    return cells


def evaluate_or_container(args: argparse.Namespace) -> None:
    configure_ablation_module(args.weight)
    if os.environ.get("E5_S1_FACTOR_EVAL_CONTAINER") == "1":
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
            "E5_S1_FACTOR_EVAL_CONTAINER=1",
            "-e",
            "MPLCONFIGDIR=/tmp/matplotlib",
            "-v",
            f"{REPO}:/workspace/JointBuildGS",
            "-w",
            "/workspace/JointBuildGS",
            "jointbuildgs-p0-tools:t0",
            "python3",
            "phases/p2-gsjso/scripts/e5_c001_s1_full_factor.py",
            "evaluate",
            "--weight",
            str(args.weight or selected_w()),
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


def readout_like(args: argparse.Namespace) -> None:
    configure_ablation_module(args.weight)
    if args.cmd in {"readout", "all"}:
        ab.run_readout(args)
    if args.cmd in {"assemble", "all"}:
        ab.run_assemble(args)
    if args.cmd in {"evaluate", "all"}:
        evaluate_or_container(args)


def load_footprints(ids: list[str]) -> dict[str, dict[str, Any]]:
    wanted = {full_id(x) for x in ids}
    payload = json.loads(FOOTPRINTS_GEOJSON.read_text(encoding="utf-8"))
    out: dict[str, dict[str, Any]] = {}
    for feat in payload["features"]:
        bid = feat.get("properties", {}).get("building_id")
        if bid not in wanted:
            continue
        geom = feat["geometry"]
        if geom["type"] == "Polygon":
            rings = [np.asarray(geom["coordinates"][0], dtype=np.float64)]
        elif geom["type"] == "MultiPolygon":
            rings = [np.asarray(poly[0], dtype=np.float64) for poly in geom["coordinates"]]
        else:
            continue
        xy = np.concatenate([r[:, :2] for r in rings], axis=0)
        out[bid] = {
            "rings": [r[:, :2] for r in rings],
            "paths": [MplPath(r[:, :2], closed=True) for r in rings],
            "bbox": (float(xy[:, 0].min()), float(xy[:, 1].min()), float(xy[:, 0].max()), float(xy[:, 1].max())),
        }
    return out


def checkpoint_path(run_root: Path, run_name: str, step: int | str) -> Path:
    if step == "final" or step == 30000:
        return run_root / run_name / "ckpt/final.pt"
    return run_root / run_name / "ckpt" / f"step_{int(step):06d}.pt"


def gaussian_stats_for_ckpt(ckpt: Path, footprints: dict[str, dict[str, Any]], target_ids: list[str]) -> list[dict[str, Any]]:
    import torch

    if not ckpt.exists():
        return []
    payload = torch.load(ckpt, map_location="cpu", weights_only=False)
    state = payload["state_dict"]
    means = state["means"].detach().cpu().numpy().astype(np.float64) + SHIFT_UTM
    opa = torch.sigmoid(state["opacities_raw"].detach().cpu().float()).numpy()
    rows: list[dict[str, Any]] = []
    for sid in target_ids:
        bid = full_id(sid)
        fp = footprints.get(bid)
        if fp is None:
            continue
        x0, y0, x1, y1 = fp["bbox"]
        m = (means[:, 0] >= x0 - 2.0) & (means[:, 0] <= x1 + 2.0) & (means[:, 1] >= y0 - 2.0) & (means[:, 1] <= y1 + 2.0)
        idx = np.array([], dtype=np.int64)
        if np.any(m):
            cand = means[m]
            inside = np.zeros(cand.shape[0], dtype=bool)
            for path in fp["paths"]:
                inside |= path.contains_points(cand[:, :2])
            idx = np.where(m)[0][inside]
        z = means[idx, 2] if idx.size else np.array([], dtype=float)
        op = opa[idx] if idx.size else np.array([], dtype=float)
        rows.append(
            {
                "building_id": bid,
                "n_gaussians_in_footprint": int(idx.size),
                "z_p50": float(np.quantile(z, 0.50)) if z.size else None,
                "z_std": float(np.std(z)) if z.size else None,
                "opacity_p50": float(np.quantile(op, 0.50)) if op.size else None,
                "opacity_p05": float(np.quantile(op, 0.05)) if op.size else None,
                "opacity_p95": float(np.quantile(op, 0.95)) if op.size else None,
            }
        )
    return rows


def timeline_roofcrop(args: argparse.Namespace) -> None:
    ids = sorted(set(TIMELINE_IDS_DENSE + TIMELINE_IDS_OTHER))
    fps = load_footprints(ids)
    rows: list[dict[str, Any]] = []
    recheck_root = REPO / "results/tum_transfer/e5_corrected_s1_recheck/C001/runs"
    corrected_root = REPO / "results/tum_transfer/e5_corrected_s1/C001/runs"
    s1_root = REPO / "results/tum_transfer/e5_3b_s1/C001/runs"
    selected = None
    if args.include_factor and selected_path().exists():
        selected = selected_w()
    families: list[tuple[str, Path, str, list[str], list[int | str]]] = [
        ("corrected_recheck", recheck_root, "gs_e5_C001_corrected_s1_preprune_dense_r1", TIMELINE_IDS_DENSE, [5000, 10000, 15000, 20000, 25000, "final"]),
        ("corrected_recheck", recheck_root, "gs_e5_C001_corrected_s1_preprune_sparse_r1", TIMELINE_IDS_OTHER, [5000, 10000, 15000, 20000, 25000, "final"]),
        ("corrected_recheck", recheck_root, "gs_e5_C001_corrected_s1_preprune_acmp_r1", TIMELINE_IDS_OTHER, [5000, 10000, 15000, 20000, 25000, "final"]),
        ("corrected_original", corrected_root, "gs_e5_C001_corrected_s1_dense_r1", TIMELINE_IDS_DENSE, [10000, 20000, "final"]),
        ("corrected_original", corrected_root, "gs_e5_C001_corrected_s1_sparse_r1", TIMELINE_IDS_OTHER, [10000, 20000, "final"]),
        ("corrected_original", corrected_root, "gs_e5_C001_corrected_s1_acmp_r1", TIMELINE_IDS_OTHER, [10000, 20000, "final"]),
        ("s1_original", s1_root, "gs_e5_C001_s1_dense_r1", TIMELINE_IDS_DENSE, [10000, 20000, "final"]),
    ]
    if selected is not None:
        for cell in cells_for_weight(selected):
            if not cell.reuse:
                families.append((f"factor_{cell.key}", CKPT_ROOT, cell.run_name, TIMELINE_IDS_DENSE, [5000, 10000, 15000, 20000, 25000, "final"]))
    for family, root, run_name, target_ids, steps in families:
        arm = run_name.split("_")[-2]
        for step in steps:
            ckpt = checkpoint_path(root, run_name, step)
            for item in gaussian_stats_for_ckpt(ckpt, fps, target_ids):
                rows.append(
                    {
                        "family": family,
                        "run_name": run_name,
                        "arm": arm,
                        "step": 30000 if step == "final" else step,
                        "ckpt": rel(ckpt),
                        **{k: fmt(v) for k, v in item.items()},
                    }
                )
    write_csv(CSV_TIMELINE, rows)
    plot_timeline(rows)
    print(json.dumps({"timeline": rel(CSV_TIMELINE), "rows": len(rows)}, ensure_ascii=False))


def plot_timeline(rows: list[dict[str, Any]]) -> None:
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    for sid in ["4907202", "4908178", "4908168", "4907184"]:
        bid = full_id(sid)
        part = [r for r in rows if r.get("building_id") == bid and r.get("arm") == "dense" and r.get("family") in {"corrected_recheck", "corrected_original", "s1_original"}]
        if not part:
            continue
        fig, axes = plt.subplots(1, 3, figsize=(11.0, 3.5))
        for family in sorted({r["family"] for r in part}):
            g = sorted([r for r in part if r["family"] == family], key=lambda x: int(x["step"]))
            x = [int(r["step"]) / 1000 for r in g]
            axes[0].plot(x, [num(r["n_gaussians_in_footprint"]) or 0 for r in g], marker="o", label=family)
            axes[1].plot(x, [num(r["z_p50"]) or np.nan for r in g], marker="o", label=family)
            axes[2].plot(x, [num(r["opacity_p50"]) or np.nan for r in g], marker="o", label=family)
        axes[0].set_ylabel("count")
        axes[1].set_ylabel("z p50")
        axes[2].set_ylabel("opacity p50")
        for ax in axes:
            ax.set_xlabel("k iter")
            ax.grid(alpha=0.25)
        axes[0].legend(fontsize=7)
        fig.suptitle(f"dense roofcrop timeline {sid}", fontsize=11)
        fig.tight_layout()
        fig.savefig(FIG_DIR / f"timeline_dense_{sid}.png", dpi=180)
        plt.close(fig)


def sheet_identity(_args: argparse.Namespace) -> None:
    import torch

    specs = [
        ("corrected_original", "dense", REPO / "results/tum_transfer/e5_corrected_s1/C001/runs/gs_e5_C001_corrected_s1_dense_r1/ckpt/final.pt"),
        ("corrected_original", "sparse", REPO / "results/tum_transfer/e5_corrected_s1/C001/runs/gs_e5_C001_corrected_s1_sparse_r1/ckpt/final.pt"),
        ("corrected_recheck", "dense", REPO / "results/tum_transfer/e5_corrected_s1_recheck/C001/runs/gs_e5_C001_corrected_s1_preprune_dense_r1/ckpt/final.pt"),
        ("corrected_recheck", "sparse", REPO / "results/tum_transfer/e5_corrected_s1_recheck/C001/runs/gs_e5_C001_corrected_s1_preprune_sparse_r1/ckpt/final.pt"),
    ]
    rows: list[dict[str, Any]] = []
    slice_points: list[tuple[str, str, np.ndarray, np.ndarray]] = []
    for family, arm, ckpt in specs:
        if not ckpt.exists():
            append_issue("A-2", "warn", "checkpoint missing for sheet identity", ckpt)
            continue
        payload = torch.load(ckpt, map_location="cpu", weights_only=False)
        state = payload["state_dict"]
        means = state["means"].detach().cpu().numpy().astype(np.float64) + SHIFT_UTM
        op = torch.sigmoid(state["opacities_raw"].detach().cpu().float()).numpy()
        z = means[:, 2]
        for band, lo, hi in [("roof_band_560_590", 560.0, 590.0), ("sheet_band_595_615", 595.0, 615.0)]:
            m = (z >= lo) & (z <= hi)
            pts = means[m]
            opa = op[m]
            rows.append(
                {
                    "family": family,
                    "arm": arm,
                    "band": band,
                    "z_min": lo,
                    "z_max": hi,
                    "n_gaussians": int(m.sum()),
                    "x_min": fmt(float(pts[:, 0].min()) if len(pts) else None),
                    "x_max": fmt(float(pts[:, 0].max()) if len(pts) else None),
                    "y_min": fmt(float(pts[:, 1].min()) if len(pts) else None),
                    "y_max": fmt(float(pts[:, 1].max()) if len(pts) else None),
                    "z_p50": fmt(float(np.quantile(pts[:, 2], 0.5)) if len(pts) else None),
                    "opacity_p50": fmt(float(np.quantile(opa, 0.5)) if len(opa) else None),
                    "opacity_p95": fmt(float(np.quantile(opa, 0.95)) if len(opa) else None),
                    "ckpt": rel(ckpt),
                }
            )
            if band == "sheet_band_595_615" and len(pts):
                slice_points.append((family, arm, pts[:, :2], opa))
        hist, edges = np.histogram(z, bins=np.arange(520, 641, 2))
        for i, count in enumerate(hist):
            rows.append(
                {
                    "family": family,
                    "arm": arm,
                    "band": "z_hist_2m",
                    "z_min": float(edges[i]),
                    "z_max": float(edges[i + 1]),
                    "n_gaussians": int(count),
                    "ckpt": rel(ckpt),
                }
            )
    write_csv(CSV_SHEET, rows)
    plot_sheet(rows, slice_points)
    print(json.dumps({"sheet_identity": rel(CSV_SHEET), "rows": len(rows)}, ensure_ascii=False))


def plot_sheet(rows: list[dict[str, Any]], slice_points: list[tuple[str, str, np.ndarray, np.ndarray]]) -> None:
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    hist_rows = [r for r in rows if r.get("band") == "z_hist_2m"]
    fig, axes = plt.subplots(1, 2, figsize=(11.0, 4.0))
    for family, arm in sorted({(r["family"], r["arm"]) for r in hist_rows}):
        g = sorted([r for r in hist_rows if r["family"] == family and r["arm"] == arm], key=lambda x: float(x["z_min"]))
        x = [(float(r["z_min"]) + float(r["z_max"])) / 2.0 for r in g]
        y = [int(r["n_gaussians"]) for r in g]
        axes[0].plot(x, y, label=f"{family}:{arm}", linewidth=1.1)
    axes[0].axvspan(560, 590, color="#90be6d", alpha=0.15)
    axes[0].axvspan(595, 615, color="#f94144", alpha=0.12)
    axes[0].set_xlabel("z (m)")
    axes[0].set_ylabel("gaussians / 2m bin")
    axes[0].grid(alpha=0.25)
    axes[0].legend(fontsize=7)
    for family, arm, xy, op in slice_points:
        if len(xy) > 30000:
            rng = np.random.default_rng(20260709)
            idx = rng.choice(np.arange(len(xy)), size=30000, replace=False)
            xy = xy[idx]
            op = op[idx]
        axes[1].scatter(xy[:, 0], xy[:, 1], s=1, alpha=0.25, label=f"{family}:{arm}", c=op, cmap="viridis", vmin=0, vmax=1)
    axes[1].set_aspect("equal", adjustable="box")
    axes[1].set_title("595-615m sheet horizontal slice")
    axes[1].set_xlabel("Easting")
    axes[1].set_ylabel("Northing")
    axes[1].grid(alpha=0.15)
    axes[1].legend(fontsize=6)
    fig.tight_layout()
    fig.savefig(FIG_DIR / "sheet_identity_hist_slice.png", dpi=180)
    plt.close(fig)


def depth_source(_args: argparse.Namespace) -> None:
    rows = []
    config_paths = sorted((REPO / "configs/tum_mob/e5_corrected_s1_recheck").glob("gs_e5_C001_corrected_s1_preprune_*_r1.yaml"))
    for path in config_paths:
        cfg = yaml_load(path)
        rows.append(
            {
                "run_name": path.stem,
                "arm": path.stem.split("_")[-2],
                "data_root": cfg.get("data_root", ""),
                "load_depth": cfg.get("load_depth", ""),
                "init_pointcloud": cfg.get("init_pointcloud", ""),
                "depth_source_interpretation": "common C001 data_root depth maps; arm changes only init_pointcloud seed family",
                "effective_config_absence_reason": "train.py effective_config stores scalar loss/schedule/densification settings, not data_root or resolved per-frame depth paths",
                "config": rel(path),
            }
        )
    write_csv(CSV_DEPTH_SOURCE, rows)
    print(json.dumps({"depth_source": rel(CSV_DEPTH_SOURCE), "rows": len(rows)}, ensure_ascii=False))


def summarize_source(metrics: list[dict[str, str]], run_name: str) -> dict[str, Any]:
    part = [r for r in metrics if r.get("setting") == "base" and r.get("run_name") == run_name]
    rms = [num(r.get("ref_rms_m")) for r in part]
    rms_vals = [v for v in rms if v is not None]
    return {
        "n": len(part),
        "has_lod22": sum(tf(r.get("has_lod22")) for r in part),
        "valid_assembled": sum(tf(r.get("has_lod22")) and tf(r.get("val3dity_valid")) for r in part),
        "invalid_assembled": sum(tf(r.get("has_lod22")) and not tf(r.get("val3dity_valid")) for r in part),
        "median_ref_rms_m": float(np.median(rms_vals)) if rms_vals else None,
        "mean_ref_rms_m": float(np.mean(rms_vals)) if rms_vals else None,
    }


def coverage_mean(run_name: str) -> float | None:
    rows = read_csv(ab.COVERAGE_CSV)
    vals = [
        num(r.get("coverage_frac"))
        for r in rows
        if r.get("setting") == "base" and r.get("run_name") == run_name and r.get("stage") == "sor_post_clean"
    ]
    vals2 = [v for v in vals if v is not None]
    return float(np.mean(vals2)) if vals2 else None


def build_factor_cells(args: argparse.Namespace) -> None:
    cells = configure_ablation_module(args.weight)
    metrics = read_csv(ab.METRICS_CSV)
    raw = read_csv(REPO / "docs/e5_c001_8way_metrics.csv")
    s1 = read_csv(REPO / "docs/e5_c001_3b_s1_metrics.csv")
    raw_by = {(r.get("source_run", ""), r.get("building_id", "")): r for r in raw}
    s1_by = {(r.get("source_run", ""), r.get("building_id", "")): r for r in s1}
    metric_by = {(r.get("run_name", ""), r.get("building_id", "")): r for r in metrics if r.get("setting") == "base"}
    rows: list[dict[str, Any]] = []
    for cell in cells:
        sm = summarize_source(metrics, cell.run_name)
        normal_eval = []
        for sid in NORMAL6:
            bid = full_id(sid)
            row = metric_by.get((cell.run_name, bid), {})
            raw_row = raw_by.get(("raw_dense", bid), {})
            s1_row = s1_by.get(("base__gs_e5_C001_s1_dense_r1", bid), {})
            rms = num(row.get("ref_rms_m"))
            raw_rms = num(raw_row.get("ref_rms_m"))
            s1_rms = num(s1_row.get("ref_rms_m"))
            normal_eval.append(
                {
                    "built": tf(row.get("has_lod22")),
                    "raw_anchor_ok": rms is not None and raw_rms is not None and rms <= raw_rms + 0.5,
                    "delta_vs_s1": None if rms is None or s1_rms is None else rms - s1_rms,
                }
            )
        deltas = [x["delta_vs_s1"] for x in normal_eval if x["delta_vs_s1"] is not None]
        train_info = parse_train_log(TRAIN_LOG_ROOT / f"{cell.run_name}.log")
        audit = summarize_audit(cell.run_name) if not cell.reuse else {}
        rows.append(
            {
                "cell_key": cell.key,
                "role": cell.role,
                "run_name": cell.run_name,
                "w_distort": cell.w_distort,
                "linear_equivalent_note": "100->21(recheck), selected high weight approximates target 50/100 per B-0",
                "prune_opa": cell.prune_opa,
                "final_prune_opa": 0.0,
                "reused_training": str(cell.reuse).lower(),
                "has_lod22": sm["has_lod22"],
                "valid_assembled": sm["valid_assembled"],
                "invalid_assembled": sm["invalid_assembled"],
                "median_ref_rms_m": fmt(sm["median_ref_rms_m"]),
                "mean_coverage_post_sor": fmt(coverage_mean(cell.run_name)),
                "normal6_all_built": str(all(x["built"] for x in normal_eval)).lower(),
                "normal6_raw_anchor_count": sum(bool(x["raw_anchor_ok"]) for x in normal_eval),
                "normal6_median_delta_vs_s1_m": fmt(float(np.median(deltas)) if deltas else None),
                "normal6_max_delta_vs_s1_m": fmt(max(deltas) if deltas else None),
                "preview_or_train_return_code": train_info.get("return_code", "reuse"),
                "elapsed_min": train_info.get("elapsed_min", ""),
                "distort_grad_norm_share_max": fmt(audit.get("distort_grad_norm_share_max")),
                "distort_weighted_loss_share_max": fmt(audit.get("distort_weighted_loss_share_max")),
                "ckpt": rel(CKPT_ROOT / cell.run_name / "ckpt/final.pt"),
                "readout": "gssem; minobs3; voxel0.05; SORstd2; Roofer unchanged",
            }
        )
    write_csv(CSV_FACTOR, rows)
    plot_factor(rows)
    print(json.dumps({"factor_cells": rel(CSV_FACTOR), "rows": len(rows)}, ensure_ascii=False))


def plot_factor(rows: list[dict[str, Any]]) -> None:
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    labels = [r["cell_key"] for r in rows]
    x = np.arange(len(labels))
    fig, axes = plt.subplots(1, 3, figsize=(12.0, 3.8))
    axes[0].bar(x, [num(r["mean_coverage_post_sor"]) or 0 for r in rows], color="#577590")
    axes[1].bar(x, [num(r["median_ref_rms_m"]) or 0 for r in rows], color="#f3722c")
    axes[2].bar(x, [int(r["valid_assembled"]) for r in rows], color="#43aa8b")
    for ax in axes:
        ax.set_xticks(x)
        ax.set_xticklabels(labels, rotation=25, ha="right", fontsize=8)
        ax.grid(axis="y", alpha=0.25)
    axes[0].set_title("coverage post-SOR")
    axes[1].set_title("median RMS")
    axes[2].set_title("valid assembled")
    fig.tight_layout()
    fig.savefig(FIG_DIR / "factor_cell_summary.png", dpi=180)
    plt.close(fig)


def fingerprint_training(args: argparse.Namespace) -> None:
    import torch

    cells = cells_for_weight(selected_w(args.weight))
    rows: list[dict[str, Any]] = []
    for cell in cells:
        cfg = CONFIG_DIR / f"{cell.run_name}.yaml"
        eff = CKPT_ROOT / cell.run_name / "effective_config.json"
        ckpt = CKPT_ROOT / cell.run_name / "ckpt/final.pt"
        log = TRAIN_LOG_ROOT / f"{cell.run_name}.log"
        info = parse_train_log(log)
        state = torch.load(ckpt, map_location="cpu", weights_only=False) if ckpt.exists() else {}
        effective = json.loads(eff.read_text(encoding="utf-8")) if eff.exists() else {}
        rows.append(
            {
                "cell_key": cell.key,
                "run_name": cell.run_name,
                "role": cell.role,
                "reused_training": str(cell.reuse).lower(),
                "w_distort": cell.w_distort,
                "prune_opa": cell.prune_opa,
                "seed": 2001,
                "config": rel(cfg) if cfg.exists() else "reuse_alias",
                "config_sha256": sha256_file(cfg) if cfg.exists() else "",
                "effective_config": rel(eff),
                "effective_config_sha256": sha256_file(eff) if eff.exists() else "",
                "ckpt": rel(ckpt),
                "ckpt_sha256": sha256_file(ckpt) if ckpt.exists() else "",
                "audit_csv": rel(audit_csv_for(cell.run_name)) if audit_csv_for(cell.run_name).exists() else "",
                "log": rel(log) if log.exists() else "reuse_alias",
                "return_code": info.get("return_code", "reuse"),
                "elapsed_min": info.get("elapsed_min", ""),
                "host_gpu": info.get("host_gpu", ""),
                "max_iter": state.get("it", "") if state else "",
                "final_n_gaussians": state.get("n_prim", "") if state else "",
                "final_prune_opa": state.get("final_prune_opa", effective.get("final_prune_opa", "")),
                "final_pruned": state.get("final_pruned", "") if state else "",
                "loss_grad_audit_every": effective.get("loss_grad_audit_every", ""),
                "z_datum_history": "C001 cropped scene; local + [690953,5336071,604] -> EPSG:25832 ellipsoidal frame",
            }
        )
    write_csv(P2_RUN_DIR / "train_fingerprints.csv", rows)
    print(json.dumps({"train_fingerprints": rel(P2_RUN_DIR / "train_fingerprints.csv"), "rows": len(rows)}, ensure_ascii=False))


def versions(_args: argparse.Namespace) -> None:
    P2_RUN_DIR.mkdir(parents=True, exist_ok=True)
    lines = [
        f"run_id: {RUN_ID}",
        f"timestamp_utc: {datetime.now(timezone.utc).isoformat()}",
        f"git_head: {capture(['git', 'rev-parse', 'HEAD'])}",
        f"git_branch: {capture(['git', 'branch', '--show-current'])}",
        "canonical_changed: no",
        "mode: S1 factor dense cells; observation material; no human verdict",
        f"selected_weight_file: {rel(selected_path())}",
        f"grad_share_csv: {rel(CSV_GRAD_SHARE)}",
        f"factor_cells_csv: {rel(CSV_FACTOR)}",
        f"timeline_csv: {rel(CSV_TIMELINE)}",
        f"sheet_identity_csv: {rel(CSV_SHEET)}",
        f"depth_source_csv: {rel(CSV_DEPTH_SOURCE)}",
        f"405_repair_csv: {rel(CSV_405_REPAIR)}",
        f"train_fingerprints: {rel(P2_RUN_DIR / 'train_fingerprints.csv')}",
        f"readout_fingerprints: {rel(P2_RUN_DIR / 'readout_fingerprints.csv')}",
        f"p0_versions: {rel(P0_RUN_DIR / 'versions.txt')}",
        f"repaired_p0_run_dir: {rel(REPAIRED_P0_RUN_DIR)}",
    ]
    (P2_RUN_DIR / "versions.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"versions": rel(P2_RUN_DIR / "versions.txt")}, ensure_ascii=False))


def md_table(rows: list[dict[str, Any]], columns: list[str], max_rows: int = 20) -> str:
    use = rows[:max_rows]
    out = ["| " + " | ".join(columns) + " |", "|" + "|".join("---" for _ in columns) + "|"]
    for row in use:
        out.append("| " + " | ".join(str(row.get(col, "")) for col in columns) + " |")
    if len(rows) > max_rows:
        out.append("| ... | " + f"{len(rows) - max_rows} rows omitted |" + " | ".join("" for _ in columns[2:]) + " |")
    return "\n".join(out)


def report(_args: argparse.Namespace) -> None:
    grad = read_csv(CSV_GRAD_SHARE)
    factor = read_csv(CSV_FACTOR)
    timeline = read_csv(CSV_TIMELINE)
    sheet = read_csv(CSV_SHEET)
    depth = read_csv(CSV_DEPTH_SOURCE)
    repair405 = read_csv(CSV_405_REPAIR)
    issues = read_csv(CSV_ISSUES)
    lines = [
        "# E5 C001 S1 완성판 요인",
        "",
        "> 관찰 자료. 판정 0. dense 요인 3셀과 corrected recheck 재사용 셀을 같은 readout/Roofer/8-way 절차로 병기했다. 정본 S0/S1/corrected 산출물은 덮어쓰지 않았다.",
        "",
        "## B-0 Preview",
        "",
        md_table(grad, ["w_distort", "return_code", "final_ckpt_exists", "gate_share_le_040", "preview_gate_ok", "distort_weighted_loss_share_max", "distort_grad_norm_share_max", "selected_w_distort", "selection_reason"], 8),
        "",
        "## B-1/B-2 Factor Cells",
        "",
        md_table(factor, ["cell_key", "role", "w_distort", "prune_opa", "has_lod22", "valid_assembled", "median_ref_rms_m", "mean_coverage_post_sor", "normal6_raw_anchor_count"], 8),
        "",
        f"- summary figure: `{rel(FIG_DIR / 'factor_cell_summary.png')}`.",
        "",
        "## A-1 Timeline",
        "",
        md_table([r for r in timeline if r.get("building_id") == "DEBY_LOD2_4907202" and r.get("arm") == "dense"], ["family", "step", "n_gaussians_in_footprint", "z_p50", "z_std", "opacity_p50"], 18),
        "",
        f"- figures: `{rel(FIG_DIR)}/timeline_dense_*.png`.",
        "",
        "## A-2 Sheet Identity",
        "",
        md_table([r for r in sheet if r.get("band") in {"roof_band_560_590", "sheet_band_595_615"}], ["family", "arm", "band", "n_gaussians", "x_min", "x_max", "y_min", "y_max", "z_p50", "opacity_p50"], 16),
        "",
        f"- figure: `{rel(FIG_DIR / 'sheet_identity_hist_slice.png')}`.",
        "",
        "## A-3 Depth Source",
        "",
        md_table(depth, ["arm", "data_root", "load_depth", "init_pointcloud", "depth_source_interpretation", "effective_config_absence_reason"], 6),
        "",
        "## A-4 405 Repair",
        "",
        md_table(
            [r for r in repair405 if r.get("source_run_id") == P0_RUN_ID],
            ["setting", "run_name", "valid_features_original", "valid_features_repaired", "error_405_original", "error_405_repaired", "error_302_repaired", "vertices_same"],
            12,
        )
        if repair405
        else "_405 repair overlay not present at report time_",
        "",
        "## Issues",
        "",
        md_table(issues, ["part", "severity", "message", "path"], 20) if issues else "_recorded issues 없음_",
        "",
        "## Outputs",
        "",
        f"- CSV: `{rel(CSV_FACTOR)}`, `{rel(CSV_TIMELINE)}`, `{rel(CSV_SHEET)}`, `{rel(CSV_GRAD_SHARE)}`, `{rel(CSV_DEPTH_SOURCE)}`, `{rel(CSV_405_REPAIR)}`.",
        f"- figures: `{rel(FIG_DIR)}/`.",
        f"- versions: `{rel(P2_RUN_DIR / 'versions.txt')}`.",
    ]
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"report": rel(REPORT_PATH)}, ensure_ascii=False))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("generate-configs")
    p_train = sub.add_parser("train-one")
    p_train.add_argument("--run-name", required=True)
    p_train.add_argument("--gpu", default="0")
    p_train.add_argument("--check", action="store_true")
    sub.add_parser("summarize-preview")
    for name in ["readout", "assemble", "evaluate", "all"]:
        p = sub.add_parser(name)
        p.add_argument("--settings", nargs="*", default=None)
        p.add_argument("--runs", nargs="*", default=None)
        p.add_argument("--force", action="store_true")
        p.add_argument("--data-root", default=DATA_ROOT)
        p.add_argument("--torch-extensions", default=TORCH_EXTENSIONS)
        p.add_argument("--gpu", default="0")
        p.add_argument("--buffer-m", type=float, default=20.0)
        p.add_argument("--weight", type=int, default=None)
    p_timeline = sub.add_parser("timeline-roofcrop")
    p_timeline.add_argument("--include-factor", action="store_true")
    sub.add_parser("sheet-identity")
    sub.add_parser("depth-source")
    p_factor = sub.add_parser("factor-cells")
    p_factor.add_argument("--weight", type=int, default=None)
    p_fp = sub.add_parser("fingerprint-training")
    p_fp.add_argument("--weight", type=int, default=None)
    sub.add_parser("versions")
    sub.add_parser("report")
    return parser


def main() -> None:
    os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib")
    args = build_parser().parse_args()
    if args.cmd == "generate-configs":
        generate_configs(args)
    elif args.cmd == "train-one":
        train_one(args)
    elif args.cmd == "summarize-preview":
        summarize_preview(args)
    elif args.cmd in {"readout", "assemble", "evaluate", "all"}:
        readout_like(args)
    elif args.cmd == "timeline-roofcrop":
        timeline_roofcrop(args)
    elif args.cmd == "sheet-identity":
        sheet_identity(args)
    elif args.cmd == "depth-source":
        depth_source(args)
    elif args.cmd == "factor-cells":
        build_factor_cells(args)
    elif args.cmd == "fingerprint-training":
        fingerprint_training(args)
    elif args.cmd == "versions":
        versions(args)
    elif args.cmd == "report":
        report(args)


if __name__ == "__main__":
    main()
