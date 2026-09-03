from __future__ import annotations

import unittest

import numpy as np

from scripts.phd.evidence_bank_v1 import run as eb


class EvidenceBankV1Test(unittest.TestCase):
    def test_ray_classification_matches_d3a(self):
        inf = np.inf
        z_m = np.array([[10.0, 10.0, 10.0, 10.0, inf, inf, 10.0]])
        z_p = np.array([[10.2, 6.0, 14.0, inf, 8.0, inf, 10.1]])
        z_occ = np.array([[inf, inf, inf, inf, inf, inf, 5.0]])
        cls = eb.classify_rays(z_m, z_p, z_occ, 0.5)[0]
        self.assertEqual(list(cls), [eb.RAY_AGREE, eb.RAY_PENETRATE, eb.RAY_BLOCK, eb.RAY_MVS_ONLY, eb.RAY_NO_LANDING, -1, eb.RAY_OCCLUDED])

    def test_zbuffer_keeps_nearest_point_and_label(self):
        K = np.array([[100.0, 0, 50.0], [0, 100.0, 50.0], [0, 0, 1.0]])
        R = np.eye(3); t = np.zeros(3)
        pts = np.array([[0.0, 0.0, 10.0], [0.0, 0.0, 4.0], [0.1, 0.0, 20.0]])
        labels = np.array([7, 3, 9])
        depth, label = eb.zbuffer(pts, labels, R, t, K, 100, 100, 0)
        self.assertAlmostEqual(float(depth[50, 50]), 4.0)
        self.assertEqual(int(label[50, 50]), 3)
        self.assertTrue(np.isinf(depth[0, 0])); self.assertEqual(int(label[0, 0]), -1)

    def test_texture_map_is_zero_on_flat_and_positive_on_edges(self):
        img = np.zeros((40, 40), dtype=np.uint8); img[:, 20:] = 200
        tex = eb.texture_map(img, 7)
        self.assertLess(float(tex[20, 5]), 1e-3); self.assertGreater(float(tex[20, 20]), 50.0)

    def test_expectation_checker(self):
        summary = {"PRIOR_ABOVE": {"core_d_median_m": 3.2, "f_penetrate_mean": 0.8, "f_agree_mean": 0.1, "f_block_mean": 0.1, "r_ge3_fraction": 0.9, "r_le1_fraction": 0.0, "n_no_landing": 0, "n_tested": 10, "n_mvs_only": 0},
                   "COMPATIBLE": {"core_d_median_m": 0.05, "f_penetrate_mean": 0.05, "f_agree_mean": 0.9, "f_block_mean": 0.05, "r_ge3_fraction": 0.7, "r_le1_fraction": 0.0, "n_no_landing": 0, "n_tested": 10, "n_mvs_only": 0}}
        cfg = eb.load_config()
        res = eb.eval_expectations(summary, cfg["expectations_before_run"])
        self.assertEqual(res["PRIOR_ABOVE"]["met"], 3); self.assertEqual(res["COMPATIBLE"]["met"], 3); self.assertFalse(res["PRIOR_ONLY"]["present"])


if __name__ == "__main__":
    unittest.main()
