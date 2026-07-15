#!/usr/bin/env python3
"""Tiny contract fixtures for the S3-A-prime Phase-3 harness."""

from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
from shapely.geometry import box


SCRIPT = Path(__file__).with_name("e5_c001_s3ap_phase3.py")
SPEC = importlib.util.spec_from_file_location("e5_c001_s3ap_phase3_tested", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class Phase3ContractTests(unittest.TestCase):
    def _job(
        self, run_id: str, kind: str = "none", value: float = 0.0,
        building: str = "8568391", arm: str = "a1", replicate: str = "r1",
    ) -> object:
        return MODULE.Job(
            run_id=run_id, building_id=building, arm=arm, replicate=replicate,
            perturbation_type=kind, perturbation_value=value, config_path="",
            prepared_root="prepared", checkpoint="final.pt",
        )

    def test_roofer_las_has_locked_crs_and_classes(self) -> None:
        import laspy

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "fixture.las"
            xyz = np.asarray([[690000.0, 5336000.0, 600.0], [690001.0, 5336001.0, 590.0]])
            MODULE._write_las(path, xyz, np.asarray([6, 2], dtype=np.uint8))
            cloud = laspy.read(path)
            self.assertEqual(cloud.header.parse_crs().to_epsg(), 25832)
            np.testing.assert_array_equal(np.asarray(cloud.classification), [6, 2])

    def test_roofer_multipolygon_components_merge_without_geometry_loss(self) -> None:
        def feature(z: int, roof_planes: int, mode: str) -> dict[str, object]:
            building = "DEBY_LOD2_8568391"
            return {
                "type": "CityJSONFeature", "id": building,
                "CityObjects": {
                    building: {
                        "type": "Building", "children": [building + "-0"],
                        "geographicalExtent": [0, 0, 0, 1, 1, z + 1],
                        "attributes": {
                            "building_id": building, "source": "fixture",
                            "grid_m": 0.5, "point_count": 20,
                            "rf_success": True, "rf_pointcloud_unusable": False,
                            "rf_force_lod11": mode == "lod11_fallback",
                            "rf_extrusion_mode": mode, "rf_roof_type": "flat",
                            "rf_roof_planes": roof_planes, "rf_volume_lod22": 2.0,
                            "rf_rmse_lod22": 0.2, "rf_pt_density": 5.0,
                            "rf_nodata_frac": 0.1,
                        },
                        "geometry": [{
                            "type": "MultiSurface", "lod": "0",
                            "boundaries": [[[0, 1, 2, 3]]],
                        }],
                    },
                    building + "-0": {
                        "type": "BuildingPart", "parents": [building],
                        "geometry": [{
                            "type": "Solid", "lod": "2.2",
                            "boundaries": [[[[0, 1, 2, 3]]]],
                            "semantics": {
                                "surfaces": [{"type": "RoofSurface"}],
                                "values": [[0]],
                            },
                        }],
                    },
                },
                "vertices": [[0, 0, z], [1, 0, z], [1, 1, z], [0, 1, z]],
            }

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            jsonl = root / "components.city.jsonl"
            header = {
                "type": "CityJSON", "version": "2.0", "CityObjects": {},
                "vertices": [], "transform": {
                    "scale": [1.0, 1.0, 1.0], "translate": [0.0, 0.0, 0.0],
                }, "metadata": {
                    "referenceSystem": "https://www.opengis.net/def/crs/EPSG/0/25832",
                },
            }
            jsonl.write_text(
                "\n".join(json.dumps(value) for value in (
                    header, feature(10, 1, "standard"), feature(20, 2, "lod11_fallback"),
                )) + "\n",
                encoding="utf-8",
            )
            output = root / "merged.city.json"
            w2 = MODULE.load_module("phase3_component_fixture_w2", MODULE.W2_SCRIPT)
            result = MODULE._combine_roofer_component_cityjsonseq(
                [jsonl], output, "DEBY_LOD2_8568391", w2,
            )
            payload = json.loads(output.read_text(encoding="utf-8"))
            objects = payload["CityObjects"]
            self.assertEqual(
                set(objects),
                {"DEBY_LOD2_8568391", "DEBY_LOD2_8568391-0", "DEBY_LOD2_8568391-1"},
            )
            parent = objects["DEBY_LOD2_8568391"]
            self.assertEqual(parent["children"], ["DEBY_LOD2_8568391-0", "DEBY_LOD2_8568391-1"])
            self.assertEqual(len(parent["geometry"][0]["boundaries"]), 2)
            self.assertEqual(len(payload["vertices"]), 8)
            self.assertEqual(
                objects["DEBY_LOD2_8568391-1"]["geometry"][0]["boundaries"][0][0][0],
                [4, 5, 6, 7],
            )
            self.assertEqual(parent["attributes"]["s3ap_component_count"], 2)
            self.assertEqual(parent["attributes"]["rf_roof_planes"], 3)
            self.assertEqual(parent["attributes"]["rf_extrusion_mode"], "lod11_fallback")
            self.assertEqual(
                objects["DEBY_LOD2_8568391-1"]["attributes"]["rf_roof_planes"],
                2,
            )
            self.assertEqual(result["component_count"], 2)
            self.assertTrue(result["has_lod22"])

    def test_roofer_component_merge_rejects_unexpected_object_graph(self) -> None:
        building = "DEBY_LOD2_8568391"
        header = {
            "type": "CityJSON", "version": "2.0", "CityObjects": {},
            "vertices": [], "transform": {
                "scale": [1.0, 1.0, 1.0], "translate": [0.0, 0.0, 0.0],
            }, "metadata": {
                "referenceSystem": "https://www.opengis.net/def/crs/EPSG/0/25832",
            },
        }
        malformed = {
            "type": "CityJSONFeature", "id": building,
            "CityObjects": {
                building: {
                    "type": "Building", "children": [building + "-0", building + "-1"],
                    "attributes": {}, "geographicalExtent": [0, 0, 0, 1, 1, 1],
                    "geometry": [{"type": "MultiSurface", "lod": "0", "boundaries": []}],
                },
            },
            "vertices": [[0, 0, 0]],
        }
        with tempfile.TemporaryDirectory() as directory:
            jsonl = Path(directory) / "malformed.city.jsonl"
            jsonl.write_text(
                json.dumps(header) + "\n" + json.dumps(malformed) + "\n",
                encoding="utf-8",
            )
            w2 = MODULE.load_module("phase3_component_reject_w2", MODULE.W2_SCRIPT)
            with self.assertRaisesRegex(RuntimeError, "exactly one BuildingPart"):
                MODULE._combine_roofer_component_cityjsonseq(
                    [jsonl], Path(directory) / "out.city.json", building, w2,
                )

    def test_roofer_component_mode_aggregation_is_fail_closed(self) -> None:
        base = {
            "building_id": "DEBY_LOD2_8568391", "source": "fixture",
            "grid_m": 0.5, "point_count": 20, "rf_success": True,
            "rf_pointcloud_unusable": False, "rf_force_lod11": False,
            "rf_roof_type": "flat", "rf_roof_planes": 1,
            "rf_volume_lod22": 1.0, "rf_rmse_lod22": 0.1,
            "rf_pt_density": 5.0, "rf_nodata_frac": 0.0,
        }
        standard = {**base, "rf_extrusion_mode": "standard"}
        skipped = {**base, "rf_extrusion_mode": "skip"}
        result = MODULE._aggregate_roofer_component_attributes([standard, skipped])
        self.assertEqual(result["rf_extrusion_mode"], "skip")
        unknown = {**base, "rf_extrusion_mode": "unknown"}
        mixed = MODULE._aggregate_roofer_component_attributes([standard, unknown])
        self.assertEqual(mixed["rf_extrusion_mode"], "mixed_components")
        self.assertFalse(mixed["rf_success"])
        unknown_only = MODULE._aggregate_roofer_component_attributes([unknown])
        self.assertEqual(unknown_only["rf_extrusion_mode"], "mixed_components")
        self.assertFalse(unknown_only["rf_success"])

    def test_roofer_solid_semantics_shape_is_fail_closed(self) -> None:
        boundaries = [[[[0, 1, 2, 3]], [[0, 3, 2, 1]]]]
        with self.assertRaisesRegex(RuntimeError, "semantic surfaces missing"):
            MODULE._validate_cityjson_solid_semantics(
                {}, boundaries, "fixture",
            )
        with self.assertRaisesRegex(RuntimeError, "surface shape mismatch"):
            MODULE._validate_cityjson_solid_semantics(
                {"surfaces": [{"type": "RoofSurface"}], "values": [[0]]},
                boundaries, "fixture",
            )
        with self.assertRaisesRegex(RuntimeError, "semantic index out of range"):
            MODULE._validate_cityjson_solid_semantics(
                {"surfaces": [{"type": "RoofSurface"}], "values": [[0, 1]]},
                boundaries, "fixture",
            )

    def test_roofer_component_merge_rejects_out_of_range_child_vertex(self) -> None:
        building = "DEBY_LOD2_8568391"
        header = {
            "type": "CityJSON", "version": "2.0", "CityObjects": {},
            "vertices": [], "transform": {
                "scale": [1.0, 1.0, 1.0], "translate": [0.0, 0.0, 0.0],
            }, "metadata": {
                "referenceSystem": "https://www.opengis.net/def/crs/EPSG/0/25832",
            },
        }
        feature = {
            "type": "CityJSONFeature", "id": building,
            "CityObjects": {
                building: {
                    "type": "Building", "children": [building + "-0"],
                    "attributes": {
                        "building_id": building, "source": "fixture",
                        "grid_m": 0.5, "point_count": 4,
                    },
                    "geographicalExtent": [0, 0, 0, 1, 1, 1],
                    "geometry": [{
                        "type": "MultiSurface", "lod": "0",
                        "boundaries": [[[0, 1, 2, 3]]],
                    }],
                },
                building + "-0": {
                    "type": "BuildingPart", "parents": [building],
                    "geometry": [{
                        "type": "Solid", "lod": "2.2",
                        "boundaries": [[[[0, 1, 2, 9]]]],
                        "semantics": {
                            "surfaces": [{"type": "RoofSurface"}],
                            "values": [[0]],
                        },
                    }],
                },
            },
            "vertices": [[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0]],
        }
        with tempfile.TemporaryDirectory() as directory:
            jsonl = Path(directory) / "bad-index.city.jsonl"
            jsonl.write_text(
                json.dumps(header) + "\n" + json.dumps(feature) + "\n",
                encoding="utf-8",
            )
            w2 = MODULE.load_module("phase3_component_bad_index_w2", MODULE.W2_SCRIPT)
            with self.assertRaisesRegex(RuntimeError, "index out of range"):
                MODULE._combine_roofer_component_cityjsonseq(
                    [jsonl], Path(directory) / "out.city.json", building, w2,
                )

    def test_phase2_inventory_aliases_and_tilt_precedence(self) -> None:
        config = MODULE.load_json(MODULE.DEFAULT_CONFIG)
        job = MODULE.job_from_row({
            "job_id": "gs_e5_C001_s3ap_b8568392_a1_tilt_p05_r1",
            "job_class": "tilt", "building_id": "8568392", "arm": "a1",
            "replicate": "r1", "height_delta_m": "0.0", "tilt_deg": "5.0",
            "config_path": "phase2/generated.yaml",
            "data_root": "results/tum_transfer/e5_s3ap_phase2/prepared/DEBY_LOD2_8568392",
            "final_checkpoint": "results/tum_transfer/e5_s3ap_phase2/runs/example/ckpt/final.pt",
        }, config)
        self.assertEqual(job.run_id, "gs_e5_C001_s3ap_b8568392_a1_tilt_p05_r1")
        self.assertEqual(job.perturbation_type, "tilt")
        self.assertEqual(job.perturbation_value, 5.0)

    def test_locked_inventory_is_exact_and_fail_closed(self) -> None:
        config = MODULE.load_json(MODULE.DEFAULT_CONFIG)
        config["phase2"]["job_inventories"] = []
        jobs = [
            self._job(f"base_{building}_{arm}_{replicate}", building=building, arm=arm, replicate=replicate)
            for building in config["targets"] for arm in ("a0", "a1", "a2")
            for replicate in ("r1", "r2")
        ]
        height_values = [
            float(value) for value in config["perturbation"]["height_deltas_m"]
            if float(value) != 0.0
        ]
        jobs.extend(
            self._job(f"height_{building}_{index}", "height", value, building=building)
            for building in config["targets"] for index, value in enumerate(height_values)
        )
        contract = MODULE.inventory_contract(config, jobs)
        self.assertEqual(contract["status"], "complete")
        self.assertEqual(contract["counts"], {
            "total": 42, "base": 18, "height_nonzero": 24, "tilt": 0,
        })
        self.assertEqual(MODULE.inventory_contract(config, jobs[:-1])["status"], "failed")
        jobs.extend(
            self._job(f"tilt_{building}_{index}", "tilt", float(value), building=building)
            for building in config["targets"]
            for index, value in enumerate(config["perturbation"]["tilt_deltas_deg"])
        )
        self.assertEqual(MODULE.inventory_contract(config, jobs)["status"], "complete")

        wrong_grid = list(jobs[:42])
        wrong_grid[0] = self._job("wrong_grid_duplicate_tuple", building=config["targets"][1], arm="a0", replicate="r1")
        wrong = MODULE.inventory_contract(config, wrong_grid)
        self.assertEqual(wrong["status"], "failed")
        self.assertIn("base_tuple_grid_mismatch", wrong["errors"])

    def test_current_repository_inventory_is_base18_height24(self) -> None:
        config = MODULE.load_json(MODULE.DEFAULT_CONFIG)
        contract = MODULE.inventory_contract(config, MODULE.discover_jobs(config))
        self.assertEqual(contract["status"], "complete")
        self.assertEqual(contract["counts"]["base"], 18)
        self.assertEqual(contract["counts"]["height_nonzero"], 24)

    def test_phase3_lock_reuses_phase2_prewarmed_cache(self) -> None:
        config = MODULE.load_json(MODULE.DEFAULT_CONFIG)
        self.assertEqual(
            config["outputs"]["torch_extensions"],
            config["phase2_prewarm"]["shared_torch_extensions"],
        )
        self.assertIn("e5_s3ap_phase2/runtime/torch_extensions", config["outputs"]["torch_extensions"])

    def test_one_worker_queue_per_gpu_never_overlaps_a_gpu(self) -> None:
        jobs = [self._job(f"queue_{index}") for index in range(8)]
        active = {"0": 0, "1": 0}
        maximum = {"0": 0, "1": 0}
        seen: set[str] = set()
        lock = threading.Lock()

        def run_job(_job: object, gpu_id: str) -> None:
            with lock:
                active[gpu_id] += 1
                maximum[gpu_id] = max(maximum[gpu_id], active[gpu_id])
                seen.add(gpu_id)
            time.sleep(0.01)
            with lock:
                active[gpu_id] -= 1

        errors = MODULE.run_gpu_serial_queues(jobs, ["0", "1"], run_job)
        self.assertEqual(errors, [])
        self.assertEqual(maximum, {"0": 1, "1": 1})
        self.assertEqual(seen, {"0", "1"})

    def test_reuse_digest_changes_with_any_bundle_digest(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "input.bin"
            path.write_bytes(b"first")
            first = MODULE.hash_file_bundle([path])
            path.write_bytes(b"second")
            second = MODULE.hash_file_bundle([path])
            self.assertNotEqual(first["digest"], second["digest"])
            pre = {"digest": first["digest"]}
            score = {"digest": "a" * 64}
            old = MODULE.full_reuse_fingerprint(pre, score)
            self.assertNotEqual(old, MODULE.full_reuse_fingerprint({"digest": second["digest"]}, score))
            self.assertNotEqual(old, MODULE.full_reuse_fingerprint(pre, {"digest": "b" * 64}))

    def test_docker_image_id_requires_exact_immutable_id(self) -> None:
        digest = "a" * 64
        self.assertEqual(MODULE.normalize_image_id(digest), "sha256:" + digest)
        self.assertEqual(MODULE.normalize_image_id("sha256:" + digest), "sha256:" + digest)
        with self.assertRaises(RuntimeError):
            MODULE.normalize_image_id("latest")

    def test_runtime_image_verification_records_match_and_rejects_drift(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config = MODULE.load_json(MODULE.DEFAULT_CONFIG)
            output = Path(directory) / "images.json"
            config["outputs"]["image_verification"] = str(output)
            expected = [
                config["containers"]["render_image_id"],
                config["containers"]["tools_image_id"],
                config["roofer"]["image_id_record"],
            ]
            good = [SimpleNamespace(returncode=0, stdout=value + "\n") for value in expected]
            with patch.object(MODULE.subprocess, "run", side_effect=good):
                result = MODULE.verify_docker_images(config)
            self.assertEqual(result["status"], "complete")
            self.assertTrue(all(row["matched"] for row in result["images"]))
            drift = list(good)
            drift[-1] = SimpleNamespace(returncode=0, stdout="sha256:" + "0" * 64 + "\n")
            with patch.object(MODULE.subprocess, "run", side_effect=drift):
                with self.assertRaisesRegex(RuntimeError, "roofer"):
                    MODULE.verify_docker_images(config)
            self.assertEqual(MODULE.load_json(output)["status"], "failed")

    def test_phase2_prewarm_verification_binds_shared_extension_hash(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cache = root / "torch_extensions"
            cache.mkdir()
            extension = cache / "gsplat_cuda.so"
            extension.write_bytes(b"locked-extension")
            script = MODULE.resolve_repo_path(
                "phases/p2-gsjso/scripts/e5_c001_s3ap_gsplat_prewarm.py"
            )
            manifest_path = root / "gsplat_prewarm.json"
            lock_path = root / "phase2_lock.json"
            prepare_path = root / "prepare_manifest.json"
            phase2_lock = {
                "runtime": {
                    "docker_image_id": MODULE.load_json(MODULE.DEFAULT_CONFIG)["containers"]["render_image_id"],
                    "writable_cache_env": {"TORCH_EXTENSIONS_DIR": str(cache)},
                    "gsplat_prewarm": {"manifest": str(manifest_path), "script": str(script)},
                }
            }
            MODULE.atomic_json(lock_path, phase2_lock)
            lock_sha = MODULE.sha256_file(lock_path)
            MODULE.atomic_json(prepare_path, {"lock_sha256": lock_sha})
            prepare_sha = MODULE.sha256_file(prepare_path)
            config = MODULE.load_json(MODULE.DEFAULT_CONFIG)
            config["phase2_prewarm"].update({
                "lock": str(lock_path), "lock_sha256": lock_sha,
                "prepare_manifest": str(prepare_path),
                "prepare_manifest_sha256": prepare_sha,
                "manifest": str(manifest_path), "script": str(script),
                "shared_torch_extensions": str(cache),
            })
            config["outputs"]["torch_extensions"] = str(cache)
            verification_path = root / "verification.json"
            config["outputs"]["prewarm_verification"] = str(verification_path)
            prewarm_log = root / "prewarm.log"
            prewarm_log.write_text("serialized prewarm fixture\n", encoding="utf-8")
            config["outputs"]["prewarm_log"] = str(prewarm_log)
            git_head = MODULE.subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=MODULE.REPO, text=True,
            ).strip()
            MODULE.atomic_json(manifest_path, {
                "schema": config["phase2_prewarm"]["manifest_schema"],
                "status": "complete", "lock_sha256": lock_sha,
                "runtime_attestation": {
                    "docker_image_id": config["containers"]["render_image_id"],
                },
                "torch_extensions_dir": str(cache), "script": str(script),
                "script_sha256": MODULE.sha256_file(script), "git_head": git_head,
                "extension_path": str(extension),
                "extension_sha256": MODULE.sha256_file(extension),
            })
            result = MODULE.verify_phase2_prewarm(config, 0)
            self.assertEqual(result["status"], "complete")
            self.assertEqual(result["extension_sha256"], MODULE.sha256_file(extension))
            binding = MODULE.phase2_prewarm_binding(config)
            self.assertEqual(binding["extension_sha256"], MODULE.sha256_file(extension))
            prewarm_log.write_text("log drift\n", encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "prewarm_log_sha256"):
                MODULE.phase2_prewarm_binding(config)
            prewarm_log.write_text("serialized prewarm fixture\n", encoding="utf-8")
            extension.write_bytes(b"drift")
            with self.assertRaisesRegex(RuntimeError, "extension_sha256_mismatch"):
                MODULE.verify_phase2_prewarm(config, 0)
            self.assertEqual(MODULE.load_json(verification_path)["status"], "failed")

    def test_controller_invokes_phase2_prewarm_launcher_only_once(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = MODULE.load_json(MODULE.DEFAULT_CONFIG)
            config["outputs"].update({
                "status_csv": str(root / "status.csv"),
                "run_log": str(root / "run.log"),
                "job_root": str(root / "jobs"),
                "prewarm_log": str(root / "prewarm.log"),
            })
            controller = MODULE.Controller(
                MODULE.DEFAULT_CONFIG, config, SimpleNamespace(resume=False),
            )
            fixture = {"status": "complete", "extension_sha256": "a" * 64}
            with patch.object(controller, "_run_command", return_value=0) as launch:
                with patch.object(MODULE, "verify_phase2_prewarm", return_value=fixture):
                    self.assertEqual(controller.run_phase2_prewarm(), fixture)
                    with self.assertRaisesRegex(RuntimeError, "already invoked"):
                        controller.run_phase2_prewarm()
            launch.assert_called_once()
            command = launch.call_args.args[0]
            self.assertEqual(command[-1], "prewarm")
            self.assertIn("run_e5_c001_s3ap_phase2.sh", command[-2])

    def test_empty_aggregate_writes_partial_artifacts_then_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = MODULE.load_json(MODULE.DEFAULT_CONFIG)
            config["outputs"].update({
                "phase3_root": str(root), "job_root": str(root / "jobs"),
                "status_csv": str(root / "status.csv"),
                "manifest": str(root / "manifest.json"),
                "scores_csv": str(root / "scores.csv"),
                "perturbation_csv": str(root / "perturbation.csv"),
                "perturbation_cells_csv": str(root / "cells.csv"),
                "report_md": str(root / "report.md"),
                "figure_dir": str(root / "figures"),
                "tilt_trigger": str(root / "trigger.json"),
                "image_verification": str(root / "images.json"),
                "prewarm_verification": str(root / "prewarm_verification.json"),
                "prewarm_log": str(root / "prewarm.log"),
            })
            config_path = root / "config.json"
            config_path.write_text(json.dumps(config), encoding="utf-8")
            MODULE.atomic_json(root / "prewarm_verification.json", {"fixture": True})
            (root / "prewarm.log").write_text("fixture prewarm log\n", encoding="utf-8")
            prewarm_fixture = {"extension_sha256": "a" * 64}
            with patch.object(MODULE, "phase2_prewarm_binding", return_value=prewarm_fixture):
                with patch.object(MODULE, "score_only_fingerprint", wraps=MODULE.score_only_fingerprint) as score_hash:
                    with self.assertRaisesRegex(RuntimeError, "aggregate fail-closed"):
                        MODULE.aggregate(SimpleNamespace(config=str(config_path), no_figures=True))
                    score_hash.assert_not_called()
            manifest = MODULE.load_json(root / "manifest.json")
            self.assertEqual(manifest["status"], "partial_fail_closed")
            self.assertIn(
                "zero_complete_score_rows_forbidden",
                manifest["aggregate_contract"]["errors"],
            )
            self.assertFalse(MODULE.load_json(root / "trigger.json")["return_signal"])

    def test_occupied_cell_union_is_global_and_footprint_free(self) -> None:
        geometry = MODULE.occupied_cell_union(
            np.asarray([[-0.1, -0.1], [0.1, 0.1], [0.2, 0.2]], dtype=np.float64),
            0.5,
        )
        self.assertTrue(np.isclose(geometry.area, 0.5))
        self.assertEqual(geometry.bounds, (-0.5, -0.5, 0.5, 0.5))

    def test_coverage_edge_and_interior_use_locked_distance(self) -> None:
        footprint = box(0.0, 0.0, 4.0, 4.0)
        result = MODULE.coverage_by_region(
            np.asarray([[0.25, 0.25], [2.25, 2.25]], dtype=np.float64),
            footprint,
            grid_m=0.5,
            edge_width_m=1.0,
        )
        self.assertEqual(result["all"], {"eligible": 64, "occupied": 2, "ratio": 2 / 64})
        self.assertEqual(result["edge"], {"eligible": 48, "occupied": 1, "ratio": 1 / 48})
        self.assertEqual(result["interior"], {"eligible": 16, "occupied": 1, "ratio": 1 / 16})

    def test_citygml_sampling_uses_score_grid_and_roof_faces(self) -> None:
        surface = SimpleNamespace(
            polygon=box(0.0, 0.0, 1.0, 1.0),
            z_at=lambda x, y: np.asarray(x) * 0.0 + 12.0,
        )
        points = MODULE._sample_citygml_roof([surface], box(0.0, 0.0, 2.0, 2.0), 0.5)
        self.assertEqual(points.shape, (4, 3))
        np.testing.assert_allclose(points[:, 2], 12.0)

    def test_substantive_filter_separates_raw_accepted_and_substantive(self) -> None:
        lock = {
            "roofer_status": "success",
            "forbidden_extrusion_modes": ["lod11_fallback"],
            "minimum_roof_planes": 1,
            "minimum_completeness": 0.5,
            "maximum_roof_rms_m": 3.0,
        }
        fallback = MODULE.substantive_classification(
            roofer_status="success", extrusion_mode="lod11_fallback", roof_planes=2,
            geometry_has_lod22=True, val3dity_valid=True, completeness=1.0,
            roof_rms_m=0.1, lock=lock,
        )
        self.assertTrue(fallback["geometry_has_lod22"])
        self.assertFalse(fallback["has_lod22"])
        self.assertFalse(fallback["substantive_filter"])
        accepted = MODULE.substantive_classification(
            roofer_status="success", extrusion_mode="", roof_planes=1,
            geometry_has_lod22=True, val3dity_valid=True, completeness=0.5,
            roof_rms_m=3.0, lock=lock,
        )
        self.assertTrue(accepted["has_lod22"])
        self.assertTrue(accepted["substantive_filter"])

    def test_height_trigger_is_exact_nonzero_a1_r1_rule(self) -> None:
        rule = "fixture exact rule"
        rows = [
            {
                "run_id": "equal", "building_id": "DEBY_LOD2_4907199",
                "arm": "a1", "replicate": "r1", "delta_m": 1.0,
                "score_status": "complete", "post_gs_signed_median_error_m": -1.2,
                "perturbed_p0_signed_median_error_m": 1.2,
            },
            {
                "run_id": "zero", "building_id": "DEBY_LOD2_4907199",
                "arm": "a1", "replicate": "r1", "delta_m": 0.0,
                "score_status": "complete", "post_gs_signed_median_error_m": 0.0,
                "perturbed_p0_signed_median_error_m": 1.0,
            },
            {
                "run_id": "r2", "building_id": "DEBY_LOD2_4907199",
                "arm": "a1", "replicate": "r2", "delta_m": 2.0,
                "score_status": "complete", "post_gs_signed_median_error_m": 0.0,
                "perturbed_p0_signed_median_error_m": 2.0,
            },
        ]
        no_signal = MODULE.perturbation_trigger(rows, rule)
        self.assertFalse(no_signal["return_signal"])
        self.assertEqual(no_signal["candidate_count"], 1)
        rows.append({
            "run_id": "strict", "building_id": "DEBY_LOD2_8568391",
            "arm": "a1", "replicate": "r1", "delta_m": -2.0,
            "score_status": "complete", "post_gs_signed_median_error_m": -0.4,
            "perturbed_p0_signed_median_error_m": -1.5,
        })
        signal = MODULE.perturbation_trigger(rows, rule)
        self.assertTrue(signal["return_signal"])
        self.assertEqual(signal["qualifying_count"], 1)
        self.assertEqual(signal["qualifying"][0]["run_id"], "strict")

    def test_spatial_perturbation_cells_preserve_edge_and_interior(self) -> None:
        job = self._job("spatial", "height", 1.0)
        points = np.asarray([[0.25, 0.25, 0.0], [2.25, 2.25, 0.0]], dtype=np.float64)
        rows = MODULE.perturbation_cell_rows(
            job=job, p0_points=points, p0_residuals=np.asarray([-1.0, 2.0]),
            gs_points=points, gs_residuals=np.asarray([-0.2, 1.0]),
            footprint=box(0.0, 0.0, 4.0, 4.0), edge_width_m=1.0,
            grid_m=0.5, score_status="complete",
        )
        self.assertEqual([row["region"] for row in rows], ["edge", "interior"])
        self.assertFalse(rows[0]["return_condition_met"])
        self.assertTrue(rows[1]["return_condition_met"])
        self.assertAlmostEqual(rows[1]["return_amount_m"], 2.0)


if __name__ == "__main__":
    unittest.main()
