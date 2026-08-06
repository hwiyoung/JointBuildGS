from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

import laspy
import numpy as np

from scripts.p2.c1_c2_shared_footprint_199_v1 import run


CONFIG = Path("configs/p2/c1_c2_shared_footprint_199_v2/run_all_v2.json")


class SharedFootprint199AllInvocationsV2Tests(unittest.TestCase):
    def test_v2_requires_all_398_invocations(self) -> None:
        config = json.loads(CONFIG.read_text(encoding="utf-8"))
        run.validate_config(config)
        self.assertTrue(config["execution"]["attempt_all_building_method_rows"])
        self.assertEqual(config["execution"]["expected_roofer_invocations"], 398)
        self.assertEqual(config["preparation"]["input_gate_role"], "DIAGNOSTIC_ONLY_DOES_NOT_BLOCK_ROOFER_INVOCATION")

    def test_empty_input_is_a_valid_zero_point_las(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "empty.las"
            run.write_classified_las(
                output,
                np.empty((0, 3), dtype=np.float64),
                np.empty((0, 3), dtype=np.float64),
                [690900.0, 5336000.0, 0.0],
            )
            with laspy.open(output) as reader:
                self.assertEqual(reader.header.point_count, 0)
                self.assertIn("classification", reader.header.point_format.dimension_names)


if __name__ == "__main__":
    unittest.main()
