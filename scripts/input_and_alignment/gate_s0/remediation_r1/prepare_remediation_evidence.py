#!/usr/bin/env python3
"""Generate bounded Gate S0 remediation evidence without running experiments."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import shutil
import subprocess
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path
from typing import Any


DEFAULT_CONFIG = Path(
    "configs/input_and_alignment/gate_s0/remediation_r1/remediation_evidence_v1.json"
)
DOC_ROOT = Path("docs/research/preregistration/gate_s0/remediation_r1")


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


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def attr_local(element: ET.Element, name: str) -> str | None:
    return next(
        (value for key, value in element.attrib.items() if local_name(key) == name),
        None,
    )


def verify_exact_file(root: Path, record: dict[str, Any]) -> Path:
    path = root / record["relative_path"]
    if not path.is_file() or path.is_symlink():
        raise RuntimeError(f"missing or unsafe exact file: {path}")
    if path.stat().st_size != record["bytes"]:
        raise RuntimeError(f"byte mismatch: {path}")
    if sha256_file(path) != record["sha256"]:
        raise RuntimeError(f"SHA-256 mismatch: {path}")
    return path


def sparse_initialization(root: Path, config: dict[str, Any]) -> dict[str, Any]:
    opf = config["opf"]
    archive_path = verify_exact_file(root, opf)
    with zipfile.ZipFile(archive_path) as archive:
        project = json.loads(archive.read(opf["project_member"]))
        scene = json.loads(archive.read(opf["scene_member"]))
        cameras = json.loads(archive.read(opf["camera_member"]))
        gltf = json.loads(archive.read(opf["sparse_descriptor_member"]))

        calibration = next(item for item in project["items"] if item["type"] == "calibration")
        resource_members = []
        for resource in calibration["resources"]:
            uri = resource["uri"].removeprefix("./")
            member = f"opf/{uri}"
            if member == opf["sparse_descriptor_member"] or (
                member.startswith("opf/sparse/") and member.endswith(".glbin")
            ):
                resource_members.append(member)
        resource_members = sorted(resource_members)
        expected_members = sorted(
            [opf["sparse_descriptor_member"]]
            + [f"opf/sparse/{item['uri']}" for item in gltf["buffers"]]
        )
        if resource_members != expected_members:
            raise RuntimeError("project OPF sparse resources differ from glTF buffers")

        member_records = []
        for member in sorted(
            resource_members
            + [opf["project_member"], opf["scene_member"], opf["camera_member"]]
        ):
            digest = hashlib.sha256()
            measured = 0
            with archive.open(member) as stream:
                for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
                    measured += len(block)
                    digest.update(block)
            member_records.append(
                {
                    "archive_member": member,
                    "decompressed_bytes": measured,
                    "decompressed_sha256": digest.hexdigest(),
                    "hash_scope": "decompressed archive-member bytes",
                }
            )

    primitive = gltf["meshes"][0]["primitives"][0]
    position = gltf["accessors"][primitive["attributes"]["POSITION"]]
    camera_uids = primitive["extensions"]["OPF_mesh_primitive_matches"]["cameraUids"]
    calibrated_ids = [int(item["id"]) for item in cameras["cameras"]]
    if len(camera_uids) != 937 or len(set(camera_uids)) != 937:
        raise RuntimeError("unexpected sparse camera UID ledger")
    if len(calibrated_ids) != 937 or set(camera_uids) != set(calibrated_ids):
        raise RuntimeError("sparse camera UIDs do not match calibrated cameras")
    if position["count"] != 4_131_648:
        raise RuntimeError("unexpected sparse point count")

    payload = {
        "schema": "jointbuildgs.gate_s0_sfm_sparse_initialization.v1",
        "handoff_id": config["handoff_id"],
        "task_id": config["task_id"],
        "observed_at": config["observed_at"],
        "status": "READY",
        "integration_replay_status": "PARTIAL",
        "scientific_verdict": None,
        "archive": {
            "uri": f"artifact://JointBuildGS/{opf['relative_path']}",
            "bytes": opf["bytes"],
            "sha256": opf["sha256"],
            "verification": "accepted receipt plus live SHA-256 rehash",
        },
        "project": {
            "name": project["name"],
            "version": project["version"],
            "calibration_resource_binding": True,
        },
        "sparse": {
            "descriptor_member": opf["sparse_descriptor_member"],
            "producer": gltf["asset"]["generator"],
            "gltf_version": gltf["asset"]["version"],
            "opf_asset_version": gltf["asset"]["extensions"]["OPF_asset_version"]["version"],
            "point_count": position["count"],
            "local_bounds_min": position["min"],
            "local_bounds_max": position["max"],
            "node_matrix": gltf["nodes"][0]["matrix"],
            "camera_uid_count": len(camera_uids),
            "camera_uid_unique_count": len(set(camera_uids)),
            "camera_uids_equal_calibrated_camera_ids": True,
        },
        "coordinate_frame": {
            "source_crs": "EPSG:32632 / WGS 84 UTM zone 32N",
            "axis_unit": "E,N; metre",
            "base_to_canonical": scene["base_to_canonical"],
            "vertical_datum": "UNKNOWN",
            "scene_definition_member": opf["scene_member"],
        },
        "member_records": member_records,
        "allowed_role": opf["role"],
        "forbidden_roles": [
            "dense MVS initialization or supervision for C3-C5",
            "evaluation reference",
            "held-out selection",
        ],
        "remaining_integration_gap": (
            "pyopf/opf2colmap replay is not callable in the current main image; no converted "
            "canonical derivative was created by this task"
        ),
        "source_record": config["official_sources"]["tum2twin_opf_tutorial"],
    }
    write_json(DOC_ROOT / "sfm_sparse_initialization_v1.json", payload)
    return payload


def lod1_discovery(root: Path, config: dict[str, Any]) -> dict[str, Any]:
    search = config["lod1_search"]
    relative_scope = Path(search["relative_scope"])
    search_root = root / relative_scope
    if not search_root.is_dir() or search_root.is_symlink():
        raise RuntimeError(f"missing or unsafe LoD1 search root: {search_root}")
    inventory: list[tuple[str, int]] = []
    local_matches: list[dict[str, Any]] = []
    for path in sorted(search_root.rglob("*")):
        if path.is_symlink() or not path.is_file():
            continue
        relative_inside = path.relative_to(search_root)
        if len(relative_inside.parts) > search["max_depth"]:
            continue
        relative = (relative_scope / relative_inside).as_posix()
        size = path.stat().st_size
        inventory.append((relative, size))
        if "lod1" in path.name.lower():
            local_matches.append({"relative_path": relative, "bytes": size})
    inventory_bytes = "".join(f"{path}|{size}\n" for path, size in inventory).encode()

    manifest_tree = Path("artifacts/manifests")
    git_matches = sorted(
        path.as_posix()
        for path in manifest_tree.rglob("*")
        if path.is_file() and not path.is_symlink() and "lod1" in path.name.lower()
    )
    payload = {
        "schema": "jointbuildgs.gate_s0_lod1_discovery.v1",
        "handoff_id": config["handoff_id"],
        "task_id": config["task_id"],
        "observed_at": config["observed_at"],
        "status": "MISSING",
        "scientific_verdict": None,
        "admissibility_definition": (
            "C5 requires bytes for a LoD1 prior independent of the scored LoD2 reference"
        ),
        "local_artifact_search": {
            "root": config["artifact_root_uri"],
            "relative_scope": search["relative_scope"],
            "max_depth": search["max_depth"],
            "algorithm": "sorted regular non-symlink file inventory; filename token lod1",
            "inventory_entry_count": len(inventory),
            "inventory_bytes": len(inventory_bytes),
            "inventory_sha256": sha256_bytes(inventory_bytes),
            "matches": local_matches,
        },
        "git_manifest_search": {
            "query": search["git_manifest_query"],
            "matches": git_matches,
            "matching_path_count": len(git_matches),
            "admissible_live_byte_records": [],
        },
        "official_scope": {
            "tum2twin_building_catalog": config["official_sources"]["tum2twin_buildings"],
            "catalog_listed_levels": ["LoD3", "textured LoD2", "LoD2"],
            "provider_candidates": search["official_candidates"],
        },
        "bounded_conclusion": (
            "No admissible independent LoD1 bytes were found in the fixed local/Git scope. "
            "The official Bavarian LoD1 candidate is derived from the updated LoD2 stock and "
            "therefore fails C5 independence; this is not a provider-wide absence claim."
        ),
        "prohibited_substitute": (
            "Do not simplify, extrude or otherwise derive LoD1 from scored LoD2 geometry, Z, "
            "RoofSurface, roof type, semantics or final models."
        ),
    }
    write_json(DOC_ROOT / "lod1_discovery_v1.json", payload)
    return payload


def reference_candidates(
    root: Path, config: dict[str, Any]
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    xmin, ymin, xmax, ymax = config["candidate_aoi"]["bbox"]
    rows: list[dict[str, Any]] = []
    source_counts: dict[str, int] = {}
    all_ids: set[str] = set()
    all_external_ids: set[str] = set()
    reference_building_count = 0
    c1_bbox = config["numeric_header_bboxes"]["C1_NADIR_EPSG32632_UNREGISTERED"]
    c2_bbox = config["numeric_header_bboxes"]["C2_MVS_EPSG32632_UNREGISTERED"]
    c4_bbox = config["numeric_header_bboxes"]["C4_ALS_EPSG25832_PROVIDER_TILE_UNION"]

    def fully_inside(bounds: tuple[float, float, float, float], outer: list[float]) -> bool:
        return (
            bounds[0] >= outer[0]
            and bounds[1] >= outer[1]
            and bounds[2] <= outer[2]
            and bounds[3] <= outer[3]
        )

    for record in config["reference_tiles"]:
        path = verify_exact_file(root, record)
        tile_count = 0
        for _event, element in ET.iterparse(path, events=("end",)):
            if local_name(element.tag) != "Building":
                continue
            reference_building_count += 1
            building_id = attr_local(element, "id")
            if not building_id or building_id in all_ids:
                raise RuntimeError("missing or duplicate reference building ID")
            all_ids.add(building_id)
            external_id = None
            for external_object in element.iter():
                if local_name(external_object.tag) != "externalObject":
                    continue
                external_id = next(
                    (
                        (child.text or "").strip()
                        for child in external_object.iter()
                        if local_name(child.tag) == "name" and (child.text or "").strip()
                    ),
                    None,
                )
                if external_id:
                    break
            if not external_id or external_id in all_external_ids:
                raise RuntimeError("missing or duplicate provider external object ID")
            all_external_ids.add(external_id)
            coordinates: list[tuple[float, float]] = []
            for child in element.iter():
                if local_name(child.tag) != "GroundSurface":
                    continue
                for position_list in child.iter():
                    if local_name(position_list.tag) != "posList" or not position_list.text:
                        continue
                    values = [float(value) for value in position_list.text.split()]
                    if len(values) % 3:
                        raise RuntimeError(f"malformed GroundSurface posList: {building_id}")
                    coordinates.extend(zip(values[0::3], values[1::3]))
            if not coordinates:
                raise RuntimeError(f"missing GroundSurface: {building_id}")
            bxmin = min(value[0] for value in coordinates)
            bymin = min(value[1] for value in coordinates)
            bxmax = max(value[0] for value in coordinates)
            bymax = max(value[1] for value in coordinates)
            bounds = (bxmin, bymin, bxmax, bymax)
            intersects = bxmin <= xmax and bxmax >= xmin and bymin <= ymax and bymax >= ymin
            if intersects:
                tile_count += 1
                rows.append(
                    {
                        "stable_id": building_id,
                        "provider_external_id": external_id,
                        "reference_tile": record["asset_id"],
                        "groundsurface_bbox_epsg25832": (
                            f"{bxmin:.3f},{bymin:.3f},{bxmax:.3f},{bymax:.3f}"
                        ),
                        "candidate_aoi_intersects": "true",
                        "image_camera_ledger": "937_INCLUDED_25_EXCLUDED_AGGREGATE_ONLY",
                        "current_image_building_coverage": "UNKNOWN",
                        "c1_numeric_bbox_full_unregistered": str(fully_inside(bounds, c1_bbox)).lower(),
                        "c1_registered_coverage": "UNKNOWN",
                        "c1_eligible": "UNKNOWN",
                        "c2_numeric_bbox_full_unregistered": str(fully_inside(bounds, c2_bbox)).lower(),
                        "c2_registered_coverage": "UNKNOWN",
                        "c2_eligible": "UNKNOWN",
                        "c3_registered_coverage": "UNKNOWN",
                        "c3_eligible": "UNKNOWN",
                        "c4_provider_tile_full_unregistered": str(fully_inside(bounds, c4_bbox)).lower(),
                        "c4_registered_coverage": "UNKNOWN",
                        "c4_eligible": "UNKNOWN",
                        "c5_candidate_availability": "MISSING",
                        "c5_eligible": "false",
                        "u_target_status": "UNKNOWN",
                        "e_paired_status": "UNKNOWN",
                        "exclusion_reason": (
                            "IMAGE_BUILDING_COVERAGE_JOIN_MISSING;"
                            "C1_REGISTERED_FULL_COVERAGE_UNKNOWN;C1_CLASS_2_6_DERIVATIVE_MISSING;"
                            "C1_VERTICAL_DATUM_UNKNOWN;C2_REGISTERED_FULL_COVERAGE_UNKNOWN;"
                            "C2_EXACT_937_BASE_MISMATCH;C2_CLASS_2_6_DERIVATIVE_MISSING;"
                            "C3_SPARSE_CONVERSION_REPLAY_PARTIAL;C4_REGISTRATION_NOT_VERIFIED;"
                            "C4_PRIOR_INTERFACE_NOT_FROZEN;C5_INDEPENDENT_LOD1_MISSING;"
                            "GRAVITY_TERRAIN_MVS_ESTIMATE_MISSING;R_DERIVED_COMMON_REPLAY_MISSING;"
                            "STAGE3_TOOLCHAIN_NOT_REPLAYABLE"
                        ),
                        "held_out_accessed": "false",
                    }
                )
            element.clear()
        source_counts[record["asset_id"]] = tile_count
    rows.sort(key=lambda item: item["stable_id"])
    if len(rows) != 199 or len({row["stable_id"] for row in rows}) != 199:
        raise RuntimeError("candidate diagnostic must contain 199 unique stable IDs")
    id_bytes = "".join(f"{row['stable_id']}\n" for row in rows).encode()
    id_pair_bytes = "".join(
        f"{row['stable_id']}|{row['provider_external_id']}\n" for row in rows
    ).encode()
    summary = {
        "reference_building_count": reference_building_count,
        "reference_unique_stable_id_count": len(all_ids),
        "reference_unique_external_id_count": len(all_external_ids),
        "candidate_count": len(rows),
        "source_counts": source_counts,
        "stable_id_set_sha256": sha256_bytes(id_bytes),
        "stable_id_external_id_pair_sha256": sha256_bytes(id_pair_bytes),
        "c1_nadir_numeric_bbox_full_unregistered_count": sum(
            row["c1_numeric_bbox_full_unregistered"] == "true" for row in rows
        ),
        "c2_mvs_numeric_bbox_full_unregistered_count": sum(
            row["c2_numeric_bbox_full_unregistered"] == "true" for row in rows
        ),
        "c4_provider_tile_full_unregistered_count": sum(
            row["c4_provider_tile_full_unregistered"] == "true" for row in rows
        ),
        "selection_geometry": "score-only GroundSurface XY bounding-box intersection",
        "selection_attributes_excluded": [
            "RoofSurface",
            "roof type",
            "semantic evaluation labels",
            "method outcomes",
        ],
    }
    write_csv(
        DOC_ROOT / "eligibility_funnel_v2.csv",
        list(rows[0]),
        rows,
    )
    return rows, summary


def coordinate_rows() -> list[dict[str, str]]:
    checks = "non-GT cross-modal control points; horizontal/vertical residual summaries; coverage after transform"
    return [
        {
            "condition": "C1_L_upper",
            "asset": "current UAS LiDAR nadir (manual is supplemental only)",
            "source_crs_axis_unit": "EPSG:32632; E,N; metre from LAS VLR",
            "vertical_datum": "UNKNOWN",
            "target": "EPSG:25832 + DHHN2016",
            "transformation_plan": "PROJ horizontal 32632->25832; vertical transform blocked until source datum is bound",
            "registration_checks": checks,
            "status": "PARTIAL",
        },
        {
            "condition": "C2_MVS",
            "asset": "Pix4Dmatic dense MVS sensor-processing bundle baseline",
            "source_crs_axis_unit": "EPSG:32632; E,N; metre",
            "vertical_datum": "EGM96 / EPSG:5773 from prior datum audit",
            "target": "EPSG:25832 + DHHN2016",
            "transformation_plan": "PROJ horizontal plus validated EGM96-to-DHHN2016 vertical grid/pipeline",
            "registration_checks": checks,
            "status": "PARTIAL",
        },
        {
            "condition": "C3_GS_image",
            "asset": "Images.zip + OPF calibrated cameras + OPF sparse SfM",
            "source_crs_axis_unit": "OPF EPSG:32632; E,N; metre; local sparse frame with recorded shift/matrix",
            "vertical_datum": "UNKNOWN",
            "target": "EPSG:25832 + DHHN2016",
            "transformation_plan": "replay OPF frame and sparse node transform, then horizontal/vertical pipeline after datum binding",
            "registration_checks": checks,
            "status": "PARTIAL",
        },
        {
            "condition": "C4_GS_lidar_prior",
            "asset": "2022 existing ALS four-tile set plus C3 common image/SfM base",
            "source_crs_axis_unit": "provider EPSG:25832; E,N; metre; LAS CRS VLR absent",
            "vertical_datum": "provider-declared DHHN2016",
            "target": "EPSG:25832 + DHHN2016",
            "transformation_plan": "bind provider declaration to exact tiles; no horizontal transform expected; verify residual",
            "registration_checks": checks,
            "status": "PARTIAL",
        },
        {
            "condition": "C5_GS_lod1_prior",
            "asset": "independent LoD1",
            "source_crs_axis_unit": "MISSING",
            "vertical_datum": "MISSING",
            "target": "EPSG:25832 + DHHN2016",
            "transformation_plan": "cannot define until an admissible independent asset is acquired and hash-bound",
            "registration_checks": checks,
            "status": "MISSING",
        },
        {
            "condition": "EVALUATION_REFERENCE",
            "asset": "Bavarian LoD2 690_5334 + 690_5336 score-only tiles",
            "source_crs_axis_unit": "urn:adv:crs:ETRS89_UTM32*DE_DHHN2016_NH; 3D; metre",
            "vertical_datum": "DHHN2016 NH",
            "target": "unchanged score-only reference frame",
            "transformation_plan": "no evaluation geometry enters inputs; stable ID and GroundSurface XY are diagnostic only",
            "registration_checks": "reference version/ID freeze and independent residual controls; no outcome-based selection",
            "status": "PARTIAL",
        },
    ]


def reference_lineage(config: dict[str, Any], candidate_summary: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema": "jointbuildgs.gate_s0_evaluation_reference_lineage.v1",
        "handoff_id": config["handoff_id"],
        "task_id": config["task_id"],
        "observed_at": config["observed_at"],
        "scientific_verdict": None,
        "geometry_reference_candidate": {
            "identity": "current 2024-12-17 UAS LiDAR nadir source",
            "status": "PARTIAL",
            "role": "positional geometry reference candidate only",
            "uncertainty": "vertical datum, registration residual and independent uncertainty are not frozen",
            "condition_overlap_class": [
                {"condition": "C1_L_upper", "class": "SELF_REFERENCE"},
                {"condition": "C2_MVS", "class": "PARTIALLY_SHARED_SAME_CAMPAIGN_PLATFORM"},
                {"condition": "C3_GS_image", "class": "PARTIALLY_SHARED_SAME_CAMPAIGN_PLATFORM"},
                {"condition": "C4_GS_lidar_prior", "class": "PARTIALLY_SHARED_CURRENT_IMAGES"},
                {"condition": "C5_GS_lod1_prior", "class": "UNKNOWN_INPUT_MISSING"}
            ],
        },
        "structure_reference": {
            "identity": "Bavarian LoD2 CityGML tiles 690_5334 and 690_5336",
            "exact_records": config["reference_tiles"],
            "provider": "Bavarian State Mapping Agency via TUM2TWIN",
            "format": "CityGML 1.0 LoD2",
            "crs_datum": "ETRS89/UTM32 + DHHN2016 NH",
            "production_lineage": (
                "Provider-described ALKIS building footprints with roofs derived from then-current ALS, "
                "ALKIS 3D survey or image DSM; exact local tile/version/epoch and per-building source/date "
                "are unbound and were not promoted to inputs"
            ),
            "uncertainty": (
                "official current page states horizontal accuracy follows ALKIS and typical height accuracy about 1 m; "
                "complex roofs may be worse"
            ),
            "candidate_diagnostic": candidate_summary,
            "allowed_selection_fields": ["gml:id", "GroundSurface XY coverage"],
            "forbidden_input_fields": [
                "LoD2 Z",
                "RoofSurface",
                "roof type",
                "semantic class",
                "final roof model",
            ],
        },
        "structure_reference_overlap_class": [
            {
                "condition": "C1_L_upper",
                "class": "UNKNOWN_OR_PARTIALLY_SHARED",
                "basis": "current UAS LiDAR is a separate 2024 asset, but reference production may include unbound ALS/image DSM lineage",
            },
            {
                "condition": "C2_MVS",
                "class": "UNKNOWN",
                "basis": "current MVS is a separate Pix4D bundle; no exact per-building LoD2 production source/date overlap is bound",
            },
            {
                "condition": "C3_GS_image",
                "class": "UNKNOWN",
                "basis": "current images are separate and no exact per-building LoD2 production source/date overlap is bound",
            },
            {
                "condition": "C4_GS_lidar_prior",
                "class": "UNKNOWN_OR_PARTIALLY_SHARED",
                "basis": "existing ALS and LoD2 are Bavarian products and LoD2 may use ALS/ALKIS sources, but exact local tile/version/epoch contribution is unbound",
            },
            {
                "condition": "C5_GS_lod1_prior",
                "class": "PROHIBITED_DERIVATIVE_CANDIDATE",
                "basis": "official Bavarian LoD1 is generated from updated LoD2 stock; no independent C5 asset exists",
            },
        ],
        "source_records": [
            config["official_sources"]["tum2twin_buildings"],
            config["official_sources"]["ldbv_lod2"],
            config["official_sources"]["ldbv_lod1"],
        ],
    }


def provenance_rows(config: dict[str, Any]) -> list[dict[str, str]]:
    c2 = config["c2_lineage"]
    items = [
        ("C1_L_upper", "asset_identity", "PARTIAL", "nadir is version-stable and proposed primary; local manual is legacy Zenodo v1.0 bytes and differs from latest v1.2", "retain NADIR_ONLY proposal and bind exact source versions"),
        ("C1_L_upper", "sensor_role", "READY", "DJI Matrice 350 RTK + Zenmuse L2 current UAS LiDAR; not ALS", "retain C1-only role"),
        ("C1_L_upper", "class_2_6_derivative", "MISSING", "source sample is class 0 and no derivative receipt exists", "approved non-GT classifier and immutable derivative"),
        ("C1_L_upper", "datum_registration_coverage", "UNKNOWN", "horizontal EPSG:32632 is bound; vertical datum and building coverage are not", "datum binding, residuals and per-ID coverage"),
        ("C2_MVS", "asset_identity", "READY", "exact Pix4Dmatic 1.58.1 dense MVS bytes are hash-bound", "retain C2-only dense role"),
        ("C2_MVS", "same_937_image_base", "MISSING", f"published MVS uses {c2['published_mvs_input_image_count']} acquired images while public archive has {c2['privacy_filtered_public_image_count']} and OPF calibrates {c2['calibrated_public_image_count']}", "do not label C2-vs-C3 as method-only"),
        ("C2_MVS", "interpretation", "READY", "honest label frozen as sensor-processing-bundle baseline", "carry limitation into Gate and results"),
        ("C2_MVS", "datum_registration_class", "PARTIAL", "EPSG:32632 and EGM96 are known; transform/residual and class 2/6 derivative absent", "replayable transform and classifier derivative"),
        ("C3_GS_image", "image_camera_base", "READY", "962 images, 937 calibrated poses and 25 deterministic exclusions remain frozen", "building-level view support join"),
        ("C3_GS_image", "sparse_initialization", "READY", "OPF sparse artifact has 4,131,648 points and exact 937-camera UID equality", "callable conversion/integration replay"),
        ("C3_GS_image", "dense_mvs_separation", "READY", "dense MVS is prohibited from initialization/supervision", "enforce later config guard"),
        ("C4_GS_lidar_prior", "asset_identity", "READY", "four exact 2022 regional ALS tiles are distinct from current UAS LiDAR", "bind derivative receipt"),
        ("C4_GS_lidar_prior", "temporal_sensor_independence_from_c1", "READY", "regional ALS 2022 versus UAS LiDAR 2024 with distinct platform/provider roles", "retain separate namespaces"),
        ("C4_GS_lidar_prior", "reference_independence", "PARTIAL", "LoD2 production can use ALS and shares ALKIS footprint lineage", "per-building production/source overlap classification"),
        ("C4_GS_lidar_prior", "coverage_registration_confidence", "UNKNOWN", "tile extents exist but building overlap/residual/confidence semantics do not", "per-ID overlap, residual and metadata semantics"),
        ("C5_GS_lod1_prior", "independent_lod1", "MISSING", "no admissible independent bytes; official LoD1 derives from updated LoD2 stock", "acquire/license/hash-bind independent candidate"),
        ("C5_GS_lod1_prior", "leakage_guard", "READY", "LoD2-derived LoD1 and scored attributes remain prohibited", "retain automated manifest guard"),
        ("ALL", "U_target", "UNKNOWN", "199 stable IDs are a reference-intersection diagnostic only", "building-level current-image and condition coverage joins"),
        ("ALL", "E_paired", "UNKNOWN", "C5 is MISSING and C1/C2/C4 eligibility joins are unresolved", "complete all-condition attemptability ledger"),
        ("ALL", "cost_bounds", "UNKNOWN", "no comparable bounded non-held-out calibration receipt", "separately approved non-held-out calibration after data readiness"),
    ]
    return [
        {
            "condition": condition,
            "field": field,
            "status": status,
            "evidence": evidence,
            "required_next_evidence": next_evidence,
        }
        for condition, field, status, evidence, next_evidence in items
    ]


def command_record(command: str) -> dict[str, Any]:
    path = shutil.which(command)
    if path is None:
        return {"command": command, "status": "MISSING", "path": None, "version": None}
    result = subprocess.run(
        [command, "--version"], check=False, capture_output=True, text=True
    )
    output = (result.stdout or result.stderr).splitlines()
    return {
        "command": command,
        "status": "FOUND",
        "path": path,
        "version": output[0] if output else "UNKNOWN",
        "version_exit_code": result.returncode,
    }


def toolchain_inventory(config: dict[str, Any]) -> dict[str, Any]:
    commands = [command_record(name) for name in ("roofer", "roofer-cli", "cjio", "cjval", "val3dity", "ogr2ogr", "pdal")]
    components = [
        {
            "component": "Roofer evidence-to-CityGML",
            "classification": "MISSING_IN_CURRENT_IMAGE",
            "version": "P0 replay evidence pins Roofer 1.0.0",
            "replay_path": config["toolchain"]["p0_versions_evidence"],
            "missing_dependency": "pinned Roofer image is not locally available; no pull/build authorized",
        },
        {
            "component": "CityJSON writer",
            "classification": "PARTIAL_PRODUCTION_CODE",
            "version": "Python repository code; cjio 0.10.1 present",
            "replay_path": config["toolchain"]["cityjson_writer"],
            "missing_dependency": "not integrated as a common C1-C5 writer; filename does not imply CityGML serialization",
        },
        {
            "component": "CityGML writer/converter",
            "classification": "MISSING_IN_CURRENT_IMAGE",
            "version": "P0 replay evidence pins citygml-tools 2.5.0",
            "replay_path": config["toolchain"]["p0_versions_evidence"],
            "missing_dependency": "citygml-tools/ogr2ogr absent and no canonical common serializer exists",
        },
        {
            "component": "cjval/val3dity validation",
            "classification": "MISSING_IN_CURRENT_IMAGE",
            "version": "P0 replay evidence pins val3dity 2.6.0; cjio 0.10.1 is present",
            "replay_path": config["toolchain"]["p0_versions_evidence"],
            "missing_dependency": "cjval and val3dity executables absent",
        },
        {
            "component": "gravity from terrain MVS normals",
            "classification": "MISSING_CANONICAL_IMPLEMENTATION",
            "version": None,
            "replay_path": config["toolchain"]["gravity_candidate"],
            "missing_dependency": "candidate estimator is MatrixCity GT-normal based; TUM config is hardcoded Z-up and is inadmissible",
        },
        {
            "component": "non-GT R_derived common protocol",
            "classification": "MISSING_CANONICAL_IMPLEMENTATION",
            "version": None,
            "replay_path": None,
            "missing_dependency": "no production implementation/config/hash found outside historical/test material",
        },
        {
            "component": "G0-G4 common reporting",
            "classification": "MISSING_CANONICAL_IMPLEMENTATION",
            "version": None,
            "replay_path": None,
            "missing_dependency": "no common C1-C5 field writer or replay path found",
        },
    ]
    payload = {
        "schema": "jointbuildgs.gate_s0_stage3_toolchain_inventory.v1",
        "handoff_id": config["handoff_id"],
        "task_id": config["task_id"],
        "observed_at": config["observed_at"],
        "scientific_verdict": None,
        "current_image": config["toolchain"]["main_image"],
        "current_image_digest": config["toolchain"]["main_image_digest"],
        "command_inventory": commands,
        "components": components,
        "p0_replay_images": [
            {
                "image": config["toolchain"]["p0_roofer_image"],
                "local_availability": "ABSENT",
            },
            {
                "image": config["toolchain"]["p0_tools_image"],
                "local_availability": "ABSENT",
            },
        ],
        "overall_status": "BLOCKED",
        "thresholds_or_adapter_selected": False,
    }
    write_json(DOC_ROOT / "stage3_toolchain_inventory_v1.json", payload)
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument(
        "--artifact-root",
        type=Path,
        default=Path(os.environ.get("JBGS_ARTIFACT_ROOT", "/artifacts/JointBuildGS")),
    )
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding="utf-8"))
    root = args.artifact_root.resolve()
    sparse_initialization(root, config)
    lod1_discovery(root, config)
    _rows, candidate_summary = reference_candidates(root, config)
    write_csv(
        DOC_ROOT / "coordinate_reference_matrix_v1.csv",
        list(coordinate_rows()[0]),
        coordinate_rows(),
    )
    write_json(
        DOC_ROOT / "evaluation_reference_lineage_v1.json",
        reference_lineage(config, candidate_summary),
    )
    provenance = provenance_rows(config)
    write_csv(
        DOC_ROOT / "condition_provenance_matrix_v1.csv",
        list(provenance[0]),
        provenance,
    )
    toolchain_inventory(config)
    print(
        "Gate S0 remediation evidence generated: sparse=READY, independent_lod1=MISSING, "
        "candidate_ids=199, scientific_verdict=null"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
