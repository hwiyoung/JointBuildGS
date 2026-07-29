"""CPU tests for the standalone pilot planarity losses.

Run in the repository container:
    python -m unittest tests/experiments/pilot_1wave/test_pilot_1wave_planarity.py
"""
from __future__ import annotations

import unittest

import torch

from src.stage2.loss.planarity import (
    audit_2dgs_flattening_invariant,
    calibrate_forward_only_plane_weight,
    local_rendered_depth_coplanarity,
    region_rendered_depth_coplanarity,
)


def _intrinsics(height: int, width: int, *, dtype=torch.float64) -> torch.Tensor:
    return torch.tensor(
        [
            [120.0, 0.0, (width - 1) / 2.0],
            [0.0, 125.0, (height - 1) / 2.0],
            [0.0, 0.0, 1.0],
        ],
        dtype=dtype,
    )


def _ray_plane_depth(
    height: int,
    width: int,
    K: torch.Tensor,
    *,
    offset: float,
    slope_x: float,
    slope_y: float,
) -> torch.Tensor:
    """Depth satisfying z = offset + slope_x*x + slope_y*y."""

    yy, xx = torch.meshgrid(
        torch.arange(height, dtype=K.dtype),
        torch.arange(width, dtype=K.dtype),
        indexing="ij",
    )
    ray_x = (xx - K[0, 2]) / K[0, 0]
    ray_y = (yy - K[1, 2]) / K[1, 1]
    return offset / (1.0 - slope_x * ray_x - slope_y * ray_y)


class PilotPlanarityTest(unittest.TestCase):
    def test_exact_plane_is_numerically_zero(self):
        height, width = 25, 27
        K = _intrinsics(height, width)
        depth = _ray_plane_depth(
            height,
            width,
            K,
            offset=7.0,
            slope_x=0.12,
            slope_y=-0.08,
        ).requires_grad_(True)
        result = local_rendered_depth_coplanarity(
            depth,
            K,
            window_size=7,
            stride=3,
            min_points=30,
            max_depth_range=2.0,
        )
        self.assertGreater(result.plane_count, 0)
        self.assertLess(float(result.loss), 1.0e-12)
        result.loss.backward()
        self.assertIsNotNone(depth.grad)
        self.assertTrue(bool(torch.isfinite(depth.grad).all()))

    def test_outlier_has_positive_loss_and_gradient(self):
        height = width = 25
        K = _intrinsics(height, width)
        depth = _ray_plane_depth(
            height,
            width,
            K,
            offset=6.0,
            slope_x=0.05,
            slope_y=0.03,
        )
        depth[12, 12] += 0.25
        depth.requires_grad_(True)
        result = local_rendered_depth_coplanarity(
            depth,
            K,
            window_size=7,
            stride=2,
            min_points=30,
            max_depth_range=1.0,
        )
        self.assertGreater(float(result.loss), 0.0)
        result.loss.backward()
        self.assertGreater(float(depth.grad[12, 12].abs()), 0.0)

    def test_separated_planes_are_not_collapsed_by_local_soft_loss(self):
        height, width = 21, 31
        K = _intrinsics(height, width)
        depth = torch.full((height, width), 5.0, dtype=torch.float64)
        depth[:, width // 2 :] = 8.0
        depth.requires_grad_(True)
        result = local_rendered_depth_coplanarity(
            depth,
            K,
            window_size=7,
            stride=1,
            min_points=30,
            max_depth_range=0.5,
        )
        self.assertGreater(result.plane_count, 0)
        self.assertGreater(result.diagnostics["rejected_depth_edge_count"], 0)
        self.assertLess(float(result.loss), 1.0e-12)
        result.loss.backward()
        self.assertLess(float(depth.grad.abs().max()), 1.0e-10)

    def test_empty_mask_returns_graph_connected_zero(self):
        height = width = 15
        K = _intrinsics(height, width)
        depth = torch.full(
            (height, width), 5.0, dtype=torch.float64, requires_grad=True
        )
        result = local_rendered_depth_coplanarity(
            depth,
            K,
            valid_mask=torch.zeros_like(depth, dtype=torch.bool),
            window_size=5,
            stride=2,
            min_points=10,
        )
        self.assertEqual(result.plane_count, 0)
        self.assertEqual(float(result.loss), 0.0)
        self.assertTrue(result.loss.requires_grad)
        result.loss.backward()
        self.assertTrue(torch.equal(depth.grad, torch.zeros_like(depth)))

    def test_region_label_map_keeps_two_planes_independent(self):
        height, width = 20, 24
        K = _intrinsics(height, width)
        left = _ray_plane_depth(
            height, width, K, offset=5.0, slope_x=0.06, slope_y=0.02
        )
        right = _ray_plane_depth(
            height, width, K, offset=8.0, slope_x=-0.04, slope_y=0.03
        )
        depth = torch.where(
            torch.arange(width)[None, :] < width // 2,
            left,
            right,
        ).requires_grad_(True)
        region_ids = torch.ones((height, width), dtype=torch.int32)
        region_ids[:, width // 2 :] = 2
        result = region_rendered_depth_coplanarity(
            depth, K, region_ids, min_points=50
        )
        self.assertEqual(result.plane_count, 2)
        self.assertLess(float(result.loss), 1.0e-12)

    def test_boolean_region_masks_and_overlap_validation(self):
        height = width = 16
        K = _intrinsics(height, width)
        depth = torch.full(
            (height, width), 6.0, dtype=torch.float64, requires_grad=True
        )
        masks = torch.zeros((2, height, width), dtype=torch.bool)
        masks[0, :, :8] = True
        masks[1, :, 8:] = True
        result = region_rendered_depth_coplanarity(
            depth, K, masks, min_points=20
        )
        self.assertEqual(result.plane_count, 2)
        self.assertLess(float(result.loss), 1.0e-12)

        masks[1, :, 7] = True
        with self.assertRaisesRegex(ValueError, "must not overlap"):
            region_rendered_depth_coplanarity(depth, K, masks, min_points=20)

    def test_flattening_is_audit_only_and_calibration_is_stateless(self):
        scales = torch.ones((8, 3), dtype=torch.float32)
        scales[:, 2] = 1.0e-6
        audit = audit_2dgs_flattening_invariant(scales)
        self.assertTrue(audit.passed)
        self.assertFalse(audit.contributes_to_loss)
        self.assertAlmostEqual(
            calibrate_forward_only_plane_weight(2.0, 4.0, target_ratio=1.0),
            0.5,
        )
        with self.assertRaisesRegex(ValueError, "strictly positive"):
            calibrate_forward_only_plane_weight(2.0, 0.0)


if __name__ == "__main__":
    unittest.main()
