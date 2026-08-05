#!/usr/bin/env python3
"""Render corrected-roofline C3-1/C3-2/C4 sheets from exact sealed results."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import html
import json
from pathlib import Path
import textwrap
from typing import Any, Mapping, Sequence

import cv2
import numpy as np
import open3d as o3d
from PIL import Image

from scripts.p2.c1_c2_c3_consolidated_results_v1.compose_v4 import lod2_zlim, shifted_lod2
from scripts.p2.c1_c2_c3_consolidated_results_v1.compose_v5 import VIEWS, point_panel, surface_faces, triangle_panel
from scripts.p2.selected10_c1_c4_presentation_v1.c1_c2_oracle import (
    jsonl_bytes,
    natural_zlim,
    point_panels,
    surface_panels_bound,
)
from scripts.p2.selected10_c1_c4_presentation_v1.render import (
    native_semantic_panels,
    placeholder,
    record,
    roofline_panels,
    sha256_file,
    verify_exact,
    write_json,
    write_new,
)
from scripts.p2.utarget199_contract_results_v1.contract import load_config as load_census_config
from scripts.p2.utarget199_contract_results_v1.render_case_sheets import BBox, PointSet, camera_context, city_file, load_geometry
from scripts.p2.utarget199_c1_c4_matrix_v1.render import postprocess_tables
from scripts.p2.utarget199_presentation_v5.render import load_references
from scripts.p2.c4_utarget199_postprocess_v1.render_case_sheets import _checkpoint_arrays
from src.visualization.fixed_view_qualitative import load_las_points


REPO = Path(__file__).resolve().parents[3]
CONFIG_PATH = REPO / "configs/p2/selected10_c1_c4_presentation_v1/c3_c4_sheets_v1.json"


def load_config(path: Path = CONFIG_PATH) -> dict[str, Any]:
    body = json.loads(path.read_text(encoding="utf-8"))
    parent = body.pop("extends", None)
    if parent is None:
        return body
    return {**load_config(path.parent / str(parent)), **body}


def validate_config(config: Mapping[str, Any]) -> None:
    if config.get("schema") not in {
        "jointbuildgs.p2.selected10_c3_1_c3_2_c4_sheets.v1",
        "jointbuildgs.p2.selected10_c3_1_c3_2_c4_sheets.v2",
        "jointbuildgs.p2.selected10_c3_1_c3_2_c4_sheets.v3",
    }:
        raise RuntimeError("unexpected C3/C4 sheet schema")
    if config.get("status") != "APPROVED_BY_DIRECT_USER_INSTRUCTION":
        raise RuntimeError("C3/C4 presentation is not authorized")
    if len(config["building_ids"]) != 10 or len(set(config["building_ids"])) != 10:
        raise RuntimeError("selected10 membership drifted")
    if [row["condition_id"] for row in config["conditions"]] != ["C3_1_SEM", "C3_2_SEM_DEPTH", "C4_EXISTING_ALS"]:
        raise RuntimeError("condition order drifted")
    if tuple(config["display"]["views"]) != VIEWS or len(config["display"]["rows"]) != 7:
        raise RuntimeError("seven-row/four-view contract drifted")
    if config["display"]["separate_principal_page_count"] != 0 or not config["display"]["missing_not_run_preserved"]:
        raise RuntimeError("presentation missingness/section boundary drifted")
    if any(int(value) != (30 if key == "presentation_pages" else 0) for key, value in config["execution_counters"].items()):
        raise RuntimeError("presentation-only execution counters drifted")
    if config.get("official_PASS_usable", "missing") is not None or config.get("scientific_verdict", "missing") is not None:
        raise RuntimeError("official PASS and scientific verdict must remain null")
    if not config["schema"].endswith(".v1"):
        expected_version = config["schema"].rsplit(".", 1)[-1]
        if config.get("output_version") != expected_version:
            raise RuntimeError("output version differs from schema")
        if config["display"].get("roofline_support_alignment") != "CURRENT_C1_CLASS6_PIXEL_RESIDUAL":
            raise RuntimeError("v2 roofline support check missing")


def condition_geometry(
    cache: dict[tuple[str, str], dict[str, Any]],
    condition: str,
    row: Mapping[str, Any],
    units: Mapping[str, Any],
    root: Path,
) -> dict[str, Any]:
    operation_id = row.get("operation_unit_id")
    if not operation_id:
        return {"points": PointSet.empty(), "surfaces": [], "roofprint": []}
    key = (condition, str(operation_id))
    if key not in cache:
        unit = units.get(operation_id)
        if unit is None or unit.get("operation_unit_id") != operation_id or unit.get("condition_id") != condition:
            raise RuntimeError(f"operation identity mismatch: {condition} {operation_id}")
        cache[key] = load_geometry(root, unit)
    return cache[key]


def mesh_or_consensus_panels(
    root: Path,
    path: Path,
    reference: Any,
    principal_zlim: tuple[float, float],
    prefix: str,
    role: str,
) -> list[Path]:
    if not path.is_file():
        return [placeholder(root / f"{prefix}_{view}.png", role, "NOT_RUN", view) for view in VIEWS]
    result = []
    if role.endswith("MESH INPUT"):
        cloud = o3d.io.read_point_cloud(str(path))
        xyz = np.asarray(cloud.points, dtype=np.float64)
        colors = np.tile(np.asarray([[0.49, 0.25, 0.77]]), (len(xyz), 1))
        natural = natural_zlim(PointSet(xyz, None), [])
        for view in VIEWS:
            panel = root / f"{prefix}_{view}.png"
            point_panel(panel, xyz, colors, reference, view, principal_zlim if view == "PRINCIPAL_SECTION" else natural)
            result.append(panel)
    else:
        mesh = o3d.io.read_triangle_mesh(str(path))
        vertices = np.asarray(mesh.vertices, dtype=np.float64)
        triangles = np.asarray(mesh.triangles, dtype=np.int64)
        faces = [vertices[index] for index in triangles]
        colors = [(0.49, 0.25, 0.77)] * len(faces)
        natural = natural_zlim(None, [type("SurfaceProxy", (), {"xyz": vertices})()])
        for view in VIEWS:
            panel = root / f"{prefix}_{view}.png"
            triangle_panel(panel, faces, colors, reference, view, principal_zlim if view == "PRINCIPAL_SECTION" else natural)
            result.append(panel)
    return result


def compose_sheet(
    path: Path,
    stable_id: str,
    condition_title: str,
    subtitle: str,
    rows: Sequence[tuple[str, str, Sequence[Path]]],
) -> None:
    cell_w, cell_h, label_w, header_h = 960, 720, 430, 150
    canvas = np.full((header_h + len(rows) * cell_h, label_w + 4 * cell_w, 3), 255, dtype=np.uint8)
    cv2.putText(canvas, stable_id, (24, 42), cv2.FONT_HERSHEY_SIMPLEX, 1.05, (20, 20, 20), 2, cv2.LINE_AA)
    cv2.putText(canvas, condition_title, (24, 82), cv2.FONT_HERSHEY_SIMPLEX, 0.78, (20, 20, 20), 2, cv2.LINE_AA)
    cv2.putText(canvas, subtitle, (24, 122), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (60, 60, 60), 1, cv2.LINE_AA)
    for column, label in enumerate(("TOP + A/B VIEW", "OBLIQUE 1", "OBLIQUE 2", "PCA PRINCIPAL")):
        cv2.putText(canvas, label, (label_w + column * cell_w + 24, 122), cv2.FONT_HERSHEY_SIMPLEX, 0.74, (20, 20, 20), 2, cv2.LINE_AA)
    for row_index, (label, status, panels) in enumerate(rows):
        if len(panels) != 4:
            raise RuntimeError(f"row lacks four panels: {label}")
        y0 = header_h + row_index * cell_h
        cv2.rectangle(canvas, (0, y0), (label_w, y0 + cell_h), (242, 244, 247), -1)
        cv2.putText(canvas, f"{row_index + 1:02d} {label}", (18, y0 + 52), cv2.FONT_HERSHEY_SIMPLEX, 0.66, (25, 25, 25), 2, cv2.LINE_AA)
        lines = textwrap.wrap(status.replace("_", "_ "), width=42, break_long_words=False, break_on_hyphens=False)
        for index, line in enumerate(lines[:8]):
            cv2.putText(canvas, line.replace("_ ", "_"), (18, y0 + 96 + index * 32), cv2.FONT_HERSHEY_SIMPLEX, 0.50, (40, 40, 40), 1, cv2.LINE_AA)
        for column, panel in enumerate(panels):
            image = cv2.imread(str(panel), cv2.IMREAD_COLOR)
            if image is None:
                raise RuntimeError(f"panel unreadable: {panel}")
            image = cv2.resize(image, (cell_w, cell_h), interpolation=cv2.INTER_AREA)
            x0 = label_w + column * cell_w
            canvas[y0:y0 + cell_h, x0:x0 + cell_w] = image
    path.parent.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(str(path), canvas, [cv2.IMWRITE_PNG_COMPRESSION, 5]):
        raise RuntimeError(f"sheet write failed: {path}")


def run(output_root: Path, artifact_root: Path, source_commit: str, run_id: str, config_path: Path = CONFIG_PATH) -> dict[str, Any]:
    config = load_config(config_path)
    validate_config(config)
    if output_root.exists() and any(output_root.iterdir()):
        raise RuntimeError("fresh add-once C3/C4 sheet namespace required")
    output_root.mkdir(parents=True, exist_ok=True)
    sources = config["sources"]
    hashes = config["exact_hashes"]
    c3_root = artifact_root / sources["c3_postprocess_relative_root"]
    c4_root = artifact_root / sources["c4_postprocess_relative_root"]
    source_checks = {
        "c3_metrics": verify_exact(c3_root / "results/building_condition_metrics_v1.jsonl", hashes["c3_metrics"], "C3 metrics"),
        "c4_metrics": verify_exact(c4_root / "results/building_c4_metrics_v1.jsonl", hashes["c4_metrics"], "C4 metrics"),
    }
    support_by_id: dict[str, PointSet] = {}
    if "c1_support_relative_root" in sources:
        support_root = artifact_root / sources["c1_support_relative_root"]
        closure_path = support_root / "control/300-closed.local_v1.json"
        manifest_path = support_root / "control/artifact_manifest_v1.json"
        source_checks["c1_support_closure"] = verify_exact(
            closure_path, hashes["c1_support_closure"], "C1 support closure"
        )
        source_checks["c1_support_manifest"] = verify_exact(
            manifest_path, hashes["c1_support_manifest"], "C1 support manifest"
        )
        support_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        support_records = {row["path"]: row for row in support_manifest["records"]}
        support_checks = []
        for stable_id in config["building_ids"]:
            relative = f"operations/C1_LIDAR_GT_FOOTPRINT_ORACLE/{stable_id}/work/input.las"
            expected = support_records.get(relative)
            if expected is None:
                raise RuntimeError(f"C1 support input absent from exact manifest: {relative}")
            input_path = support_root / relative
            support_checks.append(verify_exact(input_path, expected["sha256"], f"C1 support {stable_id}"))
            support_by_id[stable_id] = load_las_points(input_path)
        source_checks["c1_support_inputs"] = support_checks
    checkpoints = {}
    shift = np.asarray(config["frame"]["local_shift_xyz"], dtype=np.float64)
    for condition in config["conditions"]:
        key = condition["checkpoint_key"]
        path = artifact_root / sources[key]
        source_checks[key] = verify_exact(path, hashes[key], key)
        checkpoints[condition["condition_id"]] = _checkpoint_arrays(path, shift)
    lod2_paths = [artifact_root / item for item in sources["lod2_relative_paths"]]
    source_checks["lod2"] = [verify_exact(path, digest, "LoD2") for path, digest in zip(lod2_paths, hashes["lod2"])]
    tables = {}
    units = {}
    for condition in config["conditions"]:
        condition_id = condition["condition_id"]
        if condition_id.startswith("C3_"):
            tables[condition_id], units[condition_id] = postprocess_tables(c3_root, "building_condition_metrics", condition_id)
        else:
            tables[condition_id], units[condition_id] = postprocess_tables(c4_root, "building_c4_metrics", condition_id)
    references = load_references(lod2_paths, config["building_ids"])
    census = load_census_config()
    _best, cameras, camera_model, scene_ref = camera_context(artifact_root, census)
    crosswalk = json.loads((REPO / sources["exact_view_manifest_git_path"]).read_text(encoding="utf-8"))
    visible = {str(row["basename"]) for row in crosswalk["rows"]}
    if len(visible) != 937:
        raise RuntimeError("exact camera membership drifted")
    geometry_cache: dict[tuple[str, str], dict[str, Any]] = {}
    pages_by_condition: dict[str, list[Path]] = {row["condition_id"]: [] for row in config["conditions"]}
    page_records = []
    binding_rows = []
    camera_rows = []
    mesh_root = artifact_root / sources["c3_mesh_diagnostic_relative_root"]
    for condition in config["conditions"]:
        condition_id = condition["condition_id"]
        result_root = c3_root if condition_id.startswith("C3_") else c4_root
        for page_index, stable_id in enumerate(config["building_ids"], 1):
            row = tables[condition_id][stable_id]
            reference = references[stable_id]
            lod2_surfaces = shifted_lod2(reference, float(config["frame"]["lod2_display_vertical_shift_m"]))
            principal_zlim = lod2_zlim(lod2_surfaces)
            bbox = BBox(*(float(row[key]) for key in ("bbox_min_x", "bbox_min_y", "bbox_max_x", "bbox_max_y")))
            viewport = bbox.padded(0.35, 5.0)
            geometry = condition_geometry(geometry_cache, condition_id, row, units[condition_id], result_root)
            panel_root = output_root / f"qualitative/{condition_id}/{stable_id}/panels"
            roofline, camera_receipt = roofline_panels(
                panel_root,
                artifact_root,
                census,
                reference,
                cameras,
                camera_model,
                scene_ref,
                visible,
                stable_id,
                support=support_by_id.get(stable_id),
                support_alignment_threshold_px=float(config["display"].get("roofline_support_alignment_threshold_px", 20.0)),
            )
            for item in camera_receipt:
                camera_rows.append({**item, "condition_id": condition_id})
            semantic = native_semantic_panels(panel_root, checkpoints[condition_id], viewport, reference, principal_zlim, "gs_semantic")
            if len(geometry["points"].xyz):
                roofer_input = point_panels(panel_root, geometry["points"], reference, principal_zlim, "roofer_input")
                input_status = f"component input shown; association={row.get('association_status')}"
            else:
                roofer_input = [placeholder(panel_root / f"roofer_input_{view}.png", "HONEST ROOFER INPUT", "NO_ASSOCIATED_COMPONENT", view) for view in VIEWS]
                input_status = "NO_ASSOCIATED_COMPONENT; Roofer not run for this building"
            building_output = row.get("G0_generated") is True and row.get("one_to_one_building_component") is True
            output_status = f"association={row.get('association_status')} G0={row.get('G0_generated')} G1={row.get('G1_schema_semantic')}"
            if building_output:
                roofer_output = surface_panels_bound(panel_root, geometry["surfaces"], reference, principal_zlim, "roofer_output", "NO_ROOF_GEOMETRY")
            else:
                roofer_output = [placeholder(panel_root / f"roofer_output_{view}.png", "HONEST ROOFER OUTPUT", "NO_BUILDING_LEVEL_OUTPUT", view) for view in VIEWS]
                output_status += "; component output is not relabeled as building output"
            condition_mesh = mesh_root / f"conditions/{condition_id}/buildings/{stable_id}"
            consensus_path = condition_mesh / "shared_view_roof_consensus_points_v1.ply"
            tsdf_path = condition_mesh / "tsdf_roof_mesh_v1.ply"
            mesh_input = mesh_or_consensus_panels(panel_root, consensus_path, reference, principal_zlim, "mesh_input", f"{condition_id} MESH INPUT")
            tsdf = mesh_or_consensus_panels(panel_root, tsdf_path, reference, principal_zlim, "tsdf_output", f"{condition_id} TSDF OUTPUT")
            lod2 = surface_panels_bound(panel_root, lod2_surfaces, reference, principal_zlim, "lod2", "MISSING")
            rows_for_page = [
                ("2024 RGB + ROOFLINE", "yellow=2022 LoD2; cyan=current C1 class-6; clipped rings not connected", roofline),
                ("ORIENTED GS SEMANTIC", "opacity>=0.1; in-plane scale<=2m; quaternion ellipse display proxy", semantic),
                ("HONEST ROOFER INPUT", input_status, roofer_input),
                ("HONEST ROOFER OUTPUT", output_status, roofer_output),
                ("SEALED MESH INPUT", "AVAILABLE sealed diagnostic" if consensus_path.is_file() else "NOT_RUN", mesh_input),
                ("SEALED TSDF OUTPUT", "AVAILABLE sealed diagnostic" if tsdf_path.is_file() else "NOT_RUN", tsdf),
                ("2022 LoD2 REFERENCE", "epoch context; C4 comparison is prior-related diagnostic only", lod2),
            ]
            output_version = str(config.get("output_version", "v1"))
            page = output_root / f"qualitative/pages/{condition_id}/{page_index:02d}_{stable_id}_{condition_id}_7row_4view_{output_version}.png"
            subtitle = f"honest roofprint-free Stage3 | principal Z={principal_zlim[0]:.1f}..{principal_zlim[1]:.1f}m from LoD2 | PASS=null"
            compose_sheet(page, stable_id, condition["title"], subtitle, rows_for_page)
            pages_by_condition[condition_id].append(page)
            page_records.append({"condition_id": condition_id, "stable_id": stable_id, "page": record(page, output_root), "scientific_verdict": None})
            operation_id = row.get("operation_unit_id")
            unit = units[condition_id].get(operation_id) if operation_id else None
            input_record = (unit or {}).get("input")
            output_path = city_file(result_root / unit["output_directory"]) if unit else None
            output_record = record(output_path, result_root) if output_path else None
            binding_rows.append({
                "condition_id": condition_id,
                "stable_id": stable_id,
                "operation_unit_id": operation_id,
                "association_status": row.get("association_status"),
                "one_to_one_building_component": row.get("one_to_one_building_component"),
                "G0_generated": row.get("G0_generated"),
                "input_sha256": None if input_record is None else input_record.get("sha256"),
                "component_output_sha256": None if output_record is None else output_record.get("sha256"),
                "displayed_as_building_output": building_output,
                "checkpoint_sha256": hashes[condition["checkpoint_key"]],
                "metric_file_sha256": hashes["c3_metrics" if condition_id.startswith("C3_") else "c4_metrics"],
                "official_PASS_usable": None,
                "scientific_verdict": None,
            })
            print(f"rendered {condition_id} {page_index}/10 {stable_id}", flush=True)
    write_new(output_root / "receipts/condition_building_binding_v1.jsonl", jsonl_bytes(binding_rows))
    write_new(output_root / "receipts/roofline_camera_coverage_v1.jsonl", jsonl_bytes(camera_rows))
    write_new(output_root / "qualitative/page_manifest_v1.jsonl", jsonl_bytes(page_records))
    pdf_records = {}
    all_pages = []
    for condition_id, pages in pages_by_condition.items():
        output_version = str(config.get("output_version", "v1"))
        pdf = output_root / f"reports/P2_SELECTED10_{condition_id}_7row_4view_{output_version}.pdf"
        pdf.parent.mkdir(parents=True, exist_ok=True)
        images = [Image.open(path).convert("RGB") for path in pages]
        images[0].save(pdf, "PDF", save_all=True, append_images=images[1:], resolution=150.0, quality=88)
        for image in images:
            image.close()
        pdf_records[condition_id] = record(pdf, output_root)
        all_pages.extend(pages)
    output_version = str(config.get("output_version", "v1"))
    combined = output_root / f"reports/P2_SELECTED10_C3_1_C3_2_C4_30page_{output_version}.pdf"
    images = [Image.open(path).convert("RGB") for path in all_pages]
    images[0].save(combined, "PDF", save_all=True, append_images=images[1:], resolution=150.0, quality=88)
    for image in images:
        image.close()
    links = "".join(
        f'<article><h2>{html.escape(row["condition_id"])} — {html.escape(row["stable_id"])}</h2><a href="../{row["page"]["path"]}"><img loading="lazy" src="../{row["page"]["path"]}"></a></article>'
        for row in page_records
    )
    write_new(output_root / "reports/index.html", ("<!doctype html><html lang='ko'><meta charset='utf-8'><style>body{font-family:sans-serif;max-width:1800px;margin:auto}img{width:100%}article{border-top:5px solid #222;margin:3rem 0}</style><h1>Selected 10 C3-1 / C3-2 / C4</h1><p>Corrected roofline; exact honest Stage3 results; missing/not-run retained; principal Z from LoD2 only.</p>" + links).encode("utf-8"))
    manifest_material = [path for path in sorted(output_root.rglob("*")) if path.is_file() and path.name not in {"artifact_manifest_v1.json", "300-closed.local_v1.json"}]
    manifest = {
        "schema": f"jointbuildgs.p2.selected10_c3_1_c3_2_c4_sheets.manifest.{output_version}",
        "status": "COMPLETE_HASHED_PRESENTATION_ONLY",
        "source_commit": source_commit,
        "run_id": run_id,
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "page_count": len(page_records),
        "records": [record(path, output_root) for path in manifest_material],
        "source_checks": source_checks,
        "official_PASS_usable": None,
        "scientific_verdict": None,
    }
    write_json(output_root / "control/artifact_manifest_v1.json", manifest)
    closed = {
        "schema": f"jointbuildgs.p2.selected10_c3_1_c3_2_c4_sheets.closed.{output_version}",
        "status": "300-CLOSED_LOCAL_PRESENTATION_ONLY",
        "page_count": len(page_records),
        "condition_pdfs": pdf_records,
        "combined_pdf": record(combined, output_root),
        "gallery": record(output_root / "reports/index.html", output_root),
        "roofline_all_full_ring_projected": all(row["status"] == "PROJECTED" for row in camera_rows),
        "roofline_projection_supported_count": sum(row.get("support_alignment_status") == "PROJECTION_SUPPORTED" for row in camera_rows),
        "roofline_reference_support_alignment_uncertain_count": sum(row.get("support_alignment_status") == "REFERENCE_SUPPORT_ALIGNMENT_UNCERTAIN" for row in camera_rows),
        "gs_training_invocations": 0,
        "roofer_invocations": 0,
        "tsdf_invocations": 0,
        "metric_recomputations": 0,
        "official_PASS_usable": None,
        "scientific_verdict": None,
    }
    write_json(output_root / "control/300-closed.local_v1.json", closed)
    return closed


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--config", type=Path, default=CONFIG_PATH)
    args = parser.parse_args()
    print(json.dumps(run(args.output_root, args.artifact_root, args.source_commit, args.run_id, args.config), sort_keys=True))


if __name__ == "__main__":
    main()
