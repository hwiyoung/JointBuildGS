from __future__ import annotations

import unittest

import torch
import yaml

from scripts.p2.c4_existing_als_v1.prepare_prior import CONFIG_PATH, validate_matched_control
from src.stage2.external_als_prior import (
    combine_confidence_gates,
    current_consistency_attenuation,
    robust_als_depth_loss,
    sign_invariant_als_normal_loss,
)


class ExternalAlsPriorTest(unittest.TestCase):
    def test_c4_keeps_exact_c3_control(self) -> None:
        config = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
        receipt = validate_matched_control(config)
        self.assertTrue(receipt["same_seed"])
        self.assertTrue(receipt["same_initialization"])
        self.assertTrue(receipt["same_iteration_count"])
        self.assertIsNone(config["scientific_verdict"])

    def test_robust_depth_has_nonzero_gradient(self) -> None:
        rendered = torch.tensor([[2.0, 8.0]], requires_grad=True)
        prior = torch.tensor([[1.0, 1.0]])
        confidence = torch.tensor([[1.0, 0.5]])
        mask = torch.ones((1, 2), dtype=torch.bool)
        loss, stats = robust_als_depth_loss(rendered, prior, confidence, mask, huber_delta_m=1.0)
        loss.backward()
        self.assertGreater(float(rendered.grad.abs().sum()), 0.0)
        self.assertEqual(stats["valid_pixel_count"], 2)

    def test_normal_is_sign_invariant(self) -> None:
        rendered = torch.tensor([[[0.0, 0.0, 1.0]]], requires_grad=True)
        prior = torch.tensor([[[0.0, 0.0, -1.0]]])
        confidence = torch.ones((1, 1))
        mask = torch.ones((1, 1), dtype=torch.bool)
        loss, _ = sign_invariant_als_normal_loss(rendered, prior, confidence, mask)
        self.assertAlmostEqual(float(loss), 0.0, places=6)

    def test_conflict_and_five_gates_only_attenuate(self) -> None:
        residual = torch.tensor([0.0, 2.0, 10.0])
        attenuation = current_consistency_attenuation(residual, 2.0)
        self.assertTrue(torch.all(attenuation <= 1.0))
        one = torch.ones(3)
        combined = combine_confidence_gates(one, one * 0.8, one * 0.7, one, attenuation)
        self.assertTrue(torch.all(combined <= 0.8 * 0.7 + 1e-7))


if __name__ == "__main__":
    unittest.main()
