#!/usr/bin/env python3
"""Assemble all 199 full-resolution case pages with exact metric bindings."""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import math
import shutil
import xml.etree.ElementTree as ET
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import cv2
import numpy as np

from scripts.p2.c1_c2_oracle_c3_extract_v1.contract import (
    BuildingReference,
    _element_id,
    _local_name,
    canonical_json_bytes,
    file_record,
    load_building_references,
    sha256_file,
    write_new,
)


REPO_ROOT = Path(__file__).resolve().parents[3]
CONFIG_PATH = REPO_ROOT / "configs/p2/utarget199_presentation_v5/render_v5.json"


def load_config(path: Path = CONFIG_PATH) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def validate_config(config: Mapping[str, Any]) -> None:
    if config.get("schema") != "jointbuildgs.p2.utarget199_presentation.v5":
        raise RuntimeError("unexpected presentation schema")
    if config.get("status") != "APPROVED_FOR_LOCAL_NONCONFIRMATORY_PRESENTATION":
        raise RuntimeError("presentation task is not active")
    if config.get("official_G3_G4_PASS_usable", "missing") is not None:
        raise RuntimeError("official PASS_usable must remain null")
    if config.get("scientific_verdict", "missing") is not None:
        raise RuntimeError("scientific_verdict must remain null")
    if config["presentation"]["full_resolution_source_copy"] is not True:
        raise RuntimeError("source sheets must remain full resolution")
    if config["presentation"]["c5_missing_state"] != "NOT_RUN":
        raise RuntimeError("C5 must remain NOT_RUN")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical_hash(value: Any) -> str:
    return sha256_bytes(canonical_json_bytes(value))


def resolve(artifact_root: Path, relative: str) -> Path:
    path = artifact_root / relative
    if not path.exists():
        raise RuntimeError(f"missing source: {path}")
    return path


def verify_hash(path: Path, expected: str) -> dict[str, Any]:
    size, digest = sha256_file(path)
    if digest != expected:
        raise RuntimeError(f"exact source hash drifted: {path}: {digest} != {expected}")
    return {"path": str(path), "bytes": size, "sha256": digest}


def _ids_in_gml(path: Path, wanted: set[str]) -> list[str]:
    found: set[str] = set()
    for _event, element in ET.iterparse(path, events=("end",)):
        if _local_name(element.tag) == "Building":
            stable_id = _element_id(element)
            if stable_id in wanted:
                found.add(str(stable_id))
        element.clear()
    return sorted(found)


def load_references(paths: Sequence[Path], building_ids: Sequence[str]) -> dict[str, BuildingReference]:
    wanted = set(building_ids)
    references: dict[str, BuildingReference] = {}
    for path in paths:
        selected = _ids_in_gml(path, wanted - set(references))
        if selected:
            references.update(load_building_references(path, selected))
    missing = sorted(wanted - set(references))
    if missing:
        raise RuntimeError(f"LoD2 references missing: {missing}")
    return references


def _point_triangle_z(x: float, y: float, triangle: np.ndarray) -> float | None:
    xy = triangle[:, :2]
    matrix = np.asarray(
        [[xy[0, 0], xy[1, 0], xy[2, 0]], [xy[0, 1], xy[1, 1], xy[2, 1]], [1.0, 1.0, 1.0]],
        dtype=np.float64,
    )
    determinant = float(np.linalg.det(matrix))
    if abs(determinant) < 1.0e-10:
        return None
    weights = np.linalg.solve(matrix, np.asarray([x, y, 1.0], dtype=np.float64))
    if float(weights.min()) < -1.0e-7 or float(weights.max()) > 1.0 + 1.0e-7:
        return None
    return float(weights @ triangle[:, 2])


def lod2_roof_z(reference: BuildingReference, x: float, y: float) -> float | None:
    candidates: list[float] = []
    for ring in reference.roof_rings_xyz:
        vertices = np.asarray(ring[:-1] if np.allclose(ring[0], ring[-1]) else ring, dtype=np.float64)
        for index in range(1, len(vertices) - 1):
            z = _point_triangle_z(x, y, np.vstack((vertices[0], vertices[index], vertices[index + 1])))
            if z is not None and math.isfinite(z):
                candidates.append(z)
    return max(candidates) if candidates else None


def load_jsonl(path: Path) -> tuple[list[dict[str, Any]], list[bytes]]:
    raw_lines = path.read_bytes().splitlines(keepends=True)
    return [json.loads(line) for line in raw_lines], raw_lines


def _support_hash(rows: Iterable[Mapping[str, Any]]) -> str:
    normalized = [dict(sorted((str(key), str(value)) for key, value in row.items())) for row in rows]
    return canonical_hash(normalized)


def temporal_diagnostic(
    building_id: str,
    reference: BuildingReference,
    cells: Sequence[Mapping[str, Any]],
    current_rgb: str,
    config: Mapping[str, Any],
) -> dict[str, Any]:
    rule = config["lod2_diagnostic"]
    dz = float(rule["orthometric_to_current_ellipsoidal_m"])
    residuals = []
    for row in cells:
        z = lod2_roof_z(reference, float(row["cell_x"]), float(row["cell_y"]))
        if z is not None:
            residuals.append(abs(float(row["top_z"]) - (z + dz)))
    residuals_array = np.asarray(residuals, dtype=np.float64)
    median = float(np.median(residuals_array)) if len(residuals_array) else None
    p95 = float(np.quantile(residuals_array, 0.95)) if len(residuals_array) else None
    known_uncertain = building_id in set(rule["known_alignment_uncertain_ids"])
    rgb_unavailable = current_rgb in {"BBOX_NOT_PROJECTABLE", "EMPTY_RGB_CROP"}
    enough = len(residuals_array) >= int(rule["minimum_uas_cells"])
    if known_uncertain or rgb_unavailable or not enough:
        status = "REFERENCE_ID_ALIGNMENT_UNCERTAIN"
    elif median <= float(rule["unchanged_median_abs_z_max_m"]) and p95 <= float(rule["unchanged_p95_abs_z_max_m"]):
        status = "UNCHANGED_CONFIDENT"
    else:
        status = "TEMPORAL_CHANGE_SUSPECTED"
    return {
        "building_id": building_id,
        "status": status,
        "current_rgb": current_rgb,
        "uas_cell_count": len(cells),
        "lod2_interpolated_cell_count": len(residuals_array),
        "median_abs_z_m": median,
        "p95_abs_z_m": p95,
        "rule": dict(rule),
        "scientific_verdict": None,
    }


def terminal_output_map(contract_root: Path) -> dict[str, dict[str, Any]]:
    outputs: dict[str, dict[str, Any]] = {}
    for path in sorted((contract_root / "terminal").glob("*.json")):
        row = json.loads(path.read_text(encoding="utf-8"))
        operation_id = row.get("operation_unit_id")
        if operation_id:
            records = row.get("output_records") or []
            outputs[str(operation_id)] = {
                "terminal": file_record(path, contract_root),
                "output": records[0] if len(records) == 1 else None,
                "status": row.get("status"),
            }
    return outputs


def _read_image(path: Path) -> np.ndarray:
    image = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if image is None:
        raise RuntimeError(f"unreadable source sheet: {path}")
    return image


def compose_full_resolution_page(
    output: Path,
    building_id: str,
    contract_sheet: Path,
    c3_sheet: Path,
    diagnostic: Mapping[str, Any],
    metric_rows: Sequence[Mapping[str, Any]],
    c4_state: str,
    c5_state: str,
) -> None:
    first, second = _read_image(contract_sheet), _read_image(c3_sheet)
    width = max(first.shape[1], second.shape[1], 2200)
    header_height, state_height, gap = 220, 230, 32
    height = header_height + first.shape[0] + gap + second.shape[0] + gap + state_height
    canvas = np.full((height, width, 3), 255, dtype=np.uint8)
    cv2.putText(canvas, building_id, (40, 66), cv2.FONT_HERSHEY_SIMPLEX, 1.35, (20, 20, 20), 3, cv2.LINE_AA)
    cv2.putText(canvas, f"LoD2: {diagnostic['status']}", (40, 122), cv2.FONT_HERSHEY_SIMPLEX, 0.90, (60, 60, 60), 2, cv2.LINE_AA)
    summary = " | ".join(f"{row['method_id']}:{row['association_status']}" for row in metric_rows)
    cv2.putText(canvas, summary[:180], (40, 177), cv2.FONT_HERSHEY_SIMPLEX, 0.66, (55, 55, 55), 1, cv2.LINE_AA)
    y = header_height
    for image in (first, second):
        x = (width - image.shape[1]) // 2
        canvas[y:y + image.shape[0], x:x + image.shape[1]] = image
        y += image.shape[0] + gap
    cv2.rectangle(canvas, (0, y), (width - 1, y + state_height - 1), (244, 246, 248), -1)
    cv2.putText(canvas, f"C4 Image + Existing ALS GS: {c4_state}", (50, y + 82), cv2.FONT_HERSHEY_SIMPLEX, 1.05, (35, 35, 35), 2, cv2.LINE_AA)
    cv2.putText(canvas, "LoD2 comparison role: PRIOR_RELATED_REFERENCE_DIAGNOSTIC_ONLY", (50, y + 132), cv2.FONT_HERSHEY_SIMPLEX, 0.72, (70, 70, 70), 2, cv2.LINE_AA)
    cv2.putText(canvas, f"C5 Image + independent LoD1 GS: {c5_state}", (50, y + 190), cv2.FONT_HERSHEY_SIMPLEX, 1.05, (35, 35, 35), 2, cv2.LINE_AA)
    ok, encoded = cv2.imencode(".png", canvas, [cv2.IMWRITE_PNG_COMPRESSION, 4])
    if not ok:
        raise RuntimeError("case page encoding failed")
    write_new(output, encoded.tobytes())


def run(output_root: Path, artifact_root: Path, source_commit: str) -> dict[str, Any]:
    config = load_config()
    validate_config(config)
    if output_root.exists() and any(output_root.iterdir()):
        raise RuntimeError(f"add-once output is not empty: {output_root}")
    output_root.mkdir(parents=True, exist_ok=True)
    contract_root = resolve(artifact_root, config["sources"]["contract_relative_root"])
    c3_root = resolve(artifact_root, config["sources"]["c3_relative_root"])
    lod2_paths = [resolve(artifact_root, value) for value in config["sources"]["lod2_relative_paths"]]
    metric_path = contract_root / "results/building_method_metrics_v1.jsonl"
    gates_path = contract_root / "results/building_acceptance_gates_v1.csv"
    c3_metric_path = c3_root / "results/building_condition_metrics_v1.jsonl"
    reference_path = contract_root / "freeze/utarget199_reference_cells_v1.jsonl"
    source_checks = {
        "metric": verify_hash(metric_path, config["exact_hashes"][metric_path.name]),
        "gates": verify_hash(gates_path, config["exact_hashes"][gates_path.name]),
        "c3_metric": verify_hash(c3_metric_path, config["exact_hashes"][c3_metric_path.name]),
        "current_uas_reference": verify_hash(reference_path, config["exact_hashes"][reference_path.name]),
        "lod2": [file_record(path, artifact_root) for path in lod2_paths],
    }
    metrics, metric_lines = load_jsonl(metric_path)
    if len(metrics) != 597:
        raise RuntimeError(f"expected exact 597 metric rows, found {len(metrics)}")
    building_ids = sorted({str(row["building_id"]) for row in metrics})
    if len(building_ids) != 199:
        raise RuntimeError(f"expected 199 buildings, found {len(building_ids)}")
    by_building: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in metrics:
        by_building[str(row["building_id"])].append(row)
    if any(len(by_building[value]) != 3 for value in building_ids):
        raise RuntimeError("every building must retain exactly three C1/C2/C3 rows")
    contract_manifest, _ = load_jsonl(contract_root / "qualitative/case_sheet_manifest_v1.jsonl")
    c3_manifest, _ = load_jsonl(c3_root / "qualitative/case_sheet_manifest_v1.jsonl")
    contract_sheet = {row["building_id"]: row for row in contract_manifest}
    c3_sheet = {row["building_id"]: row for row in c3_manifest}
    if set(contract_sheet) != set(building_ids) or set(c3_sheet) != set(building_ids):
        raise RuntimeError("199-building source sheet membership drifted")
    reference_rows, _ = load_jsonl(reference_path)
    cells: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in reference_rows:
        cells[str(row["stable_id"])].append(row)
    references = load_references(lod2_paths, building_ids)
    output_by_operation = terminal_output_map(contract_root)
    reused_metric = output_root / "results/building_method_metrics_v1.exact_reuse.jsonl"
    reused_gates = output_root / "results/building_acceptance_gates_v1.exact_reuse.csv"
    reused_metric.parent.mkdir(parents=True, exist_ok=True)
    write_new(reused_metric, metric_path.read_bytes())
    write_new(reused_gates, gates_path.read_bytes())
    if sha256_file(reused_metric)[1] != config["exact_hashes"][metric_path.name]:
        raise RuntimeError("597-row metric copy is not byte-identical")
    temporal_rows = []
    binding_rows = []
    page_records = []
    for building_id in building_ids:
        source_row = contract_sheet[building_id]
        diagnostic = temporal_diagnostic(
            building_id,
            references[building_id],
            cells.get(building_id, []),
            str(source_row["current_rgb"]),
            config,
        )
        diagnostic["current_uas_support_sha256"] = _support_hash(cells.get(building_id, []))
        temporal_rows.append(diagnostic)
        page_path = output_root / f"qualitative/case_pages/{building_id}_full_resolution_v5.png"
        compose_full_resolution_page(
            page_path,
            building_id,
            contract_root / source_row["path"],
            c3_root / c3_sheet[building_id]["path"],
            diagnostic,
            by_building[building_id],
            config["presentation"]["c4_missing_state"],
            config["presentation"]["c5_missing_state"],
        )
        page_record = file_record(page_path, output_root)
        page_records.append({"building_id": building_id, **page_record})
        for row, raw_line in zip(metrics, metric_lines):
            if row["building_id"] != building_id:
                continue
            operation = output_by_operation.get(str(row.get("operation_unit_id")))
            support_binding = {
                "building_id": building_id,
                "method_id": row["method_id"],
                "bbox": [row["bbox_min_x"], row["bbox_min_y"], row["bbox_max_x"], row["bbox_max_y"]],
                "current_image_view_support": row["current_image_view_support"],
                "mvs_support_cells": row["mvs_support_cells"],
                "c4_support_cells": row["c4_support_cells"],
                "reference_cell_count": row["reference_cell_count"],
            }
            binding_rows.append({
                "building_id": building_id,
                "method_id": row["method_id"],
                "metric_row_sha256": sha256_bytes(raw_line.rstrip(b"\r\n")),
                "metric_source_sha256": config["exact_hashes"][metric_path.name],
                "output_sha256": (operation or {}).get("output", {}).get("sha256") if (operation or {}).get("output") else None,
                "output_null_reason": None if (operation or {}).get("output") else "NO_SINGLE_SEALED_ROOFER_OUTPUT_FOR_ROW",
                "current_uas_reference_sha256": source_checks["current_uas_reference"]["sha256"],
                "current_uas_building_support_sha256": diagnostic["current_uas_support_sha256"],
                "lod2_reference_sha256": canonical_hash(source_checks["lod2"]),
                "support_binding_sha256": canonical_hash(support_binding),
                "evaluator_config_sha256": canonical_hash(config["lod2_diagnostic"]),
                "current_uas_c1_reference_role": "SELF_REFERENCE_DIAGNOSTIC" if row["method_id"] == "C1_L_upper" else row["reference_role"],
                "lod2_2022_reference_status": diagnostic["status"],
                "c4_vs_lod2_role": "PRIOR_RELATED_REFERENCE_DIAGNOSTIC_ONLY",
                "official_PASS_usable": None,
                "scientific_verdict": None,
            })
    temporal_path = output_root / "results/lod2_temporal_reference_diagnostics_v1.jsonl"
    binding_path = output_root / "results/metric_binding_v5.jsonl"
    write_new(temporal_path, b"".join(canonical_json_bytes(row) for row in temporal_rows))
    write_new(binding_path, b"".join(canonical_json_bytes(row) for row in binding_rows))
    index_items = []
    page_map = {row["building_id"]: row for row in page_records}
    diagnostic_map = {row["building_id"]: row for row in temporal_rows}
    for building_id in building_ids:
        record = page_map[building_id]
        index_items.append(
            f'<article data-status="{html.escape(diagnostic_map[building_id]["status"])}"><h2>{html.escape(building_id)}</h2>'
            f'<p>{html.escape(diagnostic_map[building_id]["status"])}</p><a href="../{html.escape(record["path"])}">'
            f'<img loading="lazy" src="../{html.escape(record["path"])}"></a></article>'
        )
    html_body = """<!doctype html><meta charset=utf-8><title>U_target 199 v5</title>
<style>body{font-family:sans-serif;max-width:1900px;margin:auto}article{margin:3rem 0;border-top:3px solid #222}img{width:100%;height:auto}h2{font-size:2rem}p{font-size:1.25rem}</style>
<h1>U_target=199 full-resolution qualitative gallery v5</h1><p>C1/C2/C3 sealed reuse; C4/C5 missing states preserved; scientific_verdict=null.</p>""" + "".join(index_items)
    write_new(output_root / "qualitative/index.html", html_body.encode("utf-8"))
    summary = {
        "schema": "jointbuildgs.p2.utarget199_presentation_result.v5",
        "status": "COMPLETE_199_FULL_RESOLUTION_PAGES_AND_GALLERY",
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "source_commit": source_commit,
        "building_count": len(building_ids),
        "full_resolution_page_count": len(page_records),
        "metric_rows_exact_reused": len(metrics),
        "metric_bindings": len(binding_rows),
        "c4_state": config["presentation"]["c4_missing_state"],
        "c5_state": config["presentation"]["c5_missing_state"],
        "source_checks": source_checks,
        "reused_metrics": file_record(reused_metric, output_root),
        "reused_gates": file_record(reused_gates, output_root),
        "temporal_diagnostics": file_record(temporal_path, output_root),
        "metric_binding": file_record(binding_path, output_root),
        "pages": page_records,
        "official_G3_G4_PASS_usable": None,
        "scientific_verdict": None,
    }
    write_new(output_root / "control/technical_return_v5.json", canonical_json_bytes(summary))
    excluded = {"control/artifact_manifest_v5.json", "control/300-closed.local_v5.json"}
    records = [file_record(path, output_root) for path in sorted(output_root.rglob("*")) if path.is_file() and path.relative_to(output_root).as_posix() not in excluded]
    manifest = {"schema": "jointbuildgs.p2.utarget199_presentation_manifest.v5", "record_count": len(records), "records": records, "scientific_verdict": None}
    write_new(output_root / "control/artifact_manifest_v5.json", canonical_json_bytes(manifest))
    checks = {
        "building_count_199": len(building_ids) == 199,
        "pages_199": len(page_records) == 199,
        "source_metrics_597_exact": len(metrics) == 597 and sha256_file(reused_metric)[1] == config["exact_hashes"][metric_path.name],
        "bindings_597": len(binding_rows) == 597,
        "c5_not_run": config["presentation"]["c5_missing_state"] == "NOT_RUN",
        "official_and_scientific_null": summary["official_G3_G4_PASS_usable"] is None and summary["scientific_verdict"] is None,
    }
    if not all(checks.values()):
        raise RuntimeError(f"presentation verification failed: {checks}")
    write_new(output_root / "control/200-verified.local_v5.json", canonical_json_bytes({"checks": checks, "scientific_verdict": None}))
    closed = {
        "schema": "jointbuildgs.local_technical_300_closed.v5",
        "status": "300-CLOSED_LOCAL_199_FULL_RESOLUTION_PRESENTATION",
        "return": file_record(output_root / "control/technical_return_v5.json", output_root),
        "verified": file_record(output_root / "control/200-verified.local_v5.json", output_root),
        "manifest": file_record(output_root / "control/artifact_manifest_v5.json", output_root),
        "scientific_verdict": None,
    }
    write_new(output_root / "control/300-closed.local_v5.json", canonical_json_bytes(closed))
    return closed


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--source-commit", required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.output_root, args.artifact_root, args.source_commit), ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
