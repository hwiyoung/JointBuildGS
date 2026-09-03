from __future__ import annotations

import unittest

import numpy as np

from scripts.phd.warp_ncc_v1 import run as wn


class WarpNccV1Test(unittest.TestCase):
    def test_config_contract(self):
        cfg = wn.load_config()
        self.assertIsNone(cfg["scientific_verdict"])
        self.assertEqual(len(cfg["algorithm"]["controls"]), wn.N_CONTROLS)
        self.assertEqual([c["name"] for c in cfg["algorithm"]["controls"]], ["M+z0.5", "M+z1", "M+z2", "M+x1"])
        self.assertEqual(cfg["inputs"]["evidence_bank_task_id"], "PHD-EVIDENCE-BANK-v1")

    def test_weighted_zncc_is_affine_invariant_and_detects_misalignment(self):
        rng = np.random.default_rng(0)
        S = 64
        a = rng.normal(size=(3, S)).astype(np.float32) * 20 + 100
        b = a * 1.7 - 30                              # affine copy → rho 1
        c = np.roll(a, 7, axis=1)                     # misaligned → low rho
        both = np.ones((3, S), dtype=bool); w = np.ones(S); n = np.full(3, S)
        rho_ab, ok_ab = wn.weighted_zncc_batch(a, b, both, w, n, 0.8, 30, 2.0)
        rho_ac, _ = wn.weighted_zncc_batch(a, c, both, w, n, 0.8, 30, 2.0)
        self.assertTrue(ok_ab.all()); np.testing.assert_allclose(rho_ab, 1.0, atol=1e-4)
        self.assertTrue(np.all(np.abs(rho_ac) < 0.6))
        flat = np.full((3, S), 50.0, dtype=np.float32)   # textureless → invalid, not zero
        rho_flat, ok_flat = wn.weighted_zncc_batch(flat, flat, both, w, n, 0.8, 30, 2.0)
        self.assertFalse(ok_flat.any()); self.assertTrue(np.all(np.isnan(rho_flat)))
        half = both.copy(); half[:, : S // 2] = False   # visible fraction below the floor → invalid
        _, ok_half = wn.weighted_zncc_batch(a, b, half, w, n, 0.8, 30, 2.0)
        self.assertFalse(ok_half.any())

    def test_bilinear_grid_interpolates_and_falls_back_to_nearest(self):
        z = np.array([[0.0, 1.0], [2.0, 3.0]]); low = np.array([0.0, 0.0, 0.0]); cell = 1.0
        # cell centres at 0.5 and 1.5: the midpoint (1.0, 1.0) is the mean of the four cells
        self.assertAlmostEqual(float(wn.bilinear_grid(z, np.array([1.0]), np.array([1.0]), low, cell)[0]), 1.5)
        # outside the bilinear support but inside the nearest cell: falls back to that cell
        self.assertAlmostEqual(float(wn.bilinear_grid(z, np.array([0.2]), np.array([0.2]), low, cell)[0]), 0.0)
        z2 = z.copy(); z2[0, 0] = np.nan
        # a NaN corner breaks the bilinear support; the nearest cell (0,0) is the NaN one → the sample is dropped (NaN)
        self.assertTrue(np.isnan(wn.bilinear_grid(z2, np.array([1.0]), np.array([1.0]), low, cell)[0]))
        # but a point whose nearest cell is valid keeps that cell's value even though one bilinear corner is NaN
        self.assertAlmostEqual(float(wn.bilinear_grid(z2, np.array([1.4]), np.array([1.4]), low, cell)[0]), 3.0)
        # beyond the grid: NaN
        self.assertTrue(np.isnan(wn.bilinear_grid(z, np.array([5.0]), np.array([5.0]), low, cell)[0]))

    def test_self_occlusion_via_supersampled_zbuffer(self):
        K = np.array([[100.0, 0, 50.0], [0, 100.0, 50.0], [0, 0, 1.0]]); R = np.eye(3); t = np.zeros(3)
        # a wall of points at depth 4 covering the image centre, a target at depth 10 behind it
        gx, gy = np.meshgrid(np.linspace(-0.2, 0.2, 41), np.linspace(-0.2, 0.2, 41))
        wall = np.column_stack((gx.ravel(), gy.ravel(), np.full(gx.size, 4.0)))
        zb = wn.zbuffer_depth(wall, R, t, K, 100, 100, 3, 1)
        self.assertEqual(zb.shape, (300, 300))
        u, v, z, px, py, inside = wn.project_pixels(np.array([[0.0, 0.0, 10.0], [0.0, 0.0, 3.0]]), R, t, K, 100, 100, 3)
        self.assertTrue(inside.all())
        occluded = z > zb[py, px] + 0.5
        self.assertEqual(list(occluded), [True, False])
        # image pixel x covers fine pixels 3x .. 3x+2
        self.assertEqual(int(np.floor(3 * 50.3 + 1.5)) // 3, int(np.floor(50.3 + 0.5)))

    def test_pair_selection_by_intersection_angle(self):
        ref = np.zeros(3)
        centres = {1: np.array([0.0, 0.0, 100.0]), 2: np.array([20.0, 0.0, 100.0]), 3: np.array([200.0, 0.0, 100.0])}
        pairs = wn.select_pairs([1, 2, 3], centres, ref, 3.0, 60.0, 2.0)
        ids = {(a, b) for a, b, _, _ in pairs}
        self.assertIn((0, 1), ids)          # ~11 deg
        self.assertNotIn((0, 2), ids)       # ~63 deg and distance ratio 2.2

    def test_depth_edges_attribute_to_the_nearer_side(self):
        depth = np.full((5, 6), 10.0, dtype=np.float32); depth[:, 3:] = 6.0; depth[0, 0] = np.inf
        rows, cols = wn.depth_edge_pixels(depth, 1.0)
        self.assertTrue(np.all(cols == 3))  # the nearer (6 m) column
        self.assertEqual(len(rows), 5)

    def test_rank_auc(self):
        self.assertEqual(wn.rank_auc(np.arange(10) + 10.0, np.arange(10) * 1.0), 1.0)
        self.assertAlmostEqual(wn.rank_auc(np.ones(10), np.ones(10)), 0.5)
        self.assertIsNone(wn.rank_auc(np.ones(2), np.ones(10)))

    def test_expectation_checker(self):
        summary = {"COMPATIBLE": {"planar": {"n_pairs_m_median": 4.0, "power_m_fraction": 0.7, "ncc_median_m": 0.9, "delta_median": 0.01, "f_m_over_p_median": 0.1, "f_p_over_m_median": 0.1,
                                             "edge_dist_median_px_m": 3.0, "edge_dist_median_px_p": 3.4}},
                   "PRIOR_ABOVE": {"planar": {"n_views_p_median": 12.0, "n_views_m_median": 6.0, "delta_median": 0.5, "f_m_over_p_median": 0.9, "ncc_median_p": 0.2,
                                              "edge_dist_median_px_m": 3.0, "edge_dist_median_px_p": 8.0}}}
        controls = {"M+z2": {"auc": 0.95}, "M+z1": {"auc": 0.8}, "M+z0.5": {"auc": 0.5}, "M+x1": {"auc": 0.52}}
        res = wn.eval_expectations(summary, controls)
        self.assertEqual(res["COMPATIBLE"]["met"], 6); self.assertEqual(res["PRIOR_ABOVE"]["met"], 5)
        self.assertEqual(res["CONTROLS"]["met"], 3); self.assertEqual(res["CONTROLS"]["total"], 4)
        # H_M site: the same numbers fail the mirrored expectation (images should support P there)
        summary["PRIOR_ABOVE"]["planar"].update({"f_p_over_m_median": 0.05, "ncc_median_m": 0.8})
        flipped = wn.eval_expectations(summary, controls, {"PRIOR_ABOVE": {"delta_sign": -1}})
        self.assertEqual(flipped["PRIOR_ABOVE"]["met"], 1)
        self.assertIn("2D-a delta <= -0.2 (P explains images)", flipped["PRIOR_ABOVE"]["checks"])


if __name__ == "__main__":
    unittest.main()
