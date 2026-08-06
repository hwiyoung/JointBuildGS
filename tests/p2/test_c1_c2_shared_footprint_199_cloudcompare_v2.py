from __future__ import annotations

import unittest

from scripts.p2.c1_c2_shared_footprint_199_v2 import build_cloudcompare


class SharedFootprint199CloudCompareV2Tests(unittest.TestCase):
    def test_config_matches_all_invocation_counts(self) -> None:
        config = build_cloudcompare.load_config(build_cloudcompare.DEFAULT_CONFIG)
        self.assertEqual(config["methods"]["C1_L_upper"]["expected_lod22_groups"], 106)
        self.assertEqual(config["methods"]["C2_MVS"]["expected_lod22_groups"], 126)
        self.assertEqual(config["expected_paired_lod22"], 96)
        self.assertIsNone(config["scientific_verdict"])


if __name__ == "__main__":
    unittest.main()
