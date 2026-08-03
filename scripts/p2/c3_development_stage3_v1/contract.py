"""Outcome-separated C3 checkpoint to development-51 Roofer jobs.

Geometry and every ``R_derived`` are add-once frozen before the score-only R3
development cells are accepted.  This module never accepts GT footprints,
reference meshes, validation/held-out inputs, or a G3/G4/PASS threshold.
"""

from __future__ import annotations

from collections import Counter, defaultdict
import csv
import io
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from src.stage3.c3_checkpoint_roofer_adapter_v1 import (
    load_c3_checkpoint,
    materialize_component_ready_evidence,
)
from scripts.p2_baselines.c1_c2_feasibility_pilot_v1.contract import (
    AddOnceStore,
    Point,
    canonical_json_bytes,
    compact_file_record,
    component_job,
    derive_components,
    jsonl_bytes,
    parse_jsonl,
    provisional_output_check,
    read_csv,
    sha256_bytes,
)


REPO = Path(__file__).resolve().parents[3]
CONFIG_PATH = REPO / "configs/p2/c3_development_stage3_v1/stage3_v1.json"
BASE_CONFIG_PATH = REPO / "configs/p2_baselines/c1_c2_feasibility_pilot_v1/pilot_v1.json"
CONDITION = "C3_GS_image"


def load_config() -> dict[str, Any]:
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def load_reused_config() -> dict[str, Any]:
    return json.loads(BASE_CONFIG_PATH.read_text(encoding="utf-8"))


def validate_contract(config: Mapping[str, Any] | None = None) -> dict[str, Any]:
    config = dict(config or load_config())
    base = load_reused_config()
    if config.get("condition_id") != CONDITION:
        raise RuntimeError("condition must be exact C3_GS_image")
    scope = config.get("scope") or {}
    if (
        scope.get("split") != "development"
        or int(scope.get("building_count", -1)) != 51
        or int(scope.get("reference_cell_rows", -1)) != 21714
        or any(scope.get(key) is not False for key in (
            "validation_allowed", "held_out_allowed", "c1_c2_rerun_allowed"
        ))
    ):
        raise RuntimeError("development-only scope contract mismatch")
    if config.get("scientific_verdict", "invalid") is not None:
        raise RuntimeError("scientific_verdict must remain null")
    result = config.get("result") or {}
    if any(result.get(key, "invalid") is not None for key in ("G3", "G4", "PASS_usable", "scientific_verdict")):
        raise RuntimeError("G3/G4/PASS/scientific verdict must remain null")
    reused = config.get("reused_contract") or {}
    if reused.get("path") != BASE_CONFIG_PATH.relative_to(REPO).as_posix():
        raise RuntimeError("reused contract path mismatch")
    fields = tuple(reused.get("fields") or ())
    if fields != ("frame", "condition_geometry", "roofer_pointcloud", "stage3"):
        raise RuntimeError("reused contract field allowlist mismatch")
    if base["frame"]["grid_cell_m"] != 1.0:
        raise RuntimeError("base component grid is no longer the frozen 1 m contract")
    expected_args = [
        "--id-attribute", "component_id", "--jobs", "1", "--srs", "EPSG:25832",
        "--bld-class", "6", "--grnd-class", "2", "--lod22",
    ]
    if base["stage3"]["command_args"] != expected_args:
        raise RuntimeError("Roofer command differs from frozen C1/C2 contract")
    material = config.get("materialization") or {}
    if (
        material.get("surface_eligibility") != "STORED_STAGE2_GROUP_ID_GTE_ZERO"
        or material.get("regroup_allowed") is not False
        or float(material.get("grid_cell_m", -1)) != 1.0
        or material.get("output_xy") != "FROZEN_1M_CELL_CENTER"
        or material.get("opacity_threshold", "invalid") is not None
        or material.get("performance_interpretation") != "TECHNICAL_DIAGNOSTIC_ONLY"
    ):
        raise RuntimeError("stored-group materialization contract mismatch")
    return {
        "status": "PASS",
        "condition_id": CONDITION,
        "reused_contract_path": reused["path"],
        "roofer_image": base["stage3"]["roofer_image"],
        "roofer_command_args": expected_args,
        "G3": None,
        "G4": None,
        "PASS_usable": None,
        "scientific_verdict": None,
    }


def _validate_r4_attestation(config: Mapping[str, Any]) -> dict[str, Any]:
    manifest_path = REPO / str(config["inputs"]["r4_manifest_git_path"])
    if manifest_path.is_symlink() or not manifest_path.is_file():
        raise RuntimeError("R4 Git manifest missing/non-regular")
    manifest = json.loads(manifest_path.read_bytes())
    expected = config["inputs"]["r4_final_checkpoint"]
    matches = [
        item for item in manifest.get("external_records", [])
        if item.get("path") == expected["record_path"]
    ]
    if len(matches) != 1:
        raise RuntimeError("R4 final checkpoint attestation is missing/ambiguous")
    record = matches[0]
    if int(record.get("bytes", -1)) != int(expected["bytes"]) or record.get("sha256") != expected["sha256"]:
        raise RuntimeError("R4 final checkpoint identity differs from config")
    if manifest.get("scientific_verdict", "invalid") is not None:
        raise RuntimeError("R4 technical manifest scientific verdict is not null")
    return {
        "git_path": manifest_path.relative_to(REPO).as_posix(),
        "task_id": manifest.get("task_id"),
        "record": record,
    }


def _point_rows(evidence: Any) -> list[Point]:
    return [
        Point(p.x, p.y, p.z, p.classification, p.ix, p.iy)
        for p in evidence.points
    ]


def prepare_geometry(
    store: AddOnceStore,
    *,
    checkpoint_path: Path,
    source_commit: str,
    run_id: str,
) -> dict[str, Any]:
    """Freeze C3 materialization, components, LAS and R_derived without score input."""

    completed = store.path("control/c3_geometry_frozen_v1.json")
    if completed.is_file():
        body = json.loads(completed.read_bytes())
        if body.get("status") != "FROZEN" or body.get("source_commit") != source_commit or body.get("run_id") != run_id:
            raise RuntimeError("existing C3 geometry freeze identity mismatch")
        return {**body, "fast_path": True, "checkpoint_reopens": 0, "new_writes": 0}
    config = load_config()
    validate_contract(config)
    base = load_reused_config()
    attestation = _validate_r4_attestation(config)
    expected = config["inputs"]["r4_final_checkpoint"]
    if checkpoint_path.is_symlink() or not checkpoint_path.is_file():
        raise RuntimeError("C3 checkpoint missing/non-regular")
    if checkpoint_path.stat().st_size != int(expected["bytes"]):
        raise RuntimeError("C3 checkpoint byte count differs from R4 attestation")

    arrays = load_c3_checkpoint(checkpoint_path)
    evidence = materialize_component_ready_evidence(arrays)
    expected_counts = {
        "checkpoint_iteration": int(expected["expected_iteration"]),
        "source_primitive_count": int(expected["expected_primitives"]),
        "stored_stage2_group_count": int(expected["expected_stage2_groups"]),
        "stored_grouped_primitive_count": int(expected["expected_grouped_primitives"]),
    }
    observed_counts = {key: evidence.lineage_stats.get(key) for key in expected_counts}
    if observed_counts != expected_counts:
        raise RuntimeError(
            f"C3 checkpoint structural counts differ from exact R4 binding: {observed_counts}"
        )
    points = _point_rows(evidence)
    components, component_map = derive_components(CONDITION, points, base)
    if not components:
        raise RuntimeError("C3 materialization produced no eligible component")

    lineage = store.add(
        "freeze/c3_surface_group_lineage_v1.jsonl",
        jsonl_bytes([group.__dict__ for group in evidence.groups]),
    )
    component_records: list[dict[str, Any]] = []
    jobs: list[dict[str, Any]] = []
    for component in components:
        component_records.append(component)
        if component["pre_roofer_failure"]:
            continue
        input_bytes, r_derived_bytes = component_job(CONDITION, component, points, base)
        prefix = f"operations/{CONDITION}/{component['component_id']}/work"
        input_record = store.add(f"{prefix}/input.las", input_bytes)
        roofprint_record = store.add(f"{prefix}/r_derived.geojson", r_derived_bytes)
        jobs.append({
            "operation_unit_id": f"{CONDITION}|{component['component_id']}",
            "condition_id": CONDITION,
            "component_id": component["component_id"],
            "work_directory": prefix,
            "input": input_record,
            "r_derived": roofprint_record,
            "output_directory": f"{prefix}/out",
            "stable_id_used_to_derive_input": False,
            "reference_or_bbox_used_to_derive_input": False,
            "roofer_image": base["stage3"]["roofer_image"],
            "roofer_command_args": base["stage3"]["command_args"],
        })
    component_record = store.add("freeze/c3_condition_components_v1.jsonl", jsonl_bytes(component_records))
    jobs_record = store.add("freeze/c3_all_jobs_v1.jsonl", jsonl_bytes(jobs))
    cell_map_record = store.add(
        "freeze/c3_component_cell_map_v1.jsonl",
        jsonl_bytes([
            {"cell_ix": key[0], "cell_iy": key[1], "component_id": value}
            for key, value in sorted(component_map.items())
        ]),
    )
    body = {
        "schema": "jointbuildgs.c3_development_geometry_freeze.v1",
        "status": "FROZEN",
        "source_commit": source_commit,
        "run_id": run_id,
        "condition_id": CONDITION,
        "checkpoint_input": {
            "path": checkpoint_path.as_posix(),
            "bytes": int(expected["bytes"]),
            "sha256": expected["sha256"],
            "verification": expected["verification"],
            "full_hash_passes": 0,
            "deserialization_passes": 1,
        },
        "r4_attestation": attestation,
        "materialization": dict(evidence.lineage_stats),
        "surface_group_lineage": lineage,
        "condition_components": component_record,
        "component_cell_map": cell_map_record,
        "all_jobs": jobs_record,
        "component_count": len(component_records),
        "roofer_eligible_component_count": len(jobs),
        "reference_score_inputs_opened_before_freeze": 0,
        "c1_c2_reconstruction_or_roofer_invocations": 0,
        "G3": None,
        "G4": None,
        "PASS_usable": None,
        "scientific_verdict": None,
    }
    store.add_json("control/c3_geometry_frozen_v1.json", body)
    return body


def _associate(
    score_rows: Sequence[Mapping[str, Any]],
    component_map: Mapping[tuple[int, int], str],
) -> list[dict[str, Any]]:
    by_id: defaultdict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in score_rows:
        by_id[str(row["stable_id"])].append(row)
    mappings: list[dict[str, Any]] = []
    for stable_id in sorted(by_id):
        rows = by_id[stable_id]
        groups = {str(row["group_id"]) for row in rows}
        if len(groups) != 1:
            raise RuntimeError(f"development group is ambiguous for {stable_id}")
        counts: Counter[str] = Counter()
        for row in rows:
            component_id = component_map.get((int(row["cell_ix"]), int(row["cell_iy"])))
            if component_id:
                counts[component_id] += 1
        candidates = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
        component_id = candidates[0][0] if candidates else None
        overlap = counts.get(component_id, 0) if component_id else 0
        mappings.append({
            "building_id": stable_id,
            "group_id": next(iter(groups)),
            "split": "development",
            "method_id": CONDITION,
            "component_id": component_id,
            "operation_unit_id": f"{CONDITION}|{component_id}" if component_id else None,
            "reference_cell_count": len(rows),
            "component_overlap_reference_cells": overlap,
            "selected_component_overlap_fraction": overlap / len(rows),
            "overlapping_component_count": len(candidates),
            "component_candidates": [
                {
                    "component_id": name,
                    "overlap_reference_cells": count,
                    "overlap_fraction": count / len(rows),
                }
                for name, count in candidates
            ],
            "association_role": "SCORE_IDENTITY_ONLY_AFTER_FROZEN_C3_GEOMETRY",
        })
    return mappings


def associate_development(
    store: AddOnceStore,
    *,
    score_cells_path: Path,
    source_commit: str,
    run_id: str,
) -> dict[str, Any]:
    """Open the exact R3 score cells only after C3 geometry/jobs are frozen."""

    completed = store.path("control/c3_development_associated_v1.json")
    if completed.is_file():
        body = json.loads(completed.read_bytes())
        if body.get("status") != "ASSOCIATED" or body.get("source_commit") != source_commit or body.get("run_id") != run_id:
            raise RuntimeError("existing C3 association identity mismatch")
        return {**body, "fast_path": True, "score_input_reopens": 0, "new_writes": 0}
    frozen_path = store.path("control/c3_geometry_frozen_v1.json")
    if not frozen_path.is_file():
        raise RuntimeError("C3 geometry and all R_derived must be frozen before association")
    frozen = json.loads(frozen_path.read_bytes())
    if frozen.get("status") != "FROZEN" or frozen.get("source_commit") != source_commit or frozen.get("run_id") != run_id:
        raise RuntimeError("C3 geometry freeze identity mismatch")
    config = load_config()
    validate_contract(config)
    expected = config["inputs"]["r3_development_score_cells"]
    if score_cells_path.is_symlink() or not score_cells_path.is_file():
        raise RuntimeError("R3 development score cells missing/non-regular")
    data = score_cells_path.read_bytes()
    observed = {"path": score_cells_path.as_posix(), "bytes": len(data), "sha256": sha256_bytes(data), "full_read_and_digest_passes": 1}
    if observed["bytes"] != int(expected["bytes"]) or observed["sha256"] != expected["sha256"]:
        raise RuntimeError("R3 development score-cell identity mismatch")
    score_rows = parse_jsonl(data)
    if len(score_rows) != int(config["scope"]["reference_cell_rows"]):
        raise RuntimeError("R3 development score-cell row count mismatch")

    component_map_rows = parse_jsonl(store.read_verified(frozen["component_cell_map"]))
    component_map = {
        (int(row["cell_ix"]), int(row["cell_iy"])): str(row["component_id"])
        for row in component_map_rows
    }
    mappings = _associate(score_rows, component_map)
    roster = read_csv(REPO / "configs/p2_baselines/c1_c2_feasibility_pilot_v1/development_roster_v1.csv")
    expected_groups = {row["stable_id"]: row["group_id"] for row in roster}
    observed_groups = {row["building_id"]: row["group_id"] for row in mappings}
    if observed_groups != expected_groups or len(mappings) != int(config["scope"]["building_count"]):
        raise RuntimeError("association differs from frozen development roster")

    all_jobs = parse_jsonl(store.read_verified(frozen["all_jobs"]))
    jobs_by_unit = {str(row["operation_unit_id"]): row for row in all_jobs}
    required_ids = sorted({str(row["operation_unit_id"]) for row in mappings if row["operation_unit_id"]})
    missing_jobs = [value for value in required_ids if value not in jobs_by_unit]
    if missing_jobs:
        raise RuntimeError("associated component has no frozen Roofer job")
    execution_units = [jobs_by_unit[value] for value in required_ids]

    per_component: defaultdict[str, list[str]] = defaultdict(list)
    unassociated: list[str] = []
    for row in mappings:
        if row["component_id"]:
            per_component[str(row["component_id"])].append(str(row["building_id"]))
        else:
            unassociated.append(str(row["building_id"]))
    selected_usage = Counter(
        str(row["component_id"]) for row in mappings if row["component_id"]
    )
    for row in mappings:
        component_id = row["component_id"]
        shared = bool(component_id and selected_usage[str(component_id)] > 1)
        fragmented = int(row["overlapping_component_count"]) > 1
        if component_id is None:
            association_class = "UNASSOCIATED"
        elif shared and fragmented:
            association_class = "SHARED_AND_MULTI_COMPONENT"
        elif shared:
            association_class = "SHARED_COMPONENT"
        elif fragmented:
            association_class = "MULTI_COMPONENT"
        else:
            association_class = "UNIQUE_COMPONENT_SINGLE_CANDIDATE"
        row["selected_component_building_multiplicity"] = (
            selected_usage[str(component_id)] if component_id else 0
        )
        row["association_class"] = association_class
        row["building_level_gate_eligible"] = (
            association_class == "UNIQUE_COMPONENT_SINGLE_CANDIDATE"
        )
    multiplicity = {
        "schema": "jointbuildgs.c3_development_component_multiplicity.v1",
        "development_building_count": len(mappings),
        "associated_building_count": len(mappings) - len(unassociated),
        "unassociated_building_count": len(unassociated),
        "unassociated_building_ids": sorted(unassociated),
        "unique_associated_component_count": len(per_component),
        "buildings_per_component": {key: sorted(value) for key, value in sorted(per_component.items())},
        "building_count_per_component": {key: len(value) for key, value in sorted(per_component.items())},
        "max_buildings_sharing_one_component": max((len(value) for value in per_component.values()), default=0),
        "shared_component_building_excess": sum(max(0, len(value) - 1) for value in per_component.values()),
        "multi_component_building_count": sum(
            int(row["overlapping_component_count"]) > 1 for row in mappings
        ),
        "association_class_counts": dict(sorted(Counter(
            str(row["association_class"]) for row in mappings
        ).items())),
        "building_candidate_components": {
            str(row["building_id"]): row["component_candidates"] for row in mappings
        },
        "interpretation": "TECHNICAL_ASSOCIATION_MULTIPLICITY_NOT_INDEPENDENT_BUILDING_SUCCESS",
        "scientific_verdict": None,
    }
    mapping_record = store.add("freeze/c3_development_association_v1.jsonl", jsonl_bytes(mappings))
    multiplicity_record = store.add_json("diagnostics/c3_component_multiplicity_v1.json", multiplicity)
    execution_record = store.add("freeze/c3_execution_units_v1.jsonl", jsonl_bytes(execution_units))
    tsv = "operation_unit_id\twork_directory\n" + "".join(
        f"{row['operation_unit_id']}\t{row['work_directory']}\n" for row in execution_units
    )
    execution_tsv_record = store.add("freeze/c3_execution_units_v1.tsv", tsv.encode("utf-8"))
    body = {
        "schema": "jointbuildgs.c3_development_association.v1",
        "status": "ASSOCIATED",
        "source_commit": source_commit,
        "run_id": run_id,
        "score_input": observed,
        "geometry_frozen_before_score_open": True,
        "development_association": mapping_record,
        "component_multiplicity": multiplicity_record,
        "execution_units": execution_record,
        "execution_units_tsv": execution_tsv_record,
        "unique_roofer_operations": len(execution_units),
        "duplicate_roofer_calculations_prevented": (len(mappings) - len(unassociated)) - len(execution_units),
        "C1_C2_reruns": 0,
        "validation_payload_accesses": 0,
        "held_out_payload_accesses": 0,
        "G3": None,
        "G4": None,
        "PASS_usable": None,
        "scientific_verdict": None,
    }
    store.add_json("control/c3_development_associated_v1.json", body)
    return body


def _load_execution_unit(store: AddOnceStore, unit_id: str) -> dict[str, Any]:
    associated_path = store.path("control/c3_development_associated_v1.json")
    if not associated_path.is_file():
        raise RuntimeError("development association must complete before Roofer")
    associated = json.loads(associated_path.read_bytes())
    units = parse_jsonl(store.read_verified(associated["execution_units"]))
    matches = [row for row in units if row["operation_unit_id"] == unit_id]
    if len(matches) != 1:
        raise RuntimeError("Roofer operation unit is missing or ambiguous")
    return matches[0]


def _terminal_relative(unit: Mapping[str, Any]) -> str:
    return f"{unit['work_directory']}/roofer_terminal_v1.json"


def verify_roofer_terminal(store: AddOnceStore, *, unit_id: str) -> dict[str, Any]:
    """Verify one immutable terminal receipt and every file it binds."""

    unit = _load_execution_unit(store, unit_id)
    receipt_path = store.path(_terminal_relative(unit))
    if not receipt_path.is_file() or receipt_path.is_symlink():
        raise RuntimeError("Roofer terminal receipt missing/non-regular")
    body = json.loads(receipt_path.read_bytes())
    if body.get("operation_unit_id") != unit_id or body.get("status") not in {
        "COMPLETED", "FAILED"
    }:
        raise RuntimeError("Roofer terminal receipt identity/status mismatch")
    store.read_verified(body["input"])
    store.read_verified(body["r_derived"])
    store.read_verified(body["runtime_log"])
    for record in body.get("output_records", []):
        store.read_verified(record)
    return body


def record_roofer_terminal(
    store: AddOnceStore,
    *,
    unit_id: str,
    exit_code: int,
    runtime_seconds: int,
) -> dict[str, Any]:
    """Add one terminal Roofer receipt; process failure is a technical result."""

    if exit_code < 0 or runtime_seconds < 0:
        raise RuntimeError("Roofer exit/runtime values are invalid")
    unit = _load_execution_unit(store, unit_id)
    terminal_path = store.path(_terminal_relative(unit))
    if terminal_path.exists():
        return {**verify_roofer_terminal(store, unit_id=unit_id), "fast_path": True}
    work = store.path(str(unit["work_directory"]))
    runtime_path = work / "runtime.log"
    if runtime_path.is_symlink() or not runtime_path.is_file():
        raise RuntimeError("Roofer runtime log missing/non-regular")
    output_dir = store.path(str(unit["output_directory"]))
    output_records = [
        compact_file_record(store, path)
        for path in sorted(output_dir.rglob("*"))
        if path.is_file() and not path.is_symlink()
    ] if output_dir.is_dir() and not output_dir.is_symlink() else []
    body = {
        "schema": "jointbuildgs.c3_roofer_terminal.v1",
        "status": "COMPLETED" if exit_code == 0 else "FAILED",
        "operation_unit_id": unit_id,
        "exit_code": exit_code,
        "runtime_seconds": runtime_seconds,
        "input": unit["input"],
        "r_derived": unit["r_derived"],
        "runtime_log": compact_file_record(store, runtime_path),
        "output_records": output_records,
        "output_file_count": len(output_records),
        "scientific_verdict": None,
    }
    store.add_json(_terminal_relative(unit), body)
    return body


def _csv_bytes(fieldnames: Sequence[str], rows: Sequence[Mapping[str, Any]]) -> bytes:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=fieldnames, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode("utf-8")


def finalize_technical(
    store: AddOnceStore,
    *,
    source_commit: str,
    run_id: str,
) -> dict[str, Any]:
    """Collect per-unit G0/G1 screens into 51 technical rows; keep G2+ null."""

    completed = store.path("control/c3_development_technical_finalized_v1.json")
    if completed.is_file():
        body = json.loads(completed.read_bytes())
        if body.get("status") != "TECHNICAL_RESULTS_FINALIZED" or body.get("source_commit") != source_commit or body.get("run_id") != run_id:
            raise RuntimeError("existing C3 technical finalization identity mismatch")
        return {**body, "fast_path": True, "output_reopens": 0, "new_writes": 0}
    associated_path = store.path("control/c3_development_associated_v1.json")
    if not associated_path.is_file():
        raise RuntimeError("development association must complete before finalization")
    associated = json.loads(associated_path.read_bytes())
    if associated.get("status") != "ASSOCIATED" or associated.get("source_commit") != source_commit or associated.get("run_id") != run_id:
        raise RuntimeError("C3 association identity mismatch")
    mappings = parse_jsonl(store.read_verified(associated["development_association"]))
    units = parse_jsonl(store.read_verified(associated["execution_units"]))
    unit_results: dict[str, dict[str, Any]] = {}
    for unit in units:
        unit_id = str(unit["operation_unit_id"])
        terminal = verify_roofer_terminal(store, unit_id=unit_id)
        output_dir = store.path(str(unit["output_directory"]))
        if output_dir.is_symlink():
            raise RuntimeError(f"Roofer output directory is a symlink: {unit_id}")
        screen = provisional_output_check(output_dir) if terminal["exit_code"] == 0 and output_dir.is_dir() else {
            "records": 0,
            "city_object_count": 0,
            "lod22_geometry_count": 0,
            "semantic_surface_counts": {},
            "G0_generated": False,
            "G1_schema_semantic": False,
            "G1_check_class": "INTERNAL_CITYJSON_BOUNDARY_SEMANTICS_PARENT_CHILD_VALIDATION",
            "G1_failure_reasons": [f"ROOFER_TERMINAL_EXIT_{terminal['exit_code']}"],
            "geometry_ring_diagnostic": False,
            "geometry_ring_diagnostic_class": "DIAGNOSTIC_RING_INDEX_SANITY_NOT_G2_NOT_VAL3DITY",
            "G2_geometry_topology_valid": None,
            "G2_null_reason": "CANONICAL_VALIDATOR_NOT_EXECUTED_IN_MINIMAL_RUNNER",
        }
        # The internal screen is explicitly not promoted to canonical G2.
        screen["G2_geometry_topology_valid"] = None
        screen["G2_null_reason"] = "PINNED_GENERIC_C3_VAL3DITY_RUNNER_NOT_YET_FROZEN"
        unit_results[unit_id] = {**screen, "roofer_terminal_status": terminal["status"], "roofer_exit_code": terminal["exit_code"]}
    unit_record = store.add(
        "results/c3_operation_technical_checks_v1.jsonl",
        jsonl_bytes([
            {"operation_unit_id": unit_id, **unit_results[unit_id], "scientific_verdict": None}
            for unit_id in sorted(unit_results)
        ]),
    )
    rows: list[dict[str, Any]] = []
    for mapping in mappings:
        unit_id = mapping["operation_unit_id"]
        screen = unit_results.get(str(unit_id)) if unit_id else None
        component_g0 = bool(screen and screen["G0_generated"])
        component_g1 = bool(screen and screen["G1_schema_semantic"])
        building_eligible = bool(mapping["building_level_gate_eligible"])
        rows.append({
            **mapping,
            "component_G0_generated": component_g0,
            "component_G1_schema_semantic": component_g1,
            "G0_generated": component_g0 if building_eligible else None,
            "G0_null_reason": None if building_eligible else "COMPONENT_NOT_ONE_TO_ONE_WITH_BUILDING",
            "G1_schema_semantic": component_g1 if building_eligible else None,
            "G1_null_reason": None if building_eligible else "COMPONENT_NOT_ONE_TO_ONE_WITH_BUILDING",
            "G2_geometry_topology_valid": None,
            "G2_null_reason": (
                "PINNED_GENERIC_C3_VAL3DITY_RUNNER_NOT_YET_FROZEN"
                if building_eligible and component_g0 and component_g1
                else "UPSTREAM_OR_BUILDING_ASSOCIATION_NOT_ELIGIBLE"
            ),
            "geometry_ring_diagnostic": screen.get("geometry_ring_diagnostic") if screen else None,
            "G3_roof_structure_acceptable": None,
            "G4_geometric_accuracy_acceptable": None,
            "PASS_usable": None,
            "result_class": "DEVELOPMENT_TECHNICAL_DIAGNOSTIC_ONLY",
            "scientific_verdict": None,
        })
    if len(rows) != 51:
        raise RuntimeError("technical result table must contain exact development 51")
    result_record = store.add("results/development_technical_results_v1.jsonl", jsonl_bytes(rows))
    stage_rows = [
        {"condition_id": CONDITION, "stage": "ASSOCIATED", "status": "COMPLETE", "numerator": sum(row["component_id"] is not None for row in rows), "denominator": 51, "meaning": "score IDs linked to frozen outcome-free components; not a success count"},
        {"condition_id": CONDITION, "stage": "ONE_TO_ONE_BUILDING_COMPONENT", "status": "COMPLETE", "numerator": sum(row["building_level_gate_eligible"] for row in rows), "denominator": 51, "meaning": "building has one candidate component and that component is selected by one building"},
        {"condition_id": CONDITION, "stage": "COMPONENT_G0_GENERATED", "status": "COMPLETE", "numerator": sum(value["G0_generated"] for value in unit_results.values()), "denominator": len(units), "meaning": "unique Roofer operation units with LoD2.2 roof/wall/ground; component-level only"},
        {"condition_id": CONDITION, "stage": "COMPONENT_G1_SCHEMA_SEMANTIC", "status": "COMPLETE", "numerator": sum(value["G1_schema_semantic"] for value in unit_results.values()), "denominator": len(units), "meaning": "unique operation units passing internal CityJSON screen; component-level only"},
        {"condition_id": CONDITION, "stage": "BUILDING_G0_GENERATED", "status": "PARTIAL_DIAGNOSTIC", "numerator": sum(row["G0_generated"] is True for row in rows), "denominator": sum(row["building_level_gate_eligible"] for row in rows), "meaning": "only one-to-one building-component rows; shared/fragmented rows are null"},
        {"condition_id": CONDITION, "stage": "BUILDING_G1_SCHEMA_SEMANTIC", "status": "PARTIAL_DIAGNOSTIC", "numerator": sum(row["G1_schema_semantic"] is True for row in rows), "denominator": sum(row["building_level_gate_eligible"] for row in rows), "meaning": "only one-to-one building-component rows; shared/fragmented rows are null"},
        {"condition_id": CONDITION, "stage": "G2_GEOMETRY_TOPOLOGY_VALID", "status": "PENDING", "numerator": "", "denominator": 51, "meaning": "generic pinned C3 val3dity runner not frozen"},
        {"condition_id": CONDITION, "stage": "G3_ROOF_STRUCTURE_ACCEPTABLE", "status": "PENDING", "numerator": "", "denominator": 51, "meaning": "criterion not frozen"},
        {"condition_id": CONDITION, "stage": "G4_GEOMETRIC_ACCURACY_ACCEPTABLE", "status": "PENDING", "numerator": "", "denominator": 51, "meaning": "criterion not frozen"},
        {"condition_id": CONDITION, "stage": "PASS_USABLE", "status": "PENDING", "numerator": "", "denominator": 51, "meaning": "G2-G4 not frozen/completed"},
    ]
    stage_record = store.add(
        "results/stage_counts_v1.csv",
        _csv_bytes(("condition_id", "stage", "status", "numerator", "denominator", "meaning"), stage_rows),
    )
    body = {
        "schema": "jointbuildgs.c3_development_technical_finalized.v1",
        "status": "TECHNICAL_RESULTS_FINALIZED",
        "source_commit": source_commit,
        "run_id": run_id,
        "operation_checks": unit_record,
        "development_technical_results": result_record,
        "stage_counts": stage_record,
        "result_rows": 51,
        "unique_roofer_operations": len(units),
        "building_level_gate_evaluable_count": sum(row["building_level_gate_eligible"] for row in rows),
        "building_G0_true_count": sum(row["G0_generated"] is True for row in rows),
        "building_G1_true_count": sum(row["G1_schema_semantic"] is True for row in rows),
        "component_G0_true_count": sum(value["G0_generated"] for value in unit_results.values()),
        "component_G1_true_count": sum(value["G1_schema_semantic"] for value in unit_results.values()),
        "G2": None,
        "G3": None,
        "G4": None,
        "PASS_usable": None,
        "qualitative_fixed_view_status": "NOT_IN_THIS_MINIMAL_TECHNICAL_RUNNER",
        "scientific_verdict": None,
    }
    store.add_json("control/c3_development_technical_finalized_v1.json", body)
    return body


__all__ = [
    "AddOnceStore",
    "associate_development",
    "finalize_technical",
    "load_config",
    "prepare_geometry",
    "record_roofer_terminal",
    "validate_contract",
    "verify_roofer_terminal",
]
