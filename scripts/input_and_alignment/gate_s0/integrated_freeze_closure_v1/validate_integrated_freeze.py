#!/usr/bin/env python3
"""Validate the bounded, interrupted Gate S0 integrated-freeze return.

This validator never enumerates or reads external scientific payloads.  The optional
artifact check performs exact-path stat calls for the two task-owned partial outputs.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


REPO = Path(__file__).resolve().parents[4]
ROOT = REPO / "artifacts/manifests/gate_s0/integrated_freeze_closure_v1"
DOC = REPO / "docs/research/preregistration/gate_s0/integrated_freeze_closure_v1"
TASK = "P2-GATE-S0-INTEGRATED-FREEZE-CLOSURE-v1"


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def assert_null_verdicts(value: Any, path: str = "root") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if key in {"scientific_verdict", "gate_decision"} and child is not None:
                raise AssertionError(f"{path}.{key} must be null")
            assert_null_verdicts(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            assert_null_verdicts(child, f"{path}[{index}]")


def validate(artifact_root: Path | None) -> dict[str, Any]:
    required = [
        "interrupted_operation_record_v1.json",
        "four_path_fingerprint_v1.json",
        "component_enablement_v1.json",
        "c1_c4_derivative_manifest_v1.json",
        "independent_reference_manifest_v1.json",
        "universe_manifest_v1.json",
        "split_manifest_v1.json",
        "stage3_common_interface_manifest_v1.json",
        "administrative_cost_caps_v1.json",
        "external_output_records_v1.json",
    ]
    payloads = {name: load(ROOT / name) for name in required}
    payloads["frame"] = load(DOC / "frame_datum_registration_gravity_receipt_v1.json")
    payloads["smoke"] = load(DOC / "stage3_synthetic_smoke_receipt_v1.json")
    for name, payload in payloads.items():
        assert payload.get("task_id") == TASK, name
        assert_null_verdicts(payload, name)

    interrupted = payloads["interrupted_operation_record_v1.json"]
    assert interrupted["status"] == "INTERRUPTED_NON_REPEATABLE"
    selected = interrupted["retained_selected_accounting"]
    assert selected == {
        "logical_paths": 4,
        "regular_files": 8,
        "bytes_read_once": 986484109,
        "bytes_hashed_once": 986484109,
        "byte_ceiling": 986484109,
        "basis": selected["basis"],
        "digest_values": "MISSING_PROCESS_EXITED_BEFORE_MANIFEST_PERSISTENCE",
        "rerun_permitted": False,
    }
    assert interrupted["failure"]["c1_point_chunks_decoded"] == 0
    assert interrupted["failure"]["c4_tiles_accessed"] == 0
    assert interrupted["no_repeat_guard"]["next_invocation_blocks_before_external_access"]

    fingerprint = payloads["four_path_fingerprint_v1.json"]
    assert fingerprint["selected_logical_path_count"] == 4
    assert fingerprint["selected_regular_file_count"] == 8
    assert fingerprint["total_bytes_hashed_once"] == 986484109
    assert all(row.get("sha256_or_merkle", row.get("sha256")) is None for row in fingerprint["paths"])

    reference = payloads["independent_reference_manifest_v1.json"]
    assert reference["status"] == "MISSING_NOT_CONSTRUCTED"
    assert reference["input_lod2_source_geometry_asset_reads"] == 0
    assert not reference["input_lod2_used_for_reference_registration_crop_tuning_stopping"]
    assert reference["C5_input_role"] == "LOD2_DERIVED_COARSE_LOD1_INPUT_ONLY_NEVER_EVALUATION_REFERENCE"

    universe = payloads["universe_manifest_v1.json"]
    assert universe["candidate_count_attested_prior"] == 199
    assert universe["u_target_count"] is None and universe["e_paired_count"] is None
    assert not universe["held_out_accessed"]
    split = payloads["split_manifest_v1.json"]
    assert split["group_assignments"] == {} and not split["held_out_accessed"]

    stage3 = payloads["stage3_common_interface_manifest_v1.json"]
    assert len(stage3["conditions"]) == 5
    assert not stage3["external_roofprint_allowed"]
    assert not stage3["synthetic_smoke"]["quality_comparison"]
    assert stage3["synthetic_smoke"]["sha256"] == "ca3697c657730581338006ed50570d91d3a7639f7ac7f60e3c0b410893d04935"

    caps = payloads["administrative_cost_caps_v1.json"]
    assert (caps["gpu_per_condition_run"], caps["vram_gb_max"], caps["wall_clock_hours_max"]) == (1, 24, 12)
    assert (caps["new_output_gb_max_per_run"], caps["retry_max"], caps["total_new_retained_storage_gb_max"]) == (100, 1, 500)

    gate = (REPO / "docs/research/preregistration/gate_s0/GATE_S0_FREEZE_PACKET_v2.md").read_text(encoding="utf-8")
    ret = (REPO / "docs/handoffs/returns/P2_C2W_GATE_S0_INTEGRATED_FREEZE_CLOSURE_v1.md").read_text(encoding="utf-8")
    addendum = (DOC / "R2B_AND_SOURCE_PROVENANCE_ADDENDUM_v1.md").read_text(encoding="utf-8")
    for text in (gate, ret):
        assert "Technical state: `BLOCKED`" in text or "technical_state: `BLOCKED`" in text
        assert "scientific_verdict: `null`" in text
    assert "f3e0be625f7b8d7ed778d74e9b9ed9ac78d58cd0" in addendum
    assert "f3e0be62a67605727f0470c6373e0d78ea590ebb" in addendum

    external = payloads["external_output_records_v1.json"]
    records = external["records"]
    assert external["recovery_content_reads_or_hashes"] == 0
    assert [row["bytes"] for row in records] == [530, 5464707]
    assert all(row["sha256"] is None for row in records)
    metadata_checks = 0
    if artifact_root is not None:
        prefix = "artifact://JointBuildGS/"
        for record in records:
            assert record["uri"].startswith(prefix)
            path = artifact_root / record["uri"][len(prefix):]
            assert not path.is_symlink() and path.is_file()
            assert path.stat().st_size == record["bytes"]
            metadata_checks += 1

    assert not (ROOT / "no_repeat_operation_ledger_v1.json").exists()
    return {"git_manifests": len(payloads), "metadata_checks": metadata_checks, "errors": 0}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact-root", type=Path)
    args = parser.parse_args()
    print(json.dumps(validate(args.artifact_root), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
