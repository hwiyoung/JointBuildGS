#!/usr/bin/env python3
"""R0 five-pin and resume-specific preflight for FUS-W1 Gate A v2.

This program is measurement-only. It launches no Gate A residual measurement,
pose publication, seed preparation, learning, readout, Roofer, or scoring.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import struct
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence
from zoneinfo import ZoneInfo


REPO = Path(__file__).resolve().parents[4]
DEFAULT_CONFIG = (
    REPO
    / "phases/p2-gsjso/configs/fusion_w1/fusion_w1_resume_r0_v2_20260725.json"
)
HOST_CONTROL = Path("/host-control/JointBuildGS")
PASS_LIKE = {"passed", "passed_with_caveat"}


class ResumeR0Error(RuntimeError):
    pass


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def now_kst() -> str:
    return datetime.now(ZoneInfo("Asia/Seoul")).isoformat()


class EventJournal:
    """Append-and-fsync journal compatible with the locked base EventLog."""

    def __init__(self, path: Path) -> None:
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        self._handle = path.open("x", encoding="utf-8")
        self.events: list[dict[str, Any]] = []

    def record(self, payload: Mapping[str, Any]) -> None:
        row = dict(payload)
        self.events.append(row)
        self._handle.write(
            json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n"
        )
        self._handle.flush()
        os.fsync(self._handle.fileno())

    def write(self, event: str, **fields: Any) -> None:
        self.record({"at": now_utc(), "event": event, **fields})

    def close(self) -> None:
        if not self._handle.closed:
            self._handle.close()


def sha256_file(path: Path, chunk_size: int = 8 * 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ResumeR0Error(f"JSON root is not an object: {path}")
    return payload


def run(
    args: Sequence[str],
    *,
    check: bool = True,
    timeout: int = 300,
) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        list(args),
        cwd=REPO,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=timeout,
    )
    if check and completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise ResumeR0Error(
            f"command failed rc={completed.returncode}: {' '.join(args)}: {detail}"
        )
    return completed


def git(*args: str, check: bool = True) -> str:
    return run(
        ["git", "-c", f"safe.directory={REPO}", "-C", str(REPO), *args],
        check=check,
    ).stdout.strip()


def atomic_json(path: Path, payload: Mapping[str, Any]) -> None:
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


def exclusive_json(path: Path, payload: Mapping[str, Any]) -> None:
    """Create a durable exact-once claim without a check-then-create race."""

    path.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    descriptor = os.open(path, flags, 0o644)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            descriptor = -1
            handle.write(
                json.dumps(
                    payload, ensure_ascii=False, indent=2, sort_keys=True
                )
                + "\n"
            )
            handle.flush()
            os.fsync(handle.fileno())
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def import_base_module(path: Path) -> Any:
    spec = importlib.util.spec_from_file_location("fusion_w1_preflight_base", path)
    if spec is None or spec.loader is None:
        raise ResumeR0Error(f"cannot import base preflight: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def result(name: str, ok: bool, evidence: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "name": name,
        "status": "passed" if ok else "failed",
        "evidence": dict(evidence),
    }


def guarded(
    name: str,
    function: Callable[[], dict[str, Any]],
    journal: EventJournal,
) -> dict[str, Any]:
    journal.write("check_started", check=name)
    try:
        value = function()
        if value.get("name") != name:
            raise ResumeR0Error(
                f"wrong check name: expected {name}, got {value.get('name')}"
            )
    except Exception as exc:
        value = {
            "name": name,
            "status": "failed",
            "evidence": {},
            "error_type": type(exc).__name__,
            "error": str(exc),
        }
    journal.write(
        "check_finished",
        check=name,
        status=value["status"],
        error=value.get("error"),
    )
    return value


def verify_config(config: Mapping[str, Any], config_path: Path) -> None:
    if config.get("schema") != "jointbuildgs.fusion_w1.resume_r0_v2.config.v1":
        raise ResumeR0Error("unexpected config schema")
    if config.get("branch") != "exp/fusion-w1":
        raise ResumeR0Error("branch lock drift")
    if config_path.resolve() != DEFAULT_CONFIG.resolve():
        raise ResumeR0Error("only the committed default config may run")
    if not Path("/.dockerenv").exists():
        raise ResumeR0Error("R0 must run in Docker")
    if not Path("/var/run/docker.sock").is_socket():
        raise ResumeR0Error("Docker socket is unavailable")
    if not HOST_CONTROL.is_dir():
        raise ResumeR0Error("read-only host-control mount is unavailable")


def check_git_and_documents(
    config: Mapping[str, Any],
    generated_paths: Sequence[Path],
) -> dict[str, Any]:
    branch = git("branch", "--show-current")
    head = git("rev-parse", "HEAD")
    porcelain = git(
        "status", "--porcelain=v1", "--untracked-files=all"
    ).splitlines()
    allowed_generated = {
        path.relative_to(REPO).as_posix() for path in generated_paths
    }

    def status_path(row: str) -> str:
        value = row[3:] if len(row) > 3 else ""
        if " -> " in value:
            value = value.split(" -> ", maxsplit=1)[1]
        return value.strip('"')

    unexpected_porcelain = [
        row for row in porcelain if status_path(row) not in allowed_generated
    ]
    ancestors: dict[str, Any] = {}
    ancestor_ok = True
    for role, commit in config["required_ancestors"].items():
        probe = run(
            [
                "git",
                "-c",
                f"safe.directory={REPO}",
                "-C",
                str(REPO),
                "merge-base",
                "--is-ancestor",
                commit,
                head,
            ],
            check=False,
        )
        ok = probe.returncode == 0
        ancestors[role] = {"commit": commit, "ancestor_of_head": ok}
        ancestor_ok = ancestor_ok and ok

    implementation_rows = []
    implementation_ok = True
    for relative in config["implementation_files"]:
        path = REPO / relative
        working = sha256_file(path) if path.is_file() else None
        blob = run(
            [
                "git",
                "-c",
                f"safe.directory={REPO}",
                "-C",
                str(REPO),
                "show",
                f"{head}:{relative}",
            ],
            check=False,
        )
        committed = (
            hashlib.sha256(blob.stdout.encode("utf-8")).hexdigest()
            if blob.returncode == 0
            else None
        )
        matches = working is not None and working == committed
        implementation_rows.append(
            {
                "path": relative,
                "working_sha256": working,
                "head_blob_sha256": committed,
                "matches": matches,
            }
        )
        implementation_ok = implementation_ok and matches

    document_rows = []
    documents_ok = True
    for item in config["documents"]:
        source = REPO / item["path"]
        copy = REPO / item["run_copy"]
        source_hash = sha256_file(source) if source.is_file() else None
        copy_hash = sha256_file(copy) if copy.is_file() else None
        source_tracked = bool(git("ls-files", "--", item["path"]))
        copy_tracked = bool(git("ls-files", "--", item["run_copy"]))
        matches = (
            source_hash == item["sha256"]
            and copy_hash == item["sha256"]
            and source_tracked
            and copy_tracked
        )
        document_rows.append(
            {
                **item,
                "source_sha256": source_hash,
                "run_copy_sha256": copy_hash,
                "source_tracked": source_tracked,
                "run_copy_tracked": copy_tracked,
                "matches": matches,
            }
        )
        documents_ok = documents_ok and matches

    ok = (
        branch == config["branch"]
        and ancestor_ok
        and not unexpected_porcelain
        and implementation_ok
        and documents_ok
    )
    return result(
        "git_commit_branch_and_document_lock",
        ok,
        {
            "branch": branch,
            "expected_branch": config["branch"],
            "head": head,
            "required_ancestors": ancestors,
            "worktree_porcelain": porcelain,
            "allowed_generated_paths": sorted(allowed_generated),
            "unexpected_worktree_porcelain": unexpected_porcelain,
            "worktree_clean_before_r0_outputs": not unexpected_porcelain,
            "implementation_files": implementation_rows,
            "documents": document_rows,
        },
    )


def collect_counter_observations(
    value: Any,
    *,
    source: str,
    counter_names: set[str],
    rows: list[dict[str, Any]],
    pointer: str = "$",
) -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            child = f"{pointer}.{key}"
            if key in counter_names:
                rows.append(
                    {"source": source, "pointer": child, "value": item}
                )
            collect_counter_observations(
                item,
                source=source,
                counter_names=counter_names,
                rows=rows,
                pointer=child,
            )
    elif isinstance(value, list):
        for index, item in enumerate(value):
            collect_counter_observations(
                item,
                source=source,
                counter_names=counter_names,
                rows=rows,
                pointer=f"{pointer}[{index}]",
            )


def scan_runtime_counters(
    config: Mapping[str, Any],
) -> tuple[dict[str, int | None], list[dict[str, Any]], list[dict[str, Any]]]:
    source = config["counter_source"]
    runtime = config["runtime_zero_evidence"]
    names = set(source["required_zero"])
    root = REPO / runtime["run_root"]
    suffixes = set(runtime["counter_file_suffixes"])
    observations: list[dict[str, Any]] = []
    parse_failures: list[dict[str, Any]] = []
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        if path.suffix not in suffixes:
            continue
        relative = path.relative_to(REPO).as_posix()
        try:
            if path.suffix == ".json":
                payloads = [json.loads(path.read_text(encoding="utf-8"))]
            else:
                payloads = [
                    json.loads(line)
                    for line in path.read_text(encoding="utf-8").splitlines()
                    if line.strip()
                ]
            for index, payload in enumerate(payloads):
                collect_counter_observations(
                    payload,
                    source=(
                        relative
                        if len(payloads) == 1
                        else f"{relative}#line={index + 1}"
                    ),
                    counter_names=names,
                    rows=observations,
                )
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            parse_failures.append(
                {
                    "source": relative,
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                }
            )

    values: dict[str, int | None] = {}
    for name in sorted(names):
        found = [
            row["value"]
            for row in observations
            if row["pointer"].endswith(f".{name}")
        ]
        valid = [
            int(value)
            for value in found
            if isinstance(value, int) and not isinstance(value, bool)
        ]
        if not found or len(valid) != len(found):
            values[name] = None
        elif all(value == 0 for value in valid):
            values[name] = 0
        else:
            values[name] = next(value for value in valid if value != 0)
    return values, observations, parse_failures


def check_coreg_and_counters(config: Mapping[str, Any]) -> dict[str, Any]:
    evidence_rows = []
    evidence_ok = True
    for item in config["coreg_lock2_evidence"]:
        path = REPO / item["path"]
        observed = sha256_file(path) if path.is_file() else None
        matches = observed == item["sha256"]
        evidence_rows.append(
            {**item, "observed_sha256": observed, "matches": matches}
        )
        evidence_ok = evidence_ok and matches

    publication_spec = next(
        item
        for item in config["coreg_lock2_evidence"]
        if item["path"].endswith("publication_manifest.json")
    )
    publication_manifest = load_json(REPO / publication_spec["path"])
    publication_rows = []
    publication_ok = True
    for relative, expected in sorted(
        publication_manifest.get("artifacts", {}).items()
    ):
        path = REPO / relative
        observed = sha256_file(path) if path.is_file() else None
        matches = observed == expected
        publication_rows.append(
            {
                "path": relative,
                "expected_sha256": expected,
                "observed_sha256": observed,
                "matches": matches,
            }
        )
        publication_ok = publication_ok and matches
    publication_ok = publication_ok and bool(publication_rows)

    global_selection = load_json(
        REPO / config["coreg_lock2_evidence"][0]["path"]
    )
    block_selection = load_json(
        REPO / config["coreg_lock2_evidence"][1]["path"]
    )
    dispositions_ok = (
        global_selection.get("choice") == "none"
        and global_selection.get("status") == "BLOCK_REQUIRED"
        and block_selection.get("choice") == "none"
        and block_selection.get("status") == "BLOCKED"
    )

    source = config["counter_source"]
    counter_path = REPO / source["path"]
    counter_hash = sha256_file(counter_path) if counter_path.is_file() else None
    counter_manifest = load_json(counter_path)
    counters = counter_manifest.get("counters", {})
    locked_counter_values = {
        key: counters.get(key) for key in source["required_zero"]
    }
    locked_counters_ok = (
        counter_hash == source["sha256"]
        and all(value == 0 for value in locked_counter_values.values())
    )
    runtime_counter_values, counter_observations, parse_failures = (
        scan_runtime_counters(config)
    )
    observed_counter_names = {
        row["pointer"].rsplit(".", maxsplit=1)[-1]
        for row in counter_observations
    }
    runtime_counters_ok = (
        observed_counter_names == set(source["required_zero"])
        and all(row["value"] == 0 for row in counter_observations)
        and all(value == 0 for value in runtime_counter_values.values())
    )
    forbidden_rows = [
        {
            "path": relative,
            "exists": (REPO / relative).exists(),
        }
        for relative in config["runtime_zero_evidence"][
            "forbidden_downstream_paths"
        ]
    ]
    downstream_absent = not any(row["exists"] for row in forbidden_rows)
    counters_ok = (
        locked_counters_ok
        and runtime_counters_ok
        and not parse_failures
        and downstream_absent
    )

    return result(
        "coreg_lock2_evidence_and_zero_counters",
        evidence_ok
        and publication_ok
        and dispositions_ok
        and counters_ok,
        {
            "coreg_evidence": evidence_rows,
            "publication_inventory": publication_rows,
            "publication_inventory_complete": publication_ok,
            "global_disposition": {
                "choice": global_selection.get("choice"),
                "status": global_selection.get("status"),
            },
            "block_disposition": {
                "choice": block_selection.get("choice"),
                "status": block_selection.get("status"),
            },
            "counter_source": {
                **source,
                "observed_sha256": counter_hash,
            },
            "locked_counter_values": locked_counter_values,
            "runtime_counter_values": runtime_counter_values,
            "runtime_counter_observations": counter_observations,
            "runtime_counter_parse_failures": parse_failures,
            "forbidden_downstream_paths": forbidden_rows,
        },
    )


def check_r0_source_pose(
    config: Mapping[str, Any], base_config: Mapping[str, Any]
) -> dict[str, Any]:
    image_spec = next(
        item
        for item in base_config["canonical_inputs"]["files"]
        if item["role"] == "colmap_image_poses"
    )
    path = REPO / image_spec["path"]
    observed = sha256_file(path)
    expected = config["pose_transition"]["source_images_sha256"]
    with path.open("rb") as handle:
        header = handle.read(8)
    image_count = struct.unpack("<Q", header)[0] if len(header) == 8 else None
    expected_count = int(config["pose_transition"]["source_image_count"])
    pose_modified = observed != expected
    return result(
        "r0_source_pose_before_authorized_r1",
        (
            observed == expected == image_spec["sha256"]
            and image_count == expected_count
        ),
        {
            "path": image_spec["path"],
            "source_pose_sha256": observed,
            "expected_source_pose_sha256": expected,
            "image_count_observed": image_count,
            "image_count_expected": expected_count,
            "state": config["pose_transition"]["r0_expected_state"],
            "authorized_future_difference": config["pose_transition"][
                "r1_authorized_difference"
            ],
            "source_pose_modified": pose_modified,
        },
    )


def check_resume_mount_freshness(
    config: Mapping[str, Any],
    base: Any,
    base_config: Mapping[str, Any],
    git_check: Mapping[str, Any],
) -> dict[str, Any]:
    document_rows = git_check.get("evidence", {}).get("documents", [])
    original = next(
        (
            row
            for row in document_rows
            if row.get("role") == "original_dispatch"
        ),
        {},
    )
    dispatch_match = bool(original.get("matches"))
    base_result = base.check_mount_freshness(
        base_config,
        {
            "evidence": {
                "dispatch": {
                    "working_and_committed_match": dispatch_match
                }
            }
        },
        HOST_CONTROL,
    )

    rows = []
    rows_ok = True
    seen: set[str] = set()
    for item in config["documents"]:
        for field in ("path", "run_copy"):
            relative = item[field]
            if relative in seen:
                continue
            seen.add(relative)
            container_path = REPO / relative
            host_path = HOST_CONTROL / relative
            exists = container_path.is_file() and host_path.is_file()
            if exists:
                container_stat = container_path.stat()
                host_stat = host_path.stat()
                container_hash = sha256_file(container_path)
                host_hash = sha256_file(host_path)
                matches = (
                    container_hash == item["sha256"]
                    and host_hash == item["sha256"]
                    and container_stat.st_size == host_stat.st_size
                    and container_stat.st_mtime_ns == host_stat.st_mtime_ns
                )
            else:
                container_hash = None
                host_hash = None
                matches = False
            rows.append(
                {
                    "role": item["role"],
                    "path": relative,
                    "container_exists": container_path.is_file(),
                    "host_control_exists": host_path.is_file(),
                    "container_sha256": container_hash,
                    "host_control_sha256": host_hash,
                    "expected_sha256": item["sha256"],
                    "host_container_match": matches,
                }
            )
            rows_ok = rows_ok and matches

    base_ok = base_result["status"] in PASS_LIKE
    caveats = [
        item
        for item in [base_result.get("caveat")]
        if isinstance(item, str) and item
    ]
    payload = result(
        "host_container_mount_and_resume_provenance",
        base_ok and rows_ok and dispatch_match,
        {
            "base_preflight_mount_check": base_result,
            "actual_original_dispatch_document_match": dispatch_match,
            "resume_document_mount_checks": rows,
        },
    )
    if payload["status"] == "passed" and caveats:
        payload["status"] = "passed_with_caveat"
        payload["caveat"] = " | ".join(caveats)
    return payload


def check_no_active_training_strict(
    base: Any, base_config: Mapping[str, Any]
) -> dict[str, Any]:
    base_result = base.check_no_active_training(base_config)
    evidence = dict(base_result.get("evidence", {}))
    safe = (
        base_result["status"] in PASS_LIKE
        and evidence.get("no_active_training") is True
        and evidence.get("future_gpu_stage_launch_blocked") is False
    )
    evidence["base_guard_status"] = base_result["status"]
    evidence["strict_fail_closed"] = True
    payload = result("no_active_training_guard", safe, evidence)
    if safe and base_result.get("caveat"):
        payload["status"] = "passed_with_caveat"
        payload["caveat"] = base_result["caveat"]
    elif not safe and base_result.get("caveat"):
        payload["caveat"] = base_result["caveat"]
    return payload


def failure_manifest(
    config: Mapping[str, Any],
    exc: BaseException,
    *,
    claim_path: Path,
) -> dict[str, Any]:
    return {
        "schema": "jointbuildgs.fusion_w1.resume_r0_v2.preflight.v1",
        "task_id": config.get("task_id"),
        "run_id": config.get("run_id"),
        "created_utc": now_utc(),
        "created_kst": now_kst(),
        "status": "BLOCKED",
        "five_pin_preflight": {
            "passed_count": 0,
            "total_count": 5,
            "pins": [],
        },
        "additional_checks": [],
        "failed_checks": ["r0_unhandled_failure"],
        "failure": {
            "error_type": type(exc).__name__,
            "error": str(exc),
            "claim_path": claim_path.relative_to(REPO).as_posix(),
        },
        "execution_counters": {
            "learning_runs_started": None,
            "readout_runs_started": None,
            "roofer_runs_started": None,
            "scoring_runs_started": None,
        },
        "continuation": {
            "r1_pose_publication_authorized_if_passed": False,
            "learning_authorized_by_r0": False,
            "r2_must_wait_for_r1_all_checks": True,
        },
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    args = parser.parse_args(argv)
    config_path = args.config.resolve()
    if config_path != DEFAULT_CONFIG.resolve():
        raise ResumeR0Error("only the committed default config may run")
    config = load_json(config_path)
    output = {key: REPO / value for key, value in config["outputs"].items()}
    existing = [
        str(path.relative_to(REPO))
        for path in output.values()
        if path.exists()
    ]
    if existing:
        raise ResumeR0Error(f"R0 outputs already exist: {existing}")

    claim_payload = {
        "schema": "jointbuildgs.fusion_w1.resume_r0_v2.claim.v1",
        "state": "STARTED",
        "created_utc": now_utc(),
        "created_kst": now_kst(),
        "pid": os.getpid(),
        "config": config_path.relative_to(REPO).as_posix(),
        "config_sha256": sha256_file(config_path),
        "exact_once": True,
    }
    exclusive_json(output["claim"], claim_payload)

    journal: EventJournal | None = None
    try:
        journal = EventJournal(output["event_log"])
        journal.record(
            {
                "at": now_utc(),
                "event": "r0_started",
                "config": str(config_path.relative_to(REPO)),
                "config_sha256": claim_payload["config_sha256"],
                "claim": config["outputs"]["claim"],
            }
        )
        verify_config(config, config_path)

        base_lock = config["base_preflight"]
        base_config_path = REPO / base_lock["config"]
        base_implementation_path = REPO / base_lock["implementation"]
        if sha256_file(base_config_path) != base_lock["config_sha256"]:
            raise ResumeR0Error("base preflight config hash drift")
        if (
            sha256_file(base_implementation_path)
            != base_lock["implementation_sha256"]
        ):
            raise ResumeR0Error("base preflight implementation hash drift")
        base_config = load_json(base_config_path)
        base = import_base_module(base_implementation_path)

        git_check = guarded(
            "git_commit_branch_and_document_lock",
            lambda: check_git_and_documents(config, list(output.values())),
            journal,
        )
        checks = [
            git_check,
            guarded(
                "docker_image_ids_and_versions",
                lambda: base.check_docker_images(base_config),
                journal,
            ),
            guarded(
                "gpu_and_cuda_matmul",
                lambda: base.check_cuda_smoke(base_config),
                journal,
            ),
            guarded(
                "canonical_input_sha256",
                lambda: base.check_canonical_inputs(base_config, journal),
                journal,
            ),
            guarded(
                "host_container_mount_and_resume_provenance",
                lambda: check_resume_mount_freshness(
                    config, base, base_config, git_check
                ),
                journal,
            ),
            guarded(
                "epsg_class_and_datum_lock",
                lambda: base.check_coordinate_class_datum(
                    base_config, os.environ["FUS_W1_HOST_REPO"]
                ),
                journal,
            ),
            guarded(
                "no_active_training_guard",
                lambda: check_no_active_training_strict(base, base_config),
                journal,
            ),
            guarded(
                "readout_serial_24g_cgroup_plan",
                lambda: base.check_readout_plan(base_config),
                journal,
            ),
            guarded(
                "coreg_lock2_evidence_and_zero_counters",
                lambda: check_coreg_and_counters(config),
                journal,
            ),
            guarded(
                "r0_source_pose_before_authorized_r1",
                lambda: check_r0_source_pose(config, base_config),
                journal,
            ),
        ]

        five_pin_names = [
            "git_commit_branch_and_document_lock",
            "docker_image_ids_and_versions",
            "gpu_and_cuda_matmul",
            "canonical_input_sha256",
            "host_container_mount_and_resume_provenance",
        ]
        five_pins = [
            next(item for item in checks if item["name"] == name)
            for name in five_pin_names
        ]
        passed = all(item["status"] in PASS_LIKE for item in checks)
        counter_check = next(
            item
            for item in checks
            if item["name"] == "coreg_lock2_evidence_and_zero_counters"
        )
        observed_counters = counter_check.get("evidence", {}).get(
            "runtime_counter_values",
            {
                key: None
                for key in config["counter_source"]["required_zero"]
            },
        )
        manifest = {
            "schema": "jointbuildgs.fusion_w1.resume_r0_v2.preflight.v1",
            "task_id": config["task_id"],
            "run_id": config["run_id"],
            "created_utc": now_utc(),
            "created_kst": now_kst(),
            "status": "PASSED" if passed else "BLOCKED",
            "claim": {
                "path": config["outputs"]["claim"],
                "sha256": sha256_file(output["claim"]),
            },
            "five_pin_preflight": {
                "passed_count": sum(
                    item["status"] in PASS_LIKE for item in five_pins
                ),
                "total_count": len(five_pins),
                "pins": five_pins,
            },
            "additional_checks": [
                item
                for item in checks
                if item["name"] not in five_pin_names
            ],
            "failed_checks": [
                item["name"]
                for item in checks
                if item["status"] == "failed"
            ],
            "time_policy": config["time_policy"],
            "execution_counters": observed_counters,
            "continuation": {
                "r1_pose_publication_authorized_if_passed": passed,
                "learning_authorized_by_r0": False,
                "r2_must_wait_for_r1_all_checks": True,
            },
        }
        atomic_json(output["preflight"], manifest)
        status_payload = {
            "schema": "jointbuildgs.fusion_w1.resume_r0_v2.status.v1",
            "status": manifest["status"],
            "preflight_path": config["outputs"]["preflight"],
            "preflight_sha256": sha256_file(output["preflight"]),
            "five_pins": (
                f"{manifest['five_pin_preflight']['passed_count']}/"
                f"{manifest['five_pin_preflight']['total_count']}"
            ),
            "failed_checks": manifest["failed_checks"],
            "execution_counters": observed_counters,
            "next_stage": "R1" if passed else None,
        }
        atomic_json(output["status"], status_payload)
        journal.write(
            "r0_finished",
            status=manifest["status"],
            preflight_sha256=status_payload["preflight_sha256"],
        )
        print(json.dumps(status_payload, ensure_ascii=False, sort_keys=True))
        return 0 if passed else 2
    except BaseException as exc:
        if journal is not None:
            try:
                journal.write(
                    "r0_unhandled_failure",
                    error_type=type(exc).__name__,
                    error=str(exc),
                )
            except Exception:
                pass
        manifest = failure_manifest(
            config, exc, claim_path=output["claim"]
        )
        atomic_json(output["preflight"], manifest)
        status_payload = {
            "schema": "jointbuildgs.fusion_w1.resume_r0_v2.status.v1",
            "status": "BLOCKED",
            "preflight_path": config["outputs"]["preflight"],
            "preflight_sha256": sha256_file(output["preflight"]),
            "five_pins": "0/5",
            "failed_checks": manifest["failed_checks"],
            "execution_counters": manifest["execution_counters"],
            "next_stage": None,
        }
        atomic_json(output["status"], status_payload)
        print(json.dumps(status_payload, ensure_ascii=False, sort_keys=True))
        return 2
    finally:
        if journal is not None:
            journal.close()


if __name__ == "__main__":
    raise SystemExit(main())
