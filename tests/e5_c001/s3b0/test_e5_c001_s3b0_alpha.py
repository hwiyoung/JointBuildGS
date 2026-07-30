#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

import numpy as np


REPO = Path(__file__).resolve().parents[3]
SCRIPT_DIR = REPO / "scripts/e5_c001/s3b0"
sys.path.insert(0, str(SCRIPT_DIR))
SCRIPT = SCRIPT_DIR / "e5_c001_s3b0_alpha.py"
SPEC = importlib.util.spec_from_file_location("e5_c001_s3b0_alpha", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
alpha = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(alpha)


class S3B0AlphaTest(unittest.TestCase):
    def test_classification_rules(self) -> None:
        self.assertEqual(
            alpha.classify(
                {"anchor_band_count": 0, "above_anchor_count": 4, "below_anchor_count": 0},
                {"anchor_band_count": 0},
            ),
            "밀림",
        )
        self.assertEqual(
            alpha.classify(
                {"anchor_band_count": 0, "above_anchor_count": 0, "below_anchor_count": 7},
                {"anchor_band_count": 0},
            ),
            "소멸",
        )
        self.assertEqual(
            alpha.classify(
                {"anchor_band_count": 2, "above_anchor_count": 0, "below_anchor_count": 0},
                {"anchor_band_count": 0},
            ),
            "판독_미달",
        )
        self.assertEqual(
            alpha.classify(
                {"anchor_band_count": 2, "above_anchor_count": 0, "below_anchor_count": 0},
                {"anchor_band_count": 1},
            ),
            "잔존",
        )

    def test_payload_match_is_order_independent(self) -> None:
        left = np.asarray([[1.0, 2.0, 3.0], [0.0, 2.0, 4.0]])
        right = left[::-1].copy()
        self.assertTrue(alpha.payload_match(left, right))
        right[0, 2] += 0.1
        self.assertFalse(alpha.payload_match(left, right))


if __name__ == "__main__":
    unittest.main()
