#!/usr/bin/env python3
"""Build the one canonical qualitative/quantitative C1-C4 result package."""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import io
import json
from pathlib import Path
from typing import Any, Mapping

from scripts.p2.selected10_c1_c4_presentation_v1.render import (
    record,
    run as render_presentation,
    sha256_file,
    verify_exact,
    write_json,
    write_new,
)
from scripts.p2.utarget199_c1_c4_matrix_v1.render import condition_tables, postprocess_tables
from scripts.p2.utarget199_contract_results_v1.render_case_sheets import city_file


REPO = Path(__file__).resolve().parents[3]
CONFIG_PATH = REPO / "configs/p2/canonical_c1_c4_results_v1/canonical_v1.json"
CONDITIONS = (
    "C1_L_upper",
    "C2_MVS",
    "C3_GS_image_SEALED",
    "C3_1_SEM_MATCHED",
    "C3_2_SEM_DEPTH_MATCHED",
    "C4_EXISTING_ALS_MATCHED",
)
METRICS = (
    "RMSXY_m",
    "RMSZ_m",
    "surface_distance_rmse_m",
    "surface_distance_p95_m",
    "height_error_mae_m",
    "height_error_signed_median_m",
    "normal_angular_error_median_deg",
    "normal_angular_error_p95_deg",
    "reference_vertical_coverage",
    "vertically_scored_cell_count",
)


def load_config(path: Path = CONFIG_PATH) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def validate_config(config: Mapping[str, Any]) -> None:
    if config.get("schema") != "jointbuildgs.p2.canonical_c1_c4_results.v1":
        raise RuntimeError("unexpected canonical result schema")
    if config.get("status") != "CANONICAL_REPRODUCIBLE_RESULTS_CONTRACT":
        raise RuntimeError("canonical result contract is inactive")
    if tuple(config["condition_order"]) != CONDITIONS:
        raise RuntimeError("canonical condition order drifted")
    if config.get("success_predicate") != "G0_GENERATED_TRUE_AND_ONE_TO_ONE_BUILDING_COMPONENT_TRUE":
        raise RuntimeError("canonical success predicate drifted")
    if len(config["building_ids"]) != 10 or set(config["selection_roles"]) != set(config["building_ids"]):
        raise RuntimeError("canonical selected-10 membership/role drifted")
    presentation = config["presentation"]
    if presentation["oracle_results_allowed_in_main_comparison"] is not False:
        raise RuntimeError("oracle results cannot enter the main comparison")
    if presentation["oracle_projection_support_only"] is not True:
        raise RuntimeError("oracle projection-support boundary drifted")
    if config["determinism"]["pdf_metadata_epoch"] != 0:
        raise RuntimeError("canonical PDF epoch drifted")
    if config.get("official_G3_G4_PASS_usable", "missing") is not None or config.get("scientific_verdict", "missing") is not None:
        raise RuntimeError("official PASS and scientific verdict must remain null")


def jsonl_bytes(rows: list[Mapping[str, Any]]) -> bytes:
    return b"".join(
        (json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
        for row in rows
    )


def csv_bytes(rows: list[Mapping[str, Any]], fields: tuple[str, ...]) -> bytes:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n", extrasaction="raise")
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode("utf-8")


def success(row: Mapping[str, Any]) -> bool:
    return row.get("G0_generated") is True and row.get("one_to_one_building_component") is True


def file_binding(path: Path | None, cache: dict[Path, dict[str, Any]]) -> dict[str, Any] | None:
    if path is None or not path.is_file():
        return None
    if path not in cache:
        size, digest = sha256_file(path)
        cache[path] = {"path": path.as_posix(), "bytes": size, "sha256": digest}
    return cache[path]


def build_tables(
    output_root: Path,
    artifact_root: Path,
    config: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, Any], dict[str, Any]]:
    sources = config["sources"]
    hashes = config["exact_hashes"]
    c12_root = artifact_root / sources["c1_c2_contract_relative_root"]
    c3_root = artifact_root / sources["c3_postprocess_relative_root"]
    c4_root = artifact_root / sources["c4_postprocess_relative_root"]
    source_checks = {
        "c1_c2_metrics": verify_exact(c12_root / "results/building_method_metrics_v1.jsonl", hashes["c1_c2_metric_sha256"], "C1/C2/sealed-C3 metrics"),
        "c3_metrics": verify_exact(c3_root / "results/building_condition_metrics_v1.jsonl", hashes["c3_metric_sha256"], "matched C3 metrics"),
        "c4_metrics": verify_exact(c4_root / "results/building_c4_metrics_v1.jsonl", hashes["c4_metric_sha256"], "matched C4 metrics"),
        "c1_c2_finalized": verify_exact(c12_root / "control/finalized_v1.json", hashes["c1_c2_finalized_sha256"], "C1/C2 finalized receipt"),
        "c3_finalized": verify_exact(c3_root / "control/finalized_v1.json", hashes["c3_finalized_sha256"], "C3 finalized receipt"),
        "c4_closure": verify_exact(c4_root / "control/300-closed.local_v1.json", hashes["c4_closure_sha256"], "C4 closure"),
        "c3_1_checkpoint": verify_exact(artifact_root / sources["c3_1_checkpoint_relative_path"], hashes["c3_1_checkpoint_sha256"], "C3-1 checkpoint"),
        "c3_2_checkpoint": verify_exact(artifact_root / sources["c3_checkpoint_relative_path"], hashes["c3_checkpoint_sha256"], "C3-2 checkpoint"),
        "c4_checkpoint": verify_exact(artifact_root / sources["c4_checkpoint_relative_path"], hashes["c4_checkpoint_sha256"], "C4 checkpoint"),
        "current_uas_reference": verify_exact(artifact_root / sources["current_uas_reference_relative_path"], hashes["current_uas_reference_sha256"], "current UAS reference"),
        "c3_mesh_receipt": verify_exact(artifact_root / sources["c3_mesh_diagnostic_relative_root"] / "control/extraction_pair_complete_v1.json", hashes["c3_mesh_receipt_sha256"], "C3 mesh receipt"),
    }
    lod2_paths = [artifact_root / value for value in sources["lod2_relative_paths"]]
    source_checks["lod2"] = [verify_exact(path, digest, "LoD2") for path, digest in zip(lod2_paths, hashes["lod2_sha256"])]

    c12, c12_units = condition_tables(c12_root, "building_method_metrics", "method_id")
    c3_1, c3_units = postprocess_tables(c3_root, "building_condition_metrics", "C3_1_SEM")
    c3_2, c3_units_2 = postprocess_tables(c3_root, "building_condition_metrics", "C3_2_SEM_DEPTH")
    c4, c4_units = postprocess_tables(c4_root, "building_c4_metrics", "C4_EXISTING_ALS")
    if c3_units.keys() != c3_units_2.keys():
        raise RuntimeError("matched C3 unit bindings differ by condition load")
    population = sorted(c4)
    if len(population) != 199:
        raise RuntimeError(f"canonical population differs from 199: {len(population)}")
    if not set(config["building_ids"]).issubset(population):
        raise RuntimeError("canonical selected buildings are outside U_target")

    file_cache: dict[Path, dict[str, Any]] = {}
    long_rows: list[dict[str, Any]] = []
    row_lookup: dict[tuple[str, str], Mapping[str, Any]] = {}
    condition_sources = {
        "C1_L_upper": (lambda building: c12[(building, "C1_L_upper")], c12_units, c12_root, hashes["c1_c2_metric_sha256"]),
        "C2_MVS": (lambda building: c12[(building, "C2_MVS")], c12_units, c12_root, hashes["c1_c2_metric_sha256"]),
        "C3_GS_image_SEALED": (lambda building: c12[(building, "C3_GS_image")], c12_units, c12_root, hashes["c1_c2_metric_sha256"]),
        "C3_1_SEM_MATCHED": (lambda building: c3_1[building], c3_units, c3_root, hashes["c3_metric_sha256"]),
        "C3_2_SEM_DEPTH_MATCHED": (lambda building: c3_2[building], c3_units, c3_root, hashes["c3_metric_sha256"]),
        "C4_EXISTING_ALS_MATCHED": (lambda building: c4[building], c4_units, c4_root, hashes["c4_metric_sha256"]),
    }
    for building_id in population:
        for condition_id in CONDITIONS:
            getter, units, source_root, metric_hash = condition_sources[condition_id]
            row = getter(building_id)
            row_lookup[(building_id, condition_id)] = row
            operation_id = row.get("operation_unit_id")
            unit = units.get(operation_id) if operation_id else None
            work = source_root / unit["work_directory"] if unit else None
            input_binding = file_binding(work / "input.las" if work else None, file_cache)
            output_path = city_file(source_root / unit["output_directory"]) if unit else None
            output_binding = file_binding(output_path, file_cache)
            current = row.get("current_uas_metrics") or row.get("continuous_metrics") or {}
            lod2 = row.get("lod2_2022_metrics") or {}
            failure = row.get("failure_reasons") or row.get("failure_or_missing_reason") or []
            if isinstance(failure, str):
                failure = [failure]
            flat: dict[str, Any] = {
                "building_id": building_id,
                "condition_id": condition_id,
                "source_condition_id": config["condition_binding"][condition_id]["source_condition"],
                "selection_role": config["selection_roles"].get(building_id),
                "association_status": row.get("association_status"),
                "component_G0_generated": row.get("component_G0_generated"),
                "G0_generated": row.get("G0_generated"),
                "G1_schema_semantic": row.get("G1_schema_semantic"),
                "G2_geometry_topology_valid": row.get("G2_geometry_topology_valid"),
                "one_to_one_building_component": row.get("one_to_one_building_component"),
                "building_level_success": success(row),
                "operation_unit_id": operation_id,
                "input_sha256": None if input_binding is None else input_binding["sha256"],
                "component_output_sha256": None if output_binding is None else output_binding["sha256"],
                "displayed_as_building_output": success(row),
                "metric_file_sha256": metric_hash,
                "current_reference_sha256": hashes["current_uas_reference_sha256"],
                "current_reference_role": config["condition_binding"][condition_id]["reference_role"],
                "lod2_reference_sha256": "|".join(hashes["lod2_sha256"]) if condition_id == "C4_EXISTING_ALS_MATCHED" else None,
                "lod2_reference_role": row.get("lod2_reference_role"),
                "lod2_reference_status": row.get("lod2_reference_status"),
                "failure_or_missing_reasons": "|".join(str(value) for value in failure),
                "official_PASS_usable": None,
                "scientific_verdict": None,
            }
            for metric in METRICS:
                flat[f"current_{metric}"] = current.get(metric)
                flat[f"lod2_{metric}"] = lod2.get(metric) if condition_id == "C4_EXISTING_ALS_MATCHED" else None
            long_rows.append(flat)

    success_counts = {
        condition: sum(success(row_lookup[(building, condition)]) for building in population)
        for condition in CONDITIONS
    }
    both_baselines_fail = [
        building for building in population
        if not success(row_lookup[(building, "C1_L_upper")]) and not success(row_lookup[(building, "C2_MVS")])
    ]
    transitions = {
        condition: [
            building for building in both_baselines_fail
            if success(row_lookup[(building, condition)])
        ]
        for condition in CONDITIONS[2:]
    }
    summary = {
        "schema": "jointbuildgs.p2.canonical_c1_c4_results.population_summary.v1",
        "population_count": len(population),
        "condition_order": list(CONDITIONS),
        "success_predicate": config["success_predicate"],
        "building_level_success_counts": success_counts,
        "c1_and_c2_both_fail_count": len(both_baselines_fail),
        "c1_c2_both_fail_to_condition_success_ids": transitions,
        "selected_building_ids": list(config["building_ids"]),
        "selection_roles": config["selection_roles"],
        "official_PASS_usable": None,
        "scientific_verdict": None,
    }
    fields = tuple(long_rows[0].keys())
    write_new(output_root / "results/population_condition_metrics_long_v1.jsonl", jsonl_bytes(long_rows))
    write_new(output_root / "results/population_condition_metrics_long_v1.csv", csv_bytes(long_rows, fields))
    write_json(output_root / "results/population_transition_summary_v1.json", summary)
    return long_rows, summary, source_checks


def run(
    output_root: Path,
    artifact_root: Path,
    source_commit: str,
    run_id: str,
    config_path: Path = CONFIG_PATH,
    determinism_probe_building_id: str | None = None,
) -> dict[str, Any]:
    config = load_config(config_path)
    validate_config(config)
    if output_root.exists() and any(output_root.iterdir()):
        raise RuntimeError("fresh add-once canonical result namespace required")
    output_root.mkdir(parents=True, exist_ok=True)
    presentation_root = output_root / "presentation"
    render_presentation(
        presentation_root,
        artifact_root,
        source_commit,
        run_id,
        determinism_probe_building_id,
        config_path,
    )
    long_rows, summary, source_checks = build_tables(output_root, artifact_root, config)
    report = (
        "# Canonical C1-C4 qualitative/quantitative results v1\n\n"
        "This is the only canonical selected-10 presentation and U_target=199 quantitative packaging path. "
        "The main comparison uses honest C1/C2 results. The GT-footprint oracle is used only as current C1 projection support. "
        "Sealed C3_GS_image and matched C3-1/C3-2 remain distinct conditions. Building-level success is exactly "
        "`G0_generated=true AND one_to_one_building_component=true`. Missing, not-run, failure and null values are retained.\n\n"
        f"Population success counts: `{json.dumps(summary['building_level_success_counts'], sort_keys=True)}`.\n\n"
        "No GS training, Roofer, TSDF or metric recomputation is performed. official PASS_usable and scientific_verdict remain null.\n"
    )
    write_new(output_root / "reports/README.md", report.encode("utf-8"))
    write_new(
        output_root / "reports/index.html",
        (
            "<!doctype html><html lang='ko'><meta charset='utf-8'><title>JointBuildGS canonical results</title>"
            "<style>body{font-family:sans-serif;max-width:1200px;margin:auto;line-height:1.5}</style>"
            "<h1>JointBuildGS canonical C1-C4 results v1</h1>"
            "<p>Main comparison: honest C1/C2; oracle: projection support only; sealed C3 and matched C3 controls are distinct.</p>"
            "<ul><li><a href='../presentation/reports/P2_SELECTED10_C1_C2_C3_2_C4_17row_4view_v1.pdf'>10-building PDF</a></li>"
            "<li><a href='../presentation/reports/index.html'>qualitative HTML gallery</a></li>"
            "<li><a href='../results/population_condition_metrics_long_v1.csv'>199-building quantitative CSV</a></li>"
            "<li><a href='../results/population_transition_summary_v1.json'>transition summary</a></li></ul>"
        ).encode("utf-8"),
    )

    deterministic_material = [
        path for path in sorted(output_root.rglob("*"))
        if path.is_file()
        and "/control/" not in path.as_posix()
        and not path.relative_to(output_root).as_posix().startswith("presentation/control/")
    ]
    content_manifest = {
        "schema": "jointbuildgs.p2.canonical_c1_c4_results.content_manifest.v1",
        "status": "CONTENT_HASHED_DETERMINISTIC",
        "source_commit": source_commit,
        "config": record(config_path, REPO),
        "population_long_row_count": len(long_rows),
        "selected_page_count": 1 if determinism_probe_building_id else 10,
        "records": [record(path, output_root) for path in deterministic_material],
        "source_checks": source_checks,
        "official_PASS_usable": None,
        "scientific_verdict": None,
    }
    write_json(output_root / "control/content_manifest_v1.json", content_manifest)
    execution = {
        "schema": "jointbuildgs.p2.canonical_c1_c4_results.execution_receipt.v1",
        "status": "DETERMINISM_PROBE_COMPLETE" if determinism_probe_building_id else "CANONICAL_BUILD_COMPLETE",
        "run_id": run_id,
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "source_commit": source_commit,
        "determinism_probe_building_id": determinism_probe_building_id,
        "content_manifest": record(output_root / "control/content_manifest_v1.json", output_root),
        "gs_training_invocations": 0,
        "roofer_invocations": 0,
        "tsdf_invocations": 0,
        "metric_recomputations": 0,
        "official_PASS_usable": None,
        "scientific_verdict": None,
    }
    write_json(output_root / "control/execution_receipt_v1.json", execution)
    return execution


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--config", type=Path, default=CONFIG_PATH)
    parser.add_argument("--determinism-probe-building-id")
    args = parser.parse_args()
    print(json.dumps(run(args.output_root, args.artifact_root, args.source_commit, args.run_id, args.config, args.determinism_probe_building_id), sort_keys=True))


if __name__ == "__main__":
    main()
