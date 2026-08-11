import math
import unittest

import torch

from src.stage2.loss.data_fitting import l_nc_official_2dgs
from src.stage2.renderer import _depth_to_normal
from src.stage2.train import _official_2dgs_exponential_lr


class Official2DGSNormalLossTest(unittest.TestCase):
    def test_matches_reference_full_image_formula(self):
        rendered = torch.tensor(
            [[[0.5, 0.0, 0.0], [0.0, 0.25, 0.0]]],
            dtype=torch.float32,
            requires_grad=True,
        )
        surface = torch.tensor(
            [[[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]]], dtype=torch.float32
        )
        alpha = torch.tensor([[0.5, 0.25]], dtype=torch.float32, requires_grad=True)
        actual = l_nc_official_2dgs(rendered, surface, alpha)
        expected = torch.tensor((1.0 - 0.25 + 1.0 - 0.0625) / 2.0)
        self.assertTrue(torch.equal(actual, expected))
        actual.backward()
        self.assertIsNone(alpha.grad)

    def test_rejects_shape_mismatch(self):
        with self.assertRaisesRegex(ValueError, "alpha must be HxW"):
            l_nc_official_2dgs(
                torch.zeros(2, 3, 3),
                torch.zeros(2, 3, 3),
                torch.zeros(2, 2),
            )


class Official2DGSMeansLearningRateTest(unittest.TestCase):
    def test_log_linear_endpoints_and_midpoint(self):
        initial = 0.04
        final = 0.0004
        self.assertAlmostEqual(
            _official_2dgs_exponential_lr(
                0,
                lr_init=initial,
                lr_final=final,
                delay_mult=0.01,
                max_steps=30000,
            ),
            initial,
            places=15,
        )
        midpoint = _official_2dgs_exponential_lr(
            15000,
            lr_init=initial,
            lr_final=final,
            delay_mult=0.01,
            max_steps=30000,
        )
        self.assertAlmostEqual(midpoint, math.sqrt(initial * final), places=12)
        self.assertAlmostEqual(
            _official_2dgs_exponential_lr(
                30000,
                lr_init=initial,
                lr_final=final,
                delay_mult=0.01,
                max_steps=30000,
            ),
            final,
            places=15,
        )

    def test_clamps_after_max_steps(self):
        self.assertAlmostEqual(
            _official_2dgs_exponential_lr(
                40000,
                lr_init=0.04,
                lr_final=0.0004,
                delay_mult=0.01,
                max_steps=30000,
            ),
            0.0004,
            places=15,
        )


class SurfaceDepthNormalTest(unittest.TestCase):
    def test_unbatched_depth_is_replicate_padded_to_input_shape(self):
        depth = torch.full((4, 5), 3.0)
        intrinsics = torch.tensor(
            [[10.0, 0.0, 2.0], [0.0, 10.0, 1.5], [0.0, 0.0, 1.0]]
        )
        normal = _depth_to_normal(depth, intrinsics, torch.eye(4))
        self.assertEqual(normal.shape, (4, 5, 3))
        self.assertTrue(torch.isfinite(normal).all())
        self.assertTrue(torch.equal(normal[-1], normal[-2]))
        self.assertTrue(torch.equal(normal[:, -1], normal[:, -2]))


if __name__ == "__main__":
    unittest.main()
