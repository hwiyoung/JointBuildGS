import unittest
import numpy as np
from src.phd.p2_ab_v1.evaluation import geometry_metrics, decision_accounting


class EvaluationContracts(unittest.TestCase):
    def test_missing_prediction_retains_reference_denominator(self):
        m, _ = geometry_metrics(np.empty((0, 3)), [[0, 0, 0], [1, 0, 0]])
        self.assertIsNone(m['prediction_to_reference']['p90_m'])
        self.assertEqual(m['tolerance_sweep'][0]['reference_recall'], 0)
        self.assertEqual(m['tolerance_sweep'][0]['missing_reference_point_count'], 2)
        self.assertIsNone(m['tolerance_sweep'][0]['prediction_precision'])

    def test_reference_absence_is_unknown(self):
        m, _ = geometry_metrics([[0, 0, 0]], np.empty((0, 3)))
        self.assertIsNone(m['tolerance_sweep'][0]['reference_recall'])
        self.assertEqual(m['reference_status'], 'REFERENCE_ABSENT')

    def test_omitting_bad_surface_improves_precision_but_not_recall(self):
        ref = [[0, 0, 0], [2, 0, 0]]
        m, _ = geometry_metrics([[0, 0, 0]], ref)
        self.assertEqual(m['tolerance_sweep'][0]['prediction_precision'], 1)
        self.assertEqual(m['tolerance_sweep'][0]['reference_recall'], .5)

    def test_false_accept_zero_acceptance_null(self):
        m = decision_accounting([dict(action='ABSTAIN', candidate_ok={'IMAGE': True, 'PRIOR': False})])
        self.assertIsNone(m['false_accept_rate_evaluated'])
        self.assertEqual(m['usable_abstention_rate'], 1)

    def test_multiple_valid_candidates_and_unknown_are_distinct(self):
        rows = [dict(action='PRIOR', candidate_ok={'IMAGE': True, 'PRIOR': True}),
                dict(action='FUSION', candidate_ok={'IMAGE': False, 'PRIOR': False, 'FUSION': None})]
        m = decision_accounting(rows)
        self.assertEqual(m['false_accept_units'], 0)
        self.assertEqual(m['evaluated_accepted_units'], 1)
        self.assertEqual(m['accepted_evaluation_unknown_units'], 1)

    def test_point_to_point_and_vertical_gap_differ(self):
        m, a = geometry_metrics([[0, 0, 1]], [[.3, 0, 0]])
        self.assertAlmostEqual(a['prediction_to_reference_m'][0], np.sqrt(1.09))
        self.assertAlmostEqual(a['xy_nearest_signed_dz_m'][0], 1)

    def test_numpy_boolean_false_labels(self):
        m = decision_accounting([dict(action='ABSTAIN', candidate_ok={'IMAGE': np.bool_(False), 'PRIOR': np.bool_(False)})])
        self.assertEqual(m['both_original_candidates_bad_units'], 1)

    def test_neighbor_reference_only_expands_forward_support(self):
        m, _ = geometry_metrics([[.1, 0, 0]], [[2, 0, 0]], forward_reference=[[.1, 0, 0], [2, 0, 0]])
        self.assertEqual(m['prediction_to_reference']['p90_m'], 0)
        self.assertEqual(m['reference_count'], 1)
        self.assertEqual(m['tolerance_sweep'][0]['reference_recall'], 0)


if __name__ == '__main__':
    unittest.main()
