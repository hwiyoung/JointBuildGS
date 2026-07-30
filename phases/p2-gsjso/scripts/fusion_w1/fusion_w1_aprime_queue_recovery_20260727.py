#!/usr/bin/env python3
"""Recovery controller for the A-prime queue receipt-shape defect.

The committed queue controller compares a producer materialization record
(`path`, `sha256`) against its own file record (`path`, `sha256`, `bytes`).
This shim keeps the committed execution HEAD and producer code unchanged,
imports that controller, and narrows only that comparison to the producer's
two-field contract.  It also provides a hash-checked, append-only rehydration
of the valid smoke completion that the defect archived.
"""

from __future__ import annotations

import argparse
import fcntl
import importlib.util
import os
import shutil
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence


REPO = Path(__file__).resolve().parents[4]
BASE_DRIVER = REPO / "phases/p2-gsjso/scripts/fusion_w1/fusion_w1_aprime_queue_20260726.py"
DEFAULT_CONFIG = REPO / "phases/p2-gsjso/configs/fusion_w1/fusion_w1_aprime_queue_20260726.json"
SHIM_PATH = REPO / "phases/p2-gsjso/scripts/fusion_w1/fusion_w1_aprime_queue_recovery_20260727.py"
WRAPPER_PATH = REPO / "phases/p2-gsjso/scripts/fusion_w1/run_fusion_w1_aprime_queue_recovery_20260727.sh"
TEST_PATH = REPO / "tests/fusion_w1/test_fusion_w1_aprime_queue_recovery_20260727.py"
CONTROLLER_SCHEMA = "jointbuildgs.fusion_w1_aprime.unattended.recovery_controller.v1"
INTENT_SCHEMA = "jointbuildgs.fusion_w1_aprime.unattended.rehydration_intent.v1"
RECEIPT_SCHEMA = "jointbuildgs.fusion_w1_aprime.unattended.rehydration_receipt.v1"
BUG_REASON = "training_receipts_or_materialization_do_not_match_runtime_head"
EXCLUDED_ARCHIVE_FILES = {"orchestrator_orphan_failure.json"}


def load_base() -> Any:
    spec = importlib.util.spec_from_file_location(
        "fusion_w1_aprime_queue_committed", BASE_DRIVER
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load committed queue driver: {BASE_DRIVER}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


queue = load_base()
_ORIGINAL_VERIFY_TRAINING_BINDING = queue.verify_training_binding


def producer_materialization_record(record: Mapping[str, Any]) -> dict[str, Any]:
    """Return the exact two-field record emitted by the training producer."""
    return {"path": record["path"], "sha256": record["sha256"]}


def compatible_verify_training_binding(
    module: Any,
    training_config: Mapping[str, Any],
    entry: Mapping[str, Any],
    materialized: Path,
    completed: Path | None,
) -> dict[str, Any]:
    """Run the committed validator with one path-local record projection.

    No producer receipt is rewritten.  All non-materialization records retain
    their original byte-count field and all existing HEAD/hash checks run.
    """
    original_file_record = queue.file_record
    materialized_resolved = Path(materialized).resolve()

    def projected_file_record(path: Path) -> dict[str, Any]:
        record = original_file_record(path)
        if Path(path).resolve() == materialized_resolved:
            return producer_materialization_record(record)
        return record

    queue.file_record = projected_file_record
    try:
        return _ORIGINAL_VERIFY_TRAINING_BINDING(
            module, training_config, entry, materialized, completed
        )
    finally:
        queue.file_record = original_file_record


queue.verify_training_binding = compatible_verify_training_binding


def recovery_root(config: Mapping[str, Any], entry: Mapping[str, Any]) -> Path:
    return (
        queue.repo_path(config["outputs"]["root"])
        / "recovery"
        / "by_building"
        / entry["building_id"]
        / f"arm_{entry['arm']}"
        / entry["replicate"]
    )


def controller_path(config: Mapping[str, Any]) -> Path:
    return queue.repo_path(config["outputs"]["root"]) / "recovery/controller.json"


def controller_files() -> list[dict[str, Any]]:
    records = []
    for path in (SHIM_PATH, WRAPPER_PATH, TEST_PATH):
        records.append(queue.file_record(path))
    return records


def publish_controller(config: Mapping[str, Any]) -> dict[str, Any]:
    plan = queue.load_plan(config)
    path = controller_path(config)
    payload = {
        "schema": CONTROLLER_SCHEMA,
        "state": "ACTIVE",
        "created_at": queue.now_iso(),
        "run_id": config["run_id"],
        "task_id": "FUS-W1-APRIME-QUEUE-RECOVERY-001",
        "execution_head": queue.git("rev-parse", "HEAD").stdout.strip(),
        "queue_plan": queue.file_record(queue.repo_path(config["outputs"]["plan"])),
        "committed_queue_driver": queue.file_record(BASE_DRIVER),
        "recovery_files": controller_files(),
        "scope": "materialization receipt path+sha compatibility and valid archive rehydration",
        "producer_receipts_rewritten": False,
        "interpretation_or_verdict": None,
    }
    if path.exists() or path.is_symlink():
        observed = queue.load_json(path)
        for key, value in payload.items():
            if key != "created_at":
                queue.require_equal(observed.get(key), value, f"recovery controller {key}")
        return {**observed, "publication_reused": True}
    queue.exclusive_json(path, payload)
    queue.append_event(
        config,
        "QUEUE_RECOVERY_CONTROLLER_ACTIVATED",
        {"receipt": queue.file_record(path), "execution_head": payload["execution_head"]},
    )
    return payload


def relative_under(path: Path, root: Path, label: str) -> Path:
    try:
        return path.relative_to(root)
    except ValueError as exc:
        raise queue.UnattendedError(f"{label} is outside canonical training root") from exc


def verify_archived_completion(
    module: Any,
    training_config: Mapping[str, Any],
    entry: Mapping[str, Any],
    canonical: Path,
    source: Path,
) -> dict[str, Any]:
    materialized = source / training_config["outputs"]["materialization_manifest"]
    completed_path = source / training_config["outputs"]["completed_receipt"]
    started_path = source / training_config["outputs"]["started_receipt"]
    completed = queue.load_json(completed_path)
    queue.require_equal(completed.get("schema"), module.COMPLETED_SCHEMA, "archived completion schema")
    queue.require_equal(completed.get("status"), "COMPLETED", "archived completion status")
    queue.require_equal(completed.get("return_code"), 0, "archived training return code")
    for key, expected in (
        ("building_id", entry["building_id"]),
        ("arm", entry["arm"]),
        ("replicate", entry["replicate"]),
        ("profile", "full"),
    ):
        queue.require_equal(completed.get(key), expected, f"archived completion {key}")
    expected_materialization = {
        "path": queue.relative(
            canonical / training_config["outputs"]["materialization_manifest"]
        ),
        "sha256": queue.sha256_file(materialized),
    }
    queue.require_equal(
        completed.get("materialization"),
        expected_materialization,
        "archived producer materialization binding",
    )
    started_record = completed.get("started_receipt")
    if not isinstance(started_record, Mapping):
        raise queue.UnattendedError("archived completion lacks started receipt")
    queue.require_equal(
        started_record.get("path"),
        queue.relative(canonical / training_config["outputs"]["started_receipt"]),
        "archived started path",
    )
    queue.require_equal(
        started_record.get("sha256"), queue.sha256_file(started_path), "archived started SHA"
    )
    training_completion = completed.get("training_completion")
    if not isinstance(training_completion, Mapping):
        raise queue.UnattendedError("archived completion lacks training evidence")
    queue.require_equal(
        training_completion.get("completed_optimizer_updates"),
        30000,
        "archived optimizer updates",
    )
    final_record = training_completion.get("final_checkpoint")
    if not isinstance(final_record, Mapping):
        raise queue.UnattendedError("archived completion lacks final checkpoint")
    final_canonical = queue.repo_path(final_record["path"])
    final_relative = relative_under(final_canonical, canonical, "final checkpoint")
    final_archived = source / final_relative
    queue.require_equal(
        final_record.get("sha256"), queue.sha256_file(final_archived), "archived final checkpoint SHA"
    )
    return {
        "completed": queue.file_record(completed_path),
        "materialization": queue.file_record(materialized),
        "started": queue.file_record(started_path),
        "final_checkpoint": queue.file_record(final_archived),
        "completed_optimizer_updates": 30000,
    }


def filtered_ledger(root: Path) -> list[dict[str, Any]]:
    records = []
    for record in queue.recursive_ledger(root):
        if record["relative_to_root"] in EXCLUDED_ARCHIVE_FILES:
            continue
        records.append(record)
    return records


def ledger_signature(records: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "relative_to_root": record["relative_to_root"],
            "bytes": record["bytes"],
            "sha256": record["sha256"],
        }
        for record in records
    ]


def verify_destination(source_records: Sequence[Mapping[str, Any]], destination: Path) -> list[dict[str, Any]]:
    observed = queue.recursive_ledger(destination)
    queue.require_equal(
        ledger_signature(observed), ledger_signature(source_records), "rehydrated artifact ledger"
    )
    return observed


def acquire_unlocked_queue(config: Mapping[str, Any]) -> Any:
    path = queue.repo_path(config["outputs"]["driver_lock"])
    path.parent.mkdir(parents=True, exist_ok=True)
    stream = path.open("a+b")
    try:
        fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as exc:
        stream.close()
        raise queue.UnattendedError("queue recovery requires an idle queue driver") from exc
    return stream


def rehydrate_valid_archive(
    config: Mapping[str, Any], *, stage_key: str, stage_entry_order: int, attempt: int
) -> dict[str, Any]:
    lock_stream = acquire_unlocked_queue(config)
    try:
        plan = queue.load_plan(config)
        entry = queue.entry_for(plan, stage_key, stage_entry_order)
        module, training_config, canonical = queue.training_job_path(config, entry)
        archives = queue.training_archives(config, entry)
        matches = [item for item in archives if int(item["receipt"]["attempt"]) == attempt]
        queue.require_equal(len(matches), 1, "rehydration source archive count")
        archive = matches[0]
        archive_receipt = archive["receipt"]
        queue.require_equal(
            archive_receipt.get("error_type"), "OrphanedTrainingAttempt", "rehydration error type"
        )
        queue.require_equal(archive_receipt.get("reason"), BUG_REASON, "rehydration defect reason")
        source = archive["path"] / "training_job"
        evidence = verify_archived_completion(
            module, training_config, entry, canonical, source
        )
        source_records = filtered_ledger(source)
        excluded_present = sorted(
            str(path.relative_to(source))
            for path in source.rglob("*")
            if path.is_file() and str(path.relative_to(source)) in EXCLUDED_ARCHIVE_FILES
        )
        queue.require_equal(
            excluded_present, sorted(EXCLUDED_ARCHIVE_FILES), "excluded orchestration artifacts"
        )
        root = recovery_root(config, entry) / f"rehydration_attempt_{attempt:03d}"
        root.mkdir(parents=True, exist_ok=True)
        intent_path = root / "intent.json"
        receipt_path = root / "receipt.json"
        intent = {
            "schema": INTENT_SCHEMA,
            "state": "PLANNED",
            "created_at": queue.now_iso(),
            "entry": dict(entry),
            "execution_head": queue.git("rev-parse", "HEAD").stdout.strip(),
            "source_archive_receipt": queue.file_record(archive["receipt_path"]),
            "source_training_root": queue.relative(source),
            "destination_training_root": queue.relative(canonical),
            "source_completion_evidence": evidence,
            "copied_artifacts": ledger_signature(source_records),
            "excluded_artifacts": excluded_present,
            "controller": queue.file_record(controller_path(config)),
            "producer_receipts_rewritten": False,
            "interpretation_or_verdict": None,
        }
        if intent_path.exists() or intent_path.is_symlink():
            observed_intent = queue.load_json(intent_path)
            for key, value in intent.items():
                if key != "created_at":
                    queue.require_equal(observed_intent.get(key), value, f"rehydration intent {key}")
        else:
            queue.exclusive_json(intent_path, intent)
        if receipt_path.exists() or receipt_path.is_symlink():
            receipt = queue.load_json(receipt_path)
            queue.require_equal(receipt.get("schema"), RECEIPT_SCHEMA, "rehydration receipt schema")
            verify_destination(source_records, canonical)
            return {**receipt, "publication_reused": True}
        staging = canonical.parent / f".{canonical.name}.rehydration_attempt_{attempt:03d}.incomplete"
        if canonical.exists() or canonical.is_symlink():
            verify_destination(source_records, canonical)
        else:
            if staging.exists() or staging.is_symlink():
                verify_destination(source_records, staging)
            else:
                canonical.parent.mkdir(parents=True, exist_ok=True)
                shutil.copytree(
                    source,
                    staging,
                    copy_function=shutil.copy2,
                    ignore=shutil.ignore_patterns(*sorted(EXCLUDED_ARCHIVE_FILES)),
                )
                verify_destination(source_records, staging)
            os.replace(staging, canonical)
            queue.fsync_directory(canonical.parent)
        destination_records = verify_destination(source_records, canonical)
        receipt = {
            "schema": RECEIPT_SCHEMA,
            "state": "REHYDRATED_VALID_COMPLETION",
            "created_at": queue.now_iso(),
            "entry": dict(entry),
            "execution_head": queue.git("rev-parse", "HEAD").stdout.strip(),
            "defect": {
                "error_type": "ReceiptShapeMismatch",
                "reason": BUG_REASON,
                "producer_shape": ["path", "sha256"],
                "queue_shape": ["path", "sha256", "bytes"],
            },
            "intent": queue.file_record(intent_path),
            "source_archive_receipt": queue.file_record(archive["receipt_path"]),
            "destination_training_root": queue.relative(canonical),
            "destination_artifacts": ledger_signature(destination_records),
            "excluded_artifacts": excluded_present,
            "producer_receipts_rewritten": False,
            "append_only_source_preserved": True,
            "interpretation_or_verdict": None,
        }
        queue.exclusive_json(receipt_path, receipt)
        queue.append_event(
            config,
            "VALID_TRAINING_COMPLETION_REHYDRATED",
            {"entry": dict(entry), "receipt": queue.file_record(receipt_path)},
        )
        queue.publish_status(config)
        return receipt
    finally:
        fcntl.flock(lock_stream.fileno(), fcntl.LOCK_UN)
        lock_stream.close()


def recovery_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    commands = parser.add_subparsers(dest="recovery_command", required=True)
    commands.add_parser("publish-controller")
    rehydrate = commands.add_parser("rehydrate-valid-archive")
    rehydrate.add_argument("--stage-key", required=True)
    rehydrate.add_argument("--stage-entry-order", required=True, type=int)
    rehydrate.add_argument("--attempt", required=True, type=int)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    effective = list(sys.argv[1:] if argv is None else argv)
    recovery_commands = {"publish-controller", "rehydrate-valid-archive"}
    if not recovery_commands.intersection(effective):
        return queue.main(effective)
    args = recovery_parser().parse_args(effective)
    config = queue.load_config(queue.repo_path(args.config))
    if args.recovery_command == "publish-controller":
        result = publish_controller(config)
    else:
        result = rehydrate_valid_archive(
            config,
            stage_key=args.stage_key,
            stage_entry_order=args.stage_entry_order,
            attempt=args.attempt,
        )
    queue.print_json(result)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except queue.UnattendedError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2)
