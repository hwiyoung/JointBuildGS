import unittest
import torch
from src.phd.p2_ab_v3.appearance import image_quality,residual_weights,weighted_rgb_l1,freeze_except_color


class AppearanceContract(unittest.TestCase):
    def test_detached_residual_emphasis_has_expected_gradient(self):
        p=torch.tensor([[[.1,.1,.1],[.8,.8,.8],[.5,.5,.5]]],requires_grad=True)
        target=torch.zeros_like(p);q=torch.tensor([[1.,1.,0.]])
        w,_=residual_weights(p,target,q)
        self.assertFalse(w.requires_grad)
        loss,_=weighted_rgb_l1(p,target,q);loss.backward()
        self.assertTrue(torch.allclose(p.grad,w[...,None].expand_as(p)/3))
        self.assertGreater(float(p.grad[0,1,0]),float(p.grad[0,0,0]))
        self.assertEqual(float(p.grad[0,2].abs().sum()),0.)

    def test_uniform_and_quality_scaling_invariance(self):
        p=torch.tensor([[[.2,.3,.4],[.6,.8,.9]]],requires_grad=True)
        target=torch.zeros_like(p);q=torch.tensor([[1.,.25]])
        l,_=weighted_rgb_l1(p,target,q,gain=0)
        expected=((p-target).abs().mean(-1)*q).sum()/q.sum()
        self.assertTrue(torch.allclose(l,expected))
        a,_=weighted_rgb_l1(p,target,q);b,_=weighted_rgb_l1(p,target,7*q)
        self.assertTrue(torch.allclose(a,b))

    def test_quality_is_common_not_geometry_permission(self):
        target=torch.tensor([[[1.,1.,1.],[.2,.3,.4],[0.,0.,0.]]])
        q,clipped=image_quality(target,torch.tensor([[True,True,False]]))
        self.assertTrue(torch.equal(q,torch.tensor([[.25,1.,0.]])))
        self.assertTrue(torch.equal(clipped,torch.tensor([[True,False,False]])))

    def test_color_optimizer_cannot_update_geometry(self):
        model=torch.nn.Module()
        model.register_parameter("xyz",torch.nn.Parameter(torch.tensor([.3])))
        model.register_parameter("opacity",torch.nn.Parameter(torch.tensor([.8])))
        model.register_parameter("sh0",torch.nn.Parameter(torch.tensor([.1])))
        opt=torch.optim.SGD(freeze_except_color(model),lr=.1)
        before={k:p.detach().clone() for k,p in model.named_parameters()}
        for _ in range(3):
            opt.zero_grad();out=model.sh0*model.opacity+model.xyz;out.square().sum().backward();opt.step()
        self.assertTrue(torch.equal(model.xyz,before["xyz"]))
        self.assertTrue(torch.equal(model.opacity,before["opacity"]))
        self.assertIsNone(model.xyz.grad);self.assertIsNone(model.opacity.grad)
        self.assertFalse(torch.equal(model.sh0,before["sh0"]))

    def test_empty_or_nonfinite_fails(self):
        p=torch.ones(1,2,3);t=torch.zeros_like(p)
        with self.assertRaises(ValueError):weighted_rgb_l1(p,t,torch.zeros(1,2))
        p[0,0,0]=float("nan")
        with self.assertRaises(ValueError):weighted_rgb_l1(p,t,torch.ones(1,2))


if __name__=="__main__":unittest.main()
