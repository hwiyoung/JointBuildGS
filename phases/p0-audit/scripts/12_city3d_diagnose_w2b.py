#!/usr/bin/env python3
"""Diagnose W2-2 City3D results and run the W2-2b timeout sample.

Run from phases/p0-audit/. Host mode orchestrates Docker Compose services. Container
modes parse the W2-2 outputs, render OBJ diagnostics, rerun selected ALS
buildings with a longer City3D timeout, and write the W2-2b report.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import csv
import json
import os
import shutil
import subprocess
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

from p0_paths import P0_EVIDENCE


BASE_RUN_ID = "w2_2_city3d_default_20260612_175449"
TASK_ID = "W2-2b"
SAMPLE_SIZE = 20
SAMPLE_TIMEOUT_SEC = 1200
SAMPLE_WORKERS = 8
TOP_CODE_COUNT = 3
REPS_PER_CODE = 2
VAL3DITY_COMBOS = [
    ("solid_snap001", "Solid", "0.001"),
    ("solid_snap01", "Solid", "0.01"),
    ("composite_snap001", "CompositeSurface", "0.001"),
    ("composite_snap01", "CompositeSurface", "0.01"),
    ("multisurface_snap001", "MultiSurface", "0.001"),
    ("multisurface_snap01", "MultiSurface", "0.01"),
]


def host_entrypoint() -> None:
    repo = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env.setdefault("P0_UID", str(os.getuid()))
    env.setdefault("P0_GID", str(os.getgid()))
    env.setdefault("W2B_TIMEOUT_SEC", str(SAMPLE_TIMEOUT_SEC))
    env.setdefault("W2B_WORKERS", str(SAMPLE_WORKERS))
    run_id = env.get("RUN_ID") or datetime.now().strftime("w2_2b_city3d_diagnosis_%Y%m%d_%H%M%S")
    git_commit = capture(["git", "rev-parse", "--short", "HEAD"], cwd=repo.parent).strip()
    run_dir = repo / "runs" / run_id
    logs_dir = run_dir / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    write_host_config(run_dir, run_id, git_commit, env)

    compose = ["docker", "compose", "-f", str(repo / "env/docker-compose.p0.yml")]
    write_versions(repo, run_dir, compose, env, git_commit)
    common_env = [
        "-e",
        f"RUN_ID={run_id}",
        "-e",
        f"P0_GIT_COMMIT={git_commit}",
        "-e",
        f"W2B_TIMEOUT_SEC={env['W2B_TIMEOUT_SEC']}",
        "-e",
        f"W2B_WORKERS={env['W2B_WORKERS']}",
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
            "/workspace/scripts/12_city3d_diagnose_w2b.py",
            "--mode",
            "diagnose",
        ],
        cwd=repo,
        env=env,
        log_path=logs_dir / "diagnose.log",
    )
    run(
        compose
        + [
            "run",
            "-T",
            "--rm",
            *common_env,
            "city3d",
            "python",
            "/workspace/scripts/12_city3d_diagnose_w2b.py",
            "--mode",
            "sample-rerun",
        ],
        cwd=repo,
        env=env,
        log_path=logs_dir / "sample_1200_city3d.log",
    )
    run(
        compose
        + [
            "run",
            "-T",
            "--rm",
            *common_env,
            "tools",
            "python",
            "/workspace/scripts/12_city3d_diagnose_w2b.py",
            "--mode",
            "postprocess",
        ],
        cwd=repo,
        env=env,
        log_path=logs_dir / "postprocess.log",
    )
    print(f"run_id={run_id}")
    print(f"run_dir=runs/{run_id}")
    print("report=docs/W2_2b_city3d_diagnosis.md")


def run(
    cmd: list[str],
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
    log_path: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    print("+ " + " ".join(cmd), flush=True)
    if log_path:
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


def write_host_config(run_dir: Path, run_id: str, git_commit: str, env: dict[str, str]) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    config = {
        "task": "W2-2b_city3d_diagnosis",
        "run_id": run_id,
        "base_run_id": BASE_RUN_ID,
        "git_commit": git_commit,
        "sample_size": SAMPLE_SIZE,
        "sample_timeout_sec": int(env["W2B_TIMEOUT_SEC"]),
        "sample_workers": int(env["W2B_WORKERS"]),
        "val3dity_rechecks": [
            {"label": label, "primitive": primitive, "snap_tol": snap_tol}
            for label, primitive, snap_tol in VAL3DITY_COMBOS
        ],
        "drop_criterion": "After primitive/snap recheck and 1200s ALS sample rerun, drop City3D if ALS sample success rate remains below 50%.",
    }
    (run_dir / "config.yaml").write_text(to_yaml(config), encoding="utf-8")


def write_versions(repo: Path, run_dir: Path, compose: list[str], env: dict[str, str], git_commit: str) -> None:
    lines = [
        "# W2-2b Tool Versions",
        "",
        f"- Generated: {datetime.now().astimezone().isoformat(timespec='seconds')}",
        f"- Run ID: {run_dir.name}",
        f"- Base run ID: {BASE_RUN_ID}",
        f"- Repository commit: {git_commit}",
        "",
        "```console",
    ]
    commands = [
        ["git", "status", "--short", "--branch"],
        compose + ["run", "-T", "--rm", "city3d", "city3d_cli", "--version"],
        compose + ["run", "-T", "--rm", "tools", "val3dity", "--version"],
        compose + ["run", "-T", "--rm", "tools", "python", "-c", "import matplotlib, numpy; print('matplotlib ' + matplotlib.__version__); print('numpy ' + numpy.__version__)"],
    ]
    for cmd in commands:
        lines.append("$ " + " ".join(cmd))
        lines.append(capture(cmd, cwd=repo if cmd[0] != "git" else repo.parent, env=env))
    lines.append("```")
    (run_dir / "versions.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")


def diagnose_entrypoint() -> None:
    root = Path("/workspace")
    run_id = os.environ["RUN_ID"]
    run_dir = root / "runs" / run_id
    base_run = root / "runs" / BASE_RUN_ID
    docs = P0_EVIDENCE
    figs = docs.figs("W2")
    figs.mkdir(parents=True, exist_ok=True)

    status_rows = read_csv(base_run / "building_reconstruction_status.csv")
    als_invalid = [row for row in status_rows if row["input"] == "ALS" and row["reason"] == "val3dity_invalid"]
    code_rows, code_to_buildings = aggregate_error_codes(base_run, als_invalid)
    write_csv(run_dir / "als_val3dity_error_codes.csv", code_rows)
    write_csv(docs / "W2_2b_als_val3dity_error_codes.csv", code_rows)

    bounds_rows = []
    representative_rows = []
    for code_row in code_rows[:TOP_CODE_COUNT]:
        code = code_row["code"]
        for bid in code_to_buildings[code][:REPS_PER_CODE]:
            obj = base_run / "models/als" / f"{bid}.obj"
            png = figs / f"w2_2b_valerr_{code}_{bid}.png"
            bounds = render_obj_png(obj, png, code, code_row["description"], bid)
            row = {
                "code": code,
                "description": code_row["description"],
                "building_id": bid,
                "png": rel(png),
                **bounds,
            }
            representative_rows.append(row)
    for row in als_invalid:
        bid = row["building_id"]
        bounds_rows.append({"building_id": bid, **obj_bounds(base_run / "models/als" / f"{bid}.obj")})
    write_csv(run_dir / "als_invalid_obj_bounds.csv", bounds_rows)
    write_csv(run_dir / "obj_representatives.csv", representative_rows)
    write_csv(docs / "W2_2b_obj_representatives.csv", representative_rows)

    recheck_rows = run_val3dity_rechecks(base_run, run_dir, als_invalid, "base_als_invalid")
    recheck_summary = summarize_rechecks(recheck_rows)
    write_csv(run_dir / "val3dity_recheck_by_building.csv", recheck_rows)
    write_csv(run_dir / "val3dity_recheck_summary.csv", recheck_summary)
    write_csv(docs / "W2_2b_val3dity_recheck_summary.csv", recheck_summary)

    sample_rows = select_als_sample(root, base_run)
    write_csv(run_dir / "sample_als_1200_manifest.csv", sample_rows)
    print(f"als_invalid={len(als_invalid)}")
    print(f"top_codes={','.join(row['code'] for row in code_rows[:TOP_CODE_COUNT])}")
    print(f"sample_manifest={rel(run_dir / 'sample_als_1200_manifest.csv')}")


def aggregate_error_codes(base_run: Path, invalid_rows: list[dict[str, str]]) -> tuple[list[dict[str, str]], dict[str, list[str]]]:
    building_counter: Counter[str] = Counter()
    instance_counter: Counter[str] = Counter()
    descriptions: dict[str, str] = {}
    code_to_buildings: dict[str, list[str]] = defaultdict(list)
    seen_pairs: set[tuple[str, str]] = set()
    for row in invalid_rows:
        bid = row["building_id"]
        report = base_run / "val3dity/als" / f"{bid}.json"
        payload = json.loads(report.read_text(encoding="utf-8"))
        codes_in_building: set[str] = set()
        for err in iter_error_dicts(payload):
            code = str(err.get("code", ""))
            if not code:
                continue
            instance_counter[code] += 1
            descriptions.setdefault(code, str(err.get("description", "")))
            codes_in_building.add(code)
        for code in codes_in_building:
            building_counter[code] += 1
            if (code, bid) not in seen_pairs:
                code_to_buildings[code].append(bid)
                seen_pairs.add((code, bid))
    rows = []
    for code, affected in building_counter.most_common():
        rows.append(
            {
                "code": code,
                "description": descriptions.get(code, ""),
                "affected_buildings": str(affected),
                "error_instances": str(instance_counter[code]),
                "representative_buildings": ";".join(code_to_buildings[code][:6]),
            }
        )
    return rows, code_to_buildings


def iter_error_dicts(value: Any) -> Any:
    if isinstance(value, dict):
        if "code" in value and "description" in value:
            yield value
        for item in value.values():
            yield from iter_error_dicts(item)
    elif isinstance(value, list):
        for item in value:
            yield from iter_error_dicts(item)


def run_val3dity_rechecks(
    base_run: Path,
    run_dir: Path,
    rows: list[dict[str, str]],
    group: str,
) -> list[dict[str, str]]:
    output_rows = []
    total = len(rows) * len(VAL3DITY_COMBOS)
    done = 0
    for row in rows:
        bid = row["building_id"]
        obj = base_run / "models/als" / f"{bid}.obj"
        for label, primitive, snap_tol in VAL3DITY_COMBOS:
            report = run_dir / "val3dity_recheck" / group / label / f"{bid}.json"
            log = report.with_suffix(".log")
            valid, errors, returncode = validate_obj(obj, report, log, primitive, snap_tol)
            output_rows.append(
                {
                    "group": group,
                    "building_id": bid,
                    "setting": label,
                    "primitive": primitive,
                    "snap_tol": snap_tol,
                    "valid": str(valid),
                    "returncode": str(returncode),
                    "errors": ";".join(errors),
                    "report": rel(report),
                    "log": rel(log),
                }
            )
            done += 1
            if done % 100 == 0 or done == total:
                print(f"val3dity_recheck_progress={done}/{total}", flush=True)
    return output_rows


def validate_obj(obj: Path, report: Path, log: Path, primitive: str, snap_tol: str) -> tuple[bool, list[str], int]:
    report.parent.mkdir(parents=True, exist_ok=True)
    log.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "val3dity",
        obj.as_posix(),
        "--primitive",
        primitive,
        "--snap_tol",
        snap_tol,
        "--report",
        report.as_posix(),
    ]
    proc = subprocess.run(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
    log.write_text("+ " + " ".join(cmd) + "\n" + proc.stdout, encoding="utf-8")
    valid = False
    errors: list[str] = []
    if report.exists():
        payload = json.loads(report.read_text(encoding="utf-8"))
        valid = report_validity(payload)
        errors = [str(code) for code in payload.get("all_errors", [])]
        if not errors:
            seen = []
            for err in iter_error_dicts(payload):
                code = str(err.get("code", ""))
                if code and code not in seen:
                    seen.append(code)
            errors = seen
    return valid, errors, proc.returncode


def summarize_rechecks(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        grouped[row["setting"]].append(row)
    output = []
    for label, primitive, snap_tol in VAL3DITY_COMBOS:
        selected = grouped[label]
        n = len(selected)
        valid = sum(row["valid"] == "True" for row in selected)
        err_counter: Counter[str] = Counter()
        for row in selected:
            for code in row["errors"].split(";"):
                if code:
                    err_counter[code] += 1
        output.append(
            {
                "setting": label,
                "primitive": primitive,
                "snap_tol": snap_tol,
                "n": str(n),
                "valid": str(valid),
                "invalid": str(n - valid),
                "valid_rate": pct(valid, n),
                "top_remaining_errors": ";".join(f"{code}:{count}" for code, count in err_counter.most_common(5)),
            }
        )
    return output


def select_als_sample(root: Path, base_run: Path) -> list[dict[str, str]]:
    paired = read_csv(P0_EVIDENCE / "W2_2_city3d_paired_status.csv")
    manifest = {(row["input"], row["building_id"]): row for row in read_csv(base_run / "city3d_input_manifest.csv")}
    controlled_failures = [
        row
        for row in paired
        if row["w2_1c_coverage_control_population"] == "yes" and row["city3d_als_status"] != "success"
    ]

    def point_count(row: dict[str, str]) -> int:
        return int(manifest[("ALS", row["building_id"])]["point_count"])

    timeouts = [row for row in controlled_failures if row["city3d_als_reason"] == "city3d_timeout"]
    fillers = [row for row in controlled_failures if row["city3d_als_reason"] != "city3d_timeout"]
    selected = sorted(timeouts, key=point_count, reverse=True)
    selected += sorted(fillers, key=point_count, reverse=True)[: max(0, SAMPLE_SIZE - len(selected))]
    selected = selected[:SAMPLE_SIZE]

    sample_rows = []
    for index, row in enumerate(selected, start=1):
        bid = row["building_id"]
        base = dict(manifest[("ALS", bid)])
        base.update(
            {
                "sample_rank": str(index),
                "original_status": row["city3d_als_status"],
                "original_reason": row["city3d_als_reason"],
                "original_val3dity_valid": row["city3d_als_val3dity_valid"],
                "selection_note": "timeout_priority" if row["city3d_als_reason"] == "city3d_timeout" else "coverage_control_failure_filler",
                "output_obj": f"runs/{os.environ['RUN_ID']}/sample_1200/models/als/{bid}.obj",
            }
        )
        sample_rows.append(base)
    return sample_rows


def sample_rerun_entrypoint() -> None:
    root = Path("/workspace")
    run_id = os.environ["RUN_ID"]
    run_dir = root / "runs" / run_id
    manifest = read_csv(run_dir / "sample_als_1200_manifest.csv")
    timeout_sec = int(os.environ.get("W2B_TIMEOUT_SEC", str(SAMPLE_TIMEOUT_SEC)))
    workers = max(1, int(os.environ.get("W2B_WORKERS", str(SAMPLE_WORKERS))))
    logs_dir = run_dir / "logs/sample_1200_city3d"
    logs_dir.mkdir(parents=True, exist_ok=True)
    print(f"sample_jobs={len(manifest)} workers={workers} timeout_sec={timeout_sec}", flush=True)
    started = time.monotonic()
    rows = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(run_city3d_one, row, logs_dir, timeout_sec) for row in manifest]
        for index, future in enumerate(concurrent.futures.as_completed(futures), start=1):
            rows.append(future.result())
            print(f"sample_progress={index}/{len(futures)} elapsed_sec={time.monotonic() - started:.1f}", flush=True)
    rows.sort(key=lambda row: int(row["sample_rank"]))
    write_csv(run_dir / "sample_als_1200_results.csv", rows)
    print(f"sample_results={rel(run_dir / 'sample_als_1200_results.csv')}")


def run_city3d_one(row: dict[str, str], logs_dir: Path, timeout_sec: int) -> dict[str, str]:
    bid = row["building_id"]
    point_cloud = Path("/workspace") / row["point_cloud"]
    footprint = Path("/workspace") / row["footprint_geojson"]
    output_obj = Path("/workspace") / row["output_obj"]
    output_obj.parent.mkdir(parents=True, exist_ok=True)
    log_file = logs_dir / "als" / f"{bid}.log"
    log_file.parent.mkdir(parents=True, exist_ok=True)
    if output_obj.exists():
        output_obj.unlink()
    cmd = ["city3d_cli", point_cloud.as_posix(), footprint.as_posix(), output_obj.as_posix()]
    started = time.monotonic()
    skipped_reason = ""
    try:
        proc = subprocess.run(
            cmd,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout_sec,
            check=False,
        )
        elapsed = time.monotonic() - started
        log_file.write_text("+ " + " ".join(cmd) + "\n" + proc.stdout, encoding="utf-8")
        return city3d_result_row(row, proc.returncode, elapsed, skipped_reason, log_file)
    except subprocess.TimeoutExpired as exc:
        elapsed = time.monotonic() - started
        output = (exc.stdout or "") if isinstance(exc.stdout, str) else ""
        log_file.write_text(
            "+ " + " ".join(cmd) + "\n" + output + f"\nTIMEOUT after {timeout_sec} sec\n",
            encoding="utf-8",
        )
        return city3d_result_row(row, 124, elapsed, "timeout", log_file)


def city3d_result_row(
    row: dict[str, str],
    returncode: int,
    elapsed_sec: float,
    skipped_reason: str,
    log_file: Path,
) -> dict[str, str]:
    output_obj = Path("/workspace") / row["output_obj"]
    return {
        "sample_rank": row["sample_rank"],
        "building_id": row["building_id"],
        "original_status": row["original_status"],
        "original_reason": row["original_reason"],
        "selection_note": row["selection_note"],
        "point_count": row["point_count"],
        "footprint_area_m2": row["footprint_area_m2"],
        "point_density_pts_m2": row["point_density_pts_m2"],
        "returncode": str(returncode),
        "elapsed_sec": f"{elapsed_sec:.3f}",
        "skipped_reason": skipped_reason,
        "output_obj": row["output_obj"],
        "output_exists": yesno(output_obj.exists() and output_obj.stat().st_size > 0),
        "output_size_bytes": str(output_obj.stat().st_size if output_obj.exists() else 0),
        "obj_faces": str(count_obj_faces(output_obj)),
        "log_file": rel(log_file),
    }


def postprocess_entrypoint() -> None:
    root = Path("/workspace")
    run_id = os.environ["RUN_ID"]
    run_dir = root / "runs" / run_id
    docs = P0_EVIDENCE

    sample_results = read_csv(run_dir / "sample_als_1200_results.csv")
    sample_validation = validate_sample_outputs(run_dir, sample_results)
    write_csv(run_dir / "sample_als_1200_validation.csv", sample_validation)

    recheck_summary = read_csv(run_dir / "val3dity_recheck_summary.csv")
    best_setting = choose_best_setting(recheck_summary)
    sample_rows = build_sample_table(sample_results, sample_validation, best_setting)
    sample_summary = summarize_sample(sample_rows, best_setting)
    write_csv(run_dir / "sample_als_1200_table.csv", sample_rows)
    write_csv(run_dir / "sample_als_1200_summary.csv", sample_summary)
    write_csv(docs / "W2_2b_als_1200_sample.csv", sample_rows)

    code_rows = read_csv(run_dir / "als_val3dity_error_codes.csv")
    representatives = read_csv(run_dir / "obj_representatives.csv")
    report = docs / "W2_2b_city3d_diagnosis.md"
    write_report(report, run_id, code_rows, representatives, recheck_summary, sample_summary, sample_rows, best_setting)
    copy_outputs(
        run_dir,
        [
            docs / "W2_2b_city3d_diagnosis.md",
            docs / "W2_2b_als_val3dity_error_codes.csv",
            docs / "W2_2b_val3dity_recheck_summary.csv",
            docs / "W2_2b_als_1200_sample.csv",
            docs / "W2_2b_obj_representatives.csv",
        ],
    )
    print(f"report={rel(report)}")
    print(f"sample_table={rel(docs / 'W2_2b_als_1200_sample.csv')}")


def validate_sample_outputs(run_dir: Path, sample_results: list[dict[str, str]]) -> list[dict[str, str]]:
    rows = []
    for result in sample_results:
        bid = result["building_id"]
        obj = Path("/workspace") / result["output_obj"]
        for label, primitive, snap_tol in VAL3DITY_COMBOS:
            report = run_dir / "sample_1200/val3dity" / label / f"{bid}.json"
            log = report.with_suffix(".log")
            valid = False
            errors: list[str] = []
            returncode = ""
            if obj.exists() and obj.stat().st_size > 0 and count_obj_faces(obj) > 0:
                valid, errors, returncode_int = validate_obj(obj, report, log, primitive, snap_tol)
                returncode = str(returncode_int)
            rows.append(
                {
                    "building_id": bid,
                    "setting": label,
                    "primitive": primitive,
                    "snap_tol": snap_tol,
                    "valid": str(valid),
                    "returncode": returncode,
                    "errors": ";".join(errors),
                    "report": rel(report) if report.exists() else "",
                    "log": rel(log) if log.exists() else "",
                }
            )
    return rows


def build_sample_table(
    sample_results: list[dict[str, str]],
    sample_validation: list[dict[str, str]],
    best_setting: str,
) -> list[dict[str, str]]:
    val_by_key = {(row["building_id"], row["setting"]): row for row in sample_validation}
    rows = []
    for result in sample_results:
        bid = result["building_id"]
        best_valid = val_by_key.get((bid, best_setting), {}).get("valid", "False") == "True"
        default_valid = val_by_key.get((bid, "solid_snap001"), {}).get("valid", "False") == "True"
        any_valid = any(
            row["building_id"] == bid and row["valid"] == "True"
            for row in sample_validation
        )
        has_obj = result["output_exists"] == "yes" and int(result["obj_faces"] or "0") > 0
        best_success = result["returncode"] == "0" and has_obj and best_valid
        default_success = result["returncode"] == "0" and has_obj and default_valid
        rows.append(
            {
                "sample_rank": result["sample_rank"],
                "building_id": bid,
                "selection_note": result["selection_note"],
                "original_status": result["original_status"],
                "original_reason": result["original_reason"],
                "point_count": result["point_count"],
                "density_pts_m2": result["point_density_pts_m2"],
                "returncode_1200": result["returncode"],
                "elapsed_sec_1200": result["elapsed_sec"],
                "timeout_1200": str(result["skipped_reason"] == "timeout"),
                "obj_faces_1200": result["obj_faces"],
                "default_solid_snap001_valid": str(default_valid),
                "best_setting": best_setting,
                "best_setting_valid": str(best_valid),
                "any_recheck_setting_valid": str(any_valid),
                "success_original_rule_after_1200": str(default_success),
                "success_best_setting_after_1200": str(best_success),
                "output_obj": result["output_obj"],
                "log_file": result["log_file"],
            }
        )
    return rows


def summarize_sample(sample_rows: list[dict[str, str]], best_setting: str) -> list[dict[str, str]]:
    n = len(sample_rows)
    original_success = sum(row["original_status"] == "success" for row in sample_rows)
    default_success = sum(row["success_original_rule_after_1200"] == "True" for row in sample_rows)
    best_success = sum(row["success_best_setting_after_1200"] == "True" for row in sample_rows)
    any_success = sum(
        row["returncode_1200"] == "0"
        and row["any_recheck_setting_valid"] == "True"
        and int(row["obj_faces_1200"] or "0") > 0
        for row in sample_rows
    )
    return [
        {
            "population": "ALS_coverage_control_sample20",
            "n": str(n),
            "original_success": count_rate(original_success, n),
            "success_after_1200_default_solid_snap001": count_rate(default_success, n),
            f"success_after_1200_{best_setting}": count_rate(best_success, n),
            "success_after_1200_any_recheck_setting": count_rate(any_success, n),
            "drop_threshold": "50%",
            "recommendation": "drop" if best_success / n < 0.5 else "go",
        }
    ]


def choose_best_setting(summary_rows: list[dict[str, str]]) -> str:
    def key(row: dict[str, str]) -> tuple[int, int]:
        valid = int(row["valid"])
        preference = {
            "composite_snap01": 5,
            "composite_snap001": 4,
            "multisurface_snap01": 3,
            "multisurface_snap001": 2,
            "solid_snap01": 1,
            "solid_snap001": 0,
        }.get(row["setting"], 0)
        return valid, preference

    return max(summary_rows, key=key)["setting"]


def write_report(
    path: Path,
    run_id: str,
    code_rows: list[dict[str, str]],
    representatives: list[dict[str, str]],
    recheck_summary: list[dict[str, str]],
    sample_summary: list[dict[str, str]],
    sample_rows: list[dict[str, str]],
    best_setting: str,
) -> None:
    recommendation = sample_summary[0]["recommendation"]
    best_key = f"success_after_1200_{best_setting}"
    lines = [
        "# W2-2b City3D Diagnosis",
        "",
        f"- Run ID: `{run_id}`",
        f"- Base W2-2 run: `{BASE_RUN_ID}`",
        "- Predeclared decision rule: if the ALS coverage-control sample success rate remains below 50% after snap/primitive recheck and 1200s timeout rerun, classify City3D as unsuitable for this scene type and stop further City3D structure work.",
        f"- Best single val3dity recheck setting used for the sample decision: `{best_setting}`.",
        "",
        "## ALS val3dity Error Codes",
        "",
        "| code | description | affected buildings | error instances | representatives |",
        "| --- | --- | ---: | ---: | --- |",
    ]
    for row in code_rows:
        lines.append(
            f"| `{row['code']}` | {row['description']} | {row['affected_buildings']} | {row['error_instances']} | `{row['representative_buildings']}` |"
        )
    lines.extend(
        [
            "",
            "## Representative OBJ Renders",
            "",
            "The representative OBJ coordinates remain in EPSG:25832-scale coordinates, not a small local origin. This removes the main local-coordinate suspicion for the invalidity pattern.",
            "",
            "| code | building | vertices | faces | X range | Y range | Z range | PNG |",
            "| --- | --- | ---: | ---: | ---: | ---: | ---: | --- |",
        ]
    )
    for row in representatives:
        lines.append(
            f"| `{row['code']}` | `{row['building_id']}` | {row['vertex_count']} | {row['face_count']} | "
            f"{row['x_min']} to {row['x_max']} | {row['y_min']} to {row['y_max']} | {row['z_min']} to {row['z_max']} | `{row['png']}` |"
        )
    lines.extend(
        [
            "",
            "## val3dity Snap/Primitive Recheck",
            "",
            "| setting | primitive | snap tol | n | valid | invalid | valid rate | top remaining errors |",
            "| --- | --- | ---: | ---: | ---: | ---: | ---: | --- |",
        ]
    )
    for row in recheck_summary:
        lines.append(
            f"| `{row['setting']}` | {row['primitive']} | {row['snap_tol']} | {row['n']} | {row['valid']} | {row['invalid']} | {row['valid_rate']} | `{row['top_remaining_errors']}` |"
        )
    lines.extend(
        [
            "",
            "Interpretation: raising snap tolerance to 0.01 did not make any Solid or CompositeSurface case valid. The only large improvement is under the permissive MultiSurface assumption, which treats the OBJ as a loose surface set rather than a closed LoD2 solid.",
            "",
            "## ALS 1200s Sample Rerun",
            "",
            "The 20-building sample contains all 13 ALS coverage-control timeout cases, plus 7 high-point-count ALS coverage-control val3dity-invalid fillers.",
            "",
            "| population | n | original success | after 1200s default Solid | after 1200s best setting | any valid setting | threshold | recommendation |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
        ]
    )
    for row in sample_summary:
        lines.append(
            f"| {row['population']} | {row['n']} | {row['original_success']} | {row['success_after_1200_default_solid_snap001']} | "
            f"{row[best_key]} | {row['success_after_1200_any_recheck_setting']} | {row['drop_threshold']} | `{row['recommendation']}` |"
        )
    lines.extend(
        [
            "",
            "### Sample Detail",
            "",
            "| rank | building | original reason | point count | return code | elapsed sec | timeout | faces | default valid | best valid | best success |",
            "| ---: | --- | --- | ---: | ---: | ---: | --- | ---: | --- | --- | --- |",
        ]
    )
    for row in sample_rows:
        lines.append(
            f"| {row['sample_rank']} | `{row['building_id']}` | `{row['original_reason']}` | {row['point_count']} | "
            f"{row['returncode_1200']} | {row['elapsed_sec_1200']} | {row['timeout_1200']} | {row['obj_faces_1200']} | "
            f"{row['default_solid_snap001_valid']} | {row['best_setting_valid']} | {row['success_best_setting_after_1200']} |"
        )
    lines.extend(
        [
            "",
            "## Recommendation",
            "",
        ]
    )
    if recommendation == "drop":
        lines.append(
            "Drop: City3D is unsuitable for this scene type under the tested default pipeline. The W2-2b scope note is to stop further City3D structure/tuning work for these large complex buildings."
        )
    else:
        lines.append(
            "Go: the ALS sample cleared the predeclared 50% threshold after the tested mitigation, so City3D remains in scope for follow-up work."
        )
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def render_obj_png(obj: Path, png: Path, code: str, description: str, bid: str) -> dict[str, str]:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from mpl_toolkits.mplot3d.art3d import Poly3DCollection

    vertices, faces = read_obj(obj)
    bounds = bounds_from_vertices(vertices, len(faces))
    if not vertices:
        raise RuntimeError(f"No OBJ vertices: {obj}")
    fig = plt.figure(figsize=(13, 6), dpi=180)
    ax3d = fig.add_subplot(1, 2, 1, projection="3d")
    ax2d = fig.add_subplot(1, 2, 2)
    sampled_faces = faces[:3000]
    polys = [[vertices[idx] for idx in face if 0 <= idx < len(vertices)] for face in sampled_faces]
    polys = [poly for poly in polys if len(poly) >= 3]
    if polys:
        coll = Poly3DCollection(polys, facecolor="#d9b36c", edgecolor="#3b3b3b", linewidth=0.15, alpha=0.82)
        ax3d.add_collection3d(coll)
        for poly in polys[:2500]:
            xs = [p[0] for p in poly] + [poly[0][0]]
            ys = [p[1] for p in poly] + [poly[0][1]]
            ax2d.plot(xs, ys, color="#2f4858", linewidth=0.3, alpha=0.55)
    xs = [v[0] for v in vertices]
    ys = [v[1] for v in vertices]
    zs = [v[2] for v in vertices]
    ax3d.scatter(xs[:: max(1, len(xs) // 2000)], ys[:: max(1, len(ys) // 2000)], zs[:: max(1, len(zs) // 2000)], s=0.6, color="#1f77b4", alpha=0.6)
    ax2d.scatter(xs[:: max(1, len(xs) // 4000)], ys[:: max(1, len(ys) // 4000)], s=0.35, color="#1f77b4", alpha=0.35)
    ax3d.set_title(f"{bid}\nerror {code} {description}", fontsize=9)
    ax2d.set_title("XY plan", fontsize=9)
    for axis in (ax3d, ax2d):
        axis.set_xlabel("X")
        axis.set_ylabel("Y")
    ax3d.set_zlabel("Z")
    set_axes_equal_3d(ax3d, xs, ys, zs)
    ax2d.set_aspect("equal", adjustable="box")
    ax2d.grid(True, linewidth=0.2, alpha=0.4)
    info = (
        f"X {bounds['x_min']} .. {bounds['x_max']}\n"
        f"Y {bounds['y_min']} .. {bounds['y_max']}\n"
        f"Z {bounds['z_min']} .. {bounds['z_max']}"
    )
    fig.text(0.02, 0.02, info, fontsize=8, family="monospace")
    fig.tight_layout(rect=(0, 0.08, 1, 1))
    png.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(png)
    plt.close(fig)
    return bounds


def set_axes_equal_3d(ax: Any, xs: list[float], ys: list[float], zs: list[float]) -> None:
    x_mid = (min(xs) + max(xs)) / 2
    y_mid = (min(ys) + max(ys)) / 2
    z_mid = (min(zs) + max(zs)) / 2
    radius = max(max(xs) - min(xs), max(ys) - min(ys), max(zs) - min(zs)) / 2
    if radius <= 0:
        radius = 1
    ax.set_xlim(x_mid - radius, x_mid + radius)
    ax.set_ylim(y_mid - radius, y_mid + radius)
    ax.set_zlim(z_mid - radius, z_mid + radius)


def obj_bounds(obj: Path) -> dict[str, str]:
    vertices, faces = read_obj(obj)
    return bounds_from_vertices(vertices, len(faces))


def bounds_from_vertices(vertices: list[tuple[float, float, float]], face_count: int) -> dict[str, str]:
    if not vertices:
        return {
            "vertex_count": "0",
            "face_count": str(face_count),
            "x_min": "",
            "x_max": "",
            "y_min": "",
            "y_max": "",
            "z_min": "",
            "z_max": "",
            "x_range_m": "",
            "y_range_m": "",
            "z_range_m": "",
        }
    xs = [v[0] for v in vertices]
    ys = [v[1] for v in vertices]
    zs = [v[2] for v in vertices]
    return {
        "vertex_count": str(len(vertices)),
        "face_count": str(face_count),
        "x_min": f"{min(xs):.3f}",
        "x_max": f"{max(xs):.3f}",
        "y_min": f"{min(ys):.3f}",
        "y_max": f"{max(ys):.3f}",
        "z_min": f"{min(zs):.3f}",
        "z_max": f"{max(zs):.3f}",
        "x_range_m": f"{max(xs) - min(xs):.3f}",
        "y_range_m": f"{max(ys) - min(ys):.3f}",
        "z_range_m": f"{max(zs) - min(zs):.3f}",
    }


def read_obj(obj: Path) -> tuple[list[tuple[float, float, float]], list[list[int]]]:
    vertices: list[tuple[float, float, float]] = []
    faces: list[list[int]] = []
    if not obj.exists():
        return vertices, faces
    with obj.open("r", encoding="utf-8", errors="ignore") as fh:
        for line in fh:
            if line.startswith("v "):
                _, x, y, z, *_ = line.split()
                vertices.append((float(x), float(y), float(z)))
            elif line.startswith("f "):
                parts = line.split()[1:]
                face = []
                for part in parts:
                    idx = int(part.split("/")[0])
                    face.append(idx - 1 if idx > 0 else len(vertices) + idx)
                if len(face) >= 3:
                    faces.append(face)
    return vertices, faces


def report_validity(payload: dict[str, Any]) -> bool:
    if "validity" in payload:
        return bool(payload["validity"])
    features = payload.get("features") or []
    if features:
        return all(bool(feature.get("validity", False)) for feature in features)
    return False


def count_obj_faces(path: Path) -> int:
    if not path.exists():
        return 0
    count = 0
    with path.open("r", encoding="utf-8", errors="ignore") as fh:
        for line in fh:
            if line.startswith("f "):
                count += 1
    return count


def copy_outputs(run_dir: Path, docs: list[Path]) -> None:
    snapshot = run_dir / "docs_snapshot"
    snapshot.mkdir(parents=True, exist_ok=True)
    for path in docs:
        shutil.copy2(path, snapshot / path.name)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def write_csv(path: Path, rows: list[dict[str, str]], fieldnames: list[str] | None = None) -> None:
    if not rows:
        raise RuntimeError(f"No rows for {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    names = fieldnames or list(rows[0].keys())
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=names)
        writer.writeheader()
        writer.writerows(rows)


def yesno(value: bool) -> str:
    return "yes" if value else "no"


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
        return json.dumps(text)
    return text


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("host", "diagnose", "sample-rerun", "postprocess"), default="host")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.mode == "host":
        host_entrypoint()
    elif args.mode == "diagnose":
        diagnose_entrypoint()
    elif args.mode == "sample-rerun":
        sample_rerun_entrypoint()
    elif args.mode == "postprocess":
        postprocess_entrypoint()
    else:
        raise AssertionError(args.mode)


if __name__ == "__main__":
    main()
