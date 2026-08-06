import json
from pathlib import Path
import unittest
from unittest.mock import patch

import numpy as np

from scripts.p2.qualitative_row1_current_raw_v6.preview10 import (
    component_records,
    enrich_candidate,
    loop_xy_area,
)


REPO = Path(__file__).resolve().parents[2]
CONFIG = REPO / "configs/p2/qualitative_row1_current_raw_v6/preview10_v1.json"


def ring(points):
    return np.asarray([*points, points[0]], dtype=np.float64)


class RepresentativeComponentTest(unittest.TestCase):
    def test_largest_xy_area_is_representative(self):
        small = ring([(0, 0, 1), (1, 0, 1), (1, 1, 1), (0, 1, 1)])
        large = ring([(3, 0, 1), (7, 0, 1), (7, 2, 1), (3, 2, 1)])

        components, representative_id = component_records([small, large])

        self.assertEqual(loop_xy_area(small), 1.0)
        self.assertEqual(loop_xy_area(large), 8.0)
        self.assertEqual(representative_id, 2)
        self.assertEqual([row["component_id"] for row in components], [1, 2])

    def test_area_tie_uses_stable_lowest_component_id(self):
        first = ring([(0, 0, 1), (1, 0, 1), (1, 1, 1), (0, 1, 1)])
        second = ring([(3, 0, 1), (4, 0, 1), (4, 1, 1), (3, 1, 1)])

        _, representative_id = component_records([first, second])

        self.assertEqual(representative_id, 1)

    def test_other_component_may_be_absent_without_rejecting_camera(self):
        representative_uv = np.asarray(
            [[20, 20], [80, 20], [80, 80], [20, 80], [20, 20]], dtype=np.float64
        )
        outside_uv = np.asarray(
            [[120, 20], [150, 20], [150, 50], [120, 50], [120, 20]], dtype=np.float64
        )
        projected = [
            {
                "component_id": 1,
                "xy_area_m2": 100.0,
                "source_edge_count": 4,
                "all_vertices_front_finite": True,
                "all_vertices_inside_raw_image": True,
                "projected_bbox_area_px2": 3600.0,
                "_uv": representative_uv,
            },
            {
                "component_id": 2,
                "xy_area_m2": 20.0,
                "source_edge_count": 4,
                "all_vertices_front_finite": True,
                "all_vertices_inside_raw_image": False,
                "projected_bbox_area_px2": 900.0,
                "_uv": outside_uv,
            },
        ]
        candidate = {"rejection_reasons": []}

        with patch(
            "scripts.p2.qualitative_row1_current_raw_v6.preview10.project_components",
            return_value=projected,
        ):
            result = enrich_candidate(
                candidate,
                [{"component_id": 1}, {"component_id": 2}],
                1,
                None,
                (100, 100, np.empty(0)),
                {},
                {"minimum_projected_representative_bbox_area_px2": 1200.0},
                {"margin_scale": 0.0, "margin_constant_px": 1.0},
            )

        self.assertTrue(result["eligible"])
        self.assertEqual(result["visible_component_ids_in_crop"], [1])
        self.assertEqual(result["visible_component_count_in_crop"], 1)
        self.assertEqual(result["source_component_count"], 2)


class PreviewContractTest(unittest.TestCase):
    def test_v6_contract_freezes_visible_component_policy(self):
        config = json.loads(CONFIG.read_text(encoding="utf-8"))

        self.assertEqual(config["status"], "USER_APPROVED_REPRESENTATIVE_COMPONENT_PREVIEW10")
        self.assertEqual(config["preview"]["building_count"], 10)
        self.assertFalse(config["preview"]["full_199_render_authorized"])
        self.assertTrue(
            config["representative_component"][
                "require_entire_representative_loop_in_front_and_inside_raw_image"
            ]
        )
        self.assertTrue(config["representative_component"]["other_components_may_be_outside_image_or_crop"])
        self.assertFalse(config["visible_component"]["partial_component_rendering"])
        self.assertTrue(config["visible_component"]["preserve_stable_component_ids_across_cameras"])
        self.assertEqual(config["visible_component"]["panel_label"], "VISIBLE LOOPS k/n")
        self.assertFalse(config["render"]["keypoints_rendered"])
        self.assertIsNone(config["scientific_verdict"])


if __name__ == "__main__":
    unittest.main()
