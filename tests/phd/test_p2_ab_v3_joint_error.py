"""Analytic scalar fixtures; no claims about actual P2 coverage/performance."""

from copy import deepcopy
import json
from pathlib import Path
import unittest

from scripts.phd.p2_ab_v3.a_joint_error_probe import build_case
from src.phd.p2_ab_v3.joint_error import judge, truth_membership, variant


class JointErrorTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = json.loads(Path("configs/phd/p2_ab_v3/a_joint_error_probe_v1.json").read_text())

    def case(self, name):
        return build_case(self.config, next(c for c in self.config["cases"] if c["case_id"] == name))

    def test_fusion_can_pass_when_parents_do_not(self):
        p, truth = self.case("opposed_source_errors_fusion")
        result = judge(p)
        self.assertEqual(result["conditional_action"], "FUSION")
        self.assertAlmostEqual(result["selected_value_m"], 0.0)
        for c in result["candidates"]:
            self.assertLessEqual(c["error_bounds_m"]["lower_m"], abs(c["value_m"] - truth["x"]))
            self.assertGreaterEqual(c["error_bounds_m"]["upper_m"], abs(c["value_m"] - truth["x"]))
        parents = [c for c in result["candidates"] if c["candidate_id"] in ("IMAGE_RAW", "PRIOR_REGISTERED")]
        self.assertTrue(all(c["error_bounds_m"]["upper_m"] > p["tolerance_m"] for c in parents))

    def test_truth_containment_for_every_correctly_declared_fixture(self):
        for case in self.config["cases"]:
            if case["case_id"] == "deliberately_misspecified_prior_error":
                continue
            p, truth = build_case(self.config, case)
            self.assertTrue(truth_membership(p, truth)["included"], case["case_id"])
            result = judge(p)
            for c in result["candidates"]:
                if c["error_bounds_m"]["upper_m"] is not None:
                    err = abs(c["value_m"] - truth["x"])
                    self.assertLessEqual(c["error_bounds_m"]["lower_m"], err + 1e-8)
                    self.assertGreaterEqual(c["error_bounds_m"]["upper_m"], err - 1e-8)

    def test_identical_observation_replication_adds_no_information(self):
        p, _ = self.case("opposed_source_errors_fusion")
        original = judge(p)
        p["observation_copies"] = 17
        copied = judge(p)
        self.assertEqual(original["selected_candidate_id"], copied["selected_candidate_id"])
        for a, b in zip(original["branches"][0]["extrema"]["x"], copied["branches"][0]["extrema"]["x"]):
            self.assertAlmostEqual(a, b, places=10)

    def test_shared_error_cannot_cancel_by_source_averaging(self):
        p, truth = self.case("both_wrong_shared_coordinate_bias")
        self.assertEqual(judge(p)["conditional_action"], "ABSTAIN")
        wrong = judge(variant(p, "shared_error_zero"))
        self.assertNotEqual(wrong["conditional_action"], "ABSTAIN")
        self.assertGreater(abs(wrong["selected_value_m"] - truth["x"]), p["tolerance_m"])
        self.assertFalse(truth_membership(variant(p, "shared_error_zero"), truth)["included"])

    def test_changed_and_ambiguous_branches_forbid_fusion(self):
        for name in ("changed_prior", "registration_or_change_ambiguous"):
            p, _ = self.case(name)
            result = judge(p)
            self.assertEqual(result["conditional_action"], "IMAGE")
            self.assertFalse(result["same_current_surface_supported_by_all_feasible_branches"])
            self.assertFalse(any(c["action"] == "FUSION" for c in result["candidates"]))

    def test_prior_missing_mvs_not_fusion(self):
        p, _ = self.case("prior_only_current_scalar_evidence")
        result = judge(p)
        self.assertEqual(result["conditional_action"], "PRIOR")
        self.assertFalse(any(c["action"] in ("IMAGE", "FUSION") for c in result["candidates"]))

    def test_missing_mvs_error_does_not_constrain_photo(self):
        p, truth = self.case("prior_only_current_scalar_evidence")
        p["observations"]["prior"] = None
        baseline = judge(p)["branches"][0]["extrema"]["x"]
        p["bounds"]["e_I"] = [0, 0]
        p["bounds"]["nu"] = [0, 0]
        changed = judge(p)["branches"][0]["extrema"]["x"]
        self.assertEqual(baseline, changed)
        membership = truth_membership(p, truth)
        self.assertFalse(membership["included"])
        self.assertTrue(membership["current_x_feasible"])

    def test_unbounded_registration_does_not_discard_bounded_current_location(self):
        p, _ = self.case("prior_only_current_scalar_evidence")
        p["bounds"]["delta"] = [None, None]
        p["observations"]["prior"] = None
        result = judge(p)
        self.assertEqual(result["status"], "SOLVED_NUMERICAL")
        self.assertFalse(result["registration_projection_bounded"])
        self.assertIsNotNone(result["branches"][0]["extrema"]["x"])

    def test_registration_new_candidate_retested(self):
        p, _ = self.case("registration_same_epoch")
        result = judge(p)
        corrected = next(c for c in result["candidates"] if c["candidate_id"] == "PRIOR_REGISTERED")
        self.assertAlmostEqual(corrected["value_m"], p["observations"]["prior"] + corrected["correction_m"])
        self.assertLess(corrected["error_bounds_m"]["upper_m"], p["tolerance_m"])
        self.assertNotEqual(corrected["correction_m"], 0.0)

    def test_unknown_calibration_unbounded_and_inconsistent_are_distinct(self):
        expected = {"unobserved_unmatched_prior": "UNBOUNDED", "calibration_unavailable": "CALIBRATION_UNKNOWN",
                    "deliberately_misspecified_prior_error": "MODEL_INCONSISTENT"}
        for name, status in expected.items():
            p, _ = self.case(name)
            result = judge(p)
            self.assertEqual(result["status"], status)
            self.assertEqual(result["conditional_action"], "ABSTAIN")
            self.assertEqual(result["strict_current_use_action"], "ABSTAIN")

    def test_dropping_dependency_is_relaxation_not_fake_independent_precision(self):
        p, _ = self.case("opposed_source_errors_fusion")
        linked = judge(p)["branches"][0]["extrema"]["x"]
        dropped = judge(variant(p, "drop_noise_link"))["branches"][0]["extrema"]["x"]
        self.assertLessEqual(dropped[0], linked[0] + 1e-8)
        self.assertGreaterEqual(dropped[1], linked[1] - 1e-8)

    def test_analytic_interval_and_nonidentifiability(self):
        p, _ = self.case("prior_only_current_scalar_evidence")
        p["observations"] = {"photo": 1.0, "mvs": None, "prior": None}
        p["bounds"]["c"] = [-0.2, 0.2]
        p["bounds"]["eta"] = [-0.1, 0.1]
        p["bounds"]["e_I"] = [-1, 1]
        interval = judge(p)["branches"][0]["extrema"]["x"]
        self.assertAlmostEqual(interval[0], 0.7)
        self.assertAlmostEqual(interval[1], 1.3)
        p["bounds"]["c"] = [None, None]
        self.assertEqual(judge(p)["status"], "UNBOUNDED")


if __name__ == "__main__":
    unittest.main()
