import unittest
import numpy as np
from src.phd.p2_ab_v6.a_observational_envelope import observational_envelopes,map_same_patch


class EnvelopeTests(unittest.TestCase):
    def setUp(self):
        self.x=np.arange(-.3,.301,.05)
        self.cfg=dict(maximum_best_cost=.45,basin_cost_slack=.03,maximum_group_minimum_separation_m=.1,normal_use_error_epsilon_m=.15)

    def test_use_error_interval_is_not_feasible_location_interval(self):
        c=np.ones((1,2,len(self.x)),np.float32)
        c[:,:,7]=.01
        r=observational_envelopes(c,self.x,self.cfg)
        self.assertTrue(r["observable"][0])
        self.assertAlmostEqual(float(r["observation_low_m"][0]),.025,places=6)
        self.assertAlmostEqual(float(r["allowed_low_m"][0]),-.075,places=6)
        self.assertAlmostEqual(float(r["allowed_high_m"][0]),.175,places=6)

    def test_boundary_and_disagreeing_groups_do_not_authorize(self):
        c=np.ones((2,2,len(self.x)),np.float32);c[0,:,0]=.01;c[1,0,3]=.01;c[1,1,9]=.01
        r=observational_envelopes(c,self.x,self.cfg)
        self.assertFalse(r["observable"].any())
        self.assertEqual(r["reason_code"].tolist(),[3,5])

    def test_mapping_cannot_cross_native_patch(self):
        s=dict(xyz=np.array([[0.,0,0],[.1,0,0],[.2,0,0]]),native_patch_id=np.array([1,2,1]),normals=np.tile([0.,0,1],(3,1)))
        ids,d=map_same_patch(s,np.array([0]),1.,.97)
        self.assertEqual(ids.tolist(),[0,-1,0])


if __name__=="__main__":unittest.main()
