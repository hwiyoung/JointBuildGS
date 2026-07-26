#!/usr/bin/env python3
"""Deterministic unattended A-prime smoke barrier and ordered full queue.

This driver coordinates the already locked training and readout CLIs.  It does
not train, render, assemble, or score itself.  It validates the committed HEAD
and all four preflight gates, derives the exact 21 unique jobs from the
training driver's machine-joined queue, inserts the required 42364609 A'r1
smoke barrier, and publishes append-only orchestration evidence.

Failed immutable training directories are never deleted or overwritten.  They
are moved to an append-only archive with a pre-move artifact ledger and move
receipt before the canonical path can be rematerialized.  Measurements and
failures are reported without scientific interpretation or verdict.
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
from typing import Any, Mapping, Sequence


REPO = Path(__file__).resolve().parents[3]
CONTAINER_REPO = Path("/workspace/JointBuildGS")
DEFAULT_CONFIG = (
    REPO / "phases/p2-gsjso/configs/fusion_w1_aprime_queue_20260726.json"
)
CONFIG_SCHEMA = "jointbuildgs.fusion_w1_aprime.unattended.config.v1"
PLAN_SCHEMA = "jointbuildgs.fusion_w1_aprime.unattended.plan.v1"
STAGE_RECORD_SCHEMA = "jointbuildgs.fusion_w1_aprime.unattended.stage_record.v1"
TRAINING_ARCHIVE_SCHEMA = "jointbuildgs.fusion_w1_aprime.unattended.training_archive.v1"
TRAINING_ARCHIVE_INTENT_SCHEMA = (
    "jointbuildgs.fusion_w1_aprime.unattended.training_archive_intent.v1"
)
TRAINING_ARCHIVE_LEDGER_SCHEMA = (
    "jointbuildgs.fusion_w1_aprime.unattended.training_archive_ledger.v1"
)
ORPHAN_FAILURE_SCHEMA = (
    "jointbuildgs.fusion_w1_aprime.unattended.orphan_training_failure.v1"
)
ACTION_FAILURE_SCHEMA = "jointbuildgs.fusion_w1_aprime.unattended.action_failure.v1"
STATUS_SCHEMA = "jointbuildgs.fusion_w1_aprime.unattended.status.v1"
STAGE_STOP_SCHEMA = "jointbuildgs.fusion_w1_aprime.unattended.stage_stop.v1"
COMPLETE_SCHEMA = "jointbuildgs.fusion_w1_aprime.unattended.complete.v1"
EVENT_SEQUENCE_SCHEMA = "jointbuildgs.fusion_w1_aprime.unattended.event_sequence.v1"
TERMINAL_STATES = ("MEASURED", "SKIPPED")


class UnattendedError(RuntimeError):
    """A queue method, preflight, identity, receipt, or resume rule drifted."""


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
            raise UnattendedError(f"absolute path outside repository: {raw}") from exc
    path = (REPO / raw).resolve()
    try:
        path.relative_to(REPO.resolve())
    except ValueError as exc:
        raise UnattendedError(f"path escapes repository: {raw}") from exc
    return path


def relative(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(REPO.resolve()))
    except ValueError as exc:
        raise UnattendedError(f"path outside repository: {path}") from exc


def load_json(path: Path) -> dict[str, Any]:
    if not path.is_file() or path.is_symlink():
        raise UnattendedError(f"missing/non-regular JSON: {relative(path)}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise UnattendedError(f"cannot load JSON {relative(path)}: {exc}") from exc
    if not isinstance(payload, dict):
        raise UnattendedError(f"JSON root is not object: {relative(path)}")
    return payload


def atomic_bytes(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    with temporary.open("xb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)
    fsync_directory(path.parent)


def atomic_json(path: Path, payload: Mapping[str, Any]) -> None:
    atomic_bytes(path, canonical_json(dict(payload)))


def exclusive_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as stream:
        json.dump(payload, stream, ensure_ascii=False, indent=2, sort_keys=True)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    fsync_directory(path.parent)


def atomic_csv(path: Path, rows: Sequence[Mapping[str, Any]], fields: Sequence[str]) -> None:
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=list(fields), extrasaction="ignore", lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    atomic_bytes(path, output.getvalue().encode("utf-8"))


def fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def file_record(path: Path) -> dict[str, Any]:
    if not path.is_file() or path.is_symlink() or path.stat().st_size <= 0:
        raise UnattendedError(f"artifact missing/empty/non-regular: {relative(path)}")
    return {"path": relative(path), "sha256": sha256_file(path), "bytes": path.stat().st_size}


def verify_record(record: Mapping[str, Any], label: str) -> Path:
    raw, expected = record.get("path"), record.get("sha256")
    if not isinstance(raw, str) or not isinstance(expected, str):
        raise UnattendedError(f"{label} path/SHA is missing")
    path = repo_path(raw)
    if sha256_file(path) != expected:
        raise UnattendedError(f"{label} SHA drift: {raw}")
    if "bytes" in record and path.stat().st_size != int(record["bytes"]):
        raise UnattendedError(f"{label} byte-count drift: {raw}")
    return path


def require_equal(observed: Any, expected: Any, label: str) -> None:
    if observed != expected:
        raise UnattendedError(
            f"{label} mismatch: observed={observed!r}, expected={expected!r}"
        )


def load_module(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise UnattendedError(f"cannot load module: {relative(path)}")
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
        raise UnattendedError(
            process.stderr.strip() or process.stdout.strip() or "git command failed"
        )
    return process


def load_config(path: Path = DEFAULT_CONFIG) -> dict[str, Any]:
    config = load_json(path)
    require_equal(config.get("schema"), CONFIG_SCHEMA, "queue config schema")
    require_equal(config.get("branch"), "exp/fusion-w1", "queue branch")
    sequence = config["sequence_contract"]
    require_equal(sequence.get("stage_entries"), 22, "stage-entry count")
    require_equal(sequence.get("unique_jobs"), 21, "unique-job count")
    require_equal(sequence.get("user_prompts"), False, "user-prompt lock")
    require_equal(sequence.get("time_cutoff"), None, "sequence time cutoff")
    require_equal(config["resources"].get("time_cutoff"), None, "resource time cutoff")
    require_equal(config["resources"].get("training_foreground_one_at_a_time"), True, "training serial lock")
    require_equal(config["resources"].get("readout_serial"), True, "readout serial lock")
    require_equal(
        config["failure_contract"].get("same_error_signature_attempts_before_skip"),
        3,
        "same-error retry count",
    )
    require_equal(
        config["failure_contract"].get(
            "same_error_type_consecutive_buildings_before_stage_stop"
        ),
        3,
        "consecutive-building stop count",
    )
    require_equal(config["publication"].get("interpretation_or_verdict"), None, "verdict lock")
    return config


def verify_git_runtime(config: Mapping[str, Any]) -> dict[str, Any]:
    branch = git("branch", "--show-current").stdout.strip()
    head = git("rev-parse", "HEAD").stdout.strip()
    require_equal(branch, config["branch"], "runtime branch")
    records = []
    for logical in config["implementation_files"]:
        if git("ls-files", "--error-unmatch", logical, check=False).returncode:
            raise UnattendedError(f"queue implementation is not tracked: {logical}")
        head_blob = git("rev-parse", f"{head}:{logical}", check=False)
        if head_blob.returncode:
            raise UnattendedError(f"queue implementation absent at HEAD: {logical}")
        worktree_blob = git("hash-object", "--", logical).stdout.strip()
        require_equal(worktree_blob, head_blob.stdout.strip(), f"queue implementation {logical}")
        records.append({**file_record(repo_path(logical)), "git_blob": worktree_blob})
    return {"branch": branch, "head": head, "implementation_files": records}


def verify_locked_inputs(config: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    result = {}
    for name, record in config["locked_inputs"].items():
        path = repo_path(record["path"])
        observed = file_record(path)
        require_equal(observed["sha256"], record["sha256"], f"locked input {name}")
        if name not in {"targets"}:
            logical = record["path"]
            if git("ls-files", "--error-unmatch", logical, check=False).returncode:
                raise UnattendedError(f"locked input is not tracked: {logical}")
            if git("diff", "--quiet", "HEAD", "--", logical, check=False).returncode:
                raise UnattendedError(f"locked input differs from HEAD: {logical}")
        result[name] = observed
    return result


def training_context(config: Mapping[str, Any]) -> tuple[Any, dict[str, Any], Path]:
    driver = repo_path(config["locked_inputs"]["training_driver"]["path"])
    module = load_module("fusion_w1_aprime_unattended_training", driver)
    config_path = repo_path(config["locked_inputs"]["training_config"]["path"])
    training_config = module.load_config(config_path)
    return module, training_config, config_path


def readout_context(config: Mapping[str, Any]) -> tuple[Any, dict[str, Any], Path]:
    driver = repo_path(config["locked_inputs"]["readout_driver"]["path"])
    module = load_module("fusion_w1_aprime_unattended_readout", driver)
    config_path = repo_path(config["locked_inputs"]["readout_config"]["path"])
    readout_config = module.load_config(config_path)
    return module, readout_config, config_path


def validate_preflight(config: Mapping[str, Any]) -> dict[str, Any]:
    module, training_config, _ = training_context(config)
    method = module.committed_method_gate(REPO, training_config)
    head = git("rev-parse", "HEAD").stdout.strip()
    require_equal(method["head"], head, "training method/current HEAD")
    gates = module.validate_preflight_gates(REPO, training_config, "full")
    require_equal(gates.get("status"), "PASSED", "full preflight status")
    require_equal(gates.get("required_gates"), ["five_pin", "T1", "T2", "T3"], "preflight gate order")
    t1_provenance = validate_t1_provenance(
        module, training_config, method, gates["records"]["T1"]
    )
    return {"method": method, "gates": gates, "T1_provenance": t1_provenance}


def validate_t1_provenance(
    module: Any,
    training_config: Mapping[str, Any],
    current_method: Mapping[str, Any],
    gate_record: Mapping[str, Any],
) -> dict[str, Any]:
    gate_path = verify_record(gate_record, "T1 gate receipt")
    gate = load_json(gate_path)
    completed_path = verify_record(
        gate["mini_smoke_completed_receipt"], "T1 completed receipt"
    )
    completed = load_json(completed_path)
    require_equal(completed.get("schema"), module.COMPLETED_SCHEMA, "T1 completed schema")
    require_equal(completed.get("status"), "COMPLETED", "T1 completed status")
    require_equal(completed.get("profile"), "mini_smoke", "T1 completed profile")
    materialization_path = verify_record(
        completed["materialization"], "T1 materialization receipt"
    )
    materialization = load_json(materialization_path)
    require_equal(
        materialization.get("schema"),
        module.MATERIALIZATION_SCHEMA,
        "T1 materialization schema",
    )
    require_equal(materialization.get("status"), "PASSED", "T1 materialization status")
    require_equal(materialization.get("profile"), "mini_smoke", "T1 materialization profile")
    started_path = verify_record(completed["started_receipt"], "T1 started receipt")
    started = load_json(started_path)
    require_equal(started.get("schema"), module.STARTED_SCHEMA, "T1 started schema")
    require_equal(started.get("status"), "STARTED", "T1 started status")
    require_equal(started.get("profile"), "mini_smoke", "T1 started profile")
    recorded_method = materialization.get("git")
    if not isinstance(recorded_method, Mapping):
        raise UnattendedError("T1 materialization lacks method git binding")
    require_equal(recorded_method.get("branch"), "exp/fusion-w1", "T1 method branch")
    t1_head = str(recorded_method.get("head", ""))
    if re.fullmatch(r"[0-9a-f]{40}", t1_head) is None:
        raise UnattendedError("T1 materialization HEAD is invalid")
    current_head = str(current_method["head"])
    ancestry = git("merge-base", "--is-ancestor", t1_head, current_head, check=False)
    if ancestry.returncode != 0:
        raise UnattendedError(
            f"T1 materialization HEAD is not an ancestor of current HEAD: {t1_head}"
        )
    require_equal(
        recorded_method.get("files"),
        current_method.get("files"),
        "T1 recorded/current training method files",
    )
    require_equal(started.get("method"), recorded_method, "T1 started/materialized method")
    require_equal(
        started.get("materialization"),
        {
            "path": relative(materialization_path),
            "sha256": sha256_file(materialization_path),
        },
        "T1 started/materialization binding",
    )
    require_equal(
        completed.get("materialization"),
        {
            "path": relative(materialization_path),
            "sha256": sha256_file(materialization_path),
        },
        "T1 completed/materialization binding",
    )
    require_equal(
        completed.get("started_receipt"),
        {"path": relative(started_path), "sha256": sha256_file(started_path)},
        "T1 completed/started binding",
    )
    initialization = gate.get("seed_lineage_evidence", {}).get(
        "initialization_receipt"
    )
    if not isinstance(initialization, Mapping):
        raise UnattendedError("T1 initialization receipt binding is missing")
    initialization_path = verify_record(initialization, "T1 initialization receipt")
    return {
        "status": "PASSED",
        "gate": file_record(gate_path),
        "completed": file_record(completed_path),
        "materialization": file_record(materialization_path),
        "started": file_record(started_path),
        "initialization": file_record(initialization_path),
        "recorded_head": t1_head,
        "current_head": current_head,
        "recorded_head_is_ancestor_of_current": True,
        "method_files_equal_current": True,
    }


def build_plan(config: Mapping[str, Any]) -> list[dict[str, Any]]:
    module, training_config, _ = training_context(config)
    targets = module.read_targets(REPO, training_config)
    unique = module.build_queue_rows(targets, training_config)
    require_equal(len(unique), 21, "training-driver queue jobs")
    smoke_identity = (
        config["sequence_contract"]["smoke_building_id"],
        config["sequence_contract"]["smoke_arm"],
        config["sequence_contract"]["smoke_run"],
    )
    first_identity = (unique[0]["building_id"], unique[0]["arm"], unique[0]["replicate"])
    require_equal(first_identity, smoke_identity, "smoke/queue first identity")
    stage_sources = [
        (0, "smoke_barrier", [unique[0]]),
        (1, "aprime_r1", unique[:9]),
        (2, "aprime_r2", unique[9:18]),
        (3, "B_r1", unique[18:]),
    ]
    entries = []
    for stage_order, stage_key, rows in stage_sources:
        for index, row in enumerate(rows, 1):
            entries.append(
                {
                    "global_entry_order": len(entries) + 1,
                    "stage_order": stage_order,
                    "stage_key": stage_key,
                    "stage_entry_order": index,
                    "queue_order": int(row["queue_order"]),
                    "building_id": row["building_id"],
                    "aprime_order": int(row["aprime_order"]),
                    "target_role": row["target_role"],
                    "arm": row["arm"],
                    "replicate": row["replicate"],
                    "profile": "full",
                    "seed": int(row["seed"]),
                    "smoke_barrier_entry": stage_order == 0,
                    "reuse_completed_smoke": stage_order == 1 and index == 1,
                }
            )
    require_equal(len(entries), 22, "orchestrator stage entries")
    unique_keys = {
        (entry["building_id"], entry["arm"], entry["replicate"])
        for entry in entries
    }
    require_equal(len(unique_keys), 21, "orchestrator unique jobs")
    require_equal(
        [entry["building_id"] for entry in entries if entry["stage_key"] == "B_r1"],
        ["DEBY_LOD2_42364609", "DEBY_LOD2_42364659", "DEBY_LOD2_4908023"],
        "arm-B target order",
    )
    return entries


def append_event(
    config: Mapping[str, Any], event_type: str, detail: Mapping[str, Any]
) -> dict[str, Any]:
    root = repo_path(config["outputs"]["root"])
    events_path = repo_path(config["outputs"]["events"])
    sequence_path = repo_path(config["outputs"]["event_sequence"])
    lock_path = root / "event_sequence.lock"
    root.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+b") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        if sequence_path.is_file():
            sequence_payload = load_json(sequence_path)
            require_equal(sequence_payload.get("schema"), EVENT_SEQUENCE_SCHEMA, "event sequence schema")
            sequence = int(sequence_payload["last_sequence"]) + 1
        else:
            sequence = 1
        event = {
            "schema": "jointbuildgs.fusion_w1_aprime.unattended.event.v1",
            "sequence": sequence,
            "created_at": now_iso(),
            "event_type": event_type,
            "detail": dict(detail),
            "interpretation_or_verdict": None,
        }
        events_path.parent.mkdir(parents=True, exist_ok=True)
        with events_path.open("ab") as stream:
            stream.write(canonical_json(event))
            stream.flush()
            os.fsync(stream.fileno())
        atomic_json(
            sequence_path,
            {
                "schema": EVENT_SEQUENCE_SCHEMA,
                "last_sequence": sequence,
                "updated_at": event["created_at"],
                "events_path": relative(events_path),
                "events_sha256": sha256_file(events_path),
            },
        )
        fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
    return {"sequence": sequence, "events": file_record(events_path)}


def initialize(config: Mapping[str, Any], config_path: Path) -> dict[str, Any]:
    method = verify_git_runtime(config)
    locked = verify_locked_inputs(config)
    preflight = validate_preflight(config)
    entries = build_plan(config)
    plan_path = repo_path(config["outputs"]["plan"])
    expected = {
        "schema": PLAN_SCHEMA,
        "state": "ACTIVE",
        "run_id": config["run_id"],
        "task_id": config["task_id"],
        "config": file_record(config_path),
        "git_lock": method,
        "locked_inputs": locked,
        "preflight": preflight,
        "sequence_contract": config["sequence_contract"],
        "failure_contract": config["failure_contract"],
        "entries": entries,
        "stage_entries_n": len(entries),
        "unique_jobs_n": len(
            {(row["building_id"], row["arm"], row["replicate"]) for row in entries}
        ),
        "actual_training_started_at_publication": False,
        "interpretation_or_verdict": None,
    }
    if plan_path.exists() or plan_path.is_symlink():
        plan = load_json(plan_path)
        for key, value in expected.items():
            if key != "preflight":
                require_equal(plan.get(key), value, f"immutable queue plan {key}")
        require_equal(plan.get("preflight"), preflight, "queue plan current preflight")
        return {**plan, "publication_reused": True}
    expected["created_at"] = now_iso()
    exclusive_json(plan_path, expected)
    append_event(
        config,
        "QUEUE_INITIALIZED",
        {
            "plan": file_record(plan_path),
            "git_head": method["head"],
            "stage_entries_n": 22,
            "unique_jobs_n": 21,
            "preflight_status": "PASSED",
        },
    )
    publish_status(config)
    return expected


def load_plan(config: Mapping[str, Any]) -> dict[str, Any]:
    plan_path = repo_path(config["outputs"]["plan"])
    plan = load_json(plan_path)
    require_equal(plan.get("schema"), PLAN_SCHEMA, "queue plan schema")
    require_equal(plan.get("state"), "ACTIVE", "queue plan state")
    current = verify_git_runtime(config)
    require_equal(plan.get("git_lock"), current, "queue plan/current method")
    require_equal(plan.get("locked_inputs"), verify_locked_inputs(config), "queue locked inputs")
    require_equal(plan.get("preflight"), validate_preflight(config), "queue current preflight")
    require_equal(plan.get("entries"), build_plan(config), "queue plan entries")
    return plan


def entry_key(entry: Mapping[str, Any]) -> str:
    return (
        f"stage_{int(entry['stage_order']):02d}_{entry['stage_key']}/"
        f"entry_{int(entry['stage_entry_order']):02d}_{entry['building_id']}_"
        f"arm_{entry['arm']}_{entry['replicate']}"
    )


def stage_record_path(config: Mapping[str, Any], entry: Mapping[str, Any]) -> Path:
    return repo_path(config["outputs"]["stage_records"]) / f"{entry_key(entry)}.json"


def load_stage_record(
    config: Mapping[str, Any], entry: Mapping[str, Any]
) -> dict[str, Any] | None:
    path = stage_record_path(config, entry)
    if not path.exists() and not path.is_symlink():
        return None
    record = load_json(path)
    require_equal(record.get("schema"), STAGE_RECORD_SCHEMA, "stage record schema")
    require_equal(record.get("entry"), dict(entry), "stage record entry")
    if record.get("status") not in TERMINAL_STATES:
        raise UnattendedError(f"stage record is not terminal: {relative(path)}")
    return record


def training_job_path(
    config: Mapping[str, Any], entry: Mapping[str, Any]
) -> tuple[Any, dict[str, Any], Path]:
    module, training_config, _ = training_context(config)
    path = module.job_dir(
        REPO,
        training_config,
        entry["building_id"],
        entry["arm"],
        entry["replicate"],
        "full",
    )
    return module, training_config, path


def readout_job_path(
    config: Mapping[str, Any], entry: Mapping[str, Any]
) -> tuple[Any, dict[str, Any], Path]:
    module, readout_config, _ = readout_context(config)
    path = module.job_dir(
        readout_config, entry["building_id"], entry["arm"], entry["replicate"]
    )
    return module, readout_config, path


def verify_readout_complete(
    config: Mapping[str, Any], entry: Mapping[str, Any]
) -> dict[str, Any] | None:
    module, readout_config, job = readout_job_path(config, entry)
    path = job / "complete.json"
    if not path.exists() and not path.is_symlink():
        return None
    payload = load_json(path)
    require_equal(payload.get("schema"), module.COMPLETE_SCHEMA, "readout complete schema")
    require_equal(payload.get("state"), "COMPLETE", "readout complete state")
    require_equal(
        payload.get("identity"),
        {
            "building_id": entry["building_id"],
            "arm": entry["arm"],
            "replicate": entry["replicate"],
            "profile": "full",
        },
        "readout complete identity",
    )
    primary = payload.get("primary") or {}
    require_equal(primary.get("state"), "MEASURED", "primary readout state")
    require_equal(primary.get("eligible_for_preregistered_judgment"), True, "primary eligibility")
    verify_record(primary["receipt"], "primary score receipt")
    legacy = payload.get("legacy_alpha") or {}
    if legacy.get("state") not in {"MEASURED", "NOT_ASSEMBLED"}:
        raise UnattendedError("legacy alpha readout is not terminal")
    require_equal(legacy.get("eligible_for_preregistered_judgment"), False, "legacy eligibility")
    verify_record(legacy["receipt"], "legacy alpha score receipt")
    attempt_record = payload.get("attempt_materialization")
    if not isinstance(attempt_record, Mapping):
        raise UnattendedError("readout complete lacks attempt materialization")
    attempt_path = verify_record(attempt_record, "readout attempt materialization")
    attempt = load_json(attempt_path)
    require_equal(attempt.get("schema"), module.ATTEMPT_SCHEMA, "readout attempt schema")
    require_equal(attempt.get("state"), "STARTED", "readout attempt state")
    require_equal(attempt.get("identity"), payload["identity"], "readout attempt identity")
    require_equal(attempt.get("attempt"), payload.get("attempt"), "readout attempt number")
    require_equal(
        payload.get("successful_attempt"),
        relative(attempt_path.parent),
        "readout successful attempt path",
    )
    current_method = module.verify_git_runtime(readout_config)
    require_equal(attempt.get("git_lock"), current_method, "readout attempt/current HEAD")
    require_equal(
        attempt.get("locked_inputs"),
        module.verify_locked_inputs(readout_config),
        "readout attempt/current locked inputs",
    )
    return {"receipt": file_record(path), "payload": payload}


def verify_training_binding(
    module: Any,
    training_config: Mapping[str, Any],
    entry: Mapping[str, Any],
    materialized: Path,
    completed: Path | None,
) -> dict[str, Any]:
    materialization = load_json(materialized)
    require_equal(
        materialization.get("schema"),
        module.MATERIALIZATION_SCHEMA,
        "training materialization schema",
    )
    require_equal(materialization.get("status"), "PASSED", "training materialization status")
    for key, expected in (
        ("building_id", entry["building_id"]),
        ("arm", entry["arm"]),
        ("replicate", entry["replicate"]),
        ("profile", "full"),
    ):
        require_equal(materialization.get(key), expected, f"training materialization {key}")
    current_method = module.committed_method_gate(REPO, training_config)
    require_equal(materialization.get("git"), current_method, "training materialization/current HEAD")
    evidence = {
        "materialization": file_record(materialized),
        "method": current_method,
    }
    if completed is None:
        return evidence
    completion = load_json(completed)
    require_equal(completion.get("schema"), module.COMPLETED_SCHEMA, "training complete schema")
    require_equal(completion.get("status"), "COMPLETED", "training complete status")
    require_equal(completion.get("return_code"), 0, "training return code")
    for key, expected in (
        ("building_id", entry["building_id"]),
        ("arm", entry["arm"]),
        ("replicate", entry["replicate"]),
        ("profile", "full"),
    ):
        require_equal(completion.get(key), expected, f"training complete {key}")
    require_equal(
        completion.get("materialization"),
        file_record(materialized),
        "training complete/materialization binding",
    )
    started_path = verify_record(completion["started_receipt"], "training started receipt")
    started = load_json(started_path)
    require_equal(started.get("schema"), module.STARTED_SCHEMA, "training started schema")
    require_equal(started.get("status"), "STARTED", "training started status")
    require_equal(started.get("method"), current_method, "training started/current HEAD")
    for key, expected in (
        ("building_id", entry["building_id"]),
        ("arm", entry["arm"]),
        ("replicate", entry["replicate"]),
        ("profile", "full"),
    ):
        require_equal(started.get(key), expected, f"training started {key}")
    training_completion = completion.get("training_completion")
    if not isinstance(training_completion, Mapping):
        raise UnattendedError("training completion evidence is missing")
    require_equal(training_completion.get("profile"), "full", "training completion profile")
    require_equal(
        training_completion.get("completed_optimizer_updates"),
        30000,
        "training completed optimizer updates",
    )
    verify_record(training_completion["final_checkpoint"], "training final checkpoint")
    evidence.update(
        {
            "completed": file_record(completed),
            "started": file_record(started_path),
            "final_checkpoint": dict(training_completion["final_checkpoint"]),
        }
    )
    return evidence


def recursive_ledger(root: Path) -> list[dict[str, Any]]:
    if not root.is_dir() or root.is_symlink():
        raise UnattendedError(f"ledger root missing/not directory: {relative(root)}")
    records = []
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise UnattendedError(f"archived artifact symlink forbidden: {relative(path)}")
        if path.is_file():
            record = file_record(path)
            record["relative_to_root"] = str(path.relative_to(root))
            records.append(record)
    if not records:
        raise UnattendedError(f"refusing empty training archive: {relative(root)}")
    return records


def training_archive_root(
    config: Mapping[str, Any], entry: Mapping[str, Any]
) -> Path:
    return (
        repo_path(config["outputs"]["training_failure_archive"])
        / "by_building"
        / entry["building_id"]
        / f"arm_{entry['arm']}"
        / entry["replicate"]
    )


def training_archives(
    config: Mapping[str, Any], entry: Mapping[str, Any]
) -> list[dict[str, Any]]:
    root = training_archive_root(config, entry)
    if not root.is_dir():
        return []
    result = []
    for path in sorted(root.glob("attempt_[0-9][0-9][0-9]")):
        if not path.is_dir() or path.is_symlink():
            continue
        match = re.fullmatch(r"attempt_([0-9]{3})", path.name)
        if match is None:
            raise UnattendedError(f"invalid training archive directory: {relative(path)}")
        receipt_path = path / "archive_receipt.json"
        receipt = load_json(receipt_path)
        require_equal(receipt.get("schema"), TRAINING_ARCHIVE_SCHEMA, "training archive schema")
        require_equal(receipt.get("attempt"), int(match.group(1)), "training archive attempt")
        require_equal(receipt.get("identity"), {
            "building_id": entry["building_id"], "arm": entry["arm"],
            "replicate": entry["replicate"], "profile": "full",
        }, "training archive identity")
        for record in receipt.get("move_verification", []):
            verify_record(record, "archived training artifact")
        verify_record(receipt["archived_terminal_receipt"], "archived terminal receipt")
        result.append({"path": path, "receipt_path": receipt_path, "receipt": receipt})
    return result


def readout_failures(
    config: Mapping[str, Any], entry: Mapping[str, Any]
) -> list[dict[str, Any]]:
    module, _readout_config, job = readout_job_path(config, entry)
    attempts = job / "attempts"
    if not attempts.is_dir():
        return []
    result = []
    for path in sorted(attempts.glob("attempt_*")):
        failure_path = path / "failure.json"
        if not failure_path.is_file() or failure_path.is_symlink():
            continue
        payload = load_json(failure_path)
        require_equal(payload.get("schema"), module.FAILURE_SCHEMA, "readout failure schema")
        result.append({"receipt": file_record(failure_path), "payload": payload})
    return result


def action_failure_root(
    config: Mapping[str, Any], entry: Mapping[str, Any]
) -> Path:
    return repo_path(config["outputs"]["action_failures"]) / entry_key(entry)


def action_failures(
    config: Mapping[str, Any], entry: Mapping[str, Any]
) -> list[dict[str, Any]]:
    root = action_failure_root(config, entry)
    if not root.is_dir():
        return []
    result = []
    for path in sorted(root.glob("attempt_*.json")):
        payload = load_json(path)
        require_equal(payload.get("schema"), ACTION_FAILURE_SCHEMA, "action failure schema")
        require_equal(payload.get("entry"), dict(entry), "action failure entry")
        result.append({"receipt": file_record(path), "payload": payload})
    return result


def three_same_signature(
    failures: Sequence[Mapping[str, Any]], *, signature_field: str
) -> tuple[bool, str | None, str | None]:
    if len(failures) < 3:
        return False, None, None
    recent = [str(item["payload"].get(signature_field, "")) for item in failures[-3:]]
    if recent[0] and len(set(recent)) == 1:
        error_type = str(failures[-1]["payload"].get("error_type", "UnknownError"))
        return True, recent[0], error_type
    return False, None, None


def archived_three_same_signature(
    archives: Sequence[Mapping[str, Any]],
) -> tuple[bool, str | None, str | None]:
    values = [
        {
            "payload": {
                "error_signature": item["receipt"].get("error_signature"),
                "error_type": item["receipt"].get("error_type"),
            }
        }
        for item in archives
    ]
    return three_same_signature(values, signature_field="error_signature")


def terminal_skip_cause(
    config: Mapping[str, Any], entry: Mapping[str, Any]
) -> dict[str, Any] | None:
    archives = training_archives(config, entry)
    matched, signature, error_type = archived_three_same_signature(archives)
    if matched:
        return {
            "source": "training_failure_archive",
            "error_signature": signature,
            "error_type": error_type,
            "attempts": [file_record(item["receipt_path"]) for item in archives[-3:]],
        }
    failures = readout_failures(config, entry)
    matched, signature, error_type = three_same_signature(
        failures, signature_field="error_signature"
    )
    if matched:
        return {
            "source": "readout_failure_receipts",
            "error_signature": signature,
            "error_type": error_type,
            "attempts": [item["receipt"] for item in failures[-3:]],
        }
    failures = action_failures(config, entry)
    matched, signature, error_type = three_same_signature(
        failures, signature_field="error_signature"
    )
    if matched:
        return {
            "source": "orchestrator_action_failures",
            "error_signature": signature,
            "error_type": error_type,
            "attempts": [item["receipt"] for item in failures[-3:]],
        }
    return None


def inspect_pipeline(
    config: Mapping[str, Any], entry: Mapping[str, Any]
) -> dict[str, Any]:
    complete = verify_readout_complete(config, entry)
    if complete is not None:
        return {
            "state": "MEASURED",
            "action": "RECORD_MEASURED",
            "readout_complete": complete["receipt"],
        }
    pending = pending_training_archive(config, entry)
    if pending is not None:
        return {
            "state": "TRAINING_FAILED",
            "action": "ARCHIVE_TRAINING",
            "pending_archive": relative(pending),
        }
    module, training_config, training_job = training_job_path(config, entry)
    materialized = training_job / training_config["outputs"]["materialization_manifest"]
    started = training_job / training_config["outputs"]["started_receipt"]
    completed = training_job / training_config["outputs"]["completed_receipt"]
    failed = training_job / training_config["outputs"]["failed_receipt"]
    present = {
        "materialization": materialized.is_file(),
        "started": started.is_file(),
        "completed": completed.is_file(),
        "failed": failed.is_file(),
    }
    if present["completed"] and present["failed"]:
        return {
            "state": "TRAINING_FAILED",
            "action": "ARCHIVE_TRAINING",
            "training_job": relative(training_job),
            "receipt_presence": present,
            "orphan_reason": "conflicting_training_completion_and_failure_receipts",
        }
    if present["failed"]:
        return {
            "state": "TRAINING_FAILED",
            "action": "ARCHIVE_TRAINING",
            "training_job": relative(training_job),
            "receipt_presence": present,
        }
    if present["started"] and not present["completed"]:
        if training_foreground_lock_busy(training_config):
            return {
                "state": "TRAINING",
                "action": "WAIT_TRAINING",
                "training_job": relative(training_job),
                "receipt_presence": present,
            }
        return {
            "state": "TRAINING_FAILED",
            "action": "ARCHIVE_TRAINING",
            "training_job": relative(training_job),
            "receipt_presence": present,
            "orphan_reason": "started_without_terminal_receipt_and_no_live_training_lock",
        }
    if (
        not present["completed"]
        and not present["materialization"]
        and training_job.exists()
        and any(training_job.iterdir())
    ):
        return {
            "state": "TRAINING_FAILED",
            "action": "ARCHIVE_TRAINING",
            "training_job": relative(training_job),
            "receipt_presence": present,
            "orphan_reason": "nonempty_canonical_training_dir_without_materialization",
        }
    if present["completed"] and not present["materialization"]:
        return {
            "state": "TRAINING_FAILED",
            "action": "ARCHIVE_TRAINING",
            "training_job": relative(training_job),
            "receipt_presence": present,
            "orphan_reason": "training_completion_without_materialization",
        }
    binding = None
    if present["materialization"]:
        try:
            binding = verify_training_binding(
                module,
                training_config,
                entry,
                materialized,
                completed if present["completed"] else None,
            )
        except Exception as exc:
            return {
                "state": "TRAINING_FAILED",
                "action": "ARCHIVE_TRAINING",
                "training_job": relative(training_job),
                "receipt_presence": present,
                "orphan_reason": "training_binding_does_not_match_runtime_head",
                "binding_error_type": type(exc).__name__,
                "binding_error": str(exc),
            }
    skip = terminal_skip_cause(config, entry)
    if skip is not None:
        return {"state": "SKIPPED", "action": "RECORD_SKIPPED", "skip": skip}
    if present["completed"]:
        failures = readout_failures(config, entry)
        if readout_driver_lock_busy(config):
            return {
                "state": "READOUT" if failures else "TRAINED",
                "action": "WAIT_READOUT",
                "training_complete": file_record(completed),
                "training_binding": binding,
                "readout_failure_attempts": len(failures),
            }
        return {
            "state": "READOUT_FAILED" if failures else "TRAINED",
            "action": "RUN_READOUT",
            "training_complete": file_record(completed),
            "training_binding": binding,
            "readout_failure_attempts": len(failures),
        }
    if present["materialization"]:
        return {
            "state": "MATERIALIZED",
            "action": "LAUNCH_TRAINING",
            "materialization": file_record(materialized),
            "training_binding": binding,
        }
    return {"state": "MISSING", "action": "MATERIALIZE_TRAINING"}


def lock_is_busy(path: Path) -> bool:
    """Return whether another process owns an advisory exclusive lock."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as stream:
        try:
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return True
        fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
    return False


def training_foreground_lock_busy(training_config: Mapping[str, Any]) -> bool:
    value = training_config["outputs"].get("foreground_lock")
    if not isinstance(value, str) or not value:
        raise UnattendedError("training foreground lock is absent from config")
    return lock_is_busy(repo_path(value))


def readout_driver_lock_busy(config: Mapping[str, Any]) -> bool:
    _module, readout_config, _path = readout_context(config)
    root = repo_path(readout_config["outputs"]["root"])
    return lock_is_busy(root / "driver.lock")


def stable_failure_signature(
    *, action: str, error_type: str, reason: str, return_code: int | None
) -> str:
    normalized = "\0".join(
        (action.strip(), error_type.strip(), reason.strip(), str(return_code))
    )
    return sha256_bytes(normalized.encode("utf-8"))


def pending_training_archive(
    config: Mapping[str, Any], entry: Mapping[str, Any]
) -> Path | None:
    root = training_archive_root(config, entry)
    if not root.is_dir():
        return None
    candidates = sorted(root.glob("attempt_*.incomplete"))
    if len(candidates) > 1:
        raise UnattendedError(
            f"multiple incomplete training archives: {relative(root)}"
        )
    if not candidates:
        return None
    path = candidates[0]
    if not path.is_dir() or path.is_symlink() or re.fullmatch(
        r"attempt_[0-9]{3}\.incomplete", path.name
    ) is None:
        raise UnattendedError(f"invalid incomplete archive: {relative(path)}")
    return path


def entry_for(
    plan: Mapping[str, Any], stage_key: str, stage_entry_order: int
) -> dict[str, Any]:
    matches = [
        dict(entry)
        for entry in plan["entries"]
        if entry["stage_key"] == stage_key
        and int(entry["stage_entry_order"]) == stage_entry_order
    ]
    if len(matches) != 1:
        raise UnattendedError(
            f"queue entry resolution failed: {stage_key}/{stage_entry_order}"
        )
    return matches[0]


def stage_stop_path(config: Mapping[str, Any]) -> Path:
    return repo_path(config["outputs"]["stage_stop"])


def complete_path(config: Mapping[str, Any]) -> Path:
    return repo_path(config["outputs"]["complete"])


def consecutive_skip_stop(
    records: Sequence[tuple[Mapping[str, Any], Mapping[str, Any]]],
) -> dict[str, Any] | None:
    if len(records) < 3:
        return None
    recent = records[-3:]
    if any(record.get("status") != "SKIPPED" for _entry, record in recent):
        return None
    error_types = [str(record.get("error_type", "")) for _entry, record in recent]
    if not error_types[0] or len(set(error_types)) != 1:
        return None
    return {
        "reason_code": "SAME_ERROR_TYPE_THREE_CONSECUTIVE_BUILDINGS",
        "error_type": error_types[0],
        "consecutive_buildings": [entry["building_id"] for entry, _record in recent],
    }


def next_action(config: Mapping[str, Any]) -> dict[str, Any]:
    plan = load_plan(config)
    completed = complete_path(config)
    if completed.exists() or completed.is_symlink():
        payload = load_json(completed)
        require_equal(payload.get("schema"), COMPLETE_SCHEMA, "queue complete schema")
        return {"action": "DONE", "state": payload.get("state"), "entry": None}
    stop_path = stage_stop_path(config)
    if stop_path.exists() or stop_path.is_symlink():
        stop = load_json(stop_path)
        require_equal(stop.get("schema"), STAGE_STOP_SCHEMA, "stage-stop schema")
        return {
            "action": "FINALIZE_QUEUE",
            "state": "STAGE_STOPPED",
            "entry": None,
            "stage_stop": file_record(stop_path),
        }

    by_stage: dict[int, list[dict[str, Any]]] = {}
    for entry in plan["entries"]:
        by_stage.setdefault(int(entry["stage_order"]), []).append(dict(entry))
    for stage_order in sorted(by_stage):
        entries = by_stage[stage_order]
        terminal: list[tuple[dict[str, Any], dict[str, Any]]] = []
        for entry in entries:
            record = load_stage_record(config, entry)
            if record is None:
                break
            terminal.append((entry, record))

        if stage_order == 0 and terminal and terminal[-1][1]["status"] == "SKIPPED":
            return {
                "action": "STOP_STAGE",
                "state": "SMOKE_BARRIER_SKIPPED",
                "entry": terminal[-1][0],
                "stop": {
                    "reason_code": "SMOKE_BARRIER_NOT_MEASURED",
                    "error_type": terminal[-1][1].get("error_type"),
                    "consecutive_buildings": [terminal[-1][0]["building_id"]],
                    "stage_record_receipts": [
                        file_record(stage_record_path(config, terminal[-1][0]))
                    ],
                },
            }

        consecutive = consecutive_skip_stop(terminal)
        if consecutive is not None:
            consecutive["stage_record_receipts"] = [
                file_record(stage_record_path(config, entry))
                for entry, _record in terminal[-3:]
            ]
            return {
                "action": "STOP_STAGE",
                "state": "THREE_CONSECUTIVE_BUILDING_SKIPS",
                "entry": terminal[-1][0],
                "stop": consecutive,
            }

        if len(terminal) < len(entries):
            entry = entries[len(terminal)]
            pipeline = inspect_pipeline(config, entry)
            return {
                "action": pipeline["action"],
                "state": pipeline["state"],
                "entry": entry,
                "pipeline": pipeline,
            }

    return {
        "action": "FINALIZE_QUEUE",
        "state": "ALL_ENTRIES_TERMINAL",
        "entry": None,
    }


def _archive_attempt_number(
    config: Mapping[str, Any], entry: Mapping[str, Any]
) -> int:
    archives = training_archives(config, entry)
    observed = [int(item["receipt"]["attempt"]) for item in archives]
    require_equal(observed, list(range(1, len(observed) + 1)), "archive attempt sequence")
    return len(observed) + 1


def _projected_file_record(path: Path, projected: Path) -> dict[str, Any]:
    record = file_record(path)
    record["path"] = relative(projected)
    return record


def _training_failure_evidence(
    module: Any,
    training_config: Mapping[str, Any],
    training_job: Path,
    entry: Mapping[str, Any],
) -> tuple[dict[str, Any], Path]:
    failed_path = training_job / training_config["outputs"]["failed_receipt"]
    if failed_path.is_file() and not failed_path.is_symlink():
        payload = load_json(failed_path)
        require_equal(payload.get("schema"), module.FAILED_SCHEMA, "training failure schema")
        require_equal(payload.get("status"), "FAILED", "training failure status")
        for key, expected in (
            ("building_id", entry["building_id"]),
            ("arm", entry["arm"]),
            ("replicate", entry["replicate"]),
            ("profile", "full"),
        ):
            require_equal(payload.get(key), expected, f"training failure {key}")
        return payload, failed_path

    started_path = training_job / training_config["outputs"]["started_receipt"]
    completed_path = training_job / training_config["outputs"]["completed_receipt"]
    materialization_path = (
        training_job / training_config["outputs"]["materialization_manifest"]
    )
    if completed_path.is_file():
        reason = "training_receipts_or_materialization_do_not_match_runtime_head"
    elif started_path.is_file():
        reason = "started_without_terminal_receipt_and_no_live_training_lock"
    else:
        reason = "nonempty_canonical_training_dir_without_materialization"
    orphan_path = training_job / "orchestrator_orphan_failure.json"
    identity = {
        "building_id": entry["building_id"],
        "arm": entry["arm"],
        "replicate": entry["replicate"],
        "profile": "full",
    }
    if not orphan_path.exists() and not orphan_path.is_symlink():
        payload = {
            "schema": ORPHAN_FAILURE_SCHEMA,
            "status": "FAILED",
            "created_at": now_iso(),
            "identity": identity,
            "error_type": "OrphanedTrainingAttempt",
            "reason": reason,
            "return_code": None,
            "started_receipt": file_record(started_path) if started_path.is_file() else None,
            "materialization": (
                file_record(materialization_path) if materialization_path.is_file() else None
            ),
            "partial_outputs_preserved": True,
            "interpretation_or_verdict": None,
        }
        exclusive_json(orphan_path, payload)
    else:
        payload = load_json(orphan_path)
        require_equal(payload.get("schema"), ORPHAN_FAILURE_SCHEMA, "orphan failure schema")
        require_equal(payload.get("identity"), identity, "orphan failure identity")
    return payload, orphan_path


def archive_training_failure(
    config: Mapping[str, Any], entry: Mapping[str, Any]
) -> dict[str, Any]:
    recommended = next_action(config)
    require_equal(recommended.get("action"), "ARCHIVE_TRAINING", "archive recommended action")
    require_equal(recommended.get("entry"), dict(entry), "archive recommended entry")
    module, training_config, training_job = training_job_path(config, entry)
    root = training_archive_root(config, entry)
    root.mkdir(parents=True, exist_ok=True)
    staging = pending_training_archive(config, entry)

    if staging is None:
        if not training_job.is_dir() or training_job.is_symlink() or not any(training_job.iterdir()):
            raise UnattendedError(
                f"canonical failed training directory is absent/empty: {relative(training_job)}"
            )
        attempt_number = _archive_attempt_number(config, entry)
        final = root / f"attempt_{attempt_number:03d}"
        staging = root / f"attempt_{attempt_number:03d}.incomplete"
        if final.exists() or final.is_symlink() or staging.exists() or staging.is_symlink():
            raise UnattendedError(f"archive destination already exists: {relative(final)}")
        staging.mkdir()
        failure, terminal_path = _training_failure_evidence(
            module, training_config, training_job, entry
        )
        ledger = recursive_ledger(training_job)
        ledger_path = staging / "pre_move_ledger.json"
        exclusive_json(
            ledger_path,
            {
                "schema": TRAINING_ARCHIVE_LEDGER_SCHEMA,
                "created_at": now_iso(),
                "source_path": relative(training_job),
                "artifacts": ledger,
                "artifact_count": len(ledger),
            },
        )
        error_type = str(failure.get("error_type", "TrainingFailure"))
        reason = str(failure.get("reason", "training attempt failed"))
        return_code = failure.get("return_code")
        intent = {
            "schema": TRAINING_ARCHIVE_INTENT_SCHEMA,
            "created_at": now_iso(),
            "attempt": attempt_number,
            "identity": {
                "building_id": entry["building_id"],
                "arm": entry["arm"],
                "replicate": entry["replicate"],
                "profile": "full",
            },
            "source_path": relative(training_job),
            "final_destination": relative(final),
            "pre_move_ledger": _projected_file_record(
                ledger_path, final / "pre_move_ledger.json"
            ),
            "original_terminal_receipt": file_record(terminal_path),
            "original_terminal_relative_to_job": str(
                terminal_path.relative_to(training_job)
            ),
            "error_type": error_type,
            "reason": reason,
            "return_code": return_code,
            "error_signature": stable_failure_signature(
                action="training",
                error_type=error_type,
                reason=reason,
                return_code=return_code,
            ),
            "partial_artifacts_preserved": True,
            "interpretation_or_verdict": None,
        }
        exclusive_json(staging / "move_intent.json", intent)
    else:
        intent = load_json(staging / "move_intent.json")
        require_equal(intent.get("schema"), TRAINING_ARCHIVE_INTENT_SCHEMA, "archive intent schema")
        require_equal(intent.get("identity"), {
            "building_id": entry["building_id"],
            "arm": entry["arm"],
            "replicate": entry["replicate"],
            "profile": "full",
        }, "archive intent identity")
        attempt_number = int(intent["attempt"])
        final = root / f"attempt_{attempt_number:03d}"
        require_equal(intent.get("final_destination"), relative(final), "archive final destination")

    intent = load_json(staging / "move_intent.json")
    ledger_payload = load_json(staging / "pre_move_ledger.json")
    require_equal(ledger_payload.get("schema"), TRAINING_ARCHIVE_LEDGER_SCHEMA, "archive ledger schema")
    nested = staging / "training_job"
    if nested.exists() or nested.is_symlink():
        if training_job.exists() or training_job.is_symlink():
            raise UnattendedError("both canonical and staged training directories exist")
    else:
        if not training_job.is_dir() or training_job.is_symlink():
            raise UnattendedError("neither canonical nor staged training directory exists")
        os.replace(training_job, nested)
        fsync_directory(training_job.parent)
        fsync_directory(staging)

    pre_move = ledger_payload.get("artifacts")
    if not isinstance(pre_move, list) or not pre_move:
        raise UnattendedError("pre-move ledger is empty")
    final_nested = final / "training_job"
    verification = []
    for original in pre_move:
        relative_name = original.get("relative_to_root")
        if not isinstance(relative_name, str) or not relative_name:
            raise UnattendedError("archive ledger relative path is invalid")
        staged_path = nested / relative_name
        observed = _projected_file_record(staged_path, final_nested / relative_name)
        require_equal(observed["sha256"], original.get("sha256"), "moved artifact SHA")
        require_equal(observed["bytes"], original.get("bytes"), "moved artifact bytes")
        verification.append(observed)
    terminal_relative = intent.get("original_terminal_relative_to_job")
    if not isinstance(terminal_relative, str) or not terminal_relative:
        raise UnattendedError("archive terminal relative path is missing")
    archived_terminal = _projected_file_record(
        nested / terminal_relative, final_nested / terminal_relative
    )
    require_equal(
        archived_terminal["sha256"],
        intent["original_terminal_receipt"]["sha256"],
        "archived terminal receipt SHA",
    )
    receipt_path = staging / "archive_receipt.json"
    projected_receipt_path = final / "archive_receipt.json"
    if not receipt_path.exists() and not receipt_path.is_symlink():
        payload = {
            "schema": TRAINING_ARCHIVE_SCHEMA,
            "state": "ARCHIVED",
            "created_at": now_iso(),
            "attempt": int(intent["attempt"]),
            "identity": dict(intent["identity"]),
            "source_path": intent["source_path"],
            "destination_path": relative(final),
            "original_terminal_receipt": intent["original_terminal_receipt"],
            "archived_terminal_receipt": archived_terminal,
            "pre_move_ledger": _projected_file_record(
                staging / "pre_move_ledger.json", final / "pre_move_ledger.json"
            ),
            "move_verification": verification,
            "artifact_count": len(verification),
            "error_type": intent["error_type"],
            "reason": intent["reason"],
            "return_code": intent.get("return_code"),
            "error_signature": intent["error_signature"],
            "git_head": git("rev-parse", "HEAD").stdout.strip(),
            "canonical_path_absent_after_move": True,
            "partial_artifacts_preserved": True,
            "append_only_archive": True,
            "interpretation_or_verdict": None,
        }
        exclusive_json(receipt_path, payload)
    else:
        payload = load_json(receipt_path)
        require_equal(payload.get("schema"), TRAINING_ARCHIVE_SCHEMA, "archive receipt schema")
        require_equal(payload.get("move_verification"), verification, "archive move verification")
    if final.exists() or final.is_symlink():
        raise UnattendedError(f"final archive already exists during staging: {relative(final)}")
    os.replace(staging, final)
    fsync_directory(root)
    for record in verification:
        verify_record(record, "final archived training artifact")
    if training_job.exists() or training_job.is_symlink():
        raise UnattendedError("canonical training path remained after archive move")
    result = load_json(projected_receipt_path)
    append_event(
        config,
        "TRAINING_FAILURE_ARCHIVED",
        {
            "entry": dict(entry),
            "archive_receipt": file_record(projected_receipt_path),
            "attempt": int(result["attempt"]),
            "error_type": result["error_type"],
            "error_signature": result["error_signature"],
        },
    )
    publish_status(config)
    return result


def record_action_failure(
    config: Mapping[str, Any],
    entry: Mapping[str, Any],
    *,
    action: str,
    error_type: str,
    message: str,
    return_code: int | None,
    log_path: Path | None,
) -> dict[str, Any]:
    if load_stage_record(config, entry) is not None:
        raise UnattendedError("cannot attach action failure to terminal stage entry")
    if action not in {
        "MATERIALIZE_TRAINING",
        "LAUNCH_TRAINING",
        "RUN_READOUT",
        "ARCHIVE_TRAINING",
    }:
        raise UnattendedError(f"unsupported failing action: {action}")
    root = action_failure_root(config, entry)
    root.mkdir(parents=True, exist_ok=True)
    existing = action_failures(config, entry)
    attempt = len(existing) + 1
    path = root / f"attempt_{attempt:03d}.json"
    log = file_record(log_path) if log_path is not None else None
    signature = stable_failure_signature(
        action=action,
        error_type=error_type,
        reason=message,
        return_code=return_code,
    )
    payload = {
        "schema": ACTION_FAILURE_SCHEMA,
        "state": "FAILED",
        "created_at": now_iso(),
        "attempt": attempt,
        "entry": dict(entry),
        "action": action,
        "error_type": error_type,
        "message": message,
        "return_code": return_code,
        "error_signature": signature,
        "error_signature_basis": {
            "action": action,
            "error_type": error_type,
            "message": message,
            "return_code": return_code,
            "log_sha256": log["sha256"] if log is not None else None,
        },
        "log": log,
        "partial_artifacts_preserved": True,
        "interpretation_or_verdict": None,
    }
    exclusive_json(path, payload)
    append_event(
        config,
        "ACTION_FAILED",
        {
            "entry": dict(entry),
            "action": action,
            "failure_receipt": file_record(path),
            "error_type": error_type,
            "error_signature": signature,
            "return_code": return_code,
        },
    )
    publish_status(config)
    return payload


def record_action_success(
    config: Mapping[str, Any],
    entry: Mapping[str, Any],
    *,
    action: str,
    log_path: Path | None,
) -> dict[str, Any]:
    if action not in {
        "MATERIALIZE_TRAINING",
        "LAUNCH_TRAINING",
        "RUN_READOUT",
        "ARCHIVE_TRAINING",
    }:
        raise UnattendedError(f"unsupported successful action: {action}")
    log = file_record(log_path) if log_path is not None else None
    event = append_event(
        config,
        "ACTION_SUCCEEDED",
        {"entry": dict(entry), "action": action, "log": log},
    )
    publish_status(config)
    return {"state": "SUCCEEDED", "action": action, "event": event, "log": log}


def record_terminal(
    config: Mapping[str, Any], entry: Mapping[str, Any]
) -> dict[str, Any]:
    recommended = next_action(config)
    if recommended.get("action") not in {"RECORD_MEASURED", "RECORD_SKIPPED"}:
        raise UnattendedError(
            f"entry is not ready for terminal publication: {recommended.get('action')}"
        )
    require_equal(recommended.get("entry"), dict(entry), "terminal recommended entry")
    status = "MEASURED" if recommended["action"] == "RECORD_MEASURED" else "SKIPPED"
    pipeline = recommended["pipeline"]
    source_receipts: list[dict[str, Any]] = []
    error_type = None
    error_signature = None
    smoke_reuse = None
    if status == "MEASURED":
        receipt = dict(pipeline["readout_complete"])
        verify_record(receipt, "measured readout complete")
        source_receipts.append(receipt)
        if entry.get("reuse_completed_smoke"):
            plan = load_plan(config)
            smoke_entry = entry_for(plan, "smoke_barrier", 1)
            smoke_record = load_stage_record(config, smoke_entry)
            if smoke_record is None:
                raise UnattendedError("A-prime r1 reuse precedes smoke terminal record")
            require_equal(smoke_record.get("status"), "MEASURED", "smoke reuse status")
            require_equal(
                smoke_record.get("source_receipts"),
                source_receipts,
                "smoke reuse readout receipt",
            )
            smoke_path = stage_record_path(config, smoke_entry)
            smoke_reuse = {
                "reused": True,
                "smoke_stage_record": file_record(smoke_path),
                "identical_readout_complete_receipt": receipt,
            }
    else:
        skip = pipeline["skip"]
        source_receipts = [dict(record) for record in skip["attempts"]]
        for record in source_receipts:
            verify_record(record, "skip attempt receipt")
        error_type = skip["error_type"]
        error_signature = skip["error_signature"]
    payload = {
        "schema": STAGE_RECORD_SCHEMA,
        "status": status,
        "created_at": now_iso(),
        "entry": dict(entry),
        "source": "readout_complete" if status == "MEASURED" else pipeline["skip"]["source"],
        "source_receipts": source_receipts,
        "error_type": error_type,
        "error_signature": error_signature,
        "same_signature_attempts": len(source_receipts) if status == "SKIPPED" else None,
        "smoke_reuse": smoke_reuse,
        "partial_results_reviewable": True,
        "interpretation_or_verdict": None,
    }
    path = stage_record_path(config, entry)
    exclusive_json(path, payload)
    append_event(
        config,
        f"ENTRY_{status}",
        {
            "entry": dict(entry),
            "stage_record": file_record(path),
            "error_type": error_type,
            "error_signature": error_signature,
            "smoke_reuse": smoke_reuse,
        },
    )
    publish_status(config)
    return payload


def _outcome_status(pipeline_state: str) -> str:
    if pipeline_state in TERMINAL_STATES:
        return pipeline_state
    if pipeline_state.endswith("_FAILED") or pipeline_state == "FAILED":
        return "FAILED"
    return "MISSING"


def publish_status(config: Mapping[str, Any]) -> dict[str, Any]:
    complete = complete_path(config)
    status_path = repo_path(config["outputs"]["status_json"])
    if complete.is_file() and status_path.is_file():
        complete_payload = load_json(complete)
        status_payload = load_json(status_path)
        require_equal(complete_payload.get("schema"), COMPLETE_SCHEMA, "status queue complete schema")
        require_equal(status_payload.get("schema"), STATUS_SCHEMA, "existing status schema")
        require_equal(
            complete_payload.get("status_json"),
            file_record(status_path),
            "complete/status immutable binding",
        )
        return {**status_payload, "publication_reused": True}
    plan_path = repo_path(config["outputs"]["plan"])
    plan = load_json(plan_path)
    require_equal(plan.get("schema"), PLAN_SCHEMA, "status plan schema")
    rows = []
    for entry in plan["entries"]:
        record = load_stage_record(config, entry)
        if record is not None:
            pipeline_state = str(record["status"])
            next_step = "NONE"
            error_type = record.get("error_type")
            terminal_receipt = file_record(stage_record_path(config, entry))
            inspection_error = None
        else:
            try:
                pipeline = inspect_pipeline(config, entry)
                pipeline_state = str(pipeline["state"])
                next_step = str(pipeline["action"])
                error_type = (
                    (pipeline.get("skip") or {}).get("error_type")
                    if isinstance(pipeline.get("skip"), dict)
                    else None
                )
                inspection_error = None
            except Exception as exc:
                pipeline_state = "FAILED"
                next_step = "INSPECTION_REQUIRED"
                error_type = type(exc).__name__
                inspection_error = str(exc)
            terminal_receipt = None
        rows.append(
            {
                **dict(entry),
                "outcome_status": _outcome_status(pipeline_state),
                "pipeline_state": pipeline_state,
                "next_action": next_step,
                "error_type": error_type,
                "inspection_error": inspection_error,
                "terminal_receipt_path": (
                    terminal_receipt["path"] if terminal_receipt is not None else ""
                ),
                "terminal_receipt_sha256": (
                    terminal_receipt["sha256"] if terminal_receipt is not None else ""
                ),
            }
        )
    fields = (
        "global_entry_order",
        "stage_order",
        "stage_key",
        "stage_entry_order",
        "building_id",
        "arm",
        "replicate",
        "profile",
        "outcome_status",
        "pipeline_state",
        "next_action",
        "error_type",
        "inspection_error",
        "terminal_receipt_path",
        "terminal_receipt_sha256",
    )
    csv_path = repo_path(config["outputs"]["status_csv"])
    atomic_csv(csv_path, rows, fields)
    counts = {
        value: sum(row["outcome_status"] == value for row in rows)
        for value in ("MEASURED", "FAILED", "SKIPPED", "MISSING")
    }
    stop = stage_stop_path(config)
    payload = {
        "schema": STATUS_SCHEMA,
        "state": "SNAPSHOT",
        "created_at": now_iso(),
        "plan": file_record(plan_path),
        "rows": rows,
        "counts": counts,
        "stage_stop": file_record(stop) if stop.is_file() else None,
        "queue_complete_exists": complete.is_file(),
        "status_csv": file_record(csv_path),
        "interpretation_or_verdict": None,
    }
    atomic_json(status_path, payload)
    return payload


def stop_stage(config: Mapping[str, Any]) -> dict[str, Any]:
    recommended = next_action(config)
    require_equal(recommended.get("action"), "STOP_STAGE", "stage-stop recommended action")
    cause = dict(recommended["stop"])
    if cause["reason_code"] == "SAME_ERROR_TYPE_THREE_CONSECUTIVE_BUILDINGS":
        state = config["status_contract"]["stage_stop_state"]
    else:
        state = "STOPPED_SMOKE_BARRIER_NOT_MEASURED"
    payload = {
        "schema": STAGE_STOP_SCHEMA,
        "state": state,
        "created_at": now_iso(),
        "stage_order": recommended["entry"]["stage_order"],
        "stage_key": recommended["entry"]["stage_key"],
        "last_entry": dict(recommended["entry"]),
        "cause": cause,
        "later_stages_not_started_by_orchestrator": True,
        "partial_results_reviewable": True,
        "interpretation_or_verdict": None,
    }
    path = stage_stop_path(config)
    exclusive_json(path, payload)
    append_event(
        config,
        "STAGE_STOPPED",
        {
            "stage_stop": file_record(path),
            "stage_key": payload["stage_key"],
            "state": state,
            "reason_code": cause["reason_code"],
            "error_type": cause.get("error_type"),
        },
    )
    publish_status(config)
    return payload


def _unique_status_counts(rows: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    states: dict[tuple[str, str, str], str] = {}
    for row in rows:
        key = (str(row["building_id"]), str(row["arm"]), str(row["replicate"]))
        state = str(row["outcome_status"])
        if key in states and states[key] != state:
            raise UnattendedError(f"duplicate smoke status diverged for {key}")
        states[key] = state
    return {
        value: sum(state == value for state in states.values())
        for value in ("MEASURED", "FAILED", "SKIPPED", "MISSING")
    }


def finalize_queue(config: Mapping[str, Any]) -> dict[str, Any]:
    path = complete_path(config)
    if path.exists() or path.is_symlink():
        payload = load_json(path)
        require_equal(payload.get("schema"), COMPLETE_SCHEMA, "existing queue complete schema")
        return {**payload, "publication_reused": True}
    recommended = next_action(config)
    require_equal(recommended.get("action"), "FINALIZE_QUEUE", "queue finalize action")
    plan = load_plan(config)
    stop_path = stage_stop_path(config)
    stop = load_json(stop_path) if stop_path.is_file() else None
    records = []
    for entry in plan["entries"]:
        record = load_stage_record(config, entry)
        if record is not None:
            records.append(
                {
                    "entry": dict(entry),
                    "status": record["status"],
                    "receipt": file_record(stage_record_path(config, entry)),
                }
            )
    if stop is None:
        require_equal(len(records), len(plan["entries"]), "terminal stage-record count")
        state = "COMPLETE"
    else:
        require_equal(stop.get("schema"), STAGE_STOP_SCHEMA, "final stage-stop schema")
        state = str(stop["state"])
    append_event(
        config,
        "QUEUE_TERMINAL_SNAPSHOT",
        {
            "state": state,
            "terminal_stage_records_n": len(records),
            "stage_stop": file_record(stop_path) if stop is not None else None,
        },
    )
    status = publish_status(config)
    events = repo_path(config["outputs"]["events"])
    sequence = repo_path(config["outputs"]["event_sequence"])
    payload = {
        "schema": COMPLETE_SCHEMA,
        "state": state,
        "created_at": now_iso(),
        "run_id": config["run_id"],
        "task_id": config["task_id"],
        "git_head": git("rev-parse", "HEAD").stdout.strip(),
        "plan": file_record(repo_path(config["outputs"]["plan"])),
        "stage_stop": file_record(stop_path) if stop is not None else None,
        "stage_records": records,
        "stage_entry_counts": dict(status["counts"]),
        "unique_job_counts": _unique_status_counts(status["rows"]),
        "stage_entries_n": len(plan["entries"]),
        "unique_jobs_n": len(
            {
                (entry["building_id"], entry["arm"], entry["replicate"])
                for entry in plan["entries"]
            }
        ),
        "status_json": file_record(repo_path(config["outputs"]["status_json"])),
        "status_csv": file_record(repo_path(config["outputs"]["status_csv"])),
        "events": file_record(events),
        "event_sequence": file_record(sequence),
        "partial_results_reviewable": True,
        "root_complete_receipt_written_last": True,
        "interpretation_or_verdict": None,
    }
    exclusive_json(path, payload)
    return payload


def next_tsv(payload: Mapping[str, Any]) -> str:
    entry = payload.get("entry") or {}
    values = (
        payload.get("action", "-"),
        entry.get("stage_key", "-"),
        entry.get("stage_order", "-"),
        entry.get("stage_entry_order", "-"),
        entry.get("building_id", "-"),
        entry.get("arm", "-"),
        entry.get("replicate", "-"),
        payload.get("state", "-"),
    )
    return "\t".join(str(value) for value in values)


def add_entry_arguments(subparser: argparse.ArgumentParser) -> None:
    subparser.add_argument("--stage-key", required=True)
    subparser.add_argument("--stage-entry-order", type=int, required=True)


def parser() -> argparse.ArgumentParser:
    argument_parser = argparse.ArgumentParser(description=__doc__)
    argument_parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    commands = argument_parser.add_subparsers(dest="command", required=True)
    commands.add_parser("initialize")
    next_parser = commands.add_parser("next")
    next_parser.add_argument("--format", choices=("json", "tsv"), default="json")
    for name in ("archive-training", "record-terminal"):
        add_entry_arguments(commands.add_parser(name))
    failure = commands.add_parser("record-action-failure")
    add_entry_arguments(failure)
    failure.add_argument("--action", required=True)
    failure.add_argument("--error-type", required=True)
    failure.add_argument("--message", required=True)
    failure.add_argument("--return-code", type=int)
    failure.add_argument("--log-path", type=Path)
    success = commands.add_parser("record-action-success")
    add_entry_arguments(success)
    success.add_argument("--action", required=True)
    success.add_argument("--log-path", type=Path)
    commands.add_parser("stop-stage")
    commands.add_parser("snapshot")
    commands.add_parser("finalize")
    return argument_parser


def print_json(payload: Any) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))


def main(argv: Sequence[str] | None = None) -> int:
    args = parser().parse_args(argv)
    config_path = repo_path(args.config)
    config = load_config(config_path)
    entry = None
    if hasattr(args, "stage_key"):
        entry = entry_for(load_plan(config), args.stage_key, args.stage_entry_order)
    if args.command == "initialize":
        result = initialize(config, config_path)
    elif args.command == "next":
        result = next_action(config)
        if args.format == "tsv":
            print(next_tsv(result))
            return 0
    elif args.command == "archive-training":
        result = archive_training_failure(config, entry)
    elif args.command == "record-terminal":
        result = record_terminal(config, entry)
    elif args.command == "record-action-failure":
        result = record_action_failure(
            config,
            entry,
            action=args.action,
            error_type=args.error_type,
            message=args.message,
            return_code=args.return_code,
            log_path=repo_path(args.log_path) if args.log_path is not None else None,
        )
    elif args.command == "record-action-success":
        result = record_action_success(
            config,
            entry,
            action=args.action,
            log_path=repo_path(args.log_path) if args.log_path is not None else None,
        )
    elif args.command == "stop-stage":
        result = stop_stage(config)
    elif args.command == "snapshot":
        load_plan(config)
        result = publish_status(config)
    elif args.command == "finalize":
        result = finalize_queue(config)
    else:  # pragma: no cover - argparse guards this branch.
        raise UnattendedError(f"unsupported command: {args.command}")
    print_json(result)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except UnattendedError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2)
