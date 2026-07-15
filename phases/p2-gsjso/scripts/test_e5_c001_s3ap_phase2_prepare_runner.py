#!/usr/bin/env python3
"""Docker-only contract tests for the S3-A-prime Phase-2 prepare/runner."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import tempfile
import unittest
from unittest import mock
from pathlib import Path

import numpy as np
import yaml
from PIL import Image as PILImage
from shapely.geometry import Polygon

from src.stage2.colmap_io import Camera, Image


REPO = Path(__file__).resolve().parents[3]


def load_module(name: str, path: Path):
    specification = importlib.util.spec_from_file_location(name, path)
    if specification is None or specification.loader is None:
        raise RuntimeError(path)
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


prepare = load_module("s3ap_phase2_prepare", REPO / "phases/p2-gsjso/scripts/e5_c001_s3ap_phase2_prepare.py")
runner = load_module("s3ap_phase2_runner", REPO / "phases/p2-gsjso/scripts/e5_c001_s3ap_phase2_runner.py")


class Phase2PrepareRunnerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lock = prepare.load_lock()

    def test_native_pixel_crop_and_adjusted_K(self):
        image = np.arange(96 * 160 * 3, dtype=np.uint32).reshape(96, 160, 3).astype(np.uint8)
        mask = np.zeros((96, 160), dtype=bool)
        mask[30:47, 73:91] = True
        box = prepare.crop_box_4x3(
            mask, 160, 96, margin_px=4, minimum_width_px=32, width_multiple_px=16
        )
        self.assertEqual((box[2] - box[0]) * 3, (box[3] - box[1]) * 4)
        camera = Camera(9, "PINHOLE", 160, 96, np.array([120.0, 121.0, 80.0, 48.0]))
        cropped_camera = prepare.adjust_camera(camera, 1, box)
        self.assertEqual(cropped_camera.width, box[2] - box[0])
        self.assertEqual(cropped_camera.height, box[3] - box[1])
        np.testing.assert_allclose(cropped_camera.K()[0, 0], camera.K()[0, 0])
        np.testing.assert_allclose(cropped_camera.K()[1, 1], camera.K()[1, 1])
        np.testing.assert_allclose(cropped_camera.K()[0, 2], camera.K()[0, 2] - box[0])
        np.testing.assert_allclose(cropped_camera.K()[1, 2], camera.K()[1, 2] - box[1])
        expected = image[box[1]:box[3], box[0]:box[2]]
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "crop.png"
            prepare.atomic_png(output, expected)
            actual = np.asarray(PILImage.open(output).convert("RGB"))
        self.assertTrue(np.array_equal(actual, expected), "PNG crop must preserve native pixels exactly")

    def test_auxiliary_cache_crop_is_exact_and_cutline_is_not_resized(self):
        normal = np.arange(40 * 60 * 3, dtype=np.float32).reshape(40, 60, 3)
        depth = np.arange(40 * 60, dtype=np.float32).reshape(40, 60)
        region = np.zeros((40, 60), dtype=np.int32)
        region[10:30, 20:45] = 4
        cutline = np.zeros((40, 60), dtype=bool)
        cutline[:, 27:34] = True
        box = (12, 8, 52, 38)
        expected_normal = normal[8:38, 12:52]
        expected_depth = depth[8:38, 12:52]
        expected_region = region[8:38, 12:52]
        expected_cutline = cutline[8:38, 12:52]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            prepare.atomic_npy(root / "normal.npy", expected_normal)
            prepare.atomic_npy(root / "depth.npy", expected_depth)
            prepare.atomic_npz(root / "region.npz", {
                "region_ids": expected_region,
                "cutline_mask": expected_cutline,
                "metadata_json": np.asarray(json.dumps({"cutline_half_width_px": 7})),
            })
            self.assertTrue(np.array_equal(np.load(root / "normal.npy"), expected_normal))
            self.assertTrue(np.array_equal(np.load(root / "depth.npy"), expected_depth))
            with np.load(root / "region.npz", allow_pickle=False) as archive:
                self.assertTrue(np.array_equal(archive["region_ids"], expected_region))
                self.assertTrue(np.array_equal(archive["cutline_mask"], expected_cutline))
                self.assertEqual(set(archive.files), {"region_ids", "cutline_mask", "metadata_json"})
                self.assertEqual(np.flatnonzero(archive["cutline_mask"][0]).tolist(), list(range(15, 22)))

    def test_mono_target_support_counts_cutline_and_both_prior_validities(self):
        target = np.ones((3, 4), dtype=bool)
        cutline = np.zeros((3, 4), dtype=bool)
        cutline[0, 0] = True
        normal = np.ones((3, 4, 3), dtype=np.float32)
        depth = np.ones((3, 4), dtype=np.float32)
        normal[0, 1] = np.nan
        normal[0, 2] = 0.1
        depth[0, 3] = np.nan
        depth[1, 0] = 0.0
        support = prepare.mono_target_prior_support(target, cutline, normal, depth, min_pixels=7)
        self.assertEqual(support["mono_target_region_pixel_count"], 12)
        self.assertEqual(support["mono_target_cutline_excluded_pixel_count"], 11)
        self.assertEqual(support["mono_target_prior_valid_pixel_count"], 7)
        self.assertTrue(support["mono_target_loss_active"])
        support = prepare.mono_target_prior_support(target, cutline, normal, depth, min_pixels=8)
        self.assertFalse(support["mono_target_loss_active"])

    def test_sfm_subset_requires_positive_depth_and_projection_in_a_crop(self):
        camera = Camera(1, "PINHOLE", 100, 80, np.array([100.0, 100.0, 50.0, 40.0]))
        image = Image(1, np.array([1.0, 0.0, 0.0, 0.0]), np.zeros(3), 1, "view.png")
        points = np.array([
            [0.0, 0.0, 2.0, 10, 20, 30],
            [2.0, 0.0, 2.0, 40, 50, 60],
            [0.0, 0.0, -2.0, 70, 80, 90],
        ], dtype=np.float64)
        subset, counts = prepare.crop_visible_sfm_subset(points, [(image, camera, (25, 20, 75, 60))])
        self.assertEqual(len(subset), 1)
        np.testing.assert_allclose(subset[0, :3], [0.0, 0.0, 2.0])
        self.assertEqual(counts, {"view": 1})

    def test_locked_base_inventory_has_18_base_plus_24_height_jobs(self):
        jobs = prepare.base_job_specs(self.lock)
        self.assertEqual(len(jobs), 42)
        self.assertEqual(sum(job["job_class"] == "base" for job in jobs), 18)
        self.assertEqual(sum(job["job_class"] == "height" for job in jobs), 24)
        self.assertEqual(len({job["job_id"] for job in jobs}), 42)
        self.assertFalse(any(job["job_class"] == "height" and job["height_delta_m"] == 0 for job in jobs))
        self.assertEqual({job["random_seed"] for job in jobs}, {2001, 2002})

    def _prepared_fixture(self):
        return {
            "data_root": "results/_s3ap_phase2_test/prepared/DEBY_LOD2_4907199",
            "p0_surface_seed": {"path": "results/_s3ap_phase2_test/p0.npz"},
            "a1a2_surface_seed": {"path": "results/_s3ap_phase2_test/merged.npz"},
        }

    def test_arm_configs_lock_photo_only_and_signal_protection_diffs(self):
        jobs = {job["arm"]: job for job in prepare.base_job_specs(self.lock) if job["building_id"] == "4907199" and job["replicate"] == "r1"}
        configs = {
            arm: prepare.make_training_config(self.lock, job, self._prepared_fixture(), [690953.0, 5336071.0, 604.0])
            for arm, job in jobs.items()
        }
        a0, a1, a2 = configs["a0"], configs["a1"], configs["a2"]
        zero_terms = (
            "w_depth", "w_normal", "w_mono_depth", "w_nc", "w_sem", "w_semdepth_smooth",
            "w_semdepth_plane", "w_boundary_normal", "w_structure", "w_mutual", "w_mvc", "w_distort",
            "loss_grad_audit_every", "semantic_geometry_audit_every",
        )
        self.assertTrue(all(a0[key] == 0 for key in zero_terms))
        self.assertFalse(a0["load_depth"] or a0["load_normal"] or a0["load_semantic"])
        self.assertNotIn("normal_dir", a0)
        self.assertTrue(a0["surface_seed_npz"].endswith("p0.npz"))
        self.assertEqual(a1["mono_normal_loss"], "target_region")
        self.assertEqual(a1["mono_depth_loss"], "ssi")
        self.assertEqual(a1["mono_target_buildings"], ["4907199"])
        self.assertEqual(a1["mono_target_min_pixels"], 64)
        self.assertEqual((a1["w_normal"], a1["w_mono_depth"]), (0.05, 0.05))
        self.assertEqual((a1["w_semdepth_smooth"], a1["w_semdepth_plane"]), (0.125, 0.125))
        self.assertEqual(a1["semantic_geometry_warmup"], 1500)
        self.assertEqual(a1["loss_grad_audit_every"], 500)
        self.assertEqual(a1["semantic_geometry_audit_every"], 5000)
        self.assertTrue(a1["surface_seed_npz"].endswith("merged.npz"))
        self.assertFalse(a1["surface_seed_protect"])
        self.assertTrue(a2["surface_seed_protect"])
        self.assertEqual(a2["surface_seed_protect_until_iter"], 10000)
        self.assertEqual(a2["surface_seed_prune_opa_initial"], 0.05)
        self.assertEqual(a2["surface_seed_prune_opa_final"], 0.01)
        self.assertEqual(a2["surface_seed_prune_switch_iter"], 10000)
        self.assertEqual(a1["visible_views"], a1["train_views"])
        self.assertEqual(a1["eval_views"], [])
        self.assertNotIn("init_pointcloud", a1)

    def test_surface_seed_union_uses_strict_schema_and_p0_wins_duplicates(self):
        p0 = {
            "path": "p0.npz", "sha256": "1" * 64, "count": 2,
            "xyz": np.array([[0, 0, 1], [1, 0, 1]], np.float32),
            "rgb": np.array([[1, 0, 0], [0, 1, 0]], np.float32),
            "sem": np.ones(2, np.int64),
        }
        aux = {
            "path": "aux.npz", "sha256": "2" * 64, "count": 2,
            "xyz": np.array([[1, 0, 1], [2, 0, 1]], np.float32),
            "rgb": np.array([[0, 0, 1], [1, 1, 1]], np.float32),
            "sem": np.ones(2, np.int64),
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "merged.npz"
            result = prepare.merge_surface_seeds(p0, aux, None, path, "4907199", self.lock["surface_seed_contract"])
            with np.load(path, allow_pickle=False) as archive:
                self.assertEqual(set(archive.files), {"xyz", "rgb", "sem", "metadata_json"})
                self.assertEqual(len(archive["xyz"]), 3)
                np.testing.assert_allclose(archive["rgb"][1], [0, 1, 0])
                metadata = prepare.read_metadata_scalar(archive["metadata_json"])
                self.assertEqual(metadata["schema"], "jointbuildgs.s3ap.surface_seeds.v1")
                self.assertFalse(metadata["gt_used_for_seed_generation"])
            self.assertEqual(result["duplicate_count"], 1)

    def test_boundary_source_drives_half_cell_graph_propagation_with_p0_z(self):
        p0 = {
            "path": "p0.npz", "sha256": "1" * 64, "count": 1, "role": "p0_surface",
            "xyz": np.array([[0.25, 0.25, 2.0]], np.float32),
            "rgb": np.array([[0.3, 0.4, 0.5]], np.float32),
            "sem": np.ones(1, np.int64),
            "metadata": {"plane_ax_local": 0.5, "plane_by_local": -0.25, "plane_c_local": 2.0},
        }
        auxiliary = {
            "path": "aux.npz", "sha256": "2" * 64, "count": 1, "role": "bc_aux",
            "xyz": np.array([[0.1, 0.1, 99.0]], np.float32),
            "rgb": np.array([[0.3, 0.4, 0.5]], np.float32),
            "sem": np.ones(1, np.int64),
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            propagated = prepare.build_boundary_graph_propagation(
                p0=p0, auxiliary=auxiliary,
                footprint=Polygon([(0, 0), (2, 0), (2, 1), (0, 1)]),
                world_offset=[0, 0, 0], destination=root / "prop.npz",
                lineage_path=root / "lineage.csv", building="4907199",
                contract=self.lock["surface_seed_contract"],
                propagation=self.lock["boundary_propagation"],
            )
            self.assertIsNotNone(propagated)
            assert propagated is not None
            self.assertGreater(propagated["count"], 1)
            xyz = propagated["xyz"].astype(np.float64)
            np.testing.assert_allclose(xyz[:, 2], 0.5 * xyz[:, 0] - 0.25 * xyz[:, 1] + 2.0, atol=2e-6)
            self.assertFalse(np.any(np.isclose(xyz[:, 2], 99.0)))
            with (root / "lineage.csv").open(newline="", encoding="utf-8") as handle:
                lineage = list(__import__("csv").DictReader(handle))
            self.assertEqual(len(lineage), propagated["count"])
            self.assertEqual({row["source_index"] for row in lineage}, {"0"})
            self.assertGreater(max(int(row["graph_distance_cells"]) for row in lineage), 0)
            metadata = propagated["metadata"]
            self.assertIn("offline GaussianPro-style", metadata["lineage"]["claim_boundary"])
            self.assertIn("FM-anchored", metadata["height_anchor_source"])

    def test_checkpoint_resume_policy_and_failed_job_does_not_block_next(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            partial_out = root / "partial"
            (partial_out / "ckpt").mkdir(parents=True)
            (partial_out / "ckpt/iter_10000.pt").write_bytes(b"partial")
            self.assertEqual(runner.checkpoint_state(partial_out)["status"], "blocked_resume_unsupported")
            import torch
            torch.save({"it": 30000, "n_prim": 1, "state_dict": {}}, partial_out / "ckpt/final.pt")
            self.assertEqual(runner.checkpoint_state(partial_out)["status"], "skipped_final_exists")
            self.assertEqual(
                runner.checkpoint_state(
                    partial_out, expected_job_id="bound", expected_config_sha256="abc"
                )["status"],
                "invalid_final_checkpoint",
            )
            binding_job = {
                "job_id": "bound", "config_path": str(root / "bound.yaml"),
                "config_sha256": "abc", "out_dir": str(partial_out),
                "iterations": "30000",
            }
            runner.write_job_binding(binding_job)
            self.assertEqual(
                runner.checkpoint_state(
                    partial_out, expected_job_id="bound", expected_config_sha256="abc"
                )["status"],
                "skipped_final_exists",
            )
            self.assertEqual(
                runner.checkpoint_state(
                    partial_out, expected_job_id="bound", expected_config_sha256="wrong"
                )["status"],
                "invalid_final_checkpoint",
            )
            torch.save({"it": 29999, "n_prim": 1, "state_dict": {}}, partial_out / "ckpt/final.pt")
            self.assertEqual(runner.checkpoint_state(partial_out)["status"], "invalid_final_checkpoint")

            runtime_lock = json.loads(json.dumps(self.lock))
            runtime_lock["runtime"]["training_command"] = [
                "python", "-c",
                "import pathlib,sys,yaml,torch; c=yaml.safe_load(open(sys.argv[1])); "
                "fail='fail' in pathlib.Path(sys.argv[1]).name; "
                "p=pathlib.Path(c['out_dir'])/'ckpt'/'final.pt'; "
                "p.parent.mkdir(parents=True,exist_ok=True); "
                "(torch.save({'it':30000,'n_prim':1,'state_dict':{}},p) if not fail else None); "
                "sys.exit(7 if fail else 0)",
                "{config}",
            ]
            jobs = []
            for sequence, name in enumerate(("fail", "ok"), 1):
                out = root / f"out_{name}"
                config_path = root / f"{name}.yaml"
                config = {
                    "max_iter": 30000, "out_dir": str(out), "visible_views": ["v.png"],
                    "train_views": ["v.png"], "eval_views": [],
                    "phase2_input_contract": {"gt_used": False, "lod2_used": False, "als_used": False},
                    "w_depth": 0.0, "w_normal": 0.0, "w_mono_depth": 0.0, "w_nc": 0.0,
                    "w_sem": 0.0, "w_semdepth_smooth": 0.0, "w_semdepth_plane": 0.0,
                    "w_boundary_normal": 0.0, "w_structure": 0.0, "w_mutual": 0.0,
                    "w_mvc": 0.0, "w_distort": 0.0,
                }
                config_path.write_text(yaml.safe_dump(config), encoding="utf-8")
                digest = hashlib.sha256(config_path.read_bytes()).hexdigest()
                jobs.append({
                    "sequence": str(sequence), "job_id": name, "arm": "a0", "building_id": "4907199",
                    "config_path": str(config_path), "config_sha256": digest, "out_dir": str(out),
                    "final_checkpoint": str(out / "ckpt/final.pt"), "iterations": "30000",
                })
            rows = runner.run_inventory(
                jobs, runtime_lock, status_path=root / "status.csv", log_dir=root / "logs",
                timeout_s=30, gpu_ids=[0],
            )
            self.assertEqual([row["status"] for row in rows], ["failed", "complete"])
            self.assertTrue((root / "out_ok/ckpt/final.pt").is_file())

    def test_tilt_requires_machine_trigger_and_uses_footprint_pca(self):
        self.assertEqual(
            self.lock["outputs"]["tilt_trigger"],
            "phases/p2-gsjso/runs/20260715_e5_c001_s3ap_phase2_prepare/return_signal.json",
        )
        geometry = Polygon([(100, 200), (104, 200), (104, 202), (100, 202)])
        axis, pivot = prepare.footprint_pca_axis(geometry, [100.0, 200.0, 0.0])
        np.testing.assert_allclose(axis, [1.0, 0.0], atol=1e-9)
        np.testing.assert_allclose(pivot, [2.0, 1.0], atol=1e-9)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "trigger.json"
            scores = root / "scores.csv"
            perturbations = root / "perturbations.csv"
            scores.write_text("x\n1\n", encoding="utf-8")
            perturbations.write_text("x\n1\n", encoding="utf-8")
            tilt_lock = json.loads(json.dumps(self.lock))
            tilt_lock["tilt_score_source"] = {
                "scores_csv": str(scores), "perturbation_csv": str(perturbations),
                "expected_nonzero_height_rows": 24, "require_evaluation_complete": True,
            }
            payload = {
                "schema": tilt_lock["training"]["tilt_trigger_schema"],
                "return_signal": False,
                "scores_csv": str(scores), "perturbation_csv": str(perturbations),
                "source_score_sha256": hashlib.sha256(scores.read_bytes()).hexdigest(),
                "source_perturbation_sha256": hashlib.sha256(perturbations.read_bytes()).hexdigest(),
                "expected_nonzero_height_rows": 24, "observed_nonzero_height_rows": 24,
                "evaluation_complete": True,
            }
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "return_signal=true"):
                prepare.validate_tilt_trigger(path, tilt_lock)
            payload["return_signal"] = True
            path.write_text(json.dumps(payload), encoding="utf-8")
            self.assertTrue(prepare.validate_tilt_trigger(path, tilt_lock)["return_signal"])
            scores.write_text("x\n2\n", encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "score file/hash mismatch"):
                prepare.validate_tilt_trigger(path, tilt_lock)
        jobs = prepare.tilt_job_specs(
            self.lock, {key: geometry for key in self.lock["targets"]}, [100.0, 200.0, 0.0]
        )
        self.assertEqual(len(jobs), 18)
        self.assertTrue(all(job["job_class"] == "tilt" and job["tilt_deg"] != 0 for job in jobs))
        self.assertTrue(all(job["tilt_axis_xy"] == [1.0, 0.0] for job in jobs))

    def test_runtime_attestation_and_launcher_lock(self):
        names = self.lock["runtime"]["attestation_env"]
        environment = {
            names["image_id"]: self.lock["runtime"]["docker_image_id"],
            names["host_uid"]: str(__import__("os").getuid()),
            names["host_gid"]: str(__import__("os").getgid()),
        }
        with mock.patch.dict("os.environ", environment, clear=False):
            audit = prepare.validate_runtime_attestation(self.lock)
            self.assertTrue(audit["user_mapping_exact"])
            self.assertEqual(runner.validate_runtime_attestation(self.lock)["docker_image_id"], environment[names["image_id"]])
        launcher = (REPO / self.lock["runtime"]["host_launcher"]).read_text(encoding="utf-8")
        self.assertIn(self.lock["runtime"]["docker_image_id"], launcher)
        self.assertIn('--user "${HOST_UID}:${HOST_GID}"', launcher)


if __name__ == "__main__":
    unittest.main()
