#!/usr/bin/env python3
"""Same-HEAD recovery controller for the P1W numeric aggregate round trip.

This is the second, aggregate-only recovery layer.  It preserves the first
receipt-wrapper helper byte-for-byte, seals the failed aggregate attempt and
its exact driver state before clearing the live abort ledger, reuses every
completed scientific stage, and permits only aggregate attempt 002 followed
by the binding/publication chain.

No training, extraction, classification, Roofer, finalization, score, or
val3dity command is allowed to restart.  The only scorer substitution is the
pinned run-local aggregate wrapper, executed inside the original p0-tools
image and bound into the aggregate stage marker.
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
import shutil
import subprocess
import sys
import tempfile
from typing import Any

sys.dont_write_bytecode = True


EXPECTED_HEAD = "1dfdcb5ed204d88001bd6aaba4c04bef5f222c4d"
EXPECTED_INITIAL_STATE_SHA256 = (
    "e3e6aee9522d9277bcc0e9a1f1b28c20243bba9c720edc2db62b4cc3fce3d400"
)
EXPECTED_INITIAL_ABORT_EVENTS_SHA256 = (
    "9846bb5aa339e6e1e8ab873c1f165175bc76395d5aa77283d2d48e4dff61c3af"
)
EXPECTED_INITIAL_ABORT_MESSAGE = (
    "numeric aggregate failed; see "
    "/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS/"
    "phases/p2-gsjso/runs/20260721_pilot_1wave/training/postprocess/"
    "attempts/_global/aggregate/attempt_001/aggregate.log"
)
EXPECTED_FIRST_HELPER_SHA256 = (
    "c912785408b5f794f822798d6d206234bb702442016fa34944624f63f39408e7"
)
EXPECTED_SCORING_SHA256 = (
    "7e40371708ab580c132b08e2ba411a3de530feddf35e908af74e4a086c102dcf"
)
EXPECTED_RECOVERY_LOG_SHA256 = (
    "2ed895767269aee46d9f9bc1dca0ab72eaae249b049c7daa546ec31c93bc8e9d"
)
EXPECTED_AGGREGATE_ATTEMPT_FILES = {
    "started.json":
        "bdc948820fd8144eb503102837ecbd4f769e4c2a85873992d5b018dc5c9356c0",
    "stdout.log":
        "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    "aggregate.log":
        "7d8410d0be53bb3de9e2d06f5673a39c0ed6579c357e725f0e9706f3a8a5421b",
    "output/pilot_1wave_loss_shares.csv":
        "01104b91c6faab26c40042bdf5bb510248b6dcd4a6736233087f593c8afe4a45",
    "output/pilot_1wave_manifest.json":
        "b02cbb70836df5b42781b1805d6cf12569d0ab05afbcf44ecc49afcafc1cabea",
    "output/pilot_1wave_scores.csv":
        "98f22176e4735beb4d2e7925755d6a7d2c89ce247d670e7fb02e0ee654e63f31",
    "output/pilot_1wave_seg_upperbound_gap.csv":
        "d689f945572aa9d87e203b4d3c015d63a87af5d5a1576712a9580d3f86db1b1d",
    "output/pilot_1wave_summary.csv":
        "1e6e3be0d5508547015f3163f0856b3918d93b28c2eefa48c0d786c069041301",
    "output/pilot_1wave_winner.csv":
        "ea29bdc093b52148b2c25da0318531d74095c6d361172132bed994087dc68acf",
}
EXPECTED_FINAL_ROWS = {
    "pilot_1wave_scores.csv": 390,
    "pilot_1wave_summary.csv": 234,
    "pilot_1wave_seg_upperbound_gap.csv": 60,
    "pilot_1wave_winner.csv": 4,
    "pilot_1wave_loss_shares.csv": 14_000,
}
EXPECTED_DRIFT_COUNTS = {
    "01_seed1001": 9,
    "01_seed1002": 6,
    "02_seed1001": 9,
    "02_seed1002": 8,
    "03_seed1001": 8,
    "03_seed1002": 11,
    "04a_seed1001": 6,
    "04a_seed1002": 8,
    "04b_seed1001": 8,
    "04b_seed1002": 5,
}
EXPECTED_DRIFT_FINGERPRINT_SHA256 = (
    "e88e894612eb8207eb8cd4293105da2c947300ecc66b188cafc387a6e52dc1ce"
)
ARCHIVE_NAME = "attempt4_1dfdcb5_aggregate_overlay_roundtrip"
RECOVERY_SCHEMA = "jointbuildgs.pilot_1wave.aggregate_recovery.v1"
ARCHIVE_LEDGER_SCHEMA = (
    "jointbuildgs.pilot_1wave.aggregate_failure_evidence.v1"
)
SUPERSESSION_SCHEMA = (
    "jointbuildgs.pilot_1wave.aggregate_abort_supersession.v1"
)
AGGREGATE_RECONCILIATION_SCHEMA = (
    "jointbuildgs.pilot_1wave.aggregate_overlay_reconciliation.v1"
)


class AggregateControllerError(RuntimeError):
    """A fail-closed second-recovery contract violation."""


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
        raise AggregateControllerError(
            f"{label} mismatch: {actual!r} != {expected!r}"
        )


def require_sha(path: Path, expected: str, label: str) -> None:
    if not path.is_file() or path.is_symlink():
        raise AggregateControllerError(f"{label} missing/non-regular: {path}")
    require_equal(sha256_file(path), expected, f"{label} SHA256")


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AggregateControllerError(f"cannot read JSON {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise AggregateControllerError(f"JSON root is not an object: {path}")
    return value


def find_repo(path: Path) -> Path:
    for candidate in (path, *path.parents):
        driver = (
            candidate
            / "phases/p2-gsjso/scripts/pilot_1wave_postprocess_driver.py"
        )
        if driver.is_file() and (candidate / ".git").exists():
            return candidate
    raise AggregateControllerError(f"repository not found above {path}")


HELPER_PATH = Path(__file__).resolve()
REPO = find_repo(HELPER_PATH.parent)
HELPER_SIDECAR = HELPER_PATH.with_suffix(".sha256")
WRAPPER_PATH = HELPER_PATH.parent / "p1w_same_head_aggregate_wrapper.py"
WRAPPER_SIDECAR = WRAPPER_PATH.with_suffix(".sha256")
FIRST_HELPER_PATH = HELPER_PATH.parent / "p1w_same_head_receipt_recovery.py"
FIRST_HELPER_SIDECAR = FIRST_HELPER_PATH.with_suffix(".sha256")
DRIVER_PATH = REPO / "phases/p2-gsjso/scripts/pilot_1wave_postprocess_driver.py"
POSTPROCESS_ROOT = (
    REPO
    / "phases/p2-gsjso/runs/20260721_pilot_1wave/training/postprocess"
)
STATE_PATH = POSTPROCESS_ROOT / "driver_state.json"
AGGREGATE_ATTEMPT_001 = (
    POSTPROCESS_ROOT / "attempts/_global/aggregate/attempt_001"
)
RECOVERY_LOG = POSTPROCESS_ROOT / "recovery_systemd.log"
PUBLICATION_ROOT = (
    REPO / "phases/p2-gsjso/runs/20260722_pilot_1wave_readout"
)


def verify_sidecar(path: Path, sidecar: Path, label: str) -> str:
    if not sidecar.is_file() or sidecar.is_symlink():
        raise AggregateControllerError(
            f"{label} sidecar missing/non-regular: {sidecar}"
        )
    fields = sidecar.read_text(encoding="ascii").strip().split()
    require_equal(len(fields), 2, f"{label} sidecar fields")
    require_equal(fields[1], path.name, f"{label} sidecar filename")
    actual = sha256_file(path)
    require_equal(fields[0], actual, f"{label} sidecar SHA")
    return actual


def import_module(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise AggregateControllerError(f"cannot import {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def verify_code_bindings() -> dict[str, str]:
    helper_sha = verify_sidecar(
        HELPER_PATH, HELPER_SIDECAR, "aggregate recovery helper"
    )
    wrapper_sha = verify_sidecar(
        WRAPPER_PATH, WRAPPER_SIDECAR, "aggregate wrapper"
    )
    require_sha(
        FIRST_HELPER_PATH,
        EXPECTED_FIRST_HELPER_SHA256,
        "first receipt recovery helper",
    )
    first_sidecar_fields = (
        FIRST_HELPER_SIDECAR.read_text(encoding="ascii").strip().split()
    )
    require_equal(
        first_sidecar_fields,
        [EXPECTED_FIRST_HELPER_SHA256, FIRST_HELPER_PATH.name],
        "first helper sidecar",
    )
    return {
        "helper_sha256": helper_sha,
        "wrapper_sha256": wrapper_sha,
        "first_helper_sha256": EXPECTED_FIRST_HELPER_SHA256,
    }


def verify_failed_aggregate_attempt() -> dict[str, Any]:
    if not AGGREGATE_ATTEMPT_001.is_dir() or AGGREGATE_ATTEMPT_001.is_symlink():
        raise AggregateControllerError(
            f"failed aggregate attempt missing: {AGGREGATE_ATTEMPT_001}"
        )
    actual_files = {
        str(path.relative_to(AGGREGATE_ATTEMPT_001))
        for path in AGGREGATE_ATTEMPT_001.rglob("*")
        if path.is_file() and not path.is_symlink()
    }
    require_equal(
        actual_files,
        set(EXPECTED_AGGREGATE_ATTEMPT_FILES),
        "failed aggregate attempt file set",
    )
    if (AGGREGATE_ATTEMPT_001 / "stage_complete.json").exists():
        raise AggregateControllerError(
            "failed aggregate attempt unexpectedly has a completion marker"
        )
    records: list[dict[str, Any]] = []
    for relative, expected in EXPECTED_AGGREGATE_ATTEMPT_FILES.items():
        path = AGGREGATE_ATTEMPT_001 / relative
        require_sha(path, expected, f"failed aggregate {relative}")
        records.append(
            {
                "path": str(path.relative_to(REPO)),
                "relative_to_attempt": relative,
                "size": path.stat().st_size,
                "sha256": expected,
            }
        )
    log = (AGGREGATE_ATTEMPT_001 / "aggregate.log").read_text(
        encoding="utf-8"
    )
    required_fragments = (
        "write_numeric_outputs",
        "_validate_candidate_group",
        "candidate row differs from score-marker output: "
        "01/1001/DEBY_LOD2_4906966",
    )
    for fragment in required_fragments:
        if fragment not in log:
            raise AggregateControllerError(
                f"failed aggregate log lacks: {fragment!r}"
            )
    require_sha(
        RECOVERY_LOG,
        EXPECTED_RECOVERY_LOG_SHA256,
        "first recovery systemd log",
    )
    return {
        "attempt": str(AGGREGATE_ATTEMPT_001.relative_to(REPO)),
        "files": records,
        "aggregate_log_sha256":
            EXPECTED_AGGREGATE_ATTEMPT_FILES["aggregate.log"],
        "recovery_log": {
            "path": str(RECOVERY_LOG.relative_to(REPO)),
            "size": RECOVERY_LOG.stat().st_size,
            "sha256": EXPECTED_RECOVERY_LOG_SHA256,
        },
    }


def archive_path(driver: Any) -> Path:
    return driver.POSTPROCESS_FAILED_ATTEMPTS_ROOT / ARCHIVE_NAME


def archive_record(driver: Any, archive: Path) -> dict[str, Any]:
    complete = archive / "archive_complete.json"
    receipt = archive / "supersession_receipt.json"
    ledger = archive / "evidence_sha256_ledger.json"
    state = archive / "driver_state.json"
    return {
        "name": ARCHIVE_NAME,
        "path": driver.repo_relative(archive),
        "driver_state_sha256": sha256_file(state),
        "evidence_ledger": driver.repo_relative(ledger),
        "evidence_ledger_sha256": sha256_file(ledger),
        "supersession_receipt": driver.repo_relative(receipt),
        "supersession_receipt_sha256": sha256_file(receipt),
        "archive_complete": driver.repo_relative(complete),
        "archive_complete_sha256": sha256_file(complete),
        "abort_event_count": 1,
        "abort_events_sha256": EXPECTED_INITIAL_ABORT_EVENTS_SHA256,
    }


def validate_archive(
    driver: Any,
    code: Mapping[str, str],
) -> dict[str, Any]:
    archive = archive_path(driver)
    if not archive.is_dir() or archive.is_symlink():
        raise AggregateControllerError(f"aggregate archive missing: {archive}")
    require_sha(
        archive / "driver_state.json",
        EXPECTED_INITIAL_STATE_SHA256,
        "archived aggregate driver state",
    )
    archived_state = load_json(archive / "driver_state.json")
    require_equal(archived_state.get("state"), "aborted", "archived state")
    require_equal(
        sha256_bytes(canonical_json(archived_state.get("abort_events"))),
        EXPECTED_INITIAL_ABORT_EVENTS_SHA256,
        "archived abort ledger",
    )
    for relative, expected in EXPECTED_AGGREGATE_ATTEMPT_FILES.items():
        require_sha(
            archive / "aggregate_attempt_001" / relative,
            expected,
            f"archived aggregate {relative}",
        )
    require_sha(
        archive / "recovery_systemd.log",
        EXPECTED_RECOVERY_LOG_SHA256,
        "archived first recovery log",
    )
    audit = load_json(archive / "aggregate_roundtrip_audit.json")
    require_equal(
        (audit.get("audit") or {}).get("affected_rows_by_run"),
        EXPECTED_DRIFT_COUNTS,
        "archived aggregate drift counts",
    )
    require_equal(
        (audit.get("audit") or {}).get("changed_fields"),
        ["als_gap_closed_fraction"],
        "archived aggregate drift fields",
    )
    require_equal(
        (audit.get("audit") or {}).get(
            "affected_building_delta_fingerprint_sha256"
        ),
        EXPECTED_DRIFT_FINGERPRINT_SHA256,
        "archived aggregate drift fingerprint",
    )
    if float((audit.get("audit") or {}).get("max_abs_drift", 1.0)) > 3e-8:
        raise AggregateControllerError("archived aggregate drift exceeds 3e-8")
    ledger = load_json(archive / "evidence_sha256_ledger.json")
    require_equal(
        ledger.get("schema"), ARCHIVE_LEDGER_SCHEMA, "archive ledger schema"
    )
    receipt = load_json(archive / "supersession_receipt.json")
    require_equal(
        receipt.get("schema"), SUPERSESSION_SCHEMA, "archive receipt schema"
    )
    require_equal(receipt.get("state"), "archived_before_live_reset",
                  "archive receipt state")
    require_equal(
        receipt.get("recovery_helper_sha256"),
        code["helper_sha256"],
        "archive helper SHA",
    )
    require_equal(
        receipt.get("aggregate_wrapper_sha256"),
        code["wrapper_sha256"],
        "archive wrapper SHA",
    )
    complete = load_json(archive / "archive_complete.json")
    require_equal(
        complete.get("schema"),
        "jointbuildgs.pilot_1wave.aggregate_archive_complete.v1",
        "archive completion schema",
    )
    require_equal(complete.get("state"), "complete", "archive completion state")
    require_equal(
        complete.get("driver_state_sha256"),
        EXPECTED_INITIAL_STATE_SHA256,
        "archive completion state SHA",
    )
    require_equal(
        complete.get("evidence_ledger_sha256"),
        sha256_file(archive / "evidence_sha256_ledger.json"),
        "archive completion ledger SHA",
    )
    require_equal(
        complete.get("supersession_receipt_sha256"),
        sha256_file(archive / "supersession_receipt.json"),
        "archive completion receipt SHA",
    )
    return archive_record(driver, archive)


def verify_live_state(
    driver: Any,
    first: Any,
    code: Mapping[str, str],
) -> dict[str, Any]:
    require_equal(
        driver.query_git_head(), EXPECTED_HEAD, "current git HEAD"
    )
    tracked = subprocess.run(
        ["git", "status", "--porcelain=v1", "--untracked-files=no"],
        cwd=REPO,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    require_equal(tracked.returncode, 0, "tracked status exit")
    require_equal(tracked.stdout.strip(), "", "tracked worktree status")
    state = driver.load_state()
    require_equal(state.get("schema"), driver.DRIVER_SCHEMA, "driver schema")
    require_equal(
        state.get("correction_head"), EXPECTED_HEAD, "driver correction HEAD"
    )
    require_equal(
        state.get("learning_runs_started_by_postprocess"),
        0,
        "postprocess learning count",
    )
    sources = (state.get("preflight") or {}).get("committed_runtime_sources")
    require_equal(
        sources,
        first.EXPECTED_RUNTIME_SOURCES,
        "driver committed runtime source map",
    )
    require_equal(
        sha256_file(
            REPO / "phases/p2-gsjso/scripts/pilot_1wave_scoring.py"
        ),
        EXPECTED_SCORING_SHA256,
        "committed scoring SHA",
    )
    old_archive = first.validate_sealed_archive(
        driver, EXPECTED_FIRST_HELPER_SHA256
    )
    require_equal(
        state.get("superseded_abort_archive"),
        old_archive,
        "first recovery archive pointer",
    )

    current_sha = sha256_file(STATE_PATH)
    second_archive: dict[str, Any] | None = None
    if current_sha == EXPECTED_INITIAL_STATE_SHA256:
        require_equal(state.get("state"), "aborted", "initial aggregate state")
        aborts = state.get("abort_events")
        require_equal(len(aborts or []), 1, "initial aggregate abort count")
        require_equal(
            sha256_bytes(canonical_json(aborts)),
            EXPECTED_INITIAL_ABORT_EVENTS_SHA256,
            "initial aggregate abort SHA",
        )
        event = aborts[0]
        require_equal(event.get("type"), "DriverError", "aggregate abort type")
        require_equal(
            event.get("message"),
            EXPECTED_INITIAL_ABORT_MESSAGE,
            "aggregate abort message",
        )
        phase = "initial_aborted"
        if archive_path(driver).exists():
            second_archive = validate_archive(driver, code)
            phase = "initial_aborted_archive_sealed"
    elif state.get("state") in {"aggregate_recovery_ready", "running"}:
        second_archive = validate_archive(driver, code)
        require_equal(
            state.get("aggregate_recovery_archive"),
            second_archive,
            "live aggregate archive pointer",
        )
        require_equal(
            state.get("abort_events"), [], "aggregate recovery abort ledger"
        )
        controller = state.get("recovery_controller") or {}
        require_equal(
            controller.get("helper_sha256"),
            code["helper_sha256"],
            "live aggregate helper SHA",
        )
        require_equal(
            controller.get("wrapper_sha256"),
            code["wrapper_sha256"],
            "live aggregate wrapper SHA",
        )
        phase = f"resume_{state.get('state')}"
    else:
        raise AggregateControllerError(
            f"unsupported aggregate recovery state/SHA: "
            f"{state.get('state')!r}/{current_sha}"
        )
    return {
        "state": state,
        "state_sha256": current_sha,
        "phase": phase,
        "first_archive": old_archive,
        "second_archive": second_archive,
    }


def score_paths(driver: Any, jobs: Sequence[Any]) -> list[Path]:
    return [driver.score_attempt(job) / "scores.csv" for job in jobs]


def validate_cross_binding_read_only(
    driver: Any,
    jobs: Sequence[Any],
    roofprints: Path,
) -> dict[str, Any]:
    """Validate the existing cross-run receipt without rewriting its bytes."""

    path = POSTPROCESS_ROOT / "roofprint_binding_receipt.json"
    payload = load_json(path)
    require_equal(
        payload.get("schema"),
        "jointbuildgs.pilot_1wave.cross_run_roofprint_binding.v1",
        "cross-run roofprint receipt schema",
    )
    require_equal(payload.get("state"), "complete", "cross-run receipt state")
    require_equal(payload.get("run_count"), 10, "cross-run receipt run count")
    require_equal(
        payload.get("roofprint_path"),
        driver.repo_relative(roofprints.resolve()),
        "cross-run roofprint path",
    )
    require_equal(
        payload.get("roofprint_sha256"),
        sha256_file(roofprints),
        "cross-run roofprint SHA",
    )
    require_equal(
        payload.get("ordered_geometry_sha256"),
        driver.roofprint_ordered_geometry_sha256(roofprints),
        "cross-run roofprint geometry SHA",
    )
    require_equal(
        payload.get("ordered_ids_sha256"),
        driver.ORDERED_IDS_SHA256,
        "cross-run ordered IDs SHA",
    )
    require_equal(
        payload.get("unique_path_count"), 1, "cross-run unique path count"
    )
    require_equal(
        payload.get("unique_sha256_count"), 1, "cross-run unique SHA count"
    )
    records = payload.get("receipts")
    if not isinstance(records, list):
        raise AggregateControllerError("cross-run receipt ledger is not a list")
    require_equal(len(records), 10, "cross-run receipt ledger count")
    for job, record in zip(jobs, records, strict=True):
        if not isinstance(record, Mapping):
            raise AggregateControllerError(
                f"cross-run receipt record is not an object: {job.job_id}"
            )
        classification = (
            driver.classify_attempt(job) / "classification_receipt.json"
        )
        require_equal(
            record.get("job_id"), job.job_id, f"{job.job_id} cross-run job"
        )
        require_equal(
            record.get("classification_receipt"),
            driver.repo_relative(classification),
            f"{job.job_id} cross-run classification path",
        )
        require_equal(
            record.get("classification_receipt_sha256"),
            sha256_file(classification),
            f"{job.job_id} cross-run classification SHA",
        )
        require_equal(
            record.get("roofprint_path"),
            driver.repo_relative(roofprints.resolve()),
            f"{job.job_id} cross-run roofprint path",
        )
        require_equal(
            record.get("roofprint_sha256"),
            sha256_file(roofprints),
            f"{job.job_id} cross-run roofprint SHA",
        )
    return payload


def validate_reused_stages(
    driver: Any,
    first: Any,
    jobs: Sequence[Any],
    *,
    deep_classification: bool,
) -> dict[str, Any]:
    roofprint_attempt = driver.completed_attempt(
        driver.global_stage_root("roofprint"), "roofprint", "global"
    )
    if roofprint_attempt is None:
        raise AggregateControllerError("global roofprint marker is incomplete")
    roofprints = roofprint_attempt / "locked_roofprints.geojson"
    marker_ledger: dict[str, str] = {
        "roofprint": sha256_file(roofprint_attempt / "stage_complete.json")
    }
    counts = {
        "extract": 0,
        "classify": 0,
        "prepare": 0,
        "finalize": 0,
        "score": 0,
    }
    for job in jobs:
        for stage in counts:
            attempt = driver.completed_attempt(
                driver.stage_root(job, stage), stage, job.job_id
            )
            if attempt is None:
                raise AggregateControllerError(
                    f"reused stage incomplete: {job.job_id}/{stage}"
                )
            marker_ledger[f"{job.job_id}/{stage}"] = sha256_file(
                attempt / "stage_complete.json"
            )
            counts[stage] += 1
        if deep_classification:
            first.fixed_validate_classification(
                driver, job, driver.classify_attempt(job), roofprints
            )
        driver.validate_score(job, driver.score_attempt(job))
        score_marker = load_json(
            driver.score_attempt(job) / "score_invocation.json"
        )
        require_equal(
            score_marker.get("score_invocation_count"),
            1,
            f"{job.job_id} score invocation count",
        )
        require_equal(
            score_marker.get("val3dity_invocation_count"),
            1,
            f"{job.job_id} val3dity invocation count",
        )
        runtime = driver.roofer_attempt(job)
        roofer = load_json(runtime / "roofer_invocation.json")
        require_equal(
            roofer.get("roofer_invocation_count"),
            1,
            f"{job.job_id} Roofer invocation count",
        )
    require_equal(counts, {stage: 10 for stage in counts}, "reused stage counts")
    validate_cross_binding_read_only(driver, jobs, roofprints)
    loss = driver.completed_attempt(
        driver.global_stage_root("loss_cursor"), "loss_cursor", "global"
    )
    if loss is None:
        raise AggregateControllerError("loss cursor marker is incomplete")
    validated_loss = driver.validate_loss_aggregate_outputs(loss)
    marker_ledger["loss_cursor"] = sha256_file(loss / "stage_complete.json")
    return {
        "roofprints": roofprints,
        "stage_counts": counts,
        "marker_sha256": marker_ledger,
        "loss_dir": loss,
        "loss_sha256": validated_loss["output_sha256"],
    }


def wrapper_audit_command(driver: Any, jobs: Sequence[Any]) -> list[str]:
    command = driver.p0_command(
        [
            "python3",
            driver.container_path(WRAPPER_PATH),
            "audit-only",
        ]
    )
    for path in score_paths(driver, jobs):
        command.extend(["--run-score", driver.container_path(path)])
    return command


def run_wrapper_audit(driver: Any, jobs: Sequence[Any]) -> dict[str, Any]:
    before = sha256_file(STATE_PATH)
    process = subprocess.run(
        wrapper_audit_command(driver, jobs),
        cwd=REPO,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if process.returncode != 0:
        raise AggregateControllerError(
            f"aggregate wrapper audit failed exit={process.returncode}: "
            f"{process.stderr.strip()}"
        )
    try:
        result = json.loads(process.stdout)
    except json.JSONDecodeError as exc:
        raise AggregateControllerError(
            f"aggregate wrapper audit returned non-JSON: {process.stdout!r}"
        ) from exc
    if not isinstance(result, dict):
        raise AggregateControllerError("aggregate wrapper audit is not an object")
    audit = result.get("audit") or {}
    require_equal(result.get("state"), "pass", "wrapper audit state")
    require_equal(
        (result.get("controller") or {}).get("sha256"),
        sha256_file(HELPER_PATH),
        "wrapper audit controller SHA",
    )
    require_equal(
        audit.get("candidate_rows"), 300, "wrapper audit candidate rows"
    )
    require_equal(
        audit.get("unchanged_rows"), 222, "wrapper audit unchanged rows"
    )
    require_equal(
        audit.get("affected_rows"), 78, "wrapper audit affected rows"
    )
    require_equal(
        audit.get("affected_rows_by_run"),
        EXPECTED_DRIFT_COUNTS,
        "wrapper audit per-run drift",
    )
    require_equal(
        audit.get("changed_fields"),
        ["als_gap_closed_fraction"],
        "wrapper audit changed fields",
    )
    require_equal(
        audit.get("affected_building_delta_fingerprint_sha256"),
        EXPECTED_DRIFT_FINGERPRINT_SHA256,
        "wrapper audit drift fingerprint",
    )
    if float(audit.get("max_abs_drift", 1.0)) > 3e-8:
        raise AggregateControllerError("wrapper audit drift exceeds 3e-8")
    require_equal(
        sha256_file(STATE_PATH), before, "wrapper audit driver-state bytes"
    )
    return result


def verify_no_completed_legacy_aggregate(driver: Any) -> None:
    complete = driver.completed_attempt(
        driver.global_stage_root("aggregate"), "aggregate", "global"
    )
    if complete is not None:
        validate_recovered_aggregate(driver, complete)
        return
    latest = driver.latest_attempt(driver.global_stage_root("aggregate"))
    require_equal(
        latest, AGGREGATE_ATTEMPT_001, "latest incomplete aggregate attempt"
    )
    verify_failed_aggregate_attempt()


def csv_rows(path: Path) -> int:
    import csv

    with path.open(newline="", encoding="utf-8") as stream:
        return len(list(csv.DictReader(stream)))


def validate_recovered_aggregate(driver: Any, attempt: Path) -> dict[str, Any]:
    require_equal(attempt.name, "attempt_002", "recovered aggregate attempt")
    if not driver.valid_stage_attempt(attempt, "aggregate", "global"):
        raise AggregateControllerError("recovered aggregate marker is invalid")
    output = attempt / "output"
    receipt_path = output / "aggregate_overlay_reconciliation.json"
    receipt = load_json(receipt_path)
    require_equal(
        receipt.get("schema"),
        AGGREGATE_RECONCILIATION_SCHEMA,
        "aggregate reconciliation schema",
    )
    require_equal(receipt.get("state"), "pass", "aggregate reconciliation state")
    require_equal(
        (receipt.get("audit") or {}).get("affected_rows_by_run"),
        EXPECTED_DRIFT_COUNTS,
        "aggregate reconciliation drift counts",
    )
    require_equal(
        (receipt.get("audit") or {}).get(
            "affected_building_delta_fingerprint_sha256"
        ),
        EXPECTED_DRIFT_FINGERPRINT_SHA256,
        "aggregate reconciliation drift fingerprint",
    )
    require_equal(
        receipt.get("candidate_scientific_scores_recomputed"),
        False,
        "aggregate candidate score recomputation",
    )
    require_equal(
        receipt.get("aggregate_outputs_computed"),
        True,
        "aggregate output computation",
    )
    require_equal(
        (receipt.get("controller") or {}).get("sha256"),
        sha256_file(HELPER_PATH),
        "aggregate reconciliation controller SHA",
    )
    for name, expected in EXPECTED_FINAL_ROWS.items():
        require_equal(
            csv_rows(output / name), expected, f"recovered aggregate {name} rows"
        )
    scoring_manifest = load_json(output / "pilot_1wave_manifest.json")
    provenance = scoring_manifest.get("aggregate_recovery")
    if not isinstance(provenance, Mapping):
        raise AggregateControllerError(
            "published scoring manifest lacks aggregate recovery provenance"
        )
    require_equal(
        provenance.get("wrapper", {}).get("sha256"),
        sha256_file(WRAPPER_PATH),
        "scoring manifest wrapper SHA",
    )
    require_equal(
        provenance.get("controller", {}).get("sha256"),
        sha256_file(HELPER_PATH),
        "scoring manifest controller SHA",
    )
    require_equal(
        provenance.get("candidate_scientific_scores_recomputed"),
        False,
        "scoring manifest candidate score recomputation",
    )
    require_equal(
        provenance.get("aggregate_outputs_computed"),
        True,
        "scoring manifest aggregate output computation",
    )
    require_equal(
        provenance.get("affected_building_delta_fingerprint_sha256"),
        EXPECTED_DRIFT_FINGERPRINT_SHA256,
        "scoring manifest drift fingerprint",
    )
    run_inputs = provenance.get("run_score_inputs")
    if not isinstance(run_inputs, list):
        raise AggregateControllerError(
            "scoring manifest run-score input ledger is missing"
        )
    require_equal(len(run_inputs), 10, "scoring manifest run-score inputs")
    require_equal(
        len({str(record.get("sha256")) for record in run_inputs}),
        10,
        "scoring manifest unique run-score SHAs",
    )
    manifest_receipt = (scoring_manifest.get("outputs") or {}).get(
        "aggregate_overlay_reconciliation.json"
    )
    if not isinstance(manifest_receipt, Mapping):
        raise AggregateControllerError(
            "scoring manifest outputs lack aggregate reconciliation"
        )
    require_equal(
        manifest_receipt.get("sha256"),
        sha256_file(receipt_path),
        "scoring manifest aggregate reconciliation SHA",
    )
    marker = load_json(attempt / "stage_complete.json")
    require_equal(
        marker.get("aggregate_recovery_helper_sha256"),
        sha256_file(HELPER_PATH),
        "aggregate marker helper SHA",
    )
    require_equal(
        marker.get("aggregate_wrapper_sha256"),
        sha256_file(WRAPPER_PATH),
        "aggregate marker wrapper SHA",
    )
    output_paths = {
        record.get("path")
        for record in marker.get("outputs", [])
        if isinstance(record, Mapping)
    }
    for path in (
        receipt_path,
        attempt / "aggregate_controller_reconciliation.json",
        HELPER_PATH,
        HELPER_SIDECAR,
        WRAPPER_PATH,
        WRAPPER_SIDECAR,
        FIRST_HELPER_PATH,
        FIRST_HELPER_SIDECAR,
    ):
        if driver.repo_relative(path) not in output_paths:
            raise AggregateControllerError(
                f"aggregate marker lacks provenance output: {path}"
            )
    return {
        "attempt": driver.repo_relative(attempt),
        "output": output,
        "receipt": receipt_path,
        "receipt_sha256": sha256_file(receipt_path),
    }


def atomic_archive(
    driver: Any,
    code: Mapping[str, str],
    audit: Mapping[str, Any],
    first_archive: Mapping[str, Any],
) -> dict[str, Any]:
    target = archive_path(driver)
    if target.exists():
        return validate_archive(driver, code)
    require_sha(
        STATE_PATH, EXPECTED_INITIAL_STATE_SHA256, "live pre-archive state"
    )
    verify_failed_aggregate_attempt()
    root = driver.POSTPROCESS_FAILED_ATTEMPTS_ROOT
    root.mkdir(parents=True, exist_ok=True)
    staging = Path(
        tempfile.mkdtemp(
            prefix=f".{ARCHIVE_NAME}.staging.", dir=root.parent
        )
    )
    try:
        driver.atomic_bytes(
            staging / "driver_state.json", STATE_PATH.read_bytes()
        )
        copied: list[dict[str, Any]] = []
        for relative, expected in EXPECTED_AGGREGATE_ATTEMPT_FILES.items():
            source = AGGREGATE_ATTEMPT_001 / relative
            destination = staging / "aggregate_attempt_001" / relative
            driver.atomic_bytes(destination, source.read_bytes())
            require_sha(destination, expected, f"staged aggregate {relative}")
            copied.append(
                {
                    "source": driver.repo_relative(source),
                    "archived_path": driver.repo_relative(
                        target / "aggregate_attempt_001" / relative
                    ),
                    "size": destination.stat().st_size,
                    "sha256": expected,
                }
            )
        driver.atomic_bytes(
            staging / "recovery_systemd.log", RECOVERY_LOG.read_bytes()
        )
        driver.atomic_json(staging / "aggregate_roundtrip_audit.json", audit)
        copied.extend(
            [
                {
                    "source": driver.repo_relative(STATE_PATH),
                    "archived_path": driver.repo_relative(
                        target / "driver_state.json"
                    ),
                    "size": (staging / "driver_state.json").stat().st_size,
                    "sha256": EXPECTED_INITIAL_STATE_SHA256,
                },
                {
                    "source": driver.repo_relative(RECOVERY_LOG),
                    "archived_path": driver.repo_relative(
                        target / "recovery_systemd.log"
                    ),
                    "size": (staging / "recovery_systemd.log").stat().st_size,
                    "sha256": EXPECTED_RECOVERY_LOG_SHA256,
                },
            ]
        )
        ledger = {
            "schema": ARCHIVE_LEDGER_SCHEMA,
            "state": "complete",
            "reason": "aggregate_dense_overlay_csv_roundtrip",
            "correction_head": EXPECTED_HEAD,
            "files": copied,
            "aggregate_roundtrip_audit": {
                "path": driver.repo_relative(
                    target / "aggregate_roundtrip_audit.json"
                ),
                "sha256": sha256_file(
                    staging / "aggregate_roundtrip_audit.json"
                ),
            },
        }
        driver.atomic_json(staging / "evidence_sha256_ledger.json", ledger)
        receipt = {
            "schema": SUPERSESSION_SCHEMA,
            "state": "archived_before_live_reset",
            "archive_name": ARCHIVE_NAME,
            "archive_path": driver.repo_relative(target),
            "reason": "committed_aggregate_double_overlay_roundtrip",
            "correction_head": EXPECTED_HEAD,
            "driver_state_sha256": EXPECTED_INITIAL_STATE_SHA256,
            "abort_events_sha256": EXPECTED_INITIAL_ABORT_EVENTS_SHA256,
            "failed_attempt": driver.repo_relative(AGGREGATE_ATTEMPT_001),
            "failed_attempt_log_sha256":
                EXPECTED_AGGREGATE_ATTEMPT_FILES["aggregate.log"],
            "recovery_helper": driver.repo_relative(HELPER_PATH),
            "recovery_helper_sha256": code["helper_sha256"],
            "aggregate_wrapper": driver.repo_relative(WRAPPER_PATH),
            "aggregate_wrapper_sha256": code["wrapper_sha256"],
            "first_recovery_helper_sha256": code["first_helper_sha256"],
            "first_superseded_abort_archive": dict(first_archive),
            "scientific_outputs_changed": False,
            "training_started": 0,
            "roofer_started": 0,
            "score_started": 0,
        }
        driver.atomic_json(staging / "supersession_receipt.json", receipt)
        complete = {
            "schema":
                "jointbuildgs.pilot_1wave.aggregate_archive_complete.v1",
            "state": "complete",
            "archive_name": ARCHIVE_NAME,
            "driver_state_sha256": EXPECTED_INITIAL_STATE_SHA256,
            "evidence_ledger_sha256": sha256_file(
                staging / "evidence_sha256_ledger.json"
            ),
            "supersession_receipt_sha256": sha256_file(
                staging / "supersession_receipt.json"
            ),
        }
        driver.atomic_json(staging / "archive_complete.json", complete)
        first = getattr(os, "sync", None)
        if first is not None:
            first()
        os.replace(staging, target)
        first_helper = import_module(
            "p1w_first_helper_for_archive_fsync", FIRST_HELPER_PATH
        )
        first_helper.fsync_directory(target.parent)
    except BaseException:
        if staging.exists():
            shutil.rmtree(staging)
        raise
    return validate_archive(driver, code)


def reset_live_state(
    driver: Any,
    code: Mapping[str, str],
    archive: Mapping[str, Any],
) -> dict[str, Any]:
    require_sha(
        REPO / str(archive["archive_complete"]),
        str(archive["archive_complete_sha256"]),
        "aggregate archive completion",
    )
    state = driver.load_state()
    require_sha(STATE_PATH, EXPECTED_INITIAL_STATE_SHA256, "pre-reset state")
    state["state"] = "aggregate_recovery_ready"
    state["updated_utc"] = driver.now()
    state["abort_events"] = []
    state.pop("last_error", None)
    state["aggregate_recovery_archive"] = dict(archive)
    state["recovery_controller"] = {
        "schema": RECOVERY_SCHEMA,
        "state": "ready",
        "reason": "aggregate_dense_overlay_csv_roundtrip",
        "correction_head": EXPECTED_HEAD,
        "helper": driver.repo_relative(HELPER_PATH),
        "helper_sha256": code["helper_sha256"],
        "wrapper": driver.repo_relative(WRAPPER_PATH),
        "wrapper_sha256": code["wrapper_sha256"],
        "patch_scope": "aggregate_attach_dense_controls_only",
        "reused_scientific_stages": True,
        "training_started": 0,
        "roofer_started": 0,
        "score_started": 0,
        "learning_runs_started": 0,
    }
    driver.save_state(state)
    reset = driver.load_state()
    require_equal(reset.get("abort_events"), [], "reset abort ledger")
    require_equal(
        reset.get("aggregate_recovery_archive"),
        archive,
        "reset aggregate archive",
    )
    return reset


def recovered_stage_marker_writer(
    driver: Any,
    original_writer: Any,
    code: Mapping[str, str],
    archive: Mapping[str, Any],
) -> Any:
    def writer(
        attempt: Path,
        stage: str,
        job_id: str,
        outputs: Any,
        extra: Mapping[str, Any] | None = None,
    ) -> Path:
        output_tuple = tuple(outputs)
        merged = dict(extra or {})
        if stage == "aggregate":
            receipt = (
                attempt / "output/aggregate_overlay_reconciliation.json"
            )
            payload = load_json(receipt)
            require_equal(
                payload.get("schema"),
                AGGREGATE_RECONCILIATION_SCHEMA,
                "aggregate marker reconciliation schema",
            )
            controller_receipt = (
                attempt / "aggregate_controller_reconciliation.json"
            )
            driver.atomic_json(
                controller_receipt,
                {
                    "schema": RECOVERY_SCHEMA,
                    "state": "aggregate_complete",
                    "correction_head": EXPECTED_HEAD,
                    "recovery_helper": driver.repo_relative(HELPER_PATH),
                    "recovery_helper_sha256": code["helper_sha256"],
                    "aggregate_wrapper": driver.repo_relative(WRAPPER_PATH),
                    "aggregate_wrapper_sha256": code["wrapper_sha256"],
                    "first_recovery_helper_sha256":
                        code["first_helper_sha256"],
                    "superseded_aggregate_archive": dict(archive),
                    "failed_attempt_preserved":
                        driver.repo_relative(AGGREGATE_ATTEMPT_001),
                    "replacement_attempt": driver.repo_relative(attempt),
                    "candidate_rows_preserved": 300,
                    "summary_rows": 234,
                    "training_started": 0,
                    "roofer_started": 0,
                    "score_started": 0,
                },
            )
            output_tuple = (
                *output_tuple,
                receipt,
                controller_receipt,
                HELPER_PATH,
                HELPER_SIDECAR,
                WRAPPER_PATH,
                WRAPPER_SIDECAR,
                FIRST_HELPER_PATH,
                FIRST_HELPER_SIDECAR,
            )
            merged.update(
                {
                    "aggregate_recovery_helper_sha256":
                        code["helper_sha256"],
                    "aggregate_wrapper_sha256": code["wrapper_sha256"],
                    "first_recovery_helper_sha256":
                        code["first_helper_sha256"],
                    "aggregate_failure_archive_sha256":
                        archive["archive_complete_sha256"],
                    "candidate_rows_preserved": 300,
                    "summary_rows": 234,
                }
            )
        return original_writer(
            attempt, stage, job_id, output_tuple, merged
        )

    return writer


def guarded_next_attempt(driver: Any, original: Any) -> Any:
    allowed = {
        driver.global_stage_root("aggregate").resolve(),
        driver.global_stage_root("binding").resolve(),
    }

    def next_attempt(root: Path) -> Path:
        if root.resolve() not in allowed:
            raise AggregateControllerError(
                f"scientific stage restart forbidden by aggregate recovery: {root}"
            )
        return original(root)

    return next_attempt


def recovered_numeric_runner(driver: Any, original: Any) -> Any:
    def runner(jobs: Sequence[Any], loss_dir: Path) -> Path:
        prior = driver.SCORING
        driver.SCORING = WRAPPER_PATH
        try:
            output = original(jobs, loss_dir)
        finally:
            driver.SCORING = prior
        attempt = driver.completed_attempt(
            driver.global_stage_root("aggregate"), "aggregate", "global"
        )
        if attempt is None:
            raise AggregateControllerError(
                "aggregate runner returned without a completion marker"
            )
        validated = validate_recovered_aggregate(driver, attempt)
        require_equal(
            validated["output"].resolve(),
            output.resolve(),
            "aggregate runner output path",
        )
        return output

    return runner


def forbid_retained_container(*args: Any, **kwargs: Any) -> None:
    raise AggregateControllerError(
        "Roofer/score retained-container restart is forbidden in aggregate recovery"
    )


def record_failure(
    driver: Any,
    code: Mapping[str, str],
    archive: Mapping[str, Any],
    exc: BaseException,
) -> None:
    state = driver.load_state()
    aborts = state.get("abort_events")
    if not isinstance(aborts, list):
        aborts = []
    message = str(exc)
    metadata = {
        "phase": "same_head_aggregate_recovery",
        "recovery_helper_sha256": code["helper_sha256"],
        "aggregate_wrapper_sha256": code["wrapper_sha256"],
        "aggregate_failure_archive_sha256":
            archive["archive_complete_sha256"],
    }
    if aborts and aborts[-1].get("message") == message:
        # The committed driver records its own concise event first.  Enrich
        # that same event rather than suppressing recovery provenance merely
        # because the message is already present.
        aborts[-1].update(metadata)
    else:
        aborts.append(
            {
                "at": driver.now(),
                "type": type(exc).__name__,
                "message": message,
                **metadata,
            }
        )
    state.update(
        {
            "state": "aborted",
            "updated_utc": driver.now(),
            "abort_events": aborts,
            "last_error": aborts[-1],
        }
    )
    driver.save_state(state)


def postcheck_recovery(
    driver: Any,
    first: Any,
    code: Mapping[str, str],
    archive: Mapping[str, Any],
    jobs: Sequence[Any],
    reused: Mapping[str, Any],
    failed: Mapping[str, Any],
    final: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate the completed chain before reporting success."""

    state = driver.load_state()
    require_equal(state.get("state"), "complete", "final driver state")
    require_equal(state.get("abort_events"), [], "final abort ledger")
    require_equal(
        state.get("learning_runs_started_by_postprocess"),
        0,
        "final learning count",
    )
    require_equal(
        (state.get("wave2_launch") or {}).get("launch_performed"),
        False,
        "final Wave 2 launch",
    )
    final_reused = validate_reused_stages(
        driver, first, jobs, deep_classification=True
    )
    require_equal(
        final_reused["marker_sha256"],
        reused["marker_sha256"],
        "final scientific marker ledger",
    )
    attempt = driver.completed_attempt(
        driver.global_stage_root("aggregate"), "aggregate", "global"
    )
    if attempt is None:
        raise AggregateControllerError("final aggregate is incomplete")
    aggregate = validate_recovered_aggregate(driver, attempt)
    binding = driver.completed_attempt(
        driver.global_stage_root("binding"), "binding", "global"
    )
    if binding is None:
        raise AggregateControllerError("final binding is incomplete")
    binding_receipt = driver.validate_binding_batch_outputs(
        binding / "output"
    )
    require_equal(
        csv_rows(binding / "output/binding_audit.csv"),
        300,
        "binding audit rows",
    )
    require_equal(
        csv_rows(binding / "output/binding_audit_spatial_matrix.csv"),
        9000,
        "binding matrix rows",
    )
    verify_failed_aggregate_attempt()
    validate_archive(driver, code)
    manifest = PUBLICATION_ROOT / driver.FINAL_MANIFEST_NAME
    if not manifest.is_file():
        raise AggregateControllerError(
            "publication manifest was not written last"
        )
    published_scoring_manifest = (
        PUBLICATION_ROOT / "pilot_1wave_scoring_manifest.json"
    )
    require_equal(
        sha256_file(published_scoring_manifest),
        sha256_file(aggregate["output"] / "pilot_1wave_manifest.json"),
        "published scoring manifest aggregate provenance",
    )
    published_scoring = load_json(published_scoring_manifest)
    require_equal(
        (
            published_scoring.get("aggregate_recovery") or {}
        ).get("wrapper", {}).get("sha256"),
        code["wrapper_sha256"],
        "published scoring manifest wrapper SHA",
    )
    require_equal(
        (
            published_scoring.get("aggregate_recovery") or {}
        ).get("controller", {}).get("sha256"),
        code["helper_sha256"],
        "published scoring manifest controller SHA",
    )
    return {
        "schema": RECOVERY_SCHEMA,
        "state": "complete",
        "correction_head": EXPECTED_HEAD,
        "recovery_helper_sha256": code["helper_sha256"],
        "aggregate_wrapper_sha256": code["wrapper_sha256"],
        "aggregate_failure": dict(failed),
        "aggregate_archive": dict(archive),
        "aggregate": {
            "attempt": aggregate["attempt"],
            "receipt_sha256": aggregate["receipt_sha256"],
            "summary_rows": 234,
        },
        "binding_hard_gate_passed": binding_receipt["hard_gate_passed"],
        "learning_runs_started": 0,
        "roofer_reruns_started": 0,
        "score_reruns_started": 0,
        "wave2_launch_performed": False,
        "publication_state": final.get("state"),
        "publication_manifest": driver.repo_relative(manifest),
        "publication_manifest_sha256": sha256_file(manifest),
    }


def execute_recovery(
    driver: Any,
    first: Any,
    code: Mapping[str, str],
) -> dict[str, Any]:
    with driver.exclusive_lock(POSTPROCESS_ROOT / "driver.lock"):
        with driver.exclusive_lock(
            POSTPROCESS_ROOT / "aggregate_recovery.lock"
        ):
            live = verify_live_state(driver, first, code)
            failed = verify_failed_aggregate_attempt()
            jobs, checked = driver.preflight(EXPECTED_HEAD, None, None)
            reused = validate_reused_stages(
                driver, first, jobs, deep_classification=True
            )
            verify_no_completed_legacy_aggregate(driver)
            audit = run_wrapper_audit(driver, jobs)
            archive = live["second_archive"]
            if archive is None:
                archive = atomic_archive(
                    driver, code, audit, live["first_archive"]
                )
            if live["phase"].startswith("initial_aborted"):
                reset_live_state(driver, code, archive)

            # The new archive changes only the historical-failure preflight
            # ledger, so obtain the exact post-archive payload before resume.
            jobs, checked = driver.preflight(EXPECTED_HEAD, None, None)
            reused_after = validate_reused_stages(
                driver, first, jobs, deep_classification=True
            )
            require_equal(
                reused_after["marker_sha256"],
                reused["marker_sha256"],
                "pre/post-archive scientific marker ledger",
            )
            require_equal(
                checked.get("learning_runs_started_by_postprocess"),
                0,
                "fresh preflight learning count",
            )
            require_equal(
                checked.get("wave2_launch"),
                {
                    "status": "blocked_missing_wave2_lock",
                    "launch_performed": False,
                },
                "fresh preflight Wave 2 lock",
            )

            original_validator = driver.validate_classification
            original_writer = driver.write_stage_marker
            original_next_attempt = driver.next_attempt
            original_retained = driver.run_retained_container
            original_numeric = driver.run_numeric_aggregate
            original_cross_binding = (
                driver.validate_cross_run_roofprint_binding
            )
            driver.validate_classification = (
                lambda job, attempt, roofprints:
                first.fixed_validate_classification(
                    driver, job, attempt, roofprints
                )
            )
            driver.write_stage_marker = recovered_stage_marker_writer(
                driver, original_writer, code, archive
            )
            driver.next_attempt = guarded_next_attempt(
                driver, original_next_attempt
            )
            driver.run_retained_container = forbid_retained_container
            driver.run_numeric_aggregate = recovered_numeric_runner(
                driver, original_numeric
            )
            driver.validate_cross_run_roofprint_binding = (
                lambda current_jobs, roofprints:
                validate_cross_binding_read_only(
                    driver, current_jobs, roofprints
                )
            )
            try:
                final = driver.execute_resume(jobs, checked)
            except BaseException as exc:
                record_failure(driver, code, archive, exc)
                raise
            finally:
                driver.validate_classification = original_validator
                driver.write_stage_marker = original_writer
                driver.next_attempt = original_next_attempt
                driver.run_retained_container = original_retained
                driver.run_numeric_aggregate = original_numeric
                driver.validate_cross_run_roofprint_binding = (
                    original_cross_binding
                )

            try:
                return postcheck_recovery(
                    driver,
                    first,
                    code,
                    archive,
                    jobs,
                    reused,
                    failed,
                    final,
                )
            except BaseException as exc:
                # Publication bytes are immutable once the committed driver
                # freezes them.  A later audit failure is recorded only in the
                # live driver ledger and never rewrites that frozen package.
                record_failure(driver, code, archive, exc)
                raise


def plan(
    driver: Any,
    first: Any,
    code: Mapping[str, str],
    *,
    full_audit: bool,
) -> dict[str, Any]:
    live = verify_live_state(driver, first, code)
    failed = verify_failed_aggregate_attempt()
    result: dict[str, Any] = {
        "schema": RECOVERY_SCHEMA,
        "state": "ready",
        "mode": "audit-only" if full_audit else "self-test",
        "correction_head": EXPECTED_HEAD,
        "live_phase": live["phase"],
        "driver_state_sha256": live["state_sha256"],
        "recovery_helper_sha256": code["helper_sha256"],
        "aggregate_wrapper_sha256": code["wrapper_sha256"],
        "first_helper_sha256": code["first_helper_sha256"],
        "aggregate_failure": failed,
        "archive_name": ARCHIVE_NAME,
        "scientific_stage_restart_allowed": False,
        "allowed_new_attempts": ["aggregate/attempt_002", "binding/attempt_001"],
        "expected_summary_rows": 234,
        "learning_runs_started": 0,
        "roofer_reruns_started": 0,
        "score_reruns_started": 0,
        "persistent_mutations": 0,
    }
    if full_audit:
        jobs, _ = driver.preflight(EXPECTED_HEAD, None, None)
        reused = validate_reused_stages(
            driver, first, jobs, deep_classification=True
        )
        verify_no_completed_legacy_aggregate(driver)
        result["reused_stages"] = {
            "stage_counts": reused["stage_counts"],
            "marker_count": len(reused["marker_sha256"]),
            "loss_sha256": reused["loss_sha256"],
        }
        result["aggregate_wrapper_audit"] = run_wrapper_audit(
            driver, jobs
        )
    return result


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "mode", choices=("self-test", "audit-only", "resume")
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    code = verify_code_bindings()
    require_sha(
        DRIVER_PATH,
        "8ccf1755127058abb4005e816efaca0ad38451dfd04d4e7f466f783c1dd3cd25",
        "committed postprocess driver",
    )
    driver = import_module(
        "p1w_committed_driver_for_aggregate_recovery", DRIVER_PATH
    )
    first = import_module(
        "p1w_first_receipt_recovery_for_aggregate", FIRST_HELPER_PATH
    )
    if args.mode == "resume":
        result = execute_recovery(driver, first, code)
    else:
        with driver.exclusive_lock(POSTPROCESS_ROOT / "driver.lock"):
            before = sha256_file(STATE_PATH)
            result = plan(
                driver, first, code, full_audit=args.mode == "audit-only"
            )
            after = sha256_file(STATE_PATH)
            require_equal(after, before, f"{args.mode} driver-state bytes")
            result["driver_state_sha256_before"] = before
            result["driver_state_sha256_after"] = after
            result["driver_state_bytes_unchanged"] = True
    print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
