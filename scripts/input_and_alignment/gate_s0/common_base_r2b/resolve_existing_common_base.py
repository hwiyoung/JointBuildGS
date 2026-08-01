#!/usr/bin/env python3
"""Resolve retained exact-937 common-base lineage without reading payload bytes.

The completed ledger is the first external-operation lookup.  An exact repeat exits
before resolving the artifact root; a conflicting operation is blocked at the same
point.  Only the first invocation reads the bounded metadata declared in the config.
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
from pathlib import Path
from typing import Any


CONFIG_PATH = Path(
    "configs/input_and_alignment/gate_s0/common_base_r2b/r2b_lineage_v1.json"
)
SCRIPT_PATH = Path(
    "scripts/input_and_alignment/gate_s0/common_base_r2b/resolve_existing_common_base.py"
)
MANIFEST_ROOT = Path("artifacts/manifests/gate_s0/common_base_r2b")
LINEAGE_PATH = MANIFEST_ROOT / "existing_common_base_derivative_lineage_v1.json"
CROSSWALK_PATH = MANIFEST_ROOT / "exact_937_member_crosswalk_v1.json"
READINESS_PATH = MANIFEST_ROOT / "component_readiness_v1.csv"
LEDGER_PATH = MANIFEST_ROOT / "no_repeat_operation_ledger_v1.json"


class NamespaceConflict(RuntimeError):
    """Raised before external access when an existing namespace identity differs."""


def canonical_json_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def normalize_lf(value: bytes) -> bytes:
    return value.replace(b"\r\n", b"\n").replace(b"\r", b"\n")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def set_bytes(values: set[str] | list[str]) -> bytes:
    return ("\n".join(sorted(set(values))) + "\n").encode("utf-8")


def set_sha256(values: set[str] | list[str]) -> str:
    return sha256_bytes(set_bytes(values))


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def git(*args: str, cwd: Path | None = None, binary: bool = False) -> str | bytes:
    repo = (cwd or Path.cwd()).resolve()
    result = subprocess.run(
        ["git", "-c", f"safe.directory={repo}", *args],
        cwd=repo,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=not binary,
    )
    return result.stdout


def git_blob_oid(repo: Path, path: Path) -> str:
    result = git(
        "hash-object", "--path", path.as_posix(), path.as_posix(), cwd=repo
    )
    assert isinstance(result, str)
    return result.strip()


def build_operation_identity(
    config_path: Path = CONFIG_PATH,
    script_path: Path = SCRIPT_PATH,
    repo: Path | None = None,
) -> dict[str, Any]:
    repo = (repo or Path.cwd()).resolve()
    config_abs = config_path if config_path.is_absolute() else repo / config_path
    script_abs = script_path if script_path.is_absolute() else repo / script_path
    config_rel = config_abs.relative_to(repo)
    script_rel = script_abs.relative_to(repo)
    config = read_json(config_abs)
    core = {
        "schema": "jointbuildgs.gate_s0_r2b_operation_identity.v1",
        "task_id": config["task_id"],
        "source_candidate_manifest_sha256": config["source_candidate"][
            "manifest_sha256"
        ],
        "executable": {
            "path": script_rel.as_posix(),
            "git_blob_oid": git_blob_oid(repo, script_rel),
            "containing_commit": "SELF",
            "containing_commit_rule": (
                "SELF resolves to the immutable R2B output commit that first contains "
                "this exact path/blob; the validator proves the binding"
            ),
        },
        "config": {
            "path": config_rel.as_posix(),
            "sha256_lf": sha256_bytes(normalize_lf(config_abs.read_bytes())),
        },
        "producer_script_git_blob": config["producer"]["script_git_blob"],
        "producer_script_containing_commit": config["producer"][
            "actual_script_containing_commit"
        ],
        "scientific_role": "Gate-S0 retained common-base lineage resolution only",
    }
    return {**core, "operation_id": sha256_bytes(canonical_json_bytes(core))}


def completed_lookup(ledger_path: Path, identity: dict[str, Any]) -> dict[str, Any] | None:
    """Return an exact completed no-op or block, without external filesystem access."""
    if not ledger_path.exists():
        return None
    ledger_bytes = ledger_path.read_bytes()
    ledger = json.loads(ledger_bytes)
    if ledger.get("status") != "COMPLETED":
        raise NamespaceConflict("BLOCKED_INCOMPLETE_LEDGER")
    if ledger.get("operation_identity", {}).get("operation_id") != identity["operation_id"]:
        raise NamespaceConflict("BLOCKED_NAMESPACE_CONFLICT")
    return {
        "status": "REUSED_COMPLETED",
        "operation_id": identity["operation_id"],
        "ledger_sha256": sha256_bytes(ledger_bytes),
        "external_payload_read_bytes": 0,
        "external_payload_hashed_bytes": 0,
        "external_metadata_read_bytes": 0,
        "external_metadata_hashed_bytes": 0,
        "external_directory_entries_statted": 0,
        "repository_output_bytes_read_or_hashed": 0,
        "writes": 0,
    }


def read_external_metadata(
    payload_root: Path, records: list[dict[str, Any]], counters: dict[str, int]
) -> dict[str, bytes]:
    values: dict[str, bytes] = {}
    for record in records:
        path = payload_root / record["path"]
        value = path.read_bytes()
        counters["external_metadata_read_bytes"] += len(value)
        counters["external_metadata_hashed_bytes"] += len(value)
        if len(value) != record["bytes"]:
            raise RuntimeError(f"bounded metadata size mismatch: {record['path']}")
        if sha256_bytes(value) != record["sha256"]:
            raise RuntimeError(f"bounded metadata digest mismatch: {record['path']}")
        values[record["path"]] = value
    return values


def inventory_path(path: Path, kind: str, counters: dict[str, int]) -> dict[str, Any]:
    """Stat path entries only.  Never open a retained payload file."""
    if kind == "file":
        stat = path.stat()
        counters["external_directory_entries_statted"] += 1
        return {"exists": True, "files": 1, "bytes": stat.st_size}
    files = 0
    byte_count = 0
    stack = [path]
    while stack:
        current = stack.pop()
        with os.scandir(current) as entries:
            for entry in entries:
                counters["external_directory_entries_statted"] += 1
                if entry.is_dir(follow_symlinks=False):
                    stack.append(Path(entry.path))
                elif entry.is_file(follow_symlinks=False):
                    stat = entry.stat(follow_symlinks=False)
                    files += 1
                    byte_count += stat.st_size
                else:
                    raise RuntimeError(f"unsupported retained entry: {entry.path}")
    return {"exists": True, "files": files, "bytes": byte_count}


def source_members(repo: Path) -> tuple[list[dict[str, str]], set[str]]:
    ledger_path = repo / (
        "docs/research/preregistration/gate_s0/gate_s0_image_camera_ledger_v1.csv"
    )
    with ledger_path.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    included = [row for row in rows if row["status"] == "INCLUDED"]
    excluded = [row for row in rows if row["status"] != "INCLUDED"]
    if len(rows) != 962 or len(included) != 937 or len(excluded) != 25:
        raise RuntimeError("source membership no longer equals exact 962/937/25")
    return included, {row["basename"] for row in included}


def parse_colmap_images(value: bytes) -> dict[str, tuple[int, int]]:
    result: dict[str, tuple[int, int]] = {}
    for line in value.decode("utf-8").splitlines():
        fields = line.split()
        if not fields or fields[0].startswith("#") or len(fields) != 10:
            continue
        try:
            image_id = int(fields[0])
            camera_model_id = int(fields[8])
        except ValueError:
            continue
        result[fields[9]] = (image_id, camera_model_id)
    return result


def exact_known_tokens(value: bytes, known: set[str]) -> set[str]:
    tokens = re.findall(r"[A-Za-z0-9_.-]+\.(?:JPG|jpg|JPEG|jpeg)", value.decode("utf-8"))
    return {token for token in tokens if token in known}


def map_variants(directory: Path, suffixes: tuple[str, ...]) -> dict[str, set[str]]:
    result = {suffix: set() for suffix in suffixes}
    with os.scandir(directory) as entries:
        for entry in entries:
            if not entry.is_file(follow_symlinks=False):
                continue
            for suffix in suffixes:
                if entry.name.endswith(suffix):
                    result[suffix].add(entry.name[: -len(suffix)])
                    break
    return result


def csv_bytes(rows: list[dict[str, str]], fields: list[str]) -> bytes:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode("utf-8")


def inspect_and_build(
    repo: Path, artifact_root: Path, config: dict[str, Any], identity: dict[str, Any]
) -> tuple[dict[Path, bytes], dict[str, Any]]:
    counters = {
        "external_payload_read_bytes": 0,
        "external_payload_hashed_bytes": 0,
        "external_metadata_read_bytes": 0,
        "external_metadata_hashed_bytes": 0,
        "external_directory_entries_statted": 0,
    }
    payload_root = artifact_root / config["payload_root"]
    metadata = read_external_metadata(payload_root, config["bounded_metadata"], counters)
    retained: dict[str, dict[str, Any]] = {}
    for candidate in config["retained_candidates"]:
        result = inventory_path(payload_root / candidate["path"], candidate["kind"], counters)
        result["matches_retention_manifest"] = (
            result["files"] == candidate["expected_files"]
            and result["bytes"] == candidate["expected_bytes"]
        )
        if not result["matches_retention_manifest"]:
            raise RuntimeError(f"retained candidate stat mismatch: {candidate['component']}")
        retained[candidate["component"]] = {**candidate, **result}

    source_rows, known = source_members(repo)
    expected_source_hash = config["source_candidate"]["included_basename_set_sha256"]
    if set_sha256(known) != expected_source_hash:
        raise RuntimeError("Git source member set hash mismatch")

    image_dir = payload_root / "data/work/mvs/colmap_dense/images"
    image_names = {entry.name for entry in os.scandir(image_dir) if entry.is_file()}
    image_list = set(metadata["data/work/mvs/image_list.txt"].decode("utf-8").splitlines())
    colmap_map = parse_colmap_images(metadata["data/work/mvs/colmap_input_db_ids/images.txt"])
    patch_set = exact_known_tokens(
        metadata["data/work/mvs/colmap_dense/stereo/patch-match.cfg"], known
    )
    fusion_set = exact_known_tokens(
        metadata["data/work/mvs/colmap_dense/stereo/fusion.cfg"], known
    )
    densify_set = exact_known_tokens(
        metadata["data/work/mvs/openmvs/DensifyPointCloud-2606111411078B4571.log"], known
    )
    depth = map_variants(
        payload_root / "data/work/mvs/colmap_dense/stereo/depth_maps",
        (".geometric.bin", ".photometric.bin"),
    )
    normal = map_variants(
        payload_root / "data/work/mvs/colmap_dense/stereo/normal_maps",
        (".geometric.bin", ".photometric.bin"),
    )
    observed_sets = {
        "git_source": known,
        "retained_images": image_names,
        "t3_image_list": image_list,
        "colmap_sparse_model_names": set(colmap_map),
        "patch_match_config_names": patch_set,
        "fusion_config_names": fusion_set,
        "densify_log_names": densify_set,
        "geometric_depth_names": depth[".geometric.bin"],
        "photometric_depth_names": depth[".photometric.bin"],
        "geometric_normal_names": normal[".geometric.bin"],
        "photometric_normal_names": normal[".photometric.bin"],
    }
    set_checks = {
        name: {
            "count": len(values),
            "set_sha256": set_sha256(values),
            "equals_exact_source": values == known,
        }
        for name, values in observed_sets.items()
    }
    if not all(item["equals_exact_source"] for item in set_checks.values()):
        failed = [name for name, item in set_checks.items() if not item["equals_exact_source"]]
        raise RuntimeError(f"exact-937 member contradiction: {failed}")
    if len(set(colmap_map.values())) != 937 or {v[1] for v in colmap_map.values()} != {1}:
        raise RuntimeError("COLMAP image/camera-model mapping is not one-to-one exact-937")

    crosswalk_rows: list[dict[str, Any]] = []
    for row in sorted(source_rows, key=lambda item: item["basename"]):
        name = row["basename"]
        image_id, camera_model_id = colmap_map[name]
        crosswalk_rows.append(
            {
                "basename": name,
                "source_camera_uid": row["camera_id"],
                "colmap_image_id": image_id,
                "colmap_camera_model_id": camera_model_id,
                "retained_image": name in image_names,
                "patch_match_member": name in patch_set,
                "fusion_member": name in fusion_set,
                "geometric_depth": name in depth[".geometric.bin"],
                "photometric_depth": name in depth[".photometric.bin"],
                "geometric_normal": name in normal[".geometric.bin"],
                "photometric_normal": name in normal[".photometric.bin"],
            }
        )

    components = [
        {
            "component": "source_membership",
            "lineage_classification": "REUSED_EXACT",
            "existence": "EXISTS",
            "exact_lineage": "EXACT_962_937_25_FROZEN_BY_DEC_P1_012",
            "gate_readiness": "READY",
            "enablement_decision": "FIXED_BY_DEC_P1_012",
            "new_preprocessing": "UNNECESSARY",
        },
        {
            "component": "sfm_sparse",
            "lineage_classification": "REUSED_EXACT",
            "existence": "EXISTS",
            "exact_lineage": "EXACT_937_MEMBER_AND_PRODUCER_ROUTE",
            "gate_readiness": "PARTIAL",
            "enablement_decision": "HUMAN_GATE_DECISION_REQUIRED",
            "new_preprocessing": "UNNECESSARY_IF_EXISTING_CHAIN_ACCEPTED",
        },
        {
            "component": "dense_mvs",
            "lineage_classification": "PARTIAL",
            "existence": "EXISTS",
            "exact_lineage": "EXACT_937_PRODUCER_CHAIN_PAYLOAD_DIGEST_PENDING",
            "gate_readiness": "PARTIAL",
            "enablement_decision": "REQUIRED_FOR_C2; HUMAN_CANDIDATE_ACCEPTANCE_REQUIRED",
            "new_preprocessing": "UNNECESSARY_IF_EXISTING_CHAIN_ACCEPTED",
        },
        {
            "component": "depth",
            "lineage_classification": "PARTIAL",
            "existence": "EXISTS_EXACT_937_GEOMETRIC_AND_PHOTOMETRIC",
            "exact_lineage": "MEMBERSHIP_EXACT_PRODUCER_RUN_UNBOUND",
            "gate_readiness": "PARTIAL",
            "enablement_decision": "HUMAN_ON_OFF_REQUIRED",
            "new_preprocessing": "NOT_YET_DECIDABLE",
        },
        {
            "component": "normal",
            "lineage_classification": "PARTIAL",
            "existence": "EXISTS_EXACT_937_GEOMETRIC_AND_PHOTOMETRIC",
            "exact_lineage": "MEMBERSHIP_EXACT_PRODUCER_RUN_UNBOUND",
            "gate_readiness": "PARTIAL",
            "enablement_decision": "HUMAN_ON_OFF_REQUIRED",
            "new_preprocessing": "NOT_YET_DECIDABLE",
        },
        {
            "component": "confidence",
            "lineage_classification": "MISSING",
            "existence": "MISSING",
            "exact_lineage": "NONE",
            "gate_readiness": "MISSING",
            "enablement_decision": "HUMAN_ON_OFF_REQUIRED",
            "new_preprocessing": "CONDITIONAL_ON_ENABLEMENT",
        },
        {
            "component": "segmentation",
            "lineage_classification": "MISSING",
            "existence": "MISSING",
            "exact_lineage": "NONE",
            "gate_readiness": "MISSING",
            "enablement_decision": "HUMAN_ON_OFF_REQUIRED",
            "new_preprocessing": "CONDITIONAL_ON_ENABLEMENT",
        },
        {
            "component": "gravity",
            "lineage_classification": "MISSING",
            "existence": "MISSING",
            "exact_lineage": "NONE",
            "gate_readiness": "MISSING",
            "enablement_decision": "REQUIRED_BY_ROOT_INVARIANT; SOURCE_BINDING_PENDING",
            "new_preprocessing": "REQUIRED_LATER_FROM_TERRAIN_MVS_NORMALS",
        },
    ]

    lineage = {
        "schema": "jointbuildgs.gate_s0_existing_common_base_derivative_lineage.v1",
        "task_id": config["task_id"],
        "source_candidate_id": config["source_candidate"]["id"],
        "source_membership": config["source_candidate"],
        "retained_candidates": retained,
        "producer_lineage": {
            **config["producer"],
            "recorded_run_commit_interpretation": (
                "run logger captured the parent before 03_mvs.sh existed; the exact "
                "producer executable first appears in actual_script_containing_commit"
            ),
            "route": [
                "exact-937 OPF/COLMAP sparse",
                "colmap_dense/images + colmap_dense/sparse",
                "InterfaceCOLMAP -> scene.mvs",
                "DensifyPointCloud -> dim_dense.ply",
                "PDAL translation -> dim_v1.laz EPSG:25832",
            ],
            "openmvs_loaded_poses": 937,
            "openmvs_fused_depth_maps": 924,
            "dense_point_count": 43942554,
        },
        "member_set_checks": set_checks,
        "coordinate_frame": config["coordinate_frame"],
        "existing_payload_digests": "MISSING_NOT_HASHED_IN_R2B",
        "future_single_pass_hash": config["future_single_pass_hash"],
        "depth_normal_producer_gap": (
            "exact-937 files exist and match generated COLMAP configs, but their "
            "2026-06-24 producer invocation/log is not durably bound"
        ),
        "components": components,
        "large_payload_full_read_bytes": 0,
        "large_payload_full_hashed_bytes": 0,
        "generated_derivatives": [],
        "performance_authority": "NONE",
        "scientific_verdict": None,
    }
    crosswalk = {
        "schema": "jointbuildgs.gate_s0_exact_937_member_crosswalk.v1",
        "task_id": config["task_id"],
        "join_rule": config["source_candidate"]["join_rule"],
        "member_count": len(crosswalk_rows),
        "source_basename_set_sha256": expected_source_hash,
        "source_camera_uid_set_sha256": config["source_candidate"][
            "included_camera_id_set_sha256"
        ],
        "all_component_sets_equal": True,
        "set_checks": set_checks,
        "rows": crosswalk_rows,
        "scientific_verdict": None,
    }
    readiness_rows = [
        {key: str(item[key]) for key in (
            "component", "lineage_classification", "existence", "exact_lineage",
            "gate_readiness", "enablement_decision", "new_preprocessing"
        )}
        for item in components
    ]
    fields = list(readiness_rows[0])
    outputs = {
        LINEAGE_PATH: canonical_json_bytes(lineage),
        CROSSWALK_PATH: canonical_json_bytes(crosswalk),
        READINESS_PATH: csv_bytes(readiness_rows, fields),
    }
    ledger = {
        "schema": "jointbuildgs.gate_s0_r2b_no_repeat_operation_ledger.v1",
        "task_id": config["task_id"],
        "namespace": config["source_candidate"]["id"] + "/common-base-lineage-r2b-v1",
        "status": "COMPLETED",
        "operation_identity": identity,
        "completed_lookup_precedes_external_access": True,
        "completed_ledger_overwrite_allowed": False,
        "candidate_matching": "exact manifest paths plus component-aware exact member sets",
        "first_invocation": counters,
        "second_invocation_contract": {
            "external_payload_read_bytes": 0,
            "external_payload_hashed_bytes": 0,
            "external_metadata_read_bytes": 0,
            "external_metadata_hashed_bytes": 0,
            "external_directory_entries_statted": 0,
            "repository_output_bytes_read_or_hashed": 0,
            "writes": 0,
        },
        "forbidden_full_hashes_performed": [],
        "protected_large_payload_full_read_bytes": 0,
        "protected_large_payload_full_hashed_bytes": 0,
        "bounded_metadata_records": config["bounded_metadata"],
        "scientific_verdict": None,
    }
    outputs[LEDGER_PATH] = canonical_json_bytes(ledger)
    return outputs, counters


def write_add_once(repo: Path, outputs: dict[Path, bytes]) -> None:
    paths = list(outputs)
    # Ledger is published last; no existing file is ever rewritten.
    paths.sort(key=lambda path: path == LEDGER_PATH)
    for relative in paths:
        path = repo / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with path.open("xb") as stream:
                stream.write(outputs[relative])
        except FileExistsError as error:
            raise NamespaceConflict(f"BLOCKED_EXISTING_OUTPUT:{relative}") from error


def execute(
    repo: Path,
    artifact_root: Path,
    config_path: Path = CONFIG_PATH,
    script_path: Path = SCRIPT_PATH,
    ledger_path: Path = LEDGER_PATH,
) -> dict[str, Any]:
    config_abs = config_path if config_path.is_absolute() else repo / config_path
    script_abs = script_path if script_path.is_absolute() else repo / script_path
    identity = build_operation_identity(config_abs, script_abs, repo)
    ledger_abs = ledger_path if ledger_path.is_absolute() else repo / ledger_path
    reused = completed_lookup(ledger_abs, identity)
    if reused is not None:
        return reused
    config = read_json(config_abs)
    outputs, counters = inspect_and_build(repo, artifact_root, config, identity)
    write_add_once(repo, outputs)
    return {
        "status": "EXECUTED_ADD_ONCE",
        "operation_id": identity["operation_id"],
        **counters,
        "writes": len(outputs),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=Path("."))
    parser.add_argument(
        "--artifact-root",
        type=Path,
        default=Path(os.environ.get("JBGS_ARTIFACT_ROOT", "/artifacts/JointBuildGS")),
    )
    args = parser.parse_args()
    try:
        result = execute(args.repo.resolve(), args.artifact_root)
    except NamespaceConflict as error:
        print(str(error))
        return 3
    except Exception as error:  # explicit visible task failure
        print(f"R2B_RESOLUTION_FAILED: {error}")
        return 1
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
