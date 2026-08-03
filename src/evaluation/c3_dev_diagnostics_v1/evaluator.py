"""Evaluate sealed C3 Roofer outputs without changing reconstruction geometry."""

from __future__ import annotations

import csv
import hashlib
import json
import math
from collections import defaultdict
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np

from scripts.p2.c3_development_stage3_v1.contract import verify_roofer_terminal
from scripts.p2_baselines.c1_c2_feasibility_pilot_v1.contract import (
    AddOnceStore,
    canonical_json_bytes,
    jsonl_bytes,
    parse_jsonl,
    sha256_bytes,
)
from src.evaluation.c1_c2_dev_gate_closure_v1.evaluator import (
    RoofSurface,
    _normal_angle_degrees,
    evaluate_g3,
    parse_cityjsonseq_roof_surfaces,
    parse_val3dity_cjseq_stdout,
)


REPO = Path(__file__).resolve().parents[3]
CONFIG_PATH = REPO / "configs/evaluation/c3_dev_diagnostics_v1/candidate_v1.json"


def load_config() -> dict[str, Any]:
    cfg = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    if cfg.get("status") != "DEVELOPMENT_DIAGNOSTIC_ONLY" or cfg.get("scientific_verdict", 1) is not None:
        raise RuntimeError("diagnostic authority differs")
    if cfg["scope"] != {
        "split": "development",
        "building_count": 51,
        "condition_ids": ["C1_L_upper", "C2_MVS", "C3_GS_image"],
        "validation_allowed": False,
        "held_out_allowed": False,
    }:
        raise RuntimeError("development scope differs")
    return cfg


def read_exact(path: Path, spec: Mapping[str, Any]) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise RuntimeError(f"input is missing/non-regular: {path}")
    data = path.read_bytes()
    if len(data) != int(spec["bytes"]) or sha256_bytes(data) != spec["sha256"]:
        raise RuntimeError(f"input identity differs: {path}")
    return data


def _output_record(terminal: Mapping[str, Any]) -> dict[str, Any]:
    records = terminal.get("output_records") or []
    matches = [r for r in records if str(r.get("path", "")).endswith(".city.jsonl")]
    if len(matches) != 1:
        raise RuntimeError("each C3 terminal must bind exactly one CityJSONSeq output")
    return dict(matches[0])


def prepare(c3_root: Path, output_root: Path) -> dict[str, Any]:
    """Verify all prior terminal receipts and freeze the 18 evaluation units."""

    source = AddOnceStore(c3_root)
    target = AddOnceStore(output_root)
    if target.path("control/prepared_v1.json").exists():
        raise RuntimeError("diagnostic prepare is add-once")
    final = json.loads(source.path("control/c3_development_technical_finalized_v1.json").read_bytes())
    source.read_verified(final["operation_checks"])
    source.read_verified(final["development_technical_results"])
    associated = json.loads(source.path("control/c3_development_associated_v1.json").read_bytes())
    units = parse_jsonl(source.read_verified(associated["execution_units"]))
    rows: list[dict[str, Any]] = []
    for unit in sorted(units, key=lambda row: row["operation_unit_id"]):
        unit_id = str(unit["operation_unit_id"])
        terminal = verify_roofer_terminal(source, unit_id=unit_id)
        record = _output_record(terminal)
        rows.append({
            "operation_unit_id": unit_id,
            "unit_key": hashlib.sha256(unit_id.encode()).hexdigest()[:16],
            "cityjson_relative_path": record["path"],
            "bytes": record["bytes"],
            "sha256": record["sha256"],
        })
    if len(rows) != 18:
        raise RuntimeError("expected exact 18 C3 evaluation units")
    target.add("freeze/evaluation_units_v1.jsonl", jsonl_bytes(rows))
    tsv = "operation_unit_id\tunit_key\tcityjson_relative_path\n" + "".join(
        f"{r['operation_unit_id']}\t{r['unit_key']}\t{r['cityjson_relative_path']}\n" for r in rows
    )
    target.add("freeze/evaluation_units_v1.tsv", tsv.encode())
    body = {
        "schema": "jointbuildgs.c3_dev_diagnostics.prepared.v1",
        "status": "PREPARED",
        "unit_count": 18,
        "terminal_receipts_verified": 18,
        "reconstruction_invocations": 0,
        "roofer_invocations": 0,
        "scientific_verdict": None,
    }
    target.add_json("control/prepared_v1.json", body)
    return body


def _percentile(values: Sequence[float], q: float) -> float | None:
    return float(np.quantile(np.asarray(values, dtype=np.float64), q)) if values else None


def continuous_metrics(
    reference_rows: Sequence[Mapping[str, Any]], surfaces: Sequence[RoofSurface]
) -> dict[str, Any]:
    """Score roof surfaces at exact independent UAS cell centres."""

    signed: list[float] = []
    normal_angles: list[float] = []
    for row in reference_rows:
        x, y, ref_z = float(row["cell_x"]), float(row["cell_y"]), float(row["top_z"])
        candidates = [(surface.vertical_z(x, y), surface.normal) for surface in surfaces]
        candidates = [(z, n) for z, n in candidates if z is not None]
        if not candidates:
            continue
        pred_z, normal = max(candidates, key=lambda item: float(item[0]))
        signed.append(float(pred_z) - ref_z)
        normal_angles.append(_normal_angle_degrees(
            [float(row["normal_x"]), float(row["normal_y"]), float(row["normal_z"])], normal
        ))
    coverage = len(signed) / len(reference_rows) if reference_rows else None
    mae = float(np.mean(np.abs(signed))) if signed else None
    rmsz = float(np.sqrt(np.mean(np.square(signed)))) if signed else None
    return {
        "reference_cell_count": len(reference_rows),
        "vertically_scored_cell_count": len(signed),
        "reference_vertical_coverage": coverage,
        "height_error_signed_mean_m": float(np.mean(signed)) if signed else None,
        "height_error_signed_median_m": float(np.median(signed)) if signed else None,
        "height_error_mae_m": mae,
        "RMSZ_m": rmsz,
        "RMSXY_m": 0.0 if coverage == 1.0 else None,
        "surface_distance_rmse_m": rmsz,
        "surface_distance_p95_m": _percentile([abs(v) for v in signed], 0.95),
        "normal_angular_error_median_deg": float(np.median(normal_angles)) if normal_angles else None,
        "normal_angular_error_p95_deg": _percentile(normal_angles, 0.95),
    }


def g4_candidate(metrics: Mapping[str, Any], cfg: Mapping[str, Any]) -> bool:
    limits = cfg["gates"]["G4"]["candidate_thresholds"]
    required = {
        "reference_vertical_coverage": metrics.get("reference_vertical_coverage"),
        "height_error_mae_m": metrics.get("height_error_mae_m"),
        "RMSZ_m": metrics.get("RMSZ_m"),
        "surface_distance_rmse_m": metrics.get("surface_distance_rmse_m"),
        "surface_distance_p95_m": metrics.get("surface_distance_p95_m"),
    }
    if any(value is None for value in required.values()):
        return False
    return bool(
        float(required["reference_vertical_coverage"]) >= limits["reference_vertical_coverage_min"]
        and float(required["height_error_mae_m"]) <= limits["height_error_mae_m_max"]
        and float(required["RMSZ_m"]) <= limits["RMSZ_m_max"]
        and float(required["surface_distance_rmse_m"]) <= limits["surface_distance_rmse_m_max"]
        and float(required["surface_distance_p95_m"]) <= limits["surface_distance_p95_m_max"]
    )


def _bounds(rows: Sequence[Mapping[str, Any]]) -> list[float]:
    xs, ys = [float(row["cell_x"]) for row in rows], [float(row["cell_y"]) for row in rows]
    return [min(xs) - 0.5, min(ys) - 0.5, max(xs) + 0.5, max(ys) + 0.5]


def _g2_result(path: Path, unit_id: str, city_data: bytes) -> dict[str, Any]:
    key = hashlib.sha256(unit_id.encode()).hexdigest()[:16]
    stdout = (path / key / "stdout.txt").read_bytes()
    exit_code = int((path / key / "exit_code.txt").read_text().strip())
    expected_ids = []
    for line in city_data.decode("utf-8").splitlines()[1:]:
        if line.strip():
            expected_ids.append(str(json.loads(line)["id"]))
    parsed = parse_val3dity_cjseq_stdout(stdout, expected_ids)
    if exit_code not in (0, 1) or (exit_code == 1 and parsed["unit_valid"] is not False):
        raise RuntimeError("unexpected val3dity completion")
    return {"unit_valid": bool(parsed["unit_valid"]), "features": parsed["features"], "exit_code": exit_code}


def _surface_triangles(surfaces: Sequence[RoofSurface]) -> list[np.ndarray]:
    return [triangle for surface in surfaces for triangle in surface.triangles]


def _render_representatives(
    target: AddOnceStore,
    cfg: Mapping[str, Any],
    references: Mapping[str, Sequence[Mapping[str, Any]]],
    combined: Sequence[Mapping[str, Any]],
    c3_surfaces: Mapping[str, Sequence[RoofSurface]],
    c1_c2_source_root: Path,
) -> list[dict[str, Any]]:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from mpl_toolkits.mplot3d.art3d import Poly3DCollection

    manifest_path = REPO / "configs/p2_baselines/c1_c2_feasibility_pilot_finalize_recovery_r4_v1/r3_finalize_source_manifest_v1.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    records = {row["path"]: row for row in manifest["records"]}
    by_key = {(str(row["building_id"]), str(row["method_id"])): row for row in combined}
    source_cache: dict[str, list[RoofSurface]] = {}

    def surfaces_for(bid: str, method: str) -> list[RoofSurface]:
        row = by_key[(bid, method)]
        unit = row.get("source_operation_unit_id") if method != "C3_GS_image" else row.get("operation_unit_id")
        if not unit:
            return []
        if method == "C3_GS_image":
            return list(c3_surfaces.get(str(unit), []))
        if unit in source_cache:
            return source_cache[str(unit)]
        condition, component = str(unit).split("|", 1)
        prefix = f"operations/{condition}/{component}/work/out/"
        matches = [record for path, record in records.items() if path.startswith(prefix) and path.endswith(".jsonl")]
        if len(matches) != 1:
            return []
        record = matches[0]
        data = read_exact(c1_c2_source_root / record["path"], record)
        source_cache[str(unit)] = parse_cityjsonseq_roof_surfaces(data, record["path"])
        return source_cache[str(unit)]

    outputs: list[dict[str, Any]] = []
    for bid in cfg["representative_buildings"]:
        ref = list(references[bid])
        xyz = np.asarray([[float(r["cell_x"]), float(r["cell_y"]), float(r["top_z"])] for r in ref])
        if xyz.size == 0:
            raise RuntimeError(f"representative building lacks UAS cells: {bid}")
        method_surfaces = {method: surfaces_for(bid, method) for method in cfg["scope"]["condition_ids"]}
        all_z = [*xyz[:, 2].tolist(), *[float(p[2]) for values in method_surfaces.values() for tri in _surface_triangles(values) for p in tri]]
        bounds = _bounds(ref)
        zmin, zmax = min(all_z) - 1.0, max(all_z) + 1.0
        fig = plt.figure(figsize=(16, 8), constrained_layout=True)
        labels = [("UAS reference", None), ("C1 LiDAR", "C1_L_upper"), ("C2 MVS", "C2_MVS"), ("C3 GS", "C3_GS_image")]
        for col, (label, method) in enumerate(labels, start=1):
            ax = fig.add_subplot(2, 4, col)
            ax.scatter(xyz[:, 0], xyz[:, 1], c=xyz[:, 2], s=4, cmap="viridis", alpha=0.45)
            if method:
                for tri in _surface_triangles(method_surfaces[method]):
                    closed = np.vstack((tri[:, :2], tri[0, :2]))
                    ax.plot(closed[:, 0], closed[:, 1], color="#d62728", linewidth=1.2)
            ax.set_xlim(bounds[0], bounds[2]); ax.set_ylim(bounds[1], bounds[3]); ax.set_aspect("equal")
            ax.set_title(label); ax.set_xticks([]); ax.set_yticks([])
            ax3 = fig.add_subplot(2, 4, 4 + col, projection="3d")
            ax3.scatter(xyz[:, 0], xyz[:, 1], xyz[:, 2], c=xyz[:, 2], s=2, cmap="viridis", alpha=0.35)
            if method:
                triangles = _surface_triangles(method_surfaces[method])
                if triangles:
                    ax3.add_collection3d(Poly3DCollection(triangles, facecolor="#ff9896", edgecolor="#8c1d18", alpha=0.7, linewidth=0.4))
            ax3.set_xlim(bounds[0], bounds[2]); ax3.set_ylim(bounds[1], bounds[3]); ax3.set_zlim(zmin, zmax)
            ax3.view_init(elev=28, azim=-55); ax3.set_xticks([]); ax3.set_yticks([]); ax3.set_zticks([])
        c3row = by_key[(bid, "C3_GS_image")]
        fig.suptitle(f"{bid} | red=Roofer RoofSurface, points=independent UAS | C3 assoc={c3row.get('association_class')} | final PASS=PENDING")
        relative = f"qualitative/{bid}_C1_C2_C3_roof_comparison_v1.png"
        path = target.path(relative); path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(path, dpi=150); plt.close(fig)
        data = path.read_bytes()
        outputs.append({"path": relative, "bytes": len(data), "sha256": sha256_bytes(data)})
    target.add("results/qualitative_manifest_v1.jsonl", jsonl_bytes(outputs))
    return outputs


def evaluate(
    c3_root: Path,
    score_cells: Path,
    c1_c2_diagnostics: Path,
    c1_c2_source_root: Path,
    output_root: Path,
) -> dict[str, Any]:
    cfg = load_config()
    source, target = AddOnceStore(c3_root), AddOnceStore(output_root)
    prepared = json.loads(target.path("control/prepared_v1.json").read_bytes())
    if prepared.get("status") != "PREPARED":
        raise RuntimeError("prepare checkpoint missing")
    units = parse_jsonl(target.path("freeze/evaluation_units_v1.jsonl").read_bytes())
    unit_records = {row["operation_unit_id"]: row for row in units}
    score_data = read_exact(score_cells, cfg["inputs"]["score_cells"])
    references: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in parse_jsonl(score_data):
        references[str(row["stable_id"])].append(row)
    c1c2 = parse_jsonl(read_exact(c1_c2_diagnostics, cfg["inputs"]["c1_c2_diagnostics"]))
    if len(c1c2) != 102:
        raise RuntimeError("expected exact 102 C1/C2 rows")
    final = json.loads(source.path("control/c3_development_technical_finalized_v1.json").read_bytes())
    c3_rows = parse_jsonl(source.read_verified(final["development_technical_results"]))
    checks = {r["operation_unit_id"]: r for r in parse_jsonl(source.read_verified(final["operation_checks"]))}
    surface_cache: dict[str, list[RoofSurface]] = {}
    g2_cache: dict[str, dict[str, Any]] = {}
    rows: list[dict[str, Any]] = []
    for base in c3_rows:
        bid, unit_id = str(base["building_id"]), base.get("operation_unit_id")
        screen = checks.get(unit_id) if unit_id else None
        g0, g1, g2 = False, False, None
        g3_metrics = None
        g4_metrics = None
        g3_value = False
        g4_value = False
        if screen is not None:
            g0 = bool(screen["G0_generated"])
            g1 = bool(screen["G1_schema_semantic"])
        if unit_id and g0 and g1:
            record = unit_records[unit_id]
            city_data = source.read_verified({
                "path": record["cityjson_relative_path"],
                "bytes": record["bytes"],
                "sha256": record["sha256"],
            })
            if unit_id not in surface_cache:
                surface_cache[unit_id] = parse_cityjsonseq_roof_surfaces(city_data, record["cityjson_relative_path"])
                g2_cache[unit_id] = _g2_result(target.path("g2"), unit_id, city_data)
            surfaces = surface_cache[unit_id]
            ref = references[bid]
            g2 = g2_cache[unit_id]["unit_valid"]
            g3_metrics = evaluate_g3(ref, surfaces, _bounds(ref), cfg)
            g3_value = bool(g3_metrics["G3_roof_structure_acceptable"])
            g4_metrics = continuous_metrics(ref, surfaces)
            g4_value = g4_candidate(g4_metrics, cfg)
        candidate_pass = bool(g0 and g1 and g2 is True and g3_value and g4_value)
        rows.append({
            **base,
            "G0_generated_evaluation": g0,
            "G1_schema_semantic_evaluation": g1,
            "G2_geometry_topology_valid": g2,
            "G3_metrics": g3_metrics,
            "G3_candidate": g3_value,
            "G4_metrics": g4_metrics,
            "G4_candidate": g4_value,
            "PASS_candidate": candidate_pass,
            "G3_roof_structure_acceptable": None,
            "G4_geometric_accuracy_acceptable": None,
            "PASS_usable": None,
            "criterion_status": "DIAGNOSTIC_CANDIDATE_NOT_FROZEN",
            "scientific_verdict": None,
        })
    if len(rows) != 51:
        raise RuntimeError("expected exact 51 C3 rows")
    combined: list[dict[str, Any]] = []
    for row in c1c2:
        g3 = (row.get("G3_metrics") or {}).get("G3_roof_structure_acceptable")
        g4 = (row.get("G4_metrics_reused_exact") or {}).get("diagnostic_candidate")
        combined.append({**row, "G3_candidate": g3, "G4_candidate": g4,
                         "PASS_candidate": bool(row.get("G0_generated") is True and row.get("G1_schema_semantic") is True and row.get("G2_geometry_topology_valid") is True and g3 is True and g4 is True) if row["method_id"] == "C2_MVS" else None})
    combined.extend(rows)
    target.add("results/c3_development_diagnostics_v1.jsonl", jsonl_bytes(rows))
    target.add("results/three_condition_development_diagnostics_v1.jsonl", jsonl_bytes(combined))
    summary_rows = []
    for method in cfg["scope"]["condition_ids"]:
        subset = [row for row in combined if row["method_id"] == method]
        summary_rows.append({
            "method_id": method,
            "rows": len(subset),
            "G0_true": sum((r.get("G0_generated_evaluation", r.get("G0_generated"))) is True for r in subset),
            "G1_true": sum((r.get("G1_schema_semantic_evaluation", r.get("G1_schema_semantic"))) is True for r in subset),
            "G2_true": sum(r.get("G2_geometry_topology_valid") is True for r in subset),
            "G3_candidate_true": sum(r.get("G3_candidate") is True for r in subset),
            "G4_candidate_true": sum(r.get("G4_candidate") is True for r in subset),
            "PASS_candidate_true": sum(r.get("PASS_candidate") is True for r in subset),
            "PASS_usable": None,
        })
    target.add("results/three_condition_summary_v1.jsonl", jsonl_bytes(summary_rows))
    qualitative = _render_representatives(
        target, cfg, references, combined, surface_cache, c1_c2_source_root
    )
    body = {
        "schema": "jointbuildgs.c3_dev_diagnostics.finalized.v1",
        "status": "DIAGNOSTICS_COMPLETE",
        "rows": 153,
        "c3_rows": 51,
        "unique_c3_cityjson_reads": len(surface_cache),
        "c3_val3dity_units": len(g2_cache),
        "qualitative_panels": len(qualitative),
        "summary": summary_rows,
        "G3_G4_threshold_status": "CANDIDATE_NOT_FROZEN",
        "PASS_usable": None,
        "validation_accesses": 0,
        "held_out_accesses": 0,
        "reconstruction_invocations": 0,
        "roofer_invocations": 0,
        "scientific_verdict": None,
    }
    target.add_json("control/finalized_v1.json", body)
    return body


__all__ = ["continuous_metrics", "evaluate", "g4_candidate", "load_config", "prepare"]
