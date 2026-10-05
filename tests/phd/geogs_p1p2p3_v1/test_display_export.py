"""Exact display topology/provenance without regional data or scoring changes."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

import numpy as np
import open3d as o3d

BASE = Path(__file__).resolve().parents[3]/'scripts/phd/geogs_p1p2p3_v1/evaluation'
sys.path.insert(0,str(BASE))
from display_export import export_clipped_mesh,original_mesh_provenance,manifest_mesh_links,display_candidate_state,sha
from geometry import evaluate_geometry
from run_evaluation import export_display,point_metrics


class ExactDisplayExportTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.task=Path(self.temp.name)
        self.viewer=self.task/'evaluation/viewer'
        self.region=self.viewer/'P1'
        self.region.mkdir(parents=True)

    def tearDown(self):
        self.temp.cleanup()

    def test_clipped_float64_vertices_and_every_triangle_are_exact_and_scoring_unchanged(self):
        vertices=np.array([[-1.,.2,0],[2.,.2,0],[.2,2.,0],[.2,.2,.5]],dtype=np.float64)
        triangles=np.array([[0,1,2],[0,1,3]],dtype=np.int64)
        reference=np.array([[.5,.5,0],[.5,.3,.1]])
        bounds={'x':[0.,1.],'y':[0.,1.],'z':[-.1,1.]}
        metrics,arrays=evaluate_geometry(vertices,triangles,reference,bounds,spacing=.2)
        preserved={key:value.copy() for key,value in arrays.items()}
        before_metrics=copy.deepcopy(metrics)
        target=self.region/'candidate.mesh.json'
        meta=export_clipped_mesh(target,arrays,metrics['bounds_half_open'],
            dict(path='official/full_mesh.ply',sha256='synthetic',scope='FULL_CAMERA_BOUNDED_TSDF_EXTRACTION'),[1,2,3],self.viewer,metrics)
        content=json.loads(target.read_text())
        actual_vertices=np.fromfile(self.viewer/content['vertices_f64']['url'],dtype='<f8').reshape(-1,3)
        actual_triangles=np.fromfile(self.viewer/content['triangles_u32']['url'],dtype='<u4').reshape(-1,3)
        self.assertTrue(np.array_equal(actual_vertices,arrays['clipped_vertices']))
        self.assertTrue(np.array_equal(actual_triangles,arrays['clipped_triangles']))
        self.assertEqual(content['triangle_count'],len(arrays['clipped_triangles']))
        self.assertFalse(content['topology_simplified'])
        self.assertFalse(content['artificial_clip_caps'])
        self.assertFalse(content['evaluation_reinput'])
        self.assertEqual(content['gpu_coordinate_dtype'],'float32')
        self.assertEqual(content['evaluation_bvh_coordinate_dtype'],'float32_local_metric')
        self.assertEqual(meta['sha256'],sha(target))
        self.assertEqual(before_metrics,metrics)
        for name in arrays:
            self.assertTrue(np.array_equal(preserved[name],arrays[name],equal_nan=True),name)
        with self.assertRaises(FileExistsError):
            export_clipped_mesh(target,arrays,metrics['bounds_half_open'],{},[1,2,3],self.viewer)

    def test_source_download_requires_exact_sealed_original_and_records_full_context(self):
        source=self.task/'inputs/P1/surface/als_surface.ply'
        source.parent.mkdir(parents=True)
        source.write_bytes(b'synthetic sealed mesh source')
        record=dict(path=str(source.relative_to(self.task)),bytes=source.stat().st_size,sha256=sha(source))
        result=original_mesh_provenance(self.task,source,[record],'prior')
        self.assertEqual(result['scope'],'FULL_PRIOR_INPUT_CONTEXT')
        self.assertTrue(result['evaluation_crop_separate'])
        with self.assertRaisesRegex(ValueError,'absent/ambiguous'):
            original_mesh_provenance(self.task,source,[],'prior')
        source.write_bytes(b'modified')
        with self.assertRaisesRegex(ValueError,'changed after'):
            original_mesh_provenance(self.task,source,[record],'prior')

    def test_source_solid_and_nearest_mesh_vertex_colors_are_not_measured_point_rgb(self):
        points=np.array([[0.,0.,0.],[1.,0.,0.],[0.,1.,0.]])
        arrays=dict(prediction_surface_samples=points,prediction_to_reference_distance=np.zeros(3))
        solid=self.region/'source.json'
        value=export_display(solid,arrays,[21,42,63],'ORIGINAL_POINTSET_NN_BASELINE','synthetic_points.npz',
                             evaluation_metadata=dict(prediction_original_points=12,point_voxel_m=.1))
        self.assertEqual(value['color_provenance']['kind'],'FIXED_SOURCE_COLOR')
        self.assertEqual(value['display_sample_count'],3)
        self.assertEqual(value['full_evaluation_sample_count'],3)
        self.assertEqual(value['original_points_in_roi'],12)
        self.assertEqual(value['sampling_metadata']['evaluation_kind'],'FIXED_VOXEL_SELECTED_ORIGINAL_SOURCE_POINTS')
        mesh=o3d.geometry.TriangleMesh(o3d.utility.Vector3dVector(points),o3d.utility.Vector3iVector([[0,1,2]]))
        mesh.vertex_colors=o3d.utility.Vector3dVector([[1.,0,0],[0,1.,0],[0,0,1.]])
        value=export_display(self.region/'mesh_samples.json',arrays,[21,42,63],'triangle_surface','synthetic_mesh.ply',mesh,
                             dict(surface_sample_spacing_m=.1,reference_voxel_size_m=.2))
        self.assertEqual(value['color_provenance']['kind'],'NEAREST_ORIGINAL_MESH_VERTEX_COLOR')
        self.assertEqual(value['sampling_metadata']['evaluation_kind'],'AREA_UNIFORM_TRIANGLE_SURFACE_SAMPLES')
        self.assertIsNone(value['sampling_metadata']['evaluation_point_voxel_m'])
        self.assertEqual(value['sampling_metadata']['reference_voxel_m'],.2)
        self.assertTrue(value['sampling_metadata']['never_used_in_scoring'])

    def test_invalid_index_cannot_be_silently_truncated_or_repaired(self):
        arrays=dict(clipped_vertices=np.zeros((3,3)),clipped_triangles=np.array([[0,1,3]],dtype=np.int64))
        with self.assertRaisesRegex(ValueError,'topology cannot'):
            export_clipped_mesh(self.region/'invalid.mesh.json',arrays,[],{},[1,2,3],self.viewer)
        self.assertFalse(list(self.region.iterdir()))

    def test_manifest_links_bind_mesh_bytes_and_keep_original_scope_separate(self):
        arrays=dict(clipped_vertices=np.array([[0.,0,0],[1.,0,0],[0,1.,0]]),clipped_triangles=np.array([[0,1,2]]))
        source=self.task/'full_context.ply';source.write_bytes(b'original source')
        source_record=dict(path='full_context.ply',bytes=source.stat().st_size,sha256=sha(source))
        original=original_mesh_provenance(self.task,source,[source_record],'prior')
        data=export_clipped_mesh(self.region/'linked.mesh.json',arrays,[[0,1],[0,1],[0,1]],original,[1,2,3],self.viewer)
        links,files=manifest_mesh_links(self.task,data,original,{'full_context.ply':source_record})
        self.assertEqual(links[0]['url'],'../../full_context.ply')
        self.assertIn('full prior context',links[0]['label'])
        self.assertEqual(len(files),3)
        self.assertEqual(links[1]['url'],'P1/linked.mesh.json')
        with self.assertRaisesRegex(ValueError,'not bound'):
            manifest_mesh_links(self.task,data,original,{})
        vertex=self.viewer/json.loads((self.region/'linked.mesh.json').read_text())['vertices_f64']['url']
        vertex.write_bytes(b'altered binary')
        with self.assertRaisesRegex(ValueError,'differs from exporter'):
            manifest_mesh_links(self.task,data,original,{'full_context.ply':source_record})

    def test_empty_geometry_and_absent_reference_are_display_absence_without_changing_metrics(self):
        bounds={'x':[0.,1.],'y':[0.,1.],'z':[-1.,1.]}
        vertices=np.array([[.1,.1,0],[.8,.1,0],[.1,.8,0]])
        triangles=np.array([[0,1,2]])
        empty=np.empty((0,3))
        for kind in ('mesh','points'):
            for label,prediction,reference,expected in (
                ('both_absent',empty,empty,'no_geometry_reference_absent'),
                ('positive_geometry_reference_absent',vertices,empty,'available'),
                ('prediction_absent_reference_present',empty,vertices,'reconstruction_failure')):
                with self.subTest(kind=kind,case=label):
                    if kind=='mesh':
                        topology=triangles if len(prediction) else np.empty((0,3),dtype=int)
                        metrics,arrays=evaluate_geometry(prediction,topology,reference,bounds,spacing=.2)
                    else:
                        metrics,arrays=point_metrics(prediction,reference,bounds,
                            dict(reference_voxel_m=.1,thresholds_m=[.1,.5],xy_cell_m=.5))
                    before=copy.deepcopy(metrics)
                    metadata=export_display(self.region/(kind+'_'+label+'.json'),arrays,[1,2,3],kind,'synthetic')
                    status,reason=display_candidate_state(metrics,metadata)
                    self.assertEqual(status,expected)
                    self.assertEqual(metrics,before)
                    if not len(reference):
                        self.assertEqual(metrics['status'],'NOT_ASSESSED_REFERENCE_ABSENT')
                        self.assertTrue(all(row['f1'] is None for row in metrics['thresholds']))
                    if label=='both_absent':
                        self.assertEqual(reason,'표시 기하 없음 · 참조 부재로 품질평가 불가')
                    elif label=='positive_geometry_reference_absent':
                        self.assertIsNone(reason)
                        self.assertGreater(metadata['display_sample_count'],0)
                    else:
                        self.assertTrue(all(row['f1']==0 for row in metrics['thresholds']))


if __name__=='__main__':
    unittest.main()
