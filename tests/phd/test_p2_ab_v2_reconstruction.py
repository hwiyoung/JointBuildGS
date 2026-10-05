"""Meaningful gauges, partial observability and projected nonzero-step checks."""
import json
from pathlib import Path
import unittest
import numpy as np
import torch
from src.phd.p2_ab_v2.reconstruction import StructuredGaussians, prepare_geometry, subdivide_seed


class TestV2Reconstruction(unittest.TestCase):
    def make_model(self, n=16):
        cfg=json.loads(Path("configs/phd/p2_ab_v2/b_native_v1.json").read_text())
        cfg["seed_voxel_m"]=0
        x,y=np.meshgrid(np.linspace(.1,.8,4),np.linspace(.1,.8,4))
        xyz=np.column_stack((x.ravel(),y.ravel(),np.full(16,3.)))[:n].astype(np.float32)
        normals=np.tile([0,0,1.],(n,1)).astype(np.float32)
        seed=prepare_geometry(xyz,normals,np.zeros(n,np.int64),np.arange(n),np.zeros(n,np.int64),cfg)
        return StructuredGaussians(seed,cfg,device="cpu"),seed

    def test_partial_observed_detail_has_zero_moments_and_nonzero_freedom(self):
        model,_=self.make_model()
        counts=np.full(16,5);counts[:4]=0;model.set_observations(counts)
        with torch.no_grad():model.detail.copy_(torch.randn_like(model.detail)*.1)
        detail=model.project_detail(model.detail)
        self.assertLess(float((model.H.T@detail).abs().max()),1e-5)
        self.assertEqual(float(detail[:4].abs().max()),0.)
        self.assertGreater(float(detail.norm()),.01)
        detail[7,2].backward()
        self.assertGreater(float(model.detail.grad.norm()),0.)

    def test_partial_observation_rotation_exact_bound(self):
        model,_=self.make_model(4)
        model.set_observations([4,4,0,0])
        model.cfg["structure_rotation_bound_deg"]=np.rad2deg(.1)
        with torch.no_grad():model.rotation[:2,0]=.4
        model.enforce_domain(True)
        self.assertLessEqual(float(model.coarse_rotation().norm(dim=1).max()),.100001)
        self.assertGreater(float(model.rotation[:2].norm()),.01)
        self.assertEqual(float(model.rotation[2:].abs().max()),0.)

    def test_joint_point_and_mean_rotation_bounds(self):
        model,_=self.make_model();model.set_observations(np.full(16,4))
        with torch.no_grad():model.rotation.copy_(torch.randn_like(model.rotation)*5)
        model.enforce_domain(True)
        self.assertLessEqual(float(model.coarse_rotation().norm(dim=1).max()),np.deg2rad(5)+1e-6)
        self.assertLessEqual(float(model.rotation.norm(dim=1).max()),np.deg2rad(35)+1e-6)

    def test_projection_retains_nonzero_detail_and_structure(self):
        model,seed=self.make_model();model.set_observations(np.full(16,4))
        with torch.no_grad():
            model.detail.copy_(torch.randn_like(model.detail)*.04)
            model.structure[0,0,2]=.2
        model.enforce_domain(True)
        self.assertLessEqual(float(model.coarse_displacement().norm(dim=1).max()),.150001)
        self.assertGreater(float(model.project_detail(model.detail).norm()),.01)
        state=model.state_arrays(seed)
        self.assertTrue(np.allclose(state["xyz"],model.means.detach().numpy()))
        self.assertTrue(np.all(np.isfinite(state["quats"])))
        self.assertEqual(state["scales"].shape,(16,3))

    def test_subdivision_is_parent_tangent_and_provenanced(self):
        model,seed=self.make_model()
        dense=subdivide_seed(seed,model.cfg)
        self.assertEqual(len(dense["xyz"]),4*len(seed["xyz"]))
        parent=dense["parent_id"]
        normal_offset=((dense["xyz"]-seed["xyz"][parent])*seed["normals"][parent]).sum(1)
        self.assertLess(float(np.abs(normal_offset).max()),1e-6)
        self.assertTrue(np.array_equal(dense["native_row"],seed["native_row"][parent]))


if __name__=="__main__":unittest.main()
