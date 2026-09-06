"""Handoff authority, gauge, and surface disappearance regression checks."""
import unittest

import numpy as np
import torch

from src.phd.p2_ab_v1.reconstruction import (
    SurfaceGaussians, representative_rows, surface_guard, validate_handoff,
)


class ReconstructionContractTests(unittest.TestCase):
    def test_point_support_cannot_authorize_surface(self):
        row = {"strict_current_use_action": "PRIOR", "conditional_action": "PRIOR",
               "support_scope": "sampled_points"}
        self.assertTrue(validate_handoff(row, certified=False))
        with self.assertRaisesRegex(ValueError, "Sample support"):
            validate_handoff(row, certified=True)

    def test_abstain_does_not_make_geometry(self):
        self.assertFalse(validate_handoff({"strict_current_use_action": "ABSTAIN"}, certified=True))

    def test_fusion_requires_tested_geometry(self):
        with self.assertRaisesRegex(ValueError, "exact tested"):
            validate_handoff({"conditional_action": "FUSION"}, certified=False)

    def test_representation_does_not_merge_source_groups(self):
        xyz = np.array([[0., 0., 0.], [.01, .01, .01], [0., 0., 0.]])
        self.assertEqual(representative_rows(xyz, np.array([0, 0, 1]), .1).tolist(), [0, 2])

    def test_detail_cannot_reencode_affine_structure(self):
        xyz = np.array([[x, y, 0.] for x in range(3) for y in range(3)])
        normals = np.tile([0., 0., 1.], (len(xyz), 1))
        model = SurfaceGaussians(xyz, normals, np.full(len(xyz), .1),
                                 np.full_like(xyz, .5), np.zeros(len(xyz)), device="cpu")
        with torch.no_grad():
            model.detail.copy_(torch.arange(len(xyz), dtype=torch.float32).square())
        d = model.normal_displacements()
        self.assertLess(float(torch.abs(model.designs[0].T @ d).max()), 1e-3)
        (d.square().sum()).backward()
        self.assertTrue(torch.isfinite(model.detail.grad).all())

    def test_disappearance_never_reports_zero_error_pass(self):
        initial = {"alpha": torch.ones(3, 3), "depth": torch.ones(3, 3)}
        removed = {"alpha": torch.zeros(3, 3), "depth": torch.ones(3, 3)}
        result = surface_guard(initial, removed, max_depth_m=1.)
        self.assertFalse(result["pass"])
        self.assertEqual(result["removed_pixels"], 9)
        self.assertIsNone(result["max_depth_displacement_m"])

    def test_boundary_intrusion_rejected_even_same_depth(self):
        initial = {"alpha": torch.tensor([[1., 0.]]), "depth": torch.ones(1, 2)}
        proposed = {"alpha": torch.ones(1, 2), "depth": torch.ones(1, 2)}
        result = surface_guard(initial, proposed, max_depth_m=0.)
        self.assertFalse(result["pass"])
        self.assertEqual(result["added_pixels"], 1)

    def test_depth_budget_is_maximum_not_average(self):
        initial = {"alpha": torch.ones(1, 100), "depth": torch.ones(1, 100)}
        depth = torch.ones(1, 100)
        depth[0, 50] = 1.06
        result = surface_guard(initial, {"alpha": initial["alpha"], "depth": depth}, max_depth_m=.05)
        self.assertFalse(result["pass"])


if __name__ == "__main__":
    unittest.main()
