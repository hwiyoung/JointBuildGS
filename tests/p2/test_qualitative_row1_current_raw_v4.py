from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

import numpy as np

from scripts.p2.qualitative_row1_current_raw_v4.preview10 import (
    choose_views,
    load_actual_point2d_observations,
    scan_sparse_observations,
    separated,
)


REPO = Path(__file__).resolve().parents[2]


class Row1V4ObservedTrackTest(unittest.TestCase):
    def test_point2d_index_loads_actual_uv_and_point_id(self) -> None:
        support = {
            "B1": {
                "image_observations": {
                    7: [(101, 1, np.asarray([1.0, 2.0, 3.0]))]
                }
            }
        }
        images = """# Image list
7 1 0 0 0 0 0 0 1 image.jpg
10.0 20.0 -1 30.5 40.5 101
"""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "images.txt"
            path.write_text(images, encoding="utf-8")
            observed, summary = load_actual_point2d_observations(path, support)
        np.testing.assert_allclose(observed[(7, 1)][0], [30.5, 40.5])
        self.assertEqual(observed[(7, 1)][1], 101)
        self.assertEqual(summary["loaded_point2d_observations"], 1)

    def test_sparse_scan_preserves_image_id_point2d_index_pair(self) -> None:
        buildings = [
            {
                "building_id": "B1",
                "building_bbox_xy": [100.0, 200.0, 110.0, 210.0],
                "z_range_ellipsoidal_m": [50.0, 60.0],
            }
        ]
        points = """# sparse points
101 1 2 3 1 2 3 0.1 7 4 9 8
102 1 2 20 1 2 3 0.1 7 5
"""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "points3D.txt"
            path.write_text(points, encoding="utf-8")
            support, summary = scan_sparse_observations(
                path,
                buildings,
                exact_image_ids={7},
                shift=[100.0, 200.0, 50.0],
                expected_point_count=2,
            )
        row = support["B1"]["image_observations"][7]
        self.assertEqual(len(row), 1)
        self.assertEqual(row[0][0:2], (101, 4))
        np.testing.assert_allclose(row[0][2], [101.0, 202.0, 53.0])
        self.assertEqual(summary["selected_building_exact_937_track_observations"], 1)

    def test_pose_diversity_rejects_only_close_angle_and_close_baseline(self) -> None:
        base = {"_view_vector": np.asarray([0.0, 0.0, 1.0]), "_camera_center": np.zeros(3)}
        close = {"_view_vector": np.asarray([0.01, 0.0, 0.99995]), "_camera_center": np.asarray([1.0, 0.0, 0.0])}
        far_baseline = {"_view_vector": np.asarray([0.01, 0.0, 0.99995]), "_camera_center": np.asarray([20.0, 0.0, 0.0])}
        different_angle = {"_view_vector": np.asarray([0.5, 0.0, 0.8660254]), "_camera_center": np.asarray([1.0, 0.0, 0.0])}
        self.assertFalse(separated(close, [base], 8.0, 15.0))
        self.assertTrue(separated(far_baseline, [base], 8.0, 15.0))
        self.assertTrue(separated(different_angle, [base], 8.0, 15.0))

    def test_best_available_is_not_labeled_near_nadir(self) -> None:
        selection = {
            "roles": ["TOP", "RANDOM_1", "RANDOM_2", "RANDOM_3"],
            "random_seed_namespace": "test",
            "near_nadir_max_deg": 30.0,
            "minimum_view_direction_separation_deg": 8.0,
            "minimum_camera_center_separation_m": 15.0,
        }

        def candidate(name: str, nadir: float, center_x: float) -> dict:
            angle = np.radians(nadir)
            return {
                "camera_name": name,
                "eligible": True,
                "nadir_deg": nadir,
                "valid_actual_observation_count": 10,
                "_view_vector": np.asarray([np.sin(angle), 0.0, np.cos(angle)]),
                "_camera_center": np.asarray([center_x, 0.0, 100.0]),
            }

        candidates = [
            candidate("a.jpg", 80.0, 0.0),
            candidate("b.jpg", 82.0, 20.0),
            candidate("c.jpg", 84.0, 40.0),
            candidate("d.jpg", 86.0, 60.0),
        ]
        views, status, _, _ = choose_views("B1", candidates, selection)
        self.assertEqual(status, "BEST_AVAILABLE_NO_NEAR_NADIR")
        self.assertEqual(views[0]["camera"]["camera_name"], "a.jpg")
        self.assertEqual(len(views), 4)

    def test_contract_is_ten_buildings_and_never_renders_keypoints(self) -> None:
        config = json.loads(
            (REPO / "configs/p2/qualitative_row1_current_raw_v4/preview10_v1.json").read_text()
        )
        self.assertEqual(config["preview"]["building_count"], 10)
        self.assertEqual(len(config["preview"]["building_ids"]), 10)
        self.assertTrue(config["selection"]["actual_point2d_observations_used_for_internal_validation"])
        self.assertFalse(config["selection"]["keypoints_rendered"])
        self.assertFalse(config["roofline"]["keypoints_rendered"])
        self.assertFalse(config["preview"]["full_199_render_authorized"])
        self.assertFalse(config["next_row_authorized"])


if __name__ == "__main__":
    unittest.main()
