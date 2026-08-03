#!/usr/bin/env python3
"""Render contract Sheets A/B/C for every U_target building."""

from __future__ import annotations

import argparse
from collections import defaultdict
import hashlib
import html
import json
import math
from pathlib import Path
from typing import Any, Mapping

import cv2
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from scripts.evidence_and_attributes.population_analysis import population_aux_v3 as projection
from scripts.p2.utarget199_contract_results_v1.contract import load_config, parse_jsonl
from src.stage3.c3_checkpoint_roofer_adapter_v1 import LOCAL_SHIFT_XYZ, load_c3_checkpoint
from src.visualization.fixed_view_qualitative import (
    BBox,
    PointSet,
    Surface,
    load_cityjsonseq,
    load_las_points,
    load_roofprint,
)


METHODS = ("C1_L_upper", "C2_MVS", "C3_GS_image")
METHOD_TITLES = {
    "C1_L_upper": "C1 current UAS LiDAR",
    "C2_MVS": "C2 current-image MVS",
    "C3_GS_image": "C3 no-external-prior GS",
}


def rows(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def crop_points(points: PointSet, bbox: BBox) -> PointSet:
    if not len(points.xyz):
        return PointSet.empty()
    xyz = points.xyz
    keep = (
        (xyz[:, 0] >= bbox.min_x)
        & (xyz[:, 0] <= bbox.max_x)
        & (xyz[:, 1] >= bbox.min_y)
        & (xyz[:, 1] <= bbox.max_y)
    )
    classification = points.classification[keep] if points.classification is not None else None
    return PointSet(xyz[keep], classification)


def city_file(output: Path) -> Path | None:
    matches = sorted(path for path in output.glob("*") if path.is_file() and path.suffix in (".json", ".jsonl")) if output.is_dir() else []
    return matches[0] if len(matches) == 1 else None


def load_geometry(task_root: Path, unit: Mapping[str, Any] | None) -> dict[str, Any]:
    if not unit:
        return {"points": PointSet.empty(), "surfaces": [], "roofprint": []}
    work = task_root / unit["work_directory"]
    points = load_las_points(work / "input.las")
    city = city_file(task_root / unit["output_directory"])
    surfaces = load_cityjsonseq(city) if city else []
    roofprint = load_roofprint(work / "r_derived.geojson")
    return {"points": points, "surfaces": surfaces, "roofprint": roofprint}


def plot_top_points(ax: Any, points: PointSet, bbox: BBox, *, classes: bool = False, title: str = "") -> None:
    cropped = crop_points(points, bbox)
    ax.set_title(title, fontsize=8)
    if not len(cropped.xyz):
        ax.text(0.5, 0.5, "MISSING", ha="center", va="center", transform=ax.transAxes, color="crimson")
    elif classes and cropped.classification is not None:
        colors = np.where(cropped.classification == 6, "#0072B2", np.where(cropped.classification == 2, "#9A6324", "#888888"))
        ax.scatter(cropped.xyz[:, 0], cropped.xyz[:, 1], c=colors, s=3, linewidths=0)
    else:
        ax.scatter(cropped.xyz[:, 0], cropped.xyz[:, 1], c=cropped.xyz[:, 2], s=3, cmap="viridis", linewidths=0)
    ax.set_xlim(bbox.min_x, bbox.max_x)
    ax.set_ylim(bbox.min_y, bbox.max_y)
    ax.set_aspect("equal")
    ax.tick_params(labelsize=5)


def plot_top_output(ax: Any, surfaces: list[Surface], reference: PointSet, bbox: BBox, *, title: str) -> None:
    ax.set_title(title, fontsize=8)
    ref = crop_points(reference, bbox)
    if len(ref.xyz):
        ax.scatter(ref.xyz[:, 0], ref.xyz[:, 1], c=ref.xyz[:, 2], cmap="viridis", s=5, alpha=0.7, linewidths=0)
    for surface in surfaces:
        if surface.semantic == "RoofSurface":
            ring = surface.xyz
            ax.fill(ring[:, 0], ring[:, 1], facecolor="#D55E0033", edgecolor="#D55E00", linewidth=0.8)
    if not surfaces:
        ax.text(0.5, 0.5, "NO LoD2 OUTPUT", ha="center", va="center", transform=ax.transAxes, color="crimson")
    ax.set_xlim(bbox.min_x, bbox.max_x)
    ax.set_ylim(bbox.min_y, bbox.max_y)
    ax.set_aspect("equal")
    ax.tick_params(labelsize=5)


def plot_oblique(ax: Any, points: PointSet, surfaces: list[Surface], bbox: BBox, *, title: str) -> None:
    ax.set_title(title, fontsize=8)
    cropped = crop_points(points, bbox)
    if len(cropped.xyz):
        stride = max(1, len(cropped.xyz) // 5000)
        xyz = cropped.xyz[::stride]
        ax.scatter(xyz[:, 0], xyz[:, 1], xyz[:, 2], c=xyz[:, 2], cmap="viridis", s=1, alpha=0.45)
    for surface in surfaces:
        ring = surface.xyz
        if len(ring):
            closed = np.vstack((ring, ring[0]))
            ax.plot(closed[:, 0], closed[:, 1], closed[:, 2], color="#D55E00" if surface.semantic == "RoofSurface" else "#777777", linewidth=0.7)
    ax.set_xlim(bbox.min_x, bbox.max_x)
    ax.set_ylim(bbox.min_y, bbox.max_y)
    ax.view_init(elev=28, azim=-55)
    ax.tick_params(labelsize=4)


def plot_section(ax: Any, points: PointSet, surfaces: list[Surface], reference: PointSet, bbox: BBox, *, title: str) -> None:
    ax.set_title(title, fontsize=8)
    major_x = bbox.width >= bbox.height
    center = bbox.center[1 if major_x else 0]
    band = max(min(bbox.width, bbox.height) * 0.12, 0.75)
    cropped = crop_points(points, bbox)
    if len(cropped.xyz):
        keep = np.abs(cropped.xyz[:, 1 if major_x else 0] - center) <= band
        xyz = cropped.xyz[keep]
        if len(xyz):
            ax.scatter(xyz[:, 0 if major_x else 1], xyz[:, 2], s=3, c="#0072B2", alpha=0.55)
    ref = crop_points(reference, bbox)
    if len(ref.xyz):
        keep = np.abs(ref.xyz[:, 1 if major_x else 0] - center) <= band
        xyz = ref.xyz[keep]
        if len(xyz):
            ax.scatter(xyz[:, 0 if major_x else 1], xyz[:, 2], s=6, c="#009E73", marker="x")
    for surface in surfaces:
        ring = surface.xyz
        keep = np.abs(ring[:, 1 if major_x else 0] - center) <= band
        xyz = ring[keep]
        if len(xyz) >= 2:
            order = np.argsort(xyz[:, 0 if major_x else 1])
            ax.plot(xyz[order, 0 if major_x else 1], xyz[order, 2], color="#D55E00", linewidth=0.8)
    ax.tick_params(labelsize=5)
    ax.set_xlabel("Easting" if major_x else "Northing", fontsize=6)
    ax.set_ylabel("Z (m)", fontsize=6)


def draw_roofprint(ax: Any, rings: list[np.ndarray]) -> None:
    for ring in rings:
        ax.plot(ring[:, 0], ring[:, 1], color="#CC79A7", linewidth=1.0, linestyle="--")


def camera_context(artifact_root: Path, config: Mapping[str, Any]) -> tuple[dict[str, str], dict[str, Any], tuple[int, int, np.ndarray], dict[str, Any]]:
    spec = config["inputs"]["rgb_context"]
    best = json.loads((artifact_root / spec["best_view_relative_path"]).read_text(encoding="utf-8"))
    scene_ref = json.loads((artifact_root / spec["scene_reference_relative_path"]).read_text(encoding="utf-8"))
    model = projection.parse_cam_model(artifact_root / spec["cameras_relative_path"])
    cameras = projection.parse_cameras(artifact_root / spec["images_relative_path"], scene_ref)
    return best, {camera.name: camera for camera in cameras}, model, scene_ref


def rgb_crop(
    artifact_root: Path,
    config: Mapping[str, Any],
    best: Mapping[str, str],
    cameras: Mapping[str, Any],
    model: tuple[int, int, np.ndarray],
    scene_ref: Mapping[str, Any],
    building_id: str,
    bbox: BBox,
    z_values: np.ndarray,
) -> tuple[np.ndarray | None, str]:
    name = best.get(building_id, "")
    camera = cameras.get(name)
    if not name or camera is None:
        return None, "NO_FROZEN_BEST_VIEW"
    image_path = artifact_root / config["inputs"]["rgb_context"]["image_directory_relative_path"] / name
    image = cv2.imread(str(image_path), cv2.IMREAD_COLOR)
    if image is None:
        return None, "IMAGE_MISSING"
    width, height, params = model
    finite = z_values[np.isfinite(z_values)]
    if len(finite):
        z0, z1 = float(np.percentile(finite, 5)), float(np.percentile(finite, 95))
    else:
        z0, z1 = 500.0, 600.0
    if z1 - z0 < 2.0:
        z0 -= 2.0
        z1 += 2.0
    corners = np.asarray([
        [x, y, z]
        for z in (z0, z1)
        for x, y in ((bbox.min_x, bbox.min_y), (bbox.max_x, bbox.min_y), (bbox.max_x, bbox.max_y), (bbox.min_x, bbox.max_y))
    ])
    uv, front = projection.project(corners, camera, width, height, params, scene_ref)
    uv = uv[front & np.isfinite(uv).all(axis=1)]
    if not len(uv):
        return None, "BBOX_NOT_PROJECTABLE"
    x0, y0 = np.min(uv, axis=0)
    x1, y1 = np.max(uv, axis=0)
    margin = max(x1 - x0, y1 - y0) * 0.65 + 40.0
    x0, y0 = max(0, int(math.floor(x0 - margin))), max(0, int(math.floor(y0 - margin)))
    x1, y1 = min(image.shape[1], int(math.ceil(x1 + margin))), min(image.shape[0], int(math.ceil(y1 + margin)))
    if x1 <= x0 or y1 <= y0:
        return None, "EMPTY_RGB_CROP"
    return cv2.cvtColor(image[y0:y1, x0:x1], cv2.COLOR_BGR2RGB), name


def gate_text(row: Mapping[str, Any]) -> str:
    metrics = row.get("continuous_metrics") or {}
    value = lambda key: "NA" if metrics.get(key) is None else f"{float(metrics[key]):.2f}"
    gates = " ".join(
        f"{name}={row.get(key)}"
        for name, key in (
            ("G0", "G0_generated"), ("G1", "G1_schema_semantic"), ("G2", "G2_geometry_topology_valid"),
            ("G3*", "G3_candidate"), ("G4*", "G4_candidate"), ("PASS*", "PASS_candidate"),
        )
    )
    return (
        f"{gates}\n"
        f"ref cells={row.get('reference_cell_count')}  MAE-Z={value('height_error_mae_m')}m  "
        f"RMSZ={value('RMSZ_m')}m  P95dist={value('surface_distance_p95_m')}m\n"
        f"association={row.get('association_status')}\n"
        "* diagnostic candidate; official G3/G4/PASS = null"
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--task-root", type=Path, required=True)
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--checkpoint", type=Path, required=True)
    args = parser.parse_args()
    config = load_config()
    prepared = json.loads((args.task_root / "control/prepared_v1.json").read_text(encoding="utf-8"))
    final = json.loads((args.task_root / "control/finalized_v1.json").read_text(encoding="utf-8"))
    units = {row["operation_unit_id"]: row for row in parse_jsonl((args.task_root / prepared["execution_units"]["path"]).read_bytes())}
    result_rows = rows(args.task_root / final["building_method_metrics"]["path"])
    by_building: defaultdict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    for row in result_rows:
        by_building[row["building_id"]][row["method_id"]] = row
    reference_rows = rows(args.task_root / final["reference_cells"]["path"])
    reference_by_building: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in reference_rows:
        reference_by_building[row["stable_id"]].append(row)
    best, cameras, model, scene_ref = camera_context(args.artifact_root, config)
    checkpoint = load_c3_checkpoint(args.checkpoint)
    c3_xyz = checkpoint.means + np.asarray(LOCAL_SHIFT_XYZ, dtype=np.float64)
    c3_labels = np.argmax(checkpoint.sem_logits, axis=1).astype(np.uint8)
    c3_classes = np.where(np.isin(c3_labels, (1, 2)), 6, np.where(c3_labels == 3, 2, 0)).astype(np.uint8)
    c3_native = PointSet(c3_xyz, c3_classes)
    geometry_cache: dict[str, dict[str, Any]] = {}
    output_dir = args.task_root / config["outputs"]["case_sheets_directory"]
    output_dir.mkdir(parents=True, exist_ok=True)
    manifests: list[dict[str, Any]] = []
    for index, building_id in enumerate(sorted(by_building), 1):
        method_rows = by_building[building_id]
        sample = method_rows[METHODS[0]]
        building_bbox = BBox(*(float(sample[name]) for name in ("bbox_min_x", "bbox_min_y", "bbox_max_x", "bbox_max_y")))
        viewport = building_bbox.padded(0.35, 5.0)
        geometries: dict[str, dict[str, Any]] = {}
        z_parts: list[np.ndarray] = []
        for method in METHODS:
            unit_id = method_rows[method].get("operation_unit_id")
            if unit_id and unit_id not in geometry_cache:
                geometry_cache[unit_id] = load_geometry(args.task_root, units[unit_id])
            geometries[method] = geometry_cache.get(unit_id, {"points": PointSet.empty(), "surfaces": [], "roofprint": []})
            cropped = crop_points(geometries[method]["points"], viewport)
            if len(cropped.xyz):
                z_parts.append(cropped.xyz[:, 2])
        refs_raw = reference_by_building[building_id]
        reference = PointSet(
            np.asarray([[float(row["cell_x"]), float(row["cell_y"]), float(row["top_z"])] for row in refs_raw], dtype=np.float64).reshape((-1, 3)),
            None,
        )
        if len(reference.xyz):
            z_parts.append(reference.xyz[:, 2])
        z_values = np.concatenate(z_parts) if z_parts else np.asarray([], dtype=np.float64)
        image, image_note = rgb_crop(args.artifact_root, config, best, cameras, model, scene_ref, building_id, building_bbox, z_values)
        figure = plt.figure(figsize=(18, 24), dpi=105, constrained_layout=True)
        grid = figure.add_gridspec(8, 4, width_ratios=[1.1, 1, 1, 1])
        figure.suptitle(f"{building_id} — contract Sheets A/B/C — U_target census {index}/199", fontsize=14)
        rgb_ax = figure.add_subplot(grid[0:2, 0])
        rgb_ax.set_title(f"Current RGB — {image_note}", fontsize=8)
        if image is None:
            rgb_ax.text(0.5, 0.5, image_note, ha="center", va="center")
        else:
            rgb_ax.imshow(image)
        rgb_ax.axis("off")
        context_ax = figure.add_subplot(grid[2:4, 0])
        context_ax.axis("off")
        context_ax.text(
            0.0, 1.0,
            "Population / input support\n"
            f"U_target: yes (all 199 retained)\n"
            f"original split: {sample.get('original_split')} (now opened)\n"
            f"image views: {sample.get('current_image_view_support')}\n"
            f"MVS cells: {sample.get('mvs_support_cells')}\n"
            f"ALS cells: {sample.get('c4_support_cells')}\n"
            f"LoD1 candidate: {sample.get('c5_prior_available')}\n"
            f"UAS score cells: {len(reference.xyz)}\n"
            f"strict independent ref: {sample.get('strict_e_paired')}\n\n"
            "Sheet A: native/input evidence\n"
            "Sheet B: exact class-2/6 Roofer input + R_derived\n"
            "Sheet C: LoD2 output/reference + metrics/gates\n\n"
            "blue=class 6, brown=class 2, green=UAS score, red=RoofSurface\n"
            "C5 LoD2-derived LoD1 remains diagnostic-only.",
            va="top", fontsize=8,
        )
        ref_ax = figure.add_subplot(grid[4:6, 0])
        plot_top_points(ref_ax, reference, viewport, title="Evaluation UAS roof cells (score-only)")
        ref_ax.add_patch(plt.Rectangle((building_bbox.min_x, building_bbox.min_y), building_bbox.width, building_bbox.height, fill=False, edgecolor="black", linewidth=1.0))
        status_ax = figure.add_subplot(grid[6:8, 0])
        status_ax.axis("off")
        status_ax.text(
            0.0, 1.0,
            "Interpretation\n"
            "- No pre-execution building exclusion.\n"
            "- Missing inputs/references remain explicit.\n"
            "- Shared/multi components fail building-level G0.\n"
            "- G3*/G4*/PASS* are diagnostic candidates.\n"
            "- official PASS_usable and scientific_verdict are null.",
            va="top", fontsize=8,
        )
        for column, method in enumerate(METHODS, 1):
            geometry = geometries[method]
            native = c3_native if method == "C3_GS_image" else geometry["points"]
            ax = figure.add_subplot(grid[0, column])
            plot_top_points(ax, native, viewport, classes=False, title=f"Sheet A native top — {METHOD_TITLES[method]}")
            ax.add_patch(plt.Rectangle((building_bbox.min_x, building_bbox.min_y), building_bbox.width, building_bbox.height, fill=False, edgecolor="black", linewidth=1.0))
            ax = figure.add_subplot(grid[1, column], projection="3d")
            plot_oblique(ax, native, [], viewport, title="Sheet A native oblique")
            ax = figure.add_subplot(grid[2, column])
            plot_top_points(ax, geometry["points"], viewport, classes=True, title="Sheet B exact Roofer input class 2/6")
            draw_roofprint(ax, geometry["roofprint"])
            ax.add_patch(plt.Rectangle((building_bbox.min_x, building_bbox.min_y), building_bbox.width, building_bbox.height, fill=False, edgecolor="black", linewidth=1.0))
            ax = figure.add_subplot(grid[3, column])
            plot_section(ax, geometry["points"], [], PointSet.empty(), viewport, title="Sheet B exact-input principal section")
            ax = figure.add_subplot(grid[4, column])
            plot_top_output(ax, geometry["surfaces"], reference, viewport, title="Sheet C LoD2 top + UAS reference")
            ax.add_patch(plt.Rectangle((building_bbox.min_x, building_bbox.min_y), building_bbox.width, building_bbox.height, fill=False, edgecolor="black", linewidth=1.0))
            ax = figure.add_subplot(grid[5, column], projection="3d")
            plot_oblique(ax, PointSet.empty(), geometry["surfaces"], viewport, title="Sheet C LoD2 common oblique")
            ax = figure.add_subplot(grid[6, column])
            plot_section(ax, PointSet.empty(), geometry["surfaces"], reference, viewport, title="Sheet C LoD2/reference section")
            ax = figure.add_subplot(grid[7, column])
            ax.axis("off")
            ax.text(0.0, 1.0, gate_text(method_rows[method]), va="top", fontsize=7)
        path = output_dir / f"{building_id}_Sheet_ABC_v1.png"
        figure.savefig(path)
        plt.close(figure)
        data = path.read_bytes()
        manifests.append({
            "building_id": building_id,
            "path": path.relative_to(args.task_root).as_posix(),
            "bytes": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
            "current_rgb": image_note,
            "criterion_version": sample["criterion_version"],
            "scientific_verdict": None,
        })
        print(f"rendered {index}/199 {building_id}", flush=True)
    manifest_path = args.task_root / "qualitative/case_sheet_manifest_v1.jsonl"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_bytes(b"".join((json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8") for row in manifests))
    summary = {row["building_id"]: row for row in manifests}
    lines = [
        "<!doctype html><html lang='ko'><head><meta charset='utf-8'><title>P2 199동 결과</title>",
        "<style>body{font-family:sans-serif;margin:24px}table{border-collapse:collapse;width:100%}th,td{border:1px solid #ccc;padding:6px}img{width:360px}code{font-size:12px}</style></head><body>",
        "<h1>P2 C1/C2/C3 — U_target 199동 단계별 결과</h1>",
        "<p>모든 199동을 남겼습니다. G3/G4/PASS의 별표 값은 진단 후보이며 공식 판정과 scientific_verdict는 null입니다.</p>",
        "<table><thead><tr><th>건물</th><th>입력/평가 상태</th><th>C1/C2/C3 후보 PASS</th><th>Sheet A/B/C</th></tr></thead><tbody>",
    ]
    for building_id in sorted(by_building):
        sample = by_building[building_id][METHODS[0]]
        passes = " / ".join(f"{method.split('_')[0]}={by_building[building_id][method].get('PASS_candidate')}" for method in METHODS)
        status = f"images={sample.get('current_image_view_support')}, MVS={sample.get('mvs_support_cells')}, ALS={sample.get('c4_support_cells')}, UAS score={sample.get('reference_cell_count')}"
        rel = Path(summary[building_id]["path"]).relative_to("qualitative").as_posix()
        lines.append(
            f"<tr><td><code>{html.escape(building_id)}</code></td><td>{html.escape(status)}</td><td>{html.escape(passes)}</td>"
            f"<td><a href='{html.escape(rel)}'><img loading='lazy' src='{html.escape(rel)}'></a></td></tr>"
        )
    lines.append("</tbody></table></body></html>")
    gallery = args.task_root / config["outputs"]["gallery"]
    gallery.write_text("\n".join(lines), encoding="utf-8")
    control = {
        "schema": "jointbuildgs.p2_utarget199_qualitative_complete.v1",
        "status": "COMPLETE",
        "case_sheet_count": len(manifests),
        "case_sheet_manifest": manifest_path.relative_to(args.task_root).as_posix(),
        "gallery": gallery.relative_to(args.task_root).as_posix(),
        "scientific_verdict": None,
    }
    (args.task_root / "control/qualitative_complete_v1.json").write_bytes(
        (json.dumps(control, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
    )
    print(json.dumps(control, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
