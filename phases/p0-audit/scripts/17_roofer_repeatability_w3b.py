#!/usr/bin/env python3
"""Estimate Roofer default repeatability on the W2-1c coverage-control set.

Run from phases/p0-audit/. The existing W2-3a full93/default run is treated as run 1
because it already used the 93-building filter, explicit Roofer default
parameters, and the same plumbing used here.
"""

from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import math
import os
import shutil
import subprocess
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


TASK_ID = "W3-2b"
EXISTING_RUN_ID = "w2_3a_roofer_tuning_20260612_202013"
AOI_BBOX = (690791.740, 5335864.050, 691154.650, 5336353.850)
ROOFER_JOBS = 32
DEFAULT_PARAMS = {
    "plane_detect_epsilon": 0.30,
    "plane_detect_min_points": 15,
    "complexity_factor": 0.888,
}


def host_entrypoint() -> None:
    repo = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env.setdefault("P0_UID", str(os.getuid()))
    env.setdefault("P0_GID", str(os.getgid()))
    run_id = env.get("RUN_ID") or datetime.now().strftime("w3_2b_roofer_repeatability_%Y%m%d_%H%M%S")
    git_commit = capture(["git", "rev-parse", "--short", "HEAD"], cwd=repo.parent).strip()
    run_dir = repo / "runs" / run_id
    logs_dir = run_dir / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    compose = ["docker", "compose", "-f", str(repo / "env/docker-compose.p0.yml")]

    write_host_config(run_dir, run_id, git_commit)
    write_host_versions(repo, run_dir, compose, env, git_commit)
    common_env = ["-e", f"RUN_ID={run_id}", "-e", f"P0_GIT_COMMIT={git_commit}"]
    run(
        compose
        + [
            "run",
            "-T",
            "--rm",
            *common_env,
            "tools",
            "python",
            "/workspace/scripts/17_roofer_repeatability_w3b.py",
            "--mode",
            "prepare",
        ],
        cwd=repo,
        env=env,
        log_path=logs_dir / "prepare.log",
    )

    for row in read_csv(run_dir / "execution_plan.csv"):
        run_roofer_plan_row(repo, compose, env, logs_dir, row)

    run(
        compose
        + [
            "run",
            "-T",
            "--rm",
            *common_env,
            "tools",
            "python",
            "/workspace/scripts/17_roofer_repeatability_w3b.py",
            "--mode",
            "postprocess",
        ],
        cwd=repo,
        env=env,
        log_path=logs_dir / "postprocess.log",
    )

    print(f"run_id={run_id}")
    print(f"run_dir=runs/{run_id}")
    print("report=docs/W3_2b_roofer_repeatability.md")


def run_roofer_plan_row(
    repo: Path,
    compose: list[str],
    env: dict[str, str],
    logs_dir: Path,
    row: dict[str, str],
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
    log_name = f"roofer_{row['stage']}_{row['input'].lower()}_{row['config_id']}.log"
    run(cmd, cwd=repo, env=env, log_path=logs_dir / log_name)


def prepare_entrypoint() -> None:
    root = Path("/workspace")
    run_id = os.environ["RUN_ID"]
    run_dir = root / "runs" / run_id
    docs = root / "docs"
    run_dir.mkdir(parents=True, exist_ok=True)

    coverage_rows = [row for row in read_csv(docs / "W2_1c_paired_status.csv") if row["coverage_control_population"] == "yes"]
    coverage_ids = sorted(row["building_id"] for row in coverage_rows)
    write_csv(run_dir / "coverage_control_ids.csv", [{"building_id": bid} for bid in coverage_ids])
    plan_rows = []
    for stage in ("run_2", "run_3"):
        for input_label in ("ALS", "DIM"):
            pointcloud = "/workspace/data/raw/als" if input_label == "ALS" else "/workspace/data/work/w2/dim_v1_classified_z_minus0p174.laz"
            plan_rows.append(plan_row(run_id, stage, input_label, coverage_ids, pointcloud))
    write_csv(run_dir / "execution_plan.csv", plan_rows)
    print(f"coverage_control_n={len(coverage_ids)}")
    print(f"execution_plan={len(plan_rows)}")


def plan_row(run_id: str, stage: str, input_label: str, building_ids: list[str], pointcloud: str) -> dict[str, str]:
    return {
        "stage": stage,
        "input": input_label,
        "config_id": "default",
        "params_json": json.dumps(DEFAULT_PARAMS, sort_keys=True, separators=(",", ":")),
        "building_count": str(len(building_ids)),
        "building_ids": ";".join(building_ids),
        "ogr_filter": ogr_filter(building_ids),
        "pointcloud_path": pointcloud,
        "footprint_path": "/workspace/data/work/w2/footprints_scene_aoi.gpkg",
        "output_dir": f"/workspace/runs/{run_id}/roofer/{stage}/{input_label.lower()}/default",
    }


def postprocess_entrypoint() -> None:
    root = Path("/workspace")
    docs = root / "docs"
    run_id = os.environ["RUN_ID"]
    run_dir = root / "runs" / run_id
    w2a = load_module("roofer_w2a", root / "scripts/13_roofer_tune_w2a.py")
    coverage_ids = [row["building_id"] for row in read_csv(run_dir / "coverage_control_ids.csv")]

    for row in read_csv(run_dir / "execution_plan.csv"):
        w2a.postprocess_roofer_output(root, run_dir, row["stage"], row["input"], row["config_id"], coverage_ids)

    status_by_run = load_three_run_status(root, run_dir)
    success_rows = build_success_rows(status_by_run, coverage_ids)
    building_rows, unstable_rows = build_building_rows(status_by_run, coverage_ids)
    noise_rows, conclusion = build_noise_rows(success_rows)

    outputs = [
        (docs / "W3_2b_roofer_repeatability_success.csv", success_rows),
        (docs / "W3_2b_roofer_repeatability_building_status.csv", building_rows),
        (docs / "W3_2b_roofer_repeatability_unstable_buildings.csv", unstable_rows),
        (docs / "W3_2b_roofer_repeatability_noise.csv", noise_rows),
    ]
    for path, rows in outputs:
        write_csv(path, rows)
    report = docs / "W3_2b_roofer_repeatability.md"
    write_report(report, run_id, success_rows, unstable_rows, noise_rows, conclusion)
    update_w3_summary(docs / "W3_summary.md", conclusion)
    copy_outputs(run_dir, [path for path, _rows in outputs] + [report, docs / "W3_summary.md"])
    write_run_summary(run_dir / "w3_2b_summary.json", success_rows, unstable_rows, noise_rows, conclusion)

    print(f"success_table={rel(docs / 'W3_2b_roofer_repeatability_success.csv')}")
    print(f"unstable_buildings={rel(docs / 'W3_2b_roofer_repeatability_unstable_buildings.csv')}")
    print(f"noise={conclusion}")
    print(f"report={rel(report)}")


def load_three_run_status(root: Path, run_dir: Path) -> dict[str, dict[str, dict[str, dict[str, str]]]]:
    specs = [
        ("run_1_existing", EXISTING_RUN_ID, root / "runs" / EXISTING_RUN_ID / "status/full93"),
        ("run_2", run_dir.name, run_dir / "status/run_2"),
        ("run_3", run_dir.name, run_dir / "status/run_3"),
    ]
    output: dict[str, dict[str, dict[str, dict[str, str]]]] = {}
    for run_label, source_run_id, status_dir in specs:
        output[run_label] = {"_source_run_id": {"value": {"source_run_id": source_run_id}}}
        for input_label in ("ALS", "DIM"):
            path = status_dir / f"{input_label.lower()}_default.csv"
            rows = read_csv(path)
            output[run_label][input_label] = {row["building_id"]: row for row in rows}
    return output


def build_success_rows(
    status_by_run: dict[str, dict[str, dict[str, dict[str, str]]]],
    building_ids: list[str],
) -> list[dict[str, str]]:
    rows = []
    for run_label in ("run_1_existing", "run_2", "run_3"):
        source_run_id = status_by_run[run_label]["_source_run_id"]["value"]["source_run_id"]
        for input_label in ("ALS", "DIM"):
            statuses = status_by_run[run_label][input_label]
            success = sum(statuses[bid]["status"] == "success" for bid in building_ids)
            rows.append(success_row(run_label, source_run_id, input_label, len(building_ids), success))
        both_success = sum(
            status_by_run[run_label]["ALS"][bid]["status"] == "success"
            and status_by_run[run_label]["DIM"][bid]["status"] == "success"
            for bid in building_ids
        )
        rows.append(success_row(run_label, source_run_id, "PAIRED_BOTH_SUCCESS", len(building_ids), both_success))
    return rows


def success_row(run_label: str, source_run_id: str, metric: str, total: int, success: int) -> dict[str, str]:
    return {
        "run_label": run_label,
        "source_run_id": source_run_id,
        "metric": metric,
        "n": str(total),
        "success_count": str(success),
        "success_rate": count_rate(success, total),
        "success_rate_pp": f"{success / total * 100:.6f}",
    }


def build_building_rows(
    status_by_run: dict[str, dict[str, dict[str, dict[str, str]]]],
    building_ids: list[str],
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    rows = []
    unstable = []
    for bid in building_ids:
        row = {"building_id": bid}
        unstable_fields = []
        for input_label in ("ALS", "DIM"):
            values = []
            reasons = []
            for run_label in ("run_1_existing", "run_2", "run_3"):
                status = status_by_run[run_label][input_label][bid]["status"]
                reason = status_by_run[run_label][input_label][bid]["reason"]
                row[f"{input_label.lower()}_{run_label}_status"] = status
                row[f"{input_label.lower()}_{run_label}_reason"] = reason
                values.append(status)
                reasons.append(reason)
            if len(set(zip(values, reasons))) > 1:
                unstable_fields.append(input_label)
        pair_values = []
        for run_label in ("run_1_existing", "run_2", "run_3"):
            pair = pair_category(
                status_by_run[run_label]["ALS"][bid]["status"],
                status_by_run[run_label]["DIM"][bid]["status"],
            )
            row[f"pair_{run_label}"] = pair
            pair_values.append(pair)
        if len(set(pair_values)) > 1:
            unstable_fields.append("PAIR")
        row["unstable_fields"] = ";".join(unstable_fields)
        rows.append(row)
        if unstable_fields:
            unstable.append(
                {
                    "building_id": bid,
                    "unstable_fields": row["unstable_fields"],
                    "als_sequence": sequence(row, "als"),
                    "dim_sequence": sequence(row, "dim"),
                    "pair_sequence": " -> ".join(row[f"pair_{run_label}"] for run_label in ("run_1_existing", "run_2", "run_3")),
                }
            )
    if not unstable:
        unstable.append(
            {
                "building_id": "NONE",
                "unstable_fields": "",
                "als_sequence": "",
                "dim_sequence": "",
                "pair_sequence": "",
            }
        )
    return rows, unstable


def sequence(row: dict[str, str], prefix: str) -> str:
    return " -> ".join(
        f"{row[f'{prefix}_{run_label}_status']}:{row[f'{prefix}_{run_label}_reason']}"
        for run_label in ("run_1_existing", "run_2", "run_3")
    )


def build_noise_rows(success_rows: list[dict[str, str]]) -> tuple[list[dict[str, str]], str]:
    rows = []
    max_half_range = -1.0
    max_metric = ""
    for metric in ("ALS", "DIM", "PAIRED_BOTH_SUCCESS"):
        metric_rows = [row for row in success_rows if row["metric"] == metric]
        values = [float(row["success_rate_pp"]) for row in metric_rows]
        min_v = min(values)
        max_v = max(values)
        mean_v = sum(values) / len(values)
        half_range = (max_v - min_v) / 2.0
        if half_range > max_half_range:
            max_half_range = half_range
            max_metric = metric
        rows.append(
            {
                "metric": metric,
                "n_runs": str(len(values)),
                "min_success_rate_pp": f"{min_v:.6f}",
                "max_success_rate_pp": f"{max_v:.6f}",
                "mean_success_rate_pp": f"{mean_v:.6f}",
                "range_pp": f"{max_v - min_v:.6f}",
                "half_range_pp": f"{half_range:.6f}",
                "success_count_values": ";".join(row["success_count"] for row in metric_rows),
            }
        )
    conclusion = f"Same-settings Roofer default run noise over three 93-building runs is +/-{max_half_range:.1f} pp by half-range, with the maximum on {max_metric}."
    return rows, conclusion


def write_report(
    path: Path,
    run_id: str,
    success_rows: list[dict[str, str]],
    unstable_rows: list[dict[str, str]],
    noise_rows: list[dict[str, str]],
    conclusion: str,
) -> None:
    unstable_count = 0 if unstable_rows and unstable_rows[0]["building_id"] == "NONE" else len(unstable_rows)
    lines = [
        "# W3-2b Roofer Default Repeatability",
        "",
        f"- Run ID: `{run_id}`",
        f"- Existing run used as run 1: `{EXISTING_RUN_ID}` `full93/default`.",
        "- Added runs: `run_2` and `run_3` in the run directory above.",
        "- Population: W2-1c coverage-control set, 93 buildings.",
        "- Roofer settings: explicit default `plane-detect-epsilon=0.30`, `plane-detect-min-points=15`, `complexity-factor=0.888`, `--jobs 32`, same AOI `--box`, same `--filter` list.",
        "",
        "## Success Rates",
        "",
    ]
    lines.extend(markdown_table(success_rows))
    lines.extend(
        [
            "",
            "## Run Noise",
            "",
        ]
    )
    lines.extend(markdown_table(noise_rows))
    lines.extend(["", f"- Noise conclusion: {conclusion}", ""])
    lines.extend(["## Unstable Building Results", "", f"- Buildings with any input or paired-category change across runs: {unstable_count}.", ""])
    lines.extend(markdown_table(unstable_rows))
    lines.extend(
        [
            "",
            "## Files",
            "",
            "- Success-rate table: `docs/W3_2b_roofer_repeatability_success.csv`",
            "- Building-level status table: `docs/W3_2b_roofer_repeatability_building_status.csv`",
            "- Unstable building list: `docs/W3_2b_roofer_repeatability_unstable_buildings.csv`",
            "- Noise table: `docs/W3_2b_roofer_repeatability_noise.csv`",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def update_w3_summary(path: Path, conclusion: str) -> None:
    text = path.read_text(encoding="utf-8")
    marker = "## Robustness Checks"
    note_line = (
        f"Noise-band note: W3-2b repeated Roofer default with identical 93-building settings; {conclusion} "
        "See `docs/W3_2b_roofer_repeatability.md`."
    )
    if "Noise-band note: W3-2b repeated Roofer default" in text:
        lines = [
            note_line if line.startswith("Noise-band note: W3-2b repeated Roofer default") else line
            for line in text.splitlines()
        ]
        text = "\n".join(lines) + "\n"
    elif marker in text:
        text = text.replace("### Roof-Matching Recovery Trace", "\n" + note_line + "\n\n### Roof-Matching Recovery Trace")
    else:
        text = text.rstrip() + "\n\n" + note_line + "\n"
    path.write_text(text, encoding="utf-8")


def write_run_summary(
    path: Path,
    success_rows: list[dict[str, str]],
    unstable_rows: list[dict[str, str]],
    noise_rows: list[dict[str, str]],
    conclusion: str,
) -> None:
    payload = {
        "task": TASK_ID,
        "run_id": os.environ["RUN_ID"],
        "existing_run_id": EXISTING_RUN_ID,
        "population_n": 93,
        "roofer_jobs": ROOFER_JOBS,
        "default_params": DEFAULT_PARAMS,
        "success": success_rows,
        "unstable_buildings": unstable_rows,
        "noise": noise_rows,
        "conclusion": conclusion,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_host_config(run_dir: Path, run_id: str, git_commit: str) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    config = {
        "task": "W3-2b_roofer_default_repeatability",
        "run_id": run_id,
        "git_commit": git_commit,
        "existing_run_id": EXISTING_RUN_ID,
        "population": "W2-1c coverage_control_population=yes",
        "population_n": 93,
        "aoi_bbox": list(AOI_BBOX),
        "roofer_jobs": ROOFER_JOBS,
        "default_params": DEFAULT_PARAMS,
        "added_runs": ["run_2", "run_3"],
    }
    (run_dir / "config.yaml").write_text(to_yaml(config), encoding="utf-8")


def write_host_versions(repo: Path, run_dir: Path, compose: list[str], env: dict[str, str], git_commit: str) -> None:
    lines = [
        "# W3-2b Tool Versions",
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


def run(cmd: list[str], cwd: Path | None = None, env: dict[str, str] | None = None, log_path: Path | None = None) -> None:
    print("+ " + " ".join(cmd), flush=True)
    if log_path:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("w", encoding="utf-8") as log:
            log.write("+ " + " ".join(cmd) + "\n")
            proc = subprocess.run(cmd, cwd=cwd, env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            log.write(proc.stdout)
            print(proc.stdout, end="", flush=True)
            proc.check_returncode()
            return
    subprocess.run(cmd, cwd=cwd, env=env, text=True, check=True)


def capture(cmd: list[str], cwd: Path | None = None, env: dict[str, str] | None = None) -> str:
    proc = subprocess.run(cmd, cwd=cwd, env=env, text=True, capture_output=True, check=False)
    return ((proc.stdout or "") + (proc.stderr or "")).strip()


def load_module(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if not spec or not spec.loader:
        raise RuntimeError(f"Cannot import {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


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


def count_rate(count: int, total: int) -> str:
    return f"{count}/{total} ({count / total * 100:.1f}%)" if total else "0/0 (nan%)"


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
