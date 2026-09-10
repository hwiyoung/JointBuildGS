"""CPU checks of objective meaning, gradient routing and anchor provenance."""
import json
import ast
import copy
import importlib.util
import os
import random
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace

import numpy as np
import torch

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts/phd/local_complementary_refinement_v1"))
from local_depth_loss_v2 import (LocalDepthConfig, LocalDepthController,
                                 complementary_depth_losses, verify_resume_source,
                                 verify_restored_anchor)
from prepare_source_v2 import (RAW_BLOCK, STAGE2_BLOCK, RESTORE_BLOCK,
                               RESTORE_RNG_BLOCK, RESTORE_RECEIPT_BLOCK,
                               implementation_hashes, prepare_source)

NATIVE = Path(os.environ.get("JBGS_NATIVE_SOURCE", "/parent_source"))


def native_function(name, relative="train.py"):
    tree = ast.parse((NATIVE / relative).read_text())
    matches = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == name]
    if len(matches) != 1:
        raise ValueError("Expected exact native function " + name)
    module = ast.Module(body=matches, type_ignores=[])
    namespace = {"torch": torch}
    exec(compile(module, str(NATIVE / relative), "exec"), namespace)
    return namespace[name]


def tensor(values, grad=False):
    return torch.tensor([values], dtype=torch.float64, requires_grad=grad)


class LocalDepthLossTests(unittest.TestCase):
    def test_ramp_saturation_exact_multipixel_loss_and_unequal_lambda_gradient(self):
        pred = tensor([12, 12, 12, 12], grad=True)
        lp, lv, stats = complementary_depth_losses(
            pred, tensor([10, 10, 10, 10]), tensor([10, 11, 12, 14]),
            tau0=1, tau1=3, collect_stats=True)
        self.assertEqual(lp.item(), 1.25)
        self.assertEqual(lv.item(), 0.5)
        self.assertEqual(stats["a_mean_both"], 0.375)
        self.assertEqual(stats["a_zero_both"], 2)
        self.assertEqual(stats["a_one_both"], 1)
        (2 * lp + 3 * lv).backward()
        torch.testing.assert_close(pred.grad, tensor([0.5, 0.5, 0.25, -0.75]))

    def test_identical_targets_are_still_supervised_at_a_zero(self):
        pred = tensor([12], grad=True)
        lp, lv, _ = complementary_depth_losses(
            pred, tensor([10]), tensor([10]), tau0=0, tau1=2)
        self.assertEqual(lp.item(), 2)
        self.assertEqual(lv.item(), 0)
        (0.005 * lp + 0.05 * lv).backward()
        self.assertAlmostEqual(pred.grad.item(), 0.005)

    def test_zero_prior_lambda_leaves_only_spatially_gated_visual_loss(self):
        pred = tensor([11, 11], grad=True)
        lp, lv, _ = complementary_depth_losses(
            pred, tensor([10, 10]), tensor([10, 14]), tau0=1, tau1=3)
        (0 * lp + 0.05 * lv).backward()
        torch.testing.assert_close(pred.grad, tensor([0, -0.025]))

    def test_masks_missing_sources_and_nonfinite_prediction(self):
        pred = tensor([9, 12, 11, 14, float("nan")], grad=True)
        lp, lv, stats = complementary_depth_losses(
            pred, tensor([10, float("nan"), 10, 0, 8]),
            tensor([12, 11, float("nan"), 13, 10]),
            prior_mask=tensor([1, 1, 0, 1, 1]),
            visual_mask=tensor([0, 1, 1, 1, 1]),
            tau0=1, tau1=3, collect_stats=True)
        self.assertEqual(lp.item(), 1)
        self.assertEqual(lv.item(), 1)
        self.assertEqual(stats["both_valid"], 0)
        self.assertEqual(stats["prior_only"], 1)
        self.assertEqual(stats["visual_only"], 2)
        self.assertIsNone(stats["a_mean_both"])
        (lp + lv).backward()
        torch.testing.assert_close(pred.grad, tensor([-1, 0.5, 0, 0.5, 0]))

    def test_missing_entire_map_uses_other_map_at_full_weight(self):
        pred = tensor([4, 7], grad=True)
        lp, lv, _ = complementary_depth_losses(
            pred, None, tensor([2, 4]), tau0=1, tau1=3)
        self.assertEqual(lp.item(), 0)
        self.assertEqual(lv.item(), 2.5)
        (lp + lv).backward()
        torch.testing.assert_close(pred.grad, tensor([0.5, 0.5]))

    def test_negative_prediction_matches_native_validity_not_target_validity(self):
        pred = tensor([-1, -1, float("inf")], grad=True)
        lp, lv, stats = complementary_depth_losses(
            pred, tensor([2, -2, 3]), None, tau0=1, tau1=3, collect_stats=True)
        self.assertEqual(lp.item(), 3)
        self.assertEqual(lv.item(), 0)
        self.assertEqual(stats["prior_valid"], 1)
        (lp + lv).backward()
        torch.testing.assert_close(pred.grad, tensor([-1, 0, 0]))

    def test_all_invalid_maps_give_finite_zero_gradient(self):
        pred = tensor([float("nan"), 5], grad=True)
        lp, lv, _ = complementary_depth_losses(
            pred, tensor([4, float("nan")]), tensor([0, -1]), tau0=1, tau1=3)
        self.assertEqual((lp + lv).item(), 0)
        (lp + lv).backward()
        torch.testing.assert_close(pred.grad, tensor([0, 0]))

    def test_confidence_denominator_stays_native_after_attenuation(self):
        pred = tensor([11, 11], grad=True)
        lp, lv, stats = complementary_depth_losses(
            pred, tensor([10, 10]), tensor([12, 14]),
            visual_confidence=tensor([2, 6]), tau0=0, tau1=4, collect_stats=True)
        self.assertAlmostEqual(lv.item(), 19 / (8 + 1e-6))
        self.assertAlmostEqual(stats["visual_denominator"], 8 + 1e-6)
        lv.backward()
        torch.testing.assert_close(pred.grad, tensor([-1 / (8 + 1e-6), -6 / (8 + 1e-6)]))

    def test_zero_confidence_sum_keeps_native_unweighted_fallback(self):
        lp, lv, stats = complementary_depth_losses(
            tensor([11, 11]), tensor([10, 10]), tensor([12, 14]),
            visual_confidence=tensor([0, 0]), tau0=0, tau1=4, collect_stats=True)
        self.assertEqual(lv.item(), 1.75)
        self.assertEqual(stats["visual_denominator_kind"], "valid_pixel_count")

    def test_target_and_confidence_receive_no_gradient(self):
        pred, prior, visual, conf = [tensor([x], grad=True) for x in (11, 10, 12, 1)]
        lp, lv, _ = complementary_depth_losses(
            pred, prior, visual, visual_confidence=conf, tau0=0, tau1=4)
        (lp + lv).backward()
        self.assertIsNone(prior.grad)
        self.assertIsNone(visual.grad)
        self.assertIsNone(conf.grad)

    def test_threshold_and_confidence_validation(self):
        for tau0, tau1 in [(-1, 2), (2, 2), (3, 2), (0, float("nan")), (0, float("inf"))]:
            with self.subTest(tau0=tau0, tau1=tau1), self.assertRaises(ValueError):
                LocalDepthConfig("complementary", tau0, tau1)
        for conf in (-1, float("nan")):
            with self.subTest(conf=conf), self.assertRaises(ValueError):
                complementary_depth_losses(tensor([1]), None, tensor([2]),
                    visual_confidence=tensor([conf]), tau0=0, tau1=2)

    def test_disabled_preserves_original_loss_objects_and_stage1_autograd(self):
        with tempfile.TemporaryDirectory() as tmp:
            control = LocalDepthController(LocalDepthConfig(), tmp)
            rp, rv = tensor([3], True).sum(), tensor([4], True).sum()
            actual = control.stage2_losses(None, None, None, rp, rv,
                iteration=8001, camera="c", lambda_prior=0.005, lambda_visual=0.05)
            self.assertIs(actual[0], rp)
            self.assertIs(actual[1], rv)
            self.assertFalse((Path(tmp) / "local_trace.jsonl").exists())
            with control.raw_loss_context(True):
                self.assertTrue(torch.is_grad_enabled())
            enabled = LocalDepthController(LocalDepthConfig("complementary", 0, 2), tmp)
            with enabled.raw_loss_context(False):
                self.assertTrue(torch.is_grad_enabled())
            with enabled.raw_loss_context(True):
                self.assertFalse(torch.is_grad_enabled())

    def test_environment_only_configuration_and_invalid_mode(self):
        with patch.dict(os.environ, {"JBGS_LOCAL_DEPTH_MODE": "complementary",
                                   "JBGS_LOCAL_TAU0": "1", "JBGS_LOCAL_TAU1": "3"}):
            cfg = LocalDepthConfig.from_environment()
            self.assertEqual((cfg.tau0, cfg.tau1), (1, 3))
        with self.assertRaises(ValueError):
            LocalDepthConfig("typo")
        with self.assertRaises(ValueError):
            LocalDepthController(LocalDepthConfig("complementary", 0, 2), "/tmp", True)

    def test_trace_first_and_every_hundred_and_negative_global_coefficient(self):
        with tempfile.TemporaryDirectory() as tmp:
            control = LocalDepthController(LocalDepthConfig("complementary", 0, 2), tmp)
            pred, prior, visual = tensor([11], True), tensor([10]), tensor([12])
            for iteration in (8001, 8002, 8100):
                control.stage2_losses(pred, prior, visual, tensor([1]).sum(), tensor([1]).sum(),
                    iteration=iteration, camera="c", lambda_prior=0.005, lambda_visual=0.05)
            rows = [json.loads(line) for line in (Path(tmp) / "local_trace.jsonl").read_text().splitlines()]
            self.assertEqual([row["iteration"] for row in rows], [8001, 8100])
            self.assertEqual(rows[0]["weighted_depth_total"], 0.05)
            self.assertEqual(rows[0]["prior_effective_global_coefficient"], 0)
            with self.assertRaises(ValueError):
                control.stage2_losses(pred, prior, visual, tensor([1]), tensor([1]),
                    iteration=8101, camera="c", lambda_prior=-1, lambda_visual=0.05)


class SourcePreparationTests(unittest.TestCase):
    def test_copy_patch_exact_provenance_and_tamper_rejection(self):
        with tempfile.TemporaryDirectory() as tmp:
            parent, destination = Path(tmp) / "parent", Path(tmp) / "prepared"
            parent.mkdir()
            train = ("import jbgs_state\ndef training(dataset, args):\n"
                     "    tb_writer = prepare_output_and_logger(dataset)\n"
                     "    for iteration in range(1):\n" + RAW_BLOCK +
                     "\n        if True:\n" + STAGE2_BLOCK + "\n")
            (parent / "train.py").write_text(train)
            (parent / "jbgs_state.py").write_text("def restore_state(state):\n" + RESTORE_BLOCK + "\n"
                + RESTORE_RNG_BLOCK + RESTORE_RECEIPT_BLOCK + "        pass\n")
            before = implementation_hashes(parent)
            receipt = prepare_source(parent, destination)
            self.assertEqual(implementation_hashes(parent), before)
            self.assertEqual((parent / "train.py").read_text(), train)
            state = {"source_sha256": before["train.py"], "implementation_hashes": before}
            verify_resume_source(state, destination, implementation_hashes(destination))
            self.assertEqual(receipt["parent_implementation_hashes"], before)
            self.assertIn("jbgs_local_depth.py", receipt["prepared_implementation_hashes"])
            with self.assertRaises(FileExistsError):
                prepare_source(parent, destination)
            with self.assertRaises(ValueError):
                verify_resume_source(dict(state, source_sha256="wrong"), destination,
                                     implementation_hashes(destination))
            with (destination / "train.py").open("a") as handle:
                handle.write("# changed\n")
            with self.assertRaises(ValueError):
                verify_resume_source(state, destination, implementation_hashes(destination))

    def test_bad_patch_source_creates_no_destination(self):
        with tempfile.TemporaryDirectory() as tmp:
            parent, destination = Path(tmp) / "parent", Path(tmp) / "prepared"
            parent.mkdir()
            (parent / "train.py").write_text("# unrelated source\n")
            (parent / "jbgs_state.py").write_text("# unrelated source\n")
            with self.assertRaises(ValueError):
                prepare_source(parent, destination)
            self.assertFalse(destination.exists())

    def test_symlink_cannot_escape_preserved_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            parent = Path(tmp) / "parent"
            parent.mkdir()
            (parent / "external.py").symlink_to("/tmp/unowned.py")
            with self.assertRaisesRegex(ValueError, "symlinks"):
                prepare_source(parent, Path(tmp) / "prepared")


@unittest.skipUnless(NATIVE.is_dir(), "native snapshot must be mounted for source integration")
class NativeSourceIntegrationTests(unittest.TestCase):
    def test_each_single_source_matches_exact_native_loss_and_gradient(self):
        native = native_function("compute_depth_loss")
        for source in ("prior", "visual"):
            for confidence in (None, tensor([2, 0, 6, 1]), tensor([0, 0, 0, 0])):
                if source == "prior" and confidence is not None:
                    continue
                with self.subTest(source=source, confidence=confidence):
                    prediction = tensor([11, -1, 13, float("inf")], True)
                    target = tensor([10, 4, 0, 5])
                    expected = native(prediction.unsqueeze(0), target, conf_map=confidence)
                    reference_gradient = torch.autograd.grad(expected, prediction)[0]
                    lp, lv, _ = complementary_depth_losses(
                        prediction, target if source == "prior" else None,
                        target if source == "visual" else None, visual_confidence=confidence,
                        tau0=.5, tau1=2)
                    actual = lp if source == "prior" else lv
                    torch.testing.assert_close(actual, expected, rtol=0, atol=0)
                    torch.testing.assert_close(torch.autograd.grad(actual, prediction)[0], reference_gradient, rtol=0, atol=0)

    def test_raw_native_controller_values_survive_no_grad(self):
        native = native_function("compute_depth_loss")
        with tempfile.TemporaryDirectory() as tmp:
            control = LocalDepthController(LocalDepthConfig("complementary", .5, 2), tmp)
            prediction, prior, visual = tensor([11, 22, 31], True), tensor([10, 20, 30]), tensor([12, 25, 30])
            reference = [native(prediction.unsqueeze(0), target) for target in (prior, visual)]
            with control.raw_loss_context(True):
                raw = [native(prediction.unsqueeze(0), target) for target in (prior, visual)]
            for actual, expected in zip(raw, reference):
                self.assertFalse(actual.requires_grad)
                torch.testing.assert_close(actual, expected, rtol=0, atol=0)
            lp, lv = control.stage2_losses(prediction, prior, visual, *raw, iteration=8001,
                camera="c", lambda_prior=.005, lambda_visual=.05,
                controller_state={"phase": 1, "last_check": 8000, "locked_weight": None},
                rgb_loss=tensor([.2]).sum(), gaussian_count=123, protected_count=lambda: 70)
            self.assertTrue(lp.requires_grad and lv.requires_grad)
            row = json.loads((Path(tmp) / "local_trace.jsonl").read_text())
            self.assertEqual(row["controller_state"]["phase"], 1)
            self.assertEqual(row["protected"], 70)
            self.assertEqual(row["gaussians"], 123)
            self.assertEqual(row["resource_sample_phase"], "stage2_objective_before_backward")

    def test_preparation_changes_only_declared_files_and_native_loss_function_is_identical(self):
        with tempfile.TemporaryDirectory() as tmp:
            prepared = Path(tmp) / "source"
            receipt = prepare_source(NATIVE, prepared)
            self.assertEqual(receipt["changed_parent_files"], ["jbgs_state.py", "train.py"])
            self.assertEqual(receipt["added_files"], ["jbgs_local_depth.py"])
            for name in ("compute_depth_loss", "attenuate_building_xyz_lr", "attenuate_building_other_lr"):
                definitions = []
                for root in (NATIVE, prepared):
                    tree = ast.parse((root / "train.py").read_text())
                    definitions.append(ast.dump(next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == name)))
                self.assertEqual(*definitions)

    def test_native_and_prepared_full_restore_preserve_state_and_declared_release(self):
        # Execute both native restore_state and patched restore_state on CPU. Only
        # CUDA RNG I/O is mocked; native model capture/restore and torch Adam's
        # optimizer state_dict/load_state_dict are actually exercised.
        import local_depth_loss_v2
        methods = ast.parse((NATIVE / "scene/gaussian_model.py").read_text())
        original_class = next(node for node in methods.body if isinstance(node, ast.ClassDef) and node.name == "GaussianModel")
        selected = [node for node in original_class.body if isinstance(node, ast.FunctionDef) and node.name in {"capture", "restore"}]
        namespace = {}
        exec(compile(ast.Module(body=selected, type_ignores=[]), "native_model_methods", "exec"), namespace)
        class CPUModel:
            capture = namespace["capture"]
            restore = namespace["restore"]
            def training_setup(self, opt):
                self.xyz_gradient_accum = torch.zeros((2, 1))
                self.denom = torch.zeros((2, 1))
                self.optimizer = torch.optim.Adam([self._xyz, self._features_dc, self._features_rest,
                                                  self._scaling, self._rotation, self._opacity], lr=opt.lr)
            def set_frozen_mask(self, mask):
                self.frozen_mask = mask
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            prepared = root / "source"
            prepare_source(NATIVE, prepared)
            input_manifest = root / "input.json"
            input_manifest.write_text('{"training_only": true}')
            checkpoint = root / "checkpoint.pth"
            checkpoint.write_bytes(b"CPU test uses mocked torch.load; native digest remains live")
            opt = SimpleNamespace(lr=.003)
            original = CPUModel()
            original.active_sh_degree, original.spatial_lr_scale = 2, 5.
            for name in ("_xyz", "_features_dc", "_features_rest", "_scaling", "_rotation", "_opacity"):
                setattr(original, name, torch.nn.Parameter(torch.arange(6, dtype=torch.float32).reshape(2, 3)))
            original.max_radii2D = torch.tensor([2., 3.])
            original.training_setup(opt)
            sum(p.square().sum() for group in original.optimizer.param_groups for p in group["params"]).backward()
            original.optimizer.step()
            original.xyz_gradient_accum[:] = 7
            original.denom[:] = 2
            hashes = implementation_hashes(NATIVE)
            state = dict(schema="JBGS_GEOGS_COMPLETE_STATE_v1", iteration=8000,
                source_sha256=hashes["train.py"], implementation_hashes=hashes,
                model=copy.deepcopy(original.capture()), optimization=vars(opt),
                args={}, input_manifest_sha256=__import__("hashlib").sha256(input_manifest.read_bytes()).hexdigest(),
                frozen_mask=torch.tensor([True, False]), completed_mask=None,
                building_freeze_mask=torch.tensor([True, False]),
                runtime={"freeze_done": True, "da_phase": 1, "da_weight": .05, "da_depth_history": [2., 3.]},
                hook_state={"release": False, "xyz": .001, "rotation_scale": .01},
                train_order=["b", "a"], test_order=["t"], viewpoint_stack=["a"],
                rng={"python": random.getstate(), "numpy": np.random.get_state(),
                     "torch_cpu": torch.get_rng_state(), "torch_cuda": []})
            for source in (NATIVE, prepared):
                for release in (False, True):
                    with self.subTest(source=str(source), release=release):
                        module_spec = importlib.util.spec_from_file_location("state_under_test", source / "jbgs_state.py")
                        module = importlib.util.module_from_spec(module_spec)
                        module_spec.loader.exec_module(module)
                        output = root / (source.name + str(release))
                        output.mkdir()
                        args = SimpleNamespace(stage_switch_iter=8000, jbgs_release_protection=release,
                            lod2_building_xyz_lr_scale=1. if release else .001,
                            protect_bldg_lr_scale=1. if release else .01, protect_bldg=True,
                            jbgs_input_manifest=str(input_manifest), model_path=str(output), lambda_lod_anchor=.005)
                        train_cams, test_cams = [SimpleNamespace(image_name=n) for n in ("a", "b")], [SimpleNamespace(image_name="t")]
                        scene = SimpleNamespace(getTrainCameras=lambda: train_cams, getTestCameras=lambda: test_cams)
                        model = CPUModel()
                        env = dict(args=args, gaussians=model, scene=scene, opt=opt)
                        hooks = []
                        functions = {name: (lambda g, m, s, name=name: hooks.append((name, s))) for name in
                                     ("attenuate_building_xyz_lr", "attenuate_building_other_lr")}
                        with patch.object(torch, "load", return_value=copy.deepcopy(state)), \
                             patch.object(torch.cuda, "set_rng_state_all"), patch.object(torch.cuda, "get_rng_state_all", return_value=[]), \
                             patch.dict(sys.modules, {"jbgs_local_depth": local_depth_loss_v2}):
                            restored = module.restore_state(checkpoint, env, functions)
                            equality = verify_restored_anchor(state, env, restored)
                            self.assertEqual(equality["status"], "PASS")
                            self.assertEqual(len(hooks), 0 if release else 2)
                            if source == prepared:
                                receipt = json.loads((output / "jbgs_restore.json").read_text())
                                self.assertEqual(receipt["restore_equivalence"], equality)
                            restored["da_weight"] = .0001
                            with self.assertRaisesRegex(ValueError, "runtime.da_weight"):
                                verify_restored_anchor(state, env, restored)


if __name__ == "__main__":
    unittest.main()
