from __future__ import annotations

import unittest

import numpy as np

from scripts.p2.qualitative_199_cloudcompare_scene_v1 import add_lidar_visual_sample as sample


class LidarVisualSampleV1Tests(unittest.TestCase):
    def test_config_defines_exact_visual_only_sample(self) -> None:
        config = sample.load_config(sample.DEFAULT_CONFIG)
        self.assertEqual(config["sampling"]["target_points"], 10_000_000)
        self.assertFalse(config["scientific_use_allowed"])
        self.assertIsNone(config["scientific_verdict"])

    def test_affine_permutation_threshold_selects_exact_target(self) -> None:
        source_points = 17
        target_points = 5
        selected = []
        for start, count in ((0, 4), (4, 7), (11, 6)):
            mask = sample.selected_mask(start, count, source_points, target_points, 5, 3)
            selected.extend((np.arange(start, start + count)[mask]).tolist())
        self.assertEqual(len(selected), target_points)
        self.assertEqual(len(set(selected)), target_points)


if __name__ == "__main__":
    unittest.main()
