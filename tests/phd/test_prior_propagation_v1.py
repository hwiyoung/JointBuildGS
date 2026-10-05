"""CPU unit tests of src/phd/prior_propagation_v1 (PHD-STAGE2-R7-PROPAGATION-v1), one class per rule:
  conversion  : one formula for both stages; camera-Z residual x |n.d|/|n_z| = range residual x |n.d_hat|/|n_z|;
                roof-like vertical, wall-like along the normal, no surface |d_z|
  tolerance   : one clip at 3 NMAD, width 2.5 x NMAD after the clip, max with the agency spec, no spec, roof fallback
  surfaces    : steep triangles and outlines split TIN surfaces; vertex surface
  rule        : seeing / supporting views, support / missing / invisible, vote tie = agree, E; the judgment rule
  locations   : plane and TIN stores, locate (numpy and torch agree), nearest cell, in-surface paths, propagation
  seat        : cell samples stay in the cell; re-read of E with a synthetic camera and occluder
  outlines    : classification clusters, merged neighbours, intersection over union
Run in jointbuildgs:dev from the repository root: python -m unittest tests.phd.test_prior_propagation_v1"""
import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.phd.prior_propagation_v1 import conversion as C  # noqa: E402
from src.phd.prior_propagation_v1 import locations as L  # noqa: E402
from src.phd.prior_propagation_v1 import rule as R  # noqa: E402
from src.phd.prior_propagation_v1 import surfaces as S  # noqa: E402
from src.phd.prior_propagation_v1 import tolerance as T  # noqa: E402

RECT = np.array([[0.0, 0.0], [10.0, 10.0]])


class Conversion(unittest.TestCase):
    def setUp(self):
        rng = np.random.default_rng(0)
        a = rng.normal(size=3); q = np.linalg.qr(rng.normal(size=(3, 3)))[0]
        self.R = q if np.linalg.det(q) > 0 else -q
        self.d = C.pixel_rays(1000.0, 1000.0, 320.0, 240.0, self.R, 640, 480, flat_idx=np.array([0, 1234, 640 * 480 - 1]), dtype=np.float64)

    def test_forms_agree(self):
        n = np.array([0.3, -0.2, 0.93]); n /= np.linalg.norm(n)
        dz = 0.37
        f_cz = C.factor(np.tile(n, (3, 1)), self.d)
        dhat = self.d / np.linalg.norm(self.d, axis=1, keepdims=True)
        rho = dz * np.linalg.norm(self.d, axis=1)
        f_unit = np.abs(dhat @ n) / abs(n[2])
        np.testing.assert_allclose(dz * f_cz, rho * f_unit, rtol=1e-12)

    def test_vertical_offset_over_a_sloped_plane(self):
        # a point on the ray at depth z1 lies on the plane; at depth z2 it is dz * d away; its vertical offset over the plane
        n = np.array([0.0, 0.6, 0.8]); d = self.d[1]; Cc = np.zeros(3)
        z1 = 40.0; X1 = Cc + z1 * d; z2 = 40.5; X2 = Cc + z2 * d
        plane_z_at = lambda X: X1[2] - (n[0] * (X[0] - X1[0]) + n[1] * (X[1] - X1[1])) / n[2]
        vertical = abs(X2[2] - plane_z_at(X2))
        self.assertAlmostEqual(float(abs(z2 - z1) * C.factor(n, d)), vertical, places=9)

    def test_wall_and_no_surface(self):
        nw = np.array([1.0, 0.0, 0.0]); d = self.d[2]
        self.assertAlmostEqual(float(C.factor(nw, d)), abs(d[0]), places=12)          # along the normal
        self.assertAlmostEqual(float(C.factor(nw, d, has_surface=np.array(False))), abs(d[2]), places=12)
        self.assertEqual(int(C.surface_kind(0.49)), C.KIND_WALL); self.assertEqual(int(C.surface_kind(-0.5)), C.KIND_ROOF)


class Tolerance(unittest.TestCase):
    def test_clip_once_and_width(self):
        rng = np.random.default_rng(1)
        x = np.concatenate([rng.normal(0.01, 0.02, 20000), rng.normal(1.0, 0.05, 500)])
        st = T.robust_width(x)
        self.assertLess(abs(st["median_after"] - 0.01), 0.002)
        self.assertLess(abs(st["nmad_after"] - 0.02), 0.002)
        self.assertGreater(st["clipped_share"], 0.02)
        self.assertAlmostEqual(st["width"], 2.5 * st["nmad_after"])

    def test_spec_rules(self):
        st = dict(width=0.05)
        self.assertEqual(T.tolerance(st, spec=0.12)["tau"], 0.12)
        self.assertEqual(T.tolerance(st, spec=0.12)["side"], "spec")
        self.assertEqual(T.tolerance(st, spec=0.01)["side"], "data")
        self.assertEqual(T.tolerance(st, spec=None)["side"], "data (no spec)")
        self.assertEqual(T.tolerance(st, spec=0.12, use_spec=False)["tau"], 0.05)
        roof = T.tolerance(st, spec=0.12)
        fb = T.tolerance(dict(width=None), spec=None, fallback=roof)
        self.assertEqual(fb["tau"], 0.12); self.assertTrue(fb["side"].startswith("roof value"))


def two_step_tin():
    """two flat squares at z 0 and z 3 joined by a steep strip, split by x = 2..3"""
    xs = np.array([0, 1, 2, 3, 4, 5], float)
    V, F = [], []
    for x in xs:
        for y in (0.0, 1.0):
            V.append([x, y, 0.0 if x <= 2 else 3.0])
    V = np.array(V)
    idx = lambda i, j: 2 * i + j
    for i in range(len(xs) - 1):
        F += [[idx(i, 0), idx(i + 1, 0), idx(i + 1, 1)], [idx(i, 0), idx(i + 1, 1), idx(i, 1)]]
    return V, np.array(F)


class Surfaces(unittest.TestCase):
    def test_steep_boundary(self):
        V, F = two_step_tin()
        ts, n, a = S.tin_surfaces(V, F, 0.5)
        self.assertTrue((ts[4:6] == S.STEEP).all())                       # the step strip x 2..3
        self.assertEqual(len(np.unique(ts[ts >= 0])), 2)                   # two gentle surfaces
        self.assertNotEqual(ts[0], ts[-1])

    def test_outline_splits_a_gentle_region(self):
        V, F = two_step_tin(); V[:, 2] = 0.0                               # all flat: one surface
        ts, _, _ = S.tin_surfaces(V, F, 0.5)
        self.assertEqual(len(np.unique(ts)), 1)
        region = np.where(V[F].mean(1)[:, 0] < 2.5, 0, 1)
        ts2, _, _ = S.tin_surfaces(V, F, 0.5, region=region)
        self.assertEqual(len(np.unique(ts2)), 2)

    def test_vertex_surface(self):
        V, F = two_step_tin()
        ts, _, _ = S.tin_surfaces(V, F, 0.5)
        vs = S.vertex_surface(F, ts, np.ones(ts.max() + 1, bool))
        self.assertEqual(vs[0], ts[0]); self.assertEqual(vs[-1], ts[-1])


class Rule(unittest.TestCase):
    def test_states_votes_tie_agree(self):
        # 3 views x 4 locations
        n_pix = np.array([[10, 10, 10, 0], [10, 10, 10, 0], [10, 0, 10, 0]])
        n_a1 = np.array([[10, 10, 2, 0], [10, 10, 2, 0], [0, 0, 10, 0]])
        n_ag = np.array([[2, 10, 2, 0], [2, 0, 2, 0], [0, 0, 10, 0]])
        n_cf = np.array([[8, 0, 0, 0], [8, 10, 0, 0], [0, 0, 0, 0]])
        st, vote, ns, nsp, E = R.location_state(n_pix, n_a1, n_ag, n_cf)
        self.assertEqual((st[0], vote[0]), (R.ST_SUPPORT, R.V_CONFLICT))   # 2 of 3 views support, both conflict
        self.assertEqual((st[1], vote[1]), (R.ST_SUPPORT, R.V_AGREE))      # 1 agree : 1 conflict -> tie -> agree
        self.assertEqual(st[2], R.ST_MISSING)                              # 1 of 3 supports
        self.assertEqual(st[3], R.ST_INVISIBLE)
        np.testing.assert_allclose(E, [2 / 3, 1.0, 1 / 3, 0.0])

    def test_judge(self):
        kd = np.full((3, 10), np.inf); kv = np.full((3, 10), -1, np.int8)
        kd[0, :5] = [0.25, 0.25, 0.5, 0.6, 0.9]; kv[0, :5] = [1, 1, 1, 1, 0]      # 4 of 5 conflict
        kd[1, :5] = [0.25, 0.3, 0.4, 0.5, 1.2]; kv[1, :5] = [1, 1, 1, 1, 1]       # the 5th beyond 1 m
        kd[2, :5] = [0.25, 0.3, 0.4, 0.5, 0.6]; kv[2, :5] = [1, 1, 1, 0, 0]       # 3 of 5
        j = R.judge(kd, kv, 2 / 3, 5, 1.0)
        self.assertEqual(list(j), [R.J_CONFLICT, R.J_INSUFF, R.J_MIXED])


def square_store(sp=0.25, notch=False):
    V = np.array([[0, 0, 0], [2, 0, 0], [2, 2, 0], [0, 2, 0]], float)
    F = np.array([[0, 1, 2], [0, 2, 3]])
    ts = np.array([7, 7])
    st = L.build_plane_store(V, F, ts, [dict(ext=7, normal=[0, 0, 1])], RECT, sp)
    return st


class Locations(unittest.TestCase):
    def test_plane_store_and_locate(self):
        st = square_store()
        self.assertEqual(len(st["loc_area"]), 64)                          # 8 x 8 cells of 0.25 m
        X = np.array([[0.1, 0.1, 0.0], [1.9, 1.9, 0.0], [2.2, 1.0, 0.0], [1.0, -0.4, 0.0]])
        loc = L.locate(st, np.zeros(4, np.int64), X)
        c = st["loc_center"][loc]
        np.testing.assert_allclose(c[0, :2], [0.125, 0.125]); np.testing.assert_allclose(c[1, :2], [1.875, 1.875])
        np.testing.assert_allclose(c[2, :2], [1.875, 1.125]); np.testing.assert_allclose(c[3, :2], [1.125, 0.125])  # nearest cell

    def test_locate_torch_matches_numpy(self):
        import torch
        from src.phd.prior_propagation_v1 import seat
        st = square_store()
        rng = np.random.default_rng(2)
        X = np.c_[rng.uniform(-0.5, 2.5, (500, 2)), np.zeros(500)]
        a = L.locate(st, np.zeros(500, np.int64), X)
        b = seat.seat(seat.to_torch(st, "cpu"), torch.zeros(500, dtype=torch.long), torch.as_tensor(X)).numpy()
        np.testing.assert_array_equal(a, b)

    def test_propagation_on_a_square(self):
        st = square_store(sp=0.5)                                         # 4 x 4 cells
        Lc = len(st["loc_area"]); state = np.full(Lc, R.ST_SUPPORT, np.int8); vote = np.full(Lc, R.V_CONFLICT, np.int8)
        centre = L.locate(st, np.zeros(1, np.int64), np.array([[0.75, 0.75, 0.0]]))[0]
        state[centre] = R.ST_MISSING; vote[centre] = R.V_NONE
        J, _ = L.propagate(st, state, vote, 2 / 3, 5, 1.0)
        self.assertEqual(J[centre], R.J_CONFLICT)
        J, _ = L.propagate(st, state, vote, 2 / 3, 5, 0.5)                # only 4 support cells within 0.5 m
        self.assertEqual(J[centre], R.J_INSUFF)

    def test_tin_store(self):
        V, F = two_step_tin()
        ts, n, a = S.tin_surfaces(V, F, 0.5)
        surfs = [dict(ext=int(s)) for s in np.unique(ts[ts >= 0])]
        st = L.build_tin_store(V, F, ts, n, a, surfs, np.array([[0.0, 0.0], [5.0, 1.0]]), 0.25)
        self.assertEqual(set(st["surf_ext"].tolist()), set(np.unique(ts[ts >= 0]).tolist()))
        # cells of the upper surface lie at z 3
        up = int(ts[-1]); s_up = int(L.compact_index(st, [up])[0])
        self.assertTrue(np.allclose(st["loc_center"][st["loc_surface"] == s_up][:, 2], 3.0))


class Seat(unittest.TestCase):
    def test_samples_and_reread(self):
        import torch
        from src.phd.prior_propagation_v1 import seat
        st = square_store(sp=0.5)
        ts = seat.to_torch(st, "cpu")
        loc = torch.arange(len(st["loc_area"]))
        smp = seat.cell_samples(ts, loc, 3)
        c = ts["loc_center"][loc]
        self.assertTrue(bool(((smp - c[:, None, :]).abs() <= 0.25 + 1e-9).all()))
        # camera 10 m above looking down; A = 1 on the left half of the image; an occluder hides x > 1.5
        W = H = 200; f = 100.0

        class Cam:
            image_name = "v"

        def project(xyz, cam):
            z = 10.0 - xyz[:, 2]
            return f * (xyz[:, 0] - 1.0) / z + W / 2 - 0.5, f * (xyz[:, 1] - 1.0) / z + H / 2 - 0.5, z
        A = torch.zeros(H, W); A[:, : W // 2] = 1.0
        D = torch.full((H, W), 10.0); AL = torch.ones(H, W)
        D[:, int(f * 0.5 / 10 + W / 2):] = 5.0                            # pixels of x > 1.5 are hidden (depth 5 < 10)
        E, ns, nsp = seat.reread_E(smp, [Cam()], project, {"v": A}, {"v": D}, {"v": AL}, 0.5, 0.05)
        cx = c[:, 0]
        self.assertTrue(bool((E[cx < 0.9] == 1).all()))                   # left cells: seen and supported
        self.assertTrue(bool((E[(cx > 1.1) & (cx < 1.4)] == 0).all()))     # seen, A = 0
        self.assertTrue(bool((ns[cx > 1.6] == 0).all()))                   # hidden by the occluder


class Outlines(unittest.TestCase):
    def test_clusters_merge_and_iou(self):
        from src.phd.prior_propagation_v1 import outlines as O
        rng = np.random.default_rng(3)
        pts = rng.uniform(0, 10, (40000, 2))
        cls = np.where(((pts[:, 0] > 1) & (pts[:, 0] < 4) & (pts[:, 1] > 1) & (pts[:, 1] < 9))
                       | ((pts[:, 0] >= 4) & (pts[:, 0] < 7) & (pts[:, 1] > 1) & (pts[:, 1] < 9)), 6, 2)   # two touching blocks
        lab, rec = O.classification_clusters(pts, cls, RECT, cell=0.5)
        self.assertEqual(rec["n_clusters"], 1)                             # touching blocks merge
        rings = [[[1, 1], [4, 1], [4, 9], [1, 9]], [[4, 1], [7, 1], [7, 9], [4, 9]]]
        rl = O.rings_raster(rings, RECT, 0.5)
        rows = O.overlap_table(rl, lab, ["a", "b"], 0.5)
        self.assertEqual(rows[0]["merged_with"], ["b"])
        self.assertAlmostEqual(rows[0]["iou"], 0.5, delta=0.05)
        lab2 = O.region_from_rings(np.array([[2.0, 5.0], [5.0, 5.0], [9.0, 9.0]]), rings)
        self.assertEqual(list(lab2), [0, 1, -1])


if __name__ == "__main__":
    unittest.main()
