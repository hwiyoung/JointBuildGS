"""Synthetic-only aggregate weighting, failure visibility and case checks."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
import sys

import numpy as np

MODULE = Path(__file__).resolve().parents[3] / 'scripts/phd/geogs_p1p2p3_v1/evaluation/summarize.py'
sys.path.insert(0, str(MODULE.parent))
spec = importlib.util.spec_from_file_location('geogs_summarize', MODULE)
summary = importlib.util.module_from_spec(spec)
spec.loader.exec_module(summary)


class NumericFailureTests(unittest.TestCase):
    def test_infinite_failure_is_not_dropped_from_mean(self):
        result = summary.numeric_summary([.1, float('inf'), None])
        self.assertIsNone(result['mean'])
        self.assertEqual(result['status'], 'POSITIVE_INFINITY')
        self.assertEqual(result['finite_count'], 1)
        self.assertEqual(result['positive_infinity_count'], 1)
        self.assertEqual(result['missing_count'], 1)
        json.dumps(result, allow_nan=False)

    def test_invalid_nan_is_distinct_from_unavailable_reference(self):
        self.assertEqual(summary.numeric_summary([float('nan')])['status'], 'INVALID_NUMERIC_VALUES')
        self.assertEqual(summary.numeric_summary([])['status'], 'UNAVAILABLE')
        self.assertEqual(summary.numeric_summary([None])['missing_count'], 1)

    def test_weighted_mean_and_missing_denominator(self):
        result = summary.numeric_summary([.1, .9, None], [3, 1, 0])
        self.assertAlmostEqual(result['mean'], .3)
        self.assertEqual(result['status'], 'PARTIAL_MISSING_VALUES')
        self.assertIsNone(summary.numeric_summary([.1, float('inf')], [3, 1])['mean'])


class AggregateWeightingTests(unittest.TestCase):
    def optical(self, region, name, psnr, lpips=.2, status='ASSESSED', infinity=False):
        return dict(region=region, name=name, condition='condition', stage='final', domain='full_frame',
                    status=status, pixel_count=100, psnr_native_db=psnr, psnr_positive_infinity=infinity,
                    ssim_native=.9, lpips_vgg_native_01=lpips, lpips_vgg_signed_11=lpips)

    def test_image_weighted_and_equal_region_are_distinct(self):
        rows = [self.optical('P1', 'a', 10)] + [self.optical('P2', str(i), 30) for i in range(3)]
        pooled, macro = summary.optical_pooled(rows, ['P1', 'P2'])
        self.assertEqual(pooled[0]['psnr_native_db'], 25.)
        self.assertEqual(macro[0]['psnr_native_db'], 20.)
        self.assertFalse(macro[0]['independent_inference'])

    def test_metric_specific_missing_and_failed_images_remain_counted(self):
        rows = [self.optical('P1', 'a', 10, lpips=None), self.optical('P2', 'b', 20),
                self.optical('P2', 'c', None, status='RENDER_MISSING')]
        pooled, macro = summary.optical_pooled(rows, ['P1', 'P2', 'P3'])
        self.assertEqual(pooled[0]['expected_images'], 3)
        self.assertEqual(pooled[0]['failed_images'], 1)
        self.assertEqual(pooled[0]['lpips_vgg_native_01_finite_count'], 1)
        self.assertEqual(pooled[0]['lpips_vgg_native_01_missing_count'], 2)
        self.assertEqual(macro[0]['psnr_native_db_missing_count_regions'], 1)
        self.assertEqual(macro[0]['present_regions'], 2)

    def test_infinite_psnr_flag_survives_both_aggregations(self):
        rows = [self.optical('P1', 'a', None, infinity=True), self.optical('P2', 'b', 20)]
        pooled, macro = summary.optical_pooled(rows, ['P1', 'P2'])
        self.assertIsNone(pooled[0]['psnr_native_db'])
        self.assertEqual(pooled[0]['psnr_native_db_status'], 'POSITIVE_INFINITY')
        self.assertEqual(macro[0]['psnr_native_db_positive_infinity_count_regions'], 1)
        json.dumps([pooled, macro], allow_nan=False)

    def test_geometry_macro_retains_failure_and_separates_estimands(self):
        def row(region, status, kind, f1):
            return dict(region=region, candidate='candidate', sensitivity='sample0.1_reference0.1',
                        surface_kind=kind, threshold_m='.5', status=status, precision=f1, recall=f1, f1=f1,
                        p2ref_mean_m=.2 if status=='ASSESSED_DEVELOPMENT_ONLY' else None,
                        ref2candidate_mean_m=.2 if status=='ASSESSED_DEVELOPMENT_ONLY' else None)
        rows = [row('P1', 'ASSESSED_DEVELOPMENT_ONLY', 'triangle', .8),
                row('P2', 'RECONSTRUCTION_FAILURE', 'triangle', None),
                row('P1', 'ASSESSED_DEVELOPMENT_ONLY', 'pointset', .5)]
        values = summary.geometry_region_macro(rows, ['P1', 'P2', 'P3'])
        self.assertEqual(len(values), 2)
        triangle = next(row for row in values if row['surface_kind']=='triangle')
        self.assertAlmostEqual(triangle['f1_equal_region_mean'], .4)
        self.assertIsNone(triangle['ref2candidate_mean_m_equal_region_mean'])
        self.assertEqual(triangle['ref2candidate_mean_m_status'], 'POSITIVE_INFINITY')
        self.assertEqual(triangle['p2ref_mean_m_status'], 'UNDEFINED_WITH_RECONSTRUCTION_FAILURE')
        self.assertIsNone(triangle['p2ref_mean_m_equal_region_mean'])
        self.assertEqual(triangle['reconstruction_failure_regions'], 1)
        self.assertEqual(triangle['missing_regions'], 1)

    def test_median_rmse_macro_denominators_preserve_failure_and_missing_reference(self):
        rows = []
        for region, status in [('P1', 'ASSESSED_DEVELOPMENT_ONLY'), ('P2', 'RECONSTRUCTION_FAILURE'),
                               ('P3', 'NOT_ASSESSED_REFERENCE_ABSENT')]:
            row = dict(region=region, candidate='candidate', sensitivity='fixed', surface_kind='triangle',
                       threshold_m=.5, status=status)
            for direction in ('p2ref', 'ref2candidate'):
                for statistic in ('median', 'rmse'):
                    row[direction+'_'+statistic+'_m'] = .25 if region=='P1' else None
            rows.append(row)
        result = summary.geometry_region_macro(rows, ['P1', 'P2', 'P3'])[0]
        for statistic in ('median', 'rmse'):
            prefix = 'ref2candidate_'+statistic+'_m'
            self.assertIsNone(result[prefix+'_equal_region_mean'])
            self.assertEqual(result[prefix+'_positive_infinity_count'], 1)
            self.assertEqual(result[prefix+'_missing_count'], 1)
            self.assertEqual(result[prefix+'_finite_count'], 1)
            self.assertEqual(result['p2ref_'+statistic+'_m_status'], 'UNDEFINED_WITH_RECONSTRUCTION_FAILURE')
        json.dumps(result, allow_nan=False)

    def test_far_area_macro_keeps_zero_failure_and_null_reference_distinct(self):
        metric = 'far_from_observed_reference_area_estimate_m2'
        rows = [dict(region=region, candidate='surface', sensitivity='fixed', surface_kind='triangle_surface',
                     threshold_m=.5, status=status, **{metric:value})
                for region, status, value in [('P1', 'ASSESSED_DEVELOPMENT_ONLY', 4.),
                    ('P2', 'RECONSTRUCTION_FAILURE', 0.), ('P3', 'NOT_ASSESSED_REFERENCE_ABSENT', None)]]
        result = summary.geometry_region_macro(rows, ['P1', 'P2', 'P3'])[0]
        self.assertEqual(result[metric+'_equal_region_mean'], 2.)
        self.assertEqual(result[metric+'_finite_count'], 2)
        self.assertEqual(result[metric+'_missing_count'], 1)
        self.assertEqual(result['reconstruction_failure_regions'], 1)
        self.assertEqual(result['reference_absent_regions'], 1)
        self.assertIn('not confirmed wrong residual structure area', result['statistic_note'])


class CellFailureCaseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.task = Path(self.temp.name)
        self.cfg = dict(conditions=[dict(id='D005_Pnative'), dict(id='changed')],
                        regions={'P1': {'domain': {'x': [0, 1], 'y': [0, .5], 'z': [-1, 1]}}})
        self.reference = np.array([[.1, .1, 0], [.2, .1, 0], [.3, .1, 0]])
        for name, distance in [('D005_Pnative.final.raw', .2), ('changed.final.raw', float('inf')),
                               ('prior_mesh', .1), ('als_points', .1), ('mvs_points', .1)]:
            self.write(name, distance)

    def tearDown(self):
        self.temp.cleanup()

    def write(self, name, distance, reference=None):
        root = self.task/'evaluation/geometry/P1'/name
        root.mkdir(parents=True, exist_ok=True)
        np.savez(root/(summary.PRIMARY+'.npz'), reference_original_indices=np.arange(3),
                 reference_points=self.reference if reference is None else reference,
                 prediction_surface_samples=self.reference,
                 reference_to_candidate_distance=np.full(3, distance))

    def test_all_grid_cells_and_reference_absent_case_are_retained(self):
        rows, cases, _ = summary.relation_rows(self.task, 'P1', self.cfg)
        self.assertEqual(len(rows), 4)
        absent = [row for row in rows if row['reference_points']==0]
        self.assertEqual(len(absent), 2)
        self.assertTrue(all(row['reference_to_prior_relation']=='reference_absent' for row in absent))
        self.assertTrue(all('prior_to_reference_relation' not in row for row in rows+cases))
        self.assertTrue(any(row['selection_reason']=='reference_absent_first_fixed_cell' for row in cases))

    def test_failure_stratum_and_case_are_not_finite_mean_improvement(self):
        rows, cases, strata = summary.relation_rows(self.task, 'P1', self.cfg)
        failed = next(row for row in rows if row['condition']=='changed' and row['reference_points'])
        self.assertIsNone(failed['native_minus_changed_m'])
        self.assertEqual(failed['distance_transition'], 'DEGRADED_TO_RECONSTRUCTION_FAILURE')
        self.assertTrue(any(row['distance_transition']=='DEGRADED_TO_RECONSTRUCTION_FAILURE' for row in cases))
        stratum = next(row for row in strata if row['condition']=='changed' and row['reference_points'])
        self.assertEqual(stratum['reference_weighted_changed_status'], 'POSITIVE_INFINITY')
        self.assertIsNone(stratum['reference_weighted_changed_mean_m'])
        json.dumps([rows, cases, strata], allow_nan=False)

    def test_persistent_failure_and_recovery_cases_remain_visible(self):
        self.write('D005_Pnative.final.raw', float('inf'))
        _, cases, _ = summary.relation_rows(self.task, 'P1', self.cfg)
        self.assertTrue(any(row['distance_transition']=='PERSISTENT_RECONSTRUCTION_FAILURE' for row in cases))
        self.write('changed.final.raw', .1)
        _, cases, _ = summary.relation_rows(self.task, 'P1', self.cfg)
        self.assertTrue(any(row['distance_transition']=='RECOVERED_FROM_RECONSTRUCTION_FAILURE' for row in cases))

    def test_reference_coordinate_mismatch_fails_even_when_ids_match(self):
        self.write('prior_mesh', .1, self.reference+[0, 0, .1])
        with self.assertRaises(ValueError):
            summary.relation_rows(self.task, 'P1', self.cfg)

    def test_viewer_cases_use_fixed_midheight_and_keep_failure_cases(self):
        _, cases, _ = summary.relation_rows(self.task, 'P1', self.cfg)
        navigation = summary.viewer_cases(cases, self.cfg['regions']['P1']['domain'])
        self.assertEqual(len(navigation), len(cases))
        self.assertTrue(all(row['center'][2]==0 and row['extent_m']==5 for row in navigation))
        self.assertTrue(all(row['condition_id']=='changed' for row in navigation))
        self.assertEqual(len({row['id'] for row in navigation}), len(navigation))


if __name__ == '__main__':
    unittest.main()
