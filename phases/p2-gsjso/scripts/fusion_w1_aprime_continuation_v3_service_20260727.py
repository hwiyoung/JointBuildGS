#!/usr/bin/env python3
"""User-systemd control plane for the A-prime continuation v3.

The service executes the continuation-v3 scientific queue in its v3 namespace.
This module owns only fixed-HEAD installation, source-v2 boundary verification,
status/log access, and a source-read-only review index.  An external terminal
boundary watcher owns stopping the foreground v2 process; this module never
signals it.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
from typing import Any, Mapping, Sequence


REPO = Path(__file__).resolve().parents[3]
DEFAULT_CONFIG = (
    REPO
    / "phases/p2-gsjso/configs/fusion_w1_aprime_continuation_v3_service_20260727.json"
)
CONFIG_SCHEMA = "jointbuildgs.fusion_w1_aprime.continuation_v3_service.config.v1"
INSTALL_SCHEMA = "jointbuildgs.fusion_w1_aprime.continuation_v3_service.install.v1"
STOP_AUDIT_SCHEMA = "jointbuildgs.fusion_w1_aprime.continuation_v3_service.stop_audit.v1"
STOP_POST_AUDIT_SCHEMA = (
    "jointbuildgs.fusion_w1_aprime.continuation_v3_service.stop_post_audit.v1"
)
HEAD_RE = re.compile(r"[0-9a-f]{40}")
UNIT_RE = re.compile(r"[A-Za-z0-9_.@-]+[.]service")
PUBLICATION_KEY_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,79}")


class ServiceContractError(RuntimeError):
    """A service, boundary, fixed-HEAD, or review contract was violated."""


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def canonical_json(payload: Any) -> bytes:
    return (
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def pretty_json(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False)


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def require_equal(observed: Any, expected: Any, label: str) -> None:
    if observed != expected:
        raise ServiceContractError(f"{label} mismatch: {observed!r} != {expected!r}")


def require_head(value: str, label: str = "expected HEAD") -> str:
    if not isinstance(value, str) or HEAD_RE.fullmatch(value) is None:
        raise ServiceContractError(f"{label} is not a lowercase 40-hex commit: {value!r}")
    return value


def lexical_path(root: Path, value: str | Path) -> Path:
    raw = Path(value)
    candidate = raw if raw.is_absolute() else root / raw
    candidate = Path(os.path.abspath(os.fspath(candidate)))
    root_absolute = Path(os.path.abspath(os.fspath(root)))
    try:
        candidate.relative_to(root_absolute)
    except ValueError as exc:
        raise ServiceContractError(f"path escapes allowed root: {value}") from exc
    return candidate


def repo_path(value: str | Path) -> Path:
    return lexical_path(REPO, value)


def repo_relative(path: Path) -> str:
    try:
        return path.relative_to(REPO).as_posix()
    except ValueError as exc:
        raise ServiceContractError(f"path outside repository: {path}") from exc


def host_repo_path(config: Mapping[str, Any], value: str | Path) -> Path:
    return lexical_path(Path(config["repository"]), value)


def load_json_regular(path: Path) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise ServiceContractError(f"missing/non-regular JSON: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ServiceContractError(f"cannot read JSON {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ServiceContractError(f"JSON root is not an object: {path}")
    return payload


def load_config(path: Path = DEFAULT_CONFIG) -> dict[str, Any]:
    config_path = path if path.is_absolute() else repo_path(path)
    config = load_json_regular(config_path)
    require_equal(config.get("schema"), CONFIG_SCHEMA, "service config schema")
    require_equal(config.get("branch"), "exp/fusion-w1", "service branch")
    configured_roots = {
        Path(config.get("repository", "")),
        Path(config.get("container_repository", "")),
    }
    if REPO not in configured_roots:
        raise ServiceContractError(
            f"runtime repository is not a declared host/container root: {REPO}"
        )
    service = config.get("service") or {}
    unit_name = service.get("unit_name")
    if not isinstance(unit_name, str) or UNIT_RE.fullmatch(unit_name) is None:
        raise ServiceContractError(f"invalid user unit name: {unit_name!r}")
    for key, expected in (
        ("working_directory", config["repository"]),
        ("type", "exec"),
        ("kill_mode", "control-group"),
        ("kill_signal", "SIGTERM"),
        ("send_sigkill", True),
        ("timeout_stop_sec", 300),
        ("final_kill_signal", "SIGKILL"),
        ("refuse_manual_stop", False),
        ("restart", "on-failure"),
        ("restart_sec", 30),
        ("restart_prevent_exit_status", [2, 78]),
        ("start_limit_interval_sec", 0),
        ("standard_input", "null"),
        ("standard_output", "append"),
        ("standard_error", "append"),
        ("enable_on_install", False),
        ("terminal_close_capability_declared", True),
        ("terminal_close_safe_now_requires_runtime_evidence", True),
        ("logout_persistence_requires_linger", True),
        ("auto_enable_linger", False),
    ):
        require_equal(service.get(key), expected, f"service {key}")
    stop = config.get("stop_control") or {}
    for key, expected in (
        ("manual_stop_allowed", True),
        ("audit_before_signal", True),
        ("audit_after_stop", True),
        ("graceful_signal", "SIGTERM"),
        ("graceful_timeout_seconds", 300),
        ("emergency_signal_after_timeout", "SIGKILL"),
        ("control_group_scope", True),
        ("partial_artifacts_preserved", True),
        ("partial_artifacts_deleted", False),
        ("deterministic_resume_after_stop", True),
        ("audit_overwrite_allowed", False),
    ):
        require_equal(stop.get(key), expected, f"stop control {key}")
    boundary = config.get("boundary_gate") or {}
    for key, expected in (
        ("handoff_owner", "external_terminal_boundary_watcher"),
        ("service_sends_signals_to_v2", False),
        ("reused_v2_stage_record_must_be_measured", True),
        ("reused_receipt_hash_verification_delegated_to_v3", True),
        ("old_wrapper_process_must_be_absent", True),
        ("v2_driver_lock_must_be_nonblocking", True),
        ("active_aprime_container_must_be_absent", True),
        ("v3_verify_required_before_service_start", True),
        ("source_boundary_receipt_written_by_v3_initialize", True),
        ("time_cutoff", None),
    ):
        require_equal(boundary.get(key), expected, f"boundary gate {key}")
    review = config.get("review_index") or {}
    for key, expected in (
        ("mode", "READ_ONLY_SOURCE_INDEX"),
        ("exclusive_publication", True),
        ("overwrite_allowed", False),
        ("source_mutation_allowed", False),
        ("recursive_scientific_payload_hashing", False),
        ("observational_only", True),
        ("interpretation_or_verdict", None),
    ):
        require_equal(review.get(key), expected, f"review index {key}")
    implementation = config.get("implementation_files")
    if not isinstance(implementation, list) or len(implementation) != 4:
        raise ServiceContractError("service implementation_files must contain exactly four paths")
    queue_files = [config["queue"][name] for name in ("config", "driver", "wrapper", "test")]
    qualitative_files = [
        config["qualitative"][name] for name in ("config", "driver", "wrapper", "test")
    ]
    if len(set(implementation + queue_files + qualitative_files)) != 12:
        raise ServiceContractError("fixed-HEAD primary implementation scope contains duplicates")
    return config


def run_command(
    arguments: Sequence[str], *, check: bool = True, cwd: Path = REPO
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        list(arguments),
        cwd=cwd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if check and result.returncode != 0:
        message = result.stderr.strip() or result.stdout.strip() or f"exit {result.returncode}"
        raise ServiceContractError(f"command failed ({' '.join(arguments)}): {message}")
    return result


def git(*arguments: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return run_command(("git", *arguments), check=check)


def regular_file_record(path: Path, *, logical: str | None = None) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise ServiceContractError(f"missing/non-regular file: {path}")
    metadata = path.stat()
    if metadata.st_size <= 0:
        raise ServiceContractError(f"empty file is forbidden: {path}")
    return {
        "path": logical if logical is not None else os.fspath(path),
        "sha256": sha256_file(path),
        "bytes": metadata.st_size,
    }


def verify_record(record: Mapping[str, Any], path: Path, label: str) -> dict[str, Any]:
    observed = regular_file_record(path, logical=str(record.get("path", path)))
    require_equal(observed["sha256"], record.get("sha256"), f"{label} SHA")
    require_equal(observed["bytes"], record.get("bytes"), f"{label} bytes")
    return observed


def fixed_head_scope(config: Mapping[str, Any]) -> dict[str, Any]:
    service_files = list(config["implementation_files"])
    queue_files = [config["queue"][name] for name in ("config", "driver", "wrapper", "test")]
    qualitative_files = [
        config["qualitative"][name] for name in ("config", "driver", "wrapper", "test")
    ]
    queue_config = load_json_regular(repo_path(config["queue"]["config"]))
    require_equal(
        queue_config.get("implementation_files"),
        queue_files,
        "queue-v3 implementation scope",
    )
    qualitative_config = load_json_regular(repo_path(config["qualitative"]["config"]))
    require_equal(
        qualitative_config.get("implementation_files"),
        qualitative_files,
        "qualitative-v3 implementation scope",
    )
    locked = queue_config.get("locked_inputs")
    if not isinstance(locked, Mapping):
        raise ServiceContractError("queue-v3 locked_inputs is absent")
    required_names = config["fixed_head_contract"]["required_queue_locked_input_names"]
    if not isinstance(required_names, list) or len(required_names) != len(set(required_names)):
        raise ServiceContractError("required queue locked-input names are invalid")
    missing = sorted(set(required_names) - set(locked))
    if missing:
        raise ServiceContractError(f"queue-v3 required locked inputs are missing: {missing}")
    locked_paths: list[str] = []
    locked_records: dict[str, dict[str, Any]] = {}
    for name, record in locked.items():
        if not isinstance(name, str) or not isinstance(record, Mapping):
            raise ServiceContractError("queue-v3 locked-input record is invalid")
        logical, expected_sha = record.get("path"), record.get("sha256")
        if not isinstance(logical, str) or not isinstance(expected_sha, str):
            raise ServiceContractError(f"queue-v3 locked input {name} lacks path/SHA")
        observed = regular_file_record(repo_path(logical), logical=logical)
        require_equal(observed["sha256"], expected_sha, f"queue-v3 locked input {name}")
        locked_paths.append(logical)
        locked_records[name] = observed
    expanded = service_files + queue_files + qualitative_files + locked_paths
    paths = list(dict.fromkeys(expanded))
    overlaps = sorted(path for path in set(expanded) if expanded.count(path) > 1)
    return {
        "paths": paths,
        "groups": {
            "service_implementation": service_files,
            "queue_v3_implementation": queue_files,
            "qualitative_v3_implementation": qualitative_files,
            "queue_v3_locked_dependencies": locked_paths,
        },
        "queue_locked_inputs": locked_records,
        "cross_group_overlaps_verified_once": overlaps,
    }


def verify_fixed_head(config: Mapping[str, Any], expected_head: str) -> dict[str, Any]:
    expected_head = require_head(expected_head)
    branch = git("branch", "--show-current").stdout.strip()
    head = git("rev-parse", "HEAD").stdout.strip()
    require_equal(branch, config["branch"], "fixed-HEAD branch")
    require_equal(head, expected_head, "fixed-HEAD commit")
    scope = fixed_head_scope(config)
    scoped = scope["paths"]
    records: list[dict[str, Any]] = []
    for logical in scoped:
        if not isinstance(logical, str):
            raise ServiceContractError("fixed-HEAD path is not a string")
        path = repo_path(logical)
        tracked = git("ls-files", "--error-unmatch", "--", logical, check=False)
        if tracked.returncode != 0:
            raise ServiceContractError(f"fixed-HEAD file is untracked: {logical}")
        head_blob = git("rev-parse", f"{expected_head}:{logical}", check=False)
        if head_blob.returncode != 0:
            raise ServiceContractError(f"fixed-HEAD file absent at commit: {logical}")
        worktree_blob = git("hash-object", "--", logical).stdout.strip()
        require_equal(worktree_blob, head_blob.stdout.strip(), f"fixed-HEAD worktree {logical}")
        records.append(
            {
                **regular_file_record(path, logical=logical),
                "git_blob": worktree_blob,
                "tracked_at_head": True,
                "worktree_matches_head": True,
            }
        )
    return {
        "branch": branch,
        "head": head,
        "files": records,
        "groups": scope["groups"],
        "queue_locked_inputs": scope["queue_locked_inputs"],
        "all_tracked_at_head": True,
        "all_worktree_match_head": True,
    }


def safe_systemd_value(value: str, label: str) -> str:
    if not value or any(character in value for character in "\r\n\0"):
        raise ServiceContractError(f"unsafe systemd {label}: {value!r}")
    return value.replace("%", "%%")


def systemd_exec_argument(value: str) -> str:
    value = safe_systemd_value(value, "exec argument")
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def render_unit(config: Mapping[str, Any], expected_head: str) -> bytes:
    expected_head = require_head(expected_head)
    service = config["service"]
    controller = host_repo_path(config, config["implementation_files"][1])
    config_path = host_repo_path(config, config["implementation_files"][0])
    queue_wrapper = host_repo_path(config, config["queue"]["wrapper"])
    log_path = host_repo_path(config, service["log"])
    preflight = " ".join(
        systemd_exec_argument(item)
        for item in (
            "/usr/bin/python3",
            os.fspath(controller),
            "--config",
            os.fspath(config_path),
            "exec-preflight",
            "--expected-head",
            expected_head,
        )
    )
    execute = " ".join(
        systemd_exec_argument(item)
        for item in ("/usr/bin/bash", os.fspath(queue_wrapper), "run")
    )
    stop_audit = " ".join(
        systemd_exec_argument(item)
        for item in (
            "/usr/bin/python3",
            os.fspath(controller),
            "--config",
            os.fspath(config_path),
            "record-stop-audit",
            "--expected-head",
            expected_head,
        )
    )
    stop_post_audit = " ".join(
        systemd_exec_argument(item)
        for item in (
            "/usr/bin/python3",
            os.fspath(controller),
            "--config",
            os.fspath(config_path),
            "record-stop-post-audit",
            "--expected-head",
            expected_head,
            "--service-result",
            "${SERVICE_RESULT}",
            "--exit-code",
            "${EXIT_CODE}",
            "--exit-status",
            "${EXIT_STATUS}",
        )
    )
    lines = [
        "[Unit]",
        f"Description={safe_systemd_value(service['description'], 'description')}",
        "StartLimitIntervalSec=0",
        "RefuseManualStop=no",
        "",
        "[Service]",
        "Type=exec",
        f"WorkingDirectory={safe_systemd_value(service['working_directory'], 'working directory')}",
        "Environment=PYTHONDONTWRITEBYTECODE=1",
        "Environment=PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
        f"ExecStartPre={preflight}",
        f"ExecStart={execute}",
        f"ExecStop={stop_audit}",
        f"ExecStopPost={stop_post_audit}",
        "Restart=on-failure",
        f"RestartSec={service['restart_sec']}s",
        "RestartPreventExitStatus=" + " ".join(map(str, service["restart_prevent_exit_status"])),
        "KillMode=control-group",
        "KillSignal=SIGTERM",
        "SendSIGKILL=yes",
        f"TimeoutStopSec={service['timeout_stop_sec']}s",
        "FinalKillSignal=SIGKILL",
        "TimeoutStopFailureMode=terminate",
        "StandardInput=null",
        f"StandardOutput=append:{safe_systemd_value(os.fspath(log_path), 'log path')}",
        f"StandardError=append:{safe_systemd_value(os.fspath(log_path), 'log path')}",
        "UMask=0022",
        "",
        "[Install]",
        "WantedBy=default.target",
        "",
    ]
    return "\n".join(lines).encode("utf-8")


def user_unit_path(config: Mapping[str, Any], environment: Mapping[str, str] = os.environ) -> Path:
    if environment.get("XDG_CONFIG_HOME"):
        base = Path(environment["XDG_CONFIG_HOME"])
    else:
        base = Path(environment.get("HOME", os.fspath(Path.home()))) / ".config"
    if not base.is_absolute():
        raise ServiceContractError("user config home must be absolute")
    return base / "systemd/user" / config["service"]["unit_name"]


def ensure_directory(path: Path) -> None:
    missing: list[Path] = []
    cursor = path
    while not cursor.exists() and not cursor.is_symlink():
        missing.append(cursor)
        if cursor.parent == cursor:
            break
        cursor = cursor.parent
    if cursor.is_symlink() or (cursor.exists() and not cursor.is_dir()):
        raise ServiceContractError(f"directory ancestor is not a real directory: {cursor}")
    for directory in reversed(missing):
        directory.mkdir(mode=0o755)
    cursor = path
    while True:
        if cursor.is_symlink() or not cursor.is_dir():
            raise ServiceContractError(f"directory path contains invalid component: {cursor}")
        if cursor.parent == cursor:
            break
        cursor = cursor.parent


def exclusive_or_identical(path: Path, payload: bytes) -> str:
    ensure_directory(path.parent)
    if path.exists() or path.is_symlink():
        if path.is_symlink() or not path.is_file():
            raise ServiceContractError(f"existing destination is non-regular: {path}")
        if path.read_bytes() != payload:
            raise ServiceContractError(f"refusing to overwrite different existing file: {path}")
        return "REUSED_IDENTICAL"
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o644)
    try:
        with os.fdopen(descriptor, "wb", closefd=False) as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    finally:
        os.close(descriptor)
    return "CREATED"


def install_receipt_path(config: Mapping[str, Any]) -> Path:
    return repo_path(config["service"]["install_receipt"])


def install_service(
    config: Mapping[str, Any], expected_head: str, *, dry_run: bool = False
) -> dict[str, Any]:
    expected_head = require_head(expected_head)
    fixed = verify_fixed_head(config, expected_head)
    unit_payload = render_unit(config, expected_head)
    unit_path = user_unit_path(config)
    snapshot_path = repo_path(config["service"]["unit_snapshot"])
    planned = {
        "schema": INSTALL_SCHEMA,
        "state": "DRY_RUN" if dry_run else "INSTALLED",
        "unit_name": config["service"]["unit_name"],
        "expected_head": expected_head,
        "fixed_head": fixed,
        "unit_path": os.fspath(unit_path),
        "unit_snapshot_path": repo_relative(snapshot_path),
        "unit_sha256": sha256_bytes(unit_payload),
        "unit_bytes": len(unit_payload),
        "working_directory": config["service"]["working_directory"],
        "log_path": config["service"]["log"],
        "stop_control": dict(config["stop_control"]),
        "terminal_close_contract": {
            "capability_declared": True,
            "safe_now_requires_runtime_evidence": True,
            "logout_persistence_requires_linger": True,
        },
        "enabled": False,
        "started": False,
        "dry_run": dry_run,
        "interpretation_or_verdict": None,
    }
    if dry_run:
        return {**planned, "unit": unit_payload.decode("utf-8")}
    ensure_directory(repo_path(config["service"]["control_root"]))
    snapshot_state = exclusive_or_identical(snapshot_path, unit_payload)
    unit_state = exclusive_or_identical(unit_path, unit_payload)
    receipt_path = install_receipt_path(config)
    receipt_core = {
        **planned,
        "dry_run": False,
        "unit": regular_file_record(unit_path),
        "unit_snapshot": regular_file_record(
            snapshot_path, logical=repo_relative(snapshot_path)
        ),
        "unit_install_state": unit_state,
        "snapshot_install_state": snapshot_state,
    }
    if receipt_path.exists() or receipt_path.is_symlink():
        observed = load_json_regular(receipt_path)
        for key in (
            "schema",
            "state",
            "unit_name",
            "expected_head",
            "fixed_head",
            "unit_path",
            "unit_snapshot_path",
            "unit_sha256",
            "unit_bytes",
            "working_directory",
            "log_path",
            "stop_control",
            "terminal_close_contract",
            "enabled",
            "started",
            "dry_run",
            "interpretation_or_verdict",
            "unit",
            "unit_snapshot",
        ):
            require_equal(observed.get(key), receipt_core.get(key), f"install receipt {key}")
        receipt = {**observed, "publication_reused": True}
    else:
        receipt = {**receipt_core, "created_at": now_iso()}
        exclusive_or_identical(receipt_path, canonical_json(receipt))
    run_command(("systemctl", "--user", "daemon-reload"))
    return receipt


def verify_installation(config: Mapping[str, Any], expected_head: str) -> dict[str, Any]:
    expected_head = require_head(expected_head)
    receipt = load_json_regular(install_receipt_path(config))
    require_equal(receipt.get("schema"), INSTALL_SCHEMA, "install receipt schema")
    require_equal(receipt.get("state"), "INSTALLED", "install receipt state")
    require_equal(receipt.get("expected_head"), expected_head, "installed expected HEAD")
    unit_path = user_unit_path(config)
    require_equal(receipt.get("unit_path"), os.fspath(unit_path), "installed unit path")
    unit_payload = render_unit(config, expected_head)
    require_equal(sha256_bytes(unit_payload), receipt.get("unit_sha256"), "rendered unit SHA")
    verify_record(receipt["unit"], unit_path, "installed user unit")
    snapshot_path = repo_path(config["service"]["unit_snapshot"])
    verify_record(receipt["unit_snapshot"], snapshot_path, "installed unit snapshot")
    require_equal(unit_path.read_bytes(), unit_payload, "installed unit bytes")
    require_equal(snapshot_path.read_bytes(), unit_payload, "unit snapshot bytes")
    return receipt


def exec_preflight(config: Mapping[str, Any], expected_head: str) -> dict[str, Any]:
    return {
        "state": "PASSED",
        "fixed_head": verify_fixed_head(config, expected_head),
        "installation": verify_installation(config, expected_head),
        "source_boundary": verify_source_boundary(config, run_v3_verify=True),
        "queue_wrapper": config["queue"]["wrapper"],
        "scientific_execution": "docker_via_continuation_v3_wrapper",
        "interpretation_or_verdict": None,
    }


def lock_path_is_free(path: Path, *, missing_allowed: bool) -> bool:
    if not path.exists() and not path.is_symlink():
        if missing_allowed:
            return True
        raise ServiceContractError(f"required driver lock is missing: {path}")
    if path.is_symlink() or not path.is_file():
        raise ServiceContractError(f"driver lock is non-regular: {path}")
    descriptor = os.open(path, os.O_RDWR | os.O_NOFOLLOW)
    try:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return False
        fcntl.flock(descriptor, fcntl.LOCK_UN)
        return True
    finally:
        os.close(descriptor)


def verify_reused_stage_record(config: Mapping[str, Any]) -> dict[str, Any]:
    source = config["source_v2"]
    path = repo_path(source["reused_stage_record"])
    payload = load_json_regular(path)
    require_equal(payload.get("status"), source["required_status"], "reused v2 stage status")
    entry = payload.get("entry")
    if not isinstance(entry, Mapping):
        raise ServiceContractError("reused v2 stage record entry is absent")
    for key, expected in source["required_identity"].items():
        require_equal(entry.get(key), expected, f"reused v2 stage identity {key}")
    return {
        "record": regular_file_record(path, logical=source["reused_stage_record"]),
        "status": payload["status"],
        "identity": dict(source["required_identity"]),
        "referenced_receipt_hash_verification_owner": source[
            "referenced_receipt_hash_verification_owner"
        ],
    }


def active_source_v2_wrapper_processes(config: Mapping[str, Any]) -> list[dict[str, Any]]:
    expected = Path(os.path.realpath(repo_path(config["source_v2"]["wrapper"])))
    matches: list[dict[str, Any]] = []
    for proc_root in Path("/proc").iterdir():
        if not proc_root.name.isdigit():
            continue
        pid = int(proc_root.name)
        try:
            if proc_root.stat().st_uid != os.getuid():
                continue
            command = proc_cmdline(pid)
            cwd = Path(os.readlink(proc_root / "cwd"))
        except (ServiceContractError, FileNotFoundError, PermissionError, OSError):
            continue
        if len(command) < 3 or command[-1] != "run":
            continue
        candidate = Path(command[-2])
        candidate = candidate if candidate.is_absolute() else cwd / candidate
        if Path(os.path.realpath(candidate)) == expected:
            matches.append({"pid": pid, "cmdline": command, "cwd": os.fspath(cwd)})
    return sorted(matches, key=lambda item: item["pid"])


def active_blocking_aprime_containers(config: Mapping[str, Any]) -> list[dict[str, Any]]:
    source = config["source_v2"]
    require_equal(
        source.get("blocking_scope_includes_source_v2_and_orphaned_v3"),
        True,
        "blocking container scope",
    )
    require_equal(
        source.get("container_name_regex_is_auxiliary_only"),
        True,
        "container name regex role",
    )
    detection = source.get("container_primary_detection") or {}
    require_equal(detection.get("requires_repository_bind_mount"), True, "container repo bind")
    require_equal(
        detection.get("inspect_fields"),
        ["Config.Cmd", "Config.Env", "Args"],
        "container inspect fields",
    )
    markers = detection.get("scientific_markers")
    if not isinstance(markers, list) or not markers or not all(isinstance(item, str) for item in markers):
        raise ServiceContractError("container scientific markers are invalid")
    pattern = re.compile(source["blocking_active_container_name_regex"])
    running = run_command(
        ("docker", "ps", "--filter", "status=running", "--quiet"),
        check=False,
    )
    if running.returncode != 0:
        message = running.stderr.strip() or running.stdout.strip() or f"exit {running.returncode}"
        raise ServiceContractError(f"cannot inspect active Docker containers: {message}")
    identifiers = [value.strip() for value in running.stdout.splitlines() if value.strip()]
    if not identifiers:
        return []
    if any(re.fullmatch(r"[0-9a-f]{12,64}", value) is None for value in identifiers):
        raise ServiceContractError(f"docker ps returned malformed container IDs: {identifiers}")
    inspected = run_command(("docker", "inspect", *identifiers), check=False)
    if inspected.returncode != 0:
        message = inspected.stderr.strip() or inspected.stdout.strip() or f"exit {inspected.returncode}"
        raise ServiceContractError(f"docker inspect failed for active containers: {message}")
    try:
        payload = json.loads(inspected.stdout)
    except json.JSONDecodeError as exc:
        raise ServiceContractError(f"docker inspect returned invalid JSON: {exc}") from exc
    if not isinstance(payload, list) or len(payload) != len(identifiers):
        raise ServiceContractError("docker inspect active-container cardinality mismatch")
    observed_ids = [str(item.get("Id", "")) for item in payload if isinstance(item, Mapping)]
    if (
        len(observed_ids) != len(payload)
        or len(observed_ids) != len(set(observed_ids))
        or any(re.fullmatch(r"[0-9a-f]{64}", value) is None for value in observed_ids)
        or any(sum(value.startswith(requested) for value in observed_ids) != 1 for requested in identifiers)
    ):
        raise ServiceContractError("docker inspect records do not bind exactly to docker ps IDs")
    host_repo = Path(os.path.realpath(config["repository"]))
    blocked: list[dict[str, Any]] = []
    for record in payload:
        if not isinstance(record, Mapping):
            raise ServiceContractError("docker inspect container record is invalid")
        identifier = str(record.get("Id", ""))
        name = str(record.get("Name", "")).lstrip("/")
        mounts = record.get("Mounts")
        if not isinstance(mounts, list):
            raise ServiceContractError(f"docker inspect Mounts is invalid for {identifier}")
        repo_mounts: list[dict[str, str]] = []
        for mount in mounts:
            if not isinstance(mount, Mapping) or mount.get("Type") != "bind":
                continue
            raw_source, destination = mount.get("Source"), mount.get("Destination")
            if not isinstance(raw_source, str) or not isinstance(destination, str):
                continue
            mount_source = Path(os.path.realpath(raw_source))
            try:
                mount_source.relative_to(host_repo)
            except ValueError:
                continue
            repo_mounts.append(
                {"source": os.fspath(mount_source), "destination": destination}
            )
        container_config = record.get("Config")
        if not isinstance(container_config, Mapping):
            container_config = {}
        inspected_fields = {
            "Config.Cmd": container_config.get("Cmd"),
            "Config.Env": container_config.get("Env"),
            "Args": record.get("Args"),
        }
        searchable = json.dumps(inspected_fields, ensure_ascii=False, sort_keys=True).lower()
        matched_markers = sorted(marker for marker in markers if marker.lower() in searchable)
        primary_match = bool(repo_mounts and matched_markers)
        auxiliary_name_match = pattern.fullmatch(name) is not None
        if primary_match or auxiliary_name_match:
            blocked.append(
                {
                    "id": identifier,
                    "name": name,
                    "primary_repo_and_command_match": primary_match,
                    "repo_bind_mounts": repo_mounts,
                    "matched_scientific_markers": matched_markers,
                    "auxiliary_name_regex_match": auxiliary_name_match,
                    "name_regex_is_auxiliary_only": True,
                }
            )
    return sorted(blocked, key=lambda item: (item["name"], item["id"]))


def verify_source_boundary(
    config: Mapping[str, Any], *, run_v3_verify: bool
) -> dict[str, Any]:
    stage = verify_reused_stage_record(config)
    active_wrappers = active_source_v2_wrapper_processes(config)
    if active_wrappers:
        raise ServiceContractError(f"source-v2 wrapper is still active: {active_wrappers}")
    v2_lock = repo_path(config["source_v2"]["driver_lock"])
    if not lock_path_is_free(v2_lock, missing_allowed=False):
        raise ServiceContractError("source-v2 driver lock is still held")
    active_containers = active_blocking_aprime_containers(config)
    if active_containers:
        raise ServiceContractError(
            "source-v2 or orphaned-v3 jointbuildgs-aprime containers are still active: "
            f"{active_containers}"
        )
    v3_lock = repo_path(config["queue"]["driver_lock"])
    if not lock_path_is_free(v3_lock, missing_allowed=True):
        raise ServiceContractError("continuation-v3 driver lock is already held")
    verification: dict[str, Any] | None = None
    if run_v3_verify:
        wrapper = repo_path(config["queue"]["wrapper"])
        result = run_command(("/usr/bin/bash", os.fspath(wrapper), "verify"))
        verification = {
            "command": ["/usr/bin/bash", config["queue"]["wrapper"], "verify"],
            "return_code": result.returncode,
            "stdout_sha256": sha256_bytes(result.stdout.encode("utf-8")),
            "stderr_sha256": sha256_bytes(result.stderr.encode("utf-8")),
            "delegated_receipt_hash_verification": True,
        }
    return {
        "state": "PASSED",
        "reused_stage": stage,
        "active_source_v2_wrappers": [],
        "source_v2_driver_lock_free": True,
        "active_blocking_aprime_containers": [],
        "continuation_v3_driver_lock_free": True,
        "v3_verify": verification,
        "service_sent_signals_to_v2": False,
        "source_boundary_receipt_owner": "queue_v3_initialize",
        "interpretation_or_verdict": None,
    }


def installed_expected_head(config: Mapping[str, Any]) -> str:
    receipt = load_json_regular(install_receipt_path(config))
    return require_head(str(receipt.get("expected_head")), "installed expected HEAD")


def start_service(config: Mapping[str, Any], *, dry_run: bool = False) -> dict[str, Any]:
    expected_head = installed_expected_head(config)
    preflight = exec_preflight(config, expected_head)
    command = ("systemctl", "--user", "start", "--no-block", config["service"]["unit_name"])
    if not dry_run:
        run_command(command)
    return {
        "state": "DRY_RUN" if dry_run else "START_REQUESTED",
        "unit_name": config["service"]["unit_name"],
        "expected_head": expected_head,
        "preflight": preflight,
        "source_v2_driver_lock_free": True,
        "continuation_v3_driver_lock_free": True,
        "command": list(command),
        "terminal_close_capability_declared": True,
        "terminal_close_safe_now": False if dry_run else None,
        "terminal_close_safe_now_requires_status_measurement": True,
        "logout_persistence_requires_linger": True,
        "dry_run": dry_run,
        "interpretation_or_verdict": None,
    }


def stop_service(config: Mapping[str, Any], *, dry_run: bool = False) -> dict[str, Any]:
    command = ("systemctl", "--user", "stop", "--no-block", config["service"]["unit_name"])
    if not dry_run:
        run_command(command)
    return {
        "state": "DRY_RUN" if dry_run else "STOP_REQUESTED",
        "unit_name": config["service"]["unit_name"],
        "command": list(command),
        "exec_stop_pre_signal_audit_required": True,
        "exec_stop_post_outcome_audit_required": True,
        "graceful_signal": config["stop_control"]["graceful_signal"],
        "graceful_timeout_seconds": config["stop_control"]["graceful_timeout_seconds"],
        "emergency_signal_after_timeout": config["stop_control"][
            "emergency_signal_after_timeout"
        ],
        "partial_artifacts_preserved": True,
        "dry_run": dry_run,
        "interpretation_or_verdict": None,
    }


def linger_state() -> str:
    result = run_command(
        ("loginctl", "show-user", str(os.getuid()), "--property=Linger", "--value"),
        check=False,
    )
    if result.returncode != 0:
        return "UNKNOWN"
    value = result.stdout.strip().lower()
    return "ENABLED" if value == "yes" else "DISABLED" if value == "no" else "UNKNOWN"


def terminal_close_runtime_evidence(
    config: Mapping[str, Any],
    properties: Mapping[str, str],
    *,
    proc_root: Path = Path("/proc"),
) -> dict[str, Any]:
    service = config["service"]
    expected_log = f"append:{repo_path(service['log'])}"
    load_ok = properties.get("LoadState") == "loaded"
    active_ok = properties.get("ActiveState") == "active"
    running_ok = properties.get("SubState") == "running"
    raw_pid = properties.get("MainPID", "")
    try:
        main_pid = int(raw_pid)
    except (TypeError, ValueError):
        main_pid = 0
    pid_positive = main_pid > 0
    control_group = properties.get("ControlGroup", "")
    systemd_cgroup_declared = (
        control_group.startswith("/")
        and control_group != "/"
        and service["unit_name"] in control_group
    )
    proc_exists = False
    pid_owned_by_user = False
    stdin_dev_null = False
    pid_in_control_group = False
    observed_stdin: str | None = None
    observed_cgroups: list[str] = []
    if pid_positive:
        proc_dir = proc_root / str(main_pid)
        try:
            proc_metadata = proc_dir.stat()
            proc_exists = proc_dir.is_dir()
            pid_owned_by_user = proc_metadata.st_uid == os.getuid()
        except (FileNotFoundError, PermissionError, OSError):
            proc_exists = False
        if proc_exists:
            try:
                observed_stdin = os.readlink(proc_dir / "fd/0")
                stdin_dev_null = os.path.realpath(observed_stdin) == "/dev/null"
            except (FileNotFoundError, PermissionError, OSError):
                stdin_dev_null = False
            try:
                for line in (proc_dir / "cgroup").read_text(encoding="utf-8").splitlines():
                    _hierarchy, _controllers, member_path = line.split(":", 2)
                    observed_cgroups.append(member_path)
            except (FileNotFoundError, PermissionError, OSError, ValueError):
                observed_cgroups = []
            pid_in_control_group = control_group in observed_cgroups
    checks = {
        "load_state_loaded": load_ok,
        "active_state_active": active_ok,
        "sub_state_running": running_ok,
        "main_pid_positive": pid_positive,
        "main_pid_proc_exists": proc_exists,
        "main_pid_owned_by_user": pid_owned_by_user,
        "systemd_control_group_declared": systemd_cgroup_declared,
        "main_pid_in_systemd_control_group": pid_in_control_group,
        "main_pid_stdin_is_dev_null": stdin_dev_null,
        "unit_standard_input_is_null": properties.get("StandardInput") == "null",
        "unit_stdout_is_append_log": properties.get("StandardOutput") == expected_log,
        "unit_stderr_is_append_log": properties.get("StandardError") == expected_log,
    }
    return {
        "checks": checks,
        "main_pid": main_pid,
        "control_group": control_group or None,
        "observed_proc_cgroups": observed_cgroups,
        "observed_stdin_fd0": observed_stdin,
        "observed_unit_stdio": {
            "StandardInput": properties.get("StandardInput"),
            "StandardOutput": properties.get("StandardOutput"),
            "StandardError": properties.get("StandardError"),
        },
        "expected_append_log": expected_log,
        "terminal_close_safe_now": all(checks.values()),
    }


def service_status(config: Mapping[str, Any]) -> dict[str, Any]:
    properties = (
        "LoadState",
        "ActiveState",
        "SubState",
        "Result",
        "MainPID",
        "ExecMainStartTimestamp",
        "ExecMainStatus",
        "NRestarts",
        "FragmentPath",
        "ControlGroup",
        "StandardInput",
        "StandardOutput",
        "StandardError",
    )
    command = [
        "systemctl",
        "--user",
        "show",
        config["service"]["unit_name"],
        "--no-pager",
    ]
    for property_name in properties:
        command.extend(("--property", property_name))
    result = run_command(command, check=False)
    observed: dict[str, str] = {}
    for line in result.stdout.splitlines():
        key, separator, value = line.partition("=")
        if separator:
            observed[key] = value
    linger = linger_state()
    runtime = terminal_close_runtime_evidence(config, observed)
    return {
        "schema": "jointbuildgs.fusion_w1_aprime.continuation_v3_service.status.v1",
        "unit_name": config["service"]["unit_name"],
        "systemctl_return_code": result.returncode,
        "properties": observed,
        "stderr": result.stderr.strip() or None,
        "log_path": config["service"]["log"],
        "queue_root": config["queue"]["root"],
        "user_linger": linger,
        "terminal_close_capability": {
            "declared": config["service"]["terminal_close_capability_declared"],
            "user_systemd_controlled": True,
            "stdin_configured_null": config["service"]["standard_input"] == "null",
            "stdout_stderr_configured_append_log": (
                config["service"]["standard_output"] == "append"
                and config["service"]["standard_error"] == "append"
            ),
            "survives_terminal_close_when_runtime_evidence_passes": True,
            "logout_persistence_requires_linger": True,
            "logout_persistence_capable_now": linger == "ENABLED",
        },
        "terminal_close_runtime_evidence": runtime,
        "terminal_close_safe_now": runtime["terminal_close_safe_now"],
        "logout_persistence_requires_linger": True,
        "interpretation_or_verdict": None,
    }


def tail_lines(path: Path, count: int) -> str:
    if count < 1 or count > 10000:
        raise ServiceContractError("log line count must be between 1 and 10000")
    if path.is_symlink() or not path.is_file():
        raise ServiceContractError(f"service log is missing/non-regular: {path}")
    with path.open("rb") as stream:
        stream.seek(0, os.SEEK_END)
        position = stream.tell()
        buffer = b""
        while position > 0 and buffer.count(b"\n") <= count:
            step = min(65536, position)
            position -= step
            stream.seek(position)
            buffer = stream.read(step) + buffer
    return b"\n".join(buffer.splitlines()[-count:]).decode("utf-8", errors="replace")


def record_stop_audit(config: Mapping[str, Any], expected_head: str) -> dict[str, Any]:
    expected_head = require_head(expected_head)
    stop = config["stop_control"]
    try:
        fixed: dict[str, Any] = {
            "state": "PASSED",
            "verification": verify_fixed_head(config, expected_head),
        }
    except ServiceContractError as exc:
        # A stop must remain available even after worktree drift.  Record the
        # gate failure before systemd sends SIGTERM instead of suppressing the
        # only stop audit.
        fixed = {"state": "FAILED_RECORDED", "error": str(exc)}
    timestamp = datetime.now(timezone.utc)
    key = timestamp.strftime("%Y%m%dT%H%M%S.%fZ") + f"_{os.getpid()}"
    root = repo_path(stop["audit_root"])
    path = root / f"{key}.json"
    source_records = [
        stable_source_record(repo_path(logical), logical)
        for logical in config["review_index"]["control_files"]
    ]
    payload = {
        "schema": STOP_AUDIT_SCHEMA,
        "state": "STOP_REQUEST_RECORDED_BEFORE_SIGNAL",
        "created_at": timestamp.isoformat(),
        "unit_name": config["service"]["unit_name"],
        "expected_head": expected_head,
        "fixed_head": fixed,
        "pre_signal_service_status": service_status(config),
        "pre_signal_source_records": source_records,
        "stop_contract": {
            "manual_stop_allowed": True,
            "kill_mode": "control-group",
            "graceful_signal": stop["graceful_signal"],
            "graceful_timeout_seconds": stop["graceful_timeout_seconds"],
            "emergency_signal_after_timeout": stop["emergency_signal_after_timeout"],
            "partial_artifacts_preserved": True,
            "partial_artifacts_deleted": False,
            "deterministic_resume_after_stop": True,
        },
        "overwrite_allowed": False,
        "interpretation_or_verdict": None,
    }
    outcome = exclusive_or_identical(path, canonical_json(payload))
    if outcome != "CREATED":
        raise ServiceContractError(f"stop audit path unexpectedly existed: {path}")
    return {
        "state": "RECORDED",
        "audit": regular_file_record(path, logical=repo_relative(path)),
        "partial_artifacts_preserved": True,
        "interpretation_or_verdict": None,
    }


def record_stop_post_audit(
    config: Mapping[str, Any],
    expected_head: str,
    service_result: str,
    exit_code: str,
    exit_status: str,
) -> dict[str, Any]:
    expected_head = require_head(expected_head)
    for label, value in (
        ("service result", service_result),
        ("exit code", exit_code),
        ("exit status", exit_status),
    ):
        if not isinstance(value, str) or any(character in value for character in "\r\n\0"):
            raise ServiceContractError(f"invalid stop-post {label}: {value!r}")
    try:
        fixed: dict[str, Any] = {
            "state": "PASSED",
            "verification": verify_fixed_head(config, expected_head),
        }
    except ServiceContractError as exc:
        fixed = {"state": "FAILED_RECORDED", "error": str(exc)}
    timestamp = datetime.now(timezone.utc)
    key = timestamp.strftime("%Y%m%dT%H%M%S.%fZ") + f"_{os.getpid()}_post"
    root = repo_path(config["stop_control"]["audit_root"])
    path = root / f"{key}.json"
    normalized_exit = exit_status.upper()
    payload = {
        "schema": STOP_POST_AUDIT_SCHEMA,
        "state": "STOP_OUTCOME_RECORDED",
        "created_at": timestamp.isoformat(),
        "unit_name": config["service"]["unit_name"],
        "expected_head": expected_head,
        "fixed_head": fixed,
        "service_result": service_result,
        "exit_code": exit_code,
        "exit_status": exit_status,
        "timeout_observed": service_result.lower() == "timeout",
        "emergency_sigkill_observed": exit_code.lower() == "killed"
        and normalized_exit in {"9", "KILL", "SIGKILL"},
        "post_stop_service_status": service_status(config),
        "partial_artifacts_preserved": True,
        "partial_artifacts_deleted": False,
        "overwrite_allowed": False,
        "interpretation_or_verdict": None,
    }
    outcome = exclusive_or_identical(path, canonical_json(payload))
    if outcome != "CREATED":
        raise ServiceContractError(f"stop-post audit path unexpectedly existed: {path}")
    return {
        "state": "RECORDED",
        "audit": regular_file_record(path, logical=repo_relative(path)),
        "timeout_observed": payload["timeout_observed"],
        "emergency_sigkill_observed": payload["emergency_sigkill_observed"],
        "partial_artifacts_preserved": True,
        "interpretation_or_verdict": None,
    }


def proc_cmdline(pid: int) -> list[str]:
    try:
        payload = Path(f"/proc/{pid}/cmdline").read_bytes()
    except (FileNotFoundError, PermissionError, OSError) as exc:
        raise ServiceContractError(f"cannot inspect command line for PID {pid}: {exc}") from exc
    return [
        item.decode("utf-8", errors="surrogateescape")
        for item in payload.split(b"\0")
        if item
    ]


def stable_source_record(path: Path, logical: str) -> dict[str, Any]:
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        return {"path": logical, "state": "MISSING"}
    if stat.S_ISLNK(metadata.st_mode):
        return {"path": logical, "state": "REJECTED_SYMLINK"}
    if stat.S_ISDIR(metadata.st_mode):
        try:
            entries = sum(1 for _ in os.scandir(path))
        except OSError as exc:
            return {"path": logical, "state": "UNREADABLE_DIRECTORY", "error": str(exc)}
        return {
            "path": logical,
            "state": "DIRECTORY_REFERENCE",
            "entries_immediate": entries,
            "recursive_indexed": False,
        }
    if not stat.S_ISREG(metadata.st_mode):
        return {"path": logical, "state": "REJECTED_SPECIAL"}
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        return {"path": logical, "state": "UNREADABLE_FILE", "error": str(exc)}
    digest = hashlib.sha256()
    try:
        before = os.fstat(descriptor)
        while True:
            block = os.read(descriptor, 1 << 20)
            if not block:
                break
            digest.update(block)
        after = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    stable = (
        before.st_dev,
        before.st_ino,
        before.st_size,
        before.st_mtime_ns,
        before.st_mode,
    ) == (
        after.st_dev,
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
        after.st_mode,
    )
    if not stable:
        return {
            "path": logical,
            "state": "CHANGING_DURING_READ",
            "bytes_before": before.st_size,
            "bytes_after": after.st_size,
        }
    return {
        "path": logical,
        "state": "REGULAR_FILE",
        "sha256": digest.hexdigest(),
        "bytes": after.st_size,
        "mtime_ns": after.st_mtime_ns,
    }


def build_review_index(config: Mapping[str, Any], expected_head: str | None = None) -> dict[str, Any]:
    head = git("rev-parse", "HEAD").stdout.strip()
    branch = git("branch", "--show-current").stdout.strip()
    if expected_head is not None:
        require_equal(head, require_head(expected_head), "review index expected HEAD")
    require_equal(branch, config["branch"], "review index branch")
    review = config["review_index"]
    control = [
        stable_source_record(repo_path(logical), logical) for logical in review["control_files"]
    ]
    roots = [
        stable_source_record(repo_path(logical), logical) for logical in review["reference_roots"]
    ]
    return {
        "schema": review["schema"],
        "state": "OBSERVATIONAL_INDEX",
        "created_at": now_iso(),
        "branch": branch,
        "head": head,
        "unit_name": config["service"]["unit_name"],
        "service_log": config["service"]["log"],
        "queue_root": config["queue"]["root"],
        "control_files": control,
        "reference_roots": roots,
        "source_read_only": True,
        "source_mutation_performed": False,
        "recursive_scientific_payload_hashing": False,
        "publication_overwrite_allowed": False,
        "observational_only": True,
        "interpretation_or_verdict": None,
    }


def publish_review_index(
    config: Mapping[str, Any], payload: Mapping[str, Any], publication_key: str
) -> dict[str, Any]:
    if PUBLICATION_KEY_RE.fullmatch(publication_key) is None:
        raise ServiceContractError(f"invalid review publication key: {publication_key!r}")
    root = repo_path(config["review_index"]["publication_root"])
    queue_root = repo_path(config["queue"]["root"])
    try:
        root.relative_to(queue_root)
    except ValueError:
        pass
    else:
        raise ServiceContractError("review publication root must be outside queue-v3 source root")
    destination = root / f"{publication_key}.json"
    document = {
        **dict(payload),
        "publication": {
            "key": publication_key,
            "path": repo_relative(destination),
            "exclusive_create": True,
            "source_namespace_unchanged": True,
        },
    }
    outcome = exclusive_or_identical(destination, canonical_json(document))
    if outcome != "CREATED":
        raise ServiceContractError(f"review publication already exists: {destination}")
    return {
        "state": "PUBLISHED",
        "publication": regular_file_record(destination, logical=repo_relative(destination)),
        "source_mutation_performed": False,
        "interpretation_or_verdict": None,
    }


def parser() -> argparse.ArgumentParser:
    argument_parser = argparse.ArgumentParser(description=__doc__)
    argument_parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    commands = argument_parser.add_subparsers(dest="command", required=True)
    render = commands.add_parser("render-unit")
    render.add_argument("--expected-head", required=True)
    install = commands.add_parser("install")
    install.add_argument("--expected-head", required=True)
    install.add_argument("--dry-run", action="store_true")
    preflight = commands.add_parser("exec-preflight")
    preflight.add_argument("--expected-head", required=True)
    stop_audit = commands.add_parser("record-stop-audit")
    stop_audit.add_argument("--expected-head", required=True)
    stop_post = commands.add_parser("record-stop-post-audit")
    stop_post.add_argument("--expected-head", required=True)
    stop_post.add_argument("--service-result", required=True)
    stop_post.add_argument("--exit-code", required=True)
    stop_post.add_argument("--exit-status", required=True)
    start = commands.add_parser("start")
    start.add_argument("--dry-run", action="store_true")
    stop = commands.add_parser("stop")
    stop.add_argument("--dry-run", action="store_true")
    commands.add_parser("status")
    logs = commands.add_parser("logs")
    logs.add_argument("--lines", type=int, default=200)
    boundary = commands.add_parser("boundary-check")
    boundary.add_argument("--run-v3-verify", action="store_true")
    review = commands.add_parser("review-index")
    review.add_argument("--expected-head")
    review.add_argument("--publish-key")
    return argument_parser


def main(argv: Sequence[str] | None = None) -> int:
    args = parser().parse_args(argv)
    config = load_config(args.config)
    if args.command == "render-unit":
        sys.stdout.buffer.write(render_unit(config, args.expected_head))
        return 0
    if args.command == "install":
        result = install_service(config, args.expected_head, dry_run=args.dry_run)
    elif args.command == "exec-preflight":
        result = exec_preflight(config, args.expected_head)
    elif args.command == "record-stop-audit":
        result = record_stop_audit(config, args.expected_head)
    elif args.command == "record-stop-post-audit":
        result = record_stop_post_audit(
            config,
            args.expected_head,
            args.service_result,
            args.exit_code,
            args.exit_status,
        )
    elif args.command == "start":
        result = start_service(config, dry_run=args.dry_run)
    elif args.command == "stop":
        result = stop_service(config, dry_run=args.dry_run)
    elif args.command == "status":
        result = service_status(config)
    elif args.command == "logs":
        print(tail_lines(repo_path(config["service"]["log"]), args.lines))
        return 0
    elif args.command == "boundary-check":
        result = verify_source_boundary(config, run_v3_verify=args.run_v3_verify)
    elif args.command == "review-index":
        result = build_review_index(config, args.expected_head)
        if args.publish_key:
            result = {
                "index": result,
                "publication_result": publish_review_index(config, result, args.publish_key),
            }
    else:  # pragma: no cover
        raise ServiceContractError(f"unsupported command: {args.command}")
    print(pretty_json(result))
    return 0


if __name__ == "__main__":
    selected = None
    try:
        selected = parser().parse_known_args()[0].command
        raise SystemExit(main())
    except ServiceContractError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(78 if selected == "exec-preflight" else 2)
