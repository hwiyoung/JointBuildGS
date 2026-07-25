#!/usr/bin/env python3
"""Materialize and launch one locked Fusion-W1 30k training job.

The materializer binds the corrected R1 pose, the registered Gate-A-v2 PASS,
and every byte published by the per-building §3 preprocessor.  It constructs
both treatment recipes in memory and proves that the scientific configurations
differ only in the depth/normal base and final weights before publishing the
requested arm.

The launcher is deliberately single-job and foreground.  It claims the job
with an exclusive ``started.json`` receipt, updates the aggregate runtime
counter under ``flock``, and invokes only the pinned Docker training command.
It does not perform readout, Roofer, or scoring.
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import fcntl
import hashlib
import io
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time
from typing import Any, Callable, Mapping, Sequence
from zoneinfo import ZoneInfo

import yaml


REPO = Path(__file__).resolve().parents[3]
CONFIG_SCHEMA = "jointbuildgs.fusion_w1.training_driver.config.v1"
PREPROCESS_SCHEMA = "jointbuildgs.fusion_w1.preprocess_building.v1"
MATERIALIZATION_SCHEMA = "jointbuildgs.fusion_w1.training_materialization.v1"
STARTED_SCHEMA = "jointbuildgs.fusion_w1.training_started.v1"
COMPLETED_SCHEMA = "jointbuildgs.fusion_w1.training_completed.v1"
FAILED_SCHEMA = "jointbuildgs.fusion_w1.training_failed.v1"
COUNTER_SCHEMA = "jointbuildgs.fusion_w1.training_runtime_counters.v1"
RETRY_POLICY_SCHEMA = "jointbuildgs.fusion_w1.training_infra_retry_policy.v1"
RETRY_STARTED_SCHEMA = "jointbuildgs.fusion_w1.training_infra_retry_started.v1"
RETRY_COMPLETED_SCHEMA = "jointbuildgs.fusion_w1.training_infra_retry_completed.v1"
RETRY_FAILED_SCHEMA = "jointbuildgs.fusion_w1.training_infra_retry_failed.v1"
CONTAINER_REPO = Path("/workspace/JointBuildGS")
RUNS = ("r1", "r2")
ARMS = ("A", "B")
ABLATION_DIFFERENCES = frozenset(
    {"w_depth", "depth_final_weight", "w_normal", "normal_final_weight"}
)
LOSS_SHARE_FIELDS = (
    "building_id",
    "arm",
    "run",
    "seed",
    "step",
    "term",
    "raw_loss",
    "weight",
    "weighted_loss",
    "weighted_loss_share",
    "grad_norm",
    "grad_norm_share",
    "grad_status",
    "total_loss",
    "psnr_train",
    "n_primitives",
    "denominator_role",
    "source_csv_sha256",
    "materialization_sha256",
)


class ContractError(RuntimeError):
    """A locked input or pre-start condition was not satisfied."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def canonical_json_bytes(payload: Any) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def sha256_file(path: Path, block_size: int = 1 << 20) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(block_size), b""):
            digest.update(block)
    return digest.hexdigest()


def load_json_snapshot(path: Path) -> tuple[dict[str, Any], str]:
    try:
        raw = path.read_bytes()
        payload = json.loads(raw)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ContractError(f"cannot load JSON {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ContractError(f"JSON root must be an object: {path}")
    return payload, sha256_bytes(raw)


def atomic_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f".{path.name}.",
        delete=False,
    ) as stream:
        temporary = Path(stream.name)
        stream.write(text)
        stream.flush()
        os.fsync(stream.fileno())
        os.fchmod(stream.fileno(), 0o644)
    os.replace(temporary, path)
    path.chmod(0o644)
    directory_fd = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)


def atomic_json(path: Path, payload: Mapping[str, Any]) -> None:
    atomic_text(
        path,
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
            allow_nan=False,
        )
        + "\n",
    )


def atomic_csv(path: Path, rows: Sequence[Mapping[str, Any]], fields: Sequence[str]) -> None:
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(
        buffer,
        fieldnames=list(fields),
        lineterminator="\n",
        extrasaction="raise",
    )
    writer.writeheader()
    for row in rows:
        writer.writerow(row)
    atomic_text(path, buffer.getvalue())


def exclusive_json(path: Path, payload: Mapping[str, Any]) -> None:
    """Create one receipt exactly once and durably."""

    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = (
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    except FileExistsError as exc:
        raise ContractError(f"exclusive receipt already exists: {path}") from exc
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        # Keep a partially installed exclusive claim rather than reopening the
        # possibility of a duplicate launch.
        raise
    directory_fd = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)


def repo_relative(repo: Path, path: Path) -> str:
    try:
        return str(path.resolve().relative_to(repo.resolve()))
    except ValueError as exc:
        raise ContractError(f"path is outside repository: {path}") from exc


def resolve_path(repo: Path, value: str, *, local_base: Path | None = None) -> Path:
    raw = Path(str(value))
    if raw.is_absolute():
        try:
            relative = raw.relative_to(CONTAINER_REPO)
        except ValueError:
            candidate = raw
        else:
            candidate = repo / relative
    else:
        repo_candidate = repo / raw
        local_candidate = (local_base / raw) if local_base is not None else None
        if repo_candidate.exists() or local_candidate is None:
            candidate = repo_candidate
        else:
            candidate = local_candidate
    candidate = candidate.resolve()
    repo_relative(repo, candidate)
    return candidate


def container_path(repo: Path, path: Path) -> str:
    return str(CONTAINER_REPO / Path(repo_relative(repo, path)))


def require_equal(observed: Any, expected: Any, label: str) -> None:
    if observed != expected:
        raise ContractError(
            f"{label} mismatch: observed={observed!r}, expected={expected!r}"
        )


def get_pointer(payload: Mapping[str, Any], pointer: str) -> Any:
    value: Any = payload
    if not pointer.startswith("/"):
        raise ContractError(f"JSON pointer must start with '/': {pointer!r}")
    for token in pointer[1:].split("/"):
        token = token.replace("~1", "/").replace("~0", "~")
        if not isinstance(value, Mapping) or token not in value:
            raise ContractError(f"JSON pointer not found: {pointer}")
        value = value[token]
    return value


def load_driver_config(path: Path) -> dict[str, Any]:
    payload, _ = load_json_snapshot(path)
    require_equal(payload.get("schema"), CONFIG_SCHEMA, "driver config schema")
    require_equal(payload.get("run_id"), "20260724_fusion_w1", "run ID")
    return payload


def validate_cutoff_amendment(
    repo: Path, config: Mapping[str, Any]
) -> dict[str, Any]:
    """Load the human-approved cutoff amendment and bind its exact bytes."""

    launch_contract = config.get("launch_contract")
    if not isinstance(launch_contract, Mapping):
        raise ContractError("launch_contract is missing")
    locked = launch_contract.get("cutoff_amendment")
    if not isinstance(locked, Mapping):
        raise ContractError("cutoff amendment is missing")
    path_value = locked.get("path")
    expected_sha = locked.get("sha256")
    if not isinstance(path_value, str) or not path_value:
        raise ContractError("cutoff amendment path is missing")
    if not isinstance(expected_sha, str) or re.fullmatch(r"[0-9a-f]{64}", expected_sha) is None:
        raise ContractError("cutoff amendment SHA-256 is invalid")
    path = resolve_path(repo, path_value)
    amendment, observed_sha = load_json_snapshot(path)
    require_equal(observed_sha, expected_sha, "cutoff amendment SHA-256")
    require_equal(
        amendment.get("schema"),
        "jointbuildgs.fusion_w1.cutoff_amendment.v1",
        "cutoff amendment schema",
    )
    require_equal(amendment.get("status"), "APPROVED", "cutoff amendment status")
    require_equal(amendment.get("run_id"), config.get("run_id"), "cutoff amendment run ID")
    require_equal(amendment.get("approved_by"), "김휘영", "cutoff amendment approver")
    require_equal(
        amendment.get("decision"),
        "ABOLISH_0630_CUTOFF",
        "cutoff amendment decision",
    )
    require_equal(
        amendment.get("original_cutoff_kst"),
        launch_contract.get("cutoff_kst"),
        "cutoff amendment original cutoff",
    )
    scope = amendment.get("effective_scope")
    if not isinstance(scope, Mapping):
        raise ContractError("cutoff amendment effective_scope is missing")
    require_equal(
        scope.get("allow_new_training_launch_after_original_cutoff"),
        True,
        "cutoff amendment post-cutoff launch approval",
    )
    require_equal(
        scope.get(
            "queue_continues_until_stopped_by_human_or_existing_catastrophic_stop_rule"
        ),
        True,
        "cutoff amendment queue continuation",
    )
    unchanged = amendment.get("unchanged_locks")
    required_unchanged = (
        "target_list",
        "scales_1_to_4",
        "recipe_and_starting_weights",
        "queue_order",
        "scoring_scripts",
        "corrected_pose_binding",
        "gate_a_v2_pass",
        "smoke_building_first",
        "serial_readout_and_ram_cgroup",
    )
    if not isinstance(unchanged, Mapping):
        raise ContractError("cutoff amendment unchanged_locks is missing")
    for key in required_unchanged:
        require_equal(unchanged.get(key), True, f"cutoff amendment unchanged lock {key}")
    return {
        "status": "PASSED",
        "path": repo_relative(repo, path),
        "sha256": observed_sha,
        "approved_by": amendment["approved_by"],
        "approval_date_kst": amendment.get("approval_date_kst"),
        "decision": amendment["decision"],
        "original_cutoff_kst": amendment["original_cutoff_kst"],
        "effective_scope": dict(scope),
        "unchanged_locks": {key: True for key in required_unchanged},
    }


def validate_optimizer_densification_base(
    repo: Path, config: Mapping[str, Any]
) -> dict[str, Any]:
    locked = config["inputs"]["optimizer_densification_base"]
    path = resolve_path(repo, locked["path"])
    observed_sha = sha256_file(path)
    require_equal(
        observed_sha, locked["sha256"], "pilot arm-02 base config SHA-256"
    )
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise ContractError(f"cannot read pilot arm-02 base config {path}: {exc}") from exc
    if not isinstance(payload, Mapping):
        raise ContractError("pilot arm-02 base config root must be a mapping")
    recipe = config["recipe"]
    inherited = (
        "mvs_seed_init_opacity",
        "seed_protect",
        "seed_protect_until_iter",
        "w_photo",
        "photo_lam",
        "w_nc",
        "load_depth",
        "load_normal",
        "lr_means",
        "lr_scales",
        "lr_quats",
        "lr_opacities",
        "lr_sh0",
        "lr_shN",
        "prune_opa",
        "grow_grad2d",
        "grow_scale3d",
        "prune_scale3d",
        "refine_start_iter",
        "refine_stop_iter",
        "refine_every",
        "reset_every",
        "eval_every",
        "ckpt_every",
    )
    for key in inherited:
        require_equal(recipe.get(key), payload.get(key), f"pilot arm-02 inherited {key}")
    return {
        "path": repo_relative(repo, path),
        "sha256": observed_sha,
        "condition": locked["condition"],
        "reuse": locked["reuse"],
        "exact_inherited_keys": list(inherited),
        "fusion_specific_recipe_changes": [
            "per_building_data_and_photo_support_paths",
            "init_pointcloud_mode_replace_with_colored_ALS",
            "max_iter_30000",
            "depth_normal_exp_decay",
            "distortion_stage2_activation",
            "full_state_30k_and_loss_share_audit_runtime_controls",
        ],
    }


def validate_r1_r2(repo: Path, config: Mapping[str, Any]) -> dict[str, Any]:
    inputs = config["inputs"]
    r1_path = resolve_path(repo, inputs["r1_pose_manifest"])
    r1, r1_sha = load_json_snapshot(r1_path)
    require_equal(r1_sha, inputs["r1_pose_manifest_sha256"], "R1 manifest SHA-256")
    require_equal(r1.get("schema"), inputs["r1_pose_manifest_schema"], "R1 schema")
    require_equal(r1.get("status"), "PASSED", "R1 status")
    require_equal(
        get_pointer(r1, inputs["r1_pose_json_pointer"]),
        inputs["corrected_images_sha256"],
        "R1 corrected images.bin SHA-256",
    )
    require_equal(
        r1.get("transform_application_count"),
        inputs["required_transform_application_count"],
        "R1 transform application count",
    )

    r2_path = resolve_path(repo, inputs["r2_gate_manifest"])
    r2, r2_sha = load_json_snapshot(r2_path)
    require_equal(r2_sha, inputs["r2_gate_manifest_sha256"], "R2 manifest SHA-256")
    require_equal(r2.get("schema"), inputs["r2_gate_manifest_schema"], "R2 schema")
    require_equal(r2.get("status"), "PASS", "R2 status")
    require_equal(
        get_pointer(r2, inputs["r2_gate_json_pointer"]),
        inputs["required_gate_status"],
        "Gate A v2 registered status",
    )

    arm_binding_sha: dict[str, str] = {}
    for arm in ARMS:
        locked = inputs["arm_pose_bindings"][arm]
        binding_path = resolve_path(repo, locked["path"])
        binding, binding_sha = load_json_snapshot(binding_path)
        require_equal(binding_sha, locked["sha256"], f"arm {arm} binding SHA-256")
        require_equal(binding.get("arm"), arm, f"arm {arm} binding label")
        pose = binding.get("pose_binding")
        if not isinstance(pose, Mapping):
            raise ContractError(f"arm {arm} pose_binding is missing")
        require_equal(
            pose.get("manifest"),
            inputs["r1_pose_manifest"],
            f"arm {arm} R1 manifest path",
        )
        require_equal(
            pose.get("images_sha256_json_pointer"),
            inputs["r1_pose_json_pointer"],
            f"arm {arm} pose hash pointer",
        )
        require_equal(
            pose.get("required_transform_application_count"),
            1,
            f"arm {arm} transform application count",
        )
        arm_binding_sha[arm] = binding_sha

    return {
        "r1_manifest": repo_relative(repo, r1_path),
        "r1_manifest_sha256": r1_sha,
        "corrected_images_sha256": inputs["corrected_images_sha256"],
        "r1_pose_json_pointer": inputs["r1_pose_json_pointer"],
        "transform_application_count": 1,
        "r2_manifest": repo_relative(repo, r2_path),
        "r2_manifest_sha256": r2_sha,
        "r2_gate_json_pointer": inputs["r2_gate_json_pointer"],
        "r2_gate_status": inputs["required_gate_status"],
        "arm_binding_sha256": arm_binding_sha,
        "optimizer_densification_base": validate_optimizer_densification_base(
            repo, config
        ),
    }


def _manifest_path(
    repo: Path, config: Mapping[str, Any], building_id: str
) -> Path:
    root = resolve_path(repo, config["inputs"]["preprocess_root"])
    return root / "by_building" / building_id / "preprocess_manifest.json"


def _read_view_names(path: Path) -> list[str]:
    try:
        with path.open("r", encoding="utf-8", newline="") as stream:
            reader = csv.DictReader(stream)
            if not reader.fieldnames:
                raise ContractError(f"views CSV has no header: {path}")
            candidates = (
                "image_name",
                "view_name",
                "view",
                "image",
                "name",
                "selected_name",
            )
            column = next((name for name in candidates if name in reader.fieldnames), None)
            if column is None:
                raise ContractError(
                    f"views CSV lacks an image-name column {candidates}: {path}"
                )
            names = [str(row[column]).strip() for row in reader]
    except OSError as exc:
        raise ContractError(f"cannot read views CSV {path}: {exc}") from exc
    if not names or any(not name for name in names):
        raise ContractError(f"views CSV contains an empty or missing view: {path}")
    if len(names) != len(set(names)):
        raise ContractError(f"views CSV contains duplicate image names: {path}")
    return names


def _read_photo_mask_paths(
    repo: Path, index_path: Path, expected_names: Sequence[str]
) -> tuple[Path, dict[str, str]]:
    try:
        with index_path.open("r", encoding="utf-8", newline="") as stream:
            reader = csv.DictReader(stream)
            if not reader.fieldnames:
                raise ContractError(f"supervision index has no header: {index_path}")
            photo_column = "photo_support_mask_path"
            if photo_column not in reader.fieldnames:
                raise ContractError(
                    f"supervision index lacks {photo_column}: {index_path}"
                )
            name_column = next(
                (
                    name
                    for name in ("image_name", "view_name", "view", "image", "name")
                    if name in reader.fieldnames
                ),
                None,
            )
            if name_column is None:
                raise ContractError(
                    f"supervision index lacks an image-name column: {index_path}"
                )
            records = list(reader)
    except OSError as exc:
        raise ContractError(f"cannot read supervision index {index_path}: {exc}") from exc
    by_name = {
        str(row[name_column]).strip(): str(row[photo_column]).strip()
        for row in records
    }
    if list(by_name) != list(expected_names):
        if set(by_name) != set(expected_names):
            raise ContractError(
                "supervision index and selected view names do not have exact coverage"
            )
    resolved: dict[str, str] = {}
    parents: set[Path] = set()
    for name in expected_names:
        raw = by_name[name]
        mask = resolve_path(repo, raw, local_base=index_path.parent)
        if not mask.is_file():
            raise ContractError(f"missing photo support mask for {name}: {mask}")
        expected_filename = f"{Path(name).stem}.npy"
        require_equal(mask.name, expected_filename, f"photo mask filename for {name}")
        parents.add(mask.parent)
        resolved[name] = repo_relative(repo, mask)
    if len(parents) != 1:
        raise ContractError("photo support masks are not in one common directory")
    return next(iter(parents)), resolved


def validate_preprocess(
    repo: Path,
    config: Mapping[str, Any],
    building_id: str,
    *,
    hash_artifacts: bool = True,
) -> dict[str, Any]:
    """Validate and fully hash one passed §3 publication."""

    manifest_path = _manifest_path(repo, config, building_id)
    manifest, manifest_sha = load_json_snapshot(manifest_path)
    inputs = config["inputs"]
    require_equal(
        manifest.get("schema"),
        inputs.get("preprocess_building_schema", PREPROCESS_SCHEMA),
        "preprocess schema",
    )
    require_equal(
        manifest.get("status"),
        inputs["preprocess_required_status"],
        "preprocess status",
    )
    building = manifest.get("building")
    if not isinstance(building, Mapping):
        raise ContractError("preprocess building object is missing")
    require_equal(building.get("building_id"), building_id, "preprocess building ID")

    pose_binding = manifest.get("pose_binding")
    if not isinstance(pose_binding, Mapping):
        raise ContractError("preprocess pose_binding is missing")
    require_equal(
        pose_binding.get("corrected_images_sha256"),
        inputs["corrected_images_sha256"],
        "preprocess corrected pose SHA-256",
    )
    require_equal(
        pose_binding.get("r1_manifest_sha256"),
        inputs["r1_pose_manifest_sha256"],
        "preprocess R1 manifest SHA-256",
    )
    gate_binding = manifest.get("gate_binding")
    if not isinstance(gate_binding, Mapping):
        raise ContractError("preprocess gate_binding is missing")
    require_equal(
        gate_binding.get("r2_manifest_sha256"),
        inputs["r2_gate_manifest_sha256"],
        "preprocess R2 manifest SHA-256",
    )
    require_equal(
        gate_binding.get("status"),
        inputs["required_gate_status"],
        "preprocess Gate A status",
    )

    views = manifest.get("views")
    if not isinstance(views, Mapping) or not isinstance(views.get("csv"), Mapping):
        raise ContractError("preprocess views.csv binding is missing")
    views_path = resolve_path(
        repo, views["csv"]["path"], local_base=manifest_path.parent
    )
    require_equal(
        sha256_file(views_path),
        views["csv"].get("sha256"),
        "preprocess views CSV SHA-256",
    )
    manifest_selected_names = views.get("selected_names")
    if not isinstance(manifest_selected_names, list) or not all(
        isinstance(value, str) and value for value in manifest_selected_names
    ):
        raise ContractError("preprocess views.selected_names must be a string list")
    manifest_selected_names = list(manifest_selected_names)
    csv_selected_names = _read_view_names(views_path)
    require_equal(
        views.get("count"), len(manifest_selected_names), "preprocess view count"
    )
    if (
        len(csv_selected_names) != len(manifest_selected_names)
        or set(csv_selected_names) != set(manifest_selected_names)
    ):
        raise ContractError(
            "views CSV and manifest selected_names do not have exact membership"
        )
    # views.csv retains the pre-registered ranking/selection order whereas the
    # manifest inventory is sorted for equality checks. Preserve the CSV order
    # for the deterministic train/eval role split.
    selected_names = csv_selected_names
    minimum = int(config["view_contract"]["minimum_preprocess_views"])
    maximum = int(config["view_contract"]["maximum_preprocess_views"])
    if not minimum <= len(selected_names) <= maximum:
        raise ContractError(
            f"preprocess view count {len(selected_names)} is outside [{minimum},{maximum}]"
        )

    data_root_raw = manifest.get("data_root")
    if data_root_raw is None and isinstance(manifest.get("colmap_data_root"), str):
        data_root_raw = manifest["colmap_data_root"]
    if not isinstance(data_root_raw, str) or not data_root_raw:
        raise ContractError("preprocess colmap_data_root/data_root is missing")
    data_root = resolve_path(repo, data_root_raw, local_base=manifest_path.parent)
    for name in ("cameras.bin", "images.bin", "points3D.bin"):
        required = data_root / "sparse" / "0" / name
        if not required.is_file():
            raise ContractError(f"preprocess data root misses sparse file: {required}")
    # The per-building COLMAP model contains only the selected 10--30 image
    # records, so its images.bin is not byte-identical to R1's 937-view file.
    # Pose lineage is instead bound above by the preprocessor's R1 hash and the
    # entire subset images.bin is covered by artifact_sha256 below.
    subset_images_sha = sha256_file(data_root / "sparse/0/images.bin")
    for name in selected_names:
        required_paths = (
            data_root / "images" / name,
            data_root / "stereo/depth_maps" / f"{name}.geometric.bin",
            data_root / "stereo/normal_maps" / f"{name}.geometric.bin",
        )
        for required in required_paths:
            if not required.is_file():
                raise ContractError(f"preprocess data root misses view artifact: {required}")

    seed = manifest.get("seed")
    if not isinstance(seed, Mapping) or not isinstance(seed.get("canonical_npz"), Mapping):
        raise ContractError("preprocess seed.canonical_npz binding is missing")
    seed_path = resolve_path(
        repo, seed["canonical_npz"]["path"], local_base=manifest_path.parent
    )
    require_equal(
        sha256_file(seed_path),
        seed["canonical_npz"].get("sha256"),
        "canonical seed NPZ SHA-256",
    )

    supervision = manifest.get("supervision")
    if not isinstance(supervision, Mapping) or not isinstance(
        supervision.get("index"), Mapping
    ):
        raise ContractError("preprocess supervision.index binding is missing")
    supervision_index = resolve_path(
        repo, supervision["index"]["path"], local_base=manifest_path.parent
    )
    require_equal(
        sha256_file(supervision_index),
        supervision["index"].get("sha256"),
        "supervision index SHA-256",
    )
    photo_mask_dir, photo_masks = _read_photo_mask_paths(
        repo, supervision_index, selected_names
    )

    artifact_sha = manifest.get("artifact_sha256")
    if not isinstance(artifact_sha, Mapping) or not artifact_sha:
        raise ContractError("preprocess artifact_sha256 inventory is empty")
    verified_artifacts: dict[str, str] = {}
    if hash_artifacts:
        for raw_path, expected_sha in sorted(artifact_sha.items()):
            if not isinstance(raw_path, str) or not isinstance(expected_sha, str):
                raise ContractError("preprocess artifact_sha256 entries must be strings")
            path = resolve_path(repo, raw_path, local_base=manifest_path.parent)
            if not path.is_file():
                raise ContractError(f"preprocess inventory file is missing: {path}")
            observed = sha256_file(path)
            require_equal(observed, expected_sha, f"preprocess artifact SHA-256 {raw_path}")
            verified_artifacts[raw_path] = observed
    else:
        verified_artifacts = {
            str(raw_path): str(expected_sha)
            for raw_path, expected_sha in sorted(artifact_sha.items())
        }

    artifact_records_sha = sha256_bytes(canonical_json_bytes(verified_artifacts))
    full_snapshot_sha = sha256_bytes(
        canonical_json_bytes(
            {
                "manifest_sha256": manifest_sha,
                "artifact_records_sha256": artifact_records_sha,
            }
        )
    )
    return {
        "building_id": building_id,
        "manifest": repo_relative(repo, manifest_path),
        "manifest_sha256": manifest_sha,
        "full_snapshot_sha256": full_snapshot_sha,
        "artifact_records_sha256": artifact_records_sha,
        "artifact_count": len(verified_artifacts),
        "data_root": repo_relative(repo, data_root),
        "views_csv": repo_relative(repo, views_path),
        "selected_names": selected_names,
        "view_count": len(selected_names),
        "seed_canonical_npz": repo_relative(repo, seed_path),
        "seed_canonical_npz_sha256": sha256_file(seed_path),
        "supervision_index": repo_relative(repo, supervision_index),
        "photo_mask_dir": repo_relative(repo, photo_mask_dir),
        "photo_mask_paths": photo_masks,
        "corrected_images_sha256": inputs["corrected_images_sha256"],
        "subset_corrected_images_sha256": subset_images_sha,
    }


def split_views(
    selected_names: Sequence[str], view_contract: Mapping[str, Any]
) -> tuple[list[str], list[str]]:
    names = list(selected_names)
    reserve_at = int(view_contract["reserve_one_eval_when_total_at_least"])
    if len(names) >= reserve_at:
        train, evaluation = names[:-1], names[-1:]
    else:
        train, evaluation = names, []
    minimum = int(view_contract["minimum_training_views"])
    if len(train) < minimum or len(train) > int(
        view_contract["maximum_preprocess_views"]
    ):
        raise ContractError(
            f"training view count {len(train)} violates locked 10-30 contract"
        )
    if set(train) & set(evaluation):
        raise ContractError("train/eval view roles overlap")
    if train + evaluation != names:
        raise ContractError("train/eval roles do not preserve exact selected view order")
    return train, evaluation


def build_training_config(
    *,
    repo: Path,
    config: Mapping[str, Any],
    preprocess: Mapping[str, Any],
    arm: str,
    run: str,
    out_dir: Path,
) -> dict[str, Any]:
    if arm not in ARMS:
        raise ContractError(f"arm must be one of {ARMS}, got {arm!r}")
    if run not in RUNS:
        raise ContractError(f"run must be one of {RUNS}, got {run!r}")
    recipe = config["recipe"]
    train_views, eval_views = split_views(
        preprocess["selected_names"], config["view_contract"]
    )
    if arm == "A":
        w_depth = float(recipe["arm_A_depth_weight"])
        depth_final = float(recipe["arm_A_depth_final_weight"])
        w_normal = float(recipe["arm_A_normal_weight"])
        normal_final = float(recipe["arm_A_normal_final_weight"])
    else:
        w_depth = float(recipe["arm_B_depth_weight"])
        depth_final = float(recipe["arm_B_depth_final_weight"])
        w_normal = float(recipe["arm_B_normal_weight"])
        normal_final = float(recipe["arm_B_normal_final_weight"])

    def r(name: str) -> Any:
        return recipe[name]

    return {
        "seed": int(recipe["run_seeds"][run]),
        "device": "cuda",
        "data_root": container_path(repo, repo / preprocess["data_root"]),
        "out_dir": container_path(repo, out_dir),
        "init_pointcloud": container_path(
            repo, repo / preprocess["seed_canonical_npz"]
        ),
        "init_pointcloud_mode": r("init_pointcloud_mode"),
        "mvs_seed_init_opacity": float(r("mvs_seed_init_opacity")),
        "seed_protect": bool(r("seed_protect")),
        "seed_protect_until_iter": r("seed_protect_until_iter"),
        "visible_views": list(preprocess["selected_names"]),
        "train_views": train_views,
        "eval_views": eval_views,
        "photo_mask_dir": container_path(repo, repo / preprocess["photo_mask_dir"]),
        "downscale": float(r("downscale")),
        "sh_degree": int(r("sh_degree")),
        "sh_up_every": int(r("sh_up_every")),
        "w_photo": float(r("w_photo")),
        "photo_lam": float(r("photo_lam")),
        "load_depth": bool(r("load_depth")),
        "load_normal": bool(r("load_normal")),
        "depth_scale": float(r("depth_scale")),
        "w_depth": w_depth,
        "depth_schedule": r("depth_schedule"),
        "depth_warmup": int(r("depth_warmup")),
        "depth_ramp_steps": int(r("depth_ramp_steps")),
        "depth_final_weight": depth_final,
        "w_normal": w_normal,
        "normal_schedule": r("normal_schedule"),
        "normal_warmup": int(r("normal_warmup")),
        "normal_ramp_steps": int(r("normal_ramp_steps")),
        "normal_final_weight": normal_final,
        "w_nc": float(r("w_nc")),
        "w_distort": float(r("w_distort")),
        "distort_normalization": r("distort_normalization"),
        "distort_schedule": r("distort_schedule"),
        "distort_warmup": int(r("distort_warmup")),
        "distort_ramp_steps": int(r("distort_ramp_steps")),
        "load_semantic": bool(r("load_semantic")),
        "seed_semantic": bool(r("seed_semantic")),
        "w_sem": float(r("w_sem")),
        "w_mutual": float(r("w_mutual")),
        "w_structure": float(r("w_structure")),
        "w_mvc": float(r("w_mvc")),
        "w_plane": float(r("w_plane")),
        "w_mono_depth": float(r("w_mono_depth")),
        "w_mono_normal_aux": float(r("w_mono_normal_aux")),
        "w_semdepth_smooth": float(r("w_semdepth_smooth")),
        "w_semdepth_plane": float(r("w_semdepth_plane")),
        "w_boundary_normal": float(r("w_boundary_normal")),
        "lr_means": float(r("lr_means")),
        "lr_scales": float(r("lr_scales")),
        "lr_quats": float(r("lr_quats")),
        "lr_opacities": float(r("lr_opacities")),
        "lr_sh0": float(r("lr_sh0")),
        "lr_shN": float(r("lr_shN")),
        "prune_opa": float(r("prune_opa")),
        "grow_grad2d": float(r("grow_grad2d")),
        "grow_scale3d": float(r("grow_scale3d")),
        "prune_scale3d": float(r("prune_scale3d")),
        "refine_start_iter": int(r("refine_start_iter")),
        "refine_stop_iter": int(r("refine_stop_iter")),
        "refine_every": int(r("refine_every")),
        "reset_every": int(r("reset_every")),
        "max_iter": int(r("max_iter")),
        "eval_every": int(r("eval_every")),
        "ckpt_every": int(r("ckpt_every")),
        "full_state_checkpoint": bool(r("full_state_checkpoint")),
        "full_state_checkpoint_steps": list(r("full_state_checkpoint_steps")),
        "full_state_loss_csv_paths": list(r("full_state_loss_csv_paths")),
        "full_state_resume": r("full_state_resume"),
        "loss_grad_audit_every": int(r("loss_grad_audit_every")),
    }


def validate_ablation_pair(
    config_a: Mapping[str, Any], config_b: Mapping[str, Any]
) -> dict[str, Any]:
    keys = set(config_a) | set(config_b)
    differences = {
        key
        for key in keys
        if key not in config_a
        or key not in config_b
        or config_a.get(key) != config_b.get(key)
    }
    if differences != ABLATION_DIFFERENCES:
        raise ContractError(
            "arm A/B scientific configurations do not form the locked one-variable "
            f"ablation: differences={sorted(differences)}, "
            f"expected={sorted(ABLATION_DIFFERENCES)}"
        )
    for key in (
        "depth_schedule",
        "depth_warmup",
        "depth_ramp_steps",
        "normal_schedule",
        "normal_warmup",
        "normal_ramp_steps",
        "load_depth",
        "load_normal",
        "photo_mask_dir",
        "visible_views",
        "train_views",
        "eval_views",
    ):
        require_equal(config_a.get(key), config_b.get(key), f"A/B identical {key}")
    require_equal(config_a["w_depth"], 0.5, "arm A initial depth weight")
    require_equal(config_a["w_normal"], 0.05, "arm A initial normal weight")
    require_equal(config_b["w_depth"], 0.0, "arm B depth weight")
    require_equal(config_b["w_normal"], 0.0, "arm B normal weight")
    return {
        "status": "PASSED",
        "difference_keys": sorted(differences),
        "all_other_keys_identical": True,
        "schedule_metadata_identical": True,
        "maps_loaded_in_both_arms": True,
        "photo_support_masks_identical": True,
    }


def _run_git(repo: Path, *args: str) -> str:
    command = ["git", "-c", f"safe.directory={repo}", *args]
    completed = subprocess.run(
        command,
        cwd=repo,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if completed.returncode != 0:
        raise ContractError(
            f"git command failed ({' '.join(command)}): {completed.stderr.strip()}"
        )
    return completed.stdout.strip()


def validate_git_state(
    repo: Path,
    config: Mapping[str, Any],
    *,
    expected_head: str | None = None,
) -> dict[str, Any]:
    branch = _run_git(repo, "branch", "--show-current")
    head = _run_git(repo, "rev-parse", "HEAD")
    require_equal(branch, config["branch"], "git branch")
    if expected_head is not None:
        require_equal(head, expected_head, "launch HEAD vs materialization HEAD")
    ancestor = config["git_contract"]["required_ancestor"]
    ancestry = subprocess.run(
        [
            "git",
            "-c",
            f"safe.directory={repo}",
            "merge-base",
            "--is-ancestor",
            ancestor,
            head,
        ],
        cwd=repo,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    if ancestry.returncode != 0:
        raise ContractError(f"required training-core ancestor is absent: {ancestor}")

    porcelain = _run_git(repo, "status", "--porcelain=v1", "--untracked-files=all")
    allowed = tuple(config["git_contract"]["allowed_runtime_untracked_prefixes"])
    unexpected: list[str] = []
    allowed_untracked: list[str] = []
    for line in porcelain.splitlines():
        if not line:
            continue
        status = line[:2]
        raw_path = line[3:]
        if " -> " in raw_path:
            raw_path = raw_path.rsplit(" -> ", 1)[-1]
        if status == "??" and raw_path.startswith(allowed):
            allowed_untracked.append(raw_path)
        else:
            unexpected.append(line)
    if unexpected:
        raise ContractError(
            "worktree is not clean outside approved immutable/runtime publications: "
            + "; ".join(unexpected[:20])
        )
    return {
        "branch": branch,
        "head": head,
        "required_ancestor": ancestor,
        "required_ancestor_of_head": True,
        "unexpected_porcelain": [],
        "allowed_runtime_untracked_count": len(allowed_untracked),
    }


def job_dir(
    repo: Path,
    config: Mapping[str, Any],
    building_id: str,
    arm: str,
    run: str,
) -> Path:
    if re.fullmatch(r"DEBY_LOD2_[0-9]+", building_id) is None:
        raise ContractError(f"unsafe or noncanonical building ID: {building_id!r}")
    if arm not in ARMS or run not in RUNS:
        raise ContractError(f"invalid arm/run: {arm!r}/{run!r}")
    root = resolve_path(repo, config["outputs"]["training_root"])
    return root / "by_building" / building_id / f"arm_{arm}" / run


def require_docker_materializer() -> None:
    if not Path("/.dockerenv").exists():
        raise ContractError(
            "materialization must run in the pinned Docker environment via the wrapper"
        )


def materialize(
    *,
    repo: Path,
    config_path: Path,
    config: Mapping[str, Any],
    building_id: str,
    arm: str,
    run: str,
    require_docker: bool = True,
) -> dict[str, Any]:
    if require_docker:
        require_docker_materializer()
    git = validate_git_state(repo, config)
    cutoff_amendment = validate_cutoff_amendment(repo, config)
    bindings = validate_r1_r2(repo, config)
    preprocess = validate_preprocess(repo, config, building_id)
    target = job_dir(repo, config, building_id, arm, run)
    outputs = config["outputs"]
    receipt_names = (
        outputs["started_receipt"],
        outputs["completed_receipt"],
        outputs["failed_receipt"],
    )
    for name in receipt_names:
        if (target / name).exists():
            raise ContractError(f"job has a prior runtime receipt; refuse materialize: {name}")
    manifest_path = target / outputs["materialization_manifest"]
    resolved_path = target / outputs["resolved_config"]
    if manifest_path.exists() or resolved_path.exists():
        raise ContractError(
            "job was already materialized; refuse to overwrite immutable config"
        )

    # Use one identical placeholder output for the scientific A/B comparison.
    comparison_out = repo / config["outputs"]["training_root"] / "_ablation_compare"
    config_a = build_training_config(
        repo=repo,
        config=config,
        preprocess=preprocess,
        arm="A",
        run=run,
        out_dir=comparison_out,
    )
    config_b = build_training_config(
        repo=repo,
        config=config,
        preprocess=preprocess,
        arm="B",
        run=run,
        out_dir=comparison_out,
    )
    ablation = validate_ablation_pair(config_a, config_b)
    selected = build_training_config(
        repo=repo,
        config=config,
        preprocess=preprocess,
        arm=arm,
        run=run,
        out_dir=target,
    )
    target.mkdir(parents=True, exist_ok=True)
    resolved_text = yaml.safe_dump(
        selected,
        sort_keys=False,
        allow_unicode=True,
        default_flow_style=False,
    )
    atomic_text(resolved_path, resolved_text)
    resolved_sha = sha256_file(resolved_path)
    train_views, eval_views = split_views(
        preprocess["selected_names"], config["view_contract"]
    )
    config_sha = sha256_file(config_path)
    payload = {
        "schema": MATERIALIZATION_SCHEMA,
        "status": "PASSED",
        "created_at": utc_now(),
        "run_id": config["run_id"],
        "task_id": config["task_id"],
        "building_id": building_id,
        "arm": arm,
        "replicate": run,
        "seed": selected["seed"],
        "git": git,
        "driver_config": repo_relative(repo, config_path),
        "driver_config_sha256": config_sha,
        "cutoff_amendment": cutoff_amendment,
        "bindings": bindings,
        "preprocess": preprocess,
        "view_roles": {
            "visible_views": preprocess["selected_names"],
            "visible_n": len(preprocess["selected_names"]),
            "train_views": train_views,
            "train_n": len(train_views),
            "eval_views": eval_views,
            "eval_n": len(eval_views),
            "policy": (
                "reserve_last_selected_for_eval"
                if eval_views
                else "ten_selected_all_train_explicit_empty_eval"
            ),
        },
        "ablation_validation": ablation,
        "resolved_config": repo_relative(repo, resolved_path),
        "resolved_config_sha256": resolved_sha,
        "output_dir": repo_relative(repo, target),
        "runtime_receipts_present_at_publication": {
            name: False for name in receipt_names
        },
        "learning_runs_started": 0,
        "publication": {
            "resolved_config_written_first": True,
            "manifest_written_last": True,
            "actual_training_started": False,
        },
    }
    atomic_json(manifest_path, payload)
    return payload


def _materialization(
    repo: Path,
    config: Mapping[str, Any],
    building_id: str,
    arm: str,
    run: str,
) -> tuple[Path, dict[str, Any], str]:
    target = job_dir(repo, config, building_id, arm, run)
    path = target / config["outputs"]["materialization_manifest"]
    payload, digest = load_json_snapshot(path)
    require_equal(payload.get("schema"), MATERIALIZATION_SCHEMA, "materialization schema")
    require_equal(payload.get("status"), "PASSED", "materialization status")
    require_equal(payload.get("building_id"), building_id, "materialization building")
    require_equal(payload.get("arm"), arm, "materialization arm")
    require_equal(payload.get("replicate"), run, "materialization replicate")
    return path, payload, digest


def _probe_forbidden_processes(
    patterns: Sequence[str],
) -> dict[str, Any]:
    compiled = [re.compile(pattern, re.IGNORECASE) for pattern in patterns]
    process = subprocess.run(
        ["ps", "-eo", "pid=,args="],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if process.returncode != 0:
        raise ContractError(f"cannot inspect host processes: {process.stderr.strip()}")
    matches: list[str] = []
    for line in process.stdout.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        pid_text = stripped.split(None, 1)[0]
        if pid_text.isdigit() and int(pid_text) == os.getpid():
            continue
        if any(regex.search(stripped) for regex in compiled):
            matches.append(stripped)

    docker = subprocess.run(
        [
            "docker",
            "ps",
            "--format",
            "{{.ID}}\t{{.Image}}\t{{.Command}}\t{{.Names}}",
        ],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if docker.returncode != 0:
        raise ContractError(
            f"cannot inspect running Docker containers: {docker.stderr.strip()}"
        )
    docker_matches = [
        line
        for line in docker.stdout.splitlines()
        if any(regex.search(line) for regex in compiled)
    ]
    if matches or docker_matches:
        raise ContractError(
            "readout/Roofer/scoring process guard matched: "
            + "; ".join((matches + docker_matches)[:20])
        )
    return {
        "status": "PASSED",
        "host_matches": [],
        "docker_matches": [],
        "patterns": list(patterns),
    }


def _verify_image(image: str, expected_id: str) -> dict[str, str]:
    completed = subprocess.run(
        ["docker", "image", "inspect", image, "--format", "{{.Id}}"],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if completed.returncode != 0:
        raise ContractError(
            f"cannot inspect training image {image}: {completed.stderr.strip()}"
        )
    observed = completed.stdout.strip()
    require_equal(observed, expected_id, "training Docker image ID")
    return {"image": image, "image_id": observed}


def _cutoff_check(
    cutoff_iso: str,
    *,
    now: datetime | None = None,
    amendment: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    cutoff = datetime.fromisoformat(cutoff_iso)
    if cutoff.tzinfo is None:
        raise ContractError("cutoff timestamp must include an explicit UTC offset")
    observed = now or datetime.now(ZoneInfo("Asia/Seoul"))
    if observed.tzinfo is None:
        raise ContractError("observed launch time must be timezone-aware")
    reached = observed >= cutoff
    if reached and amendment is None:
        raise ContractError(
            f"new training launch is forbidden at/after cutoff: now={observed.isoformat()} "
            f"cutoff={cutoff.isoformat()}"
        )
    if amendment is not None:
        require_equal(amendment.get("status"), "PASSED", "validated cutoff amendment")
        require_equal(
            amendment.get("decision"),
            "ABOLISH_0630_CUTOFF",
            "validated cutoff amendment decision",
        )
        require_equal(
            amendment.get("original_cutoff_kst"),
            cutoff.isoformat(),
            "validated cutoff amendment original cutoff",
        )
    return {
        "status": "PASSED",
        "observed_at": observed.isoformat(),
        "cutoff": cutoff.isoformat(),
        "original_cutoff_reached": reached,
        "seconds_remaining": (
            (cutoff - observed).total_seconds() if not reached else None
        ),
        "seconds_since_original_cutoff": (
            (observed - cutoff).total_seconds() if reached else None
        ),
        "policy": (
            "HUMAN_AMENDMENT_ABOLISHED_CUTOFF"
            if amendment is not None
            else "ORIGINAL_CUTOFF"
        ),
        "amendment": dict(amendment) if amendment is not None else None,
    }


def docker_command(
    *,
    repo: Path,
    config: Mapping[str, Any],
    resolved_config: Path,
    gpu: int,
    job_key: str,
    extra_environment: Mapping[str, str] | None = None,
) -> list[str]:
    choices = tuple(int(value) for value in config["launch_contract"]["physical_gpu_choices"])
    if gpu not in choices:
        raise ContractError(f"physical GPU must be one of {choices}, got {gpu}")
    suffix = sha256_bytes(job_key.encode("utf-8"))[:12]
    name = f"jointbuildgs-fusw1-{suffix}"
    command = [
        "docker",
        "compose",
        "run",
        "--rm",
        "--no-deps",
        "-T",
        "--user",
        f"{os.getuid()}:{os.getgid()}",
        "--name",
        name,
        "-e",
        f"NVIDIA_VISIBLE_DEVICES={gpu}",
        "-e",
        f"CUDA_VISIBLE_DEVICES={config['launch_contract']['container_visible_gpu']}",
    ]
    for key, value in sorted((extra_environment or {}).items()):
        if re.fullmatch(r"[A-Z][A-Z0-9_]*", key) is None:
            raise ContractError(f"unsafe Docker environment key: {key!r}")
        command.extend(("-e", f"{key}={value}"))
    command.extend(
        [
        config["launch_contract"]["docker_service"],
        "python",
        "-m",
        "src.stage2.train",
        "--config",
        container_path(repo, resolved_config),
        ]
    )
    return command


def validate_retry_policy(
    repo: Path, policy_path: Path, config: Mapping[str, Any]
) -> tuple[dict[str, Any], str]:
    path = resolve_path(repo, str(policy_path))
    policy, digest = load_json_snapshot(path)
    require_equal(policy.get("schema"), RETRY_POLICY_SCHEMA, "retry policy schema")
    require_equal(policy.get("status"), "APPROVED", "retry policy status")
    require_equal(policy.get("run_id"), config.get("run_id"), "retry policy run ID")
    require_equal(policy.get("approved_by"), "김휘영", "retry policy approver")
    require_equal(
        policy.get("retry_kind"),
        "GSPLAT_JIT_CACHE_PERMISSION_PREOPTIMIZER",
        "retry policy kind",
    )
    require_equal(policy.get("maximum_retries_per_job"), 1, "retry maximum")
    materialization_head = policy.get("required_materialization_head")
    if not isinstance(materialization_head, str) or re.fullmatch(
        r"[0-9a-f]{40}", materialization_head
    ) is None:
        raise ContractError("retry required materialization HEAD is invalid")
    require_equal(
        policy.get("required_retry_commit_distance"), 1, "retry commit distance"
    )
    allowed_commit_paths = policy.get("allowed_retry_commit_paths")
    if not isinstance(allowed_commit_paths, list) or not allowed_commit_paths:
        raise ContractError("retry commit path allowlist is missing")
    require_equal(policy.get("attempt_directory"), "infra_retry_01", "retry directory")
    require_equal(
        policy.get("allowed_resolved_config_differences"),
        ["out_dir"],
        "retry resolved-config difference allowlist",
    )
    environment = policy.get("writable_environment")
    required_environment = {"HOME", "XDG_CACHE_HOME", "TORCH_EXTENSIONS_DIR"}
    if not isinstance(environment, Mapping) or set(environment) != required_environment:
        raise ContractError("retry writable environment must contain exactly HOME, XDG_CACHE_HOME, TORCH_EXTENSIONS_DIR")
    for key, value in environment.items():
        candidate = Path(str(value))
        if candidate.is_absolute() or ".." in candidate.parts or not candidate.parts:
            raise ContractError(f"unsafe retry environment path for {key}: {value!r}")
    preservation = policy.get("preservation_contract")
    if not isinstance(preservation, Mapping) or not all(
        preservation.get(key) is True
        for key in (
            "original_started_receipt_immutable",
            "original_failed_receipt_immutable",
            "original_log_immutable",
            "original_partial_outputs_immutable",
            "retry_receipts_exclusive",
            "retry_from_optimizer_step_zero",
        )
    ):
        raise ContractError("retry preservation contract is incomplete")
    required_failure = policy.get("required_failure")
    if not isinstance(required_failure, Mapping):
        raise ContractError("retry required failure contract is missing")
    artifact_sha256 = required_failure.get("artifact_sha256")
    required_artifacts = {"started", "failed", "log", "full_state"}
    if not isinstance(artifact_sha256, Mapping) or set(artifact_sha256) != required_artifacts:
        raise ContractError(
            "retry original artifact SHA-256 contract must contain exactly "
            "started, failed, log, full_state"
        )
    for label, digest_value in artifact_sha256.items():
        if not isinstance(digest_value, str) or re.fullmatch(
            r"[0-9a-f]{64}", digest_value
        ) is None:
            raise ContractError(
                f"retry original {label} SHA-256 is invalid: {digest_value!r}"
            )
    return {
        "path": repo_relative(repo, path),
        "sha256": digest,
        "schema": policy["schema"],
        "status": policy["status"],
        "run_id": policy["run_id"],
        "approved_by": policy["approved_by"],
        "approval_date_kst": policy.get("approval_date_kst"),
        "retry_kind": policy["retry_kind"],
        "required_materialization_head": materialization_head,
        "required_retry_commit_distance": 1,
        "allowed_retry_commit_paths": list(allowed_commit_paths),
        "maximum_retries_per_job": 1,
        "required_failure": {
            **dict(required_failure),
            "artifact_sha256": dict(artifact_sha256),
        },
        "attempt_directory": policy["attempt_directory"],
        "writable_environment": dict(environment),
        "allowed_resolved_config_differences": ["out_dir"],
        "preservation_contract": dict(preservation),
    }, digest


def _job_file_snapshot(target: Path, *, excluded_directory: str) -> dict[str, str]:
    snapshot: dict[str, str] = {}
    for path in sorted(target.rglob("*")):
        relative = path.relative_to(target)
        if relative.parts and relative.parts[0] == excluded_directory:
            continue
        if path.is_symlink():
            raise ContractError(f"retry source contains a symlink: {path}")
        if path.is_file():
            snapshot[str(relative)] = sha256_file(path)
    return snapshot


def _require_job_snapshot(
    target: Path, expected: Mapping[str, str], *, excluded_directory: str
) -> None:
    observed = _job_file_snapshot(target, excluded_directory=excluded_directory)
    require_equal(observed, dict(expected), "original failed-attempt file snapshot")


def _verify_preoptimizer_cache_failure(
    *,
    repo: Path,
    config: Mapping[str, Any],
    target: Path,
    materialization: Mapping[str, Any],
    materialization_sha256: str,
    policy: Mapping[str, Any],
) -> dict[str, Any]:
    outputs = config["outputs"]
    started_path = target / outputs["started_receipt"]
    failed_path = target / outputs["failed_receipt"]
    completed_path = target / outputs["completed_receipt"]
    log_path = target / outputs["job_log"]
    full_state_path = target / "full_state_manifest.json"
    if completed_path.exists() or completed_path.is_symlink():
        raise ContractError("infrastructure retry forbidden after a completion receipt")
    started, started_sha = load_json_snapshot(started_path)
    failed, failed_sha = load_json_snapshot(failed_path)
    full_state, full_state_sha = load_json_snapshot(full_state_path)
    require_equal(started.get("schema"), STARTED_SCHEMA, "original started schema")
    require_equal(failed.get("schema"), FAILED_SCHEMA, "original failed schema")
    require_equal(
        started.get("job_key"), failed.get("job_key"), "original failure job key"
    )
    require_equal(
        started.get("materialization_manifest_sha256"),
        materialization_sha256,
        "original started materialization SHA-256",
    )
    required = policy["required_failure"]
    pinned_sha256 = required["artifact_sha256"]
    require_equal(started_sha, pinned_sha256["started"], "original started SHA-256")
    require_equal(failed_sha, pinned_sha256["failed"], "original failed SHA-256")
    require_equal(
        full_state_sha,
        pinned_sha256["full_state"],
        "original full-state SHA-256",
    )
    require_equal(failed.get("return_code"), required["return_code"], "failure return code")
    log_sha = sha256_file(log_path)
    require_equal(log_sha, pinned_sha256["log"], "original training log SHA-256")
    require_equal(log_sha, failed.get("log_sha256"), "original failed log SHA-256")
    log_text = log_path.read_text(encoding="utf-8")
    for marker in required["log_markers"]:
        if marker not in log_text:
            raise ContractError(f"required infrastructure failure marker is absent: {marker}")
    require_equal(
        full_state.get("schema"),
        "jointbuildgs.stage2.resume_manifest.v1",
        "preoptimizer full-state schema",
    )
    for key in ("learning_runs_started", "last_completed_steps", "start_completed_steps"):
        require_equal(full_state.get(key), 0, f"preoptimizer {key}")
    require_equal(
        full_state.get("learning_runs_incremented_this_process"),
        False,
        "preoptimizer learning-run increment",
    )
    require_equal(
        full_state.get("latest_full_checkpoint"),
        required["latest_full_checkpoint"],
        "preoptimizer latest checkpoint",
    )
    checkpoint_files = [path for path in (target / "ckpt").rglob("*") if path.is_file()] if (target / "ckpt").exists() else []
    if checkpoint_files:
        raise ContractError(f"preoptimizer retry found checkpoint files: {checkpoint_files[:3]}")
    loss_files = [
        target / "audit/loss_grad_norms.csv",
        target / "audit/semantic_geometry.csv",
        target / "audit/semantic_target_observations.csv",
    ]
    existing_loss = [path for path in loss_files if path.exists() or path.is_symlink()]
    if existing_loss:
        raise ContractError(f"preoptimizer retry found loss CSV files: {existing_loss}")
    attempt_name = str(policy["attempt_directory"])
    attempt = target / attempt_name
    if attempt.exists() or attempt.is_symlink():
        raise ContractError("the one permitted infrastructure retry was already claimed")
    snapshot = _job_file_snapshot(target, excluded_directory=attempt_name)
    return {
        "started": {"path": repo_relative(repo, started_path), "sha256": started_sha},
        "failed": {"path": repo_relative(repo, failed_path), "sha256": failed_sha},
        "log": {"path": repo_relative(repo, log_path), "sha256": log_sha},
        "full_state": {
            "path": repo_relative(repo, full_state_path),
            "sha256": full_state_sha,
            "learning_runs_started": 0,
            "last_completed_steps": 0,
            "latest_full_checkpoint": None,
        },
        "checkpoint_files": 0,
        "loss_csv_files": 0,
        "original_file_snapshot": snapshot,
        "original_file_snapshot_sha256": sha256_bytes(canonical_json_bytes(snapshot)),
    }


def _validate_retry_git_state(
    repo: Path,
    config: Mapping[str, Any],
    materialization: Mapping[str, Any],
    policy: Mapping[str, Any],
) -> dict[str, Any]:
    git = validate_git_state(repo, config)
    original_head = materialization.get("git", {}).get("head")
    require_equal(
        original_head,
        policy["required_materialization_head"],
        "retry materialization HEAD",
    )
    current_head = git["head"]
    _run_git(repo, "merge-base", "--is-ancestor", original_head, current_head)
    distance_text = _run_git(repo, "rev-list", "--count", f"{original_head}..{current_head}")
    try:
        distance = int(distance_text)
    except ValueError as exc:
        raise ContractError(f"invalid retry commit distance: {distance_text!r}") from exc
    require_equal(
        distance, policy["required_retry_commit_distance"], "retry commit distance"
    )
    observed_paths = sorted(
        line
        for line in _run_git(repo, "diff", "--name-only", original_head, current_head).splitlines()
        if line
    )
    require_equal(
        observed_paths,
        sorted(policy["allowed_retry_commit_paths"]),
        "retry implementation commit paths",
    )
    return {
        **git,
        "materialization_head": original_head,
        "retry_head": current_head,
        "commit_distance": distance,
        "changed_paths": observed_paths,
    }


def _prepare_retry_attempt(
    *,
    repo: Path,
    target: Path,
    resolved: Path,
    policy: Mapping[str, Any],
) -> tuple[Path, Path, dict[str, str], dict[str, Any]]:
    attempt = target / str(policy["attempt_directory"])
    attempt.mkdir(parents=True, exist_ok=False)
    try:
        original = yaml.safe_load(resolved.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise ContractError(f"cannot load original resolved config for retry: {exc}") from exc
    if not isinstance(original, Mapping):
        raise ContractError("original resolved config root is not a mapping")
    retry_config = dict(original)
    if "out" in retry_config:
        raise ContractError("resolved training config contains noncanonical output key 'out'")
    if "out_dir" not in retry_config:
        raise ContractError("resolved training config is missing canonical output key 'out_dir'")
    original_out = retry_config.get("out_dir")
    retry_config["out_dir"] = container_path(repo, attempt)
    difference_keys = sorted(
        key
        for key in set(original) | set(retry_config)
        if original.get(key) != retry_config.get(key)
    )
    require_equal(
        difference_keys,
        policy["allowed_resolved_config_differences"],
        "infrastructure retry resolved-config differences",
    )
    retry_resolved = attempt / "resolved_config.yaml"
    atomic_text(
        retry_resolved,
        yaml.safe_dump(
            retry_config,
            sort_keys=False,
            allow_unicode=True,
            default_flow_style=False,
        ),
    )
    environment: dict[str, str] = {}
    environment_paths: dict[str, str] = {}
    for key, relative in policy["writable_environment"].items():
        path = (attempt / str(relative)).resolve()
        try:
            path.relative_to(attempt.resolve())
        except ValueError as exc:
            raise ContractError(f"retry environment escapes attempt directory: {key}") from exc
        path.mkdir(parents=True, exist_ok=False)
        environment[key] = container_path(repo, path)
        environment_paths[key] = repo_relative(repo, path)
    provenance = {
        "original_resolved_config": repo_relative(repo, resolved),
        "original_resolved_config_sha256": sha256_file(resolved),
        "retry_resolved_config": repo_relative(repo, retry_resolved),
        "retry_resolved_config_sha256": sha256_file(retry_resolved),
        "difference_keys": difference_keys,
        "original_out": original_out,
        "retry_out": retry_config["out_dir"],
        "seed": retry_config.get("seed"),
        "max_iter": retry_config.get("max_iter"),
        "environment_paths": environment_paths,
    }
    return attempt, retry_resolved, environment, provenance


def _counter_update(
    repo: Path,
    config: Mapping[str, Any],
    job_key: str,
    transition: str,
    extra: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    outputs = config["outputs"]
    root = resolve_path(repo, outputs["training_root"])
    path = root / outputs["aggregate_runtime_counter"]
    lock_path = root / outputs["aggregate_runtime_counter_lock"]
    root.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+", encoding="utf-8") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        if path.exists():
            payload, _ = load_json_snapshot(path)
            require_equal(payload.get("schema"), COUNTER_SCHEMA, "runtime counter schema")
        else:
            payload = {
                "schema": COUNTER_SCHEMA,
                "run_id": config["run_id"],
                "jobs_claimed": 0,
                "docker_processes_started": 0,
                "jobs_completed": 0,
                "jobs_failed": 0,
                "by_job": {},
            }
        counts = {
            "claimed": "jobs_claimed",
            "docker_started": "docker_processes_started",
            "completed": "jobs_completed",
            "failed": "jobs_failed",
            "infra_retry_claimed": "infrastructure_retries_claimed",
            "infra_retry_failed": "infrastructure_retries_failed",
        }
        if transition == "infra_retry_docker_started":
            payload["docker_processes_started"] = int(
                payload.get("docker_processes_started", 0)
            ) + 1
            payload["infrastructure_retry_docker_processes_started"] = int(
                payload.get("infrastructure_retry_docker_processes_started", 0)
            ) + 1
            counter_key = None
        else:
            counter_key = counts.get(transition)
        if counter_key is None and transition != "infra_retry_docker_started":
            raise ContractError(f"unknown runtime counter transition: {transition}")
        if counter_key is not None:
            payload[counter_key] = int(payload.get(counter_key, 0)) + 1
        by_job = payload.setdefault("by_job", {})
        record = dict(by_job.get(job_key, {}))
        record["state"] = transition
        record[f"{transition}_at"] = utc_now()
        if extra:
            record.update(extra)
        history = list(record.get("transition_history", []))
        history.append({"transition": transition, "at": utc_now()})
        record["transition_history"] = history
        by_job[job_key] = record
        payload["updated_at"] = utc_now()
        atomic_json(path, payload)
        fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
    return payload


def _loss_share_source_rows(
    *,
    source: Path,
    building_id: str,
    arm: str,
    run: str,
    seed: int,
    materialization_sha256: str,
) -> tuple[list[dict[str, str]], str]:
    try:
        raw = source.read_bytes()
        text = raw.decode("utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise ContractError(f"cannot read loss-share source {source}: {exc}") from exc
    source_sha = sha256_bytes(raw)
    reader = csv.DictReader(io.StringIO(text))
    required = {
        "step",
        "component",
        "raw_loss",
        "weight",
        "weighted_loss",
        "weighted_loss_share",
        "grad_norm",
        "grad_norm_share",
        "grad_status",
        "total_loss",
        "psnr_train",
        "n_primitives",
    }
    if reader.fieldnames is None or not required.issubset(reader.fieldnames):
        raise ContractError(
            f"loss-share source header mismatch: observed={reader.fieldnames}, "
            f"required={sorted(required)}"
        )
    output: list[dict[str, str]] = []
    identities: set[tuple[int, str]] = set()
    previous_step = -1
    for source_row in reader:
        try:
            step = int(source_row["step"])
        except (TypeError, ValueError) as exc:
            raise ContractError(f"invalid loss-share step: {source_row.get('step')!r}") from exc
        term = str(source_row["component"])
        if not term:
            raise ContractError("loss-share source contains an empty component")
        identity = (step, term)
        if identity in identities:
            raise ContractError(f"duplicate loss-share source row: {identity}")
        identities.add(identity)
        if step < previous_step:
            raise ContractError("loss-share source steps are not monotonic")
        previous_step = step
        output.append(
            {
                "building_id": building_id,
                "arm": arm,
                "run": run,
                "seed": str(seed),
                "step": str(step),
                "term": term,
                "raw_loss": str(source_row["raw_loss"]),
                "weight": str(source_row["weight"]),
                "weighted_loss": str(source_row["weighted_loss"]),
                "weighted_loss_share": str(source_row["weighted_loss_share"]),
                "grad_norm": str(source_row["grad_norm"]),
                "grad_norm_share": str(source_row["grad_norm_share"]),
                "grad_status": str(source_row["grad_status"]),
                "total_loss": str(source_row["total_loss"]),
                "psnr_train": str(source_row["psnr_train"]),
                "n_primitives": str(source_row["n_primitives"]),
                "denominator_role": str(source_row.get("denominator_role", "")),
                "source_csv_sha256": source_sha,
                "materialization_sha256": materialization_sha256,
            }
        )
    if not output:
        raise ContractError(f"loss-share source contains no data rows: {source}")
    output.sort(key=lambda row: (int(row["step"]), row["term"]))
    return output, source_sha


def aggregate_loss_shares(
    *,
    repo: Path,
    config: Mapping[str, Any],
    building_id: str,
    arm: str,
    run: str,
    training_output_dir: Path | None = None,
) -> dict[str, Any]:
    """Append one completed job to the fixed W1 loss-share CSV atomically.

    Repeating the operation for the same immutable source is idempotent. A
    different row set for an already aggregated job fails closed.
    """

    job_target = job_dir(repo, config, building_id, arm, run)
    target = training_output_dir or job_target
    repo_relative(repo, target)
    outputs = config["outputs"]
    materialization_path, materialization, materialization_sha = _materialization(
        repo, config, building_id, arm, run
    )
    source = target / "audit" / "loss_grad_norms.csv"
    job_rows, source_sha = _loss_share_source_rows(
        source=source,
        building_id=building_id,
        arm=arm,
        run=run,
        seed=int(materialization["seed"]),
        materialization_sha256=materialization_sha,
    )
    aggregate_path = resolve_path(repo, outputs["loss_share_csv"])
    lock_path = resolve_path(repo, outputs["loss_share_csv_lock"])
    receipt_path = target / outputs["loss_share_aggregation_receipt"]
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    job_identity = (building_id, arm, run)
    with lock_path.open("a+", encoding="utf-8") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        existing: list[dict[str, str]] = []
        if aggregate_path.exists():
            try:
                with aggregate_path.open("r", encoding="utf-8", newline="") as stream:
                    reader = csv.DictReader(stream)
                    require_equal(
                        reader.fieldnames,
                        list(LOSS_SHARE_FIELDS),
                        "w1_loss_shares.csv header",
                    )
                    existing = [dict(row) for row in reader]
            except OSError as exc:
                raise ContractError(
                    f"cannot read aggregate loss-share CSV {aggregate_path}: {exc}"
                ) from exc
        existing_job = [
            row
            for row in existing
            if (row["building_id"], row["arm"], row["run"]) == job_identity
        ]
        if existing_job:
            if existing_job != job_rows:
                raise ContractError(
                    f"aggregate loss-share rows drifted for completed job {job_identity}"
                )
            append_performed = False
            combined = existing
        else:
            append_performed = True
            combined = existing + job_rows
            combined.sort(
                key=lambda row: (
                    row["building_id"],
                    row["arm"],
                    row["run"],
                    int(row["step"]),
                    row["term"],
                )
            )
            atomic_csv(aggregate_path, combined, LOSS_SHARE_FIELDS)
        aggregate_sha = sha256_file(aggregate_path)
        job_rows_sha = sha256_bytes(canonical_json_bytes(job_rows))
        receipt = {
            "schema": "jointbuildgs.fusion_w1.loss_share_aggregation.v1",
            "status": "PASSED",
            "created_at": utc_now(),
            "run_id": config["run_id"],
            "building_id": building_id,
            "arm": arm,
            "replicate": run,
            "seed": int(materialization["seed"]),
            "source_csv": repo_relative(repo, source),
            "source_csv_sha256": source_sha,
            "source_rows": len(job_rows),
            "job_rows_sha256": job_rows_sha,
            "aggregate_csv": repo_relative(repo, aggregate_path),
            "aggregate_rows_after_operation": len(combined),
            "aggregate_sha256_after_operation": aggregate_sha,
            "append_performed": append_performed,
            "idempotent_existing_rows": not append_performed,
            "materialization_manifest": repo_relative(repo, materialization_path),
            "materialization_manifest_sha256": materialization_sha,
            "lock": repo_relative(repo, lock_path),
            "publication": {
                "aggregate_csv_atomic_replace": append_performed,
                "aggregation_executed_under_flock": True,
                "receipt_written_after_csv": True,
            },
        }
        if receipt_path.exists():
            prior, _ = load_json_snapshot(receipt_path)
            require_equal(
                prior.get("job_rows_sha256"),
                job_rows_sha,
                "prior loss-share aggregation job rows SHA-256",
            )
        atomic_json(receipt_path, receipt)
        fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
    return receipt


def _verify_training_completion(
    target: Path, maximum: int, *, repo: Path | None = None
) -> dict[str, Any]:
    manifest_path = target / "full_state_manifest.json"
    manifest, manifest_sha = load_json_snapshot(manifest_path)
    require_equal(
        manifest.get("schema"),
        "jointbuildgs.stage2.resume_manifest.v1",
        "trainer full-state schema",
    )
    require_equal(manifest.get("process_completed"), True, "trainer completion flag")
    require_equal(
        manifest.get("process_completed_steps"),
        maximum,
        "trainer completed optimizer updates",
    )
    checkpoint = target / "ckpt" / f"step_{maximum:06d}.pt"
    sidecar = Path(f"{checkpoint}.sha256")
    final_checkpoint = target / "ckpt" / "final.pt"
    loss_csv = target / "audit" / "loss_grad_norms.csv"
    for path in (checkpoint, sidecar, final_checkpoint, loss_csv):
        if not path.is_file() or path.stat().st_size <= 0:
            raise ContractError(f"completed trainer output is missing/empty: {path}")
    sidecar_match = re.fullmatch(
        r"([0-9a-f]{64})  (step_[0-9]{6}\.pt)\n?",
        sidecar.read_text(encoding="utf-8"),
    )
    if sidecar_match is None:
        raise ContractError(f"invalid full-state checkpoint sidecar: {sidecar}")
    require_equal(sidecar_match.group(2), checkpoint.name, "checkpoint sidecar filename")
    checkpoint_sha = sha256_file(checkpoint)
    require_equal(
        checkpoint_sha, sidecar_match.group(1), "30k full-state checkpoint SHA-256"
    )
    def published_path(path: Path) -> str:
        return repo_relative(repo, path) if repo is not None else str(path)

    return {
        "status": "PASSED",
        "full_state_manifest": published_path(manifest_path),
        "full_state_manifest_sha256": manifest_sha,
        "completed_optimizer_updates": maximum,
        "checkpoint": published_path(checkpoint),
        "checkpoint_sha256": checkpoint_sha,
        "final_checkpoint": published_path(final_checkpoint),
        "final_checkpoint_sha256": sha256_file(final_checkpoint),
        "loss_share_csv": published_path(loss_csv),
        "loss_share_csv_sha256": sha256_file(loss_csv),
    }


def launch(
    *,
    repo: Path,
    config_path: Path,
    config: Mapping[str, Any],
    building_id: str,
    arm: str,
    run: str,
    gpu: int,
    now: datetime | None = None,
    popen_factory: Callable[..., Any] = subprocess.Popen,
) -> dict[str, Any]:
    target = job_dir(repo, config, building_id, arm, run)
    outputs = config["outputs"]
    materialization_path, materialization, materialization_sha = _materialization(
        repo, config, building_id, arm, run
    )
    expected_head = materialization["git"]["head"]
    git = validate_git_state(repo, config, expected_head=expected_head)
    require_equal(
        sha256_file(config_path),
        materialization["driver_config_sha256"],
        "driver config SHA-256 since materialization",
    )
    cutoff_amendment = validate_cutoff_amendment(repo, config)
    require_equal(
        cutoff_amendment,
        materialization.get("cutoff_amendment"),
        "cutoff amendment snapshot since materialization",
    )
    bindings = validate_r1_r2(repo, config)
    require_equal(bindings, materialization["bindings"], "R1/R2 binding snapshot")
    preprocess = validate_preprocess(repo, config, building_id)
    require_equal(
        preprocess["manifest_sha256"],
        materialization["preprocess"]["manifest_sha256"],
        "preprocess manifest SHA-256 since materialization",
    )
    require_equal(
        preprocess["full_snapshot_sha256"],
        materialization["preprocess"]["full_snapshot_sha256"],
        "preprocess full publication SHA-256 since materialization",
    )
    resolved = target / outputs["resolved_config"]
    require_equal(
        sha256_file(resolved),
        materialization["resolved_config_sha256"],
        "resolved training config SHA-256",
    )
    cutoff = _cutoff_check(
        config["launch_contract"]["cutoff_kst"],
        now=now,
        amendment=cutoff_amendment,
    )
    process_guard = _probe_forbidden_processes(
        config["launch_contract"]["forbidden_process_patterns"]
    )
    image = _verify_image(
        config["launch_contract"]["docker_image"],
        config["launch_contract"]["docker_image_id"],
    )
    for name in (
        outputs["started_receipt"],
        outputs["completed_receipt"],
        outputs["failed_receipt"],
    ):
        if (target / name).exists():
            raise ContractError(f"job output has a prior runtime receipt: {name}")

    job_key = f"{building_id}/arm_{arm}/{run}"
    command = docker_command(
        repo=repo,
        config=config,
        resolved_config=resolved,
        gpu=gpu,
        job_key=job_key,
    )
    started_path = target / outputs["started_receipt"]
    started_payload = {
        "schema": STARTED_SCHEMA,
        "run_id": config["run_id"],
        "job_key": job_key,
        "building_id": building_id,
        "arm": arm,
        "replicate": run,
        "seed": materialization["seed"],
        "started_at": utc_now(),
        "physical_gpu": gpu,
        "container_cuda_visible_devices": config["launch_contract"][
            "container_visible_gpu"
        ],
        "command": command,
        "git": git,
        "cutoff_gate": cutoff,
        "process_guard": process_guard,
        "docker_image": image,
        "materialization_manifest": repo_relative(repo, materialization_path),
        "materialization_manifest_sha256": materialization_sha,
        "resolved_config_sha256": materialization["resolved_config_sha256"],
        "preprocess_full_snapshot_sha256": preprocess["full_snapshot_sha256"],
        "prior_started_receipt": False,
        "claim_mode": "atomic_O_EXCL",
    }
    exclusive_json(started_path, started_payload)
    _counter_update(repo, config, job_key, "claimed", {"physical_gpu": gpu})

    log_path = target / outputs["job_log"]
    launch_started = time.monotonic()
    return_code: int | None = None
    docker_pid: int | None = None
    try:
        with log_path.open("a", encoding="utf-8", buffering=1) as log:
            process = popen_factory(
                command,
                cwd=repo,
                stdout=log,
                stderr=subprocess.STDOUT,
                text=True,
            )
            docker_pid = int(process.pid)
            _counter_update(
                repo,
                config,
                job_key,
                "docker_started",
                {"docker_compose_pid": docker_pid},
            )
            return_code = int(process.wait())
        elapsed = time.monotonic() - launch_started
        if return_code != 0:
            raise ContractError(f"Docker training exited with code {return_code}")
        completion = _verify_training_completion(
            target, int(config["recipe"]["max_iter"]), repo=repo
        )
        loss_share_aggregation = aggregate_loss_shares(
            repo=repo,
            config=config,
            building_id=building_id,
            arm=arm,
            run=run,
        )
        loss_share_receipt_path = (
            target / outputs["loss_share_aggregation_receipt"]
        )
        completed_payload = {
            "schema": COMPLETED_SCHEMA,
            "run_id": config["run_id"],
            "job_key": job_key,
            "building_id": building_id,
            "arm": arm,
            "replicate": run,
            "seed": materialization["seed"],
            "completed_at": utc_now(),
            "return_code": return_code,
            "elapsed_seconds": elapsed,
            "docker_compose_pid": docker_pid,
            "started_receipt": {
                "path": repo_relative(repo, started_path),
                "sha256": sha256_file(started_path),
            },
            "materialization": {
                "path": repo_relative(repo, materialization_path),
                "sha256": materialization_sha,
                "resolved_config": materialization["resolved_config"],
                "resolved_config_sha256": materialization[
                    "resolved_config_sha256"
                ],
            },
            "pose_gate_binding": materialization["bindings"],
            "preprocess_binding": {
                "manifest": materialization["preprocess"]["manifest"],
                "manifest_sha256": materialization["preprocess"][
                    "manifest_sha256"
                ],
                "full_snapshot_sha256": materialization["preprocess"][
                    "full_snapshot_sha256"
                ],
                "seed_canonical_npz": materialization["preprocess"][
                    "seed_canonical_npz"
                ],
                "seed_canonical_npz_sha256": materialization["preprocess"][
                    "seed_canonical_npz_sha256"
                ],
            },
            "training_completion": completion,
            "loss_share_aggregation": {
                "receipt": repo_relative(repo, loss_share_receipt_path),
                "receipt_sha256": sha256_file(loss_share_receipt_path),
                "source_rows": loss_share_aggregation["source_rows"],
                "aggregate_rows_after_operation": loss_share_aggregation[
                    "aggregate_rows_after_operation"
                ],
                "aggregate_sha256_after_operation": loss_share_aggregation[
                    "aggregate_sha256_after_operation"
                ],
            },
            "log": repo_relative(repo, log_path),
            "log_sha256": sha256_file(log_path),
        }
        exclusive_json(target / outputs["completed_receipt"], completed_payload)
        _counter_update(
            repo,
            config,
            job_key,
            "completed",
            {"elapsed_seconds": elapsed},
        )
        return completed_payload
    except BaseException as exc:
        elapsed = time.monotonic() - launch_started
        failed_payload = {
            "schema": FAILED_SCHEMA,
            "run_id": config["run_id"],
            "job_key": job_key,
            "failed_at": utc_now(),
            "return_code": return_code,
            "elapsed_seconds": elapsed,
            "docker_compose_pid": docker_pid,
            "error_type": type(exc).__name__,
            "reason": str(exc),
            "log": repo_relative(repo, log_path),
            "log_sha256": sha256_file(log_path) if log_path.is_file() else None,
            "partial_outputs_preserved": True,
        }
        failed_path = target / outputs["failed_receipt"]
        if not failed_path.exists():
            exclusive_json(failed_path, failed_payload)
        _counter_update(
            repo,
            config,
            job_key,
            "failed",
            {"elapsed_seconds": elapsed, "reason": str(exc)},
        )
        raise


def retry_infrastructure_failure(
    *,
    repo: Path,
    config_path: Path,
    config: Mapping[str, Any],
    policy_path: Path,
    building_id: str,
    arm: str,
    run: str,
    gpu: int,
    now: datetime | None = None,
    popen_factory: Callable[..., Any] = subprocess.Popen,
) -> dict[str, Any]:
    """Run the single approved pre-optimizer infrastructure retry."""

    target = job_dir(repo, config, building_id, arm, run)
    outputs = config["outputs"]
    materialization_path, materialization, materialization_sha = _materialization(
        repo, config, building_id, arm, run
    )
    require_equal(
        sha256_file(config_path),
        materialization["driver_config_sha256"],
        "original driver config SHA-256 for infrastructure retry",
    )
    policy, _ = validate_retry_policy(repo, policy_path, config)
    git = _validate_retry_git_state(repo, config, materialization, policy)
    cutoff_amendment = validate_cutoff_amendment(repo, config)
    require_equal(
        cutoff_amendment,
        materialization.get("cutoff_amendment"),
        "cutoff amendment snapshot for infrastructure retry",
    )
    bindings = validate_r1_r2(repo, config)
    require_equal(bindings, materialization["bindings"], "retry R1/R2 binding snapshot")
    preprocess = validate_preprocess(repo, config, building_id)
    require_equal(
        preprocess["full_snapshot_sha256"],
        materialization["preprocess"]["full_snapshot_sha256"],
        "retry preprocess full publication SHA-256",
    )
    resolved = target / outputs["resolved_config"]
    require_equal(
        sha256_file(resolved),
        materialization["resolved_config_sha256"],
        "original resolved config SHA-256 for infrastructure retry",
    )
    cutoff = _cutoff_check(
        config["launch_contract"]["cutoff_kst"],
        now=now,
        amendment=cutoff_amendment,
    )
    eligibility = _verify_preoptimizer_cache_failure(
        repo=repo,
        config=config,
        target=target,
        materialization=materialization,
        materialization_sha256=materialization_sha,
        policy=policy,
    )
    process_guard = _probe_forbidden_processes(
        config["launch_contract"]["forbidden_process_patterns"]
    )
    image = _verify_image(
        config["launch_contract"]["docker_image"],
        config["launch_contract"]["docker_image_id"],
    )
    attempt, retry_resolved, environment, retry_config = _prepare_retry_attempt(
        repo=repo,
        target=target,
        resolved=resolved,
        policy=policy,
    )
    require_equal(retry_config["seed"], materialization["seed"], "retry seed")
    require_equal(
        retry_config["max_iter"], config["recipe"]["max_iter"], "retry max_iter"
    )
    job_key = f"{building_id}/arm_{arm}/{run}"
    retry_key = f"{job_key}/{policy['attempt_directory']}"
    command = docker_command(
        repo=repo,
        config=config,
        resolved_config=retry_resolved,
        gpu=gpu,
        job_key=retry_key,
        extra_environment=environment,
    )
    retry_started_path = attempt / "retry_started.json"
    retry_started = {
        "schema": RETRY_STARTED_SCHEMA,
        "run_id": config["run_id"],
        "job_key": job_key,
        "retry_key": retry_key,
        "building_id": building_id,
        "arm": arm,
        "replicate": run,
        "seed": materialization["seed"],
        "started_at": utc_now(),
        "physical_gpu": gpu,
        "command": command,
        "git": git,
        "cutoff_gate": cutoff,
        "process_guard": process_guard,
        "docker_image": image,
        "policy": policy,
        "materialization": {
            "path": repo_relative(repo, materialization_path),
            "sha256": materialization_sha,
        },
        "original_failure": eligibility,
        "retry_config": retry_config,
        "environment": environment,
        "optimizer_restart_completed_steps": 0,
        "claim_mode": "atomic_O_EXCL_one_time_infrastructure_retry",
    }
    exclusive_json(retry_started_path, retry_started)
    _counter_update(
        repo,
        config,
        job_key,
        "infra_retry_claimed",
        {
            "retry_key": retry_key,
            "retry_started_receipt": repo_relative(repo, retry_started_path),
            "physical_gpu": gpu,
        },
    )
    retry_log = attempt / outputs["job_log"]
    launch_started = time.monotonic()
    return_code: int | None = None
    docker_pid: int | None = None
    try:
        with retry_log.open("x", encoding="utf-8", buffering=1) as log:
            process = popen_factory(
                command,
                cwd=repo,
                stdout=log,
                stderr=subprocess.STDOUT,
                text=True,
            )
            docker_pid = int(process.pid)
            _counter_update(
                repo,
                config,
                job_key,
                "infra_retry_docker_started",
                {"retry_key": retry_key, "docker_compose_pid": docker_pid},
            )
            return_code = int(process.wait())
        elapsed = time.monotonic() - launch_started
        if return_code != 0:
            raise ContractError(f"Docker infrastructure retry exited with code {return_code}")
        completion = _verify_training_completion(
            attempt, int(config["recipe"]["max_iter"]), repo=repo
        )
        loss_share_aggregation = aggregate_loss_shares(
            repo=repo,
            config=config,
            building_id=building_id,
            arm=arm,
            run=run,
            training_output_dir=attempt,
        )
        _require_job_snapshot(
            target,
            eligibility["original_file_snapshot"],
            excluded_directory=str(policy["attempt_directory"]),
        )
        retry_completed_path = attempt / "retry_completed.json"
        retry_completed = {
            "schema": RETRY_COMPLETED_SCHEMA,
            "run_id": config["run_id"],
            "job_key": job_key,
            "retry_key": retry_key,
            "completed_at": utc_now(),
            "return_code": return_code,
            "elapsed_seconds": elapsed,
            "docker_compose_pid": docker_pid,
            "retry_started_receipt": {
                "path": repo_relative(repo, retry_started_path),
                "sha256": sha256_file(retry_started_path),
            },
            "original_failure_snapshot_sha256": eligibility[
                "original_file_snapshot_sha256"
            ],
            "training_completion": completion,
            "loss_share_aggregation": loss_share_aggregation,
            "log": repo_relative(repo, retry_log),
            "log_sha256": sha256_file(retry_log),
        }
        exclusive_json(retry_completed_path, retry_completed)
        completed_payload = {
            "schema": COMPLETED_SCHEMA,
            "run_id": config["run_id"],
            "job_key": job_key,
            "building_id": building_id,
            "arm": arm,
            "replicate": run,
            "seed": materialization["seed"],
            "completed_at": retry_completed["completed_at"],
            "return_code": return_code,
            "elapsed_seconds": elapsed,
            "docker_compose_pid": docker_pid,
            "materialization": {
                "path": repo_relative(repo, materialization_path),
                "sha256": materialization_sha,
                "resolved_config": materialization["resolved_config"],
                "resolved_config_sha256": materialization["resolved_config_sha256"],
            },
            "pose_gate_binding": materialization["bindings"],
            "preprocess_binding": materialization["preprocess"],
            "training_completion": completion,
            "loss_share_aggregation": loss_share_aggregation,
            "infrastructure_retry": {
                "policy": policy,
                "original_started_receipt": eligibility["started"],
                "original_failed_receipt": eligibility["failed"],
                "retry_started_receipt": {
                    "path": repo_relative(repo, retry_started_path),
                    "sha256": sha256_file(retry_started_path),
                },
                "retry_completed_receipt": {
                    "path": repo_relative(repo, retry_completed_path),
                    "sha256": sha256_file(retry_completed_path),
                },
                "original_file_snapshot_sha256": eligibility[
                    "original_file_snapshot_sha256"
                ],
                "resolved_config_difference_keys": ["out_dir"],
                "optimizer_restart_completed_steps": 0,
            },
            "log": repo_relative(repo, retry_log),
            "log_sha256": sha256_file(retry_log),
        }
        exclusive_json(target / outputs["completed_receipt"], completed_payload)
        _counter_update(
            repo,
            config,
            job_key,
            "completed",
            {"elapsed_seconds": elapsed, "completed_via": "infra_retry_01"},
        )
        return completed_payload
    except BaseException as exc:
        elapsed = time.monotonic() - launch_started
        retry_failed_path = attempt / "retry_failed.json"
        retry_failed = {
            "schema": RETRY_FAILED_SCHEMA,
            "run_id": config["run_id"],
            "job_key": job_key,
            "retry_key": retry_key,
            "failed_at": utc_now(),
            "return_code": return_code,
            "elapsed_seconds": elapsed,
            "docker_compose_pid": docker_pid,
            "error_type": type(exc).__name__,
            "reason": str(exc),
            "retry_started_receipt": {
                "path": repo_relative(repo, retry_started_path),
                "sha256": sha256_file(retry_started_path),
            },
            "original_file_snapshot_sha256": eligibility[
                "original_file_snapshot_sha256"
            ],
            "log": repo_relative(repo, retry_log),
            "log_sha256": sha256_file(retry_log) if retry_log.is_file() else None,
            "original_failed_attempt_preserved": True,
            "another_retry_allowed": False,
        }
        if not retry_failed_path.exists():
            exclusive_json(retry_failed_path, retry_failed)
        _counter_update(
            repo,
            config,
            job_key,
            "infra_retry_failed",
            {"elapsed_seconds": elapsed, "reason": str(exc)},
        )
        raise


def check_materialization(
    *,
    repo: Path,
    config_path: Path,
    config: Mapping[str, Any],
    building_id: str,
    arm: str,
    run: str,
) -> dict[str, Any]:
    path, payload, digest = _materialization(repo, config, building_id, arm, run)
    require_equal(
        sha256_file(config_path),
        payload["driver_config_sha256"],
        "driver config SHA-256",
    )
    preprocess = validate_preprocess(repo, config, building_id)
    require_equal(
        preprocess["full_snapshot_sha256"],
        payload["preprocess"]["full_snapshot_sha256"],
        "preprocess full snapshot SHA-256",
    )
    validate_r1_r2(repo, config)
    return {
        "status": "PASSED",
        "materialization": repo_relative(repo, path),
        "materialization_sha256": digest,
        "preprocess_full_snapshot_sha256": preprocess["full_snapshot_sha256"],
    }


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        type=Path,
        default=Path(
            "phases/p2-gsjso/configs/fusion_w1_training_v1_20260725.json"
        ),
    )
    parser.add_argument(
        "--retry-policy",
        type=Path,
        default=Path(
            "phases/p2-gsjso/configs/fusion_w1_training_infra_retry_20260726.json"
        ),
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in ("materialize", "check", "aggregate-loss-shares"):
        sub = subparsers.add_parser(command)
        sub.add_argument("--building-id", required=True)
        sub.add_argument("--arm", choices=ARMS, required=True)
        sub.add_argument("--run", choices=RUNS, required=True)
    launch_parser = subparsers.add_parser("launch")
    launch_parser.add_argument("--building-id", required=True)
    launch_parser.add_argument("--arm", choices=ARMS, required=True)
    launch_parser.add_argument("--run", choices=RUNS, required=True)
    launch_parser.add_argument("--gpu", type=int, choices=(0, 1), required=True)
    retry_parser = subparsers.add_parser("retry-infra")
    retry_parser.add_argument("--building-id", required=True)
    retry_parser.add_argument("--arm", choices=ARMS, required=True)
    retry_parser.add_argument("--run", choices=RUNS, required=True)
    retry_parser.add_argument("--gpu", type=int, choices=(0, 1), required=True)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    config_path = resolve_path(REPO, str(args.config))
    config = load_driver_config(config_path)
    if args.command == "materialize":
        result = materialize(
            repo=REPO,
            config_path=config_path,
            config=config,
            building_id=args.building_id,
            arm=args.arm,
            run=args.run,
        )
    elif args.command == "check":
        result = check_materialization(
            repo=REPO,
            config_path=config_path,
            config=config,
            building_id=args.building_id,
            arm=args.arm,
            run=args.run,
        )
    elif args.command == "launch":
        result = launch(
            repo=REPO,
            config_path=config_path,
            config=config,
            building_id=args.building_id,
            arm=args.arm,
            run=args.run,
            gpu=args.gpu,
        )
    elif args.command == "retry-infra":
        result = retry_infrastructure_failure(
            repo=REPO,
            config_path=config_path,
            config=config,
            policy_path=args.retry_policy,
            building_id=args.building_id,
            arm=args.arm,
            run=args.run,
            gpu=args.gpu,
        )
    elif args.command == "aggregate-loss-shares":
        target = job_dir(REPO, config, args.building_id, args.arm, args.run)
        _verify_training_completion(
            target, int(config["recipe"]["max_iter"]), repo=REPO
        )
        result = aggregate_loss_shares(
            repo=REPO,
            config=config,
            building_id=args.building_id,
            arm=args.arm,
            run=args.run,
        )
    else:  # pragma: no cover
        raise AssertionError(args.command)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ContractError as exc:
        print(f"FUS-W1 training contract error: {exc}", file=sys.stderr)
        raise SystemExit(2)
