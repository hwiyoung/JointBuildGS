#!/usr/bin/env python3
"""Focused Docker tests for the production A-prime readout driver."""
from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
import subprocess
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np


REPO = Path(__file__).resolve().parents[3]
SCRIPT = REPO / "phases/p2-gsjso/scripts/fusion_w1_aprime_readout_20260726.py"
CONFIG = REPO / "phases/p2-gsjso/configs/fusion_w1_aprime_readout_20260726.json"
WRAPPER = REPO / "phases/p2-gsjso/scripts/run_fusion_w1_aprime_readout_20260726.sh"


def load_module():
    spec = importlib.util.spec_from_file_location("aprime_readout_tested", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class AprimeReadoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = load_module()
        cls.config = cls.module.load_config(CONFIG)
        cls.source = SCRIPT.read_text(encoding="utf-8")
        cls.wrapper = WRAPPER.read_text(encoding="utf-8")

    def make_training_binding_fixture(self, *, historical: bool):
        temporary = tempfile.TemporaryDirectory()
        root = Path(temporary.name)

        def digest(path: Path) -> str:
            return hashlib.sha256(path.read_bytes()).hexdigest()

        def rel(path: Path) -> str:
            return str(path.relative_to(root))

        def record(path: Path) -> dict[str, object]:
            return {
                "path": rel(path),
                "sha256": digest(path),
                "bytes": path.stat().st_size,
            }

        def producer_record(path: Path) -> dict[str, str]:
            return {"path": rel(path), "sha256": digest(path)}

        identity = dict(self.module.HISTORICAL_TRAINING_ALLOWED_JOBS[0])
        producer_head = self.module.HISTORICAL_TRAINING_PRODUCER_HEAD
        current_head = "8" * 40
        target = root / "training/job"
        target.mkdir(parents=True)
        data_root = root / "preprocess/data"
        data_root.mkdir(parents=True)
        preprocess_manifest = root / "preprocess/manifest.json"
        preprocess_manifest.write_text('{"state":"PASSED"}\n', encoding="utf-8")
        method_path = root / "method.py"
        method_path.write_text("METHOD = 'locked'\n", encoding="utf-8")
        training_config_path = root / "training_config.json"
        training_config_path.write_text('{"locked":true}\n', encoding="utf-8")
        training_driver_path = root / "training_driver.py"
        training_driver_path.write_text("DRIVER = 'locked'\n", encoding="utf-8")
        resolved_path = target / "resolved.json"
        resolved_payload = {"identity": identity, "recipe": "unchanged"}
        resolved_path.write_text(json.dumps(resolved_payload) + "\n", encoding="utf-8")
        override_path = target / "compose.json"
        override_path.write_text('{"network_mode":"none"}\n', encoding="utf-8")
        checkpoint_path = target / "ckpt/step_030000.pt"
        checkpoint_path.parent.mkdir()
        checkpoint_path.write_bytes(b"checkpoint-30000")
        final_checkpoint_path = target / "ckpt/final.pt"
        final_checkpoint_path.write_bytes(b"final-checkpoint")

        method_record = {"path": rel(method_path), "sha256": digest(method_path)}
        producer_method = {
            "branch": "exp/fusion-w1",
            "head": producer_head if historical else current_head,
            "files": [method_record],
        }
        current_method = {
            "branch": "exp/fusion-w1",
            "head": current_head,
            "files": [method_record],
        }
        preprocess = {
            "manifest": rel(preprocess_manifest),
            "manifest_sha256": digest(preprocess_manifest),
            "data_root": rel(data_root),
            "full_snapshot_sha256": "1" * 64,
            "training_artifact_snapshot_sha256": "2" * 64,
            "seed_canonical_npz_sha256": "3" * 64,
            "supervision_index_sha256": "4" * 64,
        }
        canonical_digest = lambda value: hashlib.sha256(
            self.module.canonical_json(value)
        ).hexdigest()
        materialization_path = target / "materialization.json"
        materialization = {
            "schema": "materialization.v1",
            "status": "PASSED",
            **identity,
            "git": producer_method,
            "driver_config": rel(training_config_path),
            "driver_config_sha256": digest(training_config_path),
            "locked_inputs": {"locked": "same"},
            "preprocess": preprocess,
            "recipe": {
                "resolved_scientific_config_sha256": canonical_digest(resolved_payload)
            },
            "resolved_config": rel(resolved_path),
            "resolved_config_sha256": digest(resolved_path),
            "compose_override": rel(override_path),
            "compose_override_sha256": digest(override_path),
            "output_dir": rel(target),
        }
        materialization_path.write_text(
            json.dumps(materialization, sort_keys=True) + "\n", encoding="utf-8"
        )
        started_path = target / "started.json"
        started = {
            "schema": "started.v1",
            "status": "STARTED",
            **identity,
            "method": producer_method,
            "materialization": producer_record(materialization_path),
        }
        started_path.write_text(json.dumps(started, sort_keys=True) + "\n", encoding="utf-8")
        completed_path = target / "completed.json"
        completed = {
            "schema": "completed.v1",
            "status": "COMPLETED",
            **identity,
            "return_code": 0,
            "started_receipt": producer_record(started_path),
            "materialization": producer_record(materialization_path),
            "training_completion": {
                "status": "PASSED",
                "profile": "full",
                "completed_optimizer_updates": 30000,
                "checkpoint": producer_record(checkpoint_path),
                "final_checkpoint": producer_record(final_checkpoint_path),
            },
        }
        completed_path.write_text(
            json.dumps(completed, sort_keys=True) + "\n", encoding="utf-8"
        )

        allowed = [dict(row) for row in self.module.HISTORICAL_TRAINING_ALLOWED_JOBS]
        locked_artifacts = {
            "materialization": record(materialization_path),
            "started": record(started_path),
            "completed": record(completed_path),
            "final_checkpoint": record(final_checkpoint_path),
        }
        recovery_path = root / "recovery.json"
        recovery = {
            "schema": self.module.HISTORICAL_TRAINING_RECOVERY_LOCK_SCHEMA,
            "state": "LOCKED_FOR_HISTORICAL_READOUT_RECOVERY",
            "branch": "exp/fusion-w1",
            "historical_training_reuse": {
                "producer_head": producer_head,
                "producer_head_must_be_ancestor": True,
                "method_files_must_be_current_identical": True,
                "allowed_jobs": allowed,
                "records": [
                    {"identity": row, **locked_artifacts}
                    for row in allowed
                ],
            },
        }
        recovery_path.write_text(
            json.dumps(recovery, sort_keys=True) + "\n", encoding="utf-8"
        )
        contract = {
            "schema": self.module.HISTORICAL_TRAINING_CONTRACT_SCHEMA,
            "enabled": True,
            "strict_current_head_default": True,
            "producer_head": producer_head,
            "allowed_jobs": allowed,
            "producer_head_must_be_ancestor": True,
            "method_files_must_be_current_identical": True,
            "completed_optimizer_updates": 30000,
            "recovery_lock_schema": self.module.HISTORICAL_TRAINING_RECOVERY_LOCK_SCHEMA,
            "recovery_lock_state": "LOCKED_FOR_HISTORICAL_READOUT_RECOVERY",
            "recovery_lock": record(recovery_path),
        }
        config = {
            "branch": "exp/fusion-w1",
            "historical_training_readout_reuse_contract": contract,
            "locked_inputs": {
                "training_driver": {
                    "path": rel(training_driver_path),
                    "sha256": digest(training_driver_path),
                }
            },
        }
        training_config = {
            "branch": "exp/fusion-w1",
            "method_files": [rel(method_path)],
            "outputs": {
                "materialization_manifest": "materialization.json",
                "started_receipt": "started.json",
                "completed_receipt": "completed.json",
                "failed_receipt": "failed.json",
                "resolved_config": "resolved.json",
                "compose_override": "compose.json",
            },
        }

        def check_materialization(**_kwargs):
            if historical:
                raise RuntimeError("launch HEAD vs materialization HEAD")
            return {
                "method_head": current_head,
                "resolved_config": rel(resolved_path),
                "resolved_config_sha256": digest(resolved_path),
            }

        fake_module = types.SimpleNamespace(
            MATERIALIZATION_SCHEMA="materialization.v1",
            STARTED_SCHEMA="started.v1",
            COMPLETED_SCHEMA="completed.v1",
            yaml=types.SimpleNamespace(safe_load=lambda stream: json.load(stream)),
            canonical_json_sha256=canonical_digest,
            job_dir=lambda *_args, **_kwargs: target,
            check_materialization=check_materialization,
            committed_method_gate=lambda *_args, **_kwargs: current_method,
            validate_locked_inputs=lambda *_args, **_kwargs: {"locked": "same"},
            validate_preprocess=lambda *_args, **_kwargs: dict(preprocess),
            build_training_config=lambda **_kwargs: dict(resolved_payload),
        )

        def fake_git(*arguments: str, check: bool = True):
            del check
            if arguments == ("rev-parse", "HEAD"):
                return subprocess.CompletedProcess(arguments, 0, current_head + "\n", "")
            if arguments[:2] == ("merge-base", "--is-ancestor"):
                return subprocess.CompletedProcess(arguments, 0, "", "")
            if arguments and arguments[0] == "rev-parse" and ":" in arguments[1]:
                return subprocess.CompletedProcess(arguments, 0, "blob-identical\n", "")
            raise AssertionError(f"unexpected git call: {arguments}")

        return temporary, {
            "root": root,
            "config": config,
            "training_config": training_config,
            "training_config_path": training_config_path,
            "training_driver_path": training_driver_path,
            "fake_module": fake_module,
            "fake_git": fake_git,
            "identity": identity,
            "current_head": current_head,
            "recovery_path": recovery_path,
            "completed_path": completed_path,
        }

    def test_python_source_parses_and_config_has_four_method_files(self):
        ast.parse(self.source)
        self.assertEqual(len(self.config["implementation_files"]), 4)
        self.assertEqual(
            self.config["implementation_files"][-1],
            "phases/p2-gsjso/scripts/test_fusion_w1_aprime_readout_20260726.py",
        )

    def test_primary_and_comparison_roles_are_disjoint(self):
        primary = self.config["primary"]
        alpha = self.config["legacy_alpha_comparison"]
        self.assertTrue(primary["eligible_for_preregistered_judgment"])
        self.assertFalse(alpha["eligible_for_preregistered_judgment"])
        self.assertTrue(alpha["comparison_only"])
        self.assertEqual(primary["score_time_z_shift_m"], 0.0)
        self.assertEqual(alpha["score_time_z_shift_m"], -45.7)
        self.assertNotEqual(primary["readout_role"], alpha["readout_role"])

    def test_strict_current_head_training_binding_remains_default(self):
        temporary, fixture = self.make_training_binding_fixture(historical=False)
        self.addCleanup(temporary.cleanup)
        with (
            patch.object(self.module, "REPO", fixture["root"]),
            patch.object(self.module, "git", side_effect=fixture["fake_git"]),
            patch.object(
                self.module,
                "training_module",
                return_value=(
                    fixture["fake_module"],
                    fixture["training_config"],
                    fixture["training_config_path"],
                ),
            ),
        ):
            result = self.module.resolve_training_binding(
                fixture["config"],
                fixture["identity"]["building_id"],
                fixture["identity"]["arm"],
                fixture["identity"]["replicate"],
            )
        self.assertEqual(result["binding_mode"], "strict_current_head")
        self.assertEqual(result["producer_head"], fixture["current_head"])
        self.assertIsNone(result["historical_reuse_proof"])

    def test_exact_allowlisted_historical_training_binding_revalidates_full_chain(self):
        temporary, fixture = self.make_training_binding_fixture(historical=True)
        self.addCleanup(temporary.cleanup)
        with (
            patch.object(self.module, "REPO", fixture["root"]),
            patch.object(self.module, "git", side_effect=fixture["fake_git"]),
            patch.object(
                self.module,
                "training_module",
                return_value=(
                    fixture["fake_module"],
                    fixture["training_config"],
                    fixture["training_config_path"],
                ),
            ),
        ):
            result = self.module.resolve_training_binding(
                fixture["config"],
                fixture["identity"]["building_id"],
                fixture["identity"]["arm"],
                fixture["identity"]["replicate"],
            )
        self.assertEqual(result["binding_mode"], "ancestor_identical_method")
        proof = result["historical_reuse_proof"]
        self.assertEqual(proof["producer_head"], self.module.HISTORICAL_TRAINING_PRODUCER_HEAD)
        self.assertEqual(proof["current_head"], fixture["current_head"])
        self.assertEqual(proof["preprocess_full_snapshot_sha256"], "1" * 64)
        self.assertEqual(proof["completed"]["path"], "training/job/completed.json")
        self.assertEqual(len(proof["method_blob_records"]), 1)

    def test_historical_fallback_is_closed_to_nonallowlisted_identity(self):
        temporary, fixture = self.make_training_binding_fixture(historical=True)
        self.addCleanup(temporary.cleanup)
        with (
            patch.object(self.module, "REPO", fixture["root"]),
            patch.object(self.module, "git", side_effect=fixture["fake_git"]),
            patch.object(
                self.module,
                "training_module",
                return_value=(
                    fixture["fake_module"],
                    fixture["training_config"],
                    fixture["training_config_path"],
                ),
            ),
        ):
            with self.assertRaisesRegex(
                self.module.AprimeReadoutError, "strict current-HEAD training binding failed"
            ):
                self.module.resolve_training_binding(
                    fixture["config"], "DEBY_LOD2_4908166", "Aprime", "r1"
                )

    def test_historical_binding_rejects_recovery_hash_and_method_blob_drift(self):
        temporary, fixture = self.make_training_binding_fixture(historical=True)
        self.addCleanup(temporary.cleanup)
        bad_hash = json.loads(json.dumps(fixture["config"]))
        bad_hash["historical_training_readout_reuse_contract"]["recovery_lock"][
            "sha256"
        ] = "0" * 64
        with (
            patch.object(self.module, "REPO", fixture["root"]),
            patch.object(self.module, "git", side_effect=fixture["fake_git"]),
        ):
            with self.assertRaisesRegex(self.module.AprimeReadoutError, "recovery lock SHA256"):
                self.module.verify_historical_training_binding(
                    config=bad_hash,
                    module=fixture["fake_module"],
                    training_config=fixture["training_config"],
                    config_path=fixture["training_config_path"],
                    building_id=fixture["identity"]["building_id"],
                    arm="Aprime",
                    run="r1",
                )

        def blob_drift(*arguments: str, check: bool = True):
            result = fixture["fake_git"](*arguments, check=check)
            if arguments and arguments[0] == "rev-parse" and arguments[1].startswith(
                fixture["current_head"]
            ):
                return subprocess.CompletedProcess(arguments, 0, "blob-drift\n", "")
            return result

        with (
            patch.object(self.module, "REPO", fixture["root"]),
            patch.object(self.module, "git", side_effect=blob_drift),
        ):
            with self.assertRaisesRegex(self.module.AprimeReadoutError, "git blob"):
                self.module.verify_historical_training_binding(
                    config=fixture["config"],
                    module=fixture["fake_module"],
                    training_config=fixture["training_config"],
                    config_path=fixture["training_config_path"],
                    building_id=fixture["identity"]["building_id"],
                    arm="Aprime",
                    run="r1",
                )

    def test_historical_contract_is_exactly_four_jobs_at_locked_producer(self):
        contract = {
            "schema": self.module.HISTORICAL_TRAINING_CONTRACT_SCHEMA,
            "enabled": True,
            "strict_current_head_default": True,
            "producer_head": self.module.HISTORICAL_TRAINING_PRODUCER_HEAD,
            "allowed_jobs": [
                dict(row) for row in self.module.HISTORICAL_TRAINING_ALLOWED_JOBS
            ],
            "producer_head_must_be_ancestor": True,
            "method_files_must_be_current_identical": True,
            "completed_optimizer_updates": 30000,
            "recovery_lock_schema": self.module.HISTORICAL_TRAINING_RECOVERY_LOCK_SCHEMA,
            "recovery_lock_state": "LOCKED_FOR_HISTORICAL_READOUT_RECOVERY",
            "recovery_lock": {
                "path": "future-lock.json",
                "sha256": "__PLACEHOLDER_SHA256__",
                "bytes": "__PLACEHOLDER_BYTES__",
            },
        }
        observed = self.module.historical_training_contract(
            {"historical_training_readout_reuse_contract": contract}
        )
        self.assertEqual(len(observed["allowed_jobs"]), 4)
        tampered = json.loads(json.dumps(contract))
        tampered["allowed_jobs"].append(
            {"building_id": "DEBY_LOD2_4908166", "arm": "Aprime", "replicate": "r1", "profile": "full"}
        )
        with self.assertRaisesRegex(self.module.AprimeReadoutError, "exact allowlist"):
            self.module.historical_training_contract(
                {"historical_training_readout_reuse_contract": tampered}
            )

    def test_primary_contract_is_exact_Mj_no_alpha_and_original_ground(self):
        required = set(self.config["primary"]["tsdf_required_checks"])
        self.assertIn("only_exact_M_j_support", required)
        self.assertIn("no_alpha_threshold", required)
        self.assertEqual(self.config["primary"]["surface_class"], 6)
        self.assertEqual(self.config["primary"]["ground_class"], 2)
        self.assertIn("original_ALS_class2", self.config["primary"]["readout_role"])
        self.assertIn("semantic_row_exact_concatenation", self.config["primary"]["join_method"])

    def test_identity_contract_has_exact_21_jobs(self):
        rows = self.module.target_rows(self.config)
        jobs = [
            (row["building_id"], "Aprime", replicate)
            for replicate in ("r1", "r2")
            for row in rows
        ]
        jobs.extend(
            (building_id, "B", "r1")
            for building_id in self.config["identity_contract"]["B_allowed"]
        )
        self.assertEqual(len(jobs), 21)
        self.assertEqual(len(jobs), self.config["identity_contract"]["expected_queue_jobs"])
        self.assertEqual(len(set(jobs)), 21)

    def test_arm_B_is_r1_and_subset_only(self):
        allowed = self.config["identity_contract"]["B_allowed"]
        self.module.validate_identity(self.config, allowed[0], "B", "r1", "full")
        with self.assertRaises(self.module.AprimeReadoutError):
            self.module.validate_identity(self.config, allowed[0], "B", "r2", "full")
        with self.assertRaises(self.module.AprimeReadoutError):
            self.module.validate_identity(
                self.config, "DEBY_LOD2_42364663", "B", "r1", "full"
            )

    def test_surface_npz_becomes_exact_class6_epsg25832_las(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            npz = root / "surface.npz"
            output = root / "surface.las"
            xyz = np.array(
                [[690000.001, 5334000.002, 510.003], [690001.004, 5334001.005, 511.006]],
                dtype=np.float64,
            )
            rgb = np.array([[1, 2, 3], [253, 254, 255]], dtype=np.uint8)
            np.savez_compressed(
                npz,
                xyz_epsg25832_orthometric=xyz,
                rgb=rgb,
                classification=np.full(2, 6, dtype=np.uint8),
                crs=np.array("EPSG:25832"),
                vertical_datum=np.array("orthometric"),
            )
            with patch.object(self.module, "REPO", root):
                result = self.module.write_surface_las(self.config, npz, output)
            self.assertEqual(result["class_counts"], {"6": 2})
            self.assertEqual(result["epsg"], 25832)
            self.assertEqual(result["point_count"], 2)
            self.assertEqual(result["RGB8_to_LAS16_mapping"], "value_times_257")

    def test_alpha_npz_is_comparison_only_geometry(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            npz = root / "alpha.npz"
            points = np.array([[1.0, 2.0, 3.0], [2.0, 3.0, 4.0]])
            np.savez_compressed(
                npz,
                P_utm=points,
                P_utm_clean=points,
                voxel=np.array(0.05),
                downscale=np.array(1.0),
            )
            with patch.object(self.module, "REPO", root):
                result = self.module.inspect_alpha_npz(self.config, npz)
            self.assertEqual(result["clean_points_n"], 2)
            self.assertFalse(result["semantic_arrays_present"])
            self.assertIn("ellipsoidal", result["vertical_frame"])

    def test_alpha_too_few_and_zero_class6_publish_nonassembly_observation(self):
        identity = {
            "building_id": "DEBY_LOD2_42364609",
            "arm": "Aprime",
            "replicate": "r1",
            "profile": "full",
        }
        for reason, counts, classified in (
            (
                "too_few_points_before_classification",
                {
                    "n_clip": 3,
                    "n_used": 3,
                    "n_building_in_fp": 0,
                    "class_counts": {},
                    "required_classes": [2, 6],
                    "missing_required_classes": [2, 6],
                },
                None,
            ),
            (
                "zero_class6_inside_footprint_after_SMRF_overlay",
                {
                    "n_clip": 20,
                    "n_used": 20,
                    "n_building_in_fp": 0,
                    "class_counts": {"2": 20},
                    "required_classes": [2, 6],
                    "missing_required_classes": [6],
                },
                {"path": "classified.las", "sha256": "a" * 64, "point_count": 20},
            ),
        ):
            with self.subTest(reason=reason), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                attempt = root / "attempt"
                classification = attempt / "legacy_alpha/classification"
                classification.mkdir(parents=True)
                invocation = attempt / "legacy_alpha/classification_invocation.json"
                metrics = classification / "metrics.json"
                artifact = classification / "partial.txt"
                invocation.write_text('{"state":"AUTHORIZED"}\n', encoding="utf-8")
                metrics.write_text('{"bid":"DEBY_LOD2_42364609"}\n', encoding="utf-8")
                artifact.write_text("preserved\n", encoding="utf-8")
                with patch.object(self.module, "REPO", root):
                    receipt = self.module.publish_alpha_nonassembly(
                        self.config,
                        attempt=attempt,
                        materialization={"identity": identity},
                        invocation_path=invocation,
                        metrics_path=metrics,
                        reason_code=reason,
                        counts=counts,
                        wall_seconds=1.0,
                        classified=classified,
                    )
                score = json.loads(
                    (attempt / "legacy_alpha/score.json").read_text(encoding="utf-8")
                )
                self.assertEqual(receipt["state"], "UNCONSTRUCTABLE")
                self.assertEqual(receipt["assembly_status"], "NOT_ASSEMBLED")
                self.assertEqual(receipt["roofer_runs_started"], 0)
                self.assertEqual(score["state"], "NOT_ASSEMBLED")
                self.assertEqual(score["measurement_status"], "NOT_MEASURED")
                self.assertFalse(score["eligible_for_preregistered_judgment"])
                self.assertEqual(score["reason_code"], reason)
                self.assertIsNone(score["canonical_score_row"])

    def test_artifact_ledger_rejects_symlink(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            attempt = root / "attempt"
            attempt.mkdir()
            (attempt / "real.txt").write_text("evidence\n", encoding="utf-8")
            (attempt / "link.txt").symlink_to(attempt / "real.txt")
            with patch.object(self.module, "REPO", root):
                with self.assertRaises(self.module.AprimeReadoutError):
                    self.module.artifact_ledger(attempt)

    def test_retry_is_three_same_errors_with_append_only_attempts(self):
        retry = self.config["retry_contract"]
        self.assertEqual(retry["same_error_attempts_before_skip"], 3)
        self.assertEqual(retry["attempt_number_max"], 999)
        self.assertTrue(retry["attempts_are_append_only"])
        self.assertIn("failure_signatures[-threshold:]", self.source)
        self.assertIn('attempt / "failure.json"', self.source)
        self.assertIn('exclusive_json(root_complete, payload)', self.source)

    def test_wrapper_is_offline_serial_nonroot_and_unbounded(self):
        self.assertIn("--network=none", self.wrapper)
        self.assertIn('--memory="$MEMORY_LIMIT"', self.wrapper)
        self.assertIn('--memory-swap="$MEMORY_LIMIT"', self.wrapper)
        self.assertIn('--user "$HOST_UID:$HOST_GID"', self.wrapper)
        self.assertIn('flock -n 9', self.wrapper)
        self.assertNotIn("timeout ", self.wrapper)
        self.assertIn("run_roofer_and_score", self.wrapper)

    def test_training_binding_control_steps_use_pyyaml_capable_pinned_dev_image(self):
        self.assertIn("run_control()", self.wrapper)
        self.assertIn('"$DEV_IMAGE" "$@"', self.wrapper)
        self.assertIn('run_control "$SCRIPT" --config "$CONFIG" check', self.wrapper)
        self.assertIn('attempt="$(run_control "$SCRIPT" --config "$CONFIG" begin', self.wrapper)
        self.assertIn('run_tools "$SCRIPT" --config "$CONFIG" prepare-primary', self.wrapper)

    def test_wrapper_runs_primary_before_legacy_and_finalizes_last(self):
        primary = self.wrapper.index("prepare-primary")
        alpha = self.wrapper.index("authorize-alpha-extract")
        finalize = self.wrapper.rindex('CURRENT_STAGE="finalize"')
        self.assertLess(primary, alpha)
        self.assertLess(alpha, finalize)
        self.assertIn("primary", self.wrapper[primary:alpha])
        self.assertIn("legacy_alpha", self.wrapper[alpha:finalize])
        self.assertIn("alpha-disposition", self.wrapper[alpha:finalize])
        self.assertIn("NOT_ASSEMBLED", self.wrapper[alpha:finalize])

    def test_no_scientific_verdict_fields_are_populated(self):
        self.assertIsNone(self.config["publication"]["interpretation_or_verdict"])
        self.assertIn('"interpretation_or_verdict": None', self.source)
        self.assertNotIn('"verdict": "PASS"', self.source)
        self.assertNotIn('"verdict": "FAIL"', self.source)


if __name__ == "__main__":
    unittest.main()
