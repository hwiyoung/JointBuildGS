#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest


SCRIPT_PATH = Path(__file__).with_name("fusion_w1_alignment_checkpoint.py")
SPEC = importlib.util.spec_from_file_location(
    "fusion_w1_alignment_checkpoint", SCRIPT_PATH
)
assert SPEC is not None and SPEC.loader is not None
checkpoint = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = checkpoint
SPEC.loader.exec_module(checkpoint)

PNG = b"\x89PNG\r\n\x1a\n" + b"durability-test-payload"
FIELDS = ["building_id", "attempt", "view", "residual_px", "residual_m"]


def digest(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


def identity(label: str = "default") -> checkpoint.CheckpointIdentity:
    return checkpoint.CheckpointIdentity(
        config_sha256=digest(f"{label}:config"),
        input_sha256=checkpoint.canonical_hash_manifest(
            {
                "als.laz": digest(f"{label}:als"),
                "images.bin": digest(f"{label}:poses"),
            }
        ),
        view_sha256=digest(f"{label}:views"),
        implementation_sha256=digest(f"{label}:implementation"),
    )


def rows(building_id: str, attempt: str, residual: str = "0.12"):
    return [
        {
            "building_id": building_id,
            "attempt": attempt,
            "view": "images/000001.jpg",
            "residual_px": "2.5",
            "residual_m": residual,
        }
    ]


def summary(building_id: str, attempt: str, residual: float = 0.12):
    return {
        "building_id": building_id,
        "attempt": attempt,
        "median_residual_m": residual,
        "p90_residual_m": residual,
        "numeric_gate_met": residual <= 0.3,
    }


class FusionW1AlignmentCheckpointTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "checkpoint_store"
        self.store = checkpoint.AlignmentCheckpointStore(self.root)
        self.identity = identity()

    def tearDown(self) -> None:
        self.temp.cleanup()

    def complete(
        self,
        building_id: str = "DEBY_LOD2_42364609",
        attempt: str = "raw",
        *,
        overlay=PNG,
        residual: str = "0.12",
        fault_hook=None,
    ):
        return self.store.complete_attempt(
            self.identity,
            building_id=building_id,
            attempt=attempt,
            residual_rows=rows(building_id, attempt, residual),
            residual_fields=FIELDS,
            summary=summary(building_id, attempt, float(residual)),
            overlay=overlay,
            fault_hook=fault_hook,
        )

    def test_atomic_json_csv_png_and_exception_cleanup(self) -> None:
        output = self.root / "atomic"
        checkpoint.atomic_write_json(output / "payload.json", {"b": 2, "a": 1})
        checkpoint.atomic_write_csv(
            output / "rows.csv", [{"a": 1, "b": 2}], ["a", "b"]
        )
        checkpoint.atomic_write_png(output / "overlay.png", PNG)
        self.assertEqual(json.loads((output / "payload.json").read_text()), {"a": 1, "b": 2})
        self.assertEqual((output / "rows.csv").read_text(), "a,b\n1,2\n")
        self.assertEqual((output / "overlay.png").read_bytes(), PNG)

        class SimulatedException(RuntimeError):
            pass

        failed = output / "not_published.json"

        def fail_after_fsync(phase: str, _path: Path) -> None:
            if phase == "after_file_fsync":
                raise SimulatedException("test exception")

        with self.assertRaises(SimulatedException):
            checkpoint.atomic_write_json(
                failed,
                {"never": "visible"},
                fault_hook=fail_after_fsync,
            )
        self.assertFalse(failed.exists())
        self.assertFalse(any(".tmp-" in path.name for path in output.iterdir()))

    def test_no_symbolic_link_traversal(self) -> None:
        real = Path(self.temp.name) / "real"
        real.mkdir()
        linked = Path(self.temp.name) / "linked"
        linked.symlink_to(real, target_is_directory=True)
        with self.assertRaises(checkpoint.PathSecurityError):
            checkpoint.atomic_write_json(linked / "payload.json", {"x": 1})
        with self.assertRaises(checkpoint.PathSecurityError):
            checkpoint.AlignmentCheckpointStore(linked)

    def test_completion_is_immutable_and_resume_verifies(self) -> None:
        completed = self.complete()
        self.assertEqual(completed["status"], "COMPLETED")
        state = self.store.resume_status(
            self.identity, "DEBY_LOD2_42364609", "raw"
        )
        self.assertEqual(state.state, "completed")
        self.assertGreaterEqual(state.journal_event_count, 4)
        resumed = self.complete()
        self.assertEqual(
            resumed["checkpoint_sha256"], completed["checkpoint_sha256"]
        )
        with self.assertRaises(checkpoint.ImmutableCheckpointError):
            self.complete(residual="0.13")

    def test_overlay_exception_keeps_numeric_evidence(self) -> None:
        def broken_overlay() -> bytes:
            raise RuntimeError("renderer unavailable")

        completed = self.complete(overlay=broken_overlay)
        attempt_dir = self.store.attempt_dir(
            self.identity, "DEBY_LOD2_42364609", "raw"
        )
        self.assertTrue((attempt_dir / "residuals.csv").is_file())
        self.assertTrue((attempt_dir / "summary.json").is_file())
        self.assertTrue((attempt_dir / "overlay_error.json").is_file())
        self.assertFalse((attempt_dir / "overlay.png").exists())
        self.assertEqual(
            completed["overlay_status"], "failed_numeric_preserved"
        )
        issue = json.loads((attempt_dir / "overlay_error.json").read_text())
        self.assertTrue(issue["numeric_evidence_preserved"])
        self.store.verify_completed(
            self.identity, "DEBY_LOD2_42364609", "raw"
        )

    @unittest.skipUnless(hasattr(os, "fork"), "requires POSIX fork")
    def test_simulated_kill_then_restart_completes_safely(self) -> None:
        # Create the identity before forking so the kill occurs specifically
        # after the residual CSV has reached fsync but before publication.
        initial = self.store.resume_status(
            self.identity, "DEBY_LOD2_42364609", "raw"
        )
        self.assertEqual(initial.state, "new")
        pid = os.fork()
        if pid == 0:
            child_store = checkpoint.AlignmentCheckpointStore(self.root)

            def kill_after_residual_fsync(phase: str, path: Path) -> None:
                if phase == "after_file_fsync" and path.name == "residuals.csv":
                    os._exit(91)

            child_store.complete_attempt(
                self.identity,
                building_id="DEBY_LOD2_42364609",
                attempt="raw",
                residual_rows=rows("DEBY_LOD2_42364609", "raw"),
                residual_fields=FIELDS,
                summary=summary("DEBY_LOD2_42364609", "raw"),
                overlay=PNG,
                fault_hook=kill_after_residual_fsync,
            )
            os._exit(0)
        _waited, status = os.waitpid(pid, 0)
        self.assertTrue(os.WIFEXITED(status))
        self.assertEqual(os.WEXITSTATUS(status), 91)
        restarted = checkpoint.AlignmentCheckpointStore(self.root)
        state = restarted.resume_status(
            self.identity, "DEBY_LOD2_42364609", "raw"
        )
        self.assertEqual(state.state, "incomplete")
        completed = restarted.complete_attempt(
            self.identity,
            building_id="DEBY_LOD2_42364609",
            attempt="raw",
            residual_rows=rows("DEBY_LOD2_42364609", "raw"),
            residual_fields=FIELDS,
            summary=summary("DEBY_LOD2_42364609", "raw"),
            overlay=PNG,
        )
        self.assertEqual(completed["status"], "COMPLETED")
        self.assertFalse(
            any(".tmp-" in path.name for path in self.root.rglob("*"))
        )

    def test_exception_during_checkpoint_then_restart(self) -> None:
        class SimulatedException(RuntimeError):
            pass

        def fail_at_checkpoint(phase: str, path: Path) -> None:
            if phase == "after_file_fsync" and path.name == "checkpoint.json":
                raise SimulatedException("checkpoint publication interrupted")

        with self.assertRaises(SimulatedException):
            self.complete(fault_hook=fail_at_checkpoint)
        state = self.store.resume_status(
            self.identity, "DEBY_LOD2_42364609", "raw"
        )
        self.assertEqual(state.state, "incomplete")
        completed = self.complete()
        self.assertEqual(completed["status"], "COMPLETED")

    def test_checkpoint_and_journal_tamper_detection(self) -> None:
        self.complete()
        attempt_dir = self.store.attempt_dir(
            self.identity, "DEBY_LOD2_42364609", "raw"
        )
        residual_path = attempt_dir / "residuals.csv"
        residual_path.write_bytes(residual_path.read_bytes() + b"tamper")
        with self.assertRaises(checkpoint.CheckpointIntegrityError):
            self.store.verify_completed(
                self.identity, "DEBY_LOD2_42364609", "raw"
            )

        second_identity = identity("journal-tamper")
        self.store.complete_attempt(
            second_identity,
            building_id="DEBY_LOD2_4907182",
            attempt="raw",
            residual_rows=rows("DEBY_LOD2_4907182", "raw"),
            residual_fields=FIELDS,
            summary=summary("DEBY_LOD2_4907182", "raw"),
            overlay=PNG,
        )
        journal = (
            self.store.attempt_dir(
                second_identity, "DEBY_LOD2_4907182", "raw"
            )
            / "journal"
        )
        event = sorted(journal.glob("*.json"))[0]
        event.write_bytes(event.read_bytes() + b" ")
        with self.assertRaises(checkpoint.CheckpointIntegrityError):
            self.store.verify_completed(
                second_identity, "DEBY_LOD2_4907182", "raw"
            )

    def test_repeated_error_rules_and_durable_blocked_receipt(self) -> None:
        decisions = [
            self.store.record_error(
                self.identity,
                building_id="DEBY_LOD2_A",
                attempt="raw",
                error_type="ProjectionError",
                message=f"repeat {index}",
            )
            for index in range(3)
        ]
        self.assertFalse(decisions[1].skip_building)
        self.assertTrue(decisions[2].skip_building)
        self.assertEqual(decisions[2].same_error_count_for_building, 3)

        stage_identity = identity("stage-errors")
        stage_decisions = []
        for building_id in ("DEBY_LOD2_B1", "DEBY_LOD2_B2", "DEBY_LOD2_B3"):
            stage_decisions.append(
                self.store.record_error(
                    stage_identity,
                    building_id=building_id,
                    attempt="raw",
                    error_type="ImageDecodeError",
                    message="same type",
                )
            )
        self.assertFalse(stage_decisions[1].stop_stage)
        self.assertTrue(stage_decisions[2].stop_stage)
        self.assertEqual(
            stage_decisions[2].consecutive_building_count, 3
        )
        self.assertIsNotNone(stage_decisions[2].blocked_receipt)
        blocked = self.store.resolve_current_blocked(stage_identity)
        assert blocked is not None
        self.assertEqual(blocked["status"], "BLOCKED")
        self.assertFalse(blocked["learning_allowed"])

        reset_identity = identity("stage-reset")
        self.store.record_error(
            reset_identity,
            building_id="DEBY_LOD2_C1",
            attempt="raw",
            error_type="ProjectionError",
            message="first",
        )
        self.store.mark_building_success(
            reset_identity, building_id="DEBY_LOD2_C2"
        )
        self.store.record_error(
            reset_identity,
            building_id="DEBY_LOD2_C3",
            attempt="raw",
            error_type="ProjectionError",
            message="after reset",
        )
        reset = self.store.record_error(
            reset_identity,
            building_id="DEBY_LOD2_C4",
            attempt="raw",
            error_type="ProjectionError",
            message="two after reset",
        )
        self.assertEqual(reset.consecutive_building_count, 2)
        self.assertFalse(reset.stop_stage)

    def test_versioned_bundle_pointer_preserves_previous_bundle(self) -> None:
        first_building = "DEBY_LOD2_42364609"
        second_building = "DEBY_LOD2_4907182"
        self.complete(first_building)
        first = self.store.assemble_bundle(
            self.identity, [checkpoint.CheckpointRef(first_building, "raw")]
        )
        self.assertTrue(first.bundle_dir.is_dir())

        def no_overlay() -> bytes:
            raise RuntimeError("intentional overlay failure")

        self.complete(second_building, overlay=no_overlay)
        second = self.store.assemble_bundle(
            self.identity,
            [
                checkpoint.CheckpointRef(first_building, "raw"),
                checkpoint.CheckpointRef(second_building, "raw"),
            ],
        )
        self.assertNotEqual(first.bundle_id, second.bundle_id)
        self.assertTrue(first.bundle_dir.is_dir())
        self.assertTrue(second.bundle_dir.is_dir())
        current = self.store.resolve_current_bundle(self.identity)
        assert current is not None
        self.assertEqual(current.bundle_id, second.bundle_id)
        pointer = json.loads(second.current_pointer.read_text())
        self.assertEqual(pointer["previous_bundle_id"], first.bundle_id)
        residual_lines = (
            second.bundle_dir / "w1_align_residuals.csv"
        ).read_text().splitlines()
        self.assertEqual(len(residual_lines), 3)
        issue_lines = (
            second.bundle_dir / "w1_align_overlay_issues.csv"
        ).read_text().splitlines()
        self.assertEqual(len(issue_lines), 2)
        self.assertEqual(second.manifest["overlay_failure_count"], 1)

        bundle_residual = second.bundle_dir / "w1_align_residuals.csv"
        bundle_residual.write_bytes(bundle_residual.read_bytes() + b"tamper")
        with self.assertRaises(checkpoint.CheckpointIntegrityError):
            self.store.resolve_current_bundle(self.identity)

    def test_hash_binding_produces_separate_checkpoint_namespace(self) -> None:
        other = identity("other-implementation")
        self.assertNotEqual(self.identity.key, other.key)
        self.assertNotEqual(
            self.store.attempt_dir(
                self.identity, "DEBY_LOD2_1", "raw"
            ),
            self.store.attempt_dir(other, "DEBY_LOD2_1", "raw"),
        )
        with self.assertRaises(checkpoint.CheckpointBindingError):
            checkpoint.CheckpointIdentity(
                config_sha256="not-a-sha",
                input_sha256=digest("input"),
                view_sha256=digest("view"),
                implementation_sha256=digest("impl"),
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
