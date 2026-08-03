from __future__ import annotations

import unittest

import numpy as np

from src.evaluation.c1_c2_dev_gate_closure_v1.evaluator import RoofSurface
from src.evaluation.c3_dev_diagnostics_v1.evaluator import continuous_metrics, g4_candidate, load_config


class DiagnosticsTest(unittest.TestCase):
    def test_flat_roof_exact_match(self) -> None:
        surface = RoofSurface(
            "roof",
            (np.asarray([[0.0, 0.0, 10.0], [2.0, 0.0, 10.0], [0.0, 2.0, 10.0]]),),
            np.asarray([0.0, 0.0, 1.0]),
        )
        rows = [
            {"cell_x": "0.5", "cell_y": "0.5", "top_z": "10", "normal_x": "0", "normal_y": "0", "normal_z": "1"}
        ]
        metrics = continuous_metrics(rows, [surface])
        self.assertEqual(metrics["reference_vertical_coverage"], 1.0)
        self.assertEqual(metrics["RMSZ_m"], 0.0)
        self.assertTrue(g4_candidate(metrics, load_config()))

    def test_missing_roof_is_candidate_failure(self) -> None:
        rows = [
            {"cell_x": "0.5", "cell_y": "0.5", "top_z": "10", "normal_x": "0", "normal_y": "0", "normal_z": "1"}
        ]
        metrics = continuous_metrics(rows, [])
        self.assertEqual(metrics["reference_vertical_coverage"], 0.0)
        self.assertFalse(g4_candidate(metrics, load_config()))


if __name__ == "__main__":
    unittest.main()
