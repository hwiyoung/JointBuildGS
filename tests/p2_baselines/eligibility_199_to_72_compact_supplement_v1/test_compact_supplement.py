from __future__ import annotations

import csv
import json
import subprocess
import unittest
from collections import Counter
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path


REPO = Path(__file__).resolve().parents[3]
CANDIDATE_LEDGER = REPO / (
    "docs/research/preregistration/gate_s0/uas_reference_coverage_r1_v1/"
    "candidate_ledger_v1.csv"
)
SPLIT_ROSTER = REPO / (
    "docs/research/preregistration/gate_s0/uas_reference_coverage_r1_v1/"
    "split_candidate_v1.csv"
)
FIXED_CASES = REPO / (
    "docs/research/preregistration/gate_s0/uas_eligibility_explainer_v1/"
    "uas_eligibility_examples_v1.csv"
)
SUPPLEMENT = REPO / (
    "docs/experiments/p2/eligibility_199_to_72_compact_supplement_v1/"
    "ELIGIBILITY_199_TO_72_COMPACT_SUPPLEMENT_v1.md"
)
SUMMARY = REPO / (
    "docs/experiments/p2/eligibility_199_to_72_compact_supplement_v1/"
    "eligibility_199_to_72_compact_summary_v1.csv"
)
R5_MANIFEST = REPO / (
    "artifacts/manifests/p2_baselines/c1_c2_qualitative_layout_correction_r5_v1/"
    "technical_result_manifest_v1.json"
)

CANDIDATE_LEDGER_BLOB = "6e5d6ab0698c0fdf3e67e74cbdd060bf785ea06b"
SPLIT_ROSTER_BLOB = "f6db7b8accdbd7b57b4a221c441acfc5589fb592"
FIGURE_NAME = "eligibility_199_to_72_fixed_cells_layout_corrected_v1.png"
FIGURE_SHA256 = "1a1540f380f7fbc1a950e806b879c01ad744cc8cf7e5bcef42cb761923938022"


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def percentage(numerator: int, denominator: int) -> Decimal:
    return (Decimal(numerator) * 100 / Decimal(denominator)).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )


class CompactEligibilitySupplementTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.candidates = read_csv(CANDIDATE_LEDGER)
        cls.splits = read_csv(SPLIT_ROSTER)
        cls.examples = read_csv(FIXED_CASES)
        cls.summary = read_csv(SUMMARY)
        cls.report = SUPPLEMENT.read_text(encoding="utf-8")
        cls.r5_manifest = json.loads(R5_MANIFEST.read_text(encoding="utf-8"))

    def test_sealed_source_blob_bindings(self) -> None:
        for path, expected in (
            (CANDIDATE_LEDGER, CANDIDATE_LEDGER_BLOB),
            (SPLIT_ROSTER, SPLIT_ROSTER_BLOB),
        ):
            relative = path.relative_to(REPO).as_posix()
            actual = subprocess.run(
                ["git", "-C", str(REPO), "rev-parse", f"HEAD:{relative}"],
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
            self.assertEqual(expected, actual)

    def test_denominators_unique_ids_and_split_identity(self) -> None:
        ids = [row["stable_id"] for row in self.candidates]
        self.assertEqual(199, len(ids))
        self.assertEqual(199, len(set(ids)))

        eligible_ids = {
            row["stable_id"]
            for row in self.candidates
            if row["e_paired_candidate"].lower() == "true"
        }
        excluded_ids = set(ids) - eligible_ids
        self.assertEqual(72, len(eligible_ids))
        self.assertEqual(127, len(excluded_ids))
        self.assertEqual(set(ids), eligible_ids | excluded_ids)
        self.assertFalse(eligible_ids & excluded_ids)

        split_ids = [row["stable_id"] for row in self.splits]
        self.assertEqual(72, len(split_ids))
        self.assertEqual(72, len(set(split_ids)))
        self.assertEqual(eligible_ids, set(split_ids))
        self.assertEqual(
            {"development": 51, "validation": 11, "held_out": 10},
            dict(Counter(row["split"] for row in self.splits)),
        )

    def test_primary_reason_subtotal_is_exactly_127(self) -> None:
        reasons = Counter(
            row["candidate_exclusion_reason"]
            for row in self.candidates
            if row["e_paired_candidate"].lower() != "true"
        )
        self.assertEqual(
            {
                "INSUFFICIENT_INDEPENDENT_UAS_REFERENCE_SUPPORT": 78,
                "INSUFFICIENT_INDEPENDENT_UAS_REFERENCE_SUPPORT;INSUFFICIENT_MVS_SUPPORT": 38,
                "INSUFFICIENT_INDEPENDENT_UAS_REFERENCE_SUPPORT;INSUFFICIENT_C4_SUPPORT": 2,
                "INSUFFICIENT_INDEPENDENT_UAS_REFERENCE_SUPPORT;INSUFFICIENT_MVS_SUPPORT;INSUFFICIENT_C4_SUPPORT": 9,
            },
            dict(reasons),
        )
        self.assertEqual(127, sum(reasons.values()))
        self.assertTrue(
            all(
                "INSUFFICIENT_INDEPENDENT_UAS_REFERENCE_SUPPORT" in reason
                for reason in reasons
            )
        )

    def test_compact_csv_matches_sealed_counts_and_percentages(self) -> None:
        by_key = {row["key"]: row for row in self.summary}
        expected = {
            "U_TARGET": (199, 199),
            "QUANTITATIVE_ELIGIBLE": (72, 199),
            "EXCLUDED": (127, 199),
            "DEVELOPMENT": (51, 72),
            "VALIDATION": (11, 72),
            "HELD_OUT": (10, 72),
            "UAS_REFERENCE_ONLY": (78, 127),
            "UAS_REFERENCE_AND_MVS": (38, 127),
            "UAS_REFERENCE_MVS_C4": (9, 127),
            "UAS_REFERENCE_AND_C4": (2, 127),
        }
        self.assertEqual(set(expected), set(by_key))
        for key, (count, section_denominator) in expected.items():
            row = by_key[key]
            self.assertEqual(count, int(row["count"]))
            self.assertEqual(199, int(row["total_denominator"]))
            self.assertEqual(section_denominator, int(row["section_denominator"]))
            self.assertEqual(percentage(count, 199), Decimal(row["percent_of_total"]))
            self.assertEqual(
                percentage(count, section_denominator),
                Decimal(row["percent_of_section"]),
            )
            self.assertEqual(
                f"git-blob:{CANDIDATE_LEDGER_BLOB}", row["source_binding"]
            )

        self.assertEqual(
            127,
            sum(
                int(row["count"])
                for row in self.summary
                if row["section"] == "primary_exclusion_reason"
            ),
        )

    def test_fixed_cases_and_existing_figure_are_reused_exactly(self) -> None:
        self.assertEqual(7, len(self.examples))
        self.assertEqual(7, len({row["stable_id"] for row in self.examples}))
        self.assertEqual(
            {"P1", "P2", "P3", "F1", "F2", "F3", "F4"},
            {row["label"] for row in self.examples},
        )
        candidate_by_id = {row["stable_id"]: row for row in self.candidates}
        for example in self.examples:
            candidate = candidate_by_id[example["stable_id"]]
            expected_status = candidate["e_paired_candidate"].lower() == "true"
            self.assertEqual(expected_status, example["candidate"].lower() == "true")
            expected_reason = (
                candidate["candidate_exclusion_reason"]
                or "PASS_ALL_INPUT_SUPPORT_RULES"
            )
            self.assertEqual(expected_reason, example["exclusion_reason"])

        figure = self.r5_manifest["corrected_figure"]
        self.assertEqual(FIGURE_NAME, figure["path"])
        self.assertEqual(245765, figure["bytes"])
        self.assertEqual(FIGURE_SHA256, figure["sha256"])
        self.assertIn(FIGURE_NAME, self.report)
        self.assertIn(FIGURE_SHA256, self.report)

    def test_human_verdict_remains_null_and_no_repeat_scope_is_explicit(self) -> None:
        self.assertIn("scientific_verdict: `null`", self.report)
        self.assertIn("eligibility computations / building reselections | 0 / 0", self.report)
        self.assertIn("raw UAS / `Images.zip` / `OPF.zip` reads or hashes | 0", self.report)


if __name__ == "__main__":
    unittest.main()
