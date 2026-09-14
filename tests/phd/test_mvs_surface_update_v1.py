"""Evidence-admission regressions: support identity and depth identifiability."""
import unittest

import numpy as np

from src.phd.mvs_surface_update_v1 import assess, curve_summary


CFG = {
    'candidate_threshold_m': .5,
    'minimum_photo_margin': .03,
    'minimum_joint_views': 2,
    'profile_maximum_cost': .2,
    'profile_maximum_width_m': .5,
    'profile_maximum_spacing_m': .25,
    'profile_maximum_mvs_offset_m': .5,
    'minimum_patch_parallax_degrees': 1.,
}


def fixture():
    """Only observation 1 has a measured profile; six neighbor IDs are stable."""
    profile = np.tile([.5, .3, .05, .3, .5], (4, 1, 2, 1))
    photo = np.full((6, 3, 2), np.nan)
    photo[:4, 1] = [.2, .05]
    status = np.zeros((6, 3), dtype=np.int8)
    status[:4, 1] = 3
    return {
        'point_delta': np.array([np.nan, 1., .1]),
        'point_mvs_depth': np.array([np.nan, 10., 9.]),
        'point_parallax_deg': np.array([np.nan, 5., 5.]),
        'profile_point_indices': np.array([1]),
        'profile_depths': np.array([[9.6, 9.8, 10., 10.2, 10.4]]),
        'profile_per_neighbor_costs': profile,
        'photo_costs_per_neighbor': photo,
        'prior_self_status': status.copy(),
        'mvs_self_status': status.copy(),
    }


class EvidenceAdmissionTests(unittest.TestCase):
    def test_admitted_views_need_their_own_parallax(self):
        data = fixture()
        data['per_neighbor_parallax_deg'] = np.full((6,3), .1)
        data['per_neighbor_parallax_deg'][4:,1] = 10.
        result = assess(data, CFG)
        self.assertFalse(result['accepted'][1])
        self.assertEqual(result['admitted'][:,1].sum(), 0)

    def test_valid_profile_maps_back_to_its_observation(self):
        result = assess(fixture(), CFG)
        np.testing.assert_array_equal(result['accepted'], [False, True, False])
        np.testing.assert_array_equal(result['agree'], [False, False, True])
        self.assertEqual(result['joint_count'][1], 4)
        self.assertAlmostEqual(result['profile_best'][1], 10.)
        self.assertEqual(result['reasons'][1], [])

    def test_singleton_low_cost_does_not_hide_coarse_depth_grid(self):
        data = fixture()
        data['profile_depths'][0] = [8., 9., 10., 11., 12.]
        result = assess(data, CFG)
        self.assertEqual(result['profile_stats']['width'][1], 0.)
        self.assertFalse(result['accepted'][1])
        self.assertIn('resolved_depth_grid', result['reasons'][1])

    def test_support_in_other_neighbor_ids_cannot_authorize_profile(self):
        data = fixture()
        data['prior_self_status'][:] = 0
        data['mvs_self_status'][:] = 0
        data['prior_self_status'][4:, 1] = 3
        data['mvs_self_status'][4:, 1] = 3
        data['photo_costs_per_neighbor'][4:, 1] = [.2, .05]
        result = assess(data, CFG)
        self.assertFalse(result['accepted'][1])
        self.assertEqual(result['joint_count'][1], 0)
        self.assertTrue(np.isnan(result['profile_best'][1]))

    def test_both_hypotheses_need_own_model_visibility(self):
        data = fixture()
        data['prior_self_status'][:2, 1] = 4
        data['mvs_self_status'][2:4, 1] = 4
        result = assess(data, CFG)
        self.assertEqual(result['admitted'][:, 1].sum(), 0)
        self.assertFalse(result['accepted'][1])

    def test_opposing_admissible_views_remain_in_curve(self):
        data = fixture()
        data['profile_per_neighbor_costs'][:2, 0] = [.5, .4, .02, .3, .5]
        data['profile_per_neighbor_costs'][2:, 0] = [.6, .5, .8, .01, .5]
        data['photo_costs_per_neighbor'][2:4, 1] = [.05, .2]
        result = assess(data, CFG)
        self.assertEqual(result['joint_count'][1], 2)
        self.assertEqual(result['opposite'][:, 1].sum(), 2)
        self.assertEqual(result['admitted'][:, 1].sum(), 4)
        # Dropping the opposing views would incorrectly choose 10.0m and .02.
        self.assertAlmostEqual(result['profile_best'][1], 10.2)
        self.assertAlmostEqual(result['profile_stats']['cost'][1], .155)

    def test_invisible_views_are_removed_before_profile_aggregation(self):
        data = fixture()
        data['profile_per_neighbor_costs'][2:, 0] = [.01, .01, .9, .9, .9]
        data['mvs_self_status'][2:4, 1] = 4
        result = assess(data, CFG)
        self.assertEqual(result['admitted'][:, 1].sum(), 2)
        self.assertAlmostEqual(result['profile_best'][1], 10.)
        self.assertAlmostEqual(result['profile_stats']['cost'][1], .05)
        self.assertTrue(result['accepted'][1])

    def test_unmeasured_profile_is_missing_not_zero_uncertainty(self):
        data = fixture()
        data['point_delta'][2] = 1.
        data['prior_self_status'][:, 2] = 3
        data['mvs_self_status'][:, 2] = 3
        data['photo_costs_per_neighbor'][:, 2] = [.2, .05]
        result = assess(data, CFG)
        self.assertFalse(result['accepted'][2])
        self.assertTrue(np.isnan(result['profile_stats']['width'][2]))
        self.assertTrue(np.isnan(result['profile_best'][2]))

    def test_profile_minimum_must_locate_the_proposed_mvs_depth(self):
        data = fixture()
        data['point_mvs_depth'][1] = 12.
        result = assess(data, CFG)
        self.assertFalse(result['accepted'][1])
        self.assertIn('mvs_matches_profile', result['reasons'][1])

    def test_tied_boundary_minimum_is_not_interior(self):
        depths = np.array([[9.6, 9.8, 10., 10.2, 10.4]])
        costs = np.array([[.05, .4, .05, .4, .5]])
        result = curve_summary(depths, costs)
        self.assertEqual(result['edge'][0], 1)
        self.assertEqual(result['boundary'][0], 1)
        self.assertEqual(result['modes'][0], 2)


if __name__ == '__main__':
    unittest.main()
