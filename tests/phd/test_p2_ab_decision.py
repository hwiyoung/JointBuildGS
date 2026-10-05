import unittest
import numpy as np

from src.phd.p2_ab_v1.decision import (common_curve, finite_range,
    gaussian_uniform_posterior, posterior_candidate, choose_action, strict_action,
    acceptance_metrics, UNKNOWNS, CERTIFICATION_CONTRACTS)


class DecisionContractTests(unittest.TestCase):
    def test_missing_height_cannot_change_pair_support(self):
        rho = np.array([[.8, .7, .6], [.8, np.nan, .6], [.8, .7, .6]])
        curve, pairs = common_curve(rho, [[1, 2], [3, 4], [5, 6]], minimum_pairs=2)
        np.testing.assert_array_equal(pairs, [0, 2])
        np.testing.assert_allclose(curve, .7)

    def test_camera_matching_never_reuses_view(self):
        _, pairs = common_curve(np.ones((3, 4)), [[1, 2], [2, 3], [3, 4], [1, 5]], 1, True)
        np.testing.assert_array_equal(pairs, [0, 2])

    def test_remote_mode_prevents_finite_support(self):
        r = finite_range([-2, -1, 0, 1, 2], [0, .8, .9, 0, 0], .5, .25)
        self.assertEqual(r['state'], 'AMBIGUOUS')
        self.assertIsNone(r['conditional_budget_m'])

    def test_boundary_dominates_apparent_tolerance(self):
        r = finite_range([-2, -1, 0, 1, 2], [.8, 0, 0, 0, 0], .5, 4)
        self.assertEqual(r['state'], 'SEARCH_BOUNDARY_UNRESOLVED')

    def test_empty_is_model_failure_not_prior_rejection(self):
        r = finite_range([-1, 0, 1], [0, 0, 0], .5, .5)
        self.assertEqual(r['state'], 'MODEL_MISMATCH')
        self.assertIsNone(r['upper_m'])

    def test_shared_bias_removes_unjustified_budget(self):
        r = finite_range([-1, 0, 1], [0, 1, 0], .5, .25, shared_shift_radius=.5)
        self.assertEqual(r['state'], 'AMBIGUOUS')
        self.assertIsNone(r['conditional_budget_m'])

    def test_bayes_symmetric_peak_is_symmetric_posterior(self):
        h = np.linspace(-2, 2, 33)
        rho = np.tile((1 - h ** 2)[:, None], (1, 6))
        p = gaussian_uniform_posterior(h, rho, np.full(6, .1))
        np.testing.assert_allclose(p['height_mass'], p['height_mass'][::-1])
        self.assertAlmostEqual(p['height_mass'].sum(), 1)
        self.assertGreater(posterior_candidate(p, h, 0, .25)['probability_within_tolerance'], .9)
        self.assertLess(posterior_candidate(p, h, 1, .25)['probability_within_tolerance'], .1)

    def test_flat_curve_never_becomes_bayes_measurement(self):
        self.assertIsNone(gaussian_uniform_posterior(np.arange(5.), np.ones((5, 3)), np.ones(3)))

    def test_fusion_requires_both_parent_eligibilities(self):
        cs = {'PRIOR': {'score': .9}, 'IMAGE': {'score': .1},
              'FUSION': {'score': .99, 'parent_geometry_compatible': True}}
        self.assertEqual(choose_action(cs, 'SCORE_GATE', .5), 'PRIOR')

    def test_missing_mvs_only_prior_or_abstain(self):
        self.assertEqual(choose_action({'PRIOR': {'score': .9}}, 'SCORE_GATE'), 'PRIOR')
        self.assertEqual(choose_action({'PRIOR': {'score': .1}}, 'SCORE_GATE'), 'ABSTAIN')

    def test_certification_contracts_do_not_default_true(self):
        self.assertEqual(strict_action('PRIOR'), 'ABSTAIN')

    def test_unresolved_reason_flags_are_not_certification(self):
        self.assertEqual(strict_action('PRIOR', {key: True for key in UNKNOWNS}), 'ABSTAIN')
        self.assertEqual(strict_action('PRIOR', {key: True for key in CERTIFICATION_CONTRACTS}), 'PRIOR')

    def test_no_acceptance_risk_null_and_valid_abstention_counted(self):
        m = acceptance_metrics(['ABSTAIN'], [{'IMAGE': True, 'PRIOR': True}], [{}])
        self.assertIsNone(m['false_acceptance_rate'])
        self.assertEqual(m['usable_but_abstained'], 1)

    def test_unknown_reference_stays_out_of_risk_denominator(self):
        m = acceptance_metrics(['PRIOR', 'IMAGE'], [{'PRIOR': None}, {'IMAGE': False}],
                               [{'PRIOR': None}, {'IMAGE': 2}])
        self.assertEqual(m['accepted'], 2)
        self.assertEqual(m['reference_unknown_accepted'], 1)
        self.assertEqual(m['false_acceptance_rate'], 1)


if __name__ == '__main__':
    unittest.main()
