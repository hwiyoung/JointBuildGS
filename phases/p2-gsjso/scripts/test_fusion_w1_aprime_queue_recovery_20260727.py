#!/usr/bin/env python3
"""Focused tests for the A-prime queue recovery compatibility shim."""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


SCRIPT = Path(__file__).with_name("fusion_w1_aprime_queue_recovery_20260727.py")
SPEC = importlib.util.spec_from_file_location("aprime_queue_recovery_tested", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
recovery = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = recovery
SPEC.loader.exec_module(recovery)


class QueueRecoveryTest(unittest.TestCase):
    def test_producer_materialization_record_excludes_bytes(self) -> None:
        observed = recovery.producer_materialization_record(
            {"path": "x.json", "sha256": "abc", "bytes": 123}
        )
        self.assertEqual(observed, {"path": "x.json", "sha256": "abc"})

    def test_patch_is_path_local_and_restores_file_record(self) -> None:
        original_file_record = recovery.queue.file_record
        original_verify = recovery._ORIGINAL_VERIFY_TRAINING_BINDING
        materialized = Path("/tmp/materialization.json")
        other = Path("/tmp/completed.json")
        calls = []

        def fake_file_record(path: Path):
            return {"path": str(path), "sha256": "abc", "bytes": 12}

        def fake_verify(module, config, entry, observed_materialized, completed):
            calls.append(recovery.queue.file_record(observed_materialized))
            calls.append(recovery.queue.file_record(other))
            return {"ok": True}

        recovery.queue.file_record = fake_file_record
        recovery._ORIGINAL_VERIFY_TRAINING_BINDING = fake_verify
        try:
            result = recovery.compatible_verify_training_binding(
                object(), {}, {}, materialized, other
            )
            self.assertEqual(result, {"ok": True})
            self.assertEqual(
                calls[0], {"path": str(materialized), "sha256": "abc"}
            )
            self.assertEqual(
                calls[1], {"path": str(other), "sha256": "abc", "bytes": 12}
            )
            self.assertIs(recovery.queue.file_record, fake_file_record)
        finally:
            recovery.queue.file_record = original_file_record
            recovery._ORIGINAL_VERIFY_TRAINING_BINDING = original_verify

    def test_excluded_archive_artifact_is_exact(self) -> None:
        self.assertEqual(
            recovery.EXCLUDED_ARCHIVE_FILES, {"orchestrator_orphan_failure.json"}
        )


if __name__ == "__main__":
    unittest.main()
