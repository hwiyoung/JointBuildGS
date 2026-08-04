#!/usr/bin/env python3
"""Render sealed C3 roof meshes by attribute and assemble display-only footprint walls."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import html
import json
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
from scipy.spatial import cKDTree
from shapely.geometry import Polygon
from shapely.ops import triangulate

from scripts.p2.c1_c2_oracle_c3_extract_v1.contract import load_building_references
from scripts.p2.c3_mesh_attribute_hybrid_v1.contract import load_config, validate_config
from scripts.p2.c3_tsdf_roof_diagnostic_v1.contract import (
    canonical_json_bytes, file_record, resolve_artifact, write_new,
)
from scripts.p2.c3_tsdf_roof_diagnostic_v1.render import (
    VIEWS, _draw_footprint, _footprint_rings, _principal_frame, _setup_axes,
)


SEMANTIC_COLORS = {
    1: np.asarray([0.90, 0.28, 0.05]),
    2: np.asarray([0.20, 0.48, 0.72]),
    3: np.asarray([0.28, 0.62, 0.43]),
}


def _mesh_path(root: Path, condition: str, stable_id: str, method: str) -> Path:
    name = "poisson_same_evidence_roof_mesh_v1.ply" if method == "POISSON" else "tsdf_roof_mesh_v1.ply"
    return root / f"conditions/{condition}/buildings/{stable_id}/{name}"


def _resample_ring(ring: np.ndarray, spacing: float) -> np.ndarray:
    xy = np.asarray(ring, dtype=np.float64)
    if len(xy) > 1 and np.allclose(xy[0], xy[-1]):
        xy = xy[:-1]
    output = []
    for start, end in zip(xy, np.roll(xy, -1, axis=0)):
        length = float(np.linalg.norm(end - start))
        count = max(1, int(np.ceil(length / spacing)))
        output.extend(start + (end - start) * (index / count) for index in range(count))
    return np.asarray(output, dtype=np.float64)


def _source_mesh(mesh: o3d.geometry.TriangleMesh) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    if not mesh.has_vertex_normals():
        mesh.compute_vertex_normals()
    vertices = np.asarray(mesh.vertices, dtype=np.float64)
    faces = np.asarray(mesh.triangles, dtype=np.int64)
    colors = np.asarray(mesh.vertex_colors, dtype=np.float64)
    if len(colors) != len(vertices):
        colors = np.full((len(vertices), 3), 0.68, dtype=np.float64)
    labels = np.full(len(vertices), 1, dtype=np.uint8)
    return vertices, faces, np.clip(colors, 0, 1), labels


def _hybrid_mesh(
    mesh: o3d.geometry.TriangleMesh,
    footprint: Any,
    ground_z: float,
    spacing: float,
    nearest_count: int,
    minimum_wall_height: float,
) -> tuple[o3d.geometry.TriangleMesh, np.ndarray, dict[str, Any]]:
    vertices, faces, colors, labels = _source_mesh(mesh)
    if not len(vertices) or not len(faces):
        raise RuntimeError("cannot assemble hybrid from empty source mesh")
    tree = cKDTree(vertices[:, :2])
    polygons = [footprint] if footprint.geom_type == "Polygon" else list(footprint.geoms)
    added_vertices: list[np.ndarray] = []
    added_colors: list[np.ndarray] = []
    added_labels: list[int] = []
    added_faces: list[tuple[int, int, int]] = []
    wall_face_count = 0
    ground_face_count = 0
    base_count = len(vertices)
    for polygon in polygons:
        rings = [np.asarray(polygon.exterior.coords)] + [np.asarray(r.coords) for r in polygon.interiors]
        for raw_ring in rings:
            ring = _resample_ring(raw_ring, spacing)
            k = min(max(1, nearest_count), len(vertices))
            distance, index = tree.query(ring, k=k)
            if k == 1:
                distance, index = distance[:, None], index[:, None]
            weight = 1.0 / np.maximum(distance, 0.25)
            top_z = np.sum(vertices[index, 2] * weight, axis=1) / np.sum(weight, axis=1)
            boundary_rgb = np.sum(colors[index] * weight[:, :, None], axis=1) / np.sum(weight, axis=1)[:, None]
            top_z = np.maximum(top_z, ground_z + minimum_wall_height)
            ring_start = base_count + len(added_vertices)
            for xy, z, rgb in zip(ring, top_z, boundary_rgb):
                added_vertices.extend((np.asarray([xy[0], xy[1], z]), np.asarray([xy[0], xy[1], ground_z])))
                added_colors.extend((rgb, np.clip(rgb * 0.42, 0, 1)))
                added_labels.extend((2, 2))
            for index0 in range(len(ring)):
                index1 = (index0 + 1) % len(ring)
                t0, b0 = ring_start + 2 * index0, ring_start + 2 * index0 + 1
                t1, b1 = ring_start + 2 * index1, ring_start + 2 * index1 + 1
                added_faces.extend(((t0, b0, t1), (t1, b0, b1)))
                wall_face_count += 2
        for triangle in triangulate(polygon):
            if not polygon.covers(triangle.representative_point()):
                continue
            coords = np.asarray(triangle.exterior.coords[:3], dtype=np.float64)
            start = base_count + len(added_vertices)
            for xy in coords:
                added_vertices.append(np.asarray([xy[0], xy[1], ground_z]))
                added_colors.append(np.asarray([0.25, 0.32, 0.25]))
                added_labels.append(3)
            added_faces.append((start, start + 1, start + 2))
            ground_face_count += 1
    all_vertices = np.vstack((vertices, np.asarray(added_vertices)))
    all_faces = np.vstack((faces, np.asarray(added_faces, dtype=np.int64)))
    all_colors = np.vstack((colors, np.asarray(added_colors)))
    all_labels = np.concatenate((labels, np.asarray(added_labels, dtype=np.uint8)))
    hybrid = o3d.geometry.TriangleMesh()
    hybrid.vertices = o3d.utility.Vector3dVector(all_vertices)
    hybrid.triangles = o3d.utility.Vector3iVector(all_faces)
    hybrid.vertex_colors = o3d.utility.Vector3dVector(np.clip(all_colors, 0, 1))
    hybrid.compute_vertex_normals()
    return hybrid, all_labels, {
        "source_roof_vertex_count": int(len(vertices)),
        "source_roof_face_count": int(len(faces)),
        "wall_vertex_count": int(np.count_nonzero(all_labels == 2)),
        "wall_face_count": int(wall_face_count),
        "ground_vertex_count": int(np.count_nonzero(all_labels == 3)),
        "ground_face_count": int(ground_face_count),
        "ground_z_m": float(ground_z),
        "watertight_claim": False,
        "wall_texture_claim": "BOUNDARY_PROPAGATED_ROOF_RGB_NOT_OBSERVED_WALL_TEXTURE",
        "scientific_verdict": None,
    }


def _virtual_depth(vertices: np.ndarray, reference: Any, view: str) -> np.ndarray:
    center_xy, axis, cross = _principal_frame(reference)
    centered = vertices - np.asarray([center_xy[0], center_xy[1], np.median(vertices[:, 2])])
    if view == "TOP":
        return -vertices[:, 2]
    if view == "PRINCIPAL_SECTION":
        return centered[:, :2] @ cross
    elev = np.deg2rad(29 if view == "OBLIQUE_1" else 33)
    azim = np.deg2rad(-55 if view == "OBLIQUE_1" else 35)
    direction = np.asarray([np.cos(elev) * np.cos(azim), np.cos(elev) * np.sin(azim), np.sin(elev)])
    return -(centered @ direction)


def _face_colors(
    mesh: o3d.geometry.TriangleMesh,
    labels: np.ndarray,
    mode: str,
    reference: Any,
    view: str,
    depth_range: tuple[float, float],
) -> np.ndarray:
    vertices = np.asarray(mesh.vertices)
    faces = np.asarray(mesh.triangles)
    if mode == "RGB":
        values = np.asarray(mesh.vertex_colors)
    elif mode == "SEMANTIC":
        values = np.asarray([SEMANTIC_COLORS[int(label)] for label in labels])
    elif mode == "ABS_NORMAL":
        values = np.abs(np.asarray(mesh.vertex_normals))
        values /= np.maximum(np.max(values, axis=1, keepdims=True), 1e-12)
    else:
        depth = _virtual_depth(vertices, reference, view)
        lo, hi = depth_range
        normalized = np.clip((depth - lo) / max(hi - lo, 1e-9), 0, 1)
        values = plt.get_cmap("viridis")(normalized)[:, :3]
    return np.clip(values[faces].mean(axis=1), 0, 1)


def _draw_mesh(
    ax: Any,
    mesh: o3d.geometry.TriangleMesh,
    labels: np.ndarray,
    reference: Any,
    view: str,
    mode: str,
    depth_range: tuple[float, float],
) -> None:
    vertices = np.asarray(mesh.vertices)
    triangles = np.asarray(mesh.triangles)
    colors = _face_colors(mesh, labels, mode, reference, view, depth_range)
    stride = max(1, len(triangles) // 36000)
    faces = vertices[triangles[::stride]]
    face_colors = colors[::stride]
    if view == "TOP":
        ax.add_collection(PolyCollection(faces[:, :, :2], facecolors=face_colors, edgecolors="none", alpha=1.0))
    elif view.startswith("OBLIQUE"):
        ax.add_collection3d(Poly3DCollection(faces, facecolors=face_colors, edgecolors="none", alpha=1.0))
    else:
        center, axis, cross = _principal_frame(reference)
        local = faces[:, :, :2] - center
        band = max(min(np.ptp((vertices[:, :2] - center) @ cross) * 0.08, 1.5), 0.6)
        selected = (np.min(local @ cross, axis=1) <= band) & (np.max(local @ cross, axis=1) >= -band)
        if np.any(selected):
            section = np.stack((local[selected] @ axis, faces[selected, :, 2]), axis=2)
            ax.add_collection(PolyCollection(section, facecolors=face_colors[selected], edgecolors="none", alpha=0.95))


def _panel(
    path: Path,
    *,
    mesh: o3d.geometry.TriangleMesh,
    labels: np.ndarray,
    reference: Any,
    view: str,
    mode: str,
    zlim: tuple[float, float],
    ground_z: float,
    depth_range: tuple[float, float],
    title: str,
    note: str,
) -> None:
    figure = plt.figure(figsize=(6.4, 4.8), dpi=150)
    ax = figure.add_subplot(111, projection="3d", proj_type="ortho") if view.startswith("OBLIQUE") else figure.add_subplot(111)
    _draw_mesh(ax, mesh, labels, reference, view, mode, depth_range)
    _draw_footprint(ax, reference, view, ground_z)
    _setup_axes(ax, reference, zlim, view)
    ax.set_title(title, fontsize=10.5, fontweight="bold")
    figure.text(0.02, 0.018, note, fontsize=7.0, color="#222", va="bottom", bbox={"facecolor": "white", "edgecolor": "#999", "alpha": 0.88, "pad": 3})
    figure.tight_layout(rect=(0, 0.10, 1, 1))
    path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(path, metadata={"Software": "JointBuildGS C3 mesh attribute hybrid renderer"})
    plt.close(figure)


def _sheet(path: Path, stable_id: str, rows: Sequence[tuple[str, Sequence[Path]]]) -> None:
    cell_w, cell_h, label_w, header_h = 960, 720, 350, 120
    canvas = np.full((header_h + len(rows) * cell_h, label_w + 8 * cell_w, 3), 255, dtype=np.uint8)
    cv2.putText(canvas, stable_id, (24, 43), cv2.FONT_HERSHEY_SIMPLEX, 1.02, (20, 20, 20), 2, cv2.LINE_AA)
    cv2.putText(canvas, "C3 mesh attributes + GT-footprint oracle hybrid | scientific_verdict=null", (24, 88), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (55, 55, 55), 1, cv2.LINE_AA)
    conditions = ("C3-1 SEMANTIC", "C3-2 SEMANTIC + DEPTH")
    for block, condition in enumerate(conditions):
        cv2.putText(canvas, condition, (label_w + block * 4 * cell_w + 20, 34), cv2.FONT_HERSHEY_SIMPLEX, 0.68, (120, 45, 20) if block == 0 else (150, 45, 120), 2, cv2.LINE_AA)
        for column, view in enumerate(VIEWS):
            cv2.putText(canvas, view, (label_w + (block * 4 + column) * cell_w + 20, 91), cv2.FONT_HERSHEY_SIMPLEX, 0.67, (20, 20, 20), 2, cv2.LINE_AA)
    for row_index, (label, paths) in enumerate(rows):
        y0 = header_h + row_index * cell_h
        cv2.rectangle(canvas, (0, y0), (label_w, y0 + cell_h), (242, 244, 247), -1)
        for line_index, line in enumerate(label.split("\n")):
            cv2.putText(canvas, line, (18, y0 + 54 + line_index * 31), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (25, 25, 25), 1, cv2.LINE_AA)
        for column, panel_path in enumerate(paths):
            image = cv2.imread(str(panel_path), cv2.IMREAD_COLOR)
            if image is None:
                raise RuntimeError(f"panel unreadable: {panel_path}")
            image = cv2.resize(image, (cell_w, cell_h), interpolation=cv2.INTER_AREA)
            x0 = label_w + column * cell_w
            canvas[y0:y0 + cell_h, x0:x0 + cell_w] = image
    ok, encoded = cv2.imencode(".png", canvas)
    if not ok:
        raise RuntimeError("case sheet encoding failed")
    write_new(path, encoded.tobytes())


def _ground_z(config: Mapping[str, Any], artifact_root: Path, v13_root: Path, stable_id: str) -> tuple[float, str]:
    if stable_id == "DEBY_LOD2_4907177":
        presence = json.loads(resolve_artifact(artifact_root, config["source"]["presence_diagnostic_relative_path"], "presence diagnostic").read_text(encoding="utf-8"))
        values = []
        for source in presence["current_sources"].values():
            row = next(item for item in source["buffer_profiles"] if float(item["buffer_m"]) == 5.0)
            values.append(float(row["z_m"]["p10"]))
        return min(values), "MINIMUM_CURRENT_SOURCE_BUFFER_5M_P10_GROUND_FAILURE_OVERRIDE"
    prepared = json.loads((v13_root / f"operations/C2_MVS_GT_FOOTPRINT_ORACLE/{stable_id}/work/prepared_v1.json").read_text(encoding="utf-8"))
    return float(prepared["classification"]["local_ground_z"]), "C2_PREPARED_LOCAL_GROUND"


def _records(root: Path) -> list[dict[str, Any]]:
    excluded = {"control/artifact_manifest_v1.json", "control/technical_return_v1.json", "control/200-verified.local_v1.json", "control/300-closed.local_v1.json"}
    return [file_record(path, root) for path in sorted(root.rglob("*")) if path.is_file() and path.relative_to(root).as_posix() not in excluded]


def run(output_root: Path, artifact_root: Path, source_commit: str) -> dict[str, Any]:
    config = load_config()
    validate_config(config)
    mesh_root = resolve_artifact(artifact_root, config["source"]["mesh_relative_root"], "sealed mesh root")
    v13_root = resolve_artifact(artifact_root, config["source"]["v13_relative_root"], "v13")
    lod2 = resolve_artifact(artifact_root, config["source"]["lod2_relative_path"], "LoD2")
    references = load_building_references(lod2, config["scope"]["building_ids"])
    cases = []
    hybrid_records = []
    methods = tuple(config["scope"]["mesh_methods"])
    conditions = tuple(config["scope"]["condition_ids"])
    modes = tuple(config["scope"]["display_modes"])
    for stable_id in config["scope"]["building_ids"]:
        reference = references[stable_id]
        ground_z, ground_policy = _ground_z(config, artifact_root, v13_root, stable_id)
        data: dict[tuple[str, str, str], tuple[o3d.geometry.TriangleMesh, np.ndarray]] = {}
        all_vertices = []
        for condition in conditions:
            for method in methods:
                source_path = _mesh_path(mesh_root, condition, stable_id, method)
                mesh = o3d.io.read_triangle_mesh(str(source_path))
                vertices, _faces, _colors, labels = _source_mesh(mesh)
                data[(condition, method, "ROOF_ONLY")] = (mesh, labels)
                all_vertices.append(vertices)
                hybrid, hybrid_labels, provenance = _hybrid_mesh(
                    mesh, reference.footprint, ground_z,
                    float(config["hybrid"]["boundary_sample_spacing_m"]),
                    int(config["hybrid"]["nearest_roof_vertex_count"]),
                    float(config["hybrid"]["minimum_wall_height_m"]),
                )
                hybrid_path = output_root / f"hybrid/{condition}/{stable_id}/{method.lower()}_gt_footprint_oracle_hybrid_v1.ply"
                hybrid_path.parent.mkdir(parents=True, exist_ok=True)
                if hybrid_path.exists() or not o3d.io.write_triangle_mesh(str(hybrid_path), hybrid, write_ascii=False, compressed=False, write_vertex_normals=True, write_vertex_colors=True):
                    raise RuntimeError(f"failed to write hybrid mesh: {hybrid_path}")
                provenance.update({
                    "schema": "jointbuildgs.c3_gt_footprint_oracle_hybrid_mesh.v1",
                    "condition_id": condition, "stable_id": stable_id, "mesh_method": method,
                    "source_mesh": file_record(source_path, mesh_root),
                    "hybrid_mesh": file_record(hybrid_path, output_root),
                    "ground_policy": ground_policy,
                    "gt_footprint_xy_used": True, "lod2_z_used": False,
                    "honest_stage3_output": False, "official_metric_input": False,
                })
                provenance_path = hybrid_path.with_name(hybrid_path.stem + "_provenance.json")
                write_new(provenance_path, canonical_json_bytes(provenance))
                hybrid_records.append(provenance)
                data[(condition, method, "HYBRID")] = (hybrid, hybrid_labels)
                all_vertices.append(np.asarray(hybrid.vertices))
        z_values = np.concatenate([vertices[:, 2] for vertices in all_vertices if len(vertices)] + [np.asarray([ground_z])])
        zlim = (float(np.quantile(z_values, 0.001) - 1.5), float(np.quantile(z_values, 0.999) + 1.5))
        depth_ranges = {}
        for view in VIEWS:
            values = np.concatenate([_virtual_depth(vertices, reference, view) for vertices in all_vertices if len(vertices)])
            depth_ranges[view] = (float(np.min(values)), float(np.max(values)))
        rows = []
        panel_records = []
        for geometry_kind in ("ROOF_ONLY", "HYBRID"):
            for method in methods:
                for mode in modes:
                    paths = []
                    for condition in conditions:
                        mesh, labels = data[(condition, method, geometry_kind)]
                        for view in VIEWS:
                            path = output_root / f"qualitative/{stable_id}/panels/{geometry_kind.lower()}_{method.lower()}_{mode.lower()}_{condition}_{view.lower()}.png"
                            if geometry_kind == "ROOF_ONLY":
                                note = "observed roof-only mesh; semantic view is uniformly ROOF; no footprint wall"
                            else:
                                note = "GT-footprint oracle hybrid: observed roof + extruded wall + ground cap; wall RGB is propagated, not observed texture"
                            if mode == "VIRTUAL_DEPTH":
                                note += "; depth is fixed virtual-view depth, not checkpoint camera depth"
                            _panel(
                                path, mesh=mesh, labels=labels, reference=reference, view=view, mode=mode,
                                zlim=zlim, ground_z=ground_z, depth_range=depth_ranges[view],
                                title=f"{condition} | {method} | {geometry_kind} | {mode} | {view}", note=note,
                            )
                            paths.append(path)
                            panel_records.append(file_record(path, output_root))
                    rows.append((f"{geometry_kind}\n{method} | {mode}", paths))
        sheet = output_root / f"qualitative/{stable_id}/case_sheet_mesh_attributes_hybrid_v1.png"
        _sheet(sheet, stable_id, rows)
        cases.append({
            "stable_id": stable_id, "row_count": len(rows), "column_count": 8,
            "visible_cell_count": len(rows) * 8, "panel_count": len(panel_records),
            "case_sheet": file_record(sheet, output_root), "panels": panel_records,
            "ground_z_m": ground_z, "ground_policy": ground_policy,
        })
    index = {
        "schema": "jointbuildgs.c3_mesh_attribute_hybrid_qualitative_index.v1",
        "status": "COMPLETE_SEALED_MESH_ATTRIBUTES_AND_DISPLAY_ONLY_ORACLE_HYBRID",
        "source_commit": source_commit, "case_count": len(cases),
        "rows_per_sheet": 16, "columns_per_sheet": 8,
        "visible_cell_count": sum(row["visible_cell_count"] for row in cases),
        "panel_count": sum(row["panel_count"] for row in cases),
        "hybrid_mesh_count": len(hybrid_records), "cases": cases,
        "execution_counters": {
            "gs_training_invocations": 0, "checkpoint_render_extractions": 0,
            "poisson_reconstructions": 0, "tsdf_reconstructions": 0,
            "hybrid_wall_assemblies": len(hybrid_records), "roofer_invocations": 0,
            "g2_invocations": 0, "metric_recomputations": 0, "c4_c5_accesses": 0,
        },
        "official_G3_G4_PASS_usable": None, "scientific_verdict": None,
    }
    write_new(output_root / "qualitative/index_v1.json", canonical_json_bytes(index))
    report = """# C3 Poisson/TSDF mesh attribute 및 GT-footprint oracle hybrid\n\n행 1–8은 봉인된 roof-only Poisson/TSDF mesh를 RGB, semantic, fixed virtual-view depth, absolute normal로 표시한다. 행 9–16은 같은 roof mesh에 GT GroundSurface XY footprint wall과 ground cap을 추가한 display-only oracle hybrid다.\n\n원본 roof mesh의 RGB와 normal은 PLY vertex attribute다. semantic은 roof-only selection이므로 원본 mesh 전체가 roof이며, depth는 학습 camera depth가 아니라 네 고정 시점에서 계산한 비교용 virtual-view depth다. Hybrid wall RGB는 가까운 roof boundary RGB를 전파한 색으로 실제 관측 wall texture가 아니다.\n\nHybrid는 honest Stage 3 결과 또는 metric 입력이 아니다. Poisson/TSDF 재구성, GS 학습, checkpoint extraction, Roofer, G2, metric, C4/C5 접근은 모두 0회다. `scientific_verdict`는 null이다.\n"""
    write_new(output_root / "reports/technical_report_ko_v1.md", report.encode("utf-8"))
    links = "".join(f'<section><h2>{html.escape(row["stable_id"])}</h2><a href="../{row["case_sheet"]["path"]}"><img src="../{row["case_sheet"]["path"]}"></a></section>' for row in cases)
    page = "<!doctype html><meta charset='utf-8'><title>C3 mesh attributes</title><style>body{font-family:sans-serif;margin:24px}img{width:100%}section{margin:24px 0}</style><h1>C3 mesh attributes + oracle hybrid</h1>" + links
    write_new(output_root / "reports/case_index.html", page.encode("utf-8"))
    generated = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    returned = {
        "schema": "jointbuildgs.c3_mesh_attribute_hybrid_technical_return.v1",
        "status": "RETURNED_LOCAL_COMPLETE_MESH_ATTRIBUTE_HYBRID_DIAGNOSTIC",
        "source_commit": source_commit, "generated_at": generated,
        "case_count": 3, "rows_per_sheet": 16, "columns_per_sheet": 8,
        "panel_count": index["panel_count"], "hybrid_mesh_count": len(hybrid_records),
        "execution_counters": index["execution_counters"],
        "official_G3_G4_PASS_usable": None, "scientific_verdict": None,
    }
    write_new(output_root / "control/technical_return_v1.json", canonical_json_bytes(returned))
    manifest = {
        "schema": "jointbuildgs.c3_mesh_attribute_hybrid_artifact_manifest.v1",
        "status": "COMPLETE_HASHED_MATERIAL_PAYLOAD", "source_commit": source_commit,
        "records": _records(output_root), "official_G3_G4_PASS_usable": None,
        "scientific_verdict": None,
    }
    manifest["record_count"] = len(manifest["records"])
    write_new(output_root / "control/artifact_manifest_v1.json", canonical_json_bytes(manifest))
    verified = {
        "schema": "jointbuildgs.local_technical_200_verified.v1",
        "status": "200-VERIFIED_LOCAL_SELF_CHECK",
        "checks": {
            "case_count_3": len(cases) == 3,
            "rows_16_columns_8": all(row["row_count"] == 16 and row["column_count"] == 8 for row in cases),
            "panel_count_384": index["panel_count"] == 384,
            "hybrid_mesh_count_12": len(hybrid_records) == 12,
            "source_reconstructions_zero": index["execution_counters"]["poisson_reconstructions"] == 0 and index["execution_counters"]["tsdf_reconstructions"] == 0,
            "prohibited_counters_zero": all(index["execution_counters"][key] == 0 for key in ("gs_training_invocations", "checkpoint_render_extractions", "roofer_invocations", "g2_invocations", "metric_recomputations", "c4_c5_accesses")),
            "scientific_verdict_null": index["scientific_verdict"] is None,
        },
        "manifest": file_record(output_root / "control/artifact_manifest_v1.json", output_root),
        "scientific_verdict": None,
    }
    if not all(verified["checks"].values()):
        raise RuntimeError("mesh attribute hybrid verification failed")
    write_new(output_root / "control/200-verified.local_v1.json", canonical_json_bytes(verified))
    closed = {
        "schema": "jointbuildgs.local_technical_300_closed.v1",
        "status": "300-CLOSED_LOCAL_MESH_ATTRIBUTE_HYBRID_DIAGNOSTIC",
        "technical_return": file_record(output_root / "control/technical_return_v1.json", output_root),
        "verified": file_record(output_root / "control/200-verified.local_v1.json", output_root),
        "manifest": file_record(output_root / "control/artifact_manifest_v1.json", output_root),
        "official_G3_G4_PASS_usable": None, "scientific_verdict": None,
    }
    write_new(output_root / "control/300-closed.local_v1.json", canonical_json_bytes(closed))
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
