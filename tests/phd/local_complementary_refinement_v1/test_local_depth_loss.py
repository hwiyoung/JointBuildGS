"""CPU checks of objective meaning, gradient routing and anchor provenance."""
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import torch

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts/phd/local_complementary_refinement_v1"))
from local_depth_loss import (LocalDepthConfig, LocalDepthController,
                              complementary_depth_losses, verify_resume_source)
from prepare_source import (RAW_BLOCK, STAGE2_BLOCK, RESTORE_BLOCK,
                            implementation_hashes, prepare_source)


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
            (parent / "jbgs_state.py").write_text("def restore_state(state):\n" + RESTORE_BLOCK + "\n")
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


if __name__ == "__main__":
    unittest.main()
