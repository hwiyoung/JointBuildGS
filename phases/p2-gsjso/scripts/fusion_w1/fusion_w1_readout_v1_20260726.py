#!/usr/bin/env python3
"""Fusion W1 serial readout, Roofer, and per-building scoring driver.

The driver consumes only immutable, completed 30k training jobs.  It wraps the
locked ``tum_mob_tsdf_extract.py`` point-cloud readout, the P0 SMRF/footprint
classification helper, the pinned default Roofer image, and the canonical P0
CityJSON scoring helpers.  Every external stage is authorized by an immutable
receipt and counted exactly once.  Failed or partially started jobs are never
retried, except for the one human-approved, byte-pinned pre-output gsplat cache
failure represented by the dedicated infrastructure-retry policy.

The shell wrapper owns Docker, GPU, cgroup, timeout, and host process guards.
This module owns input validation, lineage, state transitions, counters,
incremental ``w1_scores_building.csv`` publication, and the required panel.
It records measurements and observations only; it does not make a verdict.
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import fcntl
import hashlib
import importlib.util
import io
import json
import math
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import time
import traceback
from typing import Any, Iterable, Mapping, Sequence


REPO = Path(__file__).resolve().parents[4]
CONTAINER_REPO = Path("/workspace/JointBuildGS")
DEFAULT_CONFIG = (
    REPO
    / "phases/p2-gsjso/configs/fusion_w1/fusion_w1_readout_v1_20260726.json"
)
DEFAULT_READOUT_RETRY_POLICY = (
    REPO
    / "phases/p2-gsjso/configs/fusion_w1/fusion_w1_readout_infra_retry_20260726.json"
)
READOUT_RECOVERY2_POLICY_RELATIVE = Path(
    "phases/p2-gsjso/configs/fusion_w1/fusion_w1_readout_infra_retry2_20260726.json"
)
DEFAULT_READOUT_RECOVERY2_POLICY = (
    REPO / READOUT_RECOVERY2_POLICY_RELATIVE
)
CONFIG_SCHEMA = "jointbuildgs.fusion_w1.readout_driver.config.v1"
COUNTER_SCHEMA = "jointbuildgs.fusion_w1.readout_counters.v1"
JOB_SCHEMA = "jointbuildgs.fusion_w1.readout_job.v1"
MATERIALIZATION_SCHEMA = (
    "jointbuildgs.fusion_w1.readout_materialization.v1"
)
TRAINING_STARTED_SCHEMA = "jointbuildgs.fusion_w1.training_started.v1"
TRAINING_FAILED_SCHEMA = "jointbuildgs.fusion_w1.training_failed.v1"
RETRY_POLICY_SCHEMA = "jointbuildgs.fusion_w1.training_infra_retry_policy.v1"
RETRY_STARTED_SCHEMA = "jointbuildgs.fusion_w1.training_infra_retry_started.v1"
RETRY_COMPLETED_SCHEMA = "jointbuildgs.fusion_w1.training_infra_retry_completed.v1"
RETRY_ATTEMPT_DIRECTORY = "infra_retry_01"
READOUT_RETRY_POLICY_SCHEMA = (
    "jointbuildgs.fusion_w1.readout_infra_retry_policy.v1"
)
READOUT_RETRY_STARTED_SCHEMA = (
    "jointbuildgs.fusion_w1.readout_infra_retry_started.v1"
)
READOUT_RETRY_COMPLETED_SCHEMA = (
    "jointbuildgs.fusion_w1.readout_infra_retry_completed.v1"
)
READOUT_RETRY_FAILED_SCHEMA = (
    "jointbuildgs.fusion_w1.readout_infra_retry_failed.v1"
)
READOUT_RETRY_INVOCATION_SCHEMA = (
    "jointbuildgs.fusion_w1.extract_infra_retry_invocation.v1"
)
READOUT_RETRY_ATTEMPT_DIRECTORY = "infra_retry_01"
READOUT_RECOVERY2_POLICY_SCHEMA = (
    "jointbuildgs.fusion_w1.readout_infra_retry2_policy.v1"
)
READOUT_RECOVERY2_STARTED_SCHEMA = (
    "jointbuildgs.fusion_w1.readout_infra_retry2_started.v1"
)
READOUT_RECOVERY2_SEED_SCHEMA = (
    "jointbuildgs.fusion_w1.gsplat_cache_seed_manifest.v1"
)
READOUT_RECOVERY2_INVOCATION_SCHEMA = (
    "jointbuildgs.fusion_w1.extract_infra_retry2_invocation.v1"
)
READOUT_RECOVERY2_COMPLETED_SCHEMA = (
    "jointbuildgs.fusion_w1.readout_infra_retry2_completed.v1"
)
READOUT_RECOVERY2_FAILED_SCHEMA = (
    "jointbuildgs.fusion_w1.readout_infra_retry2_failed.v1"
)
READOUT_RECOVERY2_ATTEMPT_DIRECTORY = "infra_retry_02"
JIT_BUILD_ENVIRONMENT = {"MAX_JOBS": "1"}
WRITABLE_ENVIRONMENT_KEYS = frozenset(
    {"HOME", "XDG_CACHE_HOME", "TORCH_EXTENSIONS_DIR"}
)

ARMS = ("A", "B")
RUNS = ("r1", "r2")
STAGE_COUNTERS = {
    "readout": "readout_runs_started",
    "roofer": "roofer_runs_started",
    "scoring": "scoring_runs_started",
}
STAGE_STARTED_FILES = {
    "readout": "readout_started.json",
    "roofer": "roofer_started.json",
    "scoring": "scoring_started.json",
}


class ReadoutError(RuntimeError):
    """Fail-closed contract, lineage, or state-transition error."""


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat()


def sha256_file(path: Path, block_size: int = 1 << 20) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(block_size), b""):
            digest.update(block)
    return digest.hexdigest()


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def canonical_json(payload: Any) -> bytes:
    return (
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")


def repo_path(value: str | Path, *, repo: Path = REPO) -> Path:
    raw = Path(value)
    if raw.is_absolute():
        raise ReadoutError(f"absolute repository path is forbidden: {raw}")
    candidate = (repo / raw).resolve()
    try:
        candidate.relative_to(repo.resolve())
    except ValueError as exc:
        raise ReadoutError(f"path escapes repository: {raw}") from exc
    return candidate


def repo_relative(path: Path, *, repo: Path = REPO) -> str:
    try:
        return str(path.resolve().relative_to(repo.resolve()))
    except ValueError as exc:
        raise ReadoutError(f"path is outside repository: {path}") from exc


def require_regular(path: Path, label: str) -> None:
    if not path.is_file() or path.is_symlink() or path.stat().st_size <= 0:
        raise ReadoutError(f"{label} is missing, empty, non-regular, or symlink: {path}")


def require_safe_input_file(
    path: Path,
    label: str,
    *,
    repo: Path = REPO,
) -> None:
    """Accept a regular file or a repository-contained immutable symlink."""

    if not path.is_file() or path.stat().st_size <= 0:
        raise ReadoutError(f"{label} is missing or empty: {path}")
    if path.is_symlink():
        try:
            path.resolve(strict=True).relative_to(repo.resolve())
        except (OSError, ValueError) as exc:
            raise ReadoutError(
                f"{label} symlink escapes the repository: {path}"
            ) from exc


def load_json(path: Path) -> dict[str, Any]:
    require_regular(path, "JSON")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ReadoutError(f"cannot read JSON {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ReadoutError(f"JSON root is not an object: {path}")
    return value


def atomic_bytes(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    with temporary.open("xb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def atomic_json(path: Path, payload: Mapping[str, Any]) -> None:
    atomic_bytes(path, canonical_json(dict(payload)))


def exclusive_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())


def append_jsonl(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("ab") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        handle.write(canonical_json(dict(payload)))
        handle.flush()
        os.fsync(handle.fileno())
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def read_csv(path: Path) -> list[dict[str, str]]:
    require_regular(path, "CSV")
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise ReadoutError(f"CSV has no header: {path}")
        return [dict(row) for row in reader]


def csv_header(path: Path) -> list[str]:
    require_regular(path, "CSV")
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.reader(handle)
        try:
            return list(next(reader))
        except StopIteration as exc:
            raise ReadoutError(f"CSV has no header: {path}") from exc


def csv_value(value: Any) -> Any:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        return "" if not math.isfinite(value) else f"{value:.9f}"
    return value


def atomic_csv(
    path: Path,
    rows: Sequence[Mapping[str, Any]],
    fields: Sequence[str],
) -> None:
    output = io.StringIO(newline="")
    writer = csv.DictWriter(
        output,
        fieldnames=list(fields),
        extrasaction="ignore",
        lineterminator="\n",
    )
    writer.writeheader()
    for row in rows:
        writer.writerow({field: csv_value(row.get(field)) for field in fields})
    atomic_bytes(path, output.getvalue().encode("utf-8"))


def truth(value: Any) -> bool:
    return value is True or str(value).strip().lower() in {
        "true",
        "1",
        "yes",
    }


def falsehood(value: Any) -> bool:
    return value is False or str(value).strip().lower() in {
        "false",
        "0",
        "no",
    }


def optional_float(value: Any) -> float | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() in {"none", "nan", "n/a", "na"}:
        return None
    number = float(text)
    return number if math.isfinite(number) else None


def require_equal(observed: Any, expected: Any, label: str) -> None:
    if observed != expected:
        raise ReadoutError(
            f"{label} mismatch: observed={observed!r}, expected={expected!r}"
        )


def safe_identity(building_id: str, arm: str, run: str) -> None:
    if re.fullmatch(r"DEBY_LOD2_[0-9]+", building_id) is None:
        raise ReadoutError(f"unsafe or noncanonical building ID: {building_id!r}")
    if arm not in ARMS or run not in RUNS:
        raise ReadoutError(f"invalid arm/run: {arm!r}/{run!r}")


def job_key(building_id: str, arm: str, run: str) -> str:
    safe_identity(building_id, arm, run)
    return f"{building_id}/arm_{arm}/{run}"


def writable_readout_environment(
    config: Mapping[str, Any],
    *,
    repo: Path = REPO,
    create: bool = False,
    require_ready: bool = False,
    declared_paths: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Resolve a normal or immutable historical writable-cache contract."""

    raw = (
        declared_paths
        if declared_paths is not None
        else config.get("pointcloudification", {}).get("writable_environment")
    )
    if not isinstance(raw, Mapping) or set(raw) != WRITABLE_ENVIRONMENT_KEYS:
        raise ReadoutError(
            "pointcloud writable environment must contain exactly HOME, "
            "XDG_CACHE_HOME, TORCH_EXTENSIONS_DIR"
        )
    runtime_root = repo_path(
        Path(str(config["outputs"]["root"])).parent / "runtime_env",
        repo=repo,
    )
    host_paths: dict[str, str] = {}
    container_values: dict[str, str] = {}
    for key in sorted(WRITABLE_ENVIRONMENT_KEYS):
        value = raw[key]
        if not isinstance(value, str) or not value:
            raise ReadoutError(f"writable environment path is invalid for {key}")
        relative = Path(value)
        if relative.is_absolute() or ".." in relative.parts:
            raise ReadoutError(f"unsafe writable environment path for {key}: {value!r}")
        unresolved = repo / relative
        cursor = unresolved
        while cursor != repo and cursor != cursor.parent:
            if cursor.exists() and cursor.is_symlink():
                raise ReadoutError(
                    f"writable environment path contains a symlink for {key}: {cursor}"
                )
            cursor = cursor.parent
        path = repo_path(relative, repo=repo)
        try:
            path.relative_to(runtime_root)
        except ValueError as exc:
            raise ReadoutError(
                f"writable environment path escapes Fusion-W1 runtime root for {key}: {value!r}"
            ) from exc
        if path == runtime_root:
            raise ReadoutError(f"writable environment leaf is missing for {key}")
        if create:
            path.mkdir(parents=True, exist_ok=True)
            if not path.is_dir() or path.is_symlink():
                raise ReadoutError(f"writable environment is not a directory for {key}: {path}")
            if not os.access(path, os.W_OK | os.X_OK):
                raise ReadoutError(f"writable environment is not writable for {key}: {path}")
        elif require_ready:
            if not path.is_dir() or path.is_symlink():
                raise ReadoutError(
                    f"writable environment is not ready for {key}: {path}"
                )
            if not os.access(path, os.W_OK | os.X_OK):
                raise ReadoutError(
                    f"writable environment is not writable for {key}: {path}"
                )
        elif path.exists() and (not path.is_dir() or path.is_symlink()):
            raise ReadoutError(f"writable environment is invalid for {key}: {path}")
        host_paths[key] = repo_relative(path, repo=repo)
        container_values[key] = str(CONTAINER_REPO / Path(host_paths[key]))
    return {
        "host_paths": host_paths,
        "container_values": container_values,
        "runtime_root": repo_relative(runtime_root, repo=repo),
        "shared_by_training_and_serial_readout": True,
    }


def jit_build_environment(config: Mapping[str, Any]) -> dict[str, str]:
    raw = config.get("pointcloudification", {}).get("jit_build_environment")
    require_equal(raw, JIT_BUILD_ENVIRONMENT, "readout JIT build environment")
    return dict(JIT_BUILD_ENVIRONMENT)


def load_config(path: Path) -> dict[str, Any]:
    config = load_json(path)
    require_equal(config.get("schema"), CONFIG_SCHEMA, "driver config schema")
    require_equal(config.get("branch"), "exp/fusion-w1", "branch lock")
    resource = config["resource_lock"]
    require_equal(resource.get("memory"), "24g", "memory cgroup")
    require_equal(resource.get("memory_swap"), "24g", "memory-swap cgroup")
    require_equal(resource.get("serial_jobs"), True, "serial job lock")
    require_equal(
        resource.get("concurrent_with_training"),
        False,
        "training concurrency lock",
    )
    require_equal(
        resource.get("failed_job_retry"), "forbidden", "failed retry policy"
    )
    require_equal(config["roofer"].get("outer_parallelism"), 1, "Roofer outer parallelism")
    require_equal(
        config["pointcloudification"].get("semantic_pass"),
        False,
        "W1 semantic readout",
    )
    require_equal(
        config["classification"].get("target_density"),
        0.0,
        "classification downsample lock",
    )
    require_equal(
        config["smoke_job"].get("job_key"),
        job_key(
            config["smoke_job"]["building_id"],
            config["smoke_job"]["arm"],
            config["smoke_job"]["run"],
        ),
        "smoke job key",
    )
    writable_readout_environment(config, repo=path.resolve().parents[3])
    jit_build_environment(config)
    expected_queue = [
        ("core", "A", "r1"),
        ("core", "A", "r2"),
        ("core", "B", "r1"),
        ("core", "B", "r2"),
        ("extension", "A", "r1"),
        ("extension", "A", "r2"),
        ("extension", "B", "r1"),
        ("extension", "B", "r2"),
    ]
    observed_queue = [
        (phase.get("cohort"), phase.get("arm"), phase.get("run"))
        for phase in config["queue_contract"]["ordered_phases"]
    ]
    require_equal(observed_queue, expected_queue, "locked readout queue phases")
    require_equal(
        config["queue_contract"].get(
            "same_error_type_consecutive_building_stop_n"
        ),
        3,
        "three-building catastrophe stop",
    )
    require_equal(
        config["scoring"]["reference"].get("score_time_z_shift_m"),
        -45.7,
        "ellipsoidal-to-orthometric score-time shift",
    )
    require_equal(
        Path(config["outputs"]["scores_csv"]).name,
        "w1_scores_building.csv",
        "fixed score filename",
    )
    require_equal(
        Path(config["outputs"]["summary_csv"]).name,
        "w1_summary.csv",
        "fixed summary filename",
    )
    require_equal(
        config["publication"].get(
            "partial_finalize_increments_stage_counters"
        ),
        False,
        "partial finalize counter policy",
    )
    return config


def job_dir(
    config: Mapping[str, Any],
    building_id: str,
    arm: str,
    run: str,
    *,
    repo: Path = REPO,
) -> Path:
    safe_identity(building_id, arm, run)
    value = config["outputs"]["job_template"].format(
        building_id=building_id,
        arm=arm,
        run=run,
    )
    return repo_path(value, repo=repo)


def training_job_dir(
    config: Mapping[str, Any],
    building_id: str,
    arm: str,
    run: str,
    *,
    repo: Path = REPO,
) -> Path:
    safe_identity(building_id, arm, run)
    root = repo_path(config["training"]["root"], repo=repo)
    relative = config["training"]["job_template"].format(
        building_id=building_id,
        arm=arm,
        run=run,
    )
    path = (root / relative).resolve()
    try:
        path.relative_to(root.resolve())
    except ValueError as exc:
        raise ReadoutError("training job path escapes training root") from exc
    return path


def load_module(name: str, path: Path) -> Any:
    require_regular(path, f"module {name}")
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ReadoutError(f"cannot load helper module: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def p0prime_module(
    config: Mapping[str, Any], *, repo: Path = REPO
) -> Any:
    module = load_module(
        "fusion_w1_seed_p0prime_runtime",
        repo_path(config["p0prime"]["driver"], repo=repo),
    )
    # P0-prime intentionally resolves only repository-relative paths.
    module.REPO = repo.resolve()
    return module


def verify_hash(path: Path, expected: str, label: str) -> str:
    require_regular(path, label)
    observed = sha256_file(path)
    require_equal(observed, expected, f"{label} SHA256")
    return observed


def target_rows(
    config: Mapping[str, Any], *, repo: Path = REPO
) -> list[dict[str, str]]:
    spec = config["targets"]
    path = repo_path(spec["path"], repo=repo)
    verify_hash(path, spec["sha256"], "w1_targets.csv")
    rows = read_csv(path)
    require_equal(len(rows), int(spec["expected_population"]), "target population")
    ids = [row[spec["id_field"]] for row in rows]
    orders = [int(row[spec["order_field"]]) for row in rows]
    if len(ids) != len(set(ids)):
        raise ReadoutError("w1_targets.csv contains duplicate building IDs")
    if sorted(orders) != list(range(1, len(rows) + 1)):
        raise ReadoutError("w1_targets.csv processing_order is not 1..N")
    return sorted(rows, key=lambda row: int(row[spec["order_field"]]))


def target_metadata(
    config: Mapping[str, Any],
    building_id: str,
    *,
    repo: Path = REPO,
) -> dict[str, Any]:
    target = [
        row
        for row in target_rows(config, repo=repo)
        if row["building_id"] == building_id
    ]
    if len(target) != 1:
        raise ReadoutError(f"target row is not unique: {building_id}")
    target_row = target[0]
    join = config["texture_join"]
    ladder_path = repo_path(join["path"], repo=repo)
    verify_hash(ladder_path, join["sha256"], "boundary_map_v4_1_ladder.csv")
    ladder = [
        row
        for row in read_csv(ladder_path)
        if row[join["id_field"]] == building_id
    ]
    if len(ladder) != 1:
        raise ReadoutError(f"texture ladder row is not unique: {building_id}")
    ladder_row = ladder[0]
    cell = ladder_row[join["tier_source_field"]]
    if cell not in join["tier_map"]:
        raise ReadoutError(f"unknown ladder cell for {building_id}: {cell}")
    tier = join["tier_map"][cell]
    require_equal(target_row["source_cell_label"], cell, "target/ladder cell")
    require_equal(target_row["tier"], tier, "target/ladder tier")
    target_texture = float(target_row["texture_low_gradient_fraction"])
    ladder_texture = float(ladder_row[join["texture_field"]])
    if abs(target_texture - ladder_texture) > 5e-10:
        raise ReadoutError(
            f"target/ladder texture value drift: {target_texture} vs {ladder_texture}"
        )
    threshold = float(join["t9_t11_threshold"])
    texture_stratum = (
        join["textureless_label"]
        if ladder_texture > threshold
        else join["textured_label"]
    )
    return {
        "building_id": building_id,
        "processing_order": int(target_row["processing_order"]),
        "tier": tier,
        "cohort": target_row["cohort"],
        "priority_bucket": target_row["priority_bucket"],
        "source_cell_label": cell,
        "texture_low_gradient_fraction": ladder_texture,
        "texture_stratum": texture_stratum,
        "texture_threshold": threshold,
        "texture_rule": join["textureless_rule"],
        "target_row": target_row,
        "ladder_row_sha256": sha256_bytes(canonical_json(ladder_row)),
    }


def verify_static_inputs(
    config: Mapping[str, Any], *, repo: Path = REPO
) -> dict[str, str]:
    locks: list[tuple[str, str, str]] = [
        (
            config["training"]["driver_config"],
            config["training"]["driver_config_sha256"],
            "training driver config",
        ),
        (
            config["training"]["trainer_source"],
            config["training"]["trainer_source_sha256"],
            "trainer source for legacy final checkpoint export",
        ),
        (
            config["pointcloudification"]["script"],
            config["pointcloudification"]["script_sha256"],
            "pointcloudification script",
        ),
        (
            config["classification"]["script"],
            config["classification"]["script_sha256"],
            "classification script",
        ),
        (
            config["footprint"]["path"],
            config["footprint"]["sha256"],
            "footprint GPKG",
        ),
        (
            config["p0prime"]["driver"],
            config["p0prime"]["driver_sha256"],
            "P0-prime driver",
        ),
        (
            config["scoring"]["paired_baseline"]["path"],
            config["scoring"]["paired_baseline"]["sha256"],
            "paired baseline CSV",
        ),
    ]
    for name, helper in config["scoring"]["canonical_helpers"].items():
        locks.append((helper["path"], helper["sha256"], f"canonical helper {name}"))
    for path, expected in config["scoring"]["reference"]["locked_files"].items():
        locks.append((path, expected, f"reference {Path(path).name}"))
    observed: dict[str, str] = {}
    for value, expected, label in locks:
        path = repo_path(value, repo=repo)
        observed[value] = verify_hash(path, expected, label)
    target_rows(config, repo=repo)
    training_config = load_json(
        repo_path(config["training"]["driver_config"], repo=repo)
    )
    require_equal(
        training_config.get("schema"),
        "jointbuildgs.fusion_w1.training_driver.config.v1",
        "training driver config schema",
    )
    require_equal(
        training_config["recipe"].get("max_iter"),
        config["training"]["required_optimizer_updates"],
        "training/readout optimizer update contract",
    )
    training_barrier = str(
        Path(config["training"]["root"])
        / training_config["outputs"]["aggregate_runtime_counter_lock"]
    )
    require_equal(
        config["resource_lock"]["shared_training_launch_barrier"],
        training_barrier,
        "shared training launch barrier",
    )
    return observed


def _verified_receipt_reference(
    reference: Any,
    expected_path: Path,
    label: str,
    *,
    repo: Path,
) -> tuple[dict[str, Any], str]:
    if not isinstance(reference, Mapping):
        raise ReadoutError(f"{label} reference is missing")
    path_value = reference.get("path")
    digest_value = reference.get("sha256")
    if not isinstance(path_value, str) or not isinstance(digest_value, str):
        raise ReadoutError(f"{label} reference path/SHA256 is invalid")
    observed_path = repo_path(path_value, repo=repo)
    require_equal(observed_path, expected_path.resolve(), f"{label} path")
    digest = verify_hash(observed_path, digest_value, label)
    return load_json(observed_path), digest


def _validate_infrastructure_retry_chain(
    *,
    completed: Mapping[str, Any],
    target: Path,
    materialization_path: Path,
    materialization_sha256: str,
    failed_path: Path,
    expected_job_key: str,
    training_contract: Mapping[str, Any],
    repo: Path,
) -> Path | None:
    chain = completed.get("infrastructure_retry")
    if chain is None:
        return None
    if not isinstance(chain, Mapping):
        raise ReadoutError("infrastructure retry chain is not an object")

    attempt = target / RETRY_ATTEMPT_DIRECTORY
    if attempt.is_symlink() or not attempt.is_dir():
        raise ReadoutError(f"infrastructure retry directory is invalid: {attempt}")
    root_started_path = target / "started.json"
    root_full_state_path = target / "full_state_manifest.json"
    root_log_path = target / "training.log"
    retry_started_path = attempt / "retry_started.json"
    retry_completed_path = attempt / "retry_completed.json"

    policy = chain.get("policy")
    if not isinstance(policy, Mapping):
        raise ReadoutError("infrastructure retry policy binding is missing")
    require_equal(policy.get("schema"), RETRY_POLICY_SCHEMA, "retry policy schema")
    require_equal(policy.get("status"), "APPROVED", "retry policy status")
    require_equal(
        policy.get("attempt_directory"),
        RETRY_ATTEMPT_DIRECTORY,
        "retry attempt directory",
    )
    policy_path_value = policy.get("path")
    policy_sha256 = policy.get("sha256")
    if not isinstance(policy_path_value, str) or not isinstance(policy_sha256, str):
        raise ReadoutError("infrastructure retry policy path/SHA256 is invalid")
    verify_hash(
        repo_path(policy_path_value, repo=repo),
        policy_sha256,
        "infrastructure retry policy",
    )
    required_failure = policy.get("required_failure")
    if not isinstance(required_failure, Mapping):
        raise ReadoutError("retry required-failure binding is missing")
    pinned = required_failure.get("artifact_sha256")
    if not isinstance(pinned, Mapping) or set(pinned) != {
        "started",
        "failed",
        "log",
        "full_state",
    }:
        raise ReadoutError("retry original artifact SHA256 binding is incomplete")

    original_started, original_started_sha = _verified_receipt_reference(
        chain.get("original_started_receipt"),
        root_started_path,
        "original training started receipt",
        repo=repo,
    )
    original_failed, original_failed_sha = _verified_receipt_reference(
        chain.get("original_failed_receipt"),
        failed_path,
        "original training failed receipt",
        repo=repo,
    )
    require_equal(
        original_started.get("schema"),
        TRAINING_STARTED_SCHEMA,
        "original training started schema",
    )
    require_equal(
        original_failed.get("schema"),
        TRAINING_FAILED_SCHEMA,
        "original training failed schema",
    )
    require_equal(original_started.get("job_key"), expected_job_key, "original started job key")
    require_equal(original_failed.get("job_key"), expected_job_key, "original failed job key")
    require_equal(original_started_sha, pinned.get("started"), "pinned original started SHA256")
    require_equal(original_failed_sha, pinned.get("failed"), "pinned original failed SHA256")
    verify_hash(root_log_path, str(pinned.get("log")), "original training log")
    verify_hash(
        root_full_state_path,
        str(pinned.get("full_state")),
        "original failed full-state manifest",
    )
    require_equal(
        original_failed.get("log_sha256"),
        pinned.get("log"),
        "original failed/log SHA256 binding",
    )

    retry_started, retry_started_sha = _verified_receipt_reference(
        chain.get("retry_started_receipt"),
        retry_started_path,
        "infrastructure retry started receipt",
        repo=repo,
    )
    retry_completed, retry_completed_sha = _verified_receipt_reference(
        chain.get("retry_completed_receipt"),
        retry_completed_path,
        "infrastructure retry completed receipt",
        repo=repo,
    )
    expected_retry_key = f"{expected_job_key}/{RETRY_ATTEMPT_DIRECTORY}"
    require_equal(retry_started.get("schema"), RETRY_STARTED_SCHEMA, "retry started schema")
    require_equal(
        retry_completed.get("schema"),
        RETRY_COMPLETED_SCHEMA,
        "retry completed schema",
    )
    for payload, label in (
        (retry_started, "retry started"),
        (retry_completed, "retry completed"),
    ):
        require_equal(payload.get("job_key"), expected_job_key, f"{label} job key")
        require_equal(payload.get("retry_key"), expected_retry_key, f"{label} retry key")
    require_equal(retry_completed.get("return_code"), 0, "retry return code")
    require_equal(retry_started.get("policy"), dict(policy), "retry started policy binding")
    retry_materialization = retry_started.get("materialization")
    if not isinstance(retry_materialization, Mapping):
        raise ReadoutError("retry started materialization binding is missing")
    require_equal(
        repo_path(str(retry_materialization.get("path")), repo=repo),
        materialization_path.resolve(),
        "retry materialization path",
    )
    require_equal(
        retry_materialization.get("sha256"),
        materialization_sha256,
        "retry materialization SHA256",
    )
    nested_started = retry_completed.get("retry_started_receipt")
    if not isinstance(nested_started, Mapping):
        raise ReadoutError("retry completed/started receipt binding is missing")
    require_equal(
        repo_path(str(nested_started.get("path")), repo=repo),
        retry_started_path.resolve(),
        "retry completed/started path",
    )
    require_equal(
        nested_started.get("sha256"),
        retry_started_sha,
        "retry completed/started SHA256",
    )
    require_equal(
        retry_completed.get("training_completion"),
        completed.get("training_completion"),
        "retry/root training completion",
    )
    training_completion = completed.get("training_completion")
    if not isinstance(training_completion, Mapping):
        raise ReadoutError("retry training completion is missing")
    for field, relative_key, label in (
        ("checkpoint", "full_state_checkpoint_relpath", "30k full-state checkpoint"),
        ("final_checkpoint", "extract_checkpoint_relpath", "extract checkpoint"),
        ("full_state_manifest", "full_state_relpath", "full-state manifest"),
    ):
        path_value = training_completion.get(field)
        if not isinstance(path_value, str):
            raise ReadoutError(f"retry {label} path is invalid")
        require_equal(
            repo_path(path_value, repo=repo),
            (attempt / str(training_contract[relative_key])).resolve(),
            f"retry {label} path",
        )
    require_equal(
        chain.get("optimizer_restart_completed_steps"),
        0,
        "retry optimizer restart step",
    )
    require_equal(
        chain.get("resolved_config_difference_keys"),
        ["out_dir"],
        "retry resolved-config differences",
    )
    require_equal(
        chain.get("original_file_snapshot_sha256"),
        retry_completed.get("original_failure_snapshot_sha256"),
        "retry original snapshot binding",
    )
    # Keep the validated receipt digests live in the chain checks above; these
    # assignments also make accidental removal of either verification obvious.
    if not retry_started_sha or not retry_completed_sha:
        raise ReadoutError("infrastructure retry receipt SHA256 is empty")
    return attempt


def resolve_training_artifacts(
    config: Mapping[str, Any],
    building_id: str,
    arm: str,
    run: str,
    *,
    repo: Path = REPO,
) -> dict[str, Any]:
    """Validate a single immutable, successful, full-state 30k training job."""

    target = training_job_dir(
        config, building_id, arm, run, repo=repo
    )
    failed = target / config["training"]["failed"]
    materialization_path = target / config["training"]["materialization"]
    completed_path = target / config["training"]["completed"]
    materialization = load_json(materialization_path)
    completed = load_json(completed_path)
    require_equal(
        materialization.get("schema"),
        config["training"]["materialization_schema"],
        "training materialization schema",
    )
    require_equal(materialization.get("status"), "PASSED", "materialization status")
    for payload, label in (
        (materialization, "materialization"),
        (completed, "completion"),
    ):
        require_equal(payload.get("building_id"), building_id, f"{label} building")
        require_equal(payload.get("arm"), arm, f"{label} arm")
        require_equal(payload.get("replicate"), run, f"{label} replicate")
    require_equal(
        completed.get("schema"),
        config["training"]["completed_schema"],
        "training completion schema",
    )
    require_equal(completed.get("job_key"), job_key(building_id, arm, run), "training job key")
    require_equal(completed.get("return_code"), 0, "training return code")

    materialization_sha = sha256_file(materialization_path)
    retry_output = _validate_infrastructure_retry_chain(
        completed=completed,
        target=target,
        materialization_path=materialization_path,
        materialization_sha256=materialization_sha,
        failed_path=failed,
        expected_job_key=job_key(building_id, arm, run),
        training_contract=config["training"],
        repo=repo,
    )
    if (failed.exists() or failed.is_symlink()) and retry_output is None:
        raise ReadoutError(
            f"training job has failed receipt; readout forbidden: {failed}"
        )
    expected_training_root = retry_output or target

    completion = completed.get("training_completion")
    if not isinstance(completion, Mapping):
        raise ReadoutError("training_completion object is missing")
    require_equal(completion.get("status"), "PASSED", "training completion status")
    maximum = int(config["training"]["required_optimizer_updates"])
    require_equal(
        completion.get("completed_optimizer_updates"),
        maximum,
        "completed optimizer updates",
    )
    full_state_checkpoint = repo_path(completion["checkpoint"], repo=repo)
    expected_full_state_checkpoint = (
        expected_training_root / config["training"]["full_state_checkpoint_relpath"]
    ).resolve()
    require_equal(
        full_state_checkpoint,
        expected_full_state_checkpoint,
        "30k full-state checkpoint path",
    )
    full_state_checkpoint_sha = verify_hash(
        full_state_checkpoint,
        completion["checkpoint_sha256"],
        "30k full-state checkpoint",
    )
    checkpoint = repo_path(completion["final_checkpoint"], repo=repo)
    expected_checkpoint = (
        expected_training_root / config["training"]["extract_checkpoint_relpath"]
    ).resolve()
    require_equal(checkpoint, expected_checkpoint, "extract checkpoint path")
    checkpoint_sha = verify_hash(
        checkpoint,
        completion["final_checkpoint_sha256"],
        "extract final checkpoint",
    )
    full_state_path = repo_path(completion["full_state_manifest"], repo=repo)
    expected_full_state = (
        expected_training_root / config["training"]["full_state_relpath"]
    ).resolve()
    require_equal(full_state_path, expected_full_state, "full-state manifest path")
    full_state_sha = verify_hash(
        full_state_path,
        completion["full_state_manifest_sha256"],
        "full-state manifest",
    )
    full_state = load_json(full_state_path)
    require_equal(
        full_state.get("schema"),
        config["training"]["full_state_schema"],
        "full-state schema",
    )
    require_equal(full_state.get("process_completed"), True, "full-state process completion")
    require_equal(
        full_state.get("process_completed_steps"),
        maximum,
        "full-state optimizer updates",
    )

    completed_materialization = completed.get("materialization")
    if not isinstance(completed_materialization, Mapping):
        raise ReadoutError("completion materialization binding is missing")
    require_equal(
        repo_path(completed_materialization["path"], repo=repo),
        materialization_path.resolve(),
        "completion materialization path",
    )
    materialization_sha = verify_hash(
        materialization_path,
        completed_materialization["sha256"],
        "training materialization",
    )

    preprocess = materialization.get("preprocess")
    if not isinstance(preprocess, Mapping):
        raise ReadoutError("materialization preprocess binding is missing")
    data_root = repo_path(preprocess["data_root"], repo=repo)
    for name in ("cameras.bin", "images.bin", "points3D.bin"):
        require_regular(
            data_root / "sparse" / "0" / name,
            f"training data root sparse/{name}",
        )
    view_roles = materialization.get("view_roles")
    if not isinstance(view_roles, Mapping):
        raise ReadoutError("training view role binding is missing")
    train_views = list(view_roles.get("train_views") or [])
    if not train_views:
        raise ReadoutError("training job has no train views")
    for name in train_views:
        if not isinstance(name, str) or not name:
            raise ReadoutError("training view list contains a non-string name")
        require_safe_input_file(
            data_root / "images" / name,
            f"training image {name}",
            repo=repo,
        )
    supervision_index = repo_path(preprocess["supervision_index"], repo=repo)
    require_regular(supervision_index, "preprocess supervision index")

    return {
        "job_dir": target,
        "job_key": job_key(building_id, arm, run),
        "materialization": materialization,
        "materialization_path": materialization_path,
        "materialization_sha256": materialization_sha,
        "completed": completed,
        "completed_path": completed_path,
        "completed_sha256": sha256_file(completed_path),
        "checkpoint": checkpoint,
        "checkpoint_sha256": checkpoint_sha,
        "full_state_checkpoint": full_state_checkpoint,
        "full_state_checkpoint_sha256": full_state_checkpoint_sha,
        "full_state_manifest": full_state_path,
        "full_state_manifest_sha256": full_state_sha,
        "data_root": data_root,
        "supervision_index": supervision_index,
        "train_views": train_views,
    }


def p0prime_binding(
    config: Mapping[str, Any],
    building_id: str,
    *,
    repo: Path = REPO,
) -> dict[str, Any]:
    scores = repo_path(config["p0prime"]["scores_csv"], repo=repo)
    rows = [
        row for row in read_csv(scores) if row.get("building_id") == building_id
    ]
    if len(rows) != 1:
        raise ReadoutError(
            f"P0-prime score row is not unique or not ready: {building_id}"
        )
    row = rows[0]
    require_equal(
        row.get("status"),
        config["p0prime"]["required_score_status"],
        "P0-prime score status",
    )
    complete_root = repo_path(
        config["p0prime"]["job_template"].format(building_id=building_id),
        repo=repo,
    )
    complete_path = complete_root / config["p0prime"]["complete_receipt"]
    complete = load_json(complete_path)
    require_equal(complete.get("state"), "COMPLETE", "P0-prime completion state")
    require_equal(complete.get("building_id"), building_id, "P0-prime completion building")
    return {
        "scores_csv": scores,
        "scores_csv_sha256": sha256_file(scores),
        "row": row,
        "row_sha256": sha256_bytes(canonical_json(row)),
        "complete": complete,
        "complete_path": complete_path,
        "complete_sha256": sha256_file(complete_path),
    }


def ensure_not_failed(job: Path, *, repo: Path = REPO) -> None:
    recovered_failure = job / "failed_after_infrastructure_retry.json"
    if recovered_failure.exists() or recovered_failure.is_symlink():
        raise ReadoutError(
            f"job failed after the approved infrastructure retry: {recovered_failure}"
        )
    failed = job / "failed.json"
    if failed.exists() or failed.is_symlink():
        if _validate_adopted_extract_retry(
            job, repo=repo
        ) or _validate_adopted_extract_recovery2(job, repo=repo):
            return
        raise ReadoutError(
            f"job has failed receipt; retries are forbidden: {failed}"
        )


def _run_git(repo: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", "-c", f"safe.directory={repo}", *args],
        cwd=repo,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if completed.returncode != 0:
        raise ReadoutError(
            f"git command failed ({' '.join(args)}): {completed.stderr.strip()}"
        )
    return completed.stdout.strip()


def validate_readout_retry_policy(
    config: Mapping[str, Any],
    policy_path: Path,
    *,
    repo: Path = REPO,
) -> tuple[dict[str, Any], str]:
    path = policy_path if policy_path.is_absolute() else repo_path(policy_path, repo=repo)
    policy = load_json(path)
    digest = sha256_file(path)
    require_equal(policy.get("schema"), READOUT_RETRY_POLICY_SCHEMA, "readout retry policy schema")
    require_equal(policy.get("status"), "APPROVED", "readout retry policy status")
    require_equal(policy.get("run_id"), config.get("run_id"), "readout retry run ID")
    require_equal(policy.get("approved_by"), "김휘영", "readout retry approver")
    require_equal(
        policy.get("retry_kind"),
        "GSPLAT_JIT_CACHE_PERMISSION_PREOUTPUT",
        "readout retry kind",
    )
    require_equal(policy.get("stage"), "readout", "readout retry stage")
    require_equal(policy.get("maximum_retries_per_job"), 1, "readout retry maximum")
    require_equal(
        policy.get("attempt_directory"),
        READOUT_RETRY_ATTEMPT_DIRECTORY,
        "readout retry attempt directory",
    )
    require_equal(
        policy.get("allowed_invocation_differences"),
        ["output", "argv_value_after_--out"],
        "readout retry invocation difference allowlist",
    )
    head = policy.get("required_pre_retry_head")
    if not isinstance(head, str) or re.fullmatch(r"[0-9a-f]{40}", head) is None:
        raise ReadoutError("readout retry pre-retry HEAD is invalid")
    require_equal(policy.get("required_retry_commit_distance"), 1, "readout retry commit distance")
    allowed_paths = policy.get("allowed_retry_commit_paths")
    if not isinstance(allowed_paths, list) or not allowed_paths or len(set(allowed_paths)) != len(allowed_paths):
        raise ReadoutError("readout retry implementation path allowlist is invalid")
    environment = policy.get("writable_environment")
    if not isinstance(environment, Mapping) or set(environment) != WRITABLE_ENVIRONMENT_KEYS:
        raise ReadoutError("readout retry writable environment is incomplete")
    historical_environment = writable_readout_environment(
        config,
        repo=repo,
        declared_paths=environment,
    )
    require_equal(
        historical_environment["host_paths"],
        dict(environment),
        "readout retry policy writable environment",
    )
    required = policy.get("required_failure")
    if not isinstance(required, Mapping):
        raise ReadoutError("readout retry required failure is missing")
    pinned = required.get("artifact_sha256")
    required_artifacts = {"materialization", "invocation", "started", "log", "failed"}
    if not isinstance(pinned, Mapping) or set(pinned) != required_artifacts:
        raise ReadoutError("readout retry original artifact SHA256 binding is incomplete")
    for label, value in pinned.items():
        if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None:
            raise ReadoutError(f"invalid pinned readout retry SHA256 for {label}")
    absent = required.get("required_absent_outputs")
    if not isinstance(absent, list) or not absent:
        raise ReadoutError("readout retry absent-output contract is missing")
    for value in absent:
        candidate = Path(str(value))
        if candidate.is_absolute() or ".." in candidate.parts or not candidate.parts:
            raise ReadoutError(f"unsafe absent-output path in retry policy: {value!r}")
    preservation = policy.get("preservation_contract")
    required_preservation = {
        "original_materialization_immutable",
        "original_invocation_immutable",
        "original_started_receipt_immutable",
        "original_failed_receipt_immutable",
        "original_log_immutable",
        "retry_receipts_exclusive",
        "retry_output_namespace_separate",
    }
    if not isinstance(preservation, Mapping) or not all(
        preservation.get(key) is True for key in required_preservation
    ):
        raise ReadoutError("readout retry preservation contract is incomplete")
    counter = policy.get("counter_contract")
    if not isinstance(counter, Mapping):
        raise ReadoutError("readout retry counter contract is missing")
    require_equal(counter.get("retry_is_same_authorized_readout"), True, "readout retry counter identity")
    require_equal(counter.get("second_readout_started_receipt_forbidden"), True, "readout retry second STARTED")
    require_equal(counter.get("readout_runs_started_increment"), 0, "readout retry counter increment")
    return {
        **dict(policy),
        "path": repo_relative(path, repo=repo),
        "sha256": digest,
        "writable_environment": dict(environment),
        "required_failure": {
            **dict(required),
            "artifact_sha256": dict(pinned),
            "required_absent_outputs": list(absent),
        },
        "preservation_contract": dict(preservation),
        "counter_contract": dict(counter),
        "allowed_retry_commit_paths": list(allowed_paths),
    }, digest


def _validate_readout_retry_git_state(
    repo: Path, policy: Mapping[str, Any]
) -> dict[str, Any]:
    branch = _run_git(repo, "branch", "--show-current")
    require_equal(branch, "exp/fusion-w1", "readout retry branch")
    head = _run_git(repo, "rev-parse", "HEAD")
    base = str(policy["required_pre_retry_head"])
    _run_git(repo, "merge-base", "--is-ancestor", base, head)
    distance_text = _run_git(repo, "rev-list", "--count", f"{base}..{head}")
    try:
        distance = int(distance_text)
    except ValueError as exc:
        raise ReadoutError(f"invalid readout retry commit distance: {distance_text!r}") from exc
    require_equal(distance, 1, "readout retry commit distance")
    changed = sorted(
        line for line in _run_git(repo, "diff", "--name-only", base, head).splitlines() if line
    )
    require_equal(
        changed,
        sorted(str(value) for value in policy["allowed_retry_commit_paths"]),
        "readout retry implementation commit paths",
    )
    porcelain = _run_git(repo, "status", "--porcelain=v1", "--untracked-files=all")
    allowed_runtime_prefix = "phases/p2-gsjso/runs/fusion_w1/20260724_fusion_w1/"
    unexpected: list[str] = []
    allowed_untracked: list[str] = []
    for line in porcelain.splitlines():
        if not line:
            continue
        status = line[:2]
        path = line[3:]
        if status == "??" and path.startswith(allowed_runtime_prefix):
            allowed_untracked.append(path)
        else:
            unexpected.append(line)
    if unexpected:
        raise ReadoutError(
            "readout retry worktree has tracked or non-runtime changes: "
            + "; ".join(unexpected[:20])
        )
    return {
        "branch": branch,
        "pre_retry_head": base,
        "retry_head": head,
        "pre_retry_head_is_ancestor": True,
        "commit_distance": distance,
        "changed_paths": changed,
        "tracked_changes": 0,
        "allowed_runtime_untracked_count": len(allowed_untracked),
    }


def _readout_job_file_snapshot(job: Path) -> dict[str, str]:
    snapshot: dict[str, str] = {}
    if not job.is_dir() or job.is_symlink():
        raise ReadoutError(f"readout job directory is invalid: {job}")
    for path in sorted(job.rglob("*")):
        relative = path.relative_to(job)
        if relative.parts and relative.parts[0] == READOUT_RETRY_ATTEMPT_DIRECTORY:
            continue
        if relative == Path("extract_receipt.json"):
            continue
        if path.is_symlink():
            raise ReadoutError(f"readout retry source contains a symlink: {path}")
        if path.is_file():
            snapshot[str(relative)] = sha256_file(path)
    return snapshot


def _snapshot_sha256(snapshot: Mapping[str, str]) -> str:
    return sha256_bytes(canonical_json(dict(sorted(snapshot.items()))))


def _require_original_snapshot_unchanged(
    job: Path, expected: Mapping[str, str]
) -> None:
    for relative, digest in expected.items():
        path = job / relative
        require_regular(path, f"original readout snapshot {relative}")
        require_equal(
            sha256_file(path), digest, f"original readout snapshot {relative} SHA256"
        )


def _require_pre_adoption_snapshot_exact(
    job: Path, expected: Mapping[str, str]
) -> None:
    """Allow no new root-job files before the retry is adopted."""

    observed = _readout_job_file_snapshot(job)
    require_equal(
        observed,
        dict(expected),
        "pre-adoption original readout file inventory",
    )


def _resolve_retry_output_before_receipt(
    invocation: Mapping[str, Any],
    attempt: Path,
    *,
    repo: Path = REPO,
) -> Path:
    """Validate the fixed retry namespace without following a symlink first."""

    raw_value = invocation.get("output")
    if not isinstance(raw_value, str) or not raw_value:
        raise ReadoutError("readout retry output path is invalid")
    raw = Path(raw_value)
    if raw.is_absolute() or ".." in raw.parts:
        raise ReadoutError(f"unsafe readout retry output path: {raw_value!r}")
    repository = repo.resolve()
    try:
        attempt_relative = attempt.relative_to(repository)
    except ValueError as exc:
        raise ReadoutError("readout retry attempt escapes repository") from exc
    expected = attempt_relative / "pointcloud" / "readout.npz"
    require_equal(raw, expected, "readout retry fixed output namespace")
    cursor = repository
    for part in raw.parts:
        cursor = cursor / part
        if cursor.is_symlink():
            raise ReadoutError(
                f"readout retry output path contains a symlink: {cursor}"
            )
    return repo_path(raw, repo=repo)


def _validate_retry_invocation_difference(
    original: Mapping[str, Any],
    retry: Mapping[str, Any],
    *,
    retry_output: str,
) -> None:
    expected_new_keys = {
        "original_invocation",
        "retry_started",
        "environment",
        "allowed_differences",
    }
    require_equal(
        set(retry) - set(original),
        expected_new_keys,
        "readout retry invocation provenance keys",
    )
    for key in set(original) - {"schema", "created_at", "output", "argv"}:
        require_equal(retry.get(key), original.get(key), f"readout retry invocation {key}")
    require_equal(retry.get("schema"), READOUT_RETRY_INVOCATION_SCHEMA, "readout retry invocation schema")
    require_equal(retry.get("output"), retry_output, "readout retry invocation output")
    original_argv = original.get("argv")
    retry_argv = retry.get("argv")
    if not isinstance(original_argv, list) or not isinstance(retry_argv, list):
        raise ReadoutError("readout retry invocation argv is invalid")
    require_equal(
        retry_argv,
        _replace_only_output(original_argv, str(original.get("output")), retry_output),
        "readout retry argv output-only difference",
    )
    require_equal(
        retry.get("allowed_differences"),
        ["output", "argv_value_after_--out"],
        "readout retry invocation difference declaration",
    )


def _verify_preoutput_cache_failure(
    config: Mapping[str, Any],
    policy: Mapping[str, Any],
    building_id: str,
    arm: str,
    run: str,
    *,
    repo: Path = REPO,
) -> dict[str, Any]:
    key = job_key(building_id, arm, run)
    require_equal(key, policy.get("job_key"), "readout retry job key")
    job = job_dir(config, building_id, arm, run, repo=repo)
    paths = {
        "materialization": job / "materialization.json",
        "invocation": job / "extract_invocation.json",
        "started": job / "readout_started.json",
        "log": job / "extract.stdout.log",
        "failed": job / "failed.json",
    }
    pinned = policy["required_failure"]["artifact_sha256"]
    payloads: dict[str, dict[str, Any]] = {}
    for label, path in paths.items():
        require_regular(path, f"original readout {label}")
        require_equal(sha256_file(path), pinned[label], f"original readout {label} SHA256")
        if label != "log":
            payloads[label] = load_json(path)
    require_equal(payloads["materialization"].get("schema"), MATERIALIZATION_SCHEMA, "original readout materialization schema")
    require_equal(payloads["materialization"].get("job_key"), key, "original readout materialization job")
    require_equal(payloads["invocation"].get("schema"), "jointbuildgs.fusion_w1.extract_invocation.v1", "original extract invocation schema")
    require_equal(payloads["invocation"].get("state"), "AUTHORIZED", "original extract invocation state")
    require_equal(payloads["invocation"].get("job_key"), key, "original extract invocation job")
    require_equal(payloads["invocation"].get("retry_allowed"), False, "original invocation retry flag")
    require_equal(payloads["started"].get("schema"), JOB_SCHEMA, "original readout STARTED schema")
    require_equal(payloads["started"].get("state"), "STARTED", "original readout STARTED state")
    require_equal(payloads["started"].get("stage"), "readout", "original readout STARTED stage")
    require_equal(payloads["started"].get("job_key"), key, "original readout STARTED job")
    require_equal(payloads["started"].get("retry_allowed"), False, "original STARTED retry flag")
    started_invocation = payloads["started"].get("invocation")
    if not isinstance(started_invocation, Mapping):
        raise ReadoutError("original readout STARTED invocation binding is missing")
    require_equal(started_invocation.get("path"), repo_relative(paths["invocation"], repo=repo), "original STARTED invocation path")
    require_equal(started_invocation.get("sha256"), pinned["invocation"], "original STARTED invocation SHA256")
    require_equal(payloads["failed"].get("schema"), "jointbuildgs.fusion_w1.readout_failure.v1", "original readout failure schema")
    require_equal(payloads["failed"].get("state"), "FAILED", "original readout failure state")
    require_equal(payloads["failed"].get("stage"), "readout", "original readout failure stage")
    require_equal(payloads["failed"].get("job_key"), key, "original readout failure job")
    require_equal(payloads["failed"].get("retry_allowed"), False, "original failure retry flag")
    log_text = paths["log"].read_text(encoding="utf-8")
    for marker in policy["required_failure"].get("log_markers", []):
        if marker not in log_text:
            raise ReadoutError(f"required readout cache-failure marker is absent: {marker}")
    for relative in policy["required_failure"]["required_absent_outputs"]:
        path = job / str(relative)
        if path.exists() or path.is_symlink():
            raise ReadoutError(f"pre-output retry found forbidden output: {path}")
    pointcloud = job / "pointcloud"
    if pointcloud.exists() and any(pointcloud.iterdir()):
        raise ReadoutError("pre-output retry found an unexpected point-cloud artifact")
    attempt = job / READOUT_RETRY_ATTEMPT_DIRECTORY
    if attempt.exists() or attempt.is_symlink():
        raise ReadoutError("the one permitted readout infrastructure retry was already claimed")
    counters = reconcile_runtime_counters(config, repo=repo)
    for name, value in policy["required_failure"]["required_counter_values"].items():
        require_equal(counters.get(name), value, f"pre-output retry counter {name}")
    snapshot = _readout_job_file_snapshot(job)
    return {
        "job": job,
        "paths": paths,
        "payloads": payloads,
        "snapshot": snapshot,
        "snapshot_sha256": _snapshot_sha256(snapshot),
    }


def _replace_only_output(argv: Sequence[str], original: str, replacement: str) -> list[str]:
    values = list(argv)
    positions = [index for index, value in enumerate(values) if value == "--out"]
    if len(positions) != 1:
        raise ReadoutError("extract argv must contain exactly one --out option")
    index = positions[0]
    if index + 1 >= len(values):
        raise ReadoutError("extract argv --out value is missing")
    require_equal(values[index + 1], original, "original extract argv output")
    values[index + 1] = replacement
    return values


def prepare_extract_infra_retry(
    config: Mapping[str, Any],
    policy_path: Path,
    building_id: str,
    arm: str,
    run: str,
    *,
    repo: Path = REPO,
    validate_git: bool = True,
) -> dict[str, Any]:
    policy, _ = validate_readout_retry_policy(config, policy_path, repo=repo)
    git = _validate_readout_retry_git_state(repo, policy) if validate_git else {"validation": "TEST_BYPASS"}
    verified = _verify_preoutput_cache_failure(config, policy, building_id, arm, run, repo=repo)
    job = verified["job"]
    attempt = job / READOUT_RETRY_ATTEMPT_DIRECTORY
    environment = writable_readout_environment(
        config,
        repo=repo,
        create=True,
        declared_paths=policy["writable_environment"],
    )
    require_equal(environment["host_paths"], policy["writable_environment"], "retry policy/environment paths")
    started_path = attempt / "retry_started.json"
    original_refs = {
        label: {"path": repo_relative(path, repo=repo), "sha256": sha256_file(path)}
        for label, path in verified["paths"].items()
    }
    started = {
        "schema": READOUT_RETRY_STARTED_SCHEMA,
        "state": "STARTED",
        "created_at": now_iso(),
        "run_id": config["run_id"],
        "job_key": job_key(building_id, arm, run),
        "retry_key": f"{job_key(building_id, arm, run)}/{READOUT_RETRY_ATTEMPT_DIRECTORY}",
        "policy": policy,
        "git": git,
        "original_artifacts": original_refs,
        "original_file_snapshot": verified["snapshot"],
        "original_file_snapshot_sha256": verified["snapshot_sha256"],
        "environment": environment,
        "counter_increment": 0,
        "claim_mode": "atomic_O_EXCL_one_time_preoutput_infrastructure_retry",
    }
    exclusive_json(started_path, started)
    original = verified["payloads"]["invocation"]
    output = attempt / "pointcloud" / "readout.npz"
    output_rel = repo_relative(output, repo=repo)
    original_argv = original.get("argv")
    if not isinstance(original_argv, list) or not all(isinstance(value, str) for value in original_argv):
        raise ReadoutError("original extract argv is invalid")
    argv = _replace_only_output(original_argv, str(original["output"]), output_rel)
    invocation = {
        **dict(original),
        "schema": READOUT_RETRY_INVOCATION_SCHEMA,
        "created_at": now_iso(),
        "output": output_rel,
        "argv": argv,
        "original_invocation": original_refs["invocation"],
        "retry_started": {
            "path": repo_relative(started_path, repo=repo),
            "sha256": sha256_file(started_path),
        },
        "environment": environment,
        "allowed_differences": ["output", "argv_value_after_--out"],
        "retry_allowed": False,
    }
    invocation_path = attempt / "extract_invocation.json"
    _validate_retry_invocation_difference(
        original, invocation, retry_output=output_rel
    )
    exclusive_json(invocation_path, invocation)
    return {
        "status": "AUTHORIZED",
        "attempt": repo_relative(attempt, repo=repo),
        "retry_started": repo_relative(started_path, repo=repo),
        "retry_invocation": repo_relative(invocation_path, repo=repo),
        "retry_output": output_rel,
        "environment": environment,
    }


def _load_active_extract_retry(
    config: Mapping[str, Any],
    building_id: str,
    arm: str,
    run: str,
    *,
    repo: Path = REPO,
    allow_completed: bool = False,
) -> tuple[Path, dict[str, Any], Path, dict[str, Any]]:
    job = job_dir(config, building_id, arm, run, repo=repo)
    attempt = job / READOUT_RETRY_ATTEMPT_DIRECTORY
    started_path = attempt / "retry_started.json"
    invocation_path = attempt / "extract_invocation.json"
    started = load_receipt(started_path, schema=READOUT_RETRY_STARTED_SCHEMA, state="STARTED")
    invocation = load_receipt(invocation_path, schema=READOUT_RETRY_INVOCATION_SCHEMA, state="AUTHORIZED")
    key = job_key(building_id, arm, run)
    require_equal(started.get("job_key"), key, "readout retry STARTED job")
    require_equal(invocation.get("job_key"), key, "readout retry invocation job")
    binding = invocation.get("retry_started")
    if not isinstance(binding, Mapping):
        raise ReadoutError("readout retry invocation/STARTED binding is missing")
    require_equal(binding.get("path"), repo_relative(started_path, repo=repo), "retry STARTED path")
    require_equal(binding.get("sha256"), sha256_file(started_path), "retry STARTED SHA256")
    policy = started.get("policy")
    if not isinstance(policy, Mapping):
        raise ReadoutError("readout retry policy binding is missing")
    policy_path = repo_path(str(policy.get("path")), repo=repo)
    verified_policy, _ = validate_readout_retry_policy(config, policy_path, repo=repo)
    require_equal(dict(policy), verified_policy, "readout retry policy binding")
    original_snapshot = started.get("original_file_snapshot")
    if not isinstance(original_snapshot, Mapping):
        raise ReadoutError("readout retry original snapshot is missing")
    _require_original_snapshot_unchanged(job, dict(original_snapshot))
    failed_retry = attempt / "retry_failed.json"
    if failed_retry.exists() or failed_retry.is_symlink():
        raise ReadoutError("readout infrastructure retry already failed")
    completed_retry = attempt / "retry_completed.json"
    if not allow_completed and (completed_retry.exists() or completed_retry.is_symlink()):
        raise ReadoutError("readout infrastructure retry already completed")
    environment = writable_readout_environment(
        config,
        repo=repo,
        create=False,
        require_ready=True,
        declared_paths=verified_policy["writable_environment"],
    )
    require_equal(invocation.get("environment"), environment, "readout retry invocation environment")
    original_invocation = load_json(job / "extract_invocation.json")
    _validate_retry_invocation_difference(
        original_invocation,
        invocation,
        retry_output=str(invocation.get("output")),
    )
    return attempt, started, invocation_path, invocation


def retry_extract_argv(
    config: Mapping[str, Any], building_id: str, arm: str, run: str, *, repo: Path = REPO
) -> list[str]:
    _, _, _, invocation = _load_active_extract_retry(config, building_id, arm, run, repo=repo)
    argv = invocation.get("argv")
    if not isinstance(argv, list) or not all(isinstance(value, str) and value for value in argv):
        raise ReadoutError("readout retry argv is invalid")
    return list(argv)


def retry_extract_environment(
    config: Mapping[str, Any], building_id: str, arm: str, run: str, *, repo: Path = REPO
) -> list[str]:
    _, _, _, invocation = _load_active_extract_retry(config, building_id, arm, run, repo=repo)
    environment = invocation["environment"]["container_values"]
    return [f"{key}={environment[key]}" for key in sorted(WRITABLE_ENVIRONMENT_KEYS)]


def record_extract_infra_retry_failure(
    config: Mapping[str, Any],
    building_id: str,
    arm: str,
    run: str,
    *,
    message: str,
    detail: str = "",
    repo: Path = REPO,
) -> dict[str, Any]:
    job = job_dir(config, building_id, arm, run, repo=repo)
    if (job / "extract_receipt.json").exists() or (
        job / "extract_receipt.json"
    ).is_symlink():
        try:
            already_adopted = _validate_adopted_extract_retry(job, repo=repo)
        except ReadoutError:
            already_adopted = False
        if already_adopted:
            raise ReadoutError(
                "readout infrastructure retry was already successfully adopted"
            )
    attempt, started, invocation_path, _ = _load_active_extract_retry(
        config, building_id, arm, run, repo=repo, allow_completed=True
    )
    payload = {
        "schema": READOUT_RETRY_FAILED_SCHEMA,
        "state": "FAILED",
        "created_at": now_iso(),
        "run_id": config["run_id"],
        "job_key": job_key(building_id, arm, run),
        "retry_key": started["retry_key"],
        "message": message,
        "detail": detail[-12000:],
        "retry_started": {"path": repo_relative(attempt / "retry_started.json", repo=repo), "sha256": sha256_file(attempt / "retry_started.json")},
        "retry_invocation": {"path": repo_relative(invocation_path, repo=repo), "sha256": sha256_file(invocation_path)},
        "partial_outputs_preserved": True,
        "another_retry_allowed": False,
        "counter_increment": 0,
    }
    exclusive_json(attempt / "retry_failed.json", payload)
    return payload


def _validate_retry_completion_chain(
    *,
    attempt: Path,
    started: Mapping[str, Any],
    invocation_path: Path,
    invocation: Mapping[str, Any],
    attempt_receipt_path: Path,
    attempt_receipt: Mapping[str, Any],
    completed_path: Path,
    completed: Mapping[str, Any],
    pointcloud: Mapping[str, Any],
    repo: Path = REPO,
) -> None:
    """Pin every link in the successful retry chain before root adoption."""

    key = str(started.get("job_key"))
    retry_key = f"{key}/{READOUT_RETRY_ATTEMPT_DIRECTORY}"
    require_equal(started.get("retry_key"), retry_key, "readout retry STARTED key")
    require_equal(invocation.get("job_key"), key, "readout retry invocation job")
    started_binding = {
        "path": repo_relative(attempt / "retry_started.json", repo=repo),
        "sha256": sha256_file(attempt / "retry_started.json"),
    }
    invocation_binding = {
        "path": repo_relative(invocation_path, repo=repo),
        "sha256": sha256_file(invocation_path),
    }
    attempt_receipt_binding = {
        "path": repo_relative(attempt_receipt_path, repo=repo),
        "sha256": sha256_file(attempt_receipt_path),
    }
    require_equal(
        invocation.get("retry_started"),
        started_binding,
        "readout retry invocation STARTED binding",
    )
    require_equal(attempt_receipt.get("job_key"), key, "retry extract receipt job")
    require_equal(
        attempt_receipt.get("retry_key"), retry_key, "retry extract receipt key"
    )
    require_equal(
        attempt_receipt.get("invocation"),
        invocation_binding,
        "retry extract receipt invocation binding",
    )
    require_equal(
        attempt_receipt.get("pointcloud"),
        dict(pointcloud),
        "retry extract receipt point cloud",
    )
    require_equal(
        attempt_receipt.get("counter_increment"),
        0,
        "retry extract receipt counter increment",
    )
    require_equal(completed.get("job_key"), key, "completed readout retry job")
    require_equal(
        completed.get("retry_key"), retry_key, "completed readout retry key"
    )
    require_equal(completed.get("return_code"), 0, "completed readout retry return code")
    require_equal(
        completed.get("retry_started"),
        started_binding,
        "completed readout retry STARTED binding",
    )
    require_equal(
        completed.get("retry_invocation"),
        invocation_binding,
        "completed readout retry invocation binding",
    )
    require_equal(
        completed.get("extract_receipt"),
        attempt_receipt_binding,
        "completed readout retry extract receipt binding",
    )
    require_equal(
        completed.get("pointcloud"),
        dict(pointcloud),
        "completed readout retry point cloud",
    )
    require_equal(
        completed.get("original_file_snapshot_sha256"),
        started.get("original_file_snapshot_sha256"),
        "completed readout retry original snapshot SHA256",
    )
    require_equal(
        completed.get("counter_increment"),
        0,
        "completed readout retry counter increment",
    )
    require_regular(completed_path, "completed readout retry receipt")


def accept_extract_infra_retry(
    config: Mapping[str, Any],
    building_id: str,
    arm: str,
    run: str,
    *,
    wall_seconds: float,
    repo: Path = REPO,
) -> dict[str, Any]:
    job = job_dir(config, building_id, arm, run, repo=repo)
    root_receipt = job / "extract_receipt.json"
    if root_receipt.exists() or root_receipt.is_symlink():
        payload = load_receipt(root_receipt, schema="jointbuildgs.fusion_w1.extract_receipt.v1", state="COMPLETE")
        if not _validate_adopted_extract_retry(job, repo=repo):
            raise ReadoutError("existing root extract receipt is not an adopted retry")
        return payload
    attempt, started, invocation_path, invocation = _load_active_extract_retry(
        config, building_id, arm, run, repo=repo, allow_completed=True
    )
    checkpoint = repo_path(invocation["training_checkpoint"]["path"], repo=repo)
    verify_hash(checkpoint, invocation["training_checkpoint"]["sha256"], "checkpoint before accepting retry readout")
    output = _resolve_retry_output_before_receipt(
        invocation, attempt, repo=repo
    )
    stats = inspect_npz(output, config, repo=repo)
    _require_pre_adoption_snapshot_exact(job, started["original_file_snapshot"])
    attempt_receipt_path = attempt / "extract_receipt.json"
    if attempt_receipt_path.exists():
        attempt_receipt = load_receipt(
            attempt_receipt_path,
            schema="jointbuildgs.fusion_w1.extract_infra_retry_receipt.v1",
            state="COMPLETE",
        )
        require_equal(attempt_receipt.get("pointcloud"), stats, "retry point-cloud receipt")
    else:
        attempt_receipt = {
            "schema": "jointbuildgs.fusion_w1.extract_infra_retry_receipt.v1",
            "state": "COMPLETE",
            "created_at": now_iso(),
            "job_key": job_key(building_id, arm, run),
            "retry_key": started["retry_key"],
            "invocation": {"path": repo_relative(invocation_path, repo=repo), "sha256": sha256_file(invocation_path)},
            "pointcloud": stats,
            "wall_seconds": float(wall_seconds),
            "counter_increment": 0,
        }
        exclusive_json(attempt_receipt_path, attempt_receipt)
    completed_path = attempt / "retry_completed.json"
    if completed_path.exists():
        completed = load_receipt(completed_path, schema=READOUT_RETRY_COMPLETED_SCHEMA, state="COMPLETE")
    else:
        completed = {
            "schema": READOUT_RETRY_COMPLETED_SCHEMA,
            "state": "COMPLETE",
            "completed_at": now_iso(),
            "run_id": config["run_id"],
            "job_key": job_key(building_id, arm, run),
            "retry_key": started["retry_key"],
            "return_code": 0,
            "retry_started": {"path": repo_relative(attempt / "retry_started.json", repo=repo), "sha256": sha256_file(attempt / "retry_started.json")},
            "retry_invocation": {"path": repo_relative(invocation_path, repo=repo), "sha256": sha256_file(invocation_path)},
            "extract_receipt": {"path": repo_relative(attempt_receipt_path, repo=repo), "sha256": sha256_file(attempt_receipt_path)},
            "pointcloud": stats,
            "original_file_snapshot_sha256": started["original_file_snapshot_sha256"],
            "counter_increment": 0,
        }
        exclusive_json(completed_path, completed)
    _validate_retry_completion_chain(
        attempt=attempt,
        started=started,
        invocation_path=invocation_path,
        invocation=invocation,
        attempt_receipt_path=attempt_receipt_path,
        attempt_receipt=attempt_receipt,
        completed_path=completed_path,
        completed=completed,
        pointcloud=stats,
        repo=repo,
    )
    root = {
        "schema": "jointbuildgs.fusion_w1.extract_receipt.v1",
        "state": "COMPLETE",
        "created_at": completed["completed_at"],
        "job_key": job_key(building_id, arm, run),
        "building_id": building_id,
        "arm": arm,
        "replicate": run,
        "invocation": {"path": repo_relative(invocation_path, repo=repo), "sha256": sha256_file(invocation_path)},
        "pointcloud": stats,
        "wall_seconds": float(attempt_receipt["wall_seconds"]),
        "resource_contract": config["resource_lock"],
        "partial_output_accepted": False,
        "infrastructure_retry": {
            "policy": started["policy"],
            "original_artifacts": started["original_artifacts"],
            "retry_started": {"path": repo_relative(attempt / "retry_started.json", repo=repo), "sha256": sha256_file(attempt / "retry_started.json")},
            "retry_invocation": {"path": repo_relative(invocation_path, repo=repo), "sha256": sha256_file(invocation_path)},
            "retry_completed": {"path": repo_relative(completed_path, repo=repo), "sha256": sha256_file(completed_path)},
            "counter_increment": 0,
            "allowed_invocation_differences": ["output", "argv_value_after_--out"],
        },
    }
    exclusive_json(root_receipt, root)
    if not _validate_adopted_extract_retry(job, repo=repo):
        raise ReadoutError("published root extract retry adoption failed validation")
    return root


def _validate_adopted_extract_retry(job: Path, *, repo: Path = REPO) -> bool:
    root_receipt = job / "extract_receipt.json"
    if not root_receipt.is_file() or root_receipt.is_symlink():
        return False
    root = load_receipt(root_receipt, schema="jointbuildgs.fusion_w1.extract_receipt.v1", state="COMPLETE")
    chain = root.get("infrastructure_retry")
    if not isinstance(chain, Mapping):
        return False
    policy = chain.get("policy")
    if not isinstance(policy, Mapping):
        raise ReadoutError("adopted readout retry policy binding is missing")
    require_equal(policy.get("schema"), READOUT_RETRY_POLICY_SCHEMA, "adopted readout retry policy schema")
    policy_path = repo_path(str(policy.get("path")), repo=repo)
    verify_hash(policy_path, str(policy.get("sha256")), "adopted readout retry policy")
    attempt = job / str(policy.get("attempt_directory"))
    if not attempt.is_dir() or attempt.is_symlink():
        raise ReadoutError("adopted readout retry attempt directory is invalid")
    refs = {
        "retry_started": attempt / "retry_started.json",
        "retry_invocation": attempt / "extract_invocation.json",
        "retry_completed": attempt / "retry_completed.json",
    }
    for label, expected in refs.items():
        binding = chain.get(label)
        if not isinstance(binding, Mapping):
            raise ReadoutError(f"adopted readout {label} binding is missing")
        require_equal(repo_path(str(binding.get("path")), repo=repo), expected.resolve(), f"adopted readout {label} path")
        verify_hash(expected, str(binding.get("sha256")), f"adopted readout {label}")
    started = load_receipt(refs["retry_started"], schema=READOUT_RETRY_STARTED_SCHEMA, state="STARTED")
    invocation = load_receipt(refs["retry_invocation"], schema=READOUT_RETRY_INVOCATION_SCHEMA, state="AUTHORIZED")
    completed = load_receipt(refs["retry_completed"], schema=READOUT_RETRY_COMPLETED_SCHEMA, state="COMPLETE")
    attempt_receipt_path = attempt / "extract_receipt.json"
    attempt_receipt = load_receipt(
        attempt_receipt_path,
        schema="jointbuildgs.fusion_w1.extract_infra_retry_receipt.v1",
        state="COMPLETE",
    )
    pointcloud = completed.get("pointcloud")
    if not isinstance(pointcloud, Mapping):
        raise ReadoutError("completed readout retry point-cloud binding is missing")
    _validate_retry_completion_chain(
        attempt=attempt,
        started=started,
        invocation_path=refs["retry_invocation"],
        invocation=invocation,
        attempt_receipt_path=attempt_receipt_path,
        attempt_receipt=attempt_receipt,
        completed_path=refs["retry_completed"],
        completed=completed,
        pointcloud=pointcloud,
        repo=repo,
    )
    require_equal(chain.get("counter_increment"), 0, "adopted readout retry counter increment")
    original = started.get("original_artifacts")
    pinned = policy.get("required_failure", {}).get("artifact_sha256", {})
    if not isinstance(original, Mapping) or not isinstance(pinned, Mapping):
        raise ReadoutError("adopted readout retry original bindings are missing")
    original_paths = {
        "materialization": job / "materialization.json",
        "invocation": job / "extract_invocation.json",
        "started": job / "readout_started.json",
        "log": job / "extract.stdout.log",
        "failed": job / "failed.json",
    }
    for label, path in original_paths.items():
        binding = original.get(label)
        if not isinstance(binding, Mapping):
            raise ReadoutError(f"adopted original {label} binding is missing")
        require_equal(repo_path(str(binding.get("path")), repo=repo), path.resolve(), f"adopted original {label} path")
        require_equal(binding.get("sha256"), pinned.get(label), f"adopted original {label} pinned SHA256")
        verify_hash(path, str(binding.get("sha256")), f"adopted original readout {label}")
    original_snapshot = started.get("original_file_snapshot")
    if not isinstance(original_snapshot, Mapping):
        raise ReadoutError("adopted original readout snapshot is missing")
    require_equal(
        started.get("original_file_snapshot_sha256"),
        _snapshot_sha256(original_snapshot),
        "adopted original readout snapshot SHA256",
    )
    require_equal(
        started.get("counter_increment"),
        0,
        "adopted readout retry STARTED counter increment",
    )
    _require_original_snapshot_unchanged(job, original_snapshot)
    require_equal(root.get("invocation", {}).get("path"), repo_relative(refs["retry_invocation"], repo=repo), "adopted root invocation path")
    require_equal(root.get("invocation", {}).get("sha256"), sha256_file(refs["retry_invocation"]), "adopted root invocation SHA256")
    root_pointcloud = root.get("pointcloud")
    if not isinstance(root_pointcloud, Mapping):
        raise ReadoutError("adopted retry point-cloud binding is missing")
    output = _resolve_retry_output_before_receipt(
        invocation, attempt, repo=repo
    )
    require_equal(
        root_pointcloud.get("path"),
        repo_relative(output, repo=repo),
        "adopted retry point-cloud path",
    )
    verify_hash(output, str(root_pointcloud.get("sha256")), "adopted retry point cloud")
    require_equal(invocation.get("output"), repo_relative(output, repo=repo), "adopted retry invocation output")
    _validate_retry_invocation_difference(
        load_json(job / "extract_invocation.json"),
        invocation,
        retry_output=repo_relative(output, repo=repo),
    )
    require_equal(completed.get("pointcloud"), dict(root_pointcloud), "adopted retry completed point cloud")
    key = started.get("job_key")
    require_equal(root.get("job_key"), key, "adopted root job key")
    require_equal(root.get("building_id"), invocation.get("building_id"), "adopted root building")
    require_equal(root.get("arm"), invocation.get("arm"), "adopted root arm")
    require_equal(root.get("replicate"), invocation.get("replicate"), "adopted root replicate")
    require_equal(root.get("partial_output_accepted"), False, "adopted root partial output")
    require_equal(chain.get("policy"), started.get("policy"), "adopted retry policy chain")
    require_equal(
        chain.get("original_artifacts"),
        started.get("original_artifacts"),
        "adopted retry original artifact chain",
    )
    require_equal(
        chain.get("allowed_invocation_differences"),
        ["output", "argv_value_after_--out"],
        "adopted retry invocation difference chain",
    )
    return True


def _cache_inventory(root: Path, *, repo: Path = REPO) -> dict[str, Any]:
    """Hash a regular-file-only cache tree with a stable reviewable format."""

    repository = repo.resolve()
    try:
        relative_root = root.relative_to(repository)
    except ValueError as exc:
        raise ReadoutError(f"cache root is outside repository: {root}") from exc
    cursor = repository
    for part in relative_root.parts:
        cursor = cursor / part
        if cursor.is_symlink():
            raise ReadoutError(f"cache path contains a symlink: {cursor}")
    if not root.is_dir() or root.is_symlink():
        raise ReadoutError(f"cache root is not a regular directory: {root}")
    records: list[dict[str, Any]] = []
    lines: list[str] = []
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise ReadoutError(f"cache tree contains a symlink: {path}")
        if path.is_dir():
            continue
        if not path.is_file():
            raise ReadoutError(f"cache tree contains a non-regular entry: {path}")
        relative = path.relative_to(root).as_posix()
        file_stat = path.stat()
        mode = format(stat.S_IMODE(file_stat.st_mode), "o")
        size = int(file_stat.st_size)
        digest = sha256_file(path)
        records.append(
            {
                "path": relative,
                "mode_octal": mode,
                "size_bytes": size,
                "sha256": digest,
            }
        )
        lines.append(f"{relative}\t{mode}\t{size}\t{digest}\n")
    return {
        "root": repo_relative(root, repo=repo),
        "inventory_format": (
            "relative_path_tab_mode_octal_tab_size_bytes_tab_sha256_newline"
        ),
        "inventory_sha256": sha256_bytes("".join(lines).encode("utf-8")),
        "files_n": len(records),
        "bytes_n": sum(int(record["size_bytes"]) for record in records),
        "files": records,
    }


def _require_cache_inventory(
    observed: Mapping[str, Any], expected: Mapping[str, Any], label: str
) -> None:
    for key in ("root", "inventory_format", "inventory_sha256", "files_n", "bytes_n"):
        require_equal(observed.get(key), expected.get(key), f"{label} {key}")


def _canonical_recovery2_policy_path(policy_path: Path, *, repo: Path) -> Path:
    """Require the one committed policy path without following symlink aliases."""

    repository = repo.resolve()
    expected = repository / READOUT_RECOVERY2_POLICY_RELATIVE
    candidate = policy_path if policy_path.is_absolute() else repository / policy_path
    candidate = Path(os.path.abspath(candidate))
    require_equal(candidate, expected, "canonical recovery2 policy path")
    cursor = repository
    for part in READOUT_RECOVERY2_POLICY_RELATIVE.parts:
        cursor = cursor / part
        if cursor.is_symlink():
            raise ReadoutError(f"recovery2 policy path contains a symlink: {cursor}")
    require_regular(expected, "canonical recovery2 policy")
    return expected


def validate_readout_recovery2_policy(
    config: Mapping[str, Any],
    policy_path: Path,
    *,
    repo: Path = REPO,
) -> tuple[dict[str, Any], str]:
    path = _canonical_recovery2_policy_path(policy_path, repo=repo)
    policy = load_json(path)
    digest = sha256_file(path)
    require_equal(policy.get("schema"), READOUT_RECOVERY2_POLICY_SCHEMA, "recovery2 policy schema")
    require_equal(policy.get("status"), "APPROVED", "recovery2 policy status")
    require_equal(policy.get("run_id"), config.get("run_id"), "recovery2 run ID")
    require_equal(policy.get("approved_by"), "김휘영", "recovery2 approver")
    require_equal(
        policy.get("recovery_kind"),
        "GSPLAT_SUCCESSFUL_TRAINING_CACHE_SEED_PREOUTPUT",
        "recovery2 kind",
    )
    require_equal(policy.get("stage"), "readout", "recovery2 stage")
    require_equal(policy.get("maximum_recoveries_per_job"), 1, "recovery2 maximum")
    require_equal(policy.get("prior_attempt_directory"), READOUT_RETRY_ATTEMPT_DIRECTORY, "recovery2 prior attempt")
    require_equal(policy.get("attempt_directory"), READOUT_RECOVERY2_ATTEMPT_DIRECTORY, "recovery2 attempt")
    require_equal(policy.get("allowed_argv_differences"), ["value_after_--out"], "recovery2 argv differences")
    require_equal(policy.get("jit_build_environment"), JIT_BUILD_ENVIRONMENT, "recovery2 JIT build environment")
    require_equal(jit_build_environment(config), JIT_BUILD_ENVIRONMENT, "configured recovery2 JIT build environment")
    environment = policy.get("writable_environment")
    if not isinstance(environment, Mapping) or set(environment) != WRITABLE_ENVIRONMENT_KEYS:
        raise ReadoutError("recovery2 writable environment is incomplete")
    require_equal(
        dict(environment),
        dict(config["pointcloudification"]["writable_environment"]),
        "recovery2 writable environment",
    )
    base = policy.get("required_pre_recovery_head")
    if not isinstance(base, str) or re.fullmatch(r"[0-9a-f]{40}", base) is None:
        raise ReadoutError("recovery2 pre-recovery HEAD is invalid")
    require_equal(policy.get("required_recovery_commit_distance"), 1, "recovery2 commit distance")
    allowed_paths = policy.get("allowed_recovery_commit_paths")
    if not isinstance(allowed_paths, list) or not allowed_paths or len(set(allowed_paths)) != len(allowed_paths):
        raise ReadoutError("recovery2 implementation path allowlist is invalid")
    if READOUT_RECOVERY2_POLICY_RELATIVE.as_posix() not in allowed_paths:
        raise ReadoutError(
            "canonical recovery2 policy is absent from the recovery commit allowlist"
        )
    required_hash_groups = (
        ("required_original_failure", {"materialization", "invocation", "started", "log", "failed"}),
        ("required_prior_retry_failure", {"retry_started", "invocation", "log", "retry_failed"}),
    )
    for group_name, expected_labels in required_hash_groups:
        group = policy.get(group_name)
        pinned = group.get("artifact_sha256") if isinstance(group, Mapping) else None
        if not isinstance(pinned, Mapping) or set(pinned) != expected_labels:
            raise ReadoutError(f"recovery2 {group_name} SHA binding is incomplete")
        for label, value in pinned.items():
            if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None:
                raise ReadoutError(f"invalid recovery2 SHA256 for {group_name}/{label}")
    zero = policy.get("required_zero_output")
    if not isinstance(zero, Mapping) or zero.get("required_file_count") != 0:
        raise ReadoutError("recovery2 zero-output contract is invalid")
    for key in ("output_roots", "required_absent_paths"):
        values = zero.get(key)
        if not isinstance(values, list) or not values:
            raise ReadoutError(f"recovery2 zero-output {key} is invalid")
        for value in values:
            candidate = Path(str(value))
            if candidate.is_absolute() or ".." in candidate.parts or not candidate.parts:
                raise ReadoutError(f"unsafe recovery2 zero-output path: {value!r}")
    source = policy.get("successful_training_cache_source")
    common = policy.get("required_common_cache_before_seed")
    for label, value in (("source", source), ("common", common)):
        if not isinstance(value, Mapping):
            raise ReadoutError(f"recovery2 {label} cache contract is missing")
        for field in ("root", "inventory_format", "inventory_sha256", "files_n", "bytes_n"):
            if field not in value:
                raise ReadoutError(f"recovery2 {label} cache {field} is missing")
    if not isinstance(source.get("successful_training_artifacts"), Mapping):
        raise ReadoutError("recovery2 successful-training artifact bindings are missing")
    for label, binding in source["successful_training_artifacts"].items():
        if not isinstance(binding, Mapping) or set(binding) != {"path", "sha256"}:
            raise ReadoutError(f"invalid successful-training binding: {label}")
        if re.fullmatch(r"[0-9a-f]{64}", str(binding["sha256"])) is None:
            raise ReadoutError(f"invalid successful-training SHA256: {label}")
    destination = policy.get("required_seed_destination_absent")
    if not isinstance(destination, Mapping):
        raise ReadoutError("recovery2 seed destination contract is missing")
    destination_root = Path(str(destination.get("root", "")))
    if (
        destination_root.is_absolute()
        or ".." in destination_root.parts
        or not destination_root.parts
    ):
        raise ReadoutError("recovery2 seed destination path is unsafe")
    require_equal(
        destination.get("must_be_absent_before_publish"),
        True,
        "recovery2 seed destination absence",
    )
    copy_contract = policy.get("cache_seed_contract")
    required_copy_contract = {
        "source_read_only": True,
        "prior_common_cache_preserved_in_place": True,
        "staged_copy_verified_before_atomic_publish": True,
        "destination_inventory_must_equal_source": True,
        "provenance_manifest_required_before_launch": True,
        "single_atomic_directory_rename": True,
        "seed_scope": "TORCH_EXTENSIONS_DIR/gsplat_cuda_only",
    }
    require_equal(copy_contract, required_copy_contract, "recovery2 cache seed contract")
    return {
        **dict(policy),
        "path": repo_relative(path, repo=repo),
        "sha256": digest,
        "allowed_recovery_commit_paths": list(allowed_paths),
        "writable_environment": dict(environment),
        "jit_build_environment": dict(JIT_BUILD_ENVIRONMENT),
    }, digest


def _validate_readout_recovery2_git_state(
    repo: Path, policy: Mapping[str, Any]
) -> dict[str, Any]:
    branch = _run_git(repo, "branch", "--show-current")
    require_equal(branch, "exp/fusion-w1", "recovery2 branch")
    head = _run_git(repo, "rev-parse", "HEAD")
    base = str(policy["required_pre_recovery_head"])
    _run_git(repo, "merge-base", "--is-ancestor", base, head)
    distance = int(_run_git(repo, "rev-list", "--count", f"{base}..{head}"))
    require_equal(distance, 1, "recovery2 commit distance")
    changed = sorted(
        line for line in _run_git(repo, "diff", "--name-only", base, head).splitlines() if line
    )
    require_equal(
        changed,
        sorted(str(value) for value in policy["allowed_recovery_commit_paths"]),
        "recovery2 implementation commit paths",
    )
    porcelain = _run_git(repo, "status", "--porcelain=v1", "--untracked-files=all")
    runtime_prefix = "phases/p2-gsjso/runs/fusion_w1/20260724_fusion_w1/"
    unexpected: list[str] = []
    allowed_runtime: list[str] = []
    for line in porcelain.splitlines():
        if line.startswith("?? ") and line[3:].startswith(runtime_prefix):
            allowed_runtime.append(line[3:])
        elif line:
            unexpected.append(line)
    if unexpected:
        raise ReadoutError(
            "recovery2 worktree has tracked or non-runtime changes: "
            + "; ".join(unexpected[:20])
        )
    return {
        "branch": branch,
        "pre_recovery_head": base,
        "recovery_head": head,
        "pre_recovery_head_is_ancestor": True,
        "commit_distance": distance,
        "changed_paths": changed,
        "tracked_changes": 0,
        "allowed_runtime_untracked_count": len(allowed_runtime),
    }


def _recovery2_artifact_paths(job: Path) -> tuple[dict[str, Path], dict[str, Path]]:
    original = {
        "materialization": job / "materialization.json",
        "invocation": job / "extract_invocation.json",
        "started": job / "readout_started.json",
        "log": job / "extract.stdout.log",
        "failed": job / "failed.json",
    }
    prior = {
        "retry_started": job / READOUT_RETRY_ATTEMPT_DIRECTORY / "retry_started.json",
        "invocation": job / READOUT_RETRY_ATTEMPT_DIRECTORY / "extract_invocation.json",
        "log": job / READOUT_RETRY_ATTEMPT_DIRECTORY / "extract.stdout.log",
        "retry_failed": job / READOUT_RETRY_ATTEMPT_DIRECTORY / "retry_failed.json",
    }
    return original, prior


def _verify_successful_training_cache_source(
    config: Mapping[str, Any], policy: Mapping[str, Any], *, repo: Path = REPO
) -> dict[str, Any]:
    source = policy["successful_training_cache_source"]
    bindings: dict[str, Any] = {}
    payloads: dict[str, Any] = {}
    for label, binding in source["successful_training_artifacts"].items():
        path = repo_path(str(binding["path"]), repo=repo)
        verify_hash(path, str(binding["sha256"]), f"successful training {label}")
        bindings[label] = {"path": repo_relative(path, repo=repo), "sha256": sha256_file(path)}
        if label != "log":
            payloads[label] = load_json(path)
    key = str(policy["job_key"])
    completed = payloads["completed"]
    retry_started = payloads["retry_started"]
    retry_completed = payloads["retry_completed"]
    require_equal(completed.get("schema"), "jointbuildgs.fusion_w1.training_completed.v1", "successful training completion schema")
    require_equal(completed.get("job_key"), key, "successful training completion job")
    require_equal(completed.get("return_code"), 0, "successful training return code")
    require_equal(retry_started.get("schema"), RETRY_STARTED_SCHEMA, "successful training retry STARTED schema")
    require_equal(retry_started.get("job_key"), key, "successful training retry STARTED job")
    require_equal(retry_started.get("retry_key"), f"{key}/{RETRY_ATTEMPT_DIRECTORY}", "successful training retry key")
    require_equal(retry_started.get("docker_image", {}).get("image_id"), source.get("docker_image_id"), "successful training image ID")
    require_equal(retry_completed.get("schema"), RETRY_COMPLETED_SCHEMA, "successful training retry completion schema")
    require_equal(retry_completed.get("job_key"), key, "successful training retry completion job")
    require_equal(retry_completed.get("return_code"), 0, "successful training retry return code")
    require_equal(retry_completed.get("training_completion", {}).get("status"), "PASSED", "successful training status")
    require_equal(retry_completed.get("training_completion", {}).get("completed_optimizer_updates"), 30000, "successful training optimizer updates")
    root_retry = completed.get("infrastructure_retry", {}).get("retry_completed_receipt", {})
    require_equal(root_retry, bindings["retry_completed"], "successful training root/retry completion binding")
    require_equal(completed.get("log_sha256"), bindings["log"]["sha256"], "successful training log binding")
    cache_root = repo_path(str(source["root"]), repo=repo)
    expected_environment = str(CONTAINER_REPO / Path(source["root"]).parent)
    require_equal(
        retry_started.get("environment", {}).get("TORCH_EXTENSIONS_DIR"),
        expected_environment,
        "successful training cache environment",
    )
    inventory = _cache_inventory(cache_root, repo=repo)
    _require_cache_inventory(inventory, source, "successful training cache")
    for relative, digest in source.get("required_key_files", {}).items():
        verify_hash(cache_root / relative, str(digest), f"successful training cache {relative}")
    require_equal(
        source.get("docker_image_id"),
        config["pointcloudification"]["image_id"],
        "training/readout cache image ID",
    )
    return {"artifacts": bindings, "inventory": inventory, "root": cache_root}


def _require_recovery2_job_directory(
    config: Mapping[str, Any],
    building_id: str,
    arm: str,
    run: str,
    *,
    repo: Path,
) -> Path:
    """Reject any symlink component in the recovery claim's parent path."""

    safe_identity(building_id, arm, run)
    relative = Path(
        str(config["outputs"]["job_template"]).format(
            building_id=building_id,
            arm=arm,
            run=run,
        )
    )
    if relative.is_absolute() or ".." in relative.parts or not relative.parts:
        raise ReadoutError("recovery2 job directory path is unsafe")
    cursor = repo.resolve()
    for part in relative.parts:
        cursor = cursor / part
        if cursor.is_symlink():
            raise ReadoutError(
                f"recovery2 job directory path contains a symlink: {cursor}"
            )
    if not cursor.is_dir():
        raise ReadoutError(f"recovery2 job directory is missing: {cursor}")
    require_equal(
        cursor,
        job_dir(config, building_id, arm, run, repo=repo),
        "recovery2 job directory",
    )
    return cursor


def _claim_recovery2_attempt(attempt: Path) -> None:
    """Atomically claim the only permitted attempt with a real directory."""

    try:
        attempt.mkdir(mode=0o755, parents=False, exist_ok=False)
    except FileExistsError as exc:
        raise ReadoutError(
            "the one permitted recovery2 attempt was already claimed"
        ) from exc
    except OSError as exc:
        raise ReadoutError(f"cannot atomically claim recovery2 attempt: {exc}") from exc
    claimed = os.lstat(attempt)
    if stat.S_ISLNK(claimed.st_mode) or not stat.S_ISDIR(claimed.st_mode):
        raise ReadoutError("recovery2 atomic claim is not a real directory")


def _verify_recovery2_preconditions(
    config: Mapping[str, Any],
    policy: Mapping[str, Any],
    building_id: str,
    arm: str,
    run: str,
    *,
    repo: Path = REPO,
) -> dict[str, Any]:
    key = job_key(building_id, arm, run)
    require_equal(key, policy.get("job_key"), "recovery2 job key")
    job = _require_recovery2_job_directory(
        config, building_id, arm, run, repo=repo
    )
    original, prior = _recovery2_artifact_paths(job)
    groups = (
        (original, policy["required_original_failure"]["artifact_sha256"], "original"),
        (prior, policy["required_prior_retry_failure"]["artifact_sha256"], "prior retry"),
    )
    refs: dict[str, Any] = {}
    for paths, pinned, prefix in groups:
        refs[prefix] = {}
        for label, path in paths.items():
            verify_hash(path, str(pinned[label]), f"recovery2 {prefix} {label}")
            refs[prefix][label] = {
                "path": repo_relative(path, repo=repo),
                "sha256": sha256_file(path),
            }
    original_invocation = load_receipt(
        original["invocation"],
        schema="jointbuildgs.fusion_w1.extract_invocation.v1",
        state="AUTHORIZED",
    )
    require_equal(original_invocation.get("job_key"), key, "recovery2 original invocation job")
    require_equal(original_invocation.get("retry_allowed"), False, "recovery2 original retry flag")
    prior_started = load_receipt(prior["retry_started"], schema=READOUT_RETRY_STARTED_SCHEMA, state="STARTED")
    prior_invocation = load_receipt(prior["invocation"], schema=READOUT_RETRY_INVOCATION_SCHEMA, state="AUTHORIZED")
    prior_failed = load_receipt(prior["retry_failed"], schema=READOUT_RETRY_FAILED_SCHEMA, state="FAILED")
    require_equal(prior_started.get("job_key"), key, "recovery2 prior STARTED job")
    require_equal(prior_invocation.get("job_key"), key, "recovery2 prior invocation job")
    require_equal(prior_failed.get("job_key"), key, "recovery2 prior failure job")
    require_equal(prior_failed.get("another_retry_allowed"), False, "recovery2 prior retry flag")
    require_equal(prior_failed.get("counter_increment"), 0, "recovery2 prior retry counter")
    require_equal(prior_failed.get("retry_started"), refs["prior retry"]["retry_started"], "recovery2 prior STARTED binding")
    require_equal(prior_failed.get("retry_invocation"), refs["prior retry"]["invocation"], "recovery2 prior invocation binding")
    prior_log = prior["log"].read_text(encoding="utf-8")
    for marker in policy["required_prior_retry_failure"].get("log_markers", []):
        if marker not in prior_log:
            raise ReadoutError(f"recovery2 prior retry log marker is absent: {marker}")
    attempt = job / READOUT_RECOVERY2_ATTEMPT_DIRECTORY
    if attempt.exists() or attempt.is_symlink():
        raise ReadoutError("the one permitted recovery2 attempt was already claimed")
    zero = policy["required_zero_output"]
    for relative in zero["required_absent_paths"]:
        path = job / str(relative)
        if path.exists() or path.is_symlink():
            raise ReadoutError(f"recovery2 preflight found forbidden output: {path}")
    output_files: list[str] = []
    for relative in zero["output_roots"]:
        root = job / str(relative)
        if root.is_symlink():
            raise ReadoutError(f"recovery2 output root is a symlink: {root}")
        if root.exists():
            if not root.is_dir():
                raise ReadoutError(f"recovery2 output root is not a directory: {root}")
            for path in root.rglob("*"):
                if path.is_symlink() or path.is_file():
                    output_files.append(repo_relative(path, repo=repo))
    require_equal(len(output_files), zero["required_file_count"], "recovery2 pre-existing output files")
    counters = reconcile_runtime_counters(config, repo=repo)
    for name, value in policy["required_counter_values"].items():
        require_equal(counters.get(name), value, f"recovery2 counter {name}")
    training_cache = _verify_successful_training_cache_source(config, policy, repo=repo)
    environment = writable_readout_environment(
        config, repo=repo, create=False, require_ready=False
    )
    common_root = repo_path(
        str(policy["required_common_cache_before_seed"]["root"]), repo=repo
    )
    common_inventory = _cache_inventory(common_root, repo=repo)
    _require_cache_inventory(common_inventory, policy["required_common_cache_before_seed"], "recovery2 pre-seed common cache")
    seed_destination = (
        repo_path(environment["host_paths"]["TORCH_EXTENSIONS_DIR"], repo=repo)
        / "gsplat_cuda"
    )
    require_equal(
        repo_relative(seed_destination, repo=repo),
        policy["required_seed_destination_absent"]["root"],
        "recovery2 versioned seed destination",
    )
    if seed_destination.exists() or seed_destination.is_symlink():
        raise ReadoutError(
            f"recovery2 versioned seed destination is not absent: {seed_destination}"
        )
    return {
        "job": job,
        "attempt": attempt,
        "original_paths": original,
        "prior_paths": prior,
        "original_invocation": original_invocation,
        "artifact_refs": refs,
        "counters": counters,
        "training_cache": training_cache,
        "common_root": common_root,
        "common_inventory": common_inventory,
        "seed_destination": seed_destination,
        "environment": environment,
    }


def _seed_recovery2_cache(
    policy: Mapping[str, Any],
    verified: Mapping[str, Any],
    started_path: Path,
    *,
    repo: Path = REPO,
) -> tuple[Path, dict[str, Any]]:
    attempt = verified["attempt"]
    source = verified["training_cache"]["root"]
    prior_common = verified["common_root"]
    destination = verified["seed_destination"]
    stage = destination.parent / ".gsplat_cuda.infra_retry_02.staging"
    manifest_path = attempt / "cache_seed_manifest.json"
    for path, label in (
        (stage, "staging cache"),
        (destination, "versioned seed destination"),
        (manifest_path, "cache seed manifest"),
    ):
        if path.exists() or path.is_symlink():
            raise ReadoutError(f"recovery2 {label} already exists: {path}")
    source_before = _cache_inventory(source, repo=repo)
    _require_cache_inventory(source_before, policy["successful_training_cache_source"], "recovery2 source before seed")
    shutil.copytree(source, stage, copy_function=shutil.copy2)
    staged = _cache_inventory(stage, repo=repo)
    require_equal(
        {key: value for key, value in staged.items() if key != "root"},
        {key: value for key, value in source_before.items() if key != "root"},
        "recovery2 staged/source cache inventory",
    )
    prior_common_before = _cache_inventory(prior_common, repo=repo)
    require_equal(
        prior_common_before,
        verified["common_inventory"],
        "recovery2 prior common cache before atomic publish",
    )
    os.rename(stage, destination)
    seeded = _cache_inventory(destination, repo=repo)
    require_equal(
        {key: value for key, value in seeded.items() if key != "root"},
        {key: value for key, value in source_before.items() if key != "root"},
        "recovery2 seeded/source cache inventory",
    )
    preserved = _cache_inventory(prior_common, repo=repo)
    require_equal(
        preserved,
        verified["common_inventory"],
        "recovery2 prior common cache preserved in place",
    )
    source_after = _cache_inventory(source, repo=repo)
    require_equal(source_after, source_before, "recovery2 source cache immutability")
    manifest = {
        "schema": READOUT_RECOVERY2_SEED_SCHEMA,
        "state": "COMPLETE",
        "created_at": now_iso(),
        "run_id": policy["run_id"],
        "job_key": policy["job_key"],
        "recovery_key": f"{policy['job_key']}/{READOUT_RECOVERY2_ATTEMPT_DIRECTORY}",
        "policy": {"path": policy["path"], "sha256": policy["sha256"]},
        "recovery_started": {
            "path": repo_relative(started_path, repo=repo),
            "sha256": sha256_file(started_path),
        },
        "successful_training_artifacts": verified["training_cache"]["artifacts"],
        "source_cache": source_before,
        "pre_seed_common_cache": verified["common_inventory"],
        "prior_common_cache_preserved_in_place_at": repo_relative(
            prior_common, repo=repo
        ),
        "seeded_common_cache": seeded,
        "copy_contract": policy["cache_seed_contract"],
        "source_unchanged_after_copy": True,
        "prior_common_cache_unchanged_after_publish": True,
        "destination_absent_before_publish": True,
        "staged_inventory_verified": True,
        "single_atomic_directory_rename_publish": True,
    }
    exclusive_json(manifest_path, manifest)
    return manifest_path, manifest


def _validate_recovery2_invocation_difference(
    original: Mapping[str, Any], retry: Mapping[str, Any], *, retry_output: str
) -> None:
    expected_new = {
        "original_invocation",
        "prior_retry_artifacts",
        "recovery_started",
        "cache_seed_manifest",
        "environment",
        "jit_build_environment",
        "allowed_differences",
    }
    require_equal(set(retry) - set(original), expected_new, "recovery2 invocation provenance keys")
    for key in set(original) - {"schema", "created_at", "output", "argv"}:
        require_equal(retry.get(key), original.get(key), f"recovery2 invocation {key}")
    require_equal(retry.get("schema"), READOUT_RECOVERY2_INVOCATION_SCHEMA, "recovery2 invocation schema")
    require_equal(retry.get("output"), retry_output, "recovery2 invocation output")
    original_argv = original.get("argv")
    retry_argv = retry.get("argv")
    if not isinstance(original_argv, list) or not isinstance(retry_argv, list):
        raise ReadoutError("recovery2 invocation argv is invalid")
    require_equal(
        retry_argv,
        _replace_only_output(original_argv, str(original.get("output")), retry_output),
        "recovery2 argv --out-only difference",
    )
    require_equal(retry.get("allowed_differences"), ["value_after_--out"], "recovery2 invocation difference declaration")
    require_equal(retry.get("jit_build_environment"), JIT_BUILD_ENVIRONMENT, "recovery2 invocation MAX_JOBS")


def _record_recovery2_failure_unchecked(
    config: Mapping[str, Any],
    building_id: str,
    arm: str,
    run: str,
    *,
    message: str,
    detail: str = "",
    repo: Path = REPO,
) -> dict[str, Any]:
    job = job_dir(config, building_id, arm, run, repo=repo)
    attempt = job / READOUT_RECOVERY2_ATTEMPT_DIRECTORY
    started_path = attempt / "recovery_started.json"
    started = load_receipt(started_path, schema=READOUT_RECOVERY2_STARTED_SCHEMA, state="STARTED")
    failed_path = attempt / "retry_failed.json"
    if failed_path.exists() or failed_path.is_symlink():
        return load_receipt(failed_path, schema=READOUT_RECOVERY2_FAILED_SCHEMA, state="FAILED")
    bindings: dict[str, Any] = {
        "recovery_started": {
            "path": repo_relative(started_path, repo=repo),
            "sha256": sha256_file(started_path),
        }
    }
    for label, filename in (("cache_seed_manifest", "cache_seed_manifest.json"), ("recovery_invocation", "extract_invocation.json")):
        path = attempt / filename
        if path.is_file() and not path.is_symlink():
            bindings[label] = {"path": repo_relative(path, repo=repo), "sha256": sha256_file(path)}
    payload = {
        "schema": READOUT_RECOVERY2_FAILED_SCHEMA,
        "state": "FAILED",
        "created_at": now_iso(),
        "run_id": config["run_id"],
        "job_key": job_key(building_id, arm, run),
        "recovery_key": started["recovery_key"],
        "message": message,
        "detail": detail[-12000:],
        **bindings,
        "partial_outputs_preserved": True,
        "another_recovery_allowed": False,
        "counter_increment": 0,
    }
    exclusive_json(failed_path, payload)
    return payload


def prepare_extract_infra_recovery2(
    config: Mapping[str, Any],
    policy_path: Path,
    building_id: str,
    arm: str,
    run: str,
    *,
    repo: Path = REPO,
    validate_git: bool = True,
) -> dict[str, Any]:
    policy, _ = validate_readout_recovery2_policy(config, policy_path, repo=repo)
    git = _validate_readout_recovery2_git_state(repo, policy) if validate_git else {"validation": "TEST_BYPASS"}
    verified = _verify_recovery2_preconditions(config, policy, building_id, arm, run, repo=repo)
    environment = writable_readout_environment(config, repo=repo, create=True)
    require_equal(environment["host_paths"], policy["writable_environment"], "recovery2 policy/environment paths")
    attempt = verified["attempt"]
    _claim_recovery2_attempt(attempt)
    started_path = attempt / "recovery_started.json"
    started = {
        "schema": READOUT_RECOVERY2_STARTED_SCHEMA,
        "state": "STARTED",
        "created_at": now_iso(),
        "run_id": config["run_id"],
        "job_key": job_key(building_id, arm, run),
        "recovery_key": f"{job_key(building_id, arm, run)}/{READOUT_RECOVERY2_ATTEMPT_DIRECTORY}",
        "policy": policy,
        "git": git,
        "original_artifacts": verified["artifact_refs"]["original"],
        "prior_retry_artifacts": verified["artifact_refs"]["prior retry"],
        "zero_output_file_count": 0,
        "successful_training_artifacts": verified["training_cache"]["artifacts"],
        "successful_training_cache_inventory": verified["training_cache"]["inventory"],
        "pre_seed_common_cache_inventory": verified["common_inventory"],
        "environment": environment,
        "jit_build_environment": dict(JIT_BUILD_ENVIRONMENT),
        "counter_increment": 0,
        "claim_mode": "atomic_O_EXCL_exactly_one_cache_seeded_preoutput_recovery",
    }
    exclusive_json(started_path, started)
    try:
        seed_path, _ = _seed_recovery2_cache(policy, verified, started_path, repo=repo)
        original = verified["original_invocation"]
        output = attempt / "pointcloud" / "readout.npz"
        output_rel = repo_relative(output, repo=repo)
        original_argv = original.get("argv")
        if not isinstance(original_argv, list) or not all(isinstance(value, str) for value in original_argv):
            raise ReadoutError("recovery2 original argv is invalid")
        invocation = {
            **dict(original),
            "schema": READOUT_RECOVERY2_INVOCATION_SCHEMA,
            "created_at": now_iso(),
            "output": output_rel,
            "argv": _replace_only_output(original_argv, str(original["output"]), output_rel),
            "original_invocation": verified["artifact_refs"]["original"]["invocation"],
            "prior_retry_artifacts": verified["artifact_refs"]["prior retry"],
            "recovery_started": {"path": repo_relative(started_path, repo=repo), "sha256": sha256_file(started_path)},
            "cache_seed_manifest": {"path": repo_relative(seed_path, repo=repo), "sha256": sha256_file(seed_path)},
            "environment": environment,
            "jit_build_environment": dict(JIT_BUILD_ENVIRONMENT),
            "allowed_differences": ["value_after_--out"],
            "retry_allowed": False,
        }
        _validate_recovery2_invocation_difference(original, invocation, retry_output=output_rel)
        invocation_path = attempt / "extract_invocation.json"
        exclusive_json(invocation_path, invocation)
    except Exception as exc:
        _record_recovery2_failure_unchecked(
            config,
            building_id,
            arm,
            run,
            message="recovery2 cache seed or authorization failed",
            detail="".join(traceback.format_exception(type(exc), exc, exc.__traceback__)),
            repo=repo,
        )
        raise
    return {
        "status": "AUTHORIZED",
        "attempt": repo_relative(attempt, repo=repo),
        "recovery_started": repo_relative(started_path, repo=repo),
        "cache_seed_manifest": repo_relative(seed_path, repo=repo),
        "recovery_invocation": repo_relative(invocation_path, repo=repo),
        "recovery_output": output_rel,
        "environment": environment,
        "jit_build_environment": dict(JIT_BUILD_ENVIRONMENT),
        "counter_increment": 0,
    }


def _verify_recovery2_pinned_artifacts(
    job: Path, policy: Mapping[str, Any], *, repo: Path = REPO
) -> dict[str, Any]:
    original, prior = _recovery2_artifact_paths(job)
    refs: dict[str, Any] = {}
    for paths, pinned, group in (
        (original, policy["required_original_failure"]["artifact_sha256"], "original"),
        (prior, policy["required_prior_retry_failure"]["artifact_sha256"], "prior retry"),
    ):
        refs[group] = {}
        for label, path in paths.items():
            verify_hash(path, str(pinned[label]), f"recovery2 pinned {group} {label}")
            refs[group][label] = {"path": repo_relative(path, repo=repo), "sha256": sha256_file(path)}
    return refs


def _validate_recovery2_seed_manifest(
    config: Mapping[str, Any],
    policy: Mapping[str, Any],
    attempt: Path,
    started_path: Path,
    *,
    repo: Path = REPO,
    require_destination_exact: bool,
) -> tuple[Path, dict[str, Any]]:
    path = attempt / "cache_seed_manifest.json"
    manifest = load_receipt(path, schema=READOUT_RECOVERY2_SEED_SCHEMA, state="COMPLETE")
    require_equal(manifest.get("job_key"), policy["job_key"], "recovery2 cache manifest job")
    require_equal(
        manifest.get("recovery_key"),
        f"{policy['job_key']}/{READOUT_RECOVERY2_ATTEMPT_DIRECTORY}",
        "recovery2 cache manifest key",
    )
    require_equal(
        manifest.get("policy"),
        {"path": policy["path"], "sha256": policy["sha256"]},
        "recovery2 cache manifest policy",
    )
    require_equal(
        manifest.get("recovery_started"),
        {"path": repo_relative(started_path, repo=repo), "sha256": sha256_file(started_path)},
        "recovery2 cache manifest STARTED binding",
    )
    require_equal(
        manifest.get("successful_training_artifacts"),
        policy["successful_training_cache_source"]["successful_training_artifacts"],
        "recovery2 cache manifest training provenance",
    )
    _require_cache_inventory(
        manifest.get("source_cache", {}),
        policy["successful_training_cache_source"],
        "recovery2 cache manifest source",
    )
    _require_cache_inventory(
        manifest.get("pre_seed_common_cache", {}),
        policy["required_common_cache_before_seed"],
        "recovery2 cache manifest pre-seed common",
    )
    require_equal(manifest.get("copy_contract"), policy["cache_seed_contract"], "recovery2 cache copy contract")
    for field in (
        "source_unchanged_after_copy",
        "prior_common_cache_unchanged_after_publish",
        "destination_absent_before_publish",
        "staged_inventory_verified",
        "single_atomic_directory_rename_publish",
    ):
        require_equal(manifest.get(field), True, f"recovery2 cache manifest {field}")
    source_root = repo_path(str(policy["successful_training_cache_source"]["root"]), repo=repo)
    source_inventory = _cache_inventory(source_root, repo=repo)
    _require_cache_inventory(source_inventory, policy["successful_training_cache_source"], "recovery2 current source cache")
    prior_common = repo_path(
        str(manifest.get("prior_common_cache_preserved_in_place_at")), repo=repo
    )
    require_equal(
        repo_relative(prior_common, repo=repo),
        policy["required_common_cache_before_seed"]["root"],
        "recovery2 prior common cache preserved path",
    )
    prior_common_inventory = _cache_inventory(prior_common, repo=repo)
    require_equal(
        prior_common_inventory,
        dict(manifest["pre_seed_common_cache"]),
        "recovery2 prior common cache inventory",
    )
    environment = writable_readout_environment(config, repo=repo, create=False, require_ready=True)
    destination = repo_path(environment["host_paths"]["TORCH_EXTENSIONS_DIR"], repo=repo) / "gsplat_cuda"
    seeded = manifest.get("seeded_common_cache")
    if not isinstance(seeded, Mapping):
        raise ReadoutError("recovery2 seeded common cache manifest is missing")
    require_equal(seeded.get("root"), repo_relative(destination, repo=repo), "recovery2 seeded cache root")
    key_sha = policy["successful_training_cache_source"]["required_key_files"]["gsplat_cuda.so"]
    verify_hash(destination / "gsplat_cuda.so", str(key_sha), "recovery2 seeded gsplat_cuda.so")
    if require_destination_exact:
        destination_inventory = _cache_inventory(destination, repo=repo)
        require_equal(destination_inventory, dict(seeded), "recovery2 seeded cache launch inventory")
    return path, manifest


def _load_active_extract_recovery2(
    config: Mapping[str, Any],
    building_id: str,
    arm: str,
    run: str,
    *,
    repo: Path = REPO,
    allow_completed: bool = False,
    require_destination_exact: bool = True,
) -> tuple[Path, dict[str, Any], Path, dict[str, Any], Path, dict[str, Any]]:
    job = job_dir(config, building_id, arm, run, repo=repo)
    attempt = job / READOUT_RECOVERY2_ATTEMPT_DIRECTORY
    if not attempt.is_dir() or attempt.is_symlink():
        raise ReadoutError("recovery2 attempt directory is invalid")
    started_path = attempt / "recovery_started.json"
    started = load_receipt(started_path, schema=READOUT_RECOVERY2_STARTED_SCHEMA, state="STARTED")
    key = job_key(building_id, arm, run)
    require_equal(started.get("job_key"), key, "recovery2 STARTED job")
    require_equal(started.get("recovery_key"), f"{key}/{READOUT_RECOVERY2_ATTEMPT_DIRECTORY}", "recovery2 STARTED key")
    policy_binding = started.get("policy")
    if not isinstance(policy_binding, Mapping):
        raise ReadoutError("recovery2 STARTED policy binding is missing")
    policy_path = repo_path(str(policy_binding.get("path")), repo=repo)
    policy, _ = validate_readout_recovery2_policy(config, policy_path, repo=repo)
    require_equal(dict(policy_binding), policy, "recovery2 STARTED policy")
    refs = _verify_recovery2_pinned_artifacts(job, policy, repo=repo)
    require_equal(started.get("original_artifacts"), refs["original"], "recovery2 STARTED original artifacts")
    require_equal(started.get("prior_retry_artifacts"), refs["prior retry"], "recovery2 STARTED prior retry artifacts")
    require_equal(started.get("zero_output_file_count"), 0, "recovery2 STARTED output count")
    require_equal(started.get("counter_increment"), 0, "recovery2 STARTED counter increment")
    failed_path = attempt / "retry_failed.json"
    if failed_path.exists() or failed_path.is_symlink():
        raise ReadoutError("recovery2 already failed")
    completed_path = attempt / "recovery_completed.json"
    if not allow_completed and (completed_path.exists() or completed_path.is_symlink()):
        raise ReadoutError("recovery2 already completed")
    seed_path, seed = _validate_recovery2_seed_manifest(
        config,
        policy,
        attempt,
        started_path,
        repo=repo,
        require_destination_exact=require_destination_exact,
    )
    invocation_path = attempt / "extract_invocation.json"
    invocation = load_receipt(invocation_path, schema=READOUT_RECOVERY2_INVOCATION_SCHEMA, state="AUTHORIZED")
    require_equal(invocation.get("job_key"), key, "recovery2 invocation job")
    require_equal(
        invocation.get("recovery_started"),
        {"path": repo_relative(started_path, repo=repo), "sha256": sha256_file(started_path)},
        "recovery2 invocation STARTED binding",
    )
    require_equal(
        invocation.get("cache_seed_manifest"),
        {"path": repo_relative(seed_path, repo=repo), "sha256": sha256_file(seed_path)},
        "recovery2 invocation cache seed binding",
    )
    environment = writable_readout_environment(config, repo=repo, create=False, require_ready=True)
    require_equal(invocation.get("environment"), environment, "recovery2 invocation environment")
    require_equal(invocation.get("jit_build_environment"), jit_build_environment(config), "recovery2 invocation JIT environment")
    _validate_recovery2_invocation_difference(
        load_json(job / "extract_invocation.json"),
        invocation,
        retry_output=str(invocation.get("output")),
    )
    return attempt, started, invocation_path, invocation, seed_path, seed


def recovery2_extract_argv(
    config: Mapping[str, Any], building_id: str, arm: str, run: str, *, repo: Path = REPO
) -> list[str]:
    _, _, _, invocation, _, _ = _load_active_extract_recovery2(
        config, building_id, arm, run, repo=repo
    )
    argv = invocation.get("argv")
    if not isinstance(argv, list) or not all(isinstance(value, str) and value for value in argv):
        raise ReadoutError("recovery2 argv is invalid")
    return list(argv)


def recovery2_extract_environment(
    config: Mapping[str, Any], building_id: str, arm: str, run: str, *, repo: Path = REPO
) -> list[str]:
    _, _, _, invocation, _, _ = _load_active_extract_recovery2(
        config, building_id, arm, run, repo=repo
    )
    values = dict(invocation["environment"]["container_values"])
    values.update(invocation["jit_build_environment"])
    require_equal(values.get("MAX_JOBS"), "1", "recovery2 launch MAX_JOBS")
    return [f"{key}={values[key]}" for key in sorted(values)]


def record_extract_infra_recovery2_failure(
    config: Mapping[str, Any],
    building_id: str,
    arm: str,
    run: str,
    *,
    message: str,
    detail: str = "",
    repo: Path = REPO,
) -> dict[str, Any]:
    job = job_dir(config, building_id, arm, run, repo=repo)
    if (job / "extract_receipt.json").exists() or (job / "extract_receipt.json").is_symlink():
        try:
            adopted = _validate_adopted_extract_recovery2(job, repo=repo)
        except ReadoutError:
            adopted = False
        if adopted:
            raise ReadoutError("recovery2 was already successfully adopted")
    return _record_recovery2_failure_unchecked(
        config,
        building_id,
        arm,
        run,
        message=message,
        detail=detail,
        repo=repo,
    )


def _validate_recovery2_completion_chain(
    *,
    attempt: Path,
    started: Mapping[str, Any],
    invocation_path: Path,
    invocation: Mapping[str, Any],
    seed_path: Path,
    attempt_receipt_path: Path,
    attempt_receipt: Mapping[str, Any],
    completed_path: Path,
    completed: Mapping[str, Any],
    pointcloud: Mapping[str, Any],
    repo: Path = REPO,
) -> None:
    key = str(started["job_key"])
    recovery_key = f"{key}/{READOUT_RECOVERY2_ATTEMPT_DIRECTORY}"
    refs = {
        "recovery_started": {"path": repo_relative(attempt / "recovery_started.json", repo=repo), "sha256": sha256_file(attempt / "recovery_started.json")},
        "recovery_invocation": {"path": repo_relative(invocation_path, repo=repo), "sha256": sha256_file(invocation_path)},
        "cache_seed_manifest": {"path": repo_relative(seed_path, repo=repo), "sha256": sha256_file(seed_path)},
        "extract_receipt": {"path": repo_relative(attempt_receipt_path, repo=repo), "sha256": sha256_file(attempt_receipt_path)},
    }
    require_equal(attempt_receipt.get("job_key"), key, "recovery2 extract receipt job")
    require_equal(attempt_receipt.get("recovery_key"), recovery_key, "recovery2 extract receipt key")
    require_equal(attempt_receipt.get("invocation"), refs["recovery_invocation"], "recovery2 extract receipt invocation")
    require_equal(attempt_receipt.get("cache_seed_manifest"), refs["cache_seed_manifest"], "recovery2 extract receipt cache seed")
    require_equal(attempt_receipt.get("pointcloud"), dict(pointcloud), "recovery2 extract receipt point cloud")
    require_equal(attempt_receipt.get("counter_increment"), 0, "recovery2 extract receipt counter")
    require_equal(completed.get("job_key"), key, "recovery2 completion job")
    require_equal(completed.get("recovery_key"), recovery_key, "recovery2 completion key")
    require_equal(completed.get("return_code"), 0, "recovery2 completion return code")
    for label in ("recovery_started", "recovery_invocation", "cache_seed_manifest", "extract_receipt"):
        require_equal(completed.get(label), refs[label], f"recovery2 completion {label}")
    require_equal(completed.get("pointcloud"), dict(pointcloud), "recovery2 completion point cloud")
    require_equal(
        completed.get("post_execution_common_cache_inventory"),
        attempt_receipt.get("post_execution_common_cache_inventory"),
        "recovery2 completion post-execution cache inventory",
    )
    require_equal(completed.get("counter_increment"), 0, "recovery2 completion counter")
    require_regular(completed_path, "recovery2 completion receipt")


def accept_extract_infra_recovery2(
    config: Mapping[str, Any],
    building_id: str,
    arm: str,
    run: str,
    *,
    wall_seconds: float,
    repo: Path = REPO,
) -> dict[str, Any]:
    job = job_dir(config, building_id, arm, run, repo=repo)
    root_receipt = job / "extract_receipt.json"
    if root_receipt.exists() or root_receipt.is_symlink():
        root = load_receipt(root_receipt, schema="jointbuildgs.fusion_w1.extract_receipt.v1", state="COMPLETE")
        if not _validate_adopted_extract_recovery2(job, repo=repo):
            raise ReadoutError("existing root extract receipt is not an adopted recovery2")
        return root
    attempt, started, invocation_path, invocation, seed_path, seed = _load_active_extract_recovery2(
        config,
        building_id,
        arm,
        run,
        repo=repo,
        allow_completed=True,
        require_destination_exact=False,
    )
    checkpoint = repo_path(str(invocation["training_checkpoint"]["path"]), repo=repo)
    verify_hash(checkpoint, str(invocation["training_checkpoint"]["sha256"]), "checkpoint before accepting recovery2")
    output = _resolve_retry_output_before_receipt(invocation, attempt, repo=repo)
    stats = inspect_npz(output, config, repo=repo)
    _verify_recovery2_pinned_artifacts(job, started["policy"], repo=repo)
    for relative in (
        "classification_invocation.json",
        "classification_receipt.json",
        "roofer_invocation.json",
        "roofer_receipt.json",
        "score_receipt.json",
        "complete.json",
    ):
        path = job / relative
        if path.exists() or path.is_symlink():
            raise ReadoutError(f"recovery2 found downstream output before adoption: {path}")
    post_cache = _cache_inventory(
        repo_path(invocation["environment"]["host_paths"]["TORCH_EXTENSIONS_DIR"], repo=repo) / "gsplat_cuda",
        repo=repo,
    )
    attempt_receipt_path = attempt / "extract_receipt.json"
    attempt_receipt = {
        "schema": "jointbuildgs.fusion_w1.extract_infra_retry2_receipt.v1",
        "state": "COMPLETE",
        "created_at": now_iso(),
        "job_key": job_key(building_id, arm, run),
        "recovery_key": started["recovery_key"],
        "invocation": {"path": repo_relative(invocation_path, repo=repo), "sha256": sha256_file(invocation_path)},
        "cache_seed_manifest": {"path": repo_relative(seed_path, repo=repo), "sha256": sha256_file(seed_path)},
        "pointcloud": stats,
        "post_execution_common_cache_inventory": post_cache,
        "wall_seconds": float(wall_seconds),
        "counter_increment": 0,
    }
    exclusive_json(attempt_receipt_path, attempt_receipt)
    completed_path = attempt / "recovery_completed.json"
    completed = {
        "schema": READOUT_RECOVERY2_COMPLETED_SCHEMA,
        "state": "COMPLETE",
        "completed_at": now_iso(),
        "run_id": config["run_id"],
        "job_key": job_key(building_id, arm, run),
        "recovery_key": started["recovery_key"],
        "return_code": 0,
        "recovery_started": {"path": repo_relative(attempt / "recovery_started.json", repo=repo), "sha256": sha256_file(attempt / "recovery_started.json")},
        "recovery_invocation": {"path": repo_relative(invocation_path, repo=repo), "sha256": sha256_file(invocation_path)},
        "cache_seed_manifest": {"path": repo_relative(seed_path, repo=repo), "sha256": sha256_file(seed_path)},
        "extract_receipt": {"path": repo_relative(attempt_receipt_path, repo=repo), "sha256": sha256_file(attempt_receipt_path)},
        "pointcloud": stats,
        "post_execution_common_cache_inventory": post_cache,
        "counter_increment": 0,
    }
    exclusive_json(completed_path, completed)
    _validate_recovery2_completion_chain(
        attempt=attempt,
        started=started,
        invocation_path=invocation_path,
        invocation=invocation,
        seed_path=seed_path,
        attempt_receipt_path=attempt_receipt_path,
        attempt_receipt=attempt_receipt,
        completed_path=completed_path,
        completed=completed,
        pointcloud=stats,
        repo=repo,
    )
    root = {
        "schema": "jointbuildgs.fusion_w1.extract_receipt.v1",
        "state": "COMPLETE",
        "created_at": completed["completed_at"],
        "job_key": job_key(building_id, arm, run),
        "building_id": building_id,
        "arm": arm,
        "replicate": run,
        "invocation": {"path": repo_relative(invocation_path, repo=repo), "sha256": sha256_file(invocation_path)},
        "pointcloud": stats,
        "wall_seconds": float(wall_seconds),
        "resource_contract": config["resource_lock"],
        "partial_output_accepted": False,
        "infrastructure_recovery2": {
            "policy": started["policy"],
            "original_artifacts": started["original_artifacts"],
            "prior_retry_artifacts": started["prior_retry_artifacts"],
            "recovery_started": completed["recovery_started"],
            "cache_seed_manifest": completed["cache_seed_manifest"],
            "recovery_invocation": completed["recovery_invocation"],
            "recovery_completed": {"path": repo_relative(completed_path, repo=repo), "sha256": sha256_file(completed_path)},
            "counter_increment": 0,
            "allowed_argv_differences": ["value_after_--out"],
        },
    }
    exclusive_json(root_receipt, root)
    if not _validate_adopted_extract_recovery2(job, repo=repo):
        raise ReadoutError("published recovery2 root receipt failed validation")
    return root


def _validate_adopted_extract_recovery2(job: Path, *, repo: Path = REPO) -> bool:
    root_path = job / "extract_receipt.json"
    if not root_path.is_file() or root_path.is_symlink():
        return False
    root = load_receipt(root_path, schema="jointbuildgs.fusion_w1.extract_receipt.v1", state="COMPLETE")
    chain = root.get("infrastructure_recovery2")
    if not isinstance(chain, Mapping):
        return False
    policy_binding = chain.get("policy")
    if not isinstance(policy_binding, Mapping):
        raise ReadoutError("adopted recovery2 policy binding is missing")
    policy_path = _canonical_recovery2_policy_path(
        Path(str(policy_binding.get("path"))), repo=repo
    )
    verify_hash(policy_path, str(policy_binding.get("sha256")), "adopted recovery2 policy")
    policy = load_json(policy_path)
    require_equal(policy.get("schema"), READOUT_RECOVERY2_POLICY_SCHEMA, "adopted recovery2 policy schema")
    expected_policy_binding = {
        **policy,
        "path": repo_relative(policy_path, repo=repo),
        "sha256": sha256_file(policy_path),
        "allowed_recovery_commit_paths": list(
            policy["allowed_recovery_commit_paths"]
        ),
        "writable_environment": dict(policy["writable_environment"]),
        "jit_build_environment": dict(JIT_BUILD_ENVIRONMENT),
    }
    require_equal(
        dict(policy_binding),
        expected_policy_binding,
        "adopted recovery2 canonical policy binding",
    )
    attempt = job / READOUT_RECOVERY2_ATTEMPT_DIRECTORY
    if not attempt.is_dir() or attempt.is_symlink():
        raise ReadoutError("adopted recovery2 attempt is invalid")
    paths = {
        "recovery_started": attempt / "recovery_started.json",
        "cache_seed_manifest": attempt / "cache_seed_manifest.json",
        "recovery_invocation": attempt / "extract_invocation.json",
        "recovery_completed": attempt / "recovery_completed.json",
    }
    for label, path in paths.items():
        binding = chain.get(label)
        if not isinstance(binding, Mapping):
            raise ReadoutError(f"adopted recovery2 {label} binding is missing")
        require_equal(repo_path(str(binding.get("path")), repo=repo), path.resolve(), f"adopted recovery2 {label} path")
        verify_hash(path, str(binding.get("sha256")), f"adopted recovery2 {label}")
    started = load_receipt(paths["recovery_started"], schema=READOUT_RECOVERY2_STARTED_SCHEMA, state="STARTED")
    invocation = load_receipt(paths["recovery_invocation"], schema=READOUT_RECOVERY2_INVOCATION_SCHEMA, state="AUTHORIZED")
    completed = load_receipt(paths["recovery_completed"], schema=READOUT_RECOVERY2_COMPLETED_SCHEMA, state="COMPLETE")
    seed = load_receipt(paths["cache_seed_manifest"], schema=READOUT_RECOVERY2_SEED_SCHEMA, state="COMPLETE")
    require_equal(started.get("policy"), dict(policy_binding), "adopted recovery2 STARTED policy")
    key = str(policy["job_key"])
    recovery_key = f"{key}/{READOUT_RECOVERY2_ATTEMPT_DIRECTORY}"
    require_equal(started.get("job_key"), key, "adopted recovery2 STARTED job")
    require_equal(started.get("recovery_key"), recovery_key, "adopted recovery2 STARTED key")
    require_equal(started.get("zero_output_file_count"), 0, "adopted recovery2 STARTED output count")
    require_equal(started.get("counter_increment"), 0, "adopted recovery2 STARTED counter")
    require_equal(started.get("jit_build_environment"), JIT_BUILD_ENVIRONMENT, "adopted recovery2 STARTED MAX_JOBS")
    refs = _verify_recovery2_pinned_artifacts(job, policy, repo=repo)
    require_equal(chain.get("original_artifacts"), refs["original"], "adopted recovery2 original artifacts")
    require_equal(chain.get("prior_retry_artifacts"), refs["prior retry"], "adopted recovery2 prior artifacts")
    require_equal(started.get("original_artifacts"), refs["original"], "adopted recovery2 STARTED original artifacts")
    require_equal(started.get("prior_retry_artifacts"), refs["prior retry"], "adopted recovery2 STARTED prior artifacts")
    extract_binding = completed.get("extract_receipt")
    if not isinstance(extract_binding, Mapping):
        raise ReadoutError("adopted recovery2 extract receipt binding is missing")
    attempt_receipt_path = repo_path(str(extract_binding.get("path")), repo=repo)
    attempt_receipt = load_receipt(attempt_receipt_path, schema="jointbuildgs.fusion_w1.extract_infra_retry2_receipt.v1", state="COMPLETE")
    pointcloud = completed.get("pointcloud")
    if not isinstance(pointcloud, Mapping):
        raise ReadoutError("adopted recovery2 point cloud is missing")
    _validate_recovery2_completion_chain(
        attempt=attempt,
        started=started,
        invocation_path=paths["recovery_invocation"],
        invocation=invocation,
        seed_path=paths["cache_seed_manifest"],
        attempt_receipt_path=attempt_receipt_path,
        attempt_receipt=attempt_receipt,
        completed_path=paths["recovery_completed"],
        completed=completed,
        pointcloud=pointcloud,
        repo=repo,
    )
    output = _resolve_retry_output_before_receipt(invocation, attempt, repo=repo)
    verify_hash(output, str(pointcloud.get("sha256")), "adopted recovery2 point cloud")
    require_equal(seed.get("job_key"), key, "adopted recovery2 cache manifest job")
    require_equal(seed.get("recovery_key"), recovery_key, "adopted recovery2 cache manifest key")
    require_equal(
        seed.get("policy"),
        {"path": policy_binding["path"], "sha256": policy_binding["sha256"]},
        "adopted recovery2 cache manifest policy",
    )
    require_equal(seed.get("copy_contract"), policy["cache_seed_contract"], "adopted recovery2 cache contract")
    _require_cache_inventory(
        seed.get("source_cache", {}),
        policy["successful_training_cache_source"],
        "adopted recovery2 source cache manifest",
    )
    _require_cache_inventory(
        seed.get("pre_seed_common_cache", {}),
        policy["required_common_cache_before_seed"],
        "adopted recovery2 prior common cache manifest",
    )
    current_prior = _cache_inventory(
        repo_path(policy["required_common_cache_before_seed"]["root"], repo=repo),
        repo=repo,
    )
    _require_cache_inventory(
        current_prior,
        policy["required_common_cache_before_seed"],
        "adopted recovery2 current prior common cache",
    )
    destination = repo_path(policy["required_seed_destination_absent"]["root"], repo=repo)
    seeded = seed.get("seeded_common_cache")
    if not isinstance(seeded, Mapping):
        raise ReadoutError("adopted recovery2 seeded cache manifest is missing")
    require_equal(seeded.get("root"), repo_relative(destination, repo=repo), "adopted recovery2 seeded cache path")
    verify_hash(
        destination / "gsplat_cuda.so",
        str(policy["successful_training_cache_source"]["required_key_files"]["gsplat_cuda.so"]),
        "adopted recovery2 seeded gsplat extension",
    )
    require_equal(root.get("pointcloud"), dict(pointcloud), "adopted recovery2 root point cloud")
    require_equal(root.get("invocation"), chain.get("recovery_invocation"), "adopted recovery2 root invocation")
    require_equal(root.get("job_key"), started.get("job_key"), "adopted recovery2 root job")
    require_equal(root.get("building_id"), invocation.get("building_id"), "adopted recovery2 root building")
    require_equal(root.get("arm"), invocation.get("arm"), "adopted recovery2 root arm")
    require_equal(root.get("replicate"), invocation.get("replicate"), "adopted recovery2 root replicate")
    require_equal(root.get("partial_output_accepted"), False, "adopted recovery2 partial output")
    require_equal(chain.get("counter_increment"), 0, "adopted recovery2 counter")
    require_equal(chain.get("allowed_argv_differences"), ["value_after_--out"], "adopted recovery2 argv difference")
    require_equal(seed.get("recovery_started"), chain.get("recovery_started"), "adopted recovery2 seed STARTED")
    _validate_recovery2_invocation_difference(load_json(job / "extract_invocation.json"), invocation, retry_output=repo_relative(output, repo=repo))
    return True


def load_receipt(
    path: Path,
    *,
    schema: str,
    state: str,
) -> dict[str, Any]:
    payload = load_json(path)
    require_equal(payload.get("schema"), schema, f"{path.name} schema")
    require_equal(payload.get("state"), state, f"{path.name} state")
    return payload


def record_failure(
    config: Mapping[str, Any],
    building_id: str,
    arm: str,
    run: str,
    *,
    stage: str,
    message: str,
    detail: str = "",
    repo: Path = REPO,
) -> dict[str, Any]:
    safe_identity(building_id, arm, run)
    job = job_dir(config, building_id, arm, run, repo=repo)
    payload = {
        "schema": "jointbuildgs.fusion_w1.readout_failure.v1",
        "state": "FAILED",
        "created_at": now_iso(),
        "run_id": config["run_id"],
        "job_key": job_key(building_id, arm, run),
        "building_id": building_id,
        "arm": arm,
        "replicate": run,
        "stage": stage,
        "message": message,
        "detail": detail[-12000:],
        "partial_outputs_preserved": True,
        "retry_allowed": False,
    }
    failed = job / "failed.json"
    if failed.exists() or failed.is_symlink():
        if not (
            _validate_adopted_extract_retry(job, repo=repo)
            or _validate_adopted_extract_recovery2(job, repo=repo)
        ):
            return load_json(failed)
        failed = job / "failed_after_infrastructure_retry.json"
        payload["schema"] = (
            "jointbuildgs.fusion_w1.readout_failure_after_infrastructure_retry.v1"
        )
        payload["original_failure"] = {
            "path": repo_relative(job / "failed.json", repo=repo),
            "sha256": sha256_file(job / "failed.json"),
        }
        payload["adopted_extract_receipt"] = {
            "path": repo_relative(job / "extract_receipt.json", repo=repo),
            "sha256": sha256_file(job / "extract_receipt.json"),
        }
        if failed.exists() or failed.is_symlink():
            return load_json(failed)
    exclusive_json(failed, payload)
    append_jsonl(
        repo_path(config["outputs"]["failures_jsonl"], repo=repo),
        payload,
    )
    return payload


def _derive_runtime_counters(
    config: Mapping[str, Any],
    *,
    repo: Path = REPO,
) -> dict[str, Any]:
    """Derive the counter materialized view from immutable STARTED receipts."""

    counter_path = repo_path(
        config["outputs"]["runtime_counters"], repo=repo
    )
    readout_root = counter_path.parent
    by_job: dict[str, dict[str, Any]] = {}
    inventory: list[dict[str, str]] = []
    inverse_names = {
        filename: stage for stage, filename in STAGE_STARTED_FILES.items()
    }
    if readout_root.exists():
        candidates = sorted(
            readout_root.glob("by_building/*/arm_*/*/*_started.json")
        )
    else:
        candidates = []
    for path in candidates:
        try:
            relative = path.relative_to(readout_root)
        except ValueError as exc:  # pragma: no cover - glob root guarantees this
            raise ReadoutError(f"counter receipt escapes readout root: {path}") from exc
        parts = relative.parts
        if len(parts) != 5 or parts[0] != "by_building":
            raise ReadoutError(f"unexpected STARTED receipt path: {relative}")
        building_id, arm_part, run, filename = (
            parts[1],
            parts[2],
            parts[3],
            parts[4],
        )
        if not arm_part.startswith("arm_") or filename not in inverse_names:
            raise ReadoutError(f"unexpected STARTED receipt path: {relative}")
        arm = arm_part.removeprefix("arm_")
        stage = inverse_names[filename]
        safe_identity(building_id, arm, run)
        key = job_key(building_id, arm, run)
        receipt = load_receipt(path, schema=JOB_SCHEMA, state="STARTED")
        require_equal(receipt.get("stage"), stage, "STARTED receipt stage")
        require_equal(receipt.get("job_key"), key, "STARTED receipt job key")
        require_equal(
            receipt.get("building_id"), building_id, "STARTED receipt building"
        )
        require_equal(receipt.get("arm"), arm, "STARTED receipt arm")
        require_equal(receipt.get("replicate"), run, "STARTED receipt run")
        record = by_job.setdefault(key, {})
        started_field = f"{stage}_started_at"
        if started_field in record:
            raise ReadoutError(f"duplicate STARTED receipt inventory: {key}/{stage}")
        record[started_field] = receipt["created_at"]
        record[f"{stage}_invocation_sha256"] = receipt["invocation"][
            "sha256"
        ]
        inventory.append(
            {
                "path": repo_relative(path, repo=repo),
                "sha256": sha256_file(path),
            }
        )

    counters: dict[str, Any] = {
        "schema": COUNTER_SCHEMA,
        "run_id": config["run_id"],
        "counter_truth": "immutable_stage_STARTED_receipts",
        "materialized_view_rebuild": True,
        "source_receipts_n": len(inventory),
        "source_receipts_sha256": sha256_bytes(canonical_json(inventory)),
        "by_job": {key: by_job[key] for key in sorted(by_job)},
        "updated_at": now_iso(),
    }
    for stage, counter_name in STAGE_COUNTERS.items():
        counters[counter_name] = sum(
            1
            for record in by_job.values()
            if f"{stage}_started_at" in record
        )
    return counters


def reconcile_runtime_counters(
    config: Mapping[str, Any],
    *,
    repo: Path = REPO,
) -> dict[str, Any]:
    """Rebuild the counter view, repairing a crash after receipt publication."""

    counter_path = repo_path(
        config["outputs"]["runtime_counters"], repo=repo
    )
    lock_path = repo_path(
        config["outputs"]["runtime_counters_lock"], repo=repo
    )
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+b") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        counters = _derive_runtime_counters(config, repo=repo)
        atomic_json(counter_path, counters)
        fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
    return counters


def begin_stage(
    config: Mapping[str, Any],
    building_id: str,
    arm: str,
    run: str,
    *,
    stage: str,
    invocation_path: Path,
    repo: Path = REPO,
) -> dict[str, Any]:
    """Atomically claim one external stage and increment its exact counter."""

    if stage not in STAGE_COUNTERS:
        raise ReadoutError(f"unknown counted stage: {stage}")
    job = job_dir(config, building_id, arm, run, repo=repo)
    ensure_not_failed(job, repo=repo)
    require_regular(invocation_path, f"{stage} invocation")
    started_path = job / STAGE_STARTED_FILES[stage]
    counter_path = repo_path(config["outputs"]["runtime_counters"], repo=repo)
    lock_path = repo_path(
        config["outputs"]["runtime_counters_lock"], repo=repo
    )
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    key = job_key(building_id, arm, run)
    with lock_path.open("a+b") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        ensure_not_failed(job, repo=repo)
        if started_path.exists() or started_path.is_symlink():
            # The STARTED receipt is authoritative.  Rebuild the materialized
            # counter view before refusing a retry, so an interruption between
            # receipt fsync and counter publication heals deterministically.
            atomic_json(
                counter_path,
                _derive_runtime_counters(config, repo=repo),
            )
            raise ReadoutError(f"{stage} already started; retry forbidden")
        receipt = {
            "schema": JOB_SCHEMA,
            "state": "STARTED",
            "stage": stage,
            "created_at": now_iso(),
            "run_id": config["run_id"],
            "job_key": key,
            "building_id": building_id,
            "arm": arm,
            "replicate": run,
            "invocation": {
                "path": repo_relative(invocation_path, repo=repo),
                "sha256": sha256_file(invocation_path),
            },
            "claim_mode": "exclusive_authoritative_receipt_under_counter_flock",
            "counter_role": "reconciled_materialized_view",
            "retry_allowed": False,
        }
        exclusive_json(started_path, receipt)
        atomic_json(
            counter_path,
            _derive_runtime_counters(config, repo=repo),
        )
        fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
    return receipt


def write_footprint_geojson(
    config: Mapping[str, Any],
    building_id: str,
    output: Path,
    *,
    repo: Path = REPO,
) -> dict[str, Any]:
    if output.exists() or output.is_symlink():
        raise ReadoutError(f"refusing to overwrite footprint subset: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    # Reuse the P0-prime subset function so Roofer receives the exact same
    # one-feature GPKG contract.  GeoJSON is a derived plumbing copy used only
    # by the two legacy readout/classification scripts.
    p0 = p0prime_module(config, repo=repo)
    gpkg = output.with_suffix(".gpkg")
    gpkg_receipt = p0.write_footprint_subset(
        {"footprint": config["footprint"]},
        building_id,
        gpkg,
    )
    command = [
        "ogr2ogr",
        "-f",
        "GeoJSON",
        output.as_posix(),
        gpkg.as_posix(),
        "p0prime_footprint",
        "-nln",
        "footprint",
        "-a_srs",
        config["footprint"]["crs"],
    ]
    process = subprocess.run(
        command,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    if process.returncode:
        raise ReadoutError(
            f"ogr2ogr footprint subset failed exit={process.returncode}: "
            f"{process.stdout[-1000:]}"
        )
    payload = load_json(output)
    features = payload.get("features")
    if not isinstance(features, list) or len(features) != 1:
        raise ReadoutError("per-building footprint GeoJSON does not have one feature")
    properties = features[0].get("properties") or {}
    require_equal(
        str(properties.get(config["footprint"]["id_field"])),
        building_id,
        "footprint building ID",
    )
    return {
        "path": repo_relative(output, repo=repo),
        "sha256": sha256_file(output),
        "feature_count": 1,
        "crs": config["footprint"]["crs"],
        "source_path": config["footprint"]["path"],
        "source_sha256": config["footprint"]["sha256"],
        "source_role": config["footprint"]["role"],
        "roofer_path": gpkg_receipt["path"],
        "roofer_sha256": gpkg_receipt["sha256"],
        "roofer_layer": "p0prime_footprint",
        "derived_geojson_role": "legacy extractor/classifier plumbing only",
        "command": command,
    }


def prepare_one(
    config: Mapping[str, Any],
    building_id: str,
    arm: str,
    run: str,
    *,
    repo: Path = REPO,
) -> dict[str, Any]:
    verify_static_inputs(config, repo=repo)
    metadata = target_metadata(config, building_id, repo=repo)
    training = resolve_training_artifacts(
        config, building_id, arm, run, repo=repo
    )
    p0prime = p0prime_binding(config, building_id, repo=repo)
    job = job_dir(config, building_id, arm, run, repo=repo)
    ensure_not_failed(job, repo=repo)
    materialization_path = job / "materialization.json"
    if job.exists() and any(job.iterdir()):
        raise ReadoutError(
            f"readout job directory is not empty; refuse rematerialization: {job}"
        )
    job.mkdir(parents=True, exist_ok=True)
    footprint = write_footprint_geojson(
        config, building_id, job / "footprint.geojson", repo=repo
    )
    payload = {
        "schema": MATERIALIZATION_SCHEMA,
        "state": "PASSED",
        "created_at": now_iso(),
        "run_id": config["run_id"],
        "task_id": config["task_id"],
        "job_key": job_key(building_id, arm, run),
        "building_id": building_id,
        "arm": arm,
        "replicate": run,
        "target": {
            key: value
            for key, value in metadata.items()
            if key not in {"target_row"}
        },
        "training": {
            "materialization": repo_relative(
                training["materialization_path"], repo=repo
            ),
            "materialization_sha256": training["materialization_sha256"],
            "completed": repo_relative(training["completed_path"], repo=repo),
            "completed_sha256": training["completed_sha256"],
            "checkpoint": repo_relative(training["checkpoint"], repo=repo),
            "checkpoint_sha256": training["checkpoint_sha256"],
            "full_state_manifest": repo_relative(
                training["full_state_manifest"], repo=repo
            ),
            "full_state_manifest_sha256": training[
                "full_state_manifest_sha256"
            ],
            "data_root": repo_relative(training["data_root"], repo=repo),
            "supervision_index": repo_relative(
                training["supervision_index"], repo=repo
            ),
            "train_views": training["train_views"],
        },
        "p0prime": {
            "scores_csv": repo_relative(p0prime["scores_csv"], repo=repo),
            "scores_csv_sha256_at_materialization": p0prime[
                "scores_csv_sha256"
            ],
            "row_sha256": p0prime["row_sha256"],
            "complete": repo_relative(p0prime["complete_path"], repo=repo),
            "complete_sha256": p0prime["complete_sha256"],
        },
        "footprint": footprint,
        "resource_contract": config["resource_lock"],
        "publication": {
            "no_external_stage_started": True,
            "materialization_written_last": True,
        },
    }
    exclusive_json(materialization_path, payload)
    return payload


def validate_materialization(
    config: Mapping[str, Any],
    building_id: str,
    arm: str,
    run: str,
    *,
    repo: Path = REPO,
) -> tuple[Path, dict[str, Any]]:
    job = job_dir(config, building_id, arm, run, repo=repo)
    ensure_not_failed(job, repo=repo)
    path = job / "materialization.json"
    payload = load_receipt(
        path, schema=MATERIALIZATION_SCHEMA, state="PASSED"
    )
    require_equal(payload.get("job_key"), job_key(building_id, arm, run), "readout materialization job")
    training = resolve_training_artifacts(
        config, building_id, arm, run, repo=repo
    )
    binding = payload["training"]
    require_equal(
        sha256_file(training["completed_path"]),
        binding["completed_sha256"],
        "training completion since readout materialization",
    )
    require_equal(
        sha256_file(training["checkpoint"]),
        binding["checkpoint_sha256"],
        "training checkpoint since readout materialization",
    )
    footprint = repo_path(payload["footprint"]["path"], repo=repo)
    verify_hash(
        footprint, payload["footprint"]["sha256"], "readout footprint subset"
    )
    roofer_footprint = repo_path(
        payload["footprint"]["roofer_path"], repo=repo
    )
    verify_hash(
        roofer_footprint,
        payload["footprint"]["roofer_sha256"],
        "Roofer footprint GPKG subset",
    )
    p0prime = p0prime_binding(config, building_id, repo=repo)
    require_equal(
        p0prime["row_sha256"],
        payload["p0prime"]["row_sha256"],
        "P0-prime score row since readout materialization",
    )
    require_equal(
        p0prime["complete_sha256"],
        payload["p0prime"]["complete_sha256"],
        "P0-prime completion since readout materialization",
    )
    return path, payload


def extract_argv(
    config: Mapping[str, Any],
    materialization: Mapping[str, Any],
    output: str,
) -> list[str]:
    pc = config["pointcloudification"]
    short_id = materialization["building_id"].replace("DEBY_LOD2_", "", 1)
    argv = [
        config["pointcloudification"]["script"],
        "--ckpt",
        materialization["training"]["checkpoint"],
        "--out",
        output,
        "--downscale",
        str(pc["downscale"]),
        "--voxel",
        str(pc["voxel_m"]),
        "--alpha",
        str(pc["alpha_min_exclusive"]),
        "--min-obs",
        str(pc["minimum_observations"]),
        "--buffer",
        str(pc["footprint_buffer_m"]),
        "--geojson",
        materialization["footprint"]["path"],
        "--data-root",
        materialization["training"]["data_root"],
        "--max-views",
        str(pc["maximum_views"]),
        "--sh-degree",
        str(pc["sh_degree"]),
        "--targets",
        short_id,
    ]
    if not pc["semantic_pass"]:
        argv.append("--no-sem")
    return argv


def authorize_extract(
    config: Mapping[str, Any],
    building_id: str,
    arm: str,
    run: str,
    *,
    repo: Path = REPO,
) -> dict[str, Any]:
    materialization_path, materialization = validate_materialization(
        config, building_id, arm, run, repo=repo
    )
    job = materialization_path.parent
    output = job / "pointcloud" / "readout.npz"
    if output.exists() or output.is_symlink():
        raise ReadoutError("point-cloud output exists before readout authorization")
    output.parent.mkdir(parents=True, exist_ok=True)
    invocation_path = job / "extract_invocation.json"
    if invocation_path.exists() or invocation_path.is_symlink():
        raise ReadoutError("readout invocation already exists; retry forbidden")
    environment = writable_readout_environment(config, repo=repo, create=True)
    jit_environment = jit_build_environment(config)
    invocation = {
        "schema": "jointbuildgs.fusion_w1.extract_invocation.v1",
        "state": "AUTHORIZED",
        "created_at": now_iso(),
        "job_key": job_key(building_id, arm, run),
        "building_id": building_id,
        "arm": arm,
        "replicate": run,
        "image": config["pointcloudification"]["image"],
        "image_id": config["pointcloudification"]["image_id"],
        "argv": extract_argv(
            config, materialization, repo_relative(output, repo=repo)
        ),
        "output": repo_relative(output, repo=repo),
        "training_checkpoint": {
            "path": materialization["training"]["checkpoint"],
            "sha256": materialization["training"]["checkpoint_sha256"],
        },
        "training_materialization": {
            "path": repo_relative(materialization_path, repo=repo),
            "sha256": sha256_file(materialization_path),
        },
        "footprint": materialization["footprint"],
        "reference_inputs_present": False,
        "resource_contract": config["resource_lock"],
        "environment": environment,
        "jit_build_environment": jit_environment,
        "retry_allowed": False,
    }
    exclusive_json(invocation_path, invocation)
    begin_stage(
        config,
        building_id,
        arm,
        run,
        stage="readout",
        invocation_path=invocation_path,
        repo=repo,
    )
    return invocation


def invocation_argv(
    config: Mapping[str, Any],
    building_id: str,
    arm: str,
    run: str,
    filename: str,
    schema: str,
    *,
    repo: Path = REPO,
) -> list[str]:
    job = job_dir(config, building_id, arm, run, repo=repo)
    ensure_not_failed(job, repo=repo)
    invocation = load_receipt(
        job / filename, schema=schema, state="AUTHORIZED"
    )
    argv = invocation.get("argv")
    if not isinstance(argv, list) or not all(
        isinstance(value, str) and value for value in argv
    ):
        raise ReadoutError(f"{filename} argv is not a nonempty string list")
    require_equal(
        invocation.get("job_key"),
        job_key(building_id, arm, run),
        f"{filename} job key",
    )
    stage_by_filename = {
        "extract_invocation.json": "readout",
        "roofer_invocation.json": "roofer",
    }
    if filename in stage_by_filename:
        verify_started_invocation_binding(
            job,
            stage_by_filename[filename],
            job / filename,
            repo=repo,
        )
    return list(argv)


def invocation_environment(
    config: Mapping[str, Any],
    building_id: str,
    arm: str,
    run: str,
    filename: str,
    schema: str,
    *,
    repo: Path = REPO,
) -> list[str]:
    job = job_dir(config, building_id, arm, run, repo=repo)
    ensure_not_failed(job, repo=repo)
    invocation_path = job / filename
    invocation = load_receipt(invocation_path, schema=schema, state="AUTHORIZED")
    require_equal(
        invocation.get("job_key"),
        job_key(building_id, arm, run),
        f"{filename} environment job key",
    )
    verify_started_invocation_binding(job, "readout", invocation_path, repo=repo)
    environment = writable_readout_environment(
        config, repo=repo, create=False, require_ready=True
    )
    require_equal(invocation.get("environment"), environment, f"{filename} environment")
    values = environment["container_values"]
    jit_environment = jit_build_environment(config)
    require_equal(
        invocation.get("jit_build_environment"),
        jit_environment,
        f"{filename} JIT build environment",
    )
    combined = {**values, **jit_environment}
    return [f"{key}={combined[key]}" for key in sorted(combined)]


def verify_started_invocation_binding(
    job: Path,
    stage: str,
    invocation_path: Path,
    *,
    repo: Path = REPO,
) -> dict[str, Any]:
    started = load_receipt(
        job / STAGE_STARTED_FILES[stage],
        schema=JOB_SCHEMA,
        state="STARTED",
    )
    require_equal(started.get("stage"), stage, f"{stage} started stage")
    require_equal(
        started["invocation"]["path"],
        repo_relative(invocation_path, repo=repo),
        f"{stage} started invocation path",
    )
    verify_hash(
        invocation_path,
        started["invocation"]["sha256"],
        f"{stage} authorized invocation",
    )
    return started


def inspect_npz(
    path: Path,
    config: Mapping[str, Any],
    *,
    repo: Path = REPO,
) -> dict[str, Any]:
    try:
        import numpy as np
    except ImportError as exc:  # pragma: no cover - tools image contract
        raise ReadoutError("numpy is required in the tools image") from exc
    require_regular(path, "readout NPZ")
    try:
        with np.load(path, allow_pickle=False) as data:
            names = sorted(data.files)
            if "P_utm_clean" not in data or "P_utm" not in data:
                raise ReadoutError("readout NPZ lacks P_utm/P_utm_clean")
            raw = np.asarray(data["P_utm"], dtype=np.float64)
            clean = np.asarray(data["P_utm_clean"], dtype=np.float64)
            if raw.ndim != 2 or raw.shape[1] != 3 or len(raw) == 0:
                raise ReadoutError(f"P_utm shape is invalid: {raw.shape}")
            if clean.ndim != 2 or clean.shape[1] != 3 or len(clean) == 0:
                raise ReadoutError(f"P_utm_clean shape is invalid: {clean.shape}")
            if not np.isfinite(raw).all() or not np.isfinite(clean).all():
                raise ReadoutError("readout NPZ contains non-finite XYZ")
            voxel = float(np.asarray(data["voxel"]).reshape(()))
            downscale = float(np.asarray(data["downscale"]).reshape(()))
            require_equal(
                voxel,
                float(config["pointcloudification"]["voxel_m"]),
                "readout voxel",
            )
            require_equal(
                downscale,
                float(config["pointcloudification"]["downscale"]),
                "readout downscale",
            )
            if "P_class" in data or "P_class_clean" in data:
                raise ReadoutError(
                    "semantic output is present despite the locked --no-sem readout"
                )
            minimum = clean.min(axis=0)
            maximum = clean.max(axis=0)
    except (OSError, ValueError) as exc:
        if isinstance(exc, ReadoutError):
            raise
        raise ReadoutError(f"cannot validate readout NPZ: {exc}") from exc
    return {
        "path": repo_relative(path, repo=repo),
        "sha256": sha256_file(path),
        "arrays": names,
        "raw_points_n": int(len(raw)),
        "clean_points_n": int(len(clean)),
        "bounds_min": minimum.astype(float).tolist(),
        "bounds_max": maximum.astype(float).tolist(),
        "voxel_m": voxel,
        "downscale": downscale,
        "crs": config["pointcloudification"]["crs"],
        "semantic_arrays_present": False,
    }


def accept_extract(
    config: Mapping[str, Any],
    building_id: str,
    arm: str,
    run: str,
    *,
    wall_seconds: float,
    repo: Path = REPO,
) -> dict[str, Any]:
    job = job_dir(config, building_id, arm, run, repo=repo)
    ensure_not_failed(job, repo=repo)
    invocation_path = job / "extract_invocation.json"
    invocation = load_receipt(
        invocation_path,
        schema="jointbuildgs.fusion_w1.extract_invocation.v1",
        state="AUTHORIZED",
    )
    verify_started_invocation_binding(
        job,
        "readout",
        invocation_path,
        repo=repo,
    )
    checkpoint = repo_path(
        invocation["training_checkpoint"]["path"], repo=repo
    )
    verify_hash(
        checkpoint,
        invocation["training_checkpoint"]["sha256"],
        "checkpoint before accepting readout",
    )
    output = repo_path(invocation["output"], repo=repo)
    stats = inspect_npz(output, config, repo=repo)
    receipt = {
        "schema": "jointbuildgs.fusion_w1.extract_receipt.v1",
        "state": "COMPLETE",
        "created_at": now_iso(),
        "job_key": job_key(building_id, arm, run),
        "building_id": building_id,
        "arm": arm,
        "replicate": run,
        "invocation": {
            "path": repo_relative(invocation_path, repo=repo),
            "sha256": sha256_file(invocation_path),
        },
        "pointcloud": stats,
        "wall_seconds": float(wall_seconds),
        "resource_contract": config["resource_lock"],
        "partial_output_accepted": False,
    }
    exclusive_json(job / "extract_receipt.json", receipt)
    return receipt


def classification_argv(
    config: Mapping[str, Any],
    materialization: Mapping[str, Any],
    extract: Mapping[str, Any],
    output_dir: str,
) -> list[str]:
    return [
        config["classification"]["script"],
        "--tsdf",
        extract["pointcloud"]["path"],
        "--bid",
        materialization["building_id"],
        "--geojson",
        materialization["footprint"]["path"],
        "--buffer",
        str(config["pointcloudification"]["footprint_buffer_m"]),
        "--target-density",
        str(config["classification"]["target_density"]),
        "--seed",
        "0",
        "--outdir",
        output_dir,
        "--tag",
        "fused",
    ]


def authorize_classification(
    config: Mapping[str, Any],
    building_id: str,
    arm: str,
    run: str,
    *,
    repo: Path = REPO,
) -> dict[str, Any]:
    materialization_path, materialization = validate_materialization(
        config, building_id, arm, run, repo=repo
    )
    job = materialization_path.parent
    extract_path = job / "extract_receipt.json"
    extract = load_receipt(
        extract_path,
        schema="jointbuildgs.fusion_w1.extract_receipt.v1",
        state="COMPLETE",
    )
    pointcloud = repo_path(extract["pointcloud"]["path"], repo=repo)
    verify_hash(pointcloud, extract["pointcloud"]["sha256"], "readout point cloud")
    outdir = job / "classification"
    if outdir.exists() or outdir.is_symlink():
        raise ReadoutError("classification output directory already exists")
    outdir.mkdir(parents=True)
    invocation_path = job / "classification_invocation.json"
    invocation = {
        "schema": "jointbuildgs.fusion_w1.classification_invocation.v1",
        "state": "AUTHORIZED",
        "created_at": now_iso(),
        "job_key": job_key(building_id, arm, run),
        "building_id": building_id,
        "arm": arm,
        "replicate": run,
        "image": config["classification"]["image"],
        "image_id": config["classification"]["image_id"],
        "argv": classification_argv(
            config,
            materialization,
            extract,
            repo_relative(outdir, repo=repo),
        ),
        "method": config["classification"]["method"],
        "readout_receipt": {
            "path": repo_relative(extract_path, repo=repo),
            "sha256": sha256_file(extract_path),
        },
        "output_dir": repo_relative(outdir, repo=repo),
        "downsample_applied": False,
        "resource_contract": config["resource_lock"],
        "retry_allowed": False,
    }
    exclusive_json(invocation_path, invocation)
    return invocation


def inspect_classified_las(
    config: Mapping[str, Any],
    path: Path,
    *,
    repo: Path = REPO,
) -> dict[str, Any]:
    module = p0prime_module(config, repo=repo)
    actual = module.inspect_las(path)
    require_equal(actual.get("epsg"), 25832, "classified LAS EPSG")
    classes = {int(key) for key in actual["class_counts"]}
    allowed = {int(value) for value in config["classification"]["allowed_classes"]}
    required = {int(value) for value in config["classification"]["required_classes"]}
    if not classes.issubset(allowed):
        raise ReadoutError(f"classified LAS has forbidden classes: {sorted(classes)}")
    if not required.issubset(classes):
        raise ReadoutError(f"classified LAS lacks required classes: {sorted(required - classes)}")
    for value in required:
        if int(actual["class_counts"][str(value)]) <= 0:
            raise ReadoutError(f"classified LAS class {value} has no points")
    return {
        "path": repo_relative(path, repo=repo),
        "sha256": sha256_file(path),
        "point_count": int(actual["point_count"]),
        "class_counts": actual["class_counts"],
        "epsg": actual["epsg"],
        "las_version": actual["version"],
        "point_format": actual["point_format"],
        "dimensions": actual["dimensions"],
    }


def accept_classification(
    config: Mapping[str, Any],
    building_id: str,
    arm: str,
    run: str,
    *,
    wall_seconds: float,
    repo: Path = REPO,
) -> dict[str, Any]:
    job = job_dir(config, building_id, arm, run, repo=repo)
    ensure_not_failed(job, repo=repo)
    invocation_path = job / "classification_invocation.json"
    invocation = load_receipt(
        invocation_path,
        schema="jointbuildgs.fusion_w1.classification_invocation.v1",
        state="AUTHORIZED",
    )
    output = repo_path(invocation["output_dir"], repo=repo)
    stem = f"{building_id}_fused"
    metrics_path = output / f"{stem}_metrics.json"
    metrics = load_json(metrics_path)
    require_equal(metrics.get("bid"), building_id, "classification metrics building")
    require_equal(metrics.get("tag"), "fused", "classification metrics tag")
    classified = output / f"{stem}_classified.las"
    actual = inspect_classified_las(config, classified, repo=repo)
    declared = metrics.get("classified_las")
    if declared:
        require_equal(
            repo_path(declared, repo=repo),
            classified.resolve(),
            "classification metrics LAS path",
        )
    require_equal(metrics.get("voxel"), None, "classification voxel downsample")
    receipt = {
        "schema": "jointbuildgs.fusion_w1.classification_receipt.v1",
        "state": "COMPLETE",
        "created_at": now_iso(),
        "job_key": job_key(building_id, arm, run),
        "building_id": building_id,
        "arm": arm,
        "replicate": run,
        "invocation": {
            "path": repo_relative(invocation_path, repo=repo),
            "sha256": sha256_file(invocation_path),
        },
        "classified_las": actual,
        "metrics": {
            "path": repo_relative(metrics_path, repo=repo),
            "sha256": sha256_file(metrics_path),
            "n_clip": int(metrics["n_clip"]),
            "n_used": int(metrics["n_used"]),
            "n_building_in_fp": int(metrics["n_building_in_fp"]),
            "roof_density": optional_float(metrics.get("roof_density")),
            "footprint_area": optional_float(metrics.get("footprint_area")),
        },
        "method": config["classification"]["method"],
        "downsample_applied": False,
        "wall_seconds": float(wall_seconds),
        "resource_contract": config["resource_lock"],
    }
    exclusive_json(job / "classification_receipt.json", receipt)
    return receipt


def roofer_argv(
    config: Mapping[str, Any],
    classified_las: str,
    footprint: str,
    output_dir: str,
) -> list[str]:
    return [
        *[str(value) for value in config["roofer"]["parameters"]],
        classified_las,
        footprint,
        output_dir,
    ]


def container_repo_path(path: Path, *, repo: Path = REPO) -> str:
    """Map a validated repository path to the wrapper's fixed container mount."""

    return f"/workspace/JointBuildGS/{repo_relative(path, repo=repo)}"


def authorize_roofer(
    config: Mapping[str, Any],
    building_id: str,
    arm: str,
    run: str,
    *,
    repo: Path = REPO,
) -> dict[str, Any]:
    materialization_path, materialization = validate_materialization(
        config, building_id, arm, run, repo=repo
    )
    job = materialization_path.parent
    classification_path = job / "classification_receipt.json"
    classification = load_receipt(
        classification_path,
        schema="jointbuildgs.fusion_w1.classification_receipt.v1",
        state="COMPLETE",
    )
    classified = repo_path(
        classification["classified_las"]["path"], repo=repo
    )
    verify_hash(
        classified,
        classification["classified_las"]["sha256"],
        "classified LAS before Roofer",
    )
    footprint = repo_path(
        materialization["footprint"]["roofer_path"], repo=repo
    )
    verify_hash(
        footprint,
        materialization["footprint"]["roofer_sha256"],
        "footprint before Roofer",
    )
    output = job / "roofer"
    if output.exists() or output.is_symlink():
        raise ReadoutError("Roofer output directory already exists")
    output.mkdir()
    invocation_path = job / "roofer_invocation.json"
    invocation = {
        "schema": "jointbuildgs.fusion_w1.roofer_invocation.v1",
        "state": "AUTHORIZED",
        "created_at": now_iso(),
        "job_key": job_key(building_id, arm, run),
        "building_id": building_id,
        "arm": arm,
        "replicate": run,
        "image": config["roofer"]["image"],
        "argv": roofer_argv(
            config,
            container_repo_path(classified, repo=repo),
            container_repo_path(footprint, repo=repo),
            container_repo_path(output, repo=repo),
        ),
        "classified_las": classification["classified_las"],
        "classification_receipt": {
            "path": repo_relative(classification_path, repo=repo),
            "sha256": sha256_file(classification_path),
        },
        "footprint": {
            **materialization["footprint"],
            "path": materialization["footprint"]["roofer_path"],
            "sha256": materialization["footprint"]["roofer_sha256"],
        },
        "output_dir": repo_relative(output, repo=repo),
        "resource_contract": config["resource_lock"],
        "outer_parallelism": 1,
        "retry_allowed": False,
    }
    exclusive_json(invocation_path, invocation)
    begin_stage(
        config,
        building_id,
        arm,
        run,
        stage="roofer",
        invocation_path=invocation_path,
        repo=repo,
    )
    return invocation


def accept_roofer(
    config: Mapping[str, Any],
    building_id: str,
    arm: str,
    run: str,
    *,
    wall_seconds: float,
    repo: Path = REPO,
) -> dict[str, Any]:
    job = job_dir(config, building_id, arm, run, repo=repo)
    ensure_not_failed(job, repo=repo)
    invocation_path = job / "roofer_invocation.json"
    invocation = load_receipt(
        invocation_path,
        schema="jointbuildgs.fusion_w1.roofer_invocation.v1",
        state="AUTHORIZED",
    )
    verify_started_invocation_binding(
        job,
        "roofer",
        invocation_path,
        repo=repo,
    )
    output = repo_path(invocation["output_dir"], repo=repo)
    files = sorted(output.glob("*.city.jsonl"))
    if not files:
        raise ReadoutError("Roofer produced no CityJSONSeq output")
    records = []
    for path in files:
        require_regular(path, "Roofer CityJSONSeq")
        records.append(
            {
                "path": repo_relative(path, repo=repo),
                "sha256": sha256_file(path),
                "size": path.stat().st_size,
            }
        )
    receipt = {
        "schema": "jointbuildgs.fusion_w1.roofer_receipt.v1",
        "state": "COMPLETE",
        "created_at": now_iso(),
        "job_key": job_key(building_id, arm, run),
        "building_id": building_id,
        "arm": arm,
        "replicate": run,
        "invocation": {
            "path": repo_relative(invocation_path, repo=repo),
            "sha256": sha256_file(invocation_path),
        },
        "image": config["roofer"]["image"],
        "argv": invocation["argv"],
        "jsonseq_outputs": records,
        "wall_seconds": float(wall_seconds),
        "outer_parallelism": 1,
        "memory_limit": config["resource_lock"]["memory"],
    }
    exclusive_json(job / "roofer_receipt.json", receipt)
    return receipt


def baseline_row(
    config: Mapping[str, Any],
    building_id: str,
    *,
    role: str,
    repo: Path = REPO,
) -> dict[str, str]:
    spec = config["scoring"]["paired_baseline"]
    if role == "laser":
        model_id, source_role = spec["laser_model_id"], spec["laser_role"]
    elif role == "image":
        model_id, source_role = spec["image_model_id"], spec["image_role"]
    else:
        raise ReadoutError(f"unknown baseline role: {role}")
    rows = [
        row
        for row in read_csv(repo_path(spec["path"], repo=repo))
        if row.get("building_id") == building_id
        and row.get("model_id") == model_id
        and row.get("role") == source_role
    ]
    if len(rows) != 1:
        raise ReadoutError(
            f"{role} paired baseline row is not unique: {building_id}"
        )
    return rows[0]


def paired_rms_fields(
    current: float | None,
    baseline: Mapping[str, Any],
    prefix: str,
) -> dict[str, Any]:
    baseline_rms = optional_float(baseline.get("roof_rms_m"))
    eligible = current is not None and baseline_rms is not None
    return {
        f"{prefix}_eligible": eligible,
        f"{prefix}_denominator_contribution": 1 if eligible else 0,
        f"{prefix}_current_m": current if eligible else None,
        f"{prefix}_baseline_m": baseline_rms if eligible else None,
        f"{prefix}_delta_m": (
            current - baseline_rms if eligible else None  # type: ignore[operator]
        ),
    }


SCORE_FIELDS = [
    "schema",
    "row_type",
    "task_id",
    "run_id",
    "building_id",
    "arm",
    "run",
    "job_key",
    "processing_order",
    "tier",
    "cohort",
    "source_cell_label",
    "texture_stratum",
    "texture_low_gradient_fraction",
    "texture_threshold",
    "training_materialization",
    "training_materialization_sha256",
    "training_completed",
    "training_completed_sha256",
    "checkpoint",
    "checkpoint_sha256",
    "readout_npz",
    "readout_npz_sha256",
    "readout_raw_points_n",
    "readout_clean_points_n",
    "readout_wall_seconds",
    "classification_method",
    "classified_las",
    "classified_las_sha256",
    "classified_point_count",
    "class1_count",
    "class2_count",
    "class6_count",
    "classification_wall_seconds",
    "footprint",
    "footprint_sha256",
    "roofer_image",
    "roofer_parameters",
    "roofer_wall_seconds",
    "roofer_feature_present",
    "rf_success",
    "rf_pointcloud_unusable",
    "rf_extrusion_mode",
    "assembly_lod2_success",
    "assembly_reason",
    "has_lod22_geometry",
    "lod1_fallback",
    "canonical_combined_status",
    "canonical_combined_reason",
    "val3dity_report_feature_present",
    "val3dity_valid",
    "val3dity_exit_code",
    "val3dity_report",
    "val3dity_report_sha256",
    "cityjson",
    "cityjson_sha256",
    "cityjson_crs",
    "geometry_roof_surface_present",
    "plane_match_count",
    "plane_precision",
    "plane_recall",
    "plane_f1",
    "roof_face_count_model",
    "roof_face_count_ref",
    "face_count_ratio",
    "roof_rms_m",
    "roof_hausdorff_m",
    "roof_distance_samples",
    "roof_completeness",
    "model_roof_xy_area_m2",
    "reference_roof_xy_area_m2",
    "roof_overlap_xy_area_m2",
    "xy_alignment",
    "xy_overlap_ratio",
    "score_time_z_shift_m",
    "rms_pair_laser_eligible",
    "rms_pair_laser_denominator_contribution",
    "rms_pair_laser_current_m",
    "rms_pair_laser_baseline_m",
    "rms_pair_laser_delta_m",
    "rms_pair_image_eligible",
    "rms_pair_image_denominator_contribution",
    "rms_pair_image_current_m",
    "rms_pair_image_baseline_m",
    "rms_pair_image_delta_m",
    "rms_pair_denominator_definition",
    "p0prime_status",
    "p0prime_assembly_lod2_success",
    "p0prime_val3dity_valid",
    "p0prime_plane_f1",
    "p0prime_roof_rms_m",
    "p0prime_roof_completeness",
    "p0prime_face_count_ratio",
    "delta_assembly_lod2_vs_p0prime",
    "delta_val3dity_valid_vs_p0prime",
    "delta_plane_f1_vs_p0prime",
    "delta_roof_rms_vs_p0prime_m",
    "delta_roof_completeness_vs_p0prime",
    "delta_face_count_ratio_vs_p0prime",
    "panel_png",
    "panel_png_sha256",
    "panel_materials",
    "panel_materials_sha256",
    "reference_role",
    "reference_absolute_metric_caveat",
    "readout_runs_started",
    "roofer_runs_started",
    "scoring_runs_started",
    "score_wall_seconds",
    "status",
]

SUMMARY_FIELDS = [
    "schema",
    "row_type",
    "task_id",
    "run_id",
    "status",
    "tier",
    "arm",
    "run",
    "score_rows_n",
    "core_rows_n",
    "extension_rows_n",
    "textured_rows_n",
    "textureless_rows_n",
    "assembly_lod2_success_n",
    "lod1_fallback_n",
    "val3dity_valid_n",
    "plane_f1_median",
    "roof_rms_m_median",
    "roof_completeness_median",
    "face_count_ratio_median",
    "rms_pair_laser_denominator_n",
    "rms_pair_laser_delta_m_median",
    "rms_pair_image_denominator_n",
    "rms_pair_image_delta_m_median",
    "delta_plane_f1_vs_p0prime_median",
    "delta_roof_rms_vs_p0prime_m_median",
    "delta_roof_completeness_vs_p0prime_median",
    "delta_face_count_ratio_vs_p0prime_median",
    "scores_csv",
    "scores_csv_sha256",
    "observation_only",
]


def finite_median(rows: Sequence[Mapping[str, Any]], field: str) -> float | None:
    values = sorted(
        value
        for row in rows
        if (value := optional_float(row.get(field))) is not None
    )
    if not values:
        return None
    middle = len(values) // 2
    if len(values) % 2:
        return values[middle]
    return 0.5 * (values[middle - 1] + values[middle])


def finalize_partial(
    config: Mapping[str, Any],
    *,
    repo: Path = REPO,
) -> dict[str, Any]:
    """Publish morning-readable score/summary CSVs without starting a stage."""

    scores = repo_path(config["outputs"]["scores_csv"], repo=repo)
    summary = repo_path(config["outputs"]["summary_csv"], repo=repo)
    counter_path = repo_path(
        config["outputs"]["runtime_counters"], repo=repo
    )
    counter_existed_before = counter_path.is_file()
    counter_sha_before = (
        sha256_file(counter_path) if counter_existed_before else None
    )
    if scores.is_symlink() or summary.is_symlink():
        raise ReadoutError("partial finalize refuses symlink CSV outputs")
    lock = scores.with_suffix(scores.suffix + ".lock")
    lock.parent.mkdir(parents=True, exist_ok=True)
    with lock.open("a+b") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        if scores.is_file():
            require_equal(
                csv_header(scores),
                SCORE_FIELDS,
                "w1_scores_building.csv fixed header",
            )
            score_rows = read_csv(scores)
        else:
            atomic_csv(scores, [], SCORE_FIELDS)
            score_rows = []
        for row in score_rows:
            if (
                row.get("tier") not in {"surface", "height", "outline"}
                or row.get("arm") not in ARMS
                or row.get("run") not in RUNS
            ):
                raise ReadoutError(
                    "score row has an invalid tier/arm/run for partial summary"
                )
        scores_sha = sha256_file(scores)
        summary_rows: list[dict[str, Any]] = []
        for tier in ("surface", "height", "outline"):
            for arm in ARMS:
                for run in RUNS:
                    selected = [
                        row
                        for row in score_rows
                        if row.get("tier") == tier
                        and row.get("arm") == arm
                        and row.get("run") == run
                    ]
                    summary_rows.append(
                        {
                            "schema": "jointbuildgs.fusion_w1.summary.v1",
                            "row_type": "tier_arm_run_observation",
                            "task_id": config["task_id"],
                            "run_id": config["run_id"],
                            "status": (
                                "MEASURED" if selected else "NOT_MEASURED"
                            ),
                            "tier": tier,
                            "arm": arm,
                            "run": run,
                            "score_rows_n": len(selected),
                            "core_rows_n": sum(
                                row.get("cohort") == "core"
                                for row in selected
                            ),
                            "extension_rows_n": sum(
                                row.get("cohort") == "extension"
                                for row in selected
                            ),
                            "textured_rows_n": sum(
                                row.get("texture_stratum") == "textured"
                                for row in selected
                            ),
                            "textureless_rows_n": sum(
                                row.get("texture_stratum") == "textureless"
                                for row in selected
                            ),
                            "assembly_lod2_success_n": sum(
                                truth(row.get("assembly_lod2_success"))
                                for row in selected
                            ),
                            "lod1_fallback_n": sum(
                                truth(row.get("lod1_fallback"))
                                for row in selected
                            ),
                            "val3dity_valid_n": sum(
                                truth(row.get("val3dity_valid"))
                                for row in selected
                            ),
                            "plane_f1_median": finite_median(
                                selected, "plane_f1"
                            ),
                            "roof_rms_m_median": finite_median(
                                selected, "roof_rms_m"
                            ),
                            "roof_completeness_median": finite_median(
                                selected, "roof_completeness"
                            ),
                            "face_count_ratio_median": finite_median(
                                selected, "face_count_ratio"
                            ),
                            "rms_pair_laser_denominator_n": sum(
                                int(
                                    optional_float(
                                        row.get(
                                            "rms_pair_laser_denominator_contribution"
                                        )
                                    )
                                    or 0
                                )
                                for row in selected
                            ),
                            "rms_pair_laser_delta_m_median": finite_median(
                                selected, "rms_pair_laser_delta_m"
                            ),
                            "rms_pair_image_denominator_n": sum(
                                int(
                                    optional_float(
                                        row.get(
                                            "rms_pair_image_denominator_contribution"
                                        )
                                    )
                                    or 0
                                )
                                for row in selected
                            ),
                            "rms_pair_image_delta_m_median": finite_median(
                                selected, "rms_pair_image_delta_m"
                            ),
                            "delta_plane_f1_vs_p0prime_median": finite_median(
                                selected, "delta_plane_f1_vs_p0prime"
                            ),
                            "delta_roof_rms_vs_p0prime_m_median": finite_median(
                                selected, "delta_roof_rms_vs_p0prime_m"
                            ),
                            "delta_roof_completeness_vs_p0prime_median": finite_median(
                                selected,
                                "delta_roof_completeness_vs_p0prime",
                            ),
                            "delta_face_count_ratio_vs_p0prime_median": finite_median(
                                selected,
                                "delta_face_count_ratio_vs_p0prime",
                            ),
                            "scores_csv": repo_relative(scores, repo=repo),
                            "scores_csv_sha256": scores_sha,
                            "observation_only": True,
                        }
                    )
        atomic_csv(summary, summary_rows, SUMMARY_FIELDS)
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    counter_existed_after = counter_path.is_file()
    counter_sha_after = (
        sha256_file(counter_path) if counter_existed_after else None
    )
    require_equal(
        counter_existed_after,
        counter_existed_before,
        "partial finalize counter-file existence",
    )
    require_equal(
        counter_sha_after,
        counter_sha_before,
        "partial finalize counter SHA256",
    )
    return {
        "schema": "jointbuildgs.fusion_w1.partial_finalize.v1",
        "state": "PUBLISHED",
        "created_at": now_iso(),
        "scores_csv": repo_relative(scores, repo=repo),
        "scores_csv_sha256": sha256_file(scores),
        "score_rows_n": len(score_rows),
        "summary_csv": repo_relative(summary, repo=repo),
        "summary_csv_sha256": sha256_file(summary),
        "summary_rows_n": len(summary_rows),
        "not_measured_rows_n": sum(
            row["status"] == "NOT_MEASURED" for row in summary_rows
        ),
        "stage_counters_touched": False,
        "counter_existed_before": counter_existed_before,
        "counter_existed_after": counter_existed_after,
        "observation_only": True,
    }


def upsert_score_row(
    config: Mapping[str, Any],
    row: Mapping[str, Any],
    *,
    repo: Path = REPO,
) -> None:
    path = repo_path(config["outputs"]["scores_csv"], repo=repo)
    lock = path.with_suffix(path.suffix + ".lock")
    lock.parent.mkdir(parents=True, exist_ok=True)
    identity = (str(row["building_id"]), str(row["arm"]), str(row["run"]))
    with lock.open("a+b") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        rows = read_csv(path) if path.is_file() else []
        existing = [
            value
            for value in rows
            if (
                value.get("building_id"),
                value.get("arm"),
                value.get("run"),
            )
            == identity
        ]
        if existing:
            raise ReadoutError(f"incremental score row already exists: {identity}")
        rows.append(dict(row))
        rows.sort(
            key=lambda value: (
                int(value["processing_order"]),
                ARMS.index(str(value["arm"])),
                RUNS.index(str(value["run"])),
            )
        )
        atomic_csv(path, rows, SCORE_FIELDS)
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def counter_snapshot(
    config: Mapping[str, Any],
    key: str,
    *,
    repo: Path = REPO,
) -> dict[str, int]:
    path = repo_path(config["outputs"]["runtime_counters"], repo=repo)
    counters = reconcile_runtime_counters(config, repo=repo)
    require_equal(
        sha256_file(path),
        sha256_bytes(canonical_json(counters)),
        "reconciled runtime counter publication",
    )
    record = counters.get("by_job", {}).get(key, {})
    for stage in STAGE_COUNTERS:
        if f"{stage}_started_at" not in record:
            raise ReadoutError(f"counter lacks {stage} start for completed score job")
    return {
        name: int(counters[name]) for name in STAGE_COUNTERS.values()
    }


def _surface_boundaries(surface: Any) -> Iterable[Any]:
    polygon = surface.polygon
    if polygon.geom_type == "Polygon":
        yield polygon
    elif polygon.geom_type == "MultiPolygon":
        yield from polygon.geoms


def _scatter_points(ax: Any, points: Any, *, mode: str, title: str) -> None:
    import numpy as np

    values = np.asarray(points, dtype=float)
    if len(values) > 60000:
        index = np.linspace(0, len(values) - 1, 60000, dtype=np.int64)
        values = values[index]
    if mode == "xy":
        ax.scatter(values[:, 0], values[:, 1], s=0.25, alpha=0.5)
        ax.set_aspect("equal", adjustable="box")
        ax.set_xlabel("E")
        ax.set_ylabel("N")
    else:
        ax.scatter(values[:, 0], values[:, 2], s=0.25, alpha=0.5)
        ax.set_xlabel("E")
        ax.set_ylabel("Z")
    ax.set_title(title, fontsize=8)
    ax.grid(alpha=0.15)


def _plot_surfaces(ax: Any, surfaces: Sequence[Any], title: str) -> None:
    for surface in surfaces:
        for polygon in _surface_boundaries(surface):
            x, y = polygon.exterior.xy
            ax.fill(x, y, alpha=0.35)
            ax.plot(x, y, linewidth=0.8)
    ax.set_aspect("equal", adjustable="box")
    ax.set_title(title, fontsize=8)
    ax.grid(alpha=0.15)


def render_panel(
    config: Mapping[str, Any],
    materialization: Mapping[str, Any],
    p0prime: Mapping[str, Any],
    extract: Mapping[str, Any],
    cityjson: Path,
    prediction: Sequence[Any],
    references: Sequence[Any],
    *,
    repo: Path = REPO,
) -> tuple[Path, Path]:
    """Render the fixed six-material panel, including a mask-derived image crop."""

    try:
        import laspy
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import numpy as np
        from PIL import Image
    except ImportError as exc:  # pragma: no cover - tools image contract
        raise ReadoutError(f"panel dependency missing in tools image: {exc}") from exc

    training = materialization["training"]
    supervision_index = repo_path(training["supervision_index"], repo=repo)
    supervision_rows = read_csv(supervision_index)
    train_views = list(training["train_views"])
    image_name = train_views[0]
    matches = [
        row for row in supervision_rows if row.get("image_name") == image_name
    ]
    if len(matches) != 1:
        raise ReadoutError("panel view is not unique in supervision index")
    support_mask = repo_path(matches[0]["photo_support_mask_path"], repo=repo)
    require_regular(support_mask, "panel photo support mask")
    image_path = (
        repo_path(training["data_root"], repo=repo) / "images" / image_name
    )
    require_safe_input_file(
        image_path, "panel input image", repo=repo
    )
    mask = np.load(support_mask, allow_pickle=False).astype(bool)
    with Image.open(image_path) as image_handle:
        image = np.asarray(image_handle.convert("RGB"))
    if mask.shape != image.shape[:2] or not mask.any():
        raise ReadoutError(
            f"panel support mask/image mismatch: {mask.shape} vs {image.shape[:2]}"
        )
    yy, xx = np.nonzero(mask)
    padding = 32
    x0 = max(0, int(xx.min()) - padding)
    x1 = min(image.shape[1], int(xx.max()) + 1 + padding)
    y0 = max(0, int(yy.min()) - padding)
    y1 = min(image.shape[0], int(yy.max()) + 1 + padding)
    crop = image[y0:y1, x0:x1]

    seed_path = repo_path(p0prime["row"]["seed_las"], repo=repo)
    require_regular(seed_path, "P0-prime seed LAS for panel")
    seed_las = laspy.read(seed_path)
    seed_xyz = np.column_stack([seed_las.x, seed_las.y, seed_las.z])
    seed_class = np.asarray(seed_las.classification)
    seed_roof = seed_xyz[seed_class == 6]
    if not len(seed_roof):
        raise ReadoutError("panel seed LAS has no class-6 points")

    npz_path = repo_path(extract["pointcloud"]["path"], repo=repo)
    with np.load(npz_path, allow_pickle=False) as data:
        learned = np.asarray(data["P_utm_clean"], dtype=np.float64)

    building_id = materialization["building_id"]
    arm = materialization["arm"]
    run = materialization["replicate"]
    panels = repo_path(config["outputs"]["panels_dir"], repo=repo)
    panels.mkdir(parents=True, exist_ok=True)
    panel_path = panels / f"{building_id}__arm_{arm}__{run}.png"
    materials_path = panel_path.with_suffix(".materials.json")
    if panel_path.exists() or materials_path.exists():
        raise ReadoutError("panel output already exists; retry forbidden")

    fig, axes = plt.subplots(2, 3, figsize=(13.2, 8.0))
    axes[0, 0].imshow(crop)
    axes[0, 0].set_title(f"input crop: {image_name}", fontsize=8)
    axes[0, 0].axis("off")
    _scatter_points(axes[0, 1], seed_roof, mode="xy", title="laser seed top view")
    _scatter_points(axes[0, 2], learned, mode="xy", title="learned point cloud top view")
    _scatter_points(axes[1, 0], learned, mode="xz", title="learned point cloud section")
    _plot_surfaces(axes[1, 1], prediction, "assembled CityJSON roof")
    _plot_surfaces(axes[1, 2], references, "reference roof (evaluation only)")
    fig.suptitle(f"{building_id} | arm {arm} | {run}", fontsize=11)
    fig.tight_layout()
    fig.savefig(panel_path, dpi=170)
    plt.close(fig)
    require_regular(panel_path, "panel PNG")

    materials = {
        "schema": "jointbuildgs.fusion_w1.panel_materials.v1",
        "state": "COMPLETE",
        "created_at": now_iso(),
        "job_key": materialization["job_key"],
        "building_id": building_id,
        "arm": arm,
        "replicate": run,
        "input_image_crop": {
            "source": repo_relative(image_path, repo=repo),
            "source_sha256": sha256_file(image_path),
            "photo_support_mask": repo_relative(support_mask, repo=repo),
            "photo_support_mask_sha256": sha256_file(support_mask),
            "crop_xyxy": [x0, y0, x1, y1],
        },
        "seed_topview": {
            "source": repo_relative(seed_path, repo=repo),
            "source_sha256": sha256_file(seed_path),
            "class6_points_n": int(len(seed_roof)),
        },
        "learned_topview_and_section": {
            "source": repo_relative(npz_path, repo=repo),
            "source_sha256": sha256_file(npz_path),
            "points_n": int(len(learned)),
        },
        "assembled_model": {
            "source": repo_relative(cityjson, repo=repo),
            "source_sha256": sha256_file(cityjson),
            "roof_surfaces_n": len(prediction),
        },
        "reference": {
            "role": config["scoring"]["reference"]["role"],
            "locked_files": config["scoring"]["reference"]["locked_files"],
            "roof_surfaces_n": len(references),
        },
        "panel": {
            "path": repo_relative(panel_path, repo=repo),
            "sha256": sha256_file(panel_path),
        },
    }
    exclusive_json(materials_path, materials)
    return panel_path, materials_path


def score_one(
    config: Mapping[str, Any],
    building_id: str,
    arm: str,
    run: str,
    *,
    repo: Path = REPO,
) -> dict[str, Any]:
    started_clock = time.monotonic()
    materialization_path, materialization = validate_materialization(
        config, building_id, arm, run, repo=repo
    )
    job = materialization_path.parent
    ensure_not_failed(job, repo=repo)
    roofer_path = job / "roofer_receipt.json"
    roofer = load_receipt(
        roofer_path,
        schema="jointbuildgs.fusion_w1.roofer_receipt.v1",
        state="COMPLETE",
    )
    scoring_invocation_path = job / "scoring_invocation.json"
    scoring_invocation = {
        "schema": "jointbuildgs.fusion_w1.scoring_invocation.v1",
        "state": "AUTHORIZED",
        "created_at": now_iso(),
        "job_key": job_key(building_id, arm, run),
        "building_id": building_id,
        "arm": arm,
        "replicate": run,
        "roofer_receipt": {
            "path": repo_relative(roofer_path, repo=repo),
            "sha256": sha256_file(roofer_path),
        },
        "reference_role": config["scoring"]["reference"]["role"],
        "reference_opened_at_authorization": False,
        "metrics": config["scoring"]["metrics"],
        "retry_allowed": False,
    }
    exclusive_json(scoring_invocation_path, scoring_invocation)
    # Count scoring before loading any evaluation-only reference.
    begin_stage(
        config,
        building_id,
        arm,
        run,
        stage="scoring",
        invocation_path=scoring_invocation_path,
        repo=repo,
    )

    for record in roofer["jsonseq_outputs"]:
        path = repo_path(record["path"], repo=repo)
        verify_hash(path, record["sha256"], "Roofer JSONSeq before score")
    p0 = p0prime_module(config, repo=repo)
    helper_config = {
        "canonical_helpers": config["scoring"]["canonical_helpers"]
    }
    w2, metric, coverage_helper = p0.load_helpers(helper_config)
    jsonseq = [
        repo_path(record["path"], repo=repo)
        for record in roofer["jsonseq_outputs"]
    ]
    cityjson = job / "cityjson" / "fusion.city.json"
    if cityjson.exists() or cityjson.is_symlink():
        raise ReadoutError("combined CityJSON exists before scoring")
    cityjson.parent.mkdir(parents=True, exist_ok=True)
    w2.combine_cityjsonseq(jsonseq, cityjson)
    val_version = p0.val3dity_version(
        config["scoring"]["val3dity_version"]
    )
    val_report = job / "val3dity" / "fusion.report.json"
    val_exit, val_by_id, val_log = p0.run_val3dity(
        cityjson, val_report
    )
    roofer_by_id = w2.parse_roofer_features(jsonseq)
    canonical_rows = w2.classify_buildings(
        f"FUSION_{arm}_{run}",
        [building_id],
        roofer_by_id,
        val_by_id,
    )
    if len(canonical_rows) != 1:
        raise ReadoutError("canonical Roofer status row count drift")
    canonical = canonical_rows[0]
    flags = p0.assembly_flags(
        roofer_by_id.get(building_id),
        val3dity_feature=val_by_id.get(building_id),
    )
    if p0.cityjson_lod22_presence(cityjson, building_id) != flags[
        "has_lod22_geometry"
    ]:
        raise ReadoutError("Roofer JSONSeq/combined CityJSON LoD2 mismatch")

    # Evaluation-only data are opened only after Roofer output is frozen.
    reference = metric.parse_lod2_roofs(
        repo_path(config["scoring"]["reference"]["lod2_dir"], repo=repo),
        {building_id},
    )
    parsed = metric.parse_cityjson_roofs(cityjson, {building_id})
    prediction = metric.shift_surface_z(
        list(parsed.get(building_id, [])),
        float(config["scoring"]["reference"]["score_time_z_shift_m"]),
    )
    references = list(reference[building_id])
    comparison = metric.compare_building(references, prediction)
    coverage = coverage_helper.roof_xy_coverage(references, prediction)
    xy_alignment, xy_overlap = coverage_helper.xy_check(references, prediction)
    precision = comparison["correctness"]
    recall = comparison["completeness"]
    plane_f1 = p0.plane_f1(precision, recall)
    fallback = bool(flags["lod1_fallback"])
    model_faces = 1 if fallback and prediction else len(prediction)
    ref_faces = len(references)
    face_ratio = model_faces / ref_faces if ref_faces else None
    current_rms = optional_float(comparison["ref_rms_m"])

    laser = baseline_row(config, building_id, role="laser", repo=repo)
    image = baseline_row(config, building_id, role="image", repo=repo)
    pair_laser = paired_rms_fields(current_rms, laser, "rms_pair_laser")
    pair_image = paired_rms_fields(current_rms, image, "rms_pair_image")
    p0binding = p0prime_binding(config, building_id, repo=repo)
    p0row = p0binding["row"]
    p0_rms = optional_float(p0row.get("roof_rms_m"))
    p0_completeness = optional_float(p0row.get("roof_completeness"))
    p0_face_ratio = optional_float(p0row.get("face_count_ratio"))
    p0_plane_f1 = optional_float(p0row.get("plane_f1"))
    current_completeness = optional_float(coverage.get("roof_completeness"))

    extract = load_receipt(
        job / "extract_receipt.json",
        schema="jointbuildgs.fusion_w1.extract_receipt.v1",
        state="COMPLETE",
    )
    classification = load_receipt(
        job / "classification_receipt.json",
        schema="jointbuildgs.fusion_w1.classification_receipt.v1",
        state="COMPLETE",
    )
    panel, panel_materials = render_panel(
        config,
        materialization,
        p0binding,
        extract,
        cityjson,
        prediction,
        references,
        repo=repo,
    )
    counters = counter_snapshot(
        config, job_key(building_id, arm, run), repo=repo
    )
    target = materialization["target"]
    class_counts = classification["classified_las"]["class_counts"]
    row: dict[str, Any] = {
        "schema": "jointbuildgs.fusion_w1.score_building.v1",
        "row_type": "building_arm_run",
        "task_id": config["task_id"],
        "run_id": config["run_id"],
        "building_id": building_id,
        "arm": arm,
        "run": run,
        "job_key": job_key(building_id, arm, run),
        "processing_order": target["processing_order"],
        "tier": target["tier"],
        "cohort": target["cohort"],
        "source_cell_label": target["source_cell_label"],
        "texture_stratum": target["texture_stratum"],
        "texture_low_gradient_fraction": target[
            "texture_low_gradient_fraction"
        ],
        "texture_threshold": target["texture_threshold"],
        "training_materialization": materialization["training"][
            "materialization"
        ],
        "training_materialization_sha256": materialization["training"][
            "materialization_sha256"
        ],
        "training_completed": materialization["training"]["completed"],
        "training_completed_sha256": materialization["training"][
            "completed_sha256"
        ],
        "checkpoint": materialization["training"]["checkpoint"],
        "checkpoint_sha256": materialization["training"][
            "checkpoint_sha256"
        ],
        "readout_npz": extract["pointcloud"]["path"],
        "readout_npz_sha256": extract["pointcloud"]["sha256"],
        "readout_raw_points_n": extract["pointcloud"]["raw_points_n"],
        "readout_clean_points_n": extract["pointcloud"]["clean_points_n"],
        "readout_wall_seconds": extract["wall_seconds"],
        "classification_method": classification["method"],
        "classified_las": classification["classified_las"]["path"],
        "classified_las_sha256": classification["classified_las"]["sha256"],
        "classified_point_count": classification["classified_las"][
            "point_count"
        ],
        "class1_count": int(class_counts.get("1", 0)),
        "class2_count": int(class_counts.get("2", 0)),
        "class6_count": int(class_counts.get("6", 0)),
        "classification_wall_seconds": classification["wall_seconds"],
        "footprint": materialization["footprint"]["roofer_path"],
        "footprint_sha256": materialization["footprint"]["roofer_sha256"],
        "roofer_image": roofer["image"],
        "roofer_parameters": " ".join(config["roofer"]["parameters"]),
        "roofer_wall_seconds": roofer["wall_seconds"],
        **flags,
        "canonical_combined_status": canonical.get("status", ""),
        "canonical_combined_reason": canonical.get("reason", ""),
        "val3dity_exit_code": val_exit,
        "val3dity_report": repo_relative(val_report, repo=repo),
        "val3dity_report_sha256": sha256_file(val_report),
        "cityjson": repo_relative(cityjson, repo=repo),
        "cityjson_sha256": sha256_file(cityjson),
        "cityjson_crs": coverage_helper.cityjson_crs(cityjson),
        "geometry_roof_surface_present": bool(prediction),
        "plane_match_count": comparison["match_count"],
        "plane_precision": precision,
        "plane_recall": recall,
        "plane_f1": plane_f1,
        "roof_face_count_model": model_faces,
        "roof_face_count_ref": ref_faces,
        "face_count_ratio": face_ratio,
        "roof_rms_m": current_rms,
        "roof_hausdorff_m": comparison["ref_hausdorff_m"],
        "roof_distance_samples": comparison["ref_distance_samples"],
        **coverage,
        "xy_alignment": xy_alignment,
        "xy_overlap_ratio": xy_overlap,
        "score_time_z_shift_m": config["scoring"]["reference"][
            "score_time_z_shift_m"
        ],
        **pair_laser,
        **pair_image,
        "rms_pair_denominator_definition": config["scoring"][
            "paired_baseline"
        ]["pair_denominator"],
        "p0prime_status": p0row["status"],
        "p0prime_assembly_lod2_success": truth(
            p0row.get("assembly_lod2_success")
        ),
        "p0prime_val3dity_valid": truth(p0row.get("val3dity_valid")),
        "p0prime_plane_f1": p0_plane_f1,
        "p0prime_roof_rms_m": p0_rms,
        "p0prime_roof_completeness": p0_completeness,
        "p0prime_face_count_ratio": p0_face_ratio,
        "delta_assembly_lod2_vs_p0prime": int(
            bool(flags["assembly_lod2_success"])
        )
        - int(truth(p0row.get("assembly_lod2_success"))),
        "delta_val3dity_valid_vs_p0prime": int(bool(flags["val3dity_valid"]))
        - int(truth(p0row.get("val3dity_valid"))),
        "delta_plane_f1_vs_p0prime": (
            plane_f1 - p0_plane_f1
            if plane_f1 is not None and p0_plane_f1 is not None
            else None
        ),
        "delta_roof_rms_vs_p0prime_m": (
            current_rms - p0_rms
            if current_rms is not None and p0_rms is not None
            else None
        ),
        "delta_roof_completeness_vs_p0prime": (
            current_completeness - p0_completeness
            if current_completeness is not None
            and p0_completeness is not None
            else None
        ),
        "delta_face_count_ratio_vs_p0prime": (
            face_ratio - p0_face_ratio
            if face_ratio is not None and p0_face_ratio is not None
            else None
        ),
        "panel_png": repo_relative(panel, repo=repo),
        "panel_png_sha256": sha256_file(panel),
        "panel_materials": repo_relative(panel_materials, repo=repo),
        "panel_materials_sha256": sha256_file(panel_materials),
        "reference_role": config["scoring"]["reference"]["role"],
        "reference_absolute_metric_caveat": config["scoring"]["reference"][
            "absolute_metric_caveat"
        ],
        **counters,
        "score_wall_seconds": time.monotonic() - started_clock,
        "status": "MEASURED",
    }
    score_receipt_path = job / "score_receipt.json"
    score_receipt = {
        "schema": "jointbuildgs.fusion_w1.score_receipt.v1",
        "state": "MEASURED",
        "created_at": now_iso(),
        "job_key": job_key(building_id, arm, run),
        "row": row,
        "row_sha256": sha256_bytes(canonical_json(row)),
        "canonical_helpers": config["scoring"]["canonical_helpers"],
        "val3dity_version": val_version,
        "val3dity_log": {
            "path": repo_relative(val_log, repo=repo),
            "sha256": sha256_file(val_log),
        },
        "reference_opened_only_after_roofer_output_frozen": True,
        "assembly_lod2_success_excludes_val3dity": True,
    }
    exclusive_json(score_receipt_path, score_receipt)
    upsert_score_row(config, row, repo=repo)
    scores_path = repo_path(config["outputs"]["scores_csv"], repo=repo)
    complete = {
        "schema": JOB_SCHEMA,
        "state": "COMPLETE",
        "created_at": now_iso(),
        "run_id": config["run_id"],
        "job_key": job_key(building_id, arm, run),
        "building_id": building_id,
        "arm": arm,
        "replicate": run,
        "score_receipt": {
            "path": repo_relative(score_receipt_path, repo=repo),
            "sha256": sha256_file(score_receipt_path),
        },
        "scores_csv_at_completion": {
            "path": repo_relative(scores_path, repo=repo),
            "sha256": sha256_file(scores_path),
            "row_count": len(read_csv(scores_path)),
        },
        "panel": {
            "path": repo_relative(panel, repo=repo),
            "sha256": sha256_file(panel),
            "materials": repo_relative(panel_materials, repo=repo),
            "materials_sha256": sha256_file(panel_materials),
        },
        "publication": {
            "score_receipt_before_csv": True,
            "incremental_csv_before_complete_receipt": True,
            "panel_required_before_complete_receipt": True,
        },
        "retry_allowed": False,
    }
    exclusive_json(job / "complete.json", complete)
    return complete


def shallow_training_complete(
    config: Mapping[str, Any],
    building_id: str,
    arm: str,
    run: str,
    *,
    repo: Path = REPO,
) -> bool:
    target = training_job_dir(
        config, building_id, arm, run, repo=repo
    )
    materialization_path = target / config["training"]["materialization"]
    completed_path = target / config["training"]["completed"]
    failed_path = target / config["training"]["failed"]
    if not materialization_path.is_file() or not completed_path.is_file():
        return False
    try:
        completed = load_json(completed_path)
        retry_output = _validate_infrastructure_retry_chain(
            completed=completed,
            target=target,
            materialization_path=materialization_path,
            materialization_sha256=sha256_file(materialization_path),
            failed_path=failed_path,
            expected_job_key=job_key(building_id, arm, run),
            training_contract=config["training"],
            repo=repo,
        )
    except ReadoutError:
        return False
    failed_present = failed_path.exists() or failed_path.is_symlink()
    return not failed_present or retry_output is not None


def is_readout_complete(
    config: Mapping[str, Any],
    building_id: str,
    arm: str,
    run: str,
    *,
    repo: Path = REPO,
) -> bool:
    return (
        job_dir(config, building_id, arm, run, repo=repo) / "complete.json"
    ).is_file()


def list_pending(
    config: Mapping[str, Any], *, repo: Path = REPO
) -> list[str]:
    """List immutable training completions, with a mandatory smoke barrier."""

    smoke = config["smoke_job"]
    smoke_job = job_dir(
        config,
        smoke["building_id"],
        smoke["arm"],
        smoke["run"],
        repo=repo,
    )
    if (smoke_job / "failed.json").exists():
        ensure_not_failed(smoke_job, repo=repo)
    smoke_complete = is_readout_complete(
        config,
        smoke["building_id"],
        smoke["arm"],
        smoke["run"],
        repo=repo,
    )
    smoke_training_ready = shallow_training_complete(
        config,
        smoke["building_id"],
        smoke["arm"],
        smoke["run"],
        repo=repo,
    )
    if not smoke_complete:
        if not smoke_training_ready:
            return []
        if smoke_job.exists() and any(smoke_job.iterdir()):
            # A started or prepared-but-not-complete smoke is never silently retried.
            raise ReadoutError(
                "smoke readout has partial state; inspect receipts before queue"
            )
        return [smoke["job_key"]]

    output: list[str] = []
    targets = target_rows(config, repo=repo)
    # Preserve the preregistered phase order across the whole cohort.  In
    # particular, all ready core A/r1 jobs precede every core A/r2 job; this
    # must not collapse to target -> arm -> replicate nesting.
    for phase in config["queue_contract"]["ordered_phases"]:
        arm = str(phase["arm"])
        run = str(phase["run"])
        cohort = str(phase["cohort"])
        safe_identity(smoke["building_id"], arm, run)
        missing_mandatory_training = False
        for target in targets:
            if target["cohort"] != cohort:
                continue
            building_id = target["building_id"]
            if (
                building_id == smoke["building_id"]
                and arm == smoke["arm"]
                and run == smoke["run"]
            ):
                continue
            job = job_dir(config, building_id, arm, run, repo=repo)
            if (job / "failed.json").exists() or (
                job / "complete.json"
            ).exists():
                continue
            if not shallow_training_complete(
                config, building_id, arm, run, repo=repo
            ):
                if not phase.get("ready_training_jobs_only", False):
                    missing_mandatory_training = True
                continue
            if job.exists() and any(job.iterdir()):
                raise ReadoutError(
                    f"ready job has partial readout state; retry forbidden: {job}"
                )
            output.append(job_key(building_id, arm, run))
        if missing_mandatory_training:
            # Process every ready job in this phase but do not leak into a
            # lower-priority phase while a mandatory cohort job is untrained.
            break
    return output


def check(
    config: Mapping[str, Any],
    *,
    building_id: str | None,
    arm: str | None,
    run: str | None,
    repo: Path = REPO,
) -> dict[str, Any]:
    static = verify_static_inputs(config, repo=repo)
    result: dict[str, Any] = {
        "schema": "jointbuildgs.fusion_w1.readout_check.v1",
        "created_at": now_iso(),
        "static_sha256": static,
        "target_population": len(target_rows(config, repo=repo)),
        "smoke_job": config["smoke_job"],
        "resource_contract": config["resource_lock"],
        "actual_training_or_readout_started_by_check": False,
    }
    if building_id is not None:
        if arm is None or run is None:
            raise ReadoutError("--arm and --run are required with --building-id")
        result["target"] = target_metadata(
            config, building_id, repo=repo
        )
        result["training"] = resolve_training_artifacts(
            config, building_id, arm, run, repo=repo
        )
        for key in (
            "job_dir",
            "materialization_path",
            "completed_path",
            "checkpoint",
            "full_state_checkpoint",
            "full_state_manifest",
            "data_root",
            "supervision_index",
        ):
            result["training"][key] = repo_relative(
                result["training"][key], repo=repo
            )
        result["p0prime"] = {
            key: value
            for key, value in p0prime_binding(
                config, building_id, repo=repo
            ).items()
            if key
            not in {
                "row",
                "complete",
            }
        }
        for key in ("scores_csv", "complete_path"):
            result["p0prime"][key] = repo_relative(
                result["p0prime"][key], repo=repo
            )
    return result


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    result.add_argument(
        "--retry-policy", type=Path, default=DEFAULT_READOUT_RETRY_POLICY
    )
    result.add_argument(
        "--recovery2-policy",
        type=Path,
        default=DEFAULT_READOUT_RECOVERY2_POLICY,
    )
    sub = result.add_subparsers(dest="command", required=True)
    check_parser = sub.add_parser("check")
    check_parser.add_argument("--building-id")
    check_parser.add_argument("--arm", choices=ARMS)
    check_parser.add_argument("--run", choices=RUNS)
    for name in (
        "prepare-one",
        "authorize-extract",
        "extract-argv",
        "extract-environment",
        "accept-extract",
        "prepare-extract-infra-retry",
        "retry-extract-argv",
        "retry-extract-environment",
        "accept-extract-infra-retry",
        "record-extract-infra-retry-failure",
        "prepare-extract-infra-recovery2",
        "recovery2-extract-argv",
        "recovery2-extract-environment",
        "accept-extract-infra-recovery2",
        "record-extract-infra-recovery2-failure",
        "authorize-classification",
        "classification-argv",
        "accept-classification",
        "authorize-roofer",
        "roofer-argv",
        "accept-roofer",
        "score-one",
        "record-failure",
        "failure-stage",
    ):
        command = sub.add_parser(name)
        command.add_argument("--building-id", required=True)
        command.add_argument("--arm", choices=ARMS, required=True)
        command.add_argument("--run", choices=RUNS, required=True)
        if name.startswith("accept-"):
            command.add_argument("--wall-seconds", type=float, required=True)
        if name in {
            "record-failure",
            "record-extract-infra-retry-failure",
            "record-extract-infra-recovery2-failure",
        }:
            if name == "record-failure":
                command.add_argument("--stage", required=True)
            command.add_argument("--message", required=True)
            command.add_argument("--detail", default="")
    sub.add_parser("list-pending")
    sub.add_parser("reconcile-counters")
    sub.add_parser("finalize-partial")
    return result


def print_json(payload: Any) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))


def main(argv: Sequence[str] | None = None) -> int:
    args = parser().parse_args(argv)
    config_path = (
        args.config
        if args.config.is_absolute()
        else repo_path(args.config)
    )
    config = load_config(config_path)
    command = args.command
    identity = (
        (args.building_id, args.arm, args.run)
        if hasattr(args, "building_id") and args.building_id
        else None
    )
    try:
        if command == "check":
            print_json(
                check(
                    config,
                    building_id=args.building_id,
                    arm=args.arm,
                    run=args.run,
                )
            )
        elif command == "prepare-one":
            print_json(prepare_one(config, *identity))
        elif command == "authorize-extract":
            print_json(authorize_extract(config, *identity))
        elif command == "extract-argv":
            for value in invocation_argv(
                config,
                *identity,
                "extract_invocation.json",
                "jointbuildgs.fusion_w1.extract_invocation.v1",
            ):
                print(value)
        elif command == "extract-environment":
            for value in invocation_environment(
                config,
                *identity,
                "extract_invocation.json",
                "jointbuildgs.fusion_w1.extract_invocation.v1",
            ):
                print(value)
        elif command == "accept-extract":
            print_json(
                accept_extract(
                    config, *identity, wall_seconds=args.wall_seconds
                )
            )
        elif command == "prepare-extract-infra-retry":
            print_json(
                prepare_extract_infra_retry(
                    config, args.retry_policy, *identity
                )
            )
        elif command == "retry-extract-argv":
            for value in retry_extract_argv(config, *identity):
                print(value)
        elif command == "retry-extract-environment":
            for value in retry_extract_environment(config, *identity):
                print(value)
        elif command == "accept-extract-infra-retry":
            print_json(
                accept_extract_infra_retry(
                    config, *identity, wall_seconds=args.wall_seconds
                )
            )
        elif command == "record-extract-infra-retry-failure":
            print_json(
                record_extract_infra_retry_failure(
                    config,
                    *identity,
                    message=args.message,
                    detail=args.detail,
                )
            )
        elif command == "prepare-extract-infra-recovery2":
            print_json(
                prepare_extract_infra_recovery2(
                    config, args.recovery2_policy, *identity
                )
            )
        elif command == "recovery2-extract-argv":
            for value in recovery2_extract_argv(config, *identity):
                print(value)
        elif command == "recovery2-extract-environment":
            for value in recovery2_extract_environment(config, *identity):
                print(value)
        elif command == "accept-extract-infra-recovery2":
            print_json(
                accept_extract_infra_recovery2(
                    config, *identity, wall_seconds=args.wall_seconds
                )
            )
        elif command == "record-extract-infra-recovery2-failure":
            print_json(
                record_extract_infra_recovery2_failure(
                    config,
                    *identity,
                    message=args.message,
                    detail=args.detail,
                )
            )
        elif command == "authorize-classification":
            print_json(authorize_classification(config, *identity))
        elif command == "classification-argv":
            for value in invocation_argv(
                config,
                *identity,
                "classification_invocation.json",
                "jointbuildgs.fusion_w1.classification_invocation.v1",
            ):
                print(value)
        elif command == "accept-classification":
            print_json(
                accept_classification(
                    config, *identity, wall_seconds=args.wall_seconds
                )
            )
        elif command == "authorize-roofer":
            print_json(authorize_roofer(config, *identity))
        elif command == "roofer-argv":
            for value in invocation_argv(
                config,
                *identity,
                "roofer_invocation.json",
                "jointbuildgs.fusion_w1.roofer_invocation.v1",
            ):
                print(value)
        elif command == "accept-roofer":
            print_json(
                accept_roofer(
                    config, *identity, wall_seconds=args.wall_seconds
                )
            )
        elif command == "score-one":
            print_json(score_one(config, *identity))
        elif command == "record-failure":
            print_json(
                record_failure(
                    config,
                    *identity,
                    stage=args.stage,
                    message=args.message,
                    detail=args.detail,
                )
            )
        elif command == "failure-stage":
            job = job_dir(config, *identity)
            recovered_failure = job / "failed_after_infrastructure_retry.json"
            if recovered_failure.is_file() and not recovered_failure.is_symlink():
                failed = load_receipt(
                    recovered_failure,
                    schema="jointbuildgs.fusion_w1.readout_failure_after_infrastructure_retry.v1",
                    state="FAILED",
                )
            else:
                failed = load_receipt(
                    job / "failed.json",
                    schema="jointbuildgs.fusion_w1.readout_failure.v1",
                    state="FAILED",
                )
            require_equal(
                failed.get("job_key"),
                job_key(*identity),
                "failure receipt job key",
            )
            print(failed["stage"])
        elif command == "list-pending":
            for value in list_pending(config):
                print(value)
        elif command == "reconcile-counters":
            print_json(reconcile_runtime_counters(config))
        elif command == "finalize-partial":
            print_json(finalize_partial(config))
        else:  # pragma: no cover
            raise AssertionError(command)
    except BaseException as exc:
        if identity is not None and command not in {
            "check",
            "record-failure",
            "extract-argv",
            "extract-environment",
            "prepare-extract-infra-retry",
            "retry-extract-argv",
            "retry-extract-environment",
            "accept-extract-infra-retry",
            "record-extract-infra-retry-failure",
            "prepare-extract-infra-recovery2",
            "recovery2-extract-argv",
            "recovery2-extract-environment",
            "accept-extract-infra-recovery2",
            "record-extract-infra-recovery2-failure",
            "classification-argv",
            "roofer-argv",
            "failure-stage",
        }:
            try:
                record_failure(
                    config,
                    *identity,
                    stage=command,
                    message=str(exc),
                    detail=traceback.format_exc(),
                )
            except Exception:
                pass
        raise
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ReadoutError as exc:
        print(f"FUS-W1 readout contract error: {exc}", file=sys.stderr)
        raise SystemExit(2)
