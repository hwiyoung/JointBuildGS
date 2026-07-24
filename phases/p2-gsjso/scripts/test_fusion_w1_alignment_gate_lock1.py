#!/usr/bin/env python3
"""Regression tests for the isolated FUS-W1 Gate A lock1 implementation."""
from __future__ import annotations

import copy
import importlib.util
import json
import math
from pathlib import Path
from types import SimpleNamespace
import sys
import tempfile
import unittest
from unittest import mock

import numpy as np


SCRIPT_PATH = Path(__file__).with_name("fusion_w1_alignment_gate_lock1.py")
SPEC = importlib.util.spec_from_file_location(
    "fusion_w1_alignment_gate_lock1_under_test", SCRIPT_PATH
)
assert SPEC is not None and SPEC.loader is not None
gate = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = gate
SPEC.loader.exec_module(gate)


def square_boundary(
    x0: float = 30.0,
    y0: float = 30.0,
    size: int = 40,
) -> tuple[np.ndarray, np.ndarray]:
    values = np.arange(size + 1, dtype=np.float64)
    x = x0 + values
    y = y0 + values
    points = np.vstack(
        [
            np.column_stack([x, np.full_like(x, y0)]),
            np.column_stack([np.full_like(y, x0 + size), y]),
            np.column_stack([x[::-1], np.full_like(x, y0 + size)]),
            np.column_stack([np.full_like(y, x0), y[::-1]]),
        ]
    )
    normals = np.vstack(
        [
            np.tile([0.0, -1.0], (len(x), 1)),
            np.tile([1.0, 0.0], (len(y), 1)),
            np.tile([0.0, 1.0], (len(x), 1)),
            np.tile([-1.0, 0.0], (len(y), 1)),
        ]
    )
    return points, normals


class FusionW1AlignmentGateLock1Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.config = gate.load_config(gate.DEFAULT_CONFIG)

    def test_locked_config_contract(self) -> None:
        cfg = self.config
        self.assertEqual(cfg["implementation_variant"], "lock1")
        self.assertEqual(cfg["gate"]["building_median_residual_max_m"], 0.3)
        self.assertEqual(cfg["gate"]["systematic_xy_norm_max_m"], 0.1)
        self.assertEqual(
            cfg["gate"]["systematic_bootstrap_ci_upper_max_m"], 0.1
        )
        self.assertFalse(cfg["time_policy"]["stop_at_0630"])
        selection = cfg["view_selection"]
        self.assertEqual(selection["selection_edge_localization_sigma_px"], 0.1)
        self.assertEqual(
            selection["predicted_uncertainty_reference_m"], 0.3
        )
        self.assertEqual(selection["azimuth_bin_count"], 8)
        self.assertEqual(selection["minimum_selected_azimuth_bins"], 1)
        self.assertIn("does not preregister", selection["azimuth_coverage_role"])
        self.assertIn("observability-first", selection["ranking"])
        self.assertIn(
            "||n^T J_xy||_2",
            cfg["alignment"]["metre_conversion"],
        )
        footprint_contract = cfg["input_locks"]["footprint_contract"]
        approval_path = footprint_contract["approved_exception_document"]
        approval_sha256 = footprint_contract[
            "approved_exception_document_sha256"
        ]
        self.assertEqual(
            cfg["input_locks"]["expected_sha256"][approval_path],
            approval_sha256,
        )

    def test_missing_observability_key_fails_at_config_load(self) -> None:
        payload = copy.deepcopy(self.config)
        del payload["view_selection"][
            "predicted_uncertainty_reference_m"
        ]
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "config.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(
                gate.GateContractError, "view-selection lock is incomplete"
            ):
                gate.load_config(path)

    def test_auto_select_is_observability_first_and_azimuth_balanced(self) -> None:
        target = gate.Target("DEBY_LOD2_1", 1, "core", "surface")
        xyz = np.column_stack(
            [
                np.linspace(0.0, 1.0, 40),
                np.linspace(0.0, 1.0, 40),
                np.full(40, 10.0),
            ]
        )
        cloud = gate.TargetCloud(
            target.building_id,
            np.array([[0, 0], [2, 0], [2, 2], [0, 2], [0, 0]], float),
            xyz,
            xyz.copy(),
            ("synthetic",),
        )
        camera = SimpleNamespace(width=100, height=100, params=[50, 50, 50, 50])
        images: dict[str, SimpleNamespace] = {}
        for index in range(16):
            azimuth_bin = index % 8
            angle = 2.0 * math.pi * azimuth_bin / 8.0 + 0.1
            center = np.array([20.0 * math.cos(angle), 20.0 * math.sin(angle), 30.0])
            image = SimpleNamespace(
                name=f"b{azimuth_bin}_{index // 8}.png",
                id=index + 1,
                camera_id=1,
                tvec=-center,
                R=lambda: np.eye(3),
            )
            images[image.name] = image

        visible = gate.VisibleBoundary(
            xyz=xyz[:32],
            source_index=np.arange(32),
            uv=np.column_stack(
                [np.linspace(20, 80, 32), np.full(32, 50.0)]
            ),
            normal_uv=np.tile([1.0, 0.0], (32, 1)),
            outward_xy=np.tile([1.0, 0.0], (32, 1)),
            camera_depth=np.full(32, 20.0),
            source_count=32,
            visible_fraction=1.0,
        )
        selection = copy.deepcopy(self.config["view_selection"])
        selection["minimum_views_per_building"] = 16
        selection["maximum_views_per_building"] = 16

        def fake_project(points, *_args, **_kwargs):
            return np.tile([50.0, 50.0], (len(points), 1)), np.ones(
                len(points), dtype=bool
            )

        def fake_jacobians(_points, image, *_args, **_kwargs):
            # The first candidate in each bin has twice the normal-row sensitivity.
            scale = (
                0.2
                if image.name == "b0_1.png"
                else (2.0 if image.name.endswith("_0.png") else 1.0)
            )
            return (
                np.tile(np.array([[scale, 0.0], [0.0, 1.0]]), (32, 1, 1)),
                np.ones(32),
            )

        with (
            mock.patch.object(gate, "project_base_points", side_effect=fake_project),
            mock.patch.object(
                gate,
                "base_to_canonical_points",
                side_effect=lambda p, *_a, **_k: np.zeros_like(p),
            ),
            mock.patch.object(gate, "_view_geometry", return_value=(30.0, 0.2)),
            mock.patch.object(gate, "visible_eave_boundary", return_value=visible),
            mock.patch.object(
                gate, "xy_projection_jacobians", side_effect=fake_jacobians
            ),
        ):
            chosen = gate.auto_select_views(
                [target],
                {target.building_id: cloud},
                {1: camera},
                images,
                {},
                "orthometric",
                0.0,
                selection,
                self.config["boundary_extraction"],
                self.config["alignment"],
            )
        self.assertEqual(len(chosen), 16)
        self.assertEqual({item.azimuth_bin for item in chosen[:8]}, set(range(8)))
        self.assertTrue(all(item.name.endswith("_0.png") for item in chosen[:8]))
        self.assertTrue(
            any(item.predicted_metric_uncertainty_m > 0.3 for item in chosen)
        )

    def test_als_exposed_direction_does_not_use_footprint_perimeter(self) -> None:
        xy = np.array(
            [
                [x, y]
                for y in range(6)
                for x in range(6)
                if not (2 <= x <= 4 and 2 <= y <= 4)
            ],
            dtype=float,
        )
        xyz = np.column_stack([xy * 0.34, np.full(len(xy), 10.0)])
        cfg = copy.deepcopy(self.config["boundary_extraction"])
        cfg.update(
            {
                "minimum_boundary_points": 4,
                "minimum_main_component_occupied_fraction": 0.1,
                "minimum_main_component_point_fraction": 0.1,
                "local_tangent_radius_m": 1.0,
                "minimum_local_tangent_neighbors": 2,
            }
        )
        cloud_a = gate.TargetCloud(
            "B",
            np.array([[-5, -5], [5, -5], [5, 5], [-5, 5], [-5, -5]], float),
            xyz,
            xyz,
            ("synthetic",),
        )
        cloud_b = gate.TargetCloud(
            "B",
            np.array([[100, 100], [101, 100], [101, 101], [100, 100]], float),
            xyz,
            xyz,
            ("synthetic",),
        )
        a_xyz, _a_tangent, a_q, a_source = gate._als_eave_boundary(cloud_a, cfg)
        b_xyz, _b_tangent, b_q, b_source = gate._als_eave_boundary(cloud_b, cfg)
        np.testing.assert_allclose(a_xyz, xyz[a_source])
        np.testing.assert_array_equal(a_source, b_source)
        np.testing.assert_allclose(a_q, b_q)
        shifted_xyz = xyz + np.array([1.25, -0.75, 0.0])
        cloud_shifted = gate.TargetCloud(
            "B",
            cloud_a.footprint_xy,
            shifted_xyz,
            shifted_xyz,
            ("synthetic",),
        )
        c_xyz, _c_tangent, _c_q, c_source = gate._als_eave_boundary(
            cloud_shifted, cfg
        )
        np.testing.assert_array_equal(a_source, c_source)
        np.testing.assert_allclose(
            c_xyz[:, :2] - a_xyz[:, :2],
            np.tile([1.25, -0.75], (len(c_xyz), 1)),
        )

    def test_pointwise_normal_row_norm_metre_formula(self) -> None:
        count = 4
        match = {
            "boundary_index": np.arange(count),
            "edge_normal": np.tile([1.0, 0.0], (count, 1)),
            "distance_px_all": np.full(count, 4.0),
            "reverse_distance_px_all": np.full(count, 4.0),
            "reverse_metric_boundary_index": np.arange(count),
            "reverse_metric_edge_normal": np.tile([1.0, 0.0], (count, 1)),
        }
        jacobian = np.array([[2.0, 1.0], [0.0, 3.0]])
        result = gate.direct_edge_distance_metric(
            match,
            np.tile(jacobian, (count, 1, 1)),
            np.tile([1.0, 0.0], (count, 1)),
            self.config["alignment"],
        )
        # ||[1,0] @ J||_2 == sqrt(5), independently at every source point.
        self.assertAlmostEqual(result["median_m"], 4.0 / math.sqrt(5.0))
        self.assertEqual(result["metre_denominator_formula"], "||n^T J_xy||_2")

    def test_primary_metric_is_forward_and_reverse_is_diagnostic(self) -> None:
        y = np.arange(10, dtype=np.float64)
        boundary = np.column_stack([np.full_like(y, 10.0), y])
        normals = np.tile([1.0, 0.0], (len(y), 1))
        edges = np.vstack(
            [
                boundary,
                np.column_stack([np.full_like(y, 30.0), y]),
            ]
        )
        edge_normals = np.tile([1.0, 0.0], (len(edges), 1))
        cfg = copy.deepcopy(self.config["alignment"])
        matched = gate.match_oriented_edges(
            boundary, normals, edges, edge_normals, cfg
        )
        result = gate.direct_edge_distance_metric(
            matched,
            np.tile(np.eye(2), (len(boundary), 1, 1)),
            normals,
            cfg,
        )
        self.assertAlmostEqual(result["forward_median_px"], 0.0)
        self.assertGreaterEqual(result["reverse_p90_px"], 19.9)
        self.assertAlmostEqual(result["median_px"], 0.0)
        self.assertAlmostEqual(result["p90_px"], 0.0)
        self.assertEqual(
            result["primary_direction"], "als_boundary_to_image_edge"
        )

    def test_pointwise_jacobian_scaling_and_censored_unmatched_median(self) -> None:
        match = {
            "boundary_index": np.arange(4),
            "edge_normal": np.tile([1.0, 0.0], (4, 1)),
            "distance_px_all": np.ones(4),
            "reverse_distance_px_all": np.ones(4),
            "reverse_metric_boundary_index": np.arange(4),
            "reverse_metric_edge_normal": np.tile([1.0, 0.0], (4, 1)),
        }
        sensitivities = np.array([10.0, 5.0, 2.5, 1.25])
        jacobians = np.array(
            [[[value, 0.0], [0.0, 1.0]] for value in sensitivities]
        )
        result = gate.direct_edge_distance_metric(
            match,
            jacobians,
            np.tile([1.0, 0.0], (4, 1)),
            self.config["alignment"],
        )
        np.testing.assert_allclose(
            result["distance_m"], [0.1, 0.2, 0.4, 0.8]
        )
        self.assertAlmostEqual(result["median_m"], 0.3)
        self.assertAlmostEqual(result["p90_m"], 0.68)

        censored = {
            "boundary_index": np.array([0, 1]),
            "edge_normal": np.tile([1.0, 0.0], (2, 1)),
            "distance_px_all": np.array([0.0, 0.0, 80.0, 80.0, 80.0]),
            "reverse_distance_px_all": np.array([0.0]),
            "reverse_metric_boundary_index": np.array([0]),
            "reverse_metric_edge_normal": np.array([[1.0, 0.0]]),
        }
        censored_result = gate.direct_edge_distance_metric(
            censored,
            np.tile(np.eye(2), (5, 1, 1)),
            np.tile([1.0, 0.0], (5, 1)),
            self.config["alignment"],
        )
        self.assertAlmostEqual(censored_result["median_px"], 80.0)

    def test_asymmetric_direct_distribution_uses_point_median(self) -> None:
        count = 5
        match = {
            "boundary_index": np.arange(count),
            "edge_normal": np.tile([1.0, 0.0], (count, 1)),
            "distance_px_all": np.array([0.0, 0.0, 20.0, 20.0, 20.0]),
            "reverse_distance_px_all": np.zeros(count),
            "reverse_metric_boundary_index": np.arange(count),
            "reverse_metric_edge_normal": np.tile([1.0, 0.0], (count, 1)),
        }
        result = gate.direct_edge_distance_metric(
            match,
            np.tile(np.eye(2), (count, 1, 1)),
            np.tile([1.0, 0.0], (count, 1)),
            self.config["alignment"],
        )
        self.assertAlmostEqual(result["median_px"], 20.0)
        self.assertAlmostEqual(result["median_m"], 20.0)

    def test_direct_side_offsets_use_point_distribution_not_shift_norm(self) -> None:
        count = 4
        match = {
            "boundary_index": np.arange(count),
            "edge_normal": np.tile([1.0, 0.0], (count, 1)),
            "distance_px_all": np.array([7.0, 7.0, 5.0, 5.0]),
            "reverse_distance_px_all": np.zeros(count),
            "reverse_metric_boundary_index": np.arange(count),
            "reverse_metric_edge_normal": np.tile([1.0, 0.0], (count, 1)),
        }
        result = gate.direct_edge_distance_metric(
            match,
            np.tile(np.eye(2), (count, 1, 1)),
            np.tile([1.0, 0.0], (count, 1)),
            self.config["alignment"],
        )
        self.assertAlmostEqual(result["median_px"], 6.0)
        self.assertAlmostEqual(result["p90_px"], 7.0)
        self.assertNotAlmostEqual(result["median_px"], math.hypot(7.0, 5.0))

    def test_wrong_normal_edge_is_rejected_and_censored(self) -> None:
        y = np.arange(8, dtype=np.float64)
        boundary = np.column_stack([np.full_like(y, 10.0), y])
        match = gate.match_oriented_edges(
            boundary,
            np.tile([1.0, 0.0], (len(y), 1)),
            boundary.copy(),
            np.tile([0.0, 1.0], (len(y), 1)),
            self.config["alignment"],
        )
        self.assertEqual(match["matched_count"], 0)
        np.testing.assert_allclose(
            match["distance_px_all"],
            self.config["alignment"]["edge_search_radius_px"],
        )

    def test_rank_deficient_translation_design_fails_closed(self) -> None:
        with self.assertRaisesRegex(
            gate.GateContractError, "do not constrain both XY axes"
        ):
            gate.robust_translation_fit(
                np.tile([1.0, 0.0], (6, 1)),
                np.arange(6, dtype=np.float64),
                self.config["alignment"],
            )

    def test_fixed_periodic_edge_support_fails_spatial_null(self) -> None:
        boundary, normals = square_boundary(x0=80.0, y0=80.0, size=20)
        edges = [boundary]
        confidence = self.config["confidence"]
        for radius in confidence["deterministic_null_shift_radii_px"]:
            for angle_index in range(
                confidence["deterministic_null_angles_per_radius"]
            ):
                angle = (
                    2.0
                    * math.pi
                    * angle_index
                    / confidence["deterministic_null_angles_per_radius"]
                )
                edges.append(
                    boundary
                    + np.array(
                        [
                            radius * math.cos(angle),
                            radius * math.sin(angle),
                        ]
                    )
                )
        edge_xy = np.vstack(edges)
        edge_normals = np.tile(normals, (len(edges), 1))
        result = gate.deterministic_spatial_null(
            0.0,
            boundary,
            normals,
            edge_xy,
            edge_normals,
            self.config["alignment"],
            confidence,
            (240, 240),
        )
        self.assertFalse(result["passed"])
        self.assertEqual(result["reason"], "spatial_null_confidence_not_met")

    def test_zbuffer_keeps_front_boundary_and_removes_rear(self) -> None:
        cfg = copy.deepcopy(self.config["boundary_extraction"])
        cfg["minimum_boundary_points"] = 1
        cfg["minimum_visible_boundary_fraction"] = 0.4
        eave_xyz = np.array([[0.0, 0.0, 10.0], [0.0, 0.0, 12.0]])
        tangent = np.tile([1.0, 0.0], (2, 1))
        outward = np.tile([0.0, 1.0], (2, 1))
        source = np.array([3, 7])
        cloud = gate.TargetCloud(
            "B",
            np.zeros((4, 2)),
            eave_xyz.copy(),
            eave_xyz.copy(),
            ("synthetic",),
        )
        image = SimpleNamespace()
        camera = SimpleNamespace(width=100, height=100)
        depth_projection = (
            np.array([[10.0, 10.0], [10.0, 10.0]]),
            np.ones(2, dtype=bool),
            np.array([10.0, 12.0]),
        )
        with (
            mock.patch.object(
                gate,
                "_als_eave_boundary",
                return_value=(eave_xyz, tangent, outward, source),
            ),
            mock.patch.object(
                gate,
                "project_base_points_with_depth",
                side_effect=[depth_projection, depth_projection],
            ),
            mock.patch.object(
                gate,
                "project_base_points",
                side_effect=[
                    (np.array([[11.0, 10.0]]), np.array([True])),
                    (np.array([[10.0, 11.0]]), np.array([True])),
                ],
            ),
        ):
            visible = gate.visible_eave_boundary(
                cloud,
                image,
                camera,
                {},
                "orthometric",
                0.0,
                (0.0, 0.0),
                cfg,
            )
        np.testing.assert_array_equal(visible.source_index, [3])
        np.testing.assert_allclose(visible.camera_depth, [10.0])

    def _diagnostic_strength(
        self, shift: tuple[float, float], second: tuple[float, float] | None = None
    ) -> tuple[np.ndarray, np.ndarray]:
        boundary, _ = square_boundary(x0=40.0, y0=40.0, size=30)
        yy, xx = np.indices((130, 130), dtype=np.float64)
        strength = np.zeros((130, 130), dtype=np.float64)
        for dx, dy in [shift] + ([] if second is None else [second]):
            for point in boundary:
                strength += np.exp(
                    -(
                        (xx - (point[0] + dx)) ** 2
                        + (yy - (point[1] + dy)) ** 2
                    )
                    / (2.0 * 0.9**2)
                )
        return boundary, strength

    def test_translation_diagnostic_clean_integer_and_subpixel(self) -> None:
        for shift, tolerance in [((7.0, -5.0), 0.2), ((0.35, -0.40), 0.35)]:
            boundary, strength = self._diagnostic_strength(shift)
            result = gate.translation_multi_hypothesis_diagnostic(
                boundary, strength, self.config["confidence"]
            )
            self.assertLessEqual(abs(result["dx_px"] - shift[0]), tolerance)
            self.assertLessEqual(abs(result["dy_px"] - shift[1]), tolerance)
            self.assertFalse(result["ambiguous"])
            self.assertFalse(result["border_hit"])

    def test_translation_diagnostic_equal_distractors_are_ambiguous(self) -> None:
        boundary, strength = self._diagnostic_strength(
            (7.0, -5.0), second=(45.0, 40.0)
        )
        result = gate.translation_multi_hypothesis_diagnostic(
            boundary, strength, self.config["confidence"]
        )
        self.assertTrue(result["ambiguous"])

    def test_edge_localization_uncertainty_is_curvature_based(self) -> None:
        yy, xx = np.indices((96, 96), dtype=np.float64)
        gray = 255.0 / (1.0 + np.exp(-(xx - 48.35) / 0.8))
        _xy, _normal, info = gate.extract_subpixel_edges(
            gray, self.config["edge_extraction"]
        )
        sigma = np.asarray(info["localization_sigma_px"])
        self.assertTrue(np.isfinite(sigma).all())
        self.assertTrue(np.all((sigma >= 0.02) & (sigma <= 2.0)))
        self.assertIn("strength_image", info)

    @staticmethod
    def _systematic_rows(east: float, north: float) -> list[dict[str, str]]:
        rows: list[dict[str, str]] = []
        for building in range(3):
            for view in range(10):
                jitter = (view - 4.5) * 0.0002
                rows.append(
                    {
                        "building_id": f"B{building}",
                        "valid": gate.CSV_TRUE,
                        "equivalent_dE_m": str(east + jitter),
                        "equivalent_dN_m": str(north - jitter),
                    }
                )
        return rows

    def test_systematic_is_equal_building_weight_cluster_bootstrap(self) -> None:
        cfg = copy.deepcopy(self.config["gate"])
        cfg["systematic_bootstrap_samples"] = 200
        small = gate.systematic_translation(
            self._systematic_rows(0.02, -0.01), cfg
        )
        self.assertEqual(
            small["building_weighting"], "equal_after_per_building_view_median"
        )
        self.assertTrue(small["bootstrap_available"])
        self.assertTrue(small["systematic_negligible"])
        large = gate.systematic_translation(
            self._systematic_rows(0.12, 0.0), cfg
        )
        self.assertFalse(large["systematic_negligible"])

    def test_systematic_does_not_weight_building_by_view_count(self) -> None:
        cfg = copy.deepcopy(self.config["gate"])
        cfg["systematic_bootstrap_samples"] = 200
        rows: list[dict[str, str]] = []
        for building, view_count, east in [
            ("A", 30, 0.0),
            ("B", 10, 0.12),
            ("C", 10, 0.12),
        ]:
            for _ in range(view_count):
                rows.append(
                    {
                        "building_id": building,
                        "valid": gate.CSV_TRUE,
                        "equivalent_dE_m": str(east),
                        "equivalent_dN_m": "0.0",
                    }
                )
        result = gate.systematic_translation(rows, cfg)
        self.assertAlmostEqual(result["global_median_e_m"], 0.12)
        self.assertFalse(result["systematic_negligible"])

    def test_global_image_split_is_consistent_across_buildings(self) -> None:
        views = [
            gate.SelectedView("B1", 1, "same.png", 1, 1, "x", 30, 0.2, 20.0),
            gate.SelectedView("B2", 1, "same.png", 1, 1, "x", 30, 0.2, 20.0),
        ]
        assigned = gate.assign_registration_splits(
            views, self.config["micro_registration"]
        )
        self.assertEqual(
            assigned[0].registration_split, assigned[1].registration_split
        )

    def test_building_gate_requires_all_selected_views(self) -> None:
        target = gate.Target("B", 1, "core", "surface")
        rows = [
            {
                "building_id": "B",
                "valid": gate.CSV_TRUE,
                "median_residual_m": "0.20",
                "median_residual_px": "2.0",
                "equivalent_dE_m": "0.01",
                "equivalent_dN_m": "0.00",
            }
            for _ in range(10)
        ]
        summary = gate.summarize_buildings(
            [target],
            rows,
            self.config["gate"],
            self.config["view_selection"],
            gate.RAW_ATTEMPT,
        )[0]
        self.assertTrue(summary["building_numeric_gate_met"])
        rows[-1]["valid"] = gate.CSV_FALSE
        summary = gate.summarize_buildings(
            [target],
            rows,
            self.config["gate"],
            self.config["view_selection"],
            gate.RAW_ATTEMPT,
        )[0]
        self.assertFalse(summary["building_numeric_gate_met"])

    def test_provisional_queue_is_not_relabelled_as_no_overlap(self) -> None:
        targets = gate.load_targets(
            gate.repo_path(self.config["inputs"]["targets_csv"]),
            self.config,
            "core",
        )
        self.assertEqual(len(targets), 28)
        self.assertEqual(
            {target.queue_status for target in targets},
            {"provisional_gs4_overlap_unresolved"},
        )
        self.assertNotIn(
            "no overlap",
            self.config["target_queue_contract"][
                "gs4_overlap_interpretation"
            ],
        )

    def test_residual_schema_has_all_numeric_evidence(self) -> None:
        required = {
            "median_residual_px",
            "p90_residual_px",
            "median_residual_m",
            "p90_residual_m",
            "forward_p90_residual_px",
            "reverse_p90_residual_px",
            "edge_localization_uncertainty_p90_m",
            "translation_diagnostic_relative_margin",
            "observability_p90_m_per_px",
            "predicted_metric_uncertainty_m",
            "azimuth_bin",
        }
        self.assertTrue(required.issubset(gate.RESIDUAL_FIELDS))

    def test_per_building_checkpoint_is_immediate_and_resumable(self) -> None:
        target = gate.Target("B", 1, "core", "surface")
        views = [
            gate.SelectedView("B", index + 1, f"{index}.png", index, 1, "x", 30, 0.2, 20.0)
            for index in range(10)
        ]
        rows = [
            {
                "building_id": "B",
                "attempt": gate.RAW_ATTEMPT,
                "valid": gate.CSV_TRUE,
                "median_residual_m": "0.20",
                "median_residual_px": "2.0",
                "equivalent_dE_m": "0.01",
                "equivalent_dN_m": "0.00",
                "view": f"{index}.png",
                "view_order": index + 1,
            }
            for index in range(10)
        ]
        identity = gate.CheckpointIdentity(
            config_sha256="a" * 64,
            input_sha256="b" * 64,
            view_sha256="c" * 64,
            implementation_sha256="d" * 64,
        )
        with tempfile.TemporaryDirectory() as temporary:
            store = gate.AlignmentCheckpointStore(Path(temporary) / "checkpoints")
            arguments = (
                [target],
                views,
                {"B": object()},
                {},
                {},
                {},
                {},
                "orthometric",
                0.0,
                Path("datum.json"),
                self.config["boundary_extraction"],
                self.config["edge_extraction"],
                self.config["alignment"],
                self.config["confidence"],
                {"B": (0.0, 0.0)},
                {"B": "not_applicable"},
                gate.RAW_ATTEMPT,
                Path("images.bin"),
                "e" * 64,
                Path("cameras.bin"),
                "f" * 64,
                store,
                identity,
                self.config["gate"],
                self.config["view_selection"],
                self.config["micro_registration"],
            )
            with (
                mock.patch.object(gate, "measure_all", return_value=copy.deepcopy(rows)) as measured,
                mock.patch.object(
                    gate,
                    "_representative_overlay_bytes",
                    return_value=b"\x89PNG\r\n\x1a\nsynthetic",
                ),
            ):
                first, refs = gate.measure_all_checkpointed(*arguments)
                second, resumed_refs = gate.measure_all_checkpointed(*arguments)
            self.assertEqual(len(first), 10)
            self.assertEqual(len(second), 10)
            self.assertEqual(
                [row["median_residual_m"] for row in first],
                [row["median_residual_m"] for row in second],
            )
            self.assertEqual(refs, resumed_refs)
            self.assertEqual(measured.call_count, 1)
            self.assertEqual(
                store.resume_status(identity, "B", gate.RAW_ATTEMPT).state,
                "completed",
            )

    def test_stage_stop_is_raised_only_after_third_checkpoint_is_durable(
        self,
    ) -> None:
        targets = [
            gate.Target(f"B{index}", index, "core", "surface")
            for index in range(1, 4)
        ]
        views = [
            gate.SelectedView(
                target.building_id,
                1,
                f"{target.building_id}.png",
                1,
                1,
                "x",
                30,
                0.2,
                20.0,
            )
            for target in targets
        ]
        identity = gate.CheckpointIdentity(
            config_sha256="a" * 64,
            input_sha256="b" * 64,
            view_sha256="c" * 64,
            implementation_sha256="d" * 64,
        )

        def exception_row(building_id: str) -> dict[str, object]:
            return {
                "building_id": building_id,
                "attempt": gate.RAW_ATTEMPT,
                "valid": gate.CSV_FALSE,
                "status_reason": (
                    "GateContractError:robust translation IRLS did not converge"
                ),
                "view": f"{building_id}.png",
                "view_order": 1,
                "registration_split": "fit",
                "diagnostic_only": gate.CSV_TRUE,
            }

        def fake_measure_all(selected_targets, *_args, **_kwargs):
            return [exception_row(selected_targets[0].building_id)]

        def fake_measure_view(selected_view, *_args, **_kwargs):
            return exception_row(selected_view.building_id)

        with tempfile.TemporaryDirectory() as temporary:
            store = gate.AlignmentCheckpointStore(Path(temporary) / "checkpoints")
            arguments = (
                targets,
                views,
                {target.building_id: object() for target in targets},
                {1: object()},
                {view.name: object() for view in views},
                {view.name: Path(view.name) for view in views},
                {},
                "orthometric",
                0.0,
                Path("datum.json"),
                self.config["boundary_extraction"],
                self.config["edge_extraction"],
                self.config["alignment"],
                self.config["confidence"],
                {target.building_id: (0.0, 0.0) for target in targets},
                {target.building_id: "not_applicable" for target in targets},
                gate.RAW_ATTEMPT,
                Path("images.bin"),
                "e" * 64,
                Path("cameras.bin"),
                "f" * 64,
                store,
                identity,
                self.config["gate"],
                self.config["view_selection"],
                self.config["micro_registration"],
            )
            with (
                mock.patch.object(
                    gate, "measure_all", side_effect=fake_measure_all
                ),
                mock.patch.object(
                    gate, "measure_view", side_effect=fake_measure_view
                ),
                mock.patch.object(
                    gate,
                    "_representative_overlay_bytes",
                    return_value=b"\x89PNG\r\n\x1a\nsynthetic",
                ),
            ):
                with self.assertRaisesRegex(
                    gate.GateContractError,
                    "same error type reached three consecutive buildings",
                ):
                    gate.measure_all_checkpointed(*arguments)

            for target in targets:
                self.assertEqual(
                    store.resume_status(
                        identity, target.building_id, gate.RAW_ATTEMPT
                    ).state,
                    "completed",
                )
                rows = gate._read_completed_checkpoint_rows(
                    store,
                    identity,
                    target.building_id,
                    gate.RAW_ATTEMPT,
                )
                self.assertEqual(len(rows), 1)
                self.assertEqual(
                    rows[0]["status_reason"],
                    "GateContractError:robust translation IRLS did not converge",
                )

    def test_version_publish_switches_one_current_pointer(self) -> None:
        publication = self.config["publication"]
        outputs = self.config["outputs"]
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            staging = gate._prepare_staging(root, publication)
            for filename in outputs.values():
                path = staging / filename
                if filename == outputs["overlay_dir"]:
                    path.mkdir()
                    (path / "B.png").write_bytes(b"\x89PNG\r\n\x1a\nx")
                else:
                    path.write_text(filename, encoding="utf-8")
            result = gate._publish_staging(
                staging, root, outputs, publication, replace=False
            )
            current = root / publication["current_pointer"]
            self.assertTrue(current.is_symlink())
            self.assertTrue(result["atomic_switch_complete"])
            for filename in outputs.values():
                fixed = root / filename
                self.assertTrue(fixed.is_symlink())
                self.assertTrue(fixed.resolve().exists())


if __name__ == "__main__":
    unittest.main()
