#!/usr/bin/env python3
"""Run the ten resolved P1W jobs on a two-GPU queue with the 9 h guard.

The driver executes only ``docker compose run`` training commands.  It stops
starting new jobs at 8.5 h.  At 9 h, each active job is allowed to publish its
next durable 5k full-state checkpoint and is then interrupted, so the next
invocation resumes from that checkpoint.  Winner eligibility additionally
requires the trainer's normal 20k completion epilogue and bound manifest; a
20k checkpoint followed by a crash remains partial/resumable.
"""
from __future__ import annotations

import argparse
from collections import deque
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import signal
import subprocess
import tempfile
import time
from typing import Any, Callable, Mapping, Sequence, TextIO

import yaml


REPO = Path(__file__).resolve().parents[3]
RUN_ID = "20260721_pilot_1wave"
RESOLVED_SCHEMA = "jointbuildgs.pilot_1wave.resolved_configs.v1"
DRIVER_SCHEMA = "jointbuildgs.pilot_1wave.driver_manifest.v1"
IMAGE_TAG = "jointbuildgs:dev"
CONTAINER_REPO = Path("/workspace/JointBuildGS")
REQUIRED_HOST_UID = 1000
REQUIRED_HOST_GID = 1000
TRAINING_CONTAINER_USER = "0:0"
TRAINING_ARTIFACT_PUBLICATION = {
    "runtime_json": "0644",
    "full_state_checkpoint": "0644",
    "checkpoint_sha256_sidecar": "0644",
}
CHECKPOINT_STEPS = (5000, 10000, 15000, 20000)
STOP_START_SECONDS = 8.5 * 3600.0
WALL_GUARD_SECONDS = 9.0 * 3600.0
MAX_ITER = 20000
FINALIZATION_GRACE_SECONDS = 3600.0
FULL_STATE_MANIFEST_SCHEMA = "jointbuildgs.stage2.resume_manifest.v1"
MATERIALIZED_INPUT_INVENTORY_SCHEMA = (
    "jointbuildgs.pilot_1wave.materialized_input_inventory.v1"
)
CHECKPOINT_VERIFICATION_SCHEMA = (
    "jointbuildgs.pilot_1wave.checkpoint_verification.v1"
)
CHECKPOINT_VERIFIER_RELATIVE_PATH = Path(
    "phases/p2-gsjso/scripts/pilot_1wave_checkpoint_verify.py"
)
CHECKPOINT_VERIFIER_RESULT_PREFIX = "P1W_CHECKPOINT_VERIFY_JSON="
FULL_STATE_BINDING_KEYS = frozenset(
    {"training_config", "effective_training_config", "output_path"}
)
FULL_STATE_STEP_SEMANTICS = "completed_optimizer_updates"
FULL_STATE_DEFAULT_LOSS_CSV_PATHS = (
    "audit/loss_grad_norms.csv",
    "audit/semantic_geometry.csv",
    "audit/semantic_target_observations.csv",
)
CONDITION_ARMS = {
    "01": "01_surface",
    "02": "02_photo_control",
    "03": "03_plane_soft",
    "04a": "04a_plane_medium_vision",
    "04b": "04b_plane_medium_gt_upperbound",
}
EXECUTION_TREE_PATHS = (
    "src",
    "phases/p2-gsjso/scripts",
    "phases/p2-gsjso/configs",
    "Dockerfile",
    "docker-compose.yml",
)
_SIDECAR_RE = re.compile(r"^([0-9a-f]{64})  (step_[0-9]{6,}\.pt)\n?$")
_CHECKPOINT_SHA_CACHE: dict[tuple[str, int, int, int, int, str], str] = {}
_CHECKPOINT_PAYLOAD_CACHE: dict[
    tuple[
        str,
        int,
        int,
        int,
        int,
        str,
        tuple[tuple[str, str], ...],
        str,
        str,
    ],
    tuple[bool, str | None],
] = {}


class DriverError(RuntimeError):
    """The resolved queue or runtime violates the P1W execution contract."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_file(path: Path, block_size: int = 1 << 20) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(block_size), b""):
            digest.update(block)
    return digest.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DriverError(f"cannot read JSON {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise DriverError(f"JSON root must be an object: {path}")
    return payload


def load_json_and_sha256(path: Path) -> tuple[dict[str, Any], str]:
    """Parse and hash the same immutable byte snapshot."""

    try:
        raw = path.read_bytes()
        payload = json.loads(raw)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise DriverError(f"cannot read JSON {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise DriverError(f"JSON root must be an object: {path}")
    return payload, hashlib.sha256(raw).hexdigest()


def atomic_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f".{path.name}.",
        delete=False,
    ) as stream:
        temporary = Path(stream.name)
        json.dump(payload, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")
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


def repo_relative(repo: Path, path: Path) -> str:
    try:
        return str(path.resolve().relative_to(repo.resolve()))
    except ValueError as exc:
        raise DriverError(f"path is outside repository: {path}") from exc


def host_from_container(repo: Path, path: str) -> Path:
    candidate = Path(path)
    try:
        relative = candidate.relative_to(CONTAINER_REPO)
    except ValueError as exc:
        raise DriverError(f"container path is outside {CONTAINER_REPO}: {path}") from exc
    return (repo / relative).resolve()


def require_host_driver_identity() -> dict[str, Any]:
    """Bind host writes and training-container writes to one exact identity."""

    identity = {
        "real_uid": os.getuid(),
        "real_gid": os.getgid(),
        "effective_uid": os.geteuid(),
        "effective_gid": os.getegid(),
        "required_uid": REQUIRED_HOST_UID,
        "required_gid": REQUIRED_HOST_GID,
        "training_container_user": TRAINING_CONTAINER_USER,
    }
    observed = (
        identity["real_uid"],
        identity["real_gid"],
        identity["effective_uid"],
        identity["effective_gid"],
    )
    required = (
        REQUIRED_HOST_UID,
        REQUIRED_HOST_GID,
        REQUIRED_HOST_UID,
        REQUIRED_HOST_GID,
    )
    if observed != required:
        raise DriverError(
            "P1W driver must run as exact host UID:GID "
            f"{REQUIRED_HOST_UID}:{REQUIRED_HOST_GID} (real/effective); observed "
            f"real={identity['real_uid']}:{identity['real_gid']} "
            f"effective={identity['effective_uid']}:{identity['effective_gid']}"
        )
    return identity


def container_name_for(job_id: str) -> str:
    if re.fullmatch(r"(?:01|02|03|04a|04b)_seed(?:1001|1002)", job_id) is None:
        raise DriverError(f"cannot derive a safe container name from job ID: {job_id!r}")
    return f"jointbuildgs-p1w-{RUN_ID.replace('_pilot_1wave', '')}-{job_id.replace('_', '-')}"


def command_for(config_path: str, gpu: int, *, container_name: str) -> list[str]:
    if gpu not in (0, 1):
        raise DriverError(f"P1W GPU must be 0 or 1, got {gpu}")
    if re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_.-]+", container_name) is None:
        raise DriverError(f"unsafe Docker container name: {container_name!r}")
    command = [
        "docker",
        "compose",
        "run",
        "--rm",
        "--no-deps",
        "-T",
        "--user",
        TRAINING_CONTAINER_USER,
    ]
    command.extend(["--name", container_name])
    command.extend(
        [
        "-e",
        f"NVIDIA_VISIBLE_DEVICES={gpu}",
        "-e",
        "CUDA_VISIBLE_DEVICES=0",
        "dev",
        "python",
        "-m",
        "src.stage2.train",
        "--config",
        config_path,
        ]
    )
    return command


def command_is_docker_only(command: Sequence[str]) -> bool:
    if tuple(command[:3]) != ("docker", "compose", "run") or tuple(
        command[-4:-1]
    ) != ("-m", "src.stage2.train", "--config"):
        return False
    try:
        name_index = command.index("--name")
        container_name = command[name_index + 1]
        expected = [
            command_for(command[-1], gpu, container_name=container_name)
            for gpu in (0, 1)
        ]
    except (DriverError, ValueError, IndexError):
        return False
    return list(command) in expected


def query_image_id(repo: Path) -> str:
    process = subprocess.run(
        ["docker", "image", "inspect", "--format={{.Id}}", IMAGE_TAG],
        cwd=repo,
        text=True,
        capture_output=True,
        check=False,
    )
    if process.returncode != 0:
        raise DriverError(f"cannot inspect {IMAGE_TAG}: {process.stderr.strip()}")
    image_id = process.stdout.strip()
    if re.fullmatch(r"sha256:[0-9a-f]{64}", image_id) is None:
        raise DriverError(f"unexpected Docker image ID: {image_id!r}")
    return image_id


def query_git_head(repo: Path) -> str:
    process = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo, text=True, capture_output=True, check=False
    )
    head = process.stdout.strip()
    if process.returncode != 0 or not re.fullmatch(r"[0-9a-f]{40}", head):
        raise DriverError(f"cannot resolve git HEAD: {process.stderr.strip()}")
    return head


def query_git_dirty(repo: Path) -> tuple[bool, str]:
    process = subprocess.run(
        ["git", "status", "--porcelain=v1"], cwd=repo, text=True, capture_output=True, check=False
    )
    if process.returncode != 0:
        raise DriverError(f"cannot inspect git worktree: {process.stderr.strip()}")
    payload = process.stdout.encode("utf-8")
    return bool(payload), hashlib.sha256(payload).hexdigest()


def query_execution_tree_state(repo: Path) -> tuple[bool, str, tuple[str, ...]]:
    """Return the exact mutable source/config status that may affect training."""

    process = subprocess.run(
        [
            "git",
            "status",
            "--porcelain=v1",
            "--untracked-files=all",
            "--",
            *EXECUTION_TREE_PATHS,
        ],
        cwd=repo,
        text=True,
        capture_output=True,
        check=False,
    )
    if process.returncode != 0:
        raise DriverError(
            f"cannot inspect P1W execution tree: {process.stderr.strip()}"
        )
    payload = process.stdout.encode("utf-8")
    lines = tuple(line for line in process.stdout.splitlines() if line)
    return bool(lines), hashlib.sha256(payload).hexdigest(), lines


def require_clean_execution_tree(
    repo: Path,
    *,
    expected_status_sha256: str | None = None,
) -> str:
    dirty, status_sha256, lines = query_execution_tree_state(repo)
    if dirty:
        raise DriverError(
            "P1W execution tree is dirty/untracked; commit the exact runtime first: "
            + " | ".join(lines)
        )
    if (
        expected_status_sha256 is not None
        and status_sha256 != expected_status_sha256
    ):
        raise DriverError("P1W execution-tree status changed during the queue")
    return status_sha256


def query_compose_config_sha256(repo: Path) -> str:
    """Hash Docker Compose's fully resolved JSON model, not only one YAML file."""

    process = subprocess.run(
        ["docker", "compose", "config", "--format", "json"],
        cwd=repo,
        text=True,
        capture_output=True,
        check=False,
    )
    if process.returncode != 0:
        raise DriverError(
            f"cannot resolve Docker Compose config: {process.stderr.strip()}"
        )
    try:
        payload = json.loads(process.stdout)
    except json.JSONDecodeError as exc:
        raise DriverError(f"Docker Compose config is not JSON: {exc}") from exc
    if not isinstance(payload, Mapping):
        raise DriverError("Docker Compose config root must be an object")
    return _json_sha256(payload)


@contextmanager
def exclusive_driver_lock(driver_manifest_path: Path):
    """Prevent two queue owners from launching the same deterministic jobs."""

    lock_path = Path(f"{driver_manifest_path}.lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    stream = lock_path.open("a+", encoding="ascii")
    os.fchmod(stream.fileno(), 0o644)
    try:
        try:
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise DriverError(f"another P1W driver owns lock: {lock_path}") from exc
        stream.seek(0)
        stream.truncate()
        stream.write(f"pid={os.getpid()} acquired_at={utc_now()}\n")
        stream.flush()
        os.fsync(stream.fileno())
        yield lock_path
    finally:
        try:
            fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
        finally:
            stream.close()


def _docker_container_id(repo: Path, container_name: str) -> str | None:
    process = subprocess.run(
        [
            "docker",
            "container",
            "inspect",
            "--format={{.Id}}",
            container_name,
        ],
        cwd=repo,
        text=True,
        capture_output=True,
        check=False,
    )
    if process.returncode == 0:
        container_id = process.stdout.strip()
        if re.fullmatch(r"[0-9a-f]{64}", container_id) is None:
            raise DriverError(
                f"unexpected container ID for {container_name}: {container_id!r}"
            )
        return container_id
    error = process.stderr.strip().lower()
    if "no such object" in error or "no such container" in error:
        return None
    raise DriverError(f"cannot inspect Docker container {container_name}: {process.stderr.strip()}")


def _assert_container_absent(repo: Path, container_name: str) -> None:
    container_id = _docker_container_id(repo, container_name)
    if container_id is not None:
        raise DriverError(
            f"deterministic training container already exists: {container_name} ({container_id})"
        )


def _docker_signal(repo: Path, container_name: str, sig: signal.Signals) -> None:
    """Signal the exact driver-owned container, tolerating an already reaped --rm."""

    if _docker_container_id(repo, container_name) is None:
        return
    signal_name = sig.name.removeprefix("SIG")
    process = subprocess.run(
        ["docker", "kill", f"--signal={signal_name}", container_name],
        cwd=repo,
        text=True,
        capture_output=True,
        check=False,
    )
    if process.returncode != 0:
        error = process.stderr.strip().lower()
        if "no such container" not in error and "is not running" not in error:
            raise DriverError(
                f"cannot signal Docker container {container_name}: {process.stderr.strip()}"
            )


def _stop_container(repo: Path, container_name: str, *, timeout_seconds: int = 10) -> None:
    """Ask an exact driver-owned container to stop before the force-cleanup fallback."""

    if _docker_container_id(repo, container_name) is None:
        return
    process = subprocess.run(
        ["docker", "stop", "--time", str(int(timeout_seconds)), container_name],
        cwd=repo,
        text=True,
        capture_output=True,
        check=False,
    )
    if process.returncode != 0:
        error = process.stderr.strip().lower()
        if "no such container" not in error and "is not running" not in error:
            raise DriverError(
                f"cannot stop Docker container {container_name}: {process.stderr.strip()}"
            )


def _cleanup_container(repo: Path, container_name: str) -> None:
    """Force-remove only the exact deterministic container owned by this driver."""

    if _docker_container_id(repo, container_name) is None:
        return
    process = subprocess.run(
        ["docker", "rm", "--force", container_name],
        cwd=repo,
        text=True,
        capture_output=True,
        check=False,
    )
    if process.returncode != 0:
        error = process.stderr.strip().lower()
        if "no such container" not in error:
            raise DriverError(
                f"cannot remove Docker container {container_name}: {process.stderr.strip()}"
            )


@dataclass(frozen=True)
class MaterializedInventoryBinding:
    host_path: Path
    container_path: str
    sha256: str
    records_sha256: str
    view_count: int
    file_count: int
    total_bytes: int
    payload: Mapping[str, Any] = field(repr=False, compare=False)


@dataclass(frozen=True)
class Job:
    sequence: int
    job_id: str
    condition: str
    arm: str
    seed: int
    config_host: Path
    config_container: str
    config_sha256: str
    resolved_manifest_sha256: str
    out_host: Path
    out_container: str
    container_name: str
    training_config_binding_sha256: str
    loss_csv_paths: tuple[str, ...]
    materialized_inventory_host: Path
    materialized_inventory_container: str
    materialized_inventory_sha256: str
    materialized_records_sha256: str
    materialized_view_count: int
    materialized_file_count: int
    materialized_total_bytes: int


def _json_sha256(value: Any) -> str:
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _expected_training_config_binding(config: Mapping[str, Any]) -> str:
    bound = {
        key: value
        for key, value in config.items()
        if key not in {"full_state_resume", "full_state_resume_strict_cuda_rng"}
    }
    return _json_sha256(bound)


def _normalize_relative_output_path(value: str) -> str:
    path = Path(value)
    if path.is_absolute() or not path.parts or ".." in path.parts:
        raise DriverError(f"loss CSV path is not output-relative: {value!r}")
    normalized = Path(os.path.normpath(str(path)))
    if normalized == Path(".") or ".." in normalized.parts:
        raise DriverError(f"loss CSV path escapes output: {value!r}")
    return normalized.as_posix()


def _expected_loss_csv_paths(config: Mapping[str, Any]) -> tuple[str, ...]:
    extra = config.get("full_state_loss_csv_paths") or []
    if not isinstance(extra, list) or not all(
        isinstance(value, str) and value.strip() for value in extra
    ):
        raise DriverError("full_state_loss_csv_paths must be a list of nonempty strings")
    return tuple(
        sorted(
            {
                _normalize_relative_output_path(value)
                for value in (*FULL_STATE_DEFAULT_LOSS_CSV_PATHS, *extra)
            }
        )
    )


def _load_materialized_inventory_binding(
    repo: Path,
    resolved_manifest: Mapping[str, Any],
) -> MaterializedInventoryBinding:
    inputs = resolved_manifest.get("inputs")
    if not isinstance(inputs, Mapping):
        raise DriverError("resolved manifest inputs must be an object")
    record = inputs.get("materialized_input_inventory")
    if not isinstance(record, Mapping):
        raise DriverError("resolved manifest has no materialized input inventory")
    required_keys = {
        "path",
        "sha256",
        "records_sha256",
        "view_count",
        "file_count",
        "total_bytes",
    }
    if set(record) != required_keys:
        raise DriverError(
            "materialized inventory binding keys changed: "
            f"{sorted(set(record))}"
        )
    raw_path = Path(str(record.get("path", "")))
    if raw_path.is_absolute() or ".." in raw_path.parts:
        raise DriverError("materialized inventory path must be repository-relative")
    unresolved = repo / raw_path
    if unresolved.is_symlink():
        raise DriverError("materialized inventory must not be a symlink")
    path = unresolved.resolve()
    try:
        path.relative_to(repo.resolve())
    except ValueError as exc:
        raise DriverError("materialized inventory escapes repository") from exc
    if not path.is_file():
        raise DriverError(f"materialized inventory is missing: {path}")
    sha = str(record.get("sha256", ""))
    records_sha = str(record.get("records_sha256", ""))
    if re.fullmatch(r"[0-9a-f]{64}", sha) is None or re.fullmatch(
        r"[0-9a-f]{64}", records_sha
    ) is None:
        raise DriverError("materialized inventory SHA binding is malformed")
    if sha256_file(path) != sha:
        raise DriverError("materialized inventory file SHA mismatch")
    payload = load_json(path)
    if payload.get("schema") != MATERIALIZED_INPUT_INVENTORY_SCHEMA:
        raise DriverError("materialized inventory schema mismatch")
    if payload.get("run_id") != RUN_ID:
        raise DriverError("materialized inventory run ID mismatch")
    if payload.get("learning_runs_started") != 0 or payload.get("optimizer_updates") != 0:
        raise DriverError("materialized inventory was not created before learning")
    records = payload.get("records")
    if not isinstance(records, list) or not records:
        raise DriverError("materialized inventory records must be a nonempty list")
    if _json_sha256(records) != records_sha or payload.get("records_sha256") != records_sha:
        raise DriverError("materialized inventory records SHA mismatch")
    for key in ("view_count", "file_count", "total_bytes"):
        value = record.get(key)
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise DriverError(f"materialized inventory {key} is invalid")
        if payload.get(key) != value:
            raise DriverError(f"materialized inventory {key} summary mismatch")
    if len(records) != int(record["file_count"]):
        raise DriverError("materialized inventory record count mismatch")
    view_ids = payload.get("view_ids")
    if (
        not isinstance(view_ids, list)
        or len(view_ids) != int(record["view_count"])
        or view_ids != sorted(view_ids)
        or len(view_ids) != len(set(view_ids))
        or any(not isinstance(value, str) or not value for value in view_ids)
    ):
        raise DriverError("materialized inventory view IDs are invalid")
    container_path = str(CONTAINER_REPO / repo_relative(repo, path))
    return MaterializedInventoryBinding(
        host_path=path,
        container_path=container_path,
        sha256=sha,
        records_sha256=records_sha,
        view_count=int(record["view_count"]),
        file_count=int(record["file_count"]),
        total_bytes=int(record["total_bytes"]),
        payload=payload,
    )


def validate_materialized_input_files(
    repo: Path,
    binding: MaterializedInventoryBinding,
) -> dict[str, Any]:
    """Hash every materialized Stage 2 byte once before the queue starts."""

    if sha256_file(binding.host_path) != binding.sha256:
        raise DriverError("materialized inventory changed before queue validation")
    records = binding.payload.get("records")
    if not isinstance(records, list) or _json_sha256(records) != binding.records_sha256:
        raise DriverError("materialized inventory records changed before validation")
    seen: set[str] = set()
    role_counts: dict[str, int] = {}
    total_bytes = 0
    for index, record in enumerate(records, start=1):
        if not isinstance(record, Mapping):
            raise DriverError(f"materialized input record {index} is not an object")
        allowed_keys = {"role", "path", "size_bytes", "sha256", "view_id"}
        if not set(record) <= allowed_keys or not {"role", "path", "size_bytes", "sha256"} <= set(record):
            raise DriverError(f"materialized input record {index} keys changed")
        relative = str(record.get("path", ""))
        relative_path = Path(relative)
        if (
            not relative
            or relative in seen
            or relative_path.is_absolute()
            or ".." in relative_path.parts
        ):
            raise DriverError(f"materialized input path is unsafe/duplicate: {relative!r}")
        seen.add(relative)
        unresolved = repo / relative_path
        if unresolved.is_symlink():
            raise DriverError(f"materialized input must not be a symlink: {relative}")
        path = unresolved.resolve()
        try:
            path.relative_to(repo.resolve())
        except ValueError as exc:
            raise DriverError(f"materialized input escapes repository: {relative}") from exc
        if not path.is_file():
            raise DriverError(f"materialized input is missing: {relative}")
        before = path.stat()
        expected_size = record.get("size_bytes")
        expected_sha = str(record.get("sha256", ""))
        if (
            isinstance(expected_size, bool)
            or not isinstance(expected_size, int)
            or expected_size <= 0
            or re.fullmatch(r"[0-9a-f]{64}", expected_sha) is None
        ):
            raise DriverError(f"materialized input metadata is invalid: {relative}")
        actual_sha = sha256_file(path)
        after = path.stat()
        before_identity = (
            before.st_dev,
            before.st_ino,
            before.st_size,
            before.st_mtime_ns,
            before.st_ctime_ns,
        )
        after_identity = (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
            after.st_ctime_ns,
        )
        if before_identity != after_identity:
            raise DriverError(f"materialized input changed while hashing: {relative}")
        if after.st_size != expected_size or actual_sha != expected_sha:
            raise DriverError(f"materialized input bytes do not match inventory: {relative}")
        role = str(record.get("role", ""))
        if not role:
            raise DriverError(f"materialized input role is empty: {relative}")
        role_counts[role] = role_counts.get(role, 0) + 1
        total_bytes += int(after.st_size)
    expected_roles = {
        "sfm_cameras": 1,
        "sfm_images": 1,
        "sfm_points3d": 1,
        "rgb": binding.view_count,
        "mvs_depth_geometric": binding.view_count,
        "mvs_normal_geometric": binding.view_count,
        "mono_normal_omnidata": binding.view_count,
    }
    if role_counts != expected_roles:
        raise DriverError(
            f"materialized input role inventory mismatch: {role_counts!r}"
        )
    if binding.payload.get("role_counts") != expected_roles:
        raise DriverError("materialized input declared role counts mismatch")
    if len(seen) != binding.file_count or total_bytes != binding.total_bytes:
        raise DriverError("materialized input aggregate summary mismatch")
    return {
        "validated": True,
        "inventory_sha256": binding.sha256,
        "records_sha256": binding.records_sha256,
        "view_count": binding.view_count,
        "file_count": binding.file_count,
        "total_bytes": binding.total_bytes,
    }


def _validate_config_contract(config: Mapping[str, Any], record: Mapping[str, Any]) -> None:
    condition = record.get("condition")
    seed = record.get("seed")
    expected_job_id = f"{condition}_seed{seed}"
    if condition not in CONDITION_ARMS or seed not in (1001, 1002) or isinstance(seed, bool):
        raise DriverError(f"invalid condition/seed schema: condition={condition!r}, seed={seed!r}")
    if record.get("job_id") != expected_job_id:
        raise DriverError(f"job ID does not match condition/seed: {record.get('job_id')!r}")
    if record.get("pilot_arm") != CONDITION_ARMS[condition]:
        raise DriverError(f"job arm does not match condition: {record.get('job_id')}")
    if config.get("pilot_resolved_config_schema") != RESOLVED_SCHEMA:
        raise DriverError(f"resolved config schema mismatch: {record.get('job_id')}")
    if config.get("pilot_run_id") != RUN_ID:
        raise DriverError(f"resolved config run ID mismatch: {record.get('job_id')}")
    if config.get("pilot_condition") != condition:
        raise DriverError(f"job/config condition mismatch: {record.get('job_id')}")
    if config.get("pilot_job_id") != record.get("job_id"):
        raise DriverError(f"job/config ID mismatch: {record.get('job_id')}")
    if config.get("pilot_arm") != record.get("pilot_arm"):
        raise DriverError(f"job/config arm mismatch: {record.get('job_id')}")
    if config.get("seed") != record.get("seed"):
        raise DriverError(f"job/config seed mismatch: {record.get('job_id')}")
    if config.get("max_iter") != MAX_ITER:
        raise DriverError(f"{record.get('job_id')} max_iter is not 20000")
    if config.get("full_state_checkpoint") is not True:
        raise DriverError(f"{record.get('job_id')} full-state checkpoint is disabled")
    if config.get("full_state_checkpoint_steps") != list(CHECKPOINT_STEPS):
        raise DriverError(f"{record.get('job_id')} checkpoint ladder changed")
    if config.get("full_state_resume") not in ("auto", "latest"):
        raise DriverError(f"{record.get('job_id')} resume selector is not auto/latest")
    _expected_loss_csv_paths(config)
    for key in (
        "w_sem",
        "w_mutual",
        "w_mvc",
        "w_distort",
        "w_mono_depth",
        "w_semdepth_smooth",
        "w_semdepth_plane",
        "w_boundary_normal",
    ):
        if float(config.get(key, float("nan"))) != 0.0:
            raise DriverError(f"{record.get('job_id')} forbidden weight {key} is not zero")


def load_resolved_jobs(repo: Path, manifest_path: Path) -> tuple[dict[str, Any], list[Job]]:
    repo = repo.resolve()
    if manifest_path.is_symlink():
        raise DriverError(f"resolved manifest must not be a symlink: {manifest_path}")
    manifest_path = manifest_path.resolve()
    try:
        manifest_path.relative_to(repo)
    except ValueError as exc:
        raise DriverError("resolved manifest escapes repository") from exc
    if not manifest_path.is_file():
        raise DriverError(f"resolved manifest must be a regular non-symlink file: {manifest_path}")
    payload, resolved_manifest_sha256 = load_json_and_sha256(manifest_path)
    if payload.get("schema") != RESOLVED_SCHEMA or payload.get("run_id") != RUN_ID:
        raise DriverError("unsupported resolved-config manifest")
    if payload.get("state") != "resolved" or payload.get("learning_runs_started") != 0:
        raise DriverError("resolved manifest must precede all learning")
    budget = payload.get("budget", {})
    expected_budget = {
        "seeds": [1001, 1002],
        "max_optimizer_updates": 20000,
        "full_state_checkpoint_updates": list(CHECKPOINT_STEPS),
        "gpu_count": 2,
        "wall_guard_hours": 9.0,
        "stop_starting_new_runs_hours": 8.5,
        "partial_is_winner_eligible": False,
    }
    for key, expected in expected_budget.items():
        if budget.get(key) != expected:
            raise DriverError(f"resolved budget {key} changed: {budget.get(key)!r}")
    materialized = _load_materialized_inventory_binding(repo, payload)
    records = payload.get("jobs")
    if not isinstance(records, list) or len(records) != 10 or payload.get("config_count") != 10:
        raise DriverError("resolved manifest must contain exactly ten jobs")
    output_binding = payload.get("training_output_root")
    if not isinstance(output_binding, Mapping):
        raise DriverError("resolved manifest has no separate training_output_root")
    if output_binding.get("writable_and_separate_from_config_bundle") is not True:
        raise DriverError("resolved training output root separation is not locked")
    training_root = (repo / str(output_binding.get("path", ""))).resolve()
    try:
        training_root.relative_to(repo.resolve())
    except ValueError as exc:
        raise DriverError("training output root escapes repository") from exc
    bundle_root = manifest_path.parent.resolve()
    if (
        training_root == bundle_root
        or training_root in bundle_root.parents
        or bundle_root in training_root.parents
    ):
        raise DriverError("training output root overlaps immutable config bundle")
    training_root_container = str(output_binding.get("container_path", ""))
    if not training_root_container.startswith(f"{CONTAINER_REPO}/"):
        raise DriverError("training output container root escapes repository mount")
    if host_from_container(repo, training_root_container) != training_root:
        raise DriverError("host/container training output roots disagree")

    jobs: list[Job] = []
    seen: set[tuple[str, int]] = set()
    seen_configs: set[Path] = set()
    seen_outputs: set[Path] = set()
    seen_containers: set[str] = set()
    for index, record in enumerate(records, start=1):
        if not isinstance(record, Mapping):
            raise DriverError(f"job {index} is not an object")
        if record.get("sequence") != index:
            raise DriverError("resolved job sequence is not contiguous")
        raw_config_path = Path(str(record.get("config_path", "")))
        config_host_unresolved = repo / raw_config_path
        if config_host_unresolved.is_symlink():
            raise DriverError(f"resolved config must not be a symlink: {config_host_unresolved}")
        config_host = config_host_unresolved.resolve()
        try:
            config_host.relative_to(repo.resolve())
        except ValueError as exc:
            raise DriverError("resolved config path escapes repository") from exc
        if not config_host.is_file():
            raise DriverError(f"resolved config is missing: {config_host}")
        expected_config = bundle_root / f"{record.get('job_id')}.yaml"
        if config_host != expected_config:
            raise DriverError(
                f"resolved config path is not canonical for {record.get('job_id')}: {config_host}"
            )
        if config_host in seen_configs:
            raise DriverError(f"duplicate resolved config path: {config_host}")
        seen_configs.add(config_host)
        actual_sha = sha256_file(config_host)
        if actual_sha != record.get("config_sha256"):
            raise DriverError(f"resolved config SHA mismatch: {config_host}")
        try:
            config = yaml.safe_load(config_host.read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError) as exc:
            raise DriverError(f"cannot parse resolved config {config_host}: {exc}") from exc
        if not isinstance(config, dict):
            raise DriverError(f"resolved config is not a mapping: {config_host}")
        _validate_config_contract(config, record)
        if (
            config.get("pilot_materialized_input_inventory_path")
            != materialized.container_path
            or config.get("pilot_materialized_input_inventory_sha256")
            != materialized.sha256
        ):
            raise DriverError(
                "job/config materialized inventory binding mismatch: "
                f"{record.get('job_id')}"
            )
        condition = str(record.get("condition"))
        seed = int(record.get("seed"))
        key = (condition, seed)
        if key in seen:
            raise DriverError(f"duplicate resolved job: {key}")
        seen.add(key)
        config_container = str(CONTAINER_REPO / repo_relative(repo, config_host))
        if config.get("out_dir") != record.get("out_dir"):
            raise DriverError(f"out_dir mismatch for {record.get('job_id')}")
        out_container = str(config["out_dir"])
        out_host = host_from_container(repo, out_container)
        try:
            out_host.relative_to(training_root)
        except ValueError as exc:
            raise DriverError(
                f"job output escapes declared training root: {record.get('job_id')}"
            ) from exc
        expected_out_host = training_root / condition / f"seed_{seed}"
        expected_out_container = (
            f"{training_root_container.rstrip('/')}/{condition}/seed_{seed}"
        )
        if out_host != expected_out_host or out_container != expected_out_container:
            raise DriverError(
                f"job output is not the canonical condition/seed directory: {record.get('job_id')}"
            )
        if out_host in seen_outputs:
            raise DriverError(f"duplicate job output directory: {out_host}")
        seen_outputs.add(out_host)
        container_name = container_name_for(str(record["job_id"]))
        if container_name in seen_containers:
            raise DriverError(f"duplicate deterministic container name: {container_name}")
        seen_containers.add(container_name)
        jobs.append(
            Job(
                sequence=index,
                job_id=str(record["job_id"]),
                condition=condition,
                arm=str(record["pilot_arm"]),
                seed=seed,
                config_host=config_host,
                config_container=config_container,
                config_sha256=actual_sha,
                resolved_manifest_sha256=resolved_manifest_sha256,
                out_host=out_host,
                out_container=out_container,
                container_name=container_name,
                training_config_binding_sha256=_expected_training_config_binding(config),
                loss_csv_paths=_expected_loss_csv_paths(config),
                materialized_inventory_host=materialized.host_path,
                materialized_inventory_container=materialized.container_path,
                materialized_inventory_sha256=materialized.sha256,
                materialized_records_sha256=materialized.records_sha256,
                materialized_view_count=materialized.view_count,
                materialized_file_count=materialized.file_count,
                materialized_total_bytes=materialized.total_bytes,
            )
        )
    expected = {
        (condition, seed)
        for condition in CONDITION_ARMS
        for seed in (1001, 1002)
    }
    if seen != expected:
        raise DriverError(f"resolved job matrix is incomplete: missing={sorted(expected - seen)}")
    return payload, jobs


def checkpoint_is_durable(
    out_dir: Path,
    step: int,
    *,
    sha_cache: dict[tuple[str, int, int, int, int, str], str] | None = None,
) -> bool:
    checkpoint = out_dir / "ckpt" / f"step_{step:06d}.pt"
    sidecar = Path(f"{checkpoint}.sha256")
    if not checkpoint.is_file() or not sidecar.is_file():
        return False
    try:
        text = sidecar.read_text(encoding="ascii")
    except OSError:
        return False
    match = _SIDECAR_RE.fullmatch(text)
    if not match or match.group(2) != checkpoint.name:
        return False
    stat = checkpoint.stat()
    if stat.st_size <= 0:
        return False
    declared_digest = match.group(1)
    cache = _CHECKPOINT_SHA_CACHE if sha_cache is None else sha_cache
    cache_key = (
        str(checkpoint.resolve()),
        int(stat.st_ino),
        int(stat.st_size),
        int(stat.st_mtime_ns),
        int(stat.st_ctime_ns),
        declared_digest,
    )
    actual_digest = cache.get(cache_key)
    if actual_digest is None:
        actual_digest = sha256_file(checkpoint)
        cache[cache_key] = actual_digest
        # One path has at most one useful current cache entry.
        for key in list(cache):
            if key != cache_key and key[0] == cache_key[0]:
                del cache[key]
    return actual_digest == declared_digest


def validate_checkpoint_payload(
    repo: Path,
    checkpoint: Path,
    *,
    checkpoint_container: str,
    verifier_container_name: str,
    expected_image_id: str,
    expected_verifier_source_sha256: str,
    expected_sha256: str,
    expected_binding_sha256: Mapping[str, str],
    expected_loss_csv_paths: Sequence[str],
) -> tuple[bool, str | None]:
    """Run the existing checkpoint loader inside the pinned, GPU-disabled image."""

    try:
        stat = checkpoint.stat()
    except OSError as exc:
        return False, f"cannot stat checkpoint payload: {exc}"
    normalized_binding = tuple(sorted(expected_binding_sha256.items()))
    cache_key = (
        str(checkpoint.resolve()),
        int(stat.st_ino),
        int(stat.st_size),
        int(stat.st_mtime_ns),
        int(stat.st_ctime_ns),
        expected_sha256,
        normalized_binding,
        expected_image_id,
        expected_verifier_source_sha256,
    )
    cached = _CHECKPOINT_PAYLOAD_CACHE.get(cache_key)
    if cached is not None:
        return cached
    command = [
        "docker",
        "compose",
        "run",
        "--rm",
        "--no-deps",
        "-T",
        "--name",
        verifier_container_name,
        "-e",
        "NVIDIA_VISIBLE_DEVICES=none",
        "-e",
        "CUDA_VISIBLE_DEVICES=-1",
        "-e",
        "PYTHONDONTWRITEBYTECODE=1",
        "dev",
        "python",
        str(CONTAINER_REPO / CHECKPOINT_VERIFIER_RELATIVE_PATH),
        "--checkpoint",
        checkpoint_container,
        "--expected-sha256",
        expected_sha256,
        "--expected-binding-json",
        json.dumps(
            dict(expected_binding_sha256),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ),
    ]
    for relative_path in expected_loss_csv_paths:
        command.extend(["--expected-loss-csv-path", str(relative_path)])
    try:
        if query_image_id(repo) != expected_image_id:
            raise DriverError("Docker image ID changed before checkpoint verification")
        _assert_container_absent(repo, verifier_container_name)
        process = subprocess.run(
            command,
            cwd=repo,
            text=True,
            capture_output=True,
            check=False,
        )
        if process.returncode != 0:
            raise DriverError(
                "pinned checkpoint verifier failed: "
                f"stdout={process.stdout[-2000:]!r} stderr={process.stderr[-2000:]!r}"
            )
        result_lines = [
            line[len(CHECKPOINT_VERIFIER_RESULT_PREFIX) :]
            for line in process.stdout.splitlines()
            if line.startswith(CHECKPOINT_VERIFIER_RESULT_PREFIX)
        ]
        if len(result_lines) != 1:
            raise DriverError("pinned checkpoint verifier emitted no unique JSON result")
        payload = json.loads(result_lines[0])
        expected_payload = {
            "schema": CHECKPOINT_VERIFICATION_SCHEMA,
            "state": "verified",
            "checkpoint_path": checkpoint_container,
            "checkpoint_sha256": expected_sha256,
            "completed_steps": MAX_ITER,
            "step_semantics": FULL_STATE_STEP_SEMANTICS,
            "binding_sha256": dict(expected_binding_sha256),
            "loss_csv_paths": list(expected_loss_csv_paths),
            "verifier_source_path": str(
                CONTAINER_REPO / CHECKPOINT_VERIFIER_RELATIVE_PATH
            ),
            "verifier_source_sha256": expected_verifier_source_sha256,
            "read_only": True,
            "gpu_required": False,
        }
        if not isinstance(payload, Mapping):
            raise DriverError("checkpoint verifier result is not an object")
        for key, expected in expected_payload.items():
            if payload.get(key) != expected:
                raise DriverError(
                    f"checkpoint verifier result {key} mismatch: "
                    f"{payload.get(key)!r} != {expected!r}"
                )
        if int(payload.get("learning_runs_started", 0) or 0) < 1:
            raise DriverError("checkpoint verifier result has no learning run")
        if query_image_id(repo) != expected_image_id:
            raise DriverError("Docker image ID changed during checkpoint verification")
        result = (True, None)
    except Exception as exc:
        result = (False, f"{type(exc).__name__}: {exc}")
    finally:
        try:
            _stop_container(repo, verifier_container_name, timeout_seconds=10)
            _cleanup_container(repo, verifier_container_name)
        except Exception as exc:
            result = (False, f"checkpoint verifier cleanup failed: {type(exc).__name__}: {exc}")
    _CHECKPOINT_PAYLOAD_CACHE[cache_key] = result
    for key in list(_CHECKPOINT_PAYLOAD_CACHE):
        if key != cache_key and key[0] == cache_key[0]:
            del _CHECKPOINT_PAYLOAD_CACHE[key]
    return result


def inspect_run_state(
    repo: Path,
    job: Job,
    *,
    expected_image_id: str,
    verifier_source_sha256: str,
) -> dict[str, Any]:
    out_dir = job.out_host
    durable = [step for step in CHECKPOINT_STEPS if checkpoint_is_durable(out_dir, step)]
    latest = max(durable, default=0)
    manifest_path = out_dir / "full_state_manifest.json"
    learning_runs = 0
    manifest_last = 0
    process_completed = False
    process_completed_steps = 0
    manifest_schema_valid = False
    binding_valid = False
    latest_manifest_checkpoint_valid = False
    checkpoint_payload_valid = False
    checkpoint_payload_error: str | None = None
    manifest_sha = None
    validation_errors: list[str] = []
    if manifest_path.is_file():
        try:
            manifest = load_json(manifest_path)
            learning_runs = int(manifest.get("learning_runs_started", 0) or 0)
            manifest_last = int(manifest.get("last_completed_steps", 0) or 0)
            process_completed = bool(manifest.get("process_completed", False))
            process_completed_steps = int(
                manifest.get("process_completed_steps", 0) or 0
            )
            manifest_schema_valid = manifest.get("schema") == FULL_STATE_MANIFEST_SCHEMA
            if not manifest_schema_valid:
                validation_errors.append("manifest schema mismatch")
            expected_manifest_fields = {
                "output_path": job.out_container,
                "config_path": job.config_container,
                "config_file_sha256": job.config_sha256,
                "max_iter": MAX_ITER,
                "checkpoint_steps": list(CHECKPOINT_STEPS),
                "step_semantics": FULL_STATE_STEP_SEMANTICS,
                "loss_csv_paths": list(job.loss_csv_paths),
            }
            for key, expected in expected_manifest_fields.items():
                if manifest.get(key) != expected:
                    validation_errors.append(
                        f"manifest {key} mismatch: {manifest.get(key)!r} != {expected!r}"
                    )
            binding = manifest.get("binding_sha256")
            binding_shape_valid = isinstance(binding, Mapping) and set(binding) == set(
                FULL_STATE_BINDING_KEYS
            ) and all(
                isinstance(key, str)
                and key
                and isinstance(value, str)
                and re.fullmatch(r"[0-9a-f]{64}", value)
                for key, value in binding.items()
            )
            expected_output_binding = hashlib.sha256(
                job.out_container.encode("utf-8")
            ).hexdigest()
            binding_valid = bool(
                binding_shape_valid
                and binding.get("training_config")
                == job.training_config_binding_sha256
                and binding.get("output_path") == expected_output_binding
            )
            if not binding_valid:
                validation_errors.append("manifest binding keys/values mismatch")
            latest_declared = manifest.get("latest_full_checkpoint")
            if isinstance(latest_declared, Mapping):
                latest_path = str(latest_declared.get("path", ""))
                latest_step = int(latest_declared.get("completed_steps", 0) or 0)
                latest_sha = str(latest_declared.get("sha256", ""))
                expected_path = out_dir / "ckpt" / f"step_{latest_step:06d}.pt"
                expected_container_path = (
                    f"{job.out_container}/ckpt/step_{latest_step:06d}.pt"
                )
                try:
                    sidecar_text = Path(f"{expected_path}.sha256").read_text(
                        encoding="ascii"
                    )
                except OSError:
                    sidecar_text = ""
                sidecar_match = _SIDECAR_RE.fullmatch(sidecar_text)
                latest_manifest_checkpoint_valid = (
                    latest_step in durable
                    and latest_step == manifest_last
                    and latest_path == expected_container_path
                    and re.fullmatch(r"[0-9a-f]{64}", latest_sha) is not None
                    and sidecar_match is not None
                    and sidecar_match.group(1) == latest_sha
                )
                if not latest_manifest_checkpoint_valid:
                    validation_errors.append("latest manifest checkpoint mismatch")
                if (
                    latest_manifest_checkpoint_valid
                    and latest_step == MAX_ITER
                    and binding_valid
                ):
                    checkpoint_payload_valid, checkpoint_payload_error = (
                        validate_checkpoint_payload(
                            repo,
                            expected_path,
                            checkpoint_container=expected_container_path,
                            verifier_container_name=(
                                f"{job.container_name}-checkpoint-verify"
                            ),
                            expected_image_id=expected_image_id,
                            expected_verifier_source_sha256=(
                                verifier_source_sha256
                            ),
                            expected_sha256=latest_sha,
                            expected_binding_sha256=dict(binding),
                            expected_loss_csv_paths=job.loss_csv_paths,
                        )
                    )
                    if not checkpoint_payload_valid:
                        validation_errors.append(
                            f"checkpoint payload invalid: {checkpoint_payload_error}"
                        )
            elif manifest_last > 0:
                validation_errors.append("latest_full_checkpoint missing")
            manifest_sha = sha256_file(manifest_path)
        except (DriverError, OSError, TypeError, ValueError) as exc:
            validation_errors.append(f"manifest parse/validation error: {exc}")
            manifest_last = 0
    completed_steps = min(latest, manifest_last) if manifest_last else latest
    completed = (
        manifest_schema_valid
        and not validation_errors
        and binding_valid
        and manifest_last == MAX_ITER
        and completed_steps == MAX_ITER
        and MAX_ITER in durable
        and latest_manifest_checkpoint_valid
        and checkpoint_payload_valid
        and process_completed
        and process_completed_steps == MAX_ITER
        and learning_runs >= 1
    )
    partial = bool(durable or learning_runs > 0 or manifest_path.is_file()) and not completed
    return {
        "learning_runs_started": learning_runs,
        "durable_checkpoint_steps": durable,
        "last_completed_steps": completed_steps,
        "full_state_manifest": str(manifest_path) if manifest_path.is_file() else None,
        "full_state_manifest_sha256": manifest_sha,
        "process_completed": process_completed,
        "process_completed_steps": process_completed_steps,
        "manifest_schema_valid": manifest_schema_valid,
        "binding_valid": binding_valid,
        "latest_manifest_checkpoint_valid": latest_manifest_checkpoint_valid,
        "checkpoint_payload_valid": checkpoint_payload_valid,
        "checkpoint_payload_error": checkpoint_payload_error,
        "manifest_validation_errors": validation_errors,
        "partial": partial,
        "completed": completed,
        "winner_eligible": completed,
    }


def next_checkpoint_target(last_completed_steps: int) -> int | None:
    for step in CHECKPOINT_STEPS:
        if step > int(last_completed_steps):
            return step
    return None


def may_start_new_run(elapsed_seconds: float) -> bool:
    return float(elapsed_seconds) < STOP_START_SECONDS


def guard_target(elapsed_seconds: float, last_completed_steps: int) -> int | None:
    if float(elapsed_seconds) < WALL_GUARD_SECONDS:
        return None
    return next_checkpoint_target(last_completed_steps)


@dataclass
class Running:
    job: Job
    gpu: int
    process: subprocess.Popen
    log_stream: TextIO
    command: list[str]
    container_name: str
    started_monotonic: float
    started_at: str
    guard_target_step: int | None = None
    guard_signal_sent_at: float | None = None
    final_checkpoint_seen_at: float | None = None
    terminate_sent_at: float | None = None
    kill_sent_at: float | None = None


def _signal_process_group(running: Running, sig: signal.Signals) -> None:
    try:
        os.killpg(running.process.pid, sig)
    except ProcessLookupError:
        pass


def _signal_running(repo: Path, running: Running, sig: signal.Signals) -> None:
    """Signal both the named container and its local compose client group."""

    container_error: Exception | None = None
    try:
        _docker_signal(repo, running.container_name, sig)
    except Exception as exc:  # still signal the local process group
        container_error = exc
    _signal_process_group(running, sig)
    if container_error is not None:
        raise container_error


def _initial_job_record(
    repo: Path,
    job: Job,
    *,
    image_id: str,
    verifier_source_sha256: str,
) -> dict[str, Any]:
    return {
        "sequence": job.sequence,
        "job_id": job.job_id,
        "condition": job.condition,
        "pilot_arm": job.arm,
        "seed": job.seed,
        "config_path": repo_relative(repo, job.config_host),
        "config_sha256": job.config_sha256,
        "out_dir": job.out_container,
        "container_name": job.container_name,
        "container_user": TRAINING_CONTAINER_USER,
        "materialized_input_inventory": {
            "path": repo_relative(repo, job.materialized_inventory_host),
            "sha256": job.materialized_inventory_sha256,
            "records_sha256": job.materialized_records_sha256,
            "view_count": job.materialized_view_count,
            "file_count": job.materialized_file_count,
            "total_bytes": job.materialized_total_bytes,
        },
        "state": "pending",
        "gpu": None,
        "command": None,
        "command_string": None,
        "started_at": None,
        "finished_at": None,
        "return_code": None,
        "guard_target_step": None,
        "guard_reason": None,
        **inspect_run_state(
            repo,
            job,
            expected_image_id=image_id,
            verifier_source_sha256=verifier_source_sha256,
        ),
    }


def _refresh_job_record(
    repo: Path,
    record: dict[str, Any],
    job: Job,
    *,
    image_id: str,
    verifier_source_sha256: str,
) -> None:
    record.update(
        inspect_run_state(
            repo,
            job,
            expected_image_id=image_id,
            verifier_source_sha256=verifier_source_sha256,
        )
    )


def _manifest_totals(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    return {
        "learning_runs_started": sum(int(row.get("learning_runs_started", 0) or 0) for row in records),
        "completed_count": sum(bool(row.get("completed")) for row in records),
        "partial_count": sum(bool(row.get("partial")) for row in records),
        "winner_eligible_count": sum(bool(row.get("winner_eligible")) for row in records),
        "deferred_count": sum(
            str(row.get("state", "")).startswith("deferred_") for row in records
        ),
    }


def _dry_run_payload(
    repo: Path,
    manifest_path: Path,
    jobs: Sequence[Job],
    image_id: str,
    git_head: str,
) -> dict[str, Any]:
    host_identity = require_host_driver_identity()
    planned = []
    for index, job in enumerate(jobs):
        gpu = index % 2
        command = command_for(
            job.config_container,
            gpu,
            container_name=job.container_name,
        )
        if not command_is_docker_only(command):
            raise DriverError("generated a non-Docker training command")
        planned.append(
            {
                "sequence": job.sequence,
                "job_id": job.job_id,
                "queue_gpu_preview": gpu,
                "container_name": job.container_name,
                "container_user": TRAINING_CONTAINER_USER,
                "command": command,
                "command_string": shlex.join(command),
                "config_sha256": job.config_sha256,
                "winner_eligible_only_if_completed_steps": MAX_ITER,
            }
        )
    return {
        "schema": DRIVER_SCHEMA,
        "state": "dry_run_validated",
        "learning_runs_started": 0,
        "resolved_manifest": {"path": repo_relative(repo, manifest_path), "sha256": sha256_file(manifest_path)},
        "runtime": {
            "image_tag": IMAGE_TAG,
            "image_id": image_id,
            "git_head": git_head,
            "host_driver_identity": host_identity,
            "training_container_user": TRAINING_CONTAINER_USER,
            "training_artifact_publication": TRAINING_ARTIFACT_PUBLICATION,
        },
        "guard": {
            "stop_starting_new_runs_seconds": STOP_START_SECONDS,
            "wall_guard_seconds": WALL_GUARD_SECONDS,
            "policy": "at 9h stop each active run immediately after its next durable 5k checkpoint",
        },
        "jobs": planned,
    }


def _verify_launch_bindings(
    *,
    resolved_manifest_path: Path,
    resolved_manifest_sha256: str,
    job: Job,
) -> None:
    if sha256_file(resolved_manifest_path) != resolved_manifest_sha256:
        raise DriverError("resolved manifest changed during the run queue")
    if sha256_file(job.config_host) != job.config_sha256:
        raise DriverError(f"resolved config changed before launch: {job.job_id}")
    if (
        sha256_file(job.materialized_inventory_host)
        != job.materialized_inventory_sha256
    ):
        raise DriverError(
            f"materialized input inventory changed before launch: {job.job_id}"
        )


def _execute_queue_locked(
    *,
    repo: Path,
    resolved_manifest_path: Path,
    driver_manifest_path: Path,
    jobs: list[Job],
    image_id: str,
    git_head: str,
    poll_seconds: float,
    checkpoint_grace_seconds: float,
    signal_grace_seconds: float,
    finalization_grace_seconds: float,
    clock: Callable[[], float] = time.monotonic,
    sleeper: Callable[[float], None] = time.sleep,
    popen_factory: Callable[..., subprocess.Popen] = subprocess.Popen,
) -> dict[str, Any]:
    host_identity = require_host_driver_identity()
    expected_manifest_shas = {job.resolved_manifest_sha256 for job in jobs}
    if len(expected_manifest_shas) != 1:
        raise DriverError("job matrix does not share one resolved manifest snapshot")
    resolved_manifest_payload, resolved_manifest_sha256 = load_json_and_sha256(
        resolved_manifest_path
    )
    if resolved_manifest_sha256 != next(iter(expected_manifest_shas)):
        raise DriverError("resolved manifest changed after job resolution")
    execution_status_sha256 = require_clean_execution_tree(repo)
    if query_git_head(repo) != git_head:
        raise DriverError("git HEAD changed before queue preflight")
    verifier_source_unresolved = repo / CHECKPOINT_VERIFIER_RELATIVE_PATH
    if verifier_source_unresolved.is_symlink():
        raise DriverError(
            f"checkpoint verifier source must not be a symlink: {verifier_source_unresolved}"
        )
    verifier_source = verifier_source_unresolved.resolve()
    try:
        verifier_source.relative_to(repo.resolve())
    except ValueError as exc:
        raise DriverError("checkpoint verifier source escapes repository") from exc
    if not verifier_source.is_file():
        raise DriverError(
            f"checkpoint verifier source is missing/non-regular: {verifier_source}"
        )
    verifier_source_sha256 = sha256_file(verifier_source)
    compose_config_sha256 = query_compose_config_sha256(repo)
    materialized_binding = _load_materialized_inventory_binding(
        repo, resolved_manifest_payload
    )
    if any(
        job.materialized_inventory_sha256 != materialized_binding.sha256
        or job.materialized_records_sha256 != materialized_binding.records_sha256
        for job in jobs
    ):
        raise DriverError("job matrix does not share the resolved materialized inventory")
    materialized_validation = validate_materialized_input_files(
        repo, materialized_binding
    )
    if sha256_file(resolved_manifest_path) != resolved_manifest_sha256:
        raise DriverError("resolved manifest changed during preflight validation")
    start = clock()
    dirty, dirty_sha = query_git_dirty(repo)
    records = [
        _initial_job_record(
            repo,
            job,
            image_id=image_id,
            verifier_source_sha256=verifier_source_sha256,
        )
        for job in jobs
    ]
    by_id = {row["job_id"]: row for row in records}
    pending: deque[Job] = deque()
    for job in jobs:
        row = by_id[job.job_id]
        if row["completed"]:
            row["state"] = "completed_existing"
        else:
            pending.append(job)
    active: dict[int, Running] = {}
    owned_container_names: set[str] = set()
    guard_triggered = False
    guard_triggered_at = None
    emergency_guard_timeout = False
    logs_dir = driver_manifest_path.parent / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)

    manifest: dict[str, Any] = {
        "schema": DRIVER_SCHEMA,
        "run_id": RUN_ID,
        "state": "running",
        "started_at": utc_now(),
        "finished_at": None,
        "resolved_manifest": {
            "path": repo_relative(repo, resolved_manifest_path),
            "sha256": resolved_manifest_sha256,
        },
        "runtime": {
            "docker_only": True,
            "image_tag": IMAGE_TAG,
            "image_id": image_id,
            "git_head": git_head,
            "git_worktree_dirty_at_start": dirty,
            "git_status_porcelain_sha256": dirty_sha,
            "execution_tree": {
                "pathspecs": list(EXECUTION_TREE_PATHS),
                "clean": True,
                "status_porcelain_sha256": execution_status_sha256,
            },
            "compose_config_sha256": compose_config_sha256,
            "host_driver_identity": host_identity,
            "training_container_user": TRAINING_CONTAINER_USER,
            "training_artifact_publication": TRAINING_ARTIFACT_PUBLICATION,
            "materialized_input_validation": materialized_validation,
            "checkpoint_verifier": {
                "path": repo_relative(repo, verifier_source),
                "sha256": verifier_source_sha256,
                "git_head": git_head,
                "container_image_id": image_id,
                "gpu_required": False,
                "read_only": True,
            },
            "deterministic_named_containers": True,
        },
        "budget": {
            "gpu_queue": [0, 1],
            "stop_starting_new_runs_seconds": STOP_START_SECONDS,
            "wall_guard_seconds": WALL_GUARD_SECONDS,
            "checkpoint_steps": list(CHECKPOINT_STEPS),
            "checkpoint_grace_seconds": checkpoint_grace_seconds,
            "finalization_grace_seconds": finalization_grace_seconds,
            "signal_grace_seconds": signal_grace_seconds,
        },
        "guard": {
            "triggered": False,
            "triggered_at": None,
            "partial": False,
            "completion": False,
            "emergency_timeout": False,
            "policy": "at 9h stop each active run immediately after its next durable 5k checkpoint",
        },
        "jobs": records,
        **_manifest_totals(records),
    }
    atomic_json(driver_manifest_path, manifest)

    def publish() -> None:
        manifest.update(_manifest_totals(records))
        manifest["guard"].update(
            {
                "triggered": guard_triggered,
                "triggered_at": guard_triggered_at,
                "partial": not all(row.get("completed") for row in records),
                "completion": all(row.get("completed") for row in records),
                "emergency_timeout": emergency_guard_timeout,
            }
        )
        atomic_json(driver_manifest_path, manifest)

    try:
        while active or pending:
            now = clock()
            elapsed = now - start

            # Reap before scheduling so a freed GPU can take the next queued job.
            for gpu, running in list(active.items()):
                return_code = running.process.poll()
                if return_code is None:
                    continue
                running.log_stream.close()
                _cleanup_container(repo, running.container_name)
                owned_container_names.discard(running.container_name)
                row = by_id[running.job.job_id]
                _refresh_job_record(
                    repo,
                    row,
                    running.job,
                    image_id=image_id,
                    verifier_source_sha256=verifier_source_sha256,
                )
                row["return_code"] = int(return_code)
                row["finished_at"] = utc_now()
                if row["completed"]:
                    row["state"] = "completed"
                elif running.guard_signal_sent_at is not None:
                    row["state"] = "partial_guarded"
                    row["guard_reason"] = (
                        "9h guard: stopped after next durable 5k checkpoint"
                    )
                else:
                    row["state"] = "failed"
                del active[gpu]
                publish()

            if not guard_triggered and elapsed >= WALL_GUARD_SECONDS:
                guard_triggered = True
                guard_triggered_at = utc_now()
                for running in active.values():
                    state = inspect_run_state(
                        repo,
                        running.job,
                        expected_image_id=image_id,
                        verifier_source_sha256=verifier_source_sha256,
                    )
                    running.guard_target_step = next_checkpoint_target(
                        state["last_completed_steps"]
                    )
                    row = by_id[running.job.job_id]
                    row["guard_target_step"] = running.guard_target_step
                publish()

            # The 8.5 h gate and every immutable binding are checked before Popen.
            if may_start_new_run(elapsed) and not guard_triggered:
                for gpu in (0, 1):
                    if gpu in active or not pending:
                        continue
                    if not may_start_new_run(clock() - start):
                        break
                    if query_git_head(repo) != git_head:
                        raise DriverError("git HEAD changed during the run queue")
                    if query_image_id(repo) != image_id:
                        raise DriverError("Docker image ID changed during the run queue")
                    require_clean_execution_tree(
                        repo,
                        expected_status_sha256=execution_status_sha256,
                    )
                    if sha256_file(verifier_source) != verifier_source_sha256:
                        raise DriverError(
                            "checkpoint verifier source changed during the run queue"
                        )
                    if query_compose_config_sha256(repo) != compose_config_sha256:
                        raise DriverError(
                            "resolved Docker Compose config changed during the run queue"
                        )
                    job = pending[0]
                    _verify_launch_bindings(
                        resolved_manifest_path=resolved_manifest_path,
                        resolved_manifest_sha256=resolved_manifest_sha256,
                        job=job,
                    )
                    _assert_container_absent(repo, job.container_name)
                    # Register ownership before Popen so interruption in the
                    # compose startup window is still covered by finally.
                    owned_container_names.add(job.container_name)
                    pending.popleft()
                    row = by_id[job.job_id]
                    if job.out_host.is_symlink():
                        raise DriverError(
                            f"job output must not be a symlink: {job.out_host}"
                        )
                    job.out_host.mkdir(parents=True, exist_ok=True)
                    job.out_host.chmod(0o775)
                    command = command_for(
                        job.config_container,
                        gpu,
                        container_name=job.container_name,
                    )
                    if not command_is_docker_only(command):
                        raise DriverError("refusing a non-Docker training command")
                    log_path = logs_dir / f"{job.job_id}.log"
                    log_stream = log_path.open("ab", buffering=0)
                    try:
                        process = popen_factory(
                            command,
                            cwd=repo,
                            stdout=log_stream,
                            stderr=subprocess.STDOUT,
                            start_new_session=True,
                        )
                    except BaseException:
                        log_stream.close()
                        raise
                    started_at = utc_now()
                    active[gpu] = Running(
                        job=job,
                        gpu=gpu,
                        process=process,
                        log_stream=log_stream,
                        command=command,
                        container_name=job.container_name,
                        started_monotonic=clock(),
                        started_at=started_at,
                    )
                    row.update(
                        {
                            "state": "running",
                            "gpu": gpu,
                            "command": command,
                            "command_string": shlex.join(command),
                            "started_at": started_at,
                            "log_path": repo_relative(repo, log_path),
                        }
                    )
                    publish()

            if guard_triggered:
                for running in active.values():
                    row = by_id[running.job.job_id]
                    state = inspect_run_state(
                        repo,
                        running.job,
                        expected_image_id=image_id,
                        verifier_source_sha256=verifier_source_sha256,
                    )
                    row.update(state)
                    target = running.guard_target_step
                    if target is None or (
                        target == MAX_ITER
                        and checkpoint_is_durable(running.job.out_host, MAX_ITER)
                    ):
                        # The 20k checkpoint is partial until the final eval and
                        # process_completed epilogue finish. Allow a separate hour.
                        if running.final_checkpoint_seen_at is None:
                            running.final_checkpoint_seen_at = now
                        if (
                            not state["completed"]
                            and now - running.final_checkpoint_seen_at
                            >= finalization_grace_seconds
                            and running.terminate_sent_at is None
                        ):
                            _signal_running(repo, running, signal.SIGTERM)
                            running.terminate_sent_at = now
                            row["guard_reason"] = (
                                "20k checkpoint completion epilogue exceeded "
                                f"{finalization_grace_seconds:g}s; left partial and non-eligible"
                            )
                            publish()
                        if (
                            running.terminate_sent_at is not None
                            and running.process.poll() is None
                            and now - running.terminate_sent_at >= signal_grace_seconds
                            and running.kill_sent_at is None
                        ):
                            _signal_running(repo, running, signal.SIGKILL)
                            running.kill_sent_at = now
                        continue

                    if checkpoint_is_durable(running.job.out_host, target):
                        if running.guard_signal_sent_at is None:
                            _signal_running(repo, running, signal.SIGINT)
                            running.guard_signal_sent_at = now
                            row["guard_reason"] = (
                                f"9h guard reached durable {target} checkpoint"
                            )
                            publish()
                    elif now - (start + WALL_GUARD_SECONDS) > checkpoint_grace_seconds:
                        emergency_guard_timeout = True
                        if running.terminate_sent_at is None:
                            _signal_running(repo, running, signal.SIGTERM)
                            running.terminate_sent_at = now
                            row["guard_reason"] = (
                                f"emergency timeout before target checkpoint {target}"
                            )
                            publish()
                    if (
                        running.guard_signal_sent_at is not None
                        and running.process.poll() is None
                        and now - running.guard_signal_sent_at >= signal_grace_seconds
                        and running.terminate_sent_at is None
                    ):
                        _signal_running(repo, running, signal.SIGTERM)
                        running.terminate_sent_at = now
                    if (
                        running.terminate_sent_at is not None
                        and running.process.poll() is None
                        and now - running.terminate_sent_at >= signal_grace_seconds
                        and running.kill_sent_at is None
                    ):
                        _signal_running(repo, running, signal.SIGKILL)
                        running.kill_sent_at = now

            if not active and pending and not may_start_new_run(elapsed):
                break
            if active or (pending and may_start_new_run(elapsed)):
                sleeper(poll_seconds)

        for job in pending:
            row = by_id[job.job_id]
            row["state"] = "deferred_8p5h_gate"
            row["guard_reason"] = "not started after 8.5h gate"
            _refresh_job_record(
                repo,
                row,
                job,
                image_id=image_id,
                verifier_source_sha256=verifier_source_sha256,
            )

        for row, job in zip(records, jobs):
            _refresh_job_record(
                repo,
                row,
                job,
                image_id=image_id,
                verifier_source_sha256=verifier_source_sha256,
            )
        manifest["finished_at"] = utc_now()
        if all(row["completed"] for row in records):
            manifest["state"] = "complete"
        elif any(row["state"] == "failed" for row in records):
            manifest["state"] = "failed_partial"
        else:
            manifest["state"] = "guarded_partial"
        publish()
        return manifest
    finally:
        # An exception, Ctrl-C, or parent death must not leave unnamed/orphaned
        # training containers. Only names launched by this invocation are touched.
        cleanup_errors: list[str] = []
        active_names = {running.container_name for running in active.values()}
        for running in list(active.values()):
            try:
                if running.process.poll() is None:
                    _stop_container(repo, running.container_name, timeout_seconds=10)
                    if running.process.poll() is None:
                        _signal_process_group(running, signal.SIGKILL)
                _cleanup_container(repo, running.container_name)
            except Exception as exc:
                cleanup_errors.append(
                    f"{running.container_name}: {type(exc).__name__}: {exc}"
                )
            finally:
                if not running.log_stream.closed:
                    running.log_stream.close()
        for container_name in sorted(owned_container_names - active_names):
            try:
                _stop_container(repo, container_name, timeout_seconds=10)
                _cleanup_container(repo, container_name)
            except Exception as exc:
                cleanup_errors.append(
                    f"{container_name}: {type(exc).__name__}: {exc}"
                )
        if cleanup_errors:
            raise DriverError("container cleanup failed: " + "; ".join(cleanup_errors))


def execute_queue(
    *,
    repo: Path,
    resolved_manifest_path: Path,
    driver_manifest_path: Path,
    jobs: list[Job],
    image_id: str,
    git_head: str,
    poll_seconds: float,
    checkpoint_grace_seconds: float,
    signal_grace_seconds: float,
    finalization_grace_seconds: float = FINALIZATION_GRACE_SECONDS,
    clock: Callable[[], float] = time.monotonic,
    sleeper: Callable[[float], None] = time.sleep,
    popen_factory: Callable[..., subprocess.Popen] = subprocess.Popen,
) -> dict[str, Any]:
    # Fail before creating the lock/manifest if this host process cannot share
    # ownership with the hard-coded training-container identity.
    require_host_driver_identity()
    if driver_manifest_path.is_symlink():
        raise DriverError("driver manifest must not be a symlink")
    driver_manifest_path = driver_manifest_path.resolve()
    try:
        driver_manifest_path.relative_to(repo.resolve())
    except ValueError as exc:
        raise DriverError("driver manifest escapes repository") from exc
    with exclusive_driver_lock(driver_manifest_path):
        return _execute_queue_locked(
            repo=repo,
            resolved_manifest_path=resolved_manifest_path,
            driver_manifest_path=driver_manifest_path,
            jobs=jobs,
            image_id=image_id,
            git_head=git_head,
            poll_seconds=poll_seconds,
            checkpoint_grace_seconds=checkpoint_grace_seconds,
            signal_grace_seconds=signal_grace_seconds,
            finalization_grace_seconds=finalization_grace_seconds,
            clock=clock,
            sleeper=sleeper,
            popen_factory=popen_factory,
        )


def parser() -> argparse.ArgumentParser:
    run_root = REPO / "phases/p2-gsjso/runs" / RUN_ID
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--resolved-manifest", type=Path, default=run_root / "training/resolved_configs/resolved_configs_manifest.json")
    result.add_argument("--driver-manifest", type=Path, default=run_root / "training/pilot_1wave_driver_manifest.json")
    result.add_argument("--dry-run", action="store_true")
    result.add_argument("--image-id", help="dry-run-only exact image ID override")
    result.add_argument("--poll-seconds", type=float, default=5.0)
    result.add_argument("--checkpoint-grace-seconds", type=float, default=3600.0)
    result.add_argument(
        "--finalization-grace-seconds",
        type=float,
        default=FINALIZATION_GRACE_SECONDS,
        help="time allowed after durable 20k for final evaluation and completion epilogue",
    )
    result.add_argument("--signal-grace-seconds", type=float, default=60.0)
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    if args.image_id and not args.dry_run:
        raise DriverError("--image-id is accepted only for non-executing dry-run")
    if (
        args.poll_seconds <= 0
        or args.checkpoint_grace_seconds <= 0
        or args.finalization_grace_seconds <= 0
        or args.signal_grace_seconds <= 0
    ):
        raise DriverError("poll and grace durations must be positive")
    manifest_path = args.resolved_manifest.resolve()
    _, jobs = load_resolved_jobs(REPO, manifest_path)
    image_id = args.image_id or query_image_id(REPO)
    if re.fullmatch(r"sha256:[0-9a-f]{64}", image_id) is None:
        raise DriverError("image ID must be sha256: plus 64 lowercase hex digits")
    git_head = query_git_head(REPO)
    if args.dry_run:
        payload = _dry_run_payload(REPO, manifest_path, jobs, image_id, git_head)
        print(json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False))
        return 0
    result = execute_queue(
        repo=REPO,
        resolved_manifest_path=manifest_path,
        driver_manifest_path=args.driver_manifest.resolve(),
        jobs=jobs,
        image_id=image_id,
        git_head=git_head,
        poll_seconds=args.poll_seconds,
        checkpoint_grace_seconds=args.checkpoint_grace_seconds,
        signal_grace_seconds=args.signal_grace_seconds,
        finalization_grace_seconds=args.finalization_grace_seconds,
    )
    print(json.dumps({"state": result["state"], **_manifest_totals(result["jobs"])}, indent=2))
    return 0 if result["state"] in {"complete", "guarded_partial"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
