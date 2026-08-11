#!/usr/bin/env python3
"""Read-only audit of exact surface-hit availability and raw-depth residuals."""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import numpy as np
import torch
import yaml
from torch import nn

from src.stage2.dataloader import ColmapDataset
from src.stage2.model import GaussianModel2D
from src.stage2.renderer import render


def model_from(path: Path) -> GaussianModel2D:
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


def q(values: torch.Tensor) -> tuple[float | None, float | None, float | None]:
    if not values.numel():
        return None, None, None
    result = torch.quantile(values.float(), torch.tensor([0.5, 0.95, 0.99], device=values.device))
    return tuple(float(x) for x in result)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--task-root", type=Path, required=True)
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--output-csv", type=Path, required=True)
    args = parser.parse_args()
    cfg = yaml.safe_load(args.config.read_text())
    names = list(cfg["visible_views"])
    train = set(cfg["train_views"])
    dataset = ColmapDataset(
        args.data_root, downscale=1.0, load_depth=True, load_normal=False,
        load_semantic=False, visible_views=names,
    )
    cases = (("EXPECTED", 7000), ("EXPECTED", 20000), ("SURFACE_INTERSECTION", 20000))
    rows: list[dict[str, object]] = []
    for arm, step in cases:
        model = model_from(args.task_root / f"arms/{arm}/R1/ckpt/step_{step:06d}.pt")
        with torch.no_grad():
            for batch in dataset:
                out = render(
                    model, batch["w2c"].cuda(), batch["K"].cuda(),
                    int(batch["width"]), int(batch["height"]), sh_degree=3,
                    render_mode="RGB+ED", near_plane=0.01, far_plane=500.0,
                )
                expected = out["depth"]
                surface = out["depth_surface_intersection"]
                hit = out["depth_surface_intersection_hit"]
                raw = batch["depth"].cuda()
                valid = batch["depth_mask"].cuda() & torch.isfinite(raw) & (raw > 0)
                hit_valid = valid & hit
                fallback = valid & ~hit
                selected = torch.where(hit, surface, expected)
                diff = torch.abs(surface[hit_valid] - expected[hit_valid])
                expected_raw = torch.abs(expected[valid] - raw[valid])
                surface_raw = torch.abs(selected[valid] - raw[valid])
                dm, d95, d99 = q(diff); em, e95, e99 = q(expected_raw); sm, s95, s99 = q(surface_raw)
                rows.append({
                    "arm": arm, "completed_updates": step, "view": batch["name"],
                    "view_role": "train" if batch["name"] in train else "held_out",
                    "raw_valid": int(valid.sum()), "surface_hit_raw_valid": int(hit_valid.sum()),
                    "surface_fallback_raw_valid": int(fallback.sum()),
                    "surface_fallback_rate": float(fallback.sum() / valid.sum()) if bool(valid.any()) else None,
                    "abs_surface_expected_hit_median": dm, "abs_surface_expected_hit_p95": d95,
                    "abs_surface_expected_hit_p99": d99,
                    "abs_expected_raw_median": em, "abs_expected_raw_p95": e95, "abs_expected_raw_p99": e99,
                    "abs_surface_selected_raw_median": sm, "abs_surface_selected_raw_p95": s95,
                    "abs_surface_selected_raw_p99": s99,
                })
        del model
        torch.cuda.empty_cache()
    args.output_csv.parent.mkdir(parents=True, exist_ok=True)
    with args.output_csv.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0])); writer.writeheader(); writer.writerows(rows)
    aggregates: dict[str, object] = {}
    for arm, step in cases:
        subset = [row for row in rows if row["arm"] == arm and row["completed_updates"] == step]
        valid = sum(int(row["raw_valid"]) for row in subset)
        fallback = sum(int(row["surface_fallback_raw_valid"]) for row in subset)
        metrics = {}
        for key in ("abs_surface_expected_hit_median", "abs_surface_expected_hit_p95", "abs_surface_expected_hit_p99",
                    "abs_expected_raw_median", "abs_expected_raw_p95", "abs_expected_raw_p99",
                    "abs_surface_selected_raw_median", "abs_surface_selected_raw_p95", "abs_surface_selected_raw_p99"):
            values = [float(row[key]) for row in subset if row[key] is not None]
            metrics[key + "_view_median"] = float(np.median(values)) if values else None
        aggregates[f"{arm}_{step}"] = {
            "view_count": len(subset), "raw_valid": valid, "fallback": fallback,
            "fallback_rate": fallback / valid if valid else None, **metrics,
        }
    body = {
        "schema": "jointbuildgs.p2.e3_local_4906982_surface_intersection_diag_v1.surface_depth_audit.v1",
        "cases": aggregates, "quantile_aggregation": "median_of_per_view_pixel_quantiles",
        "no_hit_rule": "expected_depth_fallback_without_raw_mask_change",
        "rows": rows, "scientific_verdict": None,
    }
    args.output_json.write_text(json.dumps(body, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"cases": aggregates, "row_count": len(rows), "scientific_verdict": None}, indent=2))


if __name__ == "__main__":
    main()
