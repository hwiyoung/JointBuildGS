"""Hand-made scenes for metric module v3 (PHD-MAIN-STAGE1-v1 3.5): common alignment, premise violation and band, thinning, gate."""
import filecmp
import unittest
from pathlib import Path

import numpy as np

from src.phd.metrics_v3 import align, gate, premise, thin

ROOT = Path(__file__).resolve().parents[2]


class CopiedV3(unittest.TestCase):
    def test_v2_files_unchanged(self):
        for f in ("surface", "lines", "cloud", "gauss", "cells", "band", "stats", "regions", "bins", "readings"):
            self.assertTrue(filecmp.cmp(ROOT / f"src/phd/metrics_v2/{f}.py", ROOT / f"src/phd/metrics_v3/{f}.py", shallow=False), f)


class Align(unittest.TestCase):
    def test_select_pixels(self):
        d, src = align.select_pixels(np.zeros(10), np.ones(20), min_px=5)
        self.assertEqual(src, "range")
        self.assertEqual(len(d), 10)
        d, src = align.select_pixels(np.zeros(3), np.ones(20), min_px=5)
        self.assertEqual(src, "range + 20 m")
        self.assertEqual(len(d), 20)

    def test_pooled_median_counts_each_pixel_once(self):
        med, n = align.pooled_median([np.full(3, 1.0), np.full(1, 10.0)])
        self.assertEqual(n, 4)
        self.assertEqual(med, 1.0)                         # three pixels at 1, one at 10: not the mean of the box medians

    def test_two_pass_converges_and_reproduces_one_box(self):
        offs = {"a": -0.05, "b": 0.04}                     # MVS - GT of each box before any move
        rng = np.random.default_rng(0)
        noise = {b: rng.normal(0, 0.01, 2000) for b in offs}

        def diff_fn(b, shift):
            d = offs[b] - shift + noise[b]                 # moving the GT up by `shift` lowers MVS - GT by `shift`
            return d, d
        total, rec = align.two_pass(diff_fn, ["a", "b"], min_px=100)
        self.assertAlmostEqual(rec[1]["median"], 0.0, places=9)
        both = np.concatenate([offs[b] + noise[b] for b in offs])
        self.assertAlmostEqual(total, float(np.median(both)), places=9)
        one, _ = align.two_pass(diff_fn, ["a"], min_px=100)            # one box alone = the per-box rule
        self.assertAlmostEqual(one, float(np.median(offs["a"] + noise["a"])), places=9)


class Premise(unittest.TestCase):
    def test_violation_within_band(self):
        code = np.array([3, 3, 3, 2, 2, 2, 11])
        pv = np.array([0.5, -0.5, 0.1, 0.0, 0.0, 0.0, 2.0])
        tau = np.full(7, 0.2)
        centre = np.array([[0, 0, 0], [10, 0, 0], [20, 0, 0], [1.9, 0, 0], [0, 2.1, 0], [20, 1.0, 0], [0, 0, 0.5]], float)
        v, w, b = premise.split(code, pv, tau, 1.0, centre, radius=2.0)
        self.assertEqual(v.tolist(), [True, True, False, False, False, False, False])     # |m| > 1 tau on code 3 only
        self.assertEqual(w.tolist(), [False, False, True, False, False, False, False])
        self.assertEqual(b.tolist(), [False, False, False, True, False, False, False])     # within-threshold patches make no band
        v2, w2, _ = premise.split(code, pv, tau, 2.0, centre)                              # ALS: 2 tau
        self.assertEqual(v2.tolist(), [True, True, False, False, False, False, False])
        v3, _, b3 = premise.split(code, np.array([0.3, 0, 0, 0, 0, 0, 0.0]), tau, 2.0, centre)
        self.assertFalse(v3.any())
        self.assertFalse(b3.any())

    def test_nan_premise_value_is_not_a_violation(self):
        v, w, b = premise.split(np.array([3]), np.array([np.nan]), np.array([0.2]), 1.0, np.zeros((1, 3)))
        self.assertFalse(v[0])
        self.assertTrue(w[0])


class Thin(unittest.TestCase):
    def test_roof_cells_nearest_point(self):
        xy = np.array([[0.01, 0.01], [0.05, 0.05], [0.06, 0.04], [0.15, 0.05], [0.149, 0.051]])
        k = thin.keep_nearest(xy, 0.1)
        self.assertEqual(k.tolist(), [False, True, False, True, False])    # cell (0,0): the centre point; cell (1,0): nearer to (0.15, 0.05)

    def test_tie_lowest_index_and_groups(self):
        xy = np.array([[0.125, 0.25], [0.375, 0.25], [0.125, 0.25]])     # exact tie around the centre (0.25, 0.25) of a 0.5 m cell
        self.assertEqual(thin.keep_nearest(xy, 0.5).tolist(), [True, False, False])
        self.assertEqual(thin.keep_nearest(xy, 0.5, group=[0, 0, 1]).tolist(), [True, False, True])

    def test_wall_plane_cells(self):
        n = np.tile([1.0, 0.0, 0.0], (4, 1))            # wall facing +x: s runs along y
        X = np.array([[5.0, 0.05, 1.05], [5.3, 0.04, 1.06], [5.0, 0.05, 1.15], [5.0, 0.15, 1.05]])
        sz = thin.wall_coords(X, n)
        np.testing.assert_allclose(sz[:, 1], X[:, 2])
        self.assertEqual(thin.keep_nearest(sz, 0.1).tolist(), [True, False, True, True])   # off-plane depth does not split cells


class Gate(unittest.TestCase):
    def test_pooled_sr(self):
        s, dof = gate.pooled_sr([(1.0, 2.0), (3.0, 3.0), (None, 1.0)])
        self.assertAlmostEqual(s, 0.5)
        self.assertEqual(dof, 2)
        self.assertAlmostEqual(gate.limit(0.5), 1.4)

    def test_decide_three_ways(self):
        self.assertEqual(gate.decide(1.0, 3.0, 1.4), gate.MET)
        self.assertEqual(gate.decide(3.0, 1.0, 1.4), gate.NOT_MET)
        self.assertEqual(gate.decide(2.0, 3.0, 1.4), gate.UNDECIDABLE)
        self.assertEqual(gate.decide(1.0, 3.0, 1.4, samples=9999), gate.FEW_SAMPLES)
        self.assertEqual(gate.decide(float("nan"), 3.0, 1.4), gate.NO_VALUE)

    def test_condition4(self):
        self.assertEqual(gate.decide(90.0, 95.0, 1.4, kind="not_lower"), gate.NOT_MET)     # image-only higher by more than r
        self.assertEqual(gate.decide(94.0, 95.0, 1.4, kind="not_lower"), gate.MET)
        self.assertEqual(gate.decide(99.0, 95.0, 1.4, kind="not_lower"), gate.MET)

    def test_pass_rule(self):
        ok, s = gate.passes({"1": {"a": gate.MET, "b": gate.UNDECIDABLE}, "2": {"a": gate.FEW_SAMPLES, "b": gate.FEW_SAMPLES}})
        self.assertTrue(ok)
        self.assertTrue(s["2"]["cannot_be_decided"])
        ok, _ = gate.passes({"1": {"a": gate.MET, "b": gate.NOT_MET}})
        self.assertFalse(ok)
        ok, _ = gate.passes({"1": {"a": gate.UNDECIDABLE, "b": gate.UNDECIDABLE}})            # judgeable but no unit met
        self.assertFalse(ok)


if __name__ == "__main__":
    unittest.main()
