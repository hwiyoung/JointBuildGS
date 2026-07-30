#!/usr/bin/env python3
from __future__ import annotations

import ast
import copy
import csv
import hashlib
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
SCRIPT = (
    REPO
    / "phases/p2-gsjso/scripts/fusion_w1/fusion_w1_aprime_p0prime_20260726.py"
)
CONFIG = (
    REPO
    / "phases/p2-gsjso/configs/fusion_w1/fusion_w1_aprime_p0prime_20260726.json"
)
WRAPPER = (
    REPO
    / "phases/p2-gsjso/scripts/fusion_w1/run_fusion_w1_aprime_p0prime_20260726.sh"
)


def load_module():
    spec = importlib.util.spec_from_file_location(
        "fusion_w1_aprime_p0prime_tested", SCRIPT
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FusionW1AprimeP0PrimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = load_module()
        cls.config = json.loads(CONFIG.read_text(encoding="utf-8"))
        cls.source = SCRIPT.read_text(encoding="utf-8")
        cls.wrapper = WRAPPER.read_text(encoding="utf-8")

    def target(self):
        return {
            "aprime_order": "1",
            "processing_order": "1",
            "building_id": "DEBY_LOD2_42364609",
            "target_role": "dim_failure",
            "tier": "height",
            "cohort": "core",
        }

    def valid_payload(self):
        return {
            "schema": "jointbuildgs.fusion_w1_aprime.preprocess_building.v1",
            "status": "PASSED",
            "building": {
                "aprime_order": 1,
                "building_id": "DEBY_LOD2_42364609",
                "target_role": "dim_failure",
                "tier": "height",
                "cohort": "core",
            },
            "pose_binding": {
                "corrected_images_sha256": (
                    "28b38383a0b6d82656108e8f0e5e79711dcda93948ab2e89c1cd8f47215962a5"
                ),
                "transform_application_count": 1,
                "additional_transform_application_count": 0,
            },
            "target_binding": {
                "sha256": self.config["targets"]["sha256"],
                "machine_join_verified": True,
                "manual_id_entry": False,
            },
            "seed": {
                "filtered_points_n": 4,
                "classification_counts": {"6": 4},
                "class2_rows_n": 0,
                "sfm_rows_n": 0,
                "downsample_applied": False,
                "seed_too_small": True,
                "base_las": {
                    "path": "new_cache/seed.las",
                    "sha256": "a" * 64,
                    "crs": "EPSG:25832",
                },
            },
            "ground_readout_only": {
                "points_n": 3,
                "classification_counts": {"2": 3},
                "coordinate_rows_unaltered": True,
                "source_row_order_preserved": False,
                "row_order_note": "ALS tile access is deterministically x-sorted",
                "downsample_applied": False,
                "trainer_path_reference": False,
                "role": "P0prime_and_readout_join_only_never_trainer",
                "base_las": {
                    "path": "new_cache/ground.las",
                    "sha256": "b" * 64,
                    "crs": "EPSG:25832",
                },
            },
            "publication": {
                "learning_runs_started": 0,
                "readout_runs_started": 0,
                "roofer_runs_started": 0,
                "scoring_runs_started": 0,
            },
        }

    def test_lock_is_learning_zero_and_observational(self):
        config = self.module.load_config(CONFIG)
        self.assertEqual(config["score_contract"]["learning_runs_started"], 0)
        self.assertEqual(config["score_contract"]["new_inference_runs"], 0)
        self.assertIsNone(config["score_contract"]["interpretation_or_verdict"])
        self.assertEqual(
            config["score_contract"]["baseline_role"],
            "P0prime_Aprime_seed_only_learning_zero",
        )

    def test_targets_are_machine_joined_nine_and_adapter_is_stable(self):
        rows = self.module.target_rows(self.config)
        self.assertEqual(len(rows), 9)
        self.assertEqual(rows[0]["building_id"], "DEBY_LOD2_42364609")
        self.assertEqual(rows[-1]["building_id"], "DEBY_LOD2_4908023")
        self.assertEqual([int(row["processing_order"]) for row in rows], list(range(1, 10)))
        self.assertTrue(self.config["targets"]["manual_id_entry_forbidden"])

    def test_building_contract_accepts_small_seed_and_separate_ground(self):
        result = self.module.validate_building_payload(
            self.valid_payload(), config=self.config, target=self.target()
        )
        self.assertEqual(result["seed_n"], 4)
        self.assertEqual(result["ground_n"], 3)
        self.assertTrue(result["seed_too_small"])
        self.assertEqual(result["seed_record"]["crs"], "EPSG:25832")
        self.assertFalse(
            self.valid_payload()["ground_readout_only"]["trainer_path_reference"]
        )

    def test_building_contract_rejects_seed_contamination_and_ground_mutation(self):
        contaminated = self.valid_payload()
        contaminated["seed"]["class2_rows_n"] = 1
        with self.assertRaises(self.module.AprimeP0PrimeError):
            self.module.validate_building_payload(
                contaminated, config=self.config, target=self.target()
            )
        moved = self.valid_payload()
        moved["ground_readout_only"]["coordinate_rows_unaltered"] = False
        with self.assertRaises(self.module.AprimeP0PrimeError):
            self.module.validate_building_payload(
                moved, config=self.config, target=self.target()
            )
        trainer_leak = self.valid_payload()
        trainer_leak["ground_readout_only"]["trainer_path_reference"] = True
        with self.assertRaises(self.module.AprimeP0PrimeError):
            self.module.validate_building_payload(
                trainer_leak, config=self.config, target=self.target()
            )

    def test_building_contract_rejects_nonzero_preprocess_run_counters(self):
        payload = self.valid_payload()
        payload["publication"]["readout_runs_started"] = 1
        with self.assertRaises(self.module.AprimeP0PrimeError):
            self.module.validate_building_payload(
                payload, config=self.config, target=self.target()
            )

    def test_only_new_aprime_stable_manifest_resolves_inputs(self):
        stable = self.config["preprocess_consumer"]["stable_run_manifest"]
        self.assertEqual(
            stable,
            "phases/p2-gsjso/runs/fusion_w1/20260726_fusion_w1_aprime/"
            "preprocess_aprime/preprocess_manifest.json",
        )
        forbidden = self.config["preprocess_consumer"][
            "old_arm_a_inputs_forbidden"
        ]
        self.assertIn(
            "phases/p2-gsjso/runs/fusion_w1/20260724_fusion_w1/p0prime", forbidden
        )
        self.assertIn("_forbid_old_input(config, path)", self.source)

    def test_synthetic_stable_manifest_index_resolution(self):
        with tempfile.TemporaryDirectory() as directory:
            temporary_repo = Path(directory)
            namespace = self.config["preprocess_consumer"][
                "required_cache_namespace"
            ]
            stable_root = temporary_repo / "preprocess_aprime"
            cache = stable_root / namespace
            building_root = cache / "by_building/DEBY_LOD2_42364609"
            building_root.mkdir(parents=True)
            manifest = building_root / "preprocess_manifest.json"
            manifest.write_text("{}\n", encoding="utf-8")
            manifest_sha = hashlib.sha256(manifest.read_bytes()).hexdigest()
            index = cache / "preprocess_index.csv"
            with index.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(
                    handle,
                    fieldnames=[
                        "aprime_order",
                        "building_id",
                        "status",
                        "building_manifest_path",
                        "building_manifest_sha256",
                    ],
                )
                writer.writeheader()
                writer.writerow(
                    {
                        "aprime_order": 1,
                        "building_id": "DEBY_LOD2_42364609",
                        "status": "PASSED",
                        "building_manifest_path": str(
                            manifest.relative_to(temporary_repo)
                        ),
                        "building_manifest_sha256": manifest_sha,
                    }
                )
            index_sha = hashlib.sha256(index.read_bytes()).hexdigest()
            stable = stable_root / "preprocess_manifest.json"
            stable.write_text(
                json.dumps(
                    {
                        "schema": self.config["preprocess_consumer"][
                            "run_schema"
                        ],
                        "status": "PARTIAL",
                        "target_binding": {
                            "sha256": self.config["targets"]["sha256"],
                            "population_n": 9,
                        },
                        "pose_binding": {
                            "corrected_images_sha256": self.config[
                                "preprocess_consumer"
                            ]["required_pose_sha256"],
                            "transform_application_count": 1,
                            "additional_transform_application_count": 0,
                        },
                        "cache_binding": {
                            "namespace": namespace,
                            "cache_dir": str(cache.relative_to(temporary_repo)),
                        },
                        "preprocess_index": {
                            "path": str(index.relative_to(temporary_repo)),
                            "sha256": index_sha,
                        },
                        "buildings": [
                            {
                                "building_id": "DEBY_LOD2_42364609",
                                "building_manifest_path": str(
                                    manifest.relative_to(temporary_repo)
                                ),
                                "building_manifest_sha256": manifest_sha,
                            }
                        ],
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            config = copy.deepcopy(self.config)
            config["preprocess_consumer"]["stable_run_manifest"] = str(
                stable.relative_to(temporary_repo)
            )
            config["preprocess_consumer"]["old_arm_a_inputs_forbidden"] = [
                "old_arm_a"
            ]
            original_repo = self.module.REPO
            self.module.REPO = temporary_repo
            try:
                result = self.module.preprocess_resolution(
                    config, "DEBY_LOD2_42364609"
                )
            finally:
                self.module.REPO = original_repo
        self.assertEqual(result["cache_namespace"], namespace)
        self.assertEqual(result["manifest_sha256"], manifest_sha)

    def _write_las(self, path, xyz, classification, rgb, intensity, offset):
        import laspy
        import numpy as np
        from pyproj import CRS

        header = laspy.LasHeader(point_format=3, version="1.4")
        header.scales = np.asarray([0.001, 0.001, 0.001])
        header.offsets = np.asarray(offset, dtype=np.float64)
        header.add_crs(CRS.from_epsg(25832))
        las = laspy.LasData(header)
        values = np.asarray(xyz, dtype=np.float64)
        las.x, las.y, las.z = values[:, 0], values[:, 1], values[:, 2]
        las.classification = np.asarray(classification, dtype=np.uint8)
        colors = np.asarray(rgb, dtype=np.uint16)
        las.red, las.green, las.blue = colors[:, 0], colors[:, 1], colors[:, 2]
        las.intensity = np.asarray(intensity, dtype=np.uint16)
        las.gps_time = np.arange(len(values), dtype=np.float64) + 100.0
        las.write(path)

    def test_semantic_row_exact_class6_then_class2_join(self):
        import laspy
        import numpy as np

        with tempfile.TemporaryDirectory() as directory:
            temporary_repo = Path(directory)
            seed = temporary_repo / "seed.las"
            ground = temporary_repo / "ground.las"
            output = temporary_repo / "joined.las"
            seed_xyz = np.asarray(
                [[690001.123, 5336001.456, 50.789], [690002.222, 5336002.333, 51.444]]
            )
            ground_xyz = np.asarray(
                [[689999.111, 5335999.222, 40.333], [690000.555, 5336000.666, 40.777]]
            )
            self._write_las(
                seed,
                seed_xyz,
                [6, 6],
                [[100, 200, 300], [400, 500, 600]],
                [11, 12],
                [690001.0, 5336001.0, 50.0],
            )
            self._write_las(
                ground,
                ground_xyz,
                [2, 2],
                [[700, 800, 900], [1000, 1100, 1200]],
                [21, 22],
                [689999.0, 5335999.0, 40.0],
            )
            original_repo = self.module.REPO
            self.module.REPO = temporary_repo
            try:
                receipt = self.module.join_source_lases(
                    seed,
                    ground,
                    output,
                    seed_n=2,
                    ground_n=2,
                    config=self.config,
                )
            finally:
                self.module.REPO = original_repo
            joined = laspy.read(output)
        self.assertEqual(receipt["source_rows_n"], {"6": 2, "2": 2})
        self.assertEqual(receipt["source_semantic_rows_sha256"], receipt["output_semantic_rows_sha256"])
        self.assertTrue(receipt["semantic_row_digest_equal"])
        self.assertLessEqual(receipt["maximum_coordinate_difference_m"], 1e-9)
        self.assertEqual(list(np.asarray(joined.classification)), [6, 6, 2, 2])
        self.assertEqual(list(np.asarray(joined.intensity)), [11, 12, 21, 22])
        self.assertTrue(
            np.array_equal(
                np.asarray(joined.red),
                np.asarray([100, 400, 700, 1000], dtype=np.uint16),
            )
        )

    def test_roofer_defaults_and_classes_are_explicit(self):
        roofer = self.config["roofer"]
        self.assertTrue(roofer["default_reconstruction_parameters_preserved"])
        self.assertEqual(roofer["reconstruction_parameter_overrides"], [])
        parameters = roofer["parameters"]
        self.assertIn("--bld-class", parameters)
        self.assertEqual(parameters[parameters.index("--bld-class") + 1], "6")
        self.assertIn("--grnd-class", parameters)
        self.assertEqual(parameters[parameters.index("--grnd-class") + 1], "2")
        self.assertIn("--lod22", parameters)
        self.assertIsNone(roofer["timeout_seconds_per_building"])

    def test_wrapper_is_docker_only_serial_and_writes_partial_failures(self):
        self.assertIn("docker run --rm", self.wrapper)
        self.assertIn("--network=none", self.wrapper)
        self.assertIn("flock -n", self.wrapper)
        self.assertIn("record_external_failure", self.wrapper)
        self.assertNotIn("timeout --signal", self.wrapper)
        self.assertNotIn("conda", self.wrapper)
        tree = ast.parse(self.source)
        called = {
            node.func.id
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        }
        self.assertNotIn("train", called)

    def test_outputs_are_only_under_aprime_preflight_t3(self):
        output_values = json.dumps(self.config["outputs"], sort_keys=True)
        self.assertIn("20260726_fusion_w1_aprime/preflight/T3", output_values)
        self.assertNotIn("20260724_fusion_w1", output_values)

    def test_execution_engine_reuse_excludes_old_numeric_results(self):
        record = self.config["canonical_helpers"]["p0prime_execution_engine"]
        self.assertEqual(
            record["reuse_scope"],
            "Roofer_CityJSON_val3dity_metric_and_incremental_publication_conventions_only",
        )
        self.assertFalse(record["old_preprocess_or_old_p0prime_result_consumption"])
        assumptions = " ".join(self.config["input_schema_assumptions"])
        self.assertIn("No old arm-A", assumptions)


if __name__ == "__main__":
    unittest.main()
