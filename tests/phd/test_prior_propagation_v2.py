"""CPU unit tests of src/phd/prior_propagation_v2 (PHD-STAGE2-R8-FOUR-CASES-v1). The v1 classes are kept against v2
(the rules they test did not change); v2 adds:
  ToleranceV2  : the agency spec is never a lower bound (decision 2); it is compared and a larger tolerance warns
  PriorWeight  : g_p of eq. (4) in the four cases of the research intent, for pixels with and without a judgment unit
                 (decision 1 and 3), and the reasons a unit is undetermined (decision 6)
  SurfacesV2   : the second outline source -- the classification separates building from non-building only, buildings
                 are split by steep triangles, non-building triangles carry no number (decision 4)
  OffsetV2     : u_i of eq. (7) measured like the residuals (vertical over the initial surface / along the wall normal /
                 vertical without a surface); numpy and torch agree
  CentreE      : the Gaussian confidence of a Gaussian without a judgment unit (one-sided occlusion, 0 with no view)
Run in jointbuildgs:dev from the repository root: python -m unittest tests.phd.test_prior_propagation_v2"""
import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.phd.prior_propagation_v2 import conversion as C  # noqa: E402
from src.phd.prior_propagation_v2 import locations as L  # noqa: E402
from src.phd.prior_propagation_v2 import rule as R  # noqa: E402
from src.phd.prior_propagation_v2 import surfaces as S  # noqa: E402
from src.phd.prior_propagation_v2 import tolerance as T  # noqa: E402

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
        from src.phd.prior_propagation_v2 import seat
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
        from src.phd.prior_propagation_v2 import seat
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
        from src.phd.prior_propagation_v2 import outlines as O
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


class ToleranceV2(unittest.TestCase):
    def test_spec_is_not_a_lower_bound(self):
        st = dict(width=0.05)
        t = T.tolerance(st, spec=0.12, spec_source="agency")
        self.assertEqual(t["tau"], 0.05)                                   # v1 gave 0.12
        self.assertFalse(t["exceeds_spec"]); self.assertIsNone(t["warning"]); self.assertEqual(t["spec"], 0.12)
        t = T.tolerance(dict(width=0.2), spec=0.12)
        self.assertEqual(t["tau"], 0.2); self.assertTrue(t["exceeds_spec"]); self.assertIsNotNone(t["warning"])
        t = T.tolerance(st, spec=None)
        self.assertEqual(t["tau"], 0.05); self.assertIsNone(t["exceeds_spec"])
        with self.assertRaises(TypeError):
            T.tolerance(st, 0.12, None, None, True)                        # no switch to bring the lower bound back

    def test_roof_value_for_walls_without_a_sample(self):
        roof = T.tolerance(dict(width=0.04), spec=0.12)
        fb = T.tolerance(dict(width=None), spec=None, fallback=roof)
        self.assertEqual(fb["tau"], 0.04); self.assertTrue(fb["side"].startswith("roof value"))

    def test_pipeline_value_is_the_width(self):
        rng = np.random.default_rng(5)
        x = rng.normal(0.0, 0.02, 50000)
        st = T.robust_width(x)
        self.assertAlmostEqual(T.tolerance(st, spec=1.0)["tau"], 2.5 * st["nmad_after"])


class PriorWeight(unittest.TestCase):
    """g_p = 1 - prior_term_off. Rows: the four cases of the order's table, with and without a judgment unit."""
    def g(self, located, J, A, mark, torch_=False):
        args = [np.asarray(located, bool), np.asarray(J), np.asarray(A, np.float32), np.asarray(mark)]
        if torch_:
            import torch
            args = [torch.as_tensor(x) for x in args]
            return (~R.prior_term_off(*args)).float().numpy()
        return (~R.prior_term_off(*args)).astype(np.float32)

    def cases(self):
        rows = [  # located, judgment of the unit, A, mark, expected g_p, case
            (True, R.J_AGREE, 1, R.MARK_AGREE, 1, "observed, within tolerance (support unit agree)"),
            (True, R.J_AGREE, 1, R.MARK_CONFLICT, 1, "observed, the pixel disagrees but the unit's vote is agree"),
            (True, R.J_CONFLICT, 1, R.MARK_CONFLICT, 0, "observed, beyond tolerance (support unit conflict)"),
            (True, R.J_CONFLICT, 1, R.MARK_AGREE, 0, "observed, the pixel agrees but the unit's vote is conflict"),
            (True, R.J_AGREE, 0, R.MARK_NONE, 1, "not observed, propagated agree"),
            (True, R.J_MIXED, 0, R.MARK_NONE, 1, "not observed, propagated mixed (undetermined)"),
            (True, R.J_INSUFF, 0, R.MARK_NONE, 1, "not observed, insufficient evidence (undetermined)"),
            (True, R.J_CONFLICT, 0, R.MARK_NONE, 0, "not observed, propagated conflict"),
            (True, R.J_CONFLICT, 0, R.MARK_NONE, 0, "not observed on a conflict support unit (direct and propagated alike)"),
            (False, R.J_NONE, 0, R.MARK_NONE, 1, "no unit, c = 0: inherit the prior"),
            (False, R.J_NONE, 1, R.MARK_AGREE, 1, "no unit, c = 1, own mark agree"),
            (False, R.J_NONE, 1, R.MARK_CONFLICT, 0, "no unit, c = 1, own mark conflict"),
            (False, R.J_CONFLICT, 0, R.MARK_NONE, 1, "no unit: a stray judgment value is never read"),
        ]
        return rows

    def test_four_cases_numpy_and_torch(self):
        rows = self.cases()
        loc, J, A, mark, want = (np.array([r[i] for r in rows]) for i in range(5))
        for t in (False, True):
            got = self.g(loc, J, A, mark, torch_=t)
            for r, gv in zip(rows, got):
                self.assertEqual(gv, r[4], r[5])

    def test_undetermined_why(self):
        state = np.array([R.ST_SUPPORT, R.ST_MISSING, R.ST_MISSING, R.ST_MISSING, R.ST_MISSING, R.ST_INVISIBLE], np.int8)
        J = np.array([R.J_NONE, R.J_CONFLICT, R.J_MIXED, R.J_INSUFF, R.J_INSUFF, R.J_NONE], np.int8)
        mis = np.array([1, 2, 3, 4])
        kd = np.full((4, 5), np.inf); kd[0, :5] = 0.3; kd[1, :5] = 0.4; kd[3, :2] = [0.5, 1.4]
        why = R.undetermined_why(state, J, kd, mis, 5, 1.0)
        self.assertEqual(list(why), [R.WHY_DETERMINED, R.WHY_DETERMINED, R.WHY_MIXED, R.WHY_NO_SUPPORT_ON_SURFACE,
                                     R.WHY_TOO_FEW_WITHIN_DISTANCE, R.WHY_INVISIBLE])


class SurfacesV2(unittest.TestCase):
    @staticmethod
    def strip_tin(zs):
        """a 1 m wide strip, one column of vertices per x = 0, 1, ...; zs[i] = height of column i"""
        V = np.array([[x, y, z] for x, z in enumerate(zs) for y in (0.0, 1.0)], float)
        idx = lambda i, j: 2 * i + j
        F = []
        for i in range(len(zs) - 1):
            F += [[idx(i, 0), idx(i + 1, 0), idx(i + 1, 1)], [idx(i, 0), idx(i + 1, 1), idx(i, 1)]]
        return V, np.array(F)

    def test_classification_only_separates_building_from_ground(self):
        from src.phd.prior_propagation_v2 import outlines as O
        # x 0..2 ground (class 2, z 0), x 2..3 steep wall, x 3..8 two touching roofs (class 6) at the same height 3
        V, F = self.strip_tin([0, 0, 0, 3, 3, 3, 3, 3, 3])
        cls = np.where(V[:, 0] <= 2, 2, 6)
        ts, _, _ = S.tin_surfaces(V, F, 0.5, building=O.building_triangles(F, cls))
        self.assertTrue((ts[:4] == S.NONBUILDING).all())                  # gentle ground: no number
        self.assertTrue((ts[4:6] == S.STEEP).all())                        # the step: no number
        self.assertEqual(len(np.unique(ts[ts >= 0])), 1)                   # touching roofs at one height: one surface
        # the same roofs with a height break at x 5..6: split by the steep triangles only
        V2, F2 = self.strip_tin([0, 0, 0, 3, 3, 3, 6, 6, 6])
        ts2, _, _ = S.tin_surfaces(V2, F2, 0.5, building=O.building_triangles(F2, np.where(V2[:, 0] <= 2, 2, 6)))
        self.assertEqual(len(np.unique(ts2[ts2 >= 0])), 2)
        self.assertTrue((ts2[10:12] == S.STEEP).all())

    def test_without_classification_every_gentle_triangle_is_numbered(self):
        V, F = two_step_tin()
        ts, _, _ = S.tin_surfaces(V, F, 0.5, building=None)
        self.assertFalse((ts == S.NONBUILDING).any())


class OffsetV2(unittest.TestCase):
    def test_roof_wall_none_and_backends(self):
        import torch
        n_roof = np.array([0.0, 0.6, 0.8]); n_wall = np.array([1.0, 0.0, 0.0])
        disp = np.array([[0.0, 1.0, 0.0], [0.0, 0.0, 0.3], [0.2, 0.5, 0.1], [0.3, 0.3, 0.3]])
        n = np.stack([n_roof, n_roof, n_wall, n_wall])
        kind = np.array([C.KIND_ROOF, C.KIND_ROOF, C.KIND_WALL, C.KIND_NONE])
        u = C.offset_metres(disp, n, kind)
        # a horizontal move of 1 m over a plane of slope 0.6/0.8 changes the height over the plane by 0.75 m
        self.assertAlmostEqual(u[0], 0.75); self.assertAlmostEqual(u[1], 0.3)
        self.assertAlmostEqual(u[2], 0.2); self.assertAlmostEqual(u[3], 0.3)
        ut = C.offset_metres(torch.as_tensor(disp), torch.as_tensor(n), torch.as_tensor(kind)).numpy()
        np.testing.assert_allclose(u, ut)
        # a move along the roof plane leaves u at 0 (the 3-D distance would not)
        along = np.cross(n_roof, [1.0, 0, 0]); along /= np.linalg.norm(along)
        self.assertAlmostEqual(float(C.offset_metres(0.4 * along[None], n_roof[None], np.array([C.KIND_ROOF]))[0]), 0.0)


class CentreE(unittest.TestCase):
    def test_one_sided_and_no_view(self):
        import torch
        from src.phd.prior_propagation_v2 import seat
        W = H = 100; f = 50.0

        class Cam:
            image_name = "v"

        def project(xyz, cam):
            z = 10.0 - xyz[:, 2]
            return f * xyz[:, 0] / z + W / 2 - 0.5, f * xyz[:, 1] / z + H / 2 - 0.5, z
        A = torch.zeros(H, W); A[:, : W // 2] = 1.0
        D = torch.full((H, W), 10.0); AL = torch.ones(H, W)
        xyz = torch.tensor([[-1.0, 0.0, 0.0], [1.0, 0.0, 0.0], [-1.0, 0.0, -2.0], [-1.0, 0.0, 3.0], [100.0, 0.0, 0.0]])
        E, n = seat.centre_E(xyz, [Cam()], project, {"v": A}, {"v": D}, {"v": AL}, 0.5, 0.05)
        self.assertEqual(E.tolist(), [1.0, 0.0, 0.0, 1.0, 0.0])
        self.assertEqual(n.tolist(), [1.0, 1.0, 0.0, 1.0, 0.0])            # 2 m behind: hidden; in front: seen; outside: none
        P = {"v": torch.where(torch.arange(W)[None, :].expand(H, W) < 10, torch.tensor(float("nan")), D)}
        Dp, ALp = seat.prior_occluder(P)
        self.assertEqual(float(ALp["v"][0, 0]), 0.0); self.assertEqual(float(Dp["v"][0, 0]), 0.0)


if __name__ == "__main__":
    unittest.main()
