#!/usr/bin/env python3
"""Crash-persistent, minimal-read Gate S0 freeze recovery.

The executor has three deliberately separate modes:

* ``preflight`` verifies committed code and synthetic dependency paths without
  opening scientific payload content.
* ``execute`` consumes only the frozen adapter inputs, writes every stage to an
  add-once external namespace, and never edits Git-owned evidence.
* ``record-roofer-smoke`` seals the pinned synthetic runtime output.
* ``promote`` reads only compact task-owned outputs after execution and creates
  reviewable Git evidence.  It never reopens a scientific source.

No mode runs C1--C5 performance, protected held-out evaluation, Fusion W1, or
R_ext.  ``scientific_verdict`` is always null.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import os
import platform
import re
import struct
import subprocess
import sys
import tempfile
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence

import laspy
import numpy as np
import scipy
from scipy import ndimage
from shapely import wkb
from shapely import contains_xy
from shapely.geometry import MultiPoint, Polygon, box, mapping
from shapely.ops import unary_union
from shapely.strtree import STRtree


REPO = Path(__file__).resolve().parents[4]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from scripts.input_and_alignment.gate_s0.integrated_freeze_closure_v1 import (  # noqa: E402
    run_integrated_freeze as base,
)
from src.stage3.gate_s0_integrated_v1.interface import (  # noqa: E402
    CONDITIONS,
    derive_roofprint,
    synthetic_smoke_payload,
)


TASK = "P2-GATE-S0-FREEZE-RECOVERY-v1"
HANDOFF = "P2-W2C-GATE-S0-FREEZE-RECOVERY-v1"
CONFIG_PATH = REPO / "configs/input_and_alignment/gate_s0/freeze_recovery_v1/recovery_v1.json"
PACKET_PATH = REPO / "docs/handoffs/P2_W2C_GATE_S0_FREEZE_RECOVERY_v1.md"
SCRIPT_PATH = Path(__file__).resolve()
HOST_ORCHESTRATOR_PATH = SCRIPT_PATH.with_name("run_roofer_smoke_host.sh")
TEST_PATH = REPO / "tests/input_and_alignment/gate_s0/freeze_recovery_v1/test_freeze_recovery.py"
BASE_RUNNER_PATH = REPO / "scripts/input_and_alignment/gate_s0/integrated_freeze_closure_v1/run_integrated_freeze.py"
STAGE3_INTERFACE_PATH = REPO / "src/stage3/gate_s0_integrated_v1/interface.py"
MANIFEST_ROOT = REPO / "artifacts/manifests/gate_s0/freeze_recovery_v1"
DOC_ROOT = REPO / "docs/research/preregistration/gate_s0/freeze_recovery_v1"
ACCEPTANCE_RELATIVE = Path("acceptance/artifact_root_preflight_v1.json")
ACCEPTED_RECEIPT_PATH = REPO / f"artifacts/manifests/handoffs/{HANDOFF}/100-accepted.json"
PROMOTION_PATHS = (
    MANIFEST_ROOT / "technical_freeze_manifest_v1.json",
    DOC_ROOT / "eligibility_ledger_v1.csv",
    DOC_ROOT / "GATE_S0_FREEZE_RECOVERY_REPORT_v1.md",
)


def canonical_json_bytes(value: Any) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_ids(values: Iterable[str]) -> str:
    return sha256_bytes("".join(f"{value}\n" for value in sorted(values)).encode("utf-8"))


def utc_now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=REPO, text=True).strip()


def git_blob_at(commit: str, path: Path) -> str:
    relative = path.relative_to(REPO).as_posix()
    return git("rev-parse", f"{commit}:{relative}")


def current_blob(path: Path) -> str:
    return git("rev-parse", f"HEAD:{path.relative_to(REPO).as_posix()}")


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
        self.handle = os.fdopen(
            os.open(self.pending, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o664),
            "wb",
            buffering=0,
        )
        self.digest = hashlib.sha256()
        self.bytes = 0

    def write(self, data: bytes) -> None:
        self.handle.write(data)
        self.digest.update(data)
        self.bytes += len(data)

    def close(self) -> dict[str, Any]:
        self.handle.flush()
        os.fsync(self.handle.fileno())
        self.handle.close()
        if self.compare_existing:
            existing = hash_task_output_once(self.path)
            if existing["bytes"] != self.bytes or existing["sha256"] != self.digest.hexdigest():
                raise RuntimeError(f"existing add-once output differs from deterministic retry: {self.path}")
            self.pending.unlink()
            fsync_parent(self.path)
            return {"path": self.path.as_posix(), "bytes": self.bytes, "sha256": self.digest.hexdigest(), "reused_orphan_exact": True}
        try:
            os.link(self.pending, self.path)
        except FileExistsError:
            raise FileExistsError(self.path) from None
        fsync_parent(self.path)
        self.pending.unlink()
        fsync_parent(self.path)
        return {"path": self.path.as_posix(), "bytes": self.bytes, "sha256": self.digest.hexdigest()}


def recover_pending_files(root: Path) -> list[dict[str, Any]]:
    """Quarantine task-owned incomplete writes without reopening scientific input."""
    if not root.exists():
        return []
    recovered: list[dict[str, Any]] = []
    quarantine = root / "control/abandoned_pending"
    for pending in sorted(root.rglob(".*.pending")):
        if not pending.is_file() or pending.is_symlink():
            raise RuntimeError(f"invalid pending output: {pending}")
        final_name = pending.name[1:-len(".pending")]
        final = pending.with_name(final_name)
        relative = pending.relative_to(root).as_posix()
        if final.exists() and os.path.samefile(pending, final):
            pending.unlink()
            recovered.append({"pending": relative, "action": "UNLINKED_PUBLISHED_HARDLINK"})
            continue
        quarantine.mkdir(parents=True, exist_ok=True)
        safe_name = re.sub(r"[^A-Za-z0-9_.-]+", "_", relative)
        destination = quarantine / safe_name
        if destination.exists():
            raise RuntimeError(f"pending quarantine collision: {destination}")
        os.replace(pending, destination)
        fsync_parent(destination)
        recovered.append(
            {
                "pending": relative,
                "action": "QUARANTINED_INCOMPLETE_STAGE_OUTPUT",
                "quarantine": destination.relative_to(root).as_posix(),
            }
        )
    return recovered


def add_once_bytes(path: Path, data: bytes) -> dict[str, Any]:
    writer = AddOnceWriter(path)
    writer.write(data)
    return writer.close()


def add_once_json(path: Path, value: Any) -> dict[str, Any]:
    record = add_once_bytes(path, canonical_json_bytes(value))
    record["digest_method"] = "same_stream_as_add_once_serialization"
    return record


def add_once_csv(path: Path, fieldnames: Sequence[str], rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    data = canonical_csv_bytes(fieldnames, rows)
    record = add_once_bytes(path, data)
    record.update({"rows": len(rows), "digest_method": "same_stream_as_add_once_serialization"})
    return record


def canonical_csv_bytes(fieldnames: Sequence[str], rows: Sequence[dict[str, Any]]) -> bytes:
    buffer = io.StringIO(newline="")
    csv_writer = csv.DictWriter(buffer, fieldnames=fieldnames, lineterminator="\n")
    csv_writer.writeheader()
    for row in rows:
        csv_writer.writerow(row)
    return buffer.getvalue().encode("utf-8")


def hash_capture_once(path: Path, expected_bytes: int) -> tuple[dict[str, Any], bytes]:
    if path.is_symlink() or not path.is_file():
        raise RuntimeError(f"consumer input is not a regular non-symlink file: {path}")
    digest = hashlib.sha256()
    captured = bytearray()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(8 * 1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
            captured.extend(chunk)
    if len(captured) != expected_bytes:
        raise RuntimeError(f"consumer byte mismatch: {path}: {len(captured)} != {expected_bytes}")
    return {
        "path": path.as_posix(),
        "bytes": len(captured),
        "sha256": digest.hexdigest(),
        "full_passes": 1,
        "digest_method": "same_stream_as_consumer_capture",
    }, bytes(captured)


class Checkpoints:
    def __init__(self, root: Path, operation_id: str):
        self.root = root
        self.operation_id = operation_id
        self.records: list[dict[str, Any]] = []
        self.bodies: dict[int, dict[str, Any]] = {}
        self._load_existing()

    def _load_existing(self) -> None:
        previous_sha: str | None = None
        checkpoint_root = self.root / "checkpoints"
        if not checkpoint_root.exists():
            return
        for path in sorted(checkpoint_root.glob("[0-9][0-9][0-9]-*.json")):
            data = path.read_bytes()
            body = json.loads(data)
            ordinal = int(body.get("ordinal", -1))
            if body.get("schema") != "jointbuildgs.gate_s0_recovery_checkpoint.v1":
                raise RuntimeError(f"checkpoint schema mismatch: {path}")
            if body.get("task_id") != TASK or body.get("operation_id") != self.operation_id:
                raise RuntimeError(f"checkpoint operation mismatch: {path}")
            if body.get("status") != "COMPLETED_FSYNC":
                raise RuntimeError(f"checkpoint is not completed: {path}")
            if ordinal in self.bodies or body.get("predecessor_checkpoint_sha256") != previous_sha:
                raise RuntimeError(f"checkpoint chain mismatch: {path}")
            digest = sha256_bytes(data)
            record = {
                "ordinal": ordinal,
                "stage": body["stage"],
                "path": path.as_posix(),
                "bytes": len(data),
                "sha256": digest,
                "digest_method": "same_stream_as_add_once_serialization",
            }
            self.records.append(record)
            self.bodies[ordinal] = body
            previous_sha = digest

    def completed(self, ordinal: int, stage: str) -> bool:
        body = self.bodies.get(ordinal)
        return body is not None and body.get("stage") == stage

    def payload(self, ordinal: int, stage: str) -> dict[str, Any]:
        if not self.completed(ordinal, stage):
            raise RuntimeError(f"checkpoint is not complete: {ordinal:03d}-{stage}")
        return self.bodies[ordinal]["payload"]

    def write(self, ordinal: int, stage: str, payload: dict[str, Any]) -> dict[str, Any]:
        if ordinal in self.bodies:
            if not self.completed(ordinal, stage):
                raise RuntimeError(f"checkpoint ordinal collision: {ordinal}")
            return self.records[[record["ordinal"] for record in self.records].index(ordinal)]
        if self.records and ordinal <= self.records[-1]["ordinal"]:
            raise RuntimeError("checkpoints must be written in increasing ordinal order")
        body = {
            "schema": "jointbuildgs.gate_s0_recovery_checkpoint.v1",
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
        self.records.append({"ordinal": ordinal, "stage": stage, **record})
        self.bodies[ordinal] = body
        print(json.dumps({"checkpoint": ordinal, "stage": stage, "sha256": record["sha256"]}, sort_keys=True), flush=True)
        return record


class SourceAttempts:
    """Durable per-stage source-open attempt accounting and retry enforcement."""

    def __init__(self, root: Path, operation_id: str, retry_max: int):
        self.root = root
        self.operation_id = operation_id
        self.maximum_attempts = 1 + int(retry_max)

    def _paths(self, stage: str) -> list[Path]:
        return sorted((self.root / "attempts" / stage).glob("attempt_[0-9][0-9].json"))

    def start(self, stage: str, sources: Sequence[dict[str, Any]]) -> dict[str, Any]:
        if not re.fullmatch(r"[A-Za-z0-9_.-]+", stage):
            raise RuntimeError(f"invalid attempt stage: {stage}")
        existing = self._paths(stage)
        for path in existing:
            body = json.loads(path.read_bytes())
            if body.get("operation_id") != self.operation_id or body.get("task_id") != TASK or body.get("stage") != stage:
                raise RuntimeError(f"source attempt operation mismatch: {path}")
        if len(existing) >= self.maximum_attempts:
            raise RuntimeError(f"source retry cap exhausted before stage completion: {stage}")
        attempt_number = len(existing) + 1
        body = {
            "schema": "jointbuildgs.gate_s0_source_attempt.v1",
            "task_id": TASK,
            "operation_id": self.operation_id,
            "stage": stage,
            "attempt_number": attempt_number,
            "status": "SOURCE_OPEN_INTENT_FSYNC",
            "sources": list(sources),
            "created_at": utc_now(),
            "completion_evidence": "THE_STAGE_CHECKPOINT_REFERENCING_THIS_RECORD",
            "scientific_verdict": None,
        }
        return add_once_json(self.root / "attempts" / stage / f"attempt_{attempt_number:02d}.json", body)

    def audit(self) -> dict[str, Any]:
        counts = {}
        records = []
        attempt_root = self.root / "attempts"
        if attempt_root.exists():
            for path in sorted(attempt_root.glob("*/attempt_[0-9][0-9].json")):
                body = json.loads(path.read_bytes())
                if body.get("operation_id") != self.operation_id or body.get("task_id") != TASK:
                    raise RuntimeError(f"source attempt operation mismatch: {path}")
                stage = body["stage"]
                counts[stage] = counts.get(stage, 0) + 1
                records.append({**hash_task_output_once(path), "stage": stage, "attempt_number": body["attempt_number"]})
        return {
            "maximum_attempts_per_stage": self.maximum_attempts,
            "attempt_counts": dict(sorted(counts.items())),
            "records": records,
            "interpretation": "Each record was fsync-persisted before source content open; the matching completed checkpoint proves stage completion.",
        }


class RecoveryGrid(base.GridSummary):
    """Grid summary with geometry dispersion and provider class isolation."""

    def __post_init__(self) -> None:
        super().__post_init__()
        size = self.nx * self.ny
        self.sum_z = np.zeros(size, dtype=np.float64)
        self.sum_z2 = np.zeros(size, dtype=np.float64)
        self.class2_min_z = np.full(size, np.inf, dtype=np.float64)
        self.class2_count = np.zeros(size, dtype=np.uint64)
        self.class6_max_z = np.full(size, -np.inf, dtype=np.float64)
        self.class6_count = np.zeros(size, dtype=np.uint64)

    def update(self, x: np.ndarray, y: np.ndarray, z: np.ndarray, classification: np.ndarray | None = None) -> None:
        x_array = np.asarray(x, dtype=np.float64)
        y_array = np.asarray(y, dtype=np.float64)
        z_array = np.asarray(z, dtype=np.float64)
        x0, y0, x1, y1 = self.bbox
        keep = np.isfinite(x_array) & np.isfinite(y_array) & np.isfinite(z_array)
        keep &= (x_array >= x0) & (x_array < x1) & (y_array >= y0) & (y_array < y1)
        if np.any(keep):
            ix = np.floor((x_array[keep] - x0) / self.cell).astype(np.int64)
            iy = np.floor((y_array[keep] - y0) / self.cell).astype(np.int64)
            flat = iy * self.nx + ix
            zk = z_array[keep]
            np.add.at(self.sum_z, flat, zk)
            np.add.at(self.sum_z2, flat, zk * zk)
            if classification is not None:
                classes = np.asarray(classification, dtype=np.uint8)[keep]
                class2 = classes == 2
                class6 = classes == 6
                if np.any(class2):
                    np.minimum.at(self.class2_min_z, flat[class2], zk[class2])
                    np.add.at(self.class2_count, flat[class2], 1)
                if np.any(class6):
                    np.maximum.at(self.class6_max_z, flat[class6], zk[class6])
                    np.add.at(self.class6_count, flat[class6], 1)
        super().update(x_array, y_array, z_array, classification)

    def z_std(self) -> np.ndarray:
        count = self.count.astype(np.float64)
        variance = np.zeros_like(self.sum_z)
        valid = count > 0
        variance[valid] = self.sum_z2[valid] / count[valid] - (self.sum_z[valid] / count[valid]) ** 2
        return np.sqrt(np.maximum(variance, 0.0))


def assert_git_contract(source_commit: str, require_clean: bool, strict_refs: bool = False) -> dict[str, Any]:
    git("cat-file", "-e", f"{source_commit}^{{commit}}")
    paths = [SCRIPT_PATH, HOST_ORCHESTRATOR_PATH, CONFIG_PATH, PACKET_PATH, TEST_PATH, BASE_RUNNER_PATH, STAGE3_INTERFACE_PATH]
    blobs = {}
    for path in paths:
        expected = git_blob_at(source_commit, path)
        actual = current_blob(path)
        if expected != actual:
            raise RuntimeError(f"WIP/source blob mismatch: {path.relative_to(REPO)}")
        blobs[path.relative_to(REPO).as_posix()] = actual
    dirty = git("status", "--porcelain=v1", "--untracked-files=all")
    if require_clean and dirty:
        raise RuntimeError("execution requires a clean tracked/untracked worktree")
    head = git("rev-parse", "HEAD")
    origin = git("rev-parse", "origin/main")
    if strict_refs and (head != source_commit or origin != source_commit):
        raise RuntimeError("execution requires HEAD == origin/main == accepted source commit")
    return {
        "source_commit": source_commit,
        "head": head,
        "origin_main": origin,
        "blobs": blobs,
        "clean": not bool(dirty),
    }


def acceptance_input_specs(config: dict[str, Any]) -> list[dict[str, Any]]:
    common_root = Path(config["consumed_common_base"]["payload_root"])
    records = [
        {"path": (common_root / config["consumed_common_base"][name]["path"]).as_posix(), "bytes": int(config["consumed_common_base"][name]["expected_bytes"])}
        for name in ("camera_model", "image_poses", "sparse_points", "dense_ply")
    ]
    records.append({"path": config["c1"]["path"], "bytes": int(config["c1"]["bytes"])})
    records.extend({"path": item["path"], "bytes": int(item["bytes"])} for item in config["c4"]["tiles"])
    records.extend({"path": item["path"], "bytes": int(item["bytes"])} for item in config["c5"]["selected_prisms"])
    return records


def validate_acceptance(source_commit: str, artifact_root: Path, config: dict[str, Any]) -> dict[str, Any]:
    if not ACCEPTED_RECEIPT_PATH.is_file():
        raise RuntimeError("exact 100-accepted receipt is required before source access")
    receipt_bytes = ACCEPTED_RECEIPT_PATH.read_bytes()
    receipt = json.loads(receipt_bytes)
    if receipt.get("schema") != "jointbuildgs.two_host_handoff.v1" or receipt.get("state") != "accepted":
        raise RuntimeError("100 receipt is not an accepted two-host receipt")
    if receipt.get("handoff_id") != HANDOFF or receipt.get("task_id") != TASK:
        raise RuntimeError("100 receipt task identity mismatch")
    if receipt.get("receiver_role") != "experiment_host" or not receipt.get("transport", {}).get("exclusive_writer_ack"):
        raise RuntimeError("100 receipt does not bind Experiment Host writer ownership")
    verification = receipt.get("verification", {})
    if verification.get("level") != "artifact_verified" or verification.get("verifier_role") != "experiment_host":
        raise RuntimeError("100 receipt is not artifact-verified by Experiment Host")
    if receipt.get("artifacts", {}).get("availability", {}).get("experiment_host") != "verified_local":
        raise RuntimeError("100 receipt does not declare Experiment Host local artifact availability")
    if receipt.get("scientific", {}).get("scientific_verdict") is not None:
        raise RuntimeError("100 receipt scientific_verdict must remain null")
    if git("rev-parse", "HEAD") != source_commit:
        raise RuntimeError("accepted source commit must be current HEAD")
    acceptance_path = artifact_root / config["output_namespace"] / ACCEPTANCE_RELATIVE
    if not acceptance_path.is_file() or acceptance_path.is_symlink():
        raise RuntimeError("artifact-root acceptance record is missing")
    acceptance_bytes = acceptance_path.read_bytes()
    acceptance_sha = sha256_bytes(acceptance_bytes)
    artifact_records = receipt.get("artifacts", {}).get("records", [])
    matched = [
        value for value in artifact_records
        if str(value.get("uri", "")).endswith("/" + ACCEPTANCE_RELATIVE.as_posix())
    ]
    if len(matched) != 1 or int(matched[0].get("bytes", -1)) != len(acceptance_bytes) or matched[0].get("sha256") != acceptance_sha:
        raise RuntimeError("100 receipt does not bind the exact acceptance artifact")
    acceptance = json.loads(acceptance_bytes)
    if acceptance.get("schema") != "jointbuildgs.gate_s0_recovery_acceptance.v1":
        raise RuntimeError("acceptance artifact schema mismatch")
    required = {
        "task_id": TASK,
        "handoff_id": HANDOFF,
        "status": "PASS_METADATA_ONLY",
        "artifact_root": config["artifact_root"],
        "physical_host_id": config["physical_host_id"],
        "scientific_payload_bytes_read_or_hashed": 0,
        "project_docker_image": "jointbuildgs:dev",
    }
    for key, expected in required.items():
        if acceptance.get(key) != expected:
            raise RuntimeError(f"acceptance artifact field mismatch: {key}")
    project_image_id = acceptance.get("project_docker_image_id")
    if not isinstance(project_image_id, str) or not re.fullmatch(r"sha256:[0-9a-f]{64}", project_image_id):
        raise RuntimeError("acceptance project Docker image ID is invalid")
    if verification.get("docker_image_digest") != project_image_id:
        raise RuntimeError("100 receipt Docker image digest differs from acceptance")
    expected_stats = sorted(acceptance_input_specs(config), key=lambda value: value["path"])
    observed_stats = sorted(acceptance.get("input_stats", []), key=lambda value: value.get("path", ""))
    if observed_stats != expected_stats:
        raise RuntimeError("acceptance input-stat manifest mismatch")
    for value in expected_stats:
        path = artifact_root / value["path"]
        if path.is_symlink() or not path.is_file() or path.stat().st_size != value["bytes"]:
            raise RuntimeError(f"accepted input stat changed: {value['path']}")
    return {
        "accepted_receipt_path": ACCEPTED_RECEIPT_PATH.relative_to(REPO).as_posix(),
        "accepted_receipt_blob": current_blob(ACCEPTED_RECEIPT_PATH),
        "accepted_receipt_sha256": sha256_bytes(receipt_bytes),
        "acceptance_path": acceptance_path.as_posix(),
        "acceptance_bytes": len(acceptance_bytes),
        "acceptance_sha256": acceptance_sha,
        "physical_host_id": config["physical_host_id"],
        "project_docker_image": acceptance["project_docker_image"],
        "project_docker_image_id": project_image_id,
        "input_stat_records": len(expected_stats),
    }


def allowed_namespace_file(relative: str) -> bool:
    exact = {
        ACCEPTANCE_RELATIVE.as_posix(),
        "control/started_v1.json",
        "control/execution_ledger_v1.json",
        "control/completed_ledger_v1.json",
        "common/camera_model_index_v1.json",
        "common/pose_index_v1.json",
        "common/mvs_grid_v1.npz",
        "common/mvs_class26_v1.ply",
        "reference/c1_grid_v1.npz",
        "reference/c1_class26_v1.ply",
        "reference/uasref_cells_pre_c5_v1.csv",
        "reference/reference_id_crosswalk_v1.csv",
        "inputs/c4_grid_v1.npz",
        "inputs/c4_class26_v1.ply",
        "inputs/c5_canonical_199_prior_inventory_v1.csv",
        "inputs/c5_reference_overlap_diagnostic_v1.csv",
        "freeze/eligibility_ledger_v1.csv",
        "freeze/execution_tiles_v1.geojson",
        "freeze/technical_summary_v1.json",
        "stage3/synthetic_class26.laz",
        "stage3/synthetic_r_derived.geojson",
        "stage3/common_interface_five_conditions.jsonl",
        "stage3/roofer_runtime_smoke_receipt_v1.json",
    }
    if relative in exact:
        return True
    return bool(
        re.fullmatch(r"checkpoints/[0-9]{3}-[A-Za-z0-9_.-]+\.json", relative)
        or re.fullmatch(r"attempts/[A-Za-z0-9_.-]+/attempt_[0-9]{2}\.json", relative)
        or re.fullmatch(r"inputs/c4_[0-9_]+_grid_v1\.npz", relative)
        or relative in {"stage3/roofer_smoke_sealed/exit_code", "stage3/roofer_smoke_sealed/runtime.log"}
        or relative.startswith("stage3/roofer_smoke_sealed/output/")
        or relative in {"stage3/.roofer_smoke.pending/exit_code", "stage3/.roofer_smoke.pending/runtime.log"}
        or relative.startswith("stage3/.roofer_smoke.pending/output/")
        or relative in {"stage3/.roofer_smoke.quarantine.1/exit_code", "stage3/.roofer_smoke.quarantine.1/runtime.log"}
        or relative.startswith("stage3/.roofer_smoke.quarantine.1/output/")
        or relative.startswith("control/abandoned_pending/")
    )


def synthetic_laz_fallback_check() -> dict[str, Any]:
    with tempfile.TemporaryDirectory() as temporary:
        path = Path(temporary) / "synthetic.las"
        header = laspy.LasHeader(point_format=3, version="1.2")
        cloud = laspy.LasData(header)
        cloud.x = np.array([500000.0, 500001.0, 500002.0])
        cloud.y = np.array([5300000.0, 5300001.0, 5300002.0])
        cloud.z = np.array([500.0, 501.0, 502.0])
        cloud.classification = np.array([0, 2, 6], dtype=np.uint8)
        cloud.write(path)
        grid = base.GridSummary((499999.0, 5299999.0, 500004.0, 5300004.0), 1.0)
        result = base.process_laz_once(path, grid, transform=False)
    return {"points": result["point_count"], "chunks": result["chunks"], "crs_fallback": result["parsed_crs"]}


def preflight(
    source_commit: str,
    artifact_root: Path | None,
    require_clean: bool = True,
    *,
    require_acceptance: bool = False,
    allow_resume: bool = False,
) -> dict[str, Any]:
    contract = assert_git_contract(source_commit, require_clean=require_clean, strict_refs=require_acceptance)
    fallback = synthetic_laz_fallback_check()
    tx, ty = base.epsg32632_to_25832(
        np.array([690791.74, 691154.65]), np.array([5335864.05, 5336353.85])
    )
    residual = max(
        math.hypot(float(tx[0]) - 690791.740001741, float(ty[0]) - 5335864.049877891),
        math.hypot(float(tx[1]) - 691154.650001744, float(ty[1]) - 5336353.849877889),
    )
    if residual > 0.0003:
        raise RuntimeError("EPSG:32632-to-25832 synthetic cross-check failed")
    namespace = None
    acceptance = None
    if artifact_root is not None:
        config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        output_root = artifact_root.resolve() / config["output_namespace"]
        if require_acceptance:
            acceptance = validate_acceptance(source_commit, artifact_root.resolve(), config)
        if output_root.exists():
            files = sorted(path.relative_to(output_root).as_posix() for path in output_root.rglob("*") if path.is_file())
            unexpected = [
                value for value in files
                if value != ACCEPTANCE_RELATIVE.as_posix()
                and not (allow_resume and allowed_namespace_file(value))
            ]
            if unexpected:
                raise RuntimeError(f"namespace contains unauthorized files: {unexpected}")
            namespace = {"exists": True, "files": files, "resume_allowed": allow_resume}
        else:
            namespace = {"exists": False, "allowed_files": []}
    return {
        "status": "PASS_ZERO_SCIENTIFIC_PAYLOAD_READ",
        "git": contract,
        "python": platform.python_version(),
        "numpy": np.__version__,
        "scipy": scipy.__version__,
        "laspy": laspy.__version__,
        "synthetic_las": fallback,
        "epsg_crosscheck_max_residual_m": residual,
        "namespace": namespace,
        "acceptance": acceptance,
        "scientific_payload_bytes_read_or_hashed": 0,
        "scientific_verdict": None,
    }


def enforce_runtime_control(
    source_commit: str,
    artifact_root: Path,
    *,
    allowed_dirty_paths: Sequence[Path] = (),
) -> dict[str, Any]:
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    contract = assert_git_contract(source_commit, require_clean=False, strict_refs=True)
    acceptance = validate_acceptance(source_commit, artifact_root.resolve(), config)
    allowed = {path.relative_to(REPO).as_posix() for path in allowed_dirty_paths}
    dirty_lines = [line for line in git("status", "--porcelain=v1", "--untracked-files=all").splitlines() if line]
    unexpected = []
    for line in dirty_lines:
        path_text = line[3:]
        if " -> " in path_text:
            path_text = path_text.split(" -> ", 1)[1]
        if path_text.replace("\\", "/") not in allowed:
            unexpected.append(line)
    if unexpected:
        raise RuntimeError(f"runtime mode has unauthorized Git worktree changes: {unexpected}")
    command = [
        sys.executable,
        "scripts/repository/validate_two_host_handoff.py",
        ACCEPTED_RECEIPT_PATH.relative_to(REPO).as_posix(),
        "--repo",
        ".",
        "--origin-ref",
        "origin/main",
        "--head-ref",
        "HEAD",
        "--artifact-root",
        artifact_root.resolve().as_posix(),
    ]
    completed = subprocess.run(command, cwd=REPO, text=True, capture_output=True)
    if completed.returncode != 0:
        raise RuntimeError(f"canonical 100-accepted validation failed: {completed.stdout}{completed.stderr}")
    return {
        "git": contract,
        "acceptance": acceptance,
        "canonical_handoff_validator": "PASS",
        "dirty_paths_allowed": sorted(allowed),
    }


def grid_npz_bytes(grid: RecoveryGrid) -> bytes:
    output = io.BytesIO()
    np.savez_compressed(
        output,
        min_z=grid.min_z,
        max_z=grid.max_z,
        count=grid.count,
        sum_z=grid.sum_z,
        sum_z2=grid.sum_z2,
        class2_min_z=grid.class2_min_z,
        class2_count=grid.class2_count,
        class6_max_z=grid.class6_max_z,
        class6_count=grid.class6_count,
    )
    return output.getvalue()


def verify_task_record(record: dict[str, Any], root: Path) -> Path:
    path = Path(record["path"])
    resolved = path.resolve()
    try:
        resolved.relative_to(root.resolve())
    except ValueError as error:
        raise RuntimeError(f"compact output escapes task namespace: {path}") from error
    if resolved.is_symlink() or not resolved.is_file():
        raise RuntimeError(f"compact output is missing: {resolved}")
    data = resolved.read_bytes()
    if len(data) != int(record["bytes"]) or sha256_bytes(data) != record["sha256"]:
        raise RuntimeError(f"compact output digest mismatch: {resolved}")
    return resolved


def load_json_record(record: dict[str, Any], root: Path) -> Any:
    return json.loads(verify_task_record(record, root).read_bytes())


def load_grid_record(record: dict[str, Any], root: Path, bbox: tuple[float, float, float, float], cell: float) -> RecoveryGrid:
    path = verify_task_record(record, root)
    grid = RecoveryGrid(bbox, cell)
    with np.load(path, allow_pickle=False) as source:
        names = (
            "min_z", "max_z", "count", "sum_z", "sum_z2",
            "class2_min_z", "class2_count", "class6_max_z", "class6_count",
        )
        for name in names:
            observed = np.asarray(source[name])
            target = getattr(grid, name)
            if observed.shape != target.shape or observed.dtype != target.dtype:
                raise RuntimeError(f"grid checkpoint array contract mismatch: {name}")
            target[:] = observed
    return grid


def merge_grid(target: RecoveryGrid, source: RecoveryGrid) -> None:
    if target.bbox != source.bbox or target.cell != source.cell:
        raise RuntimeError("cannot merge grids with different frames")
    target.min_z = np.minimum(target.min_z, source.min_z)
    target.max_z = np.maximum(target.max_z, source.max_z)
    target.count += source.count
    target.sum_z += source.sum_z
    target.sum_z2 += source.sum_z2
    target.class2_min_z = np.minimum(target.class2_min_z, source.class2_min_z)
    target.class2_count += source.class2_count
    target.class6_max_z = np.maximum(target.class6_max_z, source.class6_max_z)
    target.class6_count += source.class6_count


def load_camera_checkpoint(payload: dict[str, Any], root: Path) -> dict[int, dict[str, Any]]:
    rows = load_json_record(payload["output"], root)
    return {
        int(row["camera_id"]): {
            "model_id": int(row["model_id"]),
            "width": int(row["width"]),
            "height": int(row["height"]),
            "params": np.asarray(row["params"], dtype=np.float64),
        }
        for row in rows
    }


def load_pose_checkpoint(payload: dict[str, Any], root: Path) -> list[dict[str, Any]]:
    rows = load_json_record(payload["output"], root)
    return [
        {
            "image_id": int(row["image_id"]),
            "camera_id": int(row["camera_id"]),
            "name": row["name"],
            "rotation": np.asarray(row["rotation"], dtype=np.float64),
            "translation": np.asarray(row["translation"], dtype=np.float64),
        }
        for row in rows
    ]


def read_csv_record(record: dict[str, Any], root: Path) -> list[dict[str, str]]:
    path = verify_task_record(record, root)
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def camera_index(cameras: dict[int, dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "camera_id": camera_id,
            "model_id": value["model_id"],
            "width": value["width"],
            "height": value["height"],
            "params": list(value["params"]),
        }
        for camera_id, value in sorted(cameras.items())
    ]


def pose_index(images: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "image_id": value["image_id"],
            "camera_id": value["camera_id"],
            "name": value["name"],
            "rotation": np.asarray(value["rotation"]).tolist(),
            "translation": np.asarray(value["translation"]).tolist(),
        }
        for value in images
    ]


@dataclass
class Reference:
    labels: np.ndarray
    keep: np.ndarray
    terrain: np.ndarray
    top: np.ndarray
    local_rmse: np.ndarray
    normal_z: np.ndarray
    z_std: np.ndarray
    component_ids: dict[int, str]
    cells: dict[int, np.ndarray]
    planar_fraction: dict[int, float]


def terrain_envelope_from_array(lower: np.ndarray, windows: Sequence[int]) -> np.ndarray:
    valid = np.isfinite(lower)
    if not np.any(valid):
        raise RuntimeError("no finite cells for terrain envelope")
    nearest = ndimage.distance_transform_edt(~valid, return_distances=False, return_indices=True)
    filled = lower[tuple(nearest)]
    opened = [ndimage.grey_opening(filled, size=(size, size), mode="nearest") for size in windows]
    return np.minimum.reduce(opened)


def terrain_envelope(grid: base.GridSummary, windows: Sequence[int]) -> np.ndarray:
    return terrain_envelope_from_array(grid.min_z.reshape(grid.ny, grid.nx), windows)


def local_plane_metrics(
    top: np.ndarray,
    candidate: np.ndarray,
    cell: float,
    window: int,
    minimum_neighbors: int,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Fit z=ax+by+c independently in each fixed local window."""
    radius = window // 2
    rmse = np.full(top.shape, np.inf, dtype=np.float64)
    normal_z = np.zeros(top.shape, dtype=np.float64)
    neighbors = np.zeros(top.shape, dtype=np.uint16)
    finite = np.isfinite(top)
    for iy, ix in np.argwhere(candidate):
        y0, y1 = max(0, iy - radius), min(top.shape[0], iy + radius + 1)
        x0, x1 = max(0, ix - radius), min(top.shape[1], ix + radius + 1)
        local_valid = finite[y0:y1, x0:x1]
        count = int(np.count_nonzero(local_valid))
        neighbors[iy, ix] = count
        if count < minimum_neighbors:
            continue
        ly, lx = np.nonzero(local_valid)
        design = np.column_stack((lx.astype(np.float64) * cell, ly.astype(np.float64) * cell, np.ones(count)))
        values = top[y0:y1, x0:x1][local_valid]
        coefficients, _, _, _ = np.linalg.lstsq(design, values, rcond=None)
        residual = values - design @ coefficients
        rmse[iy, ix] = float(np.sqrt(np.mean(residual * residual)))
        normal_z[iy, ix] = float(1.0 / math.sqrt(1.0 + coefficients[0] ** 2 + coefficients[1] ** 2))
    return rmse, normal_z, neighbors


def input_support_mask(
    grid: base.GridSummary,
    terrain: np.ndarray,
    config: dict[str, Any],
    *,
    z_translation_m: float = 0.0,
) -> np.ndarray:
    """Outcome-free class-6 support from geometry relative to frozen terrain."""
    top = grid.max_z.reshape(grid.ny, grid.nx) + z_translation_m
    count = grid.count.reshape(grid.ny, grid.nx)
    return (
        np.isfinite(top)
        & np.isfinite(terrain)
        & (count >= int(config["grid"]["minimum_points_per_cell"]))
        & ((top - terrain) >= float(config["grid"]["minimum_height_above_terrain_m"]))
    )


def filtered_terrain_gravity(grid: RecoveryGrid, terrain: np.ndarray) -> dict[str, Any]:
    observed = np.isfinite(grid.min_z.reshape(grid.ny, grid.nx))
    dz_dy, dz_dx = np.gradient(terrain, grid.cell, grid.cell)
    slope = np.sqrt(dz_dx * dz_dx + dz_dy * dz_dy)
    terrain_cells = observed & (np.abs(grid.min_z.reshape(grid.ny, grid.nx) - terrain) <= 0.35) & (slope <= 0.35)
    if np.count_nonzero(terrain_cells) < 1000:
        raise RuntimeError("insufficient filtered MVS terrain cells for gravity")
    normals = np.stack((-dz_dx, -dz_dy, np.ones_like(dz_dx)), axis=-1)[terrain_cells]
    normals /= np.linalg.norm(normals, axis=1, keepdims=True)
    median = np.median(normals, axis=0)
    median /= np.linalg.norm(median)
    inliers = normals[(normals @ median) >= math.cos(math.radians(20.0))]
    up = np.mean(inliers, axis=0)
    up /= np.linalg.norm(up)
    angles = np.degrees(np.arccos(np.clip(inliers @ up, -1.0, 1.0)))
    return {
        "method": "filtered dense-MVS multiscale lower-envelope normals; observed delta<=0.35m; slope<=0.35; 20-degree consensus",
        "terrain_cell_count": int(np.count_nonzero(terrain_cells)),
        "inlier_normal_count": int(len(inliers)),
        "up": [float(value) for value in up],
        "gravity": [float(value) for value in -up],
        "angular_median_deg": float(np.median(angles)),
        "angular_p95_deg": float(np.percentile(angles, 95)),
        "hardcoded_gravity": False,
    }


def write_grid_ply_with_mask(
    path: Path,
    grid: base.GridSummary,
    terrain: np.ndarray,
    building: np.ndarray,
    *,
    z_translation_m: float = 0.0,
) -> dict[str, Any]:
    valid_ground = np.isfinite(terrain) & np.isfinite(grid.min_z.reshape(grid.ny, grid.nx))
    valid_building = building & np.isfinite(grid.max_z.reshape(grid.ny, grid.nx))
    x, y = grid.centers()
    writer = AddOnceWriter(path)
    writer.write(
        (
            "ply\nformat ascii 1.0\n"
            f"element vertex {int(np.count_nonzero(valid_ground) + np.count_nonzero(valid_building))}\n"
            "property double x\nproperty double y\nproperty double z\n"
            "property uchar classification\nend_header\n"
        ).encode("ascii")
    )
    for flat in np.flatnonzero(valid_ground.ravel()):
        writer.write(f"{x[flat]:.3f} {y[flat]:.3f} {terrain.ravel()[flat]:.3f} 2\n".encode("ascii"))
    for flat in np.flatnonzero(valid_building.ravel()):
        z = grid.max_z[flat] + z_translation_m
        writer.write(f"{x[flat]:.3f} {y[flat]:.3f} {z:.3f} 6\n".encode("ascii"))
    record = writer.close()
    record.update(
        {
            "ground_points": int(np.count_nonzero(valid_ground)),
            "building_points": int(np.count_nonzero(valid_building)),
            "z_translation_m": z_translation_m,
            "digest_method": "same_stream_as_add_once_serialization",
        }
    )
    return record


def write_c4_classified_ply(
    path: Path,
    grid: RecoveryGrid,
    mvs_terrain: np.ndarray,
    building: np.ndarray,
    z_translation_m: float,
) -> dict[str, Any]:
    ground = np.isfinite(grid.class2_min_z.reshape(grid.ny, grid.nx))
    building = building & np.isfinite(grid.class6_max_z.reshape(grid.ny, grid.nx))
    x, y = grid.centers()
    writer = AddOnceWriter(path)
    writer.write(
        (
            "ply\nformat ascii 1.0\n"
            f"element vertex {int(np.count_nonzero(ground) + np.count_nonzero(building))}\n"
            "property double x\nproperty double y\nproperty double z\nproperty uchar classification\nend_header\n"
        ).encode("ascii")
    )
    for flat in np.flatnonzero(ground.ravel()):
        writer.write(f"{x[flat]:.3f} {y[flat]:.3f} {grid.class2_min_z[flat] + z_translation_m:.3f} 2\n".encode("ascii"))
    for flat in np.flatnonzero(building.ravel()):
        writer.write(f"{x[flat]:.3f} {y[flat]:.3f} {grid.class6_max_z[flat] + z_translation_m:.3f} 6\n".encode("ascii"))
    record = writer.close()
    record.update(
        {
            "ground_points": int(np.count_nonzero(ground)),
            "building_points": int(np.count_nonzero(building)),
            "source_classes_consumed": [2, 6],
            "other_classes_promoted": False,
            "z_translation_m": z_translation_m,
            "digest_method": "same_stream_as_add_once_serialization",
        }
    )
    return record


def extract_reference(grid: RecoveryGrid, config: dict[str, Any], namespace_hash: str) -> Reference:
    rule = config["grid"]
    terrain = terrain_envelope(grid, rule["terrain_filter_windows_cells"])
    top = grid.max_z.reshape(grid.ny, grid.nx)
    valid_top = np.isfinite(top)
    thickness = top - terrain
    z_std = grid.z_std().reshape(grid.ny, grid.nx)
    preliminary = valid_top.copy()
    preliminary &= grid.count.reshape(grid.ny, grid.nx) >= int(rule["minimum_points_per_cell"])
    preliminary &= thickness >= float(rule["minimum_height_above_terrain_m"])
    preliminary &= z_std <= float(rule["within_cell_z_std_limit_m"])
    local_rmse, normal_z, neighbors = local_plane_metrics(
        top,
        preliminary,
        grid.cell,
        int(rule["local_window_cells"]),
        int(rule["minimum_valid_neighbors"]),
    )
    planar = preliminary.copy()
    planar &= neighbors >= int(rule["minimum_valid_neighbors"])
    planar &= local_rmse <= float(rule["local_plane_rmse_limit_m"])
    planar &= normal_z >= float(rule["minimum_up_dot"])
    planar &= ~(
        (local_rmse > float(rule["vegetation_roughness_limit_m"]))
        & (z_std > float(rule["vegetation_z_std_trigger_m"]))
    )
    preliminary_labels, _ = ndimage.label(preliminary, structure=np.ones((3, 3), dtype=np.uint8))
    preliminary_sizes = np.bincount(preliminary_labels.ravel())
    fractions: dict[int, float] = {}
    accepted_preliminary: list[int] = []
    for label in range(1, len(preliminary_sizes)):
        size = int(preliminary_sizes[label])
        if size < int(rule["minimum_component_cells"]):
            continue
        fraction = float(np.count_nonzero(planar & (preliminary_labels == label)) / size)
        fractions[label] = fraction
        if fraction >= float(rule["minimum_planar_fraction"]):
            accepted_preliminary.append(label)
    accepted_planar = planar & np.isin(preliminary_labels, accepted_preliminary)
    labels, _ = ndimage.label(accepted_planar, structure=np.ones((3, 3), dtype=np.uint8))
    sizes = np.bincount(labels.ravel())
    retained = [index for index in range(1, len(sizes)) if sizes[index] >= int(rule["minimum_component_cells"])]
    keep = np.isin(labels, retained)
    component_ids: dict[int, str] = {}
    cells: dict[int, np.ndarray] = {}
    for label in retained:
        flat = np.flatnonzero(labels.ravel() == label)
        identity = sha256_bytes((namespace_hash + "|" + ",".join(str(int(value)) for value in flat) + "\n").encode())[:20]
        component_ids[label] = f"UASREF_{identity}"
        cells[label] = flat
    retained_fraction: dict[int, float] = {}
    for label, flat in cells.items():
        source_labels = preliminary_labels.ravel()[flat]
        source = int(Counter(int(value) for value in source_labels if int(value) > 0).most_common(1)[0][0])
        retained_fraction[label] = fractions[source]
    return Reference(labels=labels, keep=keep, terrain=terrain, top=top, local_rmse=local_rmse, normal_z=normal_z, z_std=z_std, component_ids=component_ids, cells=cells, planar_fraction=retained_fraction)


def reference_rows(grid: base.GridSummary, reference: Reference) -> list[dict[str, Any]]:
    x, y = grid.centers()
    rows = []
    for label in sorted(reference.cells, key=lambda item: reference.component_ids[item]):
        stable_id = reference.component_ids[label]
        for flat in reference.cells[label]:
            iy, ix = divmod(int(flat), grid.nx)
            rows.append(
                {
                    "reference_component_id": stable_id,
                    "cell_ix": ix,
                    "cell_iy": iy,
                    "cell_x": f"{x[flat]:.3f}",
                    "cell_y": f"{y[flat]:.3f}",
                    "relative_roof_height_m": f"{reference.top[iy, ix] - reference.terrain[iy, ix]:.3f}",
                    "local_plane_rmse_m": f"{reference.local_rmse[iy, ix]:.6f}",
                    "within_cell_z_std_m": f"{reference.z_std[iy, ix]:.6f}",
                    "normal_z": f"{reference.normal_z[iy, ix]:.9f}",
                }
            )
    return rows


def polygons_from_record(record: dict[str, Any]):
    polygons = []
    for item in record["footprint"]:
        polygon = Polygon(item["exterior"], holes=item.get("interiors") or None)
        if not polygon.is_valid:
            polygon = polygon.buffer(0)
        if not polygon.is_empty and polygon.area > 0:
            polygons.append(polygon)
    return unary_union(polygons) if polygons else None


def load_candidate_buildings(config: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    path = REPO / config["eligibility"]["candidate_ledger"]
    buildings: list[dict[str, Any]] = []
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            bbox_values = tuple(float(value) for value in row["groundsurface_bbox_epsg25832"].split(","))
            if len(bbox_values) != 4 or row["candidate_aoi_intersects"] != "true":
                raise RuntimeError("canonical 199 candidate ledger contract mismatch")
            buildings.append(
                {
                    "stable_id": row["stable_id"],
                    "provider_external_id": row["provider_external_id"],
                    "reference_tile": row["reference_tile"],
                    "bbox": bbox_values,
                }
            )
    buildings.sort(key=lambda item: item["stable_id"])
    stable_digest = sha256_ids(item["stable_id"] for item in buildings)
    if len(buildings) != int(config["eligibility"]["candidate_count"]):
        raise RuntimeError("canonical candidate count is not 199")
    if stable_digest != config["eligibility"]["stable_id_set_sha256"]:
        raise RuntimeError("canonical 199 stable-ID digest mismatch")
    return buildings, {
        "path": path.relative_to(REPO).as_posix(),
        "count": len(buildings),
        "stable_id_set_sha256": stable_digest,
        "role": "EVALUATION_ONLY_TARGET_ID_AND_POST_FREEZE_REFERENCE_CROSSWALK",
        "loaded_after_reference_freeze": True,
    }


def crosswalk_reference_to_buildings(
    grid: RecoveryGrid,
    reference: Reference,
    buildings: Sequence[dict[str, Any]],
    buffer_m: float,
) -> tuple[dict[str, list[str]], dict[str, int], list[dict[str, Any]]]:
    x, y = grid.centers()
    associations: dict[str, list[str]] = {}
    score_cells: dict[str, int] = {}
    rows: list[dict[str, Any]] = []
    for building in buildings:
        bx0, by0, bx1, by1 = building["bbox"]
        buffered = box(bx0, by0, bx1, by1).buffer(buffer_m, cap_style=3, join_style=2)
        matched: list[str] = []
        matched_score_cells = 0
        for label, cells in reference.cells.items():
            xs, ys = x[cells], y[cells]
            centroid = MultiPoint(np.column_stack((xs, ys))).centroid
            inside_original = (xs >= bx0) & (xs <= bx1) & (ys >= by0) & (ys <= by1)
            centroid_buffered = buffered.covers(centroid)
            inside_count = int(np.count_nonzero(inside_original))
            if inside_count > 0 or centroid_buffered:
                reference_id = reference.component_ids[label]
                if inside_count > 0:
                    matched.append(reference_id)
                    matched_score_cells += inside_count
                rows.append(
                    {
                        "stable_id": building["stable_id"],
                        "reference_component_id": reference_id,
                        "component_cells_inside_original_bbox": inside_count,
                        "component_centroid_inside_fixed_buffer": str(centroid_buffered).lower(),
                        "crosswalk_buffer_m": f"{buffer_m:.3f}",
                        "lod2_geometry_used_to_construct_reference": "false",
                        "lod2_geometry_used_as_score_geometry": "false",
                        "score_support_is_independent_uas_cells_clipped_to_target_bbox": str(inside_count > 0).lower(),
                        "crosswalk_stage": "AFTER_REFERENCE_ADD_ONCE_FREEZE",
                    }
                )
        associations[building["stable_id"]] = sorted(set(matched))
        score_cells[building["stable_id"]] = matched_score_cells
    return associations, score_cells, rows


def raster_values_under_geometry(geometry: Any, grid: RecoveryGrid, values: np.ndarray) -> np.ndarray:
    x0, y0, _, _ = grid.bbox
    bx0, by0, bx1, by1 = geometry.bounds
    ix0 = max(0, int(math.floor((bx0 - x0) / grid.cell)))
    iy0 = max(0, int(math.floor((by0 - y0) / grid.cell)))
    ix1 = min(grid.nx, int(math.ceil((bx1 - x0) / grid.cell)))
    iy1 = min(grid.ny, int(math.ceil((by1 - y0) / grid.cell)))
    if ix0 >= ix1 or iy0 >= iy1:
        return np.array([], dtype=np.float64)
    iy, ix = np.indices((iy1 - iy0, ix1 - ix0))
    xs = x0 + (ix + ix0 + 0.5) * grid.cell
    ys = y0 + (iy + iy0 + 0.5) * grid.cell
    inside = contains_xy(geometry, xs, ys)
    selected = values[(iy + iy0, ix + ix0)][inside]
    return selected[np.isfinite(selected)]


def load_c5_file_once(
    path: Path,
    spec: dict[str, Any],
    target_ids: set[str],
    mvs_grid: RecoveryGrid,
    mvs_terrain: np.ndarray,
    candidate_bboxes: dict[str, tuple[float, float, float, float]] | None = None,
    association_buffer_m: float = 0.0,
) -> tuple[dict[str, dict[str, Any]], dict[str, Any], list[float]]:
    selected: dict[str, dict[str, Any]] = {}
    ground_to_mvs: list[float] = []
    digest = hashlib.sha256()
    total = 0
    records = 0
    with path.open("rb") as handle:
        for line in handle:
            digest.update(line)
            total += len(line)
            records += 1
            record = json.loads(line)
            stable_id = record["stable_building_id"]
            if stable_id not in target_ids:
                continue
            if record.get("primary_c5_eligible") is not False:
                raise RuntimeError("C5 prior provenance guard failed")
            if stable_id in selected:
                raise RuntimeError(f"duplicate C5 prior stable ID: {stable_id}")
            geometry = polygons_from_record(record)
            if geometry is None:
                raise RuntimeError(f"C5 prior has no footprint: {stable_id}")
            target_bbox = candidate_bboxes.get(stable_id) if candidate_bboxes is not None else None
            if candidate_bboxes is not None and target_bbox is None:
                raise RuntimeError(f"C5 candidate bbox is missing: {stable_id}")
            target_geometry = box(*target_bbox) if target_bbox is not None else None
            input_available = True if target_geometry is None else geometry.intersects(
                target_geometry.buffer(association_buffer_m, cap_style=3, join_style=2)
            )
            terrain_values = raster_values_under_geometry(geometry, mvs_grid, mvs_terrain)
            if len(terrain_values):
                ground_to_mvs.append(float(record["ground_height_m"]) - float(np.median(terrain_values)))
            selected[stable_id] = {
                "stable_id": stable_id,
                "footprint_polygon_count": len(record["footprint"]),
                "input_prior_role": record["prior_role"],
                "source_evaluation_class": record["evaluation_class"],
                "primary_c5_eligible_in_source_same_lineage": False,
                "independent_primary_reference_required": True,
                "input_available_within_fixed_buffer": bool(input_available),
                "input_availability_buffer_m": float(association_buffer_m),
                "prior_to_target_bbox_distance_m": 0.0 if target_geometry is None else float(geometry.distance(target_geometry)),
                "target_bbox_overlap_area_m2_diagnostic": None if target_geometry is None else float(geometry.intersection(target_geometry).area),
                "footprint_wkb_hex_internal": geometry.wkb_hex,
            }
    observed = digest.hexdigest()
    if total != spec["bytes"] or observed != spec["attested_sha256"]:
        raise RuntimeError(f"C5 attested output mismatch: {path}")
    input_record = {"path": path.as_posix(), "bytes": total, "sha256": observed, "records": records, "full_passes": 1}
    return selected, input_record, ground_to_mvs


def c5_alignment_from_deltas(ground_to_mvs: Sequence[float]) -> dict[str, Any]:
    if ground_to_mvs:
        values = np.asarray(ground_to_mvs)
        median = float(np.median(values))
        alignment = {
            "status": "READY_MVS_TERRAIN_ONLY_SCALAR",
            "sampled_prior_count": len(values),
            "prior_ground_minus_mvs_terrain_median_m": median,
            "prior_ground_minus_mvs_terrain_mad_m": float(np.median(np.abs(values - median))),
            "translation_applied_to_c5_input_z_m": -median,
            "used_for_reference_construction_or_target_membership": False,
        }
    else:
        alignment = {"status": "MISSING_NO_MVS_TERRAIN_OVERLAP", "sampled_prior_count": 0}
    return alignment


def load_c5_for_candidates_once(
    paths: Sequence[tuple[Path, dict[str, Any]]],
    target_ids: set[str],
    mvs_grid: RecoveryGrid,
    mvs_terrain: np.ndarray,
    candidate_bboxes: dict[str, tuple[float, float, float, float]] | None = None,
    association_buffer_m: float = 0.0,
) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    selected: dict[str, dict[str, Any]] = {}
    inputs: list[dict[str, Any]] = []
    deltas: list[float] = []
    for path, spec in paths:
        file_selected, input_record, file_deltas = load_c5_file_once(
            path,
            spec,
            target_ids,
            mvs_grid,
            mvs_terrain,
            candidate_bboxes,
            association_buffer_m,
        )
        duplicate = sorted(set(selected).intersection(file_selected))
        if duplicate:
            raise RuntimeError(f"duplicate C5 prior stable IDs across inputs: {duplicate[:5]}")
        selected.update(file_selected)
        inputs.append(input_record)
        deltas.extend(file_deltas)
    return selected, inputs, c5_alignment_from_deltas(deltas)


def c5_reference_diagnostics(
    priors: dict[str, dict[str, Any]],
    grid: RecoveryGrid,
    reference: Reference,
    config: dict[str, Any],
) -> tuple[dict[str, list[str]], list[dict[str, Any]]]:
    """Measure prior/reference XY overlap after freeze; never use it for eligibility."""
    x, y = grid.centers()
    labels = reference.labels.ravel()
    component_sizes = {label: len(cells) for label, cells in reference.cells.items()}
    matched: dict[str, list[str]] = {}
    rows: list[dict[str, Any]] = []
    for stable_id in sorted(priors):
        geometry = wkb.loads(bytes.fromhex(priors[stable_id]["footprint_wkb_hex_internal"]))
        bx0, by0, bx1, by1 = geometry.bounds
        x0, y0, _, _ = grid.bbox
        ix0 = max(0, int(math.floor((bx0 - x0) / grid.cell)))
        iy0 = max(0, int(math.floor((by0 - y0) / grid.cell)))
        ix1 = min(grid.nx, int(math.ceil((bx1 - x0) / grid.cell)))
        iy1 = min(grid.ny, int(math.ceil((by1 - y0) / grid.cell)))
        counts: Counter[int] = Counter()
        if ix0 < ix1 and iy0 < iy1:
            iy, ix = np.indices((iy1 - iy0, ix1 - ix0))
            xs = x0 + (ix + ix0 + 0.5) * grid.cell
            ys = y0 + (iy + iy0 + 0.5) * grid.cell
            flat = ((iy + iy0) * grid.nx + (ix + ix0))[contains_xy(geometry, xs, ys)]
            counts.update(int(value) for value in labels[flat] if int(value) in reference.component_ids)
        ids = []
        for label, overlap_cells in sorted(counts.items()):
            reference_id = reference.component_ids[label]
            ids.append(reference_id)
            fraction = overlap_cells / component_sizes[label]
            rows.append(
                {
                    "stable_id": stable_id,
                    "reference_component_id": reference_id,
                    "prior_overlap_cells": overlap_cells,
                    "reference_component_overlap_fraction": f"{fraction:.9f}",
                    "passes_declared_diagnostic_threshold": str(
                        overlap_cells * grid.cell * grid.cell >= float(config["association"]["minimum_intersection_area_m2"])
                        and fraction >= float(config["association"]["minimum_reference_overlap_fraction"])
                    ).lower(),
                    "role": "DIAGNOSTIC_ONLY_NOT_ELIGIBILITY_OR_SCORE_GEOMETRY",
                    "vertical_fields_used": "false",
                }
            )
        matched[stable_id] = sorted(set(ids))
    return matched, rows


class UnionFind:
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


def split_groups(
    units: Sequence[dict[str, Any]], shared_associations: dict[str, list[str]], seed: str
) -> tuple[dict[str, str], dict[str, str]]:
    ids = [row["stable_id"] for row in units]
    union = UnionFind(ids)
    by_tile: dict[str, list[str]] = defaultdict(list)
    by_prior: dict[str, list[str]] = defaultdict(list)
    for row in units:
        by_tile[row["execution_tile_id"]].append(row["stable_id"])
        for prior in shared_associations.get(row["stable_id"], []):
            by_prior[prior].append(row["stable_id"])
    for collection in [*by_tile.values(), *by_prior.values()]:
        for value in collection[1:]:
            union.union(collection[0], value)
    members: dict[str, list[str]] = defaultdict(list)
    for stable_id in ids:
        members[union.find(stable_id)].append(stable_id)
    group_for_id = {}
    for values in members.values():
        group_id = "GROUP_" + sha256_ids(values)[:16]
        for value in values:
            group_for_id[value] = group_id
    eligible = [row for row in units if row["e_paired"] == "true"]
    split_assignment = base.assign_splits(
        [{"stable_id": row["stable_id"], "spatial_group_id": group_for_id[row["stable_id"]], "e_paired": "true"} for row in eligible],
        seed,
    )
    return group_for_id, split_assignment


def execution_tiles_geojson(config: dict[str, Any]) -> dict[str, Any]:
    x0, y0, x1, y1 = (float(value) for value in config["aoi"]["bbox"])
    anchor_x, anchor_y = (float(value) for value in config["eligibility"]["tile_anchor"])
    size = float(config["eligibility"]["spatial_group_cell_m"])
    buffer_m = float(config["eligibility"]["processing_buffer_m"])
    nx = int(math.ceil((x1 - anchor_x) / size))
    ny = int(math.ceil((y1 - anchor_y) / size))
    features = []
    for iy in range(ny):
        for ix in range(nx):
            core = box(anchor_x + ix * size, anchor_y + iy * size, min(anchor_x + (ix + 1) * size, x1), min(anchor_y + (iy + 1) * size, y1))
            buffered = core.buffer(buffer_m, cap_style=3, join_style=2)
            features.append(
                {
                    "type": "Feature",
                    "properties": {"tile_id": f"TILE_{ix:03d}_{iy:03d}", "core_m": size, "buffer_m": buffer_m, "buffer_geometry": mapping(buffered)},
                    "geometry": mapping(core),
                }
            )
    return {
        "type": "FeatureCollection",
        "name": "GATE_S0_FIXED_EXECUTION_TILES",
        "crs": {"type": "name", "properties": {"name": "urn:ogc:def:crs:EPSG::25832"}},
        "features": features,
    }


def execution_tile_id(config: dict[str, Any], target_bbox: Sequence[float]) -> str:
    """Assign an AOI-intersecting target by its AOI-clipped bbox centroid."""
    x0, y0, x1, y1 = (float(value) for value in config["aoi"]["bbox"])
    anchor_x, anchor_y = (float(value) for value in config["eligibility"]["tile_anchor"])
    if not math.isclose(anchor_x, x0, abs_tol=1e-6) or not math.isclose(anchor_y, y0, abs_tol=1e-6):
        raise RuntimeError("execution-tile anchor must equal the frozen AOI lower-left corner")
    size = float(config["eligibility"]["spatial_group_cell_m"])
    clipped = box(*(float(value) for value in target_bbox)).intersection(box(x0, y0, x1, y1))
    if clipped.is_empty or clipped.area <= 0:
        raise RuntimeError("canonical target bbox has no positive-area intersection with the frozen AOI")
    nx = int(math.ceil((x1 - anchor_x) / size))
    ny = int(math.ceil((y1 - anchor_y) / size))
    tile_x = min(nx - 1, max(0, int(math.floor((clipped.centroid.x - anchor_x) / size))))
    tile_y = min(ny - 1, max(0, int(math.floor((clipped.centroid.y - anchor_y) / size))))
    return f"TILE_{tile_x:03d}_{tile_y:03d}"


def write_stage3_smoke_inputs(root: Path) -> dict[str, Any]:
    laz_path = root / "stage3/synthetic_class26.laz"
    header = laspy.LasHeader(point_format=3, version="1.2")
    cloud = laspy.LasData(header)
    ground = [(690900.0 + x, 5336000.0 + y, 500.0, 2) for x in range(8) for y in range(8)]
    building = [(690902.0 + x, 5336002.0 + y, 505.0, 6) for x in range(4) for y in range(4)]
    points = ground + building
    cloud.x = np.array([value[0] for value in points])
    cloud.y = np.array([value[1] for value in points])
    cloud.z = np.array([value[2] for value in points])
    cloud.classification = np.array([value[3] for value in points], dtype=np.uint8)
    output = io.BytesIO()
    cloud.write(output, do_compress=True)
    laz_record = add_once_bytes(laz_path, output.getvalue())
    derived = derive_roofprint("C2_MVS", points)
    footprint = Polygon(derived.coordinates)
    geojson = {
        "type": "FeatureCollection",
        "name": "R_DERIVED_SYNTHETIC_NON_GT",
        "crs": {"type": "name", "properties": {"name": "urn:ogc:def:crs:EPSG::25832"}},
        "features": [{"type": "Feature", "properties": {"building_id": "SYNTHETIC_1"}, "geometry": mapping(footprint)}],
    }
    geo_record = add_once_json(root / "stage3/synthetic_r_derived.geojson", geojson)
    smoke = synthetic_smoke_payload()
    interface_record = add_once_bytes(root / "stage3/common_interface_five_conditions.jsonl", smoke)
    return {
        "input_point_cloud": laz_record,
        "r_derived": geo_record,
        "interface_output": interface_record,
        "condition_labels": list(CONDITIONS),
        "roofprint_protocol": derived.protocol,
        "roofprint_source": derived.source,
        "roofprint_building_point_count": derived.building_point_count,
        "external_roofprint_used": False,
        "quality_or_performance": False,
    }


def build_operation_contract(
    source_commit: str,
    artifact_root: Path,
    config: dict[str, Any],
    git_contract: dict[str, Any],
    acceptance: dict[str, Any],
) -> dict[str, Any]:
    return {
        "task_id": TASK,
        "handoff_id": HANDOFF,
        "source_commit": source_commit,
        "physical_host_id": config["physical_host_id"],
        "artifact_root": artifact_root.resolve().as_posix(),
        "committed_blobs": git_contract["blobs"],
        "accepted_receipt": acceptance,
        "output_namespace": config["output_namespace"],
        "consumer_graph": acceptance_input_specs(config),
        "algorithm_contract": {
            "schema": config["schema"],
            "checkpoint_schema": "jointbuildgs.gate_s0_recovery_checkpoint.v1",
            "grid_cell_m": config["grid"]["cell_m"],
            "crs": config["aoi"]["crs"],
            "aoi_bbox": config["aoi"]["bbox"],
        },
        "prohibited_access_guards": config["guards"],
    }


def expected_checkpoint_stages(config: dict[str, Any], include_roofer: bool) -> dict[int, str]:
    stages = {
        0: "preflight",
        10: "camera_model",
        20: "image_poses",
        25: "sparse_points",
        30: "dense_mvs_and_gravity",
        40: "common_base_complete",
        50: "c1_reference_frozen_pre_c5",
        55: "canonical_199_reference_crosswalk",
        65: "c4_inputs_complete",
        75: "c5_canonical_199_inputs",
        80: "universe_eligibility_split",
        90: "stage3_interface_smoke_inputs",
        100: "technical_summary",
    }
    stages.update({61 + index: f"c4_tile_{tile['tile_id']}" for index, tile in enumerate(config["c4"]["tiles"])})
    stages.update({71 + index: f"c5_input_{index + 1}" for index, _ in enumerate(config["c5"]["selected_prisms"])})
    if include_roofer:
        stages[110] = "roofer_runtime_smoke"
    return stages


def validate_reusable_ledger(
    output_root: Path,
    ledger_path: Path,
    operation_contract: dict[str, Any],
    config: dict[str, Any],
) -> dict[str, Any]:
    ledger = json.loads(ledger_path.read_bytes())
    operation_id = sha256_bytes(canonical_json_bytes(operation_contract))
    include_roofer = ledger_path.name == "completed_ledger_v1.json"
    expected_status = "COMPLETED" if include_roofer else "EXECUTION_COMPLETE_PENDING_ROOFER_SMOKE"
    if ledger.get("schema") != "jointbuildgs.gate_s0_freeze_recovery_no_repeat_ledger.v1" or ledger.get("status") != expected_status:
        raise RuntimeError("reusable ledger schema/status mismatch")
    if ledger.get("operation_identity") != {**operation_contract, "operation_id": operation_id}:
        raise RuntimeError("reusable ledger operation contract mismatch")
    checkpoints = Checkpoints(output_root, operation_id)
    observed_stages = {record["ordinal"]: record["stage"] for record in checkpoints.records}
    if observed_stages != expected_checkpoint_stages(config, include_roofer):
        raise RuntimeError("reusable ledger checkpoint stage map is incomplete or unexpected")
    if ledger.get("checkpoints") != checkpoints.records:
        raise RuntimeError("reusable ledger checkpoint list differs from the durable chain")
    attempt_audit = SourceAttempts(output_root, operation_id, int(config["cost_caps"]["retry_max"])).audit()
    if ledger.get("source_attempts") != attempt_audit:
        raise RuntimeError("reusable ledger source-attempt accounting differs from durable records")
    summary_record = checkpoints.payload(100, "technical_summary")["summary"]
    summary = load_json_record(summary_record, output_root)
    if summary.get("operation_id") != operation_id or summary.get("source_commit") != operation_contract["source_commit"]:
        raise RuntimeError("reusable summary operation mismatch")
    return summary


def execute(source_commit: str, artifact_root: Path) -> dict[str, Any]:
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    if artifact_root.resolve().as_posix() != config["artifact_root"]:
        raise RuntimeError("artifact root differs from frozen config")
    output_root = artifact_root.resolve() / config["output_namespace"]
    runtime_control = enforce_runtime_control(source_commit, artifact_root)
    git_contract = runtime_control["git"]
    acceptance = runtime_control["acceptance"]
    operation_contract = build_operation_contract(source_commit, artifact_root, config, git_contract, acceptance)
    operation_id = sha256_bytes(canonical_json_bytes(operation_contract))
    started_path = output_root / "control/started_v1.json"
    pending_paths = sorted(output_root.rglob(".*.pending")) if output_root.exists() else []
    if pending_paths:
        if not started_path.is_file():
            raise RuntimeError("pending outputs exist before a started operation record")
        started_body = json.loads(started_path.read_bytes())
        if started_body.get("operation_id") != operation_id:
            raise RuntimeError("pending outputs belong to a different operation")
        for pending in pending_paths:
            final = pending.with_name(pending.name[1:-len(".pending")])
            if not allowed_namespace_file(final.relative_to(output_root).as_posix()):
                raise RuntimeError(f"pending output has no authorized final path: {pending}")
    recovered_pending = recover_pending_files(output_root)
    preflight_record = preflight(
        source_commit,
        artifact_root,
        require_clean=True,
        require_acceptance=True,
        allow_resume=True,
    )
    if preflight_record["git"]["blobs"] != git_contract["blobs"] or preflight_record["acceptance"] != acceptance:
        raise RuntimeError("preflight contract changed during pending recovery")
    output_root.mkdir(parents=True, exist_ok=True)
    if started_path.exists():
        started_body = json.loads(started_path.read_bytes())
        if started_body.get("operation_id") != operation_id:
            raise RuntimeError("existing namespace belongs to a different operation")
        started = hash_task_output_once(started_path)
    else:
        started = add_once_json(
            started_path,
            {
                **operation_contract,
                "schema": "jointbuildgs.gate_s0_recovery_started.v1",
                "operation_id": operation_id,
                "created_at": utc_now(),
                "scientific_verdict": None,
            },
        )
    checkpoints = Checkpoints(output_root, operation_id)
    attempts = SourceAttempts(output_root, operation_id, int(config["cost_caps"]["retry_max"]))
    initial_checkpoint_count = len(checkpoints.records)
    for ledger_name in ("completed_ledger_v1.json", "execution_ledger_v1.json"):
        ledger_path = output_root / "control" / ledger_name
        summary_path = output_root / "freeze/technical_summary_v1.json"
        if ledger_path.is_file() and summary_path.is_file():
            summary = validate_reusable_ledger(output_root, ledger_path, operation_contract, config)
            print(json.dumps({"status": "REUSED_COMPLETED_EXECUTION", "operation_id": operation_id, "ledger": ledger_path.as_posix()}, sort_keys=True))
            return summary
    if not checkpoints.completed(0, "preflight"):
        checkpoints.write(0, "preflight", {"preflight": preflight_record, "started": started, "recovered_pending": recovered_pending})

    payload_root = artifact_root / config["consumed_common_base"]["payload_root"]
    camera_spec = config["consumed_common_base"]["camera_model"]
    if checkpoints.completed(10, "camera_model"):
        camera_payload = checkpoints.payload(10, "camera_model")
        camera_record = camera_payload["input"]
        camera_output = camera_payload["output"]
        cameras = load_camera_checkpoint(camera_payload, output_root)
    else:
        camera_attempt = attempts.start("camera_model", [{"path": (payload_root / camera_spec["path"]).as_posix(), "accepted_bytes": camera_spec["expected_bytes"]}])
        camera_record, camera_bytes = hash_capture_once(payload_root / camera_spec["path"], camera_spec["expected_bytes"])
        cameras = base.parse_colmap_cameras(camera_bytes)
        camera_output = add_once_json(output_root / "common/camera_model_index_v1.json", camera_index(cameras))
        checkpoints.write(10, "camera_model", {"attempt": camera_attempt, "input": camera_record, "output": camera_output, "camera_count": len(cameras)})

    pose_spec = config["consumed_common_base"]["image_poses"]
    if checkpoints.completed(20, "image_poses"):
        pose_payload = checkpoints.payload(20, "image_poses")
        pose_record = pose_payload["input"]
        pose_output = pose_payload["output"]
        name_digest = pose_payload["name_set_sha256"]
        images = load_pose_checkpoint(pose_payload, output_root)
    else:
        pose_attempt = attempts.start("image_poses", [{"path": (payload_root / pose_spec["path"]).as_posix(), "accepted_bytes": pose_spec["expected_bytes"]}])
        pose_record, pose_bytes = hash_capture_once(payload_root / pose_spec["path"], pose_spec["expected_bytes"])
        images = base.parse_colmap_images(pose_bytes)
        if len(images) != config["common_source"]["included_pairs"]:
            raise RuntimeError("exact-937 pose count mismatch")
        name_digest = sha256_ids(value["name"] for value in images)
        if name_digest != config["common_source"]["included_basename_set_sha256"]:
            raise RuntimeError("exact-937 pose-name set mismatch")
        pose_output = add_once_json(output_root / "common/pose_index_v1.json", pose_index(images))
        checkpoints.write(20, "image_poses", {"attempt": pose_attempt, "input": pose_record, "output": pose_output, "pose_count": len(images), "name_set_sha256": name_digest})
    if len(images) != config["common_source"]["included_pairs"] or name_digest != config["common_source"]["included_basename_set_sha256"]:
        raise RuntimeError("resumed exact-937 pose checkpoint mismatch")

    sparse_spec = config["consumed_common_base"]["sparse_points"]
    if checkpoints.completed(25, "sparse_points"):
        sparse_payload = checkpoints.payload(25, "sparse_points")
        sparse_record = sparse_payload["input"]
        sparse_point_count = int(sparse_payload["point_count"])
    else:
        sparse_attempt = attempts.start("sparse_points", [{"path": (payload_root / sparse_spec["path"]).as_posix(), "accepted_bytes": sparse_spec["expected_bytes"]}])
        sparse_record, sparse_bytes = hash_capture_once(payload_root / sparse_spec["path"], sparse_spec["expected_bytes"])
        sparse_point_count = struct.unpack("<Q", sparse_bytes[:8])[0]
        checkpoints.write(25, "sparse_points", {"attempt": sparse_attempt, "input": sparse_record, "point_count": sparse_point_count, "role": "FROZEN_C3_C5_INITIALIZATION_INPUT"})

    aoi = tuple(float(value) for value in config["aoi"]["bbox"])
    cell = float(config["grid"]["cell_m"])
    dense_spec = config["consumed_common_base"]["dense_ply"]
    if checkpoints.completed(30, "dense_mvs_and_gravity"):
        dense_payload = checkpoints.payload(30, "dense_mvs_and_gravity")
        dense_record = dense_payload["input"]
        mvs_grid_record = dense_payload["grid"]
        mvs_grid = load_grid_record(mvs_grid_record, output_root, aoi, cell)
        mvs_ply = dense_payload["derivative"]
        verify_task_record(mvs_ply, output_root)
        gravity = dense_payload["gravity"]
    else:
        mvs_grid = RecoveryGrid(aoi, cell)
        dense_attempt = attempts.start("dense_mvs", [{"path": (payload_root / dense_spec["path"]).as_posix(), "accepted_bytes": dense_spec["expected_bytes"]}])
        dense_record, _unfiltered_gravity = base.hash_ply_and_grid(
            payload_root / dense_spec["path"], mvs_grid, (690953.0, 5336071.0, 604.0)
        )
        dense_record.update(
            {
                "path": (payload_root / dense_spec["path"]).as_posix(),
                "full_passes": 1,
                "digest_method": "same_stream_as_dense_grid_consumer",
            }
        )
        if dense_record["bytes"] != dense_spec["expected_bytes"]:
            raise RuntimeError("dense PLY byte mismatch")
        mvs_grid_record = add_once_bytes(output_root / "common/mvs_grid_v1.npz", grid_npz_bytes(mvs_grid))
        mvs_terrain = terrain_envelope(mvs_grid, config["grid"]["terrain_filter_windows_cells"])
        gravity = filtered_terrain_gravity(mvs_grid, mvs_terrain)
        mvs_mask = input_support_mask(mvs_grid, mvs_terrain, config)
        mvs_ply = write_grid_ply_with_mask(output_root / "common/mvs_class26_v1.ply", mvs_grid, mvs_terrain, mvs_mask)
        checkpoints.write(30, "dense_mvs_and_gravity", {"attempt": dense_attempt, "input": dense_record, "grid": mvs_grid_record, "derivative": mvs_ply, "gravity": gravity})
    mvs_terrain = terrain_envelope(mvs_grid, config["grid"]["terrain_filter_windows_cells"])
    mvs_mask = input_support_mask(mvs_grid, mvs_terrain, config)
    if not checkpoints.completed(40, "common_base_complete"):
        checkpoints.write(
            40,
            "common_base_complete",
            {
                "consumer_bytes": camera_record["bytes"] + pose_record["bytes"] + sparse_record["bytes"] + dense_record["bytes"],
                "consumer_files": 4,
                "not_consumed": config["consumed_common_base"]["not_consumed"],
                "component_contract": {"camera_pose_model": "ON", "sparse_points": "ON", "dense_ply": "ON", "gravity": "ON"},
            },
        )

    reference_namespace = sha256_bytes(canonical_json_bytes({"source_sha256": config["c1"]["attested_sha256"], "aoi": config["aoi"], "grid": config["grid"]}))
    ref_fields = ["reference_component_id", "cell_ix", "cell_iy", "cell_x", "cell_y", "relative_roof_height_m", "local_plane_rmse_m", "within_cell_z_std_m", "normal_z"]
    if checkpoints.completed(50, "c1_reference_frozen_pre_c5"):
        c1_payload = checkpoints.payload(50, "c1_reference_frozen_pre_c5")
        c1_input = c1_payload["input"]
        c1_grid_record = c1_payload["grid"]
        c1_grid = load_grid_record(c1_grid_record, output_root, aoi, cell)
        c1_ply = c1_payload["derivative"]
        verify_task_record(c1_ply, output_root)
        ref_record = c1_payload["reference"]
        reference = extract_reference(c1_grid, config, reference_namespace)
        ref_rows = reference_rows(c1_grid, reference)
        if sha256_bytes(canonical_csv_bytes(ref_fields, ref_rows)) != ref_record["sha256"]:
            raise RuntimeError("resumed C1 reference bytes differ from frozen checkpoint")
        verify_task_record(ref_record, output_root)
    else:
        c1_grid = RecoveryGrid(aoi, cell)
        c1_path = artifact_root / config["c1"]["path"]
        c1_attempt = attempts.start("c1_reference", [{"path": c1_path.as_posix(), "accepted_bytes": config["c1"]["bytes"], "attested_sha256": config["c1"]["attested_sha256"]}])
        if c1_path.stat().st_size != config["c1"]["bytes"]:
            raise RuntimeError("C1 runtime stat differs from frozen attestation")
        c1_input = base.process_laz_once(c1_path, c1_grid, transform=True)
        if c1_input["source_file_size_bytes"] != config["c1"]["bytes"]:
            raise RuntimeError("C1 decoder stat mismatch")
        c1_grid_record = add_once_bytes(output_root / "reference/c1_grid_v1.npz", grid_npz_bytes(c1_grid))
        reference = extract_reference(c1_grid, config, reference_namespace)
        c1_ply = write_grid_ply_with_mask(output_root / "reference/c1_class26_v1.ply", c1_grid, reference.terrain, reference.keep)
        ref_rows = reference_rows(c1_grid, reference)
        ref_record = add_once_csv(output_root / "reference/uasref_cells_pre_c5_v1.csv", ref_fields, ref_rows)
        checkpoints.write(
            50,
            "c1_reference_frozen_pre_c5",
            {
                "input": c1_input,
                "attempt": c1_attempt,
                "input_full_hashes": 0,
                "grid": c1_grid_record,
                "derivative": c1_ply,
                "reference": ref_record,
                "reference_components": len(reference.component_ids),
                "reference_cells": len(ref_rows),
                "reference_digest_pre_c5": ref_record["sha256"],
                "reference_id_namespace_hash": reference_namespace,
                "construction_inputs": ["UAS_LIDAR_XYZ", "FROZEN_CONFIG"],
                "prohibited_construction_inputs_used": [],
            },
        )
    pre_c5_digest = ref_record["sha256"]

    buildings, candidate_record = load_candidate_buildings(config)
    reference_by_building, reference_score_cells, crosswalk_rows = crosswalk_reference_to_buildings(
        c1_grid, reference, buildings, float(config["eligibility"]["reference_id_crosswalk_buffer_m"])
    )
    crosswalk_fields = ["stable_id", "reference_component_id", "component_cells_inside_original_bbox", "component_centroid_inside_fixed_buffer", "crosswalk_buffer_m", "lod2_geometry_used_to_construct_reference", "lod2_geometry_used_as_score_geometry", "score_support_is_independent_uas_cells_clipped_to_target_bbox", "crosswalk_stage"]
    if checkpoints.completed(55, "canonical_199_reference_crosswalk"):
        crosswalk_payload = checkpoints.payload(55, "canonical_199_reference_crosswalk")
        crosswalk_record = crosswalk_payload["crosswalk"]
        if sha256_bytes(canonical_csv_bytes(crosswalk_fields, crosswalk_rows)) != crosswalk_record["sha256"]:
            raise RuntimeError("canonical-199 crosswalk changed on resume")
        verify_task_record(crosswalk_record, output_root)
    else:
        crosswalk_record = add_once_csv(output_root / "reference/reference_id_crosswalk_v1.csv", crosswalk_fields, crosswalk_rows)
        checkpoints.write(55, "canonical_199_reference_crosswalk", {"candidate_ledger": candidate_record, "crosswalk": crosswalk_record, "buildings_with_reference": sum(bool(value) for value in reference_by_building.values()), "independent_reference_score_cells": sum(reference_score_cells.values()), "reference_geometry_modified": False})

    c4_grid = RecoveryGrid(aoi, cell)
    c4_inputs = []
    for index, tile in enumerate(config["c4"]["tiles"]):
        ordinal = 61 + index
        stage = f"c4_tile_{tile['tile_id']}"
        if checkpoints.completed(ordinal, stage):
            tile_payload = checkpoints.payload(ordinal, stage)
            tile_record = tile_payload["input"]
            tile_grid = load_grid_record(tile_payload["grid"], output_root, aoi, cell)
        else:
            tile_grid = RecoveryGrid(aoi, cell)
            tile_path = artifact_root / tile["path"]
            tile_attempt = attempts.start(stage, [{"path": tile_path.as_posix(), "accepted_bytes": tile["bytes"], "attested_sha256": tile["attested_sha256"]}])
            if tile_path.stat().st_size != tile["bytes"]:
                raise RuntimeError(f"C4 runtime stat mismatch: {tile['tile_id']}")
            tile_record = base.process_laz_once(tile_path, tile_grid, transform=False)
            if tile_record["source_file_size_bytes"] != tile["bytes"]:
                raise RuntimeError(f"C4 decoder stat mismatch: {tile['tile_id']}")
            tile_grid_record = add_once_bytes(output_root / f"inputs/c4_{tile['tile_id']}_grid_v1.npz", grid_npz_bytes(tile_grid))
            checkpoints.write(ordinal, stage, {"attempt": tile_attempt, "input": tile_record, "grid": tile_grid_record, "attested_sha256_reused": tile["attested_sha256"], "full_hashes": 0})
        c4_inputs.append(tile_record)
        merge_grid(c4_grid, tile_grid)
    c4_class2 = c4_grid.class2_min_z.reshape(c4_grid.ny, c4_grid.nx)
    c4_terrain = terrain_envelope_from_array(c4_class2, config["grid"]["terrain_filter_windows_cells"])
    overlap = np.isfinite(c4_class2) & np.isfinite(mvs_grid.min_z.reshape(mvs_grid.ny, mvs_grid.nx))
    if not np.any(overlap):
        raise RuntimeError("C4-to-MVS terrain overlap is empty")
    c4_minus_mvs = c4_terrain[overlap] - mvs_terrain[overlap]
    c4_offset = float(np.median(c4_minus_mvs))
    c4_mad = float(np.median(np.abs(c4_minus_mvs - c4_offset)))
    c4_top = c4_grid.class6_max_z.reshape(c4_grid.ny, c4_grid.nx) - c4_offset
    c4_mask = np.isfinite(c4_top) & (c4_grid.class6_count.reshape(c4_grid.ny, c4_grid.nx) >= int(config["grid"]["minimum_points_per_cell"])) & ((c4_top - mvs_terrain) >= float(config["grid"]["minimum_height_above_terrain_m"]))
    c4_to_mvs = {
        "status": "READY_MVS_TERRAIN_ONLY_SCALAR",
        "overlap_cells": int(np.count_nonzero(overlap)),
        "c4_terrain_minus_mvs_terrain_median_m": c4_offset,
        "c4_terrain_minus_mvs_terrain_mad_m": c4_mad,
        "translation_applied_to_c4_input_z_m": -c4_offset,
    }
    if checkpoints.completed(65, "c4_inputs_complete"):
        c4_payload = checkpoints.payload(65, "c4_inputs_complete")
        c4_grid_record = c4_payload["grid"]
        if sha256_bytes(grid_npz_bytes(c4_grid)) != c4_grid_record["sha256"]:
            raise RuntimeError("resumed C4 aggregate differs from tile checkpoint merge")
        verify_task_record(c4_grid_record, output_root)
        c4_ply = c4_payload["derivative"]
        verify_task_record(c4_ply, output_root)
        if canonical_json_bytes(c4_to_mvs) != canonical_json_bytes(c4_payload["input_side_alignment_measurement"]):
            raise RuntimeError("resumed C4 alignment measurement changed")
    else:
        c4_grid_record = add_once_bytes(output_root / "inputs/c4_grid_v1.npz", grid_npz_bytes(c4_grid))
        c4_ply = write_c4_classified_ply(output_root / "inputs/c4_class26_v1.ply", c4_grid, mvs_terrain, c4_mask, -c4_offset)
        checkpoints.write(65, "c4_inputs_complete", {"inputs": c4_inputs, "input_full_hashes": 0, "grid": c4_grid_record, "derivative": c4_ply, "input_side_alignment_measurement": c4_to_mvs, "uas_roof_used_for_registration": False, "other_provider_classes_promoted": False})

    target_ids = {item["stable_id"] for item in buildings}
    candidate_bboxes = {item["stable_id"]: item["bbox"] for item in buildings}
    c5_priors: dict[str, dict[str, Any]] = {}
    c5_inputs: list[dict[str, Any]] = []
    c5_deltas: list[float] = []
    for index, item in enumerate(config["c5"]["selected_prisms"]):
        ordinal = 71 + index
        stage = f"c5_input_{index + 1}"
        if checkpoints.completed(ordinal, stage):
            payload = checkpoints.payload(ordinal, stage)
            file_selected = {row["stable_id"]: row for row in payload["selected_rows"]}
            input_record = payload["input"]
            deltas = [float(value) for value in payload["ground_to_mvs_deltas_m"]]
        else:
            path = artifact_root / item["path"]
            c5_attempt = attempts.start(stage, [{"path": path.as_posix(), "accepted_bytes": item["bytes"], "attested_sha256": item["attested_sha256"]}])
            if path.stat().st_size != item["bytes"]:
                raise RuntimeError(f"C5 runtime stat mismatch: {item['path']}")
            file_selected, input_record, deltas = load_c5_file_once(
                path,
                item,
                target_ids,
                mvs_grid,
                mvs_terrain,
                candidate_bboxes,
                float(config["association"]["maximum_input_availability_distance_m"]),
            )
            checkpoints.write(ordinal, stage, {"attempt": c5_attempt, "input": input_record, "selected_rows": [file_selected[key] for key in sorted(file_selected)], "ground_to_mvs_deltas_m": deltas, "source_lod2_reads": 0})
        duplicate = sorted(set(c5_priors).intersection(file_selected))
        if duplicate:
            raise RuntimeError(f"duplicate C5 prior stable IDs across checkpoints: {duplicate[:5]}")
        c5_priors.update(file_selected)
        c5_inputs.append(input_record)
        c5_deltas.extend(deltas)
    c5_alignment = c5_alignment_from_deltas(c5_deltas)
    if set(c5_priors) != target_ids:
        raise RuntimeError(f"C5 prior ID set is not exact canonical 199: missing={len(target_ids - set(c5_priors))} extra={len(set(c5_priors) - target_ids)}")
    if not all(value["input_available_within_fixed_buffer"] for value in c5_priors.values()):
        raise RuntimeError("one or more canonical C5 priors are outside the fixed 10 m target buffer")
    c5_fields = ["stable_id", "footprint_polygon_count", "input_prior_role", "source_evaluation_class", "primary_c5_eligible_in_source_same_lineage", "independent_primary_reference_required", "input_available_within_fixed_buffer", "input_availability_buffer_m", "prior_to_target_bbox_distance_m", "target_bbox_overlap_area_m2_diagnostic"]
    c5_rows = [{key: c5_priors[stable_id][key] for key in c5_fields} for stable_id in sorted(c5_priors)]
    c5_reference_matches, c5_diagnostic_rows = c5_reference_diagnostics(c5_priors, c1_grid, reference, config)
    c5_diagnostic_fields = ["stable_id", "reference_component_id", "prior_overlap_cells", "reference_component_overlap_fraction", "passes_declared_diagnostic_threshold", "role", "vertical_fields_used"]
    post_ref_bytes = canonical_csv_bytes(ref_fields, reference_rows(c1_grid, reference))
    if pre_c5_digest != sha256_bytes(post_ref_bytes):
        raise RuntimeError("reference digest changed during C5 association")
    if checkpoints.completed(75, "c5_canonical_199_inputs"):
        c5_payload = checkpoints.payload(75, "c5_canonical_199_inputs")
        c5_record = c5_payload["candidate_priors"]
        if sha256_bytes(canonical_csv_bytes(c5_fields, c5_rows)) != c5_record["sha256"]:
            raise RuntimeError("resumed C5 canonical-199 inventory changed")
        verify_task_record(c5_record, output_root)
        c5_diagnostic_record = c5_payload["reference_overlap_diagnostic"]
        if sha256_bytes(canonical_csv_bytes(c5_diagnostic_fields, c5_diagnostic_rows)) != c5_diagnostic_record["sha256"]:
            raise RuntimeError("resumed C5/reference diagnostic changed")
        verify_task_record(c5_diagnostic_record, output_root)
        if canonical_json_bytes(c5_alignment) != canonical_json_bytes(c5_payload["input_side_alignment"]):
            raise RuntimeError("resumed C5 input alignment changed")
    else:
        c5_record = add_once_csv(output_root / "inputs/c5_canonical_199_prior_inventory_v1.csv", c5_fields, c5_rows)
        c5_diagnostic_record = add_once_csv(output_root / "inputs/c5_reference_overlap_diagnostic_v1.csv", c5_diagnostic_fields, c5_diagnostic_rows)
        checkpoints.write(75, "c5_canonical_199_inputs", {"inputs": c5_inputs, "candidate_priors": c5_record, "reference_overlap_diagnostic": c5_diagnostic_record, "candidate_prior_count": len(c5_priors), "candidate_id_set_sha256": sha256_ids(c5_priors), "exact_canonical_199_id_set": True, "all_inputs_available_within_fixed_buffer": True, "input_side_alignment": c5_alignment, "reference_digest_before": pre_c5_digest, "reference_digest_after_in_memory_reserialization": sha256_bytes(post_ref_bytes), "reference_cells_changed": 0, "source_lod2_reads": 0, "c5_vertical_fields_used_for_reference_or_membership": False})

    if checkpoints.completed(80, "universe_eligibility_split"):
        universe_payload = checkpoints.payload(80, "universe_eligibility_split")
        eligibility_record = universe_payload["eligibility"]
        units = read_csv_record(eligibility_record, output_root)
        tile_record = universe_payload["execution_tiles"]
        verify_task_record(tile_record, output_root)
    else:
        units = []
        for building in buildings:
            stable_id = building["stable_id"]
            bbox_value = building["bbox"]
            terrain_values = raster_values_under_geometry(box(*bbox_value), mvs_grid, mvs_terrain)
            if len(terrain_values):
                ground = float(np.median(terrain_values))
                z_envelope = config["eligibility"]["view_support_relative_z_envelope_m"]
                support = base.camera_view_support(bbox_value, (ground + float(z_envelope[0]), ground + float(z_envelope[1])), cameras, images, 0.0)
            else:
                support = 0
            mvs_cells = mvs_grid.coverage(bbox_value, mvs_mask.ravel())
            c4_cells = c4_grid.coverage(bbox_value, c4_mask.ravel())
            u_target = support >= int(config["eligibility"]["minimum_image_views"])
            reference_ids = reference_by_building.get(stable_id, [])
            independent_reference_cells = reference_score_cells.get(stable_id, 0)
            c5_available = stable_id in c5_priors and bool(c5_priors[stable_id]["input_available_within_fixed_buffer"])
            alignment_ready = c5_alignment["status"] == "READY_MVS_TERRAIN_ONLY_SCALAR"
            e_paired = u_target and independent_reference_cells >= int(config["eligibility"]["minimum_condition_cells"]) and mvs_cells >= int(config["eligibility"]["minimum_condition_cells"]) and c4_cells >= int(config["eligibility"]["minimum_condition_cells"]) and c5_available and alignment_ready
            units.append(
                {
                    "stable_id": stable_id,
                    "unit_semantics": "CANONICAL_SCENE_AOI_BUILDING_ID_EVALUATED_BY_INDEPENDENT_UAS_ROOF_SUPPORT",
                    "bbox_min_x": f"{bbox_value[0]:.3f}", "bbox_min_y": f"{bbox_value[1]:.3f}", "bbox_max_x": f"{bbox_value[2]:.3f}", "bbox_max_y": f"{bbox_value[3]:.3f}",
                    "independent_reference_component_ids": ";".join(reference_ids),
                    "independent_reference_component_count": len(reference_ids),
                    "independent_reference_score_cells": independent_reference_cells,
                    "current_image_view_support": support,
                    "mvs_support_cells": mvs_cells,
                    "c4_support_cells": c4_cells,
                    "c5_prior_available_by_stable_id": str(c5_available).lower(),
                    "c5_input_alignment_ready": str(alignment_ready).lower(),
                    "u_target": str(u_target).lower(),
                    "e_paired": str(e_paired).lower(),
                    "execution_tile_id": execution_tile_id(config, bbox_value),
                    "spatial_group_id": "",
                    "split": "NOT_E_PAIRED",
                    "held_out_accessed": "false",
                    "exclusion_reason": "" if e_paired else ";".join(
                        reason for condition, reason in [
                            (not u_target, "LT_2_IMAGE_VIEWS"),
                            (independent_reference_cells < config["eligibility"]["minimum_condition_cells"], "INSUFFICIENT_INDEPENDENT_UAS_REFERENCE_SUPPORT"),
                            (mvs_cells < config["eligibility"]["minimum_condition_cells"], "INSUFFICIENT_MVS_SUPPORT"),
                            (c4_cells < config["eligibility"]["minimum_condition_cells"], "INSUFFICIENT_C4_SUPPORT"),
                            (not c5_available, "C5_PRIOR_STABLE_ID_MISSING"),
                            (not alignment_ready, "C5_MVS_TERRAIN_ALIGNMENT_MISSING"),
                        ] if condition
                    ),
                }
            )
        shared_group_map = {
            stable_id: sorted(set(reference_by_building.get(stable_id, []) + c5_reference_matches.get(stable_id, [])))
            for stable_id in target_ids
        }
        group_for_id, split_assignment = split_groups(units, shared_group_map, config["eligibility"]["split_seed"])
        for row in units:
            row["spatial_group_id"] = group_for_id[row["stable_id"]]
            if row["e_paired"] == "true":
                row["split"] = split_assignment[row["spatial_group_id"]]
        eligibility_record = add_once_csv(output_root / "freeze/eligibility_ledger_v1.csv", list(units[0]) if units else [], units)
        tile_record = add_once_json(output_root / "freeze/execution_tiles_v1.geojson", execution_tiles_geojson(config))
    u_ids = [row["stable_id"] for row in units if row["u_target"] == "true"]
    e_ids = [row["stable_id"] for row in units if row["e_paired"] == "true"]
    split_counts = Counter(row["split"] for row in units if row["e_paired"] == "true")
    if len(units) != config["eligibility"]["candidate_count"]:
        raise RuntimeError("eligibility ledger does not contain canonical 199 candidates")
    if not checkpoints.completed(80, "universe_eligibility_split"):
        checkpoints.write(80, "universe_eligibility_split", {"eligibility": eligibility_record, "execution_tiles": tile_record, "canonical_candidate_count": len(units), "u_target_count": len(u_ids), "u_target_id_set_sha256": sha256_ids(u_ids), "e_paired_count": len(e_ids), "e_paired_id_set_sha256": sha256_ids(e_ids), "split_counts": dict(sorted(split_counts.items())), "held_out_accessed": False, "method_failures_are_g0_not_exclusions": True})

    if checkpoints.completed(90, "stage3_interface_smoke_inputs"):
        stage3_payload = checkpoints.payload(90, "stage3_interface_smoke_inputs")
        stage3 = {key: value for key, value in stage3_payload.items() if key not in {"roofer_image", "runtime_smoke_status"}}
        for name in ("input_point_cloud", "r_derived", "interface_output"):
            verify_task_record(stage3[name], output_root)
    else:
        stage3 = write_stage3_smoke_inputs(output_root)
        checkpoints.write(90, "stage3_interface_smoke_inputs", {**stage3, "roofer_image": config["stage3"]["roofer_image"], "runtime_smoke_status": "PENDING_HOST_ORCHESTRATOR"})

    required_splits = ("development", "validation", "held_out")
    split_complete = all(split_counts.get(name, 0) > 0 for name in required_splits)
    if not e_ids:
        technical_status = "BLOCKED_E_PAIRED_EMPTY"
    elif not split_complete:
        technical_status = "BLOCKED_SPLIT_DEGENERATE"
    else:
        technical_status = "TECHNICAL_EVIDENCE_COMPLETE_PENDING_ROOFER_SMOKE_AND_REVIEWS"
    summary_body = {
        "schema": "jointbuildgs.gate_s0_freeze_recovery_summary.v1",
        "task_id": TASK,
        "handoff_id": HANDOFF,
        "operation_id": operation_id,
        "source_commit": source_commit,
        "status": technical_status,
        "common_source": config["common_source"],
        "aoi": config["aoi"],
        "consumer_graph": {
            "files": 4,
            "bytes": camera_record["bytes"] + pose_record["bytes"] + sparse_record["bytes"] + dense_record["bytes"],
            "camera_pose_model": "READY",
            "sparse_points": "READY",
            "sparse_point_count": sparse_point_count,
            "dense_mvs": "READY",
            "gravity": "READY",
            "depth": "READY_OFF",
            "normal_map_supervision": "READY_OFF",
            "confidence": "READY_OFF",
            "segmentation": "READY_OFF",
        },
        "reference": {"uasref_component_count": len(reference.component_ids), "cells": len(ref_rows), "digest": pre_c5_digest, "digest_equal_after_c5_in_memory_reserialization": True, "canonical_buildings_with_reference": sum(bool(value) for value in reference_by_building.values()), "unit_semantics": "CANONICAL_199_BUILDINGS_WITH_INDEPENDENT_UAS_ROOF_SUPPORT_REFERENCE"},
        "c1": {"evaluation_class": "SELF_REFERENCE_UPPER_BASELINE", "independent_g3_g4_accuracy_claim_allowed": False},
        "c5": {"prior_role": config["c5"]["role"], "candidate_prior_count": len(c5_priors), "exact_canonical_199_id_set": set(c5_priors) == target_ids, "all_inputs_available_within_fixed_buffer": all(value["input_available_within_fixed_buffer"] for value in c5_priors.values()), "primary_reference": "INDEPENDENT_UAS", "input_side_alignment": c5_alignment, "source_lod2_reads": 0, "source_same_lineage_scoring": False},
        "universe": {"canonical_scene_aoi_candidate_count": len(units), "canonical_candidate_id_set_sha256": candidate_record["stable_id_set_sha256"], "u_target_count": len(u_ids), "u_target_id_set_sha256": sha256_ids(u_ids), "e_paired_count": len(e_ids), "e_paired_id_set_sha256": sha256_ids(e_ids), "split_counts": dict(sorted(split_counts.items())), "required_splits_nonempty": split_complete, "held_out_accessed": False},
        "registration": {"c3_to_c5_uas_roof_used": False, "c4_input_side_reference": "MVS_TERRAIN_ONLY", "c5_input_side_reference": "MVS_TERRAIN_ONLY", "primary_evaluation_vertical_scope": config["evaluation"]["primary_vertical_scope"], "absolute_z_metrics_enabled": False},
        "stage3": {**stage3, "roofer_runtime_smoke": "PENDING_HOST_ORCHESTRATOR"},
        "guards": config["guards"],
        "scientific_verdict": None,
    }
    if checkpoints.completed(100, "technical_summary"):
        summary_record = checkpoints.payload(100, "technical_summary")["summary"]
        summary = load_json_record(summary_record, output_root)
        if canonical_json_bytes(summary) != canonical_json_bytes(summary_body):
            raise RuntimeError("resumed technical summary differs from checkpointed result")
    else:
        summary = summary_body
        summary_record = add_once_json(output_root / "freeze/technical_summary_v1.json", summary)
        checkpoints.write(100, "technical_summary", {"summary": summary_record})
    attempt_audit = attempts.audit()
    attempt_counts = attempt_audit["attempt_counts"]
    execution_ledger = {
        "schema": "jointbuildgs.gate_s0_freeze_recovery_no_repeat_ledger.v1",
        "task_id": TASK,
        "handoff_id": HANDOFF,
        "status": "EXECUTION_COMPLETE_PENDING_ROOFER_SMOKE",
        "operation_identity": {**operation_contract, "operation_id": operation_id},
        "checkpoints": checkpoints.records,
        "source_attempts": attempt_audit,
        "read_accounting": {
            "common_base_completed_consumer_read_and_hash_bytes": camera_record["bytes"] + pose_record["bytes"] + sparse_record["bytes"] + dense_record["bytes"],
            "common_base_consumer_files": 4,
            "common_base_source_open_attempts": sum(attempt_counts.get(name, 0) for name in ("camera_model", "image_poses", "sparse_points", "dense_mvs")),
            "common_base_context_only_bytes_read_or_hashed": 0,
            "c1_completed_decode_passes": 1,
            "c1_source_open_attempts": attempt_counts.get("c1_reference", 0),
            "c1_hash_passes": 0,
            "c4_completed_decode_passes": 4,
            "c4_source_open_attempts": sum(attempt_counts.get(f"c4_tile_{tile['tile_id']}", 0) for tile in config["c4"]["tiles"]),
            "c4_hash_passes": 0,
            "c5_completed_jsonl_processing_and_digest_passes": 2,
            "c5_source_open_attempts": sum(attempt_counts.get(f"c5_input_{index + 1}", 0) for index in range(len(config["c5"]["selected_prisms"]))),
            "incomplete_attempt_bytes_read": "UNKNOWN_BY_CRASH_BOUNDARY_ATTEMPTS_DURABLY_COUNTED",
            "r1_images_opf_rehashes": 0,
            "source_lod2_reads": 0,
            "failed_namespace_reads": 0,
            "stereo_entries_enumerated": 0,
        },
        "resume_audit": {
            "checkpoints_reused_at_invocation_start": initial_checkpoint_count,
            "pending_outputs_recovered_without_scientific_source_read": recovered_pending,
        },
        "repeat_contract": "A repeated execute validates and reuses completed fsync checkpoints without reopening their scientific sources. Only an incomplete stage may be decoded again.",
        "scientific_verdict": None,
    }
    ledger_record = add_once_json(output_root / "control/execution_ledger_v1.json", execution_ledger)
    print(json.dumps({"status": "EXECUTION_COMPLETE_PENDING_ROOFER_SMOKE", "operation_id": operation_id, "summary": summary_record, "ledger": ledger_record}, sort_keys=True))
    return summary


def add_repo_once(path: Path, data: bytes) -> dict[str, Any]:
    record = add_once_bytes(path, data)
    record["path"] = path.relative_to(REPO).as_posix()
    return record


def hash_task_output_once(path: Path) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise RuntimeError(f"Roofer output is not a regular non-symlink file: {path}")
    digest = hashlib.sha256()
    total = 0
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
            total += len(chunk)
    return {"path": path.as_posix(), "bytes": total, "sha256": digest.hexdigest(), "full_hash_passes": 1}


def validate_roofer_json(path: Path) -> dict[str, Any]:
    if path.suffix == ".jsonl":
        values = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    else:
        values = [json.loads(path.read_text(encoding="utf-8"))]
    feature_count = 0
    header_count = 0
    for value in values:
        if not isinstance(value, dict):
            raise RuntimeError(f"Roofer JSON record is not an object: {path}")
        city_objects = value.get("CityObjects")
        vertices = value.get("vertices")
        geometry_present = (
            isinstance(city_objects, dict)
            and bool(city_objects)
            and isinstance(vertices, list)
            and bool(vertices)
            and any(
                isinstance(item, dict)
                and isinstance(item.get("geometry"), list)
                and any(isinstance(geometry, dict) and bool(geometry.get("boundaries")) for geometry in item["geometry"])
                for item in city_objects.values()
            )
        )
        if value.get("type") == "CityJSONFeature" and geometry_present:
            feature_count += 1
        elif value.get("type") == "CityJSON" and isinstance(city_objects, dict):
            header_count += 1
            feature_count += int(geometry_present)
    if feature_count < 1:
        raise RuntimeError(f"Roofer output contains no CityJSON geometry feature: {path}")
    return {"records": len(values), "cityjson_headers": header_count, "geometry_features": feature_count}


def record_roofer_smoke(
    artifact_root: Path,
    exit_code: int,
    observed_image: str,
    observed_image_id: str,
    observed_project_image_id: str,
) -> dict[str, Any]:
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    output_root = artifact_root.resolve() / config["output_namespace"]
    execution_path = output_root / "control/execution_ledger_v1.json"
    sealed_attempt = output_root / "stage3/roofer_smoke_sealed"
    output_dir = sealed_attempt / "output"
    log_path = sealed_attempt / "runtime.log"
    receipt_path = output_root / "stage3/roofer_runtime_smoke_receipt_v1.json"
    if observed_image != config["stage3"]["roofer_image"]:
        raise RuntimeError("observed Roofer image does not match the pinned image")
    if observed_image_id != config["stage3"]["roofer_image_id"]:
        raise RuntimeError("observed Roofer image ID does not match the pinned image ID")
    if not execution_path.is_file() or not log_path.is_file() or not output_dir.is_dir():
        raise RuntimeError("execution ledger, Roofer log and output directory are required")
    execution = json.loads(execution_path.read_bytes())
    operation_id = execution.get("operation_identity", {}).get("operation_id")
    source_commit = execution.get("operation_identity", {}).get("source_commit")
    if not operation_id or not source_commit:
        raise RuntimeError("execution ledger operation identity is incomplete")
    runtime_control = enforce_runtime_control(source_commit, artifact_root)
    expected_project_image_id = runtime_control["acceptance"]["project_docker_image_id"]
    if observed_project_image_id != expected_project_image_id:
        raise RuntimeError("observed project Docker image ID does not match acceptance")
    operation_contract = dict(execution["operation_identity"])
    operation_contract.pop("operation_id", None)
    validate_reusable_ledger(output_root, execution_path, operation_contract, config)
    checkpoints = Checkpoints(output_root, operation_id)
    stage3_payload = checkpoints.payload(90, "stage3_interface_smoke_inputs")
    smoke_inputs = {}
    for name in ("input_point_cloud", "r_derived", "interface_output"):
        path = verify_task_record(stage3_payload[name], output_root)
        smoke_inputs[name] = hash_task_output_once(path)
    outputs = [hash_task_output_once(path) for path in sorted(output_dir.rglob("*")) if path.is_file()]
    json_outputs = [record for record in outputs if record["path"].endswith((".jsonl", ".json"))]
    validations = []
    validation_error = None
    try:
        validations = [validate_roofer_json(Path(record["path"])) for record in json_outputs]
    except (RuntimeError, ValueError, json.JSONDecodeError) as error:
        validation_error = str(error)
    status = "PASS" if exit_code == 0 and json_outputs and validation_error is None else "FAIL"
    command_contract = {
        "args": config["stage3"]["command_args"],
        "input": "stage3/synthetic_class26.laz",
        "roofprint": "stage3/synthetic_r_derived.geojson",
        "output": "stage3/roofer_output",
    }
    receipt = {
        "schema": "jointbuildgs.gate_s0_recovery_roofer_runtime_smoke.v1",
        "task_id": TASK,
        "handoff_id": HANDOFF,
        "operation_id": operation_id,
        "source_commit": source_commit,
        "status": status,
        "exit_code": exit_code,
        "observed_image": observed_image,
        "observed_image_id": observed_image_id,
        "observed_project_image_id": observed_project_image_id,
        "pinned_image": config["stage3"]["roofer_image"],
        "pinned_image_id": config["stage3"]["roofer_image_id"],
        "command_contract": command_contract,
        "command_contract_sha256": sha256_bytes(canonical_json_bytes(command_contract)),
        "runtime_control": runtime_control,
        "smoke_inputs": smoke_inputs,
        "output_records": outputs,
        "json_output_count": len(json_outputs),
        "json_schema_validations": validations,
        "validation_error": validation_error,
        "runtime_log": hash_task_output_once(log_path),
        "scientific_source_bytes_read_or_hashed": 0,
        "external_or_gt_roofprint_used": False,
        "quality_or_performance": False,
        "scientific_verdict": None,
    }
    receipt_record = add_once_json(receipt_path, receipt)
    print(json.dumps(receipt, sort_keys=True))
    if status != "PASS":
        raise RuntimeError("Roofer synthetic runtime smoke failed")
    checkpoints.write(110, "roofer_runtime_smoke", {"receipt": receipt_record, "operation_id": operation_id, "observed_image": observed_image, "observed_image_id": observed_image_id, "observed_project_image_id": observed_project_image_id})
    completed = {
        **execution,
        "status": "COMPLETED",
        "checkpoints": checkpoints.records,
        "roofer_runtime": receipt_record,
    }
    add_once_json(output_root / "control/completed_ledger_v1.json", completed)
    return receipt


def promote(artifact_root: Path) -> dict[str, Any]:
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    output_root = artifact_root.resolve() / config["output_namespace"]
    ledger_path = output_root / "control/completed_ledger_v1.json"
    summary_path = output_root / "freeze/technical_summary_v1.json"
    eligibility_path = output_root / "freeze/eligibility_ledger_v1.csv"
    roofer_receipt = output_root / "stage3/roofer_runtime_smoke_receipt_v1.json"
    if not ledger_path.is_file() or not summary_path.is_file() or not roofer_receipt.is_file():
        raise RuntimeError("completed ledger, summary and Roofer smoke receipt are required")
    ledger_bytes = ledger_path.read_bytes()
    summary_bytes = summary_path.read_bytes()
    eligibility_bytes = eligibility_path.read_bytes()
    roofer_bytes = roofer_receipt.read_bytes()
    ledger = json.loads(ledger_bytes)
    summary = json.loads(summary_bytes)
    roofer = json.loads(roofer_bytes)
    runtime_control = enforce_runtime_control(
        ledger.get("operation_identity", {}).get("source_commit", ""),
        artifact_root,
        allowed_dirty_paths=PROMOTION_PATHS,
    )
    operation_id = ledger["operation_identity"]["operation_id"]
    if operation_id != summary["operation_id"]:
        raise RuntimeError("compact output operation mismatch")
    checkpoints = Checkpoints(output_root, operation_id)
    if not checkpoints.completed(110, "roofer_runtime_smoke") or ledger.get("checkpoints") != checkpoints.records:
        raise RuntimeError("completed ledger does not bind the full checkpoint chain")
    summary_record = checkpoints.payload(100, "technical_summary")["summary"]
    eligibility_record = checkpoints.payload(80, "universe_eligibility_split")["eligibility"]
    receipt_record = checkpoints.payload(110, "roofer_runtime_smoke")["receipt"]
    if summary_record["sha256"] != sha256_bytes(summary_bytes) or summary_record["bytes"] != len(summary_bytes):
        raise RuntimeError("summary differs from checkpoint 100")
    if eligibility_record["sha256"] != sha256_bytes(eligibility_bytes) or eligibility_record["bytes"] != len(eligibility_bytes):
        raise RuntimeError("eligibility differs from checkpoint 80")
    if receipt_record["sha256"] != sha256_bytes(roofer_bytes) or receipt_record["bytes"] != len(roofer_bytes):
        raise RuntimeError("Roofer receipt differs from checkpoint 110")
    if (
        roofer.get("status") != "PASS"
        or roofer.get("quality_or_performance") is not False
        or roofer.get("operation_id") != operation_id
        or roofer.get("source_commit") != summary["source_commit"]
        or roofer.get("observed_image") != config["stage3"]["roofer_image"]
        or roofer.get("observed_image_id") != config["stage3"]["roofer_image_id"]
        or roofer.get("pinned_image") != config["stage3"]["roofer_image"]
        or roofer.get("pinned_image_id") != config["stage3"]["roofer_image_id"]
        or roofer.get("observed_project_image_id") != runtime_control["acceptance"]["project_docker_image_id"]
    ):
        raise RuntimeError("Roofer runtime smoke did not pass its non-performance contract")
    summary["stage3"]["roofer_runtime_smoke"] = roofer
    if summary["universe"]["e_paired_count"] <= 0:
        summary["status"] = "BLOCKED_E_PAIRED_EMPTY"
    elif not summary["universe"].get("required_splits_nonempty"):
        summary["status"] = "BLOCKED_SPLIT_DEGENERATE"
    else:
        summary["status"] = "TECHNICALLY_READY_FOR_HUMAN_GATE_S0_REVIEW"
    summary["promotion_read_accounting"] = {
        "completed_ledger_bytes": len(ledger_bytes),
        "summary_bytes": len(summary_bytes),
        "eligibility_bytes": len(eligibility_bytes),
        "roofer_receipt_bytes": len(roofer_bytes),
        "scientific_source_bytes": 0,
    }
    manifest = add_repo_once(PROMOTION_PATHS[0], canonical_json_bytes(summary))
    eligibility = add_repo_once(PROMOTION_PATHS[1], eligibility_bytes)
    report = f"""# Gate S0 freeze recovery technical report v1

- task: `{TASK}`
- exact source commit: `{summary['source_commit']}`
- technical status: `{summary['status']}`
- scientific_verdict: `null`

## Result

The exact common source remains 962/937/25. The frozen consumer graph reads only
`cameras.bin`, `images.bin`, `points3D.bin`, and dense PLY ({summary['consumer_graph']['bytes']:,} bytes).
It does not open the context-only rig/frame metadata, scene.mvs, prior dense LAZ, retained
images or stereo tree.

The independent UAS extraction produced {summary['reference']['uasref_component_count']:,}
roof-support units and {summary['reference']['cells']:,} cells. Its digest remained
identical before and after the canonical-199 post-freeze identity crosswalk and C5
input load. The LoD2-derived LoD1 was used only as the C5 prior; source LoD2 reads
and same-lineage scoring were both zero.

`U_target` contains {summary['universe']['u_target_count']:,} units and `E_paired`
contains {summary['universe']['e_paired_count']:,}. Split counts are
`{json.dumps(summary['universe']['split_counts'], sort_keys=True)}`. Protected held-out
outcomes were not opened.

C3--C5 input registration did not use UAS roof geometry. Primary evaluation is
terrain-normalized/relative; absolute-Z metrics remain disabled. The common Stage-3
interface and pinned Roofer runtime passed only synthetic non-performance smoke.

This is technical evidence for human Gate review, not Gate approval and not a
scientific verdict.
""".encode("utf-8")
    report_record = add_repo_once(PROMOTION_PATHS[2], report)
    promotion = {"status": summary["status"], "manifest": manifest, "eligibility": eligibility, "report": report_record, "scientific_verdict": None}
    print(json.dumps(promotion, sort_keys=True))
    return promotion


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", required=True, choices=("preflight", "runtime-control", "execute", "record-roofer-smoke", "promote"))
    parser.add_argument("--source-commit")
    parser.add_argument("--artifact-root", default="/artifacts/JointBuildGS")
    parser.add_argument("--roofer-exit-code", type=int)
    parser.add_argument("--observed-roofer-image")
    parser.add_argument("--observed-roofer-image-id")
    parser.add_argument("--observed-project-image-id")
    parser.add_argument("--allow-dirty", action="store_true")
    args = parser.parse_args()
    artifact_root = Path(args.artifact_root)
    if args.mode == "preflight":
        if not args.source_commit:
            parser.error("--source-commit is required")
        print(json.dumps(preflight(args.source_commit, artifact_root if artifact_root.exists() else None, not args.allow_dirty), sort_keys=True))
    elif args.mode == "runtime-control":
        if not args.source_commit or not args.observed_project_image_id:
            parser.error("--source-commit and --observed-project-image-id are required")
        control = enforce_runtime_control(args.source_commit, artifact_root)
        if control["acceptance"]["project_docker_image_id"] != args.observed_project_image_id:
            raise RuntimeError("observed project Docker image ID does not match acceptance")
        print(json.dumps({**control, "observed_project_image_id": args.observed_project_image_id}, sort_keys=True))
    elif args.mode == "execute":
        if not args.source_commit:
            parser.error("--source-commit is required")
        execute(args.source_commit, artifact_root)
    elif args.mode == "record-roofer-smoke":
        if args.roofer_exit_code is None or not args.observed_roofer_image or not args.observed_roofer_image_id or not args.observed_project_image_id:
            parser.error("--roofer-exit-code, --observed-roofer-image, --observed-roofer-image-id and --observed-project-image-id are required")
        record_roofer_smoke(
            artifact_root,
            args.roofer_exit_code,
            args.observed_roofer_image,
            args.observed_roofer_image_id,
            args.observed_project_image_id,
        )
    else:
        promote(artifact_root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
