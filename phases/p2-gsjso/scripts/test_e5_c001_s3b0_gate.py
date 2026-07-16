#!/usr/bin/env python3
from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import e5_c001_s3b0_gate as gate  # noqa: E402


class GateScoreTests(unittest.TestCase):
    def test_texture_metrics_uses_mask_and_t11_threshold(self) -> None:
        image = np.zeros((5, 5, 3), dtype=np.uint8)
        image[:, 3:] = 255
        mask = np.zeros((5, 5), dtype=bool)
        mask[:, :2] = True
        result = gate.texture_metrics(image, mask, 0.02137)
        self.assertEqual(result["texture_valid_pixels"], 10)
        self.assertGreaterEqual(result["low_gradient_pixel_ratio"], 0.5)
        self.assertGreaterEqual(result["gradient_p10"], 0.0)

    def test_project_support_counts_nearest_target_pixels(self) -> None:
        target = np.zeros((10, 10), dtype=bool)
        target[4:7, 4:7] = True
        view = {
            "R_w2c": np.eye(3).tolist(),
            "t_w2c": [0.0, 0.0, 0.0],
            "K_crop": [[1.0, 0.0, 5.0], [0.0, 1.0, 5.0], [0.0, 0.0, 1.0]],
        }
        points = np.asarray([[0.0, 0.0, 1.0], [1.0, 0.0, 1.0], [20.0, 0.0, 1.0]])
        result = gate.project_support(points, view, target)
        self.assertEqual(result["candidate_point_count"], 3)
        self.assertEqual(result["in_frame_point_count"], 2)
        self.assertEqual(result["target_mask_point_count"], 2)
        self.assertEqual(result["target_mask_unique_pixel_count"], 2)
        self.assertEqual(result["target_mask_yield"], 1.0)


if __name__ == "__main__":
    unittest.main()
