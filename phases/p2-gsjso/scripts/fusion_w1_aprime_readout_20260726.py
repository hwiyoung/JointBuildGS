#!/usr/bin/env python3
"""Transactional per-job readout for Fusion-W1 arm A-prime.

The preregistered path consumes the completed A-prime/B checkpoint through the
locked TSDF + Marching Cubes implementation, writes a class-6 surface LAS,
concatenates the separately published original ALS class-2 ground rows, and
reuses the locked T3 Roofer/CityJSON/val3dity/scoring engine.  A historical W1
alpha-point extraction and SMRF/footprint classification path is emitted in
parallel as comparison-only evidence.  It never substitutes for the primary
path and is explicitly ineligible for the preregistered gauges.

Every attempt is append-only.  A job-level ``complete.json`` is written last
only after both paths have frozen Roofer output, scored it, and published a
complete artifact hash ledger.  This module records measurements and no
scientific interpretation or verdict.
"""
from __future__ import annotations

import argparse
import copy
import csv
from datetime import datetime, timezone
import fcntl
import hashlib
import importlib.util
import io
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import traceback
from typing import Any, Mapping, Sequence

import numpy as np


REPO = Path(__file__).resolve().parents[3]
DEFAULT_CONFIG = (
    REPO / "phases/p2-gsjso/configs/fusion_w1_aprime_readout_20260726.json"
)
CONFIG_SCHEMA = "jointbuildgs.fusion_w1_aprime.readout.config.v1"
ATTEMPT_SCHEMA = "jointbuildgs.fusion_w1_aprime.readout.attempt.v1"
FAILURE_SCHEMA = "jointbuildgs.fusion_w1_aprime.readout.failure.v1"
SCORE_SCHEMA = "jointbuildgs.fusion_w1_aprime.readout.score.v1"
COMPLETE_SCHEMA = "jointbuildgs.fusion_w1_aprime.readout.complete.v1"
PRIMARY_PREP_SCHEMA = "jointbuildgs.fusion_w1_aprime.readout.primary_prepare.v1"
ALPHA_EXTRACT_SCHEMA = "jointbuildgs.fusion_w1_aprime.readout.alpha_extract.v1"
ALPHA_CLASSIFY_SCHEMA = "jointbuildgs.fusion_w1_aprime.readout.alpha_classify.v1"
ALPHA_NONASSEMBLY_REASONS = (
    "too_few_points_before_classification",
    "required_class_missing_after_SMRF_overlay",
    "zero_class6_inside_footprint_after_SMRF_overlay",
)
ARMS = ("Aprime", "B")
RUNS = ("r1", "r2")
MODES = ("primary", "legacy_alpha")
CONTAINER_REPO = Path("/workspace/JointBuildGS")


class AprimeReadoutError(RuntimeError):
    """A readout method, identity, input, stage, or publication drifted."""


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_file(path: Path, block_size: int = 1 << 20) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(block_size), b""):
            digest.update(block)
    return digest.hexdigest()


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


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


def repo_path(value: str | Path) -> Path:
    raw = Path(value)
    if raw.is_absolute():
        try:
            raw = raw.relative_to(CONTAINER_REPO)
        except ValueError as exc:
            raise AprimeReadoutError(f"absolute path outside repository: {raw}") from exc
    result = (REPO / raw).resolve()
    try:
        result.relative_to(REPO.resolve())
    except ValueError as exc:
        raise AprimeReadoutError(f"path escapes repository: {raw}") from exc
    return result


def relative(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(REPO.resolve()))
    except ValueError as exc:
        raise AprimeReadoutError(f"path outside repository: {path}") from exc


def load_json(path: Path) -> dict[str, Any]:
    if not path.is_file() or path.is_symlink():
        raise AprimeReadoutError(f"missing/non-regular JSON: {relative(path)}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AprimeReadoutError(f"cannot load JSON {relative(path)}: {exc}") from exc
    if not isinstance(payload, dict):
        raise AprimeReadoutError(f"JSON root is not an object: {relative(path)}")
    return payload


def atomic_bytes(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    with temporary.open("xb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)
    descriptor = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def atomic_json(path: Path, payload: Mapping[str, Any]) -> None:
    atomic_bytes(path, canonical_json(dict(payload)))


def exclusive_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as stream:
        json.dump(payload, stream, ensure_ascii=False, indent=2, sort_keys=True)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())


def append_jsonl(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("ab") as stream:
        fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
        stream.write(canonical_json(dict(payload)))
        stream.flush()
        os.fsync(stream.fileno())
        fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.is_file() or path.is_symlink():
        raise AprimeReadoutError(f"missing/non-regular CSV: {relative(path)}")
    with path.open(newline="", encoding="utf-8-sig") as stream:
        reader = csv.DictReader(stream)
        if not reader.fieldnames:
            raise AprimeReadoutError(f"CSV has no header: {relative(path)}")
        return [dict(row) for row in reader]


def require_equal(observed: Any, expected: Any, label: str) -> None:
    if observed != expected:
        raise AprimeReadoutError(
            f"{label} mismatch: observed={observed!r}, expected={expected!r}"
        )


def file_record(path: Path) -> dict[str, Any]:
    if not path.is_file() or path.is_symlink() or path.stat().st_size <= 0:
        raise AprimeReadoutError(f"artifact missing/empty/non-regular: {relative(path)}")
    return {
        "path": relative(path),
        "sha256": sha256_file(path),
        "bytes": int(path.stat().st_size),
    }


def verify_record(record: Mapping[str, Any], label: str) -> Path:
    raw = record.get("path")
    expected = record.get("sha256")
    if not isinstance(raw, str) or not isinstance(expected, str):
        raise AprimeReadoutError(f"{label} path/SHA binding is missing")
    path = repo_path(raw)
    require_equal(sha256_file(path), expected, f"{label} SHA256")
    if "bytes" in record:
        require_equal(path.stat().st_size, int(record["bytes"]), f"{label} bytes")
    return path


def load_module(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise AprimeReadoutError(f"cannot load module: {relative(path)}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def git(*arguments: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    process = subprocess.run(
        ["git", "-c", f"safe.directory={REPO}", "-C", str(REPO), *arguments],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if check and process.returncode:
        raise AprimeReadoutError(
            process.stderr.strip() or process.stdout.strip() or "git command failed"
        )
    return process


def load_config(path: Path = DEFAULT_CONFIG) -> dict[str, Any]:
    config = load_json(path)
    require_equal(config.get("schema"), CONFIG_SCHEMA, "readout config schema")
    require_equal(config.get("branch"), "exp/fusion-w1", "branch lock")
    require_equal(config["identity_contract"].get("profile"), "full", "profile lock")
    require_equal(config["primary"].get("surface_class"), 6, "primary surface class")
    require_equal(config["primary"].get("ground_class"), 2, "primary ground class")
    require_equal(config["primary"].get("score_time_z_shift_m"), 0.0, "primary Z shift")
    require_equal(
        config["legacy_alpha_comparison"].get("score_time_z_shift_m"),
        -45.7,
        "legacy alpha Z shift",
    )
    require_equal(
        config["legacy_alpha_comparison"].get("eligible_for_preregistered_judgment"),
        False,
        "legacy comparison eligibility",
    )
    require_equal(config["roofer"].get("timeout_seconds_per_building"), None, "Roofer timeout")
    require_equal(config["roofer"].get("reconstruction_parameter_overrides"), [], "Roofer defaults")
    require_equal(config["containers"].get("time_cutoff"), None, "time cutoff")
    require_equal(config["containers"].get("serial_jobs"), True, "serial readout")
    require_equal(config["retry_contract"].get("same_error_attempts_before_skip"), 3, "retry count")
    require_equal(config["publication"].get("interpretation_or_verdict"), None, "verdict lock")
    return config


def verify_locked_inputs(config: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    observed: dict[str, dict[str, Any]] = {}
    for name, record in config["locked_inputs"].items():
        path = repo_path(record["path"])
        actual = file_record(path)
        require_equal(actual["sha256"], record["sha256"], f"locked input {name}")
        observed[name] = actual
    targets = read_csv(repo_path(config["locked_inputs"]["targets"]["path"]))
    require_equal(len(targets), int(config["locked_inputs"]["targets"]["population"]), "target population")
    return observed


def verify_git_runtime(config: Mapping[str, Any]) -> dict[str, Any]:
    branch = git("branch", "--show-current").stdout.strip()
    head = git("rev-parse", "HEAD").stdout.strip()
    require_equal(branch, config["branch"], "runtime branch")
    records = []
    for logical in config["implementation_files"]:
        if not git("ls-files", "--error-unmatch", logical, check=False).returncode == 0:
            raise AprimeReadoutError(f"implementation is not tracked: {logical}")
        head_blob = git("rev-parse", f"{head}:{logical}", check=False)
        if head_blob.returncode:
            raise AprimeReadoutError(f"implementation absent at HEAD: {logical}")
        worktree_blob = git("hash-object", "--", logical).stdout.strip()
        require_equal(worktree_blob, head_blob.stdout.strip(), f"implementation HEAD {logical}")
        records.append({
            **file_record(repo_path(logical)),
            "git_blob": worktree_blob,
            "tracked_at_head": True,
            "worktree_matches_head": True,
        })
    return {"branch": branch, "head": head, "implementation_files": records}


def target_rows(config: Mapping[str, Any]) -> list[dict[str, str]]:
    path = repo_path(config["locked_inputs"]["targets"]["path"])
    require_equal(sha256_file(path), config["locked_inputs"]["targets"]["sha256"], "targets SHA")
    rows = read_csv(path)
    rows.sort(key=lambda row: int(row["aprime_order"]))
    require_equal([int(row["aprime_order"]) for row in rows], list(range(1, 10)), "target order")
    if len({row["building_id"] for row in rows}) != 9:
        raise AprimeReadoutError("target building IDs are not unique")
    return rows


def target_row(config: Mapping[str, Any], building_id: str) -> dict[str, str]:
    matches = [row for row in target_rows(config) if row["building_id"] == building_id]
    if len(matches) != 1:
        raise AprimeReadoutError(f"building is not a unique A-prime target: {building_id}")
    return matches[0]


def validate_identity(
    config: Mapping[str, Any], building_id: str, arm: str, run: str, profile: str
) -> dict[str, str]:
    if re.fullmatch(r"DEBY_LOD2_[0-9]+", building_id) is None:
        raise AprimeReadoutError(f"unsafe building identity: {building_id!r}")
    if arm not in ARMS or run not in RUNS:
        raise AprimeReadoutError(f"invalid arm/run: {arm}/{run}")
    require_equal(profile, config["identity_contract"]["profile"], "readout profile")
    if arm == "B":
        require_equal(run, "r1", "arm B replicate")
        if building_id not in set(config["identity_contract"]["B_allowed"]):
            raise AprimeReadoutError(f"building is outside preregistered arm-B subset: {building_id}")
    return target_row(config, building_id)


def job_dir(config: Mapping[str, Any], building_id: str, arm: str, run: str) -> Path:
    return repo_path(
        config["outputs"]["job_template"].format(
            building_id=building_id, arm=arm, run=run
        )
    )


def attempt_dir(
    config: Mapping[str, Any], building_id: str, arm: str, run: str, attempt: int
) -> Path:
    minimum = int(config["retry_contract"]["attempt_number_min"])
    maximum = int(config["retry_contract"]["attempt_number_max"])
    if attempt < minimum or attempt > maximum:
        raise AprimeReadoutError(f"attempt outside {minimum}..{maximum}: {attempt}")
    return job_dir(config, building_id, arm, run) / "attempts" / f"attempt_{attempt:03d}"


def training_module(config: Mapping[str, Any]) -> tuple[Any, dict[str, Any], Path]:
    record = config["locked_inputs"]["training_driver"]
    path = repo_path(record["path"])
    require_equal(sha256_file(path), record["sha256"], "training driver SHA")
    module = load_module("fusion_w1_aprime_readout_training", path)
    config_path = repo_path(config["locked_inputs"]["training_config"]["path"])
    training_config = module.load_config(config_path)
    return module, training_config, config_path


def resolve_training_binding(
    config: Mapping[str, Any], building_id: str, arm: str, run: str
) -> dict[str, Any]:
    module, training_config, config_path = training_module(config)
    check = module.check_materialization(
        repo=REPO,
        config_path=config_path,
        config=training_config,
        building_id=building_id,
        arm=arm,
        run=run,
        profile="full",
        roundtrip=False,
    )
    head = git("rev-parse", "HEAD").stdout.strip()
    require_equal(check["method_head"], head, "training method HEAD/current HEAD")
    target = module.job_dir(REPO, training_config, building_id, arm, run, "full")
    materialization_path = target / training_config["outputs"]["materialization_manifest"]
    completed_path = target / training_config["outputs"]["completed_receipt"]
    failed_path = target / training_config["outputs"]["failed_receipt"]
    if failed_path.exists() or failed_path.is_symlink():
        raise AprimeReadoutError(f"training job has failure receipt: {relative(failed_path)}")
    completed = load_json(completed_path)
    require_equal(completed.get("schema"), module.COMPLETED_SCHEMA, "training completion schema")
    require_equal(completed.get("status"), "COMPLETED", "training completion status")
    for key, expected in (
        ("building_id", building_id), ("arm", arm), ("replicate", run), ("profile", "full")
    ):
        require_equal(completed.get(key), expected, f"training completion {key}")
    require_equal(completed.get("return_code"), 0, "training return code")
    materialization = load_json(materialization_path)
    require_equal(materialization.get("git", {}).get("head"), head, "training materialization HEAD")
    require_equal(
        completed.get("materialization"),
        {"path": relative(materialization_path), "sha256": sha256_file(materialization_path)},
        "training completion/materialization binding",
    )
    completion = completed.get("training_completion")
    if not isinstance(completion, Mapping):
        raise AprimeReadoutError("training completion evidence is missing")
    require_equal(completion.get("profile"), "full", "training completion profile")
    require_equal(completion.get("completed_optimizer_updates"), 30000, "optimizer updates")
    checkpoint = verify_record(completion["final_checkpoint"], "training final checkpoint")
    resolved = verify_record(
        {"path": check["resolved_config"], "sha256": check["resolved_config_sha256"]},
        "resolved training config",
    )
    preprocess = materialization.get("preprocess")
    if not isinstance(preprocess, Mapping):
        raise AprimeReadoutError("training materialization lacks preprocess binding")
    preprocess_path = repo_path(str(preprocess["manifest"]))
    require_equal(sha256_file(preprocess_path), preprocess["manifest_sha256"], "preprocess manifest")
    data_root = repo_path(str(preprocess["data_root"]))
    if not data_root.is_dir() or data_root.is_symlink():
        raise AprimeReadoutError(f"preprocess data root missing: {relative(data_root)}")
    return {
        "identity": {
            "building_id": building_id,
            "arm": arm,
            "replicate": run,
            "profile": "full",
        },
        "current_head": head,
        "training_config": file_record(config_path),
        "training_driver": file_record(repo_path(config["locked_inputs"]["training_driver"]["path"])),
        "materialization": file_record(materialization_path),
        "completed": file_record(completed_path),
        "checkpoint": file_record(checkpoint),
        "resolved_config": file_record(resolved),
        "preprocess_manifest": file_record(preprocess_path),
        "data_root": relative(data_root),
        "preprocess_full_snapshot_sha256": preprocess["full_snapshot_sha256"],
        "completed_receipt_payload_sha256": sha256_bytes(canonical_json(completed)),
    }


def begin_attempt(
    config: Mapping[str, Any], building_id: str, arm: str, run: str, profile: str
) -> dict[str, Any]:
    target = validate_identity(config, building_id, arm, run, profile)
    locked = verify_locked_inputs(config)
    method = verify_git_runtime(config)
    job = job_dir(config, building_id, arm, run)
    if (job / "complete.json").exists() or (job / "complete.json").is_symlink():
        raise AprimeReadoutError("job already has its authoritative complete receipt")
    attempts_root = job / "attempts"
    existing = sorted(
        int(match.group(1))
        for path in attempts_root.glob("attempt_*")
        if path.is_dir() and not path.is_symlink()
        and (match := re.fullmatch(r"attempt_([0-9]{3})", path.name)) is not None
    ) if attempts_root.is_dir() else []
    failure_signatures = []
    for number in existing:
        failure_path = attempt_dir(config, building_id, arm, run, number) / "failure.json"
        if failure_path.is_file() and not failure_path.is_symlink():
            failure = load_json(failure_path)
            failure_signatures.append(str(failure.get("error_signature", "")))
        else:
            failure_signatures.append("")
    threshold = int(config["retry_contract"]["same_error_attempts_before_skip"])
    if (
        len(failure_signatures) >= threshold
        and failure_signatures[-1]
        and len(set(failure_signatures[-threshold:])) == 1
    ):
        raise AprimeReadoutError(
            "the same readout error signature occurred three consecutive times; job is skipped"
        )
    next_attempt = max(existing, default=0) + 1
    if next_attempt > int(config["retry_contract"]["attempt_number_max"]):
        raise AprimeReadoutError("attempt namespace exhausted")
    training = resolve_training_binding(config, building_id, arm, run)
    attempt = attempt_dir(config, building_id, arm, run, next_attempt)
    attempt.mkdir(parents=True, exist_ok=False)
    payload = {
        "schema": ATTEMPT_SCHEMA,
        "state": "STARTED",
        "created_at": now_iso(),
        "run_id": config["run_id"],
        "task_id": config["task_id"],
        "attempt": next_attempt,
        "attempt_key": f"{building_id}/arm_{arm}/{run}/attempt_{next_attempt:03d}",
        "identity": {
            "building_id": building_id,
            "arm": arm,
            "replicate": run,
            "profile": profile,
        },
        "target": dict(target),
        "git_lock": method,
        "locked_inputs": locked,
        "training": training,
        "paths": {
            "attempt": relative(attempt),
            "tsdf": relative(attempt / "tsdf"),
            "primary": relative(attempt / "primary"),
            "legacy_alpha": relative(attempt / "legacy_alpha"),
        },
        "publication": {
            "append_only_attempt": True,
            "external_stage_started": False,
            "scientific_verdict": None,
        },
    }
    exclusive_json(attempt / "attempt.json", payload)
    return payload


def load_attempt(
    config: Mapping[str, Any], building_id: str, arm: str, run: str, attempt_number: int
) -> tuple[Path, dict[str, Any]]:
    validate_identity(config, building_id, arm, run, "full")
    attempt = attempt_dir(config, building_id, arm, run, attempt_number)
    payload = load_json(attempt / "attempt.json")
    require_equal(payload.get("schema"), ATTEMPT_SCHEMA, "attempt schema")
    require_equal(payload.get("state"), "STARTED", "attempt state")
    require_equal(payload.get("attempt"), attempt_number, "attempt number")
    require_equal(
        payload.get("identity"),
        {"building_id": building_id, "arm": arm, "replicate": run, "profile": "full"},
        "attempt identity",
    )
    current = verify_git_runtime(config)
    require_equal(payload.get("git_lock", {}).get("head"), current["head"], "attempt/current HEAD")
    for name, record in payload["training"].items():
        if isinstance(record, Mapping) and {"path", "sha256"}.issubset(record):
            verify_record(record, f"attempt training {name}")
    return attempt, payload


def tsdf_argv(
    config: Mapping[str, Any], building_id: str, arm: str, run: str, attempt_number: int
) -> list[str]:
    attempt, payload = load_attempt(config, building_id, arm, run, attempt_number)
    training = payload["training"]
    return [
        config["locked_inputs"]["tsdf_driver"]["path"],
        "--config",
        config["locked_inputs"]["tsdf_config"]["path"],
        "--checkpoint",
        training["checkpoint"]["path"],
        "--training-config",
        training["resolved_config"]["path"],
        "--data-root",
        training["data_root"],
        "--preprocess-manifest",
        training["preprocess_manifest"]["path"],
        "--output-dir",
        relative(attempt / "tsdf"),
        "--building-id",
        building_id,
        "--condition",
        f"arm_{arm}",
        "--replicate",
        run,
        "--device",
        "cuda",
    ]


def validate_tsdf_receipt(
    config: Mapping[str, Any], attempt: Path, materialization: Mapping[str, Any]
) -> dict[str, Any]:
    path = attempt / "tsdf" / "tsdf_receipt.json"
    receipt = load_json(path)
    require_equal(receipt.get("schema"), config["primary"]["tsdf_receipt_schema"], "TSDF schema")
    require_equal(receipt.get("status"), "COMPLETED", "TSDF status")
    require_equal(receipt.get("verdict"), None, "TSDF verdict")
    identity = materialization["identity"]
    require_equal(
        receipt.get("identity"),
        {
            "building_id": identity["building_id"],
            "condition": f"arm_{identity['arm']}",
            "replicate": identity["replicate"],
            "rehearsal_defaults": False,
        },
        "TSDF identity",
    )
    git_lock = receipt.get("git_lock") or {}
    require_equal(git_lock.get("head"), materialization["git_lock"]["head"], "TSDF/current HEAD")
    require_equal(git_lock.get("branch"), config["branch"], "TSDF branch")
    checks = receipt.get("checks") or {}
    for name in config["primary"]["tsdf_required_checks"]:
        require_equal(checks.get(name), True, f"TSDF check {name}")
    method = receipt.get("method") or {}
    require_equal(method.get("alpha_threshold"), None, "TSDF alpha threshold")
    require_equal(method.get("integration_mask"), "exact_class6_roof_TIN_M_j", "TSDF M_j")
    require_equal(method.get("voxel_size_m"), 0.05, "TSDF voxel")
    require_equal(method.get("sdf_trunc_m"), 0.25, "TSDF truncation")
    inputs = receipt.get("inputs") or {}
    expected = {
        "checkpoint": materialization["training"]["checkpoint"],
        "training_config": materialization["training"]["resolved_config"],
        "preprocess_manifest": materialization["training"]["preprocess_manifest"],
    }
    for name, binding in expected.items():
        observed = inputs.get(name) or {}
        require_equal(observed.get("path"), binding["path"], f"TSDF {name} path")
        require_equal(observed.get("sha256"), binding["sha256"], f"TSDF {name} SHA")
        verify_record(observed, f"TSDF input {name}")
    artifacts = receipt.get("artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        raise AprimeReadoutError("TSDF receipt has no artifact inventory")
    records = [file_record(verify_record(record, "TSDF artifact")) for record in artifacts]
    if len({record["path"] for record in records}) != len(records):
        raise AprimeReadoutError("TSDF artifact inventory has duplicate paths")
    surface = attempt / "tsdf" / config["primary"]["surface_npz_name"]
    if relative(surface) not in {record["path"] for record in records}:
        raise AprimeReadoutError("TSDF surface NPZ is absent from receipt artifacts")
    return {
        "receipt": file_record(path),
        "identity": dict(receipt["identity"]),
        "checks": {name: True for name in config["primary"]["tsdf_required_checks"]},
        "method": dict(method),
        "surface_sampling": dict(receipt.get("surface_sampling") or {}),
        "marching_cubes": dict(receipt.get("marching_cubes") or {}),
        "artifacts": records,
    }


def p0prime_module(config: Mapping[str, Any]) -> tuple[Any, dict[str, Any]]:
    adapter_record = config["locked_inputs"]["p0prime_adapter"]
    adapter_path = repo_path(adapter_record["path"])
    require_equal(sha256_file(adapter_path), adapter_record["sha256"], "T3 adapter SHA")
    module = load_module("fusion_w1_aprime_readout_p0prime", adapter_path)
    config_path = repo_path(config["locked_inputs"]["p0prime_config"]["path"])
    p0_config = module.load_config(config_path)
    return module, p0_config


def engine_for(
    config: Mapping[str, Any], attempt: Path, mode: str
) -> tuple[Any, dict[str, Any], Any, dict[str, Any]]:
    if mode not in MODES:
        raise AprimeReadoutError(f"unknown readout mode: {mode}")
    p0, p0_config = p0prime_module(config)
    engine, compat = p0.configured_engine(p0_config)
    result = copy.deepcopy(compat)
    root = attempt / mode / "engine"
    result["task_id"] = config["task_id"]
    result["implementation_files"] = list(config["implementation_files"])
    result["outputs"] = {
        "root": relative(root),
        "building_dir_template": relative(root / "by_building" / "{building_id}"),
        "scores_csv": relative(root / "scores.csv"),
        "progress": relative(root / "progress.json"),
        "failures_jsonl": relative(root / "failures.jsonl"),
        "final_manifest": relative(root / "manifest.json"),
        "driver_lock": relative(root / "driver.lock"),
    }
    result["reference"]["score_time_z_shift_m"] = float(
        config["primary" if mode == "primary" else "legacy_alpha_comparison"][
            "score_time_z_shift_m"
        ]
    )
    result["roofer"] = copy.deepcopy(config["roofer"])
    result["resource_lock"] = {
        "memory": config["containers"]["memory"],
        "memory_swap": config["containers"]["memory_swap"],
        "network": config["containers"]["network"],
        "serial_buildings": True,
        "concurrent_with_learning": False,
        "concurrent_with_readout": False,
    }
    result["publication"] = {
        "scores_incremental_atomic_upsert": True,
        "one_row_per_building": True,
        "per_building_complete_receipt_written_after_scores_csv": True,
        "partial_buildings_reviewable": True,
        "failures_append_only": True,
        "final_manifest_written_last": True,
        "refuse_work_after_final_manifest": True,
    }
    return engine, result, p0, p0_config


def engine_job(
    config: Mapping[str, Any], attempt: Path, mode: str, building_id: str
) -> tuple[Any, dict[str, Any], Path]:
    engine, compat, _p0, _p0_config = engine_for(config, attempt, mode)
    return engine, compat, engine.building_dir(compat, building_id)


def inspect_las(
    path: Path,
    *,
    required_classes: set[int],
    allowed_classes: set[int],
) -> dict[str, Any]:
    try:
        import laspy
    except ImportError as exc:
        raise AprimeReadoutError("laspy is required in the tools image") from exc
    if not path.is_file() or path.is_symlink():
        raise AprimeReadoutError(f"LAS missing/non-regular: {relative(path)}")
    las = laspy.read(path)
    crs = las.header.parse_crs()
    epsg = crs.to_epsg() if crs is not None else None
    classes = np.asarray(las.classification, dtype=np.uint8)
    unique = {int(value) for value in np.unique(classes)}
    if not required_classes.issubset(unique):
        raise AprimeReadoutError(
            f"LAS lacks required classes: {sorted(required_classes - unique)}"
        )
    if not unique.issubset(allowed_classes):
        raise AprimeReadoutError(f"LAS includes forbidden classes: {sorted(unique)}")
    xyz = np.column_stack([las.x, las.y, las.z]).astype(np.float64)
    if len(xyz) == 0 or not np.isfinite(xyz).all():
        raise AprimeReadoutError("LAS coordinates are empty or nonfinite")
    dimensions = {str(name).lower() for name in las.header.point_format.dimension_names}
    counts = {str(value): int(np.count_nonzero(classes == value)) for value in sorted(unique)}
    return {
        **file_record(path),
        "point_count": int(len(xyz)),
        "class_counts": counts,
        "epsg": epsg,
        "las_version": str(las.header.version),
        "point_format": int(las.header.point_format.id),
        "dimensions": sorted(dimensions),
        "bounds_min": xyz.min(axis=0).astype(float).tolist(),
        "bounds_max": xyz.max(axis=0).astype(float).tolist(),
    }


def write_surface_las(
    config: Mapping[str, Any], surface_npz: Path, output: Path
) -> dict[str, Any]:
    try:
        import laspy
        from pyproj import CRS
    except ImportError as exc:
        raise AprimeReadoutError("laspy and pyproj are required in the tools image") from exc
    if output.exists() or output.is_symlink():
        raise AprimeReadoutError(f"refusing to overwrite class-6 LAS: {relative(output)}")
    primary = config["primary"]
    with np.load(surface_npz, allow_pickle=False) as archive:
        required = {"xyz_epsg25832_orthometric", "rgb", "classification", "crs", "vertical_datum"}
        if not required.issubset(archive.files):
            raise AprimeReadoutError(
                f"TSDF sample NPZ lacks fields: {sorted(required - set(archive.files))}"
            )
        xyz = np.asarray(archive["xyz_epsg25832_orthometric"], dtype=np.float64)
        rgb = np.asarray(archive["rgb"], dtype=np.uint8)
        classes = np.asarray(archive["classification"], dtype=np.uint8)
        crs = str(np.asarray(archive["crs"]).reshape(()))
        datum = str(np.asarray(archive["vertical_datum"]).reshape(()))
    if xyz.ndim != 2 or xyz.shape[1] != 3 or len(xyz) == 0:
        raise AprimeReadoutError(f"TSDF sample XYZ shape invalid: {xyz.shape}")
    if rgb.shape != xyz.shape or classes.shape != (len(xyz),):
        raise AprimeReadoutError("TSDF sample RGB/classification shape drift")
    if not np.isfinite(xyz).all() or np.any(classes != int(primary["surface_class"])):
        raise AprimeReadoutError("TSDF sample is nonfinite or not exactly class 6")
    require_equal(crs, primary["crs"], "TSDF sample CRS")
    require_equal(datum, primary["vertical_datum"], "TSDF sample vertical datum")
    header = laspy.LasHeader(
        point_format=int(primary["point_format"]), version=primary["las_version"]
    )
    scales = np.asarray(primary["scale_m"], dtype=np.float64)
    header.scales = scales
    header.offsets = np.floor(xyz.min(axis=0))
    header.add_crs(CRS.from_epsg(25832))
    las = laspy.LasData(header)
    las.x, las.y, las.z = xyz[:, 0], xyz[:, 1], xyz[:, 2]
    las.classification = classes
    rgb16 = rgb.astype(np.uint16) * np.uint16(257)
    las.red, las.green, las.blue = rgb16[:, 0], rgb16[:, 1], rgb16[:, 2]
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(f".{output.name}.{os.getpid()}.tmp")
    las.write(temporary)
    with temporary.open("rb+") as stream:
        os.fsync(stream.fileno())
    os.replace(temporary, output)
    actual = inspect_las(output, required_classes={6}, allowed_classes={6})
    require_equal(actual["point_count"], len(xyz), "surface LAS row count")
    require_equal(actual["epsg"], 25832, "surface LAS EPSG")
    require_equal(actual["las_version"], primary["las_version"], "surface LAS version")
    require_equal(actual["point_format"], int(primary["point_format"]), "surface LAS point format")
    return {
        **actual,
        "source_npz": file_record(surface_npz),
        "source_array": "xyz_epsg25832_orthometric",
        "RGB8_to_LAS16_mapping": "value_times_257",
        "geometry_source_changed": False,
        "classification_assigned": 6,
        "vertical_conversion_application_count_upstream": 1,
    }


def prepare_primary(
    config: Mapping[str, Any], building_id: str, arm: str, run: str, attempt_number: int
) -> dict[str, Any]:
    attempt, materialization = load_attempt(config, building_id, arm, run, attempt_number)
    tsdf = validate_tsdf_receipt(config, attempt, materialization)
    _engine, _compat, p0, p0_config = engine_for(config, attempt, "primary")
    consumed = p0.validate_consumed_building(p0_config, building_id, deep=True)
    preprocess_path = consumed["resolution"]["manifest_path"]
    require_equal(
        relative(preprocess_path),
        materialization["training"]["preprocess_manifest"]["path"],
        "readout/T3 preprocess path",
    )
    require_equal(
        sha256_file(preprocess_path),
        materialization["training"]["preprocess_manifest"]["sha256"],
        "readout/T3 preprocess SHA",
    )
    engine, compat, job = engine_job(config, attempt, "primary", building_id)
    if job.exists() and any(job.iterdir()):
        raise AprimeReadoutError(f"primary engine job is not empty: {relative(job)}")
    job.mkdir(parents=True, exist_ok=True)
    surface_npz = attempt / "tsdf" / config["primary"]["surface_npz_name"]
    surface_las = job / "assembly_input" / "aprime_tsdf_surface_class6_epsg25832.las"
    surface = write_surface_las(config, surface_npz, surface_las)
    ground_path = consumed["ground_path"]
    ground = p0.inspect_source_las(
        ground_path,
        expected_class=2,
        expected_count=consumed["ground_n"],
        config=p0_config,
    )
    joined_path = job / "assembly_input" / config["primary"]["joined_las_name"]
    join = p0.join_source_lases(
        surface_las,
        ground_path,
        joined_path,
        seed_n=surface["point_count"],
        ground_n=consumed["ground_n"],
        config=p0_config,
    )
    require_equal(join.get("semantic_row_digest_equal"), True, "primary join digest")
    footprint = engine.write_footprint_subset(compat, building_id, job / "footprint.gpkg")
    classification = {
        "schema": "jointbuildgs.fusion_w1.seed_p0prime.classification_receipt.v1",
        "state": "PASSED",
        "created_utc": now_iso(),
        "building_id": building_id,
        "processing_order": int(materialization["target"]["aprime_order"]),
        "tier": materialization["target"]["tier"],
        "cohort": materialization["target"]["cohort"],
        "target_role": materialization["target"]["target_role"],
        "method": config["primary"]["join_method"],
        "mutation": {
            "geometry_changed": False,
            "classification_changed": False,
            "vertical_datum_changed": False,
            "rows_removed": 0,
            "rows_added": 0,
            "downsample_runs_started": 0,
            "smrf_runs_started": 0,
            "overlay_runs_started": 0,
        },
        "preprocess_manifest": file_record(preprocess_path),
        "classified_seed_las": {
            **file_record(joined_path),
            "point_count": surface["point_count"] + consumed["ground_n"],
            "class_counts": {"2": consumed["ground_n"], "6": surface["point_count"]},
            "epsg": 25832,
            "vertical_datum": "orthometric",
            "las_version": config["primary"]["las_version"],
            "point_format": int(config["primary"]["point_format"]),
            "rgb_dimensions_present": True,
        },
        "footprint": footprint,
        "primary_readout": True,
        "eligible_for_preregistered_judgment": True,
        "interpretation_or_verdict": None,
    }
    classification_path = job / "classification_receipt.json"
    exclusive_json(classification_path, classification)
    prepare_receipt = {
        "schema": PRIMARY_PREP_SCHEMA,
        "state": "PASSED",
        "created_at": now_iso(),
        "identity": dict(materialization["identity"]),
        "readout_role": config["primary"]["readout_role"],
        "eligible_for_preregistered_judgment": True,
        "tsdf": tsdf,
        "class6_surface_las": surface,
        "original_ALS_class2_ground": {
            **file_record(ground_path),
            "point_count": int(ground["point_count"]),
            "class_counts": {"2": int(ground["point_count"])},
            "trainer_path_reference": False,
        },
        "join": {
            **join,
            "receipt_embedded": True,
            "class_order": [6, 2],
            "original_ground_reused": True,
        },
        "classification_receipt": file_record(classification_path),
        "footprint": footprint,
        "reference_inputs_opened": False,
        "interpretation_or_verdict": None,
    }
    exclusive_json(attempt / "primary" / "prepare_receipt.json", prepare_receipt)
    return prepare_receipt


def write_footprint_geojson(
    config: Mapping[str, Any], attempt: Path, building_id: str
) -> dict[str, Any]:
    engine, compat, _p0, _p0_config = engine_for(config, attempt, "legacy_alpha")
    root = attempt / "legacy_alpha"
    gpkg = root / "footprint.gpkg"
    geojson = root / "footprint.geojson"
    footprint = engine.write_footprint_subset(compat, building_id, gpkg)
    if geojson.exists() or geojson.is_symlink():
        raise AprimeReadoutError("legacy alpha footprint GeoJSON already exists")
    process = subprocess.run(
        [
            "ogr2ogr", "-f", "GeoJSON", str(geojson), str(gpkg),
            "p0prime_footprint", "-nln", "footprint", "-a_srs", "EPSG:25832",
        ],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    if process.returncode:
        raise AprimeReadoutError(
            f"ogr2ogr footprint conversion failed exit={process.returncode}: {process.stdout[-1000:]}"
        )
    payload = load_json(geojson)
    features = payload.get("features")
    if not isinstance(features, list) or len(features) != 1:
        raise AprimeReadoutError("legacy alpha footprint GeoJSON is not one feature")
    properties = features[0].get("properties") or {}
    require_equal(str(properties.get("building_id")), building_id, "footprint building")
    return {
        "gpkg": {**file_record(gpkg), "layer": "p0prime_footprint"},
        "geojson": file_record(geojson),
        "source": footprint,
        "role": "approved GroundSurface XY only; legacy plumbing and Roofer footprint",
    }


def authorize_alpha_extract(
    config: Mapping[str, Any], building_id: str, arm: str, run: str, attempt_number: int
) -> dict[str, Any]:
    attempt, materialization = load_attempt(config, building_id, arm, run, attempt_number)
    root = attempt / "legacy_alpha"
    if (root / "extract_invocation.json").exists():
        raise AprimeReadoutError("legacy alpha extraction was already authorized")
    footprint = write_footprint_geojson(config, attempt, building_id)
    output = root / "pointcloud" / "readout.npz"
    output.parent.mkdir(parents=True, exist_ok=False)
    legacy = config["legacy_alpha_comparison"]
    short_id = building_id.removeprefix("DEBY_LOD2_")
    argv = [
        config["locked_inputs"]["legacy_alpha_extractor"]["path"],
        "--ckpt", materialization["training"]["checkpoint"]["path"],
        "--out", relative(output),
        "--downscale", str(legacy["downscale"]),
        "--voxel", str(legacy["voxel_m"]),
        "--alpha", str(legacy["alpha_min_exclusive"]),
        "--min-obs", str(legacy["minimum_observations"]),
        "--buffer", str(legacy["footprint_buffer_m"]),
        "--geojson", footprint["geojson"]["path"],
        "--data-root", materialization["training"]["data_root"],
        "--max-views", str(legacy["maximum_views"]),
        "--sh-degree", str(legacy["sh_degree"]),
        "--targets", short_id,
        "--no-sem",
    ]
    runtime = repo_path(config["outputs"]["runtime_environment"])
    paths = {
        "HOME": runtime / "home",
        "XDG_CACHE_HOME": runtime / "xdg_cache",
        "TORCH_EXTENSIONS_DIR": runtime / "torch_extensions",
    }
    for path in paths.values():
        path.mkdir(parents=True, exist_ok=True)
        if path.is_symlink() or not path.is_dir():
            raise AprimeReadoutError(f"invalid writable runtime path: {relative(path)}")
    invocation = {
        "schema": "jointbuildgs.fusion_w1_aprime.readout.alpha_extract_invocation.v1",
        "state": "AUTHORIZED",
        "created_at": now_iso(),
        "identity": dict(materialization["identity"]),
        "readout_role": legacy["readout_role"],
        "eligible_for_preregistered_judgment": False,
        "comparison_only": True,
        "image": config["containers"]["dev_image"],
        "image_id": config["containers"]["dev_image_id"],
        "argv": argv,
        "environment": {
            **{key: relative(path) for key, path in paths.items()},
            "MAX_JOBS": "1",
        },
        "checkpoint": materialization["training"]["checkpoint"],
        "preprocess_manifest": materialization["training"]["preprocess_manifest"],
        "footprint": footprint,
        "output": relative(output),
        "parameters": {
            "alpha_min_exclusive": legacy["alpha_min_exclusive"],
            "minimum_observations": legacy["minimum_observations"],
            "voxel_m": legacy["voxel_m"],
            "semantic_pass": False,
        },
        "reference_inputs_present": False,
        "interpretation_or_verdict": None,
    }
    exclusive_json(root / "extract_invocation.json", invocation)
    return invocation


def alpha_extract_argv(
    config: Mapping[str, Any], building_id: str, arm: str, run: str, attempt_number: int
) -> list[str]:
    attempt, _ = load_attempt(config, building_id, arm, run, attempt_number)
    invocation = load_json(attempt / "legacy_alpha" / "extract_invocation.json")
    require_equal(invocation.get("state"), "AUTHORIZED", "alpha extract invocation")
    verify_record(invocation["checkpoint"], "alpha extraction checkpoint")
    return list(invocation["argv"])


def alpha_extract_environment(
    config: Mapping[str, Any], building_id: str, arm: str, run: str, attempt_number: int
) -> list[str]:
    attempt, _ = load_attempt(config, building_id, arm, run, attempt_number)
    invocation = load_json(attempt / "legacy_alpha" / "extract_invocation.json")
    values = dict(invocation["environment"])
    result = []
    for key in ("HOME", "XDG_CACHE_HOME", "TORCH_EXTENSIONS_DIR"):
        path = repo_path(values[key])
        if not path.is_dir() or path.is_symlink():
            raise AprimeReadoutError(f"legacy alpha environment is not ready: {key}")
        result.append(f"{key}={CONTAINER_REPO / Path(values[key])}")
    result.append("MAX_JOBS=1")
    return result


def inspect_alpha_npz(config: Mapping[str, Any], path: Path) -> dict[str, Any]:
    if not path.is_file() or path.is_symlink():
        raise AprimeReadoutError(f"alpha NPZ missing/non-regular: {relative(path)}")
    with np.load(path, allow_pickle=False) as archive:
        if "P_utm" not in archive.files or "P_utm_clean" not in archive.files:
            raise AprimeReadoutError("legacy alpha NPZ lacks P_utm/P_utm_clean")
        raw = np.asarray(archive["P_utm"], dtype=np.float64)
        clean = np.asarray(archive["P_utm_clean"], dtype=np.float64)
        if raw.ndim != 2 or raw.shape[1] != 3 or len(raw) == 0:
            raise AprimeReadoutError(f"legacy alpha raw XYZ invalid: {raw.shape}")
        if clean.ndim != 2 or clean.shape[1] != 3 or len(clean) == 0:
            raise AprimeReadoutError(f"legacy alpha clean XYZ invalid: {clean.shape}")
        if not np.isfinite(raw).all() or not np.isfinite(clean).all():
            raise AprimeReadoutError("legacy alpha NPZ contains nonfinite XYZ")
        require_equal(
            float(np.asarray(archive["voxel"]).reshape(())),
            float(config["legacy_alpha_comparison"]["voxel_m"]),
            "legacy alpha voxel",
        )
        require_equal(
            float(np.asarray(archive["downscale"]).reshape(())),
            float(config["legacy_alpha_comparison"]["downscale"]),
            "legacy alpha downscale",
        )
        if "P_class" in archive.files or "P_class_clean" in archive.files:
            raise AprimeReadoutError("legacy alpha semantic arrays unexpectedly present")
        arrays = sorted(archive.files)
    return {
        **file_record(path),
        "arrays": arrays,
        "raw_points_n": int(len(raw)),
        "clean_points_n": int(len(clean)),
        "bounds_min": clean.min(axis=0).astype(float).tolist(),
        "bounds_max": clean.max(axis=0).astype(float).tolist(),
        "crs": "EPSG:25832",
        "vertical_frame": "ellipsoidal historical extractor output",
        "semantic_arrays_present": False,
    }


def accept_alpha_extract(
    config: Mapping[str, Any], building_id: str, arm: str, run: str,
    attempt_number: int, wall_seconds: float
) -> dict[str, Any]:
    attempt, _ = load_attempt(config, building_id, arm, run, attempt_number)
    root = attempt / "legacy_alpha"
    invocation_path = root / "extract_invocation.json"
    invocation = load_json(invocation_path)
    verify_record(invocation["checkpoint"], "alpha checkpoint at acceptance")
    stats = inspect_alpha_npz(config, repo_path(invocation["output"]))
    receipt = {
        "schema": ALPHA_EXTRACT_SCHEMA,
        "state": "COMPLETE",
        "created_at": now_iso(),
        "identity": dict(invocation["identity"]),
        "readout_role": config["legacy_alpha_comparison"]["readout_role"],
        "eligible_for_preregistered_judgment": False,
        "comparison_only": True,
        "invocation": file_record(invocation_path),
        "pointcloud": stats,
        "wall_seconds": float(wall_seconds),
        "interpretation_or_verdict": None,
    }
    exclusive_json(root / "extract_receipt.json", receipt)
    return receipt


def authorize_alpha_classification(
    config: Mapping[str, Any], building_id: str, arm: str, run: str, attempt_number: int
) -> dict[str, Any]:
    attempt, materialization = load_attempt(config, building_id, arm, run, attempt_number)
    root = attempt / "legacy_alpha"
    extract_path = root / "extract_receipt.json"
    extract = load_json(extract_path)
    require_equal(extract.get("schema"), ALPHA_EXTRACT_SCHEMA, "alpha extract receipt")
    verify_record(extract["pointcloud"], "alpha point cloud")
    invocation_path = root / "classification_invocation.json"
    output = root / "classification"
    if output.exists() or output.is_symlink():
        raise AprimeReadoutError("legacy alpha classification output already exists")
    output.mkdir(parents=True)
    argv = [
        config["locked_inputs"]["legacy_classifier"]["path"],
        "--tsdf", extract["pointcloud"]["path"],
        "--bid", building_id,
        "--geojson", load_json(root / "extract_invocation.json")["footprint"]["geojson"]["path"],
        "--buffer", str(config["legacy_alpha_comparison"]["footprint_buffer_m"]),
        "--target-density", str(config["legacy_alpha_comparison"]["classification_target_density"]),
        "--seed", "0",
        "--outdir", relative(output),
        "--tag", "fused",
    ]
    invocation = {
        "schema": "jointbuildgs.fusion_w1_aprime.readout.alpha_classify_invocation.v1",
        "state": "AUTHORIZED",
        "created_at": now_iso(),
        "identity": dict(materialization["identity"]),
        "readout_role": config["legacy_alpha_comparison"]["readout_role"],
        "eligible_for_preregistered_judgment": False,
        "comparison_only": True,
        "image": config["containers"]["tools_image"],
        "image_id": config["containers"]["tools_image_id"],
        "argv": argv,
        "extract_receipt": file_record(extract_path),
        "output_dir": relative(output),
        "downsample_applied": False,
        "interpretation_or_verdict": None,
    }
    exclusive_json(invocation_path, invocation)
    return invocation


def alpha_classification_argv(
    config: Mapping[str, Any], building_id: str, arm: str, run: str, attempt_number: int
) -> list[str]:
    attempt, _ = load_attempt(config, building_id, arm, run, attempt_number)
    invocation = load_json(attempt / "legacy_alpha" / "classification_invocation.json")
    require_equal(invocation.get("state"), "AUTHORIZED", "alpha classification invocation")
    return list(invocation["argv"])


def accept_alpha_classification(
    config: Mapping[str, Any], building_id: str, arm: str, run: str,
    attempt_number: int, wall_seconds: float
) -> dict[str, Any]:
    attempt, materialization = load_attempt(config, building_id, arm, run, attempt_number)
    root = attempt / "legacy_alpha"
    invocation_path = root / "classification_invocation.json"
    invocation = load_json(invocation_path)
    output = repo_path(invocation["output_dir"])
    stem = f"{building_id}_fused"
    metrics_path = output / f"{stem}_metrics.json"
    classified_path = output / f"{stem}_classified.las"
    metrics = load_json(metrics_path)
    require_equal(metrics.get("bid"), building_id, "alpha classifier building")
    require_equal(metrics.get("tag"), "fused", "alpha classifier tag")
    require_equal(metrics.get("voxel"), None, "alpha classification downsample")
    n_clip = int(metrics.get("n_clip", 0))
    n_used = int(metrics.get("n_used", 0))
    if n_used < 4 or metrics.get("classified_las") in {None, ""}:
        return publish_alpha_nonassembly(
            config,
            attempt=attempt,
            materialization=materialization,
            invocation_path=invocation_path,
            metrics_path=metrics_path,
            reason_code="too_few_points_before_classification",
            counts={
                "n_clip": n_clip,
                "n_used": n_used,
                "n_building_in_fp": 0,
                "class_counts": {},
                "required_classes": list(config["legacy_alpha_comparison"]["required_classes"]),
                "missing_required_classes": list(
                    config["legacy_alpha_comparison"]["required_classes"]
                ),
            },
            wall_seconds=wall_seconds,
        )
    classified = inspect_las(
        classified_path,
        required_classes=set(),
        allowed_classes=set(config["legacy_alpha_comparison"]["allowed_classes"]),
    )
    require_equal(classified["epsg"], 25832, "alpha classified EPSG")
    required = set(config["legacy_alpha_comparison"]["required_classes"])
    observed = {int(value) for value in classified["class_counts"]}
    missing = sorted(required - observed)
    n_building = int(metrics.get("n_building_in_fp", 0))
    if missing or n_building <= 0:
        reason_code = (
            "zero_class6_inside_footprint_after_SMRF_overlay"
            if 6 not in observed or n_building <= 0
            else "required_class_missing_after_SMRF_overlay"
        )
        return publish_alpha_nonassembly(
            config,
            attempt=attempt,
            materialization=materialization,
            invocation_path=invocation_path,
            metrics_path=metrics_path,
            reason_code=reason_code,
            counts={
                "n_clip": n_clip,
                "n_used": n_used,
                "n_building_in_fp": n_building,
                "class_counts": dict(classified["class_counts"]),
                "required_classes": sorted(required),
                "missing_required_classes": missing,
            },
            wall_seconds=wall_seconds,
            classified=classified,
        )
    source_invocation = load_json(root / "extract_invocation.json")
    engine, compat, job = engine_job(config, attempt, "legacy_alpha", building_id)
    if job.exists() and any(job.iterdir()):
        raise AprimeReadoutError(f"legacy alpha engine job is not empty: {relative(job)}")
    job.mkdir(parents=True, exist_ok=True)
    footprint = source_invocation["footprint"]["source"]
    footprint["path"] = source_invocation["footprint"]["gpkg"]["path"]
    footprint["sha256"] = source_invocation["footprint"]["gpkg"]["sha256"]
    classification = {
        "schema": "jointbuildgs.fusion_w1.seed_p0prime.classification_receipt.v1",
        "state": "PASSED",
        "created_utc": now_iso(),
        "building_id": building_id,
        "processing_order": int(materialization["target"]["aprime_order"]),
        "tier": materialization["target"]["tier"],
        "cohort": materialization["target"]["cohort"],
        "target_role": materialization["target"]["target_role"],
        "method": config["legacy_alpha_comparison"]["classification_method"],
        "mutation": {
            "geometry_changed": False,
            "classification_changed": True,
            "vertical_datum_changed": False,
            "rows_removed": int(metrics.get("n_clip", 0)) - int(metrics.get("n_used", 0)),
            "rows_added": 0,
            "downsample_runs_started": 0,
            "smrf_runs_started": 1,
            "overlay_runs_started": 1,
        },
        "preprocess_manifest": materialization["training"]["preprocess_manifest"],
        "classified_seed_las": {
            **classified,
            "vertical_datum": "ellipsoidal historical W1 readout frame",
            "rgb_dimensions_present": all(
                key in set(classified["dimensions"]) for key in ("red", "green", "blue")
            ),
        },
        "footprint": footprint,
        "legacy_alpha_comparison": True,
        "eligible_for_preregistered_judgment": False,
        "comparison_only": True,
        "interpretation_or_verdict": None,
    }
    engine_classification_path = job / "classification_receipt.json"
    exclusive_json(engine_classification_path, classification)
    receipt = {
        "schema": ALPHA_CLASSIFY_SCHEMA,
        "state": "COMPLETE",
        "created_at": now_iso(),
        "identity": dict(materialization["identity"]),
        "readout_role": config["legacy_alpha_comparison"]["readout_role"],
        "eligible_for_preregistered_judgment": False,
        "comparison_only": True,
        "invocation": file_record(invocation_path),
        "classified_las": classified,
        "metrics": {
            **file_record(metrics_path),
            "n_clip": int(metrics["n_clip"]),
            "n_used": int(metrics["n_used"]),
            "n_building_in_fp": int(metrics["n_building_in_fp"]),
        },
        "engine_classification_receipt": file_record(engine_classification_path),
        "footprint": footprint,
        "downsample_applied": False,
        "wall_seconds": float(wall_seconds),
        "interpretation_or_verdict": None,
    }
    exclusive_json(root / "classification_receipt.json", receipt)
    return receipt


def publish_alpha_nonassembly(
    config: Mapping[str, Any],
    *,
    attempt: Path,
    materialization: Mapping[str, Any],
    invocation_path: Path,
    metrics_path: Path,
    reason_code: str,
    counts: Mapping[str, Any],
    wall_seconds: float,
    classified: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    if reason_code not in ALPHA_NONASSEMBLY_REASONS:
        raise AprimeReadoutError(f"unknown alpha nonassembly reason: {reason_code}")
    root = attempt / "legacy_alpha"
    artifacts = [
        file_record(path)
        for path in sorted((root / "classification").glob("*"))
        if path.is_file() and not path.is_symlink()
    ]
    receipt = {
        "schema": ALPHA_CLASSIFY_SCHEMA,
        "state": "UNCONSTRUCTABLE",
        "created_at": now_iso(),
        "identity": dict(materialization["identity"]),
        "readout_role": config["legacy_alpha_comparison"]["readout_role"],
        "eligible_for_preregistered_judgment": False,
        "comparison_only": True,
        "assembly_status": "NOT_ASSEMBLED",
        "measurement_status": "NOT_MEASURED",
        "reason_code": reason_code,
        "counts": dict(counts),
        "invocation": file_record(invocation_path),
        "metrics": file_record(metrics_path),
        "classified_las": dict(classified) if classified is not None else None,
        "preserved_classification_artifacts": artifacts,
        "roofer_runs_started": 0,
        "scoring_runs_started": 0,
        "wall_seconds": float(wall_seconds),
        "infrastructure_failure": False,
        "interpretation_or_verdict": None,
    }
    classification_path = root / "classification_receipt.json"
    exclusive_json(classification_path, receipt)
    score = {
        "schema": SCORE_SCHEMA,
        "state": "NOT_ASSEMBLED",
        "created_at": now_iso(),
        "identity": dict(materialization["identity"]),
        "mode": "legacy_alpha",
        "readout_role": config["legacy_alpha_comparison"]["readout_role"],
        "eligible_for_preregistered_judgment": False,
        "comparison_only": True,
        "measurement_status": "NOT_MEASURED",
        "assembly_status": "NOT_ASSEMBLED",
        "classification_state": "UNCONSTRUCTABLE",
        "reason_code": reason_code,
        "counts": dict(counts),
        "classification_receipt": file_record(classification_path),
        "canonical_engine_complete": None,
        "canonical_score_receipt": None,
        "canonical_score_row": None,
        "measurements": {
            key: None
            for key in (
                "assembly_lod2_success", "assembly_reason", "has_lod22_geometry",
                "lod1_fallback", "val3dity_valid", "plane_precision", "plane_recall",
                "plane_f1", "roof_rms_m", "roof_hausdorff_m", "roof_completeness",
                "face_count_ratio", "xy_overlap_ratio",
            )
        },
        "reference_opened_only_after_roofer_output_frozen": None,
        "score_time_z_shift_m": float(
            config["legacy_alpha_comparison"]["score_time_z_shift_m"]
        ),
        "interpretation_or_verdict": None,
    }
    exclusive_json(root / "score.json", score)
    return receipt


def alpha_disposition(
    config: Mapping[str, Any], building_id: str, arm: str, run: str, attempt_number: int
) -> str:
    attempt, _ = load_attempt(config, building_id, arm, run, attempt_number)
    receipt = load_json(attempt / "legacy_alpha" / "classification_receipt.json")
    require_equal(receipt.get("schema"), ALPHA_CLASSIFY_SCHEMA, "alpha classification schema")
    state = receipt.get("state")
    if state == "COMPLETE":
        return "ASSEMBLE"
    if state == "UNCONSTRUCTABLE":
        require_equal(receipt.get("assembly_status"), "NOT_ASSEMBLED", "alpha assembly status")
        require_equal(receipt.get("measurement_status"), "NOT_MEASURED", "alpha measurement status")
        require_equal(receipt.get("eligible_for_preregistered_judgment"), False, "alpha eligibility")
        return "NOT_ASSEMBLED"
    raise AprimeReadoutError(f"unknown alpha classification state: {state!r}")


def authorize_roofer(
    config: Mapping[str, Any], building_id: str, arm: str, run: str,
    attempt_number: int, mode: str
) -> dict[str, Any]:
    attempt, _ = load_attempt(config, building_id, arm, run, attempt_number)
    if mode == "primary":
        prepare = load_json(attempt / "primary" / "prepare_receipt.json")
        require_equal(prepare.get("schema"), PRIMARY_PREP_SCHEMA, "primary preparation")
    else:
        classification = load_json(attempt / "legacy_alpha" / "classification_receipt.json")
        require_equal(classification.get("schema"), ALPHA_CLASSIFY_SCHEMA, "alpha classification")
    engine, compat, _job = engine_job(config, attempt, mode, building_id)
    invocation = engine.authorize_roofer(compat, building_id)
    require_equal(invocation.get("outer_parallelism"), 1, "Roofer outer parallelism")
    require_equal(invocation.get("image"), config["roofer"]["image"], "Roofer image")
    return invocation


def roofer_paths(
    config: Mapping[str, Any], building_id: str, arm: str, run: str,
    attempt_number: int, mode: str
) -> tuple[str, str, str]:
    attempt, _ = load_attempt(config, building_id, arm, run, attempt_number)
    engine, compat, _job = engine_job(config, attempt, mode, building_id)
    return engine.roofer_paths(compat, building_id)


def accept_roofer(
    config: Mapping[str, Any], building_id: str, arm: str, run: str,
    attempt_number: int, mode: str, wall_seconds: float
) -> dict[str, Any]:
    attempt, _ = load_attempt(config, building_id, arm, run, attempt_number)
    engine, compat, _job = engine_job(config, attempt, mode, building_id)
    return engine.accept_roofer(compat, building_id, wall_seconds=float(wall_seconds))


def score_mode(
    config: Mapping[str, Any], building_id: str, arm: str, run: str,
    attempt_number: int, mode: str
) -> dict[str, Any]:
    attempt, materialization = load_attempt(config, building_id, arm, run, attempt_number)
    engine, compat, job = engine_job(config, attempt, mode, building_id)
    complete = engine.score_one(compat, building_id)
    score_receipt_path = job / "score_receipt.json"
    score_receipt = load_json(score_receipt_path)
    row = score_receipt.get("row")
    if not isinstance(row, Mapping) or row.get("building_id") != building_id:
        raise AprimeReadoutError("canonical score receipt row identity drift")
    readout_config = config["primary" if mode == "primary" else "legacy_alpha_comparison"]
    normalized = {
        "schema": SCORE_SCHEMA,
        "state": "MEASURED",
        "created_at": now_iso(),
        "identity": dict(materialization["identity"]),
        "mode": mode,
        "readout_role": readout_config["readout_role"],
        "eligible_for_preregistered_judgment": bool(
            readout_config["eligible_for_preregistered_judgment"]
        ),
        "comparison_only": mode == "legacy_alpha",
        "canonical_engine_complete": {
            "path": relative(job / "complete.json"),
            "sha256": sha256_file(job / "complete.json"),
        },
        "canonical_score_receipt": file_record(score_receipt_path),
        "canonical_score_row": dict(row),
        "measurements": {
            key: row.get(key)
            for key in (
                "assembly_lod2_success", "assembly_reason", "has_lod22_geometry",
                "lod1_fallback", "val3dity_valid", "plane_precision", "plane_recall",
                "plane_f1", "roof_rms_m", "roof_hausdorff_m", "roof_completeness",
                "face_count_ratio", "xy_overlap_ratio",
            )
        },
        "reference_opened_only_after_roofer_output_frozen": True,
        "score_time_z_shift_m": float(readout_config["score_time_z_shift_m"]),
        "interpretation_or_verdict": None,
    }
    path = attempt / mode / "score.json"
    exclusive_json(path, normalized)
    return normalized


def artifact_ledger(attempt: Path) -> list[dict[str, Any]]:
    records = []
    for path in sorted(attempt.rglob("*")):
        if path.is_symlink():
            raise AprimeReadoutError(f"attempt artifact symlink forbidden: {relative(path)}")
        if path.is_file():
            records.append(file_record(path))
    if not records:
        raise AprimeReadoutError("attempt artifact ledger is empty")
    return records


def finalize_attempt(
    config: Mapping[str, Any], building_id: str, arm: str, run: str, attempt_number: int
) -> dict[str, Any]:
    attempt, materialization = load_attempt(config, building_id, arm, run, attempt_number)
    if (attempt / "failure.json").exists() or (attempt / "failure.json").is_symlink():
        raise AprimeReadoutError("cannot finalize a failed attempt")
    job = job_dir(config, building_id, arm, run)
    root_complete = job / "complete.json"
    if root_complete.exists() or root_complete.is_symlink():
        raise AprimeReadoutError("job complete receipt already exists")
    scores: dict[str, Any] = {}
    for mode in MODES:
        score_path = attempt / mode / "score.json"
        score = load_json(score_path)
        require_equal(score.get("schema"), SCORE_SCHEMA, f"{mode} score schema")
        accepted_states = {"MEASURED"} if mode == "primary" else {"MEASURED", "NOT_ASSEMBLED"}
        if score.get("state") not in accepted_states:
            raise AprimeReadoutError(
                f"{mode} score state is not final: {score.get('state')!r}"
            )
        require_equal(score.get("identity"), materialization["identity"], f"{mode} identity")
        require_equal(score.get("mode"), mode, f"{mode} score mode")
        require_equal(
            score.get("eligible_for_preregistered_judgment"),
            mode == "primary",
            f"{mode} judgment eligibility",
        )
        scores[mode] = {
            "state": score["state"],
            "measurement_status": score.get(
                "measurement_status", "MEASURED" if score["state"] == "MEASURED" else "NOT_MEASURED"
            ),
            "assembly_status": score.get(
                "assembly_status", "MEASURED" if score["state"] == "MEASURED" else "NOT_ASSEMBLED"
            ),
            "reason_code": score.get("reason_code"),
            "counts": score.get("counts"),
            "receipt": file_record(score_path),
            "measurements": score["measurements"],
        }
    ledger = artifact_ledger(attempt)
    payload = {
        "schema": COMPLETE_SCHEMA,
        "state": "COMPLETE",
        "created_at": now_iso(),
        "run_id": config["run_id"],
        "task_id": config["task_id"],
        "identity": dict(materialization["identity"]),
        "attempt": attempt_number,
        "successful_attempt": relative(attempt),
        "attempt_materialization": file_record(attempt / "attempt.json"),
        "primary": {
            "readout_role": config["primary"]["readout_role"],
            "eligible_for_preregistered_judgment": True,
            **scores["primary"],
        },
        "legacy_alpha": {
            "readout_role": config["legacy_alpha_comparison"]["readout_role"],
            "eligible_for_preregistered_judgment": False,
            "comparison_only": True,
            **scores["legacy_alpha"],
        },
        "artifact_ledger": ledger,
        "artifact_count": len(ledger),
        "partial_results_reviewable": True,
        "root_complete_receipt_written_last": True,
        "interpretation_or_verdict": None,
    }
    exclusive_json(root_complete, payload)
    return payload


def append_issue(config: Mapping[str, Any], payload: Mapping[str, Any]) -> None:
    path = repo_path(config["outputs"]["issues"])
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+", encoding="utf-8") as stream:
        fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
        stream.seek(0, os.SEEK_END)
        if stream.tell() > 0:
            stream.write("\n")
        stream.write("## FUS-W1-APRIME-READOUT-RUNTIME-FAILURE — preserved attempt\n\n")
        stream.write(f"- timestamp_utc: `{payload['created_at']}`\n")
        stream.write(f"- job: `{payload['job_key']}`\n")
        stream.write(f"- stage: `{payload['stage']}`\n")
        stream.write(f"- error_type: `{payload['error_type']}`\n")
        stream.write(f"- message: `{payload['message']}`\n")
        stream.write("- action: attempt artifacts and failure receipt retained; no verdict emitted.\n")
        stream.flush()
        os.fsync(stream.fileno())
        fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def record_failure(
    config: Mapping[str, Any], building_id: str, arm: str, run: str,
    attempt_number: int, stage: str, message: str, detail: str = "",
    error_type: str = "ExternalStageError",
) -> dict[str, Any]:
    attempt, _ = load_attempt(config, building_id, arm, run, attempt_number)
    payload = {
        "schema": FAILURE_SCHEMA,
        "state": "FAILED",
        "created_at": now_iso(),
        "job_key": f"{building_id}/arm_{arm}/{run}/attempt_{attempt_number:03d}",
        "identity": {
            "building_id": building_id,
            "arm": arm,
            "replicate": run,
            "profile": "full",
        },
        "attempt": attempt_number,
        "stage": stage,
        "error_type": error_type,
        "error_signature": sha256_bytes(f"{stage}\0{error_type}\0{message}".encode("utf-8")),
        "message": message,
        "detail": detail[-12000:],
        "partial_artifacts_preserved": True,
        "retry_contract": config["retry_contract"],
        "interpretation_or_verdict": None,
    }
    path = attempt / "failure.json"
    if not path.exists() and not path.is_symlink():
        exclusive_json(path, payload)
        append_jsonl(repo_path(config["outputs"]["failures_jsonl"]), payload)
        append_issue(config, payload)
    else:
        existing = load_json(path)
        require_equal(existing.get("schema"), FAILURE_SCHEMA, "existing failure schema")
        payload = existing
    return payload


def check_job(
    config: Mapping[str, Any], building_id: str, arm: str, run: str
) -> dict[str, Any]:
    validate_identity(config, building_id, arm, run, "full")
    method = verify_git_runtime(config)
    locked = verify_locked_inputs(config)
    training = resolve_training_binding(config, building_id, arm, run)
    job = job_dir(config, building_id, arm, run)
    attempts = []
    attempts_root = job / "attempts"
    for path in sorted(attempts_root.glob("attempt_*")) if attempts_root.is_dir() else []:
        match = re.fullmatch(r"attempt_([0-9]{3})", path.name)
        if match is not None and path.is_dir() and not path.is_symlink():
            number = int(match.group(1))
            attempts.append({
                "attempt": number,
                "path": relative(path),
                "failure": (path / "failure.json").is_file(),
                "primary_score": (path / "primary/score.json").is_file(),
                "legacy_alpha_score": (path / "legacy_alpha/score.json").is_file(),
            })
    return {
        "schema": "jointbuildgs.fusion_w1_aprime.readout.check.v1",
        "state": "READY",
        "created_at": now_iso(),
        "identity": {"building_id": building_id, "arm": arm, "replicate": run, "profile": "full"},
        "git_lock": method,
        "locked_inputs": locked,
        "training": training,
        "attempts": attempts,
        "complete": (job / "complete.json").is_file(),
        "interpretation_or_verdict": None,
    }


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser()
    result.add_argument("--config", default=str(DEFAULT_CONFIG))
    commands = result.add_subparsers(dest="command", required=True)

    def identity(command: str, *, attempt: bool = False, mode: bool = False) -> argparse.ArgumentParser:
        sub = commands.add_parser(command)
        sub.add_argument("--building-id", required=True)
        sub.add_argument("--arm", required=True, choices=ARMS)
        sub.add_argument("--run", required=True, choices=RUNS)
        if attempt:
            sub.add_argument("--attempt", required=True, type=int)
        if mode:
            sub.add_argument("--mode", required=True, choices=MODES)
        return sub

    identity("check")
    identity("begin")
    identity("tsdf-argv", attempt=True)
    identity("prepare-primary", attempt=True)
    identity("authorize-alpha-extract", attempt=True)
    identity("alpha-extract-argv", attempt=True)
    identity("alpha-extract-environment", attempt=True)
    accept_extract = identity("accept-alpha-extract", attempt=True)
    accept_extract.add_argument("--wall-seconds", required=True, type=float)
    identity("authorize-alpha-classification", attempt=True)
    identity("alpha-classification-argv", attempt=True)
    identity("alpha-disposition", attempt=True)
    accept_class = identity("accept-alpha-classification", attempt=True)
    accept_class.add_argument("--wall-seconds", required=True, type=float)
    identity("authorize-roofer", attempt=True, mode=True)
    identity("roofer-paths", attempt=True, mode=True)
    accept_rf = identity("accept-roofer", attempt=True, mode=True)
    accept_rf.add_argument("--wall-seconds", required=True, type=float)
    identity("score", attempt=True, mode=True)
    identity("finalize", attempt=True)
    failure = identity("record-failure", attempt=True)
    failure.add_argument("--stage", required=True)
    failure.add_argument("--message", required=True)
    failure.add_argument("--detail", default="")
    failure.add_argument("--error-type", default="ExternalStageError")
    return result


def print_json(payload: Any) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), flush=True)


def print_lines(values: Sequence[str]) -> None:
    for value in values:
        print(value, flush=True)


def main(argv: Sequence[str] | None = None) -> int:
    args = parser().parse_args(argv)
    config_path = Path(args.config)
    if not config_path.is_absolute():
        config_path = repo_path(config_path)
    config = load_config(config_path)
    kwargs = {
        "building_id": args.building_id,
        "arm": args.arm,
        "run": args.run,
    }
    command = args.command
    if command == "check":
        print_json(check_job(config, **kwargs))
    elif command == "begin":
        payload = begin_attempt(config, profile="full", **kwargs)
        print(payload["attempt"])
    elif command == "tsdf-argv":
        print_lines(tsdf_argv(config, attempt_number=args.attempt, **kwargs))
    elif command == "prepare-primary":
        print_json(prepare_primary(config, attempt_number=args.attempt, **kwargs))
    elif command == "authorize-alpha-extract":
        print_json(authorize_alpha_extract(config, attempt_number=args.attempt, **kwargs))
    elif command == "alpha-extract-argv":
        print_lines(alpha_extract_argv(config, attempt_number=args.attempt, **kwargs))
    elif command == "alpha-extract-environment":
        print_lines(alpha_extract_environment(config, attempt_number=args.attempt, **kwargs))
    elif command == "accept-alpha-extract":
        print_json(accept_alpha_extract(
            config, attempt_number=args.attempt, wall_seconds=args.wall_seconds, **kwargs
        ))
    elif command == "authorize-alpha-classification":
        print_json(authorize_alpha_classification(config, attempt_number=args.attempt, **kwargs))
    elif command == "alpha-classification-argv":
        print_lines(alpha_classification_argv(config, attempt_number=args.attempt, **kwargs))
    elif command == "alpha-disposition":
        print(alpha_disposition(config, attempt_number=args.attempt, **kwargs), flush=True)
    elif command == "accept-alpha-classification":
        print_json(accept_alpha_classification(
            config, attempt_number=args.attempt, wall_seconds=args.wall_seconds, **kwargs
        ))
    elif command == "authorize-roofer":
        print_json(authorize_roofer(
            config, attempt_number=args.attempt, mode=args.mode, **kwargs
        ))
    elif command == "roofer-paths":
        print_lines(roofer_paths(
            config, attempt_number=args.attempt, mode=args.mode, **kwargs
        ))
    elif command == "accept-roofer":
        print_json(accept_roofer(
            config, attempt_number=args.attempt, mode=args.mode,
            wall_seconds=args.wall_seconds, **kwargs
        ))
    elif command == "score":
        print_json(score_mode(
            config, attempt_number=args.attempt, mode=args.mode, **kwargs
        ))
    elif command == "finalize":
        print_json(finalize_attempt(config, attempt_number=args.attempt, **kwargs))
    elif command == "record-failure":
        print_json(record_failure(
            config, attempt_number=args.attempt, stage=args.stage, message=args.message,
            detail=args.detail, error_type=args.error_type, **kwargs
        ))
    else:  # pragma: no cover
        raise AprimeReadoutError(f"unknown command: {command}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"[FAILED] {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
        traceback.print_exc()
        raise SystemExit(1)
