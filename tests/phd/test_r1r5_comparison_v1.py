"""Verify the intervention preserves outside-pixel gradient scale and masks only prior."""
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import torch

P=Path('/repo/scripts/phd/r1r5_comparison_v1/intervention.py')
spec=importlib.util.spec_from_file_location('intervention',P);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

class LocalPriorTests(unittest.TestCase):
    def setUp(self):
        m.INSIDE_MULTIPLIER=0
    def native(self,p,t,**kw):
        p=p.squeeze(0);v=torch.isfinite(p)&torch.isfinite(t)&(t>0)
        return (p[v]-t[v]).abs().mean()
    def test_only_selected_prior_gradients_removed_without_renormalization(self):
        p=torch.tensor([[[4.,5.,6.,8.]]],requires_grad=True);t=torch.tensor([[2.,2.,2.,float('nan')]])
        m.BRANCH='local_prior0';m.MASKS={'camera':torch.tensor([[True,False,False,True]])};m.SEEN={'camera'}
        baseline=self.native(p,t);g0=torch.autograd.grad(baseline,p,retain_graph=True)[0]
        changed=m.prior_loss('camera',8001,self.native,p,t);g=torch.autograd.grad(changed,p)[0]
        self.assertEqual(g[0,0,0].item(),0);self.assertTrue(torch.equal(g[:,:,1:3],g0[:,:,1:3]))
        self.assertAlmostEqual(changed.item(),7/3,places=6);self.assertEqual(g[0,0,3].item(),0)
    def test_anchor_unlisted_camera_and_other_branches_keep_native(self):
        p=torch.tensor([[[4.,5.]]],requires_grad=True);t=torch.tensor([[2.,2.]])
        m.MASKS={'camera':torch.tensor([[True,False]])};native=self.native(p,t)
        for branch,camera,iteration in [('mvs','camera',8001),('da3','camera',8001),('local_prior0','camera',8000),('local_prior0','other',8001)]:
            m.BRANCH=branch;self.assertTrue(torch.equal(m.prior_loss(camera,iteration,self.native,p,t),native))
    def test_keep_control_matches_native_loss_and_gradient(self):
        p=torch.tensor([[[4.,5.,6.]]],requires_grad=True);t=torch.tensor([[2.,2.,2.]])
        m.BRANCH='local_prior0';m.INSIDE_MULTIPLIER=1
        m.MASKS={'camera':torch.tensor([[True,False,True]])};m.SEEN={'camera'}
        native=self.native(p,t);expected=torch.autograd.grad(native,p,retain_graph=True)[0]
        actual=m.prior_loss('camera',8001,self.native,p,t)
        self.assertTrue(torch.equal(actual,native))
        self.assertTrue(torch.equal(torch.autograd.grad(actual,p)[0],expected))

if __name__=='__main__':unittest.main()
