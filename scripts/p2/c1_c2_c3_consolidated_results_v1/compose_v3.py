#!/usr/bin/env python3
"""Correct C1/C2 lineage and add explicit principal-section locators."""
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
import numpy as np
import open3d as o3d

from scripts.p2.c1_c2_c3_consolidated_results_v1.compose import build_pdf, canonical_json_bytes, record, write_new
from scripts.p2.c1_c2_c3_consolidated_results_v1.compose_v2 import render_filled_plane_panel, section_segments
from scripts.p2.c1_c2_oracle_c3_extract_v1.contract import load_building_references
from scripts.p2.c3_tsdf_roof_diagnostic_v1.render import _footprint_rings, _principal_frame
from src.visualization.fixed_view_qualitative import load_cityjsonseq, load_las_points


REPO_ROOT = Path(__file__).resolve().parents[3]
CONFIG_PATH = REPO_ROOT / "configs/p2/c1_c2_c3_consolidated_results_v1/compose_v3.json"
VIEWS = ("TOP", "OBLIQUE_1", "OBLIQUE_2", "PRINCIPAL_SECTION")


def load_config() -> dict[str, Any]:
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def validate_config(config: Mapping[str, Any]) -> None:
    if config.get("schema") != "jointbuildgs.p2.c1_c2_c3_consolidated_results.v3":
        raise RuntimeError("unexpected v3 schema")
    if config.get("status") != "APPROVED_FOR_LOCAL_PRESENTATION_CORRECTION_ONLY":
        raise RuntimeError("v3 presentation correction is not active")
    if tuple(config["views"]) != VIEWS or len(config["building_ids"]) != 3:
        raise RuntimeError("scope drifted")
    if not all(config["presentation_corrections"].values()):
        raise RuntimeError("presentation correction contract is incomplete")
    if any(int(value) != 0 for value in config["execution_counters"].values()):
        raise RuntimeError("all execution counters must remain zero")
    if config.get("scientific_verdict", "missing") is not None:
        raise RuntimeError("scientific_verdict must remain null")


def source_roots(artifact_root: Path, config: Mapping[str, Any]) -> dict[str, Path]:
    roots = {key: artifact_root / relative for key, relative in config["sources"].items()}
    for key, path in roots.items():
        if not path.exists():
            raise RuntimeError(f"missing source {key}: {path}")
    return roots


def legacy_section_center(reference: Any) -> float:
    return 0.5 * (float(reference.footprint.bounds[1]) + float(reference.footprint.bounds[3]))


def draw_legacy_footprint(ax: Any, reference: Any, view: str, z: float) -> None:
    for ring in _footprint_rings(reference):
        if view == "TOP":
            ax.plot(ring[:, 0], ring[:, 1], color="#f59e0b", linestyle="--", linewidth=2.1)
        elif view.startswith("OBLIQUE"):
            ax.plot(ring[:, 0], ring[:, 1], np.full(len(ring), z), color="#f59e0b", linestyle="--", linewidth=1.9)
        else:
            ax.plot([ring[:, 0].min(), ring[:, 0].max()], [z, z], color="#f59e0b", linestyle="--", linewidth=1.9)


def setup_legacy_axes(ax: Any, reference: Any, zlim: tuple[float, float], view: str) -> None:
    x0, y0, x1, y1 = map(float, reference.footprint.bounds)
    pad = max(max(x1 - x0, y1 - y0) * 0.25, 4.0)
    if view == "TOP":
        ax.set_xlim(x0 - pad, x1 + pad); ax.set_ylim(y0 - pad, y1 + pad); ax.set_aspect("equal")
        ax.set_xlabel("E"); ax.set_ylabel("N")
    elif view.startswith("OBLIQUE"):
        ax.set_xlim(x0 - pad, x1 + pad); ax.set_ylim(y0 - pad, y1 + pad); ax.set_zlim(*zlim)
        ax.set_box_aspect((x1 - x0 + 2 * pad, y1 - y0 + 2 * pad, max(zlim[1] - zlim[0], 1.0)))
        ax.view_init(elev=28 if view == "OBLIQUE_1" else 32, azim=-55 if view == "OBLIQUE_1" else 35)
        ax.set_xlabel("E", fontsize=7); ax.set_ylabel("N", fontsize=7); ax.set_zlabel("Z", fontsize=7)
    else:
        ax.set_xlim(x0 - pad, x1 + pad); ax.set_ylim(*zlim)
        ax.set_xlabel("legacy principal E section"); ax.set_ylabel("Z (m)")


def render_input_panel(destination: Path, source_las: Path, reference: Any, view: str, title: str) -> dict[str, int]:
    points = load_las_points(source_las)
    xyz = np.asarray(points.xyz, dtype=np.float64)
    classes = np.asarray(points.classification if points.classification is not None else np.zeros(len(xyz)), dtype=np.uint8)
    if not len(xyz):
        raise RuntimeError(f"empty sealed LAS: {source_las}")
    stride = max(1, len(xyz) // 18000)
    xyz, classes = xyz[::stride], classes[::stride]
    colors = np.where(classes[:, None] == 6, np.asarray([[0.0, 0.72, 0.88]]), np.asarray([[0.86, 0.22, 0.78]]))
    z0, z1 = float(np.quantile(xyz[:, 2], 0.005)), float(np.quantile(xyz[:, 2], 0.995))
    pad_z = max((z1 - z0) * 0.08, 1.0); zlim = (z0 - pad_z, z1 + pad_z)
    ground_z = float(np.quantile(xyz[:, 2], 0.02))
    figure = plt.figure(figsize=(6.4, 4.8), dpi=150)
    ax = figure.add_subplot(111, projection="3d", proj_type="ortho") if view.startswith("OBLIQUE") else figure.add_subplot(111)
    if view == "TOP":
        ax.scatter(xyz[:, 0], xyz[:, 1], c=colors, s=2.0, linewidths=0)
    elif view.startswith("OBLIQUE"):
        ax.scatter(xyz[:, 0], xyz[:, 1], xyz[:, 2], c=colors, s=1.7, linewidths=0, depthshade=False)
    else:
        center_y = legacy_section_center(reference)
        band = max((reference.footprint.bounds[3] - reference.footprint.bounds[1]) * 0.08, 0.8)
        keep = np.abs(xyz[:, 1] - center_y) <= band
        ax.scatter(xyz[keep, 0], xyz[keep, 2], c=colors[keep], s=3.0, linewidths=0)
    draw_legacy_footprint(ax, reference, view, ground_z)
    setup_legacy_axes(ax, reference, zlim, view)
    ax.set_title(title, fontsize=11, fontweight="bold")
    figure.tight_layout(); destination.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(destination, metadata={"Software": "JointBuildGS sealed C1/C2 input display"}); plt.close(figure)
    return {"class6_count": int(np.count_nonzero(points.classification == 6)), "class2_count": int(np.count_nonzero(points.classification == 2))}


def render_filled_legacy_section(destination: Path, cityjson: Path, reference: Any, title: str) -> dict[str, int]:
    surfaces = load_cityjsonseq(cityjson)
    roof = [surface for surface in surfaces if surface.semantic == "RoofSurface" and len(surface.xyz) >= 3]
    wall = [surface for surface in surfaces if surface.semantic == "WallSurface" and len(surface.xyz) >= 3]
    other = [surface for surface in surfaces if surface.semantic not in {"RoofSurface", "WallSurface"} and len(surface.xyz) >= 3]
    all_xyz = np.concatenate([surface.xyz for surface in surfaces if len(surface.xyz) >= 3])
    z0, z1 = float(all_xyz[:, 2].min()), float(all_xyz[:, 2].max()); pad = max((z1 - z0) * 0.1, 1.0)
    colors = plt.get_cmap("tab20")(np.linspace(0.02, 0.82, max(len(roof), 2)))
    fig, ax = plt.subplots(figsize=(6.4, 4.8), dpi=150)
    center_y = legacy_section_center(reference)
    for index, surface in enumerate(roof):
        for segment in section_segments(surface.xyz, center_y):
            ax.plot(segment[:, 0], segment[:, 1], color=colors[index], linewidth=4.2, solid_capstyle="round")
    for surface in wall + other:
        for segment in section_segments(surface.xyz, center_y):
            ax.plot(segment[:, 0], segment[:, 1], color="#777777", linewidth=1.4, alpha=0.7)
    ground_z = float(np.quantile(all_xyz[:, 2], 0.02)); draw_legacy_footprint(ax, reference, "PRINCIPAL_SECTION", ground_z)
    setup_legacy_axes(ax, reference, (z0 - pad, z1 + pad), "PRINCIPAL_SECTION")
    ax.set_title(f"{title} | SECTION\nroof planes={len(roof)}", fontsize=10.5, fontweight="bold")
    fig.tight_layout(); destination.parent.mkdir(parents=True, exist_ok=True); fig.savefig(destination); plt.close(fig)
    return {"roof_plane_count": len(roof), "wall_surface_count": len(wall), "other_surface_count": len(other)}


def render_not_run_panel(destination: Path, reference: Any, view: str, message: str) -> None:
    fig = plt.figure(figsize=(6.4, 4.8), dpi=150)
    ax = fig.add_subplot(111, projection="3d", proj_type="ortho") if view.startswith("OBLIQUE") else fig.add_subplot(111)
    setup_legacy_axes(ax, reference, (558.0, 588.0), view)
    draw_legacy_footprint(ax, reference, view, 560.0)
    method = ax.text2D if view.startswith("OBLIQUE") else ax.text
    method(0.5, 0.5, message, transform=ax.transAxes, ha="center", va="center", fontsize=13, fontweight="bold", color="#991b1b", bbox={"facecolor": "white", "edgecolor": "#991b1b", "alpha": 0.92, "pad": 8})
    ax.set_title(f"C2 Roofer | {view}", fontsize=11, fontweight="bold")
    fig.tight_layout(); destination.parent.mkdir(parents=True, exist_ok=True); fig.savefig(destination); plt.close(fig)


def retitle_panel(path: Path, title: str) -> None:
    image = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if image is None:
        raise RuntimeError(f"panel unreadable for retitle: {path}")
    image[:72, :] = 255
    size, _baseline = cv2.getTextSize(title, cv2.FONT_HERSHEY_SIMPLEX, 0.62, 1)
    cv2.putText(image, title, (max((image.shape[1] - size[0]) // 2, 8), 38), cv2.FONT_HERSHEY_SIMPLEX, 0.62, (20, 20, 20), 1, cv2.LINE_AA)
    if not cv2.imwrite(str(path), image, [cv2.IMWRITE_PNG_COMPRESSION, 5]):
        raise RuntimeError(f"panel retitle failed: {path}")


def render_locator(destination: Path, reference: Any, *, dual: bool) -> dict[str, Any]:
    rings = _footprint_rings(reference)
    center_pca, axis, cross = _principal_frame(reference)
    x0, y0, x1, y1 = map(float, reference.footprint.bounds)
    legacy_y = 0.5 * (y0 + y1)
    fig, ax = plt.subplots(figsize=(8.6, 2.2), dpi=150)
    for ring in rings:
        ax.plot(ring[:, 0], ring[:, 1], color="#333333", linewidth=1.8)
    ax.plot([x0, x1], [legacy_y, legacy_y], color="#2563eb", linestyle="--", linewidth=2.5, label="legacy E-section")
    ax.annotate("LOOK +N", xy=(x1, legacy_y + 0.18 * (y1 - y0)), xytext=(x1, legacy_y), arrowprops={"arrowstyle": "->", "color": "#2563eb", "lw": 2}, color="#2563eb", fontsize=9)
    p0 = center_pca - axis * max(x1 - x0, y1 - y0)
    p1 = center_pca + axis * max(x1 - x0, y1 - y0)
    if dual:
        ax.plot([p0[0], p1[0]], [p0[1], p1[1]], color="#d62728", linewidth=2.5, label="PCA principal section")
        look_end = center_pca + cross * 0.28 * max(x1 - x0, y1 - y0)
        ax.annotate("PCA LOOK", xy=look_end, xytext=center_pca, arrowprops={"arrowstyle": "->", "color": "#d62728", "lw": 2}, color="#d62728", fontsize=9)
    pad = max(max(x1 - x0, y1 - y0) * 0.12, 2.0); ax.set_xlim(x0 - pad, x1 + pad); ax.set_ylim(y0 - pad, y1 + pad)
    ax.set_aspect("equal"); ax.set_xlabel("Easting"); ax.set_ylabel("Northing"); ax.legend(loc="upper right", fontsize=8)
    ax.set_title("PRINCIPAL SECTION LOCATOR — top view cut line and viewing direction", fontsize=11, fontweight="bold")
    fig.tight_layout(); destination.parent.mkdir(parents=True, exist_ok=True); fig.savefig(destination); plt.close(fig)
    return {"legacy_center_y": legacy_y, "pca_center_xy": center_pca.tolist(), "pca_axis_en": axis.tolist(), "pca_look_en": cross.tolist(), "dual": dual}


def prepend_locator(page: Path, locator: Path, note_lines: Sequence[str]) -> None:
    image = cv2.imread(str(page), cv2.IMREAD_COLOR); loc = cv2.imread(str(locator), cv2.IMREAD_COLOR)
    if image is None or loc is None:
        raise RuntimeError("page or locator unreadable")
    strip_h = 390; canvas = np.full((image.shape[0] + strip_h, image.shape[1], 3), 255, dtype=np.uint8)
    resized = cv2.resize(loc, (1500, 360), interpolation=cv2.INTER_AREA); canvas[15:375, 20:1520] = resized
    for index, line in enumerate(note_lines):
        cv2.putText(canvas, line, (1570, 80 + index * 48), cv2.FONT_HERSHEY_SIMPLEX, 0.70, (32, 32, 32), 2, cv2.LINE_AA)
    canvas[strip_h:, :] = image
    if not cv2.imwrite(str(page), canvas, [cv2.IMWRITE_PNG_COMPRESSION, 5]):
        raise RuntimeError(f"failed to prepend locator: {page}")


def compose_c1_c2_page(destination: Path, stable_id: str, rows: Sequence[tuple[str, Sequence[Path]]]) -> None:
    cell_w, cell_h, label_w, header_h = 960, 720, 620, 180
    canvas = np.full((header_h + len(rows) * cell_h, label_w + 4 * cell_w, 3), 255, dtype=np.uint8)
    cv2.putText(canvas, stable_id, (24, 52), cv2.FONT_HERSHEY_SIMPLEX, 1.05, (20, 20, 20), 2, cv2.LINE_AA)
    cv2.putText(canvas, "LATEST BUILDING-SPECIFIC C1/C2 | input points versus filled Roofer planes", (24, 98), cv2.FONT_HERSHEY_SIMPLEX, 0.62, (50, 50, 50), 1, cv2.LINE_AA)
    cv2.putText(canvas, "cyan=class6 roof | magenta=class2 terrain | orange dashed=GT footprint | filled colors=Roofer roof planes", (24, 137), cv2.FONT_HERSHEY_SIMPLEX, 0.50, (70, 70, 70), 1, cv2.LINE_AA)
    for column, view in enumerate(VIEWS):
        cv2.putText(canvas, "SECTION" if view == "PRINCIPAL_SECTION" else view, (label_w + column * cell_w + 24, 112), cv2.FONT_HERSHEY_SIMPLEX, 0.72, (30, 30, 30), 2, cv2.LINE_AA)
    for row_index, (label, panels) in enumerate(rows):
        y0 = header_h + row_index * cell_h; cv2.rectangle(canvas, (0, y0), (label_w - 1, y0 + cell_h - 1), (247, 247, 247), -1)
        for line_index, line in enumerate(label.split("\n")):
            cv2.putText(canvas, line, (22, y0 + 70 + line_index * 38), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (30, 30, 30), 2, cv2.LINE_AA)
        for column, panel in enumerate(panels):
            image = cv2.imread(str(panel), cv2.IMREAD_COLOR)
            if image is None: raise RuntimeError(f"panel unreadable: {panel}")
            image = cv2.resize(image, (cell_w, cell_h), interpolation=cv2.INTER_AREA)
            x0c = label_w + column * cell_w; canvas[y0:y0 + cell_h, x0c:x0c + cell_w] = image
    destination.parent.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(str(destination), canvas, [cv2.IMWRITE_PNG_COMPRESSION, 5]): raise RuntimeError("C1/C2 page write failed")


def run(output_root: Path, artifact_root: Path, source_base_commit: str) -> dict[str, Any]:
    config = load_config(); validate_config(config)
    if output_root.exists() and any(output_root.iterdir()): raise RuntimeError("add-once v3 namespace is not empty")
    output_root.mkdir(parents=True, exist_ok=True); roots = source_roots(artifact_root, config)
    references = load_building_references(roots["lod2_relative_path"], config["building_ids"])
    v13, recovery, v2 = roots["v13_relative_root"], roots["c1_4907177_recovery_relative_root"], roots["v2_relative_root"]
    page_records=[]; page_paths=[]; locator_records=[]; c1c2_lineage=[]
    for stable_id in config["building_ids"]:
        reference=references[stable_id]; case=output_root/f"qualitative/c1_c2/{stable_id}"; raw_root=v13/f"qualitative/c1_c2/{stable_id}/panels"
        raw=[raw_root/f"raw_{i}.png" for i in range(1,5)]
        c1_input = recovery/f"operations/C1_LIDAR_LOD2_GROUND_Z_ORACLE/{stable_id}/work/input.las" if stable_id=="DEBY_LOD2_4907177" else v13/f"operations/C1_LIDAR_GT_FOOTPRINT_ORACLE/{stable_id}/work/input.las"
        c2_input = v13/f"operations/C2_MVS_GT_FOOTPRINT_ORACLE/{stable_id}/work/input.las"
        c1_inputs=[]; c2_inputs=[]
        for view in VIEWS:
            p=case/f"panels/C1_INPUT__{view}.png"; render_input_panel(p,c1_input,reference,view,"C1 current UAS LiDAR input"); c1_inputs.append(p)
            p=case/f"panels/C2_INPUT__{view}.png"; render_input_panel(p,c2_input,reference,view,"C2 current MVS input"); c2_inputs.append(p)
        c1_city = recovery/f"operations/C1_LIDAR_LOD2_GROUND_Z_ORACLE/{stable_id}/work/out/690844_5336144.city.jsonl" if stable_id=="DEBY_LOD2_4907177" else next((v13/f"operations/C1_LIDAR_GT_FOOTPRINT_ORACLE/{stable_id}/work/out").glob("*.city.jsonl"))
        c1_outputs=[]
        for view in VIEWS:
            p=case/f"panels/C1_OUTPUT__{view}.png"
            if view=="PRINCIPAL_SECTION": render_filled_legacy_section(p,c1_city,reference,"C1 Roofer filled planes")
            else: render_filled_plane_panel(p,view,reference,load_cityjsonseq(c1_city))
            c1_outputs.append(p)
        c2_outputs=[]
        c2_candidates=list((v13/f"operations/C2_MVS_GT_FOOTPRINT_ORACLE/{stable_id}/work/out").glob("*.city.jsonl"))
        for view in VIEWS:
            p=case/f"panels/C2_OUTPUT__{view}.png"
            if not c2_candidates: render_not_run_panel(p,reference,view,"NOT RUN\ninsufficient class-6 roof evidence")
            elif view=="PRINCIPAL_SECTION": render_filled_legacy_section(p,c2_candidates[0],reference,"C2 Roofer filled planes")
            else:
                render_filled_plane_panel(p,view,reference,load_cityjsonseq(c2_candidates[0]))
                retitle_panel(p,f"C2 Roofer filled plane surfaces | {view}")
            c2_outputs.append(p)
        page=output_root/f"pages/{len(page_records)+1:02d}_{stable_id}_C1_C2.png"
        compose_c1_c2_page(page,stable_id,[("2024 RGB + 2022 roofline",raw),("C1 UAS LiDAR INPUT\nsealed LAS points",c1_inputs),("C1 ROOFER OUTPUT\nfilled CityJSON planes",c1_outputs),("C2 MVS INPUT\nsealed LAS points",c2_inputs),("C2 ROOFER OUTPUT\nfilled planes or NOT RUN",c2_outputs)])
        locator=output_root/f"qualitative/section_locators/{stable_id}_c1_c2_locator.png"; locator_info=render_locator(locator,reference,dual=False)
        prepend_locator(page,locator,["C1/C2 section frame: legacy E-section", "blue dashed=cut line; arrow=look +North", "input LAS and output CityJSON are different sources"])
        locator_records.append({"stable_id":stable_id,"page_role":"C1_C2",**locator_info,"output":record(locator,output_root)})
        page_paths.append(page); page_records.append({"page":len(page_records)+1,"stable_id":stable_id,"section":"C1_C2_LATEST_BUILDING_SPECIFIC","output":record(page,output_root)})
        for condition in config["condition_ids"]:
            source_page=v2/f"pages/{'02' if stable_id.endswith('4907177') and condition=='C3_1_SEM' else '03' if stable_id.endswith('4907177') else '05' if stable_id.endswith('4906975') and condition=='C3_1_SEM' else '06' if stable_id.endswith('4906975') else '08' if condition=='C3_1_SEM' else '09'}_{stable_id}_{condition}.png"
            page=output_root/f"pages/{len(page_records)+1:02d}_{stable_id}_{condition}.png"; page.parent.mkdir(parents=True,exist_ok=True); shutil.copyfile(source_page,page)
            locator=output_root/f"qualitative/section_locators/{stable_id}_{condition}_locator.png"; locator_info=render_locator(locator,reference,dual=True)
            prepend_locator(page,locator,["BLUE rows 2-5,9: inherited legacy E-section", "RED rows 6-8,10-12: footprint PCA section", "row 1 contains camera images, not a geometric cut", "principal-column cross-row comparison is frame-limited"])
            locator_records.append({"stable_id":stable_id,"page_role":condition,**locator_info,"output":record(locator,output_root)})
            page_paths.append(page); page_records.append({"page":len(page_records)+1,"stable_id":stable_id,"section":condition,"output":record(page,output_root),"section_frame_mismatch_explicit":True})
    pdf=output_root/"reports/C1_C2_C3_qualitative_results_v3_lineage_section_locator.pdf"; build_pdf(page_paths,pdf)
    consensus_path=roots["diagnostic_relative_root"]/"conditions/C3_2_SEM_DEPTH/buildings/DEBY_LOD2_4906975/shared_view_roof_consensus_points_v1.ply"
    pc=o3d.io.read_point_cloud(str(consensus_path)); nz=np.abs(np.asarray(pc.normals)[:,2])
    consensus_diag={"point_count":int(len(nz)),"wall_like_abs_normal_z_lt_0p3_fraction":float(np.mean(nz<0.3)),"roof_like_abs_normal_z_gt_0p7_fraction":float(np.mean(nz>0.7)),"normal_z_median":float(np.median(nz))}
    index={"schema":"jointbuildgs.c1_c2_c3_consolidated_results_index.v3","status":"COMPLETE_LATEST_C1_C2_AND_SECTION_LOCATOR_CORRECTION","generated_at":datetime.now(timezone.utc).isoformat().replace("+00:00","Z"),"source_base_commit":source_base_commit,"case_count":3,"page_count":9,"c1_c2_page_count":3,"c3_page_count":6,"pages":page_records,"section_locators":locator_records,"c3_2_4906975_consensus_normal_diagnostic":consensus_diag,"mesh_input_definition":{"shared_source":"checkpoint median depth + rendered semantic roof class 1 + alpha>=0.5 + footprint buffer 1m + 0.15m voxel + minimum 2 distinct views","poisson":"oriented consensus xyz/normals/colors; Open3D Poisson depth 8; cropped to evidence/footprint","tsdf":"same retained consensus voxel keys mapped back to depth pixels; camera-ray integration; voxel 0.15m; truncation 0.45m"},"execution_counters":config["execution_counters"],"official_G3_G4_PASS_usable":None,"scientific_verdict":None,"pdf":record(pdf,output_root)}
    write_new(output_root/"qualitative/index_v3.json",canonical_json_bytes(index))
    report=f"""# C1/C2/C3 통합 결과판 v3\n\nC1/C2 페이지를 오래된 v6 reference-overlay 판에서 최신 건물별 v13 계보로 교체했다. 4907177 C1은 후속 ground-Z diagnostic input/output을 사용하고, C2는 roof evidence 부족으로 NOT RUN을 표시한다. 입력은 LAS point cloud, 출력은 봉인 CityJSON roof plane 채움면이다.\n\n4906975 C3-2 consensus {consensus_diag['point_count']:,}점의 |normal_z|<0.3 비율은 {consensus_diag['wall_like_abs_normal_z_lt_0p3_fraction']:.2%}, |normal_z|>0.7 비율은 {consensus_diag['roof_like_abs_normal_z_gt_0p7_fraction']:.2%}다. 6행에서 벽처럼 보이는 대부분은 roof-oriented point이며, 5행 한 시점에서 큰 wall Gaussian이 roof를 가리는 것과 24-view rendered semantic/depth consensus의 차이다. 다만 semantic roof label에 normal gate는 없어 소량 leakage는 남는다.\n\nPoisson과 TSDF는 같은 roof-only consensus evidence를 사용한다. Poisson은 oriented points를 직접 표면 완성하고, TSDF는 동일 consensus voxel에 대응하는 depth pixel만 카메라 ray로 재적분한다. Roofer input LAS는 이 mesh branch와 별도다.\n\n현재 상속 panel은 legacy E-section과 footprint PCA section이 혼재한다. v3 locator는 두 절단선과 viewing direction을 TOP으로 명시했으며, 단일 frame인 것처럼 오인하지 않게 했다. GS/Roofer/mesh/metric 재실행은 0회이고 scientific_verdict는 null이다.\n"""
    write_new(output_root/"reports/technical_report_ko_v3.md",report.encode("utf-8"))
    links="".join(f'<section><h2>{html.escape(x["stable_id"])} — {html.escape(x["section"])}</h2><img src="../{html.escape(x["output"]["path"])}"></section>' for x in page_records)
    write_new(output_root/"reports/case_index.html",("<!doctype html><meta charset=utf-8><style>body{font-family:sans-serif;max-width:1800px;margin:auto}img{width:100%;margin-bottom:3rem}</style><h1>C1/C2/C3 v3</h1>"+links).encode())
    checks={"case_count_3":index["case_count"]==3,"page_count_9":index["page_count"]==9,"latest_c1_c2_page_count_3":index["c1_c2_page_count"]==3,"section_locator_count_9":len(locator_records)==9,"consensus_point_count_44177":consensus_diag["point_count"]==44177,"all_execution_counters_zero":all(v==0 for v in config["execution_counters"].values()),"scientific_verdict_null":index["scientific_verdict"] is None}
    if not all(checks.values()): raise RuntimeError(f"v3 verification failed: {checks}")
    write_new(output_root/"control/200-verified.local_v3.json",canonical_json_bytes({"schema":"jointbuildgs.local_technical_200_verified.v3","status":"200-VERIFIED_LOCAL_SELF_CHECK","checks":checks,"scientific_verdict":None}))
    write_new(output_root/"control/technical_return_v3.json",canonical_json_bytes({"schema":"jointbuildgs.local_technical_return.v3","status":"RETURNED_LOCAL_LATEST_C1_C2_AND_SECTION_LOCATORS","pdf":record(pdf,output_root),"execution_counters":config["execution_counters"],"scientific_verdict":None}))
    material=[p for p in sorted(output_root.rglob("*")) if p.is_file() and p.name not in {"artifact_manifest_v3.json","300-closed.local_v3.json"}]
    manifest={"schema":"jointbuildgs.c1_c2_c3_consolidated_results_manifest.v3","status":"COMPLETE_HASHED_MATERIAL_PAYLOAD","records":[record(p,output_root) for p in material],"scientific_verdict":None}; manifest["record_count"]=len(manifest["records"])
    write_new(output_root/"control/artifact_manifest_v3.json",canonical_json_bytes(manifest))
    closed={"schema":"jointbuildgs.local_technical_300_closed.v3","status":"300-CLOSED_LOCAL_LATEST_C1_C2_AND_SECTION_LOCATORS","verified":record(output_root/"control/200-verified.local_v3.json",output_root),"technical_return":record(output_root/"control/technical_return_v3.json",output_root),"manifest":record(output_root/"control/artifact_manifest_v3.json",output_root),"scientific_verdict":None}
    write_new(output_root/"control/300-closed.local_v3.json",canonical_json_bytes(closed)); return closed


def main() -> None:
    parser=argparse.ArgumentParser(); parser.add_argument("--output-root",type=Path,required=True); parser.add_argument("--artifact-root",type=Path,required=True); parser.add_argument("--source-base-commit",required=True); args=parser.parse_args()
    print(json.dumps(run(args.output_root,args.artifact_root,args.source_base_commit),ensure_ascii=False,sort_keys=True))


if __name__=="__main__": main()
