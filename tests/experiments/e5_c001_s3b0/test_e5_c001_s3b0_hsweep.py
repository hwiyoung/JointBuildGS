#!/usr/bin/env python3
from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np


REPO = Path(__file__).resolve().parents[3]
SCRIPT_DIR = REPO / "scripts/e5_c001/s3b0"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import e5_c001_s3b0_hsweep as hsweep  # noqa: E402


class HeightSweepTests(unittest.TestCase):
    def test_regular_grid_includes_endpoints(self) -> None:
        values = hsweep.regular_grid(2.0, 4.0, 0.5)
        np.testing.assert_allclose(values, [2.0, 2.5, 3.0, 3.5, 4.0])

    def test_peak_tie_rule_prefers_parent_then_lower(self) -> None:
        heights = np.asarray([0.0, 1.0, 2.0, 3.0])
        scores = np.asarray([0.0, 2.0, 2.0, 0.0])
        index, status = hsweep.select_peak(heights, scores, parent_centre=1.5)
        self.assertEqual(index, 1)
        self.assertEqual(status, "tied_positive_peak")

    def test_fit_anchor_plane(self) -> None:
        anchors = np.asarray(
            [[0.0, 0.0, 1.0], [1.0, 0.0, 3.0], [0.0, 1.0, 4.0], [1.0, 1.0, 6.0]]
        )
        plane, rms = hsweep.fit_anchor_plane(anchors)
        np.testing.assert_allclose(plane, [2.0, 3.0, 1.0], atol=1e-12)
        self.assertLess(rms, 1e-12)


if __name__ == "__main__":
    unittest.main()
