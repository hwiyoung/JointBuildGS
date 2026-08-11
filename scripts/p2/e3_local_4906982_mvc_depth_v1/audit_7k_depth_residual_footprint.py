#!/usr/bin/env python3
"""Measure common-7k rendered-vs-COLMAP depth residual inside 4906982 XY."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import torch
import yaml
from shapely import contains_xy
from shapely.geometry import shape
from torch import nn

from src.stage2.dataloader import ColmapDataset
from src.stage2.model import GaussianModel2D
from src.stage2.renderer import render


WORLD_SHIFT = np.asarray([690953.0, 5336071.0, 604.0], dtype=np.float64)


def _model(path: Path) -> GaussianModel2D:
    payload = torch.load(path, map_location="cpu", weights_only=False)
    state = payload["model"]["state_dict"]
    model = GaussianModel2D.__new__(GaussianModel2D)
    nn.Module.__init__(model)
    model.sh_degree = model.max_sh_degree = model.active_sh_degree = 3
    model.num_classes = 4
    for key in ("means", "quats", "log_scales", "opacities_raw", "sh0", "shN", "sem_logits"):
        setattr(model, key, nn.Parameter(state[key].cuda(), requires_grad=False))
    model.surface_seed_mask = torch.zeros(len(state["means"]), dtype=torch.bool, device="cuda")
    return model.eval()


def _summary(rows: list[dict], role: str) -> dict:
    selected = [row for row in rows if row["role"] == role and row["residual_l1_m"] is not None]
    total_pixels = sum(row["inside_valid_pixels"] for row in selected)
    return {
        "view_count_with_inside_support": len(selected),
        "inside_valid_pixels": total_pixels,
        "mean_of_view_l1_m": None if not selected else float(np.mean([row["residual_l1_m"] for row in selected])),
        "median_of_view_l1_m": None if not selected else float(np.median([row["residual_l1_m"] for row in selected])),
        "pixel_weighted_l1_m": None if not total_pixels else float(
            sum(row["residual_l1_m"] * row["inside_valid_pixels"] for row in selected) / total_pixels
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--footprint", type=Path, required=True)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    cfg = yaml.safe_load(args.config.read_text())
    footprint = shape(json.loads(args.footprint.read_text())["features"][0]["geometry"])
    dataset = ColmapDataset(
        cfg["data_root"], downscale=float(cfg["downscale"]), load_depth=True,
        load_normal=False, load_semantic=False, visible_views=cfg["visible_views"],
    )
    train = set(cfg["train_views"])
    held_out = set(cfg["eval_views"])
    model = _model(args.checkpoint)
    rows = []
    with torch.no_grad():
        for view_index, batch in enumerate(dataset):
            gt = batch["depth"].numpy().astype(np.float64)
            mask = batch["depth_mask"].numpy().astype(bool) & np.isfinite(gt)
            yy, xx = np.nonzero(mask)
            z = gt[yy, xx]
            k_np = batch["K"].numpy().astype(np.float64)
            w2c_np = batch["w2c"].numpy().astype(np.float64)
            camera = np.column_stack(((xx - k_np[0, 2]) / k_np[0, 0] * z, (yy - k_np[1, 2]) / k_np[1, 1] * z, z))
            c2w = np.linalg.inv(w2c_np)
            world = camera @ c2w[:3, :3].T + c2w[:3, 3] + WORLD_SHIFT
            inside = contains_xy(footprint, world[:, 0], world[:, 1])
            inside_mask = np.zeros_like(mask)
            inside_mask[yy[inside], xx[inside]] = True
            output = render(
                model, batch["w2c"].cuda(), batch["K"].cuda(), int(batch["width"]), int(batch["height"]),
                sh_degree=3, render_mode="RGB+ED",
            )
            pred = output["depth"].detach().cpu().numpy().astype(np.float64)
            selected = inside_mask & np.isfinite(pred)
            residual = np.abs(pred[selected] - gt[selected])
            role = "train" if batch["name"] in train else "held_out" if batch["name"] in held_out else "other"
            rows.append({
                "view_index": view_index,
                "view": batch["name"],
                "role": role,
                "inside_valid_pixels": int(selected.sum()),
                "residual_l1_m": None if not len(residual) else float(np.mean(residual)),
                "residual_median_m": None if not len(residual) else float(np.median(residual)),
                "residual_p90_m": None if not len(residual) else float(np.quantile(residual, 0.9)),
                "mvs_depth_median_camera_m": None if not selected.any() else float(np.median(gt[selected])),
                "render_depth_median_camera_m": None if not selected.any() else float(np.median(pred[selected])),
            })
    result = {
        "schema": "jointbuildgs.p2.e3_local_4906982_mvc_depth_v1.footprint_7k_depth_residual.v1",
        "checkpoint": str(args.checkpoint),
        "selection": "MVS depth backprojects inside shared GroundSurface XY footprint",
        "diagnostic_only_not_training_mask": True,
        "lod2_z_used": False,
        "train": _summary(rows, "train"),
        "held_out": _summary(rows, "held_out"),
        "views": rows,
        "scientific_verdict": None,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"train": result["train"], "held_out": result["held_out"], "scientific_verdict": None}, indent=2))


if __name__ == "__main__":
    main()
