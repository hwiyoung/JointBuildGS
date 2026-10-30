"""Scientific boundary tests for the candidate-selection order, without training."""
import unittest
import numpy as np
from scripts.phd.main_candpick_v1.rules import classify_places, outcomes, in_candidate_column


class CandidatePickRules(unittest.TestCase):
    def test_gap_and_truth_boundaries_and_exclusion_partition(self):
        # Exact 2*tau with GT midway is deliberately excluded as both-right.
        m = [np.nan, .399, .4, .5, .5, .5, .5]
        g = [0., 0., .2, np.nan, 1., 0., .5]
        r = classify_places(m, g, .2, np.zeros(7, dtype=int))
        self.assertEqual(r['reason'].tolist(), ['missing_mvs', 'gap_below_2tau',
            'both_right', 'missing_gt', 'both_wrong', 'eligible', 'eligible'])
        self.assertEqual(int(r['eligible'].sum()), 2)

    def test_front_back_is_relative_to_correct_candidate(self):
        r = classify_places([1., -1., 1., -1.], [1., -1., 0., 0.], .2, [1, 1, 0, 0])
        self.assertEqual(r['right'].tolist(), ['image', 'image', 'prior', 'prior'])
        self.assertEqual(r['side'].tolist(), ['front', 'back', 'back', 'front'])
        self.assertEqual(r['group'].tolist(), ['a'] * 4)

    def test_all_photo_labels_for_both_correct_sides(self):
        r = classify_places([1.] * 10, [0.] * 5 + [1.] * 5, .2, list(range(5)) * 2)
        self.assertEqual(r['group'].tolist(), ['a', 'c', 'b', 'b', 'b', 'c', 'a', 'b', 'b', 'b'])
        with self.assertRaises(ValueError):
            classify_places([1.], [0.], .2, [-1])

    def test_outcomes_do_not_hide_missing_or_threshold_ties(self):
        r = outcomes([.5, .49, .5, .49, np.nan, 1.1], [.49, .5, .5, .49, .1, .1])
        self.assertEqual(r.tolist(), ['right_only', 'wrong_only', 'both', 'neither', 'unavailable', 'unavailable'])

    def test_column_uses_normal_not_world_z(self):
        # Normal is +X, tangents +Y/+Z: correct interval is X in [-1.2, 3].
        q = [[-1.2, .25, .25], [3., -.25, -.25], [-1.20001, 0, 0],
             [3.00001, 0, 0], [0, .25001, 0], [0, 0, .25001]]
        mask = in_candidate_column(q, [0, 0, 0], [0, 1, 0], [0, 0, 1], [1, 0, 0], -1., .2)
        self.assertEqual(mask.tolist(), [True, True, False, False, False, False])

    def test_invalid_geometry_is_not_imputed(self):
        with self.assertRaises(ValueError):
            in_candidate_column([[0, 0, 0]], [0, 0, 0], [0, 0, 0], [0, 1, 0], [0, 0, 1], 1., .2)


if __name__ == '__main__':
    unittest.main()
