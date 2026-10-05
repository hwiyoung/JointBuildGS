"""Frozen one-camera R1 multiplier for a GeoGS metric-depth diagnostic.

Copied into a new source snapshot as jbgs_p1_weight.py. Target-camera support is
restricted to frozen manual R1/R2/R3; the other 97 cameras remain unchanged.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import numpy as np
import torch


TARGET_CAMERA = "DJI_20241217084553_0100_D"
PROVENANCE_NAME = "p1_single_view_weight_source_provenance.json"
SOURCE_SCHEMA = "JBGS_P1_SINGLE_VIEW_WEIGHT_SOURCE_v2"


def sha256(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(8 << 20), b""):
            h.update(block)
    return h.hexdigest()


def _write(path, row, mode="x"):
    with Path(path).open(mode) as stream:
        stream.write(json.dumps(row, allow_nan=False) + "\n")


def validate_alpha(alpha):
    if isinstance(alpha, (bool, np.bool_)) or alpha not in (0., 1., 4.):
        raise ValueError("R1 alpha must be exactly 0, 1, or 4")
    return float(alpha)


def load_frozen_mask(path, expected_sha256, key, target_camera):
    if target_camera != TARGET_CAMERA:
        raise ValueError("Frozen intervention target camera differs")
    if key != "r1_mask":
        raise ValueError("The frozen mask key must be r1_mask")
    if sha256(path) != expected_sha256:
        raise ValueError("Frozen R1 mask hash differs")
    with np.load(path, allow_pickle=False) as data:
        if key not in data or "use_mask" not in data:
            raise ValueError("Frozen r1_mask/use_mask key missing")
        mask = np.array(data[key], copy=True)
        use_mask = np.array(data["use_mask"], copy=True)
    if sha256(path) != expected_sha256:
        raise ValueError("Frozen R1 mask changed while loading")
    if mask.dtype != np.dtype(bool) or mask.ndim != 2 or not all(mask.shape):
        raise ValueError("R1 mask must be a nonempty two-dimensional boolean raster")
    if not mask.any():
        raise ValueError("Frozen R1 mask is empty")
    if use_mask.dtype != np.dtype(bool) or use_mask.shape != mask.shape:
        raise ValueError("use_mask must be boolean and match R1 shape")
    if np.any(mask & ~use_mask):
        raise ValueError("R1 must be a subset of frozen use_mask")
    return mask, use_mask


def _maps(pred_depth, target_depth, r1_mask, use_mask):
    pred = pred_depth.squeeze(0) if pred_depth.ndim == 3 and pred_depth.shape[0] == 1 else pred_depth
    if pred.ndim != 2 or target_depth.ndim != 2 or r1_mask.ndim != 2:
        raise ValueError("Depth and R1 must have matching HxW rasters")
    if pred.shape != target_depth.shape or pred.shape != r1_mask.shape:
        raise ValueError("Depth and R1 raster shape differs")
    if r1_mask.dtype != torch.bool:
        raise ValueError("R1 tensor must remain boolean")
    if pred.device != target_depth.device or pred.device != r1_mask.device:
        raise ValueError("Depth and R1 device differs")
    if use_mask.dtype != torch.bool or use_mask.shape != r1_mask.shape:
        raise ValueError("use_mask must be boolean and match R1 shape")
    if use_mask.device != pred.device or bool((r1_mask & ~use_mask).any()):
        raise ValueError("R1 must be a subset of use_mask on the same device")
    valid = torch.isfinite(pred) & torch.isfinite(target_depth) & (target_depth > 0)
    return pred, target_depth.detach(), valid


def weighted_metric_depth_loss(pred_depth, target_depth, r1_mask, alpha, *, use_mask, native_loss=None):
    """Native metric L1 denominator, independent of the R1 multiplier.

    Alpha=1 is a fixed-support baseline, not the original unmasked native loss.
    Finite negative predictions stay valid, as in upstream compute_depth_loss.
    """
    alpha = validate_alpha(alpha)
    pred, target, valid = _maps(pred_depth, target_depth, r1_mask, use_mask)
    residual = (pred[valid] - target[valid]).abs()
    if residual.numel() == 0:
        return pred[valid].sum()
    weight = torch.where(r1_mask[valid], alpha, 1.).to(dtype=pred.dtype)
    weight = weight * use_mask[valid]
    return (residual * weight).mean()


def first_forward_algebra(pred_depth, target_depth, mask, use_mask):
    """Check depth-loss derivatives on one detached prediction, without RNG draws."""
    values, gradients = {}, {}
    for alpha in (0., 1., 4.):
        probe = pred_depth.detach().clone().requires_grad_(True)
        value = weighted_metric_depth_loss(probe, target_depth, mask, alpha, use_mask=use_mask)
        gradients[alpha] = torch.autograd.grad(value, probe)[0]
        values[str(int(alpha))] = float(value.detach().item())
    pred, target, valid = _maps(pred_depth, target_depth, mask, use_mask)
    native_probe = pred_depth.detach().clone().requires_grad_(True)
    native_map = native_probe.squeeze(0) if native_probe.ndim == 3 else native_probe
    native = ((native_map[valid] - target[valid]).abs() * use_mask[valid]).mean()
    native_gradient = torch.autograd.grad(native, native_probe)[0]
    expanded_mask = mask.unsqueeze(0) if pred_depth.ndim == 3 else mask
    expanded_use = use_mask.unsqueeze(0) if pred_depth.ndim == 3 else use_mask
    checks = {
        "alpha1_masked_baseline_value_exact": values["1"] == float(native.detach().item()),
        "alpha1_masked_baseline_gradient_exact": torch.equal(gradients[1.], native_gradient),
        "alpha0_r1_gradient_zero": bool((gradients[0.][expanded_mask] == 0).all()),
        "alpha0_other_used_gradient_exact": torch.equal(gradients[0.][expanded_use & ~expanded_mask], native_gradient[expanded_use & ~expanded_mask]),
        "alpha4_r1_gradient_factor_four": torch.equal(gradients[4.][expanded_mask], 4 * native_gradient[expanded_mask]),
        "alpha4_other_used_gradient_exact": torch.equal(gradients[4.][expanded_use & ~expanded_mask], native_gradient[expanded_use & ~expanded_mask]),
        "excluded_gradient_zero_all_alphas": all(bool((g[~expanded_use] == 0).all()) for g in gradients.values()),
        "all_gradients_finite": all(bool(torch.isfinite(g).all()) for g in gradients.values()),
    }
    if not bool((valid & mask).any()) or not bool((valid & use_mask & ~mask).any()):
        raise ValueError("First target forward must contain valid R1 and other used pixels")
    if not all(checks.values()):
        raise AssertionError("First target depth algebra failed: " + str(checks))
    return {"status": "PASS", "scientific_verdict": None,
            "scope": "detached_prediction_depth_loss_algebra_not_Gaussian_update",
            "checks": checks, "loss_by_alpha": values,
            "valid_count": int(valid.sum()), "valid_r1_count": int((valid & mask).sum()),
            "valid_used_count": int((valid & use_mask).sum()), "valid_excluded_count": int((valid & ~use_mask).sum())}


def _subset_stats(pred, target, selected, denominator, alpha):
    count = int(selected.sum())
    if not count:
        return {"count": 0, "target_mean_m": None, "prediction_mean_m": None,
                "signed_residual_mean_m": None, "abs_residual_mean_m": None,
                "weighted_loss_contribution": 0.}
    p, t = pred[selected], target[selected]
    residual = p - t
    return {"count": count, "target_mean_m": float(t.mean()), "prediction_mean_m": float(p.mean()),
            "signed_residual_mean_m": float(residual.mean()), "abs_residual_mean_m": float(residual.abs().mean()),
            "weighted_loss_contribution": float(alpha * residual.abs().sum() / denominator)}


class Controller:
    def __init__(self, model_path, args, mvs_control, environment=None):
        env = os.environ if environment is None else environment
        if (env.get("JBGS_MVS_PGSR_MODE") != "mvs" or env.get("JBGS_MVS_REGION") != "P1"
                or args.dynamic_depth_weight or args.lambda_da_depth != .05
                or args.lambda_lod_anchor != .005 or args.use_confidence or args.use_scale_invariant
                or args.jbgs_release_protection or args.stage_switch_iter != 8000
                or not args.jbgs_resume_full or not args.freeze_onlybldg or not args.protect_bldg):
            raise ValueError("Require P1 MVS-only, fixed .05 visual/.005 prior, exact protected Anchor8k")
        self.alpha = validate_alpha(float(env["JBGS_P1_WEIGHT_ALPHA"]))
        self.target_camera = env.get("JBGS_P1_WEIGHT_TARGET_CAMERA", TARGET_CAMERA)
        self.mask_path = Path(env["JBGS_P1_WEIGHT_MASK"])
        self.mask_sha256 = env["JBGS_P1_WEIGHT_MASK_SHA256"]
        self.mask_key = env.get("JBGS_P1_WEIGHT_MASK_KEY", "r1_mask")
        mask, use_mask = load_frozen_mask(self.mask_path, self.mask_sha256, self.mask_key, self.target_camera)
        if len(mvs_control.views) != 98 or self.target_camera not in mvs_control.views:
            raise ValueError("Intervention requires exact 98-camera P1 membership and target")
        view = mvs_control.views[self.target_camera]
        if mask.shape != (view["height"], view["width"]):
            raise ValueError("R1 mask shape differs from bound target RGB camera")
        self.mask = torch.from_numpy(mask)
        self.use_mask = torch.from_numpy(use_mask)
        self.output = Path(model_path)
        self.first_target = True
        self.last_iteration = 8000
        self.target_visits = 0
        _write(self.output / "p1_weight_binding.json", {
            "schema": "JBGS_P1_SINGLE_VIEW_WEIGHT_BINDING_v2", "scientific_verdict": None,
            "target_camera": self.target_camera, "alpha": self.alpha,
            "mask_path": str(self.mask_path), "mask_sha256": self.mask_sha256, "mask_key": self.mask_key,
            "mask_shape": list(mask.shape), "r1_pixels": int(mask.sum()), "used_pixels": int(use_mask.sum()),
            "use_mask_key": "use_mask", "r1_subset_of_use": True,
            "fixed_mvs_weight": .05, "fixed_prior_weight": .005, "dynamic_depth_weight": False,
            "other_used_multiplier": 1., "excluded_multiplier": 0., "other_camera_valid_multiplier": 1.,
            "normalization": "original_per_view_valid_pixel_count_with_frozen_support",
            "policy": "annotated_support_v2", "alpha1_baseline": "fixed_support_masked_MVS",
            "train_camera_count": len(mvs_control.views), "native_protection": True,
            "mvs_binding_sha256": mvs_control.binding_sha,
            "rng_policy": "no_random_draws; inherited complete Anchor8k restore and native camera sampling"})

    def apply(self, pred_depth, target_depth, native_loss, *, camera, iteration):
        if iteration != self.last_iteration + 1:
            raise ValueError("Camera trace must follow every resumed iteration consecutively")
        self.last_iteration = iteration
        _write(self.output / "p1_weight_camera_trace.jsonl", {
            "iteration": iteration, "camera": camera, "target": camera == self.target_camera}, "a")
        if iteration == 8001:
            _write(self.output / "p1_weight_first_step.json", {
                "iteration": iteration, "camera": camera, "native_mvs_loss": float(native_loss.detach()),
                "pred_depth_sha256": hashlib.sha256(pred_depth.detach().cpu().contiguous().numpy().tobytes()).hexdigest(),
                "scientific_verdict": None})
        if camera != self.target_camera:
            return native_loss
        if target_depth is None:
            raise ValueError("Frozen target camera has no MVS depth")
        mask = self.mask.to(device=pred_depth.device)
        use_mask = self.use_mask.to(device=pred_depth.device)
        pred, target, valid = _maps(pred_depth, target_depth, mask, use_mask)
        if self.first_target:
            if sha256(self.mask_path) != self.mask_sha256:
                raise ValueError("Frozen R1 mask changed before target forward")
            receipt = first_forward_algebra(pred_depth, target_depth, mask, use_mask)
            receipt.update(iteration=iteration, camera=camera, mask_sha256=self.mask_sha256)
            _write(self.output / "p1_weight_first_target_algebra.json", receipt)
            self.first_target = False
        value = weighted_metric_depth_loss(pred_depth, target_depth, mask, self.alpha, use_mask=use_mask)
        with torch.no_grad():
            baseline = (pred[valid] - target[valid]).abs().mean()
            if not torch.equal(baseline, native_loss.detach()):
                raise ValueError("Selected target raw loss differs from native metric L1")
            self.target_visits += 1
            denominator = int(valid.sum())
            _write(self.output / "p1_weight_target_trace.jsonl", {
                "iteration": iteration, "camera": camera, "target_visit": self.target_visits,
                "alpha": self.alpha, "mvs_weight": .05, "prior_weight": .005,
                "native_valid_count": denominator,
                "native_loss": float(native_loss.detach()), "applied_loss": float(value.detach()),
                "r1": _subset_stats(pred, target, valid & mask, denominator, self.alpha),
                "other_used": _subset_stats(pred, target, valid & use_mask & ~mask, denominator, 1.),
                "excluded": _subset_stats(pred, target, valid & ~use_mask, denominator, 0.),
                "scientific_verdict": None}, "a")
        return value


def verify_resume_source(state, source_root, current_hashes):
    root = Path(source_root)
    receipt = json.loads((root / PROVENANCE_NAME).read_text())
    if receipt.get("schema") != SOURCE_SCHEMA or receipt.get("scientific_verdict") is not None:
        raise ValueError("Unrecognized P1 source provenance")
    if current_hashes != receipt["prepared_implementation_hashes"]:
        raise ValueError("Prepared P1 implementation changed")
    if sha256(root / "mvs_pgsr_source_provenance.json") != receipt["parent_source_provenance_sha256"]:
        raise ValueError("Original MVS source provenance changed")
    allowed = (receipt["ancestor_anchor_implementation_hashes"], receipt["parent_implementation_hashes"],
               receipt["prepared_implementation_hashes"])
    if not any(state["implementation_hashes"] == candidate for candidate in allowed):
        raise ValueError("Checkpoint implementation is outside the exact P1 source lineage")
    if state["source_sha256"] != state["implementation_hashes"]["train.py"]:
        raise ValueError("Checkpoint train hash differs from its implementation mapping")
    for name, expected in receipt["helper_sha256"].items():
        if sha256(root / name) != expected:
            raise ValueError("Prepared P1 helper changed: " + name)
