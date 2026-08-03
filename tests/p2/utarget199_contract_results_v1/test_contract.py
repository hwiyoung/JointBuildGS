from __future__ import annotations

import unittest

from scripts.p2.utarget199_contract_results_v1.contract import (
    _g4_candidate,
    associate_components,
    validate_config,
)


class ContractTest(unittest.TestCase):
    def test_canonical_config_is_exact_199x3(self) -> None:
        result = validate_config()
        self.assertEqual(result["buildings"], 199)
        self.assertEqual(result["expected_rows"], 597)
        self.assertIsNone(result["scientific_verdict"])

    def test_bbox_association_retains_unassociated_and_flags_shared(self) -> None:
        roster = [
            {"stable_id": "A", "bbox": [0.0, 0.0, 1.0, 1.0], "reference_patch_ids": (), "candidate_split": "development"},
            {"stable_id": "B", "bbox": [0.0, 0.0, 1.0, 1.0], "reference_patch_ids": (), "candidate_split": "held_out"},
        ]
        components = []
        for method in ("C1_L_upper", "C2_MVS", "C3_GS_image"):
            components.append({"condition_id": method, "component_id": f"{method}_X", "cells": [[0, 0]]})
        result = associate_components(roster, components, [0.0, 0.0], 1.0)
        self.assertEqual(len(result), 6)
        self.assertTrue(all(row["association_status"] == "SHARED_COMPONENT" for row in result))
        self.assertTrue(all(row["one_to_one_building_component"] is False for row in result))

    def test_candidate_g4_requires_every_metric(self) -> None:
        thresholds = {
            "reference_vertical_coverage_min": 0.8,
            "height_error_mae_m_max": 1.0,
            "RMSZ_m_max": 1.0,
            "RMSXY_m_max": 1.0,
            "surface_distance_rmse_m_max": 1.0,
            "surface_distance_p95_m_max": 2.0,
        }
        passing = {
            "reference_vertical_coverage": 0.9,
            "height_error_mae_m": 0.5,
            "RMSZ_m": 0.7,
            "RMSXY_m": 0.4,
            "surface_distance_rmse_m": 0.8,
            "surface_distance_p95_m": 1.5,
        }
        self.assertTrue(_g4_candidate(passing, thresholds))
        self.assertIsNone(_g4_candidate({**passing, "RMSZ_m": None}, thresholds))


if __name__ == "__main__":
    unittest.main()
