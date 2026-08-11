#!/usr/bin/env python3
"""Synthetic invariant/gradient audit for the task-local gsplat overlay."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import torch
from gsplat import rasterization_2dgs


def emit(path: Path, *, surface: bool) -> None:
    device = torch.device("cuda")
    dtype = torch.float32
    angle = torch.tensor(30.0 * torch.pi / 180.0, device=device)
    means = torch.tensor([[0.0, 0.0, 5.0]], device=device, dtype=dtype, requires_grad=True)
    quats = torch.stack(
        (torch.cos(angle / 2), torch.tensor(0.0, device=device),
         torch.sin(angle / 2), torch.tensor(0.0, device=device))
    )[None].detach().requires_grad_(True)
    scales = torch.tensor([[2.0, 2.0, 1.0]], device=device, requires_grad=True)
    opacities = torch.tensor([0.8], device=device, requires_grad=True)
    colors = torch.tensor([[0.2, 0.4, 0.6]], device=device, requires_grad=True)
    viewmats = torch.eye(4, device=device)[None]
    K = torch.tensor(
        [[[40.0, 0.0, 16.0], [0.0, 40.0, 16.0], [0.0, 0.0, 1.0]]],
        device=device,
    )
    out = rasterization_2dgs(
        means=means,
        quats=quats,
        scales=scales,
        opacities=opacities,
        colors=colors,
        viewmats=viewmats,
        Ks=K,
        width=33,
        height=33,
        render_mode="RGB+ED",
        sh_degree=None,
    )
    render_colors, alphas, normals, surf_normals, distort, auxiliary = out[:6]
    payload = {
        "render_colors": render_colors.detach().cpu(),
        "alphas": alphas.detach().cpu(),
        "normals": normals.detach().cpu(),
        "surf_normals": surf_normals.detach().cpu(),
        "distort": distort.detach().cpu(),
        "auxiliary": auxiliary.detach().cpu(),
    }
    if surface:
        surface_depth = auxiliary[..., 0] / alphas[..., 0].clamp(min=1e-10)
        hit = alphas[..., 0] > 1e-6
        loss = surface_depth[hit].mean()
        loss.backward()
        payload["surface_depth"] = surface_depth.detach().cpu()
        payload["gradient_audit"] = {
            "means_finite": bool(torch.isfinite(means.grad).all()),
            "quats_finite": bool(torch.isfinite(quats.grad).all()),
            "scales_finite": bool(torch.isfinite(scales.grad).all()),
            "means_l1": float(means.grad.abs().sum()),
            "quats_l1": float(quats.grad.abs().sum()),
            "scales_l1": float(scales.grad.abs().sum()),
        }
    path.parent.mkdir(parents=True, exist_ok=True)
    torch.save(payload, path)
    print(json.dumps({"output": str(path), "surface": surface}, sort_keys=True))


def compare(baseline: Path, surface: Path, output: Path) -> None:
    base = torch.load(baseline, map_location="cpu", weights_only=False)
    surf = torch.load(surface, map_location="cpu", weights_only=False)
    historical = ["render_colors", "alphas", "normals", "surf_normals", "distort"]
    exact = {key: bool(torch.equal(base[key], surf[key])) for key in historical}
    diff = (base["auxiliary"] - surf["auxiliary"]).abs()
    alpha = surf["alphas"][..., 0]
    valid = alpha > 1e-6
    surface_depth = surf["surface_depth"]
    expected_depth = surf["render_colors"][..., 3]
    separation = (surface_depth - expected_depth).abs()[valid]
    report = {
        "historical_outputs_exact_equal": exact,
        "historical_outputs_all_exact_equal": all(exact.values()),
        "auxiliary_changed_pixel_count": int((diff > 0).sum()),
        "surface_vs_expected_abs_max": float(separation.max()),
        "surface_vs_expected_abs_median": float(separation.median()),
        "gradient_audit": surf["gradient_audit"],
        "criteria": {
            "historical_exact": all(exact.values()),
            "surface_distinct": bool(separation.max() > 1e-4),
            "finite_nonzero_geometry_gradient": all(
                surf["gradient_audit"][key]
                for key in ("means_finite", "quats_finite", "scales_finite")
            ) and surf["gradient_audit"]["means_l1"] > 0
              and surf["gradient_audit"]["quats_l1"] > 0,
        },
        "scientific_verdict": None,
    }
    report["passed"] = all(report["criteria"].values())
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report, sort_keys=True))
    if not report["passed"]:
        raise SystemExit(1)


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    emit_parser = sub.add_parser("emit")
    emit_parser.add_argument("--output", required=True, type=Path)
    emit_parser.add_argument("--surface", action="store_true")
    compare_parser = sub.add_parser("compare")
    compare_parser.add_argument("--baseline", required=True, type=Path)
    compare_parser.add_argument("--surface", required=True, type=Path)
    compare_parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.command == "emit":
        emit(args.output, surface=args.surface)
    else:
        compare(args.baseline, args.surface, args.output)


if __name__ == "__main__":
    main()
