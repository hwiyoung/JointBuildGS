#!/usr/bin/env python3
"""Unit tests for first-wave MVS seed opacity control."""
from __future__ import annotations

import unittest

import numpy as np

from src.stage2.seed_control import apply_mvs_seed_init_opacity


class PilotSeedControlTest(unittest.TestCase):
    def test_legacy_none_keeps_implicit_initialization(self) -> None:
        self.assertIsNone(
            apply_mvs_seed_init_opacity(
                3,
                np.asarray([False, True, True], dtype=np.bool_),
                None,
                None,
            )
        )

    def test_only_mvs_rows_change_from_point_one_to_point_two_five(self) -> None:
        result = apply_mvs_seed_init_opacity(
            4,
            np.asarray([False, True, False, True], dtype=np.bool_),
            None,
            0.25,
        )
        np.testing.assert_allclose(result, [0.10, 0.25, 0.10, 0.25])

    def test_existing_semantic_seed_opacity_is_preserved(self) -> None:
        result = apply_mvs_seed_init_opacity(
            3,
            np.asarray([False, False, True], dtype=np.bool_),
            np.asarray([0.10, 0.40, 0.10], dtype=np.float32),
            0.25,
        )
        np.testing.assert_allclose(result, [0.10, 0.40, 0.25])

    def test_invalid_or_missing_lineage_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            apply_mvs_seed_init_opacity(2, None, None, 0.25)
        with self.assertRaises(ValueError):
            apply_mvs_seed_init_opacity(
                2,
                np.asarray([False, False], dtype=np.bool_),
                None,
                0.25,
            )


if __name__ == "__main__":
    unittest.main()
