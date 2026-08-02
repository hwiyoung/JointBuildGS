#!/usr/bin/env python3
"""Promote the exact qualitative backfill summary without reopening render inputs.

The promotion container receives only the repository and the new external output
namespace.  This module reads the renderer's technical manifest, reuses the output
digests already recorded there, and creates four task-owned Git outputs add-once.
It never opens a PNG, R3 payload, compact reference CSV, or historical result source.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
import re
import subprocess
from collections import Counter
from pathlib import Path
from typing import Any, Mapping, Sequence


TASK_ID = "P2-C1-C2-QUALITATIVE-EVALUATOR-BACKFILL-v1"
HANDOFF_ID = "P2-W2C-C1-C2-QUALITATIVE-EVALUATOR-BACKFILL-v1"
CONFIG_RELATIVE = "configs/p2_baselines/c1_c2_qualitative_evaluator_backfill_v1/render_v1.json"
ACCEPTED_RECEIPT_RELATIVE = f"artifacts/manifests/handoffs/{HANDOFF_ID}/100-accepted.json"
R3_RELATIVE = "phase-payloads/p2-baselines/c1_c2_feasibility_pilot_recovery_r3_v1/P2-C1-C2-FEASIBILITY-PILOT-RECOVERY-R3-v1"
PENDING_REASON = "CRITERION_NOT_FROZEN_G2_G3_G4_UNAVAILABLE"
ABSENT_ID = "DEBY_LOD2_4907183"
PARTIAL_IDS = (
    "DEBY_LOD2_4907177",
    "DEBY_LOD2_4907180",
    "DEBY_LOD2_4907176",
    "DEBY_LOD2_4906965",
)
ELIGIBILITY = {
    "P1": ("DEBY_LOD2_4959324", True, 5, 228, 97, 87, "PASS_ALL_INPUT_SUPPORT_RULES"),
    "P2": ("DEBY_LOD2_4959793", True, 97, 241, 282, 193, "PASS_ALL_INPUT_SUPPORT_RULES"),
    "P3": ("DEBY_LOD2_4959460", True, 3543, 399, 8842, 6740, "PASS_ALL_INPUT_SUPPORT_RULES"),
    "F1": ("DEBY_LOD2_4907184", False, 3, 186, 521, 451, "INSUFFICIENT_INDEPENDENT_UAS_REFERENCE_SUPPORT"),
    "F2": ("DEBY_LOD2_4907034", False, 0, 61, 0, 574, "INSUFFICIENT_INDEPENDENT_UAS_REFERENCE_SUPPORT;INSUFFICIENT_MVS_SUPPORT"),
    "F3": ("DEBY_LOD2_4908166", False, 0, 85, 40, 3, "INSUFFICIENT_INDEPENDENT_UAS_REFERENCE_SUPPORT;INSUFFICIENT_C4_SUPPORT"),
    "F4": ("DEBY_LOD2_4908164", False, 0, 63, 0, 0, "INSUFFICIENT_INDEPENDENT_UAS_REFERENCE_SUPPORT;INSUFFICIENT_MVS_SUPPORT;INSUFFICIENT_C4_SUPPORT"),
}


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def _csv_bytes(fields: Sequence[str], rows: Sequence[Mapping[str, Any]]) -> bytes:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=list(fields), lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode("utf-8")


def _record(path: str, data: bytes) -> dict[str, Any]:
    return {"path": path, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def _safe_path(root: Path, relative: str) -> Path:
    value = Path(relative)
    if value.is_absolute() or ".." in value.parts:
        raise RuntimeError(f"unsafe promotion path: {relative}")
    root = root.resolve()
    result = (root / value).resolve()
    if root not in result.parents:
        raise RuntimeError(f"promotion path escaped repository: {relative}")
    return result


def _add_once(root: Path, relative: str, data: bytes) -> dict[str, Any]:
    path = _safe_path(root, relative)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    directory_fd = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)
    return _record(relative, data)


def _git(repo_root: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo_root), *args], check=True, capture_output=True, text=True).stdout.strip()


def _valid_output_record(value: Mapping[str, Any]) -> None:
    if not re.fullmatch(r"[0-9a-f]{64}", str(value.get("sha256", ""))):
        raise RuntimeError("external output record has an invalid digest")
    if int(value.get("bytes", -1)) <= 0 or not str(value.get("path", "")):
        raise RuntimeError("external output record is incomplete")


def _validate_accepted_receipt(
    *,
    repo_root: Path,
    promotion_parent_commit: str,
    project_image_id: str,
    accepted_records: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    receipt_path = _safe_path(repo_root, ACCEPTED_RECEIPT_RELATIVE)
    if receipt_path.is_symlink() or not receipt_path.is_file():
        raise RuntimeError("exact 100-accepted receipt is absent or symlinked")
    receipt_bytes = receipt_path.read_bytes()
    receipt = json.loads(receipt_bytes)
    if (
        receipt.get("schema") != "jointbuildgs.two_host_handoff.v1" or receipt.get("template_only") is not False
        or receipt.get("handoff_id") != HANDOFF_ID or receipt.get("task_id") != TASK_ID
        or receipt.get("state") != "accepted" or receipt.get("direction") != "work_to_experiment"
        or receipt.get("sender_role") != "work_host" or receipt.get("receiver_role") != "experiment_host"
        or receipt.get("transport", {}).get("exclusive_writer_ack") is not True
        or receipt.get("commits", {}).get("receipt_head") != "SELF"
        or receipt.get("receiver_ack", {}).get("role") != "experiment_host"
        or receipt.get("receiver_ack", {}).get("status") != "accepted"
        or receipt.get("verification", {}).get("docker_image_digest") != project_image_id
        or receipt.get("scientific", {}).get("scientific_verdict") is not None
    ):
        raise RuntimeError("exact 100-accepted authority fields mismatch")
    receipt_commit = _git(repo_root, "log", "-1", "--format=%H", "--", ACCEPTED_RECEIPT_RELATIVE)
    if receipt_commit != promotion_parent_commit:
        raise RuntimeError("100-accepted receipt is not owned by the exact promotion parent commit")
    pre_name = "exact 25-record pre-push SHA-256 verification"
    post_name = "exact 25-record post-push SHA-256 verification"
    tests = list(receipt["verification"].get("tests", []))
    pre = [row for row in tests if row.get("name") == pre_name]
    post = [row for row in tests if row.get("name") == post_name]
    if len(pre) != 1 or pre[0].get("passed") != 25 or pre[0].get("failed") != 0:
        raise RuntimeError("accepted receipt exact 25-record pre-push proof mismatch")
    if len(post) != 1 or post[0].get("passed") != 25 or post[0].get("failed") != 0:
        raise RuntimeError("accepted receipt exact 25-record post-push proof mismatch")
    commands = [str(value).upper() for value in receipt["verification"].get("commands", [])]
    if not any("PRE-PUSH" in value and "EXACT 25-RECORD ALLOWLIST" in value for value in commands):
        raise RuntimeError("accepted receipt lacks exact allowlist PRE-PUSH command evidence")
    if not any("POST-PUSH" in value and "EXACT 25-RECORD ALLOWLIST" in value for value in commands):
        raise RuntimeError("accepted receipt lacks exact allowlist POST-PUSH command evidence")
    expected = set()
    for row in accepted_records:
        source = row.get("source")
        if source == "R3":
            relative = f"{R3_RELATIVE}/{row['path']}"
        elif source == "COMPACT_REFERENCE":
            relative = str(row["path"])
        else:
            raise RuntimeError("accepted artifact record has an unknown source class")
        expected.add((f"artifact://JointBuildGS/{relative}", int(row["bytes"]), str(row["sha256"])))
    artifact_rows = list(receipt.get("artifacts", {}).get("records", []))
    observed = {(row.get("uri"), int(row.get("bytes", -1)), row.get("sha256")) for row in artifact_rows}
    if len(expected) != 25 or len(artifact_rows) != 25 or observed != expected:
        raise RuntimeError("accepted receipt artifact records differ from exact 25-record allowlist")
    for row in artifact_rows:
        if (
            row.get("verification_method") != "sha256_rehash" or row.get("verified_by") != "experiment_host"
            or not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[^ ]+", str(row.get("verified_at", "")))
        ):
            raise RuntimeError("accepted receipt artifact verification provenance mismatch")
    pre_count = int(pre[0]["passed"])
    post_count = int(post[0]["passed"])
    return {
        "path": ACCEPTED_RECEIPT_RELATIVE,
        "commit": receipt_commit,
        "bytes": len(receipt_bytes),
        "sha256": hashlib.sha256(receipt_bytes).hexdigest(),
        "artifact_record_count": len(artifact_rows),
        "pre_push_sha256_verifications": pre_count,
        "post_push_sha256_verifications": post_count,
        "sha256_verifications_total": pre_count + post_count,
    }


def _validate_external(manifest: Mapping[str, Any]) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    if manifest.get("schema") != "jointbuildgs.c1_c2_fixed_view_qualitative_manifest.v1":
        raise RuntimeError("external renderer manifest schema mismatch")
    if manifest.get("task_id") != TASK_ID or manifest.get("status") != "POST_HOC_FIXED_RULE_VISUALIZATION_SUPPLEMENT":
        raise RuntimeError("external renderer task/status mismatch")
    if manifest.get("scientific_verdict") is not None:
        raise RuntimeError("external renderer scientific verdict must remain null")
    sheets = list(manifest.get("case_sheets", []))
    if len(sheets) != 51 or len({row.get("building_id") for row in sheets}) != 51:
        raise RuntimeError("external renderer must contain exact 51 unique case sheets")
    roles = Counter(row.get("selection_role") for row in sheets)
    if roles != Counter({
        "OUTCOME_FREE_PRESELECTED_REPRESENTATIVE": 5,
        "POST_HOC_DIAGNOSTIC_PARTIAL_COVERAGE": 4,
        "POST_HOC_DIAGNOSTIC_UNASSOCIATED_C2_EMPTY": 1,
        "FULL_DEVELOPMENT_ROSTER_DESCRIPTIVE": 41,
    }):
        raise RuntimeError("external case role counts mismatch")
    panels = [(row["building_id"], method, row["methods"][method]) for row in sheets for method in ("C1_L_upper", "C2_MVS")]
    associated = [value for _, _, value in panels if value.get("operation_unit_id")]
    c1 = [value for _, method, value in panels if method == "C1_L_upper" and value.get("operation_unit_id")]
    c2 = [value for _, method, value in panels if method == "C2_MVS" and value.get("operation_unit_id")]
    absent = [(building, value) for building, method, value in panels if method == "C2_MVS" and not value.get("operation_unit_id")]
    if len(panels) != 102 or len(associated) != 101 or len(c1) != 51 or len(c2) != 50:
        raise RuntimeError("external 102/101/51/50 method-panel contract mismatch")
    if len(absent) != 1 or absent[0][0] != ABSENT_ID or absent[0][1].get("empty_reason") != "UNASSOCIATED_CONDITION_COMPONENT":
        raise RuntimeError("external exact C2-absent panel mismatch")
    reads = manifest.get("input_reads", {})
    if (
        reads.get("artifact_allowlist_record_count") != 25
        or reads.get("sealed_association_rows") != 102
        or reads.get("sealed_execution_unit_rows") != 7
        or reads.get("unique_execution_units") != 7
        or reads.get("associated_render_uses") != 101
        or reads.get("duplicate_payload_reads_prevented") != 94
    ):
        raise RuntimeError("external 7/101/94 reuse counters mismatch")
    allowlist_records = list(reads.get("artifact_allowlist_records", []))
    if len(allowlist_records) != 25:
        raise RuntimeError("external accepted artifact allowlist must contain 25 records")
    for record in allowlist_records:
        _valid_output_record(record)
    units = reads.get("units", {})
    if len(units) != 7:
        raise RuntimeError("external manifest lacks seven exact unit read records")
    for records in units.values():
        for key in ("input_las", "r_derived", "cityjsonseq"):
            record = records.get(key, {})
            if record.get("full_read_and_digest_passes") != 1:
                raise RuntimeError(f"external unit {key} natural-read count mismatch")
            _valid_output_record(record)
    scope = manifest.get("scope", {})
    if any(scope.get(key) != 0 for key in (
        "metric_recomputation_count", "roofer_invocation_count", "reconstruction_invocation_count",
        "original_scientific_source_reads_or_hashes", "validation_payload_accesses", "held_out_payload_accesses",
    )):
        raise RuntimeError("external renderer reports a prohibited computation")
    compact = manifest.get("eligibility", {}).get("compact_source_read", {})
    if compact.get("full_read_and_digest_passes") != 1:
        raise RuntimeError("compact reference cells must have exactly one natural read")
    examples = list(manifest.get("eligibility", {}).get("examples", []))
    if len(examples) != 7:
        raise RuntimeError("external eligibility roster must contain seven rows")
    by_label = {row.get("label"): row for row in examples}
    if set(by_label) != set(ELIGIBILITY):
        raise RuntimeError("external eligibility labels mismatch")
    for label, expected in ELIGIBILITY.items():
        row = by_label[label]
        observed = (
            row.get("stable_id"), row.get("candidate"), row.get("recorded_reference_cells"),
            row.get("current_image_views"), row.get("mvs_support_cells"), row.get("c4_support_cells"), row.get("reason"),
        )
        if observed != expected or row.get("actual_compact_rows") != expected[2]:
            raise RuntimeError(f"external eligibility row mismatch: {label}")
    stage = manifest.get("stage_and_coverage_correction", {})
    if stage.get("g0") != {"C1_L_upper": {"numerator": 51, "denominator": 51}, "C2_MVS": {"numerator": 50, "denominator": 51}}:
        raise RuntimeError("external G0 stage mismatch")
    if stage.get("g1") != {"C1_L_upper": {"numerator": 51, "denominator": 51}, "C2_MVS": {"numerator": 50, "denominator": 51}}:
        raise RuntimeError("external provisional G1 stage mismatch")
    for values in stage.get("pending", {}).values():
        for value in values.values():
            if value != {"status": "PENDING", "value": None, "denominator": 51, "reason": PENDING_REASON}:
                raise RuntimeError("external pending-stage contract mismatch")
    correction = stage.get("coverage_correction", {})
    if (
        correction.get("full") != {"numerator": 46, "denominator": 50}
        or correction.get("partial") != {"numerator": 4, "denominator": 50}
        or correction.get("absent") != {"numerator": 1, "denominator": 51}
        or tuple(correction.get("partial_building_ids", [])) != PARTIAL_IDS
        or correction.get("absent_building_id") != ABSENT_ID
    ):
        raise RuntimeError("external 46/4/1 correction mismatch")
    output_rows = list(manifest.get("outputs", []))
    outputs = {row.get("path"): row for row in output_rows}
    if len(output_rows) != 53 or len(outputs) != 53:
        raise RuntimeError("external output record count must be exact 53")
    for row in output_rows:
        _valid_output_record(row)
    required = {row["file"] for row in sheets} | {manifest["eligibility"]["file"], "stage_and_coverage_correction_v1.csv"}
    if set(outputs) != required:
        raise RuntimeError("external output record identities mismatch")
    return examples, outputs


def _stage_csv() -> bytes:
    fields = ["method_id", "denominator", "G0_generated", "provisional_internal_G1", "G2", "G3", "G4", "PASS_usable", "pending_reason"]
    rows = [
        {"method_id": "C1_L_upper", "denominator": 51, "G0_generated": 51, "provisional_internal_G1": 51, "G2": "PENDING", "G3": "PENDING", "G4": "PENDING", "PASS_usable": "PENDING", "pending_reason": PENDING_REASON},
        {"method_id": "C2_MVS", "denominator": 51, "G0_generated": 50, "provisional_internal_G1": 50, "G2": "PENDING", "G3": "PENDING", "G4": "PENDING", "PASS_usable": "PENDING", "pending_reason": PENDING_REASON},
    ]
    return _csv_bytes(fields, rows)


def _eligibility_csv(examples: Sequence[Mapping[str, Any]], uri: str, panel_record: Mapping[str, Any]) -> bytes:
    fields = [
        "label", "stable_id", "candidate", "reference_cells", "current_image_views", "mvs_support_cells", "c4_support_cells",
        "bbox_min_x", "bbox_min_y", "bbox_max_x", "bbox_max_y", "exact_reason", "external_panel_uri", "external_panel_bytes", "external_panel_sha256",
    ]
    rows = []
    for row in examples:
        bbox = row["bbox"]
        rows.append({
            "label": row["label"], "stable_id": row["stable_id"], "candidate": str(row["candidate"]).lower(),
            "reference_cells": row["recorded_reference_cells"], "current_image_views": row["current_image_views"],
            "mvs_support_cells": row["mvs_support_cells"], "c4_support_cells": row["c4_support_cells"],
            "bbox_min_x": bbox[0], "bbox_min_y": bbox[1], "bbox_max_x": bbox[2], "bbox_max_y": bbox[3],
            "exact_reason": row["reason"], "external_panel_uri": f"{uri}{panel_record['path']}",
            "external_panel_bytes": panel_record["bytes"], "external_panel_sha256": panel_record["sha256"],
        })
    return _csv_bytes(fields, rows)


def _supplement_md(manifest: Mapping[str, Any], uri: str, outputs: Mapping[str, Mapping[str, Any]]) -> bytes:
    lines = [
        "# C1/C2 qualitative and evaluator supplement v1",
        "",
        "## Interpretation lock",
        "",
        "This is a post-hoc fixed-rule development visualization supplement. C1 is a self-reference upper baseline; it is not independent-reference accuracy evidence. No metric, eligibility, Roofer, reconstruction, validation, or held-out computation was performed. `scientific_verdict` remains `null`.",
        "",
        "## Stage status",
        "",
        "| Method | Denominator | G0 | Provisional internal G1 | G2 | G3 | G4 | PASS_usable |",
        "|---|---:|---:|---:|---|---|---|---|",
        "| C1_L_upper | 51 | 51 | 51 | PENDING | PENDING | PENDING | PENDING |",
        "| C2_MVS | 51 | 50 | 50 | PENDING | PENDING | PENDING | PENDING |",
        "",
        f"All pending cells carry `{PENDING_REASON}`. No final success count is derived.",
        "",
        "## Additive coverage correction",
        "",
        "The manifest-bound C2 scored surface is 46/50 full and 4/50 partial; one of the 51 denominator rows (`DEBY_LOD2_4907183`) is absent/unscored. The four partial rows are `4907177`, `4907180`, `4907176`, and `4906965`. This additively corrects the protected R4 Return prose phrase `47/50 full`; that Return remains unchanged.",
        "",
        "## Fixed eligibility example panel",
        "",
        f"The seven fixed P1/P2/P3/F1/F2/F3/F4 examples share [{manifest['eligibility']['file']}]({uri}{manifest['eligibility']['file']}). Rectangles are bound spatial bboxes, not roof outlines.",
        "",
        "## Development case-sheet index",
        "",
        "| Building | Role | External sheet | Bytes | SHA-256 |",
        "|---|---|---|---:|---|",
    ]
    for sheet in manifest["case_sheets"]:
        record = outputs[sheet["file"]]
        lines.append(f"| `{sheet['building_id']}` | `{sheet['selection_role']}` | [{sheet['file']}]({uri}{sheet['file']}) | {record['bytes']} | `{record['sha256']}` |")
    lines.extend([
        "",
        "## Limitations",
        "",
        "The sealed operation LAS records contain geometry/classification rather than usable RGB or input normals. Views therefore use fixed height coloring, component roofprint outlines, and sealed CityJSON semantics. G2/G3/G4 and final acceptance remain unavailable.",
        "",
    ])
    return "\n".join(lines).encode("utf-8")


def promote(
    *,
    external_manifest_path: Path,
    repo_root: Path,
    promotion_parent_commit: str,
    source_commit: str,
    project_image_id: str,
    run_id: str,
) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    for value, pattern, label in (
        (promotion_parent_commit, r"[0-9a-f]{40}", "promotion parent commit"),
        (source_commit, r"[0-9a-f]{40}", "source commit"),
        (project_image_id, r"sha256:[0-9a-f]{64}", "project image"),
    ):
        if not re.fullmatch(pattern, value):
            raise RuntimeError(f"invalid exact {label}")
    config = json.loads(_safe_path(repo_root, CONFIG_RELATIVE).read_bytes())
    if (
        config.get("task_id") != TASK_ID or config.get("handoff_id") != HANDOFF_ID
        or config.get("run_id") != run_id or config.get("project_image_id") != project_image_id
    ):
        raise RuntimeError("promotion authority does not match exact config")
    if _git(repo_root, "rev-parse", "HEAD") != promotion_parent_commit or _git(repo_root, "status", "--porcelain=v1", "--untracked-files=all"):
        raise RuntimeError("promotion requires the exact clean accepted commit")
    if external_manifest_path.is_symlink() or not external_manifest_path.is_file():
        raise RuntimeError("external renderer manifest is missing or symlinked")
    external_bytes = external_manifest_path.read_bytes()
    external = json.loads(external_bytes)
    examples, outputs = _validate_external(external)
    receipt_evidence = _validate_accepted_receipt(
        repo_root=repo_root,
        promotion_parent_commit=promotion_parent_commit,
        project_image_id=project_image_id,
        accepted_records=external["input_reads"]["artifact_allowlist_records"],
    )
    result = config["result"]
    prefix = str(result["promotion_prefix"])
    uri = str(result["external_uri"])
    panel = outputs[external["eligibility"]["file"]]
    report_relative = f"{prefix}/C1_C2_QUALITATIVE_EVALUATOR_SUPPLEMENT_v1.md"
    funnel_relative = f"{prefix}/c1_c2_stage_funnel_v1.csv"
    eligibility_relative = f"{prefix}/uas_199_to_72_fixed_examples_v1.csv"
    manifest_relative = str(result["technical_manifest_path"])
    report_bytes = _supplement_md(external, uri, outputs)
    funnel_bytes = _stage_csv()
    eligibility_bytes = _eligibility_csv(examples, uri, panel)
    planned = {
        report_relative: report_bytes,
        funnel_relative: funnel_bytes,
        eligibility_relative: eligibility_bytes,
        manifest_relative: b"",
    }
    for relative in planned:
        if _safe_path(repo_root, relative).exists():
            raise RuntimeError(f"add-once promotion target already exists: {relative}")
    promoted_records = [
        _record(report_relative, report_bytes),
        _record(funnel_relative, funnel_bytes),
        _record(eligibility_relative, eligibility_bytes),
    ]
    technical = {
        "schema": "jointbuildgs.c1_c2_qualitative_evaluator_backfill_manifest.v1",
        "task_id": TASK_ID,
        "handoff_id": HANDOFF_ID,
        "run_id": run_id,
        "source_commit": source_commit,
        "promotion_parent_commit": promotion_parent_commit,
        "project_image_id": project_image_id,
        "accepted_receipt": receipt_evidence,
        "external_namespace": uri,
        "external_manifest": {
            "path": external_manifest_path.name,
            "bytes": len(external_bytes),
            "sha256": hashlib.sha256(external_bytes).hexdigest(),
            "natural_reads_and_digests": 1,
        },
        "external_records_reused_without_rehash": list(external["outputs"]),
        "accepted_artifact_records": list(external["input_reads"]["artifact_allowlist_records"]),
        "promoted_records": promoted_records,
        "case_sheet_count": 51,
        "method_panel_count": 102,
        "sealed_association_rows": 102,
        "associated_render_uses": 101,
        "c1_method_panel_count": 51,
        "c2_geometry_method_panel_count": 50,
        "c2_absent_method_panel_count": 1,
        "unique_execution_units": 7,
        "duplicate_payload_reads_prevented": 94,
        "derived_operation_las_processing_reads_and_digests": 7,
        "derived_operation_las_max_reads_per_record": 1,
        "derived_r_derived_processing_reads_and_digests": 7,
        "derived_r_derived_max_reads_per_record": 1,
        "derived_cityjson_processing_reads_and_digests": 7,
        "derived_cityjson_max_reads_per_record": 1,
        "reference_candidate_cells_processing_reads_and_digests": 1,
        "reference_candidate_cells_hash_only_passes": 0,
        "accepted_artifact_record_count": receipt_evidence["artifact_record_count"],
        "accepted_pre_push_sha256_verifications": receipt_evidence["pre_push_sha256_verifications"],
        "accepted_post_push_sha256_verifications": receipt_evidence["post_push_sha256_verifications"],
        "accepted_sha256_verifications_total": receipt_evidence["sha256_verifications_total"],
        "runtime_sealed_derived_hash_only_passes": 0,
        "successor_200_300_source_rehashes": 0,
        "original_large_source_hashes": 0,
        "original_scientific_source_reads_or_hashes": 0,
        "source_scientific_inputs_read": 0,
        "png_rehashes_during_promotion": 0,
        "new_metric_calculations": 0,
        "eligibility_recomputations": 0,
        "roofer_invocations": 0,
        "reconstruction_invocations": 0,
        "validation_payload_accesses": 0,
        "held_out_payload_accesses": 0,
        "method_summary": external["stage_and_coverage_correction"],
        "PASS_usable": None,
        "scientific_verdict": None,
    }
    technical_bytes = _json_bytes(technical)
    _add_once(repo_root, report_relative, report_bytes)
    _add_once(repo_root, funnel_relative, funnel_bytes)
    _add_once(repo_root, eligibility_relative, eligibility_bytes)
    _add_once(repo_root, manifest_relative, technical_bytes)
    return technical


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(description=__doc__)
    value.add_argument("--external-manifest", type=Path, required=True)
    value.add_argument("--repo-root", type=Path, required=True)
    value.add_argument("--promotion-parent-commit", required=True)
    value.add_argument("--source-commit", required=True)
    value.add_argument("--project-image-id", required=True)
    value.add_argument("--run-id", required=True)
    return value


def main() -> int:
    args = parser().parse_args()
    result = promote(
        external_manifest_path=args.external_manifest,
        repo_root=args.repo_root,
        promotion_parent_commit=args.promotion_parent_commit,
        source_commit=args.source_commit,
        project_image_id=args.project_image_id,
        run_id=args.run_id,
    )
    print(json.dumps({"task_id": result["task_id"], "promoted_records": len(result["promoted_records"]) + 1, "scientific_verdict": None}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
