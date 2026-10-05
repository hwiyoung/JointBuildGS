"""Local complementary metric depth loss for an isolated GeoGS refinement copy.

The ramp measures prior/visual *disagreement*, not relative correctness. Raw
upstream losses remain controller inputs; only the stage-2 objective is replaced.
"""
from __future__ import annotations

import contextlib
import hashlib
import json
import math
import os
from dataclasses import dataclass
from pathlib import Path

import torch


@dataclass(frozen=True)
class LocalDepthConfig:
    mode: str = "disabled"
    tau0: float | None = None
    tau1: float | None = None

    def __post_init__(self):
        if self.mode not in {"disabled", "complementary"}:
            raise ValueError("JBGS_LOCAL_DEPTH_MODE must be disabled or complementary")
        if self.enabled:
            if self.tau0 is None or self.tau1 is None:
                raise ValueError("Enabled local depth requires explicit TAU0 and TAU1")
            if not (math.isfinite(self.tau0) and math.isfinite(self.tau1)
                    and 0 <= self.tau0 < self.tau1):
                raise ValueError("Depth thresholds must be finite and 0 <= tau0 < tau1")

    @property
    def enabled(self):
        return self.mode == "complementary"

    @classmethod
    def from_environment(cls):
        mode = os.environ.get("JBGS_LOCAL_DEPTH_MODE", "disabled")
        if mode == "disabled":
            return cls()
        return cls(mode, float(os.environ["JBGS_LOCAL_TAU0"]),
                   float(os.environ["JBGS_LOCAL_TAU1"]))


def _map(value, pred, name):
    if value is None:
        return None
    if value.shape != pred.shape:
        raise ValueError(f"{name} shape {tuple(value.shape)} != {tuple(pred.shape)}")
    if value.device != pred.device:
        raise ValueError(f"{name} and prediction must be on the same device")
    return value.detach()


def _valid(target, pred, mask):
    if target is None:
        return torch.zeros_like(pred, dtype=torch.bool)
    valid = torch.isfinite(target) & torch.isfinite(pred) & (target > 0)
    return valid if mask is None else valid & (mask > 0)


def _source_loss(pred, target, valid, multipliers, confidence=None):
    # Selecting valid samples *before* subtraction prevents 0 * NaN poisoning.
    selected_pred = pred[valid]
    if selected_pred.numel() == 0:
        return selected_pred.sum(), 0.0, "empty"
    residual = (selected_pred - target[valid]).abs()
    if confidence is not None:
        conf = confidence[valid]
        if not bool(torch.isfinite(conf).all()) or bool((conf < 0).any()):
            raise ValueError("Confidence on valid source pixels must be finite and nonnegative")
        conf_sum = conf.sum()
        if bool(conf_sum > 0):
            denominator = conf_sum + 1e-6  # Exactly the upstream confidence denominator.
            return (residual * conf * multipliers[valid]).sum() / denominator, denominator, "confidence_sum_plus_eps"
    # Do not divide by sum(local weights): attenuation must change objective strength.
    return (residual * multipliers[valid]).mean(), selected_pred.numel(), "valid_pixel_count"


def complementary_depth_losses(pred_depth, prior_depth, visual_depth, *, tau0, tau1,
                                prior_mask=None, visual_mask=None,
                                visual_confidence=None, collect_stats=False):
    """Return source losses with native per-source validity/denominators.

    A source available on its own has local multiplier one. Prediction validity
    follows upstream: negative finite predictions remain valid; targets must >0.
    """
    LocalDepthConfig("complementary", tau0, tau1)
    if pred_depth.ndim == 3 and pred_depth.shape[0] == 1:
        pred = pred_depth.squeeze(0)
    elif pred_depth.ndim == 2:
        pred = pred_depth
    else:
        raise ValueError("Prediction must have shape [1,H,W] or [H,W]")
    prior = _map(prior_depth, pred, "prior")
    visual = _map(visual_depth, pred, "visual")
    prior_mask = _map(prior_mask, pred, "prior_mask")
    visual_mask = _map(visual_mask, pred, "visual_mask")
    confidence = _map(visual_confidence, pred, "visual_confidence")
    with torch.no_grad():
        vp = _valid(prior, pred, prior_mask)
        vv = _valid(visual, pred, visual_mask)
        both = vp & vv
        wp = vp.to(pred.dtype)
        wv = vv.to(pred.dtype)
        # Only valid overlapping samples participate in the disagreement ramp.
        a = torch.empty(0, dtype=pred.dtype, device=pred.device)
        if prior is not None and visual is not None:
            a = ((prior[both] - visual[both]).abs() - tau0).div(tau1 - tau0).clamp(0, 1)
            wp[both] = 1 - a
            wv[both] = a
    lp, dp, dp_kind = _source_loss(pred, prior, vp, wp)
    lv, dv, dv_kind = _source_loss(pred, visual, vv, wv, confidence)
    stats = None
    if collect_stats:
        def scalar(value):
            return float(value.detach().item()) if isinstance(value, torch.Tensor) else float(value)
        stats = {
            "pixels": pred.numel(), "prior_valid": int(vp.sum().item()),
            "visual_valid": int(vv.sum().item()), "both_valid": int(both.sum().item()),
            "prior_only": int((vp & ~vv).sum().item()),
            "visual_only": int((vv & ~vp).sum().item()),
            "neither_valid": int((~vp & ~vv).sum().item()),
            "a_mean_both": scalar(a.mean()) if a.numel() else None,
            "a_zero_both": int((a == 0).sum().item()),
            "a_one_both": int((a == 1).sum().item()),
            "prior_multiplier_mean_valid": scalar(wp[vp].mean()) if bool(vp.any()) else None,
            "visual_multiplier_mean_valid": scalar(wv[vv].mean()) if bool(vv.any()) else None,
            "prior_denominator": scalar(dp), "visual_denominator": scalar(dv),
            "prior_denominator_kind": dp_kind, "visual_denominator_kind": dv_kind,
        }
        # Include source confidence in the effective visual coefficient summary.
        if dv_kind == "confidence_sum_plus_eps":
            stats["visual_effective_multiplier"] = scalar((wv[vv] * confidence[vv]).sum() / dv)
        else:
            stats["visual_effective_multiplier"] = stats["visual_multiplier_mean_valid"]
        stats["prior_effective_multiplier"] = stats["prior_multiplier_mean_valid"]
    return lp, lv, stats


class LocalDepthController:
    def __init__(self, config, model_path, use_scale_invariant=False):
        self.config = config
        self.model_path = Path(model_path)
        self._traced = False
        if config.enabled and use_scale_invariant:
            raise ValueError("Local complementary comparison supports metric depth only")

    @classmethod
    def from_environment(cls, model_path, use_scale_invariant=False):
        return cls(LocalDepthConfig.from_environment(), model_path, use_scale_invariant)

    def raw_loss_context(self, stage2_active):
        # Raw values feed the unchanged upstream adaptive controller and logs.
        return torch.no_grad() if self.config.enabled and stage2_active else contextlib.nullcontext()

    def stage2_losses(self, pred, prior, visual, raw_prior, raw_visual, *, iteration,
                      camera, lambda_prior, lambda_visual, visual_confidence=None,
                      prior_mask=None, visual_mask=None):
        if not self.config.enabled:
            return raw_prior, raw_visual
        if not all(math.isfinite(float(x)) and float(x) >= 0
                   for x in (lambda_prior, lambda_visual)):
            raise ValueError("Depth loss global coefficients must be finite and nonnegative")
        trace = not self._traced or iteration % 100 == 0
        lp, lv, stats = complementary_depth_losses(
            pred, prior, visual, tau0=self.config.tau0, tau1=self.config.tau1,
            prior_mask=prior_mask, visual_mask=visual_mask,
            visual_confidence=visual_confidence, collect_stats=trace)
        if trace:
            row = dict(stats, schema="JBGS_LOCAL_COMPLEMENTARY_TRACE_v1",
                       scientific_verdict=None, iteration=int(iteration), camera=str(camera),
                       mode=self.config.mode, tau0=self.config.tau0, tau1=self.config.tau1,
                       raw_prior_loss=float(raw_prior.detach().item()),
                       raw_visual_loss=float(raw_visual.detach().item()),
                       weighted_prior_loss=float(lp.detach().item()),
                       weighted_visual_loss=float(lv.detach().item()),
                       lambda_prior=float(lambda_prior), lambda_visual=float(lambda_visual))
            for name, coeff in (("prior", lambda_prior), ("visual", lambda_visual)):
                eff = row[name + "_effective_multiplier"]
                row[name + "_effective_global_coefficient"] = None if eff is None else float(coeff) * eff
            row["weighted_depth_total"] = float((lambda_prior * lp + lambda_visual * lv).detach().item())
            with (self.model_path / "local_trace.jsonl").open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(row, allow_nan=False) + "\n")
            self._traced = True
        return lp, lv


def verify_resume_source(state, source_root, current_hashes):
    """Accept only the exact recorded parent anchor and exact prepared runtime."""
    path = Path(source_root) / "local_source_provenance.json"
    receipt = json.loads(path.read_text(encoding="utf-8"))
    if receipt.get("schema") != "JBGS_LOCAL_COMPLEMENTARY_SOURCE_v1":
        raise ValueError("Unrecognized local refinement source provenance")
    if state["source_sha256"] != receipt["parent_implementation_hashes"]["train.py"]:
        raise ValueError("Anchor training source differs from recorded parent")
    if state["implementation_hashes"] != receipt["parent_implementation_hashes"]:
        raise ValueError("Anchor implementation differs from recorded parent")
    if current_hashes != receipt["prepared_implementation_hashes"]:
        raise ValueError("Prepared local refinement implementation changed")
    helper = Path(source_root) / "jbgs_local_depth.py"
    if hashlib.sha256(helper.read_bytes()).hexdigest() != receipt["local_depth_module_sha256"]:
        raise ValueError("Prepared local depth helper changed")
