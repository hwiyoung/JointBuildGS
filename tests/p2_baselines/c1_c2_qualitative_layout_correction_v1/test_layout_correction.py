from __future__ import annotations

import csv
import hashlib
import json
import re
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
        self.assertEqual(self.config["predecessor"]["closed_commit"], "57205adf16def5382322ee57136b1cd66e9d07bc")
        self.assertEqual(self.config["predecessor"]["accepted_artifact_record_count"], 25)
        self.assertEqual(self.config["predecessor"]["accepted_artifact_total_bytes"], 30432763)
        self.assertEqual(self.config["example_labels"], ["P1", "P2", "P3", "F1", "F2", "F3", "F4"])
        self.assertTrue(self.config["style"]["assert_text_containment"])
        self.assertTrue(all(value == 0 for key, value in self.config["scope"].items() if key != "runtime_compact_processing_reads_and_digests"))
        self.assertEqual(self.config["scope"]["runtime_compact_processing_reads_and_digests"], 1)
        self.assertIsNone(self.config["scientific_verdict"])

    def test_launcher_binds_canonical_receipt_and_whole_task_budget(self) -> None:
        launcher = (
            self.repository
            / "scripts/p2_baselines/c1_c2_qualitative_layout_correction_v1/run_correction_host.sh"
        ).read_text(encoding="utf-8")
        self.assertIn("validate_two_host_handoff.py", launcher)
        self.assertIn('"--origin-ref", "origin/main", "--head-ref", "HEAD"', launcher)
        self.assertIn("acceptance artifact source full-read or hash passes", launcher)
        self.assertIn("WITHOUT --ARTIFACT-ROOT", launcher)
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
