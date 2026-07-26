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


class ContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.config = report.load_config()
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

    def test_docker_wrapper_is_nonnetworked_and_nonroot(self) -> None:
        wrapper = (
            REPO / "phases/p2-gsjso/scripts/run_fusion_w1_aprime_report_20260726.sh"
        ).read_text(encoding="utf-8")
        self.assertIn("--network=none", wrapper)
        self.assertIn('--user "$(id -u):$(id -g)"', wrapper)
        self.assertIn("--pull=never", wrapper)
        self.assertIn("EXPECTED_IMAGE_ID=", wrapper)
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
        cls.config = report.load_config()

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


class VisualAndPublicationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.config = report.load_config()

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
            write_json(manifest, {"schema": report.MANIFEST_SCHEMA})
            write_json(
                receipt,
                {
                    "schema": report.RECEIPT_SCHEMA,
                    "input_fingerprint": "abc",
                    "manifest": {"sha256": report.sha256_file(manifest)},
                },
            )
            payload = report.validate_existing_snapshot(snapshot, self.config, "abc")
            self.assertEqual(payload["input_fingerprint"], "abc")
            write_json(manifest, {"schema": "tampered"})
            with self.assertRaises(report.ReportContractError):
                report.validate_existing_snapshot(snapshot, self.config, "abc")

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
