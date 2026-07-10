"""Densification wrapper around gsplat.DefaultStrategy.

gsplat's DefaultStrategy expects the model parameters as a dict of nn.Parameter,
keyed by the names it operates on: means, scales, quats, opacities, sh0, shN.
We expose the GaussianModel2D attributes through a small adapter that mutates
them in-place when the strategy prunes/splits/clones.
"""
from __future__ import annotations

from typing import Dict, Tuple

import torch
import torch.nn as nn
from gsplat.strategy import DefaultStrategy
from gsplat.strategy.ops import duplicate, remove, split

from .model import GaussianModel2D


PARAM_NAMES = ("means", "quats", "log_scales", "opacities_raw", "sh0", "shN")


def build_param_dict(model: GaussianModel2D) -> Dict[str, nn.Parameter]:
    params = {
        "means": model.means,
        "scales": model.log_scales,        # gsplat treats as raw; monotonic via exp at render
        "quats": model.quats,
        "opacities": model.opacities_raw,
        "sh0": model.sh0,
        "shN": model.shN,
    }
    if hasattr(model, "sem_logits"):
        params["sem_logits"] = model.sem_logits
    return params


def build_optimizers(
    model: GaussianModel2D,
    lr_means: float = 1.6e-4,
    lr_scales: float = 5e-3,
    lr_quats: float = 1e-3,
    lr_opacities: float = 5e-2,
    lr_sh0: float = 2.5e-3,
    lr_shN: float = 1.25e-4,
    lr_sem: float = 2.5e-3,
) -> Dict[str, torch.optim.Optimizer]:
    """One Adam per param (gsplat strategy assumption)."""
    opts = {
        "means": torch.optim.Adam([model.means], lr=lr_means),
        "scales": torch.optim.Adam([model.log_scales], lr=lr_scales),
        "quats": torch.optim.Adam([model.quats], lr=lr_quats),
        "opacities": torch.optim.Adam([model.opacities_raw], lr=lr_opacities),
        "sh0": torch.optim.Adam([model.sh0], lr=lr_sh0),
        "shN": torch.optim.Adam([model.shN], lr=lr_shN),
    }
    if hasattr(model, "sem_logits"):
        opts["sem_logits"] = torch.optim.Adam([model.sem_logits], lr=lr_sem)
    return opts


def build_strategy(
    prune_opa: float = 0.005,
    grow_grad2d: float = 2e-4,
    grow_scale3d: float = 0.01,
    prune_scale3d: float = 0.1,
    refine_start_iter: int = 500,
    refine_stop_iter: int = 15000,
    refine_every: int = 100,
    reset_every: int = 3000,
    absgrad: bool = False,
) -> DefaultStrategy:
    return DefaultStrategy(
        key_for_gradient="gradient_2dgs",   # 2DGS uses gradient_2dgs, not means2d
        prune_opa=prune_opa,
        grow_grad2d=grow_grad2d,
        grow_scale3d=grow_scale3d,
        prune_scale3d=prune_scale3d,
        refine_start_iter=refine_start_iter,
        refine_stop_iter=refine_stop_iter,
        refine_every=refine_every,
        reset_every=reset_every,
        absgrad=absgrad,
        verbose=False,
    )


class SeedProtectStrategy(DefaultStrategy):
    """DefaultStrategy with optional MVS-seed opacity-prune protection.

    Seeds are flagged by a bool tensor in ``state["is_seed"]`` registered at init. gsplat's
    remove/duplicate/split (ops.py) carry every per-Gaussian ``state`` tensor in lockstep with the
    params, so the flag stays aligned automatically (seed lineage children inherit it).
    Only ``_prune_gs`` is overridden: identical to gsplat 1.4.0 DefaultStrategy._prune_gs but with
    an optional ``is_prune &= ~is_seed`` while protection is active.
    PINNED to gsplat 1.4.0 prune logic — re-sync if gsplat is upgraded.
    """

    seed_protect_until_iter: int | None = None

    def _prune_gs(self, params, optimizers, state, step):  # type: ignore[override]
        import torch as _torch

        is_prune = _torch.sigmoid(params["opacities"].flatten()) < self.prune_opa
        if step > self.reset_every:
            is_too_big = (
                _torch.exp(params["scales"]).max(dim=-1).values
                > self.prune_scale3d * state["scene_scale"]
            )
            if step < self.refine_scale2d_stop_iter:
                is_too_big |= state["radii"] > self.prune_scale2d
            is_prune = is_prune | is_too_big

        n_candidate = int(is_prune.sum().item())
        is_seed = state.get("is_seed")
        protect_active = is_seed is not None and (
            self.seed_protect_until_iter is None or step < int(self.seed_protect_until_iter)
        )
        n_seed_protected = 0
        if protect_active:
            n_seed_protected = int((is_prune & is_seed).sum().item())
            is_prune = is_prune & (~is_seed)   # protect MVS seeds (+ their lineage)

        n_prune = int(is_prune.sum().item())
        if n_prune > 0:
            remove(params=params, optimizers=optimizers, state=state, mask=is_prune)
        state["last_prune_step"] = int(step)
        state["last_prune_candidates"] = n_candidate
        state["last_prune_seed_protected"] = n_seed_protected
        state["last_pruned"] = n_prune
        state["last_seed_protect_active"] = bool(protect_active)
        state["seed_protect_until_iter"] = -1 if self.seed_protect_until_iter is None else int(self.seed_protect_until_iter)
        state["seed_protected_count"] = int(is_seed.sum().item()) if is_seed is not None else 0
        state["cum_prune_candidates"] = int(state.get("cum_prune_candidates", 0)) + n_candidate
        state["cum_prune_seed_protected"] = int(state.get("cum_prune_seed_protected", 0)) + n_seed_protected
        state["cum_pruned"] = int(state.get("cum_pruned", 0)) + n_prune
        return n_prune


def build_seed_protect_strategy(seed_protect_until_iter: int | None = None, **kwargs) -> SeedProtectStrategy:
    """Same args/defaults as build_strategy, but seeds (state['is_seed']) are prune-protected."""
    base = build_strategy(**kwargs)
    return _clone_strategy(base, SeedProtectStrategy, seed_protect_until_iter=seed_protect_until_iter)


class ElongationFilterStrategy(DefaultStrategy):
    """DefaultStrategy with CityGSV2-style axis-ratio gating before densification.

    The upstream CityGSV2 gate is min(scale)/max(scale) > 0.01 for 3D Gaussians.
    This repo's primitives are 2DGS surfels with scale[2] fixed near zero, so the
    gate is applied to the two in-plane scales only.
    """

    axis_ratio_threshold: float = 0.01

    def _densify_candidate_mask(self, params, state):
        import torch as _torch

        scales = _torch.exp(params["scales"])
        in_plane = scales[:, :2]
        axis_ratio = in_plane.min(dim=-1).values / in_plane.max(dim=-1).values.clamp_min(1e-12)
        return axis_ratio > float(self.axis_ratio_threshold)

    @torch.no_grad()
    def _grow_gs(self, params, optimizers, state, step):  # type: ignore[override]
        count = state["count"]
        grads = state["grad2d"] / count.clamp_min(1)
        device = grads.device

        ratio_ok = self._densify_candidate_mask(params, state)
        state["elongation_filter_blocked"] = int((~ratio_ok).sum().item())
        state["elongation_axis_ratio_threshold"] = float(self.axis_ratio_threshold)

        is_grad_high = grads > self.grow_grad2d
        is_small = (
            torch.exp(params["scales"]).max(dim=-1).values
            <= self.grow_scale3d * state["scene_scale"]
        )
        is_dupli = is_grad_high & is_small & ratio_ok
        n_dupli = int(is_dupli.sum().item())

        is_large = ~is_small
        is_split = is_grad_high & is_large & ratio_ok
        if step < self.refine_scale2d_stop_iter:
            is_split |= (state["radii"] > self.grow_scale2d) & ratio_ok
        n_split = int(is_split.sum().item())

        audit_boxes = getattr(self, "densify_audit_boxes", None)
        if audit_boxes:
            means = params["means"].detach()
            events = []
            for building_id, (x0, y0, x1, y1) in audit_boxes.items():
                in_box = (
                    (means[:, 0] >= x0)
                    & (means[:, 0] <= x1)
                    & (means[:, 1] >= y0)
                    & (means[:, 1] <= y1)
                )
                duplicate_count = int((is_dupli & in_box).sum().item())
                split_count = int((is_split & in_box).sum().item())
                events.append(
                    {
                        "iteration": int(step),
                        "building_id": str(building_id),
                        "duplicate_events": duplicate_count,
                        "split_events": split_count,
                        "total_events": duplicate_count + split_count,
                    }
                )
            self.densify_audit_events = events

        if n_dupli > 0:
            duplicate(params=params, optimizers=optimizers, state=state, mask=is_dupli)

        is_split = torch.cat(
            [
                is_split,
                torch.zeros(n_dupli, dtype=torch.bool, device=device),
            ]
        )

        if n_split > 0:
            split(
                params=params,
                optimizers=optimizers,
                state=state,
                mask=is_split,
                revised_opacity=self.revised_opacity,
            )
        state["last_grow_step"] = int(step)
        state["last_grow_duplicated"] = n_dupli
        state["last_grow_split"] = n_split
        state["cum_grow_duplicated"] = int(state.get("cum_grow_duplicated", 0)) + n_dupli
        state["cum_grow_split"] = int(state.get("cum_grow_split", 0)) + n_split
        return n_dupli, n_split


class SeedProtectElongationFilterStrategy(ElongationFilterStrategy, SeedProtectStrategy):
    """Combine seed opacity-prune protection with elongation-gated densification."""


def _clone_strategy(
    base,
    cls,
    *,
    axis_ratio_threshold: float | None = None,
    seed_protect_until_iter: int | None = None,
):
    strategy = cls(**{f.name: getattr(base, f.name) for f in __import__("dataclasses").fields(base)})
    if axis_ratio_threshold is not None:
        strategy.axis_ratio_threshold = float(axis_ratio_threshold)
    if hasattr(strategy, "seed_protect_until_iter"):
        strategy.seed_protect_until_iter = None if seed_protect_until_iter is None else int(seed_protect_until_iter)
    return strategy


def build_elongation_filter_strategy(axis_ratio_threshold: float = 0.01, **kwargs) -> ElongationFilterStrategy:
    base = build_strategy(**kwargs)
    return _clone_strategy(base, ElongationFilterStrategy, axis_ratio_threshold=axis_ratio_threshold)


def build_seed_protect_elongation_filter_strategy(
    axis_ratio_threshold: float = 0.01,
    seed_protect_until_iter: int | None = None,
    **kwargs,
) -> SeedProtectElongationFilterStrategy:
    base = build_strategy(**kwargs)
    return _clone_strategy(
        base,
        SeedProtectElongationFilterStrategy,
        axis_ratio_threshold=axis_ratio_threshold,
        seed_protect_until_iter=seed_protect_until_iter,
    )
