#!/usr/bin/env python3
"""Validate compact R2A evidence without rereading source or external output bytes."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any


CONFIG_PATH = Path(
    "configs/input_and_alignment/gate_s0/common_base_r2a/r2a_evidence_v1.json"
)
PREPARE_SCRIPT = Path(
    "scripts/input_and_alignment/gate_s0/common_base_r2a/prepare_r2a_evidence.py"
)
MANIFEST_ROOT = Path("artifacts/manifests/gate_s0/common_base_r2a")
DOC_ROOT = Path("docs/research/preregistration/gate_s0/common_base_r2a")
RETURN_PATH = Path("docs/handoffs/returns/P2_C2W_GATE_S0_EVIDENCE_R2A_RETURN_v1.md")
OUTPUT_MANIFEST_PATH = MANIFEST_ROOT / "output_manifest_v1.json"
REQUIRED_OUTPUTS = [
    DOC_ROOT / "B_CURRENT_EVIDENCE_R2A_REPORT_v1.md",
    MANIFEST_ROOT / "source_candidate_replay_v1.json",
    MANIFEST_ROOT / "derivative_provenance_matrix_v1.json",
    MANIFEST_ROOT / "reuse_ledger_v1.json",
    MANIFEST_ROOT / "preprocessing_dag_v1.json",
    MANIFEST_ROOT / "lod2_derived_lod1_diagnostic_manifest_v1.json",
    MANIFEST_ROOT / "lod2_derived_lod1_lineage_v1.csv",
    DOC_ROOT / "issue_log_v1.md",
    RETURN_PATH,
]
ALLOWED_PREFIXES = (
    "artifacts/manifests/handoffs/P2-W2C-GATE-S0-EVIDENCE-R2A-v1/",
    "artifacts/manifests/gate_s0/common_base_r2a/",
    "configs/input_and_alignment/gate_s0/common_base_r2a/",
    "docs/handoffs/returns/P2_C2W_GATE_S0_EVIDENCE_R2A_RETURN_v1.md",
    "docs/research/preregistration/gate_s0/common_base_r2a/",
    "scripts/input_and_alignment/gate_s0/common_base_r2a/",
    "tests/input_and_alignment/gate_s0/common_base_r2a/",
)


def lf_bytes(path: Path) -> bytes:
    return path.read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def canonical_json_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def require(condition: bool, message: str, errors: list[str]) -> None:
    if not condition:
        errors.append(message)


def git_paths(*args: str) -> list[str]:
    result = subprocess.run(
        ["git", "-c", f"safe.directory={Path.cwd().resolve()}", *args],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip())
    return [line for line in result.stdout.splitlines() if line]


def build_output_manifest() -> dict[str, Any]:
    missing = [path.as_posix() for path in REQUIRED_OUTPUTS if not path.is_file()]
    if missing:
        raise RuntimeError(f"cannot index missing required outputs: {missing}")
    config = read_json(CONFIG_PATH)
    diagnostic = read_json(
        MANIFEST_ROOT / "lod2_derived_lod1_diagnostic_manifest_v1.json"
    )
    return {
        "schema": "jointbuildgs.gate_s0_r2a_output_manifest.v1",
        "handoff_id": "P2-W2C-GATE-S0-EVIDENCE-R2A-v1",
        "task_id": "P2-GATE-S0-EVIDENCE-R2A-v1",
        "input_commit": config["input_commit"],
        "output_commit": "SELF",
        "proposed_status": "BLOCKED_FOR_GATE_S0_EVIDENCE_REVIEW",
        "artifact_verification_level": "STREAM_DIGEST_BOUND_PENDING_FIRST_200_ARTIFACT_RECEIPT",
        "scientific_verdict": None,
        "files": [
            {
                "path": path.as_posix(),
                "bytes": len(lf_bytes(path)),
                "sha256": sha256_bytes(lf_bytes(path)),
                "hash_scope": "Git LF-canonical bytes",
            }
            for path in REQUIRED_OUTPUTS
        ],
        "external_output_records": [
            {
                "uri": item["uri"],
                "bytes": item["bytes"],
                "sha256": item["sha256"],
                "prior_role": item["prior_role"],
                "evaluation_class": item["evaluation_class"],
                "primary_c5_eligible": item["primary_c5_eligible"],
                "verification_status": item["verification_status"],
            }
            for item in diagnostic["output_records"]
        ],
    }


def validate_scope(config: dict[str, Any], errors: list[str]) -> None:
    tracked = git_paths("diff", "--name-only", config["input_commit"], "--")
    untracked = git_paths("ls-files", "--others", "--exclude-standard")
    for path in sorted(set(tracked + untracked)):
        require(
            any(path == prefix or path.startswith(prefix) for prefix in ALLOWED_PREFIXES),
            f"path outside exact R2A write scope: {path}",
            errors,
        )


def validate_compact_outputs() -> list[str]:
    errors: list[str] = []
    config = read_json(CONFIG_PATH)
    replay = read_json(MANIFEST_ROOT / "source_candidate_replay_v1.json")
    matrix = read_json(MANIFEST_ROOT / "derivative_provenance_matrix_v1.json")
    ledger = read_json(MANIFEST_ROOT / "reuse_ledger_v1.json")
    dag = read_json(MANIFEST_ROOT / "preprocessing_dag_v1.json")
    diagnostic = read_json(
        MANIFEST_ROOT / "lod2_derived_lod1_diagnostic_manifest_v1.json"
    )
    lineage = read_csv(MANIFEST_ROOT / "lod2_derived_lod1_lineage_v1.csv")
    output_manifest = read_json(OUTPUT_MANIFEST_PATH)

    require(replay["status"] == "REPLAY_EXACT_FROM_GIT_COMPACT_EVIDENCE", "source replay status differs", errors)
    require(replay["counts"] == {
        "excluded_no_pose": 25,
        "image_members": 962,
        "included_image_pose_pairs": 937,
        "unique_included_camera_ids": 937,
    }, "source replay counts differ", errors)
    require(all(replay["checks"].values()), "one or more source replay checks failed", errors)
    require(replay["contradictions"] == [], "source replay contradictions are not empty", errors)

    statuses = {item["component"]: item["status"] for item in matrix["components"]}
    require(statuses == {
        "sfm_sparse": "REUSED_EXACT",
        "dense_mvs": "AMBIGUOUS",
        "depth": "MISSING",
        "normal": "MISSING",
        "confidence": "MISSING",
    }, f"unexpected derivative statuses: {statuses}", errors)
    dense = next(item for item in matrix["components"] if item["component"] == "dense_mvs")
    require(len(dense["bounded_unbound_candidates"]) == 1, "unbound scene.mvs candidate not recorded", errors)
    require(dense["ineligible_context_candidate"]["classification"] == "INELIGIBLE_SENSOR_PROCESSING_BUNDLE_CONTEXT_ONLY", "vendor MVS classification differs", errors)
    require(matrix["missing_derivatives_generated"] is False, "missing derivative generation was claimed", errors)

    require(ledger["initialized_before_external_payload_access"] is True, "reuse ledger was not initialized first", errors)
    require(ledger["payload_operations_started"] is True and ledger["completed"] is True, "reuse ledger is incomplete", errors)
    require(ledger["config_sha256"] == sha256_bytes(lf_bytes(CONFIG_PATH)), "config hash drifted after execution", errors)
    require(ledger["implementation_script_sha256"] == sha256_bytes(lf_bytes(PREPARE_SCRIPT)), "prepare script hash drifted after execution", errors)
    totals = ledger["totals"]
    require(totals["closed_r1_bundle_repeated_read_bytes"] == 0, "R1 bundle was reread", errors)
    require(totals["images_zip_read_bytes"] == 0, "Images.zip was reread", errors)
    require(totals["opf_zip_read_bytes"] == 0, "OPF.zip was reread", errors)
    require(totals["lod2_source_read_bytes"] == 304_522_448, "LoD2 read-byte total differs", errors)
    require(totals["lod2_source_hashed_bytes"] == 304_522_448, "LoD2 hashed-byte total differs", errors)
    require(totals["output_full_rehash_passes_before_first_artifact_receipt"] == 0, "output was rehashed before first receipt", errors)
    require(totals["successor_300_output_rehash_passes"] == 0, "300 output rehash budget differs", errors)

    require(dag["namespace"] == config["source_candidate"]["id"], "DAG namespace differs", errors)
    require(dag["arm_specific_duplicate_generation"] == "INVALID", "DAG permits arm-specific generation", errors)
    for key in ("component_enablement", "mvs_algorithm", "gs_loss", "adapter", "threshold"):
        require(dag[key] is None, f"DAG selected deferred field: {key}", errors)
    dag_status = {item["node_id"]: item["status"] for item in dag["nodes"]}
    require(dag_status["dense_mvs"] == "MISSING", "DAG dense node should remain missing", errors)
    require(all(dag_status[item] == "MISSING" for item in ("depth", "normal", "confidence")), "DAG missing nodes differ", errors)

    require(diagnostic["status"] == "EXECUTED_ADD_ONCE", "diagnostic was not add-once executed", errors)
    require(diagnostic["combined_building_count"] == 12_049, "diagnostic building count differs", errors)
    require(diagnostic["combined_stable_id_unique_count"] == 12_049, "diagnostic stable-ID count differs", errors)
    require([item["building_count"] for item in diagnostic["tile_summaries"]] == [5_479, 6_570], "tile building counts differ", errors)
    require(all(item["cityjsonseq_roundtrip"]["parsed"] for item in diagnostic["tile_summaries"]), "CityJSONSeq round-trip failed", errors)
    require(len(diagnostic["output_records"]) == 4, "external output count differs", errors)
    require(sum(item["bytes"] for item in diagnostic["output_records"]) == 28_472_973, "external output bytes differ", errors)
    require(all(item["prior_role"] == "REFERENCE_DERIVED_DIAGNOSTIC_ONLY" for item in diagnostic["output_records"]), "output prior role differs", errors)
    require(all(item["evaluation_class"] == "REFERENCE_DERIVED_SELF_CONDITIONED" for item in diagnostic["output_records"]), "output evaluation class differs", errors)
    require(all(item["primary_c5_eligible"] is False for item in diagnostic["output_records"]), "output became primary C5 eligible", errors)
    require(diagnostic["performance_scored"] is False and diagnostic["e_paired_promoted"] is False, "diagnostic was scored or promoted", errors)
    require(diagnostic["scientific_verdict"] is None, "diagnostic scientific verdict is not null", errors)
    require(len(lineage) == 12_049, "lineage row count differs", errors)
    require(len({row["stable_building_id"] for row in lineage}) == 12_049, "lineage stable IDs are not unique", errors)
    require(all(row["prior_role"] == "REFERENCE_DERIVED_DIAGNOSTIC_ONLY" for row in lineage), "lineage prior role differs", errors)
    require(all(row["evaluation_class"] == "REFERENCE_DERIVED_SELF_CONDITIONED" for row in lineage), "lineage evaluation class differs", errors)
    require(all(row["primary_c5_eligible"] == "false" for row in lineage), "lineage primary C5 eligibility differs", errors)

    expected_manifest = build_output_manifest()
    require(output_manifest == expected_manifest, "LF-canonical output manifest is stale", errors)
    indexed = {item["path"]: item for item in output_manifest["files"]}
    require(set(indexed) == {path.as_posix() for path in REQUIRED_OUTPUTS}, "required output index differs", errors)
    require(output_manifest["scientific_verdict"] is None, "output manifest scientific verdict is not null", errors)

    for path in (DOC_ROOT / "B_CURRENT_EVIDENCE_R2A_REPORT_v1.md", DOC_ROOT / "issue_log_v1.md", RETURN_PATH):
        text = path.read_text(encoding="utf-8")
        require("scientific_verdict: null" in text, f"null scientific verdict missing: {path}", errors)
        require("BLOCKED_FOR_GATE_S0_EVIDENCE_REVIEW" in text, f"blocked proposal missing: {path}", errors)
    validate_scope(config, errors)
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write-output-manifest", action="store_true")
    args = parser.parse_args()
    if args.write_output_manifest:
        OUTPUT_MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
        OUTPUT_MANIFEST_PATH.write_bytes(canonical_json_bytes(build_output_manifest()))
    errors = validate_compact_outputs()
    if errors:
        print("Gate S0 R2A compact evidence: FAIL")
        for error in errors:
            print(f"  - {error}")
        return 1
    print("Gate S0 R2A compact evidence: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
