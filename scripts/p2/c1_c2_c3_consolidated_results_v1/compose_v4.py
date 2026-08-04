#!/usr/bin/env python3
"""Add LoD2-scaled PCA sections and comparable C1/C2 Roofer mesh displays."""
from __future__ import annotations

import argparse
import html
import json
import shutil
from datetime import datetime, timezone
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
import trimesh

from scripts.p2.c1_c2_c3_consolidated_results_v1.compose import build_pdf, canonical_json_bytes, record, write_new
from scripts.p2.c1_c2_oracle_c3_extract_v1.contract import load_building_references
from scripts.p2.c3_tsdf_roof_diagnostic_v1.render import _footprint_rings, _principal_frame
from src.visualization.fixed_view_qualitative import Surface, load_cityjsonseq, load_las_points


REPO_ROOT = Path(__file__).resolve().parents[3]
CONFIG_PATH = REPO_ROOT / "configs/p2/c1_c2_c3_consolidated_results_v1/compose_v4.json"
VIEWS = ("TOP", "OBLIQUE_1", "OBLIQUE_2", "PRINCIPAL_SECTION")
CONDITIONS = ("C3_1_SEM", "C3_2_SEM_DEPTH")


def load_config() -> dict[str, Any]:
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def validate_config(config: Mapping[str, Any]) -> None:
    if config.get("schema") != "jointbuildgs.p2.c1_c2_c3_consolidated_results.v4":
        raise RuntimeError("unexpected v4 schema")
    if config.get("status") != "APPROVED_FOR_LOCAL_PRESENTATION_CORRECTION_ONLY":
        raise RuntimeError("v4 presentation correction is not active")
    if tuple(config["views"]) != VIEWS or tuple(config["condition_ids"]) != CONDITIONS:
        raise RuntimeError("scope drifted")
    if config["display"]["principal_frame"] != "FOOTPRINT_PCA":
        raise RuntimeError("principal frame must be footprint PCA")
    if any(int(value) != 0 for value in config["execution_counters"].values()):
        raise RuntimeError("all scientific execution counters must remain zero")
    if config.get("scientific_verdict", "missing") is not None:
        raise RuntimeError("scientific_verdict must remain null")


def roots(artifact_root: Path, config: Mapping[str, Any]) -> dict[str, Path]:
    resolved = {key: artifact_root / value for key, value in config["sources"].items()}
    for key, path in resolved.items():
        if not path.exists():
            raise RuntimeError(f"missing source {key}: {path}")
    return resolved


def shifted_lod2(reference: Any, dz: float) -> list[Surface]:
    offset = np.asarray([0.0, 0.0, dz])
    return [Surface(np.asarray(ring, dtype=np.float64) + offset, semantic) for semantic, ring in reference.surface_rings]


def lod2_zlim(surfaces: Sequence[Surface]) -> tuple[float, float]:
    xyz = np.concatenate([surface.xyz for surface in surfaces if len(surface.xyz)])
    lo, hi = float(xyz[:, 2].min()), float(xyz[:, 2].max())
    pad = max(2.0, 0.08 * (hi - lo))
    return lo - pad, hi + pad


def geometry_paths(v13: Path, recovery: Path, stable_id: str) -> dict[str, Path | None]:
    c1_work = recovery / f"operations/C1_LIDAR_LOD2_GROUND_Z_ORACLE/{stable_id}/work" if stable_id.endswith("4907177") else v13 / f"operations/C1_LIDAR_GT_FOOTPRINT_ORACLE/{stable_id}/work"
    c2_work = v13 / f"operations/C2_MVS_GT_FOOTPRINT_ORACLE/{stable_id}/work"

    def city(work: Path) -> Path | None:
        candidates = sorted((work / "out").glob("*.city.jsonl"))
        return candidates[0] if candidates else None

    return {"c1_las": c1_work / "input.las", "c1_city": city(c1_work), "c2_las": c2_work / "input.las", "c2_city": city(c2_work)}


def c3_city(v13: Path, condition: str, stable_id: str) -> Path | None:
    work = v13 / f"operations/{condition}_GT_FOOTPRINT_ORACLE/{stable_id}/work"
    terminal_path = work / "roofer_terminal_v1.json"
    if not terminal_path.is_file():
        return None
    terminal = json.loads(terminal_path.read_text(encoding="utf-8"))
    if terminal.get("status") != "COMPLETED" or len(terminal.get("outputs") or ()) != 1:
        return None
    path = v13 / terminal["outputs"][0]["path"]
    return path if path.is_file() else None


def common_axes(ax: Any, reference: Any, zlim: tuple[float, float], view: str) -> None:
    x0, y0, x1, y1 = map(float, reference.footprint.bounds)
    pad = max(max(x1 - x0, y1 - y0) * 0.20, 3.0)
    if view == "TOP":
        ax.set_xlim(x0 - pad, x1 + pad); ax.set_ylim(y0 - pad, y1 + pad); ax.set_aspect("equal")
        ax.set_xlabel("Easting"); ax.set_ylabel("Northing")
    elif view.startswith("OBLIQUE"):
        ax.set_xlim(x0 - pad, x1 + pad); ax.set_ylim(y0 - pad, y1 + pad); ax.set_zlim(*zlim)
        ax.set_box_aspect((x1 - x0 + 2 * pad, y1 - y0 + 2 * pad, max(zlim[1] - zlim[0], 1.0)))
        ax.view_init(elev=29 if view == "OBLIQUE_1" else 33, azim=-55 if view == "OBLIQUE_1" else 35)
        ax.set_xlabel("E", fontsize=7); ax.set_ylabel("N", fontsize=7); ax.set_zlabel("Z", fontsize=7)
    else:
        center, axis, _cross = _principal_frame(reference)
        projected = (np.asarray(reference.footprint.convex_hull.exterior.coords) - center) @ axis
        pad_s = max(float(np.ptp(projected)) * 0.18, 3.0)
        ax.set_xlim(float(projected.min() - pad_s), float(projected.max() + pad_s)); ax.set_ylim(*zlim)
        ax.set_xlabel("PCA principal roof axis (m)"); ax.set_ylabel("Z (m)")
        ax.grid(True, color="#dddddd", linewidth=0.6)


def draw_footprint(ax: Any, reference: Any, view: str, ground_z: float) -> None:
    center, axis, _cross = _principal_frame(reference)
    for ring in _footprint_rings(reference):
        if view == "TOP":
            ax.plot(ring[:, 0], ring[:, 1], color="#f59e0b", linestyle="--", linewidth=2.0)
        elif view.startswith("OBLIQUE"):
            ax.plot(ring[:, 0], ring[:, 1], np.full(len(ring), ground_z), color="#f59e0b", linestyle="--", linewidth=1.8)
        else:
            s = (ring - center) @ axis
            ax.plot([float(s.min()), float(s.max())], [ground_z, ground_z], color="#f59e0b", linestyle="--", linewidth=1.8)


def ring_section_segment(xyz: np.ndarray, reference: Any) -> np.ndarray | None:
    center, axis, cross = _principal_frame(reference)
    local = xyz[:, :2] - center
    s, t, z = local @ axis, local @ cross, xyz[:, 2]
    points: list[np.ndarray] = []
    for first, second in zip(range(len(xyz)), list(range(1, len(xyz))) + [0]):
        t0, t1 = float(t[first]), float(t[second])
        if abs(t0) < 1e-9:
            points.append(np.asarray([s[first], z[first]]))
        if t0 * t1 < 0.0 or abs(t1) < 1e-9:
            denom = t1 - t0
            if abs(denom) > 1e-12:
                fraction = -t0 / denom
                if 0.0 <= fraction <= 1.0:
                    points.append(np.asarray([s[first] + fraction * (s[second] - s[first]), z[first] + fraction * (z[second] - z[first])]))
    unique: list[np.ndarray] = []
    for point in points:
        if not any(np.linalg.norm(point - other) < 1e-6 for other in unique):
            unique.append(point)
    if len(unique) < 2:
        return None
    values = np.asarray(unique)
    distances = np.linalg.norm(values[:, None] - values[None, :], axis=2)
    first, second = np.unravel_index(int(np.argmax(distances)), distances.shape)
    return np.vstack((values[first], values[second]))


def semantic_color(semantic: str, *, plane: bool) -> str:
    if semantic == "RoofSurface": return "#5b8fd1" if not plane else "#2563eb"
    if semantic == "WallSurface": return "#b9bec5"
    if semantic == "GroundSurface": return "#79a86b"
    return "#9ca3af"


def surface_triangles(surfaces: Sequence[Surface]) -> tuple[list[np.ndarray], list[str]]:
    faces: list[np.ndarray] = []
    colors: list[str] = []
    for surface in surfaces:
        ring = np.asarray(surface.xyz, dtype=np.float64)
        if len(ring) < 3: continue
        for index in range(1, len(ring) - 1):
            faces.append(np.vstack((ring[0], ring[index], ring[index + 1])))
            colors.append(semantic_color(surface.semantic, plane=False))
    return faces, colors


def draw_surfaces(ax: Any, surfaces: Sequence[Surface], reference: Any, view: str, *, mesh: bool) -> None:
    if mesh and view != "PRINCIPAL_SECTION":
        faces, colors = surface_triangles(surfaces)
        if view == "TOP":
            ax.add_collection(PolyCollection([face[:, :2] for face in faces], facecolors=colors, edgecolors="#34495e", linewidths=0.38, alpha=0.90))
        else:
            ax.add_collection3d(Poly3DCollection(faces, facecolors=colors, edgecolors="#34495e", linewidths=0.32, alpha=0.90))
        return
    for surface in surfaces:
        segment = ring_section_segment(np.asarray(surface.xyz, dtype=np.float64), reference) if view == "PRINCIPAL_SECTION" else None
        color = semantic_color(surface.semantic, plane=not mesh)
        if view == "PRINCIPAL_SECTION":
            if segment is not None:
                ax.plot(segment[:, 0], segment[:, 1], color=color, linewidth=3.3 if surface.semantic == "RoofSurface" else 1.5)
        else:
            ring = np.asarray(surface.xyz, dtype=np.float64); closed = np.vstack((ring, ring[0]))
            if view == "TOP": ax.plot(closed[:, 0], closed[:, 1], color=color, linewidth=1.7)
            else: ax.plot(closed[:, 0], closed[:, 1], closed[:, 2], color=color, linewidth=1.5)


def render_surface_panel(path: Path, surfaces: Sequence[Surface], reference: Any, view: str, zlim: tuple[float, float], title: str, *, mesh: bool, unavailable: str | None = None) -> None:
    fig = plt.figure(figsize=(6.4, 4.8), dpi=150)
    ax = fig.add_subplot(111, projection="3d", proj_type="ortho") if view.startswith("OBLIQUE") else fig.add_subplot(111)
    ground = zlim[0] + 2.0
    if surfaces: draw_surfaces(ax, surfaces, reference, view, mesh=mesh)
    draw_footprint(ax, reference, view, ground); common_axes(ax, reference, zlim, view)
    if not surfaces:
        method = ax.text2D if view.startswith("OBLIQUE") else ax.text
        method(0.5, 0.5, unavailable or "NOT AVAILABLE", transform=ax.transAxes, ha="center", va="center", fontsize=12, fontweight="bold", color="#991b1b", bbox={"facecolor":"white","edgecolor":"#991b1b","alpha":0.9,"pad":7})
    ax.set_title(title, fontsize=10.5, fontweight="bold")
    fig.tight_layout(); path.parent.mkdir(parents=True, exist_ok=True); fig.savefig(path); plt.close(fig)


def render_point_panel(path: Path, las_path: Path, reference: Any, view: str, zlim: tuple[float, float], title: str) -> dict[str, int]:
    point_set = load_las_points(las_path); xyz = np.asarray(point_set.xyz); classes = np.asarray(point_set.classification)
    x0, y0, x1, y1 = reference.footprint.bounds
    keep = (xyz[:, 0] >= x0 - 5) & (xyz[:, 0] <= x1 + 5) & (xyz[:, 1] >= y0 - 5) & (xyz[:, 1] <= y1 + 5)
    xyz, classes = xyz[keep], classes[keep]; stride = max(1, len(xyz) // 18000); xyz, classes = xyz[::stride], classes[::stride]
    colors = np.where(classes[:, None] == 6, np.asarray([[0.0, 0.72, 0.88]]), np.asarray([[0.86, 0.22, 0.78]]))
    fig = plt.figure(figsize=(6.4, 4.8), dpi=150); ax = fig.add_subplot(111, projection="3d", proj_type="ortho") if view.startswith("OBLIQUE") else fig.add_subplot(111)
    if view == "TOP": ax.scatter(xyz[:, 0], xyz[:, 1], c=colors, s=2.0, linewidths=0)
    elif view.startswith("OBLIQUE"): ax.scatter(xyz[:, 0], xyz[:, 1], xyz[:, 2], c=colors, s=1.7, linewidths=0, depthshade=False)
    else:
        center, axis, cross = _principal_frame(reference); local = xyz[:, :2] - center
        band = max(min(float(np.ptp(local @ cross)) * 0.08, 1.5), 0.6); selected = np.abs(local @ cross) <= band
        ax.scatter(local[selected] @ axis, xyz[selected, 2], c=colors[selected], s=3.0, linewidths=0)
    draw_footprint(ax, reference, view, zlim[0] + 2.0); common_axes(ax, reference, zlim, view); ax.set_title(title, fontsize=10.5, fontweight="bold")
    fig.tight_layout(); path.parent.mkdir(parents=True, exist_ok=True); fig.savefig(path); plt.close(fig)
    return {"class6_count": int(np.count_nonzero(point_set.classification == 6)), "class2_count": int(np.count_nonzero(point_set.classification == 2))}


def render_mesh_section(path: Path, mesh_path: Path | None, reference: Any, zlim: tuple[float, float], title: str, color: str, unavailable: str = "N/A") -> None:
    fig, ax = plt.subplots(figsize=(6.4, 4.8), dpi=150)
    if mesh_path is not None and mesh_path.is_file():
        mesh = o3d.io.read_triangle_mesh(str(mesh_path)); vertices = np.asarray(mesh.vertices); triangles = np.asarray(mesh.triangles)
        if len(vertices) and len(triangles):
            center, axis, cross = _principal_frame(reference)
            tm = trimesh.Trimesh(vertices=vertices, faces=triangles, process=False)
            segments = trimesh.intersections.mesh_plane(tm, plane_normal=np.asarray([cross[0], cross[1], 0.0]), plane_origin=np.asarray([center[0], center[1], 0.0]))
            if len(segments):
                projected = (segments[:, :, :2] - center) @ axis
                for s, z in zip(projected, segments[:, :, 2]): ax.plot(s, z, color=color, linewidth=1.0, alpha=0.78)
    else:
        ax.text(0.5, 0.5, unavailable, transform=ax.transAxes, ha="center", va="center", fontsize=13, fontweight="bold", color="#991b1b")
    draw_footprint(ax, reference, "PRINCIPAL_SECTION", zlim[0] + 2.0); common_axes(ax, reference, zlim, "PRINCIPAL_SECTION"); ax.set_title(title, fontsize=10.5, fontweight="bold")
    fig.tight_layout(); path.parent.mkdir(parents=True, exist_ok=True); fig.savefig(path); plt.close(fig)


def render_consensus_section(path: Path, ply: Path, reference: Any, zlim: tuple[float, float], title: str) -> None:
    cloud = o3d.io.read_point_cloud(str(ply)); xyz = np.asarray(cloud.points); center, axis, cross = _principal_frame(reference); local = xyz[:, :2] - center
    band = max(min(float(np.ptp(local @ cross)) * 0.08, 1.5), 0.6); keep = np.abs(local @ cross) <= band
    fig, ax = plt.subplots(figsize=(6.4, 4.8), dpi=150); ax.scatter(local[keep] @ axis, xyz[keep, 2], s=3.0, color="#7c3aed", alpha=0.85, linewidths=0)
    draw_footprint(ax, reference, "PRINCIPAL_SECTION", zlim[0] + 2.0); common_axes(ax, reference, zlim, "PRINCIPAL_SECTION"); ax.set_title(title, fontsize=10.5, fontweight="bold")
    fig.tight_layout(); path.parent.mkdir(parents=True, exist_ok=True); fig.savefig(path); plt.close(fig)


def compose_grid(path: Path, stable_id: str, columns: Sequence[str], rows: Sequence[tuple[str, Sequence[Path]]], subtitle: str) -> None:
    cell_w, cell_h, label_w, header_h = 960, 720, 520, 170
    canvas = np.full((header_h + len(rows) * cell_h, label_w + len(columns) * cell_w, 3), 255, dtype=np.uint8)
    cv2.putText(canvas, stable_id, (22, 45), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (20,20,20), 2, cv2.LINE_AA)
    cv2.putText(canvas, subtitle, (22, 90), cv2.FONT_HERSHEY_SIMPLEX, 0.58, (45,45,45), 1, cv2.LINE_AA)
    cv2.putText(canvas, "ALL SECTION PANELS: same footprint-PCA cut + same LoD2-derived Z limits", (22, 132), cv2.FONT_HERSHEY_SIMPLEX, 0.56, (128,45,20), 1, cv2.LINE_AA)
    for index, label in enumerate(columns): cv2.putText(canvas, label, (label_w + index * cell_w + 22, 118), cv2.FONT_HERSHEY_SIMPLEX, 0.72, (25,25,25), 2, cv2.LINE_AA)
    for row_index, (label, panels) in enumerate(rows):
        y0 = header_h + row_index * cell_h; cv2.rectangle(canvas, (0,y0), (label_w-1,y0+cell_h-1), (245,247,249), -1)
        for line_index, line in enumerate(label.split("\n")): cv2.putText(canvas, line, (20,y0+65+line_index*36), cv2.FONT_HERSHEY_SIMPLEX, 0.62, (25,25,25), 1, cv2.LINE_AA)
        for column, panel in enumerate(panels):
            image = cv2.imread(str(panel), cv2.IMREAD_COLOR)
            if image is None: raise RuntimeError(f"unreadable panel: {panel}")
            image = cv2.resize(image, (cell_w,cell_h), interpolation=cv2.INTER_AREA); x0 = label_w + column * cell_w; canvas[y0:y0+cell_h,x0:x0+cell_w] = image
    path.parent.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(str(path), canvas, [cv2.IMWRITE_PNG_COMPRESSION,5]): raise RuntimeError(f"failed to write grid: {path}")


def render_locator(path: Path, reference: Any) -> None:
    center, axis, cross = _principal_frame(reference); rings = _footprint_rings(reference); x0,y0,x1,y1 = reference.footprint.bounds; length=max(x1-x0,y1-y0)
    fig, ax = plt.subplots(figsize=(7.2,2.4), dpi=150)
    for ring in rings: ax.plot(ring[:,0],ring[:,1],color="#333333",linewidth=1.8)
    p0,p1=center-axis*length,center+axis*length; ax.plot([p0[0],p1[0]],[p0[1],p1[1]],color="#d62728",linewidth=2.6,label="canonical PCA cut")
    look=center+cross*0.30*length; ax.annotate("LOOK",xy=look,xytext=center,arrowprops={"arrowstyle":"->","color":"#d62728","lw":2},color="#d62728")
    pad=max(length*0.12,2); ax.set_xlim(x0-pad,x1+pad);ax.set_ylim(y0-pad,y1+pad);ax.set_aspect("equal");ax.set_xlabel("E");ax.set_ylabel("N");ax.legend(fontsize=8);ax.set_title("Canonical principal section locator",fontsize=11,fontweight="bold")
    fig.tight_layout();path.parent.mkdir(parents=True,exist_ok=True);fig.savefig(path);plt.close(fig)


def prepend_locator(page: Path, locator: Path, notes: Sequence[str]) -> None:
    image=cv2.imread(str(page)); loc=cv2.imread(str(locator)); strip=390; canvas=np.full((image.shape[0]+strip,image.shape[1],3),255,dtype=np.uint8)
    canvas[15:375,20:1520]=cv2.resize(loc,(1500,360),interpolation=cv2.INTER_AREA)
    for index,line in enumerate(notes): cv2.putText(canvas,line,(1570,80+index*48),cv2.FONT_HERSHEY_SIMPLEX,0.68,(32,32,32),2,cv2.LINE_AA)
    canvas[strip:]=image
    if not cv2.imwrite(str(page),canvas,[cv2.IMWRITE_PNG_COMPRESSION,5]): raise RuntimeError("locator prepend failed")


def c1c2_page(path: Path, stable_id: str, raw: Sequence[Path], rows: Sequence[tuple[str, Sequence[Path]]]) -> None:
    compose_grid(path, stable_id, ["TOP","OBLIQUE_1","OBLIQUE_2","PRINCIPAL_SECTION"], [("2024 RGB + 2022 roofline\n(camera views; 4th is not section)",raw),*rows], "C1/C2 latest sealed inputs and Roofer outputs | plane model + same-output surface mesh")


def run(output_root: Path, artifact_root: Path, source_base_commit: str) -> dict[str, Any]:
    config=load_config();validate_config(config)
    if output_root.exists() and any(output_root.iterdir()): raise RuntimeError("add-once v4 namespace is not empty")
    output_root.mkdir(parents=True,exist_ok=True); source=roots(artifact_root,config); v3=source["v3_relative_root"];v13=source["v13_relative_root"];recovery=source["c1_4907177_recovery_relative_root"];diagnostic=source["diagnostic_relative_root"]
    references=load_building_references(source["lod2_relative_path"],config["building_ids"]); dz=float(config["display"]["lod2_orthometric_to_camera_ellipsoidal_m"])
    pages=[];page_records=[];lineage=[];z_records=[];display_triangle_count=0
    for stable_id in config["building_ids"]:
        reference=references[stable_id];lod2=shifted_lod2(reference,dz);zlim=lod2_zlim(lod2);z_records.append({"stable_id":stable_id,"z_min":zlim[0],"z_max":zlim[1],"source":"2022 LoD2 all semantic surfaces +45.7m; 2m padding"})
        paths=geometry_paths(v13,recovery,stable_id); case=output_root/f"qualitative/c1_c2/{stable_id}";raw_root=v13/f"qualitative/c1_c2/{stable_id}/panels";raw=[raw_root/f"raw_{index}.png" for index in range(1,5)]
        c1_surfaces=load_cityjsonseq(paths["c1_city"]) if paths["c1_city"] else [];c2_surfaces=load_cityjsonseq(paths["c2_city"]) if paths["c2_city"] else []
        panel_rows=[]
        for method,las,surfaces in (("C1",paths["c1_las"],c1_surfaces),("C2",paths["c2_las"],c2_surfaces)):
            inputs=[];planes=[];meshes=[]
            for view in VIEWS:
                p=case/f"panels/{method}_INPUT__{view}.png";render_point_panel(p,las,reference,view,zlim,f"{method} sealed input | {view}");inputs.append(p)
                p=case/f"panels/{method}_PLANES__{view}.png";render_surface_panel(p,surfaces,reference,view,zlim,f"{method} Roofer plane model | {view}",mesh=False,unavailable="NOT RUN");planes.append(p)
                p=case/f"panels/{method}_MESH__{view}.png";render_surface_panel(p,surfaces,reference,view,zlim,f"{method} Roofer CityJSON surface mesh | {view}",mesh=True,unavailable="NOT RUN\nno Roofer output");meshes.append(p)
            panel_rows.extend([(f"{method} INPUT\nsealed LAS",inputs),(f"{method} ROOFER OUTPUT\nplane model",planes),(f"{method} ROOFER OUTPUT MESH\nsame CityJSON; display triangulation",meshes)])
            display_triangle_count += sum(max(len(surface.xyz)-2,0) for surface in surfaces)
        page=output_root/f"pages/{len(pages)+1:02d}_{stable_id}_C1_C2_LOD2_SCALE_MESH.png";c1c2_page(page,stable_id,raw,panel_rows)
        locator=output_root/f"qualitative/section_locators/{stable_id}_canonical_pca.png";render_locator(locator,reference);prepend_locator(page,locator,[f"COMMON Z: {zlim[0]:.2f} to {zlim[1]:.2f} m", "derived from shifted LoD2 (+45.7 m)", "mesh rows are display triangulations of same Roofer output"])
        pages.append(page);page_records.append({"page":len(pages),"stable_id":stable_id,"section":"C1_C2_LOD2_SCALE_WITH_MESH","output":record(page,output_root)})
        for condition in CONDITIONS:
            old_number={"DEBY_LOD2_4907177":2,"DEBY_LOD2_4906975":5,"DEBY_LOD2_108580336":8}[stable_id]+(1 if condition=="C3_2_SEM_DEPTH" else 0)
            source_page=v3/f"pages/{old_number:02d}_{stable_id}_{condition}.png";page=output_root/f"pages/{len(pages)+1:02d}_{stable_id}_{condition}_CONTEXT.png";page.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source_page,page)
            pages.append(page);page_records.append({"page":len(pages),"stable_id":stable_id,"section":condition,"output":record(page,output_root),"height_comparison_role":"CONTEXT_ONLY_USE_COMMON_SECTION_PAGE"})
        columns=["C1 LiDAR","C2 MVS","C3-1 semantic","C3-2 semantic+depth"]
        section_root=output_root/f"qualitative/common_section/{stable_id}/panels";evidence=[];roofer=[];poisson=[];tsdf=[];lod2_panels=[]
        for method,las in (("C1",paths["c1_las"]),("C2",paths["c2_las"])):
            p=section_root/f"{method}_evidence.png";render_point_panel(p,las,reference,"PRINCIPAL_SECTION",zlim,f"{method} input evidence | common PCA section");evidence.append(p)
        for condition in CONDITIONS:
            ply=diagnostic/f"conditions/{condition}/buildings/{stable_id}/shared_view_roof_consensus_points_v1.ply";p=section_root/f"{condition}_evidence.png";render_consensus_section(p,ply,reference,zlim,f"{condition} roof consensus | common PCA section");evidence.append(p)
        city_sources=[paths["c1_city"],paths["c2_city"],c3_city(v13,CONDITIONS[0],stable_id),c3_city(v13,CONDITIONS[1],stable_id)]
        for index,(label,city_path) in enumerate(zip(columns,city_sources)):
            surfaces=load_cityjsonseq(city_path) if city_path else [];p=section_root/f"roofer_mesh_{index}.png";render_surface_panel(p,surfaces,reference,"PRINCIPAL_SECTION",zlim,f"{label} Roofer mesh section",mesh=True,unavailable="NOT RUN\nno Roofer output");roofer.append(p)
            if city_path: lineage.append({"stable_id":stable_id,"role":f"{label}_ROOFER_CITYJSON","source":record(city_path,artifact_root)})
        for row_name,color in (("poisson","#ca8a04"),("tsdf","#7c3aed")):
            row=[]
            for method in ("C1","C2"):
                p=section_root/f"{row_name}_{method}_na.png";render_mesh_section(p,None,reference,zlim,f"{method}: no {row_name} branch",color,"N/A\nnot part of baseline");row.append(p)
            for condition in CONDITIONS:
                mesh_name="poisson_same_evidence_roof_mesh_v1.ply" if row_name=="poisson" else "tsdf_roof_mesh_v1.ply";mesh_path=diagnostic/f"conditions/{condition}/buildings/{stable_id}/{mesh_name}";p=section_root/f"{row_name}_{condition}.png";render_mesh_section(p,mesh_path,reference,zlim,f"{condition} {row_name.upper()} | common PCA section",color);row.append(p);lineage.append({"stable_id":stable_id,"role":f"{condition}_{row_name.upper()}_MESH","source":record(mesh_path,artifact_root)})
            (poisson if row_name=="poisson" else tsdf).extend(row)
        for index,label in enumerate(columns):
            p=section_root/f"lod2_{index}.png";render_surface_panel(p,lod2,reference,"PRINCIPAL_SECTION",zlim,f"2022 LoD2 reference | same scale",mesh=False);lod2_panels.append(p)
        compare=output_root/f"pages/{len(pages)+1:02d}_{stable_id}_COMMON_PCA_SECTION.png";compose_grid(compare,stable_id,columns,[("Input / roof evidence",evidence),("Roofer output surface mesh",roofer),("Poisson roof mesh",poisson),("TSDF roof mesh",tsdf),("2022 LoD2 reference\n+45.7m display datum",lod2_panels)],f"Canonical principal-section comparison | fixed Z={zlim[0]:.2f}..{zlim[1]:.2f} m")
        prepend_locator(compare,locator,["ONE CUT: footprint PCA axis",f"ONE Z SCALE: {zlim[0]:.2f}..{zlim[1]:.2f} m","C1/C2 mesh=same Roofer CityJSON output","C3 Poisson/TSDF=roof consensus branch"])
        pages.append(compare);page_records.append({"page":len(pages),"stable_id":stable_id,"section":"COMMON_PCA_PRINCIPAL_SECTION","output":record(compare,output_root),"zlim":list(zlim)})
    pdf=output_root/"reports/C1_C2_C3_qualitative_results_v4_lod2_scaled_sections_and_baseline_mesh.pdf";build_pdf(pages,pdf)
    index={"schema":"jointbuildgs.c1_c2_c3_consolidated_results_index.v4","status":"COMPLETE_LOD2_SCALED_PCA_SECTION_AND_C1_C2_MESH_DISPLAY","generated_at":datetime.now(timezone.utc).isoformat().replace("+00:00","Z"),"source_base_commit":source_base_commit,"case_count":3,"page_count":len(pages),"c1_c2_page_count":3,"c3_context_page_count":6,"common_section_page_count":3,"common_section_panel_count":60,"c1_c2_cityjson_mesh_role":config["display"]["cityjson_mesh_role"],"presentation_only_cityjson_triangle_count":display_triangle_count,"z_scale_records":z_records,"pages":page_records,"source_lineage":lineage,"execution_counters":config["execution_counters"],"official_G3_G4_PASS_usable":None,"scientific_verdict":None,"pdf":record(pdf,output_root)}
    write_new(output_root/"qualitative/index_v4.json",canonical_json_bytes(index))
    report="""# C1/C2/C3 통합 정성 결과판 v4\n\n건물별 principal section 비교를 footprint PCA 절단면 하나로 통일하고, Z축 범위를 2022 LoD2 전 semantic surface에 +45.7 m display datum을 적용한 최소·최대와 상하 2 m padding으로 고정했다. 기존 C3 context page의 inherited section은 문맥 확인용이며 수치 높이 비교는 새 COMMON PCA SECTION page에서 수행한다.\n\nC1/C2에는 plane model과 별도로 같은 봉인 Roofer CityJSON surface를 display-only로 삼각분할한 mesh 행을 추가했다. 이는 새로운 meshing이나 reconstruction 결과가 아니라 동일 Roofer output의 surface-mesh 표현이다. 공통 section page는 C1, C2, C3-1, C3-2를 열로 두고 input/evidence, Roofer surface mesh, Poisson, TSDF, LoD2를 같은 절단면과 Z축으로 배열한다. C1/C2에는 Poisson/TSDF branch가 없으므로 N/A다.\n\nGS 학습, checkpoint extraction, Poisson, TSDF, Roofer, G2, metric 재계산, C4/C5 access는 모두 0회다. scientific_verdict와 official G3/G4/PASS_usable은 null이다.\n"""
    write_new(output_root/"reports/technical_report_ko_v4.md",report.encode("utf-8"));links="".join(f'<section><h2>{html.escape(row["stable_id"])} — {html.escape(row["section"])}</h2><img src="../{html.escape(row["output"]["path"])}"></section>' for row in page_records);write_new(output_root/"reports/case_index.html",("<!doctype html><meta charset=utf-8><style>body{font-family:sans-serif;max-width:1800px;margin:auto}img{width:100%;margin-bottom:3rem}</style><h1>C1/C2/C3 v4</h1>"+links).encode())
    checks={"case_count_3":index["case_count"]==3,"page_count_12":index["page_count"]==12,"c1_c2_pages_3":index["c1_c2_page_count"]==3,"c3_context_pages_6":index["c3_context_page_count"]==6,"common_section_pages_3":index["common_section_page_count"]==3,"common_section_panels_60":index["common_section_panel_count"]==60,"all_z_scales_lod2_derived":len(z_records)==3 and all(row["z_max"]>row["z_min"] for row in z_records),"all_execution_counters_zero":all(value==0 for value in config["execution_counters"].values()),"scientific_verdict_null":index["scientific_verdict"] is None}
    if not all(checks.values()):raise RuntimeError(f"v4 verification failed: {checks}")
    write_new(output_root/"control/200-verified.local_v4.json",canonical_json_bytes({"schema":"jointbuildgs.local_technical_200_verified.v4","status":"200-VERIFIED_LOCAL_SELF_CHECK","checks":checks,"scientific_verdict":None}));write_new(output_root/"control/technical_return_v4.json",canonical_json_bytes({"schema":"jointbuildgs.local_technical_return.v4","status":"RETURNED_LOCAL_LOD2_SCALED_SECTIONS_AND_BASELINE_MESH","pdf":record(pdf,output_root),"execution_counters":config["execution_counters"],"scientific_verdict":None}))
    material=[p for p in sorted(output_root.rglob("*")) if p.is_file() and p.name not in {"artifact_manifest_v4.json","300-closed.local_v4.json"}];manifest={"schema":"jointbuildgs.c1_c2_c3_consolidated_results_manifest.v4","status":"COMPLETE_HASHED_MATERIAL_PAYLOAD","records":[record(p,output_root) for p in material],"scientific_verdict":None};manifest["record_count"]=len(manifest["records"]);write_new(output_root/"control/artifact_manifest_v4.json",canonical_json_bytes(manifest));closed={"schema":"jointbuildgs.local_technical_300_closed.v4","status":"300-CLOSED_LOCAL_LOD2_SCALED_SECTIONS_AND_BASELINE_MESH","verified":record(output_root/"control/200-verified.local_v4.json",output_root),"technical_return":record(output_root/"control/technical_return_v4.json",output_root),"manifest":record(output_root/"control/artifact_manifest_v4.json",output_root),"scientific_verdict":None};write_new(output_root/"control/300-closed.local_v4.json",canonical_json_bytes(closed));return closed


def main() -> None:
    parser=argparse.ArgumentParser();parser.add_argument("--output-root",type=Path,required=True);parser.add_argument("--artifact-root",type=Path,required=True);parser.add_argument("--source-base-commit",required=True);args=parser.parse_args();print(json.dumps(run(args.output_root,args.artifact_root,args.source_base_commit),ensure_ascii=False,sort_keys=True))


if __name__=="__main__":main()
