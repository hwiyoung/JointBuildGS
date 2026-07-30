#!/usr/bin/env python3
"""Tests for the committed-source FUS-W1 target resolver."""

from __future__ import annotations

import csv
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[2] / "phases/p2-gsjso/scripts/fusion_w1/fusion_w1_targets.py"
SPEC = importlib.util.spec_from_file_location("fusion_w1_targets", SCRIPT_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"cannot load resolver: {SCRIPT_PATH}")
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class FusionW1TargetTests(unittest.TestCase):
    maxDiff = None

    @classmethod
    def setUpClass(cls) -> None:
        cls.repo_root = SCRIPT_PATH.resolve().parents[4]
        cls.config_path = (
            cls.repo_root
            / "phases/p2-gsjso/configs/fusion_w1/fusion_w1_targets_v1.json"
        )
        cls.rows, cls.metadata = MODULE.resolve_targets(
            repo_root=cls.repo_root,
            config_path=cls.config_path,
        )

    def test_exact_population_cover_and_order(self) -> None:
        ids = [row["building_id"] for row in self.rows]
        self.assertEqual(len(ids), 178)
        self.assertEqual(len(set(ids)), 178)
        self.assertEqual(
            [int(row["processing_order"]) for row in self.rows],
            list(range(1, 179)),
        )
        population = {
            row["building_id"]
            for row in MODULE._read_csv(
                self.repo_root / "docs/experiments/input-and-alignment/boundary_map/tables/boundary_map_v4_1_ladder.csv"
            )
        }
        self.assertEqual(set(ids), population)

    def test_core_sources_are_resolved_by_locked_filters(self) -> None:
        selected = self.metadata["selected_ids_by_source"]
        self.assertEqual(len(selected["p0_dim_failure"]), 8)
        self.assertEqual(len(selected["c001_dense_success"]), 10)
        self.assertEqual(len(selected["height_primary"]), 4)
        self.assertEqual(len(selected["outline_rank_spread"]), 4)
        self.assertEqual(len(selected["textured_control"]), 2)
        self.assertIsNone(selected["gs4buildings_overlap"])
        self.assertIsNone(self.metadata["core_source_counts"]["gs4buildings_overlap"])
        self.assertIsNone(self.metadata["final_core_count"])
        self.assertIsNone(self.metadata["final_extension_count"])
        self.assertEqual(self.metadata["resolved_core_lower_bound_count"], 28)
        self.assertEqual(self.metadata["provisional_extension_count"], 150)
        self.assertFalse(self.metadata["core_priority_complete"])

    def test_p0_filter_matches_canonical_failure_rows(self) -> None:
        source = MODULE._read_csv(
            self.repo_root
            / "phases/p0-audit/docs/W3_2c_canonical_paired_status.csv"
        )
        expected = [
            row["building_id"]
            for row in source
            if row["coverage_control_population"] == "yes"
            and row["dim_failure_bucket_v1"]
            == "roof_matching_assembly_failure"
        ]
        self.assertEqual(
            self.metadata["selected_ids_by_source"]["p0_dim_failure"], expected
        )

    def test_dense_success_filter_matches_night_a_c001_table(self) -> None:
        source = MODULE._read_csv(self.repo_root / "docs/experiments/evaluation/qs_rescore/tables/qs_rescore_pairs.csv")
        expected = [
            row["building_id"]
            for row in source
            if row["row_type"] == "building"
            and row["dense_has_lod22"].lower() == "true"
        ]
        self.assertEqual(
            self.metadata["selected_ids_by_source"]["c001_dense_success"],
            expected,
        )

    def test_height_primary_comes_from_committed_lock(self) -> None:
        lock = json.loads(
            (
                self.repo_root
                / "phases/p2-gsjso/configs/boundary_and_robustness/primary4_assembly_validation_v2.json"
            ).read_text(encoding="utf-8")
        )
        expected = [f"DEBY_LOD2_{value}" for value in lock["targets_in_output_order"]]
        self.assertEqual(
            self.metadata["selected_ids_by_source"]["height_primary"], expected
        )
        row_by_id = {row["building_id"]: row for row in self.rows}
        self.assertTrue(all(row_by_id[value]["tier"] == "height" for value in expected))

    def test_textured_control_rule_uses_shortlist_and_metric(self) -> None:
        selected = self.metadata["selected_ids_by_source"]["textured_control"]
        self.assertEqual(selected[0], "DEBY_LOD2_4908023")
        self.assertEqual(selected[1], "DEBY_LOD2_4908028")
        row_by_id = {row["building_id"]: row for row in self.rows}
        shortlist = [
            row
            for row in self.rows
            if 4908023
            <= int(row["building_id"].removeprefix("DEBY_LOD2_"))
            <= 4908028
        ]
        non_anchor = [
            row for row in shortlist if row["building_id"] != selected[0]
        ]
        best = min(
            non_anchor,
            key=lambda row: (
                float(row["texture_low_gradient_fraction"]),
                int(row["building_id"].removeprefix("DEBY_LOD2_")),
            ),
        )
        self.assertEqual(selected[1], best["building_id"])
        self.assertEqual(row_by_id[selected[0]]["cohort"], "core")
        self.assertEqual(row_by_id[selected[1]]["cohort"], "core")

    def test_outline_selection_is_even_rank_spread_after_core_exclusion(self) -> None:
        audit = self.metadata["outline_rank_spread"]
        self.assertEqual(audit["candidate_count_after_core_exclusion"], 39)
        self.assertEqual(audit["rank_fractions"], ["0/3", "1/3", "2/3", "3/3"])
        self.assertEqual(audit["rank_indices_zero_based"], [0, 13, 25, 38])
        selected = [
            record["building_id"] for record in audit["selected"]
        ]
        self.assertEqual(
            selected,
            self.metadata["selected_ids_by_source"]["outline_rank_spread"],
        )
        other_core = set().union(
            *(
                set(self.metadata["selected_ids_by_source"][name])
                for name in (
                    "p0_dim_failure",
                    "c001_dense_success",
                    "height_primary",
                    "textured_control",
                )
            )
        )
        self.assertTrue(set(selected).isdisjoint(other_core))

    def test_extension_order_is_surface_height_outline_round_robin(self) -> None:
        extension = [row for row in self.rows if row["cohort"] == "extension"]
        tier_cycle = ["surface", "height", "outline"]
        queues = {tier: [] for tier in tier_cycle}
        for row in extension:
            queues[row["tier"]].append(row["building_id"])
        for values in queues.values():
            self.assertEqual(
                values,
                sorted(
                    values,
                    key=lambda value: int(
                        value.removeprefix("DEBY_LOD2_")
                    ),
                ),
            )

        remaining = {tier: len(values) for tier, values in queues.items()}
        observed_tiers = [row["tier"] for row in extension]
        expected_tiers: list[str] = []
        while any(remaining.values()):
            for tier in tier_cycle:
                if remaining[tier]:
                    expected_tiers.append(tier)
                    remaining[tier] -= 1
        self.assertEqual(observed_tiers, expected_tiers)

    def test_gs4_public_artifact_gap_is_unknown_and_queue_is_provisional(self) -> None:
        gs4 = self.metadata["gs4buildings"]
        self.assertEqual(gs4["status"], "unresolvable_public_artifact_missing")
        self.assertIs(gs4["id_inference_allowed"], False)
        self.assertEqual(gs4["overlap_resolution"], "unknown")
        self.assertIsNone(gs4["overlap_count"])
        self.assertIsNone(gs4["overlap_ids"])
        self.assertEqual(
            gs4["repository_url"],
            "https://github.com/zqlin0521/GS4Buildings",
        )
        self.assertEqual(gs4["checked_ref"], "refs/heads/main")
        self.assertEqual(
            gs4["checked_commit"],
            "1d25dac38d44a72cbf60a0bab730eed7f9e3663a",
        )
        self.assertEqual(gs4["checked_at_utc"], "2026-07-24T15:30:10Z")
        self.assertEqual(
            self.metadata["status"],
            "provisional_external_public_artifact_gap",
        )
        self.assertEqual(
            self.metadata["queue_status"],
            "provisional_gs4_overlap_unresolved",
        )
        for row in self.rows:
            self.assertEqual(
                row["gs4buildings_overlap_status"],
                "unresolvable_public_artifact_missing",
            )
            self.assertEqual(
                row["queue_status"],
                "provisional_gs4_overlap_unresolved",
            )
            self.assertIn(
                "overlap_unknown_not_measured_as_zero",
                row["gs4buildings_overlap_reason"],
            )
        extension = [row for row in self.rows if row["cohort"] == "extension"]
        self.assertTrue(
            all(
                row["cohort_resolution_status"]
                == "provisional_extension_pending_gs4_overlap"
                for row in extension
            )
        )

    def test_declared_lock_fields_fail_closed_when_mutated(self) -> None:
        cases = (
            (
                ("outline_rank_spread", "rank_rounding"),
                "floor",
                "outline_rank_spread.rank_rounding",
            ),
            (
                ("outline_rank_spread", "tie_break"),
                "canonical_building_id_numeric_descending",
                "outline_rank_spread.tie_break",
            ),
            (
                ("textured_control", "anchor_rule"),
                "maximum_numeric_id_in_locked_shortlist",
                "textured_control.anchor_rule",
            ),
            (
                ("textured_control", "second_rule"),
                "maximum_texture_low_gradient_fraction_excluding_anchor",
                "textured_control.second_rule",
            ),
            (
                ("textured_control", "tie_break"),
                "canonical_building_id_numeric_descending",
                "textured_control.tie_break",
            ),
            (
                ("extension_within_tier_order",),
                "canonical_building_id_numeric_descending",
                "extension_within_tier_order",
            ),
        )
        base = json.loads(self.config_path.read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for index, (path, replacement, expected_error) in enumerate(cases):
                with self.subTest(path=path):
                    mutated = json.loads(json.dumps(base))
                    target = mutated
                    for key in path[:-1]:
                        target = target[key]
                    target[path[-1]] = replacement
                    config_path = root / f"mutated_{index}.json"
                    config_path.write_text(
                        json.dumps(mutated),
                        encoding="utf-8",
                    )
                    with self.assertRaisesRegex(
                        MODULE.ResolutionError,
                        expected_error,
                    ):
                        MODULE.resolve_targets(
                            repo_root=self.repo_root,
                            config_path=config_path,
                        )

    def test_generation_parent_git_gate_fails_closed(self) -> None:
        generation = self.metadata["generation"]
        parent_commit = generation["generation_parent_commit"]
        parent_branch = generation["generation_parent_branch"]

        with self.assertRaisesRegex(
            MODULE.ResolutionError,
            "current Git branch",
        ):
            MODULE._validate_generation_git_state(
                repo_root=self.repo_root,
                parent_commit=parent_commit,
                parent_branch="not-the-current-branch",
            )

        with self.assertRaisesRegex(
            MODULE.ResolutionError,
            "generation parent commit does not exist",
        ):
            MODULE._validate_generation_git_state(
                repo_root=self.repo_root,
                parent_commit="0" * 40,
                parent_branch=parent_branch,
            )

        non_ancestor_result = MODULE._run_git(
            self.repo_root,
            "rev-list",
            "--all",
            "--not",
            "HEAD",
        )
        self.assertEqual(non_ancestor_result.returncode, 0)
        non_ancestors = non_ancestor_result.stdout.splitlines()
        if non_ancestors:
            with self.assertRaisesRegex(
                MODULE.ResolutionError,
                "not an ancestor of HEAD",
            ):
                MODULE._validate_generation_git_state(
                    repo_root=self.repo_root,
                    parent_commit=non_ancestors[0],
                    parent_branch=parent_branch,
                )

    def test_written_outputs_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / "w1_targets.csv"
            metadata_output = root / "w1_targets_manifest.json"
            metadata = MODULE.build_outputs(
                repo_root=self.repo_root,
                config_path=self.config_path,
                output_path=output,
                metadata_output_path=metadata_output,
            )
            with output.open("r", encoding="utf-8", newline="") as handle:
                written_rows = list(csv.DictReader(handle))
            written_metadata = json.loads(metadata_output.read_text(encoding="utf-8"))
            self.assertEqual(written_rows, self.rows)
            self.assertEqual(written_metadata["population_count"], 178)
            self.assertEqual(
                written_metadata["output"]["sha256"],
                metadata["output"]["sha256"],
            )
            verified = MODULE.verify_outputs(
                repo_root=self.repo_root,
                config_path=self.config_path,
                output_path=output,
                metadata_output_path=metadata_output,
            )
            self.assertEqual(verified, written_metadata)

    def test_fixed_repository_outputs_match_exact_regeneration(self) -> None:
        output = (
            self.repo_root
            / "phases/p2-gsjso/runs/fusion_w1/20260724_fusion_w1/w1_targets.csv"
        )
        metadata_output = output.with_name("w1_targets_manifest.json")
        verified = MODULE.verify_outputs(
            repo_root=self.repo_root,
            config_path=self.config_path,
            output_path=output,
            metadata_output_path=metadata_output,
        )
        self.assertEqual(verified["population_count"], 178)

    def test_output_bundle_tamper_is_detected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / "w1_targets.csv"
            metadata_output = root / "w1_targets_manifest.json"
            MODULE.build_outputs(
                repo_root=self.repo_root,
                config_path=self.config_path,
                output_path=output,
                metadata_output_path=metadata_output,
                generated_utc="2026-07-24T15:30:10+00:00",
            )
            output.write_bytes(output.read_bytes() + b"\n")
            with self.assertRaisesRegex(
                MODULE.ResolutionError,
                "fixed CSV output does not match",
            ):
                MODULE.verify_outputs(
                    repo_root=self.repo_root,
                    config_path=self.config_path,
                    output_path=output,
                    metadata_output_path=metadata_output,
                )

            MODULE.build_outputs(
                repo_root=self.repo_root,
                config_path=self.config_path,
                output_path=output,
                metadata_output_path=metadata_output,
                generated_utc="2026-07-24T15:30:10+00:00",
            )
            tampered_manifest = json.loads(
                metadata_output.read_text(encoding="utf-8")
            )
            tampered_manifest["core_priority_complete"] = True
            metadata_output.write_text(
                json.dumps(tampered_manifest, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(
                MODULE.ResolutionError,
                "fixed target manifest does not match",
            ):
                MODULE.verify_outputs(
                    repo_root=self.repo_root,
                    config_path=self.config_path,
                    output_path=output,
                    metadata_output_path=metadata_output,
                )


if __name__ == "__main__":
    unittest.main()
