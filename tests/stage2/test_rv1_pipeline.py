#!/usr/bin/env python3
from __future__ import annotations

import json
import math
import tempfile
import unittest
from pathlib import Path

import numpy as np

from src.pipelines import rv1


class TestSurfaceMetrics(unittest.TestCase):
    def test_symmetric_point_distance(self) -> None:
        a = np.asarray([[0.0, 0.0, 0.0], [2.0, 0.0, 0.0]])
        b = np.asarray([[0.1, 0.0, 0.0], [2.3, 0.0, 0.0]])
        np.testing.assert_allclose(rv1.nearest_distances(a, b), [0.1, 0.3])
        np.testing.assert_allclose(rv1.nearest_distances(b, a), [0.1, 0.3])

    def test_precision_recall_fscore(self) -> None:
        precision, recall, fscore = rv1.precision_recall_fscore(
            np.asarray([0.05, 0.15]), np.asarray([0.05, 0.30]), 0.1
        )
        self.assertEqual(precision, 0.5)
        self.assertEqual(recall, 0.5)
        self.assertEqual(fscore, 0.5)

    def test_missing_metric_handling(self) -> None:
        values = rv1.precision_recall_fscore(np.empty(0), np.asarray([0.1]), 0.2)
        self.assertTrue(all(math.isnan(value) for value in values))


class TestRelativeClassification(unittest.TestCase):
    @staticmethod
    def row(index: int, fscore: float, distance: float, plane: float, rmsz: float) -> dict:
        return {
            "building_id": f"B{index}",
            "surface_fscore_0p2m": fscore,
            "bidirectional_distance_p95_m": distance,
            "roof_plane_f1": plane,
            "rmsz_m": rmsz,
            "roofer_success": True,
            "has_lod22": True,
            "val3dity_lod22_valid": True,
            "processing_status": "success",
            "scientific_status": rv1.SCIENTIFIC_STATUS,
        }

    def test_percentile_rank_average_ties_and_inverse(self) -> None:
        self.assertEqual(rv1.percentile_ranks([1.0, 2.0, 2.0]), [0.0, 0.75, 0.75])
        self.assertEqual(rv1.percentile_ranks([1.0, 2.0, 2.0], inverse=True), [1.0, 0.25, 0.25])

    def test_q40_q50_q60_r_classification_and_rx_instability(self) -> None:
        rows = [
            self.row(0, 0.1, 1.0, 0.1, 1.0),
            self.row(1, 0.25, 0.85, 0.25, 0.85),
            self.row(2, 0.4, 0.7, 0.4, 0.7),
            self.row(3, 0.55, 0.55, 0.55, 0.55),
            self.row(4, 0.7, 0.4, 0.7, 0.4),
            self.row(5, 0.9, 0.1, 0.9, 0.1),
        ]
        classified, sensitivity, thresholds = rv1.classify_rows(rows, [0.4, 0.5, 0.6])
        self.assertEqual(len(sensitivity), 18)
        self.assertEqual(set(thresholds), {"q40", "q50", "q60"})
        self.assertEqual(classified[0]["provisional_R_final"], "R3")
        self.assertEqual(classified[-1]["provisional_R_final"], "R0")
        self.assertTrue(any(row["provisional_R_final"] == "RX" for row in classified[2:4]))

    def test_explicit_missing_primary_forces_rx(self) -> None:
        rows = [self.row(0, math.nan, 0.2, 0.8, 0.2), self.row(1, 0.8, 0.3, 0.7, 0.3)]
        classified, _sensitivity, _thresholds = rv1.classify_rows(rows, [0.4, 0.5, 0.6])
        self.assertEqual(classified[0]["provisional_R_final"], "RX")
        self.assertIn("primary metric missing", classified[0]["classification_reason"])

    def test_roofer_failure_or_invalidity_forces_lod2_zero(self) -> None:
        failed = self.row(0, 0.8, 0.2, 0.8, 0.2)
        failed["roofer_success"] = False
        invalid = self.row(1, 0.7, 0.3, 0.7, 0.3)
        invalid["val3dity_lod22_valid"] = False
        classified, _sensitivity, _thresholds = rv1.classify_rows([failed, invalid], [0.4, 0.5, 0.6])
        self.assertEqual(classified[0]["lod2_score"], 0.0)
        self.assertEqual(classified[1]["lod2_score"], 0.0)
        self.assertTrue(classified[0]["lod2_forced_zero"])


class TestAtomicResume(unittest.TestCase):
    def test_atomic_per_building_write_and_resume_detection(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "B1.json"
            rv1.write_building_result(
                path,
                {
                    "schema": rv1.SCHEMA,
                    "building_id": "B1",
                    "processing_status": "success",
                },
            )
            self.assertTrue(rv1.result_valid(path, "B1"))
            self.assertFalse(path.with_name(path.name + ".tmp").exists())
            self.assertEqual(json.loads(path.read_text())["building_id"], "B1")


if __name__ == "__main__":
    unittest.main(verbosity=2)
