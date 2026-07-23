#!/usr/bin/env python3
"""Same-HEAD recovery for the P1W classification receipt wrapper mismatch.

This retained, run-local controller makes no scientific change.  It imports
the exact committed postprocess driver, replaces only its classification
receipt validator in memory, seals two already-complete unsealed products,
and then resumes the original barrier chain in the same process.

The recovery is intentionally specific to correction commit
1dfdcb5ed204d88001bd6aaba4c04bef5f222c4d.  It fails closed if the commit,
tracked runtime source map, extract policy, existing classifier bytes, loss
cursor bytes, helper bytes, or preserved abort ledger differ.
"""
from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from typing import Any

sys.dont_write_bytecode = True


EXPECTED_HEAD = "1dfdcb5ed204d88001bd6aaba4c04bef5f222c4d"
EXPECTED_INITIAL_DRIVER_STATE_SHA256 = (
    "55578a334bb4ed19d81debc424685cda549df255e06edba576568eb1d222c44f"
)
EXPECTED_INITIAL_ABORT_EVENTS_SHA256 = (
    "f2039c90480614d6f7e3b738680cc0e3bf926ab73188a2f05e2b225410696b81"
)
EXPECTED_POLICY_SHA256 = (
    "ac7d5210b59ac04d5aeb7e853ed93514f1178308a771923f02ccaa33554155c7"
)
EXPECTED_CROP_CONTRACT_SHA256 = (
    "6d0b4b9136a51e8a5483025fe45c3dba962c71d32dbdc97a11358ae8f0385dda"
)
EXPECTED_ROOFPRINT_SHA256 = (
    "ab0db85f371aef2c95dda0e06d098b735d331b3ce8921acd513aa2f0b10bbc53"
)
EXPECTED_RUNTIME_SOURCES = {
    "phases/p2-gsjso/configs/pilot_1wave_postprocess_extract_policy_lock.json":
        "ac7d5210b59ac04d5aeb7e853ed93514f1178308a771923f02ccaa33554155c7",
    "phases/p2-gsjso/scripts/pilot_1wave_postprocess_driver.py":
        "8ccf1755127058abb4005e816efaca0ad38451dfd04d4e7f466f783c1dd3cd25",
    "phases/p2-gsjso/scripts/e5_c001_readout_extract_ablation.py":
        "560cd5540e529391957a74f5f9c9840d8932af613fe51bf981be723f012c8d6e",
    "phases/p2-gsjso/scripts/pilot_1wave_readout_lineage.py":
        "69a6e037c7c9c22ebc97a2e30abca24d6c4c8d05a4b70a412f7e128c7bdc6d80",
    "phases/p2-gsjso/scripts/pilot_1wave_scene_classify.py":
        "7acf1220f45f47afed01a6bc9532bdb4f70218dfed8aee657de6a6cbe027b36a",
    "phases/p2-gsjso/scripts/pilot_1wave_scoring.py":
        "7e40371708ab580c132b08e2ba411a3de530feddf35e908af74e4a086c102dcf",
    "phases/p2-gsjso/scripts/pilot_1wave_loss_cursor_aggregate.py":
        "d5bd5652017711cf0a0dd2bb205669782b12f3683b1e25471f9ffd4c2d801131",
    "phases/p2-gsjso/scripts/pilot_1wave_binding_audit.py":
        "9bb3134bd13b8823c297ac6d99870146b91b032586c4356f51fe8d159e8fd012",
}
EXPECTED_CLASSIFY_01_FILES = {
    "started.json":
        "a28d88d2190f77a82d032737e7bfc0a73178535e05ad8da1849e3cd0f49d71ed",
    "stdout.log":
        "a788acbf74036de7b593f38122ade98a6b04ef9e88847aefecc3949654692d6b",
    "scene_raw.las":
        "7a793c7a609d16345c5d3f202f6b3d09ec73bb6c56f30fc98c51469b503033ef",
    "scene_classified.las":
        "94f1a73e2f3efa570576d516842d935ebf969d907a8ead02557f9345cb3f1429",
    "pdal_pipeline.json":
        "c6cfdaf67a677846d41edbc2559f1a2666994a2e3d4f35dd2061acd5fa0c1920",
    "classification_receipt.json":
        "ff452f11e6a35138c0839df7aba9b4cec62aafc2316d783a3cc5701efbf5336d",
    "classification_receipt.log":
        "aeb43ea4b7e47c15de2b4224f49d542e29fa0d6da185ff545eb0cba25feac044",
}
EXPECTED_LOSS_FILES = {
    "started.json":
        "df06c352f023fe0dfa4fe356c29b64f50d0b0deebe983de818c25e4802a2ceca",
    "stdout.log":
        "a31ef8daac38643f3b13afea9e36eb09abc77a00096b2a6f2de7dce26adb84df",
    "pilot_1wave_loss_shares.csv":
        "01104b91c6faab26c40042bdf5bb510248b6dcd4a6736233087f593c8afe4a45",
    "pilot_1wave_loss_shares_receipt.json":
        "37703d6ec1f96095e759d7f6b919849de84587cb453a533f85d604d5340d5e70",
}
RECOVERY_SCHEMA = "jointbuildgs.pilot_1wave.same_head_receipt_recovery.v1"
RECONCILIATION_SCHEMA = "jointbuildgs.pilot_1wave.controller_reconciliation.v1"
EVIDENCE_LEDGER_SCHEMA = (
    "jointbuildgs.pilot_1wave.classify_validator_failure_evidence.v1"
)
SUPERSESSION_SCHEMA = (
    "jointbuildgs.pilot_1wave.postprocess_abort_supersession.v1"
)
CLASSIFY_JOB_ID = "01_seed1001"
ARCHIVE_NAME = "attempt3_1dfdcb5_classify_validator_schema"


class RecoveryError(RuntimeError):
    """A fail-closed recovery contract violation."""


def canonical_json(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path, block_size: int = 1 << 20) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(block_size), b""):
            digest.update(block)
    return digest.hexdigest()


def require_equal(actual: Any, expected: Any, label: str) -> None:
    if actual != expected:
        raise RecoveryError(f"{label} mismatch: {actual!r} != {expected!r}")


def require_sha(path: Path, expected: str, label: str) -> None:
    if not path.is_file() or path.is_symlink():
        raise RecoveryError(f"{label} is missing/non-regular: {path}")
    require_equal(sha256_file(path), expected, f"{label} SHA256")


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RecoveryError(f"cannot read JSON {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise RecoveryError(f"JSON root must be an object: {path}")
    return value


def run(command: Sequence[str], *, cwd: Path) -> str:
    process = subprocess.run(
        list(command),
        cwd=cwd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if process.returncode != 0:
        raise RecoveryError(
            f"command failed exit={process.returncode}: {list(command)!r}; "
            f"stderr={process.stderr.strip()}"
        )
    return process.stdout.strip()


def find_repo(path: Path) -> Path:
    for candidate in (path, *path.parents):
        driver = candidate / "phases/p2-gsjso/scripts/pilot_1wave_postprocess_driver.py"
        if driver.is_file() and (candidate / ".git").exists():
            return candidate
    raise RecoveryError(f"cannot locate repository above {path}")


HELPER_PATH = Path(__file__).resolve()
REPO = find_repo(HELPER_PATH.parent)
DRIVER_PATH = REPO / "phases/p2-gsjso/scripts/pilot_1wave_postprocess_driver.py"
POSTPROCESS_ROOT = (
    REPO
    / "phases/p2-gsjso/runs/20260721_pilot_1wave/training/postprocess"
)
HELPER_SHA256_PATH = HELPER_PATH.with_suffix(".sha256")


def verify_helper_bytes() -> str:
    if not HELPER_SHA256_PATH.is_file() or HELPER_SHA256_PATH.is_symlink():
        raise RecoveryError(f"helper SHA sidecar missing/non-regular: {HELPER_SHA256_PATH}")
    fields = HELPER_SHA256_PATH.read_text(encoding="ascii").strip().split()
    require_equal(len(fields), 2, "helper SHA sidecar fields")
    require_equal(fields[1], HELPER_PATH.name, "helper SHA sidecar filename")
    actual = sha256_file(HELPER_PATH)
    require_equal(actual, fields[0], "recovery helper SHA256")
    return actual


def import_committed_driver() -> Any:
    require_sha(
        DRIVER_PATH,
        EXPECTED_RUNTIME_SOURCES[
            "phases/p2-gsjso/scripts/pilot_1wave_postprocess_driver.py"
        ],
        "committed postprocess driver",
    )
    spec = importlib.util.spec_from_file_location(
        "p1w_committed_postprocess_driver", DRIVER_PATH
    )
    if spec is None or spec.loader is None:
        raise RecoveryError(f"cannot create import spec for {DRIVER_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def verify_static_binding(driver: Any) -> dict[str, Any]:
    helper_sha = verify_helper_bytes()
    require_equal(run(("git", "rev-parse", "HEAD"), cwd=REPO), EXPECTED_HEAD, "git HEAD")
    tracked = run(
        ("git", "status", "--porcelain=v1", "--untracked-files=no"), cwd=REPO
    )
    require_equal(tracked, "", "tracked worktree status")
    for relative, expected in EXPECTED_RUNTIME_SOURCES.items():
        require_sha(REPO / relative, expected, f"runtime source {relative}")
    require_equal(driver.query_git_head(), EXPECTED_HEAD, "driver git HEAD")

    state_path = POSTPROCESS_ROOT / "driver_state.json"
    state = driver.load_state()
    require_equal(state.get("schema"), driver.DRIVER_SCHEMA, "driver state schema")
    require_equal(state.get("correction_head"), EXPECTED_HEAD, "driver correction HEAD")
    require_equal(
        (state.get("preflight") or {}).get("committed_runtime_sources"),
        EXPECTED_RUNTIME_SOURCES,
        "driver runtime source map",
    )
    policy = (state.get("preflight") or {}).get("extract_policy_lock") or {}
    require_equal(policy.get("sha256"), EXPECTED_POLICY_SHA256, "state policy SHA")
    require_equal(policy.get("mode"), "serial", "state extract policy mode")
    require_equal(policy.get("max_parallel"), 1, "state extract max parallel")
    require_equal(policy.get("job_order"), [
        "01_seed1001", "01_seed1002", "02_seed1001", "02_seed1002",
        "03_seed1001", "03_seed1002", "04a_seed1001", "04a_seed1002",
        "04b_seed1001", "04b_seed1002",
    ], "state extract policy order")
    require_equal(
        state.get("learning_runs_started_by_postprocess"),
        0,
        "postprocess learning run count",
    )
    state_name = state.get("state")
    archive = None
    if state_name == "aborted" and "superseded_abort_archive" not in state:
        require_equal(
            sha256_file(state_path),
            EXPECTED_INITIAL_DRIVER_STATE_SHA256,
            "exact initial aborted driver state",
        )
        original_state = state
        phase = "initial_aborted"
    elif state_name in {"recovery_ready", "running"}:
        archive = validate_sealed_archive(driver, helper_sha)
        require_equal(
            state.get("superseded_abort_archive"),
            archive,
            "live/sealed supersession archive binding",
        )
        controller = state.get("recovery_controller") or {}
        require_equal(controller.get("helper_sha256"), helper_sha,
                      "live recovery helper SHA")
        require_equal(controller.get("correction_head"), EXPECTED_HEAD,
                      "live recovery correction HEAD")
        require_equal(state.get("abort_events"), [],
                      "interrupted recovery canonical abort ledger")
        original_state = load_json(
            driver.POSTPROCESS_FAILED_ATTEMPTS_ROOT
            / ARCHIVE_NAME
            / "driver_state.json"
        )
        phase = f"resume_{state_name}"
    else:
        raise RecoveryError(
            f"unsupported live recovery state: {state_name!r}"
        )
    aborts = original_state.get("abort_events")
    if not isinstance(aborts, list):
        raise RecoveryError("the original abort ledger is not an array")
    require_equal(len(aborts), 1, "original abort event count")
    require_equal(
        sha256_bytes(canonical_json(aborts)),
        EXPECTED_INITIAL_ABORT_EVENTS_SHA256,
        "exact original abort ledger SHA",
    )
    last_abort = aborts[0]
    if not isinstance(last_abort, Mapping):
        raise RecoveryError("the original abort ledger entry is not an object")
    require_equal(last_abort.get("type"), "DriverError", "original abort type")
    require_equal(
        last_abort.get("message"),
        "crop mode mismatch: None != 'single_locked_global_bbox'",
        "original abort message",
    )
    return {
        "helper_sha256": helper_sha,
        "state": state,
        "original_state": original_state,
        "phase": phase,
        "archive": archive,
        "abort_events": copy.deepcopy(aborts),
        "abort_events_sha256": sha256_bytes(canonical_json(aborts)),
        "driver_state_sha256": sha256_file(state_path),
    }


def fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def evidence_record(driver: Any, path: Path) -> dict[str, Any]:
    if not path.is_file() or path.is_symlink():
        raise RecoveryError(f"failure evidence is missing/non-regular: {path}")
    return {
        "path": driver.repo_relative(path),
        "size": path.stat().st_size,
        "sha256": sha256_file(path),
    }


def archive_record(driver: Any, archive: Path) -> dict[str, Any]:
    archived_state = archive / "driver_state.json"
    ledger = archive / "evidence_sha256_ledger.json"
    supersession = archive / "supersession_receipt.json"
    complete = archive / "archive_complete.json"
    return {
        "name": ARCHIVE_NAME,
        "path": driver.repo_relative(archive),
        "driver_state_sha256": sha256_file(archived_state),
        "evidence_ledger": driver.repo_relative(ledger),
        "evidence_ledger_sha256": sha256_file(ledger),
        "supersession_receipt": driver.repo_relative(supersession),
        "supersession_receipt_sha256": sha256_file(supersession),
        "archive_complete": driver.repo_relative(complete),
        "archive_complete_sha256": sha256_file(complete),
        "abort_event_count": 1,
        "abort_events_sha256": EXPECTED_INITIAL_ABORT_EVENTS_SHA256,
    }


def validate_sealed_archive(driver: Any, helper_sha: str) -> dict[str, Any]:
    archive = driver.POSTPROCESS_FAILED_ATTEMPTS_ROOT / ARCHIVE_NAME
    if not archive.is_dir() or archive.is_symlink():
        raise RecoveryError(f"sealed supersession archive is missing: {archive}")
    state_path = archive / "driver_state.json"
    ledger_path = archive / "evidence_sha256_ledger.json"
    receipt_path = archive / "supersession_receipt.json"
    complete_path = archive / "archive_complete.json"
    require_sha(
        state_path,
        EXPECTED_INITIAL_DRIVER_STATE_SHA256,
        "sealed original driver state",
    )
    original = load_json(state_path)
    require_equal(original.get("state"), "aborted", "sealed original state")
    require_equal(
        sha256_bytes(canonical_json(original.get("abort_events"))),
        EXPECTED_INITIAL_ABORT_EVENTS_SHA256,
        "sealed original abort ledger",
    )
    ledger = load_json(ledger_path)
    require_equal(ledger.get("schema"), EVIDENCE_LEDGER_SCHEMA,
                  "sealed evidence ledger schema")
    require_equal(ledger.get("state"), "complete",
                  "sealed evidence ledger state")
    require_equal(ledger.get("original_abort_events_sha256"),
                  EXPECTED_INITIAL_ABORT_EVENTS_SHA256,
                  "sealed evidence abort SHA")
    copied = ledger.get("copied_evidence")
    if not isinstance(copied, list) or len(copied) != 2:
        raise RecoveryError("sealed archive must contain two copied controller logs")
    for record in copied:
        if not isinstance(record, Mapping):
            raise RecoveryError("sealed copied evidence record is not an object")
        archived = REPO / str(record.get("archived_path", ""))
        require_sha(archived, str(record.get("sha256")),
                    "sealed copied controller log")
        require_equal(archived.stat().st_size, int(record.get("size", -1)),
                      "sealed copied controller log size")
        require_equal(record.get("byte_for_byte_copy"), True,
                      "sealed copied controller log byte binding")
    receipt = load_json(receipt_path)
    require_equal(receipt.get("schema"), SUPERSESSION_SCHEMA,
                  "sealed supersession schema")
    require_equal(receipt.get("state"), "archived_before_live_reset",
                  "sealed supersession state")
    require_equal(receipt.get("archive_name"), ARCHIVE_NAME,
                  "sealed archive name")
    require_equal(receipt.get("driver_state_sha256"),
                  EXPECTED_INITIAL_DRIVER_STATE_SHA256,
                  "sealed supersession driver state SHA")
    require_equal(receipt.get("abort_events_sha256"),
                  EXPECTED_INITIAL_ABORT_EVENTS_SHA256,
                  "sealed supersession abort SHA")
    require_equal(receipt.get("recovery_helper_sha256"), helper_sha,
                  "sealed supersession helper SHA")
    complete = load_json(complete_path)
    require_equal(complete.get("schema"), SUPERSESSION_SCHEMA,
                  "sealed archive completion schema")
    require_equal(complete.get("state"), "complete",
                  "sealed archive completion state")
    require_equal(complete.get("driver_state_sha256"),
                  EXPECTED_INITIAL_DRIVER_STATE_SHA256,
                  "sealed completion driver state SHA")
    require_equal(complete.get("evidence_ledger_sha256"),
                  sha256_file(ledger_path), "sealed completion ledger SHA")
    require_equal(complete.get("supersession_receipt_sha256"),
                  sha256_file(receipt_path), "sealed completion receipt SHA")
    return archive_record(driver, archive)


def archive_aborted_attempt(
    driver: Any,
    recovery: Mapping[str, Any],
    classify_attempt: Path,
    loss_attempt: Path,
) -> dict[str, Any]:
    """Build off-tree, fsync, atomically rename, and validate the archive."""

    root = driver.POSTPROCESS_FAILED_ATTEMPTS_ROOT
    root.mkdir(parents=True, exist_ok=True)
    archive = root / ARCHIVE_NAME
    if archive.exists():
        return validate_sealed_archive(driver, str(recovery["helper_sha256"]))
    staging = Path(tempfile.mkdtemp(
        prefix=f".{ARCHIVE_NAME}.",
        dir=HELPER_PATH.parent,
    ))

    live_state = POSTPROCESS_ROOT / "driver_state.json"
    archived_state = staging / "driver_state.json"
    state_bytes = live_state.read_bytes()
    require_equal(
        sha256_bytes(state_bytes), EXPECTED_INITIAL_DRIVER_STATE_SHA256,
        "exact live state before byte archive",
    )
    driver.atomic_bytes(archived_state, state_bytes)
    require_equal(
        archived_state.read_bytes(), state_bytes, "byte-for-byte archived driver state"
    )

    log_sources = [
        POSTPROCESS_ROOT / "controller_systemd.log",
        POSTPROCESS_ROOT / "loss_precompute_systemd.log",
    ]
    copied_logs = []
    for source in log_sources:
        if not source.is_file() or source.is_symlink():
            raise RecoveryError(f"controller log missing/non-regular: {source}")
        destination = staging / source.name
        source_bytes = source.read_bytes()
        driver.atomic_bytes(destination, source_bytes)
        require_equal(destination.read_bytes(), source_bytes,
                      f"byte-for-byte copied log {source.name}")
        copied_logs.append({
            "source_path": driver.repo_relative(source),
            "archived_path": driver.repo_relative(archive / source.name),
            "size": len(source_bytes),
            "sha256": sha256_bytes(source_bytes),
            "byte_for_byte_copy": True,
        })
    evidence_paths = [
        *(
            classify_attempt / name
            for name in EXPECTED_CLASSIFY_01_FILES
        ),
        *(
            loss_attempt / name
            for name in EXPECTED_LOSS_FILES
        ),
        *sorted((loss_attempt / "run_receipts").glob("*.json")),
    ]
    ledger = staging / "evidence_sha256_ledger.json"
    driver.atomic_json(ledger, {
        "schema": EVIDENCE_LEDGER_SCHEMA,
        "state": "complete",
        "created_utc": driver.now(),
        "reason": "classification_receipt_wrapper_validator_schema_mismatch",
        "correction_head": EXPECTED_HEAD,
        "archived_driver_state": {
            "path": driver.repo_relative(archive / "driver_state.json"),
            "size": archived_state.stat().st_size,
            "sha256": sha256_file(archived_state),
            "byte_for_byte_copy": True,
        },
        "copied_evidence": copied_logs,
        "copied_evidence_count": len(copied_logs),
        "original_abort_events": recovery["abort_events"],
        "original_abort_events_sha256": recovery["abort_events_sha256"],
        "evidence": [evidence_record(driver, path) for path in evidence_paths],
        "evidence_file_count": len(evidence_paths),
        "learning_runs_started": 0,
        "gpu_work_started": 0,
    })
    supersession = staging / "supersession_receipt.json"
    driver.atomic_json(supersession, {
        "schema": SUPERSESSION_SCHEMA,
        "state": "archived_before_live_reset",
        "created_utc": driver.now(),
        "reason": "validator_schema_only_recovery_same_head",
        "archive_name": ARCHIVE_NAME,
        "archive_path": driver.repo_relative(archive),
        "correction_head": EXPECTED_HEAD,
        "driver_state_sha256": sha256_file(archived_state),
        "evidence_ledger_sha256": sha256_file(ledger),
        "abort_events_sha256": recovery["abort_events_sha256"],
        "recovery_helper": driver.repo_relative(HELPER_PATH),
        "recovery_helper_sha256": recovery["helper_sha256"],
        "monkeypatch_scope":
            "validate_classification_and_classify_stage_marker_provenance",
        "recovery_service_log_policy":
            "external_to_superseded_archive_during_active_recovery",
        "scientific_outputs_changed": False,
        "retraining": False,
        "learning_runs_started": 0,
        "gpu_work_started": 0,
    })
    complete = staging / "archive_complete.json"
    driver.atomic_json(complete, {
        "schema": SUPERSESSION_SCHEMA,
        "state": "complete",
        "completed_utc": driver.now(),
        "driver_state_sha256": sha256_file(archived_state),
        "evidence_ledger_sha256": sha256_file(ledger),
        "supersession_receipt_sha256": sha256_file(supersession),
    })
    fsync_directory(staging)
    os.replace(staging, archive)
    fsync_directory(root)
    fsync_directory(archive)
    return validate_sealed_archive(driver, str(recovery["helper_sha256"]))


def reset_live_abort_ledger(
    driver: Any,
    recovery: Mapping[str, Any],
    archive: Mapping[str, Any],
) -> dict[str, Any]:
    """Start the canonical recovered attempt only after the archive is sealed."""

    complete = REPO / str(archive["archive_complete"])
    require_sha(
        complete,
        str(archive["archive_complete_sha256"]),
        "supersession archive completion receipt",
    )
    state = driver.load_state()
    require_equal(state, recovery["state"], "live state before canonical reset")
    state["state"] = "recovery_ready"
    state["updated_utc"] = driver.now()
    state["abort_events"] = []
    state.pop("last_error", None)
    state["superseded_abort_archive"] = dict(archive)
    state["recovery_controller"] = {
        "schema": RECOVERY_SCHEMA,
        "state": "ready",
        "reason": "classification_receipt_wrapper_validator_schema_mismatch",
        "correction_head": EXPECTED_HEAD,
        "helper": driver.repo_relative(HELPER_PATH),
        "helper_sha256": recovery["helper_sha256"],
        "monkeypatch_scope":
            "validate_classification_and_classify_stage_marker_provenance",
        "scientific_outputs_changed": False,
        "retraining": False,
        "learning_runs_started": 0,
        "gpu_work_started": 0,
    }
    driver.save_state(state)
    reset = driver.load_state()
    require_equal(reset.get("abort_events"), [], "canonical abort ledger reset")
    require_equal(
        (reset.get("superseded_abort_archive") or {}).get("archive_complete_sha256"),
        archive["archive_complete_sha256"],
        "canonical superseded archive binding",
    )
    require_equal(
        reset.get("learning_runs_started_by_postprocess"),
        0,
        "canonical reset learning run count",
    )
    return reset


def decode_crop_contract_wrapper(
    driver: Any,
    receipt: Mapping[str, Any],
    receipt_path: Path,
    job_id: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    wrapper = receipt.get("crop_contract")
    if not isinstance(wrapper, Mapping):
        raise RecoveryError(f"{job_id} crop contract wrapper is missing")
    require_equal(set(wrapper), {
        "schema", "json", "sha256", "crs", "population_count",
        "ordered_building_ids", "ordered_ids_sha256", "crop_bbox_utm",
        "crop_area_m2",
    }, f"{job_id} normalized crop wrapper keys")
    encoded = wrapper.get("json")
    if not isinstance(encoded, str):
        raise RecoveryError(f"{job_id} crop contract wrapper JSON is not a string")
    encoded_bytes = encoded.encode("utf-8")
    encoded_sha = sha256_bytes(encoded_bytes)
    require_equal(encoded_sha, EXPECTED_CROP_CONTRACT_SHA256,
                  f"{job_id} exact crop contract SHA")
    require_equal(wrapper.get("sha256"), encoded_sha,
                  f"{job_id} wrapper crop contract SHA")
    try:
        decoded = json.loads(encoded)
    except json.JSONDecodeError as exc:
        raise RecoveryError(f"{job_id} crop contract JSON cannot decode: {exc}") from exc
    if not isinstance(decoded, dict):
        raise RecoveryError(f"{job_id} decoded crop contract is not an object")
    require_equal(
        canonical_json(decoded),
        encoded_bytes,
        f"{job_id} canonical crop contract JSON",
    )

    crop = decoded.get("crop") or {}
    population = decoded.get("population") or {}
    normalized = {
        "schema": decoded.get("schema"),
        "crs": decoded.get("crs"),
        "population_count": population.get("count"),
        "ordered_building_ids": population.get("ordered_building_ids"),
        "ordered_ids_sha256": population.get("ordered_ids_sha256"),
        "crop_bbox_utm": crop.get("bbox_utm"),
        "crop_area_m2": crop.get("area_m2"),
    }
    for key, expected in normalized.items():
        require_equal(wrapper.get(key), expected, f"{job_id} wrapper field {key}")

    lineage = receipt.get("readout_lineage") or {}
    require_equal(lineage.get("crop_contract_json"), encoded,
                  f"{job_id} lineage crop contract JSON")
    require_equal(lineage.get("crop_contract_sha256"), encoded_sha,
                  f"{job_id} lineage crop contract SHA")
    driver.validate_crop_contract(decoded)
    return decoded, {
        "receipt": driver.repo_relative(receipt_path),
        "wrapper_sha256": encoded_sha,
        "canonical_json": True,
        "normalized_wrapper_fields": sorted(normalized),
        "lineage_json_match": True,
        "lineage_sha256_match": True,
    }


def fixed_validate_classification(
    driver: Any,
    job: Any,
    attempt: Path,
    roofprints: Path,
) -> None:
    receipt_path = attempt / "classification_receipt.json"
    receipt = driver.load_json(receipt_path)
    driver.require_equal(
        receipt.get("schema"),
        "jointbuildgs.pilot_1wave.scene_classification.v1",
        f"{job.job_id} classification schema",
    )
    driver.require_equal(
        receipt.get("state"), "complete", f"{job.job_id} classification state"
    )
    driver.require_equal(
        receipt.get("crs"), "EPSG:25832", f"{job.job_id} classification CRS"
    )
    roof = receipt.get("roofprints") or {}
    driver.require_equal(
        driver._resolve_declared_path(roof.get("path"), declaring_file=receipt_path),
        roofprints.resolve(),
        f"{job.job_id} roofprint path",
    )
    driver.require_equal(
        roof.get("sha256"), driver.sha256_file(roofprints),
        f"{job.job_id} roofprint SHA",
    )
    driver.require_equal(
        tuple(roof.get("building_ids", [])),
        driver.EXPECTED_IDS,
        f"{job.job_id} roofprint order",
    )
    source = receipt.get("source_scene_npz") or {}
    expected_npz = driver.extract_attempt(job) / "scene_geometry.npz"
    driver.require_equal(
        driver._resolve_declared_path(source.get("path"), declaring_file=receipt_path),
        expected_npz.resolve(),
        f"{job.job_id} source NPZ path",
    )
    driver.require_equal(
        source.get("sha256"), driver.sha256_file(expected_npz),
        f"{job.job_id} source NPZ SHA",
    )
    driver.require_equal(source.get("array"), "P_utm_clean",
                         f"{job.job_id} source NPZ array")
    decode_crop_contract_wrapper(driver, receipt, receipt_path, job.job_id)
    lineage = receipt.get("readout_lineage") or {}
    driver.require_equal(
        lineage.get("condition_id"), job.condition,
        f"{job.job_id} classification condition",
    )
    driver.require_equal(
        int(lineage.get("seed", -1)), job.seed,
        f"{job.job_id} classification seed",
    )
    raw = receipt.get("raw_las") or {}
    raw_las = attempt / "scene_raw.las"
    driver.require_equal(
        driver._resolve_declared_path(raw.get("path"), declaring_file=receipt_path),
        raw_las.resolve(),
        f"{job.job_id} raw LAS path",
    )
    driver.require_equal(
        raw.get("sha256"), driver.sha256_file(raw_las),
        f"{job.job_id} raw LAS SHA",
    )
    classification = receipt.get("classification") or {}
    pipeline_path = attempt / "pdal_pipeline.json"
    driver.require_equal(
        driver._resolve_declared_path(
            classification.get("pipeline_path"), declaring_file=receipt_path
        ),
        pipeline_path.resolve(),
        f"{job.job_id} PDAL pipeline path",
    )
    driver.require_equal(
        classification.get("pipeline_sha256"),
        driver.sha256_file(pipeline_path),
        f"{job.job_id} PDAL pipeline SHA",
    )
    pipeline = driver.load_json(pipeline_path).get("pipeline")
    if not isinstance(pipeline, list) or len(pipeline) != 4:
        raise driver.DriverError(f"{job.job_id} PDAL pipeline must have four stages")
    reader, smrf, overlay, writer = pipeline
    driver.require_equal(reader.get("type"), "readers.las",
                         f"{job.job_id} PDAL reader type")
    driver.require_equal(
        driver._resolve_declared_path(
            reader.get("filename"), declaring_file=pipeline_path
        ),
        raw_las.resolve(),
        f"{job.job_id} PDAL reader path",
    )
    driver.require_equal(smrf, {
        "type": "filters.smrf", "cell": 1.0, "slope": 0.15,
        "scalar": 1.25, "threshold": 0.5, "window": 18.0,
        "ground_class": 2, "other_class": 1,
    }, f"{job.job_id} PDAL SMRF stage")
    driver.require_equal(overlay.get("type"), "filters.overlay",
                         f"{job.job_id} PDAL overlay type")
    driver.require_equal(overlay.get("dimension"), "Classification",
                         f"{job.job_id} PDAL overlay dimension")
    driver.require_equal(overlay.get("column"), "class",
                         f"{job.job_id} PDAL overlay column")
    driver.require_equal(overlay.get("where"), "Classification != 2",
                         f"{job.job_id} PDAL overlay ground exclusion")
    driver.require_equal(
        driver._resolve_declared_path(
            overlay.get("datasource"), declaring_file=pipeline_path
        ),
        roofprints.resolve(),
        f"{job.job_id} PDAL overlay roofprint",
    )
    driver.require_equal(writer.get("type"), "writers.las",
                         f"{job.job_id} PDAL writer type")
    driver.require_equal(
        driver._resolve_declared_path(
            writer.get("filename"), declaring_file=pipeline_path
        ),
        (attempt / "scene_classified.las").resolve(),
        f"{job.job_id} PDAL writer path",
    )
    driver.require_equal(
        {key: writer.get(key) for key in ("a_srs", "minor_version", "dataformat_id")},
        {"a_srs": "EPSG:25832", "minor_version": 4, "dataformat_id": 6},
        f"{job.job_id} PDAL writer contract",
    )
    classified = receipt.get("classified_las") or {}
    las = attempt / "scene_classified.las"
    driver.require_equal(
        driver._resolve_declared_path(classified.get("path"), declaring_file=receipt_path),
        las.resolve(),
        f"{job.job_id} classified LAS path",
    )
    driver.require_equal(
        classified.get("sha256"), driver.sha256_file(las),
        f"{job.job_id} classified LAS SHA",
    )
    driver.require_equal(
        int(classified.get("epsg", -1)), 25832,
        f"{job.job_id} classified LAS EPSG",
    )
    counts = classified.get("class_counts") or {}
    if int(counts.get("2", 0)) <= 0 or int(counts.get("6", 0)) <= 0:
        raise driver.DriverError(f"{job.job_id} classified LAS lacks class 2/6")
    driver.require_equal(
        int(classified.get("point_count", -1)),
        int(source.get("point_count", -2)),
        f"{job.job_id} classified/source point count",
    )
    driver.require_equal(
        receipt.get("learning_runs_started_by_this_adapter"), 0,
        f"{job.job_id} classifier learning run count",
    )


def atomic_reconciliation(driver: Any, path: Path, payload: Mapping[str, Any]) -> None:
    driver.atomic_json(path, {
        "schema": RECONCILIATION_SCHEMA,
        "state": "complete",
        "created_utc": driver.now(),
        **dict(payload),
    })


def verify_no_complete_marker(driver: Any, root: Path, stage: str, job_id: str) -> None:
    attempts = sorted(root.glob("attempt_[0-9][0-9][0-9]")) if root.is_dir() else []
    complete = [
        attempt for attempt in attempts
        if driver.valid_stage_attempt(attempt, stage, job_id)
    ]
    if complete:
        raise RecoveryError(
            f"{stage}/{job_id} is already sealed; refusing a duplicate marker: {complete}"
        )


def read_only_prerequisites(
    driver: Any,
    jobs: Sequence[Any],
) -> dict[str, Any]:
    extract_markers = []
    for job in jobs:
        attempt = driver.completed_attempt(
            driver.stage_root(job, "extract"), "extract", job.job_id
        )
        if attempt is None:
            raise RecoveryError(f"extract prerequisite is incomplete: {job.job_id}")
        driver.validate_extract(job, attempt)
        extract_markers.append(attempt / "stage_complete.json")
    require_equal(len(extract_markers), 10, "complete extract prerequisite count")
    roof_attempt = driver.completed_attempt(
        driver.global_stage_root("roofprint"), "roofprint", "global"
    )
    if roof_attempt is None:
        raise RecoveryError("global locked roofprint prerequisite is incomplete")
    roofprints = roof_attempt / "locked_roofprints.geojson"
    require_sha(roofprints, EXPECTED_ROOFPRINT_SHA256, "locked global roofprint")
    return {
        "extract_complete_count": len(extract_markers),
        "extract_marker_sha256": [
            sha256_file(path) for path in extract_markers
        ],
        "roofprint": roofprints,
        "roofprint_marker_sha256": sha256_file(
            roof_attempt / "stage_complete.json"
        ),
        "roofprint_sha256": sha256_file(roofprints),
    }


def classify_reconciliation_candidate(
    driver: Any,
    jobs: Sequence[Any],
    roofprints: Path,
    *,
    full_validation: bool,
) -> dict[str, Any]:
    indexed = {job.job_id: job for job in jobs}
    job = indexed.get(CLASSIFY_JOB_ID)
    if job is None:
        raise RecoveryError(f"validated job set lacks {CLASSIFY_JOB_ID}")
    root = driver.stage_root(job, "classify")
    attempts = sorted(root.glob("attempt_[0-9][0-9][0-9]"))
    require_equal(
        [path.name for path in attempts],
        ["attempt_001"],
        f"{job.job_id} unsealed classification attempts",
    )
    attempt = attempts[0]
    complete = driver.completed_attempt(root, "classify", job.job_id)
    already_reconciled = complete is not None
    if already_reconciled:
        require_equal(complete, attempt, f"{job.job_id} reconciled attempt")
        reconciliation = load_json(attempt / "controller_reconciliation.json")
        require_equal(reconciliation.get("recovery_helper_sha256"),
                      verify_helper_bytes(),
                      f"{job.job_id} reconciled helper SHA")
        marker_payload = load_json(attempt / "stage_complete.json")
        require_equal(marker_payload.get("recovery_helper_sha256"),
                      verify_helper_bytes(),
                      f"{job.job_id} marker helper SHA")
        marker_paths = {
            record.get("path")
            for record in marker_payload.get("outputs", [])
            if isinstance(record, Mapping)
        }
        for bound in (HELPER_PATH, HELPER_SHA256_PATH,
                      attempt / "controller_reconciliation.json"):
            if driver.repo_relative(bound) not in marker_paths:
                raise RecoveryError(
                    f"{job.job_id} marker lacks recovery provenance: {bound}"
                )
    elif (attempt / "stage_complete.json").exists():
        raise RecoveryError(
            f"{job.job_id} has an invalid/noncanonical stage marker"
        )
    if (attempt / "failure.json").exists():
        raise RecoveryError(f"{job.job_id} candidate contains failure.json")
    for name, expected_sha in EXPECTED_CLASSIFY_01_FILES.items():
        require_sha(attempt / name, expected_sha, f"{job.job_id} {name}")
    started = load_json(attempt / "started.json")
    require_equal(started.get("schema"), driver.STAGE_MARKER_SCHEMA,
                  f"{job.job_id} started schema")
    require_equal(started.get("state"), "started", f"{job.job_id} started state")
    require_equal(started.get("stage"), "classify", f"{job.job_id} started stage")
    require_equal(
        started.get("command"),
        driver.classify_command(job, attempt, roofprints),
        f"{job.job_id} committed classify command",
    )
    receipt = load_json(attempt / "classification_receipt.json")
    _, crop_audit = decode_crop_contract_wrapper(
        driver, receipt, attempt / "classification_receipt.json", job.job_id
    )
    if full_validation:
        fixed_validate_classification(driver, job, attempt, roofprints)
    return {
        "job": job,
        "attempt": attempt,
        "crop_audit": crop_audit,
        "file_sha256": dict(EXPECTED_CLASSIFY_01_FILES),
        "full_validation": full_validation,
        "already_reconciled": already_reconciled,
    }


def reconcile_classification(
    driver: Any,
    candidate: Mapping[str, Any],
    roofprints: Path,
    recovery: Mapping[str, Any],
    archive: Mapping[str, Any],
) -> Path:
    job = candidate["job"]
    attempt = candidate["attempt"]
    fixed_validate_classification(driver, job, attempt, roofprints)
    if candidate.get("already_reconciled"):
        marker = attempt / "stage_complete.json"
        if not driver.valid_stage_attempt(attempt, "classify", job.job_id):
            raise RecoveryError(f"{job.job_id} existing marker became invalid")
        receipt = load_json(attempt / "controller_reconciliation.json")
        require_equal(receipt.get("superseded_abort_archive"), archive,
                      f"{job.job_id} existing archive binding")
        require_equal(
            load_json(marker).get("superseded_abort_archive_sha256"),
            archive["archive_complete_sha256"],
            f"{job.job_id} existing marker archive SHA",
        )
        return marker
    reconciliation = attempt / "controller_reconciliation.json"
    atomic_reconciliation(driver, reconciliation, {
        "reason": "classifier_exit_0_outputs_complete_wrapper_validator_shape_only",
        "job_id": job.job_id,
        "attempt": driver.repo_relative(attempt),
        "correction_head": EXPECTED_HEAD,
        "runtime_sources_sha256": driver.sha256_bytes(
            driver.canonical_json(EXPECTED_RUNTIME_SOURCES)
        ),
        "extract_policy_sha256": EXPECTED_POLICY_SHA256,
        "recovery_helper": driver.repo_relative(HELPER_PATH),
        "recovery_helper_sha256": recovery["helper_sha256"],
        "monkeypatch_scope":
            "validate_classification_and_classify_stage_marker_provenance",
        "preserved_abort_events_sha256": recovery["abort_events_sha256"],
        "superseded_abort_archive": dict(archive),
        "crop_contract": candidate["crop_audit"],
        "original_files": [
            {"path": driver.repo_relative(attempt / name), "sha256": digest}
            for name, digest in EXPECTED_CLASSIFY_01_FILES.items()
        ],
        "command_reexecuted": False,
        "classification_invocations_started_by_recovery": 0,
        "learning_runs_started": 0,
        "gpu_work_started": 0,
    })
    marker = driver.write_stage_marker(
        attempt,
        "classify",
        job.job_id,
        (
            attempt / "scene_raw.las",
            attempt / "scene_classified.las",
            attempt / "pdal_pipeline.json",
            attempt / "classification_receipt.json",
            attempt / "classification_receipt.log",
            reconciliation,
            HELPER_PATH,
            HELPER_SHA256_PATH,
        ),
        {
            "roofprint_sha256": driver.sha256_file(roofprints),
            "controller_reconciliation": driver.repo_relative(reconciliation),
            "recovery_helper_sha256": recovery["helper_sha256"],
            "crop_contract_sha256": EXPECTED_CROP_CONTRACT_SHA256,
            "superseded_abort_archive_sha256":
                archive["archive_complete_sha256"],
        },
    )
    if not driver.valid_stage_attempt(attempt, "classify", job.job_id):
        raise RecoveryError(f"{job.job_id} reconciled stage marker is invalid")
    require_equal(
        driver.completed_attempt(
            driver.stage_root(job, "classify"), "classify", job.job_id
        ),
        attempt,
        f"{job.job_id} unique completed classification attempt",
    )
    return marker


def expected_loss_precompute_command(driver: Any, attempt: Path) -> list[str]:
    return [
        "docker", "run", "--rm", "--network", "none",
        "--memory", "12g", "--memory-swap", "12g",
        "--user", f"{os.getuid()}:{os.getgid()}",
        "-e", "PYTHONDONTWRITEBYTECODE=1",
        "-e", "HOME=/tmp/p1w-loss-home",
        "-e", "XDG_CACHE_HOME=/tmp/p1w-loss-cache",
        "-e", "NVIDIA_VISIBLE_DEVICES=none",
        "-e", "CUDA_VISIBLE_DEVICES=-1",
        "-v", f"{REPO}:{driver.CONTAINER_REPO}",
        "-w", str(driver.CONTAINER_REPO),
        driver.DEV_IMAGE_ID,
        "python3", driver.container_path(driver.LOSS_AGGREGATE),
        "--training-root", driver.container_path(driver.TRAINING_ROOT / "runs"),
        "--output", driver.container_path(attempt / driver.LOSS_OUTPUT_NAME),
        "--receipt", driver.container_path(attempt / driver.LOSS_RECEIPT_NAME),
        "--run-receipt-dir", driver.container_path(attempt / "run_receipts"),
    ]


def loss_reconciliation_candidate(
    driver: Any,
    *,
    full_validation: bool,
) -> dict[str, Any]:
    root = driver.global_stage_root("loss_cursor")
    attempts = sorted(root.glob("attempt_[0-9][0-9][0-9]"))
    require_equal(
        [path.name for path in attempts],
        ["attempt_001"],
        "unsealed loss cursor attempts",
    )
    attempt = attempts[0]
    complete = driver.completed_attempt(root, "loss_cursor", "global")
    already_reconciled = complete is not None
    if already_reconciled:
        require_equal(complete, attempt, "reconciled loss cursor attempt")
        reconciliation = load_json(attempt / "controller_reconciliation.json")
        require_equal(reconciliation.get("recovery_helper_sha256"),
                      verify_helper_bytes(),
                      "reconciled loss cursor helper SHA")
        marker_payload = load_json(attempt / "stage_complete.json")
        require_equal(marker_payload.get("recovery_helper_sha256"),
                      verify_helper_bytes(),
                      "reconciled loss cursor marker helper SHA")
        marker_paths = {
            record.get("path")
            for record in marker_payload.get("outputs", [])
            if isinstance(record, Mapping)
        }
        for bound in (HELPER_PATH, HELPER_SHA256_PATH,
                      attempt / "controller_reconciliation.json"):
            if driver.repo_relative(bound) not in marker_paths:
                raise RecoveryError(
                    f"loss cursor marker lacks recovery provenance: {bound}"
                )
    elif (attempt / "stage_complete.json").exists():
        raise RecoveryError("loss cursor has an invalid/noncanonical stage marker")
    if (attempt / "failure.json").exists():
        raise RecoveryError("loss cursor candidate contains failure.json")
    for name, expected_sha in EXPECTED_LOSS_FILES.items():
        require_sha(attempt / name, expected_sha, f"loss cursor {name}")
    started = load_json(attempt / "started.json")
    require_equal(started.get("schema"), driver.STAGE_MARKER_SCHEMA,
                  "loss cursor started schema")
    require_equal(started.get("state"), "started", "loss cursor started state")
    require_equal(started.get("stage"), "loss_cursor", "loss cursor started stage")
    require_equal(
        started.get("command"),
        expected_loss_precompute_command(driver, attempt),
        "loss cursor bounded CPU precompute command",
    )
    receipt = load_json(attempt / driver.LOSS_RECEIPT_NAME)
    require_equal(receipt.get("cpu_only"), True, "loss cursor CPU-only receipt")
    require_equal(receipt.get("checkpoint_map_location"), "cpu",
                  "loss cursor checkpoint map location")
    script = receipt.get("script") or {}
    require_equal(
        script.get("sha256"),
        EXPECTED_RUNTIME_SOURCES[
            "phases/p2-gsjso/scripts/pilot_1wave_loss_cursor_aggregate.py"
        ],
        "loss cursor committed script SHA",
    )
    validated = (
        driver.validate_loss_aggregate_outputs(attempt) if full_validation else None
    )
    return {
        "attempt": attempt,
        "validated": validated,
        "file_sha256": dict(EXPECTED_LOSS_FILES),
        "full_validation": full_validation,
        "already_reconciled": already_reconciled,
    }


def reconcile_loss(
    driver: Any,
    candidate: Mapping[str, Any],
    recovery: Mapping[str, Any],
    archive: Mapping[str, Any],
) -> Path:
    attempt = candidate["attempt"]
    loss = driver.validate_loss_aggregate_outputs(attempt)
    if candidate.get("already_reconciled"):
        marker = attempt / "stage_complete.json"
        if not driver.valid_stage_attempt(attempt, "loss_cursor", "global"):
            raise RecoveryError("existing loss cursor marker became invalid")
        receipt = load_json(attempt / "controller_reconciliation.json")
        require_equal(receipt.get("superseded_abort_archive"), archive,
                      "existing loss cursor archive binding")
        require_equal(
            load_json(marker).get("superseded_abort_archive_sha256"),
            archive["archive_complete_sha256"],
            "existing loss cursor marker archive SHA",
        )
        return marker
    reconciliation = attempt / "controller_reconciliation.json"
    atomic_reconciliation(driver, reconciliation, {
        "reason": "bounded_cpu_precompute_exit_0_outputs_complete_controller_aborted_before_marker",
        "job_id": "global",
        "attempt": driver.repo_relative(attempt),
        "correction_head": EXPECTED_HEAD,
        "runtime_sources_sha256": driver.sha256_bytes(
            driver.canonical_json(EXPECTED_RUNTIME_SOURCES)
        ),
        "extract_policy_sha256": EXPECTED_POLICY_SHA256,
        "recovery_helper": driver.repo_relative(HELPER_PATH),
        "recovery_helper_sha256": recovery["helper_sha256"],
        "preserved_abort_events_sha256": recovery["abort_events_sha256"],
        "superseded_abort_archive": dict(archive),
        "original_files": [
            {"path": driver.repo_relative(attempt / name), "sha256": digest}
            for name, digest in EXPECTED_LOSS_FILES.items()
        ],
        "aggregate_output_sha256": loss["output_sha256"],
        "aggregate_receipt_sha256": loss["receipt_sha256"],
        "run_receipt_count": len(loss["run_receipts"]),
        "command_reexecuted": False,
        "loss_aggregate_invocations_started_by_recovery": 0,
        "learning_runs_started": 0,
        "gpu_work_started": 0,
    })
    run_receipts = tuple(record["path"] for record in loss["run_receipts"])
    marker = driver.write_stage_marker(
        attempt,
        "loss_cursor",
        "global",
        (
            loss["output"],
            loss["receipt"],
            *run_receipts,
            reconciliation,
            HELPER_PATH,
            HELPER_SHA256_PATH,
        ),
        {
            "run_receipt_count": 10,
            "controller_reconciliation": driver.repo_relative(reconciliation),
            "recovery_helper_sha256": recovery["helper_sha256"],
            "aggregate_output_sha256": loss["output_sha256"],
            "superseded_abort_archive_sha256":
                archive["archive_complete_sha256"],
        },
    )
    if not driver.valid_stage_attempt(attempt, "loss_cursor", "global"):
        raise RecoveryError("reconciled loss cursor stage marker is invalid")
    require_equal(
        driver.completed_attempt(
            driver.global_stage_root("loss_cursor"), "loss_cursor", "global"
        ),
        attempt,
        "unique completed loss cursor attempt",
    )
    return marker


def recovered_stage_marker_writer(
    driver: Any,
    original_writer: Any,
    recovery: Mapping[str, Any],
    archive: Mapping[str, Any],
) -> Any:
    """Bind the run-local helper to each newly executed classification marker."""

    def writer(
        attempt: Path,
        stage: str,
        job_id: str,
        outputs: Any,
        extra: Mapping[str, Any] | None = None,
    ) -> Path:
        output_tuple = tuple(outputs)
        merged_extra = dict(extra or {})
        if stage == "classify":
            receipt_path = attempt / "classification_receipt.json"
            receipt = driver.load_json(receipt_path)
            _, crop_audit = decode_crop_contract_wrapper(
                driver, receipt, receipt_path, job_id
            )
            reconciliation = attempt / "controller_reconciliation.json"
            atomic_reconciliation(driver, reconciliation, {
                "reason": "same_head_normalized_wrapper_validator_applied",
                "job_id": job_id,
                "attempt": driver.repo_relative(attempt),
                "correction_head": EXPECTED_HEAD,
                "runtime_sources_sha256": driver.sha256_bytes(
                    driver.canonical_json(EXPECTED_RUNTIME_SOURCES)
                ),
                "extract_policy_sha256": EXPECTED_POLICY_SHA256,
                "recovery_helper": driver.repo_relative(HELPER_PATH),
                "recovery_helper_sha256": recovery["helper_sha256"],
                "monkeypatch_scope":
                    "validate_classification_and_classify_stage_marker_provenance",
                "superseded_abort_archive": dict(archive),
                "crop_contract": crop_audit,
                "command_reexecuted": True,
                "classification_invocations_started_by_recovery": 1,
                "learning_runs_started": 0,
                "gpu_work_started": 0,
            })
            output_tuple = (
                *output_tuple,
                reconciliation,
                HELPER_PATH,
                HELPER_SHA256_PATH,
            )
            merged_extra.update({
                "controller_reconciliation":
                    driver.repo_relative(reconciliation),
                "recovery_helper_sha256": recovery["helper_sha256"],
                "crop_contract_sha256": EXPECTED_CROP_CONTRACT_SHA256,
                "superseded_abort_archive_sha256":
                    archive["archive_complete_sha256"],
            })
        return original_writer(
            attempt, stage, job_id, output_tuple, merged_extra
        )

    return writer


def validate_existing_recovery_classifications(
    driver: Any,
    jobs: Sequence[Any],
    roofprints: Path,
    recovery: Mapping[str, Any],
    archive: Mapping[str, Any],
) -> int:
    """Re-open every sealed classify marker before an interrupted resume."""

    checked = 0
    for job in jobs:
        attempt = driver.completed_attempt(
            driver.stage_root(job, "classify"), "classify", job.job_id
        )
        if attempt is None:
            continue
        fixed_validate_classification(driver, job, attempt, roofprints)
        marker = load_json(attempt / "stage_complete.json")
        require_equal(marker.get("recovery_helper_sha256"),
                      recovery["helper_sha256"],
                      f"{job.job_id} sealed marker helper SHA")
        require_equal(marker.get("superseded_abort_archive_sha256"),
                      archive["archive_complete_sha256"],
                      f"{job.job_id} sealed marker archive SHA")
        reconciliation_path = attempt / "controller_reconciliation.json"
        reconciliation = load_json(reconciliation_path)
        require_equal(reconciliation.get("recovery_helper_sha256"),
                      recovery["helper_sha256"],
                      f"{job.job_id} sealed receipt helper SHA")
        require_equal(reconciliation.get("superseded_abort_archive"), archive,
                      f"{job.job_id} sealed receipt archive")
        output_paths = {
            record.get("path")
            for record in marker.get("outputs", [])
            if isinstance(record, Mapping)
        }
        for bound in (HELPER_PATH, HELPER_SHA256_PATH, reconciliation_path):
            if driver.repo_relative(bound) not in output_paths:
                raise RecoveryError(
                    f"{job.job_id} sealed marker lacks bound recovery file: {bound}"
                )
        checked += 1
    return checked


def record_canonical_recovery_failure(
    driver: Any,
    recovery: Mapping[str, Any],
    archive: Mapping[str, Any],
    exc: BaseException,
) -> None:
    """Ensure failures after the live reset enter the canonical abort ledger."""

    state = driver.load_state()
    aborts = state.get("abort_events")
    if not isinstance(aborts, list):
        aborts = []
    event = {
        "at": driver.now(),
        "type": type(exc).__name__,
        "message": str(exc),
        "phase": "same_head_receipt_recovery",
        "recovery_helper_sha256": recovery["helper_sha256"],
        "superseded_abort_archive_sha256": archive["archive_complete_sha256"],
    }
    duplicate = (
        bool(aborts)
        and isinstance(aborts[-1], Mapping)
        and aborts[-1].get("type") == event["type"]
        and aborts[-1].get("message") == event["message"]
    )
    if not duplicate:
        aborts.append(event)
    state.update({
        "state": "aborted",
        "updated_utc": driver.now(),
        "abort_events": aborts,
        "last_error": aborts[-1],
    })
    driver.save_state(state)


def exact_preflight(driver: Any, expected_state: Mapping[str, Any]) -> tuple[list[Any], dict[str, Any]]:
    jobs, checked = driver.preflight(EXPECTED_HEAD, None, None)
    require_equal(
        checked.get("committed_runtime_sources"),
        EXPECTED_RUNTIME_SOURCES,
        "fresh preflight runtime source map",
    )
    policy = checked.get("extract_policy_lock") or {}
    require_equal(policy.get("sha256"), EXPECTED_POLICY_SHA256,
                  "fresh preflight extract policy SHA")
    require_equal(
        policy,
        (expected_state.get("preflight") or {}).get("extract_policy_lock"),
        "fresh/state exact extract policy",
    )
    require_equal(
        checked.get("wave2_launch"),
        {"status": "blocked_missing_wave2_lock", "launch_performed": False},
        "Wave 2 lock state",
    )
    require_equal(
        checked.get("learning_runs_started_by_postprocess"), 0,
        "preflight learning run count",
    )
    return jobs, checked


def assert_original_abort_ledger_unmodified(
    driver: Any,
    recovery: Mapping[str, Any],
) -> None:
    state = driver.load_state()
    require_equal(
        state.get("abort_events"),
        recovery["abort_events"],
        "preserved abort event ledger",
    )
    require_equal(
        sha256_bytes(canonical_json(state.get("abort_events"))),
        recovery["abort_events_sha256"],
        "preserved abort event ledger SHA",
    )
    require_equal(
        state.get("learning_runs_started_by_postprocess"), 0,
        "post-reconciliation learning run count",
    )


def assert_canonical_reset(
    driver: Any,
    archive: Mapping[str, Any],
) -> None:
    state = driver.load_state()
    require_equal(state.get("abort_events"), [], "canonical live abort ledger")
    require_equal(
        (state.get("superseded_abort_archive") or {}).get(
            "archive_complete_sha256"
        ),
        archive["archive_complete_sha256"],
        "canonical live superseded archive binding",
    )
    require_equal(
        state.get("learning_runs_started_by_postprocess"), 0,
        "canonical live learning run count",
    )


def recovery_plan(
    driver: Any,
    jobs: Sequence[Any],
    recovery: Mapping[str, Any],
    *,
    full_validation: bool,
) -> dict[str, Any]:
    prerequisites = read_only_prerequisites(driver, jobs)
    roofprints = prerequisites["roofprint"]
    classify = classify_reconciliation_candidate(
        driver, jobs, roofprints, full_validation=full_validation
    )
    loss = loss_reconciliation_candidate(driver, full_validation=full_validation)
    return {
        "schema": RECOVERY_SCHEMA,
        "state": "ready",
        "mode": "dry-run",
        "correction_head": EXPECTED_HEAD,
        "runtime_sources": EXPECTED_RUNTIME_SOURCES,
        "extract_policy_sha256": EXPECTED_POLICY_SHA256,
        "recovery_helper_sha256": recovery["helper_sha256"],
        "preserved_abort_event_count": len(recovery["abort_events"]),
        "preserved_abort_events_sha256": recovery["abort_events_sha256"],
        "prerequisites": {
            "extract_complete_count": prerequisites["extract_complete_count"],
            "roofprint_sha256": prerequisites["roofprint_sha256"],
        },
        "planned_supersession_archive": driver.repo_relative(
            driver.POSTPROCESS_FAILED_ATTEMPTS_ROOT / ARCHIVE_NAME
        ),
        "planned_live_abort_event_count_after_reset": 0,
        "classification_reconciliation": {
            "job_id": CLASSIFY_JOB_ID,
            "attempt": driver.repo_relative(classify["attempt"]),
            "full_validation": classify["full_validation"],
            "command_reexecuted": False,
        },
        "loss_reconciliation": {
            "attempt": driver.repo_relative(loss["attempt"]),
            "full_validation": loss["full_validation"],
            "command_reexecuted": False,
        },
        "remaining_classification_jobs": [
            job.job_id for job in jobs if job.job_id != CLASSIFY_JOB_ID
        ],
        "resume_entrypoint": "committed_driver.execute_resume_same_process",
        "monkeypatch_scope":
            "validate_classification_and_classify_stage_marker_provenance",
        "learning_runs_started": 0,
        "wave2_launch_performed": False,
    }


def self_test(driver: Any, recovery: Mapping[str, Any]) -> dict[str, Any]:
    receipt_path = (
        POSTPROCESS_ROOT
        / "attempts/01_seed1001/classify/attempt_001/classification_receipt.json"
    )
    receipt = load_json(receipt_path)
    _, crop = decode_crop_contract_wrapper(
        driver, receipt, receipt_path, CLASSIFY_JOB_ID
    )
    return {
        "schema": RECOVERY_SCHEMA,
        "state": "pass",
        "mode": "self-test",
        "correction_head": EXPECTED_HEAD,
        "recovery_helper_sha256": recovery["helper_sha256"],
        "runtime_source_count": len(EXPECTED_RUNTIME_SOURCES),
        "extract_policy_sha256": EXPECTED_POLICY_SHA256,
        "crop_contract": crop,
        "preserved_abort_event_count": len(recovery["abort_events"]),
        "preserved_abort_events_sha256": recovery["abort_events_sha256"],
        "persistent_filesystem_mutations": 0,
        "scientific_commands_started": 0,
        "read_only_host_checks_executed": True,
    }


def execute_recovery(driver: Any) -> dict[str, Any]:
    with driver.exclusive_lock(POSTPROCESS_ROOT / "driver.lock"):
        with driver.exclusive_lock(POSTPROCESS_ROOT / "loss_cursor_recovery.lock"):
            recovery = verify_static_binding(driver)
            jobs, _ = exact_preflight(driver, recovery["state"])
            prerequisites = read_only_prerequisites(driver, jobs)
            roofprints = prerequisites["roofprint"]
            classify = classify_reconciliation_candidate(
                driver, jobs, roofprints, full_validation=True
            )
            loss = loss_reconciliation_candidate(driver, full_validation=True)
            if recovery["phase"] == "initial_aborted":
                assert_original_abort_ledger_unmodified(driver, recovery)
                archive = archive_aborted_attempt(
                    driver,
                    recovery,
                    classify["attempt"],
                    loss["attempt"],
                )
            else:
                archive = recovery["archive"]
                if not isinstance(archive, Mapping):
                    raise RecoveryError("resumed recovery lacks its sealed archive")
            try:
                if recovery["phase"] == "initial_aborted":
                    live_state = reset_live_abort_ledger(
                        driver, recovery, archive
                    )
                else:
                    live_state = driver.load_state()
                jobs, checked = exact_preflight(driver, live_state)
                assert_canonical_reset(driver, archive)
                classify_marker = reconcile_classification(
                    driver, classify, roofprints, recovery, archive
                )
                loss_marker = reconcile_loss(
                    driver, loss, recovery, archive
                )
                validate_existing_recovery_classifications(
                    driver, jobs, roofprints, recovery, archive
                )
                assert_canonical_reset(driver, archive)

                original_validator = driver.validate_classification
                original_marker_writer = driver.write_stage_marker
                driver.validate_classification = (
                    lambda job, attempt, roofprints_path:
                    fixed_validate_classification(
                        driver, job, attempt, roofprints_path
                    )
                )
                driver.write_stage_marker = recovered_stage_marker_writer(
                    driver, original_marker_writer, recovery, archive
                )
                try:
                    final = driver.execute_resume(jobs, checked)
                finally:
                    driver.validate_classification = original_validator
                    driver.write_stage_marker = original_marker_writer

                state = driver.load_state()
                require_equal(state.get("abort_events"), [],
                              "post-resume canonical abort ledger")
                require_equal(
                    state.get("learning_runs_started_by_postprocess"),
                    0,
                    "post-resume learning run count",
                )
                require_equal(
                    state.get("superseded_abort_archive"),
                    archive,
                    "post-resume sealed archive binding",
                )
                wave2 = state.get("wave2_launch") or {}
                require_equal(wave2.get("launch_performed"), False,
                              "post-resume Wave 2 launch")
                return {
                    "schema": RECOVERY_SCHEMA,
                    "state": state.get("state"),
                    "correction_head": EXPECTED_HEAD,
                    "recovery_helper_sha256": recovery["helper_sha256"],
                    "classification_reconciliation_marker":
                        driver.repo_relative(classify_marker),
                    "loss_reconciliation_marker":
                        driver.repo_relative(loss_marker),
                    "superseded_abort_archive": archive,
                    "canonical_abort_event_count": 0,
                    "learning_runs_started": 0,
                    "wave2_launch_performed": False,
                    "publication_state": final.get("state"),
                }
            except BaseException as exc:
                current = driver.load_state()
                pointer = current.get("superseded_abort_archive") or {}
                if (
                    isinstance(pointer, Mapping)
                    and pointer.get("archive_complete_sha256")
                    == archive["archive_complete_sha256"]
                ):
                    record_canonical_recovery_failure(
                        driver, recovery, archive, exc
                    )
                raise


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument(
        "mode",
        choices=("self-test", "dry-run", "audit-only", "resume"),
        help="self-test/dry-run/audit-only are read-only; resume performs recovery",
    )
    result.add_argument(
        "--full-validation",
        action="store_true",
        help="in dry-run, also hash and validate the large LAS/loss outputs",
    )
    return result


def main(argv: Sequence[str] | None = None) -> int:
    args = parser().parse_args(argv)
    driver = import_committed_driver()
    recovery = verify_static_binding(driver)
    if args.mode == "self-test":
        result = self_test(driver, recovery)
    elif args.mode in {"dry-run", "audit-only"}:
        with driver.exclusive_lock(POSTPROCESS_ROOT / "driver.lock"):
            recovery = verify_static_binding(driver)
            state_path = POSTPROCESS_ROOT / "driver_state.json"
            state_sha_before = sha256_file(state_path)
            jobs, _ = exact_preflight(driver, recovery["state"])
            result = recovery_plan(
                driver,
                jobs,
                recovery,
                full_validation=args.full_validation or args.mode == "audit-only",
            )
            result["mode"] = args.mode
            result["persistent_filesystem_mutations"] = 0
            result["scientific_commands_started"] = 0
            state_sha_after = sha256_file(state_path)
            require_equal(
                state_sha_after, state_sha_before,
                f"{args.mode} driver state byte preservation",
            )
            result["driver_state_sha256_before"] = state_sha_before
            result["driver_state_sha256_after"] = state_sha_after
            result["driver_state_bytes_unchanged"] = True
            if recovery["phase"] == "initial_aborted":
                assert_original_abort_ledger_unmodified(driver, recovery)
            else:
                require_equal(
                    driver.load_state(), recovery["state"],
                    f"{args.mode} interrupted recovery state preservation",
                )
    else:
        result = execute_recovery(driver)
    print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
