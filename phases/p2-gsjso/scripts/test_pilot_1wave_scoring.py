#!/usr/bin/env python3
"""Docker synthetic tests for the P1W expanded-30 scoring adapter."""
from __future__ import annotations

import csv
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
from pyproj import CRS

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import pilot_1wave_scoring as score


class PilotOneWaveScoringTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.lock = score.load_pilot_lock()

    def temporary_directory(self) -> tempfile.TemporaryDirectory[str]:
        return tempfile.TemporaryDirectory(prefix="p1w_score_")

    def full_state_fixture(
        self,
        root: Path,
        condition: str,
        seed: int,
        *,
        completed_steps: int,
    ) -> Path:
        root.mkdir(parents=True, exist_ok=True)
        config: dict[str, object] = {
            "max_iter": score.MAX_ITER,
            "pilot_arm": score.CONDITION_PILOT_ARM[condition],
            "seed": seed,
        }
        if condition in {"04a", "04b"}:
            plane = root / "plane_mask_manifest.json"
            plane.write_text(
                json.dumps({"source": score.CONDITION_SEGMENTATION_SOURCE[condition]}) + "\n",
                encoding="utf-8",
            )
            config["plane_region_mask_manifest"] = str(plane)
        config_path = root / "train.json"
        config_path.write_text(json.dumps(config) + "\n", encoding="utf-8")
        checkpoint = root / f"ckpt_{completed_steps:06d}.pt"
        checkpoint.write_bytes(f"checkpoint-{condition}-{seed}-{completed_steps}".encode())
        complete = completed_steps == score.MAX_ITER
        manifest = root / "full_state_manifest.json"
        payload: dict[str, object] = {
            "schema": score.FULL_STATE_MANIFEST_SCHEMA,
            "config_path": str(config_path),
            "config_file_sha256": score.sha256_file(config_path),
            "max_iter": score.MAX_ITER,
            "checkpoint_steps": list(score.FULL_CHECKPOINT_STEPS),
            "learning_runs_started": 1,
            "latest_full_checkpoint": {
                "path": str(checkpoint),
                "sha256": score.sha256_file(checkpoint),
                "completed_steps": completed_steps,
            },
            "last_completed_steps": completed_steps,
            "process_completed": complete,
        }
        if complete:
            payload["process_completed_steps"] = score.MAX_ITER
        manifest.write_text(json.dumps(payload) + "\n", encoding="utf-8")
        return manifest

    def roofer_marker_fixture(
        self,
        root: Path,
        condition: str,
        seed: int,
        cityjson: Path,
    ) -> Path:
        root.mkdir(parents=True, exist_ok=True)
        pointcloud = root / "classified.laz"
        pointcloud.write_bytes(b"synthetic classified pointcloud")
        footprints = root / "locked_30.geojson"
        footprints.write_text("{}\n", encoding="utf-8")
        marker = root / "roofer_invocation.json"
        marker.write_text(
            json.dumps(
                {
                    "schema": score.ROOFER_MARKER_SCHEMA,
                    "condition_id": condition,
                    "seed": seed,
                    "state": "complete",
                    "roofer_invocation_count": 1,
                    "pointcloud_path": str(pointcloud),
                    "pointcloud_sha256": score.sha256_file(pointcloud),
                    "footprints": {
                        "path": str(footprints),
                        "sha256": score.sha256_file(footprints),
                        "feature_count": 30,
                    },
                    "roofer_image": score.ROOFER_IMAGE,
                    "roofer_parameters": score.ROOFER_PARAMETERS,
                    "selection_sha256": self.lock.selection_sha256,
                    "cityjson_path": str(cityjson),
                    "cityjson_sha256": score.sha256_file(cityjson),
                }
            )
            + "\n",
            encoding="utf-8",
        )
        return marker

    def bound_score_fixture(
        self,
        root: Path,
        condition: str,
        seed: int,
        *,
        completed_steps: int,
        z_offset: float = 0.2,
    ) -> tuple[list[dict[str, object]], Path, list[tuple[Path, Path]]]:
        root.mkdir(parents=True, exist_ok=True)
        cityjson, _unused_report, references = self.synthetic_fixture(root, z_offset=z_offset)
        full_state = self.full_state_fixture(
            root / "train", condition, seed, completed_steps=completed_steps
        )
        roofer_marker = self.roofer_marker_fixture(
            root / "roofer", condition, seed, cityjson
        )
        calls: list[tuple[Path, Path]] = []

        def fake_val3dity(path: Path, report: Path) -> tuple[dict[str, bool], int, str]:
            calls.append((path, report))
            report.write_text(
                json.dumps(
                    {
                        "features": [
                            {"id": building_id, "validity": True}
                            for building_id in self.lock.ids
                        ]
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            return {building_id: True for building_id in self.lock.ids}, 0, "val3dity 2.6.0"

        output = root / "run_scores.csv"
        marker = root / "score_invocation.json"
        rows, _state = score.score_bound_run_once(
            condition,
            seed,
            cityjson,
            roofer_marker,
            full_state,
            output,
            marker,
            self.lock,
            guard_status=(
                "not_triggered"
                if completed_steps == score.MAX_ITER
                else "triggered_checkpoint_stop"
            ),
            guard_reason=("" if completed_steps == score.MAX_ITER else "9h guard"),
            references=references,
            val3dity_runner=fake_val3dity,
        )
        return rows, marker, calls

    def test_strict_lock_binds_full_files_ids_and_bbox(self) -> None:
        lock = self.lock
        self.assertEqual(len(lock.ids), 30)
        self.assertEqual(lock.selection_sha256, score.SELECTION_SHA256)
        self.assertEqual(lock.ordered_ids_sha256, score.ORDERED_IDS_SHA256)
        self.assertEqual(lock.scoring_bbox, score.SCORING_BBOX)
        self.assertEqual(sum(item.is_small_lt50m2 for item in lock.buildings), 5)
        with self.temporary_directory() as raw:
            root = Path(raw)
            pilot_set = root / "pilot.csv"
            manifest = root / "manifest.json"
            shutil.copyfile(score.PILOT_SET, pilot_set)
            shutil.copyfile(score.PILOT_MANIFEST, manifest)
            with pilot_set.open("a", encoding="utf-8") as handle:
                handle.write("\n")
            with self.assertRaisesRegex(RuntimeError, "pilot-set SHA256"):
                score.load_pilot_lock(pilot_set, manifest)

    def test_empty_output_headers_and_denominators_are_fixed(self) -> None:
        with self.temporary_directory() as raw:
            root = Path(raw)
            manifest = score.initialize_output_schemas(root, self.lock)
            expected = {
                "scores": score.SCORE_FIELDS,
                "summary": score.SUMMARY_FIELDS,
                "seg_gap": score.SEG_GAP_FIELDS,
                "loss_shares": score.LOSS_SHARE_FIELDS,
                "winner": score.WINNER_FIELDS,
            }
            for key, fields in expected.items():
                path = root / score.OUTPUT_NAMES[key]
                with path.open(newline="", encoding="utf-8") as handle:
                    reader = csv.reader(handle)
                    self.assertEqual(tuple(next(reader)), tuple(fields))
                    self.assertEqual(list(reader), [])
            self.assertEqual(manifest["metrics"]["completeness_thresholds"], [0.8, 0.9, 0.95])
            denominators = manifest["metrics"]["summary_denominators"]
            self.assertEqual(denominators["all"], 30)
            self.assertEqual(denominators["small_lt50m2"], 5)
            self.assertEqual(denominators["non_small_ge50m2"], 25)
            self.assertEqual(denominators["observation"], {"low": 8, "mid": 10, "high": 12})
            self.assertEqual(denominators["size_area"], {"low": 8, "mid": 12, "high": 10})
            self.assertEqual(manifest["conditions"]["honest"], ["01", "02", "03", "04a"])
            self.assertEqual(manifest["conditions"]["seg_upperbound"], "04b")
            self.assertEqual(manifest["controls"]["cheap_refine_mls_default"]["selected_population_missing_count"], 20)
            self.assertEqual(len(manifest["run_states"]), 10)
            self.assertTrue(all(row["status"] == "not_scored" for row in manifest["run_states"].values()))
            self.assertIsNone(manifest["interpretation_or_verdict"])
            with self.assertRaisesRegex(RuntimeError, "nonempty output"):
                score.initialize_output_schemas(root, self.lock)

    def test_controls_keep_expanded_missing_values_empty(self) -> None:
        rows = score.load_control_rows(self.lock)
        self.assertEqual(len(rows), 90)
        cheap = [row for row in rows if row["source_id"] == "cheap_refine_mls_default"]
        self.assertEqual(len(cheap), 30)
        available = [row for row in cheap if row["metric_available"]]
        missing = [row for row in cheap if not row["metric_available"]]
        self.assertEqual((len(available), len(missing)), (10, 20))
        for row in missing:
            self.assertIsNone(row["roof_rms_m"])
            self.assertIsNone(row["roof_completeness"])
            self.assertIsNone(row["face_count_ratio"])
        summaries = score.summarize_scores(rows)
        cheap_all = next(
            row
            for row in summaries
            if row["source_id"] == "cheap_refine_mls_default" and row["stratum"] == "all"
        )
        self.assertEqual(cheap_all["population_count"], 30)
        self.assertEqual(cheap_all["metric_available_count"], 10)
        self.assertEqual(cheap_all["completeness_measurable_count"], 10)
        self.assertEqual(cheap_all["completeness_ge_0p9_rate"], cheap_all["completeness_ge_0p9_count"] / 10)

    def synthetic_fixture(self, root: Path, z_offset: float = 0.2) -> tuple[Path, Path, dict[str, list[object]]]:
        vertices: list[list[float]] = []
        objects: dict[str, object] = {}
        references: dict[str, list[object]] = {}
        for index, building_id in enumerate(self.lock.ids):
            x0 = float(index * 3)
            ring_reference = np.asarray(
                [
                    [x0, 0.0, 10.0],
                    [x0 + 1.0, 0.0, 10.0],
                    [x0 + 1.0, 1.0, 10.0],
                    [x0, 1.0, 10.0],
                    [x0, 0.0, 10.0],
                ],
                dtype=np.float64,
            )
            surface = score.get_metric_module().roof_surface_from_rings(
                f"ref_{index}", [ring_reference]
            )
            assert surface is not None
            references[building_id] = [surface]
            start = len(vertices)
            vertices.extend(
                [
                    [x0, 0.0, 10.0 + z_offset],
                    [x0 + 1.0, 0.0, 10.0 + z_offset],
                    [x0 + 1.0, 1.0, 10.0 + z_offset],
                    [x0, 1.0, 10.0 + z_offset],
                ]
            )
            objects[building_id] = {
                "type": "Building",
                "geometry": [
                    {
                        "type": "MultiSurface",
                        "lod": "2.2",
                        "boundaries": [[[start, start + 1, start + 2, start + 3, start]]],
                        "semantics": {"surfaces": [{"type": "RoofSurface"}], "values": [0]},
                    }
                ],
            }
        cityjson = root / "synthetic.city.json"
        cityjson.write_text(
            json.dumps(
                {
                    "type": "CityJSON",
                    "version": "1.1",
                    "metadata": {"referenceSystem": "https://www.opengis.net/def/crs/EPSG/0/25832"},
                    "CityObjects": objects,
                    "vertices": vertices,
                },
                separators=(",", ":"),
            )
            + "\n",
            encoding="utf-8",
        )
        report = root / "synthetic.val3dity.json"
        report.write_text(
            json.dumps(
                {
                    "features": [
                        {"id": building_id, "validity": True}
                        for building_id in self.lock.ids
                    ]
                },
                separators=(",", ":"),
            )
            + "\n",
            encoding="utf-8",
        )
        return cityjson, report, references

    def test_synthetic_cityjson_scores_exact_six_metrics(self) -> None:
        with self.temporary_directory() as raw:
            root = Path(raw)
            cityjson, report, references = self.synthetic_fixture(root)
            rows = score.score_cityjson(
                "04a",
                1001,
                cityjson,
                report,
                self.lock,
                references=references,
            )
            self.assertEqual(len(rows), 30)
            for row in rows:
                self.assertTrue(row["has_lod22"])
                self.assertTrue(row["val3dity_valid"])
                self.assertEqual(row["roof_face_count_model"], 1)
                self.assertEqual(row["roof_face_count_ref"], 1)
                self.assertAlmostEqual(row["face_count_ratio"], 1.0, places=12)
                self.assertAlmostEqual(row["roof_rms_m"], 0.2, places=10)
                self.assertAlmostEqual(row["roof_hausdorff_m"], 0.2, places=10)
                self.assertAlmostEqual(row["roof_completeness"], 1.0, places=12)
                self.assertTrue(row["completeness_ge_0p8"])
                self.assertTrue(row["completeness_ge_0p9"])
                self.assertTrue(row["completeness_ge_0p95"])

    def test_lod11_fallback_is_preserved_and_not_counted_as_lod2(self) -> None:
        with self.temporary_directory() as raw:
            root = Path(raw)
            cityjson, report, references = self.synthetic_fixture(root)
            payload = json.loads(cityjson.read_text(encoding="utf-8"))
            fallback_id = self.lock.ids[0]
            payload["CityObjects"][fallback_id]["attributes"] = {
                "rf_success": True,
                "rf_extrusion_mode": "lod11_fallback",
            }
            cityjson.write_text(json.dumps(payload) + "\n", encoding="utf-8")
            rows = score.score_cityjson(
                "01", 1001, cityjson, report, self.lock, references=references
            )
            fallback = next(row for row in rows if row["building_id"] == fallback_id)
            self.assertTrue(fallback["geometry_has_lod22"])
            self.assertTrue(fallback["lod1_fallback"])
            self.assertEqual(fallback["rf_extrusion_mode"], "lod11_fallback")
            self.assertFalse(fallback["has_lod22"])
            self.assertEqual(fallback["roof_face_count_model"], 1)

    def test_5k_full_state_is_reportable_partial_but_winner_ineligible(self) -> None:
        with self.temporary_directory() as raw:
            root = Path(raw)
            partial_manifest = self.full_state_fixture(
                root / "partial", "01", 1001, completed_steps=5000
            )
            partial = score.validate_full_state_manifest(
                "01",
                1001,
                partial_manifest,
                guard_status="triggered_checkpoint_stop",
                guard_reason="9h guard",
            )
            self.assertTrue(partial["partial"])
            self.assertFalse(partial["eligible_20k_full_state"])
            self.assertEqual(partial["latest_full_checkpoint_steps"], 5000)

            summaries: list[dict[str, object]] = []
            for condition in score.HONEST_CONDITIONS:
                for seed in score.EXPECTED_SEEDS:
                    summaries.append(
                        {
                            "source_role": "honest",
                            "stratum": "all",
                            "condition_id": condition,
                            "seed": seed,
                            "rms_measurable_count": 30,
                            "roof_rms_median_m": 0.2,
                            "rule_abcd": True,
                            "run_eligible_20k_full_state": not (
                                condition == "01" and seed == 1001
                            ),
                        }
                    )
            winner = score.build_winner_rows(summaries)
            condition_01 = next(row for row in winner if row["condition_id"] == "01")
            self.assertEqual(condition_01["complete_seed_count"], 2)
            self.assertEqual(condition_01["eligible_20k_seed_count"], 1)
            self.assertFalse(condition_01["eligible_two_seed_rule"])

    def test_bound_score_marker_binds_one_val3dity_report_and_all_hashes(self) -> None:
        with self.temporary_directory() as raw:
            root = Path(raw)
            rows, marker, calls = self.bound_score_fixture(
                root, "04a", 1001, completed_steps=20000
            )
            self.assertEqual(len(rows), 30)
            self.assertEqual(len(calls), 1)
            state = score.validate_score_marker("04a", 1001, marker)
            self.assertEqual(state["val3dity_invocation_count"], 1)
            self.assertEqual(state["val3dity_version"], score.VAL3DITY_VERSION)
            self.assertEqual(state["score_output_row_count"], 30)
            report = Path(state["val3dity_report"])
            if not report.is_absolute():
                report = score.REPO / report
            report.write_text("{}\n", encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "val3dity report SHA256"):
                score.validate_score_marker("04a", 1001, marker)

    def test_face_rule_uses_abs_of_median_ratio(self) -> None:
        with self.temporary_directory() as raw:
            root = Path(raw)
            cityjson, report, references = self.synthetic_fixture(root, z_offset=0.0)
            candidate = score.score_cityjson(
                "01", 1001, cityjson, report, self.lock, references=references
            )
            controls = score.load_control_rows(self.lock)
            candidate = score.attach_dense_controls(candidate, controls)
            for index, row in enumerate(candidate):
                ratio = 0.5 if index < 15 else 1.5
                row["face_count_ratio"] = ratio
                row["face_count_ratio_abs_error"] = abs(ratio - 1.0)
            summary = next(
                row
                for row in score.summarize_scores([*controls, *candidate])
                if row["source_id"] == "01_seed1001" and row["stratum"] == "all"
            )
            self.assertAlmostEqual(summary["face_count_ratio_median"], 1.0)
            self.assertAlmostEqual(summary["face_count_ratio_target_abs_deviation"], 0.0)

    def test_summary_threshold_denominators_and_small_double_report(self) -> None:
        with self.temporary_directory() as raw:
            root = Path(raw)
            cityjson, report, references = self.synthetic_fixture(root, z_offset=0.0)
            candidate = score.score_cityjson("01", 1001, cityjson, report, self.lock, references=references)
            controls = score.load_control_rows(self.lock)
            candidate = score.attach_dense_controls(candidate, controls)
            summaries = score.summarize_scores([*controls, *candidate])
            source = [row for row in summaries if row["source_id"] == "01_seed1001"]
            self.assertTrue(
                {"all", "small_lt50m2", "non_small_ge50m2"}.issubset(
                    {row["stratum"] for row in source}
                )
            )
            by_stratum = {row["stratum"]: row for row in source}
            self.assertEqual(by_stratum["all"]["population_count"], 30)
            self.assertEqual(by_stratum["small_lt50m2"]["population_count"], 5)
            self.assertEqual(by_stratum["non_small_ge50m2"]["population_count"], 25)
            self.assertTrue(by_stratum["all"]["rule_a_rms_below_dense_bar"])
            for row in source:
                self.assertEqual(row["completeness_ge_0p8_count"], row["population_count"])
                self.assertEqual(row["completeness_ge_0p9_count"], row["population_count"])
                self.assertEqual(row["completeness_ge_0p95_count"], row["population_count"])

    def test_numeric_writer_preserves_fixed_schemas_on_partial_jobs(self) -> None:
        with self.temporary_directory() as raw:
            root = Path(raw)
            candidate, _marker, calls = self.bound_score_fixture(
                root / "run", "01", 1001, completed_steps=5000
            )
            aggregate = root / "aggregate"
            manifest = score.write_numeric_outputs(aggregate, candidate, self.lock)
            scores = score.read_csv(aggregate / score.OUTPUT_NAMES["scores"])
            winners = score.read_csv(aggregate / score.OUTPUT_NAMES["winner"])
            self.assertEqual(len(scores), 120)
            self.assertEqual(len(winners), 4)
            self.assertEqual({row["condition_id"] for row in winners}, {"01", "02", "03", "04a"})
            self.assertEqual(manifest["candidate_score_rows"], 30)
            self.assertEqual(manifest["learning_runs_started"], 1)
            self.assertEqual(manifest["partial_run_count"], 1)
            self.assertTrue(manifest["guard_triggered"])
            self.assertEqual(len(calls), 1)
            winner_01 = next(row for row in winners if row["condition_id"] == "01")
            self.assertEqual(winner_01["eligible_20k_seed_count"], "0")
            self.assertEqual(winner_01["eligible_two_seed_rule"], "false")
            with (aggregate / score.OUTPUT_NAMES["scores"]).open(newline="", encoding="utf-8") as handle:
                self.assertEqual(tuple(next(csv.reader(handle))), score.SCORE_FIELDS)

    def test_seg_gap_is_control_pair_and_winner_hard_excludes_04b(self) -> None:
        fixture: list[dict[str, object]] = []
        for condition, rms in (("04a", 0.3), ("04b", 0.2)):
            for seed in score.EXPECTED_SEEDS:
                for building in self.lock.buildings:
                    fixture.append(
                        {
                            "condition_id": condition,
                            "seed": seed,
                            "building_id": building.building_id,
                            "metric_available": True,
                            "roof_rms_m": rms,
                            "roof_hausdorff_m": rms * 2,
                            "face_count_ratio_abs_error": 0.0,
                            "roof_completeness": 1.0,
                            "val3dity_valid": True,
                            "has_lod22": True,
                        }
                    )
        gap = score.build_seg_gap(fixture, self.lock)
        self.assertEqual(len(gap), 60)
        self.assertTrue(all(abs(float(row["delta_gt_minus_vision_roof_rms_m"]) + 0.1) < 1e-12 for row in gap))

        summaries: list[dict[str, object]] = []
        for condition_index, condition in enumerate((*score.HONEST_CONDITIONS, "04b")):
            for seed in score.EXPECTED_SEEDS:
                summaries.append(
                    {
                        "source_role": "honest" if condition != "04b" else "seg_upperbound",
                        "stratum": "all",
                        "condition_id": condition,
                        "seed": seed,
                        "rms_measurable_count": 30,
                        "roof_rms_median_m": 0.2 + condition_index * 0.01,
                        "rule_abcd": True,
                        "run_eligible_20k_full_state": True,
                    }
                )
        winner = score.build_winner_rows(summaries)
        self.assertEqual([row["condition_id"] for row in winner], ["01", "02", "03", "04a"])
        self.assertNotIn("04b", {row["condition_id"] for row in winner})
        self.assertEqual(sum(bool(row["is_minimum_worst_rms"]) for row in winner), 1)
        self.assertEqual(next(row for row in winner if row["is_minimum_worst_rms"])["condition_id"], "01")

    def test_seg_gap_keeps_all_60_rows_when_pair_is_missing(self) -> None:
        one_vision = {
            "condition_id": "04a",
            "seed": 1001,
            "building_id": self.lock.ids[0],
            "metric_available": True,
            "partial": True,
            "roof_rms_m": 0.3,
        }
        gap = score.build_seg_gap([one_vision], self.lock)
        self.assertEqual(len(gap), 60)
        indexed = {(int(row["seed"]), row["building_id"]): row for row in gap}
        first = indexed[(1001, self.lock.ids[0])]
        self.assertEqual(first["pair_state"], "missing_gt")
        self.assertTrue(first["vision_partial"])
        self.assertEqual(first["gt_run_state"], "missing")
        self.assertEqual(indexed[(1002, self.lock.ids[-1])]["pair_state"], "missing_both")

    def test_equal_worst_rms_values_are_co_minima(self) -> None:
        summaries: list[dict[str, object]] = []
        values = {"01": 0.2, "02": 0.2, "03": 0.3, "04a": 0.4}
        for condition, rms in values.items():
            for seed in score.EXPECTED_SEEDS:
                summaries.append(
                    {
                        "source_role": "honest",
                        "stratum": "all",
                        "condition_id": condition,
                        "seed": seed,
                        "rms_measurable_count": 30,
                        "roof_rms_median_m": rms,
                        "rule_abcd": True,
                        "run_eligible_20k_full_state": True,
                    }
                )
        winner = score.build_winner_rows(summaries)
        minima = {row["condition_id"] for row in winner if row["is_minimum_worst_rms"]}
        self.assertEqual(minima, {"01", "02"})
        self.assertTrue(
            all(row["co_minimum_count"] == 2 for row in winner)
        )
        self.assertTrue(
            all(
                row["minimum_worst_rms_order"] == 1
                for row in winner
                if row["condition_id"] in minima
            )
        )

    def test_aggregate_preserves_existing_run_and_rejects_completed_overwrite(self) -> None:
        with self.temporary_directory() as raw:
            root = Path(raw)
            first, _first_marker, _calls = self.bound_score_fixture(
                root / "first", "01", 1001, completed_steps=20000, z_offset=0.2
            )
            aggregate = root / "aggregate"
            score.write_numeric_outputs(aggregate, first, self.lock)
            score.write_numeric_outputs(aggregate, [], self.lock)
            preserved = [
                row
                for row in score.read_csv(aggregate / score.OUTPUT_NAMES["scores"])
                if row.get("condition_id") == "01" and row.get("seed") == "1001"
            ]
            self.assertEqual(len(preserved), 30)

            replacement, _second_marker, _calls = self.bound_score_fixture(
                root / "replacement", "01", 1001, completed_steps=20000, z_offset=0.3
            )
            with self.assertRaisesRegex(RuntimeError, "replace completed 20k run"):
                score.write_numeric_outputs(aggregate, replacement, self.lock)

    def test_roofer_recipe_and_locked_footprints(self) -> None:
        with self.temporary_directory() as raw:
            root = Path(raw)
            roofprints = root / "locked.geojson"
            record = score.materialize_locked_roofprints(self.lock, roofprints)
            payload = json.loads(roofprints.read_text(encoding="utf-8"))
            self.assertEqual(record["feature_count"], 30)
            self.assertEqual(
                [feature["properties"]["building_id"] for feature in payload["features"]],
                list(self.lock.ids),
            )
            self.assertTrue(all(feature["properties"]["class"] == 6 for feature in payload["features"]))
            self.assertTrue(
                all(
                    length == 2
                    for feature in payload["features"]
                    for length in score._all_coordinate_lengths(feature["geometry"]["coordinates"])
                )
            )
            pointcloud = score.RUN_DIR / "synthetic_not_created.laz"
            command_roofprints = score.RUN_DIR / "synthetic_not_created.geojson"
            output = score.RUN_DIR / "synthetic_not_created_roofer"
            command = score.roofer_docker_command(pointcloud, command_roofprints, output)
            self.assertEqual(command.count(score.ROOFER_IMAGE), 1)
            self.assertIn("--lod22", command)
            self.assertNotIn("--box", command)
            self.assertEqual(command.count("--id-attribute"), 1)
            self.assertEqual(command.count("--jobs"), 1)
            self.assertEqual(command.count("--srs"), 1)

    def test_roofer_pointcloud_requires_epsg25832_and_classes_2_6(self) -> None:
        with self.temporary_directory() as raw:
            root = Path(raw)
            path = root / "synthetic.las"
            metric_module = score.get_metric_module()
            header = metric_module.laspy.LasHeader(point_format=6, version="1.4")
            header.add_crs(CRS.from_epsg(25832))
            cloud = metric_module.laspy.LasData(header)
            cloud.x = np.asarray([690800.0, 690801.0])
            cloud.y = np.asarray([5336000.0, 5336001.0])
            cloud.z = np.asarray([500.0, 510.0])
            cloud.classification = np.asarray([2, 6], dtype=np.uint8)
            cloud.write(path)
            record = score.validate_roofer_pointcloud(path)
            self.assertEqual(record["epsg"], 25832)
            self.assertEqual(record["classes_required"], [2, 6])
            self.assertEqual(record["point_count"], 2)

            wrong = root / "wrong.las"
            wrong_header = metric_module.laspy.LasHeader(point_format=6, version="1.4")
            wrong_header.add_crs(CRS.from_epsg(4326))
            wrong_cloud = metric_module.laspy.LasData(wrong_header)
            wrong_cloud.x = np.asarray([11.0, 11.1])
            wrong_cloud.y = np.asarray([48.0, 48.1])
            wrong_cloud.z = np.asarray([500.0, 510.0])
            wrong_cloud.classification = np.asarray([2, 6], dtype=np.uint8)
            wrong_cloud.write(wrong)
            with self.assertRaisesRegex(RuntimeError, "pointcloud EPSG"):
                score.validate_roofer_pointcloud(wrong)


if __name__ == "__main__":
    unittest.main(verbosity=2)
