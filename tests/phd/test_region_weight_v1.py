"""Mask-to-camera binding and actual multi-camera gradient behavior on CPU."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
import numpy as np
import torch
from src.phd.region_weight_v1.loss import Controller,load_masks,sha256


class RegionWeightTests(unittest.TestCase):
    def setUp(self):
        self.temp=TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        self.views={name:dict(height=3,width=4) for name in ['A','B','C']}
        self.labels={'A':np.array([[1,1,2,2],[1,1,2,2],[5,5,5,5]],np.uint8),
                     'B':np.full((3,4),5,np.uint8),'C':np.full((3,4),3,np.uint8)}
        rows=[]
        for name,labels in self.labels.items():
            path=self.root/(name+'.npz');np.savez(path,region_id=labels,valid=np.ones((3,4),bool))
            rows.append(dict(camera=name,path=path.name,sha256=sha256(path),r1_pixels=int((labels==1).sum()),used_pixels=int(np.isin(labels,[1,2,3]).sum())))
        self.path=self.root/'manifest.json';self.path.write_text(json.dumps(dict(region='P2',binding_sha256='mvs',views=rows)))
        self.args=SimpleNamespace(dynamic_depth_weight=False,lambda_da_depth=.05,lambda_lod_anchor=.005,
            use_confidence=False,use_scale_invariant=False,jbgs_release_protection=False,stage_switch_iter=8000,
            jbgs_resume_full='checkpoint',freeze_onlybldg=True,protect_bldg=True)
        self.mvs=SimpleNamespace(views=self.views,binding_sha='mvs')

    def controller(self,alpha):
        out=self.root/f'alpha{alpha}';out.mkdir()
        env=dict(JBGS_MVS_PGSR_MODE='mvs',JBGS_MVS_REGION='P2',JBGS_REGION_WEIGHT_ALPHA=str(alpha),
            JBGS_REGION_WEIGHT_MASK=str(self.path),JBGS_REGION_WEIGHT_MASK_SHA256=sha256(self.path))
        return Controller(out,self.args,self.mvs,env),out

    def test_all_cameras_follow_their_own_masks_and_empty_support_is_zero(self):
        for alpha in [0,1,4]:
            controller,out=self.controller(alpha)
            for iteration,camera in enumerate(['A','B','C'],8001):
                prediction=torch.full((1,3,4),12.,requires_grad=True);target=torch.full((3,4),10.)
                native=(prediction.squeeze(0)-target).abs().mean()
                loss=controller.apply(prediction,target,native,camera=camera,iteration=iteration);loss.backward()
                labels=self.labels[camera];weights=np.where(labels==1,alpha,np.where(np.isin(labels,[2,3]),1,0))
                expected=torch.tensor(weights,dtype=torch.float32)/12
                torch.testing.assert_close(prediction.grad.squeeze(0),expected,rtol=0,atol=0)
            self.assertEqual(len((out/'region_weight_trace.jsonl').read_text().splitlines()),3)
            self.assertEqual(json.loads((out/'region_weight_first_algebra.json').read_text())['status'],'PASS')

    def test_manifest_membership_and_raster_shape_are_bound(self):
        with self.assertRaises(ValueError):load_masks(self.path,sha256(self.path),{'A':self.views['A']})
        wrong=dict(self.views);wrong['A']=dict(height=4,width=3)
        with self.assertRaises(ValueError):load_masks(self.path,sha256(self.path),wrong)

    def test_changed_mask_bytes_fail_closed(self):
        with (self.root/'A.npz').open('ab') as f:f.write(b'tamper')
        with self.assertRaises(ValueError):load_masks(self.path,sha256(self.path),self.views)

    def test_empty_native_depth_produces_differentiable_zero(self):
        controller,_=self.controller(4)
        p=torch.full((1,3,4),12.,requires_grad=True);target=torch.zeros((3,4))
        value=controller.apply(p,target,torch.tensor(0.),camera='B',iteration=8001);value.backward()
        self.assertEqual(float(value),0);self.assertTrue((p.grad==0).all())

    def test_no_rng_draws_or_camera_resampling(self):
        before=torch.random.get_rng_state().clone();controller,_=self.controller(1)
        self.assertTrue(torch.equal(before,torch.random.get_rng_state()))
        with self.assertRaises(ValueError):controller.apply(torch.ones((1,3,4)),torch.ones((3,4)),torch.tensor(0.),camera='A',iteration=8002)

    def test_native_controls_cannot_silently_change(self):
        self.args.dynamic_depth_weight=True
        with self.assertRaises(ValueError):self.controller(1)


if __name__=='__main__':unittest.main()
