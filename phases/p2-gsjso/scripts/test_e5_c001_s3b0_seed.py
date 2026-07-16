#!/usr/bin/env python3
from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import e5_c001_s3b0_seed as seed  # noqa: E402


class VirtualSeedTests(unittest.TestCase):
    def test_robust_view_normal_orients_positive_z(self) -> None:
        values = np.asarray(
            [[0.0, 0.0, -1.0], [0.1, 0.0, 0.995], [-0.1, 0.0, 0.995]],
            dtype=np.float64,
        )
        normal = seed.robust_view_normal(values)
        self.assertGreater(normal[2], 0.99)
        self.assertAlmostEqual(float(np.linalg.norm(normal)), 1.0, places=12)

    def test_plane_through_anchor(self) -> None:
        plane = seed.plane_through_anchor((0.2, -0.1), np.asarray([3.0, 4.0]), 7.0)
        predicted = plane[0] * 3.0 + plane[1] * 4.0 + plane[2]
        self.assertAlmostEqual(float(predicted), 7.0, places=12)

    def test_nearest_distance(self) -> None:
        value = seed.nearest_distance(
            np.asarray([[0.0, 0.0], [3.0, 4.0]]),
            np.asarray([[0.0, 0.0]]),
        )
        np.testing.assert_allclose(value, [0.0, 5.0])

    def test_plane_from_five_equal_weight_anchors(self) -> None:
        anchors = np.asarray(
            [
                [0.5, 0.5, 3.5],
                [0.0, 0.0, 1.0],
                [1.0, 0.0, 3.0],
                [0.0, 1.0, 4.0],
                [1.0, 1.0, 6.0],
            ]
        )
        plane = seed.plane_from_xyz(anchors)
        np.testing.assert_allclose(plane, [2.0, 3.0, 1.0], atol=1e-12)


if __name__ == "__main__":
    unittest.main()
