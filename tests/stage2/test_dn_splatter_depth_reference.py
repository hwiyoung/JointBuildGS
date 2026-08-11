from __future__ import annotations

import torch
import unittest

from src.stage2.loss.depth_reference import dn_splatter_edge_aware_log_l1


class DNSplatterDepthReferenceTests(unittest.TestCase):
    def test_matches_pinned_reduction(self) -> None:
        pred = torch.tensor([[2.0, 4.0, 8.0], [1.0, 3.0, 7.0]])
        gt = torch.tensor([[1.0, 2.0, 4.0], [1.0, 2.0, 5.0]])
        rgb = torch.tensor(
            [
                [[0.0, 0.0, 0.0], [1.0, 1.0, 1.0], [1.0, 1.0, 1.0]],
                [[0.0, 0.0, 0.0], [0.0, 0.0, 0.0], [1.0, 1.0, 1.0]],
            ]
        )
        mask = torch.ones_like(gt, dtype=torch.bool)
        log_l1 = torch.log1p(torch.abs(pred - gt))
        weight_x = torch.exp(-torch.mean(torch.abs(rgb[:, :-1] - rgb[:, 1:]), -1))
        weight_y = torch.exp(-torch.mean(torch.abs(rgb[:-1] - rgb[1:]), -1))
        expected = (weight_x * log_l1[:, :-1]).mean() + (
            weight_y * log_l1[:-1]
        ).mean()
        actual = dn_splatter_edge_aware_log_l1(pred, gt, rgb, mask)
        torch.testing.assert_close(actual, expected)

    def test_applies_depth_tolerance(self) -> None:
        pred = torch.ones((2, 2))
        gt = torch.tensor([[0.1, 1.0], [1.0, 1.0]])
        rgb = torch.zeros((2, 2, 3))
        mask = torch.ones_like(gt, dtype=torch.bool)
        actual = dn_splatter_edge_aware_log_l1(pred, gt, rgb, mask)
        self.assertTrue(torch.isfinite(actual))
        self.assertEqual(actual.item(), 0.0)
