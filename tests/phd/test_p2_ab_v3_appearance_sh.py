import unittest
import torch
from src.phd.p2_ab_v3.appearance_sh import freeze_except_color
from gsplat.cuda._torch_impl import _eval_sh_bases_fast


class SHCapacityTest(unittest.TestCase):
    def test_zero_higher_coefficients_preserve_sh0_and_receive_gradient(self):
        directions=torch.tensor([[.2,.3,.9327379],[-.3,.4,.8660254]],dtype=torch.float32)
        directions=directions/directions.norm(dim=-1,keepdim=True)
        sh0=torch.tensor([[[.1,.2,.3]]],requires_grad=True)
        rest=torch.zeros((1,15,3),requires_grad=True)
        bases=_eval_sh_bases_fast(16,directions)
        rgb=(bases[:,:,None]*torch.cat((sh0,rest),1)).sum(1)+.5
        expected=(bases[:,:1,None]*sh0).sum(1)+.5
        self.assertTrue(torch.equal(rgb,expected))
        rgb.square().sum().backward()
        self.assertTrue(torch.isfinite(rest.grad).all())
        self.assertGreater(float(rest.grad.norm()),0)

    def test_only_color_blocks_train(self):
        model=torch.nn.Module()
        for name in ["geometry","sh0","sh_rest"]:model.register_parameter(name,torch.nn.Parameter(torch.ones(2)))
        params=freeze_except_color(model)
        self.assertEqual(len(params),2)
        self.assertFalse(model.geometry.requires_grad)
        self.assertTrue(model.sh_rest.requires_grad)


if __name__=="__main__":unittest.main()
