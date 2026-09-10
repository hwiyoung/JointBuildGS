"""Bounded checks for sealed CSV grain, partition, denominator and matrix guards."""
import copy
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts/phd/local_complementary_refinement_v1"))
from analyze_strata_v2 import (completed_conditions, unique_index, validate_paired,
                               validate_partition, validate_threeway)


def paired():
    # A,G,LC eight-state counts = 1,2,...,8, total36. G->LC corrected8, damaged10.
    return dict(reference_count=36, comparator_near_count=22, comparator_far_count=14,
        corrected_count=8, damaged_count=10, retained_near_count=12, remaining_far_count=6,
        unchanged_proximity_class_count=18, finite_pair_count=36, became_missing_count=0,
        recovered_from_missing_count=0, closer_finite_count=10, farther_finite_count=11,
        equal_finite_distance_count=15, corrected_fraction_of_comparator_far=8/14,
        damaged_fraction_of_comparator_near=10/22, preservation_fraction_of_comparator_near=12/22,
        comparator_reference_recall=22/36, candidate_reference_recall=20/36)


def threeway():
    row = {f"anchor_global_local_near_{i:03b}_count": i+1 for i in range(8)}
    row.update(reference_count=36, global_corrected_count=7, global_correction_retained_by_local_count=4,
        global_correction_lost_by_local_count=3, additional_local_correction_count=2,
        global_damaged_count=11, global_damage_recovered_by_local_count=6,
        global_damage_remaining_in_local_count=5, additional_local_damage_count=7,
        anchor_valid_retained_by_both_count=8, anchor_far_remaining_far_in_both_count=1)
    return row


class StrataAuditTests(unittest.TestCase):
    def test_rates_have_distinct_conditioned_denominators(self):
        row = paired()
        validate_paired(row)
        row["corrected_fraction_of_comparator_far"] = 8/36
        with self.assertRaisesRegex(ValueError, "Ratio denominator"):
            validate_paired(row)

    def test_threeway_preserves_global_success_and_global_damage(self):
        baseline = dict(reference_count=36, corrected_count=7, damaged_count=11)
        validate_threeway(paired(), threeway(), baseline)
        corrupt = threeway()
        corrupt["global_correction_lost_by_local_count"] = 4
        with self.assertRaisesRegex(ValueError, "named decomposition"):
            validate_threeway(paired(), corrupt, baseline)
        baseline["corrected_count"] = 8
        with self.assertRaisesRegex(ValueError, "baseline success/damage"):
            validate_threeway(paired(), threeway(), baseline)

    def test_duplicate_grain_and_overlapping_partition_fail(self):
        row = dict(region="P1", cohort="STRICT_SUPPORT", threshold_m="0.5")
        with self.assertRaisesRegex(ValueError, "Duplicate analytical grain"):
            unique_index([row, dict(row, threshold_m=".50")], tuple(row))
        cohorts = {"ALL": {"reference_count": 10}, "SUPPORTED": {"reference_count": 4},
                   "UNSUPPORTED": {"reference_count": 6}}
        validate_partition(cohorts, "ALL", ("SUPPORTED", "UNSUPPORTED"), ["reference_count"])
        cohorts["SUPPORTED"]["reference_count"] = 5
        with self.assertRaisesRegex(ValueError, "partition mismatch"):
            validate_partition(cohorts, "ALL", ("SUPPORTED", "UNSUPPORTED"), ["reference_count"])

    def test_completed_matrix_discovery_is_not_p2_or_d005_specific(self):
        conditions = {("P1", "LC_D0_Pnative", "D0_Pnative", "raw", "ALL_REFERENCE", .5): {}}
        producer = dict(run_count=1, expected_full_run_count=3, selected_regions=["P1"])
        config = dict(regions=["P1", "P2", "P3"], conditions=[dict(id="LC_D0_Pnative", parent_condition="D0_Pnative")])
        discovered, status = completed_conditions(conditions, producer, config)
        self.assertEqual(discovered, [("P1", "LC_D0_Pnative", "D0_Pnative")])
        self.assertEqual(status, "PARTIAL_MATRIX")
        producer["run_count"] = 2
        with self.assertRaisesRegex(ValueError, "count differs"):
            completed_conditions(conditions, producer, config)
        producer["run_count"] = 1
        bad = copy.deepcopy(config)
        bad["conditions"][0]["parent_condition"] = "D005_Pnative"
        with self.assertRaisesRegex(ValueError, "mapping"):
            completed_conditions(conditions, producer, bad)


if __name__ == "__main__":
    unittest.main()
