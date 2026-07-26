#!/usr/bin/env python3
"""Focused Docker tests for the production A-prime readout driver."""
from __future__ import annotations

import ast
import importlib.util
import json
import tempfile
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
