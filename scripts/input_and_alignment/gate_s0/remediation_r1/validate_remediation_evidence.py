#!/usr/bin/env python3
"""Validate the bounded Gate S0 remediation package and its exact evidence bindings."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import subprocess
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path
from typing import Any


CONFIG_PATH = Path(
    "configs/input_and_alignment/gate_s0/remediation_r1/remediation_evidence_v1.json"
)
DOC_ROOT = Path("docs/research/preregistration/gate_s0/remediation_r1")
RETURN_PATH = Path("docs/handoffs/returns/P2_C2W_GATE_S0_REMEDIATION_R1_RETURN_v1.md")
OUTPUT_MANIFEST = Path(
    "artifacts/manifests/gate_s0/remediation_r1/remediation_output_manifest_v1.json"
)
REQUIRED_OUTPUTS = [
    DOC_ROOT / "REMEDIATION_EVIDENCE_REPORT_v1.md",
    DOC_ROOT / "lod1_discovery_v1.json",
    DOC_ROOT / "sfm_sparse_initialization_v1.json",
    DOC_ROOT / "coordinate_reference_matrix_v1.csv",
    DOC_ROOT / "evaluation_reference_lineage_v1.json",
    DOC_ROOT / "condition_provenance_matrix_v1.csv",
    DOC_ROOT / "eligibility_funnel_v2.csv",
    DOC_ROOT / "stage3_toolchain_inventory_v1.json",
    DOC_ROOT / "remediation_issue_log_v1.md",
    RETURN_PATH,
]
ALLOWED_PREFIXES = (
    "artifacts/manifests/handoffs/P2-W2C-GATE-S0-REMEDIATION-R1-v1/",
    "artifacts/manifests/gate_s0/remediation_r1/",
    "configs/input_and_alignment/gate_s0/remediation_r1/",
    "docs/research/preregistration/gate_s0/remediation_r1/",
    "scripts/input_and_alignment/gate_s0/remediation_r1/",
    "tests/input_and_alignment/gate_s0/remediation_r1/",
)


def lf_bytes(path: Path) -> bytes:
    return path.read_bytes().replace(b"\r\n", b"\n")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def git(*args: str) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        ["git", "-c", f"safe.directory={Path.cwd().resolve()}", *args],
        check=False,
        capture_output=True,
    )


def git_introducing_commit(path: Path) -> str | None:
    result = git("log", "-1", "--format=%H", "--", path.as_posix())
    value = result.stdout.decode().strip()
    return value if result.returncode == 0 and len(value) == 40 else None


def git_blob(commit: str, path: Path) -> bytes | None:
    result = git("show", f"{commit}:{path.as_posix()}")
    return result.stdout if result.returncode == 0 else None


def build_output_manifest() -> dict[str, Any]:
    missing = [path.as_posix() for path in REQUIRED_OUTPUTS if not path.is_file()]
    if missing:
        raise RuntimeError(f"cannot index missing outputs: {missing}")
    return {
        "schema": "jointbuildgs.gate_s0_remediation_output_manifest.v1",
        "handoff_id": "P2-W2C-GATE-S0-REMEDIATION-R1-v1",
        "task_id": "P2-GATE-S0-REMEDIATION-R1-v1",
        "input_commit": "7a16085c221ccf87d16f712332ac3c97eda193b1",
        "output_commit": "SELF",
        "proposed_status": "BLOCKED_FOR_GATE_S0_REMEDIATION_REVIEW",
        "artifact_verification_level": "artifact_verified",
        "scientific_verdict": None,
        "files": [
            {
                "path": path.as_posix(),
                "bytes": len(lf_bytes(path)),
                "sha256": sha256_bytes(lf_bytes(path)),
            }
            for path in REQUIRED_OUTPUTS
        ],
    }


def write_output_manifest() -> None:
    payload = build_output_manifest()
    OUTPUT_MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_MANIFEST.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def attribute(element: ET.Element, name: str) -> str | None:
    return next(
        (value for key, value in element.attrib.items() if local_name(key) == name), None
    )


def recompute_reference_candidates(
    root: Path, config: dict[str, Any]
) -> tuple[list[dict[str, str]], dict[str, int]]:
    xmin, ymin, xmax, ymax = config["candidate_aoi"]["bbox"]
    rows: list[dict[str, str]] = []
    counts: dict[str, int] = {}
    all_ids: set[str] = set()
    all_external: set[str] = set()
    total = 0
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
        path = root / record["relative_path"]
        if not path.is_file() or path.is_symlink():
            raise RuntimeError(f"reference GML missing or unsafe: {path}")
        if path.stat().st_size != record["bytes"]:
            raise RuntimeError(f"reference GML byte mismatch: {path}")
        if sha256_file(path) != record["sha256"]:
            raise RuntimeError(f"reference GML SHA-256 mismatch: {path}")
        count = 0
        for _event, element in ET.iterparse(path, events=("end",)):
            if local_name(element.tag) != "Building":
                continue
            total += 1
            stable_id = attribute(element, "id")
            external_id = None
            for external in element.iter():
                if local_name(external.tag) != "externalObject":
                    continue
                external_id = next(
                    (
                        (child.text or "").strip()
                        for child in external.iter()
                        if local_name(child.tag) == "name" and (child.text or "").strip()
                    ),
                    None,
                )
                if external_id:
                    break
            coordinates: list[tuple[float, float]] = []
            for ground in element.iter():
                if local_name(ground.tag) != "GroundSurface":
                    continue
                for position_list in ground.iter():
                    if local_name(position_list.tag) != "posList" or not position_list.text:
                        continue
                    values = [float(value) for value in position_list.text.split()]
                    if len(values) % 3:
                        raise RuntimeError("malformed GroundSurface position list")
                    coordinates.extend(zip(values[0::3], values[1::3]))
            if not stable_id or stable_id in all_ids or not external_id or external_id in all_external:
                raise RuntimeError("reference ID uniqueness failure")
            if not coordinates:
                raise RuntimeError("reference GroundSurface missing")
            all_ids.add(stable_id)
            all_external.add(external_id)
            bxmin = min(item[0] for item in coordinates)
            bymin = min(item[1] for item in coordinates)
            bxmax = max(item[0] for item in coordinates)
            bymax = max(item[1] for item in coordinates)
            if bxmin <= xmax and bxmax >= xmin and bymin <= ymax and bymax >= ymin:
                count += 1
                bounds = (bxmin, bymin, bxmax, bymax)
                rows.append(
                    {
                        "stable_id": stable_id,
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
        counts[record["asset_id"]] = count
    counts["REFERENCE_TOTAL"] = total
    return sorted(rows, key=lambda row: row["stable_id"]), counts


def validate_funnel_rows(
    actual: list[dict[str, str]], expected: list[dict[str, str]], errors: list[str]
) -> None:
    require(actual == expected, "funnel rows differ from exact live per-ID reconstruction", errors)


def recompute_lod1_inventory(root: Path, search: dict[str, Any]) -> tuple[int, int, str, list[str]]:
    relative_scope = Path(search["relative_scope"])
    search_root = root / relative_scope
    inventory: list[tuple[str, int]] = []
    matches: list[str] = []
    for path in sorted(search_root.rglob("*")):
        if path.is_symlink() or not path.is_file():
            continue
        inside = path.relative_to(search_root)
        if len(inside.parts) > search["max_depth"]:
            continue
        relative = (relative_scope / inside).as_posix()
        inventory.append((relative, path.stat().st_size))
        if "lod1" in path.name.lower():
            matches.append(relative)
    value = "".join(f"{path}|{size}\n" for path, size in inventory).encode()
    return len(inventory), len(value), sha256_bytes(value), matches


def require(condition: bool, message: str, errors: list[str]) -> None:
    if not condition:
        errors.append(message)


def validate(root: Path, *, verify_self: bool) -> list[str]:
    errors: list[str] = []
    for path in [CONFIG_PATH, *REQUIRED_OUTPUTS, OUTPUT_MANIFEST]:
        require(path.is_file() and path.stat().st_size > 0, f"missing/empty: {path}", errors)
    if errors:
        return errors

    config = read_json(CONFIG_PATH)
    manifest = read_json(OUTPUT_MANIFEST)
    require(manifest["scientific_verdict"] is None, "manifest verdict must be null", errors)
    require(manifest["output_commit"] == "SELF", "manifest SELF marker missing", errors)
    require(
        manifest["proposed_status"] == "BLOCKED_FOR_GATE_S0_REMEDIATION_REVIEW",
        "manifest proposed status mismatch",
        errors,
    )
    require(manifest["artifact_verification_level"] == "artifact_verified", "artifact level mismatch", errors)
    indexed = {item["path"]: item for item in manifest["files"]}
    require(set(indexed) == {path.as_posix() for path in REQUIRED_OUTPUTS}, "output index mismatch", errors)
    for path in REQUIRED_OUTPUTS:
        item = indexed.get(path.as_posix(), {})
        require(item.get("bytes") == len(lf_bytes(path)), f"output bytes mismatch: {path}", errors)
        require(item.get("sha256") == sha256_bytes(lf_bytes(path)), f"output SHA mismatch: {path}", errors)

    if verify_self:
        commits: set[str] = set()
        for path in [*REQUIRED_OUTPUTS, OUTPUT_MANIFEST]:
            commit = git_introducing_commit(path)
            require(commit is not None, f"cannot resolve introducing commit: {path}", errors)
            if commit is None:
                continue
            commits.add(commit)
            blob = git_blob(commit, path)
            require(blob == lf_bytes(path), f"worktree differs from introducing blob: {path}", errors)
        require(len(commits) == 1, "SELF package was not introduced by one commit", errors)

        changed = git("diff", "--name-only", f"{config['input_commit']}..HEAD")
        require(changed.returncode == 0, "cannot inspect scope diff", errors)
        for raw in changed.stdout.decode().splitlines():
            allowed = raw == RETURN_PATH.as_posix() or raw.startswith(ALLOWED_PREFIXES)
            require(allowed, f"path outside approved scope: {raw}", errors)

    opf = config["opf"]
    archive_path = root / opf["relative_path"]
    require(archive_path.is_file() and not archive_path.is_symlink(), "OPF archive missing/unsafe", errors)
    if archive_path.is_file():
        require(archive_path.stat().st_size == opf["bytes"], "OPF archive bytes mismatch", errors)
        require(sha256_file(archive_path) == opf["sha256"], "OPF archive SHA mismatch", errors)
    sparse = read_json(DOC_ROOT / "sfm_sparse_initialization_v1.json")
    require(sparse["scientific_verdict"] is None, "sparse verdict must be null", errors)
    require(sparse["status"] == "READY", "sparse source must be READY", errors)
    require(sparse["integration_replay_status"] == "PARTIAL", "integration status mismatch", errors)
    require(sparse["sparse"]["point_count"] == 4_131_648, "sparse point count mismatch", errors)
    require(sparse["sparse"]["camera_uid_count"] == 937, "sparse camera count mismatch", errors)
    require(sparse["sparse"]["camera_uids_equal_calibrated_camera_ids"] is True, "camera binding mismatch", errors)
    require(len(sparse["member_records"]) == 16, "sparse/control member count mismatch", errors)
    sparse_bytes = sum(
        item["decompressed_bytes"]
        for item in sparse["member_records"]
        if item["archive_member"].startswith("opf/sparse/")
    )
    require(sparse_bytes == 469_147_486, "sparse decompressed byte total mismatch", errors)
    if archive_path.is_file():
        with zipfile.ZipFile(archive_path) as archive:
            for item in sparse["member_records"]:
                value = archive.read(item["archive_member"])
                require(len(value) == item["decompressed_bytes"], f"member bytes mismatch: {item['archive_member']}", errors)
                require(sha256_bytes(value) == item["decompressed_sha256"], f"member SHA mismatch: {item['archive_member']}", errors)

    lod1 = read_json(DOC_ROOT / "lod1_discovery_v1.json")
    require(lod1["scientific_verdict"] is None, "LoD1 verdict must be null", errors)
    require(lod1["status"] == "MISSING", "independent LoD1 must remain MISSING", errors)
    require(lod1["local_artifact_search"]["matches"] == [], "unexpected local LoD1 match", errors)
    require(lod1["git_manifest_search"]["admissible_live_byte_records"] == [], "unexpected manifest bytes", errors)
    count, size, digest, matches = recompute_lod1_inventory(root, lod1["local_artifact_search"])
    require(count == 13, "LoD1 inventory count mismatch", errors)
    require(count == lod1["local_artifact_search"]["inventory_entry_count"], "LoD1 live count drift", errors)
    require(size == lod1["local_artifact_search"]["inventory_bytes"], "LoD1 inventory byte drift", errors)
    require(digest == lod1["local_artifact_search"]["inventory_sha256"], "LoD1 inventory hash drift", errors)
    require(matches == [], "LoD1 live search unexpectedly found a match", errors)
    official = lod1["official_scope"]["provider_candidates"][0]
    require(official["independent_from_scored_lod2"] is False, "LoD1 independence overclaim", errors)
    require(official["admissibility"] == "INADMISSIBLE_AS_INDEPENDENT_C5", "LoD1 admissibility mismatch", errors)

    funnel = read_csv(DOC_ROOT / "eligibility_funnel_v2.csv")
    require(len(funnel) == 199, "funnel row count mismatch", errors)
    require(funnel == sorted(funnel, key=lambda row: row["stable_id"]), "funnel not sorted", errors)
    require(len({row["stable_id"] for row in funnel}) == 199, "funnel stable IDs not unique", errors)
    require(len({row["provider_external_id"] for row in funnel}) == 199, "funnel external IDs not unique", errors)
    require(all(row["held_out_accessed"] == "false" for row in funnel), "held-out flag mismatch", errors)
    require(all(row["u_target_status"] == "UNKNOWN" and row["e_paired_status"] == "UNKNOWN" for row in funnel), "U_target/E_paired overclaim", errors)
    require(all(row["c5_candidate_availability"] == "MISSING" and row["c5_eligible"] == "false" for row in funnel), "C5 funnel mismatch", errors)
    expected_funnel, reference_counts = recompute_reference_candidates(root, config)
    validate_funnel_rows(funnel, expected_funnel, errors)
    id_bytes = "".join(f"{item['stable_id']}\n" for item in expected_funnel).encode()
    pair_bytes = "".join(
        f"{item['stable_id']}|{item['provider_external_id']}\n"
        for item in expected_funnel
    ).encode()
    require(sha256_bytes(id_bytes) == "047717a5d678aeed540602a2d4fc9a57a076e2ac9205b22a4de75315c1622fe5", "stable ID hash mismatch", errors)
    require(sha256_bytes(pair_bytes) == "330598a07840972e1371aa77b21ee42f19065c8c401fa8f1b78b3bb82f6f44da", "ID pair hash mismatch", errors)
    require(reference_counts == {"LOD2_REFERENCE_690_5334": 35, "LOD2_REFERENCE_690_5336": 164, "REFERENCE_TOTAL": 12049}, "reference counts mismatch", errors)
    require(sum(row["c1_numeric_bbox_full_unregistered"] == "true" for row in funnel) == 187, "C1 diagnostic count mismatch", errors)
    require(sum(row["c2_numeric_bbox_full_unregistered"] == "true" for row in funnel) == 197, "C2 diagnostic count mismatch", errors)
    require(sum(row["c4_provider_tile_full_unregistered"] == "true" for row in funnel) == 199, "C4 diagnostic count mismatch", errors)

    coordinates = read_csv(DOC_ROOT / "coordinate_reference_matrix_v1.csv")
    require(len(coordinates) == 6, "coordinate matrix row count mismatch", errors)
    require(next(row for row in coordinates if row["condition"] == "C5_GS_lod1_prior")["status"] == "MISSING", "C5 coordinate status mismatch", errors)

    reference = read_json(DOC_ROOT / "evaluation_reference_lineage_v1.json")
    require(reference["scientific_verdict"] is None, "reference verdict must be null", errors)
    geometry_classes = {item["condition"]: item["class"] for item in reference["geometry_reference_candidate"]["condition_overlap_class"]}
    require(geometry_classes.get("C1_L_upper") == "SELF_REFERENCE", "C1 self-reference class missing", errors)
    require("RoofSurface" in reference["structure_reference"]["forbidden_input_fields"], "reference leakage guard missing", errors)
    structure_classes = {
        item["condition"]: item["class"]
        for item in reference["structure_reference_overlap_class"]
    }
    require(structure_classes.get("C2_MVS") == "UNKNOWN", "C2 structure overlap overclaim", errors)
    require(structure_classes.get("C3_GS_image") == "UNKNOWN", "C3 structure overlap overclaim", errors)
    require(
        structure_classes.get("C4_GS_lidar_prior") == "UNKNOWN_OR_PARTIALLY_SHARED",
        "C4 structure overlap overclaim",
        errors,
    )

    provenance = read_csv(DOC_ROOT / "condition_provenance_matrix_v1.csv")
    status = {(row["condition"], row["field"]): row["status"] for row in provenance}
    require(status.get(("C2_MVS", "same_937_image_base")) == "MISSING", "C2 mismatch status missing", errors)
    require(status.get(("C3_GS_image", "sparse_initialization")) == "READY", "C3 sparse status mismatch", errors)
    require(status.get(("C5_GS_lod1_prior", "independent_lod1")) == "MISSING", "C5 status mismatch", errors)
    require(status.get(("ALL", "U_target")) == "UNKNOWN", "U_target status mismatch", errors)

    tools = read_json(DOC_ROOT / "stage3_toolchain_inventory_v1.json")
    require(tools["scientific_verdict"] is None, "toolchain verdict must be null", errors)
    require(tools["overall_status"] == "BLOCKED", "toolchain status mismatch", errors)
    require(tools["thresholds_or_adapter_selected"] is False, "adapter/threshold must remain unselected", errors)
    commands = {item["command"]: item["status"] for item in tools["command_inventory"]}
    require(commands.get("cjio") == "FOUND", "cjio inventory mismatch", errors)
    for command in ("roofer", "roofer-cli", "cjval", "val3dity", "ogr2ogr", "pdal"):
        require(commands.get(command) == "MISSING", f"tool status mismatch: {command}", errors)

    report = (DOC_ROOT / "REMEDIATION_EVIDENCE_REPORT_v1.md").read_text(encoding="utf-8")
    issues = (DOC_ROOT / "remediation_issue_log_v1.md").read_text(encoding="utf-8")
    returned = RETURN_PATH.read_text(encoding="utf-8")
    for label, text in (("report", report), ("issues", issues), ("return", returned)):
        require("scientific_verdict: null" in text, f"{label} null verdict marker missing", errors)
        require("BLOCKED_FOR_GATE_S0_REMEDIATION_REVIEW" in text, f"{label} status marker missing", errors)
    require("No joint-prior synergy claim" in report, "joint-prior limitation missing", errors)
    require("output_commit: `SELF`" in returned, "Return SELF marker missing", errors)
    require("held_out_accessed=false" in report, "report held-out flag missing", errors)
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write-output-manifest", action="store_true")
    parser.add_argument(
        "--artifact-root",
        type=Path,
        default=Path(os.environ.get("JBGS_ARTIFACT_ROOT", "/artifacts/JointBuildGS")),
    )
    args = parser.parse_args()
    if args.write_output_manifest:
        write_output_manifest()
    errors = validate(args.artifact_root.resolve(), verify_self=not args.write_output_manifest)
    if errors:
        print("Gate S0 remediation evidence: FAIL")
        for error in errors:
            print(f"  - {error}")
        return 1
    print(
        "Gate S0 remediation evidence: PASS "
        "(status=BLOCKED_FOR_GATE_S0_REMEDIATION_REVIEW, scientific_verdict=null)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
