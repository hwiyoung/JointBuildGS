import copy
import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import numpy as np

from scripts.input_and_alignment.gate_s0.uas_reference_coverage_r1_v1 import (
    run_uas_reference_coverage_r1 as coverage,
)


CONFIG_PATH = Path(
    "configs/input_and_alignment/gate_s0/uas_reference_coverage_r1_v1/coverage_r1_v1.json"
)


class CoverageR1Test(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))

    def test_precommitted_power_requirements(self):
        power = self.config["power"]
        observed = {
            (q, delta): coverage.required_pairs(
                q, delta, power["z_alpha"], power["z_power"]
            )
            for q in power["discordance_rates"]
            for delta in power["net_effects"]
        }
        self.assertEqual(
            observed,
            {
                (0.2, 0.15): 82,
                (0.2, 0.2): 45,
                (0.3, 0.15): 125,
                (0.3, 0.2): 69,
                (0.4, 0.15): 167,
                (0.4, 0.2): 93,
            },
        )

    def test_mask_pack_round_trip(self):
        masks = {
            "first": np.array([[True, False, True], [False, True, False]]),
            "second": np.array([[False, True, False], [True, False, True]]),
        }
        packed, names = coverage.pack_masks(masks)
        restored = coverage.unpack_masks(packed, names, (2, 3))
        self.assertEqual(names, ["first", "second"])
        for name in names:
            np.testing.assert_array_equal(restored[name], masks[name])

    def test_group_graph_uses_excluded_nodes_transitively(self):
        rows = [
            {"stable_id": "A", "execution_tile_id": "T1"},
            {"stable_id": "B", "execution_tile_id": "T1"},
            {"stable_id": "C", "execution_tile_id": "T2"},
            {"stable_id": "D", "execution_tile_id": "T3"},
        ]
        # B may later be ineligible, but it still joins A to C through shared P1.
        groups, members = coverage.group_graph(
            rows, {"A": [], "B": ["P1"], "C": ["P1"], "D": []}
        )
        self.assertEqual(groups["A"], groups["B"])
        self.assertEqual(groups["B"], groups["C"])
        self.assertNotEqual(groups["A"], groups["D"])
        self.assertEqual(members[groups["A"]], ["A", "B", "C"])

    def test_group_quotas_enforce_large_scope_minima(self):
        rule = self.config["eligibility"]
        self.assertEqual(
            coverage.group_quotas(30, rule["split_ratios"], rule["minimum_groups"]),
            {"development": 18, "validation": 6, "held_out": 6},
        )
        quotas = coverage.group_quotas(
            31, rule["split_ratios"], rule["minimum_groups"]
        )
        self.assertEqual(sum(quotas.values()), 31)
        self.assertGreaterEqual(quotas["development"], 18)
        self.assertGreaterEqual(quotas["validation"], 6)
        self.assertGreaterEqual(quotas["held_out"], 6)

    def test_split_assignment_is_order_independent(self):
        rule = self.config["eligibility"]
        sizes = {f"G{index:02d}": (index % 4) + 1 for index in range(30)}
        forward = coverage.assign_group_splits(
            sizes, rule["split_seed"], rule["split_ratios"], rule["minimum_groups"]
        )
        reverse = coverage.assign_group_splits(
            dict(reversed(list(sizes.items()))),
            rule["split_seed"],
            rule["split_ratios"],
            rule["minimum_groups"],
        )
        self.assertEqual(forward, reverse)

    def test_effective_size_penalizes_clustered_buildings(self):
        independent = coverage.effective_size([1] * 10, 0.05)
        clustered = coverage.effective_size([5, 5], 0.05)
        self.assertEqual(independent["n_eff"], 10)
        self.assertLess(clustered["n_eff"], 10)
        self.assertEqual(clustered["largest_group"], 5)

    def test_claim_scope_does_not_promote_small_held_out_set(self):
        claim, _ = coverage.claim_scope(
            [1] * 80,
            [1] * 20,
            {"development": 48, "validation": 16, "held_out": 16},
            self.config,
        )
        self.assertEqual(claim["status"], "DESCRIPTIVE_CENSUS_ONLY")
        self.assertIsNone(claim["scientific_verdict"])

    def test_all_four_claim_scope_transitions(self):
        main, _ = coverage.claim_scope(
            [1] * 200,
            [1] * 150,
            {"development": 30, "validation": 20, "held_out": 150},
            self.config,
        )
        large, _ = coverage.claim_scope(
            [2] * 50 + [1] * 50,
            [2] * 50,
            {"development": 30, "validation": 20, "held_out": 50},
            self.config,
        )
        descriptive, _ = coverage.claim_scope(
            [1] * 80,
            [1] * 20,
            {"development": 48, "validation": 12, "held_out": 20},
            self.config,
        )
        pilot, _ = coverage.claim_scope(
            [1] * 20,
            [1] * 6,
            {"development": 12, "validation": 2, "held_out": 6},
            self.config,
        )
        self.assertEqual(main["status"], "CONFIRMATORY_MAIN_CLAIM_CANDIDATE")
        self.assertEqual(large["status"], "CONFIRMATORY_LARGE_EFFECT_ONLY_CANDIDATE")
        self.assertEqual(descriptive["status"], "DESCRIPTIVE_CENSUS_ONLY")
        self.assertEqual(pilot["status"], "PILOT_ONLY_REFERENCE_SCOPE")
        self.assertTrue(main["confirmatory_minimum_held_out_groups_pass"])

    def test_finite_cluster_requirement_penalizes_six_groups(self):
        six = coverage.finite_cluster_required_pairs(0.3, 0.2, 0.025, 0.8, 6)
        fifty = coverage.finite_cluster_required_pairs(0.3, 0.2, 0.025, 0.8, 50)
        self.assertGreater(six["critical_value"], fifty["critical_value"])
        self.assertGreater(six["required_effective_pairs"], fifty["required_effective_pairs"])

    def test_bbox_association_is_inclusive_on_exact_edges(self):
        row = {
            "bbox_min_x": "1.0",
            "bbox_min_y": "2.0",
            "bbox_max_x": "3.0",
            "bbox_max_y": "4.0",
        }
        for point in ((1.0, 2.0), (1.0, 4.0), (3.0, 2.0), (3.0, 4.0)):
            self.assertTrue(coverage.inside_bbox(*point, row))
        self.assertFalse(coverage.inside_bbox(0.999, 3.0, row))

    def test_cell_footprint_hull_fill_is_bounded(self):
        metrics = coverage.cell_footprint_hull_metrics(
            [0.5, 1.5, 0.5], [0.5, 0.5, 1.5], 1.0
        )
        self.assertLessEqual(metrics["fill_ratio"], 1.0)
        self.assertEqual(metrics["bbox_min_x"], 0.0)
        self.assertEqual(metrics["bbox_max_y"], 2.0)

    def test_segmentation_splits_adjacent_height_discontinuity(self):
        config = copy.deepcopy(self.config)
        config["aoi"]["cell_m"] = 1.0
        config["segmentation"]["final_min_cells"] = 4
        top = np.zeros((3, 6), dtype=np.float64)
        top[:, 3:] = 2.0
        mask = np.ones_like(top, dtype=bool)
        fields = coverage.PlaneFields(
            rmse=np.zeros_like(top),
            normal_z=np.ones_like(top),
            neighbors=np.full_like(top, 9, dtype=np.uint16),
            a=np.zeros_like(top),
            b=np.zeros_like(top),
            center_c=top.copy(),
        )
        result = coverage.segment_patches(mask, top, fields, config)
        self.assertEqual(len(result["patches"]), 2)
        self.assertEqual(sorted(map(len, result["patches"].values())), [9, 9])
        self.assertTrue(
            any("height" in item["reasons"] for item in result["local_rejected"])
        )

    def test_segmentation_preserves_sloped_plane_and_replays_exactly(self):
        config = copy.deepcopy(self.config)
        config["aoi"]["cell_m"] = 1.0
        config["segmentation"]["final_min_cells"] = 4
        yy, xx = np.indices((4, 4))
        top = 0.1 * xx + 0.2 * yy
        fields = coverage.PlaneFields(
            rmse=np.zeros_like(top),
            normal_z=np.full_like(top, 1.0 / np.sqrt(1.05)),
            neighbors=np.full_like(top, 9, dtype=np.uint16),
            a=np.full_like(top, 0.1),
            b=np.full_like(top, 0.2),
            center_c=top.copy(),
        )
        first = coverage.segment_patches(np.ones_like(top, dtype=bool), top, fields, config)
        second = coverage.segment_patches(np.ones_like(top, dtype=bool), top, fields, config)
        self.assertEqual(len(first["patches"]), 1)
        self.assertEqual(
            coverage.canonical_json_bytes(first["patches"]),
            coverage.canonical_json_bytes(second["patches"]),
        )

    def test_normal_discontinuity_is_rejected(self):
        config = copy.deepcopy(self.config)
        config["segmentation"]["final_min_cells"] = 4
        top = np.zeros((3, 6), dtype=np.float64)
        top[:, 3:] = np.arange(3, dtype=np.float64)
        a = np.zeros_like(top)
        a[:, 3:] = 1.0
        fields = coverage.PlaneFields(
            rmse=np.zeros_like(top), normal_z=1.0 / np.sqrt(1.0 + a * a),
            neighbors=np.full_like(top, 9, dtype=np.uint16), a=a,
            b=np.zeros_like(top), center_c=top.copy(),
        )
        result = coverage.segment_patches(np.ones_like(top, dtype=bool), top, fields, config)
        self.assertEqual(len(result["patches"]), 2)
        self.assertTrue(any("normal" in item["reasons"] for item in result["local_rejected"]))

    def test_cross_plane_discontinuity_is_rejected(self):
        config = copy.deepcopy(self.config)
        top = np.zeros((1, 2), dtype=np.float64)
        fields = coverage.PlaneFields(
            rmse=np.zeros_like(top), normal_z=np.ones_like(top),
            neighbors=np.full_like(top, 9, dtype=np.uint16),
            a=np.zeros_like(top), b=np.zeros_like(top),
            center_c=np.array([[0.0, 1.0]]),
        )
        accepted, rejected = coverage.build_edges(
            np.ones_like(top, dtype=bool), top, fields, config
        )
        self.assertEqual(accepted, [])
        self.assertIn("cross_plane", rejected[0]["reasons"])

    def test_global_coherence_stops_locally_smooth_transitive_chain(self):
        config = copy.deepcopy(self.config)
        config["segmentation"]["final_min_cells"] = 4
        yy, xx = np.indices((5, 9))
        top = 0.05 * xx.astype(np.float64) ** 2
        a = 0.1 * xx.astype(np.float64)
        fields = coverage.PlaneFields(
            rmse=np.zeros_like(top), normal_z=1.0 / np.sqrt(1.0 + a * a),
            neighbors=np.full_like(top, 9, dtype=np.uint16), a=a,
            b=np.zeros_like(top), center_c=top.copy(),
        )
        result = coverage.segment_patches(np.ones_like(top, dtype=bool), top, fields, config)
        reasons = [reason for item in result["global_rejected"] for reason in item["reasons"]]
        self.assertTrue(reasons)
        self.assertLess(max(map(len, result["patches"].values())), top.size)

    def test_retry_audit_reports_success_min_and_unknown_max(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            attempts = coverage.SourceAttempts(root, "operation", retry_max=1)
            sources = [{"path": "grid.npz", "accepted_bytes": 100, "accepted_sha256": "a" * 64}]
            attempts.start("reference_grid", sources)
            attempts.start("reference_grid", sources)
            audit = attempts.audit({"reference_grid"})
            item = audit["per_source_read_digest_accounting"][0]
            self.assertEqual(item["known_successful_full_read_digest_passes"], 1)
            self.assertEqual(item["prior_unknown_attempts"], 1)
            self.assertEqual(item["full_read_digest_passes_min"], 1)
            self.assertEqual(item["full_read_digest_passes_max"], 2)
            self.assertEqual(item["bytes_read_and_digested_max"], 200)

    def test_pending_recovery_handles_incomplete_and_published_hardlink(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            final = root / "result.json"
            pending = root / ".result.json.pending"
            pending.write_bytes(b"partial")
            recovered = coverage.recover_pending(root)
            self.assertEqual(recovered[0]["action"], "QUARANTINED_INCOMPLETE")
            self.assertFalse(pending.exists())
            coverage.add_once_bytes(final, b"complete")
            os.link(final, pending)
            recovered = coverage.recover_pending(root)
            self.assertEqual(recovered[0]["action"], "UNLINKED_PUBLISHED_HARDLINK")
            self.assertEqual(final.read_bytes(), b"complete")

    def test_selected_promotion_pending_recovers_then_exact_output_reuses(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            final = root / "report.md"
            pending = root / ".report.md.pending"
            pending.write_bytes(b"partial")
            recovered = coverage.recover_selected_pending([final], root / "quarantine")
            self.assertEqual(recovered[0]["action"], "QUARANTINED_INCOMPLETE")
            coverage.add_once_bytes(final, b"exact")
            reused = coverage.add_once_bytes(final, b"exact")
            self.assertTrue(reused["reused_orphan_exact"])

    def test_promotion_invocation_pending_is_recovered_before_new_event(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            pending = root / "control" / "invocations" / ".0001-promote.json.pending"
            pending.parent.mkdir(parents=True)
            pending.write_bytes(b"partial-event")
            recovered = coverage.recover_pending(root)
            event = coverage.append_invocation_event(
                root, "promote", {"recovered_pending": recovered}
            )
            self.assertFalse(pending.exists())
            self.assertTrue(Path(event["path"]).is_file())
            body = json.loads(Path(event["path"]).read_bytes())
            self.assertEqual(body["recovered_pending"][0]["action"], "QUARANTINED_INCOMPLETE")

    def _completed_fixture(self, root):
        operation_id = "operation"
        coverage.append_invocation_event(root, "execute", {"operation_id": operation_id, "recovered_pending": []})
        checkpoints = coverage.Checkpoints(root, operation_id)
        attempts = coverage.SourceAttempts(root, operation_id, retry_max=1)
        attempts.start(
            "reference_grid",
            [{"path": "external-grid", "accepted_bytes": 10, "accepted_sha256": "a" * 64}],
        )
        attempts.start(
            "eligibility_metadata",
            [{"path": "external-ledger", "accepted_bytes": 20, "accepted_sha256": "b" * 64}],
        )
        stages = [
            (0, "runtime_control"),
            (10, "reference_candidate_frozen"),
            (20, "eligibility_candidate"),
            (30, "group_split_candidate"),
            (40, "claim_scope"),
            (100, "technical_summary"),
        ]
        output_records = []
        for ordinal, stage in stages:
            data = coverage.canonical_json_bytes({"ordinal": ordinal, "stage": stage})
            record = coverage.add_once_bytes(root / "outputs" / f"{ordinal}.json", data)
            output_records.append(record)
            checkpoints.write(ordinal, stage, {"output": record, **({"summary": record} if ordinal == 100 else {})})
        operation_identity = {"operation_id": operation_id, "source_commit": "a" * 40}
        audit = attempts.audit({"reference_grid", "eligibility_metadata"})
        ledger = {
            "schema": "jointbuildgs.gate_s0_uas_reference_coverage_execution_ledger.v1",
            "status": "COMPLETED",
            "operation_identity": operation_identity,
            "checkpoints": checkpoints.records,
            "source_attempts": audit,
            "invocation_events_at_completion": coverage.invocation_event_audit(root),
            "scientific_source_read_contract": {
                "per_source_read_digest_accounting": audit["per_source_read_digest_accounting"],
                "separate_grid_hash_passes": 0,
                "raw_source_reads": 0,
            },
            "scientific_verdict": None,
        }
        return ledger, operation_identity, checkpoints, attempts, output_records

    def test_completed_ledger_validates_outputs_without_opening_external_sources(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fixture = self._completed_fixture(root)
            result = coverage.validate_completed_ledger(*fixture[:4], root)
            self.assertEqual(result["checkpoints"]["verified_output_count"], 6)

    def test_completed_ledger_rejects_corrupt_or_symlink_output(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            ledger, identity, checkpoints, attempts, records = self._completed_fixture(root)
            victim = Path(records[2]["path"])
            victim.write_bytes(b"corrupt")
            with self.assertRaises(RuntimeError):
                coverage.validate_completed_ledger(ledger, identity, checkpoints, attempts, root)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            ledger, identity, checkpoints, attempts, records = self._completed_fixture(root)
            victim = Path(records[2]["path"])
            target = root / "target.json"
            target.write_bytes(victim.read_bytes())
            victim.unlink()
            victim.symlink_to(target)
            with self.assertRaises(RuntimeError):
                coverage.validate_completed_ledger(ledger, identity, checkpoints, attempts, root)

    def test_promotion_contract_lists_all_gate_review_outputs(self):
        observed = {path.name for path in coverage.PROMOTION_PATHS}
        self.assertTrue(
            {
                "technical_candidate_manifest_v1.json",
                "candidate_ledger_v1.csv",
                "group_graph_v1.csv",
                "split_candidate_v1.csv",
                "claim_scope_v1.json",
                "power_sensitivity_v1.csv",
                "pair_requirements_v1.csv",
                "patch_summary_v1.csv",
                "patch_association_qa_v1.csv",
                "baseline_attrition_v1.csv",
                "UAS_REFERENCE_COVERAGE_R1_REPORT_v1.md",
            }.issubset(observed)
        )

    def test_acceptance_binds_direct_parent_predecessor_and_image_digest(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            artifact_root = root / "artifacts"
            repo = root / "repo"
            output_namespace = "task-output"
            artifact_root.mkdir()
            accepted = repo / "artifacts" / "manifests" / "handoffs" / coverage.HANDOFF / "100-accepted.json"
            offered = accepted.with_name("000-offered.json")
            offered.parent.mkdir(parents=True)
            offered.write_bytes(b"offered")
            image_id = "sha256:" + "1" * 64
            acceptance_path = artifact_root / output_namespace / coverage.ACCEPTANCE_RELATIVE
            acceptance_path.parent.mkdir(parents=True)
            offered_commit, accepted_commit = "a" * 40, "b" * 40
            inputs = {
                name: {"path": f"inputs/{name}", "bytes": index, "sha256": str(index) * 64}
                for index, name in enumerate(("grid", "source_checkpoint", "eligibility"), start=1)
            }
            body = {
                "source_commit": offered_commit,
                "status": "PASS_METADATA_ONLY",
                "scientific_payload_bytes_read_or_hashed": 0,
                "project_docker_image_id": image_id,
                "input_stats": [
                    {"path": str(artifact_root / item["path"]), "bytes": item["bytes"]}
                    for item in inputs.values()
                ],
            }
            acceptance_data = coverage.canonical_json_bytes(body)
            acceptance_path.write_bytes(acceptance_data)
            receipt = {
                "state": "accepted",
                "handoff_id": coverage.HANDOFF,
                "task_id": coverage.TASK,
                "transport": {"exclusive_writer_ack": True},
                "verification": {"level": "artifact_verified", "docker_image_digest": image_id},
                "commits": {"offered_head": offered_commit, "receipt_head": "SELF"},
                "previous_receipt": {
                    "path": offered.relative_to(repo).as_posix(),
                    "sha256": coverage.sha256_bytes(offered.read_bytes()),
                },
                "artifacts": {
                    "records": [
                        {
                            "uri": "artifact://JointBuildGS/" + coverage.ACCEPTANCE_RELATIVE.as_posix(),
                            "bytes": len(acceptance_data),
                            "sha256": coverage.sha256_bytes(acceptance_data),
                        }
                    ]
                },
                "scientific": {"scientific_verdict": None},
            }
            accepted.write_bytes(coverage.canonical_json_bytes(receipt))
            config = {"output_namespace": output_namespace, "inputs": inputs}
            with (
                mock.patch.object(coverage, "REPO", repo),
                mock.patch.object(coverage, "ACCEPTED_RECEIPT_PATH", accepted),
                mock.patch.object(coverage, "HANDOFF_VALIDATOR_PATH", repo / "validator.py"),
                mock.patch.object(coverage, "git", return_value=offered_commit),
                mock.patch.object(coverage.subprocess, "run", return_value=SimpleNamespace(returncode=0, stdout="", stderr="")),
            ):
                result = coverage.validate_acceptance(accepted_commit, artifact_root, config)
            self.assertEqual(result["project_image_id"], image_id)
            self.assertEqual(result["offered_commit"], offered_commit)


if __name__ == "__main__":
    unittest.main()
