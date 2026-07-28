#!/usr/bin/env python3
"""Static and focused contract tests for the overnight-v4 queue."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import unittest


SCRIPT = Path(__file__).with_name("fusion_w1_aprime_queue_continuation_v3_20260727.py")
CONFIG = SCRIPT.parents[1] / "configs/fusion_w1_aprime_queue_overnight_v4_20260727.json"
WRAPPER = Path(__file__).with_name("run_fusion_w1_aprime_queue_overnight_v4_20260727.sh")
BASE_WRAPPER = Path(__file__).with_name("run_fusion_w1_aprime_queue_continuation_v3_20260727.sh")
SPEC = importlib.util.spec_from_file_location("aprime_queue_overnight_v4_tested", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
queue = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = queue
SPEC.loader.exec_module(queue)


class OvernightV4Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.raw = json.loads(CONFIG.read_text(encoding="utf-8"))
        cls.config = queue.load_config(CONFIG)

    def test_overlay_and_counts(self) -> None:
        self.assertEqual(self.config["contract_profile"], "overnight_v4")
        self.assertEqual(self.config["sequence_contract"]["new_training_jobs"], 15)
        self.assertEqual(self.config["sequence_contract"]["pair_member_jobs"], 19)
        self.assertEqual(self.config["sequence_contract"]["pair_count"], 11)

    def test_recovery_lock_and_readout_source_fix(self) -> None:
        record = self.config["locked_inputs"]["recovery_contract"]
        self.assertEqual(queue.sha256_file(queue.repo_path(record["path"])), record["sha256"])
        readout = self.config["locked_inputs"]["readout_config"]
        self.assertEqual(readout["sha256"], "4486b727fd94bc9baf0706fac529d3a3aa1b8996d238773a2a148800b80d349a")
        self.assertEqual(readout["bytes"], 9448)

    def test_historical_reuse_is_exactly_four(self) -> None:
        contract = self.config["historical_training_reuse_contract"]
        self.assertEqual(len(contract["allowed_jobs"]), 4)
        self.assertTrue(contract["producer_head_must_be_ancestor"])
        self.assertTrue(contract["method_files_must_be_current_identical"])
        self.assertTrue(contract["new_training_requires_strict_current_head"])

    def test_panel_v4_hook_and_runtime_contract(self) -> None:
        hook = self.config["qualitative_hook"]
        self.assertEqual(hook["kind"], "panel_v4")
        self.assertEqual(hook["receipt_schema"], queue.PANEL_V4_SCHEMA)
        runtime = queue.runtime_contract(self.config)
        self.assertEqual(runtime["review_wrapper"], hook["wrapper"])
        self.assertEqual(runtime["queue_root"], self.config["outputs"]["root"])

    def test_legacy_v3_config_still_loads(self) -> None:
        legacy = queue.load_config(queue.DEFAULT_CONFIG)
        self.assertEqual(legacy["schema"], queue.CONFIG_SCHEMA)
        self.assertEqual(legacy["qualitative_hook"].get("kind", "qualitative_v3"), "qualitative_v3")

    def test_wrappers_are_syntactically_valid_and_config_driven(self) -> None:
        for path in (WRAPPER, BASE_WRAPPER):
            result = subprocess.run(["bash", "-n", str(path)], check=False)
            self.assertEqual(result.returncode, 0)
        source = BASE_WRAPPER.read_text(encoding="utf-8")
        self.assertIn("load_runtime_contract", source)
        self.assertIn('bash "$QUALITATIVE_WRAPPER" one', source)

    def test_no_unresolved_placeholders(self) -> None:
        paths = [CONFIG, WRAPPER, SCRIPT, queue.repo_path(self.config["locked_inputs"]["recovery_contract"]["path"])]
        for path in paths:
            source = path.read_text(encoding="utf-8")
            self.assertNotIn("TODO", source)
            self.assertNotIn("PLACEHOLDER", source)


if __name__ == "__main__":
    unittest.main(verbosity=2)
