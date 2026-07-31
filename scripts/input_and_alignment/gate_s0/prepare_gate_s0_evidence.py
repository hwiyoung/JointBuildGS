#!/usr/bin/env python3
"""Generate deterministic, outcome-free Gate S0 evidence from exact inputs."""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
import zipfile
from collections import Counter
from pathlib import Path
from typing import Any

import laspy


DEFAULT_CONFIG = Path("configs/input_and_alignment/gate_s0/gate_s0_evidence_v1.json")
DOC_ROOT = Path("docs/research/preregistration/gate_s0")
MANIFEST_ROOT = Path("artifacts/manifests/gate_s0")
LEDGER_PATH = DOC_ROOT / "gate_s0_image_camera_ledger_v1.csv"
IMAGE_INVENTORY_PATH = MANIFEST_ROOT / "gate_s0_image_member_inventory_v1.csv"
INPUT_MANIFEST_PATH = DOC_ROOT / "gate_s0_input_manifest_v1.json"
ARTIFACT_RECORDS_PATH = MANIFEST_ROOT / "gate_s0_live_artifact_records_v1.json"
READINESS_PATH = DOC_ROOT / "gate_s0_condition_readiness_v1.csv"
FUNNEL_PATH = DOC_ROOT / "gate_s0_eligibility_funnel_v1.csv"
COST_PATH = DOC_ROOT / "gate_s0_cost_bounds_v1.csv"
SPLIT_PATH = DOC_ROOT / "gate_s0_split_proposal_v1.json"
AOI_PATH = MANIFEST_ROOT / "gate_s0_candidate_aoi_v1.geojson"
LOD1_SEARCH_PATH = MANIFEST_ROOT / "gate_s0_lod1_search_v1.json"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def artifact_uri(relative: str) -> str:
    return f"artifact://JointBuildGS/{relative}"


def verify_files(root: Path, config: dict[str, Any]) -> list[dict[str, Any]]:
    verified: list[dict[str, Any]] = []
    for record in config["files"]:
        path = root / record["relative_path"]
        if not path.is_file() or path.is_symlink():
            raise RuntimeError(f"missing or unsafe exact input: {path}")
        measured_bytes = path.stat().st_size
        measured_sha256 = sha256_file(path)
        if measured_bytes != record["expected_bytes"]:
            raise RuntimeError(f"byte mismatch: {path}")
        if measured_sha256 != record["expected_sha256"]:
            raise RuntimeError(f"SHA-256 mismatch: {path}")
        verified.append(
            {
                **record,
                "uri": artifact_uri(record["relative_path"]),
                "bytes": measured_bytes,
                "sha256": measured_sha256,
                "verification_method": "sha256_rehash",
                "verified_by": "experiment_host",
                "verified_at": config["observed_at"],
            }
        )
    return verified


def image_camera_evidence(
    root: Path, config: dict[str, Any]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    image_path = root / next(
        item["relative_path"]
        for item in config["files"]
        if item["asset_id"] == "IMG_CURRENT_ARCHIVE"
    )
    opf_path = root / next(
        item["relative_path"]
        for item in config["files"]
        if item["asset_id"] == "CAM_CURRENT_OPF"
    )
    inventory: list[dict[str, Any]] = []
    with zipfile.ZipFile(image_path) as archive:
        members = sorted(
            (item for item in archive.infolist() if not item.is_dir()),
            key=lambda item: Path(item.filename).name,
        )
        image_names: set[str] = set()
        for member in members:
            basename = Path(member.filename).name
            if basename in image_names:
                raise RuntimeError(f"duplicate image basename: {basename}")
            image_names.add(basename)
            digest = hashlib.sha256()
            with archive.open(member) as stream:
                for block in iter(lambda: stream.read(4 * 1024 * 1024), b""):
                    digest.update(block)
            inventory.append(
                {
                    "basename": basename,
                    "archive_member": member.filename,
                    "uncompressed_bytes": member.file_size,
                    "compressed_bytes": member.compress_size,
                    "crc32_hex": f"{member.CRC:08x}",
                    "sha256": digest.hexdigest(),
                }
            )
    with zipfile.ZipFile(opf_path) as archive:
        def load(name: str) -> dict[str, Any]:
            return json.loads(archive.read(name))

        camera_list = load("opf/camera_list.json")["cameras"]
        input_cameras = load("opf/input_cameras.json")["captures"]
        projected = load("opf/projected_input_cameras.json")["captures"]
        calibrated = load("opf/calibrated_cameras.json")["cameras"]
        member_hashes = {
            name: {
                "bytes": len(archive.read(name)),
                "sha256": sha256_bytes(archive.read(name)),
            }
            for name in (
                "opf/camera_list.json",
                "opf/calibrated_cameras.json",
                "opf/input_cameras.json",
                "opf/projected_input_cameras.json",
                "opf/project.opf",
                "opf/scene_reference_frame.json",
            )
        }
    input_ids = {int(item["id"]) for item in input_cameras}
    projected_ids = {int(item["id"]) for item in projected}
    calibrated_ids = {int(item["id"]) for item in calibrated}
    image_names = {item["basename"] for item in inventory}
    ledger: list[dict[str, Any]] = []
    for camera in sorted(camera_list, key=lambda item: Path(item["uri"]).name):
        basename = Path(camera["uri"]).name
        camera_id = int(camera["id"])
        has_pose = camera_id in calibrated_ids
        ledger.append(
            {
                "basename": basename,
                "camera_id": str(camera_id),
                "image_in_zip": str(basename in image_names).lower(),
                "input_capture_present": str(camera_id in input_ids).lower(),
                "calibrated_pose_present": str(has_pose).lower(),
                "status": "INCLUDED" if has_pose else "EXCLUDED",
                "exclusion_reason": "" if has_pose else config["image_camera_contract"]["exclusion_reason"],
            }
        )
    expected = config["image_camera_contract"]
    if len(inventory) != expected["image_count"]:
        raise RuntimeError("unexpected image count")
    if len(camera_list) != expected["camera_list_count"]:
        raise RuntimeError("unexpected camera-list count")
    if len(calibrated_ids) != expected["calibrated_pose_count"]:
        raise RuntimeError("unexpected calibrated-pose count")
    excluded = [item for item in ledger if item["status"] == "EXCLUDED"]
    if len(excluded) != expected["excluded_count"]:
        raise RuntimeError("unexpected exclusion count")
    if any(item["image_in_zip"] != "true" for item in ledger):
        raise RuntimeError("OPF camera list does not match image archive")
    if any(item["input_capture_present"] != "true" for item in ledger):
        raise RuntimeError("OPF camera list does not match input captures")
    if projected_ids != input_ids:
        raise RuntimeError("projected and input capture ID sets differ")
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=list(ledger[0]), lineterminator="\n")
    writer.writeheader()
    writer.writerows(ledger)
    ledger_bytes = buffer.getvalue().encode("utf-8")
    included_names = "".join(
        f"{item['basename']}\n" for item in ledger if item["status"] == "INCLUDED"
    ).encode("utf-8")
    all_names = "".join(f"{item['basename']}\n" for item in ledger).encode("utf-8")
    summary = {
        "image_count": len(inventory),
        "camera_list_count": len(camera_list),
        "input_capture_count": len(input_ids),
        "projected_input_count": len(projected_ids),
        "calibrated_pose_count": len(calibrated_ids),
        "included_count": len(ledger) - len(excluded),
        "excluded_count": len(excluded),
        "ledger_bytes": len(ledger_bytes),
        "ledger_sha256": sha256_bytes(ledger_bytes),
        "all_basename_set_sha256": sha256_bytes(all_names),
        "included_basename_set_sha256": sha256_bytes(included_names),
        "opf_member_hashes": member_hashes,
        "join_rule": "Exact case-sensitive basename after normalizing only the archive directory component.",
        "exclusion_reason": expected["exclusion_reason"],
    }
    return ledger, inventory, summary


def point_cloud_metadata(root: Path, verified: list[dict[str, Any]]) -> dict[str, Any]:
    metadata: dict[str, Any] = {}
    for record in verified:
        if not record["relative_path"].lower().endswith((".las", ".laz")):
            continue
        path = root / record["relative_path"]
        with laspy.open(path) as reader:
            header = reader.header
            count = int(header.point_count)
            chunk = min(250_000, count)
            starts = sorted({0, max(0, count // 2 - chunk // 2), max(0, count - chunk)})
            classes: Counter[int] = Counter()
            sampled = 0
            for start in starts:
                reader.seek(start)
                points = reader.read_points(chunk)
                classes.update(int(value) for value in points.classification)
                sampled += len(points)
            width = float(header.maxs[0]) - float(header.mins[0])
            height = float(header.maxs[1]) - float(header.mins[1])
            metadata[record["asset_id"]] = {
                "las_version": str(header.version),
                "point_format": int(header.point_format.id),
                "point_count": count,
                "bounds": {
                    "min": [round(float(value), 4) for value in header.mins],
                    "max": [round(float(value), 4) for value in header.maxs],
                },
                "gross_bbox_density_points_per_m2": round(count / (width * height), 6),
                "creation_date": str(header.creation_date),
                "generating_software": str(header.generating_software),
                "bounded_class_sample": {
                    "algorithm": "first/middle/last 250000-point chunks",
                    "starts": starts,
                    "sampled_points": sampled,
                    "counts": {str(key): value for key, value in sorted(classes.items())},
                },
                "vlr_ids": [
                    {
                        "user_id": str(getattr(vlr, "user_id", "")),
                        "record_id": int(getattr(vlr, "record_id", -1)),
                    }
                    for vlr in header.vlrs
                    if str(getattr(vlr, "user_id", "")) != "laszip encoded"
                ],
            }
    return metadata


def bounded_lod1_search(root: Path, config: dict[str, Any]) -> dict[str, Any]:
    """Inventory a fixed raw-input scope without reading model geometry."""
    relative_scope = Path("phase-payloads/p0-audit/data/raw")
    search_root = root / relative_scope
    max_depth = 4
    if not search_root.is_dir() or search_root.is_symlink():
        raise RuntimeError(f"missing or unsafe LoD1 search root: {search_root}")
    inventory: list[tuple[str, int]] = []
    candidates: list[dict[str, Any]] = []
    lod1_matches: list[str] = []
    for path in sorted(search_root.rglob("*")):
        if path.is_symlink() or not path.is_file():
            continue
        relative_inside = path.relative_to(search_root)
        if len(relative_inside.parts) > max_depth:
            continue
        relative = (relative_scope / relative_inside).as_posix()
        size = path.stat().st_size
        inventory.append((relative, size))
        name_lower = path.name.lower()
        suffix_lower = path.suffix.lower()
        name_match = "lod1" in name_lower
        model_suffix = suffix_lower in {".gml", ".cityjson", ".jsonl"}
        if name_match:
            lod1_matches.append(relative)
        if name_match or model_suffix:
            candidates.append(
                {
                    "relative_path": relative,
                    "bytes": size,
                    "name_contains_lod1": name_match,
                    "model_suffix_match": model_suffix,
                    "classification": "LOD1_NAME_MATCH" if name_match else "NON_LOD1_MODEL_FILE",
                }
            )
    inventory_bytes = "".join(f"{path}|{size}\n" for path, size in inventory).encode("utf-8")
    payload = {
        "schema": "jointbuildgs.gate_s0_lod1_search.v1",
        "handoff_id": config["handoff_id"],
        "observed_at": config["observed_at"],
        "artifact_root": config["artifact_root_uri"],
        "relative_scope": relative_scope.as_posix(),
        "max_depth": max_depth,
        "algorithm": "sorted regular non-symlink file inventory; case-insensitive filename contains lod1 OR suffix in .gml/.cityjson/.jsonl; no model geometry read",
        "inventory_entry_count": len(inventory),
        "inventory_bytes": len(inventory_bytes),
        "inventory_sha256": sha256_bytes(inventory_bytes),
        "candidate_matches": candidates,
        "lod1_matches": lod1_matches,
        "status": "MISSING" if not lod1_matches else "FOUND_REQUIRES_LINEAGE_REVIEW",
        "prohibited_substitute": config["lod1_search"]["prohibited_substitute"],
    }
    write_json(LOD1_SEARCH_PATH, payload)
    return payload


def build_readiness_rows() -> list[dict[str, str]]:
    rows = [
        ("C1_L_upper", "selected_source", "PARTIAL", "LIDAR_UAS_CURRENT_NADIR exact bytes; unregistered UTM32 numeric bbox screening supports nadir-only provisional proposal", "verified EPSG:32632-to-EPSG:25832 transform/residual, per-building coverage and Gate review"),
        ("C1_L_upper", "class_2_6", "MISSING", "bounded raw sample is class 0 only", "provenance-bound ground=2/building=6 derivative"),
        ("C1_L_upper", "crs_vertical_registration", "UNKNOWN", "horizontal EPSG:32632 evidence; vertical datum and residual unresolved", "frozen EPSG:25832/DHHN2016 pipeline and residual"),
        ("C1_L_upper", "coverage", "UNKNOWN", "numeric bbox screening only; source and target UTM32 frames are not yet registered", "verified transform/residual and per-building class-specific coverage"),
        ("C2_MVS", "identity", "PARTIAL", "Pix4D exact live bytes and header verified", "hash-linked producer/replay receipt"),
        ("C2_MVS", "same_image_camera_base", "PARTIAL", "937-image OPF ledger is available but MVS-to-ledger derivation is not hash-bound", "producer receipt or replay from frozen 937 ledger"),
        ("C2_MVS", "class_2_6", "MISSING", "bounded MVS sample is class 0 only", "frozen Roofer classification derivative"),
        ("C2_MVS", "crs_vertical_registration", "PARTIAL", "EPSG:32632 plus EGM96 evidence", "frozen transform to EPSG:25832/DHHN2016 and residual"),
        ("C3_GS_image", "image_camera_base", "PARTIAL", "937 exact OPF calibrated IDs proposed", "building view coverage and freeze receipt"),
        ("C3_GS_image", "dense_mvs_separation", "READY", "contract prohibits dense MVS geometry/depth/normal input", "enforce in later config validator"),
        ("C4_GS_lidar_prior", "als_identity", "PARTIAL", "four exact 2022 ALS tiles rehashed", "provider/header CRS binding and derivative receipt"),
        ("C4_GS_lidar_prior", "c1_independence", "PARTIAL", "different files, survey years, platform regimes and classes", "formal derivative independence and registration receipt"),
        ("C4_GS_lidar_prior", "prior_interface", "PARTIAL", "future data fields proposed without a loss equation", "implementation and confidence semantics deferred to later authorized work"),
        ("C4_GS_lidar_prior", "coverage_registration", "UNKNOWN", "tile bbox exists; common-building overlap/residual absent", "building-level overlap and cross-modal residual"),
        ("C5_GS_lod1_prior", "independent_lod1", "MISSING", "no LoD1 in the fixed approved raw-input search scope", "obtain independent provider asset; no LoD2 substitute"),
        ("C5_GS_lod1_prior", "leakage_guard", "READY", "scored LoD2 simplification/extrusion explicitly prohibited", "retain guard in future manifest"),
        ("ALL", "R_derived_common_protocol", "PARTIAL", "contract defined; no campaign-wide non-GT code/config/hash", "common derivation implementation and method-specific polygon hashes"),
        ("ALL", "gravity", "UNKNOWN", "must be estimated once from terrain MVS normals", "source normals, estimator, vector and hash"),
        ("ALL", "U_target", "UNKNOWN", "199 reference intersections are not U_target", "stable-ID and current-image coverage join"),
        ("ALL", "E_paired", "UNKNOWN", "C5 MISSING and C1-C4 prerequisites incomplete", "all-condition eligibility manifest"),
        ("ALL", "cost_ceiling", "UNKNOWN", "no comparable non-held-out per-condition calibration receipt", "bounded calibration without performance results"),
        ("ALL", "CityJSON_writer", "PARTIAL", "repository writer compiles and cjio 0.10.1 exists", "integrated C1-C5 writer tests and schema validator"),
        ("ALL", "CityGML_cjval_val3dity", "MISSING", "main image lacks trusted converter, cjval and val3dity executables", "pinned callable toolchain and tests"),
    ]
    return [
        {
            "condition": condition,
            "field": field,
            "status": status,
            "evidence": evidence,
            "required_next_evidence": next_evidence,
        }
        for condition, field, status, evidence, next_evidence in rows
    ]


def build_funnel_rows(config: dict[str, Any]) -> list[dict[str, Any]]:
    count = config["candidate_aoi"]["provisional_reference_intersections"]
    return [
        {
            "stage": "CANDIDATE_AOI_REFERENCE_INTERSECTIONS",
            "unit_id": "AGGREGATE_ONLY",
            "count": count,
            "status": "PARTIAL",
            "included": "UNKNOWN",
            "exclusion_reason": "Reference-intersection count is not an outcome-free stable-ID U_target ledger.",
            "held_out_accessed": "false",
        },
        {
            "stage": "U_target",
            "unit_id": "NOT_ASSIGNED",
            "count": "",
            "status": "UNKNOWN",
            "included": "UNKNOWN",
            "exclusion_reason": "No safe building-level stable-ID plus current-image coverage join; no IDs fabricated.",
            "held_out_accessed": "false",
        },
        {
            "stage": "C1_ELIGIBLE",
            "unit_id": "NOT_ASSIGNED",
            "count": "",
            "status": "UNKNOWN",
            "included": "UNKNOWN",
            "exclusion_reason": "C1 class-2/6, vertical datum and registration unresolved.",
            "held_out_accessed": "false",
        },
        {
            "stage": "C2_ELIGIBLE",
            "unit_id": "NOT_ASSIGNED",
            "count": "",
            "status": "UNKNOWN",
            "included": "UNKNOWN",
            "exclusion_reason": "C2 class/transform and exact common-ledger derivation unresolved.",
            "held_out_accessed": "false",
        },
        {
            "stage": "C3_ELIGIBLE",
            "unit_id": "NOT_ASSIGNED",
            "count": "",
            "status": "UNKNOWN",
            "included": "UNKNOWN",
            "exclusion_reason": "Building-level image view support and common R_derived protocol unresolved.",
            "held_out_accessed": "false",
        },
        {
            "stage": "C4_ELIGIBLE",
            "unit_id": "NOT_ASSIGNED",
            "count": "",
            "status": "UNKNOWN",
            "included": "UNKNOWN",
            "exclusion_reason": "ALS independence, registration and building overlap unresolved.",
            "held_out_accessed": "false",
        },
        {
            "stage": "C5_ELIGIBLE",
            "unit_id": "NOT_ASSIGNED",
            "count": 0,
            "status": "MISSING",
            "included": "false",
            "exclusion_reason": "Independent LoD1 not found in fixed scope; scored LoD2 substitute prohibited.",
            "held_out_accessed": "false",
        },
        {
            "stage": "E_paired",
            "unit_id": "NOT_ASSIGNED",
            "count": "",
            "status": "UNKNOWN",
            "included": "UNKNOWN",
            "exclusion_reason": "Cannot compute until U_target and all C1-C5 attemptability are evidenced.",
            "held_out_accessed": "false",
        },
    ]


def build_cost_rows(verified: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_id = {item["asset_id"]: item for item in verified}
    images = by_id["IMG_CURRENT_ARCHIVE"]["bytes"] + by_id["CAM_CURRENT_OPF"]["bytes"]
    als = sum(item["bytes"] for key, item in by_id.items() if key.startswith("ALS_EXISTING_"))
    entries = [
        ("C1_L_upper", by_id["LIDAR_UAS_CURRENT_NADIR"]["bytes"], "UNKNOWN", "UNKNOWN", "UNKNOWN", "PARTIAL", "Exact selected input bytes only; no class/Roofer calibration receipt."),
        ("C2_MVS", by_id["MVS_CURRENT_PIX4D"]["bytes"], "UNKNOWN", "UNKNOWN", "UNKNOWN", "PARTIAL", "Exact MVS input bytes only; no common-ledger adapter/Roofer calibration receipt."),
        ("C3_GS_image", images, "UNKNOWN", "UNKNOWN", "UNKNOWN", "UNKNOWN", "Image+OPF input bytes are exact; no comparable non-held-out training/extraction calibration."),
        ("C4_GS_lidar_prior", images + als, "UNKNOWN", "UNKNOWN", "UNKNOWN", "UNKNOWN", "Image+OPF+ALS input bytes are exact; prior method and calibration deferred."),
        ("C5_GS_lod1_prior", images, "UNKNOWN", "UNKNOWN", "UNKNOWN", "MISSING", "Independent LoD1 input is missing; total input and execution cost cannot be bounded."),
    ]
    return [
        {
            "condition": condition,
            "known_input_bytes": known_input,
            "runtime_bound": runtime,
            "peak_memory_bound": memory,
            "output_bytes_bound": output,
            "status": status,
            "assumptions_and_limitation": limitation,
            "retention_policy": "raw inputs immutable; outputs require new run namespace; failed outputs retained by frozen policy",
            "held_out_accessed": "false",
        }
        for condition, known_input, runtime, memory, output, status, limitation in entries
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    parser.add_argument("--artifact-root", default=os.environ.get("JBGS_ARTIFACT_ROOT", "/artifacts/JointBuildGS"))
    args = parser.parse_args()
    config = json.loads(Path(args.config).read_text(encoding="utf-8"))
    artifact_root = Path(args.artifact_root).resolve()
    verified = verify_files(artifact_root, config)
    ledger, image_inventory, image_summary = image_camera_evidence(artifact_root, config)
    point_metadata = point_cloud_metadata(artifact_root, verified)
    lod1_search = bounded_lod1_search(artifact_root, config)
    if lod1_search["status"] != "MISSING":
        raise RuntimeError("LoD1 candidate found; manual lineage review required before generation")

    write_csv(LEDGER_PATH, list(ledger[0]), ledger)
    write_csv(IMAGE_INVENTORY_PATH, list(image_inventory[0]), image_inventory)

    aoi = config["candidate_aoi"]
    xmin, ymin, xmax, ymax = aoi["bbox"]
    aoi_payload = {
        "type": "FeatureCollection",
        "name": "gate_s0_candidate_aoi_v1",
        "crs": {"type": "name", "properties": {"name": aoi["crs"]}},
        "features": [
            {
                "type": "Feature",
                "properties": {
                    "status": aoi["status"],
                    "selection_basis": aoi["selection_basis"],
                    "area_m2": aoi["area_m2"],
                },
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[[xmin, ymin], [xmax, ymin], [xmax, ymax], [xmin, ymax], [xmin, ymin]]],
                },
            }
        ],
    }
    write_json(AOI_PATH, aoi_payload)

    receipt_records = [
        {
            "uri": item["uri"],
            "bytes": item["bytes"],
            "sha256": item["sha256"],
            "verification_method": item["verification_method"],
            "verified_by": item["verified_by"],
            "verified_at": item["verified_at"],
        }
        for item in verified
    ]
    write_json(
        ARTIFACT_RECORDS_PATH,
        {
            "schema": "jointbuildgs.gate_s0_live_artifact_records.v1",
            "handoff_id": config["handoff_id"],
            "artifact_root": config["artifact_root_uri"],
            "verification_level": "artifact_verified",
            "docker_image_digest": config["docker_image_digest"],
            "records": receipt_records,
        },
    )
    manifest = {
        "schema": "jointbuildgs.gate_s0_input_manifest.v1",
        "handoff_id": config["handoff_id"],
        "input_commit": config["input_commit"],
        "observed_at": config["observed_at"],
        "scientific_verdict": None,
        "verification": {
            "level": "artifact_verified",
            "artifact_root": config["artifact_root_uri"],
            "docker_image_digest": config["docker_image_digest"],
            "exact_file_count": len(verified),
            "exact_total_bytes": sum(item["bytes"] for item in verified),
            "method": "full SHA-256 rehash of exact target files; no store-wide hash",
        },
        "files": verified,
        "image_camera_ledger": {
            **image_summary,
            "path": str(LEDGER_PATH),
            "image_member_inventory_path": str(IMAGE_INVENTORY_PATH),
            "image_member_inventory_sha256": sha256_file(IMAGE_INVENTORY_PATH),
            "c2_same_base_status": config["image_camera_contract"]["c2_same_base_status"],
            "c2_limitation": config["image_camera_contract"]["c2_limitation"],
        },
        "point_cloud_bounded_metadata": point_metadata,
        "candidate_aoi": {
            **config["candidate_aoi"],
            "geojson_path": str(AOI_PATH),
            "geojson_sha256": sha256_file(AOI_PATH),
        },
        "c1_source_proposal": config["c1_source_proposal"],
        "c4_prior_interface_proposal": config["c4_prior_interface_proposal"],
        "lod1_search": {
            **config["lod1_search"],
            "status": lod1_search["status"],
            "matches": lod1_search["lod1_matches"],
            "search_evidence_path": str(LOD1_SEARCH_PATH),
            "search_evidence_sha256": sha256_file(LOD1_SEARCH_PATH),
            "inventory_entry_count": lod1_search["inventory_entry_count"],
            "inventory_sha256": lod1_search["inventory_sha256"],
            "candidate_matches": lod1_search["candidate_matches"],
        },
        "reference_guard": "LoD2 records are score-only; no RoofSurface, Z, roof type, semantic evaluation label or final model enters an honest arm.",
    }
    write_json(INPUT_MANIFEST_PATH, manifest)
    readiness = build_readiness_rows()
    write_csv(READINESS_PATH, list(readiness[0]), readiness)
    funnel = build_funnel_rows(config)
    write_csv(FUNNEL_PATH, list(funnel[0]), funnel)
    costs = build_cost_rows(verified)
    write_csv(COST_PATH, list(costs[0]), costs)
    split = {
        "schema": "jointbuildgs.gate_s0_split_proposal.v1",
        "status": config["split_proposal"]["status"],
        "scientific_verdict": None,
        "candidate_aoi": {
            "path": str(AOI_PATH),
            "sha256": sha256_file(AOI_PATH),
            "status": config["candidate_aoi"]["status"],
        },
        "preferred_mode": config["split_proposal"]["preferred_mode"],
        "seed": config["split_proposal"]["seed"],
        "algorithm": "After U_target/E_paired freeze, sort immutable spatial group IDs by SHA256(seed|group_id), then allocate whole groups to development, validation and held-out according to a separately approved ratio while preserving strata balance.",
        "grouping": config["split_proposal"]["grouping"],
        "strata": config["split_proposal"]["strata"],
        "forbidden_strata": config["split_proposal"]["forbidden_strata"],
        "fallback": config["split_proposal"]["fallback"],
        "U_target_ids": [],
        "E_paired_ids": [],
        "development_ids": [],
        "validation_ids": [],
        "held_out_ids": [],
        "held_out_accessed": False,
        "freeze_blockers": [
            "U_target stable-ID ledger is UNKNOWN",
            "E_paired is UNKNOWN",
            "C5 independent LoD1 is MISSING",
            "per-condition runtime/memory/output/retention ceiling is UNKNOWN",
        ],
        "phase_contract": {
            "P2_P3_pool": "same development plus validation building pool",
            "P4": "first access to all frozen held-out buildings for C1-C5",
        },
    }
    write_json(SPLIT_PATH, split)
    print(
        json.dumps(
            {
                "status": "PASS",
                "verified_files": len(verified),
                "verified_bytes": sum(item["bytes"] for item in verified),
                "ledger_rows": len(ledger),
                "ledger_sha256": sha256_file(LEDGER_PATH),
                "excluded": sum(item["status"] == "EXCLUDED" for item in ledger),
                "lod1": lod1_search["status"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
