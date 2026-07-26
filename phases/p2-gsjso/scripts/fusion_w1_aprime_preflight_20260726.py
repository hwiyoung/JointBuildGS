#!/usr/bin/env python3
"""Write the arm A-prime five-pin preflight measurement receipt.

This is a Docker-only evidence collector.  It deliberately does not decide a
research verdict and does not authorize T1, training, readout, or scoring.
The working tree may contain the named prior-run evidence and the concurrent
T1 implementation diff; those paths are classified in the receipt instead of
being mistaken for a clean-tree launch gate.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import platform
import re
import subprocess
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Sequence
from zoneinfo import ZoneInfo


REPO = Path(__file__).resolve().parents[3]
DEFAULT_CONFIG = (
    REPO
    / "phases/p2-gsjso/configs/"
    "fusion_w1_aprime_preflight_20260726.json"
)
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class PreflightError(RuntimeError):
    """A five-pin contract or measurement failure."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def kst_now() -> str:
    return datetime.now(ZoneInfo("Asia/Seoul")).isoformat()


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise PreflightError(f"JSON root is not an object: {path}")
    return payload


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


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
        temporary = Path(handle.name)
        handle.write(rendered)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def run(
    command: Sequence[str],
    *,
    cwd: Path = REPO,
    check: bool = True,
    timeout: int = 600,
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
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise PreflightError(
            f"command failed rc={completed.returncode}: "
            f"{' '.join(command)}: {detail or '(no output)'}"
        )
    return completed


def run_bytes(
    command: Sequence[str],
    *,
    cwd: Path = REPO,
    check: bool = True,
    timeout: int = 600,
) -> subprocess.CompletedProcess[bytes]:
    completed = subprocess.run(
        list(command),
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=timeout,
    )
    if check and completed.returncode != 0:
        detail = completed.stderr.decode("utf-8", errors="replace").strip()
        raise PreflightError(
            f"command failed rc={completed.returncode}: "
            f"{' '.join(command)}: {detail or '(no output)'}"
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


def git_bytes(
    *args: str, check: bool = True
) -> subprocess.CompletedProcess[bytes]:
    return run_bytes(
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


def status(name: str, ok: bool, evidence: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": name,
        "status": "passed" if ok else "failed",
        "evidence": evidence,
    }


def measured(
    name: str, function: Callable[[], dict[str, Any]]
) -> dict[str, Any]:
    started = time.monotonic()
    try:
        result = function()
        if result.get("name") != name:
            raise PreflightError(
                f"wrong check name: expected={name} got={result.get('name')}"
            )
    except Exception as exc:  # always preserve a structured receipt
        result = {
            "name": name,
            "status": "failed",
            "evidence": {},
            "error_type": type(exc).__name__,
            "error": str(exc),
        }
    result["elapsed_seconds"] = round(time.monotonic() - started, 6)
    return result


def validate_config(config: dict[str, Any]) -> None:
    if config.get("schema") != (
        "jointbuildgs.fusion_w1_aprime.preflight_config.v1"
    ):
        raise PreflightError("unexpected config schema")
    if config.get("purpose") != (
        "five_pin_measurement_receipt_not_a_training_launch_gate"
    ):
        raise PreflightError("preflight purpose drift")
    if config.get("verdict") is not None:
        raise PreflightError("preflight config must keep verdict null")
    git_lock = config["git"]
    if git_lock.get("expected_branch") != "exp/fusion-w1":
        raise PreflightError("branch contract drift")
    if not re.fullmatch(r"[0-9a-f]{40}", git_lock["required_ancestor_commit"]):
        raise PreflightError("invalid preregistration commit")
    roles: set[str] = set()
    for item in git_lock["locked_documents"]:
        if item["role"] in roles:
            raise PreflightError("duplicate locked-document role")
        roles.add(item["role"])
        if not SHA256_RE.fullmatch(item["sha256"]):
            raise PreflightError("invalid locked-document SHA-256")
    if roles != {
        "aprime_dispatch",
        "aprime_preregistration",
        "aprime_machine_preregistration",
    }:
        raise PreflightError("incomplete preregistration document lock")
    dirty = git_lock["dirty_state_policy"]
    if (
        dirty.get("mode") != "record_and_classify_only"
        or dirty.get("training_launch_gate_evaluated") is not False
    ):
        raise PreflightError("dirty-state receipt policy drift")
    for item in config["docker_images"].values():
        if not re.fullmatch(r"sha256:[0-9a-f]{64}", item["image_id"]):
            raise PreflightError("invalid Docker image ID lock")
    for item in config["locked_sources"].values():
        if not SHA256_RE.fullmatch(item["sha256"]):
            raise PreflightError("invalid locked-source SHA-256")
    files = config["canonical_inputs"]["files"]
    if sum(item["role"] == "als_laz" for item in files) != 4:
        raise PreflightError("exactly four ALS locks are required")
    if sum(item["role"] == "reference_gml" for item in files) != 2:
        raise PreflightError("exactly two reference GML locks are required")
    for item in files:
        if not SHA256_RE.fullmatch(item["sha256"]):
            raise PreflightError("invalid input SHA-256")
    outputs = config["outputs"]
    if outputs["receipt"] == outputs["status"]:
        raise PreflightError("receipt and status paths must differ")


def require_runtime(host_control_root: Path) -> None:
    if not Path("/.dockerenv").exists():
        raise PreflightError("A-prime preflight must run inside Docker")
    if not Path("/var/run/docker.sock").is_socket():
        raise PreflightError("Docker socket is not mounted")
    if not Path("/usr/local/bin/docker").exists():
        raise PreflightError("Docker client is not mounted")
    if not host_control_root.is_dir():
        raise PreflightError("one-off read-only host-control bind is absent")


def path_matches(path: str, contracts: Sequence[str]) -> bool:
    return any(path == item or path.startswith(item) for item in contracts)


def classify_dirty_rows(
    rows: Sequence[str], policy: dict[str, Any]
) -> dict[str, Any]:
    classified: list[dict[str, str]] = []
    counts: dict[str, int] = {}
    for line in rows:
        if not line:
            continue
        code = line[:2]
        path = line[3:]
        if path_matches(path, policy["known_shared_t1_code_paths"]):
            category = "shared_T1_code_diff"
        elif path_matches(path, policy["allowed_user_artifact_prefixes"]):
            category = "preexisting_user_run_artifact"
        elif path_matches(path, policy["allowed_current_preflight_paths"]):
            category = "current_preflight_implementation_or_output"
        elif path_matches(path, policy["concurrent_aprime_work_prefixes"]):
            category = "concurrent_aprime_worktree_change"
        else:
            category = "unclassified_dirty_path"
        classified.append(
            {"porcelain_code": code, "path": path, "category": category}
        )
        counts[category] = counts.get(category, 0) + 1
    return {"rows": classified, "counts": counts}


def check_git_prereg(config: dict[str, Any]) -> dict[str, Any]:
    lock = config["git"]
    branch = git("branch", "--show-current").stdout.strip()
    head = git("rev-parse", "HEAD").stdout.strip()
    required = lock["required_ancestor_commit"]
    commit_probe = git("cat-file", "-t", required, check=False)
    commit_exists = (
        commit_probe.returncode == 0
        and commit_probe.stdout.strip() == "commit"
    )
    ancestor_probe = git(
        "merge-base", "--is-ancestor", required, head, check=False
    )
    ancestor = commit_exists and ancestor_probe.returncode == 0
    documents: list[dict[str, Any]] = []
    documents_ok = True
    for spec in lock["locked_documents"]:
        path = REPO / spec["path"]
        exists = path.is_file()
        observed_sha = sha256_file(path) if exists else None
        observed_bytes = path.stat().st_size if exists else None
        tracked_probe = git("ls-files", "--error-unmatch", spec["path"], check=False)
        blob_probe = git_bytes(
            "show", f"{required}:{spec['path']}", check=False
        )
        committed_sha = (
            sha256_bytes(blob_probe.stdout)
            if blob_probe.returncode == 0
            else None
        )
        size_ok = "bytes" not in spec or observed_bytes == int(spec["bytes"])
        matches = (
            exists
            and tracked_probe.returncode == 0
            and blob_probe.returncode == 0
            and observed_sha == spec["sha256"]
            and committed_sha == spec["sha256"]
            and size_ok
        )
        documents.append(
            {
                "role": spec["role"],
                "path": spec["path"],
                "expected_sha256": spec["sha256"],
                "working_tree_sha256": observed_sha,
                "required_commit_blob_sha256": committed_sha,
                "bytes": observed_bytes,
                "expected_bytes": spec.get("bytes"),
                "tracked_in_current_index": tracked_probe.returncode == 0,
                "present_in_required_commit": blob_probe.returncode == 0,
                "matches_lock": matches,
            }
        )
        documents_ok = documents_ok and matches

    dirty_lines = git(
        "status", "--porcelain=v1", "--untracked-files=normal"
    ).stdout.splitlines()
    dirty = classify_dirty_rows(dirty_lines, lock["dirty_state_policy"])
    ok = (
        branch == lock["expected_branch"]
        and ancestor
        and documents_ok
    )
    evidence = {
        "repository": str(REPO),
        "branch": branch,
        "expected_branch": lock["expected_branch"],
        "head": head,
        "required_preregistration_commit": required,
        "required_commit_exists": commit_exists,
        "required_commit_is_ancestor_of_head": ancestor,
        "locked_documents": documents,
        "dirty_worktree": {
            **dirty,
            "policy": lock["dirty_state_policy"],
            "affects_this_measurement_receipt": False,
            "training_launch_gate_evaluated": False,
            "training_launch_authorized": False,
            "note": (
                "Existing run evidence and concurrent T1 code changes are "
                "classified only. A fresh committed-HEAD launch gate is "
                "required before any training process."
            ),
        },
    }
    return status("git_branch_commit_and_prereg", ok, evidence)


def docker_image_inspect(reference: str) -> dict[str, Any]:
    payload = json.loads(
        run(["docker", "image", "inspect", reference]).stdout
    )
    if not isinstance(payload, list) or len(payload) != 1:
        raise PreflightError(f"unexpected docker inspect output: {reference}")
    item = payload[0]
    return {
        "reference": reference,
        "image_id": item["Id"],
        "repo_tags": item.get("RepoTags") or [],
        "repo_digests": item.get("RepoDigests") or [],
        "created": item.get("Created"),
    }


def check_docker_images(config: dict[str, Any]) -> dict[str, Any]:
    locks = config["docker_images"]
    inspected = {
        role: docker_image_inspect(spec["reference"])
        for role, spec in locks.items()
    }

    import gsplat
    import torch

    gs_versions = {
        "python": platform.python_version(),
        "torch": torch.__version__,
        "torch_cuda_build": torch.version.cuda,
        "gsplat": gsplat.__version__,
    }
    roofer_probe = run(
        [
            "docker",
            "run",
            "--rm",
            "--pull=never",
            "--network",
            "none",
            locks["roofer"]["reference"],
            "--version",
        ]
    )
    roofer_version = (roofer_probe.stdout + roofer_probe.stderr).strip()
    tools_probe = run(
        [
            "docker",
            "run",
            "--rm",
            "--pull=never",
            "--network",
            "none",
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
    tools_versions = json.loads(tools_probe.stdout)
    for key, command in {
        "pdal": "pdal --version",
        "gdal": "gdalinfo --version",
        "val3dity": "val3dity --version",
        "citygml_tools": "citygml-tools --version",
    }.items():
        probe = run(
            [
                "docker",
                "run",
                "--rm",
                "--pull=never",
                "--network",
                "none",
                "--entrypoint",
                "/bin/bash",
                locks["tools"]["reference"],
                "-lc",
                command,
            ]
        )
        tools_versions[key] = (probe.stdout + probe.stderr).strip()

    checks = [
        inspected[role]["image_id"] == spec["image_id"]
        for role, spec in locks.items()
    ]
    checks.append(
        locks["roofer"]["required_repo_digest"]
        in inspected["roofer"]["repo_digests"]
    )
    checks.append(locks["roofer"]["version_contains"] in roofer_version)
    checks.extend(
        gs_versions[key] == expected
        for key, expected in locks["gs"]["versions"].items()
    )
    for key in ("python", "numpy", "laspy", "pyproj"):
        checks.append(
            tools_versions[key] == locks["tools"]["versions"][key]
        )
    for observed, expected in (
        ("pdal", "pdal_contains"),
        ("gdal", "gdal_contains"),
        ("val3dity", "val3dity_contains"),
        ("citygml_tools", "citygml_tools_contains"),
    ):
        checks.append(
            locks["tools"]["versions"][expected]
            in tools_versions[observed]
        )
    docker_server = json.loads(
        run(["docker", "version", "--format", "{{json .Server}}"]).stdout
    )
    return status(
        "docker_image_ids_and_versions",
        all(checks),
        {
            "docker_server": docker_server,
            "images": inspected,
            "versions": {
                "gs": gs_versions,
                "roofer": roofer_version,
                "tools": tools_versions,
            },
        },
    )


def parse_nvidia_csv(output: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in output.splitlines():
        if not line.strip():
            continue
        parts = [part.strip() for part in line.split(",")]
        if len(parts) != 5:
            raise PreflightError(f"unexpected nvidia-smi row: {line}")
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


def check_cuda(config: dict[str, Any]) -> dict[str, Any]:
    import torch

    lock = config["cuda_smoke"]
    query = run(
        [
            "nvidia-smi",
            "--query-gpu=index,uuid,name,driver_version,memory.total",
            "--format=csv,noheader,nounits",
        ]
    )
    rows = parse_nvidia_csv(query.stdout)
    available = torch.cuda.is_available()
    if not available:
        return status(
            "nvidia_smi_and_cuda_matmul",
            False,
            {"nvidia_smi": rows, "torch_cuda_available": False},
        )
    size = int(lock["matrix_size"])
    left = torch.ones((size, size), dtype=torch.float32, device="cuda")
    right = torch.ones((size, size), dtype=torch.float32, device="cuda")
    product = left @ right
    torch.cuda.synchronize()
    finite = bool(torch.isfinite(product).all().item())
    first_value = float(product[0, 0].item())
    props = torch.cuda.get_device_properties(0)
    ok = (
        bool(rows)
        and finite == bool(lock["required_finite"])
        and math.isclose(
            first_value,
            float(lock["expected_first_value"]),
            rel_tol=0.0,
            abs_tol=float(lock["absolute_tolerance"]),
        )
    )
    return status(
        "nvidia_smi_and_cuda_matmul",
        ok,
        {
            "nvidia_smi": rows,
            "torch_cuda_available": available,
            "torch_cuda_build": torch.version.cuda,
            "cuda_visible_devices": os.environ.get("CUDA_VISIBLE_DEVICES"),
            "torch_logical_device": 0,
            "torch_device_name": props.name,
            "matrix_size": size,
            "operation": "float32 ones matrix multiplication on CUDA",
            "finite": finite,
            "first_value": first_value,
            "expected_first_value": float(lock["expected_first_value"]),
        },
    )


def image_inventory_aggregate(
    root: Path,
) -> tuple[str, int, int]:
    files = sorted(
        (path for path in root.iterdir() if path.is_file()),
        key=lambda path: path.relative_to(REPO).as_posix().encode("utf-8"),
    )
    aggregate = hashlib.sha256()
    total_bytes = 0
    for path in files:
        digest = sha256_file(path)
        total_bytes += path.stat().st_size
        logical = path.relative_to(REPO).as_posix()
        aggregate.update(f"{digest}  {logical}\n".encode("utf-8"))
    return aggregate.hexdigest(), len(files), total_bytes


def manifest_file_hashes(pose: dict[str, Any]) -> dict[str, str]:
    return {
        row["path"]: row["sha256"]
        for row in pose["immutable_inputs_after"]["files"]
    }


def check_inputs(config: dict[str, Any]) -> dict[str, Any]:
    source_payloads: dict[str, dict[str, Any]] = {}
    source_rows: list[dict[str, Any]] = []
    sources_ok = True
    for role, spec in config["locked_sources"].items():
        path = REPO / spec["path"]
        observed = sha256_file(path) if path.is_file() else None
        matches = observed == spec["sha256"]
        source_rows.append(
            {
                "role": role,
                "path": spec["path"],
                "expected_sha256": spec["sha256"],
                "observed_sha256": observed,
                "matches_lock": matches,
            }
        )
        sources_ok = sources_ok and matches
        if path.is_file():
            source_payloads[role] = load_json(path)

    required_roles = {
        "aprime_prereg_config",
        "pose_adoption_manifest",
        "gate_a_v2_manifest",
        "fusion_w1_preprocess_config",
    }
    if set(source_payloads) != required_roles:
        missing = sorted(required_roles - set(source_payloads))
        raise PreflightError(f"missing locked source payloads: {missing}")
    prereg = source_payloads["aprime_prereg_config"]
    pose = source_payloads["pose_adoption_manifest"]
    gate = source_payloads["gate_a_v2_manifest"]
    preprocess = source_payloads["fusion_w1_preprocess_config"]
    pose_input_hashes = manifest_file_hashes(pose)
    preprocess_hashes = preprocess["input_sha256"]

    input_rows: list[dict[str, Any]] = []
    files_ok = True
    for spec in config["canonical_inputs"]["files"]:
        path = REPO / spec["path"]
        exists = path.is_file()
        observed_bytes = path.stat().st_size if exists else None
        observed_sha = sha256_file(path) if exists else None
        expected_sources: dict[str, Any] = {}
        if spec["path"] in preprocess_hashes:
            expected_sources["fusion_w1_preprocess_config"] = (
                preprocess_hashes[spec["path"]]
            )
        if spec["path"] in pose_input_hashes:
            expected_sources["pose_adoption_immutable_inputs"] = (
                pose_input_hashes[spec["path"]]
            )
        if spec["role"].startswith("corrected_"):
            basename = path.name
            expected_sources["pose_adoption_derived_sha256"] = pose[
                "derived_sha256"
            ].get(basename)
        source_values_match = (
            bool(expected_sources)
            and all(value == spec["sha256"] for value in expected_sources.values())
        )
        matches = (
            exists
            and observed_bytes == int(spec["bytes"])
            and observed_sha == spec["sha256"]
            and source_values_match
        )
        input_rows.append(
            {
                "role": spec["role"],
                "path": spec["path"],
                "bytes": observed_bytes,
                "expected_bytes": int(spec["bytes"]),
                "sha256": observed_sha,
                "expected_sha256": spec["sha256"],
                "locked_source_values": expected_sources,
                "locked_sources_match_expected": source_values_match,
                "matches_lock": matches,
            }
        )
        files_ok = files_ok and matches

    image_lock = config["canonical_inputs"]["training_images"]
    image_root = REPO / image_lock["path"]
    aggregate, count, total_bytes = image_inventory_aggregate(image_root)
    pose_image_lock = pose["immutable_inputs_after"]["training_image_set"]
    image_source_matches = all(
        (
            pose_image_lock["path"] == image_lock["path"],
            int(pose_image_lock["file_count"]) == int(image_lock["file_count"]),
            int(pose_image_lock["total_bytes"]) == int(image_lock["total_bytes"]),
            pose_image_lock["sha256sum_stream_aggregate"]
            == image_lock["sha256sum_stream_aggregate"],
        )
    )
    image_ok = (
        count == int(image_lock["file_count"])
        and total_bytes == int(image_lock["total_bytes"])
        and aggregate == image_lock["sha256sum_stream_aggregate"]
        and image_source_matches
    )

    prereg_cross_checks = {
        "pose_manifest_sha256": (
            prereg["inputs"]["pose_adoption_manifest_sha256"]
            == config["locked_sources"]["pose_adoption_manifest"]["sha256"]
        ),
        "gate_manifest_sha256": (
            prereg["inputs"]["gate_a_v2_manifest_sha256"]
            == config["locked_sources"]["gate_a_v2_manifest"]["sha256"]
        ),
        "corrected_images_sha256": (
            prereg["inputs"]["corrected_images_sha256"]
            == next(
                item["sha256"]
                for item in config["canonical_inputs"]["files"]
                if item["role"] == "corrected_images"
            )
        ),
        "transform_application_count": (
            int(prereg["inputs"]["transform_application_count"]) == 1
        ),
        "gate_required_status": (
            prereg["inputs"]["gate_a_v2_required_status"] == "PASS"
        ),
    }
    ok = (
        sources_ok
        and files_ok
        and image_ok
        and all(prereg_cross_checks.values())
    )
    return status(
        "immutable_inputs_and_image_inventory",
        ok,
        {
            "locked_sources": source_rows,
            "files": input_rows,
            "training_images": {
                "path": image_lock["path"],
                "file_count": count,
                "expected_file_count": int(image_lock["file_count"]),
                "total_bytes": total_bytes,
                "expected_total_bytes": int(image_lock["total_bytes"]),
                "sha256sum_stream_aggregate": aggregate,
                "expected_sha256sum_stream_aggregate": image_lock[
                    "sha256sum_stream_aggregate"
                ],
                "algorithm": image_lock["algorithm"],
                "locked_pose_manifest_values_match": image_source_matches,
                "matches_lock": image_ok,
            },
            "aprime_prereg_cross_checks": prereg_cross_checks,
        },
    )


def check_mount_freshness(
    config: dict[str, Any], host_control_root: Path
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    ok = True
    for spec in config["mount_freshness"]["documents"]:
        container_path = REPO / spec["path"]
        host_path = host_control_root / spec["path"]
        container_exists = container_path.is_file()
        host_exists = host_path.is_file()
        if container_exists and host_exists:
            container_stat = container_path.stat()
            host_stat = host_path.stat()
            container_sha = sha256_file(container_path)
            host_sha = sha256_file(host_path)
            matches = (
                container_sha == spec["sha256"]
                and host_sha == spec["sha256"]
                and container_stat.st_size == host_stat.st_size
                and container_stat.st_mtime_ns == host_stat.st_mtime_ns
            )
            row = {
                "role": spec["role"],
                "path": spec["path"],
                "expected_sha256": spec["sha256"],
                "container_sha256": container_sha,
                "host_control_sha256": host_sha,
                "container_bytes": container_stat.st_size,
                "host_control_bytes": host_stat.st_size,
                "container_mtime_ns": container_stat.st_mtime_ns,
                "host_control_mtime_ns": host_stat.st_mtime_ns,
                "host_container_hash_size_mtime_match": matches,
            }
        else:
            matches = False
            row = {
                "role": spec["role"],
                "path": spec["path"],
                "expected_sha256": spec["sha256"],
                "container_exists": container_exists,
                "host_control_exists": host_exists,
                "host_container_hash_size_mtime_match": False,
            }
        rows.append(row)
        ok = ok and matches
    return status(
        "one_off_bind_mount_freshness",
        ok,
        {
            "container_repo_root": str(REPO),
            "host_control_root": str(host_control_root),
            "mount_mode": "same_host_repo_second_read_only_bind",
            "documents": rows,
        },
    )


def check_pose_gate_appendix(config: dict[str, Any]) -> dict[str, Any]:
    pose_spec = config["locked_sources"]["pose_adoption_manifest"]
    gate_spec = config["locked_sources"]["gate_a_v2_manifest"]
    pose = load_json(REPO / pose_spec["path"])
    gate = load_json(REPO / gate_spec["path"])
    lock = config["appendix_contract"]
    observed = {
        "pose_manifest_schema": pose.get("schema"),
        "pose_status": pose.get("status"),
        "pose_image_count": pose.get("image_count"),
        "transform_application_count": pose.get("transform_application_count"),
        "pose_binding_required_transform_application_count": pose.get(
            "arm_pose_contract", {}
        ).get("pose_binding", {}).get("required_transform_application_count"),
        "zeta_application_count_during_pose_adoption": pose.get(
            "coordinate_datum", {}
        ).get("zeta_application_count_during_r1"),
        "gate_manifest_schema": gate.get("schema"),
        "gate_status": gate.get("status"),
        "gate_version": gate.get("gate_a_version"),
        "gate_pose_application_count": gate.get("r1_pose_consumer", {}).get(
            "transform_application_count_in_r1"
        ),
        "additional_transform_applied_by_gate": gate.get(
            "r1_pose_consumer", {}
        ).get("additional_transform_applied_by_r2"),
        "als_transform_applied_by_gate": gate.get(
            "r1_pose_consumer", {}
        ).get("als_transform_applied_by_r2"),
    }
    expected = {
        **lock,
        "pose_binding_required_transform_application_count": 1,
        "zeta_application_count_during_pose_adoption": 0,
        "gate_pose_application_count": 1,
        "als_transform_applied_by_gate": False,
    }
    ok = all(observed.get(key) == value for key, value in expected.items())
    return status(
        "pose_application_and_gate_a_v2_appendix",
        ok,
        {"observed": observed, "expected": expected},
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument(
        "--host-control-root",
        type=Path,
        default=Path("/host-control/JointBuildGS"),
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config_path = args.config.resolve()
    config = load_json(config_path)
    validate_config(config)
    require_runtime(args.host_control_root)

    pin_functions: list[tuple[str, Callable[[], dict[str, Any]]]] = [
        ("git_branch_commit_and_prereg", lambda: check_git_prereg(config)),
        ("docker_image_ids_and_versions", lambda: check_docker_images(config)),
        ("nvidia_smi_and_cuda_matmul", lambda: check_cuda(config)),
        (
            "immutable_inputs_and_image_inventory",
            lambda: check_inputs(config),
        ),
        (
            "one_off_bind_mount_freshness",
            lambda: check_mount_freshness(config, args.host_control_root),
        ),
    ]
    pins = [measured(name, function) for name, function in pin_functions]
    appendix = measured(
        "pose_application_and_gate_a_v2_appendix",
        lambda: check_pose_gate_appendix(config),
    )
    passed = all(item["status"] == "passed" for item in pins) and (
        appendix["status"] == "passed"
    )
    receipt_path = REPO / config["outputs"]["receipt"]
    status_path = REPO / config["outputs"]["status"]
    receipt = {
        "schema": "jointbuildgs.fusion_w1_aprime.five_pin_receipt.v1",
        "task_id": config["task_id"],
        "run_id": config["run_id"],
        "created_utc": utc_now(),
        "created_kst": kst_now(),
        "purpose": config["purpose"],
        "status": "PASSED" if passed else "BLOCKED",
        "verdict": None,
        "config": {
            "path": config_path.relative_to(REPO).as_posix(),
            "sha256": sha256_file(config_path),
        },
        "implementation": {
            "path": Path(__file__).resolve().relative_to(REPO).as_posix(),
            "sha256": sha256_file(Path(__file__).resolve()),
        },
        "five_pins": {
            "passed_count": sum(item["status"] == "passed" for item in pins),
            "total_count": 5,
            "items": pins,
        },
        "appendix": appendix,
        "launch_contract": {
            "training_launch_gate_evaluated": False,
            "training_launch_authorized_by_this_receipt": False,
            "reason": (
                "This receipt measures the five pins while shared T1 code "
                "may be changing. T1/T2/T3 and a fresh committed-HEAD start "
                "gate remain mandatory."
            ),
        },
        "execution_counters": {
            "training_runs_started": 0,
            "readout_runs_started": 0,
            "roofer_runs_started": 0,
            "scoring_runs_started": 0,
        },
    }
    atomic_write_json(receipt_path, receipt)
    receipt_sha = sha256_file(receipt_path)
    status_receipt = {
        "schema": "jointbuildgs.fusion_w1_aprime.five_pin_status.v1",
        "task_id": config["task_id"],
        "run_id": config["run_id"],
        "created_utc": utc_now(),
        "created_kst": kst_now(),
        "status": receipt["status"],
        "verdict": None,
        "receipt": {
            "path": config["outputs"]["receipt"],
            "sha256": receipt_sha,
        },
        "passed_pin_count": receipt["five_pins"]["passed_count"],
        "total_pin_count": 5,
        "failed_pins": [
            item["name"] for item in pins if item["status"] != "passed"
        ],
        "appendix_status": appendix["status"],
        "training_launch_authorized": False,
        "actual_training_started": False,
        "actual_readout_started": False,
    }
    atomic_write_json(status_path, status_receipt)
    print(
        json.dumps(
            {
                "status": receipt["status"],
                "passed_pin_count": receipt["five_pins"]["passed_count"],
                "total_pin_count": 5,
                "appendix_status": appendix["status"],
                "receipt": str(receipt_path.relative_to(REPO)),
                "status_receipt": str(status_path.relative_to(REPO)),
                "verdict": None,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0 if passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
