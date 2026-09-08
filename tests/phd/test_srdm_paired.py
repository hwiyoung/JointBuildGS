"""Synthetic pixel joins and coverage changes; no research/reference payloads."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest

import numpy as np

SPEC = importlib.util.spec_from_file_location("srdm_paired", Path(__file__).resolve().parents[2] /
                                            "scripts/phd/srdm_p1p2p3_v1/analyze_paired.py")
paired = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(paired)


class SRDMPairedTests(unittest.TestCase):
    def test_point_order_and_evaluation_order_do_not_change_pixel_alignment(self):
        domain = {"bbox_min": [0, 0, 0], "bbox_max": [3, 3, 3]}
        payload = {"xyz": np.array([[1.2, .2, .5], [.2, .2, .5], [2.2, .2, .5]]),
                   "pixel_uv": np.array([[2, 0], [0, 0], [1, 0]]),
                   "valid": np.ones((1, 3), bool), "disparity": np.ones((1, 3)),
                   "interpolated_mask": np.array([[False, True, False]])}
        raw = {"candidate_source_index": np.array([1, 2, 0]),
               "candidate_to_reference": np.array([.1, .2, .9]),
               "interpolated": np.array([False, True, False])}
        rays = paired.measured_rays(payload, raw, domain, 1., np.array([0]), (1, 3))
        np.testing.assert_array_equal(rays["pixel_id"], [0, 2])
        np.testing.assert_array_equal(rays["source_row"], [1, 0])
        np.testing.assert_allclose(rays["distance"], [.1, .9])
        np.testing.assert_array_equal(rays["reference_xy_support"], [True, False])
        self.assertEqual(rays["interpolated_points_in_roi"], 1)
        bad = {**raw, "interpolated": np.array([False, False, True])}
        with self.assertRaisesRegex(ValueError, "interpolation flags"):
            paired.measured_rays(payload, bad, domain, 1., np.array([0]), (1, 3))

    def test_common_three_pair_only_gain_loss_and_unknown_support_are_separate(self):
        def arm(ids, distances, supported):
            return {"pixel_id": np.array(ids), "source_row": np.arange(len(ids)),
                    "distance": np.array(distances), "reference_xy_support": np.array(supported, bool)}
        rays = {paired.ev.ARMS[0]: arm([0, 1], [.8, .2], [1, 1]),
                paired.ev.ARMS[1]: arm([0, 1, 2, 4], [1., .1, 2., .8], [1, 1, 0, 0]),
                paired.ev.ARMS[2]: arm([0, 1, 3, 4], [.2, .7, 1., .7], [1, 0, 0, 0])}
        table = paired.align_rays(rays)
        np.testing.assert_array_equal(table["pixel_id"], [0, 1, 2, 3, 4])
        summary = paired.comparison_summary(table, 1, 2, True)
        self.assertEqual(summary["common_all_three_primary"]["n_pixels"], 2)
        self.assertEqual(summary["both_measured_pixels"], 3)
        self.assertEqual(summary["gained_measured_pixels"], 1)
        self.assertEqual(summary["lost_measured_pixels"], 1)
        self.assertEqual(summary["net_measured_pixels"], 0)
        changes = summary["common_all_three_primary"]["threshold_counts_m"]["0.5"]
        self.assertEqual(changes["distance_reduction_ge"], 1)
        self.assertEqual(changes["distance_increase_ge"], 1)
        self.assertEqual(summary["common_all_three_reference_xy_support"]["only_before_supported"]["count"], 1)
        self.assertEqual(summary["common_pair_reference_xy_support"]["neither_supported_unknown"]["count"], 1)
        self.assertEqual(summary["gained"]["reference_xy_absent_unknown"], 1)
        self.assertEqual(summary["lost"]["reference_xy_absent_unknown"], 1)
        self.assertAlmostEqual(summary["common_all_three_primary"]["mean_delta_m"], -.1)


if __name__ == "__main__":
    unittest.main()
