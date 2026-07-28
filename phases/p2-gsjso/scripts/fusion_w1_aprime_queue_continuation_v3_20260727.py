#!/usr/bin/env python3
"""Two-lane A-prime continuation with pair barriers and per-job terminals.

The scientific training/readout implementations remain the locked A-prime
implementations.  This controller changes only host orchestration: each
within-stage pair may train on physical GPU0/GPU1, both training lanes must be
terminal before globally serial readout starts, and a job is terminal only
after training, quantitative readout, and the v3 qualitative receipt exist.
It never writes the source v2 namespace.
"""
from __future__ import annotations

import argparse
import copy
from contextlib import contextmanager
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
import shutil
import subprocess
import sys
import time
from typing import Any, Mapping, Sequence


REPO = Path(__file__).resolve().parents[3]
CONTAINER_REPO = Path("/workspace/JointBuildGS")
DEFAULT_CONFIG = REPO / "phases/p2-gsjso/configs/fusion_w1_aprime_queue_continuation_v3_20260727.json"
CONFIG_SCHEMA = "jointbuildgs.fusion_w1_aprime.unattended_continuation_v3.config.v1"
CONFIG_SCHEMAS = {
    CONFIG_SCHEMA,
    "jointbuildgs.fusion_w1_aprime.unattended_queue_overnight_v4.config.v1",
}
PLAN_SCHEMA = "jointbuildgs.fusion_w1_aprime.unattended_continuation_v3.plan.v1"
PAIR_SCHEMA = "jointbuildgs.fusion_w1_aprime.unattended_continuation_v3.pair_barrier.v1"
STAGE_RECORD_SCHEMA = "jointbuildgs.fusion_w1_aprime.unattended_continuation_v3.stage_record.v1"
ACTION_FAILURE_SCHEMA = "jointbuildgs.fusion_w1_aprime.unattended_continuation_v3.action_failure.v1"
LAUNCH_INTENT_SCHEMA = "jointbuildgs.fusion_w1_aprime.unattended_continuation_v3.launch_intent.v1"
LAUNCH_RECEIPT_SCHEMA = "jointbuildgs.fusion_w1_aprime.unattended_continuation_v3.launch_receipt.v1"
ARCHIVE_SCHEMA = "jointbuildgs.fusion_w1_aprime.unattended_continuation_v3.training_archive.v1"
ARCHIVE_INTENT_SCHEMA = "jointbuildgs.fusion_w1_aprime.unattended_continuation_v3.training_archive_intent.v1"
ARCHIVE_LEDGER_SCHEMA = "jointbuildgs.fusion_w1_aprime.unattended_continuation_v3.training_archive_ledger.v1"
ORPHAN_SCHEMA = "jointbuildgs.fusion_w1_aprime.unattended_continuation_v3.orphan_training_failure.v1"
STATUS_SCHEMA = "jointbuildgs.fusion_w1_aprime.unattended_continuation_v3.status.v1"
STOP_SCHEMA = "jointbuildgs.fusion_w1_aprime.unattended_continuation_v3.stage_stop.v1"
COMPLETE_SCHEMA = "jointbuildgs.fusion_w1_aprime.unattended_continuation_v3.complete.v1"
QUAL_SCHEMA = "jointbuildgs.fusion_w1_aprime.job_qualitative.complete.v3"
PANEL_V4_SCHEMA = "jointbuildgs.fusion_w1_aprime.job_panel.complete.v4"
TERMINAL = {"MEASURED", "SKIPPED"}
TRAINING_READY = {"TRAINED", "READOUT", "READOUT_FAILED", "QUANTITATIVE_COMPLETE", "READY_MEASURED", "MEASURED", "SKIPPED"}
_QUALITATIVE_CONTEXT: dict[tuple[str, str, str], tuple[Any, dict[str, Any], dict[str, Any] | None]] = {}


class V3Error(RuntimeError):
    """A locked method, state transition, or immutable receipt drifted."""


class GpuBoundaryUnavailable(V3Error):
    """A valid host GPU boundary is temporarily unavailable due to contention."""


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def canonical_json(payload: Any) -> bytes:
    return (json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")


def sha256_file(path: Path, block_size: int = 1 << 20) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(block_size), b""):
            digest.update(block)
    return digest.hexdigest()


def require_equal(observed: Any, expected: Any, label: str) -> None:
    if observed != expected:
        raise V3Error(f"{label} mismatch: observed={observed!r}, expected={expected!r}")


def repo_path(value: str | Path) -> Path:
    raw = Path(value)
    if raw.is_absolute():
        try:
            raw = raw.relative_to(CONTAINER_REPO)
        except ValueError:
            try:
                raw = raw.relative_to(REPO)
            except ValueError as exc:
                raise V3Error(f"absolute path outside repository: {raw}") from exc
    path = (REPO / raw).resolve()
    try:
        path.relative_to(REPO.resolve())
    except ValueError as exc:
        raise V3Error(f"path escapes repository: {raw}") from exc
    return path


def relative(path: Path) -> str:
    try:
        return path.resolve().relative_to(REPO.resolve()).as_posix()
    except ValueError as exc:
        raise V3Error(f"path outside repository: {path}") from exc


def load_json(path: Path) -> dict[str, Any]:
    if not path.is_file() or path.is_symlink():
        raise V3Error(f"missing/non-regular JSON: {relative(path)}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise V3Error(f"cannot load JSON {relative(path)}: {exc}") from exc
    if not isinstance(value, dict):
        raise V3Error(f"JSON root is not an object: {relative(path)}")
    return value


def fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


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
        json.dump(dict(payload), stream, ensure_ascii=False, indent=2, sort_keys=True)
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


def file_record(path: Path, *, allow_empty: bool = False) -> dict[str, Any]:
    if not path.is_file() or path.is_symlink() or (not allow_empty and path.stat().st_size <= 0):
        raise V3Error(f"artifact missing/empty/non-regular: {relative(path)}")
    return {"path": relative(path), "sha256": sha256_file(path), "bytes": path.stat().st_size}


def verify_record(record: Mapping[str, Any], label: str) -> Path:
    raw, expected = record.get("path"), record.get("sha256")
    if not isinstance(raw, str) or not isinstance(expected, str):
        raise V3Error(f"{label} lacks path/SHA")
    path = repo_path(raw)
    if not path.is_file() or path.is_symlink() or sha256_file(path) != expected:
        raise V3Error(f"{label} missing or SHA drift: {raw}")
    if "bytes" in record and path.stat().st_size != int(record["bytes"]):
        raise V3Error(f"{label} byte-count drift: {raw}")
    return path


def git(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(["git", "-c", f"safe.directory={REPO}", "-C", str(REPO), *args], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    if check and result.returncode:
        raise V3Error(result.stderr.strip() or result.stdout.strip() or "git command failed")
    return result


def load_module(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise V3Error(f"cannot import module: {relative(path)}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def output_path(config: Mapping[str, Any], key: str) -> Path:
    root = repo_path(config["outputs"]["root"])
    value = Path(config["outputs"][key])
    return repo_path(value) if len(value.parts) > 1 else root / value


def _deep_update(target: dict[str, Any], updates: Mapping[str, Any]) -> dict[str, Any]:
    for key, value in updates.items():
        if isinstance(value, Mapping) and isinstance(target.get(key), dict):
            _deep_update(target[key], value)
        else:
            target[key] = copy.deepcopy(value)
    return target


def load_config(path: Path = DEFAULT_CONFIG) -> dict[str, Any]:
    config_path = repo_path(path)
    config = load_json(config_path)
    if config.get("schema") == "jointbuildgs.fusion_w1_aprime.unattended_queue_overnight_v4.config.v1" and "extends" in config:
        base_record = config["extends"]
        base_path = verify_record(base_record, "overnight base queue config")
        base = load_json(base_path)
        overrides = config.get("overrides")
        if not isinstance(overrides, Mapping):
            raise V3Error("overnight config overrides are absent")
        merged = _deep_update(copy.deepcopy(base), overrides)
        merged["schema"] = config["schema"]
        merged["extends"] = dict(base_record)
        config = merged
    if config.get("schema") not in CONFIG_SCHEMAS:
        raise V3Error(f"unsupported queue config schema: {config.get('schema')!r}")
    if not isinstance(config.get("task_id"), str) or not config["task_id"]:
        raise V3Error("queue task ID is absent")
    require_equal(config.get("branch"), "exp/fusion-w1", "branch")
    require_equal(config["sequence_contract"].get("source_entries"), 20, "source entries")
    require_equal(config["sequence_contract"].get("reused_jobs"), 1, "reused jobs")
    expected_new_jobs = 15 if config.get("contract_profile") == "overnight_v4" else 19
    require_equal(config["sequence_contract"].get("new_training_jobs"), expected_new_jobs, "new jobs")
    require_equal(config["sequence_contract"].get("terminal_jobs"), 20, "terminal jobs")
    require_equal(config["sequence_contract"].get("pair_count"), 11, "pair count")
    require_equal(config["resources"].get("maximum_concurrent_training"), 2, "training concurrency")
    require_equal(config["resources"].get("physical_gpus"), [0, 1], "physical GPUs")
    require_equal(config["resources"].get("readout_global_serial"), True, "readout serialization")
    require_equal(config["resources"].get("readout_concurrent_with_training"), False, "readout overlap")
    require_equal(config["failure_contract"].get("same_error_signature_attempts_before_skip"), 3, "retry threshold")
    require_equal(config["failure_contract"].get("same_error_type_consecutive_buildings_before_stage_stop"), 3, "stage-stop threshold")
    hook = config["qualitative_hook"]
    kind = hook.get("kind", "qualitative_v3")
    if kind not in {"qualitative_v3", "panel_v4"}:
        raise V3Error(f"unsupported qualitative hook kind: {kind!r}")
    expected_schema = QUAL_SCHEMA if kind == "qualitative_v3" else PANEL_V4_SCHEMA
    require_equal(hook.get("receipt_schema"), expected_schema, "qualitative hook schema")
    if not isinstance(hook.get("locked_input_keys"), Mapping):
        hook["locked_input_keys"] = {
            "config": "qualitative_config",
            "renderer": "qualitative_renderer",
            "wrapper": "qualitative_wrapper",
            "test": "qualitative_test",
        }
    require_equal(config["publication"].get("interpretation_or_verdict"), None, "verdict lock")
    require_equal(relative(config_path), config["implementation_files"][0], "config path")
    return config


def verify_method(config: Mapping[str, Any]) -> dict[str, Any]:
    branch = git("branch", "--show-current").stdout.strip()
    head = git("rev-parse", "HEAD").stdout.strip()
    require_equal(branch, config["branch"], "runtime branch")
    records = []
    for logical in [*config["implementation_files"], *config["provenance_files"]]:
        if git("ls-files", "--error-unmatch", logical, check=False).returncode:
            raise V3Error(f"v3 implementation/provenance is not tracked: {logical}")
        head_blob = git("rev-parse", f"{head}:{logical}", check=False)
        if head_blob.returncode:
            raise V3Error(f"v3 implementation/provenance absent at HEAD: {logical}")
        worktree_blob = git("hash-object", "--", logical).stdout.strip()
        require_equal(worktree_blob, head_blob.stdout.strip(), f"worktree/HEAD {logical}")
        records.append({**file_record(repo_path(logical)), "git_blob": worktree_blob})
    return {"branch": branch, "head": head, "files": records}


def verify_locked_inputs(config: Mapping[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, expected in config["locked_inputs"].items():
        path = repo_path(expected["path"])
        observed = file_record(path)
        require_equal(observed["sha256"], expected["sha256"], f"locked input {key}")
        if git("ls-files", "--error-unmatch", expected["path"], check=False).returncode:
            raise V3Error(f"locked input is not tracked: {expected['path']}")
        if git("diff", "--quiet", "HEAD", "--", expected["path"], check=False).returncode:
            raise V3Error(f"locked input differs from HEAD: {expected['path']}")
        result[key] = observed
    return result


def lock_is_busy_readonly(path: Path, *, require_exists: bool = False) -> bool:
    """Probe an existing flock without creating or modifying its inode."""
    if not path.exists():
        if require_exists:
            raise V3Error(f"required lock file is absent: {relative(path)}")
        return False
    if not path.is_file() or path.is_symlink():
        raise V3Error(f"lock is not a regular file: {relative(path)}")
    descriptor = os.open(path, os.O_RDONLY)
    try:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return True
        finally:
            try:
                fcntl.flock(descriptor, fcntl.LOCK_UN)
            except OSError:
                pass
    finally:
        os.close(descriptor)
    return False


def source_v2_module(config: Mapping[str, Any]) -> Any:
    record = config["locked_inputs"]["source_v2_driver"]
    path = repo_path(record["path"])
    require_equal(sha256_file(path), record["sha256"], "source v2 driver bootstrap SHA")
    return load_module("fusion_w1_aprime_queue_v2_for_v3", path)


def training_context(config: Mapping[str, Any]) -> tuple[Any, dict[str, Any], Path]:
    path = repo_path(config["locked_inputs"]["training_driver"]["path"])
    module = load_module("fusion_w1_aprime_training_for_v3", path)
    config_path = repo_path(config["locked_inputs"]["training_config"]["path"])
    return module, module.load_config(config_path), config_path


def verify_training_preflight(config: Mapping[str, Any]) -> dict[str, Any]:
    module, training_config, _config_path = training_context(config)
    method = module.committed_method_gate(REPO, training_config)
    require_equal(method.get("head"), git("rev-parse", "HEAD").stdout.strip(), "training method/current HEAD")
    gates = module.validate_preflight_gates(REPO, training_config, "full")
    require_equal(gates.get("status"), "PASSED", "training preflight status")
    require_equal(gates.get("required_gates"), ["five_pin", "T1", "T2", "T3"], "training preflight gates")
    return {"method": method, "gates": gates, "T2_exact_head_republication_required": True}


def source_plan(config: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    expected = config["source_v2"]["plan"]
    path = repo_path(expected["path"])
    observed = file_record(path)
    require_equal(observed["sha256"], expected["sha256"], "source v2 plan SHA")
    payload = load_json(path)
    require_equal(payload.get("schema"), "jointbuildgs.fusion_w1_aprime.unattended.plan.v1", "source v2 plan schema")
    require_equal(payload.get("state"), "ACTIVE", "source v2 plan state")
    entries = payload.get("entries")
    if not isinstance(entries, list):
        raise V3Error("source v2 entries missing")
    require_equal(len(entries), 20, "source v2 entry count")
    return payload, observed


def build_v3_plan(source_entries: Sequence[Mapping[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if len(source_entries) != 20:
        raise V3Error(f"source plan must contain 20 entries, got {len(source_entries)}")
    entries: list[dict[str, Any]] = []
    for index, raw in enumerate(source_entries, 1):
        entry = dict(raw)
        entry["v3_global_order"] = index
        entry["reuse_source_v2"] = index == 1
        entry["pair_id"] = None
        entry["pair_member_order"] = None
        entry["assigned_gpu"] = None
        entries.append(entry)
    pairs: list[dict[str, Any]] = []
    pair_global = 0
    for stage_order in sorted({int(row["stage_order"]) for row in entries}):
        pending = [row for row in entries if int(row["stage_order"]) == stage_order and not row["reuse_source_v2"]]
        for stage_pair_order, offset in enumerate(range(0, len(pending), 2), 1):
            pair_global += 1
            members = pending[offset : offset + 2]
            pair_id = f"pair_{pair_global:02d}_stage_{stage_order:02d}_{members[0]['stage_key']}_{stage_pair_order:02d}"
            packed = []
            for member_order, member in enumerate(members, 1):
                gpu = member_order - 1
                member["pair_id"] = pair_id
                member["pair_member_order"] = member_order
                member["assigned_gpu"] = gpu
                packed.append({
                    "member_order": member_order,
                    "physical_gpu": gpu,
                    "stage_key": member["stage_key"],
                    "stage_entry_order": int(member["stage_entry_order"]),
                    "building_id": member["building_id"],
                    "arm": member["arm"],
                    "replicate": member["replicate"],
                })
            pairs.append({
                "pair_order": pair_global,
                "pair_id": pair_id,
                "stage_order": stage_order,
                "stage_key": members[0]["stage_key"],
                "stage_pair_order": stage_pair_order,
                "members": packed,
            })
    require_equal(len(pairs), 11, "v3 pair count")
    require_equal(sum(len(pair["members"]) for pair in pairs), 19, "v3 paired jobs")
    for pair in pairs:
        require_equal(len({member["stage_key"] for member in pair["members"]}), 1, "pair stage boundary")
        if len(pair["members"]) > 2:
            raise V3Error("pair exceeds two training lanes")
    return entries, pairs


def verify_continuation_contract(config: Mapping[str, Any], entries: Sequence[Mapping[str, Any]], pairs: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    contract_path = repo_path(config["locked_inputs"]["continuation_contract"]["path"])
    contract = load_json(contract_path)
    require_equal(contract.get("schema"), "jointbuildgs.fusion_w1_aprime.continuation_v3.lock.v1", "continuation contract schema")
    require_equal(contract.get("task_id"), config["task_id"], "continuation contract task")
    require_equal(contract.get("branch"), config["branch"], "continuation contract branch")
    require_equal(contract.get("interpretation_or_verdict"), None, "continuation contract verdict")
    source_head = str(contract.get("source_git_head", ""))
    if re.fullmatch(r"[0-9a-f]{40}", source_head) is None or git("merge-base", "--is-ancestor", source_head, git("rev-parse", "HEAD").stdout.strip(), check=False).returncode:
        raise V3Error(f"continuation source HEAD is not an ancestor: {source_head}")
    source = contract["source_v2"]
    require_equal(source.get("plan"), config["source_v2"]["plan"], "contract source plan")
    status_expected = config["source_v2"]["status"]
    status_path = repo_path(status_expected["path"])
    require_equal(file_record(status_path)["sha256"], status_expected["sha256"], "source v2 status SHA")
    require_equal(source.get("status", {}).get("path"), status_expected["path"], "contract source status path")
    require_equal(source.get("status", {}).get("sha256"), status_expected["sha256"], "contract source status SHA")
    status = load_json(status_path)
    require_equal(status.get("counts"), source["status"]["counts"], "contract source status counts")
    reused = source["reused_job"]
    first = entries[0]
    for key in ("building_id", "arm", "replicate"):
        require_equal(reused.get(key), first[key], f"contract reused {key}")
    current = verify_source_reuse(config, first, verify_contract=False)
    require_equal(current["stage_record"]["sha256"], reused["stage_record_sha256"], "contract reused stage SHA")
    require_equal(current["training_complete"]["sha256"], reused["training_complete_sha256"], "contract reused training SHA")
    require_equal(current["readout_complete"]["sha256"], reused["readout_complete_sha256"], "contract reused readout SHA")
    require_equal(reused.get("qualitative_required_before_v3_terminal"), True, "contract reused qualitative gate")
    require_equal(source.get("next_job_not_materialized"), f"{entries[1]['building_id']}/{entries[1]['arm']}/{entries[1]['replicate']}", "contract next job")
    require_equal(source.get("v2_files_immutable"), True, "contract v2 immutability")
    resources = contract["resources"]
    require_equal(resources.get("maximum_concurrent_training"), 2, "contract training concurrency")
    require_equal(resources.get("physical_gpus"), [0, 1], "contract GPUs")
    require_equal(resources.get("training_pair_barrier_before_readout"), True, "contract pair barrier")
    require_equal(resources.get("readout_global_serial"), True, "contract serial readout")
    require_equal(resources.get("readout_concurrent_with_training"), False, "contract no overlap")
    require_equal(resources.get("scientific_recipe_changed"), False, "contract scientific recipe")
    expected_pairs = []
    for pair in pairs:
        by_gpu = {int(member["physical_gpu"]): member["building_id"] for member in pair["members"]}
        expected_pairs.append({"stage": pair["stage_key"], "pair": int(pair["stage_pair_order"]), "gpu0": by_gpu.get(0), "gpu1": by_gpu.get(1)})
    require_equal(contract.get("pairs"), expected_pairs, "contract pair schedule")
    failure = contract["failure_contract"]
    require_equal(failure.get("same_error_signature_attempts_before_skip"), 3, "contract retry count")
    require_equal(failure.get("same_error_type_consecutive_buildings_before_stage_stop"), 3, "contract stop count")
    require_equal(failure.get("delete_or_overwrite_allowed"), False, "contract overwrite")
    require_equal(failure.get("user_prompts"), False, "contract prompts")
    require_equal(failure.get("time_cutoff"), None, "contract time cutoff")
    return {"contract": file_record(contract_path), "markdown": file_record(repo_path(config["locked_inputs"]["continuation_contract_markdown"]["path"])), "source_head": source_head, "source_head_is_ancestor": True, "status": file_record(status_path), "pair_schedule_verified": True}


def verify_repair_contract(
    config: Mapping[str, Any],
    entries: Sequence[Mapping[str, Any]],
    pairs: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    contract_path = repo_path(config["locked_inputs"]["repair_contract"]["path"])
    contract = load_json(contract_path)
    require_equal(
        contract.get("schema"),
        "jointbuildgs.fusion_w1_aprime.unattended_continuation_v3.repair_lock.v1",
        "repair contract schema",
    )
    require_equal(contract.get("task_id"), config["task_id"], "repair contract task")
    require_equal(contract.get("branch"), config["branch"], "repair contract branch")
    require_equal(contract.get("interpretation_or_verdict"), None, "repair contract verdict")
    source = contract["source_failed_control"]
    old_root = repo_path(config["locked_inputs"]["continuation_contract"]["path"]).parent
    require_equal(source.get("namespace"), relative(old_root), "repair source namespace")
    if re.fullmatch(r"[0-9a-f]{40}", str(source.get("git_head", ""))) is None:
        raise V3Error("repair source HEAD is invalid")
    source_records = {}
    for name in ("queue_plan", "source_boundary", "stop_post_audit"):
        observed = file_record(verify_record(source[name], f"repair source {name}"))
        require_equal(observed, source[name], f"repair source {name} record")
        source_records[name] = observed
    require_equal(source.get("service_exit_status"), 2, "repair source exit status")
    require_equal(
        source.get("failure"),
        "qualitative verifier omitted required output_root argument",
        "repair source failure",
    )
    reused = contract["reused_measured_job"]
    first = entries[0]
    for key in ("building_id", "arm", "replicate"):
        require_equal(reused.get(key), first[key], f"repair reused {key}")
    reused_records = {}
    for name in ("qualitative_complete", "panel"):
        observed = file_record(verify_record(reused[name], f"repair reused {name}"))
        require_equal(observed, reused[name], f"repair reused {name} record")
        reused_records[name] = observed
    for key in ("recompute_training", "recompute_readout", "recompute_qualitative"):
        require_equal(reused.get(key), False, f"repair reused {key}")
    repair = contract["repair_scope"]
    require_equal(repair.get("scientific_recipe_changed"), False, "repair scientific recipe")
    require_equal(repair.get("target_list_changed"), False, "repair target list")
    require_equal(repair.get("pair_schedule_changed"), False, "repair pair schedule")
    require_equal(repair.get("failure_thresholds_changed"), False, "repair failure thresholds")
    require_equal(repair.get("new_training_jobs"), 19, "repair training jobs")
    require_equal(repair.get("maximum_concurrent_training"), 2, "repair concurrency")
    require_equal(repair.get("readout_remains_global_serial"), True, "repair readout serialization")
    require_equal(repair.get("new_control_namespace"), config["outputs"]["root"], "repair output namespace")
    require_equal(repair.get("old_control_namespace_mutation_allowed"), False, "repair old namespace mutation")
    expected_first_pair = pairs[0]
    first_pair = contract["first_new_pair"]
    require_equal(first_pair.get("pair_id"), expected_first_pair["pair_id"], "repair first pair ID")
    by_gpu = {
        int(member["physical_gpu"]): f"{member['building_id']}/{member['arm']}/{member['replicate']}"
        for member in expected_first_pair["members"]
    }
    require_equal(first_pair.get("gpu0"), by_gpu.get(0), "repair first pair GPU0")
    require_equal(first_pair.get("gpu1"), by_gpu.get(1), "repair first pair GPU1")
    require_equal(first_pair.get("materialized_before_repair"), False, "repair pre-materialization")
    t2 = contract["t2_control"]
    for key in (
        "final_repair_head_requires_new_receipt",
        "previous_receipt_must_be_archived",
        "geometry_and_sample_artifact_hashes_must_remain_unchanged",
    ):
        require_equal(t2.get(key), True, f"repair T2 {key}")
    require_equal(contract.get("partial_artifacts_preserved"), True, "repair partial preservation")
    return {
        "contract": file_record(contract_path),
        "markdown": file_record(
            repo_path(config["locked_inputs"]["repair_contract_markdown"]["path"])
        ),
        "source_head": source["git_head"],
        "source_records": source_records,
        "reused_records": reused_records,
        "scientific_recipe_changed": False,
        "target_list_changed": False,
        "pair_schedule_changed": False,
    }


def _verify_record_tree(value: Any, label: str) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    if isinstance(value, Mapping):
        if isinstance(value.get("path"), str) and isinstance(value.get("sha256"), str):
            path = verify_record(value, label)
            observed = file_record(path, allow_empty=int(value.get("bytes", 1)) == 0)
            require_equal(observed, dict(value), f"{label} record")
            records.append(observed)
        else:
            for key, nested in value.items():
                records.extend(_verify_record_tree(nested, f"{label}.{key}"))
    elif isinstance(value, list):
        for index, nested in enumerate(value):
            records.extend(_verify_record_tree(nested, f"{label}[{index}]"))
    return records


def verify_overnight_recovery_contract(
    config: Mapping[str, Any],
    entries: Sequence[Mapping[str, Any]],
    pairs: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    expected = config["locked_inputs"]["recovery_contract"]
    path = repo_path(expected["path"])
    require_equal(file_record(path)["sha256"], expected["sha256"], "overnight recovery lock SHA")
    contract = load_json(path)
    require_equal(contract.get("schema"), "jointbuildgs.fusion_w1_aprime.unattended_queue_overnight_v4.recovery_lock.v1", "overnight recovery schema")
    require_equal(contract.get("state"), "LOCKED_FOR_OVERNIGHT_RECOVERY", "overnight recovery state")
    require_equal(contract.get("task_id"), config["task_id"], "overnight recovery task")
    require_equal(contract.get("branch"), config["branch"], "overnight recovery branch")
    require_equal(contract.get("interpretation_or_verdict"), None, "overnight recovery verdict")
    source = contract["source_failed_control"]
    require_equal(source.get("namespace"), config["recovery_contract"]["source_namespace"], "overnight source namespace")
    require_equal(source.get("terminal_state"), "STOPPED_THREE_CONSECUTIVE_BUILDING_SKIPS", "overnight source terminal state")
    failure = source["failure"]
    require_equal(failure.get("error_type"), "CacheProbeHeadMismatch", "overnight failure type")
    require_equal(failure.get("producer_head"), config["historical_training_reuse_contract"]["producer_head"], "overnight failure producer HEAD")
    require_equal(failure.get("source_fixed"), True, "overnight source-fixed flag")
    records = _verify_record_tree(source.get("records"), "overnight source record")
    reuse = contract["historical_training_reuse"]
    require_equal(reuse.get("producer_head"), config["historical_training_reuse_contract"]["producer_head"], "overnight reuse producer HEAD")
    require_equal(reuse.get("allowed_jobs"), config["historical_training_reuse_contract"]["allowed_jobs"], "overnight reuse jobs")
    require_equal(reuse.get("producer_head_must_be_ancestor"), True, "overnight ancestor rule")
    require_equal(reuse.get("method_files_must_be_current_identical"), True, "overnight method rule")
    records.extend(_verify_record_tree(reuse.get("records"), "overnight historical training record"))
    scope = contract["recovery_scope"]
    require_equal(scope.get("new_control_namespace"), config["outputs"]["root"], "overnight output namespace")
    require_equal(scope.get("old_control_namespace_mutation_allowed"), False, "overnight old namespace mutation")
    require_equal(scope.get("scientific_recipe_changed"), False, "overnight scientific recipe")
    require_equal(scope.get("target_list_changed"), False, "overnight target list")
    require_equal(scope.get("pair_schedule_changed"), False, "overnight pair schedule")
    require_equal(scope.get("panel_hook"), config["qualitative_hook"]["wrapper"], "overnight panel hook")
    readout_record = scope.get("source_fixed_readout_config")
    if not isinstance(readout_record, Mapping):
        raise V3Error("overnight source-fixed readout config record is absent")
    require_equal(readout_record, config["locked_inputs"]["readout_config"], "overnight/readout config lock")
    records.extend(_verify_record_tree(readout_record, "overnight source-fixed readout config"))
    records.extend(_verify_record_tree(scope.get("readout_continuation_lock"), "overnight readout continuation lock"))
    require_equal(len(entries), 20, "overnight entries")
    require_equal(len(pairs), 11, "overnight pairs")
    return {
        "contract": file_record(path),
        "markdown": file_record(repo_path(config["locked_inputs"]["recovery_contract_markdown"]["path"])),
        "source_records_n": len(records),
        "producer_head": reuse["producer_head"],
        "old_namespace_mutation_allowed": False,
        "scientific_recipe_changed": False,
    }


def control_contracts(
    config: Mapping[str, Any],
    entries: Sequence[Mapping[str, Any]],
    pairs: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    profile = config.get("contract_profile", "continuation_v3_repair1")
    if profile == "continuation_v3_repair1":
        return {
            "continuation_contract": verify_continuation_contract(config, entries, pairs),
            "repair_contract": verify_repair_contract(config, entries, pairs),
        }
    if profile == "overnight_v4":
        return {"recovery_contract": verify_overnight_recovery_contract(config, entries, pairs)}
    raise V3Error(f"unsupported queue contract profile: {profile!r}")


def identity(entry: Mapping[str, Any]) -> dict[str, str]:
    return {"building_id": str(entry["building_id"]), "arm": str(entry["arm"]), "replicate": str(entry["replicate"]), "profile": "full"}


def entry_key(entry: Mapping[str, Any]) -> str:
    return f"stage_{int(entry['stage_order']):02d}_{entry['stage_key']}/entry_{int(entry['stage_entry_order']):02d}_{entry['building_id']}_arm_{entry['arm']}_{entry['replicate']}"


def stage_record_path(config: Mapping[str, Any], entry: Mapping[str, Any]) -> Path:
    return output_path(config, "stage_records") / f"{entry_key(entry)}.json"


def qualitative_path(config: Mapping[str, Any], entry: Mapping[str, Any]) -> Path:
    value = config["qualitative_hook"]["receipt_template"].format(building_id=entry["building_id"], arm=entry["arm"], replicate=entry["replicate"])
    return repo_path(value)


def verify_source_reuse(config: Mapping[str, Any], first_entry: Mapping[str, Any], *, verify_contract: bool = True) -> dict[str, Any]:
    expected = config["source_v2"]["reused_first_job"]
    for key in ("building_id", "arm", "replicate", "profile", "stage_key", "stage_order", "stage_entry_order"):
        require_equal(first_entry.get(key), expected[key], f"reused source {key}")
    stage_path = repo_path(expected["stage_record"])
    stage = load_json(stage_path)
    require_equal(stage.get("schema"), "jointbuildgs.fusion_w1_aprime.unattended.stage_record.v1", "source stage schema")
    require_equal(stage.get("status"), "MEASURED", "source stage status")
    require_equal(stage.get("entry"), {key: value for key, value in first_entry.items() if key not in {"v3_global_order", "reuse_source_v2", "pair_id", "pair_member_order", "assigned_gpu"}}, "source stage entry")
    training_path = repo_path(expected["training_complete"])
    training = load_json(training_path)
    require_equal(training.get("status"), "COMPLETED", "source training status")
    for key, value in identity(first_entry).items():
        require_equal(training.get("replicate" if key == "replicate" else key), value, f"source training {key}")
    require_equal(training.get("return_code"), 0, "source training return code")
    final_checkpoint = training.get("training_completion", {}).get("final_checkpoint")
    if not isinstance(final_checkpoint, Mapping):
        raise V3Error("source training final checkpoint missing")
    verify_record(final_checkpoint, "source final checkpoint")
    verify_record(training["started_receipt"], "source started receipt")
    verify_record(training["materialization"], "source materialization")
    readout_path = repo_path(expected["readout_complete"])
    readout = load_json(readout_path)
    require_equal(readout.get("state"), "COMPLETE", "source readout state")
    require_equal(readout.get("identity"), identity(first_entry), "source readout identity")
    primary = readout.get("primary") or {}
    require_equal(primary.get("state"), "MEASURED", "source primary state")
    require_equal(primary.get("eligible_for_preregistered_judgment"), True, "source primary eligibility")
    primary_path = verify_record(primary["receipt"], "source primary score")
    source_receipts = stage.get("source_receipts")
    if not isinstance(source_receipts, list) or len(source_receipts) != 1:
        raise V3Error("source stage must bind one readout receipt")
    require_equal(source_receipts[0], file_record(readout_path), "source stage/readout binding")
    ledger = readout.get("artifact_ledger")
    if not isinstance(ledger, list) or not ledger:
        raise V3Error("source readout ledger missing")
    require_equal(readout.get("artifact_count"), len(ledger), "source readout artifact count")
    for record in ledger:
        verify_record(record, "source readout artifact")
    result = {
        "stage_record": file_record(stage_path),
        "training_complete": file_record(training_path),
        "readout_complete": file_record(readout_path),
        "primary_score": file_record(primary_path),
    }
    if verify_contract:
        contract = load_json(repo_path(config["locked_inputs"]["continuation_contract"]["path"]))
        reused = contract.get("source_v2", {}).get("reused_job", {})
        require_equal(result["stage_record"]["sha256"], reused.get("stage_record_sha256"), "locked reused stage SHA")
        require_equal(result["training_complete"]["sha256"], reused.get("training_complete_sha256"), "locked reused training SHA")
        require_equal(result["readout_complete"]["sha256"], reused.get("readout_complete_sha256"), "locked reused readout SHA")
    return result


def ensure_source_not_advanced(config: Mapping[str, Any], entries: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    source_root = repo_path(config["source_v2"]["root"])
    expected_stage = repo_path(config["source_v2"]["reused_first_job"]["stage_record"]).resolve()
    observed = [path.resolve() for path in (source_root / "stage_records").rglob("*.json")]
    require_equal(observed, [expected_stage], "source v2 terminal stage records")
    module, training_config, _ = training_context(config)
    v2 = source_v2_module(config)
    for entry in entries[1:]:
        training_job = module.job_dir(REPO, training_config, entry["building_id"], entry["arm"], entry["replicate"], "full")
        if training_job.exists() or training_job.is_symlink():
            raise V3Error(f"source v2 advanced into remaining training job: {relative(training_job)}")
        _readout_module, _readout_config, readout_job = v2.queue.readout_job_path(config, entry)
        if readout_job.exists() or readout_job.is_symlink():
            raise V3Error(f"source v2 advanced into remaining readout job: {relative(readout_job)}")
    return {
        "observed_source_stage_records": [file_record(expected_stage)],
        "expected_source_stage_record_only": True,
        "remaining_training_jobs_checked": len(entries) - 1,
        "remaining_readout_jobs_checked": len(entries) - 1,
        "remaining_canonical_outputs_absent_at_boundary": True,
    }


def append_event(config: Mapping[str, Any], event_type: str, detail: Mapping[str, Any]) -> dict[str, Any]:
    root = output_path(config, "root") if "root" != "root" else repo_path(config["outputs"]["root"])
    root.mkdir(parents=True, exist_ok=True)
    events = output_path(config, "events")
    sequence_path = root / "event_sequence.json"
    lock_path = root / "event_sequence.lock"
    with lock_path.open("a+b") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        sequence = int(load_json(sequence_path)["last_sequence"]) + 1 if sequence_path.is_file() else 1
        payload = {"schema": "jointbuildgs.fusion_w1_aprime.unattended_continuation_v3.event.v1", "sequence": sequence, "created_at": now_iso(), "event_type": event_type, "detail": dict(detail), "interpretation_or_verdict": None}
        with events.open("ab") as stream:
            stream.write(canonical_json(payload)); stream.flush(); os.fsync(stream.fileno())
        atomic_json(sequence_path, {"schema": "jointbuildgs.fusion_w1_aprime.unattended_continuation_v3.event_sequence.v1", "last_sequence": sequence, "events": file_record(events)})
        fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
    return payload


def initialize(config: Mapping[str, Any], config_path: Path) -> dict[str, Any]:
    source_lock = repo_path(config["source_v2"]["driver_lock"])
    if lock_is_busy_readonly(source_lock, require_exists=True):
        raise V3Error("source v2 driver lock is still held")
    method = verify_method(config)
    locked = verify_locked_inputs(config)
    preflight = verify_training_preflight(config)
    source, source_record = source_plan(config)
    entries, pairs = build_v3_plan(source["entries"])
    contracts = control_contracts(config, entries, pairs)
    source_gate = verify_source_reuse(config, entries[0])
    plan_path = output_path(config, "plan")
    boundary_path = output_path(config, "source_boundary_receipt")
    if boundary_path.exists() or boundary_path.is_symlink():
        boundary = load_json(boundary_path)
        require_equal(boundary.get("schema"), "jointbuildgs.fusion_w1_aprime.unattended_continuation_v3.source_boundary.v1", "source boundary schema")
        require_equal(boundary.get("state"), "LOCKED", "source boundary state")
        require_equal(boundary.get("git_lock"), method, "source boundary/current method")
        require_equal(boundary.get("locked_inputs"), locked, "source boundary/current locked inputs")
        require_equal(boundary.get("training_preflight"), preflight, "source boundary/current preflight")
        require_equal(boundary.get("source_v2_plan"), source_record, "source boundary plan")
        require_equal(boundary.get("source_v2_gate"), source_gate, "source boundary gate")
        for key, value in contracts.items():
            require_equal(boundary.get(key), value, f"source boundary {key}")
        require_equal(boundary.get("source_v2_driver_lock_free"), True, "source boundary lock proof")
        require_equal(boundary.get("source_v2_namespace_rewritten"), False, "source boundary immutability")
    else:
        no_advance = (
            ensure_source_not_advanced(config, entries)
            if config.get("contract_profile", "continuation_v3_repair1") == "continuation_v3_repair1"
            else {
                "recovery_source_rehashed": True,
                "historical_canonical_training_outputs_preserved": True,
                "source_control_namespace_rewritten": False,
            }
        )
        boundary = {
            "schema": "jointbuildgs.fusion_w1_aprime.unattended_continuation_v3.source_boundary.v1",
            "state": "LOCKED",
            "created_at": now_iso(),
            "git_lock": method,
            "locked_inputs": locked,
            "training_preflight": preflight,
            "source_v2_plan": source_record,
            "source_v2_gate": source_gate,
            **contracts,
            "source_v2_driver_lock": file_record(source_lock, allow_empty=True),
            "source_v2_driver_lock_free": True,
            "source_not_advanced": no_advance,
            "source_v2_namespace_rewritten": False,
            "interpretation_or_verdict": None,
        }
        exclusive_json(boundary_path, boundary)
    expected = {
        "schema": PLAN_SCHEMA,
        "state": "ACTIVE",
        "run_id": config["run_id"],
        "task_id": config["task_id"],
        "config": file_record(repo_path(config_path)),
        "git_lock": method,
        "locked_inputs": locked,
        "training_preflight": preflight,
        "source_v2_plan": source_record,
        "source_v2_plan_snapshot_sha256": hashlib.sha256(canonical_json(source)).hexdigest(),
        "source_v2_gate": source_gate,
        **contracts,
        "source_boundary_receipt": file_record(boundary_path),
        "source_v2_namespace_rewritten": False,
        "sequence_contract": config["sequence_contract"],
        "failure_contract": config["failure_contract"],
        "entries": entries,
        "pairs": pairs,
        "terminal_jobs_n": int(config["sequence_contract"]["terminal_jobs"]),
        "new_training_jobs_n": int(config["sequence_contract"]["new_training_jobs"]),
        "interpretation_or_verdict": None,
    }
    if plan_path.exists() or plan_path.is_symlink():
        observed = load_json(plan_path)
        for key, value in expected.items():
            require_equal(observed.get(key), value, f"immutable v3 plan {key}")
        return {**observed, "publication_reused": True}
    expected["created_at"] = now_iso()
    exclusive_json(plan_path, expected)
    append_event(config, "QUEUE_INITIALIZED", {"plan": file_record(plan_path), "source_gate": source_gate, "pairs_n": len(pairs), "contract_profile": config.get("contract_profile", "continuation_v3_repair1")})
    return expected


def load_plan(config: Mapping[str, Any], *, runtime_gate: bool = True) -> dict[str, Any]:
    plan_path = output_path(config, "plan")
    plan = load_json(plan_path)
    require_equal(plan.get("schema"), PLAN_SCHEMA, "v3 plan schema")
    require_equal(plan.get("state"), "ACTIVE", "v3 plan state")
    source, source_record = source_plan(config)
    require_equal(plan.get("source_v2_plan"), source_record, "v3/source plan record")
    require_equal(plan.get("source_v2_plan_snapshot_sha256"), hashlib.sha256(canonical_json(source)).hexdigest(), "v3/source plan snapshot")
    entries, pairs = build_v3_plan(source["entries"])
    contracts = control_contracts(config, entries, pairs)
    require_equal(plan.get("entries"), entries, "v3 plan entries")
    require_equal(plan.get("pairs"), pairs, "v3 plan pairs")
    for key, value in contracts.items():
        require_equal(plan.get(key), value, f"queue plan {key}")
    boundary_path = output_path(config, "source_boundary_receipt")
    boundary = load_json(boundary_path)
    require_equal(boundary.get("schema"), "jointbuildgs.fusion_w1_aprime.unattended_continuation_v3.source_boundary.v1", "source boundary schema")
    require_equal(plan.get("source_boundary_receipt"), file_record(boundary_path), "plan/source boundary")
    require_equal(boundary.get("source_v2_plan"), source_record, "source boundary/current source plan")
    require_equal(boundary.get("source_v2_gate"), verify_source_reuse(config, entries[0]), "source boundary/current source gate")
    for key, value in contracts.items():
        require_equal(boundary.get(key), value, f"source boundary/current {key}")
    require_equal(boundary.get("source_v2_driver_lock_free"), True, "source boundary lock free")
    if lock_is_busy_readonly(repo_path(config["source_v2"]["driver_lock"]), require_exists=True):
        raise V3Error("source v2 driver lock became busy")
    if runtime_gate:
        require_equal(plan.get("git_lock"), verify_method(config), "v3 plan/current method")
        require_equal(plan.get("locked_inputs"), verify_locked_inputs(config), "v3 locked inputs")
        require_equal(plan.get("training_preflight"), verify_training_preflight(config), "v3 training preflight")
    return plan


def entry_for(plan: Mapping[str, Any], stage_key: str, stage_entry_order: int) -> dict[str, Any]:
    matches = [dict(entry) for entry in plan["entries"] if entry["stage_key"] == stage_key and int(entry["stage_entry_order"]) == stage_entry_order]
    if len(matches) != 1:
        raise V3Error(f"entry resolution failed: {stage_key}/{stage_entry_order}")
    return matches[0]


def load_stage_record(config: Mapping[str, Any], entry: Mapping[str, Any]) -> dict[str, Any] | None:
    path = stage_record_path(config, entry)
    if not path.exists() and not path.is_symlink():
        return None
    payload = load_json(path)
    require_equal(payload.get("schema"), STAGE_RECORD_SCHEMA, "stage record schema")
    require_equal(payload.get("entry"), dict(entry), "stage record entry")
    if payload.get("status") not in TERMINAL:
        raise V3Error(f"stage record is not terminal: {relative(path)}")
    verify_stage_payload(config, entry, payload)
    return payload


def verify_stage_payload(config: Mapping[str, Any], entry: Mapping[str, Any], payload: Mapping[str, Any]) -> None:
    status = payload.get("status")
    receipts = payload.get("source_receipts")
    if not isinstance(receipts, list):
        raise V3Error("terminal source receipts are absent")
    if status == "SKIPPED":
        require_equal(payload.get("components"), None, "skipped components")
        require_equal(payload.get("same_signature_attempts"), len(receipts), "skip receipt count")
        if len(receipts) != 3 or not payload.get("error_signature") or not payload.get("error_type"):
            raise V3Error("skip terminal lacks exact three-attempt evidence")
        for record in receipts:
            verify_record(record, "skip terminal evidence")
        return
    require_equal(status, "MEASURED", "terminal measured status")
    components = payload.get("components")
    if not isinstance(components, Mapping):
        raise V3Error("measured terminal components missing")
    required = config["terminal_contract"]["measured_requires"]
    require_equal(sorted(components), sorted(required), "measured terminal component keys")
    require_equal(receipts, [components[key] for key in ("training_complete", "readout_complete", "primary_quantitative_score", "qualitative_complete")], "measured terminal receipt order")
    for key, record in components.items():
        verify_record(record, f"measured terminal {key}")
    training = verify_training_complete(config, entry, allow_launch_reconcile=False)
    readout = verify_readout_complete(config, entry)
    qualitative = verify_qualitative_complete(config, entry)
    if training is None or readout is None or qualitative is None:
        raise V3Error("measured terminal current component disappeared")
    require_equal(components["training_complete"], training["receipt"], "terminal/current training")
    require_equal(components["readout_complete"], readout["receipt"], "terminal/current readout")
    require_equal(components["primary_quantitative_score"], readout["primary_score"], "terminal/current primary score")
    require_equal(components["qualitative_complete"], qualitative["receipt"], "terminal/current qualitative")
    require_equal(qualitative["source_readout_complete"], readout["receipt"], "qualitative/readout cross-binding")


def _file_records(value: Any) -> list[Mapping[str, Any]]:
    records: list[Mapping[str, Any]] = []
    if isinstance(value, Mapping):
        if isinstance(value.get("path"), str) and isinstance(value.get("sha256"), str):
            records.append(value)
        else:
            for nested in value.values():
                records.extend(_file_records(nested))
    elif isinstance(value, list):
        for nested in value:
            records.extend(_file_records(nested))
    return records


def qualitative_context(config: Mapping[str, Any]) -> tuple[Any, dict[str, Any], dict[str, Any] | None]:
    hook = config["qualitative_hook"]
    kind = hook.get("kind", "qualitative_v3")
    keys = hook["locked_input_keys"]
    for role in ("config", "renderer", "wrapper", "test"):
        key = keys[role]
        expected = config["locked_inputs"][key]
        require_equal(sha256_file(repo_path(expected["path"])), expected["sha256"], f"qualitative method {key}")
    renderer_path = repo_path(config["locked_inputs"][keys["renderer"]]["path"])
    qualitative_config_path = repo_path(config["locked_inputs"][keys["config"]]["path"])
    cache_key = (kind, relative(renderer_path), relative(qualitative_config_path))
    if cache_key not in _QUALITATIVE_CONTEXT:
        renderer = load_module(f"fusion_w1_aprime_job_review_for_queue_{kind}", renderer_path)
        if kind == "panel_v4":
            panel_config, base_config = renderer.load_panel_config(qualitative_config_path)
            _QUALITATIVE_CONTEXT[cache_key] = (renderer, panel_config, base_config)
        else:
            _QUALITATIVE_CONTEXT[cache_key] = (renderer, renderer.load_config(qualitative_config_path), None)
    return _QUALITATIVE_CONTEXT[cache_key]


def verify_qualitative_complete(config: Mapping[str, Any], entry: Mapping[str, Any]) -> dict[str, Any] | None:
    path = qualitative_path(config, entry)
    if not path.exists() and not path.is_symlink():
        return None
    payload = load_json(path)
    context = qualitative_context(config)
    if len(context) == 2:  # compatibility with v3 test doubles and older callers
        renderer, qualitative_config = context
        base_config = None
    else:
        renderer, qualitative_config, base_config = context
    try:
        if config["qualitative_hook"].get("kind", "qualitative_v3") == "panel_v4":
            fully_verified = renderer.verify_bundle(
                qualitative_config, base_config, entry["building_id"], entry["arm"], entry["replicate"], None
            )
        else:
            fully_verified = renderer.verify_bundle(
                qualitative_config, entry["building_id"], entry["arm"], entry["replicate"], None
            )
    except Exception as exc:
        raise V3Error(f"qualitative full bundle verification failed: {exc}") from exc
    require_equal(fully_verified, payload, "qualitative renderer full verification payload")
    require_equal(payload.get("schema"), config["qualitative_hook"]["receipt_schema"], "qualitative receipt schema")
    require_equal(payload.get("state"), "COMPLETE", "qualitative state")
    require_equal(payload.get("measurement_state"), "MEASURED", "qualitative measurement state")
    require_equal(payload.get("identity"), {"run_id": config["run_id"], "building_id": entry["building_id"], "arm": entry["arm"], "replicate": entry["replicate"]}, "qualitative identity")
    if config["qualitative_hook"].get("kind", "qualitative_v3") == "panel_v4":
        require_equal(payload.get("panel_contract", {}).get("placeholders"), 0, "panel v4 placeholders")
        require_equal(payload.get("panel_contract", {}).get("single_visual_file"), True, "panel v4 single visual")
        require_equal(payload.get("publication", {}).get("one_visual_panel_per_job"), True, "panel v4 publication")
    else:
        require_equal(payload.get("placeholder_count"), 0, "qualitative placeholders")
        require_equal(payload.get("components"), {key: True for key in "ABCDEFGHI"}, "qualitative components")
    if payload.get("scientific_verdict") is not None or payload.get("interpretation_or_verdict") is not None or payload.get("interpretation") is not None:
        raise V3Error("qualitative receipt contains a scientific verdict")
    source = payload.get("source_readout_complete")
    if not isinstance(source, Mapping):
        raise V3Error("qualitative source readout binding missing")
    source_path = verify_record(source, "qualitative source readout")
    outputs = payload.get("outputs")
    if not isinstance(outputs, Mapping):
        raise V3Error("qualitative output records missing")
    required_output_keys = {"panel", "opacity_csv", "canonical_roofer_cityjson"}
    if not required_output_keys.issubset(outputs):
        raise V3Error(f"qualitative outputs omit {sorted(required_output_keys - set(outputs))}")
    records = _file_records(outputs)
    if len(records) < 3:
        raise V3Error("qualitative output ledger is too small")
    artifact_paths = [verify_record(record, "qualitative artifact") for record in records]
    if path.stat().st_mtime_ns < max(item.stat().st_mtime_ns for item in artifact_paths):
        raise V3Error("qualitative complete receipt was not written after its artifacts")
    # The selected renderer independently rehashes its full implementation and
    # source/reference closure before this queue accepts the receipt.
    return {"receipt": file_record(path), "payload": payload, "source_readout_complete": file_record(source_path)}


def training_job(config: Mapping[str, Any], entry: Mapping[str, Any]) -> tuple[Any, dict[str, Any], Path, Path]:
    module, training_config, config_path = training_context(config)
    path = module.job_dir(REPO, training_config, entry["building_id"], entry["arm"], entry["replicate"], "full")
    return module, training_config, config_path, path


def _producer_record(path: Path) -> dict[str, Any]:
    record = file_record(path)
    return {"path": record["path"], "sha256": record["sha256"]}


def verify_historical_training_binding(
    config: Mapping[str, Any],
    module: Any,
    training_config: Mapping[str, Any],
    entry: Mapping[str, Any],
    materialized: Path,
    completed: Path,
) -> dict[str, Any]:
    contract = config.get("historical_training_reuse_contract")
    if not isinstance(contract, Mapping) or contract.get("enabled") is not True:
        raise V3Error("historical training reuse is not enabled")
    expected_identity = identity(entry)
    if expected_identity not in contract.get("allowed_jobs", []):
        raise V3Error(f"historical training job is not allowlisted: {expected_identity}")
    materialization = load_json(materialized)
    require_equal(materialization.get("schema"), module.MATERIALIZATION_SCHEMA, "historical materialization schema")
    require_equal(materialization.get("status"), "PASSED", "historical materialization status")
    for key, expected in expected_identity.items():
        require_equal(materialization.get("replicate" if key == "replicate" else key), expected, f"historical materialization {key}")
    producer_method = materialization.get("git")
    if not isinstance(producer_method, Mapping):
        raise V3Error("historical producer method is absent")
    producer_head = str(producer_method.get("head", ""))
    require_equal(producer_head, contract["producer_head"], "historical producer HEAD")
    current_method = module.committed_method_gate(REPO, training_config)
    current_head = str(current_method["head"])
    if re.fullmatch(r"[0-9a-f]{40}", producer_head) is None:
        raise V3Error("historical producer HEAD is malformed")
    if git("merge-base", "--is-ancestor", producer_head, current_head, check=False).returncode:
        raise V3Error("historical producer HEAD is not an ancestor of current HEAD")
    require_equal(producer_method.get("branch"), current_method.get("branch"), "historical method branch")
    require_equal(producer_method.get("files"), current_method.get("files"), "historical/current method file SHA list")
    for record in current_method["files"]:
        path = str(record["path"])
        producer_blob = git("rev-parse", f"{producer_head}:{path}").stdout.strip()
        current_blob = git("rev-parse", f"{current_head}:{path}").stdout.strip()
        require_equal(producer_blob, current_blob, f"historical/current git blob {path}")
        require_equal(sha256_file(repo_path(path)), record["sha256"], f"historical/current SHA {path}")
    completion = load_json(completed)
    require_equal(completion.get("schema"), module.COMPLETED_SCHEMA, "historical completion schema")
    require_equal(completion.get("status"), "COMPLETED", "historical completion status")
    require_equal(completion.get("return_code"), 0, "historical completion return code")
    for key, expected in expected_identity.items():
        require_equal(completion.get("replicate" if key == "replicate" else key), expected, f"historical completion {key}")
    require_equal(completion.get("materialization"), _producer_record(materialized), "historical completion/materialization")
    started_path = verify_record(completion["started_receipt"], "historical started receipt")
    started = load_json(started_path)
    require_equal(started.get("schema"), module.STARTED_SCHEMA, "historical started schema")
    require_equal(started.get("status"), "STARTED", "historical started status")
    require_equal(started.get("method"), producer_method, "historical started/producer method")
    require_equal(started.get("materialization"), _producer_record(materialized), "historical started/materialization")
    for key, expected in expected_identity.items():
        require_equal(started.get("replicate" if key == "replicate" else key), expected, f"historical started {key}")
    training = completion.get("training_completion")
    if not isinstance(training, Mapping):
        raise V3Error("historical training completion evidence is absent")
    require_equal(training.get("status"), "PASSED", "historical training completion status")
    require_equal(training.get("profile"), "full", "historical training profile")
    require_equal(training.get("completed_optimizer_updates"), 30000, "historical optimizer updates")
    checkpoint_path = verify_record(training["checkpoint"], "historical step-30000 checkpoint")
    final_checkpoint_path = verify_record(training["final_checkpoint"], "historical final checkpoint")
    return {
        "reuse_mode": "ancestor_identical_method",
        "producer_head": producer_head,
        "current_head": current_head,
        "producer_head_is_ancestor": True,
        "method_files_current_identical": True,
        "materialization": file_record(materialized),
        "started": file_record(started_path),
        "completed": file_record(completed),
        "checkpoint": file_record(checkpoint_path),
        "final_checkpoint": file_record(final_checkpoint_path),
    }


def verify_training_complete(config: Mapping[str, Any], entry: Mapping[str, Any], *, allow_launch_reconcile: bool = True) -> dict[str, Any] | None:
    if entry.get("reuse_source_v2"):
        records = verify_source_reuse(config, entry)
        return {"receipt": records["training_complete"], "source_reuse": records}
    module, training_config, _config_path, job = training_job(config, entry)
    materialized = job / training_config["outputs"]["materialization_manifest"]
    completed = job / training_config["outputs"]["completed_receipt"]
    if not completed.exists() and not completed.is_symlink():
        return None
    v2 = source_v2_module(config)
    try:
        binding = v2.queue.verify_training_binding(module, training_config, entry, materialized, completed)
    except Exception as strict_error:
        try:
            binding = verify_historical_training_binding(config, module, training_config, entry, materialized, completed)
        except Exception as historical_error:
            raise V3Error(
                f"strict current training binding failed ({strict_error}); historical reuse failed ({historical_error})"
            ) from historical_error
    if binding.get("reuse_mode") == "ancestor_identical_method":
        launch = {
            "reuse_mode": "ancestor_identical_method",
            "started": binding["started"],
            "producer_head": binding["producer_head"],
        }
    else:
        launch = ensure_launch_receipt(config, entry, allow_publish=allow_launch_reconcile)
    return {"receipt": file_record(completed), "binding": binding, "lane_launch": launch}


def verify_readout_complete(config: Mapping[str, Any], entry: Mapping[str, Any]) -> dict[str, Any] | None:
    if entry.get("reuse_source_v2"):
        records = verify_source_reuse(config, entry)
        payload = load_json(verify_record(records["readout_complete"], "source readout complete"))
        return {"receipt": records["readout_complete"], "payload": payload, "primary_score": records["primary_score"], "source_reuse": records}
    v2 = source_v2_module(config)
    result = v2.verify_readout_complete(config, entry)
    if result is None:
        return None
    primary = result["payload"].get("primary") or {}
    primary_path = verify_record(primary["receipt"], "primary score receipt")
    return {**result, "primary_score": file_record(primary_path)}


def launch_root(config: Mapping[str, Any], entry: Mapping[str, Any]) -> Path:
    return repo_path(config["outputs"]["root"]) / "launches" / entry_key(entry)


def launch_attempts(config: Mapping[str, Any], entry: Mapping[str, Any]) -> list[tuple[Path, dict[str, Any]]]:
    root = launch_root(config, entry)
    if not root.is_dir():
        return []
    result = []
    for path in sorted(root.glob("attempt_[0-9][0-9][0-9]_intent.json")):
        payload = load_json(path)
        require_equal(payload.get("schema"), LAUNCH_INTENT_SCHEMA, "launch intent schema")
        require_equal(payload.get("entry"), dict(entry), "launch intent entry")
        result.append((path, payload))
    return result


def launch_receipt_path(intent_path: Path) -> Path:
    return intent_path.with_name(intent_path.name.replace("_intent.json", "_complete.json"))


def ensure_launch_receipt(config: Mapping[str, Any], entry: Mapping[str, Any], *, allow_publish: bool) -> dict[str, Any]:
    attempts = launch_attempts(config, entry)
    if not attempts:
        raise V3Error("completed v3 training lacks lane launch intent")
    intent_path, intent = attempts[-1]
    receipt_path = launch_receipt_path(intent_path)
    module, training_config, _config_path, job = training_job(config, entry)
    started_path = job / training_config["outputs"]["started_receipt"]
    completed_path = job / training_config["outputs"]["completed_receipt"]
    if not completed_path.is_file():
        raise V3Error("cannot reconcile launch before training completion")
    started = load_json(started_path)
    expected_lane = config["resources"]["lanes"][f"gpu{int(intent['physical_gpu'])}"]
    require_equal(started.get("foreground_single_job_lock"), expected_lane["lock"], "started lane lock")
    require_equal(started.get("writable_environment", {}).get("root"), expected_lane["runtime_environment"], "started lane runtime environment")
    require_equal(started.get("physical_gpu"), int(intent["physical_gpu"]), "started physical GPU")
    command = started.get("command")
    if not isinstance(command, list) or "--name" not in command:
        raise V3Error("started command lacks container name")
    container_name = command[command.index("--name") + 1]
    if not str(container_name).startswith(str(expected_lane["container_namespace"]) + "-"):
        raise V3Error("started container is outside lane namespace")
    payload = {
        "schema": LAUNCH_RECEIPT_SCHEMA,
        "state": "COMPLETE",
        "created_at": now_iso(),
        "entry": dict(entry),
        "physical_gpu": int(intent["physical_gpu"]),
        "lane": intent["lane"],
        "container_name": container_name,
        "operational_overrides": intent["operational_overrides"],
        "intent": file_record(intent_path),
        "started": file_record(started_path),
        "completed": file_record(completed_path),
        "scientific_recipe_changed": False,
        "interpretation_or_verdict": None,
    }
    if receipt_path.exists() or receipt_path.is_symlink():
        observed = load_json(receipt_path)
        for key, value in payload.items():
            if key != "created_at":
                require_equal(observed.get(key), value, f"launch receipt {key}")
        return {**observed, "receipt": file_record(receipt_path), "publication_reused": True}
    if not allow_publish:
        raise V3Error("lane launch receipt is absent")
    exclusive_json(receipt_path, payload)
    append_event(config, "TRAINING_LAUNCH_RECONCILED", {"entry": dict(entry), "receipt": file_record(receipt_path)})
    return {**payload, "receipt": file_record(receipt_path)}


def operational_training_config(config: Mapping[str, Any], base: Mapping[str, Any], gpu: int) -> tuple[dict[str, Any], dict[str, Any]]:
    if gpu not in (0, 1):
        raise V3Error(f"unsupported physical GPU: {gpu}")
    lane = config["resources"]["lanes"][f"gpu{gpu}"]
    mutated = copy.deepcopy(dict(base))
    run_root = repo_path(mutated["outputs"]["run_root"])
    lane_lock = repo_path(lane["lock"])
    try:
        lock_relative = lane_lock.relative_to(run_root).as_posix()
    except ValueError as exc:
        raise V3Error("lane lock is outside A-prime run root") from exc
    overrides = {
        "outputs.foreground_lock": {"base": base["outputs"]["foreground_lock"], "effective": lock_relative},
        "launch_contract.writable_environment_root": {"base": base["launch_contract"]["writable_environment_root"], "effective": lane["runtime_environment"]},
    }
    mutated["outputs"]["foreground_lock"] = lock_relative
    mutated["launch_contract"]["writable_environment_root"] = lane["runtime_environment"]
    check = copy.deepcopy(mutated)
    check["outputs"]["foreground_lock"] = base["outputs"]["foreground_lock"]
    check["launch_contract"]["writable_environment_root"] = base["launch_contract"]["writable_environment_root"]
    require_equal(check, dict(base), "scientific config outside operational override")
    require_equal(sorted(overrides), sorted(config["operational_training_override_contract"]["allowed_in_memory_override_keys"]), "operational override keys")
    return mutated, overrides


def launch_training(config: Mapping[str, Any], entry: Mapping[str, Any], gpu: int) -> dict[str, Any]:
    if Path("/.dockerenv").is_file():
        raise V3Error("launch-training is a host-side Docker orchestration command")
    plan = load_plan(config)
    current = entry_for(plan, entry["stage_key"], int(entry["stage_entry_order"]))
    require_equal(current, dict(entry), "launch entry")
    require_equal(current.get("reuse_source_v2"), False, "source job relaunch prohibition")
    require_equal(current.get("assigned_gpu"), gpu, "pair-assigned physical GPU")
    inspection = inspect_entry(config, current)
    require_equal(inspection.get("action"), "LAUNCH_TRAINING", "launch recommended action")
    module, base, config_path, _job = training_job(config, current)
    effective, overrides = operational_training_config(config, base, gpu)
    root = launch_root(config, current)
    root.mkdir(parents=True, exist_ok=True)
    attempt = len(launch_attempts(config, current)) + 1
    intent_path = root / f"attempt_{attempt:03d}_intent.json"
    lane_key = f"gpu{gpu}"
    lane = config["resources"]["lanes"][lane_key]
    intent = {
        "schema": LAUNCH_INTENT_SCHEMA,
        "state": "INTENDED",
        "created_at": now_iso(),
        "attempt": attempt,
        "entry": dict(current),
        "lane": lane_key,
        "physical_gpu": gpu,
        "container_namespace": lane["container_namespace"],
        "operational_overrides": overrides,
        "base_training_config": file_record(config_path),
        "scientific_recipe_changed": False,
        "interpretation_or_verdict": None,
    }
    exclusive_json(intent_path, intent)
    original_docker_command = module.docker_command
    suffix = hashlib.sha256(f"{current['building_id']}|{current['arm']}|{current['replicate']}".encode()).hexdigest()[:12]
    container_name = f"{lane['container_namespace']}-{suffix}"

    def namespaced_command(**kwargs: Any) -> list[str]:
        command = original_docker_command(**kwargs)
        index = command.index("--name") + 1
        command[index] = container_name
        return command

    module.docker_command = namespaced_command
    try:
        result = module.launch(repo=REPO, config_path=config_path, config=effective, building_id=current["building_id"], arm=current["arm"], run=current["replicate"], profile="full", gpu=gpu)
    finally:
        module.docker_command = original_docker_command
    receipt = ensure_launch_receipt(config, current, allow_publish=True)
    append_event(config, "TRAINING_LAUNCH_COMPLETED", {"entry": dict(current), "lane": lane_key, "physical_gpu": gpu, "launch_receipt": receipt["receipt"]})
    return {"state": "COMPLETED", "training": result, "lane_launch": receipt}


def action_failure_root(config: Mapping[str, Any], entry: Mapping[str, Any]) -> Path:
    return output_path(config, "action_failures") / entry_key(entry)


def action_failures(config: Mapping[str, Any], entry: Mapping[str, Any]) -> list[dict[str, Any]]:
    root = action_failure_root(config, entry)
    if not root.is_dir():
        return []
    result = []
    for path in sorted(root.glob("attempt_[0-9][0-9][0-9].json")):
        payload = load_json(path)
        require_equal(payload.get("schema"), ACTION_FAILURE_SCHEMA, "action failure schema")
        require_equal(payload.get("entry"), dict(entry), "action failure entry")
        result.append({"receipt": file_record(path), "payload": payload})
    return result


def stable_failure_signature(action: str, error_type: str, message: str, return_code: int | None) -> str:
    return hashlib.sha256("\0".join((action.strip(), error_type.strip(), message.strip(), str(return_code))).encode()).hexdigest()


def record_action_failure(config: Mapping[str, Any], entry: Mapping[str, Any], *, invocation_id: str, action: str, error_type: str, message: str, return_code: int | None, log_path: Path | None) -> dict[str, Any]:
    if not re.fullmatch(r"[A-Za-z0-9_.:-]{1,160}", invocation_id):
        raise V3Error("invalid action invocation ID")
    if action not in config["failure_contract"]["failure_actions"]:
        raise V3Error(f"unsupported failing action: {action}")
    if load_stage_record(config, entry) is not None:
        raise V3Error("cannot attach failure to terminal entry")
    signature = stable_failure_signature(action, error_type, message, return_code)
    log = file_record(repo_path(log_path), allow_empty=True) if log_path is not None else None
    existing = action_failures(config, entry)
    for item in existing:
        if item["payload"].get("invocation_id") == invocation_id:
            basis = (item["payload"].get("action"), item["payload"].get("error_type"), item["payload"].get("message"), item["payload"].get("return_code"))
            require_equal(basis, (action, error_type, message, return_code), "reused invocation basis")
            return {**item["payload"], "receipt": item["receipt"], "publication_reused": True}
    root = action_failure_root(config, entry); root.mkdir(parents=True, exist_ok=True)
    path = root / f"attempt_{len(existing) + 1:03d}.json"
    payload = {"schema": ACTION_FAILURE_SCHEMA, "state": "FAILED", "created_at": now_iso(), "attempt": len(existing) + 1, "invocation_id": invocation_id, "entry": dict(entry), "action": action, "error_type": error_type, "message": message, "return_code": return_code, "error_signature": signature, "log": log, "partial_artifacts_preserved": True, "interpretation_or_verdict": None}
    exclusive_json(path, payload)
    append_event(config, "ACTION_FAILED", {"entry": dict(entry), "action": action, "failure": file_record(path), "error_type": error_type, "error_signature": signature})
    return {**payload, "receipt": file_record(path)}


def three_same_action_failure(config: Mapping[str, Any], entry: Mapping[str, Any]) -> dict[str, Any] | None:
    failures = action_failures(config, entry)
    if len(failures) < 3:
        return None
    recent = failures[-3:]
    signatures = [item["payload"].get("error_signature") for item in recent]
    if signatures[0] and len(set(signatures)) == 1:
        return {"source": "orchestrator_action_failures", "error_signature": signatures[0], "error_type": recent[-1]["payload"].get("error_type", "UnknownError"), "attempts": [item["receipt"] for item in recent]}
    return None


def archive_root(config: Mapping[str, Any], entry: Mapping[str, Any]) -> Path:
    return output_path(config, "training_failure_archive") / "by_building" / entry["building_id"] / f"arm_{entry['arm']}" / entry["replicate"]


def recursive_ledger(root: Path) -> list[dict[str, Any]]:
    if not root.is_dir() or root.is_symlink():
        raise V3Error(f"ledger root is invalid: {relative(root)}")
    result = []
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise V3Error(f"symlink forbidden in training archive: {relative(path)}")
        if path.is_file():
            record = file_record(path, allow_empty=True)
            record["relative_to_root"] = path.relative_to(root).as_posix()
            result.append(record)
    if not result:
        raise V3Error("refusing empty training archive")
    return result


def training_archives(config: Mapping[str, Any], entry: Mapping[str, Any]) -> list[dict[str, Any]]:
    root = archive_root(config, entry)
    if not root.is_dir():
        return []
    result = []
    for directory in sorted(root.glob("attempt_[0-9][0-9][0-9]")):
        if not directory.is_dir() or directory.is_symlink():
            continue
        path = directory / "archive_receipt.json"
        payload = load_json(path)
        require_equal(payload.get("schema"), ARCHIVE_SCHEMA, "archive schema")
        require_equal(payload.get("identity"), identity(entry), "archive identity")
        for record in payload.get("move_verification", []):
            verify_record(record, "archived training artifact")
        result.append({"receipt": file_record(path), "payload": payload, "path": directory})
    return result


def pending_archive(config: Mapping[str, Any], entry: Mapping[str, Any]) -> Path | None:
    root = archive_root(config, entry)
    if not root.is_dir():
        return None
    values = sorted(root.glob("attempt_[0-9][0-9][0-9].incomplete"))
    if len(values) > 1:
        raise V3Error("multiple incomplete archives for one job")
    return values[0] if values else None


def archived_skip(config: Mapping[str, Any], entry: Mapping[str, Any]) -> dict[str, Any] | None:
    archives = training_archives(config, entry)
    if len(archives) < 3:
        return None
    recent = archives[-3:]
    signatures = [item["payload"].get("error_signature") for item in recent]
    if signatures[0] and len(set(signatures)) == 1:
        return {"source": "training_failure_archive", "error_signature": signatures[0], "error_type": recent[-1]["payload"].get("error_type", "TrainingFailure"), "attempts": [item["receipt"] for item in recent]}
    return None


def readout_skip(config: Mapping[str, Any], entry: Mapping[str, Any]) -> dict[str, Any] | None:
    if entry.get("reuse_source_v2"):
        return None
    v2 = source_v2_module(config)
    failures = v2.queue.readout_failures(config, entry)
    if len(failures) < 3:
        return None
    recent = failures[-3:]
    signatures = [item["payload"].get("error_signature") for item in recent]
    if signatures[0] and len(set(signatures)) == 1:
        return {"source": "readout_failure_receipts", "error_signature": signatures[0], "error_type": recent[-1]["payload"].get("error_type", "ReadoutFailure"), "attempts": [item["receipt"] for item in recent]}
    return None


def terminal_skip(config: Mapping[str, Any], entry: Mapping[str, Any]) -> dict[str, Any] | None:
    return archived_skip(config, entry) or readout_skip(config, entry) or three_same_action_failure(config, entry)


def _orphan_failure(module: Any, training_config: Mapping[str, Any], job: Path, entry: Mapping[str, Any]) -> tuple[dict[str, Any], Path]:
    failed_path = job / training_config["outputs"]["failed_receipt"]
    if failed_path.is_file() and not failed_path.is_symlink():
        payload = load_json(failed_path)
        require_equal(payload.get("schema"), module.FAILED_SCHEMA, "training failure schema")
        require_equal(payload.get("status"), "FAILED", "training failure status")
        return payload, failed_path
    started_path = job / training_config["outputs"]["started_receipt"]
    completed_path = job / training_config["outputs"]["completed_receipt"]
    materialized_path = job / training_config["outputs"]["materialization_manifest"]
    reason = "training_receipts_or_materialization_do_not_match_runtime_head" if completed_path.is_file() else ("started_without_terminal_receipt_and_no_live_lane_lock" if started_path.is_file() else "nonempty_canonical_training_dir_without_materialization")
    path = job / "v3_orchestrator_orphan_failure.json"
    expected_identity = identity(entry)
    payload = {"schema": ORPHAN_SCHEMA, "status": "FAILED", "created_at": now_iso(), "identity": expected_identity, "error_type": "OrphanedTrainingAttempt", "reason": reason, "return_code": None, "started_receipt": file_record(started_path) if started_path.is_file() else None, "materialization": file_record(materialized_path) if materialized_path.is_file() else None, "partial_outputs_preserved": True, "interpretation_or_verdict": None}
    if path.exists() or path.is_symlink():
        observed = load_json(path)
        require_equal(observed.get("schema"), ORPHAN_SCHEMA, "orphan schema")
        require_equal(observed.get("identity"), expected_identity, "orphan identity")
        return observed, path
    exclusive_json(path, payload)
    return payload, path


def _projected_record(path: Path, projected: Path) -> dict[str, Any]:
    record = file_record(path, allow_empty=True)
    record["path"] = relative(projected)
    return record


def archive_training(config: Mapping[str, Any], entry: Mapping[str, Any]) -> dict[str, Any]:
    inspection = inspect_entry(config, entry)
    require_equal(inspection.get("action"), "ARCHIVE_TRAINING", "archive recommended action")
    module, training_config, _config_path, job = training_job(config, entry)
    started_path = job / training_config["outputs"]["started_receipt"]
    if started_path.is_file():
        started = load_json(started_path)
        raw_lock = started.get("foreground_single_job_lock")
        if isinstance(raw_lock, str) and lock_is_busy_readonly(repo_path(raw_lock), require_exists=True):
            raise V3Error("refusing to archive a live lane training job")
    root = archive_root(config, entry); root.mkdir(parents=True, exist_ok=True)
    staging = pending_archive(config, entry)
    if staging is None:
        if not job.is_dir() or job.is_symlink() or not any(job.iterdir()):
            raise V3Error("canonical failed training job is absent/empty")
        attempt = len(training_archives(config, entry)) + 1
        final = root / f"attempt_{attempt:03d}"
        staging = root / f"attempt_{attempt:03d}.incomplete"
        if final.exists() or staging.exists():
            raise V3Error("archive destination already exists")
        staging.mkdir()
        failure, terminal_path = _orphan_failure(module, training_config, job, entry)
        ledger = recursive_ledger(job)
        ledger_path = staging / "pre_move_ledger.json"
        exclusive_json(ledger_path, {"schema": ARCHIVE_LEDGER_SCHEMA, "created_at": now_iso(), "source_path": relative(job), "artifacts": ledger, "artifact_count": len(ledger)})
        error_type = str(failure.get("error_type", "TrainingFailure")); reason = str(failure.get("reason", "training failed")); return_code = failure.get("return_code")
        intent = {"schema": ARCHIVE_INTENT_SCHEMA, "created_at": now_iso(), "attempt": attempt, "identity": identity(entry), "source_path": relative(job), "final_destination": relative(final), "original_terminal_receipt": file_record(terminal_path), "original_terminal_relative_to_job": terminal_path.relative_to(job).as_posix(), "error_type": error_type, "reason": reason, "return_code": return_code, "error_signature": stable_failure_signature("training", error_type, reason, return_code), "partial_artifacts_preserved": True, "interpretation_or_verdict": None}
        exclusive_json(staging / "move_intent.json", intent)
    intent = load_json(staging / "move_intent.json")
    attempt = int(intent["attempt"]); final = root / f"attempt_{attempt:03d}"; nested = staging / "training_job"
    ledger_payload = load_json(staging / "pre_move_ledger.json")
    require_equal(ledger_payload.get("schema"), ARCHIVE_LEDGER_SCHEMA, "archive ledger schema")
    if nested.exists():
        if job.exists():
            raise V3Error("both canonical and staged training jobs exist")
    else:
        if not job.is_dir() or job.is_symlink():
            raise V3Error("neither canonical nor staged training job exists")
        os.replace(job, nested); fsync_directory(job.parent); fsync_directory(staging)
    verification = []
    final_nested = final / "training_job"
    for original in ledger_payload["artifacts"]:
        rel = str(original["relative_to_root"])
        observed = _projected_record(nested / rel, final_nested / rel)
        require_equal(observed["sha256"], original["sha256"], "archived artifact SHA")
        require_equal(observed["bytes"], original["bytes"], "archived artifact bytes")
        verification.append(observed)
    terminal_rel = str(intent["original_terminal_relative_to_job"])
    archived_terminal = _projected_record(nested / terminal_rel, final_nested / terminal_rel)
    receipt_path = staging / "archive_receipt.json"
    payload = {"schema": ARCHIVE_SCHEMA, "state": "ARCHIVED", "created_at": now_iso(), "attempt": attempt, "identity": identity(entry), "source_path": intent["source_path"], "destination_path": relative(final), "original_terminal_receipt": intent["original_terminal_receipt"], "archived_terminal_receipt": archived_terminal, "move_verification": verification, "artifact_count": len(verification), "error_type": intent["error_type"], "reason": intent["reason"], "return_code": intent.get("return_code"), "error_signature": intent["error_signature"], "canonical_path_absent_after_move": True, "partial_artifacts_preserved": True, "append_only_archive": True, "interpretation_or_verdict": None}
    if not receipt_path.exists():
        exclusive_json(receipt_path, payload)
    if final.exists():
        raise V3Error("final archive exists before incomplete publication")
    os.replace(staging, final); fsync_directory(root)
    for record in verification:
        verify_record(record, "final archived artifact")
    if job.exists() or job.is_symlink():
        raise V3Error("canonical training job remained after archive")
    final_receipt = final / "archive_receipt.json"
    append_event(config, "TRAINING_FAILURE_ARCHIVED", {"entry": dict(entry), "archive": file_record(final_receipt), "attempt": attempt, "error_signature": intent["error_signature"]})
    return load_json(final_receipt)


def training_state(config: Mapping[str, Any], entry: Mapping[str, Any]) -> dict[str, Any]:
    if entry.get("reuse_source_v2"):
        source = verify_source_reuse(config, entry)
        return {"state": "TRAINED", "action": "RUN_READOUT", "source_reuse": source}
    module, training_config, _config_path, job = training_job(config, entry)
    names = training_config["outputs"]
    paths = {"materialization": job / names["materialization_manifest"], "started": job / names["started_receipt"], "completed": job / names["completed_receipt"], "failed": job / names["failed_receipt"]}
    present = {key: path.is_file() and not path.is_symlink() for key, path in paths.items()}
    if present["failed"] or (present["completed"] and present["failed"]):
        return {"state": "TRAINING_FAILED", "action": "ARCHIVE_TRAINING", "receipt_presence": present}
    if present["started"] and not present["completed"]:
        started = load_json(paths["started"])
        raw_lock = started.get("foreground_single_job_lock")
        if isinstance(raw_lock, str) and lock_is_busy_readonly(repo_path(raw_lock), require_exists=True):
            return {"state": "TRAINING", "action": "WAIT_TRAINING", "receipt_presence": present, "lane_lock": raw_lock}
        return {"state": "TRAINING_FAILED", "action": "ARCHIVE_TRAINING", "receipt_presence": present, "orphan_reason": "started_without_terminal_receipt_and_no_live_lane_lock"}
    if job.exists() and not present["materialization"] and any(job.iterdir()):
        return {"state": "TRAINING_FAILED", "action": "ARCHIVE_TRAINING", "receipt_presence": present, "orphan_reason": "nonempty_job_without_materialization"}
    if present["completed"]:
        try:
            complete = verify_training_complete(config, entry)
        except Exception as exc:
            return {"state": "TRAINING_FAILED", "action": "ARCHIVE_TRAINING", "receipt_presence": present, "orphan_reason": "training_binding_invalid", "binding_error_type": type(exc).__name__, "binding_error": str(exc)}
        return {"state": "TRAINED", "action": "RUN_READOUT", "training_complete": complete}
    if present["materialization"]:
        try:
            v2 = source_v2_module(config)
            v2.queue.verify_training_binding(module, training_config, entry, paths["materialization"], None)
        except Exception as exc:
            return {"state": "TRAINING_FAILED", "action": "ARCHIVE_TRAINING", "receipt_presence": present, "orphan_reason": "materialization_binding_invalid", "binding_error_type": type(exc).__name__, "binding_error": str(exc)}
        return {"state": "MATERIALIZED", "action": "LAUNCH_TRAINING", "materialization": file_record(paths["materialization"])}
    return {"state": "MISSING", "action": "MATERIALIZE_TRAINING"}


def inspect_entry(config: Mapping[str, Any], entry: Mapping[str, Any]) -> dict[str, Any]:
    record = load_stage_record(config, entry)
    if record is not None:
        return {"state": record["status"], "action": "NONE", "terminal": file_record(stage_record_path(config, entry))}
    skip = terminal_skip(config, entry)
    if skip is not None:
        return {"state": "SKIPPED", "action": "RECORD_TERMINAL", "skip": skip}
    readout = verify_readout_complete(config, entry)
    if readout is not None:
        qualitative = verify_qualitative_complete(config, entry)
        if qualitative is None:
            return {"state": "QUANTITATIVE_COMPLETE", "action": "RUN_QUALITATIVE", "training_complete": verify_training_complete(config, entry), "readout_complete": readout}
        return {"state": "READY_MEASURED", "action": "RECORD_TERMINAL", "training_complete": verify_training_complete(config, entry), "readout_complete": readout, "qualitative_complete": qualitative}
    pending = pending_archive(config, entry)
    if pending is not None:
        return {"state": "TRAINING_FAILED", "action": "ARCHIVE_TRAINING", "pending_archive": relative(pending)}
    state = training_state(config, entry)
    if state["state"] == "TRAINED" and not entry.get("reuse_source_v2"):
        v2 = source_v2_module(config)
        failures = v2.queue.readout_failures(config, entry)
        if failures:
            state["state"] = "READOUT_FAILED"
            state["readout_failure_attempts"] = len(failures)
    return state


def record_terminal(config: Mapping[str, Any], entry: Mapping[str, Any]) -> dict[str, Any]:
    existing = load_stage_record(config, entry)
    if existing is not None:
        return {**existing, "receipt": file_record(stage_record_path(config, entry)), "publication_reused": True}
    inspection = inspect_entry(config, entry)
    require_equal(inspection.get("action"), "RECORD_TERMINAL", "terminal recommended action")
    if inspection["state"] == "SKIPPED":
        skip = inspection["skip"]
        receipts = [dict(record) for record in skip["attempts"]]
        for receipt in receipts:
            verify_record(receipt, "skip evidence")
        payload = {
            "schema": STAGE_RECORD_SCHEMA,
            "status": "SKIPPED",
            "created_at": now_iso(),
            "entry": dict(entry),
            "source": skip["source"],
            "components": None,
            "source_receipts": receipts,
            "error_type": skip["error_type"],
            "error_signature": skip["error_signature"],
            "same_signature_attempts": len(receipts),
            "partial_results_reviewable": True,
            "interpretation_or_verdict": None,
        }
    else:
        require_equal(inspection.get("state"), "READY_MEASURED", "measured terminal state")
        training = inspection["training_complete"]
        readout = inspection["readout_complete"]
        qualitative = inspection["qualitative_complete"]
        primary = readout["primary_score"]
        for label, record in (("training", training["receipt"]), ("readout", readout["receipt"]), ("primary", primary), ("qualitative", qualitative["receipt"])):
            verify_record(record, f"terminal {label} receipt")
        components = {
            "training_complete": dict(training["receipt"]),
            "readout_complete": dict(readout["receipt"]),
            "primary_quantitative_score": dict(primary),
            "qualitative_complete": dict(qualitative["receipt"]),
        }
        require_equal(sorted(components), sorted(config["terminal_contract"]["measured_requires"]), "terminal component names")
        payload = {
            "schema": STAGE_RECORD_SCHEMA,
            "status": "MEASURED",
            "created_at": now_iso(),
            "entry": dict(entry),
            "source": "four_component_job_terminal",
            "components": components,
            "source_receipts": list(components.values()),
            "source_v2_reuse": training.get("source_reuse") if entry.get("reuse_source_v2") else None,
            "error_type": None,
            "error_signature": None,
            "same_signature_attempts": None,
            "partial_results_reviewable": True,
            "interpretation_or_verdict": None,
        }
    path = stage_record_path(config, entry)
    exclusive_json(path, payload)
    append_event(config, f"ENTRY_{payload['status']}", {"entry": dict(entry), "stage_record": file_record(path), "error_type": payload["error_type"]})
    return {**payload, "receipt": file_record(path)}


def pair_for(plan: Mapping[str, Any], pair_id: str) -> dict[str, Any]:
    matches = [dict(pair) for pair in plan["pairs"] if pair["pair_id"] == pair_id]
    if len(matches) != 1:
        raise V3Error(f"pair resolution failed: {pair_id}")
    return matches[0]


def pair_member_entries(plan: Mapping[str, Any], pair: Mapping[str, Any]) -> list[dict[str, Any]]:
    return [entry_for(plan, member["stage_key"], int(member["stage_entry_order"])) for member in pair["members"]]


def assert_no_training(config: Mapping[str, Any], *, inspect_processes: bool = True) -> dict[str, Any]:
    locks = []
    for lane_key in ("gpu0", "gpu1"):
        path = repo_path(config["resources"]["lanes"][lane_key]["lock"])
        busy = lock_is_busy_readonly(path)
        locks.append({"lane": lane_key, "path": relative(path), "busy": busy})
    if any(item["busy"] for item in locks):
        raise V3Error("training lane lock remains held before readout")
    processes: list[str] = []
    if inspect_processes and not Path("/.dockerenv").is_file():
        result = subprocess.run(["pgrep", "-af", "src.stage2.train"], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
        if result.returncode not in (0, 1):
            raise V3Error("cannot inspect training processes")
        processes = [line for line in result.stdout.splitlines() if line.strip() and str(os.getpid()) not in line.split(maxsplit=1)[0:1]]
        if processes:
            raise V3Error(f"training process remains before readout: {processes}")
    return {"state": "NO_TRAINING", "lane_locks": locks, "process_scan_performed": inspect_processes and not Path("/.dockerenv").is_file(), "matching_processes": processes}


def gpu_boundary(config: Mapping[str, Any], pair_id: str, gpu: int) -> dict[str, Any]:
    if gpu not in (0, 1):
        raise V3Error("GPU boundary accepts only physical GPU0/GPU1")
    plan = load_plan(config)
    pair = pair_for(plan, pair_id)
    if gpu not in {int(member["physical_gpu"]) for member in pair["members"]}:
        raise V3Error(f"GPU{gpu} is not assigned in pair {pair_id}")
    query = subprocess.run(["nvidia-smi", f"--id={gpu}", "--query-gpu=uuid,memory.total,memory.free", "--format=csv,noheader,nounits"], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    if query.returncode:
        raise V3Error(query.stderr.strip() or f"cannot query GPU{gpu}")
    values = [item.strip() for item in query.stdout.strip().split(",")]
    if len(values) != 3 or not values[0].startswith("GPU-"):
        raise V3Error(f"malformed GPU{gpu} boundary query")
    uuid, total_raw, free_raw = values
    total, free = int(total_raw), int(free_raw)
    gate = config["resources"]["gpu_boundary_gate"]
    if free < int(gate["minimum_free_memory_mib"]):
        raise GpuBoundaryUnavailable(f"GPU{gpu} free VRAM below floor: {free} MiB < {gate['minimum_free_memory_mib']} MiB")
    apps = subprocess.run(["nvidia-smi", "--query-compute-apps=gpu_uuid,pid,process_name,used_memory", "--format=csv,noheader,nounits"], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    if apps.returncode:
        raise V3Error(apps.stderr.strip() or "cannot query GPU compute apps")
    observed_apps = []
    for line in apps.stdout.splitlines():
        if not line.strip():
            continue
        fields = [item.strip() for item in line.split(",")]
        if len(fields) != 4:
            raise V3Error(f"malformed GPU compute row: {line}")
        app_uuid, pid_raw, process_name, memory_raw = fields
        if app_uuid != uuid:
            continue
        pid = int(pid_raw)
        proc = Path("/proc") / str(pid)
        try:
            owner_uid = proc.stat().st_uid
            cmdline = [part.decode("utf-8") for part in (proc / "cmdline").read_bytes().split(b"\0") if part]
        except FileNotFoundError as exc:
            raise GpuBoundaryUnavailable(f"GPU process PID {pid} vanished during /proc verification") from exc
        except (OSError, UnicodeDecodeError) as exc:
            raise V3Error(f"cannot verify GPU process identity for PID {pid}: {exc}") from exc
        observed_apps.append({"pid": pid, "process_name": process_name, "cmdline": cmdline, "owner_uid": owner_uid, "used_memory_mib": int(memory_raw)})
    allowed = gate[f"gpu{gpu}_exact_allowlist"]
    for app in observed_apps:
        if not gpu_app_is_allowlisted(app, allowed, current_uid=os.getuid()):
            raise GpuBoundaryUnavailable(f"GPU{gpu} has non-allowlisted live compute process: {app}")
    root = output_path(config, "pairs") / pair_id / "gpu_boundaries"
    root.mkdir(parents=True, exist_ok=True)
    existing = sorted(root.glob(f"gpu{gpu}_attempt_[0-9][0-9][0-9].json"))
    path = root / f"gpu{gpu}_attempt_{len(existing) + 1:03d}.json"
    payload = {"schema": "jointbuildgs.fusion_w1_aprime.unattended_continuation_v3.gpu_boundary.v1", "state": "READY", "created_at": now_iso(), "pair_id": pair_id, "physical_gpu": gpu, "gpu_uuid": uuid, "memory_total_mib": total, "memory_free_mib": free, "minimum_free_memory_mib": int(gate["minimum_free_memory_mib"]), "compute_apps": observed_apps, "exact_allowlist": allowed, "all_observed_apps_allowlisted": True, "interpretation_or_verdict": None}
    exclusive_json(path, payload)
    append_event(config, "GPU_BOUNDARY_READY", {"pair_id": pair_id, "physical_gpu": gpu, "receipt": file_record(path), "memory_free_mib": free, "compute_apps": observed_apps})
    return {**payload, "receipt": file_record(path)}


def gpu_app_is_allowlisted(app: Mapping[str, Any], allowlist: Sequence[Mapping[str, Any]], *, current_uid: int) -> bool:
    matches = [item for item in allowlist if item.get("process_name") == app.get("process_name") and item.get("cmdline") == app.get("cmdline") and item.get("required_owner") == "current_uid" and int(app.get("owner_uid", -1)) == current_uid and int(app.get("used_memory_mib", -1)) <= int(item.get("maximum_used_memory_mib", -1))]
    return len(matches) == 1


def wait_gpu_boundary(config: Mapping[str, Any], pair_id: str, gpu: int, *, require_host: bool = True) -> dict[str, Any]:
    if require_host and Path("/.dockerenv").is_file():
        raise V3Error("wait-gpu-boundary must inspect the host GPU/PID namespace")
    poll_seconds = int(config["resources"]["gpu_boundary_gate"]["poll_seconds"])
    require_equal(poll_seconds, 30, "GPU boundary poll seconds")
    attempt = 0
    while True:
        attempt += 1
        try:
            result = gpu_boundary(config, pair_id, gpu)
            return {**result, "wait_attempts": attempt, "poll_seconds": poll_seconds, "time_cutoff": None}
        except GpuBoundaryUnavailable as exc:
            message = " ".join(str(exc).split())[:512]
            print(f"GPU_BOUNDARY_WAIT pair={pair_id} physical_gpu={gpu} attempt={attempt} reason={message}", file=sys.stderr, flush=True)
            time.sleep(poll_seconds)


def pair_training_ready(config: Mapping[str, Any], pair_id: str) -> dict[str, Any]:
    plan = load_plan(config)
    pair = pair_for(plan, pair_id)
    members = pair_member_entries(plan, pair)
    states = []
    for entry in members:
        inspection = inspect_entry(config, entry)
        if inspection["state"] not in TRAINING_READY:
            raise V3Error(f"pair training barrier not ready: {entry['building_id']} state={inspection['state']}")
        if inspection["state"] != "SKIPPED" and load_stage_record(config, entry) is None:
            training_complete = inspection.get("training_complete")
            binding = training_complete.get("binding", {}) if isinstance(training_complete, Mapping) else {}
            if binding.get("reuse_mode") != "ancestor_identical_method":
                ensure_launch_receipt(config, entry, allow_publish=True)
        states.append({"entry": dict(entry), "state": inspection["state"], "action": inspection["action"]})
    no_training = assert_no_training(config, inspect_processes=False)
    root = output_path(config, "pairs") / pair_id
    root.mkdir(parents=True, exist_ok=True)
    path = root / "training_ready.json"
    payload = {"schema": PAIR_SCHEMA, "state": "TRAINING_READY", "created_at": now_iso(), "pair": pair, "member_states": states, "no_training": no_training, "readout_may_start": True, "interpretation_or_verdict": None}
    if path.exists() or path.is_symlink():
        observed = load_json(path)
        require_equal(observed.get("pair"), pair, "pair receipt pair")
        return {**observed, "receipt": file_record(path), "publication_reused": True}
    exclusive_json(path, payload)
    append_event(config, "PAIR_TRAINING_READY", {"pair_id": pair_id, "receipt": file_record(path), "member_states": states})
    return {**payload, "receipt": file_record(path)}


def consecutive_skip_stop(records: Sequence[tuple[Mapping[str, Any], Mapping[str, Any]]]) -> dict[str, Any] | None:
    if len(records) < 3:
        return None
    recent = records[-3:]
    errors = [str(record.get("error_type") or "") for _entry, record in recent]
    if not all(record.get("status") == "SKIPPED" for _entry, record in recent) or not errors[0] or len(set(errors)) != 1:
        return None
    return {"reason_code": "SAME_ERROR_TYPE_THREE_CONSECUTIVE_BUILDINGS", "error_type": errors[0], "consecutive_buildings": [entry["building_id"] for entry, _record in recent]}


def stage_stop_check(config: Mapping[str, Any]) -> dict[str, Any]:
    path = output_path(config, "stage_stop")
    if path.exists() or path.is_symlink():
        payload = load_json(path); require_equal(payload.get("schema"), STOP_SCHEMA, "stage stop schema")
        return {**payload, "receipt": file_record(path), "publication_reused": True}
    plan = load_plan(config)
    for stage_order in sorted({int(entry["stage_order"]) for entry in plan["entries"]}):
        stage_entries = [entry for entry in plan["entries"] if int(entry["stage_order"]) == stage_order]
        contiguous: list[tuple[Mapping[str, Any], Mapping[str, Any]]] = []
        for entry in stage_entries:
            record = load_stage_record(config, entry)
            if record is None:
                break
            contiguous.append((entry, record))
        if len(contiguous) < 3:
            continue
        recent = contiguous[-3:]
        cause = consecutive_skip_stop(contiguous)
        if cause is not None:
            payload = {
                "schema": STOP_SCHEMA,
                "state": "STOPPED_THREE_CONSECUTIVE_BUILDING_SKIPS",
                "created_at": now_iso(),
                "stage_order": stage_order,
                "stage_key": recent[-1][0]["stage_key"],
                "last_entry": dict(recent[-1][0]),
                "cause": {**cause, "stage_record_receipts": [file_record(stage_record_path(config, entry)) for entry, _record in recent]},
                "later_stages_not_started_by_orchestrator": True,
                "partial_results_reviewable": True,
                "interpretation_or_verdict": None,
            }
            exclusive_json(path, payload)
            append_event(config, "STAGE_STOPPED", {"stage_stop": file_record(path), "stage_key": payload["stage_key"], "error_type": cause["error_type"]})
            return {**payload, "receipt": file_record(path)}
    return {"state": "CONTINUE", "stage_stop": None}


@contextmanager
def publication_lock(config: Mapping[str, Any]):
    path = output_path(config, "publication_lock")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as stream:
        fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def _publish_status_unlocked(config: Mapping[str, Any]) -> dict[str, Any]:
    complete_path = output_path(config, "complete")
    status_path = output_path(config, "status_json")
    if complete_path.is_file() or complete_path.is_symlink():
        complete_payload = load_json(complete_path)
        verify_complete_payload(config, complete_payload)
        status_payload = load_json(status_path)
        require_equal(complete_payload.get("status_json"), file_record(status_path), "complete/status immutable binding")
        return {**status_payload, "publication_reused": True}
    plan = load_plan(config)
    rows = []
    for entry in plan["entries"]:
        try:
            inspection = inspect_entry(config, entry)
            pipeline_state = inspection["state"]; next_action = inspection["action"]
            error_type = (inspection.get("skip") or {}).get("error_type") if isinstance(inspection.get("skip"), Mapping) else None
            inspection_error = None
        except Exception as exc:
            pipeline_state = "FAILED"; next_action = "INSPECTION_REQUIRED"; error_type = type(exc).__name__; inspection_error = str(exc)
        record = load_stage_record(config, entry)
        outcome = record["status"] if record is not None else ("FAILED" if pipeline_state == "FAILED" or pipeline_state.endswith("_FAILED") else "MISSING")
        terminal_receipt = file_record(stage_record_path(config, entry)) if record is not None else None
        rows.append({**dict(entry), "outcome_status": outcome, "pipeline_state": pipeline_state, "next_action": next_action, "error_type": error_type, "inspection_error": inspection_error, "terminal_receipt_path": terminal_receipt["path"] if terminal_receipt else "", "terminal_receipt_sha256": terminal_receipt["sha256"] if terminal_receipt else ""})
    fields = ("v3_global_order", "stage_order", "stage_key", "stage_entry_order", "building_id", "arm", "replicate", "profile", "pair_id", "assigned_gpu", "outcome_status", "pipeline_state", "next_action", "error_type", "inspection_error", "terminal_receipt_path", "terminal_receipt_sha256")
    csv_path = output_path(config, "status_csv"); atomic_csv(csv_path, rows, fields)
    counts = {state: sum(row["outcome_status"] == state for row in rows) for state in ("MEASURED", "FAILED", "SKIPPED", "MISSING")}
    stop_path = output_path(config, "stage_stop")
    payload = {"schema": STATUS_SCHEMA, "state": "SNAPSHOT", "created_at": now_iso(), "plan": file_record(output_path(config, "plan")), "rows": rows, "counts": counts, "stage_stop": file_record(stop_path) if stop_path.is_file() else None, "status_csv": file_record(csv_path), "queue_complete_exists": output_path(config, "complete").is_file(), "interpretation_or_verdict": None}
    atomic_json(status_path, payload)
    return payload


def publish_status(config: Mapping[str, Any]) -> dict[str, Any]:
    with publication_lock(config):
        return _publish_status_unlocked(config)


def finalize(config: Mapping[str, Any]) -> dict[str, Any]:
    with publication_lock(config):
        path = output_path(config, "complete")
        if path.exists() or path.is_symlink():
            payload = load_json(path); verify_complete_payload(config, payload)
            return {**payload, "publication_reused": True}
        plan = load_plan(config)
        stop_path = output_path(config, "stage_stop")
        records = []
        for entry in plan["entries"]:
            record = load_stage_record(config, entry)
            if record is not None:
                records.append({"entry": dict(entry), "status": record["status"], "receipt": file_record(stage_record_path(config, entry))})
        if stop_path.is_file():
            state = load_json(stop_path)["state"]
        else:
            require_equal(len(records), len(plan["entries"]), "terminal job count")
            state = "COMPLETE"
        status = _publish_status_unlocked(config)
        events_path = output_path(config, "events")
        payload = {"schema": COMPLETE_SCHEMA, "state": state, "created_at": now_iso(), "run_id": config["run_id"], "task_id": config["task_id"], "git_head": git("rev-parse", "HEAD").stdout.strip(), "plan": file_record(output_path(config, "plan")), "stage_stop": file_record(stop_path) if stop_path.is_file() else None, "stage_records": records, "counts": status["counts"], "terminal_jobs_n": len(records), "status_json": file_record(output_path(config, "status_json")), "status_csv": file_record(output_path(config, "status_csv")), "events": file_record(events_path), "partial_results_reviewable": True, "root_complete_receipt_written_last": True, "interpretation_or_verdict": None}
        exclusive_json(path, payload)
        return payload


def verify_complete_payload(config: Mapping[str, Any], payload: Mapping[str, Any]) -> None:
    require_equal(payload.get("schema"), COMPLETE_SCHEMA, "complete schema")
    require_equal(payload.get("run_id"), config["run_id"], "complete run")
    require_equal(payload.get("task_id"), config["task_id"], "complete task")
    require_equal(payload.get("git_head"), git("rev-parse", "HEAD").stdout.strip(), "complete/current HEAD")
    require_equal(payload.get("plan"), file_record(output_path(config, "plan")), "complete/current plan")
    for key in ("status_json", "status_csv", "events"):
        verify_record(payload[key], f"complete {key}")
    plan = load_plan(config)
    expected_records = []
    for entry in plan["entries"]:
        record = load_stage_record(config, entry)
        if record is not None:
            expected_records.append({"entry": dict(entry), "status": record["status"], "receipt": file_record(stage_record_path(config, entry))})
    require_equal(payload.get("stage_records"), expected_records, "complete/current stage records")
    require_equal(payload.get("terminal_jobs_n"), len(expected_records), "complete terminal count")
    stop_path = output_path(config, "stage_stop")
    expected_stop = file_record(stop_path) if stop_path.is_file() else None
    require_equal(payload.get("stage_stop"), expected_stop, "complete/current stage stop")
    if expected_stop is None:
        require_equal(len(expected_records), len(plan["entries"]), "complete all jobs terminal")
        require_equal(payload.get("state"), "COMPLETE", "complete state")
    status = load_json(verify_record(payload["status_json"], "complete status JSON"))
    require_equal(payload.get("counts"), status.get("counts"), "complete/status counts")
    require_equal(payload.get("root_complete_receipt_written_last"), True, "complete-last claim")


def verify(config: Mapping[str, Any]) -> dict[str, Any]:
    if lock_is_busy_readonly(repo_path(config["source_v2"]["driver_lock"]), require_exists=True):
        raise V3Error("source v2 driver lock is held")
    result = {"state": "VERIFIED", "git_lock": verify_method(config), "locked_inputs": verify_locked_inputs(config), "training_preflight": verify_training_preflight(config)}
    source, record = source_plan(config); entries, pairs = build_v3_plan(source["entries"])
    result.update({"source_plan": record, "source_gate": verify_source_reuse(config, entries[0]), **control_contracts(config, entries, pairs), "entries_n": len(entries), "pairs_n": len(pairs), "source_v2_driver_lock_free": True})
    if output_path(config, "plan").is_file():
        result["v3_plan"] = file_record(output_path(config, "plan")); load_plan(config)
    return result


def runtime_contract(config: Mapping[str, Any]) -> dict[str, Any]:
    hook = config["qualitative_hook"]
    command = hook.get("command")
    if not isinstance(command, list) or command != ["one", "{building_id}", "{arm}", "{replicate}"]:
        raise V3Error("review hook command contract drift")
    first = config["source_v2"]["reused_first_job"]
    return {
        "queue_root": config["outputs"]["root"],
        "training_wrapper": config["locked_inputs"]["training_wrapper"]["path"],
        "readout_wrapper": config["locked_inputs"]["readout_wrapper"]["path"],
        "review_wrapper": hook["wrapper"],
        "review_command": command[0],
        "pair_member_rows": 19,
        "pair_count": int(config["sequence_contract"]["pair_count"]),
        "readout_lock": config["resources"]["readout_lock"],
        "service_log": str(output_path(config, "service_log").relative_to(REPO)),
        "reused_stage_key": first["stage_key"],
        "reused_stage_entry_order": int(first["stage_entry_order"]),
        "reused_building_id": first["building_id"],
        "reused_arm": first["arm"],
        "reused_replicate": first["replicate"],
    }


def add_entry_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--stage-key", required=True)
    parser.add_argument("--stage-entry-order", required=True, type=int)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    commands = result.add_subparsers(dest="command", required=True)
    commands.add_parser("verify"); commands.add_parser("initialize"); commands.add_parser("status"); commands.add_parser("finalize")
    runtime = commands.add_parser("runtime-contract"); runtime.add_argument("--format", choices=("json", "tsv"), default="json")
    pairs = commands.add_parser("pairs"); pairs.add_argument("--format", choices=("json", "tsv"), default="json")
    inspect = commands.add_parser("inspect"); add_entry_args(inspect); inspect.add_argument("--format", choices=("json", "tsv"), default="json")
    launch = commands.add_parser("launch-training"); add_entry_args(launch); launch.add_argument("--gpu", type=int, choices=(0, 1), required=True)
    archive = commands.add_parser("archive-training"); add_entry_args(archive)
    terminal = commands.add_parser("record-terminal"); add_entry_args(terminal)
    failure = commands.add_parser("record-action-failure"); add_entry_args(failure); failure.add_argument("--invocation-id", required=True); failure.add_argument("--action", required=True); failure.add_argument("--error-type", required=True); failure.add_argument("--message", required=True); failure.add_argument("--return-code", type=int); failure.add_argument("--log-path", type=Path)
    barrier = commands.add_parser("pair-training-ready"); barrier.add_argument("--pair-id", required=True)
    boundary = commands.add_parser("gpu-boundary"); boundary.add_argument("--pair-id", required=True); boundary.add_argument("--gpu", type=int, choices=(0, 1), required=True)
    wait_boundary = commands.add_parser("wait-gpu-boundary"); wait_boundary.add_argument("--pair-id", required=True); wait_boundary.add_argument("--gpu", type=int, choices=(0, 1), required=True)
    no_training = commands.add_parser("assert-no-training"); no_training.add_argument("--skip-process-scan", action="store_true")
    commands.add_parser("stage-stop-check")
    return result


def print_json(value: Any) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True))


def main(argv: Sequence[str] | None = None) -> int:
    args = parser().parse_args(argv)
    config_path = repo_path(args.config)
    config = load_config(config_path)
    plan = None
    if args.command == "verify": value = verify(config)
    elif args.command == "initialize": value = initialize(config, config_path)
    elif args.command == "status": value = publish_status(config)
    elif args.command == "finalize": value = finalize(config)
    elif args.command == "runtime-contract":
        value = runtime_contract(config)
        if args.format == "tsv":
            print("\t".join(str(value[key]) for key in (
                "queue_root", "training_wrapper", "readout_wrapper", "review_wrapper", "review_command",
                "pair_member_rows", "pair_count", "readout_lock", "service_log", "reused_stage_key",
                "reused_stage_entry_order", "reused_building_id", "reused_arm", "reused_replicate",
            )))
            return 0
    elif args.command == "pairs":
        plan = load_plan(config); value = plan["pairs"]
        if args.format == "tsv":
            for pair in value:
                for member in pair["members"]:
                    print("\t".join(str(item) for item in (pair["pair_order"], pair["pair_id"], pair["stage_order"], pair["stage_key"], member["member_order"], member["physical_gpu"], member["stage_entry_order"], member["building_id"], member["arm"], member["replicate"])))
            return 0
    elif args.command in {"inspect", "launch-training", "archive-training", "record-terminal", "record-action-failure"}:
        plan = load_plan(config); entry = entry_for(plan, args.stage_key, args.stage_entry_order)
        if args.command == "inspect":
            value = inspect_entry(config, entry)
            if args.format == "tsv":
                print(f"{value['state']}\t{value['action']}")
                return 0
        elif args.command == "launch-training": value = launch_training(config, entry, args.gpu)
        elif args.command == "archive-training": value = archive_training(config, entry)
        elif args.command == "record-terminal": value = record_terminal(config, entry)
        else: value = record_action_failure(config, entry, invocation_id=args.invocation_id, action=args.action, error_type=args.error_type, message=args.message, return_code=args.return_code, log_path=args.log_path)
    elif args.command == "pair-training-ready": value = pair_training_ready(config, args.pair_id)
    elif args.command == "gpu-boundary": value = gpu_boundary(config, args.pair_id, args.gpu)
    elif args.command == "wait-gpu-boundary": value = wait_gpu_boundary(config, args.pair_id, args.gpu)
    elif args.command == "assert-no-training": value = assert_no_training(config, inspect_processes=not args.skip_process_scan)
    elif args.command == "stage-stop-check": value = stage_stop_check(config)
    else: raise V3Error(f"unsupported command: {args.command}")
    print_json(value)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except V3Error as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2)
