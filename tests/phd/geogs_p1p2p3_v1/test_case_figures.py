"""Synthetic temporary fixtures; no regional arrays/photos/reference are mounted."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

import numpy as np
from PIL import Image

MODULES = Path(__file__).resolve().parents[3] / 'scripts/phd/geogs_p1p2p3_v1/evaluation'
sys.path.insert(0, str(MODULES))
import case_figures as cases


class CaseProjectionAndPixelsTests(unittest.TestCase):
    def camera(self, name, focal, t=(0, 0, 0)):
        return dict(name=name, R=np.eye(3).tolist(), t=list(t), K=[[focal, 0, 32], [0, focal, 24], [0, 0, 1]],
                    width=64, height=48)

    def test_camera_selection_uses_only_projection_area_and_name_tie(self):
        bounds = dict(x=[0, 1], y=[0, 1], z=[2, 4])
        views = [self.camera('z.png', 20), self.camera('b.png', 10), self.camera('a.png', 20)]
        selected, candidates = cases.choose_photo(views, bounds)
        self.assertEqual(selected['name'], 'a.png')
        self.assertEqual(selected['bbox'], [32, 24, 42, 34])
        self.assertEqual(selected['evaluation_index'], 0)
        self.assertEqual(candidates[-1]['bbox_area_pixels'], 25)

    def test_behind_all_evaluation_cameras_is_unavailable(self):
        selected, _ = cases.choose_photo([self.camera('a.png', 20)], dict(x=[0, 1], y=[0, 1], z=[-4, -2]))
        self.assertIsNone(selected)

    def test_same_crop_preserves_photo_and_black_render_pixels(self):
        photo = np.arange(8*9*3, dtype=np.uint8).reshape(8, 9, 3)
        native, changed = np.zeros_like(photo), np.full_like(photo, 255)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            receipt = cases.write_photo_triptych(photo, native, changed, [2, 1, 7, 6], root)
            np.testing.assert_array_equal(np.asarray(Image.open(root/'photo_crop.png')), photo[1:6, 2:7])
            self.assertTrue(np.all(np.asarray(Image.open(root/'native_crop.png'))==0))
            self.assertTrue(np.all(np.asarray(Image.open(root/'changed_crop.png'))==255))
            self.assertFalse(receipt['pixel_resize'])
            self.assertFalse(receipt['exposure_fit'])

    def test_case_prism_clips_to_region_with_unchanged_full_height(self):
        bounds = cases.case_prism(dict(center_x_m=1., center_y_m=.5), dict(x=[0, 10], y=[0, 10], z=[-50, -10]))
        self.assertEqual(bounds, dict(x=[0, 3.5], y=[0, 3.], z=[-50, -10]))


class SealedCaseEndToEndTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.task = Path(self.temp.name)
        self.used_candidate, self.evaluated = [], []
        self.config = dict(scientific_verdict=None, regions={'P1': {'domain': dict(x=[0, 1], y=[0, 1], z=[2, 4])}})
        self.save_json('contracts/execution_v1.json', self.config)
        self.save_json('contracts/evaluation_analysis_v1.json', dict(scientific_verdict=None, fixture_only=True))
        self.views = []
        for index, (name, focal) in enumerate([('a.png', 10), ('b.png', 20)]):
            path = self.task/'inputs/P1/scene/images'/name
            path.parent.mkdir(parents=True, exist_ok=True)
            Image.fromarray(np.full((48, 64, 3), 123, dtype=np.uint8)).save(path)
            self.used_candidate.append(self.record(path))
            self.views.append(dict(name=name, image_id=index+1, camera_id=index+10, width=64, height=48,
                R=np.eye(3).tolist(), t=[0, 0, 0], K=[[focal, 0, 32], [0, focal, 24], [0, 0, 1]], sha256=cases.sha(path)))
        split = self.save_json('inputs/P1/scene/split_manifest_da3_v2.json', dict(region='P1', train=[], evaluation=self.views))
        self.used_candidate.append(self.record(split))
        candidates = []
        for condition, value in [('D005_Pnative', 0), ('changed', 255)]:
            records = []
            for index, view in enumerate(self.views):
                path = self.task/f'runs/P1/{condition}/renders/{index:05d}.png'
                path.parent.mkdir(parents=True, exist_ok=True)
                Image.fromarray(np.full((48, 64, 3), value, dtype=np.uint8)).save(path)
                self.used_candidate.append(self.record(path))
                records.append(dict(name=view['name'], image_id=view['image_id'], camera_id=view['camera_id'], evaluation_index=index,
                    render_path=str(path.relative_to(self.task)), render_sha256=cases.sha(path)))
            candidates.append(dict(region='P1', condition=condition, variant='final', mesh_kind='raw', render_records=records))
        self.seal_path = self.save_json('contracts/candidates_sealed_v1.json', dict(scientific_verdict=None,
            status='ALL_FIXED_CANDIDATES_SEALED', config_sha256=cases.sha(self.task/'contracts/execution_v1.json'),
            files=self.used_candidate, candidates=candidates))
        self.reference = np.array([[.4, .4, 3], [.5, .5, 3], [.6, .6, 3]])
        for name in ('prior_mesh', 'mvs_points', 'D005_Pnative.anchor.raw', 'D005_Pnative.final.raw', 'changed.final.raw'):
            path = self.task/f'evaluation/geometry/P1/{name}/{cases.PRIMARY}.npz'
            path.parent.mkdir(parents=True, exist_ok=True)
            np.savez(path, prediction_surface_samples=self.reference+[0, 0, .1], reference_points=self.reference,
                     reference_original_indices=np.arange(3), reference_to_candidate_distance=np.full(3, .1))
            metric = self.save_json(str(path.with_suffix('.json').relative_to(self.task)), dict(status='ASSESSED_DEVELOPMENT_ONLY',
                surface_kind='ORIGINAL_POINTSET_NN_BASELINE' if name=='mvs_points' else 'triangle_surface',
                candidate_seal_sha256=cases.sha(self.seal_path)))
            self.evaluated.extend([self.record(path), self.record(metric)])
        self.case = dict(region='P1', condition='changed', center_x_m=.5, center_y_m=.5, reference_points=3,
                         selection_reason='synthetic_fixture_case', reference_to_prior_relation='reference_consistent_prior')
        selected = self.save_json('evaluation/summary/selected_cases.json', dict(scientific_verdict=None,
            cases=[self.case], analysis_config_sha256=cases.sha(self.task/'contracts/evaluation_analysis_v1.json')))
        viewer = self.save_json('evaluation/viewer/manifest.json', dict(scientific_verdict=None, regions=[dict(id='P1', sections=[], renders=[])]))
        self.viewer_sha = cases.sha(viewer)
        self.summary = self.save_json('evaluation/summary/receipt.json', dict(scientific_verdict=None,
            status='TABLES_AND_ACTUAL_VIEWER_DATA_READY', candidate_seal_sha256=cases.sha(self.seal_path),
            config_sha256=cases.sha(self.task/'contracts/execution_v1.json'),
            analysis_config_sha256=cases.sha(self.task/'contracts/evaluation_analysis_v1.json'),
            summary_files=[self.record(selected), self.record(viewer)], case_figure_input_files=self.evaluated))

    def tearDown(self):
        self.temp.cleanup()

    def record(self, path):
        return dict(path=str(path.relative_to(self.task)), sha256=cases.sha(path), bytes=path.stat().st_size)

    def save_json(self, relative, value):
        path = self.task/relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value))
        return path

    def test_gated_actual_pipeline_shared_axes_crops_and_additive_viewer(self):
        output = self.task/'evaluation/cases_v1'
        result = cases.run(self.task, output, viewer_manifest_v2=True)
        self.assertEqual(len(result['cases']), 1)
        item = result['cases'][0]
        metadata = json.loads((output/item['metadata_url']).read_text())
        self.assertEqual(len(metadata['sections']), 10)
        for axis in 'xy':
            sections = [row for row in metadata['sections'] if row['section_axis']==axis]
            self.assertTrue(all(row['horizontal_bounds']==[0, 1] and row['z_bounds']==[2, 4] for row in sections))
            self.assertEqual(len({row['reference_samples'] for row in sections}), 1)
        self.assertEqual(metadata['photo_comparison']['selected_camera']['name'], 'b.png')
        self.assertEqual(cases.sha(self.task/'evaluation/viewer/manifest.json'), self.viewer_sha)
        viewer = json.loads((self.task/'evaluation/viewer/manifest_v2.json').read_text())
        self.assertEqual(len(viewer['regions'][0]['sections']), 1)
        self.assertEqual(len(viewer['regions'][0]['renders']), 1)
        self.assertFalse(result['raw_reference_accessed'])
        self.assertTrue(all(len(row['sha256'])==64 for row in result['inputs']))
        with self.assertRaises(FileExistsError):
            cases.run(self.task, output, viewer_manifest_v2=True)

    def test_unsealed_summary_stops_before_creating_output(self):
        data = json.loads(self.summary.read_text())
        data['candidate_seal_sha256'] = '0'*64
        self.summary.write_text(json.dumps(data))
        output = self.task/'evaluation/cases_v1'
        with self.assertRaisesRegex(ValueError, 'identity differs'):
            cases.run(self.task, output)
        self.assertFalse(output.exists())

    def test_changed_evaluated_array_is_rejected_without_recomputation(self):
        gate = cases.load_gate(self.task)
        path = self.task/self.evaluated[0]['path']
        path.write_bytes(path.read_bytes()+b'changed')
        with self.assertRaisesRegex(ValueError, 'bytes changed'):
            cases.load_geometry(self.task, 'P1', 'changed', gate)

    def test_mismatched_render_pose_and_bytes_are_rejected(self):
        gate = cases.load_gate(self.task)
        gate['candidates']['candidates'][1]['render_records'][1]['camera_id'] = 99
        directory = self.task/'fixture_output'
        directory.mkdir()
        with self.assertRaisesRegex(ValueError, 'camera identity differ'):
            cases.photo_figure(self.task, 'P1', 'changed', self.config['regions']['P1']['domain'], gate, directory)
        record = gate['candidates']['candidates'][1]['render_records'][1]
        record['camera_id'] = self.views[1]['camera_id']
        path = self.task/record['render_path']
        path.write_bytes(path.read_bytes()+b'changed')
        with self.assertRaisesRegex(ValueError, 'bytes changed'):
            cases.photo_figure(self.task, 'P1', 'changed', self.config['regions']['P1']['domain'], gate, directory)

    def test_reference_absence_and_empty_candidate_sections_remain_explicit(self):
        geometry = [dict(id='missing', label='Absent fixture surface', points=np.empty((0, 3)),
                         evaluation_status='RECONSTRUCTION_FAILURE', surface_kind='triangle_surface')]*5
        result = cases.section_figure(self.task/'empty_sections.png', geometry, np.empty((0, 3)),
                                     dict(self.case, reference_points=0), self.config['regions']['P1']['domain'])
        self.assertTrue(all(row['reference_samples']==0 and row['prediction_samples']==0 for row in result))
        self.assertTrue(all(row['evaluation_status']=='RECONSTRUCTION_FAILURE' for row in result))


if __name__ == '__main__':
    unittest.main()
