#!/usr/bin/env python3
"""Contract tests for dense qualitative v3 reference-roof photo overlays."""
from __future__ import annotations

import copy
import importlib.util
import inspect
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import numpy as np


REPO = Path(__file__).resolve().parents[2]
MODULE_PATH = (
    REPO
    / "phases/p2-gsjso/scripts/fusion_w1/fusion_w1_dense_baseline_qualitative_v3_20260728.py"
)
SPEC = importlib.util.spec_from_file_location(
    "fusion_w1_dense_baseline_qualitative_v3", MODULE_PATH
)
if SPEC is None or SPEC.loader is None:  # pragma: no cover
    raise RuntimeError(f"cannot import {MODULE_PATH}")
qual = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = qual
SPEC.loader.exec_module(qual)


class DenseBaselineQualitativeV3Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.config = qual.load_config()
        cls.result = qual.BASE.select_sample(cls.config)

    def test_input_only_sample_is_frozen_before_reference_access(self) -> None:
        observed = tuple(row["building_id"] for row in self.result.selected)
        self.assertEqual(observed, qual.EXPECTED_SELECTED)
        self.assertEqual(observed, tuple(self.config["sample_freeze"]["selected_building_ids"]))
        self.assertEqual(
            qual.BASE.set_sha256(observed),
            self.config["sample_freeze"]["selected_set_sha256"],
        )
        self.assertEqual(len(self.result.population_ids), 114)

    def test_row_one_allows_only_reference_roof_exterior_boundary(self) -> None:
        contract = self.config["photo_projection_contract"]
        self.assertEqual(
            contract["allowed_photo_overlay"],
            "reference RoofSurface exterior boundary only",
        )
        self.assertIn("evaluation-only", contract["overlay_source"])
        for key in (
            "dense_point_overlay_forbidden",
            "dense_tin_boundary_overlay_forbidden",
            "footprint_overlay_forbidden",
            "filled_polygon_overlay_forbidden",
            "interior_ring_overlay_forbidden",
        ):
            self.assertTrue(contract[key])

    def test_photo_panel_source_has_no_point_scatter_or_fill(self) -> None:
        source = inspect.getsource(qual.projected_reference_photo_panel)
        self.assertNotIn("ax.scatter", source)
        self.assertNotIn("fill(", source)
        self.assertNotIn("fill_between", source)
        self.assertNotIn("points", inspect.signature(qual.projected_reference_photo_panel).parameters)
        self.assertNotIn("boundary", inspect.signature(qual.projected_reference_photo_panel).parameters)
        self.assertIn("reference_rings", inspect.signature(qual.projected_reference_photo_panel).parameters)

    def test_reference_rings_preserve_xyz_and_close_without_flattening(self) -> None:
        ring = np.asarray(
            [[0.0, 0.0, 10.0], [1.0, 0.0, 10.4], [1.0, 1.0, 11.0], [0.0, 1.0, 10.2]],
            dtype=np.float64,
        )
        closed = qual._closed_ring(ring)
        self.assertEqual(closed.shape, (5, 3))
        np.testing.assert_allclose(closed[0], closed[-1])
        self.assertGreater(float(np.ptp(closed[:, 2])), 0.9)

    def test_projection_receipt_enforces_all_vertices_inside_margin(self) -> None:
        ring = np.asarray(
            [[30.0, 30.0, 5.0], [70.0, 30.0, 5.0], [70.0, 70.0, 5.0], [30.0, 70.0, 5.0]],
            dtype=np.float64,
        )
        camera = SimpleNamespace(width=100, height=100)
        view = SimpleNamespace(camera=camera, pose=object())

        def fake_project(points, *_args, **_kwargs):
            values = np.asarray(points, dtype=np.float64)
            return qual.BASE.ProjectionResult(
                uv=values[:, :2],
                depth=np.full(len(values), 5.0),
                valid=np.ones(len(values), dtype=bool),
            )

        with mock.patch.object(qual.BASE, "project_base_points", side_effect=fake_project):
            _uv, receipt = qual.project_reference_roof_boundaries(
                [ring], view, {}, self.config
            )
        self.assertTrue(receipt["all_vertices_valid"])
        self.assertTrue(receipt["all_vertices_inside_margin"])
        self.assertEqual(receipt["rings_n"], 1)
        self.assertEqual(receipt["vertices_n"], 5)
        self.assertAlmostEqual(receipt["bbox_area_px2"], 1600.0)

    def test_projection_receipt_rejects_edge_crossing_even_when_in_frame(self) -> None:
        ring = np.asarray(
            [[2.0, 30.0, 5.0], [70.0, 30.0, 5.0], [70.0, 70.0, 5.0], [2.0, 70.0, 5.0]],
            dtype=np.float64,
        )
        view = SimpleNamespace(camera=SimpleNamespace(width=100, height=100), pose=object())

        def fake_project(points, *_args, **_kwargs):
            values = np.asarray(points, dtype=np.float64)
            return qual.BASE.ProjectionResult(
                uv=values[:, :2],
                depth=np.full(len(values), 5.0),
                valid=np.ones(len(values), dtype=bool),
            )

        with mock.patch.object(qual.BASE, "project_base_points", side_effect=fake_project):
            _uv, receipt = qual.project_reference_roof_boundaries(
                [ring], view, {}, self.config
            )
        self.assertTrue(receipt["all_vertices_valid"])
        self.assertFalse(receipt["all_vertices_inside_margin"])

    def test_view_ranking_contract_prioritizes_visibility_then_centrality(self) -> None:
        ranking = self.config["photo_projection_contract"]["view_ranking"]
        self.assertLess(ranking.index("visibility fraction"), ranking.index("frame centre"))
        self.assertLess(ranking.index("frame centre"), ranking.index("boundary bbox area"))
        self.assertIn("occluded views never fill empty slots", ranking)

    def test_chunked_first_intersection_detects_near_occluder(self) -> None:
        origin = np.asarray([0.0, 0.0, 0.0], dtype=np.float64)
        directions = np.asarray([[0.0, 0.0, 1.0]], dtype=np.float64)
        triangles = np.asarray(
            [
                [[-1.0, -1.0, 5.0], [1.0, -1.0, 5.0], [0.0, 1.0, 5.0]],
                [[-2.0, -2.0, 10.0], [2.0, -2.0, 10.0], [0.0, 2.0, 10.0]],
            ],
            dtype=np.float64,
        )
        observed = qual._nearest_intersection_distances(origin, directions, triangles, 1)
        self.assertAlmostEqual(float(observed[0]), 5.0, places=8)

    def test_visible_slot_policy_never_invents_occluded_view(self) -> None:
        one = qual.photo_slot_plan([{"name": "visible.jpg"}])
        self.assertEqual([slot["crop_profile"] for slot in one], ["full", "medium", "tight"])
        self.assertEqual({slot["view"]["name"] for slot in one}, {"visible.jpg"})
        two = qual.photo_slot_plan([{"name": "a.jpg"}, {"name": "b.jpg"}])
        self.assertEqual([slot["view"]["name"] for slot in two], ["a.jpg", "b.jpg", "a.jpg"])
        self.assertEqual([slot["crop_profile"] for slot in two], ["medium", "medium", "tight"])

    def test_visibility_and_tier_contracts_are_fail_closed(self) -> None:
        contract = self.config["photo_projection_contract"]
        visibility = contract["visibility_gate"]
        self.assertIn("first-intersection", visibility["raycast_engine"])
        self.assertGreaterEqual(visibility["surrounding_scene_aoi_margin_m"], 50.0)
        self.assertGreater(visibility["minimum_visible_fraction"], 0.0)
        self.assertEqual(
            contract["eligibility_tiers"],
            [
                "tier_1_all_boundary_vertices_inside_5_percent_margin_and_target_roof_raycast_visible",
                "tier_2_fallback_all_boundary_vertices_inside_full_frame_and_target_roof_raycast_visible",
            ],
        )

    def test_reference_role_and_postfreeze_influence_are_explicit(self) -> None:
        contract = self.config["photo_projection_contract"]
        self.assertEqual(contract["overlay_role"].split(";")[0], "evaluation_only")
        self.assertIn("after population and nine-building sample freeze", contract["overlay_role"])
        binding = self.config["selection_contract"]["representative_photo_binding"]
        self.assertIn("after the input-only nine-building sample is frozen", binding)

    def test_rows_two_to_four_keep_v2_meanings(self) -> None:
        rows = self.config["visual_contract"]["row_order"]
        base = qual.BASE.load_config()
        self.assertEqual(rows[1:], base["visual_contract"]["row_order"][1:])
        self.assertEqual(self.config["visual_overrides"]["rows_2_to_4"], "unchanged_from_v2")

    def test_wrapper_is_cpu_only_and_overwrite_refusing(self) -> None:
        wrapper = (
            REPO
            / "phases/p2-gsjso/scripts/fusion_w1/run_fusion_w1_dense_baseline_qualitative_v3_20260728.sh"
        ).read_text(encoding="utf-8")
        self.assertIn("--network=none", wrapper)
        self.assertIn("--read-only", wrapper)
        self.assertIn("--cpus=6", wrapper)
        self.assertNotIn("--gpus", wrapper)
        self.assertIn("output exists; overwrite refused", wrapper)
        self.assertIn("$OUTPUT_PARENT_REL:rw", wrapper)

    def test_config_is_verdict_free_and_uses_new_output_namespace(self) -> None:
        self.assertEqual(self.config["publication"]["learning_runs_started"], 0)
        self.assertIsNone(self.config["publication"]["scientific_verdict"])
        self.assertIsNone(self.config["publication"]["interpretation"])
        self.assertTrue(self.config["outputs"]["root"].endswith("_v3"))
        self.assertTrue(self.config["outputs"]["multipage_pdf"].endswith("_v3.pdf"))

    def test_v3_does_not_import_retired_projection_helper(self) -> None:
        source = MODULE_PATH.read_text(encoding="utf-8")
        self.assertNotIn("T7.project_points", source)
        self.assertNotIn("07_failure_diagnosis.py", source)
        self.assertIn("BASE.project_base_points", source)

    def test_config_rejects_row_one_overlay_relaxation(self) -> None:
        raw = json.loads(qual.DEFAULT_CONFIG.read_text(encoding="utf-8"))
        raw["photo_projection_contract"]["dense_point_overlay_forbidden"] = False
        with tempfile.TemporaryDirectory(prefix="dense-v3-config-test-") as temporary:
            path = Path(temporary) / "config.json"
            path.write_text(json.dumps(raw), encoding="utf-8")
            with self.assertRaisesRegex(qual.DenseBaselineV3Error, "prohibition absent"):
                qual.load_config(path, verify_sources=False)

    def test_config_rejects_sample_freeze_drift(self) -> None:
        raw = json.loads(qual.DEFAULT_CONFIG.read_text(encoding="utf-8"))
        raw["sample_freeze"]["selected_building_ids"] = list(reversed(raw["sample_freeze"]["selected_building_ids"]))
        with tempfile.TemporaryDirectory(prefix="dense-v3-config-test-") as temporary:
            path = Path(temporary) / "config.json"
            path.write_text(json.dumps(raw), encoding="utf-8")
            with self.assertRaisesRegex(qual.DenseBaselineV3Error, "sample freeze drift"):
                qual.load_config(path, verify_sources=False)


if __name__ == "__main__":
    unittest.main()
