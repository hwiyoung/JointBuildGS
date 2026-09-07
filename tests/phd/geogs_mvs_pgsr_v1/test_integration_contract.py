"""CPU checks of the actual GeoGS integration boundary and frozen bindings."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import random
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np
import torch

from src.phd.geogs_mvs_pgsr_v1 import geometry, mvs_depth


ROOT = Path(__file__).resolve().parents[3]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class IntegrationContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path = ROOT / "src/phd/geogs_mvs_pgsr_v1/integration.py"
        spec = importlib.util.spec_from_file_location("mvs_integration_contract_fixture", path)
        cls.integration = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {"jbgs_mvs_pgsr_depth": mvs_depth,
                                      "jbgs_mvs_pgsr_geometry": geometry}):
            spec.loader.exec_module(cls.integration)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.output = self.root / "output"
        self.output.mkdir()
        self.config_path = self.root / "config.json"
        self.config = json.loads((ROOT / "configs/phd/geogs_mvs_pgsr_v1/experiment_v1.json").read_text())
        self.config_path.write_text(json.dumps(self.config))
        self.parent_manifest = self.root / "parent.json"
        self.parent_manifest.write_text("{}")
        K = [[8., 0., 3.], [0., 8., 3.], [0., 0., 1.]]
        R = np.eye(3).tolist()
        self.views = []
        self.cameras = []
        for index, name in enumerate(("camera_A.JPG", "camera_B.JPG")):
            depth_path = self.root / (name + ".geometric.bin")
            header = b"7&7&1&"
            raw = np.full((7, 7), 5., dtype="<f4")
            depth_path.write_bytes(header + raw.T.tobytes(order="F"))
            t = [index * .1, 0., 0.]
            self.views.append({"name": name, "width": 7, "height": 7,
                               "K": K, "R": R, "t": t,
                               "maps": {"depth": {"frame": "CAMERA_Z", "sha256": sha(depth_path),
                                                  "width": 7, "height": 7, "channels": 1,
                                                  "header_bytes": len(header), "K": K}},
                               "local_depth": depth_path.name})
            transform = torch.eye(4)
            transform[:3, 3] = torch.tensor(t)
            projection = torch.zeros(4, 4)
            projection[0, 0], projection[1, 1] = 2 * K[0][0] / 7, 2 * K[1][1] / 7
            projection[0, 2], projection[1, 2] = (2 * K[0][2] + 1 - 7) / 7, (2 * K[1][2] + 1 - 7) / 7
            self.cameras.append(SimpleNamespace(image_name=Path(name).stem,
                                                world_view_transform=transform.T,
                                                projection_matrix=projection.T,
                                                image_width=7, image_height=7,
                                                jbgs_source_intrinsics=np.array(K),
                                                original_image=torch.ones(3, 7, 7)))
        self.binding_path = self.root / "binding.json"
        self.binding = {
            "schema": "JBGS_MVS_PGSR_INPUT_v1", "region": "P2",
            "config_sha256": sha(self.config_path), "scientific_verdict": None,
            "parent_input_manifest_sha256": sha(self.parent_manifest),
            "train": self.views, "evaluation_names": [],
            "neighbor_graph": {"graph": {
                self.views[0]["name"]: {"selected": [self.views[1]["name"]]},
                self.views[1]["name"]: {"selected": [self.views[0]["name"]]}}},
        }
        self.binding_path.write_text(json.dumps(self.binding))
        self.args = SimpleNamespace(use_scale_invariant=False, use_confidence=False,
                                    jbgs_release_protection=False, stage_switch_iter=8000,
                                    jbgs_resume_full="/anchor/checkpoint.pth", lambda_lod_anchor=.005,
                                    jbgs_input_manifest=str(self.parent_manifest))
        self.pipe = SimpleNamespace(depth_ratio=0.)

    def controller(self, mode="mvs"):
        environment = {"JBGS_MVS_PGSR_MODE": mode, "JBGS_MVS_REGION": "P2",
                       "JBGS_MVS_CONFIG": str(self.config_path),
                       "JBGS_MVS_CONFIG_SHA256": sha(self.config_path),
                       "JBGS_MVS_BINDING": str(self.binding_path),
                       "JBGS_MVS_BINDING_SHA256": sha(self.binding_path)}
        with patch.dict(os.environ, environment):
            return self.integration.from_environment(SimpleNamespace(model_path=str(self.output)),
                                                     SimpleNamespace(), self.pipe, self.args)

    def test_mvs_mode_preserves_exact_native_normal_tensor_without_neighbor_render(self):
        controller = self.controller()
        native = torch.tensor(.75, requires_grad=True)
        value = controller.geometry_loss(None, {}, None, None, None, 8001, native_normal_loss=native)
        self.assertIs(value, native)

    def test_geometry_terms_replace_native_penalty_and_use_native_render_keys(self):
        controller = self.controller("mvs_pgsr")
        controller.cameras = {camera.image_name: camera for camera in self.cameras}
        controller.calibration = {camera.image_name: (torch.eye(3), torch.eye(3), torch.zeros(3))
                                  for camera in self.cameras}
        gaussians = SimpleNamespace(_xyz=torch.tensor([[1., 2., 3.]], requires_grad=True),
                                    _rotation=torch.tensor([[1., 0., 0., 0.]], requires_grad=True),
                                    _scaling=torch.tensor([[.5, .75]], requires_grad=True))
        depth, normal, alpha = torch.full((1, 7, 7), 5.), torch.ones(3, 7, 7), torch.ones(1, 7, 7)
        package = {"surf_depth": depth, "rend_normal": normal, "rend_alpha": alpha}
        losses = {"svgeo": gaussians._rotation.square().sum(),
                  "mvrgb": gaussians._xyz.square().sum(),
                  "mvgeom": gaussians._scaling.square().sum(),
                  "counts": {"sv_valid": 25, "mv_valid": 16, "ncc_valid": 9}}
        native = torch.tensor(123., requires_grad=True)
        renderer = SimpleNamespace(render=lambda *args: package)
        with patch.dict(sys.modules, {"gaussian_renderer": renderer}), \
                patch.object(torch.Tensor, "cuda", lambda value, *a, **kw: value), \
                patch.object(self.integration, "pgsr_geometry_losses", return_value=losses) as call:
            total = controller.geometry_loss(self.cameras[0], package, gaussians, self.pipe, None,
                                             8001, native_normal_loss=native)
        expected = sum(self.config["geometry"][key + "_weight"] * losses[key]
                       for key in ("svgeo", "mvrgb", "mvgeom"))
        torch.testing.assert_close(total, expected)
        self.assertIs(call.call_args.args[0], depth)
        self.assertIs(call.call_args.args[1], normal)
        self.assertIs(call.call_args.args[2], alpha)
        total.backward()
        self.assertEqual(native.grad.item(), 0.)
        self.assertTrue(torch.isfinite(gaussians._xyz.grad).all())
        self.assertTrue((self.output / "geometry_first_step_gradients.json").exists())

    def test_metric_mvs_loader_binds_camera_stems_without_global_rng_draws(self):
        controller = self.controller()
        tensor = torch.tensor
        def cpu_tensor(*args, **kwargs):
            kwargs.pop("device", None)
            return tensor(*args, **kwargs)
        python_state, numpy_state, torch_state = random.getstate(), np.random.get_state(), torch.get_rng_state()
        with patch.object(self.integration.torch, "tensor", cpu_tensor):
            maps = controller.load_mvs_depth_set(self.cameras, (7, 7),
                                                  train_camera_names=[camera.image_name for camera in self.cameras])
        self.assertEqual(set(maps.maps), {"camera_A", "camera_B"})
        self.assertTrue(torch.equal(maps.maps["camera_A"], torch.full((7, 7), 5.)))
        self.assertEqual(controller._seed(8001, "camera_A"), controller._seed(8001, "camera_A"))
        self.assertEqual(python_state, random.getstate())
        np.testing.assert_equal(numpy_state, np.random.get_state())
        self.assertTrue(torch.equal(torch_state, torch.get_rng_state()))

    def test_wrong_actual_pose_rejected_before_depth_transfer(self):
        controller = self.controller()
        self.cameras[0].world_view_transform = self.cameras[0].world_view_transform.clone()
        self.cameras[0].world_view_transform[3, 0] += 1.
        with self.assertRaisesRegex(ValueError, "renderer pose"):
            controller.load_mvs_depth_set(self.cameras, (7, 7),
                                           train_camera_names=[camera.image_name for camera in self.cameras])

    def test_actual_train_membership_must_match_supplemental_train_exactly(self):
        controller = self.controller()
        with self.assertRaises(ValueError):
            controller.load_mvs_depth_set(self.cameras, (7, 7),
                                           train_camera_names=[self.cameras[0].image_name])

    def test_wrong_actual_intrinsics_rejected_before_depth_transfer(self):
        controller = self.controller()
        self.cameras[0].jbgs_source_intrinsics = self.cameras[0].jbgs_source_intrinsics.copy()
        self.cameras[0].jbgs_source_intrinsics[0, 2] += .5
        with self.assertRaises(ValueError):
            controller.load_mvs_depth_set(self.cameras, (7, 7),
                                           train_camera_names=[camera.image_name for camera in self.cameras])

    def test_wrong_actual_raster_rejected_before_depth_transfer(self):
        controller = self.controller()
        self.cameras[0].image_width = 8
        with self.assertRaises(ValueError):
            controller.load_mvs_depth_set(self.cameras, (7, 7),
                                           train_camera_names=[camera.image_name for camera in self.cameras])

    def test_changed_original_scene_identity_rejected(self):
        self.parent_manifest.write_text('{"tampered": true}')
        with self.assertRaisesRegex(ValueError, "Original scene identity"):
            self.controller()

    def test_supplemental_file_hash_change_rejected(self):
        with self.assertRaisesRegex(ValueError, "Frozen supplemental input changed"):
            self.integration._load_bound(self.binding_path, "0" * 64)


class DriverCompletionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location("mvs_phase_driver_fixture",
                    ROOT / "scripts/phd/geogs_mvs_pgsr_v1/run_phase.py")
        cls.driver = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.driver)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.cfg = json.loads((ROOT / "configs/phd/geogs_mvs_pgsr_v1/experiment_v1.json").read_text())
        self.args = SimpleNamespace(region="P2", mode="mvs_pgsr", prior=.005, phase="preflight")
        self.model = self.root / "model"
        self.complete = self.model / "jbgs_complete" / "iteration_8100"
        self.complete.mkdir(parents=True)
        self.restore = {"schema": "JBGS_GEOGS_COMPLETE_STATE_v1", "iteration": 8000,
                        "checkpoint_sha256": self.cfg["anchors"]["P2"]["sha256"],
                        "release": False, "lambda_lod_anchor": .005, "scientific_verdict": None,
                        "restore_equivalence": {"status": "PASS", "scope": "immediate_complete_anchor_restore",
                                                "protection": "native_exact", "scientific_verdict": None,
                                                "model_optimizer_exact": True, "controller_exact": True,
                                                "camera_order_and_stack_exact": True, "rng_exact": True}}
        (self.model / "jbgs_restore.json").write_text(json.dumps(self.restore))
        trace = {"mode": "mvs_pgsr", "visual_source": "COLMAP_MVS_CAMERA_Z", "scientific_verdict": None,
                 "prior_weight": .005, "mvs_weight": .05, "prior_loss": 1., "mvs_loss": 2.,
                 "geometry_weighted_total": .1, "rgb_loss": .2, "counts": {"mv_valid": 20, "ncc_valid": 10}}
        (self.model / "mvs_pgsr_trace.jsonl").write_text("\n".join(
            json.dumps(dict(trace, iteration=iteration)) for iteration in (8001, 8100)))
        (self.complete / "checkpoint.pth").write_bytes(b"synthetic checkpoint byte identity fixture")
        (self.complete / "point_cloud.ply").write_bytes(b"synthetic ply byte identity fixture")
        receipt = {"schema": "JBGS_GEOGS_COMPLETE_STATE_v1", "iteration": 8100,
                   "after_protection_registration": True, "scientific_verdict": None,
                   "checkpoint_sha256": sha(self.complete / "checkpoint.pth"),
                   "ply_sha256": sha(self.complete / "point_cloud.ply")}
        (self.complete / "receipt.json").write_text(json.dumps(receipt))

    def test_complete_identity_validates_and_returns_both_payload_hashes(self):
        result = self.driver.validate_completion(self.root, self.cfg, self.args)
        self.assertEqual(result["final_iteration"], 8100)
        self.assertEqual(len(result["verified_outputs"]), 2)

    def test_final_trace_without_checkpoint_is_rejected(self):
        (self.complete / "checkpoint.pth").unlink()
        with self.assertRaises(FileNotFoundError):
            self.driver.validate_completion(self.root, self.cfg, self.args)

    def test_final_checkpoint_tamper_is_rejected(self):
        (self.complete / "checkpoint.pth").write_bytes(b"tampered")
        with self.assertRaisesRegex(ValueError, "payload changed"):
            self.driver.validate_completion(self.root, self.cfg, self.args)

    def test_incomplete_anchor_restore_is_rejected(self):
        self.restore["restore_equivalence"]["rng_exact"] = False
        (self.model / "jbgs_restore.json").write_text(json.dumps(self.restore))
        with self.assertRaisesRegex(ValueError, "restoration was not verified"):
            self.driver.validate_completion(self.root, self.cfg, self.args)

    def test_driver_and_actual_helper_mode_must_match(self):
        environment = {"JBGS_MVS_PGSR_MODE": "mvs", "JBGS_MVS_REGION": "P2",
                       "JBGS_RUNTIME_IMAGE_ID": self.cfg["runtime_image_id"],
                       "PYTORCH_CUDA_ALLOC_CONF": self.cfg["allocator"]}
        with self.assertRaisesRegex(ValueError, "integration environment"):
            self.driver.validate_runtime_controls(self.cfg, self.args, environment)
        environment["JBGS_MVS_PGSR_MODE"] = "mvs_pgsr"
        self.driver.validate_runtime_controls(self.cfg, self.args, environment)


if __name__ == "__main__":
    unittest.main()
