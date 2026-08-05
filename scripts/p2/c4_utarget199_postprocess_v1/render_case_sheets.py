#!/usr/bin/env python3
"""Render 199 matched C3-2/C4 sheets, integrated pages, gallery, and PDF."""

from __future__ import annotations

from collections import defaultdict
import argparse
import hashlib
import html
import json
from pathlib import Path
from typing import Any, Mapping

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d.art3d import Poly3DCollection
import numpy as np
from PIL import Image
import torch

from scripts.p2.c1_c2_c3_consolidated_results_v1.compose_v4 import ring_section_segment
from scripts.p2.c1_c2_c3_consolidated_results_v1.compose_v5 import draw_section_locator
from scripts.p2.c3_tsdf_roof_diagnostic_v1.render import _principal_frame
from scripts.p2.c3_utarget199_postprocess_v1.render_case_sheets import COLORS
from scripts.p2.c4_utarget199_postprocess_v1.contract import CONDITION_ID, load_config
from scripts.p2.utarget199_contract_results_v1.render_case_sheets import (
    BBox,
    PointSet,
    draw_roofprint,
    load_geometry,
    plot_oblique,
    plot_top_output,
    plot_top_points,
    rows,
)
from scripts.p2.utarget199_presentation_v5.render import load_references
from src.stage2.model import quat_to_rotmat


def _write_new(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(data)


def _checkpoint_arrays(path: Path, shift: np.ndarray) -> dict[str, np.ndarray]:
    payload = torch.load(path, map_location="cpu", weights_only=True)
    state = payload["state_dict"]
    return {
        "means": state["means"].numpy().astype(np.float64) + shift,
        "rotations": quat_to_rotmat(state["quats"].to(torch.float64)).numpy(),
        "scales": torch.exp(state["log_scales"].to(torch.float64)).numpy(),
        "labels": torch.argmax(state["sem_logits"], dim=1).numpy().astype(np.uint8),
    }


def _native_crop(native: Mapping[str, np.ndarray], bbox: BBox) -> np.ndarray:
    xyz = native["means"]
    return np.where(
        (xyz[:, 0] >= bbox.min_x) & (xyz[:, 0] <= bbox.max_x)
        & (xyz[:, 1] >= bbox.min_y) & (xyz[:, 1] <= bbox.max_y)
    )[0]


def plot_native_top(axis: Any, native: Mapping[str, np.ndarray], bbox: BBox, reference: Any, title: str) -> None:
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
    draw_section_locator(axis, reference)


def plot_native_mesh(axis: Any, native: Mapping[str, np.ndarray], bbox: BBox, zlim: tuple[float, float], title: str) -> None:
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
        axis.add_collection3d(Poly3DCollection(quads, facecolors=COLORS[native["labels"][indices]], edgecolors="none"))
    else:
        axis.text2D(0.5, 0.5, "NO NATIVE SURFELS", ha="center", va="center", transform=axis.transAxes)
    axis.set_xlim(bbox.min_x, bbox.max_x)
    axis.set_ylim(bbox.min_y, bbox.max_y)
    axis.set_zlim(*zlim)
    axis.view_init(elev=28, azim=-55)
    axis.tick_params(labelsize=6)


def _lod2_zlim(reference: Any, dz: float) -> tuple[float, float]:
    values = [float(value) + dz for _semantic, ring in reference.surface_rings for value in np.asarray(ring)[:, 2]]
    lo, hi = min(values), max(values)
    pad = max(2.0, 0.08 * (hi - lo))
    return lo - pad, hi + pad


def plot_pca_section(
    axis: Any,
    geometry: Mapping[str, Any],
    current_reference: PointSet,
    lod2_reference: Any,
    zlim: tuple[float, float],
    title: str,
) -> None:
    axis.set_title(title, fontsize=11)
    center, principal, cross = _principal_frame(lod2_reference)
    points = geometry["points"].xyz
    if len(points):
        local = points[:, :2] - center
        band = max(min(float(np.ptp(local @ cross)) * 0.08, 1.5), 0.6)
        keep = np.abs(local @ cross) <= band
        axis.scatter(local[keep] @ principal, points[keep, 2], s=5, c="#0072B2", alpha=0.55)
    if len(current_reference.xyz):
        local = current_reference.xyz[:, :2] - center
        band = max(min(float(np.ptp(local @ cross)) * 0.08, 1.5), 0.6)
        keep = np.abs(local @ cross) <= band
        axis.scatter(local[keep] @ principal, current_reference.xyz[keep, 2], s=10, c="#009E73", marker="x")
    for surface in geometry["surfaces"]:
        segment = ring_section_segment(surface.xyz, lod2_reference)
        if segment is not None:
            axis.plot(segment[:, 0], segment[:, 1], color="#D55E00", linewidth=1.5)
    dz = 45.7
    for semantic, ring in lod2_reference.surface_rings:
        if semantic != "RoofSurface":
            continue
        xyz = np.asarray(ring, dtype=np.float64) + np.asarray([0.0, 0.0, dz])
        segment = ring_section_segment(xyz, lod2_reference)
        if segment is not None:
            axis.plot(segment[:, 0], segment[:, 1], color="#7C3AED", linewidth=1.4, linestyle="--")
    footprint = np.asarray(lod2_reference.footprint.convex_hull.exterior.coords, dtype=np.float64)
    along = (footprint - center) @ principal
    axis.set_xlim(float(along.min() - 3), float(along.max() + 3))
    axis.set_ylim(*zlim)
    axis.set_xlabel("Footprint-PCA A→B (m)", fontsize=8)
    axis.set_ylabel("common Z (m)", fontsize=8)
    axis.tick_params(labelsize=7)
    axis.grid(True, color="#dddddd", linewidth=0.6)


def _value(metrics: Mapping[str, Any], name: str) -> str:
    return "NA" if metrics.get(name) is None else f"{float(metrics[name]):.3f}"


def _metric_text(
    condition_id: str,
    row: Mapping[str, Any],
    delta: Mapping[str, Any] | None,
) -> str:
    if condition_id == "C3_2_SEM_DEPTH":
        current = row["continuous_metrics"]
        return (
            f"association={row['association_status']}  one-to-one={row['one_to_one_building_component']}\n"
            f"Current UAS: MAE-Z={_value(current, 'height_error_mae_m')} m  RMSZ={_value(current, 'RMSZ_m')} m\n"
            f"surface RMSE={_value(current, 'surface_distance_rmse_m')} m  P95={_value(current, 'surface_distance_p95_m')} m\n"
            "matched sealed C3-2 control; official PASS_usable=null"
        )
    current, lod2 = row["current_uas_metrics"], row["lod2_2022_metrics"]
    delta_metrics = (delta or {}).get("current_uas_metric_delta", {})
    delta_mae = delta_metrics.get("height_error_mae_m")
    return (
        f"association={row['association_status']}  one-to-one={row['one_to_one_building_component']}\n"
        f"Current UAS: MAE-Z={_value(current, 'height_error_mae_m')} m  RMSZ={_value(current, 'RMSZ_m')} m\n"
        f"2022 LoD2: MAE-Z={_value(lod2, 'height_error_mae_m')} m  status={row['lod2_reference_status']}\n"
        f"C4−C3-2 ΔMAE-Z={'NA' if delta_mae is None else f'{float(delta_mae):+.3f}'} m\n"
        "LoD2 role=PRIOR_RELATED_REFERENCE_DIAGNOSTIC_ONLY; PASS_usable=null"
    )


def _task_tables(task_root: Path) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    finalized = json.loads((task_root / "control/finalized_v1.json").read_text(encoding="utf-8"))
    metric_key = "building_c4_metrics" if "building_c4_metrics" in finalized else "building_condition_metrics"
    result_rows = rows(task_root / finalized[metric_key]["path"])
    by_building = {row["building_id"]: row for row in result_rows if row.get("condition_id") in {CONDITION_ID, "C3_2_SEM_DEPTH"}}
    associated = json.loads((task_root / "control/population_associated_v1.json").read_text(encoding="utf-8"))
    units = {
        row["operation_unit_id"]: row for row in rows(task_root / associated["execution_units"]["path"])
    }
    return by_building, units


def _integrated_page(source: Path, pair: Path, output: Path) -> None:
    with Image.open(source) as first_source, Image.open(pair) as second_source:
        first = first_source.convert("RGB")
        second = second_source.convert("RGB")
        width = max(first.width, second.width)
        canvas = Image.new("RGB", (width, first.height + 40 + second.height), "white")
        canvas.paste(first, ((width - first.width) // 2, 0))
        canvas.paste(second, ((width - second.width) // 2, first.height + 40))
        output.parent.mkdir(parents=True, exist_ok=True)
        canvas.save(output, format="PNG", compress_level=4)
        first.close()
        second.close()


def render_all(*, task_root: Path, artifact_root: Path) -> dict[str, Any]:
    completed = task_root / "control/qualitative_complete_v1.json"
    if completed.is_file():
        return {**json.loads(completed.read_text(encoding="utf-8")), "fast_path": True}
    config = load_config()
    c3_root = artifact_root / config["matched_c3_2"]["postprocess_relative_root"]
    c4_rows, c4_units = _task_tables(task_root)
    c3_rows, c3_units = _task_tables(c3_root)
    delta_control = json.loads((task_root / "control/finalized_v1.json").read_text(encoding="utf-8"))
    deltas = {row["building_id"]: row for row in rows(task_root / delta_control["matched_delta"]["path"])}
    current_refs: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    associated = json.loads((task_root / "control/population_associated_v1.json").read_text(encoding="utf-8"))
    for row in rows(task_root / associated["current_uas_reference"]["path"]):
        current_refs[row["stable_id"]].append(row)
    building_ids = sorted(c4_rows)
    lod2_paths = [artifact_root / value for value in config["inputs"]["lod2_relative_paths"]]
    lod2_refs = load_references(lod2_paths, building_ids)
    shift = np.asarray(config["frame"]["local_shift_xyz"], dtype=np.float64)
    natives = {
        "C3_2_SEM_DEPTH": _checkpoint_arrays(artifact_root / config["matched_c3_2"]["checkpoint_relative_path"], shift),
        CONDITION_ID: _checkpoint_arrays(artifact_root / config["condition"]["checkpoint_relative_path"], shift),
    }
    geometry_cache: dict[tuple[str, str], dict[str, Any]] = {}
    pair_root = task_root / "qualitative/case_sheets"
    pair_root.mkdir(parents=True, exist_ok=False)
    full_root = task_root / "qualitative/full_resolution_pages"
    full_root.mkdir(parents=True, exist_ok=False)
    old_root = artifact_root / config["inputs"]["utarget_v5_relative_root"] / "qualitative/case_pages"
    manifests = []
    full_manifests = []
    for index, building_id in enumerate(building_ids, 1):
        sample = c4_rows[building_id]
        bbox = BBox(*(float(sample[name]) for name in ("bbox_min_x", "bbox_min_y", "bbox_max_x", "bbox_max_y")))
        viewport = bbox.padded(0.35, 5.0)
        lod2 = lod2_refs[building_id]
        zlim = _lod2_zlim(lod2, float(config["frame"]["lod2_orthometric_to_current_ellipsoidal_m"]))
        refs = current_refs[building_id]
        current_reference = PointSet(
            np.asarray([[float(row["cell_x"]), float(row["cell_y"]), float(row["top_z"])] for row in refs], dtype=np.float64).reshape((-1, 3)),
            None,
        )
        figure = plt.figure(figsize=(19, 25), dpi=115, constrained_layout=True)
        grid = figure.add_gridspec(6, 3, width_ratios=[0.72, 1, 1])
        figure.suptitle(f"{building_id} — matched C3-2 vs C4 Existing ALS — {index}/199", fontsize=18)
        reference_axis = figure.add_subplot(grid[0:2, 0])
        plot_top_points(reference_axis, current_reference, viewport, title="Independent current UAS evaluation cells")
        reference_axis.add_patch(plt.Rectangle((bbox.min_x, bbox.min_y), bbox.width, bbox.height, fill=False, edgecolor="black", linewidth=1.3))
        draw_section_locator(reference_axis, lod2)
        notes = figure.add_subplot(grid[2:6, 0])
        notes.axis("off")
        notes.text(
            0.0, 1.0,
            "MATCHED READING ORDER\n\n"
            "Left: sealed C3-2 image-derived base\n"
            "Right: same base + Existing ALS prior\n\n"
            "1. Native Gaussian centers\n2. Native oriented surfel mesh\n"
            "3. Common Roofer input\n4. Roofer output + current UAS\n"
            "5. Roofer output oblique\n6. One footprint-PCA principal section\n\n"
            "purple dashed=2022 LoD2 evaluation context\n"
            "green x=current UAS evaluation\n"
            "C5=NOT_RUN\n\n"
            "Missing/unassociated/failed rows are retained.\n"
            "G2/G3/G4/PASS_usable and scientific_verdict remain null.",
            va="top", fontsize=11, linespacing=1.5,
        )
        for column, condition_id in enumerate(("C3_2_SEM_DEPTH", CONDITION_ID), 1):
            row = c3_rows[building_id] if condition_id == "C3_2_SEM_DEPTH" else c4_rows[building_id]
            units = c3_units if condition_id == "C3_2_SEM_DEPTH" else c4_units
            root = c3_root if condition_id == "C3_2_SEM_DEPTH" else task_root
            unit_id = row.get("operation_unit_id")
            key = (condition_id, str(unit_id))
            if unit_id and key not in geometry_cache:
                geometry_cache[key] = load_geometry(root, units[unit_id])
            geometry = geometry_cache.get(key, {"points": PointSet.empty(), "surfaces": [], "roofprint": []})
            axis = figure.add_subplot(grid[0, column])
            plot_native_top(axis, natives[condition_id], viewport, lod2, f"{condition_id} — native Gaussian centers")
            axis.add_patch(plt.Rectangle((bbox.min_x, bbox.min_y), bbox.width, bbox.height, fill=False, edgecolor="black", linewidth=1.0))
            axis = figure.add_subplot(grid[1, column], projection="3d")
            plot_native_mesh(axis, natives[condition_id], viewport, zlim, "native oriented 2D Gaussian surfel mesh")
            axis = figure.add_subplot(grid[2, column])
            plot_top_points(axis, geometry["points"], viewport, classes=True, title="common Roofer input class 2/6 + R_derived")
            draw_roofprint(axis, geometry["roofprint"])
            axis.add_patch(plt.Rectangle((bbox.min_x, bbox.min_y), bbox.width, bbox.height, fill=False, edgecolor="black", linewidth=1.0))
            draw_section_locator(axis, lod2)
            axis = figure.add_subplot(grid[3, column])
            plot_top_output(axis, geometry["surfaces"], current_reference, viewport, title="Roofer roof + independent current UAS")
            axis.add_patch(plt.Rectangle((bbox.min_x, bbox.min_y), bbox.width, bbox.height, fill=False, edgecolor="black", linewidth=1.0))
            draw_section_locator(axis, lod2)
            axis = figure.add_subplot(grid[4, column], projection="3d")
            plot_oblique(axis, PointSet.empty(), geometry["surfaces"], viewport, title="Roofer output oblique")
            axis.set_zlim(*zlim)
            axis = figure.add_subplot(grid[5, column])
            plot_pca_section(axis, geometry, current_reference, lod2, zlim, "canonical footprint-PCA section")
            axis.text(0.01, 0.99, _metric_text(condition_id, row, deltas.get(building_id)), transform=axis.transAxes, va="top", fontsize=7.5, bbox={"facecolor": "white", "alpha": 0.82, "edgecolor": "#777"})
        pair_path = pair_root / f"{building_id}_C3_2_C4_matched_v1.png"
        figure.savefig(pair_path, metadata={"Software": "JointBuildGS C4 U_target postprocess"})
        plt.close(figure)
        pair_data = pair_path.read_bytes()
        manifests.append({
            "building_id": building_id,
            "path": pair_path.relative_to(task_root).as_posix(),
            "bytes": len(pair_data),
            "sha256": hashlib.sha256(pair_data).hexdigest(),
            "scientific_verdict": None,
        })
        old_page = old_root / f"{building_id}_full_resolution_v5.png"
        if not old_page.is_file():
            raise RuntimeError(f"missing sealed U_target v5 page: {building_id}")
        full_path = full_root / f"{building_id}_C1_C2_C3_C4_full_resolution_v1.png"
        _integrated_page(old_page, pair_path, full_path)
        full_data = full_path.read_bytes()
        full_manifests.append({
            "building_id": building_id,
            "lod2_reference_status": c4_rows[building_id]["lod2_reference_status"],
            "path": full_path.relative_to(task_root).as_posix(),
            "bytes": len(full_data),
            "sha256": hashlib.sha256(full_data).hexdigest(),
            "scientific_verdict": None,
        })
        print(f"rendered {index}/199 {building_id}", flush=True)
    _write_new(task_root / "qualitative/case_sheet_manifest_v1.jsonl", b"".join((json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n").encode() for row in manifests))
    _write_new(task_root / "qualitative/full_resolution_manifest_v1.jsonl", b"".join((json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n").encode() for row in full_manifests))
    lines = [
        "<!doctype html><html lang='ko'><head><meta charset='utf-8'><title>C3-2 vs C4 U_target 199</title>",
        "<style>body{font-family:sans-serif;max-width:1900px;margin:auto}article{border-top:3px solid #222;margin:3rem 0}img{width:100%;height:auto}code{font-size:1.1rem}</style></head><body>",
        "<h1>C3-2 / C4 Existing ALS — U_target 199동 matched gallery</h1>",
        "<p>199동 전체를 표시하며 missing/not-run/failure를 삭제하지 않습니다. C5=NOT_RUN; official PASS_usable=null; scientific_verdict=null.</p>",
    ]
    for row in full_manifests:
        rel = Path(row["path"]).relative_to("qualitative").as_posix()
        lines.append(f"<article data-status='{html.escape(row['lod2_reference_status'])}'><h2><code>{html.escape(row['building_id'])}</code></h2><p>{html.escape(row['lod2_reference_status'])}</p><a href='{html.escape(rel)}'><img loading='lazy' src='{html.escape(rel)}'></a></article>")
    lines.append("</body></html>")
    _write_new(task_root / "qualitative/index.html", "\n".join(lines).encode("utf-8"))
    representatives = config["presentation"]["representative_building_ids"]
    pdf_path = task_root / "reports/C3_2_C4_matched_representative_v1.pdf"
    images = [Image.open(pair_root / f"{building_id}_C3_2_C4_matched_v1.png").convert("RGB") for building_id in representatives]
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    images[0].save(pdf_path, "PDF", save_all=True, append_images=images[1:], resolution=115.0)
    for image in images:
        image.close()
    pdf_data = pdf_path.read_bytes()
    body = {
        "schema": "jointbuildgs.c4_utarget199_qualitative_complete.v1",
        "status": "COMPLETE",
        "case_sheet_count": len(manifests),
        "full_resolution_page_count": len(full_manifests),
        "representative_pdf_page_count": len(representatives),
        "representative_pdf": {
            "path": pdf_path.relative_to(task_root).as_posix(),
            "bytes": len(pdf_data),
            "sha256": hashlib.sha256(pdf_data).hexdigest(),
        },
        "condition_ids": ["C3_2_SEM_DEPTH", CONDITION_ID],
        "canonical_principal_frame": "FOOTPRINT_PCA_SINGLE_SECTION",
        "principal_z_scale": "LOD2_PLUS_45P7M_COMMON_PER_BUILDING",
        "missing_not_run_failure_preserved": True,
        "c5_state": "NOT_RUN",
        "official_PASS_usable": None,
        "scientific_verdict": None,
    }
    _write_new(completed, (json.dumps(body, sort_keys=True, separators=(",", ":")) + "\n").encode())
    return body


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--task-root", type=Path, required=True)
    parser.add_argument("--artifact-root", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(render_all(task_root=args.task_root, artifact_root=args.artifact_root), sort_keys=True))


if __name__ == "__main__":
    main()
