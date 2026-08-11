#!/usr/bin/env python3
"""Render read-only oblique comparisons for the 4906982 MVC-depth diagnostic.

The script reads existing 20k checkpoints, classified fusion clouds, Roofer
CityJSONSeq outputs, and the shared footprint.  It does not train, fuse,
classify, or rerun Roofer.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import laspy
import matplotlib
import numpy as np
import torch
from matplotlib import pyplot as plt
from mpl_toolkits.mplot3d.art3d import Poly3DCollection
from shapely import contains_xy
from shapely.geometry import shape

from src.visualization.fixed_view_qualitative import load_cityjsonseq


matplotlib.use("Agg")

ARMS = ("DEPTH0", "DEPTH03")
REPLICAS = ("R1", "R2", "R3")
WORLD_SHIFT = np.asarray([690953.0, 5336071.0, 604.0], dtype=np.float64)
ARM_COLORS = {"DEPTH0": "#1688c7", "DEPTH03": "#c51b8a"}


def _setup(ax, bounds: tuple[float, float, float, float], zlim: tuple[float, float]) -> None:
    x0, y0, x1, y1 = bounds
    pad = max(max(x1 - x0, y1 - y0) * 0.16, 3.0)
    ax.set_xlim(x0 - pad, x1 + pad)
    ax.set_ylim(y0 - pad, y1 + pad)
    ax.set_zlim(*zlim)
    ax.set_box_aspect((x1 - x0 + 2 * pad, y1 - y0 + 2 * pad, zlim[1] - zlim[0]))
    ax.view_init(elev=29, azim=-55)
    ax.set_xlabel("E", fontsize=7)
    ax.set_ylabel("N", fontsize=7)
    ax.set_zlabel("Z", fontsize=7)
    ax.tick_params(labelsize=6)


def _footprint_line(ax, footprint, z: float) -> None:
    rings = [np.asarray(footprint.exterior.coords, dtype=np.float64)]
    rings.extend(np.asarray(ring.coords, dtype=np.float64) for ring in footprint.interiors)
    for ring in rings:
        ax.plot(ring[:, 0], ring[:, 1], np.full(len(ring), z), color="#111111", linewidth=1.2)


def _checkpoint_points(path: Path, footprint, zlim: tuple[float, float]) -> tuple[np.ndarray, np.ndarray]:
    payload = torch.load(path, map_location="cpu", weights_only=False)
    state = payload["model"]["state_dict"]
    xyz = state["means"].detach().cpu().numpy().astype(np.float64) + WORLD_SHIFT
    opacity = torch.sigmoid(state["opacities_raw"].reshape(-1)).detach().cpu().numpy()
    xy_keep = contains_xy(footprint.buffer(5.0), xyz[:, 0], xyz[:, 1])
    keep = xy_keep & (xyz[:, 2] >= zlim[0]) & (xyz[:, 2] <= zlim[1]) & (opacity >= 0.1)
    xyz, opacity = xyz[keep], opacity[keep]
    if len(xyz) > 45000:
        order = np.linspace(0, len(xyz) - 1, 45000, dtype=np.int64)
        xyz, opacity = xyz[order], opacity[order]
    return xyz, opacity


def _checkpoint_points_full(path: Path, footprint) -> tuple[np.ndarray, np.ndarray]:
    payload = torch.load(path, map_location="cpu", weights_only=False)
    state = payload["model"]["state_dict"]
    xyz = state["means"].detach().cpu().numpy().astype(np.float64) + WORLD_SHIFT
    opacity = torch.sigmoid(state["opacities_raw"].reshape(-1)).detach().cpu().numpy()
    keep = contains_xy(footprint.buffer(5.0), xyz[:, 0], xyz[:, 1]) & (opacity >= 0.1)
    xyz, opacity = xyz[keep], opacity[keep]
    ordinary = np.flatnonzero(xyz[:, 2] <= 650.0)
    high = np.flatnonzero(xyz[:, 2] > 650.0)
    if len(ordinary) > 22000:
        ordinary = ordinary[np.linspace(0, len(ordinary) - 1, 22000, dtype=np.int64)]
    if len(high) > 8000:
        high = high[np.linspace(0, len(high) - 1, 8000, dtype=np.int64)]
    selected = np.concatenate((ordinary, high))
    return xyz[selected], opacity[selected]


def render_gs(task_root: Path, footprint, output: Path) -> None:
    zlim = (555.0, 620.0)
    fig = plt.figure(figsize=(15, 8.5), dpi=150, constrained_layout=True)
    for row, arm in enumerate(ARMS):
        for col, replica in enumerate(REPLICAS):
            ax = fig.add_subplot(2, 3, row * 3 + col + 1, projection="3d", proj_type="ortho")
            xyz, opacity = _checkpoint_points(
                task_root / "arms" / arm / replica / "ckpt/step_020000.pt", footprint, zlim
            )
            ax.scatter(
                xyz[:, 0], xyz[:, 1], xyz[:, 2], c=xyz[:, 2], cmap="turbo",
                vmin=zlim[0], vmax=zlim[1], s=0.45, alpha=np.clip(opacity, 0.18, 0.8),
                linewidths=0, depthshade=False, rasterized=True,
            )
            _footprint_line(ax, footprint, 559.5)
            _setup(ax, footprint.bounds, zlim)
            ax.set_title(f"{arm} {replica} | 20k Gaussian centers | roof-scale Z", fontsize=9)
    fig.suptitle("DEBY_LOD2_4906982 | fixed oblique GS geometry | Z=555..620 m", fontsize=14)
    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output)
    plt.close(fig)


def render_gs_full(task_root: Path, footprint, output: Path) -> None:
    zlim = (550.0, 700.0)
    fig = plt.figure(figsize=(15, 8.5), dpi=150, constrained_layout=True)
    for row, arm in enumerate(ARMS):
        for col, replica in enumerate(REPLICAS):
            ax = fig.add_subplot(2, 3, row * 3 + col + 1, projection="3d", proj_type="ortho")
            xyz, opacity = _checkpoint_points_full(
                task_root / "arms" / arm / replica / "ckpt/step_020000.pt", footprint
            )
            high = xyz[:, 2] > 650.0
            if np.any(~high):
                ax.scatter(
                    xyz[~high, 0], xyz[~high, 1], xyz[~high, 2], color="#7f8c8d",
                    s=0.35, alpha=np.clip(opacity[~high], 0.12, 0.45), linewidths=0,
                    depthshade=False, rasterized=True,
                )
            if np.any(high):
                ax.scatter(
                    xyz[high, 0], xyz[high, 1], xyz[high, 2], color="#d62728",
                    s=2.2, alpha=np.clip(opacity[high], 0.35, 0.9), linewidths=0,
                    depthshade=False, rasterized=True,
                )
            _footprint_line(ax, footprint, 559.5)
            _setup(ax, footprint.bounds, zlim)
            max_z = float(np.max(xyz[:, 2])) if len(xyz) else float("nan")
            ax.set_title(f"{arm} {replica} | footprint-buffer max Z={max_z:.1f} m", fontsize=9)
    fig.suptitle("DEBY_LOD2_4906982 | fixed oblique GS geometry | footprint+5 m Z axis | red: Z>650 m", fontsize=14)
    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output)
    plt.close(fig)


def _city_faces(ax, surfaces, arm: str) -> None:
    for surface in surfaces:
        if surface.semantic != "RoofSurface":
            continue
        xyz = np.asarray(surface.xyz, dtype=np.float64)
        if len(xyz) < 3:
            continue
        ax.add_collection3d(
            Poly3DCollection(
                [xyz], facecolor=ARM_COLORS[arm], edgecolor="#222222", linewidth=0.35, alpha=0.82
            )
        )


def render_roofer(task_root: Path, footprint, output: Path) -> None:
    zlim = (555.0, 620.0)
    fig = plt.figure(figsize=(15, 8.5), dpi=150, constrained_layout=True)
    for row, arm in enumerate(ARMS):
        for col, replica in enumerate(REPLICAS):
            ax = fig.add_subplot(2, 3, row * 3 + col + 1, projection="3d", proj_type="ortho")
            base = task_root / "arms" / arm / replica / "evaluation/step_020000/fusion"
            cloud = laspy.read(base / "classified_surface.laz")
            xyz = np.column_stack((np.asarray(cloud.x), np.asarray(cloud.y), np.asarray(cloud.z)))
            cls = np.asarray(cloud.classification, dtype=np.uint8)
            keep = contains_xy(footprint.buffer(5.0), xyz[:, 0], xyz[:, 1]) & (cls == 6)
            xyz = xyz[keep]
            if len(xyz) > 18000:
                xyz = xyz[np.linspace(0, len(xyz) - 1, 18000, dtype=np.int64)]
            ax.scatter(
                xyz[:, 0], xyz[:, 1], xyz[:, 2], color="#a8a8a8", s=0.7,
                alpha=0.22, linewidths=0, depthshade=False, rasterized=True,
            )
            surfaces = load_cityjsonseq(base / "roofer/output/690897_5336168.city.jsonl")
            _city_faces(ax, surfaces, arm)
            _footprint_line(ax, footprint, 559.5)
            _setup(ax, footprint.bounds, zlim)
            ax.set_title(f"{arm} {replica} | class-6 evidence + Roofer", fontsize=9)
    fig.suptitle("DEBY_LOD2_4906982 | fixed oblique classified evidence and Roofer | 20k", fontsize=14)
    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output)
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--task-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    footprint_doc = json.loads((args.task_root / "control/shared_standard_footprint_4906982.geojson").read_text())
    footprint = shape(footprint_doc["features"][0]["geometry"])
    render_gs(args.task_root, footprint, args.output_dir / "gs_oblique_20k.png")
    render_gs_full(args.task_root, footprint, args.output_dir / "gs_oblique_full_z_20k.png")
    render_roofer(args.task_root, footprint, args.output_dir / "roofer_oblique_20k.png")
    print(json.dumps({
        "status": "complete",
        "inputs_modified": False,
        "training_reruns": 0,
        "fusion_reruns": 0,
        "roofer_reruns": 0,
        "outputs": [
            str(args.output_dir / "gs_oblique_20k.png"),
            str(args.output_dir / "gs_oblique_full_z_20k.png"),
            str(args.output_dir / "roofer_oblique_20k.png"),
        ],
        "scientific_verdict": None,
    }, indent=2))


if __name__ == "__main__":
    main()
