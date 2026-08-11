"""Artifact-independent checks for the E4/E5/E6 redesign S0 namespace."""
from __future__ import annotations

import unittest
from pathlib import Path

import yaml

from scripts.p2.e4_e6_redesign_s0_v1.s0a_legacy_e3_auto_ox import no_g2_verdict

REPO = Path(__file__).resolve().parents[2]


class S0ConfigTest(unittest.TestCase):
    def test_common_config_contract(self) -> None:
        config = yaml.safe_load(
            (REPO / "configs/p2/e4_e6_redesign_s0_v1/s0_v1.yaml").read_text(encoding="utf-8")
        )
        self.assertEqual(config["task_id"], "P2-E4-E6-REDESIGN-S0-v1")
        self.assertIsNone(config["scientific_verdict"])
        self.assertIsNone(config["official_PASS_usable"])
        targets = config["projection_prototype"]["qa_targets"]
        self.assertLessEqual(targets["gt2m_fraction_max"], 0.25)
        self.assertEqual(config["projection_prototype"]["classes"], [2, 6])

    def test_plan_document_exists(self) -> None:
        plan = REPO / yaml.safe_load(
            (REPO / "configs/p2/e4_e6_redesign_s0_v1/s0_v1.yaml").read_text(encoding="utf-8")
        )["plan"]
        self.assertTrue(plan.is_file())


class NoG2VerdictTest(unittest.TestCase):
    def test_na_passthrough(self) -> None:
        row = {"verdict": "NA", "G0_status": "O", "G1_status": "O", "G3_status": "NA", "G4_status": "NA"}
        self.assertEqual(no_g2_verdict(row), "NA")

    def test_g2_only_failure_recovers(self) -> None:
        row = {"verdict": "X", "G0_status": "O", "G1_status": "O", "G3_status": "O", "G4_status": "O"}
        self.assertEqual(no_g2_verdict(row), "O")

    def test_other_gate_failure_stays_x(self) -> None:
        row = {"verdict": "X", "G0_status": "O", "G1_status": "O", "G3_status": "X", "G4_status": "O"}
        self.assertEqual(no_g2_verdict(row), "X")


if __name__ == "__main__":
    unittest.main()
