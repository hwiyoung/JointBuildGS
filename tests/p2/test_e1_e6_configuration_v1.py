from __future__ import annotations

import json
import unittest
from pathlib import Path

import yaml


class E1E6ConfigurationContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(__file__).resolve().parents[2]
        self.config = self.root / "configs/p2/e1_e6_techdev_v1"

    def test_condition_order_and_nonconfirmatory_boundary(self) -> None:
        contract = json.loads((self.config / "contract.json").read_text(encoding="utf-8"))
        self.assertEqual(
            contract["conditions"],
            [
                "E1_LIDAR_ROOFER",
                "E2_MVS_ROOFER",
                "E3_GS_IMAGE",
                "E4_GS_ALS_UNWEIGHTED",
                "E5_GS_ALS_WB",
                "E6_GS_LOD2_PLANES_DIAGNOSTIC",
            ],
        )
        self.assertIsNone(contract["official_PASS_usable"])
        self.assertIsNone(contract["scientific_verdict"])

    def test_e4_e5_overlays_differ_only_by_identity_output_and_wb_flag(self) -> None:
        e4 = json.loads((self.config / "e4.json").read_text(encoding="utf-8"))
        e5 = json.loads((self.config / "e5.json").read_text(encoding="utf-8"))
        differing = {key for key in set(e4) | set(e5) if e4.get(key) != e5.get(key)}
        self.assertEqual(
            differing,
            {"condition_id", "out_dir", "external_als_apply_building_weight"},
        )
        self.assertFalse(e4["external_als_apply_building_weight"])
        self.assertTrue(e5["external_als_apply_building_weight"])

    def test_common_seed_subsample_is_locked(self) -> None:
        common = yaml.safe_load((self.config / "common_gs.yaml").read_text(encoding="utf-8"))
        self.assertEqual(common["init_pointcloud_max_points"], 300000)
        self.assertEqual(common["init_pointcloud_subsample_seed"], 0)
        self.assertEqual(common["depth_loss"], "huber")
        self.assertEqual(common["depth_warmup"], 2000)
        self.assertEqual(common["depth_ramp_steps"], 2000)
        self.assertEqual(common["normal_prior_orientation"], "signed")
        self.assertEqual(common["normal_warmup"], 2000)
        self.assertEqual(common["normal_ramp_steps"], 2000)


if __name__ == "__main__":
    unittest.main()
