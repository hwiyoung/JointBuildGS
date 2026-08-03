#!/usr/bin/env python3
"""Render three reuse-only DEC-P1-016 qualitative/quantitative sample matrices."""

from __future__ import annotations

import argparse
from collections import Counter
import csv
from dataclasses import asdict, dataclass
import hashlib
import html
import json
import math
from pathlib import Path
import re
import subprocess
from typing import Any, Iterable, Mapping, Sequence

import cv2
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from scripts.evidence_and_attributes.population_analysis import population_aux_v3 as projection
from src.visualization.fixed_view_qualitative import (
    BBox,
    PointSet,
    Surface,
    load_cityjsonseq,
    load_las_points,
    load_roofprint,
)


METHODS_SOURCE = ("C1_L_upper", "C2_MVS", "C3_GS_image")
METHODS_ALL = (*METHODS_SOURCE, "C4_GS_lidar_prior", "C5_GS_lod1_prior")
METHOD_TITLES = {
    "C1_L_upper": "C1 — Current UAS LiDAR",
    "C2_MVS": "C2 — Current-image MVS",
    "C3_GS_image": "C3 — Image-only GS",
    "C4_GS_lidar_prior": "C4 — Image + existing ALS GS",
    "C5_GS_lod1_prior": "C5 — Image + independent LoD1 GS",
}
STAGE_ROWS = {
    "C1_L_upper": (("LIDAR_INPUT", "input"), ("LIDAR_ROOFER_OUTPUT", "output")),
    "C2_MVS": (("MVS_INPUT", "input"), ("MVS_ROOFER_OUTPUT", "output")),
    "C3_GS_image": (
        ("GS_RENDER_RGB_SEMANTIC", "missing_render"),
        ("GS_SURFACE_SEMANTIC", "input"),
        ("GS_ROOFER_OUTPUT", "output"),
    ),
    "C4_GS_lidar_prior": (
        ("GS_RENDER_RGB_SEMANTIC", "not_run"),
        ("GS_SURFACE_SEMANTIC", "not_run"),
        ("GS_ROOFER_OUTPUT", "not_run"),
    ),
    "C5_GS_lod1_prior": (
        ("GS_RENDER_RGB_SEMANTIC", "not_run"),
        ("GS_SURFACE_SEMANTIC", "not_run"),
        ("GS_ROOFER_OUTPUT", "not_run"),
    ),
}
VIEW_IDS = ("TOP", "OBLIQUE_1", "OBLIQUE_2", "PRINCIPAL_SECTION")


def expected_panel_ids(
    building_ids: Sequence[str],
    methods: Sequence[str] = METHODS_ALL,
) -> set[str]:
    expected: set[str] = set()
    for building_id in building_ids:
        expected.update(
            f"{building_id}__RAW__RAW_CURRENT_IMAGES_WITH_ROOF_PROJECTION__RAW_{index}"
            for index in range(1, 5)
        )
        for method in methods:
            stages = STAGE_ROWS[method]
            expected.update(
                f"{building_id}__{method}__{stage_id}__{view_id}"
                for stage_id, _ in stages
                for view_id in VIEW_IDS
            )
    return expected


def validate_sealed_operation_units(
    by_building: Mapping[str, Mapping[str, Mapping[str, Any]]],
    building_ids: Sequence[str],
    units: Mapping[str, Mapping[str, Any]],
    required_methods: Sequence[str] = METHODS_SOURCE,
) -> None:
    for building_id in building_ids:
        for method in required_methods:
            unit_id = by_building[building_id][method].get("operation_unit_id")
            if not unit_id or str(unit_id) not in units:
                raise RuntimeError(
                    f"sealed operation unit missing before output creation: {building_id} {method} {unit_id}"
                )


def canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def write_new(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(data)


def contained_path(root: Path, relative: str | Path, *, label: str) -> Path:
    root = root.resolve()
    candidate = (root / relative).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise RuntimeError(f"{label} escapes allowed root: {candidate}") from exc
    return candidate


def git_blob_sha256(repo_root: Path, commit: str, relative_path: str) -> str:
    if re.fullmatch(r"[0-9a-f]{40}", commit) is None:
        raise RuntimeError(f"invalid exact Git commit: {commit}")
    relative = Path(relative_path)
    if relative.is_absolute() or ".." in relative.parts:
        raise RuntimeError(f"invalid Git blob path: {relative_path}")
    result = subprocess.run(
        ["git", "-c", f"safe.directory={repo_root.resolve()}", "show", f"{commit}:{relative.as_posix()}"],
        cwd=repo_root,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Git blob unavailable: {commit}:{relative.as_posix()}")
    return sha256_bytes(result.stdout)


def verify_git_binding(repo_root: Path, commit: str, relative_path: str, expected_sha256: str) -> None:
    observed = git_blob_sha256(repo_root, commit, relative_path)
    if observed != expected_sha256:
        raise RuntimeError(f"Git blob SHA mismatch: {commit}:{relative_path}")


class DigestCache:
    def __init__(self) -> None:
        self._cache: dict[Path, dict[str, Any]] = {}

    def record(self, path: Path, *, root: Path, role: str) -> dict[str, Any]:
        path = path.resolve()
        if path not in self._cache:
            digest = hashlib.sha256()
            total = 0
            with path.open("rb") as stream:
                for block in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(block)
                    total += len(block)
            self._cache[path] = {"bytes": total, "sha256": digest.hexdigest()}
        return {
            "path": path.relative_to(root.resolve()).as_posix(),
            "role": role,
            **self._cache[path],
        }


def read_verified(path: Path, expected: Mapping[str, Any]) -> tuple[bytes, dict[str, Any]]:
    data = path.read_bytes()
    observed = {"path": str(expected["path"]), "bytes": len(data), "sha256": sha256_bytes(data)}
    if observed["bytes"] != int(expected["bytes"]) or observed["sha256"] != str(expected["sha256"]):
        raise RuntimeError(f"sealed source mismatch: {path}")
    return data, observed


def parse_jsonl(data: bytes) -> list[dict[str, Any]]:
    return [json.loads(line) for line in data.decode("utf-8").splitlines() if line.strip()]


def city_file(output: Path) -> Path | None:
    if not output.is_dir():
        return None
    matches = sorted(path for path in output.rglob("*.city.jsonl") if path.is_file() and not path.is_symlink())
    return matches[0] if len(matches) == 1 else None


@dataclass
class Geometry:
    points: PointSet
    surfaces: list[Surface]
    roofprint: list[np.ndarray]
    sources: list[dict[str, Any]]
    operation_unit_id: str | None


def empty_geometry() -> Geometry:
    return Geometry(PointSet.empty(), [], [], [], None)


def load_geometry(
    task_root: Path,
    unit: Mapping[str, Any] | None,
    *,
    digest: DigestCache,
    artifact_root: Path,
) -> Geometry:
    if not unit:
        return empty_geometry()
    operation_unit_id = str(unit["operation_unit_id"])
    work = contained_path(task_root, str(unit["work_directory"]), label="work directory")
    terminal_path = contained_path(task_root, str(unit["terminal_record"]), label="terminal record")
    terminal = json.loads(terminal_path.read_text(encoding="utf-8"))
    if terminal.get("operation_unit_id") != operation_unit_id or terminal.get("scientific_verdict") is not None:
        raise RuntimeError(f"terminal record binding mismatch: {operation_unit_id}")
    if terminal.get("status") not in {"COMPLETED", "COMPLETED_REUSED_EXACT"}:
        raise RuntimeError(f"non-complete sealed operation: {operation_unit_id}")

    def sealed_record(expected: Mapping[str, Any], *, role: str) -> tuple[Path, dict[str, Any]]:
        path = contained_path(task_root, str(expected["path"]), label=role)
        observed = digest.record(path, root=artifact_root, role=role)
        if observed["bytes"] != int(expected["bytes"]) or observed["sha256"] != str(expected["sha256"]):
            raise RuntimeError(f"sealed method artifact mismatch: {operation_unit_id} {role}")
        return path, observed

    input_path, input_record = sealed_record(terminal["input"], role="sealed_roofer_input")
    roofprint_path, roofprint_record = sealed_record(terminal["r_derived"], role="sealed_derived_roofprint")
    if input_path != (work / "input.las").resolve() or roofprint_path != (work / "r_derived.geojson").resolve():
        raise RuntimeError(f"terminal work-path mismatch: {operation_unit_id}")
    output_records = list(terminal.get("output_records") or [])
    if len(output_records) != 1:
        raise RuntimeError(f"expected one sealed CityJSON output: {operation_unit_id}")
    output_path, output_record = sealed_record(output_records[0], role="sealed_roofer_output")
    output_directory = contained_path(task_root, str(unit["output_directory"]), label="output directory")
    try:
        output_path.relative_to(output_directory)
    except ValueError as exc:
        raise RuntimeError(f"terminal output escaped operation output directory: {operation_unit_id}") from exc
    if not output_path.name.endswith(".city.jsonl"):
        raise RuntimeError(f"unexpected sealed output type: {output_path}")
    terminal_record = digest.record(terminal_path, root=artifact_root, role="sealed_terminal_record")
    sources = [input_record, roofprint_record, output_record, terminal_record]
    return Geometry(
        points=load_las_points(input_path),
        surfaces=load_cityjsonseq(output_path),
        roofprint=load_roofprint(roofprint_path),
        sources=sources,
        operation_unit_id=operation_unit_id,
    )


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
    classes = points.classification[keep] if points.classification is not None else None
    return PointSet(xyz[keep], classes)


def bbox_from_row(row: Mapping[str, Any]) -> BBox:
    return BBox(*(float(row[key]) for key in ("bbox_min_x", "bbox_min_y", "bbox_max_x", "bbox_max_y")))


def reference_for(rows: Sequence[Mapping[str, Any]]) -> PointSet:
    values = np.asarray(
        [[float(row["cell_x"]), float(row["cell_y"]), float(row["top_z"])] for row in rows],
        dtype=np.float64,
    ).reshape((-1, 3))
    return PointSet(values, None)


def circular_distance(left: float, right: float) -> float:
    return abs((left - right + 180.0) % 360.0 - 180.0)


def select_cameras(
    reference: PointSet,
    bbox: BBox,
    cameras: Sequence[Any],
    model: tuple[int, int, np.ndarray],
    scene_ref: Mapping[str, Any],
    count: int,
    minimum_fraction: float,
) -> list[dict[str, Any]]:
    width, height, params = model
    candidates: list[dict[str, Any]] = []
    for camera in cameras:
        uv, front = projection.project(reference.xyz, camera, width, height, params, scene_ref)
        inside = front & np.isfinite(uv).all(axis=1)
        inside &= (uv[:, 0] >= 0) & (uv[:, 0] < width) & (uv[:, 1] >= 0) & (uv[:, 1] < height)
        visible = int(np.count_nonzero(inside))
        if not visible:
            continue
        azimuth = math.degrees(math.atan2(float(camera.center[1]) - bbox.center[1], float(camera.center[0]) - bbox.center[0]))
        candidates.append({"camera": camera, "visible": visible, "uv": uv, "inside": inside, "azimuth": azimuth})
    if len(candidates) < count:
        raise RuntimeError(f"fewer than {count} reference-projectable cameras for bbox {bbox}")
    candidates.sort(key=lambda item: (-int(item["visible"]), str(item["camera"].name)))
    best_visible = int(candidates[0]["visible"])
    pool = [item for item in candidates if int(item["visible"]) >= max(1, math.ceil(best_visible * minimum_fraction))]
    selected = [pool.pop(0)]
    while len(selected) < count and pool:
        pool.sort(
            key=lambda item: (
                -min(circular_distance(float(item["azimuth"]), float(other["azimuth"])) for other in selected),
                -int(item["visible"]),
                str(item["camera"].name),
            )
        )
        selected.append(pool.pop(0))
    if len(selected) < count:
        selected_names = {str(item["camera"].name) for item in selected}
        for item in candidates:
            if str(item["camera"].name) not in selected_names:
                selected.append(item)
                selected_names.add(str(item["camera"].name))
                if len(selected) == count:
                    break
    return selected


def save_rgb_projection(
    output: Path,
    image_path: Path,
    camera_record: Mapping[str, Any],
    margin_ratio: float,
    minimum_margin: int,
) -> dict[str, Any]:
    image = cv2.imread(str(image_path), cv2.IMREAD_COLOR)
    if image is None:
        raise RuntimeError(f"raw image is unreadable: {image_path}")
    uv = np.asarray(camera_record["uv"])[np.asarray(camera_record["inside"])]
    x0, y0 = np.min(uv, axis=0)
    x1, y1 = np.max(uv, axis=0)
    margin = max(float(max(x1 - x0, y1 - y0)) * margin_ratio, float(minimum_margin))
    left = max(0, int(math.floor(x0 - margin)))
    top = max(0, int(math.floor(y0 - margin)))
    right = min(image.shape[1], int(math.ceil(x1 + margin)))
    bottom = min(image.shape[0], int(math.ceil(y1 + margin)))
    if right <= left or bottom <= top:
        raise RuntimeError(f"empty raw-image crop: {image_path}")
    crop = image[top:bottom, left:right].copy()
    local = np.rint(uv - np.asarray([left, top])).astype(np.int32)
    for x, y in local:
        cv2.circle(crop, (int(x), int(y)), 3, (0, 210, 80), -1, lineType=cv2.LINE_AA)
    if len(local) >= 3:
        hull = cv2.convexHull(local.reshape((-1, 1, 2)))
        cv2.polylines(crop, [hull], True, (80, 255, 120), 2, lineType=cv2.LINE_AA)
    label = f"roof reference projected — {camera_record['visible']} cells"
    cv2.putText(crop, label, (12, 26), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 0, 0), 4, cv2.LINE_AA)
    cv2.putText(crop, label, (12, 26), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (80, 255, 120), 1, cv2.LINE_AA)
    ok, encoded = cv2.imencode(".png", crop)
    if not ok:
        raise RuntimeError(f"PNG encode failed: {output}")
    write_new(output, encoded.tobytes())
    return {
        "crop_xyxy": [left, top, right, bottom],
        "projected_visible_count": int(camera_record["visible"]),
        "projected_clipped_count": int(len(camera_record["inside"]) - int(camera_record["visible"])),
        "camera_name": str(camera_record["camera"].name),
        "camera_azimuth_deg": float(camera_record["azimuth"]),
    }


def z_limits(points: Iterable[PointSet], surfaces: Iterable[Surface]) -> tuple[float, float]:
    values = [point.xyz[:, 2] for point in points if len(point.xyz)]
    values.extend(surface.xyz[:, 2] for surface in surfaces if len(surface.xyz))
    if not values:
        return (0.0, 1.0)
    merged = np.concatenate(values)
    low, high = float(np.min(merged)), float(np.max(merged))
    pad = max((high - low) * 0.08, 1.0)
    return (low - pad, high + pad)


def draw_reference_top(ax: Any, reference: PointSet) -> int:
    if not len(reference.xyz):
        return 0
    ax.scatter(reference.xyz[:, 0], reference.xyz[:, 1], s=9, facecolors="none", edgecolors="#00a65a", linewidths=0.7, zorder=10)
    return int(len(reference.xyz))


def draw_reference_3d(ax: Any, reference: PointSet) -> int:
    if not len(reference.xyz):
        return 0
    ax.scatter(reference.xyz[:, 0], reference.xyz[:, 1], reference.xyz[:, 2], s=7, c="#00c66a", depthshade=False)
    return int(len(reference.xyz))


def draw_points(ax: Any, points: PointSet, view: str) -> None:
    if not len(points.xyz):
        return
    stride = max(1, len(points.xyz) // 12000)
    xyz = points.xyz[::stride]
    classes = points.classification[::stride] if points.classification is not None else None
    if classes is None:
        colors: Any = xyz[:, 2]
        cmap = "viridis"
    else:
        colors = np.where(classes == 6, "#1f77b4", np.where(classes == 2, "#8c6d31", "#8c8c8c"))
        cmap = None
    if view == "TOP":
        ax.scatter(xyz[:, 0], xyz[:, 1], c=colors, cmap=cmap, s=2, linewidths=0, rasterized=True)
    else:
        ax.scatter(xyz[:, 0], xyz[:, 1], xyz[:, 2], c=colors, cmap=cmap, s=1.5, linewidths=0, depthshade=False, rasterized=True)


def draw_surfaces(ax: Any, surfaces: Sequence[Surface], view: str) -> None:
    for surface in surfaces:
        if not len(surface.xyz):
            continue
        ring = surface.xyz
        closed = np.vstack((ring, ring[0]))
        color = "#d1495b" if surface.semantic == "RoofSurface" else "#777777"
        if view == "TOP":
            if surface.semantic == "RoofSurface":
                ax.fill(ring[:, 0], ring[:, 1], facecolor="#d1495b33", edgecolor=color, linewidth=0.9)
            else:
                ax.plot(closed[:, 0], closed[:, 1], color=color, linewidth=0.55)
        else:
            ax.plot(closed[:, 0], closed[:, 1], closed[:, 2], color=color, linewidth=0.8)


def draw_context_inset(ax: Any, geometry: Geometry, bbox: BBox, mode: str) -> None:
    inset = ax.inset_axes([0.66, 0.67, 0.31, 0.29])
    if mode == "input" and len(geometry.points.xyz):
        stride = max(1, len(geometry.points.xyz) // 2500)
        xyz = geometry.points.xyz[::stride]
        inset.scatter(xyz[:, 0], xyz[:, 1], s=0.6, c="#888888", linewidths=0)
    elif mode == "output":
        for surface in geometry.surfaces:
            if surface.semantic == "RoofSurface" and len(surface.xyz):
                closed = np.vstack((surface.xyz, surface.xyz[0]))
                inset.plot(closed[:, 0], closed[:, 1], color="#d1495b", linewidth=0.45)
    inset.add_patch(plt.Rectangle((bbox.min_x, bbox.min_y), bbox.width, bbox.height, fill=False, edgecolor="#111111", linewidth=1.0))
    inset.set_title("full component context", fontsize=5)
    inset.set_aspect("equal")
    inset.set_xticks([])
    inset.set_yticks([])


def screen_text(ax: Any, x: float, y: float, value: str, **kwargs: Any) -> Any:
    """Draw axis-relative text on either 2D or 3D Matplotlib axes."""
    if hasattr(ax, "text2D"):
        return ax.text2D(x, y, value, transform=ax.transAxes, **kwargs)
    return ax.text(x, y, value, transform=ax.transAxes, **kwargs)


def section_data(points: np.ndarray, bbox: BBox, half_band: float) -> tuple[np.ndarray, np.ndarray, str]:
    if bbox.width >= bbox.height:
        keep = np.abs(points[:, 1] - bbox.center[1]) <= half_band
        return points[keep, 0], points[keep, 2], "Easting"
    keep = np.abs(points[:, 0] - bbox.center[0]) <= half_band
    return points[keep, 1], points[keep, 2], "Northing"


def render_spatial_panel(
    output: Path,
    *,
    view: str,
    bbox: BBox,
    reference: PointSet,
    geometry: Geometry,
    mode: str,
    status: str | None,
    self_reference: bool,
    view_config: Mapping[str, Any],
) -> dict[str, Any]:
    viewport = bbox.padded(float(view_config["viewport_margin_ratio"]), float(view_config["viewport_minimum_margin_m"]))
    points = crop_points(geometry.points, viewport) if mode == "input" else PointSet.empty()
    ref = crop_points(reference, viewport)
    surfaces = geometry.surfaces if mode == "output" else []
    limits_z = z_limits((points, ref), surfaces)
    figure = plt.figure(figsize=(4.8, 3.6), dpi=120)
    if view in {"OBLIQUE_1", "OBLIQUE_2"}:
        ax = figure.add_subplot(111, projection="3d", proj_type="ortho")
        draw_points(ax, points, view)
        draw_surfaces(ax, surfaces, view)
        visible = draw_reference_3d(ax, ref)
        settings = view_config[view.lower()]
        ax.view_init(elev=float(settings["elevation_deg"]), azim=float(settings["azimuth_deg"]), roll=0)
        ax.set(xlim=(viewport.min_x, viewport.max_x), ylim=(viewport.min_y, viewport.max_y), zlim=limits_z)
        ax.set_box_aspect((viewport.width, viewport.height, max(limits_z[1] - limits_z[0], 1.0)))
        ax.set_xlabel("E", fontsize=6)
        ax.set_ylabel("N", fontsize=6)
        ax.set_zlabel("Z", fontsize=6)
    elif view == "PRINCIPAL_SECTION":
        ax = figure.add_subplot(111)
        half_band = max(min(bbox.width, bbox.height) * float(view_config["section_band_ratio"]), float(view_config["section_minimum_half_band_m"]))
        axis_label = "Easting" if bbox.width >= bbox.height else "Northing"
        if len(points.xyz):
            along, height, axis_label = section_data(points.xyz, bbox, half_band)
            ax.scatter(along, height, s=2, c="#1f77b4", linewidths=0)
        if len(ref.xyz):
            along, height, _ = section_data(ref.xyz, bbox, half_band)
            ax.scatter(along, height, s=12, facecolors="none", edgecolors="#00a65a", linewidths=0.8)
            visible = int(len(along))
        else:
            visible = 0
        for surface in surfaces:
            along, height, _ = section_data(surface.xyz, bbox, half_band)
            if len(along) >= 2:
                order = np.argsort(along)
                ax.plot(along[order], height[order], color="#d1495b", linewidth=0.8)
        ax.set_xlabel(axis_label)
        ax.set_ylabel("Z (m)")
        if bbox.width >= bbox.height:
            ax.set_xlim(viewport.min_x, viewport.max_x)
        else:
            ax.set_xlim(viewport.min_y, viewport.max_y)
        ax.set_ylim(limits_z)
        ax.set_title(f"fixed section ±{half_band:.2f}m", fontsize=8)
    else:
        ax = figure.add_subplot(111)
        draw_points(ax, points, view)
        draw_surfaces(ax, surfaces, view)
        visible = draw_reference_top(ax, ref)
        ax.add_patch(plt.Rectangle((bbox.min_x, bbox.min_y), bbox.width, bbox.height, fill=False, edgecolor="#111111", linewidth=1.0))
        ax.set(xlim=(viewport.min_x, viewport.max_x), ylim=(viewport.min_y, viewport.max_y), aspect="equal")
        ax.set_xlabel("Easting")
        ax.set_ylabel("Northing")
        if mode in {"input", "output"}:
            draw_context_inset(ax, geometry, bbox, mode)
    if status:
        screen_text(ax, 0.5, 0.5, status, ha="center", va="center", color="#b22222", fontsize=9, bbox={"facecolor": "white", "alpha": 0.88, "edgecolor": "#b22222"})
    if self_reference:
        screen_text(
            ax,
            0.5,
            0.98,
            "C1 METRIC = SELF-REFERENCE; GREEN OVERLAY = INDEPENDENT UAS",
            ha="center",
            va="top",
            color="#b22222",
            fontsize=6.2,
            bbox={"facecolor": "white", "alpha": 0.85, "edgecolor": "none"},
        )
    screen_text(ax, 0.01, 0.01, "green = roof evaluation reference", fontsize=6, color="#007c42", bbox={"facecolor": "white", "alpha": 0.78, "edgecolor": "none"})
    figure.tight_layout()
    buffer_path = output
    buffer_path.parent.mkdir(parents=True, exist_ok=True)
    if buffer_path.exists():
        raise RuntimeError(f"refusing to overwrite panel: {buffer_path}")
    figure.savefig(buffer_path, metadata={"Software": "JointBuildGS DEC-P1-016 sample renderer"})
    plt.close(figure)
    return {
        "projected_visible_count": visible,
        "projected_occluded_count": 0,
        "projected_clipped_count": int(len(reference.xyz) - visible),
    }


def metric_value(row: Mapping[str, Any], name: str) -> Any:
    if name in row:
        return row.get(name)
    return (row.get("continuous_metrics") or {}).get(name)


def metric_card(method: str, row: Mapping[str, Any] | None, input_count: int | None) -> str:
    if row is None:
        return "<strong>NOT_RUN</strong><br>정량값: null"
    def fmt(name: str, digits: int = 2) -> str:
        value = metric_value(row, name)
        return "null" if value is None else f"{float(value):.{digits}f}"
    role = (
        "METRIC: SELF_REFERENCE_DIAGNOSTIC_ONLY / GREEN OVERLAY: STRICT_INDEPENDENT_UAS"
        if method == "C1_L_upper"
        else "METRIC + GREEN OVERLAY: STRICT_INDEPENDENT_UAS_REFERENCE"
    )
    association = html.escape(str(row.get("association_status")))
    meaning = "건물별 1:1 출력" if row.get("one_to_one_building_component") else "shared/multi 출력 — 건물 단위 gate 실패"
    return (
        f"<strong>{html.escape(role)}</strong><br>"
        f"association: <b>{association}</b><br>{html.escape(meaning)}<br>"
        f"display input points: {input_count if input_count is not None else 'null'}<br>"
        f"reference cells: {row.get('reference_cell_count')}<br>"
        f"G0/G1/G2: {row.get('G0_generated')}/{row.get('G1_schema_semantic')}/{row.get('G2_geometry_topology_valid')}<br>"
        f"height MAE: {fmt('height_error_mae_m')} m<br>RMSZ: {fmt('RMSZ_m')} m<br>"
        f"surface RMSE/P95: {fmt('surface_distance_rmse_m')}/{fmt('surface_distance_p95_m')} m<br>"
        f"G3*/G4*: {row.get('G3_candidate')}/{row.get('G4_candidate')}<br>"
        "official G3/G4/PASS: <b>null</b>"
    )


def summarize_reason(row: Mapping[str, Any]) -> str:
    if not row.get("one_to_one_building_component"):
        return f"{row.get('association_status')}: 한 건물의 독립 출력이 아니므로 building-level G0–G2 false"
    if not row.get("G2_geometry_topology_valid"):
        return "1:1 output이지만 G2 geometry/topology 실패"
    return "G0–G2 통과; G3/G4/PASS는 criterion 미동결로 official null"


class Recorder:
    def __init__(
        self,
        output_root: Path,
        artifact_root: Path,
        script_path: Path,
        config_path: Path,
        reference_sha: str,
        config: Mapping[str, Any],
        offered_commit: str,
    ) -> None:
        self.output_root = output_root
        self.artifact_root = artifact_root
        self.digest = DigestCache()
        self.script_record = self.digest.record(script_path, root=script_path.parents[3], role="renderer_implementation")
        self.config_record = self.digest.record(config_path, root=config_path.parents[3], role="renderer_config")
        self.reference_sha = reference_sha
        self.config = config
        self.offered_commit = offered_commit
        self.panels: list[dict[str, Any]] = []
        self.metrics: list[dict[str, Any]] = []

    def panel(
        self,
        *,
        panel_id: str,
        building_id: str,
        method_id: str,
        stage_id: str,
        view_id: str,
        path: Path,
        sources: Sequence[dict[str, Any]],
        overlay: Mapping[str, Any],
        view_spec: Mapping[str, Any],
        run_id: str,
        geometry_independence_class: str,
        structure_independence_class: str,
        method_metric_reference_class: str,
        status: str,
        content_status: str,
        support_hash: str,
        reference_subset_sha: str,
    ) -> dict[str, Any]:
        panel_data = path.read_bytes()
        source_manifest = [*sources, self.script_record, self.config_record]
        source_manifest_sha = sha256_bytes(canonical_bytes(source_manifest))
        panel_sha = sha256_bytes(panel_data)
        view_sha = sha256_bytes(canonical_bytes(view_spec))
        receipt_payload = {
            "schema": "jointbuildgs.p2.roof_projection_receipt.v1",
            "panel_id": panel_id,
            "run_id": run_id,
            "panel_artifact_sha256": panel_sha,
            "reference_subset_sha256": reference_subset_sha,
            "geometry_reference_version": self.config["reference_binding"]["geometry_reference_version"],
            "structure_reference_version": self.config["reference_binding"]["structure_reference_version"],
            "geometry_reference_independence_class": geometry_independence_class,
            "structure_reference_independence_class": structure_independence_class,
            "method_metric_reference_class": method_metric_reference_class,
            "view_spec_hash": view_sha,
            "overlay_status": status,
            "content_status": content_status,
            **overlay,
        }
        receipt_path = self.output_root / "manifests/projection_receipts" / f"{panel_id}.json"
        receipt_bytes = canonical_bytes(receipt_payload)
        write_new(receipt_path, receipt_bytes)
        record = {
            "schema": "jointbuildgs.p2.comparison_matrix_panel.v1",
            "matrix_id": f"MATRIX_{building_id}",
            "panel_id": panel_id,
            "building_id": building_id,
            "method_id": method_id,
            "run_id": run_id,
            "stage_id": stage_id,
            "view_id": view_id,
            "panel_path": path.relative_to(self.output_root).as_posix(),
            "panel_bytes": len(panel_data),
            "panel_artifact_sha256": panel_sha,
            "ordered_source_artifact_manifest_sha256": source_manifest_sha,
            "sources": source_manifest,
            "renderer_implementation_hash": self.script_record["sha256"],
            "renderer_config_hash": self.config_record["sha256"],
            "geometry_reference_artifact_sha256": reference_subset_sha,
            "structure_reference_artifact_sha256": reference_subset_sha,
            "geometry_reference_version": self.config["reference_binding"]["geometry_reference_version"],
            "structure_reference_version": self.config["reference_binding"]["structure_reference_version"],
            "geometry_reference_independence_class": geometry_independence_class,
            "structure_reference_independence_class": structure_independence_class,
            "method_metric_reference_class": method_metric_reference_class,
            "shared_reference_artifact_reason": self.config["reference_binding"]["shared_reference_artifact_reason"],
            "reference_source_artifact_sha256": self.reference_sha,
            "criterion_version": self.config["criterion_version"],
            "view_spec_hash": view_sha,
            "evaluation_support_hash": support_hash,
            "projection_receipt_path": receipt_path.relative_to(self.output_root).as_posix(),
            "projection_receipt_sha256": sha256_bytes(receipt_bytes),
            "overlay_status": status,
            "content_status": content_status,
            **overlay,
        }
        self.panels.append(record)
        return record

    def metric(
        self,
        *,
        metric_id: str,
        panel: Mapping[str, Any],
        value: Any,
        unit: str,
        reference_role: str,
        validity: str,
        source_sha: str,
        evaluator: str,
    ) -> None:
        if evaluator == "SOURCE_SEALED":
            source_evaluator = self.config["source_evaluator"]
            implementation_hash = source_evaluator["implementation_sha256"]
            evaluator_config_hash = source_evaluator["config_sha256"]
            evaluator_commit = source_evaluator["source_git_commit"]
        elif evaluator == "DISPLAY_RENDERER":
            implementation_hash = self.script_record["sha256"]
            evaluator_config_hash = self.config_record["sha256"]
            evaluator_commit = self.offered_commit
        else:
            raise RuntimeError(f"unknown evaluator binding: {evaluator}")
        self.metrics.append({
            "schema": "jointbuildgs.p2.comparison_matrix_metric_binding.v1",
            "metric_id": metric_id,
            "panel_id": panel["panel_id"],
            "building_id": panel["building_id"],
            "method_id": panel["method_id"],
            "run_id": panel["run_id"],
            "value": value,
            "unit": unit,
            "validity": validity,
            "reference_role": reference_role,
            "metric_source_artifact_sha256": source_sha,
            "evaluator_implementation_hash": implementation_hash,
            "evaluator_config_hash": evaluator_config_hash,
            "evaluator_source_commit": evaluator_commit,
            "evaluator_binding_hash": sha256_bytes(canonical_bytes({
                "metric_id": metric_id,
                "metric_source_artifact_sha256": source_sha,
                "criterion_version": self.config["criterion_version"],
                "validity": validity,
                "evaluator_implementation_hash": implementation_hash,
                "evaluator_config_hash": evaluator_config_hash,
            })),
            "panel_artifact_sha256": panel["panel_artifact_sha256"],
            "ordered_source_artifact_manifest_sha256": panel["ordered_source_artifact_manifest_sha256"],
            "geometry_reference_artifact_sha256": panel["geometry_reference_artifact_sha256"],
            "structure_reference_artifact_sha256": panel["structure_reference_artifact_sha256"],
            "geometry_reference_version": panel["geometry_reference_version"],
            "structure_reference_version": panel["structure_reference_version"],
            "geometry_reference_independence_class": panel["geometry_reference_independence_class"],
            "structure_reference_independence_class": panel["structure_reference_independence_class"],
            "evaluation_support_hash": panel["evaluation_support_hash"],
        })


def case_html(
    building_id: str,
    selection: Mapping[str, Any],
    panel_map: Mapping[str, Mapping[str, Any]],
    metric_cards: Mapping[str, str],
    camera_records: Sequence[Mapping[str, Any]],
    methods: Sequence[str],
) -> str:
    diagnostic_note = (
        "이 페이지는 요청 순서에 따른 C1/C2-only 개발 기술 진단입니다. "
        "C3–C5는 읽거나 표시하지 않았습니다. official G3/G4/PASS와 scientific_verdict는 null입니다."
        if tuple(methods) == ("C1_L_upper", "C2_MVS")
        else "현재 sealed Stage 3는 C1–C3의 건물별 분리가 대부분 실패했습니다. 따라서 이 페이지는 성능 결론이 아니라 실패 위치를 확인하는 기술 진단입니다. 별표 gate는 후보값이며 official G3/G4/PASS와 scientific_verdict는 null입니다."
    )
    lines = [
        "<!doctype html><html lang='ko'><head><meta charset='utf-8'>",
        f"<title>{html.escape(building_id)} 정성·정량 비교</title>",
        "<style>body{font-family:Arial,'Malgun Gothic',sans-serif;margin:20px;background:#f5f6f8;color:#20242a}"
        "h1{margin-bottom:4px}.note{background:#fff7d6;border-left:5px solid #d49b00;padding:10px;margin:12px 0}"
        "table{border-collapse:collapse;width:100%;background:white}th,td{border:1px solid #ccd2d8;padding:6px;vertical-align:top}"
        "th.stage{width:190px;background:#eaf0f5;text-align:left}th.view{background:#273746;color:white}"
        "td.panel{width:19%}td.metrics{width:250px;background:#f8fafb;font-size:13px;line-height:1.45}"
        "img{width:100%;height:auto;display:block}.block th.stage{border-top:4px solid #576574}code{font-size:12px}</style></head><body>",
        f"<h1>{html.escape(building_id)} — {html.escape(str(selection['size_bin']))} sample</h1>",
        f"<p>group={html.escape(str(selection['candidate_group_id']))}, bbox area={selection['bbox_area_m2']} m². 녹색은 모든 panel에 투영된 roof evaluation reference입니다.</p>",
        f"<div class='note'>{diagnostic_note}</div>",
        "<table><thead><tr><th class='stage'>입력/단계</th><th class='view'>TOP / RAW 1</th><th class='view'>OBLIQUE 1 / RAW 2</th><th class='view'>OBLIQUE 2 / RAW 3</th><th class='view'>SECTION / RAW 4</th><th class='view'>같은 결과의 정량값과 의미</th></tr></thead><tbody>",
    ]
    lines.append("<tr class='block'><th class='stage'>지붕이 투영된 current raw images</th>")
    for index, _ in enumerate(camera_records, 1):
        panel = panel_map[f"{building_id}__RAW__RAW_CURRENT_IMAGES_WITH_ROOF_PROJECTION__RAW_{index}"]
        lines.append(f"<td class='panel'><img src='{html.escape(panel['panel_path'].split(building_id + '/')[1])}'><code>{html.escape(str(camera_records[index-1]['camera'].name))}</code></td>")
    lines.append(f"<td class='metrics'>camera count=4<br>selection=roof coverage + angular diversity<br>reference=STRICT_INDEPENDENT_UAS<br>method outcome 사용 안 함</td></tr>")
    for method in methods:
        stages = STAGE_ROWS[method]
        for stage_index, (stage_id, _) in enumerate(stages):
            row_class = " class='block'" if stage_index == 0 else ""
            label = f"{METHOD_TITLES[method]}<br><code>{stage_id}</code>" if stage_index == 0 else f"<code>{stage_id}</code>"
            lines.append(f"<tr{row_class}><th class='stage'>{label}</th>")
            for view_id in VIEW_IDS:
                panel = panel_map[f"{building_id}__{method}__{stage_id}__{view_id}"]
                relative = panel["panel_path"].split(building_id + "/")[1]
                lines.append(f"<td class='panel'><img src='{html.escape(relative)}'><code>{view_id}</code></td>")
            if stage_index == 0:
                lines.append(f"<td class='metrics' rowspan='{len(stages)}'>{metric_cards[method]}</td>")
            lines.append("</tr>")
    lines.append("</tbody></table><p><a href='../index.html'>sample index로 돌아가기</a></p></body></html>")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--config", type=Path, default=Path("configs/p2/representative_comparison_matrix_sample_v1/render_v1.json"))
    parser.add_argument("--offered-commit", required=True)
    args = parser.parse_args()
    artifact_root = args.artifact_root.resolve()
    config_path = args.config.resolve()
    config = json.loads(config_path.read_text(encoding="utf-8"))
    display_methods = tuple(str(method) for method in config["methods"])
    if not display_methods or len(set(display_methods)) != len(display_methods):
        raise RuntimeError("config methods must be a non-empty unique ordered list")
    if any(method not in METHODS_ALL for method in display_methods):
        raise RuntimeError(f"unsupported display methods: {display_methods}")
    source_methods = tuple(method for method in display_methods if method in METHODS_SOURCE)
    if not source_methods:
        raise RuntimeError("at least one sealed source method is required")
    offered_commit = str(args.offered_commit)
    repo_root = Path(__file__).resolve().parents[3]
    if re.fullmatch(r"[0-9a-f]{40}", offered_commit) is None:
        raise RuntimeError("--offered-commit must be an exact 40-character lowercase SHA")
    ancestor = subprocess.run(
        ["git", "-c", f"safe.directory={repo_root}", "merge-base", "--is-ancestor", offered_commit, "HEAD"],
        cwd=repo_root,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if ancestor.returncode != 0:
        raise RuntimeError(f"offered commit is not an ancestor of execution HEAD: {offered_commit}")
    script_path = Path(__file__).resolve()
    script_relative = script_path.relative_to(repo_root).as_posix()
    config_relative = config_path.relative_to(repo_root).as_posix()
    verify_git_binding(repo_root, offered_commit, script_relative, sha256_bytes(script_path.read_bytes()))
    verify_git_binding(repo_root, offered_commit, config_relative, sha256_bytes(config_path.read_bytes()))
    source_evaluator = config["source_evaluator"]
    verify_git_binding(
        repo_root,
        str(source_evaluator["source_git_commit"]),
        str(source_evaluator["implementation_path"]),
        str(source_evaluator["implementation_sha256"]),
    )
    verify_git_binding(
        repo_root,
        str(source_evaluator["source_git_commit"]),
        str(source_evaluator["config_path"]),
        str(source_evaluator["config_sha256"]),
    )
    source_root = contained_path(artifact_root, str(config["source_task_relative_root"]), label="source task root")
    final_output_root = contained_path(artifact_root, str(config["output_task_relative_root"]), label="final output root")
    output_root = final_output_root.with_name(final_output_root.name + ".partial")
    try:
        output_root.resolve().relative_to(artifact_root)
    except ValueError as exc:
        raise RuntimeError(f"partial output root escapes artifact root: {output_root}") from exc
    if final_output_root.exists() or output_root.exists():
        raise RuntimeError(
            "PARTIAL_NAMESPACE_PRESENT_OR_FINAL_EXISTS: no overwrite, reuse, or automatic cleanup is allowed; "
            f"an exact recovery review must choose a new namespace or approve exact-target cleanup: {final_output_root}"
        )
    source_records = config["source_records"]
    metrics_data, metrics_record = read_verified(
        contained_path(source_root, source_records["metrics"]["path"], label="source metrics"),
        source_records["metrics"],
    )
    reference_data, reference_record = read_verified(
        contained_path(source_root, source_records["reference_cells"]["path"], label="source reference cells"),
        source_records["reference_cells"],
    )
    units_data, units_record = read_verified(
        contained_path(source_root, source_records["execution_units"]["path"], label="source execution units"),
        source_records["execution_units"],
    )
    selected_records = list(config["selection"]["records"])
    selected_ids = [str(record["building_id"]) for record in selected_records]
    if len(selected_ids) != 3 or len(set(selected_ids)) != 3:
        raise RuntimeError("sample config must contain exactly three unique buildings")
    all_metrics = [
        row
        for row in parse_jsonl(metrics_data)
        if row.get("building_id") in selected_ids and row.get("method_id") in source_methods
    ]
    expected_metric_rows = len(selected_ids) * len(source_methods)
    if len(all_metrics) != expected_metric_rows:
        raise RuntimeError(
            f"expected exact {len(selected_ids)}x{len(source_methods)} source metric rows, found {len(all_metrics)}"
        )
    by_building: dict[str, dict[str, dict[str, Any]]] = {building_id: {} for building_id in selected_ids}
    for row in all_metrics:
        by_building[str(row["building_id"])][str(row["method_id"])] = row
    for selection in selected_records:
        building_id = str(selection["building_id"])
        rows = by_building[building_id]
        if set(rows) != set(source_methods):
            raise RuntimeError(f"method rows mismatch for {building_id}")
        sample = rows["C1_L_upper"]
        if not all(bool(row.get("strict_e_paired")) for row in rows.values()):
            raise RuntimeError(f"sample lost strict independent reference: {building_id}")
        if "C1_L_upper" in rows and rows["C1_L_upper"].get("reference_role") != "SELF_REFERENCE_DIAGNOSTIC_ONLY":
            raise RuntimeError(f"C1 reference isolation drift: {building_id}")
        independent_methods = [method for method in ("C2_MVS", "C3_GS_image") if method in rows]
        if any(rows[method].get("reference_role") != "UAS_PATCH_CANDIDATE_SCORE_ONLY" for method in independent_methods):
            raise RuntimeError(f"C2/C3 reference isolation drift: {building_id}")
        if any(row.get("scientific_verdict") is not None for row in rows.values()):
            raise RuntimeError(f"scientific verdict must remain null: {building_id}")
        for method, row in rows.items():
            for field in ("G3_roof_structure_acceptable", "G4_geometric_accuracy_acceptable", "PASS_usable"):
                if field not in row or row[field] is not None:
                    raise RuntimeError(f"official null field drift: {building_id} {method} {field}")
        if any(row.get("criterion_version") != config["criterion_version"] for row in rows.values()):
            raise RuntimeError(f"criterion version drift: {building_id}")
        if any(row.get("git_commit") != config["source_evaluator"]["source_git_commit"] for row in rows.values()):
            raise RuntimeError(f"source evaluator commit drift: {building_id}")
        bbox = bbox_from_row(sample)
        observed_area = bbox.width * bbox.height
        if not math.isclose(observed_area, float(selection["bbox_area_m2"]), rel_tol=0, abs_tol=0.01):
            raise RuntimeError(f"outcome-free bbox area drift: {building_id}")
        if str(sample["candidate_group_id"]) != str(selection["candidate_group_id"]):
            raise RuntimeError(f"outcome-free group drift: {building_id}")
    reference_rows = [row for row in parse_jsonl(reference_data) if row.get("stable_id") in selected_ids]
    ref_by_building = {building_id: [] for building_id in selected_ids}
    for row in reference_rows:
        ref_by_building[str(row["stable_id"])].append(row)
    if any(not ref_by_building[building_id] for building_id in selected_ids):
        raise RuntimeError("one or more strict sample buildings have no reference rows")
    for building_id in selected_ids:
        expected_count = len(ref_by_building[building_id])
        if any(int(row.get("reference_cell_count", -1)) != expected_count for row in by_building[building_id].values()):
            raise RuntimeError(f"reference-cell count drift: {building_id}")
    units = {str(row["operation_unit_id"]): row for row in parse_jsonl(units_data)}
    validate_sealed_operation_units(by_building, selected_ids, units, source_methods)
    rgb = config["rgb_context"]
    scene_path = contained_path(artifact_root, str(rgb["scene_reference_relative_path"]), label="scene reference")
    camera_model_path = contained_path(artifact_root, str(rgb["cameras_relative_path"]), label="camera model")
    camera_poses_path = contained_path(artifact_root, str(rgb["images_relative_path"]), label="camera poses")
    image_root = contained_path(artifact_root, str(rgb["image_directory_relative_path"]), label="raw image root")
    scene_ref = json.loads(scene_path.read_text(encoding="utf-8"))
    model = projection.parse_cam_model(camera_model_path)
    cameras = projection.parse_cameras(camera_poses_path, scene_ref)
    if len(cameras) != 937:
        raise RuntimeError(f"expected exact 937 cameras, found {len(cameras)}")
    output_root.mkdir(parents=True)
    recorder = Recorder(
        output_root,
        artifact_root,
        script_path,
        config_path,
        reference_record["sha256"],
        config,
        offered_commit,
    )
    common_source_paths = [scene_path, camera_model_path, camera_poses_path]
    common_sources = [recorder.digest.record(path, root=artifact_root, role="camera_projection") for path in common_source_paths]
    geometry_cache: dict[str, Geometry] = {}
    panel_map: dict[str, dict[str, Any]] = {}
    summary_rows: list[dict[str, Any]] = []
    selected_metric_rows: list[dict[str, Any]] = []
    for selection in selected_records:
        building_id = str(selection["building_id"])
        rows = by_building[building_id]
        bbox = bbox_from_row(rows["C1_L_upper"])
        reference = reference_for(ref_by_building[building_id])
        reference_subset_sha = sha256_bytes(canonical_bytes(reference.xyz.tolist()))
        support_hash = sha256_bytes(canonical_bytes({"crs": "EPSG:25832", "bbox": asdict(bbox), "reference_subset_sha256": reference_subset_sha}))
        camera_records = select_cameras(reference, bbox, cameras, model, scene_ref, int(rgb["camera_count"]), float(rgb["minimum_coverage_fraction_of_best"]))
        case_root = output_root / "qualitative" / building_id
        for index, camera_record in enumerate(camera_records, 1):
            panel_id = f"{building_id}__RAW__RAW_CURRENT_IMAGES_WITH_ROOF_PROJECTION__RAW_{index}"
            image_path = contained_path(image_root, str(camera_record["camera"].name), label="selected raw image")
            panel_path = case_root / "panels" / f"RAW_{index}.png"
            raw_overlay = save_rgb_projection(panel_path, image_path, camera_record, float(config["views"]["raw_crop_margin_ratio"]), int(config["views"]["raw_crop_minimum_margin_px"]))
            if int(raw_overlay["projected_visible_count"]) <= 0:
                raise RuntimeError(f"raw roof reference is not visibly projected: {panel_id}")
            overlay = {
                "geometry_projected_visible_count": raw_overlay["projected_visible_count"],
                "geometry_projected_occluded_count": 0,
                "geometry_projected_clipped_count": raw_overlay["projected_clipped_count"],
                "structure_projected_visible_count": raw_overlay["projected_visible_count"],
                "structure_projected_occluded_count": 0,
                "structure_projected_clipped_count": raw_overlay["projected_clipped_count"],
                "projected_clipped_count": raw_overlay["projected_clipped_count"],
            }
            image_source = recorder.digest.record(image_path, root=artifact_root, role="current_raw_image")
            panel = recorder.panel(
                panel_id=panel_id,
                building_id=building_id,
                method_id="RAW",
                stage_id="RAW_CURRENT_IMAGES_WITH_ROOF_PROJECTION",
                view_id=f"RAW_{index}",
                path=panel_path,
                sources=[*common_sources, image_source, reference_record],
                overlay=overlay,
                view_spec=raw_overlay,
                run_id="DISPLAY_ONLY_FROM_FROZEN_BASE",
                geometry_independence_class="STRICT_INDEPENDENT_UAS_REFERENCE_DIAGNOSTIC",
                structure_independence_class="STRICT_INDEPENDENT_UAS_REFERENCE_DIAGNOSTIC",
                method_metric_reference_class="NOT_APPLICABLE_DISPLAY_ONLY",
                status="PROJECTED",
                content_status="AVAILABLE",
                support_hash=support_hash,
                reference_subset_sha=reference_subset_sha,
            )
            panel_map[panel_id] = panel
        geometries: dict[str, Geometry] = {}
        for method in source_methods:
            unit_id = rows[method].get("operation_unit_id")
            if not unit_id or str(unit_id) not in units:
                raise RuntimeError(f"sealed operation unit missing: {building_id} {method} {unit_id}")
            if str(unit_id) not in geometry_cache:
                geometry_cache[str(unit_id)] = load_geometry(
                    source_root,
                    units.get(str(unit_id)),
                    digest=recorder.digest,
                    artifact_root=artifact_root,
                )
            geometries[method] = geometry_cache.get(str(unit_id), empty_geometry())
        metric_cards: dict[str, str] = {}
        for method in display_methods:
            row = rows.get(method)
            geometry = geometries.get(method, empty_geometry())
            input_count = int(len(crop_points(geometry.points, bbox.padded(float(config["views"]["viewport_margin_ratio"]), float(config["views"]["viewport_minimum_margin_m"]))).xyz)) if row is not None else None
            metric_cards[method] = metric_card(method, row, input_count)
            source_list = geometry.sources
            for stage_id, mode in STAGE_ROWS[method]:
                if mode == "missing_render":
                    status = "OUTPUT_MISSING: sealed C3 run has no RGB+semantic render artifact"
                    render_mode = "missing"
                elif mode == "not_run":
                    status = "NOT_RUN: this sample reuses C1–C3 only"
                    render_mode = "missing"
                else:
                    status = None
                    render_mode = mode
                content_status = "OUTPUT_MISSING" if mode == "missing_render" else "NOT_RUN" if mode == "not_run" else "AVAILABLE"
                if mode == "input" and not len(geometry.points.xyz):
                    status = "OUTPUT_MISSING: no associated sealed input"
                    content_status = "OUTPUT_MISSING"
                if mode == "output" and not geometry.surfaces:
                    status = "OUTPUT_MISSING: no associated sealed Roofer output"
                    content_status = "OUTPUT_MISSING"
                for view_id in VIEW_IDS:
                    panel_id = f"{building_id}__{method}__{stage_id}__{view_id}"
                    panel_path = case_root / "panels" / f"{method}__{stage_id}__{view_id}.png"
                    overlay_counts = render_spatial_panel(
                        panel_path,
                        view=view_id,
                        bbox=bbox,
                        reference=reference,
                        geometry=geometry if render_mode != "missing" else empty_geometry(),
                        mode=render_mode,
                        status=status,
                        self_reference=method == "C1_L_upper",
                        view_config=config["views"],
                    )
                    if int(overlay_counts["projected_visible_count"]) <= 0:
                        raise RuntimeError(f"roof reference is not visibly projected: {panel_id}")
                    overlay = {
                        "geometry_projected_visible_count": int(overlay_counts["projected_visible_count"]),
                        "geometry_projected_occluded_count": int(overlay_counts["projected_occluded_count"]),
                        "geometry_projected_clipped_count": int(overlay_counts["projected_clipped_count"]),
                        "structure_projected_visible_count": int(overlay_counts["projected_visible_count"]),
                        "structure_projected_occluded_count": int(overlay_counts["projected_occluded_count"]),
                        "structure_projected_clipped_count": int(overlay_counts["projected_clipped_count"]),
                        "projected_clipped_count": int(overlay_counts["projected_clipped_count"]),
                    }
                    if method == "C1_L_upper":
                        overlay_independence = "STRICT_INDEPENDENT_UAS_REFERENCE_DIAGNOSTIC"
                        metric_reference_class = "SELF_REFERENCE_DIAGNOSTIC_ONLY"
                    elif method in {"C2_MVS", "C3_GS_image"}:
                        overlay_independence = "STRICT_INDEPENDENT_UAS_REFERENCE_DIAGNOSTIC"
                        metric_reference_class = "UAS_PATCH_CANDIDATE_SCORE_ONLY"
                    else:
                        overlay_independence = "REFERENCE_AVAILABLE_METHOD_NOT_RUN"
                        metric_reference_class = "NONE_METHOD_NOT_RUN"
                    panel = recorder.panel(
                        panel_id=panel_id,
                        building_id=building_id,
                        method_id=method,
                        stage_id=stage_id,
                        view_id=view_id,
                        path=panel_path,
                        sources=[*source_list, reference_record, metrics_record],
                        overlay=overlay,
                        view_spec={"view_id": view_id, **config["views"]},
                        run_id=str(row["run_id"]) if row is not None else "NOT_RUN",
                        geometry_independence_class=overlay_independence,
                        structure_independence_class=overlay_independence,
                        method_metric_reference_class=metric_reference_class,
                        status="PROJECTED",
                        content_status=content_status,
                        support_hash=support_hash,
                        reference_subset_sha=reference_subset_sha,
                    )
                    panel_map[panel_id] = panel
            first_stage = STAGE_ROWS[method][0][0]
            if row is not None:
                input_stage = next(stage for stage, mode in STAGE_ROWS[method] if mode == "input")
                output_stage = next(stage for stage, mode in STAGE_ROWS[method] if mode == "output")
                input_panel = panel_map[f"{building_id}__{method}__{input_stage}__TOP"]
                metric_panel = panel_map[f"{building_id}__{method}__{output_stage}__TOP"]
                recorder.metric(
                    metric_id=f"{building_id}:{method}:display_input_point_count",
                    panel=input_panel,
                    value=input_count,
                    unit="points",
                    reference_role="display_support",
                    validity="POST_HOC_DISPLAY_DIAGNOSTIC",
                    source_sha=source_list[0]["sha256"] if source_list else metrics_record["sha256"],
                    evaluator="DISPLAY_RENDERER",
                )
            else:
                metric_panel = panel_map[f"{building_id}__{method}__{first_stage}__TOP"]
            if row is None:
                recorder.metric(
                    metric_id=f"{building_id}:{method}:NOT_RUN",
                    panel=metric_panel,
                    value=None,
                    unit="status",
                    reference_role="NONE_METHOD_NOT_RUN",
                    validity="NOT_RUN",
                    source_sha=metrics_record["sha256"],
                    evaluator="DISPLAY_RENDERER",
                )
                continue
            reference_role = str(row["reference_role"])
            for metric_name, unit in (
                ("height_error_mae_m", "m"),
                ("RMSZ_m", "m"),
                ("surface_distance_rmse_m", "m"),
                ("surface_distance_p95_m", "m"),
                ("G0_generated", "boolean"),
                ("G1_schema_semantic", "boolean"),
                ("G2_geometry_topology_valid", "boolean"),
                ("G3_roof_structure_acceptable", "nullable_boolean"),
                ("G4_geometric_accuracy_acceptable", "nullable_boolean"),
                ("PASS_usable", "nullable_boolean"),
            ):
                value = metric_value(row, metric_name)
                validity = "OFFICIAL_NULL_CRITERION_NOT_FROZEN" if metric_name in {"G3_roof_structure_acceptable", "G4_geometric_accuracy_acceptable", "PASS_usable"} else "DIAGNOSTIC"
                recorder.metric(
                    metric_id=f"{building_id}:{method}:{metric_name}",
                    panel=metric_panel,
                    value=value,
                    unit=unit,
                    reference_role=reference_role,
                    validity=validity,
                    source_sha=metrics_record["sha256"],
                    evaluator="SOURCE_SEALED",
                )
            selected_metric_rows.append(row)
            summary_rows.append({
                "building_id": building_id,
                "size_bin": selection["size_bin"],
                "method_id": method,
                "association_status": row.get("association_status"),
                "one_to_one": row.get("one_to_one_building_component"),
                "reference_role": row.get("reference_role"),
                "reference_cells": row.get("reference_cell_count"),
                "G0": row.get("G0_generated"),
                "G1": row.get("G1_schema_semantic"),
                "G2": row.get("G2_geometry_topology_valid"),
                "height_MAE_m": metric_value(row, "height_error_mae_m"),
                "RMSZ_m": metric_value(row, "RMSZ_m"),
                "surface_RMSE_m": metric_value(row, "surface_distance_rmse_m"),
                "surface_P95_m": metric_value(row, "surface_distance_p95_m"),
                "official_G3": row.get("G3_roof_structure_acceptable"),
                "official_G4": row.get("G4_geometric_accuracy_acceptable"),
                "official_PASS": row.get("PASS_usable"),
                "meaning_ko": summarize_reason(row),
            })
        case_page = case_html(building_id, selection, panel_map, metric_cards, camera_records, display_methods)
        write_new(case_root / "case.html", case_page.encode("utf-8"))
    expected_ids = expected_panel_ids(selected_ids, display_methods)
    expected_panel_count = len(selected_ids) * (
        4 + len(VIEW_IDS) * sum(len(STAGE_ROWS[method]) for method in display_methods)
    )
    observed_ids = [str(row["panel_id"]) for row in recorder.panels]
    if (
        len(observed_ids) != expected_panel_count
        or len(set(observed_ids)) != expected_panel_count
        or set(observed_ids) != expected_ids
    ):
        missing = sorted(expected_ids - set(observed_ids))
        extra = sorted(set(observed_ids) - expected_ids)
        raise RuntimeError(f"panel-slot contract mismatch: missing={missing[:5]} extra={extra[:5]}")
    overlay_status_counts = Counter(str(row["overlay_status"]) for row in recorder.panels)
    if overlay_status_counts != Counter({"PROJECTED": expected_panel_count}):
        raise RuntimeError(f"roof-reference projection coverage mismatch: {dict(overlay_status_counts)}")
    reference_counts = {building_id: len(ref_by_building[building_id]) for building_id in selected_ids}
    for panel in recorder.panels:
        reference_count = reference_counts[str(panel["building_id"])]
        geometry_total = sum(
            int(panel[key])
            for key in (
                "geometry_projected_visible_count",
                "geometry_projected_occluded_count",
                "geometry_projected_clipped_count",
            )
        )
        structure_total = sum(
            int(panel[key])
            for key in (
                "structure_projected_visible_count",
                "structure_projected_occluded_count",
                "structure_projected_clipped_count",
            )
        )
        if geometry_total != reference_count or structure_total != reference_count:
            raise RuntimeError(
                f"roof-reference projection count mismatch: {panel['panel_id']} "
                f"geometry={geometry_total} structure={structure_total} expected={reference_count}"
            )
    panel_manifest = b"".join(canonical_bytes(row) for row in recorder.panels)
    metric_manifest = b"".join(canonical_bytes(row) for row in recorder.metrics)
    write_new(output_root / "manifests/panel_manifest_v1.jsonl", panel_manifest)
    write_new(output_root / "manifests/metric_manifest_v1.jsonl", metric_manifest)
    metric_fields = ["building_id", "method_id", "association_status", "one_to_one_building_component", "reference_role", "reference_cell_count", "G0_generated", "G1_schema_semantic", "G2_geometry_topology_valid", "G3_roof_structure_acceptable", "G4_geometric_accuracy_acceptable", "PASS_usable", "criterion_version", "scientific_verdict", "continuous_metrics"]
    metric_csv_path = output_root / "metrics/sample_building_method_metrics_v1.csv"
    metric_csv_path.parent.mkdir(parents=True, exist_ok=True)
    with metric_csv_path.open("x", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=metric_fields, lineterminator="\n")
        writer.writeheader()
        for row in selected_metric_rows:
            writer.writerow({key: json.dumps(row.get(key), ensure_ascii=False, sort_keys=True) if key == "continuous_metrics" else row.get(key) for key in metric_fields})
    summary_path = output_root / "metrics/sample_quantitative_summary_v1.csv"
    with summary_path.open("x", encoding="utf-8", newline="") as stream:
        fields = list(summary_rows[0])
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(summary_rows)
    index_lines = [
        "<!doctype html><html lang='ko'><head><meta charset='utf-8'><title>P2 대표 3동 정성·정량 sample</title>",
        "<style>body{font-family:Arial,'Malgun Gothic',sans-serif;margin:28px;max-width:1100px}table{border-collapse:collapse;width:100%}th,td{border:1px solid #bbb;padding:8px;text-align:left}.warn{background:#fff3cd;padding:12px}</style></head><body>",
        "<h1>P2 대표 3동 정성·정량 sample</h1>",
        "<p class='warn'>현재 결과는 건물별 Stage 3 분리 실패를 보여주는 기술 진단입니다. 공식 G3/G4/PASS와 scientific_verdict는 null입니다.</p>",
        "<table><thead><tr><th>크기</th><th>건물</th><th>선정 이유</th><th>비교판</th></tr></thead><tbody>",
    ]
    for selection in selected_records:
        building_id = str(selection["building_id"])
        index_lines.append(f"<tr><td>{html.escape(str(selection['size_bin']))}</td><td><code>{html.escape(building_id)}</code></td><td>strict independent reference, distinct spatial group, outcome-free bbox selection</td><td><a href='{html.escape(building_id)}/case.html'>정성·정량 matrix 열기</a></td></tr>")
    index_lines.append(
        "</tbody></table><p>정량 CSV: <a href='../metrics/sample_quantitative_summary_v1.csv'>요약</a> · "
        f"<a href='../metrics/sample_building_method_metrics_v1.csv'>exact {len(selected_metric_rows)} rows</a></p></body></html>"
    )
    write_new(output_root / "qualitative/index.html", "\n".join(index_lines).encode("utf-8"))
    output_files = [path for path in output_root.rglob("*") if path.is_file() and not path.is_symlink()]
    output_bytes = sum(path.stat().st_size for path in output_files)
    if output_bytes > int(config["execution"]["output_cap_bytes"]):
        raise RuntimeError(f"output cap exceeded: {output_bytes}")
    finalized = {
        "schema": "jointbuildgs.p2.representative_comparison_matrix_sample.finalized.v1",
        "task_id": config["task_id"],
        "status": "TECHNICAL_DIAGNOSTIC_SAMPLE_COMPLETE",
        "selected_buildings": selected_ids,
        "case_count": 3,
        "panel_count": len(recorder.panels),
        "metric_binding_count": len(recorder.metrics),
        "display_methods": list(display_methods),
        "overlay_status_counts": dict(sorted(overlay_status_counts.items())),
        "source_full_read_digest_passes": {"metrics": 1, "reference_cells": 1, "execution_units": 1},
        "execution_accounting": {"roofer": 0, "g2": 0, "gs_training": 0, "large_archive_hash_passes": 0},
        "output_file_count_before_finalized": len(output_files),
        "output_bytes_before_finalized": output_bytes,
        "criterion_version": config["criterion_version"],
        "official_G3_G4_PASS": None,
        "scientific_verdict": None,
    }
    write_new(output_root / "control/finalized_v1.json", canonical_bytes(finalized))
    output_root.rename(final_output_root)
    print(json.dumps(finalized, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
