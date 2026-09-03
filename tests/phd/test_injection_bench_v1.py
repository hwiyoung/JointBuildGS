from __future__ import annotations

import unittest

import numpy as np

from scripts.phd.injection_bench_v1 import inject as ib


def _top(nx: int = 12, ny: int = 12) -> np.ndarray:
    dtype = np.dtype([("ix", "<i4"), ("iy", "<i4"), ("layer", "u1"), ("state", "u1"), ("rough", "u1"), ("mvs_z", "<f4"), ("als_z", "<f4")])
    top = np.zeros(nx * ny, dtype=dtype)
    top["ix"] = np.tile(np.arange(nx), ny); top["iy"] = np.repeat(np.arange(ny), nx)
    top["state"] = 1; top["rough"] = 0
    top["state"][(top["ix"] >= 6)] = 2          # east half is PRIOR_ABOVE → not a candidate
    return top


class InjectionBenchV1Test(unittest.TestCase):
    def test_config_contract(self):
        cfg = ib.load_config()
        self.assertIsNone(cfg["scientific_verdict"])
        self.assertEqual([v["id"] for v in cfg["variants"]], ["V1", "V2", "V3", "V4", "V5", "V6", "V7", "V8"])

    def test_candidate_patches_and_deterministic_selection(self):
        top = _top(); domain = {"x": [0.0, 6.0], "y": [0.0, 6.0]}
        rule = {"grid_m": 3.0, "cell_size_m": 0.5, "min_compatible_planar_fraction": 0.8, "select_fraction": 0.5, "seed": 1}
        cands = ib.candidate_patches(top, domain, rule)
        self.assertEqual([(c["gx"], c["gy"]) for c in cands], [(0, 0), (0, 1)])     # only the west column (x < 3 m) is compatible
        chosen = ib.select_patches(cands, rule)
        self.assertEqual(len(chosen), 1)
        self.assertEqual(chosen, ib.select_patches(cands, rule))                     # same seed → same choice

    def test_variants_modify_only_the_truth_flagged_points(self):
        rng = np.random.default_rng(0)
        mvs = np.column_stack((rng.uniform(0, 6, 500), rng.uniform(0, 6, 500), np.zeros(500))).astype("<f4")
        als = mvs.copy() + np.float32(0.01)
        patches = [{"patch_id": 1, "bbox": [0.0, 0.0, 3.0, 3.0], "cells": [[ix, iy] for ix in range(6) for iy in range(6)]}]
        inside = (mvs[:, 0] < 3) & (mvs[:, 1] < 3)
        m, a, tm, ta, kind = ib.apply_variant({"kind": "mvs_delete_patches"}, mvs, als, patches)
        self.assertEqual(kind, "mvs_missing"); self.assertEqual(len(m), int((~inside).sum())); self.assertTrue(np.array_equal(tm.astype(bool), inside))
        m, a, tm, ta, kind = ib.apply_variant({"kind": "mvs_shift_patches", "shift_z_m": 1.0}, mvs, als, patches)
        self.assertTrue(np.allclose(m[inside, 2], 1.0)); self.assertTrue(np.all(m[~inside, 2] == 0)); self.assertEqual(int(ta.sum()), 0)
        m, a, tm, ta, kind = ib.apply_variant({"kind": "als_shift_all", "shift_xyz_m": [0, 0, 2.0]}, mvs, als, patches)
        self.assertTrue(np.allclose(a[:, 2] - als[:, 2], 2.0)); self.assertEqual(int(ta.sum()), len(als)); self.assertEqual(kind, "delta_all")
        m, a, tm, ta, kind = ib.apply_variant({"kind": "mvs_noise_patches", "sigma_m": 0.3, "noise_seed": 3}, mvs, als, patches)
        self.assertGreater(float(np.std(m[inside, 2])), 0.2); self.assertTrue(np.all(m[~inside, 2] == 0))

    def test_truth_cells(self):
        top = _top(); patches = [{"patch_id": 1, "bbox": [0, 0, 3, 3], "cells": [[ix, iy] for ix in range(6) for iy in range(6)]}]
        cells = ib.truth_cells(top, "mvs_biased", patches)
        self.assertEqual(int(np.count_nonzero(cells["kind"])), 36); self.assertEqual(int(cells["kind"].max()), ib.CELL_KIND["mvs_biased"])
        cells_all = ib.truth_cells(top, "delta_all", [])
        self.assertTrue(np.all(cells_all["kind"] == ib.CELL_KIND["delta_all"]))


class InjectionBenchEvaluateTest(unittest.TestCase):
    def _cells(self, n_pairs_m, n_pairs_p, delta, f_agree, f_pen, f_block, no_landing, tested, dz):
        from scripts.phd.injection_bench_v1 import evaluate as ev
        t1 = np.zeros(1, dtype=[("ix", "<i4"), ("iy", "<i4"), ("n_agree", "<u4"), ("n_penetrate", "<u4"), ("n_block", "<u4"), ("n_no_landing", "<u4"),
                                ("f_agree", "<f4"), ("f_penetrate", "<f4"), ("f_block", "<f4")])
        t1["n_agree"] = int(tested * f_agree); t1["n_penetrate"] = int(tested * f_pen); t1["n_block"] = tested - t1["n_agree"] - t1["n_penetrate"]
        t1["n_no_landing"] = no_landing; t1["f_agree"] = f_agree; t1["f_penetrate"] = f_pen; t1["f_block"] = f_block
        t2 = np.zeros(1, dtype=[("ix", "<i4"), ("iy", "<i4"), ("n_pairs_m", "<u4"), ("n_pairs_p", "<u4"), ("delta_median", "<f4")])
        t2["n_pairs_m"] = n_pairs_m; t2["n_pairs_p"] = n_pairs_p; t2["delta_median"] = delta
        top = np.zeros(1, dtype=[("ix", "<i4"), ("iy", "<i4"), ("dz_m", "<f4")]); top["dz_m"] = dz
        return ev, t1, t2, top

    def test_provisional_reading_separates_the_bench_causes(self):
        ev, t1, t2, top = self._cells(0, 10, np.nan, 0.0, 0.0, 0.0, 500, 10, np.nan)
        self.assertEqual(ev.provisional_reading(t1, t2, top, 0), "H_M_missing")             # MVS gone, prior visible, rays do not land
        ev, t1, t2, top = self._cells(10, 10, -0.4, 0.2, 0.1, 0.7, 0, 200, -1.0)
        self.assertEqual(ev.provisional_reading(t1, t2, top, 0), "H_M_biased")              # MVS in front + images support P
        ev, t1, t2, top = self._cells(10, 10, 0.5, 0.05, 0.9, 0.05, 0, 200, 2.0)
        self.assertEqual(ev.provisional_reading(t1, t2, top, 0), "PRIOR_WRONG_OR_DELTA")    # rays cross the prior + images support M
        ev, t1, t2, top = self._cells(10, 10, 0.0, 0.9, 0.05, 0.05, 0, 200, 0.05)
        self.assertEqual(ev.provisional_reading(t1, t2, top, 0), "H_C")
        ev, t1, t2, top = self._cells(10, 10, 0.0, 0.9, 0.05, 0.05, 0, 5, 0.05)
        self.assertEqual(ev.provisional_reading(t1, t2, top, 0), "ABSTAIN")                 # too few rays
        self.assertEqual(ev.truth_reading_target(ib.CELL_KIND["mvs_biased"]), "H_M_biased")
        self.assertEqual(ev.truth_reading_target(ib.CELL_KIND["delta_all"]), "PRIOR_WRONG_OR_DELTA")

    def test_coherence_statistic(self):
        from scripts.phd.injection_bench_v1 import evaluate as ev
        top = np.zeros(40, dtype=[("dz_m", "<f4")]); top["dz_m"] = 1.0 + np.linspace(-0.05, 0.05, 40)
        c = ev.coherence(np.ones(40, dtype=bool), top)
        self.assertLess(c["dz_variance"], 0.01); self.assertEqual(c["sign_agreement"], 1.0)
        top["dz_m"][:20] = -1.0
        c2 = ev.coherence(np.ones(40, dtype=bool), top)
        self.assertGreater(c2["dz_variance"], 0.5); self.assertAlmostEqual(c2["sign_agreement"], 0.5)


if __name__ == "__main__":
    unittest.main()
