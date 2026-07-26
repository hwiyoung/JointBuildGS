#!/usr/bin/env python3
"""Focused contract tests for the unattended A-prime queue (no experiments)."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import re
import tempfile
import types
import unittest
from unittest import mock


REPO = Path(__file__).resolve().parents[3]
DRIVER_PATH = REPO / "phases/p2-gsjso/scripts/fusion_w1_aprime_queue_20260726.py"
CONFIG_PATH = REPO / "phases/p2-gsjso/configs/fusion_w1_aprime_queue_20260726.json"
WRAPPER_PATH = REPO / "phases/p2-gsjso/scripts/run_fusion_w1_aprime_queue_20260726.sh"


def load_driver():
    spec = importlib.util.spec_from_file_location("aprime_unattended_under_test", DRIVER_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


queue = load_driver()


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")


def entry(
    stage_order: int,
    stage_key: str,
    stage_entry_order: int,
    building_id: str,
    *,
    arm: str = "Aprime",
    replicate: str = "r1",
    reuse: bool = False,
) -> dict:
    return {
        "global_entry_order": stage_entry_order + (0 if stage_order == 0 else 1),
        "stage_order": stage_order,
        "stage_key": stage_key,
        "stage_entry_order": stage_entry_order,
        "queue_order": stage_entry_order,
        "building_id": building_id,
        "aprime_order": stage_entry_order,
        "target_role": "dim_failure",
        "arm": arm,
        "replicate": replicate,
        "profile": "full",
        "seed": 1001,
        "smoke_barrier_entry": stage_order == 0,
        "reuse_completed_smoke": reuse,
    }


class PlanContractTests(unittest.TestCase):
    def test_exact_stage_order_and_unique_job_contract(self):
        config = queue.load_config(CONFIG_PATH)
        rows = queue.build_plan(config)
        self.assertEqual(len(rows), 22)
        self.assertEqual(
            len({(row["building_id"], row["arm"], row["replicate"]) for row in rows}),
            21,
        )
        self.assertEqual(
            [(row["stage_key"], row["stage_entry_order"]) for row in rows[:3]],
            [("smoke_barrier", 1), ("aprime_r1", 1), ("aprime_r1", 2)],
        )
        self.assertEqual(
            (rows[0]["building_id"], rows[0]["arm"], rows[0]["replicate"]),
            ("DEBY_LOD2_42364609", "Aprime", "r1"),
        )
        self.assertEqual(
            (rows[1]["building_id"], rows[1]["arm"], rows[1]["replicate"]),
            ("DEBY_LOD2_42364609", "Aprime", "r1"),
        )
        self.assertTrue(rows[1]["reuse_completed_smoke"])
        self.assertEqual(
            [row["building_id"] for row in rows if row["stage_key"] == "B_r1"],
            ["DEBY_LOD2_42364609", "DEBY_LOD2_42364659", "DEBY_LOD2_4908023"],
        )

    def test_locked_hashes_match_current_inputs(self):
        config = queue.load_config(CONFIG_PATH)
        for record in config["locked_inputs"].values():
            path = REPO / record["path"]
            self.assertEqual(queue.sha256_file(path), record["sha256"], record["path"])

    def test_preflight_binding_is_current_head_and_ordered(self):
        source = DRIVER_PATH.read_text(encoding="utf-8")
        self.assertIn('method = module.committed_method_gate(REPO, training_config)', source)
        self.assertIn('require_equal(method["head"], head, "training method/current HEAD")', source)
        self.assertIn(
            'require_equal(gates.get("required_gates"), ["five_pin", "T1", "T2", "T3"]',
            source,
        )

    def test_t1_linked_receipts_preserve_current_training_method_hashes(self):
        config = queue.load_config(CONFIG_PATH)
        module, training_config, _path = queue.training_context(config)
        current = module.committed_method_gate(REPO, training_config)
        t1_contract = training_config["preflight_gates"]["T1"]
        t1_path = REPO / t1_contract["path"]
        gate_record = {
            "path": t1_contract["path"],
            "sha256": queue.sha256_file(t1_path),
        }
        evidence = queue.validate_t1_provenance(
            module, training_config, current, gate_record
        )
        self.assertEqual(evidence["status"], "PASSED")
        self.assertTrue(evidence["recorded_head_is_ancestor_of_current"])
        self.assertTrue(evidence["method_files_equal_current"])


class StateMachineTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.complete = self.root / "complete.json"
        self.stop = self.root / "stage_stop.json"
        self.config = {"outputs": {"complete": "ignored", "stage_stop": "ignored"}}
        self.path_patches = (
            mock.patch.object(queue, "complete_path", return_value=self.complete),
            mock.patch.object(queue, "stage_stop_path", return_value=self.stop),
        )
        for patcher in self.path_patches:
            patcher.start()

    def tearDown(self):
        for patcher in reversed(self.path_patches):
            patcher.stop()
        self.temporary.cleanup()

    def test_smoke_barrier_precedes_queue_and_is_reused(self):
        smoke = entry(0, "smoke_barrier", 1, "DEBY_LOD2_42364609")
        reused = entry(
            1,
            "aprime_r1",
            1,
            "DEBY_LOD2_42364609",
            reuse=True,
        )
        plan = {"entries": [smoke, reused]}
        records: dict[str, dict] = {}

        def record_for(_config, candidate):
            return records.get(candidate["stage_key"])

        with (
            mock.patch.object(queue, "load_plan", return_value=plan),
            mock.patch.object(queue, "load_stage_record", side_effect=record_for),
            mock.patch.object(
                queue,
                "inspect_pipeline",
                return_value={"state": "MISSING", "action": "MATERIALIZE_TRAINING"},
            ) as inspect,
        ):
            first = queue.next_action(self.config)
            self.assertEqual(first["entry"], smoke)
            records["smoke_barrier"] = {"status": "MEASURED"}
            second = queue.next_action(self.config)
            self.assertEqual(second["entry"], reused)
            self.assertEqual(inspect.call_args.args[1], reused)

    def test_three_consecutive_skipped_buildings_stops_stage(self):
        rows = [entry(1, "aprime_r1", index, f"DEBY_LOD2_{index}") for index in range(1, 5)]
        receipts = {
            row["building_id"]: {
                "status": "SKIPPED",
                "error_type": "CudaRuntimeError",
            }
            for row in rows[:3]
        }
        with (
            mock.patch.object(queue, "load_plan", return_value={"entries": rows}),
            mock.patch.object(
                queue,
                "load_stage_record",
                side_effect=lambda _config, row: receipts.get(row["building_id"]),
            ),
            mock.patch.object(queue, "stage_record_path", return_value=self.root / "record.json"),
            mock.patch.object(
                queue,
                "file_record",
                return_value={"path": "record.json", "sha256": "a" * 64, "bytes": 1},
            ),
        ):
            result = queue.next_action(self.config)
        self.assertEqual(result["action"], "STOP_STAGE")
        self.assertEqual(
            result["stop"]["reason_code"],
            "SAME_ERROR_TYPE_THREE_CONSECUTIVE_BUILDINGS",
        )
        self.assertEqual(
            result["stop"]["consecutive_buildings"],
            ["DEBY_LOD2_1", "DEBY_LOD2_2", "DEBY_LOD2_3"],
        )

    def test_skipped_smoke_stops_before_aprime_r1(self):
        smoke = entry(0, "smoke_barrier", 1, "DEBY_LOD2_42364609")
        later = entry(1, "aprime_r1", 1, "DEBY_LOD2_42364609", reuse=True)
        with (
            mock.patch.object(queue, "load_plan", return_value={"entries": [smoke, later]}),
            mock.patch.object(
                queue,
                "load_stage_record",
                side_effect=lambda _config, row: (
                    {"status": "SKIPPED", "error_type": "CudaRuntimeError"}
                    if row == smoke
                    else None
                ),
            ),
            mock.patch.object(queue, "stage_record_path", return_value=self.root / "record.json"),
            mock.patch.object(
                queue,
                "file_record",
                return_value={"path": "record.json", "sha256": "b" * 64, "bytes": 1},
            ),
            mock.patch.object(queue, "inspect_pipeline") as inspect,
        ):
            result = queue.next_action(self.config)
        self.assertEqual(result["action"], "STOP_STAGE")
        self.assertEqual(result["stop"]["reason_code"], "SMOKE_BARRIER_NOT_MEASURED")
        inspect.assert_not_called()

    def test_measured_row_resets_consecutive_skip_window(self):
        rows = [entry(1, "aprime_r1", index, f"DEBY_LOD2_{index}") for index in range(1, 5)]
        states = ["SKIPPED", "MEASURED", "SKIPPED", None]
        records = {
            row["building_id"]: (
                {"status": state, "error_type": "CudaRuntimeError"}
                if state is not None
                else None
            )
            for row, state in zip(rows, states)
        }
        with (
            mock.patch.object(queue, "load_plan", return_value={"entries": rows}),
            mock.patch.object(
                queue,
                "load_stage_record",
                side_effect=lambda _config, row: records[row["building_id"]],
            ),
            mock.patch.object(
                queue,
                "inspect_pipeline",
                return_value={"state": "MISSING", "action": "MATERIALIZE_TRAINING"},
            ),
        ):
            result = queue.next_action(self.config)
        self.assertEqual(result["action"], "MATERIALIZE_TRAINING")
        self.assertEqual(result["entry"], rows[3])


class ArchiveTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.original_repo = queue.REPO
        queue.REPO = self.root
        self.entry = entry(0, "smoke_barrier", 1, "DEBY_LOD2_42364609")
        self.training_job = self.root / "training/canonical"
        self.archive_root = self.root / "queue/archive"
        self.training_config = {
            "outputs": {
                "failed_receipt": "failed.json",
                "started_receipt": "started.json",
                "completed_receipt": "completed.json",
                "materialization_manifest": "materialization.json",
            }
        }
        self.fake_module = types.SimpleNamespace(
            FAILED_SCHEMA="jointbuildgs.fusion_w1_aprime.training_failed.v1",
            MATERIALIZATION_SCHEMA="jointbuildgs.fusion_w1_aprime.training_materialization.v1",
            committed_method_gate=lambda _repo, _config: {
                "branch": "exp/fusion-w1",
                "head": "2" * 40,
                "files": [],
            },
        )
        self.config = {
            "outputs": {"training_failure_archive": "queue/archive"}
        }
        self.patches = (
            mock.patch.object(
                queue,
                "next_action",
                return_value={"action": "ARCHIVE_TRAINING", "entry": self.entry},
            ),
            mock.patch.object(
                queue,
                "training_job_path",
                return_value=(self.fake_module, self.training_config, self.training_job),
            ),
            mock.patch.object(
                queue,
                "training_archive_root",
                return_value=self.archive_root,
            ),
            mock.patch.object(queue, "append_event", return_value={"sequence": 1}),
            mock.patch.object(queue, "publish_status", return_value={}),
            mock.patch.object(
                queue,
                "git",
                return_value=types.SimpleNamespace(stdout="f" * 40 + "\n"),
            ),
        )
        for patcher in self.patches:
            patcher.start()

    def tearDown(self):
        for patcher in reversed(self.patches):
            patcher.stop()
        queue.REPO = self.original_repo
        self.temporary.cleanup()

    def create_failure(self, marker: str = "partial-output") -> None:
        self.training_job.mkdir(parents=True)
        (self.training_job / "partial.bin").write_bytes(marker.encode("utf-8"))
        write_json(
            self.training_job / "failed.json",
            {
                "schema": self.fake_module.FAILED_SCHEMA,
                "status": "FAILED",
                "building_id": self.entry["building_id"],
                "arm": self.entry["arm"],
                "replicate": self.entry["replicate"],
                "profile": "full",
                "error_type": "CudaRuntimeError",
                "reason": "same deterministic failure",
                "return_code": 1,
            },
        )

    def test_failed_directories_are_moved_append_only_and_trigger_three_retry_skip(self):
        receipts = []
        for attempt in range(1, 4):
            self.create_failure(f"partial-{attempt}")
            receipt = queue.archive_training_failure(self.config, self.entry)
            receipts.append(receipt)
            self.assertFalse(self.training_job.exists())
            archived = self.archive_root / f"attempt_{attempt:03d}/training_job/partial.bin"
            self.assertEqual(archived.read_text(encoding="utf-8"), f"partial-{attempt}")
        self.assertEqual([receipt["attempt"] for receipt in receipts], [1, 2, 3])
        self.assertEqual(len({receipt["error_signature"] for receipt in receipts}), 1)
        archives = queue.training_archives(self.config, self.entry)
        self.assertEqual(len(archives), 3)
        with (
            mock.patch.object(queue, "training_archives", return_value=archives),
            mock.patch.object(queue, "readout_failures", return_value=[]),
            mock.patch.object(queue, "action_failures", return_value=[]),
        ):
            skip = queue.terminal_skip_cause(self.config, self.entry)
        self.assertEqual(skip["source"], "training_failure_archive")
        self.assertEqual(skip["error_type"], "CudaRuntimeError")

    def test_incomplete_archive_is_resumed_without_overwrite(self):
        self.create_failure()
        real_replace = queue.os.replace

        def interrupt_final_rename(source, destination):
            source_path = Path(source)
            destination_path = Path(destination)
            if source_path.name.endswith(".incomplete") and destination_path.name == "attempt_001":
                raise OSError("simulated interruption before final archive publication")
            return real_replace(source, destination)

        with mock.patch.object(queue.os, "replace", side_effect=interrupt_final_rename):
            with self.assertRaises(OSError):
                queue.archive_training_failure(self.config, self.entry)
        self.assertFalse(self.training_job.exists())
        self.assertTrue((self.archive_root / "attempt_001.incomplete/training_job/partial.bin").is_file())
        result = queue.archive_training_failure(self.config, self.entry)
        self.assertEqual(result["state"], "ARCHIVED")
        self.assertTrue((self.archive_root / "attempt_001/training_job/partial.bin").is_file())
        self.assertFalse((self.archive_root / "attempt_001.incomplete").exists())

    def test_third_failed_canonical_is_archived_before_action_failure_skip(self):
        for attempt in range(1, 3):
            self.create_failure(f"preserved-{attempt}")
            queue.archive_training_failure(self.config, self.entry)
        self.create_failure("preserved-3")
        premature_skip = {
            "source": "orchestrator_action_failures",
            "error_signature": "c" * 64,
            "error_type": "ExternalActionError",
            "attempts": [],
        }
        with (
            mock.patch.object(queue, "verify_readout_complete", return_value=None),
            mock.patch.object(queue, "terminal_skip_cause", return_value=premature_skip) as skip,
        ):
            result = queue.inspect_pipeline(self.config, self.entry)
        self.assertEqual(result["action"], "ARCHIVE_TRAINING")
        self.assertEqual(result["state"], "TRAINING_FAILED")
        skip.assert_not_called()
        queue.archive_training_failure(self.config, self.entry)
        self.assertFalse(self.training_job.exists())
        self.assertTrue((self.archive_root / "attempt_003/training_job/partial.bin").is_file())

    def test_stale_training_materialization_is_archived_not_launched(self):
        self.training_job.mkdir(parents=True)
        write_json(
            self.training_job / "materialization.json",
            {
                "schema": self.fake_module.MATERIALIZATION_SCHEMA,
                "status": "PASSED",
                "building_id": self.entry["building_id"],
                "arm": self.entry["arm"],
                "replicate": self.entry["replicate"],
                "profile": "full",
                "git": {
                    "branch": "exp/fusion-w1",
                    "head": "1" * 40,
                    "files": [],
                },
            },
        )
        with mock.patch.object(queue, "verify_readout_complete", return_value=None):
            result = queue.inspect_pipeline(self.config, self.entry)
        self.assertEqual(result["action"], "ARCHIVE_TRAINING")
        self.assertEqual(
            result["orphan_reason"], "training_binding_does_not_match_runtime_head"
        )
        self.assertIn("training materialization/current HEAD", result["binding_error"])


class TerminalPublicationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.original_repo = queue.REPO
        queue.REPO = self.root
        self.config = {"outputs": {"stage_records": "queue/stage_records"}}
        self.smoke = entry(0, "smoke_barrier", 1, "DEBY_LOD2_42364609")
        self.reused = entry(
            1,
            "aprime_r1",
            1,
            "DEBY_LOD2_42364609",
            reuse=True,
        )
        self.source = self.root / "readout/complete.json"
        write_json(self.source, {"schema": "readout.complete", "state": "COMPLETE"})
        self.source_record = queue.file_record(self.source)
        smoke_path = queue.stage_record_path(self.config, self.smoke)
        queue.exclusive_json(
            smoke_path,
            {
                "schema": queue.STAGE_RECORD_SCHEMA,
                "status": "MEASURED",
                "created_at": "2026-07-26T00:00:00+00:00",
                "entry": self.smoke,
                "source": "readout_complete",
                "source_receipts": [self.source_record],
                "error_type": None,
                "error_signature": None,
                "same_signature_attempts": None,
                "smoke_reuse": None,
                "partial_results_reviewable": True,
                "interpretation_or_verdict": None,
            },
        )

    def tearDown(self):
        queue.REPO = self.original_repo
        self.temporary.cleanup()

    def test_aprime_r1_job1_reuses_exact_smoke_receipt_hash(self):
        recommended = {
            "action": "RECORD_MEASURED",
            "state": "MEASURED",
            "entry": self.reused,
            "pipeline": {
                "state": "MEASURED",
                "action": "RECORD_MEASURED",
                "readout_complete": self.source_record,
            },
        }
        with (
            mock.patch.object(queue, "next_action", return_value=recommended),
            mock.patch.object(
                queue, "load_plan", return_value={"entries": [self.smoke, self.reused]}
            ),
            mock.patch.object(queue, "append_event", return_value={"sequence": 1}),
            mock.patch.object(queue, "publish_status", return_value={}),
        ):
            result = queue.record_terminal(self.config, self.reused)
        self.assertEqual(result["status"], "MEASURED")
        self.assertEqual(result["source_receipts"], [self.source_record])
        self.assertEqual(
            result["smoke_reuse"]["identical_readout_complete_receipt"],
            self.source_record,
        )
        self.assertTrue(
            (self.root / "queue/stage_records/stage_01_aprime_r1").is_dir()
        )

    def test_readout_complete_from_older_head_is_rejected(self):
        candidate = self.smoke
        identity = {
            "building_id": candidate["building_id"],
            "arm": candidate["arm"],
            "replicate": candidate["replicate"],
            "profile": "full",
        }
        job = self.root / "readout/job"
        attempt = job / "attempts/attempt_001"
        attempt.mkdir(parents=True)
        primary = attempt / "primary/score.json"
        legacy = attempt / "legacy_alpha/score.json"
        write_json(primary, {"state": "MEASURED"})
        write_json(legacy, {"state": "NOT_ASSEMBLED"})
        old_lock = {
            "branch": "exp/fusion-w1",
            "head": "0" * 40,
            "implementation_files": [],
        }
        current_lock = {**old_lock, "head": "1" * 40}
        write_json(
            attempt / "attempt.json",
            {
                "schema": "readout.attempt.v1",
                "state": "STARTED",
                "attempt": 1,
                "identity": identity,
                "git_lock": old_lock,
                "locked_inputs": {},
            },
        )
        write_json(
            job / "complete.json",
            {
                "schema": "readout.complete.v1",
                "state": "COMPLETE",
                "identity": identity,
                "attempt": 1,
                "successful_attempt": queue.relative(attempt),
                "attempt_materialization": queue.file_record(attempt / "attempt.json"),
                "primary": {
                    "state": "MEASURED",
                    "eligible_for_preregistered_judgment": True,
                    "receipt": queue.file_record(primary),
                },
                "legacy_alpha": {
                    "state": "NOT_ASSEMBLED",
                    "eligible_for_preregistered_judgment": False,
                    "receipt": queue.file_record(legacy),
                },
            },
        )
        fake_module = types.SimpleNamespace(
            COMPLETE_SCHEMA="readout.complete.v1",
            ATTEMPT_SCHEMA="readout.attempt.v1",
            verify_git_runtime=lambda _config: current_lock,
            verify_locked_inputs=lambda _config: {},
        )
        with mock.patch.object(
            queue, "readout_job_path", return_value=(fake_module, {}, job)
        ):
            with self.assertRaisesRegex(queue.UnattendedError, "readout attempt/current HEAD"):
                queue.verify_readout_complete({}, candidate)


class PublicationAndWrapperTests(unittest.TestCase):
    def test_outcome_status_taxonomy(self):
        self.assertEqual(queue._outcome_status("MEASURED"), "MEASURED")
        self.assertEqual(queue._outcome_status("SKIPPED"), "SKIPPED")
        self.assertEqual(queue._outcome_status("TRAINING_FAILED"), "FAILED")
        self.assertEqual(queue._outcome_status("READOUT_FAILED"), "FAILED")
        self.assertEqual(queue._outcome_status("MATERIALIZED"), "MISSING")

    def test_external_error_signature_ignores_attempt_specific_log_content(self):
        candidate = entry(1, "aprime_r1", 2, "DEBY_LOD2_42364659")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            original_repo = queue.REPO
            queue.REPO = root
            first_log = root / "logs/first.log"
            second_log = root / "logs/second.log"
            first_log.parent.mkdir(parents=True)
            first_log.write_text("timestamp=one attempt=1\nCUDA failed\n", encoding="utf-8")
            second_log.write_text("timestamp=two attempt=2\nCUDA failed\n", encoding="utf-8")
            config = {
                "outputs": {
                    "action_failures": "queue/action_failures",
                    "stage_records": "queue/stage_records",
                }
            }
            try:
                with (
                    mock.patch.object(queue, "append_event", return_value={"sequence": 1}),
                    mock.patch.object(queue, "publish_status", return_value={}),
                ):
                    first = queue.record_action_failure(
                        config,
                        candidate,
                        action="MATERIALIZE_TRAINING",
                        error_type="ExternalActionError",
                        message="external action exited nonzero",
                        return_code=1,
                        log_path=first_log,
                    )
                    second = queue.record_action_failure(
                        config,
                        candidate,
                        action="MATERIALIZE_TRAINING",
                        error_type="ExternalActionError",
                        message="external action exited nonzero",
                        return_code=1,
                        log_path=second_log,
                    )
            finally:
                queue.REPO = original_repo
        self.assertNotEqual(first["log"]["sha256"], second["log"]["sha256"])
        self.assertEqual(first["error_signature"], second["error_signature"])
        self.assertNotEqual(
            first["error_signature_basis"]["log_sha256"],
            second["error_signature_basis"]["log_sha256"],
        )

    def test_wrapper_is_serial_unattended_and_uses_locked_clis(self):
        source = WRAPPER_PATH.read_text(encoding="utf-8")
        self.assertNotRegex(source, r"\btimeout\b")
        self.assertNotRegex(source, r"read\s+-p")
        self.assertNotIn("06:30", source)
        self.assertIn('bash "$TRAINING_WRAPPER" materialize', source)
        self.assertIn('bash "$TRAINING_WRAPPER" launch', source)
        self.assertIn('bash "$READOUT_WRAPPER" one "$building_id" "$arm" "$replicate"', source)
        self.assertNotRegex(source, re.compile(r"(^|[; ])&(\s|$)", re.MULTILINE))
        self.assertIn("flock -n 9", source)
        self.assertIn("while true; do", source)

    def test_queue_code_has_no_delete_or_overwrite_operations(self):
        driver = DRIVER_PATH.read_text(encoding="utf-8")
        wrapper = WRAPPER_PATH.read_text(encoding="utf-8")
        self.assertNotRegex(driver, r"\.(unlink|rmdir)\(")
        self.assertNotIn("shutil.rmtree", driver)
        self.assertNotRegex(wrapper, r"(^|\s)rm\s", re.MULTILINE)
        self.assertIn("os.replace(training_job, nested)", driver)
        self.assertIn('path.open("x"', driver)

    def test_generated_receipt_contracts_forbid_scientific_verdict_values(self):
        source = DRIVER_PATH.read_text(encoding="utf-8")
        self.assertNotIn('"interpretation_or_verdict": "', source)
        self.assertNotIn('"scientific_verdict": "', source)
        self.assertGreaterEqual(source.count('"interpretation_or_verdict": None'), 8)


if __name__ == "__main__":
    unittest.main()
