#!/usr/bin/env python3
"""Contract tests for the 20-job A-prime continuation (no experiments)."""

from __future__ import annotations

import copy
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import types
import unittest
from unittest import mock


REPO = Path(__file__).resolve().parents[2]
DRIVER_PATH = REPO / "phases/p2-gsjso/scripts/fusion_w1/fusion_w1_aprime_queue_continuation_20260727.py"
CONFIG_PATH = REPO / "phases/p2-gsjso/configs/fusion_w1/fusion_w1_aprime_queue_continuation_20260727.json"
WRAPPER_PATH = REPO / "phases/p2-gsjso/scripts/fusion_w1/run_fusion_w1_aprime_queue_continuation_20260727.sh"
CACHEFIX_WRAPPER = "phases/p2-gsjso/scripts/fusion_w1/run_fusion_w1_aprime_readout_cachefix_20260727.sh"


def load_driver():
    spec = importlib.util.spec_from_file_location("aprime_continuation_under_test", DRIVER_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


controller = load_driver()
queue = controller.queue
config = controller.load_config(CONFIG_PATH)


class PlanContractTests(unittest.TestCase):
    def test_exact_remaining_plan_is_eight_plus_nine_plus_three(self):
        rows = controller.build_plan(config)
        self.assertEqual(len(rows), 20)
        self.assertEqual(
            len({(row["building_id"], row["arm"], row["replicate"]) for row in rows}),
            20,
        )
        self.assertEqual(
            {order: sum(row["stage_order"] == order for row in rows) for order in (1, 2, 3)},
            {1: 8, 2: 9, 3: 3},
        )
        self.assertEqual([row["global_entry_order"] for row in rows], list(range(1, 21)))
        self.assertTrue(all(not row["smoke_barrier_entry"] for row in rows))
        self.assertTrue(all(not row["reuse_completed_smoke"] for row in rows))

    def test_first_job_is_second_source_aprime_r1_entry(self):
        first = controller.build_plan(config)[0]
        self.assertEqual(
            (
                first["building_id"],
                first["arm"],
                first["replicate"],
                first["stage_order"],
                first["stage_entry_order"],
            ),
            ("DEBY_LOD2_42364659", "Aprime", "r1", 1, 2),
        )

    def test_committed_continuation_lock_matches_all_twenty_jobs(self):
        rows = controller.build_plan(config)
        record = controller.verify_continuation_lock(config, rows)
        self.assertEqual(
            record["sha256"],
            "e1076ce7bfef0e66c496910dcfe2e52509a2170cfe49a128ded2c07d3dce8137",
        )
        self.assertEqual(record, queue.file_record(REPO / record["path"]))

    def test_only_external_smoke_and_its_duplicate_are_removed(self):
        source = controller._SOURCE_BUILD_PLAN(controller.source_config(config))
        remaining = controller.build_plan(config)
        source_keys = {
            (row["stage_order"], row["stage_entry_order"], row["building_id"], row["arm"], row["replicate"])
            for row in source
        }
        remaining_keys = {
            (row["stage_order"], row["stage_entry_order"], row["building_id"], row["arm"], row["replicate"])
            for row in remaining
        }
        self.assertEqual(
            source_keys - remaining_keys,
            {
                (0, 1, "DEBY_LOD2_42364609", "Aprime", "r1"),
                (1, 1, "DEBY_LOD2_42364609", "Aprime", "r1"),
            },
        )

    def test_first_next_is_materialize_for_42364659_on_empty_continuation(self):
        plan = {"schema": queue.PLAN_SCHEMA, "state": "ACTIVE", "entries": controller.build_plan(config)}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with (
                mock.patch.object(queue, "load_plan", return_value=plan),
                mock.patch.object(queue, "complete_path", return_value=root / "complete.json"),
                mock.patch.object(queue, "stage_stop_path", return_value=root / "stage_stop.json"),
                mock.patch.object(queue, "load_stage_record", return_value=None),
                mock.patch.object(
                    queue,
                    "inspect_pipeline",
                    return_value={"state": "MISSING", "action": "MATERIALIZE_TRAINING"},
                ),
            ):
                result = queue.next_action(config)
        self.assertEqual(result["action"], "MATERIALIZE_TRAINING")
        self.assertEqual(result["state"], "MISSING")
        self.assertEqual(
            (result["entry"]["building_id"], result["entry"]["arm"], result["entry"]["replicate"]),
            ("DEBY_LOD2_42364659", "Aprime", "r1"),
        )


class ExternalGateTests(unittest.TestCase):
    def test_source_terminal_and_smoke_completion_hashes_are_exact(self):
        qualitative = {
            "state": "COMPLETE",
            "components_true_n": 8,
            "placeholder_count": 0,
        }
        with mock.patch.object(
            controller, "verify_smoke_qualitative_publication", return_value=qualitative
        ):
            gate = controller.verify_external_smoke_gate(config)
        self.assertEqual(gate["state"], "PASSED")
        self.assertEqual(gate["successful_continuation_attempt"], 5)
        self.assertEqual(gate["primary_state"], "MEASURED")
        self.assertEqual(gate["artifact_count"], 46)
        self.assertFalse(gate["source_queue_rewritten"])
        self.assertEqual(gate["qualitative"], qualitative)
        self.assertEqual(
            gate["records"]["source_stage_stop"]["sha256"],
            "759569f0d5c3b33602e8f67fe3869a9007d936da6a438343cacd58412f7a0774",
        )
        self.assertEqual(
            gate["records"]["source_complete"]["sha256"],
            "7a37c2ea41edd194169415335f1412408748c24b9f0741d09372b04383f0b1e3",
        )
        self.assertEqual(
            gate["records"]["smoke_recovery_complete"]["sha256"],
            "9a2bfa641761e2081e49ef7b66f78ee468eb18f5c100951d8f957de4f3eed8c6",
        )
        self.assertEqual(
            gate["records"]["smoke_readout_job_complete"]["sha256"],
            "bfe7e8425efb43ee4ee14fd955c09412b76e8cce5ed58e0563fef03ec436360e",
        )

    def test_gate_rejects_a_changed_smoke_completion_hash(self):
        changed = copy.deepcopy(config)
        changed["source_queue"]["smoke_recovery_complete"]["sha256"] = "0" * 64
        with (
            mock.patch.object(controller, "verify_smoke_qualitative_publication"),
            self.assertRaises(queue.UnattendedError),
        ):
            controller.verify_external_smoke_gate(changed)

    def _run_strict_gate(self, *, component_value: bool = True):
        head = "a" * 40
        branch = "exp/fusion-w1"
        source_records = {
            "smoke_readout_job_complete": controller.exact_record(
                config["source_queue"]["smoke_readout_job_complete"], "test readout"
            ),
            "smoke_recovery_complete": controller.exact_record(
                config["source_queue"]["smoke_recovery_complete"], "test recovery"
            ),
        }
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory) / "qualitative_smoke"
            root = base / "publications" / head
            root.mkdir(parents=True)
            panel = root / "panel.png"
            opacity = root / "opacity.png"
            receipt_path = root / "receipt.json"
            panel.write_bytes(b"panel")
            opacity.write_bytes(b"opacity")
            receipt_path.write_text("{}\n", encoding="utf-8")
            generic = {"path": "artifact.bin", "sha256": "0" * 64, "bytes": 1}
            source_snapshot = {
                "readout_complete": source_records["smoke_readout_job_complete"],
                "recovery_complete": source_records["smoke_recovery_complete"],
                "other": generic,
            }
            legacy = {
                "panel": {**generic, "path": "legacy/panel.png"},
                "opacity": {**generic, "path": "legacy/opacity.png"},
                "receipt": {**generic, "path": "legacy/receipt.json"},
            }
            components = {name: True for name in controller.QUALITATIVE_COMPONENTS}
            components["opacity"] = component_value
            receipt = {
                "schema": config["qualitative_gate"]["receipt_schema"],
                "state": "COMPLETE",
                "execution_head": head,
                "execution_branch": branch,
                "publication_key": head,
                "components": components,
                "placeholder_count": 0,
                "scientific_verdict": None,
                "interpretation": None,
                "publication": {
                    "append_only": True,
                    "same_head_verify_only": True,
                    "overwrite_allowed": False,
                    "partial_publication_allowed": False,
                    "receipt_written_after_artifact_validation": True,
                    "receipt_published_last": True,
                    "source_inputs_unchanged": True,
                    "legacy_top_level_unchanged": True,
                },
                "source_snapshot_before": source_snapshot,
                "source_snapshot_after": source_snapshot,
                "legacy_top_level_before": legacy,
                "legacy_top_level_after": legacy,
                "outputs": {
                    "panel": {**generic, "path": "strict/panel.png"},
                    "opacity": {**generic, "path": "strict/opacity.png"},
                },
            }
            strict_file = {
                **generic,
                "path": "implementation.py",
                "git_blob": "blob-id",
                "tracked_at_head": True,
                "worktree_matches_head": True,
            }
            strict = {
                "head": head,
                "branch": branch,
                "publication_key": head,
                "files": [strict_file],
                "all_tracked_at_head": True,
                "all_worktree_match_head": True,
            }
            fake_module = types.SimpleNamespace(
                load_config=lambda _path: {},
                strict_head_context=lambda _config: strict,
                verify_strict_publication=lambda _config, context: receipt,
                strict_publication_paths=lambda _config, _head: (
                    root,
                    panel,
                    opacity,
                    receipt_path,
                ),
            )
            original_repo_path = queue.repo_path

            def repo_path(value):
                if value == config["qualitative_gate"]["root"]:
                    return base
                if value in {
                    config["qualitative_gate"]["config"],
                    config["qualitative_gate"]["driver"],
                }:
                    return Path(directory) / Path(value).name
                return original_repo_path(value)

            def git(*arguments, **_kwargs):
                if arguments == ("rev-parse", "HEAD"):
                    return types.SimpleNamespace(stdout=head + "\n")
                if arguments == ("branch", "--show-current"):
                    return types.SimpleNamespace(stdout=branch + "\n")
                if arguments == ("rev-parse", f"{head}:implementation.py"):
                    return types.SimpleNamespace(stdout="blob-id\n")
                raise AssertionError(arguments)

            with (
                mock.patch.object(queue, "repo_path", side_effect=repo_path),
                mock.patch.object(queue, "load_module", return_value=fake_module),
                mock.patch.object(queue, "git", side_effect=git),
                mock.patch.object(queue, "verify_record", return_value=Path("verified")),
                mock.patch.object(
                    queue,
                    "file_record",
                    return_value={"path": "strict/receipt.json", "sha256": "1" * 64, "bytes": 3},
                ),
            ):
                return controller.verify_smoke_qualitative_publication(config, source_records)

    def test_current_head_qualitative_gate_binds_eight_components_and_artifacts(self):
        result = self._run_strict_gate()
        self.assertEqual(result["components_true_n"], 8)
        self.assertEqual(result["placeholder_count"], 0)
        self.assertTrue(result["source_snapshot_unchanged"])
        self.assertTrue(result["legacy_top_level_unchanged"])

    def test_current_head_qualitative_gate_rejects_false_component(self):
        with self.assertRaises(queue.UnattendedError):
            self._run_strict_gate(component_value=False)

    def test_qualitative_gate_uses_runtime_full_head_not_legacy_receipt_sha(self):
        serialized = json.dumps(config, sort_keys=True)
        self.assertNotIn("c3fa7de587a90912a6e31f668367a747328afb6a3b8f6150fbac2f064e699dda", serialized)
        self.assertEqual(config["qualitative_gate"]["publication_key"], "current_full_git_head")
        source = DRIVER_PATH.read_text(encoding="utf-8")
        self.assertIn("strict_head_context", source)
        self.assertIn("verify_strict_publication", source)
        for name in (
            "qualitative_config",
            "qualitative_driver",
            "qualitative_wrapper",
            "qualitative_test",
        ):
            record = config["locked_inputs"][name]
            self.assertEqual(queue.sha256_file(REPO / record["path"]), record["sha256"])

    def test_source_queue_is_terminal_but_not_used_as_continuation_root(self):
        source_complete = json.loads(
            (REPO / config["source_queue"]["source_complete"]["path"]).read_text(encoding="utf-8")
        )
        self.assertEqual(source_complete["state"], "STOPPED_SMOKE_BARRIER_NOT_MEASURED")
        self.assertNotEqual(config["outputs"]["root"], "phases/p2-gsjso/runs/fusion_w1/20260726_fusion_w1_aprime/unattended_queue")
        self.assertTrue(config["outputs"]["root"].endswith("/unattended_queue_continuation_v2"))


class InheritedFailureContractTests(unittest.TestCase):
    @staticmethod
    def terminal(building: str, status: str, error_type: str | None = None):
        return ({"building_id": building}, {"status": status, "error_type": error_type})

    def test_three_same_job_signatures_trigger_skip_evidence(self):
        failures = [
            {"payload": {"error_signature": "same", "error_type": "PermissionError"}}
            for _ in range(3)
        ]
        self.assertEqual(
            queue.three_same_signature(failures, signature_field="error_signature"),
            (True, "same", "PermissionError"),
        )

    def test_three_consecutive_building_skips_stop_stage(self):
        records = [
            self.terminal("b1", "SKIPPED", "PermissionError"),
            self.terminal("b2", "SKIPPED", "PermissionError"),
            self.terminal("b3", "SKIPPED", "PermissionError"),
        ]
        stop = queue.consecutive_skip_stop(records)
        self.assertIsNotNone(stop)
        self.assertEqual(stop["reason_code"], "SAME_ERROR_TYPE_THREE_CONSECUTIVE_BUILDINGS")
        self.assertEqual(stop["consecutive_buildings"], ["b1", "b2", "b3"])

    def test_measurement_resets_cross_building_skip_window(self):
        records = [
            self.terminal("b1", "SKIPPED", "PermissionError"),
            self.terminal("b2", "MEASURED"),
            self.terminal("b3", "SKIPPED", "PermissionError"),
            self.terminal("b4", "SKIPPED", "PermissionError"),
        ]
        self.assertIsNone(queue.consecutive_skip_stop(records))

    def test_recovery_receipt_projection_is_the_imported_binding(self):
        self.assertIs(queue.verify_training_binding, controller.recovery.compatible_verify_training_binding)

    def test_three_identical_archive_action_failures_skip_before_archive_retry(self):
        failures = [
            {
                "receipt": {"path": f"failure-{index}.json", "sha256": "0" * 64, "bytes": 1},
                "payload": {
                    "action": "ARCHIVE_TRAINING",
                    "error_signature": "archive-same",
                    "error_type": "ArchiveError",
                },
            }
            for index in range(3)
        ]
        with (
            mock.patch.object(queue, "action_failures", return_value=failures),
            mock.patch.object(controller, "_SOURCE_INSPECT_PIPELINE") as inherited,
        ):
            result = controller.inspect_pipeline(config, {"building_id": "b"})
        inherited.assert_not_called()
        self.assertEqual(result["action"], "RECORD_SKIPPED")
        self.assertEqual(result["skip"]["source"], "orchestrator_archive_action_failures")
        self.assertEqual(len(result["skip"]["attempts"]), 3)

    def test_two_archive_action_failures_still_delegate_to_inherited_inspector(self):
        failures = [
            {
                "receipt": {"path": f"failure-{index}.json", "sha256": "0" * 64, "bytes": 1},
                "payload": {
                    "action": "ARCHIVE_TRAINING",
                    "error_signature": "archive-same",
                    "error_type": "ArchiveError",
                },
            }
            for index in range(2)
        ]
        expected = {"state": "TRAINING_FAILED", "action": "ARCHIVE_TRAINING"}
        with (
            mock.patch.object(queue, "action_failures", return_value=failures),
            mock.patch.object(controller, "_SOURCE_INSPECT_PIPELINE", return_value=expected),
        ):
            self.assertEqual(controller.inspect_pipeline(config, {"building_id": "b"}), expected)

    def test_readout_complete_revalidates_unique_ledger_and_no_final_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            attempt_root = Path(directory) / "attempts/attempt_003"
            attempt_root.mkdir(parents=True)
            complete = Path(directory) / "complete.json"
            attempt = attempt_root / "attempt.json"
            artifact = attempt_root / "artifact.bin"
            for path in (complete, attempt, artifact):
                path.write_bytes(path.name.encode())
            payload = {
                "attempt": 3,
                "attempt_materialization": {"path": "attempt.json", "sha256": "a"},
                "artifact_count": 2,
                "artifact_ledger": [
                    {"path": "attempt.json", "sha256": "a"},
                    {"path": "artifact.bin", "sha256": "b"},
                ],
            }
            source = {
                "receipt": {"path": "complete.json", "sha256": "c"},
                "payload": payload,
            }

            def verified(record, _label):
                return {
                    "complete.json": complete,
                    "attempt.json": attempt,
                    "artifact.bin": artifact,
                }[record["path"]]

            with (
                mock.patch.object(controller, "_SOURCE_VERIFY_READOUT_COMPLETE", return_value=source),
                mock.patch.object(queue, "verify_record", side_effect=verified),
            ):
                result = controller.verify_readout_complete(config, {"building_id": "b"})
            self.assertTrue(result["artifact_ledger_verified"])
            self.assertTrue(result["artifact_ledger_exact_coverage_verified"])
            self.assertTrue(result["successful_attempt_failure_absent"])

    def test_readout_complete_rejects_duplicate_ledger_path(self):
        with tempfile.TemporaryDirectory() as directory:
            attempt_root = Path(directory) / "attempts/attempt_003"
            attempt_root.mkdir(parents=True)
            complete = Path(directory) / "complete.json"
            attempt = attempt_root / "attempt.json"
            artifact = attempt_root / "artifact.bin"
            for path in (complete, attempt, artifact):
                path.write_bytes(path.name.encode())
            record = {"path": "artifact.bin", "sha256": "b"}
            source = {
                "receipt": {"path": "complete.json", "sha256": "c"},
                "payload": {
                    "attempt": 3,
                    "attempt_materialization": {"path": "attempt.json", "sha256": "a"},
                    "artifact_count": 3,
                    "artifact_ledger": [
                        {"path": "attempt.json", "sha256": "a"},
                        record,
                        dict(record),
                    ],
                },
            }

            def verified(value, _label):
                return {
                    "complete.json": complete,
                    "attempt.json": attempt,
                    "artifact.bin": artifact,
                }[value["path"]]

            with (
                mock.patch.object(controller, "_SOURCE_VERIFY_READOUT_COMPLETE", return_value=source),
                mock.patch.object(queue, "verify_record", side_effect=verified),
                self.assertRaises(queue.UnattendedError),
            ):
                controller.verify_readout_complete(config, {"building_id": "b"})

    def test_readout_complete_rejects_failure_in_successful_attempt(self):
        with tempfile.TemporaryDirectory() as directory:
            attempt_root = Path(directory) / "attempts/attempt_003"
            attempt_root.mkdir(parents=True)
            complete = Path(directory) / "complete.json"
            attempt = attempt_root / "attempt.json"
            artifact = attempt_root / "artifact.bin"
            failure = attempt_root / "failure.json"
            for path in (complete, attempt, artifact, failure):
                path.write_bytes(path.name.encode())
            source = {
                "receipt": {"path": "complete.json", "sha256": "c"},
                "payload": {
                    "attempt": 3,
                    "attempt_materialization": {"path": "attempt.json", "sha256": "a"},
                    "artifact_count": 2,
                    "artifact_ledger": [
                        {"path": "attempt.json", "sha256": "a"},
                        {"path": "artifact.bin", "sha256": "b"},
                    ],
                },
            }

            def verified(value, _label):
                return {
                    "complete.json": complete,
                    "attempt.json": attempt,
                    "artifact.bin": artifact,
                }[value["path"]]

            with (
                mock.patch.object(controller, "_SOURCE_VERIFY_READOUT_COMPLETE", return_value=source),
                mock.patch.object(queue, "verify_record", side_effect=verified),
                self.assertRaises(queue.UnattendedError),
            ):
                controller.verify_readout_complete(config, {"building_id": "b"})

    def test_readout_complete_rejects_current_artifact_hash_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            attempt_root = Path(directory) / "attempts/attempt_003"
            attempt_root.mkdir(parents=True)
            complete = Path(directory) / "complete.json"
            attempt = attempt_root / "attempt.json"
            complete.write_bytes(b"complete")
            attempt.write_bytes(b"attempt")
            source = {
                "receipt": {"path": "complete.json", "sha256": "c"},
                "payload": {
                    "attempt": 3,
                    "attempt_materialization": {"path": "attempt.json", "sha256": "a"},
                    "artifact_count": 2,
                    "artifact_ledger": [
                        {"path": "attempt.json", "sha256": "a"},
                        {"path": "artifact.bin", "sha256": "bad"},
                    ],
                },
            }

            def verified(value, _label):
                if value["path"] == "artifact.bin":
                    raise queue.UnattendedError("artifact SHA drift")
                return {"complete.json": complete, "attempt.json": attempt}[value["path"]]

            with (
                mock.patch.object(controller, "_SOURCE_VERIFY_READOUT_COMPLETE", return_value=source),
                mock.patch.object(queue, "verify_record", side_effect=verified),
                self.assertRaises(queue.UnattendedError),
            ):
                controller.verify_readout_complete(config, {"building_id": "b"})

    def test_readout_complete_rejects_unlisted_file_added_after_finalize(self):
        with tempfile.TemporaryDirectory() as directory:
            attempt_root = Path(directory) / "attempts/attempt_003"
            attempt_root.mkdir(parents=True)
            complete = Path(directory) / "complete.json"
            attempt = attempt_root / "attempt.json"
            artifact = attempt_root / "artifact.bin"
            unlisted = attempt_root / "late.bin"
            for path in (complete, attempt, artifact, unlisted):
                path.write_bytes(path.name.encode())
            source = {
                "receipt": {"path": "complete.json", "sha256": "c"},
                "payload": {
                    "attempt": 3,
                    "attempt_materialization": {"path": "attempt.json", "sha256": "a"},
                    "artifact_count": 2,
                    "artifact_ledger": [
                        {"path": "attempt.json", "sha256": "a"},
                        {"path": "artifact.bin", "sha256": "b"},
                    ],
                },
            }

            def verified(value, _label):
                return {
                    "complete.json": complete,
                    "attempt.json": attempt,
                    "artifact.bin": artifact,
                }[value["path"]]

            with (
                mock.patch.object(controller, "_SOURCE_VERIFY_READOUT_COMPLETE", return_value=source),
                mock.patch.object(queue, "verify_record", side_effect=verified),
                self.assertRaisesRegex(queue.UnattendedError, "missing_from_ledger=.*late.bin"),
            ):
                controller.verify_readout_complete(config, {"building_id": "b"})

    def test_readout_complete_rejects_recursive_symlink(self):
        with tempfile.TemporaryDirectory() as directory:
            attempt_root = Path(directory) / "attempts/attempt_003"
            nested = attempt_root / "nested"
            nested.mkdir(parents=True)
            complete = Path(directory) / "complete.json"
            attempt = attempt_root / "attempt.json"
            artifact = attempt_root / "artifact.bin"
            for path in (complete, attempt, artifact):
                path.write_bytes(path.name.encode())
            (nested / "late-link").symlink_to(artifact)
            source = {
                "receipt": {"path": "complete.json", "sha256": "c"},
                "payload": {
                    "attempt": 3,
                    "attempt_materialization": {"path": "attempt.json", "sha256": "a"},
                    "artifact_count": 2,
                    "artifact_ledger": [
                        {"path": "attempt.json", "sha256": "a"},
                        {"path": "artifact.bin", "sha256": "b"},
                    ],
                },
            }

            def verified(value, _label):
                return {
                    "complete.json": complete,
                    "attempt.json": attempt,
                    "artifact.bin": artifact,
                }[value["path"]]

            with (
                mock.patch.object(controller, "_SOURCE_VERIFY_READOUT_COMPLETE", return_value=source),
                mock.patch.object(queue, "verify_record", side_effect=verified),
                self.assertRaisesRegex(queue.UnattendedError, "contains symlink: nested/late-link"),
            ):
                controller.verify_readout_complete(config, {"building_id": "b"})

    @unittest.skipUnless(hasattr(os, "mkfifo"), "FIFO requires os.mkfifo")
    def test_readout_complete_rejects_recursive_special_file_before_hashing(self):
        with tempfile.TemporaryDirectory() as directory:
            attempt_root = Path(directory) / "attempts/attempt_003"
            nested = attempt_root / "nested"
            nested.mkdir(parents=True)
            complete = Path(directory) / "complete.json"
            attempt = attempt_root / "attempt.json"
            artifact = attempt_root / "artifact.bin"
            for path in (complete, attempt, artifact):
                path.write_bytes(path.name.encode())
            os.mkfifo(nested / "late.fifo")
            source = {
                "receipt": {"path": "complete.json", "sha256": "c"},
                "payload": {
                    "attempt": 3,
                    "attempt_materialization": {"path": "attempt.json", "sha256": "a"},
                    "artifact_count": 2,
                    "artifact_ledger": [
                        {"path": "attempt.json", "sha256": "a"},
                        {"path": "artifact.bin", "sha256": "b"},
                    ],
                },
            }

            def verified(value, _label):
                return {
                    "complete.json": complete,
                    "attempt.json": attempt,
                    "artifact.bin": artifact,
                }[value["path"]]

            with (
                mock.patch.object(controller, "_SOURCE_VERIFY_READOUT_COMPLETE", return_value=source),
                mock.patch.object(queue, "verify_record", side_effect=verified),
                self.assertRaisesRegex(
                    queue.UnattendedError, "contains special file: nested/late.fifo"
                ),
            ):
                controller.verify_readout_complete(config, {"building_id": "b"})


class WrapperAndLockTests(unittest.TestCase):
    @staticmethod
    def run_wrapper_functions(script: str, *, environment: dict[str, str] | None = None):
        source = WRAPPER_PATH.read_text(encoding="utf-8")
        definitions = source.rsplit("\nverify_control_image\n", 1)[0]
        return subprocess.run(
            ["bash", "-c", definitions + "\n" + script],
            cwd=REPO,
            env=environment,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )

    def test_cachefix_readout_wrapper_is_locked_and_old_wrapper_not_executed(self):
        source = WRAPPER_PATH.read_text(encoding="utf-8")
        self.assertIn(f'READOUT_WRAPPER="{CACHEFIX_WRAPPER}"', source)
        self.assertIn('bash "$READOUT_WRAPPER" one "$building_id" "$arm" "$replicate"', source)
        self.assertNotIn('READOUT_WRAPPER="phases/p2-gsjso/scripts/fusion_w1/run_fusion_w1_aprime_readout_20260726.sh"', source)
        self.assertEqual(config["locked_inputs"]["readout_wrapper"]["path"], CACHEFIX_WRAPPER)

    def test_queue_inspection_uses_cachefix_config_and_its_locked_base_api(self):
        base, readout_config, config_path = controller.cachefix_readout_context(config)
        self.assertEqual(
            queue.relative(config_path),
            "phases/p2-gsjso/configs/fusion_w1/fusion_w1_aprime_readout_cachefix_20260727.json",
        )
        self.assertEqual(readout_config["task_id"], "FUS-W1-APRIME-READOUT-CACHEFIX-001")
        self.assertTrue(callable(base.job_dir))
        self.assertTrue(callable(base.verify_git_runtime))
        self.assertEqual(queue.readout_context, controller.cachefix_readout_context)

    def test_scientific_outputs_remain_canonical_and_queue_metadata_is_v2(self):
        training = json.loads(
            (REPO / config["locked_inputs"]["training_config"]["path"]).read_text(encoding="utf-8")
        )
        readout = json.loads(
            (REPO / config["locked_inputs"]["readout_config"]["path"]).read_text(encoding="utf-8")
        )
        self.assertEqual(
            training["outputs"]["training_root"],
            "phases/p2-gsjso/runs/fusion_w1/20260726_fusion_w1_aprime/training",
        )
        self.assertEqual(
            readout["outputs"]["root"],
            "phases/p2-gsjso/runs/fusion_w1/20260726_fusion_w1_aprime/readout",
        )
        self.assertEqual(
            config["outputs"]["root"],
            "phases/p2-gsjso/runs/fusion_w1/20260726_fusion_w1_aprime/unattended_queue_continuation_v2",
        )

    def test_gpu_one_is_fixed_without_environment_override(self):
        source = WRAPPER_PATH.read_text(encoding="utf-8")
        self.assertIn('GPU_INDEX="1"', source)
        self.assertIn('--gpu "$GPU_INDEX"', source)
        self.assertIn('env APRIME_READOUT_CACHEFIX_GPU_INDEX="$GPU_INDEX"', source)
        self.assertNotIn("APRIME_QUEUE_GPU_INDEX", source)
        self.assertEqual(config["resources"]["physical_gpu_choices"], [1])

    def test_gpu_guard_polls_unrelated_process_at_thirty_seconds(self):
        with tempfile.TemporaryDirectory() as directory:
            count = Path(directory) / "count"
            sleep_log = Path(directory) / "sleep.log"
            count.write_text("0\n", encoding="utf-8")
            environment = dict(os.environ)
            environment.update(COUNT_FILE=str(count), SLEEP_LOG=str(sleep_log))
            result = self.run_wrapper_functions(
                r'''
nvidia-smi() {
  case "$*" in
    *--query-gpu=uuid*) echo "GPU-fake" ;;
    *--query-compute-apps*)
      value="$(cat "$COUNT_FILE")"
      if [[ "$value" == "0" ]]; then
        echo "1, foreign-python"
        echo "1" >"$COUNT_FILE"
      fi
      ;;
    *) return 2 ;;
  esac
}
sleep() { echo "$1" >>"$SLEEP_LOG"; }
wait_for_gpu1_job_boundary "building|Aprime|r1|test"
''',
                environment=environment,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(sleep_log.read_text(encoding="utf-8").splitlines(), ["30"])
            self.assertIn("unrelated_compute", result.stderr)

    def test_gpu_guard_excludes_current_queue_process(self):
        result = self.run_wrapper_functions(
            r'''
nvidia-smi() {
  case "$*" in
    *--query-gpu=uuid*) echo "GPU-fake" ;;
    *--query-compute-apps*) echo "$QUEUE_SHELL_PID, queue-owned-python" ;;
    *) return 2 ;;
  esac
}
sleep() { echo "sleep must not run" >&2; return 99; }
wait_for_gpu1_job_boundary "building|Aprime|r1|owned"
'''
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("GPU boundary ready", result.stderr)
        self.assertNotIn("waiting", result.stderr)

    def test_job_boundary_and_every_cuda_action_are_separately_guarded(self):
        result = self.run_wrapper_functions(
            r'''
wait_for_gpu1_job_boundary() { echo "$1"; }
GPU_BOUNDARY_GUARDED_JOB_KEY=""
guard_job_and_cuda_action MATERIALIZE_TRAINING b Aprime r1
guard_job_and_cuda_action LAUNCH_TRAINING b Aprime r1
guard_job_and_cuda_action RUN_READOUT b Aprime r1
guard_job_and_cuda_action RUN_READOUT b Aprime r1
'''
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            result.stdout.splitlines(),
            [
                "b|Aprime|r1|job_boundary",
                "b|Aprime|r1|before_LAUNCH_TRAINING",
                "b|Aprime|r1|before_RUN_READOUT",
                "b|Aprime|r1|before_RUN_READOUT",
            ],
        )

    def test_training_launch_runs_cache_check_in_same_action_log_before_launch(self):
        source = WRAPPER_PATH.read_text(encoding="utf-8")
        function = source.split("launch_training_after_cache_check() {", 1)[1].split("\n}\n", 1)[0]
        self.assertLess(function.index('bash "$READOUT_WRAPPER" cache-check'), function.index('bash "$TRAINING_WRAPPER" launch'))
        self.assertIn('execute_action "$action"', source)
        self.assertIn('launch_training_after_cache_check "$building_id" "$arm" "$replicate"', source)

    def test_serial_no_prompt_no_cutoff_contract(self):
        source = WRAPPER_PATH.read_text(encoding="utf-8")
        self.assertEqual(source.count("run_queue()"), 1)
        self.assertIn("while true; do", source)
        self.assertNotIn("timeout ", source)
        self.assertNotRegex(source, r"read\s+-p")
        self.assertFalse(config["sequence_contract"]["user_prompts"])
        self.assertIsNone(config["sequence_contract"]["time_cutoff"])
        self.assertTrue(config["resources"]["training_foreground_one_at_a_time"])
        self.assertTrue(config["resources"]["readout_serial"])
        guard = config["resources"]["gpu_job_boundary_guard"]
        self.assertTrue(guard["before_each_cuda_action"])
        self.assertLessEqual(guard["poll_seconds"], 60)
        self.assertIsNone(guard["time_cutoff"])

    def test_new_wrapper_hash_is_explicitly_fillable_before_commit(self):
        value = config["locked_inputs"]["readout_wrapper"]["sha256"]
        self.assertEqual(value, "1bd8ca0cdd04d8d0535b81a38c2d2c05c82d8c90558b069790cfadd56d851d3d")
        self.assertTrue(re.fullmatch(r"[0-9a-f]{64}", value))

    def test_controller_imports_base_through_recovery_shim(self):
        source = DRIVER_PATH.read_text(encoding="utf-8")
        self.assertIn("fusion_w1_aprime_queue_recovery_20260727.py", source)
        self.assertIn("queue = recovery.queue", source)
        self.assertIn("_SOURCE_BUILD_PLAN = queue.build_plan", source)
        self.assertIn("queue.build_plan = build_plan", source)
        self.assertIn("queue.load_plan = load_plan", source)
        self.assertIn("queue.readout_context = cachefix_readout_context", source)
        self.assertIn("queue.inspect_pipeline = inspect_pipeline", source)
        self.assertIn("queue.verify_readout_complete = verify_readout_complete", source)


if __name__ == "__main__":
    unittest.main()
