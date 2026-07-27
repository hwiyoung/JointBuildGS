#!/usr/bin/env python3
"""One-job, no-retraining continuation for the A-prime smoke readout.

The stopped unattended queue and its original readout attempts remain
immutable.  This adapter verifies their SHA-pinned evidence, proves that the
current commit is an allowlisted descendant of the training execution commit,
and materializes one new readout namespace for
DEBY_LOD2_42364609/Aprime/r1/attempt_004.  Downstream geometry and scoring are
delegated to the locked original readout driver.
"""
from __future__ import annotations

import argparse
import copy
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any, Mapping, Sequence


REPO = Path(__file__).resolve().parents[3]
DEFAULT_CONFIG = (
    REPO
    / "phases/p2-gsjso/configs/fusion_w1_aprime_smoke_recovery_20260727.json"
)
CONFIG_SCHEMA = "jointbuildgs.fusion_w1_aprime.smoke_recovery.config.v1"
LOCK_V1_SCHEMA = "jointbuildgs.fusion_w1_aprime.smoke_recovery.lock.v1"
LOCK_V2_SCHEMA = "jointbuildgs.fusion_w1_aprime.smoke_recovery.lock.v2"
MATERIALIZATION_SCHEMA = (
    "jointbuildgs.fusion_w1_aprime.smoke_recovery.materialization.v1"
)
CACHE_SCHEMA = "jointbuildgs.fusion_w1_aprime.smoke_recovery.cache_probe.v1"
COMPLETE_SCHEMA = "jointbuildgs.fusion_w1_aprime.smoke_recovery.complete.v1"
CONTAINER_REPO = Path("/workspace/JointBuildGS")


class SmokeRecoveryError(RuntimeError):
    """The one-job recovery scope, provenance, or evidence drifted."""


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_file(path: Path, block_size: int = 1 << 20) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(block_size), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_json(payload: Any) -> bytes:
    return (
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def load_json(path: Path) -> dict[str, Any]:
    if not path.is_file() or path.is_symlink():
        raise SmokeRecoveryError(f"missing/non-regular JSON: {relative(path)}")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise SmokeRecoveryError(f"JSON root must be an object: {relative(path)}")
    return value


def relative(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(REPO.resolve()))
    except ValueError as exc:
        raise SmokeRecoveryError(f"path escapes repository: {path}") from exc


def repo_path(raw: str) -> Path:
    path = (REPO / raw).resolve()
    try:
        path.relative_to(REPO.resolve())
    except ValueError as exc:
        raise SmokeRecoveryError(f"path escapes repository: {raw}") from exc
    return path


def require_equal(observed: Any, expected: Any, label: str) -> None:
    if observed != expected:
        raise SmokeRecoveryError(
            f"{label} mismatch: observed={observed!r}, expected={expected!r}"
        )


def file_record(path: Path) -> dict[str, Any]:
    if not path.is_file() or path.is_symlink() or path.stat().st_size <= 0:
        raise SmokeRecoveryError(
            f"artifact missing/empty/non-regular: {relative(path)}"
        )
    return {
        "path": relative(path),
        "sha256": sha256_file(path),
        "bytes": int(path.stat().st_size),
    }


def verify_record(record: Mapping[str, Any], label: str) -> Path:
    raw = record.get("path")
    digest = record.get("sha256")
    if not isinstance(raw, str) or not isinstance(digest, str):
        raise SmokeRecoveryError(f"{label} lacks path/SHA256")
    path = repo_path(raw)
    require_equal(sha256_file(path), digest, f"{label} SHA256")
    if "bytes" in record:
        require_equal(path.stat().st_size, int(record["bytes"]), f"{label} bytes")
    return path


def git(*arguments: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    process = subprocess.run(
        [
            "git",
            "-c",
            f"safe.directory={REPO}",
            "-C",
            str(REPO),
            *arguments,
        ],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if check and process.returncode:
        raise SmokeRecoveryError(
            process.stderr.strip()
            or process.stdout.strip()
            or f"git {' '.join(arguments)} failed"
        )
    return process


def load_config(path: Path = DEFAULT_CONFIG) -> dict[str, Any]:
    config = load_json(path)
    require_equal(config.get("schema"), CONFIG_SCHEMA, "recovery config schema")
    require_equal(config.get("branch"), "exp/fusion-w1", "recovery branch")
    require_equal(
        config.get("source_execution_head"),
        "de8852c00c737eced081f2627b49bcedddade652",
        "source execution HEAD",
    )
    scope = config.get("scope") or {}
    require_equal(
        scope,
        {
            "building_id": "DEBY_LOD2_42364609",
            "arm": "Aprime",
            "replicate": "r1",
            "profile": "full",
            "continuation_attempt": 4,
            "new_training_runs_allowed": 0,
            "other_queue_jobs_allowed": 0,
        },
        "recovery scope",
    )
    require_equal(config["containers"].get("time_cutoff"), None, "time cutoff")
    require_equal(config["containers"].get("nonroot"), True, "nonroot")
    require_equal(config["cache_contract"].get("reuse_only"), True, "cache reuse")
    require_equal(
        config["cache_contract"].get("compilation_allowed"),
        False,
        "cache compilation",
    )
    require_equal(config["publication"].get("retraining_forbidden"), True, "retraining")
    require_equal(
        config["publication"].get("scientific_verdict"), None, "scientific verdict"
    )
    return config


def load_base_driver(config: Mapping[str, Any]) -> Any:
    record = config["locked_inputs"]["base_readout_driver"]
    path = verify_record(record, "base readout driver")
    spec = importlib.util.spec_from_file_location("aprime_smoke_recovery_base", path)
    if spec is None or spec.loader is None:
        raise SmokeRecoveryError("cannot import locked base readout driver")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def verify_locked_inputs(config: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    records: dict[str, dict[str, Any]] = {}
    for name, expected in config["locked_inputs"].items():
        path = verify_record(expected, f"locked input {name}")
        records[name] = file_record(path)
    return records


def tree_ledger(root: Path) -> list[dict[str, Any]]:
    if not root.is_dir() or root.is_symlink():
        raise SmokeRecoveryError(f"tree root missing/non-directory: {relative(root)}")
    rows: list[dict[str, Any]] = []
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise SmokeRecoveryError(f"source tree symlink forbidden: {relative(path)}")
        if path.is_file():
            record = file_record(path)
            record["relative_to_root"] = str(path.relative_to(root))
            rows.append(record)
    if not rows:
        raise SmokeRecoveryError(f"source tree is empty: {relative(root)}")
    return rows


def require_scope(
    config: Mapping[str, Any],
    building_id: str,
    arm: str,
    replicate: str,
    attempt: int,
) -> None:
    scope = config["scope"]
    observed = {
        "building_id": building_id,
        "arm": arm,
        "replicate": replicate,
        "continuation_attempt": int(attempt),
    }
    expected = {
        "building_id": scope["building_id"],
        "arm": scope["arm"],
        "replicate": scope["replicate"],
        "continuation_attempt": int(scope["continuation_attempt"]),
    }
    require_equal(observed, expected, "one-job continuation identity")


def recovery_namespace_inventory(config: Mapping[str, Any]) -> dict[str, Any]:
    """Reject any recovery job or attempt outside the one authorized identity."""

    root = repo_path(config["outputs"]["readout_root"])
    scope = config["scope"]
    if not root.exists():
        return {
            "readout_root": relative(root),
            "exists": False,
            "attempt_directories": [],
            "job_complete": False,
            "other_queue_jobs_started": 0,
        }
    if not root.is_dir() or root.is_symlink():
        raise SmokeRecoveryError("recovery readout root is not a real directory")
    allowed_top = {"by_building", "driver.lock", "failures.jsonl"}
    unexpected_top = sorted(path.name for path in root.iterdir() if path.name not in allowed_top)
    if unexpected_top:
        raise SmokeRecoveryError(f"unexpected recovery readout entries: {unexpected_top}")
    for path in root.iterdir():
        if path.is_symlink():
            raise SmokeRecoveryError(f"recovery namespace symlink forbidden: {relative(path)}")

    by_building = root / "by_building"
    if not by_building.exists():
        return {
            "readout_root": relative(root),
            "exists": True,
            "attempt_directories": [],
            "job_complete": False,
            "other_queue_jobs_started": 0,
        }
    expected_building = str(scope["building_id"])
    expected_arm = f"arm_{scope['arm']}"
    expected_run = str(scope["replicate"])
    expected_attempt = f"attempt_{int(scope['continuation_attempt']):03d}"
    levels = (
        (by_building, expected_building, "building"),
        (by_building / expected_building, expected_arm, "arm"),
        (by_building / expected_building / expected_arm, expected_run, "replicate"),
    )
    for parent, expected, label in levels:
        if not parent.exists():
            break
        if not parent.is_dir() or parent.is_symlink():
            raise SmokeRecoveryError(f"recovery {label} parent is not a real directory")
        children = list(parent.iterdir())
        unexpected = sorted(path.name for path in children if path.name != expected)
        if unexpected:
            raise SmokeRecoveryError(f"unauthorized recovery {label} entries: {unexpected}")
        if children and (children[0].is_symlink() or not children[0].is_dir()):
            raise SmokeRecoveryError(f"recovery {label} entry is not a real directory")

    job = by_building / expected_building / expected_arm / expected_run
    if not job.exists():
        return {
            "readout_root": relative(root),
            "exists": True,
            "attempt_directories": [],
            "job_complete": False,
            "other_queue_jobs_started": 0,
        }
    allowed_job = {"attempts", "complete.json"}
    unexpected_job = sorted(path.name for path in job.iterdir() if path.name not in allowed_job)
    if unexpected_job:
        raise SmokeRecoveryError(f"unexpected recovery job entries: {unexpected_job}")
    complete_path = job / "complete.json"
    if complete_path.is_symlink() or (complete_path.exists() and not complete_path.is_file()):
        raise SmokeRecoveryError("recovery complete receipt is not a regular file")
    attempts_root = job / "attempts"
    attempts: list[str] = []
    if attempts_root.exists():
        if not attempts_root.is_dir() or attempts_root.is_symlink():
            raise SmokeRecoveryError("recovery attempts root is not a real directory")
        for path in sorted(attempts_root.iterdir()):
            if path.name != expected_attempt:
                raise SmokeRecoveryError(f"unauthorized recovery attempt: {path.name}")
            if not path.is_dir() or path.is_symlink():
                raise SmokeRecoveryError("authorized attempt is not a real directory")
            for artifact in path.rglob("*"):
                if artifact.is_symlink():
                    raise SmokeRecoveryError(
                        f"recovery attempt symlink forbidden: {relative(artifact)}"
                    )
            attempts.append(path.name)
    return {
        "readout_root": relative(root),
        "exists": True,
        "attempt_directories": attempts,
        "job_complete": complete_path.is_file(),
        "other_queue_jobs_started": 0,
    }


def load_locks(
    config: Mapping[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    v1 = load_json(verify_record(config["locked_inputs"]["recovery_lock_v1"], "lock v1"))
    v2 = load_json(verify_record(config["locked_inputs"]["recovery_lock_v2"], "lock v2"))
    require_equal(v1.get("schema"), LOCK_V1_SCHEMA, "lock v1 schema")
    require_equal(v2.get("schema"), LOCK_V2_SCHEMA, "lock v2 schema")
    require_equal(v1.get("scope"), config["scope"], "lock v1 scope")
    require_equal(v2.get("scope"), config["scope"], "lock v2 scope")
    require_equal(
        v2.get("supersedes_layout_only"),
        config["locked_inputs"]["recovery_lock_v1"],
        "lock v2/v1 binding",
    )
    for key in ("source_execution_head", "source_terminal_state", "source_failure_signature"):
        require_equal(v1.get(key), config[key], f"lock v1 {key}")
        require_equal(v2.get(key), config[key], f"lock v2 {key}")
    require_equal(v1.get("retraining_allowed"), False, "lock v1 retraining")
    require_equal(v2.get("retraining_allowed"), False, "lock v2 retraining")
    return v1, v2


def verify_git_provenance(
    config: Mapping[str, Any], v2: Mapping[str, Any]
) -> dict[str, Any]:
    branch = git("branch", "--show-current").stdout.strip()
    head = git("rev-parse", "HEAD").stdout.strip()
    require_equal(branch, config["branch"], "runtime branch")
    source = str(config["source_execution_head"])
    ancestor = git("merge-base", "--is-ancestor", source, head, check=False)
    if ancestor.returncode != 0:
        raise SmokeRecoveryError(f"source execution HEAD is not an ancestor: {source}..{head}")
    allowed = set(v2["allowed_descendant_paths"])
    final_paths = {
        value.strip()
        for value in git("diff", "--name-only", f"{source}..{head}").stdout.splitlines()
        if value.strip()
    }
    history_paths = {
        value.strip()
        for value in git(
            "log", "--format=", "--name-only", f"{source}..{head}"
        ).stdout.splitlines()
        if value.strip()
    }
    for label, paths in (("final", final_paths), ("history", history_paths)):
        unexpected = sorted(paths - allowed)
        if unexpected:
            raise SmokeRecoveryError(
                f"nonallowlisted {label} descendant paths: {unexpected}"
            )
    implementation: list[dict[str, Any]] = []
    for logical in config["implementation_files"]:
        if git("ls-files", "--error-unmatch", logical, check=False).returncode:
            raise SmokeRecoveryError(f"implementation is not tracked: {logical}")
        head_blob = git("rev-parse", f"{head}:{logical}").stdout.strip()
        worktree_blob = git("hash-object", "--", logical).stdout.strip()
        require_equal(worktree_blob, head_blob, f"implementation worktree {logical}")
        implementation.append({
            **file_record(repo_path(logical)),
            "git_blob": worktree_blob,
            "worktree_matches_head": True,
        })
    return {
        "branch": branch,
        "head": head,
        "source_execution_head": source,
        "source_is_ancestor": True,
        "final_descendant_paths": sorted(final_paths),
        "history_descendant_paths": sorted(history_paths),
        "all_descendant_paths_allowlisted": True,
        "implementation_files": implementation,
    }


def verify_source_evidence(
    config: Mapping[str, Any], v1: Mapping[str, Any]
) -> dict[str, Any]:
    records = {
        name: file_record(verify_record(record, f"source record {name}"))
        for name, record in v1["source_records"].items()
    }
    queue_stop = load_json(repo_path(records["queue_stage_stop"]["path"]))
    queue_complete = load_json(repo_path(records["queue_complete"]["path"]))
    require_equal(queue_stop.get("state"), config["source_terminal_state"], "stage stop")
    require_equal(queue_complete.get("state"), config["source_terminal_state"], "queue complete")
    for number in range(1, 4):
        failure = load_json(repo_path(records[f"attempt_{number:03d}_failure"]["path"]))
        require_equal(failure.get("attempt"), number, f"attempt {number} identity")
        require_equal(
            failure.get("error_signature"),
            config["source_failure_signature"],
            f"attempt {number} signature",
        )
        tsdf = load_json(repo_path(records[f"attempt_{number:03d}_tsdf_failure"]["path"]))
        require_equal(tsdf.get("status"), "FAILED", f"TSDF attempt {number} status")
        require_equal(tsdf.get("error_type"), "PermissionError", f"TSDF attempt {number} type")
        require_equal(
            tsdf.get("message"),
            "[Errno 13] Permission denied: '/.cache'",
            f"TSDF attempt {number} message",
        )
    rehydration = load_json(repo_path(records["training_rehydration_receipt"]["path"]))
    require_equal(
        rehydration.get("state"), "REHYDRATED_VALID_COMPLETION", "training recovery"
    )
    require_equal(rehydration.get("producer_receipts_rewritten"), False, "producer rewrite")
    require_equal(
        rehydration.get("execution_head"),
        config["source_execution_head"],
        "rehydration execution HEAD",
    )
    training_root = repo_path(str(rehydration["destination_training_root"]))
    training_tree = tree_ledger(training_root)
    expected_tree = [
        {
            "path": relative(training_root / str(row["relative_to_root"])),
            "sha256": row["sha256"],
            "bytes": int(row["bytes"]),
            "relative_to_root": row["relative_to_root"],
        }
        for row in rehydration["destination_artifacts"]
    ]
    require_equal(training_tree, expected_tree, "rehydrated training tree")
    original_attempt_root = repo_path(
        "phases/p2-gsjso/runs/20260726_fusion_w1_aprime/readout/by_building/"
        "DEBY_LOD2_42364609/arm_Aprime/r1/attempts"
    )
    attempt_trees = {
        f"attempt_{number:03d}": tree_ledger(original_attempt_root / f"attempt_{number:03d}")
        for number in range(1, 4)
    }
    return {
        "source_records": records,
        "training_root": relative(training_root),
        "training_tree": training_tree,
        "original_attempt_trees": attempt_trees,
        "source_queue_state": config["source_terminal_state"],
        "source_failure_signature": config["source_failure_signature"],
    }


def verify_contract(config: Mapping[str, Any]) -> dict[str, Any]:
    locked = verify_locked_inputs(config)
    v1, v2 = load_locks(config)
    provenance = verify_git_provenance(config, v2)
    sources = verify_source_evidence(config, v1)
    return {
        "locked_inputs": locked,
        "lock_v1": v1,
        "lock_v2": v2,
        "provenance": provenance,
        "sources": sources,
    }


def derived_readout_config(
    config: Mapping[str, Any], contract: Mapping[str, Any]
) -> dict[str, Any]:
    base = load_base_driver(config)
    base_path = verify_record(
        config["locked_inputs"]["base_readout_config"], "base readout config"
    )
    derived = copy.deepcopy(base.load_config(base_path))
    outputs = config["outputs"]
    derived["task_id"] = config["task_id"]
    derived["run_id"] = config["run_id"]
    derived["role"] = "one-job post-terminal smoke readout continuation; no retraining"
    derived["implementation_files"] = list(config["implementation_files"])
    derived["identity_contract"]["expected_queue_jobs"] = 1
    derived["retry_contract"]["attempt_number_min"] = 4
    derived["retry_contract"]["attempt_number_max"] = 4
    derived["locked_inputs"]["recovery_lock_v1"] = dict(
        config["locked_inputs"]["recovery_lock_v1"]
    )
    derived["locked_inputs"]["recovery_lock_v2"] = dict(
        config["locked_inputs"]["recovery_lock_v2"]
    )
    derived["outputs"] = {
        "root": outputs["readout_root"],
        "job_template": outputs["readout_job_template"],
        "failures_jsonl": outputs["failure_log"],
        "driver_lock": outputs["driver_lock"],
        "issues": outputs["issues"],
        "runtime_environment": outputs["shared_t2_runtime_environment"],
    }
    derived["containers"]["time_cutoff"] = None
    derived["containers"]["serial_jobs"] = True
    derived["containers"]["concurrent_with_training"] = False
    derived["containers"]["concurrent_with_other_readout"] = False
    derived["publication"].update({
        "source_queue_immutable": True,
        "source_failures_immutable": True,
        "single_use_continuation": True,
        "retraining_forbidden": True,
        "interpretation_or_verdict": None,
    })
    derived["continuation_contract"] = {
        "task_id": config["task_id"],
        "scope": dict(config["scope"]),
        "source_execution_head": config["source_execution_head"],
        "source_terminal_state": config["source_terminal_state"],
        "source_failure_signature": config["source_failure_signature"],
        "recovery_lock_v1": contract["locked_inputs"]["recovery_lock_v1"],
        "recovery_lock_v2": contract["locked_inputs"]["recovery_lock_v2"],
        "new_training_runs_allowed": 0,
        "other_queue_jobs_allowed": 0,
        "scientific_verdict": None,
    }
    return derived


def prepare(config: Mapping[str, Any]) -> dict[str, Any]:
    base = load_base_driver(config)
    recovery_namespace_inventory(config)
    contract = verify_contract(config)
    derived = derived_readout_config(config, contract)
    method = base.verify_git_runtime(derived)
    output = repo_path(config["outputs"]["derived_readout_config"])
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists() or output.is_symlink():
        require_equal(load_json(output), derived, "existing derived readout config")
    else:
        base.exclusive_json(output, derived)
    base.load_config(output)
    materialization_path = repo_path(config["outputs"]["materialization_receipt"])
    payload = {
        "schema": MATERIALIZATION_SCHEMA,
        "state": "PREPARED",
        "created_at": now_iso(),
        "run_id": config["run_id"],
        "task_id": config["task_id"],
        "scope": dict(config["scope"]),
        "git_lock": method,
        "provenance": contract["provenance"],
        "locked_inputs": contract["locked_inputs"],
        "source_records": contract["sources"]["source_records"],
        "source_training_tree": contract["sources"]["training_tree"],
        "source_attempt_trees": contract["sources"]["original_attempt_trees"],
        "derived_readout_config": file_record(output),
        "new_training_runs_started": 0,
        "other_queue_jobs_started": 0,
        "source_queue_rewritten": False,
        "scientific_verdict": None,
    }
    if materialization_path.exists() or materialization_path.is_symlink():
        existing = load_json(materialization_path)
        for key in (
            "schema", "state", "run_id", "task_id", "scope", "git_lock",
            "provenance", "locked_inputs", "source_records",
            "source_training_tree", "source_attempt_trees",
            "derived_readout_config", "new_training_runs_started",
            "other_queue_jobs_started", "source_queue_rewritten",
            "scientific_verdict",
        ):
            require_equal(existing.get(key), payload.get(key), f"materialization {key}")
        payload = existing
    else:
        base.exclusive_json(materialization_path, payload)
    return payload


def source_training_binding(
    config: Mapping[str, Any], contract: Mapping[str, Any]
) -> dict[str, Any]:
    base = load_base_driver(config)
    records = contract["sources"]["source_records"]
    completed_path = verify_record(records["training_completed"], "training completed")
    completed = load_json(completed_path)
    scope = config["scope"]
    for key, expected in (
        ("building_id", scope["building_id"]),
        ("arm", scope["arm"]),
        ("replicate", scope["replicate"]),
        ("profile", scope["profile"]),
        ("status", "COMPLETED"),
        ("return_code", 0),
    ):
        require_equal(completed.get(key), expected, f"training completion {key}")
    completion = completed.get("training_completion") or {}
    require_equal(completion.get("completed_optimizer_updates"), 30000, "optimizer updates")
    final_expected = records["training_final_checkpoint"]
    final_observed = completion.get("final_checkpoint") or {}
    require_equal(
        {key: final_observed.get(key) for key in ("path", "sha256")},
        {key: final_expected.get(key) for key in ("path", "sha256")},
        "final checkpoint binding",
    )
    checkpoint = verify_record(final_expected, "training final checkpoint")
    materialization_record = completed.get("materialization") or {}
    materialization_path = verify_record(materialization_record, "training materialization")
    materialization = load_json(materialization_path)
    require_equal(
        materialization.get("git", {}).get("head"),
        config["source_execution_head"],
        "training materialization execution HEAD",
    )
    base_config = load_json(
        verify_record(config["locked_inputs"]["base_readout_config"], "base config")
    )
    training_config_record = base_config["locked_inputs"]["training_config"]
    training_driver_record = base_config["locked_inputs"]["training_driver"]
    training_config_path = verify_record(training_config_record, "training config")
    training_driver_path = verify_record(training_driver_record, "training driver")
    require_equal(
        materialization.get("driver_config_sha256"),
        training_config_record["sha256"],
        "materialization training config",
    )
    resolved = repo_path(str(materialization["resolved_config"]))
    require_equal(
        sha256_file(resolved),
        materialization["resolved_config_sha256"],
        "resolved training config",
    )
    preprocess = materialization.get("preprocess") or {}
    preprocess_path = repo_path(str(preprocess["manifest"]))
    require_equal(
        sha256_file(preprocess_path), preprocess["manifest_sha256"], "preprocess manifest"
    )
    data_root = repo_path(str(preprocess["data_root"]))
    if not data_root.is_dir() or data_root.is_symlink():
        raise SmokeRecoveryError("preprocess data root is missing/non-directory")
    return {
        "identity": {
            "building_id": scope["building_id"],
            "arm": scope["arm"],
            "replicate": scope["replicate"],
            "profile": scope["profile"],
        },
        "current_head": contract["provenance"]["head"],
        "source_execution_head": config["source_execution_head"],
        "training_config": file_record(training_config_path),
        "training_driver": file_record(training_driver_path),
        "materialization": file_record(materialization_path),
        "completed": file_record(completed_path),
        "checkpoint": file_record(checkpoint),
        "resolved_config": file_record(resolved),
        "preprocess_manifest": file_record(preprocess_path),
        "data_root": relative(data_root),
        "preprocess_full_snapshot_sha256": preprocess["full_snapshot_sha256"],
        "completed_receipt_payload_sha256": hashlib.sha256(
            canonical_json(completed)
        ).hexdigest(),
        "source_rehydration_receipt": records["training_rehydration_receipt"],
        "retraining_performed": False,
    }


def check(config: Mapping[str, Any]) -> dict[str, Any]:
    base = load_base_driver(config)
    namespace = recovery_namespace_inventory(config)
    contract = verify_contract(config)
    derived = derived_readout_config(config, contract)
    method = base.verify_git_runtime(derived)
    training = source_training_binding(config, contract)
    scope = config["scope"]
    require_scope(
        config,
        scope["building_id"],
        scope["arm"],
        scope["replicate"],
        int(scope["continuation_attempt"]),
    )
    job = repo_path(
        config["outputs"]["readout_job_template"].format(
            building_id=scope["building_id"], arm=scope["arm"], run=scope["replicate"]
        )
    )
    attempts = []
    attempts_root = job / "attempts"
    if attempts_root.is_dir():
        attempts = sorted(path.name for path in attempts_root.iterdir())
    complete = (job / "complete.json").is_file()
    return {
        "schema": "jointbuildgs.fusion_w1_aprime.smoke_recovery.check.v1",
        "state": "COMPLETE" if complete else ("STARTED" if attempts else "READY"),
        "created_at": now_iso(),
        "scope": dict(scope),
        "git_lock": method,
        "provenance": contract["provenance"],
        "training": training,
        "attempt_directories": attempts,
        "recovery_namespace": namespace,
        "complete": complete,
        "new_training_runs_started": 0,
        "other_queue_jobs_started": 0,
        "scientific_verdict": None,
    }


def begin(config: Mapping[str, Any]) -> dict[str, Any]:
    base = load_base_driver(config)
    prepare(config)
    namespace = recovery_namespace_inventory(config)
    cache_path = repo_path(config["outputs"]["cache_probe_receipt"])
    cache = load_json(cache_path)
    contract = verify_contract(config)
    validate_cache_receipt(config, cache, contract)
    derived_path = repo_path(config["outputs"]["derived_readout_config"])
    derived = base.load_config(derived_path)
    scope = config["scope"]
    attempt_number = int(scope["continuation_attempt"])
    require_scope(
        config,
        scope["building_id"],
        scope["arm"],
        scope["replicate"],
        attempt_number,
    )
    job = base.job_dir(derived, scope["building_id"], scope["arm"], scope["replicate"])
    if (job / "complete.json").exists() or (job / "complete.json").is_symlink():
        raise SmokeRecoveryError("recovery job already has complete.json")
    attempts_root = job / "attempts"
    existing = sorted(path.name for path in attempts_root.iterdir()) if attempts_root.is_dir() else []
    if existing:
        raise SmokeRecoveryError(f"single-use recovery already has attempts: {existing}")
    method = base.verify_git_runtime(derived)
    locked = base.verify_locked_inputs(derived)
    training = source_training_binding(config, contract)
    attempt = base.attempt_dir(
        derived, scope["building_id"], scope["arm"], scope["replicate"], attempt_number
    )
    attempt.mkdir(parents=True, exist_ok=False)
    payload = {
        "schema": base.ATTEMPT_SCHEMA,
        "state": "STARTED",
        "created_at": now_iso(),
        "run_id": config["run_id"],
        "task_id": config["task_id"],
        "attempt": attempt_number,
        "attempt_key": (
            f"{scope['building_id']}/arm_{scope['arm']}/"
            f"{scope['replicate']}/attempt_{attempt_number:03d}"
        ),
        "identity": {
            "building_id": scope["building_id"],
            "arm": scope["arm"],
            "replicate": scope["replicate"],
            "profile": scope["profile"],
        },
        "target": dict(base.target_row(derived, scope["building_id"])),
        "git_lock": method,
        "locked_inputs": locked,
        "training": training,
        "paths": {
            "attempt": relative(attempt),
            "tsdf": relative(attempt / "tsdf"),
            "primary": relative(attempt / "primary"),
            "legacy_alpha": relative(attempt / "legacy_alpha"),
        },
        "continuation": {
            "recovery_lock_v1": contract["locked_inputs"]["recovery_lock_v1"],
            "recovery_lock_v2": contract["locked_inputs"]["recovery_lock_v2"],
            "materialization": file_record(
                repo_path(config["outputs"]["materialization_receipt"])
            ),
            "cache_probe": file_record(cache_path),
            "source_terminal_state": config["source_terminal_state"],
            "source_failure_signature": config["source_failure_signature"],
            "source_attempts_preserved": [1, 2, 3],
            "source_queue_rewritten": False,
            "retraining_performed": False,
            "other_queue_jobs_started": 0,
            "recovery_namespace_before_begin": namespace,
        },
        "publication": {
            "append_only_attempt": True,
            "single_use_post_terminal_continuation": True,
            "external_stage_started": False,
            "scientific_verdict": None,
        },
    }
    base.exclusive_json(attempt / "attempt.json", payload)
    return payload


def cache_environment(config: Mapping[str, Any]) -> dict[str, str]:
    runtime_rel = str(config["outputs"]["shared_t2_runtime_environment"])
    return {
        "HOME": str(CONTAINER_REPO / runtime_rel / "home"),
        "XDG_CACHE_HOME": str(CONTAINER_REPO / runtime_rel / "xdg_cache"),
        "TORCH_EXTENSIONS_DIR": str(
            CONTAINER_REPO / runtime_rel / "torch_extensions"
        ),
    }


def validate_cache_receipt(
    config: Mapping[str, Any],
    payload: Mapping[str, Any],
    contract: Mapping[str, Any],
) -> None:
    expected_extension = config["cache_contract"]["preexisting_gsplat_extension"]
    expected_module = str(CONTAINER_REPO / str(expected_extension["path"]))
    checks = (
        (payload.get("schema"), CACHE_SCHEMA, "cache receipt schema"),
        (payload.get("state"), "PASSED", "cache receipt state"),
        (payload.get("run_id"), config["run_id"], "cache receipt run"),
        (payload.get("task_id"), config["task_id"], "cache receipt task"),
        (payload.get("scope"), config["scope"], "cache receipt scope"),
        (
            payload.get("git_head"),
            contract["provenance"]["head"],
            "cache receipt HEAD",
        ),
        (payload.get("nonroot"), True, "cache receipt nonroot"),
        (payload.get("environment"), cache_environment(config), "cache environment"),
        (
            payload.get("max_jobs"),
            int(config["containers"]["max_compile_jobs"]),
            "cache MAX_JOBS",
        ),
        (payload.get("cuda_available"), True, "cache CUDA"),
        (payload.get("gsplat_extension"), expected_module, "cache module path"),
        (
            payload.get("preexisting_extension_before"),
            expected_extension,
            "cache extension before",
        ),
        (
            payload.get("preexisting_extension_after"),
            expected_extension,
            "cache extension after",
        ),
        (
            payload.get("cache_tree_unchanged"),
            True,
            "cache tree unchanged",
        ),
        (
            payload.get("loaded_from_shared_t2_cache"),
            True,
            "cache load source",
        ),
        (
            payload.get("new_training_runs_started"),
            0,
            "cache training count",
        ),
        (payload.get("scientific_verdict"), None, "cache verdict"),
    )
    for observed, expected, label in checks:
        require_equal(observed, expected, label)
    require_equal(payload.get("cache_tree_before"), payload.get("cache_tree_after"), "cache tree")
    if int(payload.get("uid", 0)) == 0:
        raise SmokeRecoveryError("cache receipt records root execution")
    writable = payload.get("writable") or {}
    require_equal(writable, {name: True for name in cache_environment(config)}, "cache writes")


def cache_probe(config: Mapping[str, Any]) -> dict[str, Any]:
    base = load_base_driver(config)
    contract = verify_contract(config)
    receipt_path = repo_path(config["outputs"]["cache_probe_receipt"])
    expected = cache_environment(config)
    if os.geteuid() == 0:
        raise SmokeRecoveryError("cache probe must run as non-root")
    writes = {}
    for name, expected_path in expected.items():
        require_equal(os.environ.get(name), expected_path, f"cache environment {name}")
        path = Path(expected_path)
        if not path.is_dir() or path.is_symlink():
            raise SmokeRecoveryError(f"cache path missing/non-directory: {name}={path}")
        probe = path / f".smoke_recovery_probe_{os.getpid()}"
        probe.write_text("writable\n", encoding="utf-8")
        probe.unlink()
        writes[name] = True
    require_equal(
        os.environ.get("MAX_JOBS"),
        str(config["containers"]["max_compile_jobs"]),
        "MAX_JOBS",
    )
    extension_expected = dict(
        config["cache_contract"]["preexisting_gsplat_extension"]
    )
    extension_path = verify_record(extension_expected, "preexisting gsplat extension")
    cache_module_root = extension_path.parent
    cache_tree_before = tree_ledger(cache_module_root)
    import torch
    from gsplat.cuda._backend import _C

    if not torch.cuda.is_available():
        raise SmokeRecoveryError("CUDA is unavailable in cache probe")
    module_path = Path(str(_C.__file__)).resolve()
    require_equal(module_path, extension_path.resolve(), "loaded gsplat extension")
    extension_after = file_record(extension_path)
    require_equal(extension_after, extension_expected, "post-load gsplat extension")
    cache_tree_after = tree_ledger(cache_module_root)
    require_equal(cache_tree_after, cache_tree_before, "post-load cache tree")
    payload = {
        "schema": CACHE_SCHEMA,
        "state": "PASSED",
        "created_at": now_iso(),
        "run_id": config["run_id"],
        "task_id": config["task_id"],
        "scope": dict(config["scope"]),
        "git_head": contract["provenance"]["head"],
        "uid": os.geteuid(),
        "nonroot": True,
        "environment": expected,
        "writable": writes,
        "max_jobs": int(os.environ["MAX_JOBS"]),
        "cuda_available": True,
        "cuda_device": torch.cuda.get_device_name(torch.cuda.current_device()),
        "gsplat_extension": str(module_path),
        "preexisting_extension_before": extension_expected,
        "preexisting_extension_after": extension_after,
        "cache_tree_before": cache_tree_before,
        "cache_tree_after": cache_tree_after,
        "cache_tree_unchanged": True,
        "loaded_from_shared_t2_cache": True,
        "new_training_runs_started": 0,
        "scientific_verdict": None,
    }
    if receipt_path.exists() or receipt_path.is_symlink():
        existing = load_json(receipt_path)
        for key in (
            "schema", "state", "run_id", "task_id", "scope", "git_head",
            "uid", "nonroot", "environment", "writable", "max_jobs",
            "cuda_available", "cuda_device", "gsplat_extension",
            "preexisting_extension_before", "preexisting_extension_after",
            "cache_tree_before", "cache_tree_after", "cache_tree_unchanged",
            "loaded_from_shared_t2_cache",
            "new_training_runs_started", "scientific_verdict",
        ):
            require_equal(existing.get(key), payload.get(key), f"cache receipt {key}")
        payload = existing
    else:
        receipt_path.parent.mkdir(parents=True, exist_ok=True)
        base.exclusive_json(receipt_path, payload)
    validate_cache_receipt(config, payload, contract)
    return payload


def source_snapshots_from_materialization(
    config: Mapping[str, Any]
) -> tuple[list[dict[str, Any]], dict[str, list[dict[str, Any]]]]:
    materialization = load_json(repo_path(config["outputs"]["materialization_receipt"]))
    require_equal(materialization.get("schema"), MATERIALIZATION_SCHEMA, "materialization schema")
    training_root = repo_path(
        "phases/p2-gsjso/runs/20260726_fusion_w1_aprime/training/by_building/"
        "DEBY_LOD2_42364609/arm_Aprime/r1"
    )
    training_tree = tree_ledger(training_root)
    require_equal(
        training_tree,
        materialization["source_training_tree"],
        "post-readout training tree",
    )
    original_attempt_root = repo_path(
        "phases/p2-gsjso/runs/20260726_fusion_w1_aprime/readout/by_building/"
        "DEBY_LOD2_42364609/arm_Aprime/r1/attempts"
    )
    attempt_trees = {
        f"attempt_{number:03d}": tree_ledger(original_attempt_root / f"attempt_{number:03d}")
        for number in range(1, 4)
    }
    require_equal(
        attempt_trees,
        materialization["source_attempt_trees"],
        "post-readout source attempt trees",
    )
    return training_tree, attempt_trees


def publish(config: Mapping[str, Any]) -> dict[str, Any]:
    base = load_base_driver(config)
    namespace = recovery_namespace_inventory(config)
    contract = verify_contract(config)
    source_snapshots_from_materialization(config)
    derived_path = repo_path(config["outputs"]["derived_readout_config"])
    derived = base.load_config(derived_path)
    scope = config["scope"]
    job = base.job_dir(derived, scope["building_id"], scope["arm"], scope["replicate"])
    attempts_root = job / "attempts"
    attempts = sorted(path.name for path in attempts_root.iterdir())
    require_equal(attempts, ["attempt_004"], "single-use attempt namespace")
    job_complete_path = job / "complete.json"
    job_complete = load_json(job_complete_path)
    require_equal(job_complete.get("schema"), base.COMPLETE_SCHEMA, "job complete schema")
    require_equal(job_complete.get("state"), "COMPLETE", "job complete state")
    require_equal(job_complete.get("attempt"), 4, "successful continuation attempt")
    require_equal(
        job_complete.get("identity"),
        {
            "building_id": scope["building_id"],
            "arm": scope["arm"],
            "replicate": scope["replicate"],
            "profile": scope["profile"],
        },
        "job complete identity",
    )
    for record in job_complete.get("artifact_ledger") or []:
        base.verify_record(record, "readout artifact ledger")
    payload = {
        "schema": COMPLETE_SCHEMA,
        "state": "COMPLETE",
        "created_at": now_iso(),
        "run_id": config["run_id"],
        "task_id": config["task_id"],
        "scope": dict(scope),
        "git_head": contract["provenance"]["head"],
        "source_execution_head": config["source_execution_head"],
        "source_queue_state": config["source_terminal_state"],
        "source_queue_rewritten": False,
        "source_attempts_001_to_003_preserved": True,
        "source_training_tree_preserved": True,
        "new_training_runs_started": 0,
        "other_queue_jobs_started": 0,
        "recovery_namespace": namespace,
        "successful_continuation_attempt": 4,
        "materialization": file_record(
            repo_path(config["outputs"]["materialization_receipt"])
        ),
        "cache_probe": file_record(repo_path(config["outputs"]["cache_probe_receipt"])),
        "derived_readout_config": file_record(derived_path),
        "readout_job_complete": file_record(job_complete_path),
        "primary": job_complete["primary"],
        "legacy_alpha": job_complete["legacy_alpha"],
        "artifact_count": job_complete["artifact_count"],
        "complete_receipt_written_last": True,
        "scientific_verdict": None,
    }
    complete_path = repo_path(config["outputs"]["complete_receipt"])
    if complete_path.exists() or complete_path.is_symlink():
        existing = load_json(complete_path)
        for key in payload:
            if key != "created_at":
                require_equal(existing.get(key), payload.get(key), f"recovery complete {key}")
        payload = existing
    else:
        base.exclusive_json(complete_path, payload)
    return payload


def verify_complete(config: Mapping[str, Any]) -> dict[str, Any]:
    namespace = recovery_namespace_inventory(config)
    contract = verify_contract(config)
    source_snapshots_from_materialization(config)
    complete_path = repo_path(config["outputs"]["complete_receipt"])
    payload = load_json(complete_path)
    require_equal(payload.get("schema"), COMPLETE_SCHEMA, "complete schema")
    require_equal(payload.get("state"), "COMPLETE", "complete state")
    require_equal(payload.get("scope"), config["scope"], "complete scope")
    require_equal(payload.get("source_queue_rewritten"), False, "queue rewrite")
    require_equal(
        payload.get("source_attempts_001_to_003_preserved"),
        True,
        "source attempts preserved",
    )
    require_equal(
        payload.get("source_training_tree_preserved"),
        True,
        "source training preserved",
    )
    require_equal(payload.get("new_training_runs_started"), 0, "new training runs")
    require_equal(payload.get("other_queue_jobs_started"), 0, "other queue jobs")
    require_equal(payload.get("successful_continuation_attempt"), 4, "attempt")
    require_equal(payload.get("recovery_namespace"), namespace, "recovery namespace")
    require_equal(payload.get("complete_receipt_written_last"), True, "receipt ordering")
    require_equal(payload.get("scientific_verdict"), None, "complete verdict")
    for key in (
        "materialization", "cache_probe", "derived_readout_config", "readout_job_complete"
    ):
        verify_record(payload[key], f"complete {key}")
    cache = load_json(repo_path(payload["cache_probe"]["path"]))
    validate_cache_receipt(config, cache, contract)
    job_complete = load_json(repo_path(payload["readout_job_complete"]["path"]))
    require_equal(job_complete.get("state"), "COMPLETE", "readout complete state")
    require_equal(job_complete.get("attempt"), 4, "readout complete attempt")
    require_equal(payload.get("primary"), job_complete.get("primary"), "primary payload")
    require_equal(
        payload.get("legacy_alpha"), job_complete.get("legacy_alpha"), "legacy payload"
    )
    require_equal(payload.get("artifact_count"), job_complete.get("artifact_count"), "artifact count")
    return payload


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser()
    result.add_argument("--config", default=str(DEFAULT_CONFIG))
    result.add_argument(
        "command",
        choices=("check", "prepare", "begin", "cache-probe", "publish", "verify"),
    )
    return result


def print_json(payload: Any) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), flush=True)


def main(argv: Sequence[str] | None = None) -> int:
    args = parser().parse_args(argv)
    config_path = Path(args.config)
    if not config_path.is_absolute():
        config_path = repo_path(str(config_path))
    config = load_config(config_path)
    actions = {
        "check": check,
        "prepare": prepare,
        "begin": begin,
        "cache-probe": cache_probe,
        "publish": publish,
        "verify": verify_complete,
    }
    print_json(actions[args.command](config))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"[FAILED] {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
        raise
