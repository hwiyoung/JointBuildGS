from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest import mock

import numpy as np

from scripts.p2.representative_comparison_matrix_sample_v1 import render_sample as sample
from src.visualization.fixed_view_qualitative import BBox, PointSet


REPO = Path(__file__).resolve().parents[3]
CONFIG = REPO / "configs/p2/representative_comparison_matrix_sample_v1/render_v1.json"
PACKET = REPO / "docs/handoffs/P2_W2C_REPRESENTATIVE_COMPARISON_MATRIX_SAMPLE_v1.md"


class RepresentativeComparisonMatrixSampleTest(unittest.TestCase):
    def setUp(self) -> None:
        self.config = json.loads(CONFIG.read_text(encoding="utf-8"))

    def test_selection_is_exact_outcome_free_strict_three(self) -> None:
        records = self.config["selection"]["records"]
        self.assertEqual(
            [row["building_id"] for row in records],
            ["DEBY_LOD2_4906974", "DEBY_LOD2_4907176", "DEBY_LOD2_4906968"],
        )
        self.assertEqual({row["size_bin"] for row in records}, {"small", "medium", "large"})
        self.assertEqual(len({row["candidate_group_id"] for row in records}), 3)
        self.assertIn("NO_OUTCOME_FIELDS", self.config["selection"]["rule"])

    def test_matrix_slots_match_dec_p1_016(self) -> None:
        self.assertEqual(sample.METHODS_ALL, tuple(self.config["methods"]))
        self.assertEqual(len(sample.STAGE_ROWS["C1_L_upper"]), 2)
        self.assertEqual(len(sample.STAGE_ROWS["C2_MVS"]), 2)
        self.assertEqual(len(sample.STAGE_ROWS["C3_GS_image"]), 3)
        self.assertEqual(len(sample.STAGE_ROWS["C4_GS_lidar_prior"]), 3)
        self.assertEqual(len(sample.STAGE_ROWS["C5_GS_lod1_prior"]), 3)
        expected_panels = 3 * (4 + 4 * sum(len(rows) for rows in sample.STAGE_ROWS.values()))
        self.assertEqual(expected_panels, 168)
        expected_ids = sample.expected_panel_ids([row["building_id"] for row in self.config["selection"]["records"]])
        self.assertEqual(len(expected_ids), 168)

    def test_output_paths_are_contained(self) -> None:
        root = REPO.resolve()
        self.assertEqual(sample.contained_path(root, "configs", label="test"), root / "configs")
        with self.assertRaisesRegex(RuntimeError, "escapes allowed root"):
            sample.contained_path(root, "../escape", label="test")

    def test_camera_selection_is_coverage_then_angular_diversity(self) -> None:
        cameras = [
            SimpleNamespace(name=f"cam{i}.jpg", center=np.asarray([np.cos(np.deg2rad(i * 45)), np.sin(np.deg2rad(i * 45)), 10.0]))
            for i in range(8)
        ]
        reference = PointSet(np.asarray([[0.0, 0.0, 1.0]] * 10), None)
        counts = {f"cam{i}.jpg": 10 - i for i in range(8)}

        def fake_project(points, camera, width, height, params, scene_ref):
            count = counts[camera.name]
            uv = np.full((len(points), 2), -1.0)
            uv[:count] = [50.0, 50.0]
            front = np.zeros((len(points),), dtype=bool)
            front[:count] = True
            return uv, front

        with mock.patch.object(sample.projection, "project", side_effect=fake_project):
            selected = sample.select_cameras(
                reference,
                BBox(-1.0, -1.0, 1.0, 1.0),
                cameras,
                (100, 100, np.zeros((12,), dtype=float)),
                {},
                4,
                0.25,
            )
        self.assertEqual(len(selected), 4)
        self.assertEqual(selected[0]["camera"].name, "cam0.jpg")
        self.assertEqual(len({row["camera"].name for row in selected}), 4)
        self.assertGreaterEqual(
            min(
                sample.circular_distance(float(left["azimuth"]), float(right["azimuth"]))
                for index, left in enumerate(selected)
                for right in selected[index + 1 :]
            ),
            45.0,
        )

    def test_metric_card_explains_shared_failure_and_official_null(self) -> None:
        row = {
            "association_status": "SHARED_COMPONENT",
            "one_to_one_building_component": False,
            "reference_cell_count": 100,
            "G0_generated": False,
            "G1_schema_semantic": False,
            "G2_geometry_topology_valid": False,
            "G3_candidate": False,
            "G4_candidate": False,
            "continuous_metrics": {
                "height_error_mae_m": 2.5,
                "RMSZ_m": 3.0,
                "surface_distance_rmse_m": 3.0,
                "surface_distance_p95_m": 4.0,
            },
        }
        card = sample.metric_card("C2_MVS", row, 500)
        self.assertIn("shared/multi 출력", card)
        self.assertIn("official G3/G4/PASS: <b>null</b>", card)
        self.assertIn("STRICT_INDEPENDENT_UAS_REFERENCE", card)

    def test_packet_is_draft_and_forbids_reexecution(self) -> None:
        text = PACKET.read_text(encoding="utf-8")
        self.assertIn("status: `DRAFT`", text)
        self.assertIn("Roofer, G2, metric 또는 GS training 재실행", text)
        self.assertIn("PARTIAL_NAMESPACE_PRESENT", text)
        self.assertIn("scientific_verdict: `null`", text)


if __name__ == "__main__":
    unittest.main()
