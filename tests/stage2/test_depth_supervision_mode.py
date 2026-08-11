import unittest

import torch

from src.stage2.train import (
    _depth_supervision_prediction,
    _validate_depth_supervision_mode,
)


class DepthSupervisionModeTest(unittest.TestCase):
    def test_expected_selects_legacy_expected_depth_tensor(self):
        expected = torch.tensor([[1.0]])
        median = torch.tensor([[2.0]])

        selected = _depth_supervision_prediction(
            {"depth": expected, "depth_median": median}, "expected"
        )

        self.assertIs(selected, expected)

    def test_median_selects_median_depth_tensor(self):
        expected = torch.tensor([[1.0]])
        median = torch.tensor([[2.0]])

        selected = _depth_supervision_prediction(
            {"depth": expected, "depth_median": median}, "median"
        )

        self.assertIs(selected, median)

    def test_mode_is_case_normalized(self):
        self.assertEqual(_validate_depth_supervision_mode("MEDIAN"), "median")

    def test_surface_intersection_uses_hit_and_expected_no_hit_fallback(self):
        expected = torch.tensor([[1.0, 2.0]])
        surface = torch.tensor([[10.0, 20.0]])
        selected = _depth_supervision_prediction(
            {
                "depth": expected,
                "depth_surface_intersection": surface,
                "depth_surface_intersection_hit": torch.tensor([[True, False]]),
            },
            "surface_intersection",
        )
        self.assertTrue(torch.equal(selected, torch.tensor([[10.0, 2.0]])))

    def test_invalid_mode_fails_closed(self):
        with self.assertRaisesRegex(
            ValueError,
            "depth_supervision_mode must be expected\\|median\\|surface_intersection",
        ):
            _validate_depth_supervision_mode("not_a_mode")

    def test_missing_selected_tensor_fails_closed(self):
        with self.assertRaisesRegex(KeyError, "depth_median"):
            _depth_supervision_prediction(
                {"depth": torch.tensor([[1.0]])}, "median"
            )

    def test_surface_missing_hit_mask_fails_closed(self):
        with self.assertRaisesRegex(
            KeyError, "depth_surface_intersection_hit"
        ):
            _depth_supervision_prediction(
                {
                    "depth": torch.tensor([[1.0]]),
                    "depth_surface_intersection": torch.tensor([[2.0]]),
                },
                "surface_intersection",
            )


if __name__ == "__main__":
    unittest.main()
