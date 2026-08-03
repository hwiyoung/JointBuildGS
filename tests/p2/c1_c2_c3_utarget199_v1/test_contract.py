from __future__ import annotations

import json
from pathlib import Path
import unittest

import yaml


REPO = Path(__file__).resolve().parents[3]
ROOT = REPO / "configs/p2/c1_c2_c3_utarget199_v1"


class UTarget199C123ContractTests(unittest.TestCase):
    def test_all_199_and_reference_cohorts_are_not_display_conditions(self):
        contract = json.loads((ROOT / "contract_v1.json").read_text(encoding="utf-8"))
        self.assertEqual(contract["target_buildings"], 199)
        self.assertTrue(contract["evaluation"]["all_199_case_sheets"])
        self.assertFalse(contract["evaluation"]["reference_cohort_labels_visible"])
        self.assertIsNone(contract["evaluation"]["scientific_verdict"])
        self.assertEqual(
            contract["common_image_seed"]["candidate_voxel_m"],
            [0.5, 1.0, 2.0, 4.0, 8.0, 16.0],
        )
        self.assertEqual(
            contract["common_image_seed"]["recovery_namespace"],
            "P2-C1-C2-C3-UTARGET199-SEED-RECOVERY-v1",
        )
        self.assertEqual(
            contract["paired_training"]["sequential_gpu"],
            "AUTO_EXCLUSIVE_MIN_FREE_22000_MIB",
        )

    def test_common_seed_is_sparse_plus_neutral_sampled_dense(self):
        contract = json.loads((ROOT / "contract_v1.json").read_text(encoding="utf-8"))
        seed = contract["common_image_seed"]
        self.assertEqual(seed["sfm_sparse_points"], 371_808)
        self.assertEqual(seed["dense_point_cap"], 220_000)
        self.assertLessEqual(seed["maximum_initial_gaussians"], 600_000)
        self.assertFalse(seed["classification_filtering"])
        self.assertFalse(seed["footprint_filtering"])
        self.assertTrue(seed["reuse_for_future_c4_c5"])

    def test_c3_pair_differs_only_in_depth_keys(self):
        c31 = yaml.safe_load((ROOT / "c3_1_sem_seed0.yaml").read_text(encoding="utf-8"))
        c32 = yaml.safe_load((ROOT / "c3_2_sem_depth_seed0.yaml").read_text(encoding="utf-8"))
        allowed = {"load_depth", "w_depth", "out_dir"}
        differences = {key for key in set(c31) | set(c32) if c31.get(key) != c32.get(key)}
        self.assertEqual(differences, allowed)
        self.assertFalse(c31["load_depth"])
        self.assertEqual(c31["w_depth"], 0.0)
        self.assertTrue(c32["load_depth"])
        self.assertEqual(c32["w_depth"], 0.03)
        for cfg in (c31, c32):
            self.assertEqual(cfg["seed"], 0)
            self.assertEqual(cfg["exact_view_count"], 937)
            self.assertEqual(cfg["max_iter"], 30_000)
            self.assertEqual(cfg["w_sem"], 0.1)
            self.assertEqual(cfg["w_structure"], 0.0)
            self.assertEqual(cfg["w_mutual"], 0.0)
            self.assertEqual(cfg["w_mvc"], 0.0)
            self.assertEqual(cfg["max_gaussians"], 800_000)
            self.assertIsNone(cfg["scientific_verdict"])


if __name__ == "__main__":
    unittest.main()
