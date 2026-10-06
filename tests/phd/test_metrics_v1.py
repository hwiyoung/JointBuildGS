"""Tests of src/phd/metrics_v1 (PHD-MAIN-METRICS-TRIAL-v1) on hand-made scenes.
  Spread      a flat GT at z = 0 with result planes at 0.05, 0.4, 2 and 4 m and the wrong data W at 4 m, 0.4 m and -4 m
              (buried old surface): the four classes, the threshold t = min(0.5, |s_W| / 2) and the spread share; the same
              on a wall with the line along its normal
  EdgeBand    a 1 m step: points within 0.5 m of it are in the band, farther ones are not; a 10 degree plane is not, a
              30 degree plane is (the known property of the trial values)
  Readings    highest crossing on two layers, signed nearest crossing along a line, 3-D distance shares
  Clouds      mesh sampling count and position, Chamfer / precision / completeness / F1 of two parallel planes, M3C2 of
              offset planes (roof and wall), voxel thinning
  Gaussians   counts near points, the highest-surface raster and floaters
  Cells       cell medians of a point path at query points
Run in Docker: python -m unittest tests.phd.test_metrics_v1"""
import unittest

import numpy as np

from src.phd.metrics_v1 import band, cells, cloud, gauss, lines, stats
from src.phd.metrics_v1.surface import MeshScene


def hplane(z, lo=0.0, hi=10.0):
    V = np.array([[lo, lo, z], [hi, lo, z], [hi, hi, z], [lo, hi, z]], float)
    return V, np.array([[0, 1, 2], [0, 2, 3]])


def vplane(x, lo=0.0, hi=10.0):
    V = np.array([[x, lo, lo], [x, hi, lo], [x, hi, hi], [x, lo, hi]], float)
    return V, np.array([[0, 1, 2], [0, 2, 3]])


def merge(*meshes):
    Vs, Fs, n = [], [], 0
    for V, F in meshes:
        Vs.append(V)
        Fs.append(F + n)
        n += len(V)
    return np.concatenate(Vs), np.concatenate(Fs)


def grid_points(n=11, lo=2.0, hi=8.0):
    a = np.linspace(lo, hi, n)
    xx, yy = np.meshgrid(a, a)
    return np.column_stack([xx.ravel(), yy.ravel(), np.zeros(xx.size)])


UP = np.array([0.0, 0.0, 1.0])


class Spread(unittest.TestCase):
    def classes(self, mesh, s_w):
        X = grid_points()
        sc = MeshScene(*mesh) if mesh is not None else MeshScene(np.zeros((0, 3)), np.zeros((0, 3), int))
        c, t = lines.four_way(sc, X, UP, np.full(len(X), s_w))
        return c, t

    def test_threshold(self):
        self.assertAlmostEqual(float(lines.threshold(4.0)), 0.5)
        self.assertAlmostEqual(float(lines.threshold(0.4)), 0.2)
        self.assertAlmostEqual(float(lines.threshold(-0.1)), 0.05)

    def test_w_far_above(self):
        for z, want in ((0.05, lines.GT_SIDE), (0.4, lines.GT_SIDE), (4.0, lines.WRONG_SIDE), (2.0, lines.NEITHER)):
            c, _ = self.classes(hplane(z), 4.0)
            self.assertTrue((c == want).all(), (z, np.unique(c)))
        c, _ = self.classes(merge(hplane(0.05), hplane(4.0)), 4.0)
        self.assertTrue((c == lines.BOTH).all())
        c, _ = self.classes(None, 4.0)
        self.assertTrue((c == lines.NEITHER).all())

    def test_w_near(self):
        # W at 0.4 m: t = 0.2 m, so a surface at 0.4 m is the wrong side and one at 0.05 m the GT side
        for z, want in ((0.05, lines.GT_SIDE), (0.4, lines.WRONG_SIDE), (4.0, lines.NEITHER)):
            c, t = self.classes(hplane(z), 0.4)
            self.assertTrue((c == want).all(), (z, np.unique(c)))
            self.assertTrue(np.allclose(t, 0.2))

    def test_buried_old_surface(self):
        # the old surface 4 m below the new one, both in the result: 'both'
        c, _ = self.classes(merge(hplane(0.0), hplane(-4.0)), -4.0)
        self.assertTrue((c == lines.BOTH).all())
        c, _ = self.classes(hplane(0.0), -4.0)
        self.assertTrue((c == lines.GT_SIDE).all())

    def test_wall(self):
        a = np.linspace(3, 7, 5)
        yy, zz = np.meshgrid(a, a)
        X = np.column_stack([np.zeros(yy.size), yy.ravel(), zz.ravel()])
        D = np.array([1.0, 0.0, 0.0])
        for x, want in ((0.05, lines.GT_SIDE), (1.0, lines.WRONG_SIDE)):
            c, _ = lines.four_way(MeshScene(*vplane(x)), X, D, np.full(len(X), 1.0))
            self.assertTrue((c == want).all(), (x, np.unique(c)))

    def test_shares(self):
        c = np.array([0, 0, 1, 2, 3, 3, 3, 3])
        s = lines.shares(c)
        self.assertEqual(s["points"], 8)
        self.assertAlmostEqual(s["spread"], 0.25)
        self.assertAlmostEqual(s["neither"], 0.5)


class EdgeBand(unittest.TestCase):
    def test_step(self):
        a = np.arange(0.025, 10, 0.05)          # points off the cell edges (no rounding at the step)
        xx, yy = np.meshgrid(a, a)
        z = np.where(xx >= 5.0, 1.0, 0.0)
        X = np.column_stack([xx.ravel(), yy.ravel(), z.ravel()])
        Q = np.array([[4.45, 5.0, 0.0], [4.55, 5.0, 0.0], [4.0, 5.0, 0.0], [5.4, 5.0, 1.0], [5.6, 5.0, 1.0], [6.5, 5.0, 1.0]])
        inb, r = band.edge_band(X, Q, 0.5, 0.3, 0.1)
        self.assertEqual(inb.tolist(), [False, True, False, True, False, False])
        self.assertAlmostEqual(float(r[1]), 1.0)

    def test_slopes(self):
        a = np.arange(0, 10, 0.05)
        xx, yy = np.meshgrid(a, a)
        Q = np.array([[5.0, 5.0, 0.0]])
        for deg, want in ((10.0, False), (30.0, True)):
            X = np.column_stack([xx.ravel(), yy.ravel(), np.tan(np.radians(deg)) * xx.ravel()])
            inb, _ = band.edge_band(X, Q, 0.5, 0.3, 0.1)
            self.assertEqual(bool(inb[0]), want, deg)


class Readings(unittest.TestCase):
    def test_highest(self):
        sc = MeshScene(*merge(hplane(0.0), hplane(3.0)))
        z = sc.highest_z(np.array([[5.0, 5.0], [20.0, 20.0]]))
        self.assertAlmostEqual(float(z[0]), 3.0, places=5)
        self.assertTrue(np.isnan(z[1]))

    def test_along(self):
        X = np.array([[5.0, 5.0, 0.0]])
        self.assertAlmostEqual(float(MeshScene(*hplane(0.3)).along(X, UP, 2.0)[0]), 0.3, places=5)
        self.assertAlmostEqual(float(MeshScene(*hplane(-0.2)).along(X, UP, 2.0)[0]), -0.2, places=5)
        self.assertAlmostEqual(float(MeshScene(*merge(hplane(0.3), hplane(-0.2))).along(X, UP, 2.0)[0]), -0.2, places=5)
        self.assertTrue(np.isnan(MeshScene(*hplane(2.5)).along(X, UP, 2.0)[0]))

    def test_distance(self):
        sc = MeshScene(*hplane(0.0))
        d = sc.distance(np.array([[5, 5, 0.1], [5, 5, 0.3], [5, 5, 0.8]], float))
        w = stats.within(d)
        self.assertAlmostEqual(w["le_0.2"], 1 / 3, places=4)
        self.assertAlmostEqual(w["le_0.5"], 2 / 3, places=4)

    def test_robust(self):
        r = stats.robust(np.array([0.1, 0.1, 0.1, -0.1, np.nan]))
        self.assertEqual(r["n"], 4)
        self.assertAlmostEqual(r["median"], 0.1)
        self.assertAlmostEqual(r["nmad"], 0.0)
        self.assertAlmostEqual(r["abs_median"], 0.1)


class Clouds(unittest.TestCase):
    def test_sample(self):
        P = cloud.sample_mesh(*hplane(0.0, 0.0, 2.0), density=400, seed=0)
        self.assertEqual(len(P), 1600)
        self.assertTrue(np.allclose(P[:, 2], 0.0))
        self.assertTrue((P[:, :2] >= 0).all() and (P[:, :2] <= 2).all())
        Q = cloud.sample_mesh(*hplane(0.0, 0.0, 2.0), density=400, seed=0)
        self.assertTrue(np.array_equal(P, Q))

    def test_chamfer(self):
        G = cloud.sample_mesh(*hplane(0.0, 0.0, 4.0), density=2500, seed=1)
        R = cloud.sample_mesh(*hplane(0.1, 0.0, 4.0), density=2500, seed=2)
        out, _, _ = cloud.chamfer_pcf(R, G, ts=(0.05, 0.2))
        self.assertAlmostEqual(out["chamfer_mean"], 0.1, delta=0.01)
        self.assertEqual(out["precision_0.2"], 1.0)
        self.assertEqual(out["completeness_0.2"], 1.0)
        self.assertEqual(out["f1_0.05"], 0.0)

    def test_m3c2_roof_and_wall(self):
        G = cloud.sample_mesh(*hplane(0.0, 0.0, 6.0), density=900, seed=1)
        core = np.array([[3.0, 3.0, 0.0], [2.0, 4.0, 0.0]])
        n = cloud.pca_normals(core, G, 0.5)
        n *= np.sign(n[:, 2:3])
        self.assertTrue(np.allclose(n, [[0, 0, 1], [0, 0, 1]], atol=1e-6))
        for dz in (0.3, -0.3):
            R = cloud.sample_mesh(*hplane(dz, 0.0, 6.0), density=900, seed=2)
            d, nr, nc = cloud.m3c2(core, n, G, R, radius=0.25, half_len=1.0)
            self.assertTrue(np.allclose(d, dz, atol=1e-6), d)
            self.assertTrue((nr >= 30).all() and (nc >= 30).all())
        R = cloud.sample_mesh(*hplane(1.5, 0.0, 6.0), density=900, seed=2)
        d, _, _ = cloud.m3c2(core, n, G, R, radius=0.25, half_len=1.0)
        self.assertTrue(np.isnan(d).all())
        Gw = cloud.sample_mesh(*vplane(0.0, 0.0, 6.0), density=900, seed=3)
        Rw = cloud.sample_mesh(*vplane(0.2, 0.0, 6.0), density=900, seed=4)
        d, _, _ = cloud.m3c2(np.array([[0.0, 3.0, 3.0]]), np.array([[1.0, 0, 0]]), Gw, Rw)
        self.assertAlmostEqual(float(d[0]), 0.2, places=6)

    def test_voxel_thin(self):
        X = np.array([[0.01, 0.01, 0.01], [0.24, 0.24, 0.24], [0.26, 0.0, 0.0], [0.12, 0.13, 0.12]])
        k = cloud.voxel_thin(X, 0.25)
        self.assertEqual(k.tolist(), [2, 3])


class Gaussians(unittest.TestCase):
    def test_count(self):
        g = np.array([[0, 0, 0], [0.2, 0, 0], [1, 1, 1.0]])
        c = gauss.count_near(np.array([[0, 0, 0.1], [5, 5, 5.0]]), g, 0.25)
        self.assertEqual(c.tolist(), [2, 0])

    def test_floaters(self):
        X = np.array([[0.5, 0.5, 10.0], [5.5, 5.5, 2.0], [9.5, 9.5, 0.0]])
        R = gauss.TopRaster(X, [0, 0], [10, 10], cell=1.0, k=1)
        self.assertAlmostEqual(float(R.top(np.array([[1.2, 1.2]]))[0]), 10.0)      # neighbour cell of the 10 m point
        self.assertAlmostEqual(float(R.top(np.array([[3.5, 3.5]]))[0]), 10.0)      # no GT within 3 x 3: highest of the range
        g = np.array([[5.5, 5.5, 4.5], [5.5, 5.5, 5.5], [5.5, 5.5, 5.5], [0.5, 0.5, 12.0]])
        f = gauss.floaters(g, np.array([0.9, 0.9, 0.2, 0.9]), R, np.ones(4, bool), above=3.0)
        self.assertEqual(f.tolist(), [False, True, False, False])


class Cells(unittest.TestCase):
    def test_medians(self):
        q = np.array([[0.05, 0.05], [0.15, 0.05], [0.95, 0.95]])
        cm = cells.CellMedian(q, 0.1)
        cm.add(np.array([[0.01, 0.02, 1.0], [0.03, 0.04, 2.0], [0.07, 0.08, 9.0], [0.12, 0.01, 5.0], [0.5, 0.5, 7.0]]))
        cm.add(np.array([[0.02, 0.09, 3.0], [0.16, 0.06, 6.0]]))
        m, n = cm.medians(min_n=3)
        self.assertAlmostEqual(float(m[0]), 2.5)
        self.assertEqual(n.tolist(), [4, 2, 0])
        self.assertTrue(np.isnan(m[1]) and np.isnan(m[2]))


if __name__ == "__main__":
    unittest.main()
