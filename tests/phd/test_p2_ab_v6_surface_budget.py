import unittest
import numpy as np
import torch
from src.phd.p2_ab_v6.surface_budget import allowable_interval, Evidence


class SurfaceBudgetTest(unittest.TestCase):
    def test_membership_is_not_use_error_bound(self):
        lo,hi=allowable_interval(-.1,.1,.15)
        self.assertAlmostEqual(lo,-.05);self.assertAlmostEqual(hi,.05)
        self.assertGreater(max(abs(.1-(-.1)),abs(.1-.1)),.15)

    def test_infeasible_wide_interval(self):
        lo,hi=allowable_interval(-.3,.3,.15)
        self.assertGreater(lo,hi)

    def test_dynamic_rejects_conflicting_groups(self):
        handoff=dict(seed_id=np.array([2]),anchor_id=np.array([0]),observable=np.array([True]),
            initial_eligible=np.array([True]),observation_low_m=np.array([-.05]),
            observation_high_m=np.array([.05]),allowed_low_m=np.array([-.1]),
            allowed_high_m=np.array([.1]),target_m=np.array([0.]))
        profiles=dict(offsets_m=np.array([-.1,0.,.1]),cost=np.array([[[1.,.5,0.]],[[0.,.5,1.]]]))
        evidence=Evidence(handoff,profiles,dict(seed_id=np.array([2])),device="cpu")
        self.assertFalse(bool(evidence.dynamic_accept(torch.tensor([0.]),torch.tensor([.05]))[0]))
        profiles["cost"][1]=profiles["cost"][0]
        evidence=Evidence(handoff,profiles,dict(seed_id=np.array([2])),device="cpu")
        self.assertTrue(bool(evidence.dynamic_accept(torch.tensor([0.]),torch.tensor([.05]))[0]))

    def test_backtrack_does_not_accept_incomplete_correction(self):
        handoff=dict(seed_id=np.array([2]),anchor_id=np.array([0]),observable=np.array([True]),
            initial_eligible=np.array([False]),observation_low_m=np.array([.15]),
            observation_high_m=np.array([.25]),allowed_low_m=np.array([.1]),
            allowed_high_m=np.array([.3]),target_m=np.array([.2]))
        profiles=dict(offsets_m=np.array([0.,.15,.3]),cost=np.array([[[1.,.5,0.]],[[1.,.5,0.]]]))
        evidence=Evidence(handoff,profiles,dict(seed_id=np.array([2])),device="cpu")
        result=evidence.retain_jointly_valid_changes(torch.tensor([0.]),torch.tensor([.05]))
        self.assertEqual(float(result[0]),0.)
        # Unresolved initial geometry remains outside the interval, not accepted.
        self.assertLess(float(result[0]),float(evidence.allowed_low_m[0]))

    def test_backtrack_rechecks_nonmonotone_image_cost(self):
        handoff=dict(seed_id=np.array([2]),anchor_id=np.array([0]),observable=np.array([True]),
            initial_eligible=np.array([True]),observation_low_m=np.array([0.]),
            observation_high_m=np.array([.3]),allowed_low_m=np.array([0.]),
            allowed_high_m=np.array([.3]),target_m=np.array([.15]))
        profiles=dict(offsets_m=np.array([0.,.15,.3]),cost=np.array([[[.4,.8,.1]],[[.4,.8,.1]]]))
        evidence=Evidence(handoff,profiles,dict(seed_id=np.array([2])),device="cpu")
        self.assertTrue(bool(evidence.dynamic_accept(torch.tensor([0.]),torch.tensor([.3]))[0]))
        result=evidence.retain_jointly_valid_changes(torch.tensor([0.]),torch.tensor([.15]))
        self.assertEqual(float(result[0]),0.)


if __name__=="__main__":unittest.main()
