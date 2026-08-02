"""Add-once finalize recovery over the sealed R3 operation namespace.

This module has no source-preparation or reconstruction interface.  It reads the
small, explicitly allowlisted R3 ledgers and seven native CityJSONSeq files from a
read-only source root, then writes a fresh R4 result namespace.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import subprocess
from collections import defaultdict
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any, Mapping, Sequence

import numpy as np

from scripts.p2_baselines.c1_c2_feasibility_pilot_v1 import contract as source_contract


REPO = Path(__file__).resolve().parents[3]
CONFIG_PATH = REPO / "configs/p2_baselines/c1_c2_feasibility_pilot_finalize_recovery_r4_v1/recovery_v1.json"
TASK_ID = "P2-C1-C2-FEASIBILITY-PILOT-FINALIZE-RECOVERY-R4-v1"
HANDOFF_ID = "P2-W2C-C1-C2-FEASIBILITY-PILOT-FINALIZE-RECOVERY-R4-v1"
RUN_ID = "P2-C1-C2-FEASIBILITY-PILOT-FINALIZE-RECOVERY-R4-RUN-v1"
EXECUTION_MODE = "FINALIZE_ONLY_REUSE"
PACKET_PATH = "docs/handoffs/P2_W2C_C1_C2_FEASIBILITY_PILOT_FINALIZE_RECOVERY_R4_v1.md"
SOURCE_R3_TASK_ID = "P2-C1-C2-FEASIBILITY-PILOT-RECOVERY-R3-v1"
SOURCE_R3_RUN_ID = "P2-C1-C2-FEASIBILITY-PILOT-RECOVERY-R3-RUN-v1"
LAS12_HEADER_BYTES = 227
LAS_POINT_FORMAT_3_BYTES = 34

AddOnceStore = source_contract.AddOnceStore
canonical_json_bytes = source_contract.canonical_json_bytes
sha256_bytes = source_contract.sha256_bytes


def load_config() -> dict[str, Any]:
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def _frozen_source_manifest(config: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    """Load the Work-reviewed exact R3 derived-file surface."""

    contract = config["source_manifest_contract"]
    path = _safe_repo_path(str(contract["git_path"]))
    body = json.loads(path.read_bytes())
    records = body.get("records")
    if not isinstance(records, list):
        raise RuntimeError("frozen R3 finalize source manifest has no records")
    identity = sha256_bytes(canonical_json_bytes(records))
    if (
        body.get("schema") != "jointbuildgs.p2_c1_c2_r3_finalize_source_manifest.v1"
        or body.get("source_closed_commit") != config["source_r3"]["closed_commit"]
        or body.get("source_operation_id") != config["source_r3"]["operation_id"]
        or body.get("record_count") != contract["record_count"]
        or body.get("total_bytes") != contract["total_bytes"]
        or body.get("record_identity_sha256") != contract["manifest_records_sha256"]
        or identity != contract["manifest_records_sha256"]
        or body.get("original_scientific_source_records") != 0
        or body.get("operation_las_records") != 0
        or body.get("scientific_verdict") is not None
    ):
        raise RuntimeError("frozen R3 finalize source manifest identity mismatch")
    allowlist = config["source_manifest_allowlist"]
    exact = set(allowlist["exact_paths"])
    patterns = [re.compile(value) for value in allowlist["path_patterns"]]
    result: dict[str, dict[str, Any]] = {}
    for record in records:
        if not isinstance(record, Mapping):
            raise RuntimeError("frozen R3 source record is not an object")
        relative = str(record.get("path", ""))
        pure = PurePosixPath(relative)
        if (
            not relative or pure.is_absolute() or ".." in pure.parts or pure.as_posix() != relative
            or (relative not in exact and not any(pattern.fullmatch(relative) for pattern in patterns))
            or relative.endswith(".las")
            or record.get("verification_required") != contract["verification_method"]
            or int(record.get("bytes", -1)) < 0
            or not re.fullmatch(r"[0-9a-f]{64}", str(record.get("sha256", "")))
            or relative in result
        ):
            raise RuntimeError(f"frozen R3 source record is invalid: {relative}")
        result[relative] = {
            "path": relative,
            "bytes": int(record["bytes"]),
            "sha256": str(record["sha256"]),
        }
    if (
        len(result) != int(contract["record_count"])
        or len(result) != int(allowlist["expected_files_read"])
        or sum(record["bytes"] for record in result.values()) != int(contract["total_bytes"])
    ):
        raise RuntimeError("frozen R3 source manifest count/byte total mismatch")
    return result


def _safe_repo_path(relative: str) -> Path:
    path = (REPO / relative).resolve()
    try:
        path.relative_to(REPO.resolve())
    except ValueError as error:
        raise RuntimeError(f"repository path escapes root: {relative}") from error
    return path


def _git_blob(path: str, commit: str = "HEAD") -> str:
    return subprocess.run(
        ["git", "-C", str(REPO), "rev-parse", f"{commit}:{path}"],
        check=True, capture_output=True, text=True,
    ).stdout.strip()


def _git_output(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args], check=True, capture_output=True, text=True,
    ).stdout.strip()


def _direct_parent(repo: Path, commit: str) -> str:
    return _git_output(repo, "rev-parse", f"{commit}^")


def _packet_value(packet: str, key: str) -> str:
    matches = re.findall(rf"^- {re.escape(key)}: `([^`]+)`(?:\s.*)?$", packet, flags=re.MULTILINE)
    if len(matches) != 1:
        raise RuntimeError(f"activated R4 packet must bind exactly one {key}")
    return matches[0]


def validate_recovery_contract(config: Mapping[str, Any] | None = None) -> dict[str, Any]:
    config = dict(config or load_config())
    source = config["source_r3"]
    result = config["result"]
    if (
        config.get("task_id") != TASK_ID or config.get("handoff_id") != HANDOFF_ID
        or config.get("run_id") != RUN_ID or config.get("execution_mode") != EXECUTION_MODE
        or not re.fullmatch(r"sha256:[0-9a-f]{64}", str(config.get("project_image_id", "")))
    ):
        raise RuntimeError("R4 task/handoff identity mismatch")
    if source.get("task_id") != SOURCE_R3_TASK_ID or source.get("run_id") != SOURCE_R3_RUN_ID:
        raise RuntimeError("sealed R3 source identity mismatch")
    if source.get("closed_commit") != "551e633fb9b3f29418a5ba1620c10451b55ddcd6":
        raise RuntimeError("sealed R3 close commit mismatch")
    if _git_blob("configs/p2_baselines/c1_c2_feasibility_pilot_v1/pilot_v1.json", source["source_commit"]) != source["config_git_blob"]:
        raise RuntimeError("sealed R3 config blob mismatch")
    if _git_blob(source["closed_receipt_path"], source["closed_commit"]) != source["closed_receipt_git_blob"]:
        raise RuntimeError("sealed R3 close receipt blob mismatch")
    if _git_blob("docs/handoffs/returns/P2_C2W_C1_C2_FEASIBILITY_PILOT_RECOVERY_R3_RETURN_v1.md", source["return_commit"]) != source["return_git_blob"]:
        raise RuntimeError("sealed R3 Return blob mismatch")
    lineage = [
        source["source_commit"], source["activation_commit"], source["offered_commit"],
        source["accepted_commit"], source["return_commit"], source["blocked_commit"],
        source["closed_commit"],
    ]
    for parent, child in zip(lineage, lineage[1:]):
        actual_parent = subprocess.run(
            ["git", "-C", str(REPO), "rev-parse", f"{child}^"],
            check=True, capture_output=True, text=True,
        ).stdout.strip()
        if actual_parent != parent:
            raise RuntimeError("sealed R3 source/activation/offered/accepted/Return/blocked/closed chain is not direct-child")
    protected_source_paths = (
        "configs/p2_baselines/c1_c2_feasibility_pilot_v1/pilot_v1.json",
        "configs/p2_baselines/c1_c2_feasibility_pilot_v1/result_schema_v1.json",
        "configs/p2_baselines/c1_c2_feasibility_pilot_v1/development_roster_v1.csv",
        "configs/p2_baselines/c1_c2_feasibility_pilot_v1/development_score_scope_v1.csv",
        "scripts/p2_baselines/c1_c2_feasibility_pilot_v1/contract.py",
    )
    if any(_git_blob(path) != _git_blob(path, source["source_commit"]) for path in protected_source_paths):
        raise RuntimeError("R3 protected metric/config/roster/scope implementation drift")
    source_config = source_contract.load_config()
    scope = source_config["scope"]
    if (
        scope["building_count"] != source["expected_buildings"]
        or scope["group_count"] != source["expected_groups"]
        or scope["expected_result_rows"] != source["expected_result_rows"]
        or scope["condition_ids"] != result["conditions"]
        or scope["validation_payload_mount_allowed"]
        or scope["held_out_payload_mount_allowed"]
        or scope["c3_c5_allowed"]
    ):
        raise RuntimeError("R3 frozen scientific scope mismatch")
    if source_config["roofer_pointcloud"]["format"] != "LAS_1_2_POINT_FORMAT_3_UNCOMPRESSED":
        raise RuntimeError("R3 LAS point-count provenance mismatch")
    if config.get("scientific_verdict") is not None:
        raise RuntimeError("technical recovery cannot set a scientific verdict")
    frozen_source_manifest = _frozen_source_manifest(config)
    return {
        "status": "PASS_ZERO_ORIGINAL_SCIENTIFIC_PAYLOAD",
        "task_id": TASK_ID,
        "source_r3_closed_commit": source["closed_commit"],
        "expected_result_rows": source["expected_result_rows"],
        "expected_unique_execution_units": source["expected_unique_execution_units"],
        "frozen_source_record_count": len(frozen_source_manifest),
        "frozen_source_bytes": sum(record["bytes"] for record in frozen_source_manifest.values()),
        "original_scientific_payload_bytes_read_or_hashed": 0,
        "roofer_invocations": 0,
        "scientific_verdict": None,
    }


class SourceManifestReader:
    """Read each allowlisted sealed-source file at most once with exact identity."""

    def __init__(
        self,
        root: Path,
        config: Mapping[str, Any],
        expected_records: Mapping[str, Mapping[str, Any]],
    ):
        self.root = root.resolve()
        if root.is_symlink() or not self.root.is_dir():
            raise RuntimeError("sealed R3 source root is missing, non-directory, or symlinked")
        allowlist = config["source_manifest_allowlist"]
        self.exact = set(allowlist["exact_paths"])
        self.patterns = [re.compile(value) for value in allowlist["path_patterns"]]
        self.maximum_files = int(allowlist["maximum_files_read"])
        self.maximum_bytes = int(allowlist["maximum_bytes_read"])
        self.expected_file_count = int(allowlist["expected_files_read"])
        if len(expected_records) != self.expected_file_count or self.maximum_files != self.expected_file_count:
            raise RuntimeError("accepted sealed-source manifest file count mismatch")
        self.expected: dict[str, dict[str, Any]] = {}
        for relative, record in expected_records.items():
            normalized = self._normalize(relative)
            value = {
                "path": normalized,
                "bytes": int(record.get("bytes", -1)),
                "sha256": str(record.get("sha256", "")),
            }
            if value["bytes"] < 0 or not re.fullmatch(r"[0-9a-f]{64}", value["sha256"]):
                raise RuntimeError(f"accepted sealed-source manifest record is malformed: {relative}")
            self.expected[normalized] = value
        if sum(record["bytes"] for record in self.expected.values()) > self.maximum_bytes:
            raise RuntimeError("accepted sealed-source manifest exceeds the byte-read cap")
        self.cache: dict[str, bytes] = {}
        self.records: list[dict[str, Any]] = []
        self.total_bytes = 0

    def _normalize(self, relative: str) -> str:
        pure = PurePosixPath(relative)
        normalized = pure.as_posix()
        if pure.is_absolute() or ".." in pure.parts or normalized != relative or not relative:
            raise RuntimeError(f"sealed source path is not canonical relative: {relative}")
        if relative not in self.exact and not any(pattern.fullmatch(relative) for pattern in self.patterns):
            raise RuntimeError(f"sealed source path is outside recovery allowlist: {relative}")
        return relative

    def read(self, relative: str, expected: Mapping[str, Any] | None = None) -> bytes:
        relative = self._normalize(relative)
        manifest_expected = self.expected.get(relative)
        if manifest_expected is None:
            raise RuntimeError(f"sealed source path is absent from accepted manifest: {relative}")
        if expected is not None and any(
            expected.get(key) != manifest_expected[key] for key in ("path", "bytes", "sha256")
        ):
            raise RuntimeError(f"sealed source ledger/accepted-manifest identity mismatch: {relative}")
        if relative in self.cache:
            return self.cache[relative]
        if len(self.cache) >= self.maximum_files:
            raise RuntimeError("sealed source file-read cap exceeded")
        candidate = self.root / relative
        if candidate.is_symlink():
            raise RuntimeError(f"sealed source record is symlinked: {relative}")
        path = candidate.resolve()
        try:
            path.relative_to(self.root)
        except ValueError as error:
            raise RuntimeError("sealed source path escapes root") from error
        if not path.is_file():
            raise RuntimeError(f"sealed source record is missing/non-regular: {relative}")
        digest = hashlib.sha256()
        chunks: list[bytes] = []
        total = 0
        with path.open("rb") as handle:
            while True:
                chunk = handle.read(1024 * 1024)
                if not chunk:
                    break
                digest.update(chunk)
                chunks.append(chunk)
                total += len(chunk)
        observed = {"path": relative, "bytes": total, "sha256": digest.hexdigest(), "full_read_and_digest_passes": 1}
        if (
            manifest_expected["bytes"] != total
            or manifest_expected["sha256"] != observed["sha256"]
        ):
            raise RuntimeError(f"sealed source record identity mismatch: {relative}")
        if self.total_bytes + total > self.maximum_bytes:
            raise RuntimeError("sealed source byte-read cap exceeded")
        data = b"".join(chunks)
        self.total_bytes += total
        self.cache[relative] = data
        self.records.append(observed)
        return data

    def read_json(self, relative: str, expected: Mapping[str, Any] | None = None) -> dict[str, Any]:
        value = json.loads(self.read(relative, expected))
        if not isinstance(value, dict):
            raise RuntimeError(f"sealed source JSON is not an object: {relative}")
        return value


def _validated_transform(value: Any) -> tuple[np.ndarray, np.ndarray]:
    if not isinstance(value, Mapping):
        raise RuntimeError("CityJSONSeq transform is missing or not an object")
    scale = np.asarray(value.get("scale"), dtype=np.float64)
    translate = np.asarray(value.get("translate"), dtype=np.float64)
    if scale.shape != (3,) or translate.shape != (3,) or not np.all(np.isfinite(scale)) or not np.all(np.isfinite(translate)):
        raise RuntimeError("CityJSONSeq transform shape/value is invalid")
    return scale, translate


def _transformed_feature_vertices(record: Mapping[str, Any], transform: Mapping[str, Any]) -> np.ndarray:
    if "vertices" not in record or not isinstance(record["vertices"], list) or not record["vertices"]:
        raise RuntimeError("CityJSONFeature vertices are missing or empty")
    vertices = np.asarray(record["vertices"], dtype=np.float64)
    scale, translate = _validated_transform(transform)
    if vertices.ndim != 2 or vertices.shape[1] != 3 or not np.all(np.isfinite(vertices)):
        raise RuntimeError("CityJSONFeature vertex shape/value is invalid")
    return vertices * scale + translate


def roof_triangles_from_cityjsonseq(relative: str, data: bytes) -> list[np.ndarray]:
    """Parse one native header+feature sequence and inherit only its transform."""

    inherited: Mapping[str, Any] | None = None
    triangles: list[np.ndarray] = []
    header_count = 0
    feature_count = 0
    for line_number, line in enumerate(data.decode("utf-8").splitlines(), 1):
        if not line.strip():
            continue
        record = json.loads(line)
        if not isinstance(record, Mapping):
            raise RuntimeError(f"CityJSONSeq record is not an object: {relative}:{line_number}")
        record_type = record.get("type")
        if record_type == "CityJSON":
            header_count += 1
            if (
                header_count != 1
                or feature_count
                or record.get("vertices") != []
                or record.get("CityObjects") != {}
            ):
                raise RuntimeError("CityJSONSeq header must be one leading empty inheritance record")
            _validated_transform(record.get("transform"))
            inherited = record["transform"]
            continue
        if record_type != "CityJSONFeature" or inherited is None or "transform" in record:
            raise RuntimeError("CityJSONSeq feature is missing its leading transform header")
        feature_count += 1
        vertices = _transformed_feature_vertices(record, inherited)
        city_objects = record.get("CityObjects")
        if not isinstance(city_objects, Mapping) or not city_objects:
            raise RuntimeError("CityJSONFeature CityObjects are missing or empty")
        for city_object in city_objects.values():
            if not isinstance(city_object, Mapping):
                raise RuntimeError("CityJSONFeature contains an invalid CityObject")
            geometries = city_object.get("geometry", [])
            if not isinstance(geometries, list):
                raise RuntimeError("CityObject geometry is not an array")
            for geometry in geometries:
                if not isinstance(geometry, Mapping) or str(geometry.get("lod")) != "2.2":
                    continue
                try:
                    roof_rings = list(source_contract._roof_rings(geometry))
                except (TypeError, ValueError, IndexError) as error:
                    raise RuntimeError("LoD2.2 semantic/boundary structure is malformed") from error
                for ring in roof_rings:
                    if len(ring) >= 2 and ring[0] == ring[-1]:
                        ring = ring[:-1]
                    if len(ring) < 3 or any(index < 0 or index >= len(vertices) for index in ring):
                        raise RuntimeError("RoofSurface ring has invalid vertex references")
                    first = vertices[ring[0]]
                    for index in range(1, len(ring) - 1):
                        triangle = np.vstack((first, vertices[ring[index]], vertices[ring[index + 1]]))
                        if np.linalg.norm(np.cross(triangle[1] - triangle[0], triangle[2] - triangle[0])) > 1e-12:
                            triangles.append(triangle)
    if header_count != 1 or feature_count < 1 or not triangles:
        raise RuntimeError("CityJSONSeq lacks one header, feature records, or roof triangles")
    return triangles


def _point_count_from_record(record: Mapping[str, Any]) -> int:
    """Use the frozen LAS1.2/PF3 serializer contract without reopening LAS."""

    size = int(record.get("bytes", -1))
    digest = str(record.get("sha256", ""))
    if str(record.get("path", "")).endswith("/input.las") is False or not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise RuntimeError("R3 operation LAS record provenance is incomplete")
    payload = size - LAS12_HEADER_BYTES
    if payload < 0 or payload % LAS_POINT_FORMAT_3_BYTES:
        raise RuntimeError("R3 operation LAS byte size violates LAS1.2/PF3 fixed-record provenance")
    count = payload // LAS_POINT_FORMAT_3_BYTES
    if count <= 0:
        raise RuntimeError("R3 operation LAS derived point count is empty")
    return count


def _jsonl(data: bytes) -> list[dict[str, Any]]:
    values = source_contract.parse_jsonl(data)
    if any(not isinstance(value, dict) for value in values):
        raise RuntimeError("source JSONL row is not an object")
    return values


def _regular_bytes(path: Path, label: str) -> bytes:
    if not path.is_file() or path.is_symlink() or path.resolve() != path.absolute():
        raise RuntimeError(f"{label} must be an exact regular non-symlink file")
    return path.read_bytes()


def _validate_r4_git_authority(
    accepted_receipt_path: Path,
    accepted: Mapping[str, Any],
    *,
    source_commit: str,
    accepted_commit: str,
    project_image_id: str,
    run_id: str,
    repo_root: Path = REPO,
) -> dict[str, str]:
    repo_root = repo_root.resolve()
    receipt_path = accepted_receipt_path.resolve()
    try:
        receipt_relative = receipt_path.relative_to(repo_root).as_posix()
    except ValueError as error:
        raise RuntimeError("R4 accepted receipt is outside the repository") from error
    expected_receipt = f"artifacts/manifests/handoffs/{HANDOFF_ID}/100-accepted.json"
    offered_relative = f"artifacts/manifests/handoffs/{HANDOFF_ID}/000-offered.json"
    if receipt_relative != expected_receipt:
        raise RuntimeError("R4 accepted receipt path is not canonical")
    head = _git_output(repo_root, "rev-parse", "HEAD")
    origin = _git_output(repo_root, "rev-parse", "origin/main")
    receipt_commit = _git_output(repo_root, "log", "-1", "--format=%H", "--", receipt_relative)
    if head != origin or head != accepted_commit or receipt_commit != accepted_commit:
        raise RuntimeError("R4 accepted receipt commit is not exact clean HEAD/origin")
    if _git_output(repo_root, "status", "--porcelain=v1", "--untracked-files=all"):
        raise RuntimeError("R4 execution authority requires a clean repository")

    commits = accepted.get("commits") if isinstance(accepted.get("commits"), Mapping) else {}
    activation_commit = str(commits.get("base_main", ""))
    offered_commit = str(commits.get("offered_head", ""))
    if not all(re.fullmatch(r"[0-9a-f]{40}", value) for value in (source_commit, activation_commit, offered_commit, accepted_commit)):
        raise RuntimeError("R4 source/activation/offered/accepted commit identity is malformed")
    if (
        _direct_parent(repo_root, activation_commit) != source_commit
        or _direct_parent(repo_root, offered_commit) != activation_commit
        or _direct_parent(repo_root, accepted_commit) != offered_commit
    ):
        raise RuntimeError("R4 source/activation/offered/accepted chain is not direct-child")
    changed = lambda parent, child: set(filter(None, _git_output(
        repo_root, "diff", "--name-only", parent, child,
    ).splitlines()))
    if changed(source_commit, activation_commit) != {PACKET_PATH}:
        raise RuntimeError("R4 activation commit must change only the activated packet")
    if changed(activation_commit, offered_commit) != {offered_relative}:
        raise RuntimeError("R4 offered commit must change only 000-offered.json")
    if changed(offered_commit, accepted_commit) != {receipt_relative}:
        raise RuntimeError("R4 accepted commit must change only 100-accepted.json")

    offered_path = repo_root / offered_relative
    offered_bytes = _regular_bytes(offered_path, "R4 offered receipt")
    offered = json.loads(offered_bytes)
    previous = accepted.get("previous_receipt") if isinstance(accepted.get("previous_receipt"), Mapping) else {}
    if (
        _git_output(repo_root, "log", "-1", "--format=%H", "--", offered_relative) != offered_commit
        or previous.get("path") != offered_relative
        or previous.get("sha256") != sha256_bytes(offered_bytes)
        or offered.get("state") != "offered"
        or offered.get("commits", {}).get("base_main") != activation_commit
        or offered.get("commits", {}).get("offered_head") != "SELF"
    ):
        raise RuntimeError("R4 offered/accepted previous-receipt binding mismatch")

    packet = (repo_root / PACKET_PATH).read_text(encoding="utf-8")
    if (
        _packet_value(packet, "status") != "APPROVED_FOR_EXECUTION"
        or _packet_value(packet, "user_approval") != "APPROVED_FOR_EXECUTION"
        or _packet_value(packet, "source_commit") != source_commit
        or _packet_value(packet, "project_image_id") != project_image_id
        or _packet_value(packet, "run_id") != run_id
        or _packet_value(packet, "execution_mode") != EXECUTION_MODE
    ):
        raise RuntimeError("activated R4 packet invocation binding mismatch")
    return {
        "source_commit": source_commit,
        "activation_commit": activation_commit,
        "offered_commit": offered_commit,
        "accepted_commit": accepted_commit,
    }


def _validate_receipts(
    config: Mapping[str, Any], source_closed_receipt_path: Path, accepted_receipt_path: Path,
    handoff_id: str, source_commit: str, accepted_commit: str, project_image_id: str, run_id: str,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    closed_bytes = _regular_bytes(source_closed_receipt_path, "R3 closed receipt")
    accepted_bytes = _regular_bytes(accepted_receipt_path, "R4 accepted receipt")
    closed, accepted = json.loads(closed_bytes), json.loads(accepted_bytes)
    source = config["source_r3"]
    if sha256_bytes(closed_bytes) != source["closed_receipt_sha256"]:
        raise RuntimeError("R3 closed receipt byte identity mismatch")
    if (
        closed.get("schema") != "jointbuildgs.two_host_handoff.v1" or closed.get("template_only") is not False
        or closed.get("handoff_id") != source["handoff_id"] or closed.get("task_id") != source["task_id"]
        or closed.get("state") != "closed" or closed.get("direction") != "work_to_experiment"
        or closed.get("sender_role") != "work_host" or closed.get("receiver_role") != "experiment_host"
        or closed.get("receiver_ack", {}).get("role") != "experiment_host"
        or closed.get("receiver_ack", {}).get("status") != "closed"
        or closed.get("transport", {}).get("exclusive_writer_ack") is not True
        or closed.get("scientific", {}).get("scientific_verdict") is not None
    ):
        raise RuntimeError("R3 closed receipt identity/state mismatch")
    artifacts = accepted.get("artifacts") if isinstance(accepted.get("artifacts"), Mapping) else {}
    availability = artifacts.get("availability") if isinstance(artifacts.get("availability"), Mapping) else {}
    verification = accepted.get("verification") if isinstance(accepted.get("verification"), Mapping) else {}
    scientific = accepted.get("scientific") if isinstance(accepted.get("scientific"), Mapping) else {}
    run_binding = f"bind finalization run_id={RUN_ID} execution_mode={EXECUTION_MODE}"
    if (
        accepted.get("schema") != "jointbuildgs.two_host_handoff.v1" or accepted.get("template_only") is not False
        or accepted.get("handoff_id") != handoff_id or accepted.get("task_id") != TASK_ID
        or accepted.get("state") != "accepted" or accepted.get("direction") != "work_to_experiment"
        or accepted.get("sender_role") != "work_host" or accepted.get("receiver_role") != "experiment_host"
        or accepted.get("transport", {}).get("exclusive_writer_ack") is not True
        or accepted.get("receiver_ack", {}).get("role") != "experiment_host"
        or accepted.get("receiver_ack", {}).get("status") != "accepted"
        or verification.get("level") != "artifact_verified"
        or verification.get("verifier_role") != "experiment_host"
        or verification.get("docker_image_digest") != project_image_id
        or run_binding not in verification.get("commands", [])
        or artifacts.get("required_for_task") is not True
        or artifacts.get("attestation_reuse") is not None
        or availability.get("experiment_host") != "verified_local"
        or scientific.get("technical_state") != "pending"
        or scientific.get("scientific_verdict") is not None
        or scientific.get("promotion_status") != "not_requested"
        or not re.fullmatch(r"[0-9a-f]{40}", accepted_commit)
        or project_image_id != config["project_image_id"]
        or run_id != config["run_id"]
    ):
        raise RuntimeError("R4 accepted execution authority mismatch")
    lineage = _validate_r4_git_authority(
        accepted_receipt_path, accepted, source_commit=source_commit,
        accepted_commit=accepted_commit, project_image_id=project_image_id, run_id=run_id,
    )
    return closed, accepted, {
        "source_closed_receipt": {"path": source_closed_receipt_path.as_posix(), "bytes": len(closed_bytes), "sha256": sha256_bytes(closed_bytes)},
        "accepted_receipt": {"path": accepted_receipt_path.as_posix(), "bytes": len(accepted_bytes), "sha256": sha256_bytes(accepted_bytes)},
        "r4_git_lineage": lineage,
    }


def _accepted_source_manifest(
    accepted: Mapping[str, Any], config: Mapping[str, Any]
) -> dict[str, dict[str, Any]]:
    artifacts = accepted.get("artifacts")
    records = artifacts.get("records") if isinstance(artifacts, Mapping) else None
    if not isinstance(records, list):
        raise RuntimeError("R4 accepted receipt lacks its exact R3-derived source manifest")
    prefix = config["source_r3"]["external_namespace"]
    result: dict[str, dict[str, Any]] = {}
    identities: list[dict[str, Any]] = []
    for record in records:
        if not isinstance(record, Mapping):
            raise RuntimeError("R4 accepted source-manifest record is malformed")
        uri = str(record.get("uri", ""))
        verified_at = record.get("verified_at")
        try:
            if not isinstance(verified_at, str) or not verified_at:
                raise ValueError
            datetime.fromisoformat(verified_at.replace("Z", "+00:00"))
        except ValueError as error:
            raise RuntimeError("R4 accepted source record has invalid verified_at") from error
        if (
            not uri.startswith(prefix)
            or record.get("verification_method") != "sha256_rehash"
            or record.get("verified_by") != "experiment_host"
        ):
            raise RuntimeError("R4 accepted source record lacks exact Experiment Host rehash authority")
        relative = uri[len(prefix):]
        if relative in result:
            raise RuntimeError(f"duplicate R4 accepted source-manifest path: {relative}")
        result[relative] = {
            "path": relative,
            "bytes": record.get("bytes"),
            "sha256": record.get("sha256"),
        }
        identities.append({key: record.get(key) for key in ("uri", "bytes", "sha256")})
    expected = int(config["source_manifest_allowlist"]["expected_files_read"])
    if len(result) != expected:
        raise RuntimeError("R4 accepted source-manifest exact file count mismatch")
    frozen = _frozen_source_manifest(config)
    if result != frozen:
        raise RuntimeError("R4 accepted source manifest differs from the Work-reviewed exact R3 surface")
    identity = sha256_bytes(canonical_json_bytes(sorted(identities, key=lambda item: item["uri"])))
    if identity != config["source_manifest_contract"]["accepted_record_identity_sha256"]:
        raise RuntimeError("R4 accepted canonical artifact-record identity mismatch")
    return result


def validate_execution_authority(
    *,
    source_closed_receipt_path: Path,
    accepted_receipt_path: Path,
    source_commit: str,
    accepted_commit: str,
    project_image_id: str,
    run_id: str,
) -> dict[str, Any]:
    """Validate exact Git/receipt authority without opening any external artifact."""

    config = load_config()
    contract_result = validate_recovery_contract(config)
    _, accepted, receipt_records = _validate_receipts(
        config, source_closed_receipt_path, accepted_receipt_path, HANDOFF_ID,
        source_commit, accepted_commit, project_image_id, run_id,
    )
    records = _accepted_source_manifest(accepted, config)
    return {
        **contract_result,
        "status": "PASS_EXACT_ACCEPTED_AUTHORITY_NO_ARTIFACT_READ",
        "run_id": run_id,
        "execution_mode": config["execution_mode"],
        "accepted_commit": accepted_commit,
        "accepted_source_records": len(records),
        "accepted_source_bytes": sum(int(record["bytes"]) for record in records.values()),
        "receipt_records": receipt_records,
    }


def _source_rows(reader: SourceManifestReader, prepared: Mapping[str, Any], config: Mapping[str, Any]) -> tuple[
    list[dict[str, Any]], list[dict[str, Any]], dict[str, dict[str, Any]], dict[str, dict[str, Any]]
]:
    mappings = _jsonl(reader.read(prepared["development_score_association"]["path"], prepared["development_score_association"]))
    cells = _jsonl(reader.read(prepared["development_score_cells"]["path"], prepared["development_score_cells"]))
    components = {
        row["component_id"]: row
        for row in _jsonl(reader.read(prepared["condition_components"]["path"], prepared["condition_components"]))
    }
    units = {
        row["operation_unit_id"]: row
        for row in _jsonl(reader.read(prepared["execution_units"]["path"], prepared["execution_units"]))
    }
    source = config["source_r3"]
    if len(mappings) != source["expected_result_rows"] or len(units) != source["expected_unique_execution_units"]:
        raise RuntimeError("R3 mapping or execution-unit count mismatch")
    pairs = {(row["building_id"], row["method_id"]) for row in mappings}
    roster = source_contract.read_csv(_safe_repo_path(config["result"]["development_roster_path"]))
    expected_pairs = {(row["stable_id"], method) for row in roster for method in config["result"]["conditions"]}
    if pairs != expected_pairs:
        raise RuntimeError("R3 exact 51x2 mapping membership drift")
    if len(cells) != source_contract.load_config()["scope"]["development_score_cell_rows"]:
        raise RuntimeError("R3 development score-cell count mismatch")
    associated = [row for row in mappings if row.get("operation_unit_id")]
    unassociated = [row for row in mappings if not row.get("operation_unit_id")]
    expected_unassociated = {(row["building_id"], row["method_id"], row["reference_cell_count"]) for row in source["expected_unassociated"]}
    observed_unassociated = {
        (row["building_id"], row["method_id"], sum(cell["stable_id"] == row["building_id"] for cell in cells))
        for row in unassociated
    }
    if len(associated) != source["expected_mapped_rows"] or observed_unassociated != expected_unassociated:
        raise RuntimeError("R3 mapped/unassociated row contract mismatch")
    if {row["operation_unit_id"] for row in associated} != set(units):
        raise RuntimeError("R3 associated operation-unit membership mismatch")
    if any(
        unit.get("reference_or_bbox_used_to_derive_input") is not False
        or unit.get("stable_id_used_to_derive_input") is not False
        or unit.get("condition_id") not in config["result"]["conditions"]
        or unit.get("component_id") not in components
        or components[unit["component_id"]].get("condition_id") != unit.get("condition_id")
        for unit in units.values()
    ):
        raise RuntimeError("R3 execution unit violates frozen no-reference/no-stable-ID condition lineage")
    if any(
        row.get("split") != "development"
        or row.get("association_role") != "SCORE_IDENTITY_ONLY_AFTER_FROZEN_CONDITION_GEOMETRY"
        for row in mappings
    ):
        raise RuntimeError("R3 mapping violates development-only score-after-freeze isolation")
    for row in associated:
        unit = units[row["operation_unit_id"]]
        if (
            row.get("method_id") != unit.get("condition_id")
            or row.get("component_id") != unit.get("component_id")
            or components[row["component_id"]].get("condition_id") != row.get("method_id")
        ):
            raise RuntimeError("R3 mapping method/component/execution-unit lineage mismatch")
    if any(row.get("component_id") is not None for row in unassociated):
        raise RuntimeError("R3 unassociated mapping unexpectedly carries a condition component")
    return mappings, cells, components, units


def _csv_bytes(fieldnames: Sequence[str], rows: Sequence[Mapping[str, Any]]) -> bytes:
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=fieldnames, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue().encode("utf-8")


def finalize_recovery(
    destination: AddOnceStore,
    *,
    source_root: Path,
    source_closed_receipt_path: Path,
    accepted_receipt_path: Path,
    source_commit: str,
    accepted_commit: str,
    project_image_id: str,
    run_id: str,
    handoff_id: str,
    artifact_root_token: str,
) -> dict[str, Any]:
    completed = destination.path("control/finalized_v1.json")
    if completed.is_file():
        return {**json.loads(completed.read_bytes()), "fast_path": True, "source_r3_reopens": 0, "new_writes": 0}
    started = destination.path("control/finalize_started_v1.json")
    if started.exists() or any(path.is_file() for path in destination.root.rglob("*")):
        raise RuntimeError("partial R4 finalize is terminal; retry is prohibited")
    config = load_config()
    validate_recovery_contract(config)
    if source_root.resolve() == destination.root or destination.root.is_relative_to(source_root.resolve()) or source_root.resolve().is_relative_to(destination.root):
        raise RuntimeError("sealed R3 source and R4 destination must be disjoint")
    if (
        artifact_root_token != "artifact://JointBuildGS" or handoff_id != HANDOFF_ID
        or not re.fullmatch(r"[0-9a-f]{40}", source_commit)
        or run_id != config["run_id"] or project_image_id != config["project_image_id"]
        or config["execution_mode"] != EXECUTION_MODE
    ):
        raise RuntimeError("R4 invocation identity mismatch")
    closed, accepted, receipt_records = _validate_receipts(
        config, source_closed_receipt_path, accepted_receipt_path, handoff_id,
        source_commit, accepted_commit, project_image_id, run_id,
    )
    authority = {
        "task_id": TASK_ID,
        "handoff_id": handoff_id,
        "source_commit": source_commit,
        "accepted_commit": accepted_commit,
        "project_image_id": project_image_id,
        "artifact_root_token": artifact_root_token,
        "finalization_run_id": run_id,
        "execution_mode": config["execution_mode"],
        **receipt_records,
    }
    finalization_operation_id = sha256_bytes(canonical_json_bytes(authority))
    destination.add_json("control/finalize_started_v1.json", {
        "status": "STARTED_ADD_ONCE_NO_RETRY",
        "authority": authority,
        "finalization_operation_id": finalization_operation_id,
        "source_r3_closed_commit": config["source_r3"]["closed_commit"],
        "source_r3_namespace": config["source_r3"]["external_namespace"],
        "original_scientific_source_mounts": 0,
        "roofer_invocations": 0,
        "scientific_verdict": None,
    })

    accepted_source_manifest = _accepted_source_manifest(accepted, config)
    reader = SourceManifestReader(source_root, config, accepted_source_manifest)
    source = config["source_r3"]
    prepared = reader.read_json(source["prepared_path"])
    if (
        prepared.get("status") != "PREPARED" or prepared.get("source_commit") != source["source_commit"]
        or prepared.get("run_id") != source["run_id"] or prepared.get("operation_id") != source["operation_id"]
        or prepared.get("result_rows") != source["expected_result_rows"]
        or prepared.get("unique_execution_units") != source["expected_unique_execution_units"]
        or prepared.get("duplicate_roofer_calculations_prevented") != source["expected_duplicate_operations_prevented"]
        or prepared.get("validation_payload_accesses") != 0 or prepared.get("held_out_payload_accesses") != 0
        or prepared.get("raw_dim_dense_accesses") != 0 or prepared.get("scientific_verdict") is not None
        or prepared.get("execution_authority", {}).get("accepted_commit") != source["accepted_commit"]
    ):
        raise RuntimeError("sealed R3 prepared ledger contract mismatch")
    smoke = reader.read_json(source["synthetic_smoke_path"])
    if smoke.get("status") != "PASS" or not smoke.get("G0_generated") or not smoke.get("G1_schema_semantic") or smoke.get("scientific_verdict") is not None:
        raise RuntimeError("sealed R3 synthetic PASS ledger mismatch")
    if (source_root / source["finalized_path"]).exists():
        raise RuntimeError("sealed R3 unexpectedly contains a finalized ledger")
    checkpoint = reader.read_json("checkpoints/120-condition_components_and_r_derived_frozen.json")
    if checkpoint.get("stage") != "condition_components_and_all_r_derived_frozen" or checkpoint.get("reference_score_cells_opened_before_checkpoint") is not False:
        raise RuntimeError("R3 pre-reference condition freeze checkpoint mismatch")
    cases = reader.read_json(source["preselected_cases_path"])
    if cases.get("chosen_before_score_outcomes") is not True:
        raise RuntimeError("R3 representative cases were not frozen before score outcomes")
    mappings, cells, components, units = _source_rows(reader, prepared, config)

    operation_results: dict[str, dict[str, Any]] = {}
    triangles: dict[str, list[np.ndarray]] = {}
    roofer_points: dict[str, int] = {}
    for unit_id, unit in sorted(units.items()):
        final_relative = f"operation_records/{source_contract._unit_slug(unit_id)}/final_v1.json"
        final = reader.read_json(final_relative)
        if (
            final.get("operation_unit_id") != unit_id or final.get("condition_id") != unit.get("condition_id")
            or final.get("component_id") != unit.get("component_id") or final.get("status") != "COMPLETE"
            or final.get("attempt_count") != 1 or final.get("retry_count") != 0
            or final.get("G0_generated") is not True or final.get("G1_schema_semantic") is not True
            or final.get("scientific_verdict") is not None
        ):
            raise RuntimeError(f"sealed R3 terminal operation ledger mismatch: {unit_id}")
        output_records = final.get("output_records")
        if not isinstance(output_records, list):
            raise RuntimeError("sealed R3 output record list is invalid")
        sequences = [
            record for record in output_records
            if isinstance(record, Mapping) and str(record.get("path", "")).endswith(".jsonl")
        ]
        if len(sequences) != 1:
            raise RuntimeError(f"sealed R3 operation must bind one native CityJSONSeq: {unit_id}")
        sequence = sequences[0]
        output_prefix = f"{unit['output_directory'].rstrip('/')}/"
        if not str(sequence["path"]).startswith(output_prefix):
            raise RuntimeError("CityJSONSeq record escapes its frozen operation output")
        data = reader.read(str(sequence["path"]), sequence)
        triangles[unit_id] = roof_triangles_from_cityjsonseq(str(sequence["path"]), data)
        roofer_points[unit_id] = _point_count_from_record(unit["input"])
        operation_results[unit_id] = final

    if len(reader.records) != int(config["source_manifest_allowlist"]["expected_files_read"]):
        raise RuntimeError("R4 did not consume exactly the accepted derived-source manifest")

    reuse_manifest = {
        "schema": "jointbuildgs.p2_c1_c2_r4_source_reuse.v1",
        "status": "REUSED_EXACT_FROM_CLOSED_R3",
        "source_r3": {
            **{key: source[key] for key in (
                "task_id", "handoff_id", "source_commit", "activation_commit", "offered_commit", "accepted_commit",
                "return_commit", "blocked_commit", "closed_commit", "run_id", "operation_id",
                "external_namespace", "config_git_blob",
                "return_git_blob", "closed_receipt_git_blob",
            )},
            "operation_id": prepared["operation_id"],
        },
        "source_records": reader.records,
        "accepted_source_manifest": [
            accepted_source_manifest[path] for path in sorted(accepted_source_manifest)
        ],
        "source_files_full_read_and_digest_passes": len(reader.records),
        "source_bytes_read_and_digested": reader.total_bytes,
        "source_operation_las_reads_or_hashes": 0,
        "original_scientific_source_reads_or_hashes": 0,
        "roofer_invocations": 0,
        "source_r3_writes": 0,
        "scientific_verdict": None,
    }
    reuse_record = destination.add_json("control/source_reuse_manifest_v1.json", reuse_manifest)

    by_building: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    for cell in cells:
        by_building[cell["stable_id"]].append(cell)
    source_config = source_contract.load_config()
    rows: list[dict[str, Any]] = []
    for mapping in mappings:
        unit_id = mapping.get("operation_unit_id")
        operation = operation_results.get(unit_id) if unit_id else None
        method = mapping["method_id"]
        component = components.get(mapping.get("component_id"))
        metrics = source_contract.score_continuous(by_building[mapping["building_id"]], triangles.get(unit_id, []))
        rows.append({
            "building_id": mapping["building_id"], "group_id": mapping["group_id"], "split": "development",
            "method_id": method, "run_id": prepared["run_id"], "operation_id": prepared["operation_id"],
            "criterion_version": source_config["result"]["criterion_version"],
            "reference_provenance": source_config["result"]["c1_reference_provenance"] if method == "C1_L_upper" else source_config["result"]["c2_reference_provenance"],
            "component_id": mapping.get("component_id"), "operation_unit_id": unit_id,
            "G0_generated": bool(operation and operation["G0_generated"]),
            "G1_schema_semantic": operation["G1_schema_semantic"] if operation else None,
            "G1_check_class": "INTERNAL_CITYJSON_BOUNDARY_SEMANTICS_PARENT_CHILD_VALIDATION",
            "G1_failure_reasons": operation["G1_failure_reasons"] if operation else ["NO_EXECUTED_CITYJSON_OUTPUT"],
            "geometry_ring_diagnostic": operation["geometry_ring_diagnostic"] if operation else None,
            "geometry_ring_diagnostic_class": "DIAGNOSTIC_RING_INDEX_SANITY_NOT_G2_NOT_VAL3DITY",
            "G2_geometry_topology_valid": None, "G2_null_reason": "CANONICAL_VALIDATOR_UNAVAILABLE",
            "G3_roof_structure_acceptable": None, "G4_geometric_accuracy_acceptable": None, "PASS_usable": None,
            "threshold_null_reason": "THRESHOLD_NOT_FROZEN",
            "attempt_count": operation["attempt_count"] if operation else 0,
            "retry_count": operation["retry_count"] if operation else 0,
            "runtime_seconds": operation["runtime_seconds"] if operation else None,
            "peak_memory_bytes": operation["peak_memory_bytes"] if operation else None,
            "peak_memory_unavailable_reason": operation["peak_memory_unavailable_reason"] if operation else "NO_ROOFER_EXECUTION",
            "input_point_count": component["point_count"] if component else None,
            "roofer_input_point_count": roofer_points.get(unit_id),
            "output_bytes": operation["output_bytes"] if operation else 0,
            "failure_reasons": operation["failure_reasons"] if operation else [mapping.get("pre_roofer_failure") or "UNASSOCIATED_CONDITION_COMPONENT"],
            "metrics": metrics, "scientific_verdict": None,
        })
    if len(rows) != 102 or len({(row["building_id"], row["method_id"]) for row in rows}) != 102:
        raise RuntimeError("R4 recovered result matrix is not exact 51x2")
    schema_validation = source_contract.validate_result_rows(rows, source_config)
    metrics_record = destination.add("results/building_method_metrics_v1.jsonl", source_contract.jsonl_bytes(rows))
    metric_names = (
        "reference_vertical_coverage", "height_error_mae_m", "RMSZ_m", "RMSXY_m",
        "surface_distance_rmse_m", "surface_distance_p95_m", "normal_angular_error_median_deg",
    )
    summaries = [
        {"method_id": method, **source_contract.group_balanced_summary([row for row in rows if row["method_id"] == method], name)}
        for method in source_contract.CONDITIONS for name in metric_names
    ]
    summary_record = destination.add("results/group_balanced_descriptive_v1.jsonl", source_contract.jsonl_bytes(summaries))
    technical_groups = source_contract.condition_group_technical_summary(rows, source_config["scope"]["group_sizes"])
    technical_record = destination.add("results/condition_group_technical_summary_v1.jsonl", source_contract.jsonl_bytes(technical_groups))
    input_definition_record = destination.add(
        "results/development_input_definition_v1.csv",
        source_contract.canonical_lf_bytes(_safe_repo_path(config["result"]["development_score_scope_path"])),
    )
    selected = cases["cases"]
    case_rows = [row for row in rows if selected.get(row["group_id"]) == row["building_id"]]
    case_record = destination.add("results/preselected_case_index_v1.jsonl", source_contract.jsonl_bytes(case_rows))
    method_summary = {
        method: {
            "denominator": 51,
            "G0_generated": sum(row["G0_generated"] for row in rows if row["method_id"] == method),
            "G1_provisional_true": sum(row["G1_schema_semantic"] is True for row in rows if row["method_id"] == method),
            "G2_canonical_available": 0,
            "G3_G4_PASS_available": 0,
            "self_reference": method == "C1_L_upper",
        }
        for method in source_contract.CONDITIONS
    }
    panel_lines: list[str] = []
    for method in source_contract.CONDITIONS:
        panel_lines.extend([
            f"## {method} technical panel",
            "",
            "| group | denominator | attempted | G0 | G1 | failed G0 | runtime sum (s) | failure reasons |",
            "|---|---:|---:|---:|---:|---:|---:|---|",
        ])
        for item in technical_groups:
            if item["method_id"] == method:
                panel_lines.append(
                    f"| {item['group_id']} | {item['denominator']} | {item['attempted']} | "
                    f"{item['G0_generated']} | {item['G1_true']} | {item['failed_G0']} | "
                    f"{item['runtime_seconds_sum']} | "
                    f"`{json.dumps(item['failure_reason_counts'], sort_keys=True, separators=(',', ':'))}` |"
                )
        panel_lines.append("")
    report = f"""# C1/C2 development feasibility finalize-only recovery report

- Result rows: 102 (exact sealed R3 51-building x 2-condition surface)
- Source reconstruction run: `{prepared['run_id']}`
- Source reconstruction operation: `{prepared['operation_id']}`
- R4 finalization run: `{run_id}`
- R4 finalization operation: `{finalization_operation_id}`
- R4 Roofer invocations: 0
- Original scientific source rereads: 0
- Sealed R3 operation LAS rereads: 0 (point counts derived from bound LAS1.2/PF3 byte records)
- Unique reused R3 operations: 7
- C1 G0/G1: {method_summary['C1_L_upper']['G0_generated']}/{method_summary['C1_L_upper']['G1_provisional_true']} of 51
- C2 G0/G1: {method_summary['C2_MVS']['G0_generated']}/{method_summary['C2_MVS']['G1_provisional_true']} of 51
- C1 remains a self-reference upper baseline and cannot be pooled as independent-reference accuracy.
- Validation/held-out/C3-C5/LoD1/LoD2/Fusion/R_ext access: 0
- Canonical G2, G3, G4 and PASS_usable: null
- Qualitative fixed-view evidence: NOT_RENDERED
- Qualitative null reason: {source_config['result']['qualitative_fixed_view_null_reason']}
- scientific_verdict: null

{chr(10).join(panel_lines)}
"""
    report_record = destination.add("results/C1_C2_DEVELOPMENT_REPORT_v1.md", report.encode("utf-8"))
    body = {
        "schema": "jointbuildgs.p2_c1_c2_finalize_recovery_r4.v1",
        "status": "TECHNICAL_RESULTS_COMPLETE_FOR_WORK_HOST_REVIEW",
        "task_id": TASK_ID,
        "finalization_run_id": run_id,
        "finalization_operation_id": finalization_operation_id,
        "source_run_id": prepared["run_id"],
        "source_operation_id": prepared["operation_id"],
        "result_rows": 102,
        "unique_reused_execution_units": 7,
        "duplicate_roofer_calculations_prevented": prepared["duplicate_roofer_calculations_prevented"],
        "method_summary": method_summary,
        "metrics": metrics_record,
        "group_balanced_descriptive": summary_record,
        "condition_group_technical_summary": technical_record,
        "development_input_definition": input_definition_record,
        "preselected_cases": case_record,
        "report": report_record,
        "source_reuse_manifest": reuse_record,
        "result_schema_validation": schema_validation,
        "execution_authority": authority,
        "source_r3_lineage": reuse_manifest["source_r3"],
        "source_input_records": prepared["input_records"],
        "qualitative_fixed_view": {
            "status": "NOT_RENDERED",
            "reason": source_config["result"]["qualitative_fixed_view_null_reason"],
        },
        "output_records": {
            "metrics": metrics_record, "group_balanced_descriptive": summary_record,
            "condition_group_technical_summary": technical_record,
            "development_input_definition": input_definition_record,
            "preselected_cases": case_record, "report": report_record,
            "source_reuse_manifest": reuse_record,
        },
        "r4_roofer_invocations": 0,
        "original_scientific_source_reads_or_hashes": 0,
        "source_operation_las_reads_or_hashes": 0,
        "source_r3_writes": 0,
        "canonical_G2": None, "G3": None, "G4": None, "PASS_usable": None,
        "scientific_verdict": None,
    }
    destination.add_json("control/finalized_v1.json", body)
    return body


def promote_recovery(store: AddOnceStore, repo_root: Path, promotion_parent_commit: str) -> dict[str, Any]:
    config = load_config()
    repo_root = repo_root.resolve()
    git_store = AddOnceStore(repo_root)
    manifest_relative = config["result"]["manifest_path"]
    existing = git_store.path(manifest_relative)
    if existing.is_file():
        manifest = json.loads(existing.read_bytes())
        for record in manifest["promoted_records"]:
            git_store.read_verified(record)
        return {**manifest, "fast_path": True, "source_r3_reopens": 0, "new_writes": 0}
    if not re.fullmatch(r"[0-9a-f]{40}", promotion_parent_commit):
        raise RuntimeError("promotion parent commit must be an exact full SHA")
    finalized = json.loads(store.path("control/finalized_v1.json").read_bytes())
    if finalized.get("status") != "TECHNICAL_RESULTS_COMPLETE_FOR_WORK_HOST_REVIEW" or finalized.get("scientific_verdict") is not None:
        raise RuntimeError("R4 finalized ledger is not promotable")
    actual_head = subprocess.run(["git", "-C", str(repo_root), "rev-parse", "HEAD"], check=True, capture_output=True, text=True).stdout.strip()
    dirty = subprocess.run(["git", "-C", str(repo_root), "status", "--porcelain=v1", "--untracked-files=all"], check=True, capture_output=True, text=True).stdout
    if actual_head != promotion_parent_commit or finalized["execution_authority"]["accepted_commit"] != actual_head or dirty:
        raise RuntimeError("promotion requires the exact clean R4 accepted commit")
    rows = _jsonl(store.read_verified(finalized["metrics"]))
    summaries = _jsonl(store.read_verified(finalized["group_balanced_descriptive"]))
    technical = _jsonl(store.read_verified(finalized["condition_group_technical_summary"]))
    cases = _jsonl(store.read_verified(finalized["preselected_cases"]))
    input_definition = store.read_verified(finalized["development_input_definition"])
    report = store.read_verified(finalized["report"])
    metric_fields = [
        "building_id", "group_id", "split", "method_id", "run_id", "operation_id",
        "criterion_version", "reference_provenance", "component_id", "operation_unit_id",
        "G0_generated", "G1_schema_semantic", "G1_check_class", "G1_failure_reasons",
        "geometry_ring_diagnostic", "geometry_ring_diagnostic_class",
        "G2_geometry_topology_valid", "G2_null_reason", "G3_roof_structure_acceptable",
        "G4_geometric_accuracy_acceptable", "PASS_usable", "threshold_null_reason",
        "attempt_count", "retry_count", "runtime_seconds", "peak_memory_bytes",
        "peak_memory_unavailable_reason", "input_point_count", "roofer_input_point_count",
        "output_bytes", "reference_cell_count", "vertically_scored_cell_count",
        "reference_vertical_coverage", "height_error_signed_mean_m",
        "height_error_signed_median_m", "height_error_mae_m", "RMSZ_m", "RMSXY_m",
        "surface_distance_rmse_m", "surface_distance_p95_m",
        "normal_angular_error_median_deg", "normal_angular_error_p95_deg", "failure_reasons",
    ]
    flat_rows = []
    for row in rows:
        flat = {name: row.get(name) for name in metric_fields}
        for name, value in row["metrics"].items():
            if name in flat:
                flat[name] = value
        flat["failure_reasons"] = ";".join(row["failure_reasons"])
        flat["G1_failure_reasons"] = ";".join(row["G1_failure_reasons"])
        flat_rows.append(flat)
    summary_fields = ["method_id", "metric", "unweighted_group_mean", "groups_with_value", "all_five_groups_have_value", "inferential_statistics", "interpretation", "group_means_json", "groups_with_denominators_json"]
    flat_summaries = [{
        **{name: row.get(name) for name in summary_fields},
        "group_means_json": json.dumps(row["group_means"], sort_keys=True, separators=(",", ":")),
        "groups_with_denominators_json": json.dumps(row["groups"], sort_keys=True, separators=(",", ":")),
    } for row in summaries]
    technical_fields = ["method_id", "group_id", "denominator", "attempted", "G0_generated", "G1_true", "failed_G0", "runtime_seconds_sum", "runtime_seconds_median", "failure_reason_counts_json"]
    flat_technical = [{
        **{name: row.get(name) for name in technical_fields},
        "failure_reason_counts_json": json.dumps(row["failure_reason_counts"], sort_keys=True, separators=(",", ":")),
    } for row in technical]
    case_fields = ["building_id", "group_id", "method_id", "reference_provenance", "G0_generated", "G1_schema_semantic", "RMSZ_m", "RMSXY_m", "surface_distance_rmse_m", "reference_vertical_coverage", "operation_unit_id"]
    flat_cases = [{**{name: row.get(name) for name in case_fields}, **{name: row["metrics"].get(name) for name in case_fields if name in row["metrics"]}} for row in cases]
    prefix = config["result"]["promotion_prefix"]
    promoted = [
        git_store.add(f"{prefix}/C1_C2_DEVELOPMENT_REPORT_v1.md", report),
        git_store.add(f"{prefix}/building_method_metrics_v1.csv", _csv_bytes(metric_fields, flat_rows)),
        git_store.add(f"{prefix}/group_balanced_descriptive_v1.csv", _csv_bytes(summary_fields, flat_summaries)),
        git_store.add(f"{prefix}/condition_group_technical_summary_v1.csv", _csv_bytes(technical_fields, flat_technical)),
        git_store.add(f"{prefix}/development_input_definition_v1.csv", input_definition),
        git_store.add(f"{prefix}/preselected_case_metrics_v1.csv", _csv_bytes(case_fields, flat_cases)),
    ]
    manifest = {
        "schema": "jointbuildgs.p2_c1_c2_finalize_recovery_r4_manifest.v1",
        "task_id": TASK_ID,
        "promotion_parent_commit": promotion_parent_commit,
        "finalization_run_id": finalized["finalization_run_id"],
        "finalization_operation_id": finalized["finalization_operation_id"],
        "source_run_id": finalized["source_run_id"],
        "source_operation_id": finalized["source_operation_id"],
        "source_r3_lineage": finalized["source_r3_lineage"],
        "external_namespace": config["result"]["external_namespace"],
        "external_records": {
            "metrics": finalized["metrics"],
            "group_balanced_descriptive": finalized["group_balanced_descriptive"],
            "condition_group_technical_summary": finalized["condition_group_technical_summary"],
            "development_input_definition": finalized["development_input_definition"],
            "preselected_cases": finalized["preselected_cases"],
            "report": finalized["report"],
            "source_reuse_manifest": finalized["source_reuse_manifest"],
        },
        "execution_authority": finalized["execution_authority"],
        "result_schema_validation": finalized["result_schema_validation"],
        "promoted_records": promoted,
        "result_rows": 102,
        "unique_reused_execution_units": finalized["unique_reused_execution_units"],
        "duplicate_roofer_calculations_prevented": finalized["duplicate_roofer_calculations_prevented"],
        "method_summary": finalized["method_summary"],
        "qualitative_fixed_view": finalized["qualitative_fixed_view"],
        "validation_payload_accesses": 0,
        "held_out_payload_accesses": 0,
        "r4_roofer_invocations": 0,
        "original_scientific_source_reads_or_hashes": 0,
        "source_operation_las_reads_or_hashes": 0,
        "canonical_G2": None,
        "G3": None,
        "G4": None,
        "PASS_usable": None,
        "scientific_verdict": None,
    }
    git_store.add_json(manifest_relative, manifest)
    return manifest
