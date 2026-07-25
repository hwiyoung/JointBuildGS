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


REPO = Path(__file__).resolve().parents[3]
SCRIPT = (
    REPO
    / "phases/p2-gsjso/scripts/fusion_w1_seed_p0prime_20260725.py"
)
CONFIG = (
    REPO
    / "phases/p2-gsjso/configs/fusion_w1_seed_p0prime_20260725.json"
)
WRAPPER = (
    REPO
    / "phases/p2-gsjso/scripts/run_fusion_w1_seed_p0prime_20260725.sh"
)


def load_module():
    spec = importlib.util.spec_from_file_location("fusion_w1_seed_p0prime", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FusionW1SeedP0PrimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = load_module()
        cls.config = json.loads(CONFIG.read_text(encoding="utf-8"))
        cls.source = SCRIPT.read_text(encoding="utf-8")
        cls.wrapper = WRAPPER.read_text(encoding="utf-8")

    def valid_preprocess_payload(self):
        return {
            "schema": "jointbuildgs.fusion_w1.preprocess_building.v1",
            "status": "PASSED",
            "building": {
                "building_id": "DEBY_LOD2_123",
                "processing_order": 7,
                "tier": "height",
                "cohort": "core",
            },
            "seed": {
                "source_points_n": 15,
                "output_points_n": 15,
                "downsample_applied": False,
                "classification_counts": {"2": 10, "6": 5},
                "base_las": {
                    "path": (
                        "phases/p2-gsjso/runs/20260724_fusion_w1/"
                        "preprocess_v1/cache/by_building/DEBY_LOD2_123/"
                        "seed_epsg25832.las"
                    ),
                    "sha256": "a" * 64,
                    "crs": "EPSG:25832",
                    "vertical_datum": "orthometric",
                },
            },
        }

    def target(self):
        return {
            "building_id": "DEBY_LOD2_123",
            "processing_order": "7",
            "tier": "height",
            "cohort": "core",
        }

    def test_preprocess_resolver_is_stable_manifest_only(self):
        consumer = self.config["preprocess_consumer"]
        self.assertEqual(
            consumer["run_manifest"],
            "phases/p2-gsjso/runs/20260724_fusion_w1/"
            "preprocess_v1/preprocess_manifest.json",
        )
        serialized = json.dumps(self.config, ensure_ascii=False)
        self.assertNotIn("pose_28b38383a0b6d826", serialized)
        self.assertIn("building_manifest_path", consumer["index_required_columns"])
        self.assertIn("preprocess_resolution(config, building_id)", self.source)

    def test_stable_manifest_index_resolves_building_manifest(self):
        with tempfile.TemporaryDirectory() as directory:
            temporary_repo = Path(directory)
            cache = temporary_repo / "preprocess_v1/pose_test"
            by_building = cache / "by_building/DEBY_LOD2_123"
            by_building.mkdir(parents=True)
            building_manifest = by_building / "preprocess_manifest.json"
            building_manifest.write_text(
                json.dumps(self.valid_preprocess_payload()) + "\n",
                encoding="utf-8",
            )
            building_sha = hashlib.sha256(
                building_manifest.read_bytes()
            ).hexdigest()
            cache_run = cache / "preprocess_run_manifest.json"
            cache_run.write_text(
                json.dumps(
                    {
                        "schema": "jointbuildgs.fusion_w1.preprocess_run.v1",
                        "status": "PARTIAL",
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            index = cache / "preprocess_index.csv"
            fields = self.config["preprocess_consumer"][
                "index_required_columns"
            ]
            with index.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=fields)
                writer.writeheader()
                writer.writerow(
                    {
                        "processing_order": 7,
                        "building_id": "DEBY_LOD2_123",
                        "tier": "height",
                        "cohort": "core",
                        "status": "PASSED",
                        "data_root": "unused",
                        "building_manifest_path": str(
                            building_manifest.relative_to(temporary_repo)
                        ),
                        "building_manifest_sha256": building_sha,
                        "views_n": 10,
                        "seed_points_n": 15,
                        "class2_n": 10,
                        "class6_n": 5,
                        "pose_sha256": "b" * 64,
                    }
                )
            stable = temporary_repo / "preprocess_v1/preprocess_manifest.json"
            stable.parent.mkdir(parents=True, exist_ok=True)
            stable.write_text(
                json.dumps(
                    {
                        "schema": "jointbuildgs.fusion_w1.preprocess_run.v1",
                        "status": "PARTIAL",
                        "cache_binding": {
                            "namespace": "pose_test",
                            "cache_dir": str(cache.relative_to(temporary_repo)),
                            "cache_run_manifest": {
                                "path": str(cache_run.relative_to(temporary_repo)),
                                "sha256": hashlib.sha256(
                                    cache_run.read_bytes()
                                ).hexdigest(),
                            },
                            "preprocess_index": {
                                "path": str(index.relative_to(temporary_repo)),
                                "sha256": hashlib.sha256(
                                    index.read_bytes()
                                ).hexdigest(),
                            },
                        },
                        "buildings": [
                            {
                                "building_id": "DEBY_LOD2_123",
                                "building_manifest_path": str(
                                    building_manifest.relative_to(temporary_repo)
                                ),
                                "building_manifest_sha256": building_sha,
                            }
                        ],
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            config = copy.deepcopy(self.config)
            config["preprocess_consumer"]["run_manifest"] = str(
                stable.relative_to(temporary_repo)
            )
            original_repo = self.module.REPO
            self.module.REPO = temporary_repo
            try:
                result = self.module.preprocess_resolution(
                    config, "DEBY_LOD2_123"
                )
            finally:
                self.module.REPO = original_repo
            self.assertEqual(result["cache_namespace"], "pose_test")
            self.assertEqual(result["building_manifest_path"], building_manifest)

    def test_preprocess_payload_accepts_exact_class_2_6_passthrough(self):
        result = self.module.validate_preprocess_payload(
            self.valid_preprocess_payload(),
            expected_building_id="DEBY_LOD2_123",
            expected_target=self.target(),
            config=self.config,
        )
        self.assertEqual(result["declared_class_counts"], {"2": 10, "6": 5})
        self.assertEqual(result["source_points_n"], result["output_points_n"])

    def test_preprocess_payload_rejects_downsample_or_extra_class(self):
        downsampled = self.valid_preprocess_payload()
        downsampled["seed"]["downsample_applied"] = True
        with self.assertRaises(self.module.P0PrimeError):
            self.module.validate_preprocess_payload(
                downsampled,
                expected_building_id="DEBY_LOD2_123",
                expected_target=self.target(),
                config=self.config,
            )
        extra = self.valid_preprocess_payload()
        extra["seed"]["classification_counts"] = {"1": 1, "2": 9, "6": 5}
        with self.assertRaises(self.module.P0PrimeError):
            self.module.validate_preprocess_payload(
                extra,
                expected_building_id="DEBY_LOD2_123",
                expected_target=self.target(),
                config=self.config,
            )

    def test_classification_is_nonmutating_passthrough(self):
        consumer = self.config["preprocess_consumer"]
        self.assertEqual(
            consumer["classification_stage"],
            "validated_preclassified_passthrough",
        )
        self.assertFalse(consumer["classification_mutates_geometry_or_classes"])
        tree = ast.parse(self.source)
        commands = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.List):
                continue
            values = [
                item.value
                for item in node.elts
                if isinstance(item, ast.Constant) and isinstance(item.value, str)
            ]
            commands.extend(values)
        self.assertNotIn("pdal", commands)
        self.assertNotIn("filters.smrf", self.source)

    def test_synthetic_las_14_point_format_3_rgb_class_2_6(self):
        import laspy
        import numpy as np
        from pyproj import CRS

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "seed_epsg25832.las"
            header = laspy.LasHeader(point_format=3, version="1.4")
            header.scales = np.array([0.001, 0.001, 0.001])
            header.offsets = np.array([690000.0, 5336000.0, 40.0])
            header.add_crs(CRS.from_epsg(25832))
            las = laspy.LasData(header)
            las.x = np.array([690001.0, 690002.0])
            las.y = np.array([5336001.0, 5336002.0])
            las.z = np.array([40.0, 45.0])
            las.classification = np.array([2, 6], dtype=np.uint8)
            las.red = np.array([1, 2], dtype=np.uint16)
            las.green = np.array([3, 4], dtype=np.uint16)
            las.blue = np.array([5, 6], dtype=np.uint16)
            las.write(path)
            observed = self.module.inspect_las(path)
        self.assertEqual(observed["version"], "1.4")
        self.assertEqual(observed["point_format"], 3)
        self.assertEqual(observed["epsg"], 25832)
        self.assertEqual(observed["class_counts"], {"2": 1, "6": 1})
        self.assertTrue(
            {"red", "green", "blue"}.issubset(observed["dimensions"])
        )

    def test_assembly_is_independent_from_val3dity(self):
        feature = {
            "attributes": {
                "rf_success": True,
                "rf_pointcloud_unusable": False,
                "rf_extrusion_mode": "standard",
            },
            "has_lod22": True,
        }
        flags = self.module.assembly_flags(
            feature,
            val3dity_feature={"id": "DEBY_LOD2_123", "validity": False},
        )
        self.assertTrue(flags["assembly_lod2_success"])
        self.assertFalse(flags["val3dity_valid"])
        self.assertIn("assembly_lod2_success", self.module.SCORE_FIELDS)
        self.assertIn("val3dity_valid", self.module.SCORE_FIELDS)

    def test_fallback_is_not_lod2_assembly_even_when_val3dity_valid(self):
        feature = {
            "attributes": {
                "rf_success": True,
                "rf_pointcloud_unusable": False,
                "rf_extrusion_mode": "lod11_fallback",
            },
            "has_lod22": False,
        }
        flags = self.module.assembly_flags(
            feature,
            val3dity_feature={"validity": True},
        )
        self.assertFalse(flags["assembly_lod2_success"])
        self.assertTrue(flags["lod1_fallback"])
        self.assertTrue(flags["val3dity_valid"])

    def test_plane_f1_contract(self):
        self.assertAlmostEqual(self.module.plane_f1(0.5, 1.0), 2.0 / 3.0)
        self.assertEqual(self.module.plane_f1(0.0, 0.0), 0.0)
        self.assertIsNone(self.module.plane_f1(None, 1.0))

    def test_roofer_command_is_canonical_and_outer_serial(self):
        self.assertEqual(
            self.config["roofer"]["image"],
            "3dgi/roofer@sha256:"
            "dd2c415aaee337502bde0dc1426dfa9c9f88e648f9d2f6340110c49932c251d2",
        )
        self.assertEqual(self.config["roofer"]["outer_parallelism"], 1)
        self.assertEqual(
            self.config["roofer"]["parameters"],
            [
                "--id-attribute",
                "building_id",
                "--jobs",
                "3",
                "--srs",
                "EPSG:25832",
                "--bld-class",
                "6",
                "--grnd-class",
                "2",
                "--lod22",
            ],
        )
        argv = self.module.roofer_argv(
            self.config,
            classified_las="seed.las",
            footprint="footprint.gpkg",
            output_dir="roofer",
        )
        self.assertEqual(argv[-3:], ["seed.las", "footprint.gpkg", "roofer"])

    def test_wrapper_applies_24g_to_tools_and_roofer_and_runs_serially(self):
        self.assertIn('MEMORY="24g"', self.wrapper)
        self.assertGreaterEqual(self.wrapper.count('--memory="$MEMORY"'), 2)
        self.assertGreaterEqual(self.wrapper.count('--memory-swap="$MEMORY"'), 2)
        self.assertIn('for building_id in "${pending[@]}"; do', self.wrapper)
        self.assertNotIn("xargs -P", self.wrapper)
        self.assertNotIn("parallel ", self.wrapper)

    def test_process_guard_does_not_match_this_wrapper(self):
        guard_line = next(
            line.strip()
            for line in self.wrapper.splitlines()
            if line.strip().startswith("pattern=")
        )
        for own_token in (
            "fusion_w1_seed_p0prime",
            "run_fusion_w1_seed_p0prime",
            "test_fusion_w1_seed_p0prime",
        ):
            self.assertNotIn(own_token, guard_line)
        self.assertIn("train.py", guard_line)
        self.assertIn("fusion_w1_training_v1_20260725.py", guard_line)
        self.assertIn("fusion_w1_preprocess_v1_20260725.py", guard_line)
        self.assertIn("pilot_1wave_postprocess_driver", guard_line)

    def test_retry_is_fail_closed_after_any_started_claim(self):
        self.assertIn('exclusive_json(\n        claim,', self.source)
        self.assertIn(
            'exclusive_json(job / "roofer_invocation.json", invocation)',
            self.source,
        )
        self.assertIn(
            'exclusive_json(\n        score_started,',
            self.source,
        )
        self.assertIn('if not (job / "start.json").exists():', self.source)
        self.assertIn(
            'run_tools "$SCRIPT" --config "$CONFIG" list-pending',
            self.wrapper,
        )
        self.assertNotIn("rm -f", self.wrapper)
        self.assertNotIn("rm -rf", self.wrapper)

    def test_canonical_helpers_are_hash_pinned(self):
        for record in self.config["canonical_helpers"].values():
            path = REPO / record["path"]
            self.assertEqual(self.module.sha256_file(path), record["sha256"])
        for value, expected in self.config["reference"]["locked_files"].items():
            self.assertEqual(
                self.module.sha256_file(REPO / value),
                expected,
            )

    def test_static_inputs_include_178_of_178_p0_refl_lod2(self):
        observed = self.module.verify_static_inputs(self.config)
        baseline = self.config["p0_refl_baseline"]
        self.assertEqual(
            observed[baseline["path"]],
            baseline["sha256"],
        )
        self.assertEqual(baseline["expected_population"], 178)
        self.assertEqual(baseline["expected_lod2_count"], 178)

    def test_incremental_csv_precedes_per_building_complete_receipt(self):
        upsert = self.source.index("upsert_score_row(config, row)")
        complete = self.source.index(
            'exclusive_json(job / "complete.json", complete)'
        )
        self.assertLess(upsert, complete)
        self.assertTrue(
            self.config["publication"][
                "per_building_complete_receipt_written_after_scores_csv"
            ]
        )

    def test_final_manifest_is_last_publication_write(self):
        start = self.source.index("def finalize(")
        section = self.source[start : self.source.index("def parser()", start)]
        progress = section.index(
            'update_progress(config, "finalize_pre_manifest")'
        )
        manifest = section.index(
            'exclusive_json(paths["final_manifest"], manifest)'
        )
        self.assertLess(progress, manifest)
        self.assertNotIn("atomic_json(", section[manifest:])

    def test_exact_once_claim_rejects_second_writer(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "start.json"
            self.module.exclusive_json(path, {"state": "STARTED"})
            with self.assertRaises(FileExistsError):
                self.module.exclusive_json(path, {"state": "STARTED"})

    def test_no_learning_and_no_issues_mutation(self):
        self.assertEqual(
            self.config["score_contract"]["learning_runs_started"], 0
        )
        self.assertEqual(
            self.config["score_contract"]["new_inference_runs"], 0
        )
        self.assertNotIn("issues.md", json.dumps(self.config["outputs"]))
        self.assertNotIn("issues.md", self.wrapper)


if __name__ == "__main__":
    unittest.main()
