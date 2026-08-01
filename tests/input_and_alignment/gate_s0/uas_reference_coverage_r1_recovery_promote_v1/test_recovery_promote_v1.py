import inspect
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts.input_and_alignment.gate_s0.uas_reference_coverage_r1_recovery_promote_v1 import (
    run_recovery_promote_v1 as recovery,
)
from scripts.input_and_alignment.gate_s0.uas_reference_coverage_r1_v1 import (
    run_uas_reference_coverage_r1 as historical,
)


class CheckpointRecordRegressionTests(unittest.TestCase):
    def test_write_then_fresh_instance_records_are_exact(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = historical.Checkpoints(root, "operation")
            written = first.write(10, "stage", {"value": 1})
            second = historical.Checkpoints(root, "operation")
            self.assertEqual(first.records, second.records)
            self.assertEqual(written, second.records[0])

    def test_historical_six_record_sequence_survives_reload(self):
        stages = [
            (0, "runtime_control"),
            (10, "reference_candidate_frozen"),
            (20, "eligibility_candidate"),
            (30, "group_split_candidate"),
            (40, "claim_scope"),
            (100, "technical_summary"),
        ]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = historical.Checkpoints(root, "historical-operation")
            for ordinal, stage in stages:
                first.write(ordinal, stage, {"stage": stage})
            expected = list(first.records)
            observed = historical.Checkpoints(root, "historical-operation").records
            self.assertEqual(expected, observed)

    def test_record_has_historical_digest_method(self):
        record = historical.Checkpoints._record(1, "x", Path("/tmp/x"), 2, "a" * 64)
        self.assertEqual(record["digest_method"], "same_stream_as_add_once_serialization")

    def test_record_field_set_is_stable(self):
        record = historical.Checkpoints._record(1, "x", Path("/tmp/x"), 2, "a" * 64)
        self.assertEqual(set(record), {"ordinal", "stage", "path", "bytes", "sha256", "digest_method"})


class RecoveryContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cfg = recovery.config()

    def test_config_identity_and_null_verdict(self):
        self.assertEqual(self.cfg["task_id"], recovery.TASK)
        self.assertEqual(self.cfg["handoff_id"], recovery.HANDOFF)
        self.assertIsNone(self.cfg["scientific_verdict"])

    def test_historical_ledger_is_exactly_bound(self):
        ledger = self.cfg["historical"]["execution_ledger"]
        self.assertEqual(ledger["bytes"], 11268)
        self.assertEqual(ledger["sha256"], "cdf41594f1c218aa1c60206b9a6c070e5222f00da8149796151b15385f1f6bec")

    def test_recovery_namespace_is_disjoint(self):
        old = Path(self.cfg["historical"]["output_namespace"])
        new = Path(self.cfg["recovery_output_namespace"])
        self.assertNotEqual(old, new)
        self.assertNotIn(old, new.parents)
        self.assertNotIn(new, old.parents)

    def test_expected_scope_stays_pilot_only(self):
        expected = self.cfg["historical"]["expected"]
        self.assertEqual(expected["e_paired_candidate_count"], 72)
        self.assertEqual(expected["independent_group_count"], 9)
        self.assertEqual(expected["claim_scope_status"], "PILOT_ONLY_REFERENCE_SCOPE")
        self.assertEqual(expected["recommended_gate_action"], "BLOCKED_REFERENCE_COVERAGE_OR_INDEPENDENCE")

    def test_verify_entry_point_has_no_scientific_capture_or_attempt_start(self):
        source = inspect.getsource(recovery.verify_promote)
        self.assertNotIn("capture_exact(", source)
        self.assertNotIn(".start(", source)

    def test_acceptance_requires_exactly_one_bound_artifact(self):
        source = inspect.getsource(recovery.validate_acceptance)
        self.assertIn("if len(matching) != 1", source)
        self.assertIn('get("level") != "artifact_verified"', source)
        self.assertIn('get("required_for_task")', source)

    def test_actual_verify_entry_fast_path_never_calls_source_accessors(self):
        image = "sha256:" + "a" * 64
        sentinel = {"status": "COMPLETED"}
        with tempfile.TemporaryDirectory() as directory, mock.patch.object(recovery, "config", return_value=self.cfg), mock.patch.object(
            recovery, "assert_historical_binding"
        ), mock.patch.object(recovery, "assert_current_source", return_value={}), mock.patch.object(
            recovery, "validate_acceptance", return_value={"project_image_id": image}
        ), mock.patch.object(recovery, "artifact_paths", return_value=(Path(directory) / "old", Path(directory) / "new")), mock.patch.object(
            recovery, "recover_invocation_pending", return_value={"recovery_namespace": [], "promotion_paths": []}
        ), mock.patch.object(recovery, "git", return_value=""), mock.patch.object(
            recovery, "completed_fast_path", return_value=sentinel
        ), mock.patch.object(historical, "capture_exact", side_effect=AssertionError("forbidden")), mock.patch.object(
            historical.SourceAttempts, "start", side_effect=AssertionError("forbidden")
        ):
            self.assertIs(recovery.verify_promote("accepted", Path(directory), image), sentinel)

    def test_config_contains_no_scientific_input_path_list(self):
        self.assertNotIn("inputs", self.cfg["historical"])

    def test_expected_result_assertion_passes_exact_values(self):
        expected = self.cfg["historical"]["expected"]
        summary = {
            "u_target_count": expected["u_target_count"],
            "e_paired_candidate_count": expected["e_paired_candidate_count"],
            "independent_group_count": expected["independent_group_count"],
            "split_building_counts": {"held_out": expected["held_out_building_count"]},
            "split_group_counts": {"held_out": expected["held_out_group_count"]},
            "claim_scope_status": expected["claim_scope_status"],
            "recommended_gate_action": expected["recommended_gate_action"],
        }
        validation = {
            "source_attempts": {
                "attempt_counts": expected["attempt_counts"],
                "per_source_read_digest_accounting": [
                    {
                        "known_successful_full_read_digest_passes": 1,
                        "full_read_digest_passes_min": 1,
                        "full_read_digest_passes_max": 1,
                    }
                ],
            }
        }
        recovery.assert_expected(summary, validation, self.cfg)

    def test_changed_count_fails_closed(self):
        expected = self.cfg["historical"]["expected"]
        summary = {
            "u_target_count": 199,
            "e_paired_candidate_count": 73,
            "independent_group_count": 9,
            "split_building_counts": {"held_out": 10},
            "split_group_counts": {"held_out": 2},
            "claim_scope_status": expected["claim_scope_status"],
            "recommended_gate_action": expected["recommended_gate_action"],
        }
        validation = {"source_attempts": {"attempt_counts": expected["attempt_counts"], "per_source_read_digest_accounting": []}}
        with self.assertRaisesRegex(RuntimeError, "frozen result mismatch"):
            recovery.assert_expected(summary, validation, self.cfg)

    def test_fast_path_rejects_nonzero_source_reads(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            old = self.cfg["historical"]
            ledger = {
                "schema": "jointbuildgs.gate_s0_uas_reference_coverage_r1_recovery_ledger.v1",
                "task_id": recovery.TASK,
                "handoff_id": recovery.HANDOFF,
                "status": "COMPLETED",
                "source_commit": "accepted",
                "project_image_id": "sha256:" + "a" * 64,
                "historical_execution_ledger": {
                    "bytes": old["execution_ledger"]["bytes"],
                    "sha256": old["execution_ledger"]["sha256"],
                },
                "historical_operation_id": old["operation_id"],
                "frozen_result": old["expected"],
                "scientific_source_reads_or_hashes": 1,
                "scientific_recalculations": 0,
                "scientific_verdict": None,
                "promoted_git_records": {},
            }
            recovery.add_once(root / "control/recovery_ledger_v1.json", recovery.canonical_bytes(ledger))
            with self.assertRaisesRegex(RuntimeError, "source/recalculation accounting"):
                recovery.completed_fast_path(root, self.cfg, "accepted", "sha256:" + "a" * 64)

    def test_fast_path_rejects_empty_promotion_record_set(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            old = self.cfg["historical"]
            ledger = {
                "schema": "jointbuildgs.gate_s0_uas_reference_coverage_r1_recovery_ledger.v1",
                "task_id": recovery.TASK,
                "handoff_id": recovery.HANDOFF,
                "status": "COMPLETED",
                "source_commit": "accepted",
                "project_image_id": "sha256:" + "a" * 64,
                "historical_execution_ledger": {
                    "bytes": old["execution_ledger"]["bytes"],
                    "sha256": old["execution_ledger"]["sha256"],
                },
                "historical_operation_id": old["operation_id"],
                "frozen_result": old["expected"],
                "scientific_source_reads_or_hashes": 0,
                "scientific_recalculations": 0,
                "scientific_verdict": None,
                "promoted_git_records": {},
            }
            recovery.add_once(root / "control/recovery_ledger_v1.json", recovery.canonical_bytes(ledger))
            with self.assertRaisesRegex(RuntimeError, "record key set mismatch"):
                recovery.completed_fast_path(root, self.cfg, "accepted", "sha256:" + "a" * 64)

    def test_stale_pending_is_quarantined_and_reported(self):
        with tempfile.TemporaryDirectory() as directory, mock.patch.object(historical, "PROMOTION_PATHS", ()):
            root = Path(directory)
            pending = root / "control/.recovery_ledger_v1.json.pending"
            pending.parent.mkdir(parents=True)
            pending.write_bytes(b"incomplete")
            recovered = recovery.recover_invocation_pending(root)
            self.assertFalse(pending.exists())
            self.assertEqual(recovered["recovery_namespace"][0]["action"], "QUARANTINED_INCOMPLETE")

    def test_forbidden_accessors_can_be_guarded_without_affecting_assertion(self):
        expected = self.cfg["historical"]["expected"]
        summary = {
            "u_target_count": 199,
            "e_paired_candidate_count": 72,
            "independent_group_count": 9,
            "split_building_counts": {"held_out": 10},
            "split_group_counts": {"held_out": 2},
            "claim_scope_status": "PILOT_ONLY_REFERENCE_SCOPE",
            "recommended_gate_action": "BLOCKED_REFERENCE_COVERAGE_OR_INDEPENDENCE",
        }
        validation = {
            "source_attempts": {
                "attempt_counts": expected["attempt_counts"],
                "per_source_read_digest_accounting": [{
                    "known_successful_full_read_digest_passes": 1,
                    "full_read_digest_passes_min": 1,
                    "full_read_digest_passes_max": 1,
                }],
            }
        }
        with mock.patch.object(historical, "capture_exact", side_effect=AssertionError("forbidden")), mock.patch.object(
            historical.SourceAttempts, "start", side_effect=AssertionError("forbidden")
        ):
            recovery.assert_expected(summary, validation, self.cfg)

    def test_report_preserves_null_gate_and_verdict(self):
        summary = {
            "e_paired_candidate_count": 72,
            "u_target_count": 199,
            "independent_group_count": 9,
            "split_building_counts": {"held_out": 10},
            "split_group_counts": {"held_out": 2},
            "claim_scope_status": "PILOT_ONLY_REFERENCE_SCOPE",
            "recommended_gate_action": "BLOCKED_REFERENCE_COVERAGE_OR_INDEPENDENCE",
        }
        report = recovery.report_bytes(summary).decode()
        self.assertIn("Gate S0 decision: `null`", report)
        self.assertIn("scientific_verdict: `null`", report)
        self.assertIn("does not authorize any P2 performance", report)


if __name__ == "__main__":
    unittest.main()
