#!/usr/bin/env python3
"""Fixed-view evaluation and qualitative panels for pinned upstream DN-Splatter."""
from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path

import matplotlib
import numpy as np
import torch
import yaml
from PIL import Image, ImageDraw
from nerfstudio.utils.eval_utils import eval_setup


matplotlib.use("Agg")
from matplotlib import colormaps  # noqa: E402


def rgb8(value: torch.Tensor) -> np.ndarray:
    value = value.detach().float().cpu().numpy()
    if value.ndim == 4:
        value = value[0]
    return (np.clip(value, 0.0, 1.0) * 255.0 + 0.5).astype(np.uint8)


def colorize(value: np.ndarray, low: float, high: float, cmap: str, invalid: np.ndarray | None = None) -> np.ndarray:
    scaled = np.clip((value - low) / max(high - low, 1e-8), 0.0, 1.0)
    result = (colormaps[cmap](scaled)[..., :3] * 255.0 + 0.5).astype(np.uint8)
    if invalid is not None:
        result[invalid] = 0
    return result


def tile(value: np.ndarray, label: str, width: int = 320) -> Image.Image:
    image = Image.fromarray(value)
    height = max(1, round(image.height * width / image.width))
    image = image.resize((width, height), Image.Resampling.LANCZOS)
    canvas = Image.new("RGB", (width, height + 24), "white")
    canvas.paste(image, (0, 24))
    ImageDraw.Draw(canvas).text((6, 5), label, fill="black")
    return canvas


def save_panel(path: Path, parts: list[tuple[str, np.ndarray]]) -> None:
    images = [tile(value, label) for label, value in parts]
    panel = Image.new("RGB", (sum(image.width for image in images), max(image.height for image in images)), "white")
    offset = 0
    for image in images:
        panel.paste(image, (offset, 0))
        offset += image.width
    path.parent.mkdir(parents=True, exist_ok=True)
    panel.save(path, optimize=True)


def save_contact_sheet(path: Path, panels: list[Path]) -> None:
    thumbs = []
    for panel in panels:
        image = Image.open(panel).convert("RGB")
        image.thumbnail((1200, 260), Image.Resampling.LANCZOS)
        thumbs.append(image.copy())
    canvas = Image.new("RGB", (max(x.width for x in thumbs), sum(x.height for x in thumbs)), "white")
    y = 0
    for image in thumbs:
        canvas.paste(image, (0, y))
        y += image.height
    path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(path, optimize=True)


def quantiles(value: torch.Tensor) -> dict:
    q = torch.quantile(value.float(), torch.tensor([0.5, 0.9, 0.95, 0.99], device=value.device))
    return {"p50": float(q[0]), "p90": float(q[1]), "p95": float(q[2]), "p99": float(q[3])}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--steps", type=int, nargs="+", default=(7000, 12000, 15000, 19999))
    parser.add_argument("--seed-ply", type=Path, required=True)
    parser.add_argument("--world-z-shift", type=float, default=604.0)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)

    # ASCII adapter PLY has a fixed 10-line header.
    seed = np.loadtxt(args.seed_ply, skiprows=10, usecols=(0, 1, 2), dtype=np.float64)
    seed_z_max = float(seed[:, 2].max())
    rows: list[dict] = []
    checkpoint_rows: list[dict] = []

    for step in args.steps:
        config = yaml.load(args.config.read_text(), Loader=yaml.Loader)
        config.load_step = step
        eval_config = args.output / "configs" / f"step_{step:06d}.yml"
        eval_config.parent.mkdir(parents=True, exist_ok=True)
        eval_config.write_text(yaml.dump(config))
        _, pipeline, checkpoint_path, loaded_step = eval_setup(eval_config, test_mode="test")
        if loaded_step != step:
            raise RuntimeError(f"checkpoint selection drift: requested={step}, loaded={loaded_step}")

        checkpoint = torch.load(checkpoint_path, map_location="cpu")
        state = checkpoint["pipeline"]
        means = state["_model.gauss_params.means"].float()
        scales = torch.exp(state["_model.gauss_params.scales"].float())
        opacity = torch.sigmoid(state["_model.gauss_params.opacities"].float().reshape(-1))
        z = means[:, 2]
        zq = torch.quantile(z, torch.tensor([0.0, 0.5, 0.95, 0.99, 1.0]))
        elongation = scales.max(dim=1).values / scales.min(dim=1).values.clamp_min(1e-12)
        checkpoint_rows.append(
            {
                "checkpoint_step": step,
                "checkpoint": str(checkpoint_path),
                "gaussian_count": len(means),
                "z_min": float(zq[0]),
                "z_median": float(zq[1]),
                "z_p95": float(zq[2]),
                "z_p99": float(zq[3]),
                "z_max": float(zq[4]),
                "world_z_min": float(zq[0] + args.world_z_shift),
                "world_z_median": float(zq[1] + args.world_z_shift),
                "world_z_p95": float(zq[2] + args.world_z_shift),
                "world_z_p99": float(zq[3] + args.world_z_shift),
                "world_z_max": float(zq[4] + args.world_z_shift),
                "world_z_gt_650": int((z + args.world_z_shift > 650.0).sum()),
                "world_z_gt_650_opacity_ge_0p1": int(((z + args.world_z_shift > 650.0) & (opacity >= 0.1)).sum()),
                "seed_z_max": seed_z_max,
                "above_seed_z_max": int((z > seed_z_max).sum()),
                "above_seed_z_max_opacity_ge_0p1": int(((z > seed_z_max) & (opacity >= 0.1)).sum()),
                "opacity_lt_0p1": int((opacity < 0.1).sum()),
                "opacity_0p1_to_0p5": int(((opacity >= 0.1) & (opacity < 0.5)).sum()),
                "opacity_ge_0p5": int((opacity >= 0.5).sum()),
                "elongation_median": float(torch.quantile(elongation, 0.5)),
                "elongation_p95": float(torch.quantile(elongation, 0.95)),
                "elongation_p99": float(torch.quantile(elongation, 0.99)),
                "scientific_verdict": None,
            }
        )

        filenames = [Path(x).name for x in pipeline.datamanager.eval_dataset.image_filenames]
        panels = []
        for index, (camera, batch) in enumerate(pipeline.datamanager.fixed_indices_eval_dataloader):
            with torch.no_grad():
                outputs = pipeline.model.get_outputs_for_camera(camera=camera)
                upstream_metrics, _ = pipeline.model.get_image_metrics_and_images(outputs, batch)
            name = filenames[index]
            gt_rgb = batch["image"].to(pipeline.device)
            pred_rgb = outputs["rgb"][0] if outputs["rgb"].ndim == 4 else outputs["rgb"]
            gt_depth = batch["sensor_depth"].to(pipeline.device).float()
            pred_depth = outputs["depth"][0] if outputs["depth"].ndim == 4 else outputs["depth"]
            valid = torch.isfinite(gt_depth[..., 0]) & (gt_depth[..., 0] > 0.1) & torch.isfinite(pred_depth[..., 0])
            residual = (pred_depth[..., 0] - gt_depth[..., 0]).abs()[valid]
            relative = residual / gt_depth[..., 0][valid].clamp_min(1e-6)
            depth_q = torch.quantile(gt_depth[..., 0][valid], torch.tensor([0.01, 0.99], device=pipeline.device))
            residual_q95 = float(torch.quantile(residual, 0.95))

            row = {
                "checkpoint_step": step,
                "view": name,
                "valid_depth_pixels": int(valid.sum()),
                **{key: float(value) for key, value in upstream_metrics.items()},
                "depth_l1_mean_m": float(residual.mean()),
                "depth_rmse_valid_m": float(torch.sqrt((residual * residual).mean())),
                "depth_abs_rel_valid": float(relative.mean()),
                **{f"depth_abs_{key}_m": value for key, value in quantiles(residual).items()},
                "scientific_verdict": None,
            }
            rows.append(row)

            gt_d = gt_depth[..., 0].detach().cpu().numpy()
            pred_d = pred_depth[..., 0].detach().cpu().numpy()
            invalid = ~valid.detach().cpu().numpy()
            abs_d = np.abs(pred_d - gt_d)
            normal = outputs["normal"][0] if outputs["normal"].ndim == 4 else outputs["normal"]
            normal_np = normal.detach().float().cpu().numpy()
            if float(np.nanmin(normal_np)) < -0.01:
                normal_np = normal_np * 0.5 + 0.5
            alpha = outputs.get("accumulation")
            if alpha is None:
                alpha_np = np.ones_like(gt_d)
            else:
                alpha_np = alpha[0, ..., 0].detach().cpu().numpy() if alpha.ndim == 4 else alpha[..., 0].detach().cpu().numpy()
            row["alpha_mean"] = float(np.mean(alpha_np))
            row["alpha_ge_0p1_fraction"] = float(np.mean(alpha_np >= 0.1))
            row["alpha_ge_0p5_fraction"] = float(np.mean(alpha_np >= 0.5))
            panel_path = args.output / "representative_images" / f"step_{step:06d}" / f"{Path(name).stem}_panel.png"
            save_panel(
                panel_path,
                [
                    ("RGB input", rgb8(gt_rgb)),
                    ("RGB DN", rgb8(pred_rgb)),
                    (f"raw depth {float(depth_q[0]):.1f}-{float(depth_q[1]):.1f}m", colorize(gt_d, float(depth_q[0]), float(depth_q[1]), "turbo", invalid)),
                    ("DN expected depth", colorize(pred_d, float(depth_q[0]), float(depth_q[1]), "turbo", invalid)),
                    (f"abs residual p95={residual_q95:.2f}m", colorize(abs_d, 0.0, max(residual_q95, 1e-6), "magma", invalid)),
                    ("DN normal", (np.clip(normal_np, 0.0, 1.0) * 255.0 + 0.5).astype(np.uint8)),
                    ("alpha", colorize(alpha_np, 0.0, 1.0, "gray")),
                ],
            )
            panels.append(panel_path)
        save_contact_sheet(args.output / "representative_images" / f"step_{step:06d}_heldout_contact.png", panels)
        del pipeline, checkpoint, state, means, scales, opacity, z
        torch.cuda.empty_cache()

    fieldnames = list(rows[0])
    with (args.output / "checkpoint_metrics.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    with (args.output / "gaussian_metrics.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(checkpoint_rows[0]))
        writer.writeheader()
        writer.writerows(checkpoint_rows)

    aggregates = []
    for step in args.steps:
        selected = [row for row in rows if row["checkpoint_step"] == step]
        aggregate = {"checkpoint_step": step, "view_count": len(selected)}
        for key in ("rgb_psnr", "rgb_ssim", "rgb_lpips", "depth_l1_mean_m", "depth_rmse_valid_m", "depth_abs_rel_valid", "depth_abs_p50_m", "depth_abs_p95_m", "alpha_mean", "alpha_ge_0p1_fraction", "alpha_ge_0p5_fraction"):
            values = np.array([row[key] for row in selected], dtype=np.float64)
            aggregate[key + "_mean_of_views"] = float(values.mean())
            aggregate[key + "_median_of_views"] = float(np.median(values))
        aggregates.append(aggregate)
    body = {
        "schema": "jointbuildgs.p2.e3_local_4906982_dn_splatter_upstream_v1.metrics.v1",
        "fixed_heldout_aggregates": aggregates,
        "gaussian_metrics": checkpoint_rows,
        "notes": ["All checkpoint comparisons use the exact same eight held-out views.", "DN expected depth is the upstream renderer output.", "Input depth is raw positive-finite COLMAP geometric camera-Z.", "World Z adds the frozen 604.0 m EPSG:25832 shift from the prior coordinate-frame audit.", "LoD2 geometry was not used."],
        "scientific_verdict": None,
    }
    (args.output / "metrics.json").write_text(json.dumps(body, indent=2, sort_keys=True) + "\n")
    print(json.dumps(body, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
