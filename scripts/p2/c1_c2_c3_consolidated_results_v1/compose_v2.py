#!/usr/bin/env python3
"""Correct C1 Roofer display to filled CityJSON plane surfaces without rerunning Roofer."""
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

from scripts.p2.c1_c2_c3_consolidated_results_v1.compose import (
    build_pdf,
    canonical_json_bytes,
    record,
    sha256,
    write_new,
)
from scripts.p2.c1_c2_oracle_c3_extract_v1.contract import load_building_references
from scripts.p2.c1_c2_oracle_c3_extract_v1.render_results import _bbox, _draw_footprint, _rings_xy, _setup_3d
from src.visualization.fixed_view_qualitative import load_cityjsonseq


REPO_ROOT = Path(__file__).resolve().parents[3]
CONFIG_PATH = REPO_ROOT / "configs/p2/c1_c2_c3_consolidated_results_v1/compose_v2.json"


def load_config() -> dict[str, Any]:
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def validate_config(config: Mapping[str, Any]) -> None:
    if config.get("schema") != "jointbuildgs.p2.c1_c2_c3_consolidated_results.v2":
        raise RuntimeError("unexpected v2 config schema")
    if config.get("status") != "APPROVED_FOR_LOCAL_PRESENTATION_CORRECTION_ONLY":
        raise RuntimeError("v2 presentation correction is not active")
    if config["correction"] != {
        "target_row": 9,
        "old_display": "ROOFER_SURFACE_WIREFRAME_WITH_EVALUATION_OVERLAY",
        "new_display": "FILLED_CITYJSON_ROOF_PLANE_SURFACES_WITH_MUTED_WALLS",
        "roofer_reexecution": False,
    }:
        raise RuntimeError("row-9 correction contract drifted")
    if any(int(value) != 0 for value in config["execution_counters"].values()):
        raise RuntimeError("all v2 execution counters must remain zero")
    if config.get("scientific_verdict", "missing") is not None:
        raise RuntimeError("scientific_verdict must remain null")


def resolve_file(artifact_root: Path, relative: str, role: str) -> Path:
    path = artifact_root / relative
    if not path.is_file():
        raise RuntimeError(f"missing {role}: {path}")
    return path


def section_segments(ring: np.ndarray, center_y: float) -> list[np.ndarray]:
    points: list[np.ndarray] = []
    closed = np.vstack((ring, ring[0]))
    for first, second in zip(closed[:-1], closed[1:]):
        d1, d2 = float(first[1] - center_y), float(second[1] - center_y)
        if abs(d1) < 1e-8:
            points.append(first[[0, 2]])
        if d1 * d2 < 0.0 or abs(d2) < 1e-8:
            delta = float(second[1] - first[1])
            if abs(delta) < 1e-10:
                points.append(second[[0, 2]])
            else:
                t = (center_y - float(first[1])) / delta
                if 0.0 <= t <= 1.0:
                    points.append((first + t * (second - first))[[0, 2]])
    unique: list[np.ndarray] = []
    for point in points:
        if not any(np.linalg.norm(point - existing) < 1e-6 for existing in unique):
            unique.append(point)
    if len(unique) < 2:
        return []
    values = np.asarray(unique)
    distances = np.linalg.norm(values[:, None, :] - values[None, :, :], axis=2)
    first, second = np.unravel_index(int(np.argmax(distances)), distances.shape)
    return [np.vstack((values[first], values[second]))]


def render_filled_plane_panel(destination: Path, view: str, reference: Any, surfaces: Sequence[Any]) -> dict[str, int]:
    bbox = _bbox(reference)
    footprint_rings = _rings_xy(reference)
    roof_surfaces = [surface for surface in surfaces if surface.semantic == "RoofSurface" and len(surface.xyz) >= 3]
    wall_surfaces = [surface for surface in surfaces if surface.semantic == "WallSurface" and len(surface.xyz) >= 3]
    other_surfaces = [surface for surface in surfaces if surface.semantic not in {"RoofSurface", "WallSurface"} and len(surface.xyz) >= 3]
    if not roof_surfaces:
        raise RuntimeError("sealed C1 CityJSON has no RoofSurface planes")
    all_xyz = np.concatenate([surface.xyz for surface in surfaces if len(surface.xyz) >= 3])
    z0, z1 = float(np.min(all_xyz[:, 2])), float(np.max(all_xyz[:, 2]))
    pad_z = max((z1 - z0) * 0.10, 1.0)
    zlim = (z0 - pad_z, z1 + pad_z)
    ground_z = float(np.quantile(all_xyz[:, 2], 0.02))
    roof_colors = plt.get_cmap("tab20")(np.linspace(0.02, 0.82, max(len(roof_surfaces), 2)))
    figure = plt.figure(figsize=(6.4, 4.8), dpi=150)
    ax = figure.add_subplot(111, projection="3d", proj_type="ortho") if view.startswith("OBLIQUE") else figure.add_subplot(111)

    if view == "TOP":
        polygons = [surface.xyz[:, :2] for surface in roof_surfaces]
        ax.add_collection(PolyCollection(polygons, facecolors=roof_colors[:len(polygons)], edgecolors="#173f73", linewidths=1.0, alpha=0.86))
        for surface in wall_surfaces + other_surfaces:
            closed = np.vstack((surface.xyz, surface.xyz[0]))
            ax.plot(closed[:, 0], closed[:, 1], color="#777777", linewidth=0.45, alpha=0.55)
        pad = max(max(bbox.width, bbox.height) * 0.25, 4.0)
        ax.set_xlim(bbox.min_x - pad, bbox.max_x + pad)
        ax.set_ylim(bbox.min_y - pad, bbox.max_y + pad)
        ax.set_aspect("equal")
        ax.set_xlabel("Easting")
        ax.set_ylabel("Northing")
    elif view.startswith("OBLIQUE"):
        ax.add_collection3d(Poly3DCollection([surface.xyz for surface in wall_surfaces], facecolors="#c7c7c7", edgecolors="#686868", linewidths=0.35, alpha=0.35))
        ax.add_collection3d(Poly3DCollection([surface.xyz for surface in other_surfaces], facecolors="#b5b5b5", edgecolors="#686868", linewidths=0.35, alpha=0.25))
        ax.add_collection3d(Poly3DCollection([surface.xyz for surface in roof_surfaces], facecolors=roof_colors[:len(roof_surfaces)], edgecolors="#173f73", linewidths=0.75, alpha=0.90))
        _setup_3d(ax, bbox, zlim, view)
    else:
        center_y = float(np.median(np.concatenate([ring[:, 1] for ring in footprint_rings])))
        for index, surface in enumerate(roof_surfaces):
            for segment in section_segments(surface.xyz, center_y):
                ax.plot(segment[:, 0], segment[:, 1], color=roof_colors[index], linewidth=4.2, solid_capstyle="round")
        for surface in wall_surfaces + other_surfaces:
            for segment in section_segments(surface.xyz, center_y):
                ax.plot(segment[:, 0], segment[:, 1], color="#777777", linewidth=1.5, alpha=0.70)
        pad = max(bbox.width * 0.25, 4.0)
        ax.set_xlim(bbox.min_x - pad, bbox.max_x + pad)
        ax.set_ylim(*zlim)
        ax.set_xlabel("principal E section")
        ax.set_ylabel("Z (m)")
    _draw_footprint(ax, footprint_rings, view, ground_z)
    ax.set_title(f"C1 Roofer filled plane surfaces | {view.replace('PRINCIPAL_SECTION', 'SECTION')}\nroof planes={len(roof_surfaces)}; walls muted", fontsize=10.5, fontweight="bold")
    figure.tight_layout()
    destination.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(destination, metadata={"Software": "JointBuildGS sealed CityJSON filled-plane renderer"})
    plt.close(figure)
    return {"roof_plane_count": len(roof_surfaces), "wall_surface_count": len(wall_surfaces), "other_surface_count": len(other_surfaces)}


def run(output_root: Path, artifact_root: Path, source_base_commit: str) -> dict[str, Any]:
    config = load_config()
    validate_config(config)
    if output_root.exists() and any(output_root.iterdir()):
        raise RuntimeError(f"add-once v2 output is not empty: {output_root}")
    output_root.mkdir(parents=True, exist_ok=True)
    v1_root = artifact_root / config["sources"]["v1_relative_root"]
    if json.loads((v1_root / "control/300-closed.local_v1.json").read_text(encoding="utf-8"))["status"] != "300-CLOSED_LOCAL_CONSOLIDATED_RESULTS":
        raise RuntimeError("v1 consolidated source is not closed")
    lod2_path = resolve_file(artifact_root, config["sources"]["lod2_relative_path"], "LoD2 reference")
    references = load_building_references(lod2_path, config["building_ids"])
    cityjson_paths = {
        stable_id: resolve_file(artifact_root, config["sources"][f"c1_{stable_id.removeprefix('DEBY_LOD2_')}_cityjson_relative_path"], f"C1 CityJSON {stable_id}")
        for stable_id in config["building_ids"]
    }

    plane_panels: dict[str, list[Path]] = {}
    cityjson_lineage = []
    panel_lineage = []
    plane_counts: dict[str, dict[str, int]] = {}
    for stable_id in config["building_ids"]:
        surfaces = load_cityjsonseq(cityjson_paths[stable_id])
        cityjson_lineage.append({"stable_id": stable_id, **record(cityjson_paths[stable_id], artifact_root)})
        plane_panels[stable_id] = []
        for view in config["views"]:
            panel = output_root / f"qualitative/c1_roofer_filled/{stable_id}/C1_ROOFER_FILLED__{view}.png"
            counts = render_filled_plane_panel(panel, view, references[stable_id], surfaces)
            plane_panels[stable_id].append(panel)
            plane_counts[stable_id] = counts
            panel_lineage.append({"stable_id": stable_id, "view": view, "source_cityjson_sha256": sha256(cityjson_paths[stable_id]), "output": record(panel, output_root), **counts})

    page_records = []
    page_paths = []
    for source_page in sorted((v1_root / "pages").glob("*.png")):
        destination = output_root / "pages" / source_page.name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source_page, destination)
        section = "C1_C2_EXISTING" if "_C1_C2" in source_page.name else ("C3_1_SEM" if "_C3_1_SEM" in source_page.name else "C3_2_SEM_DEPTH")
        stable_id = next(stable for stable in config["building_ids"] if stable in source_page.name)
        exact_copy = True
        if section != "C1_C2_EXISTING":
            image = cv2.imread(str(destination), cv2.IMREAD_COLOR)
            if image is None or image.shape[:2] != (8820, 4460):
                raise RuntimeError(f"unexpected v1 C3 page geometry: {destination}")
            y0, cell_h, label_w, cell_w = 180 + 8 * 720, 720, 620, 960
            for column, panel in enumerate(plane_panels[stable_id]):
                replacement = cv2.imread(str(panel), cv2.IMREAD_COLOR)
                if replacement is None:
                    raise RuntimeError(f"filled plane panel unreadable: {panel}")
                replacement = cv2.resize(replacement, (cell_w, cell_h), interpolation=cv2.INTER_AREA)
                x0 = label_w + column * cell_w
                image[y0:y0 + cell_h, x0:x0 + cell_w] = replacement
            if not cv2.imwrite(str(destination), image, [cv2.IMWRITE_PNG_COMPRESSION, 5]):
                raise RuntimeError(f"failed to write corrected page: {destination}")
            exact_copy = False
        page_paths.append(destination)
        page_records.append({"page": len(page_records) + 1, "stable_id": stable_id, "section": section, "source_v1": record(source_page, artifact_root), "output": record(destination, output_root), "exact_copy": exact_copy, "c1_roofer_row_display": "FILLED_CITYJSON_PLANE_SURFACES" if section != "C1_C2_EXISTING" else "INHERITED_C1_C2_PAGE"})

    pdf_path = output_root / "reports/C1_C2_C3_qualitative_results_v2_filled_c1_roofer.pdf"
    build_pdf(page_paths, pdf_path)
    links = "".join(f'<section><h2>Page {item["page"]}: {html.escape(item["stable_id"])} — {html.escape(item["section"])}</h2><img src="../{html.escape(item["output"]["path"])}"></section>' for item in page_records)
    write_new(output_root / "reports/case_index.html", ("<!doctype html><meta charset=utf-8><title>C1/C2/C3 v2 filled C1 Roofer</title><style>body{font-family:sans-serif;max-width:1800px;margin:auto}img{width:100%;margin-bottom:3rem}</style><h1>C1/C2/C3 v2 — filled C1 Roofer plane surfaces</h1>" + links).encode("utf-8"))
    index = {
        "schema": "jointbuildgs.c1_c2_c3_consolidated_results_index.v2",
        "status": "COMPLETE_C1_ROOFER_FILLED_PLANE_DISPLAY_CORRECTION",
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "source_base_commit": source_base_commit,
        "case_count": 3,
        "page_count": 9,
        "corrected_c3_page_count": 6,
        "filled_c1_roofer_panel_count": 12,
        "row_9_semantics": "SEALED_C1_CITYJSON_ROOF_PLANE_POLYGONS_FILLED; WALLSURFACE_MUTED; ORANGE_DASHED_GT_FOOTPRINT_CONTEXT",
        "cityjson_lineage": cityjson_lineage,
        "filled_panel_lineage": panel_lineage,
        "plane_counts": plane_counts,
        "pages": page_records,
        "pdf": record(pdf_path, output_root),
        "execution_counters": config["execution_counters"],
        "official_G3_G4_PASS_usable": None,
        "scientific_verdict": None,
    }
    write_new(output_root / "qualitative/index_v2.json", canonical_json_bytes(index))
    report = """# C1/C2/C3 통합 정성 결과판 v2 — C1 Roofer plane surface 교정

v1의 C3 9행은 실제 C1 CityJSONSeq Roofer output을 사용했지만 roof polygon을 wireframe 위주로 표시해 plane의 합이라는 의미가 약했다. v2는 같은 봉인 CityJSONSeq를 다시 읽어 RoofSurface polygon을 plane별 색으로 채우고 WallSurface는 회색 반투명으로 표시했다. orange dashed line은 GT footprint context이며 Roofer plane 자체가 아니다.

C1/C2 기존 3쪽과 C3의 나머지 11행은 v1에서 그대로 상속했다. Roofer, GS, Poisson, TSDF, G2, metric은 재실행하지 않았다. scientific_verdict는 null이다.
"""
    write_new(output_root / "reports/technical_report_ko_v2.md", report.encode("utf-8"))
    checks = {
        "case_count_3": index["case_count"] == 3,
        "page_count_9": index["page_count"] == 9,
        "corrected_c3_page_count_6": index["corrected_c3_page_count"] == 6,
        "filled_c1_roofer_panel_count_12": len(panel_lineage) == 12,
        "all_cityjson_have_roof_planes": all(value["roof_plane_count"] > 0 for value in plane_counts.values()),
        "all_execution_counters_zero": all(int(value) == 0 for value in config["execution_counters"].values()),
        "scientific_verdict_null": index["scientific_verdict"] is None,
    }
    if not all(checks.values()):
        raise RuntimeError(f"v2 verification failed: {checks}")
    write_new(output_root / "control/200-verified.local_v2.json", canonical_json_bytes({"schema": "jointbuildgs.local_technical_200_verified.v2", "status": "200-VERIFIED_LOCAL_SELF_CHECK", "checks": checks, "scientific_verdict": None}))
    write_new(output_root / "control/technical_return_v2.json", canonical_json_bytes({"schema": "jointbuildgs.local_technical_return.v2", "status": "RETURNED_LOCAL_FILLED_C1_ROOFER_DISPLAY", "pdf": record(pdf_path, output_root), "execution_counters": config["execution_counters"], "scientific_verdict": None}))
    material = [path for path in sorted(output_root.rglob("*")) if path.is_file() and path.name not in {"artifact_manifest_v2.json", "300-closed.local_v2.json"}]
    manifest = {"schema": "jointbuildgs.c1_c2_c3_consolidated_results_manifest.v2", "status": "COMPLETE_HASHED_MATERIAL_PAYLOAD", "records": [record(path, output_root) for path in material], "scientific_verdict": None}
    manifest["record_count"] = len(manifest["records"])
    write_new(output_root / "control/artifact_manifest_v2.json", canonical_json_bytes(manifest))
    closed = {"schema": "jointbuildgs.local_technical_300_closed.v2", "status": "300-CLOSED_LOCAL_FILLED_C1_ROOFER_DISPLAY", "verified": record(output_root / "control/200-verified.local_v2.json", output_root), "technical_return": record(output_root / "control/technical_return_v2.json", output_root), "manifest": record(output_root / "control/artifact_manifest_v2.json", output_root), "scientific_verdict": None}
    write_new(output_root / "control/300-closed.local_v2.json", canonical_json_bytes(closed))
    return closed


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--source-base-commit", required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.output_root, args.artifact_root, args.source_base_commit), ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
