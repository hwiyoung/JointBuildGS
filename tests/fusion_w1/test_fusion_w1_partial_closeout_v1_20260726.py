#!/usr/bin/env python3
from __future__ import annotations

import copy
import csv
from datetime import datetime
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock


HERE = Path(__file__).resolve().parent
SOURCE = HERE / "fusion_w1_partial_closeout_v1_20260726.py"
SPEC = importlib.util.spec_from_file_location("fusion_w1_partial_closeout_tested", SOURCE)
assert SPEC is not None and SPEC.loader is not None
closeout = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(closeout)


def json_bytes(payload: object) -> bytes:
    return (
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def csv_bytes(fields: list[str], rows: list[dict[str, object]]) -> bytes:
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue().encode("utf-8")


class Fixture:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.config = copy.deepcopy(
            json.loads(
                (
                    HERE.parent
                    / "configs/fusion_w1_partial_closeout_v1_20260726.json"
                ).read_text(encoding="utf-8")
            )
        )
        self._build()

    def path(self, logical: str) -> Path:
        return self.root / logical

    def write(self, logical: str, payload: bytes) -> str:
        path = self.path(logical)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
        return hashlib.sha256(payload).hexdigest()

    def write_json(self, logical: str, payload: object) -> str:
        return self.write(logical, json_bytes(payload))

    def write_csv(
        self, logical: str, fields: list[str], rows: list[dict[str, object]]
    ) -> str:
        return self.write(logical, csv_bytes(fields, rows))

    def bind(self, key: str, digest: str) -> None:
        self.config["inputs"][key]["sha256"] = digest

    def _build(self) -> None:
        inputs = self.config["inputs"]
        r0 = {
            "schema": inputs["r0"]["schema"],
            "status": "PASSED",
            "execution_counters": {
                "learning_runs_started": 0,
                "readout_runs_started": 0,
                "roofer_runs_started": 0,
                "scoring_runs_started": 0,
            },
        }
        self.bind("r0", self.write_json(inputs["r0"]["path"], r0))
        diagnostic = {
            "population_n": 178,
            "n_threshold": 40,
            "correspondence_capable_n": 132,
            "matched_median_le_0p3_n": 132,
            "core_population_n": 28,
            "core_correspondence_capable_n": 24,
            "core_matched_median_le_0p3_n": 24,
            "building_balanced_median_of_matched_medians_m": 0.07236711717994171,
            "t5_building_balanced_median_r_total_m": 0.004186004000697177,
        }
        validation = {
            "maximum_pose_roundtrip_rotation_matrix_error": 1.6e-15,
            "maximum_pose_roundtrip_translation_error_m": 1.4e-14,
            "maximum_projection_invariance_error": 5.1e-13,
            "maximum_camera_center_error_m": 3.7e-13,
        }
        r1 = {
            "schema": inputs["r1"]["schema"],
            "status": "PASSED",
            "image_count": 937,
            "transform_application_count": 1,
            "source_sha256": {
                "cameras.bin": "c" * 64,
                "images.bin": "i" * 64,
                "points3D.bin": "p" * 64,
            },
            "derived_sha256": {
                "cameras.bin": "c" * 64,
                "images.bin": "d" * 64,
                "points3D.bin": "q" * 64,
            },
            "diagnostic_reproduction": diagnostic,
            "pose_validation": validation,
        }
        self.bind("r1", self.write_json(inputs["r1"]["path"], r1))
        r2 = {
            "schema": inputs["r2"]["schema"],
            "status": "PASS",
            "gate_slots": {
                "status": "PASS",
                "population_n": 178,
                "n_threshold": 40,
                "correspondence_capable_n": 132,
                "capable_matched_median_le_0p3_n": 132,
                "core_population_n": 28,
                "core_correspondence_capable_n": 24,
                "core_capable_matched_median_le_0p3_n": 24,
                "incapable_tier_counts": {
                    "surface": 2,
                    "height": 11,
                    "outline": 33,
                },
            },
            "qualitative_overlays": {
                "count": 28,
                "index_path": (
                    "phases/p2-gsjso/runs/fusion_w1/20260724_fusion_w1/"
                    "resume_v2/r2_overlay_index.csv"
                ),
            },
        }
        self.bind("r2", self.write_json(inputs["r2"]["path"], r2))

        target_fields = ["building_id", "cohort", "tier"]
        targets: list[dict[str, object]] = []
        tiers = ["surface"] * 114 + ["height"] * 23 + ["outline"] * 41
        for index in range(178):
            targets.append(
                {
                    "building_id": f"B{index + 1:03d}",
                    "cohort": "core" if index < 28 else "extension",
                    "tier": tiers[index],
                }
            )
        targets[0]["building_id"] = "DEBY_LOD2_42364609"
        self.bind(
            "targets",
            self.write_csv(inputs["targets"]["path"], target_fields, targets),
        )
        target_manifest = {
            "schema": inputs["targets_manifest"]["schema"],
            "status": inputs["targets_manifest"]["status"],
            "queue_status": "provisional_gs4_overlap_unresolved",
            "core_priority_complete": False,
        }
        self.bind(
            "targets_manifest",
            self.write_json(inputs["targets_manifest"]["path"], target_manifest),
        )
        self.bind(
            "alignment_source",
            self.write_csv(
                inputs["alignment_source"]["path"],
                ["building_id", "candidate_median_m"],
                [
                    {"building_id": f"B{index:03d}", "candidate_median_m": "0.1"}
                    for index in range(178)
                ],
            ),
        )
        building = {
            "building_id": "DEBY_LOD2_42364609",
            "seed_points_n": 7993,
            "views_n": 30,
            "class2_n": 7644,
            "class6_n": 349,
        }
        preprocess = {
            "schema": inputs["preprocess_manifest"]["schema"],
            "status": "PARTIAL",
            "completed_buildings_n": 1,
            "core_completed_n": 1,
            "core_expected_n": 28,
            "buildings": [building],
        }
        self.bind(
            "preprocess_manifest",
            self.write_json(inputs["preprocess_manifest"]["path"], preprocess),
        )
        seed_row = {
            "building_id": "DEBY_LOD2_42364609",
            "views_n": 30,
            "output_points_n": 7993,
            "class2_n": 7644,
            "class6_n": 349,
        }
        self.bind(
            "seed_stats",
            self.write_csv(
                inputs["seed_stats"]["path"], list(seed_row), [seed_row]
            ),
        )
        p0_row = {
            "building_id": "DEBY_LOD2_42364609",
            "plane_f1": "1.000000000",
            "roof_rms_m": "0.089892857",
            "roof_completeness": "0.999715443",
            "face_count_ratio": "1.000000000",
            "assembly_lod2_matches_p0_refl": "true",
            "delta_roof_rms_vs_p0_refl_m": "-0.000623414",
            "delta_roof_completeness_vs_p0_refl": "0.000012621",
            "delta_face_count_ratio_vs_p0_refl": "0.000000000",
            "status": "MEASURED",
        }
        p0_score_sha = self.write_csv(
            inputs["p0prime_scores"]["path"], list(p0_row), [p0_row]
        )
        self.bind("p0prime_scores", p0_score_sha)
        complete_logical = (
            "phases/p2-gsjso/runs/fusion_w1/20260724_fusion_w1/p0prime/"
            "by_building/DEBY_LOD2_42364609/complete.json"
        )
        complete_sha = self.write_json(
            complete_logical,
            {
                "schema": "jointbuildgs.fusion_w1.seed_p0prime.building_receipt.v1",
                "state": "COMPLETE",
                "building_id": "DEBY_LOD2_42364609",
            },
        )
        p0 = {
            "schema": inputs["p0prime_manifest"]["schema"],
            "state": "PARTIAL",
            "learning_runs_started": 0,
            "manifest_written_last": True,
            "population": {
                "completed_count": 1,
                "target_count": 178,
                "assembly_lod2_success_count": 1,
                "val3dity_valid_count": 1,
            },
            "scores_csv": {
                "path": inputs["p0prime_scores"]["path"],
                "sha256": p0_score_sha,
                "row_count": 1,
            },
            "completion_records": [
                {
                    "complete_receipt": complete_logical,
                    "complete_receipt_sha256": complete_sha,
                }
            ],
        }
        self.bind(
            "p0prime_manifest",
            self.write_json(inputs["p0prime_manifest"]["path"], p0),
        )
        p0_driver = b"def refuse_after_final_manifest():\n    pass\n"
        self.bind(
            "p0prime_driver",
            self.write(inputs["p0prime_driver"]["path"], p0_driver),
        )
        self.bind(
            "scores",
            self.write_csv(inputs["scores"]["path"], ["status"], []),
        )
        summary_rows = [
            {"tier": tier, "arm": arm, "run": run, "status": "NOT_MEASURED"}
            for tier in closeout.TIERS
            for arm in closeout.ARMS
            for run in closeout.RUNS
        ]
        self.bind(
            "summary",
            self.write_csv(
                inputs["summary"]["path"],
                ["tier", "arm", "run", "status"],
                summary_rows,
            ),
        )
        training_source = (
            "LOSS_SHARE_FIELDS = " + repr(closeout.LOSS_SHARE_FIELDS) + "\n"
        ).encode("utf-8")
        self.bind(
            "training_driver",
            self.write(inputs["training_driver"]["path"], training_source),
        )
        training_config = {
            "schema": "jointbuildgs.fusion_w1.training_driver.config.v1",
            "launch_contract": {"cutoff_kst": self.config["cutoff_kst"]},
        }
        self.bind(
            "training_config",
            self.write_json(inputs["training_config"]["path"], training_config),
        )
        stale = {
            "schema": inputs["stale_manifest"]["schema"],
            "run_status": "BLOCKED",
        }
        self.bind(
            "stale_manifest",
            self.write_json(inputs["stale_manifest"]["path"], stale),
        )
        issue_text = "# issues\n\n" + "\n\n".join(
            f"## {issue} — fixture" for issue in inputs["issues"]["required_ids"]
        ) + "\n"
        self.write(inputs["issues"]["path"], issue_text.encode("utf-8"))
        self.path(self.config["counter_contract"]["training_root"]).mkdir(
            parents=True, exist_ok=True
        )
        self.path(self.config["counter_contract"]["readout_root"]).mkdir(
            parents=True, exist_ok=True
        )
        panel_spec = inputs["p0prime_panel"]
        panel_payload = b"fixture-png"
        panel_sha = self.write(panel_spec["path"], panel_payload)
        self.write_json(
            panel_spec["receipt"],
            {
                "schema": "jointbuildgs.fusion_w1.seed_p0prime.panel_receipt.v1",
                "state": "COMPLETE",
                "panel": {"path": panel_spec["path"], "sha256": panel_sha},
            },
        )


class PartialCloseoutTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.fixture = Fixture(self.root)
        self.now = datetime.fromisoformat("2026-07-26T07:00:00+09:00")
        self.git = {
            "branch": "exp/fusion-w1",
            "head": "f" * 40,
            "required_ancestor": "a" * 40,
            "required_ancestor_of_head": True,
            "implementation_files_match_head": True,
            "tracked_worktree_clean_before_closeout": True,
            "status_porcelain_sha256": "0" * 64,
            "status_porcelain_lines_n": 0,
        }

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_config_locks_fixed_output_names(self) -> None:
        path = self.root / "config.json"
        path.write_bytes(json_bytes(self.fixture.config))
        loaded = closeout.load_config(path)
        self.assertEqual(loaded["outputs"]["manifest"].split("/")[-1], "w1_manifest.json")
        loaded["outputs"]["loss_shares"] = "wrong.csv"
        path.write_bytes(json_bytes(loaded))
        with self.assertRaises(closeout.CloseoutError):
            closeout.load_config(path)

    def test_real_training_driver_exports_locked_loss_header(self) -> None:
        config = json.loads(
            (
                HERE.parent
                / "configs/fusion_w1_partial_closeout_v1_20260726.json"
            ).read_text(encoding="utf-8")
        )
        self.assertEqual(
            closeout.load_loss_share_fields(closeout.REPO, config),
            closeout.LOSS_SHARE_FIELDS,
        )

    def test_current_locked_artifact_snapshot_is_readable(self) -> None:
        config = json.loads(
            (
                HERE.parent
                / "configs/fusion_w1_partial_closeout_v1_20260726.json"
            ).read_text(encoding="utf-8")
        )
        snapshot = closeout.collect_inputs(closeout.REPO, config)
        self.assertEqual(snapshot["panel"]["status"], "PRESENT")
        self.assertEqual(
            snapshot["panel"]["sha256"],
            "973aa51a327615e5a2888772914ae63a14345390f8e8f3195e8c1ac18bdd5c7c",
        )
        self.assertEqual(snapshot["counters"]["learning_runs_started"], 0)
        self.assertEqual(snapshot["summary_not_measured_rows_n"], 12)

    def test_collect_inputs_accepts_zero_stage_fixture(self) -> None:
        snapshot = closeout.collect_inputs(self.root, self.fixture.config)
        self.assertEqual(snapshot["counters"]["learning_runs_started"], 0)
        self.assertEqual(snapshot["summary_not_measured_rows_n"], 12)
        self.assertEqual(snapshot["panel"]["status"], "PRESENT")

    def test_training_started_receipt_fails_closed(self) -> None:
        receipt = (
            self.fixture.path(self.fixture.config["counter_contract"]["training_root"])
            / "by_building/B001/arm_A/r1/started.json"
        )
        receipt.parent.mkdir(parents=True, exist_ok=True)
        receipt.write_text("{}\n", encoding="utf-8")
        with self.assertRaisesRegex(closeout.CloseoutError, "training receipts"):
            closeout.zero_counter_snapshot(self.root, self.fixture.config)

    def test_measured_summary_row_fails_closed(self) -> None:
        spec = self.fixture.config["inputs"]["summary"]
        path = self.fixture.path(spec["path"])
        fields, rows = closeout.read_csv(path)
        rows[0]["status"] = "MEASURED"
        payload = csv_bytes(fields, rows)
        path.write_bytes(payload)
        spec["sha256"] = hashlib.sha256(payload).hexdigest()
        with self.assertRaisesRegex(closeout.CloseoutError, "measured row"):
            closeout.collect_inputs(self.root, self.fixture.config)

    def test_panel_requires_exact_pair_and_receipt_binding(self) -> None:
        spec = self.fixture.config["inputs"]["p0prime_panel"]
        panel = self.fixture.path(spec["path"])
        receipt = self.fixture.path(spec["receipt"])
        panel.unlink()
        receipt.unlink()
        with self.assertRaisesRegex(closeout.CloseoutError, "pair is missing"):
            closeout.collect_panel(self.root, self.fixture.config)
        panel.write_bytes(b"png")
        with self.assertRaisesRegex(closeout.CloseoutError, "asymmetric"):
            closeout.collect_panel(self.root, self.fixture.config)
        panel_sha = hashlib.sha256(b"png").hexdigest()
        self.fixture.write_json(
            spec["receipt"],
            {
                "schema": "panel.receipt.v1",
                "state": "COMPLETE",
                "panel": {"path": spec["path"], "sha256": panel_sha},
            },
        )
        result = closeout.collect_panel(self.root, self.fixture.config)
        self.assertEqual(result["status"], "PRESENT")
        self.assertEqual(result["sha256"], panel_sha)

    def test_existing_different_fixed_output_is_not_overwritten(self) -> None:
        path = self.root / "fixed.csv"
        path.write_bytes(b"unexpected\n")
        with self.assertRaisesRegex(closeout.CloseoutError, "differs"):
            closeout.publish_exact_or_accept(path, b"required\n", "fixed")
        self.assertEqual(path.read_bytes(), b"unexpected\n")

    def test_check_is_read_only(self) -> None:
        before = sorted(
            (path.relative_to(self.root).as_posix(), path.read_bytes())
            for path in self.root.rglob("*")
            if path.is_file()
        )
        with mock.patch.object(
            closeout, "verify_git_contract", return_value=self.git
        ):
            result = closeout.check(
                self.fixture.config, repo=self.root, now=self.now
            )
        after = sorted(
            (path.relative_to(self.root).as_posix(), path.read_bytes())
            for path in self.root.rglob("*")
            if path.is_file()
        )
        self.assertEqual(before, after)
        self.assertFalse(result["outputs_written_by_check"])

    def test_publish_creates_exact_csv_report_and_manifest_last(self) -> None:
        issues = self.fixture.path(self.fixture.config["inputs"]["issues"]["path"])
        issues_sha = closeout.sha256_file(issues)
        source = self.fixture.path(
            self.fixture.config["inputs"]["alignment_source"]["path"]
        )
        with mock.patch.object(
            closeout, "verify_git_contract", return_value=self.git
        ):
            result = closeout.publish(
                self.fixture.config, repo=self.root, now=self.now
            )
        align = self.fixture.path(self.fixture.config["outputs"]["align_residuals"])
        loss = self.fixture.path(self.fixture.config["outputs"]["loss_shares"])
        report = self.fixture.path(self.fixture.config["outputs"]["report"])
        manifest_path = self.fixture.path(self.fixture.config["outputs"]["manifest"])
        self.assertEqual(align.read_bytes(), source.read_bytes())
        fields, loss_rows = closeout.read_csv(loss)
        self.assertEqual(tuple(fields), closeout.LOSS_SHARE_FIELDS)
        self.assertEqual(loss_rows, [])
        manifest = closeout.load_json(manifest_path)
        self.assertEqual(manifest["schema"], closeout.MANIFEST_SCHEMA)
        self.assertEqual(manifest["state"], "PARTIAL")
        self.assertEqual(manifest["judgment_scales"][0]["status"], "NOT_MEASURED")
        self.assertEqual(
            manifest["training_throughput"]["status"], "NOT_MEASURED"
        )
        self.assertNotIn("cumulative_counters", manifest)
        self.assertEqual(
            manifest["postlearning_fusion_counters"]["roofer_runs_started"], 0
        )
        self.assertEqual(
            manifest["stage_inventory"]["p0prime"]["roofer_completed_n"], 1
        )
        self.assertEqual(manifest["report"]["sha256"], closeout.sha256_file(report))
        report_text = report.read_text(encoding="utf-8")
        self.assertIn("눈금 1–4", report_text)
        self.assertIn("`NOT_MEASURED`", report_text)
        self.assertIn("[w1_summary.csv](w1_summary.csv)", report_text)
        self.assertIn("resume_v2/r2_overlay_index.csv", report_text)
        self.assertIn("w1_panels/DEBY_LOD2_42364609__p0prime.png", report_text)
        self.assertIn(
            "w1_panels/DEBY_LOD2_42364609__p0prime.receipt.json",
            report_text,
        )
        self.assertIn("RMS delta `-0.000623414 m`", report_text)
        self.assertIn("new approved namespace or reopen contract", report_text)
        self.assertIn("30k 학습 1런 처리율", report_text)
        self.assertEqual(closeout.sha256_file(issues), issues_sha)
        self.assertFalse(result["stage_commands_invoked"])

    def test_before_cutoff_is_rejected(self) -> None:
        with self.assertRaisesRegex(closeout.CloseoutError, "before cutoff"):
            closeout.verify_cutoff(
                self.fixture.config,
                datetime.fromisoformat("2026-07-26T06:29:59+09:00"),
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
