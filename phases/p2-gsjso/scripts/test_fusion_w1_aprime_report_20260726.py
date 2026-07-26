#!/usr/bin/env python3
"""Focused contract tests for the A-prime observational report generator."""
from __future__ import annotations

import copy
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np


REPO = Path(__file__).resolve().parents[3]
MODULE_PATH = REPO / "phases/p2-gsjso/scripts/fusion_w1_aprime_report_20260726.py"
SPEC = importlib.util.spec_from_file_location("fusion_w1_aprime_report", MODULE_PATH)
if SPEC is None or SPEC.loader is None:  # pragma: no cover - import setup guard
    raise RuntimeError(f"cannot import {MODULE_PATH}")
report = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = report
SPEC.loader.exec_module(report)


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def complete_payload(*, legacy_state: str | None = None) -> dict:
    legacy: dict = {
        "eligible_for_preregistered_judgment": False,
        "role": "comparison_only",
    }
    if legacy_state is None:
        legacy["measurements"] = {
            "assembly_lod2_success": False,
            "plane_f1": 0.25,
            "roof_rms_m": 0.8,
        }
    else:
        legacy.update(
            {
                "state": legacy_state,
                "assembly_status": "NOT_ASSEMBLED",
                "measurement_status": "NOT_MEASURED",
                "reason_code": "zero_class6_inside_footprint_after_SMRF_overlay",
                "counts": {
                    "n_clip": 125,
                    "n_used": 125,
                    "n_building_in_fp": 0,
                    "class_counts": {"2": 125},
                    "required_classes": [2, 6],
                    "missing_required_classes": [6],
                },
                "measurements": {
                    "assembly_lod2_success": None,
                    "plane_f1": None,
                    "roof_rms_m": None,
                },
                "diagnostics": {
                    "class6_points_n": 0,
                    "class2_points_n": 125,
                    "roof_clusters_count": 0,
                },
            }
        )
    return {
        "schema": report.READOUT_COMPLETE_SCHEMA,
        "state": "COMPLETE",
        "primary": {
            "eligible_for_preregistered_judgment": True,
            "measurements": {
                "assembly_lod2_success": True,
                "has_lod22_geometry": True,
                "lod1_fallback": False,
                "val3dity_valid": True,
                "plane_precision": 0.8,
                "plane_recall": 0.75,
                "plane_f1": 0.774,
                "roof_rms_m": 0.19,
                "roof_hausdorff_m": 0.61,
                "roof_completeness": 0.91,
                "face_count_ratio": 1.1,
            },
        },
        "legacy_alpha": legacy,
    }


def queue_fixture_config(config: dict, root: Path) -> dict:
    value = copy.deepcopy(config)
    queue_root = root / "unattended_queue"
    for name, relative in {
        "queue_plan": "queue_plan.json",
        "queue_stage_records": "stage_records",
        "queue_training_failure_archive": "training_failure_archive",
        "queue_status_json": "status.json",
        "queue_status_csv": "status.csv",
        "queue_stage_stop": "stage_stop.json",
        "queue_complete": "complete.json",
        "queue_events": "events.jsonl",
        "queue_event_sequence": "event_sequence.json",
    }.items():
        value["sources"][name] = str(queue_root / relative)
    value["sources"]["queue_recovery_root"] = str(queue_root / "recovery")
    value["sources"]["queue_recovery_controller"] = str(
        queue_root / "recovery" / "controller.json"
    )
    value["sources"]["training_root"] = str(root / "training")
    value["sources"]["readout_root"] = str(root / "readout")
    return value


class ContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.config = report.load_config(verify_locked_files=False)
        cls.targets = report.load_targets(cls.config)

    def test_metric_state_and_queue_contracts_are_exact(self) -> None:
        contract = self.config["measurement_contract"]
        self.assertEqual(
            contract["metric_fields"],
            [
                "assembly_lod2_success",
                "has_lod22_geometry",
                "lod1_fallback",
                "val3dity_valid",
                "plane_precision",
                "plane_recall",
                "plane_f1",
                "roof_rms_m",
                "roof_hausdorff_m",
                "roof_completeness",
                "face_count_ratio",
            ],
        )
        self.assertEqual(
            set(contract["measurement_states"]),
            {"measured", "missing", "censored", "not_applicable"},
        )
        self.assertEqual(
            set(contract["comparison_nonmeasurement_outcomes"]),
            {"NOT_ASSEMBLED", "UNCONSTRUCTABLE"},
        )
        self.assertEqual(contract["comparison_nonmeasurement_state"], "not_applicable")
        self.assertIsNone(self.config["queue_contract"]["time_cutoff"])
        self.assertEqual(self.config["queue_contract"]["expected_stage_entries"], 22)
        self.assertEqual(
            self.config["provenance_contract"]["execution_head"],
            "de8852c00c737eced081f2627b49bcedddade652",
        )

        jobs = report.expected_jobs(self.targets, self.config)
        self.assertEqual(len(jobs), 21)
        self.assertEqual([(job.arm, job.run) for job in jobs[:9]], [("Aprime", "r1")] * 9)
        self.assertEqual([(job.arm, job.run) for job in jobs[9:18]], [("Aprime", "r2")] * 9)
        self.assertEqual(
            [job.building_id for job in jobs[18:]],
            ["DEBY_LOD2_42364609", "DEBY_LOD2_42364659", "DEBY_LOD2_4908023"],
        )

    def test_target_population_and_texture_rule(self) -> None:
        self.assertEqual(len(self.targets), 9)
        field = self.config["measurement_contract"]["texture_field"]
        at_threshold = {field: "0.804"}
        above_threshold = {field: "0.8040001"}
        self.assertEqual(report.texture_stratum(at_threshold, self.config), "textured")
        self.assertEqual(report.texture_stratum(above_threshold, self.config), "textureless")

    def test_fixed_outputs_and_transactional_publication_contract(self) -> None:
        outputs = self.config["outputs"]
        for key in (
            "one_page_markdown",
            "report_markdown",
            "scores_csv",
            "alpha_comparison_csv",
            "opacity_csv",
            "queue_stage_records_csv",
            "queue_archives_csv",
            "t4_bundle_manifest",
            "panels_dir",
            "manifest",
            "receipt",
        ):
            self.assertIn(key, outputs)
        publication = self.config["publication"]
        self.assertTrue(publication["immutable_content_addressed_snapshots"])
        self.assertTrue(publication["staging_before_snapshot_publish"])
        self.assertTrue(publication["receipt_written_last_inside_snapshot"])
        self.assertTrue(publication["source_inventory_rehashed_before_publish"])
        self.assertTrue(publication["partial_outputs_allowed"])
        self.assertTrue(publication["cached_partial_rejected_for_final"])
        self.assertTrue(publication["queue_stage_receipts_sha_verified"])
        self.assertTrue(publication["queue_archive_receipts_sha_verified"])

    def test_docker_wrapper_is_nonnetworked_and_nonroot(self) -> None:
        wrapper = (
            REPO / "phases/p2-gsjso/scripts/run_fusion_w1_aprime_report_20260726.sh"
        ).read_text(encoding="utf-8")
        self.assertIn("--network=none", wrapper)
        self.assertIn('--user "$(id -u):$(id -g)"', wrapper)
        self.assertIn("--pull=never", wrapper)
        self.assertIn("EXPECTED_IMAGE_ID=", wrapper)
        self.assertIn("GIT_COMMON_DIR=", wrapper)
        self.assertIn('GIT_MOUNTS=(--volume "$GIT_COMMON_DIR:$GIT_COMMON_DIR:ro")', wrapper)
        self.assertNotIn("--gpus", wrapper)
        for mode in ("test)", "check)", "partial)", "final)"):
            self.assertIn(mode, wrapper)

    def test_partial_markdown_keeps_all_nine_buildings_without_scores(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config = copy.deepcopy(self.config)
            config["sources"]["training_root"] = str(root / "training")
            config["sources"]["readout_root"] = str(root / "readout")
            for key in (
                "five_pin",
                "T1",
                "T2",
                "T2_failure",
                "T3",
                "T3_scores",
                "T4",
                "t5_summary",
                "issues",
            ):
                config["sources"][key] = str(root / f"missing_{key}")
            jobs = report.expected_jobs(self.targets, config)
            scores, _, _ = report.build_score_rows(jobs, config, {}, {})
            replicate = report.build_replicate_medians(scores, config)
            gauges = report.build_gauges(scores, replicate)
            preflight = report.preflight_rows(config)
            overlap = report.overlap_rows(self.targets)
            one_page = report.build_one_page_markdown(
                gauges, scores, preflight, overlap, "snapshot", config
            )
            full = report.build_report_markdown(
                one_page,
                scores,
                report.build_summary(scores, config),
                preflight,
                overlap,
                [],
                report.incomplete_rows(scores),
                config,
            )
        self.assertEqual(one_page.count("DEBY_LOD2_"), 9)
        self.assertIn("## 동별 A′ 기록", one_page)
        self.assertIn("## 미완 산출 목록", full)
        report.assert_observational_language(full)


class MeasurementStateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.config = report.load_config(verify_locked_files=False)

    def test_false_and_zero_are_measured_not_missing(self) -> None:
        value, state = report.metric_value(
            {"assembly_lod2_success": False},
            "assembly_lod2_success",
            self.config,
        )
        self.assertIs(value, False)
        self.assertEqual(state, "measured")
        value, state = report.metric_value({"roof_rms_m": 0}, "roof_rms_m", self.config)
        self.assertEqual(value, 0.0)
        self.assertEqual(state, "measured")
        self.assertEqual(
            report.metric_value({}, "roof_rms_m", self.config), (None, "missing")
        )
        self.assertEqual(
            report.metric_value(
                {"roof_rms_m": 3.2}, "roof_rms_m", self.config, censored=True
            ),
            (None, "censored"),
        )

    def test_find_score_row_accepts_complete_receipt_measurements(self) -> None:
        payload = complete_payload()
        primary = report.find_score_row(payload, "primary")
        legacy = report.find_score_row(payload, "legacy_alpha")
        self.assertEqual(primary["roof_rms_m"], 0.19)
        self.assertEqual(legacy["roof_rms_m"], 0.8)

    def test_legacy_nonassembly_is_not_applicable_and_primary_stays_measured(self) -> None:
        payload = complete_payload(legacy_state="NOT_ASSEMBLED")
        observation = report.branch_observation(payload, "legacy_alpha")
        self.assertEqual(observation["outcome"], "NOT_ASSEMBLED")
        self.assertEqual(observation["assembly_status"], "NOT_ASSEMBLED")
        self.assertEqual(observation["measurement_status"], "NOT_MEASURED")
        self.assertEqual(
            observation["reason_code"],
            "zero_class6_inside_footprint_after_SMRF_overlay",
        )
        self.assertEqual(observation["counts"]["n_building_in_fp"], 0)

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config = copy.deepcopy(self.config)
            config["sources"]["training_root"] = str(root / "training")
            config["sources"]["readout_root"] = str(root / "readout")
            target = report.load_targets(config)[0]
            job = report.Job(1, target["building_id"], "Aprime", "r1", target)
            _, readout_dir = report.job_dirs(job, config)
            write_json(readout_dir / "complete.json", payload)
            rows, comparisons, _ = report.build_score_rows([job], config, {}, {})

        self.assertEqual(rows[0]["job_terminal_state"], "measured")
        self.assertEqual(rows[0]["primary_measurement_state"], "measured")
        self.assertEqual(rows[0]["alpha_comparison_state"], "not_applicable")
        self.assertEqual(rows[0]["alpha_comparison_outcome"], "NOT_ASSEMBLED")
        self.assertEqual(rows[0]["alpha_comparison_assembly_status"], "NOT_ASSEMBLED")
        legacy = next(row for row in comparisons if not row["eligible_for_preregistered_gauges"])
        self.assertEqual(legacy["measurement_state"], "not_applicable")
        self.assertEqual(legacy["roof_rms_m_state"], "not_applicable")
        self.assertEqual(legacy["diagnostic_counts_json"]["n_clip"], 125)

    def test_complete_receipt_only_primary_can_censor_job(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            job_dir = root / "job"
            training = root / "training"
            payload = complete_payload(legacy_state="NOT_ASSEMBLED")
            payload["legacy_alpha"]["is_censored"] = True
            write_json(job_dir / "complete.json", payload)
            state, _, _ = report.terminal_evidence(job_dir, training)
            self.assertEqual(state, "measured")
            payload["primary"]["measurement_state"] = "censored"
            write_json(job_dir / "complete.json", payload)
            state, _, _ = report.terminal_evidence(job_dir, training)
            self.assertEqual(state, "censored")

    def test_readout_retry_is_terminal_only_after_three_same_signatures(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            job = root / "job"
            training = root / "training"
            for number, signature in enumerate(("one", "two", "three"), 1):
                write_json(
                    job / f"attempts/attempt_{number:03d}/failure.json",
                    {"state": "FAILED", "error_signature": signature},
                )
            state, _, _ = report.terminal_evidence(job, training)
            self.assertEqual(state, "retry_pending")

            for number in range(1, 4):
                write_json(
                    job / f"attempts/attempt_{number:03d}/failure.json",
                    {"state": "FAILED", "error_signature": "same"},
                )
            state, evidence, _ = report.terminal_evidence(job, training)
            self.assertEqual(state, "skipped")
            self.assertTrue(evidence.endswith("attempt_003/failure.json"))

    def test_numeric_aggregate_excludes_missing_and_censored(self) -> None:
        rows = [
            {"roof_rms_m": 0.0, "roof_rms_m_state": "measured"},
            {"roof_rms_m": 99.0, "roof_rms_m_state": "missing"},
            {"roof_rms_m": 88.0, "roof_rms_m_state": "censored"},
        ]
        self.assertEqual(report.numeric_values(rows, "roof_rms_m"), [0.0])

    def test_two_run_median_and_p0_delta_require_both_replicates(self) -> None:
        metrics = self.config["measurement_contract"]["metric_fields"]

        def member(value: float, run: str, state: str = "measured") -> dict:
            row = {
                "building_id": "B1",
                "arm": "Aprime",
                "run": run,
                "target_role": "dim_failure",
                "tier": "failed8",
                "cohort": "core",
                "texture_stratum": "textured",
                "job_terminal_state": "measured",
                "primary_measurement_state": state,
                "p0prime_roof_rms_m": 0.13,
                "p0prime_roof_rms_m_state": "measured",
            }
            for metric in metrics:
                row[metric] = value
                row[f"{metric}_state"] = state
            row["roof_rms_m"] = value
            return row

        complete = report.build_replicate_medians(
            [member(0.1, "r1"), member(0.2, "r2")], self.config
        )[0]
        self.assertAlmostEqual(complete["roof_rms_m_replicate_median"], 0.15)
        self.assertAlmostEqual(complete["roof_rms_m_replicate_range"], 0.1)
        self.assertAlmostEqual(complete["roof_rms_median_delta_vs_p0prime"], 0.02)
        self.assertIs(complete["rms_median_within_p0prime_plus_0p05"], True)

        partial = report.build_replicate_medians([member(0.1, "r1")], self.config)[0]
        self.assertEqual(partial["roof_rms_m_replicate_state"], "missing")
        self.assertIsNone(partial["roof_rms_m_replicate_median"])

    def test_issue_inventory_preserves_case_insensitive_status_and_bullets(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "issues.md"
            path.write_text(
                "# issues\n\n## Runtime item\n\n- Status: RECORDED\n- message: retained\n",
                encoding="utf-8",
            )
            config = copy.deepcopy(self.config)
            config["sources"]["issues"] = str(path)
            rows = report.issue_rows(config)
        self.assertEqual(
            [row["record_type"] for row in rows],
            ["heading", "status_line", "bullet"],
        )
        self.assertEqual(rows[1]["text"], "- Status: RECORDED")


class QueueEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.base_config = report.load_config(verify_locked_files=False)
        cls.targets = report.load_targets(cls.base_config)

    def _plan(self, config: dict) -> tuple[list[report.Job], list[dict]]:
        jobs = report.expected_jobs(self.targets, config)
        entries = report.expected_queue_stage_specs(jobs, config)
        queue_config = report.repo_path(config["locked_inputs"]["queue_config"]["path"])
        write_json(
            Path(config["sources"]["queue_plan"]),
            {
                "schema": report.QUEUE_PLAN_SCHEMA,
                "state": "ACTIVE",
                "run_id": config["run_id"],
                "task_id": "FUS-W1-APRIME-QUEUE-001",
                "config": report.receipt_binding(queue_config),
                "git_lock": {
                    "head": config["provenance_contract"]["execution_head"],
                    "branch": config["branch"],
                },
                "entries": entries,
                "stage_entries_n": 22,
                "unique_jobs_n": 21,
                "actual_training_started_at_publication": False,
                "interpretation_or_verdict": None,
            },
        )
        return jobs, entries

    @staticmethod
    def _stage_payload(entry: dict, source: dict, *, status: str = "MEASURED") -> dict:
        return {
            "schema": report.QUEUE_STAGE_RECORD_SCHEMA,
            "status": status,
            "entry": entry,
            "source": "readout_complete" if status == "MEASURED" else "test_failure",
            "source_receipts": [source],
            "error_type": None if status == "MEASURED" else "TestFailure",
            "error_signature": None if status == "MEASURED" else "same",
            "same_signature_attempts": None if status == "MEASURED" else 1,
            "smoke_reuse": None,
            "partial_results_reviewable": True,
            "interpretation_or_verdict": None,
        }

    def _smoke_and_reuse(
        self, config: dict, entries: list[dict], source_path: Path
    ) -> tuple[Path, Path]:
        source = report.receipt_binding(source_path)
        smoke, reuse = entries[0], entries[1]
        smoke_path = report.queue_stage_record_path(config, smoke)
        write_json(smoke_path, self._stage_payload(smoke, source))
        reuse_payload = self._stage_payload(reuse, source)
        reuse_payload["smoke_reuse"] = {
            "reused": True,
            "smoke_stage_record": report.receipt_binding(smoke_path),
            "identical_readout_complete_receipt": source,
        }
        reuse_path = report.queue_stage_record_path(config, reuse)
        write_json(reuse_path, reuse_payload)
        return smoke_path, reuse_path

    def test_stage_records_deduplicate_smoke_22_to_21_with_exact_sha(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config = queue_fixture_config(self.base_config, root)
            jobs, entries = self._plan(config)
            readout = root / "receipts/readout_complete.json"
            readout_payload = complete_payload(legacy_state="NOT_ASSEMBLED")
            readout_payload["identity"] = {
                "building_id": jobs[0].building_id,
                "arm": jobs[0].arm,
                "replicate": jobs[0].run,
                "profile": "full",
            }
            write_json(readout, readout_payload)
            smoke_path, reuse_path = self._smoke_and_reuse(config, entries, readout)
            evidence = report.load_queue_evidence(jobs, config)
            rows, _, _ = report.build_score_rows(
                [jobs[0]], config, {}, {}, queue_evidence=evidence
            )
            for name in (
                "queue_status_json",
                "queue_status_csv",
                "queue_events",
                "queue_event_sequence",
            ):
                write_json(Path(config["sources"][name]), {"name": name})
            write_json(
                Path(config["sources"]["queue_stage_stop"]),
                {
                    "schema": report.QUEUE_STAGE_STOP_SCHEMA,
                    "state": "STOPPED_SAME_ERROR_TYPE_THREE_CONSECUTIVE_BUILDINGS",
                },
            )
            write_json(
                Path(config["sources"]["queue_complete"]),
                {
                    "schema": report.QUEUE_COMPLETE_SCHEMA,
                    "state": "STOPPED_SAME_ERROR_TYPE_THREE_CONSECUTIVE_BUILDINGS",
                    "run_id": config["run_id"],
                    "git_head": config["provenance_contract"]["execution_head"],
                    "plan": report.receipt_binding(Path(config["sources"]["queue_plan"])),
                    "stage_stop": report.receipt_binding(
                        Path(config["sources"]["queue_stage_stop"])
                    ),
                    "stage_records": [
                        {
                            "entry": entries[0],
                            "status": "MEASURED",
                            "receipt": report.receipt_binding(smoke_path),
                        },
                        {
                            "entry": entries[1],
                            "status": "MEASURED",
                            "receipt": report.receipt_binding(reuse_path),
                        },
                    ],
                    "stage_entries_n": 22,
                    "unique_jobs_n": 21,
                    "status_json": report.receipt_binding(
                        Path(config["sources"]["queue_status_json"])
                    ),
                    "status_csv": report.receipt_binding(
                        Path(config["sources"]["queue_status_csv"])
                    ),
                    "events": report.receipt_binding(
                        Path(config["sources"]["queue_events"])
                    ),
                    "event_sequence": report.receipt_binding(
                        Path(config["sources"]["queue_event_sequence"])
                    ),
                },
            )
            stopped = report.load_queue_evidence(jobs, config)

        self.assertEqual(evidence["stage_entries_n"], 22)
        self.assertEqual(evidence["unique_jobs_n"], 21)
        self.assertEqual(evidence["terminal_unique_jobs_n"], 1)
        self.assertEqual(
            evidence["jobs"][jobs[0].key]["deduplicated_stage_entries_n"], 2
        )
        self.assertEqual(
            evidence["jobs"][jobs[0].key]["stage_record"]["stage_record_path"],
            report.repo_relative(reuse_path),
        )
        self.assertNotEqual(report.repo_relative(smoke_path), report.repo_relative(reuse_path))
        self.assertEqual(rows[0]["job_terminal_state"], "measured")
        self.assertEqual(rows[0]["queue_deduplicated_stage_entries_n"], 2)
        self.assertEqual(rows[0]["terminal_evidence"], report.repo_relative(reuse_path))
        self.assertEqual(
            stopped["complete"]["state"],
            "STOPPED_SAME_ERROR_TYPE_THREE_CONSECUTIVE_BUILDINGS",
        )

    def test_smoke_reuse_divergence_and_source_tamper_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config = queue_fixture_config(self.base_config, root)
            jobs, entries = self._plan(config)
            readout = root / "receipts/readout_complete.json"
            readout_payload = complete_payload()
            readout_payload["identity"] = {
                "building_id": jobs[0].building_id,
                "arm": jobs[0].arm,
                "replicate": jobs[0].run,
                "profile": "full",
            }
            write_json(readout, readout_payload)
            _smoke, reuse_path = self._smoke_and_reuse(config, entries, readout)
            reuse = json.loads(reuse_path.read_text(encoding="utf-8"))
            reuse["status"] = "SKIPPED"
            reuse["source_receipts"] = reuse["source_receipts"] * 3
            reuse["same_signature_attempts"] = 3
            reuse["error_type"] = "TestFailure"
            reuse["error_signature"] = "same"
            write_json(reuse_path, reuse)
            with self.assertRaisesRegex(
                report.ReportContractError, "duplicate smoke status diverged"
            ):
                report.load_queue_evidence(jobs, config)

            reuse["status"] = "MEASURED"
            reuse["source_receipts"] = reuse["source_receipts"][:1]
            reuse["same_signature_attempts"] = None
            reuse["error_type"] = None
            reuse["error_signature"] = None
            write_json(reuse_path, reuse)
            write_json(readout, {"schema": "tampered"})
            with self.assertRaisesRegex(report.ReportContractError, "SHA-256 drift"):
                report.load_queue_evidence(jobs, config)

    def test_archived_receipts_are_verified_and_incomplete_archive_stays_nonterminal(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config = queue_fixture_config(self.base_config, root)
            jobs, _entries = self._plan(config)
            job = jobs[0]
            archive_root = (
                Path(config["sources"]["queue_training_failure_archive"])
                / "by_building"
                / job.building_id
                / f"arm_{job.arm}"
                / job.run
            )
            attempt = archive_root / "attempt_001"
            terminal = attempt / "training_job/failed.json"
            write_json(terminal, {"status": "FAILED", "error_type": "RuntimeError"})
            terminal_record = report.receipt_binding(terminal)
            source_root = root / "canonical_training_job"
            original_terminal_record = {
                "path": str(source_root / "failed.json"),
                "sha256": terminal_record["sha256"],
                "bytes": terminal_record["bytes"],
            }
            ledger = attempt / "pre_move_ledger.json"
            write_json(
                ledger,
                {
                    "schema": report.QUEUE_ARCHIVE_LEDGER_SCHEMA,
                    "source_path": str(source_root),
                    "artifacts": [
                        {**original_terminal_record, "relative_to_root": "failed.json"}
                    ],
                    "artifact_count": 1,
                },
            )
            write_json(
                attempt / "archive_receipt.json",
                {
                    "schema": report.QUEUE_ARCHIVE_SCHEMA,
                    "state": "ARCHIVED",
                    "attempt": 1,
                    "identity": {
                        "building_id": job.building_id,
                        "arm": job.arm,
                        "replicate": job.run,
                        "profile": "full",
                    },
                    "source_path": str(source_root),
                    "destination_path": report.repo_relative(attempt),
                    "original_terminal_receipt": original_terminal_record,
                    "archived_terminal_receipt": terminal_record,
                    "pre_move_ledger": report.receipt_binding(ledger),
                    "move_verification": [terminal_record],
                    "artifact_count": 1,
                    "error_type": "RuntimeError",
                    "error_signature": "same",
                    "git_head": config["provenance_contract"]["execution_head"],
                    "append_only_archive": True,
                },
            )
            incomplete = archive_root / "attempt_002.incomplete/move_intent.json"
            write_json(incomplete, {"state": "MOVING"})
            evidence = report.load_queue_evidence(jobs, config)
            self.assertEqual(
                [row["archive_state"] for row in evidence["archive_rows"]],
                ["ARCHIVED", "INCOMPLETE"],
            )
            self.assertEqual(evidence["incomplete_archives_n"], 1)
            self.assertEqual(evidence["terminal_unique_jobs_n"], 0)

            write_json(terminal, {"status": "TAMPERED"})
            with self.assertRaisesRegex(report.ReportContractError, "SHA-256 drift"):
                report.load_queue_evidence(jobs, config)


class VisualAndPublicationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.config = report.load_config(verify_locked_files=False)

    def test_opacity_prefers_exact_building_scope(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            training = Path(temporary)
            path = training / "audit/seed_lineage.csv"
            fields = [
                "iteration",
                "scope",
                "gaussians_total",
                "seed_lineage_count",
                "opacity_median",
                "cum_prune_candidates",
                "cum_pruned",
                "cum_prune_seed_protected",
                "seed_protect_active",
            ]
            rows = []
            for scope, opacity in (("all_seed_lineage", 0.9), ("B1", 0.2)):
                rows.append(
                    {
                        "iteration": 15000,
                        "scope": scope,
                        "gaussians_total": 10,
                        "seed_lineage_count": 4,
                        "opacity_median": opacity,
                        "cum_prune_candidates": 3,
                        "cum_pruned": 2,
                        "cum_prune_seed_protected": 0,
                        "seed_protect_active": False,
                    }
                )
            report.write_csv(path, rows, fields)
            write_json(
                training / "audit/seed_initialization.json",
                {
                    "schema": "jointbuildgs.stage2.seed_initialization_audit.v1",
                    "status": "OBSERVED",
                    "iteration": 0,
                    "observation_phase": "initialization_pre_dynamics",
                    "gaussians_total": 10,
                    "seed_lineage_count": 4,
                    "requested_opacity": 0.1,
                    "opacity_median": 0.1,
                    "strategy_step_post_backward_calls": 0,
                    "optimizer_updates_completed": 0,
                    "intervention": False,
                    "scientific_verdict": None,
                },
            )
            job = report.Job(1, "B1", "Aprime", "r1", {})
            observed, state, scope = report.load_opacity_rows(job, training)
            self.assertEqual(state, "measured")
            self.assertIn("B1", scope)
            self.assertEqual(len(observed), 2)
            self.assertEqual(observed[0]["observation_phase"], "initialization_pre_dynamics")
            self.assertEqual(observed[0]["opacity_median"], 0.1)
            self.assertEqual(observed[1]["observation_phase"], "post_dynamics")
            self.assertEqual(observed[1]["opacity_median"], 0.2)
            self.assertFalse(observed[1]["seed_protect_active"])

    def test_opacity_figure_and_partial_panel_are_retained(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            opacity_path = root / "opacity.png"
            rows = [
                {
                    "iteration": 0,
                    "opacity_median": 0.1,
                    "observation_phase": "initialization_pre_dynamics",
                },
                {
                    "iteration": 0,
                    "opacity_median": 0.01,
                    "observation_phase": "post_dynamics",
                },
                {
                    "iteration": 15000,
                    "opacity_median": 0.2,
                    "observation_phase": "post_dynamics",
                },
                {
                    "iteration": 20000,
                    "opacity_median": 0.25,
                    "observation_phase": "post_dynamics",
                },
            ]
            report.plot_opacity(rows, opacity_path, self.config, "test")
            self.assertGreater(opacity_path.stat().st_size, 1000)

            config = copy.deepcopy(self.config)
            config["sources"]["run_root"] = str(root / "run")
            config["sources"]["preprocess_cache_namespace"] = "cache"
            config["locked_inputs"]["reference_gml"] = []
            job = report.Job(1, "B1", "Aprime", "r1", {})
            score = {
                "building_id": "B1",
                "arm": "Aprime",
                "run": "r1",
                "job_terminal_state": "pending",
                "primary_measurement_state": "missing",
                "tier": "failed8",
                "texture_stratum": "textured",
                "seed_filter_after_n": None,
                "mask_pixels_total": None,
            }
            runtime = {
                job.key: {
                    "job": job,
                    "training_dir": root / "training",
                    "readout_paths": {
                        "mesh": None,
                        "tsdf_npz": None,
                        "cityjson": None,
                        "alpha_npz": None,
                        "alpha_cityjson": None,
                    },
                }
            }
            opacity = report.generate_visuals([score], runtime, root / "snapshot", config)
            panel = root / "snapshot" / score["panel_path"]
            self.assertEqual(opacity, [])
            self.assertEqual(score["panel_state"], "partial")
            self.assertTrue(panel.is_file())
            self.assertGreater(panel.stat().st_size, 1000)
            self.assertFalse(any(score["panel_components_json"].values()))

    def test_cityjson_transform_is_applied(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "model.city.json"
            write_json(
                path,
                {
                    "type": "CityJSON",
                    "version": "1.1",
                    "transform": {"scale": [0.5, 0.5, 1], "translate": [10, 20, 30]},
                    "vertices": [[0, 0, 0], [2, 0, 0], [2, 2, 1]],
                    "CityObjects": {
                        "B1": {
                            "type": "Building",
                            "geometry": [{"type": "MultiSurface", "boundaries": [[[0, 1, 2]]]}],
                        }
                    },
                },
            )
            rings = report.cityjson_rings(path)
            self.assertEqual(len(rings), 1)
            np.testing.assert_allclose(rings[0][2], [11, 21, 31])

    def test_gml_streaming_cache_resolves_multiple_buildings_in_one_pass(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "reference.gml"
            path.write_text(
                """<?xml version="1.0"?>
<CityModel xmlns:gml="http://www.opengis.net/gml" xmlns:bldg="urn:bldg">
  <cityObjectMember><bldg:Building gml:id="B1"><gml:posList srsDimension="3">0 0 1 1 0 1 1 1 2</gml:posList></bldg:Building></cityObjectMember>
  <cityObjectMember><bldg:Building gml:id="B2"><gml:posList srsDimension="3">2 2 3 3 2 3 3 3 4</gml:posList></bldg:Building></cityObjectMember>
</CityModel>""",
                encoding="utf-8",
            )
            rings = report.gml_rings_by_building([path], ["B1", "B2"])
        self.assertEqual(len(rings["B1"]), 1)
        self.assertEqual(len(rings["B2"]), 1)
        np.testing.assert_allclose(rings["B2"][0][0], [2, 2, 3])

    def test_receipt_validates_manifest_hash(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            snapshot = Path(temporary)
            manifest = snapshot / self.config["outputs"]["manifest"]
            receipt = snapshot / self.config["outputs"]["receipt"]
            write_json(
                manifest,
                {
                    "schema": report.MANIFEST_SCHEMA,
                    "state": "PARTIAL",
                    "artifacts": [],
                },
            )
            write_json(
                receipt,
                {
                    "schema": report.RECEIPT_SCHEMA,
                    "input_fingerprint": "abc",
                    "state": "PARTIAL",
                    "manifest": {"sha256": report.sha256_file(manifest)},
                },
            )
            payload = report.validate_existing_snapshot(snapshot, self.config, "abc")
            self.assertEqual(payload["input_fingerprint"], "abc")
            with self.assertRaisesRegex(
                report.ReportContractError, "refuses cached PARTIAL"
            ):
                report.validate_existing_snapshot(
                    snapshot, self.config, "abc", require_terminal=True
                )
            write_json(manifest, {"schema": "tampered"})
            with self.assertRaises(report.ReportContractError):
                report.validate_existing_snapshot(snapshot, self.config, "abc")

    def test_t4_receipt_binds_sources_and_publishes_snapshot_local_bundle(self) -> None:
        original = report.load_t4_bundle(self.config)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config = copy.deepcopy(self.config)
            csv_path = root / "source/trajectory.csv"
            figure_path = root / "source/trajectory.png"
            csv_path.parent.mkdir(parents=True)
            csv_path.write_bytes(original["paths"]["csv"].read_bytes())
            figure_path.write_bytes(original["paths"]["figure"].read_bytes())
            receipt_payload = copy.deepcopy(original["payload"])
            receipt_payload["outputs"]["csv"] = {
                "path": str(csv_path),
                "sha256": report.sha256_file(csv_path),
            }
            receipt_payload["outputs"]["figure"] = {
                "path": str(figure_path),
                "sha256": report.sha256_file(figure_path),
            }
            receipt_path = root / "source/receipt.json"
            write_json(receipt_path, receipt_payload)
            config["t4_contract"] = {
                "receipt": {
                    "path": str(receipt_path),
                    "sha256": report.sha256_file(receipt_path),
                },
                "csv": {
                    "path": str(csv_path),
                    "sha256": report.sha256_file(csv_path),
                },
                "figure": {
                    "path": str(figure_path),
                    "sha256": report.sha256_file(figure_path),
                },
            }
            bundle = report.load_t4_bundle(config)
            manifest = report.publish_t4_bundle(root / "snapshot", config, bundle)
            links = report.t4_bundle_links(config)
            self.assertEqual(
                manifest["files"]["figure"]["snapshot_sha256"],
                config["t4_contract"]["figure"]["sha256"],
            )
            self.assertTrue((root / "snapshot" / links["receipt"]).is_file())
            self.assertTrue((root / "snapshot" / links["figure"]).is_file())

            figure_path.write_bytes(figure_path.read_bytes() + b"tamper")
            with self.assertRaisesRegex(report.ReportContractError, "T4 figure SHA-256 drift"):
                report.load_t4_bundle(config)

    def test_report_descendant_allowlist_rejects_nonreport_paths(self) -> None:
        allowlist = self.config["provenance_contract"][
            "report_implementation_files"
        ]
        self.assertEqual(
            report.validate_report_descendant_paths(allowlist[:2], allowlist),
            sorted(allowlist[:2]),
        )
        with self.assertRaisesRegex(
            report.ReportContractError, "contains non-report paths"
        ):
            report.validate_report_descendant_paths(
                [allowlist[0], "phases/p2-gsjso/scripts/producer.py"], allowlist
            )

    def test_source_fingerprint_tracks_missing_to_present_transition(self) -> None:
        missing = [{"role": "attempt", "path": "attempt.json", "state": "missing"}]
        present = [
            {
                "role": "attempt",
                "path": "attempt.json",
                "state": "present",
                "bytes": 12,
                "sha256": "a" * 64,
            }
        ]
        self.assertNotEqual(
            report.source_fingerprint(missing, self.config),
            report.source_fingerprint(present, self.config),
        )

    def test_verdict_phrases_are_rejected(self) -> None:
        report.assert_observational_language("측정 결과와 분모만 기록한다")
        with self.assertRaises(report.ReportContractError):
            report.assert_observational_language("결론: 따라서 성립")


if __name__ == "__main__":
    unittest.main()
