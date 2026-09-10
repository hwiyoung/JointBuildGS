"""Synthetic correctness and fail-closed checks; no experimental references."""
import copy
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
CODE = ROOT/'scripts/phd/local_complementary_refinement_v1'
sys.path.insert(0, str(CODE))
import evaluation_utils_v2 as ev
import evaluate_v2 as driver


SPEC = dict(thresholds_m=[.1, .2, .25, .5, 1., 2.],
    surface_sample_spacing_m=.1, reference_voxel_m=.1, seed=0,
    reference_voxel_origin=[0., 0., 0.], xy_cell_m=.5,
    paired_primary_threshold_m=.5, source_stratum_threshold_m=.5,
    distance_change_reporting_epsilon_m=1e-6,
    reference_for_training_or_parameter_selection=False,
    mesh_resolutions=[512], scientific_verdict=None)


class EvaluationV2Tests(unittest.TestCase):
    def test_known_failure_is_not_pending_when_later_phases_are_absent(self):
        with tempfile.TemporaryDirectory() as root:
            run=Path(root);(run/'train_receipt.json').write_text('{"status":"FAIL"}')
            row=driver.run_phase_presence(run)
            self.assertEqual(row['status'],'FAILED_PHASE')
            self.assertEqual(row['phase_statuses'],dict(train='FAIL',render='MISSING',metrics='MISSING'))

    def test_pending_phase_is_distinct_from_all_phase_receipts_pass(self):
        with tempfile.TemporaryDirectory() as root:
            run=Path(root);self.assertEqual(driver.run_phase_presence(run)['status'],'PENDING_OR_MISSING_PHASE')
            for phase in ['train','render','metrics']:(run/(phase+'_receipt.json')).write_text('{"status":"PASS"}')
            self.assertEqual(driver.run_phase_presence(run)['status'],'ALL_PHASE_RECEIPTS_PASS')

    def test_malformed_receipt_is_not_pending(self):
        with tempfile.TemporaryDirectory() as root:
            run=Path(root);(run/'train_receipt.json').write_text('{')
            self.assertEqual(driver.run_phase_presence(run)['status'],'INVALID_PHASE_RECEIPT')

    def test_unknown_receipt_status_is_invalid(self):
        with tempfile.TemporaryDirectory() as root:
            run=Path(root);(run/'train_receipt.json').write_text('{"status":"UNREVIEWED"}')
            self.assertEqual(driver.run_phase_presence(run)['status'],'INVALID_PHASE_STATUS')

    def test_explicit_spec_and_no_implicit_training_threshold(self):
        ev.validate_evaluation_spec(SPEC)
        for key in SPEC:
            altered = dict(SPEC)
            del altered[key]
            with self.subTest(key=key), self.assertRaises(ValueError):
                ev.validate_evaluation_spec(altered)

    def test_reference_cannot_be_training_input(self):
        altered = dict(SPEC, reference_for_training_or_parameter_selection=True)
        with self.assertRaises(ValueError):
            ev.validate_evaluation_spec(altered)

    def test_three_way_all_eight_states_are_exhaustive(self):
        # Binary 000..111 means near Anchor, G, LC. Far is 1m, near .1m.
        states = np.arange(8)
        anchor = np.where(states & 4, .1, 1.)
        global_result = np.where(states & 2, .1, 1.)
        local = np.where(states & 1, .1, 1.)
        row = ev.three_way_rows('P1','LC','G','raw',anchor,global_result,local,
                               {'ALL': np.ones(8, bool)}, [.5])[0]
        for state in range(8):
            self.assertEqual(row[f'anchor_global_local_near_{state:03b}_count'], 1)
        self.assertEqual(row['global_corrected_count'], 2)
        self.assertEqual(row['global_correction_lost_by_local_count'], 1)
        self.assertEqual(row['global_damage_recovered_by_local_count'], 1)
        self.assertEqual(row['additional_local_damage_count'], 1)
        self.assertEqual(row['reference_count'], 8)

    def test_empty_surface_is_failure_not_reference_absence(self):
        row = ev.paired_rows('P','LC','G','raw',np.array([.1, 1.]),np.full(2,np.inf),
                             {'ALL':np.ones(2,bool)},[.5])[0]
        self.assertEqual(row['damaged_count'], 1)
        self.assertEqual(row['became_missing_count'], 2)
        self.assertEqual(row['candidate_reference_recall'], 0.)
        self.assertIsNone(row['paired_change_mean_m'])

    def test_numeric_equality_is_not_effect_threshold(self):
        row = ev.paired_rows('P','LC','G','raw',np.array([.1,.2]),np.array([.10000001,.1]),
                             {'ALL':np.ones(2,bool)},[.5])[0]
        self.assertEqual(row['equal_finite_distance_count'], 1)
        self.assertEqual(row['closer_finite_count'], 1)
        self.assertLess(row['paired_change_mean_m'], 0)

    def test_threshold_boundary_is_strict_for_proximity(self):
        row = ev.paired_rows('P','LC','G','raw',np.array([.5]),np.array([.499]),
                             {'ALL':np.ones(1,bool)},[.5])[0]
        self.assertEqual(row['corrected_count'], 1)

    def test_four_source_strata_exclude_unsupported_targets(self):
        paired = dict(strict_target_world_z_error_median=np.array([.5,1.,.5,1.,np.nan]),
                      strict_view_count=np.ones(5), strict_view_range=np.zeros(5))
        strata = ev.evaluation_cohorts(paired,np.ones(5),np.array([.1,.1,1.,1.,.1]))
        selected = [v for k,v in strata.items() if k.startswith('PRIOR_PROXIMITY_')]
        np.testing.assert_array_equal(np.sum(selected,axis=0),[1,1,1,1,0])
        self.assertEqual(strata['NO_STRICT_SUPPORT'].sum(), 1)

    def test_source_membership_mismatch_fails(self):
        with self.assertRaises(ValueError):
            ev.require_membership(np.zeros((2,3)),np.array([2,1]),np.zeros((2,3)),np.array([1,2]))
        with self.assertRaises(ValueError):
            ev.three_way_rows('P','LC','G','raw',np.ones(2),np.ones(1),np.ones(2),{'ALL':np.ones(2,bool)},[.5])
        with self.assertRaises(ValueError):
            ev.validate_distances(np.array([np.nan]),1)

    def test_same_tile_simultaneous_correction_and_damage(self):
        paired = dict(xy_cell_index=np.array([0,0,1]),xy_cell_centres=np.array([[.25,.25],[.75,.25]]),
                      strict_target_world_z_error_median=np.array([0.,0.,np.nan]))
        rows = ev.spatial_rows('P','LC','G','raw',paired,np.array([1.,.1,.1]),np.array([.1,1.,.1]))
        self.assertTrue(rows[0]['both_correction_and_damage'])
        self.assertEqual(rows[0]['corrected_count'],rows[0]['damaged_count'])
        self.assertFalse(rows[1]['both_correction_and_damage'])

    def test_output_cannot_escape_by_symlink_or_traversal(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)/'root'; root.mkdir()
            (root/'escape').symlink_to(Path(temp))
            for path in ('../outside','escape/outside','/outside'):
                with self.assertRaises(ValueError): ev.safe_child(root,path)

    def test_psnr_uses_actual_rgb_and_explicit_infinity(self):
        black = np.zeros((2,2,3),np.uint8)
        self.assertEqual(ev.psnr_uint8(black,black),(None,True))
        self.assertEqual(ev.psnr_uint8(black,np.full_like(black,255)),(0.,False))

    def test_producer_output_digest_fails_on_disagreement(self):
        receipt={'outputs':[{'path':'/output/a','sha256':'one'}],
                 'validation':[{'path':'a','sha256':'two'}]}
        with self.assertRaises(ValueError): driver.output_digest(receipt,'a')


class AppearanceIdentityTests(unittest.TestCase):
    def fixture(self):
        views=[dict(name='photo.jpg',image_id=71,camera_id=1,sha256='sealed-photo')]
        records=[dict(name='photo.jpg',image_id=71,camera_id=1,evaluation_index=0,render_sha256='sealed-render')]
        boxes={('photo.jpg','full_frame'):[0,0,10,8],('photo.jpg','fixed_prism_projected_bbox'):[1,2,6,8]}
        rows=[]
        for (_,domain),box in boxes.items():
            rows.append(dict(region='P2',condition='G',stage='final',name='photo.jpg',domain=domain,
                image_id='71',camera_id='1',evaluation_index='0',photo_sha256='sealed-photo',
                render_sha256='sealed-render',status='ASSESSED',pixel_count=str((box[2]-box[0])*(box[3]-box[1])),
                **{key:str(value) for key,value in zip(('roi_x0','roi_y0','roi_x1','roi_y1'),box)}))
        return rows,views,records,boxes

    def check(self,rows,views,records,boxes):
        return driver.validate_parent_appearance(rows,'P2','G',views,records,boxes)

    def test_fixed_identity_and_rectangles_pass(self):
        self.assertEqual(len(self.check(*self.fixture())),2)

    def test_duplicate_and_extra_domains_cannot_be_silently_overwritten(self):
        rows,views,records,boxes=self.fixture()
        for changed in (rows+rows[:1],rows[:1],rows+[dict(rows[0],name='other.jpg')]):
            with self.subTest(rows=len(changed)),self.assertRaises(ValueError):
                self.check(changed,views,records,boxes)

    def test_same_camera_different_image_or_source_fails(self):
        for key,value in [('image_id','72'),('evaluation_index','1'),('photo_sha256','other'),('render_sha256','other')]:
            rows,views,records,boxes=self.fixture();rows[0][key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):self.check(rows,views,records,boxes)

    def test_equal_pixel_count_shifted_crop_fails(self):
        rows,views,records,boxes=self.fixture()
        rows[1].update(roi_x0='2',roi_x1='7')  # Same 30 pixels, different region.
        with self.assertRaises(ValueError):self.check(rows,views,records,boxes)

    def test_pixel_denominator_and_failure_status_are_not_ignored(self):
        for key,value in [('pixel_count','29'),('status','METRIC_OR_MONTAGE_FAILURE')]:
            rows,views,records,boxes=self.fixture();rows[1][key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):self.check(rows,views,records,boxes)

    def test_absent_prism_is_explicit_not_zero_pixel_assessed(self):
        rows,views,records,boxes=self.fixture();boxes['photo.jpg','fixed_prism_projected_bbox']=None
        rows[1].update(status='PRISM_NOT_IN_CAMERA_DOMAIN',pixel_count='0',roi_x0='',roi_y0='',roi_x1='',roi_y1='')
        self.check(rows,views,records,boxes)
        rows[1]['status']='ASSESSED'
        with self.assertRaises(ValueError):self.check(rows,views,records,boxes)

    def test_render_seal_wrong_order_fails_even_if_csv_matches_photo(self):
        rows,views,records,boxes=self.fixture();records[0]['evaluation_index']=1
        with self.assertRaises(ValueError):self.check(rows,views,records,boxes)

    def test_runtime_requires_the_host_verified_launcher_and_image(self):
        launcher=CODE/'run_evaluation_v2.sh'
        env=dict(JBGS_EVALUATION_IMAGE_ID='sha256:fixed',JBGS_EVALUATION_LAUNCHER_SHA256=ev.sha(launcher))
        with mock.patch.dict(driver.os.environ,env):
            result=driver.evaluation_runtime(driver.Evidence(),'sha256:fixed')
            self.assertEqual(set(result['versions']),{'python','numpy','scipy','open3d','pillow'})
            self.assertFalse(result['reference_used_for_training_or_parameter_selection'])
            with self.assertRaises(ValueError):driver.evaluation_runtime(driver.Evidence(),'sha256:changed')
        with mock.patch.dict(driver.os.environ,dict(env,JBGS_EVALUATION_LAUNCHER_SHA256='changed')):
            with self.assertRaises(ValueError):driver.evaluation_runtime(driver.Evidence(),'sha256:fixed')

    def test_snapshot_is_exact_and_rejects_change_after_hash_binding(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);source=root/'evaluation.py';source.write_bytes(b'original')
            output=root/'attempt';output.mkdir();evidence=driver.Evidence();evidence.bind(source)
            records=driver.snapshot_implementation(output,[source],evidence)
            self.assertEqual((output/records[0]['path']).read_bytes(),b'original')
            source.write_bytes(b'changed')
            second=root/'attempt2';second.mkdir()
            with self.assertRaises(ValueError):driver.snapshot_implementation(second,[source],evidence)


class GeometryCacheTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.geometry=driver.load_module('synthetic_geometry',driver.GEOMETRY_DIR/'geometry.py')

    def synthetic(self,empty=False,reference_absent=False):
        vertices=np.empty((0,3)) if empty else np.array([[0.,0.,0.],[1.,0.,0.],[0.,1.,0.]])
        triangles=np.empty((0,3),int) if empty else np.array([[0,1,2]])
        reference=np.empty((0,3)) if reference_absent else np.array([[.2,.2,.1],[.4,.4,.1]])
        metrics,arrays=self.geometry.evaluate_geometry(vertices,triangles,reference,
            [[0.,1.],[0.,1.],[-1.,1.]],thresholds=SPEC['thresholds_m'])
        metrics['mesh_res']=512
        return metrics,arrays

    def test_triangle_interior_and_cache_recalculation(self):
        metrics,arrays=self.synthetic()
        np.testing.assert_allclose(arrays['reference_to_triangle_distance'],.1,atol=1e-6)
        ev.verify_metric_cache(metrics,arrays,SPEC,arrays['reference_points'],arrays['reference_original_indices'])
        for key in ('precision','recall','f1'):
            broken=copy.deepcopy(metrics); broken['thresholds'][0][key]+=.01
            with self.subTest(key=key),self.assertRaises(ValueError):
                ev.verify_metric_cache(broken,arrays,SPEC,arrays['reference_points'],arrays['reference_original_indices'])

    def test_zero_prediction_keeps_reference_and_zero_scores(self):
        metrics,arrays=self.synthetic(empty=True)
        self.assertEqual(metrics['status'],'RECONSTRUCTION_FAILURE')
        self.assertTrue(np.isinf(arrays['reference_to_triangle_distance']).all())
        self.assertTrue(all(r['f1']==0 for r in metrics['thresholds']))
        ev.verify_metric_cache(metrics,arrays,SPEC,arrays['reference_points'],arrays['reference_original_indices'])

    def test_missing_reference_remains_unassessed(self):
        metrics,arrays=self.synthetic(reference_absent=True)
        self.assertEqual(metrics['status'],'NOT_ASSESSED_REFERENCE_ABSENT')
        self.assertTrue(all(r['f1'] is None for r in metrics['thresholds']))
        ev.verify_metric_cache(metrics,arrays,SPEC,arrays['reference_points'],arrays['reference_original_indices'])

    def test_coverage_does_not_call_unobserved_cells_wrong(self):
        metrics,arrays=self.synthetic()
        row=ev.coverage_row('P','LC','raw',metrics,1)
        self.assertEqual(row['roi_intersecting_xy_cell_count'],4)
        self.assertFalse(row['coverage_certified'])
        self.assertFalse(row['reference_absence_is_prediction_failure'])
        self.assertEqual(row['strict_target_unsupported_reference_count'],1)

    def test_raw_and_post_areas_are_separate(self):
        raw,_=self.synthetic(); post,_=self.synthetic(empty=True)
        row=ev.postprocess_row('P','LC',raw,post)
        self.assertEqual(row['raw_removed_area_fraction'],1.)
        self.assertEqual(row['post_status'],'RECONSTRUCTION_FAILURE')


class ComputeScopeTests(unittest.TestCase):
    def test_1024_and_512_render_costs_are_not_same_scope(self):
        old=driver.phase_cost_scope({'command':['render.py','--mesh_res','1024']},'render','parent_primary_driver')
        new=driver.phase_cost_scope({'command':['render.py','--mesh_res','512']},'render','new_v2_driver')
        self.assertEqual(old['mesh_res'],1024)
        self.assertIn('mesh_res',driver.cost_scope_differences(new,old,'render'))

    def test_512_without_exports_is_not_512_full_render_phase(self):
        old=driver.phase_cost_scope({'command':['render.py','--mesh_res','512','--skip_train','--skip_test']},'render','parent_auxiliary_variant')
        new=driver.phase_cost_scope({'command':['render.py','--mesh_res','512']},'render','new_v2_driver')
        differences=driver.cost_scope_differences(new,old,'render')
        self.assertNotIn('mesh_res',differences)
        self.assertIn('exports_train_images',differences)
        self.assertIn('exports_test_images',differences)
        self.assertIn('driver_timing_boundary_and_instrumentation',differences)

    def test_anchor_and_extra_checkpoint_cost_are_visible(self):
        old=driver.phase_cost_scope({'training_start_iteration':0,
            'command':['train.py','--iterations','30000','--jbgs_capture_iterations','8000','8100','30000']},'train','parent_primary_driver')
        new=driver.phase_cost_scope({'training_start_iteration':8000,
            'command':['train.py','--iterations','30000','--jbgs_capture_iterations','30000']},'train','new_v2_driver')
        self.assertEqual(old['iteration_count'],30000)
        self.assertEqual(new['iteration_count'],22000)
        self.assertEqual(old['complete_capture_iterations_in_executed_range'],[8000,8100,30000])
        self.assertIn('complete_capture_iterations_in_executed_range',driver.cost_scope_differences(new,old,'train'))

    def test_fullframe_metric_scope_does_not_claim_roi_scores(self):
        result=driver.phase_cost_scope({'phase':'metrics','command':['metrics.py','-m','/model']},'metrics','new_v2_driver')
        self.assertEqual(result['image_domain'],'full_frame')
        self.assertEqual(result['psnr_unit'],'dB')
        self.assertEqual(result['ssim_unit'],'dimensionless')
        self.assertFalse(result['roi_ssim_lpips_in_this_phase'])
        self.assertFalse(result['roi_psnr_in_this_phase'])

    def test_conflicting_resolution_metadata_fails(self):
        with self.assertRaises(ValueError):
            driver.phase_cost_scope({'mesh_res':512,'command':['render.py','--mesh_res','1024']},'render','new_v2_driver')

    def test_auxiliary_cost_requires_exact_sealed_surface_identity(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);directory=root/'extraction_resource_v3/primary/P2/D005_Pnative/auxiliary/mesh_512'
            files=[];candidates=[]
            for kind,filename in [('raw','fuse.ply'),('post','fuse_post.ply')]:
                relative='model/train/ours_30000/'+filename
                path=directory/relative;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(kind.encode())
                files.append(dict(path=relative,exists=True,sha256=ev.sha(path)))
                candidates.append(dict(region='P2',condition='D005_Pnative',variant='mesh_512',mesh_kind=kind,
                    surface=dict(path=str(path.relative_to(root)),sha256=ev.sha(path))))
            seal=root/'contracts/candidates_sealed_v1.json';ev.write_json(seal,dict(candidates=candidates))
            parent_render=dict(input_manifest_sha256='input',runtime_image_id='image',render_source_ply={'sha256':'model'})
            receipt=dict(region='P2',condition='D005_Pnative',phase='auxiliary_variant',variant='mesh_512',
                iteration=30000,mesh_res=512,status='PASS',scientific_verdict=None,input_manifest_sha256='input',
                runtime_image_id='image',source_complete_ply_sha256='model',copied_ply_sha256='model',files=files,
                wall_seconds=12.3,command=['render.py','--mesh_res','512','--skip_train','--skip_test'])
            ev.write_json(directory/'receipt.json',receipt)
            with mock.patch.object(driver,'PARENT_SEAL_SHA',ev.sha(seal)):
                valid=driver.parent_512_extraction_cost(root,'P2','D005_Pnative',parent_render,driver.Evidence())
                self.assertEqual(valid['parent_aux512_wall_seconds'],12.3)
                self.assertEqual(valid['parent_aux512_cost_status'],'VERIFIED_EXACT_SURFACE_CONTEXTUAL_COST')
                self.assertTrue(valid['parent_aux512_not_comparable_as_pure_method_cost'])
                self.assertFalse(valid['parent_aux512_matched_phase_cost_available'])
                (directory/files[0]['path']).write_bytes(b'changed')
                invalid=driver.parent_512_extraction_cost(root,'P2','D005_Pnative',parent_render,driver.Evidence())
                self.assertEqual(invalid['parent_aux512_cost_status'],'UNAVAILABLE_IDENTITY_NOT_VERIFIED')
                self.assertIsNone(invalid['parent_aux512_wall_seconds'])

    def test_missing_auxiliary_cost_is_unavailable(self):
        with tempfile.TemporaryDirectory() as temp:
            result=driver.parent_512_extraction_cost(Path(temp),'P2','D005_Pnative',{},driver.Evidence())
            self.assertEqual(result['parent_aux512_cost_status'],'UNAVAILABLE')
            self.assertIsNone(result['parent_aux512_wall_seconds'])


if __name__=='__main__': unittest.main()
