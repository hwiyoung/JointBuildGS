"""Boundary and ambiguity regressions for the standalone evidence driver."""
import unittest

import numpy as np

from scripts.phd.mvs_evidence_v1.build import Builder, profile_summary


class ProfileSummaryTests(unittest.TestCase):
    def test_profile_plane_must_not_restore_a_missing_raw_ray(self):
        builder = Builder.__new__(Builder)
        builder.cfg = dict(patch_radius=3, profile_padding_m=2., profile_samples=5,
                           profile_neighbors=2, texture_std=0., profile_excess_cost=.03)
        K = np.array([[60., 0., 50.], [0., 60., 40.], [0., 0., 1.]])
        view = dict(K=K, R=np.eye(3), t=np.zeros(3), width=101, height=81)
        gray = np.random.default_rng(7).uniform(.1, .9, (81, 101))
        ref = dict(view=view, gray=gray)
        neighbors = [dict(view=dict(view, t=np.array([-b, 0., 0.])), gray=gray) for b in (1., 2.)]
        raw_prior = np.full((1, 49), 10.); raw_mvs = raw_prior.copy()
        raw_prior[0, 0] = np.nan  # Center is valid, but one original ray is absent.
        result = builder.profiles(np.array([[50., 40.]]), np.array([10.]), np.array([10.]),
                                  raw_prior, raw_mvs, ref, neighbors)
        self.assertEqual(result['neighbor_count'][0], 0)
        self.assertTrue(np.isnan(result['width'][0]))

    def test_equal_minimum_at_right_boundary_must_be_reported(self):
        depths = np.array([[8., 9., 10., 11.]])
        cost = np.array([[.2, .1, .3, .1]])
        summary = profile_summary(depths, cost, .03)
        self.assertTrue(summary['edge'][0])
        self.assertEqual(summary['modes'][0], 2)
        self.assertEqual(summary['width'][0], 2.)

    def test_disconnected_low_cost_intervals_and_undefined_profile(self):
        depths = np.array([[8., 9., 10., 11., 12.]]*2)
        cost = np.array([[.3, .1, .11, .4, .12], [.3, .1, np.nan, .4, .12]])
        summary = profile_summary(depths, cost, .03)
        self.assertEqual(summary['modes'][0], 2)
        self.assertEqual(summary['width'][0], 3.)
        self.assertTrue(np.isnan(summary['width'][1]))
        self.assertTrue(np.isnan(summary['best'][1]))

    def test_flat_profile_spans_complete_search_and_touches_boundary(self):
        depths = np.array([[8., 9., 10., 11.]])
        summary = profile_summary(depths, np.full_like(depths, .2), .03)
        self.assertEqual(summary['width'][0], 3.)
        self.assertEqual(summary['modes'][0], 1)
        self.assertTrue(summary['edge'][0])


if __name__ == '__main__':
    unittest.main()
