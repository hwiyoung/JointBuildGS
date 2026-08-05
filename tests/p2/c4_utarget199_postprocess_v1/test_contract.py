from __future__ import annotations

from types import SimpleNamespace
import unittest

import numpy as np

from scripts.p2.c4_utarget199_postprocess_v1.contract import (
    _metric_delta,
    lod2_reference_rows,
    load_config,
    validate_config,
)


class C4UTarget199PostprocessContractTest(unittest.TestCase):
    def test_config_keeps_bounded_c4_and_null_verdicts(self) -> None:
        result = validate_config()
        self.assertEqual(result["condition_id"], "C4_EXISTING_ALS")
        self.assertEqual(result["building_count"], 199)
        self.assertFalse(result["c5_executed"])
        self.assertIsNone(result["scientific_verdict"])

    def test_lod2_sampler_applies_registered_vertical_offset(self) -> None:
        reference = SimpleNamespace(
            roof_rings_xyz=[np.asarray([
                [0.0, 0.0, 10.0],
                [2.0, 0.0, 10.0],
                [2.0, 2.0, 10.0],
                [0.0, 2.0, 10.0],
                [0.0, 0.0, 10.0],
            ])],
        )
        config = load_config()
        config["frame"]["grid_origin_xy"] = [0.0, 0.0]
        sampled = lod2_reference_rows(reference, [0.0, 0.0, 2.0, 2.0], config)
        self.assertEqual(len(sampled), 4)
        self.assertTrue(all(abs(row["top_z"] - 55.7) < 1e-9 for row in sampled))

    def test_metric_delta_preserves_nulls(self) -> None:
        delta, reasons = _metric_delta(
            {"height_error_mae_m": 2.5, "RMSZ_m": None},
            {"height_error_mae_m": 2.0, "RMSZ_m": 3.0},
        )
        self.assertAlmostEqual(delta["height_error_mae_m"], 0.5)
        self.assertIsNone(delta["RMSZ_m"])
        self.assertEqual(reasons["RMSZ_m"], "C4_OR_MATCHED_C3_2_METRIC_NULL")


if __name__ == "__main__":
    unittest.main()
