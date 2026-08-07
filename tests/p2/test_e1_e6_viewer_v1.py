from __future__ import annotations

import unittest

import numpy as np
from shapely.geometry import Polygon

from scripts.p2.e1_e6_techdev_v1.build_viewer import WORLD_SHIFT, change_label, local_rings
from scripts.p2.e1_e6_techdev_v1.extract_real_change_candidates import (
    AOI,
    RESOLUTION_M,
    cell_mask_geometry,
)


class E1E6ViewerChangeOverlayTests(unittest.TestCase):
    def test_change_types_have_distinct_labels_and_colors(self) -> None:
        new_label, new_color = change_label({"simulates": "NEW_CONSTRUCTION"})
        demolished_label, demolished_color = change_label({"simulates": "DEMOLITION"})
        height_label, height_color = change_label({"operation": "SCALE_PRIOR_HEIGHT", "scale": 1.3})

        self.assertIn("신축", new_label)
        self.assertIn("철거", demolished_label)
        self.assertIn("높이 증가", height_label)
        self.assertEqual(len({new_color, demolished_color, height_color}), 3)

    def test_footprint_ring_is_shifted_to_viewer_coordinates(self) -> None:
        x, y = WORLD_SHIFT[:2]
        polygon = Polygon([(x, y), (x + 2, y), (x + 2, y + 3), (x, y + 3)])

        rings = local_rings(polygon)

        self.assertEqual(len(rings), 1)
        self.assertEqual(rings[0][0], [0.0, 0.0])
        self.assertEqual(rings[0][2], [2.0, 3.0])
        self.assertEqual(rings[0][0], rings[0][-1])

    def test_real_change_geometry_is_changed_cells_not_whole_footprint(self) -> None:
        mask = np.zeros((4, 5), dtype=bool)
        mask[1, 1:3] = True
        footprint = Polygon([
            (AOI[0], AOI[1]),
            (AOI[0] + 5 * RESOLUTION_M, AOI[1]),
            (AOI[0] + 5 * RESOLUTION_M, AOI[1] + 4 * RESOLUTION_M),
            (AOI[0], AOI[1] + 4 * RESOLUTION_M),
        ])

        geometry = cell_mask_geometry(mask, footprint)

        self.assertAlmostEqual(geometry.area, 2 * RESOLUTION_M**2)
        self.assertLess(geometry.area, footprint.area)


if __name__ == "__main__":
    unittest.main()
