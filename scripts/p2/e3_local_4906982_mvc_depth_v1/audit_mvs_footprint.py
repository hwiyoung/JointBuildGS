#!/usr/bin/env python3
"""Audit COLMAP geometric depth support inside the shared 4906982 footprint.

This is read-only and LoD2-Z blind.  Valid depth pixels are back-projected with
the frozen camera model, transformed to EPSG:25832, and selected only by the
shared GroundSurface XY footprint.
"""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

import numpy as np
import yaml
from shapely import contains_xy
from shapely.geometry import Point, shape

from src.stage2.dataloader import ColmapDataset


WORLD_SHIFT = np.asarray([690953.0, 5336071.0, 604.0], dtype=np.float64)


def _quantiles(values: np.ndarray) -> dict[str, float] | None:
    if not len(values):
        return None
    result = np.quantile(values, [0.0, 0.1, 0.5, 0.9, 1.0])
    return dict(zip(("min", "p10", "median", "p90", "max"), map(float, result)))


def _summarize_cells(per_view_cells, eligible_cells: set[tuple[int, int]], view_indices: set[int]) -> dict:
    support = defaultdict(list)
    for (view_index, cell), z in per_view_cells.items():
        if view_index in view_indices and cell in eligible_cells:
            support[cell].append(float(z))
    counts = np.asarray([len(values) for values in support.values()], dtype=np.int32)
    spreads = np.asarray(
        [max(values) - min(values) for values in support.values() if len(values) >= 2], dtype=np.float64
    )
    total = max(len(eligible_cells), 1)
    return {
        "footprint_cell_count": len(eligible_cells),
        "covered_cell_count": len(support),
        "covered_fraction": len(support) / total,
        "support_ge2_count": int(np.count_nonzero(counts >= 2)),
        "support_ge2_fraction": float(np.count_nonzero(counts >= 2) / total),
        "support_ge3_count": int(np.count_nonzero(counts >= 3)),
        "support_ge3_fraction": float(np.count_nonzero(counts >= 3) / total),
        "cross_view_z_spread_m": _quantiles(spreads),
        "cross_view_z_spread_le_0p5_fraction": (
            None if not len(spreads) else float(np.mean(spreads <= 0.5))
        ),
        "cross_view_z_spread_le_1p0_fraction": (
            None if not len(spreads) else float(np.mean(spreads <= 1.0))
        ),
        "cross_view_z_spread_le_2p0_fraction": (
            None if not len(spreads) else float(np.mean(spreads <= 2.0))
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--footprint", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    cfg = yaml.safe_load(args.config.read_text())
    footprint_doc = json.loads(args.footprint.read_text())
    footprint = shape(footprint_doc["features"][0]["geometry"])
    dataset = ColmapDataset(
        cfg["data_root"],
        downscale=float(cfg["downscale"]),
        load_depth=True,
        load_normal=False,
        load_semantic=False,
        visible_views=cfg["visible_views"],
    )
    train_names = set(cfg["train_views"])
    eval_names = set(cfg["eval_views"])
    view_rows = []
    all_inside_z = []
    per_view_cells: dict[tuple[int, tuple[int, int]], float] = {}
    x0, y0, x1, y1 = footprint.bounds
    eligible_cells = {
        (ix, iy)
        for ix in range(int(np.floor(x0)), int(np.ceil(x1)))
        for iy in range(int(np.floor(y0)), int(np.ceil(y1)))
        if footprint.covers(Point(ix + 0.5, iy + 0.5))
    }

    for view_index, batch in enumerate(dataset):
        depth = batch["depth"].numpy().astype(np.float64)
        mask = batch["depth_mask"].numpy().astype(bool) & np.isfinite(depth)
        yy, xx = np.nonzero(mask)
        z = depth[yy, xx]
        k = batch["K"].numpy().astype(np.float64)
        w2c = batch["w2c"].numpy().astype(np.float64)
        camera = np.column_stack(((xx - k[0, 2]) / k[0, 0] * z, (yy - k[1, 2]) / k[1, 1] * z, z))
        c2w = np.linalg.inv(w2c)
        world = camera @ c2w[:3, :3].T + c2w[:3, 3] + WORLD_SHIFT
        inside = contains_xy(footprint, world[:, 0], world[:, 1])
        inside_xyz = world[inside]
        all_inside_z.append(inside_xyz[:, 2])
        cells = np.floor(inside_xyz[:, :2]).astype(np.int64)
        cell_z = defaultdict(list)
        for cell, value in zip(map(tuple, cells), inside_xyz[:, 2]):
            if cell in eligible_cells:
                cell_z[cell].append(float(value))
        for cell, values in cell_z.items():
            per_view_cells[(view_index, cell)] = float(np.median(values))
        role = "train" if batch["name"] in train_names else "held_out" if batch["name"] in eval_names else "other"
        view_rows.append({
            "view_index": view_index,
            "view": batch["name"],
            "role": role,
            "image_pixels": int(depth.size),
            "valid_depth_pixels": int(mask.sum()),
            "valid_depth_fraction": float(mask.mean()),
            "backprojected_inside_footprint_pixels": int(inside.sum()),
            "inside_fraction_of_image": float(inside.sum() / depth.size),
            "inside_fraction_of_valid_depth": float(inside.mean()) if len(inside) else 0.0,
            "inside_footprint_cell_count": len(cell_z),
            "inside_z_epsg25832_m": _quantiles(inside_xyz[:, 2]),
        })

    train_indices = {row["view_index"] for row in view_rows if row["role"] == "train"}
    eval_indices = {row["view_index"] for row in view_rows if row["role"] == "held_out"}
    all_indices = train_indices | eval_indices
    all_z = np.concatenate(all_inside_z) if all_inside_z else np.empty(0)
    histogram, edges = np.histogram(all_z, bins=np.arange(520.0, 681.0, 1.0))
    top_bins = sorted(
        ({"z_from": float(edges[i]), "z_to": float(edges[i + 1]), "count": int(count)} for i, count in enumerate(histogram)),
        key=lambda row: (-row["count"], row["z_from"]),
    )[:12]
    output = {
        "schema": "jointbuildgs.p2.e3_local_4906982_mvc_depth_v1.mvs_footprint_audit.v1",
        "building_id": "DEBY_LOD2_4906982",
        "depth_source": "COLMAP geometric consistency depth",
        "selection": "backproject valid depth then shared GroundSurface XY footprint only",
        "lod2_z_used": False,
        "view_count": len(view_rows),
        "train_view_count": len(train_indices),
        "held_out_view_count": len(eval_indices),
        "inside_footprint_depth_pixel_count": int(sum(row["backprojected_inside_footprint_pixels"] for row in view_rows)),
        "inside_z_epsg25832_m": _quantiles(all_z),
        "top_one_metre_z_bins": top_bins,
        "grid_1m": {
            "train": _summarize_cells(per_view_cells, eligible_cells, train_indices),
            "held_out": _summarize_cells(per_view_cells, eligible_cells, eval_indices),
            "all": _summarize_cells(per_view_cells, eligible_cells, all_indices),
        },
        "views": view_rows,
        "scientific_verdict": None,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n")
    print(json.dumps({key: output[key] for key in (
        "view_count", "inside_footprint_depth_pixel_count", "inside_z_epsg25832_m", "top_one_metre_z_bins", "grid_1m", "scientific_verdict"
    )}, indent=2))


if __name__ == "__main__":
    main()
