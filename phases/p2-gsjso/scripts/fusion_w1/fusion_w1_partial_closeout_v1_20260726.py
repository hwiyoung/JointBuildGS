#!/usr/bin/env python3
"""Publish the Fusion-W1 06:30 partial closeout without starting a stage.

The command validates the frozen R0/R1/R2 and partial Section 3/5 artifacts,
derives zero learning/readout counters from immutable receipts, publishes the
two missing zero-run fixed CSVs, writes the factual partial report, and
atomically replaces the stale initial ``w1_manifest.json`` last.
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import fcntl
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from typing import Any, Mapping, Sequence
from zoneinfo import ZoneInfo


REPO = Path(__file__).resolve().parents[4]
DEFAULT_CONFIG = REPO / (
    "phases/p2-gsjso/configs/fusion_w1/"
    "fusion_w1_partial_closeout_v1_20260726.json"
)
CONFIG_SCHEMA = "jointbuildgs.fusion_w1.partial_closeout.config.v1"
MANIFEST_SCHEMA = "jointbuildgs.fusion_w1.partial_closeout_manifest.v1"
LOSS_SHARE_FIELDS = (
    "building_id",
    "arm",
    "run",
    "seed",
    "step",
    "term",
    "raw_loss",
    "weight",
    "weighted_loss",
    "weighted_loss_share",
    "grad_norm",
    "grad_norm_share",
    "grad_status",
    "total_loss",
    "psnr_train",
    "n_primitives",
    "denominator_role",
    "source_csv_sha256",
    "materialization_sha256",
)
ARMS = ("A", "B")
RUNS = ("r1", "r2")
TIERS = ("surface", "height", "outline")


class CloseoutError(RuntimeError):
    """A frozen closeout contract was not satisfied."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path, block_size: int = 1 << 20) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(block_size), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_json(payload: Any) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def require_equal(observed: Any, expected: Any, label: str) -> None:
    if observed != expected:
        raise CloseoutError(
            f"{label} mismatch: observed={observed!r}, expected={expected!r}"
        )


def repo_path(repo: Path, value: str) -> Path:
    path = (repo / value).resolve() if not Path(value).is_absolute() else Path(value).resolve()
    try:
        path.relative_to(repo.resolve())
    except ValueError as exc:
        raise CloseoutError(f"path escapes repository: {value}") from exc
    return path


def relative(repo: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(repo.resolve()).as_posix()
    except ValueError as exc:
        raise CloseoutError(f"path escapes repository: {path}") from exc


def require_regular(path: Path, label: str) -> None:
    if path.is_symlink() or not path.is_file():
        raise CloseoutError(f"{label} is not a regular file: {path}")


def load_json(path: Path) -> dict[str, Any]:
    require_regular(path, "JSON input")
    try:
        payload = json.loads(path.read_bytes())
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CloseoutError(f"cannot load JSON {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise CloseoutError(f"JSON root must be an object: {path}")
    return payload


def read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    require_regular(path, "CSV input")
    with path.open("r", encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames is None:
            raise CloseoutError(f"CSV has no header: {path}")
        return list(reader.fieldnames), list(reader)


def atomic_bytes(path: Path, payload: bytes) -> None:
    if path.is_symlink():
        raise CloseoutError(f"refusing atomic replacement of symlink: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "wb", dir=path.parent, prefix=f".{path.name}.", delete=False
    ) as stream:
        temporary = Path(stream.name)
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())
        os.fchmod(stream.fileno(), 0o644)
    os.replace(temporary, path)
    path.chmod(0o644)
    directory_fd = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)


def atomic_text(path: Path, payload: str) -> None:
    atomic_bytes(path, payload.encode("utf-8"))


def atomic_json(path: Path, payload: Mapping[str, Any]) -> None:
    atomic_text(
        path,
        json.dumps(
            dict(payload),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
            allow_nan=False,
        )
        + "\n",
    )


def empty_csv_bytes(fields: Sequence[str]) -> bytes:
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=list(fields), lineterminator="\n")
    writer.writeheader()
    return output.getvalue().encode("utf-8")


def verify_hash(path: Path, expected: str, label: str) -> str:
    require_regular(path, label)
    observed = sha256_file(path)
    require_equal(observed, expected, f"{label} SHA256")
    return observed


def run_git(repo: Path, *args: str, binary: bool = False) -> bytes | str:
    result = subprocess.run(
        ["git", *args],
        cwd=repo,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode:
        raise CloseoutError(
            f"git {' '.join(args)} failed: "
            f"{result.stderr.decode('utf-8', errors='replace').strip()}"
        )
    if binary:
        return result.stdout
    return result.stdout.decode("utf-8", errors="strict").strip()


def verify_git_contract(config: Mapping[str, Any], repo: Path) -> dict[str, Any]:
    branch = str(run_git(repo, "branch", "--show-current"))
    require_equal(branch, config["branch"], "git branch")
    head = str(run_git(repo, "rev-parse", "HEAD"))
    ancestor = config["git_contract"]["required_ancestor"]
    probe = subprocess.run(
        ["git", "merge-base", "--is-ancestor", ancestor, head],
        cwd=repo,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if probe.returncode != 0:
        raise CloseoutError(f"required ancestor is not in HEAD: {ancestor}")
    for logical in config["git_contract"]["implementation_paths"]:
        working = repo_path(repo, logical)
        require_regular(working, "closeout implementation")
        head_bytes = run_git(repo, "show", f"HEAD:{logical}", binary=True)
        if working.read_bytes() != head_bytes:
            raise CloseoutError(f"implementation differs from HEAD: {logical}")
    tracked = subprocess.run(
        ["git", "diff", "--quiet", "HEAD", "--"], cwd=repo, check=False
    )
    if tracked.returncode != 0:
        raise CloseoutError("tracked worktree is not clean before closeout")
    porcelain = str(run_git(repo, "status", "--short"))
    return {
        "branch": branch,
        "head": head,
        "required_ancestor": ancestor,
        "required_ancestor_of_head": True,
        "implementation_files_match_head": True,
        "tracked_worktree_clean_before_closeout": True,
        "status_porcelain_sha256": sha256_bytes(porcelain.encode("utf-8")),
        "status_porcelain_lines_n": len(porcelain.splitlines()) if porcelain else 0,
    }


def load_config(path: Path) -> dict[str, Any]:
    config = load_json(path)
    require_equal(config.get("schema"), CONFIG_SCHEMA, "config schema")
    require_equal(config.get("run_id"), "20260724_fusion_w1", "run ID")
    cutoff = datetime.fromisoformat(config["cutoff_kst"])
    if cutoff.tzinfo is None:
        raise CloseoutError("cutoff_kst must include an explicit offset")
    names = {
        "align_residuals": "w1_align_residuals.csv",
        "loss_shares": "w1_loss_shares.csv",
        "manifest": "w1_manifest.json",
        "report": "W_FUSION_W1_PARTIAL_REPORT_20260726.md",
    }
    for key, expected in names.items():
        require_equal(Path(config["outputs"][key]).name, expected, key)
    for key, expected in {
        "alignment_exact_bytes": True,
        "loss_share_header_only_zero_rows": True,
        "manifest_atomic_replace": True,
        "report_before_manifest": True,
        "issues_md_modified": False,
        "interpretation_or_verdict": False,
    }.items():
        require_equal(config["publication"].get(key), expected, key)
    return config


def verify_cutoff(config: Mapping[str, Any], now: datetime | None = None) -> dict[str, Any]:
    cutoff = datetime.fromisoformat(config["cutoff_kst"])
    observed = now or datetime.now(ZoneInfo("Asia/Seoul"))
    if observed.tzinfo is None:
        raise CloseoutError("closeout time must be timezone-aware")
    if observed < cutoff:
        raise CloseoutError(
            f"partial closeout is forbidden before cutoff: {observed.isoformat()}"
        )
    return {
        "locked_kst": cutoff.isoformat(),
        "observed_kst": observed.astimezone(ZoneInfo("Asia/Seoul")).isoformat(),
        "at_or_after_cutoff": True,
        "new_training_launch_forbidden": True,
    }


def verify_json_input(
    repo: Path, spec: Mapping[str, Any], state_key: str
) -> tuple[Path, dict[str, Any]]:
    path = repo_path(repo, spec["path"])
    verify_hash(path, spec["sha256"], path.name)
    payload = load_json(path)
    require_equal(payload.get("schema"), spec["schema"], f"{path.name} schema")
    require_equal(payload.get(state_key), spec[state_key], f"{path.name} {state_key}")
    return path, payload


def load_loss_share_fields(repo: Path, config: Mapping[str, Any]) -> tuple[str, ...]:
    spec = config["inputs"]["training_driver"]
    path = repo_path(repo, spec["path"])
    verify_hash(path, spec["sha256"], "training driver")
    module_spec = importlib.util.spec_from_file_location(
        "fusion_w1_training_closeout_contract", path
    )
    if module_spec is None or module_spec.loader is None:
        raise CloseoutError("cannot load the training driver")
    module = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(module)
    fields = tuple(getattr(module, "LOSS_SHARE_FIELDS", ()))
    require_equal(fields, LOSS_SHARE_FIELDS, "training LOSS_SHARE_FIELDS")
    return fields


def collect_issue_snapshot(repo: Path, config: Mapping[str, Any]) -> dict[str, Any]:
    path = repo_path(repo, config["inputs"]["issues"]["path"])
    require_regular(path, "issues.md")
    text = path.read_text(encoding="utf-8")
    headings = [
        match.group(1).strip()
        for match in re.finditer(r"^##\s+(.+?)\s*$", text, flags=re.MULTILINE)
    ]
    ids = [heading.split(" — ", 1)[0].strip() for heading in headings]
    missing = [
        value
        for value in config["inputs"]["issues"]["required_ids"]
        if value not in ids
    ]
    if missing:
        raise CloseoutError(f"required issues are missing: {missing}")
    return {
        "path": relative(repo, path),
        "sha256": sha256_file(path),
        "headings": headings,
        "issue_count": len(headings),
        "modified_by_closeout": False,
    }


def scalar_strings(value: Any) -> list[str]:
    if isinstance(value, dict):
        output: list[str] = []
        for nested in value.values():
            output.extend(scalar_strings(nested))
        return output
    if isinstance(value, list):
        output = []
        for nested in value:
            output.extend(scalar_strings(nested))
        return output
    return [value] if isinstance(value, str) else []


def collect_panel(repo: Path, config: Mapping[str, Any]) -> dict[str, Any]:
    spec = config["inputs"]["p0prime_panel"]
    panel = repo_path(repo, spec["path"])
    receipt = repo_path(repo, spec["receipt"])
    present = (panel.exists() or panel.is_symlink(), receipt.exists() or receipt.is_symlink())
    if present == (False, False):
        if spec.get("required_pair", False):
            raise CloseoutError("required P0-prime panel/receipt pair is missing")
        return {
            "status": "MISSING",
            "building_id": spec["building_id"],
            "path": spec["path"],
            "receipt": spec["receipt"],
        }
    if present[0] != present[1]:
        raise CloseoutError("P0-prime panel/receipt pair is asymmetric")
    require_regular(panel, "P0-prime panel")
    require_regular(receipt, "P0-prime panel receipt")
    panel_sha = sha256_file(panel)
    receipt_payload = load_json(receipt)
    strings = scalar_strings(receipt_payload)
    if spec["path"] not in strings or panel_sha not in strings:
        raise CloseoutError("P0-prime panel receipt does not bind path and SHA256")
    return {
        "status": "PRESENT",
        "building_id": spec["building_id"],
        "path": spec["path"],
        "sha256": panel_sha,
        "bytes": panel.stat().st_size,
        "receipt": spec["receipt"],
        "receipt_sha256": sha256_file(receipt),
        "receipt_schema": receipt_payload.get("schema"),
        "receipt_state": receipt_payload.get("state", receipt_payload.get("status")),
        "role": "pre_learning_p0prime_qualitative_panel",
    }


def receipt_paths(root: Path, names: Sequence[str]) -> list[Path]:
    if not root.exists():
        return []
    if root.is_symlink() or not root.is_dir():
        raise CloseoutError(f"counter root is not a directory: {root}")
    wanted = set(names)
    return sorted(
        path for path in root.rglob("*") if path.is_file() and path.name in wanted
    )


def zero_counter_snapshot(repo: Path, config: Mapping[str, Any]) -> dict[str, Any]:
    contract = config["counter_contract"]
    training_root = repo_path(repo, contract["training_root"])
    training_names = [
        contract["training_started_receipt"],
        contract["training_completed_receipt"],
        contract["training_failed_receipt"],
    ]
    training_receipts = receipt_paths(training_root, training_names)
    if training_receipts:
        raise CloseoutError(
            "training receipts are not zero: "
            + ", ".join(relative(repo, path) for path in training_receipts)
        )
    training_counter = repo_path(repo, contract["training_counter"])
    training_counter_record: dict[str, Any] = {"exists": False}
    if training_counter.exists() or training_counter.is_symlink():
        payload = load_json(training_counter)
        require_equal(
            payload.get("schema"),
            "jointbuildgs.fusion_w1.training_runtime_counters.v1",
            "training counter schema",
        )
        values = {
            key: int(payload.get(key, 0))
            for key in (
                "jobs_claimed",
                "docker_processes_started",
                "jobs_completed",
                "jobs_failed",
            )
        }
        if any(values.values()):
            raise CloseoutError(f"training counter is not zero: {values}")
        training_counter_record = {
            "exists": True,
            "path": relative(repo, training_counter),
            "sha256": sha256_file(training_counter),
            **values,
        }
    readout_root = repo_path(repo, contract["readout_root"])
    readout_receipts = receipt_paths(
        readout_root, contract["readout_started_receipts"]
    )
    if readout_receipts:
        raise CloseoutError(
            "Section 5 STARTED receipts are not zero: "
            + ", ".join(relative(repo, path) for path in readout_receipts)
        )
    readout_counter = repo_path(repo, contract["readout_counter"])
    readout_counter_record: dict[str, Any] = {"exists": False}
    if readout_counter.exists() or readout_counter.is_symlink():
        payload = load_json(readout_counter)
        require_equal(
            payload.get("schema"),
            "jointbuildgs.fusion_w1.readout_counters.v1",
            "readout counter schema",
        )
        values = {
            key: int(payload.get(key, 0))
            for key in (
                "readout_runs_started",
                "roofer_runs_started",
                "scoring_runs_started",
            )
        }
        if any(values.values()):
            raise CloseoutError(f"readout counter is not zero: {values}")
        readout_counter_record = {
            "exists": True,
            "path": relative(repo, readout_counter),
            "sha256": sha256_file(readout_counter),
            **values,
        }
    materialized = receipt_paths(training_root, ["materialization_manifest.json"])
    return {
        "learning_runs_started": 0,
        "readout_runs_started": 0,
        "roofer_runs_started": 0,
        "scoring_runs_started": 0,
        "training_receipts_n": 0,
        "training_materializations_n": len(materialized),
        "section5_started_receipts_n": 0,
        "training_counter": training_counter_record,
        "readout_counter": readout_counter_record,
        "counter_truth": "immutable_STARTED_receipts_and_zero_locked_CSV_rows",
    }


def collect_inputs(repo: Path, config: Mapping[str, Any]) -> dict[str, Any]:
    inputs = config["inputs"]
    r0_path, r0 = verify_json_input(repo, inputs["r0"], "status")
    r1_path, r1 = verify_json_input(repo, inputs["r1"], "status")
    r2_path, r2 = verify_json_input(repo, inputs["r2"], "status")
    require_equal(r0["execution_counters"], {
        "learning_runs_started": 0,
        "readout_runs_started": 0,
        "roofer_runs_started": 0,
        "scoring_runs_started": 0,
    }, "R0 counters")
    require_equal(r1.get("image_count"), 937, "R1 image count")
    require_equal(r1.get("transform_application_count"), 1, "R1 transform count")
    diagnostic = r1["diagnostic_reproduction"]
    for key, expected in {
        "population_n": 178,
        "n_threshold": 40,
        "correspondence_capable_n": 132,
        "matched_median_le_0p3_n": 132,
        "core_population_n": 28,
        "core_correspondence_capable_n": 24,
        "core_matched_median_le_0p3_n": 24,
    }.items():
        require_equal(diagnostic.get(key), expected, f"R1 diagnostic {key}")
    slots = r2["gate_slots"]
    for key, expected in {
        "population_n": 178,
        "n_threshold": 40,
        "correspondence_capable_n": 132,
        "capable_matched_median_le_0p3_n": 132,
        "core_population_n": 28,
        "core_correspondence_capable_n": 24,
        "core_capable_matched_median_le_0p3_n": 24,
    }.items():
        require_equal(slots.get(key), expected, f"R2 gate slot {key}")
    require_equal(r2["qualitative_overlays"].get("count"), 28, "R2 overlay count")

    target_path = repo_path(repo, inputs["targets"]["path"])
    verify_hash(target_path, inputs["targets"]["sha256"], "w1_targets.csv")
    _, targets = read_csv(target_path)
    require_equal(len(targets), inputs["targets"]["rows"], "target rows")
    cohort_counts = {value: sum(row["cohort"] == value for row in targets) for value in ("core", "extension")}
    tier_counts = {value: sum(row["tier"] == value for row in targets) for value in TIERS}
    targets_manifest_path, targets_manifest = verify_json_input(
        repo, inputs["targets_manifest"], "status"
    )
    require_equal(targets_manifest.get("core_priority_complete"), False, "target core priority completeness")

    alignment_path = repo_path(repo, inputs["alignment_source"]["path"])
    verify_hash(
        alignment_path,
        inputs["alignment_source"]["sha256"],
        "coregdiag building residuals",
    )
    _, alignment_rows = read_csv(alignment_path)
    require_equal(len(alignment_rows), 178, "alignment building rows")

    preprocess_path, preprocess = verify_json_input(
        repo, inputs["preprocess_manifest"], "status"
    )
    require_equal(preprocess.get("completed_buildings_n"), 1, "preprocess completed")
    require_equal(preprocess.get("core_completed_n"), 1, "preprocess core completed")
    require_equal(preprocess.get("core_expected_n"), 28, "preprocess core expected")
    require_equal(len(preprocess.get("buildings", [])), 1, "preprocess building records")

    seed_path = repo_path(repo, inputs["seed_stats"]["path"])
    verify_hash(seed_path, inputs["seed_stats"]["sha256"], "w1_seed_stats.csv")
    _, seed_rows = read_csv(seed_path)
    require_equal(len(seed_rows), inputs["seed_stats"]["rows"], "seed rows")
    seed_row = seed_rows[0]
    building = preprocess["buildings"][0]
    require_equal(seed_row["building_id"], building["building_id"], "seed building")
    require_equal(int(seed_row["output_points_n"]), building["seed_points_n"], "seed points")

    p0_path, p0 = verify_json_input(repo, inputs["p0prime_manifest"], "state")
    p0_driver_path = repo_path(repo, inputs["p0prime_driver"]["path"])
    verify_hash(p0_driver_path, inputs["p0prime_driver"]["sha256"], "P0-prime driver")
    require_equal(p0.get("manifest_written_last"), True, "P0-prime final manifest publication")
    require_equal(p0["population"].get("completed_count"), 1, "P0-prime completed")
    require_equal(p0["population"].get("target_count"), 178, "P0-prime target")
    require_equal(p0.get("learning_runs_started"), 0, "P0-prime learning")
    p0_scores_path = repo_path(repo, inputs["p0prime_scores"]["path"])
    verify_hash(p0_scores_path, inputs["p0prime_scores"]["sha256"], "P0-prime scores")
    _, p0_rows = read_csv(p0_scores_path)
    require_equal(len(p0_rows), inputs["p0prime_scores"]["rows"], "P0-prime rows")
    require_equal(p0_rows[0].get("status"), "MEASURED", "P0-prime score status")
    require_equal(p0["scores_csv"].get("sha256"), inputs["p0prime_scores"]["sha256"], "P0-prime manifest score SHA")
    completion = p0["completion_records"][0]
    complete_path = repo_path(repo, completion["complete_receipt"])
    verify_hash(complete_path, completion["complete_receipt_sha256"], "P0-prime completion")
    complete = load_json(complete_path)
    require_equal(complete.get("state"), "COMPLETE", "P0-prime completion state")

    scores_path = repo_path(repo, inputs["scores"]["path"])
    verify_hash(scores_path, inputs["scores"]["sha256"], "w1_scores_building.csv")
    _, score_rows = read_csv(scores_path)
    require_equal(len(score_rows), 0, "fusion score rows")
    summary_path = repo_path(repo, inputs["summary"]["path"])
    verify_hash(summary_path, inputs["summary"]["sha256"], "w1_summary.csv")
    _, summary_rows = read_csv(summary_path)
    require_equal(len(summary_rows), inputs["summary"]["rows"], "summary rows")
    require_equal(
        {(row["tier"], row["arm"], row["run"]) for row in summary_rows},
        {(tier, arm, run) for tier in TIERS for arm in ARMS for run in RUNS},
        "summary tier/arm/run cells",
    )
    if any(row.get("status") != inputs["summary"]["required_status"] for row in summary_rows):
        raise CloseoutError("w1_summary.csv contains a measured row")

    training_config_path = repo_path(repo, inputs["training_config"]["path"])
    verify_hash(training_config_path, inputs["training_config"]["sha256"], "training config")
    training_config = load_json(training_config_path)
    require_equal(training_config["launch_contract"].get("cutoff_kst"), config["cutoff_kst"], "training cutoff")
    loss_fields = load_loss_share_fields(repo, config)

    stale_path, stale = verify_json_input(repo, inputs["stale_manifest"], "run_status")
    issues = collect_issue_snapshot(repo, config)
    panel = collect_panel(repo, config)
    counters = zero_counter_snapshot(repo, config)
    return {
        "paths": {
            "r0": r0_path,
            "r1": r1_path,
            "r2": r2_path,
            "targets": target_path,
            "targets_manifest": targets_manifest_path,
            "alignment_source": alignment_path,
            "preprocess": preprocess_path,
            "seed_stats": seed_path,
            "p0prime": p0_path,
            "p0prime_scores": p0_scores_path,
            "scores": scores_path,
            "summary": summary_path,
            "stale_manifest": stale_path,
        },
        "r0": r0,
        "r1": r1,
        "r2": r2,
        "targets": {
            "population_n": len(targets),
            "resolved_core_lower_bound_n": cohort_counts["core"],
            "provisional_extension_n": cohort_counts["extension"],
            "tier_counts": tier_counts,
            "queue_status": targets_manifest.get("queue_status"),
            "core_priority_complete": False,
        },
        "preprocess": preprocess,
        "seed_row": seed_row,
        "p0prime": p0,
        "p0prime_row": p0_rows[0],
        "scores_rows_n": 0,
        "summary_rows_n": len(summary_rows),
        "summary_not_measured_rows_n": len(summary_rows),
        "loss_share_fields": loss_fields,
        "stale_manifest": stale,
        "issues": issues,
        "panel": panel,
        "counters": counters,
        "input_sha256": {
            key: spec["sha256"]
            for key, spec in inputs.items()
            if isinstance(spec, dict) and "sha256" in spec
        },
    }


def publish_exact_or_accept(path: Path, payload: bytes, label: str) -> None:
    if path.exists() or path.is_symlink():
        require_regular(path, label)
        if path.read_bytes() != payload:
            raise CloseoutError(f"existing {label} differs from required bytes")
        return
    atomic_bytes(path, payload)
    if path.read_bytes() != payload:
        raise CloseoutError(f"{label} byte publication verification failed")


def grade_rows() -> list[dict[str, str]]:
    return [
        {
            "scale": str(index),
            "name": name,
            "status": "NOT_MEASURED",
            "value": "",
            "measurement_basis": "two_run_training_measurements_n=0",
        }
        for index, name in enumerate(
            (
                "assembly_establishment",
                "seed_retention",
                "textured_boundary_improvement",
                "supervision_removal_control",
            ),
            start=1,
        )
    ]


def markdown_link(path: str, label: str | None = None) -> str:
    return f"[{label or Path(path).name}]({Path(path).name})"


def run_link(config: Mapping[str, Any], path: str, label: str | None = None) -> str:
    run_dir = Path(config["outputs"]["manifest"]).parent
    try:
        target = Path(path).relative_to(run_dir).as_posix()
    except ValueError as exc:
        raise CloseoutError(f"report link is outside run directory: {path}") from exc
    return f"[{label or Path(path).name}]({target})"


def render_report(
    config: Mapping[str, Any], snapshot: Mapping[str, Any], created_at: str
) -> str:
    r1 = snapshot["r1"]
    diag = r1["diagnostic_reproduction"]
    validation = r1["pose_validation"]
    r2 = snapshot["r2"]
    slots = r2["gate_slots"]
    targets = snapshot["targets"]
    preprocess = snapshot["preprocess"]
    seed = snapshot["seed_row"]
    p0 = snapshot["p0prime"]
    p0row = snapshot["p0prime_row"]
    panel = snapshot["panel"]
    issues = snapshot["issues"]
    output = config["outputs"]
    lines = [
        "# Fusion W1 06:30 부분 종료 기록 — 2026-07-26",
        "",
        "문서 역할: 수치·산출물·미완 단계 기록. 해석 및 사람 판정은 포함하지 않는다.",
        "",
        f"- 생성 시각(UTC): `{created_at}`",
        f"- cutoff(KST): `{config['cutoff_kst']}`",
        f"- run: `{config['run_id']}`",
        "",
        "## R1 검증 표",
        "",
        "| 항목 | 기록값 |",
        "|---|---|",
        f"| R1 status | `{r1['status']}` |",
        f"| 카메라 / 변환 적용 | `{r1['image_count']}` / `{r1['transform_application_count']}` |",
        f"| source images.bin SHA256 | `{r1['source_sha256']['images.bin']}` |",
        f"| corrected images.bin SHA256 | `{r1['derived_sha256']['images.bin']}` |",
        f"| roundtrip R max | `{validation['maximum_pose_roundtrip_rotation_matrix_error']}` |",
        f"| roundtrip t max (m) | `{validation['maximum_pose_roundtrip_translation_error_m']}` |",
        f"| projection max | `{validation['maximum_projection_invariance_error']}` |",
        f"| camera-center max (m) | `{validation['maximum_camera_center_error_m']}` |",
        f"| 대응 가능 / 기준 충족 | `{diag['correspondence_capable_n']}/{diag['population_n']}` / `{diag['matched_median_le_0p3_n']}/{diag['correspondence_capable_n']}` |",
        f"| 핵심군 대응 가능 / 기준 충족 | `{diag['core_correspondence_capable_n']}/{diag['core_population_n']}` / `{diag['core_matched_median_le_0p3_n']}/{diag['core_correspondence_capable_n']}` |",
        f"| 동별 중앙의 중앙 (m) | `{diag['building_balanced_median_of_matched_medians_m']}` |",
        f"| T5 총 잔차 (m) | `{diag['t5_building_balanced_median_r_total_m']}` |",
        "",
        "## R2 관문 A v2 및 오버레이",
        "",
        "| 항목 | 기록값 |",
        "|---|---|",
        f"| Gate A v2 | `{r2['status']}` |",
        f"| n* | `{slots['n_threshold']}` |",
        f"| 대응 가능 / 기준 충족 | `{slots['correspondence_capable_n']}/{slots['population_n']}` / `{slots['capable_matched_median_le_0p3_n']}/{slots['correspondence_capable_n']}` |",
        f"| 핵심군 | `{slots['core_correspondence_capable_n']}/{slots['core_capable_matched_median_le_0p3_n']}` |",
        f"| 대응 불가 표면/높이/윤곽 | `{slots['incapable_tier_counts']['surface']}/{slots['incapable_tier_counts']['height']}/{slots['incapable_tier_counts']['outline']}` |",
        f"| 오버레이 | `{r2['qualitative_overlays']['count']}` PNG · {run_link(config, r2['qualitative_overlays']['index_path'], 'index')} · [directory](resume_v2/w1_align_overlays_v2/) |",
        "",
        "## 눈금 1–4",
        "",
        "| 눈금 | 항목 | 상태 | 값 | 근거 수량 |",
        "|---:|---|---|---|---|",
    ]
    for row in grade_rows():
        lines.append(
            f"| {row['scale']} | `{row['name']}` | `NOT_MEASURED` | — | `2-run n=0` |"
        )
    lines.extend(
        [
            "",
            "## 대상·전처리·P0′ 수량",
            "",
            "| 단계 | 기록값 |",
            "|---|---|",
            f"| target queue | `{targets['population_n']}`동; resolved core lower bound `{targets['resolved_core_lower_bound_n']}`; provisional extension `{targets['provisional_extension_n']}`; core_priority_complete=`false` |",
            f"| target 층 | surface `{targets['tier_counts']['surface']}`, height `{targets['tier_counts']['height']}`, outline `{targets['tier_counts']['outline']}` |",
            f"| preprocess | `{preprocess['completed_buildings_n']}`동; core `{preprocess['core_completed_n']}/{preprocess['core_expected_n']}`; status `{preprocess['status']}` |",
            f"| preprocess 첫 동 | `{seed['building_id']}`; views `{seed['views_n']}`; points `{seed['output_points_n']}`; class2/class6 `{seed['class2_n']}/{seed['class6_n']}` |",
            f"| P0′ | `{p0['population']['completed_count']}/{p0['population']['target_count']}`동; assembly LoD2 `{p0['population']['assembly_lod2_success_count']}`; val3dity valid `{p0['population']['val3dity_valid_count']}`; state `{p0['state']}` |",
            f"| P0′ 첫 동 지표 | plane F1 `{p0row['plane_f1']}`; RMS `{p0row['roof_rms_m']} m`; completeness `{p0row['roof_completeness']}`; face ratio `{p0row['face_count_ratio']}` |",
            f"| P0′ vs P0 Ref-L | assembly match `{p0row['assembly_lod2_matches_p0_refl']}`; RMS delta `{p0row['delta_roof_rms_vs_p0_refl_m']} m`; completeness delta `{p0row['delta_roof_completeness_vs_p0_refl']}`; face-ratio delta `{p0row['delta_face_count_ratio_vs_p0_refl']}` |",
            "| post-learning fusion learning/readout/Section5 Roofer/scoring | `0/0/0/0` |",
            "| 30k 학습 1런 처리율 | `NOT_MEASURED`; 30k learning started/completed=`0/0` |",
            f"| 층별 placeholder | {markdown_link(config['inputs']['summary']['path'])}; `{snapshot['summary_rows_n']}`행, `NOT_MEASURED` `{snapshot['summary_not_measured_rows_n']}`행 |",
            "",
            "## 정성 패널",
            "",
        ]
    )
    if panel["status"] == "PRESENT":
        lines.append(
            f"- P0′ pre-learning: {run_link(config, panel['path'])} · {run_link(config, panel['receipt'], 'receipt')} SHA256 `{panel['receipt_sha256']}`"
        )
    else:
        lines.append(
            f"- P0′ pre-learning: `MISSING` — `{panel['path']}` / `{panel['receipt']}`"
        )
    lines.extend(
        [
            "- fusion arm/run panel: `0`",
            "",
            "## 고정 산출물",
            "",
            "| 산출물 | 상태 | 행/파일 |",
            "|---|---|---:|",
            f"| `{Path(output['align_residuals']).name}` | `PRESENT_EXACT_COPY` | `178` |",
            f"| `{Path(config['inputs']['seed_stats']['path']).name}` | `PRESENT` | `1` |",
            f"| `{Path(config['inputs']['p0prime_scores']['path']).name}` | `PRESENT_MEASURED` | `1` |",
            f"| `{Path(output['loss_shares']).name}` | `HEADER_ONLY` | `0` |",
            f"| `{Path(config['inputs']['scores']['path']).name}` | `HEADER_ONLY` | `0` |",
            f"| `{Path(config['inputs']['summary']['path']).name}` | `PLACEHOLDER_NOT_MEASURED` | `12` |",
            f"| `w1_panels/` | `{'P0PRIME_ONLY' if panel['status'] == 'PRESENT' else 'MISSING'}` | `{'1' if panel['status'] == 'PRESENT' else '0'}` |",
            f"| `{Path(output['manifest']).name}` | `ATOMIC_REPLACE_AFTER_REPORT` | — |",
            "",
            "## issues",
            "",
            f"- [issues.md](issues.md) SHA256 `{issues['sha256']}`; headings `{issues['issue_count']}`.",
        ]
    )
    for heading in issues["headings"]:
        lines.append(f"- `{heading}`")
    lines.extend(
        [
            "",
            "## 미완 단계",
            "",
            f"- preprocess: completed `{preprocess['completed_buildings_n']}`, remaining `{targets['population_n'] - preprocess['completed_buildings_n']}`.",
            f"- P0′: completed `{p0['population']['completed_count']}`, remaining `{p0['population']['target_count'] - p0['population']['completed_count']}`.",
            "- P0′ current namespace: `PARTIAL` final manifest published (`manifest_written_last=true`); remaining 177 require a new approved namespace or reopen contract under the locked driver guard.",
            "- smoke arm A r1 30k training: `NOT_STARTED`.",
            "- core arm A r1/r2 training: `NOT_STARTED`.",
            "- arm B 감독 제거 training: `NOT_STARTED`.",
            "- extension training: `NOT_STARTED`.",
            "- fusion pointcloudification/classification/Roofer/scoring: `NOT_STARTED`.",
            "- fusion arm/run panels: `NOT_PRODUCED`.",
            "- 눈금 1–4: `NOT_MEASURED`.",
            "",
        ]
    )
    return "\n".join(lines)


def artifact_record(
    repo: Path,
    path: Path,
    content_state: str,
    *,
    rows: int | None = None,
) -> dict[str, Any]:
    require_regular(path, path.name)
    record: dict[str, Any] = {
        "path": relative(repo, path),
        "exists": True,
        "content_state": content_state,
        "sha256": sha256_file(path),
    }
    if rows is not None:
        record["row_count"] = rows
    return record


def build_manifest(
    repo: Path,
    config: Mapping[str, Any],
    snapshot: Mapping[str, Any],
    git: Mapping[str, Any],
    cutoff: Mapping[str, Any],
    report: Path,
    align: Path,
    loss: Path,
    created_at: str,
) -> dict[str, Any]:
    preprocess = snapshot["preprocess"]
    p0 = snapshot["p0prime"]
    panel = snapshot["panel"]
    fixed = {
        "w1_targets": artifact_record(repo, snapshot["paths"]["targets"], "PRESENT", rows=178),
        "w1_align_residuals": artifact_record(repo, align, "PRESENT_EXACT_COPY", rows=178),
        "w1_seed_stats": artifact_record(repo, snapshot["paths"]["seed_stats"], "PRESENT", rows=1),
        "w1_seed_p0prime_scores": artifact_record(repo, snapshot["paths"]["p0prime_scores"], "PRESENT_MEASURED", rows=1),
        "w1_loss_shares": artifact_record(repo, loss, "HEADER_ONLY", rows=0),
        "w1_scores_building": artifact_record(repo, snapshot["paths"]["scores"], "HEADER_ONLY", rows=0),
        "w1_summary": artifact_record(repo, snapshot["paths"]["summary"], "PLACEHOLDER_NOT_MEASURED", rows=12),
        "partial_report": artifact_record(repo, report, "PRESENT"),
    }
    fixed["w1_panels"] = panel
    return {
        "schema": MANIFEST_SCHEMA,
        "state": "PARTIAL",
        "created_at": created_at,
        "task_id": config["task_id"],
        "run_id": config["run_id"],
        "observation_only": True,
        "interpretation_or_verdict": False,
        "git": dict(git),
        "cutoff": dict(cutoff),
        "supersedes": {
            "path": config["inputs"]["stale_manifest"]["path"],
            "sha256": config["inputs"]["stale_manifest"]["sha256"],
            "schema": snapshot["stale_manifest"]["schema"],
            "run_status": snapshot["stale_manifest"]["run_status"],
            "reason": "legacy_initial_manifest_superseded_by_resume_v2_and_partial_closeout",
        },
        "authority_chain": {
            "r0": {"path": config["inputs"]["r0"]["path"], "sha256": config["inputs"]["r0"]["sha256"], "status": "PASSED"},
            "r1": {"path": config["inputs"]["r1"]["path"], "sha256": config["inputs"]["r1"]["sha256"], "status": "PASSED"},
            "r2": {"path": config["inputs"]["r2"]["path"], "sha256": config["inputs"]["r2"]["sha256"], "status": "PASS"},
        },
        "target_population": snapshot["targets"],
        "r1_verification": {
            "source_sha256": snapshot["r1"]["source_sha256"],
            "derived_sha256": snapshot["r1"]["derived_sha256"],
            "pose_validation": snapshot["r1"]["pose_validation"],
            "diagnostic_reproduction": snapshot["r1"]["diagnostic_reproduction"],
        },
        "r2_registration": {
            "status": snapshot["r2"]["status"],
            "gate_slots": snapshot["r2"]["gate_slots"],
            "qualitative_overlays": snapshot["r2"]["qualitative_overlays"],
        },
        "judgment_scales": grade_rows(),
        "stage_inventory": {
            "preprocess": {"status": preprocess["status"], "completed_n": preprocess["completed_buildings_n"], "target_n": 178},
            "p0prime": {"state": p0["state"], "completed_n": p0["population"]["completed_count"], "target_n": p0["population"]["target_count"], "roofer_completed_n": p0["population"]["assembly_lod2_success_count"], "scoring_completed_n": p0["population"]["completed_count"], "counter_scope": "separate_pre_learning_seed_attribution", "final_manifest_published": True, "remaining_namespace_contract": "new_approved_namespace_or_reopen_contract_required"},
            "training": {"state": "NOT_STARTED", "materialized_n": snapshot["counters"]["training_materializations_n"], "started_n": 0, "completed_n": 0, "failed_n": 0},
            "section5": {"state": "NOT_STARTED", "readout_started_n": 0, "roofer_started_n": 0, "scoring_started_n": 0, "measured_rows_n": 0},
        },
        "postlearning_fusion_counters": snapshot["counters"],
        "training_throughput": {
            "scope": "one_30k_training_run",
            "status": "NOT_MEASURED",
            "started_n": 0,
            "completed_n": 0,
        },
        "fixed_outputs": fixed,
        "issues": snapshot["issues"],
        "incomplete_stages": [
            {"stage": "preprocess", "completed_n": preprocess["completed_buildings_n"], "target_n": 178, "remaining_n": 178 - preprocess["completed_buildings_n"], "state": "PARTIAL"},
            {"stage": "p0prime", "completed_n": p0["population"]["completed_count"], "target_n": 178, "remaining_n": 178 - p0["population"]["completed_count"], "state": "PARTIAL"},
            {"stage": "training", "completed_n": 0, "state": "NOT_STARTED"},
            {"stage": "section5_readout_roofer_scoring", "completed_n": 0, "state": "NOT_STARTED"},
            {"stage": "judgment_scales_1_to_4", "completed_n": 0, "state": "NOT_MEASURED"},
        ],
        "report": {"path": relative(repo, report), "sha256": sha256_file(report)},
        "publication": {
            "alignment_exact_bytes": True,
            "loss_share_header_only_zero_rows": True,
            "report_written_before_manifest": True,
            "manifest_atomic_replace_written_last": True,
            "stage_counters_touched": False,
            "stage_receipts_created": False,
            "issues_md_modified": False,
        },
    }


def check(
    config: Mapping[str, Any], repo: Path = REPO, now: datetime | None = None
) -> dict[str, Any]:
    git = verify_git_contract(config, repo)
    cutoff = verify_cutoff(config, now)
    snapshot = collect_inputs(repo, config)
    return {
        "schema": "jointbuildgs.fusion_w1.partial_closeout_check.v1",
        "state": "READY_FOR_EXPLICIT_PUBLICATION",
        "created_at": utc_now(),
        "git": git,
        "cutoff": cutoff,
        "counters": snapshot["counters"],
        "panel": snapshot["panel"],
        "planned_outputs": config["outputs"],
        "outputs_written_by_check": False,
        "stage_commands_invoked": False,
    }


def acquire_locks(repo: Path, config: Mapping[str, Any]) -> list[Any]:
    paths = [
        repo_path(repo, config["outputs"]["lock"]),
        repo_path(repo, config["counter_contract"]["training_root"]) / "runtime_counters.json.lock",
        repo_path(repo, config["counter_contract"]["readout_root"]) / "driver.lock",
        repo_path(repo, "phases/p2-gsjso/runs/fusion_w1/20260724_fusion_w1/p0prime/driver.lock"),
    ]
    handles: list[Any] = []
    for path in paths:
        path.parent.mkdir(parents=True, exist_ok=True)
        handle = path.open("a+b")
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            handle.close()
            for held in handles:
                held.close()
            raise CloseoutError(f"closeout lock is busy: {path}") from exc
        handles.append(handle)
    return handles


def publish(
    config: Mapping[str, Any], repo: Path = REPO, now: datetime | None = None
) -> dict[str, Any]:
    handles = acquire_locks(repo, config)
    try:
        git = verify_git_contract(config, repo)
        cutoff = verify_cutoff(config, now)
        snapshot = collect_inputs(repo, config)
        align = repo_path(repo, config["outputs"]["align_residuals"])
        source = repo_path(repo, config["inputs"]["alignment_source"]["path"])
        publish_exact_or_accept(align, source.read_bytes(), "w1_align_residuals.csv")
        require_equal(sha256_file(align), sha256_file(source), "alignment copy SHA")
        loss = repo_path(repo, config["outputs"]["loss_shares"])
        loss_payload = empty_csv_bytes(snapshot["loss_share_fields"])
        publish_exact_or_accept(loss, loss_payload, "w1_loss_shares.csv")
        _, loss_rows = read_csv(loss)
        require_equal(len(loss_rows), 0, "loss share rows")

        created_at = utc_now()
        report = repo_path(repo, config["outputs"]["report"])
        atomic_text(report, render_report(config, snapshot, created_at))
        # Re-read the two mutable external snapshots and all zero counters
        # immediately before manifest-last publication.
        require_equal(collect_issue_snapshot(repo, config), snapshot["issues"], "issues snapshot")
        require_equal(collect_panel(repo, config), snapshot["panel"], "panel snapshot")
        require_equal(zero_counter_snapshot(repo, config), snapshot["counters"], "counter snapshot")
        manifest = build_manifest(
            repo, config, snapshot, git, cutoff, report, align, loss, created_at
        )
        manifest_path = repo_path(repo, config["outputs"]["manifest"])
        atomic_json(manifest_path, manifest)
        return {
            "schema": "jointbuildgs.fusion_w1.partial_closeout_publication.v1",
            "state": "PUBLISHED",
            "manifest": relative(repo, manifest_path),
            "manifest_sha256": sha256_file(manifest_path),
            "report": relative(repo, report),
            "report_sha256": sha256_file(report),
            "w1_align_residuals_sha256": sha256_file(align),
            "w1_loss_shares_sha256": sha256_file(loss),
            "stage_commands_invoked": False,
            "stage_counters_touched": False,
        }
    finally:
        for handle in reversed(handles):
            handle.close()


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    result.add_argument("command", choices=("check", "publish"))
    return result


def main(argv: Sequence[str] | None = None) -> int:
    args = parser().parse_args(argv)
    config_path = args.config if args.config.is_absolute() else REPO / args.config
    config = load_config(config_path)
    payload = check(config) if args.command == "check" else publish(config)
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except CloseoutError as exc:
        print(f"FUS-W1 partial closeout contract error: {exc}", file=sys.stderr)
        raise SystemExit(2)
