from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from scripts.p2.c1_c2_shared_footprint_199_v3.verify_frozen_replay import (
    DEFAULT_MANIFEST,
    EXPECTED_SCHEMA,
    FreezeVerificationError,
    verify,
)


class FrozenReplayV3Tests(unittest.TestCase):
    def test_checked_in_manifest_freezes_new_native_mvs_and_disallows_rerun(self) -> None:
        manifest = json.loads(DEFAULT_MANIFEST.read_text(encoding="utf-8"))
        self.assertEqual(manifest["schema"], EXPECTED_SCHEMA)
        self.assertFalse(manifest["policy"]["roofer_reconstruction_after_freeze_allowed"])
        self.assertFalse(manifest["policy"]["historical_v1_v2_obj_allowed_as_active_review_input"])
        self.assertEqual(
            manifest["condition_inputs"]["C2_MVS"]["source_kind"],
            "NEW_NATIVE_MVS_DENSE_POINT_CLOUD",
        )
        self.assertFalse(manifest["condition_inputs"]["C2_MVS"]["vendor_1104_image_mvs_used"])
        self.assertIsNone(manifest["scientific_verdict"])
        self.assertEqual(len(manifest["records"]), manifest["record_count"])

    def test_verifier_accepts_exact_record_and_rejects_drift(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "payload"
            source.mkdir()
            record = source / "result.bin"
            record.write_bytes(b"frozen-result")
            manifest = {
                "schema": EXPECTED_SCHEMA,
                "freeze_id": "test-freeze",
                "artifact_relative_root": "payload",
                "policy": {
                    "downstream_mode": "EXACT_HASH_BOUND_REUSE_ONLY",
                    "roofer_reconstruction_after_freeze_allowed": False,
                    "scientific_verdict": None,
                },
                "records": [
                    {
                        "path": "result.bin",
                        "bytes": len(b"frozen-result"),
                        "sha256": hashlib.sha256(b"frozen-result").hexdigest(),
                    }
                ],
                "record_count": 1,
                "scientific_verdict": None,
            }
            manifest_path = root / "manifest.json"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            result = verify(manifest_path, root)
            self.assertEqual(result["status"], "EXACT_FROZEN_REPLAY_VERIFIED")
            self.assertEqual(result["roofer_invocations"], 0)

            record.write_bytes(b"drifted")
            with self.assertRaisesRegex(FreezeVerificationError, "byte-size drift"):
                verify(manifest_path, root)


if __name__ == "__main__":
    unittest.main()
