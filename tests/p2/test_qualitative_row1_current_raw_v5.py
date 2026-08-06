import json
from pathlib import Path
import unittest
from unittest.mock import patch

import numpy as np

from scripts.p2.qualitative_row1_current_raw_v5.preview10 import enrich_candidate, ordered_boundary_loops


REPO = Path(__file__).resolve().parents[2]
CONFIG = REPO / "configs/p2/qualitative_row1_current_raw_v5/preview10_v1.json"


def ring(points):
    return np.asarray([*points, points[0]], dtype=np.float64)


class OrderedBoundaryLoopsTest(unittest.TestCase):
    def test_single_square_is_one_closed_four_edge_loop(self):
        loops, topology = ordered_boundary_loops(
            [ring([(0, 0, 1), (1, 0, 1), (1, 1, 1), (0, 1, 1)])],
            tolerance=0.005,
        )

        self.assertEqual(len(loops), 1)
        self.assertTrue(np.array_equal(loops[0][0], loops[0][-1]))
        self.assertEqual(len(loops[0]) - 1, 4)
        self.assertEqual(topology["boundary_edge_count"], 4)
        self.assertEqual(topology["boundary_loop_count"], 1)
        self.assertEqual(topology["topology_status"], "SIMPLE_CLOSED_LOOPS")
        self.assertTrue(topology["all_boundary_edges_consumed_once"])

    def test_two_disconnected_squares_remain_two_loops(self):
        loops, topology = ordered_boundary_loops(
            [
                ring([(0, 0, 1), (1, 0, 1), (1, 1, 1), (0, 1, 1)]),
                ring([(3, 0, 1), (4, 0, 1), (4, 1, 1), (3, 1, 1)]),
            ],
            tolerance=0.005,
        )

        self.assertEqual(len(loops), 2)
        self.assertTrue(all(np.array_equal(loop[0], loop[-1]) for loop in loops))
        self.assertEqual(sum(len(loop) - 1 for loop in loops), 8)
        self.assertEqual(topology["boundary_edge_count"], 8)
        self.assertEqual(topology["boundary_loop_count"], 2)

    def test_touching_squares_use_one_closed_eulerian_walk(self):
        loops, topology = ordered_boundary_loops(
            [
                ring([(0, 0, 1), (1, 0, 1), (1, 1, 1), (0, 1, 1)]),
                ring([(1, 1, 1), (2, 1, 1), (2, 2, 1), (1, 2, 1)]),
            ],
            tolerance=0.005,
        )

        self.assertEqual(len(loops), 1)
        self.assertTrue(np.array_equal(loops[0][0], loops[0][-1]))
        self.assertEqual(len(loops[0]) - 1, 8)
        self.assertEqual(topology["degree_histogram"], {"2": 6, "4": 1})
        self.assertEqual(topology["topology_status"], "TOUCHING_EULERIAN_BOUNDARY")


class PreviewContractTest(unittest.TestCase):
    def test_nonfinite_projection_is_rejected_before_crop(self):
        projected = [np.asarray([[np.nan, np.nan], [1.0, 1.0]], dtype=np.float64)]
        diagnostic = {
            "all_boundary_vertices_front_finite": False,
            "all_boundary_vertices_inside_raw_image": False,
            "projected_roof_bbox_area_px2": 0.0,
            "projected_boundary_vertex_count": 2,
        }
        candidate = {"rejection_reasons": []}

        with patch(
            "scripts.p2.qualitative_row1_current_raw_v5.preview10.project_loops",
            return_value=(projected, diagnostic),
        ):
            result = enrich_candidate(
                candidate,
                [],
                None,
                (100, 100, np.empty(0)),
                {},
                {"minimum_projected_roof_bbox_area_px2": 1.0},
                {"margin_scale": 0.5, "margin_constant_px": 10.0},
            )

        self.assertFalse(result["eligible"])
        self.assertIsNone(result["crop_xyxy"])
        self.assertIn("ROOF_BOUNDARY_NOT_IN_FRONT", result["rejection_reasons"])
        self.assertIn("ROOF_BOUNDARY_CROP_UNAVAILABLE", result["rejection_reasons"])

    def test_v5_contract_freezes_requested_preview_and_render_rules(self):
        config = json.loads(CONFIG.read_text(encoding="utf-8"))

        self.assertEqual(config["status"], "USER_APPROVED_ORDERED_POLYGON_LOOP_PREVIEW10")
        self.assertEqual(config["preview"]["building_count"], 10)
        self.assertEqual(len(config["preview"]["population_indices"]), 10)
        self.assertEqual(len(config["preview"]["building_ids"]), 10)
        self.assertFalse(config["preview"]["full_199_render_authorized"])
        self.assertTrue(config["boundary_topology"]["same_edge_ids_required_in_every_selected_camera"])
        self.assertTrue(config["camera_visibility"]["partial_or_outside_roofline_camera_is_ineligible"])
        self.assertTrue(config["render"]["draw_after_final_image_resize"])
        self.assertFalse(config["render"]["keypoints_rendered"])
        self.assertEqual(config["scientific_verdict"], None)


if __name__ == "__main__":
    unittest.main()
