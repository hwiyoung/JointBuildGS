"""Tests of src/phd/prior_propagation_v5 (PHD-MAIN-PREP-DISCARD-RULE-v1): the files copied from v4 stay byte-identical except
locations.py (one function added), and the new pieces behave as the moved code / the rules of configs discard_v1.json.
  CopiedV5     : conversion, faces, orientation, outlines, rule, seat, surfaces, tolerance = v4 bytes; locations = v4 + one function
  NeighbourIds : k_nearest_support_ids gathers the same support patches, distances and order as k_nearest_support
  RulesV5      : votes_at = tallies.unit_states on the same counts; current rule = rule.judge; margin_all marks at k tau;
                 margin_propagation only counts big conflicts; asymmetric turns propagated conflicts into mixed; discard set
  SwitchesV5   : judgment / propagation switches; init_exclusion keeps every point
  RegistrationV5: vertical_shift and final_check_fails as the prep stage-1 rules
Run in Docker: python -m unittest tests.phd.test_prior_propagation_v5"""
import hashlib
import unittest
from pathlib import Path

import numpy as np

from src.phd.prior_propagation_v5 import locations as L
from src.phd.prior_propagation_v5 import registration as G
from src.phd.prior_propagation_v5 import rule
from src.phd.prior_propagation_v5 import rules as R
from src.phd.prior_propagation_v5 import switches as S
from src.phd.prior_propagation_v5 import tallies as T

ROOT = Path(__file__).resolve().parents[2]


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


class CopiedV5(unittest.TestCase):
    def test_bytes(self):
        for f in ("conversion.py", "faces.py", "orientation.py", "outlines.py", "rule.py", "seat.py", "surfaces.py", "tolerance.py"):
            self.assertEqual(sha(ROOT / "src/phd/prior_propagation_v4" / f), sha(ROOT / "src/phd/prior_propagation_v5" / f), f)
        v4 = (ROOT / "src/phd/prior_propagation_v4/locations.py").read_text()
        v5 = (ROOT / "src/phd/prior_propagation_v5/locations.py").read_text()
        self.assertTrue(v5.startswith(v4.rstrip("\n")))
        self.assertIn("def k_nearest_support_ids(", v5[len(v4.rstrip("\n")):])


def plane_store(n=24):
    """a flat 6 m x 6 m roof in two surfaces (left / right halves)."""
    V = np.array([[0, 0, 0], [3, 0, 0], [3, 6, 0], [0, 6, 0], [6, 0, 0], [6, 6, 0]], float)
    F = np.array([[0, 1, 2], [0, 2, 3], [1, 4, 5], [1, 5, 2]])
    ts = np.array([1, 1, 2, 2])
    rect = np.array([[0.0, 0.0], [6.0, 6.0]])
    return L.build_plane_store(V, F, ts, [dict(ext=1, normal=[0, 0, 1.0]), dict(ext=2, normal=[0, 0, 1.0])], rect, 0.25)


class NeighbourIds(unittest.TestCase):
    def test_same_gathering(self):
        st = plane_store()
        n = len(st["loc_area"])
        rng = np.random.default_rng(1)
        state = rng.choice([rule.ST_SUPPORT, rule.ST_MISSING, rule.ST_INVISIBLE], n, p=[0.6, 0.3, 0.1]).astype(np.int8)
        vote = np.where(state == rule.ST_SUPPORT, rng.choice([rule.V_AGREE, rule.V_CONFLICT], n), rule.V_NONE).astype(np.int8)
        Gr = L.graph(st)
        mis, kd, kv = L.k_nearest_support(Gr, st["loc_surface"], state, vote, 5, 1.0)
        mis2, kd2, kid = L.k_nearest_support_ids(Gr, st["loc_surface"], state, 5, 1.0)
        self.assertTrue(np.array_equal(mis, mis2)); self.assertTrue(np.array_equal(kd, kd2))
        self.assertTrue(np.array_equal(kv, np.where(kid >= 0, vote[np.maximum(kid, 0)], rule.V_NONE)))
        J, _ = L.propagate(st, state, vote, 2 / 3, 5, 1.0)
        J2 = R.judge(mis2, kd2, kid, vote, n, R.RULES["current"], 2 / 3, 5, 1.0)
        self.assertTrue(np.array_equal(J, J2))


def pairs_example():
    # 3 units x 3 views; unit 0 support (agree at tau, conflict at 0.5 tau), unit 1 missing, unit 2 support with big residuals
    loc = np.array([0, 0, 0, 1, 1, 1, 2, 2, 2]); view = np.tile([0, 1, 2], 3)
    npix = np.array([10, 10, 10, 10, 10, 10, 10, 10, 10]); na1 = np.array([10, 10, 8, 2, 3, 10, 10, 10, 10])
    le = np.zeros((9, len(T.THRESHOLDS)), int)
    le[0:3] = [[2, 9, 10, 10, 10], [3, 8, 10, 10, 10], [1, 6, 8, 8, 8]]
    le[3:6] = [[1, 2, 2, 2, 2], [1, 3, 3, 3, 3], [5, 9, 10, 10, 10]]
    le[6:9] = [[0, 1, 2, 3, 3], [0, 0, 1, 2, 4], [0, 2, 3, 3, 5]]
    return dict(loc=loc, view=view, npix=npix, na1=na1, le=le)


class RulesV5(unittest.TestCase):
    def test_votes_match_tallies(self):
        p = pairs_example()
        acc = T.new_acc(3)
        for v in range(3):
            m = p["view"] == v
            nag = p["le"][m, 1]; ncf = p["na1"][m] - nag
            T.accumulate(acc, p["loc"][m], p["npix"][m], p["na1"][m], nag, ncf)
        st, vote, _ = T.unit_states(acc)
        st2, vote2 = R.votes_at(p, 3, 1.0)
        self.assertTrue(np.array_equal(st, st2)); self.assertTrue(np.array_equal(vote, vote2))
        self.assertEqual(list(st), [rule.ST_SUPPORT, rule.ST_MISSING, rule.ST_SUPPORT])
        self.assertEqual(int(vote[2]), rule.V_CONFLICT)
        _, v_half = R.votes_at(p, 3, 0.5); _, v3 = R.votes_at(p, 3, 3.0)
        self.assertEqual(int(v_half[0]), rule.V_CONFLICT); self.assertEqual(int(v3[2]), rule.V_CONFLICT)
        big2 = R.big_residual(p, 3, 2.0)
        self.assertTrue(bool(big2[2])); self.assertFalse(bool(big2[0]))

    def test_propagation_variants(self):
        kd = np.array([[0.1, 0.2, 0.3, 0.4, 0.5], [0.1, 0.2, 0.3, 0.4, 0.5], [0.1, 0.2, 0.3, 0.4, np.inf]])
        kid = np.array([[0, 1, 2, 3, 4], [0, 1, 2, 3, 4], [0, 1, 2, 3, -1]])
        vote = np.array([rule.V_CONFLICT] * 4 + [rule.V_AGREE, rule.V_NONE, rule.V_NONE], np.int8)
        big = np.array([True, True, False, False, False, False, False])
        mis = np.array([5, 6, 6])[:2]
        J = R.judge(np.array([5, 6]), kd[:2], kid[:2], vote, 7, R.RULES["current"], 2 / 3, 5, 1.0)
        self.assertEqual(int(J[5]), rule.J_CONFLICT)
        Jm = R.judge(np.array([5, 6]), kd[:2], kid[:2], vote, 7, R.RULES["margin_prop_2"], 2 / 3, 5, 1.0, big)
        self.assertEqual(int(Jm[5]), rule.J_MIXED)              # only 2 big conflicts out of 5 gathered
        Ja = R.judge(np.array([5, 6]), kd[:2], kid[:2], vote, 7, R.RULES["asymmetric"], 2 / 3, 5, 1.0)
        self.assertEqual(int(Ja[5]), rule.J_MIXED)
        Ji = R.judge(np.array([5]), kd[2:], kid[2:], vote, 7, R.RULES["current"], 2 / 3, 5, 1.0)
        self.assertEqual(int(Ji[5]), rule.J_INSUFF)
        state = np.array([1, 1, 1, 1, 1, 2, 2], np.int8)
        d = R.discard(state, vote, J)
        self.assertTrue(bool(d[0]) and not bool(d[4]) and bool(d[5]))


class SwitchesV5(unittest.TestCase):
    def test_judgment_level(self):
        state = np.array([1, 1, 2, 2, 0], np.int8); vote = np.array([0, 1, -1, -1, -1], np.int8); J = np.array([-1, -1, 0, 2, -1], np.int8)
        v, j, jl = S.judgment_level(state, vote, J, S.DEFAULT)
        self.assertTrue(np.array_equal(v, vote) and np.array_equal(j, J))
        v, j, jl = S.judgment_level(state, vote, J, dict(S.DEFAULT, judgment=False))
        self.assertTrue((jl[:4] == rule.J_AGREE).all() and jl[4] == rule.J_NONE)
        v, j, jl = S.judgment_level(state, vote, J, dict(S.DEFAULT, propagation=False))
        self.assertTrue((j[2:4] == rule.J_INSUFF).all() and v[1] == rule.V_CONFLICT)
        self.assertTrue(S.planted(state, jl, dict(S.DEFAULT, init_exclusion=False)).all())
        jl0 = np.array([0, 0, 0, 1, -1], np.int8)
        self.assertFalse(bool(S.planted(state, jl0, S.DEFAULT)[2]))


class RegistrationV5(unittest.TestCase):
    def test_vertical_and_final_check(self):
        dz, m, s = G.vertical_shift(lambda sh: (0.3, 0.1), np.zeros(2))
        self.assertEqual(dz, 0.3)
        dz, m, s = G.vertical_shift(lambda sh: (0.05, 0.1), np.zeros(2))
        self.assertEqual(dz, 0.0)
        self.assertTrue(G.final_check_fails(np.array([0.1, 0.0]), 0.10, 0.19))
        self.assertFalse(G.final_check_fails(np.array([0.1, 0.0]), 0.10, 0.09))
        self.assertFalse(G.final_check_fails(np.zeros(2), 0.10, 0.19))


if __name__ == "__main__":
    unittest.main()
