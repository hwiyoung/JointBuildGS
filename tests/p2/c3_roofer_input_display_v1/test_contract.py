import unittest

import numpy as np
from shapely.geometry import Polygon

from scripts.p2.c3_roofer_input_display_v1.render import _support, load_config, validate_config
from scripts.p2.c3_roofer_input_display_v1.render_complete import (
    _height_colors,
    _normal_colors,
    load_config as load_complete_config,
    validate_config as validate_complete_config,
)
from scripts.p2.c3_roofer_input_display_v1.render_12row import (
    load_config as load_12row_config,
    validate_config as validate_12row_config,
)


class SupportTest(unittest.TestCase):
    def test_config_is_bounded_and_null_verdict(self):
        config = load_config()
        validate_config(config)
        self.assertEqual(config["display"]["new_roofer_input_panel_count"], 24)
        self.assertIsNone(config["scientific_verdict"])

    def test_support_distinguishes_local_coverage_from_hull_span(self):
        class Reference:
            footprint = Polygon([(0, 0), (10, 0), (10, 10), (0, 10)])

        xyz = np.asarray([[1, 1, 5], [9, 1, 6], [9, 9, 7], [1, 9, 8]], dtype=np.float64)
        result = _support(Reference(), xyz, 0.3)
        self.assertLess(result["buffer_coverage_fraction"], 0.02)
        self.assertGreater(result["convex_hull_span_fraction"], 0.6)
        self.assertEqual(result["class6_point_count"], 4)

    def test_complete_lineage_config_and_attribute_colors(self):
        config = load_complete_config()
        validate_complete_config(config)
        self.assertEqual(config["display"]["row_count_per_sheet"], 22)
        xyz = np.asarray([[0, 0, 1], [0, 0, 2]], dtype=np.float64)
        colors = _height_colors(xyz)
        self.assertEqual(colors.shape, (2, 3))
        quaternions = np.asarray([[1, 0, 0, 0]], dtype=np.float64)
        normals = _normal_colors(quaternions)
        np.testing.assert_allclose(normals, [[0, 0, 1]])

    def test_twelve_row_layout_is_bounded_and_zero_execution(self):
        config = load_12row_config()
        validate_12row_config(config)
        self.assertEqual(config["display"]["row_count_per_sheet"], 12)
        self.assertEqual(config["display"]["visible_cell_count"], 288)


if __name__ == "__main__":
    unittest.main()
