#!/usr/bin/env python3
"""Reproducible section-0 resume preflight for FUS-W1.

This program is intentionally limited to environment/input measurement.  It
does not import the training entry point, launch training, extract a point
cloud, run Roofer on experiment data, or score a building.

The program must run in the pinned GS Docker image with:

* the repository bind-mounted at ``/workspace/JointBuildGS``;
* the same host repository mounted read-only at
  ``/host-control/JointBuildGS``;
* the Docker socket and client available for read-only image/runtime probes;
* the host PID namespace visible for the no-active-training guard; and
* one CUDA device exposed for a real matrix-multiply smoke check.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import platform
import re
import sqlite3
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence
from zoneinfo import ZoneInfo


REPO = Path(__file__).resolve().parents[3]
DEFAULT_CONFIG = (
    REPO / "phases/p2-gsjso/configs/fusion_w1_preflight_resume_v1.json"
)
DEFAULT_HOST_CONTROL = Path("/host-control/JointBuildGS")
PASS_LIKE = {"passed", "passed_with_caveat"}
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class PreflightError(RuntimeError):
    """A deterministic preflight contract failure."""


class EventLog:
    def __init__(self, path: Path) -> None:
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        self._handle = path.open("w", encoding="utf-8")

    def write(self, event: str, **fields: Any) -> None:
        payload = {
            "timestamp_utc": utc_now(),
            "event": event,
            **fields,
        }
        self._handle.write(
            json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n"
        )
        self._handle.flush()

    def close(self) -> None:
        self._handle.close()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def kst_now() -> str:
    return datetime.now(ZoneInfo("Asia/Seoul")).isoformat()


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise PreflightError(f"JSON root must be an object: {path}")
    return payload


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path, chunk_bytes: int = 8 * 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(chunk_bytes)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rendered = json.dumps(
        payload, ensure_ascii=False, indent=2, sort_keys=True
    ) + "\n"
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
    ) as handle:
        temp_path = Path(handle.name)
        handle.write(rendered)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temp_path, path)


def run(
    command: Sequence[str],
    *,
    cwd: Path = REPO,
    check: bool = True,
    timeout: int = 300,
) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        list(command),
        cwd=cwd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=timeout,
    )
    if check and completed.returncode != 0:
        stderr = completed.stderr.strip()
        stdout = completed.stdout.strip()
        detail = stderr or stdout or "(no output)"
        raise PreflightError(
            f"command failed rc={completed.returncode}: "
            f"{' '.join(command)}: {detail}"
        )
    return completed


def git(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return run(
        [
            "git",
            "-c",
            f"safe.directory={REPO}",
            "-C",
            str(REPO),
            *args,
        ],
        check=check,
    )


def repo_relative_resolved(path: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(REPO.resolve()).as_posix()
    except ValueError:
        return str(resolved)


def status(name: str, ok: bool, evidence: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": name,
        "status": "passed" if ok else "failed",
        "evidence": evidence,
    }


def status_with_caveat(
    name: str,
    ok: bool,
    evidence: dict[str, Any],
    caveat: str | None,
) -> dict[str, Any]:
    if not ok:
        state = "failed"
    elif caveat:
        state = "passed_with_caveat"
    else:
        state = "passed"
    return {
        "name": name,
        "status": state,
        "evidence": evidence,
        **({"caveat": caveat} if caveat else {}),
    }


def run_check(
    name: str,
    function: Callable[[], dict[str, Any]],
    event_log: EventLog,
) -> dict[str, Any]:
    event_log.write("check_started", check=name)
    try:
        result = function()
        if result.get("name") != name:
            raise PreflightError(
                f"check returned wrong name: expected {name}, "
                f"got {result.get('name')}"
            )
    except Exception as exc:  # preserve a receipt even on unexpected failures
        result = {
            "name": name,
            "status": "failed",
            "evidence": {},
            "error_type": type(exc).__name__,
            "error": str(exc),
        }
    event_log.write(
        "check_finished",
        check=name,
        status=result["status"],
        error=result.get("error"),
    )
    return result


def validate_config(config: dict[str, Any]) -> None:
    if config.get("schema") != (
        "jointbuildgs.fusion_w1.preflight_resume_config.v1"
    ):
        raise PreflightError("unexpected resume preflight config schema")
    if config.get("execution_mode") != "docker_read_only_preflight":
        raise PreflightError("config does not lock Docker read-only preflight")

    git_lock = config["git_lock"]
    if git_lock["expected_branch"] != "exp/fusion-w1":
        raise PreflightError("branch lock drift")
    dispatch = git_lock["dispatch"]
    if not SHA256_RE.fullmatch(dispatch["sha256"]):
        raise PreflightError("invalid dispatch SHA-256 lock")
    amendment = git_lock["protocol_amendment"]
    if (
        amendment["commit"]
        != git_lock["required_ancestor_commits"]["protocol_amendment_v3a"]
    ):
        raise PreflightError("protocol amendment commit lock drift")
    if not amendment.get("amendment_id"):
        raise PreflightError("protocol amendment ID is required")
    for item in amendment["files"]:
        if not SHA256_RE.fullmatch(item["sha256"]):
            raise PreflightError("invalid protocol amendment SHA-256 lock")

    expected_implementation_files = {
        "config": (
            "phases/p2-gsjso/configs/"
            "fusion_w1_preflight_resume_v1.json"
        ),
        "script": (
            "phases/p2-gsjso/scripts/fusion_w1_preflight_resume.py"
        ),
        "wrapper": (
            "phases/p2-gsjso/scripts/"
            "run_fusion_w1_preflight_resume.sh"
        ),
        "test": (
            "phases/p2-gsjso/scripts/"
            "test_fusion_w1_preflight_resume.py"
        ),
    }
    implementation_files = git_lock.get("implementation_files")
    if not isinstance(implementation_files, list):
        raise PreflightError("implementation file contract is required")
    observed_implementation_files: dict[str, str] = {}
    for item in implementation_files:
        if not isinstance(item, dict):
            raise PreflightError("invalid implementation file contract entry")
        role = item.get("role")
        path = item.get("path")
        if (
            not isinstance(role, str)
            or not isinstance(path, str)
            or role in observed_implementation_files
        ):
            raise PreflightError("invalid implementation file role/path")
        resolved = (REPO / path).resolve()
        try:
            resolved.relative_to(REPO.resolve())
        except ValueError as exc:
            raise PreflightError(
                f"implementation path escapes repository: {path}"
            ) from exc
        observed_implementation_files[role] = path
    if observed_implementation_files != expected_implementation_files:
        raise PreflightError("implementation file contract drift")

    override = config["mount_freshness"]["missing_background_document"]
    if override["override_mode"] != "user_resume_override":
        raise PreflightError("only the explicit user resume override is allowed")
    if not override.get("provenance_caveat"):
        raise PreflightError("resume override must retain a provenance caveat")

    coordinate = config["coordinate_class_datum_lock"]
    if coordinate["crs"] != "EPSG:25832":
        raise PreflightError("CRS lock drift")
    if (coordinate["ground_class"], coordinate["building_class"]) != (2, 6):
        raise PreflightError("LAS class lock drift")
    if float(coordinate["active_orthometric_geoid_m"]) != 45.7:
        raise PreflightError("active W1 datum lock drift")

    plan = config["readout_resource_plan"]
    if (
        plan["mode"] != "serial_only"
        or int(plan["max_parallel_readout_jobs"]) != 1
        or bool(plan["concurrent_with_training"])
        or plan["memory"] != "24g"
        or plan["memory_swap"] != "24g"
        or int(plan["memory_bytes"]) != 24 * 1024**3
        or int(plan["memory_swap_bytes"]) != 24 * 1024**3
    ):
        raise PreflightError("serial 24g readout plan drift")

    time_policy = config["time_policy"]
    if (
        time_policy["amendment_id"] != amendment["amendment_id"]
        or time_policy["amendment_commit"] != amendment["commit"]
        or time_policy["timezone"] != "Asia/Seoul"
        or time_policy["snapshot_local_time"] != "06:30"
        or time_policy["snapshot_mode"] != "status_snapshot_only"
        or bool(time_policy["hard_stop_at_snapshot"])
        or not bool(time_policy["continue_after_snapshot"])
    ):
        raise PreflightError("06:30 snapshot-only policy drift")

    outputs = config["outputs"]
    prior = (REPO / outputs["prior_blocked_manifest"]).resolve()
    resume = (REPO / outputs["preflight_resume"]).resolve()
    receipt = (REPO / outputs["status_receipt"]).resolve()
    if prior in {resume, receipt}:
        raise PreflightError("resume output may not overwrite blocked manifest")
    if resume == receipt:
        raise PreflightError("resume JSON and status receipt must be separate")


def require_locked_config_path(
    config: dict[str, Any], config_path: Path
) -> None:
    locked_config_path = next(
        REPO / item["path"]
        for item in config["git_lock"]["implementation_files"]
        if item["role"] == "config"
    ).resolve()
    if config_path.resolve() != locked_config_path:
        raise PreflightError(
            "runtime config is not the committed implementation-contract config"
        )


def require_runtime() -> None:
    if not Path("/.dockerenv").exists():
        raise PreflightError("preflight must run inside Docker")
    if not Path("/var/run/docker.sock").is_socket():
        raise PreflightError("Docker socket is not mounted")
    if not Path("/usr/local/bin/docker").exists():
        raise PreflightError("Docker client is not mounted")
    if not DEFAULT_HOST_CONTROL.is_dir():
        raise PreflightError("read-only host-control bind is not mounted")


def check_git_lock(config: dict[str, Any]) -> dict[str, Any]:
    lock = config["git_lock"]
    branch = git("branch", "--show-current").stdout.strip()
    head = git("rev-parse", "HEAD").stdout.strip()
    required: dict[str, Any] = {}
    all_required = True
    for role, commit in lock["required_ancestor_commits"].items():
        commit_type = git("cat-file", "-t", commit, check=False)
        exists = commit_type.returncode == 0 and commit_type.stdout.strip() == "commit"
        ancestor_probe = git(
            "merge-base", "--is-ancestor", commit, head, check=False
        )
        ancestor = exists and ancestor_probe.returncode == 0
        required[role] = {
            "commit": commit,
            "type": commit_type.stdout.strip() if exists else None,
            "exists": exists,
            "ancestor_of_head": ancestor,
        }
        all_required = all_required and exists and ancestor

    dispatch = lock["dispatch"]
    dispatch_path = REPO / dispatch["path"]
    working_sha = sha256_file(dispatch_path) if dispatch_path.is_file() else None
    blob_probe = git(
        "show", f"{dispatch['commit']}:{dispatch['path']}", check=False
    )
    committed_sha = (
        sha256_bytes(blob_probe.stdout.encode("utf-8"))
        if blob_probe.returncode == 0
        else None
    )
    dispatch_ok = (
        working_sha == dispatch["sha256"]
        and committed_sha == dispatch["sha256"]
    )

    amendment = lock["protocol_amendment"]
    amendment_rows: list[dict[str, Any]] = []
    amendment_ok = True
    for item in amendment["files"]:
        working_path = REPO / item["path"]
        amendment_blob = git(
            "show", f"{amendment['commit']}:{item['path']}", check=False
        )
        amendment_working_sha = (
            sha256_file(working_path) if working_path.is_file() else None
        )
        amendment_committed_sha = (
            sha256_bytes(amendment_blob.stdout.encode("utf-8"))
            if amendment_blob.returncode == 0
            else None
        )
        matches = (
            amendment_working_sha == item["sha256"]
            and amendment_committed_sha == item["sha256"]
        )
        amendment_rows.append(
            {
                "path": item["path"],
                "expected_sha256": item["sha256"],
                "working_tree_sha256": amendment_working_sha,
                "committed_blob_sha256": amendment_committed_sha,
                "working_and_committed_match": matches,
            }
        )
        amendment_ok = amendment_ok and matches
    amendment_json_path = next(
        (
            REPO / item["path"]
            for item in amendment["files"]
            if item["path"].endswith(".json")
        ),
        None,
    )
    amendment_payload = (
        load_json(amendment_json_path)
        if amendment_json_path is not None and amendment_json_path.is_file()
        else {}
    )
    amendment_semantics_ok = (
        amendment_payload.get("amendment_id") == amendment["amendment_id"]
        and amendment_payload.get("cutoff_policy", {}).get(
            "hard_cutoff_removed"
        )
        is True
        and amendment_payload.get("cutoff_policy", {}).get(
            "snapshot_stops_execution"
        )
        is False
        and amendment_payload.get("cutoff_policy", {}).get(
            "continue_priority_queue_after_snapshot"
        )
        is True
    )
    amendment_ok = amendment_ok and amendment_semantics_ok

    implementation_rows: list[dict[str, Any]] = []
    implementation_ok = True
    for item in lock["implementation_files"]:
        working_path = REPO / item["path"]
        head_blob = git("show", f"{head}:{item['path']}", check=False)
        implementation_working_sha = (
            sha256_file(working_path) if working_path.is_file() else None
        )
        implementation_head_sha = (
            sha256_bytes(head_blob.stdout.encode("utf-8"))
            if head_blob.returncode == 0
            else None
        )
        matches = (
            implementation_working_sha is not None
            and implementation_head_sha is not None
            and implementation_working_sha == implementation_head_sha
        )
        implementation_rows.append(
            {
                "role": item["role"],
                "path": item["path"],
                "working_tree_sha256": implementation_working_sha,
                "head_committed_blob_sha256": implementation_head_sha,
                "head_blob_exists": head_blob.returncode == 0,
                "working_and_head_match": matches,
            }
        )
        implementation_ok = implementation_ok and matches

    porcelain = git(
        "status", "--porcelain=v1", "--untracked-files=all"
    ).stdout.splitlines()
    tracked_changes = [
        line for line in porcelain if line and not line.startswith("??")
    ]
    evidence = {
        "repository_root": str(REPO),
        "branch": branch,
        "expected_branch": lock["expected_branch"],
        "head": head,
        "required_commits": required,
        "dispatch": {
            "path": dispatch["path"],
            "lock_commit": dispatch["commit"],
            "expected_sha256": dispatch["sha256"],
            "working_tree_sha256": working_sha,
            "committed_blob_sha256": committed_sha,
            "working_and_committed_match": dispatch_ok,
        },
        "protocol_amendment": {
            "amendment_id": amendment["amendment_id"],
            "lock_commit": amendment["commit"],
            "files": amendment_rows,
            "semantics": {
                "hard_cutoff_removed": amendment_payload.get(
                    "cutoff_policy", {}
                ).get("hard_cutoff_removed"),
                "snapshot_stops_execution": amendment_payload.get(
                    "cutoff_policy", {}
                ).get("snapshot_stops_execution"),
                "continue_priority_queue_after_snapshot": (
                    amendment_payload.get("cutoff_policy", {}).get(
                        "continue_priority_queue_after_snapshot"
                    )
                ),
                "matches_time_policy": amendment_semantics_ok,
            },
            "working_and_committed_match": amendment_ok,
        },
        "implementation_head": head,
        "implementation_files": implementation_rows,
        "implementation_all_working_and_head_match": implementation_ok,
        "tracked_worktree_changes": tracked_changes,
        "untracked_path_count": sum(
            1 for line in porcelain if line.startswith("??")
        ),
        "note": (
            "Untracked output paths are recorded. Every contracted "
            "implementation file must already exist in HEAD and match its "
            "committed blob; tracked worktree changes fail this check."
        ),
    }
    ok = (
        branch == lock["expected_branch"]
        and all_required
        and dispatch_ok
        and amendment_ok
        and implementation_ok
        and not tracked_changes
    )
    return status("git_commit_branch_dispatch_lock", ok, evidence)


def docker_image_inspect(reference: str) -> dict[str, Any]:
    completed = run(["docker", "image", "inspect", reference])
    payload = json.loads(completed.stdout)
    if not isinstance(payload, list) or len(payload) != 1:
        raise PreflightError(f"unexpected docker inspect result: {reference}")
    item = payload[0]
    return {
        "reference": reference,
        "image_id": item["Id"],
        "repo_tags": item.get("RepoTags") or [],
        "repo_digests": item.get("RepoDigests") or [],
        "created": item.get("Created"),
        "oci_labels": (item.get("Config") or {}).get("Labels") or {},
    }


def check_docker_images(config: dict[str, Any]) -> dict[str, Any]:
    locks = config["images"]
    inspected = {
        role: docker_image_inspect(spec["reference"])
        for role, spec in locks.items()
    }

    import gsplat  # Docker image version evidence
    import torch

    training_versions = {
        "python": platform.python_version(),
        "torch": torch.__version__,
        "torch_cuda_build": torch.version.cuda,
        "gsplat": gsplat.__version__,
    }

    roofer = run(
        [
            "docker",
            "run",
            "--rm",
            "--pull=never",
            locks["roofer"]["reference"],
            "--version",
        ]
    )
    roofer_version = (roofer.stdout + roofer.stderr).strip()

    tools_python = run(
        [
            "docker",
            "run",
            "--rm",
            "--pull=never",
            "--entrypoint",
            "python",
            locks["tools"]["reference"],
            "-c",
            (
                "import json,sys,numpy,laspy,pyproj;"
                "print(json.dumps({'python':sys.version.split()[0],"
                "'numpy':numpy.__version__,'laspy':laspy.__version__,"
                "'pyproj':pyproj.__version__},sort_keys=True))"
            ),
        ]
    )
    tools_versions = json.loads(tools_python.stdout)
    version_commands = {
        "pdal": "pdal --version",
        "gdal": "gdalinfo --version",
        "val3dity": "val3dity --version",
        "citygml_tools": "citygml-tools --version",
    }
    for key, command in version_commands.items():
        probe = run(
            [
                "docker",
                "run",
                "--rm",
                "--pull=never",
                "--entrypoint",
                "/bin/bash",
                locks["tools"]["reference"],
                "-lc",
                command,
            ]
        )
        tools_versions[key] = (probe.stdout + probe.stderr).strip()

    checks: list[bool] = []
    for role, spec in locks.items():
        checks.append(inspected[role]["image_id"] == spec["image_id"])
    checks.append(
        locks["roofer"]["required_repo_digest"]
        in inspected["roofer"]["repo_digests"]
    )
    checks.append(locks["roofer"]["version_contains"] in roofer_version)
    checks.extend(
        training_versions[key] == expected
        for key, expected in locks["gs_training"]["versions"].items()
    )
    simple_tool_keys = ("python", "numpy", "laspy", "pyproj")
    checks.extend(
        tools_versions[key] == locks["tools"]["versions"][key]
        for key in simple_tool_keys
    )
    for observed_key, expected_key in (
        ("pdal", "pdal_contains"),
        ("gdal", "gdal_contains"),
        ("val3dity", "val3dity_contains"),
        ("citygml_tools", "citygml_tools_contains"),
    ):
        checks.append(
            locks["tools"]["versions"][expected_key]
            in tools_versions[observed_key]
        )

    evidence = {
        "docker_server": json.loads(
            run(["docker", "version", "--format", "{{json .Server}}"]).stdout
        ),
        "images": inspected,
        "versions": {
            "gs_training": training_versions,
            "roofer": roofer_version,
            "tools": tools_versions,
        },
    }
    return status("docker_image_ids_and_versions", all(checks), evidence)


def parse_nvidia_csv(output: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in output.splitlines():
        if not line.strip():
            continue
        parts = [value.strip() for value in line.split(",")]
        if len(parts) != 5:
            continue
        rows.append(
            {
                "index": int(parts[0]),
                "uuid": parts[1],
                "name": parts[2],
                "driver_version": parts[3],
                "memory_total_mib": int(parts[4]),
            }
        )
    return rows


def check_cuda_smoke(config: dict[str, Any]) -> dict[str, Any]:
    import torch

    lock = config["cuda_smoke"]
    available = torch.cuda.is_available()
    if not available:
        return status(
            "gpu_and_cuda_matmul",
            False,
            {"torch_cuda_available": False},
        )

    size = int(lock["matrix_size"])
    values = torch.arange(
        size * size, device="cuda", dtype=torch.float32
    ).reshape(size, size)
    product = values @ values.T
    torch.cuda.synchronize()
    finite = bool(torch.isfinite(product).all().item())
    checksum = float(product[0, 0].item())
    gpu_query = run(
        [
            "nvidia-smi",
            "--query-gpu=index,uuid,name,driver_version,memory.total",
            "--format=csv,noheader,nounits",
        ]
    )
    visible_gpus = parse_nvidia_csv(gpu_query.stdout)
    props = torch.cuda.get_device_properties(0)
    evidence = {
        "torch_cuda_available": available,
        "torch_cuda_build": torch.version.cuda,
        "visible_gpus_nvidia_smi": visible_gpus,
        "torch_logical_device": 0,
        "torch_device_name": props.name,
        "matrix_size": size,
        "operation": "torch float32 matrix @ transpose on CUDA",
        "finite": finite,
        "checksum": checksum,
        "expected_checksum": float(lock["expected_checksum"]),
        "allocated_bytes": int(torch.cuda.memory_allocated()),
    }
    ok = (
        finite == bool(lock["required_finite"])
        and math.isclose(
            checksum,
            float(lock["expected_checksum"]),
            abs_tol=float(lock["checksum_tolerance"]),
            rel_tol=0.0,
        )
        and len(visible_gpus) >= 1
    )
    return status("gpu_and_cuda_matmul", ok, evidence)


def sha256sum_stream_aggregate(
    logical_root: Path,
) -> tuple[str, int, int, list[dict[str, Any]]]:
    files = sorted(
        (path for path in logical_root.iterdir() if path.is_file()),
        key=lambda path: path.as_posix().encode("utf-8"),
    )
    aggregate = hashlib.sha256()
    total_bytes = 0
    inventory: list[dict[str, Any]] = []
    for path in files:
        digest = sha256_file(path)
        size = path.stat().st_size
        total_bytes += size
        logical = path.relative_to(REPO).as_posix()
        aggregate.update(f"{digest}  {logical}\n".encode("utf-8"))
        inventory.append(
            {
                "path": logical,
                "bytes": size,
                "sha256": digest,
            }
        )
    return aggregate.hexdigest(), len(files), total_bytes, inventory


def check_canonical_inputs(
    config: dict[str, Any], event_log: EventLog
) -> dict[str, Any]:
    lock = config["canonical_inputs"]
    rows: list[dict[str, Any]] = []
    ok = True
    for spec in lock["files"]:
        path = REPO / spec["path"]
        event_log.write(
            "input_hash_started", path=spec["path"], bytes=spec["bytes"]
        )
        if not path.is_file():
            row = {
                **spec,
                "exists": False,
                "matches_lock": False,
            }
        else:
            observed_size = path.stat().st_size
            observed_sha = sha256_file(path)
            matches = (
                observed_size == int(spec["bytes"])
                and observed_sha == spec["sha256"]
            )
            row = {
                "role": spec["role"],
                "path": spec["path"],
                "resolved_path": repo_relative_resolved(path),
                "exists": True,
                "bytes": observed_size,
                "expected_bytes": int(spec["bytes"]),
                "sha256": observed_sha,
                "expected_sha256": spec["sha256"],
                "matches_lock": matches,
            }
        rows.append(row)
        ok = ok and bool(row["matches_lock"])
        event_log.write(
            "input_hash_finished",
            path=spec["path"],
            matches_lock=row["matches_lock"],
        )

    image_lock = lock["training_image_set"]
    logical_root = REPO / image_lock["path"]
    event_log.write("image_set_hash_started", path=image_lock["path"])
    aggregate, count, total_bytes, inventory = sha256sum_stream_aggregate(
        logical_root
    )
    image_ok = (
        aggregate == image_lock["sha256sum_stream_aggregate"]
        and count == int(image_lock["file_count"])
        and total_bytes == int(image_lock["total_bytes"])
    )
    ok = ok and image_ok
    event_log.write(
        "image_set_hash_finished",
        path=image_lock["path"],
        file_count=count,
        total_bytes=total_bytes,
        matches_lock=image_ok,
    )
    evidence = {
        "files": rows,
        "training_image_set": {
            "path": image_lock["path"],
            "resolved_path": repo_relative_resolved(logical_root),
            "file_count": count,
            "expected_file_count": int(image_lock["file_count"]),
            "total_bytes": total_bytes,
            "expected_total_bytes": int(image_lock["total_bytes"]),
            "sha256sum_stream_aggregate": aggregate,
            "expected_sha256sum_stream_aggregate": image_lock[
                "sha256sum_stream_aggregate"
            ],
            "algorithm": image_lock["algorithm"],
            "matches_lock": image_ok,
            "per_file_inventory": inventory,
        },
    }
    return status("canonical_input_sha256", ok, evidence)


def check_mount_freshness(
    config: dict[str, Any],
    git_check: dict[str, Any],
    host_control_root: Path,
) -> dict[str, Any]:
    lock = config["mount_freshness"]
    controls: list[dict[str, Any]] = []
    controls_ok = True
    for spec in lock["control_files"]:
        container_path = REPO / spec["path"]
        host_path = host_control_root / spec["path"]
        container_exists = container_path.is_file()
        host_exists = host_path.is_file()
        if container_exists and host_exists:
            container_sha = sha256_file(container_path)
            host_sha = sha256_file(host_path)
            container_stat = container_path.stat()
            host_stat = host_path.stat()
            matches = (
                container_sha == spec["sha256"]
                and host_sha == spec["sha256"]
                and container_stat.st_size == host_stat.st_size
                and container_stat.st_mtime_ns == host_stat.st_mtime_ns
            )
            row = {
                "path": spec["path"],
                "container_exists": True,
                "host_control_exists": True,
                "container_sha256": container_sha,
                "host_control_sha256": host_sha,
                "expected_sha256": spec["sha256"],
                "container_mtime_ns": container_stat.st_mtime_ns,
                "host_control_mtime_ns": host_stat.st_mtime_ns,
                "size_bytes": container_stat.st_size,
                "host_container_match": matches,
            }
        else:
            matches = False
            row = {
                "path": spec["path"],
                "container_exists": container_exists,
                "host_control_exists": host_exists,
                "expected_sha256": spec["sha256"],
                "host_container_match": False,
            }
        controls.append(row)
        controls_ok = controls_ok and matches

    missing = lock["missing_background_document"]
    missing_container = REPO / missing["path"]
    missing_host = host_control_root / missing["path"]
    doc_absent = not missing_container.exists() and not missing_host.exists()
    dispatch_evidence = git_check.get("evidence", {}).get("dispatch", {})
    dispatch_lock_ok = bool(
        dispatch_evidence.get("working_and_committed_match")
    )
    override_valid = (
        missing["override_mode"] == "user_resume_override"
        and bool(missing.get("authorization_text"))
        and bool(missing.get("provenance_caveat"))
        and dispatch_lock_ok
    )

    if doc_absent:
        caveat = missing["provenance_caveat"]
        document_policy_ok = override_valid
        document_status = "absent_user_resume_override"
    else:
        caveat = (
            "The background document appeared without an expected SHA-256 "
            "and committed-source lock. The absence-only user resume override "
            "does not authorize this file."
        )
        document_policy_ok = False
        document_status = "unexpected_present_unlocked"

    evidence = {
        "host_control_mount": str(host_control_root),
        "control_files": controls,
        "missing_background_document": {
            "path": missing["path"],
            "container_exists": missing_container.exists(),
            "host_control_exists": missing_host.exists(),
            "status": document_status,
            "override_mode": missing["override_mode"],
            "authorization_date_local": missing["authorization_date_local"],
            "authorization_text": missing["authorization_text"],
            "override_scope": missing["scope"],
            "dispatch_working_and_committed_match": dispatch_lock_ok,
            "override_valid": override_valid,
            "expected_sha256": None,
            "committed_source_lock": None,
            "not_reconstructed_or_substituted": doc_absent,
        },
    }
    return status_with_caveat(
        "host_container_mount_and_resume_provenance",
        controls_ok and document_policy_ok,
        evidence,
        caveat,
    )


def read_gpkg_srs(path: Path) -> dict[str, Any]:
    connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        contents = connection.execute(
            "SELECT table_name, data_type, srs_id FROM gpkg_contents "
            "ORDER BY table_name"
        ).fetchall()
        srs = connection.execute(
            "SELECT srs_name, srs_id, organization, "
            "organization_coordsys_id FROM gpkg_spatial_ref_sys "
            "WHERE srs_id = 25832"
        ).fetchall()
    finally:
        connection.close()
    return {
        "contents": [
            {"table": row[0], "data_type": row[1], "srs_id": row[2]}
            for row in contents
        ],
        "epsg_25832_definition": [
            {
                "srs_name": row[0],
                "srs_id": row[1],
                "organization": row[2],
                "organization_coordsys_id": row[3],
            }
            for row in srs
        ],
    }


def inspect_laz_classes(
    tools_reference: str, host_repo: str, paths: Iterable[str]
) -> list[dict[str, Any]]:
    code = r"""
import json
import sys
import laspy
import numpy as np

rows = []
for source in sys.argv[1:]:
    counts = {}
    with laspy.open(source) as reader:
        header = reader.header
        parsed_crs = header.parse_crs()
        for points in reader.chunk_iterator(2_000_000):
            values, frequencies = np.unique(
                np.asarray(points.classification, dtype=np.int64),
                return_counts=True,
            )
            for value, frequency in zip(values.tolist(), frequencies.tolist()):
                key = str(int(value))
                counts[key] = counts.get(key, 0) + int(frequency)
        rows.append(
            {
                "path": source,
                "point_count": int(header.point_count),
                "header_crs": None if parsed_crs is None else str(parsed_crs),
                "classification_counts": counts,
            }
        )
print(json.dumps(rows, sort_keys=True))
"""
    container_paths = [
        f"/workspace/JointBuildGS/{path}" for path in paths
    ]
    completed = run(
        [
            "docker",
            "run",
            "--rm",
            "--pull=never",
            "--entrypoint",
            "python",
            "-v",
            f"{host_repo}:/workspace/JointBuildGS:ro",
            tools_reference,
            "-c",
            code,
            *container_paths,
        ],
        timeout=600,
    )
    rows = json.loads(completed.stdout)
    for row, logical in zip(rows, paths):
        row["path"] = logical
    return rows


def extract_gml_srs(path: Path) -> list[str]:
    with path.open("rb") as handle:
        sample = handle.read(8 * 1024 * 1024).decode(
            "utf-8", errors="replace"
        )
    return sorted(set(re.findall(r'srsName="([^"]+)"', sample)))


def check_coordinate_class_datum(
    config: dict[str, Any], host_repo: str
) -> dict[str, Any]:
    lock = config["coordinate_class_datum_lock"]
    datum_path = REPO / lock["projection_datum_config"]
    datum_sha = sha256_file(datum_path)
    datum = load_json(datum_path)
    datum_ok = (
        datum_sha == lock["projection_datum_config_sha256"]
        and datum.get("geo_crs") == lock["crs"]
        and datum.get("input_vertical_datum_default")
        == lock["input_vertical_datum_default"]
        and float(datum.get("orthometric_geoid_m"))
        == float(lock["active_orthometric_geoid_m"])
        and float(datum.get("a1_zeta_ls", {}).get("zeta_hat_m"))
        == float(lock["recorded_nonactive_a1_zeta_hat_m"])
    )

    gpkg = read_gpkg_srs(REPO / lock["footprint_gpkg"])
    gpkg_srs_ids = {int(row["srs_id"]) for row in gpkg["contents"]}
    gpkg_ok = gpkg_srs_ids == {25832} and bool(
        gpkg["epsg_25832_definition"]
    )

    als_paths = [
        item["path"]
        for item in config["canonical_inputs"]["files"]
        if item["role"] == "als_laz"
    ]
    laz_rows = inspect_laz_classes(
        config["images"]["tools"]["reference"], host_repo, als_paths
    )
    ground = str(int(lock["ground_class"]))
    building = str(int(lock["building_class"]))
    classes_ok = bool(laz_rows) and all(
        int(row["classification_counts"].get(ground, 0)) > 0
        and int(row["classification_counts"].get(building, 0)) > 0
        for row in laz_rows
    )
    raw_headers_missing = all(row["header_crs"] is None for row in laz_rows)

    gml_paths = [
        REPO / item["path"]
        for item in config["canonical_inputs"]["files"]
        if item["role"] == "reference_gml"
    ]
    gml_srs = {
        path.relative_to(REPO).as_posix(): extract_gml_srs(path)
        for path in gml_paths
    }
    gml_xy_ok = all(
        any("ETRS89_UTM32" in name for name in names)
        for names in gml_srs.values()
    )

    evidence = {
        "crs_lock": lock["crs"],
        "footprint_gpkg": {
            "path": lock["footprint_gpkg"],
            **gpkg,
        },
        "reference_gml_srs_names": gml_srs,
        "als": {
            "ground_class": int(lock["ground_class"]),
            "building_class": int(lock["building_class"]),
            "tiles": laz_rows,
            "both_required_classes_present_in_every_tile": classes_ok,
            "raw_headers_have_no_embedded_crs": raw_headers_missing,
            "raw_header_crs_policy": lock["raw_als_header_crs_policy"],
        },
        "datum": {
            "config_path": lock["projection_datum_config"],
            "config_sha256": datum_sha,
            "expected_config_sha256": lock[
                "projection_datum_config_sha256"
            ],
            "input_vertical_datum_default": datum.get(
                "input_vertical_datum_default"
            ),
            "active_orthometric_geoid_m": datum.get(
                "orthometric_geoid_m"
            ),
            "recorded_nonactive_a1_zeta_hat_m": datum.get(
                "a1_zeta_ls", {}
            ).get("zeta_hat_m"),
            "w1_selection": lock["w1_datum_selection"],
            "three_dimensional_seed_path_unchanged": True,
        },
    }
    caveat = (
        lock["raw_als_header_crs_policy"] if raw_headers_missing else None
    )
    return status_with_caveat(
        "epsg_class_and_datum_lock",
        datum_ok and gpkg_ok and gml_xy_ok and classes_ok,
        evidence,
        caveat,
    )


def process_command(pid: int) -> str:
    try:
        raw = Path(f"/proc/{pid}/cmdline").read_bytes()
    except (FileNotFoundError, PermissionError, ProcessLookupError):
        return ""
    return raw.replace(b"\x00", b" ").decode("utf-8", errors="replace").strip()


def scan_processes(
    patterns: Sequence[str],
    *,
    pids: Iterable[int] | None = None,
) -> list[dict[str, Any]]:
    compiled = [re.compile(pattern, flags=re.IGNORECASE) for pattern in patterns]
    if pids is None:
        pids = (
            int(path.name)
            for path in Path("/proc").iterdir()
            if path.name.isdigit()
        )
    matches: list[dict[str, Any]] = []
    own_pid = os.getpid()
    for pid in pids:
        if pid == own_pid:
            continue
        command = process_command(pid)
        if not command:
            continue
        matched = [regex.pattern for regex in compiled if regex.search(command)]
        if matched:
            matches.append(
                {
                    "pid": pid,
                    "command": command,
                    "matched_regexes": matched,
                }
            )
    return sorted(matches, key=lambda item: item["pid"])


def parse_json_lines(text: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in text.splitlines():
        if not line.strip():
            continue
        item = json.loads(line)
        if isinstance(item, dict):
            rows.append(item)
    return rows


def parse_compute_apps(text: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in text.splitlines():
        if not line.strip():
            continue
        parts = [value.strip() for value in line.split(",", 2)]
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
            used_memory_mib = int(parts[2])
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
                "used_memory_mib": used_memory_mib,
                "command": process_command(pid),
                "parse_error": False,
            }
        )
    return rows


def check_no_active_training(config: dict[str, Any]) -> dict[str, Any]:
    patterns = config["training_process_guard"]["forbidden_command_regexes"]
    process_matches = scan_processes(patterns)

    containers = parse_json_lines(
        run(["docker", "ps", "--no-trunc", "--format", "{{json .}}"]).stdout
    )
    relevant_containers = []
    container_command_matches = []
    compiled = [re.compile(pattern, re.IGNORECASE) for pattern in patterns]
    for item in containers:
        labels = item.get("Labels", "")
        image = item.get("Image", "")
        names = item.get("Names", "")
        command = item.get("Command", "")
        relevant = (
            "com.docker.compose.project=jointbuildgs" in labels
            or "jointbuildgs" in image.lower()
            or "jointbuildgs" in names.lower()
        )
        if relevant:
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
        matched = [regex.pattern for regex in compiled if regex.search(command)]
        if matched:
            container_command_matches.append(
                {
                    "id": item.get("ID"),
                    "name": names,
                    "image": image,
                    "command": command,
                    "matched_regexes": matched,
                }
            )

    compute_probe = run(
        [
            "nvidia-smi",
            "--query-compute-apps=pid,process_name,used_memory",
            "--format=csv,noheader,nounits",
        ],
        check=False,
    )
    gpu_compute_processes = parse_compute_apps(compute_probe.stdout)
    own_pid = os.getpid()
    own_gpu_compute_processes = [
        row for row in gpu_compute_processes if row.get("pid") == own_pid
    ]
    unknown_gpu_compute_processes = [
        row for row in gpu_compute_processes if row.get("pid") != own_pid
    ]
    gpu_probe_ok = compute_probe.returncode == 0
    known_training_absent = (
        not process_matches and not container_command_matches
    )
    no_active_training = known_training_absent and gpu_probe_ok
    unknown_caveat = None
    if gpu_probe_ok and unknown_gpu_compute_processes:
        unknown_caveat = (
            "Unknown GPU compute processes were observed. This preflight "
            "records a caveated pass only for environment inspection; Gate A, "
            "training, and readout launchers must fail closed until a fresh "
            "probe has no unknown compute process."
        )

    evidence = {
        "host_pid_namespace_visible": Path("/proc/1").exists(),
        "forbidden_command_regexes": patterns,
        "matching_processes": process_matches,
        "matching_container_commands": container_command_matches,
        "relevant_running_containers": relevant_containers,
        "nvidia_compute_probe_returncode": compute_probe.returncode,
        "gpu_compute_processes": gpu_compute_processes,
        "preflight_own_gpu_compute_processes": own_gpu_compute_processes,
        "unknown_gpu_compute_processes": unknown_gpu_compute_processes,
        "guard_scope": (
            "Block known JointBuildGS training entry points. Other GPU "
            "compute processes block every later Gate A/training/readout "
            "launcher until a fresh fail-closed probe is clean."
        ),
        "known_training_entry_points_absent": known_training_absent,
        "no_active_training": no_active_training,
        "future_gpu_stage_launch_blocked": (
            not no_active_training or bool(unknown_gpu_compute_processes)
        ),
        "future_launch_policy": (
            "Rerun immediately before Gate A, training, or readout. Fail "
            "closed on a failed nvidia-smi query, a known training command, "
            "or any GPU compute PID other than the probing process itself."
        ),
    }
    return status_with_caveat(
        "no_active_training_guard",
        no_active_training,
        evidence,
        unknown_caveat,
    )


def parse_meminfo() -> dict[str, int]:
    result: dict[str, int] = {}
    for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
        key, raw = line.split(":", 1)
        parts = raw.strip().split()
        if not parts:
            continue
        value = int(parts[0])
        if len(parts) == 2 and parts[1] == "kB":
            value *= 1024
        result[key] = value
    return result


def check_readout_plan(config: dict[str, Any]) -> dict[str, Any]:
    lock = config["readout_resource_plan"]
    docker_info = json.loads(
        run(["docker", "info", "--format", "{{json .}}"]).stdout
    )
    meminfo = parse_meminfo()
    cgroup_version = str(docker_info.get("CgroupVersion", ""))
    flags = list(lock["required_docker_flags"])
    plan_ok = (
        lock["mode"] == "serial_only"
        and int(lock["max_parallel_readout_jobs"]) == 1
        and not lock["concurrent_with_training"]
        and flags == ["--memory=24g", "--memory-swap=24g"]
        and int(lock["memory_bytes"]) == 24 * 1024**3
        and int(lock["memory_swap_bytes"]) == 24 * 1024**3
        and cgroup_version == "2"
        and docker_info.get("MemoryLimit") is True
        and docker_info.get("SwapLimit") is True
    )
    evidence = {
        "docker_engine": {
            "server_version": docker_info.get("ServerVersion"),
            "driver": docker_info.get("Driver"),
            "cgroup_driver": docker_info.get("CgroupDriver"),
            "cgroup_version": docker_info.get("CgroupVersion"),
            "memory_limit_supported": docker_info.get("MemoryLimit"),
            "swap_limit_supported": docker_info.get("SwapLimit"),
        },
        "host_memory": {
            "mem_total_bytes": meminfo.get("MemTotal"),
            "mem_available_bytes": meminfo.get("MemAvailable"),
            "swap_total_bytes": meminfo.get("SwapTotal"),
            "swap_free_bytes": meminfo.get("SwapFree"),
        },
        "plan": {
            **lock,
            "docker_command_contract": [
                "docker",
                "run",
                "--rm",
                "--memory=24g",
                "--memory-swap=24g",
                "<other-locked-mounts-and-image>",
                "<serial-readout-command>",
            ],
            "cgroup_limit_applied_now": False,
            "not_applied_reason": (
                "Preflight only; no readout container or training run launched."
            ),
            "future_launch_must_recheck_training_guard": True,
            "future_readout_launcher_must_apply_cgroup_flags": True,
            "future_readout_launcher_must_acquire_serial_lock": True,
            "future_gate_a_or_gpu_stage_must_recheck_unknown_compute": True,
        },
    }
    return status("readout_serial_24g_cgroup_plan", plan_ok, evidence)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument(
        "--host-control-root", type=Path, default=DEFAULT_HOST_CONTROL
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config_path = args.config.resolve()
    config = load_json(config_path)
    validate_config(config)
    require_locked_config_path(config, config_path)
    require_runtime()

    output_config = config["outputs"]
    prior_path = REPO / output_config["prior_blocked_manifest"]
    output_path = REPO / output_config["preflight_resume"]
    receipt_path = REPO / output_config["status_receipt"]
    log_path = REPO / output_config["event_log"]
    prior_before = sha256_file(prior_path)
    prior_payload = load_json(prior_path)

    event_log = EventLog(log_path)
    event_log.write(
        "preflight_started",
        config=str(config_path.relative_to(REPO)),
        config_sha256=sha256_file(config_path),
        prior_blocked_manifest_sha256=prior_before,
    )
    try:
        git_check = run_check(
            "git_commit_branch_dispatch_lock",
            lambda: check_git_lock(config),
            event_log,
        )
        checks = [
            git_check,
            run_check(
                "docker_image_ids_and_versions",
                lambda: check_docker_images(config),
                event_log,
            ),
            run_check(
                "gpu_and_cuda_matmul",
                lambda: check_cuda_smoke(config),
                event_log,
            ),
            run_check(
                "canonical_input_sha256",
                lambda: check_canonical_inputs(config, event_log),
                event_log,
            ),
            run_check(
                "host_container_mount_and_resume_provenance",
                lambda: check_mount_freshness(
                    config, git_check, args.host_control_root
                ),
                event_log,
            ),
            run_check(
                "epsg_class_and_datum_lock",
                lambda: check_coordinate_class_datum(
                    config, os.environ["FUS_W1_HOST_REPO"]
                ),
                event_log,
            ),
            run_check(
                "no_active_training_guard",
                lambda: check_no_active_training(config),
                event_log,
            ),
            run_check(
                "readout_serial_24g_cgroup_plan",
                lambda: check_readout_plan(config),
                event_log,
            ),
        ]

        all_passed = all(item["status"] in PASS_LIKE for item in checks)
        caveats = [
            {
                "check": item["name"],
                "caveat": item["caveat"],
            }
            for item in checks
            if item.get("caveat")
        ]
        git_evidence = git_check.get("evidence", {})
        implementation_provenance = {
            "head": git_evidence.get("implementation_head"),
            "all_working_and_head_match": git_evidence.get(
                "implementation_all_working_and_head_match"
            ),
            "tracked_worktree_changes": git_evidence.get(
                "tracked_worktree_changes"
            ),
            "files": git_evidence.get("implementation_files", []),
        }
        no_training_check = next(
            item
            for item in checks
            if item["name"] == "no_active_training_guard"
        )
        future_gpu_stage_launch_blocked = bool(
            no_training_check.get("evidence", {}).get(
                "future_gpu_stage_launch_blocked", True
            )
        )
        five_pin_names = [
            "git_commit_branch_dispatch_lock",
            "docker_image_ids_and_versions",
            "gpu_and_cuda_matmul",
            "canonical_input_sha256",
            "host_container_mount_and_resume_provenance",
        ]
        five_pins = [
            next(item for item in checks if item["name"] == name)
            for name in five_pin_names
        ]
        prior_after = sha256_file(prior_path)
        prior_preserved = prior_before == prior_after
        all_passed = all_passed and prior_preserved

        manifest = {
            "schema": "jointbuildgs.fusion_w1.preflight_resume.v1",
            "task_id": config["task_id"],
            "run_id": config["run_id"],
            "created_utc": utc_now(),
            "created_kst": kst_now(),
            "execution_mode": config["execution_mode"],
            "overall_status": "PASSED" if all_passed else "BLOCKED",
            "interpretation_or_verdict": None,
            "config": {
                "path": config_path.relative_to(REPO).as_posix(),
                "sha256": sha256_file(config_path),
            },
            "implementation_provenance": implementation_provenance,
            "prior_blocked_receipt": {
                "path": output_config["prior_blocked_manifest"],
                "recorded_status": prior_payload.get("run_status"),
                "sha256_before": prior_before,
                "sha256_after": prior_after,
                "preserved_unchanged": prior_preserved,
                "superseded_or_overwritten": False,
            },
            "five_pin_preflight": {
                "passed_or_caveated_count": sum(
                    item["status"] in PASS_LIKE for item in five_pins
                ),
                "total_pin_count": len(five_pins),
                "pins": five_pins,
            },
            "additional_execution_guards": [
                item for item in checks if item not in five_pins
            ],
            "provenance_caveats": caveats,
            "resume_override": config["mount_freshness"][
                "missing_background_document"
            ],
            "execution_counters": {
                "learning_runs_started_by_preflight": 0,
                "gate_a_measurements_started_by_preflight": 0,
                "seed_preparations_started_by_preflight": 0,
                "readout_runs_started_by_preflight": 0,
                "roofer_experiment_runs_started_by_preflight": 0,
                "scoring_runs_started_by_preflight": 0,
            },
            "continuation_contract": {
                "section_0_resume_gate_passed": all_passed,
                "next_stage_if_passed": (
                    "target resolution and per-building Gate A measurement"
                    if all_passed
                    else None
                ),
                "learning_entry_authorized_by_this_receipt": False,
                "learning_entry_reason": (
                    "Each building must pass Gate A before training entry."
                ),
                "preflight_resource_plan_is_plan_only": True,
                "gate_a_or_later_gpu_launcher_must_recheck_compute_guard": True,
                "future_gpu_stage_launch_blocked_at_receipt": (
                    future_gpu_stage_launch_blocked
                ),
                "readout_launcher_must_apply_serial_lock_and_24g_cgroup": True,
                "readout_launcher_contract": (
                    "Before every readout launch, rerun the no-active-training "
                    "and unknown-compute guard, acquire the single serial lock, "
                    "and apply --memory=24g --memory-swap=24g. This preflight "
                    "does not apply those runtime controls."
                ),
                "human_verdict_written": False,
            },
            "time_policy": config["time_policy"],
        }
        atomic_write_json(output_path, manifest)
        manifest_sha = sha256_file(output_path)

        receipt = {
            "schema": "jointbuildgs.fusion_w1.preflight_resume_status.v1",
            "task_id": config["task_id"],
            "run_id": config["run_id"],
            "created_utc": utc_now(),
            "created_kst": kst_now(),
            "status": manifest["overall_status"],
            "preflight_resume": {
                "path": output_config["preflight_resume"],
                "sha256": manifest_sha,
            },
            "implementation_provenance": implementation_provenance,
            "event_log": {
                "path": output_config["event_log"],
            },
            "prior_blocked_manifest": manifest["prior_blocked_receipt"],
            "five_pin_passed_or_caveated_count": manifest[
                "five_pin_preflight"
            ]["passed_or_caveated_count"],
            "five_pin_total_count": manifest["five_pin_preflight"][
                "total_pin_count"
            ],
            "failed_checks": [
                item["name"] for item in checks if item["status"] == "failed"
            ],
            "caveat_checks": [item["check"] for item in caveats],
            "actual_training_started": False,
            "actual_readout_started": False,
            "continuation_authorized": all_passed,
            "next_stage": manifest["continuation_contract"][
                "next_stage_if_passed"
            ],
            "learning_still_gated_by_gate_a": True,
            "preflight_resource_plan_is_plan_only": True,
            "future_gpu_stage_launch_blocked_at_receipt": (
                future_gpu_stage_launch_blocked
            ),
            "future_launcher_requirements": [
                (
                    "Rerun the known-training and unknown-GPU-compute guard "
                    "immediately before Gate A or any later GPU stage."
                ),
                (
                    "Before readout, acquire the single serial lock and apply "
                    "--memory=24g --memory-swap=24g."
                ),
            ],
            "time_policy": config["time_policy"],
            "commit_created_by_preflight": False,
        }
        atomic_write_json(receipt_path, receipt)
        event_log.write(
            "preflight_finished",
            status=manifest["overall_status"],
            output=output_config["preflight_resume"],
            output_sha256=manifest_sha,
            status_receipt=output_config["status_receipt"],
        )
        print(
            json.dumps(
                {
                    "status": manifest["overall_status"],
                    "preflight_resume": output_config["preflight_resume"],
                    "preflight_resume_sha256": manifest_sha,
                    "status_receipt": output_config["status_receipt"],
                    "five_pins": (
                        f"{manifest['five_pin_preflight']['passed_or_caveated_count']}"
                        f"/{manifest['five_pin_preflight']['total_pin_count']}"
                    ),
                    "failed_checks": receipt["failed_checks"],
                    "learning_runs_started": 0,
                    "readout_runs_started": 0,
                },
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        return 0 if all_passed else 2
    finally:
        event_log.close()


if __name__ == "__main__":
    raise SystemExit(main())
