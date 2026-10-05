"""CPU invariants for the isolated P1 single-view metric-depth intervention."""
import copy
import json
import os
from pathlib import Path
import random
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np
import torch

from src.phd.p1_single_view_weight_v1 import loss
from scripts.phd.p1_single_view_weight_v1 import prepare_source as preparer


class MetricLossTests(unittest.TestCase):
    def setUp(self):
        self.pred = torch.tensor([[[2., 7., -2.], [9., float("nan"), 5.]]], dtype=torch.float64, requires_grad=True)
        self.target = torch.tensor([[1., 4., 3.], [7., 3., float("nan")]], dtype=torch.float64)
        self.mask = torch.tensor([[True, False, False], [True, True, False]])
        self.use_mask = torch.tensor([[True, True, False], [True, True, True]])
        self.valid = torch.isfinite(self.pred[0]) & torch.isfinite(self.target) & (self.target > 0)

    def native(self, pred):
        return ((pred[0][self.valid] - self.target[self.valid]).abs() * self.use_mask[self.valid]).mean()

    def test_alpha_one_matches_fixed_support_baseline_value_and_gradient(self):
        native = self.native(self.pred)
        value = loss.weighted_metric_depth_loss(self.pred, self.target, self.mask, 1, use_mask=self.use_mask)
        self.assertTrue(torch.equal(value, native))
        expected = torch.autograd.grad(native, self.pred, retain_graph=True)[0]
        actual = torch.autograd.grad(value, self.pred)[0]
        self.assertTrue(torch.equal(actual, expected))

    def test_zero_and_four_only_change_selected_valid_pixel_gradients(self):
        native_gradient = torch.autograd.grad(self.native(self.pred), self.pred)[0]
        for alpha in (0., 4.):
            pred = self.pred.detach().clone().requires_grad_(True)
            value = loss.weighted_metric_depth_loss(pred, self.target, self.mask, alpha, use_mask=self.use_mask)
            gradient = torch.autograd.grad(value, pred)[0]
            expanded = self.mask.unsqueeze(0)
            self.assertTrue(torch.equal(gradient[expanded], native_gradient[expanded] * alpha))
            self.assertTrue(torch.equal(gradient[~expanded], native_gradient[~expanded]))
            self.assertTrue((gradient[~self.use_mask.unsqueeze(0)] == 0).all())
            self.assertTrue(torch.isfinite(gradient).all())

    def test_weight_change_keeps_original_valid_pixel_denominator(self):
        pred = torch.full((1, 2, 2), 2., requires_grad=True)
        target = torch.ones(2, 2)
        mask = torch.tensor([[True, True], [False, False]])
        use_mask = torch.tensor([[True, True], [True, False]])
        self.assertEqual(loss.weighted_metric_depth_loss(pred, target, mask, 4, use_mask=use_mask).item(), 2.25)
        self.assertEqual(loss.weighted_metric_depth_loss(pred, target, mask, 0, use_mask=use_mask).item(), .25)

    def test_nan_zero_negative_targets_excluded_but_negative_prediction_valid(self):
        pred = torch.tensor([[[float("nan"), 3., 4., -2.]]], requires_grad=True)
        target = torch.tensor([[1., 0., -1., 3.]])
        mask = torch.ones((1, 4), dtype=torch.bool)
        value = loss.weighted_metric_depth_loss(pred, target, mask, 1, use_mask=mask)
        self.assertEqual(value.item(), 5.)
        gradient = torch.autograd.grad(value, pred)[0]
        self.assertTrue(torch.equal(gradient, torch.tensor([[[0., 0., 0., -1.]]])))

    def test_all_invalid_is_connected_finite_zero(self):
        pred = torch.full((1, 2, 2), float("nan"), requires_grad=True)
        value = loss.weighted_metric_depth_loss(pred, torch.zeros(2, 2), torch.ones(2, 2, dtype=torch.bool), 4,
                                               use_mask=torch.ones(2, 2, dtype=torch.bool))
        self.assertEqual(value.item(), 0.)
        self.assertTrue(torch.equal(torch.autograd.grad(value, pred)[0], torch.zeros_like(pred)))

    def test_shape_boolean_and_alpha_are_fail_closed(self):
        for alpha in (-1, .25, float("nan"), float("inf"), True):
            with self.assertRaises(ValueError):
                loss.weighted_metric_depth_loss(self.pred, self.target, self.mask, alpha, use_mask=self.use_mask)
        with self.assertRaisesRegex(ValueError, "boolean"):
            loss.weighted_metric_depth_loss(self.pred, self.target, self.mask.to(torch.int64), 1, use_mask=self.use_mask)
        with self.assertRaisesRegex(ValueError, "shape"):
            loss.weighted_metric_depth_loss(self.pred, self.target, self.mask[:, :2], 1, use_mask=self.use_mask)

    def test_support_is_required_boolean_and_contains_r1(self):
        with self.assertRaises(TypeError):
            loss.weighted_metric_depth_loss(self.pred, self.target, self.mask, 1)
        with self.assertRaisesRegex(ValueError, "boolean"):
            loss.weighted_metric_depth_loss(self.pred, self.target, self.mask, 1, use_mask=self.use_mask.to(torch.int64))
        with self.assertRaisesRegex(ValueError, "subset"):
            loss.weighted_metric_depth_loss(self.pred, self.target, self.mask, 1, use_mask=~self.mask)

    def test_first_forward_algebra_has_no_rng_or_prediction_side_effects(self):
        py_state, np_state, torch_state = random.getstate(), np.random.get_state(), torch.get_rng_state()
        before = self.pred.detach().clone()
        result = loss.first_forward_algebra(self.pred, self.target, self.mask, self.use_mask)
        self.assertEqual(result["status"], "PASS")
        self.assertTrue(all(result["checks"].values()))
        self.assertEqual(result["valid_count"], 4)
        self.assertEqual(result["valid_r1_count"], 2)
        self.assertEqual(result["valid_excluded_count"], 1)
        torch.testing.assert_close(self.pred, before, equal_nan=True, rtol=0, atol=0)
        self.assertIsNone(self.pred.grad)
        self.assertEqual(random.getstate(), py_state)
        np.testing.assert_equal(np.random.get_state(), np_state)
        self.assertTrue(torch.equal(torch.get_rng_state(), torch_state))


class ControllerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.mask_path = self.root / "mask.npz"
        self.mask = np.array([[True, False, False], [True, False, False]])
        self.use_mask = np.array([[True, True, False], [True, True, False]])
        np.savez_compressed(self.mask_path, r1_mask=self.mask, use_mask=self.use_mask)
        self.env = {"JBGS_MVS_PGSR_MODE": "mvs", "JBGS_MVS_REGION": "P1",
                    "JBGS_P1_WEIGHT_ALPHA": "4", "JBGS_P1_WEIGHT_MASK": str(self.mask_path),
                    "JBGS_P1_WEIGHT_MASK_SHA256": loss.sha256(self.mask_path),
                    "JBGS_P1_WEIGHT_MASK_KEY": "r1_mask", "JBGS_P1_WEIGHT_TARGET_CAMERA": loss.TARGET_CAMERA}
        self.args = SimpleNamespace(dynamic_depth_weight=False, lambda_da_depth=.05,
                                    lambda_lod_anchor=.005, use_confidence=False, use_scale_invariant=False,
                                    jbgs_release_protection=False, stage_switch_iter=8000,
                                    jbgs_resume_full="/anchor/checkpoint.pth", freeze_onlybldg=True, protect_bldg=True)
        views = {f"other_{i}": {"height": 2, "width": 3} for i in range(97)}
        views[loss.TARGET_CAMERA] = {"height": 2, "width": 3}
        self.mvs = SimpleNamespace(views=views, binding_sha="a" * 64)
        self.output_count = 0

    def controller(self):
        self.output_count += 1
        output = self.root / str(self.output_count)
        output.mkdir()
        return loss.Controller(output, self.args, self.mvs, self.env)

    @staticmethod
    def prediction():
        pred = torch.tensor([[[2., 4., 6.], [8., 10., 12.]]], requires_grad=True)
        target = torch.ones(2, 3)
        native = (pred.squeeze(0) - target).abs().mean()
        return pred, target, native

    def test_all_other_cameras_return_native_tensor_without_applying_mask(self):
        controller = self.controller()
        for i in range(97):
            pred, target, native = self.prediction()
            actual = controller.apply(pred, target, native, camera=f"other_{i}", iteration=8001+i)
            self.assertIs(actual, native)
        self.assertFalse((controller.output / "p1_weight_target_trace.jsonl").exists())
        rows = [json.loads(line) for line in (controller.output / "p1_weight_camera_trace.jsonl").read_text().splitlines()]
        self.assertEqual(len(rows), 97)
        self.assertEqual(len({r["camera"] for r in rows}), 97)

    def test_each_target_visit_logs_r1_other_and_fixed_controls(self):
        controller = self.controller()
        for iteration in (8001, 8002):
            pred, target, native = self.prediction()
            value = controller.apply(pred, target, native, camera=loss.TARGET_CAMERA, iteration=iteration)
            self.assertGreater(value.item(), native.item())
        rows = [json.loads(line) for line in (controller.output / "p1_weight_target_trace.jsonl").read_text().splitlines()]
        self.assertEqual([r["target_visit"] for r in rows], [1, 2])
        for row in rows:
            self.assertEqual(row["native_valid_count"], 6)
            self.assertEqual(row["r1"]["count"], 2)
            self.assertEqual(row["other_used"]["count"], 2)
            self.assertEqual(row["excluded"]["count"], 2)
            self.assertEqual(row["excluded"]["weighted_loss_contribution"], 0)
            self.assertEqual(row["mvs_weight"], .05)
            self.assertEqual(row["prior_weight"], .005)
            self.assertAlmostEqual(row["applied_loss"], row["r1"]["weighted_loss_contribution"] + row["other_used"]["weighted_loss_contribution"], places=5)
        algebra = json.loads((controller.output / "p1_weight_first_target_algebra.json").read_text())
        self.assertEqual(algebra["iteration"], 8001)
        self.assertTrue(all(algebra["checks"].values()))

    def test_alpha_one_target_uses_masked_baseline_with_zero_excluded_gradient(self):
        self.env["JBGS_P1_WEIGHT_ALPHA"] = "1"
        controller = self.controller()
        pred, target, native = self.prediction()
        value = controller.apply(pred, target, native, camera=loss.TARGET_CAMERA, iteration=8001)
        self.assertIsNot(value, native)
        self.assertLess(value.item(), native.item())
        expected = ((pred.squeeze(0) - target).abs() * torch.from_numpy(self.use_mask)).mean()
        self.assertTrue(torch.equal(value, expected))
        gradient = torch.autograd.grad(value, pred)[0]
        self.assertTrue((gradient[0][~torch.from_numpy(self.use_mask)] == 0).all())

    def test_global_controls_are_fixed(self):
        for key, value in (("dynamic_depth_weight", True), ("lambda_da_depth", .0475),
                           ("lambda_lod_anchor", .0005), ("use_confidence", True),
                           ("jbgs_release_protection", True), ("protect_bldg", False),
                           ("freeze_onlybldg", False), ("stage_switch_iter", 8100)):
            original = getattr(self.args, key)
            setattr(self.args, key, value)
            with self.assertRaisesRegex(ValueError, "fixed"):
                self.controller()
            setattr(self.args, key, original)
        self.env["JBGS_MVS_PGSR_MODE"] = "mvs_pgsr"
        with self.assertRaises(ValueError):
            self.controller()

    def test_mask_hash_boolean_key_target_and_shape_are_checked(self):
        original = dict(self.env)
        for key, value in (("JBGS_P1_WEIGHT_MASK_SHA256", "0" * 64),
                           ("JBGS_P1_WEIGHT_MASK_KEY", "region_id"),
                           ("JBGS_P1_WEIGHT_TARGET_CAMERA", loss.TARGET_CAMERA + ".JPG")):
            self.env = dict(original, **{key: value})
            with self.assertRaises(ValueError):
                self.controller()
        self.env = original
        np.savez_compressed(self.mask_path, r1_mask=self.mask.astype(np.int64), use_mask=self.use_mask)
        self.env["JBGS_P1_WEIGHT_MASK_SHA256"] = loss.sha256(self.mask_path)
        with self.assertRaisesRegex(ValueError, "boolean"):
            self.controller()
        np.savez_compressed(self.mask_path, r1_mask=np.ones((3, 3), bool), use_mask=np.ones((3, 3), bool))
        self.env["JBGS_P1_WEIGHT_MASK_SHA256"] = loss.sha256(self.mask_path)
        with self.assertRaisesRegex(ValueError, "shape"):
            self.controller()

    def test_mask_mutation_after_initialization_rejected_before_target(self):
        controller = self.controller()
        np.savez_compressed(self.mask_path, r1_mask=~self.mask, use_mask=self.use_mask)
        with self.assertRaisesRegex(ValueError, "changed"):
            controller.apply(*self.prediction(), camera=loss.TARGET_CAMERA, iteration=8001)

    def test_target_membership_and_exact_count_required(self):
        self.mvs.views.pop("other_0")
        with self.assertRaisesRegex(ValueError, "98-camera"):
            self.controller()
        self.mvs.views["unrelated"] = self.mvs.views.pop(loss.TARGET_CAMERA)
        with self.assertRaisesRegex(ValueError, "98-camera"):
            self.controller()

    def test_missing_or_non_boolean_or_non_containing_frozen_support_rejected(self):
        for payload in ({"r1_mask": self.mask},
                        {"r1_mask": self.mask, "use_mask": self.use_mask.astype(np.int64)},
                        {"r1_mask": self.mask, "use_mask": ~self.mask}):
            np.savez_compressed(self.mask_path, **payload)
            self.env["JBGS_P1_WEIGHT_MASK_SHA256"] = loss.sha256(self.mask_path)
            with self.assertRaises(ValueError):
                self.controller()
    def test_non_native_raw_loss_and_missing_iterations_rejected(self):
        controller = self.controller()
        pred, target, native = self.prediction()
        with self.assertRaisesRegex(ValueError, "raw loss"):
            controller.apply(pred, target, native * 2, camera=loss.TARGET_CAMERA, iteration=8001)
        other = self.controller()
        with self.assertRaisesRegex(ValueError, "consecutively"):
            other.apply(*self.prediction(), camera="other_0", iteration=8002)


class SourcePreparationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.parent = self.root / "parent"
        self.parent.mkdir()
        (self.parent / "gaussian_renderer").mkdir()
        (self.parent / "gaussian_renderer/__init__.py").write_text("RENDERER = 'unchanged fixture'\n")
        (self.parent / "train.py").write_text("import jbgs_mvs_pgsr\n\ndef training(dataset, opt, pipe, args):\n" +
            preparer.INIT_BLOCK + "    for iteration in []:\n" + preparer.RAW_BLOCK + "\n")
        (self.parent / "jbgs_state.py").write_text("def restore_state(state, args):\n" +
            preparer.RESUME_IMPORT + preparer.ALLOWED_BLOCK + "\n" +
            "    receipt['restore_equivalence'] = restore_equivalence\n")
        self.expected = preparer.implementation_hashes(self.parent)
        self.ancestor = {"train.py": "b" * 64, "jbgs_state.py": "c" * 64}
        (self.parent / "mvs_pgsr_source_provenance.json").write_text(json.dumps({
            "schema": "JBGS_GEOGS_MVS_PGSR_SOURCE_v1", "scientific_verdict": None,
            "prepared_implementation_hashes": self.expected, "parent_implementation_hashes": self.ancestor}))

    def prepare(self):
        destination = self.root / "prepared"
        with patch.dict(preparer.EXPECTED_PARENT, self.expected, clear=True):
            receipt = preparer.prepare_source(self.parent, destination)
        return destination, receipt

    def test_preparation_preserves_parent_and_limits_changed_files(self):
        before = preparer.payload_hashes(self.parent)
        destination, receipt = self.prepare()
        self.assertEqual(preparer.payload_hashes(self.parent), before)
        self.assertEqual(receipt["changed_parent_files"], ["jbgs_state.py", "train.py"])
        self.assertEqual(receipt["added_files"], ["jbgs_p1_weight.py"])
        self.assertEqual((destination / "mvs_pgsr_source_provenance.json").read_bytes(),
                         (self.parent / "mvs_pgsr_source_provenance.json").read_bytes())
        self.assertEqual((destination / "gaussian_renderer/__init__.py").read_bytes(),
                         (self.parent / "gaussian_renderer/__init__.py").read_bytes())
        self.assertEqual(receipt["prepared_implementation_hashes"], preparer.implementation_hashes(destination))
        self.assertEqual(receipt["prepared_payload_hashes"], preparer.payload_hashes(destination))
        self.assertIn("{'dynamic_depth_weight'}", (destination / "jbgs_state.py").read_text())

    def test_resume_accepts_exact_anchor_and_prepared_lineages_only(self):
        destination, receipt = self.prepare()
        current = preparer.implementation_hashes(destination)
        for hashes in (self.ancestor, self.expected, current):
            state = {"implementation_hashes": hashes, "source_sha256": hashes["train.py"]}
            loss.verify_resume_source(state, destination, current)
        unrelated = {"train.py": "d" * 64}
        with self.assertRaisesRegex(ValueError, "lineage"):
            loss.verify_resume_source({"implementation_hashes": unrelated, "source_sha256": unrelated["train.py"]}, destination, current)
        with self.assertRaisesRegex(ValueError, "train hash"):
            loss.verify_resume_source({"implementation_hashes": self.ancestor, "source_sha256": "0" * 64}, destination, current)

    def test_prepared_code_or_original_provenance_tamper_rejected(self):
        destination, receipt = self.prepare()
        state = {"implementation_hashes": self.ancestor, "source_sha256": self.ancestor["train.py"]}
        helper = destination / "jbgs_p1_weight.py"
        helper.write_text(helper.read_text() + "\n# changed\n")
        with self.assertRaisesRegex(ValueError, "implementation changed"):
            loss.verify_resume_source(state, destination, preparer.implementation_hashes(destination))
        helper.write_bytes(Path(loss.__file__).read_bytes())
        (destination / "mvs_pgsr_source_provenance.json").write_text("{}")
        with self.assertRaisesRegex(ValueError, "provenance changed"):
            loss.verify_resume_source(state, destination, preparer.implementation_hashes(destination))

    def test_tampered_parent_or_existing_destination_fails_closed(self):
        destination, _ = self.prepare()
        with self.assertRaises(FileExistsError):
            preparer.prepare_source(self.parent, destination)
        path = self.parent / "train.py"
        path.write_text(path.read_text() + "\n# changed\n")
        with self.assertRaisesRegex(ValueError, "frozen MVS receipt"):
            preparer.prepare_source(self.parent, self.root / "bad")
        self.assertFalse((self.root / "bad").exists())

    @unittest.skipUnless(os.environ.get("JBGS_P1_TEST_PARENT"), "Exact parent mounted only for pinned-source validation")
    def test_actual_pinned_parent_can_be_prepared_without_mutation(self):
        parent = Path(os.environ["JBGS_P1_TEST_PARENT"])
        before = preparer.payload_hashes(parent)
        destination = self.root / "actual_prepared"
        receipt = preparer.prepare_source(parent, destination)
        self.assertEqual(before, preparer.payload_hashes(parent))
        self.assertEqual(receipt["changed_parent_files"], ["jbgs_state.py", "train.py"])
        self.assertEqual(receipt["added_files"], ["jbgs_p1_weight.py"])
        self.assertIn("from jbgs_mvs_pgsr_source import verify_restored_anchor", (destination / "jbgs_state.py").read_text())
        for hashes in (receipt["ancestor_anchor_implementation_hashes"], receipt["prepared_implementation_hashes"]):
            loss.verify_resume_source({"implementation_hashes": hashes, "source_sha256": hashes["train.py"]},
                                      destination, preparer.implementation_hashes(destination))


if __name__ == "__main__":
    unittest.main()
