#!/usr/bin/env python3
"""Prepare, bind, and render the selected-10 C1/C2 footprint-oracle diagnostic."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import html
import json
from pathlib import Path
import shutil
from typing import Any, Mapping, Sequence

import numpy as np
from PIL import Image

from scripts.p2.c1_c2_c3_consolidated_results_v1.compose import canonical_json_bytes
from scripts.p2.c1_c2_c3_consolidated_results_v1.compose_v4 import lod2_zlim, shifted_lod2
from scripts.p2.c1_c2_c3_consolidated_results_v1.compose_v5 import (
    VIEWS,
    point_panel,
    surface_faces,
    triangle_panel,
)
from scripts.p2.c1_c2_oracle_c3_extract_v1.contract import (
    classify_oracle_crop,
    file_record,
    footprint_geojson,
    load_building_references,
    sha256_file,
    write_las,
    write_new,
)
from scripts.p2.c1_c2_oracle_c3_extract_v1.prepare_c1_c2 import collect_laz, collect_mvs
from scripts.p2.c1_c2_oracle_c3_extract_v1.render_results import _compose_sheet
from scripts.p2.selected10_c1_c4_presentation_v1.render import (
    placeholder,
    roofline_panels,
)
from scripts.p2.utarget199_contract_results_v1.contract import load_config as load_census_config
from scripts.p2.utarget199_contract_results_v1.render_case_sheets import camera_context
from src.visualization.fixed_view_qualitative import PointSet, Surface, load_cityjsonseq, load_las_points


REPO = Path(__file__).resolve().parents[3]
CONFIG_PATH = REPO / "configs/p2/selected10_c1_c4_presentation_v1/c1_c2_oracle_v1.json"
METHODS = ("C1_LIDAR_GT_FOOTPRINT_ORACLE", "C2_MVS_GT_FOOTPRINT_ORACLE")


def jsonl_bytes(rows: Sequence[Mapping[str, Any]]) -> bytes:
    return b"".join(
        (json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
        for row in rows
    )


def load_config() -> dict[str, Any]:
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def validate_config(config: Mapping[str, Any]) -> None:
    if config.get("schema") != "jointbuildgs.p2.selected10_c1_c2_oracle_presentation.v1":
        raise RuntimeError("selected10 oracle schema drifted")
    if config.get("status") != "APPROVED_BY_DIRECT_USER_INSTRUCTION":
        raise RuntimeError("selected10 oracle execution is not authorized")
    ids = list(config.get("building_ids") or ())
    if len(ids) != 10 or len(set(ids)) != 10:
        raise RuntimeError("selected10 membership drifted")
    bound = [item for values in config["lod2_membership"].values() for item in values]
    if sorted(bound) != sorted(ids) or len(bound) != len(set(bound)):
        raise RuntimeError("LoD2 file membership is not an exact partition")
    presentation = config["presentation"]
    if tuple(presentation["views"]) != VIEWS or len(presentation["rows"]) != 6:
        raise RuntimeError("six-row/four-view presentation drifted")
    if presentation["official_honest_stage3"] is not False:
        raise RuntimeError("oracle must never be relabeled as honest Stage 3")
    if presentation["separate_principal_page_count"] != 0:
        raise RuntimeError("separate principal page is prohibited")
    if config.get("official_PASS_usable", "missing") is not None or config.get("scientific_verdict", "missing") is not None:
        raise RuntimeError("official PASS and scientific verdict must remain null")


def exact(path: Path, expected_bytes: int | None, expected_sha256: str) -> dict[str, Any]:
    size, digest = sha256_file(path)
    if (expected_bytes is not None and size != expected_bytes) or digest != expected_sha256:
        raise RuntimeError(f"exact source drift: {path} bytes={size} sha256={digest}")
    return {"path": path.as_posix(), "bytes": size, "sha256": digest}


def references(config: Mapping[str, Any], artifact_root: Path) -> dict[str, Any]:
    result: dict[str, Any] = {}
    directory = artifact_root / config["inputs"]["lod2_relative_directory"]
    for name, ids in config["lod2_membership"].items():
        result.update(load_building_references(directory / name, ids))
    if set(result) != set(config["building_ids"]):
        raise RuntimeError("reference membership differs after parsing")
    return result


def prepare(output_root: Path, artifact_root: Path) -> dict[str, Any]:
    config = load_config()
    validate_config(config)
    if output_root.exists() and any(output_root.iterdir()):
        raise RuntimeError("fresh add-once oracle namespace required")
    output_root.mkdir(parents=True, exist_ok=True)
    inputs = config["inputs"]
    c1_path = artifact_root / inputs["c1_relative_path"]
    c2_path = artifact_root / inputs["c2_relative_path"]
    sources = {
        "c1": exact(c1_path, int(inputs["c1_bytes"]), str(inputs["c1_sha256"])),
        "c2": exact(c2_path, int(inputs["c2_bytes"]), str(inputs["c2_sha256"])),
        "lod2": {},
    }
    for name, digest in inputs["lod2_sha256"].items():
        sources["lod2"][name] = exact(artifact_root / inputs["lod2_relative_directory"] / name, None, digest)
    refs = references(config, artifact_root)
    prep = config["preparation"]
    c1_crops = collect_laz(c1_path, refs, float(prep["crop_buffer_m"]))
    c2_crops = collect_mvs(c2_path, refs, float(prep["crop_buffer_m"]), config["frame"]["world_shift_xyz"])
    all_rows: list[dict[str, Any]] = []
    for method, crops in zip(METHODS, (c1_crops, c2_crops)):
        for stable_id in config["building_ids"]:
            building, ground, stats = classify_oracle_crop(
                crops[stable_id], refs[stable_id],
                crop_buffer_m=float(prep["crop_buffer_m"]),
                ground_ring_inner_buffer_m=float(prep["ground_ring_inner_buffer_m"]),
                minimum_building_height_m=float(prep["minimum_building_height_above_local_ground_m"]),
                ground_cell_m=float(prep["ground_height_cell_m"]),
                ground_keep_above_m=float(prep["ground_keep_above_local_ground_m"]),
                voxel_m=float(prep["deterministic_voxel_m"]),
            )
            operation_id = f"{method}|{stable_id}"
            work = output_root / "operations" / method / stable_id / "work"
            input_path = work / "input.las"
            footprint_path = work / "gt_footprint_oracle.geojson"
            write_las(input_path, building, ground)
            write_new(footprint_path, canonical_json_bytes(footprint_geojson(refs[stable_id])))
            eligible = len(building) >= int(prep["minimum_roofer_class6_points"])
            row = {
                "operation_unit_id": operation_id,
                "condition_id": method,
                "stable_id": stable_id,
                "work_directory": work.relative_to(output_root).as_posix(),
                "input": file_record(input_path, output_root),
                "footprint": file_record(footprint_path, output_root),
                "classification": stats,
                "roofer_eligible": bool(eligible),
                "pre_roofer_failure": None if eligible else {
                    "code": "PRE_ROOFER_INSUFFICIENT_CLASS6_EVIDENCE",
                    "observed_class6_points": int(len(building)),
                    "minimum_class6_points": int(prep["minimum_roofer_class6_points"]),
                },
                "oracle_diagnostic": True,
                "official_honest_stage3": False,
                "roofsurface_used_as_roofer_input": False,
                "scientific_verdict": None,
            }
            write_new(work / "prepared_v1.json", canonical_json_bytes(row))
            all_rows.append(row)
    if len(all_rows) != 20 or len({row["operation_unit_id"] for row in all_rows}) != 20:
        raise RuntimeError("expected twenty exact C1/C2 operation units")
    write_new(output_root / "freeze/execution_units_v1.jsonl", jsonl_bytes(all_rows))
    eligible_rows = [row for row in all_rows if row["roofer_eligible"]]
    tsv = "operation_unit_id\twork_directory\n" + "".join(
        f"{row['operation_unit_id']}\t{row['work_directory']}\n" for row in eligible_rows
    )
    write_new(output_root / "freeze/execution_units_v1.tsv", tsv.encode("utf-8"))
    body = {
        "schema": "jointbuildgs.p2.selected10_c1_c2_oracle.prepared.v1",
        "status": "PREPARED_SELECTED10_ORACLE_UNITS",
        "source_records": sources,
        "operation_unit_count": 20,
        "roofer_eligible_count": len(eligible_rows),
        "pre_roofer_failure_count": 20 - len(eligible_rows),
        "eligible_operation_ids": [row["operation_unit_id"] for row in eligible_rows],
        "oracle_diagnostic": True,
        "official_honest_stage3": False,
        "scientific_verdict": None,
    }
    write_new(output_root / "control/prepared_v1.json", canonical_json_bytes(body))
    return body


def load_units(output_root: Path) -> dict[str, dict[str, Any]]:
    rows = [json.loads(line) for line in (output_root / "freeze/execution_units_v1.jsonl").read_text(encoding="utf-8").splitlines() if line]
    return {row["operation_unit_id"]: row for row in rows}


def repair_freeze(output_root: Path) -> dict[str, Any]:
    """Recover the preserved first-run multiline-JSON freeze without rerunning Roofer."""
    prepared_paths = sorted(output_root.glob("operations/*/*/work/prepared_v1.json"))
    rows = [json.loads(path.read_text(encoding="utf-8")) for path in prepared_paths]
    if len(rows) != 20 or len({row["operation_unit_id"] for row in rows}) != 20:
        raise RuntimeError("cannot recover anything other than the exact twenty prepared units")
    rows.sort(key=lambda row: (METHODS.index(row["condition_id"]), load_config()["building_ids"].index(row["stable_id"])))
    freeze = output_root / "freeze/execution_units_v1.jsonl"
    try:
        existing = [json.loads(line) for line in freeze.read_text(encoding="utf-8").splitlines() if line]
    except json.JSONDecodeError:
        existing = []
    if len(existing) == 20:
        return {"status": "ALREADY_COMPACT_JSONL", "operation_unit_count": 20}
    preserved = output_root / "freeze/execution_units_multiline_invalid_preserved_v1.json"
    if preserved.exists():
        raise RuntimeError("recovery source already preserved but compact freeze is still invalid")
    freeze.rename(preserved)
    write_new(freeze, jsonl_bytes(rows))
    eligible = [row for row in rows if row["roofer_eligible"]]
    tsv_path = output_root / "freeze/execution_units_v1.tsv"
    preserved_tsv = output_root / "freeze/execution_units_from_failed_run_preserved_v1.tsv"
    tsv_path.rename(preserved_tsv)
    tsv = "operation_unit_id\twork_directory\n" + "".join(
        f"{row['operation_unit_id']}\t{row['work_directory']}\n" for row in eligible
    )
    write_new(tsv_path, tsv.encode("utf-8"))
    body = {
        "schema": "jointbuildgs.p2.selected10_c1_c2_oracle.freeze_recovery.v1",
        "status": "RECOVERED_COMPACT_JSONL_WITHOUT_ROOFER_REEXECUTION",
        "preserved_invalid_freeze": file_record(preserved, output_root),
        "preserved_failed_run_tsv": file_record(preserved_tsv, output_root),
        "operation_unit_count": 20,
        "roofer_eligible_count": len(eligible),
        "scientific_verdict": None,
    }
    write_new(output_root / "control/freeze_recovery_v1.json", canonical_json_bytes(body))
    return body


def record_terminal(output_root: Path, operation_id: str, exit_code: int, runtime_seconds: int) -> dict[str, Any]:
    row = load_units(output_root).get(operation_id)
    if row is None or not row["roofer_eligible"]:
        raise RuntimeError(f"unknown or ineligible operation: {operation_id}")
    work = output_root / row["work_directory"]
    terminal_path = work / "roofer_terminal_v1.json"
    if terminal_path.exists():
        raise RuntimeError(f"terminal already exists: {terminal_path}")
    outputs = sorted((work / "out").glob("*.city.jsonl")) if (work / "out").is_dir() else []
    completed = exit_code == 0 and len(outputs) == 1
    body = {
        "schema": "jointbuildgs.p2.selected10_c1_c2_oracle.roofer_terminal.v1",
        "status": "COMPLETED" if completed else "FAILED",
        "operation_unit_id": operation_id,
        "condition_id": row["condition_id"],
        "stable_id": row["stable_id"],
        "exit_code": int(exit_code),
        "runtime_seconds": int(runtime_seconds),
        "input": row["input"],
        "footprint": row["footprint"],
        "outputs": [file_record(path, output_root) for path in outputs],
        "oracle_diagnostic": True,
        "official_honest_stage3": False,
        "scientific_verdict": None,
    }
    write_new(terminal_path, canonical_json_bytes(body))
    return body


def verify_record(root: Path, item: Mapping[str, Any]) -> None:
    path = root / item["path"]
    size, digest = sha256_file(path)
    if size != int(item["bytes"]) or digest != item["sha256"]:
        raise RuntimeError(f"bound record digest drift: {path}")


def method_geometry(output_root: Path, method: str, stable_id: str) -> tuple[PointSet, list[Surface], dict[str, Any]]:
    operation_id = f"{method}|{stable_id}"
    row = load_units(output_root)[operation_id]
    if row["condition_id"] != method or row["stable_id"] != stable_id:
        raise RuntimeError(f"operation binding mismatch: {operation_id}")
    verify_record(output_root, row["input"])
    verify_record(output_root, row["footprint"])
    points = load_las_points(output_root / row["input"]["path"])
    if not row["roofer_eligible"]:
        return points, [], {
            "status": row["pre_roofer_failure"]["code"],
            "operation_unit_id": operation_id,
            "condition_id": method,
            "stable_id": stable_id,
            "input": row["input"],
            "footprint": row["footprint"],
            "outputs": [],
        }
    terminal_path = output_root / row["work_directory"] / "roofer_terminal_v1.json"
    if not terminal_path.is_file():
        raise RuntimeError(f"missing Roofer terminal: {operation_id}")
    terminal = json.loads(terminal_path.read_text(encoding="utf-8"))
    if any(terminal.get(key) != row[key] for key in ("operation_unit_id", "condition_id", "stable_id")):
        raise RuntimeError(f"Roofer terminal identity mismatch: {operation_id}")
    if terminal["input"] != row["input"] or terminal["footprint"] != row["footprint"]:
        raise RuntimeError(f"Roofer terminal input binding mismatch: {operation_id}")
    for item in terminal.get("outputs") or ():
        verify_record(output_root, item)
    if terminal["status"] == "COMPLETED" and len(terminal["outputs"]) == 1:
        surfaces = load_cityjsonseq(output_root / terminal["outputs"][0]["path"])
    elif terminal["status"] == "FAILED":
        surfaces = []
    else:
        raise RuntimeError(f"invalid Roofer terminal state: {operation_id}")
    return points, surfaces, terminal


def inherit_closed_operations(output_root: Path, source_root: Path) -> dict[str, Any]:
    """Hash-verify and inherit only the closed v1 execution state; never rerun Roofer."""
    if output_root.exists() and any(output_root.iterdir()):
        raise RuntimeError("fresh add-once recovery namespace required")
    closure_path = source_root / "control/300-closed.local_v1.json"
    manifest_path = source_root / "control/artifact_manifest_v1.json"
    closure = json.loads(closure_path.read_text(encoding="utf-8"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if closure.get("status") != "300-CLOSED_LOCAL_SELECTED10_ORACLE_PRESENTATION" or manifest.get("status") != "COMPLETE_HASHED_SELECTED10_ORACLE_PRESENTATION":
        raise RuntimeError("source oracle artifact is not closed")
    for item in manifest["records"]:
        verify_record(source_root, item)
    output_root.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source_root / "operations", output_root / "operations")
    shutil.copytree(source_root / "freeze", output_root / "freeze")
    (output_root / "control").mkdir()
    for name in ("prepared_v1.json", "failure_receipt_v1.json", "freeze_recovery_v1.json"):
        path = source_root / "control" / name
        if path.is_file():
            shutil.copy2(path, output_root / "control" / name)
    body = {
        "schema": "jointbuildgs.p2.selected10_c1_c2_oracle.presentation_recovery_inheritance.v1",
        "status": "INHERITED_HASH_VERIFIED_OPERATIONS_NO_ROOFER_REEXECUTION",
        "source_root": source_root.as_posix(),
        "source_closure": file_record(closure_path, source_root),
        "source_manifest": file_record(manifest_path, source_root),
        "verified_source_record_count": len(manifest["records"]),
        "roofer_invocations_this_recovery": 0,
        "scientific_verdict": None,
    }
    write_new(output_root / "control/presentation_recovery_inheritance_v1.json", canonical_json_bytes(body))
    return body


def natural_zlim(points: PointSet | None, surfaces: Sequence[Surface]) -> tuple[float, float]:
    chunks = []
    if points is not None and len(points.xyz):
        chunks.append(np.asarray(points.xyz)[:, 2])
    chunks.extend(np.asarray(surface.xyz)[:, 2] for surface in surfaces if len(surface.xyz))
    values = np.concatenate(chunks) if chunks else np.asarray([0.0, 1.0])
    low, high = float(np.quantile(values, 0.002)), float(np.quantile(values, 0.998))
    pad = max((high - low) * 0.10, 1.0)
    return low - pad, high + pad


def point_panels(root: Path, points: PointSet, reference: Any, principal_zlim: tuple[float, float], prefix: str) -> list[Path]:
    xyz = np.asarray(points.xyz)
    classes = np.asarray(points.classification)
    colors = np.where(classes[:, None] == 6, np.asarray([[0.0, 0.62, 0.82]]), np.asarray([[0.78, 0.28, 0.68]]))
    natural = natural_zlim(points, [])
    result = []
    for view in VIEWS:
        path = root / f"{prefix}_{view}.png"
        point_panel(path, xyz, colors, reference, view, principal_zlim if view == "PRINCIPAL_SECTION" else natural)
        result.append(path)
    return result


def surface_panels_bound(root: Path, surfaces: Sequence[Surface], reference: Any, principal_zlim: tuple[float, float], prefix: str, status: str) -> list[Path]:
    if not surfaces:
        return [placeholder(root / f"{prefix}_{view}.png", prefix.upper(), status, view) for view in VIEWS]
    faces, semantics = surface_faces(surfaces)
    palette = {"RoofSurface": (0.18, 0.46, 0.76), "WallSurface": (0.67, 0.70, 0.73), "GroundSurface": (0.42, 0.62, 0.37)}
    colors = [palette.get(item, (0.55, 0.58, 0.62)) for item in semantics]
    natural = natural_zlim(None, surfaces)
    result = []
    for view in VIEWS:
        path = root / f"{prefix}_{view}.png"
        triangle_panel(path, faces, colors, reference, view, principal_zlim if view == "PRINCIPAL_SECTION" else natural)
        result.append(path)
    return result


def render_finalize(output_root: Path, artifact_root: Path, source_commit: str, run_id: str) -> dict[str, Any]:
    config = load_config()
    validate_config(config)
    refs = references(config, artifact_root)
    census = load_census_config()
    _best, cameras, camera_model, scene_ref = camera_context(artifact_root, census)
    crosswalk = json.loads((REPO / config["inputs"]["exact_view_manifest_git_path"]).read_text(encoding="utf-8"))
    visible = {str(row["basename"]) for row in crosswalk["rows"]}
    if len(visible) != 937:
        raise RuntimeError("exact camera membership drifted")
    pages: list[Path] = []
    bindings: list[dict[str, Any]] = []
    camera_receipts: list[dict[str, Any]] = []
    for page_index, stable_id in enumerate(config["building_ids"], 1):
        reference = refs[stable_id]
        c1_points, c1_surfaces, c1_terminal = method_geometry(output_root, METHODS[0], stable_id)
        c2_points, c2_surfaces, c2_terminal = method_geometry(output_root, METHODS[1], stable_id)
        lod2_surfaces = shifted_lod2(reference, float(config["frame"]["lod2_display_vertical_shift_m"]))
        principal_zlim = lod2_zlim(lod2_surfaces)
        panel_root = output_root / "qualitative/c1_c2" / stable_id / "panels"
        rgb, receipts = roofline_panels(
            panel_root,
            artifact_root,
            census,
            reference,
            cameras,
            camera_model,
            scene_ref,
            visible,
            stable_id,
            support=c1_points,
        )
        camera_receipts.extend(receipts)
        c1_input = point_panels(panel_root, c1_points, reference, principal_zlim, "c1_input")
        c1_output = surface_panels_bound(panel_root, c1_surfaces, reference, principal_zlim, "c1_roofer", c1_terminal["status"])
        c2_input = point_panels(panel_root, c2_points, reference, principal_zlim, "c2_input")
        c2_output = surface_panels_bound(panel_root, c2_surfaces, reference, principal_zlim, "c2_roofer", c2_terminal["status"])
        lod2 = surface_panels_bound(panel_root, lod2_surfaces, reference, principal_zlim, "lod2_reference", "MISSING")
        c1_status = c1_terminal["status"]
        c2_status = c2_terminal["status"]
        rows = [
            ("2024 RGB + 2022 roofline\nprojection only", rgb),
            ("C1 UAS LiDAR input\nGT footprint oracle", c1_input),
            (f"C1 Roofer\n{c1_status}; oracle only", c1_output),
            ("C2 current MVS input\nGT footprint oracle", c2_input),
            (f"C2 Roofer\n{c2_status}; oracle only", c2_output),
            ("2022 LoD2\nepoch context only", lod2),
        ]
        page = output_root / "qualitative/pages" / f"{page_index:02d}_{stable_id}_c1_c2_oracle_v1.png"
        subtitle = f"GT-footprint oracle diagnostic; official honest Stage3=false | PRINCIPAL Z={principal_zlim[0]:.1f}..{principal_zlim[1]:.1f}m from LoD2"
        _compose_sheet(page, rows, stable_id, subtitle)
        pages.append(page)
        for method, terminal in zip(METHODS, (c1_terminal, c2_terminal)):
            bindings.append({
                "stable_id": stable_id,
                "condition_id": method,
                "operation_unit_id": f"{method}|{stable_id}",
                "status": terminal["status"],
                "input_sha256": terminal.get("input", {}).get("sha256"),
                "footprint_sha256": terminal.get("footprint", {}).get("sha256"),
                "output_sha256": (terminal.get("outputs") or [{}])[0].get("sha256"),
                "oracle_diagnostic": True,
                "official_honest_stage3": False,
                "official_PASS_usable": None,
                "scientific_verdict": None,
            })
    receipt_root = output_root / "receipts"
    write_new(receipt_root / "roofer_metric_binding_v1.jsonl", jsonl_bytes(bindings))
    write_new(receipt_root / "roofline_camera_coverage_v1.jsonl", jsonl_bytes(camera_receipts))
    pdf = output_root / "reports/P2_SELECTED10_C1_C2_ORACLE_6row_4view_v1.pdf"
    pdf.parent.mkdir(parents=True, exist_ok=True)
    images = [Image.open(path).convert("RGB") for path in pages]
    images[0].save(pdf, "PDF", save_all=True, append_images=images[1:], resolution=150.0, quality=90)
    for image in images:
        image.close()
    links = "".join(
        f'<article><h2>{html.escape(stable_id)}</h2><a href="../{path.relative_to(output_root).as_posix()}"><img loading="lazy" src="../{path.relative_to(output_root).as_posix()}"></a></article>'
        for stable_id, path in zip(config["building_ids"], pages)
    )
    index = "<!doctype html><html lang='ko'><meta charset='utf-8'><style>body{font-family:sans-serif;max-width:1800px;margin:auto}img{width:100%}article{border-top:5px solid #222;margin:3rem 0}</style><h1>Selected 10 C1/C2 oracle diagnostic</h1><p>GT GroundSurface XY oracle; official honest Stage3=false. Principal-section Z only is fixed to each building's shifted LoD2 range.</p>" + links
    write_new(output_root / "reports/index.html", index.encode("utf-8"))
    manifest_records = []
    for path in sorted(item for item in output_root.rglob("*") if item.is_file() and item.name != "artifact_manifest_v1.json"):
        manifest_records.append(file_record(path, output_root))
    manifest = {
        "schema": "jointbuildgs.p2.selected10_c1_c2_oracle.manifest.v1",
        "status": "COMPLETE_HASHED_SELECTED10_ORACLE_PRESENTATION",
        "source_commit": source_commit,
        "run_id": run_id,
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "page_count": len(pages),
        "roofer_binding_count": len(bindings),
        "records": manifest_records,
        "official_PASS_usable": None,
        "scientific_verdict": None,
    }
    write_new(output_root / "control/artifact_manifest_v1.json", canonical_json_bytes(manifest))
    closed = {
        "schema": "jointbuildgs.p2.selected10_c1_c2_oracle.closed.v1",
        "status": "300-CLOSED_LOCAL_SELECTED10_ORACLE_PRESENTATION",
        "pdf": file_record(pdf, output_root),
        "gallery": file_record(output_root / "reports/index.html", output_root),
        "page_count": len(pages),
        "roofer_binding_count": len(bindings),
        "all_roofline_views_projected": all(row["status"] == "PROJECTED" for row in camera_receipts),
        "official_PASS_usable": None,
        "scientific_verdict": None,
    }
    write_new(output_root / "control/300-closed.local_v1.json", canonical_json_bytes(closed))
    return closed


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="mode", required=True)
    prepare_parser = sub.add_parser("prepare")
    prepare_parser.add_argument("--output-root", type=Path, required=True)
    prepare_parser.add_argument("--artifact-root", type=Path, required=True)
    terminal_parser = sub.add_parser("record-terminal")
    terminal_parser.add_argument("--output-root", type=Path, required=True)
    terminal_parser.add_argument("--operation-id", required=True)
    terminal_parser.add_argument("--exit-code", type=int, required=True)
    terminal_parser.add_argument("--runtime-seconds", type=int, required=True)
    repair_parser = sub.add_parser("repair-freeze")
    repair_parser.add_argument("--output-root", type=Path, required=True)
    inherit_parser = sub.add_parser("inherit-closed-operations")
    inherit_parser.add_argument("--output-root", type=Path, required=True)
    inherit_parser.add_argument("--source-root", type=Path, required=True)
    render_parser = sub.add_parser("render-finalize")
    render_parser.add_argument("--output-root", type=Path, required=True)
    render_parser.add_argument("--artifact-root", type=Path, required=True)
    render_parser.add_argument("--source-commit", required=True)
    render_parser.add_argument("--run-id", required=True)
    args = parser.parse_args()
    if args.mode == "prepare":
        result = prepare(args.output_root, args.artifact_root)
    elif args.mode == "record-terminal":
        result = record_terminal(args.output_root, args.operation_id, args.exit_code, args.runtime_seconds)
    elif args.mode == "repair-freeze":
        result = repair_freeze(args.output_root)
    elif args.mode == "inherit-closed-operations":
        result = inherit_closed_operations(args.output_root, args.source_root)
    else:
        result = render_finalize(args.output_root, args.artifact_root, args.source_commit, args.run_id)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
