#!/usr/bin/env python3
"""Audit whether Roofer input loss occurs before or during classification."""
from __future__ import annotations

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
from shapely import contains_xy
from shapely.geometry import Point, shape


REPO = Path("/workspace/JointBuildGS")
CONFIG_PATH = REPO / "configs/p2/e3_local_4906982_roofer_input_audit_v1/config.json"
OUTPUT_ROOT = Path(
    "/artifacts/JointBuildGS/phase-payloads/p2/e3_local_4906982_roofer_input_audit_v1/"
    "P2-E3-LOCAL-4906982-ROOFER-INPUT-AUDIT-v1"
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_laz(path: Path) -> dict[str, np.ndarray]:
    cloud = laspy.read(path)
    result = {
        "x": np.asarray(cloud.x, dtype=np.float64),
        "y": np.asarray(cloud.y, dtype=np.float64),
        "z": np.asarray(cloud.z, dtype=np.float64),
    }
    if "classification" in [name.lower() for name in cloud.point_format.dimension_names]:
        result["classification"] = np.asarray(cloud.classification, dtype=np.uint8)
    return result


def grid_cells(geometry, grid_m: float) -> tuple[set[tuple[int, int]], tuple[float, float]]:
    minx, miny, maxx, maxy = geometry.bounds
    nx = int(np.ceil((maxx - minx) / grid_m))
    ny = int(np.ceil((maxy - miny) / grid_m))
    cells = set()
    for iy in range(ny):
        for ix in range(nx):
            center = Point(minx + (ix + 0.5) * grid_m, miny + (iy + 0.5) * grid_m)
            if geometry.covers(center):
                cells.add((ix, iy))
    return cells, (minx, miny)


def occupied_cells(x, y, origin, grid_m: float, eligible: set[tuple[int, int]]) -> set[tuple[int, int]]:
    minx, miny = origin
    indices = zip(np.floor((x - minx) / grid_m).astype(int), np.floor((y - miny) / grid_m).astype(int))
    return {cell for cell in indices if cell in eligible}


def percentiles(values: np.ndarray) -> dict[str, float | None]:
    if not len(values):
        return {name: None for name in ("min", "p05", "median", "p95", "max")}
    q = np.quantile(values, [0.0, 0.05, 0.5, 0.95, 1.0])
    return {name: float(value) for name, value in zip(("min", "p05", "median", "p95", "max"), q)}


def main() -> None:
    started = datetime.now(timezone.utc).isoformat()
    config = json.loads(CONFIG_PATH.read_text())
    source_root = Path(config["source_task"])
    footprint_path = source_root / "control/shared_standard_footprint_4906982.geojson"
    footprint_document = json.loads(footprint_path.read_text())
    footprint = shape(footprint_document["features"][0]["geometry"])
    grid_m = float(config["xy_coverage_grid_m"])
    eligible_cells, origin = grid_cells(footprint, grid_m)
    metrics = {}
    plot_rows = {}
    inputs = {"config": CONFIG_PATH, "footprint": footprint_path}

    for arm in config["arms"]:
        fusion = source_root / f"arms/{arm}/{config['replica']}/evaluation/step_{config['completed_updates']:06d}/fusion"
        raw_path = fusion / "fused_surface.laz"
        classified_path = fusion / "classified_surface.laz"
        inputs[f"{arm}.fused_surface"] = raw_path
        inputs[f"{arm}.classified_surface"] = classified_path
        raw = read_laz(raw_path)
        classified = read_laz(classified_path)
        raw_inside = contains_xy(footprint, raw["x"], raw["y"])
        classified_inside = contains_xy(footprint, classified["x"], classified["y"])
        raw_occupied = occupied_cells(raw["x"][raw_inside], raw["y"][raw_inside], origin, grid_m, eligible_cells)
        labels = classified["classification"][classified_inside]
        class_metrics = {}
        for label in (1, 2, 6):
            mask = classified_inside & (classified["classification"] == label)
            cells = occupied_cells(classified["x"][mask], classified["y"][mask], origin, grid_m, eligible_cells)
            class_metrics[str(label)] = {
                "count": int(mask.sum()),
                "inside_footprint_fraction": float(mask.sum() / max(1, classified_inside.sum())),
                "xy_coverage_cells": len(cells),
                "xy_coverage_pct": 100.0 * len(cells) / max(1, len(eligible_cells)),
                "z_m": percentiles(classified["z"][mask]),
            }
        metrics[arm] = {
            "raw_total_points": int(len(raw["x"])),
            "raw_inside_footprint_points": int(raw_inside.sum()),
            "raw_inside_footprint_fraction": float(raw_inside.mean()),
            "raw_xy_coverage_cells": len(raw_occupied),
            "raw_xy_coverage_pct": 100.0 * len(raw_occupied) / max(1, len(eligible_cells)),
            "raw_z_m_inside_footprint": percentiles(raw["z"][raw_inside]),
            "classified_inside_footprint_points": int(classified_inside.sum()),
            "class_inside_footprint": class_metrics,
        }
        plot_rows[arm] = (raw, raw_inside, classified, classified_inside)

    output_images = OUTPUT_ROOT / "representative_images"
    output_images.mkdir(parents=True, exist_ok=True)
    figure, axes = plt.subplots(len(config["arms"]), 2, figsize=(13.5, 13.0), sharex=True, sharey=True)
    footprint_xy = np.asarray(footprint.exterior.coords)
    class_palette = {1: "#d8d8d8", 2: "#d9a441", 6: "#2a6fbb"}
    labels = {
        "MVS_SURFACE_METRIC": "All fused-mesh ray hits",
        "FUSED_VIS_CONF": "View-supported fused target",
    }
    z_min = min(metrics[arm]["raw_z_m_inside_footprint"]["p05"] for arm in config["arms"])
    z_max = max(metrics[arm]["raw_z_m_inside_footprint"]["p95"] for arm in config["arms"])
    for row, arm in enumerate(config["arms"]):
        raw, raw_inside, classified, classified_inside = plot_rows[arm]
        ax_raw, ax_class = axes[row]
        scatter = ax_raw.scatter(raw["x"][raw_inside], raw["y"][raw_inside], c=raw["z"][raw_inside], s=1.0, cmap="viridis", vmin=z_min, vmax=z_max, rasterized=True)
        figure.colorbar(scatter, ax=ax_raw, fraction=0.047, pad=0.02, label="Z (m), p05–p95 color range")
        for label in (1, 2, 6):
            mask = classified_inside & (classified["classification"] == label)
            ax_class.scatter(classified["x"][mask], classified["y"][mask], s=1.0, color=class_palette[label], label=f"class {label}", rasterized=True)
        for axis in (ax_raw, ax_class):
            axis.plot(footprint_xy[:, 0], footprint_xy[:, 1], color="#202020", linewidth=1.4)
            axis.set_aspect("equal", adjustable="box")
            axis.grid(color="#dedede", linewidth=0.5, alpha=0.55)
            axis.tick_params(labelsize=8)
            axis.set_xlabel("Easting (m)")
            axis.set_ylabel("Northing (m)")
        m = metrics[arm]
        ax_raw.set_title(f"{labels[arm]} — fused_surface before SMRF\n{m['raw_inside_footprint_points']:,} points, {m['raw_xy_coverage_pct']:.1f}% XY grid coverage", fontsize=11, fontweight="bold")
        c2 = m["class_inside_footprint"]["2"]
        c6 = m["class_inside_footprint"]["6"]
        ax_class.set_title(f"After SMRF + footprint overlay\nclass 2: {c2['count']:,} ({100*c2['inside_footprint_fraction']:.1f}%), class 6: {c6['count']:,} ({100*c6['inside_footprint_fraction']:.1f}%)", fontsize=11, fontweight="bold")
        ax_class.legend(loc="upper right", markerscale=5, fontsize=8, framealpha=0.9)
    figure.suptitle("DEBY_LOD2_4906982 — Roofer input point-cloud audit at 20k", fontsize=17, fontweight="bold", y=0.995)
    figure.text(0.5, 0.006, "Same fused point clouds, before and after the frozen Roofer classification pipeline. Shared footprint XY only; no LoD2 Z or roof geometry.", ha="center", fontsize=9)
    figure.tight_layout(rect=(0, 0.02, 1, 0.98))
    png = output_images / "roofer_input_classification_audit.png"
    figure.savefig(png, dpi=170, bbox_inches="tight")
    plt.close(figure)

    csv_path = OUTPUT_ROOT / "pointcloud_metrics.csv"
    with csv_path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=["arm", "raw_inside_points", "raw_xy_coverage_pct", "class1_inside", "class2_inside", "class6_inside", "class2_fraction_pct", "class6_fraction_pct", "class6_xy_coverage_pct"])
        writer.writeheader()
        for arm in config["arms"]:
            m = metrics[arm]
            writer.writerow({
                "arm": arm,
                "raw_inside_points": m["raw_inside_footprint_points"],
                "raw_xy_coverage_pct": m["raw_xy_coverage_pct"],
                "class1_inside": m["class_inside_footprint"]["1"]["count"],
                "class2_inside": m["class_inside_footprint"]["2"]["count"],
                "class6_inside": m["class_inside_footprint"]["6"]["count"],
                "class2_fraction_pct": 100.0 * m["class_inside_footprint"]["2"]["inside_footprint_fraction"],
                "class6_fraction_pct": 100.0 * m["class_inside_footprint"]["6"]["inside_footprint_fraction"],
                "class6_xy_coverage_pct": m["class_inside_footprint"]["6"]["xy_coverage_pct"],
            })
    receipt = {
        "schema": "jointbuildgs.p2.e3_local_4906982.roofer_input_audit.v1",
        "task_id": config["task_id"],
        "status": "COMPLETE",
        "inputs_sha256": {name: sha256(path) for name, path in inputs.items()},
        "metrics": metrics,
        "coverage_definition": {"grid_m": grid_m, "eligible_cell_rule": "cell center covered by shared footprint XY", "occupied_cell_rule": "at least one point in eligible cell"},
        "output_sha256": {"pointcloud_metrics.csv": sha256(csv_path), "representative_images/roofer_input_classification_audit.png": sha256(png)},
        "started_at": started,
        "ended_at": datetime.now(timezone.utc).isoformat(),
        "lod2_z_or_roof_geometry_used": False,
        "scientific_verdict": None,
    }
    (OUTPUT_ROOT / "metrics.json").write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    print(json.dumps(receipt, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
