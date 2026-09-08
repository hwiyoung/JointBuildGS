import unittest
import numpy as np
from src.phd.source_candidate_v1.geometry import fit_candidate, cell_membership

CFG = dict(min_points=6, fit_cap=512, seed=41, ransac_trials=64, inlier_distance_m=.15,
           minimum_inlier_fraction=.6, minimum_second_spread_m=.08)


class CandidateGeometryTest(unittest.TestCase):
    def test_sloped_plane_preserves_native_rows_and_rejects_outliers(self):
        x, y = np.meshgrid(np.linspace(-1, 1, 12), np.linspace(-1, 1, 12))
        xyz = np.c_[x.ravel(), y.ravel(), (.2*x-.3*y+2).ravel()]
        xyz = np.r_[xyz, [[.5, .2, 5], [-.6, .8, -2]]]
        original = xyz.copy()
        result, mask = fit_candidate(xyz, np.array([0, 0, 1]), CFG)
        self.assertTrue(result['valid'])
        self.assertEqual(mask.sum(), 144)
        np.testing.assert_array_equal(xyz, original)
        self.assertLess(result['rms_m'], 1e-10)

    def test_linear_and_sparse_geometry_are_not_surfaces(self):
        xyz = np.c_[np.arange(10), np.zeros(10), np.ones(10)]
        self.assertFalse(fit_candidate(xyz, np.array([0, 0, 1]), CFG)[0]['valid'])
        self.assertFalse(fit_candidate(xyz[:3], np.array([0, 0, 1]), CFG)[0]['valid'])

    def test_membership_half_open_and_all_units(self):
        xyz = np.array([[0, 0, 0], [1.99, 0, 0], [2, 2, 0], [4, 2, 0]])
        ids, shape = cell_membership(xyz, dict(x=[0, 4], y=[0, 4], z=[-1, 1]), 2)
        np.testing.assert_array_equal(ids, [0, 0, 3, -1])
        np.testing.assert_array_equal(shape, [2, 2])

    def test_two_equal_layers_are_not_accepted_as_one_surface(self):
        x, y = np.meshgrid(np.linspace(0, 2, 10), np.linspace(0, 2, 10))
        xyz = np.r_[np.c_[x.ravel(),y.ravel(),np.zeros(100)], np.c_[x.ravel(),y.ravel(),np.ones(100)*3]]
        self.assertFalse(fit_candidate(xyz, np.array([0, 0, 1]), CFG)[0]['valid'])


if __name__ == '__main__':
    unittest.main()
