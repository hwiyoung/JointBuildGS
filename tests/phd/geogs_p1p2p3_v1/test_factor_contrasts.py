"""Synthetic arithmetic, identity, missingness and post-summary access-gate checks."""
import copy
import csv
import json
import math
from pathlib import Path
import sys
import tempfile
import unittest
import shutil
from contextlib import redirect_stdout
import io
from unittest.mock import patch

MODULES = Path(__file__).resolve().parents[3]/'scripts/phd/geogs_p1p2p3_v1/analysis'
sys.path.insert(0, str(MODULES))
import factor_contrasts as fc


def config(count=2):
    return dict(regions={'P1':dict(expected_test=count)}, evaluation=dict(
        surface_sample_spacing_m=.1, reference_voxel_m=.1, sample_sensitivity_m=[],
        reference_voxel_sensitivity_m=[], thresholds_m=[.5]))


def geometry(condition, value=1., kind='raw', **changes):
    row = dict(region='P1', candidate=condition+'.final.'+kind, status='ASSESSED_DEVELOPMENT_ONLY',
        mesh_res='1024', iteration='30000', surface_kind='triangle_surface',
        sensitivity='sample0.1_reference0.1', threshold_m='.5', supplemental_only='False',
        far_area_estimate_status='AREA_SAMPLING_ESTIMATE')
    row.update({metric:str(value) for metric in fc.GEOMETRY_METRICS})
    row.update(changes)
    return row


def optical(condition, value=1., index=0, **changes):
    row = dict(region='P1', condition=condition, status='ASSESSED', stage='final', domain='full_frame',
        name=f'image_{index}.jpg', evaluation_index=str(index), image_id=str(index+10), camera_id='1',
        photo_sha256=str(index)*64, seed='0', roi_x0='0', roi_y0='0', roi_x1='100', roi_y1='100',
        pixel_count='10000', psnr_positive_infinity='False', lpips_status='ASSESSED_NATIVE_RANGE_0_1',
        supplemental_only='False')
    row.update({metric:str(value) for metric in fc.OPTICAL_METRICS})
    row.update(changes)
    return row


def complete_optical(cfg, values=None):
    values = values or {condition:i for i, condition in enumerate(fc.CONDITIONS)}
    return [optical(condition, values[condition], index, domain=domain)
            for domain in fc.DOMAINS for index in range(cfg['regions']['P1']['expected_test'])
            for condition in fc.CONDITIONS]


class ContrastArithmeticTests(unittest.TestCase):
    def test_nine_fixed_contrasts_and_independent_did_algebra(self):
        # Known nonadditive 2x3 table: native 10,7,4; release 9,2,1.
        values = dict(zip(fc.CONDITIONS, (10, 7, 4, 9, 2, 1)))
        source = {condition:geometry(condition, value) for condition, value in values.items()}
        result = {item['id']:fc.make_contrast({}, item, source, 'p2ref_mean_m')
                  for item in fc.mapping()['contrasts']}
        self.assertEqual(len(result), 9)
        self.assertEqual(result['depth_D005_to_D0005_Pnative']['contrast_value'], -3.)
        self.assertEqual(result['depth_D005_to_D0_Prelease']['contrast_value'], -8.)
        self.assertEqual(result['protection_D0005_native_to_release']['contrast_value'], -5.)
        self.assertEqual(result['interaction_D005_to_D0005']['contrast_value'], -4.)
        self.assertEqual(result['interaction_D005_to_D0']['contrast_value'], -2.)
        # DID equals the difference of protection effects as well as depth effects.
        self.assertEqual(result['interaction_D005_to_D0005']['contrast_value'],
                         result['protection_D0005_native_to_release']['contrast_value']-
                         result['protection_D005_native_to_release']['contrast_value'])

    def test_metric_direction_and_no_invented_area_quality(self):
        self.assertEqual(fc.metric_direction('f1'), 'HIGHER')
        self.assertEqual(fc.metric_direction('lpips_vgg_signed_11'), 'LOWER')
        self.assertEqual(fc.metric_direction('surface_area_m2'), 'NO_MONOTONIC_QUALITY_DIRECTION')
        self.assertIn('NOT_CONFIRMED_ERROR_AREA', fc.metric_direction('far_from_observed_reference_area_estimate_m2'))

    def test_extended_real_positive_negative_and_cancellation(self):
        finite, infinite = fc.number(4), fc.number(math.inf)
        self.assertEqual(fc.linear_contrast([(1, infinite), (-1, finite)])['contrast_status'], 'POSITIVE_INFINITY')
        self.assertEqual(fc.linear_contrast([(1, finite), (-1, infinite)])['contrast_status'], 'NEGATIVE_INFINITY')
        result = fc.linear_contrast([(1, infinite), (-1, infinite)])
        self.assertEqual(result['contrast_status'], 'UNDEFINED_INFINITY_CANCELLATION')
        self.assertIsNone(result['contrast_value'])
        self.assertFalse(result['contrast_positive_infinity'])

    def test_did_cannot_cancel_undefined_infinity(self):
        result = fc.linear_contrast([(1, fc.number(math.inf)), (-1, fc.number(math.inf)),
                                     (-1, fc.number(2)), (1, fc.number(3))])
        self.assertIsNone(result['contrast_value'])
        self.assertEqual(result['contrast_status'], 'UNDEFINED_INFINITY_CANCELLATION')

    def test_missing_and_invalid_dominate_infinite_operand(self):
        for value in (None, '', 'nan', 'bad'):
            with self.subTest(value=value):
                result = fc.linear_contrast([(1, fc.number(value)), (-1, fc.number(math.inf))])
                self.assertEqual(result['contrast_status'], 'UNAVAILABLE_OR_INVALID_OPERAND')
                self.assertIsNone(result['contrast_value'])
                json.dumps(result, allow_nan=False)

    def test_empty_prediction_preserves_existing_zero_and_distance_semantics(self):
        row = geometry('D005_Pnative', 0, status='RECONSTRUCTION_FAILURE')
        for metric in fc.GEOMETRY_METRICS:
            if metric.startswith(('p2ref_', 'ref2candidate_')):
                row[metric] = ''
        self.assertEqual(fc.metric_value(row, 'f1')['value'], 0.)
        self.assertEqual(fc.metric_value(row, 'p2ref_mean_m')['status'], 'UNDEFINED_EMPTY_PREDICTION')
        self.assertTrue(fc.metric_value(row, 'ref2candidate_mean_m')['positive_infinity'])
        self.assertEqual(fc.metric_value(row, 'surface_area_m2')['value'], 0.)
        row['f1'] = ''
        with self.assertRaisesRegex(ValueError, 'zero is absent'):
            fc.metric_value(row, 'f1')

    def test_reference_absence_is_not_failure_but_area_is_descriptive(self):
        row = geometry('D005_Pnative', 12, status='NOT_ASSESSED_REFERENCE_ABSENT')
        for metric in fc.GEOMETRY_METRICS:
            if metric != 'surface_area_m2':
                row[metric] = ''
        self.assertEqual(fc.metric_value(row, 'f1')['status'], 'NOT_ASSESSED_REFERENCE_ABSENT')
        self.assertEqual(fc.metric_value(row, 'surface_area_m2')['value'], 12.)
        row['f1'] = '0'
        with self.assertRaisesRegex(ValueError, 'Reference-absent'):
            fc.metric_value(row, 'f1')

    def test_false_csv_psnr_flag_is_not_true_and_lpips_na_is_preserved(self):
        row = optical('D005_Pnative', 20)
        self.assertEqual(fc.metric_value(row, 'psnr_native_db', True)['value'], 20.)
        row.update(psnr_native_db='', psnr_positive_infinity='True', lpips_vgg_signed_11='',
                   lpips_status='NOT_ASSESSED_DOMAIN_SIDE_LT_32')
        self.assertTrue(fc.metric_value(row, 'psnr_native_db', True)['positive_infinity'])
        self.assertEqual(fc.metric_value(row, 'lpips_vgg_signed_11', True)['status'], 'NOT_ASSESSED_DOMAIN_SIDE_LT_32')

    def test_failed_render_cannot_use_leftover_finite_score(self):
        row = optical('D005_Pnative', 22, status='RENDER_MISSING')
        self.assertEqual(fc.metric_value(row, 'psnr_native_db', True)['status'], 'RENDER_MISSING')
        self.assertIsNone(fc.metric_value(row, 'psnr_native_db', True)['value'])

    def test_numeric_overflow_not_fabricated_finite_or_infinity(self):
        result = fc.linear_contrast([(1, fc.number(1e308)), (1, fc.number(1e308))])
        self.assertEqual(result['contrast_status'], 'INVALID_FINITE_ARITHMETIC_OVERFLOW')


class MembershipTests(unittest.TestCase):
    def test_geometry_exact_full_grid_missing_rows_and_no_mutation(self):
        cfg = config()
        cfg['evaluation']['sample_sensitivity_m'] = [.05, .2]
        cfg['evaluation']['reference_voxel_sensitivity_m'] = [.05, .2]
        cfg['evaluation']['thresholds_m'] = [.1, .5]
        rows = [geometry(condition) for condition in fc.CONDITIONS]
        before = copy.deepcopy(rows)
        result, inventory = fc.geometry_contrasts(rows, cfg)
        self.assertEqual(len(result), 2*5*2*9*13)
        self.assertEqual(inventory['present_condition_rows'], 6)
        self.assertEqual(inventory['expected_condition_rows'], 2*5*2*6)
        missing = next(row for row in result if row['mesh_kind']=='post')
        self.assertEqual(missing['contrast_status'], 'UNAVAILABLE_OR_INVALID_OPERAND')
        self.assertIn('MISSING_ROW', missing['operands_json'])
        self.assertEqual(rows, before)

    def test_duplicate_wrong_estimator_and_repeat_are_rejected(self):
        row = geometry('D005_Pnative')
        for rows, text in (([row, row], 'Duplicate'),
                           ([dict(row, surface_kind='ORIGINAL_POINTSET_NN_BASELINE')], 'estimator'),
                           ([dict(row, candidate='native_repeat_1.final.raw')], 'Unexpected'),
                           ([dict(row, supplemental_only='True')], 'Supplemental')):
            with self.subTest(text=text), self.assertRaisesRegex(ValueError, text):
                fc.geometry_contrasts(rows, config())

    def test_optical_expected_indices_do_not_shrink_if_every_row_is_missing(self):
        rows, inventory = fc.optical_contrasts([], config(3))
        self.assertEqual(len(rows), 3*2*9*4)
        self.assertEqual(inventory['expected_condition_rows'], 3*2*6)
        means = fc.optical_means(rows, config(3))
        self.assertTrue(all(row['expected_image_pairs'] == 3 and row['finite_image_pairs'] == 0
                            and row['mean_contrast_value'] is None for row in means))

    def test_optical_identity_mismatch_not_numerical_difference(self):
        source = {condition:optical(condition) for condition in fc.CONDITIONS}
        source['D0005_Pnative']['photo_sha256'] = 'x'*64
        result = fc.make_contrast({}, fc.mapping()['contrasts'][0], source, 'ssim_native', True)
        self.assertEqual(result['contrast_status'], 'PAIR_IDENTITY_MISMATCH')
        self.assertIsNone(result['contrast_value'])
        self.assertIn('photo_sha256', result['mismatched_identity_fields_json'])
        self.assertIn('x'*64, result['camera_identity_by_condition_json'])

    def test_duplicate_image_names_and_duplicate_indices_fail(self):
        rows = [optical('D005_Pnative', index=i) for i in range(2)]
        rows[1]['name'] = rows[0]['name']
        with self.assertRaisesRegex(ValueError, 'Duplicate or empty optical image name'):
            fc.optical_contrasts(rows, config())
        with self.assertRaisesRegex(ValueError, 'Duplicate optical metric identity'):
            fc.optical_contrasts([rows[0], rows[0]], config())

    def test_all_finite_equal_image_means_and_no_survivor_aggregate(self):
        cfg = config()
        rows = complete_optical(cfg)
        contrasts, _ = fc.optical_contrasts(rows, cfg)
        means = fc.optical_means(contrasts, cfg)
        self.assertEqual(len(means), 2*9*4)
        self.assertTrue(all(row['finite_image_pairs'] == 2 and row['mean_contrast_value'] is not None for row in means))
        for row in rows:
            if row['condition'] == 'D0005_Pnative' and row['domain'] == 'full_frame' and row['evaluation_index'] == '1':
                row.update(status='RENDER_MISSING')
        changed, _ = fc.optical_contrasts(rows, cfg)
        result = next(row for row in fc.optical_means(changed, cfg) if row['contrast_id']=='depth_D005_to_D0005_Pnative'
                      and row['domain']=='full_frame' and row['metric']=='ssim_native')
        self.assertEqual(result['finite_image_pairs'], 1)
        self.assertIsNone(result['mean_contrast_value'])
        self.assertNotIn('finite_pair_mean', result)

    def test_one_infinite_image_prevents_finite_regional_mean(self):
        cfg = config()
        rows = complete_optical(cfg)
        rows[1].update(psnr_native_db='', psnr_positive_infinity='True')
        contrasts, _ = fc.optical_contrasts(rows, cfg)
        result = next(row for row in fc.optical_means(contrasts, cfg)
                      if row['contrast_id']=='depth_D005_to_D0005_Pnative' and row['domain']=='full_frame' and row['metric']=='psnr_native_db')
        self.assertEqual(result['finite_image_pairs'], 1)
        self.assertIsNone(result['mean_contrast_value'])
        self.assertIn('POSITIVE_INFINITY', result['contrast_status_counts_json'])

    def test_csv_output_strict_json_fields_and_input_width_validation(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'rows.csv'
            result, _ = fc.optical_contrasts([], config(1))
            fc.csv_write(path, result)
            read = fc.load_csv(path, ('contrast_status', 'operands_json'))
            self.assertEqual(len(read), len(result))
            self.assertIsNone(json.loads(read[0]['operands_json'])[0]['value'])
            path.write_text('a,b\n1\n')
            with self.assertRaisesRegex(ValueError, 'Malformed CSV'):
                fc.load_csv(path, ('a', 'b'))


class InputGateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.task = Path(self.temp.name)
        (self.task/'contracts').mkdir()
        summary = self.task/'evaluation/summary'
        summary.mkdir(parents=True)
        for name in ('execution_v1.json', 'evaluation_analysis_v1.json', 'runtime_layout_allocator_v2.json',
                     'supplemental_repeat_v1.json', 'extraction_resource_v3.json'):
            (self.task/'contracts'/name).write_text('{}')
        self.seal = dict(schema='JBGS_GEOGS_CANDIDATES_SEALED_v2',
            status='ALL_REQUIRED_CANDIDATES_SEALED_OPTIONAL_ACCOUNTED', scientific_verdict=None,
            reference_accessed=False, config_sha256=fc.sha(self.task/'contracts/execution_v1.json'),
            runtime_layout_sha256='layout', repeat_contract_sha256='repeat', resource_contract_sha256='resource')
        fc.dump(self.task/'contracts/candidates_sealed_v1.json', self.seal)
        files = []
        for name in ('geometry_primary_1024.csv', 'render_all_images.csv'):
            path = summary/name
            path.write_text('synthetic\n1\n')
            files.append(fc.file_record(self.task, path))
        self.receipt = dict(regions=['P1', 'P2', 'P3'], primary_condition_count=6,
                           supplemental_in_primary_tables_or_case_ranking=False, summary_files=files)
        fc.dump(summary/'receipt.json', self.receipt)

    def factory(self, task):
        outer = self
        class Gate:
            def candidate_seal(self):
                return outer.seal, fc.sha(task/'contracts/candidates_sealed_v1.json')
            def bound_receipt(self, path, status, seal_sha, **identity):
                outer.assertEqual(status, 'TABLES_AND_ACTUAL_VIEWER_DATA_READY')
                outer.assertEqual(seal_sha, fc.sha(task/'contracts/candidates_sealed_v1.json'))
                return outer.receipt
        return Gate()

    def test_complete_gate_records_exact_csv_hashes_without_scoring(self):
        value = fc.input_gate(self.task, self.factory)
        self.assertEqual(len(value['summary_csv_files']), 2)
        self.assertEqual(len(value['contract_files']), 6)
        self.assertEqual(value['summary_csv_files']['render_all_images.csv']['sha256'],
                         fc.sha(self.task/'evaluation/summary/render_all_images.csv'))

    def test_incomplete_all21_seal_rejected_before_summary_read(self):
        self.seal['status'] = 'INCOMPLETE'
        (self.task/'evaluation/summary/receipt.json').unlink()
        with self.assertRaisesRegex(ValueError, 'complete resource-v3 seal'):
            fc.input_gate(self.task, self.factory)

    def test_changed_csv_or_missing_inventory_rejected(self):
        (self.task/'evaluation/summary/render_all_images.csv').write_text('changed')
        with self.assertRaisesRegex(ValueError, 'bytes changed'):
            fc.input_gate(self.task, self.factory)
        self.receipt['summary_files'] = self.receipt['summary_files'][:1]
        with self.assertRaisesRegex(ValueError, 'not bound'):
            fc.input_gate(self.task, self.factory)

    def test_primary_repeat_contamination_rejected(self):
        self.receipt['supplemental_in_primary_tables_or_case_ranking'] = True
        with self.assertRaisesRegex(ValueError, 'membership differs'):
            fc.input_gate(self.task, self.factory)


class ExistingEvaluatorCSVCompatibilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Actual project evaluator modules, synthetic arrays/photos only; no model/cache mount.
        sys.path.insert(0, str(MODULES.parent/'evaluation'))
        import run_evaluation
        import render_quality
        import summarize
        import numpy
        from PIL import Image
        cls.evaluation, cls.quality, cls.summary = run_evaluation, render_quality, summarize
        cls.np, cls.Image = numpy, Image

    def test_actual_geometry_evaluator_fields_csv_and_empty_surface_semantics(self):
        np = self.np
        vertices = np.array([[0., 0., 0.], [1., 0., 0.], [0., 1., 0.]])
        triangles = np.array([[0, 1, 2]])
        reference = np.array([[.2, .2, .1]])
        bounds = dict(x=[-1, 2], y=[-1, 2], z=[-1, 1])
        for case in ('assessed', 'empty_prediction', 'reference_absent'):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as tmp:
                metrics, arrays = self.evaluation.evaluate_geometry(
                    np.empty((0, 3)) if case=='empty_prediction' else vertices,
                    np.empty((0, 3), dtype=int) if case=='empty_prediction' else triangles,
                    np.empty((0, 3)) if case=='reference_absent' else reference, bounds, thresholds=[.5])
                threshold = metrics['thresholds'][0]
                # These are the evaluator's actual reporting functions and writer, not copied formulas.
                row = geometry('D005_Pnative', status=metrics['status'],
                    surface_area_m2=metrics['surface_area_m2'], **threshold,
                    **self.evaluation.distance_table_fields(metrics),
                    **self.evaluation.far_surface_area_fields(metrics, threshold))
                path = Path(tmp)/'geometry.csv'
                self.evaluation.write_csv(path, [row])
                loaded = fc.load_csv(path, fc.GEOMETRY_METRICS)
                result, _ = fc.geometry_contrasts(loaded, config())
                self.assertTrue(result)
                actual = loaded[0]
                if case == 'empty_prediction':
                    self.assertTrue(np.isinf(arrays['reference_to_triangle_distance']).all())
                    self.assertEqual(actual['ref2candidate_mean_m'], '')
                    self.assertTrue(fc.metric_value(actual, 'ref2candidate_mean_m')['positive_infinity'])
                    self.assertEqual(fc.metric_value(actual, 'f1')['value'], 0.)
                elif case == 'reference_absent':
                    self.assertEqual(fc.metric_value(actual, 'f1')['status'], 'NOT_ASSESSED_REFERENCE_ABSENT')
                else:
                    self.assertAlmostEqual(fc.metric_value(actual, 'ref2candidate_mean_m')['value'], .1, places=6)

    def test_actual_render_evaluation_writer_then_summary_writer_round_trip(self):
        np = self.np
        class Scorer:
            metadata = dict(synthetic_fixture_only=True)
            def score(self, photo, render):
                return dict(psnr_native_db=20., psnr_positive_infinity=False, ssim_native=.8,
                            lpips_vgg_native_01=None, lpips_vgg_signed_11=None,
                            lpips_status='SYNTHETIC_FIXTURE_NO_MODEL')
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            photos = root/'photos'
            photos.mkdir()
            self.Image.fromarray(np.full((40, 48, 3), 255, dtype=np.uint8)).save(photos/'photo.png')
            self.Image.fromarray(np.zeros((40, 48, 3), dtype=np.uint8)).save(root/'render.png')
            view = dict(name='photo.png', image_id=91, camera_id=2, width=48, height=40,
                sha256=self.quality.sha(photos/'photo.png'), R=np.eye(3).tolist(), t=[0, 0, 0],
                K=[[10, 0, 24], [0, 10, 20], [0, 0, 1]])
            record = dict(name='photo.png', evaluation_index=0, image_id=91, camera_id=2,
                render_path=str(root/'render.png'), render_sha256=self.quality.sha(root/'render.png'))
            rows = []
            for condition in fc.CONDITIONS:
                # One true missing-render condition exercises existing failure CSV semantics.
                output = root/condition
                self.quality.evaluate_render_set(dict(train=[], evaluation=[view]),
                    [] if condition=='D0_Prelease' else [record], [[-1, 1], [-1, 1], [2, 4]],
                    photos, Scorer(), output, 'P1', condition, 'final', 0, 'a'*64)
                rows.extend(fc.load_csv(output/'per_image_metrics.csv', ('condition', 'status', *fc.OPTICAL_METRICS)))
            summary_path = root/'render_all_images.csv'
            self.summary.csv_write(summary_path, rows)
            loaded = fc.load_csv(summary_path, ('region', 'condition', 'stage', 'domain', *fc.CAMERA_FIELDS))
            contrasts, inventory = fc.optical_contrasts(loaded, config(1))
            self.assertEqual(inventory['present_condition_rows'], 12)
            finite = next(row for row in contrasts if row['contrast_id']=='depth_D005_to_D0005_Pnative'
                          and row['domain']=='full_frame' and row['metric']=='ssim_native')
            self.assertEqual(finite['contrast_value'], 0.)
            missing = next(row for row in contrasts if row['contrast_id']=='protection_D0_native_to_release'
                           and row['domain']=='full_frame' and row['metric']=='psnr_native_db')
            self.assertEqual(missing['contrast_status'], 'UNAVAILABLE_OR_INVALID_OPERAND')
            self.assertIn('RENDER_MISSING', missing['operands_json'])
            small = next(row for row in contrasts if row['contrast_id']=='depth_D005_to_D0005_Pnative'
                         and row['metric']=='lpips_vgg_signed_11')
            self.assertIn('SYNTHETIC_FIXTURE_NO_MODEL', small['operands_json'])


class ActualAll21GateTests(unittest.TestCase):
    def setUp(self):
        base = MODULES.parent
        for directory in (base, base/'evaluation', base/'runtime'):
            sys.path.insert(0, str(directory))
        from finalization_control import FinalizationGate
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.task = Path(self.temp.name)
        contracts = self.task/'contracts'
        contracts.mkdir()
        config_root = Path(__file__).resolve().parents[3]/'configs/phd/geogs_p1p2p3_v1'
        for name in ('experiment_v1.json', 'evaluation_analysis_v1.json', 'runtime_layout_allocator_v2.json',
                     'supplemental_repeat_v1.json', 'extraction_resource_v3.json'):
            shutil.copyfile(config_root/name, contracts/('execution_v1.json' if name=='experiment_v1.json' else name))
        gate = FinalizationGate(self.task)
        binding = dict(config_sha256=fc.sha(contracts/'execution_v1.json'), **gate.layout.binding(),
                       **gate.repeat.binding(), **gate.resource.binding())
        self.seal = dict(schema='JBGS_GEOGS_CANDIDATES_SEALED_v2',
            status='ALL_REQUIRED_CANDIDATES_SEALED_OPTIONAL_ACCOUNTED', reference_accessed=False,
            scientific_verdict=None, **binding, candidates=[], extraction_inventory=[])
        for region in gate.cfg['regions']:
            for condition in [*fc.CONDITIONS, gate.repeat.identifier]:
                repeated = condition == gate.repeat.identifier
                for variant in gate.resource.variant_inventory(region, 'D005_Pnative' if repeated else condition,
                                                              gate.repeat.identifier if repeated else None):
                    self.seal['extraction_inventory'].append(dict(region=region, condition=condition,
                        variant=variant['name'], **{key:variant[key] for key in ('iteration', 'mesh_res', 'required', 'export_images')},
                        status='PASS' if variant['required'] else 'TECHNICAL_RESOURCE_UNAVAILABLE'))
                variants = ['final', 'mesh_512'] + (['anchor_512'] if condition=='D005_Pnative' else [])
                for variant in variants:
                    for kind in ('raw', 'post'):
                        self.seal['candidates'].append(dict(region=region, condition=condition, variant=variant,
                            mesh_kind=kind, supplemental_only=repeated,
                            run_directory=str((gate.repeat.run(region) if repeated else gate.layout.run(region, condition)).relative_to(self.task)),
                            anchor_provenance=dict(checkpoint=dict(sha256=gate.repeat.data['anchors'][region].get('checkpoint_sha256')))))
        fc.dump(contracts/'candidates_sealed_v1.json', self.seal)
        summary = self.task/'evaluation/summary'
        summary.mkdir(parents=True)
        files = []
        for name in ('geometry_primary_1024.csv', 'render_all_images.csv'):
            path = summary/name
            path.write_text('synthetic\n1\n')
            files.append(fc.file_record(self.task, path))
        fc.dump(summary/'receipt.json', dict(status='TABLES_AND_ACTUAL_VIEWER_DATA_READY',
            scientific_verdict=None, **binding, analysis_config_sha256=fc.sha(contracts/'evaluation_analysis_v1.json'),
            candidate_seal_sha256=fc.sha(contracts/'candidates_sealed_v1.json'),
            regions=['P1', 'P2', 'P3'], primary_condition_count=6,
            supplemental_in_primary_tables_or_case_ranking=False, summary_files=files))

    def test_real_gate_accepts_full_synthetic_inventory_under_exact_contracts(self):
        self.assertEqual(len(self.seal['extraction_inventory']), 48)
        finals = [row for row in self.seal['candidates'] if row['variant']=='final' and row['mesh_kind']=='raw']
        self.assertEqual(len(finals), 21)
        result = fc.input_gate(self.task)
        self.assertEqual(result['candidate_seal_sha256'], fc.sha(self.task/'contracts/candidates_sealed_v1.json'))

    def test_real_gate_rejects_missing_run_before_opening_absent_summary(self):
        self.seal['candidates'] = [row for row in self.seal['candidates']
                                   if not (row['region']=='P3' and row['condition']=='native_repeat_1')]
        (self.task/'contracts/candidates_sealed_v1.json').write_text(json.dumps(self.seal))
        (self.task/'evaluation/summary/receipt.json').unlink()
        with self.assertRaisesRegex(ValueError, 'Every declared native repetition must be sealed'):
            fc.input_gate(self.task)

    def test_real_gate_rejects_missing_required_post_surface(self):
        self.seal['candidates'] = [row for row in self.seal['candidates'] if not (
            row['region']=='P2' and row['condition']=='D0_Prelease' and row['variant']=='mesh_512' and row['mesh_kind']=='post')]
        (self.task/'contracts/candidates_sealed_v1.json').write_text(json.dumps(self.seal))
        (self.task/'evaluation/summary/receipt.json').unlink()
        with self.assertRaisesRegex(ValueError, 'omits or duplicates'):
            fc.input_gate(self.task)

    def test_main_writes_new_tables_receipt_and_all_declared_missing_rows(self):
        summary = self.task/'evaluation/summary'
        binding = {key:self.seal[key] for key in ('runtime_layout_sha256', 'repeat_contract_sha256')}
        for name, rows in (
                ('geometry_primary_1024.csv', [dict(geometry(condition), **binding) for condition in fc.CONDITIONS]),
                ('render_all_images.csv', [dict(row, **binding) for row in complete_optical(config(1))])):
            (summary/name).unlink()
            fc.csv_write(summary/name, rows)
        receipt_path = summary/'receipt.json'
        receipt = fc.read_json(receipt_path)
        receipt['summary_files'] = [fc.file_record(self.task, summary/name)
                                   for name in ('geometry_primary_1024.csv', 'render_all_images.csv')]
        receipt_path.write_text(json.dumps(receipt))
        summary_before = fc.sha(receipt_path)
        output = self.task/'new_results'
        with patch.object(sys, 'argv', ['factor_contrasts.py', '--task', str(self.task), '--output', str(output)]), redirect_stdout(io.StringIO()):
            fc.main()
        result = fc.read_json(output/'receipt.json')
        self.assertEqual(result['output_rows']['geometry_factor_contrasts.csv'], 3*2*5*6*9*13)
        self.assertEqual(result['output_rows']['render_per_image_factor_contrasts.csv'], (15+9+20)*2*9*4)
        self.assertIsNone(result['scientific_verdict'])
        self.assertFalse(result['reference_payload_read'])
        self.assertEqual(fc.sha(receipt_path), summary_before)
        means = fc.load_csv(output/'render_regional_paired_contrasts.csv', ('expected_image_pairs', 'mean_contrast_value'))
        self.assertTrue(all(row['mean_contrast_value'] == '' for row in means))
        self.assertEqual({int(row['expected_image_pairs']) for row in means}, {15, 9, 20})
        for item in result['files']:
            self.assertEqual(fc.file_record(output, output/item['path']), item)


if __name__ == '__main__':
    unittest.main()
