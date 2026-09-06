import unittest
import numpy as np
from src.phd.p2_ab_v6.a_multipair_profiles import aggregate_pairs


class MultiPairTests(unittest.TestCase):
    def test_group_profile_uses_median_not_lowest_pair(self):
        costs=np.array([[[.01,.01],[.4,.5],[.6,.7]]],np.float32)
        profile,n=aggregate_pairs(costs,2)
        np.testing.assert_allclose(profile,[[.4,.5]])
        self.assertEqual(n.tolist(),[3])

    def test_incomplete_pair_cannot_supply_favorable_offset(self):
        costs=np.array([[[.1,.2],[.01,np.nan],[.3,.4]]],np.float32)
        profile,n=aggregate_pairs(costs,2)
        np.testing.assert_allclose(profile,[[.2,.3]])
        self.assertEqual(n.tolist(),[2])
        profile,_=aggregate_pairs(costs,3)
        self.assertTrue(np.isnan(profile).all())


if __name__=='__main__':unittest.main()
