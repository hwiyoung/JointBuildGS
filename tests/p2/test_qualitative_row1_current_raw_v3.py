from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

import numpy as np

from scripts.p2.qualitative_row1_current_raw_v3.preview import (
    choose_views,
    deterministic_sample,
    outer_roof_shell_edges,
    projection_qc,
    scan_sparse_tracks,
    stable_seed,
)


REPO = Path(__file__).resolve().parents[2]


class Row1V3SparseTrackTest(unittest.TestCase):
    def test_seeded_sample_is_stable_and_order_independent(self) -> None:
        seed = stable_seed("namespace", "DEBY_LOD2_1")
        self.assertEqual(seed, stable_seed("namespace", "DEBY_LOD2_1"))
        self.assertEqual(
            deterministic_sample(["d", "b", "a", "c"], 3, seed),
            deterministic_sample(["c", "a", "d", "b"], 3, seed),
        )

    def test_sparse_tracks_are_restricted_to_frozen_xyz_prism_and_exact_membership(self) -> None:
        buildings = [
            {
                "building_id": "B1",
                "building_bbox_xy": [100.0, 200.0, 110.0, 210.0],
                "z_range_ellipsoidal_m": [50.0, 60.0],
            }
        ]
        payload = """# Number of points: 3
1 1 2 3 1 2 3 0.1 10 0 20 1
2 1 2 20 1 2 3 0.1 10 2
3 30 40 3 1 2 3 0.1 10 3
"""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "points3D.txt"
            path.write_text(payload, encoding="utf-8")
            support, summary = scan_sparse_tracks(
                path,
                buildings,
                exact_image_ids={10},
                shift=[100.0, 200.0, 50.0],
                expected_point_count=3,
            )
        row = support["B1"]
        self.assertEqual(row["xy_point_count_all_z"], 2)
        self.assertEqual(row["xyz_point_count"], 1)
        self.assertEqual(set(row["image_points"]), {10})
        np.testing.assert_allclose(row["image_points"][10], [[101.0, 202.0, 53.0]])
        self.assertEqual(summary["sparse_points_scanned"], 3)
        self.assertEqual(summary["exact_937_track_observations_retained"], 1)

    def test_shared_gable_ridge_is_removed_from_outer_shell(self) -> None:
        left = np.asarray(
            [[0, 0, 0], [0, 1, 0], [0.5, 1, 1], [0.5, 0, 1], [0, 0, 0]],
            dtype=float,
        )
        right = np.asarray(
            [[0.5, 0, 1], [0.5, 1, 1], [1, 1, 0], [1, 0, 0], [0.5, 0, 1]],
            dtype=float,
        )
        edges, diagnostic = outer_roof_shell_edges([left, right], 0.001)
        self.assertEqual(len(edges), 6)
        self.assertEqual(diagnostic["outer_roof_shell_component_count"], 1)
        self.assertEqual(diagnostic["shell_status"], "SINGLE_ROOF_SHELL")

    def test_top_prefers_near_nadir_but_labels_no_near_nadir(self) -> None:
        selection = {
            "roles": ["TOP", "RANDOM_1", "RANDOM_2", "RANDOM_3"],
            "near_nadir_max_deg": 30.0,
            "random_seed_namespace": "test",
        }
        base = {
            "eligible": True,
            "track_point_count": 5,
            "track_spread_diagonal_px": 20.0,
        }
        candidates = [
            {**base, "camera_name": "near.jpg", "nadir_deg": 15.0},
            {**base, "camera_name": "strong.jpg", "nadir_deg": 60.0, "track_point_count": 20},
            {**base, "camera_name": "r1.jpg", "nadir_deg": 65.0},
            {**base, "camera_name": "r2.jpg", "nadir_deg": 70.0},
        ]
        views, status, _, _ = choose_views("B1", candidates, selection)
        self.assertEqual(status, "NEAR_NADIR_TRACK_CONFIRMED")
        self.assertEqual(views[0]["camera"]["camera_name"], "near.jpg")
        no_near = [{**row, "nadir_deg": row["nadir_deg"] + 30.0} for row in candidates]
        views, status, _, _ = choose_views("B1", no_near, selection)
        self.assertEqual(status, "NO_NEAR_NADIR_BEST_TRACK_SUPPORT")
        self.assertEqual(views[0]["camera"]["camera_name"], "strong.jpg")

    def test_missing_roles_are_not_filled_with_projection_only_cameras(self) -> None:
        selection = {
            "roles": ["TOP", "RANDOM_1", "RANDOM_2", "RANDOM_3"],
            "near_nadir_max_deg": 30.0,
            "random_seed_namespace": "test",
        }
        candidate = {
            "eligible": True,
            "camera_name": "only.jpg",
            "nadir_deg": 10.0,
            "track_point_count": 5,
            "track_spread_diagonal_px": 20.0,
        }
        views, _, _, _ = choose_views("B1", [candidate], selection)
        self.assertEqual(views[0]["status"], "SELECTED")
        self.assertTrue(all(view["status"] == "SPARSE_SUPPORT_MISSING" for view in views[1:]))

    def test_projection_qc_never_changes_selection(self) -> None:
        status, delta = projection_qc(np.asarray([[100.0, 100.0]]), np.asarray([[110.0, 110.0]]), 20.0)
        self.assertEqual(status, "PROJECTION_ALIGNED")
        self.assertAlmostEqual(delta, np.sqrt(200.0))
        status, _ = projection_qc(np.asarray([[100.0, 100.0]]), np.asarray([[500.0, 500.0]]), 20.0)
        self.assertEqual(status, "PROJECTION_MISMATCH")

    def test_contract_blocks_full_199_render_and_next_row(self) -> None:
        config = json.loads(
            (REPO / "configs/p2/qualitative_row1_current_raw_v3/preview_v1.json").read_text()
        )
        self.assertEqual(config["status"], "USER_APPROVED_SPARSE_TRACK_ROW1_PREVIEW")
        self.assertFalse(config["selection"]["roof_boundary_used_for_selection"])
        self.assertFalse(config["projection_qc"]["used_for_selection"])
        self.assertEqual(config["roofline"]["main_panel_geometry"], "OUTER_ROOF_SHELL_EDGES_ONLY")
        self.assertFalse(config["preview"]["full_199_render_authorized"])
        self.assertFalse(config["next_row_authorized"])


if __name__ == "__main__":
    unittest.main()
