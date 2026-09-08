"""Viewer provenance, schema, native display, and arbitrary saved-pair replay."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import cv2
import numpy as np

from scripts.phd.source_candidate_v1.common import sha, write
from scripts.phd.source_candidate_viewer_v1.data import DataStore, TASK_ID
from src.phd.source_candidate_v1.geometry import self_depth_buffer
from src.phd.source_candidate_v1.photometry import score_candidates
from tests.phd.test_source_candidate_photometry import plane, synthetic_views


def build_fixture(root):
    parent=root/'task';run=parent/'run';inputs=root/'inputs';rgb=root/'images'
    run.mkdir(parents=True);rgb.mkdir()
    views=[];loaded=[]
    for view in synthetic_views():
        name=f"frame_{view['id']}.png";path=rgb/name
        image=np.clip(np.rint(view['gray']),0,255).astype(np.uint8)
        assert cv2.imwrite(str(path),image)
        meta=dict(image_id=view['id'],name=name,path=str(path),sha256=sha(path),width=view['width'],
                  height=view['height'],R=view['R'].tolist(),t=view['t'].tolist(),K=view['K'].tolist())
        views.append(meta);loaded.append(dict(view,gray=image.astype(np.float32)))
    cfg=dict(max_views=4,max_pairs=6,max_patch_centers=9,minimum_patch_std=2.,
             profile_offsets_m=[-2.,-1.,-.5,0.,.5,1.,2.])
    candidates={'mvs':plane(10),'als':plane(12)}
    native={s+'_xyz':c['support_points'].astype(np.float32) for s,c in candidates.items()}
    native['mvs_rgb']=np.tile(np.array([24,125,230],np.uint8),(len(native['mvs_xyz']),1))
    for source in candidates:
        candidates[source]['context_depths']={v['id']:self_depth_buffer(native[source+'_xyz'],v,1,1)for v in loaded}
    observation=score_candidates(candidates,loaded,cfg)
    self_visibility=dict(downsample=1,splat_radius=1)
    config=dict(task_id=TASK_ID,regions={},self_visibility=self_visibility)
    files={};evaluation=[]
    for region in ('P1','P2','P3'):
        local=inputs/region;local.mkdir(parents=True)
        np.savez(local/'native.npz',**native);write(local/'views.json',dict(views=views))
        config['regions'][region]=dict(domain={'x':[-5,5],'y':[-5,5],'z':[5,15]},view_count=4,
            native_sha256=sha(local/'native.npz'),views_sha256=sha(local/'views.json'))
        destination=run/region;destination.mkdir()
        row=dict(cell_id=0,ix=0,iy=0,x=0.,y=0.,bbox_xy=[-5,-5,5,5],both_valid=True,
                 height_difference_m=-2.,availability='BOTH',area_m2=100.,
                 candidates={s:{k:candidates[s][k]for k in ('center','normal','valid')}for s in candidates})
        write(destination/'candidates.json',[row]);write(destination/'observations.json',[dict(cell_id=0,observation=observation)])
        write(destination/'decisions.json',[dict(cell_id=0,action='IMAGE',accepted=True,scientific_verdict=None)])
        membership={s+'_cell':np.zeros(len(native[s+'_xyz']),np.int64)for s in candidates}
        membership.update({s+'_inlier':np.ones(len(native[s+'_xyz']),bool)for s in candidates})
        np.savez(destination/'membership.npz',**membership)
        for stage in ('input','observation','decision'):
            write(destination/(stage+'_summary.json'),dict(region=region,total_cells=1))
        write(destination/'rgb_ledger.json',[{k:v[k]for k in ('image_id','name','sha256','width','height')}for v in views])
        for name in ('candidates.json','membership.npz','observations.json','decisions.json','input_summary.json',
                     'observation_summary.json','decision_summary.json','rgb_ledger.json'):
            files[f'{region}/{name}']=sha(destination/name)
        evaluation.append(dict(region=region,cell_id=0,mvs_error_m=0.,als_error_m=2.,action='IMAGE'))
    write(run/'sensitivity.json',[]);files['sensitivity.json']=sha(run/'sensitivity.json')
    write(run/'config.json',config)
    write(run/'method_seal.json',dict(status='METHOD_FROZEN_BEFORE_REFERENCE_ACCESS',scientific_verdict=None,
        reference_accessed=False,config_sha256=sha(run/'config.json'),files=files))
    ev=run/'evaluation';ev.mkdir();seal_sha=sha(run/'method_seal.json')
    write(ev/'summary.json',dict(method_seal_sha256=seal_sha,regions={r:dict(accepted_cells=1)for r in config['regions']}))
    write(ev/'per_cell.json',evaluation)
    write(ev/'evaluation_receipt.json',dict(method_seal_sha256=seal_sha,scientific_verdict=None,
        reference_accessed_only_after_all_method_verification=True,
        output_sha256={name:sha(ev/name)for name in ('summary.json','per_cell.json')}))
    return parent,inputs,native


class SourceCandidateViewerDataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory();cls.root=Path(cls.tmp.name)
        cls.parent,cls.inputs,cls.native=build_fixture(cls.root)
        cls.store=DataStore(cls.parent,cls.inputs)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_manifest_region_and_cell_schema_are_finite(self):
        manifest=self.store.manifest()
        self.assertEqual(manifest['task_id'],TASK_ID)
        self.assertIsNone(manifest['scientific_verdict'])
        self.assertEqual(manifest['verified_image_count'],4)
        self.assertEqual([r['id']for r in manifest['regions']],['P1','P2','P3'])
        region=self.store.region('P2');self.assertEqual(region['cells'][0]['cell_id'],0)
        cell=self.store.cell('P2',0)
        self.assertEqual(cell['decision']['action'],'IMAGE')
        self.assertEqual(len(cell['points']['mvs']['positions']),3*len(self.native['mvs_xyz']))
        json.dumps(dict(manifest=manifest,region=region,cell=cell),allow_nan=False)

    def test_native_display_cap_preserves_original_rows_and_color(self):
        with patch('scripts.phd.source_candidate_viewer_v1.data.DISPLAY_CAP',10):
            payload=self.store.points('P1','mvs')
        self.assertEqual(payload['display_count'],10)
        self.assertEqual(payload['native_count'],len(self.native['mvs_xyz']))
        positions=np.asarray(payload['positions']).reshape(-1,3)
        np.testing.assert_array_equal(positions,self.native['mvs_xyz'][payload['native_row_indices']])
        np.testing.assert_array_equal(np.asarray(payload['colors']).reshape(-1,3),self.native['mvs_rgb'][payload['native_row_indices']])
        self.assertTrue(payload['display_only'])

    def test_arbitrary_saved_pair_and_explicit_anchor_reproduce_nominal_scores(self):
        first=self.store.evidence('P1',0)
        self.assertTrue(first['available']);self.assertTrue(first['reproduced'])
        pairs=[p for p in first['pairs']if p['scored']]
        self.assertGreaterEqual(len(pairs),2)
        second=self.store.evidence('P1',0,pair_id=pairs[1]['pair_id'])
        self.assertEqual(second['pair_id'],pairs[1]['pair_id'])
        self.assertNotEqual(second['pair_id'],first['pair_id'])
        replay=self.store.evidence('P1',0,pair_id=second['pair_id'],anchor=second['anchor'])
        self.assertEqual(replay['patch'],second['patch'])
        for source in ('mvs','als'):
            self.assertAlmostEqual(replay['reproduced_pair_costs'][source],pairs[1][source+'_cost'],places=6)
        self.assertEqual(len(replay['reference']['pixels']),replay['patch']['width']**2)
        self.assertEqual(len(replay['reference']['pixels'][0]),2)
        self.assertEqual(len(replay['target']['pixels']['als']),81)
        self.assertEqual(len(replay['patch']['mask']),81)
        self.assertTrue(all(isinstance(v,bool)for v in replay['patch']['mask']))
        self.assertEqual(replay['reference']['url'],f"/images/P1/{pairs[1]['reference_id']}")
        json.dumps(replay,allow_nan=False)

    def test_unknown_pair_or_anchor_is_explicitly_unavailable(self):
        missing=self.store.evidence('P1',0,pair_id='0->missing')
        self.assertFalse(missing['available']);self.assertEqual(missing['reason'],'UNKNOWN_SAVED_PAIR')
        missing=self.store.evidence('P1',0,anchor=999)
        self.assertFalse(missing['available']);self.assertEqual(missing['reason'],'ANCHOR_OUT_OF_RANGE')
        self.assertGreater(missing['anchor_count'],0)

    def test_image_resolver_rejects_paths_and_unlisted_ids(self):
        self.assertEqual(self.store.image_path('P1',0).name,'frame_0.png')
        for image_id in ('../config.json','4','0/../../passwd'):
            with self.assertRaises(KeyError):self.store.image_path('P1',image_id)
        with self.assertRaises(KeyError):self.store.image_path('UNKNOWN',0)

    def test_tampered_method_is_rejected_before_native_loading(self):
        path=self.parent/'run/P1/decisions.json';previous=path.read_bytes()
        try:
            path.write_text('["tampered"]')
            with patch('numpy.load',side_effect=AssertionError('Must verify seal before scientific arrays')):
                with self.assertRaisesRegex(ValueError,'Sealed method bytes changed'):
                    DataStore(self.parent,self.inputs)
        finally:path.write_bytes(previous)

    def test_tampered_evaluation_and_original_rgb_are_rejected(self):
        for path in (self.parent/'run/evaluation/per_cell.json',self.root/'images/frame_0.png'):
            previous=path.read_bytes()
            try:
                path.write_bytes(previous+b'tampered')
                with self.assertRaisesRegex(ValueError,'Frozen viewer input changed|Original RGB bytes changed'):
                    DataStore(self.parent,self.inputs)
            finally:path.write_bytes(previous)


if __name__=='__main__':
    unittest.main()
