#!/usr/bin/env python3
"""Regression tests for exact outside-invariant footprint photo masking."""
from __future__ import annotations

import unittest

import torch

from src.stage2.loss.data_fitting import l_photo, masked_ssim


class PilotMaskedPhotoTest(unittest.TestCase):
    def setUp(self) -> None:
        generator = torch.Generator().manual_seed(20260721)
        self.prediction = torch.rand((17, 19, 3), generator=generator)
        self.target = torch.rand((17, 19, 3), generator=generator)
        self.mask = torch.zeros((17, 19), dtype=torch.bool)
        self.mask[4:14, 5:16] = True
        self.mask[8:10, 9:12] = False

    def test_outside_mutation_cannot_change_masked_photo_value(self) -> None:
        baseline = l_photo(self.prediction, self.target, mask=self.mask)
        changed_prediction = self.prediction.clone()
        changed_target = self.target.clone()
        changed_prediction[~self.mask] = 1.0e6
        changed_target[~self.mask] = -1.0e6
        changed = l_photo(changed_prediction, changed_target, mask=self.mask)
        self.assertTrue(torch.equal(baseline, changed))

    def test_outside_prediction_gradient_is_exactly_zero(self) -> None:
        prediction = self.prediction.clone().requires_grad_(True)
        loss = l_photo(prediction, self.target, mask=self.mask)
        loss.backward()
        self.assertTrue(
            torch.equal(
                prediction.grad[~self.mask],
                torch.zeros_like(prediction.grad[~self.mask]),
            )
        )
        self.assertGreater(float(prediction.grad[self.mask].abs().sum()), 0.0)

    def test_legacy_unmasked_path_is_unchanged_by_optional_argument(self) -> None:
        implicit = l_photo(self.prediction, self.target, lam=0.2)
        explicit = l_photo(self.prediction, self.target, lam=0.2, mask=None)
        self.assertTrue(torch.equal(implicit, explicit))

    def test_empty_or_misaligned_masks_fail(self) -> None:
        with self.assertRaisesRegex(ValueError, "empty"):
            masked_ssim(
                self.prediction,
                self.target,
                torch.zeros_like(self.mask),
            )
        with self.assertRaisesRegex(ValueError, "aligned"):
            l_photo(
                self.prediction,
                self.target,
                mask=torch.ones((4, 5), dtype=torch.bool),
            )


if __name__ == "__main__":
    unittest.main()
