#!/usr/bin/env python3
"""Run W2-3a Roofer parameter tuning on the coverage-controlled population.

Run from phases/p0-audit/. Host mode selects a deterministic dev subset, runs a small
Roofer parameter grid separately for ALS and DIM, selects one configuration per
input using dev success/validity, and reruns the selected configurations on all
93 coverage-controlled buildings.
"""

from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import os
import random
import shutil
import subprocess
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


TASK_ID = "W2-3a"
BASE_W2_RUN_ID = "w2_1_roofer_default_20260612_152729"
DEV_SEED = 20260612
DEV_N = 15
AOI_BBOX = (690791.740, 5335864.050, 691154.650, 5336353.850)
ROOFER_JOBS = 32
GRID = [
    {
        "config_id": "default",
        "plane_detect_epsilon": 0.30,
        "plane_detect_min_points": 15,
        "complexity_factor": 0.888,
    },
    {
        "config_id": "simple_loose_min10",
        "plane_detect_epsilon": 0.45,
        "plane_detect_min_points": 10,
        "complexity_factor": 0.65,
    },
    {
        "config_id": "simple_strict_min10",
        "plane_detect_epsilon": 0.25,
        "plane_detect_min_points": 10,
        "complexity_factor": 0.65,
    },
    {
        "config_id": "simple_loose_min20",
        "plane_detect_epsilon": 0.45,
        "plane_detect_min_points": 20,
        "complexity_factor": 0.65,
    },
    {
        "config_id": "simple_strict_min20",
        "plane_detect_epsilon": 0.25,
        "plane_detect_min_points": 20,
        "complexity_factor": 0.65,
    },
    {
        "config_id": "detail_loose_min10",
        "plane_detect_epsilon": 0.45,
        "plane_detect_min_points": 10,
        "complexity_factor": 0.95,
    },
    {
        "config_id": "detail_strict_min10",
        "plane_detect_epsilon": 0.25,
        "plane_detect_min_points": 10,
        "complexity_factor": 0.95,
    },
    {
        "config_id": "detail_loose_min20",
        "plane_detect_epsilon": 0.45,
        "plane_detect_min_points": 20,
        "complexity_factor": 0.95,
    },
    {
        "config_id": "detail_strict_min20",
        "plane_detect_epsilon": 0.25,
        "plane_detect_min_points": 20,
        "complexity_factor": 0.95,
    },
]


def host_entrypoint() -> None:
    repo = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env.setdefault("P0_UID", str(os.getuid()))
    env.setdefault("P0_GID", str(os.getgid()))
    run_id = env.get("RUN_ID") or datetime.now().strftime("w2_3a_roofer_tuning_%Y%m%d_%H%M%S")
    git_commit = capture(["git", "rev-parse", "--short", "HEAD"], cwd=repo.parent).strip()
    run_dir = repo / "runs" / run_id
    logs_dir = run_dir / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    compose = ["docker", "compose", "-f", str(repo / "env/docker-compose.p0.yml")]

    write_host_config(run_dir, run_id, git_commit)
    write_host_versions(repo, run_dir, compose, env, git_commit)

    common_env = [
        "-e",
        f"RUN_ID={run_id}",
        "-e",
        f"P0_GIT_COMMIT={git_commit}",
    ]
    run(
        compose
        + [
            "run",
            "-T",
            "--rm",
            *common_env,
            "tools",
            "python",
            "/workspace/scripts/13_roofer_tune_w2a.py",
            "--mode",
            "prepare",
        ],
        cwd=repo,
        env=env,
        log_path=logs_dir / "prepare.log",
    )

    plan_rows = read_csv(run_dir / "execution_plan.csv")
    for row in plan_rows:
        label = row["input"].lower()
        run_roofer_plan_row(repo, compose, env, logs_dir, row, label)

    run(
        compose
        + [
            "run",
            "-T",
            "--rm",
            *common_env,
            "tools",
            "python",
            "/workspace/scripts/13_roofer_tune_w2a.py",
            "--mode",
            "postprocess",
        ],
        cwd=repo,
        env=env,
        log_path=logs_dir / "postprocess.log",
    )
    full_plan = run_dir / "execution_plan_full93.csv"
    if not full_plan.exists():
        raise RuntimeError(f"Expected full93 plan was not written: {full_plan}")
    for row in read_csv(full_plan):
        label = row["input"].lower()
        run_roofer_plan_row(repo, compose, env, logs_dir, row, label)
    run(
        compose
        + [
            "run",
            "-T",
            "--rm",
            *common_env,
            "tools",
            "python",
            "/workspace/scripts/13_roofer_tune_w2a.py",
            "--mode",
            "postprocess",
        ],
        cwd=repo,
        env=env,
        log_path=logs_dir / "postprocess_final.log",
    )
    print(f"run_id={run_id}")
    print(f"run_dir=runs/{run_id}")
    print("report=docs/W2_3a_roofer_tuning.md")


def run_roofer_plan_row(
    repo: Path,
    compose: list[str],
    env: dict[str, str],
    logs_dir: Path,
    row: dict[str, str],
    label: str,
) -> None:
    params = json.loads(row["params_json"])
    cmd = [
        *compose,
        "run",
        "-T",
        "--rm",
        "roofer",
        "--id-attribute",
        "building_id",
        "--jobs",
        str(ROOFER_JOBS),
        "--box",
        *(f"{value:.3f}" for value in AOI_BBOX),
        "--filter",
        row["ogr_filter"],
    ]
    for key, value in params.items():
        cmd.extend([f"--{key.replace('_', '-')}", str(value)])
    cmd.extend([row["pointcloud_path"], row["footprint_path"], row["output_dir"]])
    log_name = f"roofer_{row['stage']}_{label}_{row['config_id']}.log"
    run(cmd, cwd=repo, env=env, log_path=logs_dir / log_name)


def run(
    cmd: list[str],
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
    log_path: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    print("+ " + " ".join(cmd), flush=True)
    if log_path:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("w", encoding="utf-8") as log:
            log.write("+ " + " ".join(cmd) + "\n")
            proc = subprocess.run(
                cmd,
                cwd=cwd,
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
            )
            log.write(proc.stdout)
            print(proc.stdout, end="", flush=True)
            proc.check_returncode()
            return proc
    return subprocess.run(cmd, cwd=cwd, env=env, text=True, check=True)


def capture(cmd: list[str], cwd: Path | None = None, env: dict[str, str] | None = None) -> str:
    proc = subprocess.run(cmd, cwd=cwd, env=env, text=True, capture_output=True, check=False)
    return ((proc.stdout or "") + (proc.stderr or "")).strip()


def write_host_config(run_dir: Path, run_id: str, git_commit: str) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    config = {
        "task": "W2-3a_roofer_input_specific_tuning",
        "run_id": run_id,
        "git_commit": git_commit,
        "base_w2_run_id": BASE_W2_RUN_ID,
        "coverage_population_source": "docs/W2_1c_paired_status.csv",
        "coverage_population_n": 93,
        "dev_seed": DEV_SEED,
        "dev_n": DEV_N,
        "roofer_jobs": ROOFER_JOBS,
        "selection_rule": [
            "maximize dev status=success count",
            "tie: maximize dev LoD2.2 generated count",
            "tie: maximize dev val3dity-valid count",
            "tie: minimize mean rf_rmse_lod22",
            "tie: prefer lower complexity_factor, then lower plane_detect_epsilon, then lower plane_detect_min_points",
        ],
        "grid": GRID,
    }
    (run_dir / "config.yaml").write_text(to_yaml(config), encoding="utf-8")


def write_host_versions(
    repo: Path,
    run_dir: Path,
    compose: list[str],
    env: dict[str, str],
    git_commit: str,
) -> None:
    lines = [
        "# W2-3a Tool Versions",
        "",
        f"- Generated: {datetime.now(timezone.utc).astimezone().isoformat(timespec='seconds')}",
        f"- Run ID: {run_dir.name}",
        f"- Repository commit: {git_commit}",
        "",
        "```console",
    ]
    commands = [
        ["git", "status", "--short", "--branch"],
        [*compose, "run", "-T", "--rm", "roofer", "-v"],
        [*compose, "run", "-T", "--rm", "tools", "val3dity", "--version"],
        [*compose, "run", "-T", "--rm", "tools", "python", "-c", "import numpy; print('numpy ' + numpy.__version__)"],
    ]
    for cmd in commands:
        lines.append("$ " + " ".join(cmd))
        lines.append(capture(cmd, cwd=repo if cmd[0] != "git" else repo.parent, env=env))
    lines.append("```")
    (run_dir / "versions.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")


def prepare_entrypoint() -> None:
    root = Path("/workspace")
    docs = root / "docs"
    run_id = os.environ["RUN_ID"]
    run_dir = root / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    coverage_rows = [row for row in read_csv(docs / "W2_1c_paired_status.csv") if row["coverage_control_population"] == "yes"]
    coverage_ids = sorted(row["building_id"] for row in coverage_rows)
    rng = random.Random(DEV_SEED)
    dev_ids = sorted(rng.sample(coverage_ids, DEV_N))
    eval_ids = [bid for bid in coverage_ids if bid not in set(dev_ids)]
    dev_rows = [{"building_id": bid, "subset": "dev", "seed": str(DEV_SEED)} for bid in dev_ids]
    eval_rows = [{"building_id": bid, "subset": "eval", "seed": str(DEV_SEED)} for bid in eval_ids]
    write_csv(run_dir / "coverage_control_ids.csv", [{"building_id": bid} for bid in coverage_ids])
    write_csv(run_dir / "dev_subset.csv", dev_rows + eval_rows)
    write_csv(docs / "W2_3a_dev_subset.csv", dev_rows + eval_rows)

    plan_rows = []
    for input_label in ("ALS", "DIM"):
        pointcloud = "/workspace/data/raw/als" if input_label == "ALS" else "/workspace/data/work/w2/dim_v1_classified_z_minus0p174.laz"
        for config in GRID:
            plan_rows.append(plan_row(run_id, "dev", input_label, config, dev_ids, pointcloud))
    write_csv(run_dir / "execution_plan.csv", plan_rows)
    print(f"coverage_control_n={len(coverage_ids)}")
    print(f"dev_seed={DEV_SEED}")
    print(f"dev_n={len(dev_ids)}")
    print(f"execution_plan={len(plan_rows)}")


def plan_row(
    run_id: str,
    stage: str,
    input_label: str,
    config: dict[str, Any],
    building_ids: list[str],
    pointcloud: str,
) -> dict[str, str]:
    params = {
        "plane_detect_epsilon": config["plane_detect_epsilon"],
        "plane_detect_min_points": config["plane_detect_min_points"],
        "complexity_factor": config["complexity_factor"],
    }
    config_id = config["config_id"]
    output_dir = f"/workspace/runs/{run_id}/roofer/{stage}/{input_label.lower()}/{config_id}"
    return {
        "stage": stage,
        "input": input_label,
        "config_id": config_id,
        "params_json": json.dumps(params, sort_keys=True, separators=(",", ":")),
        "building_count": str(len(building_ids)),
        "building_ids": ";".join(building_ids),
        "ogr_filter": ogr_filter(building_ids),
        "pointcloud_path": pointcloud,
        "footprint_path": "/workspace/data/work/w2/footprints_scene_aoi.gpkg",
        "output_dir": output_dir,
    }


def postprocess_entrypoint() -> None:
    root = Path("/workspace")
    docs = root / "docs"
    run_id = os.environ["RUN_ID"]
    run_dir = root / "runs" / run_id
    cityjson_dir = run_dir / "cityjson"
    val_dir = run_dir / "val3dity"
    cityjson_dir.mkdir(parents=True, exist_ok=True)
    val_dir.mkdir(parents=True, exist_ok=True)

    subset_rows = read_csv(run_dir / "dev_subset.csv")
    dev_ids = [row["building_id"] for row in subset_rows if row["subset"] == "dev"]
    coverage_ids = [row["building_id"] for row in subset_rows]
    grid_rows = []
    status_by_key: dict[tuple[str, str, str, str], list[dict[str, str]]] = {}
    for input_label in ("ALS", "DIM"):
        for config in GRID:
            config_id = config["config_id"]
            rows, metrics = postprocess_roofer_output(
                root,
                run_dir,
                "dev",
                input_label,
                config_id,
                dev_ids,
            )
            status_by_key[("dev", input_label, config_id, "status")] = rows
            grid_rows.append({**grid_metric_row("dev", input_label, config, rows, metrics), "selected": "no"})

    selected_by_input = {}
    for input_label in ("ALS", "DIM"):
        candidates = [row for row in grid_rows if row["input"] == input_label]
        selected_by_input[input_label] = choose_config(candidates)
        for row in candidates:
            if row["config_id"] == selected_by_input[input_label]["config_id"]:
                row["selected"] = "yes"

    full_plan_rows = []
    for input_label in ("ALS", "DIM"):
        config = next(config for config in GRID if config["config_id"] == selected_by_input[input_label]["config_id"])
        pointcloud = "/workspace/data/raw/als" if input_label == "ALS" else "/workspace/data/work/w2/dim_v1_classified_z_minus0p174.laz"
        full_plan_rows.append(plan_row(run_id, "full93", input_label, config, coverage_ids, pointcloud))
    full_plan_path = run_dir / "execution_plan_full93.csv"
    if not full_plan_path.exists():
        write_csv(full_plan_path, full_plan_rows)
        print(f"full93_plan_written={rel(full_plan_path)}")
        print("Run the full93 Roofer commands from host and rerun postprocess.")
        return

    missing_full = []
    for row in read_csv(full_plan_path):
        output_dir = Path(row["output_dir"].replace("/workspace", str(root)))
        if not list(output_dir.glob("*.city.jsonl")):
            missing_full.append(row)
    if missing_full:
        print(f"waiting_for_full93_runs={len(missing_full)}")
        print("Run the full93 Roofer commands from host and rerun postprocess.")
        return

    tuned_status: dict[tuple[str, str], dict[str, str]] = {}
    for row in read_csv(full_plan_path):
        input_label = row["input"]
        config_id = row["config_id"]
        rows, _metrics = postprocess_roofer_output(root, run_dir, "full93", input_label, config_id, coverage_ids)
        for status_row in rows:
            tuned_status[(input_label, status_row["building_id"])] = status_row

    default_rows = [row for row in read_csv(docs / "W2_1c_paired_status.csv") if row["coverage_control_population"] == "yes"]
    tuned_paired = build_tuned_paired(default_rows, tuned_status, dev_ids, selected_by_input)
    paired_summary = build_success_summary(tuned_paired)
    bucket_summary = build_bucket_summary(tuned_paired)
    selected_rows = [
        selected_param_row(input_label, selected_by_input[input_label])
        for input_label in ("ALS", "DIM")
    ]

    outputs = [
        (docs / "W2_3a_grid_results.csv", grid_rows),
        (docs / "W2_3a_selected_params.csv", selected_rows),
        (docs / "W2_3a_tuned_paired_status.csv", tuned_paired),
        (docs / "W2_3a_paired_success.csv", paired_summary),
        (docs / "W2_3a_bucket_summary.csv", bucket_summary),
    ]
    for path, rows in outputs:
        write_csv(path, rows)
    report = docs / "W2_3a_roofer_tuning.md"
    write_report(report, run_id, selected_rows, grid_rows, paired_summary, bucket_summary)
    copy_outputs(run_dir, [path for path, _rows in outputs] + [report, docs / "W2_3a_dev_subset.csv"])
    print(f"report={rel(report)}")
    print(f"selected_params={rel(docs / 'W2_3a_selected_params.csv')}")
    print(f"paired_success={rel(docs / 'W2_3a_paired_success.csv')}")


def postprocess_roofer_output(
    root: Path,
    run_dir: Path,
    stage: str,
    input_label: str,
    config_id: str,
    expected_ids: list[str],
) -> tuple[list[dict[str, str]], dict[str, str]]:
    w2 = load_w2_module(root)
    output_dir = run_dir / "roofer" / stage / input_label.lower() / config_id
    jsonl_files = sorted(output_dir.glob("*.city.jsonl"))
    if not jsonl_files:
        raise RuntimeError(f"No Roofer output found: {output_dir}")
    cityjson = run_dir / "cityjson" / stage / f"{input_label.lower()}_{config_id}.city.json"
    val_report = run_dir / "val3dity" / stage / f"{input_label.lower()}_{config_id}.json"
    val_log = val_report.with_suffix(".log")
    w2.combine_cityjsonseq(jsonl_files, cityjson)
    run(["val3dity", cityjson.as_posix(), "--report", val_report.as_posix()], log_path=val_log)
    payload = json.loads(val_report.read_text(encoding="utf-8"))
    val_by_id = {
        str(feature.get("id")): feature
        for feature in payload.get("features", [])
        if feature.get("id") is not None
    }
    roofer_by_id = w2.parse_roofer_features(jsonl_files)
    rows = w2.classify_buildings(input_label, expected_ids, roofer_by_id, val_by_id)
    status_csv = run_dir / "status" / stage / f"{input_label.lower()}_{config_id}.csv"
    status_csv.parent.mkdir(parents=True, exist_ok=True)
    w2.write_status_csv(status_csv, rows)
    metrics = {
        "cityjson": rel(cityjson),
        "val_report": rel(val_report),
        "status_csv": rel(status_csv),
        "feature_total": str(sum(item.get("total", 0) for item in payload.get("features_overview", []))),
        "feature_valid": str(sum(item.get("valid", 0) for item in payload.get("features_overview", []))),
        "dataset_validity": str(bool(payload.get("validity", False))),
    }
    return rows, metrics


def grid_metric_row(
    stage: str,
    input_label: str,
    config: dict[str, Any],
    rows: list[dict[str, str]],
    metrics: dict[str, str],
) -> dict[str, str]:
    total = len(rows)
    success = sum(row["status"] == "success" for row in rows)
    lod22 = sum(row["has_lod22"] == "True" for row in rows)
    valid = sum(row["val3dity_valid"] == "True" for row in rows)
    rmses = [parse_float(row["rf_rmse_lod22"]) for row in rows if parse_float(row["rf_rmse_lod22"]) is not None]
    reason_counts = Counter(row["reason"] for row in rows)
    return {
        "stage": stage,
        "input": input_label,
        "config_id": config["config_id"],
        "plane_detect_epsilon": str(config["plane_detect_epsilon"]),
        "plane_detect_min_points": str(config["plane_detect_min_points"]),
        "complexity_factor": str(config["complexity_factor"]),
        "n": str(total),
        "success": str(success),
        "success_rate": pct(success, total),
        "lod22_generated": str(lod22),
        "lod22_rate": pct(lod22, total),
        "val3dity_valid": str(valid),
        "valid_rate": pct(valid, total),
        "mean_rf_rmse_lod22": f"{sum(rmses) / len(rmses):.6f}" if rmses else "",
        "reason_counts": json.dumps(dict(sorted(reason_counts.items())), sort_keys=True, separators=(",", ":")),
        **metrics,
    }


def choose_config(rows: list[dict[str, str]]) -> dict[str, str]:
    def key(row: dict[str, str]) -> tuple[float, float, float, float, float, float, float]:
        rmse = parse_float(row["mean_rf_rmse_lod22"])
        if rmse is None:
            rmse = 999999.0
        return (
            float(row["success"]),
            float(row["lod22_generated"]),
            float(row["val3dity_valid"]),
            -rmse,
            -float(row["complexity_factor"]),
            -float(row["plane_detect_epsilon"]),
            -float(row["plane_detect_min_points"]),
        )

    return max(rows, key=key)


def selected_param_row(input_label: str, row: dict[str, str]) -> dict[str, str]:
    return {
        "input": input_label,
        "selected_config_id": row["config_id"],
        "plane_detect_epsilon": row["plane_detect_epsilon"],
        "plane_detect_min_points": row["plane_detect_min_points"],
        "complexity_factor": row["complexity_factor"],
        "dev_n": row["n"],
        "dev_success": row["success"],
        "dev_success_rate": row["success_rate"],
        "dev_lod22_generated": row["lod22_generated"],
        "dev_lod22_rate": row["lod22_rate"],
        "dev_val3dity_valid": row["val3dity_valid"],
        "dev_valid_rate": row["valid_rate"],
        "dev_mean_rf_rmse_lod22": row["mean_rf_rmse_lod22"],
        "selection_basis": "max success, then LoD2.2 count, validity count, lower RMSE, lower complexity/epsilon/min-points",
    }


def build_tuned_paired(
    default_rows: list[dict[str, str]],
    tuned_status: dict[tuple[str, str], dict[str, str]],
    dev_ids: list[str],
    selected_by_input: dict[str, dict[str, str]],
) -> list[dict[str, str]]:
    dev_set = set(dev_ids)
    output = []
    for row in default_rows:
        bid = row["building_id"]
        als = tuned_status[("ALS", bid)]
        dim = tuned_status[("DIM", bid)]
        als_bucket = failure_bucket("ALS", als["status"], als["reason"])
        dim_bucket = failure_bucket("DIM", dim["status"], dim["reason"])
        output.append(
            {
                "building_id": bid,
                "subset": "dev" if bid in dev_set else "eval",
                "als_selected_config": selected_by_input["ALS"]["config_id"],
                "dim_selected_config": selected_by_input["DIM"]["config_id"],
                "als_default_status": row["als_status"],
                "als_default_reason": row["als_reason"],
                "als_tuned_status": als["status"],
                "als_tuned_reason": als["reason"],
                "als_tuned_bucket_v1": als_bucket,
                "als_tuned_rf_pt_density": als["rf_pt_density"],
                "als_tuned_rf_rmse_lod22": als["rf_rmse_lod22"],
                "dim_default_status": row["dim_status"],
                "dim_default_reason": row["dim_reason"],
                "dim_tuned_status": dim["status"],
                "dim_tuned_reason": dim["reason"],
                "dim_tuned_bucket_v1": dim_bucket,
                "dim_tuned_rf_pt_density": dim["rf_pt_density"],
                "dim_tuned_rf_rmse_lod22": dim["rf_rmse_lod22"],
                "default_pair_category": pair_category(row["als_status"], row["dim_status"]),
                "tuned_pair_category": pair_category(als["status"], dim["status"]),
            }
        )
    return output


def build_success_summary(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    populations = [
        ("coverage_control_93_all", rows),
        ("dev15_tuning_subset", [row for row in rows if row["subset"] == "dev"]),
        ("eval78_non_dev", [row for row in rows if row["subset"] == "eval"]),
    ]
    output = []
    for pop_name, pop in populations:
        total = len(pop)
        for input_label in ("ALS", "DIM"):
            prefix = input_label.lower()
            default_success = sum(row[f"{prefix}_default_status"] == "success" for row in pop)
            tuned_success = sum(row[f"{prefix}_tuned_status"] == "success" for row in pop)
            delta = tuned_success - default_success
            output.append(
                {
                    "population": pop_name,
                    "input": input_label,
                    "n": str(total),
                    "default_success": count_rate(default_success, total),
                    "tuned_success": count_rate(tuned_success, total),
                    "delta_count": str(delta),
                    "delta_percentage_points": f"{(delta / total * 100):+.1f}" if total else "nan",
                }
            )
        default_both = sum(row["default_pair_category"] == "both_success" for row in pop)
        tuned_both = sum(row["tuned_pair_category"] == "both_success" for row in pop)
        output.append(
            {
                "population": pop_name,
                "input": "PAIRED_BOTH_SUCCESS",
                "n": str(total),
                "default_success": count_rate(default_both, total),
                "tuned_success": count_rate(tuned_both, total),
                "delta_count": str(tuned_both - default_both),
                "delta_percentage_points": f"{((tuned_both - default_both) / total * 100):+.1f}" if total else "nan",
            }
        )
    return output


def build_bucket_summary(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    buckets = ["success", "coverage", "roof_matching_assembly_failure", "validity", "reference_mismatch", "aoi_edge_excluded"]
    populations = [
        ("coverage_control_93_all", rows),
        ("dev15_tuning_subset", [row for row in rows if row["subset"] == "dev"]),
        ("eval78_non_dev", [row for row in rows if row["subset"] == "eval"]),
    ]
    output = []
    for pop_name, pop in populations:
        for input_label in ("ALS", "DIM"):
            prefix = input_label.lower()
            for bucket in buckets:
                output.append(
                    {
                        "population": pop_name,
                        "input": input_label,
                        "bucket_v1": bucket,
                        "default_count": str(sum(default_bucket(input_label, row) == bucket for row in pop)),
                        "tuned_count": str(sum(row[f"{prefix}_tuned_bucket_v1"] == bucket for row in pop)),
                    }
                )
    return output


def write_report(
    path: Path,
    run_id: str,
    selected_rows: list[dict[str, str]],
    grid_rows: list[dict[str, str]],
    paired_summary: list[dict[str, str]],
    bucket_summary: list[dict[str, str]],
) -> None:
    lines = [
        "# W2-3a Roofer Input-Specific Tuning",
        "",
        f"- Run ID: `{run_id}`",
        f"- Coverage-control population: 93 buildings from `docs/W2_1c_paired_status.csv`.",
        f"- Dev subset: {DEV_N} buildings, random seed `{DEV_SEED}`. Dev rows are reported separately from the non-dev evaluation subset.",
        "- Selection rule fixed before tuning: maximize dev `status=success`, then LoD2.2 generated count, val3dity-valid count, lower mean `rf_rmse_lod22`, then lower complexity/epsilon/min-points.",
        "- Roofer grid parameters: `plane-detect-epsilon`, `plane-detect-min-points`, `complexity-factor`; plumbing kept fixed (`--id-attribute`, AOI `--box`, `--filter`, `--jobs`).",
        "",
        "## Selected Parameters",
        "",
    ]
    lines.extend(markdown_table(selected_rows))
    selected_non_default = any(row["selected_config_id"] != "default" for row in selected_rows)
    if not selected_non_default:
        lines.extend(
            [
                "",
                "## Interpretation Note",
                "",
                "Both inputs selected Roofer default parameters on the dev subset. The full-93 deltas below are therefore selected-default filtered rerun deltas against the W2-1c baseline table, not evidence that a non-default tuning setting improved reconstruction.",
            ]
        )
    lines.extend(["", "## Dev Grid Results", ""])
    compact_grid = [
        {
            "input": row["input"],
            "config_id": row["config_id"],
            "epsilon": row["plane_detect_epsilon"],
            "min_points": row["plane_detect_min_points"],
            "complexity": row["complexity_factor"],
            "success": row["success"],
            "lod22": row["lod22_generated"],
            "valid": row["val3dity_valid"],
            "mean_rmse": row["mean_rf_rmse_lod22"],
            "selected": row["selected"],
        }
        for row in grid_rows
    ]
    lines.extend(markdown_table(compact_grid))
    lines.extend(["", "## Default vs Tuned Success", ""])
    lines.extend(markdown_table(paired_summary))
    lines.extend(["", "## Failure Bucket Reclassification", ""])
    bucket_compact = [
        row
        for row in bucket_summary
        if row["default_count"] != "0" or row["tuned_count"] != "0"
    ]
    lines.extend(markdown_table(bucket_compact))
    lines.extend(
        [
            "",
            "## Files",
            "",
            "- Dev subset: `docs/W2_3a_dev_subset.csv`",
            "- Dev grid table: `docs/W2_3a_grid_results.csv`",
            "- Selected parameters: `docs/W2_3a_selected_params.csv`",
            "- Tuned paired status: `docs/W2_3a_tuned_paired_status.csv`",
            "- Default vs tuned success: `docs/W2_3a_paired_success.csv`",
            "- Bucket summary: `docs/W2_3a_bucket_summary.csv`",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def failure_bucket(input_label: str, status: str, reason: str) -> str:
    if status == "success":
        return "success"
    if reason in {"pointcloud_unusable_no_points", "pointcloud_unusable_no_planes", "pointcloud_unusable"}:
        return "coverage"
    if reason == "missing_roofer_output":
        return "aoi_edge_excluded"
    if reason == "val3dity_invalid":
        return "validity"
    if input_label == "DIM" and reason == "missing_lod22_geometry":
        return "roof_matching_assembly_failure"
    return "roof_matching_assembly_failure"


def default_bucket(input_label: str, row: dict[str, str]) -> str:
    return row[f"{input_label.lower()}_default_reason"] and failure_bucket(
        input_label,
        row[f"{input_label.lower()}_default_status"],
        row[f"{input_label.lower()}_default_reason"],
    )


def pair_category(als_status: str, dim_status: str) -> str:
    if als_status == "success" and dim_status == "success":
        return "both_success"
    if als_status == "success":
        return "ALS_only"
    if dim_status == "success":
        return "DIM_only"
    return "both_fail"


def ogr_filter(building_ids: list[str]) -> str:
    quoted = ",".join("'" + bid.replace("'", "''") + "'" for bid in building_ids)
    return f"building_id IN ({quoted})"


def load_w2_module(root: Path) -> Any:
    path = root / "scripts/08_roofer_w2.py"
    spec = importlib.util.spec_from_file_location("roofer_w2", path)
    if not spec or not spec.loader:
        raise RuntimeError(f"Cannot import {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    if not rows:
        raise RuntimeError(f"No rows for {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def copy_outputs(run_dir: Path, paths: list[Path]) -> None:
    snapshot = run_dir / "docs_snapshot"
    snapshot.mkdir(parents=True, exist_ok=True)
    for path in paths:
        shutil.copy2(path, snapshot / path.name)


def markdown_table(rows: list[dict[str, str]]) -> list[str]:
    if not rows:
        return ["_No rows._"]
    headers = list(rows[0].keys())
    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"]
    for row in rows:
        lines.append("| " + " | ".join(str(row.get(header, "")) for header in headers) + " |")
    return lines


def parse_float(value: str | None) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except ValueError:
        return None


def pct(count: int, total: int) -> str:
    if total <= 0:
        return "nan"
    return f"{count / total * 100:.1f}%"


def count_rate(count: int, total: int) -> str:
    return f"{count}/{total} ({pct(count, total)})"


def rel(path: Path) -> str:
    return path.as_posix().replace("/workspace/", "").replace("phases/p0-audit/", "")


def to_yaml(value: Any, indent: int = 0) -> str:
    space = " " * indent
    if isinstance(value, dict):
        lines = []
        for key, item in value.items():
            if isinstance(item, (dict, list)):
                lines.append(f"{space}{key}:")
                lines.append(to_yaml(item, indent + 2))
            else:
                lines.append(f"{space}{key}: {yaml_scalar(item)}")
        return "\n".join(lines) + ("\n" if indent == 0 else "")
    if isinstance(value, list):
        lines = []
        for item in value:
            if isinstance(item, (dict, list)):
                lines.append(f"{space}-")
                lines.append(to_yaml(item, indent + 2))
            else:
                lines.append(f"{space}- {yaml_scalar(item)}")
        return "\n".join(lines)
    return f"{space}{yaml_scalar(value)}"


def yaml_scalar(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    text = str(value)
    if not text or any(ch in text for ch in [":", "#", "{", "}", "[", "]", ",", "\n"]):
        return json.dumps(text, ensure_ascii=False)
    return text


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("host", "prepare", "postprocess"), default="host")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.mode == "host":
        host_entrypoint()
    elif args.mode == "prepare":
        prepare_entrypoint()
    elif args.mode == "postprocess":
        postprocess_entrypoint()
    else:
        raise AssertionError(args.mode)


if __name__ == "__main__":
    main()
