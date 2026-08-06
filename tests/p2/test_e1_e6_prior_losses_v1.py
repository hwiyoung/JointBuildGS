from __future__ import annotations

import unittest

import torch

from src.stage2.external_als_prior import oriented_als_normal_loss, select_external_als_weight
from src.stage2.loss.data_fitting import l_depth_huber
from src.stage2.external_lod_prior import lod_plane_loss


class E1E6PriorLossTests(unittest.TestCase):
    def test_e4_e5_differ_only_by_building_weight_multiplier(self) -> None:
        base = torch.tensor([[1.0, 0.5]])
        wb = torch.tensor([[0.2, 1.0]])
        e4 = select_external_als_weight(base, wb, apply_building_weight=False)
        e5 = select_external_als_weight(base, wb, apply_building_weight=True)
        torch.testing.assert_close(e4, base)
        torch.testing.assert_close(e5, base * wb)

    def test_mvs_depth_huber_uses_metric_delta(self) -> None:
        predicted = torch.tensor([[0.0, 3.0]], requires_grad=True)
        target = torch.tensor([[1.0, 1.0]])
        loss = l_depth_huber(
            predicted,
            target,
            torch.ones((1, 2), dtype=torch.bool),
            delta_m=1.0,
        )
        self.assertAlmostEqual(float(loss.detach()), 1.0, places=6)
        loss.backward()
        self.assertTrue(torch.isfinite(predicted.grad).all())

    def test_als_normal_loss_is_signed(self) -> None:
        rendered = torch.tensor([[[0.0, 0.0, 1.0]]])
        prior = torch.tensor([[[0.0, 0.0, -1.0]]])
        loss, stats = oriented_als_normal_loss(
            rendered,
            prior,
            torch.ones((1, 1)),
            torch.ones((1, 1), dtype=torch.bool),
        )
        self.assertEqual(stats["valid_pixel_count"], 1)
        self.assertAlmostEqual(float(loss), 2.0, places=6)

    def test_als_zero_rendered_normal_remains_a_supervised_miss(self) -> None:
        loss, stats = oriented_als_normal_loss(
            torch.zeros((1, 1, 3)),
            torch.tensor([[[0.0, 0.0, -1.0]]]),
            torch.ones((1, 1)),
            torch.ones((1, 1), dtype=torch.bool),
        )
        self.assertEqual(stats["valid_pixel_count"], 1)
        self.assertAlmostEqual(float(loss), 1.0, places=6)

    def test_lod_plane_loss_accepts_matching_roof_plane(self) -> None:
        depth = torch.full((2, 2), 5.0, requires_grad=True)
        rendered_normal = torch.zeros((2, 2, 3))
        rendered_normal[..., 2] = 1.0
        plane_point = torch.zeros((2, 2, 3))
        plane_point[..., 2] = 5.0
        plane_normal = rendered_normal.clone()
        kind = torch.full((2, 2), 2, dtype=torch.int64)
        weight = torch.ones((2, 2))
        mask = torch.ones((2, 2), dtype=torch.bool)
        loss, stats = lod_plane_loss(
            depth,
            rendered_normal,
            plane_point,
            plane_normal,
            kind,
            weight,
            mask,
            torch.eye(3),
            wall_weight=0.3,
            roof_weight=0.1,
            max_distance_m=1.0,
            max_angle_deg=30.0,
        )
        self.assertEqual(stats["roof_pixel_count"], 4)
        self.assertAlmostEqual(float(loss.detach()), 0.0, places=6)
        loss.backward()
        self.assertTrue(torch.isfinite(depth.grad).all())

    def test_lod_plane_loss_rejects_normal_angle(self) -> None:
        depth = torch.full((1, 1), 5.0)
        rendered_normal = torch.tensor([[[1.0, 0.0, 0.0]]])
        plane_point = torch.tensor([[[0.0, 0.0, 5.0]]])
        plane_normal = torch.tensor([[[0.0, 0.0, 1.0]]])
        loss, stats = lod_plane_loss(
            depth,
            rendered_normal,
            plane_point,
            plane_normal,
            torch.tensor([[2]]),
            torch.ones((1, 1)),
            torch.ones((1, 1), dtype=torch.bool),
            torch.eye(3),
            wall_weight=0.3,
            roof_weight=0.1,
            max_distance_m=1.0,
            max_angle_deg=30.0,
        )
        self.assertEqual(stats["valid_pixel_count"], 0)
        self.assertEqual(float(loss), 0.0)


if __name__ == "__main__":
    unittest.main()
