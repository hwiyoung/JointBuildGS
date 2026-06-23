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
from gsplat.strategy.ops import remove

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
    """DefaultStrategy that NEVER prunes MVS-seed Gaussians (P2 make-or-break C: seed protection).

    Seeds are flagged by a bool tensor in ``state["is_seed"]`` registered at init. gsplat's
    remove/duplicate/split (ops.py) carry every per-Gaussian ``state`` tensor in lockstep with the
    params, so the flag stays aligned automatically (seed lineage — split/dup children — inherits it).
    Only ``_prune_gs`` is overridden: identical to gsplat 1.4.0 DefaultStrategy._prune_gs but with
    ``is_prune &= ~is_seed`` so seeds survive opacity-prune (and reset_opa, which only lowers opacity).
    PINNED to gsplat 1.4.0 prune logic — re-sync if gsplat is upgraded.
    """

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

        is_seed = state.get("is_seed")
        if is_seed is not None:
            is_prune = is_prune & (~is_seed)   # protect MVS seeds (+ their lineage)

        n_prune = int(is_prune.sum().item())
        if n_prune > 0:
            remove(params=params, optimizers=optimizers, state=state, mask=is_prune)
        return n_prune


def build_seed_protect_strategy(**kwargs) -> SeedProtectStrategy:
    """Same args/defaults as build_strategy, but seeds (state['is_seed']) are prune-protected."""
    base = build_strategy(**kwargs)
    return SeedProtectStrategy(**{f.name: getattr(base, f.name) for f in __import__("dataclasses").fields(base)})
