#!/usr/bin/env python3
"""Outcome-free Gate-S0 independent-UAS reference coverage calibration.

The only scientific geometry input is the predecessor's compact 3 MB UAS grid.
Raw UAS, common-base, ALS, C5, LoD2, held-out outcomes and performance results are
outside this runner's authority.  ``scientific_verdict`` is always null.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import os
import re
import stat
import subprocess
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence

import numpy as np
from scipy import ndimage, stats
from shapely.geometry import MultiPoint


REPO = Path(__file__).resolve().parents[4]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from scripts.input_and_alignment.gate_s0.freeze_recovery_v1 import (  # noqa: E402
    run_freeze_recovery as frozen,
)


TASK = "P2-GATE-S0-UAS-REFERENCE-COVERAGE-R1-v1"
HANDOFF = "P2-W2C-GATE-S0-UAS-REFERENCE-COVERAGE-R1-v1"
CONFIG_PATH = REPO / "configs/input_and_alignment/gate_s0/uas_reference_coverage_r1_v1/coverage_r1_v1.json"
PACKET_PATH = REPO / "docs/handoffs/P2_W2C_GATE_S0_UAS_REFERENCE_COVERAGE_R1_v1.md"
SCRIPT_PATH = Path(__file__).resolve()
TEST_PATH = REPO / "tests/input_and_alignment/gate_s0/uas_reference_coverage_r1_v1/test_uas_reference_coverage_r1.py"
FROZEN_RUNNER_PATH = REPO / "scripts/input_and_alignment/gate_s0/freeze_recovery_v1/run_freeze_recovery.py"
HANDOFF_VALIDATOR_PATH = REPO / "scripts/repository/validate_two_host_handoff.py"
ACCEPTANCE_RELATIVE = Path("acceptance/artifact_root_preflight_v1.json")
ACCEPTED_RECEIPT_PATH = REPO / f"artifacts/manifests/handoffs/{HANDOFF}/100-accepted.json"
MANIFEST_PATH = REPO / "artifacts/manifests/gate_s0/uas_reference_coverage_r1_v1/technical_candidate_manifest_v1.json"
DOC_ROOT = REPO / "docs/research/preregistration/gate_s0/uas_reference_coverage_r1_v1"
PROMOTION_PATHS = (
    MANIFEST_PATH,
    DOC_ROOT / "eligibility_candidate_v1.csv",
    DOC_ROOT / "candidate_ledger_v1.csv",
    DOC_ROOT / "group_graph_v1.csv",
    DOC_ROOT / "split_candidate_v1.csv",
    DOC_ROOT / "claim_scope_v1.json",
    DOC_ROOT / "power_sensitivity_v1.csv",
    DOC_ROOT / "pair_requirements_v1.csv",
    DOC_ROOT / "patch_summary_v1.csv",
    DOC_ROOT / "patch_association_qa_v1.csv",
    DOC_ROOT / "baseline_attrition_v1.csv",
    DOC_ROOT / "UAS_REFERENCE_COVERAGE_R1_REPORT_v1.md",
)
SPLITS = ("development", "validation", "held_out")


def canonical_json_bytes(value: Any) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8")


def canonical_csv_bytes(fieldnames: Sequence[str], rows: Sequence[dict[str, Any]]) -> bytes:
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=fieldnames, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue().encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_ids(values: Iterable[str]) -> str:
    return sha256_bytes("".join(f"{value}\n" for value in sorted(values)).encode())


def utc_now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=REPO, text=True).strip()


def current_blob(path: Path) -> str:
    return git("rev-parse", f"HEAD:{path.relative_to(REPO).as_posix()}")


def git_blob_at(commit: str, path: Path) -> str:
    return git("rev-parse", f"{commit}:{path.relative_to(REPO).as_posix()}")


def fsync_parent(path: Path) -> None:
    if os.name == "nt":
        return
    descriptor = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


class AddOnceWriter:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self.pending = path.with_name(f".{path.name}.pending")
        self.compare_existing = path.exists()
        self.handle = os.fdopen(os.open(self.pending, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o664), "wb", buffering=0)
        self.digest = hashlib.sha256()
        self.size = 0

    def write(self, data: bytes) -> None:
        self.handle.write(data)
        self.digest.update(data)
        self.size += len(data)

    def close(self) -> dict[str, Any]:
        self.handle.flush()
        os.fsync(self.handle.fileno())
        self.handle.close()
        digest = self.digest.hexdigest()
        if self.compare_existing:
            existing = hash_file_once(self.path)
            if existing["bytes"] != self.size or existing["sha256"] != digest:
                raise RuntimeError(f"existing add-once output differs: {self.path}")
            self.pending.unlink()
            fsync_parent(self.path)
            return {"path": self.path.as_posix(), "bytes": self.size, "sha256": digest, "reused_orphan_exact": True}
        try:
            os.link(self.pending, self.path)
        except FileExistsError:
            raise FileExistsError(self.path) from None
        fsync_parent(self.path)
        self.pending.unlink()
        fsync_parent(self.path)
        return {"path": self.path.as_posix(), "bytes": self.size, "sha256": digest}


def add_once_bytes(path: Path, data: bytes) -> dict[str, Any]:
    writer = AddOnceWriter(path)
    writer.write(data)
    return writer.close()


def add_once_json(path: Path, value: Any) -> dict[str, Any]:
    record = add_once_bytes(path, canonical_json_bytes(value))
    record["digest_method"] = "same_stream_as_add_once_serialization"
    return record


def add_once_csv(path: Path, fieldnames: Sequence[str], rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    record = add_once_bytes(path, canonical_csv_bytes(fieldnames, rows))
    record.update({"rows": len(rows), "digest_method": "same_stream_as_add_once_serialization"})
    return record


def hash_file_once(path: Path) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise RuntimeError(f"not a regular non-symlink file: {path}")
    digest = hashlib.sha256()
    total = 0
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
            total += len(chunk)
    return {"path": path.as_posix(), "bytes": total, "sha256": digest.hexdigest(), "full_passes": 1}


def add_repo_once(path: Path, data: bytes) -> dict[str, Any]:
    record = add_once_bytes(path, data)
    record["path"] = path.relative_to(REPO).as_posix()
    return record


def recover_pending(root: Path) -> list[dict[str, str]]:
    if not root.exists():
        return []
    recovered = []
    quarantine = root / "control/abandoned_pending"
    for path in sorted(root.rglob(".*.pending")):
        if not path.is_file() or path.is_symlink():
            raise RuntimeError(f"invalid pending file: {path}")
        final = path.with_name(path.name[1:-len(".pending")])
        relative = path.relative_to(root).as_posix()
        if final.exists() and os.path.samefile(path, final):
            path.unlink()
            recovered.append({"pending": relative, "action": "UNLINKED_PUBLISHED_HARDLINK"})
            continue
        quarantine.mkdir(parents=True, exist_ok=True)
        destination = quarantine / re.sub(r"[^A-Za-z0-9_.-]+", "_", relative)
        if destination.exists():
            raise RuntimeError(f"pending quarantine collision: {destination}")
        os.replace(path, destination)
        fsync_parent(destination)
        recovered.append({"pending": relative, "action": "QUARANTINED_INCOMPLETE", "quarantine": destination.relative_to(root).as_posix()})
    return recovered


def recover_selected_pending(paths: Sequence[Path], quarantine: Path) -> list[dict[str, str]]:
    recovered = []
    for final in paths:
        pending = final.with_name(f".{final.name}.pending")
        if not pending.exists():
            continue
        if pending.is_symlink() or not pending.is_file():
            raise RuntimeError(f"invalid selected pending file: {pending}")
        if final.exists() and os.path.samefile(pending, final):
            pending.unlink()
            recovered.append({"pending": pending.as_posix(), "action": "UNLINKED_PUBLISHED_HARDLINK"})
            continue
        quarantine.mkdir(parents=True, exist_ok=True)
        destination = quarantine / f"{sha256_bytes(pending.as_posix().encode())[:16]}-{pending.name[1:]}"
        if destination.exists():
            raise RuntimeError(f"selected pending quarantine collision: {destination}")
        os.replace(pending, destination)
        recovered.append({"pending": pending.as_posix(), "action": "QUARANTINED_INCOMPLETE", "quarantine": destination.as_posix()})
    return recovered


def append_invocation_event(root: Path, phase: str, payload: dict[str, Any]) -> dict[str, Any]:
    directory = root / "control/invocations"
    existing = sorted(directory.glob("[0-9][0-9][0-9][0-9]-*.json")) if directory.exists() else []
    ordinal = len(existing) + 1
    body = {
        "schema": "jointbuildgs.gate_s0_uas_reference_coverage_invocation.v1",
        "task_id": TASK,
        "ordinal": ordinal,
        "phase": phase,
        "created_at": utc_now(),
        "scientific_verdict": None,
        **payload,
    }
    return add_once_json(directory / f"{ordinal:04d}-{phase}.json", body)


def invocation_event_audit(root: Path) -> dict[str, Any]:
    records = []
    recovered_count = 0
    directory = root / "control/invocations"
    for path in sorted(directory.glob("[0-9][0-9][0-9][0-9]-*.json")) if directory.exists() else []:
        if path.is_symlink() or not path.is_file():
            raise RuntimeError(f"invocation event is not a regular non-symlink file: {path}")
        data = path.read_bytes()
        body = json.loads(data)
        if body.get("schema") != "jointbuildgs.gate_s0_uas_reference_coverage_invocation.v1" or body.get("task_id") != TASK or body.get("scientific_verdict") is not None:
            raise RuntimeError(f"invocation event schema/task/verdict mismatch: {path}")
        recovered_count += len(body.get("recovered_pending", []))
        records.append({"path": path.as_posix(), "bytes": len(data), "sha256": sha256_bytes(data), "phase": body["phase"], "ordinal": body["ordinal"]})
    return {"records": records, "recovered_pending_event_count": recovered_count}


class Checkpoints:
    def __init__(self, root: Path, operation_id: str):
        self.root = root
        self.operation_id = operation_id
        self.records: list[dict[str, Any]] = []
        self.bodies: dict[int, dict[str, Any]] = {}
        self._load()

    def _load(self) -> None:
        previous = None
        directory = self.root / "checkpoints"
        if not directory.exists():
            return
        for path in sorted(directory.glob("[0-9][0-9][0-9]-*.json")):
            if path.is_symlink() or not path.is_file():
                raise RuntimeError(f"checkpoint is not a regular non-symlink file: {path}")
            data = path.read_bytes()
            body = json.loads(data)
            ordinal = int(body.get("ordinal", -1))
            if body.get("schema") != "jointbuildgs.gate_s0_uas_reference_coverage_checkpoint.v1" or body.get("task_id") != TASK:
                raise RuntimeError(f"checkpoint schema/task mismatch: {path}")
            if body.get("operation_id") != self.operation_id or body.get("status") != "COMPLETED_FSYNC":
                raise RuntimeError(f"checkpoint operation/status mismatch: {path}")
            if body.get("scientific_verdict") is not None or path.name != f"{ordinal:03d}-{body.get('stage')}.json":
                raise RuntimeError(f"checkpoint verdict/filename mismatch: {path}")
            if ordinal in self.bodies or body.get("predecessor_checkpoint_sha256") != previous:
                raise RuntimeError(f"checkpoint chain mismatch: {path}")
            digest = sha256_bytes(data)
            record = self._record(ordinal, body["stage"], path, len(data), digest)
            self.records.append(record)
            self.bodies[ordinal] = body
            previous = digest

    def completed(self, ordinal: int, stage: str) -> bool:
        return ordinal in self.bodies and self.bodies[ordinal].get("stage") == stage

    def payload(self, ordinal: int, stage: str) -> dict[str, Any]:
        if not self.completed(ordinal, stage):
            raise RuntimeError(f"checkpoint not complete: {ordinal}-{stage}")
        return self.bodies[ordinal]["payload"]

    @staticmethod
    def _record(ordinal: int, stage: str, path: Path, size: int, digest: str) -> dict[str, Any]:
        return {
            "ordinal": ordinal,
            "stage": stage,
            "path": path.as_posix(),
            "bytes": size,
            "sha256": digest,
            "digest_method": "same_stream_as_add_once_serialization",
        }

    def write(self, ordinal: int, stage: str, payload: dict[str, Any]) -> dict[str, Any]:
        if ordinal in self.bodies:
            if not self.completed(ordinal, stage):
                raise RuntimeError("checkpoint ordinal collision")
            return self.records[[item["ordinal"] for item in self.records].index(ordinal)]
        if self.records and ordinal <= self.records[-1]["ordinal"]:
            raise RuntimeError("checkpoint ordinals must increase")
        body = {
            "schema": "jointbuildgs.gate_s0_uas_reference_coverage_checkpoint.v1",
            "task_id": TASK,
            "operation_id": self.operation_id,
            "ordinal": ordinal,
            "stage": stage,
            "status": "COMPLETED_FSYNC",
            "predecessor_checkpoint_sha256": self.records[-1]["sha256"] if self.records else None,
            "completed_at": utc_now(),
            "payload": payload,
            "scientific_verdict": None,
        }
        record = add_once_json(self.root / "checkpoints" / f"{ordinal:03d}-{stage}.json", body)
        compact = self._record(ordinal, stage, Path(record["path"]), int(record["bytes"]), record["sha256"])
        self.records.append(compact)
        self.bodies[ordinal] = body
        print(json.dumps({"checkpoint": ordinal, "stage": stage, "sha256": record["sha256"]}, sort_keys=True), flush=True)
        return compact


class SourceAttempts:
    def __init__(self, root: Path, operation_id: str, retry_max: int):
        self.root = root
        self.operation_id = operation_id
        self.maximum_attempts = 1 + int(retry_max)

    def start(self, stage: str, sources: Sequence[dict[str, Any]]) -> dict[str, Any]:
        if not re.fullmatch(r"[A-Za-z0-9_.-]+", stage):
            raise RuntimeError("invalid attempt stage")
        directory = self.root / "attempts" / stage
        existing = sorted(directory.glob("attempt_[0-9][0-9].json")) if directory.exists() else []
        if len(existing) >= self.maximum_attempts:
            raise RuntimeError(f"source retry cap exhausted: {stage}")
        number = len(existing) + 1
        body = {
            "schema": "jointbuildgs.gate_s0_uas_reference_coverage_source_attempt.v1",
            "task_id": TASK,
            "operation_id": self.operation_id,
            "stage": stage,
            "attempt_number": number,
            "status": "SOURCE_OPEN_INTENT_FSYNC",
            "sources": list(sources),
            "created_at": utc_now(),
            "completion_evidence": "matching completed checkpoint",
            "scientific_verdict": None,
        }
        return add_once_json(directory / f"attempt_{number:02d}.json", body)

    def audit(self, successful_stages: set[str] | None = None) -> dict[str, Any]:
        successful_stages = successful_stages or set()
        rows = []
        counts: Counter[str] = Counter()
        source_bytes_by_stage: dict[str, int] = {}
        sources_by_stage: dict[str, list[dict[str, Any]]] = {}
        directory = self.root / "attempts"
        for path in sorted(directory.glob("*/attempt_[0-9][0-9].json")) if directory.exists() else []:
            body = json.loads(path.read_bytes())
            if body.get("task_id") != TASK or body.get("operation_id") != self.operation_id:
                raise RuntimeError(f"attempt operation mismatch: {path}")
            counts[body["stage"]] += 1
            declared_bytes = sum(int(item.get("accepted_bytes", 0)) for item in body.get("sources", []))
            previous = source_bytes_by_stage.setdefault(body["stage"], declared_bytes)
            if previous != declared_bytes:
                raise RuntimeError(f"attempt source-byte contract changed: {path}")
            normalized_sources = [
                {
                    "path": item["path"],
                    "accepted_bytes": int(item["accepted_bytes"]),
                    "accepted_sha256": item["accepted_sha256"],
                }
                for item in body.get("sources", [])
            ]
            previous_sources = sources_by_stage.setdefault(body["stage"], normalized_sources)
            if previous_sources != normalized_sources:
                raise RuntimeError(f"attempt source identity changed: {path}")
            rows.append({**hash_file_once(path), "stage": body["stage"], "attempt_number": body["attempt_number"]})
        unknown = {
            stage: {
                "unknown_prior_attempts": max(count - 1, 0),
                "unknown_prior_boundary_bytes_max": max(count - 1, 0) * source_bytes_by_stage[stage],
            }
            for stage, count in sorted(counts.items())
        }
        per_source = []
        for stage, sources in sorted(sources_by_stage.items()):
            successful = stage in successful_stages
            attempts = counts[stage]
            for source in sources:
                per_source.append(
                    {
                        "stage": stage,
                        **source,
                        "known_successful_full_read_digest_passes": int(successful),
                        "prior_unknown_attempts": max(attempts - int(successful), 0),
                        "full_read_digest_passes_min": int(successful),
                        "full_read_digest_passes_max": attempts,
                        "bytes_read_and_digested_min": int(successful) * source["accepted_bytes"],
                        "bytes_read_and_digested_max": attempts * source["accepted_bytes"],
                    }
                )
        return {
            "maximum_attempts_per_stage": self.maximum_attempts,
            "attempt_counts": dict(sorted(counts.items())),
            "unknown_crash_boundary_accounting": unknown,
            "per_source_read_digest_accounting": per_source,
            "records": rows,
        }


def assert_git_contract(source_commit: str, strict_refs: bool, require_clean: bool, include_receipt: bool = False) -> dict[str, Any]:
    git("cat-file", "-e", f"{source_commit}^{{commit}}")
    paths = [SCRIPT_PATH, CONFIG_PATH, PACKET_PATH, TEST_PATH, FROZEN_RUNNER_PATH, HANDOFF_VALIDATOR_PATH]
    if include_receipt:
        paths.append(ACCEPTED_RECEIPT_PATH)
    blobs = {}
    for path in paths:
        expected = git_blob_at(source_commit, path)
        actual = current_blob(path)
        if expected != actual:
            raise RuntimeError(f"source/WIP blob mismatch: {path.relative_to(REPO)}")
        blobs[path.relative_to(REPO).as_posix()] = actual
    dirty = git("status", "--porcelain=v1", "--untracked-files=all")
    if require_clean and dirty:
        raise RuntimeError("execution requires a clean worktree")
    head, origin = git("rev-parse", "HEAD"), git("rev-parse", "origin/main")
    if strict_refs and (head != source_commit or origin != source_commit):
        raise RuntimeError("requires HEAD == origin/main == source commit")
    return {"source_commit": source_commit, "head": head, "origin_main": origin, "blobs": blobs, "clean": not bool(dirty)}


def metadata_stat(path: Path, expected_bytes: int) -> dict[str, Any]:
    if path.is_symlink():
        raise RuntimeError(f"metadata input is a symlink: {path}")
    observed = path.lstat()
    if not stat.S_ISREG(observed.st_mode) or observed.st_size != expected_bytes:
        raise RuntimeError(f"metadata input type/size mismatch: {path}")
    return {"path": path.as_posix(), "bytes": observed.st_size, "file_type": "regular", "content_opened_or_hashed": False}


def input_specs(config: dict[str, Any]) -> list[dict[str, Any]]:
    return [{"path": value["path"], "bytes": int(value["bytes"]), "sha256": value["sha256"]} for value in (config["inputs"]["grid"], config["inputs"]["source_checkpoint"], config["inputs"]["eligibility"])]


def acceptance_metadata(source_commit: str, artifact_root: Path, project_image_id: str) -> dict[str, Any]:
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    if artifact_root.resolve().as_posix() != config["artifact_root"]:
        raise RuntimeError("artifact root mismatch")
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", project_image_id):
        raise RuntimeError("invalid project image ID")
    contract = assert_git_contract(source_commit, strict_refs=True, require_clean=True)
    stats = [metadata_stat(artifact_root / spec["path"], spec["bytes"]) for spec in input_specs(config)]
    output_root = artifact_root / config["output_namespace"]
    output_root.mkdir(parents=True, exist_ok=True)
    recovered = recover_pending(output_root)
    body = {
        "schema": "jointbuildgs.gate_s0_uas_reference_coverage_acceptance.v1",
        "task_id": TASK,
        "handoff_id": HANDOFF,
        "source_commit": source_commit,
        "status": "PASS_METADATA_ONLY",
        "artifact_root": config["artifact_root"],
        "project_docker_image": "jointbuildgs:dev",
        "project_docker_image_id": project_image_id,
        "input_stats": stats,
        "scientific_payload_bytes_read_or_hashed": 0,
        "predecessor_receipt_classification_defect": "ROOFER_TECHNICAL_FAILURE_USED_200_VERIFIED_INSTEAD_OF_200_BLOCKED",
        "git": contract,
        "scientific_verdict": None,
    }
    record = add_once_json(output_root / ACCEPTANCE_RELATIVE, body)
    append_invocation_event(
        output_root,
        "acceptance_metadata",
        {"source_commit": source_commit, "recovered_pending": recovered, "acceptance": record},
    )
    print(json.dumps({"acceptance": record, "scientific_payload_bytes": 0}, sort_keys=True))
    return body


def validate_acceptance(source_commit: str, artifact_root: Path, config: dict[str, Any]) -> dict[str, Any]:
    if not ACCEPTED_RECEIPT_PATH.is_file():
        raise RuntimeError("100-accepted receipt missing")
    receipt_bytes = ACCEPTED_RECEIPT_PATH.read_bytes()
    receipt = json.loads(receipt_bytes)
    if receipt.get("state") != "accepted" or receipt.get("handoff_id") != HANDOFF or receipt.get("task_id") != TASK:
        raise RuntimeError("100 receipt identity/state mismatch")
    if receipt.get("verification", {}).get("level") != "artifact_verified" or not receipt.get("transport", {}).get("exclusive_writer_ack"):
        raise RuntimeError("100 receipt is not artifact-verified/exclusive")
    if receipt.get("scientific", {}).get("scientific_verdict") is not None:
        raise RuntimeError("100 scientific_verdict must be null")
    offered_commit = git("rev-parse", f"{source_commit}^")
    if receipt.get("commits", {}).get("offered_head") != offered_commit or receipt.get("commits", {}).get("receipt_head") != "SELF":
        raise RuntimeError("100 receipt commit chain is not the direct offered parent")
    offered_relative = Path(f"artifacts/manifests/handoffs/{HANDOFF}/000-offered.json")
    offered_path = REPO / offered_relative
    previous = receipt.get("previous_receipt", {})
    if previous.get("path") != offered_relative.as_posix() or not offered_path.is_file() or previous.get("sha256") != sha256_bytes(offered_path.read_bytes()):
        raise RuntimeError("100 receipt predecessor path/digest mismatch")
    canonical = subprocess.run(
        [
            sys.executable,
            str(HANDOFF_VALIDATOR_PATH),
            str(ACCEPTED_RECEIPT_PATH.relative_to(REPO)),
            "--repo", str(REPO),
            "--origin-ref", "origin/main",
            "--head-ref", "HEAD",
            "--artifact-root", str(artifact_root),
        ],
        cwd=REPO,
        text=True,
        capture_output=True,
    )
    if canonical.returncode != 0:
        raise RuntimeError(f"canonical 100 receipt validation failed: {canonical.stdout}{canonical.stderr}")
    path = artifact_root / config["output_namespace"] / ACCEPTANCE_RELATIVE
    data = path.read_bytes()
    body = json.loads(data)
    if body.get("source_commit") != offered_commit:
        raise RuntimeError("acceptance source is not the offered/direct-parent commit")
    if body.get("status") != "PASS_METADATA_ONLY" or body.get("scientific_payload_bytes_read_or_hashed") != 0:
        raise RuntimeError("acceptance status/read accounting mismatch")
    if receipt.get("verification", {}).get("docker_image_digest") != body.get("project_docker_image_id"):
        raise RuntimeError("100 receipt Docker digest does not bind acceptance image ID")
    expected = sorted((spec["path"], spec["bytes"]) for spec in input_specs(config))
    observed = sorted((Path(item["path"]).relative_to(artifact_root).as_posix(), int(item["bytes"])) for item in body.get("input_stats", []))
    if observed != expected:
        raise RuntimeError("acceptance stat set mismatch")
    records = receipt.get("artifacts", {}).get("records", [])
    matched = [item for item in records if str(item.get("uri", "")).endswith("/" + ACCEPTANCE_RELATIVE.as_posix())]
    if len(matched) != 1 or matched[0].get("sha256") != sha256_bytes(data) or int(matched[0].get("bytes", -1)) != len(data):
        raise RuntimeError("100 receipt does not bind acceptance artifact")
    return {
        "receipt_sha256": sha256_bytes(receipt_bytes),
        "acceptance_sha256": sha256_bytes(data),
        "project_image_id": body["project_docker_image_id"],
        "canonical_validator": "PASS",
        "offered_commit": offered_commit,
    }


def capture_exact(path: Path, spec: dict[str, Any]) -> tuple[bytes, dict[str, Any]]:
    if path.is_symlink() or not path.is_file():
        raise RuntimeError(f"input is not a regular non-symlink file: {path}")
    data = path.read_bytes()
    observed = {"path": path.as_posix(), "bytes": len(data), "sha256": sha256_bytes(data), "full_content_read_and_digest_passes": 1}
    if observed["bytes"] != int(spec["bytes"]) or observed["sha256"] != spec["sha256"]:
        raise RuntimeError(f"input bytes/digest mismatch: {path}")
    return data, observed


GRID_NAMES = ("min_z", "max_z", "count", "sum_z", "sum_z2", "class2_min_z", "class2_count", "class6_max_z", "class6_count")


def load_grid_from_bytes(data: bytes, config: dict[str, Any]) -> frozen.RecoveryGrid:
    bbox = tuple(float(value) for value in config["aoi"]["bbox"])
    grid = frozen.RecoveryGrid(bbox, float(config["aoi"]["cell_m"]))
    with np.load(io.BytesIO(data), allow_pickle=False) as source:
        if tuple(sorted(source.files)) != tuple(sorted(GRID_NAMES)):
            raise RuntimeError("grid NPZ member allowlist mismatch")
        for name in GRID_NAMES:
            value = np.asarray(source[name])
            target = getattr(grid, name)
            if value.dtype.hasobject or value.shape != target.shape or value.dtype != target.dtype:
                raise RuntimeError(f"grid array shape/dtype mismatch: {name}")
            target[:] = value
    return grid


@dataclass(frozen=True)
class Edge:
    left: int
    right: int
    theta: float
    height_step: float
    cross_plane: float
    score: float


@dataclass
class PlaneFields:
    rmse: np.ndarray
    normal_z: np.ndarray
    neighbors: np.ndarray
    a: np.ndarray
    b: np.ndarray
    center_c: np.ndarray


def local_plane_fields(top: np.ndarray, candidate: np.ndarray, cell: float, window: int, minimum_neighbors: int) -> PlaneFields:
    radius = window // 2
    shape = top.shape
    rmse = np.full(shape, np.inf, dtype=np.float64)
    normal_z = np.zeros(shape, dtype=np.float64)
    neighbors = np.zeros(shape, dtype=np.uint16)
    a_field = np.full(shape, np.nan, dtype=np.float64)
    b_field = np.full(shape, np.nan, dtype=np.float64)
    c_field = np.full(shape, np.nan, dtype=np.float64)
    finite = np.isfinite(top)
    for iy, ix in np.argwhere(candidate):
        y0, y1 = max(0, iy - radius), min(shape[0], iy + radius + 1)
        x0, x1 = max(0, ix - radius), min(shape[1], ix + radius + 1)
        valid = finite[y0:y1, x0:x1]
        count = int(np.count_nonzero(valid))
        neighbors[iy, ix] = count
        if count < minimum_neighbors:
            continue
        ly, lx = np.nonzero(valid)
        design = np.column_stack((lx.astype(np.float64) * cell, ly.astype(np.float64) * cell, np.ones(count)))
        values = top[y0:y1, x0:x1][valid]
        coefficients, _, _, _ = np.linalg.lstsq(design, values, rcond=None)
        residual = values - design @ coefficients
        a, b, c_window = (float(value) for value in coefficients)
        rmse[iy, ix] = float(np.sqrt(np.mean(residual * residual)))
        normal_z[iy, ix] = float(1.0 / math.sqrt(1.0 + a * a + b * b))
        a_field[iy, ix], b_field[iy, ix] = a, b
        c_field[iy, ix] = a * ((ix - x0) * cell) + b * ((iy - y0) * cell) + c_window
    return PlaneFields(rmse, normal_z, neighbors, a_field, b_field, c_field)


def compute_masks(grid: frozen.RecoveryGrid, config: dict[str, Any]) -> tuple[dict[str, np.ndarray], PlaneFields, np.ndarray, dict[int, float]]:
    rule = config["per_cell"]
    terrain = frozen.terrain_envelope(grid, rule["terrain_filter_windows_cells"])
    top = grid.max_z.reshape(grid.ny, grid.nx)
    count = grid.count.reshape(grid.ny, grid.nx)
    z_std = grid.z_std().reshape(grid.ny, grid.nx)
    masks: dict[str, np.ndarray] = {}
    masks["raw_observed"] = np.isfinite(top) & (count > 0)
    masks["minimum_points"] = masks["raw_observed"] & (count >= int(rule["minimum_points_per_cell"]))
    masks["height"] = masks["minimum_points"] & ((top - terrain) >= float(rule["minimum_height_above_terrain_m"]))
    masks["z_std"] = masks["height"] & (z_std <= float(rule["within_cell_z_std_limit_m"]))
    fields = local_plane_fields(top, masks["z_std"], grid.cell, int(rule["local_window_cells"]), int(rule["minimum_valid_neighbors"]))
    old_rmse, old_normal_z, old_neighbors = frozen.local_plane_metrics(top, masks["z_std"], grid.cell, int(rule["local_window_cells"]), int(rule["minimum_valid_neighbors"]))
    if not np.array_equal(fields.neighbors, old_neighbors) or not np.allclose(fields.rmse, old_rmse, atol=1e-12, rtol=0, equal_nan=True) or not np.allclose(fields.normal_z, old_normal_z, atol=1e-12, rtol=0, equal_nan=True):
        raise RuntimeError("extended OLS fields do not reproduce frozen RMSE/normal_z")
    masks["neighbors"] = masks["z_std"] & (fields.neighbors >= int(rule["minimum_valid_neighbors"]))
    masks["plane_rmse"] = masks["neighbors"] & (fields.rmse <= float(rule["local_plane_rmse_limit_m"]))
    masks["normal"] = masks["plane_rmse"] & (fields.normal_z >= float(rule["minimum_up_dot"]))
    masks["roughness"] = masks["normal"] & ~((fields.rmse > float(rule["vegetation_roughness_limit_m"])) & (z_std > float(rule["vegetation_z_std_trigger_m"])))
    preliminary_labels, _ = ndimage.label(masks["z_std"], structure=np.ones((3, 3), dtype=np.uint8))
    sizes = np.bincount(preliminary_labels.ravel())
    fractions: dict[int, float] = {}
    large = []
    baseline_accepted = []
    for label in range(1, len(sizes)):
        size = int(sizes[label])
        if size < int(rule["minimum_component_cells"]):
            continue
        large.append(label)
        fraction = float(np.count_nonzero(masks["roughness"] & (preliminary_labels == label)) / size)
        fractions[label] = fraction
        if fraction >= float(rule["baseline_minimum_planar_fraction"]):
            baseline_accepted.append(label)
    masks["preliminary_component_size"] = masks["roughness"] & np.isin(preliminary_labels, large)
    masks["baseline_planar_fraction"] = masks["roughness"] & np.isin(preliminary_labels, baseline_accepted)
    labels, _ = ndimage.label(masks["baseline_planar_fraction"], structure=np.ones((3, 3), dtype=np.uint8))
    final_sizes = np.bincount(labels.ravel())
    retained = [label for label in range(1, len(final_sizes)) if final_sizes[label] >= int(rule["minimum_component_cells"])]
    masks["baseline_final"] = np.isin(labels, retained)
    diagnostic_labels, _ = ndimage.label(masks["roughness"], structure=np.ones((3, 3), dtype=np.uint8))
    diagnostic_sizes = np.bincount(diagnostic_labels.ravel())
    diagnostic_retained = [label for label in range(1, len(diagnostic_sizes)) if diagnostic_sizes[label] >= int(rule["minimum_component_cells"])]
    masks["diagnostic_final"] = np.isin(diagnostic_labels, diagnostic_retained)
    if int(np.count_nonzero(masks["roughness"])) != int(rule["expected_planar_cells"]):
        raise RuntimeError("pre-segmentation planar cell count mismatch")
    if len(retained) != int(rule["expected_baseline_components"]) or int(np.count_nonzero(masks["baseline_final"])) != int(rule["expected_baseline_cells"]):
        raise RuntimeError("baseline component/cell count mismatch")
    if len(diagnostic_retained) != int(rule["expected_diagnostic_components"]) or int(np.count_nonzero(masks["diagnostic_final"])) != int(rule["expected_diagnostic_cells"]):
        raise RuntimeError("diagnostic component/cell count mismatch")
    return masks, fields, terrain, fractions


def unit_normal(a: float, b: float) -> np.ndarray:
    value = np.array([-a, -b, 1.0], dtype=np.float64)
    return value / np.linalg.norm(value)


def global_plane(members: Sequence[int], top: np.ndarray, shape: tuple[int, int], cell: float, fields: PlaneFields) -> dict[str, Any]:
    iy, ix = np.unravel_index(np.asarray(members, dtype=np.int64), shape)
    x = ix.astype(np.float64) * cell
    y = iy.astype(np.float64) * cell
    z = top[iy, ix]
    cx, cy = float(np.mean(x)), float(np.mean(y))
    design = np.column_stack((x - cx, y - cy, np.ones(len(members))))
    coefficients, _, rank, _ = np.linalg.lstsq(design, z, rcond=None)
    residual = z - design @ coefficients
    a, b, c = (float(value) for value in coefficients)
    normal = unit_normal(a, b)
    local_normals = np.column_stack((-fields.a[iy, ix], -fields.b[iy, ix], np.ones(len(members))))
    local_normals /= np.linalg.norm(local_normals, axis=1)[:, None]
    angles = np.degrees(np.arccos(np.clip(local_normals @ normal, -1.0, 1.0)))
    return {
        "a": a, "b": b, "c_center": c, "center_x": cx, "center_y": cy,
        "rank": int(rank), "rmse": float(np.sqrt(np.mean(residual * residual))),
        "max_abs_residual": float(np.max(np.abs(residual))), "normal": normal,
        "local_angles": angles, "residual": residual,
    }


def build_edges(mask: np.ndarray, top: np.ndarray, fields: PlaneFields, config: dict[str, Any]) -> tuple[list[Edge], list[dict[str, Any]]]:
    rule = config["segmentation"]
    epsilon = float(rule["comparison_epsilon"])
    directions = ((0, 1), (1, -1), (1, 0), (1, 1))
    accepted: list[Edge] = []
    rejected: list[dict[str, Any]] = []
    ny, nx = mask.shape
    for iy, ix in np.argwhere(mask):
        left = int(iy * nx + ix)
        normal_left = unit_normal(float(fields.a[iy, ix]), float(fields.b[iy, ix]))
        for dy, dx in directions:
            jy, jx = int(iy + dy), int(ix + dx)
            if jy < 0 or jy >= ny or jx < 0 or jx >= nx or not mask[jy, jx]:
                continue
            right = int(jy * nx + jx)
            normal_right = unit_normal(float(fields.a[jy, jx]), float(fields.b[jy, jx]))
            theta = float(np.degrees(np.arccos(np.clip(float(normal_left @ normal_right), -1.0, 1.0))))
            mx, my = dx * float(config["aoi"]["cell_m"]), dy * float(config["aoi"]["cell_m"])
            height = abs(float((top[jy, jx] - top[iy, ix]) - 0.5 * ((fields.a[iy, ix] + fields.a[jy, jx]) * mx + (fields.b[iy, ix] + fields.b[jy, jx]) * my)))
            predicted_right = float(fields.center_c[iy, ix] + fields.a[iy, ix] * mx + fields.b[iy, ix] * my)
            predicted_left = float(fields.center_c[jy, jx] - fields.a[jy, jx] * mx - fields.b[jy, jx] * my)
            cross = max(abs(float(top[jy, jx]) - predicted_right), abs(float(top[iy, ix]) - predicted_left))
            reasons = []
            if theta > float(rule["edge_normal_deg"]) + epsilon:
                reasons.append("normal")
            if height > float(rule["edge_height_step_m"]) + epsilon:
                reasons.append("height")
            if cross > float(rule["edge_cross_plane_m"]) + epsilon:
                reasons.append("cross_plane")
            if reasons:
                rejected.append({"left": left, "right": right, "reasons": reasons})
                continue
            score = max(theta / float(rule["edge_normal_deg"]), height / float(rule["edge_height_step_m"]), cross / float(rule["edge_cross_plane_m"]))
            accepted.append(Edge(min(left, right), max(left, right), theta, height, cross, score))
    decimals = int(rule["sort_decimals"])
    accepted.sort(key=lambda edge: (round(edge.score, decimals), round(edge.theta, decimals), round(edge.cross_plane, decimals), round(edge.height_step, decimals), edge.left, edge.right))
    return accepted, rejected


class FlatUnion:
    def __init__(self, values: Iterable[int]):
        self.parent = {int(value): int(value) for value in values}
        self.members = {int(value): [int(value)] for value in values}

    def find(self, value: int) -> int:
        while self.parent[value] != value:
            self.parent[value] = self.parent[self.parent[value]]
            value = self.parent[value]
        return value

    def merge(self, left: int, right: int) -> int:
        a, b = self.find(left), self.find(right)
        if a == b:
            return a
        root, other = min(a, b), max(a, b)
        self.parent[other] = root
        self.members[root] = sorted(self.members[root] + self.members.pop(other))
        return root


def segment_patches(mask: np.ndarray, top: np.ndarray, fields: PlaneFields, config: dict[str, Any]) -> dict[str, Any]:
    rule = config["segmentation"]
    planar = [int(value) for value in np.flatnonzero(mask.ravel())]
    union = FlatUnion(planar)
    edges, local_rejected = build_edges(mask, top, fields, config)
    accepted_edges: list[Edge] = []
    global_rejected: list[dict[str, Any]] = []
    epsilon = float(rule["comparison_epsilon"])
    for edge in edges:
        left, right = union.find(edge.left), union.find(edge.right)
        if left == right:
            accepted_edges.append(edge)
            continue
        combined = sorted(union.members[left] + union.members[right])
        if len(combined) == 2:
            passes, fit, reasons = True, None, []
        else:
            fit = global_plane(combined, top, mask.shape, float(config["aoi"]["cell_m"]), fields)
            reasons = []
            if fit["rank"] != 3:
                reasons.append("global_rank")
            if fit["rmse"] > float(rule["patch_plane_rmse_m"]) + epsilon:
                reasons.append("global_rmse")
            if fit["max_abs_residual"] > float(rule["patch_max_abs_residual_m"]) + epsilon:
                reasons.append("global_max_residual")
            if float(np.max(fit["local_angles"])) > float(rule["patch_max_local_normal_deg"]) + epsilon:
                reasons.append("global_normal")
            passes = not reasons
        if passes:
            union.merge(left, right)
            accepted_edges.append(edge)
        else:
            global_rejected.append({"left": edge.left, "right": edge.right, "reasons": reasons})
    final_components = sorted((members for members in union.members.values() if len(members) >= int(rule["final_min_cells"])), key=lambda values: values[0])
    namespace = sha256_bytes(canonical_json_bytes({"method": rule, "aoi": config["aoi"], "per_cell": config["per_cell"]}))
    patches = {}
    seen: set[int] = set()
    for members in final_components:
        if seen.intersection(members):
            raise RuntimeError("duplicate patch cell")
        seen.update(members)
        identity = sha256_bytes((namespace + "|" + ",".join(str(value) for value in members) + "\n").encode())[:20]
        patch_id = f"UASPATCH_{identity}"
        if patch_id in patches:
            raise RuntimeError("patch ID collision")
        patches[patch_id] = members
    return {"patches": patches, "accepted_edges": accepted_edges, "local_rejected": local_rejected, "global_rejected": global_rejected, "namespace_sha256": namespace}


def quantile(values: Sequence[float], q: float) -> float:
    return float(np.quantile(np.asarray(values, dtype=np.float64), q)) if values else float("nan")


def cell_footprint_hull_metrics(xs: Sequence[float], ys: Sequence[float], cell: float) -> dict[str, float]:
    if len(xs) != len(ys) or not xs:
        raise ValueError("non-empty matched cell-center coordinates required")
    half_cell = cell / 2.0
    corners = [
        (x + dx, y + dy)
        for x, y in zip(xs, ys)
        for dx, dy in ((-half_cell, -half_cell), (-half_cell, half_cell), (half_cell, -half_cell), (half_cell, half_cell))
    ]
    hull_area = float(MultiPoint(corners).convex_hull.area)
    fill_ratio = len(xs) * cell * cell / hull_area
    if fill_ratio > 1.0 + 1e-12:
        raise RuntimeError("cell-footprint convex-hull fill ratio exceeds one")
    return {
        "bbox_min_x": float(min(xs) - half_cell),
        "bbox_min_y": float(min(ys) - half_cell),
        "bbox_max_x": float(max(xs) + half_cell),
        "bbox_max_y": float(max(ys) + half_cell),
        "convex_hull_area": hull_area,
        "fill_ratio": min(fill_ratio, 1.0),
    }


def patch_outputs(grid: frozen.RecoveryGrid, masks: dict[str, np.ndarray], fields: PlaneFields, terrain: np.ndarray, fractions: dict[int, float], segmentation: dict[str, Any], config: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    top = grid.max_z.reshape(grid.ny, grid.nx)
    z_std = grid.z_std().reshape(grid.ny, grid.nx)
    prelim_labels, _ = ndimage.label(masks["z_std"], structure=np.ones((3, 3), dtype=np.uint8))
    x0, y0, _, _ = grid.bbox
    cell_rows = []
    summary_rows = []
    final_root = {}
    for patch_id, members in segmentation["patches"].items():
        for flat in members:
            final_root[flat] = patch_id
    internal_edges: defaultdict[str, list[Edge]] = defaultdict(list)
    for edge in segmentation["accepted_edges"]:
        if final_root.get(edge.left) and final_root.get(edge.left) == final_root.get(edge.right):
            internal_edges[final_root[edge.left]].append(edge)
    rejected_counts: defaultdict[str, Counter[str]] = defaultdict(Counter)
    for item in [*segmentation["local_rejected"], *segmentation["global_rejected"]]:
        for flat in (item["left"], item["right"]):
            patch_id = final_root.get(flat)
            if patch_id:
                rejected_counts[patch_id].update(item["reasons"])
    for patch_id, members in sorted(segmentation["patches"].items()):
        iy, ix = np.unravel_index(np.asarray(members, dtype=np.int64), top.shape)
        xs = x0 + (ix.astype(np.float64) + 0.5) * grid.cell
        ys = y0 + (iy.astype(np.float64) + 0.5) * grid.cell
        heights = top[iy, ix] - terrain[iy, ix]
        fit = global_plane(members, top, top.shape, grid.cell, fields)
        source_fractions = [fractions.get(int(prelim_labels[y, x]), 0.0) for y, x in zip(iy, ix)]
        angles = fit["local_angles"].tolist()
        edges = internal_edges[patch_id]
        hull = cell_footprint_hull_metrics(xs.tolist(), ys.tolist(), grid.cell)
        hull_area, fill_ratio = hull["convex_hull_area"], hull["fill_ratio"]
        bbox_min_x, bbox_min_y = hull["bbox_min_x"], hull["bbox_min_y"]
        bbox_max_x, bbox_max_y = hull["bbox_max_x"], hull["bbox_max_y"]
        bbox_width, bbox_height = bbox_max_x - bbox_min_x, bbox_max_y - bbox_min_y
        summary_rows.append({
            "patch_id": patch_id, "cell_count": len(members), "area_m2": f"{len(members) * grid.cell * grid.cell:.6f}",
            "bbox_min_x": f"{bbox_min_x:.3f}", "bbox_min_y": f"{bbox_min_y:.3f}", "bbox_max_x": f"{bbox_max_x:.3f}", "bbox_max_y": f"{bbox_max_y:.3f}",
            "bbox_width_m": f"{bbox_width:.6f}", "bbox_height_m": f"{bbox_height:.6f}", "bbox_diagonal_m": f"{math.hypot(bbox_width, bbox_height):.6f}",
            "cell_footprint_convex_hull_area_m2": f"{hull_area:.6f}", "cell_footprint_hull_fill_ratio": f"{fill_ratio:.9f}",
            "relative_height_min_m": f"{np.min(heights):.6f}", "relative_height_median_m": f"{np.median(heights):.6f}", "relative_height_p95_m": f"{np.quantile(heights, .95):.6f}", "relative_height_max_m": f"{np.max(heights):.6f}", "relative_height_range_m": f"{np.ptp(heights):.6f}", "relative_height_mad_m": f"{np.median(np.abs(heights - np.median(heights))):.6f}",
            "local_rmse_median_m": f"{np.median(fields.rmse[iy, ix]):.9f}", "local_rmse_p95_m": f"{np.quantile(fields.rmse[iy, ix], .95):.9f}", "local_rmse_max_m": f"{np.max(fields.rmse[iy, ix]):.9f}",
            "z_std_median_m": f"{np.median(z_std[iy, ix]):.9f}", "z_std_p95_m": f"{np.quantile(z_std[iy, ix], .95):.9f}", "z_std_max_m": f"{np.max(z_std[iy, ix]):.9f}",
            "local_to_global_normal_median_deg": f"{np.median(angles):.9f}", "local_to_global_normal_p95_deg": f"{np.quantile(angles, .95):.9f}", "local_to_global_normal_max_deg": f"{np.max(angles):.9f}",
            "global_plane_a": f"{fit['a']:.12f}", "global_plane_b": f"{fit['b']:.12f}", "global_plane_c_center": f"{fit['c_center']:.12f}", "global_plane_rmse_m": f"{fit['rmse']:.9f}", "global_plane_max_abs_residual_m": f"{fit['max_abs_residual']:.9f}",
            "internal_edge_theta_p50_deg": f"{quantile([edge.theta for edge in edges], .5):.9f}", "internal_edge_theta_p95_deg": f"{quantile([edge.theta for edge in edges], .95):.9f}", "internal_edge_theta_max_deg": f"{max([edge.theta for edge in edges], default=0):.9f}",
            "internal_edge_height_p50_m": f"{quantile([edge.height_step for edge in edges], .5):.9f}", "internal_edge_height_p95_m": f"{quantile([edge.height_step for edge in edges], .95):.9f}", "internal_edge_height_max_m": f"{max([edge.height_step for edge in edges], default=0):.9f}",
            "internal_edge_cross_plane_p50_m": f"{quantile([edge.cross_plane for edge in edges], .5):.9f}", "internal_edge_cross_plane_p95_m": f"{quantile([edge.cross_plane for edge in edges], .95):.9f}", "internal_edge_cross_plane_max_m": f"{max([edge.cross_plane for edge in edges], default=0):.9f}",
            "source_planar_fraction_weighted_mean": f"{np.mean(source_fractions):.9f}", "source_planar_fraction_min": f"{np.min(source_fractions):.9f}", "source_below_0_70_cell_fraction": f"{np.mean(np.asarray(source_fractions) < .7):.9f}",
            "rejected_normal_edges": rejected_counts[patch_id]["normal"], "rejected_height_edges": rejected_counts[patch_id]["height"], "rejected_cross_plane_edges": rejected_counts[patch_id]["cross_plane"],
            "rejected_global_rank_edges": rejected_counts[patch_id]["global_rank"], "rejected_global_rmse_edges": rejected_counts[patch_id]["global_rmse"], "rejected_global_max_residual_edges": rejected_counts[patch_id]["global_max_residual"], "rejected_global_normal_edges": rejected_counts[patch_id]["global_normal"],
        })
        for flat, y, x in zip(members, iy, ix):
            cell_rows.append({
                "patch_id": patch_id, "flat_index": flat, "cell_ix": int(x), "cell_iy": int(y),
                "cell_x": f"{x0 + (x + .5) * grid.cell:.3f}", "cell_y": f"{y0 + (y + .5) * grid.cell:.3f}",
                "top_z": f"{top[y, x]:.6f}", "terrain_z": f"{terrain[y, x]:.6f}", "relative_height_m": f"{top[y, x] - terrain[y, x]:.6f}",
                "local_rmse_m": f"{fields.rmse[y, x]:.9f}", "z_std_m": f"{z_std[y, x]:.9f}",
                "normal_x": f"{-fields.a[y, x] * fields.normal_z[y, x]:.12f}", "normal_y": f"{-fields.b[y, x] * fields.normal_z[y, x]:.12f}", "normal_z": f"{fields.normal_z[y, x]:.12f}",
                "preliminary_component": int(prelim_labels[y, x]), "preliminary_planar_fraction": f"{fractions.get(int(prelim_labels[y, x]), 0.0):.9f}",
            })
    return cell_rows, summary_rows


def pack_masks(masks: dict[str, np.ndarray]) -> tuple[bytes, list[str]]:
    names = list(masks)
    stacked = np.stack([masks[name].ravel() for name in names]).astype(np.uint8)
    return np.packbits(stacked, axis=1, bitorder="little").tobytes(), names


def unpack_masks(data: bytes, names: Sequence[str], shape: tuple[int, int]) -> dict[str, np.ndarray]:
    cells = shape[0] * shape[1]
    packed_width = (cells + 7) // 8
    observed = np.frombuffer(data, dtype=np.uint8)
    if observed.size != len(names) * packed_width:
        raise RuntimeError("packed mask byte count mismatch")
    observed = observed.reshape(len(names), packed_width)
    return {name: np.unpackbits(observed[index], bitorder="little")[:cells].astype(bool).reshape(shape) for index, name in enumerate(names)}


def read_task_record(record: dict[str, Any], root: Path) -> bytes:
    path = Path(record["path"])
    if path.is_symlink() or not path.is_file():
        raise RuntimeError(f"task record is not a regular non-symlink file: {path}")
    resolved = path.resolve()
    try:
        resolved.relative_to(root.resolve())
    except ValueError as error:
        raise RuntimeError("task record escapes namespace") from error
    data = resolved.read_bytes()
    if len(data) != int(record["bytes"]) or sha256_bytes(data) != record["sha256"]:
        raise RuntimeError(f"task record digest mismatch: {path}")
    return data


def task_output_records(value: Any, root: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    if isinstance(value, dict):
        if {"path", "bytes", "sha256"}.issubset(value):
            try:
                Path(value["path"]).resolve().relative_to(root.resolve())
            except (ValueError, TypeError):
                pass
            else:
                records.append(value)
        for child in value.values():
            records.extend(task_output_records(child, root))
    elif isinstance(value, list):
        for child in value:
            records.extend(task_output_records(child, root))
    return records


def validate_checkpoint_outputs(checkpoints: Checkpoints, root: Path) -> dict[str, Any]:
    expected = [
        (0, "runtime_control"),
        (10, "reference_candidate_frozen"),
        (20, "eligibility_candidate"),
        (30, "group_split_candidate"),
        (40, "claim_scope"),
        (100, "technical_summary"),
    ]
    observed = [(item["ordinal"], item["stage"]) for item in checkpoints.records]
    if observed != expected:
        raise RuntimeError(f"completed checkpoint stage set mismatch: {observed}")
    verified: dict[tuple[str, int, str], dict[str, Any]] = {}
    for ordinal, stage in expected:
        for record in task_output_records(checkpoints.payload(ordinal, stage), root):
            key = (record["path"], int(record["bytes"]), record["sha256"])
            if key not in verified:
                read_task_record(record, root)
                verified[key] = {
                    "path": record["path"],
                    "bytes": int(record["bytes"]),
                    "sha256": record["sha256"],
                }
    return {"verified_output_count": len(verified), "verified_outputs": list(verified.values())}


def validate_completed_ledger(
    ledger: dict[str, Any],
    operation_identity: dict[str, Any],
    checkpoints: Checkpoints,
    attempts: SourceAttempts,
    output_root: Path,
) -> dict[str, Any]:
    if (
        ledger.get("schema") != "jointbuildgs.gate_s0_uas_reference_coverage_execution_ledger.v1"
        or ledger.get("status") != "COMPLETED"
        or ledger.get("scientific_verdict") is not None
        or ledger.get("operation_identity") != operation_identity
        or ledger.get("checkpoints") != checkpoints.records
    ):
        raise RuntimeError("completed execution ledger envelope mismatch")
    checkpoint_validation = validate_checkpoint_outputs(checkpoints, output_root)
    current_attempts = attempts.audit({"reference_grid", "eligibility_metadata"})
    if ledger.get("source_attempts") != current_attempts:
        raise RuntimeError("completed execution ledger source-attempt audit mismatch")
    current_invocations = invocation_event_audit(output_root)
    current_invocation_keys = {
        (item["path"], int(item["bytes"]), item["sha256"])
        for item in current_invocations["records"]
    }
    ledger_invocations = ledger.get("invocation_events_at_completion", {}).get("records", [])
    if not ledger_invocations or any(
        (item.get("path"), int(item.get("bytes", -1)), item.get("sha256")) not in current_invocation_keys
        for item in ledger_invocations
    ):
        raise RuntimeError("completed execution ledger invocation-event binding mismatch")
    read_contract = ledger.get("scientific_source_read_contract", {})
    if (
        read_contract.get("per_source_read_digest_accounting") != current_attempts["per_source_read_digest_accounting"]
        or read_contract.get("separate_grid_hash_passes") != 0
        or read_contract.get("raw_source_reads") != 0
    ):
        raise RuntimeError("completed execution ledger read/digest contract mismatch")
    return {"checkpoints": checkpoint_validation, "source_attempts": current_attempts}


class StringUnion:
    def __init__(self, values: Iterable[str]):
        self.parent = {value: value for value in values}

    def find(self, value: str) -> str:
        while self.parent[value] != value:
            self.parent[value] = self.parent[self.parent[value]]
            value = self.parent[value]
        return value

    def union(self, left: str, right: str) -> None:
        a, b = self.find(left), self.find(right)
        if a != b:
            self.parent[max(a, b)] = min(a, b)


def group_graph(rows: Sequence[dict[str, Any]], patch_ids: dict[str, list[str]]) -> tuple[dict[str, str], dict[str, list[str]]]:
    ids = sorted(row["stable_id"] for row in rows)
    union = StringUnion(ids)
    by_tile: defaultdict[str, list[str]] = defaultdict(list)
    by_patch: defaultdict[str, list[str]] = defaultdict(list)
    for row in rows:
        by_tile[row["execution_tile_id"]].append(row["stable_id"])
        for patch in patch_ids.get(row["stable_id"], []):
            by_patch[patch].append(row["stable_id"])
    for values in [*by_tile.values(), *by_patch.values()]:
        ordered = sorted(values)
        for value in ordered[1:]:
            union.union(ordered[0], value)
    members: defaultdict[str, list[str]] = defaultdict(list)
    for stable_id in ids:
        members[union.find(stable_id)].append(stable_id)
    group_members = {}
    group_for_id = {}
    for values in sorted(members.values(), key=lambda item: item[0]):
        group_id = "GROUP_" + sha256_ids(values)[:16]
        group_members[group_id] = sorted(values)
        for value in values:
            group_for_id[value] = group_id
    return group_for_id, group_members


def group_quotas(group_count: int, ratios: dict[str, float], minimums: dict[str, int]) -> dict[str, int]:
    if group_count >= int(minimums["all"]):
        quotas = {split: int(minimums[split]) for split in SPLITS}
    elif group_count >= 3:
        quotas = {split: 1 for split in SPLITS}
    else:
        return {split: int(index < group_count) for index, split in enumerate(SPLITS)}
    remaining = group_count - sum(quotas.values())
    exact = {split: remaining * float(ratios[split]) for split in SPLITS}
    floors = {split: int(math.floor(exact[split])) for split in SPLITS}
    for split in SPLITS:
        quotas[split] += floors[split]
    residual = remaining - sum(floors.values())
    ranked = sorted(SPLITS, key=lambda split: (-(exact[split] - floors[split]), SPLITS.index(split)))
    for split in ranked[:residual]:
        quotas[split] += 1
    if sum(quotas.values()) != group_count:
        raise RuntimeError("group quotas do not exhaust groups")
    return quotas


def assign_group_splits(group_sizes: dict[str, int], seed: str, ratios: dict[str, float], minimums: dict[str, int]) -> tuple[dict[str, str], dict[str, int]]:
    quotas = group_quotas(len(group_sizes), ratios, minimums)
    total = sum(group_sizes.values())
    targets = {split: max(float(total) * float(ratios[split]), 1e-12) for split in SPLITS}
    assigned_members = {split: 0 for split in SPLITS}
    assigned_groups = {split: 0 for split in SPLITS}
    assignment = {}
    ordered = sorted(group_sizes, key=lambda group: (-group_sizes[group], sha256_bytes(f"{seed}|{group}".encode()), group))
    for group in ordered:
        available = [split for split in SPLITS if assigned_groups[split] < quotas[split]]
        if not available:
            raise RuntimeError("no split quota remains")
        split = min(available, key=lambda name: ((assigned_members[name] + group_sizes[group]) / targets[name], (assigned_groups[name] + 1) / max(quotas[name], 1), SPLITS.index(name)))
        assignment[group] = split
        assigned_members[split] += group_sizes[group]
        assigned_groups[split] += 1
    if assigned_groups != quotas:
        raise RuntimeError("assigned group quotas mismatch")
    return assignment, quotas


def required_pairs(q: float, delta: float, z_alpha: float, z_power: float) -> int:
    if not (0 < delta <= q <= 1) or q - delta * delta < 0:
        raise ValueError("requires 0 < delta <= q <= 1 and q - delta^2 >= 0")
    return int(math.ceil(((z_alpha * math.sqrt(q) + z_power * math.sqrt(q - delta * delta)) / delta) ** 2))


def finite_cluster_required_pairs(
    q: float,
    delta: float,
    per_contrast_alpha: float,
    desired_power: float,
    held_out_groups: int,
) -> dict[str, Any]:
    if held_out_groups < 2:
        return {
            "held_out_groups": held_out_groups,
            "degrees_of_freedom": max(held_out_groups - 1, 0),
            "critical_value": None,
            "required_effective_pairs": 2**31 - 1,
        }
    degrees = held_out_groups - 1
    critical = float(stats.t.ppf(1.0 - per_contrast_alpha / 2.0, degrees))
    power_quantile = float(stats.norm.ppf(desired_power))
    return {
        "held_out_groups": held_out_groups,
        "degrees_of_freedom": degrees,
        "critical_value": critical,
        "required_effective_pairs": required_pairs(q, delta, critical, power_quantile),
    }


def effective_size(sizes: Sequence[int], rho: float) -> dict[str, float]:
    n = int(sum(sizes))
    if n == 0:
        return {"n": 0, "groups": 0, "sum_sq": 0, "design_effect": float("inf"), "n_eff": 0.0, "largest_group": 0}
    sum_sq = int(sum(value * value for value in sizes))
    design = 1.0 + (sum_sq / n - 1.0) * rho
    return {"n": n, "groups": len(sizes), "sum_sq": sum_sq, "design_effect": design, "n_eff": n / design, "largest_group": max(sizes)}


def claim_scope(all_sizes: Sequence[int], held_sizes: Sequence[int], split_group_counts: dict[str, int], config: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    power = config["power"]
    rows = []
    metrics = {}
    for scope, sizes in (("all_e_paired", all_sizes), ("held_out", held_sizes)):
        metrics[scope] = {}
        for rho in power["rho_values"]:
            result = effective_size(sizes, float(rho))
            metrics[scope][str(rho)] = result
            rows.append({"scope": scope, "rho": f"{float(rho):.2f}", **{key: f"{value:.9f}" if isinstance(value, float) else value for key, value in result.items()}})
    primary_key = str(power["primary_rho"])
    all_primary, held_primary = metrics["all_e_paired"][primary_key], metrics["held_out"][primary_key]
    minima = config["eligibility"]["minimum_groups"]
    group_caps = config["eligibility"]["largest_group_fraction_max"]
    overall_ok = (
        all_primary["groups"] >= int(minima["all"])
        and split_group_counts.get("development", 0) >= int(minima["development"])
        and split_group_counts.get("validation", 0) >= int(minima["validation"])
        and split_group_counts.get("held_out", 0) >= int(minima["held_out"])
        and int(all_primary["largest_group"]) <= float(group_caps["all"]) * int(all_primary["n"]) + 1e-12
    )
    held_ok = (
        held_primary["groups"] >= int(minima["held_out"])
        and int(held_primary["largest_group"]) <= float(group_caps["held_out"]) * int(held_primary["n"]) + 1e-12
    )
    confirmatory_group_ok = held_primary["groups"] >= int(power["minimum_held_out_groups_for_confirmatory_inference"])
    achieved_main = finite_cluster_required_pairs(
        float(power["primary_discordance_rate"]),
        0.15,
        float(power["per_contrast_two_sided_alpha"]),
        float(power["desired_power"]),
        int(held_primary["groups"]),
    )
    achieved_large = finite_cluster_required_pairs(
        float(power["primary_discordance_rate"]),
        0.20,
        float(power["per_contrast_two_sided_alpha"]),
        float(power["desired_power"]),
        int(held_primary["groups"]),
    )
    if overall_ok and held_ok and confirmatory_group_ok and held_primary["n_eff"] >= int(achieved_main["required_effective_pairs"]):
        status = "CONFIRMATORY_MAIN_CLAIM_CANDIDATE"
    elif overall_ok and held_ok and confirmatory_group_ok and held_primary["n_eff"] >= int(achieved_large["required_effective_pairs"]):
        status = "CONFIRMATORY_LARGE_EFFECT_ONLY_CANDIDATE"
    elif overall_ok and all_primary["n_eff"] >= int(power["asymptotic_large_effect_n_eff"]):
        status = "DESCRIPTIVE_CENSUS_ONLY"
    else:
        status = "PILOT_ONLY_REFERENCE_SCOPE"
    requirements = [{"discordance": q, "net_effect": delta, "required_pairs": required_pairs(float(q), float(delta), float(power["z_alpha"]), float(power["z_power"]))} for q in power["discordance_rates"] for delta in power["net_effects"]]
    finite_sensitivity = [
        {
            "discordance": q,
            "net_effect": delta,
            **finite_cluster_required_pairs(
                float(q),
                float(delta),
                float(power["per_contrast_two_sided_alpha"]),
                float(power["desired_power"]),
                groups,
            ),
        }
        for groups in power["held_out_group_sensitivity"]
        for q in power["discordance_rates"]
        for delta in power["net_effects"]
    ]
    return {
        "status": status,
        "overall_group_criteria_pass": overall_ok,
        "held_out_group_criteria_pass": held_ok,
        "confirmatory_minimum_held_out_groups_pass": confirmatory_group_ok,
        "finite_cluster_method": power["finite_cluster_critical_value"],
        "achieved_held_out_main_requirement": achieved_main,
        "achieved_held_out_large_effect_requirement": achieved_large,
        "metrics": metrics,
        "requirements": requirements,
        "finite_cluster_requirement_sensitivity": finite_sensitivity,
        "split_group_counts": split_group_counts,
        "scientific_verdict": None,
    }, rows


def inside_bbox(x: float, y: float, row: dict[str, Any]) -> bool:
    return float(row["bbox_min_x"]) <= x <= float(row["bbox_max_x"]) and float(row["bbox_min_y"]) <= y <= float(row["bbox_max_y"])


def stage_building_counts(rows: Sequence[dict[str, Any]], masks: dict[str, np.ndarray], bbox: tuple[float, float, float, float], cell: float, minimum: int) -> dict[str, int]:
    x0, y0, _, _ = bbox
    output = {}
    for name, mask in masks.items():
        iy, ix = np.nonzero(mask)
        points = list(zip((x0 + (ix + .5) * cell).tolist(), (y0 + (iy + .5) * cell).tolist()))
        count = 0
        for row in rows:
            if sum(inside_bbox(x, y, row) for x, y in points) >= minimum:
                count += 1
        output[name] = count
    return output


def expected_stage_counts() -> dict[str, int]:
    return {"raw_observed": 129, "minimum_points": 129, "height": 124, "z_std": 124, "neighbors": 124, "plane_rmse": 96, "normal": 96, "roughness": 94, "preliminary_component_size": 89, "baseline_planar_fraction": 12, "baseline_final": 10, "diagnostic_final": 72}


def run_preflight(source_commit: str) -> dict[str, Any]:
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    contract = assert_git_contract(source_commit, strict_refs=False, require_clean=True)
    if config["segmentation"]["method"] != "DETERMINISTIC_LOCAL_PLANE_PATCH_KRUSKAL_v1" or config["segmentation"]["edge_revisit"] is not False:
        raise RuntimeError("segmentation proposal contract mismatch")
    observed = {(q, delta): required_pairs(q, delta, config["power"]["z_alpha"], config["power"]["z_power"]) for q in config["power"]["discordance_rates"] for delta in config["power"]["net_effects"]}
    expected = {(0.2, 0.15): 82, (0.2, 0.2): 45, (0.3, 0.15): 125, (0.3, 0.2): 69, (0.4, 0.15): 167, (0.4, 0.2): 93}
    if observed != expected:
        raise RuntimeError(f"power contract mismatch: {observed}")
    result = {"status": "PASS_ZERO_SCIENTIFIC_PAYLOAD", "git": contract, "power_requirements": {f"{q}:{delta}": value for (q, delta), value in observed.items()}, "scientific_payload_bytes_read_or_hashed": 0, "scientific_verdict": None}
    print(json.dumps(result, sort_keys=True))
    return result


def execute(source_commit: str, artifact_root: Path, project_image_id: str) -> dict[str, Any]:
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    if artifact_root.resolve().as_posix() != config["artifact_root"]:
        raise RuntimeError("artifact root mismatch")
    git_contract = assert_git_contract(source_commit, strict_refs=True, require_clean=True, include_receipt=True)
    acceptance = validate_acceptance(source_commit, artifact_root, config)
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", project_image_id) or project_image_id != acceptance["project_image_id"]:
        raise RuntimeError("executing project image ID does not match accepted image ID")
    if current_blob(REPO / config["inputs"]["frozen_config_git_path"]) != config["inputs"]["frozen_config_git_blob"]:
        raise RuntimeError("frozen predecessor config Git blob mismatch")
    output_root = artifact_root / config["output_namespace"]
    output_root.mkdir(parents=True, exist_ok=True)
    recovered = recover_pending(output_root)
    operation_contract = {"task_id": TASK, "handoff_id": HANDOFF, "source_commit": source_commit, "inputs": input_specs(config), "config_blob": current_blob(CONFIG_PATH), "algorithm": config["segmentation"], "power": config["power"], "project_image_id": acceptance["project_image_id"]}
    operation_id = sha256_bytes(canonical_json_bytes(operation_contract))
    checkpoints = Checkpoints(output_root, operation_id)
    attempts = SourceAttempts(output_root, operation_id, int(config["cost_caps"]["retry_max"]))
    invocation = append_invocation_event(
        output_root,
        "execute",
        {"source_commit": source_commit, "operation_id": operation_id, "recovered_pending": recovered},
    )
    completed_path = output_root / "control/execution_ledger_v1.json"
    if completed_path.is_file():
        if completed_path.is_symlink():
            raise RuntimeError("completed execution ledger is a symlink")
        ledger = json.loads(completed_path.read_bytes())
        validate_completed_ledger(
            ledger,
            {**operation_contract, "operation_id": operation_id},
            checkpoints,
            attempts,
            output_root,
        )
        summary = json.loads(read_task_record(checkpoints.payload(100, "technical_summary")["summary"], output_root))
        print(json.dumps({"status": "REUSED_COMPLETED_LEDGER", "operation_id": operation_id, "invocation": invocation, "scientific_source_reopens": 0, "claim_scope": summary["claim_scope_status"]}, sort_keys=True))
        return summary
    if not checkpoints.completed(0, "runtime_control"):
        started = {"schema": "jointbuildgs.gate_s0_uas_reference_coverage_started.v1", "operation_identity": {**operation_contract, "operation_id": operation_id}, "git": git_contract, "acceptance": acceptance, "recovered_pending": recovered, "scientific_verdict": None}
        started_record = add_once_json(output_root / "control/started_v1.json", started)
        checkpoints.write(0, "runtime_control", {"started": started_record})

    if checkpoints.completed(10, "reference_candidate_frozen"):
        reference_payload = checkpoints.payload(10, "reference_candidate_frozen")
    else:
        grid_spec, checkpoint_spec = config["inputs"]["grid"], config["inputs"]["source_checkpoint"]
        attempt = attempts.start("reference_grid", [{"path": grid_spec["path"], "accepted_bytes": grid_spec["bytes"], "accepted_sha256": grid_spec["sha256"]}, {"path": checkpoint_spec["path"], "accepted_bytes": checkpoint_spec["bytes"], "accepted_sha256": checkpoint_spec["sha256"]}])
        checkpoint_bytes, checkpoint_input = capture_exact(artifact_root / checkpoint_spec["path"], checkpoint_spec)
        checkpoint_body = json.loads(checkpoint_bytes)
        if checkpoint_body.get("ordinal") != 50 or checkpoint_body.get("stage") != "c1_reference_frozen_pre_c5" or checkpoint_body.get("scientific_verdict") is not None:
            raise RuntimeError("source checkpoint semantic mismatch")
        grid_bytes, grid_input = capture_exact(artifact_root / grid_spec["path"], grid_spec)
        grid = load_grid_from_bytes(grid_bytes, config)
        masks, fields, terrain, fractions = compute_masks(grid, config)
        segmentation = segment_patches(masks["roughness"], grid.max_z.reshape(grid.ny, grid.nx), fields, config)
        cell_rows, summary_rows = patch_outputs(grid, masks, fields, terrain, fractions, segmentation, config)
        replay_segmentation = segment_patches(masks["roughness"], grid.max_z.reshape(grid.ny, grid.nx), fields, config)
        replay_cells, replay_summaries = patch_outputs(grid, masks, fields, terrain, fractions, replay_segmentation, config)
        if (
            canonical_json_bytes(segmentation["patches"]) != canonical_json_bytes(replay_segmentation["patches"])
            or canonical_csv_bytes(list(cell_rows[0]) if cell_rows else [], cell_rows)
            != canonical_csv_bytes(list(replay_cells[0]) if replay_cells else [], replay_cells)
            or canonical_csv_bytes(list(summary_rows[0]) if summary_rows else [], summary_rows)
            != canonical_csv_bytes(list(replay_summaries[0]) if replay_summaries else [], replay_summaries)
        ):
            raise RuntimeError("in-memory exact-dataset segmentation replay is not byte-identical")
        cell_record = add_once_csv(output_root / "reference/reference_candidate_cells_v1.csv", list(cell_rows[0]) if cell_rows else [], cell_rows)
        patch_record = add_once_csv(output_root / "reference/patch_summary_v1.csv", list(summary_rows[0]) if summary_rows else [], summary_rows)
        mask_bytes, mask_names = pack_masks(masks)
        mask_record = add_once_bytes(output_root / "reference/stage_masks_v1.bin", mask_bytes)
        reference_payload = {
            "attempt": attempt, "source_checkpoint_input": checkpoint_input, "grid_input": grid_input,
            "grid_known_successful_full_content_read_and_digest_passes": 1, "separate_grid_hash_passes": 0,
            "mask_names": mask_names, "mask_shape": [grid.ny, grid.nx], "stage_masks": mask_record,
            "candidate_cells": cell_record, "patch_summary": patch_record,
            "algorithm": config["segmentation"], "algorithm_namespace_sha256": segmentation["namespace_sha256"],
            "planar_cells": int(np.count_nonzero(masks["roughness"])), "patch_count": len(segmentation["patches"]), "patch_cell_count": len(cell_rows),
            "patch_membership_frozen_before_candidate_association": True,
            "in_memory_exact_dataset_algorithm_replays": 1,
            "byte_identical_replay": True,
            "raw_uas_reads": 0, "threshold_sweeps": 0, "candidate_count_targeting": False,
        }
        checkpoints.write(10, "reference_candidate_frozen", reference_payload)

    if checkpoints.completed(20, "eligibility_candidate"):
        eligibility_payload = checkpoints.payload(20, "eligibility_candidate")
    else:
        spec = config["inputs"]["eligibility"]
        attempt = attempts.start("eligibility_metadata", [{"path": spec["path"], "accepted_bytes": spec["bytes"], "accepted_sha256": spec["sha256"]}])
        eligibility_bytes, eligibility_input = capture_exact(artifact_root / spec["path"], spec)
        rows = list(csv.DictReader(io.StringIO(eligibility_bytes.decode("utf-8"), newline="")))
        if len(rows) != int(config["aoi"]["candidate_count"]) or sha256_ids(row["stable_id"] for row in rows) != config["aoi"]["candidate_id_set_sha256"]:
            raise RuntimeError("canonical eligibility candidate set mismatch")
        mask_data = read_task_record(reference_payload["stage_masks"], output_root)
        masks = unpack_masks(mask_data, reference_payload["mask_names"], tuple(reference_payload["mask_shape"]))
        stage_counts = stage_building_counts(rows, masks, tuple(config["aoi"]["bbox"]), float(config["aoi"]["cell_m"]), int(config["eligibility"]["minimum_condition_cells"]))
        if stage_counts != expected_stage_counts():
            raise RuntimeError(f"baseline attrition mismatch: {stage_counts}")
        attrition_rows = [{"stage": stage, "buildings_with_minimum_score_cells": stage_counts[stage]} for stage in masks]
        attrition_record = add_once_csv(output_root / "reference/baseline_attrition_v1.csv", list(attrition_rows[0]), attrition_rows)
        cell_rows = list(csv.DictReader(io.StringIO(read_task_record(reference_payload["candidate_cells"], output_root).decode("utf-8"), newline="")))
        cells_by_patch: defaultdict[str, list[tuple[float, float]]] = defaultdict(list)
        for item in cell_rows:
            cells_by_patch[item["patch_id"]].append((float(item["cell_x"]), float(item["cell_y"])))
        patch_ids_by_building: dict[str, list[str]] = {}
        score_cells_by_building: dict[str, int] = {}
        patch_building_counts: Counter[str] = Counter()
        patch_eligible_counts: Counter[str] = Counter()
        output_rows = []
        for row in rows:
            patch_counts = {patch: sum(inside_bbox(x, y, row) for x, y in points) for patch, points in cells_by_patch.items()}
            patch_counts = {patch: count for patch, count in patch_counts.items() if count > 0}
            patches = sorted(patch_counts)
            score = int(sum(patch_counts.values()))
            patch_ids_by_building[row["stable_id"]] = patches
            score_cells_by_building[row["stable_id"]] = score
            for patch in patches:
                patch_building_counts[patch] += 1
            eligible = (
                row["u_target"] == "true"
                and int(row["current_image_view_support"]) >= int(config["eligibility"]["minimum_image_views"])
                and score >= int(config["eligibility"]["minimum_condition_cells"])
                and int(row["mvs_support_cells"]) >= int(config["eligibility"]["minimum_condition_cells"])
                and int(row["c4_support_cells"]) >= int(config["eligibility"]["minimum_condition_cells"])
                and row["c5_prior_available_by_stable_id"] == "true" and row["c5_input_alignment_ready"] == "true"
            )
            if eligible:
                for patch in patches:
                    patch_eligible_counts[patch] += 1
            output_rows.append({**row, "reference_candidate_score_cells": score, "reference_candidate_patch_ids": ";".join(patches), "e_paired_candidate": str(eligible).lower(), "candidate_exclusion_reason": "" if eligible else ";".join(reason for condition, reason in ((row["u_target"] != "true" or int(row["current_image_view_support"]) < int(config["eligibility"]["minimum_image_views"]), "LT_2_IMAGE_VIEWS"), (score < 4, "INSUFFICIENT_INDEPENDENT_UAS_REFERENCE_SUPPORT"), (int(row["mvs_support_cells"]) < 4, "INSUFFICIENT_MVS_SUPPORT"), (int(row["c4_support_cells"]) < 4, "INSUFFICIENT_C4_SUPPORT"), (row["c5_prior_available_by_stable_id"] != "true", "C5_PRIOR_MISSING"), (row["c5_input_alignment_ready"] != "true", "C5_ALIGNMENT_MISSING")) if condition)})
        eligibility_record = add_once_csv(output_root / "freeze/eligibility_candidate_v1.csv", list(output_rows[0]), output_rows)
        association_rows = [{"patch_id": patch, "canonical_buildings_with_score_cells": patch_building_counts[patch], "eligible_buildings_with_score_cells": patch_eligible_counts[patch], "multi_building": str(patch_building_counts[patch] > 1).lower()} for patch in sorted(cells_by_patch)]
        association_record = add_once_csv(output_root / "reference/patch_association_qa_v1.csv", list(association_rows[0]) if association_rows else [], association_rows)
        eligibility_payload = {"attempt": attempt, "eligibility_input": eligibility_input, "baseline_attrition": attrition_record, "baseline_counts": stage_counts, "eligibility": eligibility_record, "patch_association_qa": association_record, "candidate_count": len(output_rows), "e_paired_candidate_count": sum(row["e_paired_candidate"] == "true" for row in output_rows), "patch_ids_by_building": patch_ids_by_building}
        checkpoints.write(20, "eligibility_candidate", eligibility_payload)

    if checkpoints.completed(30, "group_split_candidate"):
        group_payload = checkpoints.payload(30, "group_split_candidate")
    else:
        output_rows = list(csv.DictReader(io.StringIO(read_task_record(eligibility_payload["eligibility"], output_root).decode("utf-8"), newline="")))
        patch_ids = {row["stable_id"]: row["reference_candidate_patch_ids"].split(";") if row["reference_candidate_patch_ids"] else [] for row in output_rows}
        group_for_id, group_members = group_graph(output_rows, patch_ids)
        eligible_ids = {row["stable_id"] for row in output_rows if row["e_paired_candidate"] == "true"}
        group_sizes = {group: sum(value in eligible_ids for value in members) for group, members in group_members.items()}
        eligible_group_sizes = {group: size for group, size in group_sizes.items() if size > 0}
        assignment, quotas = assign_group_splits(eligible_group_sizes, config["eligibility"]["split_seed"], config["eligibility"]["split_ratios"], config["eligibility"]["minimum_groups"])
        graph_rows = [{"stable_id": row["stable_id"], "group_id": group_for_id[row["stable_id"]], "group_all_member_count": len(group_members[group_for_id[row["stable_id"]]]), "group_eligible_member_count": group_sizes[group_for_id[row["stable_id"]]], "execution_tile_id": row["execution_tile_id"], "shared_patch_ids": row["reference_candidate_patch_ids"], "e_paired_candidate": row["e_paired_candidate"]} for row in output_rows]
        split_rows = [{"stable_id": row["stable_id"], "group_id": group_for_id[row["stable_id"]], "split": assignment[group_for_id[row["stable_id"]]]} for row in output_rows if row["e_paired_candidate"] == "true"]
        split_for_id = {row["stable_id"]: row["split"] for row in split_rows}
        predecessor_names = {
            "e_paired": "predecessor_e_paired",
            "spatial_group_id": "predecessor_spatial_group_id",
            "split": "predecessor_split",
            "held_out_accessed": "predecessor_held_out_accessed",
            "exclusion_reason": "predecessor_exclusion_reason",
        }
        candidate_rows = []
        for row in output_rows:
            renamed = {predecessor_names.get(key, key): value for key, value in row.items()}
            renamed.update(
                {
                    "candidate_group_id": group_for_id[row["stable_id"]],
                    "candidate_split": split_for_id.get(row["stable_id"], "NOT_E_PAIRED"),
                    "held_out_outcome_accessed": "false",
                }
            )
            candidate_rows.append(renamed)
        graph_record = add_once_csv(output_root / "freeze/group_graph_v1.csv", list(graph_rows[0]), graph_rows)
        split_record = add_once_csv(output_root / "freeze/split_candidate_v1.csv", list(split_rows[0]) if split_rows else [], split_rows)
        candidate_record = add_once_csv(output_root / "freeze/candidate_ledger_v1.csv", list(candidate_rows[0]), candidate_rows)
        split_id_digests = {
            split: sha256_ids(row["stable_id"] for row in split_rows if row["split"] == split)
            for split in SPLITS
        }
        group_payload = {
            "group_graph": graph_record,
            "split_candidate": split_record,
            "candidate_ledger": candidate_record,
            "group_count": len(eligible_group_sizes),
            "group_quotas": quotas,
            "split_group_counts": dict(Counter(assignment.values())),
            "split_building_counts": dict(Counter(row["split"] for row in split_rows)),
            "split_id_set_sha256": split_id_digests,
            "e_paired_candidate_id_set_sha256": sha256_ids(eligible_ids),
            "group_sizes": eligible_group_sizes,
            "assignment": assignment,
            "all_199_nodes_in_graph": len(graph_rows) == 199,
            "c5_geometry_or_old_overlap_used": False,
        }
        checkpoints.write(30, "group_split_candidate", group_payload)

    if checkpoints.completed(40, "claim_scope"):
        claim_payload = checkpoints.payload(40, "claim_scope")
    else:
        split_rows = list(csv.DictReader(io.StringIO(read_task_record(group_payload["split_candidate"], output_root).decode("utf-8"), newline="")))
        all_sizes = list(group_payload["group_sizes"].values())
        held_counts = Counter(row["group_id"] for row in split_rows if row["split"] == "held_out")
        claim, power_rows = claim_scope(all_sizes, list(held_counts.values()), group_payload["split_group_counts"], config)
        power_record = add_once_csv(output_root / "analysis/power_sensitivity_v1.csv", list(power_rows[0]), power_rows)
        requirement_rows = [
            {
                "basis": "ASYMPTOTIC_Z",
                "held_out_groups": "",
                "degrees_of_freedom": "",
                "critical_value": f"{float(config['power']['z_alpha']):.12f}",
                "discordance_rate": f"{float(item['discordance']):.2f}",
                "net_effect": f"{float(item['net_effect']):.2f}",
                "required_effective_pairs": item["required_pairs"],
            }
            for item in claim["requirements"]
        ]
        requirement_rows.extend(
            {
                "basis": "STUDENT_T_HELD_OUT_GROUPS_MINUS_1",
                "held_out_groups": item["held_out_groups"],
                "degrees_of_freedom": item["degrees_of_freedom"],
                "critical_value": f"{float(item['critical_value']):.12f}",
                "discordance_rate": f"{float(item['discordance']):.2f}",
                "net_effect": f"{float(item['net_effect']):.2f}",
                "required_effective_pairs": item["required_effective_pairs"],
            }
            for item in claim["finite_cluster_requirement_sensitivity"]
        )
        requirement_record = add_once_csv(
            output_root / "analysis/pair_requirements_v1.csv",
            list(requirement_rows[0]),
            requirement_rows,
        )
        claim_record = add_once_json(output_root / "analysis/claim_scope_v1.json", claim)
        claim_payload = {
            "claim_scope": claim_record,
            "power_sensitivity": power_record,
            "pair_requirements": requirement_record,
            "status": claim["status"],
            "requirements": claim["requirements"],
        }
        checkpoints.write(40, "claim_scope", claim_payload)

    if checkpoints.completed(100, "technical_summary"):
        summary = json.loads(read_task_record(checkpoints.payload(100, "technical_summary")["summary"], output_root))
    else:
        claim_body = json.loads(read_task_record(claim_payload["claim_scope"], output_root))
        primary_rho_key = str(config["power"]["primary_rho"])
        gate_action = (
            "REFERENCE_SPLIT_CANDIDATE_FOR_HUMAN_GATE_REVIEW"
            if claim_payload["status"] in {"CONFIRMATORY_MAIN_CLAIM_CANDIDATE", "CONFIRMATORY_LARGE_EFFECT_ONLY_CANDIDATE"}
            else "BLOCKED_REFERENCE_COVERAGE_OR_INDEPENDENCE"
        )
        source_attempt_audit = attempts.audit({"reference_grid", "eligibility_metadata"})
        invocation_audit = invocation_event_audit(output_root)
        grid_accounting = next(
            item
            for item in source_attempt_audit["per_source_read_digest_accounting"]
            if item["path"] == config["inputs"]["grid"]["path"]
        )
        summary = {
            "schema": "jointbuildgs.gate_s0_uas_reference_coverage_summary.v1", "task_id": TASK, "handoff_id": HANDOFF,
            "operation_id": operation_id, "source_commit": source_commit, "status": "TECHNICAL_EXECUTION_COMPLETE",
            "project_image_id": project_image_id,
            "algorithm": config["segmentation"], "input_grid_bytes": config["inputs"]["grid"]["bytes"],
            "input_grid_known_successful_full_read_digest_passes": grid_accounting["known_successful_full_read_digest_passes"],
            "input_grid_prior_unknown_attempts": grid_accounting["prior_unknown_attempts"],
            "input_grid_full_read_digest_passes_min": grid_accounting["full_read_digest_passes_min"],
            "input_grid_full_read_digest_passes_max": grid_accounting["full_read_digest_passes_max"],
            "source_read_digest_accounting": source_attempt_audit["per_source_read_digest_accounting"],
            "invocation_events_at_summary": len(invocation_audit["records"]),
            "recovered_pending_events_at_summary": invocation_audit["recovered_pending_event_count"],
            "raw_uas_reads": 0,
            "baseline_counts": eligibility_payload["baseline_counts"], "patch_count": reference_payload["patch_count"], "patch_cell_count": reference_payload["patch_cell_count"],
            "u_target_count": 199, "e_paired_candidate_count": eligibility_payload["e_paired_candidate_count"],
            "e_paired_candidate_id_set_sha256": group_payload["e_paired_candidate_id_set_sha256"],
            "independent_group_count": group_payload["group_count"], "split_group_counts": group_payload["split_group_counts"],
            "split_building_counts": group_payload["split_building_counts"],
            "split_id_set_sha256": group_payload["split_id_set_sha256"],
            "claim_scope_status": claim_payload["status"], "performance_or_held_out_outcomes_accessed": False,
            "primary_rho": config["power"]["primary_rho"],
            "all_e_paired_primary_effective_size": claim_body["metrics"]["all_e_paired"][primary_rho_key],
            "held_out_primary_effective_size": claim_body["metrics"]["held_out"][primary_rho_key],
            "overall_group_criteria_pass": claim_body["overall_group_criteria_pass"],
            "held_out_group_criteria_pass": claim_body["held_out_group_criteria_pass"],
            "confirmatory_minimum_held_out_groups_pass": claim_body["confirmatory_minimum_held_out_groups_pass"],
            "recommended_gate_action": gate_action,
            "inference_population": "ACHIEVED_FROZEN_REFERENCE_COVERED_E_PAIRED_NOT_ALL_U_TARGET",
            "reference_planarity_attrition_is_selection_limitation": True,
            "guards": config["guards"], "gate_decision": None, "scientific_verdict": None,
        }
        summary_record = add_once_json(output_root / "freeze/technical_summary_v1.json", summary)
        checkpoints.write(100, "technical_summary", {"summary": summary_record})
    source_attempt_audit = attempts.audit({"reference_grid", "eligibility_metadata"})
    invocation_audit = invocation_event_audit(output_root)
    ledger = {
        "schema": "jointbuildgs.gate_s0_uas_reference_coverage_execution_ledger.v1",
        "status": "COMPLETED",
        "operation_identity": {**operation_contract, "operation_id": operation_id},
        "checkpoints": checkpoints.records,
        "source_attempts": source_attempt_audit,
        "invocation_events_at_completion": invocation_audit,
        "scientific_source_read_contract": {
            "per_source_read_digest_accounting": source_attempt_audit["per_source_read_digest_accounting"],
            "separate_grid_hash_passes": 0,
            "raw_source_reads": 0,
        },
        "scientific_verdict": None,
    }
    add_once_json(completed_path, ledger)
    print(json.dumps(summary, sort_keys=True))
    return summary


def promote(artifact_root: Path) -> dict[str, Any]:
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    output_root = artifact_root.resolve() / config["output_namespace"]
    recovered_external_pending = recover_pending(output_root)
    recovered_promotion_pending = recover_selected_pending(
        PROMOTION_PATHS,
        output_root / "control/promotion_abandoned_pending",
    )
    append_invocation_event(
        output_root,
        "promote",
        {"recovered_pending": [*recovered_external_pending, *recovered_promotion_pending]},
    )
    ledger_path = output_root / "control/execution_ledger_v1.json"
    if ledger_path.is_symlink() or not ledger_path.is_file():
        raise RuntimeError("regular non-symlink execution ledger required for promotion")
    ledger = json.loads(ledger_path.read_bytes())
    source_commit = ledger.get("operation_identity", {}).get("source_commit")
    if not isinstance(source_commit, str):
        raise RuntimeError("execution ledger source commit missing")
    promotion_git = assert_git_contract(source_commit, strict_refs=True, require_clean=False, include_receipt=True)
    allowed_dirty = {path.relative_to(REPO).as_posix() for path in PROMOTION_PATHS}
    preexisting_dirty = {
        line[3:].replace("\\", "/")
        for line in git("status", "--porcelain=v1", "--untracked-files=all").splitlines()
        if line
    }
    if not preexisting_dirty.issubset(allowed_dirty):
        raise RuntimeError(f"promotion has unrelated dirty paths: {sorted(preexisting_dirty)}")
    promotion_acceptance = validate_acceptance(source_commit, artifact_root.resolve(), config)
    operation_id = ledger["operation_identity"]["operation_id"]
    checkpoints = Checkpoints(output_root, operation_id)
    attempts = SourceAttempts(output_root, operation_id, int(config["cost_caps"]["retry_max"]))
    completed_validation = validate_completed_ledger(
        ledger,
        ledger["operation_identity"],
        checkpoints,
        attempts,
        output_root,
    )
    summary_bytes = read_task_record(checkpoints.payload(100, "technical_summary")["summary"], output_root)
    summary = json.loads(summary_bytes)
    reference_payload = checkpoints.payload(10, "reference_candidate_frozen")
    eligibility_payload = checkpoints.payload(20, "eligibility_candidate")
    group_payload = checkpoints.payload(30, "group_split_candidate")
    claim_payload = checkpoints.payload(40, "claim_scope")
    promoted_sources = {
        "eligibility": eligibility_payload["eligibility"],
        "candidate_ledger": group_payload["candidate_ledger"],
        "group_graph": group_payload["group_graph"],
        "split_candidate": group_payload["split_candidate"],
        "claim_scope": claim_payload["claim_scope"],
        "power_sensitivity": claim_payload["power_sensitivity"],
        "pair_requirements": claim_payload["pair_requirements"],
        "patch_summary": reference_payload["patch_summary"],
        "patch_association_qa": eligibility_payload["patch_association_qa"],
        "baseline_attrition": eligibility_payload["baseline_attrition"],
    }
    promoted_bytes = {
        name: read_task_record(record, output_root)
        for name, record in promoted_sources.items()
    }
    ledger_bytes = (output_root / "control/execution_ledger_v1.json").read_bytes()
    manifest = {
        **summary,
        "schema": "jointbuildgs.gate_s0_uas_reference_coverage_technical_candidate_manifest.v1",
        "execution_ledger": {
            "path": "control/execution_ledger_v1.json",
            "bytes": len(ledger_bytes),
            "sha256": sha256_bytes(ledger_bytes),
        },
        "promotion_git_contract": {
            key: promotion_git[key]
            for key in ("source_commit", "head", "origin_main", "blobs")
        },
        "promotion_acceptance": promotion_acceptance,
        "completed_state_validation": completed_validation,
        "external_artifact_records": {
            "candidate_cells": reference_payload["candidate_cells"],
            **promoted_sources,
        },
        "promoted_copy_digests": {
            name: {"bytes": len(data), "sha256": sha256_bytes(data)}
            for name, data in promoted_bytes.items()
        },
        "scientific_verdict": None,
    }
    report = f"""# Gate S0 independent-UAS reference coverage R1 technical report

- task: `{TASK}`
- technical status: `TECHNICAL_EXECUTION_COMPLETE`
- reference candidate: `{summary['e_paired_candidate_count']}` of 199 buildings
- independent groups: `{summary['independent_group_count']}`
- claim scope: `{summary['claim_scope_status']}`
- recommended Gate action: `{summary['recommended_gate_action']}`
- Gate S0 decision: `null`
- scientific_verdict: `null`

The exact checkpointed 3,023,643-byte UAS grid had one known-successful same-stream
read/digest pass. Total passes are bounded by the recorded minimum
`{summary['input_grid_full_read_digest_passes_min']}` and maximum
`{summary['input_grid_full_read_digest_passes_max']}`; any pre-checkpoint crash attempt
is reported explicitly rather than counted as a known complete pass. Raw UAS,
common-base, ALS, C5 JSONL, LoD2, held-out outcomes and performance results were not
accessed. `DETERMINISTIC_LOCAL_PLANE_PATCH_KRUSKAL_v1` retained every frozen per-cell
guard and used its single precommitted patch proposal without a sweep or count target.

The candidate and its full tile/shared-patch grouping, patch QA, held-out-only power
and descriptive-census sensitivity remain technical evidence for a later human Gate.
This report does not authorize P2 performance or make a scientific verdict.

Any future confirmatory interpretation is limited to the achieved frozen,
reference-covered `E_paired` population; it does not generalize automatically to all
199 `U_target` buildings. Independent-reference planarity attrition is an explicit
selection limitation.
""".encode()
    destinations = {
        "eligibility": DOC_ROOT / "eligibility_candidate_v1.csv",
        "candidate_ledger": DOC_ROOT / "candidate_ledger_v1.csv",
        "group_graph": DOC_ROOT / "group_graph_v1.csv",
        "split_candidate": DOC_ROOT / "split_candidate_v1.csv",
        "claim_scope": DOC_ROOT / "claim_scope_v1.json",
        "power_sensitivity": DOC_ROOT / "power_sensitivity_v1.csv",
        "pair_requirements": DOC_ROOT / "pair_requirements_v1.csv",
        "patch_summary": DOC_ROOT / "patch_summary_v1.csv",
        "patch_association_qa": DOC_ROOT / "patch_association_qa_v1.csv",
        "baseline_attrition": DOC_ROOT / "baseline_attrition_v1.csv",
    }
    records = {"manifest": add_repo_once(MANIFEST_PATH, canonical_json_bytes(manifest))}
    records.update(
        {
            name: add_repo_once(destinations[name], promoted_bytes[name])
            for name in destinations
        }
    )
    records["report"] = add_repo_once(DOC_ROOT / "UAS_REFERENCE_COVERAGE_R1_REPORT_v1.md", report)
    if tuple(path for path in PROMOTION_PATHS if not path.is_file()):
        raise RuntimeError("promoted output path contract incomplete")
    observed_dirty = {
        line[3:].replace("\\", "/")
        for line in git("status", "--porcelain=v1", "--untracked-files=all").splitlines()
        if line
    }
    if not observed_dirty or not observed_dirty.issubset(allowed_dirty):
        raise RuntimeError(f"promotion dirty-path contract mismatch: {sorted(observed_dirty)}")
    print(json.dumps(records, sort_keys=True))
    return records


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", required=True, choices=("preflight", "acceptance-metadata", "execute", "promote"))
    parser.add_argument("--source-commit")
    parser.add_argument("--artifact-root", type=Path)
    parser.add_argument("--project-image-id")
    args = parser.parse_args()
    if args.mode == "preflight":
        if not args.source_commit:
            parser.error("preflight requires --source-commit")
        run_preflight(args.source_commit)
    elif args.mode == "acceptance-metadata":
        if not args.source_commit or args.artifact_root is None or not args.project_image_id:
            parser.error("acceptance-metadata requires --source-commit, --artifact-root and --project-image-id")
        acceptance_metadata(args.source_commit, args.artifact_root, args.project_image_id)
    elif args.mode == "execute":
        if not args.source_commit or args.artifact_root is None or not args.project_image_id:
            parser.error("execute requires --source-commit, --artifact-root and --project-image-id")
        execute(args.source_commit, args.artifact_root, args.project_image_id)
    else:
        if args.artifact_root is None:
            parser.error("promote requires --artifact-root")
        promote(args.artifact_root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
