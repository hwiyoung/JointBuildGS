"""Adversarial decision and numeric support checks, independent of scene labels."""
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
import numpy as np

from src.phd import irregular_source_masks_v1 as dense
from src.phd import mvs_evidence_v1 as old
from scripts.phd.mvs_evidence_v1.build import Builder, patch_uv
from tests.phd.test_mvs_evidence_v1 import camera, texture


CONFIG = json.loads((Path(__file__).resolve().parents[2]/'configs/phd/irregular_source_masks_v1/experiment.json').read_text())


class DenseMaskTests(unittest.TestCase):
    def test_candidate_shape_is_native_and_roi_does_not_fill_missing_source(self):
        p=np.full((7,9),10.); m=p.copy(); roi=np.zeros(p.shape,bool); roi[1:6,1:8]=True
        m[2,2]=12; m[3,3]=12; m[4,4]=12; m[1,5]=np.nan; m[5,7]=0
        state,candidate=dense.initial_decisions(p,m,roi,.5)
        np.testing.assert_array_equal(np.argwhere(state==3), [[2,2],[3,3],[4,4]])
        self.assertEqual(int(candidate.sum()),3); self.assertEqual(int((state==1).sum()),2)
        self.assertEqual(state[2,3],2); self.assertEqual(state[0,0],0)

    def test_both_missing_sources_cannot_certify_outside_roi(self):
        p=np.array([[np.nan,10.,np.nan]]); m=np.array([[np.nan,10.,12.]])
        state,_=dense.initial_decisions(p,m,np.array([[False,False,True]]),.5)
        np.testing.assert_array_equal(state,[[7,0,1]])

    def test_vote_tie_is_not_majority_and_opposition_is_retained(self):
        margins=np.array([[.1,.1],[.1,.1],[-.1,-.1],[-.1,.0]])
        v=dense.votes(margins,np.ones_like(margins,bool),.03,2)
        np.testing.assert_array_equal(v['mvs_winner'],[False,True])
        np.testing.assert_array_equal(v['profile_candidate'],[True,True])
        np.testing.assert_array_equal(v['dissent'],[True,True])
        self.assertEqual(v['prior'][0],2)

    def fixture(self):
        z=np.array([[9.5,9.75,10.,10.25,10.5]])
        costs=np.array([.4,.15,.01,.15,.4])
        raw=np.broadcast_to(costs,(3,1,2,5)).copy()
        return z,raw,np.array([[.1],[.08],[.0]]),np.ones((3,1),bool)

    def test_source_choice_swaps_symmetrically(self):
        z,raw,margin,admission=self.fixture()
        a=dense.decide_profiles(np.array([12.]),np.array([10.]),margin,admission,z,raw,CONFIG)
        b=dense.decide_profiles(np.array([10.]),np.array([12.]),-margin,admission,z,raw[:,:,::-1],CONFIG)
        self.assertEqual(a['decision'][0],5); self.assertEqual(b['decision'][0],6)
        np.testing.assert_allclose(a['curves'],b['curves'])

    def test_tied_photo_votes_reach_profile_and_final_eligible_votes_decide(self):
        z,raw,_,_=self.fixture()
        raw=np.concatenate([raw,raw[:1]],axis=0); raw[2:]=np.nan
        margin=np.array([[.1],[.1],[-.1],[-.1]]); admission=np.ones((4,1),bool)
        pre=dense.votes(margin,admission,.03,2)
        self.assertTrue(pre['profile_candidate'][0]); self.assertFalse(pre['mvs_winner'][0])
        post=dense.decide_profiles(np.array([12.]),np.array([10.]),margin,admission,z,raw,CONFIG)
        self.assertEqual(post['decision'][0],5)

    def test_missing_profile_and_boundary_minimum_abstain(self):
        z,raw,margin,admission=self.fixture(); raw[1]=np.nan
        a=dense.decide_profiles(np.array([12.]),np.array([10.]),margin,admission,z,raw,CONFIG)
        self.assertEqual(a['decision'][0],4)
        z,raw,margin,admission=self.fixture(); raw[:]=[.01,.1,.2,.3,.4]
        a=dense.decide_profiles(np.array([12.]),np.array([9.5]),margin,admission,z,raw,CONFIG)
        self.assertEqual(a['decision'][0],4); self.assertEqual(a['stats']['boundary'][0],1)

    def test_curve_aggregates_opposing_and_neutral_neighbors(self):
        z,raw,margin,admission=self.fixture()
        margin[:]=[[.1],[.08],[-.1]]
        raw[0,0,:,:]=[.4,.18,.01,.18,.4]
        raw[1,0,:,:]=[.3,.12,.04,.12,.3]
        raw[2,0,:,:]=[.01,.05,.2,.25,.3]
        a=dense.decide_profiles(np.array([12.]),np.array([10.]),margin,admission,z,raw,CONFIG)
        np.testing.assert_allclose(a['curves'],np.min(np.median(raw,axis=0),axis=1))
        self.assertEqual(a['votes']['prior'][0],1)
        self.assertFalse(np.allclose(a['curves'],np.min(np.median(raw[:2],axis=0),axis=1)))

    def test_discrete_zero_width_is_not_unresolved_grid_acceptance(self):
        z,raw,margin,admission=self.fixture(); z=np.array([[8.,9.,10.,11.,12.]])
        a=dense.decide_profiles(np.array([12.]),np.array([10.]),margin,admission,z,raw,CONFIG)
        self.assertEqual(a['stats']['width'][0],0); self.assertEqual(a['decision'][0],4)

    def test_fast_raw_pair_matches_existing_common_pixel_computation(self):
        rv,nv=camera(),camera((1.,0.,0.)); rgb=texture(); nb=rgb.copy()
        center=np.array([[50.,40.],[60.,50.]])
        dp=np.array([10.,10.]); dm=np.array([12.,12.]); puv=patch_uv(center,3)
        pp=np.full((2,49),10.); mp=np.full((2,49),12.); pp[0,1]=np.nan
        gray=rgb@np.array([.299,.587,.114]); other=nb@np.array([.299,.587,.114])
        result=dense.paired_costs(center,dp,dm,pp,mp,dict(view=rv,gray=gray),dict(view=nv,gray=other),CONFIG)
        expected=old.pair_patch_cost(center,dp,dm,rv,nv,gray,other,3,prior_patch_depth=pp,mvs_patch_depth=mp,
                                    minimum_fraction=CONFIG['minimum_patch_fraction'],texture_std=CONFIG['texture_std'])
        np.testing.assert_allclose(result['costs'],expected['costs'],equal_nan=True)
        np.testing.assert_array_equal(result['common_count'],expected['common_count'])

    def test_profile_reuses_parent_numeric_model_and_missing_support(self):
        rv,nv=camera(),camera((1.,0.,0.)); rgb=texture(); gray=rgb@np.array([.299,.587,.114])
        c=np.array([[50.,40.],[60.,50.]]); dp=np.array([10.,10.]); dm=np.array([12.,12.])
        pp=np.full((2,49),10.); mp=np.full((2,49),12.); pp[1,0]=np.nan
        ref=dict(view=rv,gray=gray); neighbor=dict(view=nv,gray=gray)
        cfg=dict(CONFIG,profile_neighbors=2)
        depths,raw=dense.source_profiles(c,dp,dm,pp,mp,ref,[neighbor,neighbor],np.ones((2,2),bool),cfg)
        loader=object.__new__(Builder); loader.cfg=cfg
        expected=loader.profiles(c,dp,dm,pp,mp,ref,[neighbor,neighbor])
        np.testing.assert_allclose(depths,expected['depths'])
        np.testing.assert_allclose(raw,expected['per_neighbor_costs'],rtol=2e-6,atol=1e-8,equal_nan=True)
        self.assertTrue(np.isnan(raw[:,1]).all())


if __name__=='__main__': unittest.main()
