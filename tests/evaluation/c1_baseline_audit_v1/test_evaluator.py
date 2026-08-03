import unittest

from src.evaluation.c1_baseline_audit_v1.evaluator import _summary


class C1BaselineAuditTests(unittest.TestCase):
    def test_summary_separates_shared_unit_from_building_results(self):
        rows = [
            {
                "G0_generated": True,
                "G1_schema_semantic": True,
                "G2_geometry_topology_valid": True,
                "G3_self_reference_candidate": False,
                "G4_self_reference_candidate": True,
                "PASS_self_reference_candidate": False,
            }
            for _ in range(51)
        ]
        summary = _summary(rows, True)
        self.assertEqual(summary["buildings"], 51)
        self.assertEqual(summary["unique_roofer_outputs"], 1)
        self.assertEqual(summary["building_level_independent_outputs"], 0)
        self.assertEqual(summary["G2_inherited_true"], 51)
        self.assertEqual(summary["G4_self_reference_candidate_true"], 51)
        self.assertIsNone(summary["PASS_usable"])
        self.assertIsNone(summary["scientific_verdict"])


if __name__ == "__main__":
    unittest.main()
