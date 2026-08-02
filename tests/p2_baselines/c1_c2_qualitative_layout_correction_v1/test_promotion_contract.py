from __future__ import annotations

import csv
import copy
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from scripts.p2_baselines.c1_c2_qualitative_layout_correction_v1.promote_results import promote


class PromotionContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source_repo = Path(__file__).resolve().parents[3]
        cls.config_rel = Path("configs/p2_baselines/c1_c2_qualitative_layout_correction_v1/render_v1.json")
        cls.config = json.loads((cls.source_repo / cls.config_rel).read_text(encoding="utf-8"))

    @staticmethod
    def _run(root: Path, *args: str) -> str:
        return subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True, text=True).stdout.strip()

    def _fixture(self, root: Path, *, substitute_receipt_sha: bool = False) -> tuple[Path, Path, str]:
        repo = root / "repo"
        repo.mkdir()
        for relative in (
            self.config_rel,
            Path(self.config["inputs"]["examples_git_path"]),
            Path(self.config["inputs"]["bbox_ledger_git_path"]),
            Path(self.config["predecessor"]["closed_receipt_path"]),
        ):
            target = repo / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(self.source_repo / relative, target)

        predecessor = json.loads((repo / self.config["predecessor"]["closed_receipt_path"]).read_text(encoding="utf-8"))
        accepted_rows = copy.deepcopy(predecessor["artifacts"]["records"])
        for row in accepted_rows:
            row["verification_method"] = "closed_attestation_reuse"
        if substitute_receipt_sha:
            accepted_rows[0]["sha256"] = "0" * 64
        accepted = {
            "handoff_id": self.config["handoff_id"],
            "task_id": self.config["task_id"],
            "state": "accepted",
            "transport": {"exclusive_writer_ack": True},
            "verification": {
                "commands": ["validate without --artifact-root with zero artifact read and hash passes"],
                "tests": [{"name": "acceptance artifact source full-read or hash passes", "passed": 0, "failed": 0}],
            },
            "artifacts": {
                "records": accepted_rows,
                "attestation_reuse": {
                    "source_receipt_path": self.config["predecessor"]["closed_receipt_path"],
                    "source_receipt_commit": self.config["predecessor"]["closed_commit"],
                    "source_receipt_sha256": self.config["predecessor"]["closed_receipt_sha256"],
                    "record_identity_sha256": self.config["predecessor"]["accepted_record_identity_sha256"],
                },
            },
            "scientific": {"scientific_verdict": None},
        }
        accepted_rel = Path(f"artifacts/manifests/handoffs/{self.config['handoff_id']}/100-accepted.json")
        accepted_path = repo / accepted_rel
        accepted_path.parent.mkdir(parents=True, exist_ok=True)
        accepted_path.write_text(json.dumps(accepted, sort_keys=True) + "\n", encoding="utf-8")

        with (repo / self.config["inputs"]["examples_git_path"]).open("r", encoding="utf-8", newline="") as stream:
            examples = {row["label"]: row for row in csv.DictReader(stream)}
        with (repo / self.config["inputs"]["bbox_ledger_git_path"]).open("r", encoding="utf-8", newline="") as stream:
            ledgers = {row["stable_id"]: row for row in csv.DictReader(stream)}
        manifest_examples = []
        for label in self.config["example_labels"]:
            expected = self.config["expected_examples"][label]
            ledger = ledgers[expected[0]]
            source = examples[label]
            manifest_examples.append({
                "label": label,
                "stable_id": expected[0],
                "candidate": expected[1],
                "actual_compact_rows": expected[2],
                "recorded_reference_cells": expected[2],
                "current_image_views": expected[3],
                "mvs_support_cells": expected[4],
                "c4_support_cells": expected[5],
                "bbox": [float(ledger[key]) for key in ("bbox_min_x", "bbox_min_y", "bbox_max_x", "bbox_max_y")],
                "reason": source["exclusion_reason"],
            })
        external = {
            "schema": "jointbuildgs.c1_c2_qualitative_layout_correction_manifest.v1",
            "task_id": self.config["task_id"],
            "run_id": self.config["run_id"],
            "status": "LAYOUT_CORRECTED_AUTOMATED_CONTAINMENT_PASS",
            "predecessor": self.config["predecessor"],
            "examples": manifest_examples,
            "compact_source_read": {
                "bytes": 3785261,
                "sha256": "bf87736227ea3c28bc8f966f36e2498f786d2de420a732fa0bfebbb73664275a",
                "rows": 20520,
                "full_read_and_digest_passes": 1,
            },
            "output": {
                "path": self.config["result"]["figure_filename"],
                "bytes": 1234,
                "sha256": "a" * 64,
                "post_write_digest_passes": 1,
            },
            "scope": self.config["scope"],
            "scientific_verdict": None,
        }
        external_path = root / "external.json"
        external_path.write_text(json.dumps(external, sort_keys=True) + "\n", encoding="utf-8")

        self._run(repo, "init", "-b", "main")
        self._run(repo, "config", "user.email", "test@example.invalid")
        self._run(repo, "config", "user.name", "JointBuildGS Test")
        self._run(repo, "add", ".")
        self._run(repo, "commit", "-m", "test accepted fixture")
        accepted_commit = self._run(repo, "rev-parse", "HEAD")
        self._run(repo, "update-ref", "refs/remotes/origin/main", accepted_commit)
        return repo, external_path, accepted_commit

    def test_valid_manifest_promotes_only_two_add_once_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            repo, external, accepted = self._fixture(Path(temp))
            result = promote(external_manifest=external, repo_root=repo, source_commit="1" * 40, accepted_commit=accepted)
            self.assertEqual(result["status"], "PROMOTED_PENDING_ORIGINAL_PIXEL_REVIEW")
            self.assertEqual(len(result["outputs"]), 2)

    def test_manifest_reason_substitution_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            repo, external, accepted = self._fixture(Path(temp))
            value = json.loads(external.read_text(encoding="utf-8"))
            value["examples"][-1]["reason"] = "SUBSTITUTED"
            external.write_text(json.dumps(value) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "exact eligibility record mismatch"):
                promote(external_manifest=external, repo_root=repo, source_commit="1" * 40, accepted_commit=accepted)

    def test_accepted_record_substitution_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            repo, external, accepted = self._fixture(Path(temp), substitute_receipt_sha=True)
            with self.assertRaisesRegex(RuntimeError, "exactly inherit predecessor"):
                promote(external_manifest=external, repo_root=repo, source_commit="1" * 40, accepted_commit=accepted)


if __name__ == "__main__":
    unittest.main()
