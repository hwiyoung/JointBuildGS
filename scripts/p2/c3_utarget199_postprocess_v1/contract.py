"""Add-once C3 paired checkpoint exports and roofprint-free Stage-3 read-out.

Both C3 geometries and their native Gaussian exports are frozen before stable
building bboxes or independent UAS evaluation cells are opened.  The native
point cloud and surfel mesh are presentation/intermediate records; Roofer uses
the same deterministic 1 m class-2/6 read-out contract as C1/C2.
"""

from __future__ import annotations

from collections import Counter, defaultdict
import csv
import hashlib
import io
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np
import torch

from scripts.p2_baselines.c1_c2_feasibility_pilot_v1.contract import (
    AddOnceStore,
    Point,
    component_job,
    derive_components,
    jsonl_bytes,
    parse_jsonl,
    provisional_output_check,
    score_continuous,
)
from scripts.p2.c3_development_stage3_v1.contract import load_reused_config
from scripts.p2_baselines.c1_c2_feasibility_pilot_finalize_recovery_r4_v1.contract import (
    roof_triangles_from_cityjsonseq,
)
from src.stage2.model import quat_to_rotmat
from src.stage3.c3_checkpoint_roofer_adapter_v1 import (
    load_c3_checkpoint,
    materialize_component_ready_evidence,
)


REPO = Path(__file__).resolve().parents[3]
CONFIG_PATH = REPO / "configs/p2/c3_utarget199_postprocess_v1/postprocess_v1.json"


def load_config(path: Path = CONFIG_PATH) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def validate_config(
    config: Mapping[str, Any] | None = None,
    *,
    require_activation: bool = True,
) -> dict[str, Any]:
    cfg = dict(config or load_config())
    conditions = list(cfg.get("conditions") or ())
    ids = [row.get("condition_id") for row in conditions]
    if ids != ["C3_1_SEM", "C3_2_SEM_DEPTH"]:
        raise RuntimeError("C3 paired condition order drifted")
    scope = cfg.get("scope") or {}
    if (
        scope.get("population") != "U_target"
        or int(scope.get("building_count", -1)) != 199
        or int(scope.get("expected_result_rows", -1)) != 398
        or scope.get("pre_execution_building_exclusion_allowed") is not False
        or scope.get("visible_72_10_subgroup_rows") is not False
        or scope.get("c4_c5_access_allowed") is not False
    ):
        raise RuntimeError("C3 U_target scope drifted")
    if cfg.get("scientific_verdict", "invalid") is not None:
        raise RuntimeError("scientific_verdict must remain null")
    if cfg.get("official_G3_G4_PASS_usable", "invalid") is not None:
        raise RuntimeError("official G3/G4/PASS must remain null")
    if (cfg.get("roofer") or {}).get("external_roofprint_allowed") is not False:
        raise RuntimeError("C3 Stage-3 must not accept an external roofprint")
    if (cfg.get("association") or {}).get("timing") != (
        "ONLY_AFTER_BOTH_CONDITIONS_GEOMETRY_R_DERIVED_AND_INTERMEDIATE_EXPORTS_ARE_FROZEN"
    ):
        raise RuntimeError("outcome-separation timing drifted")
    base = load_reused_config()
    if base["frame"]["grid_cell_m"] != float(cfg["frame"]["grid_cell_m"]):
        raise RuntimeError("common Stage-3 grid drifted")
    if base["stage3"]["command_args"] != cfg["roofer"]["command_args"]:
        raise RuntimeError("common Roofer command drifted")
    if require_activation:
        if cfg.get("status") != "APPROVED_FOR_EXECUTION":
            raise RuntimeError("postprocess config is not activated")
        for row in conditions:
            if not isinstance(row.get("expected_bytes"), int) or row["expected_bytes"] <= 0:
                raise RuntimeError("checkpoint byte binding is incomplete")
            digest = row.get("expected_sha256")
            if not isinstance(digest, str) or len(digest) != 64:
                raise RuntimeError("checkpoint SHA-256 binding is incomplete")
    return {
        "status": "PASS",
        "condition_ids": ids,
        "building_count": 199,
        "result_rows": 398,
        "scientific_verdict": None,
    }


def _sha256_file(path: Path) -> tuple[int, str]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
            size += len(chunk)
    return size, digest.hexdigest()


def _checkpoint_spec(config: Mapping[str, Any], condition_id: str) -> Mapping[str, Any]:
    matches = [row for row in config["conditions"] if row["condition_id"] == condition_id]
    if len(matches) != 1:
        raise RuntimeError(f"checkpoint condition binding is ambiguous: {condition_id}")
    return matches[0]


def _semantic_colors(labels: np.ndarray, sh0: np.ndarray) -> np.ndarray:
    base = np.clip(sh0[:, 0, :] * 0.28209479177387814 + 0.5, 0.0, 1.0)
    colors = np.rint(base * 255.0).astype(np.uint8)
    accents = np.asarray(
        [[90, 90, 90], [213, 94, 0], [0, 114, 178], [0, 158, 115]],
        dtype=np.float64,
    )
    return np.rint(0.58 * colors + 0.42 * accents[labels]).astype(np.uint8)


def gaussian_point_cloud_ply(
    state: Mapping[str, torch.Tensor],
    shift_xyz: Sequence[float],
) -> bytes:
    means = state["means"].detach().cpu().numpy().astype(np.float64)
    logits = state["sem_logits"].detach().cpu().numpy()
    labels = np.argmax(logits, axis=1).astype(np.uint8)
    colors = _semantic_colors(labels, state["sh0"].detach().cpu().numpy())
    opacity = torch.sigmoid(state["opacities_raw"].detach().cpu()).numpy().astype(np.float32)
    xyz = means + np.asarray(shift_xyz, dtype=np.float64)
    rows = np.empty(
        len(xyz),
        dtype=np.dtype([
            ("x", "<f8"), ("y", "<f8"), ("z", "<f8"),
            ("red", "u1"), ("green", "u1"), ("blue", "u1"),
            ("semantic_class", "u1"), ("opacity", "<f4"),
        ]),
    )
    rows["x"], rows["y"], rows["z"] = xyz.T
    rows["red"], rows["green"], rows["blue"] = colors.T
    rows["semantic_class"] = labels
    rows["opacity"] = opacity
    header = (
        "ply\nformat binary_little_endian 1.0\n"
        "comment JointBuildGS native Gaussian centers; EPSG:25832\n"
        f"element vertex {len(rows)}\n"
        "property double x\nproperty double y\nproperty double z\n"
        "property uchar red\nproperty uchar green\nproperty uchar blue\n"
        "property uchar semantic_class\nproperty float opacity\nend_header\n"
    ).encode("ascii")
    return header + rows.tobytes()


def gaussian_surfel_mesh_ply(
    state: Mapping[str, torch.Tensor],
    shift_xyz: Sequence[float],
) -> bytes:
    means = state["means"].detach().cpu().to(torch.float64)
    quats = state["quats"].detach().cpu().to(torch.float64)
    scales = torch.exp(state["log_scales"].detach().cpu().to(torch.float64))
    rotations = quat_to_rotmat(quats)
    u = rotations[:, :, 0] * scales[:, 0:1]
    v = rotations[:, :, 1] * scales[:, 1:2]
    centers = means + torch.as_tensor(shift_xyz, dtype=torch.float64)
    vertices = torch.stack(
        (centers - u - v, centers + u - v, centers + u + v, centers - u + v),
        dim=1,
    ).reshape(-1, 3).numpy()
    labels = torch.argmax(state["sem_logits"].detach().cpu(), dim=1).numpy().astype(np.uint8)
    colors = _semantic_colors(labels, state["sh0"].detach().cpu().numpy())
    vertex_colors = np.repeat(colors, 4, axis=0)
    vertex_labels = np.repeat(labels, 4)
    vrows = np.empty(
        len(vertices),
        dtype=np.dtype([
            ("x", "<f8"), ("y", "<f8"), ("z", "<f8"),
            ("red", "u1"), ("green", "u1"), ("blue", "u1"),
            ("semantic_class", "u1"),
        ]),
    )
    vrows["x"], vrows["y"], vrows["z"] = vertices.T
    vrows["red"], vrows["green"], vrows["blue"] = vertex_colors.T
    vrows["semantic_class"] = vertex_labels
    primitive = np.arange(len(means), dtype=np.int32) * 4
    faces = np.empty(
        len(means) * 2,
        dtype=np.dtype([("count", "u1"), ("indices", "<i4", (3,))]),
    )
    faces["count"] = 3
    faces["indices"][0::2] = np.stack((primitive, primitive + 1, primitive + 2), axis=1)
    faces["indices"][1::2] = np.stack((primitive, primitive + 2, primitive + 3), axis=1)
    header = (
        "ply\nformat binary_little_endian 1.0\n"
        "comment JointBuildGS exact 2D Gaussian surfel quads; EPSG:25832\n"
        f"element vertex {len(vrows)}\n"
        "property double x\nproperty double y\nproperty double z\n"
        "property uchar red\nproperty uchar green\nproperty uchar blue\n"
        "property uchar semantic_class\n"
        f"element face {len(faces)}\n"
        "property list uchar int vertex_indices\nend_header\n"
    ).encode("ascii")
    return header + vrows.tobytes() + faces.tobytes()


def _point_rows(evidence: Any) -> list[Point]:
    return [Point(p.x, p.y, p.z, p.classification, p.ix, p.iy) for p in evidence.points]


def prepare_condition(
    store: AddOnceStore,
    *,
    condition_id: str,
    checkpoint_path: Path,
    source_commit: str,
    run_id: str,
) -> dict[str, Any]:
    control_relative = f"control/{condition_id}_geometry_frozen_v1.json"
    completed = store.path(control_relative)
    if completed.is_file():
        body = json.loads(completed.read_text(encoding="utf-8"))
        if body.get("source_commit") != source_commit or body.get("run_id") != run_id:
            raise RuntimeError("existing condition freeze identity differs")
        return {**body, "fast_path": True, "new_writes": 0}
    config = load_config()
    validate_config(config)
    spec = _checkpoint_spec(config, condition_id)
    if checkpoint_path.is_symlink() or not checkpoint_path.is_file():
        raise RuntimeError("checkpoint is missing/non-regular")
    size, digest = _sha256_file(checkpoint_path)
    if size != int(spec["expected_bytes"]) or digest != spec["expected_sha256"]:
        raise RuntimeError("checkpoint identity differs from activated binding")
    arrays = load_c3_checkpoint(checkpoint_path)
    if arrays.iteration != int(spec["expected_iteration"]):
        raise RuntimeError("checkpoint iteration differs from activated binding")
    payload = torch.load(checkpoint_path, map_location="cpu", weights_only=True)
    state = payload["state_dict"]
    required = {"means", "quats", "log_scales", "opacities_raw", "sh0", "sem_logits"}
    if not required.issubset(state):
        raise RuntimeError("checkpoint lacks native export tensors")
    prefix = f"conditions/{condition_id}"
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
    components, component_map = derive_components(condition_id, points, base)
    if not components:
        raise RuntimeError("C3 checkpoint produced no Stage-3 components")
    lineage = store.add(
        f"{prefix}/freeze/surface_group_lineage_v1.jsonl",
        jsonl_bytes([group.__dict__ for group in evidence.groups]),
    )
    component_record = store.add(
        f"{prefix}/freeze/components_v1.jsonl",
        jsonl_bytes(components),
    )
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
        input_bytes, derived_bytes = component_job(condition_id, component, points, base)
        work = f"{prefix}/operations/{component['component_id']}/work"
        input_record = store.add(f"{work}/input.las", input_bytes)
        derived_record = store.add(f"{work}/r_derived.geojson", derived_bytes)
        jobs.append({
            "operation_unit_id": f"{condition_id}|{component['component_id']}",
            "condition_id": condition_id,
            "component_id": component["component_id"],
            "work_directory": work,
            "output_directory": f"{work}/out",
            "input": input_record,
            "r_derived": derived_record,
            "stable_id_used_to_derive_input": False,
            "reference_or_bbox_used_to_derive_input": False,
        })
    jobs_record = store.add(f"{prefix}/freeze/all_jobs_v1.jsonl", jsonl_bytes(jobs))
    body = {
        "schema": "jointbuildgs.c3_utarget199_condition_geometry_freeze.v1",
        "status": "FROZEN_BEFORE_BUILDING_IDENTITY_OR_REFERENCE_ACCESS",
        "condition_id": condition_id,
        "source_commit": source_commit,
        "run_id": run_id,
        "checkpoint": {
            "path": checkpoint_path.as_posix(),
            "bytes": size,
            "sha256": digest,
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
        "reference_cell_accesses": 0,
        "external_roofprint_accesses": 0,
        "scientific_verdict": None,
    }
    store.add_json(control_relative, body)
    return body


def _roster(config: Mapping[str, Any]) -> list[dict[str, Any]]:
    path = REPO / config["inputs"]["roster_git_path"]
    rows = list(csv.DictReader(io.StringIO(path.read_bytes().replace(b"\r\n", b"\n").decode("utf-8"))))
    if len(rows) != 199 or len({row["stable_id"] for row in rows}) != 199:
        raise RuntimeError("U_target roster is not exact 199")
    output = []
    for row in rows:
        output.append({
            **row,
            "bbox": [float(row[name]) for name in ("bbox_min_x", "bbox_min_y", "bbox_max_x", "bbox_max_y")],
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


def associate_population(
    store: AddOnceStore,
    *,
    reference_cells_path: Path,
    source_commit: str,
    run_id: str,
) -> dict[str, Any]:
    completed = store.path("control/population_associated_v1.json")
    if completed.is_file():
        return {**json.loads(completed.read_text(encoding="utf-8")), "fast_path": True, "new_writes": 0}
    config = load_config()
    validate_config(config)
    controls = []
    components: list[dict[str, Any]] = []
    jobs: dict[str, dict[str, Any]] = {}
    for condition in config["conditions"]:
        condition_id = condition["condition_id"]
        control = json.loads(store.path(f"control/{condition_id}_geometry_frozen_v1.json").read_text(encoding="utf-8"))
        if control.get("source_commit") != source_commit or control.get("run_id") != run_id:
            raise RuntimeError("condition geometry freeze identity differs")
        controls.append(control)
        components.extend(parse_jsonl(store.read_verified(control["components"])))
        for job in parse_jsonl(store.read_verified(control["all_jobs"])):
            jobs[job["operation_unit_id"]] = job
    ref_size, ref_digest = _sha256_file(reference_cells_path)
    spec = config["inputs"]
    if ref_size != int(spec["reference_cells_bytes"]) or ref_digest != spec["reference_cells_sha256"]:
        raise RuntimeError("reference-cell identity differs")
    reference_data = reference_cells_path.read_bytes()
    references = parse_jsonl(reference_data)
    reference_record = store.add("freeze/reference_cells_v1.jsonl", reference_data)
    roster = _roster(config)
    by_condition: defaultdict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for component in components:
        by_condition[str(component["condition_id"])].append(component)
    associations: list[dict[str, Any]] = []
    for condition in config["conditions"]:
        condition_id = condition["condition_id"]
        counts: dict[str, Counter[str]] = {row["stable_id"]: Counter() for row in roster}
        for component in by_condition[condition_id]:
            for building_id, count in _component_counts(
                component,
                roster,
                config["frame"]["grid_origin_xy"],
                float(config["frame"]["grid_cell_m"]),
            ).items():
                counts[building_id][str(component["component_id"])] += count
        for building in roster:
            building_id = str(building["stable_id"])
            ranked = sorted(counts[building_id].items(), key=lambda value: (-value[1], value[0]))
            selected = ranked[0][0] if ranked else None
            associations.append({
                "building_id": building_id,
                "condition_id": condition_id,
                "bbox_min_x": building["bbox"][0],
                "bbox_min_y": building["bbox"][1],
                "bbox_max_x": building["bbox"][2],
                "bbox_max_y": building["bbox"][3],
                "original_split": building.get("candidate_split") or building.get("split") or "",
                "component_id": selected,
                "operation_unit_id": f"{condition_id}|{selected}" if selected else None,
                "component_cell_count_inside_bbox": ranked[0][1] if ranked else 0,
                "overlapping_component_count": len(ranked),
                "component_candidates": [
                    {"component_id": name, "cell_count_inside_bbox": count}
                    for name, count in ranked
                ],
                "association_role": "IDENTITY_DISPLAY_AND_EVALUATION_ONLY_AFTER_GEOMETRY_FREEZE",
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
    if len(associations) != 398:
        raise RuntimeError("population association is not exact 199x2")
    selected_ids = sorted({str(row["operation_unit_id"]) for row in associations if row["operation_unit_id"]})
    missing = [unit_id for unit_id in selected_ids if unit_id not in jobs]
    if missing:
        raise RuntimeError("associated Roofer units are missing")
    execution_units = [jobs[unit_id] for unit_id in selected_ids]
    association_record = store.add("freeze/population_association_v1.jsonl", jsonl_bytes(associations))
    units_record = store.add("freeze/execution_units_v1.jsonl", jsonl_bytes(execution_units))
    tsv = "operation_unit_id\twork_directory\n" + "".join(
        f"{row['operation_unit_id']}\t{row['work_directory']}\n" for row in execution_units
    )
    units_tsv = store.add("freeze/execution_units_v1.tsv", tsv.encode("utf-8"))
    body = {
        "schema": "jointbuildgs.c3_utarget199_population_association.v1",
        "status": "ASSOCIATED_AFTER_BOTH_GEOMETRIES_FROZEN",
        "source_commit": source_commit,
        "run_id": run_id,
        "building_count": 199,
        "result_rows": 398,
        "reference_cells": reference_record,
        "population_association": association_record,
        "execution_units": units_record,
        "execution_units_tsv": units_tsv,
        "unique_roofer_operations": len(execution_units),
        "C1_C2_reruns": 0,
        "C4_C5_accesses": 0,
        "scientific_verdict": None,
    }
    store.add_json("control/population_associated_v1.json", body)
    return body


def _unit(store: AddOnceStore, unit_id: str) -> dict[str, Any]:
    associated = json.loads(store.path("control/population_associated_v1.json").read_text(encoding="utf-8"))
    units = parse_jsonl(store.read_verified(associated["execution_units"]))
    matches = [row for row in units if row["operation_unit_id"] == unit_id]
    if len(matches) != 1:
        raise RuntimeError("Roofer unit is missing/ambiguous")
    return matches[0]


def _output_records(store: AddOnceStore, output_dir: Path) -> list[dict[str, Any]]:
    records = []
    if not output_dir.is_dir() or output_dir.is_symlink():
        raise RuntimeError("Roofer output directory missing/non-regular")
    for path in sorted(output_dir.rglob("*")):
        if path.is_symlink() or (not path.is_file() and not path.is_dir()):
            raise RuntimeError("Roofer output tree contains non-regular entry")
        if path.is_file():
            data = path.read_bytes()
            records.append({
                "path": path.relative_to(store.root).as_posix(),
                "bytes": len(data),
                "sha256": hashlib.sha256(data).hexdigest(),
            })
    return records


def record_terminal(
    store: AddOnceStore,
    *,
    unit_id: str,
    exit_code: int,
    runtime_seconds: int,
) -> dict[str, Any]:
    unit = _unit(store, unit_id)
    relative = f"{unit['work_directory']}/roofer_terminal_v1.json"
    existing = store.path(relative)
    if existing.is_file():
        return {**verify_terminal(store, unit_id), "fast_path": True}
    work = store.path(unit["work_directory"])
    runtime = work / "runtime.log"
    if not runtime.is_file() or runtime.is_symlink():
        raise RuntimeError("Roofer runtime log missing/non-regular")
    runtime_bytes = runtime.read_bytes()
    body = {
        "schema": "jointbuildgs.c3_utarget199_roofer_terminal.v1",
        "status": "COMPLETED" if exit_code == 0 else "FAILED",
        "operation_unit_id": unit_id,
        "exit_code": exit_code,
        "runtime_seconds": runtime_seconds,
        "input": unit["input"],
        "r_derived": unit["r_derived"],
        "runtime_log": {
            "path": runtime.relative_to(store.root).as_posix(),
            "bytes": len(runtime_bytes),
            "sha256": hashlib.sha256(runtime_bytes).hexdigest(),
        },
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
        raise RuntimeError("Roofer terminal identity/status differs")
    store.read_verified(body["input"])
    store.read_verified(body["r_derived"])
    store.read_verified(body["runtime_log"])
    for record in body["output_records"]:
        store.read_verified(record)
    if _output_records(store, store.path(unit["output_directory"])) != body["output_records"]:
        raise RuntimeError("Roofer output tree differs from terminal")
    return body


def _city_file(output_dir: Path) -> Path | None:
    matches = sorted(
        path for path in output_dir.glob("*")
        if path.is_file() and path.suffix in {".json", ".jsonl"}
    ) if output_dir.is_dir() else []
    return matches[0] if len(matches) == 1 else None


def _csv_bytes(rows: Sequence[Mapping[str, Any]], fields: Sequence[str]) -> bytes:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode("utf-8")


def finalize(
    store: AddOnceStore,
    *,
    source_commit: str,
    run_id: str,
) -> dict[str, Any]:
    completed = store.path("control/finalized_v1.json")
    if completed.is_file():
        return {**json.loads(completed.read_text(encoding="utf-8")), "fast_path": True, "new_writes": 0}
    config = load_config()
    associated = json.loads(store.path("control/population_associated_v1.json").read_text(encoding="utf-8"))
    if associated.get("source_commit") != source_commit or associated.get("run_id") != run_id:
        raise RuntimeError("finalization identity differs")
    associations = parse_jsonl(store.read_verified(associated["population_association"]))
    references = parse_jsonl(store.read_verified(associated["reference_cells"]))
    refs_by_building: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in references:
        refs_by_building[str(row["stable_id"])].append(row)
    units = {
        row["operation_unit_id"]: row
        for row in parse_jsonl(store.read_verified(associated["execution_units"]))
    }
    component_results: dict[str, dict[str, Any]] = {}
    for unit_id, unit in units.items():
        terminal = verify_terminal(store, unit_id)
        output = store.path(unit["output_directory"])
        city = _city_file(output)
        screen = provisional_output_check(output) if terminal["exit_code"] == 0 and city else None
        triangles = []
        if city and screen and screen["G0_generated"] and screen["G1_schema_semantic"]:
            triangles = roof_triangles_from_cityjsonseq(city.name, city.read_bytes())
        component_results[unit_id] = {
            "terminal": terminal,
            "screen": screen,
            "triangles": triangles,
            "city_path": city.relative_to(store.root).as_posix() if city else None,
        }
    rows: list[dict[str, Any]] = []
    for association in associations:
        unit_id = association.get("operation_unit_id")
        component = component_results.get(str(unit_id)) if unit_id else None
        screen = component["screen"] if component else None
        component_g0 = bool(screen and screen["G0_generated"])
        component_g1 = bool(screen and screen["G1_schema_semantic"])
        one_to_one = bool(association["one_to_one_building_component"])
        refs = refs_by_building[str(association["building_id"])]
        metrics = score_continuous(refs, component["triangles"] if component else [])
        rows.append({
            **{key: value for key, value in association.items() if key != "component_candidates"},
            "run_id": run_id,
            "source_commit": source_commit,
            "reference_role": "INDEPENDENT_CURRENT_UAS_EVALUATION_ONLY",
            "reference_cell_count": len(refs),
            "component_G0_generated": component_g0,
            "component_G1_schema_semantic": component_g1,
            "G0_generated": bool(one_to_one and component_g0),
            "G1_schema_semantic": bool(one_to_one and component_g0 and component_g1),
            "G2_geometry_topology_valid": None,
            "G3_roof_structure_acceptable": None,
            "G4_geometric_accuracy_acceptable": None,
            "PASS_usable": None,
            "continuous_metrics": metrics,
            "cityjson_path": component["city_path"] if component else None,
            "scientific_verdict": None,
        })
    if len(rows) != 398 or len({(row["building_id"], row["condition_id"]) for row in rows}) != 398:
        raise RuntimeError("C3 result matrix is not exact 199x2")
    results = store.add("results/building_condition_metrics_v1.jsonl", jsonl_bytes(rows))
    summaries = []
    for condition in config["conditions"]:
        subset = [row for row in rows if row["condition_id"] == condition["condition_id"]]
        summaries.append({
            "condition_id": condition["condition_id"],
            "U_target": 199,
            "associated": sum(row["operation_unit_id"] is not None for row in subset),
            "one_to_one": sum(row["one_to_one_building_component"] for row in subset),
            "reference_scorable": sum(row["reference_cell_count"] > 0 for row in subset),
            "building_G0": sum(row["G0_generated"] for row in subset),
            "building_G1": sum(row["G1_schema_semantic"] for row in subset),
            "G2": "null",
            "G3": "null",
            "G4": "null",
            "PASS_usable": "null",
            "scientific_verdict": "null",
        })
    summary = store.add(
        "results/method_summary_v1.csv",
        _csv_bytes(summaries, list(summaries[0])),
    )
    body = {
        "schema": "jointbuildgs.c3_utarget199_postprocess_finalized.v1",
        "status": "TECHNICAL_RESULTS_COMPLETE_QUALITATIVE_PENDING",
        "task_id": config["task_id"],
        "source_commit": source_commit,
        "run_id": run_id,
        "building_count": 199,
        "condition_count": 2,
        "result_rows": 398,
        "building_condition_metrics": results,
        "method_summary": summary,
        "summary": summaries,
        "execution_accounting": {
            "C1_C2_roofer_invocations": 0,
            "C1_C2_metric_recomputation": 0,
            "C3_roofer_unique_operations": len(units),
            "C3_metric_rows": 398,
            "G2_invocations": 0,
            "C4_C5_accesses": 0,
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
    gs_render = json.loads(store.path("control/gs_render_complete_v1.json").read_text(encoding="utf-8"))
    if final.get("result_rows") != 398 or qualitative.get("case_sheet_count") != 199:
        raise RuntimeError("C3 final result/case count differs")
    if gs_render.get("condition_count") != 2 or gs_render.get("render_panel_count") != 8:
        raise RuntimeError("C3 GS render count differs")
    files = [path for path in store.root.rglob("*") if path.is_file() and not path.is_symlink()]
    total = sum(path.stat().st_size for path in files)
    if total > int(config["caps"]["output_bytes"]):
        raise RuntimeError("C3 postprocess output cap exceeded")
    body = {
        "schema": "jointbuildgs.c3_utarget199_postprocess_completed.v1",
        "status": "TECHNICAL_POSTPROCESS_COMPLETE",
        "task_id": config["task_id"],
        "building_count": 199,
        "condition_count": 2,
        "result_rows": 398,
        "case_sheet_count": 199,
        "actual_gs_render_panels": 8,
        "native_gaussian_point_clouds": 2,
        "native_gaussian_surfel_meshes": 2,
        "file_count_before_completion": len(files),
        "bytes_before_completion": total,
        "official_G3_G4_PASS_usable": None,
        "scientific_verdict": None,
    }
    store.add_json("control/completed_v1.json", body)
    return body


__all__ = [
    "AddOnceStore",
    "associate_population",
    "complete_task",
    "finalize",
    "gaussian_point_cloud_ply",
    "gaussian_surfel_mesh_ply",
    "load_config",
    "prepare_condition",
    "record_terminal",
    "validate_config",
    "verify_terminal",
]
