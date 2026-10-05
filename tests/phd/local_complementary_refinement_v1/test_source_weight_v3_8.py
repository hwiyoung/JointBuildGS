"""Algebra/contract checks only; no source-accuracy or Gaussian-update claim."""

import unittest

import numpy as np

from src.phd.local_source_weight_v3_8 import evidence_from_costs, weight_from_evidence


class CostEvidenceTests(unittest.TestCase):
    def test_supported_rejected_unknown_and_scale_reversal(self):
        costs = [[0, .05, .1], [.5, .7, 1], [.3, .3, .3], [.05, .8, .1]]
        actual = evidence_from_costs(costs, 1)
        np.testing.assert_allclose(actual, [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 1]], atol=1e-15)

    def test_weakest_scale_and_external_gate(self):
        support, rejection, unknown = evidence_from_costs([[.1, .2, .1], [.5, .4, .5]], [.8, .6])
        np.testing.assert_allclose(support, [.4, 0])
        np.testing.assert_allclose(rejection, [0, .3])
        np.testing.assert_allclose(unknown, [.6, .7])

    def test_missing_and_unknown_gate_do_not_become_rejection(self):
        costs = [[None, np.nan, np.inf], [0, 0, 0], [1, 1, 1]]
        support, rejection, unknown = evidence_from_costs(costs, 0)
        np.testing.assert_array_equal(support, np.zeros(3))
        np.testing.assert_array_equal(rejection, np.zeros(3))
        np.testing.assert_array_equal(unknown, np.ones(3))

    def test_broadcasting_and_finite_missing_mix(self):
        support, rejection, unknown = evidence_from_costs([0, 0, 0], [[0], [.5], [1]])
        np.testing.assert_array_equal(support, [[0], [.5], [1]])
        np.testing.assert_array_equal(rejection, np.zeros((3, 1)))
        np.testing.assert_array_equal(unknown, [[1], [.5], [0]])
        actual = evidence_from_costs([[None, None, None], [.1, .1, .1]], [0, 1])
        np.testing.assert_allclose(actual, [[0, 1], [0, 0], [1, 0]], atol=1e-15)

    def test_invalid_domains_and_shapes(self):
        cases = [([.1, .1], 1), (.1, 1), ([0, 0, 0], -1), ([0, 0, 0], 1.1),
                 ([0, 0, 0], np.nan), ([0, 0, 0], np.inf), ([-.1, .2, .3], 0),
                 ([1.1, .2, .3], 1), ([np.nan, .1, .1], .01),
                 ([np.inf, .1, .1], 1), ([[0, 0, 0], [0, 0, 0]], [0, 0, 0]),
                 ([1j, 0, 0], 1)]
        for costs, gate in cases:
            with self.subTest(costs=costs, gate=gate), self.assertRaises(ValueError):
                evidence_from_costs(costs, gate)

    def test_random_evidence_partition_and_cost_monotonicity(self):
        rng = np.random.default_rng(3801)
        costs = rng.random((10000, 3))
        gate = rng.random(10000)
        s, r, u = evidence_from_costs(costs, gate)
        self.assertTrue(np.all((s >= 0) & (r >= 0) & (u >= 0)))
        np.testing.assert_allclose(s + r + u, 1)
        np.testing.assert_array_equal(s * r, 0)
        s2, r2, _ = evidence_from_costs(np.minimum(1, costs + .1), gate)
        self.assertTrue(np.all(s2 <= s))
        self.assertTrue(np.all(r2 >= r))


class SourceWeightTests(unittest.TestCase):
    def test_all_nine_evidence_endpoints(self):
        states = {"support": (1, 0), "unknown": (0, 0), "reject": (0, 1)}
        # Columns: image support, unknown, reject. Rows: the same prior states.
        expected = [[(.005, .05), (.005, 0), (.055, 0)],
                    [(.005, .05), (.005, 0), (.005, 0)],
                    [(0, .055), (0, 0), (0, 0)]]
        for row, (pname, (sp, rp)) in enumerate(states.items()):
            for col, (iname, (si, ri)) in enumerate(states.items()):
                with self.subTest(prior=pname, image=iname):
                    np.testing.assert_allclose(weight_from_evidence(.005, .05, sp, rp, si, ri),
                                               expected[row][col], atol=1e-15)

    def test_disabled_source_never_receives_transferred_budget(self):
        rng = np.random.default_rng(3802)
        sp, si = rng.random((2, 1000))
        rp, ri = rng.random((2, 1000)) * (1 - np.array([sp, si]))
        wp, wi = weight_from_evidence(0, .05, sp, rp, si, ri)
        np.testing.assert_array_equal(wp, np.zeros(1000))
        np.testing.assert_allclose(wi, .05 * si)
        wp, wi = weight_from_evidence(.005, 0, sp, rp, si, ri)
        np.testing.assert_allclose(wp, .005 * (1 - rp))
        np.testing.assert_array_equal(wi, np.zeros(1000))
        wp, wi = weight_from_evidence(0, 0, sp, rp, si, ri)
        np.testing.assert_array_equal(wp + wi, np.zeros(1000))

    def test_random_budget_and_independent_amount_accounting(self):
        rng = np.random.default_rng(3803)
        cp, ci, sp, si = rng.random((4, 20000))
        rp, ri = rng.random((2, 20000)) * (1 - np.array([sp, si]))
        wp, wi = weight_from_evidence(cp, ci, sp, rp, si, ri)
        self.assertTrue(np.all((wp >= 0) & (wi >= 0)))
        self.assertTrue(np.all(wp + wi <= cp + ci + 1e-15))
        # Unspent budget: rejected prior without supported image; image not
        # supported, except the share rejected and transferred to supported prior.
        unused = cp * rp * (1 - si) + ci * ((1 - si - ri) + ri * (1 - sp))
        np.testing.assert_allclose(wp + wi + unused, cp + ci, atol=1e-15)

    def test_monotonic_transfer_of_rejected_prior_to_supported_image(self):
        rp = np.linspace(0, 1, 101)
        wp, wi = weight_from_evidence(.005, .05, 0, rp, 1, 0)
        self.assertTrue(np.all(np.diff(wp) <= 0))
        self.assertTrue(np.all(np.diff(wi) >= 0))
        np.testing.assert_allclose(wp + wi, .055)
        wp, wi = weight_from_evidence(.005, .05, 0, rp, 0, 0)
        np.testing.assert_array_equal(wi, np.zeros(101))
        self.assertTrue(np.all(np.diff(wp + wi) <= 0))

    def test_monotonic_transfer_of_rejected_image_to_supported_prior(self):
        ri = np.linspace(0, 1, 101)
        wp, wi = weight_from_evidence(.005, .05, 1, 0, 1 - ri, ri)
        self.assertTrue(np.all(np.diff(wp) >= 0))
        self.assertTrue(np.all(np.diff(wi) <= 0))
        np.testing.assert_allclose(wp + wi, .055)

    def test_high_both_and_scale_reversal_have_different_fallbacks(self):
        sp, rp, _ = evidence_from_costs([.6, .7, .8], 1)
        si, ri, _ = evidence_from_costs([.7, .8, .9], 1)
        np.testing.assert_allclose(weight_from_evidence(.005, .05, sp, rp, si, ri), [0, 0])
        sp, rp, _ = evidence_from_costs([.1, .3, .8], 1)
        si, ri, _ = evidence_from_costs([.8, .3, .1], 1)
        np.testing.assert_allclose(weight_from_evidence(.005, .05, sp, rp, si, ri), [.005, 0])
        sp, rp, _ = evidence_from_costs([None, None, None], 0)
        si, ri, _ = evidence_from_costs([None, None, None], 0)
        np.testing.assert_allclose(weight_from_evidence(.005, .05, sp, rp, si, ri), [.005, 0])

    def test_broadcasting_and_inputs_not_mutated(self):
        cp = np.array([[.005], [0]])
        si = np.array([0, .5, 1])
        before_cp, before_si = cp.copy(), si.copy()
        wp, wi = weight_from_evidence(cp, .05, 0, 1, si, 0)
        np.testing.assert_array_equal(wp, np.zeros((2, 3)))
        np.testing.assert_allclose(wi, [[0, .0275, .055], [0, .025, .05]])
        np.testing.assert_array_equal(cp, before_cp)
        np.testing.assert_array_equal(si, before_si)

    def test_invalid_domains(self):
        for pos in range(6):
            for invalid in (-.1, np.nan, np.inf, 1j):
                args = [.005, .05, .2, .3, .4, .5]
                args[pos] = invalid
                with self.subTest(pos=pos, invalid=invalid), self.assertRaises(ValueError):
                    weight_from_evidence(*args)
        for args in [(1, 1, 1.1, 0, 0, 0), (1, 1, .8, .3, 0, 0),
                     (1, 1, 0, 0, .4, .7), (1e308, 1e308, 0, 0, 0, 0),
                     ([1, 1], [1, 1, 1], 0, 0, 0, 0)]:
            with self.subTest(args=args), self.assertRaises(ValueError):
                weight_from_evidence(*args)

    def test_l1_finite_difference_distinct_identical_and_opposed_targets(self):
        configurations = [(.005, .05, 1, 0, 1, 0), (.005, .05, 0, 1, 1, 0),
                          (.005, .05, 1, 0, 0, 1), (.005, .05, 0, 0, 0, 0),
                          (.005, .05, 0, 1, 0, 1), (0, .05, 1, 0, 0, 1)]
        for args in configurations:
            wp, wi = weight_from_evidence(*args)
            for dp, di in [(2., 5.), (3., 3.)]:
                prediction = np.array([0., 2.5, 3.5, 7.])
                eps = 1e-5
                def loss(x):
                    return wp * np.abs(x - dp) + wi * np.abs(x - di)
                numerical = (loss(prediction + eps) - loss(prediction - eps)) / (2 * eps)
                expected = wp * np.sign(prediction - dp) + wi * np.sign(prediction - di)
                with self.subTest(args=args, targets=(dp, di)):
                    np.testing.assert_allclose(numerical, expected, atol=1e-10, rtol=1e-9)
                    if dp == di:
                        np.testing.assert_allclose(expected, (wp + wi) * np.sign(prediction - dp))


if __name__ == "__main__":
    unittest.main()
