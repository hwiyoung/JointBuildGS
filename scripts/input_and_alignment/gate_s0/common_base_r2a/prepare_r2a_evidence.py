#!/usr/bin/env python3
"""Prepare bounded Gate S0 R2A common-base and LoD1 diagnostic evidence.

The initializer writes the duplicate-work ledger without touching the external
artifact backend. The executor then performs metadata-only derivative discovery and
reads each approved LoD2 source exactly once; SHA-256 is computed by the same stream
that feeds the XML parser.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import os
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, BinaryIO, Iterable


CONFIG_PATH = Path(
    "configs/input_and_alignment/gate_s0/common_base_r2a/r2a_evidence_v1.json"
)
SCRIPT_PATH = Path(
    "scripts/input_and_alignment/gate_s0/common_base_r2a/prepare_r2a_evidence.py"
)
MANIFEST_ROOT = Path("artifacts/manifests/gate_s0/common_base_r2a")
DOC_ROOT = Path("docs/research/preregistration/gate_s0/common_base_r2a")
LEDGER_PATH = MANIFEST_ROOT / "reuse_ledger_v1.json"
SOURCE_REPLAY_PATH = MANIFEST_ROOT / "source_candidate_replay_v1.json"
DERIVATIVE_MATRIX_PATH = MANIFEST_ROOT / "derivative_provenance_matrix_v1.json"
DAG_PATH = MANIFEST_ROOT / "preprocessing_dag_v1.json"
DIAGNOSTIC_MANIFEST_PATH = (
    MANIFEST_ROOT / "lod2_derived_lod1_diagnostic_manifest_v1.json"
)
LINEAGE_PATH = MANIFEST_ROOT / "lod2_derived_lod1_lineage_v1.csv"
ISSUE_LOG_PATH = DOC_ROOT / "issue_log_v1.md"

IMAGE_INVENTORY = Path(
    "artifacts/manifests/gate_s0/gate_s0_image_member_inventory_v1.csv"
)
IMAGE_CAMERA_LEDGER = Path(
    "docs/research/preregistration/gate_s0/gate_s0_image_camera_ledger_v1.csv"
)
INPUT_MANIFEST = Path(
    "docs/research/preregistration/gate_s0/gate_s0_input_manifest_v1.json"
)
SOURCE_BUILDER = Path(
    "scripts/input_and_alignment/gate_s0/build_b_current_source_candidate.py"
)

PRIOR_ROLE = "REFERENCE_DERIVED_DIAGNOSTIC_ONLY"
EVALUATION_CLASS = "REFERENCE_DERIVED_SELF_CONDITIONED"
TASK_ID = "P2-GATE-S0-EVIDENCE-R2A-v1"
HANDOFF_ID = "P2-W2C-GATE-S0-EVIDENCE-R2A-v1"
INITIALIZED_AT = "2026-08-01T02:11:00+09:00"


def canonical_json_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def compact_json_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
        + "\n"
    ).encode("utf-8")


def lf_bytes(path: Path) -> bytes:
    return path.read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical_json_bytes(value))


def write_csv(path: Path, fieldnames: list[str], rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def sha256_lines(values: Iterable[str]) -> str:
    payload = "".join(f"{value}\n" for value in sorted(values)).encode("utf-8")
    return sha256_bytes(payload)


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def attribute(element: ET.Element, name: str) -> str | None:
    return next(
        (value for key, value in element.attrib.items() if local_name(key) == name),
        None,
    )


def git(*args: str) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        ["git", "-c", f"safe.directory={Path.cwd().resolve()}", *args],
        check=False,
        capture_output=True,
    )


def operation_identity(
    config: dict[str, Any],
    *,
    component: str,
    producer_and_version: str,
    coordinate_frame: Any,
    scientific_role: str,
) -> dict[str, Any]:
    core = {
        "source_candidate_manifest_sha256": config["source_candidate"][
            "manifest_sha256"
        ],
        "component": component,
        "producer_and_version": producer_and_version,
        "code_commit": config["input_commit"],
        "config_sha256": sha256_bytes(lf_bytes(CONFIG_PATH)),
        "coordinate_frame": coordinate_frame,
        "scientific_role": scientific_role,
    }
    return {**core, "operation_id": sha256_bytes(canonical_json_bytes(core))}


def initialize_ledger(config: dict[str, Any]) -> dict[str, Any]:
    frame = {
        "horizontal": config["diagnostic"]["source_crs"],
        "vertical": config["diagnostic"]["vertical_datum"],
    }
    source_frame = {
        "horizontal": "EPSG:32632 scene frame",
        "vertical": "UNKNOWN",
    }
    operations = [
        {
            "name": "closed_r1_input_bundle_attestation",
            "identity": operation_identity(
                config,
                component="R1_15_7GB_INPUT_BUNDLE",
                producer_and_version="immutable R1 100-accepted receipt",
                coordinate_frame="MULTIPLE_RECORDED_FRAMES",
                scientific_role="PRIOR_ARTIFACT_ATTESTATION_ONLY",
            ),
            "status": "REUSED",
            "planned_full_bytes": 0,
            "read_bytes": 0,
            "hashed_bytes": 0,
            "reason": "Closed R1 artifact attestation is inherited without live rehash.",
        },
        {
            "name": "source_candidate_replay",
            "identity": operation_identity(
                config,
                component="B_CURRENT_SOURCE_CANDIDATE_REPLAY",
                producer_and_version=f"{SOURCE_BUILDER.as_posix()}@Git-compact-check",
                coordinate_frame=source_frame,
                scientific_role="OUTCOME_FREE_SOURCE_MEMBERSHIP_REPLAY",
            ),
            "status": "PLANNED",
            "planned_full_bytes": 0,
            "read_bytes": 0,
            "hashed_bytes": 0,
            "reason": "Git compact evidence only; Images.zip and OPF.zip remain unopened.",
        },
        {
            "name": "sfm_sparse_binding",
            "identity": operation_identity(
                config,
                component="sfm_sparse",
                producer_and_version="Pix4D PCL IO 2.1.2 / R1 member evidence",
                coordinate_frame=source_frame,
                scientific_role="SHARED_IMAGE_DERIVED_INITIALIZATION_SUPPORT_CANDIDATE",
            ),
            "status": "REUSED_EXACT",
            "planned_full_bytes": 0,
            "read_bytes": 0,
            "hashed_bytes": 0,
            "reason": "Reuse exact R1 member hashes; canonical conversion remains missing.",
        },
        {
            "name": "derivative_resolution",
            "identity": operation_identity(
                config,
                component="sfm_dense_depth_normal_confidence_resolution",
                producer_and_version=f"R2A metadata resolver/{sha256_bytes(lf_bytes(SCRIPT_PATH))[:16]}",
                coordinate_frame=source_frame,
                scientific_role="EXISTENCE_AND_PROVENANCE_BINDING_ONLY",
            ),
            "status": "PLANNED",
            "planned_full_bytes": 0,
            "read_bytes": 0,
            "hashed_bytes": 0,
            "reason": "Manifest-first resolution followed by bounded filename metadata discovery.",
        },
    ]
    for source in config["diagnostic"]["sources"]:
        operations.append(
            {
                "name": f"lod2_to_lod1_diagnostic_{source['tile_id']}",
                "identity": operation_identity(
                    config,
                    component=f"lod2_derived_lod1_{source['tile_id']}",
                    producer_and_version=f"R2A deterministic prism converter/{sha256_bytes(lf_bytes(SCRIPT_PATH))[:16]}",
                    coordinate_frame=frame,
                    scientific_role=PRIOR_ROLE,
                ),
                "status": "PLANNED",
                "planned_full_bytes": source["bytes"],
                "read_bytes": 0,
                "hashed_bytes": 0,
                "reason": "One parser stream including source SHA-256; no separate source hash pass.",
            }
        )
    return {
        "schema": "jointbuildgs.gate_s0_r2a_reuse_ledger.v1",
        "handoff_id": HANDOFF_ID,
        "task_id": TASK_ID,
        "initialized_at": INITIALIZED_AT,
        "initialized_before_external_payload_access": True,
        "payload_operations_started": False,
        "completed": False,
        "source_candidate_id": config["source_candidate"]["id"],
        "config_sha256": sha256_bytes(lf_bytes(CONFIG_PATH)),
        "implementation_script_sha256": sha256_bytes(lf_bytes(SCRIPT_PATH)),
        "identity_fields": [
            "source_candidate_manifest_sha256",
            "component",
            "producer_and_version",
            "code_commit",
            "config_sha256",
            "coordinate_frame",
            "scientific_role",
        ],
        "byte_budget": {
            "closed_r1_15_7gb_source_bundle_repeated_full_passes": 0,
            "images_zip_full_rehash_passes": 0,
            "opf_zip_full_rehash_passes": 0,
            "lod2_source_processing_passes_each": 1,
            "new_output_receipt_safety_passes_each": 2,
            "successor_300_output_rehash_passes": 0,
        },
        "operations": operations,
        "duplicate_work_guard_events": [],
        "scientific_verdict": None,
        "performance_authority": "NONE",
    }


def build_preprocessing_dag(config: dict[str, Any]) -> dict[str, Any]:
    frame = {
        "source": "EPSG:32632 scene frame",
        "target": "EPSG:25832",
        "vertical_datum": None,
    }
    nodes: list[dict[str, Any]] = []

    def add_node(
        component: str,
        depends_on: list[str],
        status: str,
        producer: str,
        role: str,
        output_requirement: str,
    ) -> None:
        identity = operation_identity(
            config,
            component=component,
            producer_and_version=producer,
            coordinate_frame=frame,
            scientific_role=role,
        )
        nodes.append(
            {
                "node_id": component,
                "operation_identity": identity,
                "depends_on": depends_on,
                "status": status,
                "producer_version": None if producer.startswith("UNSELECTED") else producer,
                "config_placeholder_requirements": [
                    "producer/version",
                    "exact CLI or API parameters",
                    "source-member manifest hash",
                    "coordinate transform and vertical datum",
                    "output URI/bytes/SHA-256",
                    "resource ceiling and resume checkpoint",
                ],
                "coordinate_frame": frame,
                "scientific_role": role,
                "output_requirement": output_requirement,
                "bounded_cost": {
                    "input_read_bytes": None,
                    "output_write_bytes": None,
                    "cpu_wall_seconds": None,
                    "gpu_wall_seconds": None,
                    "peak_memory_bytes": None,
                },
                "resume_rule": (
                    "Resolve the operation_id in manifests first. REUSED_EXACT is a no-op; "
                    "a conflicting record is BLOCKED_NAMESPACE_CONFLICT; otherwise write once "
                    "under the shared B_current namespace and atomically publish its manifest."
                ),
                "execution_identity_final": not producer.startswith("UNSELECTED"),
            }
        )

    add_node(
        "source_membership",
        [],
        "REUSED_EXACT",
        "B_current compact candidate generator",
        "SHARED_C2_C5_CURRENT_IMAGE_POSE_SOURCE",
        "Exact 937 included image/pose pairs plus 25 exclusions.",
    )
    add_node(
        "sfm_sparse",
        ["source_membership"],
        "REUSED_EXACT_SOURCE_MEMBERS_CANONICAL_CONVERSION_MISSING",
        "Pix4D PCL IO 2.1.2 / R1 member evidence",
        "SHARED_IMAGE_DERIVED_INITIALIZATION_SUPPORT_CANDIDATE",
        "One canonical sparse derivative or an explicit decision to consume bound OPF members.",
    )
    add_node(
        "dense_mvs",
        ["source_membership", "sfm_sparse"],
        "MISSING",
        "UNSELECTED_REQUIRES_HUMAN_GATE_REVIEW",
        "SHARED_IMAGE_DERIVED_GEOMETRY_CANDIDATE",
        "One exact-937-base dense MVS derivative shared by C2-C5.",
    )
    add_node(
        "depth",
        ["dense_mvs"],
        "MISSING",
        "UNSELECTED_REQUIRES_HUMAN_GATE_REVIEW",
        "SHARED_IMAGE_DERIVED_DEPTH_CANDIDATE",
        "Per-view or fused depth with exact camera/member relation.",
    )
    add_node(
        "normal",
        ["dense_mvs", "depth"],
        "MISSING",
        "UNSELECTED_REQUIRES_HUMAN_GATE_REVIEW",
        "SHARED_IMAGE_DERIVED_NORMAL_CANDIDATE",
        "Normal evidence with orientation convention and frame.",
    )
    add_node(
        "confidence",
        ["depth", "normal"],
        "MISSING",
        "UNSELECTED_REQUIRES_HUMAN_GATE_REVIEW",
        "SHARED_IMAGE_DERIVED_CONFIDENCE_CANDIDATE",
        "Image-derived confidence separated from any external-prior confidence.",
    )
    return {
        "schema": "jointbuildgs.gate_s0_r2a_preprocessing_dag.v1",
        "handoff_id": HANDOFF_ID,
        "task_id": TASK_ID,
        "namespace": config["source_candidate"]["id"],
        "arm_specific_duplicate_generation": "INVALID",
        "component_enablement": None,
        "mvs_algorithm": None,
        "gs_loss": None,
        "adapter": None,
        "threshold": None,
        "nodes": nodes,
        "consumers": {
            "C2_MVS": ["source_membership", "sfm_sparse", "dense_mvs"],
            "C3_GS_image": [
                "source_membership",
                "sfm_sparse",
                "dense_mvs",
                "depth",
                "normal",
                "confidence",
            ],
            "C4_GS_lidar_prior": "exact C3 base plus Existing ALS only",
            "C5_GS_lod1_prior": "exact C3 base plus independent LoD1 only",
        },
        "scientific_verdict": None,
        "performance_authority": "NONE",
    }


def replay_source_candidate(config: dict[str, Any]) -> dict[str, Any]:
    from scripts.input_and_alignment.gate_s0.build_b_current_source_candidate import (
        build_candidate,
    )

    check = subprocess.run(
        [sys.executable, SOURCE_BUILDER.as_posix(), "--check"],
        check=False,
        capture_output=True,
        text=True,
    )
    current = read_json(Path(config["source_candidate"]["path"]))
    rebuilt = build_candidate()
    inventory = read_csv(IMAGE_INVENTORY)
    camera_ledger = read_csv(IMAGE_CAMERA_LEDGER)
    input_manifest = read_json(INPUT_MANIFEST)
    prior_path = Path(config["prior_evidence"]["r1_accepted_receipt_path"])
    prior = read_json(prior_path)
    sparse_path = Path(config["prior_evidence"]["sfm_sparse_evidence_path"])
    sparse = read_json(sparse_path)

    included = [row for row in camera_ledger if row["status"] == "INCLUDED"]
    excluded = [row for row in camera_ledger if row["status"] == "EXCLUDED"]
    camera_ids = [row["camera_id"] for row in included]
    pose_members = input_manifest["image_camera_ledger"]["opf_member_hashes"]
    prior_records = {row["uri"]: row for row in prior["artifacts"]["records"]}
    source_records = current["source_archives"]
    archive_attestation_match = all(
        prior_records[item["uri"]]["bytes"] == item["bytes"]
        and prior_records[item["uri"]]["sha256"] == item["sha256"]
        for item in source_records.values()
    )
    introduced = git("log", "--diff-filter=A", "-1", "--format=%H", "--", prior_path.as_posix())
    introduced_commit = introduced.stdout.decode().strip()
    checks = {
        "generator_check_exit_zero": check.returncode == 0,
        "rebuilt_bytes_equal_tracked_candidate": canonical_json_bytes(rebuilt)
        == canonical_json_bytes(current),
        "candidate_manifest_hash_exact": current["source_candidate_manifest_sha256"]
        == config["source_candidate"]["manifest_sha256"],
        "inventory_and_ledger_basename_sets_equal": {
            row["basename"] for row in inventory
        }
        == {row["basename"] for row in camera_ledger},
        "counts_962_937_25": (len(inventory), len(included), len(excluded))
        == (
            config["source_replay"]["expected_image_count"],
            config["source_replay"]["expected_included_count"],
            config["source_replay"]["expected_excluded_count"],
        ),
        "included_camera_ids_unique": len(camera_ids) == len(set(camera_ids)),
        "included_all_have_pose": all(
            row["calibrated_pose_present"] == "true" for row in included
        ),
        "excluded_all_lack_pose": all(
            row["calibrated_pose_present"] == "false" for row in excluded
        ),
        "exclusion_rule_exact": all(
            row["exclusion_reason"]
            == config["source_replay"]["expected_exclusion_rule"]
            for row in excluded
        ),
        "pose_member_hashes_exact": pose_members == current["pose_member_binding"],
        "sparse_member_records_exact": len(sparse["member_records"])
        == current["component_registry"]["sfm_sparse"]["member_count"],
        "prior_attestation_lf_hash_exact": sha256_bytes(lf_bytes(prior_path))
        == config["prior_evidence"]["r1_accepted_receipt_lf_sha256"],
        "prior_attestation_introducing_commit_exact": introduced_commit
        == config["prior_evidence"]["r1_accepted_receipt_commit"],
        "source_archives_match_prior_attestation": archive_attestation_match,
        "external_archives_remained_unopened_and_unhashed": True,
    }
    if not all(checks.values()):
        failed = [key for key, value in checks.items() if not value]
        raise RuntimeError(f"source candidate replay failed: {failed}")
    return {
        "schema": "jointbuildgs.gate_s0_r2a_source_candidate_replay.v1",
        "handoff_id": HANDOFF_ID,
        "task_id": TASK_ID,
        "source_candidate_id": current["common_image_pose_base_id"],
        "source_candidate_manifest_sha256": current[
            "source_candidate_manifest_sha256"
        ],
        "status": "REPLAY_EXACT_FROM_GIT_COMPACT_EVIDENCE",
        "counts": {
            "image_members": len(inventory),
            "included_image_pose_pairs": len(included),
            "excluded_no_pose": len(excluded),
            "unique_included_camera_ids": len(set(camera_ids)),
        },
        "set_hashes": {
            "included_basenames": sha256_lines(row["basename"] for row in included),
            "excluded_basenames": sha256_lines(row["basename"] for row in excluded),
            "included_camera_ids": sha256_lines(camera_ids),
            "included_image_camera_pairs": sha256_lines(
                f"{row['basename']}|{row['camera_id']}" for row in included
            ),
        },
        "pose_member_binding": pose_members,
        "prior_attestation": {
            "path": prior_path.as_posix(),
            "introducing_commit": introduced_commit,
            "lf_sha256": sha256_bytes(lf_bytes(prior_path)),
            "verification_level": prior["verification"]["level"],
            "record_count": len(prior["artifacts"]["records"]),
            "live_rehash_in_r2a": False,
        },
        "checks": checks,
        "contradictions": [],
        "candidate_not_human_frozen": True,
        "performance_authority": "NONE",
        "scientific_verdict": None,
    }


def path_has_forbidden_token(path: Path, tokens: list[str]) -> bool:
    lowered = path.as_posix().lower()
    return any(token.lower() in lowered for token in tokens)


def bounded_metadata_discovery(root: Path, config: dict[str, Any]) -> dict[str, Any]:
    discovery = config["derivative_discovery"]
    named: list[dict[str, Any]] = []
    for item in discovery["manifest_named_candidates"]:
        path = root / item["relative_path"]
        exists = path.is_file() and not path.is_symlink()
        observed_bytes = path.stat().st_size if exists else None
        named.append(
            {
                **item,
                "exists": exists,
                "observed_bytes": observed_bytes,
                "bytes_match_manifest": observed_bytes == item["bytes"],
                "content_read": False,
                "hash_recomputed": False,
            }
        )

    matches: list[dict[str, Any]] = []
    tokens = [value.lower() for value in discovery["filename_tokens"]]
    forbidden = discovery["forbidden_path_tokens"]
    for bounded in discovery["bounded_roots"]:
        scan_root = root / bounded["relative_path"]
        if not scan_root.is_dir() or scan_root.is_symlink():
            continue
        base_depth = len(scan_root.parts)
        for current, dirs, files in os.walk(scan_root):
            current_path = Path(current)
            depth = len(current_path.parts) - base_depth
            dirs[:] = sorted(
                value
                for value in dirs
                if depth < bounded["max_depth"]
                and not path_has_forbidden_token(current_path / value, forbidden)
            )
            if path_has_forbidden_token(current_path, forbidden):
                dirs[:] = []
                continue
            for name in sorted(files):
                lowered = name.lower()
                if not any(token in lowered for token in tokens):
                    continue
                path = current_path / name
                if path.is_symlink() or not path.is_file():
                    continue
                stat = path.stat()
                relative = path.relative_to(root).as_posix()
                if any(relative == item["relative_path"] for item in named):
                    continue
                matches.append(
                    {
                        "relative_path": relative,
                        "bytes": stat.st_size,
                        "classification": "AMBIGUOUS_UNBOUND_FILENAME_CANDIDATE",
                        "content_read": False,
                        "hash_recomputed": False,
                    }
                )
    return {
        "manifest_named_candidates": named,
        "bounded_discovery_matches": matches,
        "directory_entry_only": True,
        "payload_content_read_bytes": 0,
        "payload_hashed_bytes": 0,
    }


class HashingReader:
    def __init__(self, raw: BinaryIO) -> None:
        self.raw = raw
        self.digest = hashlib.sha256()
        self.bytes_read = 0

    def read(self, size: int = -1) -> bytes:
        value = self.raw.read(size)
        self.digest.update(value)
        self.bytes_read += len(value)
        return value


def parse_positions(element: ET.Element) -> list[tuple[float, float, float]]:
    values = [float(value) for value in (element.text or "").split()]
    if not values:
        return []
    dimension_text = attribute(element, "srsDimension")
    dimension = int(dimension_text) if dimension_text else 3
    if dimension not in (2, 3) or len(values) % dimension:
        raise RuntimeError(
            f"malformed coordinate sequence: dimension={dimension}, values={len(values)}"
        )
    if dimension == 2:
        return [(values[index], values[index + 1], float("nan")) for index in range(0, len(values), 2)]
    return [
        (values[index], values[index + 1], values[index + 2])
        for index in range(0, len(values), 3)
    ]


def coordinates_in(element: ET.Element) -> list[tuple[float, float, float]]:
    coordinates: list[tuple[float, float, float]] = []
    for child in element.iter():
        if local_name(child.tag) in {"posList", "pos"}:
            coordinates.extend(parse_positions(child))
    return coordinates


def ring_coordinates(container: ET.Element) -> list[tuple[float, float, float]]:
    rings = [item for item in container.iter() if local_name(item.tag) == "LinearRing"]
    if len(rings) != 1:
        raise RuntimeError(f"expected one LinearRing, found {len(rings)}")
    coordinates = coordinates_in(rings[0])
    if len(coordinates) < 4:
        raise RuntimeError("GroundSurface ring has fewer than four coordinates")
    if coordinates[0][:2] != coordinates[-1][:2]:
        coordinates.append(coordinates[0])
    return coordinates


def ground_polygons(building: ET.Element) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for ground in building.iter():
        if local_name(ground.tag) != "GroundSurface":
            continue
        polygon_elements = [
            item
            for item in ground.iter()
            if local_name(item.tag) in {"Polygon", "PolygonPatch"}
        ]
        for polygon in polygon_elements:
            exteriors = [
                item for item in polygon.iter() if local_name(item.tag) == "exterior"
            ]
            interiors = [
                item for item in polygon.iter() if local_name(item.tag) == "interior"
            ]
            if len(exteriors) != 1:
                raise RuntimeError(
                    f"GroundSurface polygon expected one exterior, found {len(exteriors)}"
                )
            exterior = ring_coordinates(exteriors[0])
            holes = [ring_coordinates(item) for item in interiors]
            output.append(
                {
                    "exterior_3d": exterior,
                    "interiors_3d": holes,
                }
            )
    return output


def building_record(building: ET.Element, source: dict[str, Any]) -> dict[str, Any]:
    stable_id = attribute(building, "id")
    if not stable_id:
        raise RuntimeError("source Building lacks gml:id")
    polygons = ground_polygons(building)
    if not polygons:
        raise RuntimeError(f"{stable_id}: no inline GroundSurface polygon")
    all_positions = coordinates_in(building)
    all_z = [value[2] for value in all_positions if value[2] == value[2]]
    ground_z = [
        value[2]
        for polygon in polygons
        for ring in [polygon["exterior_3d"], *polygon["interiors_3d"]]
        for value in ring
        if value[2] == value[2]
    ]
    if not all_z or not ground_z:
        raise RuntimeError(f"{stable_id}: 3D height envelope cannot be resolved")
    ground_height = min(ground_z)
    top_height = max(all_z)
    if top_height <= ground_height:
        raise RuntimeError(
            f"{stable_id}: non-positive height envelope {ground_height}..{top_height}"
        )
    footprint = [
        {
            "exterior": [[value[0], value[1]] for value in polygon["exterior_3d"]],
            "interiors": [
                [[value[0], value[1]] for value in ring]
                for ring in polygon["interiors_3d"]
            ],
        }
        for polygon in polygons
    ]
    return {
        "schema": "jointbuildgs.reference_derived_lod1_prism_record.v1",
        "source_tile": source["tile_id"],
        "source_asset_id": source["asset_id"],
        "stable_building_id": stable_id,
        "crs": "EPSG:25832",
        "vertical_datum": "DHHN2016",
        "footprint": footprint,
        "ground_height_m": ground_height,
        "top_height_m": top_height,
        "height_envelope_m": top_height - ground_height,
        "geometry_rule": "VERTICAL_MULTIPRISM_SINGLE_BUILDING_HEIGHT_ENVELOPE",
        "prior_role": PRIOR_ROLE,
        "evaluation_class": EVALUATION_CLASS,
        "primary_c5_eligible": False,
        "removed_information": [
            "roof_slope",
            "ridge",
            "face_adjacency",
            "roof_type",
            "semantic_evaluation_label",
            "RoofSurface topology",
        ],
    }


def process_source_once(path: Path, source: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if not path.is_file() or path.is_symlink():
        raise RuntimeError(f"LoD2 source missing or unsafe: {path}")
    observed_bytes = path.stat().st_size
    if observed_bytes != source["bytes"]:
        raise RuntimeError(
            f"LoD2 source byte mismatch before processing: {path}: {observed_bytes}"
        )
    records: list[dict[str, Any]] = []
    seen: set[str] = set()
    with path.open("rb") as raw:
        reader = HashingReader(raw)
        for _event, element in ET.iterparse(reader, events=("end",)):
            if local_name(element.tag) != "Building":
                continue
            record = building_record(element, source)
            stable_id = record["stable_building_id"]
            if stable_id in seen:
                raise RuntimeError(f"duplicate stable building ID in tile: {stable_id}")
            seen.add(stable_id)
            records.append(record)
            element.clear()
    observed_sha256 = reader.digest.hexdigest()
    if reader.bytes_read != source["bytes"]:
        raise RuntimeError(
            f"processing stream did not consume exact source bytes: {reader.bytes_read}"
        )
    if observed_sha256 != source["sha256"]:
        raise RuntimeError(
            f"LoD2 source SHA-256 mismatch in processing stream: {path}"
        )
    records.sort(key=lambda item: item["stable_building_id"])
    return records, {
        "uri": source["uri"],
        "bytes": reader.bytes_read,
        "sha256": observed_sha256,
        "digest_method": "same_stream_as_xml_iterparse",
        "full_byte_passes": 1,
    }


def strip_ring_closure(ring: list[list[float]]) -> list[list[float]]:
    if ring and ring[0] == ring[-1]:
        return ring[:-1]
    return ring


def build_cityjson(records: list[dict[str, Any]]) -> dict[str, Any]:
    vertices: list[list[float]] = []
    cityobjects: dict[str, Any] = {}

    all_xy = [
        coordinate
        for record in records
        for polygon in record["footprint"]
        for ring in [polygon["exterior"], *polygon["interiors"]]
        for coordinate in ring
    ]
    if not all_xy:
        raise RuntimeError("cannot serialize CityJSON without footprint coordinates")
    translate = [
        float(math.floor(min(value[0] for value in all_xy))),
        float(math.floor(min(value[1] for value in all_xy))),
        float(math.floor(min(record["ground_height_m"] for record in records))),
    ]
    scale = [0.001, 0.001, 0.001]

    def vertex(x: float, y: float, z: float) -> int:
        vertices.append(
            [
                int(round((x - translate[0]) / scale[0])),
                int(round((y - translate[1]) / scale[1])),
                int(round((z - translate[2]) / scale[2])),
            ]
        )
        return len(vertices) - 1

    for record in records:
        solids: list[Any] = []
        ground = record["ground_height_m"]
        top = record["top_height_m"]
        for polygon in record["footprint"]:
            rings = [polygon["exterior"], *polygon["interiors"]]
            bottom_rings: list[list[int]] = []
            top_rings: list[list[int]] = []
            wall_surfaces: list[list[list[int]]] = []
            for ring in rings:
                open_ring = strip_ring_closure(ring)
                if len(open_ring) < 3:
                    raise RuntimeError("footprint ring cannot form a prism")
                bottom = [vertex(x, y, ground) for x, y in open_ring]
                upper = [vertex(x, y, top) for x, y in open_ring]
                bottom_rings.append(bottom)
                top_rings.append(upper)
                for index in range(len(open_ring)):
                    nxt = (index + 1) % len(open_ring)
                    wall_surfaces.append(
                        [[bottom[index], bottom[nxt], upper[nxt], upper[index]]]
                    )
            surfaces: list[list[list[int]]] = [
                [list(reversed(ring)) for ring in bottom_rings],
                top_rings,
                *wall_surfaces,
            ]
            solids.append([surfaces])
        cityobjects[record["stable_building_id"]] = {
            "type": "Building",
            "attributes": {
                "source_tile": record["source_tile"],
                "prior_role": PRIOR_ROLE,
                "evaluation_class": EVALUATION_CLASS,
                "primary_c5_eligible": False,
                "ground_height_m": ground,
                "top_height_m": top,
            },
            "geometry": [
                {
                    "type": "MultiSolid",
                    "lod": "1",
                    "boundaries": solids,
                }
            ],
        }
    extent = [
        min(value[0] for value in all_xy),
        min(value[1] for value in all_xy),
        min(record["ground_height_m"] for record in records),
        max(value[0] for value in all_xy),
        max(value[1] for value in all_xy),
        max(record["top_height_m"] for record in records),
    ]
    return {
        "type": "CityJSON",
        "version": "2.0",
        "transform": {"scale": scale, "translate": translate},
        "metadata": {
            "referenceSystem": "https://www.opengis.net/def/crs/EPSG/0/25832",
            "geographicalExtent": extent,
            "presentLoDs": ["1"],
            "datasetTitle": "JointBuildGS reference-derived self-conditioned LoD1 diagnostic",
        },
        "CityObjects": cityobjects,
        "vertices": vertices,
    }


def cityjsonseq_bytes(records: list[dict[str, Any]]) -> tuple[bytes, dict[str, Any]]:
    from cjio import cityjson

    model = cityjson.CityJSON(j=build_cityjson(records))
    payload = model.export2jsonl().getvalue().encode("utf-8")
    previous_stdin = sys.stdin
    try:
        sys.stdin = io.StringIO(payload.decode("utf-8"))
        parsed = cityjson.read_stdin()
    finally:
        sys.stdin = previous_stdin
    expected_ids = [record["stable_building_id"] for record in records]
    parsed_ids = sorted(parsed.j["CityObjects"])
    if sorted(expected_ids) != parsed_ids:
        raise RuntimeError("cjio CityJSONSeq round-trip changed stable building IDs")
    for value in parsed.j["CityObjects"].values():
        if value["type"] != "Building":
            raise RuntimeError("cjio CityJSONSeq round-trip changed object type")
        if value["geometry"][0]["type"] != "MultiSolid":
            raise RuntimeError("cjio CityJSONSeq round-trip changed LoD1 geometry type")
    return payload, {
        "library": "cjio==0.10.1",
        "serialized": True,
        "parsed": True,
        "stable_id_set_equal": True,
        "building_count": len(parsed_ids),
    }


def output_payloads(
    records_by_tile: dict[str, list[dict[str, Any]]], config: dict[str, Any]
) -> tuple[dict[str, bytes], list[dict[str, Any]], dict[str, Any]]:
    payloads: dict[str, bytes] = {}
    lineages: list[dict[str, Any]] = []
    roundtrips: dict[str, Any] = {}
    namespace_uri = (
        "artifact://JointBuildGS/"
        + config["diagnostic"]["output_namespace_relative_path"]
    )
    source_by_tile = {
        value["tile_id"]: value for value in config["diagnostic"]["sources"]
    }
    for tile_id in sorted(records_by_tile):
        records = records_by_tile[tile_id]
        neutral_name = tile_id + config["diagnostic"]["neutral_output_suffix"]
        cityjson_name = tile_id + config["diagnostic"]["cityjsonseq_output_suffix"]
        neutral_lines = [compact_json_bytes(record) for record in records]
        neutral_payload = b"".join(neutral_lines)
        cityjson_payload, roundtrip = cityjsonseq_bytes(records)
        payloads[neutral_name] = neutral_payload
        payloads[cityjson_name] = cityjson_payload
        roundtrips[tile_id] = roundtrip
        for index, (record, line) in enumerate(zip(records, neutral_lines), start=1):
            lineages.append(
                {
                    "source_tile": tile_id,
                    "source_asset_id": source_by_tile[tile_id]["asset_id"],
                    "stable_building_id": record["stable_building_id"],
                    "neutral_output_uri": f"{namespace_uri}/{neutral_name}",
                    "neutral_record_line": index,
                    "neutral_record_sha256": sha256_bytes(line),
                    "cityjsonseq_output_uri": f"{namespace_uri}/{cityjson_name}",
                    "cityjsonseq_feature_line": index + 1,
                    "footprint_polygon_count": len(record["footprint"]),
                    "interior_ring_count": sum(
                        len(value["interiors"]) for value in record["footprint"]
                    ),
                    "ground_height_m": record["ground_height_m"],
                    "top_height_m": record["top_height_m"],
                    "prior_role": PRIOR_ROLE,
                    "evaluation_class": EVALUATION_CLASS,
                    "primary_c5_eligible": "false",
                }
            )
    return payloads, lineages, roundtrips


def promote_add_once(
    final_namespace: Path, payloads: dict[str, bytes]
) -> tuple[str, list[dict[str, Any]]]:
    expected = {
        name: {"bytes": len(value), "sha256": sha256_bytes(value)}
        for name, value in payloads.items()
    }
    if final_namespace.exists():
        if not final_namespace.is_dir() or final_namespace.is_symlink():
            raise RuntimeError("BLOCKED_NAMESPACE_CONFLICT: output namespace is unsafe")
        observed_names = sorted(path.name for path in final_namespace.iterdir())
        if observed_names != sorted(payloads):
            raise RuntimeError("BLOCKED_NAMESPACE_CONFLICT: output file set differs")
        for name, record in expected.items():
            path = final_namespace / name
            digest = hashlib.sha256()
            observed_bytes = 0
            with path.open("rb") as stream:
                for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
                    digest.update(block)
                    observed_bytes += len(block)
            if observed_bytes != record["bytes"] or digest.hexdigest() != record["sha256"]:
                raise RuntimeError("BLOCKED_NAMESPACE_CONFLICT: output bytes differ")
        status = "REUSED"
    else:
        final_namespace.parent.mkdir(parents=True, exist_ok=True)
        staging = final_namespace.parent / f".{final_namespace.name}.staging-{os.getpid()}"
        if staging.exists():
            raise RuntimeError(f"staging path already exists: {staging}")
        staging.mkdir()
        try:
            for name in sorted(payloads):
                with (staging / name).open("xb") as stream:
                    stream.write(payloads[name])
                    stream.flush()
                    os.fsync(stream.fileno())
            os.rename(staging, final_namespace)
        except Exception:
            if staging.exists():
                shutil.rmtree(staging)
            raise
        status = "EXECUTED_ADD_ONCE"
    records = [
        {
            "filename": name,
            "bytes": expected[name]["bytes"],
            "sha256": expected[name]["sha256"],
            "digest_method": "computed_from_serialized_bytes_before_add_once_write",
            "receipt_pre_push_full_rehashes": 0,
            "receipt_post_push_full_rehashes": 0,
        }
        for name in sorted(expected)
    ]
    return status, records


def build_derivative_matrix(
    config: dict[str, Any], discovery: dict[str, Any]
) -> dict[str, Any]:
    candidate = read_json(Path(config["source_candidate"]["path"]))
    sparse = read_json(Path(config["prior_evidence"]["sfm_sparse_evidence_path"]))
    ambiguous_paths = discovery["bounded_discovery_matches"]
    components: list[dict[str, Any]] = [
        {
            "component": "sfm_sparse",
            "status": "REUSED_EXACT",
            "source_member_relation": "16 exact OPF member records; 937 camera UIDs equal calibrated camera IDs",
            "producer_version": sparse["sparse"]["producer"],
            "code": "R1 compact member evidence; no R2A source replay",
            "config": "OPF project/scene binding from immutable R1 evidence",
            "coordinate_frame": sparse["coordinate_frame"],
            "scientific_role": "SHARED_IMAGE_DERIVED_INITIALIZATION_SUPPORT_CANDIDATE",
            "uri": candidate["source_archives"]["camera_pose_opf"]["uri"],
            "bytes": sum(item["decompressed_bytes"] for item in sparse["member_records"]),
            "hash": candidate["component_registry"]["sfm_sparse"][
                "member_manifest_sha256"
            ],
            "hash_scope": "canonical manifest of exact member records",
            "next_requirement": "Bind or generate one canonical sparse derivative without repeating R1 member hashing.",
            "gate_enablement": None,
        }
    ]
    named_dense = discovery["manifest_named_candidates"][0]
    for component in ("dense_mvs", "depth", "normal", "confidence"):
        component_matches = [
            item
            for item in ambiguous_paths
            if component.split("_")[0] in item["relative_path"].lower()
        ]
        status = "AMBIGUOUS" if component_matches else "MISSING"
        item: dict[str, Any] = {
            "component": component,
            "status": status,
            "source_member_relation": None,
            "producer_version": None,
            "code": None,
            "config": None,
            "coordinate_frame": None,
            "scientific_role": f"SHARED_IMAGE_DERIVED_{component.upper()}_CANDIDATE",
            "uri": None,
            "bytes": None,
            "hash": None,
            "hash_scope": None,
            "bounded_unbound_candidates": component_matches,
            "next_requirement": (
                "Execute the matching shared DAG node once after human selection of producer/config/frame/role; "
                "do not create an arm-specific derivative."
            ),
            "gate_enablement": None,
        }
        if component == "dense_mvs":
            item["ineligible_context_candidate"] = named_dense
            item["next_requirement"] = (
                "Generate or bind one exact-937-base shared dense MVS derivative. The 1,104-image vendor MVS "
                "remains context-only and cannot satisfy this requirement."
            )
        components.append(item)
    return {
        "schema": "jointbuildgs.gate_s0_r2a_derivative_provenance_matrix.v1",
        "handoff_id": HANDOFF_ID,
        "task_id": TASK_ID,
        "source_candidate_id": config["source_candidate"]["id"],
        "resolution_order": [
            "Git manifest-named candidates",
            "exact manifest paths by metadata only",
            "bounded work-tree filename discovery without content read or hash",
        ],
        "components": components,
        "missing_derivatives_generated": False,
        "component_enablement_selected": False,
        "performance_authority": "NONE",
        "scientific_verdict": None,
    }


def update_ledger(
    ledger: dict[str, Any],
    replay: dict[str, Any],
    discovery: dict[str, Any],
    source_streams: dict[str, dict[str, Any]],
    output_records: list[dict[str, Any]],
    promotion_status: str,
) -> dict[str, Any]:
    by_name = {item["name"]: item for item in ledger["operations"]}
    git_paths = [
        IMAGE_INVENTORY,
        IMAGE_CAMERA_LEDGER,
        INPUT_MANIFEST,
        SOURCE_BUILDER,
        Path(read_json(CONFIG_PATH)["source_candidate"]["path"]),
        Path(read_json(CONFIG_PATH)["prior_evidence"]["r1_accepted_receipt_path"]),
        Path(read_json(CONFIG_PATH)["prior_evidence"]["sfm_sparse_evidence_path"]),
    ]
    by_name["source_candidate_replay"].update(
        {
            "status": "EXECUTED_GIT_COMPACT_ONLY",
            "read_bytes": sum(len(lf_bytes(path)) for path in git_paths),
            "hashed_bytes": sum(len(lf_bytes(path)) for path in git_paths),
            "result": replay["status"],
        }
    )
    by_name["derivative_resolution"].update(
        {
            "status": "EXECUTED_METADATA_ONLY",
            "read_bytes": 0,
            "hashed_bytes": 0,
            "manifest_named_candidate_count": len(
                discovery["manifest_named_candidates"]
            ),
            "bounded_unbound_candidate_count": len(
                discovery["bounded_discovery_matches"]
            ),
        }
    )
    for tile_id, stream in source_streams.items():
        by_name[f"lod2_to_lod1_diagnostic_{tile_id}"].update(
            {
                "status": promotion_status,
                "read_bytes": stream["bytes"],
                "hashed_bytes": stream["bytes"],
                "source_sha256": stream["sha256"],
                "source_digest_passes": 1,
                "separate_source_hash_passes": 0,
            }
        )
    return {
        **ledger,
        "payload_operations_started": True,
        "completed": True,
        "operations": list(by_name.values()),
        "totals": {
            "closed_r1_bundle_repeated_read_bytes": 0,
            "images_zip_read_bytes": 0,
            "opf_zip_read_bytes": 0,
            "lod2_source_read_bytes": sum(item["bytes"] for item in source_streams.values()),
            "lod2_source_hashed_bytes": sum(item["bytes"] for item in source_streams.values()),
            "new_external_output_count": len(output_records),
            "new_external_output_bytes": sum(item["bytes"] for item in output_records),
            "output_full_rehash_passes_before_first_artifact_receipt": 0,
            "output_receipt_pre_push_passes_pending": 1,
            "output_receipt_post_push_passes_pending": 1,
            "successor_300_output_rehash_passes": 0,
        },
        "duplicate_work_guard_events": [
            {
                "code": "DUPLICATE_WORK_GUARD",
                "event": "R1 source bundle, Images.zip, OPF.zip and R1 sparse member hash pass were not repeated.",
                "triggered_stop": False,
            },
            {
                "code": "DUPLICATE_WORK_GUARD",
                "event": "Missing dense/depth/normal/confidence derivatives were recorded but not generated.",
                "triggered_stop": False,
            },
        ],
        "scientific_verdict": None,
        "performance_authority": "NONE",
    }


def write_issue_log(matrix: dict[str, Any], discovery: dict[str, Any]) -> None:
    statuses = {item["component"]: item["status"] for item in matrix["components"]}
    text = f"""# Gate S0 Evidence R2A issue log v1

- task_id: `{TASK_ID}`
- proposed_status: `BLOCKED_FOR_GATE_S0_EVIDENCE_REVIEW`
- scientific_verdict: null
- performance_authority: `NONE`

## Findings

| ID | State | Finding | Next idempotent action |
|---|---|---|---|
| R2A-I01 | `{statuses['sfm_sparse']}` | Exact R1 sparse member evidence is reusable, but one canonical converted derivative or an explicit bound-member consumption contract is still absent. | Execute the shared `sfm_sparse` DAG node once after Gate review; do not repeat R1 member hashing. |
| R2A-I02 | `{statuses['dense_mvs']}` | No exact-937-base dense MVS derivative is bound. The 1,104-image vendor MVS is context-only and ineligible. | Select producer/config/frame in a later approved preprocessing task and execute the shared node once. |
| R2A-I03 | `{statuses['depth']}` | Exact-base depth is not bound. | Generate only after the shared dense-MVS identity is frozen. |
| R2A-I04 | `{statuses['normal']}` | Exact-base normal evidence is not bound. | Generate only under the shared DAG and record orientation/frame. |
| R2A-I05 | `{statuses['confidence']}` | Exact-base image-derived confidence is not bound. | Keep confidence definition null until human review; separate it from external-prior confidence. |
| R2A-I06 | `DIAGNOSTIC_ONLY` | LoD2-derived LoD1 is self-conditioned against the same reference lineage. | Keep `primary_c5_eligible=false`; do not place it in primary C5, E_paired or Delta_N_pass(C5). |
| R2A-I07 | `BLOCKED` | Gate S0, U_target/E_paired, split, component enablement and performance remain unfrozen. | Human Gate S0 evidence review after this return. |

## Duplicate-work guard

- Closed R1 15.7 GB inputs, `Images.zip`, `opf.zip` and R1 sparse members were not rehashed.
- Dense MVS, depth, normal and confidence were not generated.
- Bounded discovery used directory entries and file metadata only; content-read bytes: `0`, hashed bytes: `0`.
- Bounded unbound filename candidates: `{len(discovery['bounded_discovery_matches'])}`.
- Each LoD2 source was consumed once by the processing-and-digest stream.
- New LoD1 outputs await exactly one pre-push and one post-push first-artifact-receipt safety pass; `300-closed` must not rehash them.

## Prohibited activity attestation

No C1-C5 performance, GS training, Roofer comparison, held-out, Fusion W1 or `R_ext`
path was read, executed or written. No existing external file was overwritten or deleted.
"""
    ISSUE_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    ISSUE_LOG_PATH.write_text(text, encoding="utf-8", newline="\n")


def execute(config: dict[str, Any], artifact_root: Path) -> None:
    if not LEDGER_PATH.is_file():
        raise RuntimeError("reuse ledger must be initialized before payload operations")
    ledger = read_json(LEDGER_PATH)
    if ledger["payload_operations_started"] or ledger["completed"]:
        raise RuntimeError("reuse ledger says payload operations already started")
    final_namespace = artifact_root / config["diagnostic"][
        "output_namespace_relative_path"
    ]
    if final_namespace.exists() and not DIAGNOSTIC_MANIFEST_PATH.is_file():
        raise RuntimeError(
            "BLOCKED_NAMESPACE_CONFLICT: namespace exists without a compact R2A manifest"
        )

    replay = replay_source_candidate(config)
    discovery = bounded_metadata_discovery(artifact_root, config)
    records_by_tile: dict[str, list[dict[str, Any]]] = {}
    source_streams: dict[str, dict[str, Any]] = {}
    all_ids: set[str] = set()
    for source in config["diagnostic"]["sources"]:
        records, stream = process_source_once(
            artifact_root / source["relative_path"], source
        )
        duplicate = all_ids.intersection(
            record["stable_building_id"] for record in records
        )
        if duplicate:
            raise RuntimeError(
                f"stable building IDs duplicate across source tiles: {sorted(duplicate)[:5]}"
            )
        all_ids.update(record["stable_building_id"] for record in records)
        records_by_tile[source["tile_id"]] = records
        source_streams[source["tile_id"]] = stream

    payloads, lineages, roundtrips = output_payloads(records_by_tile, config)
    promotion_status, output_records = promote_add_once(final_namespace, payloads)
    namespace_uri = (
        "artifact://JointBuildGS/"
        + config["diagnostic"]["output_namespace_relative_path"]
    )
    for record in output_records:
        record["uri"] = f"{namespace_uri}/{record.pop('filename')}"
        record["verification_status"] = (
            "STREAM_DIGEST_BOUND_PENDING_FIRST_ARTIFACT_RECEIPT"
        )
        record["prior_role"] = PRIOR_ROLE
        record["evaluation_class"] = EVALUATION_CLASS
        record["primary_c5_eligible"] = False

    matrix = build_derivative_matrix(config, discovery)
    diagnostic_manifest = {
        "schema": "jointbuildgs.gate_s0_r2a_lod2_derived_lod1_manifest.v1",
        "handoff_id": HANDOFF_ID,
        "task_id": TASK_ID,
        "status": promotion_status,
        "source_digest_rule": "computed in the sole XML processing stream",
        "height_rule": config["diagnostic"]["height_rule"],
        "source_records": [source_streams[key] for key in sorted(source_streams)],
        "output_namespace": namespace_uri,
        "output_records": output_records,
        "tile_summaries": [
            {
                "tile_id": tile_id,
                "building_count": len(records_by_tile[tile_id]),
                "stable_id_unique_count": len(
                    {record["stable_building_id"] for record in records_by_tile[tile_id]}
                ),
                "footprint_polygon_count": sum(
                    len(record["footprint"]) for record in records_by_tile[tile_id]
                ),
                "interior_ring_count": sum(
                    len(polygon["interiors"])
                    for record in records_by_tile[tile_id]
                    for polygon in record["footprint"]
                ),
                "coverage": "all parsed source Building records",
                "cityjsonseq_roundtrip": roundtrips[tile_id],
            }
            for tile_id in sorted(records_by_tile)
        ],
        "combined_building_count": len(all_ids),
        "combined_stable_id_unique_count": len(all_ids),
        "prior_role": PRIOR_ROLE,
        "evaluation_class": EVALUATION_CLASS,
        "primary_c5_eligible": False,
        "roof_slope_or_topology_transferred": False,
        "roof_type_transferred": False,
        "semantic_evaluation_label_transferred": False,
        "performance_scored": False,
        "e_paired_promoted": False,
        "scientific_verdict": None,
    }
    write_json(SOURCE_REPLAY_PATH, replay)
    write_json(DERIVATIVE_MATRIX_PATH, matrix)
    write_json(DIAGNOSTIC_MANIFEST_PATH, diagnostic_manifest)
    write_csv(
        LINEAGE_PATH,
        [
            "source_tile",
            "source_asset_id",
            "stable_building_id",
            "neutral_output_uri",
            "neutral_record_line",
            "neutral_record_sha256",
            "cityjsonseq_output_uri",
            "cityjsonseq_feature_line",
            "footprint_polygon_count",
            "interior_ring_count",
            "ground_height_m",
            "top_height_m",
            "prior_role",
            "evaluation_class",
            "primary_c5_eligible",
        ],
        lineages,
    )
    write_issue_log(matrix, discovery)
    write_json(
        LEDGER_PATH,
        update_ledger(
            ledger,
            replay,
            discovery,
            source_streams,
            output_records,
            promotion_status,
        ),
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--initialize-ledger", action="store_true")
    mode.add_argument("--execute", action="store_true")
    parser.add_argument("--artifact-root", type=Path)
    args = parser.parse_args()
    config = read_json(CONFIG_PATH)
    if args.initialize_ledger:
        write_json(LEDGER_PATH, initialize_ledger(config))
        write_json(DAG_PATH, build_preprocessing_dag(config))
        return 0
    if args.artifact_root is None:
        raise SystemExit("--artifact-root is required with --execute")
    execute(config, args.artifact_root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
