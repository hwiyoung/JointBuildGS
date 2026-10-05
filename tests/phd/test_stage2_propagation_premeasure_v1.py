"""CPU unit tests of the propagation pre-measurement rules (PHD-STAGE2-PROPAGATION-PREMEASURE-v1,
scripts/phd/stage2_propagation_premeasure_v1/propagation_rule.py):
  judge          : nearest first, stop at the minimum, nothing beyond the maximum distance, majority thresholds,
                   insufficient evidence; integer effect of the majority threshold
  location_state : per-view measuring and marks, support / missing / invisible, tie break of the vote
  grid_edges     : in-surface paths do not cross a boundary; two surfaces on one grid are not connected
Run: python -m unittest tests.phd.test_stage2_propagation_premeasure_v1 (jointbuildgs:dev, repo root)."""
import sys
import unittest
from pathlib import Path

import numpy as np
from scipy.sparse.csgraph import dijkstra

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts/phd/stage2_propagation_premeasure_v1"))
import propagation_rule as R  # noqa: E402

C, A = R.V_CONFLICT, R.V_AGREE
INF = np.inf


def one(dists, votes, q, k, r):
    kd = np.full((1, 10), INF); kv = np.full((1, 10), -1, np.int8)
    kd[0, :len(dists)] = dists; kv[0, :len(votes)] = votes
    return int(R.judge(kd, kv, q, k, r)[0])


class JudgeRule(unittest.TestCase):
    def test_majority_of_the_first_k(self):
        self.assertEqual(one([0.25, 0.25, 0.35, 0.5], [C, C, A, A], 2 / 3, 3, 1.0), R.J_CONFLICT)   # 2 of 3 = 2/3
        self.assertEqual(one([0.25, 0.25, 0.35, 0.5], [C, A, A, C], 2 / 3, 3, 1.0), R.J_AGREE)
        self.assertEqual(one([0.25, 0.25, 0.35], [C, C, A], 0.75, 3, 1.0), R.J_MIXED)              # needs 3 of 3

    def test_stop_at_minimum_and_max_distance(self):
        # the 4th location is never collected (stop at k = 3)
        self.assertEqual(one([0.25, 0.3, 0.4, 0.45], [A, A, A, C], 0.8, 3, 1.0), R.J_AGREE)
        # only two within 0.35 m -> insufficient evidence
        self.assertEqual(one([0.25, 0.3, 0.4], [C, C, C], 2 / 3, 3, 0.35), R.J_INSUFF)
        # no support location on the surface
        self.assertEqual(one([], [], 2 / 3, 1, 5.0), R.J_INSUFF)

    def test_minimum_one_is_never_mixed(self):
        for q in (0.55, 0.6, 2 / 3, 0.75, 0.8):
            self.assertEqual(one([0.25], [C], q, 1, 1.0), R.J_CONFLICT)
            self.assertEqual(one([0.25], [A], q, 1, 1.0), R.J_AGREE)

    def test_integer_effect_of_the_threshold(self):
        # with 5 collected locations 0.55 and 0.6 need 3, 2/3 .. 0.8 need 4
        d = [0.25] * 5
        for q, want in ((0.55, R.J_CONFLICT), (0.6, R.J_CONFLICT), (2 / 3, R.J_MIXED), (0.75, R.J_MIXED), (0.8, R.J_MIXED)):
            self.assertEqual(one(d, [C, C, C, A, A], q, 5, 1.0), want)


class LocationState(unittest.TestCase):
    def test_states_and_votes(self):
        # three views x five locations; counts per view: pixels, A = 1 pixels, agree pixels, conflict pixels
        n_pix = np.array([[10, 10, 10, 4, 0], [10, 10, 10, 4, 0], [10, 0, 10, 4, 0]])
        n_a1 = np.array([[10, 10, 2, 4, 0], [10, 10, 2, 4, 0], [0, 0, 10, 4, 0]])
        n_ag = np.array([[2, 10, 2, 1, 0], [2, 0, 2, 3, 0], [0, 0, 10, 1, 0]])
        n_cf = np.array([[8, 0, 0, 3, 0], [8, 10, 0, 1, 0], [0, 0, 0, 3, 0]])
        st, vote, n_obs, n_meas = R.location_state(n_pix, n_a1, n_ag, n_cf)
        # loc 0: two of three views measure (2/3 >= 0.5) -> support, both conflict
        self.assertEqual((st[0], vote[0]), (R.ST_SUPPORT, C))
        # loc 1: views 1 and 2 measure, one agree and one conflict -> pooled pixels 10 : 10 -> exact tie = agree
        self.assertEqual((st[1], vote[1]), (R.ST_SUPPORT, A))
        # loc 2: only view 3 measures (A-share 1.0); views 1 and 2 have 2 of 10 A = 1 pixels -> 1/3 < 0.5 -> missing
        self.assertEqual(st[2], R.ST_MISSING)
        self.assertEqual(vote[2], -1)
        # loc 3: all measure; marks conflict, agree, conflict -> conflict
        self.assertEqual((st[3], vote[3]), (R.ST_SUPPORT, C))
        # loc 4: nobody observes
        self.assertEqual(st[4], R.ST_INVISIBLE)
        self.assertEqual(list(n_obs), [3, 2, 3, 3, 0])

    def test_half_is_support(self):
        n_pix = np.array([[5], [5]]); n_a1 = np.array([[5], [0]]); n_ag = np.array([[0], [0]]); n_cf = np.array([[5], [0]])
        st, vote, _, _ = R.location_state(n_pix, n_a1, n_ag, n_cf)
        self.assertEqual((st[0], vote[0]), (R.ST_SUPPORT, C))     # E = 0.5 counts as measured, as in the r6 lock rule


def graph(member, sp=1.0, owner=None):
    ni, nj = member.shape
    loc = np.full((ni, nj), -1, np.int64); loc[member] = np.arange(int(member.sum()))
    ii, jj = np.meshgrid(np.arange(ni), np.arange(nj), indexing="ij")
    P3 = np.stack([ii * sp, jj * sp, np.zeros_like(ii, float)], -1).astype(float)
    rows, cols, w = [], [], []
    R.grid_edges(loc, P3, rows, cols, w, owner=owner)
    return loc, R.csr(rows, cols, w, int(member.sum()))


class GridPaths(unittest.TestCase):
    def test_path_goes_around_a_notch(self):
        # U shape: two arms of one surface joined at the bottom row; the straight line between the arm tips is 4 cells
        m = np.zeros((5, 5), bool); m[:, 0] = True; m[:, 4] = True; m[4, :] = True
        loc, G = graph(m)
        d = dijkstra(G, directed=False, indices=[loc[0, 0]])[0, loc[0, 4]]
        self.assertGreater(d, 4.0 + 1e-6)
        self.assertLess(d, 12.0)            # 4 down + 4 across + 4 up, shortened by diagonal/knight steps

    def test_straight_line_is_exact(self):
        m = np.ones((1, 6), bool)
        loc, G = graph(m, sp=0.25)
        self.assertAlmostEqual(float(dijkstra(G, directed=False, indices=[loc[0, 0]])[0, loc[0, 5]]), 1.25)

    def test_knight_step_blocked_by_a_boundary_cell(self):
        # cells (0,0) and (1,2) of one surface; the straddled cells (0,1), (1,1) belong to another surface
        owner = np.array([[0, 1, -1], [-1, 1, 0]])
        loc = np.full(owner.shape, -1, np.int64); mem = owner >= 0; loc[mem] = np.arange(int(mem.sum()))
        P3 = np.stack(np.meshgrid(np.arange(2), np.arange(3), indexing="ij") + [np.zeros((2, 3), int)], -1).astype(float)
        rows, cols, w = [], [], []
        R.grid_edges(loc, P3, rows, cols, w, owner=owner)
        G = R.csr(rows, cols, w, int(mem.sum()))
        d = dijkstra(G, directed=False, indices=[loc[0, 0]])[0]
        self.assertTrue(np.isinf(d[loc[1, 2]]))            # surface 0 cells are not connected through surface 1
        self.assertTrue(np.isinf(d[loc[0, 1]]))            # and the two surfaces are not connected at all


if __name__ == "__main__":
    unittest.main()
