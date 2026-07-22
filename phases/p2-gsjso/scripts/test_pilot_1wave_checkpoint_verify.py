#!/usr/bin/env python3
"""Unit tests for the pinned, read-only P1W checkpoint verifier."""
from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import sys
import tempfile
import unittest


SCRIPT = Path(__file__).with_name("pilot_1wave_checkpoint_verify.py")
SPEC = importlib.util.spec_from_file_location("pilot_1wave_checkpoint_verify", SCRIPT)
verify = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = verify
SPEC.loader.exec_module(verify)


class CheckpointVerifierTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="p1w-checkpoint-verify-")
        self.checkpoint = Path(self.temporary.name) / "step_020000.pt"
        self.checkpoint.write_bytes(b"synthetic checkpoint bytes")
        self.sha = hashlib.sha256(self.checkpoint.read_bytes()).hexdigest()
        self.binding = {
            "training_config": "1" * 64,
            "effective_training_config": "2" * 64,
            "output_path": "3" * 64,
        }
        self.loss_paths = [
            "audit/loss_grad_norms.csv",
            "audit/pilot_loss_shares.csv",
        ]

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _loaded(self, **payload_overrides):
        payload = {
            "step_semantics": "completed_optimizer_updates",
            "binding_sha256": dict(self.binding),
            "learning_runs_started": 1,
            "loss_log_cursor": {
                "schema": "jointbuildgs.stage2.loss_csv_cursor.v1",
                "completed_steps": 20000,
                "files": {path: {} for path in self.loss_paths},
            },
        }
        payload.update(payload_overrides)
        return SimpleNamespace(
            sha256=self.sha,
            completed_steps=20000,
            payload=payload,
        )

    def test_exact_payload_is_verified_read_only(self) -> None:
        loader_calls = []

        def loader(path, **kwargs):
            loader_calls.append((path, kwargs))
            return self._loaded()

        result = verify.verify_checkpoint(
            checkpoint=self.checkpoint,
            expected_sha256=self.sha,
            expected_binding_sha256=self.binding,
            expected_loss_csv_paths=self.loss_paths,
            loader=loader,
        )
        self.assertEqual(result["state"], "verified")
        self.assertTrue(result["read_only"])
        self.assertFalse(result["gpu_required"])
        self.assertEqual(result["completed_steps"], 20000)
        self.assertEqual(loader_calls[0][1]["map_location"], "cpu")
        self.assertEqual(
            loader_calls[0][1]["expected_binding_sha256"], self.binding
        )

    def test_binding_and_loss_cursor_drift_fail_closed(self) -> None:
        bad_binding = dict(self.binding)
        bad_binding["injected"] = "4" * 64
        with self.assertRaisesRegex(verify.VerificationError, "exactly three"):
            verify.verify_checkpoint(
                checkpoint=self.checkpoint,
                expected_sha256=self.sha,
                expected_binding_sha256=bad_binding,
                expected_loss_csv_paths=self.loss_paths,
                loader=lambda *_args, **_kwargs: self._loaded(),
            )

        with self.assertRaisesRegex(verify.VerificationError, "cursor paths"):
            verify.verify_checkpoint(
                checkpoint=self.checkpoint,
                expected_sha256=self.sha,
                expected_binding_sha256=self.binding,
                expected_loss_csv_paths=self.loss_paths,
                loader=lambda *_args, **_kwargs: self._loaded(
                    loss_log_cursor={
                        "schema": "jointbuildgs.stage2.loss_csv_cursor.v1",
                        "completed_steps": 20000,
                        "files": {"audit/injected.csv": {}},
                    }
                ),
            )

    def test_filename_must_be_exact_20k(self) -> None:
        other = self.checkpoint.with_name("step_015000.pt")
        other.write_bytes(self.checkpoint.read_bytes())
        with self.assertRaisesRegex(verify.VerificationError, "filename"):
            verify.verify_checkpoint(
                checkpoint=other,
                expected_sha256=self.sha,
                expected_binding_sha256=self.binding,
                expected_loss_csv_paths=self.loss_paths,
                loader=lambda *_args, **_kwargs: self._loaded(),
            )


if __name__ == "__main__":
    unittest.main()
