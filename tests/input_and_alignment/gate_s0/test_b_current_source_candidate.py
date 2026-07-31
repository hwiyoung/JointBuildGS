from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path

from scripts.input_and_alignment.gate_s0.build_b_current_source_candidate import (
    DEFAULT_OUTPUT,
    build_candidate,
    canonical_json_bytes,
)


class BCurrentSourceCandidateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.payload = json.loads(DEFAULT_OUTPUT.read_text(encoding="utf-8"))

    def test_generated_candidate_is_current(self) -> None:
        self.assertEqual(self.payload, build_candidate())

    def test_exact_membership_and_join_are_bound(self) -> None:
        membership = self.payload["membership"]
        self.assertEqual(membership["image_count"], 962)
        self.assertEqual(membership["included_count"], 937)
        self.assertEqual(membership["excluded_count"], 25)
        self.assertNotEqual(
            membership["included_basename_set_sha256"],
            membership["excluded_basename_set_sha256"],
        )
        self.assertEqual(
            self.payload["component_registry"]["sfm_sparse"]["camera_uid_count"],
            membership["included_count"],
        )

    def test_candidate_hash_is_reproducible(self) -> None:
        core = dict(self.payload)
        core.pop("common_image_pose_base_id")
        expected = core.pop("source_candidate_manifest_sha256")
        core.pop("source_candidate_hash_scope")
        self.assertEqual(hashlib.sha256(canonical_json_bytes(core)).hexdigest(), expected)
        self.assertEqual(
            self.payload["common_image_pose_base_id"],
            f"B_CURRENT_CANDIDATE_{expected[:16]}",
        )

    def test_no_gate_or_performance_authority_is_claimed(self) -> None:
        self.assertEqual(self.payload["status"], "CANDIDATE_NOT_FROZEN")
        self.assertIsNone(self.payload["scientific_verdict"])
        self.assertEqual(self.payload["performance_authority"], "NONE")
        self.assertEqual(self.payload["gate_state"]["gate_s0"], "NOT_APPROVED")
        self.assertEqual(self.payload["gate_state"]["p2_performance"], "PROHIBITED")

    def test_missing_derivatives_are_not_invented(self) -> None:
        components = self.payload["component_registry"]
        self.assertEqual(
            components["sfm_sparse"]["source_identity"],
            "READY_FROM_PRIOR_VERIFIED_EVIDENCE",
        )
        for component in ("dense_mvs", "depth", "normal", "confidence"):
            self.assertEqual(
                components[component]["status"],
                "MISSING_EXACT_COMMON_BASE_DERIVATIVE",
            )
            self.assertIsNone(components[component]["gate_enablement"])
        self.assertEqual(
            components["dense_mvs"]["existing_1104_image_vendor_mvs"],
            "SENSOR_PROCESSING_BUNDLE_CONTEXT_ONLY",
        )

    def test_reuse_contract_blocks_known_duplicate_work(self) -> None:
        policy = "\n".join(self.payload["reuse_contract"]["policy"])
        self.assertIn("do not rerun", policy)
        self.assertIn("not per arm", policy)
        self.assertIn("15.7 GB", policy)
        self.assertIn("LoD1 search", policy)


if __name__ == "__main__":
    unittest.main()
