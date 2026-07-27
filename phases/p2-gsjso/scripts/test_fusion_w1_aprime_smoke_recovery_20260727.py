#!/usr/bin/env python3
"""Focused Docker tests for the one-job A-prime smoke continuation."""
from __future__ import annotations

import ast
import copy
import importlib.util
import json
import re
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


REPO = Path(__file__).resolve().parents[3]
SCRIPT = REPO / "phases/p2-gsjso/scripts/fusion_w1_aprime_smoke_recovery_20260727.py"
CONFIG = REPO / "phases/p2-gsjso/configs/fusion_w1_aprime_smoke_recovery_20260727.json"
WRAPPER = REPO / "phases/p2-gsjso/scripts/run_fusion_w1_aprime_smoke_recovery_20260727.sh"
BASE_CONFIG = REPO / "phases/p2-gsjso/configs/fusion_w1_aprime_readout_20260726.json"
BASE_DRIVER = REPO / "phases/p2-gsjso/scripts/fusion_w1_aprime_readout_20260726.py"


def load_module():
    spec = importlib.util.spec_from_file_location("aprime_smoke_recovery_tested", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class AprimeSmokeRecoveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = load_module()
        cls.config = cls.module.load_config(CONFIG)
        cls.source = SCRIPT.read_text(encoding="utf-8")
        cls.wrapper = WRAPPER.read_text(encoding="utf-8")
        cls.base_source = BASE_DRIVER.read_text(encoding="utf-8")

    def test_sources_parse_and_wrapper_has_valid_bash_syntax(self):
        ast.parse(self.source)
        parsed = subprocess.run(
            ["bash", "-n", str(WRAPPER)],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        self.assertEqual(parsed.returncode, 0, parsed.stderr)

    def test_scope_is_exactly_one_existing_training_job(self):
        scope = self.config["scope"]
        self.assertEqual(
            scope,
            {
                "building_id": "DEBY_LOD2_42364609",
                "arm": "Aprime",
                "replicate": "r1",
                "profile": "full",
                "continuation_attempt": 5,
                "preserved_recovery_attempts": [4],
                "new_training_runs_allowed": 0,
                "other_queue_jobs_allowed": 0,
            },
        )
        self.module.require_scope(
            self.config, "DEBY_LOD2_42364609", "Aprime", "r1", 5
        )
        for identity in (
            ("DEBY_LOD2_42364659", "Aprime", "r1", 5),
            ("DEBY_LOD2_42364609", "Aprime", "r2", 5),
            ("DEBY_LOD2_42364609", "B", "r1", 5),
            ("DEBY_LOD2_42364609", "Aprime", "r1", 4),
            ("DEBY_LOD2_42364609", "Aprime", "r1", 6),
        ):
            with self.subTest(identity=identity), self.assertRaises(
                self.module.SmokeRecoveryError
            ):
                self.module.require_scope(self.config, *identity)

    def test_derived_readout_config_is_one_job_attempt_four_in_new_namespace(self):
        locked = self.module.verify_locked_inputs(self.config)
        contract = {
            "locked_inputs": locked,
            "preserved_attempt_004": {"tree_sha256": "locked-in-v3"},
        }
        derived = self.module.derived_readout_config(self.config, contract)
        self.assertEqual(derived["identity_contract"]["expected_queue_jobs"], 1)
        self.assertEqual(derived["retry_contract"]["attempt_number_min"], 5)
        self.assertEqual(derived["retry_contract"]["attempt_number_max"], 5)
        self.assertIn("20260727_fusion_w1_aprime_smoke_recovery", derived["outputs"]["root"])
        self.assertNotIn(
            "20260726_fusion_w1_aprime/readout/by_building",
            derived["outputs"]["job_template"],
        )
        self.assertEqual(
            derived["outputs"]["runtime_environment"],
            "phases/p2-gsjso/runs/20260726_fusion_w1_aprime/runtime_env",
        )
        self.assertFalse(derived["containers"]["concurrent_with_training"])
        self.assertIsNone(derived["publication"]["interpretation_or_verdict"])
        self.assertTrue(derived["publication"]["retraining_forbidden"])

    def test_lock_v2_allows_only_the_dedicated_implementation_layout(self):
        v1, v2, v3 = self.module.load_locks(self.config)
        self.assertEqual(v1["scope"]["continuation_attempt"], 4)
        self.assertEqual(v2["scope"]["continuation_attempt"], 4)
        self.assertEqual(v3["scope"], self.config["scope"])
        allowed = set(v3["allowed_descendant_paths"])
        self.assertTrue(set(self.config["implementation_files"][:4]).issubset(allowed))
        self.assertFalse(v2["original_queue_rewrite_allowed"])
        self.assertFalse(v2["original_readout_code_change_allowed"])
        self.assertFalse(v2["retraining_allowed"])
        self.assertFalse(v3["recovery_attempt_004_rewrite_allowed"])
        self.assertFalse(v3["other_jobs_allowed"])

    def test_locked_original_driver_config_queue_and_failures_are_unchanged(self):
        locked = self.config["locked_inputs"]
        self.assertEqual(
            self.module.sha256_file(BASE_CONFIG),
            locked["base_readout_config"]["sha256"],
        )
        self.assertEqual(
            self.module.sha256_file(BASE_DRIVER),
            locked["base_readout_driver"]["sha256"],
        )
        v1, _v2, v3 = self.module.load_locks(self.config)
        records = v1["source_records"]
        for number in range(1, 4):
            failure_path = self.module.verify_record(
                records[f"attempt_{number:03d}_failure"], f"attempt {number} failure"
            )
            failure = json.loads(failure_path.read_text(encoding="utf-8"))
            self.assertEqual(failure["attempt"], number)
            self.assertEqual(
                failure["error_signature"], self.config["source_failure_signature"]
            )
            tsdf_path = self.module.verify_record(
                records[f"attempt_{number:03d}_tsdf_failure"],
                f"attempt {number} TSDF failure",
            )
            tsdf = json.loads(tsdf_path.read_text(encoding="utf-8"))
            self.assertEqual(tsdf["error_type"], "PermissionError")
            self.assertEqual(tsdf["message"], "[Errno 13] Permission denied: '/.cache'")
        for name in ("queue_stage_stop", "queue_complete"):
            path = self.module.verify_record(records[name], name)
            payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(payload["state"], self.config["source_terminal_state"])
        preserved = self.module.verify_preserved_attempt_004(self.config, v3)
        self.assertEqual(preserved["files_n"], 47)
        self.assertEqual(
            preserved["tree_sha256"],
            "1be09fe5f59eb5852bff2afb667e27f69aa60284de6e4135960ad710ffddd358",
        )

    def test_adapter_checks_both_final_and_history_allowlists(self):
        self.assertIn('("final", final_paths)', self.source)
        self.assertIn('("history", history_paths)', self.source)
        self.assertIn("all_descendant_paths_allowlisted", self.source)
        self.assertIn("source_attempt_trees", self.source)
        self.assertIn("post-readout source attempt trees", self.source)
        self.assertIn("post-readout training tree", self.source)

    def test_recovery_namespace_rejects_every_foreign_job_or_attempt(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = copy.deepcopy(self.config)
            config["outputs"]["readout_root"] = "readout"
            authorized = (
                root
                / "readout/by_building/DEBY_LOD2_42364609/arm_Aprime/r1/attempts/attempt_004"
            )
            authorized.mkdir(parents=True)
            with patch.object(self.module, "REPO", root):
                inventory = self.module.recovery_namespace_inventory(config)
                self.assertEqual(inventory["attempt_directories"], ["attempt_004"])
                self.assertEqual(inventory["other_queue_jobs_started"], 0)
                foreign = root / "readout/by_building/DEBY_LOD2_42364659"
                foreign.mkdir()
                with self.assertRaises(self.module.SmokeRecoveryError):
                    self.module.recovery_namespace_inventory(config)
                foreign.rmdir()
                foreign_attempt = authorized.parent / "attempt_006"
                foreign_attempt.mkdir()
                with self.assertRaises(self.module.SmokeRecoveryError):
                    self.module.recovery_namespace_inventory(config)

    def test_wrapper_reuses_exact_t2_cache_as_nonroot_offline_gpu_job(self):
        expected_root = "phases/p2-gsjso/runs/20260726_fusion_w1_aprime/runtime_env"
        self.assertIn(f'RUNTIME_REL="{expected_root}"', self.wrapper)
        self.assertIn('HOME=/workspace/JointBuildGS/$RUNTIME_REL/home', self.wrapper)
        self.assertIn('XDG_CACHE_HOME=/workspace/JointBuildGS/$RUNTIME_REL/xdg_cache', self.wrapper)
        self.assertIn('TORCH_EXTENSIONS_DIR=/workspace/JointBuildGS/$RUNTIME_REL/torch_extensions', self.wrapper)
        self.assertIn("--env MAX_JOBS=2", self.wrapper)
        self.assertIn('--user "$HOST_UID:$HOST_GID"', self.wrapper)
        self.assertIn("--network=none", self.wrapper)
        self.assertIn("--gpus all", self.wrapper)
        self.assertIn('GPU_INDEX="${APRIME_SMOKE_RECOVERY_GPU_INDEX:-1}"', self.wrapper)
        self.assertNotIn("timeout ", self.wrapper)
        cache = self.config["cache_contract"]
        self.assertTrue(cache["reuse_only"])
        self.assertFalse(cache["compilation_allowed"])
        extension = cache["preexisting_gsplat_extension"]
        self.assertEqual(extension["bytes"], 9115720)
        self.assertEqual(
            extension["sha256"],
            "ca43f10b5d8adacb8e40fdc9685a661d459cf80bed9eec955cf2ecff0d555ca1",
        )
        self.assertIn("cache_tree_before", self.source)
        self.assertIn("post-load cache tree", self.source)

    def test_wrapper_never_calls_base_check_or_begin_and_has_no_training_action(self):
        self.assertIsNone(re.search(r"\bbase\s+(check|begin)\b", self.wrapper))
        guard_start = self.wrapper.index("assert_no_training()")
        guard_end = self.wrapper.index("acquire_driver_lock()")
        executable = self.wrapper[:guard_start] + self.wrapper[guard_end:]
        self.assertNotIn("src/stage2/train.py", executable)
        self.assertNotRegex(
            executable,
            r"fusion_w1_aprime_training_20260726\.py\s+(materialize|launch)",
        )
        self.assertNotIn("unattended_queue", self.wrapper)
        self.assertIn('ATTEMPT="5"', self.wrapper)
        self.assertIn('[[ "$#" -eq 1 ]]', self.wrapper)

    def test_wrapper_order_is_probe_begin_primary_legacy_finalize_publish(self):
        probe = self.wrapper.index('CURRENT_STAGE="cache_probe"')
        begin = self.wrapper.index('CURRENT_STAGE="begin_attempt"')
        primary = self.wrapper.index('CURRENT_STAGE="primary_tsdf"')
        legacy = self.wrapper.index('CURRENT_STAGE="legacy_alpha_authorize"')
        finalize = self.wrapper.index('CURRENT_STAGE="finalize"')
        hygiene = self.wrapper.index('CURRENT_STAGE="finalize_hygiene"')
        publish = self.wrapper.index('CURRENT_STAGE="publish"')
        verify = self.wrapper.index('CURRENT_STAGE="verify"')
        self.assertLess(probe, begin)
        self.assertLess(begin, primary)
        self.assertLess(primary, legacy)
        self.assertLess(legacy, finalize)
        self.assertLess(legacy, hygiene)
        self.assertLess(hygiene, finalize)
        self.assertLess(finalize, publish)
        self.assertLess(publish, verify)
        between = self.wrapper[finalize:publish]
        self.assertIn('ACTIVE_ATTEMPT=""', between)

    def test_single_use_and_null_verdict_publication_are_explicit(self):
        self.assertTrue(self.config["publication"]["single_use_attempt"])
        self.assertTrue(self.config["publication"]["complete_receipt_written_last"])
        self.assertIsNone(self.config["publication"]["scientific_verdict"])
        self.assertIn('require_equal(existing, expected_existing', self.source)
        self.assertIn('["attempt_004", "attempt_005"]', self.source)
        self.assertNotIn('"scientific_verdict": "PASS"', self.source)
        self.assertNotIn('"scientific_verdict": "FAIL"', self.source)
        self.assertIn("expected_git_head=execution_head", self.source)
        self.assertIn('"--is-ancestor", execution_head, current_head', self.source)


if __name__ == "__main__":
    unittest.main()
