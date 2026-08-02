"""Outcome-free evaluator closure for the sealed C1/C2 development pilot.

This module is intentionally read-only with respect to the sealed R3/R4 inputs.
It never invokes reconstruction, Roofer, or a geometry validator.  G2 reuses
the exact six-unit receipt produced by the sibling pinned runner.  G3 and G4
remain development diagnostics, so this module can never emit a positive
``PASS_usable``.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import tempfile
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Iterator, Mapping, Sequence

import numpy as np


REPO = Path(__file__).resolve().parents[3]
DEFAULT_CONFIG = REPO / "configs/evaluation/c1_c2_dev_gate_closure_v1/criterion_candidate_v1.json"
METHODS = ("C1_L_upper", "C2_MVS")
PROHIBITED_PATH_TOKENS = ("validation", "held_out", "fusion", "r_ext")


class ClosureError(RuntimeError):
    """Fail-closed contract error."""


def canonical_json_bytes(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def repo_path(value: str) -> Path:
    path = (REPO / value).resolve()
    try:
        path.relative_to(REPO.resolve())
    except ValueError as error:
        raise ClosureError(f"repository path escapes the repository: {value}") from error
    return path


def _read_bound_file(spec: Mapping[str, Any]) -> bytes:
    path = repo_path(str(spec["path"]))
    if path.is_symlink() or not path.is_file():
        raise ClosureError(f"bound Git input is missing or non-regular: {path}")
    data = path.read_bytes()
    if len(data) != int(spec["bytes"]) or sha256_bytes(data) != spec["sha256"]:
        raise ClosureError(f"bound Git input identity differs: {spec['path']}")
    return data


def load_config(path: Path = DEFAULT_CONFIG) -> dict[str, Any]:
    config = json.loads(path.read_text(encoding="utf-8"))
    if config.get("schema") != "jointbuildgs.c1_c2_dev_gate_closure_candidate.v1":
        raise ClosureError("unexpected criterion candidate schema")
    if config.get("status") != "USER_DIRECTED_PROVISIONAL_DEVELOPMENT_DIAGNOSTIC_CLOSURE":
        raise ClosureError("unexpected development closure authority")
    if config.get("scientific_verdict") is not None:
        raise ClosureError("scientific_verdict must remain null")
    if config["scope"] != {
        "split": "development",
        "building_count": 51,
        "condition_ids": ["C1_L_upper", "C2_MVS"],
        "expected_rows": 102,
        "validation_access": False,
        "held_out_access": False,
    }:
        raise ClosureError("development-only scope contract differs")
    g2 = config["gates"]["G2"]
    if (
        g2.get("status") != "READY_PINNED_IMAGE_AND_STDIN_CONTRACT"
        or g2.get("validator") != "val3dity"
        or g2.get("version") != "2.6.0"
        or g2.get("container_image_id") != "sha256:02b4b7bb2e35e9b88bcc8457678ed8f178cca8f76f22b1b62f02721359e46be8"
        or g2.get("command", [])[-1:] != ["stdin"]
    ):
        raise ClosureError("pinned G2 validator contract differs")
    for spec in config["inputs"].values():
        _read_bound_file(spec)
    freeze = json.loads(_read_bound_file(config["inputs"]["gate_s0_freeze_recovery_config"]))
    if freeze.get("evaluation", {}).get("absolute_z_metrics_enabled") is not False:
        raise ClosureError("absolute Z gate guard differs from the frozen Gate S0 contract")
    return config


@dataclass(frozen=True)
class RoofSurface:
    surface_id: str
    triangles: tuple[np.ndarray, ...]
    normal: np.ndarray

    def vertical_z(self, x: float, y: float) -> float | None:
        values = [_vertical_z(x, y, triangle) for triangle in self.triangles]
        finite = [value for value in values if value is not None]
        return max(finite) if finite else None


def _transformed_vertices(record: Mapping[str, Any], inherited: Mapping[str, Any] | None) -> np.ndarray:
    transform = record.get("transform") or inherited or {"scale": [1, 1, 1], "translate": [0, 0, 0]}
    vertices = np.asarray(record.get("vertices", []), dtype=np.float64)
    scale = np.asarray(transform.get("scale", [1, 1, 1]), dtype=np.float64)
    translate = np.asarray(transform.get("translate", [0, 0, 0]), dtype=np.float64)
    if vertices.ndim != 2 or (vertices.size and vertices.shape[1] < 3):
        raise ClosureError("CityJSON vertex array is invalid")
    if scale.shape != (3,) or translate.shape != (3,):
        raise ClosureError("CityJSON transform is invalid")
    return vertices[:, :3] * scale + translate if vertices.size else np.empty((0, 3), dtype=np.float64)


def _roof_ring_records(geometry: Mapping[str, Any]) -> Iterator[tuple[int, list[int]]]:
    semantics = geometry.get("semantics") or {}
    semantic_surfaces = semantics.get("surfaces") or []
    roof_indices = {
        index
        for index, surface in enumerate(semantic_surfaces)
        if isinstance(surface, Mapping) and surface.get("type") == "RoofSurface"
    }
    boundaries = geometry.get("boundaries") or []
    values = semantics.get("values") or []
    candidates: list[tuple[Any, Any]] = []
    kind = geometry.get("type")
    if kind in ("MultiSurface", "CompositeSurface"):
        candidates = list(zip(boundaries, values))
    elif kind == "Solid":
        candidates = [
            (surface, semantic)
            for shell, shell_values in zip(boundaries, values)
            for surface, semantic in zip(shell, shell_values)
        ]
    elif kind in ("MultiSolid", "CompositeSolid"):
        candidates = [
            (surface, semantic)
            for solid, solid_values in zip(boundaries, values)
            for shell, shell_values in zip(solid, solid_values)
            for surface, semantic in zip(shell, shell_values)
        ]
    for surface_index, (rings, semantic) in enumerate(candidates):
        if semantic not in roof_indices:
            continue
        if not isinstance(rings, list) or not rings or not isinstance(rings[0], list):
            raise ClosureError("RoofSurface boundary is malformed")
        if len(rings) != 1:
            raise ClosureError("RoofSurface inner rings are unsupported by candidate v1")
        yield surface_index, [int(value) for value in rings[0]]


def parse_cityjsonseq_roof_surfaces(data: bytes, source_name: str = "sealed.city.jsonl") -> list[RoofSurface]:
    inherited: Mapping[str, Any] | None = None
    output: list[RoofSurface] = []
    for line_number, raw_line in enumerate(data.decode("utf-8").splitlines(), start=1):
        if not raw_line.strip():
            continue
        record = json.loads(raw_line)
        if record.get("type") == "CityJSON" and record.get("transform"):
            inherited = record["transform"]
        vertices = _transformed_vertices(record, inherited)
        for object_id, city_object in sorted((record.get("CityObjects") or {}).items()):
            for geometry_index, geometry in enumerate(city_object.get("geometry", [])):
                if str(geometry.get("lod")) != "2.2":
                    continue
                for surface_index, ring in _roof_ring_records(geometry):
                    if len(ring) >= 2 and ring[0] == ring[-1]:
                        ring = ring[:-1]
                    if len(ring) < 3 or any(index < 0 or index >= len(vertices) for index in ring):
                        raise ClosureError("RoofSurface ring has invalid vertex references")
                    triangles: list[np.ndarray] = []
                    area_vector = np.zeros(3, dtype=np.float64)
                    first = vertices[ring[0]]
                    for index in range(1, len(ring) - 1):
                        triangle = np.vstack((first, vertices[ring[index]], vertices[ring[index + 1]]))
                        cross = np.cross(triangle[1] - triangle[0], triangle[2] - triangle[0])
                        if np.linalg.norm(cross) <= 1e-12:
                            continue
                        triangles.append(triangle)
                        area_vector += cross
                    norm = float(np.linalg.norm(area_vector))
                    if not triangles or norm <= 1e-12:
                        raise ClosureError("RoofSurface is degenerate")
                    output.append(
                        RoofSurface(
                            surface_id=f"{source_name}:{line_number}:{object_id}:{geometry_index}:{surface_index}",
                            triangles=tuple(triangles),
                            normal=area_vector / norm,
                        )
                    )
    return output


def cityjsonseq_feature_ids(data: bytes) -> list[str]:
    values = _jsonl(data)
    if not values or values[0].get("type") != "CityJSON":
        raise ClosureError("CityJSONSeq must start with one metadata record")
    ids: list[str] = []
    for value in values[1:]:
        feature_id = value.get("id")
        if value.get("type") != "CityJSONFeature" or not isinstance(feature_id, str) or not feature_id:
            raise ClosureError("CityJSONSeq feature identity is invalid")
        ids.append(feature_id)
    if not ids or len(ids) != len(set(ids)):
        raise ClosureError("CityJSONSeq feature identities are empty or duplicated")
    return ids


def parse_val3dity_cjseq_stdout(data: bytes, expected_feature_ids: Sequence[str]) -> dict[str, Any]:
    """Parse the exact line-oriented stdout produced by val3dity 2.6.0 stdin mode."""

    lines = data.decode("utf-8").splitlines()
    expected = ["1st-line", *expected_feature_ids]
    if len(lines) != len(expected):
        raise ClosureError("val3dity stdin output line count differs")
    parsed: list[dict[str, Any]] = []
    decoder = json.JSONDecoder()
    for line, expected_id in zip(lines, expected):
        try:
            feature_id, offset = decoder.raw_decode(line)
            remainder = line[offset:].lstrip()
            errors, consumed = decoder.raw_decode(remainder)
        except (json.JSONDecodeError, TypeError) as error:
            raise ClosureError("val3dity stdin output is malformed") from error
        if remainder[consumed:].strip() or feature_id != expected_id:
            raise ClosureError("val3dity stdin output feature order or syntax differs")
        if (
            not isinstance(errors, list)
            or any(not isinstance(code, int) or isinstance(code, bool) for code in errors)
            or errors != sorted(set(errors))
        ):
            raise ClosureError("val3dity stdin error-code list is invalid")
        parsed.append({"feature_id": feature_id, "error_codes": errors, "valid": not errors})
    if parsed[0]["error_codes"]:
        raise ClosureError("val3dity rejected the CityJSONSeq metadata record")
    features = parsed[1:]
    return {
        "metadata": parsed[0],
        "features": features,
        "unit_valid": all(row["valid"] for row in features),
    }


def _vertical_z(x: float, y: float, triangle: np.ndarray) -> float | None:
    a, b, c = triangle
    denominator = (b[1] - c[1]) * (a[0] - c[0]) + (c[0] - b[0]) * (a[1] - c[1])
    if abs(float(denominator)) <= 1e-12:
        return None
    alpha = ((b[1] - c[1]) * (x - c[0]) + (c[0] - b[0]) * (y - c[1])) / denominator
    beta = ((c[1] - a[1]) * (x - c[0]) + (a[0] - c[0]) * (y - c[1])) / denominator
    gamma = 1.0 - alpha - beta
    if min(alpha, beta, gamma) < -1e-9:
        return None
    return float(alpha * a[2] + beta * b[2] + gamma * c[2])


def _normal_angle_degrees(left: Sequence[float], right: Sequence[float]) -> float:
    a, b = np.asarray(left, dtype=np.float64), np.asarray(right, dtype=np.float64)
    if a.shape != (3,) or b.shape != (3,) or np.linalg.norm(a) <= 0 or np.linalg.norm(b) <= 0:
        return math.inf
    cosine = float(np.clip(abs(np.dot(a / np.linalg.norm(a), b / np.linalg.norm(b))), 0.0, 1.0))
    return math.degrees(math.acos(cosine))


def _grid_indices(bounds: Sequence[float], origin: Sequence[float], cell_m: float) -> Iterator[tuple[int, int]]:
    min_x, min_y, max_x, max_y = (float(value) for value in bounds)
    x0, y0 = (float(value) for value in origin)
    ix0 = math.ceil((min_x - x0) / cell_m - 0.5 - 1e-9)
    iy0 = math.ceil((min_y - y0) / cell_m - 0.5 - 1e-9)
    ix1 = math.floor((max_x - x0) / cell_m - 0.5 + 1e-9)
    iy1 = math.floor((max_y - y0) / cell_m - 0.5 + 1e-9)
    for iy in range(iy0, iy1 + 1):
        for ix in range(ix0, ix1 + 1):
            yield ix, iy


def evaluate_g3(
    reference_rows: Sequence[Mapping[str, Any]],
    surfaces: Sequence[RoofSurface],
    bounds: Sequence[float],
    config: Mapping[str, Any],
) -> dict[str, Any]:
    """Compute a development-only plane-support candidate without altering geometry."""

    rule = config["gates"]["G3"]
    cell_m = float(rule["grid_cell_m"])
    origin = rule["grid_origin_xy"]
    reference: dict[tuple[int, int], Mapping[str, Any]] = {}
    by_patch: defaultdict[str, set[tuple[int, int]]] = defaultdict(set)
    for row in reference_rows:
        key = (int(row["cell_ix"]), int(row["cell_iy"]))
        if key in reference:
            raise ClosureError("reference score cell is duplicated within a building")
        reference[key] = row
        by_patch[str(row["patch_id"])].add(key)
    surface_support: defaultdict[str, set[tuple[int, int]]] = defaultdict(set)
    surface_by_id = {surface.surface_id: surface for surface in surfaces}
    for ix, iy in _grid_indices(bounds, origin, cell_m):
        x = float(origin[0]) + (ix + 0.5) * cell_m
        y = float(origin[1]) + (iy + 0.5) * cell_m
        for surface in surfaces:
            if surface.vertical_z(x, y) is not None:
                surface_support[surface.surface_id].add((ix, iy))
    pair_cells: defaultdict[tuple[str, str], set[tuple[int, int]]] = defaultdict(set)
    max_angle = float(rule["matching_normal_angle_degrees_max"])
    for key, row in reference.items():
        ref_normal = [float(row["normal_x"]), float(row["normal_y"]), float(row["normal_z"])]
        patch_id = str(row["patch_id"])
        for surface_id, supported in surface_support.items():
            if key in supported and _normal_angle_degrees(ref_normal, surface_by_id[surface_id].normal) <= max_angle:
                pair_cells[(patch_id, surface_id)].add(key)
    accepted: dict[tuple[str, str], set[tuple[int, int]]] = {}
    bilateral = float(rule["bilateral_support_overlap_min"])
    for pair, cells in pair_cells.items():
        patch_id, surface_id = pair
        if len(cells) / len(by_patch[patch_id]) >= bilateral and len(cells) / len(surface_support[surface_id]) >= bilateral:
            accepted[pair] = cells
    matched_reference = set().union(*accepted.values()) if accepted else set()
    matched_prediction_cells = set().union(*accepted.values()) if accepted else set()
    prediction_cells = set().union(*surface_support.values()) if surface_support else set()
    prediction_atoms = {(key, surface_id) for surface_id, cells in surface_support.items() for key in cells}
    ref_n, pred_n, tp_n = len(reference), len(prediction_cells), len(matched_reference)
    completeness = tp_n / ref_n if ref_n else None
    correctness = len(matched_prediction_cells) / pred_n if pred_n else None
    quality_denominator = ref_n + pred_n - tp_n
    quality = tp_n / quality_denominator if quality_denominator else None
    by_ref_matches: defaultdict[str, set[str]] = defaultdict(set)
    by_pred_matches: defaultdict[str, set[str]] = defaultdict(set)
    for patch_id, surface_id in accepted:
        by_ref_matches[patch_id].add(surface_id)
        by_pred_matches[surface_id].add(patch_id)
    over_excess = sum(max(0, len(values) - 1) for values in by_ref_matches.values())
    under_excess = sum(max(0, len(values) - 1) for values in by_pred_matches.values())
    oversegmentation = over_excess / max(1, len(by_patch))
    undersegmentation = under_excess / max(1, len(surface_support))
    values = {
        "roof_plane_completeness": completeness,
        "roof_plane_correctness": correctness,
        "roof_plane_quality": quality,
        "oversegmentation": oversegmentation,
        "undersegmentation": undersegmentation,
        "reference_plane_count": len(by_patch),
        "predicted_plane_count": len(surface_support),
        "accepted_plane_pair_count": len(accepted),
        "reference_cell_count": ref_n,
        "predicted_cell_count": pred_n,
        "predicted_support_atom_count": len(prediction_atoms),
        "matched_reference_cell_count": tp_n,
        "matching_version": rule["matching_version"],
    }
    required = rule["candidate_thresholds"]
    candidate = bool(
        completeness is not None
        and correctness is not None
        and quality is not None
        and completeness >= float(required["roof_plane_completeness_min"])
        and correctness >= float(required["roof_plane_correctness_min"])
        and quality >= float(required["roof_plane_quality_min"])
        and oversegmentation <= float(required["oversegmentation_max"])
        and undersegmentation <= float(required["undersegmentation_max"])
    )
    return {**values, "G3_roof_structure_acceptable": candidate, "candidate_only": True}


def _finite_metric(row: Mapping[str, Any], name: str) -> float | None:
    value = row.get(name)
    if value in (None, ""):
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def evaluate_g4(metric_row: Mapping[str, Any], config: Mapping[str, Any]) -> tuple[bool | None, dict[str, float | None], str | None]:
    rule = config["gates"]["G4"]
    metrics = {
        name: _finite_metric(metric_row, name)
        for name in rule["required_metrics"]
    }
    missing = sorted(name for name, value in metrics.items() if value is None)
    if missing:
        return None, metrics, "MISSING_SEALED_CONTINUOUS_METRICS:" + ",".join(missing)
    thresholds = rule["candidate_thresholds"]
    passed = all(
        float(metrics[name]) >= float(limit)
        if threshold_name.endswith("_min")
        else float(metrics[name]) <= float(limit)
        for threshold_name, limit in thresholds.items()
        for name in [rule["threshold_metric_map"][threshold_name]]
    )
    return bool(passed), metrics, None


def _parse_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if value in (None, ""):
        return None
    lowered = str(value).strip().lower()
    if lowered in ("true", "1"):
        return True
    if lowered in ("false", "0"):
        return False
    raise ClosureError(f"invalid boolean value: {value!r}")


def evaluate_row(
    metric_row: Mapping[str, Any],
    reference_rows: Sequence[Mapping[str, Any]],
    surfaces: Sequence[RoofSurface],
    bounds: Sequence[float],
    config: Mapping[str, Any],
    g2_unit: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    method = str(metric_row["method_id"])
    if method not in METHODS or metric_row.get("split") != "development":
        raise ClosureError("only sealed C1/C2 development rows are accepted")
    g0 = _parse_bool(metric_row.get("G0_generated"))
    g1 = _parse_bool(metric_row.get("G1_schema_semantic"))
    null_reasons: dict[str, str] = {"PASS_usable": "G3_G4_DIAGNOSTIC_ONLY_CRITERION_NOT_FROZEN"}
    g2: bool | None = None
    g2_reused: dict[str, Any] | None = None
    g3_metrics: dict[str, Any] | None = None
    g3: bool | None = None
    g4_metrics: dict[str, float | None] | None = None
    g4: bool | None = None
    if method == "C1_L_upper":
        null_reasons["G2"] = "C1_NOT_IN_C2_PINNED_G2_SCOPE"
        null_reasons["G3"] = "SELF_REFERENCE_UPPER_BASELINE_NOT_INDEPENDENT_ACCEPTANCE"
        null_reasons["G4"] = "SELF_REFERENCE_UPPER_BASELINE_NOT_INDEPENDENT_ACCEPTANCE"
    elif g0 is not True or g1 is not True:
        null_reasons["G2"] = "UPSTREAM_G0_OR_G1_NOT_TRUE"
        null_reasons["G3"] = "UPSTREAM_G0_OR_G1_NOT_TRUE"
        null_reasons["G4"] = "UPSTREAM_G0_OR_G1_NOT_TRUE"
    else:
        if g2_unit is None:
            null_reasons["G2"] = config["gates"]["G2"]["null_reason_without_receipt"]
        else:
            g2 = bool(g2_unit["result"]["unit_valid"])
            g2_reused = {
                "operation_unit_id": g2_unit["operation_unit_id"],
                "source": g2_unit["source"],
                "feature_count": len(g2_unit["result"]["features"]),
                "unit_valid": g2,
            }
        g3_metrics = evaluate_g3(reference_rows, surfaces, bounds, config)
        g3_metrics["diagnostic_only_blocker"] = config["gates"]["G3"]["gate_blocker"]
        null_reasons["G3"] = config["gates"]["G3"]["gate_blocker"]
        g4_candidate, g4_metrics, g4_reason = evaluate_g4(metric_row, config)
        if g4_metrics is not None:
            g4_metrics = {**g4_metrics, "diagnostic_candidate": g4_candidate}
        if g4_reason:
            null_reasons["G4"] = g4_reason + ";" + config["gates"]["G4"]["gate_blocker"]
        else:
            null_reasons["G4"] = config["gates"]["G4"]["gate_blocker"]
    first_failure = None
    for name, value in (("G0", g0), ("G1", g1), ("G2", g2), ("G3", g3), ("G4", g4)):
        if value is False:
            first_failure = name
            break
        if value is None:
            break
    return {
        "schema": "jointbuildgs.c1_c2_dev_gate_closure.row.v1",
        "building_id": metric_row["building_id"],
        "group_id": metric_row["group_id"],
        "split": "development",
        "method_id": method,
        "source_run_id": metric_row["run_id"],
        "source_operation_id": metric_row["operation_id"],
        "source_operation_unit_id": metric_row.get("operation_unit_id") or None,
        "criterion_version": config["criterion"]["version"],
        "criterion_status": config["criterion"]["status"],
        "G0_generated": g0,
        "G1_schema_semantic": g1,
        "G2_geometry_topology_valid": g2,
        "G3_roof_structure_acceptable": g3,
        "G4_geometric_accuracy_acceptable": g4,
        "PASS_usable": None,
        "first_known_failure_gate": first_failure,
        "gate_null_reasons": null_reasons,
        "G2_validation_reused_exact": g2_reused,
        "G3_metrics": g3_metrics,
        "G4_metrics_reused_exact": g4_metrics,
        "reconstruction_invocation_count": 0,
        "roofer_invocation_count": 0,
        "validator_invocation_count": 0,
        "scientific_verdict": None,
    }


def _safe_source_file(source_root: Path, relative: str) -> Path:
    normalized = relative.replace("\\", "/").lower()
    if any(token in normalized for token in PROHIBITED_PATH_TOKENS):
        raise ClosureError(f"prohibited source path token: {relative}")
    root = source_root.resolve()
    path = (root / relative).resolve()
    try:
        path.relative_to(root)
    except ValueError as error:
        raise ClosureError(f"source path escapes sealed root: {relative}") from error
    if path.is_symlink() or not path.is_file():
        raise ClosureError(f"sealed source file is missing or non-regular: {relative}")
    return path


def _read_source_record(source_root: Path, record: Mapping[str, Any]) -> bytes:
    data = _safe_source_file(source_root, str(record["path"])).read_bytes()
    if len(data) != int(record["bytes"]) or sha256_bytes(data) != record["sha256"]:
        raise ClosureError(f"sealed source record identity differs: {record['path']}")
    return data


def _jsonl(data: bytes) -> list[dict[str, Any]]:
    return [json.loads(line) for line in data.decode("utf-8").splitlines() if line.strip()]


def _metric_rows(config: Mapping[str, Any]) -> list[dict[str, str]]:
    data = _read_bound_file(config["inputs"]["promoted_metrics"])
    rows = list(csv.DictReader(data.decode("utf-8").splitlines()))
    expected = int(config["scope"]["expected_rows"])
    keys = {(row["building_id"], row["method_id"]) for row in rows}
    if len(rows) != expected or len(keys) != expected:
        raise ClosureError("sealed promoted metric matrix is not exact 51x2")
    if {row["split"] for row in rows} != {"development"} or {row["method_id"] for row in rows} != set(METHODS):
        raise ClosureError("sealed promoted metric scope differs")
    roster_data = _read_bound_file(config["inputs"]["development_roster"])
    roster_ids = {row["stable_id"] for row in csv.DictReader(roster_data.decode("utf-8").splitlines())}
    expected_keys = {(stable_id, method) for stable_id in roster_ids for method in METHODS}
    if len(roster_ids) != 51 or keys != expected_keys:
        raise ClosureError("sealed promoted metric rows differ from the exact development roster x two methods")
    return rows


def load_g2_receipts(path: Path, config: Mapping[str, Any], source_records: Mapping[str, Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    g2 = config["gates"]["G2"]
    if (
        data.get("schema") != "jointbuildgs.c1_c2_dev_g2_receipts.v1"
        or data.get("status") != "COMPLETED_PINNED_VALIDATION"
        or data.get("scientific_verdict") is not None
        or data.get("container_image_id") != g2["container_image_id"]
        or data.get("command") != g2["command"]
        or data.get("validator_invocation_count") != g2["expected_unique_c2_units"]
    ):
        raise ClosureError("G2 receipt authority differs")
    units = data.get("units")
    if not isinstance(units, list) or len(units) != g2["expected_unique_c2_units"]:
        raise ClosureError("G2 receipt unit count differs")
    output: dict[str, dict[str, Any]] = {}
    expected_units = {
        f"C2_MVS|{source_path.split('/')[2]}"
        for source_path in source_records
        if source_path.startswith("operations/C2_MVS/") and source_path.endswith(".jsonl")
    }
    for unit in units:
        unit_id = unit.get("operation_unit_id")
        source = unit.get("source")
        result = unit.get("result")
        if (
            not isinstance(unit_id, str)
            or unit_id in output
            or not isinstance(source, Mapping)
            or not isinstance(result, Mapping)
            or unit.get("process_exit_code") != 0
        ):
            raise ClosureError("G2 unit receipt is malformed or duplicated")
        record = source_records.get(str(source.get("path")))
        if record is None or any(source.get(key) != record.get(key) for key in ("path", "bytes", "sha256")):
            raise ClosureError("G2 unit source identity differs from the sealed manifest")
        features = result.get("features")
        if not isinstance(features, list) or not features:
            raise ClosureError("G2 unit receipt has no feature verdicts")
        for row in features:
            errors = row.get("error_codes") if isinstance(row, Mapping) else None
            if not isinstance(errors, list) or row.get("valid") is not (not errors):
                raise ClosureError("G2 feature verdict is internally inconsistent")
        observed_valid = all(row["valid"] for row in features)
        if result.get("unit_valid") is not observed_valid:
            raise ClosureError("G2 unit aggregate differs from feature verdicts")
        output[unit_id] = unit
    if set(output) != expected_units:
        raise ClosureError("G2 receipt units differ from the exact six sealed C2 units")
    return output


def run(source_root: Path, g2_receipt_path: Path, output_path: Path, config_path: Path = DEFAULT_CONFIG) -> dict[str, Any]:
    config = load_config(config_path)
    if output_path.exists():
        raise ClosureError("output is add-once and already exists")
    try:
        output_path.resolve().relative_to(source_root.resolve())
    except ValueError:
        pass
    else:
        raise ClosureError("output must not be written inside the sealed source namespace")
    manifest = json.loads(_read_bound_file(config["inputs"]["source_manifest"]))
    records = {record["path"]: record for record in manifest["records"]}
    g2_receipts = load_g2_receipts(g2_receipt_path, config, records)
    reference_path = "freeze/development_score_cells_v1.jsonl"
    references = _jsonl(_read_source_record(source_root, records[reference_path]))
    by_building: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in references:
        by_building[str(row["stable_id"])].append(row)
    scope_data = _read_bound_file(config["inputs"]["development_score_scope"])
    scope = {row["stable_id"]: row for row in csv.DictReader(scope_data.decode("utf-8").splitlines())}
    metric_rows = _metric_rows(config)
    surface_cache: dict[str, list[RoofSurface]] = {}
    output_rows: list[dict[str, Any]] = []
    for row in metric_rows:
        unit_id = row.get("operation_unit_id") or ""
        surfaces: list[RoofSurface] = []
        if row["method_id"] == "C2_MVS" and _parse_bool(row["G0_generated"]) is True and unit_id:
            if unit_id not in surface_cache:
                condition, component = unit_id.split("|", 1)
                prefix = f"operations/{condition}/{component}/work/out/"
                candidates = [record for path, record in records.items() if path.startswith(prefix) and path.endswith(".jsonl")]
                if len(candidates) != 1:
                    raise ClosureError(f"expected one sealed CityJSONSeq record for {unit_id}")
                payload = _read_source_record(source_root, candidates[0])
                surface_cache[unit_id] = parse_cityjsonseq_roof_surfaces(payload, candidates[0]["path"])
            surfaces = surface_cache[unit_id]
        scope_row = scope[row["building_id"]]
        bounds = [scope_row[name] for name in ("bbox_min_x", "bbox_min_y", "bbox_max_x", "bbox_max_y")]
        output_rows.append(
            evaluate_row(
                row,
                by_building[row["building_id"]],
                surfaces,
                bounds,
                config,
                g2_receipts.get(unit_id),
            )
        )
    if len(output_rows) != 102:
        raise ClosureError("closure output row count differs")
    payload = b"".join(canonical_json_bytes(row) for row in output_rows)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=output_path.parent, prefix=f".{output_path.name}.", delete=False) as handle:
        temporary = Path(handle.name)
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, output_path)
    return {
        "schema": "jointbuildgs.c1_c2_dev_gate_closure.run_receipt.v1",
        "status": "COMPLETED_CANDIDATE_ONLY",
        "rows": len(output_rows),
        "unique_sealed_cityjson_reads": len(surface_cache),
        "output": {"path": str(output_path), "bytes": len(payload), "sha256": sha256_bytes(payload)},
        "reconstruction_invocation_count": 0,
        "roofer_invocation_count": 0,
        "validator_invocation_count": 0,
        "validator_receipt_unit_count": len(g2_receipts),
        "PASS_usable_true_count": 0,
        "scientific_verdict": None,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--g2-receipt", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    print(json.dumps(run(args.source_root, args.g2_receipt, args.output, args.config), sort_keys=True))


if __name__ == "__main__":
    main()
