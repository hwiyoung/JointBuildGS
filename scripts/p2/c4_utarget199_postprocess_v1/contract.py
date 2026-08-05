"""Add-once C4 checkpoint read-out, reference-separated metrics, and receipts.

The C4 geometry and native Gaussian exports are frozen before stable building
identity, current UAS evaluation cells, or 2022 LoD2 evaluation geometry are
opened.  C4 uses the same stored Stage-2 grouping and 1 m class-2/6 Roofer
read-out as sealed C3-2.  LoD2 is evaluation-only and its C4 comparison is
explicitly prior-related diagnostic evidence.
"""

from __future__ import annotations

from collections import Counter, defaultdict
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np
import torch

from scripts.p2.c3_development_stage3_v1.contract import load_reused_config
from scripts.p2.c3_utarget199_postprocess_v1.contract import (
    AddOnceStore,
    _city_file,
    _component_counts,
    _csv_bytes,
    _output_records,
    _point_rows,
    _roster,
    _sha256_file,
    gaussian_point_cloud_ply,
    gaussian_surfel_mesh_ply,
)
from scripts.p2.utarget199_presentation_v5.render import load_references
from scripts.p2_baselines.c1_c2_feasibility_pilot_v1.contract import (
    component_job,
    derive_components,
    jsonl_bytes,
    parse_jsonl,
    provisional_output_check,
    score_continuous,
)
from scripts.p2_baselines.c1_c2_feasibility_pilot_finalize_recovery_r4_v1.contract import (
    roof_triangles_from_cityjsonseq,
)
from src.stage3.c3_checkpoint_roofer_adapter_v1 import (
    load_c3_checkpoint,
    materialize_component_ready_evidence,
)


REPO = Path(__file__).resolve().parents[3]
CONFIG_PATH = REPO / "configs/p2/c4_utarget199_postprocess_v1/postprocess_v1.json"
CONDITION_ID = "C4_EXISTING_ALS"


def load_config(path: Path = CONFIG_PATH) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def canonical_json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def canonical_hash(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def validate_config(config: Mapping[str, Any] | None = None) -> dict[str, Any]:
    cfg = dict(config or load_config())
    if cfg.get("schema") != "jointbuildgs.p2.c4_utarget199_postprocess_config.v1":
        raise RuntimeError("unexpected C4 postprocess schema")
    if cfg.get("status") != "APPROVED_BY_DEC_P1_017":
        raise RuntimeError("C4 postprocess is not activated")
    condition = cfg.get("condition") or {}
    if condition.get("condition_id") != CONDITION_ID or condition.get("expected_iteration") != 30000:
        raise RuntimeError("C4 condition binding drifted")
    if not isinstance(condition.get("expected_bytes"), int) or condition["expected_bytes"] <= 0:
        raise RuntimeError("C4 checkpoint byte binding is incomplete")
    if len(str(condition.get("expected_sha256", ""))) != 64:
        raise RuntimeError("C4 checkpoint hash binding is incomplete")
    scope = cfg.get("scope") or {}
    if (
        scope.get("population") != "U_target"
        or scope.get("building_count") != 199
        or scope.get("expected_result_rows") != 199
        or scope.get("pre_execution_building_exclusion_allowed") is not False
        or scope.get("missing_not_run_failure_preserved") is not True
        or scope.get("c5_execution_allowed") is not False
    ):
        raise RuntimeError("C4 U_target scope drifted")
    if cfg.get("scientific_verdict", "invalid") is not None:
        raise RuntimeError("scientific_verdict must remain null")
    if cfg.get("official_G3_G4_PASS_usable", "invalid") is not None:
        raise RuntimeError("official PASS_usable must remain null")
    if cfg["roofer"].get("external_roofprint_allowed") is not False:
        raise RuntimeError("C4 Stage-3 must not accept an external roofprint")
    if cfg["presentation"].get("c5_state") != "NOT_RUN":
        raise RuntimeError("C5 must remain NOT_RUN")
    base = load_reused_config()
    if base["stage3"]["command_args"] != cfg["roofer"]["command_args"]:
        raise RuntimeError("common Roofer command drifted")
    return {
        "status": "PASS",
        "condition_id": CONDITION_ID,
        "building_count": 199,
        "result_rows": 199,
        "c5_executed": False,
        "scientific_verdict": None,
    }


def _record(path: Path, root: Path) -> dict[str, Any]:
    size, digest = _sha256_file(path)
    return {"path": path.relative_to(root).as_posix(), "bytes": size, "sha256": digest}


def _verify_exact(path: Path, size: int, digest: str, label: str) -> dict[str, Any]:
    actual_size, actual_digest = _sha256_file(path)
    if actual_size != size or actual_digest != digest:
        raise RuntimeError(f"{label} exact identity differs")
    return {"path": path.as_posix(), "bytes": actual_size, "sha256": actual_digest}


def prepare_condition(
    store: AddOnceStore,
    *,
    checkpoint_path: Path,
    source_commit: str,
    run_id: str,
) -> dict[str, Any]:
    relative = "control/C4_EXISTING_ALS_geometry_frozen_v1.json"
    completed = store.path(relative)
    if completed.is_file():
        body = json.loads(completed.read_text(encoding="utf-8"))
        if body.get("source_commit") != source_commit or body.get("run_id") != run_id:
            raise RuntimeError("existing C4 freeze identity differs")
        return {**body, "fast_path": True, "new_writes": 0}
    config = load_config()
    validate_config(config)
    spec = config["condition"]
    _verify_exact(checkpoint_path, int(spec["expected_bytes"]), spec["expected_sha256"], "C4 checkpoint")
    arrays = load_c3_checkpoint(checkpoint_path)
    if arrays.iteration != int(spec["expected_iteration"]):
        raise RuntimeError("C4 checkpoint iteration differs")
    payload = torch.load(checkpoint_path, map_location="cpu", weights_only=True)
    state = payload["state_dict"]
    required = {"means", "quats", "log_scales", "opacities_raw", "sh0", "sem_logits"}
    if not required.issubset(state):
        raise RuntimeError("C4 checkpoint lacks native export tensors")
    prefix = f"conditions/{CONDITION_ID}"
    cloud = store.add(
        f"{prefix}/intermediate/native_gaussian_centers_v1.ply",
        gaussian_point_cloud_ply(state, config["frame"]["local_shift_xyz"]),
    )
    mesh = store.add(
        f"{prefix}/intermediate/native_gaussian_surfel_mesh_v1.ply",
        gaussian_surfel_mesh_ply(state, config["frame"]["local_shift_xyz"]),
    )
    del payload, state
    evidence = materialize_component_ready_evidence(arrays)
    points = _point_rows(evidence)
    base = load_reused_config()
    components, component_map = derive_components(CONDITION_ID, points, base)
    if not components:
        raise RuntimeError("C4 checkpoint produced no Stage-3 components")
    lineage = store.add(
        f"{prefix}/freeze/surface_group_lineage_v1.jsonl",
        jsonl_bytes([group.__dict__ for group in evidence.groups]),
    )
    component_record = store.add(f"{prefix}/freeze/components_v1.jsonl", jsonl_bytes(components))
    cell_map = store.add(
        f"{prefix}/freeze/component_cell_map_v1.jsonl",
        jsonl_bytes([
            {"cell_ix": ix, "cell_iy": iy, "component_id": component_id}
            for (ix, iy), component_id in sorted(component_map.items())
        ]),
    )
    jobs: list[dict[str, Any]] = []
    for component in components:
        if component["pre_roofer_failure"]:
            continue
        input_bytes, derived_bytes = component_job(CONDITION_ID, component, points, base)
        work = f"{prefix}/operations/{component['component_id']}/work"
        jobs.append({
            "operation_unit_id": f"{CONDITION_ID}|{component['component_id']}",
            "condition_id": CONDITION_ID,
            "component_id": component["component_id"],
            "work_directory": work,
            "output_directory": f"{work}/out",
            "input": store.add(f"{work}/input.las", input_bytes),
            "r_derived": store.add(f"{work}/r_derived.geojson", derived_bytes),
            "stable_id_used_to_derive_input": False,
            "reference_or_bbox_used_to_derive_input": False,
        })
    jobs_record = store.add(f"{prefix}/freeze/all_jobs_v1.jsonl", jsonl_bytes(jobs))
    body = {
        "schema": "jointbuildgs.c4_utarget199_condition_geometry_freeze.v1",
        "status": "FROZEN_BEFORE_BUILDING_IDENTITY_OR_REFERENCE_ACCESS",
        "condition_id": CONDITION_ID,
        "source_commit": source_commit,
        "run_id": run_id,
        "checkpoint": {
            "path": checkpoint_path.as_posix(),
            "bytes": int(spec["expected_bytes"]),
            "sha256": spec["expected_sha256"],
            "iteration": arrays.iteration,
            "primitive_count": int(arrays.means.shape[0]),
            "full_hash_passes": 1,
        },
        "native_gaussian_point_cloud": cloud,
        "native_gaussian_surfel_mesh": mesh,
        "surface_group_lineage": lineage,
        "materialization": dict(evidence.lineage_stats),
        "components": component_record,
        "component_cell_map": cell_map,
        "all_jobs": jobs_record,
        "component_count": len(components),
        "roofer_eligible_component_count": len(jobs),
        "building_bbox_accesses": 0,
        "current_uas_reference_accesses": 0,
        "lod2_reference_accesses": 0,
        "external_roofprint_accesses": 0,
        "c5_executed": False,
        "scientific_verdict": None,
    }
    store.add_json(relative, body)
    return body


def associate_population(
    store: AddOnceStore,
    *,
    current_uas_reference_path: Path,
    source_commit: str,
    run_id: str,
) -> dict[str, Any]:
    completed = store.path("control/population_associated_v1.json")
    if completed.is_file():
        return {**json.loads(completed.read_text(encoding="utf-8")), "fast_path": True, "new_writes": 0}
    config = load_config()
    validate_config(config)
    frozen = json.loads(store.path("control/C4_EXISTING_ALS_geometry_frozen_v1.json").read_text(encoding="utf-8"))
    if frozen.get("source_commit") != source_commit or frozen.get("run_id") != run_id:
        raise RuntimeError("C4 geometry freeze identity differs")
    spec = config["inputs"]
    _verify_exact(
        current_uas_reference_path,
        int(spec["current_uas_reference_bytes"]),
        spec["current_uas_reference_sha256"],
        "current UAS reference",
    )
    reference_record = store.add("freeze/current_uas_reference_cells_v1.jsonl", current_uas_reference_path.read_bytes())
    roster = _roster(config)
    components = parse_jsonl(store.read_verified(frozen["components"]))
    jobs = {row["operation_unit_id"]: row for row in parse_jsonl(store.read_verified(frozen["all_jobs"]))}
    counts: dict[str, Counter[str]] = {row["stable_id"]: Counter() for row in roster}
    for component in components:
        for building_id, count in _component_counts(
            component,
            roster,
            config["frame"]["grid_origin_xy"],
            float(config["frame"]["grid_cell_m"]),
        ).items():
            counts[building_id][str(component["component_id"])] += count
    associations: list[dict[str, Any]] = []
    for building in roster:
        building_id = str(building["stable_id"])
        ranked = sorted(counts[building_id].items(), key=lambda value: (-value[1], value[0]))
        selected = ranked[0][0] if ranked else None
        associations.append({
            "building_id": building_id,
            "condition_id": CONDITION_ID,
            "bbox_min_x": building["bbox"][0],
            "bbox_min_y": building["bbox"][1],
            "bbox_max_x": building["bbox"][2],
            "bbox_max_y": building["bbox"][3],
            "original_split": building.get("candidate_split") or building.get("split") or "",
            "component_id": selected,
            "operation_unit_id": f"{CONDITION_ID}|{selected}" if selected else None,
            "component_cell_count_inside_bbox": ranked[0][1] if ranked else 0,
            "overlapping_component_count": len(ranked),
            "component_candidates": [
                {"component_id": name, "cell_count_inside_bbox": count} for name, count in ranked
            ],
            "association_role": "IDENTITY_DISPLAY_AND_EVALUATION_ONLY_AFTER_C4_GEOMETRY_FREEZE",
        })
    usage = Counter(row["operation_unit_id"] for row in associations if row["operation_unit_id"])
    for row in associations:
        multiplicity = usage.get(row["operation_unit_id"], 0)
        row["selected_component_building_multiplicity"] = multiplicity
        row["one_to_one_building_component"] = bool(
            row["operation_unit_id"] and row["overlapping_component_count"] == 1 and multiplicity == 1
        )
        if not row["operation_unit_id"]:
            row["association_status"] = "UNASSOCIATED"
        elif multiplicity > 1 and row["overlapping_component_count"] > 1:
            row["association_status"] = "SHARED_AND_MULTI_COMPONENT"
        elif multiplicity > 1:
            row["association_status"] = "SHARED_COMPONENT"
        elif row["overlapping_component_count"] > 1:
            row["association_status"] = "MULTI_COMPONENT"
        else:
            row["association_status"] = "ONE_TO_ONE"
    if len(associations) != 199:
        raise RuntimeError("C4 population association is not exact 199")
    selected_ids = sorted({str(row["operation_unit_id"]) for row in associations if row["operation_unit_id"]})
    missing = [unit_id for unit_id in selected_ids if unit_id not in jobs]
    if missing:
        raise RuntimeError("associated C4 Roofer units are missing")
    execution_units = [jobs[unit_id] for unit_id in selected_ids]
    association_record = store.add("freeze/population_association_v1.jsonl", jsonl_bytes(associations))
    units_record = store.add("freeze/execution_units_v1.jsonl", jsonl_bytes(execution_units))
    units_tsv = store.add(
        "freeze/execution_units_v1.tsv",
        ("operation_unit_id\twork_directory\n" + "".join(
            f"{row['operation_unit_id']}\t{row['work_directory']}\n" for row in execution_units
        )).encode("utf-8"),
    )
    body = {
        "schema": "jointbuildgs.c4_utarget199_population_association.v1",
        "status": "ASSOCIATED_AFTER_C4_GEOMETRY_FROZEN",
        "source_commit": source_commit,
        "run_id": run_id,
        "building_count": 199,
        "result_rows": 199,
        "current_uas_reference": reference_record,
        "population_association": association_record,
        "execution_units": units_record,
        "execution_units_tsv": units_tsv,
        "associated_building_count": sum(row["operation_unit_id"] is not None for row in associations),
        "unique_roofer_operations": len(execution_units),
        "c5_executed": False,
        "scientific_verdict": None,
    }
    store.add_json("control/population_associated_v1.json", body)
    return body


def _unit(store: AddOnceStore, unit_id: str) -> dict[str, Any]:
    associated = json.loads(store.path("control/population_associated_v1.json").read_text(encoding="utf-8"))
    matches = [
        row for row in parse_jsonl(store.read_verified(associated["execution_units"]))
        if row["operation_unit_id"] == unit_id
    ]
    if len(matches) != 1:
        raise RuntimeError("C4 Roofer unit is missing/ambiguous")
    return matches[0]


def record_terminal(
    store: AddOnceStore,
    *,
    unit_id: str,
    exit_code: int,
    runtime_seconds: int,
) -> dict[str, Any]:
    unit = _unit(store, unit_id)
    relative = f"{unit['work_directory']}/roofer_terminal_v1.json"
    if store.path(relative).is_file():
        return {**verify_terminal(store, unit_id), "fast_path": True}
    runtime = store.path(unit["work_directory"]) / "runtime.log"
    if not runtime.is_file() or runtime.is_symlink():
        raise RuntimeError("C4 Roofer runtime log missing/non-regular")
    body = {
        "schema": "jointbuildgs.c4_utarget199_roofer_terminal.v1",
        "status": "COMPLETED" if exit_code == 0 else "FAILED",
        "operation_unit_id": unit_id,
        "exit_code": exit_code,
        "runtime_seconds": runtime_seconds,
        "input": unit["input"],
        "r_derived": unit["r_derived"],
        "runtime_log": _record(runtime, store.root),
        "output_records": _output_records(store, store.path(unit["output_directory"])),
        "scientific_verdict": None,
    }
    store.add_json(relative, body)
    return body


def verify_terminal(store: AddOnceStore, unit_id: str) -> dict[str, Any]:
    unit = _unit(store, unit_id)
    path = store.path(f"{unit['work_directory']}/roofer_terminal_v1.json")
    body = json.loads(path.read_text(encoding="utf-8"))
    if body.get("operation_unit_id") != unit_id or body.get("status") not in {"COMPLETED", "FAILED"}:
        raise RuntimeError("C4 Roofer terminal identity/status differs")
    for key in ("input", "r_derived", "runtime_log"):
        store.read_verified(body[key])
    for record in body["output_records"]:
        store.read_verified(record)
    if _output_records(store, store.path(unit["output_directory"])) != body["output_records"]:
        raise RuntimeError("C4 Roofer output tree differs from terminal")
    return body


def _roof_triangles(reference: Any) -> list[np.ndarray]:
    triangles: list[np.ndarray] = []
    for ring in reference.roof_rings_xyz:
        vertices = np.asarray(ring[:-1] if np.allclose(ring[0], ring[-1]) else ring, dtype=np.float64)
        for index in range(1, len(vertices) - 1):
            triangle = np.vstack((vertices[0], vertices[index], vertices[index + 1]))
            if np.linalg.norm(np.cross(triangle[1] - triangle[0], triangle[2] - triangle[0])) > 1e-10:
                triangles.append(triangle)
    return triangles


def _triangle_z_normal(x: float, y: float, triangle: np.ndarray) -> tuple[float, np.ndarray] | None:
    xy = triangle[:, :2]
    matrix = np.asarray(
        [[xy[0, 0], xy[1, 0], xy[2, 0]], [xy[0, 1], xy[1, 1], xy[2, 1]], [1, 1, 1]],
        dtype=np.float64,
    )
    if abs(float(np.linalg.det(matrix))) < 1e-10:
        return None
    weights = np.linalg.solve(matrix, np.asarray([x, y, 1.0], dtype=np.float64))
    if float(weights.min()) < -1e-7 or float(weights.max()) > 1 + 1e-7:
        return None
    normal = np.cross(triangle[1] - triangle[0], triangle[2] - triangle[0])
    normal /= max(float(np.linalg.norm(normal)), 1e-12)
    return float(weights @ triangle[:, 2]), normal


def lod2_reference_rows(reference: Any, bbox: Sequence[float], config: Mapping[str, Any]) -> list[dict[str, Any]]:
    cell = float(config["references"]["lod2_grid_cell_m"])
    origin_x, origin_y = (float(value) for value in config["frame"]["grid_origin_xy"])
    min_x, min_y, max_x, max_y = (float(value) for value in bbox)
    ix0 = math.floor((min_x - origin_x) / cell)
    ix1 = math.ceil((max_x - origin_x) / cell)
    iy0 = math.floor((min_y - origin_y) / cell)
    iy1 = math.ceil((max_y - origin_y) / cell)
    triangles = _roof_triangles(reference)
    dz = float(config["frame"]["lod2_orthometric_to_current_ellipsoidal_m"])
    rows: list[dict[str, Any]] = []
    for ix in range(ix0, ix1):
        x = origin_x + (ix + 0.5) * cell
        if not min_x <= x <= max_x:
            continue
        for iy in range(iy0, iy1):
            y = origin_y + (iy + 0.5) * cell
            if not min_y <= y <= max_y:
                continue
            candidates = [value for triangle in triangles if (value := _triangle_z_normal(x, y, triangle)) is not None]
            if not candidates:
                continue
            z, normal = max(candidates, key=lambda value: value[0])
            rows.append({
                "cell_x": x,
                "cell_y": y,
                "top_z": z + dz,
                "normal_x": float(normal[0]),
                "normal_y": float(normal[1]),
                "normal_z": float(normal[2]),
            })
    return rows


def _raw_jsonl(path: Path) -> tuple[list[dict[str, Any]], list[bytes]]:
    lines = path.read_bytes().splitlines(keepends=True)
    return [json.loads(line) for line in lines], lines


def _metric_delta(c4: Mapping[str, Any], c3: Mapping[str, Any]) -> tuple[dict[str, float | None], dict[str, str]]:
    names = (
        "reference_vertical_coverage",
        "height_error_signed_mean_m",
        "height_error_signed_median_m",
        "height_error_mae_m",
        "RMSZ_m",
        "RMSXY_m",
        "surface_distance_rmse_m",
        "surface_distance_p95_m",
        "normal_angular_error_median_deg",
        "normal_angular_error_p95_deg",
    )
    delta: dict[str, float | None] = {}
    reasons: dict[str, str] = {}
    for name in names:
        current, control = c4.get(name), c3.get(name)
        if current is None or control is None:
            delta[name] = None
            reasons[name] = "C4_OR_MATCHED_C3_2_METRIC_NULL"
        else:
            delta[name] = float(current) - float(control)
    return delta, reasons


def finalize(
    store: AddOnceStore,
    *,
    artifact_root: Path,
    source_commit: str,
    run_id: str,
) -> dict[str, Any]:
    completed = store.path("control/finalized_v1.json")
    if completed.is_file():
        return {**json.loads(completed.read_text(encoding="utf-8")), "fast_path": True, "new_writes": 0}
    config = load_config()
    associated = json.loads(store.path("control/population_associated_v1.json").read_text(encoding="utf-8"))
    if associated.get("source_commit") != source_commit or associated.get("run_id") != run_id:
        raise RuntimeError("C4 finalization identity differs")
    associations = parse_jsonl(store.read_verified(associated["population_association"]))
    current_refs = parse_jsonl(store.read_verified(associated["current_uas_reference"]))
    current_by_building: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in current_refs:
        current_by_building[str(row["stable_id"])].append(row)
    units = {row["operation_unit_id"]: row for row in parse_jsonl(store.read_verified(associated["execution_units"]))}
    component_results: dict[str, dict[str, Any]] = {}
    for unit_id, unit in units.items():
        terminal = verify_terminal(store, unit_id)
        output = store.path(unit["output_directory"])
        city = _city_file(output)
        screen = provisional_output_check(output) if terminal["exit_code"] == 0 and city else None
        triangles: list[np.ndarray] = []
        if city and screen and screen["G0_generated"] and screen["G1_schema_semantic"]:
            triangles = roof_triangles_from_cityjsonseq(city.name, city.read_bytes())
        component_results[unit_id] = {
            "terminal": terminal,
            "screen": screen,
            "triangles": triangles,
            "city_path": city.relative_to(store.root).as_posix() if city else None,
            "city_record": _record(city, store.root) if city else None,
        }
    inputs = config["inputs"]
    temporal_path = artifact_root / inputs["temporal_diagnostic_relative_path"]
    _verify_exact(temporal_path, inputs["temporal_diagnostic_bytes"], inputs["temporal_diagnostic_sha256"], "LoD2 temporal diagnostic")
    temporal_rows, _ = _raw_jsonl(temporal_path)
    temporal = {row["building_id"]: row for row in temporal_rows}
    allowed_status = set(config["references"]["lod2_status_values"])
    if len(temporal) != 199 or {row["status"] for row in temporal.values()} - allowed_status:
        raise RuntimeError("LoD2 temporal diagnostic scope/status differs")
    lod2_paths = [artifact_root / relative for relative in inputs["lod2_relative_paths"]]
    lod2_records = [
        _verify_exact(path, path.stat().st_size, digest, "2022 LoD2")
        for path, digest in zip(lod2_paths, inputs["lod2_sha256"])
    ]
    building_ids = [row["building_id"] for row in associations]
    lod2 = load_references(lod2_paths, building_ids)
    rows: list[dict[str, Any]] = []
    binding_support: list[dict[str, Any]] = []
    for association in associations:
        building_id = str(association["building_id"])
        unit_id = association.get("operation_unit_id")
        component = component_results.get(str(unit_id)) if unit_id else None
        screen = component["screen"] if component else None
        component_g0 = bool(screen and screen["G0_generated"])
        component_g1 = bool(screen and screen["G1_schema_semantic"])
        one_to_one = bool(association["one_to_one_building_component"])
        triangles = component["triangles"] if component else []
        current_reference = current_by_building[building_id]
        bbox = [association[name] for name in ("bbox_min_x", "bbox_min_y", "bbox_max_x", "bbox_max_y")]
        lod2_reference = lod2_reference_rows(lod2[building_id], bbox, config)
        row = {
            **{key: value for key, value in association.items() if key != "component_candidates"},
            "run_id": run_id,
            "source_commit": source_commit,
            "method_id": "C4_GS_lidar_prior",
            "matched_control_condition_id": "C3_2_SEM_DEPTH",
            "current_uas_reference_role": config["references"]["current_uas_role"],
            "lod2_reference_role": config["references"]["c4_vs_lod2_role"],
            "lod2_reference_status": temporal[building_id]["status"],
            "component_G0_generated": component_g0,
            "component_G1_schema_semantic": component_g1,
            "G0_generated": bool(one_to_one and component_g0),
            "G1_schema_semantic": bool(one_to_one and component_g0 and component_g1),
            "G2_geometry_topology_valid": None,
            "G3_roof_structure_acceptable": None,
            "G4_geometric_accuracy_acceptable": None,
            "PASS_usable": None,
            "current_uas_metrics": score_continuous(current_reference, triangles),
            "lod2_2022_metrics": score_continuous(lod2_reference, triangles),
            "cityjson_path": component["city_path"] if component else None,
            "failure_or_missing_reason": None if component and component["city_path"] else (
                "UNASSOCIATED" if not unit_id else "NO_SINGLE_ROOFER_CITYJSON_OUTPUT"
            ),
            "official_PASS_usable": None,
            "scientific_verdict": None,
        }
        rows.append(row)
        binding_support.append({
            "building_id": building_id,
            "operation_unit_id": unit_id,
            "output": component["city_record"] if component else None,
            "current_uas_support_sha256": canonical_hash(current_reference),
            "lod2_support_sha256": canonical_hash(lod2_reference),
            "support_binding_sha256": canonical_hash({
                "bbox": bbox,
                "component_cell_count_inside_bbox": association["component_cell_count_inside_bbox"],
                "current_uas_reference_cell_count": len(current_reference),
                "lod2_reference_cell_count": len(lod2_reference),
            }),
        })
    if len(rows) != 199 or len({row["building_id"] for row in rows}) != 199:
        raise RuntimeError("C4 result matrix is not exact 199")
    result_bytes = jsonl_bytes(rows)
    results = store.add("results/building_c4_metrics_v1.jsonl", result_bytes)
    raw_c4 = result_bytes.splitlines(keepends=True)
    config_record = _record(CONFIG_PATH, REPO)
    bindings = []
    for row, support, raw in zip(rows, binding_support, raw_c4):
        bindings.append({
            "building_id": row["building_id"],
            "method_id": row["method_id"],
            "metric_row_sha256": hashlib.sha256(raw.rstrip(b"\r\n")).hexdigest(),
            "metric_source_sha256": results["sha256"],
            "output_sha256": support["output"]["sha256"] if support["output"] else None,
            "output_null_reason": row["failure_or_missing_reason"],
            "checkpoint_sha256": config["condition"]["expected_sha256"],
            "current_uas_reference_sha256": inputs["current_uas_reference_sha256"],
            "current_uas_building_support_sha256": support["current_uas_support_sha256"],
            "lod2_reference_sha256": canonical_hash(lod2_records),
            "lod2_building_support_sha256": support["lod2_support_sha256"],
            "support_binding_sha256": support["support_binding_sha256"],
            "evaluator_config_sha256": config_record["sha256"],
            "lod2_reference_status": row["lod2_reference_status"],
            "c4_vs_lod2_role": config["references"]["c4_vs_lod2_role"],
            "official_PASS_usable": None,
            "scientific_verdict": None,
        })
    binding_record = store.add("results/metric_binding_v1.jsonl", jsonl_bytes(bindings))
    c3 = config["matched_c3_2"]
    c3_checkpoint = artifact_root / c3["checkpoint_relative_path"]
    c3_checkpoint_record = _verify_exact(
        c3_checkpoint,
        int(c3["checkpoint_bytes"]),
        c3["checkpoint_sha256"],
        "matched C3-2 checkpoint",
    )
    c3_path = artifact_root / c3["postprocess_relative_root"] / c3["metric_relative_path"]
    _verify_exact(c3_path, c3["metric_bytes"], c3["metric_sha256"], "matched C3-2 metrics")
    c3_rows, c3_lines = _raw_jsonl(c3_path)
    c3_pairs = {
        row["building_id"]: (row, raw)
        for row, raw in zip(c3_rows, c3_lines)
        if row.get("condition_id") == "C3_2_SEM_DEPTH"
    }
    if len(c3_pairs) != 199:
        raise RuntimeError("matched C3-2 metric population differs")
    deltas = []
    for c4_row, c4_raw in zip(rows, raw_c4):
        c3_row, c3_raw = c3_pairs[c4_row["building_id"]]
        delta, reasons = _metric_delta(c4_row["current_uas_metrics"], c3_row["continuous_metrics"])
        deltas.append({
            "building_id": c4_row["building_id"],
            "comparison": "C4_EXISTING_ALS_MINUS_MATCHED_C3_2_SEM_DEPTH",
            "current_uas_metric_delta": delta,
            "null_reasons": reasons,
            "c3_2_metric_row_sha256": hashlib.sha256(c3_raw.rstrip(b"\r\n")).hexdigest(),
            "c4_metric_row_sha256": hashlib.sha256(c4_raw.rstrip(b"\r\n")).hexdigest(),
            "c3_2_checkpoint_sha256": c3["checkpoint_sha256"],
            "c4_checkpoint_sha256": config["condition"]["expected_sha256"],
            "same_seed_init_iteration_contract": True,
            "official_PASS_usable": None,
            "scientific_verdict": None,
        })
    delta_record = store.add("results/c4_minus_matched_c3_2_v1.jsonl", jsonl_bytes(deltas))
    summary_row = {
        "condition_id": CONDITION_ID,
        "U_target": 199,
        "associated": sum(row["operation_unit_id"] is not None for row in rows),
        "one_to_one": sum(row["one_to_one_building_component"] for row in rows),
        "current_uas_scorable": sum(row["current_uas_metrics"]["reference_cell_count"] > 0 for row in rows),
        "lod2_scorable": sum(row["lod2_2022_metrics"]["reference_cell_count"] > 0 for row in rows),
        "building_G0": sum(row["G0_generated"] for row in rows),
        "building_G1": sum(row["G1_schema_semantic"] for row in rows),
        "G2": "null",
        "G3": "null",
        "G4": "null",
        "PASS_usable": "null",
        "scientific_verdict": "null",
    }
    summary = store.add("results/method_summary_v1.csv", _csv_bytes([summary_row], list(summary_row)))
    body = {
        "schema": "jointbuildgs.c4_utarget199_postprocess_finalized.v1",
        "status": "TECHNICAL_RESULTS_COMPLETE_QUALITATIVE_PENDING",
        "task_id": config["task_id"],
        "source_commit": source_commit,
        "run_id": run_id,
        "building_count": 199,
        "result_rows": 199,
        "building_c4_metrics": results,
        "metric_binding": binding_record,
        "matched_delta": delta_record,
        "method_summary": summary,
        "summary": summary_row,
        "lod2_sources": lod2_records,
        "matched_c3_2_checkpoint": c3_checkpoint_record,
        "temporal_source": {"bytes": inputs["temporal_diagnostic_bytes"], "sha256": inputs["temporal_diagnostic_sha256"]},
        "execution_accounting": {
            "C4_roofer_unique_operations": len(units),
            "C4_metric_rows": 199,
            "C3_retraining": 0,
            "C3_roofer_reruns": 0,
            "C5_executed": 0,
            "G2_invocations": 0,
        },
        "official_G3_G4_PASS_usable": None,
        "scientific_verdict": None,
    }
    store.add_json("control/finalized_v1.json", body)
    return body


def complete_task(store: AddOnceStore) -> dict[str, Any]:
    completed = store.path("control/completed_v1.json")
    if completed.is_file():
        return {**json.loads(completed.read_text(encoding="utf-8")), "fast_path": True}
    config = load_config()
    final = json.loads(store.path("control/finalized_v1.json").read_text(encoding="utf-8"))
    qualitative = json.loads(store.path("control/qualitative_complete_v1.json").read_text(encoding="utf-8"))
    rendered = json.loads(store.path("control/gs_render_complete_v1.json").read_text(encoding="utf-8"))
    if final.get("result_rows") != 199 or qualitative.get("case_sheet_count") != 199:
        raise RuntimeError("C4 final result/case count differs")
    if rendered.get("render_panel_count") != 4:
        raise RuntimeError("C4 GS render count differs")
    if qualitative.get("full_resolution_page_count") != 199 or qualitative.get("representative_pdf_page_count") != 3:
        raise RuntimeError("C4 integrated presentation count differs")
    files = [path for path in store.root.rglob("*") if path.is_file() and not path.is_symlink()]
    total = sum(path.stat().st_size for path in files)
    if total > int(config["caps"]["output_bytes"]):
        raise RuntimeError("C4 postprocess output cap exceeded")
    body = {
        "schema": "jointbuildgs.c4_utarget199_postprocess_completed.v1",
        "status": "TECHNICAL_POSTPROCESS_COMPLETE",
        "task_id": config["task_id"],
        "building_count": 199,
        "result_rows": 199,
        "case_sheet_count": 199,
        "full_resolution_page_count": 199,
        "actual_gs_render_panels": 4,
        "native_gaussian_point_clouds": 1,
        "native_gaussian_surfel_meshes": 1,
        "file_count_before_completion": len(files),
        "bytes_before_completion": total,
        "c5_executed": False,
        "official_G3_G4_PASS_usable": None,
        "scientific_verdict": None,
    }
    completion_record = store.add_json("control/completed_v1.json", body)
    manifest_rows = []
    for path in sorted(store.root.rglob("*")):
        if not path.is_file() or path.is_symlink():
            continue
        relative = path.relative_to(store.root).as_posix()
        if relative in {"control/artifact_manifest_v1.json", "control/300-closed.local_v1.json"}:
            continue
        manifest_rows.append(_record(path, store.root))
    artifact_manifest = store.add_json(
        "control/artifact_manifest_v1.json",
        {
            "schema": "jointbuildgs.c4_utarget199_artifact_manifest.v1",
            "status": "SEALED_LOCAL_ARTIFACT_TREE",
            "task_id": config["task_id"],
            "source_commit": final["source_commit"],
            "run_id": final["run_id"],
            "record_count": len(manifest_rows),
            "records": manifest_rows,
            "c5_executed": False,
            "official_G3_G4_PASS_usable": None,
            "scientific_verdict": None,
        },
    )
    closed = {
        "schema": "jointbuildgs.c4_utarget199_postprocess_closed.local.v1",
        "status": "TECHNICAL_POSTPROCESS_CLOSED",
        "task_id": config["task_id"],
        "source_commit": final["source_commit"],
        "run_id": final["run_id"],
        "completion": completion_record,
        "artifact_manifest": artifact_manifest,
        "building_count": 199,
        "result_rows": 199,
        "case_sheet_count": 199,
        "full_resolution_page_count": 199,
        "c5_executed": False,
        "official_G3_G4_PASS_usable": None,
        "scientific_verdict": None,
    }
    store.add_json("control/300-closed.local_v1.json", closed)
    return closed


def record_failure(
    store: AddOnceStore,
    *,
    stage: str,
    exit_code: int,
    source_commit: str,
    run_id: str,
) -> dict[str, Any]:
    relative = "control/100-c4-postprocess-failed.local_v1.json"
    if store.path(relative).is_file():
        body = json.loads(store.path(relative).read_text(encoding="utf-8"))
        if body.get("source_commit") != source_commit or body.get("run_id") != run_id:
            raise RuntimeError("existing C4 postprocess failure identity differs")
        return {**body, "fast_path": True}
    body = {
        "schema": "jointbuildgs.c4_utarget199_postprocess_failed.local.v1",
        "status": "FAILED_VISIBLE_CHECKPOINT_PRESERVED",
        "task_id": load_config()["task_id"],
        "stage": stage,
        "exit_code": int(exit_code),
        "source_commit": source_commit,
        "run_id": run_id,
        "checkpoint_preserved": True,
        "partial_outputs_preserved": True,
        "c5_executed": False,
        "official_G3_G4_PASS_usable": None,
        "scientific_verdict": None,
    }
    store.add_json(relative, body)
    return body


__all__ = [
    "AddOnceStore",
    "CONDITION_ID",
    "associate_population",
    "complete_task",
    "finalize",
    "load_config",
    "lod2_reference_rows",
    "prepare_condition",
    "record_failure",
    "record_terminal",
    "validate_config",
    "verify_terminal",
]
