import unittest
import numpy as np

from src.phd.p2_ab_v3.handoff import Candidate, assemble_selected_geometry


class HandoffTests(unittest.TestCase):
    def setUp(self):
        self.candidate = Candidate("mvs:r1", "IMAGE", np.array([[1., 2., 3.]]),
            np.array([[0., 0., 1.]]), np.array([41]), ("mvs_hash",), "fixed_v1")
        self.decision = dict(region_id="r1", action="IMAGE", candidate_id="mvs:r1",
            geometry_sha256=self.candidate.fingerprint(), eligibility="ELIGIBLE",
            calibration_status="CALIBRATED", appearance_allowed=[True], detail_allowed=[False],
            components=[dict(component="normal_position", unit="m", candidate_error_upper=.1,
                             required_error=.2)])

    def test_exact_selected_source_and_abstention(self):
        arrays, receipt = assemble_selected_geometry({"mvs:r1": self.candidate},
            [self.decision, dict(region_id="r2", action="ABSTAIN", candidate_id=None)])
        np.testing.assert_array_equal(arrays["xyz"], self.candidate.xyz)
        self.assertEqual(arrays["native_rows"].tolist(), [41])
        self.assertEqual(receipt["regions"][1]["point_count"], 0)
        self.assertFalse(arrays["detail_allowed"].any())

    def test_replaced_geometry_is_rejected(self):
        self.candidate.xyz[0, 2] += 1
        with self.assertRaisesRegex(ValueError, "differs from A"):
            assemble_selected_geometry({"mvs:r1": self.candidate}, [self.decision])

    def test_unknown_cannot_become_actual_decision(self):
        self.decision["calibration_status"] = "UNAVAILABLE"
        with self.assertRaisesRegex(ValueError, "fixture"):
            assemble_selected_geometry({"mvs:r1": self.candidate}, [self.decision])
        _, receipt = assemble_selected_geometry({"mvs:r1": self.candidate}, [self.decision], fixture=True)
        self.assertEqual(receipt["status"], "WIRING_FIXTURE_ONLY")

    def test_appearance_is_not_detail_permission(self):
        self.decision["detail_allowed"] = [True]
        with self.assertRaisesRegex(ValueError, "own evidence"):
            assemble_selected_geometry({"mvs:r1": self.candidate}, [self.decision])

    def test_fusion_requires_distinct_parent_geometry(self):
        candidate = Candidate("fusion", "FUSION", self.candidate.xyz, self.candidate.normals,
                              self.candidate.native_rows, ("same", "same"), "fixed_v1")
        with self.assertRaisesRegex(ValueError, "distinct parent"):
            candidate.validate()


if __name__ == "__main__":
    unittest.main()
