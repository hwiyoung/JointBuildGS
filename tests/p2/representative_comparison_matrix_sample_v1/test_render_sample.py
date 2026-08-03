from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest import mock

import numpy as np
import matplotlib.pyplot as plt

from scripts.p2.representative_comparison_matrix_sample_v1 import render_sample as sample
from src.visualization.fixed_view_qualitative import BBox, PointSet


REPO = Path(__file__).resolve().parents[3]
CONFIG = REPO / "configs/p2/representative_comparison_matrix_sample_v1/render_v1.json"
PACKET = REPO / "docs/handoffs/P2_W2C_REPRESENTATIVE_COMPARISON_MATRIX_SAMPLE_v1.md"
CONFIG_V2 = REPO / "configs/p2/representative_comparison_matrix_sample_v2/render_v2.json"
PACKET_V2 = REPO / "docs/handoffs/P2_W2C_REPRESENTATIVE_COMPARISON_MATRIX_SAMPLE_v2.md"
CONFIG_V3 = REPO / "configs/p2/representative_comparison_matrix_sample_v3/render_v3.json"
PACKET_V3 = REPO / "docs/handoffs/P2_W2C_REPRESENTATIVE_COMPARISON_MATRIX_SAMPLE_v3.md"
CONFIG_C1_C2 = REPO / "configs/p2/c1_c2_comparison_matrix_sample_v1/render_v1.json"
PACKET_C1_C2 = REPO / "docs/handoffs/P2_W2C_C1_C2_COMPARISON_MATRIX_SAMPLE_v1.md"
CONFIG_C1_C2_R2 = REPO / "configs/p2/c1_c2_comparison_matrix_sample_v2/render_v2.json"
PACKET_C1_C2_R2 = REPO / "docs/handoffs/P2_W2C_C1_C2_COMPARISON_MATRIX_SAMPLE_v2.md"
CONFIG_C1_C2_R4 = REPO / "configs/p2/c1_c2_comparison_matrix_sample_v4/render_v4.json"
PACKET_C1_C2_R4 = REPO / "docs/handoffs/P2_W2C_C1_C2_COMPARISON_MATRIX_SAMPLE_v4.md"
CONFIG_C1_C2_R5 = REPO / "configs/p2/c1_c2_comparison_matrix_sample_v5/render_v5.json"
PACKET_C1_C2_R5 = REPO / "docs/handoffs/P2_W2C_C1_C2_COMPARISON_MATRIX_SAMPLE_v5.md"


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

        def fake_project(points, camera, width, height, params, scene_ref, input_datum="orthometric"):
            self.assertEqual(input_datum, "ellipsoidal")
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
                "ellipsoidal",
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

    def test_screen_text_supports_2d_and_3d_axes(self) -> None:
        figure = plt.figure()
        try:
            axis_2d = figure.add_subplot(121)
            axis_3d = figure.add_subplot(122, projection="3d")
            text_2d = sample.screen_text(axis_2d, 0.5, 0.5, "2D")
            text_3d = sample.screen_text(axis_3d, 0.5, 0.5, "3D")
            self.assertEqual(text_2d.get_text(), "2D")
            self.assertEqual(text_3d.get_text(), "3D")
        finally:
            plt.close(figure)

    def test_reference_centered_section_keeps_roof_reference_visible(self) -> None:
        bbox = BBox(0.0, 0.0, 10.0, 10.0)
        points = np.asarray([[2.0, 9.0, 5.0], [8.0, 9.2, 6.0]])
        default_along, _, _ = sample.section_data(points, bbox, 0.75)
        anchored_along, _, _ = sample.section_data(points, bbox, 0.75, (5.0, 9.1))
        self.assertEqual(len(default_along), 0)
        self.assertEqual(len(anchored_along), 2)

    def test_missing_method_unit_fails_before_output_creation(self) -> None:
        rows = {
            "B1": {
                method: {"operation_unit_id": f"{method}|unit"}
                for method in sample.METHODS_SOURCE
            }
        }
        units = {row["operation_unit_id"]: row for row in rows["B1"].values()}
        sample.validate_sealed_operation_units(rows, ["B1"], units)
        rows["B1"]["C3_GS_image"]["operation_unit_id"] = None
        with self.assertRaisesRegex(RuntimeError, "before output creation"):
            sample.validate_sealed_operation_units(rows, ["B1"], units)

    def test_c1_c2_only_preflight_does_not_require_c3(self) -> None:
        rows = {
            "B1": {
                method: {"operation_unit_id": f"{method}|unit"}
                for method in ("C1_L_upper", "C2_MVS")
            }
        }
        units = {row["operation_unit_id"]: row for row in rows["B1"].values()}
        sample.validate_sealed_operation_units(
            rows,
            ["B1"],
            units,
            ("C1_L_upper", "C2_MVS"),
        )

    def test_packet_is_approved_and_forbids_reexecution(self) -> None:
        text = PACKET.read_text(encoding="utf-8")
        self.assertIn("status: `APPROVED_FOR_EXECUTION`", text)
        self.assertIn("Roofer, G2, metric 또는 GS training 재실행", text)
        self.assertIn("PARTIAL_NAMESPACE_PRESENT", text)
        self.assertIn("scientific_verdict: `null`", text)

    def test_v2_uses_new_namespace_and_exact_runtime_fix(self) -> None:
        config_v2 = json.loads(CONFIG_V2.read_text(encoding="utf-8"))
        self.assertEqual(config_v2["selection"], self.config["selection"])
        self.assertNotEqual(config_v2["output_task_relative_root"], self.config["output_task_relative_root"])
        self.assertTrue(config_v2["output_task_relative_root"].endswith("SAMPLE-v2"))
        packet = PACKET_V2.read_text(encoding="utf-8")
        self.assertIn("status: `APPROVED_FOR_EXECUTION`", packet)
        self.assertIn("v1 partial 삭제·덮어쓰기·재사용", packet)

    def test_v3_uses_source_available_distinct_group_sample(self) -> None:
        config_v3 = json.loads(CONFIG_V3.read_text(encoding="utf-8"))
        records = config_v3["selection"]["records"]
        self.assertEqual(
            [row["building_id"] for row in records],
            ["DEBY_LOD2_4907177", "DEBY_LOD2_4906975", "DEBY_LOD2_108580336"],
        )
        self.assertEqual(len({row["candidate_group_id"] for row in records}), 3)
        self.assertIn("C1_C2_C3_SEALED_SOURCE_AVAILABLE", config_v3["selection"]["rule"])
        self.assertTrue(config_v3["output_task_relative_root"].endswith("SAMPLE-v3"))
        packet = PACKET_V3.read_text(encoding="utf-8")
        self.assertIn("status: `APPROVED_FOR_EXECUTION`", packet)
        self.assertIn("output namespace 생성 전에 exact 3×3 operation unit", packet)

    def test_c1_c2_only_config_has_exact_60_panel_contract(self) -> None:
        config = json.loads(CONFIG_C1_C2.read_text(encoding="utf-8"))
        methods = tuple(config["methods"])
        self.assertEqual(methods, ("C1_L_upper", "C2_MVS"))
        building_ids = [row["building_id"] for row in config["selection"]["records"]]
        expected = sample.expected_panel_ids(building_ids, methods)
        self.assertEqual(len(expected), 60)
        packet = PACKET_C1_C2.read_text(encoding="utf-8")
        self.assertIn("C3–C5 source를 읽거나 표시하지 않는다", packet)
        self.assertIn("60 PNG", packet)

    def test_c1_c2_recovery_uses_new_namespace_and_reference_center(self) -> None:
        config = json.loads(CONFIG_C1_C2_R2.read_text(encoding="utf-8"))
        self.assertEqual(config["methods"], ["C1_L_upper", "C2_MVS"])
        self.assertTrue(config["output_task_relative_root"].endswith("SAMPLE-v2"))
        packet = PACKET_C1_C2_R2.read_text(encoding="utf-8")
        self.assertIn("reference XY median", packet)
        self.assertIn("v1 partial을 삭제·수정·재사용하지 않는다", packet)

    def test_c1_c2_v4_locks_canonical_mount_and_fresh_namespace(self) -> None:
        config = json.loads(CONFIG_C1_C2_R4.read_text(encoding="utf-8"))
        self.assertEqual(config["methods"], ["C1_L_upper", "C2_MVS"])
        self.assertEqual(config["views"]["section_anchor"], "REFERENCE_XY_MEDIAN")
        self.assertTrue(config["output_task_relative_root"].endswith("SAMPLE-v4"))
        packet = PACKET_C1_C2_R4.read_text(encoding="utf-8")
        self.assertIn("/workspace/JointBuildGS:ro", packet)
        self.assertIn("v1/v2 partial", packet)
        self.assertIn("C3–C5 method artifact", packet)

    def test_c1_c2_v5_uses_same_frame_current_uas_datum(self) -> None:
        config = json.loads(CONFIG_C1_C2_R5.read_text(encoding="utf-8"))
        rgb = config["rgb_context"]
        self.assertEqual(config["methods"], ["C1_L_upper", "C2_MVS"])
        self.assertEqual(rgb["reference_input_datum"], "ellipsoidal")
        self.assertEqual(rgb["current_uas_input_datum"], "ellipsoidal")
        self.assertIn("45.7 m exactly once", rgb["existing_als_image_projection_policy"])
        self.assertEqual(
            [panel["role"] for panel in rgb["raw_panel_layout"]],
            ["REFERENCE_CONTEXT", "NADIR_MEDIUM", "NADIR_TIGHT", "OBLIQUE_VALIDATION"],
        )
        self.assertEqual(len(sample.expected_panel_ids(
            [row["building_id"] for row in config["selection"]["records"]],
            config["methods"],
        )), 60)
        packet = PACKET_C1_C2_R5.read_text(encoding="utf-8")
        self.assertIn("current UAS LiDAR와 동일 획득 드론 RGB", packet)
        self.assertIn("45.7 m", packet)

    def test_current_uas_camera_roles_require_zero_shift_datum(self) -> None:
        reference = PointSet(np.asarray([[0.0, 0.0, 1.0], [0.5, 0.5, 1.0]]), None)
        support = PointSet(np.asarray([[0.0, 0.0, 1.0], [0.5, 0.5, 1.0]]), np.asarray([6, 6]))
        cameras = [
            SimpleNamespace(
                name="near.jpg",
                center=np.asarray([0.0, 0.0, 11.0]),
                rot=np.eye(3),
                tvec=np.asarray([0.0, 0.0, -11.0]),
            ),
            SimpleNamespace(
                name="oblique.jpg",
                center=np.asarray([10.0, 0.0, 11.0]),
                rot=np.eye(3),
                tvec=np.asarray([-10.0, 0.0, -11.0]),
            ),
        ]

        def fake_project(points, camera, width, height, params, scene_ref, input_datum="orthometric"):
            self.assertEqual(input_datum, "ellipsoidal")
            uv = np.tile(np.asarray([[50.0, 50.0]]), (len(points), 1))
            return uv, np.ones((len(points),), dtype=bool)

        with mock.patch.object(sample.projection, "project", side_effect=fake_project):
            roles = sample.select_current_uas_camera_roles(
                reference,
                support,
                BBox(-1.0, -1.0, 1.0, 1.0),
                cameras,
                (100, 100, np.zeros((12,), dtype=float)),
                {},
                0.5,
                "ellipsoidal",
            )
        self.assertEqual(roles["NADIR"]["camera"].name, "near.jpg")
        self.assertEqual(roles["OBLIQUE"]["camera"].name, "oblique.jpg")
        with self.assertRaisesRegex(RuntimeError, "same-frame ellipsoidal"):
            sample.select_current_uas_camera_roles(
                reference,
                support,
                BBox(-1.0, -1.0, 1.0, 1.0),
                cameras,
                (100, 100, np.zeros((12,), dtype=float)),
                {},
                0.5,
                "orthometric",
                "orthometric",
            )

    def test_context_crop_is_four_by_three_and_respects_minimum(self) -> None:
        bounds = sample.context_crop_xyxy(
            np.asarray([[900.0, 700.0], [1100.0, 800.0]]),
            3000,
            2000,
            2.0,
            1200,
            900,
        )
        left, top, right, bottom = bounds
        self.assertEqual((right - left, bottom - top), (1200, 900))
        self.assertGreaterEqual(left, 0)
        self.assertGreaterEqual(top, 0)


if __name__ == "__main__":
    unittest.main()
