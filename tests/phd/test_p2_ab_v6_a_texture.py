import unittest
import numpy as np
from src.phd.p2_ab_v6.a_texture_profile import zncc_profiles


class TextureValidityTests(unittest.TestCase):
    def setUp(self):self.cfg=dict(minimum_patch_pixels=4,minimum_patch_std=.015)

    def test_wrong_flat_candidate_does_not_erase_matching_candidate(self):
        reference=np.array([[.2,.4,.6,.8]],np.float32)
        target=np.array([[[.5,.5,.5,.5],[.2,.4,.6,.8],[.8,.6,.4,.2]]],np.float32)
        cost,n,_=zncc_profiles(reference,target,np.ones((1,4),bool),self.cfg)
        self.assertTrue(np.isfinite(cost).all())
        np.testing.assert_allclose(cost,[[.5,0.,1.]],atol=1e-6)

    def test_all_target_offsets_flat_remain_unknown(self):
        reference=np.array([[.2,.4,.6,.8]],np.float32)
        target=np.full((1,3,4),.5,np.float32)
        cost,_,_=zncc_profiles(reference,target,np.ones((1,4),bool),self.cfg)
        self.assertTrue(np.isnan(cost).all())

    def test_flat_reference_remains_unknown(self):
        reference=np.full((1,4),.5,np.float32)
        target=np.array([[[.2,.4,.6,.8],[.8,.6,.4,.2]]],np.float32)
        cost,_,_=zncc_profiles(reference,target,np.ones((1,4),bool),self.cfg)
        self.assertTrue(np.isnan(cost).all())


if __name__=='__main__':unittest.main()
