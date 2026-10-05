"""Meaningful bounded-optimizer and fixed-supervision controls, CPU Docker."""
import json
from pathlib import Path
import unittest
import numpy as np
import torch
from src.phd.source_selected_2dgs_v1 import optimization as o

CFG=json.loads((Path(__file__).resolve().parents[2]/'configs/phd/source_selected_2dgs_v1/experiment.json').read_text())['training']


def points():
    return dict(xyz=np.array([[0.,0.,1.],[2.,2.,2.]],np.float32),normal=np.array([[0.,0.,1.],[0.,0.,-1.]],np.float32),
        rgb=np.array([[.2,.3,.4],[.4,.5,.6]],np.float32),scale=np.array([.1,.2],np.float32),
        trainable_geometry=np.array([True,False]),stable_source_id=np.array([1,2]),source_kind=np.array([1,0]))


class OptimizationControls(unittest.TestCase):
    def test_normal_quaternions_cover_antipodal_and_arbitrary_normals(self):
        n=torch.tensor([[0.,0.,1.],[0.,0.,-1.],[.2,.5,-.3]])
        actual=o.quaternion_normals(o.normal_quaternions(n))
        torch.testing.assert_close(actual,torch.nn.functional.normalize(n,dim=-1),atol=1e-6,rtol=1e-6)

    def test_adam_updates_color_but_preserves_outside_geometry_exactly(self):
        model=o.SourceGaussians(points(),CFG,'cpu');optimizer=model.optimizer(CFG)
        original={name:p.detach().clone() for name,p in model.named_parameters()}
        for _ in range(4):
            optimizer.zero_grad();loss=sum((param-1).square().mean() for param in model.parameters());loss.backward();optimizer.step();model.constrain()
        for key in ('means','quats_raw','log_scales','opacity_raw'):
            self.assertTrue(torch.equal(getattr(model,key)[1],original[key][1]),key)
        self.assertFalse(torch.equal(model.rgb_raw[1],original['rgb_raw'][1]))
        self.assertTrue(model.invariants()['finite_parameters'])

    def test_center_motion_is_euclidean_bounded_not_axiswise(self):
        model=o.SourceGaussians(points(),CFG,'cpu')
        with torch.no_grad():model.means[0]+=torch.tensor([10.,10.,10.])
        model.constrain();shift=(model.means[0]-model.initial_means[0]).norm()
        self.assertAlmostEqual(float(shift),.25,places=6)
        self.assertTrue(model.invariants()['means'])

    def test_small_target_cannot_be_diluted_by_large_context(self):
        for n in (10,10000):
            value=torch.zeros(n);value[0]=1;target=torch.zeros(n,dtype=torch.bool);target[0]=True
            self.assertEqual(float(o.stratified_mean(value,target,~target,.5)),.5)
        value=torch.tensor([2.,2.]);empty=torch.zeros(2,dtype=torch.bool)
        self.assertEqual(float(o.stratified_mean(value,empty,~empty,.5)),2.)

    def test_projected_abstention_never_adds_depth_or_normal_targets(self):
        H=W=12;photo=torch.full((H,W,3),.3)
        pred=dict(rgb=photo.clone().requires_grad_(),depth=torch.ones((H,W),requires_grad=True),alpha=torch.full((H,W),.8,requires_grad=True),
            normal=torch.zeros((H,W,3)),normal_from_depth=torch.zeros((H,W,3)),distortion=torch.zeros((H,W)))
        pred['normal'][...,2]=1;pred['normal_from_depth'][...,2]=1
        a=dict(photo_mask=np.ones((H,W),bool),authority_mask=np.zeros((H,W),bool),target_mask=np.zeros((H,W),bool),
            depth_valid=np.ones((H,W),bool),normal_valid=np.ones((H,W),bool),projection_abstain_mask=np.zeros((H,W),bool),
            prior_depth=np.ones((H,W),np.float32),selected_depth=np.ones((H,W),np.float32),
            prior_normal=np.tile(np.array([0,0,1.],np.float32),(H,W,1)),selected_normal=np.tile(np.array([0,0,1.],np.float32),(H,W,1)))
        a['authority_mask'][2,2]=a['target_mask'][2,2]=True;a['projection_abstain_mask'][4,4]=True
        a['selected_depth'][2,2]=2
        _,terms,counts=o.objective(pred,photo,a,'source_selected',CFG)
        before=float(terms['source_depth_huber']);a['selected_depth'][4,4]=1000;a['selected_normal'][4,4]=[1,0,0]
        _,changed,counts2=o.objective(pred,photo,a,'source_selected',CFG)
        self.assertEqual(float(changed['source_depth_huber']),before)
        self.assertEqual(float(changed['source_normal']),float(terms['source_normal']))
        self.assertEqual(counts,counts2);self.assertEqual(counts['candidate_depth_pixels'],1)
        self.assertEqual(counts['context_depth_pixels'],H*W-2)


if __name__=='__main__':unittest.main()
