"""G6: valid_pixel_count normalization must keep uniform attenuation absolute."""
from __future__ import annotations

import unittest

import torch

from src.stage2.external_als_prior import robust_als_depth_loss, sign_invariant_als_normal_loss


class DepthNormalizationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.rendered = torch.full((4, 4), 10.0)
        self.prior = torch.full((4, 4), 12.5)
        self.mask = torch.ones((4, 4), dtype=torch.bool)

    def test_legacy_confidence_sum_cancels_uniform_attenuation(self) -> None:
        strong, _ = robust_als_depth_loss(
            self.rendered, self.prior, torch.full((4, 4), 1.0), self.mask, huber_delta_m=1.0
        )
        weak, _ = robust_als_depth_loss(
            self.rendered, self.prior, torch.full((4, 4), 0.001), self.mask, huber_delta_m=1.0
        )
        self.assertAlmostEqual(float(strong), float(weak), places=5)

    def test_valid_pixel_count_keeps_attenuation_absolute(self) -> None:
        strong, _ = robust_als_depth_loss(
            self.rendered, self.prior, torch.full((4, 4), 1.0), self.mask,
            huber_delta_m=1.0, normalization="valid_pixel_count",
        )
        weak, _ = robust_als_depth_loss(
            self.rendered, self.prior, torch.full((4, 4), 0.001), self.mask,
            huber_delta_m=1.0, normalization="valid_pixel_count",
        )
        self.assertAlmostEqual(float(weak) / float(strong), 0.001, places=5)

    def test_full_confidence_matches_between_normalizations(self) -> None:
        legacy, _ = robust_als_depth_loss(
            self.rendered, self.prior, torch.ones((4, 4)), self.mask, huber_delta_m=1.0
        )
        absolute, _ = robust_als_depth_loss(
            self.rendered, self.prior, torch.ones((4, 4)), self.mask,
            huber_delta_m=1.0, normalization="valid_pixel_count",
        )
        self.assertAlmostEqual(float(legacy), float(absolute), places=6)

    def test_unknown_normalization_rejected(self) -> None:
        with self.assertRaises(ValueError):
            robust_als_depth_loss(
                self.rendered, self.prior, torch.ones((4, 4)), self.mask,
                huber_delta_m=1.0, normalization="mean",
            )


class NormalNormalizationTest(unittest.TestCase):
    def test_valid_pixel_count_keeps_attenuation_absolute(self) -> None:
        rendered = torch.zeros((2, 2, 3))
        rendered[..., 0] = 1.0
        prior = torch.zeros((2, 2, 3))
        prior[..., 2] = 1.0
        mask = torch.ones((2, 2), dtype=torch.bool)
        strong, _ = sign_invariant_als_normal_loss(
            rendered, prior, torch.full((2, 2), 1.0), mask, normalization="valid_pixel_count"
        )
        weak, _ = sign_invariant_als_normal_loss(
            rendered, prior, torch.full((2, 2), 0.25), mask, normalization="valid_pixel_count"
        )
        self.assertAlmostEqual(float(weak) / float(strong), 0.25, places=5)


if __name__ == "__main__":
    unittest.main()
