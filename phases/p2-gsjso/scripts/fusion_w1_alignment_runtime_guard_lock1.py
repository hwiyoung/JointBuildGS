#!/usr/bin/env python3
"""Fail-closed runtime/provenance guard for FUS-W1 Gate A lock1.

Integration contract
====================

This module is deliberately separate from the numerical Gate A implementation.
The supported execution sequence is:

1. ``run_fusion_w1_alignment_gate_lock1.sh`` starts the exact pinned tools image
   without a GPU, with the host PID namespace and a single-writer lock.
2. ``launch`` verifies the immutable section-0 receipts, current git
   provenance, host-control mirror, exact runtime image, cgroup/mount
   contract, all locked inputs, and the complete training-image aggregate.
3. A fresh host PID/container/GPU-compute probe is written atomically to the
   guard receipt. Known training blocks this CPU Gate. Unknown GPU work (or an
   unavailable compute query) is recorded as a mandatory downstream GPU-stage
   block but does not make this CPU-only measurement use CUDA.
4. The Gate process receives that receipt via ``--execution-guard`` while this
   process keeps the advisory single-writer lock for the child's full lifetime.
5. Immediately before publishing a complete Gate result, the numerical module
   should call ``revalidate_before_publish(config_path, receipt_path)`` and
   include the returned evidence in its manifest. A failed revalidation must
   prevent publication.

The guard neither measures alignment nor imports the numerical implementation.
It never launches training, readout, Roofer, or scoring.
"""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import importlib.metadata
import json
import os
import platform
import re
import socket
import subprocess
import sys
import tempfile
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Iterator, Mapping, Sequence


REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_CONFIG = (
    REPO_ROOT / "phases/p2-gsjso/configs/fusion_w1_alignment_gate_lock1.json"
)
DEFAULT_RECEIPT = (
    REPO_ROOT
    / "phases/p2-gsjso/runs/20260724_fusion_w1"
    / "w1_align_execution_guard.json"
)
DEFAULT_LOCK = (
    REPO_ROOT
    / "phases/p2-gsjso/runs/20260724_fusion_w1"
    / "w1_align_gate.lock"
)
DEFAULT_HOST_CONTROL = Path("/host-control/JointBuildGS")

EXPECTED_BRANCH = "exp/fusion-w1"
PINNED_TOOLS_REFERENCE = "jointbuildgs-p0-tools:t0"
PINNED_TOOLS_IMAGE_ID = (
    "sha256:87bea02e5598a3d53a119b754191673497d52641bd8ea4106ffee653407579b0"
)
EXPECTED_MEMORY_BYTES = 24 * 1024**3
EXPECTED_SWAP_BYTES_CGROUP_V2 = 0
PASS_LIKE = {"passed", "passed_with_caveat"}
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")

RUNTIME_FILES = (
    "phases/p2-gsjso/scripts/fusion_w1_alignment_runtime_guard_lock1.py",
    "phases/p2-gsjso/scripts/run_fusion_w1_alignment_gate_lock1.sh",
    "phases/p2-gsjso/scripts/test_fusion_w1_alignment_runtime_guard_lock1.py",
)
LOCKED_GATE_SCRIPT = (
    "phases/p2-gsjso/scripts/fusion_w1_alignment_gate_lock1.py"
)


class RuntimeGuardError(RuntimeError):
    """A fail-closed runtime or provenance contract failure."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeGuardError(f"cannot read JSON object {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise RuntimeGuardError(f"JSON root must be an object: {path}")
    return payload


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path, chunk_bytes: int = 8 * 1024 * 1024) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            while True:
                chunk = handle.read(chunk_bytes)
                if not chunk:
                    break
                digest.update(chunk)
    except OSError as exc:
        raise RuntimeGuardError(f"cannot hash {path}: {exc}") from exc
    return digest.hexdigest()


def canonical_json_sha256(payload: Any) -> str:
    raw = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return sha256_bytes(raw)


def atomic_write_json(path: Path, payload: Mapping[str, Any]) -> None:
    if not path.parent.is_dir() or path.parent.is_symlink():
        raise RuntimeGuardError(
            f"receipt parent must be an existing non-symlink directory: "
            f"{path.parent}"
        )
    rendered = (
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    )
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary_path = Path(handle.name)
            handle.write(rendered)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
        directory_fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    except OSError as exc:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
        raise RuntimeGuardError(
            f"cannot atomically write guard receipt {path}: {exc}"
        ) from exc


def run(
    command: Sequence[str],
    *,
    cwd: Path = REPO_ROOT,
    check: bool = True,
    timeout: int = 300,
    env: Mapping[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    try:
        completed = subprocess.run(
            list(command),
            cwd=cwd,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=timeout,
            env=None if env is None else dict(env),
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeGuardError(
            f"command could not run: {' '.join(command)}: {exc}"
        ) from exc
    if check and completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise RuntimeGuardError(
            f"command failed rc={completed.returncode}: "
            f"{' '.join(command)}: {detail or '(no output)'}"
        )
    return completed


def run_bytes(
    command: Sequence[str],
    *,
    cwd: Path = REPO_ROOT,
    check: bool = True,
    timeout: int = 300,
) -> subprocess.CompletedProcess[bytes]:
    try:
        completed = subprocess.run(
            list(command),
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeGuardError(
            f"command could not run: {' '.join(command)}: {exc}"
        ) from exc
    if check and completed.returncode != 0:
        detail = completed.stderr.decode(
            "utf-8", errors="replace"
        ).strip() or completed.stdout.decode("utf-8", errors="replace").strip()
        raise RuntimeGuardError(
            f"command failed rc={completed.returncode}: "
            f"{' '.join(command)}: {detail or '(no output)'}"
        )
    return completed


def git(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return run(
        [
            "git",
            "-c",
            f"safe.directory={REPO_ROOT}",
            "-C",
            str(REPO_ROOT),
            *args,
        ],
        check=check,
    )


def git_bytes(
    *args: str, check: bool = True
) -> subprocess.CompletedProcess[bytes]:
    return run_bytes(
        [
            "git",
            "-c",
            f"safe.directory={REPO_ROOT}",
            "-C",
            str(REPO_ROOT),
            *args,
        ],
        check=check,
    )


def repo_path(value: str | Path) -> Path:
    candidate = Path(value)
    if not candidate.is_absolute():
        candidate = REPO_ROOT / candidate
    resolved = candidate.resolve()
    try:
        resolved.relative_to(REPO_ROOT.resolve())
    except ValueError as exc:
        raise RuntimeGuardError(
            f"path escapes repository: {value}"
        ) from exc
    return resolved


def repo_relative(path: Path) -> str:
    try:
        return path.resolve().relative_to(REPO_ROOT.resolve()).as_posix()
    except ValueError:
        return str(path.resolve())


def find_named_record(payload: Any, name: str) -> dict[str, Any]:
    found: list[dict[str, Any]] = []

    def visit(value: Any) -> None:
        if isinstance(value, dict):
            if value.get("name") == name:
                found.append(value)
            for child in value.values():
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    visit(payload)
    if len(found) != 1:
        raise RuntimeGuardError(
            f"expected exactly one {name!r} record, found {len(found)}"
        )
    return found[0]


def _required_bool(
    payload: Mapping[str, Any], key: str, expected: bool
) -> None:
    if payload.get(key) is not expected:
        raise RuntimeGuardError(
            f"immutable receipt field {key!r} must be {expected!r}"
        )


def validate_immutable_preflight(
    config: Mapping[str, Any],
) -> dict[str, Any]:
    guard = config.get("execution_guard")
    if not isinstance(guard, Mapping):
        raise RuntimeGuardError("Gate config lacks execution_guard")
    receipt_path = repo_path(str(guard["immutable_baseline_receipt"]))
    status_path = repo_path(str(guard["immutable_baseline_status"]))
    wanted_receipt_sha = str(
        guard["immutable_baseline_receipt_sha256"]
    ).lower()
    wanted_status_sha = str(guard["immutable_baseline_status_sha256"]).lower()
    if not SHA256_RE.fullmatch(wanted_receipt_sha):
        raise RuntimeGuardError("invalid baseline receipt SHA-256 lock")
    if not SHA256_RE.fullmatch(wanted_status_sha):
        raise RuntimeGuardError("invalid baseline status SHA-256 lock")
    observed_receipt_sha = sha256_file(receipt_path)
    observed_status_sha = sha256_file(status_path)
    if observed_receipt_sha != wanted_receipt_sha:
        raise RuntimeGuardError(
            "immutable preflight receipt SHA-256 mismatch"
        )
    if observed_status_sha != wanted_status_sha:
        raise RuntimeGuardError(
            "immutable preflight status SHA-256 mismatch"
        )

    receipt = load_json(receipt_path)
    status = load_json(status_path)
    if receipt.get("overall_status") != "PASSED":
        raise RuntimeGuardError("section-0 receipt is not PASSED")
    five_pin = receipt.get("five_pin_preflight")
    if not isinstance(five_pin, Mapping):
        raise RuntimeGuardError("section-0 receipt lacks five-pin evidence")
    pins = five_pin.get("pins")
    if (
        int(five_pin.get("passed_or_caveated_count", -1)) != 5
        or not isinstance(pins, list)
        or len(pins) != 5
        or any(
            not isinstance(item, Mapping)
            or item.get("status") not in PASS_LIKE
            for item in pins
        )
    ):
        raise RuntimeGuardError("section-0 receipt is not a locked 5-of-5 pass")
    continuation = receipt.get("continuation_contract")
    if not isinstance(continuation, Mapping):
        raise RuntimeGuardError("section-0 continuation contract is missing")
    _required_bool(continuation, "section_0_resume_gate_passed", True)
    _required_bool(continuation, "learning_entry_authorized_by_this_receipt", False)
    next_stage = str(continuation.get("next_stage_if_passed", ""))
    if "Gate A" not in next_stage:
        raise RuntimeGuardError("section-0 receipt no longer requires Gate A")

    if status.get("status") != "PASSED":
        raise RuntimeGuardError("section-0 status receipt is not PASSED")
    if (
        int(status.get("five_pin_passed_or_caveated_count", -1)) != 5
        or int(status.get("five_pin_total_count", -1)) != 5
    ):
        raise RuntimeGuardError("status receipt is not a locked 5-of-5 pass")
    _required_bool(status, "continuation_authorized", True)
    _required_bool(status, "learning_still_gated_by_gate_a", True)
    _required_bool(status, "actual_training_started", False)
    _required_bool(status, "actual_readout_started", False)
    implementation = status.get("implementation_provenance")
    if not isinstance(implementation, Mapping):
        raise RuntimeGuardError("status receipt lacks implementation provenance")
    _required_bool(implementation, "all_working_and_head_match", True)
    status_preflight = status.get("preflight_resume")
    if (
        not isinstance(status_preflight, Mapping)
        or status_preflight.get("sha256") != wanted_receipt_sha
    ):
        raise RuntimeGuardError(
            "status receipt does not cross-lock the immutable preflight"
        )
    time_policy = status.get("time_policy")
    if not isinstance(time_policy, Mapping):
        raise RuntimeGuardError("status receipt lacks amended time policy")
    _required_bool(time_policy, "continue_after_snapshot", True)
    _required_bool(time_policy, "hard_stop_at_snapshot", False)

    git_pin = find_named_record(
        receipt, "git_commit_branch_dispatch_lock"
    )
    git_evidence = git_pin.get("evidence")
    if not isinstance(git_evidence, Mapping):
        raise RuntimeGuardError("preflight git pin lacks evidence")
    dispatch = git_evidence.get("dispatch")
    amendment = git_evidence.get("protocol_amendment")
    if not isinstance(dispatch, Mapping) or not isinstance(amendment, Mapping):
        raise RuntimeGuardError(
            "preflight receipt lacks dispatch/amendment provenance"
        )
    dispatch_commit = str(dispatch.get("lock_commit", ""))
    amendment_commit = str(amendment.get("lock_commit", ""))
    if (
        not re.fullmatch(r"[0-9a-f]{40}", dispatch_commit)
        or not re.fullmatch(r"[0-9a-f]{40}", amendment_commit)
    ):
        raise RuntimeGuardError("invalid dispatch/amendment commit lock")
    if time_policy.get("amendment_commit") != amendment_commit:
        raise RuntimeGuardError(
            "status time policy and preflight amendment commits differ"
        )
    _required_bool(dispatch, "working_and_committed_match", True)
    _required_bool(amendment, "working_and_committed_match", True)

    return {
        "status": "passed",
        "receipt": {
            "path": repo_relative(receipt_path),
            "sha256": observed_receipt_sha,
            "overall_status": receipt["overall_status"],
            "five_pin_passed_or_caveated_count": 5,
            "section_0_resume_gate_passed": True,
            "learning_entry_authorized": False,
            "next_stage_if_passed": next_stage,
        },
        "status_receipt": {
            "path": repo_relative(status_path),
            "sha256": observed_status_sha,
            "status": status["status"],
            "five_pin": "5/5",
            "continuation_authorized": True,
            "learning_still_gated_by_gate_a": True,
            "actual_training_started": False,
            "actual_readout_started": False,
        },
        "dispatch_commit": dispatch_commit,
        "amendment_commit": amendment_commit,
        "baseline_payload": receipt,
    }


def _implementation_paths(config: Mapping[str, Any]) -> list[str]:
    git_lock = config.get("git_lock")
    if not isinstance(git_lock, Mapping):
        raise RuntimeGuardError("Gate config lacks git_lock")
    configured = git_lock.get("implementation_files")
    if not isinstance(configured, list):
        raise RuntimeGuardError("Gate implementation_files must be a list")
    paths: list[str] = []
    for value in configured:
        if isinstance(value, str):
            path = value
        elif isinstance(value, Mapping) and isinstance(value.get("path"), str):
            path = str(value["path"])
        else:
            raise RuntimeGuardError("invalid Gate implementation file entry")
        if path not in paths:
            paths.append(path)
    for path in RUNTIME_FILES:
        if path not in paths:
            paths.append(path)
    expected_minimum = {
        "phases/p2-gsjso/configs/fusion_w1_alignment_gate_lock1.json",
        LOCKED_GATE_SCRIPT,
        "phases/p2-gsjso/scripts/run_fusion_w1_alignment_gate_lock1.sh",
        "phases/p2-gsjso/scripts/test_fusion_w1_alignment_gate_lock1.py",
        *RUNTIME_FILES,
    }
    missing = sorted(expected_minimum - set(paths))
    if missing:
        raise RuntimeGuardError(
            "Gate implementation contract is incomplete: "
            + ", ".join(missing)
        )
    return paths


def validate_git_provenance(
    config: Mapping[str, Any],
    *,
    dispatch_commit: str,
    amendment_commit: str,
) -> dict[str, Any]:
    expected_branch = str(
        config.get("git_lock", {}).get("expected_branch", "")
    )
    if expected_branch != EXPECTED_BRANCH:
        raise RuntimeGuardError("Gate config branch lock drift")
    branch = git("branch", "--show-current").stdout.strip()
    head = git("rev-parse", "HEAD").stdout.strip()
    if branch != expected_branch:
        raise RuntimeGuardError(
            f"wrong branch: {branch!r}, expected {expected_branch!r}"
        )
    ancestors: dict[str, Any] = {}
    for name, commit in (
        ("dispatch", dispatch_commit),
        ("protocol_amendment", amendment_commit),
    ):
        exists = (
            git("cat-file", "-t", commit, check=False).stdout.strip()
            == "commit"
        )
        ancestor = (
            exists
            and git(
                "merge-base", "--is-ancestor", commit, head, check=False
            ).returncode
            == 0
        )
        ancestors[name] = {
            "commit": commit,
            "exists": exists,
            "ancestor_of_head": ancestor,
        }
        if not ancestor:
            raise RuntimeGuardError(
                f"{name} commit is not an ancestor of current HEAD"
            )

    tracked_changes = git(
        "status", "--porcelain=v1", "--untracked-files=no"
    ).stdout.splitlines()
    if tracked_changes:
        raise RuntimeGuardError(
            "tracked worktree/index is not clean: "
            + "; ".join(tracked_changes[:20])
        )

    implementation_rows: list[dict[str, Any]] = []
    for relative in _implementation_paths(config):
        path = repo_path(relative)
        if not path.is_file() or path.is_symlink():
            raise RuntimeGuardError(
                f"implementation file is missing/non-regular: {relative}"
            )
        blob = git_bytes("show", f"HEAD:{relative}", check=False)
        if blob.returncode != 0:
            raise RuntimeGuardError(
                f"implementation file is not committed at HEAD: {relative}"
            )
        working = path.read_bytes()
        matches = working == blob.stdout
        row = {
            "path": relative,
            "working_sha256": sha256_bytes(working),
            "head_blob_sha256": sha256_bytes(blob.stdout),
            "working_and_head_match": matches,
        }
        implementation_rows.append(row)
        if not matches:
            raise RuntimeGuardError(
                f"working implementation differs from HEAD: {relative}"
            )

    return {
        "status": "passed",
        "branch": branch,
        "expected_branch": expected_branch,
        "head": head,
        "tracked_worktree_changes": [],
        "required_ancestors": ancestors,
        "implementation_files": implementation_rows,
        "implementation_all_committed_and_head_match": True,
    }


def _mount_rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    try:
        lines = Path("/proc/self/mountinfo").read_text(
            encoding="utf-8"
        ).splitlines()
    except OSError as exc:
        raise RuntimeGuardError(f"cannot read mountinfo: {exc}") from exc
    for line in lines:
        left, separator, right = line.partition(" - ")
        if not separator:
            continue
        fields = left.split()
        right_fields = right.split()
        if len(fields) < 6 or len(right_fields) < 3:
            continue
        rows.append(
            {
                "mount_point": fields[4].replace("\\040", " "),
                "mount_options": fields[5].split(","),
                "filesystem": right_fields[0],
                "source": right_fields[1],
                "super_options": right_fields[2].split(","),
            }
        )
    return rows


def _mount_for(path: Path, rows: Sequence[Mapping[str, Any]]) -> Mapping[str, Any]:
    wanted = path.as_posix()
    matches = [
        row
        for row in rows
        if wanted == str(row["mount_point"])
        or wanted.startswith(str(row["mount_point"]).rstrip("/") + "/")
    ]
    if not matches:
        raise RuntimeGuardError(f"no mountinfo record covers {path}")
    return max(matches, key=lambda row: len(str(row["mount_point"])))


def _read_cgroup_value(name: str) -> str | None:
    path = Path("/sys/fs/cgroup") / name
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return None


def validate_container_contract(
    host_control_root: Path,
) -> dict[str, Any]:
    if not Path("/.dockerenv").exists():
        raise RuntimeGuardError("Gate runtime must be inside Docker")
    if not Path("/var/run/docker.sock").is_socket():
        raise RuntimeGuardError("Docker socket is not mounted")
    if not Path("/usr/local/bin/docker").is_file():
        raise RuntimeGuardError("read-only Docker CLI bind is missing")
    if not host_control_root.is_dir():
        raise RuntimeGuardError("read-only host-control repository is missing")
    if os.geteuid() == 0 or os.getegid() == 0:
        raise RuntimeGuardError("Gate container must run as the caller UID/GID")
    if os.environ.get("MPLCONFIGDIR") != "/tmp/matplotlib":
        raise RuntimeGuardError("MPLCONFIGDIR must be /tmp/matplotlib")
    if os.environ.get("CUDA_VISIBLE_DEVICES") not in ("", "-1"):
        raise RuntimeGuardError("Gate CPU container exposes CUDA visibility")
    if os.environ.get("NVIDIA_VISIBLE_DEVICES") not in ("void", "none"):
        raise RuntimeGuardError("Gate CPU container exposes NVIDIA devices")

    nspid_line = next(
        (
            line
            for line in Path("/proc/self/status").read_text(
                encoding="utf-8"
            ).splitlines()
            if line.startswith("NSpid:")
        ),
        "",
    )
    nspids = nspid_line.split()[1:]
    if len(nspids) != 1:
        raise RuntimeGuardError(
            "host PID namespace is not visible (NSpid must have one value)"
        )

    mounts = _mount_rows()
    root_mount = _mount_for(Path("/"), mounts)
    repo_mount = _mount_for(REPO_ROOT, mounts)
    control_mount = _mount_for(host_control_root, mounts)
    socket_path = Path("/var/run/docker.sock").resolve()
    cli_path = Path("/usr/local/bin/docker").resolve()
    socket_mount = _mount_for(socket_path, mounts)
    cli_mount = _mount_for(cli_path, mounts)
    if "ro" not in root_mount["mount_options"]:
        raise RuntimeGuardError("container root filesystem is not read-only")
    if "rw" not in repo_mount["mount_options"]:
        raise RuntimeGuardError("repository bind is not writable")
    if "ro" not in control_mount["mount_options"]:
        raise RuntimeGuardError("host-control bind is not read-only")
    if (
        socket_mount["mount_point"] != socket_path.as_posix()
        or "ro" not in socket_mount["mount_options"]
    ):
        raise RuntimeGuardError("Docker socket bind is not marked read-only")
    if (
        cli_mount["mount_point"] != cli_path.as_posix()
        or "ro" not in cli_mount["mount_options"]
    ):
        raise RuntimeGuardError("Docker CLI bind is not read-only")

    memory_max = _read_cgroup_value("memory.max")
    memory_swap_max = _read_cgroup_value("memory.swap.max")
    if memory_max != str(EXPECTED_MEMORY_BYTES):
        raise RuntimeGuardError(
            f"memory.max is {memory_max!r}, expected {EXPECTED_MEMORY_BYTES}"
        )
    if memory_swap_max != str(EXPECTED_SWAP_BYTES_CGROUP_V2):
        raise RuntimeGuardError(
            "memory.swap.max must be 0 for --memory=24g "
            "--memory-swap=24g under cgroup v2"
        )

    gpu_devices = sorted(
        str(path) for path in Path("/dev").glob("nvidia*")
    )
    if gpu_devices:
        raise RuntimeGuardError(
            "Gate measurement container unexpectedly exposes NVIDIA devices"
        )

    return {
        "status": "passed",
        "inside_docker": True,
        "uid": os.geteuid(),
        "gid": os.getegid(),
        "host_pid_namespace_visible": True,
        "nspid": nspids,
        "rootfs_read_only": True,
        "repo_bind_read_write": True,
        "host_control_bind_read_only": True,
        "docker_socket_bind_read_only": True,
        "docker_cli_bind_read_only": True,
        "memory_max_bytes": int(memory_max),
        "memory_swap_max_bytes": int(memory_swap_max),
        "wrapper_memory_flags": ["--memory=24g", "--memory-swap=24g"],
        "mplconfigdir": os.environ["MPLCONFIGDIR"],
        "cuda_visible_devices": os.environ.get("CUDA_VISIBLE_DEVICES"),
        "nvidia_visible_devices": os.environ.get("NVIDIA_VISIBLE_DEVICES"),
        "nvidia_device_nodes": gpu_devices,
        "measurement_container_cuda_used": False,
    }


def docker_json(command: Sequence[str]) -> Any:
    completed = run(command)
    try:
        return json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeGuardError(
            f"Docker returned invalid JSON: {' '.join(command)}"
        ) from exc


def runtime_versions_and_image() -> dict[str, Any]:
    reference_payload = docker_json(
        ["docker", "image", "inspect", PINNED_TOOLS_REFERENCE]
    )
    if not isinstance(reference_payload, list) or len(reference_payload) != 1:
        raise RuntimeGuardError("unexpected pinned tools image inspect result")
    reference_image_id = reference_payload[0].get("Id")
    if reference_image_id != PINNED_TOOLS_IMAGE_ID:
        raise RuntimeGuardError(
            "pinned tools tag resolves to a different image ID"
        )

    container_id = socket.gethostname()
    container_payload = docker_json(
        ["docker", "container", "inspect", container_id]
    )
    if not isinstance(container_payload, list) or len(container_payload) != 1:
        raise RuntimeGuardError("cannot inspect current Gate container")
    current_image_id = container_payload[0].get("Image")
    if current_image_id != PINNED_TOOLS_IMAGE_ID:
        raise RuntimeGuardError(
            "Gate container is not running the exact pinned tools image ID"
        )

    docker_version = docker_json(
        ["docker", "version", "--format", "{{json .}}"]
    )
    packages: dict[str, str | None] = {}
    for name in (
        "numpy",
        "laspy",
        "pyproj",
        "matplotlib",
        "Pillow",
        "GDAL",
    ):
        try:
            packages[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            packages[name] = None
    return {
        "status": "passed",
        "tools_image_reference": PINNED_TOOLS_REFERENCE,
        "expected_tools_image_id": PINNED_TOOLS_IMAGE_ID,
        "reference_tools_image_id": reference_image_id,
        "current_container_id": container_payload[0].get("Id"),
        "current_container_image_id": current_image_id,
        "current_container_config_image": container_payload[0]
        .get("Config", {})
        .get("Image"),
        "python": platform.python_version(),
        "python_executable": sys.executable,
        "platform": platform.platform(),
        "packages": packages,
        "docker": docker_version,
        "measurement_container_cuda_used": False,
    }


def validate_host_control_mirror(
    config_path: Path,
    config: Mapping[str, Any],
    baseline: Mapping[str, Any],
    git_evidence: Mapping[str, Any],
    host_control_root: Path,
) -> dict[str, Any]:
    paths = [
        repo_relative(config_path),
        str(baseline["receipt"]["path"]),
        str(baseline["status_receipt"]["path"]),
        *(
            str(row["path"])
            for row in git_evidence["implementation_files"]
        ),
    ]
    rows: list[dict[str, Any]] = []
    for relative in dict.fromkeys(paths):
        workspace = repo_path(relative)
        control = host_control_root / relative
        if not control.is_file():
            raise RuntimeGuardError(
                f"host-control mirror lacks contracted file: {relative}"
            )
        workspace_sha = sha256_file(workspace)
        control_sha = sha256_file(control)
        matches = workspace_sha == control_sha
        rows.append(
            {
                "path": relative,
                "workspace_sha256": workspace_sha,
                "host_control_sha256": control_sha,
                "matches": matches,
            }
        )
        if not matches:
            raise RuntimeGuardError(
                f"host-control mirror is stale for {relative}"
            )
    return {
        "status": "passed",
        "host_control_root": str(host_control_root),
        "files": rows,
        "all_match": True,
    }


def sha256sum_stream_aggregate(
    logical_root: Path,
) -> tuple[str, int, int]:
    if not logical_root.is_dir():
        raise RuntimeGuardError(
            f"training image directory is missing: {logical_root}"
        )
    files = sorted(
        (path for path in logical_root.iterdir() if path.is_file()),
        key=lambda path: path.as_posix().encode("utf-8"),
    )
    aggregate = hashlib.sha256()
    total_bytes = 0
    for path in files:
        digest = sha256_file(path)
        size = path.stat().st_size
        total_bytes += size
        logical = path.relative_to(REPO_ROOT).as_posix()
        aggregate.update(f"{digest}  {logical}\n".encode("utf-8"))
    return aggregate.hexdigest(), len(files), total_bytes


def provided_views_lock(
    config: Mapping[str, Any],
) -> tuple[str, str] | None:
    """Return the optional result-blind views CSV lock or fail on half-locks."""

    view_selection = config.get("view_selection")
    if not isinstance(view_selection, Mapping):
        raise RuntimeGuardError("Gate config lacks view_selection")
    path_value = view_selection.get("provided_views_csv_path")
    sha_value = view_selection.get("provided_views_csv_sha256")
    input_locks = config.get("input_locks")
    if isinstance(input_locks, Mapping):
        alternate_path = input_locks.get("provided_views_csv")
        alternate_sha = input_locks.get("provided_views_csv_sha256")
        if alternate_path is not None or alternate_sha is not None:
            if path_value is not None and alternate_path != path_value:
                raise RuntimeGuardError(
                    "provided views path locks conflict across config sections"
                )
            if sha_value is not None and alternate_sha != sha_value:
                raise RuntimeGuardError(
                    "provided views SHA-256 locks conflict across config sections"
                )
            path_value = alternate_path
            sha_value = alternate_sha
    if path_value is None and sha_value is None:
        return None
    if (
        not isinstance(path_value, str)
        or not path_value.strip()
        or not isinstance(sha_value, str)
        or not SHA256_RE.fullmatch(sha_value.lower())
    ):
        raise RuntimeGuardError(
            "provided views CSV requires both an explicit repo path and SHA-256"
        )
    path = repo_path(path_value)
    if not path.is_file() or path.is_symlink():
        raise RuntimeGuardError(
            "locked provided views CSV is missing or not a regular file"
        )
    observed = sha256_file(path)
    if observed != sha_value.lower():
        raise RuntimeGuardError(
            "locked provided views CSV SHA-256 mismatch"
        )
    return repo_relative(path), observed


def rehash_gate_inputs(
    config: Mapping[str, Any],
    baseline_payload: Mapping[str, Any],
) -> dict[str, Any]:
    started = time.monotonic()
    expected = config.get("input_locks", {}).get("expected_sha256")
    if not isinstance(expected, Mapping) or not expected:
        raise RuntimeGuardError("Gate config has no input SHA-256 locks")
    rows: list[dict[str, Any]] = []
    for relative, wanted_value in sorted(expected.items()):
        wanted = str(wanted_value).lower()
        if not SHA256_RE.fullmatch(wanted):
            raise RuntimeGuardError(
                f"invalid input SHA-256 lock: {relative}"
            )
        path = repo_path(str(relative))
        if not path.is_file():
            raise RuntimeGuardError(f"locked Gate input is missing: {relative}")
        observed = sha256_file(path)
        matches = observed == wanted
        rows.append(
            {
                "path": str(relative),
                "bytes": path.stat().st_size,
                "expected_sha256": wanted,
                "sha256": observed,
                "matches_lock": matches,
            }
        )
        if not matches:
            raise RuntimeGuardError(
                f"locked Gate input SHA-256 mismatch: {relative}"
            )

    datum_relative = str(
        config.get("inputs", {}).get("projection_datum_config", "")
    )
    datum_wanted = str(
        config.get("input_locks", {}).get(
            "projection_datum_config_sha256", ""
        )
    ).lower()
    if not datum_relative or not SHA256_RE.fullmatch(datum_wanted):
        raise RuntimeGuardError("projection datum SHA-256 lock is missing")
    if datum_relative not in expected:
        datum_path = repo_path(datum_relative)
        observed = sha256_file(datum_path)
        matches = observed == datum_wanted
        rows.append(
            {
                "path": datum_relative,
                "bytes": datum_path.stat().st_size,
                "expected_sha256": datum_wanted,
                "sha256": observed,
                "matches_lock": matches,
            }
        )
        if not matches:
            raise RuntimeGuardError(
                "projection datum config SHA-256 mismatch"
            )

    views_lock = provided_views_lock(config)
    if views_lock is not None:
        views_relative, views_sha = views_lock
        if not any(row["path"] == views_relative for row in rows):
            views_path = repo_path(views_relative)
            rows.append(
                {
                    "path": views_relative,
                    "role": "provided_views_csv",
                    "bytes": views_path.stat().st_size,
                    "expected_sha256": views_sha,
                    "sha256": views_sha,
                    "matches_lock": True,
                }
            )

    canonical = find_named_record(
        baseline_payload, "canonical_input_sha256"
    )
    canonical_evidence = canonical.get("evidence")
    if not isinstance(canonical_evidence, Mapping):
        raise RuntimeGuardError(
            "baseline canonical input receipt lacks evidence"
        )
    image_lock = canonical_evidence.get("training_image_set")
    if not isinstance(image_lock, Mapping):
        raise RuntimeGuardError(
            "baseline canonical receipt lacks training image lock"
        )
    image_relative = str(
        config.get("inputs", {}).get("training_image_dir", "")
    )
    if image_relative != image_lock.get("path"):
        raise RuntimeGuardError(
            "Gate image path differs from immutable preflight image path"
        )
    image_root = repo_path(image_relative)
    aggregate, count, total_bytes = sha256sum_stream_aggregate(image_root)
    expected_aggregate = str(
        image_lock.get("expected_sha256sum_stream_aggregate")
        or image_lock.get("sha256sum_stream_aggregate")
        or ""
    )
    expected_count = int(
        image_lock.get("expected_file_count")
        or image_lock.get("file_count")
        or -1
    )
    expected_bytes = int(
        image_lock.get("expected_total_bytes")
        or image_lock.get("total_bytes")
        or -1
    )
    image_matches = (
        aggregate == expected_aggregate
        and count == expected_count
        and total_bytes == expected_bytes
    )
    if not image_matches:
        raise RuntimeGuardError(
            "training image aggregate differs from immutable preflight"
        )

    compact = {
        "files": rows,
        "training_image_set": {
            "path": image_relative,
            "sha256sum_stream_aggregate": aggregate,
            "expected_sha256sum_stream_aggregate": expected_aggregate,
            "file_count": count,
            "expected_file_count": expected_count,
            "total_bytes": total_bytes,
            "expected_total_bytes": expected_bytes,
            "matches_lock": image_matches,
            "algorithm": image_lock.get("algorithm"),
        },
    }
    return {
        "status": "passed",
        **compact,
        "snapshot_sha256": canonical_json_sha256(compact),
        "elapsed_seconds": time.monotonic() - started,
    }


def process_command(pid: int) -> str:
    try:
        raw = Path(f"/proc/{pid}/cmdline").read_bytes()
    except (FileNotFoundError, PermissionError, ProcessLookupError):
        return ""
    return raw.replace(b"\x00", b" ").decode(
        "utf-8", errors="replace"
    ).strip()


def scan_processes(
    patterns: Sequence[str],
    *,
    pids: Iterable[int] | None = None,
) -> list[dict[str, Any]]:
    compiled = [
        re.compile(pattern, flags=re.IGNORECASE) for pattern in patterns
    ]
    if pids is None:
        pids = (
            int(path.name)
            for path in Path("/proc").iterdir()
            if path.name.isdigit()
        )
    own_pid = os.getpid()
    parent_pid = os.getppid()
    matches: list[dict[str, Any]] = []
    for pid in pids:
        if pid in (own_pid, parent_pid):
            continue
        command = process_command(pid)
        if not command:
            continue
        matched = [
            pattern.pattern
            for pattern in compiled
            if pattern.search(command)
        ]
        if matched:
            matches.append(
                {
                    "pid": pid,
                    "command": command,
                    "matched_regexes": matched,
                }
            )
    return sorted(matches, key=lambda row: int(row["pid"]))


def parse_json_lines(text: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in text.splitlines():
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise RuntimeGuardError(
                "docker ps emitted invalid JSON lines"
            ) from exc
        if isinstance(value, dict):
            rows.append(value)
    return rows


def parse_compute_apps(text: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in text.splitlines():
        if not line.strip():
            continue
        parts = [part.strip() for part in line.split(",", 2)]
        if len(parts) != 3:
            rows.append(
                {
                    "pid": None,
                    "process_name": None,
                    "used_memory_mib": None,
                    "raw": line.strip(),
                    "parse_error": True,
                }
            )
            continue
        try:
            pid = int(parts[0])
            memory = int(parts[2])
        except ValueError:
            rows.append(
                {
                    "pid": None,
                    "process_name": parts[1],
                    "used_memory_mib": None,
                    "raw": line.strip(),
                    "parse_error": True,
                }
            )
            continue
        rows.append(
            {
                "pid": pid,
                "process_name": parts[1],
                "used_memory_mib": memory,
                "command": process_command(pid),
                "parse_error": False,
            }
        )
    return rows


def _training_image_lock(
    baseline_payload: Mapping[str, Any],
) -> tuple[str, str]:
    image_record = find_named_record(
        baseline_payload, "docker_image_ids_and_versions"
    )
    evidence = image_record.get("evidence")
    if not isinstance(evidence, Mapping):
        raise RuntimeGuardError("baseline Docker image pin lacks evidence")
    images = evidence.get("images")
    if not isinstance(images, Mapping):
        raise RuntimeGuardError("baseline Docker image evidence lacks images")
    training = images.get("gs_training")
    if not isinstance(training, Mapping):
        raise RuntimeGuardError("baseline lacks GS training image pin")
    reference = str(training.get("reference", ""))
    image_id = str(training.get("image_id", ""))
    if not reference or not image_id.startswith("sha256:"):
        raise RuntimeGuardError("invalid baseline GS training image pin")
    inspected = docker_json(["docker", "image", "inspect", reference])
    if (
        not isinstance(inspected, list)
        or len(inspected) != 1
        or inspected[0].get("Id") != image_id
    ):
        raise RuntimeGuardError(
            "GS training probe tag no longer resolves to preflight image ID"
        )
    return reference, image_id


def _gpu_compute_probe(
    baseline_payload: Mapping[str, Any],
) -> dict[str, Any]:
    query = [
        "--query-compute-apps=pid,process_name,used_memory",
        "--format=csv,noheader,nounits",
    ]
    try:
        direct = run(["nvidia-smi", *query], check=False, timeout=30)
    except RuntimeGuardError as exc:
        direct = subprocess.CompletedProcess(
            args=["nvidia-smi", *query],
            returncode=127,
            stdout="",
            stderr=str(exc),
        )
    if direct.returncode == 0:
        return {
            "source": "direct_cpu_container_nvidia_smi",
            "argv": ["nvidia-smi", *query],
            "returncode": 0,
            "stdout": direct.stdout,
            "stderr": direct.stderr[-2000:],
            "probe_container_used_gpu_visibility": False,
        }

    reference, image_id = _training_image_lock(baseline_payload)
    nested_argv = [
        "docker",
        "run",
        "--rm",
        "--pull=never",
        "--gpus",
        "all",
        "--read-only",
        "--network",
        "none",
        "--entrypoint",
        "nvidia-smi",
        image_id,
        *query,
    ]
    nested = run(nested_argv, check=False, timeout=90)
    return {
        "source": "ephemeral_pinned_training_image_nvidia_smi",
        "argv": nested_argv,
        "returncode": nested.returncode,
        "stdout": nested.stdout,
        "stderr": nested.stderr[-2000:],
        "direct_probe_returncode": direct.returncode,
        "direct_probe_stderr": direct.stderr[-2000:],
        "training_image_reference": reference,
        "training_image_id": image_id,
        "probe_container_used_gpu_visibility": True,
        "measurement_container_used_gpu_visibility": False,
    }


def fresh_execution_probe(
    config: Mapping[str, Any],
    baseline_payload: Mapping[str, Any],
) -> dict[str, Any]:
    guard = config.get("execution_guard")
    if not isinstance(guard, Mapping):
        raise RuntimeGuardError("Gate config lacks execution_guard")
    patterns = guard.get("local_namespace_forbidden_command_regexes")
    if not isinstance(patterns, list) or not all(
        isinstance(value, str) for value in patterns
    ):
        raise RuntimeGuardError("training process regex contract is invalid")
    process_matches = scan_processes(patterns)
    compiled = [
        re.compile(pattern, flags=re.IGNORECASE) for pattern in patterns
    ]
    containers = parse_json_lines(
        run(
            [
                "docker",
                "ps",
                "--no-trunc",
                "--format",
                "{{json .}}",
            ]
        ).stdout
    )
    container_matches: list[dict[str, Any]] = []
    relevant_containers: list[dict[str, Any]] = []
    for item in containers:
        command = str(item.get("Command", ""))
        matched = [
            pattern.pattern
            for pattern in compiled
            if pattern.search(command)
        ]
        if matched:
            container_matches.append(
                {
                    "id": item.get("ID"),
                    "name": item.get("Names"),
                    "image": item.get("Image"),
                    "command": command,
                    "matched_regexes": matched,
                }
            )
        labels = str(item.get("Labels", ""))
        image = str(item.get("Image", ""))
        names = str(item.get("Names", ""))
        if (
            "com.docker.compose.project=jointbuildgs" in labels
            or "jointbuildgs" in image.lower()
            or "jointbuildgs" in names.lower()
        ):
            relevant_containers.append(
                {
                    "id": item.get("ID"),
                    "name": names,
                    "image": image,
                    "command": command,
                    "state": item.get("State"),
                    "status": item.get("Status"),
                }
            )

    gpu_probe = _gpu_compute_probe(baseline_payload)
    gpu_rows = (
        parse_compute_apps(str(gpu_probe["stdout"]))
        if int(gpu_probe["returncode"]) == 0
        else []
    )
    known_training_absent = not process_matches and not container_matches
    downstream_block = (
        int(gpu_probe["returncode"]) != 0 or bool(gpu_rows)
    )
    host_visible = len(
        next(
            (
                line.split()[1:]
                for line in Path("/proc/self/status").read_text(
                    encoding="utf-8"
                ).splitlines()
                if line.startswith("NSpid:")
            ),
            [],
        )
    ) == 1
    evidence = {
        "host_pid_namespace_visible": host_visible,
        "forbidden_command_regexes": patterns,
        "matching_processes": process_matches,
        "matching_container_commands": container_matches,
        "relevant_running_containers": relevant_containers,
        "known_training_entry_points_absent": known_training_absent,
        "no_active_training": known_training_absent,
        "gpu_compute_probe_source": gpu_probe["source"],
        "gpu_compute_probe_argv": gpu_probe["argv"],
        "nvidia_compute_probe_returncode": gpu_probe["returncode"],
        "nvidia_compute_probe_stderr": gpu_probe["stderr"],
        "gpu_compute_processes": gpu_rows,
        "gpu_compute_processes_raw": gpu_rows,
        "unknown_gpu_compute_processes": gpu_rows,
        "future_gpu_stage_launch_blocked": downstream_block,
        "downstream_gpu_stage_launch_blocked": downstream_block,
        "cpu_gate_authorized": known_training_absent and host_visible,
        "execution_device": "cpu_numpy_only",
        "cuda_used": False,
        "measurement_container_cuda_used": False,
        "gpu_probe": {
            key: value
            for key, value in gpu_probe.items()
            if key != "stdout"
        },
        "policy": (
            "Known training blocks CPU Gate A. Unknown GPU work or a failed "
            "GPU query blocks every downstream GPU launch but is recorded as "
            "a caveat for this CPU-only alignment measurement."
        ),
    }
    if not host_visible:
        raise RuntimeGuardError("fresh probe lacks host PID namespace")
    if not known_training_absent:
        raise RuntimeGuardError(
            "fresh host process/container probe found active training"
        )
    return {
        "name": "no_active_training_guard",
        "status": (
            "passed_with_caveat" if downstream_block else "passed"
        ),
        "evidence": evidence,
    }


def validate_child_argv(
    child_argv: Sequence[str],
    config_path: Path,
    receipt_path: Path,
    *,
    config: Mapping[str, Any] | None = None,
) -> list[str]:
    argv = list(child_argv)
    if argv and argv[0] == "--":
        argv = argv[1:]
    if len(argv) < 6:
        raise RuntimeGuardError("Gate child argv is incomplete")
    if Path(argv[0]).name not in {"python", "python3"}:
        raise RuntimeGuardError("Gate child must use Python directly")
    if argv[1] != LOCKED_GATE_SCRIPT:
        raise RuntimeGuardError(
            "runtime guard may launch only the locked Gate A script"
        )

    def option_values(name: str) -> list[str]:
        values: list[str] = []
        for index, value in enumerate(argv):
            if value == name:
                if index + 1 >= len(argv):
                    raise RuntimeGuardError(f"{name} has no value")
                values.append(argv[index + 1])
            elif value.startswith(name + "="):
                values.append(value.split("=", 1)[1])
        return values

    configs = option_values("--config")
    receipts = option_values("--execution-guard")
    if len(configs) != 1 or repo_path(configs[0]) != config_path.resolve():
        raise RuntimeGuardError(
            "child argv must contain exactly one locked --config"
        )
    if (
        len(receipts) != 1
        or repo_path(receipts[0]) != receipt_path.resolve()
    ):
        raise RuntimeGuardError(
            "child argv must contain exactly one fresh --execution-guard"
        )

    locked_config = load_json(config_path) if config is None else config

    def require_optional_locked_path(
        option: str,
        configured_value: Any,
    ) -> None:
        values = option_values(option)
        if len(values) > 1:
            raise RuntimeGuardError(
                f"child argv may contain at most one {option}"
            )
        if not values:
            return
        if not isinstance(configured_value, str) or not configured_value:
            raise RuntimeGuardError(
                f"{option} is disabled without an explicit config path lock"
            )
        if repo_path(values[0]) != repo_path(configured_value):
            raise RuntimeGuardError(
                f"{option} differs from the locked config path"
            )

    inputs = locked_config.get("inputs")
    if not isinstance(inputs, Mapping):
        raise RuntimeGuardError("Gate config lacks inputs")
    require_optional_locked_path("--targets", inputs.get("targets_csv"))
    require_optional_locked_path(
        "--datum-config", inputs.get("projection_datum_config")
    )
    require_optional_locked_path("--output-dir", inputs.get("output_dir"))

    views = option_values("--views")
    if len(views) > 1:
        raise RuntimeGuardError(
            "child argv may contain at most one --views"
        )
    locked_views = provided_views_lock(locked_config)
    if views:
        if locked_views is None:
            raise RuntimeGuardError(
                "--views is disabled unless config locks its path and SHA-256"
            )
        locked_views_path, _ = locked_views
        if repo_path(views[0]) != repo_path(locked_views_path):
            raise RuntimeGuardError(
                "--views differs from the locked provided views CSV"
            )

    input_datums = option_values("--input-datum")
    if len(input_datums) > 1:
        raise RuntimeGuardError(
            "child argv may contain at most one --input-datum"
        )
    locked_datum = locked_config.get("input_locks", {}).get(
        "input_vertical_datum"
    )
    if input_datums and input_datums[0] != locked_datum:
        raise RuntimeGuardError(
            "--input-datum differs from the locked config value"
        )
    return argv


@contextmanager
def single_writer_lock(path: Path) -> Iterator[dict[str, Any]]:
    if not path.parent.is_dir() or path.parent.is_symlink():
        raise RuntimeGuardError(
            f"lock parent must be an existing non-symlink directory: "
            f"{path.parent}"
        )
    try:
        handle = path.open("a+", encoding="utf-8")
    except OSError as exc:
        raise RuntimeGuardError(f"cannot open Gate lock {path}: {exc}") from exc
    try:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeGuardError(
                f"another Gate A writer holds {path}"
            ) from exc
        handle.seek(0)
        handle.truncate()
        handle.write(
            json.dumps(
                {
                    "pid": os.getpid(),
                    "created_utc": utc_now(),
                    "argv": sys.argv,
                },
                ensure_ascii=False,
                sort_keys=True,
            )
            + "\n"
        )
        handle.flush()
        os.fsync(handle.fileno())
        yield {
            "path": repo_relative(path),
            "pid": os.getpid(),
            "advisory_lock_held_for_child_lifetime": True,
        }
    finally:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        finally:
            handle.close()


def _base_checks(
    config_path: Path,
    host_control_root: Path,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    config = load_json(config_path)
    if (
        config.get("schema")
        != "jointbuildgs.fusion_w1.alignment_gate_config.v1"
    ):
        raise RuntimeGuardError("unexpected Gate A config schema")
    if config_path.resolve() != DEFAULT_CONFIG.resolve():
        raise RuntimeGuardError("alternate Gate A config is forbidden")

    immutable = validate_immutable_preflight(config)
    git_evidence = validate_git_provenance(
        config,
        dispatch_commit=str(immutable["dispatch_commit"]),
        amendment_commit=str(immutable["amendment_commit"]),
    )
    container = validate_container_contract(host_control_root)
    runtime = runtime_versions_and_image()
    mirror = validate_host_control_mirror(
        config_path,
        config,
        immutable,
        git_evidence,
        host_control_root,
    )
    inputs = rehash_gate_inputs(
        config, immutable["baseline_payload"]
    )
    probe = fresh_execution_probe(
        config, immutable["baseline_payload"]
    )
    checks = [
        {
            "name": "immutable_preflight_and_continuation",
            "status": "passed",
            "evidence": {
                key: value
                for key, value in immutable.items()
                if key != "baseline_payload"
            },
        },
        {
            "name": "git_implementation_provenance",
            "status": "passed",
            "evidence": git_evidence,
        },
        {
            "name": "container_runtime_contract",
            "status": "passed",
            "evidence": container,
        },
        {
            "name": "runtime_versions_and_tools_image",
            "status": "passed",
            "evidence": runtime,
        },
        {
            "name": "host_control_mount_freshness",
            "status": "passed",
            "evidence": mirror,
        },
        {
            "name": "gate_input_and_training_image_rehash",
            "status": "passed",
            "evidence": inputs,
        },
        probe,
    ]
    return config, checks


def build_guard_receipt(
    config_path: Path,
    host_control_root: Path,
    *,
    child_argv: Sequence[str],
    lock_evidence: Mapping[str, Any],
) -> dict[str, Any]:
    created = utc_now()
    config, checks = _base_checks(config_path, host_control_root)
    downstream_block = bool(
        find_named_record(checks, "no_active_training_guard")[
            "evidence"
        ]["downstream_gpu_stage_launch_blocked"]
    )
    return {
        "schema": "jointbuildgs.fusion_w1.alignment_runtime_guard.v1",
        "task_id": config.get("task_id"),
        "run_id": config.get("run_id"),
        "created_utc": created,
        "status": (
            "PASSED_WITH_DOWNSTREAM_GPU_BLOCK"
            if downstream_block
            else "PASSED"
        ),
        "cpu_gate_authorized": True,
        "execution_device": "cpu_numpy_only",
        "cuda_used": False,
        "measurement_container_cuda_used": False,
        "downstream_gpu_stage_launch_blocked": downstream_block,
        "config": {
            "path": repo_relative(config_path),
            "sha256": sha256_file(config_path),
        },
        "runtime_guard": {
            "path": repo_relative(Path(__file__)),
            "sha256": sha256_file(Path(__file__)),
        },
        "argv": {
            "runtime_guard": list(sys.argv),
            "gate_child": list(child_argv),
        },
        "single_writer_lock": dict(lock_evidence),
        "checks": checks,
        "human_research_judgment": None,
    }


def _failed_receipt(
    *,
    config_path: Path,
    child_argv: Sequence[str],
    error: BaseException,
) -> dict[str, Any]:
    return {
        "schema": "jointbuildgs.fusion_w1.alignment_runtime_guard.v1",
        "created_utc": utc_now(),
        "status": "BLOCKED",
        "cpu_gate_authorized": False,
        "execution_device": "cpu_numpy_only",
        "cuda_used": False,
        "measurement_container_cuda_used": False,
        "downstream_gpu_stage_launch_blocked": True,
        "config": {
            "path": repo_relative(config_path),
            "sha256": (
                sha256_file(config_path) if config_path.is_file() else None
            ),
        },
        "argv": {
            "runtime_guard": list(sys.argv),
            "gate_child": list(child_argv),
        },
        "error_type": type(error).__name__,
        "error": str(error),
        "human_research_judgment": None,
    }


def revalidate_before_publish(
    config_path: str | Path,
    receipt_path: str | Path,
    *,
    host_control_root: str | Path = DEFAULT_HOST_CONTROL,
) -> dict[str, Any]:
    """Fail closed if provenance/input/runtime drifted before publication.

    The numerical Gate should call this after all outputs exist in staging but
    before any result pointer or fixed output is replaced.
    """

    started = time.monotonic()
    resolved_config = repo_path(config_path)
    resolved_receipt = repo_path(receipt_path)
    initial = load_json(resolved_receipt)
    if initial.get("cpu_gate_authorized") is not True:
        raise RuntimeGuardError("initial runtime guard did not authorize CPU Gate")
    initial_input = find_named_record(
        initial, "gate_input_and_training_image_rehash"
    )
    initial_snapshot = initial_input.get("evidence", {}).get(
        "snapshot_sha256"
    )
    if not isinstance(initial_snapshot, str):
        raise RuntimeGuardError("initial guard lacks input snapshot")

    config = load_json(resolved_config)
    initial_argv = initial.get("argv", {}).get("gate_child")
    if not isinstance(initial_argv, list) or not all(
        isinstance(value, str) for value in initial_argv
    ):
        raise RuntimeGuardError("initial guard lacks exact Gate child argv")
    validate_child_argv(
        initial_argv,
        resolved_config,
        resolved_receipt,
        config=config,
    )
    immutable = validate_immutable_preflight(config)
    git_evidence = validate_git_provenance(
        config,
        dispatch_commit=str(immutable["dispatch_commit"]),
        amendment_commit=str(immutable["amendment_commit"]),
    )
    mirror = validate_host_control_mirror(
        resolved_config,
        config,
        immutable,
        git_evidence,
        Path(host_control_root),
    )
    inputs = rehash_gate_inputs(config, immutable["baseline_payload"])
    if inputs["snapshot_sha256"] != initial_snapshot:
        raise RuntimeGuardError(
            "Gate inputs changed between launch and pre-publication"
        )
    probe = fresh_execution_probe(config, immutable["baseline_payload"])
    return {
        "schema": (
            "jointbuildgs.fusion_w1."
            "alignment_prepublication_revalidation.v1"
        ),
        "created_utc": utc_now(),
        "status": "PASSED",
        "initial_guard_receipt": {
            "path": repo_relative(resolved_receipt),
            "sha256": sha256_file(resolved_receipt),
            "created_utc": initial.get("created_utc"),
        },
        "git": git_evidence,
        "host_control": mirror,
        "input_snapshot_sha256": inputs["snapshot_sha256"],
        "input_snapshot_unchanged": True,
        "fresh_execution_probe": probe,
        "downstream_gpu_stage_launch_blocked": probe["evidence"][
            "downstream_gpu_stage_launch_blocked"
        ],
        "elapsed_seconds": time.monotonic() - started,
        "human_research_judgment": None,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="FUS-W1 Gate A runtime/provenance guard"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    launch = subparsers.add_parser(
        "launch", help="guard and launch the CPU-only Gate A child"
    )
    launch.add_argument("--config", default=str(DEFAULT_CONFIG))
    launch.add_argument(
        "--guard-receipt", default=str(DEFAULT_RECEIPT)
    )
    launch.add_argument("--lock-file", default=str(DEFAULT_LOCK))
    launch.add_argument(
        "--host-control-root", default=str(DEFAULT_HOST_CONTROL)
    )
    launch.add_argument(
        "child_argv", nargs=argparse.REMAINDER, help="-- python Gate ..."
    )

    revalidate = subparsers.add_parser(
        "revalidate",
        help="run the documented pre-publication revalidation hook",
    )
    revalidate.add_argument("--config", default=str(DEFAULT_CONFIG))
    revalidate.add_argument(
        "--guard-receipt", default=str(DEFAULT_RECEIPT)
    )
    revalidate.add_argument(
        "--host-control-root", default=str(DEFAULT_HOST_CONTROL)
    )
    return parser


def launch(args: argparse.Namespace) -> int:
    config_path = repo_path(args.config)
    receipt_path = repo_path(args.guard_receipt)
    lock_path = repo_path(args.lock_file)
    host_control_root = Path(args.host_control_root).resolve()
    child_argv: list[str] = list(args.child_argv)
    try:
        validated_child = validate_child_argv(
            child_argv, config_path, receipt_path
        )
        with single_writer_lock(lock_path) as lock_evidence:
            try:
                receipt = build_guard_receipt(
                    config_path,
                    host_control_root,
                    child_argv=validated_child,
                    lock_evidence=lock_evidence,
                )
                atomic_write_json(receipt_path, receipt)
            except Exception as exc:
                atomic_write_json(
                    receipt_path,
                    _failed_receipt(
                        config_path=config_path,
                        child_argv=validated_child,
                        error=exc,
                    ),
                )
                raise
            completed = subprocess.run(validated_child, check=False)
            return int(completed.returncode)
    except RuntimeGuardError as exc:
        print(f"[BLOCKED] Gate A runtime guard: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:
        print(
            f"[BLOCKED] Gate A runtime guard unhandled "
            f"{type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
        return 2


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "launch":
        return launch(args)
    try:
        result = revalidate_before_publish(
            args.config,
            args.guard_receipt,
            host_control_root=args.host_control_root,
        )
    except RuntimeGuardError as exc:
        print(
            f"[BLOCKED] Gate A pre-publication revalidation: {exc}",
            file=sys.stderr,
        )
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
