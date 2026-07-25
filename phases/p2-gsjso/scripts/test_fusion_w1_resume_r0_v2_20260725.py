#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parents[3]
SCRIPT = REPO / "phases/p2-gsjso/scripts/fusion_w1_resume_r0_v2_20260725.py"
CONFIG = REPO / "phases/p2-gsjso/configs/fusion_w1_resume_r0_v2_20260725.json"


def load_module():
    spec = importlib.util.spec_from_file_location("resume_r0", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ResumeR0Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = load_module()
        cls.config = json.loads(CONFIG.read_text(encoding="utf-8"))

    def test_schema_and_branch_are_locked(self):
        self.assertEqual(
            self.config["schema"],
            "jointbuildgs.fusion_w1.resume_r0_v2.config.v1",
        )
        self.assertEqual(self.config["branch"], "exp/fusion-w1")

    def test_diagnostic_commit_is_required(self):
        self.assertEqual(
            self.config["required_ancestors"]["diagnostic"],
            "45bce93c45b5f00e9984f2e86b4293f643c763fc",
        )

    def test_all_documents_have_distinct_run_copies(self):
        for item in self.config["documents"]:
            self.assertNotEqual(item["path"], item["run_copy"])
            self.assertRegex(item["sha256"], r"^[0-9a-f]{64}$")

    def test_counters_are_all_zero_gates(self):
        self.assertEqual(
            set(self.config["counter_source"]["required_zero"]),
            {
                "learning_runs_started",
                "readout_runs_started",
                "roofer_runs_started",
                "scoring_runs_started",
            },
        )

    def test_pose_change_is_deferred_to_r1(self):
        pose = self.config["pose_transition"]
        self.assertEqual(pose["source_image_count"], 937)
        self.assertIn("source", pose["r0_expected_state"])
        self.assertIn("separately published", pose["r1_authorized_difference"])

    def test_latest_cutoff_is_absolute_and_supersedes_v3a(self):
        policy = self.config["time_policy"]
        self.assertEqual(policy["cutoff_at"], "2026-07-26T06:30:00+09:00")
        self.assertIn("supersedes", policy)
        self.assertIn("stop_new_training", policy["cutoff_mode"])

    def test_result_helper_has_no_verdict_field(self):
        value = self.module.result("x", True, {"n": 1})
        self.assertEqual(value["status"], "passed")
        self.assertNotIn("interpretation", value)

    def test_exact_once_claim_rejects_second_writer(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "claim.json"
            self.module.exclusive_json(path, {"state": "STARTED"})
            with self.assertRaises(FileExistsError):
                self.module.exclusive_json(path, {"state": "STARTED"})
            self.assertEqual(
                json.loads(path.read_text(encoding="utf-8"))["state"],
                "STARTED",
            )

    def test_unknown_gpu_caveat_is_fail_closed(self):
        class UnsafeBase:
            @staticmethod
            def check_no_active_training(_config):
                return {
                    "name": "no_active_training_guard",
                    "status": "passed_with_caveat",
                    "caveat": "unknown GPU process",
                    "evidence": {
                        "no_active_training": True,
                        "future_gpu_stage_launch_blocked": True,
                    },
                }

        value = self.module.check_no_active_training_strict(UnsafeBase, {})
        self.assertEqual(value["status"], "failed")
        self.assertTrue(value["evidence"]["strict_fail_closed"])

    def test_runtime_counter_scan_observes_drift(self):
        old_repo = self.module.REPO
        try:
            with tempfile.TemporaryDirectory() as directory:
                self.module.REPO = Path(directory)
                root = self.module.REPO / "run"
                root.mkdir()
                (root / "ledger.json").write_text(
                    json.dumps(
                        {
                            "learning_runs_started": 1,
                            "readout_runs_started": 0,
                        }
                    ),
                    encoding="utf-8",
                )
                config = {
                    "counter_source": {
                        "required_zero": [
                            "learning_runs_started",
                            "readout_runs_started",
                        ]
                    },
                    "runtime_zero_evidence": {
                        "run_root": "run",
                        "counter_file_suffixes": [".json"],
                    },
                }
                values, observations, failures = (
                    self.module.scan_runtime_counters(config)
                )
                self.assertEqual(values["learning_runs_started"], 1)
                self.assertEqual(values["readout_runs_started"], 0)
                self.assertTrue(observations)
                self.assertFalse(failures)
        finally:
            self.module.REPO = old_repo

    def test_runtime_counter_negative_cannot_be_hidden_by_zero(self):
        old_repo = self.module.REPO
        try:
            with tempfile.TemporaryDirectory() as directory:
                self.module.REPO = Path(directory)
                root = self.module.REPO / "run"
                root.mkdir()
                (root / "a.json").write_text(
                    json.dumps({"learning_runs_started": -1}),
                    encoding="utf-8",
                )
                (root / "b.json").write_text(
                    json.dumps({"learning_runs_started": 0}),
                    encoding="utf-8",
                )
                config = {
                    "counter_source": {
                        "required_zero": ["learning_runs_started"]
                    },
                    "runtime_zero_evidence": {
                        "run_root": "run",
                        "counter_file_suffixes": [".json"],
                    },
                }
                values, _, _ = self.module.scan_runtime_counters(config)
                self.assertEqual(values["learning_runs_started"], -1)
        finally:
            self.module.REPO = old_repo

    def test_current_coreg_publication_and_zero_counters_are_complete(self):
        value = self.module.check_coreg_and_counters(self.config)
        self.assertEqual(value["status"], "passed")
        evidence = value["evidence"]
        self.assertTrue(evidence["publication_inventory_complete"])
        self.assertGreaterEqual(len(evidence["publication_inventory"]), 16)
        self.assertEqual(
            set(evidence["runtime_counter_values"].values()), {0}
        )
        self.assertFalse(evidence["runtime_counter_parse_failures"])
        self.assertFalse(
            any(
                row["exists"]
                for row in evidence["forbidden_downstream_paths"]
            )
        )

    def test_unhandled_failure_does_not_claim_zero_counters(self):
        with tempfile.TemporaryDirectory() as directory:
            old_repo = self.module.REPO
            try:
                self.module.REPO = Path(directory)
                claim = self.module.REPO / "claim.json"
                manifest = self.module.failure_manifest(
                    {"task_id": "x", "run_id": "y"},
                    RuntimeError("boom"),
                    claim_path=claim,
                )
            finally:
                self.module.REPO = old_repo
        self.assertEqual(manifest["status"], "BLOCKED")
        self.assertTrue(
            all(
                value is None
                for value in manifest["execution_counters"].values()
            )
        )


if __name__ == "__main__":
    unittest.main()
