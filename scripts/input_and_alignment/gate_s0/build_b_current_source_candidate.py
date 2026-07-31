#!/usr/bin/env python3
"""Build the compact, outcome-free B_current source candidate from prior evidence.

This tool deliberately reads only Git-owned compact evidence. It does not open or
rehash the external image/OPF archives and it does not freeze Gate S0.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
from typing import Any


IMAGE_INVENTORY = Path(
    "artifacts/manifests/gate_s0/gate_s0_image_member_inventory_v1.csv"
)
IMAGE_CAMERA_LEDGER = Path(
    "docs/research/preregistration/gate_s0/gate_s0_image_camera_ledger_v1.csv"
)
INPUT_MANIFEST = Path(
    "docs/research/preregistration/gate_s0/gate_s0_input_manifest_v1.json"
)
SPARSE_EVIDENCE = Path(
    "docs/research/preregistration/gate_s0/remediation_r1/"
    "sfm_sparse_initialization_v1.json"
)
PRIOR_ATTESTATION = Path(
    "artifacts/manifests/handoffs/P2-W2C-GATE-S0-REMEDIATION-R1-v1/"
    "100-accepted.json"
)
DEFAULT_OUTPUT = Path(
    "artifacts/manifests/gate_s0/b_current_source_candidate_v1.json"
)


def lf_bytes(path: Path) -> bytes:
    return path.read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")


def file_record(path: Path) -> dict[str, Any]:
    payload = lf_bytes(path)
    return {
        "path": path.as_posix(),
        "bytes": len(payload),
        "sha256": hashlib.sha256(payload).hexdigest(),
        "hash_scope": "Git LF-canonical bytes",
    }


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def sha256_lines(values: list[str]) -> str:
    payload = "".join(f"{value}\n" for value in sorted(values)).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def canonical_json_bytes(payload: dict[str, Any]) -> bytes:
    return (
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def artifact_by_id(inputs: dict[str, Any], asset_id: str) -> dict[str, Any]:
    matches = [item for item in inputs["files"] if item["asset_id"] == asset_id]
    if len(matches) != 1:
        raise ValueError(f"expected one {asset_id} record, found {len(matches)}")
    item = matches[0]
    return {
        "asset_id": item["asset_id"],
        "uri": item["uri"],
        "bytes": item["bytes"],
        "sha256": item["sha256"],
        "source_crs": item["source_crs"],
        "vertical_datum": item["vertical_datum"],
        "prior_verification_method": item["verification_method"],
        "prior_verified_at": item["verified_at"],
        "prior_verified_by": item["verified_by"],
    }


def build_candidate() -> dict[str, Any]:
    inventory = read_csv(IMAGE_INVENTORY)
    ledger = read_csv(IMAGE_CAMERA_LEDGER)
    inputs = read_json(INPUT_MANIFEST)
    sparse = read_json(SPARSE_EVIDENCE)
    prior = read_json(PRIOR_ATTESTATION)

    inventory_by_name = {row["basename"]: row for row in inventory}
    ledger_by_name = {row["basename"]: row for row in ledger}
    if len(inventory_by_name) != len(inventory):
        raise ValueError("duplicate image basename in member inventory")
    if len(ledger_by_name) != len(ledger):
        raise ValueError("duplicate image basename in image/camera ledger")
    if set(inventory_by_name) != set(ledger_by_name):
        raise ValueError("image inventory and camera ledger basename sets differ")

    included = [row for row in ledger if row["status"] == "INCLUDED"]
    excluded = [row for row in ledger if row["status"] == "EXCLUDED"]
    if len(included) != 937 or len(excluded) != 25 or len(ledger) != 962:
        raise ValueError("expected 962 total, 937 included, and 25 excluded images")
    if any(row["calibrated_pose_present"] != "true" for row in included):
        raise ValueError("included image lacks a calibrated pose")
    if any(row["calibrated_pose_present"] != "false" for row in excluded):
        raise ValueError("excluded image unexpectedly has a calibrated pose")
    if any(
        row["exclusion_reason"] != "NO_CALIBRATED_CAMERA_POSE_IN_OPF"
        for row in excluded
    ):
        raise ValueError("unexpected exclusion reason")
    camera_ids = [row["camera_id"] for row in included]
    if len(set(camera_ids)) != len(camera_ids):
        raise ValueError("included camera IDs are not unique")

    compact = inputs["image_camera_ledger"]
    expected_hashes = {
        "inventory": compact["image_member_inventory_sha256"],
        "ledger": compact["ledger_sha256"],
    }
    observed_hashes = {
        "inventory": file_record(IMAGE_INVENTORY)["sha256"],
        "ledger": file_record(IMAGE_CAMERA_LEDGER)["sha256"],
    }
    if expected_hashes != observed_hashes:
        raise ValueError(
            f"prior compact evidence hash mismatch: {expected_hashes} != {observed_hashes}"
        )

    prior_records = {item["uri"]: item for item in prior["artifacts"]["records"]}
    image_archive = artifact_by_id(inputs, "IMG_CURRENT_ARCHIVE")
    pose_archive = artifact_by_id(inputs, "CAM_CURRENT_OPF")
    for source in (image_archive, pose_archive):
        attested = prior_records.get(source["uri"])
        if not attested:
            raise ValueError(f"prior accepted attestation is missing {source['uri']}")
        if (attested["bytes"], attested["sha256"]) != (
            source["bytes"],
            source["sha256"],
        ):
            raise ValueError(f"prior accepted attestation differs for {source['uri']}")

    sparse_members = sparse["member_records"]
    source_evidence = {
        "image_member_inventory": file_record(IMAGE_INVENTORY),
        "image_camera_ledger": file_record(IMAGE_CAMERA_LEDGER),
        "gate_s0_input_manifest": file_record(INPUT_MANIFEST),
        "sparse_evidence": file_record(SPARSE_EVIDENCE),
        "prior_artifact_attestation": {
            **file_record(PRIOR_ATTESTATION),
            "state": prior["state"],
            "verification_level": prior["verification"]["level"],
            "record_count": len(prior_records),
            "reuse_rule": (
                "Cite the immutable prior attestation; do not rehash the same source "
                "archives for this Work Host consolidation."
            ),
        },
    }

    core: dict[str, Any] = {
        "schema": "jointbuildgs.gate_s0_b_current_source_candidate.v1",
        "status": "CANDIDATE_NOT_FROZEN",
        "research_canon": "C1C5_CANON_v2",
        "decision_log_through": "DEC-P1-011",
        "scientific_verdict": None,
        "performance_authority": "NONE",
        "source_evidence": source_evidence,
        "source_archives": {
            "images": image_archive,
            "camera_pose_opf": pose_archive,
        },
        "membership": {
            "join_rule": compact["join_rule"],
            "image_count": len(inventory),
            "included_count": len(included),
            "excluded_count": len(excluded),
            "included_basename_set_sha256": sha256_lines(
                [row["basename"] for row in included]
            ),
            "excluded_basename_set_sha256": sha256_lines(
                [row["basename"] for row in excluded]
            ),
            "included_camera_id_set_sha256": sha256_lines(camera_ids),
            "included_image_camera_pair_sha256": sha256_lines(
                [f"{row['basename']}|{row['camera_id']}" for row in included]
            ),
            "exclusion_rule": "NO_CALIBRATED_CAMERA_POSE_IN_OPF",
            "exact_members_are_bound_by": [
                IMAGE_INVENTORY.as_posix(),
                IMAGE_CAMERA_LEDGER.as_posix(),
            ],
        },
        "pose_member_binding": compact["opf_member_hashes"],
        "coordinate_frame": {
            "source_crs": sparse["coordinate_frame"]["source_crs"],
            "axis_unit": sparse["coordinate_frame"]["axis_unit"],
            "vertical_datum": sparse["coordinate_frame"]["vertical_datum"],
            "base_to_canonical": sparse["coordinate_frame"]["base_to_canonical"],
            "gate_state": "PARTIAL_VERTICAL_DATUM_UNRESOLVED",
        },
        "component_registry": {
            "sfm_sparse": {
                "source_identity": "READY_FROM_PRIOR_VERIFIED_EVIDENCE",
                "gate_enablement": "PROVISIONAL",
                "integration_status": sparse["integration_replay_status"],
                "producer": sparse["sparse"]["producer"],
                "point_count": sparse["sparse"]["point_count"],
                "camera_uid_count": sparse["sparse"]["camera_uid_count"],
                "camera_uids_equal_calibrated_camera_ids": sparse["sparse"][
                    "camera_uids_equal_calibrated_camera_ids"
                ],
                "member_count": len(sparse_members),
                "member_manifest_sha256": hashlib.sha256(
                    canonical_json_bytes({"members": sparse_members})
                ).hexdigest(),
                "allowed_role_under_dec_p1_010": (
                    "C3-C5 shared image-derived initialization/support; exact enabled "
                    "role remains a human Gate S0 decision."
                ),
                "remaining_gap": sparse["remaining_integration_gap"],
            },
            "dense_mvs": {
                "status": "MISSING_EXACT_COMMON_BASE_DERIVATIVE",
                "gate_enablement": None,
                "existing_1104_image_vendor_mvs": "SENSOR_PROCESSING_BUNDLE_CONTEXT_ONLY",
            },
            "depth": {
                "status": "MISSING_EXACT_COMMON_BASE_DERIVATIVE",
                "gate_enablement": None,
            },
            "normal": {
                "status": "MISSING_EXACT_COMMON_BASE_DERIVATIVE",
                "gate_enablement": None,
            },
            "confidence": {
                "status": "MISSING_EXACT_COMMON_BASE_DERIVATIVE",
                "gate_enablement": None,
            },
        },
        "condition_binding": {
            "C2_MVS": "same B_current dense MVS -> direct Roofer",
            "C3_GS_image": "B_current -> no-external-prior GS reoptimization",
            "C4_GS_lidar_prior": "exact C3 base + existing ALS only",
            "C5_GS_lod1_prior": "exact C3 base + independent LoD1 only",
        },
        "reuse_contract": {
            "operation_identity_fields": [
                "source_candidate_manifest_sha256",
                "component",
                "producer_and_version",
                "code_commit",
                "config_sha256",
                "coordinate_frame",
                "scientific_role",
            ],
            "policy": [
                "Resolve an exact prior operation identity before scheduling work.",
                "If an exact completed artifact exists, mark REUSED and do not rerun.",
                "Create each shared image-derived component once under B_current, not per arm.",
                "Hash a newly promoted candidate once; successor receipts inherit the attestation.",
                "Never rehash the unchanged 15.7 GB R1 source bundle at every handoff state.",
                "Never repeat the closed R1 LoD1 search without a new provider or scope delta.",
            ],
        },
        "gate_state": {
            "source_member_candidate": "COMPLETE_FROM_PRIOR_VERIFIED_EVIDENCE",
            "combined_b_current": "BLOCKED_MISSING_DERIVATIVE_PROVENANCE_AND_HUMAN_FREEZE",
            "gate_s0": "NOT_APPROVED",
            "p2_performance": "PROHIBITED",
        },
    }
    digest = hashlib.sha256(canonical_json_bytes(core)).hexdigest()
    return {
        **core,
        "common_image_pose_base_id": f"B_CURRENT_CANDIDATE_{digest[:16]}",
        "source_candidate_manifest_sha256": digest,
        "source_candidate_hash_scope": (
            "canonical JSON of this document excluding common_image_pose_base_id, "
            "source_candidate_manifest_sha256, and source_candidate_hash_scope"
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    payload = canonical_json_bytes(build_candidate())
    if args.check:
        if not args.output.exists() or lf_bytes(args.output) != payload:
            raise SystemExit(f"stale or missing B_current candidate: {args.output}")
        return 0
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
