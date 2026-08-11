import unittest
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]


class RingGroundContractTest(unittest.TestCase):
    def test_single_readout_variable_and_six_frozen_sources(self):
        cfg = yaml.safe_load((ROOT / "configs/p2/e3_local_4906982_ring_ground_roofer_v1/experiment.yaml").read_text())
        self.assertEqual(cfg["ground_height"]["exterior_ring_outer_m"], 4.0)
        self.assertEqual(cfg["ground_height"]["quantile"], 0.05)
        self.assertEqual(cfg["roofer"]["h_terrain_strategy"], "user")
        self.assertEqual(len(cfg["cases"]), 6)
        self.assertIsNone(cfg["scientific_verdict"])

    def test_prohibited_training_source_is_not_edited_by_runner(self):
        text = (ROOT / "scripts/p2/e3_local_4906982_ring_ground_roofer_v1/run.py").read_text()
        self.assertNotIn("src/stage2/loss/multiview.py", text)
        self.assertIn("inside_footprint_excluded", text)
        self.assertIn("--h-terrain-strategy", text)


if __name__ == "__main__":
    unittest.main()
