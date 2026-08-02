from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts.input_and_alignment.gate_s0.uas_eligibility_explainer_v1 import build_explainer


class UASEligibilityExplainerTest(unittest.TestCase):
    def test_builds_exact_frozen_scope_without_scientific_payloads(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            with mock.patch.object(build_explainer, "OUT", output):
                build_explainer.main()
            manifest = json.loads((output / "uas_eligibility_explainer_v1.json").read_text(encoding="utf-8"))
            with (output / "uas_eligibility_examples_v1.csv").open(encoding="utf-8", newline="") as handle:
                examples = list(csv.DictReader(handle))
            report = (output / "UAS_199_TO_72_EXPLAINER_v1.md").read_text(encoding="utf-8")
            svg = (output / "uas_eligibility_overview_v1.svg").read_text(encoding="utf-8")
        self.assertEqual(199, manifest["counts"]["u_target"])
        self.assertEqual(129, manifest["counts"]["raw_uas_observed_buildings_min_4_cells"])
        self.assertEqual(72, manifest["counts"]["reference_candidate"])
        self.assertEqual(127, manifest["counts"]["excluded"])
        self.assertEqual(10, manifest["counts"]["strict_planar_branch"])
        self.assertEqual(72, manifest["attrition"]["diagnostic_final"])
        self.assertEqual({"development": 51, "validation": 11, "held_out": 10}, manifest["counts"]["splits"])
        self.assertEqual(9, manifest["counts"]["independent_groups"])
        self.assertEqual(47, manifest["counts"]["largest_group"])
        self.assertEqual(
            {
                "INSUFFICIENT_INDEPENDENT_UAS_REFERENCE_SUPPORT": 78,
                "INSUFFICIENT_INDEPENDENT_UAS_REFERENCE_SUPPORT;INSUFFICIENT_C4_SUPPORT": 2,
                "INSUFFICIENT_INDEPENDENT_UAS_REFERENCE_SUPPORT;INSUFFICIENT_MVS_SUPPORT": 38,
                "INSUFFICIENT_INDEPENDENT_UAS_REFERENCE_SUPPORT;INSUFFICIENT_MVS_SUPPORT;INSUFFICIENT_C4_SUPPORT": 9,
            },
            manifest["exclusion_reason_combinations"],
        )
        self.assertEqual(
            {name: blob for name, (_, blob) in build_explainer.SOURCES.items()},
            {name: record["git_blob"] for name, record in manifest["sources"].items()},
        )
        self.assertEqual(
            "LOD2_DERIVED_DIAGNOSTIC_ONLY_NOT_PRIMARY_C5_READY",
            manifest["claim_scope"]["c5_lod1_scope"],
        )
        self.assertIsNone(manifest["scientific_verdict"])
        self.assertEqual(7, len(examples))
        self.assertEqual({"P1", "P2", "P3", "F1", "F2", "F3", "F4"}, {row["label"] for row in examples})
        self.assertIn("199동 모두에 UAS LiDAR가 충분히 관측된 것이 아니다", report)
        self.assertIn("primary C5 실행·평가가 READY가 되지는 않음", report)
        self.assertIn("scientific_verdict: `null`", report)
        self.assertIn("UAS eligibility from 199 target buildings", svg)
        self.assertIn('clip-path="url(#aoi-clip)"', svg)


if __name__ == "__main__":
    unittest.main()
