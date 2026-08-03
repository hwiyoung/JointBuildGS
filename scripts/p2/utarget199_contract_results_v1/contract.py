"""C1/C2/C3 census over all 199 U_target buildings.

The task reuses already-frozen component jobs.  Stable-building bounding boxes
are opened only after geometry and R_derived exist, and are used solely for
identity/display association.  They never crop or modify scientific geometry.
"""

from __future__ import annotations

from collections import Counter, defaultdict
import csv
import io
import json
import math
from pathlib import Path
import shutil
from typing import Any, Iterable, Mapping, Sequence

import numpy as np

from scripts.p2_baselines.c1_c2_feasibility_pilot_v1.contract import (
    AddOnceStore,
    canonical_json_bytes,
    jsonl_bytes,
    parse_jsonl,
    provisional_output_check,
    roof_triangles,
    score_continuous,
    sha256_bytes,
)
from src.evaluation.c1_c2_dev_gate_closure_v1.evaluator import (
    cityjsonseq_feature_ids,
    evaluate_g3,
    parse_cityjsonseq_roof_surfaces,
    parse_val3dity_cjseq_stdout,
)


REPO = Path(__file__).resolve().parents[3]
CONFIG_PATH = REPO / "configs/p2/utarget199_contract_results_v1/census_v1.json"
METHODS = ("C1_L_upper", "C2_MVS", "C3_GS_image")


def load_config(path: Path = CONFIG_PATH) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def canonical_lf(path: Path) -> bytes:
    return path.read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")


def compact_record(path: Path, relative: str | None = None) -> dict[str, Any]:
    data = path.read_bytes()
    return {
        "path": relative or path.as_posix(),
        "bytes": len(data),
        "sha256": sha256_bytes(data),
    }


def validate_config(config: Mapping[str, Any] | None = None) -> dict[str, Any]:
    cfg = dict(config or load_config())
    scope = cfg.get("scope") or {}
    if (
        scope.get("population") != "U_target"
        or int(scope.get("building_count", -1)) != 199
        or tuple(scope.get("condition_ids") or ()) != METHODS
        or int(scope.get("expected_rows", -1)) != 597
        or scope.get("pre_execution_quality_exclusion_allowed") is not False
        or scope.get("missing_input_or_reference_is_retained") is not True
    ):
        raise RuntimeError("U_target=199 census scope is invalid")
    if cfg.get("scientific_verdict", "invalid") is not None:
        raise RuntimeError("scientific_verdict must remain null")
    if (cfg.get("evaluation") or {}).get("official_G3_G4_PASS", "invalid") is not None:
        raise RuntimeError("official G3/G4/PASS must remain null")
    if (cfg.get("association") or {}).get("bbox_role") != (
        "IDENTITY_AND_DISPLAY_ONLY_NO_GEOMETRY_CROP_OR_R_DERIVED_CHANGE"
    ):
        raise RuntimeError("building bbox role drifted")
    for name in ("roster", "result_contract"):
        spec = cfg["inputs"][name]
        data = canonical_lf(REPO / spec["git_path"])
        if len(data) != int(spec["canonical_lf_bytes"]) or sha256_bytes(data) != spec["canonical_lf_sha256"]:
            raise RuntimeError(f"canonical Git input differs: {name}")
    roster = list(csv.DictReader(io.StringIO(canonical_lf(REPO / cfg["inputs"]["roster"]["git_path"]).decode("utf-8"))))
    if len(roster) != 199 or len({row["stable_id"] for row in roster}) != 199:
        raise RuntimeError("roster is not exact 199 unique buildings")
    return {
        "status": "PASS",
        "buildings": 199,
        "methods": list(METHODS),
        "expected_rows": 597,
        "scientific_verdict": None,
    }


def _read_bound(root: Path, spec: Mapping[str, Any]) -> bytes:
    path = root / str(spec["path"])
    if path.is_symlink() or not path.is_file():
        raise RuntimeError(f"bound source record missing/non-regular: {path}")
    data = path.read_bytes()
    if len(data) != int(spec["bytes"]) or sha256_bytes(data) != spec["sha256"]:
        raise RuntimeError(f"bound source record differs: {path}")
    return data


def _roster(config: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows = list(csv.DictReader(io.StringIO(canonical_lf(REPO / config["inputs"]["roster"]["git_path"]).decode("utf-8"))))
    output: list[dict[str, Any]] = []
    for row in rows:
        output.append({
            **row,
            "bbox": [float(row[name]) for name in ("bbox_min_x", "bbox_min_y", "bbox_max_x", "bbox_max_y")],
            "reference_patch_ids": tuple(value for value in row.get("reference_candidate_patch_ids", "").split(";") if value),
        })
    return sorted(output, key=lambda row: row["stable_id"])


def _component_counts(
    component: Mapping[str, Any],
    roster: Sequence[Mapping[str, Any]],
    origin: Sequence[float],
    cell_m: float,
) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for ix_raw, iy_raw in component.get("cells") or ():
        x = float(origin[0]) + (int(ix_raw) + 0.5) * cell_m
        y = float(origin[1]) + (int(iy_raw) + 0.5) * cell_m
        for building in roster:
            min_x, min_y, max_x, max_y = building["bbox"]
            if min_x <= x <= max_x and min_y <= y <= max_y:
                counts[str(building["stable_id"])] += 1
    return dict(counts)


def associate_components(
    roster: Sequence[Mapping[str, Any]],
    components: Sequence[Mapping[str, Any]],
    origin: Sequence[float],
    cell_m: float,
) -> list[dict[str, Any]]:
    by_method: defaultdict[str, list[Mapping[str, Any]]] = defaultdict(list)
    building_counts: dict[tuple[str, str], Counter[str]] = {}
    for method in METHODS:
        for building in roster:
            building_counts[(method, str(building["stable_id"]))] = Counter()
    for component in components:
        method = str(component["condition_id"])
        if method not in METHODS:
            continue
        by_method[method].append(component)
        for stable_id, count in _component_counts(component, roster, origin, cell_m).items():
            building_counts[(method, stable_id)][str(component["component_id"])] += count
    rows: list[dict[str, Any]] = []
    for method in METHODS:
        for building in roster:
            stable_id = str(building["stable_id"])
            counts = building_counts[(method, stable_id)]
            ranked = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
            selected = ranked[0][0] if ranked else None
            rows.append({
                "building_id": stable_id,
                "method_id": method,
                "original_split": building.get("candidate_split") or building.get("split") or "",
                "candidate_group_id": building.get("candidate_group_id") or building.get("spatial_group_id") or "",
                "bbox_min_x": building["bbox"][0],
                "bbox_min_y": building["bbox"][1],
                "bbox_max_x": building["bbox"][2],
                "bbox_max_y": building["bbox"][3],
                "component_id": selected,
                "operation_unit_id": f"{method}|{selected}" if selected else None,
                "component_cell_count_inside_bbox": ranked[0][1] if ranked else 0,
                "overlapping_component_count": len(ranked),
                "component_candidates": [
                    {"component_id": component_id, "cell_count_inside_bbox": count}
                    for component_id, count in ranked
                ],
                "e_paired_candidate": str(building.get("e_paired_candidate", "")).lower() == "true",
                "strict_e_paired": str(building.get("e_paired", "")).lower() == "true",
                "input_exclusion_reason": building.get("candidate_exclusion_reason") or building.get("exclusion_reason") or "",
                "current_image_view_support": int(building.get("current_image_view_support") or 0),
                "mvs_support_cells": int(building.get("mvs_support_cells") or 0),
                "c4_support_cells": int(building.get("c4_support_cells") or 0),
                "c5_prior_available": str(building.get("c5_prior_available_by_stable_id", "")).lower() == "true",
                "reference_patch_ids": list(building["reference_patch_ids"]),
            })
    selected_usage = Counter(row["operation_unit_id"] for row in rows if row["operation_unit_id"])
    for row in rows:
        row["selected_component_building_multiplicity"] = selected_usage.get(row["operation_unit_id"], 0)
        row["one_to_one_building_component"] = bool(
            row["operation_unit_id"]
            and int(row["overlapping_component_count"]) == 1
            and int(row["selected_component_building_multiplicity"]) == 1
        )
        if not row["operation_unit_id"]:
            row["association_status"] = "UNASSOCIATED"
        elif int(row["selected_component_building_multiplicity"]) > 1 and int(row["overlapping_component_count"]) > 1:
            row["association_status"] = "SHARED_AND_MULTI_COMPONENT"
        elif int(row["selected_component_building_multiplicity"]) > 1:
            row["association_status"] = "SHARED_COMPONENT"
        elif int(row["overlapping_component_count"]) > 1:
            row["association_status"] = "MULTI_COMPONENT"
        else:
            row["association_status"] = "ONE_TO_ONE"
    if len(rows) != len(roster) * len(METHODS):
        raise RuntimeError("association is not exact roster x three methods")
    return rows


def _copy_verified(source: Path, target: Path, spec: Mapping[str, Any]) -> dict[str, Any]:
    data = source.read_bytes()
    if len(data) != int(spec["bytes"]) or sha256_bytes(data) != spec["sha256"]:
        raise RuntimeError(f"operation input identity mismatch: {source}")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    return {"path": target.as_posix(), "bytes": len(data), "sha256": spec["sha256"]}


def _source_terminal(source_root: Path, unit: Mapping[str, Any]) -> dict[str, Any] | None:
    work = source_root / str(unit["work_directory"])
    if unit["condition_id"] == "C3_GS_image":
        receipt = work / "roofer_terminal_v1.json"
        if not receipt.is_file():
            return None
        data = json.loads(receipt.read_text(encoding="utf-8"))
        return data if data.get("status") == "COMPLETED" else None
    records = source_root / "operation_records"
    if not records.is_dir():
        return None
    for path in records.glob("*/final_v1.json"):
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("operation_unit_id") == unit["operation_unit_id"] and data.get("status") == "COMPLETE":
            return data
    return None


def _copy_source_outputs(
    source_root: Path,
    output_root: Path,
    unit: Mapping[str, Any],
    terminal: Mapping[str, Any],
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    target_dir = output_root / str(unit["output_directory"])
    target_dir.mkdir(parents=True, exist_ok=True)
    for record in terminal.get("output_records") or ():
        source = source_root / str(record["path"])
        data = source.read_bytes()
        if len(data) != int(record["bytes"]) or sha256_bytes(data) != record["sha256"]:
            raise RuntimeError(f"reused Roofer output differs: {source}")
        target = target_dir / source.name
        target.write_bytes(data)
        records.append({"path": target.relative_to(output_root).as_posix(), "bytes": len(data), "sha256": record["sha256"]})
    return records


def prepare(
    store: AddOnceStore,
    *,
    c1_c2_source_root: Path,
    c3_source_root: Path,
    source_commit: str,
    run_id: str,
) -> dict[str, Any]:
    done = store.path("control/prepared_v1.json")
    if done.is_file():
        body = json.loads(done.read_text(encoding="utf-8"))
        if body.get("source_commit") != source_commit or body.get("run_id") != run_id:
            raise RuntimeError("existing preparation identity mismatch")
        return {**body, "fast_path": True, "new_writes": 0}
    config = load_config()
    validate_config(config)
    source_specs = (
        ("c1_c2_source", c1_c2_source_root),
        ("c3_source", c3_source_root),
    )
    all_jobs: list[dict[str, Any]] = []
    components: list[dict[str, Any]] = []
    roots_by_method: dict[str, Path] = {}
    source_records: dict[str, Any] = {}
    for name, root in source_specs:
        spec = config["inputs"][name]
        jobs_data = _read_bound(root, spec["all_jobs"])
        components_data = _read_bound(root, spec["components"])
        jobs = parse_jsonl(jobs_data)
        comp = parse_jsonl(components_data)
        all_jobs.extend(jobs)
        components.extend(comp)
        for method in {row["condition_id"] for row in jobs}:
            roots_by_method[str(method)] = root
        source_records[name] = {
            "root": root.as_posix(),
            "all_jobs": {**spec["all_jobs"], "full_read_and_digest_passes": 1},
            "components": {**spec["components"], "full_read_and_digest_passes": 1},
        }
    if {row["condition_id"] for row in all_jobs} != set(METHODS):
        raise RuntimeError("source jobs do not contain exact C1/C2/C3")
    roster = _roster(config)
    associations = associate_components(
        roster,
        components,
        config["frame"]["grid_origin_xy"],
        float(config["frame"]["grid_cell_m"]),
    )
    jobs_by_id = {str(row["operation_unit_id"]): row for row in all_jobs}
    selected_ids = sorted({str(row["operation_unit_id"]) for row in associations if row["operation_unit_id"]})
    missing_jobs = sorted(set(selected_ids) - set(jobs_by_id))
    if missing_jobs:
        raise RuntimeError(f"associated components lack frozen jobs: {missing_jobs[:3]}")
    unit_rows: list[dict[str, Any]] = []
    reused_count = 0
    for unit_id in selected_ids:
        source_unit = jobs_by_id[unit_id]
        method = str(source_unit["condition_id"])
        source_root = roots_by_method[method]
        work_relative = f"operations/{method}/{source_unit['component_id']}/work"
        work = store.path(work_relative)
        input_record = _copy_verified(
            source_root / str(source_unit["input"]["path"]),
            work / "input.las",
            source_unit["input"],
        )
        r_record = _copy_verified(
            source_root / str(source_unit["r_derived"]["path"]),
            work / "r_derived.geojson",
            source_unit["r_derived"],
        )
        output_relative = f"{work_relative}/out"
        terminal = _source_terminal(source_root, source_unit)
        reuse_records: list[dict[str, Any]] = []
        if terminal and terminal.get("output_records"):
            reuse_records = _copy_source_outputs(source_root, store.root, {**source_unit, "output_directory": output_relative}, terminal)
        if reuse_records:
            reused_count += 1
            result = {
                "schema": "jointbuildgs.p2_utarget199_roofer_terminal.v1",
                "operation_unit_id": unit_id,
                "condition_id": method,
                "component_id": source_unit["component_id"],
                "status": "COMPLETED_REUSED_EXACT",
                "exit_code": int(terminal.get("exit_code", 0)),
                "runtime_seconds": terminal.get("runtime_seconds"),
                "input": {**input_record, "path": f"{work_relative}/input.las"},
                "r_derived": {**r_record, "path": f"{work_relative}/r_derived.geojson"},
                "output_records": reuse_records,
                "source_namespace": source_root.as_posix(),
                "duplicate_roofer_execution_prevented": True,
                "scientific_verdict": None,
            }
            store.add_json(f"terminal/{sha256_bytes(unit_id.encode())[:24]}.json", result)
        unit_rows.append({
            "operation_unit_id": unit_id,
            "condition_id": method,
            "component_id": source_unit["component_id"],
            "work_directory": work_relative,
            "output_directory": output_relative,
            "source_output_reused": bool(reuse_records),
            "terminal_record": f"terminal/{sha256_bytes(unit_id.encode())[:24]}.json",
        })
    association_record = store.add("freeze/utarget199_association_v1.jsonl", jsonl_bytes(associations))
    unit_record = store.add("freeze/execution_units_v1.jsonl", jsonl_bytes(unit_rows))
    tsv = "operation_unit_id\twork_directory\tsource_output_reused\n" + "".join(
        f"{row['operation_unit_id']}\t{row['work_directory']}\t{str(row['source_output_reused']).lower()}\n"
        for row in unit_rows
    )
    tsv_record = store.add("freeze/execution_units_v1.tsv", tsv.encode("utf-8"))
    body = {
        "schema": "jointbuildgs.p2_utarget199_prepared.v1",
        "status": "PREPARED_GEOMETRY_BEFORE_REFERENCE",
        "task_id": config["task_id"],
        "run_id": run_id,
        "source_commit": source_commit,
        "source_records": source_records,
        "association": association_record,
        "execution_units": unit_record,
        "execution_units_tsv": tsv_record,
        "building_count": 199,
        "result_rows_expected": 597,
        "unique_execution_units": len(unit_rows),
        "source_output_units_reused": reused_count,
        "roofer_units_remaining": len(unit_rows) - reused_count,
        "reference_inputs_opened": 0,
        "bbox_modified_geometry_or_r_derived": False,
        "scientific_verdict": None,
    }
    store.add_json("control/prepared_v1.json", body)
    return body


def _unit(store: AddOnceStore, unit_id: str) -> dict[str, Any]:
    prepared = json.loads(store.path("control/prepared_v1.json").read_text(encoding="utf-8"))
    rows = parse_jsonl(store.read_verified(prepared["execution_units"]))
    matches = [row for row in rows if row["operation_unit_id"] == unit_id]
    if len(matches) != 1:
        raise RuntimeError("operation unit missing/ambiguous")
    return matches[0]


def record_roofer_terminal(
    store: AddOnceStore,
    *,
    unit_id: str,
    exit_code: int,
    runtime_seconds: int,
) -> dict[str, Any]:
    unit = _unit(store, unit_id)
    terminal_path = store.path(unit["terminal_record"])
    if terminal_path.is_file():
        body = json.loads(terminal_path.read_text(encoding="utf-8"))
        return {**body, "fast_path": True, "new_writes": 0}
    work = store.path(unit["work_directory"])
    output_dir = store.path(unit["output_directory"])
    check = provisional_output_check(output_dir) if exit_code == 0 and output_dir.is_dir() else None
    output_records: list[dict[str, Any]] = []
    if output_dir.is_dir():
        for path in sorted(output_dir.rglob("*")):
            if path.is_file() and not path.is_symlink():
                output_records.append(compact_record(path, path.relative_to(store.root).as_posix()))
    body = {
        "schema": "jointbuildgs.p2_utarget199_roofer_terminal.v1",
        "operation_unit_id": unit_id,
        "condition_id": unit["condition_id"],
        "component_id": unit["component_id"],
        "status": "COMPLETED" if exit_code == 0 else "FAILED",
        "exit_code": exit_code,
        "runtime_seconds": runtime_seconds,
        "output_records": output_records,
        "G0_component_generated": bool(exit_code == 0 and check and check["G0_generated"]),
        "G1_component_schema_semantic": check["G1_schema_semantic"] if check else False,
        "G1_failure_reasons": check["G1_failure_reasons"] if check else ["NO_VALIDATABLE_CITYJSON_OUTPUT"],
        "source_namespace": None,
        "duplicate_roofer_execution_prevented": False,
        "scientific_verdict": None,
    }
    store.add_json(unit["terminal_record"], body)
    return body


def verify_terminal(store: AddOnceStore, unit_id: str) -> dict[str, Any]:
    unit = _unit(store, unit_id)
    path = store.path(unit["terminal_record"])
    if not path.is_file():
        raise RuntimeError("terminal record missing")
    body = json.loads(path.read_text(encoding="utf-8"))
    if body.get("operation_unit_id") != unit_id:
        raise RuntimeError("terminal identity mismatch")
    for record in body.get("output_records") or ():
        data = store.path(record["path"]).read_bytes()
        if len(data) != int(record["bytes"]) or sha256_bytes(data) != record["sha256"]:
            raise RuntimeError("terminal output differs")
    return {**body, "verified": True}


def _reference_rows(
    roster: Sequence[Mapping[str, Any]],
    source: Path,
    expected: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    data = source.read_bytes()
    if len(data) != int(expected["bytes"]) or sha256_bytes(data) != expected["sha256"]:
        raise RuntimeError("reference candidate cell input differs")
    patch_to_buildings: defaultdict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for building in roster:
        for patch in building["reference_patch_ids"]:
            patch_to_buildings[str(patch)].append(building)
    rows: list[dict[str, Any]] = []
    for cell in csv.DictReader(io.StringIO(data.decode("utf-8"))):
        x, y = float(cell["cell_x"]), float(cell["cell_y"])
        for building in patch_to_buildings.get(cell["patch_id"], ()):
            min_x, min_y, max_x, max_y = building["bbox"]
            if min_x <= x <= max_x and min_y <= y <= max_y:
                rows.append({**cell, "stable_id": building["stable_id"]})
    counts = Counter(row["stable_id"] for row in rows)
    return rows, {
        "path": source.as_posix(),
        "bytes": len(data),
        "sha256": expected["sha256"],
        "full_read_and_digest_passes": 1,
        "global_rows_streamed": sum(1 for _ in data.splitlines()) - 1,
        "retained_buildings": len(counts),
        "retained_building_cell_rows": len(rows),
    }


def _city_file(output_dir: Path) -> Path | None:
    files = sorted(path for path in output_dir.rglob("*") if path.is_file() and path.suffix in (".jsonl", ".json"))
    return files[0] if len(files) == 1 else None


def _g4_candidate(metrics: Mapping[str, Any], thresholds: Mapping[str, float]) -> bool | None:
    values = {
        "reference_vertical_coverage_min": metrics.get("reference_vertical_coverage"),
        "height_error_mae_m_max": metrics.get("height_error_mae_m"),
        "RMSZ_m_max": metrics.get("RMSZ_m"),
        "RMSXY_m_max": metrics.get("RMSXY_m"),
        "surface_distance_rmse_m_max": metrics.get("surface_distance_rmse_m"),
        "surface_distance_p95_m_max": metrics.get("surface_distance_p95_m"),
    }
    if any(value is None or not math.isfinite(float(value)) for value in values.values()):
        return None
    return all(
        float(values[name]) >= float(limit) if name.endswith("_min") else float(values[name]) <= float(limit)
        for name, limit in thresholds.items()
    )


def _csv_bytes(rows: Sequence[Mapping[str, Any]], fields: Sequence[str]) -> bytes:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=list(fields), lineterminator="\n", extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode("utf-8")


def finalize(
    store: AddOnceStore,
    *,
    reference_cells: Path,
    g2_receipts: Path,
    source_commit: str,
    run_id: str,
) -> dict[str, Any]:
    done = store.path("control/finalized_v1.json")
    if done.is_file():
        body = json.loads(done.read_text(encoding="utf-8"))
        return {**body, "fast_path": True, "new_writes": 0}
    config = load_config()
    validate_config(config)
    prepared = json.loads(store.path("control/prepared_v1.json").read_text(encoding="utf-8"))
    if prepared.get("source_commit") != source_commit or prepared.get("run_id") != run_id:
        raise RuntimeError("finalize identity differs from preparation")
    associations = parse_jsonl(store.read_verified(prepared["association"]))
    units = {row["operation_unit_id"]: row for row in parse_jsonl(store.read_verified(prepared["execution_units"]))}
    terminals = {unit_id: verify_terminal(store, unit_id) for unit_id in units}
    roster = _roster(config)
    reference, reference_record = _reference_rows(roster, reference_cells, config["inputs"]["reference_candidate_cells"])
    reference_by_building: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in reference:
        reference_by_building[str(row["stable_id"])].append(row)
    reference_output = store.add("freeze/utarget199_reference_cells_v1.jsonl", jsonl_bytes(reference))
    g2_rows = parse_jsonl(g2_receipts.read_bytes())
    g2_by_unit = {row["operation_unit_id"]: row for row in g2_rows}
    if set(g2_by_unit) != set(units):
        raise RuntimeError("G2 receipt set differs from execution unit set")
    eval_config = {
        "gates": {
            "G3": {
                "grid_cell_m": config["frame"]["grid_cell_m"],
                "grid_origin_xy": config["frame"]["grid_origin_xy"],
                "matching_version": "UAS_PATCH_TO_ROOFER_ROOFSURFACE_GRID_BILATERAL_v1",
                "matching_normal_angle_degrees_max": config["evaluation"]["candidate_G3"]["normal_angle_degrees_max"],
                "bilateral_support_overlap_min": config["evaluation"]["candidate_G3"]["bilateral_support_overlap_min"],
                "candidate_thresholds": {key: value for key, value in config["evaluation"]["candidate_G3"].items() if key not in ("normal_angle_degrees_max", "bilateral_support_overlap_min")},
            }
        }
    }
    component_cache: dict[str, dict[str, Any]] = {}
    for unit_id, unit in units.items():
        terminal = terminals[unit_id]
        output_dir = store.path(unit["output_directory"])
        city = _city_file(output_dir)
        check = provisional_output_check(output_dir) if city else None
        triangles = roof_triangles(output_dir) if city and check and check["G0_generated"] else []
        surfaces = parse_cityjsonseq_roof_surfaces(city.read_bytes(), city.name) if city else []
        g2 = g2_by_unit[unit_id]
        component_cache[unit_id] = {
            "terminal": terminal,
            "city": city,
            "check": check,
            "triangles": triangles,
            "surfaces": surfaces,
            "component_G0": bool(check and check["G0_generated"]),
            "component_G1": bool(check and check["G1_schema_semantic"]),
            "component_G2": bool(g2.get("unit_valid")) if g2.get("completed") else None,
            "g2": g2,
        }
    rows: list[dict[str, Any]] = []
    for association in associations:
        unit_id = association.get("operation_unit_id")
        component = component_cache.get(str(unit_id)) if unit_id else None
        one_to_one = bool(association["one_to_one_building_component"])
        component_g0 = bool(component and component["component_G0"])
        component_g1 = bool(component and component["component_G1"])
        component_g2 = component["component_G2"] if component else None
        g0 = bool(one_to_one and component_g0)
        g1 = bool(g0 and component_g1)
        g2 = bool(g1 and component_g2 is True)
        refs = reference_by_building[str(association["building_id"])]
        metrics = score_continuous(refs, component["triangles"] if component else [])
        if refs and component and component["surfaces"]:
            g3_metrics = evaluate_g3(
                refs,
                component["surfaces"],
                [association[name] for name in ("bbox_min_x", "bbox_min_y", "bbox_max_x", "bbox_max_y")],
                eval_config,
            )
            g3_candidate: bool | None = bool(g3_metrics["G3_roof_structure_acceptable"])
        else:
            g3_metrics = {"candidate_only": True, "null_reason": "NO_REFERENCE_OR_PREDICTED_ROOF"}
            g3_candidate = None
        g4_candidate = _g4_candidate(metrics, config["evaluation"]["candidate_G4"])
        pass_candidate = bool(g0 and g1 and g2 and g3_candidate is True and g4_candidate is True) if g3_candidate is not None and g4_candidate is not None else None
        failure_reasons: list[str] = []
        if not association["operation_unit_id"]:
            failure_reasons.append("NO_METHOD_COMPONENT_INSIDE_BUILDING_BBOX")
        if association["association_status"] != "ONE_TO_ONE":
            failure_reasons.append(f"BUILDING_COMPONENT_{association['association_status']}")
        if one_to_one and not component_g0:
            failure_reasons.append("ROOFER_LOD22_NOT_GENERATED")
        if g0 and not component_g1:
            failure_reasons.append("SCHEMA_OR_SEMANTIC_CONFORMANCE_FAILED")
        if g1 and component_g2 is not True:
            failure_reasons.append("GEOMETRY_TOPOLOGY_VALIDITY_FAILED_OR_MISSING")
        if not refs:
            failure_reasons.append("UAS_REFERENCE_SCORE_UNAVAILABLE")
        row = {
            **{key: association[key] for key in association if key not in ("component_candidates", "reference_patch_ids")},
            "run_id": run_id,
            "git_commit": source_commit,
            "criterion_version": config["evaluation"]["criterion_version"],
            "reference_role": config["evaluation"]["c1_reference_role"] if association["method_id"] == "C1_L_upper" else config["evaluation"]["c2_c3_reference_role"],
            "reference_cell_count": len(refs),
            "component_G0_generated": component_g0,
            "component_G1_schema_semantic": component_g1,
            "component_G2_geometry_topology_valid": component_g2,
            "G0_generated": g0,
            "G1_schema_semantic": g1,
            "G2_geometry_topology_valid": g2,
            "G3_candidate": g3_candidate,
            "G4_candidate": g4_candidate,
            "PASS_candidate": pass_candidate,
            "G3_roof_structure_acceptable": None,
            "G4_geometric_accuracy_acceptable": None,
            "PASS_usable": None,
            "official_null_reason": config["evaluation"]["official_null_reason"],
            "continuous_metrics": metrics,
            "G3_candidate_metrics": g3_metrics,
            "failure_reasons": failure_reasons,
            "scientific_verdict": None,
        }
        rows.append(row)
    if len(rows) != 597 or len({(row["building_id"], row["method_id"]) for row in rows}) != 597:
        raise RuntimeError("result matrix is not exact 199x3")
    metrics_record = store.add(config["outputs"]["building_method_metrics"], jsonl_bytes(rows))
    gate_fields = [
        "building_id", "method_id", "original_split", "association_status", "reference_cell_count",
        "G0_generated", "G1_schema_semantic", "G2_geometry_topology_valid", "G3_candidate", "G4_candidate",
        "PASS_candidate", "G3_roof_structure_acceptable", "G4_geometric_accuracy_acceptable", "PASS_usable",
        "criterion_version", "official_null_reason", "failure_reasons",
    ]
    gate_rows = [{**row, "failure_reasons": ";".join(row["failure_reasons"])} for row in rows]
    gates_record = store.add(config["outputs"]["acceptance_gates"], _csv_bytes(gate_rows, gate_fields))
    summary_rows: list[dict[str, Any]] = []
    funnel_rows: list[dict[str, Any]] = []
    for method in METHODS:
        subset = [row for row in rows if row["method_id"] == method]
        summary_rows.append({
            "method_id": method,
            "U_target": 199,
            "associated": sum(row["operation_unit_id"] is not None for row in subset),
            "one_to_one": sum(row["one_to_one_building_component"] for row in subset),
            "reference_scorable": sum(row["reference_cell_count"] > 0 for row in subset),
            "G0": sum(row["G0_generated"] for row in subset),
            "G1": sum(row["G1_schema_semantic"] for row in subset),
            "G2": sum(row["G2_geometry_topology_valid"] for row in subset),
            "G3_candidate": sum(row["G3_candidate"] is True for row in subset),
            "G4_candidate": sum(row["G4_candidate"] is True for row in subset),
            "PASS_candidate": sum(row["PASS_candidate"] is True for row in subset),
            "official_PASS_usable": "null",
            "scientific_verdict": "null",
        })
        stages = [
            ("U_target", 199),
            ("ASSOCIATED", sum(row["operation_unit_id"] is not None for row in subset)),
            ("ONE_TO_ONE", sum(row["one_to_one_building_component"] for row in subset)),
            ("G0", sum(row["G0_generated"] for row in subset)),
            ("G1", sum(row["G1_schema_semantic"] for row in subset)),
            ("G2", sum(row["G2_geometry_topology_valid"] for row in subset)),
            ("G3_CANDIDATE", sum(row["G3_candidate"] is True for row in subset)),
            ("G4_CANDIDATE", sum(row["G4_candidate"] is True for row in subset)),
            ("PASS_CANDIDATE", sum(row["PASS_candidate"] is True for row in subset)),
            ("PASS_USABLE_OFFICIAL", "null"),
        ]
        funnel_rows.extend({"method_id": method, "stage": stage, "count": count, "denominator": 199} for stage, count in stages)
    summary_record = store.add(config["outputs"]["method_summary"], _csv_bytes(summary_rows, list(summary_rows[0])))
    funnel_record = store.add(config["outputs"]["gate_funnel"], _csv_bytes(funnel_rows, ["method_id", "stage", "count", "denominator"]))
    population_rows = [
        {"stage": "U_target", "count": 199, "meaning": "all stable-ID buildings in the AOI"},
        {"stage": "UAS_reference_candidate", "count": sum(str(row.get("e_paired_candidate", "")).lower() == "true" for row in roster), "meaning": "candidate patch reference; not an execution filter"},
        {"stage": "strict_independent_reference", "count": sum(str(row.get("e_paired", "")).lower() == "true" for row in roster), "meaning": "strict independent reference evidence"},
        {"stage": "no_reference_but_retained", "count": 199 - len({row["stable_id"] for row in reference}), "meaning": "processed and retained with score missingness"},
    ]
    population_record = store.add(config["outputs"]["population_funnel"], _csv_bytes(population_rows, ["stage", "count", "meaning"]))
    body = {
        "schema": "jointbuildgs.p2_utarget199_finalized.v1",
        "status": "TECHNICAL_RESULTS_COMPLETE_QUALITATIVE_PENDING",
        "task_id": config["task_id"],
        "run_id": run_id,
        "source_commit": source_commit,
        "result_rows": 597,
        "building_count": 199,
        "method_count": 3,
        "reference_input": reference_record,
        "reference_cells": reference_output,
        "building_method_metrics": metrics_record,
        "acceptance_gates": gates_record,
        "method_summary": summary_record,
        "gate_funnel": funnel_record,
        "population_funnel": population_record,
        "summary": summary_rows,
        "official_PASS_usable": None,
        "scientific_verdict": None,
    }
    store.add_json("control/finalized_v1.json", body)
    return body
