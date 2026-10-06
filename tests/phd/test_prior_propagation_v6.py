"""Tests of src/phd/prior_propagation_v6 (PHD-MAIN-STAGE0-v1): v6 = v5 with two appended pieces.
  CopiedV6     : twelve files byte-identical to v5; locations.py and rules.py = the v5 text + appended functions only
  MoveStore    : locate(moved store, X) = locate(unmoved store, X - shift) on plane and TIN stores; cells, surfaces, areas
                 and the in-surface graph unchanged; the shift is recorded and a second move is refused
  RuleDefaults : LoD2 -> current, ALS and DSM -> margin_all_2; 'auto' resolves by the prior kind; unknown names refused
Run in Docker: python -m unittest tests.phd.test_prior_propagation_v6"""
import hashlib
import unittest
from pathlib import Path

import numpy as np

from src.phd.prior_propagation_v6 import locations as L
from src.phd.prior_propagation_v6 import rules as R

ROOT = Path(__file__).resolve().parents[2]
SAME = ("caps.py", "conversion.py", "faces.py", "orientation.py", "outlines.py", "registration.py", "rule.py", "seat.py",
        "surfaces.py", "switches.py", "tallies.py", "tolerance.py")


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


class CopiedV6(unittest.TestCase):
    def test_bytes(self):
        for f in SAME:
            self.assertEqual(sha(ROOT / "src/phd/prior_propagation_v5" / f), sha(ROOT / "src/phd/prior_propagation_v6" / f), f)
        for f, added in (("locations.py", ("def move_store(", "def frame_shift(")), ("rules.py", ("DEFAULT_BY_PRIOR", "def default_rule(", "def resolve("))):
            v5 = (ROOT / "src/phd/prior_propagation_v5" / f).read_text().rstrip("\n")
            v6 = (ROOT / "src/phd/prior_propagation_v6" / f).read_text()
            self.assertTrue(v6.startswith(v5), f)
            for a in added:
                self.assertIn(a, v6[len(v5):], (f, a))


def plane_store():
    """a 6 m x 6 m roof (two halves) and a wall of 6 m x 3 m."""
    V = np.array([[0, 0, 10], [3, 0, 10], [3, 6, 10], [0, 6, 10], [6, 0, 10], [6, 6, 10],
                  [0, 0, 7], [6, 0, 7], [6, 0, 10.0], [0, 0, 10.0]], float)
    F = np.array([[0, 1, 2], [0, 2, 3], [1, 4, 5], [1, 5, 2], [6, 7, 8], [6, 8, 9]])
    ts = np.array([1, 1, 2, 2, 3, 3])
    rect = np.array([[-1.0, -1.0], [7.0, 7.0]])
    surfs = [dict(ext=1, normal=[0, 0, 1.0]), dict(ext=2, normal=[0, 0, 1.0]), dict(ext=3, normal=[0, -1.0, 0])]
    return L.build_plane_store(V, F, ts, surfs, rect, 0.25)


def tin_store():
    x, y = np.meshgrid(np.arange(0, 7.0), np.arange(0, 7.0), indexing="ij")
    V = np.stack([x.ravel(), y.ravel(), 10 + 0.2 * x.ravel()], 1)
    F = []
    for i in range(6):
        for j in range(6):
            a = i * 7 + j; b = a + 7
            F += [[a, b, b + 1], [a, b + 1, a + 1]]
    F = np.array(F)
    ts = np.where(V[F].mean(1)[:, 0] < 3, 1, 2)
    n = np.cross(V[F[:, 1]] - V[F[:, 0]], V[F[:, 2]] - V[F[:, 0]]); ar = 0.5 * np.linalg.norm(n, axis=1); n = n / (2 * ar[:, None])
    n[n[:, 2] < 0] *= -1
    return L.build_tin_store(V, F, ts, n, ar, [dict(ext=1), dict(ext=2)], np.array([[0.0, 0.0], [6.0, 6.0]]), 0.25)


class MoveStore(unittest.TestCase):
    def check(self, st, X, s_idx):
        shift = np.array([-0.048, 0.043, 0.012])
        mv = L.move_store(st, shift)
        a = L.locate(mv, s_idx, X + shift)
        b = L.locate(st, s_idx, X)
        self.assertTrue(np.array_equal(a, b))
        for k in ("member", "nearest", "loc_surface", "loc_area", "loc_t1", "loc_t2", "loc_kind", "surf_ext", "e1", "e2", "i0", "j0", "ni", "nj", "off"):
            self.assertTrue(np.array_equal(mv[k], st[k]), k)
        self.assertTrue(np.allclose(mv["loc_center"] - st["loc_center"], shift))
        self.assertTrue(np.allclose(L.frame_shift(mv), shift)); self.assertTrue(np.allclose(L.frame_shift(st), 0))
        G0, G1 = L.graph(st), L.graph(mv)
        self.assertEqual(G0.shape, G1.shape); self.assertEqual(G0.nnz, G1.nnz)
        self.assertLess(abs(G0 - G1).max(), 1e-9)          # edge lengths = centre distances: the same up to rounding
        with self.assertRaises(ValueError):
            L.move_store(mv, shift)
        # the unmoved lookup of a moved point differs where the shift crosses a cell boundary (the v5 mismatch)
        c = L.locate(st, s_idx, X + shift)
        return int((c != b).sum())

    def test_plane(self):
        st = plane_store()
        rng = np.random.default_rng(3)
        X = np.concatenate([np.c_[rng.uniform(0, 6, (2000, 2)), np.full(2000, 10.0)],
                            np.c_[rng.uniform(0, 6, 500), np.zeros(500), rng.uniform(7, 10, 500)]])
        s = np.concatenate([np.where(X[:2000, 0] < 3, 0, 1), np.full(500, 2)])
        ci = L.compact_index(st, np.array([1, 2, 3]))
        n_diff = self.check(st, X, ci[s])
        self.assertGreater(n_diff, 0)

    def test_tin(self):
        st = tin_store()
        rng = np.random.default_rng(4)
        xy = rng.uniform(0.1, 5.9, (3000, 2))
        X = np.c_[xy, 10 + 0.2 * xy[:, 0]]
        s = L.compact_index(st, np.where(xy[:, 0] < 3, 1, 2))
        self.check(st, X, s)


class RuleDefaults(unittest.TestCase):
    def test_defaults(self):
        self.assertEqual(R.default_rule("LoD2"), "current")
        self.assertEqual(R.default_rule("ALS"), "margin_all_2")
        self.assertEqual(R.default_rule("DSM"), "margin_all_2")
        self.assertEqual(R.resolve("auto", "ALS"), "margin_all_2"); self.assertEqual(R.resolve(None, "LoD2"), "current")
        self.assertEqual(R.resolve("current", "ALS"), "current")
        self.assertEqual(R.RULES["margin_all_2"], dict(t=2.0, prop="standard"))
        with self.assertRaises(ValueError):
            R.default_rule("TIN")
        with self.assertRaises(ValueError):
            R.resolve("margin_all_4", "ALS")


if __name__ == "__main__":
    unittest.main()
