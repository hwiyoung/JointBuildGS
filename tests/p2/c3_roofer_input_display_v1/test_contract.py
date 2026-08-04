import unittest

import numpy as np
from shapely.geometry import Polygon

from scripts.p2.c3_roofer_input_display_v1.render import _support, load_config, validate_config


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


if __name__ == "__main__":
    unittest.main()
