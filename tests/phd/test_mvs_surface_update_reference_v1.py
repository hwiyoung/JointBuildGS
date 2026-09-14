"""Reference-only cohort freezing and paired coverage/error accounting."""
import unittest

import numpy as np

from scripts.phd.mvs_surface_update_v1.evaluate_reference import (
    front_return_cohort, reference_masks, score_cohort,
)


CAMERA = dict(K=np.eye(3), R=np.eye(3), t=np.zeros(3), width=5, height=5)


class ReferenceDiagnosticTests(unittest.TestCase):
    def test_frontmost_return_and_original_id_tie_break(self):
        target, surrounding = reference_masks(CAMERA, [2, 2, 3, 3], 1)
        points = np.array([[2., 2., 1.], [4., 4., 2.], [2., 2., 1.],
                           [-2., 0., 1.], [3., 2., 1.], [np.nan, 0., 1.]])
        cohort = front_return_cohort(points, CAMERA, target, surrounding)
        np.testing.assert_array_equal(cohort['reference_original_indices'], [0, 4])
        np.testing.assert_array_equal(cohort['domain_code'], [1, 2])
        self.assertEqual(cohort['excluded_rear_or_duplicate_returns'], 2)
        np.testing.assert_array_equal(cohort['returns_per_selected_pixel'], [3, 1])

    def test_subpixel_reference_offset_is_preserved(self):
        target, surrounding = reference_masks(CAMERA, [2, 2, 3, 3], 1)
        points = np.array([[2.2, 1.8, 1.]])
        cohort = front_return_cohort(points, CAMERA, target, surrounding)
        np.testing.assert_array_equal(cohort['reference_pixel_xy'], [[2, 2]])
        self.assertAlmostEqual(cohort['projection_rounding_error_px'][0], np.sqrt(.08))
        arrays = {k: np.ones((5, 5)) for k in ('depth_before', 'depth_after', 'alpha_before', 'alpha_after')}
        paired, _ = score_cohort(cohort, CAMERA, arrays)
        self.assertAlmostEqual(paired['before_signed_camera_z_error_m'][0], 0.)
        self.assertAlmostEqual(paired['before_distance_to_same_return_m'][0], np.sqrt(.08))

    def test_lost_after_support_stays_in_frozen_reference_denominator(self):
        target, surrounding = reference_masks(CAMERA, [2, 2, 3, 3], 1)
        cohort = front_return_cohort(np.array([[2., 2., 1.], [3., 2., 1.], [1., 2., 1.]]), CAMERA, target, surrounding)
        arrays = {k: np.ones((5, 5)) for k in ('depth_before', 'depth_after', 'alpha_before', 'alpha_after')}
        arrays['depth_before'][2, 2] = 1.2
        arrays['depth_after'][2, 2] = 1.1
        arrays['depth_after'][2, 3] = 1.2
        arrays['alpha_after'][2, 1] = .49
        paired, summary = score_cohort(cohort, CAMERA, arrays)
        np.testing.assert_array_equal(paired['reference_original_indices'], cohort['reference_original_indices'])
        self.assertEqual(summary['target']['transitions'][0]['improved'], 1)
        self.assertEqual(summary['surrounding']['frozen_reference_count'], 2)
        self.assertEqual(summary['surrounding']['paired_valid'], 1)
        self.assertEqual(summary['surrounding']['lost_after'], 1)
        self.assertEqual(summary['surrounding']['missing_after'], 1)
        self.assertEqual(summary['surrounding']['transitions'][1]['damaged'], 1)
        self.assertAlmostEqual(summary['surrounding']['after_coverage'], .5)

    def test_no_reference_is_absent_not_zero_error(self):
        target, surrounding = reference_masks(CAMERA, [2, 2, 3, 3], 1)
        cohort = front_return_cohort(np.empty((0, 3)), CAMERA, target, surrounding)
        arrays = {k: np.ones((5, 5)) for k in ('depth_before', 'depth_after', 'alpha_before', 'alpha_after')}
        paired, summary = score_cohort(cohort, CAMERA, arrays)
        self.assertEqual(len(paired['reference_original_indices']), 0)
        for row in summary.values():
            self.assertEqual(row['status'], 'NOT_ASSESSED_REFERENCE_ABSENT')
            self.assertIsNone(row['before_coverage'])
            self.assertIsNone(row['paired_before_absolute_camera_z_error_m']['mean'])

    def test_identical_arms_have_no_recovery_or_damage(self):
        target, surrounding = reference_masks(CAMERA, [2, 2, 3, 3], 1)
        cohort = front_return_cohort(np.array([[2., 2., 1.]]), CAMERA, target, surrounding)
        arrays = {k: np.ones((5, 5)) for k in ('depth_before', 'depth_after', 'alpha_before', 'alpha_after')}
        arrays['depth_before'][:] = 1.3
        arrays['depth_after'][:] = 1.3
        _, summary = score_cohort(cohort, CAMERA, arrays)
        self.assertEqual(summary['target']['paired_absolute_error_delta_m']['mean'], 0.)
        self.assertEqual(summary['target']['transitions'][0]['improved'], 0)
        self.assertEqual(summary['target']['transitions'][0]['damaged'], 0)


if __name__ == '__main__': unittest.main()
