#!/usr/bin/env python3
"""Focused CPU tests for RGB init, eval depth PNG, and distortion scheduling."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import imageio.v2 as imageio
import numpy as np
import torch

from src.stage2.pointcloud_io import (
    read_init_pointcloud,
    read_init_pointcloud_with_rgb,
)
from src.stage2.train import (
    _aligned_depth_prior_l1,
    _encode_expected_depth_png,
    _resolve_init_pointcloud_rgb,
    _save_expected_depth_png,
    _scheduled_weight,
    _signed_normal_prior_loss,
)


class InitPointCloudRgbTest(unittest.TestCase):
    def test_xyz_only_npz_keeps_legacy_api_and_scene_mean_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "xyz_only.npz"
            xyz64 = np.asarray(
                [[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]],
                dtype=np.float64,
            )
            np.savez(path, P_local=xyz64)

            legacy_xyz = read_init_pointcloud(str(path))
            rich_xyz, supplied_rgb = read_init_pointcloud_with_rgb(str(path))
            self.assertEqual(legacy_xyz.dtype, np.float32)
            self.assertTrue(legacy_xyz.flags.c_contiguous)
            np.testing.assert_array_equal(legacy_xyz, rich_xyz)
            self.assertIsNone(supplied_rgb)

            fallback = _resolve_init_pointcloud_rgb(
                rich_xyz,
                supplied_rgb,
                np.asarray([0.25, 0.5, 0.75], dtype=np.float32),
            )
            np.testing.assert_array_equal(
                fallback,
                np.asarray(
                    [[0.25, 0.5, 0.75], [0.25, 0.5, 0.75]],
                    dtype=np.float32,
                ),
            )

    def test_npz_uint8_rgb_is_normalized_and_preserved(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "colored.npz"
            xyz = np.asarray(
                [[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]],
                dtype=np.float32,
            )
            rgb8 = np.asarray([[255, 0, 64], [10, 20, 30]], dtype=np.uint8)
            # An object-valued surface-seed metadata field is deliberately
            # present: the generic init loader must neither parse nor use it.
            np.savez(
                path,
                xyz=xyz,
                rgb=rgb8,
                sem=np.asarray([1, 2], dtype=np.int64),
                metadata_json=np.asarray({"not": "init RGB"}, dtype=object),
            )

            loaded_xyz, loaded_rgb = read_init_pointcloud_with_rgb(str(path))
            self.assertIsNotNone(loaded_rgb)
            assert loaded_rgb is not None
            np.testing.assert_array_equal(loaded_xyz, xyz)
            np.testing.assert_allclose(loaded_rgb, rgb8.astype(np.float32) / 255.0)

            preserved = _resolve_init_pointcloud_rgb(
                loaded_xyz,
                loaded_rgb,
                np.asarray([0.9, 0.9, 0.9], dtype=np.float32),
            )
            np.testing.assert_array_equal(preserved, loaded_rgb)

    def test_colored_ply_path_preserves_open3d_colors(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "seed.ply"
            path.write_text(
                "\n".join(
                    [
                        "ply",
                        "format ascii 1.0",
                        "element vertex 2",
                        "property float x",
                        "property float y",
                        "property float z",
                        "property uchar red",
                        "property uchar green",
                        "property uchar blue",
                        "end_header",
                        "1 2 3 255 0 64",
                        "4 5 6 10 20 30",
                        "",
                    ]
                ),
                encoding="ascii",
            )
            loaded_xyz, loaded_rgb = read_init_pointcloud_with_rgb(str(path))
        np.testing.assert_array_equal(
            loaded_xyz,
            np.asarray([[1, 2, 3], [4, 5, 6]], dtype=np.float32),
        )
        np.testing.assert_allclose(
            loaded_rgb,
            np.asarray([[255, 0, 64], [10, 20, 30]], dtype=np.float32) / 255.0,
        )

    def test_malformed_coordinates_and_rgb_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bad_xyz = root / "bad_xyz.npz"
            np.savez(bad_xyz, xyz=np.ones((2, 2), dtype=np.float32))
            with self.assertRaisesRegex(ValueError, r"shape \(N,>=3\)"):
                read_init_pointcloud_with_rgb(str(bad_xyz))

            bad_rgb_shape = root / "bad_rgb_shape.npz"
            np.savez(
                bad_rgb_shape,
                xyz=np.ones((2, 3), dtype=np.float32),
                rgb=np.ones((1, 3), dtype=np.float32),
            )
            with self.assertRaisesRegex(ValueError, "RGB must have shape"):
                read_init_pointcloud_with_rgb(str(bad_rgb_shape))

            bad_rgb_range = root / "bad_rgb_range.npz"
            np.savez(
                bad_rgb_range,
                xyz=np.ones((2, 3), dtype=np.float32),
                rgb=np.full((2, 3), 255.0, dtype=np.float32),
            )
            with self.assertRaisesRegex(ValueError, r"must lie in \[0,1\]"):
                read_init_pointcloud_with_rgb(str(bad_rgb_range))


class ExpectedDepthPngTest(unittest.TestCase):
    def test_encoding_is_deterministic_and_masks_nonfinite_nonpositive(self) -> None:
        depth = np.asarray(
            [[np.nan, -1.0, 1.0], [2.0, np.inf, 3.0]],
            dtype=np.float32,
        )
        first, receipt = _encode_expected_depth_png(depth)
        second, second_receipt = _encode_expected_depth_png(depth)
        np.testing.assert_array_equal(first, second)
        self.assertEqual(receipt, second_receipt)
        np.testing.assert_array_equal(first == 0, ~np.isfinite(depth) | (depth <= 0))
        self.assertEqual(receipt["valid_pixel_count"], 3)
        self.assertEqual(receipt["depth_min_m"], 1.0)
        self.assertEqual(receipt["depth_max_m"], 3.0)
        self.assertEqual(int(first[0, 2]), 1)
        self.assertEqual(int(first[1, 2]), 65535)

    def test_png_has_adjacent_metric_scale_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "it030000_v0_depth.png"
            receipt_path = _save_expected_depth_png(
                np.asarray([[10.0, 11.0]], dtype=np.float32),
                path,
                context={"iteration": 30000, "view_name": "view.jpg"},
            )
            self.assertTrue(path.is_file())
            self.assertTrue(receipt_path.is_file())
            self.assertEqual(imageio.imread(path).dtype, np.uint16)
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
            self.assertEqual(receipt["iteration"], 30000)
            self.assertEqual(receipt["unit"], "m")
            self.assertEqual(receipt["decode_offset_m"], 10.0)
            self.assertGreater(receipt["decode_scale_m_per_code_step"], 0.0)
            self.assertEqual(len(receipt["png_sha256"]), 64)


class DistortionScheduleTest(unittest.TestCase):
    def test_default_schedule_reproduces_constant_weight(self) -> None:
        for iteration in (0, 1, 14999, 30000):
            self.assertEqual(
                _scheduled_weight(100.0, iteration, 0, "constant", 0),
                100.0,
            )

    def test_warmup_defers_surface_regularization_to_stage_two(self) -> None:
        self.assertEqual(
            _scheduled_weight(100.0, 14999, 15000, "constant", 0),
            0.0,
        )
        self.assertEqual(
            _scheduled_weight(100.0, 15000, 15000, "constant", 0),
            100.0,
        )

    def test_zero_weight_ablation_stays_exactly_zero_under_exp_decay(self) -> None:
        for iteration in (0, 1, 14999, 29999):
            self.assertEqual(
                _scheduled_weight(
                    0.0,
                    iteration,
                    0,
                    "exp_decay",
                    30000,
                    final_weight=0.0,
                ),
                0.0,
            )

    def test_nc_schedule_can_activate_only_in_phase_two(self) -> None:
        self.assertEqual(
            _scheduled_weight(0.05, 14999, 15000, "constant", 0),
            0.0,
        )
        self.assertEqual(
            _scheduled_weight(0.05, 15000, 15000, "constant", 0),
            0.05,
        )

    def test_prior_stays_constant_then_decays_over_phase_two(self) -> None:
        kwargs = {
            "base_weight": 0.5,
            "warmup": 15000,
            "schedule": "constant_then_exp_decay",
            "ramp_steps": 15000,
            "final_weight": 0.05,
        }
        self.assertEqual(_scheduled_weight(it=14999, **kwargs), 0.5)
        self.assertAlmostEqual(_scheduled_weight(it=15000, **kwargs), 0.5)
        self.assertAlmostEqual(_scheduled_weight(it=29999, **kwargs), 0.05)
        midpoint = _scheduled_weight(it=22499, **kwargs)
        self.assertGreater(midpoint, 0.05)
        self.assertLess(midpoint, 0.5)


class AlignedDepthPriorTest(unittest.TestCase):
    def test_lsq_alpha_and_loss_use_only_masked_valid_pixels(self) -> None:
        prediction = torch.tensor(
            [[1.0, 3.0], [999.0, float("nan")]],
            dtype=torch.float64,
            requires_grad=True,
        )
        prior = torch.tensor(
            [[2.0, 5.0], [1.0e9, 1.0e9]],
            dtype=torch.float64,
        )
        mask = torch.tensor([[True, True], [False, False]])

        loss, alpha, valid_count = _aligned_depth_prior_l1(
            prediction,
            prior,
            mask,
        )

        # (1*2 + 3*5) / (1^2 + 3^2) = 1.7; residual mean=(.3+.1)/2=.2.
        self.assertAlmostEqual(float(alpha), 1.7, places=12)
        self.assertAlmostEqual(float(loss), 0.2, places=12)
        self.assertEqual(valid_count, 2)
        self.assertFalse(alpha.requires_grad)
        loss.backward()
        self.assertEqual(float(prediction.grad[1, 0]), 0.0)
        self.assertEqual(float(prediction.grad[1, 1]), 0.0)

    def test_exact_scale_match_has_zero_mask_normalized_loss(self) -> None:
        prediction = torch.tensor([[1.0, 2.0], [10.0, 20.0]])
        prior = torch.tensor([[2.0, 4.0], [999.0, 999.0]])
        mask = torch.tensor([[True, True], [False, False]])
        loss, alpha, valid_count = _aligned_depth_prior_l1(
            prediction,
            prior,
            mask,
            detach_scale=False,
        )
        self.assertEqual(float(alpha), 2.0)
        self.assertEqual(float(loss), 0.0)
        self.assertEqual(valid_count, 2)

    def test_empty_or_wrong_dtype_mask_fails_closed(self) -> None:
        prediction = torch.ones((2, 2))
        prior = torch.ones((2, 2))
        with self.assertRaisesRegex(ValueError, "mask must be bool"):
            _aligned_depth_prior_l1(
                prediction,
                prior,
                torch.ones((2, 2)),
            )
        with self.assertRaisesRegex(ValueError, "at least one valid"):
            _aligned_depth_prior_l1(
                prediction,
                prior,
                torch.zeros((2, 2), dtype=torch.bool),
            )
        invalid_prior = prior.clone()
        invalid_prior[0, 0] = float("nan")
        with self.assertRaisesRegex(ValueError, "finite positive prior depths"):
            _aligned_depth_prior_l1(
                prediction,
                invalid_prior,
                torch.tensor([[True, False], [False, False]]),
            )

    def test_zero_rendered_depth_keeps_exact_mask_denominator(self) -> None:
        prediction = torch.tensor([[1.0, 0.0]], requires_grad=True)
        prior = torch.tensor([[2.0, 3.0]])
        mask = torch.tensor([[True, True]])
        loss, alpha, valid_count = _aligned_depth_prior_l1(
            prediction,
            prior,
            mask,
        )
        self.assertEqual(float(alpha), 2.0)
        self.assertEqual(float(loss), 1.5)
        self.assertEqual(valid_count, 2)


class SignedNormalPriorTest(unittest.TestCase):
    def test_signed_orientation_penalizes_opposite_normal_by_two(self) -> None:
        prediction = torch.tensor([[[0.0, 0.0, 3.0], [0.0, 2.0, 0.0]]])
        prior = torch.tensor([[[0.0, 0.0, -4.0], [0.0, 5.0, 0.0]]])
        mask = torch.tensor([[True, True]])
        loss, count = _signed_normal_prior_loss(prediction, prior, mask)
        # Per-pixel errors are 2 (opposite) and 0 (same), hence mean 1.
        self.assertEqual(float(loss), 1.0)
        self.assertEqual(count, 2)

    def test_mask_is_exact_and_outside_values_have_no_gradient(self) -> None:
        prediction = torch.tensor(
            [[[1.0, 0.0, 0.0], [float("nan"), 0.0, 0.0]]],
            requires_grad=True,
        )
        prior = torch.tensor(
            [[[0.0, 1.0, 0.0], [float("nan"), 0.0, 0.0]]]
        )
        mask = torch.tensor([[True, False]])
        loss, count = _signed_normal_prior_loss(prediction, prior, mask)
        self.assertEqual(float(loss), 1.0)
        self.assertEqual(count, 1)
        loss.backward()
        self.assertTrue(torch.equal(prediction.grad[0, 1], torch.zeros(3)))

    def test_zero_rendered_normal_is_a_masked_miss(self) -> None:
        normals = torch.tensor([[[1.0, 0.0, 0.0]]])
        loss, count = _signed_normal_prior_loss(
            torch.zeros_like(normals),
            normals,
            torch.tensor([[True]]),
        )
        self.assertEqual(float(loss), 1.0)
        self.assertEqual(count, 1)

    def test_invalid_or_empty_masked_normal_fails_closed(self) -> None:
        normals = torch.tensor([[[1.0, 0.0, 0.0]]])
        with self.assertRaisesRegex(ValueError, "at least one masked pixel"):
            _signed_normal_prior_loss(
                normals,
                normals,
                torch.tensor([[False]]),
            )
        with self.assertRaisesRegex(ValueError, "nonzero prior normals"):
            _signed_normal_prior_loss(
                normals,
                torch.zeros_like(normals),
                torch.tensor([[True]]),
            )


if __name__ == "__main__":
    unittest.main()
