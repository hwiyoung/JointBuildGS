"""PHD-MAIN-PREP-MEASURE-v1 unit tests (run in jointbuildgs:dev):
  python -m unittest tests.phd.test_main_prep_measure_v1
1. Nuth-Kaab recovers a known horizontal displacement of planar faces (sign of the correction).
2. the sparse per-view accumulation of step 03 equals rule.location_state.
3. the gap caps of step 02 stop rays that enter a party-wall slit (probe hits before > 0, after = 0)."""
import sys
import unittest

import numpy as np

sys.path.insert(0, "/repo")
sys.path.insert(0, "/repo/scripts/phd/main_prep_measure_v1")


class T(unittest.TestCase):
    def test_nuth_kaab_sign(self):
        import step03_stage1 as s3
        rng = np.random.default_rng(1)
        n = rng.normal(size=(20000, 3)); n[:, 2] = np.abs(n[:, 2]) + 0.6
        n /= np.linalg.norm(n, axis=1, keepdims=True)
        n = n[(n[:, 2] > 0.5) & (n[:, 2] < 0.99)]
        true_corr = np.array([0.31, -0.17])           # translating the prior by this makes dh constant
        gx, gy = n[:, 0] / n[:, 2], n[:, 1] / n[:, 2]
        dh = 0.05 + gx * true_corr[0] + gy * true_corr[1] + rng.normal(0, 0.01, len(n))
        cfg = dict(iterations_max=10, stop_increment_m=0.001)
        r = s3.nuth_kaab(dh, n, cfg)
        self.assertTrue(r["horizontal_estimable"])
        np.testing.assert_allclose(r["shift_xy"], true_corr, atol=0.01)
        after = s3.apply_shift_dh(dh, n, np.array(r["shift_xy"]))
        self.assertLess(np.std(after), 0.02)

    def test_sparse_states(self):
        from src.phd.prior_propagation_v4 import rule
        rng = np.random.default_rng(2)
        Vn, L = 7, 50
        npx = rng.integers(0, 5, (Vn, L)); na1 = np.minimum(npx, rng.integers(0, 5, (Vn, L)))
        nag = rng.integers(0, 3, (Vn, L)); ncf = rng.integers(0, 3, (Vn, L))
        nag = np.minimum(nag, na1); ncf = np.minimum(ncf, na1 - nag)
        st, vo, ns, nsp, E = rule.location_state(npx, na1, nag, ncf)
        acc = dict(n_seeing=np.zeros(L, int), n_supporting=np.zeros(L, int), ag=np.zeros(L, int), cf=np.zeros(L, int))
        for v in range(Vn):
            u = np.nonzero(npx[v] > 0)[0]
            sup = 2 * na1[v, u] >= npx[v, u]; mk = nag[v, u] >= ncf[v, u]
            acc["n_seeing"][u] += 1; acc["n_supporting"][u] += sup; acc["ag"][u] += sup & mk; acc["cf"][u] += sup & ~mk
        st2 = np.full(L, rule.ST_INVISIBLE); ns2, nsp2 = acc["n_seeing"], acc["n_supporting"]
        st2[(ns2 > 0) & (2 * nsp2 >= ns2)] = rule.ST_SUPPORT; st2[(ns2 > 0) & (2 * nsp2 < ns2)] = rule.ST_MISSING
        vo2 = np.where(acc["cf"] > acc["ag"], rule.V_CONFLICT, rule.V_AGREE); vo2[st2 != rule.ST_SUPPORT] = rule.V_NONE
        np.testing.assert_array_equal(st, st2); np.testing.assert_array_equal(vo, vo2)
        np.testing.assert_array_equal(ns, ns2); np.testing.assert_array_equal(nsp, nsp2)

    def test_gap_caps(self):
        import open3d as o3d
        from src.phd.prior_propagation_v4 import faces as fc
        # two boxes' facing walls 0.06 m apart (x = 0 and x = 0.06), 10 m high, 10 m long; roofs at z = 10 on both sides
        def quad(a, b, c, d):
            return [np.array([a, b, c]), np.array([a, c, d])]
        wa = quad([0, 0, 0], [0, 10, 0], [0, 10, 10], [0, 0, 10])            # building A wall, outward +x
        wb = quad([0.06, 10, 0], [0.06, 0, 0], [0.06, 0, 10], [0.06, 10, 10])  # building B wall, outward -x
        ra = quad([-10, 0, 10], [0, 0, 10], [0, 10, 10], [-10, 10, 10])
        rb = quad([0.06, 0, 10], [10.06, 0, 10], [10.06, 10, 10], [0.06, 10, 10])
        polys = [dict(id=0, building="A", normal=np.array([1.0, 0, 0]), tris=np.array(wa)),
                 dict(id=1, building="B", normal=np.array([-1.0, 0, 0]), tris=np.array(wb))]
        ov = fc.party_wall_overlaps(polys)
        self.assertEqual(len(ov), 1)
        r = ov[0]
        caps, probes = [], []
        xy = np.asarray(r["region"].exterior.coords)
        for i in range(len(xy) - 1):
            e = xy[i:i + 2]
            Pa = fc.lift(e, r["frame"], polys[0]["tris"][0, 0], polys[0]["normal"]); Pb = fc.lift(e, r["frame"], polys[1]["tris"][0, 0], polys[1]["normal"])
            if Pa[:, 2].mean() <= 0.05 and abs(Pa[0, 2] - Pa[1, 2]) < 0.05:
                continue
            caps += [np.array([Pa[0], Pa[1], Pb[1]]), np.array([Pa[0], Pb[1], Pb[0]])]
        for W in polys:
            probes += list(W["tris"])
        def first_hits(tris, nprobe):
            T = np.array(tris); V = T.reshape(-1, 3); F = np.arange(len(V)).reshape(-1, 3)
            sc = o3d.t.geometry.RaycastingScene(); sc.add_triangles(o3d.core.Tensor(V.astype(np.float32)), o3d.core.Tensor(F.astype(np.uint32)))
            # oblique rays that pass the slit at its top (x = 0.03, z = 10): direction (0.3, 0, -1)
            O = np.array([[0.03 - 3.0, y, 20.0] for y in np.linspace(1, 9, 9)], np.float32); Dd = np.tile([0.3, 0, -1.0], (9, 1)).astype(np.float32)
            ans = sc.cast_rays(o3d.core.Tensor(np.concatenate([O, Dd], 1)))
            pid = ans["primitive_ids"].numpy().astype(np.int64)
            return int((np.isfinite(ans["t_hit"].numpy()) & (pid >= len(T) - nprobe)).sum())
        before = first_hits(ra + rb + probes, len(probes))
        after = first_hits(ra + rb + caps + probes, len(probes))
        self.assertGreater(before, 0); self.assertEqual(after, 0)


if __name__ == "__main__":
    unittest.main()
