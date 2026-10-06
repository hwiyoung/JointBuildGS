"""Tests of src/phd/metrics_v2 (PHD-MAIN-METRICS-FIX-v1) on hand-made scenes.
  CopiedV2    surface, lines, cloud, gauss, cells byte-identical to v1; band.py and stats.py = the v1 text + appended functions
  EdgeBandV2  a 30 degree and a 60 degree plane are not in the new band (the v1 band takes the 30 degree plane); a 1 m step on a
              flat roof and on a 30 degree roof is, within 0.5 m of the step only
  Readings    gentle faces read vertically, steep faces along the normal (a 0.1 m normal offset on a 30 degree plane reads 0.1)
  RegionsV2   the per-patch median of the values at the GT points; codes 2 / 3 and 11 / 12 re-split by |d| <= tau; few values or
              wall-like patches keep v1 and are flagged
  Bins        merging of small bins (trial counts of both priors), the correction boundary
  Stats       bias and dispersion
Run in Docker: python -m unittest tests.phd.test_metrics_v2"""
import hashlib
import unittest
from pathlib import Path

import numpy as np

from src.phd.metrics_v1 import band as band_v1
from src.phd.metrics_v2 import band, bins, regions, stats
from src.phd.metrics_v2.readings import roof_reading
from src.phd.metrics_v2.surface import MeshScene

ROOT = Path(__file__).resolve().parents[2]


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


class CopiedV2(unittest.TestCase):
    def test_bytes(self):
        for f in ("surface.py", "lines.py", "cloud.py", "gauss.py", "cells.py"):
            self.assertEqual(sha(ROOT / "src/phd/metrics_v1" / f), sha(ROOT / "src/phd/metrics_v2" / f), f)
        for f, added in (("band.py", "def edge_band_v2("), ("stats.py", "def bias_dispersion(")):
            v1 = (ROOT / "src/phd/metrics_v1" / f).read_text().rstrip("\n")
            v2 = (ROOT / "src/phd/metrics_v2" / f).read_text()
            self.assertTrue(v2.startswith(v1), f)
            self.assertIn(added, v2[len(v1):], f)


def sloped(deg, step_at=None, step=1.0):
    a = np.arange(0.025, 10, 0.05)
    xx, yy = np.meshgrid(a, a)
    z = np.tan(np.radians(deg)) * xx
    if step_at is not None:
        z = z + np.where(xx >= step_at, step, 0.0)
    return np.column_stack([xx.ravel(), yy.ravel(), z.ravel()])


class EdgeBandV2(unittest.TestCase):
    def test_planes(self):
        Q = np.array([[5.02, 5.02, 0.0]])
        for deg in (30.0, 60.0):
            X = sloped(deg)
            inb, adj = band.edge_band_v2(X, Q, [deg])
            self.assertFalse(bool(inb[0]), (deg, adj))
        old, _ = band_v1.edge_band(sloped(30.0), Q)
        self.assertTrue(bool(old[0]))

    def test_steps(self):
        for deg in (0.0, 30.0):
            X = sloped(deg, step_at=5.0)
            Q = np.array([[4.55, 5.0, 0.0], [5.4, 5.0, 0.0], [3.9, 5.0, 0.0], [6.2, 5.0, 0.0]])
            inb, _ = band.edge_band_v2(X, Q, [deg] * 4)
            self.assertEqual(inb.tolist(), [True, True, False, False], deg)


def plane_mesh(deg, offset=0.0, size=10.0):
    """a plane z = tan(deg) x, moved by `offset` along its unit normal."""
    t = np.tan(np.radians(deg))
    nrm = np.array([-t, 0.0, 1.0]) / np.sqrt(1 + t * t)
    V = np.array([[0, 0, 0], [size, 0, t * size], [size, size, t * size], [0, size, 0]], float) + offset * nrm
    return V, np.array([[0, 1, 2], [0, 2, 3]]), nrm


class Readings(unittest.TestCase):
    def test_gentle_and_steep(self):
        for deg, steep in ((10.0, False), (30.0, True)):
            V, F, nrm = plane_mesh(deg, offset=0.1)
            X = np.array([[5.0, 5.0, np.tan(np.radians(deg)) * 5.0]])
            v, s = roof_reading(MeshScene(V, F), X, nrm[None, :], [deg])
            self.assertEqual(bool(s[0]), steep)
            want = 0.1 if steep else 0.1 / np.cos(np.radians(deg))
            self.assertAlmostEqual(float(v[0]), want, places=4)


class RegionsV2(unittest.TestCase):
    def test_patch_median(self):
        med, cnt = regions.patch_median([0, 0, 0, 1, 1, 2], [0.1, 0.3, np.nan, 0.5, 0.7, np.nan], 4)
        self.assertAlmostEqual(med[0], 0.2)
        self.assertAlmostEqual(med[1], 0.6)
        self.assertTrue(np.isnan(med[2]) and np.isnan(med[3]))
        self.assertEqual(cnt.tolist(), [2, 2, 0, 0])

    def test_split(self):
        code = np.array([2, 3, 3, 11, 12, 12, 2, 12, 0, 4])
        kind = np.array([1, 1, 1, 1, 1, 1, 2, 1, 1, 1])
        tau = np.full(10, 0.2)
        d = np.array([0.5, 0.1, 0.5, 0.3, 0.05, -0.1, 0.0, 0.0, 0.0, 0.0])
        n = np.array([10, 10, 10, 10, 10, 10, 10, 3, 10, 10])
        c2, kept = regions.split_v2(code, kind, tau, d, n)
        self.assertEqual(c2.tolist(), [3, 2, 3, 12, 11, 11, 2, 12, 0, 4])
        self.assertEqual(kept.tolist(), [False, False, False, False, False, False, True, True, False, False])


class Bins(unittest.TestCase):
    def test_merge(self):
        lod2 = [129935, 43422, 21995, 8942, 2359, 539522]
        self.assertEqual(bins.merge_small(lod2), [[0], [1], [2], [3, 4], [5]])
        als = [597, 576, 988, 1023, 1780, 376161]
        self.assertEqual(bins.merge_small(als), [[0, 1, 2, 3, 4, 5]])
        self.assertEqual(bins.merge_small([20000, 3000]), [[0, 1]])

    def test_boundary(self):
        self.assertEqual(bins.boundary([0.3, 0.45, 0.8, 0.97], [1.0, 1.5, 2.0, 3.0]), 2.0)
        self.assertEqual(bins.boundary([0.6, 0.4, 0.8], [1.0, 1.5, 2.0]), 2.0)
        self.assertIsNone(bins.boundary([0.3, 0.4], [1.0, 1.5]))


class Stats(unittest.TestCase):
    def test_bias_dispersion(self):
        s = stats.bias_dispersion(np.array([0.07, 0.08, 0.06, 0.07, 0.17, np.nan]))
        self.assertEqual(s["n"], 5)
        self.assertAlmostEqual(s["bias"], 0.07)
        self.assertAlmostEqual(s["mad"], 0.01)
        self.assertAlmostEqual(s["nmad"], 0.0148, places=4)


if __name__ == "__main__":
    unittest.main()
