"""CPU unit tests of src/phd/prior_propagation_v3 (PHD-STAGE2-R9-THREE-FIXES-v1).

The 24 tests of tests/phd/test_prior_propagation_v2.py run again against v3 (the same file, its imports pointed at v3;
classes prefixed V2onV3_). v3 adds:
  ProtectionV3      : eq. (7) with the patch judgment (r8 review, fix 'na'): a support patch voted conflict excludes like a
                      propagated conflict; a support patch voted agree and an invisible patch protect at c-bar 0; numpy and
                      torch agree
  OrientationV3     : the initial direction of prior-origin Gaussians (fix 'da'): the disk normal of the quaternion is the
                      face normal, the first axis is the face's horizontal line (the cell grid's e1), numpy and torch agree
  TinVertexNormalsV3: the normal of an airborne LiDAR point = its seat surface's incident triangles, else the larger kind
  GroundFacesV3     : the LoD2 bottom face (fix 'ra'): by type (GroundSurface, ClosureSurface), and without types the
                      downward face at the building's lowest height
  OutwardWallsV3    : the footprint test of a wall's outward side
  PartyWallsV3      : walls of two buildings within 0.1 m with opposite normals
Run in jointbuildgs:dev from the repository root: python -m unittest tests.phd.test_prior_propagation_v3"""
import sys
import types
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from src.phd.prior_propagation_v3 import faces as FA  # noqa: E402
from src.phd.prior_propagation_v3 import locations as L  # noqa: E402
from src.phd.prior_propagation_v3 import orientation as O  # noqa: E402
from src.phd.prior_propagation_v3 import rule as R  # noqa: E402
from src.phd.prior_propagation_v3 import surfaces as S  # noqa: E402

# ---- the v2 tests, unchanged, against v3
_src = (Path(__file__).with_name("test_prior_propagation_v2.py")).read_text().replace("src.phd.prior_propagation_v2", "src.phd.prior_propagation_v3")
_v2 = types.ModuleType("test_prior_propagation_v2_on_v3")
_v2.__file__ = str(Path(__file__).with_name("test_prior_propagation_v2.py"))
exec(compile(_src, "test_prior_propagation_v2.py (imports -> v3)", "exec"), _v2.__dict__)
for _name, _obj in list(_v2.__dict__.items()):
    if isinstance(_obj, type) and issubclass(_obj, unittest.TestCase) and _obj is not unittest.TestCase:
        globals()[f"V2onV3_{_name}"] = type(f"V2onV3_{_name}", (_obj,), {})
del _name, _obj


def box(x0, y0, x1, y1, z0, z1):
    """closed box with outward winding: (V, F, tri_poly, types) polygons 0 bottom, 1 top, 2..5 walls (-x, +x, -y, +y)."""
    V = np.array([[x0, y0, z0], [x1, y0, z0], [x1, y1, z0], [x0, y1, z0], [x0, y0, z1], [x1, y0, z1], [x1, y1, z1], [x0, y1, z1]], float)
    quads = [(0, 3, 2, 1), (4, 5, 6, 7), (0, 4, 7, 3), (1, 2, 6, 5), (0, 1, 5, 4), (3, 7, 6, 2)]
    F, tp = [], []
    for k, (a, b, c, d) in enumerate(quads):
        F += [[a, b, c], [a, c, d]]; tp += [k, k]
    types_ = ["GroundSurface", "RoofSurface"] + ["WallSurface"] * 4
    return V, np.array(F), np.array(tp), types_


class ProtectionV3(unittest.TestCase):
    def setUp(self):
        J = R.J_NONE
        # rows: 0 support-conflict E 0 | 1 support-agree E 0 | 2 missing propagated conflict E 0 | 3 invisible E 0 |
        #       4 no patch E 0.2 | 5 support-agree E 0.6 | 6 invisible u beyond | 7 image origin
        self.pj = np.array([R.J_CONFLICT, R.J_AGREE, R.J_CONFLICT, J, J, R.J_AGREE, J, J])
        self.E = np.array([0.0, 0.0, 0.0, 0.0, 0.2, 0.6, 0.0, 0.0])
        self.u = np.array([0.0, 0.0, 0.0, 0.0, 0.1, 0.0, 0.3, 0.0])
        self.prior = np.array([True] * 7 + [False])
        self.want = [False, True, False, True, True, False, False, False]

    def test_numpy(self):
        prot, low, near, conflict = R.protected(self.prior, self.E, 0.5, self.u, 0.2, self.pj)
        self.assertEqual(prot.tolist(), self.want)
        self.assertEqual(conflict.tolist(), [True, False, True, False, False, False, False, False])

    def test_torch(self):
        import torch
        prot, *_ = R.protected(torch.as_tensor(self.prior), torch.as_tensor(self.E), 0.5, torch.as_tensor(self.u),
                               torch.full((8,), 0.2, dtype=torch.float64), torch.as_tensor(self.pj))
        self.assertEqual(prot.tolist(), self.want)

    def test_nan_u_is_not_near(self):
        prot, *_ = R.protected(np.array([True]), np.array([0.0]), 0.5, np.array([np.nan]), 0.2, np.array([R.J_NONE]))
        self.assertFalse(prot[0])


class OrientationV3(unittest.TestCase):
    def setUp(self):
        rng = np.random.default_rng(0)
        n = rng.normal(size=(200, 3)); n /= np.linalg.norm(n, axis=1, keepdims=True)
        self.n = np.vstack([n, [[0, 0, 1.0], [0, 0, -1.0], [1.0, 0, 0], [0, 0.6, 0.8]]])

    def test_normal_and_first_axis(self):
        q = O.quat_from_normal(self.n)
        np.testing.assert_allclose(np.linalg.norm(q, axis=1), 1.0, atol=1e-12)
        a1, a2, a3 = O.axes_of_quat(q)
        np.testing.assert_allclose(a3, self.n, atol=1e-9)
        e1, e2 = O.tangent_frame(self.n)
        np.testing.assert_allclose(a1, e1, atol=1e-9)
        np.testing.assert_allclose(a2, e2, atol=1e-9)
        self.assertTrue(np.all(np.abs(a1[:, 2]) < 1e-9))                       # horizontal line of the face
        np.testing.assert_allclose(a1[-4], [1.0, 0, 0], atol=1e-12)            # horizontal face: the x axis
        for k in (0, 5, -1):                                                    # the cell grid's axes (locations._plane_axes)
            g1, g2 = L._plane_axes(self.n[k])
            np.testing.assert_allclose(a1[k], g1, atol=1e-9); np.testing.assert_allclose(a2[k], g2, atol=1e-9)

    def test_torch_matches_numpy(self):
        import torch
        qn = O.quat_from_normal(self.n)
        qt = O.quat_from_normal(torch.as_tensor(self.n, dtype=torch.float64)).numpy()
        np.testing.assert_allclose(qt, qn, atol=1e-9)
        nt = O.normal_of_quat(torch.as_tensor(qn)).numpy()
        np.testing.assert_allclose(nt, self.n, atol=1e-9)


class TinVertexNormalsV3(unittest.TestCase):
    def test_seat_ground_and_steep(self):
        k = 6
        xs, ys = np.meshgrid(np.arange(k, dtype=float), np.arange(k, dtype=float), indexing="ij")
        z = np.where((xs >= 2) & (xs <= 3) & (ys >= 2) & (ys <= 3), 2.0, 0.0)
        V = np.stack([xs.ravel(), ys.ravel(), z.ravel()], 1)
        idx = np.arange(k * k).reshape(k, k)
        F = []
        for i in range(k - 1):
            for j in range(k - 1):
                a, b, c, d = idx[i, j], idx[i + 1, j], idx[i + 1, j + 1], idx[i, j + 1]
                F += [[a, b, c], [a, c, d]]
        F = np.array(F)
        ts, n, a = S.tin_surfaces(V, F, 0.5)
        roof_s = ts[np.nonzero((V[F][:, :, 2] == 2).all(1))[0][0]]
        eligible = np.zeros(int(ts.max()) + 1, bool); eligible[roof_s] = True
        seat = S.vertex_surface(F, ts, eligible)
        nrm, rule_ = O.tin_vertex_normals(V, F, ts, seat)
        inner = idx[2, 2]
        self.assertEqual(rule_[inner], 1); np.testing.assert_allclose(nrm[inner], [0, 0, 1], atol=1e-12)
        self.assertEqual(rule_[idx[0, 0]], 2); np.testing.assert_allclose(nrm[idx[0, 0]], [0, 0, 1], atol=1e-12)
        v = idx[1, 2]                                                           # ground vertex next to the block (x = 1)
        self.assertIn(rule_[v], (2, 3))
        self.assertGreater(nrm[v, 2], 0)
        if rule_[v] == 3:
            self.assertLess(nrm[v, 0], 0)                                       # away from the block: outward
        self.assertTrue(np.all(nrm[:, 2] >= 0))
        self.assertTrue(np.allclose(np.linalg.norm(nrm, axis=1), 1))


class GroundFacesV3(unittest.TestCase):
    def test_by_type(self):
        self.assertEqual(FA.excluded_by_type(["RoofSurface", "GroundSurface", "WallSurface", "ClosureSurface"]).tolist(),
                         [False, True, False, True])

    def test_without_types(self):
        V, F, tp, types_ = box(0, 0, 4, 3, 10, 16)
        # an overhang underside facing down, 2 m above the bottom (not the bottom face)
        Vo = np.array([[4, 0, 12.0], [5, 0, 12.0], [5, 3, 12.0], [4, 3, 12.0]])
        V2 = np.vstack([V, Vo]); F2 = np.vstack([F, [[8, 10, 9], [8, 11, 10]]]); tp2 = np.r_[tp, 6, 6]
        t = FA.polygon_table(V2, F2, tp2)
        self.assertLess(t["normal"][6, 2], -0.99)
        bottom = FA.bottom_faces_untyped(t["normal"][:, 2], t["zmax"], np.full(len(t["ids"]), V2[:, 2].min()))
        self.assertEqual(bottom.tolist(), [True, False, False, False, False, False, False])
        self.assertEqual(FA.excluded_by_type(types_).tolist(), bottom[:6].tolist())


class OutwardWallsV3(unittest.TestCase):
    def test_footprint(self):
        V, F, tp, _ = box(0, 0, 4, 3, 0, 5)
        t = FA.polygon_table(V, F, tp)
        foot = V[F[tp == 0]][:, :, :2]
        walls = np.arange(2, 6)
        plus, minus = FA.outward_side_outside(t["centroid"][walls], t["normal"][walls], foot)
        self.assertTrue(plus.all() and not minus.any())
        plus, minus = FA.outward_side_outside(t["centroid"][walls], -t["normal"][walls], foot)
        self.assertTrue(minus.all() and not plus.any())


class PartyWallsV3(unittest.TestCase):
    def test_shared_wall(self):
        parts = [box(0, 0, 1, 1, 0, 3), box(1, 0, 2, 1, 0, 3), box(2.2, 0, 3.2, 1, 0, 3)]
        Vs, Fs, bs, ns = [], [], [], []
        off = 0
        for b, (V, F, tp, _) in enumerate(parts):
            t = FA.polygon_table(V, F, tp)
            w = tp >= 2
            Vs.append(V); Fs.append(F[w] + off); bs += [str(b)] * int(w.sum()); ns.append(t["normal"][tp[w]])
            off += len(V)
        WV, WF, WB, WN = np.vstack(Vs), np.vstack(Fs), np.array(bs), np.vstack(ns)
        # cells: building 0 at x = 1 (+x, shared with 1) and at x = 0 (-x); building 1 at x = 2 (+x, 0.2 m from building 2)
        cells = np.array([[1.0, 0.5, 1.5], [0.0, 0.5, 1.5], [2.0, 0.5, 1.5]])
        cb = np.array(["0", "0", "1"]); cn = np.array([[1.0, 0, 0], [-1.0, 0, 0], [1.0, 0, 0]])
        shared, dist, partner = FA.party_wall_cells(cells, cb, cn, WV, WF, WB, WN)
        self.assertEqual(shared.tolist(), [True, False, False])
        self.assertAlmostEqual(float(dist[2]), 0.2, places=5)
        self.assertEqual(WB[partner[0]], "1")


if __name__ == "__main__":
    unittest.main()
