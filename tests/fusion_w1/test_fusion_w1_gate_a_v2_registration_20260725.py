#!/usr/bin/env python3
from __future__ import annotations

import ast
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "phases/p2-gsjso/scripts/fusion_w1/fusion_w1_gate_a_v2_registration_20260725.py"
CONFIG = REPO / "phases/p2-gsjso/configs/fusion_w1/fusion_w1_gate_a_v2_registration_20260725.json"


def load_module():
    spec = importlib.util.spec_from_file_location("gate_a_v2_registration", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class GateAV2RegistrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = load_module()
        cls.config = json.loads(CONFIG.read_text(encoding="utf-8"))

    def test_r1_manifest_is_the_only_pose_input(self):
        contract = self.config["r1_consumer_contract"]
        self.assertEqual(
            contract["manifest"],
            "phases/p2-gsjso/runs/fusion_w1/20260724_fusion_w1/resume_v2/"
            "r1_pose_adoption_manifest.json",
        )
        self.assertEqual(
            contract["schema"],
            "jointbuildgs.fusion_w1.pose_adoption_v2.manifest.v1",
        )
        serialized = json.dumps(self.config)
        self.assertNotIn("derived_sparse/0", serialized)

    def test_r1_once_and_immutability_fields_are_locked(self):
        contract = self.config["r1_consumer_contract"]
        self.assertEqual(contract["transform_application_count"], 1)
        self.assertEqual(contract["application_scope"], "all_937_camera_poses_once")
        source = SCRIPT.read_text(encoding="utf-8")
        for token in (
            '"als_source_modified": False',
            '"source_pose_modified": False',
            '"derived_pose_differs_from_source": True',
        ):
            self.assertIn(token, source)

    def test_locked_numeric_slots_are_exact(self):
        slots = self.config["gate_a_v2_locked_slots"]
        self.assertEqual(
            (
                slots["n_threshold"],
                slots["population_n"],
                slots["correspondence_capable_n"],
                slots["capable_matched_median_le_0p3_n"],
                slots["core_correspondence_capable_n"],
                slots["core_capable_matched_median_le_0p3_n"],
            ),
            (40, 178, 132, 132, 24, 24),
        )
        self.assertEqual(
            slots["incapable_tier_counts"],
            {"surface": 2, "height": 11, "outline": 33},
        )
        self.assertEqual(slots["numeric_source_role"], "reuse_only_no_remeasurement")

    def test_current_locked_csv_reproduces_only_declared_slots(self):
        observed, targets = self.module.validate_locked_slots(self.config)
        self.assertEqual(len(targets), 178)
        self.assertEqual(observed["correspondence_capable_n"], 132)
        self.assertEqual(observed["core_correspondence_capable_n"], 24)
        self.assertEqual(observed["incapable_tier_counts"], {
            "surface": 2,
            "height": 11,
            "outline": 33,
        })

    def test_runtime_requires_committed_clean_method_and_r1_manifest(self):
        self.assertEqual(
            self.config["required_ancestor_commit"],
            "03f6a71c883ea2bb5e371f6cb185e4d921841d8e",
        )
        self.assertEqual(len(self.config["implementation_files"]), 4)
        source = SCRIPT.read_text(encoding="utf-8")
        self.assertIn("verify_git_lock(config, outputs)", source)
        self.assertIn(
            'config["r1_consumer_contract"]["manifest"]',
            source,
        )

    def test_overlay_population_is_all_core_28(self):
        overlay = self.config["overlay_contract"]
        self.assertEqual(overlay["expected_buildings"], 28)
        self.assertIn("four_correspondence_incapable", overlay["population"])
        self.assertEqual(overlay["projection_xy_shift_m"], [0.0, 0.0])
        self.assertIn("display_only", overlay["selection_role"])

    def test_forbidden_edge_and_gate_functions_are_not_called(self):
        tree = ast.parse(SCRIPT.read_text(encoding="utf-8"))
        called = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    called.add(node.func.id)
                elif isinstance(node.func, ast.Attribute):
                    called.add(node.func.attr)
        self.assertTrue(
            set(self.config["overlay_contract"]["forbidden_calls"]).isdisjoint(called)
        )

    def test_manifest_is_written_after_png_and_index_publication(self):
        source = SCRIPT.read_text(encoding="utf-8")
        move_overlay = source.index('os.replace(staging_overlay, outputs["overlay_dir"])')
        move_index = source.index('os.replace(staged_index, outputs["overlay_index"])')
        write_manifest = source.index('atomic_json(outputs["manifest"], manifest)')
        self.assertLess(move_overlay, write_manifest)
        self.assertLess(move_index, write_manifest)

    def test_sources_are_rehashed_before_publication(self):
        source = SCRIPT.read_text(encoding="utf-8")
        second_input_hash = source.index(
            "observed_inputs_after = verify_small_inputs(config)"
        )
        move_overlay = source.index(
            'os.replace(staging_overlay, outputs["overlay_dir"])'
        )
        self.assertLess(second_input_hash, move_overlay)
        self.assertIn('"unchanged": True', source)

    def test_exact_once_claim_rejects_second_writer(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "claim.json"
            self.module.exclusive_json(path, {"state": "STARTED"})
            with self.assertRaises(FileExistsError):
                self.module.exclusive_json(path, {"state": "STARTED"})

    def test_issues_is_not_an_output(self):
        self.assertNotIn(
            "issues.md",
            json.dumps(self.config["outputs"], ensure_ascii=False),
        )


if __name__ == "__main__":
    unittest.main()
