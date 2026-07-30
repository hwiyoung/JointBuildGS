"""Tests for the pilot reference lock and offline asset verifier.

Run in the repository container:
    python -m unittest tests/experiments/pilot_1wave/test_pilot_1wave_reference_assets.py
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


REPO = Path(__file__).resolve().parents[3]
SCRIPT = REPO / "scripts/pilot_1wave/pilot_1wave_reference_assets.py"
LOCK = REPO / "phases/p2-gsjso/configs/pilot_1wave_reference_lock.json"
SPEC = importlib.util.spec_from_file_location("pilot_1wave_reference_assets", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
assets = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(assets)


class PilotReferenceAssetsTest(unittest.TestCase):
    def test_lock_has_exact_revisions_pipeline_and_unfetched_weights(self):
        lock = assets.load_and_validate_lock(LOCK)
        revisions = {
            key: row["revision"] for key, row in lock["code_references"].items()
        }
        self.assertEqual(revisions, assets.EXPECTED_REVISIONS)
        self.assertEqual(lock["grounded_sam_pipeline"]["prompt_literal"], "roof")
        self.assertEqual(
            lock["grounded_sam_pipeline"]["thresholds"],
            {"box": 0.25, "text": 0.25, "nms_iou": 0.8},
        )
        for row in lock["model_weights"].values():
            self.assertEqual(row["state"], "unfetched")
            self.assertIsNone(row["expected_sha256"])
            self.assertFalse(row["tracked_in_git"])

    def test_vision_fusion_and_score_only_gt_contract_are_locked(self):
        lock = assets.load_and_validate_lock(LOCK)
        pipeline = lock["grounded_sam_pipeline"]
        fusion = pipeline["vision_fusion"]
        self.assertEqual(fusion["footprint_dilation_px"], 5)
        self.assertEqual(fusion["footprint_core_erosion_px_default"], 5)
        self.assertEqual(
            fusion["footprint_core_erosion_px_small_building_if_default_empty"], 1
        )
        self.assertFalse(fusion["gt_used_for_selection"])
        self.assertIn("core_only_fallback", fusion["required_flags"])
        self.assertIn(
            "score-only", pipeline["quality_reporting"]["stage_2_posthoc_score_only"]
        )

    def test_audit_is_offline_and_reports_all_assets_absent(self):
        lock = assets.load_and_validate_lock(LOCK)
        with tempfile.TemporaryDirectory() as tmp:
            audit = assets.audit_local(lock, tmp)
        self.assertFalse(audit["network_accessed"])
        self.assertEqual(len(audit["artifacts"]), 7)
        self.assertTrue(
            all(row["local_state"] == "absent" for row in audit["artifacts"])
        )

    def test_receipt_verifies_bytes_and_detects_tamper(self):
        lock = assets.load_and_validate_lock(LOCK)
        artifact = assets.artifact_map(lock)["source:pgsr"]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            payload_path = root / artifact["expected_filename"]
            payload_path.write_bytes(b"test source archive bytes")
            digest = assets.sha256_file(payload_path)
            receipt_path = root / "receipt.json"
            receipt = {
                "schema": assets.RECEIPT_SCHEMA,
                "lock_sha256": assets.lock_sha256(LOCK),
                "fetched_utc": "2026-07-22T00:00:00+00:00",
                "asset_root": str(root),
                "artifacts": {
                    "source:pgsr": {
                        "kind": "source_archive",
                        "source_url": artifact["url"],
                        "filename": artifact["expected_filename"],
                        "size_bytes": payload_path.stat().st_size,
                        "sha256": digest,
                    }
                },
            }
            receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
            verified = assets.verify_receipt(lock, LOCK, root, receipt_path)
            self.assertEqual(verified["verified"][0]["sha256"], digest)

            payload_path.write_bytes(b"tampered")
            with self.assertRaisesRegex(ValueError, "differs from receipt"):
                assets.verify_receipt(lock, LOCK, root, receipt_path)

    def test_fetch_requires_explicit_artifact_ids(self):
        lock = assets.load_and_validate_lock(LOCK)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with self.assertRaisesRegex(ValueError, "at least one explicit"):
                assets.fetch_artifacts(lock, LOCK, root, [], root / "receipt.json")


if __name__ == "__main__":
    unittest.main()
