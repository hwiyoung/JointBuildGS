#!/usr/bin/env python3
"""Render roof-first C3 diagnostic sheets with contextual wall/terrain evidence."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import textwrap
from typing import Any, Mapping, Sequence

import cv2
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.collections import PolyCollection
from mpl_toolkits.mplot3d.art3d import Poly3DCollection
import numpy as np
import open3d as o3d

from scripts.p2.c1_c2_oracle_c3_extract_v1.contract import load_building_references
from scripts.p2.c1_c2_oracle_c3_extract_v1.render_results import _read_binary_vertex_ply
from scripts.p2.c3_tsdf_roof_diagnostic_v1.contract import (
    canonical_json_bytes,
    file_record,
    load_config,
    resolve_artifact,
    validate_config,
    write_new,
)
from src.visualization.fixed_view_qualitative import Surface, load_cityjsonseq


VIEWS = ("TOP", "OBLIQUE_1", "OBLIQUE_2", "PRINCIPAL_SECTION")
CLASS_COLORS = {
    0: np.asarray([0.55, 0.55, 0.55]),
    1: np.asarray([0.90, 0.28, 0.05]),
    2: np.asarray([0.20, 0.48, 0.72]),
    3: np.asarray([0.28, 0.62, 0.43]),
}


def _footprint_rings(reference: Any) -> list[np.ndarray]:
    geometries = [reference.footprint] if reference.footprint.geom_type == "Polygon" else list(reference.footprint.geoms)
    rings = []
    for polygon in geometries:
        rings.append(np.asarray(polygon.exterior.coords, dtype=np.float64))
        rings.extend(np.asarray(interior.coords, dtype=np.float64) for interior in polygon.interiors)
    return rings


def _principal_frame(reference: Any) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    xy = np.asarray(reference.footprint.convex_hull.exterior.coords[:-1], dtype=np.float64)
    center = xy.mean(axis=0)
    _u, _s, vh = np.linalg.svd(xy - center, full_matrices=False)
    axis = vh[0]
    if axis[0] < 0:
        axis = -axis
    cross = np.asarray([-axis[1], axis[0]])
    return center, axis, cross


def _setup_axes(ax: Any, reference: Any, zlim: tuple[float, float], view: str) -> None:
    x0, y0, x1, y1 = reference.footprint.bounds
    pad = max(max(x1 - x0, y1 - y0) * 0.18, 3.0)
    if view == "TOP":
        ax.set_xlim(x0 - pad, x1 + pad)
        ax.set_ylim(y0 - pad, y1 + pad)
        ax.set_aspect("equal")
        ax.set_xlabel("E")
        ax.set_ylabel("N")
    elif view.startswith("OBLIQUE"):
        ax.set_xlim(x0 - pad, x1 + pad)
        ax.set_ylim(y0 - pad, y1 + pad)
        ax.set_zlim(*zlim)
        ax.set_box_aspect((x1 - x0 + 2 * pad, y1 - y0 + 2 * pad, max(zlim[1] - zlim[0], 1)))
        ax.view_init(elev=29 if view == "OBLIQUE_1" else 33, azim=-55 if view == "OBLIQUE_1" else 35)
        ax.set_xlabel("E", fontsize=7)
        ax.set_ylabel("N", fontsize=7)
        ax.set_zlabel("Z", fontsize=7)
    else:
        center, axis, _cross = _principal_frame(reference)
        projected = (np.asarray(reference.footprint.convex_hull.exterior.coords) - center) @ axis
        pad_s = max(np.ptp(projected) * 0.18, 3.0)
        ax.set_xlim(float(np.min(projected) - pad_s), float(np.max(projected) + pad_s))
        ax.set_ylim(*zlim)
        ax.set_xlabel("principal roof axis (m)")
        ax.set_ylabel("Z (m)")


def _draw_footprint(ax: Any, reference: Any, view: str, z: float) -> None:
    center, axis, _cross = _principal_frame(reference)
    for ring in _footprint_rings(reference):
        if view == "TOP":
            ax.plot(ring[:, 0], ring[:, 1], color="#f59e0b", linestyle="--", linewidth=2.2)
        elif view.startswith("OBLIQUE"):
            ax.plot(ring[:, 0], ring[:, 1], np.full(len(ring), z), color="#f59e0b", linestyle="--", linewidth=2.0)
        else:
            s = (ring - center) @ axis
            ax.plot([float(np.min(s)), float(np.max(s))], [z, z], color="#f59e0b", linestyle="--", linewidth=2.0)


def _draw_points(
    ax: Any,
    xyz: np.ndarray,
    colors: np.ndarray,
    reference: Any,
    view: str,
    *,
    roof_mask: np.ndarray | None = None,
    roof_point_size: float = 7.5,
    context_point_size: float = 1.1,
) -> int:
    if not len(xyz):
        return 0
    x0, y0, x1, y1 = reference.footprint.bounds
    pad = 5.0
    keep = (
        (xyz[:, 0] >= x0 - pad) & (xyz[:, 0] <= x1 + pad)
        & (xyz[:, 1] >= y0 - pad) & (xyz[:, 1] <= y1 + pad)
    )
    xyz = xyz[keep]
    colors = colors[keep]
    if roof_mask is not None:
        roof_mask = roof_mask[keep]
    stride = max(1, len(xyz) // 18000)
    xyz, colors = xyz[::stride], colors[::stride]
    if roof_mask is not None:
        roof_mask = roof_mask[::stride]
        sizes = np.where(roof_mask, roof_point_size, context_point_size)
        alpha = np.where(roof_mask, 0.95, 0.18)
    else:
        sizes = np.full(len(xyz), 5.0)
        alpha = np.full(len(xyz), 0.88)
    if view == "TOP":
        for a in np.unique(alpha):
            selected = alpha == a
            ax.scatter(xyz[selected, 0], xyz[selected, 1], c=colors[selected], s=sizes[selected], linewidths=0, alpha=float(a))
    elif view.startswith("OBLIQUE"):
        for a in np.unique(alpha):
            selected = alpha == a
            ax.scatter(xyz[selected, 0], xyz[selected, 1], xyz[selected, 2], c=colors[selected], s=sizes[selected], linewidths=0, alpha=float(a), depthshade=False)
    else:
        center, axis, cross = _principal_frame(reference)
        local = xyz[:, :2] - center
        band = max(min(np.ptp(local @ cross) * 0.08, 1.5), 0.6)
        selected = np.abs(local @ cross) <= band
        s = local[selected] @ axis
        for a in np.unique(alpha[selected]):
            layer = selected.copy()
            layer[selected] = alpha[selected] == a
            local_layer = xyz[layer, :2] - center
            ax.scatter(local_layer @ axis, xyz[layer, 2], c=colors[layer], s=sizes[layer], linewidths=0, alpha=float(a))
    return int(len(xyz))


def _draw_mesh(ax: Any, mesh: o3d.geometry.TriangleMesh, reference: Any, view: str, color: str) -> None:
    vertices = np.asarray(mesh.vertices, dtype=np.float64)
    triangles = np.asarray(mesh.triangles, dtype=np.int64)
    if not len(vertices) or not len(triangles):
        return
    stride = max(1, len(triangles) // 24000)
    faces = vertices[triangles[::stride]]
    if view == "TOP":
        ax.add_collection(PolyCollection(faces[:, :, :2], facecolor=color, edgecolor="#2f3b46", linewidth=0.08, alpha=0.78))
    elif view.startswith("OBLIQUE"):
        ax.add_collection3d(Poly3DCollection(faces, facecolor=color, edgecolor="#2f3b46", linewidth=0.04, alpha=0.80))
    else:
        center, axis, cross = _principal_frame(reference)
        local = vertices[:, :2] - center
        band = max(min(np.ptp(local @ cross) * 0.08, 1.5), 0.6)
        selected = np.abs(local @ cross) <= band
        if np.any(selected):
            ax.scatter(local[selected] @ axis, vertices[selected, 2], s=2.2, color=color, alpha=0.82, linewidths=0)


def _draw_surfaces(ax: Any, surfaces: Sequence[Surface], reference: Any, view: str, lod2: bool = False) -> None:
    center, axis, cross = _principal_frame(reference)
    palette = {"RoofSurface": "#d95f02" if lod2 else "#2563eb", "WallSurface": "#8a8f98", "GroundSurface": "#2f855a"}
    for surface in surfaces:
        ring = surface.xyz
        if not len(ring):
            continue
        color = palette.get(surface.semantic, "#777777")
        closed = np.vstack((ring, ring[0]))
        if view == "TOP":
            ax.plot(closed[:, 0], closed[:, 1], color=color, linewidth=1.4)
        elif view.startswith("OBLIQUE"):
            ax.plot(closed[:, 0], closed[:, 1], closed[:, 2], color=color, linewidth=1.3)
        else:
            local = ring[:, :2] - center
            if np.min(local @ cross) <= 0 <= np.max(local @ cross):
                order = np.argsort(local @ axis)
                ax.plot((local @ axis)[order], ring[order, 2], color=color, linewidth=1.4)


def _panel(
    path: Path,
    *,
    reference: Any,
    view: str,
    zlim: tuple[float, float],
    ground_z: float,
    title: str,
    points: tuple[np.ndarray, np.ndarray, np.ndarray | None] | None = None,
    mesh: o3d.geometry.TriangleMesh | None = None,
    mesh_color: str = "#ca8a04",
    surfaces: Sequence[Surface] = (),
    lod2: bool = False,
    note: str | None = None,
    roof_point_size: float = 7.5,
    context_point_size: float = 1.1,
) -> None:
    figure = plt.figure(figsize=(6.4, 4.8), dpi=150)
    ax = figure.add_subplot(111, projection="3d", proj_type="ortho") if view.startswith("OBLIQUE") else figure.add_subplot(111)
    if points is not None:
        _draw_points(
            ax,
            points[0],
            points[1],
            reference,
            view,
            roof_mask=points[2],
            roof_point_size=roof_point_size,
            context_point_size=context_point_size,
        )
    if mesh is not None:
        _draw_mesh(ax, mesh, reference, view, mesh_color)
    if surfaces:
        _draw_surfaces(ax, surfaces, reference, view, lod2=lod2)
    _draw_footprint(ax, reference, view, ground_z)
    _setup_axes(ax, reference, zlim, view)
    ax.set_title(title, fontsize=12, fontweight="bold")
    if note:
        figure.text(
            0.02,
            0.018,
            textwrap.fill(note, width=115),
            fontsize=7.6,
            color="#222",
            va="bottom",
            bbox={"facecolor": "white", "edgecolor": "#999", "alpha": 0.88, "pad": 3},
        )
        figure.tight_layout(rect=(0.0, 0.105, 1.0, 1.0))
    else:
        figure.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(path, metadata={"Software": "JointBuildGS C3 TSDF roof diagnostic renderer"})
    plt.close(figure)


def _sheet(
    path: Path,
    stable_id: str,
    rows: Sequence[tuple[str, Sequence[Path]]],
    *,
    subtitle: str = "roof-first C3 evidence | same views: Poisson vs TSDF | scientific_verdict=null",
) -> None:
    cell_w, cell_h = 960, 720
    label_w, header_h = 330, 110
    canvas = np.full((header_h + len(rows) * cell_h, label_w + 4 * cell_w, 3), 255, dtype=np.uint8)
    cv2.putText(canvas, stable_id, (24, 45), cv2.FONT_HERSHEY_SIMPLEX, 1.08, (20, 20, 20), 2, cv2.LINE_AA)
    cv2.putText(canvas, subtitle, (24, 88), cv2.FONT_HERSHEY_SIMPLEX, 0.61, (55, 55, 55), 1, cv2.LINE_AA)
    for col, view in enumerate(VIEWS):
        cv2.putText(canvas, view, (label_w + col * cell_w + 24, 84), cv2.FONT_HERSHEY_SIMPLEX, 0.75, (20, 20, 20), 2, cv2.LINE_AA)
    for row_index, (label, paths) in enumerate(rows):
        y0 = header_h + row_index * cell_h
        cv2.rectangle(canvas, (0, y0), (label_w, y0 + cell_h), (242, 244, 247), -1)
        for line_index, line in enumerate(label.split("\n")):
            cv2.putText(canvas, line, (18, y0 + 55 + line_index * 33), cv2.FONT_HERSHEY_SIMPLEX, 0.60, (25, 25, 25), 1, cv2.LINE_AA)
        for col, panel_path in enumerate(paths):
            image = cv2.imread(str(panel_path), cv2.IMREAD_COLOR)
            if image is None:
                raise RuntimeError(f"panel unreadable: {panel_path}")
            image = cv2.resize(image, (cell_w, cell_h), interpolation=cv2.INTER_AREA)
            x0 = label_w + col * cell_w
            canvas[y0:y0 + cell_h, x0:x0 + cell_w] = image
    ok, encoded = cv2.imencode(".png", canvas)
    if not ok:
        raise RuntimeError("case sheet encoding failed")
    write_new(path, encoded.tobytes())


def _condition_data(output_root: Path, v13_root: Path, condition_id: str, stable_id: str) -> dict[str, Any]:
    new_root = output_root / f"conditions/{condition_id}/buildings/{stable_id}"
    result = json.loads((new_root / "result_v1.json").read_text(encoding="utf-8"))
    v13_points = _read_binary_vertex_ply(v13_root / f"c3/{condition_id}/buildings/{stable_id}/rendered_depth_fused_surface_points_v1.ply")
    context_xyz = np.column_stack((v13_points["x"], v13_points["y"], v13_points["z"])).astype(np.float64)
    labels = np.asarray(v13_points["semantic_class"], dtype=np.uint8)
    colors = np.asarray([CLASS_COLORS[int(value)] for value in labels])
    roof_path = new_root / "shared_view_roof_consensus_points_v1.ply"
    if roof_path.is_file():
        roof = _read_binary_vertex_ply(roof_path)
        roof_xyz = np.column_stack((roof["x"], roof["y"], roof["z"])).astype(np.float64)
        view_count = np.asarray(roof["view_count"], dtype=np.float64)
        normalized = (view_count - view_count.min()) / max(np.ptp(view_count), 1.0)
        roof_colors = plt.get_cmap("plasma")(normalized)[:, :3]
        poisson = o3d.io.read_triangle_mesh(str(new_root / "poisson_same_evidence_roof_mesh_v1.ply"))
        tsdf = o3d.io.read_triangle_mesh(str(new_root / "tsdf_roof_mesh_v1.ply"))
    else:
        roof_xyz = np.empty((0, 3), dtype=np.float64)
        roof_colors = np.empty((0, 3), dtype=np.float64)
        poisson = o3d.geometry.TriangleMesh()
        tsdf = o3d.geometry.TriangleMesh()
    operation = v13_root / f"operations/{condition_id}_GT_FOOTPRINT_ORACLE/{stable_id}/work"
    prepared = json.loads((operation / "prepared_v1.json").read_text(encoding="utf-8"))
    if prepared.get("roofer_eligible"):
        terminal = json.loads((operation / "roofer_terminal_v1.json").read_text(encoding="utf-8"))
        roofer = load_cityjsonseq(v13_root / terminal["outputs"][0]["path"])
    else:
        roofer = []
    return {
        "result": result, "context_xyz": context_xyz, "context_labels": labels, "context_colors": colors,
        "roof_xyz": roof_xyz, "roof_colors": roof_colors, "poisson": poisson, "tsdf": tsdf,
        "roofer": roofer,
    }


def run(output_root: Path, artifact_root: Path) -> dict[str, Any]:
    config = load_config()
    validate_config(config)
    complete = json.loads((output_root / "control/five_question_diagnostic_complete_v1.json").read_text(encoding="utf-8"))
    if complete.get("status") != "COMPLETE":
        raise RuntimeError("five-question diagnostics are incomplete")
    v13_root = resolve_artifact(artifact_root, config["source"]["v13_relative_root"], "v13")
    lod2 = resolve_artifact(artifact_root, config["source"]["lod2_relative_path"], "LoD2")
    references = load_building_references(lod2, config["scope"]["building_ids"])
    geoid = float(config["frame"]["lod2_orthometric_to_camera_ellipsoidal_m"])
    records = []
    for stable_id in config["scope"]["building_ids"]:
        reference = references[stable_id]
        ground = float(json.loads((v13_root / f"operations/C2_MVS_GT_FOOTPRINT_ORACLE/{stable_id}/work/prepared_v1.json").read_text(encoding="utf-8"))["classification"]["local_ground_z"])
        condition_data = {
            condition: _condition_data(output_root, v13_root, condition, stable_id)
            for condition in config["scope"]["condition_ids"]
        }
        lod2_surfaces = [Surface(np.asarray(ring, dtype=np.float64) + np.asarray([0, 0, geoid]), semantic) for semantic, ring in reference.surface_rings]
        z_values = [ground]
        for data in condition_data.values():
            if len(data["roof_xyz"]):
                z_values.extend([float(np.min(data["roof_xyz"][:, 2])), float(np.max(data["roof_xyz"][:, 2]))])
        for surface in lod2_surfaces:
            z_values.extend([float(np.min(surface.xyz[:, 2])), float(np.max(surface.xyz[:, 2]))])
        zlim = (min(z_values) - 2.0, max(z_values) + 2.0)
        rows: list[tuple[str, Sequence[Path]]] = []
        rgb_paths = [v13_root / f"qualitative/c3/comparison/{stable_id}/panels/01_rgb_roofline_{index}.png" for index in range(1, 5)]
        rows.append(("2024 RGB + 2022 roofline\nprojection context", rgb_paths))
        case_root = output_root / f"qualitative/roof_first/{stable_id}"
        for condition_id in config["scope"]["condition_ids"]:
            data = condition_data[condition_id]
            row_specs = [
                ("semantic_context", "semantic context | roof emphasized; wall/terrain faint", (data["context_xyz"], data["context_colors"], data["context_labels"] == 1), None, (), "roof orange; non-roof context is deliberately faint"),
                ("roof_consensus", "actual roof evidence | multi-view consensus", (data["roof_xyz"], data["roof_colors"], None), None, (), f"N={len(data['roof_xyz']):,}; color=distinct-view support"),
                ("poisson", "Poisson | same roof depth/cameras", None, data["poisson"], (), "oriented consensus points; no ray/free-space model"),
                ("tsdf", "TSDF | same roof depth/cameras", None, data["tsdf"], (), f"voxel={config['surface']['tsdf_voxel_m']:.2f}m trunc={config['surface']['tsdf_truncation_m']:.2f}m"),
                ("roofer", "inherited GT-footprint oracle Roofer", None, None, data["roofer"], "no rerun; roof evidence only + shared C2 terrain" if data["roofer"] else "NOT RUN: insufficient exact-footprint roof evidence"),
            ]
            for row_key, title, points, mesh, surfaces, note in row_specs:
                paths = []
                for view in VIEWS:
                    path = case_root / f"panels/{condition_id}_{row_key}_{view.lower()}.png"
                    _panel(
                        path, reference=reference, view=view, zlim=zlim, ground_z=ground,
                        title=f"{condition_id} | {title} | {view}", points=points, mesh=mesh,
                        mesh_color="#d5a021" if row_key == "poisson" else "#7c3aed",
                        surfaces=surfaces, note=note,
                    )
                    paths.append(path)
                rows.append((f"{condition_id}\n{row_key.replace('_', ' ')}", paths))
        lod2_paths = []
        for view in VIEWS:
            path = case_root / f"panels/lod2_context_{view.lower()}.png"
            _panel(
                path, reference=reference, view=view, zlim=zlim, ground_z=ground,
                title=f"2022 LoD2 +45.7m display datum | {view}", surfaces=lod2_surfaces,
                lod2=True, note="epoch context only; not current accuracy GT",
            )
            lod2_paths.append(path)
        rows.append(("2022 LoD2 context\n+45.7m display datum", lod2_paths))
        sheet = case_root / "case_sheet_roof_first_poisson_tsdf_v1.png"
        _sheet(sheet, stable_id, rows)
        panels = [path for _label, paths in rows[1:] for path in paths]
        records.append({
            "stable_id": stable_id,
            "case_sheet": file_record(sheet, output_root),
            "panel_count": len(panels),
            "panels": [file_record(path, output_root) for path in panels],
        })
    body = {
        "schema": "jointbuildgs.c3_roof_first_poisson_tsdf_qualitative.v1",
        "status": "COMPLETE",
        "case_sheet_count": len(records),
        "panel_count": sum(row["panel_count"] for row in records),
        "rows_per_sheet": 12,
        "view_count_per_row": 4,
        "roof_display_role": "PRIMARY_EVIDENCE",
        "wall_ground_display_role": "FAINT_CONTEXT_WITH_GAUSSIAN_SCALE_DIAGNOSTICS_SEPARATE",
        "records": records,
        "scientific_verdict": None,
    }
    write_new(output_root / "qualitative/index_v1.json", canonical_json_bytes(body))
    return body


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--artifact-root", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.output_root, args.artifact_root), ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
