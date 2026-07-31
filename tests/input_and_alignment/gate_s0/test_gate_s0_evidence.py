from __future__ import annotations

import csv
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from scripts.input_and_alignment.gate_s0.validate_gate_s0_evidence import (
    git_blob_bytes,
    git_introducing_commit,
    lf_canonical_worktree_text_bytes,
)


DOC_ROOT = Path("docs/research/preregistration/gate_s0")
MANIFEST_ROOT = Path("artifacts/manifests/gate_s0")


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def read_csv(path: Path):
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


class GateS0EvidenceTests(unittest.TestCase):
    def test_canonical_git_text_hash_ignores_checkout_eol(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "evidence.txt"
            path.write_bytes(b"alpha\nbeta\n")
            expected = lf_canonical_worktree_text_bytes(path)
            path.write_bytes(b"alpha\r\nbeta\r\n")
            self.assertEqual(lf_canonical_worktree_text_bytes(path), expected)

    def test_image_camera_ledger_is_exact(self) -> None:
        path = DOC_ROOT / "gate_s0_image_camera_ledger_v1.csv"
        rows = read_csv(path)
        self.assertEqual(len(rows), 962)
        self.assertEqual(sum(row["status"] == "INCLUDED" for row in rows), 937)
        self.assertEqual(sum(row["status"] == "EXCLUDED" for row in rows), 25)
        self.assertEqual(
            hashlib.sha256(lf_canonical_worktree_text_bytes(path)).hexdigest(),
            "8c1e89040869e800c34ebd8a06c2b5185524330fc5d56e594b41686173c465b0",
        )

    def test_live_records_bind_exact_inputs(self) -> None:
        inputs = read_json(DOC_ROOT / "gate_s0_input_manifest_v1.json")
        records = read_json(MANIFEST_ROOT / "gate_s0_live_artifact_records_v1.json")
        self.assertEqual(inputs["verification"]["level"], "artifact_verified")
        self.assertEqual(inputs["verification"]["exact_file_count"], 11)
        self.assertEqual(inputs["verification"]["exact_total_bytes"], 15743666051)
        self.assertEqual(len(records["records"]), 11)
        self.assertTrue(
            all(record["verification_method"] == "sha256_rehash" for record in records["records"])
        )
        image_inventory_path = Path(
            inputs["image_camera_ledger"]["image_member_inventory_path"]
        )
        self.assertEqual(
            inputs["image_camera_ledger"]["image_member_inventory_sha256"],
            hashlib.sha256(
                lf_canonical_worktree_text_bytes(image_inventory_path)
            ).hexdigest(),
        )
        aoi_path = Path(inputs["candidate_aoi"]["geojson_path"])
        self.assertEqual(
            inputs["candidate_aoi"]["geojson_sha256"],
            hashlib.sha256(lf_canonical_worktree_text_bytes(aoi_path)).hexdigest(),
        )

    def test_c1_c2_c4_are_not_overclaimed(self) -> None:
        inputs = read_json(DOC_ROOT / "gate_s0_input_manifest_v1.json")
        self.assertEqual(inputs["c1_source_proposal"]["selection"], "NADIR_ONLY")
        self.assertEqual(inputs["c1_source_proposal"]["status"], "PARTIAL")
        self.assertEqual(inputs["image_camera_ledger"]["c2_same_base_status"], "PARTIAL")
        self.assertEqual(inputs["c4_prior_interface_proposal"]["status"], "PARTIAL")
        self.assertEqual(inputs["c4_prior_interface_proposal"]["loss_equation"], "DEFERRED_TO_P3")

    def test_c5_is_missing_without_lod2_substitution(self) -> None:
        inputs = read_json(DOC_ROOT / "gate_s0_input_manifest_v1.json")
        search_path = Path(inputs["lod1_search"]["search_evidence_path"])
        search = read_json(search_path)
        self.assertEqual(inputs["lod1_search"]["status"], "MISSING")
        self.assertEqual(inputs["lod1_search"]["matches"], [])
        self.assertEqual(
            inputs["lod1_search"]["search_evidence_sha256"],
            hashlib.sha256(lf_canonical_worktree_text_bytes(search_path)).hexdigest(),
        )
        self.assertEqual(search["status"], "MISSING")
        self.assertEqual(search["lod1_matches"], [])
        self.assertTrue(all(not item["name_contains_lod1"] for item in search["candidate_matches"]))
        self.assertIn("Do not simplify", inputs["lod1_search"]["prohibited_substitute"])
        self.assertIn("score-only", inputs["reference_guard"])

    def test_funnel_and_split_do_not_invent_ids_or_open_held_out(self) -> None:
        funnel = read_csv(DOC_ROOT / "gate_s0_eligibility_funnel_v1.csv")
        split = read_json(DOC_ROOT / "gate_s0_split_proposal_v1.json")
        self.assertTrue(all(row["held_out_accessed"] == "false" for row in funnel))
        self.assertEqual(next(row for row in funnel if row["stage"] == "E_paired")["status"], "UNKNOWN")
        self.assertEqual(split["preferred_mode"], "EXHAUSTIVE_PARTITION")
        self.assertEqual(split["status"], "PROPOSAL_NOT_FREEZEABLE")
        self.assertFalse(split["held_out_accessed"])
        for key in ("U_target_ids", "E_paired_ids", "development_ids", "validation_ids", "held_out_ids"):
            self.assertEqual(split[key], [])

    def test_cost_evidence_preserves_unknown_bounds(self) -> None:
        rows = read_csv(DOC_ROOT / "gate_s0_cost_bounds_v1.csv")
        self.assertEqual(len(rows), 5)
        self.assertTrue(all(row["runtime_bound"] == "UNKNOWN" for row in rows))
        self.assertTrue(all(row["peak_memory_bound"] == "UNKNOWN" for row in rows))
        self.assertTrue(all(row["output_bytes_bound"] == "UNKNOWN" for row in rows))
        self.assertTrue(all(row["held_out_accessed"] == "false" for row in rows))

    def test_documents_keep_review_status_and_null_verdict(self) -> None:
        for path in (
            DOC_ROOT / "GATE_S0_EVIDENCE_REPORT_v1.md",
            DOC_ROOT / "issues.md",
            Path("docs/handoffs/returns/P2_C2W_GATE_S0_PREPARATION_RETURN_v1.md"),
        ):
            text = path.read_text(encoding="utf-8")
            self.assertIn("BLOCKED_FOR_GATE_S0_REVIEW", text)
            self.assertIn("scientific_verdict: null", text)

    def test_output_manifest_hashes_every_required_output(self) -> None:
        payload = read_json(MANIFEST_ROOT / "gate_s0_output_manifest_v1.json")
        self.assertIsNone(payload["scientific_verdict"])
        self.assertEqual(payload["proposed_status"], "BLOCKED_FOR_GATE_S0_REVIEW")
        self.assertEqual(len(payload["files"]), 9)
        introducing_commits = set()
        for item in payload["files"]:
            path = Path(item["path"])
            canonical_bytes = lf_canonical_worktree_text_bytes(path)
            self.assertEqual(len(canonical_bytes), item["bytes"])
            self.assertEqual(hashlib.sha256(canonical_bytes).hexdigest(), item["sha256"])
            commit = git_introducing_commit(path)
            introducing_commits.add(commit)
            self.assertEqual(git_blob_bytes(commit, path), canonical_bytes)
        output_manifest_path = MANIFEST_ROOT / "gate_s0_output_manifest_v1.json"
        output_manifest_commit = git_introducing_commit(output_manifest_path)
        introducing_commits.add(output_manifest_commit)
        self.assertEqual(
            git_blob_bytes(output_manifest_commit, output_manifest_path),
            lf_canonical_worktree_text_bytes(output_manifest_path),
        )
        self.assertEqual(introducing_commits, {"380cc8916e739702206a65cdd9318b2014c81030"})


if __name__ == "__main__":
    unittest.main()
