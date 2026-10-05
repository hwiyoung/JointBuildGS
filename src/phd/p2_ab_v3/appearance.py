"""Appearance-only residual emphasis; residuals never authorize geometry changes."""
from __future__ import annotations
import torch


def image_quality(target, support, *, low=1/255, high=254/255, clipped_weight=.25):
    """Declared radiometric heuristic, not an estimated noise/currentness score."""
    if target.shape[:-1]!=support.shape or target.shape[-1]!=3:raise ValueError("RGB/support shape mismatch")
    clipped=(target<=low).all(-1)|(target>=high).all(-1)
    q=torch.where(clipped,torch.full_like(target[...,0],clipped_weight),torch.ones_like(target[...,0]))
    return (q*support.to(q.dtype)).detach(),clipped&support


def residual_weights(prediction,target,quality,*,gain=1.,cap=2.,scale_floor=1/255):
    """Stop-gradient, bounded relative emphasis, normalized by actual valid mass."""
    if prediction.shape!=target.shape or quality.shape!=target.shape[:-1]:raise ValueError("unaligned inputs")
    if gain<0 or cap<0 or scale_floor<=0:raise ValueError("invalid residual control")
    if not bool(torch.isfinite(prediction).all()&torch.isfinite(target).all()&torch.isfinite(quality).all()):
        raise ValueError("nonfinite appearance input")
    if bool((quality<0).any()):raise ValueError("negative quality")
    with torch.no_grad():
        residual=(prediction.detach()-target.detach()).abs().mean(-1)
        selected=quality>0
        if not bool(selected.any()):raise ValueError("empty appearance support")
        scale=residual[selected].median().clamp_min(scale_floor)
        relative=1+gain*(residual/scale).clamp(max=cap)
        mass=quality.detach()*relative
        weights=mass/mass.sum()
        effective=(mass.sum().square()/mass.square().sum()).item()
    return weights,dict(residual_scale=float(scale),relative_min=float(relative[selected].min()),
        relative_max=float(relative[selected].max()),weight_sum=float(weights.sum()),
        supported_pixels=int(selected.sum()),effective_pixels=effective)


def weighted_rgb_l1(prediction,target,quality,*,gain=1.,cap=2.,scale_floor=1/255):
    weights,metadata=residual_weights(prediction,target,quality,gain=gain,cap=cap,scale_floor=scale_floor)
    return (weights*(prediction-target).abs().mean(-1)).sum(),metadata


def freeze_except_color(model,color_name="sh0"):
    parameters=dict(model.named_parameters())
    if color_name not in parameters:raise ValueError("missing color parameter")
    for name,value in parameters.items():value.requires_grad_(name==color_name)
    return [parameters[color_name]]
