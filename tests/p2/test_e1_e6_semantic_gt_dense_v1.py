from __future__ import annotations

import unittest

import numpy as np

from scripts.p2.e1_e6_techdev_v1.make_semantic_gt_dense import dense_surfel_raster
from scripts.p2.e1_e6_techdev_v1.make_semantic_rgb_sam_v2 import preserve_uncertain_boundaries


class DenseSemanticRasterTests(unittest.TestCase):
    def test_empty_projection_remains_invalid(self) -> None:
        labels = np.zeros((9, 9), dtype=np.uint8)
        depths = np.full((9, 9), np.inf, dtype=np.float32)
        radii = np.zeros((9, 9), dtype=np.uint8)

        output, mask, stats = dense_surfel_raster(labels, depths, radii)

        self.assertFalse(np.any(output))
        self.assertFalse(np.any(mask))
        self.assertEqual(stats["dense_valid_pixels"], 0)

    def test_single_surfel_expands_only_within_its_radius(self) -> None:
        labels = np.zeros((9, 9), dtype=np.uint8)
        depths = np.full((9, 9), np.inf, dtype=np.float32)
        radii = np.zeros((9, 9), dtype=np.uint8)
        labels[4, 4] = 1
        depths[4, 4] = 10.0
        radii[4, 4] = 2

        output, mask, stats = dense_surfel_raster(labels, depths, radii)

        self.assertEqual(stats["sparse_valid_pixels"], 1)
        self.assertEqual(stats["dense_valid_pixels"], 13)
        self.assertEqual(output[4, 4], 1)
        self.assertEqual(mask[4, 4], 255)
        self.assertEqual(mask[4, 7], 0)

    def test_class_transition_has_ignore_band(self) -> None:
        labels = np.zeros((15, 15), dtype=np.uint8)
        depths = np.full((15, 15), np.inf, dtype=np.float32)
        radii = np.zeros((15, 15), dtype=np.uint8)
        labels[7, 4] = 1
        labels[7, 10] = 2
        depths[7, 4] = depths[7, 10] = 10.0
        radii[7, 4] = radii[7, 10] = 5

        output, mask, stats = dense_surfel_raster(labels, depths, radii)

        self.assertGreater(stats["boundary_ignore_pixels"], 0)
        self.assertFalse(np.any(mask[:, 6:9]))
        self.assertFalse(np.any(output[:, 6:9]))

    def test_rgb_sam_boundary_filter_never_removes_geometry_seed(self) -> None:
        labels = np.ones((7, 7), dtype=np.uint8)
        labels[:, 4:] = 2
        original_valid = np.zeros((7, 7), dtype=bool)
        original_valid[3, 3] = True
        original_valid[3, 4] = True

        filtered = preserve_uncertain_boundaries(labels, original_valid)

        self.assertEqual(filtered[3, 3], 1)
        self.assertEqual(filtered[3, 4], 2)
        self.assertEqual(filtered[2, 3], 0)
        self.assertEqual(filtered[2, 4], 0)


if __name__ == "__main__":
    unittest.main()
