#!/usr/bin/env python3
"""Render large-label C1/C2 and C3 3D diagnostic case sheets from new outputs."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any, Mapping, Sequence

import cv2
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.collections import PolyCollection
from mpl_toolkits.mplot3d.art3d import Poly3DCollection
import numpy as np
import open3d as o3d

from scripts.evidence_and_attributes.population_analysis import population_aux_v3 as projection
from scripts.p2.c1_c2_oracle_c3_extract_v1.contract import (
    canonical_json_bytes,
    file_record,
    load_building_references,
    load_config,
    write_new,
)
from scripts.p2.c1_c2_oracle_c3_extract_v1.prepare_c1_c2 import CONDITIONS
from scripts.p2.representative_comparison_matrix_sample_v1.render_sample import (
    context_crop_xyxy,
    projection_inside,
    roof_ring_vertices,
    select_current_uas_camera_roles,
)
from src.visualization.fixed_view_qualitative import BBox, PointSet, Surface, load_cityjsonseq, load_las_points


VIEWS = ("TOP", "OBLIQUE_1", "OBLIQUE_2", "PRINCIPAL_SECTION")
SEMANTIC_COLORS = np.asarray([[45, 45, 45], [213, 94, 0], [0, 114, 178], [0, 158, 115]], dtype=np.uint8)


def _bbox(reference: Any) -> BBox:
    return BBox(*map(float, reference.footprint.bounds))


def _rings_xy(reference: Any) -> list[np.ndarray]:
    geometry = reference.footprint
    polygons = [geometry] if geometry.geom_type == "Polygon" else list(geometry.geoms)
    output = []
    for polygon in polygons:
        output.append(np.asarray(polygon.exterior.coords, dtype=np.float64))
        output.extend(np.asarray(interior.coords, dtype=np.float64) for interior in polygon.interiors)
    return output


def _load_method_geometry(output_root: Path, method: str, stable_id: str) -> tuple[PointSet, list[Surface], list[np.ndarray], dict[str, Any]]:
    work = output_root / "operations" / method / stable_id / "work"
    prepared = json.loads((work / "prepared_v1.json").read_text(encoding="utf-8"))
    terminal_path = work / "roofer_terminal_v1.json"
    terminal = json.loads(terminal_path.read_text(encoding="utf-8")) if terminal_path.is_file() else {
        "status": "PRE_ROOFER_REFERENCE_ID_ALIGNMENT_FAILURE",
        "outputs": [],
        "pre_roofer_failure": prepared.get("pre_roofer_failure"),
    }
    if terminal.get("status") == "COMPLETED" and len(terminal.get("outputs") or ()) == 1:
        output_path = output_root / terminal["outputs"][0]["path"]
        surfaces = load_cityjsonseq(output_path)
    elif prepared.get("roofer_eligible") is False and terminal.get("status") == "PRE_ROOFER_REFERENCE_ID_ALIGNMENT_FAILURE":
        surfaces = []
    else:
        raise RuntimeError(f"incomplete C1/C2 terminal: {method} {stable_id}")
    footprint = json.loads((work / "gt_footprint_oracle.geojson").read_text(encoding="utf-8"))
    coordinates = footprint["features"][0]["geometry"]["coordinates"]
    if footprint["features"][0]["geometry"]["type"] == "Polygon":
        rings = [np.asarray(ring, dtype=np.float64) for ring in coordinates]
    else:
        rings = [np.asarray(ring, dtype=np.float64) for polygon in coordinates for ring in polygon]
    return load_las_points(work / "input.las"), surfaces, rings, terminal


def _setup_3d(ax: Any, bbox: BBox, zlim: tuple[float, float], view: str) -> None:
    pad = max(max(bbox.width, bbox.height) * 0.25, 4.0)
    ax.set_xlim(bbox.min_x - pad, bbox.max_x + pad)
    ax.set_ylim(bbox.min_y - pad, bbox.max_y + pad)
    ax.set_zlim(*zlim)
    ax.set_box_aspect((bbox.width + 2 * pad, bbox.height + 2 * pad, max(zlim[1] - zlim[0], 1.0)))
    if view == "OBLIQUE_1":
        ax.view_init(elev=28, azim=-55)
    else:
        ax.view_init(elev=32, azim=35)
    ax.set_xlabel("E", fontsize=8)
    ax.set_ylabel("N", fontsize=8)
    ax.set_zlabel("Z", fontsize=8)


def _draw_footprint(ax: Any, rings: Sequence[np.ndarray], view: str, z: float) -> None:
    for ring in rings:
        if view == "TOP":
            ax.plot(ring[:, 0], ring[:, 1], color="#f59e0b", linestyle="--", linewidth=2.2)
        elif view.startswith("OBLIQUE"):
            ax.plot(ring[:, 0], ring[:, 1], np.full(len(ring), z), color="#f59e0b", linestyle="--", linewidth=2.0)
        else:
            horizontal = ring[:, 0]
            ax.plot([horizontal.min(), horizontal.max()], [z, z], color="#f59e0b", linestyle="--", linewidth=2.0)


def _panel(
    path: Path,
    *,
    view: str,
    bbox: BBox,
    points: PointSet | None,
    surfaces: Sequence[Surface],
    footprint_rings: Sequence[np.ndarray],
    title: str,
    lod2_context: bool = False,
) -> None:
    xyz_sets = []
    if points is not None and len(points.xyz):
        xyz_sets.append(points.xyz)
    xyz_sets.extend(surface.xyz for surface in surfaces if len(surface.xyz))
    z_all = np.concatenate([xyz[:, 2] for xyz in xyz_sets]) if xyz_sets else np.asarray([0.0, 1.0])
    z0, z1 = float(np.min(z_all)), float(np.max(z_all))
    pad_z = max((z1 - z0) * 0.1, 1.0)
    zlim = (z0 - pad_z, z1 + pad_z)
    figure = plt.figure(figsize=(6.4, 4.8), dpi=150)
    if view.startswith("OBLIQUE"):
        ax = figure.add_subplot(111, projection="3d", proj_type="ortho")
    else:
        ax = figure.add_subplot(111)
    if points is not None and len(points.xyz):
        keep = (
            (points.xyz[:, 0] >= bbox.min_x - 8) & (points.xyz[:, 0] <= bbox.max_x + 8)
            & (points.xyz[:, 1] >= bbox.min_y - 8) & (points.xyz[:, 1] <= bbox.max_y + 8)
        )
        xyz = points.xyz[keep]
        classes = points.classification[keep] if points.classification is not None else np.zeros(len(xyz), dtype=np.uint8)
        stride = max(1, len(xyz) // 8000)
        xyz, classes = xyz[::stride], classes[::stride]
        colors = np.where(classes[:, None] == 6, np.asarray([[0.0, 0.75, 0.88]]), np.asarray([[0.85, 0.18, 0.85]]))
        if view == "TOP":
            ax.scatter(xyz[:, 0], xyz[:, 1], c=colors, s=2.0, linewidths=0)
        elif view.startswith("OBLIQUE"):
            ax.scatter(xyz[:, 0], xyz[:, 1], xyz[:, 2], c=colors, s=1.7, linewidths=0, depthshade=False)
        else:
            center_y = (bbox.min_y + bbox.max_y) / 2
            band = max(bbox.height * 0.08, 0.8)
            section = xyz[np.abs(xyz[:, 1] - center_y) <= band]
            section_classes = classes[np.abs(xyz[:, 1] - center_y) <= band]
            section_colors = np.where(section_classes[:, None] == 6, np.asarray([[0.0, 0.75, 0.88]]), np.asarray([[0.85, 0.18, 0.85]]))
            ax.scatter(section[:, 0], section[:, 2], c=section_colors, s=3, linewidths=0)
    for surface in surfaces:
        ring = surface.xyz
        if not len(ring):
            continue
        color = "#2563eb" if surface.semantic == "RoofSurface" else "#777777" if not lod2_context else {
            "RoofSurface": "#d95f02", "WallSurface": "#7570b3", "GroundSurface": "#1b9e77"
        }.get(surface.semantic, "#777777")
        closed = np.vstack((ring, ring[0]))
        if view == "TOP":
            ax.plot(closed[:, 0], closed[:, 1], color=color, linewidth=1.1)
        elif view.startswith("OBLIQUE"):
            ax.plot(closed[:, 0], closed[:, 1], closed[:, 2], color=color, linewidth=1.1)
        else:
            center_y = (bbox.min_y + bbox.max_y) / 2
            if np.min(ring[:, 1]) <= center_y <= np.max(ring[:, 1]):
                order = np.argsort(ring[:, 0])
                ax.plot(ring[order, 0], ring[order, 2], color=color, linewidth=1.1)
    ground_z = float(np.quantile(z_all, 0.02))
    _draw_footprint(ax, footprint_rings, view, ground_z)
    if (points is None or not len(points.xyz)) and not surfaces:
        text_method = ax.text2D if view.startswith("OBLIQUE") else ax.text
        text_method(
            0.5,
            0.5,
            "NO ROOFER OUTPUT\nNOT RUN BEFORE ROOFER",
            transform=ax.transAxes,
            ha="center",
            va="center",
            fontsize=13,
            fontweight="bold",
            color="#991b1b",
            bbox={"facecolor": "white", "edgecolor": "#991b1b", "alpha": 0.92, "pad": 8},
        )
    if view == "TOP":
        pad = max(max(bbox.width, bbox.height) * 0.25, 4.0)
        ax.set_xlim(bbox.min_x - pad, bbox.max_x + pad)
        ax.set_ylim(bbox.min_y - pad, bbox.max_y + pad)
        ax.set_aspect("equal")
        ax.set_xlabel("Easting")
        ax.set_ylabel("Northing")
    elif view.startswith("OBLIQUE"):
        _setup_3d(ax, bbox, zlim, view)
    else:
        pad = max(bbox.width * 0.25, 4.0)
        ax.set_xlim(bbox.min_x - pad, bbox.max_x + pad)
        ax.set_ylim(*zlim)
        ax.set_xlabel("principal E section")
        ax.set_ylabel("Z (m)")
    ax.set_title(title, fontsize=12, fontweight="bold")
    figure.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(path, metadata={"Software": "JointBuildGS C1/C2 oracle C3 extraction renderer"})
    plt.close(figure)


def _raw_roofline_panel(
    path: Path,
    image_path: Path,
    camera_record: Mapping[str, Any],
    roof_rings: Sequence[np.ndarray],
    model: tuple[int, int, np.ndarray],
    scene_ref: Mapping[str, Any],
    *,
    crop_scale: float,
    title: str,
) -> None:
    image = cv2.imread(str(image_path), cv2.IMREAD_COLOR)
    projections = [projection_inside(ring, camera_record["camera"], model, scene_ref, "orthometric") for ring in roof_rings]
    visible = [uv[inside] for uv, inside in projections if np.any(inside)]
    if not visible:
        raise RuntimeError(f"roofline not visible in selected current image: {image_path}")
    left, top, right, bottom = context_crop_xyxy(np.vstack(visible), image.shape[1], image.shape[0], crop_scale, 900, 675)
    crop = image[top:bottom, left:right].copy()
    offset = np.asarray([left, top])
    for uv, inside in projections:
        if np.all(inside):
            ring = np.rint(uv - offset).astype(np.int32).reshape((-1, 1, 2))
            cv2.polylines(crop, [ring], True, (20, 20, 20), 12, cv2.LINE_AA)
            cv2.polylines(crop, [ring], True, (30, 205, 255), 6, cv2.LINE_AA)
    cv2.rectangle(crop, (0, 0), (crop.shape[1], 52), (20, 20, 20), -1)
    cv2.putText(crop, title, (16, 35), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (245, 245, 245), 2, cv2.LINE_AA)
    ok, encoded = cv2.imencode(".png", crop)
    if not ok:
        raise RuntimeError("raw roofline panel encoding failed")
    write_new(path, encoded.tobytes())


def _compose_sheet(path: Path, rows: Sequence[tuple[str, Sequence[Path]]], stable_id: str, subtitle: str) -> None:
    cell_w, cell_h = 960, 720
    label_w, header_h = 300, 100
    canvas = np.full((header_h + len(rows) * cell_h, label_w + 4 * cell_w, 3), 255, dtype=np.uint8)
    cv2.putText(canvas, stable_id, (24, 42), cv2.FONT_HERSHEY_SIMPLEX, 1.05, (20, 20, 20), 2, cv2.LINE_AA)
    cv2.putText(canvas, subtitle, (24, 82), cv2.FONT_HERSHEY_SIMPLEX, 0.62, (55, 55, 55), 1, cv2.LINE_AA)
    for col, name in enumerate(VIEWS):
        cv2.putText(canvas, name, (label_w + col * cell_w + 24, 82), cv2.FONT_HERSHEY_SIMPLEX, 0.75, (20, 20, 20), 2, cv2.LINE_AA)
    for row_index, (label, paths) in enumerate(rows):
        y0 = header_h + row_index * cell_h
        cv2.rectangle(canvas, (0, y0), (label_w, y0 + cell_h), (242, 244, 247), -1)
        words = label.split("\n")
        for line_index, word in enumerate(words):
            cv2.putText(canvas, word, (18, y0 + 54 + line_index * 34), cv2.FONT_HERSHEY_SIMPLEX, 0.62, (25, 25, 25), 2, cv2.LINE_AA)
        for col, panel_path in enumerate(paths):
            image = cv2.imread(str(panel_path), cv2.IMREAD_COLOR)
            if image is None:
                raise RuntimeError(f"panel unreadable: {panel_path}")
            resized = cv2.resize(image, (cell_w, cell_h), interpolation=cv2.INTER_AREA)
            x0 = label_w + col * cell_w
            canvas[y0:y0 + cell_h, x0:x0 + cell_w] = resized
    ok, encoded = cv2.imencode(".png", canvas, [cv2.IMWRITE_PNG_COMPRESSION, 6])
    if not ok:
        raise RuntimeError("case sheet encoding failed")
    write_new(path, encoded.tobytes())


def render_c1_c2(output_root: Path, artifact_root: Path, lod2_path: Path) -> dict[str, Any]:
    config = load_config()
    references = load_building_references(lod2_path, config["scope"]["building_ids"])
    rgb_cfg = config["inputs"]["current_rgb"]
    scene_ref = json.loads((artifact_root / rgb_cfg["scene_reference_relative_path"]).read_text(encoding="utf-8"))
    camera_model = projection.parse_cam_model(artifact_root / rgb_cfg["cameras_relative_path"])
    cameras = projection.parse_cameras(artifact_root / rgb_cfg["images_relative_path"], scene_ref)
    image_root = artifact_root / rgb_cfg["image_directory_relative_path"]
    sheet_records = []
    for stable_id, reference in references.items():
        bbox = _bbox(reference)
        c1_points, c1_surfaces, footprint_rings, _c1_terminal = _load_method_geometry(output_root, CONDITIONS[0], stable_id)
        c2_points, c2_surfaces, _footprint2, _c2_terminal = _load_method_geometry(output_root, CONDITIONS[1], stable_id)
        roof_reference = roof_ring_vertices(reference.roof_rings_xyz)
        roles = select_current_uas_camera_roles(
            roof_reference,
            c1_points,
            bbox,
            cameras,
            camera_model,
            scene_ref,
            0.5,
            "orthometric",
            "ellipsoidal",
        )
        case_root = output_root / "qualitative/c1_c2" / stable_id
        raw_rows = []
        raw_specs = [("COVERAGE", 3.0), ("NADIR", 2.0), ("NADIR", 1.35), ("OBLIQUE", 2.0)]
        for index, (role, scale) in enumerate(raw_specs):
            path = case_root / f"panels/raw_{index + 1}.png"
            _raw_roofline_panel(
                path,
                image_root / roles[role]["camera"].name,
                roles[role],
                reference.roof_rings_xyz,
                camera_model,
                scene_ref,
                crop_scale=scale,
                title=f"2024 RGB + 2022 LoD2 roofline | {roles[role]['camera'].name}",
            )
            raw_rows.append(path)
        lod2_surfaces = [Surface(np.asarray(ring, dtype=np.float64), semantic) for semantic, ring in reference.surface_rings]
        failed_alignment = stable_id == "DEBY_LOD2_4907177"
        roofer_suffix = "NOT RUN — REFERENCE/ID ALIGNMENT" if failed_alignment else "oracle diagnostic"
        row_specs = [
            ("C1 UAS LiDAR\npoint cloud + GT footprint", c1_points, [], False),
            (f"C1 Roofer\n{roofer_suffix}", None, c1_surfaces, False),
            ("C2 current MVS\npoint cloud + GT footprint", c2_points, [], False),
            (f"C2 Roofer\n{roofer_suffix}", None, c2_surfaces, False),
            ("2022 LoD2\nepoch context only", None, lod2_surfaces, True),
        ]
        rows: list[tuple[str, Sequence[Path]]] = [("2024 RGB + 2022 roofline\nprojection only", raw_rows)]
        for row_index, (label, points, surfaces, lod2_context) in enumerate(row_specs):
            paths = []
            for view in VIEWS:
                path = case_root / "panels" / f"row_{row_index + 2}_{view.lower()}.png"
                _panel(
                    path,
                    view=view,
                    bbox=bbox,
                    points=points,
                    surfaces=surfaces,
                    footprint_rings=footprint_rings,
                    title=f"{label.replace(chr(10), ' ')} | {view}",
                    lod2_context=lod2_context,
                )
                paths.append(path)
            rows.append((label, paths))
        sheet = case_root / "case_sheet_c1_c2_oracle_v1.png"
        alignment = "REFERENCE/ID ALIGNMENT REVIEW" if stable_id == "DEBY_LOD2_4907177" else "2022/2024 epoch context shown separately"
        _compose_sheet(sheet, rows, stable_id, f"GT-footprint oracle diagnostic; official honest Stage3=false | {alignment}")
        sheet_records.append({"stable_id": stable_id, "case_sheet": file_record(sheet, output_root), "panel_count": 24})
    body = {
        "schema": "jointbuildgs.c1_c2_oracle_qualitative.v1",
        "case_sheet_count": len(sheet_records),
        "panel_count": sum(row["panel_count"] for row in sheet_records),
        "records": sheet_records,
        "roofline_role": "CURRENT_RGB_PROJECTION_AND_SEPARATE_LOD2_CONTEXT_ONLY",
        "input_output_overlay": "GT_GROUNDSURFACE_XY_FOOTPRINT_ONLY",
        "scientific_verdict": None,
    }
    write_new(output_root / "qualitative/c1_c2/index_v1.json", canonical_json_bytes(body))
    return body


def _read_binary_vertex_ply(path: Path) -> np.ndarray:
    with path.open("rb") as stream:
        lines = []
        while True:
            line = stream.readline()
            if not line:
                raise RuntimeError("truncated PLY")
            text = line.decode("ascii").strip()
            lines.append(text)
            if text == "end_header":
                break
        offset = stream.tell()
    count = int(next(line.split()[-1] for line in lines if line.startswith("element vertex ")))
    fields = []
    type_map = {"double": "<f8", "float": "<f4", "uchar": "u1"}
    for line in lines:
        tokens = line.split()
        if len(tokens) == 3 and tokens[0] == "property" and tokens[1] in type_map:
            fields.append((tokens[2], type_map[tokens[1]]))
    return np.memmap(path, mode="r", dtype=np.dtype(fields), offset=offset, shape=(count,))


def _c3_point_panel(
    path: Path,
    xyz: np.ndarray,
    colors: np.ndarray,
    bbox: BBox,
    footprint_rings: Sequence[np.ndarray],
    footprint_z: float,
    view: str,
    title: str,
) -> None:
    classes = np.zeros(len(xyz), dtype=np.uint8)
    points = PointSet(xyz, classes)
    figure = plt.figure(figsize=(6.4, 4.8), dpi=150)
    if view.startswith("OBLIQUE"):
        ax = figure.add_subplot(111, projection="3d", proj_type="ortho")
    else:
        ax = figure.add_subplot(111)
    stride = max(1, len(xyz) // 12000)
    q, c = xyz[::stride], colors[::stride]
    z0, z1 = float(np.quantile(xyz[:, 2], 0.005)), float(np.quantile(xyz[:, 2], 0.995))
    if view == "TOP":
        ax.scatter(q[:, 0], q[:, 1], c=c, s=2, linewidths=0)
        ax.set_aspect("equal")
        ax.set_xlim(bbox.min_x - 5, bbox.max_x + 5)
        ax.set_ylim(bbox.min_y - 5, bbox.max_y + 5)
    elif view.startswith("OBLIQUE"):
        ax.scatter(q[:, 0], q[:, 1], q[:, 2], c=c, s=1.8, linewidths=0, depthshade=False)
        _setup_3d(ax, bbox, (z0, z1), view)
    else:
        center_y = (bbox.min_y + bbox.max_y) / 2
        band = max(bbox.height * 0.08, 0.8)
        keep = np.abs(q[:, 1] - center_y) <= band
        ax.scatter(q[keep, 0], q[keep, 2], c=c[keep], s=3, linewidths=0)
        ax.set_xlim(bbox.min_x - 5, bbox.max_x + 5)
        ax.set_ylim(z0, z1)
    _draw_footprint(ax, footprint_rings, view, footprint_z)
    ax.set_title(title, fontsize=12, fontweight="bold")
    figure.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(path)
    plt.close(figure)


def _quaternion_axes(quaternions: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    q = np.asarray(quaternions, dtype=np.float64)
    q = q / np.maximum(np.linalg.norm(q, axis=1, keepdims=True), 1e-12)
    w, x, y, z = q.T
    axis_x = np.column_stack((1 - 2 * (y * y + z * z), 2 * (x * y + w * z), 2 * (x * z - w * y)))
    axis_y = np.column_stack((2 * (x * y - w * z), 1 - 2 * (x * x + z * z), 2 * (y * z + w * x)))
    return axis_x, axis_y


def _c3_gaussian_panel(
    path: Path,
    xyz: np.ndarray,
    quaternions: np.ndarray,
    scales_xy: np.ndarray,
    opacity: np.ndarray,
    colors: np.ndarray,
    bbox: BBox,
    footprint_rings: Sequence[np.ndarray],
    footprint_z: float,
    view: str,
    title: str,
) -> None:
    if not len(xyz):
        raise RuntimeError("no Gaussian primitives in building display crop")
    score = np.asarray(opacity) * np.sqrt(np.maximum(scales_xy[:, 0] * scales_xy[:, 1], 1e-12))
    maximum = 2800
    if len(xyz) > maximum:
        high_count = maximum // 2
        high = np.argpartition(score, -high_count)[-high_count:]
        remaining = np.setdiff1d(np.arange(len(xyz)), high, assume_unique=False)
        uniform = remaining[np.linspace(0, len(remaining) - 1, maximum - high_count, dtype=int)]
        selected = np.concatenate((high, uniform))
    else:
        selected = np.arange(len(xyz))
    selected = selected[np.argsort(score[selected])]
    q_xyz = np.asarray(xyz[selected], dtype=np.float64)
    q_quat = np.asarray(quaternions[selected], dtype=np.float64)
    q_scale = np.asarray(scales_xy[selected], dtype=np.float64)
    q_opacity = np.asarray(opacity[selected], dtype=np.float64)
    q_colors = np.asarray(colors[selected], dtype=np.float64)
    axis_x, axis_y = _quaternion_axes(q_quat)
    theta = np.linspace(0, 2 * np.pi, 13, endpoint=False)
    ellipse = (
        q_xyz[:, None, :]
        + 1.5 * q_scale[:, 0, None, None] * np.cos(theta)[None, :, None] * axis_x[:, None, :]
        + 1.5 * q_scale[:, 1, None, None] * np.sin(theta)[None, :, None] * axis_y[:, None, :]
    )
    facecolors = np.column_stack((q_colors, np.clip(0.16 + 0.72 * q_opacity, 0.16, 0.88)))
    z0, z1 = float(np.quantile(q_xyz[:, 2], 0.005)), float(np.quantile(q_xyz[:, 2], 0.995))
    figure = plt.figure(figsize=(6.4, 4.8), dpi=150)
    if view.startswith("OBLIQUE"):
        ax = figure.add_subplot(111, projection="3d", proj_type="ortho")
        collection = Poly3DCollection(ellipse, facecolors=facecolors, edgecolors="none", zsort="average")
        ax.add_collection3d(collection)
        _setup_3d(ax, bbox, (z0, z1), view)
    else:
        ax = figure.add_subplot(111)
        if view == "TOP":
            polygons = ellipse[:, :, :2]
            ax.add_collection(PolyCollection(polygons, facecolors=facecolors, edgecolors="none"))
            ax.set_aspect("equal")
            ax.set_xlim(bbox.min_x - 5, bbox.max_x + 5)
            ax.set_ylim(bbox.min_y - 5, bbox.max_y + 5)
        else:
            center_y = (bbox.min_y + bbox.max_y) / 2
            band = max(bbox.height * 0.08, 0.8)
            crosses = (ellipse[:, :, 1].min(axis=1) <= center_y + band) & (ellipse[:, :, 1].max(axis=1) >= center_y - band)
            polygons = ellipse[crosses][:, :, (0, 2)]
            ax.add_collection(PolyCollection(polygons, facecolors=facecolors[crosses], edgecolors="none"))
            ax.set_xlim(bbox.min_x - 5, bbox.max_x + 5)
            ax.set_ylim(z0, z1)
    _draw_footprint(ax, footprint_rings, view, footprint_z)
    ax.set_title(title, fontsize=12, fontweight="bold")
    figure.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(path, metadata={"Software": "JointBuildGS oriented 2D Gaussian ellipse renderer"})
    plt.close(figure)


def _c3_mesh_panel(
    path: Path,
    mesh_path: Path,
    bbox: BBox,
    footprint_rings: Sequence[np.ndarray],
    footprint_z: float,
    view: str,
    title: str,
) -> None:
    mesh = o3d.io.read_triangle_mesh(str(mesh_path))
    vertices = np.asarray(mesh.vertices)
    triangles = np.asarray(mesh.triangles)
    colors = np.asarray(mesh.vertex_colors)
    if not len(colors):
        colors = np.full((len(vertices), 3), 0.55)
    figure = plt.figure(figsize=(6.4, 4.8), dpi=150)
    if view.startswith("OBLIQUE"):
        ax = figure.add_subplot(111, projection="3d", proj_type="ortho")
        stride = max(1, len(triangles) // 50000)
        faces = vertices[triangles[::stride]]
        face_colors = colors[triangles[::stride]].mean(axis=1)
        collection = Poly3DCollection(faces, facecolors=face_colors, edgecolors="none", alpha=1.0)
        ax.add_collection3d(collection)
        zlim = (float(vertices[:, 2].min()), float(vertices[:, 2].max()))
        _setup_3d(ax, bbox, zlim, view)
    else:
        ax = figure.add_subplot(111)
        stride = max(1, len(vertices) // 12000)
        q, c = vertices[::stride], colors[::stride]
        if view == "TOP":
            ax.scatter(q[:, 0], q[:, 1], c=c, s=2, linewidths=0)
            ax.set_aspect("equal")
            ax.set_xlim(bbox.min_x - 5, bbox.max_x + 5)
            ax.set_ylim(bbox.min_y - 5, bbox.max_y + 5)
        else:
            center_y = (bbox.min_y + bbox.max_y) / 2
            band = max(bbox.height * 0.08, 0.8)
            keep = np.abs(q[:, 1] - center_y) <= band
            ax.scatter(q[keep, 0], q[keep, 2], c=c[keep], s=3, linewidths=0)
            ax.set_xlim(bbox.min_x - 5, bbox.max_x + 5)
    _draw_footprint(ax, footprint_rings, view, footprint_z)
    ax.set_title(title, fontsize=12, fontweight="bold")
    figure.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(path)
    plt.close(figure)


def _c3_mesh_status_panel(
    path: Path,
    bbox: BBox,
    footprint_rings: Sequence[np.ndarray],
    footprint_z: float,
    view: str,
    roof_point_count: int,
) -> None:
    figure = plt.figure(figsize=(6.4, 4.8), dpi=150)
    if view.startswith("OBLIQUE"):
        ax = figure.add_subplot(111, projection="3d", proj_type="ortho")
        _setup_3d(ax, bbox, (footprint_z, footprint_z + 10.0), view)
    else:
        ax = figure.add_subplot(111)
        if view == "TOP":
            ax.set_aspect("equal")
            ax.set_xlim(bbox.min_x - 5, bbox.max_x + 5)
            ax.set_ylim(bbox.min_y - 5, bbox.max_y + 5)
        else:
            ax.set_xlim(bbox.min_x - 5, bbox.max_x + 5)
            ax.set_ylim(footprint_z, footprint_z + 10.0)
    _draw_footprint(ax, footprint_rings, view, footprint_z)
    text_method = ax.text2D if view.startswith("OBLIQUE") else ax.text
    text_method(
        0.5,
        0.5,
        f"INSUFFICIENT ROOF SEMANTIC EVIDENCE\nselected roof points: {roof_point_count} (<100)\nmesh not generated",
        transform=ax.transAxes,
        ha="center",
        va="center",
        fontsize=13,
        fontweight="bold",
        color="#991b1b",
        bbox={"facecolor": "white", "edgecolor": "#991b1b", "alpha": 0.92, "pad": 10},
    )
    ax.set_title(f"Roof-semantic Poisson mesh | {view}", fontsize=12, fontweight="bold")
    figure.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(path)
    plt.close(figure)


def render_c3(output_root: Path, artifact_root: Path, lod2_path: Path) -> dict[str, Any]:
    config = load_config()
    references = load_building_references(lod2_path, config["scope"]["building_ids"])
    rgb_cfg = config["inputs"]["current_rgb"]
    scene_ref = json.loads((artifact_root / rgb_cfg["scene_reference_relative_path"]).read_text(encoding="utf-8"))
    camera_model = projection.parse_cam_model(artifact_root / rgb_cfg["cameras_relative_path"])
    cameras = projection.parse_cameras(artifact_root / rgb_cfg["images_relative_path"], scene_ref)
    image_root = artifact_root / rgb_cfg["image_directory_relative_path"]
    mesh_recovery = json.loads((output_root / "control/c3_roof_semantic_mesh_recovery_v1.json").read_text(encoding="utf-8"))
    mesh_results = {
        (row["condition_id"], row["stable_id"]): row
        for row in mesh_recovery["results"]
    }
    condition_rows: dict[tuple[str, str], list[tuple[str, Sequence[Path]]]] = {}
    condition_metadata: dict[tuple[str, str], dict[str, Any]] = {}
    raw_by_building: dict[str, Sequence[Path]] = {}
    for condition in config["c3_training_provenance"]["conditions"]:
        condition_id = condition["condition_id"]
        proxy = _read_binary_vertex_ply(output_root / f"c3/{condition_id}/gaussians/display_proxy_gaussian_parameters_v1.ply")
        proxy_xyz = np.column_stack((proxy["x"], proxy["y"], proxy["z"]))
        proxy_quaternions = np.column_stack((proxy["quat_w"], proxy["quat_x"], proxy["quat_y"], proxy["quat_z"]))
        proxy_scales_xy = np.column_stack((proxy["scale_x"], proxy["scale_y"]))
        proxy_opacity = np.asarray(proxy["opacity"], dtype=np.float64)
        proxy_rgb = np.column_stack((proxy["red"], proxy["green"], proxy["blue"])).astype(float) / 255
        proxy_sem = SEMANTIC_COLORS[np.asarray(proxy["semantic_class"], dtype=np.uint8)].astype(float) / 255
        for stable_id, reference in references.items():
            bbox = _bbox(reference)
            footprint_rings = _rings_xy(reference)
            keep = (
                (proxy_xyz[:, 0] >= bbox.min_x - 5) & (proxy_xyz[:, 0] <= bbox.max_x + 5)
                & (proxy_xyz[:, 1] >= bbox.min_y - 5) & (proxy_xyz[:, 1] <= bbox.max_y + 5)
            )
            gaussian_xyz = proxy_xyz[keep]
            gaussian_quaternions = proxy_quaternions[keep]
            gaussian_scales_xy = proxy_scales_xy[keep]
            gaussian_opacity = proxy_opacity[keep]
            gaussian_rgb, gaussian_sem = proxy_rgb[keep], proxy_sem[keep]
            fused_path = output_root / f"c3/{condition_id}/buildings/{stable_id}/rendered_depth_fused_surface_points_v1.ply"
            fused = _read_binary_vertex_ply(fused_path)
            fused_xyz = np.column_stack((fused["x"], fused["y"], fused["z"]))
            fused_sem = SEMANTIC_COLORS[np.asarray(fused["semantic_class"], dtype=np.uint8)].astype(float) / 255
            mesh_result = mesh_results[(condition_id, stable_id)]
            mesh_path = (
                output_root / mesh_result["roof_mesh"]["path"]
                if mesh_result["roof_mesh"] is not None else None
            )
            case_root = output_root / "qualitative/c3/support" / condition_id / stable_id
            c1_points, _c1_surfaces, _footprint_rings, _c1_terminal = _load_method_geometry(
                output_root, CONDITIONS[0], stable_id
            )
            footprint_z = float(np.quantile(c1_points.xyz[:, 2], 0.02))
            roof_reference = roof_ring_vertices(reference.roof_rings_xyz)
            roles = select_current_uas_camera_roles(
                roof_reference,
                c1_points,
                bbox,
                cameras,
                camera_model,
                scene_ref,
                0.5,
                "orthometric",
                "ellipsoidal",
            )
            if stable_id not in raw_by_building:
                raw_paths = []
                for index, (role, scale) in enumerate((("COVERAGE", 3.0), ("NADIR", 2.0), ("NADIR", 1.35), ("OBLIQUE", 2.0))):
                    path = output_root / "qualitative/c3/comparison" / stable_id / "panels" / f"01_rgb_roofline_{index + 1}.png"
                    _raw_roofline_panel(
                        path,
                        image_root / roles[role]["camera"].name,
                        roles[role],
                        reference.roof_rings_xyz,
                        camera_model,
                        scene_ref,
                        crop_scale=scale,
                        title=f"2024 RGB + 2022 LoD2 roofline | {roles[role]['camera'].name}",
                    )
                    raw_paths.append(path)
                raw_by_building[stable_id] = raw_paths
            rows: list[tuple[str, Sequence[Path]]] = []
            for row_name, panel_title, colors in (
                ("2D Gaussian ellipses\nRGB display proxy\n(quat+scale+opacity)", "Gaussian ellipses RGB", gaussian_rgb),
                ("2D Gaussian ellipses\nsemantic display proxy\n(quat+scale+opacity)", "Gaussian ellipses semantic", gaussian_sem),
            ):
                paths = []
                for view in VIEWS:
                    path = case_root / "panels" / f"{len(rows) + 1}_{view.lower()}.png"
                    _c3_gaussian_panel(
                        path,
                        gaussian_xyz,
                        gaussian_quaternions,
                        gaussian_scales_xy,
                        gaussian_opacity,
                        colors,
                        bbox,
                        footprint_rings,
                        footprint_z,
                        view,
                        f"{panel_title} | {view}",
                    )
                    paths.append(path)
                rows.append((row_name, paths))
            fused_paths = []
            for view in VIEWS:
                path = case_root / "panels" / f"4_{view.lower()}.png"
                _c3_point_panel(
                    path,
                    fused_xyz,
                    fused_sem,
                    bbox,
                    footprint_rings,
                    footprint_z,
                    view,
                    f"Rendered-depth fused 3D surface points | {view}",
                )
                fused_paths.append(path)
            rows.append(("Rendered-depth fused\n3D surface points", fused_paths))
            mesh_paths = []
            for view in VIEWS:
                path = case_root / "panels" / f"5_{view.lower()}.png"
                if mesh_path is None:
                    _c3_mesh_status_panel(
                        path,
                        bbox,
                        footprint_rings,
                        footprint_z,
                        view,
                        int(mesh_result["selected_roof_point_count"]),
                    )
                else:
                    _c3_mesh_panel(path, mesh_path, bbox, footprint_rings, footprint_z, view, "Roof-semantic Poisson mesh | " + view)
                mesh_paths.append(path)
            rows.append(("Roof-class-only Poisson mesh\n(class 1; footprint buffer 1 m)", mesh_paths))
            _roofer_points, roofer_surfaces, _roofer_footprint, roofer_terminal = _load_method_geometry(
                output_root, f"{condition_id}_GT_FOOTPRINT_ORACLE", stable_id
            )
            roofer_paths = []
            for view in VIEWS:
                path = case_root / "panels" / f"6_roofer_{view.lower()}.png"
                _panel(
                    path,
                    view=view,
                    bbox=bbox,
                    points=None,
                    surfaces=roofer_surfaces,
                    footprint_rings=footprint_rings,
                    title=(
                        f"GT-footprint oracle Roofer | {view}"
                        if roofer_terminal["status"] == "COMPLETED"
                        else f"Roofer NOT RUN — insufficient roof evidence | {view}"
                    ),
                )
                roofer_paths.append(path)
            rows.append(("GT-footprint oracle Roofer\nroof=C3; terrain=C2 MVS", roofer_paths))
            condition_rows[(condition_id, stable_id)] = rows
            condition_metadata[(condition_id, stable_id)] = {
                "roof_mesh_status": mesh_result["status"],
                "selected_roof_point_count": int(mesh_result["selected_roof_point_count"]),
                "roofer_status": roofer_terminal["status"],
            }
    records = []
    for stable_id, reference in references.items():
        bbox = _bbox(reference)
        footprint_rings = _rings_xy(reference)
        c1_points, _c1_surfaces, _footprint_rings, _c1_terminal = _load_method_geometry(
            output_root, CONDITIONS[0], stable_id
        )
        footprint_z = float(np.quantile(c1_points.xyz[:, 2], 0.02))
        lod2_surfaces = [Surface(np.asarray(ring, dtype=np.float64), semantic) for semantic, ring in reference.surface_rings]
        lod2_paths = []
        case_root = output_root / "qualitative/c3/comparison" / stable_id
        for view in VIEWS:
            path = case_root / "panels" / f"12_lod2_{view.lower()}.png"
            _panel(
                path,
                view=view,
                bbox=bbox,
                points=None,
                surfaces=lod2_surfaces,
                footprint_rings=footprint_rings,
                title=f"2022 LoD2 epoch context only | {view}",
                lod2_context=True,
            )
            lod2_paths.append(path)
        rows = [("2024 RGB + 2022 roofline\nprojection only", raw_by_building[stable_id])]
        for condition_id, short_name in (("C3_1_SEM", "C3-1"), ("C3_2_SEM_DEPTH", "C3-2")):
            for label, paths in condition_rows[(condition_id, stable_id)]:
                rows.append((f"{short_name} {label}", paths))
        rows.append(("2022 LoD2\nepoch context only", lod2_paths))
        sheet = case_root / "case_sheet_c3_1_vs_c3_2_v1.png"
        alignment = "REFERENCE/ID ALIGNMENT REVIEW" if stable_id == "DEBY_LOD2_4907177" else "2022 LoD2 shown as epoch context"
        _compose_sheet(
            sheet,
            rows,
            stable_id,
            f"C3-1 semantic vs C3-2 semantic+depth; GT-footprint oracle Roofer diagnostic | {alignment}; scientific_verdict=null",
        )
        records.append({
            "stable_id": stable_id,
            "case_sheet": file_record(sheet, output_root),
            "panel_count": 48,
            "panels": [file_record(path, output_root) for _label, paths in rows for path in paths],
            "conditions": {
                condition_id: condition_metadata[(condition_id, stable_id)]
                for condition_id in ("C3_1_SEM", "C3_2_SEM_DEPTH")
            },
        })
    body = {
        "schema": "jointbuildgs.c3_3d_qualitative.v1",
        "case_sheet_count": len(records),
        "panel_count": sum(row["panel_count"] for row in records),
        "records": records,
        "roofline_role": "CURRENT_RGB_PROJECTION_CONTEXT_ONLY",
        "footprint_role": "GT_GROUNDSURFACE_XY_DISPLAY_ONLY_ON_ALL_3D_ROWS",
        "gaussian_representation": "ORIENTED_2D_ELLIPSES_FROM_CHECKPOINT_QUATERNION_SCALE_OPACITY_NOT_CENTER_POINTS",
        "mesh_role": "ROOF_SEMANTIC_CLASS_1_WITHIN_GT_GROUNDSURFACE_XY_1M_BUFFER_POISSON_OR_EXPLICIT_INSUFFICIENT_EVIDENCE",
        "roofer_role": "GT_FOOTPRINT_ORACLE_DIAGNOSTIC_C3_ROOF_PLUS_C2_COMMON_MVS_TERRAIN_NOT_OFFICIAL_HONEST_STAGE3",
        "lod2_role": "2022_EPOCH_CONTEXT_ONLY_NOT_TRAINING_OR_EVALUATION",
        "comparison_layout": "ONE_BUILDING_PER_SHEET_C3_1_THEN_C3_2_SHARED_FOUR_VIEWS",
        "roof_mesh_completed_count": int(mesh_recovery["completed_mesh_count"]),
        "roof_mesh_insufficient_evidence_count": int(mesh_recovery["insufficient_evidence_count"]),
        "roofer_completed_count": 4,
        "roofer_pre_failure_count": 2,
        "training_invocations": 0,
        "scientific_verdict": None,
    }
    write_new(output_root / "qualitative/c3/index_v1.json", canonical_json_bytes(body))
    return body


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="mode", required=True)
    c12 = sub.add_parser("c1-c2")
    c12.add_argument("--output-root", type=Path, required=True)
    c12.add_argument("--artifact-root", type=Path, required=True)
    c12.add_argument("--lod2", type=Path, required=True)
    c3 = sub.add_parser("c3")
    c3.add_argument("--output-root", type=Path, required=True)
    c3.add_argument("--artifact-root", type=Path, required=True)
    c3.add_argument("--lod2", type=Path, required=True)
    args = parser.parse_args()
    if args.mode == "c1-c2":
        result = render_c1_c2(args.output_root, args.artifact_root, args.lod2)
    else:
        result = render_c3(args.output_root, args.artifact_root, args.lod2)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
