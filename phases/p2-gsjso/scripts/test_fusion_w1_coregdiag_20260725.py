#!/usr/bin/env python3
"""Result-blind unit and contract tests for the 2026-07-25 coreg diagnosis."""

from __future__ import annotations

import importlib.util
import json
import sys
import unittest
from pathlib import Path

import numpy as np
from shapely.geometry import Polygon


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "phases/p2-gsjso/scripts/fusion_w1_coregdiag_20260725.py"
SPEC = importlib.util.spec_from_file_location("fusion_w1_coregdiag_20260725", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
DIAG = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = DIAG
SPEC.loader.exec_module(DIAG)


class CoregDiagnosticTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.config = DIAG.load_config(DIAG.DEFAULT_CONFIG)

    def group(
        self,
        *,
        fixed: np.ndarray,
        moving: np.ndarray,
        surface: str = "roof",
    ) -> object:
        fixed = np.asarray(fixed, dtype=np.float64)
        moving = np.asarray(moving, dtype=np.float64)
        fixed_normals = np.tile(np.array([[0.0, 0.0, 1.0]]), (len(fixed), 1))
        moving_normals = np.tile(np.array([[0.0, 0.0, 1.0]]), (len(moving), 1))
        return DIAG.DiagnosticGroup(
            building_id="DEBY_LOD2_SYNTH",
            tier="surface",
            surface=surface,
            fixed=fixed,
            moving=moving,
            fixed_normals=fixed_normals,
            moving_normals=moving_normals,
        )

    def test_nearest_rank_is_explicit(self) -> None:
        values = list(range(1, 11))
        self.assertEqual(DIAG.nearest_rank(values, 0.1), 1.0)
        self.assertEqual(DIAG.nearest_rank(values, 0.25), 3.0)
        self.assertEqual(DIAG.nearest_rank(values, 0.5), 5.0)

    def test_matched_residual_and_offset_sign(self) -> None:
        group = self.group(
            fixed=np.array([[0.0, 0.0, 0.0], [0.2, 0.0, 0.0]]),
            moving=np.array([[0.0, 0.0, 0.1], [0.2, 0.0, 0.1]]),
        )
        polygon = Polygon([(-1, -1), (1, -1), (1, 1), (-1, 1)])
        metric, offset, _, _, _ = DIAG.evaluate_building(
            self.config,
            [group],
            np.eye(4),
            "before",
            polygon,
            source_population="synthetic",
            tier="surface",
            population_role="synthetic",
        )
        self.assertAlmostEqual(metric["matched_median_m"], 0.1)
        self.assertAlmostEqual(metric["censored_p90_m"], 0.1)
        self.assertEqual(metric["correspondence_n"], 2)
        self.assertEqual(metric["pooled_matched_observations_n"], 4)
        self.assertAlmostEqual(offset["median_dZ_m"], 0.1)
        self.assertAlmostEqual(offset["median_r_vertical_m"], 0.1)

    def test_unmatched_is_censored_not_measured(self) -> None:
        group = self.group(
            fixed=np.array([[0.0, 0.0, 0.0]]),
            moving=np.array([[2.0, 0.0, 0.0]]),
        )
        polygon = Polygon([(-1, -1), (3, -1), (3, 1), (-1, 1)])
        metric, offset, counter, exposure, _ = DIAG.evaluate_building(
            self.config,
            [group],
            np.eye(4),
            "before",
            polygon,
            source_population="synthetic",
            tier="surface",
            population_role="synthetic",
        )
        self.assertIsNone(metric["matched_median_m"])
        self.assertAlmostEqual(metric["censored_median_m"], 0.35)
        self.assertEqual(metric["correspondence_n"], 0)
        self.assertEqual(offset["matched_pair_n"], 0)
        self.assertEqual(sum(counter.values()), 2)
        self.assertTrue(all(key[7].startswith("unmatched_") for key in counter))
        rows = DIAG.tail_rows(counter, exposure)
        aggregate = [
            row for row in rows if row["row_type"] == "exposure_complete_aggregate"
        ]
        self.assertEqual(len(aggregate), 4)
        self.assertTrue(all(row["exposure_n"] == 1 for row in aggregate))

    def test_tier_fraction_keeps_capable_missing_in_denominator(self) -> None:
        rows = [
            {
                "tier": "surface",
                "correspondence_capable": True,
                "before_matched_median_m": 0.2,
                "before_matched_p90_m": 0.25,
                "before_censored_median_m": 0.2,
                "before_censored_p90_m": 0.35,
                "before_correspondence_n": 100,
                "before_bidirectional_support": 0.8,
                "after_matched_median_m": 0.2,
                "after_matched_p90_m": 0.25,
                "after_censored_median_m": 0.2,
                "after_censored_p90_m": 0.35,
                "after_correspondence_n": 100,
                "after_bidirectional_support": 0.8,
            },
            {
                "tier": "surface",
                "correspondence_capable": True,
                "before_matched_median_m": None,
                "before_matched_p90_m": None,
                "before_censored_median_m": None,
                "before_censored_p90_m": None,
                "before_correspondence_n": 40,
                "before_bidirectional_support": None,
                "after_matched_median_m": None,
                "after_matched_p90_m": None,
                "after_censored_median_m": None,
                "after_censored_p90_m": None,
                "after_correspondence_n": 0,
                "after_bidirectional_support": None,
            },
        ]
        summary = DIAG.tier_summary_rows(rows, 40)
        after_all = next(
            row for row in summary if row["state"].startswith("diagnostic") and row["tier"] == "all"
        )
        self.assertEqual(after_all["matched_median_missing_n"], 1)
        self.assertAlmostEqual(after_all["matched_median_le_0p3_fraction"], 0.5)

    def test_block_inventory_keeps_zero_group_blocks(self) -> None:
        rows = DIAG.block_inventory_rows(
            {"blocks": ["capture_block_01"], "rows": []},
            [{"building_id": "DEBY_LOD2_SYNTH", "role": "fit"}],
            {"DEBY_LOD2_SYNTH": {"tier": "surface"}},
            [
                "capture_block_01",
                "capture_block_02",
                "capture_block_03",
            ],
        )
        self.assertEqual(len(rows), 6)
        self.assertEqual(
            {row["capture_block"] for row in rows},
            {
                "capture_block_01",
                "capture_block_02",
                "capture_block_03",
            },
        )
        self.assertTrue(all(row["block_group_used"] is False for row in rows))

    def test_proxy_categories_use_locked_priority(self) -> None:
        polygon = Polygon([(0, 0), (10, 0), (10, 10), (0, 10)])
        photo = np.array([[0.6, 5.0, 10.0], [5.0, 5.0, 10.0]])
        als = np.array([[0.6, 5.0, 9.9], [5.0, 5.0, 9.9]])
        roof = DIAG.proxy_categories(self.config, polygon, "roof", photo, als)
        self.assertEqual(roof.tolist(), [
            "roof_edge_or_facade_proxy",
            "roof_interior_class6_proxy",
        ])
        ground_photo = np.array(
            [[1.0, 1.0, 1.0], [2.0, 2.0, -1.0], [3.0, 3.0, 0.1]]
        )
        ground_als = np.zeros((3, 3))
        ground = DIAG.proxy_categories(
            self.config, polygon, "ground", ground_photo, ground_als
        )
        self.assertEqual(
            ground.tolist(),
            [
                "above_ground_vegetation_or_moving_clutter_proxy",
                "below_ground_or_occlusion_proxy",
                "ground_class2_proxy",
            ],
        )

    def test_population_join_is_exact(self) -> None:
        targets, ladder = DIAG.load_population(self.config)
        self.assertEqual(len(targets), 178)
        self.assertEqual(len(ladder), 178)
        self.assertEqual(
            {row["tier"] for row in targets},
            {"surface", "height", "outline"},
        )

    def test_candidate_is_diagnostic_not_adopted(self) -> None:
        selection = json.loads(
            DIAG.repo_path(self.config["inputs"]["global_selection"]).read_text()
        )
        self.assertEqual(selection["choice"], "none")
        self.assertEqual(selection["status"], "BLOCK_REQUIRED")
        self.assertFalse(self.config["states"]["after"]["adopted_for_learning"])
        np.testing.assert_array_equal(
            np.asarray(self.config["states"]["after"]["matrix"]),
            np.asarray(
                selection["block_base_photo_to_als_global_pivot_matrix"]
            ),
        )

    def test_gate_uses_only_matched_median(self) -> None:
        gate = self.config["correspondence_capability"]
        self.assertEqual(gate["gate_numeric_threshold_m"], 0.3)
        self.assertTrue(gate["p90_and_support_are_auxiliary_only"])
        self.assertIn("matched", gate["gate_statistic"])

    def test_learning_and_source_writes_are_forbidden(self) -> None:
        self.assertTrue(self.config["execution"]["learning_forbidden"])
        coordinate = self.config["coordinate_contract"]
        self.assertTrue(coordinate["source_als_modification_forbidden"])
        self.assertTrue(coordinate["source_photo_modification_forbidden"])
        self.assertTrue(coordinate["source_pose_modification_forbidden"])
        self.assertEqual(
            set(self.config["implementation_files"]),
            {
                "phases/p2-gsjso/configs/fusion_w1_coregdiag_20260725.json",
                "phases/p2-gsjso/scripts/fusion_w1_coregdiag_20260725.py",
                "phases/p2-gsjso/scripts/run_fusion_w1_coregdiag_20260725.sh",
                "phases/p2-gsjso/scripts/test_fusion_w1_coregdiag_20260725.py",
            },
        )

    def test_tail_definitions_distinguish_censoring(self) -> None:
        tail = self.config["tail"]
        self.assertIn("strictly greater", tail["matched_tail_definition"])
        self.assertIn("unmatched", tail["censored_tail_definition"])
        self.assertTrue(tail["capture_block_not_available_for_raw_dense"])

    def test_signed_horizontal_scalar_is_not_directional(self) -> None:
        self.assertIn("unsigned", self.config["offsets"]["horizontal_scalar"])
        self.assertEqual(self.config["offsets"]["sign"], "photo_minus_als")


if __name__ == "__main__":
    unittest.main()
