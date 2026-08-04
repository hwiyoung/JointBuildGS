#!/usr/bin/env python3
"""Build the nine-page v5 presentation and texture sealed C2 Roofer surfaces."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import html
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

from scripts.p2.c1_c2_c3_consolidated_results_v1.compose import (
    build_pdf,
    canonical_json_bytes,
    record,
    write_new,
)
from scripts.p2.c1_c2_c3_consolidated_results_v1.compose_v4 import (
    c3_city,
    common_axes,
    geometry_paths,
    lod2_zlim,
    ring_section_segment,
    shifted_lod2,
)
from scripts.p2.c1_c2_oracle_c3_extract_v1.contract import load_building_references
from scripts.p2.c3_tsdf_roof_diagnostic_v1.render import _footprint_rings, _principal_frame
from src.stage2.dataloader import ColmapDataset
from src.visualization.fixed_view_qualitative import Surface, load_cityjsonseq, load_las_points


REPO_ROOT = Path(__file__).resolve().parents[3]
CONFIG_PATH = REPO_ROOT / "configs/p2/c1_c2_c3_consolidated_results_v1/compose_v5.json"
VIEWS = ("TOP", "OBLIQUE_1", "OBLIQUE_2", "PRINCIPAL_SECTION")
CONDITIONS = ("C3_1_SEM", "C3_2_SEM_DEPTH")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_config() -> dict[str, Any]:
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def validate_config(config: Mapping[str, Any]) -> None:
    if config.get("schema") != "jointbuildgs.p2.c1_c2_c3_consolidated_results.v5":
        raise RuntimeError("unexpected v5 schema")
    if tuple(config["views"]) != VIEWS or tuple(config["condition_ids"]) != CONDITIONS:
        raise RuntimeError("presentation scope drifted")
    display = config["display"]
    if display["principal_frame"] != "FOOTPRINT_PCA_SINGLE_CANONICAL_SECTION":
        raise RuntimeError("v5 requires one footprint-PCA section")
    if display["legacy_blue_red_dual_section_visible"]:
        raise RuntimeError("legacy dual section must be hidden")
    if int(display["separate_principal_section_page_count"]) != 0:
        raise RuntimeError("separate principal-section pages are prohibited")
    for key, value in config["execution_counters"].items():
        expected = 3 if key == "c2_display_texture_bakes" else 0
        if int(value) != expected:
            raise RuntimeError(f"unexpected execution counter {key}={value}")
    if config.get("scientific_verdict", "missing") is not None:
        raise RuntimeError("scientific_verdict must remain null")
    if config.get("official_G3_G4_PASS_usable", "missing") is not None:
        raise RuntimeError("official PASS_usable must remain null")


def source_roots(artifact_root: Path, config: Mapping[str, Any]) -> dict[str, Path]:
    resolved = {key: artifact_root / value for key, value in config["sources"].items() if not key.endswith("git_path")}
    for key, path in resolved.items():
        if not path.exists():
            raise RuntimeError(f"missing source {key}: {path}")
    sealed = resolved["sealed_v4_relative_root"]
    expected = config["exact_source_hashes"]
    checks = {
        "sealed_v4_closure": sealed / "control/300-closed.local_v4.json",
        "sealed_v4_manifest": sealed / "control/artifact_manifest_v4.json",
        "sealed_v4_pdf": sealed / "reports/C1_C2_C3_qualitative_results_v4_lod2_scaled_sections_and_baseline_mesh.pdf",
    }
    for label, path in checks.items():
        actual = sha256(path)
        if actual != expected[label]:
            raise RuntimeError(f"sealed v4 hash drift for {label}: {actual}")
    return resolved


def visible_names(config: Mapping[str, Any]) -> list[str]:
    manifest_path = REPO_ROOT / config["sources"]["exact_view_manifest_git_path"]
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    names = [str(row["basename"]) for row in manifest["rows"]]
    if len(names) != 937:
        raise RuntimeError(f"exact common-base membership drifted: {len(names)}")
    return names


def draw_section_locator(ax: Any, reference: Any) -> None:
    """Draw the only canonical section directly on a coordinate-aware TOP panel."""
    center, axis, cross = _principal_frame(reference)
    ring = np.asarray(reference.footprint.convex_hull.exterior.coords, dtype=np.float64)
    local = ring - center
    half = max(float(np.max(np.abs(local @ axis))) * 1.18, 3.0)
    width = max(float(np.ptp(local @ cross)) * 0.055, 0.55)
    a, b = center - axis * half, center + axis * half
    polygon = np.vstack((a - cross * width, b - cross * width, b + cross * width, a + cross * width))
    ax.add_patch(plt.Polygon(polygon, closed=True, facecolor="#fbbf24", edgecolor="#111827", linewidth=2.8, alpha=0.48, zorder=20))
    ax.plot([a[0], b[0]], [a[1], b[1]], color="#111827", linewidth=4.5, zorder=21)
    ax.text(a[0], a[1], "A", fontsize=16, fontweight="bold", ha="right", va="bottom", color="#111827", zorder=22)
    ax.text(b[0], b[1], "B", fontsize=16, fontweight="bold", ha="left", va="top", color="#111827", zorder=22)
    start = center + cross * max(float(np.ptp(local @ cross)) * 0.48, 4.0)
    end = center + cross * max(float(np.ptp(local @ cross)) * 0.12, 1.0)
    ax.annotate("VIEW", xy=end, xytext=start, fontsize=15, fontweight="bold", ha="center", va="center", color="#111827", arrowprops={"arrowstyle": "-|>", "color": "#111827", "lw": 4.0}, zorder=23)


def draw_footprint(ax: Any, reference: Any, view: str, ground_z: float) -> None:
    center, axis, _ = _principal_frame(reference)
    for ring in _footprint_rings(reference):
        if view == "TOP":
            ax.plot(ring[:, 0], ring[:, 1], color="#f59e0b", linestyle="--", linewidth=2.4)
        elif view.startswith("OBLIQUE"):
            ax.plot(ring[:, 0], ring[:, 1], np.full(len(ring), ground_z), color="#f59e0b", linestyle="--", linewidth=2.0)
        else:
            s = (ring - center) @ axis
            ax.plot([float(s.min()), float(s.max())], [ground_z, ground_z], color="#f59e0b", linestyle="--", linewidth=2.0)


def panel_axes(reference: Any, zlim: tuple[float, float], view: str) -> tuple[Any, Any]:
    fig = plt.figure(figsize=(6.4, 4.8), dpi=150)
    ax = fig.add_subplot(111, projection="3d", proj_type="ortho") if view.startswith("OBLIQUE") else fig.add_subplot(111)
    common_axes(ax, reference, zlim, view)
    ax.tick_params(labelsize=8)
    return fig, ax


def save_panel(fig: Any, path: Path) -> None:
    fig.tight_layout(pad=1.0)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path)
    plt.close(fig)


def point_panel(path: Path, xyz: np.ndarray, colors: np.ndarray, reference: Any, view: str, zlim: tuple[float, float]) -> None:
    fig, ax = panel_axes(reference, zlim, view)
    x0, y0, x1, y1 = reference.footprint.bounds
    keep = (xyz[:, 0] >= x0 - 5) & (xyz[:, 0] <= x1 + 5) & (xyz[:, 1] >= y0 - 5) & (xyz[:, 1] <= y1 + 5)
    xyz, colors = xyz[keep], colors[keep]
    stride = max(1, len(xyz) // 22000)
    xyz, colors = xyz[::stride], colors[::stride]
    if view == "TOP":
        ax.scatter(xyz[:, 0], xyz[:, 1], c=colors, s=2.2, linewidths=0)
        draw_section_locator(ax, reference)
    elif view.startswith("OBLIQUE"):
        ax.scatter(xyz[:, 0], xyz[:, 1], xyz[:, 2], c=colors, s=1.8, linewidths=0, depthshade=False)
    else:
        center, axis, cross = _principal_frame(reference)
        local = xyz[:, :2] - center
        width = max(min(float(np.ptp(local @ cross)) * 0.08, 1.5), 0.6)
        section = np.abs(local @ cross) <= width
        ax.scatter(local[section] @ axis, xyz[section, 2], c=colors[section], s=3.2, linewidths=0)
    draw_footprint(ax, reference, view, zlim[0] + 2.0)
    save_panel(fig, path)


def las_panels(root: Path, las_path: Path, reference: Any, zlim: tuple[float, float], prefix: str) -> list[Path]:
    points = load_las_points(las_path)
    xyz = np.asarray(points.xyz)
    classes = np.asarray(points.classification)
    colors = np.where(classes[:, None] == 6, np.asarray([[0.0, 0.62, 0.82]]), np.asarray([[0.78, 0.28, 0.68]]))
    result = []
    for view in VIEWS:
        path = root / f"{prefix}_{view}.png"
        point_panel(path, xyz, colors, reference, view, zlim)
        result.append(path)
    return result


def surface_faces(surfaces: Sequence[Surface]) -> tuple[list[np.ndarray], list[str]]:
    faces: list[np.ndarray] = []
    semantics: list[str] = []
    for surface in surfaces:
        ring = np.asarray(surface.xyz, dtype=np.float64)
        for index in range(1, len(ring) - 1):
            faces.append(np.vstack((ring[0], ring[index], ring[index + 1])))
            semantics.append(surface.semantic)
    return faces, semantics


def semantic_rgb(semantic: str) -> tuple[float, float, float]:
    return {"RoofSurface": (0.18, 0.46, 0.76), "WallSurface": (0.67, 0.70, 0.73), "GroundSurface": (0.42, 0.62, 0.37)}.get(semantic, (0.55, 0.58, 0.62))


def triangle_panel(path: Path, faces: Sequence[np.ndarray], face_colors: Sequence[Sequence[float]], reference: Any, view: str, zlim: tuple[float, float]) -> None:
    fig, ax = panel_axes(reference, zlim, view)
    if view == "TOP":
        ax.add_collection(PolyCollection([face[:, :2] for face in faces], facecolors=face_colors, edgecolors="#374151", linewidths=0.35))
        draw_section_locator(ax, reference)
    elif view.startswith("OBLIQUE"):
        ax.add_collection3d(Poly3DCollection(faces, facecolors=face_colors, edgecolors="#374151", linewidths=0.30))
    else:
        for face, color in zip(faces, face_colors):
            segment = ring_section_segment(face, reference)
            if segment is not None:
                ax.plot(segment[:, 0], segment[:, 1], color=color, linewidth=2.8)
    draw_footprint(ax, reference, view, zlim[0] + 2.0)
    save_panel(fig, path)


def surface_panels(root: Path, surfaces: Sequence[Surface], reference: Any, zlim: tuple[float, float], prefix: str, face_colors: Sequence[Sequence[float]] | None = None) -> list[Path]:
    faces, semantics = surface_faces(surfaces)
    colors = list(face_colors) if face_colors is not None else [semantic_rgb(item) for item in semantics]
    result = []
    for view in VIEWS:
        path = root / f"{prefix}_{view}.png"
        triangle_panel(path, faces, colors, reference, view, zlim)
        result.append(path)
    return result


def mesh_panels(root: Path, mesh_path: Path, reference: Any, zlim: tuple[float, float], prefix: str, color: tuple[float, float, float]) -> list[Path]:
    mesh = o3d.io.read_triangle_mesh(str(mesh_path))
    vertices = np.asarray(mesh.vertices, dtype=np.float64)
    triangles = np.asarray(mesh.triangles, dtype=np.int64)
    faces = [vertices[row] for row in triangles]
    colors = [color] * len(faces)
    result = []
    for view in VIEWS:
        path = root / f"{prefix}_{view}.png"
        triangle_panel(path, faces, colors, reference, view, zlim)
        result.append(path)
    return result


def consensus_panels(root: Path, ply: Path, reference: Any, zlim: tuple[float, float], prefix: str) -> list[Path]:
    cloud = o3d.io.read_point_cloud(str(ply))
    xyz = np.asarray(cloud.points)
    colors = np.tile(np.asarray([[0.49, 0.25, 0.77]]), (len(xyz), 1))
    result = []
    for view in VIEWS:
        path = root / f"{prefix}_{view}.png"
        point_panel(path, xyz, colors, reference, view, zlim)
        result.append(path)
    return result


def project_triangle(triangle: np.ndarray, frame: Any, sample: Mapping[str, Any], shift: np.ndarray) -> dict[str, Any]:
    local = triangle - shift
    k = sample["K"].numpy().astype(np.float64)
    w2c = sample["w2c"].numpy().astype(np.float64)
    camera = local @ w2c[:3, :3].T + w2c[:3, 3]
    front = camera[:, 2] > 0.1
    uvw = camera @ k.T
    uv = np.full((3, 2), -1.0, dtype=np.float64)
    uv[front] = uvw[front, :2] / uvw[front, 2:3]
    rgb = sample["rgb"].numpy()
    height, width = rgb.shape[:2]
    inside = front & (uv[:, 0] >= 0) & (uv[:, 0] < width - 1) & (uv[:, 1] >= 0) & (uv[:, 1] < height - 1)
    center_local = local.mean(axis=0)
    center_camera = center_local @ w2c[:3, :3].T + w2c[:3, 3]
    center_uvw = center_camera @ k.T
    center_uv = center_uvw[:2] / max(center_uvw[2], 1e-12)
    center_inside = center_camera[2] > 0.1 and 0 <= center_uv[0] < width - 1 and 0 <= center_uv[1] < height - 1
    normal = np.cross(triangle[1] - triangle[0], triangle[2] - triangle[0])
    normal /= max(np.linalg.norm(normal), 1e-12)
    camera_center = -w2c[:3, :3].T @ w2c[:3, 3]
    view = camera_center - center_local
    view /= max(np.linalg.norm(view), 1e-12)
    incidence = float(abs(np.dot(normal, view)))
    depth_available = False
    depth_consistent = False
    depth_residual = None
    if center_inside and "depth" in sample:
        x, y = int(round(center_uv[0])), int(round(center_uv[1]))
        mask = sample["depth_mask"].numpy()
        if bool(mask[y, x]):
            depth_available = True
            depth_residual = float(abs(float(sample["depth"].numpy()[y, x]) - center_camera[2]))
            depth_consistent = depth_residual <= 1.25
    return {
        "name": str(frame.name),
        "uv": uv,
        "center_uv": center_uv,
        "vertex_coverage_fraction": float(np.mean(inside)),
        "center_inside": bool(center_inside),
        "incidence_cosine": incidence,
        "depth_available": depth_available,
        "depth_consistent": depth_consistent,
        "depth_residual_m": depth_residual,
        "sample": sample,
    }


def texture_c2(
    output_root: Path,
    stable_id: str,
    surfaces: Sequence[Surface],
    frames: Sequence[tuple[Any, Mapping[str, Any]]],
    config: Mapping[str, Any],
) -> tuple[list[tuple[float, float, float]], dict[str, Any]]:
    faces, semantics = surface_faces(surfaces)
    cell = int(config["texture"]["atlas_cell_px"])
    columns = max(1, int(math.ceil(math.sqrt(len(faces)))))
    maximum = int(config["texture"]["atlas_max_px"])
    if columns * cell > maximum:
        cell = max(24, maximum // columns)
    rows = max(1, int(math.ceil(len(faces) / columns)))
    atlas = np.full((rows * cell, columns * cell, 3), 128, dtype=np.uint8)
    shift = np.asarray(config["texture"]["world_shift_xyz"], dtype=np.float64)
    minimum_incidence = float(config["texture"]["minimum_incidence_cosine"])
    receipt_rows: list[dict[str, Any]] = []
    colors: list[tuple[float, float, float]] = []
    obj_vertices: list[np.ndarray] = []
    obj_uv: list[np.ndarray] = []
    obj_faces: list[tuple[int, int, int]] = []
    margin = max(2, cell // 12)
    destination_local = np.asarray([[margin, margin], [cell - margin - 1, margin], [margin, cell - margin - 1]], dtype=np.float32)
    if not faces:
        receipt_rows.append({
            "schema": "jointbuildgs.c2_roofer_face_texture_camera_coverage.v1",
            "stable_id": stable_id,
            "face_id": None,
            "status": "NOT_RUN_NO_SEALED_C2_ROOFER_OUTPUT",
            "selected_camera": None,
            "candidate_camera_count": 0,
            "official_metric_input": False,
            "scientific_verdict": None,
        })
    for face_index, (triangle, semantic) in enumerate(zip(faces, semantics)):
        candidates = [project_triangle(triangle, frame, sample, shift) for frame, sample in frames]
        candidates = [row for row in candidates if row["center_inside"] and row["vertex_coverage_fraction"] >= 2.0 / 3.0 and row["incidence_cosine"] >= minimum_incidence]
        candidates = [row for row in candidates if not row["depth_available"] or row["depth_consistent"]]
        for row in candidates:
            row["score"] = row["incidence_cosine"] * (0.5 + 0.5 * row["vertex_coverage_fraction"]) * (1.2 if row["depth_consistent"] else 1.0)
        selected = max(candidates, key=lambda row: row["score"]) if candidates else None
        grid_x, grid_y = (face_index % columns) * cell, (face_index // columns) * cell
        destination = destination_local + np.asarray([grid_x, grid_y], dtype=np.float32)
        if selected is not None:
            rgb = selected["sample"]["rgb"].numpy()
            source_bgr = cv2.cvtColor(np.rint(np.clip(rgb, 0, 1) * 255).astype(np.uint8), cv2.COLOR_RGB2BGR)
            matrix = cv2.getAffineTransform(selected["uv"].astype(np.float32), destination)
            warped = cv2.warpAffine(source_bgr, matrix, (atlas.shape[1], atlas.shape[0]), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT)
            mask = np.zeros(atlas.shape[:2], dtype=np.uint8)
            cv2.fillConvexPoly(mask, np.rint(destination).astype(np.int32), 255)
            atlas[mask > 0] = warped[mask > 0]
            sample_mask = mask[grid_y:grid_y + cell, grid_x:grid_x + cell] > 0
            sample_pixels = atlas[grid_y:grid_y + cell, grid_x:grid_x + cell][sample_mask]
            mean_bgr = sample_pixels.mean(axis=0) if len(sample_pixels) else np.asarray([128, 128, 128])
            color = tuple((mean_bgr[::-1] / 255.0).tolist())
            status = "TEXTURED_CURRENT_RGB"
        else:
            color = semantic_rgb(semantic)
            status = "UNOBSERVED_NEUTRAL_DISPLAY_COLOR"
        colors.append(color)
        base = len(obj_vertices) + 1
        obj_vertices.extend(triangle)
        uv = destination / np.asarray([atlas.shape[1] - 1, atlas.shape[0] - 1], dtype=np.float64)
        uv[:, 1] = 1.0 - uv[:, 1]
        obj_uv.extend(uv)
        obj_faces.append((base, base + 1, base + 2))
        receipt_rows.append({
            "schema": "jointbuildgs.c2_roofer_face_texture_camera_coverage.v1",
            "stable_id": stable_id,
            "face_id": f"C2_ROOFER_FACE_{face_index:04d}",
            "semantic": semantic,
            "status": status,
            "selected_camera": None if selected is None else selected["name"],
            "vertex_coverage_fraction": 0.0 if selected is None else selected["vertex_coverage_fraction"],
            "incidence_cosine": None if selected is None else selected["incidence_cosine"],
            "mvs_depth_available": False if selected is None else selected["depth_available"],
            "mvs_depth_consistent": False if selected is None else selected["depth_consistent"],
            "mvs_depth_residual_m": None if selected is None else selected["depth_residual_m"],
            "candidate_camera_count": len(candidates),
            "official_metric_input": False,
            "scientific_verdict": None,
        })
    texture_root = output_root / f"textures/c2_roofer/{stable_id}"
    texture_root.mkdir(parents=True, exist_ok=True)
    atlas_path = texture_root / "c2_roofer_2024_rgb_atlas.png"
    if not cv2.imwrite(str(atlas_path), atlas, [cv2.IMWRITE_PNG_COMPRESSION, 5]):
        raise RuntimeError(f"failed atlas write: {atlas_path}")
    mtl_path = texture_root / "c2_roofer_2024_rgb.mtl"
    write_new(mtl_path, b"newmtl c2_roofer_2024_rgb\nKd 1 1 1\nmap_Kd c2_roofer_2024_rgb_atlas.png\n")
    lines = [f"mtllib {mtl_path.name}", "usemtl c2_roofer_2024_rgb"]
    lines.extend(f"v {x:.9f} {y:.9f} {z:.9f}" for x, y, z in obj_vertices)
    lines.extend(f"vt {u:.9f} {v:.9f}" for u, v in obj_uv)
    lines.extend(f"f {a}/{a} {b}/{b} {c}/{c}" for a, b, c in obj_faces)
    obj_path = texture_root / "c2_roofer_2024_rgb_textured.obj"
    write_new(obj_path, ("\n".join(lines) + "\n").encode("ascii"))
    receipt_path = texture_root / "face_texture_camera_coverage_v1.jsonl"
    write_new(receipt_path, b"".join((json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8") for row in receipt_rows))
    observed = sum(row["status"] == "TEXTURED_CURRENT_RGB" for row in receipt_rows)
    summary = {
        "stable_id": stable_id,
        "source_status": "SEALED_C2_ROOFER_OUTPUT_AVAILABLE" if faces else "NOT_RUN_NO_SEALED_C2_ROOFER_OUTPUT",
        "face_count": len(faces),
        "geometric_face_count": len(faces),
        "receipt_record_count": len(receipt_rows),
        "current_rgb_textured_face_count": observed,
        "unobserved_face_count": len(faces) - observed,
        "current_rgb_textured_face_fraction": observed / max(len(faces), 1),
        "atlas": record(atlas_path, output_root),
        "obj": record(obj_path, output_root),
        "mtl": record(mtl_path, output_root),
        "face_receipt": record(receipt_path, output_root),
        "official_metric_input": False,
        "scientific_verdict": None,
    }
    return colors, summary


def compose_page(path: Path, stable_id: str, page_label: str, rows: Sequence[tuple[str, Sequence[Path]]], zlim: tuple[float, float]) -> None:
    cell_w, cell_h, label_w, header_h = 960, 720, 430, 270
    canvas = np.full((header_h + len(rows) * cell_h, label_w + 4 * cell_w, 3), 255, dtype=np.uint8)
    cv2.putText(canvas, stable_id, (28, 58), cv2.FONT_HERSHEY_SIMPLEX, 1.35, (18, 18, 18), 3, cv2.LINE_AA)
    cv2.putText(canvas, page_label, (28, 116), cv2.FONT_HERSHEY_SIMPLEX, 1.20, (35, 35, 35), 3, cv2.LINE_AA)
    cv2.putText(canvas, f"ONE PCA CUT | LoD2 common Z {zlim[0]:.1f}..{zlim[1]:.1f} m", (28, 174), cv2.FONT_HERSHEY_SIMPLEX, 1.05, (92, 55, 12), 2, cv2.LINE_AA)
    for index, label in enumerate(("TOP + A/B VIEW", "OBLIQUE 1", "OBLIQUE 2", "PCA SECTION")):
        cv2.putText(canvas, label, (label_w + index * cell_w + 26, 242), cv2.FONT_HERSHEY_SIMPLEX, 1.05, (20, 20, 20), 2, cv2.LINE_AA)
    for row_index, (label, panels) in enumerate(rows):
        if len(panels) != 4:
            raise RuntimeError(f"row does not have four views: {label}")
        y0 = header_h + row_index * cell_h
        cv2.rectangle(canvas, (0, y0), (label_w - 1, y0 + cell_h - 1), (242, 244, 247), -1)
        parts = label.split("\n")
        for line_index, line in enumerate(parts):
            cv2.putText(canvas, line, (24, y0 + 90 + 58 * line_index), cv2.FONT_HERSHEY_SIMPLEX, 1.12, (24, 24, 24), 3, cv2.LINE_AA)
        for column, panel in enumerate(panels):
            image = cv2.imread(str(panel), cv2.IMREAD_COLOR)
            if image is None:
                raise RuntimeError(f"unreadable panel: {panel}")
            image = cv2.resize(image, (cell_w, cell_h), interpolation=cv2.INTER_AREA)
            x0 = label_w + column * cell_w
            canvas[y0:y0 + cell_h, x0:x0 + cell_w] = image
    path.parent.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(str(path), canvas, [cv2.IMWRITE_PNG_COMPRESSION, 5]):
        raise RuntimeError(f"failed page write: {path}")


def run(output_root: Path, artifact_root: Path, source_commit: str) -> dict[str, Any]:
    config = load_config()
    validate_config(config)
    if output_root.exists() and any(output_root.iterdir()):
        raise RuntimeError("add-once v5 namespace is not empty")
    output_root.mkdir(parents=True, exist_ok=True)
    source = source_roots(artifact_root, config)
    v13 = source["v13_relative_root"]
    recovery = source["c1_4907177_recovery_relative_root"]
    diagnostic = source["diagnostic_relative_root"]
    references = load_building_references(source["lod2_relative_path"], config["building_ids"])
    view_plan = json.loads(source["shared_view_plan_relative_path"].read_text(encoding="utf-8"))["plan"]
    visible = visible_names(config)
    dataset = ColmapDataset(
        source["colmap_relative_root"],
        downscale=float(config["texture"]["image_downscale"]),
        load_depth=True,
        load_normal=False,
        load_semantic=False,
        visible_views=visible,
    )
    frame_by_name = {frame.name: (index, frame) for index, frame in enumerate(dataset.frames)}
    dz = float(config["display"]["lod2_orthometric_to_camera_ellipsoidal_m"])
    pages: list[Path] = []
    page_records: list[dict[str, Any]] = []
    texture_summaries: list[dict[str, Any]] = []
    z_records: list[dict[str, Any]] = []
    source_lineage: list[dict[str, Any]] = []
    for stable_id in config["building_ids"]:
        reference = references[stable_id]
        lod2 = shifted_lod2(reference, dz)
        zlim = lod2_zlim(lod2)
        z_records.append({"stable_id": stable_id, "zlim_m": list(zlim), "source": "2022 LoD2 all semantic surfaces +45.7m; 2m padding"})
        paths = geometry_paths(v13, recovery, stable_id)
        c1_surfaces = load_cityjsonseq(paths["c1_city"]) if paths["c1_city"] else []
        c2_surfaces = load_cityjsonseq(paths["c2_city"]) if paths["c2_city"] else []
        planned = view_plan[stable_id][: int(config["texture"]["maximum_views_per_building"])]
        frames = [(frame_by_name[row["name"]][1], dataset[frame_by_name[row["name"]][0]]) for row in planned]
        c2_colors, texture_summary = texture_c2(output_root, stable_id, c2_surfaces, frames, config)
        texture_summaries.append(texture_summary)
        c1c2_root = output_root / f"qualitative/{stable_id}/c1_c2/panels"
        c1_input = las_panels(c1c2_root, paths["c1_las"], reference, zlim, "c1_input")
        c1_roofer = surface_panels(c1c2_root, c1_surfaces, reference, zlim, "c1_roofer")
        c2_input = las_panels(c1c2_root, paths["c2_las"], reference, zlim, "c2_input")
        c2_roofer = surface_panels(c1c2_root, c2_surfaces, reference, zlim, "c2_roofer_textured", c2_colors)
        page = output_root / f"pages/{len(pages) + 1:02d}_{stable_id}_C1_C2.png"
        compose_page(page, stable_id, "C1 / C2 SEALED", [("C1\nLiDAR", c1_input), ("C1\nRoofer", c1_roofer), ("C2\nMVS", c2_input), ("C2 Roofer\n2024 RGB", c2_roofer)], zlim)
        pages.append(page)
        page_records.append({"page": len(pages), "stable_id": stable_id, "condition": "C1_C2", "output": record(page, output_root), "principal_column_zlim_m": list(zlim)})
        for role, source_path in (("C1_CITYJSON", paths["c1_city"]), ("C2_CITYJSON", paths["c2_city"])):
            if source_path:
                source_lineage.append({"stable_id": stable_id, "role": role, "source": record(source_path, artifact_root)})
        for condition in CONDITIONS:
            panel_root = output_root / f"qualitative/{stable_id}/{condition}/panels"
            consensus = diagnostic / f"conditions/{condition}/buildings/{stable_id}/shared_view_roof_consensus_points_v1.ply"
            poisson = diagnostic / f"conditions/{condition}/buildings/{stable_id}/poisson_same_evidence_roof_mesh_v1.ply"
            tsdf = diagnostic / f"conditions/{condition}/buildings/{stable_id}/tsdf_roof_mesh_v1.ply"
            city_path = c3_city(v13, condition, stable_id)
            city_surfaces = load_cityjsonseq(city_path) if city_path else []
            rows = [
                ("RGB-derived\nevidence", consensus_panels(panel_root, consensus, reference, zlim, "evidence")),
                ("Roofer\nCityJSON", surface_panels(panel_root, city_surfaces, reference, zlim, "roofer")),
                ("Poisson\nroof", mesh_panels(panel_root, poisson, reference, zlim, "poisson", (0.80, 0.54, 0.10))),
                ("TSDF\nroof", mesh_panels(panel_root, tsdf, reference, zlim, "tsdf", (0.49, 0.25, 0.77))),
                ("2022 LoD2\nreference", surface_panels(panel_root, lod2, reference, zlim, "lod2")),
            ]
            page = output_root / f"pages/{len(pages) + 1:02d}_{stable_id}_{condition}.png"
            compose_page(page, stable_id, condition.replace("_", " "), rows, zlim)
            pages.append(page)
            page_records.append({"page": len(pages), "stable_id": stable_id, "condition": condition, "output": record(page, output_root), "principal_column_zlim_m": list(zlim)})
            for role, path in (("CONSENSUS", consensus), ("POISSON", poisson), ("TSDF", tsdf), ("ROOFER_CITYJSON", city_path)):
                if path:
                    source_lineage.append({"stable_id": stable_id, "condition": condition, "role": role, "source": record(path, artifact_root)})
    pdf = output_root / "reports/C1_C2_C3_qualitative_results_v5_single_pca_section_c2_rgb_texture.pdf"
    build_pdf(pages, pdf)
    index = {
        "schema": "jointbuildgs.c1_c2_c3_consolidated_results_index.v5",
        "status": "COMPLETE_SINGLE_PCA_SECTION_AND_C2_CURRENT_RGB_TEXTURE",
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "source_commit": source_commit,
        "case_count": 3,
        "page_count": len(pages),
        "c1_c2_page_count": 3,
        "c3_page_count": 6,
        "separate_principal_section_page_count": 0,
        "legacy_blue_red_dual_section_visible": False,
        "all_top_panels_include_section_band_ab_view": True,
        "all_principal_columns_use_lod2_common_z": True,
        "minimum_page_text_px": int(config["display"]["minimum_page_text_px"]),
        "c2_texture_bake_count": len(texture_summaries),
        "c2_texture_summaries": texture_summaries,
        "z_scale_records": z_records,
        "pages": page_records,
        "source_lineage": source_lineage,
        "execution_counters": config["execution_counters"],
        "official_G3_G4_PASS_usable": None,
        "scientific_verdict": None,
        "pdf": record(pdf, output_root),
    }
    write_new(output_root / "qualitative/index_v5.json", canonical_json_bytes(index))
    links = "".join(f'<section><h2>{html.escape(row["stable_id"])} — {html.escape(row["condition"])}</h2><a href="../{html.escape(row["output"]["path"])}"><img src="../{html.escape(row["output"]["path"])}"></a></section>' for row in page_records)
    write_new(output_root / "reports/case_index.html", ("<!doctype html><meta charset=utf-8><style>body{font-family:sans-serif;max-width:1800px;margin:auto}img{width:100%;margin-bottom:4rem}</style><h1>C1/C2/C3 presentation v5</h1>" + links).encode("utf-8"))
    report = """# C1/C2/C3 presentation v5 기술 Return

v5는 3개 사례마다 C1/C2 한 페이지와 C3-1, C3-2 각 한 페이지만 생성해 총 9페이지다. 별도 principal-section 페이지는 없다. 모든 TOP 패널에 동일 footprint-PCA 절단 band, A/B, VIEW 화살표를 직접 표시했고, 모든 페이지의 네 번째 열은 해당 건물의 2022 LoD2(+45.7 m)에서 얻은 동일 Z 범위로 다시 렌더했다. legacy blue/red dual section은 표시하지 않았다.

C2의 봉인 Roofer CityJSON surface는 exact 937-member 2024 RGB common base 중 건물별 sealed 12-view plan으로 display texture를 생성했다. OBJ/MTL/atlas와 face별 선택 camera, vertex coverage, incidence, MVS depth availability/consistency를 JSONL receipt로 남겼다. 이 texture는 표시용이며 official metric input이 아니다.

GS 학습, checkpoint render, Poisson, TSDF, Roofer, G2, metric 재계산 및 C4/C5 access는 수행하지 않았다. scientific_verdict와 official G3/G4/PASS_usable은 null이다.
"""
    write_new(output_root / "reports/technical_report_ko_v5.md", report.encode("utf-8"))
    checks = {
        "case_count_3": index["case_count"] == 3,
        "page_count_9": index["page_count"] == 9,
        "separate_principal_pages_0": index["separate_principal_section_page_count"] == 0,
        "legacy_dual_section_absent": not index["legacy_blue_red_dual_section_visible"],
        "top_locator_direct": index["all_top_panels_include_section_band_ab_view"],
        "all_sections_lod2_scaled": index["all_principal_columns_use_lod2_common_z"] and len(z_records) == 3,
        "c2_textures_3": index["c2_texture_bake_count"] == 3,
        "face_receipts_nonempty_or_explicit_not_run": all(
            row["receipt_record_count"] > 0
            and (row["geometric_face_count"] > 0 or row["source_status"] == "NOT_RUN_NO_SEALED_C2_ROOFER_OUTPUT")
            for row in texture_summaries
        ),
        "scientific_verdict_null": index["scientific_verdict"] is None,
        "official_pass_null": index["official_G3_G4_PASS_usable"] is None,
    }
    if not all(checks.values()):
        raise RuntimeError(f"v5 verification failed: {checks}")
    write_new(output_root / "control/200-verified.local_v5.json", canonical_json_bytes({"schema": "jointbuildgs.local_technical_200_verified.v5", "status": "200-VERIFIED_LOCAL_PRESENTATION_V5", "checks": checks, "scientific_verdict": None}))
    write_new(output_root / "control/technical_return_v5.json", canonical_json_bytes({"schema": "jointbuildgs.local_technical_return.v5", "status": "RETURNED_LOCAL_SINGLE_PCA_SECTION_AND_C2_RGB_TEXTURE", "pdf": record(pdf, output_root), "scientific_verdict": None}))
    material = [path for path in sorted(output_root.rglob("*")) if path.is_file() and path.name not in {"artifact_manifest_v5.json", "300-closed.local_v5.json"}]
    manifest = {"schema": "jointbuildgs.c1_c2_c3_consolidated_results_manifest.v5", "status": "COMPLETE_HASHED_MATERIAL_PAYLOAD", "records": [record(path, output_root) for path in material], "scientific_verdict": None}
    manifest["record_count"] = len(manifest["records"])
    write_new(output_root / "control/artifact_manifest_v5.json", canonical_json_bytes(manifest))
    closed = {"schema": "jointbuildgs.local_technical_300_closed.v5", "status": "300-CLOSED_LOCAL_PRESENTATION_V5", "verified": record(output_root / "control/200-verified.local_v5.json", output_root), "technical_return": record(output_root / "control/technical_return_v5.json", output_root), "manifest": record(output_root / "control/artifact_manifest_v5.json", output_root), "scientific_verdict": None}
    write_new(output_root / "control/300-closed.local_v5.json", canonical_json_bytes(closed))
    return closed


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--source-commit", required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.output_root, args.artifact_root, args.source_commit), ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
