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
from types import SimpleNamespace
from unittest import mock


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

    def test_panel_one_renders_four_panel_receipt_without_mutating_inputs(self):
        import laspy
        import numpy as np
        from PIL import Image
        from pyproj import CRS
        from shapely.geometry import Polygon

        building_id = "DEBY_LOD2_123"

        def write_json(path, payload):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps(payload, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            return hashlib.sha256(path.read_bytes()).hexdigest()

        with tempfile.TemporaryDirectory() as directory:
            temporary_repo = Path(directory)

            targets = temporary_repo / "targets.csv"
            with targets.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(
                    handle,
                    fieldnames=(
                        "building_id",
                        "processing_order",
                        "tier",
                        "cohort",
                    ),
                )
                writer.writeheader()
                writer.writerow(
                    {
                        "building_id": building_id,
                        "processing_order": 1,
                        "tier": "height",
                        "cohort": "core",
                    }
                )

            data_root_rel = f"preprocess/by_building/{building_id}"
            data_root = temporary_repo / data_root_rel
            image_rel = f"{data_root_rel}/images/view.png"
            image_path = temporary_repo / image_rel
            image_path.parent.mkdir(parents=True)
            pixels = np.zeros((64, 80, 3), dtype=np.uint8)
            pixels[..., 1] = np.arange(80, dtype=np.uint8)[None, :]
            pixels[..., 2] = 120
            Image.fromarray(pixels).save(image_path)

            mask_rel = f"{data_root_rel}/photo_support_masks/view.npy"
            mask_path = temporary_repo / mask_rel
            mask_path.parent.mkdir(parents=True)
            mask = np.zeros((64, 80), dtype=bool)
            mask[20:45, 30:60] = True
            np.save(mask_path, mask, allow_pickle=False)

            index_rel = f"{data_root_rel}/supervision_index.csv"
            index_path = temporary_repo / index_rel
            with index_path.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(
                    handle,
                    fieldnames=(
                        "selection_order",
                        "building_id",
                        "image_name",
                        "photo_support_mask_path",
                        "photo_support_valid_pixels_n",
                    ),
                )
                writer.writeheader()
                writer.writerow(
                    {
                        "selection_order": 1,
                        "building_id": building_id,
                        "image_name": "view.png",
                        "photo_support_mask_path": mask_rel,
                        "photo_support_valid_pixels_n": int(mask.sum()),
                    }
                )

            seed_rel = f"{data_root_rel}/seed_epsg25832.las"
            seed_path = temporary_repo / seed_rel
            header = laspy.LasHeader(point_format=3, version="1.4")
            header.scales = np.array([0.001, 0.001, 0.001])
            header.offsets = np.array([690000.0, 5336000.0, 40.0])
            header.add_crs(CRS.from_epsg(25832))
            las = laspy.LasData(header)
            las.x = np.array(
                [690001.0, 690002.0, 690003.0, 690004.0, 690005.0, 690006.0]
            )
            las.y = np.array(
                [5336001.0, 5336002.0, 5336003.0, 5336001.5, 5336002.5, 5336003.5]
            )
            las.z = np.array([40.0, 40.1, 40.2, 45.0, 45.1, 45.2])
            las.classification = np.array([2, 2, 2, 6, 6, 6], dtype=np.uint8)
            las.red = np.arange(1, 7, dtype=np.uint16)
            las.green = np.arange(11, 17, dtype=np.uint16)
            las.blue = np.arange(21, 27, dtype=np.uint16)
            las.write(seed_path)

            preprocess_rel = f"{data_root_rel}/preprocess_manifest.json"
            preprocess_path = temporary_repo / preprocess_rel
            preprocess_sha = write_json(
                preprocess_path,
                {
                    "schema": "jointbuildgs.fusion_w1.preprocess_building.v1",
                    "status": "PASSED",
                    "building": {"building_id": building_id},
                    "data_root": data_root_rel,
                    "supervision": {
                        "index": {
                            "path": index_rel,
                            "sha256": hashlib.sha256(
                                index_path.read_bytes()
                            ).hexdigest(),
                        }
                    },
                    "artifact_sha256": {
                        image_rel: hashlib.sha256(image_path.read_bytes()).hexdigest(),
                        mask_rel: hashlib.sha256(mask_path.read_bytes()).hexdigest(),
                    },
                },
            )

            job_rel = f"run/p0prime/by_building/{building_id}"
            job = temporary_repo / job_rel
            job.mkdir(parents=True)
            classification_path = job / "classification_receipt.json"
            write_json(
                classification_path,
                {
                    "schema": (
                        "jointbuildgs.fusion_w1.seed_p0prime."
                        "classification_receipt.v1"
                    ),
                    "state": "PASSED",
                    "building_id": building_id,
                    "preprocess_manifest": {
                        "path": preprocess_rel,
                        "sha256": preprocess_sha,
                    },
                    "classified_seed_las": {
                        "path": seed_rel,
                        "sha256": hashlib.sha256(seed_path.read_bytes()).hexdigest(),
                        "point_count": 6,
                        "class_counts": {"2": 3, "6": 3},
                    },
                },
            )

            invocation_rel = f"{job_rel}/roofer_invocation.json"
            invocation_path = temporary_repo / invocation_rel
            invocation_sha = write_json(
                invocation_path,
                {
                    "schema": (
                        "jointbuildgs.fusion_w1.seed_p0prime."
                        "roofer_invocation.v1"
                    ),
                    "state": "AUTHORIZED",
                    "building_id": building_id,
                },
            )
            jsonseq_rel = f"{job_rel}/roofer/output.city.jsonl"
            jsonseq_path = temporary_repo / jsonseq_rel
            jsonseq_path.parent.mkdir(parents=True)
            jsonseq_path.write_text("{}\n", encoding="utf-8")
            roofer_receipt_rel = f"{job_rel}/roofer_receipt.json"
            roofer_receipt_path = temporary_repo / roofer_receipt_rel
            roofer_receipt_sha = write_json(
                roofer_receipt_path,
                {
                    "schema": (
                        "jointbuildgs.fusion_w1.seed_p0prime."
                        "roofer_receipt.v1"
                    ),
                    "state": "COMPLETE",
                    "building_id": building_id,
                    "invocation": {
                        "path": invocation_rel,
                        "sha256": invocation_sha,
                    },
                    "jsonseq_outputs": [
                        {
                            "path": jsonseq_rel,
                            "sha256": hashlib.sha256(
                                jsonseq_path.read_bytes()
                            ).hexdigest(),
                        }
                    ],
                },
            )

            cityjson_rel = f"{job_rel}/cityjson/seed_p0prime.city.json"
            cityjson_path = temporary_repo / cityjson_rel
            write_json(cityjson_path, {"type": "CityJSON", "version": "2.0"})
            score_receipt_rel = f"{job_rel}/score_receipt.json"
            score_receipt_path = temporary_repo / score_receipt_rel
            score_receipt_sha = write_json(
                score_receipt_path,
                {
                    "schema": (
                        "jointbuildgs.fusion_w1.seed_p0prime."
                        "score_receipt.v1"
                    ),
                    "state": "MEASURED",
                    "building_id": building_id,
                    "row": {
                        "building_id": building_id,
                        "roofer_receipt": roofer_receipt_rel,
                        "roofer_receipt_sha256": roofer_receipt_sha,
                        "cityjson": cityjson_rel,
                        "cityjson_sha256": hashlib.sha256(
                            cityjson_path.read_bytes()
                        ).hexdigest(),
                    },
                },
            )
            complete_path = job / "complete.json"
            write_json(
                complete_path,
                {
                    "schema": self.module.BUILDING_RECEIPT_SCHEMA,
                    "state": "COMPLETE",
                    "building_id": building_id,
                    "score_receipt": {
                        "path": score_receipt_rel,
                        "sha256": score_receipt_sha,
                    },
                },
            )

            reference_rel = "reference/tile.gml"
            reference_path = temporary_repo / reference_rel
            reference_path.parent.mkdir(parents=True)
            reference_path.write_text("<CityModel/>\n", encoding="utf-8")

            config = copy.deepcopy(self.config)
            config["run_dir"] = "run"
            config["targets_csv"] = {
                "path": "targets.csv",
                "sha256": hashlib.sha256(targets.read_bytes()).hexdigest(),
                "id_field": "building_id",
                "order_field": "processing_order",
                "expected_population": 1,
            }
            config["outputs"]["building_dir_template"] = (
                "run/p0prime/by_building/{building_id}"
            )
            config["reference"]["lod2_dir"] = "reference"
            config["reference"]["locked_files"] = {
                reference_rel: hashlib.sha256(reference_path.read_bytes()).hexdigest()
            }

            prediction_surface = SimpleNamespace(
                polygon=Polygon(
                    [(690001.0, 5336001.0), (690006.0, 5336001.0),
                     (690006.0, 5336004.0), (690001.0, 5336004.0)]
                )
            )
            reference_surface = SimpleNamespace(
                polygon=Polygon(
                    [(690000.8, 5336000.8), (690006.2, 5336000.8),
                     (690006.2, 5336004.2), (690000.8, 5336004.2)]
                )
            )

            class FakeMetric:
                @staticmethod
                def parse_cityjson_roofs(_path, _ids):
                    return {building_id: [prediction_surface]}

                @staticmethod
                def parse_lod2_roofs(_path, _ids):
                    return {building_id: [reference_surface]}

            immutable_inputs = (
                image_path,
                mask_path,
                index_path,
                seed_path,
                jsonseq_path,
                cityjson_path,
                reference_path,
            )
            input_sha_before = {
                path: hashlib.sha256(path.read_bytes()).hexdigest()
                for path in immutable_inputs
            }
            original_repo = self.module.REPO
            self.module.REPO = temporary_repo
            try:
                with mock.patch.object(
                    self.module,
                    "load_helpers",
                    return_value=(object(), FakeMetric(), object()),
                ):
                    receipt = self.module.panel_one(config, building_id)
                    with self.assertRaises(self.module.P0PrimeError):
                        self.module.panel_one(config, building_id)
            finally:
                self.module.REPO = original_repo

            panel_path = (
                temporary_repo
                / "run/w1_panels"
                / f"{building_id}__p0prime.png"
            )
            receipt_path = panel_path.with_name(
                f"{building_id}__p0prime.receipt.json"
            )
            self.assertTrue(panel_path.is_file())
            self.assertTrue(receipt_path.is_file())
            self.assertEqual(receipt["state"], "COMPLETE")
            self.assertEqual(receipt["panel"]["panels_n"], 4)
            self.assertEqual(receipt["panel"]["sha256"], hashlib.sha256(
                panel_path.read_bytes()
            ).hexdigest())
            self.assertEqual(
                [value["index"] for value in receipt["panels"]],
                [1, 2, 3, 4],
            )
            self.assertTrue(
                receipt["roofer_output_frozen_before_reference_open"]
            )
            self.assertFalse(receipt["original_inputs_modified"])
            self.assertEqual(receipt["learning_runs_started"], 0)
            self.assertEqual(receipt["new_inference_runs"], 0)
            self.assertEqual(
                input_sha_before,
                {
                    path: hashlib.sha256(path.read_bytes()).hexdigest()
                    for path in immutable_inputs
                },
            )

    def test_panel_command_is_serial_guarded_and_not_head_pinned(self):
        parsed = self.module.parser().parse_args(
            ["panel-one", "--building-id", "DEBY_LOD2_123"]
        )
        self.assertEqual(parsed.command, "panel-one")
        self.assertIn('elif command == "panel-one":', self.source)
        self.assertIn("verify_git_runtime(config)", self.source)
        self.assertNotIn("45bce93", self.source)
        self.assertNotIn("82a171e", self.source)

        case_start = self.wrapper.index("  panel-one)")
        case_end = self.wrapper.index("    ;;", case_start)
        section = self.wrapper[case_start:case_end]
        self.assertLess(
            section.index("acquire_driver_lock"),
            section.index("assert_no_learning_or_other_readout"),
        )
        self.assertIn(
            'run_tools "$SCRIPT" --config "$CONFIG" panel-one',
            section,
        )

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
