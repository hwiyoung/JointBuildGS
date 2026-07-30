#!/usr/bin/env python3
"""Human-authorized, exact-once global pose adoption for fusion W1.

This stage publishes a separate COLMAP sparse model.  It never modifies the
source sparse model, ALS, imagery, footprint, reference model, or fixed zeta.
It launches no learning, readout, Roofer, or scoring command.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import itertools
import json
import math
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, Mapping, Sequence

import numpy as np


REPO = Path(__file__).resolve().parents[4]
DEFAULT_CONFIG = (
    REPO
    / "phases/p2-gsjso/configs/fusion_w1/fusion_w1_pose_adoption_v2_20260725.json"
)


class PoseAdoptionError(RuntimeError):
    """Fail-closed R1 contract or validation error."""


class ClaimConflictError(PoseAdoptionError):
    """Another process already owns the exact-once R1 namespace."""


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def repo_path(value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else REPO / path


def relative(path: str | Path) -> str:
    resolved = Path(path).resolve()
    try:
        return str(resolved.relative_to(REPO.resolve()))
    except ValueError:
        return str(resolved)


def sha256_file(path: str | Path, chunk_size: int = 8 * 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        while block := handle.read(chunk_size):
            digest.update(block)
    return digest.hexdigest()


def canonical_json_sha(payload: Any) -> str:
    encoded = json.dumps(
        json_safe(payload), sort_keys=True, separators=(",", ":")
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def json_safe(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(item) for item in value]
    if isinstance(value, np.ndarray):
        return json_safe(value.tolist())
    if isinstance(value, (np.floating, float)):
        number = float(value)
        return number if math.isfinite(number) else None
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.bool_):
        return bool(value)
    return value


def load_json(path: str | Path) -> dict[str, Any]:
    target = repo_path(path)
    payload = json.loads(target.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise PoseAdoptionError(f"JSON root is not an object: {relative(target)}")
    return payload


def atomic_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
    ) as handle:
        temporary = Path(handle.name)
        handle.write(text)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def atomic_json(path: Path, payload: Mapping[str, Any]) -> None:
    atomic_text(
        path,
        json.dumps(
            json_safe(payload),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
            allow_nan=False,
        )
        + "\n",
    )


def exclusive_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            descriptor = -1
            handle.write(
                json.dumps(
                    json_safe(payload),
                    ensure_ascii=False,
                    indent=2,
                    sort_keys=True,
                    allow_nan=False,
                )
                + "\n"
            )
            handle.flush()
            os.fsync(handle.fileno())
    finally:
        if descriptor >= 0:
            os.close(descriptor)


class EventJournal:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self.handle = path.open("x", encoding="utf-8")

    def write(self, event: str, **fields: Any) -> None:
        row = {"at": now_utc(), "event": event, **fields}
        self.handle.write(
            json.dumps(json_safe(row), ensure_ascii=False, sort_keys=True)
            + "\n"
        )
        self.handle.flush()
        os.fsync(self.handle.fileno())

    def close(self) -> None:
        if not self.handle.closed:
            self.handle.close()


def run_git(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        [
            "git",
            "-c",
            f"safe.directory={REPO}",
            "-C",
            str(REPO),
            *args,
        ],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if check and result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip()
        raise PoseAdoptionError(f"git {' '.join(args)} failed: {detail}")
    return result


def import_locked_module(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise PoseAdoptionError(f"cannot import locked module: {relative(path)}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def verify_config(config: Mapping[str, Any], config_path: Path) -> None:
    if config_path.resolve() != DEFAULT_CONFIG.resolve():
        raise PoseAdoptionError("alternate R1 config paths are forbidden")
    if (
        config.get("schema")
        != "jointbuildgs.fusion_w1.pose_adoption_v2.config.v1"
    ):
        raise PoseAdoptionError("unexpected R1 config schema")
    if config.get("branch") != "exp/fusion-w1":
        raise PoseAdoptionError("R1 branch lock drift")
    if not Path("/.dockerenv").exists():
        raise PoseAdoptionError("R1 must execute in the pinned Docker image")
    contract = config["transform_contract"]
    if float(contract["scale"]) != 1.0:
        raise PoseAdoptionError("scale must remain exactly one")
    if float(contract["orthometric_to_ellipsoidal_zeta_m"]) != 45.7:
        raise PoseAdoptionError("fixed zeta must remain exactly 45.7 m")
    if contract["zeta_applied_during_pose_publication"] is not False:
        raise PoseAdoptionError("pose publication must not apply zeta")
    if contract["block_transforms_required_empty"] is not True:
        raise PoseAdoptionError("block transforms must remain forbidden")
    if config["issues_contract"]["append_only_on_success"] is not True:
        raise PoseAdoptionError("issues append-on-success contract is not locked")


def verify_repo_gate(config: Mapping[str, Any]) -> dict[str, Any]:
    branch = run_git("branch", "--show-current").stdout.strip()
    head = run_git("rev-parse", "HEAD").stdout.strip()
    ancestor = run_git(
        "merge-base",
        "--is-ancestor",
        str(config["required_ancestor_commit"]),
        head,
        check=False,
    )
    if branch != config["branch"]:
        raise PoseAdoptionError(f"branch {branch!r} != {config['branch']!r}")
    if ancestor.returncode != 0:
        raise PoseAdoptionError("committed R0 implementation/result is not an ancestor")
    porcelain = run_git(
        "status", "--porcelain=v1", "--untracked-files=all"
    ).stdout.strip()
    if porcelain:
        raise PoseAdoptionError("worktree must be clean before exact-once R1 claim")
    implementation_hashes: dict[str, str] = {}
    for logical in config["implementation_files"]:
        path = repo_path(logical)
        if not path.is_file():
            raise PoseAdoptionError(f"implementation file missing: {logical}")
        tracked = run_git("ls-files", "--error-unmatch", logical, check=False)
        if tracked.returncode != 0:
            raise PoseAdoptionError(f"implementation file is untracked: {logical}")
        blob = subprocess.run(
            [
                "git",
                "-c",
                f"safe.directory={REPO}",
                "-C",
                str(REPO),
                "show",
                f"HEAD:{logical}",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        if blob.returncode != 0 or blob.stdout != path.read_bytes():
            raise PoseAdoptionError(f"implementation differs from HEAD: {logical}")
        implementation_hashes[logical] = sha256_file(path)
    return {
        "branch": branch,
        "head": head,
        "required_ancestor_commit": config["required_ancestor_commit"],
        "required_ancestor_of_head": True,
        "implementation_sha256": implementation_hashes,
    }


def verify_r0_gate(config: Mapping[str, Any]) -> dict[str, Any]:
    gate = config["r0_gate"]
    path = repo_path(gate["path"])
    observed_hash = sha256_file(path)
    if observed_hash != gate["sha256"]:
        raise PoseAdoptionError("R0 PASS receipt hash drift")
    receipt = load_json(path)
    if receipt.get("schema") != gate["schema"]:
        raise PoseAdoptionError("R0 receipt schema drift")
    if receipt.get("status") != gate["status"]:
        raise PoseAdoptionError("R0 did not pass")
    if receipt.get("execution_counters") != gate["required_counters"]:
        raise PoseAdoptionError("R0 zero-counter receipt drift")
    continuation = receipt.get("continuation", {})
    for key, expected in gate["required_continuation"].items():
        if continuation.get(key) != expected:
            raise PoseAdoptionError(f"R0 continuation gate drift: {key}")
    return {
        "path": gate["path"],
        "sha256": observed_hash,
        "schema": receipt["schema"],
        "status": receipt["status"],
        "execution_counters": receipt["execution_counters"],
        "continuation": continuation,
    }


def verify_input_hashes(config: Mapping[str, Any]) -> dict[str, str]:
    observed: dict[str, str] = {}
    for logical, expected in config["input_sha256"].items():
        path = repo_path(logical)
        if not path.is_file():
            raise PoseAdoptionError(f"locked input missing: {logical}")
        actual = sha256_file(path)
        if actual != expected:
            raise PoseAdoptionError(
                f"locked input hash mismatch: {logical}: {actual} != {expected}"
            )
        observed[logical] = actual
    return observed


def sha256sum_stream_aggregate(
    logical_root: Path,
) -> tuple[str, int, int]:
    if not logical_root.is_dir():
        raise PoseAdoptionError(
            f"immutable image directory missing: {relative(logical_root)}"
        )
    files = sorted(
        (path for path in logical_root.iterdir() if path.is_file()),
        key=lambda path: path.as_posix().encode("utf-8"),
    )
    aggregate = hashlib.sha256()
    total_bytes = 0
    for path in files:
        digest = sha256_file(path)
        total_bytes += path.stat().st_size
        logical = path.relative_to(REPO).as_posix()
        aggregate.update(f"{digest}  {logical}\n".encode("utf-8"))
    return aggregate.hexdigest(), len(files), total_bytes


def snapshot_immutable_inputs(config: Mapping[str, Any]) -> dict[str, Any]:
    contract = config["immutable_inputs"]
    rows: list[dict[str, Any]] = []
    for spec in contract["files"]:
        path = repo_path(spec["path"])
        if not path.is_file():
            raise PoseAdoptionError(f"immutable input missing: {spec['path']}")
        observed_bytes = path.stat().st_size
        observed_sha = sha256_file(path)
        if (
            observed_bytes != int(spec["bytes"])
            or observed_sha != spec["sha256"]
        ):
            raise PoseAdoptionError(
                f"immutable input lock mismatch: {spec['path']}"
            )
        rows.append(
            {
                "role": spec["role"],
                "path": spec["path"],
                "bytes": observed_bytes,
                "sha256": observed_sha,
            }
        )

    image_contract = contract["training_image_set"]
    aggregate, count, total_bytes = sha256sum_stream_aggregate(
        repo_path(image_contract["path"])
    )
    if (
        aggregate != image_contract["sha256sum_stream_aggregate"]
        or count != int(image_contract["file_count"])
        or total_bytes != int(image_contract["total_bytes"])
    ):
        raise PoseAdoptionError("immutable 937-image pixel inventory mismatch")
    return {
        "files": rows,
        "training_image_set": {
            "path": image_contract["path"],
            "file_count": count,
            "total_bytes": total_bytes,
            "sha256sum_stream_aggregate": aggregate,
            "algorithm": image_contract["algorithm"],
        },
    }


def validate_coordinate_datum_payload(
    config: Mapping[str, Any], payload: Mapping[str, Any]
) -> dict[str, Any]:
    contract = config["coordinate_datum_contract"]
    required = {
        "geo_crs": contract["geo_crs"],
        "input_vertical_datum_default": contract[
            "input_vertical_datum_default"
        ],
        "orthometric_geoid_m": contract["orthometric_geoid_m"],
    }
    for key, expected in required.items():
        if payload.get(key) != expected:
            raise PoseAdoptionError(f"coordinate/datum semantic drift: {key}")
    if float(contract["scale"]) != 1.0:
        raise PoseAdoptionError("coordinate scale must remain exactly one")
    if int(contract["zeta_application_count_during_r1"]) != 0:
        raise PoseAdoptionError("R1 zeta application count must remain zero")
    return {
        "path": contract["path"],
        "sha256": sha256_file(repo_path(contract["path"])),
        "geo_crs": payload["geo_crs"],
        "input_vertical_datum_default": payload[
            "input_vertical_datum_default"
        ],
        "orthometric_geoid_m": float(payload["orthometric_geoid_m"]),
        "scale": float(contract["scale"]),
        "zeta_application_count_during_r1": 0,
    }


def verify_coordinate_datum(config: Mapping[str, Any]) -> dict[str, Any]:
    contract = config["coordinate_datum_contract"]
    path = repo_path(contract["path"])
    if sha256_file(path) != contract["sha256"]:
        raise PoseAdoptionError("projection datum config hash drift")
    return validate_coordinate_datum_payload(config, load_json(path))


def verify_arm_pose_configs(config: Mapping[str, Any]) -> dict[str, Any]:
    contract = config["arm_config_contract"]
    configs: dict[str, dict[str, Any]] = {}
    hashes: dict[str, str] = {}
    for arm_key, expected_arm in (("arm_A", "A"), ("arm_B", "B")):
        logical = contract[arm_key]
        payload = load_json(logical)
        if payload.get("schema") != contract["schema"]:
            raise PoseAdoptionError(f"{arm_key} pose-binding schema drift")
        if payload.get("arm") != expected_arm:
            raise PoseAdoptionError(f"{arm_key} label drift")
        configs[arm_key] = payload
        hashes[arm_key] = sha256_file(repo_path(logical))
    binding_a = configs["arm_A"].get("pose_binding")
    binding_b = configs["arm_B"].get("pose_binding")
    if binding_a != binding_b or not isinstance(binding_a, dict):
        raise PoseAdoptionError("arm A/B corrected-pose bindings differ")
    expected_binding = {
        "manifest": contract["required_manifest"],
        "manifest_schema": contract["required_manifest_schema"],
        "derived_sparse_json_pointer": contract[
            "required_derived_sparse_pointer"
        ],
        "images_sha256_json_pointer": contract[
            "required_images_sha256_pointer"
        ],
        "required_transform_application_count": int(
            contract["required_transform_application_count"]
        ),
        "source_sparse_pose_consumption_forbidden": bool(
            contract["source_sparse_pose_consumption_forbidden"]
        ),
        "cache_key_must_include_images_sha256": True,
    }
    if binding_a != expected_binding:
        raise PoseAdoptionError("arm corrected-pose binding contract drift")
    if binding_a["manifest"] != config["outputs"]["manifest"]:
        raise PoseAdoptionError("arm configs do not bind this R1 manifest")
    for arm_key in ("arm_A", "arm_B"):
        terms = configs[arm_key].get("locked_training_terms", {})
        if int(terms.get("iterations", -1)) != 30000:
            raise PoseAdoptionError(f"{arm_key} iteration lock drift")
    terms_a = configs["arm_A"]["locked_training_terms"]
    terms_b = configs["arm_B"]["locked_training_terms"]
    if (
        terms_a["depth_supervision_enabled"] is not True
        or terms_a["normal_supervision_enabled"] is not True
        or float(terms_a["depth_weight_initial"]) != 0.5
        or float(terms_a["normal_weight_initial"]) != 0.05
        or terms_b["depth_supervision_enabled"] is not False
        or terms_b["normal_supervision_enabled"] is not False
        or float(terms_b["depth_weight_initial"]) != 0.0
        or float(terms_b["normal_weight_initial"]) != 0.0
    ):
        raise PoseAdoptionError("arm A/B supervision ablation lock drift")
    return {
        "config_paths": {
            "arm_A": contract["arm_A"],
            "arm_B": contract["arm_B"],
        },
        "config_sha256": hashes,
        "identical_pose_binding": True,
        "pose_binding": binding_a,
        "iterations": 30000,
        "arm_A_depth_normal_initial_weights": [0.5, 0.05],
        "arm_B_depth_normal_supervision_removed": True,
    }


def check_outputs_absent(config: Mapping[str, Any]) -> None:
    outputs = config["outputs"]
    for key in (
        "claim",
        "event_log",
        "failure",
        "diagnostic_reproduction",
        "manifest",
        "runtime_dir",
    ):
        path = repo_path(outputs[key])
        if path.exists() or path.is_symlink():
            if key == "claim":
                raise ClaimConflictError(
                    f"R1 exact-once claim already exists: {relative(path)}"
                )
            raise PoseAdoptionError(
                f"R1 is exact-once and output already exists: {key}={relative(path)}"
            )


def serialize_matrix(matrix: np.ndarray) -> list[list[float]]:
    return [[float(value) for value in row] for row in np.asarray(matrix)]


def extract_and_validate_candidate(
    config: Mapping[str, Any],
    coreg: Any,
    fit: Mapping[str, Any],
    global_selection: Mapping[str, Any],
    block_selection: Mapping[str, Any],
) -> tuple[np.ndarray, dict[str, Any]]:
    if fit.get("schema") != "jointbuildgs.fusion_w1.coreg_fit_candidate.v1":
        raise PoseAdoptionError("fit candidate schema drift")
    if fit.get("status") != "CANDIDATE_ESTIMATED":
        raise PoseAdoptionError("fit candidate is not estimated")
    if (
        global_selection.get("schema")
        != "jointbuildgs.fusion_w1.coreg_frozen_transform.v1"
        or global_selection.get("choice") != "none"
        or global_selection.get("status") != "BLOCK_REQUIRED"
    ):
        raise PoseAdoptionError("global selection consumer guard drift")
    if (
        block_selection.get("schema")
        != "jointbuildgs.fusion_w1.coreg_block_selection.v1"
        or block_selection.get("choice") != "none"
        or block_selection.get("status") != "BLOCKED"
        or block_selection.get("block_transforms") != {}
    ):
        raise PoseAdoptionError("block selection consumer guard drift")

    fit_matrix = np.asarray(
        fit["candidate_photo_to_als_global_pivot_matrix"], dtype=np.float64
    )
    global_matrix = np.asarray(
        global_selection["block_base_photo_to_als_global_pivot_matrix"],
        dtype=np.float64,
    )
    block_matrix = np.asarray(
        block_selection["selected_photo_to_als_global_pivot_matrix"],
        dtype=np.float64,
    )
    if not (
        np.array_equal(fit_matrix, global_matrix)
        and np.array_equal(fit_matrix, block_matrix)
    ):
        raise PoseAdoptionError("fit/global/block candidate matrices differ")
    coreg.validate_rigid_transform(
        fit_matrix, tolerance=float(config["validation"]["rigid_tolerance"])
    )
    serialized = serialize_matrix(fit_matrix)
    matrix_hash = canonical_json_sha(serialized)
    bundle_hash = canonical_json_sha({"global": serialized, "blocks": {}})
    contract = config["transform_contract"]
    if matrix_hash != contract["matrix_sha256"]:
        raise PoseAdoptionError("candidate matrix hash differs from adoption contract")
    if bundle_hash != contract["bundle_sha256"]:
        raise PoseAdoptionError("candidate bundle hash differs from adoption contract")
    if fit.get("candidate_transform_sha256") != matrix_hash:
        raise PoseAdoptionError("fit candidate matrix receipt mismatch")
    if global_selection.get("block_base_transform_sha256") != matrix_hash:
        raise PoseAdoptionError("global block-base matrix receipt mismatch")
    if block_selection.get("selected_transform_sha256") != bundle_hash:
        raise PoseAdoptionError("block selection bundle receipt mismatch")

    diagnostics = fit.get("diagnostics", {})
    if diagnostics.get("candidate_valid") is not True:
        raise PoseAdoptionError("fit candidate is invalid")
    if int(diagnostics.get("final_rank", -1)) != int(
        contract["expected_final_rank"]
    ):
        raise PoseAdoptionError("fit rank cross-check failed")
    if int(diagnostics.get("final_correspondences", -1)) != int(
        contract["expected_final_correspondences"]
    ):
        raise PoseAdoptionError("fit correspondence cross-check failed")
    rotation = float(diagnostics["rotation_deg"])
    if abs(rotation - float(contract["expected_rotation_deg"])) > float(
        config["validation"]["candidate_rotation_tolerance_deg"]
    ):
        raise PoseAdoptionError("fit rotation cross-check failed")
    translation = fit_matrix[:3, 3]
    expected_translation = np.asarray(
        contract["expected_translation_components_m"], dtype=np.float64
    )
    if float(np.max(np.abs(translation - expected_translation))) > float(
        config["validation"]["candidate_translation_tolerance_m"]
    ):
        raise PoseAdoptionError("fit translation cross-check failed")
    return fit_matrix, {
        "source": config["inputs"]["fit_candidate"],
        "source_key": contract["source_key"],
        "matrix_sha256": matrix_hash,
        "bundle_sha256": bundle_hash,
        "three_way_exact_matrix_match": True,
        "rotation_deg": rotation,
        "translation_components_m": translation,
        "final_rank": int(diagnostics["final_rank"]),
        "final_correspondences": int(diagnostics["final_correspondences"]),
        "old_consumer_guard": {
            "global_choice": global_selection["choice"],
            "global_status": global_selection["status"],
            "block_choice": block_selection["choice"],
            "block_status": block_selection["status"],
            "block_transforms": block_selection["block_transforms"],
            "human_override_source": "adoption_authority",
        },
    }


def camera_block_names(path: Path) -> set[str]:
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    names = [row["image_name"] for row in rows]
    if len(names) != len(set(names)):
        raise PoseAdoptionError("camera-block inventory contains duplicate image names")
    return set(names)


def iter_points3d_records(
    path: Path,
) -> Iterator[tuple[int, np.ndarray, bytes, bytes, bytes]]:
    with path.open("rb") as handle:
        raw_count = handle.read(8)
        if len(raw_count) != 8:
            raise PoseAdoptionError("truncated points3D header")
        count = struct.unpack("<Q", raw_count)[0]
        for _ in range(count):
            point_id_raw = handle.read(8)
            xyz_raw = handle.read(24)
            fixed_tail = handle.read(11)
            track_count_raw = handle.read(8)
            if (
                len(point_id_raw) != 8
                or len(xyz_raw) != 24
                or len(fixed_tail) != 11
                or len(track_count_raw) != 8
            ):
                raise PoseAdoptionError("truncated points3D record")
            track_count = struct.unpack("<Q", track_count_raw)[0]
            track = handle.read(8 * track_count)
            if len(track) != 8 * track_count:
                raise PoseAdoptionError("truncated points3D track")
            yield (
                struct.unpack("<Q", point_id_raw)[0],
                np.asarray(struct.unpack("<ddd", xyz_raw), dtype=np.float64),
                fixed_tail,
                track_count_raw,
                track,
            )
        if handle.read(1):
            raise PoseAdoptionError("unexpected trailing bytes in points3D")


def validate_points3d_transform(
    source: Path,
    target: Path,
    transform: np.ndarray,
    *,
    forward_tolerance: float,
    roundtrip_tolerance: float,
) -> dict[str, Any]:
    sentinel = object()
    inverse = np.linalg.inv(transform)
    count = 0
    max_forward = 0.0
    max_roundtrip = 0.0
    for source_record, target_record in itertools.zip_longest(
        iter_points3d_records(source),
        iter_points3d_records(target),
        fillvalue=sentinel,
    ):
        if source_record is sentinel or target_record is sentinel:
            raise PoseAdoptionError("source/derived points3D record counts differ")
        source_id, source_xyz, source_fixed, source_track_n, source_track = (
            source_record
        )
        target_id, target_xyz, target_fixed, target_track_n, target_track = (
            target_record
        )
        if (
            source_id != target_id
            or source_fixed != target_fixed
            or source_track_n != target_track_n
            or source_track != target_track
        ):
            raise PoseAdoptionError(
                f"points3D non-XYZ metadata differs for point {source_id}"
            )
        expected = (transform @ np.append(source_xyz, 1.0))[:3]
        recovered = (inverse @ np.append(target_xyz, 1.0))[:3]
        max_forward = max(
            max_forward, float(np.max(np.abs(target_xyz - expected)))
        )
        max_roundtrip = max(
            max_roundtrip, float(np.max(np.abs(recovered - source_xyz)))
        )
        count += 1
    if max_forward > forward_tolerance:
        raise PoseAdoptionError("points3D forward-transform error exceeds tolerance")
    if max_roundtrip > roundtrip_tolerance:
        raise PoseAdoptionError("points3D inverse-roundtrip error exceeds tolerance")
    return {
        "record_count": count,
        "ids_rgb_error_tracks_byte_identical": True,
        "maximum_forward_error_m": max_forward,
        "maximum_inverse_roundtrip_error_m": max_roundtrip,
    }


def publish_sparse_to_staging(
    config: Mapping[str, Any],
    coreg: Any,
    local_transform: np.ndarray,
) -> dict[str, Any]:
    outputs = config["outputs"]
    source_sparse = repo_path(config["inputs"]["source_sparse"])
    runtime = repo_path(outputs["runtime_dir"])
    staging = repo_path(outputs["staging_dir"])
    stage_sparse = staging / "derived_sparse" / "0"
    final_sparse = repo_path(outputs["derived_sparse"])
    runtime.mkdir(parents=True, exist_ok=False)
    stage_sparse.mkdir(parents=True, exist_ok=False)

    source_files = {
        name: source_sparse / name
        for name in ("cameras.bin", "images.bin", "points3D.bin")
    }
    stage_files = {
        name: stage_sparse / name
        for name in ("cameras.bin", "images.bin", "points3D.bin")
    }
    for name in source_files:
        if source_files[name].resolve() == stage_files[name].resolve():
            raise PoseAdoptionError(f"source/derived path alias detected: {name}")
    source_hashes_before = {
        name: sha256_file(path) for name, path in source_files.items()
    }
    locked = config["input_sha256"]
    for name, observed in source_hashes_before.items():
        logical = f"{config['inputs']['source_sparse']}/{name}"
        if observed != locked[logical]:
            raise PoseAdoptionError(f"source sparse hash drift before R1: {name}")

    shutil.copyfile(source_files["cameras.bin"], stage_files["cameras.bin"])
    source_images = coreg.read_images_bin_complete(source_files["images.bin"])
    expected_count = int(config["validation"]["expected_image_count"])
    if len(source_images) != expected_count:
        raise PoseAdoptionError("source COLMAP image count is not 937")
    source_names = {record.name for record in source_images.values()}
    if len(source_names) != expected_count:
        raise PoseAdoptionError("source COLMAP image names are not unique")
    block_names = camera_block_names(repo_path(config["inputs"]["camera_blocks_csv"]))
    if source_names != block_names:
        raise PoseAdoptionError("937-pose and camera-block inventories differ")

    expected_images: dict[int, Any] = {}
    for image_id, image in source_images.items():
        qvec, tvec = coreg.update_colmap_pose(
            image.qvec, image.tvec, local_transform
        )
        expected_images[image_id] = coreg.ColmapImageRecord(
            image.image_id,
            qvec,
            tvec,
            image.camera_id,
            image.name,
            image.points2d_tail,
        )
    coreg.write_images_bin_complete(stage_files["images.bin"], expected_images)
    derived_images = coreg.read_images_bin_complete(stage_files["images.bin"])
    if set(source_images) != set(derived_images):
        raise PoseAdoptionError("derived images.bin ID inventory differs")

    projection_errors: list[float] = []
    center_errors: list[float] = []
    roundtrip_rotation_errors: list[float] = []
    roundtrip_translation_errors: list[float] = []
    inverse = np.linalg.inv(local_transform)
    for image_id in sorted(source_images):
        source = source_images[image_id]
        expected = expected_images[image_id]
        derived = derived_images[image_id]
        if (
            derived.image_id != source.image_id
            or derived.camera_id != source.camera_id
            or derived.name != source.name
            or derived.points2d_tail != source.points2d_tail
            or not np.array_equal(derived.qvec, expected.qvec)
            or not np.array_equal(derived.tvec, expected.tvec)
        ):
            raise PoseAdoptionError(f"derived image record drift: {image_id}")
        projection_errors.append(
            coreg.verify_projection_invariance(source, derived, local_transform)
        )
        center_errors.append(
            coreg.verify_camera_center_invariance(
                source, derived, local_transform
            )
        )
        recovered_qvec, recovered_tvec = coreg.update_colmap_pose(
            derived.qvec, derived.tvec, inverse
        )
        roundtrip_rotation_errors.append(
            float(
                np.max(
                    np.abs(
                        coreg.qvec_to_rotmat(recovered_qvec)
                        - coreg.qvec_to_rotmat(source.qvec)
                    )
                )
            )
        )
        roundtrip_translation_errors.append(
            float(np.max(np.abs(recovered_tvec - source.tvec)))
        )

    validation = config["validation"]
    max_projection = max(projection_errors)
    max_center = max(center_errors)
    max_roundtrip_rotation = max(roundtrip_rotation_errors)
    max_roundtrip_translation = max(roundtrip_translation_errors)
    if max_projection > float(validation["projection_tolerance"]):
        raise PoseAdoptionError("projection invariance error exceeds tolerance")
    if max_center > float(validation["camera_center_tolerance_m"]):
        raise PoseAdoptionError("camera-center error exceeds tolerance")
    if max_roundtrip_rotation > float(
        validation["pose_roundtrip_rotation_tolerance"]
    ):
        raise PoseAdoptionError("pose rotation roundtrip exceeds tolerance")
    if max_roundtrip_translation > float(
        validation["pose_roundtrip_translation_tolerance_m"]
    ):
        raise PoseAdoptionError("pose translation roundtrip exceeds tolerance")

    point_count = coreg.transform_points3d_bin(
        source_files["points3D.bin"],
        stage_files["points3D.bin"],
        local_transform,
    )
    points_validation = validate_points3d_transform(
        source_files["points3D.bin"],
        stage_files["points3D.bin"],
        local_transform,
        forward_tolerance=float(validation["points_forward_tolerance_m"]),
        roundtrip_tolerance=float(
            validation["points_roundtrip_tolerance_m"]
        ),
    )
    if point_count != points_validation["record_count"]:
        raise PoseAdoptionError("points3D writer/validator counts differ")

    source_hashes_after = {
        name: sha256_file(path) for name, path in source_files.items()
    }
    if source_hashes_before != source_hashes_after:
        raise PoseAdoptionError("source sparse model changed during R1")
    derived_hashes = {
        name: sha256_file(path) for name, path in stage_files.items()
    }
    if derived_hashes["cameras.bin"] != source_hashes_before["cameras.bin"]:
        raise PoseAdoptionError("camera intrinsics were not copied byte-for-byte")
    if derived_hashes["images.bin"] == source_hashes_before["images.bin"]:
        raise PoseAdoptionError("derived pose file unexpectedly equals source")
    if derived_hashes["points3D.bin"] == source_hashes_before["points3D.bin"]:
        raise PoseAdoptionError("derived points3D file unexpectedly equals source")

    return {
        "source_sparse": relative(source_sparse),
        "staged_sparse": relative(stage_sparse),
        "final_sparse": relative(final_sparse),
        "source_sha256_before": source_hashes_before,
        "source_sha256_after": source_hashes_after,
        "derived_sha256": derived_hashes,
        "image_count": len(derived_images),
        "camera_block_inventory_count": len(block_names),
        "camera_pose_records_transformed_once": len(derived_images),
        "points3d_coordinate_companion_transform": True,
        "points3d_is_not_an_independent_alignment_treatment": True,
        "transformed_point3d_count": point_count,
        "points3d_validation": points_validation,
        "maximum_projection_invariance_error": max_projection,
        "maximum_camera_center_error_m": max_center,
        "maximum_pose_roundtrip_rotation_matrix_error": max_roundtrip_rotation,
        "maximum_pose_roundtrip_translation_error_m": max_roundtrip_translation,
        "points2d_tails_preserved": True,
        "camera_intrinsics_copied_byte_identical": True,
    }


def csv_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() == "true"


def compare_published_mapping(
    *,
    building_id: str,
    kind: str,
    expected: Mapping[str, Any],
    published: Mapping[str, Any],
    prefix: str,
    tolerance: float,
) -> float:
    maximum_numeric_difference = 0.0
    for key, expected_value in expected.items():
        column = f"{prefix}{key}"
        if column not in published:
            raise PoseAdoptionError(
                f"published {kind} column missing for {building_id}: {column}"
            )
        observed_raw = published[column]
        if expected_value is None:
            if observed_raw not in ("", None):
                raise PoseAdoptionError(
                    f"published {kind} null drift for {building_id}: {column}"
                )
        elif isinstance(expected_value, (bool, np.bool_)):
            if csv_bool(observed_raw) != bool(expected_value):
                raise PoseAdoptionError(
                    f"published {kind} bool drift for {building_id}: {column}"
                )
        elif isinstance(expected_value, (int, np.integer)):
            if int(observed_raw) != int(expected_value):
                raise PoseAdoptionError(
                    f"published {kind} integer drift for {building_id}: {column}"
                )
        elif isinstance(expected_value, (float, np.floating)):
            difference = abs(float(observed_raw) - float(expected_value))
            maximum_numeric_difference = max(
                maximum_numeric_difference, difference
            )
            if difference > tolerance:
                raise PoseAdoptionError(
                    f"published {kind} numeric drift for {building_id}: "
                    f"{column}: {difference} > {tolerance}"
                )
        elif str(observed_raw) != str(expected_value):
            raise PoseAdoptionError(
                f"published {kind} text drift for {building_id}: {column}"
            )
    return maximum_numeric_difference


def reproduce_diagnostic(
    config: Mapping[str, Any],
    diagnostic: Any,
    candidate: np.ndarray,
) -> dict[str, Any]:
    diagnostic_config_path = repo_path(config["inputs"]["diagnostic_config"])
    diag_config = diagnostic.load_config(diagnostic_config_path)
    diagnostic.verify_method_lock(diag_config)
    verified_reference = diagnostic.verify_outputs(diag_config)
    observed_inputs = diagnostic.verify_inputs(diag_config, include_clouds=True)
    running = diagnostic.active_learning_processes()
    if running:
        raise PoseAdoptionError(
            f"learning-like process found before diagnostic reproduction: {running}"
        )
    targets, ladder_by_id = diagnostic.load_population(diag_config)
    coreg = diagnostic.load_coreg_module(diag_config)
    groups_by_id, inventory, context = diagnostic.build_inventory(
        diag_config, coreg, targets
    )
    footprints = context["footprints"]
    identity = np.eye(4, dtype=np.float64)
    before_metrics: dict[str, dict[str, Any]] = {}
    after_metrics: dict[str, dict[str, Any]] = {}
    after_offsets: dict[str, dict[str, Any]] = {}
    rows: list[dict[str, Any]] = []
    for target in targets:
        building_id = target["building_id"]
        groups = groups_by_id.get(building_id, [])
        before, _, _, _, _ = diagnostic.evaluate_building(
            diag_config,
            groups,
            identity,
            "before",
            footprints[building_id],
            source_population="raw_dense_all_178",
            tier=target["tier"],
            population_role=target["cohort"],
        )
        after, offset, _, _, _ = diagnostic.evaluate_building(
            diag_config,
            groups,
            candidate,
            "after",
            footprints[building_id],
            source_population="raw_dense_all_178",
            tier=target["tier"],
            population_role=target["cohort"],
        )
        before_metrics[building_id] = before
        after_metrics[building_id] = after
        after_offsets[building_id] = offset
        row = dict(inventory[building_id])
        row["boundary_cell_label"] = ladder_by_id[building_id]["cell_label"]
        diagnostic.add_prefixed(row, "before", before)
        diagnostic.add_prefixed(row, "after", after)
        rows.append(row)

    reproduction = config["diagnostic_reproduction"]
    n_values = [int(row["before_correspondence_n"]) for row in rows]
    q10 = int(
        diagnostic.nearest_rank(n_values, float(reproduction["n_quantile"]))
    )
    n_threshold = max(
        int(reproduction["minimum_bidirectional_matches"]), q10
    )
    for row in rows:
        row["correspondence_capable"] = (
            int(row["before_correspondence_n"]) >= n_threshold
        )

    published = diagnostic.read_csv(
        repo_path(config["inputs"]["diagnostic_building_residuals"])
    )
    published_by_id = {row["building_id"]: row for row in published}
    published_offsets = diagnostic.read_csv(
        repo_path(config["inputs"]["diagnostic_building_offsets"])
    )
    published_offsets_by_id = {
        row["building_id"]: row for row in published_offsets
    }
    reproduced_ids = {row["building_id"] for row in rows}
    if (
        set(published_by_id) != reproduced_ids
        or set(published_offsets_by_id) != reproduced_ids
    ):
        raise PoseAdoptionError(
            "published per-building diagnostic inventories did not reproduce"
        )
    row_tolerance = float(
        config["diagnostic_reproduction"]["unrounded_tolerance_m"]
    )
    maximum_residual_row_difference = 0.0
    maximum_offset_row_difference = 0.0
    for building_id in sorted(reproduced_ids):
        maximum_residual_row_difference = max(
            maximum_residual_row_difference,
            compare_published_mapping(
                building_id=building_id,
                kind="candidate residual",
                expected=after_metrics[building_id],
                published=published_by_id[building_id],
                prefix="after_",
                tolerance=row_tolerance,
            ),
        )
        maximum_offset_row_difference = max(
            maximum_offset_row_difference,
            compare_published_mapping(
                building_id=building_id,
                kind="candidate offset",
                expected=after_offsets[building_id],
                published=published_offsets_by_id[building_id],
                prefix="after_",
                tolerance=row_tolerance,
            ),
        )
    published_capable = {
        row["building_id"]
        for row in published
        if csv_bool(row["correspondence_capable"])
    }
    reproduced_capable = {
        row["building_id"] for row in rows if row["correspondence_capable"]
    }
    if published_capable != reproduced_capable:
        raise PoseAdoptionError("diagnostic capability membership did not reproduce")
    if any(int(row["n_threshold"]) != n_threshold for row in published):
        raise PoseAdoptionError("published diagnostic n threshold drift")

    capable = [row for row in rows if row["correspondence_capable"]]
    passing = [
        row
        for row in capable
        if row["after_matched_median_m"] is not None
        and float(row["after_matched_median_m"])
        <= float(reproduction["gate_threshold_m"])
    ]
    core_rows = [row for row in rows if row["cohort"] == "core"]
    core_capable = [row for row in core_rows if row["correspondence_capable"]]
    core_passing = [
        row
        for row in core_capable
        if row["after_matched_median_m"] is not None
        and float(row["after_matched_median_m"])
        <= float(reproduction["gate_threshold_m"])
    ]
    median = float(
        np.median(
            [
                float(row["after_matched_median_m"])
                for row in capable
                if row["after_matched_median_m"] is not None
            ]
        )
    )
    offset_values = [
        float(value["median_r_total_m"])
        for value in after_offsets.values()
        if value["median_r_total_m"] is not None
    ]
    t5_total = float(np.median(offset_values))
    tier_summary = diagnostic.tier_summary_rows(rows, n_threshold)
    after_all = next(
        row
        for row in tier_summary
        if row["state"] == "diagnostic_global_candidate_not_adopted"
        and row["tier"] == "all"
    )

    exact_expectations = {
        "n_threshold": (n_threshold, reproduction["expected_n_threshold"]),
        "population_n": (len(rows), reproduction["expected_population_n"]),
        "correspondence_capable_n": (
            len(capable),
            reproduction["expected_correspondence_capable_n"],
        ),
        "matched_median_le_0p3_n": (
            len(passing),
            reproduction["expected_matched_median_le_0p3_n"],
        ),
        "core_population_n": (
            len(core_rows),
            reproduction["expected_core_population_n"],
        ),
        "core_correspondence_capable_n": (
            len(core_capable),
            reproduction["expected_core_correspondence_capable_n"],
        ),
        "core_matched_median_le_0p3_n": (
            len(core_passing),
            reproduction["expected_core_matched_median_le_0p3_n"],
        ),
        "offsets_observed_n": (
            len(offset_values),
            reproduction["expected_offsets_observed_n"],
        ),
    }
    for label, (observed, expected) in exact_expectations.items():
        if int(observed) != int(expected):
            raise PoseAdoptionError(
                f"diagnostic reproduction mismatch {label}: {observed} != {expected}"
            )
    unrounded_tolerance = float(reproduction["unrounded_tolerance_m"])
    if (
        abs(median - float(reproduction["expected_building_balanced_median_m"]))
        > unrounded_tolerance
    ):
        raise PoseAdoptionError("diagnostic matched-median aggregate mismatch")
    if (
        abs(
            float(after_all["building_balanced_median_of_matched_medians_m"])
            - median
        )
        > unrounded_tolerance
    ):
        raise PoseAdoptionError("tier-summary and direct median aggregates differ")
    if (
        abs(
            t5_total
            - float(reproduction["expected_t5_total_residual_m_rounded"])
        )
        > float(reproduction["rounded_report_tolerance_m"])
    ):
        raise PoseAdoptionError("diagnostic T5 total residual mismatch")

    return {
        "schema": "jointbuildgs.fusion_w1.pose_adoption_v2.diagnostic_reproduction.v1",
        "status": "PASSED",
        "method": "locked_coregdiag_functions_without_measure_command",
        "corrected_images_bin_directly_consumed": False,
        "pose_frame_equivalence_basis": (
            "same adopted transform hash plus all-camera center/projection/roundtrip checks"
        ),
        "candidate_applied_in_memory_to_raw_dense_count": 1,
        "raw_dense_or_source_pose_modified": False,
        "reference_outputs_verified": verified_reference,
        "current_input_sha256": observed_inputs,
        "membership_matches_published_building_ids": True,
        "per_building_candidate_residual_rows_reproduced_n": len(rows),
        "per_building_candidate_offset_rows_reproduced_n": len(rows),
        "maximum_candidate_residual_row_difference": (
            maximum_residual_row_difference
        ),
        "maximum_candidate_offset_row_difference": maximum_offset_row_difference,
        "n_threshold": n_threshold,
        "population_n": len(rows),
        "correspondence_capable_n": len(capable),
        "matched_median_le_0p3_n": len(passing),
        "core_population_n": len(core_rows),
        "core_correspondence_capable_n": len(core_capable),
        "core_matched_median_le_0p3_n": len(core_passing),
        "building_balanced_median_of_matched_medians_m": median,
        "offsets_observed_n": len(offset_values),
        "t5_building_balanced_median_r_total_m": t5_total,
        "tolerances": {
            "unrounded_m": unrounded_tolerance,
            "rounded_report_m": float(
                reproduction["rounded_report_tolerance_m"]
            ),
        },
        "learning_runs_started": 0,
        "readout_runs_started": 0,
        "roofer_runs_started": 0,
        "scoring_runs_started": 0,
    }


def render_issue_append(existing: str, entries: Sequence[str]) -> str:
    for entry in entries:
        if entry in existing:
            raise PoseAdoptionError("success issue entry already exists")
        if not entry.startswith("## FUS-W1-") or "\n- Status:" not in entry:
            raise PoseAdoptionError(
                "issue entry is not one locked detailed markdown section"
            )
    return existing.rstrip() + "\n\n" + "\n\n".join(entries) + "\n"


def append_success_issues(config: Mapping[str, Any]) -> dict[str, Any]:
    contract = config["issues_contract"]
    path = repo_path(contract["path"])
    before_hash = sha256_file(path)
    if before_hash != contract["expected_before_sha256"]:
        raise PoseAdoptionError("issues.md changed before success append")
    existing = path.read_text(encoding="utf-8")
    updated = render_issue_append(existing, contract["entries"])
    atomic_text(path, updated)
    after_hash = sha256_file(path)
    return {
        "path": contract["path"],
        "before_sha256": before_hash,
        "after_sha256": after_hash,
        "entries_appended": list(contract["entries"]),
        "append_count": len(contract["entries"]),
        "append_only_on_success": True,
    }


def failure_payload(
    config: Mapping[str, Any],
    error: BaseException,
    *,
    claim_owned: bool,
    claim_id: str | None,
) -> dict[str, Any]:
    outputs = config.get("outputs", {})
    partial_paths = {
        key: bool(repo_path(path).exists() or repo_path(path).is_symlink())
        for key, path in outputs.items()
        if key
        in {
            "claim",
            "event_log",
            "diagnostic_reproduction",
            "manifest",
            "runtime_dir",
            "derived_sparse",
        }
    }
    issues_path = repo_path(config["issues_contract"]["path"])
    issues_hash = sha256_file(issues_path) if issues_path.is_file() else None
    return {
        "schema": "jointbuildgs.fusion_w1.pose_adoption_v2.failure.v1",
        "status": "BLOCKED",
        "task_id": config.get("task_id"),
        "run_id": config.get("run_id"),
        "at": now_utc(),
        "error_type": type(error).__name__,
        "error": str(error),
        "claim_owned_by_failing_process": claim_owned,
        "claim_id": claim_id,
        "source_data_modified": None,
        "source_integrity_status": (
            "not_asserted_on_failure; inspect locked before/after hashes"
        ),
        "partial_publication": partial_paths,
        "issues_sha256_observed": issues_hash,
        "issues_sha256_expected_before": config["issues_contract"][
            "expected_before_sha256"
        ],
        "learning_runs_started": 0,
        "readout_runs_started": 0,
        "roofer_runs_started": 0,
        "scoring_runs_started": 0,
        "recovery": (
            "Manifest is the only R1 commit marker. Do not reapply the transform. "
            "Inspect the retained claim, partial-publication map, hashes, and "
            "staging; obtain explicit recovery authorization."
        ),
    }


def execute(config: Mapping[str, Any], config_path: Path) -> dict[str, Any]:
    verify_config(config, config_path)
    check_outputs_absent(config)
    repo_gate = verify_repo_gate(config)
    r0_gate = verify_r0_gate(config)
    input_hashes = verify_input_hashes(config)
    immutable_inputs_before = snapshot_immutable_inputs(config)
    coordinate_datum = verify_coordinate_datum(config)
    arm_configs = verify_arm_pose_configs(config)

    coreg = import_locked_module(
        "fusion_w1_coreg_lock1_pose_adoption_locked",
        repo_path(config["inputs"]["coreg_implementation"]),
    )
    coreg_config = coreg.load_config(repo_path(config["inputs"]["coreg_config"]))
    if (
        coreg_config["input_locks"]["transform_direction"]
        != config["transform_contract"]["transform_direction"]
        or coreg_config["input_locks"]["rotation_pivot_global_m"]
        != config["transform_contract"]["rotation_pivot_global_m"]
        or coreg_config["input_locks"]["scene_global_to_canonical_shift_m"]
        != config["transform_contract"]["scene_global_to_canonical_shift_m"]
    ):
        raise PoseAdoptionError("coreg coordinate contract drift")
    diagnostic = import_locked_module(
        "fusion_w1_coregdiag_pose_adoption_locked",
        repo_path(config["inputs"]["diagnostic_implementation"]),
    )
    running = diagnostic.active_learning_processes()
    if running:
        raise PoseAdoptionError(f"learning-like process active before R1: {running}")

    fit = load_json(config["inputs"]["fit_candidate"])
    global_selection = load_json(config["inputs"]["global_selection"])
    block_selection = load_json(config["inputs"]["block_selection"])
    candidate, candidate_receipt = extract_and_validate_candidate(
        config, coreg, fit, global_selection, block_selection
    )
    global_transform = coreg.pivot_global_to_homogeneous(
        candidate, config["transform_contract"]["rotation_pivot_global_m"]
    )
    local_transform = coreg.conjugate_global_to_canonical(
        global_transform,
        config["transform_contract"]["scene_global_to_canonical_shift_m"],
    )
    tolerance = float(config["validation"]["rigid_tolerance"])
    coreg.validate_rigid_transform(global_transform, tolerance=tolerance)
    coreg.validate_rigid_transform(local_transform, tolerance=tolerance)

    outputs = config["outputs"]
    claim_path = repo_path(outputs["claim"])
    claim_id = uuid.uuid4().hex
    claim = {
        "schema": "jointbuildgs.fusion_w1.pose_adoption_v2.claim.v1",
        "state": "STARTED_EXACT_ONCE",
        "task_id": config["task_id"],
        "run_id": config["run_id"],
        "started_at": now_utc(),
        "claim_id": claim_id,
        "owner_pid": os.getpid(),
        "head": repo_gate["head"],
        "config_path": relative(config_path),
        "config_sha256": sha256_file(config_path),
        "r0_receipt_sha256": r0_gate["sha256"],
        "candidate_matrix_sha256": candidate_receipt["matrix_sha256"],
        "immutable_inputs_before_sha256": canonical_json_sha(
            immutable_inputs_before
        ),
        "source_images_sha256": input_hashes[
            f"{config['inputs']['source_sparse']}/images.bin"
        ],
        "transform_application_count_before_claim": 0,
        **config["execution_counters"],
    }
    try:
        exclusive_json(claim_path, claim)
    except FileExistsError as error:
        raise ClaimConflictError(
            f"R1 exact-once claim was won by another process: {relative(claim_path)}"
        ) from error
    journal = EventJournal(repo_path(outputs["event_log"]))
    journal.write(
        "r1_claimed",
        claim=outputs["claim"],
        candidate_matrix_sha256=candidate_receipt["matrix_sha256"],
    )
    try:
        sparse = publish_sparse_to_staging(config, coreg, local_transform)
        journal.write(
            "pose_model_staged_and_validated",
            image_count=sparse["image_count"],
            point_count=sparse["transformed_point3d_count"],
        )
        diagnostic_receipt = reproduce_diagnostic(
            config, diagnostic, candidate
        )
        journal.write(
            "diagnostic_reproduced",
            correspondence_capable_n=diagnostic_receipt[
                "correspondence_capable_n"
            ],
            matched_median_le_0p3_n=diagnostic_receipt[
                "matched_median_le_0p3_n"
            ],
        )

        source_als_hash_after = sha256_file(
            repo_path(config["inputs"]["source_als_laz"])
        )
        if source_als_hash_after != config["input_sha256"][
            config["inputs"]["source_als_laz"]
        ]:
            raise PoseAdoptionError("ALS source changed during R1")
        immutable_inputs_after = snapshot_immutable_inputs(config)
        if immutable_inputs_after != immutable_inputs_before:
            raise PoseAdoptionError(
                "canonical ALS/image/footprint/reference inputs changed during R1"
            )

        manifest = {
            "schema": "jointbuildgs.fusion_w1.pose_adoption_v2.manifest.v1",
            "status": "PASSED",
            "task_id": config["task_id"],
            "run_id": config["run_id"],
            "created_at": now_utc(),
            "branch": repo_gate["branch"],
            "head": repo_gate["head"],
            "claim_path": outputs["claim"],
            "claim_sha256": sha256_file(claim_path),
            "r0_gate": r0_gate,
            "input_sha256": input_hashes,
            "immutable_inputs_before": immutable_inputs_before,
            "immutable_inputs_after": immutable_inputs_after,
            "immutable_inputs_unchanged": True,
            "coordinate_datum": coordinate_datum,
            "crs_unchanged": True,
            "scale_unchanged": True,
            "candidate_source": candidate_receipt,
            "adoption_authority": dict(config["adoption_authority"]),
            "transform_direction": config["transform_contract"][
                "transform_direction"
            ],
            "pivot_global_m": config["transform_contract"][
                "rotation_pivot_global_m"
            ],
            "photo_to_als_pivot_matrix": serialize_matrix(candidate),
            "photo_to_als_global_homogeneous": serialize_matrix(
                global_transform
            ),
            "photo_to_als_canonical_homogeneous": serialize_matrix(
                local_transform
            ),
            "adopted_matrix_sha256": candidate_receipt["matrix_sha256"],
            "adopted_bundle_sha256": candidate_receipt["bundle_sha256"],
            "transform_application_count": 1,
            "application_scope": "all_937_camera_poses_once",
            "als_source_modified": False,
            "image_pixels_modified": False,
            "footprint_modified": False,
            "reference_gml_modified": False,
            "source_pose_modified": False,
            "derived_pose_differs_from_source": True,
            "zeta_applied_during_pose_publication": False,
            "orthometric_to_ellipsoidal_zeta_m_unchanged": 45.7,
            "source_sparse": sparse["source_sparse"],
            "derived_sparse": outputs["derived_sparse"],
            "source_sha256": sparse["source_sha256_before"],
            "source_sha256_after": sparse["source_sha256_after"],
            "derived_sha256": sparse["derived_sha256"],
            "image_count": sparse["image_count"],
            "transformed_point3d_count": sparse[
                "transformed_point3d_count"
            ],
            "points3d_coordinate_companion_transform": True,
            "points3d_is_not_an_independent_alignment_treatment": True,
            "pose_validation": {
                key: value
                for key, value in sparse.items()
                if key
                not in {
                    "source_sparse",
                    "staged_sparse",
                    "final_sparse",
                    "source_sha256_before",
                    "source_sha256_after",
                    "derived_sha256",
                }
            },
            "diagnostic_reproduction": diagnostic_receipt,
            "diagnostic_reproduction_path": outputs[
                "diagnostic_reproduction"
            ],
            "arm_pose_contract": {
                **arm_configs,
                "arm_A_required_pose_sha256": sparse["derived_sha256"][
                    "images.bin"
                ],
                "arm_B_required_pose_sha256": sparse["derived_sha256"][
                    "images.bin"
                ],
                "identical": True,
            },
            "learning_allowed": False,
            "r2_overlay_and_gate_record_ready": True,
            "next_step": "R2 Gate A v2 registration and qualitative overlays",
            **config["execution_counters"],
        }

        staging = repo_path(outputs["staging_dir"])
        staged_derived = staging / "derived_sparse"
        final_derived = repo_path(outputs["derived_sparse"]).parent
        if final_derived.exists():
            raise PoseAdoptionError("final derived_sparse appeared during R1")
        os.replace(staged_derived, final_derived)
        atomic_json(
            repo_path(outputs["diagnostic_reproduction"]),
            diagnostic_receipt,
        )
        if staging.exists():
            shutil.rmtree(staging)
        issues_receipt = append_success_issues(config)
        manifest["issues_append"] = issues_receipt
        manifest["issues_sha256_after"] = issues_receipt["after_sha256"]
        journal.write(
            "r1_manifest_ready",
            manifest=outputs["manifest"],
            derived_images_sha256=sparse["derived_sha256"]["images.bin"],
        )
        journal.close()
        manifest["event_log_sha256"] = sha256_file(
            repo_path(outputs["event_log"])
        )
        atomic_json(repo_path(outputs["manifest"]), manifest)
        return manifest
    except BaseException as error:
        try:
            journal.write(
                "r1_blocked",
                claim_id=claim_id,
                error_type=type(error).__name__,
                error=str(error),
            )
        except BaseException:
            pass
        failure_path = repo_path(outputs["failure"])
        if not failure_path.exists():
            atomic_json(
                failure_path,
                failure_payload(
                    config,
                    error,
                    claim_owned=True,
                    claim_id=claim_id,
                ),
            )
        raise
    finally:
        journal.close()


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("command", choices=("publish",), nargs="?", default="publish")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    config_path = args.config.resolve()
    config = load_json(config_path)
    try:
        manifest = execute(config, config_path)
        print(
            json.dumps(
                {
                    "status": manifest["status"],
                    "manifest": config["outputs"]["manifest"],
                    "derived_sparse": manifest["derived_sparse"],
                    "images_sha256": manifest["derived_sha256"]["images.bin"],
                    "image_count": manifest["image_count"],
                },
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        return 0
    except BaseException as error:
        failure_path_raw = config.get("outputs", {}).get("failure")
        if failure_path_raw and not isinstance(error, ClaimConflictError):
            failure_path = repo_path(failure_path_raw)
            if not failure_path.exists():
                atomic_json(
                    failure_path,
                    failure_payload(
                        config,
                        error,
                        claim_owned=False,
                        claim_id=None,
                    ),
                )
        print(
            json.dumps(
                {
                    "status": "BLOCKED",
                    "error_type": type(error).__name__,
                    "error": str(error),
                    "claim_conflict": isinstance(error, ClaimConflictError),
                },
                ensure_ascii=False,
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
