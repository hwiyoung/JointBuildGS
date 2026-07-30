#!/usr/bin/env python3
"""Run only the 20 A-prime jobs left after the completed smoke recovery.

The controller imports the committed queue through its receipt-compatibility
recovery shim.  It changes only the immutable plan namespace and removes the
two source-plan entries representing the already completed smoke job.  All
pipeline inspection, retry, append-only archive, per-job skip, cross-building
stage-stop, status, and finalization mechanics remain those of the source
queue.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence


REPO = Path(__file__).resolve().parents[4]
DEFAULT_CONFIG = (
    REPO
    / "phases/p2-gsjso/configs/fusion_w1/fusion_w1_aprime_queue_continuation_20260727.json"
)
RECOVERY_SHIM = (
    REPO
    / "phases/p2-gsjso/scripts/fusion_w1/fusion_w1_aprime_queue_recovery_20260727.py"
)
SOURCE_BASE_DRIVER = REPO / "phases/p2-gsjso/scripts/fusion_w1/fusion_w1_aprime_queue_20260726.py"
RECOVERY_SHIM_SHA256 = "c98f8fc8f69b50096f3503d08775ef3204b6ab3d0b25579c257d56fe3c7921fa"
SOURCE_BASE_DRIVER_SHA256 = "5f2ed650508e20929478ea308efbe6aba2e32f80b57a90d996bab1280079a043"
CONFIG_SCHEMA = "jointbuildgs.fusion_w1_aprime.unattended_continuation.config.v1"
TASK_ID = "FUS-W1-APRIME-QUEUE-CONTINUATION-001"
SOURCE_SMOKE_IDENTITY = {
    "building_id": "DEBY_LOD2_42364609",
    "arm": "Aprime",
    "replicate": "r1",
    "profile": "full",
}
FIRST_IDENTITY = {
    "building_id": "DEBY_LOD2_42364659",
    "arm": "Aprime",
    "replicate": "r1",
    "stage_order": 1,
    "stage_entry_order": 2,
}
QUALITATIVE_COMPONENTS = (
    "input_crop",
    "seed_top",
    "mesh_top",
    "points_top",
    "points_section",
    "assembled",
    "reference",
    "opacity",
)


def load_recovery() -> Any:
    for path, expected, label in (
        (RECOVERY_SHIM, RECOVERY_SHIM_SHA256, "queue recovery shim"),
        (SOURCE_BASE_DRIVER, SOURCE_BASE_DRIVER_SHA256, "source queue driver"),
    ):
        observed = hashlib.sha256(path.read_bytes()).hexdigest()
        if observed != expected:
            raise RuntimeError(f"{label} bootstrap SHA mismatch: {observed}")
    spec = importlib.util.spec_from_file_location(
        "fusion_w1_aprime_queue_recovery_for_continuation", RECOVERY_SHIM
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load queue recovery shim: {RECOVERY_SHIM}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


recovery = load_recovery()
queue = recovery.queue
_SOURCE_BUILD_PLAN = queue.build_plan
_SOURCE_INSPECT_PIPELINE = queue.inspect_pipeline
_SOURCE_VERIFY_READOUT_COMPLETE = queue.verify_readout_complete


def local_repo_path(value: str | Path) -> Path:
    """Accept either the host checkout root or the locked container root."""
    raw = Path(value)
    if raw.is_absolute():
        try:
            raw = raw.relative_to(REPO)
        except ValueError:
            pass
    return queue.repo_path(raw)


def load_config(path: Path = DEFAULT_CONFIG) -> dict[str, Any]:
    config_path = local_repo_path(path)
    config = queue.load_json(config_path)
    queue.require_equal(config.get("schema"), CONFIG_SCHEMA, "continuation config schema")
    queue.require_equal(config.get("task_id"), TASK_ID, "continuation task")
    queue.require_equal(config.get("branch"), "exp/fusion-w1", "continuation branch")
    sequence = config["sequence_contract"]
    queue.require_equal(sequence.get("source_stage_orders_retained"), [1, 2, 3], "retained stages")
    queue.require_equal(sequence.get("stage_entries"), 20, "continuation stage entries")
    queue.require_equal(sequence.get("unique_jobs"), 20, "continuation unique jobs")
    queue.require_equal(sequence.get("first_job"), FIRST_IDENTITY, "continuation first job")
    queue.require_equal(sequence.get("user_prompts"), False, "user-prompt lock")
    queue.require_equal(sequence.get("time_cutoff"), None, "sequence time cutoff")
    queue.require_equal(config["resources"].get("time_cutoff"), None, "resource time cutoff")
    queue.require_equal(
        config["resources"].get("training_foreground_one_at_a_time"),
        True,
        "training serial lock",
    )
    queue.require_equal(config["resources"].get("readout_serial"), True, "readout serial lock")
    queue.require_equal(config["resources"].get("physical_gpu_choices"), [1], "GPU choice lock")
    queue.require_equal(config["resources"].get("default_physical_gpu"), 1, "default GPU lock")
    gpu_guard = config["resources"].get("gpu_job_boundary_guard", {})
    for key, expected in (
        ("enabled", True),
        ("physical_gpu", 1),
        ("poll_seconds", 30),
        ("only_before_first_action_of_each_job_identity", True),
        ("before_each_cuda_action", True),
        ("queue_descendant_processes_excluded", True),
        ("time_cutoff", None),
    ):
        queue.require_equal(gpu_guard.get(key), expected, f"GPU boundary guard {key}")
    qualitative = config.get("qualitative_gate", {})
    queue.require_equal(
        qualitative.get("config"),
        config["locked_inputs"]["qualitative_config"]["path"],
        "qualitative config path lock",
    )
    queue.require_equal(
        qualitative.get("driver"),
        config["locked_inputs"]["qualitative_driver"]["path"],
        "qualitative driver path lock",
    )
    queue.require_equal(
        qualitative.get("receipt_schema"),
        "jointbuildgs.fusion_w1_aprime.smoke_qualitative.strict_head_receipt.v1",
        "qualitative receipt schema lock",
    )
    queue.require_equal(
        qualitative.get("publication_key"),
        "current_full_git_head",
        "qualitative publication key lock",
    )
    queue.require_equal(qualitative.get("branch"), "exp/fusion-w1", "qualitative branch lock")
    queue.require_equal(
        qualitative.get("components"), list(QUALITATIVE_COMPONENTS), "qualitative components lock"
    )
    for key in (
        "source_snapshot_current_hash_required",
        "legacy_top_level_current_hash_required",
        "receipt_written_last_required",
    ):
        queue.require_equal(qualitative.get(key), True, f"qualitative {key}")
    queue.require_equal(qualitative.get("placeholder_count"), 0, "qualitative placeholder lock")
    queue.require_equal(
        config["failure_contract"].get("same_error_signature_attempts_before_skip"),
        3,
        "same-error retry count",
    )
    queue.require_equal(
        config["failure_contract"].get(
            "same_error_type_consecutive_buildings_before_stage_stop"
        ),
        3,
        "consecutive-building stop count",
    )
    queue.require_equal(
        config["publication"].get("external_smoke_gate_required_on_every_resume"),
        True,
        "external gate resume lock",
    )
    queue.require_equal(config["publication"].get("source_queue_immutable"), True, "source immutability")
    queue.require_equal(config["publication"].get("interpretation_or_verdict"), None, "verdict lock")
    expected_config = config["implementation_files"][0]
    queue.require_equal(queue.relative(config_path), expected_config, "continuation config path")
    return config


def exact_record(record: Mapping[str, Any], label: str) -> dict[str, Any]:
    path = queue.repo_path(record["path"])
    observed = queue.file_record(path)
    queue.require_equal(observed["path"], record["path"], f"{label} path")
    queue.require_equal(observed["sha256"], record["sha256"], f"{label} SHA")
    return observed


def cachefix_readout_context(
    config: Mapping[str, Any],
) -> tuple[Any, dict[str, Any], Path]:
    """Expose the cachefix config through the base readout inspection API.

    The cachefix adapter deliberately owns only environment and hygiene.  Its
    locked base driver still owns job paths and completion receipt validation.
    """
    try:
        adapter_path = queue.repo_path(config["locked_inputs"]["readout_driver"]["path"])
        adapter = queue.load_module("fusion_w1_aprime_continuation_readout_cachefix", adapter_path)
        config_path = queue.repo_path(config["locked_inputs"]["readout_config"]["path"])
        readout_config = adapter.load_config(config_path)
        base = adapter.load_base_driver(readout_config)
    except queue.UnattendedError:
        raise
    except Exception as exc:
        raise queue.UnattendedError(f"cachefix readout context failed: {exc}") from exc
    return base, readout_config, config_path


# The inherited queue sees canonical scientific outputs, while its current
# method lock is the cachefix config/adapter/wrapper implementation set.
queue.readout_context = cachefix_readout_context


def verify_readout_complete(
    config: Mapping[str, Any], entry: Mapping[str, Any]
) -> dict[str, Any] | None:
    result = _SOURCE_VERIFY_READOUT_COMPLETE(config, entry)
    if result is None:
        return None
    payload = result["payload"]
    complete_path = queue.verify_record(result["receipt"], "readout complete receipt")
    ledger = payload.get("artifact_ledger")
    if not isinstance(ledger, list) or not ledger:
        raise queue.UnattendedError("readout complete artifact ledger is absent")
    queue.require_equal(payload.get("artifact_count"), len(ledger), "readout artifact count")
    attempt_path = queue.verify_record(
        payload["attempt_materialization"], "readout attempt materialization"
    )
    attempt_root = attempt_path.parent.resolve()
    current_files: set[str] = set()
    for artifact in sorted(attempt_root.rglob("*")):
        relative_artifact = artifact.relative_to(attempt_root).as_posix()
        if artifact.is_symlink():
            raise queue.UnattendedError(
                f"successful readout attempt contains symlink: {relative_artifact}"
            )
        if artifact.is_dir():
            continue
        if not artifact.is_file():
            raise queue.UnattendedError(
                f"successful readout attempt contains special file: {relative_artifact}"
            )
        current_files.add(relative_artifact)
    if not current_files:
        raise queue.UnattendedError("successful readout attempt contains no regular files")

    seen_raw: set[str] = set()
    ledger_files: set[str] = set()
    for record in ledger:
        if not isinstance(record, Mapping) or not isinstance(record.get("path"), str):
            raise queue.UnattendedError("readout artifact ledger record is invalid")
        raw = str(record["path"])
        if raw in seen_raw:
            raise queue.UnattendedError(f"duplicate readout artifact ledger path: {raw}")
        seen_raw.add(raw)
        artifact = queue.verify_record(record, f"readout artifact {raw}")
        if artifact.is_symlink():
            raise queue.UnattendedError(f"readout artifact ledger contains symlink: {raw}")
        try:
            relative_artifact = artifact.resolve().relative_to(attempt_root).as_posix()
        except ValueError as exc:
            raise queue.UnattendedError(
                f"readout artifact is outside successful attempt: {raw}"
            ) from exc
        if relative_artifact in ledger_files:
            raise queue.UnattendedError(
                f"duplicate resolved readout artifact ledger path: {relative_artifact}"
            )
        ledger_files.add(relative_artifact)

    if ledger_files != current_files:
        missing = sorted(current_files - ledger_files)
        nonexistent = sorted(ledger_files - current_files)
        raise queue.UnattendedError(
            "readout artifact ledger does not exactly cover successful attempt files: "
            f"missing_from_ledger={missing}, absent_from_attempt={nonexistent}"
        )

    final_failure = attempt_root / "failure.json"
    if final_failure.exists() or final_failure.is_symlink():
        raise queue.UnattendedError("successful readout attempt also contains failure.json")
    attempt_number = int(payload["attempt"])
    attempts_root = attempt_root.parent
    for failure in sorted(attempts_root.glob("attempt_*/failure.json")):
        match = re.fullmatch(r"attempt_([0-9]{3})", failure.parent.name)
        if match is None:
            raise queue.UnattendedError(f"malformed readout attempt path: {queue.relative(failure)}")
        failure_attempt = int(match.group(1))
        if failure_attempt >= attempt_number or failure.stat().st_mtime_ns > complete_path.stat().st_mtime_ns:
            raise queue.UnattendedError(
                f"contradictory readout failure after completion: {queue.relative(failure)}"
            )
    return {
        **result,
        "artifact_ledger_verified": True,
        "artifact_ledger_exact_coverage_verified": True,
        "artifact_count": len(ledger),
        "successful_attempt_failure_absent": True,
        "post_complete_failure_absent": True,
    }


queue.verify_readout_complete = verify_readout_complete


def verify_cachefix_readout_method(config: Mapping[str, Any]) -> dict[str, Any]:
    base, readout_config, config_path = cachefix_readout_context(config)
    try:
        return {
            "config": queue.file_record(config_path),
            "git_lock": base.verify_git_runtime(readout_config),
            "locked_inputs": base.verify_locked_inputs(readout_config),
            "canonical_output_root": readout_config["outputs"]["root"],
            "cachefix_contract": readout_config["cachefix_contract"]["schema"],
        }
    except queue.UnattendedError:
        raise
    except Exception as exc:
        raise queue.UnattendedError(f"cachefix readout method gate failed: {exc}") from exc


def verify_smoke_qualitative_publication(
    config: Mapping[str, Any], source_records: Mapping[str, Mapping[str, Any]]
) -> dict[str, Any]:
    contract = config["qualitative_gate"]
    try:
        driver_path = queue.repo_path(contract["driver"])
        qualitative = queue.load_module(
            "fusion_w1_aprime_continuation_qualitative_gate", driver_path
        )
        qualitative_config_path = queue.repo_path(contract["config"])
        qualitative_config = qualitative.load_config(qualitative_config_path)
        strict = qualitative.strict_head_context(qualitative_config)
        receipt = qualitative.verify_strict_publication(
            qualitative_config, context=strict
        )
        root, panel_path, opacity_path, receipt_path = qualitative.strict_publication_paths(
            qualitative_config, strict["head"]
        )
    except Exception as exc:
        raise queue.UnattendedError(
            f"current-HEAD smoke qualitative publication gate failed: {exc}"
        ) from exc

    current_head = queue.git("rev-parse", "HEAD").stdout.strip()
    current_branch = queue.git("branch", "--show-current").stdout.strip()
    queue.require_equal(strict.get("head"), current_head, "qualitative execution HEAD")
    queue.require_equal(strict.get("branch"), current_branch, "qualitative execution branch")
    queue.require_equal(current_branch, contract["branch"], "qualitative locked branch")
    expected_root = (
        queue.repo_path(contract["root"])
        / contract["publications_directory"]
        / current_head
    )
    queue.require_equal(root.resolve(), expected_root.resolve(), "qualitative publication root")
    queue.require_equal(receipt_path.name, contract["receipt_name"], "qualitative receipt name")
    queue.require_equal(panel_path.name, contract["panel_name"], "qualitative panel name")
    queue.require_equal(opacity_path.name, contract["opacity_name"], "qualitative opacity name")
    queue.require_equal(receipt.get("schema"), contract["receipt_schema"], "qualitative schema")
    queue.require_equal(receipt.get("state"), "COMPLETE", "qualitative state")
    queue.require_equal(receipt.get("execution_head"), current_head, "qualitative receipt HEAD")
    queue.require_equal(receipt.get("execution_branch"), current_branch, "qualitative receipt branch")
    queue.require_equal(receipt.get("publication_key"), current_head, "qualitative publication key")
    expected_components = {name: True for name in QUALITATIVE_COMPONENTS}
    queue.require_equal(receipt.get("components"), expected_components, "qualitative components")
    queue.require_equal(receipt.get("placeholder_count"), 0, "qualitative placeholders")
    queue.require_equal(receipt.get("scientific_verdict"), None, "qualitative verdict")
    queue.require_equal(receipt.get("interpretation"), None, "qualitative interpretation")

    publication = receipt.get("publication", {})
    for key, expected in (
        ("append_only", True),
        ("same_head_verify_only", True),
        ("overwrite_allowed", False),
        ("partial_publication_allowed", False),
        ("receipt_written_after_artifact_validation", True),
        ("receipt_published_last", True),
        ("source_inputs_unchanged", True),
        ("legacy_top_level_unchanged", True),
    ):
        queue.require_equal(publication.get(key), expected, f"qualitative publication {key}")

    source_before = receipt.get("source_snapshot_before")
    source_after = receipt.get("source_snapshot_after")
    legacy_before = receipt.get("legacy_top_level_before")
    legacy_after = receipt.get("legacy_top_level_after")
    if not all(
        isinstance(value, Mapping) and value
        for value in (source_before, source_after, legacy_before, legacy_after)
    ):
        raise queue.UnattendedError("qualitative source/legacy bindings are absent")
    queue.require_equal(source_after, source_before, "qualitative source snapshot")
    queue.require_equal(legacy_after, legacy_before, "qualitative legacy snapshot")
    queue.require_equal(
        source_after.get("readout_complete"),
        source_records["smoke_readout_job_complete"],
        "qualitative/readout completion",
    )
    queue.require_equal(
        source_after.get("recovery_complete"),
        source_records["smoke_recovery_complete"],
        "qualitative/recovery completion",
    )
    queue.require_equal(set(legacy_after), {"panel", "opacity", "receipt"}, "qualitative legacy set")

    verified: dict[str, Mapping[str, Any]] = {}
    collections = (
        receipt.get("outputs", {}),
        source_after,
        legacy_after,
    )
    for collection in collections:
        if not isinstance(collection, Mapping):
            raise queue.UnattendedError("qualitative artifact collection is invalid")
        for record in collection.values():
            if not isinstance(record, Mapping) or not isinstance(record.get("path"), str):
                raise queue.UnattendedError("qualitative artifact record is invalid")
            raw = str(record["path"])
            if raw in verified:
                queue.require_equal(record, verified[raw], f"qualitative duplicate artifact {raw}")
            else:
                verified[raw] = record
    for raw, record in verified.items():
        queue.verify_record(record, f"qualitative artifact {raw}")

    strict_files = strict.get("files")
    if not isinstance(strict_files, list) or not strict_files:
        raise queue.UnattendedError("qualitative strict implementation inventory is absent")
    for record in strict_files:
        queue.verify_record(record, "qualitative strict implementation")
        queue.require_equal(record.get("tracked_at_head"), True, "qualitative tracked implementation")
        queue.require_equal(record.get("worktree_matches_head"), True, "qualitative clean implementation")
        raw = str(record["path"])
        blob = queue.git("rev-parse", f"{current_head}:{raw}").stdout.strip()
        queue.require_equal(record.get("git_blob"), blob, f"qualitative git blob {raw}")
    queue.require_equal(strict.get("all_tracked_at_head"), True, "qualitative tracked inventory")
    queue.require_equal(strict.get("all_worktree_match_head"), True, "qualitative clean inventory")

    receipt_stat = receipt_path.stat()
    if receipt_stat.st_mtime_ns < max(panel_path.stat().st_mtime_ns, opacity_path.stat().st_mtime_ns):
        raise queue.UnattendedError("qualitative receipt was not written after its outputs")
    return {
        "receipt": queue.file_record(receipt_path),
        "state": "COMPLETE",
        "execution_head": current_head,
        "execution_branch": current_branch,
        "components_true_n": len(expected_components),
        "placeholder_count": 0,
        "verified_unique_artifacts_n": len(verified),
        "strict_implementation_files_n": len(strict_files),
        "source_snapshot_unchanged": True,
        "legacy_top_level_unchanged": True,
    }


def verify_external_smoke_gate(config: Mapping[str, Any]) -> dict[str, Any]:
    records = {
        name: exact_record(record, f"source queue {name}")
        for name, record in config["source_queue"].items()
    }

    source_plan = queue.load_json(queue.repo_path(records["source_plan"]["path"]))
    queue.require_equal(source_plan.get("schema"), queue.PLAN_SCHEMA, "source plan schema")
    queue.require_equal(source_plan.get("state"), "ACTIVE", "source plan state")
    queue.require_equal(source_plan.get("stage_entries_n"), 22, "source stage entries")
    queue.require_equal(source_plan.get("unique_jobs_n"), 21, "source unique jobs")

    source_stop = queue.load_json(queue.repo_path(records["source_stage_stop"]["path"]))
    queue.require_equal(source_stop.get("schema"), queue.STAGE_STOP_SCHEMA, "source stage-stop schema")
    queue.require_equal(
        source_stop.get("state"),
        "STOPPED_SMOKE_BARRIER_NOT_MEASURED",
        "source stage-stop state",
    )
    queue.require_equal(
        source_stop.get("cause", {}).get("reason_code"),
        "SMOKE_BARRIER_NOT_MEASURED",
        "source stage-stop reason",
    )

    source_complete = queue.load_json(queue.repo_path(records["source_complete"]["path"]))
    queue.require_equal(source_complete.get("schema"), queue.COMPLETE_SCHEMA, "source complete schema")
    queue.require_equal(
        source_complete.get("state"),
        "STOPPED_SMOKE_BARRIER_NOT_MEASURED",
        "source complete state",
    )
    queue.require_equal(source_complete.get("plan"), records["source_plan"], "source complete/plan")
    queue.require_equal(
        source_complete.get("stage_stop"), records["source_stage_stop"], "source complete/stage stop"
    )

    smoke = queue.load_json(queue.repo_path(records["smoke_recovery_complete"]["path"]))
    queue.require_equal(
        smoke.get("schema"),
        "jointbuildgs.fusion_w1_aprime.smoke_recovery.complete.v1",
        "smoke recovery schema",
    )
    queue.require_equal(smoke.get("state"), "COMPLETE", "smoke recovery state")
    queue.require_equal(smoke.get("successful_continuation_attempt"), 5, "smoke recovery attempt")
    queue.require_equal(smoke.get("new_training_runs_started"), 0, "smoke recovery new training")
    queue.require_equal(smoke.get("other_queue_jobs_started"), 0, "smoke recovery other jobs")
    queue.require_equal(smoke.get("source_queue_rewritten"), False, "source queue rewrite lock")
    queue.require_equal(smoke.get("source_training_tree_preserved"), True, "source training preservation")
    queue.require_equal(
        smoke.get("source_queue_state"),
        "STOPPED_SMOKE_BARRIER_NOT_MEASURED",
        "smoke recovery source state",
    )
    queue.require_equal(smoke.get("scientific_verdict"), None, "smoke recovery verdict lock")
    queue.require_equal(
        smoke.get("scope"),
        {
            **SOURCE_SMOKE_IDENTITY,
            "continuation_attempt": 5,
            "new_training_runs_allowed": 0,
            "other_queue_jobs_allowed": 0,
            "preserved_recovery_attempts": [4],
        },
        "smoke recovery scope",
    )
    queue.require_equal(
        smoke.get("readout_job_complete"),
        records["smoke_readout_job_complete"],
        "smoke recovery/readout complete",
    )
    queue.require_equal(smoke.get("primary", {}).get("state"), "MEASURED", "smoke primary state")
    queue.require_equal(
        smoke.get("primary", {}).get("measurement_status"), "MEASURED", "smoke primary measurement"
    )

    readout = queue.load_json(queue.repo_path(records["smoke_readout_job_complete"]["path"]))
    queue.require_equal(
        readout.get("schema"),
        "jointbuildgs.fusion_w1_aprime.readout.complete.v1",
        "smoke readout schema",
    )
    queue.require_equal(readout.get("state"), "COMPLETE", "smoke readout state")
    queue.require_equal(readout.get("identity"), SOURCE_SMOKE_IDENTITY, "smoke readout identity")
    queue.require_equal(readout.get("primary"), smoke.get("primary"), "smoke primary binding")
    queue.require_equal(readout.get("interpretation_or_verdict"), None, "smoke readout verdict lock")
    ledger = readout.get("artifact_ledger")
    if not isinstance(ledger, list) or not ledger:
        raise queue.UnattendedError("smoke readout artifact ledger is absent")
    queue.require_equal(readout.get("artifact_count"), len(ledger), "smoke artifact count")
    for artifact in ledger:
        queue.verify_record(artifact, "smoke readout artifact")
    qualitative = verify_smoke_qualitative_publication(config, records)
    return {
        "state": "PASSED",
        "records": records,
        "smoke_identity": SOURCE_SMOKE_IDENTITY,
        "successful_continuation_attempt": 5,
        "primary_state": "MEASURED",
        "artifact_count": len(ledger),
        "qualitative": qualitative,
        "source_queue_rewritten": False,
        "interpretation_or_verdict": None,
    }


def source_config(config: Mapping[str, Any]) -> dict[str, Any]:
    record = config["source_queue"]["base_config"]
    exact_record(record, "source base config")
    return queue.load_config(queue.repo_path(record["path"]))


def verify_continuation_lock(
    config: Mapping[str, Any], entries: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    record = exact_record(config["locked_inputs"]["continuation_lock"], "continuation lock")
    payload = queue.load_json(queue.repo_path(record["path"]))
    queue.require_equal(
        payload.get("schema"),
        "jointbuildgs.fusion_w1_aprime.queue_continuation_lock.v1",
        "continuation lock schema",
    )
    queue.require_equal(
        payload.get("state"),
        "LOCKED_BEFORE_REMAINING_JOB_START",
        "continuation lock state",
    )
    queue.require_equal(payload.get("branch"), "exp/fusion-w1", "continuation lock branch")
    scope = payload.get("scope", {})
    queue.require_equal(
        scope.get("completed_smoke_identity"),
        {key: SOURCE_SMOKE_IDENTITY[key] for key in ("building_id", "arm", "replicate")},
        "continuation lock smoke identity",
    )
    for key, expected in (
        ("remaining_jobs", 20),
        ("new_smoke_training_allowed", 0),
        ("serial", True),
        ("physical_gpu", 1),
        ("user_prompts", False),
        ("time_cutoff", None),
    ):
        queue.require_equal(scope.get(key), expected, f"continuation lock {key}")
    expected_jobs = [
        {
            "order": index,
            "building_id": entry["building_id"],
            "arm": entry["arm"],
            "replicate": entry["replicate"],
            "seed": int(entry["seed"]),
        }
        for index, entry in enumerate(entries, 1)
    ]
    queue.require_equal(payload.get("jobs"), expected_jobs, "continuation lock jobs")
    queue.require_equal(
        payload.get("failure_contract"),
        {
            "same_error_signature_attempts_before_skip": 3,
            "same_error_type_consecutive_buildings_before_stage_stop": 3,
            "partial_artifacts_preserved": True,
            "no_delete_or_overwrite": True,
        },
        "continuation lock failure contract",
    )
    queue.require_equal(
        payload.get("publication", {}).get("scientific_verdict"),
        None,
        "continuation lock verdict",
    )
    return record


def build_plan(config: Mapping[str, Any]) -> list[dict[str, Any]]:
    source_entries = _SOURCE_BUILD_PLAN(source_config(config))
    retained = [
        dict(entry)
        for entry in source_entries
        if int(entry["stage_order"]) in {1, 2, 3}
        and not (int(entry["stage_order"]) == 1 and int(entry["stage_entry_order"]) == 1)
    ]
    for global_order, entry in enumerate(retained, 1):
        entry["global_entry_order"] = global_order
        entry["smoke_barrier_entry"] = False
        entry["reuse_completed_smoke"] = False
    queue.require_equal(len(retained), 20, "continuation plan size")
    unique = {(row["building_id"], row["arm"], row["replicate"]) for row in retained}
    queue.require_equal(len(unique), 20, "continuation unique plan size")
    counts = {
        order: sum(int(row["stage_order"]) == order for row in retained)
        for order in (1, 2, 3)
    }
    queue.require_equal(counts, {1: 8, 2: 9, 3: 3}, "continuation stage counts")
    first = retained[0]
    queue.require_equal(
        {
            "building_id": first["building_id"],
            "arm": first["arm"],
            "replicate": first["replicate"],
            "stage_order": first["stage_order"],
            "stage_entry_order": first["stage_entry_order"],
        },
        FIRST_IDENTITY,
        "continuation first identity",
    )
    verify_continuation_lock(config, retained)
    return retained


# Every imported source-queue transition now sees the reduced immutable plan.
queue.build_plan = build_plan


def inspect_pipeline(
    config: Mapping[str, Any], entry: Mapping[str, Any]
) -> dict[str, Any]:
    """Close the inherited archive-failure retry-ordering gap.

    The source inspector returns ARCHIVE_TRAINING before its ordinary action
    failure skip check.  Three identical archive action failures therefore
    need this continuation-local early terminal path.
    """
    archive_failures = [
        failure
        for failure in queue.action_failures(config, entry)
        if failure["payload"].get("action") == "ARCHIVE_TRAINING"
    ]
    matched, signature, error_type = queue.three_same_signature(
        archive_failures, signature_field="error_signature"
    )
    if matched:
        return {
            "state": "SKIPPED",
            "action": "RECORD_SKIPPED",
            "skip": {
                "source": "orchestrator_archive_action_failures",
                "error_signature": signature,
                "error_type": error_type,
                "attempts": [item["receipt"] for item in archive_failures[-3:]],
            },
        }
    return _SOURCE_INSPECT_PIPELINE(config, entry)


queue.inspect_pipeline = inspect_pipeline


def initialize(config: Mapping[str, Any], config_path: Path) -> dict[str, Any]:
    method = queue.verify_git_runtime(config)
    locked = queue.verify_locked_inputs(config)
    readout_method = verify_cachefix_readout_method(config)
    preflight = queue.validate_preflight(config)
    external_gate = verify_external_smoke_gate(config)
    entries = build_plan(config)
    plan_path = queue.repo_path(config["outputs"]["plan"])
    expected = {
        "schema": queue.PLAN_SCHEMA,
        "state": "ACTIVE",
        "run_id": config["run_id"],
        "task_id": config["task_id"],
        "config": queue.file_record(config_path),
        "git_lock": method,
        "locked_inputs": locked,
        "readout_method": readout_method,
        "preflight": preflight,
        "external_smoke_gate": external_gate,
        "source_queue_continuation": {
            "source_plan": external_gate["records"]["source_plan"],
            "source_stage_stop": external_gate["records"]["source_stage_stop"],
            "source_complete": external_gate["records"]["source_complete"],
            "excluded_completed_job": SOURCE_SMOKE_IDENTITY,
            "source_queue_rewritten": False,
        },
        "sequence_contract": config["sequence_contract"],
        "failure_contract": config["failure_contract"],
        "entries": entries,
        "stage_entries_n": 20,
        "unique_jobs_n": 20,
        "actual_training_started_at_publication": False,
        "interpretation_or_verdict": None,
    }
    if plan_path.exists() or plan_path.is_symlink():
        observed = queue.load_json(plan_path)
        for key, value in expected.items():
            queue.require_equal(observed.get(key), value, f"immutable continuation plan {key}")
        return {**observed, "publication_reused": True}
    expected["created_at"] = queue.now_iso()
    queue.exclusive_json(plan_path, expected)
    queue.append_event(
        config,
        "CONTINUATION_QUEUE_INITIALIZED",
        {
            "plan": queue.file_record(plan_path),
            "git_head": method["head"],
            "stage_entries_n": 20,
            "unique_jobs_n": 20,
            "external_smoke_gate": external_gate["records"]["smoke_recovery_complete"],
        },
    )
    queue.publish_status(config)
    return expected


def load_plan(config: Mapping[str, Any]) -> dict[str, Any]:
    plan_path = queue.repo_path(config["outputs"]["plan"])
    plan = queue.load_json(plan_path)
    queue.require_equal(plan.get("schema"), queue.PLAN_SCHEMA, "continuation plan schema")
    queue.require_equal(plan.get("state"), "ACTIVE", "continuation plan state")
    queue.require_equal(
        plan.get("config"),
        queue.file_record(queue.repo_path(config["implementation_files"][0])),
        "continuation plan/current config",
    )
    queue.require_equal(plan.get("git_lock"), queue.verify_git_runtime(config), "continuation plan/current method")
    queue.require_equal(
        plan.get("locked_inputs"), queue.verify_locked_inputs(config), "continuation locked inputs"
    )
    queue.require_equal(
        plan.get("readout_method"),
        verify_cachefix_readout_method(config),
        "continuation cachefix readout method",
    )
    queue.require_equal(plan.get("preflight"), queue.validate_preflight(config), "continuation preflight")
    queue.require_equal(
        plan.get("external_smoke_gate"),
        verify_external_smoke_gate(config),
        "continuation external smoke gate",
    )
    queue.require_equal(plan.get("entries"), build_plan(config), "continuation plan entries")
    queue.require_equal(plan.get("stage_entries_n"), 20, "continuation plan entry count")
    queue.require_equal(plan.get("unique_jobs_n"), 20, "continuation plan unique count")
    return plan


# Imported archive/terminal/stop/finalize functions resolve through this gate.
queue.load_plan = load_plan


def entry_from_args(config: Mapping[str, Any], args: argparse.Namespace) -> dict[str, Any] | None:
    if not hasattr(args, "stage_key"):
        return None
    return queue.entry_for(load_plan(config), args.stage_key, args.stage_entry_order)


def parser() -> argparse.ArgumentParser:
    argument_parser = argparse.ArgumentParser(description=__doc__)
    argument_parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    commands = argument_parser.add_subparsers(dest="command", required=True)
    commands.add_parser("initialize")
    commands.add_parser("verify")
    next_parser = commands.add_parser("next")
    next_parser.add_argument("--format", choices=("json", "tsv"), default="json")
    for name in ("archive-training", "record-terminal"):
        queue.add_entry_arguments(commands.add_parser(name))
    failure = commands.add_parser("record-action-failure")
    queue.add_entry_arguments(failure)
    failure.add_argument("--action", required=True)
    failure.add_argument("--error-type", required=True)
    failure.add_argument("--message", required=True)
    failure.add_argument("--return-code", type=int)
    failure.add_argument("--log-path", type=Path)
    success = commands.add_parser("record-action-success")
    queue.add_entry_arguments(success)
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
    config_path = local_repo_path(args.config)
    config = load_config(config_path)
    entry = entry_from_args(config, args)
    if args.command == "initialize":
        result = initialize(config, config_path)
    elif args.command == "verify":
        result = {
            "state": "PASSED",
            "git": queue.verify_git_runtime(config),
            "locked_inputs": queue.verify_locked_inputs(config),
            "readout_method": verify_cachefix_readout_method(config),
            "preflight": queue.validate_preflight(config),
            "external_smoke_gate": verify_external_smoke_gate(config),
            "stage_entries_n": len(build_plan(config)),
            "interpretation_or_verdict": None,
        }
    elif args.command == "next":
        result = queue.next_action(config)
        if args.format == "tsv":
            print(queue.next_tsv(result))
            return 0
    elif args.command == "archive-training":
        result = queue.archive_training_failure(config, entry)
    elif args.command == "record-terminal":
        result = queue.record_terminal(config, entry)
    elif args.command == "record-action-failure":
        result = queue.record_action_failure(
            config,
            entry,
            action=args.action,
            error_type=args.error_type,
            message=args.message,
            return_code=args.return_code,
            log_path=queue.repo_path(args.log_path) if args.log_path is not None else None,
        )
    elif args.command == "record-action-success":
        result = queue.record_action_success(
            config,
            entry,
            action=args.action,
            log_path=queue.repo_path(args.log_path) if args.log_path is not None else None,
        )
    elif args.command == "stop-stage":
        result = queue.stop_stage(config)
    elif args.command == "snapshot":
        load_plan(config)
        result = queue.publish_status(config)
    elif args.command == "finalize":
        result = queue.finalize_queue(config)
    else:  # pragma: no cover
        raise queue.UnattendedError(f"unsupported command: {args.command}")
    print_json(result)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except queue.UnattendedError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2)
