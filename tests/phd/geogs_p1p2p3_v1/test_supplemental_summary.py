"""Synthetic supplemental comparison isolation and matched estimator fixtures."""
import json
import csv
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

MODULES = Path(__file__).resolve().parents[3] / 'scripts/phd/geogs_p1p2p3_v1/evaluation'
sys.path.insert(0, str(MODULES))
import summarize as summary
from runtime_layout import RuntimeLayout, sha
from supplemental_repeat import SupplementalRepeat


class MatchedRepeatTests(unittest.TestCase):
    def geometry(self, condition, value=.4, **changes):
        row = dict(region='P1', candidate=condition+'.final.raw', sensitivity='sample0.1_reference0.1',
                   surface_kind='triangle_surface', threshold_m='.5', status='ASSESSED_DEVELOPMENT_ONLY')
        row.update({metric:value for metric in summary.GEOMETRY_METRICS})
        row.update(changes)
        return row

    def optical(self, condition, name='image.jpg', **changes):
        row = dict(region='P1', condition=condition, name=name, stage='final', domain='full_frame', status='ASSESSED',
                   pixel_count=100, evaluation_index=0, image_id=1, camera_id=1, photo_sha256='p'*64,
                   seed=42, roi_x0=0, roi_y0=0, roi_x1=10, roi_y1=10,
                   psnr_native_db=20., psnr_positive_infinity=False, ssim_native=.9,
                   lpips_vgg_native_01=.2, lpips_vgg_signed_11=.3)
        row.update(changes)
        return row

    def test_repeat_is_not_in_primary_macro_or_input_rows(self):
        rows = [self.geometry('D005_Pnative', .8), self.geometry('changed', .6),
                self.geometry('native_repeat_1', .1, supplemental_only='True')]
        before = json.dumps(rows)
        primary, repeated = summary.partition_geometry(rows, SimpleNamespace(identifier='native_repeat_1'))
        macro = summary.geometry_region_macro(primary, ['P1'])
        self.assertEqual({row['candidate'] for row in macro}, {'D005_Pnative.final.raw', 'changed.final.raw'})
        self.assertEqual(len(repeated), 1)
        self.assertEqual(json.dumps(rows), before)
        with self.assertRaisesRegex(ValueError, 'Undeclared'):
            summary.partition_geometry(rows, SimpleNamespace(identifier=None))

    def test_every_metric_and_surface_sensitivity_is_matched_without_rounding(self):
        primary = [self.geometry('D005_Pnative', .8), self.geometry('D005_Pnative', .7, sensitivity='sample0.2_reference0.1')]
        repeated = [self.geometry('native_repeat_1', .3), self.geometry('native_repeat_1', .2, sensitivity='sample0.2_reference0.1')]
        rows = summary.geometry_repeat_differences(primary, repeated, 'native_repeat_1')
        self.assertEqual(len(rows), 2*len(summary.GEOMETRY_METRICS))
        self.assertTrue(all(abs(row['primary_minus_repeat']-.5)<1e-12 for row in rows))
        for change in ({'surface_kind':'pointset'}, {'threshold_m':'.25'}, {'sensitivity':'different'}):
            with self.subTest(change=change), self.assertRaisesRegex(ValueError, 'match exactly'):
                summary.geometry_repeat_differences(primary[:1], [self.geometry('native_repeat_1', **change)], 'native_repeat_1')

    def test_duplicate_or_missing_repeat_estimator_fails_closed(self):
        primary, repeated = [self.geometry('D005_Pnative')], [self.geometry('native_repeat_1')]
        for invalid in ([], repeated+repeated):
            with self.assertRaises(ValueError):
                summary.geometry_repeat_differences(primary, invalid, 'native_repeat_1')

    def test_failure_keeps_directional_undefined_and_infinite_distances(self):
        rows = summary.geometry_repeat_differences([self.geometry('D005_Pnative')],
            [self.geometry('native_repeat_1', None, status='RECONSTRUCTION_FAILURE')], 'native_repeat_1')
        by_metric = {row['metric']:row for row in rows}
        self.assertEqual(by_metric['ref2candidate_median_m']['difference_status'], 'NEGATIVE_INFINITY')
        self.assertTrue(by_metric['ref2candidate_rmse_m']['difference_negative_infinity'])
        self.assertEqual(by_metric['p2ref_p95_m']['repeat_metric_status'], 'UNDEFINED_EMPTY_PREDICTION')
        self.assertEqual(by_metric['f1']['repeat_value'], 0.)
        self.assertAlmostEqual(by_metric['f1']['primary_minus_repeat'], .4)
        json.dumps(rows, allow_nan=False)

    def test_same_image_and_roi_are_required_for_optical_pairs(self):
        primary = [self.optical('D005_Pnative')]
        for change in ({'name':'other.jpg'}, {'image_id':2}, {'roi_x1':9}, {'photo_sha256':'q'*64}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                summary.optical_repeat_differences(primary, [self.optical('native_repeat_1', **change)], 'native_repeat_1')

    def test_missing_metric_and_infinite_psnr_are_not_finite_only_noise_claim(self):
        primary = [self.optical('D005_Pnative'), self.optical('D005_Pnative', 'b.jpg', psnr_native_db=None, psnr_positive_infinity=True)]
        repeated = [self.optical('native_repeat_1', psnr_native_db=19.),
                    self.optical('native_repeat_1', 'b.jpg', psnr_native_db=None, psnr_positive_infinity=True, lpips_vgg_native_01=None)]
        rows = summary.optical_repeat_differences(primary, repeated, 'native_repeat_1')
        means = {row['metric']:row for row in summary.optical_difference_summary(rows)}
        self.assertEqual(means['psnr_native_db']['expected_pairs'], 2)
        self.assertEqual(means['psnr_native_db']['finite_pairs'], 1)
        self.assertIsNone(means['psnr_native_db']['mean_primary_minus_repeat'])
        self.assertEqual(means['psnr_native_db']['finite_pair_mean_primary_minus_repeat'], 1.)
        self.assertEqual(means['psnr_native_db']['undefined_infinity_minus_infinity_pairs'], 1)
        self.assertEqual(means['lpips_vgg_native_01']['unavailable_or_invalid_pair_pairs'], 1)
        json.dumps([rows, means], allow_nan=False)

    def test_anchor_and_final_render_differences_stay_separate(self):
        primary = [self.optical('D005_Pnative', stage=stage) for stage in ('anchor', 'final')]
        repeated = [self.optical('native_repeat_1', stage='anchor'), self.optical('native_repeat_1', psnr_native_db=18.)]
        rows = summary.optical_repeat_differences(primary, repeated, 'native_repeat_1')
        means = [row for row in summary.optical_difference_summary(rows) if row['metric']=='psnr_native_db']
        self.assertEqual({row['stage']:row['mean_primary_minus_repeat'] for row in means}, {'anchor':0., 'final':2.})


class SupplementalResourceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.task = Path(self.temporary.name)
        config = self.save('contracts/execution_v1.json', dict(seed=42,
            conditions=[dict(id='D005_Pnative', lambda_lod_anchor=.05, protection='native')]))
        self.layout_path = self.save('contracts/layout.json', dict(schema='geogs_runtime_layout_v1', revision='allocator_v2',
            scientific_verdict=None, scientific_config_sha256=sha(config), runs_directory='runs_allocator_v2',
            parity_directory='parity_allocator_v2', queue_directory='queue_allocator_v2', allocator='fixed_allocator',
            anchors={'P1':dict(baseline_directory='runs/P1/D005_Pnative',
                checkpoint_directory='runs/P1/D005_Pnative/model/jbgs_complete/iteration_8000')}))
        self.layout = RuntimeLayout(self.task, self.layout_path, ['P1'])
        self.repeat_path = self.save('contracts/repeat.json', dict(schema='GEOGS_SUPPLEMENTAL_NATIVE_REPEAT_v1',
            condition_id='D005_Pnative', start_iteration=8000, iterations=30000, scientific_verdict=None,
            runtime_layout_sha256=self.layout.digest, scientific_config_sha256=sha(config), regions=['P1'], seed=42,
            phases=['train','render','metrics','auxiliary'], allocator='fixed_allocator',
            output_directory='native_repeat_allocator_v2', repeat_id='native_repeat_1',
            lambda_lod_anchor=.05, protection='native', runtime_image_id='synthetic_image',
            anchors={'P1':dict(checkpoint_directory='runs/P1/D005_Pnative/model/jbgs_complete/iteration_8000')}))
        self.repeat = SupplementalRepeat(self.task, self.repeat_path, self.layout)
        self.files = {}
        run = self.repeat.run('P1')
        for phase in ('train','render','metrics','auxiliary'):
            path = self.save(str((run/(phase+'_receipt.json')).relative_to(self.task)),
                dict(status='PASS', phase=phase, region='P1', condition='D005_Pnative', repeat_id='native_repeat_1',
                     supplemental_only=True, training_start_iteration=8000, wall_seconds=100, child_peak_rss_bytes=1000,
                     runtime_image_id='synthetic_image',
                     **self.layout.binding(), **self.repeat.binding()))
            self.bind(path)
        trace = run/'model/jbgs_trace.jsonl'
        trace.parent.mkdir()
        trace.write_text(json.dumps(dict(iteration=30000, elapsed_seconds=95, peak_cuda_allocated_bytes=100,
            peak_cuda_reserved_bytes=200, peak_rss_bytes=1000, gaussians=10, protected=5))+'\n')
        self.bind(trace)

    def tearDown(self):
        self.temporary.cleanup()

    def save(self, relative, value):
        path = self.task/relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value))
        return path

    def bind(self, path):
        record = dict(path=str(path.relative_to(self.task)), sha256=sha(path))
        self.files[record['path']] = record

    def test_repeat_cost_uses_sealed_repeat_run_and_exact_8000_restore(self):
        rows = summary.resource_records(self.task, 'P1', 'native_repeat_1', self.layout, self.files, self.repeat)
        self.assertEqual(len(rows), 5)
        self.assertTrue(all(row['supplemental_only'] for row in rows))
        self.assertTrue(all(row['cost_category'].startswith('SUPPLEMENTAL_REPEAT_') for row in rows))
        self.assertTrue(all(row['source_path'].startswith('native_repeat_allocator_v2/') for row in rows))
        self.assertEqual(rows[0]['training_start_iteration'], 8000)
        self.assertEqual(rows[-1]['post_anchor_instrumented_interval_seconds'], 95)
        self.assertTrue(all(row['full_pipeline_wall_seconds'] is None for row in rows))

    def test_repeat_resource_does_not_accept_wrong_scientific_condition(self):
        path = self.repeat.run('P1')/'train_receipt.json'
        row = json.loads(path.read_text())
        row['condition'] = 'changed'
        path.write_text(json.dumps(row))
        self.bind(path)
        with self.assertRaisesRegex(ValueError, 'same-condition'):
            summary.resource_records(self.task, 'P1', 'native_repeat_1', self.layout, self.files, self.repeat)

    def test_summary_entrypoint_emits_separate_tables_and_optional_viewer_condition(self):
        # All geometry, pixels and receipts below are synthetic; the orchestration
        # check never mounts or reads any regional/reference payload.
        config_path = self.task/'contracts/execution_v1.json'
        config = json.loads(config_path.read_text())
        config['regions'] = {'P1':dict(domain={'x':[0,1], 'y':[0,1], 'z':[-1,1]})}
        config_path.write_text(json.dumps(config))
        layout_data = json.loads(self.layout_path.read_text())
        layout_data['scientific_config_sha256'] = sha(config_path)
        self.layout_path.write_text(json.dumps(layout_data))
        self.layout = RuntimeLayout(self.task, self.layout_path, ['P1'])
        repeat_data = json.loads(self.repeat_path.read_text())
        repeat_data.update(scientific_config_sha256=sha(config_path), runtime_layout_sha256=self.layout.digest)
        self.repeat_path.write_text(json.dumps(repeat_data))
        self.repeat = SupplementalRepeat(self.task, self.repeat_path, self.layout)
        binding = dict(self.layout.binding(), **self.repeat.binding())
        analysis = self.save('contracts/evaluation_analysis_v1.json', dict(scientific_verdict=None))
        seal = self.save('contracts/candidates_sealed_v1.json', dict(status='ALL_FIXED_CANDIDATES_SEALED',
            config_sha256=sha(config_path), files=[], candidates=[
                dict(region='P1', condition='D005_Pnative', variant='anchor', mesh_kind='raw', anchor_provenance={}),
                dict(region='P1', condition='native_repeat_1', variant='final', mesh_kind='raw',
                     supplemental_only=True, run_directory=str(self.repeat.run('P1').relative_to(self.task)))], **binding))
        self.save('evaluation/geometry/P1/receipt.json', dict(status='PASS_GEOMETRY_EVALUATION',
            candidate_seal_sha256=sha(seal), **binding))
        fixture = MatchedRepeatTests()
        geometry = [fixture.geometry('D005_Pnative', .8), fixture.geometry('native_repeat_1', .3, supplemental_only=True)]
        summary.csv_write(self.task/'evaluation/geometry/P1/geometry_metrics.csv', geometry)
        index = []
        for condition in ('D005_Pnative', 'native_repeat_1'):
            identifier = condition+'.final.raw'
            relative = 'evaluation/geometry/P1/'+identifier+'/'+summary.PRIMARY+'.json'
            metric = self.save(relative, dict(status='ASSESSED_DEVELOPMENT_ONLY', **binding))
            metric.with_suffix('.npz').write_bytes(b'synthetic hash fixture; no geometric coordinates')
            index.append(dict(id=identifier, role='vanilla' if condition=='D005_Pnative' else 'changed',
                metrics_relative=relative, data_url=identifier+'.json', surface_kind='triangle_surface',
                source_path='synthetic/'+identifier, section_url=identifier+'.png', distance_url=identifier+'.distance.png'))
            for stage in ('final','anchor'):
                rows = [dict(fixture.optical(condition, stage=stage, domain=domain), montage='synthetic.png')
                        for domain in ('full_frame','fixed_prism_projected_bbox')]
                self.save(f'evaluation/renders/P1/{condition}/{stage}/receipt.json',
                          dict(status='PASS_RENDER_QUALITY_EVALUATION', rows=rows,
                               sealed_render_manifest_sha256=sha(seal), **binding))
        self.save('evaluation/geometry/P1/viewer_index.json', dict(candidates=index, reference_points=0))
        (self.task/'evaluation/viewer').mkdir(parents=True)
        argv = ['summarize.py','--task',str(self.task),'--analysis-config',str(analysis),
                '--runtime-layout',str(self.layout_path),'--repeat-contract',str(self.repeat_path)]
        with patch.object(sys, 'argv', argv), patch.object(summary, 'relation_rows', return_value=([],[],[])), \
             patch.object(summary, 'anchor_resource_records', return_value=[]), \
             patch.object(summary, 'resource_records', side_effect=lambda task,region,condition,*args:[dict(region=region,condition=condition)]):
            summary.main()
        root = self.task/'evaluation/summary'
        def rows(path):
            with path.open() as stream:
                return list(csv.DictReader(stream))
        self.assertEqual({row['candidate'] for row in rows(root/'geometry_all.csv')}, {'D005_Pnative.final.raw'})
        self.assertEqual({row['condition'] for row in rows(root/'render_summary.csv')}, {'D005_Pnative'})
        self.assertEqual({row['condition'] for row in rows(root/'resource_summary.csv')}, {'D005_Pnative'})
        self.assertEqual({row['condition'] for row in rows(root/'supplemental_repeat/resource_summary.csv')}, {'native_repeat_1'})
        self.assertTrue((root/'supplemental_repeat/geometry_primary_minus_repeat.csv').is_file())
        receipt = json.loads((root/'receipt.json').read_text())
        self.assertEqual(receipt['primary_condition_count'], 1)
        self.assertFalse(receipt['supplemental_in_primary_tables_or_case_ranking'])
        self.assertTrue(any('supplemental_repeat/' in row['path'] for row in receipt['summary_files']))
        manifest = json.loads((self.task/'evaluation/viewer/manifest.json').read_text())
        condition = next(row for row in manifest['regions'][0]['conditions'] if row['id']=='native_repeat_1')
        self.assertIn('Supplemental', condition['label'])
        self.assertFalse(condition['included_in_primary_comparison'])
        self.assertEqual(manifest['regions'][0]['cases'], [])


if __name__ == '__main__':
    unittest.main()
