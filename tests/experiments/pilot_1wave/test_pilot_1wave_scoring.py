#!/usr/bin/env python3
"""Docker synthetic tests for the P1W expanded-30 scoring adapter."""
from __future__ import annotations

import copy
import csv
import hashlib
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import numpy as np
from pyproj import CRS

REPO = Path(__file__).resolve().parents[3]
TEST_DIR = Path(__file__).resolve().parent
SCRIPT_DIR = REPO / "scripts/experiments/pilot_1wave"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import pilot_1wave_scoring as score
import pilot_1wave_readout_lineage as lineage_contract


class PilotOneWaveScoringTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.p0_environment = mock.patch.dict(
            os.environ,
            {
                score.P0_TOOLS_SENTINEL_ENV: "1",
                score.P0_TOOLS_IMAGE_ID_ENV: score.P0_TOOLS_IMAGE_ID,
            },
        )
        cls.p0_environment.start()
        cls.lock = score.load_pilot_lock()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.p0_environment.stop()

    def temporary_directory(self) -> tempfile.TemporaryDirectory[str]:
        return tempfile.TemporaryDirectory(prefix=".p1w_score_", dir=TEST_DIR)

    def repo_path(self, value: str) -> Path:
        path = Path(value)
        return path if path.is_absolute() else score.REPO / path

    def write_classified_las(self, path: Path) -> None:
        metric_module = score.get_metric_module()
        header = metric_module.laspy.LasHeader(point_format=6, version="1.4")
        header.add_crs(CRS.from_epsg(25832))
        cloud = metric_module.laspy.LasData(header)
        cloud.x = np.asarray([690800.0, 690801.0])
        cloud.y = np.asarray([5336000.0, 5336001.0])
        cloud.z = np.asarray([500.0, 510.0])
        cloud.classification = np.asarray([2, 6], dtype=np.uint8)
        cloud.write(path)

    def write_roofer_jsonseq(self, source_cityjson: Path, raw_dir: Path) -> Path:
        source = json.loads(source_cityjson.read_text(encoding="utf-8"))
        source_vertices = source["vertices"]
        source_transform = source.get("transform")
        scale = [0.001, 0.001, 0.001]
        translate = [0.0, 0.0, 0.0]

        def absolute_vertex(vertex: list[float]) -> list[float]:
            if source_transform is None:
                return [float(value) for value in vertex]
            return [
                float(vertex[index]) * float(source_transform["scale"][index])
                + float(source_transform["translate"][index])
                for index in range(3)
            ]

        def indices(value: object) -> list[int]:
            if isinstance(value, int):
                return [value]
            if isinstance(value, list):
                return [index for item in value for index in indices(item)]
            return []

        def remap(value: object, mapping: dict[int, int]) -> object:
            if isinstance(value, int):
                return mapping[value]
            if isinstance(value, list):
                return [remap(item, mapping) for item in value]
            return value

        header = {
            "type": "CityJSON",
            "version": "2.0",
            "transform": {"scale": scale, "translate": translate},
            "metadata": {
                "referenceSystem": "https://www.opengis.net/def/crs/EPSG/0/25832"
            },
            "CityObjects": {},
            "vertices": [],
        }
        lines = [json.dumps(header, separators=(",", ":"))]
        for building_id in self.lock.ids:
            cityobject = copy.deepcopy(source["CityObjects"][building_id])
            used = sorted(
                set(
                    index
                    for geometry in cityobject.get("geometry", [])
                    for index in indices(geometry.get("boundaries"))
                )
            )
            mapping = {old: new for new, old in enumerate(used)}
            for geometry in cityobject.get("geometry", []):
                geometry["boundaries"] = remap(geometry["boundaries"], mapping)
            vertices = [
                [
                    int(round((coordinate - translate[index]) / scale[index]))
                    for index, coordinate in enumerate(absolute_vertex(source_vertices[old]))
                ]
                for old in used
            ]
            lines.append(
                json.dumps(
                    {
                        "type": "CityJSONFeature",
                        "id": building_id,
                        "CityObjects": {building_id: cityobject},
                        "vertices": vertices,
                    },
                    separators=(",", ":"),
                )
            )
        output = raw_dir / "synthetic.city.jsonl"
        output.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return output

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
            "step_semantics": "completed_optimizer_updates",
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

    def write_execution_receipt(
        self,
        prepared: dict[str, object],
        condition: str,
        seed: int,
    ) -> Path:
        runtime = Path(str(prepared["path"])).parent
        job_id = f"{condition}_seed{seed}"
        container_name = (
            f"{score.ROOFER_CONTAINER_NAME_PREFIX}-{condition}-seed{seed}-roofer"
        )
        container_id = "a" * 64
        argv = prepared["roofer_argv"]
        if not isinstance(argv, dict):
            raise AssertionError("synthetic prepare fixture lacks argv")
        contract_sha = score.canonical_json_sha256(
            {
                "job_id": job_id,
                "prepare_sha256": prepared["sha256"],
                "argv_sha256": argv["sha256"],
                "image": score.ROOFER_IMAGE,
                "arguments": argv["arguments"],
            }
        )
        start_attempts = [
            {"ordinal": 1, "requested_utc": "2026-07-22T00:00:00+00:00"}
        ]
        repo_bind = f"/host-mount/JointBuildGS:{score.ROOFER_CONTAINER_REPO}"
        launch_path = runtime / "container_launch.json"
        process_path = runtime / "process_complete.json"
        log_path = runtime / "container.log"
        score.atomic_json(
            launch_path,
            {
                "schema": "jointbuildgs.pilot_1wave.postprocess_stage.v1",
                "state": "start_requested",
                "job_id": job_id,
                "container_name": container_name,
                "container_id": container_id,
                "contract_sha256": contract_sha,
                "create_command": [
                    "docker", "create", "-v", repo_bind, score.ROOFER_IMAGE,
                ],
                "start_attempt_count": 1,
                "start_attempts": start_attempts,
            },
        )
        score.atomic_json(
            process_path,
            {
                "schema": "jointbuildgs.pilot_1wave.postprocess_stage.v1",
                "state": "process_complete",
                "job_id": job_id,
                "container_name": container_name,
                "contract_sha256": contract_sha,
                "exit_code": 0,
                "wait_exit_code": 0,
            },
        )
        log_path.write_text("immutable synthetic Roofer log\n", encoding="utf-8")
        receipt_path = runtime / "roofer_execution_receipt.json"
        score.atomic_json(
            receipt_path,
            {
                "schema": score.ROOFER_EXECUTION_SCHEMA,
                "state": "complete",
                "condition_id": condition,
                "seed": seed,
                "job_id": job_id,
                "prepare_receipt": {
                    "path": score.rel(Path(str(prepared["path"]))),
                    "sha256": prepared["sha256"],
                },
                "roofer_argv": {
                    "path": argv["path"],
                    "sha256": argv["sha256"],
                },
                "container": {
                    "id": container_id,
                    "name": container_name,
                    "image_reference": score.ROOFER_IMAGE,
                    "image_id": score.ROOFER_IMAGE_ID,
                    "config_image": score.ROOFER_IMAGE,
                    "entrypoint": list(score.ROOFER_ENTRYPOINT),
                    "cmd": argv["arguments"],
                    "labels": {
                        "jointbuildgs.p1w.job": job_id,
                        "jointbuildgs.p1w.contract": contract_sha,
                    },
                    "binds": [repo_bind],
                    "network_mode": "none",
                    "restart_count": 0,
                },
                "execution": {
                    "start_attempt_count": 1,
                    "start_attempts": start_attempts,
                    "started_at": "2026-07-22T00:00:00+00:00",
                    "finished_at": "2026-07-22T00:01:00+00:00",
                    "wait_exit_code": 0,
                    "docker_state": "exited",
                },
                "logs": {
                    "path": score.rel(log_path),
                    "sha256": score.sha256_file(log_path),
                    "size": log_path.stat().st_size,
                },
                "launch_receipt": {
                    "path": score.rel(launch_path),
                    "sha256": score.sha256_file(launch_path),
                },
                "process_receipt": {
                    "path": score.rel(process_path),
                    "sha256": score.sha256_file(process_path),
                },
                "created_utc": "2026-07-22T00:01:01+00:00",
                "roofer_invocation_count": 1,
            },
        )
        return receipt_path

    def roofer_marker_fixture(
        self,
        root: Path,
        condition: str,
        seed: int,
        cityjson: Path,
        full_state: Path,
    ) -> tuple[Path, Path]:
        root.mkdir(parents=True, exist_ok=True)
        pointcloud = root / "classified.laz"
        self.write_classified_las(pointcloud)
        run_provenance = score.validate_full_state_manifest(
            condition,
            seed,
            full_state,
            guard_status=(
                "not_triggered"
                if json.loads(full_state.read_text(encoding="utf-8")).get(
                    "process_completed"
                )
                else "triggered_checkpoint_stop"
            ),
            guard_reason=(
                ""
                if json.loads(full_state.read_text(encoding="utf-8")).get(
                    "process_completed"
                )
                else "9h guard"
            ),
        )
        crop_json = lineage_contract.canonical_json(
            lineage_contract.PILOT_CROP_CONTRACT
        )
        lineage = {
            "schema": score.READOUT_LINEAGE_SCHEMA,
            "condition_id": condition,
            "seed": seed,
            "checkpoint": {
                "format": "jointbuildgs.stage2.full_state",
                "path": run_provenance["latest_full_checkpoint_path"],
                "sha256": run_provenance["latest_full_checkpoint_sha256"],
                "completed_steps": run_provenance[
                    "latest_full_checkpoint_steps"
                ],
                "step_semantics": "completed_optimizer_updates",
            },
            "full_state_manifest": {
                "path": score.rel(full_state),
                "sha256": score.sha256_file(full_state),
                "schema": score.FULL_STATE_MANIFEST_SCHEMA,
            },
            "training_config": {
                "path": run_provenance["training_config_path"],
                "sha256": run_provenance["training_config_sha256"],
                "pilot_arm": run_provenance["pilot_arm"],
            },
            "verified_full_state": True,
            "eligible_20k_full_state": run_provenance[
                "eligible_20k_full_state"
            ],
            "geometry_only": True,
            "crop_contract_json": crop_json,
            "crop_contract_sha256": lineage_contract.PILOT_CROP_CONTRACT_SHA256,
        }
        lineage = lineage_contract.validate_readout_lineage(
            lineage,
            expected_condition=condition,
            expected_seed=seed,
        )
        crop_contract = lineage_contract.validate_pilot_crop_contract(
            crop_json, lineage_contract.PILOT_CROP_CONTRACT_SHA256
        )
        scene_npz = root / "scene_geometry.npz"
        np.savez(
            scene_npz,
            P_utm_clean=np.asarray([[690800.0, 5336000.0, 570.0]]),
            readout_lineage_json=np.array(
                json.dumps(lineage, sort_keys=True, separators=(",", ":"))
            ),
            crop_contract_json=np.array(crop_json),
            crop_contract_sha256=np.array(
                lineage_contract.PILOT_CROP_CONTRACT_SHA256
            ),
        )
        footprints = root / "locked_30.geojson"
        score.materialize_locked_roofprints(self.lock, footprints)
        roofprint_record = lineage_contract.validate_roofprint_file(
            footprints, expected_building_ids=self.lock.ids
        )
        pipeline = root / "pdal_pipeline.json"
        pipeline.write_text(
            json.dumps(
                {
                    "pipeline": [
                        {
                            "type": "filters.overlay",
                            "datasource": str(footprints),
                            "dimension": "Classification",
                            "column": "class",
                            "where": "Classification != 2",
                        },
                        {"type": "writers.las", "filename": str(pointcloud)},
                    ]
                }
            )
            + "\n",
            encoding="utf-8",
        )
        classification_receipt = root / "scene_classification.receipt.json"
        classification_receipt.write_text(
            json.dumps(
                {
                    "schema": "jointbuildgs.pilot_1wave.scene_classification.v1",
                    "state": "complete",
                    "source_scene_npz": {
                        "path": str(scene_npz),
                        "sha256": score.sha256_file(scene_npz),
                    },
                    "classified_las": {
                        "path": str(pointcloud),
                        "sha256": score.sha256_file(pointcloud),
                    },
                    "readout_lineage": lineage,
                    "crop_contract": crop_contract,
                    "roofprints": roofprint_record,
                    "classification": {
                        "pipeline_path": str(pipeline),
                        "pipeline_sha256": score.sha256_file(pipeline),
                    },
                }
            )
            + "\n",
            encoding="utf-8",
        )
        prepared = score.prepare_roofer(
            condition,
            seed,
            pointcloud,
            classification_receipt,
            root / "runtime",
            self.lock,
        )
        raw_dir = score.REPO / prepared["outputs"]["raw_jsonseq_dir"]
        self.write_roofer_jsonseq(cityjson, raw_dir)
        execution_receipt = self.write_execution_receipt(
            prepared, condition, seed
        )
        merged, _state = score.finalize_roofer(
            Path(prepared["path"]),
            execution_receipt,
            self.lock,
            expected_condition=condition,
            expected_seed=seed,
        )
        return merged.parent / "roofer_invocation.json", merged

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
        roofer_marker, cityjson = self.roofer_marker_fixture(
            root / "roofer", condition, seed, cityjson, full_state
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

    def test_manifest_lineage_drift_fails_before_val3dity(self) -> None:
        with self.temporary_directory() as raw:
            root = Path(raw)
            cityjson, _unused_report, references = self.synthetic_fixture(root)
            full_state = self.full_state_fixture(
                root / "train", "01", 1001, completed_steps=20000
            )
            roofer_marker, cityjson = self.roofer_marker_fixture(
                root / "roofer", "01", 1001, cityjson, full_state
            )
            payload = json.loads(full_state.read_text(encoding="utf-8"))
            payload["post_lineage_mutation"] = True
            full_state.write_text(json.dumps(payload) + "\n", encoding="utf-8")
            calls: list[tuple[Path, Path]] = []

            def forbidden_val3dity(
                path: Path, report: Path
            ) -> tuple[dict[str, bool], int, str]:
                calls.append((path, report))
                raise AssertionError("val3dity must not run after lineage drift")

            with self.assertRaisesRegex(RuntimeError, "full-state manifest SHA256"):
                score.score_bound_run_once(
                    "01",
                    1001,
                    cityjson,
                    roofer_marker,
                    full_state,
                    root / "scores.csv",
                    root / "score_marker.json",
                    self.lock,
                    guard_status="not_triggered",
                    references=references,
                    val3dity_runner=forbidden_val3dity,
                )
            self.assertEqual(calls, [])

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

    def test_numeric_writer_attests_prepopulated_loss_cursor_without_replacing_it(self) -> None:
        with self.temporary_directory() as raw:
            root = Path(raw)
            candidate, _marker, _calls = self.bound_score_fixture(
                root / "run", "01", 1001, completed_steps=5000
            )
            aggregate = root / "aggregate"
            score.initialize_output_schemas(aggregate, self.lock)
            loss_path = aggregate / score.OUTPUT_NAMES["loss_shares"]
            loss_rows = [
                {
                    "schema_version": score.SCHEMA_VERSION,
                    "condition_id": "01",
                    "seed": 1001,
                    "checkpoint_step": 20_000,
                    "checkpoint_sha256": "a" * 64,
                    "iter": 100,
                    "term": "pho",
                    "raw": 1.0,
                    "weighted": 1.0,
                    "share": 1.0,
                    "roof_share": 1.0,
                }
            ]
            score.atomic_csv(loss_path, loss_rows, score.LOSS_SHARE_FIELDS)
            expected = loss_path.read_bytes()
            manifest = score.write_numeric_outputs(aggregate, candidate, self.lock)
            self.assertEqual(loss_path.read_bytes(), expected)
            self.assertEqual(
                manifest["outputs"][score.OUTPUT_NAMES["loss_shares"]]["sha256"],
                score.sha256_file(loss_path),
            )
            self.assertEqual(
                manifest["outputs"][score.OUTPUT_NAMES["loss_shares"]]["row_count"],
                1,
            )

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

    def test_receipt_bound_roofprints_reject_swapped_order_and_mutated_bytes(self) -> None:
        with self.temporary_directory() as raw:
            root = Path(raw)
            roofprints = root / "swapped.geojson"
            score.materialize_locked_roofprints(self.lock, roofprints)
            payload = json.loads(roofprints.read_text(encoding="utf-8"))
            payload["features"][0], payload["features"][1] = (
                payload["features"][1],
                payload["features"][0],
            )
            roofprints.write_text(json.dumps(payload) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "ordered building IDs"):
                lineage_contract.validate_roofprint_file(
                    roofprints, expected_building_ids=self.lock.ids
                )
            score.materialize_locked_roofprints(self.lock, roofprints)
            payload = json.loads(roofprints.read_text(encoding="utf-8"))
            payload["features"][0]["properties"]["unexpected"] = True
            roofprints.write_text(json.dumps(payload) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "roofprint properties"):
                lineage_contract.validate_roofprint_file(
                    roofprints, expected_building_ids=self.lock.ids
                )

            bound_root = root / "bound"
            bound_root.mkdir()
            cityjson, _report, _references = self.synthetic_fixture(bound_root)
            full_state = self.full_state_fixture(
                root / "bound/train", "01", 1001, completed_steps=score.MAX_ITER
            )
            marker, _merged = self.roofer_marker_fixture(
                root / "bound/roofer", "01", 1001, cityjson, full_state
            )
            marker_payload = json.loads(marker.read_text(encoding="utf-8"))
            receipt = Path(marker_payload["classification_receipt"]["path"])
            pointcloud = Path(marker_payload["pointcloud_path"])
            bound_roofprints = Path(marker_payload["footprints"]["path"])
            bound_roofprints.write_bytes(bound_roofprints.read_bytes() + b" \n")
            with self.assertRaisesRegex(
                RuntimeError, "classification receipt roofprints sha256"
            ):
                lineage_contract.validate_classification_receipt(
                    receipt,
                    pointcloud_path=pointcloud,
                    expected_condition="01",
                    expected_seed=1001,
                    expected_building_ids=self.lock.ids,
                )

    def test_classification_receipt_rejects_roofprint_path_and_sha_mismatch(self) -> None:
        for drift in ("path", "sha256", "geometry_sha256"):
            with self.subTest(drift=drift), self.temporary_directory() as raw:
                root = Path(raw)
                cityjson, _report, _references = self.synthetic_fixture(root)
                full_state = self.full_state_fixture(
                    root / "train", "02", 1002, completed_steps=score.MAX_ITER
                )
                marker, _merged = self.roofer_marker_fixture(
                    root / "roofer", "02", 1002, cityjson, full_state
                )
                marker_payload = json.loads(marker.read_text(encoding="utf-8"))
                receipt = Path(marker_payload["classification_receipt"]["path"])
                pointcloud = Path(marker_payload["pointcloud_path"])
                receipt_payload = json.loads(receipt.read_text(encoding="utf-8"))
                if drift == "path":
                    replacement = receipt.with_name("same_bytes_other_path.geojson")
                    shutil.copyfile(receipt_payload["roofprints"]["path"], replacement)
                    receipt_payload["roofprints"]["path"] = str(replacement)
                    expected_error = "classification pipeline roofprint path"
                else:
                    if drift == "sha256":
                        receipt_payload["roofprints"]["sha256"] = "0" * 64
                        expected_error = "classification receipt roofprints sha256"
                    else:
                        receipt_payload["roofprints"][
                            "ordered_feature_geometry_sha256"
                        ] = "0" * 64
                        expected_error = (
                            "classification receipt roofprints "
                            "ordered_feature_geometry_sha256"
                        )
                receipt.write_text(json.dumps(receipt_payload) + "\n", encoding="utf-8")
                with self.assertRaisesRegex(RuntimeError, expected_error):
                    lineage_contract.validate_classification_receipt(
                        receipt,
                        pointcloud_path=pointcloud,
                        expected_condition="02",
                        expected_seed=1002,
                        expected_building_ids=self.lock.ids,
                    )

    def test_scene_binding_rejects_crop_population_mismatch_even_with_new_sha(self) -> None:
        with self.temporary_directory() as raw:
            root = Path(raw)
            cityjson, _report, _references = self.synthetic_fixture(root)
            full_state = self.full_state_fixture(
                root / "train", "03", 1001, completed_steps=score.MAX_ITER
            )
            marker, _merged = self.roofer_marker_fixture(
                root / "roofer", "03", 1001, cityjson, full_state
            )
            marker_payload = json.loads(marker.read_text(encoding="utf-8"))
            receipt = Path(marker_payload["classification_receipt"]["path"])
            receipt_payload = json.loads(receipt.read_text(encoding="utf-8"))
            source_npz = Path(receipt_payload["source_scene_npz"]["path"])
            with np.load(source_npz, allow_pickle=False) as source:
                points = np.asarray(source["P_utm_clean"])
                embedded_lineage = json.loads(
                    str(source["readout_lineage_json"].item())
                )
            bad_contract = json.loads(
                json.dumps(lineage_contract.PILOT_CROP_CONTRACT)
            )
            bad_contract["population"]["count"] = 29
            bad_json = lineage_contract.canonical_json(bad_contract)
            bad_sha = hashlib.sha256(bad_json.encode("utf-8")).hexdigest()
            embedded_lineage["crop_contract_json"] = bad_json
            embedded_lineage["crop_contract_sha256"] = bad_sha
            bad_npz = root / "bad_population.npz"
            np.savez(
                bad_npz,
                P_utm_clean=points,
                readout_lineage_json=np.array(
                    lineage_contract.canonical_json(embedded_lineage)
                ),
                crop_contract_json=np.array(bad_json),
                crop_contract_sha256=np.array(bad_sha),
            )
            with self.assertRaisesRegex(RuntimeError, "locked crop contract SHA256"):
                lineage_contract.validate_scene_npz_binding(
                    bad_npz,
                    expected_condition="03",
                    expected_seed=1001,
                )

    def test_prepare_roofer_is_p0_only_immutable_and_uses_receipt_roofprints(self) -> None:
        with self.temporary_directory() as raw:
            root = Path(raw)
            cityjson, _report, _references = self.synthetic_fixture(root)
            full_state = self.full_state_fixture(
                root / "train", "04a", 1001, completed_steps=score.MAX_ITER
            )
            fixture_marker, _merged = self.roofer_marker_fixture(
                root / "fixture", "04a", 1001, cityjson, full_state
            )
            fixture_payload = json.loads(
                fixture_marker.read_text(encoding="utf-8")
            )
            receipt = self.repo_path(fixture_payload["classification_receipt"]["path"])
            pointcloud = self.repo_path(fixture_payload["pointcloud_path"])
            roofprints = Path(fixture_payload["footprints"]["path"]).resolve()
            output_dir = root / "prepare_only"
            with mock.patch.object(
                score.subprocess,
                "run",
                side_effect=AssertionError("prepare must not execute subprocess"),
            ):
                prepared = score.prepare_roofer(
                    "04a", 1001, pointcloud, receipt, output_dir, self.lock
                )
            expected_container_path = str(
                Path("/workspace/JointBuildGS")
                / roofprints.relative_to(score.REPO.resolve())
            )
            self.assertEqual(
                prepared["roofer_argv"]["arguments"][-2], expected_container_path
            )
            self.assertEqual(
                prepared["footprints"]["ordered_feature_geometry_sha256"],
                fixture_payload["footprints"]["ordered_feature_geometry_sha256"],
            )
            self.assertEqual(
                prepared["footprints"]["feature_properties"],
                fixture_payload["footprints"]["feature_properties"],
            )
            self.assertEqual(list((output_dir / "raw_jsonseq").iterdir()), [])
            self.assertFalse((output_dir / "assembled.city.json").exists())
            self.assertFalse((output_dir / "roofer_invocation.json").exists())

            stale = root / "stale"
            stale.mkdir()
            (stale / "old.output").write_text("stale", encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "not empty"):
                score.prepare_roofer(
                    "04a", 1001, pointcloud, receipt, stale, self.lock
                )
            with mock.patch.dict(
                os.environ, {score.P0_TOOLS_SENTINEL_ENV: "0"}
            ):
                with self.assertRaisesRegex(RuntimeError, "lacks P1W_INSIDE_P0_TOOLS"):
                    score.prepare_roofer(
                        "04a", 1001, pointcloud, receipt, root / "outside", self.lock
                    )
            with mock.patch.object(score, "DOCKER_SENTINEL", root / "not-docker"):
                with self.assertRaisesRegex(RuntimeError, "Docker sentinel"):
                    score.require_p0_tools_runtime()
            with mock.patch.dict(
                os.environ, {score.P0_TOOLS_IMAGE_ID_ENV: "sha256:" + "0" * 64}
            ):
                with self.assertRaisesRegex(RuntimeError, "image ID attestation"):
                    score.require_p0_tools_runtime()

    def test_finalize_v2_marker_is_exact_and_second_finalize_is_idempotent(self) -> None:
        with self.temporary_directory() as raw:
            root = Path(raw)
            cityjson, _report, _references = self.synthetic_fixture(root)
            full_state = self.full_state_fixture(
                root / "train", "04b", 1002, completed_steps=score.MAX_ITER
            )
            marker, merged = self.roofer_marker_fixture(
                root / "roofer", "04b", 1002, cityjson, full_state
            )
            validated = score.validate_roofer_marker(
                "04b", 1002, marker, merged, self.lock
            )
            marker_payload = json.loads(marker.read_text(encoding="utf-8"))
            self.assertEqual(marker_payload["schema"], score.ROOFER_MARKER_SCHEMA)
            self.assertEqual(marker_payload["raw_jsonseq"]["feature_count"], 30)
            self.assertEqual(marker_payload["raw_jsonseq"]["root_building_count"], 30)
            self.assertEqual(marker_payload["merged_cityjson"]["root_building_count"], 30)
            self.assertEqual(
                marker_payload["roofer_execution"]["roofer_local_image_id"],
                score.ROOFER_IMAGE_ID,
            )
            self.assertEqual(
                marker_payload["roofer_execution"]["start_attempt_count"], 1
            )
            self.assertEqual(
                marker_payload["execution_receipt"]["sha256"],
                validated["execution_receipt_sha256"],
            )
            self.assertEqual(
                marker_payload["footprints"]["ordered_feature_geometry_sha256"],
                validated["roofprints"]["ordered_feature_geometry_sha256"],
            )
            prepare_path = self.repo_path(marker_payload["prepare_receipt"]["path"])
            execution_path = self.repo_path(
                marker_payload["execution_receipt"]["path"]
            )
            marker_sha = score.sha256_file(marker)
            with mock.patch.object(
                score,
                "load_module",
                side_effect=AssertionError("idempotent finalize must not rerun W2"),
            ):
                repeated_cityjson, repeated_state = score.finalize_roofer(
                    prepare_path,
                    execution_path,
                    self.lock,
                    expected_condition="04b",
                    expected_seed=1002,
                )
            self.assertEqual(repeated_cityjson, merged)
            self.assertEqual(repeated_state, marker_payload)
            self.assertEqual(score.sha256_file(marker), marker_sha)

            marker_payload["schema"] = "jointbuildgs.pilot_1wave.roofer_invocation.v1"
            marker.write_text(json.dumps(marker_payload) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "Roofer marker schema"):
                score.validate_roofer_marker("04b", 1002, marker, merged, self.lock)

    def test_finalize_requires_present_untampered_execution_receipt(self) -> None:
        for drift in ("missing", "tampered"):
            with self.subTest(drift=drift), self.temporary_directory() as raw:
                root = Path(raw)
                cityjson, _report, _references = self.synthetic_fixture(root)
                full_state = self.full_state_fixture(
                    root / "train", "01", 1002, completed_steps=score.MAX_ITER
                )
                marker, merged = self.roofer_marker_fixture(
                    root / "roofer", "01", 1002, cityjson, full_state
                )
                marker_payload = json.loads(marker.read_text(encoding="utf-8"))
                prepare_path = self.repo_path(
                    marker_payload["prepare_receipt"]["path"]
                )
                execution_path = self.repo_path(
                    marker_payload["execution_receipt"]["path"]
                )
                marker.unlink()
                merged.unlink()
                if drift == "missing":
                    execution_path.unlink()
                    expected = "roofer_execution_receipt.json"
                else:
                    receipt = json.loads(execution_path.read_text(encoding="utf-8"))
                    receipt["execution"]["docker_state"] = "running"
                    execution_path.write_text(
                        json.dumps(receipt) + "\n", encoding="utf-8"
                    )
                    expected = "Roofer Docker state"
                with mock.patch.object(
                    score,
                    "load_module",
                    side_effect=AssertionError("invalid receipt must fail before W2"),
                ):
                    with self.assertRaisesRegex((RuntimeError, FileNotFoundError), expected):
                        score.finalize_roofer(
                            prepare_path,
                            execution_path,
                            self.lock,
                            expected_condition="01",
                            expected_seed=1002,
                        )

    def test_v2_marker_reopens_execution_log_and_rejects_tamper(self) -> None:
        with self.temporary_directory() as raw:
            root = Path(raw)
            cityjson, _report, _references = self.synthetic_fixture(root)
            full_state = self.full_state_fixture(
                root / "train", "02", 1002, completed_steps=score.MAX_ITER
            )
            marker, merged = self.roofer_marker_fixture(
                root / "roofer", "02", 1002, cityjson, full_state
            )
            marker_payload = json.loads(marker.read_text(encoding="utf-8"))
            log_path = self.repo_path(
                marker_payload["roofer_execution"]["logs"]["path"]
            )
            log_path.write_bytes(log_path.read_bytes() + b"tampered\n")
            with self.assertRaisesRegex(RuntimeError, "immutable log SHA256"):
                score.validate_roofer_marker(
                    "02", 1002, marker, merged, self.lock
                )

    def test_execution_receipt_rejects_actual_docker_contract_drift(self) -> None:
        with self.temporary_directory() as raw:
            root = Path(raw)
            cityjson, _report, _references = self.synthetic_fixture(root)
            full_state = self.full_state_fixture(
                root / "train", "03", 1002, completed_steps=score.MAX_ITER
            )
            marker, _merged = self.roofer_marker_fixture(
                root / "roofer", "03", 1002, cityjson, full_state
            )
            marker_payload = json.loads(marker.read_text(encoding="utf-8"))
            prepare_path = self.repo_path(marker_payload["prepare_receipt"]["path"])
            execution_path = self.repo_path(
                marker_payload["execution_receipt"]["path"]
            )
            prepared = score.validate_roofer_prepare_receipt(
                prepare_path,
                self.lock,
                expected_condition="03",
                expected_seed=1002,
            )
            original = execution_path.read_bytes()
            drifts = {
                "job_id": (lambda value: value.__setitem__("job_id", "wrong"), "job_id"),
                "name": (
                    lambda value: value["container"].__setitem__("name", "wrong"),
                    "container name",
                ),
                "entrypoint": (
                    lambda value: value["container"].__setitem__("entrypoint", ["wrong"]),
                    "container entrypoint",
                ),
                "cmd": (
                    lambda value: value["container"].__setitem__("cmd", ["--wrong"]),
                    "container command",
                ),
                "contract_label": (
                    lambda value: value["container"]["labels"].__setitem__(
                        "jointbuildgs.p1w.contract", "0" * 64
                    ),
                    "contract label",
                ),
                "network": (
                    lambda value: value["container"].__setitem__(
                        "network_mode", "default"
                    ),
                    "network mode",
                ),
                "bind": (
                    lambda value: value["container"].__setitem__("binds", []),
                    "repository bind",
                ),
            }
            for drift, (mutate, expected) in drifts.items():
                with self.subTest(drift=drift):
                    payload = json.loads(original.decode("utf-8"))
                    mutate(payload)
                    execution_path.write_text(
                        json.dumps(payload) + "\n", encoding="utf-8"
                    )
                    with self.assertRaisesRegex(RuntimeError, expected):
                        score.validate_roofer_execution_receipt(
                            execution_path,
                            prepared,
                            expected_condition="03",
                            expected_seed=1002,
                        )
                    execution_path.write_bytes(original)

    def test_repository_bind_uses_host_alias_and_sealed_create_command(self) -> None:
        raw = f"/host-mount/JointBuildGS:{score.ROOFER_CONTAINER_REPO}"
        launch = {
            "create_command": [
                "docker", "create", "-v", raw, score.ROOFER_IMAGE,
            ]
        }
        normalized = score.validate_repository_bind([raw], launch)
        self.assertEqual(normalized, {
            "source": "/host-mount/JointBuildGS",
            "target": str(score.ROOFER_CONTAINER_REPO),
            "mode": "rw",
            "docker_value": raw,
            "launch_value": raw,
        })
        self.assertNotEqual(normalized["source"], str(score.REPO.resolve()))
        inspect_with_rw = f"{raw}:rw"
        normalized_rw = score.validate_repository_bind([inspect_with_rw], launch)
        self.assertEqual(normalized_rw["source"], normalized["source"])
        self.assertEqual(normalized_rw["mode"], "rw")
        self.assertEqual(normalized_rw["docker_value"], inspect_with_rw)
        self.assertEqual(normalized_rw["launch_value"], raw)
        with self.assertRaisesRegex(RuntimeError, "mode must be absent or rw"):
            score.validate_repository_bind(
                [f"/host-mount/JointBuildGS:{score.ROOFER_CONTAINER_REPO}:ro"],
                {"create_command": [
                    "docker", "create", "-v",
                    f"/host-mount/JointBuildGS:{score.ROOFER_CONTAINER_REPO}:ro",
                ]},
            )
        with self.assertRaisesRegex(RuntimeError, "launch/inspect bind source"):
            score.validate_repository_bind(
                [raw],
                {"create_command": [
                    "docker", "create", "-v",
                    f"/different-host/JointBuildGS:{score.ROOFER_CONTAINER_REPO}",
                ]},
            )

    def test_finalize_recovers_merged_without_marker_without_rerunning_w2(self) -> None:
        with self.temporary_directory() as raw:
            root = Path(raw)
            cityjson, _report, _references = self.synthetic_fixture(root)
            full_state = self.full_state_fixture(
                root / "train", "03", 1001, completed_steps=score.MAX_ITER
            )
            marker, merged = self.roofer_marker_fixture(
                root / "roofer", "03", 1001, cityjson, full_state
            )
            marker_payload = json.loads(marker.read_text(encoding="utf-8"))
            prepare_path = self.repo_path(marker_payload["prepare_receipt"]["path"])
            execution_path = self.repo_path(
                marker_payload["execution_receipt"]["path"]
            )
            merged_sha = score.sha256_file(merged)
            marker.unlink()
            with mock.patch.object(
                score,
                "load_module",
                side_effect=AssertionError("merged recovery must not rerun W2"),
            ):
                recovered, state = score.finalize_roofer(
                    prepare_path,
                    execution_path,
                    self.lock,
                    expected_condition="03",
                    expected_seed=1001,
                )
            self.assertEqual(recovered, merged)
            self.assertEqual(score.sha256_file(recovered), merged_sha)
            self.assertEqual(state["cityjson_sha256"], merged_sha)
            self.assertTrue(marker.is_file())

    def test_finalize_validates_and_promotes_temp_only_recovery(self) -> None:
        with self.temporary_directory() as raw:
            root = Path(raw)
            cityjson, _report, _references = self.synthetic_fixture(root)
            full_state = self.full_state_fixture(
                root / "train", "04a", 1002, completed_steps=score.MAX_ITER
            )
            marker, merged = self.roofer_marker_fixture(
                root / "roofer", "04a", 1002, cityjson, full_state
            )
            marker_payload = json.loads(marker.read_text(encoding="utf-8"))
            prepare_path = self.repo_path(marker_payload["prepare_receipt"]["path"])
            execution_path = self.repo_path(
                marker_payload["execution_receipt"]["path"]
            )
            merged_sha = score.sha256_file(merged)
            temporary = merged.with_name(f".{merged.name}.tmp")
            marker.unlink()
            os.replace(merged, temporary)
            with mock.patch.object(
                score,
                "load_module",
                side_effect=AssertionError("temp recovery must not rerun W2"),
            ):
                recovered, state = score.finalize_roofer(
                    prepare_path,
                    execution_path,
                    self.lock,
                    expected_condition="04a",
                    expected_seed=1002,
                )
            self.assertEqual(recovered, merged)
            self.assertFalse(temporary.exists())
            self.assertEqual(score.sha256_file(recovered), merged_sha)
            self.assertEqual(state["cityjson_sha256"], merged_sha)

    def test_finalize_rejects_invalid_temp_only_recovery_precisely(self) -> None:
        with self.temporary_directory() as raw:
            root = Path(raw)
            cityjson, _report, _references = self.synthetic_fixture(root)
            full_state = self.full_state_fixture(
                root / "train", "04b", 1001, completed_steps=score.MAX_ITER
            )
            marker, merged = self.roofer_marker_fixture(
                root / "roofer", "04b", 1001, cityjson, full_state
            )
            marker_payload = json.loads(marker.read_text(encoding="utf-8"))
            prepare_path = self.repo_path(marker_payload["prepare_receipt"]["path"])
            execution_path = self.repo_path(
                marker_payload["execution_receipt"]["path"]
            )
            temporary = merged.with_name(f".{merged.name}.tmp")
            marker.unlink()
            merged.unlink()
            temporary.write_text("{}\n", encoding="utf-8")
            with self.assertRaisesRegex(
                RuntimeError, "Roofer finalize recovery temporary validation failed"
            ):
                score.finalize_roofer(
                    prepare_path,
                    execution_path,
                    self.lock,
                    expected_condition="04b",
                    expected_seed=1001,
                )
            self.assertTrue(temporary.is_file())
            self.assertFalse(marker.exists())
            self.assertFalse(merged.exists())

    def test_v2_marker_rejects_raw_jsonseq_tamper_add_and_delete(self) -> None:
        for drift in ("tamper", "add", "delete"):
            with self.subTest(drift=drift), self.temporary_directory() as raw:
                root = Path(raw)
                cityjson, _report, _references = self.synthetic_fixture(root)
                full_state = self.full_state_fixture(
                    root / "train", "01", 1001, completed_steps=score.MAX_ITER
                )
                marker, merged = self.roofer_marker_fixture(
                    root / "roofer", "01", 1001, cityjson, full_state
                )
                marker_payload = json.loads(marker.read_text(encoding="utf-8"))
                raw_dir = self.repo_path(
                    marker_payload["raw_jsonseq"]["directory_path"]
                )
                raw_file = next(raw_dir.glob("*.city.jsonl"))
                if drift == "tamper":
                    raw_file.write_bytes(raw_file.read_bytes() + b"\n")
                    expected = "raw JSONSeq bundle"
                elif drift == "add":
                    shutil.copyfile(raw_file, raw_dir / "extra.city.jsonl")
                    expected = "duplicate raw CityObject IDs"
                else:
                    raw_file.unlink()
                    expected = "raw JSONSeq bundle is missing"
                with self.assertRaisesRegex(RuntimeError, expected):
                    score.validate_roofer_marker(
                        "01", 1001, marker, merged, self.lock
                    )

    def test_finalize_rejects_missing_extra_duplicate_and_orphan_raw_features(self) -> None:
        for drift in ("missing", "extra", "duplicate", "orphan"):
            with self.subTest(drift=drift), self.temporary_directory() as raw:
                root = Path(raw)
                cityjson, _report, _references = self.synthetic_fixture(root)
                full_state = self.full_state_fixture(
                    root / "train", "02", 1001, completed_steps=score.MAX_ITER
                )
                marker, merged = self.roofer_marker_fixture(
                    root / "roofer", "02", 1001, cityjson, full_state
                )
                marker_payload = json.loads(marker.read_text(encoding="utf-8"))
                prepare_path = self.repo_path(
                    marker_payload["prepare_receipt"]["path"]
                )
                execution_path = self.repo_path(
                    marker_payload["execution_receipt"]["path"]
                )
                raw_dir = self.repo_path(
                    marker_payload["raw_jsonseq"]["directory_path"]
                )
                raw_file = next(raw_dir.glob("*.city.jsonl"))
                marker.unlink()
                merged.unlink()
                if drift == "missing":
                    raw_file.unlink()
                    expected = "raw JSONSeq bundle is missing"
                elif drift == "extra":
                    shutil.copyfile(raw_file, raw_dir / "extra.city.jsonl")
                    expected = "duplicate raw CityObject IDs"
                else:
                    lines = raw_file.read_text(encoding="utf-8").splitlines()
                    if drift == "duplicate":
                        lines[-1] = lines[1]
                        expected = "duplicate raw CityObject IDs"
                    else:
                        feature = json.loads(lines[1])
                        feature["CityObjects"]["orphan-part"] = {
                            "type": "BuildingPart",
                            "geometry": [],
                        }
                        lines[1] = json.dumps(feature, separators=(",", ":"))
                        expected = "orphan child objects"
                    raw_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
                with self.assertRaisesRegex(RuntimeError, expected):
                    score.finalize_roofer(
                        prepare_path,
                        execution_path,
                        self.lock,
                        expected_condition="02",
                        expected_seed=1001,
                    )

    def test_finalize_preserves_one_uniquely_owned_child(self) -> None:
        with self.temporary_directory() as raw:
            root = Path(raw)
            cityjson, _report, _references = self.synthetic_fixture(root)
            full_state = self.full_state_fixture(
                root / "train", "03", 1002, completed_steps=score.MAX_ITER
            )
            marker, merged = self.roofer_marker_fixture(
                root / "roofer", "03", 1002, cityjson, full_state
            )
            marker_payload = json.loads(marker.read_text(encoding="utf-8"))
            prepare_path = self.repo_path(marker_payload["prepare_receipt"]["path"])
            execution_path = self.repo_path(
                marker_payload["execution_receipt"]["path"]
            )
            raw_dir = self.repo_path(marker_payload["raw_jsonseq"]["directory_path"])
            raw_file = next(raw_dir.glob("*.city.jsonl"))
            marker.unlink()
            merged.unlink()
            lines = raw_file.read_text(encoding="utf-8").splitlines()
            feature = json.loads(lines[1])
            root_id = feature["id"]
            child_id = root_id + "-part"
            feature["CityObjects"][root_id]["children"] = [child_id]
            feature["CityObjects"][child_id] = {
                "type": "BuildingPart",
                "parents": [root_id],
                "geometry": [],
            }
            lines[1] = json.dumps(feature, separators=(",", ":"))
            raw_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
            merged, state = score.finalize_roofer(
                prepare_path,
                execution_path,
                self.lock,
                expected_condition="03",
                expected_seed=1002,
            )
            self.assertEqual(state["raw_jsonseq"]["child_count"], 1)
            self.assertEqual(state["merged_cityjson"]["child_count"], 1)
            score.validate_roofer_marker(
                "03", 1002, merged.parent / "roofer_invocation.json", merged, self.lock
            )

    def test_roofer_recipe_and_locked_footprints(self) -> None:
        with self.temporary_directory() as raw:
            root = Path(raw)
            roofprints = root / "locked.geojson"
            record = score.materialize_locked_roofprints(self.lock, roofprints)
            payload = json.loads(roofprints.read_text(encoding="utf-8"))
            self.assertEqual(record["feature_count"], 30)
            self.assertEqual(len(record["feature_properties"]), 30)
            self.assertRegex(record["ordered_feature_geometry_sha256"], r"^[0-9a-f]{64}$")
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
            argv = score.roofer_argv_payload(
                "01", 1001, pointcloud, command_roofprints, output
            )
            command = argv["arguments"]
            self.assertEqual(argv["image"], score.ROOFER_IMAGE)
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
