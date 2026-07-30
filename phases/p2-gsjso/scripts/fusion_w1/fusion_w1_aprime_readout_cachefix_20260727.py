#!/usr/bin/env python3
"""Generic cache-fixed adapter for the locked A-prime readout driver.

Scientific readout behavior and the canonical output namespace remain owned by
the 2026-07-26 driver.  This adapter has only two responsibilities:

* prove that gsplat loads the already-built, SHA-pinned CUDA extension from the
  writable non-root T2 cache without changing its extension tree; and
* move only closed, zero-byte ``scores.csv.lock`` synchronization files into an
  append-only continuation quarantine before the base driver inventories the
  attempt.

No training action is implemented here.
"""
from __future__ import annotations

import argparse
from contextlib import ExitStack
from datetime import datetime, timezone
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any, BinaryIO, Mapping, Sequence


REPO = Path(__file__).resolve().parents[4]
CONTAINER_REPO = Path("/workspace/JointBuildGS")
DEFAULT_CONFIG = (
    REPO
    / "phases/p2-gsjso/configs/fusion_w1/fusion_w1_aprime_readout_cachefix_20260727.json"
)
CONFIG_SCHEMA = "jointbuildgs.fusion_w1_aprime.readout.config.v1"
CONTRACT_SCHEMA = "jointbuildgs.fusion_w1_aprime.readout_cachefix.contract.v1"
CACHE_SCHEMA = "jointbuildgs.fusion_w1_aprime.readout_cachefix.cache_probe.v1"
HYGIENE_SCHEMA = "jointbuildgs.fusion_w1_aprime.readout_cachefix.finalize_hygiene.v1"
EMPTY_SHA256 = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"


class ReadoutCachefixError(RuntimeError):
    """The locked readout, cache, or ephemeral-lock contract drifted."""


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


def sha256_file(path: Path, block_size: int = 1 << 20) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(block_size), b""):
            digest.update(block)
    return digest.hexdigest()


def require_equal(observed: Any, expected: Any, label: str) -> None:
    if observed != expected:
        raise ReadoutCachefixError(
            f"{label} mismatch: observed={observed!r}, expected={expected!r}"
        )


def repo_path(raw: str | Path) -> Path:
    path = (REPO / raw).resolve()
    try:
        path.relative_to(REPO.resolve())
    except ValueError as exc:
        raise ReadoutCachefixError(f"path escapes repository: {raw}") from exc
    return path


def relative(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(REPO.resolve()))
    except ValueError as exc:
        raise ReadoutCachefixError(f"path escapes repository: {path}") from exc


def load_json(path: Path) -> dict[str, Any]:
    if not path.is_file() or path.is_symlink():
        raise ReadoutCachefixError(f"missing/non-regular JSON: {relative(path)}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ReadoutCachefixError(f"JSON root must be an object: {relative(path)}")
    return payload


def fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def exclusive_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(canonical_json(dict(payload)))
        stream.flush()
        os.fsync(stream.fileno())
    fsync_directory(path.parent)


def file_record(path: Path, *, allow_empty: bool = False) -> dict[str, Any]:
    if not path.is_file() or path.is_symlink():
        raise ReadoutCachefixError(f"artifact missing/non-regular: {relative(path)}")
    size = int(path.stat().st_size)
    if size == 0 and not allow_empty:
        raise ReadoutCachefixError(f"artifact is empty: {relative(path)}")
    return {"path": relative(path), "sha256": sha256_file(path), "bytes": size}


def verify_record(record: Mapping[str, Any], label: str) -> Path:
    if not {"path", "sha256", "bytes"}.issubset(record):
        raise ReadoutCachefixError(f"{label} lacks path/SHA256/bytes")
    path = repo_path(str(record["path"]))
    actual = file_record(path)
    require_equal(actual["sha256"], str(record["sha256"]), f"{label} SHA256")
    require_equal(actual["bytes"], int(record["bytes"]), f"{label} bytes")
    return path


def git(*arguments: str) -> str:
    process = subprocess.run(
        ["git", "-c", f"safe.directory={REPO}", "-C", str(REPO), *arguments],
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if process.returncode:
        raise ReadoutCachefixError(
            process.stderr.strip()
            or process.stdout.strip()
            or f"git {' '.join(arguments)} failed"
        )
    return process.stdout.strip()


def expected_container_environment(runtime_rel: str) -> dict[str, str]:
    root = CONTAINER_REPO / runtime_rel
    return {
        "HOME": str(root / "home"),
        "XDG_CACHE_HOME": str(root / "xdg_cache"),
        "TORCH_EXTENSIONS_DIR": str(root / "torch_extensions"),
        "MAX_JOBS": "2",
    }


def load_config(path: Path = DEFAULT_CONFIG) -> dict[str, Any]:
    config = load_json(path)
    require_equal(config.get("schema"), CONFIG_SCHEMA, "readout config schema")
    require_equal(config.get("branch"), "exp/fusion-w1", "branch")
    contract = config.get("cachefix_contract")
    if not isinstance(contract, Mapping):
        raise ReadoutCachefixError("cachefix contract is missing")
    require_equal(contract.get("schema"), CONTRACT_SCHEMA, "cachefix schema")
    require_equal(contract.get("reuse_only"), True, "cache reuse-only")
    require_equal(contract.get("compilation_allowed"), False, "cache compilation")
    require_equal(contract.get("required_nonroot"), True, "non-root execution")
    require_equal(contract.get("required_gpu_default"), 1, "default GPU")
    require_equal(contract.get("new_training_runs_allowed"), 0, "new training runs")
    require_equal(
        contract.get("scientific_artifact_move_allowed"),
        False,
        "scientific artifact move",
    )
    require_equal(contract.get("required_lock_bytes"), 0, "lock bytes")
    require_equal(contract.get("required_lock_sha256"), EMPTY_SHA256, "lock SHA256")
    require_equal(
        contract.get("allowed_lock_relative_paths"),
        [
            "primary/engine/scores.csv.lock",
            "legacy_alpha/engine/scores.csv.lock",
        ],
        "allowed scorer locks",
    )

    base_config_path = verify_record(
        contract["base_readout_config"], "base readout config"
    )
    verify_record(contract["base_readout_driver"], "base readout driver")
    continuation_lock_path = verify_record(
        contract["continuation_lock"], "queue continuation lock"
    )
    continuation_lock = load_json(continuation_lock_path)
    require_equal(
        continuation_lock.get("schema"),
        "jointbuildgs.fusion_w1_aprime.queue_continuation_lock.v1",
        "queue continuation lock schema",
    )
    require_equal(
        continuation_lock.get("state"),
        "LOCKED_BEFORE_REMAINING_JOB_START",
        "queue continuation lock state",
    )
    require_equal(
        continuation_lock.get("scope", {}).get("remaining_jobs"),
        20,
        "queue continuation remaining jobs",
    )
    require_equal(
        continuation_lock.get("scope", {}).get("physical_gpu"),
        1,
        "queue continuation GPU",
    )
    base = load_json(base_config_path)
    for key in (
        "schema",
        "run_id",
        "branch",
        "locked_inputs",
        "identity_contract",
        "primary",
        "legacy_alpha_comparison",
        "roofer",
        "containers",
        "retry_contract",
        "publication",
    ):
        require_equal(config.get(key), base.get(key), f"base-preserved {key}")
    expected_outputs = dict(base["outputs"])
    runtime_rel = str(contract["shared_t2_runtime_environment"])
    expected_outputs["runtime_environment"] = runtime_rel
    require_equal(config.get("outputs"), expected_outputs, "base-preserved outputs")
    require_equal(
        config.get("implementation_files"),
        [
            "phases/p2-gsjso/configs/fusion_w1/fusion_w1_aprime_readout_cachefix_20260727.json",
            "phases/p2-gsjso/scripts/fusion_w1/fusion_w1_aprime_readout_cachefix_20260727.py",
            "phases/p2-gsjso/scripts/fusion_w1/run_fusion_w1_aprime_readout_cachefix_20260727.sh",
            "tests/fusion_w1/test_fusion_w1_aprime_readout_cachefix_20260727.py",
            contract["base_readout_driver"]["path"],
        ],
        "cachefix implementation files",
    )
    require_equal(
        config["outputs"]["root"], base["outputs"]["root"], "canonical readout root"
    )
    require_equal(
        contract.get("container_environment"),
        expected_container_environment(runtime_rel),
        "container cache environment",
    )
    extension = contract.get("preexisting_gsplat_extension")
    if not isinstance(extension, Mapping):
        raise ReadoutCachefixError("preexisting gsplat extension record is missing")
    expected_extension = (
        Path(runtime_rel) / "torch_extensions/gsplat_cuda/gsplat_cuda.so"
    )
    require_equal(extension.get("path"), str(expected_extension), "extension path")
    verify_record(extension, "preexisting gsplat extension")
    for key in (
        "continuation_root",
        "cache_probe_receipt",
        "ephemeral_lock_quarantine",
    ):
        raw = contract.get(key)
        if not isinstance(raw, str):
            raise ReadoutCachefixError(f"cachefix {key} is missing")
        repo_path(raw)
    continuation_root = Path(str(contract["continuation_root"]))
    require_equal(
        Path(str(contract["continuation_lock"]["path"])).parent,
        continuation_root,
        "continuation lock root",
    )
    for key in ("cache_probe_receipt", "ephemeral_lock_quarantine"):
        try:
            Path(str(contract[key])).relative_to(continuation_root)
        except ValueError as exc:
            raise ReadoutCachefixError(
                f"cachefix {key} is outside the locked continuation root"
            ) from exc
    return config


def load_base_driver(config: Mapping[str, Any]) -> Any:
    path = verify_record(
        config["cachefix_contract"]["base_readout_driver"], "base readout driver"
    )
    spec = importlib.util.spec_from_file_location("aprime_readout_cachefix_base", path)
    if spec is None or spec.loader is None:
        raise ReadoutCachefixError("cannot import locked base readout driver")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def tree_ledger(root: Path) -> list[dict[str, Any]]:
    if not root.is_dir() or root.is_symlink():
        raise ReadoutCachefixError(f"cache tree is missing/non-directory: {root}")
    rows: list[dict[str, Any]] = []
    for path in sorted(root.rglob("*")):
        rel = str(path.relative_to(root))
        if path.is_symlink():
            raise ReadoutCachefixError(f"cache tree symlink forbidden: {rel}")
        if path.is_dir():
            rows.append({"path": rel, "type": "directory"})
        elif path.is_file():
            rows.append(
                {
                    "path": rel,
                    "type": "file",
                    "sha256": sha256_file(path),
                    "bytes": int(path.stat().st_size),
                }
            )
        else:
            raise ReadoutCachefixError(f"cache tree special file forbidden: {rel}")
    return rows


def prove_directory_writable(path: Path, label: str) -> None:
    if not path.is_dir() or path.is_symlink():
        raise ReadoutCachefixError(f"cache path missing/non-directory: {label}={path}")
    probe = path / f".aprime_cachefix_probe_{os.getpid()}"
    if probe.exists() or probe.is_symlink():
        raise ReadoutCachefixError(f"cache writability probe collision: {probe}")
    try:
        with probe.open("xb") as stream:
            stream.write(b"writable\n")
            stream.flush()
            os.fsync(stream.fileno())
    finally:
        if probe.is_file() and not probe.is_symlink():
            probe.unlink()


def validate_cache_receipt(
    config: Mapping[str, Any], payload: Mapping[str, Any]
) -> None:
    contract = config["cachefix_contract"]
    extension = dict(contract["preexisting_gsplat_extension"])
    expected_environment = dict(contract["container_environment"])
    checks = (
        (payload.get("schema"), CACHE_SCHEMA, "cache receipt schema"),
        (payload.get("state"), "PASSED", "cache receipt state"),
        (payload.get("run_id"), config["run_id"], "cache receipt run"),
        (payload.get("task_id"), config["task_id"], "cache receipt task"),
        (payload.get("uid_is_nonroot"), True, "cache receipt non-root"),
        (payload.get("environment"), expected_environment, "cache receipt environment"),
        (payload.get("reuse_only"), True, "cache receipt reuse-only"),
        (payload.get("compilation_allowed"), False, "cache receipt compilation"),
        (payload.get("cuda_available"), True, "cache receipt CUDA"),
        (
            payload.get("preexisting_extension_before"),
            extension,
            "cache extension before",
        ),
        (
            payload.get("preexisting_extension_after"),
            extension,
            "cache extension after",
        ),
        (payload.get("cache_tree_unchanged"), True, "cache tree unchanged"),
        (payload.get("loaded_from_preexisting_extension"), True, "cache source"),
        (payload.get("new_training_runs_started"), 0, "cache training count"),
        (payload.get("scientific_verdict"), None, "cache verdict"),
    )
    for observed, expected, label in checks:
        require_equal(observed, expected, label)
    require_equal(
        payload.get("cache_tree_before"), payload.get("cache_tree_after"), "cache tree"
    )
    if int(payload.get("uid", 0)) == 0:
        raise ReadoutCachefixError("cache receipt records root execution")
    expected_module = str(
        CONTAINER_REPO / str(contract["preexisting_gsplat_extension"]["path"])
    )
    require_equal(payload.get("loaded_extension"), expected_module, "loaded extension")


def cache_probe(config: Mapping[str, Any]) -> dict[str, Any]:
    contract = config["cachefix_contract"]
    if os.geteuid() == 0:
        raise ReadoutCachefixError("cache probe must run as non-root")
    expected_environment = dict(contract["container_environment"])
    for key, expected in expected_environment.items():
        require_equal(os.environ.get(key), expected, f"cache environment {key}")
    for key in ("HOME", "XDG_CACHE_HOME", "TORCH_EXTENSIONS_DIR"):
        prove_directory_writable(Path(expected_environment[key]), key)

    extension_expected = dict(contract["preexisting_gsplat_extension"])
    extension_path = verify_record(extension_expected, "preexisting gsplat extension")
    module_root = extension_path.parent
    before = tree_ledger(module_root)

    import torch
    from gsplat.cuda._backend import _C

    if not torch.cuda.is_available():
        raise ReadoutCachefixError("CUDA is unavailable in cache probe")
    loaded = Path(str(_C.__file__)).resolve()
    require_equal(loaded, extension_path.resolve(), "loaded gsplat extension")
    after_record = file_record(extension_path)
    require_equal(after_record, extension_expected, "post-import extension")
    after = tree_ledger(module_root)
    require_equal(after, before, "post-import extension tree")

    payload = {
        "schema": CACHE_SCHEMA,
        "state": "PASSED",
        "created_at": now_iso(),
        "run_id": config["run_id"],
        "task_id": config["task_id"],
        "git_head": git("rev-parse", "HEAD"),
        "uid": os.geteuid(),
        "uid_is_nonroot": True,
        "environment": expected_environment,
        "reuse_only": True,
        "compilation_allowed": False,
        "cuda_available": True,
        "cuda_device": torch.cuda.get_device_name(torch.cuda.current_device()),
        "loaded_extension": str(loaded),
        "preexisting_extension_before": extension_expected,
        "preexisting_extension_after": after_record,
        "cache_tree_before": before,
        "cache_tree_after": after,
        "cache_tree_unchanged": True,
        "loaded_from_preexisting_extension": True,
        "new_training_runs_started": 0,
        "scientific_verdict": None,
    }
    receipt = repo_path(str(contract["cache_probe_receipt"]))
    if receipt.exists() or receipt.is_symlink():
        existing = load_json(receipt)
        for key, value in payload.items():
            if key != "created_at":
                require_equal(existing.get(key), value, f"existing cache receipt {key}")
        payload = existing
    else:
        exclusive_json(receipt, payload)
    validate_cache_receipt(config, payload)
    return payload


def scientific_ledger(attempt: Path, lock_paths: set[str]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for path in sorted(attempt.rglob("*")):
        if path.is_symlink():
            raise ReadoutCachefixError(
                f"attempt artifact symlink forbidden: {path.relative_to(attempt)}"
            )
        if path.is_file():
            rel = str(path.relative_to(attempt))
            if rel not in lock_paths:
                records.append(
                    {"path": rel, "sha256": sha256_file(path), "bytes": path.stat().st_size}
                )
    return records


def expected_scorer_locks(attempt: Path) -> set[str]:
    primary = load_json(attempt / "primary/score.json")
    require_equal(primary.get("state"), "MEASURED", "primary score state")
    legacy = load_json(attempt / "legacy_alpha/score.json")
    if legacy.get("state") not in {"MEASURED", "NOT_ASSEMBLED"}:
        raise ReadoutCachefixError(
            f"legacy alpha score is not final: {legacy.get('state')!r}"
        )
    expected = {"primary/engine/scores.csv.lock"}
    if legacy.get("state") == "MEASURED":
        expected.add("legacy_alpha/engine/scores.csv.lock")
    return expected


def quarantine_path(
    config: Mapping[str, Any], building_id: str, arm: str, run: str, attempt: int
) -> Path:
    return (
        repo_path(config["cachefix_contract"]["ephemeral_lock_quarantine"])
        / "by_building"
        / building_id
        / f"arm_{arm}"
        / run
        / f"attempt_{attempt:03d}"
    )


def acquire_scorer_lock(source: Path, relative_source: str) -> BinaryIO:
    stream = source.open("r+b")
    try:
        fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as exc:
        stream.close()
        raise ReadoutCachefixError(
            f"scorer lock is still held: {relative_source}"
        ) from exc
    return stream


def quarantine_ephemeral_locks(
    config: Mapping[str, Any], building_id: str, arm: str, run: str, attempt_number: int
) -> dict[str, Any]:
    """Move only final, closed zero-byte scorer locks before base finalization."""

    base = load_base_driver(config)
    derived = base.load_config(DEFAULT_CONFIG)
    attempt, _materialization = base.load_attempt(
        derived, building_id, arm, run, attempt_number
    )
    receipt_path = attempt / "finalize_hygiene.json"
    if receipt_path.exists() or receipt_path.is_symlink():
        raise ReadoutCachefixError("finalize hygiene was already applied")
    if (attempt / "failure.json").exists() or (attempt / "failure.json").is_symlink():
        raise ReadoutCachefixError("cannot quarantine locks for a failed attempt")
    job_complete = base.job_dir(derived, building_id, arm, run) / "complete.json"
    if job_complete.exists() or job_complete.is_symlink():
        raise ReadoutCachefixError("job was already finalized")

    expected = expected_scorer_locks(attempt)
    allowed = set(config["cachefix_contract"]["allowed_lock_relative_paths"])
    if not expected.issubset(allowed):
        raise ReadoutCachefixError("score state requires an unauthorized lock path")
    candidates = sorted(attempt.rglob("scores.csv.lock"))
    candidate_rel = {str(path.relative_to(attempt)) for path in candidates}
    require_equal(candidate_rel, expected, "score-state scorer locks")
    all_zero = sorted(
        str(path.relative_to(attempt))
        for path in attempt.rglob("*")
        if path.is_file() and path.stat().st_size == 0
    )
    require_equal(all_zero, sorted(expected), "zero-byte attempt files/scorer locks")

    for source in candidates:
        rel = str(source.relative_to(attempt))
        if source.is_symlink() or not source.is_file():
            raise ReadoutCachefixError(f"scorer lock missing/non-regular: {rel}")
        require_equal(source.stat().st_size, 0, f"{rel} bytes")
        require_equal(sha256_file(source), EMPTY_SHA256, f"{rel} SHA256")

    before_scientific = scientific_ledger(attempt, expected)
    quarantine = quarantine_path(config, building_id, arm, run, attempt_number)
    if quarantine.exists() or quarantine.is_symlink():
        raise ReadoutCachefixError(
            f"attempt quarantine already exists: {relative(quarantine)}"
        )

    records: list[dict[str, Any]] = []
    with ExitStack() as stack:
        locked: list[tuple[Path, str, BinaryIO]] = []
        for source in candidates:
            rel = str(source.relative_to(attempt))
            stream = stack.enter_context(acquire_scorer_lock(source, rel))
            locked.append((source, rel, stream))
        quarantine.mkdir(parents=True, exist_ok=False)
        fsync_directory(quarantine.parent)
        for source, rel, _stream in locked:
            destination = quarantine / rel
            destination.parent.mkdir(parents=True, exist_ok=True)
            if destination.exists() or destination.is_symlink():
                raise ReadoutCachefixError(
                    f"quarantine destination exists: {relative(destination)}"
                )
            source_parent = source.parent
            os.replace(source, destination)
            fsync_directory(source_parent)
            fsync_directory(destination.parent)
            require_equal(destination.stat().st_size, 0, "quarantined lock bytes")
            require_equal(sha256_file(destination), EMPTY_SHA256, "quarantined lock SHA")
            records.append(
                {
                    "source_path": relative(source),
                    "source_relative_to_attempt": rel,
                    "destination_path": relative(destination),
                    "sha256": EMPTY_SHA256,
                    "bytes": 0,
                    "exclusive_lock_acquired_after_scorer_close": True,
                }
            )

    remaining_zero = sorted(
        str(path.relative_to(attempt))
        for path in attempt.rglob("*")
        if path.is_file() and path.stat().st_size == 0
    )
    require_equal(remaining_zero, [], "zero-byte files after scorer-lock quarantine")
    require_equal(list(attempt.rglob("scores.csv.lock")), [], "remaining scorer locks")
    after_scientific = scientific_ledger(attempt, set())
    require_equal(after_scientific, before_scientific, "scientific artifact ledger")

    payload = {
        "schema": HYGIENE_SCHEMA,
        "state": "PASSED",
        "created_at": now_iso(),
        "run_id": config["run_id"],
        "task_id": config["task_id"],
        "git_head": git("rev-parse", "HEAD"),
        "identity": {
            "building_id": building_id,
            "arm": arm,
            "replicate": run,
            "profile": "full",
        },
        "attempt": attempt_number,
        "expected_locks_from_final_score_states": sorted(expected),
        "moved_ephemeral_locks": records,
        "moved_ephemeral_lock_count": len(records),
        "scientific_artifacts_before": before_scientific,
        "scientific_artifacts_after": after_scientific,
        "scientific_artifacts_moved": False,
        "scientific_artifact_move_count": 0,
        "new_training_runs_started": 0,
        "scientific_verdict": None,
    }
    exclusive_json(receipt_path, payload)
    return payload


def verify_hygiene(
    config: Mapping[str, Any], building_id: str, arm: str, run: str, attempt_number: int
) -> dict[str, Any]:
    base = load_base_driver(config)
    derived = base.load_config(DEFAULT_CONFIG)
    attempt, _materialization = base.load_attempt(
        derived, building_id, arm, run, attempt_number
    )
    payload = load_json(attempt / "finalize_hygiene.json")
    require_equal(payload.get("schema"), HYGIENE_SCHEMA, "hygiene schema")
    require_equal(payload.get("state"), "PASSED", "hygiene state")
    require_equal(
        payload.get("identity"),
        {
            "building_id": building_id,
            "arm": arm,
            "replicate": run,
            "profile": "full",
        },
        "hygiene identity",
    )
    require_equal(payload.get("attempt"), attempt_number, "hygiene attempt")
    require_equal(payload.get("scientific_artifacts_moved"), False, "scientific move")
    require_equal(payload.get("scientific_artifact_move_count"), 0, "scientific moves")
    require_equal(payload.get("new_training_runs_started"), 0, "training count")
    require_equal(payload.get("scientific_verdict"), None, "hygiene verdict")
    records = list(payload.get("moved_ephemeral_locks") or [])
    expected = set(payload.get("expected_locks_from_final_score_states") or [])
    require_equal(
        {str(record.get("source_relative_to_attempt")) for record in records},
        expected,
        "verified quarantined locks",
    )
    for record in records:
        destination = repo_path(str(record["destination_path"]))
        actual = file_record(destination, allow_empty=True)
        require_equal(actual["bytes"], 0, "verified lock bytes")
        require_equal(actual["sha256"], EMPTY_SHA256, "verified lock SHA256")
        require_equal(
            record.get("exclusive_lock_acquired_after_scorer_close"),
            True,
            "verified exclusive lock",
        )
    require_equal(list(attempt.rglob("scores.csv.lock")), [], "verified remaining locks")
    return payload


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser()
    result.add_argument("--config", default=str(DEFAULT_CONFIG))
    commands = result.add_subparsers(dest="command", required=True)
    commands.add_parser("validate-config")
    commands.add_parser("cache-probe")
    for command in ("quarantine-locks", "verify-hygiene"):
        sub = commands.add_parser(command)
        sub.add_argument("--building-id", required=True)
        sub.add_argument("--arm", required=True, choices=("Aprime", "B"))
        sub.add_argument("--run", required=True, choices=("r1", "r2"))
        sub.add_argument("--attempt", required=True, type=int)
    return result


def print_json(payload: Any) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), flush=True)


def main(argv: Sequence[str] | None = None) -> int:
    args = parser().parse_args(argv)
    config_path = Path(args.config)
    if not config_path.is_absolute():
        config_path = repo_path(config_path)
    config = load_config(config_path)
    if args.command == "validate-config":
        payload = {
            "schema": CONTRACT_SCHEMA,
            "state": "VALID",
            "config": file_record(config_path),
            "base_readout_config": file_record(
                repo_path(config["cachefix_contract"]["base_readout_config"]["path"])
            ),
            "base_readout_driver": file_record(
                repo_path(config["cachefix_contract"]["base_readout_driver"]["path"])
            ),
            "continuation_lock": file_record(
                repo_path(config["cachefix_contract"]["continuation_lock"]["path"])
            ),
            "scientific_behavior_changed": False,
            "scientific_verdict": None,
        }
    elif args.command == "cache-probe":
        payload = cache_probe(config)
    elif args.command == "quarantine-locks":
        payload = quarantine_ephemeral_locks(
            config, args.building_id, args.arm, args.run, args.attempt
        )
    elif args.command == "verify-hygiene":
        payload = verify_hygiene(
            config, args.building_id, args.arm, args.run, args.attempt
        )
    else:  # pragma: no cover - argparse enforces the command set.
        raise ReadoutCachefixError(f"unknown command: {args.command}")
    print_json(payload)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"[FAILED] {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
        raise
