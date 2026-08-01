from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from scripts.input_and_alignment.gate_s0.common_base_r2b.resolve_existing_common_base import (
    CONFIG_PATH,
    CROSSWALK_PATH,
    LEDGER_PATH,
    LINEAGE_PATH,
    READINESS_PATH,
    SCRIPT_PATH,
    NamespaceConflict,
    build_operation_identity,
    canonical_json_bytes,
    completed_lookup,
    execute,
    normalize_lf,
    read_json,
)
from scripts.input_and_alignment.gate_s0.common_base_r2b.validate_r2b_lineage import (
    OUTPUT_MANIFEST_PATH,
    build_output_manifest,
    portable_changed_paths,
)


class R2BLineageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repo = Path.cwd().resolve()
        self.config = read_json(CONFIG_PATH)
        self.identity = build_operation_identity(CONFIG_PATH, SCRIPT_PATH, self.repo)

    def test_exact_completed_lookup_is_zero_byte_noop_and_preserves_ledger(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            ledger_path = Path(directory) / "ledger.json"
            ledger_path.write_bytes(
                canonical_json_bytes(
                    {
                        "status": "COMPLETED",
                        "operation_identity": self.identity,
                    }
                )
            )
            before = ledger_path.read_bytes()
            result = execute(
                self.repo,
                Path(directory) / "artifact-root-must-not-exist",
                ledger_path=ledger_path,
            )
            self.assertEqual(result["status"], "REUSED_COMPLETED")
            for key in (
                "external_payload_read_bytes",
                "external_payload_hashed_bytes",
                "external_metadata_read_bytes",
                "external_metadata_hashed_bytes",
                "external_directory_entries_statted",
                "repository_output_bytes_read_or_hashed",
                "writes",
            ):
                self.assertEqual(result[key], 0)
            self.assertEqual(ledger_path.read_bytes(), before)

    def test_conflict_blocks_before_artifact_root_access(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            ledger_path = Path(directory) / "ledger.json"
            ledger_path.write_bytes(
                canonical_json_bytes(
                    {
                        "status": "COMPLETED",
                        "operation_identity": {"operation_id": "different"},
                    }
                )
            )
            artifact_root = Path(directory) / "absent-artifact-root"
            with self.assertRaisesRegex(NamespaceConflict, "BLOCKED_NAMESPACE_CONFLICT"):
                execute(self.repo, artifact_root, ledger_path=ledger_path)
            self.assertFalse(artifact_root.exists())

    def test_incomplete_ledger_cannot_be_reinitialized(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            ledger_path = Path(directory) / "ledger.json"
            ledger_path.write_text('{"status":"IN_PROGRESS"}\n', encoding="utf-8")
            with self.assertRaisesRegex(NamespaceConflict, "BLOCKED_INCOMPLETE_LEDGER"):
                completed_lookup(ledger_path, self.identity)

    def test_operation_identity_binds_executable_blob_config_and_self_commit(self) -> None:
        identity = self.identity
        self.assertEqual(identity["executable"]["path"], SCRIPT_PATH.as_posix())
        self.assertEqual(len(identity["executable"]["git_blob_oid"]), 40)
        self.assertEqual(identity["executable"]["containing_commit"], "SELF")
        self.assertEqual(identity["config"]["path"], CONFIG_PATH.as_posix())
        self.assertEqual(len(identity["config"]["sha256_lf"]), 64)
        self.assertEqual(
            identity["producer_script_containing_commit"],
            "252ea1dce31acec53481876137941192fea9a9bc",
        )

    def test_component_aware_candidate_paths_cover_files_and_directories(self) -> None:
        candidates = {
            item["component"]: (item["kind"], item["path"])
            for item in self.config["retained_candidates"]
        }
        self.assertEqual(
            candidates,
            {
                "images": ("directory", "data/work/mvs/colmap_dense/images"),
                "sfm_sparse": ("directory", "data/work/mvs/colmap_dense/sparse"),
                "stereo": ("directory", "data/work/mvs/colmap_dense/stereo"),
                "dense_mvs_scene": ("file", "data/work/mvs/openmvs/scene.mvs"),
                "dense_mvs_ply": ("file", "data/work/mvs/openmvs/dim_dense.ply"),
                "dense_mvs_laz": ("file", "data/work/mvs/dim/dim_v1.laz"),
            },
        )
        self.assertEqual(len(set(candidates.values())), len(candidates))

    def test_exact_937_crosswalk_and_component_sets(self) -> None:
        crosswalk = read_json(CROSSWALK_PATH)
        self.assertEqual(crosswalk["member_count"], 937)
        self.assertEqual(len(crosswalk["rows"]), 937)
        self.assertEqual(
            crosswalk["source_basename_set_sha256"],
            "dd9b446e11c978ef8223858f08571bfea832e0d33517b24c1e573060244f4e2c",
        )
        self.assertTrue(crosswalk["all_component_sets_equal"])
        self.assertTrue(
            all(item["equals_exact_source"] for item in crosswalk["set_checks"].values())
        )
        self.assertEqual(len({row["source_camera_uid"] for row in crosswalk["rows"]}), 937)
        self.assertEqual(len({row["colmap_image_id"] for row in crosswalk["rows"]}), 937)

    def test_readiness_separates_existence_lineage_gate_and_enablement(self) -> None:
        lineage = read_json(LINEAGE_PATH)
        by_component = {item["component"]: item for item in lineage["components"]}
        self.assertEqual(
            set(by_component),
            {"source_membership", "sfm_sparse", "dense_mvs", "depth", "normal", "confidence", "segmentation", "gravity"},
        )
        for item in by_component.values():
            for key in (
                "existence", "exact_lineage", "gate_readiness",
                "enablement_decision", "new_preprocessing"
            ):
                self.assertIn(key, item)
        self.assertEqual(by_component["source_membership"]["gate_readiness"], "READY")
        self.assertEqual(by_component["dense_mvs"]["gate_readiness"], "PARTIAL")
        self.assertEqual(by_component["depth"]["exact_lineage"], "MEMBERSHIP_EXACT_PRODUCER_RUN_UNBOUND")
        self.assertEqual(by_component["normal"]["exact_lineage"], "MEMBERSHIP_EXACT_PRODUCER_RUN_UNBOUND")

    def test_forbidden_work_remains_disabled(self) -> None:
        guards = self.config["guards"]
        self.assertEqual(guards["performance_authority"], "NONE")
        for key, value in guards.items():
            if key != "performance_authority":
                self.assertFalse(value, key)

    def test_lf_crlf_portable_worktree_comparison(self) -> None:
        self.assertEqual(normalize_lf(b"a\r\nb\r\n"), normalize_lf(b"a\nb\n"))
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
            subprocess.run(["git", "config", "user.email", "r2b@example.invalid"], cwd=repo, check=True)
            subprocess.run(["git", "config", "user.name", "R2B Test"], cwd=repo, check=True)
            path = repo / "protected.txt"
            path.write_bytes(b"alpha\nbeta\n")
            subprocess.run(["git", "add", "protected.txt"], cwd=repo, check=True)
            subprocess.run(["git", "commit", "-q", "-m", "base"], cwd=repo, check=True)
            path.write_bytes(b"alpha\r\nbeta\r\n")
            self.assertEqual(portable_changed_paths(repo, "HEAD"), set())
            path.write_bytes(b"alpha\r\nchanged\r\n")
            self.assertEqual(portable_changed_paths(repo, "HEAD"), {"protected.txt"})

    def test_output_manifest_uses_lf_canonical_bytes(self) -> None:
        self.assertEqual(read_json(OUTPUT_MANIFEST_PATH), build_output_manifest(self.repo))


if __name__ == "__main__":
    unittest.main()
