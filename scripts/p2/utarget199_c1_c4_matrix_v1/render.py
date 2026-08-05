#!/usr/bin/env python3
"""Render one attached-style full-resolution C1-C4 matrix per U_target building."""

from __future__ import annotations

from collections import defaultdict
import argparse
import hashlib
import html
import json
from pathlib import Path
from typing import Any, Mapping

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from PIL import Image

from scripts.p2.c4_utarget199_postprocess_v1.render_case_sheets import (
    _checkpoint_arrays,
    _lod2_zlim,
    _native_crop,
    plot_native_mesh,
    plot_native_top,
    plot_pca_section,
)
from scripts.p2.c1_c2_c3_consolidated_results_v1.compose_v5 import draw_section_locator
from scripts.p2.utarget199_contract_results_v1.render_case_sheets import (
    PointSet,
    camera_context,
    load_geometry,
    plot_oblique,
    plot_top_output,
    plot_top_points,
    rgb_crop,
    rows,
)
from scripts.p2.utarget199_contract_results_v1.contract import load_config as load_census_config
from scripts.p2.utarget199_presentation_v5.render import load_references
from src.visualization.fixed_view_qualitative import BBox


REPO = Path(__file__).resolve().parents[3]
CONFIG_PATH = REPO / "configs/p2/utarget199_c1_c4_matrix_v1/render_v1.json"


def load_config() -> dict[str, Any]:
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def sha256_file(path: Path) -> tuple[int, str]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
            size += len(chunk)
    return size, digest.hexdigest()


def record(path: Path, root: Path) -> dict[str, Any]:
    size, digest = sha256_file(path)
    return {"path": path.relative_to(root).as_posix(), "bytes": size, "sha256": digest}


def write_new(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(data)


def write_json(path: Path, body: Mapping[str, Any]) -> None:
    write_new(path, (json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode())


def verify_config(config: Mapping[str, Any]) -> None:
    if config.get("schema") != "jointbuildgs.p2.utarget199_c1_c4_matrix.v1":
        raise RuntimeError("unexpected 199-building matrix schema")
    if config.get("status") != "APPROVED_BY_USER_FOR_ATTACHED_STYLE_199_BUILDING_PRESENTATION":
        raise RuntimeError("199-building matrix task is not active")
    scope = config["scope"]
    if scope["building_count"] != 199 or scope["full_resolution_page_count"] != 199:
        raise RuntimeError("199-building matrix scope drifted")
    if scope["missing_not_run_failure_preserved"] is not True or scope["c5_execution_allowed"] is not False:
        raise RuntimeError("missing/C5 boundary drifted")
    if config["presentation"]["separate_principal_section_pages"] != 0:
        raise RuntimeError("principal section must remain inside each matrix page")
    if config["presentation"]["c5_state"] != "NOT_RUN":
        raise RuntimeError("C5 must remain NOT_RUN")
    if config.get("official_G3_G4_PASS_usable", "missing") is not None or config.get("scientific_verdict", "missing") is not None:
        raise RuntimeError("official PASS and verdict must remain null")


def verify_exact(path: Path, expected: str, label: str) -> dict[str, Any]:
    size, digest = sha256_file(path)
    if digest != expected:
        raise RuntimeError(f"{label} exact hash differs")
    return {"path": path.as_posix(), "bytes": size, "sha256": digest}


def condition_tables(root: Path, metric_key: str, metric_name: str) -> tuple[dict[tuple[str, str], dict[str, Any]], dict[str, dict[str, Any]]]:
    prepared = json.loads((root / "control/prepared_v1.json").read_text(encoding="utf-8"))
    finalized = json.loads((root / "control/finalized_v1.json").read_text(encoding="utf-8"))
    units = {row["operation_unit_id"]: row for row in rows(root / prepared["execution_units"]["path"])}
    metrics = rows(root / finalized[metric_key]["path"])
    return {(row["building_id"], row[metric_name]): row for row in metrics}, units


def postprocess_tables(root: Path, result_key: str, condition_id: str) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    finalized = json.loads((root / "control/finalized_v1.json").read_text(encoding="utf-8"))
    metrics = rows(root / finalized[result_key]["path"])
    selected = {row["building_id"]: row for row in metrics if row.get("condition_id") == condition_id}
    associated = json.loads((root / "control/population_associated_v1.json").read_text(encoding="utf-8"))
    units = {row["operation_unit_id"]: row for row in rows(root / associated["execution_units"]["path"])}
    return selected, units


def empty_geometry() -> dict[str, Any]:
    return {"points": PointSet.empty(), "surfaces": [], "roofprint": []}


def metric_value(metrics: Mapping[str, Any], name: str) -> str:
    value = metrics.get(name)
    return "NA" if value is None else f"{float(value):.3f}"


def label_text(condition: str, role: str, row: Mapping[str, Any], *, output: bool) -> str:
    metrics = row.get("current_uas_metrics") or row.get("continuous_metrics") or {}
    state = "ROOFER OUTPUT" if output else "NATIVE / INPUT EVIDENCE"
    return (
        f"{condition}\n{state}\n\n"
        f"role: {role}\n"
        f"association: {row.get('association_status')}\n"
        f"G0/G1: {row.get('G0_generated')}/{row.get('G1_schema_semantic')}\n"
        f"MAE-Z: {metric_value(metrics, 'height_error_mae_m')} m\n"
        f"RMSZ: {metric_value(metrics, 'RMSZ_m')} m\n\n"
        "G2/G3/G4/PASS_usable: null\nscientific_verdict: null"
    )


def draw_label(axis: Any, title: str, text: str, color: str) -> None:
    axis.set_facecolor(color)
    axis.axis("off")
    axis.text(0.04, 0.96, title, va="top", fontsize=11, fontweight="bold")
    axis.text(0.04, 0.80, text, va="top", fontsize=8.4, linespacing=1.35)


def native_points(native: Mapping[str, np.ndarray], bbox: Any) -> PointSet:
    index = _native_crop(native, bbox)
    return PointSet(native["means"][index], None)


def plot_input_row(
    figure: Any,
    grid: Any,
    row_index: int,
    geometry: Mapping[str, Any],
    native: Mapping[str, np.ndarray] | None,
    viewport: Any,
    reference: Any,
    current: PointSet,
    zlim: tuple[float, float],
    title: str,
) -> None:
    top = figure.add_subplot(grid[row_index, 1])
    if native is None:
        plot_top_points(top, geometry["points"], viewport, classes=True, title=f"{title} | TOP")
        draw_section_locator(top, reference)
    else:
        plot_native_top(top, native, viewport, reference, f"{title} | TOP")
    oblique = figure.add_subplot(grid[row_index, 2], projection="3d")
    if native is None:
        plot_oblique(oblique, geometry["points"], [], viewport, title=f"{title} | OBLIQUE")
        oblique.set_zlim(*zlim)
    else:
        plot_native_mesh(oblique, native, viewport, zlim, f"{title} | OBLIQUE")
    section = figure.add_subplot(grid[row_index, 3])
    section_geometry = geometry if native is None else {"points": native_points(native, viewport), "surfaces": []}
    plot_pca_section(section, section_geometry, current, reference, zlim, f"{title} | CANONICAL PCA SECTION")


def plot_output_row(
    figure: Any,
    grid: Any,
    row_index: int,
    geometry: Mapping[str, Any],
    viewport: Any,
    reference: Any,
    current: PointSet,
    zlim: tuple[float, float],
    title: str,
) -> None:
    top = figure.add_subplot(grid[row_index, 1])
    plot_top_output(top, geometry["surfaces"], current, viewport, title=f"{title} | TOP")
    draw_section_locator(top, reference)
    oblique = figure.add_subplot(grid[row_index, 2], projection="3d")
    plot_oblique(oblique, PointSet.empty(), geometry["surfaces"], viewport, title=f"{title} | OBLIQUE")
    oblique.set_zlim(*zlim)
    section = figure.add_subplot(grid[row_index, 3])
    plot_pca_section(section, geometry, current, reference, zlim, f"{title} | CANONICAL PCA SECTION")


def pdf_volumes(page_paths: list[Path], output_root: Path, volume_size: int) -> list[dict[str, Any]]:
    records = []
    for start in range(0, len(page_paths), volume_size):
        chunk = page_paths[start:start + volume_size]
        images = []
        for path in chunk:
            with Image.open(path) as source:
                images.append(source.convert("RGB"))
        volume = output_root / f"reports/P2_UTARGET199_C1_C4_MATRIX_v1_volume_{start // volume_size + 1:02d}.pdf"
        volume.parent.mkdir(parents=True, exist_ok=True)
        images[0].save(volume, "PDF", save_all=True, append_images=images[1:], resolution=110.0, quality=88)
        for image in images:
            image.close()
        records.append({"page_start": start + 1, "page_end": start + len(chunk), **record(volume, output_root)})
    return records


def run(
    output_root: Path,
    artifact_root: Path,
    source_commit: str,
    run_id: str,
    validation_building_id: str | None = None,
) -> dict[str, Any]:
    config = load_config()
    verify_config(config)
    if output_root.exists() and any(output_root.iterdir()):
        raise RuntimeError("fresh add-once C1-C4 matrix namespace required")
    output_root.mkdir(parents=True, exist_ok=True)
    sources = config["sources"]
    c12_root = artifact_root / sources["c1_c2_contract_relative_root"]
    c3_root = artifact_root / sources["c3_postprocess_relative_root"]
    c4_root = artifact_root / sources["c4_postprocess_relative_root"]
    checks = {
        "c1_c2_metrics": verify_exact(c12_root / "results/building_method_metrics_v1.jsonl", config["exact_hashes"]["c1_c2_metric_sha256"], "C1/C2 metrics"),
        "c3_metrics": verify_exact(c3_root / "results/building_condition_metrics_v1.jsonl", config["exact_hashes"]["c3_metric_sha256"], "C3 metrics"),
        "c4_metrics": verify_exact(c4_root / "results/building_c4_metrics_v1.jsonl", config["exact_hashes"]["c4_metric_sha256"], "C4 metrics"),
        "current_uas": verify_exact(c12_root / "freeze/utarget199_reference_cells_v1.jsonl", config["exact_hashes"]["current_uas_reference_sha256"], "current UAS reference"),
        "c3_checkpoint": verify_exact(artifact_root / sources["c3_checkpoint_relative_path"], config["exact_hashes"]["c3_checkpoint_sha256"], "C3 checkpoint"),
        "c4_checkpoint": verify_exact(artifact_root / sources["c4_checkpoint_relative_path"], config["exact_hashes"]["c4_checkpoint_sha256"], "C4 checkpoint"),
    }
    lod2_paths = [artifact_root / path for path in sources["lod2_relative_paths"]]
    checks["lod2"] = [verify_exact(path, digest, "LoD2 reference") for path, digest in zip(lod2_paths, config["exact_hashes"]["lod2_sha256"])]
    c12, c12_units = condition_tables(c12_root, "building_method_metrics", "method_id")
    c3, c3_units = postprocess_tables(c3_root, "building_condition_metrics", "C3_2_SEM_DEPTH")
    c4, c4_units = postprocess_tables(c4_root, "building_c4_metrics", "C4_EXISTING_ALS")
    building_ids = sorted(c4)
    if len(building_ids) != 199 or any((building_id, method) not in c12 for building_id in building_ids for method in ("C1_L_upper", "C2_MVS")) or set(c3) != set(building_ids):
        raise RuntimeError("exact 199-building C1/C2/C3/C4 membership differs")
    render_ids = building_ids
    if validation_building_id is not None:
        if validation_building_id not in building_ids:
            raise RuntimeError("validation building is outside exact U_target membership")
        render_ids = [validation_building_id]
    references = load_references(lod2_paths, building_ids)
    current_rows: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows(c12_root / "freeze/utarget199_reference_cells_v1.jsonl"):
        current_rows[str(row["stable_id"])].append(row)
    shift = np.asarray(config["frame"]["local_shift_xyz"], dtype=np.float64)
    natives = {
        "C3_2_SEM_DEPTH": _checkpoint_arrays(artifact_root / sources["c3_checkpoint_relative_path"], shift),
        "C4_EXISTING_ALS": _checkpoint_arrays(artifact_root / sources["c4_checkpoint_relative_path"], shift),
    }
    census_config = load_census_config()
    best, cameras, camera_model, scene_ref = camera_context(artifact_root, census_config)
    geometry_cache: dict[tuple[str, str], dict[str, Any]] = {}
    page_root = output_root / "qualitative/full_resolution_matrix_pages"
    page_root.mkdir(parents=True, exist_ok=False)
    page_records = []
    page_paths = []
    for index, building_id in enumerate(render_ids, 1):
        c1_row, c2_row, c3_row, c4_row = c12[(building_id, "C1_L_upper")], c12[(building_id, "C2_MVS")], c3[building_id], c4[building_id]
        reference = references[building_id]
        bbox = BBox(*(float(c4_row[name]) for name in ("bbox_min_x", "bbox_min_y", "bbox_max_x", "bbox_max_y")))
        viewport = bbox.padded(0.35, 5.0)
        zlim = _lod2_zlim(reference, float(config["frame"]["lod2_orthometric_to_current_ellipsoidal_m"]))
        current = PointSet(np.asarray([[float(row["cell_x"]), float(row["cell_y"]), float(row["top_z"])] for row in current_rows[building_id]], dtype=np.float64).reshape((-1, 3)), None)
        condition_specs = [
            ("C1", c1_row, c12_units, c12_root, None, "SELF_REFERENCE_DIAGNOSTIC"),
            ("C2", c2_row, c12_units, c12_root, None, "INDEPENDENT_CURRENT_UAS"),
            ("C3-2", c3_row, c3_units, c3_root, natives["C3_2_SEM_DEPTH"], "MATCHED_IMAGE_DERIVED_CONTROL"),
            ("C4", c4_row, c4_units, c4_root, natives["C4_EXISTING_ALS"], "EXISTING_ALS_PRIOR_TECHNICAL_DIAGNOSTIC"),
        ]
        geometries = []
        for condition, row, units, root, native, role in condition_specs:
            unit_id = row.get("operation_unit_id")
            key = (condition, str(unit_id))
            if unit_id and key not in geometry_cache:
                geometry_cache[key] = load_geometry(root, units[unit_id])
            geometries.append(geometry_cache.get(key, empty_geometry()))
        z_context = np.concatenate((current.xyz[:, 2], np.asarray([value + 45.7 for _semantic, ring in reference.surface_rings for value in np.asarray(ring)[:, 2]]))) if len(current.xyz) else np.asarray([value + 45.7 for _semantic, ring in reference.surface_rings for value in np.asarray(ring)[:, 2]])
        image, image_note = rgb_crop(artifact_root, census_config, best, cameras, camera_model, scene_ref, building_id, bbox, z_context)
        figure = plt.figure(figsize=(20, 28), dpi=110, constrained_layout=True)
        grid = figure.add_gridspec(10, 4, width_ratios=[0.60, 1, 1, 1])
        population_index = building_ids.index(building_id) + 1
        figure.suptitle(f"{building_id} — C1 / C2 / matched C3-2 / C4 Existing ALS — U_target {population_index}/199", fontsize=18, fontweight="bold")
        rgb_label = figure.add_subplot(grid[0, 0])
        draw_label(rgb_label, "01  CURRENT RGB CONTEXT", f"frozen best view: {image_note}\nqualitative display only\nLoD2 status: {c4_row['lod2_reference_status']}\nC5: NOT_RUN", "#f7f7f7")
        rgb_axis = figure.add_subplot(grid[0, 1:4])
        if image is None:
            rgb_axis.text(0.5, 0.5, image_note, ha="center", va="center", fontsize=16, color="crimson")
        else:
            rgb_axis.imshow(image)
        rgb_axis.set_title("CURRENT RGB — frozen best-view crop", fontsize=11)
        rgb_axis.axis("off")
        row_index = 1
        colors = ("#eef7ff", "#eef7ff", "#f7f2ff", "#fff4ea")
        for (condition, row, _units, _root, native, role), geometry, color in zip(condition_specs, geometries, colors):
            label = figure.add_subplot(grid[row_index, 0])
            draw_label(label, f"{row_index + 1:02d}  {condition} INPUT", label_text(condition, role, row, output=False), color)
            plot_input_row(figure, grid, row_index, geometry, native, viewport, reference, current, zlim, f"{condition} input")
            row_index += 1
            label = figure.add_subplot(grid[row_index, 0])
            draw_label(label, f"{row_index + 1:02d}  {condition} ROOFER", label_text(condition, role, row, output=True), color)
            plot_output_row(figure, grid, row_index, geometry, viewport, reference, current, zlim, f"{condition} Roofer output")
            row_index += 1
        label = figure.add_subplot(grid[9, 0])
        draw_label(label, "10  REFERENCE CONTEXT", "green=current UAS evaluation\npurple dashed=2022 LoD2 +45.7 m\nA/B=footprint-PCA section\nVIEW=section viewing direction\n\nC4 vs LoD2:\nPRIOR_RELATED_REFERENCE_DIAGNOSTIC_ONLY", "#f3f3f3")
        top = figure.add_subplot(grid[9, 1])
        plot_top_points(top, current, viewport, title="Independent current UAS evaluation | TOP")
        draw_section_locator(top, reference)
        oblique = figure.add_subplot(grid[9, 2], projection="3d")
        plot_oblique(oblique, current, [], viewport, title="Independent current UAS evaluation | OBLIQUE")
        oblique.set_zlim(*zlim)
        section = figure.add_subplot(grid[9, 3])
        plot_pca_section(section, empty_geometry(), current, reference, zlim, "Reference context | CANONICAL PCA SECTION")
        page = page_root / f"{building_id}_C1_C2_C3_2_C4_matrix_v1.png"
        figure.savefig(page, metadata={"Software": "JointBuildGS U_target199 C1-C4 attached-style matrix"})
        plt.close(figure)
        page_paths.append(page)
        page_records.append({
            "building_id": building_id,
            "index": population_index,
            "lod2_reference_status": c4_row["lod2_reference_status"],
            "c4_association_status": c4_row["association_status"],
            "c5_state": "NOT_RUN",
            **record(page, output_root),
            "official_PASS_usable": None,
            "scientific_verdict": None,
        })
        print(f"rendered attached-style matrix {index}/199 {building_id}", flush=True)
    if validation_building_id is not None:
        body = {
            "schema": "jointbuildgs.p2.utarget199_c1_c4_matrix_validation.v1",
            "status": "VALIDATION_ONLY_COMPLETE_NOT_PRODUCTION_CLOSURE",
            "building_id": validation_building_id,
            "page": page_records[0],
            "source_checks": checks,
            "c5_executed": False,
            "official_G3_G4_PASS_usable": None,
            "scientific_verdict": None,
        }
        write_json(output_root / "control/validation_complete_v1.json", body)
        return body
    write_new(output_root / "qualitative/full_resolution_matrix_manifest_v1.jsonl", b"".join((json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n").encode() for row in page_records))
    gallery = [
        "<!doctype html><html lang='ko'><head><meta charset='utf-8'><title>U_target 199 C1-C4 matrix</title>",
        "<style>body{font-family:sans-serif;max-width:2200px;margin:auto}article{border-top:4px solid #222;margin:3rem 0}img{width:100%;height:auto}code{font-size:1.1rem}</style></head><body>",
        "<h1>U_target 199동 — C1/C2/matched C3-2/C4 attached-style full-resolution matrix</h1>",
        "<p>199동 전체를 유지합니다. C5=NOT_RUN; official PASS_usable=null; scientific_verdict=null.</p>",
    ]
    for row in page_records:
        rel = Path(row["path"]).relative_to("qualitative").as_posix()
        gallery.append(f"<article><h2><code>{html.escape(row['building_id'])}</code> — {html.escape(row['lod2_reference_status'])} — C4 {html.escape(row['c4_association_status'])}</h2><a href='{html.escape(rel)}'><img loading='lazy' src='{html.escape(rel)}'></a></article>")
    gallery.append("</body></html>")
    write_new(output_root / "qualitative/index.html", "\n".join(gallery).encode())
    volumes = pdf_volumes(page_paths, output_root, int(config["scope"]["pdf_volume_size"]))
    material = [path for path in sorted(output_root.rglob("*")) if path.is_file() and path.name not in {"artifact_manifest_v1.json", "300-closed.local_v1.json"}]
    manifest = {
        "schema": "jointbuildgs.p2.utarget199_c1_c4_matrix_manifest.v1",
        "status": "COMPLETE_HASHED_MATERIAL_PAYLOAD",
        "source_commit": source_commit,
        "run_id": run_id,
        "source_checks": checks,
        "building_count": 199,
        "page_count": len(page_records),
        "pdf_volumes": volumes,
        "records": [record(path, output_root) for path in material],
        "c5_executed": False,
        "official_G3_G4_PASS_usable": None,
        "scientific_verdict": None,
    }
    manifest["record_count"] = len(manifest["records"])
    write_json(output_root / "control/artifact_manifest_v1.json", manifest)
    closed = {
        "schema": "jointbuildgs.p2.utarget199_c1_c4_matrix_closed.local.v1",
        "status": "TECHNICAL_PRESENTATION_CLOSED",
        "task_id": config["task_id"],
        "source_commit": source_commit,
        "run_id": run_id,
        "building_count": 199,
        "full_resolution_page_count": len(page_records),
        "pdf_volume_count": len(volumes),
        "gallery": record(output_root / "qualitative/index.html", output_root),
        "manifest": record(output_root / "control/artifact_manifest_v1.json", output_root),
        "c5_executed": False,
        "official_G3_G4_PASS_usable": None,
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
    parser.add_argument("--validation-building-id")
    args = parser.parse_args()
    try:
        result = run(
            args.output_root,
            args.artifact_root,
            args.source_commit,
            args.run_id,
            validation_building_id=args.validation_building_id,
        )
    except Exception as error:
        args.output_root.mkdir(parents=True, exist_ok=True)
        failure = args.output_root / "control/100-failed.local_v1.json"
        if not failure.exists():
            write_json(failure, {
                "schema": "jointbuildgs.p2.utarget199_c1_c4_matrix_failed.local.v1",
                "status": "FAILED_VISIBLE_PARTIAL_OUTPUTS_PRESERVED",
                "error_type": type(error).__name__,
                "error": str(error),
                "source_commit": args.source_commit,
                "run_id": args.run_id,
                "c5_executed": False,
                "official_G3_G4_PASS_usable": None,
                "scientific_verdict": None,
            })
        raise
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
