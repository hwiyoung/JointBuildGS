import unittest

from scripts.p2.c3_tsdf_roof_diagnostic_v1.contract import load_config, validate_config


class ContractTest(unittest.TestCase):
    def test_config_is_activated_and_bounded(self):
        result = validate_config(load_config())
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["building_count"], 3)
        self.assertIsNone(result["scientific_verdict"])

    def test_tsdf_and_poisson_share_roof_evidence_contract(self):
        config = load_config()
        self.assertEqual(config["surface"]["semantic_roof_class"], 1)
        self.assertEqual(config["shared_view_plan"]["maximum_views_per_building"], 24)
        self.assertEqual(config["surface"]["minimum_distinct_views"], 2)
        self.assertGreaterEqual(
            config["surface"]["tsdf_truncation_m"],
            2 * config["surface"]["tsdf_voxel_m"],
        )

    def test_depth_is_only_substantive_condition_difference(self):
        left = "configs/p2/c1_c2_c3_utarget199_v1/c3_1_sem_seed0.yaml"
        right = "configs/p2/c1_c2_c3_utarget199_v1/c3_2_sem_depth_seed0_gpu0_recovery.yaml"
        from pathlib import Path
        import yaml

        a = yaml.safe_load(Path(left).read_text(encoding="utf-8"))
        b = yaml.safe_load(Path(right).read_text(encoding="utf-8"))
        ignored = {"out_dir", "load_depth", "w_depth"}
        self.assertEqual({k: v for k, v in a.items() if k not in ignored}, {k: v for k, v in b.items() if k not in ignored})
        self.assertFalse(a["load_depth"])
        self.assertTrue(b["load_depth"])
        self.assertEqual(a["w_depth"], 0.0)
        self.assertEqual(b["w_depth"], 0.03)


if __name__ == "__main__":
    unittest.main()
