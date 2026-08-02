from __future__ import annotations

import csv
import hashlib
import json
import re
import subprocess
import tempfile
import unittest
import warnings
from pathlib import Path

import numpy as np
from PIL import Image

from src.visualization.fixed_view_qualitative import PointSet, _bbox_from_row, _render_eligibility


class LayoutCorrectionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.repository = Path(__file__).resolve().parents[3]
        cls.config = json.loads(
            (
                cls.repository
                / "configs/p2_baselines/c1_c2_qualitative_layout_correction_v1/render_v1.json"
            ).read_text(encoding="utf-8")
        )

    def _inputs(self) -> tuple[list[dict[str, str]], dict[str, dict[str, str]], dict[str, PointSet]]:
        inputs = self.config["inputs"]
        with (self.repository / inputs["examples_git_path"]).open("r", encoding="utf-8", newline="") as stream:
            all_examples = {row["label"]: row for row in csv.DictReader(stream)}
        examples = [all_examples[label] for label in self.config["example_labels"]]
        with (self.repository / inputs["bbox_ledger_git_path"]).open("r", encoding="utf-8", newline="") as stream:
            ledgers = {row["stable_id"]: row for row in csv.DictReader(stream)}
        cells: dict[str, PointSet] = {}
        for example in examples:
            bbox = _bbox_from_row(ledgers[example["stable_id"]])
            cx, cy = bbox.center
            count = int(example["reference_cells"])
            xyz = np.tile(np.asarray([[cx, cy, 500.0]], dtype=np.float64), (count, 1))
            cells[example["stable_id"]] = PointSet(xyz, None)
        return examples, ledgers, cells

    def test_config_is_exact_layout_only_successor(self) -> None:
        self.assertEqual(self.config["task_id"], "P2-C1-C2-QUALITATIVE-LAYOUT-CORRECTION-R4-v1")
        self.assertEqual(self.config["handoff_id"], "P2-W2C-C1-C2-QUALITATIVE-LAYOUT-CORRECTION-R4-v1")
        self.assertEqual(self.config["predecessor"]["closed_commit"], "57205adf16def5382322ee57136b1cd66e9d07bc")
        self.assertEqual(self.config["predecessor"]["accepted_artifact_record_count"], 25)
        self.assertEqual(self.config["predecessor"]["accepted_artifact_total_bytes"], 30432763)
        self.assertEqual(self.config["example_labels"], ["P1", "P2", "P3", "F1", "F2", "F3", "F4"])
        self.assertTrue(self.config["style"]["assert_text_containment"])
        self.assertTrue(all(value == 0 for key, value in self.config["scope"].items() if key != "runtime_compact_processing_reads_and_digests"))
        self.assertEqual(self.config["scope"]["runtime_compact_processing_reads_and_digests"], 1)
        self.assertIsNone(self.config["scientific_verdict"])

    def test_predecessor_receipt_digest_uses_git_blob_bytes(self) -> None:
        predecessor = self.config["predecessor"]
        blob = subprocess.run(
            [
                "git",
                "-C",
                str(self.repository),
                "show",
                f'{predecessor["closed_commit"]}:{predecessor["closed_receipt_path"]}',
            ],
            check=True,
            capture_output=True,
        ).stdout
        self.assertEqual(hashlib.sha256(blob).hexdigest(), predecessor["closed_receipt_sha256"])
        self.assertEqual(
            predecessor["closed_receipt_sha256"],
            "7fc0770501eb3447733b481fe7ccf195064cdb3cb35934744a8db2fca6d0ec64",
        )

    def test_r4_identity_and_path_matrix_is_exact(self) -> None:
        task = "P2-C1-C2-QUALITATIVE-LAYOUT-CORRECTION-R4-v1"
        handoff = "P2-W2C-C1-C2-QUALITATIVE-LAYOUT-CORRECTION-R4-v1"
        run = "P2-C1-C2-QUALITATIVE-LAYOUT-CORRECTION-R4-RUN-v1"
        packet_rel = "docs/handoffs/P2_W2C_C1_C2_QUALITATIVE_LAYOUT_CORRECTION_R4_v1.md"
        namespace = f"phase-payloads/p2-baselines/c1_c2_qualitative_layout_correction_r4_v1/{task}"
        report_rel = "docs/experiments/p2/c1_c2_qualitative_layout_correction_r4_v1/C1_C2_QUALITATIVE_LAYOUT_CORRECTION_R4_v1.md"
        technical_rel = "artifacts/manifests/p2_baselines/c1_c2_qualitative_layout_correction_r4_v1/technical_result_manifest_v1.json"
        return_rel = "docs/handoffs/returns/P2_C2W_C1_C2_QUALITATIVE_LAYOUT_CORRECTION_R4_RETURN_v1.md"
        receipt_rel = f"artifacts/manifests/handoffs/{handoff}/"

        self.assertEqual(self.config["task_id"], task)
        self.assertEqual(self.config["handoff_id"], handoff)
        self.assertEqual(self.config["run_id"], run)
        self.assertEqual(self.config["result"]["external_relative_namespace"], namespace)
        self.assertEqual(self.config["result"]["external_uri"], f"artifact://JointBuildGS/{namespace}/")

        launcher = (
            self.repository
            / "scripts/p2_baselines/c1_c2_qualitative_layout_correction_v1/run_correction_host.sh"
        ).read_text(encoding="utf-8")
        promoter = (
            self.repository
            / "scripts/p2_baselines/c1_c2_qualitative_layout_correction_v1/promote_results.py"
        ).read_text(encoding="utf-8")
        packet = (self.repository / packet_rel).read_text(encoding="utf-8")
        for exact in (
            f'HANDOFF_ID="{handoff}"',
            f'TASK_ID="{task}"',
            f'PACKET_REL="{packet_rel}"',
            f'OUTPUT_REL="{namespace}"',
            f'"${{RUN_ID}}" != "{run}"',
        ):
            self.assertIn(exact, launcher)
        for exact in (
            f'TASK_ID = "{task}"',
            f'HANDOFF_ID = "{handoff}"',
            f'REPORT_REL = "{report_rel}"',
            f'TECHNICAL_REL = "{technical_rel}"',
        ):
            self.assertIn(exact, promoter)
        for exact in (
            f"- handoff_id: `{handoff}`",
            f"- task_id: `{task}`",
            f"- run_id: `{run}`",
            f"`artifact://JointBuildGS/{namespace}/`",
            f"`{report_rel}`",
            f"`{technical_rel}`",
            f"`{return_rel}`",
            f"`{receipt_rel}`",
        ):
            self.assertIn(exact, packet)

        stale = (
            "P2-W2C-C1-C2-QUALITATIVE-LAYOUT-CORRECTION-v1",
            "P2-C1-C2-QUALITATIVE-LAYOUT-CORRECTION-RUN-v1",
            "P2_W2C_C1_C2_QUALITATIVE_LAYOUT_CORRECTION_v1.md",
            "phase-payloads/p2-baselines/c1_c2_qualitative_layout_correction_v1/P2-C1-C2-QUALITATIVE-LAYOUT-CORRECTION-v1",
            "P2-W2C-C1-C2-QUALITATIVE-LAYOUT-CORRECTION-R2-v1",
            "P2-C1-C2-QUALITATIVE-LAYOUT-CORRECTION-R2-RUN-v1",
            "P2_W2C_C1_C2_QUALITATIVE_LAYOUT_CORRECTION_R2_v1.md",
            "P2-W2C-C1-C2-QUALITATIVE-LAYOUT-CORRECTION-R3-v1",
            "P2-C1-C2-QUALITATIVE-LAYOUT-CORRECTION-R3-RUN-v1",
            "P2_W2C_C1_C2_QUALITATIVE_LAYOUT_CORRECTION_R3_v1.md",
        )
        for value in stale:
            self.assertNotIn(value, launcher)
            self.assertNotIn(value, promoter)
            self.assertNotIn(value, packet)

    def test_actual_packet_authority_and_launcher_git_mode(self) -> None:
        packet = self.repository / "docs/handoffs/P2_W2C_C1_C2_QUALITATIVE_LAYOUT_CORRECTION_R4_v1.md"
        parser = self.repository / "scripts/p2_baselines/c1_c2_feasibility_pilot_v1/parse_execution_authority.awk"
        launcher_rel = "scripts/p2_baselines/c1_c2_qualitative_layout_correction_v1/run_correction_host.sh"
        packet_text = packet.read_text(encoding="utf-8")
        activated = re.sub(
            r"^- status: `[^`]+`$",
            "- status: `APPROVED_FOR_EXECUTION`",
            packet_text,
            count=1,
            flags=re.MULTILINE,
        )
        activated = re.sub(
            r"^- user_approval: `[^`]+`$",
            "- user_approval: `APPROVED_FOR_EXECUTION`",
            activated,
            count=1,
            flags=re.MULTILINE,
        )
        synthetic = subprocess.run(
            ["awk", "-f", str(parser)], input=activated, text=True, capture_output=True
        )
        self.assertEqual(synthetic.returncode, 0)
        actual = subprocess.run(["awk", "-f", str(parser), str(packet)], capture_output=True)
        if "- status: `APPROVED_FOR_EXECUTION`" in packet_text:
            self.assertEqual(actual.returncode, 0)
        else:
            self.assertIn("- status: `DRAFT`", packet_text)
            self.assertNotEqual(actual.returncode, 0)
        mode = subprocess.run(
            ["git", "-C", str(self.repository), "ls-files", "--stage", "--", launcher_rel],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.split()[0]
        self.assertEqual(mode, "100755")

    def test_launcher_binds_canonical_receipt_and_whole_task_budget(self) -> None:
        launcher = (
            self.repository
            / "scripts/p2_baselines/c1_c2_qualitative_layout_correction_v1/run_correction_host.sh"
        ).read_text(encoding="utf-8")
        promoter = (
            self.repository
            / "scripts/p2_baselines/c1_c2_qualitative_layout_correction_v1/promote_results.py"
        ).read_text(encoding="utf-8")
        self.assertIn("validate_two_host_handoff.py", launcher)
        self.assertIn('"--origin-ref", "origin/main", "--head-ref", "HEAD"', launcher)
        self.assertIn("acceptance artifact source full-read or hash passes", launcher)
        self.assertNotIn("commands =", launcher)
        self.assertNotIn("WITHOUT --ARTIFACT-ROOT", launcher)
        self.assertIn('zero[0]["passed"] == 0 and zero[0]["failed"] == 0', launcher)
        self.assertNotIn("commands =", promoter)
        self.assertNotIn("WITHOUT --ARTIFACT-ROOT", promoter)
        self.assertIn("len(zero_tests) != 1", promoter)
        self.assertIn("remaining_seconds", launcher)
        self.assertNotIn("timeout 600", launcher)
        for key in ("PACKET_IMAGE", "PACKET_RUN", "PACKET_MODE", "CONFIG_MEMORY", "CONFIG_OUTPUT_CAP"):
            self.assertIn(key, launcher)
        embedded = re.findall(r"-c '\n(.*?)\n'\s*$", launcher, flags=re.DOTALL | re.MULTILINE)
        self.assertEqual(len(embedded), 1)
        compile(embedded[0], "run_correction_host.sh embedded authority Python", "exec")

    def test_promoter_does_not_reopen_predecessor_or_scientific_inputs(self) -> None:
        promoter = (
            self.repository
            / "scripts/p2_baselines/c1_c2_qualitative_layout_correction_v1/promote_results.py"
        ).read_text(encoding="utf-8")
        self.assertNotIn('config["inputs"]["examples_git_path"]', promoter)
        self.assertNotIn('config["inputs"]["bbox_ledger_git_path"]', promoter)
        self.assertNotIn('_safe(repo_root, config["predecessor"]["closed_receipt_path"])', promoter)
        self.assertNotIn("Image.open", promoter)

    def test_longest_reason_is_contained_and_render_is_deterministic(self) -> None:
        examples, ledgers, cells = self._inputs()
        with tempfile.TemporaryDirectory() as temp:
            first = Path(temp) / "first.png"
            second = Path(temp) / "second.png"
            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter("always")
                first_records = _render_eligibility(
                    output_path=first,
                    examples=examples,
                    ledgers=ledgers,
                    cells=cells,
                    style=self.config["style"],
                )
            second_records = _render_eligibility(
                output_path=second,
                examples=examples,
                ledgers=ledgers,
                cells=cells,
                style=self.config["style"],
            )
            self.assertFalse(any("constrained_layout" in str(value.message) for value in caught))
            self.assertEqual([row["reason"] for row in first_records], [row["reason"] for row in second_records])
            self.assertEqual(first_records[-1]["reason"], self.config["expected_examples"]["F4"][6])
            self.assertEqual(hashlib.sha256(first.read_bytes()).hexdigest(), hashlib.sha256(second.read_bytes()).hexdigest())
            with Image.open(first) as image:
                self.assertEqual(image.size, (2520, 1400))
                image.verify()


if __name__ == "__main__":
    unittest.main()
