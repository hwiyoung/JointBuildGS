"""Audit the sealed C1 Roofer result without rerunning reconstruction or Roofer."""

from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Mapping

from scripts.p2_baselines.c1_c2_feasibility_pilot_v1.contract import AddOnceStore, jsonl_bytes, sha256_bytes
from src.evaluation.c1_c2_dev_gate_closure_v1.evaluator import (
    _metric_rows,
    _read_source_record,
    cityjsonseq_feature_ids,
    evaluate_g3,
    evaluate_g4,
    load_config,
    parse_cityjsonseq_roof_surfaces,
    parse_val3dity_cjseq_stdout,
)


C1_RELATIVE = "operations/C1_L_upper/C1_L_upper_COMP_84a837b5d7c79565f0e8/work/out/690792_5335864.city.jsonl"
REFERENCE_RELATIVE = "freeze/development_score_cells_v1.jsonl"
UNIT_ID = "C1_L_upper|C1_L_upper_COMP_84a837b5d7c79565f0e8"


def _jsonl(data: bytes) -> list[dict[str, Any]]:
    return [json.loads(line) for line in data.decode("utf-8").splitlines() if line.strip()]


def _bool(value: Any) -> bool:
    return str(value).strip().lower() in {"true", "1"}


def _summary(rows: list[Mapping[str, Any]], unit_valid: bool) -> dict[str, Any]:
    return {
        "schema": "jointbuildgs.c1_baseline_audit.summary.v1",
        "status": "DIAGNOSTICS_COMPLETE_SELF_REFERENCE",
        "buildings": len(rows),
        "unique_roofer_outputs": 1,
        "building_level_independent_outputs": 0,
        "G0_true": sum(row["G0_generated"] is True for row in rows),
        "G1_true": sum(row["G1_schema_semantic"] is True for row in rows),
        "G2_unique_unit_valid": unit_valid,
        "G2_inherited_true": sum(row["G2_geometry_topology_valid"] is True for row in rows),
        "G3_self_reference_candidate_true": sum(row["G3_self_reference_candidate"] is True for row in rows),
        "G4_self_reference_candidate_true": sum(row["G4_self_reference_candidate"] is True for row in rows),
        "PASS_self_reference_candidate_true": sum(row["PASS_self_reference_candidate"] is True for row in rows),
        "G3_roof_structure_acceptable": None,
        "G4_geometric_accuracy_acceptable": None,
        "PASS_usable": None,
        "scientific_verdict": None,
        "reconstruction_invocations": 0,
        "roofer_invocations": 0,
        "validator_invocations": 1,
    }


def run(
    source_root: Path,
    g2_stdout: Path,
    g2_exit_code: Path,
    output_root: Path,
) -> dict[str, Any]:
    target = AddOnceStore(output_root)
    config = load_config()
    manifest = json.loads(Path(config["inputs"]["source_manifest"]["path"]).read_text(encoding="utf-8"))
    records = {str(record["path"]): record for record in manifest["records"]}
    city_data = _read_source_record(source_root, records[C1_RELATIVE])
    references = _jsonl(_read_source_record(source_root, records[REFERENCE_RELATIVE]))

    stdout = g2_stdout.read_bytes()
    expected_ids = cityjsonseq_feature_ids(city_data)
    g2 = parse_val3dity_cjseq_stdout(stdout, expected_ids)
    exit_code = int(g2_exit_code.read_text(encoding="utf-8").strip())
    if exit_code not in (0, 1) or (exit_code == 1 and g2["unit_valid"] is not False):
        raise RuntimeError("C1 val3dity did not terminate as a recognized validation result")

    surfaces = parse_cityjsonseq_roof_surfaces(city_data, C1_RELATIVE)
    by_building: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in references:
        by_building[str(row["stable_id"])].append(row)

    scope_path = Path(config["inputs"]["development_score_scope"]["path"])
    scope = {row["stable_id"]: row for row in csv.DictReader(scope_path.read_text(encoding="utf-8").splitlines())}
    metrics = [row for row in _metric_rows(config) if row["method_id"] == "C1_L_upper"]
    if len(metrics) != 51 or {row["operation_unit_id"] for row in metrics} != {UNIT_ID}:
        raise RuntimeError("sealed C1 development scope is not the expected 51 rows over one output")

    output_rows: list[dict[str, Any]] = []
    for metric in metrics:
        building_id = str(metric["building_id"])
        scope_row = scope[building_id]
        bounds = [float(scope_row[name]) for name in ("bbox_min_x", "bbox_min_y", "bbox_max_x", "bbox_max_y")]
        g3_metrics = evaluate_g3(by_building[building_id], surfaces, bounds, config)
        g3_candidate = bool(g3_metrics["G3_roof_structure_acceptable"])
        g4_candidate, g4_metrics, g4_reason = evaluate_g4(metric, config)
        g0, g1, unit_valid = _bool(metric["G0_generated"]), _bool(metric["G1_schema_semantic"]), bool(g2["unit_valid"])
        output_rows.append({
            "schema": "jointbuildgs.c1_baseline_audit.row.v1",
            "building_id": building_id,
            "group_id": metric["group_id"],
            "split": "development",
            "method_id": "C1_L_upper",
            "input_role": "CURRENT_UAS_LIDAR_DIRECT_ROOFER_BASELINE",
            "reference_provenance": "SELF_REFERENCE_UPPER_BASELINE",
            "source_operation_unit_id": UNIT_ID,
            "building_level_independent_output": False,
            "G0_generated": g0,
            "G1_schema_semantic": g1,
            "G2_geometry_topology_valid": unit_valid,
            "G2_inheritance": "ONE_SHARED_CITYJSONSEQ_UNIT_TO_51_BUILDINGS",
            "G3_self_reference_candidate": g3_candidate,
            "G3_metrics": g3_metrics,
            "G3_roof_structure_acceptable": None,
            "G4_self_reference_candidate": g4_candidate,
            "G4_metrics": g4_metrics,
            "G4_missing_reason": g4_reason,
            "G4_geometric_accuracy_acceptable": None,
            "PASS_self_reference_candidate": bool(g0 and g1 and unit_valid and g3_candidate and g4_candidate),
            "PASS_usable": None,
            "null_reason": "C1_INPUT_AND_UAS_GEOMETRY_REFERENCE_SHARE_LINEAGE;G3_G4_THRESHOLDS_NOT_FROZEN",
            "scientific_verdict": None,
        })

    summary = _summary(output_rows, bool(g2["unit_valid"]))
    target.add("results/c1_baseline_audit_v1.jsonl", jsonl_bytes(output_rows))
    target.add_json("results/c1_baseline_summary_v1.json", summary)
    target.add_json("control/finalized_v1.json", {
        **summary,
        "c1_cityjson": {"path": C1_RELATIVE, "bytes": len(city_data), "sha256": sha256_bytes(city_data)},
        "g2_stdout": {"bytes": len(stdout), "sha256": sha256_bytes(stdout)},
        "g2_exit_code": exit_code,
        "reference_rows": len(references),
    })
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--g2-stdout", type=Path, required=True)
    parser.add_argument("--g2-exit-code", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.source_root, args.g2_stdout, args.g2_exit_code, args.output_root), sort_keys=True))


if __name__ == "__main__":
    main()

