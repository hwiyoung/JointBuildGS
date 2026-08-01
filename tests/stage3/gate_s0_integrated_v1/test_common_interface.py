from __future__ import annotations

import json
import unittest

from src.stage3.gate_s0_integrated_v1.interface import CONDITIONS, derive_roofprint, synthetic_smoke_payload


POINTS = [
    (0.0, 0.0, 0.0, 2),
    (5.0, 0.0, 3.0, 6),
    (5.0, 5.0, 3.0, 6),
    (0.0, 5.0, 3.0, 6),
]


class CommonInterfaceTests(unittest.TestCase):
    def test_all_conditions_use_same_non_gt_protocol(self) -> None:
        protocols = {derive_roofprint(condition, POINTS).protocol for condition in CONDITIONS}
        self.assertEqual({"R_DERIVED_NON_GT_CONVEX_HULL_V1"}, protocols)

    def test_external_roofprint_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "prohibited"):
            derive_roofprint("C1_L_upper", POINTS, external_roofprint={"type": "Polygon"})

    def test_smoke_is_cityjsonseq_and_not_quality_result(self) -> None:
        lines = synthetic_smoke_payload().decode("utf-8").splitlines()
        self.assertEqual(6, len(lines))
        header = json.loads(lines[0])
        self.assertEqual("CityJSON", header["type"])
        self.assertFalse(header["metadata"]["qualityComparison"])
        ids = {json.loads(line)["jointbuildgsStage3Request"]["condition_id"] for line in lines[1:]}
        self.assertEqual(set(CONDITIONS), ids)


if __name__ == "__main__":
    unittest.main()
