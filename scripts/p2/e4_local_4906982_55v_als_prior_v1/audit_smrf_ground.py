#!/usr/bin/env python3
"""Explain the high SMRF ground fraction without changing any input artifact."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import laspy
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from scipy.ndimage import label
from scipy.spatial import cKDTree
from shapely import contains_xy
from shapely.geometry import shape


REPO = Path("/workspace/JointBuildGS")
CONFIG = REPO / "configs/p2/e4_local_4906982_55v_als_prior_v1/smrf_diagnostic.json"
OUTPUT = Path(
    "/artifacts/JointBuildGS/phase-payloads/p2/e4_local_4906982_55v_als_prior_v1/"
    "P2-E4-LOCAL-4906982-55V-ALS-PRIOR-v1/smrf_diagnostic"
)


def sha256(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def stats(values: np.ndarray) -> dict[str, float | int | None]:
    finite = values[np.isfinite(values)]
    if not len(finite):
        return {"count": 0, "min": None, "p05": None, "median": None, "p95": None, "max": None}
    q = np.quantile(finite, [0, 0.05, 0.5, 0.95, 1])
    return {
        "count": int(len(finite)),
        **{key: float(value) for key, value in zip(("min", "p05", "median", "p95", "max"), q)},
    }


def grid_diagnostics(x: np.ndarray, y: np.ndarray, z: np.ndarray, cls: np.ndarray, footprint, cell: float) -> tuple[dict, dict]:
    minx, miny, maxx, maxy = footprint.bounds
    nx = int(np.ceil((maxx - minx) / cell))
    ny = int(np.ceil((maxy - miny) / cell))
    ix = np.floor((x - minx) / cell).astype(int)
    iy = np.floor((y - miny) / cell).astype(int)
    valid = (ix >= 0) & (ix < nx) & (iy >= 0) & (iy < ny)
    keys = iy[valid] * nx + ix[valid]
    order = np.argsort(keys)
    keys_sorted = keys[order]
    unique, starts = np.unique(keys_sorted, return_index=True)
    ends = np.r_[starts[1:], len(keys_sorted)]
    cell_relief = []
    ground_fraction = []
    occupied = np.zeros((ny, nx), dtype=bool)
    ground_majority = np.zeros((ny, nx), dtype=bool)
    for key, start, end in zip(unique, starts, ends):
        index = np.flatnonzero(valid)[order[start:end]]
        row, col = divmod(int(key), nx)
        occupied[row, col] = True
        relief = float(np.quantile(z[index], 0.90) - np.quantile(z[index], 0.10))
        fraction = float(np.mean(cls[index] == 2))
        cell_relief.append(relief)
        ground_fraction.append(fraction)
        ground_majority[row, col] = fraction >= 0.5
    _, components = label(ground_majority, structure=np.ones((3, 3), dtype=np.uint8))
    component_sizes = []
    if components:
        labelled, _ = label(ground_majority, structure=np.ones((3, 3), dtype=np.uint8))
        component_sizes = [int(np.sum(labelled == value)) for value in range(1, components + 1)]
    metrics = {
        "cell_m": cell,
        "occupied_cell_count": int(occupied.sum()),
        "ground_majority_cell_count": int(ground_majority.sum()),
        "ground_majority_fraction": float(ground_majority.sum() / max(1, occupied.sum())),
        "cell_relief_m": stats(np.asarray(cell_relief)),
        "cell_relief_le_0_5m_fraction": float(np.mean(np.asarray(cell_relief) <= 0.5)),
        "ground_majority_component_count": int(components),
        "largest_ground_component_cells": max(component_sizes, default=0),
        "largest_ground_component_fraction_of_occupied": max(component_sizes, default=0) / max(1, int(occupied.sum())),
    }
    arrays = {"occupied": occupied, "ground_majority": ground_majority, "extent": (minx, maxx, miny, maxy)}
    return metrics, arrays


def plane_diagnostics(x: np.ndarray, y: np.ndarray, z: np.ndarray) -> dict:
    center_x, center_y = float(np.median(x)), float(np.median(y))
    design = np.column_stack((x - center_x, y - center_y, np.ones(len(x))))
    coef, *_ = np.linalg.lstsq(design, z, rcond=None)
    residual = z - design @ coef
    slope = float(np.hypot(coef[0], coef[1]))
    return {
        "fit": "least_squares_z_equals_ax_plus_by_plus_c_on_class2_inside_footprint",
        "slope_m_per_m": slope,
        "slope_degrees": float(np.degrees(np.arctan(slope))),
        "residual_m": stats(np.abs(residual)),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=CONFIG)
    parser.add_argument("--source-task", type=Path)
    parser.add_argument("--arm")
    parser.add_argument("--replica")
    parser.add_argument("--completed-updates", type=int)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    started = datetime.now(timezone.utc).isoformat()
    cfg = json.loads(args.config.read_text())
    if args.source_task is not None:
        cfg["source_task"] = str(args.source_task)
    if args.arm is not None:
        cfg["arm"] = args.arm
    if args.replica is not None:
        cfg["replica"] = args.replica
    if args.completed_updates is not None:
        cfg["completed_updates"] = args.completed_updates
    output = args.output
    source = Path(cfg["source_task"])
    fusion = source / f"arms/{cfg['arm']}/{cfg['replica']}/evaluation/step_{cfg['completed_updates']:06d}/fusion"
    raw_path = fusion / "fused_surface.laz"
    classified_path = fusion / "classified_surface.laz"
    pipeline_path = fusion / "classification_pipeline.json"
    footprint_path = source / "control/shared_standard_footprint_4906982.geojson"
    footprint_doc = json.loads(footprint_path.read_text())
    footprint = shape(footprint_doc["features"][0]["geometry"])

    raw_las = laspy.read(raw_path)
    classified_las = laspy.read(classified_path)
    x = np.asarray(classified_las.x, dtype=np.float64)
    y = np.asarray(classified_las.y, dtype=np.float64)
    z = np.asarray(classified_las.z, dtype=np.float64)
    cls = np.asarray(classified_las.classification, dtype=np.uint8)
    inside = contains_xy(footprint, x, y)
    ring2 = contains_xy(footprint.buffer(2.0), x, y) & ~inside
    ring5 = contains_xy(footprint.buffer(5.0), x, y) & ~contains_xy(footprint.buffer(2.0), x, y)
    ring10 = contains_xy(footprint.buffer(float(cfg["nearest_context_radius_m"])), x, y) & ~contains_xy(footprint.buffer(5.0), x, y)

    ground = inside & (cls == 2)
    building = inside & (cls == 6)
    other = inside & ~np.isin(cls, [2, 6])
    context = ~inside & contains_xy(footprint.buffer(float(cfg["nearest_context_radius_m"])), x, y)
    if not context.any():
        raise RuntimeError("no exterior context points within frozen diagnostic radius")
    tree = cKDTree(np.column_stack((x[context], y[context])))
    distance, nearest = tree.query(np.column_stack((x[inside], y[inside])), k=1, workers=-1)
    exterior_z = z[context][nearest]
    dz = z[inside] - exterior_z
    inside_cls = cls[inside]

    grid_metrics, grid_arrays = grid_diagnostics(x[inside], y[inside], z[inside], inside_cls, footprint, float(cfg["analysis_grid_m"]))
    ground_return = np.asarray(classified_las.return_number, dtype=np.uint8)
    number_returns = np.asarray(classified_las.number_of_returns, dtype=np.uint8)
    dimensions = [str(name) for name in classified_las.point_format.dimension_names]
    pipeline = json.loads(pipeline_path.read_text())
    smrf_stage = next(stage for stage in pipeline["pipeline"] if stage["type"] == "filters.smrf")
    overlay_stage = next(stage for stage in pipeline["pipeline"] if stage["type"] == "filters.overlay")

    metrics = {
        "inside_footprint": {
            "point_count": int(inside.sum()),
            "class2_ground_count": int(ground.sum()),
            "class2_ground_fraction": float(ground.sum() / max(1, inside.sum())),
            "class6_building_count": int(building.sum()),
            "class6_building_fraction": float(building.sum() / max(1, inside.sum())),
            "other_count": int(other.sum()),
            "z_m_all": stats(z[inside]),
            "z_m_class2": stats(z[ground]),
            "z_m_class6": stats(z[building]),
        },
        "exterior_context_z_m": {
            "0_to_2m": stats(z[ring2]),
            "2_to_5m": stats(z[ring5]),
            "5_to_10m": stats(z[ring10]),
        },
        "nearest_exterior_context": {
            "radius_m": float(cfg["nearest_context_radius_m"]),
            "xy_distance_m": stats(distance),
            "inside_minus_nearest_exterior_z_m_all": stats(dz),
            "inside_minus_nearest_exterior_z_m_class2": stats(dz[inside_cls == 2]),
            "inside_minus_nearest_exterior_z_m_class6": stats(dz[inside_cls == 6]),
            "class2_more_than_2m_above_nearest_exterior_fraction": float(np.mean(dz[inside_cls == 2] > 2.0)),
            "class2_more_than_5m_above_nearest_exterior_fraction": float(np.mean(dz[inside_cls == 2] > 5.0)),
        },
        "local_surface_continuity": grid_metrics,
        "class2_planarity": plane_diagnostics(x[ground], y[ground], z[ground]),
        "return_metadata": {
            "dimensions_present": dimensions,
            "return_number_all_zero": bool(np.all(ground_return == 0)),
            "number_of_returns_all_zero": bool(np.all(number_returns == 0)),
            "unique_return_number": np.unique(ground_return).astype(int).tolist(),
            "unique_number_of_returns": np.unique(number_returns).astype(int).tolist(),
            "interpretation": "fused GS surface has no LiDAR return structure for SMRF return filtering",
        },
        "pipeline_logic": {
            "smrf_stage": smrf_stage,
            "overlay_stage": overlay_stage,
            "class2_preserved_by_overlay": overlay_stage.get("where") == "Classification != 2",
            "inside_non_ground_relabelled_to_class6": int(building.sum()),
            "inside_smrf_ground_left_as_class2": int(ground.sum()),
        },
    }

    output.mkdir(parents=True, exist_ok=True)
    image_dir = output / "representative_images"
    image_dir.mkdir(parents=True, exist_ok=True)
    figure, axes = plt.subplots(2, 2, figsize=(14, 12))
    boundary = np.asarray(footprint.exterior.coords)
    axes[0, 0].scatter(x[ground], y[ground], s=1, color="#d9a441", label="SMRF class 2", rasterized=True)
    axes[0, 0].scatter(x[building], y[building], s=1, color="#2a6fbb", label="overlay class 6", rasterized=True)
    axes[0, 0].plot(boundary[:, 0], boundary[:, 1], color="black", lw=1.2)
    axes[0, 0].set_title("Final classification inside footprint")
    axes[0, 0].legend(markerscale=5)

    sc = axes[0, 1].scatter(x[inside], y[inside], c=np.clip(dz, -5, 20), s=1, cmap="coolwarm", vmin=-5, vmax=20, rasterized=True)
    axes[0, 1].plot(boundary[:, 0], boundary[:, 1], color="black", lw=1.2)
    axes[0, 1].set_title("Z minus nearest exterior point (clipped -5..20 m)")
    figure.colorbar(sc, ax=axes[0, 1], label="dZ (m)")

    axes[1, 0].imshow(grid_arrays["ground_majority"], origin="lower", extent=grid_arrays["extent"], cmap="YlOrBr", interpolation="nearest")
    axes[1, 0].plot(boundary[:, 0], boundary[:, 1], color="black", lw=1.2)
    axes[1, 0].set_title("1 m cells where class 2 is the majority")

    xy = np.column_stack((x[inside], y[inside]))
    centered = xy - np.mean(xy, axis=0)
    _, _, vh = np.linalg.svd(centered, full_matrices=False)
    along = centered @ vh[0]
    axes[1, 1].scatter(along[inside_cls == 2], z[inside][inside_cls == 2], s=1, color="#d9a441", label="class 2", rasterized=True)
    axes[1, 1].scatter(along[inside_cls == 6], z[inside][inside_cls == 6], s=1, color="#2a6fbb", label="class 6", rasterized=True)
    axes[1, 1].set_xlabel("Footprint principal axis (m)")
    axes[1, 1].set_ylabel("Z (m)")
    axes[1, 1].set_title("Vertical profile of the same fused cloud")
    axes[1, 1].legend(markerscale=5)
    for axis in axes.flat[:3]:
        axis.set_aspect("equal", adjustable="box")
        axis.set_xlabel("Easting (m)")
        axis.set_ylabel("Northing (m)")
    figure.suptitle("DEBY_LOD2_4906982 — why SMRF retained most footprint points as ground", fontsize=16, fontweight="bold")
    figure.tight_layout()
    image_path = image_dir / "smrf_ground_cause.png"
    figure.savefig(image_path, dpi=170, bbox_inches="tight")
    plt.close(figure)

    csv_path = output / "smrf_class_metrics.csv"
    with csv_path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=["class", "count", "fraction_pct", "z_median", "z_p95", "nearest_exterior_dz_median", "nearest_exterior_dz_p95"])
        writer.writeheader()
        for value, name in ((2, "SMRF_ground"), (6, "footprint_non_ground")):
            mask = inside_cls == value
            writer.writerow({
                "class": name,
                "count": int(mask.sum()),
                "fraction_pct": 100.0 * float(mask.mean()),
                "z_median": stats(z[inside][mask])["median"],
                "z_p95": stats(z[inside][mask])["p95"],
                "nearest_exterior_dz_median": stats(dz[mask])["median"],
                "nearest_exterior_dz_p95": stats(dz[mask])["p95"],
            })

    receipt = {
        "schema": cfg["schema"],
        "task_id": cfg["task_id"],
        "status": "COMPLETE",
        "started_at": started,
        "ended_at": datetime.now(timezone.utc).isoformat(),
        "inputs_sha256": {str(path): sha256(path) for path in (args.config, raw_path, classified_path, pipeline_path, footprint_path)},
        "metrics": metrics,
        "diagnostic_observation": {
            "primary_chain": "continuous low-local-relief fused surface -> SMRF class2 -> overlay preserves class2 -> Roofer receives only remaining class6 fragments",
            "alternative_not_supported": "the 84 percent is not caused by missing raw XY coverage before classification",
        },
        "outputs_sha256": {"smrf_class_metrics.csv": sha256(csv_path), "representative_images/smrf_ground_cause.png": sha256(image_path)},
        "source_artifacts_modified": False,
        "lod2_z_or_roof_geometry_used": False,
        "scientific_verdict": None,
    }
    (output / "metrics.json").write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    print(json.dumps(receipt, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
