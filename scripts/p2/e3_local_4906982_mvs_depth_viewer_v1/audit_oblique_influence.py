#!/usr/bin/env python3
"""LoD2-Z-blind audit of train-view obliquity versus MVS depth disagreement."""
from __future__ import annotations

import argparse
from collections import defaultdict
import json
from pathlib import Path

import numpy as np
from scipy.stats import spearmanr
from shapely import contains_xy
from shapely.geometry import shape
import yaml

from src.stage2.dataloader import ColmapDataset


SHIFT = np.asarray([690953.0, 5336071.0, 604.0], dtype=np.float64)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--training-config", type=Path, required=True)
    parser.add_argument("--footprint", type=Path, required=True)
    parser.add_argument("--viewer-manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    cfg = yaml.safe_load(args.training_config.read_text())
    viewer = json.loads(args.viewer_manifest.read_text())
    footprint = shape(json.loads(args.footprint.read_text())["features"][0]["geometry"])
    angle = {row["view_name"]: float(row["nadir_deg"]) for row in viewer["views"]}
    train = set(cfg["train_views"])
    dataset = ColmapDataset(
        cfg["data_root"], downscale=float(cfg["downscale"]), load_depth=True,
        load_normal=False, load_semantic=False, visible_views=cfg["visible_views"],
    )
    by_view: dict[str, dict[tuple[int, int], float]] = {}
    for batch in dataset:
        if batch["name"] not in train:
            continue
        depth = batch["depth"].numpy().astype(np.float64)
        mask = batch["depth_mask"].numpy().astype(bool) & np.isfinite(depth)
        yy, xx = np.nonzero(mask); z = depth[yy, xx]
        k = batch["K"].numpy().astype(np.float64); c2w = np.linalg.inv(batch["w2c"].numpy().astype(np.float64))
        camera = np.column_stack(((xx - k[0, 2]) / k[0, 0] * z, (yy - k[1, 2]) / k[1, 1] * z, z))
        world = camera @ c2w[:3, :3].T + c2w[:3, 3] + SHIFT
        inside = contains_xy(footprint, world[:, 0], world[:, 1]); xyz = world[inside]
        values = defaultdict(list)
        for cell, wz in zip(map(tuple, np.floor(xyz[:, :2]).astype(np.int64)), xyz[:, 2]):
            values[cell].append(float(wz))
        by_view[batch["name"]] = {cell: float(np.median(items)) for cell, items in values.items()}

    support = defaultdict(list)
    for name, cells in by_view.items():
        for cell, value in cells.items(): support[cell].append((name, value))
    consensus = {cell: float(np.median([value for _name, value in rows])) for cell, rows in support.items()}
    baseline_spreads = np.asarray([max(v for _n, v in rows) - min(v for _n, v in rows) for rows in support.values() if len(rows) >= 2])
    baseline_median = float(np.median(baseline_spreads))
    rows = []
    for name, cells in by_view.items():
        deviations = np.asarray([abs(value - consensus[cell]) for cell, value in cells.items()], dtype=np.float64)
        without = []
        for cell_rows in support.values():
            values = [value for other, value in cell_rows if other != name]
            if len(values) >= 2: without.append(max(values) - min(values))
        without_median = float(np.median(without)) if without else None
        rows.append({
            "view": name, "nadir_deg": angle[name], "cell_count": len(cells),
            "median_abs_deviation_from_cell_consensus_m": None if not len(deviations) else float(np.median(deviations)),
            "p90_abs_deviation_from_cell_consensus_m": None if not len(deviations) else float(np.quantile(deviations, .9)),
            **{f"fraction_abs_deviation_gt_{str(t).replace('.', 'p')}m": None if not len(deviations) else float(np.mean(deviations > t)) for t in (.5, 1., 2., 5., 10.)},
            "median_cross_view_spread_without_view_m": without_median,
            "median_spread_reduction_if_removed_m": None if without_median is None else baseline_median - without_median,
        })
    rows.sort(key=lambda row: row["nadir_deg"])

    def group(label: str, selected: list[dict]) -> dict:
        def median(key):
            values = [row[key] for row in selected if row[key] is not None]
            return None if not values else float(np.median(values))
        return {"label": label, "view_count": len(selected), "nadir_deg_median": median("nadir_deg"), "view_median_abs_deviation_median_m": median("median_abs_deviation_from_cell_consensus_m"), "view_p90_abs_deviation_median_m": median("p90_abs_deviation_from_cell_consensus_m"), "fraction_gt_2m_median": median("fraction_abs_deviation_gt_2p0m"), "fraction_gt_5m_median": median("fraction_abs_deviation_gt_5p0m"), "spread_reduction_if_removed_median_m": median("median_spread_reduction_if_removed_m")}

    finite = [row for row in rows if row["median_abs_deviation_from_cell_consensus_m"] is not None]
    rho, pvalue = spearmanr([row["nadir_deg"] for row in finite], [row["median_abs_deviation_from_cell_consensus_m"] for row in finite])
    result = {
        "schema": "jointbuildgs.p2.e3_local_4906982_mvs_depth_viewer_v1.oblique_influence.v1",
        "building_id": "DEBY_LOD2_4906982", "train_view_count": len(rows),
        "cell_consensus": "median world Z of per-view 1m-cell medians; shared GroundSurface XY only",
        "baseline_cross_view_max_minus_min_median_m": baseline_median,
        "obliquity_spearman_vs_view_median_abs_deviation": {"rho": float(rho), "p_value_descriptive": float(pvalue)},
        "groups": [group("near_nadir_le_10deg", [r for r in rows if r["nadir_deg"] <= 10]), group("mid_10_to_30deg", [r for r in rows if 10 < r["nadir_deg"] <= 30]), group("oblique_gt_30deg", [r for r in rows if r["nadir_deg"] > 30])],
        "top_views_by_consensus_deviation": sorted(finite, key=lambda row: row["median_abs_deviation_from_cell_consensus_m"], reverse=True)[:10],
        "views": rows, "lod2_z_used": False, "scientific_verdict": None,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps({key: result[key] for key in ("train_view_count", "baseline_cross_view_max_minus_min_median_m", "obliquity_spearman_vs_view_median_abs_deviation", "groups", "top_views_by_consensus_deviation", "scientific_verdict")}, indent=2))


if __name__ == "__main__":
    main()
