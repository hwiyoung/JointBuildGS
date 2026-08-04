#!/usr/bin/env python3
"""Render all 199 C3-1/C3-2 native-to-Roofer technical case sheets."""

from __future__ import annotations

from collections import defaultdict
import argparse
import hashlib
import html
import json
from pathlib import Path
from typing import Any, Mapping

import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d.art3d import Poly3DCollection
import numpy as np
import torch

from scripts.p2.c3_utarget199_postprocess_v1.contract import load_config
from scripts.p2.utarget199_contract_results_v1.render_case_sheets import (
    BBox,
    PointSet,
    crop_points,
    draw_roofprint,
    load_geometry,
    plot_oblique,
    plot_top_output,
    plot_top_points,
    rows,
)
from src.stage2.model import quat_to_rotmat


COLORS = np.asarray(
    [[0.35, 0.35, 0.35, 0.25], [0.84, 0.37, 0.0, 0.45], [0.0, 0.45, 0.70, 0.45], [0.0, 0.62, 0.45, 0.35]],
    dtype=np.float64,
)


def _write_new(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(data)


def _checkpoint_arrays(path: Path, shift: np.ndarray) -> dict[str, np.ndarray]:
    payload = torch.load(path, map_location="cpu", weights_only=True)
    state = payload["state_dict"]
    means = state["means"].numpy().astype(np.float64) + shift
    rotations = quat_to_rotmat(state["quats"].to(torch.float64)).numpy()
    scales = torch.exp(state["log_scales"].to(torch.float64)).numpy()
    labels = torch.argmax(state["sem_logits"], dim=1).numpy().astype(np.uint8)
    return {"means": means, "rotations": rotations, "scales": scales, "labels": labels}


def _native_crop(native: Mapping[str, np.ndarray], bbox: BBox) -> np.ndarray:
    xyz = native["means"]
    return np.where(
        (xyz[:, 0] >= bbox.min_x) & (xyz[:, 0] <= bbox.max_x)
        & (xyz[:, 1] >= bbox.min_y) & (xyz[:, 1] <= bbox.max_y)
    )[0]


def plot_native_top(axis: Any, native: Mapping[str, np.ndarray], bbox: BBox, title: str) -> None:
    indices = _native_crop(native, bbox)
    if len(indices) > 15000:
        indices = indices[np.linspace(0, len(indices) - 1, 15000, dtype=int)]
    axis.set_title(title, fontsize=11)
    if not len(indices):
        axis.text(0.5, 0.5, "NO NATIVE GAUSSIANS", ha="center", va="center", transform=axis.transAxes)
    else:
        xyz = native["means"][indices]
        axis.scatter(xyz[:, 0], xyz[:, 1], c=COLORS[native["labels"][indices]], s=3, linewidths=0)
    axis.set_xlim(bbox.min_x, bbox.max_x)
    axis.set_ylim(bbox.min_y, bbox.max_y)
    axis.set_aspect("equal")
    axis.tick_params(labelsize=7)


def plot_native_mesh(axis: Any, native: Mapping[str, np.ndarray], bbox: BBox, title: str) -> None:
    indices = _native_crop(native, bbox)
    if len(indices) > 2500:
        indices = indices[np.linspace(0, len(indices) - 1, 2500, dtype=int)]
    axis.set_title(title, fontsize=11)
    if len(indices):
        centers = native["means"][indices]
        rotations = native["rotations"][indices]
        scales = native["scales"][indices]
        u = rotations[:, :, 0] * scales[:, 0:1]
        v = rotations[:, :, 1] * scales[:, 1:2]
        quads = np.stack((centers - u - v, centers + u - v, centers + u + v, centers - u + v), axis=1)
        collection = Poly3DCollection(
            quads,
            facecolors=COLORS[native["labels"][indices]],
            edgecolors="none",
        )
        axis.add_collection3d(collection)
        axis.set_zlim(float(np.nanpercentile(centers[:, 2], 2)), float(np.nanpercentile(centers[:, 2], 98)))
    else:
        axis.text2D(0.5, 0.5, "NO NATIVE SURFELS", ha="center", va="center", transform=axis.transAxes)
    axis.set_xlim(bbox.min_x, bbox.max_x)
    axis.set_ylim(bbox.min_y, bbox.max_y)
    axis.view_init(elev=28, azim=-55)
    axis.tick_params(labelsize=6)


def plot_reference_section(
    axis: Any,
    points: PointSet,
    surfaces: list[Any],
    reference: PointSet,
    bbox: BBox,
    title: str,
) -> None:
    axis.set_title(title, fontsize=11)
    major_x = bbox.width >= bbox.height
    cross_axis = 1 if major_x else 0
    along_axis = 0 if major_x else 1
    anchor = float(np.median(reference.xyz[:, cross_axis])) if len(reference.xyz) else bbox.center[cross_axis]
    band = max(min(bbox.width, bbox.height) * 0.12, 0.75)
    cropped = crop_points(points, bbox)
    if len(cropped.xyz):
        keep = np.abs(cropped.xyz[:, cross_axis] - anchor) <= band
        xyz = cropped.xyz[keep]
        if len(xyz):
            axis.scatter(xyz[:, along_axis], xyz[:, 2], s=5, c="#0072B2", alpha=0.55)
    if len(reference.xyz):
        keep = np.abs(reference.xyz[:, cross_axis] - anchor) <= band
        xyz = reference.xyz[keep]
        if len(xyz):
            axis.scatter(xyz[:, along_axis], xyz[:, 2], s=10, c="#009E73", marker="x")
    for surface in surfaces:
        ring = surface.xyz
        keep = np.abs(ring[:, cross_axis] - anchor) <= band
        xyz = ring[keep]
        if len(xyz) >= 2:
            order = np.argsort(xyz[:, along_axis])
            axis.plot(xyz[order, along_axis], xyz[order, 2], color="#D55E00", linewidth=1.2)
    axis.set_xlabel("Easting" if major_x else "Northing", fontsize=8)
    axis.set_ylabel("Z (m)", fontsize=8)
    axis.tick_params(labelsize=7)


def _metric_text(row: Mapping[str, Any]) -> str:
    metrics = row["continuous_metrics"]
    def value(name: str) -> str:
        return "NA" if metrics.get(name) is None else f"{float(metrics[name]):.3f}"
    return (
        f"association={row['association_status']}\n"
        f"one-to-one={row['one_to_one_building_component']}  G0={row['G0_generated']}  G1={row['G1_schema_semantic']}\n"
        f"UAS cells={row['reference_cell_count']}  MAE-Z={value('height_error_mae_m')} m  RMSZ={value('RMSZ_m')} m\n"
        f"surface RMSE={value('surface_distance_rmse_m')} m  P95={value('surface_distance_p95_m')} m\n"
        "G2/G3/G4/PASS_usable=null; scientific_verdict=null"
    )


def render_all(
    *,
    task_root: Path,
    checkpoint_root: Path,
) -> dict[str, Any]:
    completed = task_root / "control/qualitative_complete_v1.json"
    if completed.is_file():
        return {**json.loads(completed.read_text(encoding="utf-8")), "fast_path": True}
    config = load_config()
    finalized = json.loads((task_root / "control/finalized_v1.json").read_text(encoding="utf-8"))
    result_rows = rows(task_root / finalized["building_condition_metrics"]["path"])
    by_building: defaultdict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    for row in result_rows:
        by_building[row["building_id"]][row["condition_id"]] = row
    associated = json.loads((task_root / "control/population_associated_v1.json").read_text(encoding="utf-8"))
    units = {
        row["operation_unit_id"]: row
        for row in rows(task_root / associated["execution_units"]["path"])
    }
    refs_by_building: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows(task_root / associated["reference_cells"]["path"]):
        refs_by_building[row["stable_id"]].append(row)
    shift = np.asarray(config["frame"]["local_shift_xyz"], dtype=np.float64)
    natives = {}
    for condition in config["conditions"]:
        checkpoint = checkpoint_root / condition["checkpoint_relative_path"]
        natives[condition["condition_id"]] = _checkpoint_arrays(checkpoint, shift)
    geometry_cache: dict[str, dict[str, Any]] = {}
    output = task_root / "qualitative/case_sheets"
    output.mkdir(parents=True, exist_ok=False)
    manifests = []
    condition_ids = [row["condition_id"] for row in config["conditions"]]
    for index, building_id in enumerate(sorted(by_building), 1):
        sample = by_building[building_id][condition_ids[0]]
        bbox = BBox(*(float(sample[name]) for name in ("bbox_min_x", "bbox_min_y", "bbox_max_x", "bbox_max_y")))
        viewport = bbox.padded(0.35, 5.0)
        refs = refs_by_building[building_id]
        reference = PointSet(
            np.asarray([[float(row["cell_x"]), float(row["cell_y"]), float(row["top_z"])] for row in refs], dtype=np.float64).reshape((-1, 3)),
            None,
        )
        figure = plt.figure(figsize=(19, 25), dpi=115, constrained_layout=True)
        grid = figure.add_gridspec(6, 3, width_ratios=[0.72, 1, 1])
        figure.suptitle(f"{building_id} — C3 native GS → common Roofer read-out — {index}/199", fontsize=18)
        reference_axis = figure.add_subplot(grid[0:2, 0])
        plot_top_points(reference_axis, reference, viewport, title="Independent current UAS evaluation cells")
        reference_axis.add_patch(plt.Rectangle((bbox.min_x, bbox.min_y), bbox.width, bbox.height, fill=False, edgecolor="black", linewidth=1.3))
        notes = figure.add_subplot(grid[2:6, 0])
        notes.axis("off")
        notes.text(
            0.0, 1.0,
            "READING ORDER\n\n"
            "1. Native Gaussian centers\n"
            "2. Native oriented surfel mesh\n"
            "3. Common 1 m class-2/6 Roofer input\n"
            "4. Roofer roof + independent UAS cells\n"
            "5. Roofer output oblique\n"
            "6. Reference-centered principal section\n\n"
            "orange=roof Gaussian/surface\nblue=wall/input\ngreen=independent UAS evaluation\n"
            "R_derived comes from the C3 component itself; no GT/external roofprint.\n\n"
            "Stable-ID bbox and UAS cells are opened only after both C3 geometries are frozen.\n"
            "This sheet is technical evidence, not a scientific verdict.",
            va="top", fontsize=11, linespacing=1.5,
        )
        for column, condition_id in enumerate(condition_ids, 1):
            row = by_building[building_id][condition_id]
            unit_id = row.get("operation_unit_id")
            if unit_id and unit_id not in geometry_cache:
                geometry_cache[unit_id] = load_geometry(task_root, units[unit_id])
            geometry = geometry_cache.get(unit_id, {"points": PointSet.empty(), "surfaces": [], "roofprint": []})
            axis = figure.add_subplot(grid[0, column])
            plot_native_top(axis, natives[condition_id], viewport, f"{condition_id} — native Gaussian centers")
            axis.add_patch(plt.Rectangle((bbox.min_x, bbox.min_y), bbox.width, bbox.height, fill=False, edgecolor="black", linewidth=1.0))
            axis = figure.add_subplot(grid[1, column], projection="3d")
            plot_native_mesh(axis, natives[condition_id], viewport, "native oriented 2D Gaussian surfel mesh")
            axis = figure.add_subplot(grid[2, column])
            plot_top_points(axis, geometry["points"], viewport, classes=True, title="common Roofer input class 2/6 + R_derived")
            draw_roofprint(axis, geometry["roofprint"])
            axis.add_patch(plt.Rectangle((bbox.min_x, bbox.min_y), bbox.width, bbox.height, fill=False, edgecolor="black", linewidth=1.0))
            axis = figure.add_subplot(grid[3, column])
            plot_top_output(axis, geometry["surfaces"], reference, viewport, title="Roofer roof + independent UAS evaluation")
            axis.add_patch(plt.Rectangle((bbox.min_x, bbox.min_y), bbox.width, bbox.height, fill=False, edgecolor="black", linewidth=1.0))
            axis = figure.add_subplot(grid[4, column], projection="3d")
            plot_oblique(axis, PointSet.empty(), geometry["surfaces"], viewport, title="Roofer output oblique")
            axis = figure.add_subplot(grid[5, column])
            plot_reference_section(axis, geometry["points"], geometry["surfaces"], reference, viewport, "reference-centered principal section")
            axis.text(0.01, 0.99, _metric_text(row), transform=axis.transAxes, va="top", fontsize=8, bbox={"facecolor": "white", "alpha": 0.78, "edgecolor": "#777"})
        path = output / f"{building_id}_C3_pair_v1.png"
        figure.savefig(path, metadata={"Software": "JointBuildGS C3 U_target postprocess"})
        plt.close(figure)
        data = path.read_bytes()
        manifests.append({
            "building_id": building_id,
            "path": path.relative_to(task_root).as_posix(),
            "bytes": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
            "scientific_verdict": None,
        })
        print(f"rendered {index}/199 {building_id}", flush=True)
    manifest_data = b"".join((json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n").encode() for row in manifests)
    _write_new(task_root / "qualitative/case_sheet_manifest_v1.jsonl", manifest_data)
    lines = [
        "<!doctype html><html lang='ko'><head><meta charset='utf-8'><title>C3 U_target 199</title>",
        "<style>body{font-family:sans-serif;margin:24px}table{border-collapse:collapse;width:100%}th,td{border:1px solid #ccc;padding:7px}img{width:420px}code{font-size:12px}</style></head><body>",
        "<h1>C3-1 / C3-2 — U_target 199동 native GS → Roofer</h1>",
        "<p>199동 전체를 표시합니다. 72/10 보조 분류는 사용하지 않습니다. G2/G3/G4/PASS_usable 및 scientific_verdict는 null입니다.</p>",
        "<table><thead><tr><th>건물</th><th>case sheet</th></tr></thead><tbody>",
    ]
    for row in manifests:
        rel = Path(row["path"]).relative_to("qualitative").as_posix()
        lines.append(f"<tr><td><code>{html.escape(row['building_id'])}</code></td><td><a href='{html.escape(rel)}'><img loading='lazy' src='{html.escape(rel)}'></a></td></tr>")
    lines.append("</tbody></table></body></html>")
    _write_new(task_root / "qualitative/index.html", "\n".join(lines).encode("utf-8"))
    body = {
        "schema": "jointbuildgs.c3_utarget199_qualitative_complete.v1",
        "status": "COMPLETE",
        "case_sheet_count": len(manifests),
        "condition_ids": condition_ids,
        "native_point_cloud_shown": True,
        "native_surfel_mesh_shown": True,
        "roofer_input_shown": True,
        "roofer_output_shown": True,
        "reference_centered_section": True,
        "scientific_verdict": None,
    }
    _write_new(task_root / "control/qualitative_complete_v1.json", (json.dumps(body, sort_keys=True, separators=(",", ":")) + "\n").encode())
    return body


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--task-root", type=Path, required=True)
    parser.add_argument("--checkpoint-root", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(render_all(task_root=args.task_root, checkpoint_root=args.checkpoint_root), sort_keys=True))


if __name__ == "__main__":
    main()
