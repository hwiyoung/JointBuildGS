#!/usr/bin/env python3
"""Build the observational arm A-prime review bundle.

The generator is deliberately receipt-led.  It emits one row for every
preregistered job even when the job has not produced a score, and keeps
``missing`` and ``censored`` distinct from numeric zero.  Static figures are
review aids only; no scientific verdict or interpretation is generated.
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
import shutil
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Mapping, MutableMapping, Sequence

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from PIL import Image


REPO = Path(__file__).resolve().parents[4]
DEFAULT_CONFIG = (
    REPO / "phases/p2-gsjso/configs/fusion_w1/fusion_w1_aprime_report_20260726.json"
)
CONFIG_SCHEMA = "jointbuildgs.fusion_w1_aprime.report.config.v2"
MANIFEST_SCHEMA = "jointbuildgs.fusion_w1_aprime.report.manifest.v2"
RECEIPT_SCHEMA = "jointbuildgs.fusion_w1_aprime.report.receipt.v2"
LATEST_SCHEMA = "jointbuildgs.fusion_w1_aprime.report.latest.v2"
READOUT_COMPLETE_SCHEMA = "jointbuildgs.fusion_w1_aprime.readout.complete.v1"
SEED_INITIALIZATION_SCHEMA = "jointbuildgs.stage2.seed_initialization_audit.v1"
QUEUE_CONFIG_SCHEMA = "jointbuildgs.fusion_w1_aprime.unattended.config.v1"
QUEUE_PLAN_SCHEMA = "jointbuildgs.fusion_w1_aprime.unattended.plan.v1"
QUEUE_STAGE_RECORD_SCHEMA = "jointbuildgs.fusion_w1_aprime.unattended.stage_record.v1"
QUEUE_ARCHIVE_SCHEMA = "jointbuildgs.fusion_w1_aprime.unattended.training_archive.v1"
QUEUE_ARCHIVE_LEDGER_SCHEMA = (
    "jointbuildgs.fusion_w1_aprime.unattended.training_archive_ledger.v1"
)
QUEUE_STAGE_STOP_SCHEMA = "jointbuildgs.fusion_w1_aprime.unattended.stage_stop.v1"
QUEUE_COMPLETE_SCHEMA = "jointbuildgs.fusion_w1_aprime.unattended.complete.v1"
RECOVERY_CONTROLLER_SCHEMA = (
    "jointbuildgs.fusion_w1_aprime.unattended.recovery_controller.v1"
)
RECOVERY_INTENT_SCHEMA = (
    "jointbuildgs.fusion_w1_aprime.unattended.rehydration_intent.v1"
)
RECOVERY_RECEIPT_SCHEMA = (
    "jointbuildgs.fusion_w1_aprime.unattended.rehydration_receipt.v1"
)
T4_RECEIPT_SCHEMA = "jointbuildgs.fusion_w1_aprime.t4_smoke_collapse.v1"
TRUE_VALUES = {"true", "1", "yes"}
FALSE_VALUES = {"false", "0", "no"}
TERMINAL_STATES = {"measured", "failed", "censored", "skipped"}


class ReportContractError(RuntimeError):
    """A report input, measurement-state, or publication contract failed."""


@dataclass(frozen=True)
class Job:
    queue_order: int
    building_id: str
    arm: str
    run: str
    target: Mapping[str, str]

    @property
    def key(self) -> str:
        return f"{self.building_id}/arm_{self.arm}/{self.run}"

    @property
    def slug(self) -> str:
        return f"{self.building_id}_arm_{self.arm}_{self.run}"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def repo_path(value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else REPO / path


def repo_relative(path: Path) -> str:
    try:
        return path.resolve().relative_to(REPO.resolve()).as_posix()
    except ValueError:
        return str(path.resolve())


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_sha(value: Any) -> str:
    payload = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReportContractError(f"cannot read JSON {repo_relative(path)}: {exc}") from exc
    if not isinstance(value, dict):
        raise ReportContractError(f"JSON root is not an object: {repo_relative(path)}")
    return value


def read_csv(path: Path) -> list[dict[str, str]]:
    try:
        with path.open("r", encoding="utf-8", newline="") as stream:
            return [dict(row) for row in csv.DictReader(stream)]
    except OSError as exc:
        raise ReportContractError(f"cannot read CSV {repo_relative(path)}: {exc}") from exc


def atomic_bytes(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as stream:
        temporary = Path(stream.name)
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def atomic_text(path: Path, payload: str) -> None:
    atomic_bytes(path, payload.encode("utf-8"))


def atomic_json(path: Path, payload: Mapping[str, Any]) -> None:
    atomic_text(
        path,
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    )


def write_csv(
    path: Path, rows: Sequence[Mapping[str, Any]], fields: Sequence[str] | None = None
) -> None:
    if fields is None:
        ordered: list[str] = []
        seen: set[str] = set()
        for row in rows:
            for key in row:
                if key not in seen:
                    ordered.append(key)
                    seen.add(key)
        fields = ordered
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(
        stream,
        fieldnames=list(fields),
        extrasaction="ignore",
        lineterminator="\n",
    )
    writer.writeheader()
    for row in rows:
        writer.writerow({key: csv_value(row.get(key)) for key in fields})
    atomic_text(path, stream.getvalue())


def csv_value(value: Any) -> Any:
    if value is None:
        return ""
    if isinstance(value, bool):
        return str(value).lower()
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    if isinstance(value, float):
        if not math.isfinite(value):
            return ""
        return f"{value:.12g}"
    return value


def load_config(
    path: Path = DEFAULT_CONFIG, *, verify_locked_files: bool = True
) -> dict[str, Any]:
    config = load_json(path)
    if config.get("schema") != CONFIG_SCHEMA:
        raise ReportContractError("report config schema drift")
    if config.get("branch") != "exp/fusion-w1":
        raise ReportContractError("report branch lock drift")
    contract = config["measurement_contract"]
    states = set(contract["measurement_states"])
    if states != {"measured", "missing", "censored", "not_applicable"}:
        raise ReportContractError("measurement-state vocabulary drift")
    if contract.get("censored_is_measured") is not False:
        raise ReportContractError("censored rows must not be measured")
    if set(contract.get("comparison_nonmeasurement_outcomes", [])) != {
        "NOT_ASSEMBLED",
        "UNCONSTRUCTABLE",
    }:
        raise ReportContractError("legacy alpha nonmeasurement outcome contract drift")
    if contract.get("comparison_nonmeasurement_state") != "not_applicable":
        raise ReportContractError("legacy alpha nonmeasurement state contract drift")
    if contract.get("scientific_verdict") is not None:
        raise ReportContractError("report config contains a scientific verdict")
    if contract.get("interpretation") is not None:
        raise ReportContractError("report config contains an interpretation")
    queue = config["queue_contract"]
    if int(queue.get("expected_stage_entries", -1)) != 22:
        raise ReportContractError("queue stage-entry cardinality drift")
    if int(queue.get("expected_jobs", -1)) != 21:
        raise ReportContractError("queue unique-job cardinality drift")
    if queue.get("time_cutoff") is not None:
        raise ReportContractError("report queue time cutoff drift")
    provenance = config["provenance_contract"]
    execution_head = str(provenance.get("execution_head", ""))
    if execution_head != "de8852c00c737eced081f2627b49bcedddade652":
        raise ReportContractError("execution HEAD lock drift")
    report_files = list(provenance.get("report_implementation_files", []))
    if report_files != list(config.get("implementation_files", [])):
        raise ReportContractError("report implementation provenance drift")
    recovery = config["recovery_contract"]
    controller_files = list(recovery.get("controller_files", []))
    recovery_paths = [str(record.get("path", "")) for record in controller_files]
    recovery_exact = list(
        provenance.get("recovery_exact_descendant_allowlist", [])
    )
    expected_recovery_exact = recovery_paths + [recovery["controller"]["path"]]
    if recovery_exact != expected_recovery_exact or len(set(recovery_exact)) != len(
        recovery_exact
    ):
        raise ReportContractError("recovery descendant exact allowlist drift")
    operational_exact = list(
        provenance.get("operational_evidence_exact_descendant_allowlist", [])
    )
    if operational_exact != [config["sources"]["issues"]]:
        raise ReportContractError("operational evidence descendant allowlist drift")
    recovery_globs = list(
        provenance.get("recovery_glob_descendant_allowlist", [])
    )
    if len(recovery_globs) != 2 or not all(
        pattern.endswith(("/intent.json", "/receipt.json"))
        for pattern in recovery_globs
    ):
        raise ReportContractError("recovery descendant glob allowlist drift")
    if provenance.get("history_paths_not_only_final_tree") is not True:
        raise ReportContractError("descendant history-path provenance drift")
    if provenance.get("report_files_must_match_generation_head") is not True:
        raise ReportContractError("report worktree/HEAD binding drift")
    if provenance.get("recovery_files_must_match_controller_receipt") is not True:
        raise ReportContractError("recovery/controller provenance drift")
    controller = recovery["controller"]
    if (
        controller.get("path") != config["sources"]["queue_recovery_controller"]
        or controller.get("schema") != RECOVERY_CONTROLLER_SCHEMA
        or recovery.get("rehydration_intent_schema") != RECOVERY_INTENT_SCHEMA
        or recovery.get("rehydration_receipt_schema") != RECOVERY_RECEIPT_SCHEMA
    ):
        raise ReportContractError("queue recovery schema/path contract drift")
    if recovery.get("producer_receipts_rewritten") is not False:
        raise ReportContractError("queue recovery producer-receipt policy drift")
    if recovery.get("append_only_source_preserved") is not True:
        raise ReportContractError("queue recovery archive-preservation policy drift")
    for item in [recovery["committed_queue_driver"], *controller_files]:
        path_value = item.get("path") if isinstance(item, Mapping) else None
        expected = item.get("sha256") if isinstance(item, Mapping) else None
        expected_bytes = item.get("bytes") if isinstance(item, Mapping) else None
        if (
            not path_value
            or not isinstance(expected, str)
            or re.fullmatch(r"[0-9a-f]{64}", expected) is None
            or not isinstance(expected_bytes, int)
        ):
            raise ReportContractError("queue recovery file contract incomplete")
        if verify_locked_files:
            path_obj = repo_path(path_value)
            if (
                not path_obj.is_file()
                or path_obj.stat().st_size != expected_bytes
                or sha256_file(path_obj) != expected
            ):
                raise ReportContractError(f"queue recovery file drift: {path_value}")
    for name, item in config["t4_contract"].items():
        if name not in {"receipt", "csv", "figure"}:
            raise ReportContractError(f"unexpected T4 contract role: {name}")
        if not isinstance(item, Mapping) or not item.get("path") or not item.get("sha256"):
            raise ReportContractError(f"incomplete T4 contract role: {name}")
    for record in config["locked_inputs"].values():
        records = record if isinstance(record, list) else [record]
        for item in records:
            path_value = item.get("path") if isinstance(item, Mapping) else None
            expected = item.get("sha256") if isinstance(item, Mapping) else None
            if verify_locked_files and expected and path_value:
                path_obj = repo_path(path_value)
                if not path_obj.is_file() or sha256_file(path_obj) != expected:
                    raise ReportContractError(f"locked input drift: {path_value}")
    readout = config["locked_inputs"]["readout_config"]
    readout_path = repo_path(readout["path"])
    if readout_path.is_file():
        if load_json(readout_path).get("schema") != readout["schema"]:
            raise ReportContractError("readout config schema drift")
    queue_config = config["locked_inputs"]["queue_config"]
    queue_path = repo_path(queue_config["path"])
    if load_json(queue_path).get("schema") != QUEUE_CONFIG_SCHEMA:
        raise ReportContractError("queue config schema drift")
    return config


def load_targets(config: Mapping[str, Any]) -> list[dict[str, str]]:
    locked = config["locked_inputs"]["targets"]
    path = repo_path(locked["path"])
    rows = read_csv(path)
    if len(rows) != int(locked["population"]):
        raise ReportContractError("A-prime target population drift")
    id_field = locked["id_field"]
    order_field = locked["order_field"]
    ids = [row[id_field] for row in rows]
    orders = [int(row[order_field]) for row in rows]
    if len(ids) != len(set(ids)) or sorted(orders) != list(range(1, len(rows) + 1)):
        raise ReportContractError("A-prime target identity/order drift")
    return sorted(rows, key=lambda row: int(row[order_field]))


def expected_jobs(
    targets: Sequence[Mapping[str, str]], config: Mapping[str, Any]
) -> list[Job]:
    queue = config["queue_contract"]
    rows: list[Job] = []
    by_id = {row["building_id"]: row for row in targets}
    for run in queue["Aprime_runs"]:
        for target in targets:
            rows.append(
                Job(len(rows) + 1, target["building_id"], "Aprime", run, target)
            )
    for run in queue["B_runs"]:
        for building_id in queue["B_buildings"]:
            if building_id not in by_id:
                raise ReportContractError(f"B queue target missing: {building_id}")
            rows.append(Job(len(rows) + 1, building_id, "B", run, by_id[building_id]))
    if len(rows) != int(queue["expected_jobs"]):
        raise ReportContractError("A-prime report queue cardinality drift")
    return rows


def texture_stratum(target: Mapping[str, str], config: Mapping[str, Any]) -> str:
    contract = config["measurement_contract"]
    value = float(target[contract["texture_field"]])
    return (
        contract["textureless_label"]
        if value > float(contract["texture_threshold"])
        else contract["textured_label"]
    )


def file_record(
    path: Path,
    role: str,
    *,
    expected_sha256: str | None = None,
    required: bool = False,
) -> dict[str, Any]:
    record: dict[str, Any] = {
        "role": role,
        "path": repo_relative(path),
        "state": "present" if path.is_file() else "missing",
    }
    if path.is_file():
        before = path.stat()
        digest = sha256_file(path)
        after = path.stat()
        if (before.st_size, before.st_mtime_ns) != (
            after.st_size,
            after.st_mtime_ns,
        ):
            raise ReportContractError(
                f"source changed while hashing: {repo_relative(path)}"
            )
        record["bytes"] = after.st_size
        record["mtime_ns"] = after.st_mtime_ns
        record["sha256"] = digest
        if expected_sha256 is not None:
            record["expected_sha256"] = expected_sha256
            record["hash_matches"] = record["sha256"] == expected_sha256
            if not record["hash_matches"]:
                raise ReportContractError(f"source hash drift: {repo_relative(path)}")
    elif required:
        raise ReportContractError(f"required report source missing: {repo_relative(path)}")
    return record


def receipt_binding(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise ReportContractError(f"receipt-bound file missing: {repo_relative(path)}")
    return {
        "path": repo_relative(path),
        "sha256": sha256_file(path),
        "bytes": path.stat().st_size,
    }


def verify_file_binding(value: Any, label: str) -> tuple[Path, dict[str, Any]]:
    if not isinstance(value, Mapping):
        raise ReportContractError(f"{label} is not a file binding")
    raw_path = value.get("path")
    expected_sha = value.get("sha256")
    if not isinstance(raw_path, str) or not raw_path:
        raise ReportContractError(f"{label} path is missing")
    if not isinstance(expected_sha, str) or not re.fullmatch(r"[0-9a-f]{64}", expected_sha):
        raise ReportContractError(f"{label} SHA-256 is missing or malformed")
    path = repo_path(raw_path)
    observed = receipt_binding(path)
    if observed["path"] != raw_path:
        raise ReportContractError(f"{label} path is not canonical: {raw_path}")
    if observed["sha256"] != expected_sha:
        raise ReportContractError(f"{label} SHA-256 drift: {raw_path}")
    if value.get("bytes") is not None and int(value["bytes"]) != observed["bytes"]:
        raise ReportContractError(f"{label} byte count drift: {raw_path}")
    return path, observed


def load_t4_bundle(config: Mapping[str, Any]) -> dict[str, Any]:
    contract = config["t4_contract"]
    files: dict[str, dict[str, Any]] = {}
    paths: dict[str, Path] = {}
    for role in ("receipt", "csv", "figure"):
        path, observed = verify_file_binding(contract[role], f"T4 {role}")
        files[role] = observed
        paths[role] = path
    payload = load_json(paths["receipt"])
    if payload.get("schema") != T4_RECEIPT_SCHEMA:
        raise ReportContractError("T4 receipt schema drift")
    if payload.get("status") != "COMPLETED" or payload.get("role") != "record_only_not_verdict":
        raise ReportContractError("T4 receipt status/role drift")
    for role in ("csv", "figure"):
        embedded = nested_get(payload, f"outputs.{role}")
        if not isinstance(embedded, Mapping):
            raise ReportContractError(f"T4 receipt output binding missing: {role}")
        if embedded.get("path") != files[role]["path"]:
            raise ReportContractError(f"T4 receipt output path drift: {role}")
        if embedded.get("sha256") != files[role]["sha256"]:
            raise ReportContractError(f"T4 receipt output SHA drift: {role}")
    return {"payload": payload, "files": files, "paths": paths}


def t4_bundle_links(config: Mapping[str, Any]) -> dict[str, str]:
    root = str(config["outputs"]["t4_bundle_dir"]).rstrip("/")
    return {
        "receipt": f"{root}/receipt.json",
        "csv": f"{root}/arm_A_roof_opacity_trajectory.csv",
        "figure": f"{root}/arm_A_roof_opacity_trajectory.png",
        "manifest": config["outputs"]["t4_bundle_manifest"],
    }


def publish_t4_bundle(
    snapshot: Path, config: Mapping[str, Any], bundle: Mapping[str, Any]
) -> dict[str, Any]:
    links = t4_bundle_links(config)
    published: dict[str, dict[str, Any]] = {}
    for role in ("receipt", "csv", "figure"):
        source = bundle["paths"][role]
        destination = snapshot / links[role]
        atomic_bytes(destination, source.read_bytes())
        observed = receipt_binding(destination)
        expected = bundle["files"][role]["sha256"]
        if observed["sha256"] != expected:
            raise ReportContractError(f"snapshot-local T4 {role} SHA drift")
        published[role] = {
            "source": dict(bundle["files"][role]),
            "snapshot_path": links[role],
            "snapshot_sha256": observed["sha256"],
            "snapshot_bytes": observed["bytes"],
        }
    manifest = {
        "schema": "jointbuildgs.fusion_w1_aprime.report.t4_bundle.v1",
        "role": "snapshot_local_record_only_evidence",
        "files": published,
        "source_receipt_status": bundle["payload"].get("status"),
        "scientific_verdict": None,
    }
    atomic_json(snapshot / links["manifest"], manifest)
    return manifest


def queue_job_key(entry: Mapping[str, Any]) -> str:
    return f"{entry['building_id']}/arm_{entry['arm']}/{entry['replicate']}"


def expected_queue_stage_specs(
    jobs: Sequence[Job], config: Mapping[str, Any]
) -> list[dict[str, Any]]:
    queue = config["queue_contract"]
    if len(jobs) != int(queue["expected_jobs"]):
        raise ReportContractError("queue/report unique job mismatch")
    smoke_job = jobs[0]
    smoke_identity = (smoke_job.building_id, smoke_job.arm, smoke_job.run)
    if smoke_identity != (
        queue["smoke_building_id"],
        queue["smoke_arm"],
        queue["smoke_run"],
    ):
        raise ReportContractError("queue smoke identity drift")
    stages = [
        (0, queue["smoke_stage_key"], [smoke_job]),
        (1, queue["reuse_stage_key"], list(jobs[:9])),
        (2, "aprime_r2", list(jobs[9:18])),
        (3, "B_r1", list(jobs[18:])),
    ]
    training_config = load_json(
        repo_path(config["locked_inputs"]["training_config"]["path"])
    )
    run_seeds = nested_get(training_config, "recipe.run_seeds")
    if not isinstance(run_seeds, Mapping):
        raise ReportContractError("training run-seed contract missing")
    result: list[dict[str, Any]] = []
    for stage_order, stage_key, members in stages:
        for stage_entry_order, job in enumerate(members, 1):
            result.append(
                {
                    "global_entry_order": len(result) + 1,
                    "stage_order": stage_order,
                    "stage_key": stage_key,
                    "stage_entry_order": stage_entry_order,
                    "queue_order": job.queue_order,
                    "building_id": job.building_id,
                    "aprime_order": int(job.target["aprime_order"]),
                    "target_role": job.target["target_role"],
                    "arm": job.arm,
                    "replicate": job.run,
                    "profile": "full",
                    "seed": int(run_seeds[job.run]),
                    "smoke_barrier_entry": stage_order == 0,
                    "reuse_completed_smoke": stage_order == 1 and stage_entry_order == 1,
                }
            )
    if len(result) != int(queue["expected_stage_entries"]):
        raise ReportContractError("queue stage-entry derivation drift")
    return result


def queue_stage_record_path(
    config: Mapping[str, Any], entry: Mapping[str, Any]
) -> Path:
    root = repo_path(config["sources"]["queue_stage_records"])
    return root / (
        f"stage_{int(entry['stage_order']):02d}_{entry['stage_key']}/"
        f"entry_{int(entry['stage_entry_order']):02d}_{entry['building_id']}_"
        f"arm_{entry['arm']}_{entry['replicate']}.json"
    )


def _entry_matches_spec(entry: Mapping[str, Any], spec: Mapping[str, Any]) -> bool:
    return all(entry.get(key) == value for key, value in spec.items())


def _queue_top_source_records(config: Mapping[str, Any]) -> list[dict[str, Any]]:
    sources = config["sources"]
    return [
        file_record(repo_path(sources[name]), name)
        for name in (
            "queue_plan",
            "queue_status_json",
            "queue_status_csv",
            "queue_stage_stop",
            "queue_complete",
            "queue_events",
            "queue_event_sequence",
        )
    ]


def _validate_queue_complete(
    config: Mapping[str, Any], plan_path: Path, present_stage: Mapping[str, Mapping[str, Any]]
) -> dict[str, Any] | None:
    complete_path = repo_path(config["sources"]["queue_complete"])
    if not complete_path.is_file():
        return None
    payload = load_json(complete_path)
    if payload.get("schema") != QUEUE_COMPLETE_SCHEMA:
        raise ReportContractError("queue complete schema drift")
    state = str(payload.get("state", ""))
    if state != "COMPLETE" and not state.startswith("STOPPED_"):
        raise ReportContractError("queue complete terminal state drift")
    if payload.get("run_id") != config["run_id"]:
        raise ReportContractError("queue complete run identity drift")
    if payload.get("git_head") != config["provenance_contract"]["execution_head"]:
        raise ReportContractError("queue execution HEAD drift")
    _, observed_plan = verify_file_binding(payload.get("plan"), "queue complete plan")
    if observed_plan != receipt_binding(plan_path):
        raise ReportContractError("queue complete/plan binding drift")
    complete_records = payload.get("stage_records")
    if not isinstance(complete_records, list):
        raise ReportContractError("queue complete stage-record inventory missing")
    bound_paths: set[str] = set()
    for index, item in enumerate(complete_records):
        if not isinstance(item, Mapping):
            raise ReportContractError("queue complete stage-record row drift")
        _, observed = verify_file_binding(
            item.get("receipt"), f"queue complete stage record {index + 1}"
        )
        entry = item.get("entry")
        if not isinstance(entry, Mapping):
            raise ReportContractError("queue complete stage-record entry missing")
        path = observed["path"]
        current = present_stage.get(path)
        if path in bound_paths:
            raise ReportContractError("queue complete contains duplicate stage-record receipt")
        if (
            current is None
            or current.get("entry") != entry
            or current.get("status") != item.get("status")
        ):
            raise ReportContractError("queue complete/stage-record status drift")
        bound_paths.add(path)
    if bound_paths != set(present_stage):
        raise ReportContractError("queue complete/stage-record inventory drift")
    if state == "COMPLETE" and len(complete_records) != int(
        config["queue_contract"]["expected_stage_entries"]
    ):
        raise ReportContractError("queue COMPLETE lacks all stage records")
    if int(payload.get("stage_entries_n", -1)) != int(
        config["queue_contract"]["expected_stage_entries"]
    ):
        raise ReportContractError("queue complete stage-entry count drift")
    if int(payload.get("unique_jobs_n", -1)) != int(
        config["queue_contract"]["expected_jobs"]
    ):
        raise ReportContractError("queue complete unique-job count drift")
    complete_sources = {
        "status_json": "queue_status_json",
        "status_csv": "queue_status_csv",
        "events": "queue_events",
        "event_sequence": "queue_event_sequence",
    }
    for name, source_name in complete_sources.items():
        _path, observed = verify_file_binding(
            payload.get(name), f"queue complete {name}"
        )
        if observed["path"] != config["sources"][source_name]:
            raise ReportContractError(f"queue complete {name} path drift")
    stage_stop = payload.get("stage_stop")
    if state == "COMPLETE" and stage_stop is not None:
        raise ReportContractError("queue COMPLETE unexpectedly binds a stage-stop receipt")
    if state.startswith("STOPPED_") and stage_stop is None:
        raise ReportContractError("stopped queue complete lacks stage-stop receipt")
    if stage_stop is not None:
        stage_stop_path, _observed = verify_file_binding(
            stage_stop, "queue complete stage stop"
        )
        if repo_relative(stage_stop_path) != config["sources"]["queue_stage_stop"]:
            raise ReportContractError("queue complete stage-stop path drift")
        stage_stop_payload = load_json(stage_stop_path)
        if stage_stop_payload.get("schema") != QUEUE_STAGE_STOP_SCHEMA:
            raise ReportContractError("queue stage-stop schema drift")
        if stage_stop_payload.get("state") != state:
            raise ReportContractError("queue complete/stage-stop state drift")
    return payload


def _queue_archive_rows(
    jobs: Sequence[Job], config: Mapping[str, Any]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    root = repo_path(config["sources"]["queue_training_failure_archive"])
    known = {job.key for job in jobs}
    rows: list[dict[str, Any]] = []
    sources: list[dict[str, Any]] = []
    if not root.is_dir():
        return rows, sources
    pattern = "by_building/*/arm_*/*/attempt_*"
    by_job_attempts: dict[str, list[int]] = defaultdict(list)
    for directory in sorted(root.glob(pattern)):
        if not directory.is_dir() or directory.is_symlink():
            continue
        match = re.fullmatch(r"attempt_([0-9]{3})(\.incomplete)?", directory.name)
        if match is None:
            raise ReportContractError(
                f"queue archive directory name drift: {repo_relative(directory)}"
            )
        building_id = directory.parents[2].name
        arm_dir = directory.parents[1].name
        replicate = directory.parent.name
        if not arm_dir.startswith("arm_"):
            raise ReportContractError("queue archive arm directory drift")
        arm = arm_dir[4:]
        key = f"{building_id}/arm_{arm}/{replicate}"
        if key not in known:
            raise ReportContractError(f"queue archive identity outside report queue: {key}")
        attempt = int(match.group(1))
        incomplete = match.group(2) is not None
        if not incomplete:
            by_job_attempts[key].append(attempt)
        row: dict[str, Any] = {
            "job_key": key,
            "building_id": building_id,
            "arm": arm,
            "run": replicate,
            "attempt": attempt,
            "archive_state": "INCOMPLETE" if incomplete else "ARCHIVED",
            "archive_path": repo_relative(directory),
            "receipt_path": "",
            "receipt_sha256": None,
            "error_type": None,
            "error_signature": None,
            "artifact_count": None,
        }
        if incomplete:
            for name in ("move_intent.json", "pre_move_ledger.json", "archive_receipt.json"):
                path = directory / name
                if path.is_file():
                    sources.append(file_record(path, f"queue_archive_incomplete_{key}_{attempt}_{name}"))
            rows.append(row)
            continue
        receipt_path = directory / "archive_receipt.json"
        sources.append(file_record(receipt_path, f"queue_archive_receipt_{key}_{attempt}", required=True))
        payload = load_json(receipt_path)
        if payload.get("schema") != QUEUE_ARCHIVE_SCHEMA or payload.get("state") != "ARCHIVED":
            raise ReportContractError("queue archive receipt schema/state drift")
        identity = payload.get("identity")
        if identity != {
            "building_id": building_id,
            "arm": arm,
            "replicate": replicate,
            "profile": "full",
        }:
            raise ReportContractError("queue archive receipt identity drift")
        if int(payload.get("attempt", -1)) != attempt:
            raise ReportContractError("queue archive attempt drift")
        if payload.get("git_head") != config["provenance_contract"]["execution_head"]:
            raise ReportContractError("queue archive execution HEAD drift")
        if payload.get("append_only_archive") is not True:
            raise ReportContractError("queue archive append-only flag drift")
        if payload.get("destination_path") != repo_relative(directory):
            raise ReportContractError("queue archive destination path drift")
        source_path = payload.get("source_path")
        if not isinstance(source_path, str) or not source_path:
            raise ReportContractError("queue archive source path missing")
        _, archived_terminal = verify_file_binding(
            payload.get("archived_terminal_receipt"), "queue archived terminal receipt"
        )
        original = payload.get("original_terminal_receipt")
        if (
            not isinstance(original, Mapping)
            or original.get("sha256") != archived_terminal["sha256"]
            or int(original.get("bytes", -1)) != archived_terminal["bytes"]
        ):
            raise ReportContractError("queue archive terminal SHA binding drift")
        ledger_path, _ledger_record = verify_file_binding(
            payload.get("pre_move_ledger"), "queue archive pre-move ledger"
        )
        ledger = load_json(ledger_path)
        if ledger.get("schema") != QUEUE_ARCHIVE_LEDGER_SCHEMA:
            raise ReportContractError("queue archive ledger schema drift")
        if ledger.get("source_path") != source_path:
            raise ReportContractError("queue archive ledger source path drift")
        ledger_artifacts = ledger.get("artifacts")
        if not isinstance(ledger_artifacts, list) or not ledger_artifacts:
            raise ReportContractError("queue archive ledger artifacts missing")
        if int(ledger.get("artifact_count", -1)) != len(ledger_artifacts):
            raise ReportContractError("queue archive ledger artifact count drift")
        sources.append(file_record(ledger_path, f"queue_archive_ledger_{key}_{attempt}"))
        verification = payload.get("move_verification")
        if not isinstance(verification, list) or not verification:
            raise ReportContractError("queue archive move verification missing")
        if int(payload.get("artifact_count", -1)) != len(verification):
            raise ReportContractError("queue archive artifact count drift")
        if len(ledger_artifacts) != len(verification):
            raise ReportContractError("queue archive ledger/move count drift")
        relative_names: set[str] = set()
        original_paths: dict[str, str] = {}
        archived_paths: set[str] = set()
        for index, (original_record, record) in enumerate(
            zip(ledger_artifacts, verification)
        ):
            if not isinstance(original_record, Mapping) or not isinstance(record, Mapping):
                raise ReportContractError("queue archive ledger row drift")
            relative_name = original_record.get("relative_to_root")
            if not isinstance(relative_name, str) or not relative_name:
                raise ReportContractError("queue archive ledger relative path missing")
            relative = Path(relative_name)
            if (
                relative.is_absolute()
                or relative.as_posix() != relative_name
                or any(part in {"", ".", ".."} for part in relative.parts)
                or relative_name in relative_names
            ):
                raise ReportContractError("queue archive ledger relative path drift")
            relative_names.add(relative_name)
            expected_original = repo_relative(repo_path(source_path) / relative)
            expected_archived = repo_relative(directory / "training_job" / relative)
            if original_record.get("path") != expected_original:
                raise ReportContractError("queue archive original artifact path drift")
            if record.get("path") != expected_archived or expected_archived in archived_paths:
                raise ReportContractError("queue archive moved artifact path drift")
            original_paths[expected_original] = relative_name
            archived_paths.add(expected_archived)
            if (
                original_record.get("sha256") != record.get("sha256")
                or int(original_record.get("bytes", -1)) != int(record.get("bytes", -2))
            ):
                raise ReportContractError("queue archive ledger/move SHA drift")
            path, _observed = verify_file_binding(
                record, f"queue archived artifact {key} attempt {attempt} item {index + 1}"
            )
            sources.append(file_record(path, f"queue_archived_artifact_{key}_{attempt}"))
        original_terminal_path = original.get("path") if isinstance(original, Mapping) else None
        terminal_relative = original_paths.get(str(original_terminal_path))
        if terminal_relative is None or archived_terminal["path"] != repo_relative(
            directory / "training_job" / terminal_relative
        ):
            raise ReportContractError("queue archive terminal path correspondence drift")
        receipt = receipt_binding(receipt_path)
        row.update(
            {
                "receipt_path": receipt["path"],
                "receipt_sha256": receipt["sha256"],
                "error_type": payload.get("error_type"),
                "error_signature": payload.get("error_signature"),
                "artifact_count": payload.get("artifact_count"),
            }
        )
        rows.append(row)
    for key, attempts in by_job_attempts.items():
        if sorted(attempts) != list(range(1, len(attempts) + 1)):
            raise ReportContractError(f"queue archive attempt sequence drift: {key}")
    return rows, sources


def _safe_recovery_relative(value: Any, label: str) -> Path:
    if not isinstance(value, str) or not value:
        raise ReportContractError(f"{label} relative path missing")
    relative = Path(value)
    if (
        relative.is_absolute()
        or relative.as_posix() != value
        or any(part in {"", ".", ".."} for part in relative.parts)
    ):
        raise ReportContractError(f"{label} relative path drift: {value}")
    return relative


def _recovery_signatures(
    value: Any, label: str
) -> dict[str, dict[str, Any]]:
    if not isinstance(value, list) or not value:
        raise ReportContractError(f"{label} artifact signatures missing")
    result: dict[str, dict[str, Any]] = {}
    for item in value:
        if not isinstance(item, Mapping):
            raise ReportContractError(f"{label} artifact row drift")
        relative = _safe_recovery_relative(item.get("relative_to_root"), label)
        key = relative.as_posix()
        digest = item.get("sha256")
        if (
            key in result
            or not isinstance(digest, str)
            or re.fullmatch(r"[0-9a-f]{64}", digest) is None
            or not isinstance(item.get("bytes"), int)
        ):
            raise ReportContractError(f"{label} artifact signature drift: {key}")
        result[key] = dict(item)
    return result


def _verify_recovery_tree(
    root: Path,
    signatures: Mapping[str, Mapping[str, Any]],
    *,
    excluded: Sequence[str],
    label: str,
    role_prefix: str,
) -> list[dict[str, Any]]:
    if not root.is_dir() or root.is_symlink():
        raise ReportContractError(f"{label} root missing: {repo_relative(root)}")
    excluded_set = set(excluded)
    for value in excluded_set:
        _safe_recovery_relative(value, f"{label} excluded")
    observed: set[str] = set()
    for path in root.rglob("*"):
        if path.is_symlink():
            raise ReportContractError(f"{label} symlink forbidden: {repo_relative(path)}")
        if path.is_file():
            observed.add(path.relative_to(root).as_posix())
    expected = set(signatures) | excluded_set
    if observed != expected:
        raise ReportContractError(f"{label} artifact path-set drift")
    records: list[dict[str, Any]] = []
    for relative_name, signature in sorted(signatures.items()):
        path = root / relative_name
        record = file_record(
            path,
            f"{role_prefix}_{relative_name}",
            expected_sha256=str(signature["sha256"]),
            required=True,
        )
        if int(signature["bytes"]) != int(record["bytes"]):
            raise ReportContractError(f"{label} artifact byte drift: {relative_name}")
        records.append(record)
    for relative_name in sorted(excluded_set):
        records.append(
            file_record(
                root / relative_name,
                f"{role_prefix}_excluded_{relative_name}",
                required=True,
            )
        )
    return records


def _load_queue_recovery_evidence(
    jobs: Sequence[Job],
    entries: Sequence[Mapping[str, Any]],
    config: Mapping[str, Any],
) -> dict[str, Any]:
    contract = config["recovery_contract"]
    root = repo_path(config["sources"]["queue_recovery_root"])
    controller_path = repo_path(config["sources"]["queue_recovery_controller"])
    sources = [file_record(controller_path, "queue_recovery_controller")]
    attempt_dirs = (
        sorted(root.glob("by_building/*/arm_*/*/rehydration_attempt_*"))
        if root.is_dir()
        else []
    )
    if not controller_path.is_file():
        if attempt_dirs:
            raise ReportContractError("queue recovery attempts exist without controller")
        return {"controller": None, "rows": [], "source_records": sources}

    controller = load_json(controller_path)
    controller_spec = contract["controller"]
    if (
        controller.get("schema") != controller_spec["schema"]
        or controller.get("state") != controller_spec["state"]
        or controller.get("task_id") != controller_spec["task_id"]
        or controller.get("run_id") != config["run_id"]
        or controller.get("execution_head")
        != config["provenance_contract"]["execution_head"]
    ):
        raise ReportContractError("queue recovery controller identity drift")
    if (
        controller.get("producer_receipts_rewritten") is not False
        or controller.get("interpretation_or_verdict") is not None
    ):
        raise ReportContractError("queue recovery controller policy drift")
    controller_binding = receipt_binding(controller_path)
    _, plan_binding = verify_file_binding(
        controller.get("queue_plan"), "queue recovery controller plan"
    )
    if plan_binding != receipt_binding(repo_path(config["sources"]["queue_plan"])):
        raise ReportContractError("queue recovery controller/plan binding drift")
    _, driver_binding = verify_file_binding(
        controller.get("committed_queue_driver"),
        "queue recovery committed queue driver",
    )
    if driver_binding != dict(contract["committed_queue_driver"]):
        raise ReportContractError("queue recovery committed driver drift")
    sources.append(
        file_record(
            repo_path(driver_binding["path"]),
            "queue_recovery_committed_driver",
            expected_sha256=driver_binding["sha256"],
            required=True,
        )
    )
    recovery_files = controller.get("recovery_files")
    if recovery_files != contract["controller_files"]:
        raise ReportContractError("queue recovery controller file inventory drift")
    for index, expected in enumerate(contract["controller_files"], 1):
        _path, observed = verify_file_binding(
            expected, f"queue recovery controller file {index}"
        )
        if observed != dict(expected):
            raise ReportContractError("queue recovery controller file SHA/byte drift")
        sources.append(
            file_record(
                repo_path(expected["path"]),
                f"queue_recovery_controller_file_{index}",
                expected_sha256=expected["sha256"],
                required=True,
            )
        )

    known_jobs = {job.key: job for job in jobs}
    expected_entries = [dict(entry) for entry in entries]
    rows: list[dict[str, Any]] = []
    for directory in attempt_dirs:
        if not directory.is_dir() or directory.is_symlink():
            raise ReportContractError("queue recovery attempt directory drift")
        match = re.fullmatch(r"rehydration_attempt_([0-9]{3})", directory.name)
        if match is None:
            raise ReportContractError("queue recovery attempt name drift")
        attempt = int(match.group(1))
        building_id = directory.parents[2].name
        arm_dir = directory.parents[1].name
        replicate = directory.parent.name
        if not arm_dir.startswith("arm_"):
            raise ReportContractError("queue recovery arm directory drift")
        arm = arm_dir[4:]
        key = f"{building_id}/arm_{arm}/{replicate}"
        job = known_jobs.get(key)
        if job is None:
            raise ReportContractError(f"queue recovery identity outside queue: {key}")
        unexpected = [
            path.name
            for path in directory.iterdir()
            if path.name not in {"intent.json", "receipt.json"}
        ]
        if unexpected:
            raise ReportContractError("queue recovery attempt contains unexpected files")
        intent_path = directory / "intent.json"
        sources.append(
            file_record(
                intent_path,
                f"queue_recovery_intent_{key}_{attempt}",
                required=True,
            )
        )
        intent = load_json(intent_path)
        if (
            intent.get("schema") != contract["rehydration_intent_schema"]
            or intent.get("state") != "PLANNED"
            or intent.get("execution_head")
            != config["provenance_contract"]["execution_head"]
            or intent.get("entry") not in expected_entries
            or intent.get("producer_receipts_rewritten") is not False
            or intent.get("interpretation_or_verdict") is not None
        ):
            raise ReportContractError("queue recovery intent identity/policy drift")
        entry = intent["entry"]
        if queue_job_key(entry) != key:
            raise ReportContractError("queue recovery directory/entry identity drift")
        _, observed_controller = verify_file_binding(
            intent.get("controller"), "queue recovery intent controller"
        )
        if observed_controller != controller_binding:
            raise ReportContractError("queue recovery intent/controller binding drift")
        archive_root = (
            repo_path(config["sources"]["queue_training_failure_archive"])
            / "by_building"
            / building_id
            / f"arm_{arm}"
            / replicate
            / f"attempt_{attempt:03d}"
        )
        source_root = archive_root / "training_job"
        expected_archive_receipt = receipt_binding(archive_root / "archive_receipt.json")
        _, archive_binding = verify_file_binding(
            intent.get("source_archive_receipt"),
            "queue recovery intent source archive",
        )
        if archive_binding != expected_archive_receipt:
            raise ReportContractError("queue recovery source archive binding drift")
        sources.append(
            file_record(
                archive_root / "archive_receipt.json",
                f"queue_recovery_source_archive_{key}_{attempt}",
                required=True,
            )
        )
        if intent.get("source_training_root") != repo_relative(source_root):
            raise ReportContractError("queue recovery source training root drift")
        destination_root, _readout = job_dirs(job, config)
        if intent.get("destination_training_root") != repo_relative(destination_root):
            raise ReportContractError("queue recovery destination training root drift")
        excluded = intent.get("excluded_artifacts")
        if excluded != contract["excluded_artifacts"]:
            raise ReportContractError("queue recovery excluded artifact drift")
        copied = _recovery_signatures(intent.get("copied_artifacts"), "queue recovery intent")
        sources.extend(
            _verify_recovery_tree(
                source_root,
                copied,
                excluded=excluded,
                label="queue recovery archive source",
                role_prefix=f"queue_recovery_source_{key}_{attempt}",
            )
        )
        completion = intent.get("source_completion_evidence")
        if not isinstance(completion, Mapping) or int(
            completion.get("completed_optimizer_updates", -1)
        ) != 30000:
            raise ReportContractError("queue recovery completion evidence drift")
        for name in ("completed", "final_checkpoint", "materialization", "started"):
            path, observed = verify_file_binding(
                completion.get(name), f"queue recovery completion {name}"
            )
            try:
                relative_name = path.resolve().relative_to(source_root.resolve()).as_posix()
            except ValueError as exc:
                raise ReportContractError(
                    "queue recovery completion evidence escaped source archive"
                ) from exc
            signature = copied.get(relative_name)
            if signature is None or (
                observed["sha256"] != signature["sha256"]
                or observed["bytes"] != signature["bytes"]
            ):
                raise ReportContractError("queue recovery completion/artifact drift")
            sources.append(
                file_record(path, f"queue_recovery_completion_{key}_{attempt}_{name}")
            )

        receipt_path = directory / "receipt.json"
        receipt_payload: dict[str, Any] | None = None
        receipt_state = "PLANNED"
        if receipt_path.is_file():
            sources.append(
                file_record(
                    receipt_path,
                    f"queue_recovery_receipt_{key}_{attempt}",
                    required=True,
                )
            )
            receipt_payload = load_json(receipt_path)
            if (
                receipt_payload.get("schema")
                != contract["rehydration_receipt_schema"]
                or receipt_payload.get("state")
                != contract["rehydration_receipt_state"]
                or receipt_payload.get("entry") != entry
                or receipt_payload.get("execution_head")
                != config["provenance_contract"]["execution_head"]
                or receipt_payload.get("producer_receipts_rewritten") is not False
                or receipt_payload.get("append_only_source_preserved") is not True
                or receipt_payload.get("interpretation_or_verdict") is not None
            ):
                raise ReportContractError("queue recovery receipt identity/policy drift")
            _, intent_binding = verify_file_binding(
                receipt_payload.get("intent"), "queue recovery receipt intent"
            )
            if intent_binding != receipt_binding(intent_path):
                raise ReportContractError("queue recovery receipt/intent binding drift")
            _, receipt_archive = verify_file_binding(
                receipt_payload.get("source_archive_receipt"),
                "queue recovery receipt source archive",
            )
            if receipt_archive != archive_binding:
                raise ReportContractError("queue recovery receipt/archive binding drift")
            if (
                receipt_payload.get("destination_training_root")
                != repo_relative(destination_root)
                or receipt_payload.get("excluded_artifacts") != excluded
            ):
                raise ReportContractError("queue recovery receipt destination drift")
            destination = _recovery_signatures(
                receipt_payload.get("destination_artifacts"),
                "queue recovery receipt",
            )
            if destination != copied:
                raise ReportContractError("queue recovery source/destination ledger drift")
            defect = receipt_payload.get("defect")
            if not isinstance(defect, Mapping) or (
                defect.get("error_type") != "ReceiptShapeMismatch"
                or defect.get("reason")
                != "training_receipts_or_materialization_do_not_match_runtime_head"
                or defect.get("producer_shape") != ["path", "sha256"]
                or defect.get("queue_shape") != ["path", "sha256", "bytes"]
            ):
                raise ReportContractError("queue recovery defect record drift")
            sources.extend(
                _verify_recovery_tree(
                    destination_root,
                    destination,
                    excluded=[],
                    label="queue recovery destination",
                    role_prefix=f"queue_recovery_destination_{key}_{attempt}",
                )
            )
            receipt_state = str(receipt_payload["state"])
        rows.append(
            {
                "job_key": key,
                "building_id": building_id,
                "arm": arm,
                "run": replicate,
                "archive_attempt": attempt,
                "recovery_state": receipt_state,
                "intent_path": repo_relative(intent_path),
                "intent_sha256": sha256_file(intent_path),
                "receipt_path": repo_relative(receipt_path),
                "receipt_sha256": (
                    sha256_file(receipt_path) if receipt_path.is_file() else None
                ),
                "source_artifacts_n": len(copied),
                "destination_artifacts_n": (
                    len(receipt_payload.get("destination_artifacts", []))
                    if receipt_payload is not None
                    else None
                ),
                "producer_receipts_rewritten": False,
                "append_only_source_preserved": (
                    receipt_payload.get("append_only_source_preserved")
                    if receipt_payload is not None
                    else None
                ),
            }
        )
    return {"controller": controller, "rows": rows, "source_records": sources}


def load_queue_evidence(
    jobs: Sequence[Job], config: Mapping[str, Any]
) -> dict[str, Any]:
    specs = expected_queue_stage_specs(jobs, config)
    source_records = _queue_top_source_records(config)
    plan_path = repo_path(config["sources"]["queue_plan"])
    plan: dict[str, Any] | None = None
    entries: list[dict[str, Any]] = [dict(spec) for spec in specs]
    if plan_path.is_file():
        plan = load_json(plan_path)
        if plan.get("schema") != QUEUE_PLAN_SCHEMA or plan.get("run_id") != config["run_id"]:
            raise ReportContractError("queue plan schema/run drift")
        if plan.get("state") != "ACTIVE":
            raise ReportContractError("queue plan state drift")
        queue_config_payload = load_json(
            repo_path(config["locked_inputs"]["queue_config"]["path"])
        )
        if plan.get("task_id") != queue_config_payload.get("task_id"):
            raise ReportContractError("queue plan task identity drift")
        if int(plan.get("stage_entries_n", -1)) != int(
            config["queue_contract"]["expected_stage_entries"]
        ):
            raise ReportContractError("queue plan declared stage-entry count drift")
        if int(plan.get("unique_jobs_n", -1)) != int(
            config["queue_contract"]["expected_jobs"]
        ):
            raise ReportContractError("queue plan declared unique-job count drift")
        if plan.get("actual_training_started_at_publication") is not False:
            raise ReportContractError("queue plan publication-state drift")
        if plan.get("interpretation_or_verdict") is not None:
            raise ReportContractError("queue plan contains interpretation or verdict")
        plan_entries = plan.get("entries")
        if not isinstance(plan_entries, list) or len(plan_entries) != len(specs):
            raise ReportContractError("queue plan stage-entry count drift")
        entries = []
        for observed, spec in zip(plan_entries, specs):
            if not isinstance(observed, Mapping) or not _entry_matches_spec(observed, spec):
                raise ReportContractError("queue plan entry order/identity drift")
            entries.append(dict(observed))
        unique = {queue_job_key(entry) for entry in entries}
        expected = {job.key for job in jobs}
        if unique != expected:
            raise ReportContractError("queue plan 22-to-21 identity dedup drift")
        queue_config = config["locked_inputs"]["queue_config"]
        _, queue_config_observed = verify_file_binding(
            plan.get("config"), "queue plan config"
        )
        if queue_config_observed["path"] != queue_config["path"] or queue_config_observed[
            "sha256"
        ] != queue_config["sha256"]:
            raise ReportContractError("queue plan/config binding drift")
        git_lock = plan.get("git_lock")
        if not isinstance(git_lock, Mapping) or git_lock.get("head") != config[
            "provenance_contract"
        ]["execution_head"]:
            raise ReportContractError("queue plan execution HEAD drift")

    stage_rows: list[dict[str, Any]] = []
    present_by_path: dict[str, dict[str, Any]] = {}
    for entry in entries:
        path = queue_stage_record_path(config, entry)
        source_records.append(file_record(path, f"queue_stage_record_{entry['global_entry_order']}"))
        payload: dict[str, Any] | None = None
        source_receipts: list[dict[str, Any]] = []
        if path.is_file():
            if plan is None:
                raise ReportContractError("queue stage record exists without queue plan")
            payload = load_json(path)
            if payload.get("schema") != QUEUE_STAGE_RECORD_SCHEMA:
                raise ReportContractError("queue stage-record schema drift")
            if payload.get("entry") != entry:
                raise ReportContractError("queue stage-record entry drift")
            if payload.get("status") not in {"MEASURED", "SKIPPED"}:
                raise ReportContractError("queue stage-record terminal status drift")
            raw_receipts = payload.get("source_receipts")
            if not isinstance(raw_receipts, list) or not raw_receipts:
                raise ReportContractError("queue stage-record source receipts missing")
            if payload["status"] == "MEASURED" and len(raw_receipts) != 1:
                raise ReportContractError("queue MEASURED source receipt count drift")
            if payload["status"] == "SKIPPED":
                if len(raw_receipts) != 3 or int(
                    payload.get("same_signature_attempts", -1)
                ) != 3:
                    raise ReportContractError("queue SKIPPED retry receipt count drift")
                if not payload.get("error_type") or not payload.get("error_signature"):
                    raise ReportContractError("queue SKIPPED error identity missing")
            for index, record in enumerate(raw_receipts):
                _path, observed = verify_file_binding(
                    record,
                    f"queue stage-record {entry['global_entry_order']} source {index + 1}",
                )
                source_receipts.append(observed)
            current = receipt_binding(path)
            present_by_path[current["path"]] = payload
        stage_rows.append(
            {
                **{key: entry.get(key) for key in specs[0]},
                "job_key": queue_job_key(entry),
                "stage_record_state": payload.get("status") if payload else "MISSING",
                "stage_record_path": repo_relative(path),
                "stage_record_sha256": sha256_file(path) if path.is_file() else None,
                "source_receipts_json": source_receipts,
                "smoke_reuse_json": payload.get("smoke_reuse") if payload else None,
                "payload": payload,
            }
        )

    by_key: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in stage_rows:
        by_key[row["job_key"]].append(row)
    canonical: dict[str, dict[str, Any]] = {}
    smoke_key = jobs[0].key
    for job in jobs:
        candidates = by_key[job.key]
        expected_n = 2 if job.key == smoke_key else 1
        if len(candidates) != expected_n:
            raise ReportContractError(f"queue stage multiplicity drift: {job.key}")
        present = [row for row in candidates if row["payload"] is not None]
        if job.key == smoke_key:
            smoke = next(row for row in candidates if row["stage_key"] == config["queue_contract"]["smoke_stage_key"])
            reuse = next(row for row in candidates if row["stage_key"] == config["queue_contract"]["reuse_stage_key"])
            if reuse["payload"] is not None:
                if smoke["payload"] is None:
                    raise ReportContractError("queue smoke reuse exists before smoke stage record")
                if smoke["stage_record_state"] != "MEASURED" or reuse["stage_record_state"] != "MEASURED":
                    raise ReportContractError("queue duplicate smoke status diverged")
                if smoke["source_receipts_json"] != reuse["source_receipts_json"]:
                    raise ReportContractError("queue duplicate smoke source receipt drift")
                reuse_contract = reuse["payload"].get("smoke_reuse")
                if not isinstance(reuse_contract, Mapping) or reuse_contract.get("reused") is not True:
                    raise ReportContractError("queue smoke reuse binding missing")
                _, smoke_observed = verify_file_binding(
                    reuse_contract.get("smoke_stage_record"), "queue smoke stage-record reuse"
                )
                if smoke_observed["path"] != smoke["stage_record_path"] or smoke_observed[
                    "sha256"
                ] != smoke["stage_record_sha256"]:
                    raise ReportContractError("queue smoke stage-record SHA drift")
                if reuse_contract.get("identical_readout_complete_receipt") != reuse[
                    "source_receipts_json"
                ][0]:
                    raise ReportContractError("queue smoke readout receipt reuse drift")
            selected = reuse if reuse["payload"] is not None else smoke
        else:
            selected = candidates[0]
        payload = selected["payload"]
        measured_payload = None
        if payload is not None and payload.get("status") == "MEASURED":
            source_path, _observed = verify_file_binding(
                payload["source_receipts"][0], "queue measured readout receipt"
            )
            measured_payload = load_json(source_path)
            if measured_payload.get("schema") != READOUT_COMPLETE_SCHEMA or measured_payload.get(
                "state"
            ) != "COMPLETE":
                raise ReportContractError("queue measured readout receipt drift")
            if measured_payload.get("identity") != {
                "building_id": job.building_id,
                "arm": job.arm,
                "replicate": job.run,
                "profile": "full",
            }:
                raise ReportContractError("queue measured readout identity drift")
            if nested_get(
                measured_payload, "primary.eligible_for_preregistered_judgment"
            ) is not True:
                raise ReportContractError("queue measured primary eligibility drift")
            if nested_get(
                measured_payload, "legacy_alpha.eligible_for_preregistered_judgment"
            ) is not False:
                raise ReportContractError("queue measured legacy eligibility drift")
        canonical[job.key] = {
            "stage_record": selected,
            "terminal_status": payload.get("status") if payload else None,
            "measured_payload": measured_payload,
            "deduplicated_stage_entries_n": len(candidates),
        }

    archive_rows, archive_sources = _queue_archive_rows(jobs, config)
    source_records.extend(archive_sources)
    archives_by_job: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in archive_rows:
        archives_by_job[row["job_key"]].append(row)
    for key, value in canonical.items():
        value["archives"] = archives_by_job.get(key, [])

    recovery = _load_queue_recovery_evidence(jobs, entries, config)
    source_records.extend(recovery["source_records"])
    recovery_by_job: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in recovery["rows"]:
        recovery_by_job[row["job_key"]].append(row)
    for key, value in canonical.items():
        value["recoveries"] = recovery_by_job.get(key, [])

    complete = _validate_queue_complete(config, plan_path, present_by_path) if plan else None
    unique_sources: dict[tuple[str, str], dict[str, Any]] = {}
    for row in source_records:
        unique_sources[(row["role"], row["path"])] = row
    return {
        "plan": plan,
        "complete": complete,
        "recovery_controller": recovery["controller"],
        "stage_rows": stage_rows,
        "archive_rows": archive_rows,
        "recovery_rows": recovery["rows"],
        "jobs": canonical,
        "source_records": sorted(
            unique_sources.values(), key=lambda row: (row["role"], row["path"])
        ),
        "stage_entries_n": len(stage_rows),
        "unique_jobs_n": len(canonical),
        "terminal_unique_jobs_n": sum(
            value["terminal_status"] in {"MEASURED", "SKIPPED"}
            for value in canonical.values()
        ),
        "incomplete_archives_n": sum(
            row["archive_state"] == "INCOMPLETE" for row in archive_rows
        ),
        "rehydrated_attempts_n": sum(
            row["recovery_state"]
            == config["recovery_contract"]["rehydration_receipt_state"]
            for row in recovery["rows"]
        ),
    }


def nested_get(payload: Mapping[str, Any], path: str) -> Any:
    value: Any = payload
    for key in path.split("."):
        if not isinstance(value, Mapping) or key not in value:
            return None
        value = value[key]
    return value


def path_from_record(value: Any) -> Path | None:
    if isinstance(value, str) and value:
        return repo_path(value)
    if isinstance(value, Mapping) and isinstance(value.get("path"), str):
        return repo_path(value["path"])
    return None


def contains_censored(payload: Any) -> bool:
    if isinstance(payload, Mapping):
        for key, value in payload.items():
            low_key = str(key).lower()
            if low_key in {"censored", "is_censored"} and value is True:
                return True
            if low_key in {"status", "measurement_state", "state"} and str(value).lower() == "censored":
                return True
            if "censored" in low_key and value not in (None, "", False, 0, [], {}):
                return True
            if contains_censored(value):
                return True
    elif isinstance(payload, list):
        return any(contains_censored(value) for value in payload)
    return False


def scalar(value: Any, *, boolean: bool = False) -> bool | float | str | None:
    if value is None or value == "":
        return None
    if boolean:
        if isinstance(value, bool):
            return value
        low = str(value).strip().lower()
        if low in TRUE_VALUES:
            return True
        if low in FALSE_VALUES:
            return False
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        number = float(value)
        return number if math.isfinite(number) else None
    try:
        number = float(str(value))
    except ValueError:
        return str(value)
    return number if math.isfinite(number) else None


def metric_value(
    row: Mapping[str, Any] | None,
    metric: str,
    config: Mapping[str, Any],
    *,
    censored: bool = False,
) -> tuple[Any, str]:
    if censored:
        return None, "censored"
    if not isinstance(row, Mapping):
        return None, "missing"
    value = scalar(
        row.get(metric),
        boolean=metric in set(config["measurement_contract"]["boolean_metrics"]),
    )
    return (value, "measured") if value is not None else (None, "missing")


def score_has_measurement(
    row: Mapping[str, Any] | None, config: Mapping[str, Any]
) -> bool:
    if not isinstance(row, Mapping):
        return False
    return any(
        metric_value(row, metric, config)[1] == "measured"
        for metric in config["measurement_contract"]["metric_fields"]
    )


def find_score_row(payload: Mapping[str, Any], branch: str) -> Mapping[str, Any] | None:
    direct_paths = (
        f"{branch}.measurements",
        f"{branch}.canonical_score_row",
        f"{branch}.score.row",
        f"{branch}.score_row",
        f"{branch}.score.receipt.row",
        f"{branch}.score_receipt.row",
    )
    for path in direct_paths:
        value = nested_get(payload, path)
        if isinstance(value, Mapping):
            return value
    node = payload.get(branch)
    metrics = {"assembly_lod2_success", "plane_f1", "roof_rms_m"}

    def search(value: Any) -> Mapping[str, Any] | None:
        if isinstance(value, Mapping):
            if metrics.intersection(value):
                return value
            for key in ("row", "score", "measurement", "receipt"):
                if key in value:
                    found = search(value[key])
                    if found is not None:
                        return found
            for child in value.values():
                found = search(child)
                if found is not None:
                    return found
        elif isinstance(value, list):
            for child in value:
                found = search(child)
                if found is not None:
                    return found
        return None

    return search(node)


def branch_observation(
    payload: Mapping[str, Any] | None, branch: str
) -> dict[str, Any]:
    """Extract an explicit non-measurement outcome without inventing a score.

    The legacy alpha comparison is allowed to finish as NOT_ASSEMBLED or
    UNCONSTRUCTABLE while the primary TSDF readout remains complete.  Receipt
    producers may nest the reason/count diagnostics, so the report preserves
    their field paths in a compact object instead of treating the absence of a
    score as an unexplained missing value.
    """
    node = payload.get(branch) if isinstance(payload, Mapping) else None
    result: dict[str, Any] = {
        "outcome": None,
        "assembly_status": None,
        "measurement_status": None,
        "reason_code": None,
        "reason": None,
        "counts": {},
        "receipt_path": None,
    }
    allowed = {"NOT_ASSEMBLED", "UNCONSTRUCTABLE", "NOT_APPLICABLE"}
    outcome_keys = {
        "state",
        "status",
        "outcome",
        "assembly_state",
        "measurement_state",
        "comparison_state",
    }
    reason_keys = {
        "reason",
        "message",
        "detail",
        "explanation",
        "nonassembly_reason",
        "unconstructable_reason",
    }

    def visit(value: Any, prefix: str = "") -> None:
        if isinstance(value, Mapping):
            for key, child in value.items():
                low = str(key).lower()
                field = f"{prefix}.{key}" if prefix else str(key)
                if low in outcome_keys and isinstance(child, str):
                    normalized = re.sub(r"[^A-Z0-9]+", "_", child.upper()).strip("_")
                    if normalized in allowed and result["outcome"] is None:
                        result["outcome"] = normalized
                if low == "assembly_status" and isinstance(child, str):
                    result["assembly_status"] = child
                if low == "measurement_status" and isinstance(child, str):
                    result["measurement_status"] = child
                if low == "reason_code" and child not in (None, ""):
                    result["reason_code"] = str(child)
                    if result["reason"] is None:
                        result["reason"] = str(child)
                if low == "receipt":
                    receipt = path_from_record(child)
                    if receipt is not None:
                        result["receipt_path"] = repo_relative(receipt)
                if (
                    low in reason_keys
                    and child not in (None, "", [], {})
                    and result["reason"] is None
                ):
                    result["reason"] = str(child)
                if low == "counts" and isinstance(child, Mapping):
                    result["counts"] = dict(child)
                if (
                    isinstance(child, (int, float))
                    and not isinstance(child, bool)
                    and (
                        low.endswith(("_n", "_count", "_points"))
                        or low.startswith("n_")
                        or low in {"count", "points"}
                    )
                ):
                    if not result["counts"]:
                        result["counts"][field] = child
                visit(child, field)
        elif isinstance(value, list):
            for index, child in enumerate(value):
                visit(child, f"{prefix}[{index}]")

    visit(node)
    return result


def terminal_evidence(job_dir: Path, training_dir: Path) -> tuple[str, str, dict[str, Any] | None]:
    complete = job_dir / "complete.json"
    if complete.is_file():
        payload = load_json(complete)
        if payload.get("schema") != READOUT_COMPLETE_SCHEMA or payload.get("state") != "COMPLETE":
            raise ReportContractError(
                f"authoritative readout complete receipt drift: {repo_relative(complete)}"
            )
        if nested_get(payload, "primary.eligible_for_preregistered_judgment") is not True:
            raise ReportContractError("primary readout judgment eligibility drift")
        if nested_get(payload, "legacy_alpha.eligible_for_preregistered_judgment") is not False:
            raise ReportContractError("legacy alpha judgment eligibility drift")
        # A comparison-only legacy branch cannot censor or fail the primary
        # preregistered measurement.
        if contains_censored(payload.get("primary")):
            return "censored", repo_relative(complete), payload
        return "measured", repo_relative(complete), payload
    candidates = [
        job_dir / "skipped.json",
        job_dir / "failed.json",
        job_dir / "terminal_failure.json",
        training_dir / "failed.json",
    ]
    for path in candidates:
        if path.is_file():
            payload = load_json(path)
            state = "censored" if contains_censored(payload) else (
                "skipped" if "skip" in path.name else "failed"
            )
            return state, repo_relative(path), payload
    attempts = sorted(
        list(job_dir.glob("attempts/attempt_*/failure.json"))
        + list(job_dir.glob("attempts/attempt_*/failed.json"))
    )
    if attempts:
        payload = load_json(attempts[-1])
        if payload.get("terminal") is True:
            state = "censored" if contains_censored(payload) else "failed"
            return state, repo_relative(attempts[-1]), payload
        signatures = [str(load_json(path).get("error_signature", "")) for path in attempts]
        if (
            len(signatures) >= 3
            and signatures[-1]
            and len(set(signatures[-3:])) == 1
        ):
            state = "censored" if contains_censored(payload) else "skipped"
            return state, repo_relative(attempts[-1]), payload
        return "retry_pending", repo_relative(attempts[-1]), payload
    started = job_dir / "started.json"
    training_started = training_dir / "started.json"
    if started.is_file() or training_started.is_file():
        path = started if started.is_file() else training_started
        return "running", repo_relative(path), load_json(path)
    if (training_dir / "completed.json").is_file():
        return "readout_pending", repo_relative(training_dir / "completed.json"), None
    return "pending", "", None


def load_p0prime_scores(config: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    path = repo_path(config["sources"]["T3_scores"])
    rows: list[dict[str, Any]] = []
    if path.is_file():
        rows.extend(read_csv(path))
    else:
        root = repo_path(config["sources"]["T3"]).parent / "by_building"
        for receipt in sorted(root.glob("*/score_receipt.json")):
            payload = load_json(receipt)
            row = payload.get("row")
            if isinstance(row, Mapping):
                rows.append(dict(row))
    result: dict[str, dict[str, Any]] = {}
    for row in rows:
        building_id = str(row.get("building_id", ""))
        if building_id:
            result[building_id] = dict(row)
    return result


def preprocess_building_root(config: Mapping[str, Any], building_id: str) -> Path:
    sources = config["sources"]
    return (
        repo_path(sources["run_root"])
        / "preprocess_aprime"
        / sources["preprocess_cache_namespace"]
        / "by_building"
        / building_id
    )


def load_t5(config: Mapping[str, Any]) -> dict[str, dict[str, str]]:
    path = repo_path(config["sources"]["t5_summary"])
    if not path.is_file():
        return {}
    return {row["building_id"]: row for row in read_csv(path) if row.get("building_id")}


def job_dirs(job: Job, config: Mapping[str, Any]) -> tuple[Path, Path]:
    sources = config["sources"]
    training = (
        repo_path(sources["training_root"])
        / "by_building"
        / job.building_id
        / f"arm_{job.arm}"
        / job.run
    )
    readout = (
        repo_path(sources["readout_root"])
        / "by_building"
        / job.building_id
        / f"arm_{job.arm}"
        / job.run
    )
    return training, readout


def selected_readout_paths(
    job_dir: Path, payload: Mapping[str, Any] | None
) -> dict[str, Path | None]:
    """Resolve review inputs from the complete receipt, then bounded fallbacks."""
    result: dict[str, Path | None] = {
        "tsdf_npz": None,
        "mesh": None,
        "cityjson": None,
        "alpha_npz": None,
        "alpha_cityjson": None,
    }
    preferred_names = {
        "tsdf_npz": "tsdf_surface_samples.npz",
        "mesh": "tsdf_mesh_filtered_epsg25832_orthometric.ply",
        "cityjson": "seed_p0prime.city.json",
        "alpha_npz": "readout.npz",
    }

    def visit(value: Any, branch: str = "") -> None:
        if isinstance(value, Mapping):
            for key, child in value.items():
                visit(child, f"{branch}.{key}" if branch else str(key))
        elif isinstance(value, list):
            for child in value:
                visit(child, branch)
        elif isinstance(value, str):
            path = repo_path(value)
            name = path.name
            low_context = f"{branch} {value}".lower()
            if name == preferred_names["tsdf_npz"] and "legacy" not in low_context:
                result["tsdf_npz"] = result["tsdf_npz"] or path
            elif name == preferred_names["mesh"] and "legacy" not in low_context:
                result["mesh"] = result["mesh"] or path
            elif name == preferred_names["alpha_npz"] and "legacy" in low_context:
                result["alpha_npz"] = result["alpha_npz"] or path
            elif name.endswith(".city.json"):
                if "legacy" in low_context:
                    result["alpha_cityjson"] = result["alpha_cityjson"] or path
                else:
                    result["cityjson"] = result["cityjson"] or path

    if payload is not None:
        visit(payload)
    fallbacks = {
        "tsdf_npz": "attempts/attempt_*/tsdf/tsdf_surface_samples.npz",
        "mesh": "attempts/attempt_*/tsdf/tsdf_mesh_filtered_epsg25832_orthometric.ply",
        "cityjson": "attempts/attempt_*/primary/engine/by_building/*/cityjson/*.city.json",
        "alpha_npz": "attempts/attempt_*/legacy_alpha/pointcloud/readout.npz",
        "alpha_cityjson": "attempts/attempt_*/legacy_alpha/engine/by_building/*/cityjson/*.city.json",
    }
    for key, pattern in fallbacks.items():
        current = result[key]
        if current is not None and current.is_file():
            continue
        matches = sorted(job_dir.glob(pattern))
        result[key] = matches[-1] if matches else current
    return result


def build_score_rows(
    jobs: Sequence[Job],
    config: Mapping[str, Any],
    p0prime: Mapping[str, Mapping[str, Any]],
    t5: Mapping[str, Mapping[str, str]],
    queue_evidence: Mapping[str, Any] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, dict[str, Any]]]:
    contract = config["measurement_contract"]
    metrics = list(contract["metric_fields"])
    boolean = set(contract["boolean_metrics"])
    rows: list[dict[str, Any]] = []
    alpha_rows: list[dict[str, Any]] = []
    runtime: dict[str, dict[str, Any]] = {}
    for job in jobs:
        training_dir, readout_dir = job_dirs(job, config)
        raw_terminal, raw_evidence, raw_receipt = terminal_evidence(
            readout_dir, training_dir
        )
        queue_job = (
            queue_evidence.get("jobs", {}).get(job.key)
            if isinstance(queue_evidence, Mapping)
            else None
        )
        if isinstance(queue_job, Mapping):
            queue_status = queue_job.get("terminal_status")
            stage = queue_job["stage_record"]
            if queue_status == "MEASURED":
                terminal = "measured"
                evidence = stage["stage_record_path"]
                receipt = queue_job.get("measured_payload")
            elif queue_status == "SKIPPED":
                terminal = "skipped"
                evidence = stage["stage_record_path"]
                receipt = stage.get("payload")
            else:
                terminal = (
                    "queue_pending"
                    if raw_terminal in TERMINAL_STATES
                    else raw_terminal
                )
                evidence = raw_evidence
                receipt = None
        else:
            terminal, evidence, receipt = raw_terminal, raw_evidence, raw_receipt
        censored = terminal == "censored"
        primary_candidate = find_score_row(receipt, "primary") if receipt else None
        alpha_candidate = find_score_row(receipt, "legacy_alpha") if receipt else None
        primary = (
            primary_candidate
            if score_has_measurement(primary_candidate, config)
            else None
        )
        alpha = (
            alpha_candidate if score_has_measurement(alpha_candidate, config) else None
        )
        primary_observation = branch_observation(receipt, "primary")
        alpha_observation = branch_observation(receipt, "legacy_alpha")
        if terminal == "measured" and primary is None:
            if isinstance(queue_job, Mapping):
                raise ReportContractError(
                    f"queue MEASURED receipt lacks primary score: {job.key}"
                )
            terminal = "failed"
        if terminal == "measured" and contains_censored((receipt or {}).get("primary")):
            raise ReportContractError("queue measured primary receipt is censored")
        primary_state = "censored" if censored else (
            "measured" if primary is not None else "missing"
        )
        if alpha is not None:
            alpha_state = "measured"
        elif alpha_observation["outcome"] is not None:
            alpha_state = "not_applicable"
        elif contains_censored((receipt or {}).get("legacy_alpha")):
            alpha_state = "censored"
        else:
            alpha_state = "missing"
        target = job.target
        seed = t5.get(job.building_id, {})
        evidence_path = repo_path(evidence) if evidence else None
        queue_stage = queue_job.get("stage_record", {}) if isinstance(queue_job, Mapping) else {}
        queue_archives = queue_job.get("archives", []) if isinstance(queue_job, Mapping) else []
        queue_recoveries = (
            queue_job.get("recoveries", []) if isinstance(queue_job, Mapping) else []
        )
        base: dict[str, Any] = {
            "schema": "jointbuildgs.fusion_w1_aprime.report.score_row.v1",
            "task_id": config["task_id"],
            "run_id": config["run_id"],
            "queue_order": job.queue_order,
            "job_key": job.key,
            "building_id": job.building_id,
            "arm": job.arm,
            "run": job.run,
            "target_role": target.get("target_role", ""),
            "tier": target.get("tier", ""),
            "cohort": target.get("cohort", ""),
            "texture_low_gradient_fraction": scalar(
                target.get("texture_low_gradient_fraction")
            ),
            "texture_stratum": texture_stratum(target, config),
            "gs4buildings_overlap_status": target.get(
                "gs4buildings_overlap_status", ""
            ),
            "job_terminal_state": terminal,
            "terminal_evidence": evidence,
            "terminal_evidence_sha256": (
                sha256_file(evidence_path)
                if evidence_path is not None and evidence_path.is_file()
                else None
            ),
            "queue_stage_key": queue_stage.get("stage_key"),
            "queue_stage_entry_order": queue_stage.get("stage_entry_order"),
            "queue_stage_record_path": queue_stage.get("stage_record_path"),
            "queue_stage_record_sha256": queue_stage.get("stage_record_sha256"),
            "queue_deduplicated_stage_entries_n": (
                queue_job.get("deduplicated_stage_entries_n")
                if isinstance(queue_job, Mapping)
                else None
            ),
            "queue_archived_attempts_n": sum(
                row.get("archive_state") == "ARCHIVED" for row in queue_archives
            ),
            "queue_incomplete_archives_n": sum(
                row.get("archive_state") == "INCOMPLETE" for row in queue_archives
            ),
            "queue_rehydrated_attempts_n": sum(
                row.get("recovery_state")
                == config["recovery_contract"]["rehydration_receipt_state"]
                for row in queue_recoveries
            ),
            "queue_recovery_receipts_json": queue_recoveries,
            "primary_readout_role": contract["primary_readout_role"],
            "primary_eligible_for_preregistered_gauges": True,
            "primary_measurement_state": primary_state,
            "alpha_comparison_state": alpha_state,
            "alpha_comparison_outcome": alpha_observation["outcome"],
            "alpha_comparison_assembly_status": alpha_observation[
                "assembly_status"
            ],
            "alpha_comparison_measurement_status": alpha_observation[
                "measurement_status"
            ],
            "alpha_comparison_reason_code": alpha_observation["reason_code"],
            "alpha_comparison_reason": alpha_observation["reason"],
            "alpha_comparison_counts_json": alpha_observation["counts"],
            "alpha_comparison_receipt_path": alpha_observation["receipt_path"],
            "seed_filter_before_n": scalar(seed.get("seed_filter_before_n")),
            "seed_filter_after_n": scalar(seed.get("seed_filter_after_n")),
            "seed_too_small": scalar(seed.get("seed_too_small"), boolean=True),
            "mask_pixels_total": scalar(seed.get("mask_pixels_total")),
            "mask_fraction_mean": scalar(seed.get("mask_fraction_mean")),
            "p0prime_delta_definition": contract["p0prime_delta_definition"],
            "reference_absolute_metric_caveat": contract["reference_caveat"],
            "panel_state": "missing",
            "panel_path": "",
            "opacity_state": "missing",
            "opacity_path": "",
        }
        p0row = p0prime.get(job.building_id)
        for metric in metrics:
            value, state = metric_value(primary, metric, config, censored=censored)
            p0_value, p0_state = metric_value(p0row, metric, config)
            base[metric] = value
            base[f"{metric}_state"] = state
            base[f"p0prime_{metric}"] = p0_value
            base[f"p0prime_{metric}_state"] = p0_state
            if state == "measured" and p0_state == "measured":
                left = int(value) if metric in boolean else float(value)
                right = int(p0_value) if metric in boolean else float(p0_value)
                base[f"delta_vs_p0prime_{metric}"] = left - right
                base[f"delta_vs_p0prime_{metric}_state"] = "measured"
            else:
                base[f"delta_vs_p0prime_{metric}"] = None
                base[f"delta_vs_p0prime_{metric}_state"] = (
                    "censored" if "censored" in {state, p0_state} else "missing"
                )
        rms = base.get("roof_rms_m")
        p0_rms = base.get("p0prime_roof_rms_m")
        if (
            base.get("roof_rms_m_state") == "measured"
            and base.get("p0prime_roof_rms_m_state") == "measured"
        ):
            base["rms_within_p0prime_plus_0p05"] = float(rms) <= float(p0_rms) + float(
                contract["rms_margin_m"]
            )
            base["rms_within_p0prime_plus_0p05_state"] = "measured"
        else:
            base["rms_within_p0prime_plus_0p05"] = None
            base["rms_within_p0prime_plus_0p05_state"] = (
                "censored" if censored else "missing"
            )
        rows.append(base)
        for role, score, state, eligible, observation in (
            (
                contract["primary_readout_role"],
                primary,
                primary_state,
                True,
                primary_observation,
            ),
            (
                contract["comparison_readout_role"],
                alpha,
                alpha_state,
                False,
                alpha_observation,
            ),
        ):
            comparison = {
                "schema": "jointbuildgs.fusion_w1_aprime.report.readout_comparison_row.v1",
                "task_id": config["task_id"],
                "run_id": config["run_id"],
                "queue_order": job.queue_order,
                "job_key": job.key,
                "building_id": job.building_id,
                "arm": job.arm,
                "run": job.run,
                "readout_role": role,
                "eligible_for_preregistered_gauges": eligible,
                "measurement_state": state,
                "nonmeasurement_outcome": observation["outcome"],
                "assembly_status": observation["assembly_status"],
                "measurement_status": observation["measurement_status"],
                "reason_code": observation["reason_code"],
                "nonmeasurement_reason": observation["reason"],
                "diagnostic_counts_json": observation["counts"],
                "branch_receipt_path": observation["receipt_path"],
                "terminal_evidence": evidence,
            }
            for metric in metrics:
                value, metric_state = metric_value(
                    score, metric, config, censored=state == "censored"
                )
                if state == "not_applicable":
                    value, metric_state = None, "not_applicable"
                comparison[metric] = value
                comparison[f"{metric}_state"] = metric_state
            alpha_rows.append(comparison)
        runtime[job.key] = {
            "job": job,
            "training_dir": training_dir,
            "readout_dir": readout_dir,
            "terminal_state": terminal,
            "receipt": receipt,
            "receipt_path": repo_path(evidence) if evidence else None,
            "readout_paths": selected_readout_paths(readout_dir, receipt),
        }
    return rows, alpha_rows, runtime


def numeric_values(
    rows: Iterable[Mapping[str, Any]], metric: str
) -> list[float]:
    values: list[float] = []
    for row in rows:
        if row.get(f"{metric}_state") != "measured":
            continue
        value = row.get(metric)
        if isinstance(value, bool):
            values.append(float(int(value)))
        elif isinstance(value, (int, float)) and math.isfinite(float(value)):
            values.append(float(value))
    return values


def aggregate_group(
    rows: Sequence[Mapping[str, Any]],
    config: Mapping[str, Any],
    dimension: str,
    value: str,
    arm: str,
    run: str,
) -> dict[str, Any]:
    metrics = config["measurement_contract"]["metric_fields"]
    subset = [
        row
        for row in rows
        if row["arm"] == arm
        and row["run"] == run
        and (dimension == "overall" or str(row.get(dimension)) == value)
    ]
    result: dict[str, Any] = {
        "group_dimension": dimension,
        "group_value": value,
        "arm": arm,
        "run": run,
        "expected_n": len(subset),
        "terminal_n": sum(row["job_terminal_state"] in TERMINAL_STATES for row in subset),
        "measured_primary_n": sum(row["primary_measurement_state"] == "measured" for row in subset),
        "censored_n": sum(row["primary_measurement_state"] == "censored" for row in subset),
        "missing_n": sum(row["primary_measurement_state"] == "missing" for row in subset),
    }
    for metric in metrics:
        values = numeric_values(subset, metric)
        result[f"{metric}_n"] = len(values)
        if values:
            result[f"{metric}_median"] = float(np.median(values))
            result[f"{metric}_q25"] = float(np.quantile(values, 0.25))
            result[f"{metric}_q75"] = float(np.quantile(values, 0.75))
        else:
            result[f"{metric}_median"] = None
            result[f"{metric}_q25"] = None
            result[f"{metric}_q75"] = None
        delta_metric = f"delta_vs_p0prime_{metric}"
        deltas = numeric_values(subset, delta_metric)
        result[f"{delta_metric}_n"] = len(deltas)
        if deltas:
            result[f"{delta_metric}_median"] = float(np.median(deltas))
            result[f"{delta_metric}_q25"] = float(np.quantile(deltas, 0.25))
            result[f"{delta_metric}_q75"] = float(np.quantile(deltas, 0.75))
        else:
            result[f"{delta_metric}_median"] = None
            result[f"{delta_metric}_q25"] = None
            result[f"{delta_metric}_q75"] = None
    margin = [
        bool(row["rms_within_p0prime_plus_0p05"])
        for row in subset
        if row["rms_within_p0prime_plus_0p05_state"] == "measured"
    ]
    result["rms_margin_measured_n"] = len(margin)
    result["rms_within_p0prime_plus_0p05_n"] = sum(margin)
    return result


def build_summary(
    rows: Sequence[Mapping[str, Any]], config: Mapping[str, Any]
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    arms_runs = sorted({(str(row["arm"]), str(row["run"])) for row in rows})
    dimensions: list[tuple[str, list[str]]] = [
        ("overall", ["all"]),
        ("texture_stratum", sorted({str(row["texture_stratum"]) for row in rows})),
        ("tier", sorted({str(row["tier"]) for row in rows})),
        ("cohort", sorted({str(row["cohort"]) for row in rows})),
        ("target_role", sorted({str(row["target_role"]) for row in rows})),
    ]
    for arm, run in arms_runs:
        for dimension, values in dimensions:
            for value in values:
                aggregate = aggregate_group(rows, config, dimension, value, arm, run)
                if aggregate["expected_n"] > 0:
                    result.append(aggregate)
    return result


def build_replicate_medians(
    rows: Sequence[Mapping[str, Any]], config: Mapping[str, Any]
) -> list[dict[str, Any]]:
    metrics = config["measurement_contract"]["metric_fields"]
    grouped: dict[tuple[str, str], list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[(str(row["building_id"]), str(row["arm"]))].append(row)
    result: list[dict[str, Any]] = []
    for (building_id, arm), members in sorted(grouped.items()):
        first = members[0]
        required_runs = 2 if arm == "Aprime" else 1
        row: dict[str, Any] = {
            "building_id": building_id,
            "arm": arm,
            "target_role": first["target_role"],
            "tier": first["tier"],
            "cohort": first["cohort"],
            "texture_stratum": first["texture_stratum"],
            "required_replicates_n": required_runs,
            "planned_replicates_n": len(members),
            "terminal_replicates_n": sum(
                member["job_terminal_state"] in TERMINAL_STATES for member in members
            ),
            "measured_replicates_n": sum(
                member["primary_measurement_state"] == "measured" for member in members
            ),
        }
        for metric in metrics:
            values = numeric_values(members, metric)
            state = (
                "measured"
                if len(values) == required_runs
                else (
                    "censored"
                    if any(member[f"{metric}_state"] == "censored" for member in members)
                    else "missing"
                )
            )
            row[f"{metric}_replicate_median"] = (
                float(np.median(values)) if state == "measured" else None
            )
            row[f"{metric}_replicate_range"] = (
                float(max(values) - min(values)) if state == "measured" else None
            )
            row[f"{metric}_replicate_state"] = state
        for metric in metrics:
            p0_values = {
                member.get(f"p0prime_{metric}")
                for member in members
                if member.get(f"p0prime_{metric}_state") == "measured"
            }
            replicate_state = row.get(f"{metric}_replicate_state")
            delta_field = f"{metric}_replicate_delta_vs_p0prime"
            delta_state_field = f"{delta_field}_state"
            if replicate_state == "measured" and len(p0_values) == 1:
                baseline = next(iter(p0_values))
                baseline_numeric = float(int(baseline)) if isinstance(baseline, bool) else float(baseline)
                row[f"p0prime_{metric}"] = baseline
                row[delta_field] = float(row[f"{metric}_replicate_median"]) - baseline_numeric
                row[delta_state_field] = "measured"
            else:
                row[f"p0prime_{metric}"] = None
                row[delta_field] = None
                row[delta_state_field] = (
                    "censored" if replicate_state == "censored" else "missing"
                )

        p0_values = {
            member.get("p0prime_roof_rms_m")
            for member in members
            if member.get("p0prime_roof_rms_m_state") == "measured"
        }
        rms_state = row.get("roof_rms_m_replicate_state")
        if rms_state == "measured" and len(p0_values) == 1:
            p0_rms = float(next(iter(p0_values)))
            row["p0prime_roof_rms_m"] = p0_rms
            row["roof_rms_median_delta_vs_p0prime"] = row[
                "roof_rms_m_replicate_delta_vs_p0prime"
            ]
            row["rms_median_within_p0prime_plus_0p05"] = float(
                row["roof_rms_m_replicate_median"]
            ) <= p0_rms + float(config["measurement_contract"]["rms_margin_m"])
            row["rms_median_margin_state"] = "measured"
        else:
            row["p0prime_roof_rms_m"] = None
            row["roof_rms_median_delta_vs_p0prime"] = None
            row["rms_median_within_p0prime_plus_0p05"] = None
            row["rms_median_margin_state"] = (
                "censored" if rms_state == "censored" else "missing"
            )
        result.append(row)
    return result


def build_gauges(
    scores: Sequence[Mapping[str, Any]],
    replicate: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    gauges: list[dict[str, Any]] = []

    def add(
        gauge: str,
        metric: str,
        value: Any,
        numerator: int | None,
        denominator: int,
        state: str,
        definition: str,
    ) -> None:
        gauges.append(
            {
                "gauge": gauge,
                "metric": metric,
                "value": value,
                "numerator": numerator,
                "denominator": denominator,
                "measurement_state": state,
                "definition": definition,
                "scientific_verdict": None,
            }
        )

    dim_scores = [row for row in scores if row["target_role"] == "dim_failure"]
    for run in ("r1", "r2"):
        subset = [
            row
            for row in dim_scores
            if row["arm"] == "Aprime"
            and row["run"] == run
            and row["assembly_lod2_success_state"] == "measured"
        ]
        numerator = sum(bool(row["assembly_lod2_success"]) for row in subset)
        add(
            "1_assembly",
            f"Aprime_{run}_LoD2_count",
            f"{numerator}/{len(subset)}",
            numerator,
            len(subset),
            "measured" if subset else "missing",
            "DIM-failure targets with measured primary TSDF score",
        )
        fallback_subset = [
            row
            for row in dim_scores
            if row["arm"] == "Aprime"
            and row["run"] == run
            and row["lod1_fallback_state"] == "measured"
        ]
        fallback_n = sum(bool(row["lod1_fallback"]) for row in fallback_subset)
        add(
            "1_assembly",
            f"Aprime_{run}_LoD1_fallback_count",
            f"{fallback_n}/{len(fallback_subset)}",
            fallback_n,
            len(fallback_subset),
            "measured" if fallback_subset else "missing",
            "DIM-failure targets with measured primary TSDF fallback field",
        )
    rep_dim = [
        row
        for row in replicate
        if row["arm"] == "Aprime"
        and row["target_role"] == "dim_failure"
        and row["assembly_lod2_success_replicate_state"] == "measured"
    ]
    both = sum(float(row["assembly_lod2_success_replicate_median"]) == 1.0 for row in rep_dim)
    add(
        "1_assembly",
        "Aprime_two_run_both_LoD2_count",
        f"{both}/{len(rep_dim)}",
        both,
        len(rep_dim),
        "measured" if rep_dim else "missing",
        "two measured replicates; binary replicate median equals 1.0 only when both are true",
    )
    rms_rep = [
        row
        for row in replicate
        if row["arm"] == "Aprime"
        and row["target_role"] == "dim_failure"
        and row["rms_median_margin_state"] == "measured"
    ]
    rms_n = sum(bool(row["rms_median_within_p0prime_plus_0p05"]) for row in rms_rep)
    add(
        "2_seed_retention",
        "two_run_RMS_median_at_or_below_P0prime_plus_0p05_count",
        f"{rms_n}/{len(rms_rep)}",
        rms_n,
        len(rms_rep),
        "measured" if rms_rep else "missing",
        "Aprime two-run roof RMS median <= building P0-prime roof RMS + 0.05 m",
    )
    observation_metrics = (
        "plane_f1",
        "roof_rms_m",
        "roof_hausdorff_m",
        "roof_completeness",
        "face_count_ratio",
    )
    for metric in observation_metrics:
        delta_field = f"{metric}_replicate_delta_vs_p0prime"
        values = [
            float(row[delta_field])
            for row in replicate
            if row["arm"] == "Aprime"
            and row["texture_stratum"] == "textured"
            and row.get(f"{delta_field}_state") == "measured"
        ]
        add(
            "3_textured_observation",
            f"textured_two_run_{metric}_delta_median",
            float(np.median(values)) if values else None,
            None,
            len(values),
            "measured" if values else "missing",
            f"median across textured-stratum buildings of Aprime two-run {metric} median minus P0-prime {metric}",
        )
    by_key = {(row["building_id"], row["arm"], row["run"]): row for row in scores}
    for metric in observation_metrics:
        b_pairs: list[float] = []
        for key, b_row in by_key.items():
            building_id, arm, run = key
            if arm != "B" or b_row[f"{metric}_state"] != "measured":
                continue
            a_row = by_key.get((building_id, "Aprime", run))
            if a_row and a_row[f"{metric}_state"] == "measured":
                b_pairs.append(float(b_row[metric]) - float(a_row[metric]))
        add(
            "4_supervision_ablation",
            f"B_minus_Aprime_{metric}_paired_median",
            float(np.median(b_pairs)) if b_pairs else None,
            None,
            len(b_pairs),
            "measured" if b_pairs else "missing",
            f"matched building/run primary TSDF {metric}(B) - {metric}(Aprime)",
        )
    return gauges


def preflight_rows(config: Mapping[str, Any]) -> list[dict[str, Any]]:
    sources = config["sources"]
    specifications = [
        ("five_pin", sources["five_pin"], "status", "PASSED"),
        ("T1", sources["T1"], "status", "PASSED"),
        ("T2", sources["T2"], "status", "COMPLETED"),
        ("T3", sources["T3"], "state", "COMPLETE"),
        ("T4", sources["T4"], "status", "COMPLETED"),
    ]
    rows: list[dict[str, Any]] = []
    for name, value, field, expected in specifications:
        path = repo_path(value)
        observed = None
        state = "missing"
        details: dict[str, Any] = {}
        if path.is_file():
            payload = load_json(path)
            observed = payload.get(field)
            state = "measured"
            if name == "T1":
                details["actual_prune_count_positive"] = nested_get(
                    payload, "requirements.actual_prune_count_positive"
                )
                details["post_transition_terms_positive"] = nested_get(
                    payload,
                    "requirements.post_transition_term_fields_strictly_positive",
                )
            elif name == "T2":
                details["git_lock_present"] = isinstance(payload.get("git_lock"), Mapping)
                checks = payload.get("checks") or {}
                details["true_checks_n"] = sum(value is True for value in checks.values())
                details["checks_n"] = len(checks)
                failure = repo_path(sources["T2_failure"])
                details["prior_failure_receipt_present"] = failure.is_file()
                details["prior_failure_receipt_path"] = repo_relative(failure)
                details["prior_failure_receipt_sha256"] = (
                    sha256_file(failure) if failure.is_file() else None
                )
            elif name == "T3":
                details["completed_count"] = nested_get(
                    payload, "population.completed_count"
                )
            elif name == "T4":
                bundle = load_t4_bundle(config)
                details["observation_rows_n"] = len(payload.get("observations") or [])
                details["source_hashes_verified"] = True
                details["snapshot_local_bundle_links"] = t4_bundle_links(config)
        rows.append(
            {
                "item": name,
                "measurement_state": state,
                "observed_status": observed,
                "contract_status": expected,
                "status_matches_contract": observed == expected if observed is not None else None,
                "evidence_path": (
                    t4_bundle_links(config)["receipt"]
                    if name == "T4" and path.is_file()
                    else repo_relative(path)
                ),
                "evidence_sha256": sha256_file(path) if path.is_file() else None,
                "details_json": details,
                "scientific_verdict": None,
            }
        )
    t5_path = repo_path(sources["t5_summary"])
    t5 = read_csv(t5_path) if t5_path.is_file() else []
    rows.append(
        {
            "item": "T5",
            "measurement_state": "measured" if t5 else "missing",
            "observed_status": (
                "COMPLETED"
                if len(t5) == 9 and all(row.get("status") == "PASSED" for row in t5)
                else ("PARTIAL" if t5 else None)
            ),
            "contract_status": "COMPLETED",
            "status_matches_contract": (
                len(t5) == 9 and all(row.get("status") == "PASSED" for row in t5)
            )
            if t5
            else None,
            "evidence_path": repo_relative(t5_path),
            "evidence_sha256": sha256_file(t5_path) if t5_path.is_file() else None,
            "details_json": {"rows_n": len(t5)},
            "scientific_verdict": None,
        }
    )
    return rows


def overlap_rows(targets: Sequence[Mapping[str, str]]) -> list[dict[str, Any]]:
    return [
        {
            "aprime_order": int(row["aprime_order"]),
            "building_id": row["building_id"],
            "gs4buildings_overlap_status": row.get("gs4buildings_overlap_status", ""),
            "gs4buildings_overlap_reason": row.get("gs4buildings_overlap_reason", ""),
            "selection_reason": row.get("selection_reason", ""),
        }
        for row in targets
    ]


def issue_rows(config: Mapping[str, Any]) -> list[dict[str, Any]]:
    path = repo_path(config["sources"]["issues"])
    if not path.is_file():
        return []
    result: list[dict[str, Any]] = []
    current = "preamble"
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if line.startswith("##"):
            current = line.lstrip("# ").strip()
            result.append(
                {
                    "line": number,
                    "section": current,
                    "record_type": "heading",
                    "text": current,
                    "source_path": repo_relative(path),
                }
            )
        elif line.strip().startswith("- "):
            stripped = line.strip()
            result.append(
                {
                    "line": number,
                    "section": current,
                    "record_type": (
                        "status_line"
                        if stripped.lower().startswith(("- status", "- 상태"))
                        else "bullet"
                    ),
                    "text": stripped,
                    "source_path": repo_relative(path),
                }
            )
    return result


def incomplete_rows(scores: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for row in scores:
        if row["primary_measurement_state"] == "measured":
            continue
        result.append(
            {
                "queue_order": row["queue_order"],
                "building_id": row["building_id"],
                "arm": row["arm"],
                "run": row["run"],
                "job_terminal_state": row["job_terminal_state"],
                "primary_measurement_state": row["primary_measurement_state"],
                "terminal_evidence": row["terminal_evidence"],
                "value_treatment": "excluded_from_numeric_aggregates",
            }
        )
    return result


def loss_share_rows(
    runtime: Mapping[str, Mapping[str, Any]]
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for evidence in runtime.values():
        job: Job = evidence["job"]
        path = evidence["training_dir"] / "audit/loss_grad_norms.csv"
        if not path.is_file():
            continue
        for source in read_csv(path):
            row: dict[str, Any] = {
                "queue_order": job.queue_order,
                "building_id": job.building_id,
                "arm": job.arm,
                "run": job.run,
                "source_path": repo_relative(path),
            }
            row.update(source)
            result.append(row)
    return result


def load_opacity_rows(
    job: Job, training_dir: Path
) -> tuple[list[dict[str, Any]], str, str]:
    path = training_dir / "audit/seed_lineage.csv"
    initialization_path = training_dir / "audit/seed_initialization.json"
    source = read_csv(path) if path.is_file() else []
    scopes = {row.get("scope", "") for row in source}
    selected_scope = (
        job.building_id if job.building_id in scopes else "all_seed_lineage"
    )
    selected = [row for row in source if row.get("scope") == selected_scope]
    result: list[dict[str, Any]] = []
    for row in sorted(selected, key=lambda value: int(value["iteration"])):
        result.append(
            {
                "queue_order": job.queue_order,
                "building_id": job.building_id,
                "arm": job.arm,
                "run": job.run,
                "iteration": int(row["iteration"]),
                "observation_phase": "post_dynamics",
                "scope": selected_scope,
                "gaussians_total": int(row["gaussians_total"]),
                "seed_lineage_count": int(row["seed_lineage_count"]),
                "opacity_median": float(row["opacity_median"]),
                "cum_prune_candidates": int(row["cum_prune_candidates"]),
                "cum_pruned": int(row["cum_pruned"]),
                "cum_prune_seed_protected": int(row["cum_prune_seed_protected"]),
                "seed_protect_active": str(row["seed_protect_active"]).lower() in TRUE_VALUES,
                "source_path": repo_relative(path),
            }
        )

    marker: Mapping[str, Any] | None = None
    if initialization_path.is_file():
        payload = load_json(initialization_path)
        if (
            payload.get("schema") != SEED_INITIALIZATION_SCHEMA
            or payload.get("status") != "OBSERVED"
            or payload.get("iteration") != 0
            or payload.get("observation_phase") != "initialization_pre_dynamics"
            or payload.get("intervention") is not False
        ):
            raise ReportContractError(
                f"seed initialization receipt drift: {repo_relative(initialization_path)}"
            )
        candidates: list[tuple[str | None, Mapping[str, Any], float]] = []
        opacity_keys = (
            "opacity_median",
            "initial_opacity_median",
            "initial_opacity",
            "seed_init_opacity",
        )

        def visit(value: Any, inherited_scope: str | None = None) -> None:
            if isinstance(value, Mapping):
                scope = str(value.get("scope")) if value.get("scope") else inherited_scope
                opacity = next(
                    (scalar(value.get(key)) for key in opacity_keys if scalar(value.get(key)) is not None),
                    None,
                )
                if isinstance(opacity, (int, float)):
                    candidates.append((scope, value, float(opacity)))
                for key, child in value.items():
                    child_scope = str(key) if str(key) in {job.building_id, "all_seed_lineage"} else scope
                    visit(child, child_scope)
            elif isinstance(value, list):
                for child in value:
                    visit(child, inherited_scope)

        visit(payload)
        for preferred_scope in (job.building_id, "all_seed_lineage", None):
            match = next(
                (candidate for candidate in candidates if candidate[0] == preferred_scope),
                None,
            )
            if match is not None:
                marker_scope, marker, opacity = match
                result.append(
                    {
                        "queue_order": job.queue_order,
                        "building_id": job.building_id,
                        "arm": job.arm,
                        "run": job.run,
                        "iteration": int(scalar(marker.get("iteration")) or 0),
                        "observation_phase": "initialization_pre_dynamics",
                        "scope": marker_scope or "all_seed_lineage",
                        "gaussians_total": scalar(marker.get("gaussians_total")),
                        "seed_lineage_count": scalar(marker.get("seed_lineage_count")),
                        "opacity_median": opacity,
                        "cum_prune_candidates": scalar(marker.get("cum_prune_candidates")),
                        "cum_pruned": scalar(marker.get("cum_pruned")),
                        "cum_prune_seed_protected": scalar(
                            marker.get("cum_prune_seed_protected")
                        ),
                        "seed_protect_active": scalar(
                            marker.get("seed_protect_active"), boolean=True
                        ),
                        "source_path": repo_relative(initialization_path),
                    }
                )
                break

    result.sort(
        key=lambda row: (
            int(row["iteration"]),
            0 if row["observation_phase"] == "initialization_pre_dynamics" else 1,
        )
    )
    has_dynamics = bool(selected)
    has_marker = marker is not None
    if has_dynamics and has_marker:
        return result, "measured", f"{selected_scope}; initialization marker present"
    if result:
        missing = "seed_initialization.json marker" if not has_marker else "seed_lineage.csv dynamics"
        return result, "partial", f"{selected_scope}; missing {missing}"
    return [], "missing", "seed_lineage.csv dynamics and initialization marker absent"


def save_figure(fig: plt.Figure, path: Path, dpi: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(
        path,
        dpi=dpi,
        bbox_inches="tight",
        facecolor="white",
        metadata={"Software": "JointBuildGS A-prime observational report"},
    )
    plt.close(fig)


def plot_opacity(
    rows: Sequence[Mapping[str, Any]],
    path: Path,
    config: Mapping[str, Any],
    title: str,
) -> None:
    palette = config["visual_contract"]["palette"]
    fig, ax = plt.subplots(figsize=(8.0, 4.5), constrained_layout=True)
    initial_phase = config["visual_contract"]["opacity_initial_observation_phase"]
    line_phase = config["visual_contract"]["opacity_line_observation_phase"]
    dynamics = [row for row in rows if row.get("observation_phase", line_phase) == line_phase]
    initial = [row for row in rows if row.get("observation_phase") == initial_phase]
    x = [int(row["iteration"]) for row in dynamics]
    y = [float(row["opacity_median"]) for row in dynamics]
    if dynamics:
        ax.plot(
            x,
            y,
            color=palette["blue"],
            marker="o",
            markersize=2.5,
            linewidth=1.7,
            label="post-dynamics trajectory",
        )
    if initial:
        ax.scatter(
            [int(row["iteration"]) for row in initial],
            [float(row["opacity_median"]) for row in initial],
            marker="D",
            s=38,
            facecolors="white",
            edgecolors=palette["charcoal"],
            linewidths=1.2,
            zorder=4,
            label="initialization pre-dynamics marker",
        )
    transition = int(config["visual_contract"]["transition_iteration"])
    ramp_end = int(config["visual_contract"]["surface_ramp_end_iteration"])
    ax.axvline(
        transition,
        color=palette["orange"],
        linestyle="--",
        linewidth=1.4,
        label="prior decay + surface regularization start (15k)",
    )
    ax.axvline(
        ramp_end,
        color=palette["gold"],
        linestyle=":",
        linewidth=1.4,
        label="surface regularization ramp end (20k)",
    )
    ax.set_title(title, color=palette["charcoal"], fontsize=11)
    ax.set_xlabel("optimizer iteration")
    ax.set_ylabel("median opacity")
    ax.set_ylim(bottom=0.0)
    ax.grid(True, color=palette["light_grey"], linewidth=0.7)
    ax.legend(loc="best", frameon=False, fontsize=8)
    save_figure(fig, path, int(config["visual_contract"]["panel_dpi"]))


def _placeholder(ax: plt.Axes, title: str, reason: str) -> None:
    ax.set_title(title, fontsize=9)
    ax.text(
        0.5,
        0.5,
        f"missing\n{reason}",
        transform=ax.transAxes,
        ha="center",
        va="center",
        fontsize=8,
        color="#7c8794",
    )
    ax.set_xticks([])
    ax.set_yticks([])
    for spine in ax.spines.values():
        spine.set_color("#e3e7eb")


def _scatter_points(
    ax: plt.Axes,
    xyz: np.ndarray,
    rgb: np.ndarray | None,
    title: str,
    config: Mapping[str, Any],
    *,
    section: bool = False,
) -> bool:
    if xyz.ndim != 2 or xyz.shape[1] != 3 or len(xyz) == 0:
        _placeholder(ax, title, "empty point set")
        return False
    limit = int(config["visual_contract"]["maximum_scatter_points"])
    if len(xyz) > limit:
        index = np.linspace(0, len(xyz) - 1, limit, dtype=np.int64)
        xyz = xyz[index]
        if rgb is not None and len(rgb) >= int(index[-1]) + 1:
            rgb = rgb[index]
    color: Any = config["visual_contract"]["palette"]["blue"]
    if rgb is not None and rgb.shape == (len(xyz), 3):
        color = np.clip(rgb.astype(np.float64) / 255.0, 0.0, 1.0)
    if section:
        centered = xyz[:, :2] - np.median(xyz[:, :2], axis=0)
        if len(centered) >= 2:
            _, _, vt = np.linalg.svd(centered, full_matrices=False)
            horizontal = centered @ vt[0]
        else:
            horizontal = centered[:, 0]
        ax.scatter(horizontal, xyz[:, 2], s=1.2, c=color, linewidths=0, rasterized=True)
        ax.set_xlabel("principal horizontal axis (m)", fontsize=7)
        ax.set_ylabel("Z (m)", fontsize=7)
    else:
        ax.scatter(xyz[:, 0], xyz[:, 1], s=1.2, c=color, linewidths=0, rasterized=True)
        ax.set_xlabel("E / local X (m)", fontsize=7)
        ax.set_ylabel("N / local Y (m)", fontsize=7)
    ax.set_title(title, fontsize=9)
    ax.set_aspect("equal", adjustable="datalim")
    ax.tick_params(labelsize=6)
    ax.grid(True, color=config["visual_contract"]["palette"]["light_grey"], linewidth=0.5)
    return True


def npz_xyz_rgb(path: Path, candidates: Sequence[str]) -> tuple[np.ndarray, np.ndarray | None]:
    with np.load(path, allow_pickle=False) as archive:
        key = next((name for name in candidates if name in archive.files), None)
        if key is None:
            raise ReportContractError(f"NPZ has no coordinate field: {repo_relative(path)}")
        xyz = np.asarray(archive[key], dtype=np.float64)
        rgb = np.asarray(archive["rgb"]) if "rgb" in archive.files else None
    return xyz, rgb


def ply_vertices(path: Path) -> np.ndarray:
    try:
        import open3d as o3d

        mesh = o3d.io.read_triangle_mesh(str(path), enable_post_processing=False)
        vertices = np.asarray(mesh.vertices, dtype=np.float64)
        if len(vertices):
            return vertices
        cloud = o3d.io.read_point_cloud(str(path))
        return np.asarray(cloud.points, dtype=np.float64)
    except Exception as exc:  # visual fallback only; the reason is surfaced in the panel
        raise ReportContractError(f"cannot read PLY {repo_relative(path)}: {exc}") from exc


def cityjson_rings(path: Path) -> list[np.ndarray]:
    payload = load_json(path)
    vertices = np.asarray(payload.get("vertices") or [], dtype=np.float64)
    transform = payload.get("transform") or {}
    if len(vertices) and transform:
        vertices = vertices * np.asarray(transform.get("scale", [1, 1, 1]), dtype=np.float64)
        vertices = vertices + np.asarray(transform.get("translate", [0, 0, 0]), dtype=np.float64)
    rings: list[np.ndarray] = []

    def visit(value: Any) -> None:
        if isinstance(value, list) and value and all(isinstance(item, int) for item in value):
            indices = [int(item) for item in value if 0 <= int(item) < len(vertices)]
            if len(indices) >= 3:
                rings.append(vertices[indices])
            return
        if isinstance(value, list):
            for child in value:
                visit(child)

    for city_object in (payload.get("CityObjects") or {}).values():
        for geometry in city_object.get("geometry") or []:
            visit(geometry.get("boundaries") or [])
    return rings


def _gml_element_rings(element: ET.Element) -> list[np.ndarray]:
    rings: list[np.ndarray] = []
    for child in element.iter():
        if not child.tag.endswith("posList") or not child.text:
            continue
        try:
            values = np.asarray([float(value) for value in child.text.split()])
        except ValueError:
            continue
        dimension = int(child.attrib.get("srsDimension", 3))
        if dimension not in {2, 3} or len(values) % dimension:
            dimension = 3 if len(values) % 3 == 0 else 2
        points = values.reshape(-1, dimension)
        if dimension == 2:
            points = np.column_stack([points, np.zeros(len(points))])
        if len(points) >= 3:
            rings.append(points[:, :3])
    return rings


def gml_rings_by_building(
    paths: Sequence[Path], building_ids: Sequence[str]
) -> dict[str, list[np.ndarray]]:
    result = {building_id: [] for building_id in building_ids}
    remaining = set(building_ids)
    for path in paths:
        try:
            iterator = ET.iterparse(path, events=("end",))
            for _, element in iterator:
                local_name = element.tag.rsplit("}", 1)[-1]
                if local_name == "cityObjectMember":
                    element.clear()
                    continue
                if local_name != "Building":
                    continue
                identifiers = {str(value) for value in element.attrib.values()}
                building_id = next(
                    (candidate for candidate in remaining if candidate in identifiers),
                    None,
                )
                if building_id is not None:
                    result[building_id] = _gml_element_rings(element)
                    if result[building_id]:
                        remaining.remove(building_id)
                element.clear()
        except (OSError, ET.ParseError):
            continue
        if not remaining:
            break
    return result


def gml_rings(paths: Sequence[Path], building_id: str) -> list[np.ndarray]:
    return gml_rings_by_building(paths, [building_id])[building_id]


def plot_rings(ax: plt.Axes, rings: Sequence[np.ndarray], title: str, color: str) -> bool:
    if not rings:
        _placeholder(ax, title, "geometry not resolved")
        return False
    for ring in rings:
        closed = np.vstack([ring, ring[0]]) if not np.array_equal(ring[0], ring[-1]) else ring
        ax.plot(closed[:, 0], closed[:, 1], color=color, linewidth=0.8)
    ax.set_title(title, fontsize=9)
    ax.set_aspect("equal", adjustable="datalim")
    ax.tick_params(labelsize=6)
    ax.grid(True, color="#e3e7eb", linewidth=0.5)
    return True


def input_crop(building_root: Path) -> tuple[Image.Image | None, str]:
    index_path = building_root / "supervision_index.csv"
    if not index_path.is_file():
        return None, "supervision index absent"
    rows = read_csv(index_path)
    rows = sorted(rows, key=lambda row: int(row.get("mask_pixels_n", 0)), reverse=True)
    for row in rows:
        image = repo_path(row["class6_npz_path"]).parent.parent.parent / "images" / row["image_name"]
        if not image.is_file():
            image = building_root / "images" / row["image_name"]
        prior = repo_path(row["class6_npz_path"])
        if not image.is_file() or not prior.is_file():
            continue
        with np.load(prior, allow_pickle=False) as archive:
            field = "valid_M_j" if "valid_M_j" in archive.files else "valid"
            if field not in archive.files:
                continue
            mask = np.asarray(archive[field]).astype(bool)
        y, x = np.nonzero(mask)
        if not len(x):
            continue
        picture = Image.open(image).convert("RGB")
        x0, x1 = int(x.min()), int(x.max()) + 1
        y0, y1 = int(y.min()), int(y.max()) + 1
        pad_x = max(8, int((x1 - x0) * 0.2))
        pad_y = max(8, int((y1 - y0) * 0.2))
        crop = picture.crop(
            (
                max(0, x0 - pad_x),
                max(0, y0 - pad_y),
                min(picture.width, x1 + pad_x),
                min(picture.height, y1 + pad_y),
            )
        )
        return crop, row["image_name"]
    return None, "no nonempty M_j image pair"


def generate_visuals(
    scores: list[dict[str, Any]],
    runtime: Mapping[str, Mapping[str, Any]],
    snapshot: Path,
    config: Mapping[str, Any],
) -> list[dict[str, Any]]:
    outputs = config["outputs"]
    palette = config["visual_contract"]["palette"]
    score_by_key = {
        f"{row['building_id']}/arm_{row['arm']}/{row['run']}": row for row in scores
    }
    all_opacity: list[dict[str, Any]] = []
    reference_paths = [
        repo_path(record["path"])
        for record in config["locked_inputs"]["reference_gml"]
    ]
    reference_cache = gml_rings_by_building(
        reference_paths,
        sorted(
            {
                evidence["job"].building_id
                for evidence in runtime.values()
            }
        ),
    )
    for evidence in runtime.values():
        job: Job = evidence["job"]
        score = score_by_key[job.key]
        opacity, opacity_state, opacity_scope = load_opacity_rows(
            job, evidence["training_dir"]
        )
        all_opacity.extend(opacity)
        opacity_name = f"{job.slug}.png"
        opacity_rel = f"{outputs['opacity_dir']}/{opacity_name}"
        opacity_path = snapshot / opacity_rel
        if opacity:
            plot_opacity(
                opacity,
                opacity_path,
                config,
                f"{job.building_id} | {job.arm} {job.run} | roof seed-lineage opacity",
            )
            score["opacity_state"] = opacity_state
            score["opacity_path"] = opacity_rel
        else:
            score["opacity_state"] = opacity_state
            score["opacity_path"] = ""

        fig, axes = plt.subplots(
            3,
            3,
            figsize=tuple(config["visual_contract"]["panel_inches"]),
            constrained_layout=True,
        )
        fig.suptitle(
            f"{job.building_id} | arm {job.arm} | {job.run} | observational review panel",
            fontsize=13,
            color=palette["charcoal"],
        )
        present: dict[str, bool] = {}
        building_root = preprocess_building_root(config, job.building_id)
        crop, crop_label = input_crop(building_root)
        if crop is not None:
            axes[0, 0].imshow(crop)
            axes[0, 0].set_title(f"Input crop | max M_j view\n{crop_label}", fontsize=9)
            axes[0, 0].axis("off")
            present["input_crop"] = True
        else:
            _placeholder(axes[0, 0], "Input crop | max M_j view", crop_label)
            present["input_crop"] = False

        seed_path = building_root / "seed_class6_filtered_canonical.npz"
        try:
            seed_xyz, seed_rgb = npz_xyz_rgb(
                seed_path,
                ("xyz_base_epsg25832_orthometric", "xyz"),
            )
            present["seed_top"] = _scatter_points(
                axes[0, 1], seed_xyz, seed_rgb, "A-prime class-6 seed | top", config
            )
        except Exception as exc:
            _placeholder(axes[0, 1], "A-prime class-6 seed | top", str(exc))
            present["seed_top"] = False

        paths = evidence["readout_paths"]
        mesh_path = paths.get("mesh")
        try:
            if mesh_path is None or not mesh_path.is_file():
                raise ReportContractError("filtered TSDF mesh absent")
            mesh_xyz = ply_vertices(mesh_path)
            present["mesh_top"] = _scatter_points(
                axes[0, 2], mesh_xyz, None, "TSDF filtered mesh vertices | top", config
            )
        except Exception as exc:
            _placeholder(axes[0, 2], "TSDF filtered mesh vertices | top", str(exc))
            present["mesh_top"] = False

        tsdf_path = paths.get("tsdf_npz")
        tsdf_xyz: np.ndarray | None = None
        tsdf_rgb: np.ndarray | None = None
        try:
            if tsdf_path is None or not tsdf_path.is_file():
                raise ReportContractError("TSDF surface sample NPZ absent")
            tsdf_xyz, tsdf_rgb = npz_xyz_rgb(
                tsdf_path,
                ("xyz_epsg25832_orthometric", "xyz_canonical_ellipsoidal", "xyz"),
            )
            present["points_top"] = _scatter_points(
                axes[1, 0], tsdf_xyz, tsdf_rgb, "TSDF surface samples | top", config
            )
            present["points_section"] = _scatter_points(
                axes[1, 1],
                tsdf_xyz,
                tsdf_rgb,
                "TSDF surface samples | principal section",
                config,
                section=True,
            )
        except Exception as exc:
            _placeholder(axes[1, 0], "TSDF surface samples | top", str(exc))
            _placeholder(
                axes[1, 1], "TSDF surface samples | principal section", str(exc)
            )
            present["points_top"] = False
            present["points_section"] = False

        cityjson_path = paths.get("cityjson")
        try:
            if cityjson_path is None or not cityjson_path.is_file():
                raise ReportContractError("assembled CityJSON absent")
            present["assembled"] = plot_rings(
                axes[1, 2],
                cityjson_rings(cityjson_path),
                "Roofer CityJSON | top",
                palette["blue"],
            )
        except Exception as exc:
            _placeholder(axes[1, 2], "Roofer CityJSON | top", str(exc))
            present["assembled"] = False

        present["reference"] = plot_rings(
            axes[2, 0],
            reference_cache[job.building_id],
            "Evaluation-only reference GML | top",
            palette["charcoal"],
        )

        if opacity:
            initial_phase = config["visual_contract"][
                "opacity_initial_observation_phase"
            ]
            line_phase = config["visual_contract"]["opacity_line_observation_phase"]
            dynamics = [
                row
                for row in opacity
                if row.get("observation_phase", line_phase) == line_phase
            ]
            initial = [
                row
                for row in opacity
                if row.get("observation_phase") == initial_phase
            ]
            if dynamics:
                axes[2, 1].plot(
                    [int(row["iteration"]) for row in dynamics],
                    [float(row["opacity_median"]) for row in dynamics],
                    color=palette["blue"],
                    linewidth=1.5,
                )
            if initial:
                axes[2, 1].scatter(
                    [int(row["iteration"]) for row in initial],
                    [float(row["opacity_median"]) for row in initial],
                    marker="D",
                    s=28,
                    facecolors="white",
                    edgecolors=palette["charcoal"],
                    linewidths=1.0,
                    zorder=4,
                )
            axes[2, 1].axvline(
                int(config["visual_contract"]["transition_iteration"]),
                color=palette["orange"],
                linestyle="--",
                linewidth=1.1,
            )
            axes[2, 1].axvline(
                int(config["visual_contract"]["surface_ramp_end_iteration"]),
                color=palette["gold"],
                linestyle=":",
                linewidth=1.1,
            )
            axes[2, 1].set_ylim(bottom=0.0)
            axes[2, 1].set_title("Roof seed-lineage median opacity", fontsize=9)
            axes[2, 1].set_xlabel("optimizer iteration", fontsize=7)
            axes[2, 1].set_ylabel("median opacity", fontsize=7)
            axes[2, 1].tick_params(labelsize=6)
            axes[2, 1].grid(True, color=palette["light_grey"], linewidth=0.5)
            present["opacity"] = True
        else:
            _placeholder(
                axes[2, 1], "Roof seed-lineage median opacity", opacity_scope
            )
            present["opacity"] = False

        axes[2, 2].axis("off")
        metadata = [
            f"terminal: {score['job_terminal_state']}",
            f"primary score: {score['primary_measurement_state']}",
            f"tier / texture: {score['tier']} / {score['texture_stratum']}",
            f"seed filtered: {csv_value(score.get('seed_filter_after_n'))}",
            f"M_j pixels: {csv_value(score.get('mask_pixels_total'))}",
            "reference: evaluation only",
            "panel role: observation, no verdict",
        ]
        axes[2, 2].text(
            0.02,
            0.96,
            "\n".join(metadata),
            transform=axes[2, 2].transAxes,
            va="top",
            ha="left",
            fontsize=9,
            color=palette["charcoal"],
            linespacing=1.5,
        )
        panel_rel = f"{outputs['panels_dir']}/{job.slug}.png"
        panel_path = snapshot / panel_rel
        save_figure(fig, panel_path, int(config["visual_contract"]["panel_dpi"]))
        score["panel_state"] = "measured" if all(present.values()) else "partial"
        score["panel_path"] = panel_rel
        score["panel_components_json"] = present
    return all_opacity


def source_inventory(
    jobs: Sequence[Job],
    config: Mapping[str, Any],
    *,
    queue_evidence: Mapping[str, Any] | None = None,
    t4_bundle: Mapping[str, Any] | None = None,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    rows.append(file_record(DEFAULT_CONFIG, "report_config", required=True))
    for path_value in config.get("implementation_files", []):
        rows.append(file_record(repo_path(path_value), "report_implementation"))
    for name, record in config["locked_inputs"].items():
        records = record if isinstance(record, list) else [record]
        for index, item in enumerate(records):
            if not isinstance(item, Mapping) or not item.get("path"):
                continue
            rows.append(
                file_record(
                    repo_path(item["path"]),
                    f"locked_{name}_{index}" if len(records) > 1 else f"locked_{name}",
                    expected_sha256=item.get("sha256"),
                )
            )
    for config_name in (
        "training_config",
        "p0prime_config",
        "preprocess_config",
        "readout_config",
        "queue_config",
    ):
        record = config["locked_inputs"][config_name]
        method_config_path = repo_path(record["path"])
        if not method_config_path.is_file():
            continue
        method_config = load_json(method_config_path)
        for field in ("method_files", "implementation_files"):
            for path_value in method_config.get(field, []):
                rows.append(
                    file_record(
                        repo_path(path_value),
                        f"{config_name}_{field}",
                    )
                )
    for name in (
        "preprocess_stable_manifest",
        "t5_summary",
        "t5_mask_inventory",
        "five_pin",
        "T1",
        "T2",
        "T2_failure",
        "T3",
        "T3_scores",
        "T4",
        "issues",
    ):
        rows.append(file_record(repo_path(config["sources"][name]), name))
    t4 = t4_bundle if t4_bundle is not None else load_t4_bundle(config)
    for role in ("receipt", "csv", "figure"):
        rows.append(
            file_record(
                t4["paths"][role],
                f"T4_bundle_{role}",
                expected_sha256=t4["files"][role]["sha256"],
                required=True,
            )
        )
    queue = (
        queue_evidence
        if queue_evidence is not None
        else load_queue_evidence(jobs, config)
    )
    rows.extend(dict(record) for record in queue["source_records"])
    for job in jobs:
        training_dir, readout_dir = job_dirs(job, config)
        rows.append(
            file_record(
                preprocess_building_root(config, job.building_id)
                / "preprocess_manifest.json",
                f"preprocess_{job.building_id}",
            )
        )
        rows.append(file_record(training_dir / "started.json", f"training_started_{job.key}"))
        rows.append(file_record(training_dir / "completed.json", f"training_{job.key}"))
        if (training_dir / "failed.json").is_file():
            rows.append(
                file_record(training_dir / "failed.json", f"training_failed_{job.key}")
            )
        rows.append(
            file_record(
                training_dir / "audit/loss_grad_norms.csv",
                f"loss_share_{job.key}",
            )
        )
        rows.append(
            file_record(
                training_dir / "audit/seed_lineage.csv", f"opacity_{job.key}"
            )
        )
        rows.append(
            file_record(
                training_dir / "audit/seed_initialization.json",
                f"opacity_initialization_{job.key}",
            )
        )
        rows.append(file_record(readout_dir / "complete.json", f"readout_{job.key}"))
        for name in ("started.json", "skipped.json", "failed.json", "terminal_failure.json"):
            if (readout_dir / name).is_file():
                rows.append(
                    file_record(readout_dir / name, f"readout_terminal_{job.key}_{name}")
                )
        attempt_patterns = {
            "attempt_receipt": "attempts/attempt_*/attempt.json",
            "attempt_failure": "attempts/attempt_*/failure.json",
            "tsdf_receipt": "attempts/attempt_*/tsdf/tsdf_receipt.json",
            "tsdf_samples": "attempts/attempt_*/tsdf/tsdf_surface_samples.npz",
            "tsdf_mesh": "attempts/attempt_*/tsdf/tsdf_mesh_filtered_epsg25832_orthometric.ply",
            "primary_score": "attempts/attempt_*/primary/score.json",
            "primary_cityjson": "attempts/attempt_*/primary/engine/by_building/*/cityjson/*.city.json",
            "legacy_alpha_score": "attempts/attempt_*/legacy_alpha/score.json",
            "legacy_alpha_classification": "attempts/attempt_*/legacy_alpha/classification_receipt.json",
            "legacy_alpha_points": "attempts/attempt_*/legacy_alpha/pointcloud/readout.npz",
            "legacy_alpha_cityjson": "attempts/attempt_*/legacy_alpha/engine/by_building/*/cityjson/*.city.json",
        }
        for role, pattern in attempt_patterns.items():
            for path in sorted(readout_dir.glob(pattern)):
                rows.append(file_record(path, f"{role}_{job.key}"))
    unique: dict[tuple[str, str], dict[str, Any]] = {}
    for row in rows:
        unique[(row["role"], row["path"])] = row
    return sorted(unique.values(), key=lambda row: (row["role"], row["path"]))


def source_fingerprint(
    rows: Sequence[Mapping[str, Any]],
    config: Mapping[str, Any],
    *,
    provenance: Mapping[str, Any] | None = None,
) -> str:
    payload = [
        {
            "role": row["role"],
            "path": row["path"],
            "state": row["state"],
            "bytes": row.get("bytes"),
            "sha256": row.get("sha256"),
        }
        for row in rows
    ]
    return canonical_sha(
        {
            "schema": "jointbuildgs.fusion_w1_aprime.report.inputs.v2",
            "run_id": config["run_id"],
            "report_provenance": dict(provenance) if provenance is not None else None,
            "sources": payload,
        }
    )


def markdown_table(headers: Sequence[str], rows: Sequence[Sequence[Any]]) -> str:
    def cell(value: Any) -> str:
        text = str(csv_value(value))
        return text.replace("|", "\\|").replace("\n", " ")

    lines = [
        "| " + " | ".join(cell(header) for header in headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    lines.extend("| " + " | ".join(cell(value) for value in row) + " |" for row in rows)
    return "\n".join(lines)


def state_value(row: Mapping[str, Any], metric: str) -> str:
    state = row.get(f"{metric}_state", "missing")
    return str(csv_value(row.get(metric))) if state == "measured" else f"[{state}]"


def build_one_page_markdown(
    gauges: Sequence[Mapping[str, Any]],
    scores: Sequence[Mapping[str, Any]],
    preflight: Sequence[Mapping[str, Any]],
    overlap: Sequence[Mapping[str, Any]],
    snapshot_id: str,
    config: Mapping[str, Any],
) -> str:
    t4_links = t4_bundle_links(config)
    terminal = sum(row["job_terminal_state"] in TERMINAL_STATES for row in scores)
    measured = sum(row["primary_measurement_state"] == "measured" for row in scores)
    censored = sum(row["primary_measurement_state"] == "censored" for row in scores)
    overlap_counts = Counter(row["gs4buildings_overlap_status"] for row in overlap)
    alpha_states = Counter(row["alpha_comparison_state"] for row in scores)
    alpha_outcomes = Counter(
        row["alpha_comparison_outcome"]
        for row in scores
        if row.get("alpha_comparison_outcome")
    )
    by_key = {
        (row["building_id"], row["arm"], row["run"]): row for row in scores
    }
    building_order = [
        row["building_id"]
        for row in sorted(scores, key=lambda value: int(value["queue_order"]))
        if row["arm"] == "Aprime" and row["run"] == "r1"
    ]
    building_rows: list[list[Any]] = []
    for building_id in building_order:
        r1 = by_key[(building_id, "Aprime", "r1")]
        r2 = by_key[(building_id, "Aprime", "r2")]
        building_rows.append(
            [
                building_id,
                f"{r1['tier']}/{r1['texture_stratum']}",
                state_value(r1, "p0prime_roof_rms_m"),
                f"{state_value(r1, 'assembly_lod2_success')} / {state_value(r1, 'roof_rms_m')}",
                f"{state_value(r2, 'assembly_lod2_success')} / {state_value(r2, 'roof_rms_m')}",
                r1["gs4buildings_overlap_status"],
            ]
        )
    lines = [
        "# 생성축 1파 arm A′ 측정 요약",
        "",
        "> GS4Buildings 레시피 이식판의 측정·산출 요약이다. 과학적 판정과 해석은 포함하지 않는다.",
        "",
        f"- Snapshot: `{snapshot_id}`",
        f"- 예정 job: {len(scores)}; terminal receipt: {terminal}; primary TSDF score measured: {measured}; censored: {censored}",
        f"- 결측 및 censored 값은 모든 수치 집계에서 제외한다. censored는 실측치로 세지 않는다.",
        f"- legacy-alpha 비교 상태: `{dict(sorted(alpha_states.items()))}`; 비조립 outcome: `{dict(sorted(alpha_outcomes.items()))}`",
        f"- P0′ 차이: `{config['measurement_contract']['p0prime_delta_definition']}`",
        "",
        "## 사전등록 눈금 수치",
        "",
        markdown_table(
            ["눈금", "측정량", "값", "분모", "상태"],
            [
                [
                    row["gauge"],
                    row["metric"],
                    row["value"],
                    row["denominator"],
                    row["measurement_state"],
                ]
                for row in gauges
            ],
        ),
        "",
        "## 동별 A′ 기록",
        "",
        markdown_table(
            ["동", "tier/texture", "P0′ RMS m", "r1 LoD2/RMS", "r2 LoD2/RMS", "GS4B 식별"],
            building_rows,
        ),
        "",
        "## T1–T5 영수증",
        "",
        markdown_table(
            ["항목", "관측 상태", "계약 상태", "일치", "측정 상태"],
            [
                [
                    row["item"],
                    row["observed_status"],
                    row["contract_status"],
                    row["status_matches_contract"],
                    row["measurement_state"],
                ]
                for row in preflight
            ],
        ),
        "",
        "T4 snapshot-local 증거: "
        f"[receipt]({t4_links['receipt']}) · [CSV]({t4_links['csv']}) · "
        f"[figure]({t4_links['figure']}) · [bundle manifest]({t4_links['manifest']})",
        "",
        "## GS4Buildings 겹침 식별 기록",
        "",
        markdown_table(
            ["식별 상태", "동 수"], sorted(overlap_counts.items())
        ),
        "",
        "상세 동별 수치·패널·issues·미완 목록은 [REPORT.md](REPORT.md)에 기록한다.",
        "",
    ]
    return "\n".join(lines)


def build_report_markdown(
    one_page: str,
    scores: Sequence[Mapping[str, Any]],
    summary: Sequence[Mapping[str, Any]],
    preflight: Sequence[Mapping[str, Any]],
    overlap: Sequence[Mapping[str, Any]],
    issues: Sequence[Mapping[str, Any]],
    incomplete: Sequence[Mapping[str, Any]],
    config: Mapping[str, Any],
) -> str:
    lines = [one_page.rstrip(), "", "## 측정 범위·정의", ""]
    contract = config["measurement_contract"]
    lines.extend(
        [
            f"- Primary readout: `{contract['primary_readout_role']}`",
            f"- 비교 기록: `{contract['comparison_readout_role']}`; 사전등록 눈금 집계에는 미사용",
            f"- 텍스처 층: `{contract['textureless_rule']}`; 나머지는 `{contract['textured_label']}`",
            f"- RMS 눈금 기록: `A′ roof_rms_m <= P0′ roof_rms_m + {contract['rms_margin_m']} m`",
            f"- 참조 단서: {contract['reference_caveat']}",
            "- `measured`, `missing`, `censored`, `not_applicable` 상태를 값과 분리해 저장한다.",
            "",
            "## 동×arm×run 수치",
            "",
            markdown_table(
                [
                    "동",
                    "arm/run",
                    "층",
                    "texture",
                    "terminal",
                    "LoD2",
                    "RMS m",
                    "ΔRMS vs P0′ m",
                    "plane F1",
                    "completeness",
                    "face ratio",
                    "panel",
                    "opacity",
                ],
                [
                    [
                        row["building_id"],
                        f"{row['arm']}/{row['run']}",
                        row["tier"],
                        row["texture_stratum"],
                        row["job_terminal_state"],
                        state_value(row, "assembly_lod2_success"),
                        state_value(row, "roof_rms_m"),
                        state_value(row, "delta_vs_p0prime_roof_rms_m"),
                        state_value(row, "plane_f1"),
                        state_value(row, "roof_completeness"),
                        state_value(row, "face_count_ratio"),
                        f"[{row['panel_state']}]({row['panel_path']})"
                        if row.get("panel_path")
                        else "[missing]",
                        f"[{row['opacity_state']}]({row['opacity_path']})"
                        if row.get("opacity_path")
                        else f"[{row['opacity_state']}]",
                    ]
                    for row in scores
                ],
            ),
            "",
            "정확한 전체 지표와 각 지표 상태는 [w1_scores_building.csv](w1_scores_building.csv)에 저장한다.",
            "",
            "## 층화 집계",
            "",
            markdown_table(
                [
                    "분류",
                    "값",
                    "arm/run",
                    "expected",
                    "measured",
                    "censored",
                    "LoD2 median (n)",
                    "RMS median m (n)",
                    "plane F1 median (n)",
                ],
                [
                    [
                        row["group_dimension"],
                        row["group_value"],
                        f"{row['arm']}/{row['run']}",
                        row["expected_n"],
                        row["measured_primary_n"],
                        row["censored_n"],
                        f"{csv_value(row['assembly_lod2_success_median'])} ({row['assembly_lod2_success_n']})",
                        f"{csv_value(row['roof_rms_m_median'])} ({row['roof_rms_m_n']})",
                        f"{csv_value(row['plane_f1_median'])} ({row['plane_f1_n']})",
                    ]
                    for row in summary
                ],
            ),
            "",
            "집계의 Q25/Q75·완전율·면수비·val3dity 분모는 [w1_summary.csv](w1_summary.csv)에 저장한다.",
            "",
            "## T1–T5 세부 기록",
            "",
            markdown_table(
                ["항목", "관측", "계약", "상태", "세부", "영수증"],
                [
                    [
                        row["item"],
                        row["observed_status"],
                        row["contract_status"],
                        row["measurement_state"],
                        row["details_json"],
                        row["evidence_path"],
                    ]
                    for row in preflight
                ],
            ),
            "",
            "## GS4Buildings 겹침 식별 결과",
            "",
            markdown_table(
                ["순번", "동", "식별 상태", "사유"],
                [
                    [
                        row["aprime_order"],
                        row["building_id"],
                        row["gs4buildings_overlap_status"],
                        row["gs4buildings_overlap_reason"],
                    ]
                    for row in overlap
                ],
            ),
            "",
            "이 기록은 공개 산출물에서 식별 가능한 교차표의 유무만 나타내며, unknown을 0개 겹침으로 바꾸지 않는다.",
            "",
            "## Legacy alpha 비교 산출 상태",
            "",
            "Primary TSDF 완료와 비교용 alpha 조립 상태는 분리한다. `NOT_ASSEMBLED`·`UNCONSTRUCTABLE`은 `not_applicable`로 기록하고 수치 집계에서 제외한다.",
            "",
            markdown_table(
                [
                    "순번",
                    "동",
                    "arm/run",
                    "상태",
                    "outcome",
                    "assembly",
                    "measurement",
                    "reason_code",
                    "진단 개수",
                ],
                [
                    [
                        row["queue_order"],
                        row["building_id"],
                        f"{row['arm']}/{row['run']}",
                        row["alpha_comparison_state"],
                        row["alpha_comparison_outcome"],
                        row["alpha_comparison_assembly_status"],
                        row["alpha_comparison_measurement_status"],
                        row["alpha_comparison_reason_code"],
                        row["alpha_comparison_counts_json"],
                    ]
                    for row in scores
                ],
            ),
            "",
            "## Issues 기록",
            "",
        ]
    )
    if issues:
        lines.extend(
            f"- L{row['line']} `{row['section']}`: {row['text']}" for row in issues
        )
    else:
        lines.append("- [missing] issues.md에서 제목/상태 행을 읽지 못함")
    lines.extend(["", "## 미완 산출 목록", ""])
    if incomplete:
        lines.append(
            markdown_table(
                ["순번", "동", "arm/run", "terminal", "측정 상태", "증거"],
                [
                    [
                        row["queue_order"],
                        row["building_id"],
                        f"{row['arm']}/{row['run']}",
                        row["job_terminal_state"],
                        row["primary_measurement_state"],
                        row["terminal_evidence"],
                    ]
                    for row in incomplete
                ],
            )
        )
    else:
        lines.append("- 미완 primary TSDF score 행: 0")
    lines.extend(
        [
            "",
            "## 파일 안내",
            "",
            "- 주 수치: [w1_scores_building.csv](w1_scores_building.csv)",
            "- P0′: [w1_seed_p0prime_scores.csv](w1_seed_p0prime_scores.csv)",
            "- alpha 비교: [w1_alpha_comparison.csv](w1_alpha_comparison.csv)",
            "- opacity 전 동 궤적: [w1_opacity_trajectories.csv](w1_opacity_trajectories.csv)",
            "- queue stage receipt 정규화: [w1_queue_stage_records.csv](w1_queue_stage_records.csv)",
            "- queue training archive: [w1_queue_archives.csv](w1_queue_archives.csv)",
            "- queue recovery evidence: [w1_queue_recoveries.csv](w1_queue_recoveries.csv)",
            f"- T4 snapshot-local bundle: [receipt]({t4_bundle_links(config)['receipt']}) · [CSV]({t4_bundle_links(config)['csv']}) · [figure]({t4_bundle_links(config)['figure']})",
            "- 정성 패널 폴더: [w1_panels](w1_panels)",
            "- source/artifact 해시: [w1_manifest.json](w1_manifest.json)",
            "",
        ]
    )
    return "\n".join(lines)


def assert_observational_language(text: str) -> None:
    forbidden = (
        "판정: 성공",
        "판정: 실패",
        "결론:",
        "따라서 성립",
        "따라서 실패",
        "채택한다",
        "기각한다",
        "go/no-go",
    )
    matched = [phrase for phrase in forbidden if phrase.lower() in text.lower()]
    if matched:
        raise ReportContractError(f"verdict-like report phrase detected: {matched}")


def p0prime_output_rows(
    targets: Sequence[Mapping[str, str]],
    p0prime: Mapping[str, Mapping[str, Any]],
    config: Mapping[str, Any],
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for target in targets:
        building_id = target["building_id"]
        source = p0prime.get(building_id)
        row: dict[str, Any] = {
            "aprime_order": int(target["aprime_order"]),
            "building_id": building_id,
            "target_role": target["target_role"],
            "tier": target["tier"],
            "texture_stratum": texture_stratum(target, config),
            "baseline_role": "P0prime_Aprime_seed_only_learning_zero",
            "measurement_state": "measured" if source else "missing",
        }
        for metric in config["measurement_contract"]["metric_fields"]:
            value, state = metric_value(source, metric, config)
            row[metric] = value
            row[f"{metric}_state"] = state
        result.append(row)
    return result


def seed_stat_rows(
    targets: Sequence[Mapping[str, str]],
    t5: Mapping[str, Mapping[str, str]],
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for target in targets:
        building_id = target["building_id"]
        source = t5.get(building_id)
        if source:
            row: dict[str, Any] = dict(source)
            row["measurement_state"] = "measured"
        else:
            row = {
                "aprime_order": int(target["aprime_order"]),
                "building_id": building_id,
                "target_role": target["target_role"],
                "tier": target["tier"],
                "measurement_state": "missing",
            }
        result.append(row)
    return result


def quality_notes(config: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema": "jointbuildgs.fusion_w1_aprime.report.quality_notes.v1",
        "audience": "technical",
        "delivery_surface": "repo_native_markdown_csv_and_static_png",
        "user_override": (
            "repository contract requests fixed CSV names, one-page Markdown, and PNG panels; "
            "no external publication surface is created by this driver"
        ),
        "report_structure": [
            "title",
            "observational technical summary",
            "preregistered gauge values",
            "scope and metric definitions",
            "per-job and stratified evidence",
            "T1-T5 receipt results",
            "GS4Buildings overlap record",
            "issues and incomplete artifacts",
        ],
        "omissions": {
            "interpretation": "explicitly prohibited by dispatch",
            "scientific_recommendations": "reserved for human review",
            "causal_claims": "not produced",
        },
        "chart_map": [
            {
                "section": "per-job opacity trajectory",
                "question": "what was the observed class-6 seed-lineage median opacity over optimizer iterations",
                "family": "Trend",
                "type": "single-series line with two preregistered vertical references",
                "fields": ["iteration", "opacity_median"],
                "data_sufficiency": "all audit iterations available; missing audit produces an explicit placeholder",
                "palette_policy": "single-root preferred plus two reference colors",
                "non_color_encoding": "dash pattern distinguishes transition references",
            },
            {
                "section": "per-job qualitative review panel",
                "question": "what source and readout geometries are present for the requested review surfaces",
                "family": "Tables and Scorecards / spatial small multiples",
                "type": "fixed nine-cell static review panel",
                "fields": [
                    "input crop",
                    "seed XY",
                    "mesh vertices XY",
                    "surface samples XY and section",
                    "CityJSON rings",
                    "reference GML rings",
                    "opacity trajectory",
                ],
                "missing_policy": "component-level missing label; panel retained and marked partial",
                "palette_policy": "single-root preferred with charcoal reference geometry",
            },
        ],
        "measurement_state_contract": config["measurement_contract"][
            "measurement_states"
        ],
        "censored_is_measured": False,
        "scientific_verdict": None,
    }


def git_identity() -> dict[str, Any]:
    def run(*args: str) -> str | None:
        try:
            return subprocess.check_output(
                ["git", *args], cwd=REPO, text=True, stderr=subprocess.DEVNULL
            ).strip()
        except (OSError, subprocess.CalledProcessError):
            return None

    return {
        "head": run("rev-parse", "HEAD"),
        "branch": run("branch", "--show-current"),
    }


def validate_report_descendant_paths(
    changed_paths: Iterable[str],
    allowlist: Iterable[str],
    glob_allowlist: Iterable[str] = (),
) -> list[str]:
    allowed = set(allowlist)
    patterns = list(glob_allowlist)
    changed = sorted(set(changed_paths))
    unexpected = [
        path
        for path in changed
        if path not in allowed
        and not any(PurePosixPath(path).match(pattern) for pattern in patterns)
    ]
    if unexpected:
        raise ReportContractError(
            "report generation descendant contains non-report paths: "
            + ", ".join(unexpected)
        )
    return changed


def report_provenance(config: Mapping[str, Any]) -> dict[str, Any]:
    def run(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(
            ["git", "-c", f"safe.directory={REPO}", "-C", str(REPO), *args],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        if check and result.returncode:
            raise ReportContractError(
                result.stderr.strip() or result.stdout.strip() or "git provenance query failed"
            )
        return result

    contract = config["provenance_contract"]
    execution_head = str(contract["execution_head"])
    generation_head = run("rev-parse", "HEAD").stdout.strip()
    ancestor = run(
        "merge-base", "--is-ancestor", execution_head, generation_head, check=False
    ).returncode == 0
    if not ancestor:
        raise ReportContractError("execution HEAD is not an ancestor of report generation HEAD")
    report_files = list(contract["report_implementation_files"])
    exact_allowlist = [
        *report_files,
        *contract["recovery_exact_descendant_allowlist"],
        *contract["operational_evidence_exact_descendant_allowlist"],
    ]
    glob_allowlist = list(contract["recovery_glob_descendant_allowlist"])
    history_changed = validate_report_descendant_paths(
        [
            path
            for path in run(
                "log",
                "--format=",
                "--name-only",
                "--no-renames",
                f"{execution_head}..{generation_head}",
            ).stdout.splitlines()
            if path
        ],
        exact_allowlist,
        glob_allowlist,
    )
    final_tree_changed = validate_report_descendant_paths(
        run("diff", "--name-only", "--no-renames", f"{execution_head}..{generation_head}")
        .stdout.splitlines(),
        exact_allowlist,
        glob_allowlist,
    )
    implementation = []
    for logical in report_files:
        if run("ls-files", "--error-unmatch", logical, check=False).returncode:
            raise ReportContractError(f"report implementation is not tracked: {logical}")
        head_blob = run("rev-parse", f"{generation_head}:{logical}", check=False)
        if head_blob.returncode:
            raise ReportContractError(f"report implementation absent at generation HEAD: {logical}")
        worktree_blob = run("hash-object", "--", logical).stdout.strip()
        matches = worktree_blob == head_blob.stdout.strip()
        if contract.get("report_files_must_match_generation_head") is True and not matches:
            raise ReportContractError(
                f"report implementation differs from generation HEAD: {logical}"
            )
        implementation.append(
            {
                "path": logical,
                "git_blob": worktree_blob,
                "sha256": sha256_file(repo_path(logical)),
                "worktree_matches_generation_head": matches,
            }
        )
    recovery_expected = {
        record["path"]: record
        for record in config["recovery_contract"]["controller_files"]
    }
    operational = []
    for logical in history_changed:
        if logical in report_files:
            continue
        if run("ls-files", "--error-unmatch", logical, check=False).returncode:
            raise ReportContractError(
                f"allowed operational descendant path is not tracked: {logical}"
            )
        head_blob = run("rev-parse", f"{generation_head}:{logical}", check=False)
        if head_blob.returncode:
            raise ReportContractError(
                f"allowed operational descendant path absent at generation HEAD: {logical}"
            )
        worktree_blob = run("hash-object", "--", logical).stdout.strip()
        matches = worktree_blob == head_blob.stdout.strip()
        if not matches:
            raise ReportContractError(
                f"operational evidence differs from generation HEAD: {logical}"
            )
        digest = sha256_file(repo_path(logical))
        expected = recovery_expected.get(logical)
        if expected is not None and (
            digest != expected["sha256"]
            or repo_path(logical).stat().st_size != int(expected["bytes"])
        ):
            raise ReportContractError(
                f"recovery implementation differs from controller contract: {logical}"
            )
        operational.append(
            {
                "path": logical,
                "git_blob": worktree_blob,
                "sha256": digest,
                "worktree_matches_generation_head": matches,
                "controller_hash_bound": expected is not None,
            }
        )
    return {
        "execution_head": execution_head,
        "report_generation_head": generation_head,
        "execution_head_is_ancestor": ancestor,
        "report_and_recovery_only_descendant": True,
        "descendant_history_changed_paths": history_changed,
        "descendant_final_tree_changed_paths": final_tree_changed,
        "report_implementation_files_allowlist": report_files,
        "recovery_exact_descendant_allowlist": list(
            contract["recovery_exact_descendant_allowlist"]
        ),
        "operational_evidence_exact_descendant_allowlist": list(
            contract["operational_evidence_exact_descendant_allowlist"]
        ),
        "recovery_glob_descendant_allowlist": glob_allowlist,
        "report_generation_branch": run("branch", "--show-current").stdout.strip(),
        "implementation_files": implementation,
        "operational_descendant_files": operational,
    }


def artifact_records(root: Path, *, exclude: set[str] | None = None) -> list[dict[str, Any]]:
    excluded = exclude or set()
    result: list[dict[str, Any]] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.relative_to(root).as_posix() in excluded:
            continue
        result.append(
            {
                "path": path.relative_to(root).as_posix(),
                "bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
        )
    return result


def validate_snapshot_artifacts(
    snapshot: Path,
    manifest_payload: Mapping[str, Any],
    config: Mapping[str, Any],
) -> None:
    records = manifest_payload.get("artifacts")
    if not isinstance(records, list):
        raise ReportContractError("existing report artifact inventory missing")
    expected: dict[str, Mapping[str, Any]] = {}
    for record in records:
        if not isinstance(record, Mapping):
            raise ReportContractError("existing report artifact row drift")
        raw_path = record.get("path")
        if not isinstance(raw_path, str) or not raw_path:
            raise ReportContractError("existing report artifact path missing")
        relative = Path(raw_path)
        if (
            relative.is_absolute()
            or relative.as_posix() != raw_path
            or any(part in {"", ".", ".."} for part in relative.parts)
        ):
            raise ReportContractError(f"unsafe existing report artifact path: {raw_path}")
        if raw_path in expected:
            raise ReportContractError(f"duplicate existing report artifact path: {raw_path}")
        expected[raw_path] = record
    excluded = {config["outputs"]["manifest"], config["outputs"]["receipt"]}
    observed = {
        path.relative_to(snapshot).as_posix()
        for path in snapshot.rglob("*")
        if path.is_file() and path.relative_to(snapshot).as_posix() not in excluded
    }
    if observed != set(expected):
        raise ReportContractError("existing report artifact inventory/path set drift")
    for raw_path, record in expected.items():
        path = snapshot / raw_path
        if path.is_symlink() or not path.is_file():
            raise ReportContractError(f"existing report artifact missing: {raw_path}")
        if int(record.get("bytes", -1)) != path.stat().st_size:
            raise ReportContractError(f"existing report artifact byte drift: {raw_path}")
        if record.get("sha256") != sha256_file(path):
            raise ReportContractError(f"existing report artifact SHA drift: {raw_path}")


def validate_existing_snapshot(
    snapshot: Path,
    config: Mapping[str, Any],
    fingerprint: str,
    *,
    require_terminal: bool = False,
    current_provenance: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    receipt = snapshot / config["outputs"]["receipt"]
    manifest = snapshot / config["outputs"]["manifest"]
    if not receipt.is_file() or not manifest.is_file():
        raise ReportContractError(f"content-addressed snapshot incomplete: {snapshot}")
    payload = load_json(receipt)
    if payload.get("schema") != RECEIPT_SCHEMA:
        raise ReportContractError("existing report receipt schema drift")
    if payload.get("input_fingerprint") != fingerprint:
        raise ReportContractError("existing report snapshot fingerprint collision")
    if nested_get(payload, "manifest.sha256") != sha256_file(manifest):
        raise ReportContractError("existing report manifest hash drift")
    manifest_payload = load_json(manifest)
    if manifest_payload.get("schema") != MANIFEST_SCHEMA:
        raise ReportContractError("existing report manifest schema drift")
    if payload.get("state") not in {"PARTIAL", "TERMINAL"}:
        raise ReportContractError("existing report snapshot state drift")
    if manifest_payload.get("state") != payload.get("state"):
        raise ReportContractError("existing report receipt/manifest state drift")
    if current_provenance is not None and (
        canonical_sha(payload.get("provenance")) != canonical_sha(current_provenance)
        or canonical_sha(manifest_payload.get("provenance"))
        != canonical_sha(current_provenance)
    ):
        raise ReportContractError("existing report generation provenance drift")
    validate_snapshot_artifacts(snapshot, manifest_payload, config)
    if require_terminal and payload.get("state") != "TERMINAL":
        raise ReportContractError("final mode refuses cached PARTIAL report snapshot")
    return payload


def publish_latest(
    output_root: Path,
    snapshot: Path,
    receipt: Mapping[str, Any],
    config: Mapping[str, Any],
) -> None:
    payload = {
        "schema": LATEST_SCHEMA,
        "run_id": config["run_id"],
        "snapshot_id": snapshot.name,
        "snapshot_path": repo_relative(snapshot),
        "receipt": {
            "path": repo_relative(snapshot / config["outputs"]["receipt"]),
            "sha256": sha256_file(snapshot / config["outputs"]["receipt"]),
        },
        "state": receipt["state"],
        "execution_head": nested_get(receipt, "provenance.execution_head"),
        "report_generation_head": nested_get(
            receipt, "provenance.report_generation_head"
        ),
        "scientific_verdict": None,
    }
    atomic_json(output_root / config["outputs"]["latest"], payload)


def build_snapshot(
    config: Mapping[str, Any], *, require_terminal: bool = False
) -> dict[str, Any]:
    provenance = report_provenance(config)
    targets = load_targets(config)
    jobs = expected_jobs(targets, config)
    queue = load_queue_evidence(jobs, config)
    t4 = load_t4_bundle(config)
    sources = source_inventory(
        jobs, config, queue_evidence=queue, t4_bundle=t4
    )
    fingerprint = source_fingerprint(sources, config, provenance=provenance)
    snapshot_id = fingerprint[:16]
    output_root = repo_path(config["outputs"]["root"])
    snapshots = output_root / config["outputs"]["snapshots"]
    snapshot = snapshots / snapshot_id
    if snapshot.exists():
        receipt = validate_existing_snapshot(
            snapshot,
            config,
            fingerprint,
            require_terminal=require_terminal,
            current_provenance=provenance,
        )
        publish_latest(output_root, snapshot, receipt, config)
        return dict(receipt)

    p0prime = load_p0prime_scores(config)
    t5 = load_t5(config)
    scores, alpha, runtime = build_score_rows(
        jobs, config, p0prime, t5, queue_evidence=queue
    )
    pending = [
        row for row in scores if row["job_terminal_state"] not in TERMINAL_STATES
    ]
    queue_complete = queue.get("complete")
    queue_terminal_state = (
        queue_complete.get("state")
        if isinstance(queue_complete, Mapping)
        else None
    )
    if require_terminal:
        if queue_terminal_state != "COMPLETE":
            raise ReportContractError("final mode requires queue state COMPLETE")
        if int(queue.get("incomplete_archives_n", 0)):
            raise ReportContractError("final mode refuses incomplete queue training archive")
        if pending:
            raise ReportContractError(
                f"queue COMPLETE has {len(pending)} nonterminal unique jobs"
            )

    snapshots.mkdir(parents=True, exist_ok=True)
    staging = snapshots / f".staging_{snapshot_id}_{os.getpid()}"
    if staging.exists():
        raise ReportContractError(f"report staging path already exists: {staging}")
    staging.mkdir(parents=True)
    try:
        t4_bundle_manifest = publish_t4_bundle(staging, config, t4)
        opacity = generate_visuals(scores, runtime, staging, config)
        summary = build_summary(scores, config)
        replicate = build_replicate_medians(scores, config)
        gauges = build_gauges(scores, replicate)
        preflight = preflight_rows(config)
        overlap = overlap_rows(targets)
        issues = issue_rows(config)
        incomplete = incomplete_rows(scores)
        loss = loss_share_rows(runtime)
        p0_rows = p0prime_output_rows(targets, p0prime, config)
        seed_rows = seed_stat_rows(targets, t5)
        outputs = config["outputs"]

        write_csv(staging / outputs["targets_csv"], targets)
        write_csv(staging / outputs["seed_stats_csv"], seed_rows)
        write_csv(staging / outputs["p0prime_scores_csv"], p0_rows)
        write_csv(staging / outputs["loss_shares_csv"], loss)
        write_csv(staging / outputs["scores_csv"], scores)
        write_csv(staging / outputs["alpha_comparison_csv"], alpha)
        write_csv(staging / outputs["replicate_medians_csv"], replicate)
        write_csv(staging / outputs["summary_csv"], summary)
        write_csv(staging / outputs["gauge_csv"], gauges)
        write_csv(staging / outputs["preflight_csv"], preflight)
        write_csv(staging / outputs["overlap_csv"], overlap)
        write_csv(staging / outputs["incomplete_csv"], incomplete)
        write_csv(staging / outputs["issues_csv"], issues)
        write_csv(staging / outputs["opacity_csv"], opacity)
        write_csv(
            staging / outputs["queue_stage_records_csv"],
            [
                {key: value for key, value in row.items() if key != "payload"}
                for row in queue["stage_rows"]
            ],
        )
        write_csv(staging / outputs["queue_archives_csv"], queue["archive_rows"])
        write_csv(staging / outputs["queue_recoveries_csv"], queue["recovery_rows"])
        write_csv(staging / outputs["source_inventory_csv"], sources)
        atomic_json(staging / outputs["quality_notes_json"], quality_notes(config))

        one_page = build_one_page_markdown(
            gauges, scores, preflight, overlap, snapshot_id, config
        )
        report = build_report_markdown(
            one_page,
            scores,
            summary,
            preflight,
            overlap,
            issues,
            incomplete,
            config,
        )
        assert_observational_language(one_page)
        assert_observational_language(report)
        atomic_text(staging / outputs["one_page_markdown"], one_page)
        atomic_text(staging / outputs["report_markdown"], report)

        inventory_before = artifact_records(
            staging,
            exclude={
                outputs["artifact_inventory_csv"],
                outputs["manifest"],
                outputs["receipt"],
            },
        )
        write_csv(staging / outputs["artifact_inventory_csv"], inventory_before)
        artifacts = artifact_records(
            staging, exclude={outputs["manifest"], outputs["receipt"]}
        )
        final_queue = load_queue_evidence(jobs, config)
        final_t4 = load_t4_bundle(config)
        final_sources = source_inventory(
            jobs,
            config,
            queue_evidence=final_queue,
            t4_bundle=final_t4,
        )
        if source_fingerprint(
            final_sources, config, provenance=provenance
        ) != fingerprint:
            raise ReportContractError("report sources changed during snapshot build")
        if canonical_sha(report_provenance(config)) != canonical_sha(provenance):
            raise ReportContractError("report provenance changed during snapshot build")
        terminal_n = sum(
            row["job_terminal_state"] in TERMINAL_STATES for row in scores
        )
        measured_n = sum(
            row["primary_measurement_state"] == "measured" for row in scores
        )
        censored_n = sum(
            row["primary_measurement_state"] == "censored" for row in scores
        )
        state = "TERMINAL" if queue_terminal_state == "COMPLETE" else "PARTIAL"
        manifest_payload = {
            "schema": MANIFEST_SCHEMA,
            "created_at": utc_now(),
            "task_id": config["task_id"],
            "run_id": config["run_id"],
            "snapshot_id": snapshot_id,
            "input_fingerprint": fingerprint,
            "state": state,
            "git": git_identity(),
            "provenance": provenance,
            "queue": {
                "expected_jobs": len(scores),
                "expected_stage_entries": int(
                    config["queue_contract"]["expected_stage_entries"]
                ),
                "observed_stage_entries": int(queue["stage_entries_n"]),
                "unique_jobs_after_smoke_reuse_dedup": int(queue["unique_jobs_n"]),
                "terminal_jobs": terminal_n,
                "terminal_unique_jobs_from_stage_records": int(
                    queue["terminal_unique_jobs_n"]
                ),
                "terminal_queue_receipt_present": queue_terminal_state is not None,
                "terminal_queue_state": queue_terminal_state,
                "incomplete_training_archives": int(queue["incomplete_archives_n"]),
                "recovery_controller_present": queue["recovery_controller"] is not None,
                "rehydrated_attempts": int(queue["rehydrated_attempts_n"]),
                "primary_measured_jobs": measured_n,
                "primary_censored_jobs": censored_n,
                "primary_missing_jobs": len(scores) - measured_n - censored_n,
            },
            "preflight": preflight,
            "measurement_contract": config["measurement_contract"],
            "visual_contract": config["visual_contract"],
            "t4_bundle": t4_bundle_manifest,
            "sources": sources,
            "artifacts": artifacts,
            "publication": {
                "content_addressed": True,
                "staging_before_publish": True,
                "source_inventory_rehashed_before_publish": True,
                "queue_stage_receipts_sha_verified": True,
                "queue_archive_receipts_sha_verified": True,
                "queue_recovery_receipts_sha_verified": True,
                "smoke_reuse_deduplicated_to_unique_job": True,
                "cached_partial_rejected_for_final": True,
                "t4_bundle_hash_verified_before_copy": True,
                "report_and_recovery_descendant_provenance_required": True,
                "receipt_written_last": True,
                "partial_allowed": True,
            },
            "scientific_verdict": None,
            "interpretation": None,
        }
        manifest_path = staging / outputs["manifest"]
        atomic_json(manifest_path, manifest_payload)
        receipt_payload = {
            "schema": RECEIPT_SCHEMA,
            "created_at": utc_now(),
            "task_id": config["task_id"],
            "run_id": config["run_id"],
            "snapshot_id": snapshot_id,
            "input_fingerprint": fingerprint,
            "state": state,
            "counts": manifest_payload["queue"],
            "provenance": provenance,
            "manifest": {
                "path": outputs["manifest"],
                "sha256": sha256_file(manifest_path),
            },
            "receipt_written_last_inside_snapshot": True,
            "censored_is_measured": False,
            "scientific_verdict": None,
            "interpretation": None,
        }
        atomic_json(staging / outputs["receipt"], receipt_payload)
        os.replace(staging, snapshot)
        publish_latest(output_root, snapshot, receipt_payload, config)
        return receipt_payload
    except BaseException:
        if staging.exists():
            shutil.rmtree(staging)
        raise


def check_inputs(config: Mapping[str, Any]) -> dict[str, Any]:
    provenance = report_provenance(config)
    targets = load_targets(config)
    jobs = expected_jobs(targets, config)
    queue = load_queue_evidence(jobs, config)
    t4 = load_t4_bundle(config)
    inventory = source_inventory(
        jobs, config, queue_evidence=queue, t4_bundle=t4
    )
    return {
        "schema": "jointbuildgs.fusion_w1_aprime.report.check.v2",
        "targets_n": len(targets),
        "jobs_n": len(jobs),
        "queue_stage_entries_n": queue["stage_entries_n"],
        "queue_unique_jobs_n": queue["unique_jobs_n"],
        "queue_terminal_unique_jobs_n": queue["terminal_unique_jobs_n"],
        "queue_incomplete_archives_n": queue["incomplete_archives_n"],
        "queue_rehydrated_attempts_n": queue["rehydrated_attempts_n"],
        "t4_source_hashes_verified": True,
        "provenance": provenance,
        "sources_present_n": sum(row["state"] == "present" for row in inventory),
        "sources_missing_n": sum(row["state"] == "missing" for row in inventory),
        "missing_roles": [row["role"] for row in inventory if row["state"] == "missing"],
        "scientific_verdict": None,
    }


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("check")
    build = subparsers.add_parser("build")
    build.add_argument("--require-terminal", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        config = load_config(args.config)
        if args.command == "check":
            payload = check_inputs(config)
        else:
            payload = build_snapshot(config, require_terminal=args.require_terminal)
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    except ReportContractError as exc:
        print(json.dumps({"status": "BLOCKED", "reason": str(exc)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
