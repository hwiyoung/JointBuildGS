"""Synthetic-only regression checks for baseline estimands and seal identity."""
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest

import numpy as np

MODULES = Path(__file__).resolve().parents[3] / 'scripts/phd/geogs_p1p2p3_v1/evaluation'
sys.path.insert(0, str(MODULES))
import run_evaluation as evaluation
import seal_candidates as seal


class PointsetBaselineTests(unittest.TestCase):
    def setUp(self):
        self.bounds = {'x': [-23, 7], 'y': [-21, 9], 'z': [-44.272, -25.962]}
        self.cfg = dict(reference_voxel_m=.1, xy_cell_m=.5, thresholds_m=[.1, .5, 1.])
        self.reference = np.array([[-8., -6., -35.], [-7., -6., -35.]])

    def test_point_distances_are_distinct_from_triangle_estimator(self):
        metrics, arrays = evaluation.point_metrics(self.reference + [0, 0, .25], self.reference, self.bounds, self.cfg)
        self.assertIsNone(metrics['reference_to_prediction_triangle'])
        self.assertNotIn('reference_to_triangle_distance', arrays)
        np.testing.assert_allclose(arrays['reference_to_prediction_point_distance'], [.25, .25])
        self.assertEqual(metrics['thresholds'][0]['f1'], 0.)
        self.assertEqual(metrics['thresholds'][1]['f1'], 1.)

    def test_original_point_membership_survives_voxel_sampling(self):
        points = np.vstack([self.reference, [30, 30, -35], self.reference[0] + [.001, 0, 0]])
        _, arrays = evaluation.point_metrics(points, self.reference, self.bounds, self.cfg)
        np.testing.assert_array_equal(points[arrays['prediction_original_indices']], arrays['prediction_surface_samples'])
        self.assertEqual(len(arrays['prediction_surface_samples']), 2)

    def test_distance_table_retains_directional_median_rmse_and_undefined_failure(self):
        metrics, _ = evaluation.point_metrics(self.reference + [0, 0, .25], self.reference, self.bounds, self.cfg)
        fields = evaluation.distance_table_fields(metrics)
        self.assertEqual(len(fields), 8)
        for direction in ('p2ref', 'ref2candidate'):
            self.assertEqual(fields[direction+'_median_m'], .25)
            self.assertEqual(fields[direction+'_rmse_m'], .25)
        failed, _ = evaluation.point_metrics(np.empty((0, 3)), self.reference, self.bounds, self.cfg)
        self.assertTrue(all(value is None for value in evaluation.distance_table_fields(failed).values()))
        self.assertEqual(failed['status'], 'RECONSTRUCTION_FAILURE')

    def test_reference_absence_and_prediction_failure_differ(self):
        absent, _ = evaluation.point_metrics(self.reference, np.empty((0, 3)), self.bounds, self.cfg)
        failed, arrays = evaluation.point_metrics(np.empty((0, 3)), self.reference, self.bounds, self.cfg)
        self.assertEqual(absent['status'], 'NOT_ASSESSED_REFERENCE_ABSENT')
        self.assertTrue(all(row['f1'] is None for row in absent['thresholds']))
        self.assertEqual(failed['status'], 'RECONSTRUCTION_FAILURE')
        self.assertTrue(all(row['f1'] == 0 for row in failed['thresholds']))
        self.assertTrue(np.isinf(arrays['reference_to_prediction_point_distance']).all())

    def test_nonfinite_points_and_invalid_threshold_fail(self):
        with self.assertRaises(ValueError):
            evaluation.point_metrics([[np.nan, 0, 0]], self.reference, self.bounds, self.cfg)
        with self.assertRaises(ValueError):
            evaluation.point_metrics(self.reference, self.reference, self.bounds, dict(self.cfg, thresholds_m=[0]))

    def test_figures_represent_absence_and_failure_without_crashing(self):
        with tempfile.TemporaryDirectory() as tmp:
            for name, pred, ref in [('reference_absent', self.reference, np.empty((0, 3))),
                                    ('prediction_absent', np.empty((0, 3)), self.reference)]:
                _, arrays = evaluation.point_metrics(pred, ref, self.bounds, self.cfg)
                evaluation.distance_figure(Path(tmp)/(name+'.png'), arrays, self.bounds, name)
                evaluation.section_figure(Path(tmp)/(name+'_section.png'), arrays, arrays['reference_points'], self.bounds, 'P1', name)
                self.assertGreater((Path(tmp)/(name+'.png')).stat().st_size, 0)


class FarSurfaceAreaReportingTests(unittest.TestCase):
    def setUp(self):
        self.vertices = np.array([[0., 0., 0.], [4., 0., 0.], [0., 2., 0.]])
        self.triangles = np.array([[0, 1, 2]])
        self.reference = np.array([[1., .5, 0.]])
        self.bounds = {'x':[-1., 5.], 'y':[-1., 3.], 'z':[-1., 1.]}
        self.thresholds = [.1, .2, .25, .5, 1., 2.]
        self.field = 'far_from_observed_reference_area_estimate_m2'

    def evaluate(self, vertices=None, triangles=None, reference=None):
        return evaluation.evaluate_geometry(self.vertices if vertices is None else vertices,
            self.triangles if triangles is None else triangles,
            self.reference if reference is None else reference, self.bounds,
            thresholds=self.thresholds)

    def test_report_uses_existing_area_samples_at_every_frozen_threshold(self):
        metrics, arrays = self.evaluate()
        self.assertEqual(metrics['surface_area_m2'], 4.)
        for threshold in metrics['thresholds']:
            row = evaluation.far_surface_area_fields(metrics, threshold)
            expected = 4. * np.mean(arrays['prediction_to_reference_distance'] >= threshold['threshold_m'])
            self.assertAlmostEqual(row[self.field], expected)
            self.assertEqual(row['far_area_estimate_status'], 'AREA_SAMPLING_ESTIMATE')
            self.assertIn('not confirmed wrong residual structure area', row['far_area_estimate_interpretation'])
            json.dumps(row, allow_nan=False)

    def test_empty_surface_has_zero_area_but_stays_reconstruction_failure(self):
        metrics, _ = self.evaluate(vertices=np.empty((0, 3)), triangles=np.empty((0, 3), dtype=int))
        self.assertEqual(metrics['status'], 'RECONSTRUCTION_FAILURE')
        for threshold in metrics['thresholds']:
            row = evaluation.far_surface_area_fields(metrics, threshold)
            self.assertEqual(row[self.field], 0.)
            self.assertEqual(row['far_area_estimate_status'], 'EMPTY_SURFACE_ZERO_AREA')
            self.assertEqual(threshold['f1'], 0.)

    def test_reference_absence_stays_null_for_nonempty_and_empty_surfaces(self):
        for vertices, triangles in [(self.vertices, self.triangles),
                                     (np.empty((0, 3)), np.empty((0, 3), dtype=int))]:
            metrics, _ = self.evaluate(vertices, triangles, np.empty((0, 3)))
            for threshold in metrics['thresholds']:
                row = evaluation.far_surface_area_fields(metrics, threshold)
                self.assertIsNone(row[self.field])
                self.assertEqual(row['far_area_estimate_status'], 'NOT_ASSESSED_REFERENCE_ABSENT')

    def test_pointset_precision_cannot_be_reinterpreted_as_surface_area(self):
        metrics, _ = evaluation.point_metrics(self.reference, self.reference, self.bounds,
            dict(reference_voxel_m=.1, xy_cell_m=.5, thresholds_m=self.thresholds))
        for threshold in metrics['thresholds']:
            row = evaluation.far_surface_area_fields(metrics, threshold)
            self.assertIsNone(row[self.field])
            self.assertEqual(row['far_area_estimate_status'], 'NOT_APPLICABLE_POINTSET')


class CandidateSealIdentityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.task = Path(self.temp.name)
        self.root = self.task / 'inputs/P1'
        self.root.mkdir(parents=True)
        self.config_sha = 'a'*64
        self.bound = {}
        split = dict(region='P1', train=[], evaluation=[dict(name='photo.png', sha256='placeholder')])
        for name, content in [('scene/images/photo.png', b'fixture photo bytes'),
                              ('scene/sparse/0/cameras.bin', b'fixture camera bytes'),
                              ('scene/sparse/0/images.bin', b'fixture pose bytes'),
                              ('surface/als_surface.ply', b'fixture surface bytes')]:
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
        split['evaluation'][0]['sha256'] = seal.sha(self.root/'scene/images/photo.png')
        (self.root/'scene/split_manifest_da3_v2.json').write_text(json.dumps(split))
        files = [dict(path=str(path.relative_to(self.root)), sha256=seal.sha(path)) for path in self.root.rglob('*') if path.is_file()]
        self.manifest = dict(status='INPUTS_SEALED_FOR_EXECUTION', region='P1', config_sha256=self.config_sha,
                             split_path='scene/split_manifest_da3_v2.json',
                             split_sha256=seal.sha(self.root/'scene/split_manifest_da3_v2.json'), files=files)
        (self.root/'input_manifest.json').write_text(json.dumps(self.manifest))

    def tearDown(self):
        self.temp.cleanup()

    def bind(self, path):
        record = dict(path=str(path.relative_to(self.task)), sha256=seal.sha(path))
        self.bound[record['path']] = record
        return record

    def test_calibration_split_photo_and_prior_are_bound(self):
        _, manifest_sha = seal.bind_evaluation_inputs(self.task, 'P1', self.config_sha, self.bind)
        self.assertEqual(manifest_sha, seal.sha(self.root/'input_manifest.json'))
        for path in ('scene/sparse/0/cameras.bin', 'scene/sparse/0/images.bin', 'scene/split_manifest_da3_v2.json',
                     'scene/images/photo.png', 'surface/als_surface.ply'):
            self.assertIn('inputs/P1/'+path, self.bound)

    def test_camera_or_split_drift_rejected_after_training(self):
        for relative in ('scene/sparse/0/cameras.bin', 'scene/split_manifest_da3_v2.json'):
            path = self.root/relative
            original = path.read_bytes()
            path.write_bytes(original+b'changed')
            with self.assertRaisesRegex(ValueError, 'changed after pre-training seal'):
                seal.bind_evaluation_inputs(self.task, 'P1', self.config_sha, self.bind)
            path.write_bytes(original)

    def test_wrong_phase_or_input_manifest_receipt_is_rejected(self):
        receipt = dict(status='PASS', region='P1', condition='D005_Pnative', phase='render',
                       config_sha256=self.config_sha, input_manifest_sha256='b'*64)
        seal.validate_phase_receipt(receipt, 'P1', 'D005_Pnative', 'render', self.config_sha, 'b'*64)
        for key, bad in [('phase', 'train'), ('region', 'P2'), ('condition', 'D0_Pnative'),
                         ('input_manifest_sha256', 'c'*64)]:
            with self.assertRaises(ValueError):
                seal.validate_phase_receipt(dict(receipt, **{key: bad}), 'P1', 'D005_Pnative', 'render', self.config_sha, 'b'*64)


class ProducerArtifactSealTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.run = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def bind(self, path):
        return dict(path=str(path.relative_to(self.run)), bytes=path.stat().st_size, sha256=seal.sha(path))

    def produce(self, phase, names):
        rows = []
        for index, name in enumerate(names):
            path = self.run/name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(('synthetic artifact '+str(index)).encode())
            rows.append(dict(path=name, exists_nonempty=True, bytes=path.stat().st_size, sha256=seal.sha(path)))
        return dict(phase=phase, validation=rows)

    def test_final_raw_and_post_mesh_replacement_rejected_even_at_same_size(self):
        names = ['model/train/ours_30000/fuse.ply', 'model/train/ours_30000/fuse_post.ply']
        receipt = self.produce('render', names)
        self.assertEqual(set(seal.bind_phase_outputs(self.run, receipt, self.bind)), set(names))
        for name in names:
            path = self.run/name
            original = path.read_bytes()
            path.write_bytes(b'X'*len(original))
            with self.subTest(path=name), self.assertRaisesRegex(ValueError, 'producer hash'):
                seal.bind_phase_outputs(self.run, receipt, self.bind)
            path.write_bytes(original)

    def test_missing_duplicate_and_wrong_size_producer_records_rejected(self):
        name = 'model/train/ours_30000/fuse.ply'
        receipt = self.produce('render', [name])
        row = receipt['validation'][0]
        for rows in ([], [row, row], [dict(row, bytes=row['bytes']+1)]):
            with self.subTest(rows=rows), self.assertRaises(ValueError):
                seal.bind_produced_file(self.run, name, dict(validation=rows), self.bind)

    def train_fixture(self):
        prefix = 'model/jbgs_complete/iteration_30000/'
        names = [prefix+'checkpoint.pth', prefix+'point_cloud.ply',
                 'model/point_cloud/iteration_30000/point_cloud.ply']
        receipt = self.produce('train', names)
        state = dict(iteration=30000, after_protection_registration=True,
                     checkpoint_sha256=receipt['validation'][0]['sha256'],
                     ply_sha256=receipt['validation'][1]['sha256'])
        (self.run/prefix/'receipt.json').write_text(json.dumps(state))
        return receipt, state, prefix

    def test_complete_checkpoint_and_ply_bind_to_train_and_state_receipts(self):
        train, state, prefix = self.train_fixture()
        produced = seal.bind_phase_outputs(self.run, train, self.bind)
        result = seal.bind_final_complete_state(self.run, produced, self.bind)
        self.assertEqual(result['checkpoint']['sha256'], state['checkpoint_sha256'])
        for key in ('checkpoint_sha256', 'ply_sha256'):
            (self.run/prefix/'receipt.json').write_text(json.dumps(dict(state, **{key:'f'*64})))
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, 'train producer or state receipt'):
                seal.bind_final_complete_state(self.run, produced, self.bind)

    def test_final_checkpoint_replacement_cannot_be_admitted_by_state_receipt_alone(self):
        train, state, prefix = self.train_fixture()
        checkpoint = self.run/prefix/'checkpoint.pth'
        checkpoint.write_bytes(b'X'*checkpoint.stat().st_size)
        (self.run/prefix/'receipt.json').write_text(json.dumps(dict(state, checkpoint_sha256=seal.sha(checkpoint))))
        with self.assertRaisesRegex(ValueError, 'producer hash'):
            seal.bind_phase_outputs(self.run, train, self.bind)


if __name__ == '__main__':
    unittest.main()
