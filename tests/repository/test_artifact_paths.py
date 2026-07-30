from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.artifact_paths import ArtifactResolutionError, resolve_existing_path


class ArtifactPathTests(unittest.TestCase):
    def test_repository_file_wins(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            tracked = root / "phases/p0-audit/data/item.bin"
            tracked.parent.mkdir(parents=True)
            tracked.write_bytes(b"repo")
            with patch.dict(os.environ, {"JBGS_ARTIFACT_ROOT": str(root / "external")}):
                self.assertEqual(resolve_existing_path(root, "phases/p0-audit/data/item.bin"), tracked)

    def test_exact_p0_payload_mapping(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            external = root / "external"
            payload = external / "phase-payloads/p0-audit/data/work/item.bin"
            payload.parent.mkdir(parents=True)
            payload.write_bytes(b"external")
            with patch.dict(os.environ, {"JBGS_ARTIFACT_ROOT": str(external)}):
                self.assertEqual(
                    resolve_existing_path(root / "repo", "phases/p0-audit/data/work/item.bin"),
                    payload,
                )

    def test_fusion_run_compatibility_mapping_is_exact(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            external = root / "external"
            payload = external / "phase-payloads/p2-gsjso/runs/fusion_w1/run/receipt.json"
            payload.parent.mkdir(parents=True)
            payload.write_text("{}", encoding="utf-8")
            with patch.dict(os.environ, {"JBGS_ARTIFACT_ROOT": str(external)}):
                self.assertEqual(
                    resolve_existing_path(root / "repo", "phases/p2-gsjso/runs/run/receipt.json"),
                    payload,
                )

    def test_tracked_fusion_receipt_compatibility_mapping_is_exact(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            payload = root / "repo/phases/p2-gsjso/runs/fusion_w1/run/receipt.json"
            payload.parent.mkdir(parents=True)
            payload.write_text("{}", encoding="utf-8")
            self.assertEqual(
                resolve_existing_path(
                    root / "repo", "phases/p2-gsjso/runs/run/receipt.json"
                ),
                payload,
            )

    def test_legacy_results_path_maps_without_basename_search(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            external = root / "external"
            payload = external / "results/tum_transfer/cameras.bin"
            payload.parent.mkdir(parents=True)
            payload.write_bytes(b"camera")
            with patch.dict(os.environ, {"JBGS_ARTIFACT_ROOT": str(external)}):
                self.assertEqual(
                    resolve_existing_path(root / "repo", "results/tum_transfer/cameras.bin"),
                    payload,
                )

    def test_ambiguous_direct_and_compatibility_payload_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            external = root / "external"
            direct = external / "phase-payloads/p2-gsjso/runs/run/receipt.json"
            compatibility = external / "phase-payloads/p2-gsjso/runs/fusion_w1/run/receipt.json"
            for path in (direct, compatibility):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("{}", encoding="utf-8")
            with patch.dict(os.environ, {"JBGS_ARTIFACT_ROOT": str(external)}):
                with self.assertRaises(ArtifactResolutionError):
                    resolve_existing_path(root / "repo", "phases/p2-gsjso/runs/run/receipt.json")

    def test_missing_payload_remains_repository_relative(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with patch.dict(os.environ, {}, clear=True):
                self.assertEqual(
                    resolve_existing_path(root, "phases/p0-audit/data/missing.bin"),
                    root / "phases/p0-audit/data/missing.bin",
                )


if __name__ == "__main__":
    unittest.main()
