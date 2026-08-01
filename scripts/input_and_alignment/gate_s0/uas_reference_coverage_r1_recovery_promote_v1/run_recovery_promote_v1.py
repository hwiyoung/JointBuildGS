from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any


REPO = Path(__file__).resolve().parents[4]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from scripts.input_and_alignment.gate_s0.uas_reference_coverage_r1_v1 import (  # noqa: E402
    run_uas_reference_coverage_r1 as historical,
)


TASK = "P2-GATE-S0-UAS-REFERENCE-COVERAGE-R1-RECOVERY-PROMOTE-v1"
HANDOFF = "P2-W2C-GATE-S0-UAS-REFERENCE-COVERAGE-R1-RECOVERY-PROMOTE-v1"
CONFIG_PATH = REPO / "configs/input_and_alignment/gate_s0/uas_reference_coverage_r1_recovery_promote_v1/recovery_promote_v1.json"
PACKET_PATH = REPO / "docs/handoffs/P2_W2C_GATE_S0_UAS_REFERENCE_COVERAGE_R1_RECOVERY_PROMOTE_v1.md"
SCRIPT_PATH = Path(__file__).resolve()
TEST_PATH = REPO / "tests/input_and_alignment/gate_s0/uas_reference_coverage_r1_recovery_promote_v1/test_recovery_promote_v1.py"
RECEIPT_PATH = REPO / f"artifacts/manifests/handoffs/{HANDOFF}/100-accepted.json"
HANDOFF_VALIDATOR = REPO / "scripts/repository/validate_two_host_handoff.py"


def canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def git(*args: str) -> str:
    result = subprocess.run(["git", *args], cwd=REPO, text=True, capture_output=True)
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip())
    return result.stdout.strip()


def config() -> dict[str, Any]:
    body = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    if body.get("task_id") != TASK or body.get("handoff_id") != HANDOFF or body.get("scientific_verdict") is not None:
        raise RuntimeError("recovery config identity/verdict mismatch")
    return body


def regular_bytes(path: Path) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise RuntimeError(f"regular non-symlink file required: {path}")
    return path.read_bytes()


def add_once(path: Path, data: bytes) -> dict[str, Any]:
    if path.exists():
        observed = regular_bytes(path)
        if observed != data:
            raise RuntimeError(f"add-once collision: {path}")
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        pending = path.with_name(path.name + f".pending.{os.getpid()}")
        if pending.exists():
            pending.unlink()
        with pending.open("xb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(pending, path)
        pending.unlink()
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    return {"path": path.as_posix(), "bytes": len(data), "sha256": sha256_bytes(data)}


def blob_at(commit: str, path: Path) -> str:
    return git("rev-parse", f"{commit}:{path.relative_to(REPO).as_posix()}")


def assert_historical_binding(cfg: dict[str, Any]) -> None:
    old = cfg["historical"]
    if blob_at(old["accepted_source_commit"], historical.SCRIPT_PATH) != old["runner_blob"]:
        raise RuntimeError("historical runner blob mismatch")
    if blob_at(old["accepted_source_commit"], historical.CONFIG_PATH) != old["config_blob"]:
        raise RuntimeError("historical config blob mismatch")


def assert_current_source(source_commit: str, *, require_clean: bool) -> dict[str, Any]:
    head, origin = git("rev-parse", "HEAD"), git("rev-parse", "origin/main")
    if head != source_commit or origin != source_commit:
        raise RuntimeError("recovery requires HEAD == origin/main == source commit")
    paths = (SCRIPT_PATH, CONFIG_PATH, PACKET_PATH, TEST_PATH, historical.SCRIPT_PATH)
    blobs = {}
    for path in paths:
        expected, current = blob_at(source_commit, path), git("hash-object", str(path))
        if expected != current:
            raise RuntimeError(f"source/WIP blob mismatch: {path.relative_to(REPO)}")
        blobs[path.relative_to(REPO).as_posix()] = current
    dirty = git("status", "--porcelain=v1", "--untracked-files=all")
    if require_clean and dirty:
        raise RuntimeError("recovery requires a clean worktree")
    return {"head": head, "origin_main": origin, "source_commit": source_commit, "blobs": blobs, "clean": not bool(dirty)}


def artifact_paths(cfg: dict[str, Any], artifact_root: Path) -> tuple[Path, Path]:
    if artifact_root.resolve().as_posix() != cfg["artifact_root"]:
        raise RuntimeError("artifact root mismatch")
    old_root = artifact_root.resolve() / cfg["historical"]["output_namespace"]
    recovery_root = artifact_root.resolve() / cfg["recovery_output_namespace"]
    if old_root == recovery_root or old_root in recovery_root.parents or recovery_root in old_root.parents:
        raise RuntimeError("historical and recovery namespaces must be disjoint")
    return old_root, recovery_root


def preflight(source_commit: str) -> dict[str, Any]:
    cfg = config()
    assert_historical_binding(cfg)
    contract = assert_current_source(source_commit, require_clean=True)
    if "APPROVED_FOR_EXECUTION" not in PACKET_PATH.read_text(encoding="utf-8"):
        raise RuntimeError("packet is not activated")
    result = {"task_id": TASK, "status": "PASS", "git": contract, "scientific_source_reads": 0, "scientific_verdict": None}
    print(json.dumps(result, sort_keys=True))
    return result


def acceptance_metadata(source_commit: str, artifact_root: Path, project_image_id: str) -> dict[str, Any]:
    cfg = config()
    assert_historical_binding(cfg)
    contract = assert_current_source(source_commit, require_clean=True)
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", project_image_id):
        raise RuntimeError("invalid project image ID")
    old_root, recovery_root = artifact_paths(cfg, artifact_root)
    ledger_spec = cfg["historical"]["execution_ledger"]
    ledger = old_root / ledger_spec["path"]
    observed = ledger.lstat()
    if ledger.is_symlink() or not ledger.is_file() or observed.st_size != int(ledger_spec["bytes"]):
        raise RuntimeError("historical ledger metadata mismatch")
    body = {
        "schema": "jointbuildgs.gate_s0_uas_reference_coverage_r1_recovery_acceptance.v1",
        "task_id": TASK,
        "handoff_id": HANDOFF,
        "source_commit": source_commit,
        "status": "PASS_METADATA_ONLY",
        "project_image_id": project_image_id,
        "historical_ledger": {"path": ledger.as_posix(), "bytes": observed.st_size, "content_opened_or_hashed": False},
        "scientific_payload_bytes_read_or_hashed": 0,
        "git": contract,
        "scientific_verdict": None,
    }
    record = add_once(recovery_root / "acceptance/artifact_root_preflight_v1.json", canonical_bytes(body))
    print(json.dumps({"acceptance": record, "scientific_source_reads": 0}, sort_keys=True))
    return body


def validate_acceptance(accepted_commit: str, artifact_root: Path, cfg: dict[str, Any]) -> dict[str, Any]:
    receipt_bytes = regular_bytes(RECEIPT_PATH)
    receipt = json.loads(receipt_bytes)
    offered = git("rev-parse", f"{accepted_commit}^")
    if receipt.get("state") != "accepted" or receipt.get("task_id") != TASK or receipt.get("handoff_id") != HANDOFF:
        raise RuntimeError("100-accepted identity/state mismatch")
    if receipt.get("commits", {}).get("offered_head") != offered or receipt.get("commits", {}).get("receipt_head") != "SELF":
        raise RuntimeError("100-accepted commit chain mismatch")
    if receipt.get("scientific", {}).get("scientific_verdict") is not None:
        raise RuntimeError("100-accepted scientific_verdict must be null")
    canonical = subprocess.run(
        [sys.executable, str(HANDOFF_VALIDATOR), str(RECEIPT_PATH.relative_to(REPO)), "--repo", str(REPO),
         "--origin-ref", "origin/main", "--head-ref", "HEAD", "--artifact-root", str(artifact_root)],
        cwd=REPO, text=True, capture_output=True,
    )
    if canonical.returncode:
        raise RuntimeError(f"canonical 100 validation failed: {canonical.stdout}{canonical.stderr}")
    _, recovery_root = artifact_paths(cfg, artifact_root)
    acceptance_path = recovery_root / "acceptance/artifact_root_preflight_v1.json"
    data = regular_bytes(acceptance_path)
    body = json.loads(data)
    if body.get("source_commit") != offered or body.get("scientific_payload_bytes_read_or_hashed") != 0:
        raise RuntimeError("acceptance source/read accounting mismatch")
    if body.get("project_image_id") != receipt.get("verification", {}).get("docker_image_digest"):
        raise RuntimeError("acceptance/receipt image mismatch")
    records = receipt.get("artifacts", {}).get("records", [])
    matching = [item for item in records if str(item.get("uri", "")).endswith("/acceptance/artifact_root_preflight_v1.json")]
    if len(matching) != 1 or matching[0].get("sha256") != sha256_bytes(data) or int(matching[0].get("bytes", -1)) != len(data):
        raise RuntimeError("100-accepted artifact binding mismatch")
    return {"receipt_sha256": sha256_bytes(receipt_bytes), "acceptance_sha256": sha256_bytes(data), "offered_commit": offered, "project_image_id": body["project_image_id"]}


def assert_expected(summary: dict[str, Any], validation: dict[str, Any], cfg: dict[str, Any]) -> None:
    expected = cfg["historical"]["expected"]
    observed = {
        "u_target_count": summary.get("u_target_count"),
        "e_paired_candidate_count": summary.get("e_paired_candidate_count"),
        "independent_group_count": summary.get("independent_group_count"),
        "held_out_building_count": summary.get("split_building_counts", {}).get("held_out"),
        "held_out_group_count": summary.get("split_group_counts", {}).get("held_out"),
        "claim_scope_status": summary.get("claim_scope_status"),
        "recommended_gate_action": summary.get("recommended_gate_action"),
        "attempt_counts": validation.get("source_attempts", {}).get("attempt_counts"),
    }
    if observed != expected:
        raise RuntimeError(f"historical frozen result mismatch: {observed}")
    for item in validation["source_attempts"]["per_source_read_digest_accounting"]:
        if any(int(item[key]) != 1 for key in ("known_successful_full_read_digest_passes", "full_read_digest_passes_min", "full_read_digest_passes_max")):
            raise RuntimeError("historical source read/digest count changed")


def promotion_bytes(checkpoints: historical.Checkpoints, old_root: Path) -> tuple[dict[str, dict[str, Any]], dict[str, bytes]]:
    reference = checkpoints.payload(10, "reference_candidate_frozen")
    eligibility = checkpoints.payload(20, "eligibility_candidate")
    grouping = checkpoints.payload(30, "group_split_candidate")
    claim = checkpoints.payload(40, "claim_scope")
    records = {
        "eligibility": eligibility["eligibility"],
        "candidate_ledger": grouping["candidate_ledger"],
        "group_graph": grouping["group_graph"],
        "split_candidate": grouping["split_candidate"],
        "claim_scope": claim["claim_scope"],
        "power_sensitivity": claim["power_sensitivity"],
        "pair_requirements": claim["pair_requirements"],
        "patch_summary": reference["patch_summary"],
        "patch_association_qa": eligibility["patch_association_qa"],
        "baseline_attrition": eligibility["baseline_attrition"],
    }
    return records, {name: historical.read_task_record(record, old_root) for name, record in records.items()}


def destination_map() -> dict[str, Path]:
    return {
        "eligibility": historical.DOC_ROOT / "eligibility_candidate_v1.csv",
        "candidate_ledger": historical.DOC_ROOT / "candidate_ledger_v1.csv",
        "group_graph": historical.DOC_ROOT / "group_graph_v1.csv",
        "split_candidate": historical.DOC_ROOT / "split_candidate_v1.csv",
        "claim_scope": historical.DOC_ROOT / "claim_scope_v1.json",
        "power_sensitivity": historical.DOC_ROOT / "power_sensitivity_v1.csv",
        "pair_requirements": historical.DOC_ROOT / "pair_requirements_v1.csv",
        "patch_summary": historical.DOC_ROOT / "patch_summary_v1.csv",
        "patch_association_qa": historical.DOC_ROOT / "patch_association_qa_v1.csv",
        "baseline_attrition": historical.DOC_ROOT / "baseline_attrition_v1.csv",
    }


def report_bytes(summary: dict[str, Any]) -> bytes:
    return f"""# Gate S0 independent-UAS reference coverage R1 technical report

- historical task: `{historical.TASK}`
- recovery task: `{TASK}`
- technical status: `RECOVERED_AND_PROMOTED_WITHOUT_SCIENTIFIC_SOURCE_REOPEN`
- reference candidate: `{summary['e_paired_candidate_count']}` of `{summary['u_target_count']}` buildings
- independent groups: `{summary['independent_group_count']}`
- held-out buildings/groups: `{summary['split_building_counts']['held_out']}` / `{summary['split_group_counts']['held_out']}`
- claim scope: `{summary['claim_scope_status']}`
- recommended Gate action: `{summary['recommended_gate_action']}`
- Gate S0 decision: `null`
- scientific_verdict: `null`

This report promotes the existing R1 derived evidence after correcting only the
checkpoint record write/reload envelope. The recovery did not open, hash, or
recalculate the UAS grid, predecessor eligibility/checkpoint inputs, raw UAS,
LoD1/LoD2, common-base geometry, held-out outcomes, or C1–C5 performance.

The 72 buildings share only nine independent reference/spatial groups; one group
contains 47 buildings and held-out contains ten buildings in two groups. Therefore
the result remains pilot-only and does not authorize confirmatory P2 performance.
""".encode()


def completed_fast_path(recovery_root: Path) -> dict[str, Any] | None:
    path = recovery_root / "control/recovery_ledger_v1.json"
    if not path.exists():
        return None
    body = json.loads(regular_bytes(path))
    if body.get("schema") != "jointbuildgs.gate_s0_uas_reference_coverage_r1_recovery_ledger.v1" or body.get("task_id") != TASK or body.get("status") != "COMPLETED" or body.get("scientific_verdict") is not None:
        raise RuntimeError("completed recovery ledger mismatch")
    if body.get("scientific_source_reads_or_hashes") != 0 or body.get("scientific_recalculations") != 0:
        raise RuntimeError("completed recovery source/recalculation accounting mismatch")
    for record in body.get("promoted_git_records", {}).values():
        path = (REPO / record["path"]).resolve()
        try:
            path.relative_to(REPO.resolve())
        except ValueError as error:
            raise RuntimeError("completed promotion record escapes repository") from error
        data = regular_bytes(path)
        if len(data) != int(record["bytes"]) or sha256_bytes(data) != record["sha256"]:
            raise RuntimeError(f"completed promotion digest mismatch: {path}")
    print(json.dumps({"status": "COMPLETED_FAST_PATH", "scientific_source_reads": 0, "scientific_recalculations": 0}, sort_keys=True))
    return body


def verify_promote(source_commit: str, artifact_root: Path, project_image_id: str) -> dict[str, Any]:
    cfg = config()
    assert_historical_binding(cfg)
    contract = assert_current_source(source_commit, require_clean=False)
    acceptance = validate_acceptance(source_commit, artifact_root.resolve(), cfg)
    if acceptance["project_image_id"] != project_image_id:
        raise RuntimeError("execution image does not match acceptance")
    old_root, recovery_root = artifact_paths(cfg, artifact_root)
    allowed_dirty = {path.relative_to(REPO).as_posix() for path in historical.PROMOTION_PATHS}
    dirty = {line[3:].replace("\\", "/") for line in git("status", "--porcelain=v1", "--untracked-files=all").splitlines() if line}
    if not dirty.issubset(allowed_dirty):
        raise RuntimeError(f"unrelated dirty paths: {sorted(dirty)}")
    fast = completed_fast_path(recovery_root)
    if fast is not None:
        return fast

    ledger_spec = cfg["historical"]["execution_ledger"]
    ledger_path = old_root / ledger_spec["path"]
    ledger_bytes = regular_bytes(ledger_path)
    if len(ledger_bytes) != int(ledger_spec["bytes"]) or sha256_bytes(ledger_bytes) != ledger_spec["sha256"]:
        raise RuntimeError("historical execution ledger digest mismatch")
    ledger = json.loads(ledger_bytes)
    identity = ledger.get("operation_identity", {})
    old = cfg["historical"]
    if identity.get("source_commit") != old["accepted_source_commit"] or identity.get("operation_id") != old["operation_id"] or identity.get("task_id") != old["task_id"] or identity.get("handoff_id") != old["handoff_id"]:
        raise RuntimeError("historical operation identity mismatch")

    checkpoints = historical.Checkpoints(old_root, old["operation_id"])
    attempts = historical.SourceAttempts(old_root, old["operation_id"], retry_max=1)
    validation = historical.validate_completed_ledger(ledger, identity, checkpoints, attempts, old_root)
    summary = json.loads(historical.read_task_record(checkpoints.payload(100, "technical_summary")["summary"], old_root))
    assert_expected(summary, validation, cfg)
    records, promoted = promotion_bytes(checkpoints, old_root)

    manifest = {
        **summary,
        "schema": "jointbuildgs.gate_s0_uas_reference_coverage_technical_candidate_manifest.v1",
        "historical_task_id": historical.TASK,
        "recovery_task_id": TASK,
        "recovery_source_commit": source_commit,
        "historical_execution_ledger": {"path": ledger_spec["path"], "bytes": len(ledger_bytes), "sha256": sha256_bytes(ledger_bytes)},
        "historical_operation_identity": identity,
        "historical_completed_state_validation": validation,
        "external_artifact_records": {"candidate_cells": checkpoints.payload(10, "reference_candidate_frozen")["candidate_cells"], **records},
        "promoted_copy_digests": {name: {"bytes": len(data), "sha256": sha256_bytes(data)} for name, data in promoted.items()},
        "recovery_git_contract": contract,
        "recovery_acceptance": acceptance,
        "recovery_no_repeat_contract": {
            "scientific_source_reads_or_hashes": 0,
            "scientific_recalculations": 0,
            "capture_exact_calls": 0,
            "source_attempt_start_calls": 0,
            "historical_attempt_counts_preserved": validation["source_attempts"]["attempt_counts"],
        },
        "gate_decision": None,
        "scientific_verdict": None,
    }
    output_data = {name: data for name, data in promoted.items()}
    output_data["manifest"] = canonical_bytes(manifest)
    output_data["report"] = report_bytes(summary)
    destinations = destination_map()
    destinations["manifest"] = historical.MANIFEST_PATH
    destinations["report"] = historical.DOC_ROOT / "UAS_REFERENCE_COVERAGE_R1_REPORT_v1.md"
    promoted_records = {
        name: {**add_once(path, output_data[name]), "path": path.relative_to(REPO).as_posix()}
        for name, path in destinations.items()
    }
    expected_dirty = {path.relative_to(REPO).as_posix() for path in destinations.values()}
    observed_dirty = {line[3:].replace("\\", "/") for line in git("status", "--porcelain=v1", "--untracked-files=all").splitlines() if line}
    if observed_dirty != expected_dirty:
        raise RuntimeError(f"promotion dirty-path contract mismatch: {sorted(observed_dirty)}")

    recovery = {
        "schema": "jointbuildgs.gate_s0_uas_reference_coverage_r1_recovery_ledger.v1",
        "task_id": TASK,
        "handoff_id": HANDOFF,
        "status": "COMPLETED",
        "source_commit": source_commit,
        "project_image_id": project_image_id,
        "historical_execution_ledger": {"bytes": len(ledger_bytes), "sha256": sha256_bytes(ledger_bytes)},
        "historical_operation_id": old["operation_id"],
        "validated_checkpoint_count": len(checkpoints.records),
        "validated_derived_output_count": validation["checkpoints"]["verified_output_count"],
        "historical_attempt_counts": validation["source_attempts"]["attempt_counts"],
        "frozen_result": old["expected"],
        "promoted_git_records": promoted_records,
        "scientific_source_reads_or_hashes": 0,
        "scientific_recalculations": 0,
        "scientific_verdict": None,
    }
    record = add_once(recovery_root / "control/recovery_ledger_v1.json", canonical_bytes(recovery))
    print(json.dumps({"recovery": record, "promoted": promoted_records, "scientific_source_reads": 0, "scientific_recalculations": 0}, sort_keys=True))
    return recovery


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", required=True, choices=("preflight", "acceptance-metadata", "verify-promote"))
    parser.add_argument("--source-commit")
    parser.add_argument("--artifact-root", type=Path)
    parser.add_argument("--project-image-id")
    args = parser.parse_args()
    if args.mode == "preflight":
        if not args.source_commit:
            parser.error("preflight requires --source-commit")
        preflight(args.source_commit)
    elif args.mode == "acceptance-metadata":
        if not args.source_commit or args.artifact_root is None or not args.project_image_id:
            parser.error("acceptance-metadata requires --source-commit, --artifact-root and --project-image-id")
        acceptance_metadata(args.source_commit, args.artifact_root, args.project_image_id)
    else:
        if not args.source_commit or args.artifact_root is None or not args.project_image_id:
            parser.error("verify-promote requires --source-commit, --artifact-root and --project-image-id")
        verify_promote(args.source_commit, args.artifact_root, args.project_image_id)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
