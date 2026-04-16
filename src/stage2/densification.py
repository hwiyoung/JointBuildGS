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

from .model import GaussianModel2D


PARAM_NAMES = ("means", "quats", "log_scales", "opacities_raw", "sh0", "shN")


def build_param_dict(model: GaussianModel2D) -> Dict[str, nn.Parameter]:
    return {
        "means": model.means,
        "scales": model.log_scales,        # gsplat treats as raw; monotonic via exp at render
        "quats": model.quats,
        "opacities": model.opacities_raw,
        "sh0": model.sh0,
        "shN": model.shN,
    }


def build_optimizers(
    model: GaussianModel2D,
    lr_means: float = 1.6e-4,
    lr_scales: float = 5e-3,
    lr_quats: float = 1e-3,
    lr_opacities: float = 5e-2,
    lr_sh0: float = 2.5e-3,
    lr_shN: float = 1.25e-4,
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
