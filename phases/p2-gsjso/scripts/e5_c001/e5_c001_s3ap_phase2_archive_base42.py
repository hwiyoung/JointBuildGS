#!/usr/bin/env python3
"""Freeze and attest the completed S3-A-prime base-42 Phase-2 wave.

This stdlib-only tool is fail-closed. It copies the runner status CSV and
writes hashes/metadata only; raw logs, checkpoints, bindings, and configs stay
in place. Checkpoint semantics are attested by the locked training-image runner
dry-run and bound here by the canonical JSON hash.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping


REPO = Path(__file__).resolve().parents[3]
DEFAULT_RUN_ROOT = Path("phases/p2-gsjso/runs/e5_c001/20260715_e5_c001_s3ap_phase2_prepare")
DEFAULT_JOBS = DEFAULT_RUN_ROOT / "jobs.csv"
DEFAULT_STATUS = DEFAULT_RUN_ROOT / "runner/status.csv"
DEFAULT_OUTPUT_DIR = DEFAULT_RUN_ROOT / "runner"
DEFAULT_LOCK = Path("phases/p2-gsjso/configs/e5_c001/e5_c001_s3ap_phase2_lock.json")
SNAPSHOT_NAME = "status_base42.csv"
ARTIFACTS_NAME = "artifacts_base42.sha256"
COMPLETION_NAME = "completion_base42.json"
COMPLETION_SCHEMA = "jointbuildgs.s3ap.phase2.base42_completion.v1"
HEX64 = re.compile(r"^[0-9a-f]{64}$")
HEX40 = re.compile(r"^[0-9a-f]{40}$")
BUILDINGS = ("4907199", "8568391", "8568392")
BASE_ARMS = ("a0", "a1", "a2")
REPLICATE_SEEDS = (("r1", "2001"), ("r2", "2002"))
HEIGHT_GRID = (
    ("0.5", "p0p5"), ("-0.5", "m0p5"),
    ("1.0", "p1"), ("-1.0", "m1"),
    ("2.0", "p2"), ("-2.0", "m2"),
    ("4.0", "p4"), ("-4.0", "m4"),
)
TRAINING_IMAGE = "jointbuildgs:dev"
TRAINING_IMAGE_ID = (
    "sha256:926b2fd5e31d9f22d44db347b703ed1acfe0a98d19c189c80324daec63fd6396"
)
TOOLS_IMAGE = "jointbuildgs-p0-tools:t0"
TOOLS_IMAGE_ID = (
    "sha256:87bea02e5598a3d53a119b754191673497d52641bd8ea4106ffee653407579b0"
)
CONTAINER_REPO_ROOT = "/workspace/JointBuildGS"
HOST_LAUNCHER = "phases/p2-gsjso/scripts/e5_c001/run_e5_c001_s3ap_phase2.sh"
ARCHIVE_LAUNCHER = (
    "phases/p2-gsjso/scripts/e5_c001/run_e5_c001_s3ap_phase2_archive_base42.sh"
)
PREWARM_SCRIPT = "scripts/e5_c001/p2_gsjso/e5_c001_s3ap_gsplat_prewarm.py"
PREWARM_MANIFEST = (
    "results/tum_transfer/e5_s3ap_phase2/runtime/gsplat_prewarm.json"
)
PREWARM_SCHEMA = "jointbuildgs.s3ap.phase2.gsplat_prewarm.v1"
PREPARED_SCHEMA = "jointbuildgs.s3ap.phase2.prepared_data.v1"
EXPECTED_CACHE_ENV = {
    "HOME": (
        "/workspace/JointBuildGS/results/tum_transfer/e5_s3ap_phase2/runtime/home"
    ),
    "XDG_CACHE_HOME": (
        "/workspace/JointBuildGS/results/tum_transfer/e5_s3ap_phase2/runtime/xdg_cache"
    ),
    "TORCH_EXTENSIONS_DIR": (
        "/workspace/JointBuildGS/results/tum_transfer/e5_s3ap_phase2/runtime/"
        "torch_extensions"
    ),
}
COMPLETION_OBSERVATIONAL_KEYS = frozenset({
    "created_utc", "archive_git_head", "archive_git_branch",
})

STATUS_HASH_FIELDS = (
    "config_sha256",
    "prepare_manifest_sha256",
    "data_manifest_sha256",
    "surface_seed_sha256",
    "job_binding_sha256",
    "final_checkpoint_sha256",
)
JOB_CSV_FIELDS = (
    "sequence", "job_id", "job_class", "building_id", "arm", "replicate",
    "random_seed", "height_delta_m", "tilt_deg", "config_path",
    "config_sha256", "data_root", "surface_seed_npz",
    "surface_seed_sha256", "out_dir", "final_checkpoint", "iterations",
    "gt_used", "lod2_used", "als_used", "status",
)
STATUS_CSV_FIELDS = (
    "sequence", "job_id", "gpu_id", "status", "attempt", "config_path",
    "config_sha256", "out_dir", "final_checkpoint", "partial_checkpoints",
    "started_utc", "ended_utc", "elapsed_s", "timeout_s", "returncode",
    "log_path", "prepare_manifest_sha256", "data_manifest_sha256",
    "surface_seed_sha256", "job_binding_sha256",
    "final_checkpoint_sha256", "final_checkpoint_it",
    "final_checkpoint_n_prim", "message",
)

STATIC_PROVENANCE = (
    DEFAULT_LOCK,
    Path(HOST_LAUNCHER),
    Path("phases/p2-gsjso/scripts/e5_c001/e5_c001_s3ap_phase2_prepare.py"),
    Path("phases/p2-gsjso/scripts/e5_c001/e5_c001_s3ap_phase2_runner.py"),
    Path(PREWARM_SCRIPT),
    Path("phases/p2-gsjso/scripts/e5_c001/e5_c001_s3ap_phase2_archive_base42.py"),
    Path(ARCHIVE_LAUNCHER),
    Path("src/stage2/train.py"),
)

PER_JOB_ARTIFACTS = (
    "phase2_job_binding.json",
    "effective_config.json",
    "view_roles.json",
    "surface_seed_audit.json",
    "ckpt/final.pt",
)


class ArchiveError(RuntimeError):
    """Fail-closed archival contract violation."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def resolve(repo: Path, value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else repo / path


def relative(repo: Path, path: str | Path) -> str:
    resolved = resolve(repo, path).resolve()
    try:
        return str(resolved.relative_to(repo.resolve()))
    except ValueError as error:
        raise ArchiveError(f"artifact escapes repository root: {resolved}") from error


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path, block_size: int = 1 << 20) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(block_size), b""):
            digest.update(block)
    return digest.hexdigest()


def read_required(path: Path, role: str) -> bytes:
    if not path.is_file():
        raise ArchiveError(f"missing {role}: {path}")
    return path.read_bytes()


def parse_csv_bytes(
    payload: bytes,
    role: str,
    expected_fields: Iterable[str] | None = None,
) -> list[dict[str, str]]:
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ArchiveError(f"{role} is not UTF-8") from error
    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None:
        raise ArchiveError(f"{role} has no header")
    if (
        expected_fields is not None
        and reader.fieldnames != list(expected_fields)
    ):
        raise ArchiveError(
            f"{role} header/order drift: actual={reader.fieldnames!r}, "
            f"expected={list(expected_fields)!r}"
        )
    return list(reader)


def parse_json_object_text(text: str, role: str) -> dict[str, Any]:
    def no_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ArchiveError(f"duplicate JSON key in {role}: {key}")
            result[key] = value
        return result

    try:
        payload = json.loads(text, object_pairs_hook=no_duplicate_keys)
    except json.JSONDecodeError as error:
        raise ArchiveError(f"invalid {role} JSON") from error
    if not isinstance(payload, dict):
        raise ArchiveError(f"{role} must be a JSON object")
    return payload


def load_json_object(path: Path, role: str) -> dict[str, Any]:
    try:
        text = read_required(path, role).decode("utf-8")
    except UnicodeDecodeError as error:
        raise ArchiveError(f"invalid UTF-8 {role}: {path}") from error
    return parse_json_object_text(text, f"{role}: {path}")


def require_hex64(value: Any, role: str) -> None:
    if not HEX64.fullmatch(str(value)):
        raise ArchiveError(f"{role} must be lowercase 64-hex, got {value!r}")


def require_image_id(value: Any, role: str) -> None:
    text = str(value)
    if not text.startswith("sha256:") or not HEX64.fullmatch(text[7:]):
        raise ArchiveError(
            f"{role} must be sha256:<lowercase 64-hex>, got {value!r}"
        )


def require_exact_keys(value: Any, expected: Iterable[str], role: str) -> None:
    if not isinstance(value, Mapping):
        raise ArchiveError(f"{role} must be an object")
    actual_keys = set(value)
    expected_keys = set(expected)
    if actual_keys != expected_keys:
        raise ArchiveError(
            f"{role} key-set drift: actual={sorted(actual_keys)!r}, "
            f"expected={sorted(expected_keys)!r}"
        )


def require_json_int(value: Any, expected: int, role: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value != expected:
        raise ArchiveError(f"{role} must be integer {expected}, got {value!r}")


def require_json_false(value: Any, role: str) -> None:
    if value is not False:
        raise ArchiveError(f"{role} must be JSON false, got {value!r}")


def require_json_true(value: Any, role: str) -> None:
    if value is not True:
        raise ArchiveError(f"{role} must be JSON true, got {value!r}")


def parse_positive_int(value: Any, role: str) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError) as error:
        raise ArchiveError(f"{role} must be an integer, got {value!r}") from error
    if number <= 0:
        raise ArchiveError(f"{role} must be positive, got {number}")
    return number


def require_csv_false(value: Any, role: str) -> None:
    if str(value).strip().lower() not in {"false", "0"}:
        raise ArchiveError(f"{role} must be false, got {value!r}")


def canonical_json_bytes(payload: Mapping[str, Any]) -> bytes:
    try:
        return json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as error:
        raise ArchiveError("attestation is not canonicalizable JSON") from error


def json_exact_equal(left: Any, right: Any) -> bool:
    return canonical_json_bytes({"value": left}) == canonical_json_bytes(
        {"value": right}
    )


def add_artifact(
    repo: Path,
    artifacts: dict[str, str],
    path: str | Path,
    *,
    expected_hash: str | None = None,
) -> str:
    resolved = resolve(repo, path)
    rel = relative(repo, resolved)
    if rel in artifacts:
        actual = artifacts[rel]
    else:
        if not resolved.is_file():
            raise ArchiveError(f"missing artifact: {rel}")
        actual = sha256_file(resolved)
        artifacts[rel] = actual
    if expected_hash is not None and actual != expected_hash:
        raise ArchiveError(
            f"artifact hash mismatch: {rel}: {actual} != {expected_hash}"
        )
    return actual


def expected_job_grid() -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for building in BUILDINGS:
        for arm in BASE_ARMS:
            for replicate, random_seed in REPLICATE_SEEDS:
                job_id = f"gs_e5_C001_s3ap_b{building}_{arm}_{replicate}"
                rows.append({
                    "job_id": job_id,
                    "job_class": "base",
                    "building_id": building,
                    "arm": arm,
                    "replicate": replicate,
                    "random_seed": random_seed,
                    "height_delta_m": "0.0",
                    "tilt_deg": "0.0",
                })
    for building in BUILDINGS:
        for height, slug in HEIGHT_GRID:
            job_id = f"gs_e5_C001_s3ap_b{building}_a1_dz_{slug}_r1"
            rows.append({
                "job_id": job_id,
                "job_class": "height",
                "building_id": building,
                "arm": "a1",
                "replicate": "r1",
                "random_seed": "2001",
                "height_delta_m": height,
                "tilt_deg": "0.0",
            })
    for row in rows:
        building = row["building_id"]
        job_id = row["job_id"]
        row["config_path"] = str(
            DEFAULT_RUN_ROOT / "configs" / f"{job_id}.yaml"
        )
        row["data_root"] = (
            f"results/tum_transfer/e5_s3ap_phase2/prepared/DEBY_LOD2_{building}"
        )
        if row["arm"] == "a0":
            row["surface_seed_npz"] = (
                "phases/p2-gsjso/runs/e5_c001/20260715_e5_c001_s3ap_phase1_seedprep/"
                f"seeds/DEBY_LOD2_{building}_p0_surface_seed.npz"
            )
        else:
            row["surface_seed_npz"] = (
                f"{row['data_root']}/seeds/"
                f"DEBY_LOD2_{building}_a1a2_surface_seed.npz"
            )
        row["out_dir"] = (
            f"results/tum_transfer/e5_s3ap_phase2/runs/{job_id}"
        )
        row["final_checkpoint"] = f"{row['out_dir']}/ckpt/final.pt"
        row["iterations"] = "30000"
    return rows


def validate_jobs(rows: list[dict[str, str]]) -> list[str]:
    if len(rows) != 42:
        raise ArchiveError(
            f"jobs.csv must contain exactly 42 rows, got {len(rows)}"
        )
    ids = [row.get("job_id", "") for row in rows]
    if any(not value for value in ids) or len(set(ids)) != 42:
        raise ArchiveError("jobs.csv must contain 42 nonempty unique job IDs")
    sequences = [row.get("sequence", "") for row in rows]
    if sequences != [str(value) for value in range(1, 43)]:
        raise ArchiveError("jobs.csv sequence must be exactly 1..42 in row order")
    expected = expected_job_grid()
    locked_fields = (
        "job_id", "job_class", "building_id", "arm", "replicate",
        "random_seed", "height_delta_m", "tilt_deg", "config_path",
        "data_root", "surface_seed_npz", "out_dir", "final_checkpoint",
        "iterations",
    )
    for sequence, (row, expected_row) in enumerate(zip(rows, expected), 1):
        job_id = row["job_id"]
        for field in locked_fields:
            if row.get(field) != expected_row[field]:
                raise ArchiveError(
                    f"jobs.csv locked tuple drift at sequence {sequence}: "
                    f"{field}={row.get(field)!r}, "
                    f"expected {expected_row[field]!r}"
                )
        if row.get("status") != "prepared":
            raise ArchiveError(f"{job_id}: inventory status must be prepared")
        for field in ("gt_used", "lod2_used", "als_used"):
            require_csv_false(row.get(field, ""), f"{job_id}:{field}")
        for field in ("config_sha256", "surface_seed_sha256"):
            require_hex64(row.get(field, ""), f"{job_id}:{field}")
    return ids


def container_to_repo_path(
    repo: Path, lock: Mapping[str, Any], value: Any, role: str,
) -> Path:
    root_text = lock.get("container_repo_root")
    if root_text != CONTAINER_REPO_ROOT:
        raise ArchiveError(
            f"Phase-2 container repo root drift: {root_text!r}"
        )
    root = Path(CONTAINER_REPO_ROOT)
    path = Path(str(value))
    try:
        suffix = path.relative_to(root)
    except ValueError as error:
        raise ArchiveError(
            f"{role} escapes locked container repo root: {path}"
        ) from error
    resolved = (repo / suffix).resolve()
    relative(repo, resolved)
    return resolved


def validate_attested_cache(
    value: Any, expected: Mapping[str, str], role: str,
) -> None:
    require_exact_keys(value, expected, role)
    for name, expected_path in expected.items():
        entry = value[name]
        require_exact_keys(entry, ("path", "writable"), f"{role}:{name}")
        if entry.get("path") != expected_path:
            raise ArchiveError(
                f"{role}:{name} path drift: "
                f"{entry.get('path')!r} != {expected_path!r}"
            )
        require_json_true(
            entry.get("writable"), f"{role}:{name}:writable"
        )


def validate_uid_mapping(attestation: Mapping[str, Any], role: str) -> None:
    for field in ("container_uid", "container_gid", "host_uid", "host_gid"):
        value = attestation.get(field)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ArchiveError(
                f"{role}:{field} must be a nonnegative JSON integer"
            )
    if (
        attestation["container_uid"] != attestation["host_uid"]
        or attestation["container_gid"] != attestation["host_gid"]
    ):
        raise ArchiveError(f"{role} container/host UID/GID mapping drift")


def validate_runner_runtime_attestation(value: Any, role: str) -> None:
    expected_keys = (
        "docker_image_id", "container_uid", "container_gid", "host_uid",
        "host_gid", "writable_cache_env",
    )
    require_exact_keys(value, expected_keys, role)
    if value.get("docker_image_id") != TRAINING_IMAGE_ID:
        raise ArchiveError(f"{role} Docker image ID drift")
    require_image_id(
        value.get("docker_image_id"), f"{role}:docker_image_id"
    )
    validate_uid_mapping(value, role)
    validate_attested_cache(
        value.get("writable_cache_env"), EXPECTED_CACHE_ENV, role
    )


def validate_prepare_runtime_attestation(value: Any) -> None:
    role = "prepare runtime attestation"
    expected_keys = (
        "docker_image", "docker_image_id", "container_uid", "container_gid",
        "host_uid", "host_gid", "user_mapping_exact",
        "writable_cache_env",
    )
    require_exact_keys(value, expected_keys, role)
    if value.get("docker_image") != TRAINING_IMAGE:
        raise ArchiveError("prepare Docker image tag drift")
    if value.get("docker_image_id") != TRAINING_IMAGE_ID:
        raise ArchiveError("prepare Docker image ID drift")
    require_image_id(
        value.get("docker_image_id"), f"{role}:docker_image_id"
    )
    require_json_true(
        value.get("user_mapping_exact"), f"{role}:user_mapping_exact"
    )
    validate_uid_mapping(value, role)
    validate_attested_cache(
        value.get("writable_cache_env"), EXPECTED_CACHE_ENV, role
    )


def validate_lock_contract(
    repo: Path,
    lock: Mapping[str, Any],
    run_root: Path,
    jobs_path: Path,
    status_path: Path,
) -> None:
    if lock.get("schema") != "jointbuildgs.s3ap.phase2.lock.v1":
        raise ArchiveError("Phase-2 lock schema drift")
    if lock.get("container_repo_root") != CONTAINER_REPO_ROOT:
        raise ArchiveError("Phase-2 lock container_repo_root drift")

    targets = lock.get("targets")
    if not isinstance(targets, Mapping) or list(targets) != list(BUILDINGS):
        raise ArchiveError("Phase-2 lock target keys/order drift")

    training = lock.get("training")
    if not isinstance(training, Mapping):
        raise ArchiveError("Phase-2 lock training contract absent")
    require_json_int(
        training.get("iterations"), 30000, "Phase-2 training iterations"
    )
    replicates = training.get("replicates")
    if (
        not isinstance(replicates, Mapping)
        or list(replicates) != ["r1", "r2"]
        or not json_exact_equal(replicates, {"r1": 2001, "r2": 2002})
    ):
        raise ArchiveError("Phase-2 training replicates/order drift")
    arms = training.get("arms")
    if not isinstance(arms, Mapping) or list(arms) != list(BASE_ARMS):
        raise ArchiveError("Phase-2 training arm keys/order drift")
    expected_height = [0.5, -0.5, 1.0, -1.0, 2.0, -2.0, 4.0, -4.0]
    if json.dumps(
        training.get("height_perturbation_m"), separators=(",", ":")
    ) != json.dumps(expected_height, separators=(",", ":")):
        raise ArchiveError("Phase-2 height perturbation grid/order drift")

    run_rel = relative(repo, run_root)
    expected_outputs = {
        "prepared_root": "results/tum_transfer/e5_s3ap_phase2/prepared",
        "training_root": "results/tum_transfer/e5_s3ap_phase2/runs",
        "prepare_run_root": run_rel,
        "generated_config_dir": f"{run_rel}/configs",
        "base_inventory": relative(repo, jobs_path),
        "prepare_manifest": f"{run_rel}/manifest.json",
        "runner_status": relative(repo, status_path),
        "runner_log_dir": f"{run_rel}/runner/logs",
    }
    outputs = lock.get("outputs")
    if not isinstance(outputs, Mapping):
        raise ArchiveError("Phase-2 lock outputs contract absent")
    for field, expected in expected_outputs.items():
        if outputs.get(field) != expected:
            raise ArchiveError(
                f"Phase-2 output {field} drift: "
                f"{outputs.get(field)!r} != {expected!r}"
            )

    safety = lock.get("safety")
    if not isinstance(safety, Mapping):
        raise ArchiveError("Phase-2 safety contract absent")
    for field in (
        "prepare_starts_training",
        "gt_lod2_or_als_allowed_for_input_generation",
        "mvs_initialization_allowed",
    ):
        require_json_false(safety.get(field), f"Phase-2 safety:{field}")
    metadata = safety.get("output_metadata")
    require_exact_keys(
        metadata,
        ("gt_used", "lod2_used", "als_used"),
        "Phase-2 output metadata",
    )
    for field in ("gt_used", "lod2_used", "als_used"):
        require_json_false(
            metadata.get(field), f"Phase-2 output metadata:{field}"
        )

    runtime = lock.get("runtime")
    if not isinstance(runtime, Mapping):
        raise ArchiveError("Phase-2 runtime contract absent")
    if runtime.get("docker_image") != TRAINING_IMAGE:
        raise ArchiveError("Phase-2 training Docker image tag drift")
    if runtime.get("docker_image_id") != TRAINING_IMAGE_ID:
        raise ArchiveError("Phase-2 training Docker image ID drift")
    require_image_id(
        runtime.get("docker_image_id"), "Phase-2 runtime docker_image_id"
    )
    if runtime.get("host_launcher") != HOST_LAUNCHER:
        raise ArchiveError("Phase-2 host launcher drift")
    if not json_exact_equal(runtime.get("gpu_ids"), [0, 1]):
        raise ArchiveError("Phase-2 GPU ID lock drift")
    require_json_int(
        runtime.get("default_run_timeout_s"), 7200, "Phase-2 timeout"
    )
    if runtime.get("writable_cache_env") != EXPECTED_CACHE_ENV:
        raise ArchiveError("Phase-2 writable cache lock drift")
    prewarm = runtime.get("gsplat_prewarm")
    if not isinstance(prewarm, Mapping):
        raise ArchiveError("Phase-2 gsplat prewarm lock absent")
    if (
        prewarm.get("script") != PREWARM_SCRIPT
        or prewarm.get("manifest") != PREWARM_MANIFEST
    ):
        raise ArchiveError(
            "Phase-2 gsplat prewarm script/manifest lock drift"
        )


def validate_prewarm_contract(
    repo: Path,
    lock_path: Path,
    lock_hash: str,
    lock: Mapping[str, Any],
    prewarm_path: Path,
    prewarm: Mapping[str, Any],
    artifacts: dict[str, str],
) -> None:
    if relative(repo, prewarm_path) != PREWARM_MANIFEST:
        raise ArchiveError("gsplat prewarm manifest path drift")
    if (
        prewarm.get("schema") != PREWARM_SCHEMA
        or prewarm.get("status") != "complete"
    ):
        raise ArchiveError("gsplat prewarm schema/status drift")
    if prewarm.get("lock_path") != relative(repo, lock_path):
        raise ArchiveError("gsplat prewarm lock path drift")
    if prewarm.get("lock_sha256") != lock_hash:
        raise ArchiveError("gsplat prewarm lock hash drift")
    validate_runner_runtime_attestation(
        prewarm.get("runtime_attestation"),
        "gsplat prewarm runtime attestation",
    )

    if prewarm.get("script") != PREWARM_SCRIPT:
        raise ArchiveError("gsplat prewarm script path drift")
    script_hash = add_artifact(repo, artifacts, PREWARM_SCRIPT)
    if prewarm.get("script_sha256") != script_hash:
        raise ArchiveError("gsplat prewarm script hash drift")

    cache_root = EXPECTED_CACHE_ENV["TORCH_EXTENSIONS_DIR"]
    if prewarm.get("torch_extensions_dir") != cache_root:
        raise ArchiveError("gsplat prewarm cache root drift")
    for name, container_path in EXPECTED_CACHE_ENV.items():
        host_path = container_to_repo_path(
            repo, lock, container_path, f"prewarm cache {name}"
        )
        if not host_path.is_dir():
            raise ArchiveError(
                "gsplat prewarm cache directory missing: "
                f"{relative(repo, host_path)}"
            )
    expected_extension = f"{cache_root}/gsplat_cuda/gsplat_cuda.so"
    if prewarm.get("extension_module") != "gsplat.cuda._backend._C":
        raise ArchiveError("gsplat prewarm extension module drift")
    if prewarm.get("extension_path") != expected_extension:
        raise ArchiveError("gsplat prewarm extension path drift")
    extension_path = container_to_repo_path(
        repo, lock, expected_extension, "gsplat extension path"
    )
    extension_hash = add_artifact(repo, artifacts, extension_path)
    if prewarm.get("extension_sha256") != extension_hash:
        raise ArchiveError(
            "gsplat prewarm extension hash differs from actual shared object"
        )
    add_artifact(repo, artifacts, prewarm_path)


def validate_prepare_contract(
    repo: Path,
    run_root: Path,
    jobs_path: Path,
    status_path: Path,
    jobs: list[dict[str, str]],
    jobs_bytes: bytes,
    artifacts: dict[str, str],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    prepare_path = run_root / "manifest.json"
    prepare = load_json_object(prepare_path, "Phase-2 prepare manifest")
    if (
        prepare.get("schema")
        != "jointbuildgs.s3ap.phase2.prepare_manifest.v1"
        or prepare.get("status") != "complete"
        or prepare.get("mode") != "base"
    ):
        raise ArchiveError("Phase-2 prepare manifest base-42 contract drift")
    require_json_false(
        prepare.get("training_started"), "prepare training_started"
    )
    require_json_int(prepare.get("job_count"), 42, "prepare job_count")
    for field in ("gt_used", "lod2_used", "als_used"):
        require_json_false(prepare.get(field), f"prepare:{field}")

    jobs_hash = sha256_bytes(jobs_bytes)
    if (
        prepare.get("inventory") != relative(repo, jobs_path)
        or prepare.get("inventory_sha256") != jobs_hash
    ):
        raise ArchiveError("prepare manifest inventory path/hash drift")
    manifest_jobs = prepare.get("jobs")
    if not isinstance(manifest_jobs, list) or len(manifest_jobs) != 42:
        raise ArchiveError(
            "prepare manifest jobs must contain exactly 42 entries"
        )
    for job, manifest_job in zip(jobs, manifest_jobs):
        expected = {
            "job_id": job["job_id"],
            "config_path": job["config_path"],
            "config_sha256": job["config_sha256"],
            "final_checkpoint": job["final_checkpoint"],
        }
        require_exact_keys(
            manifest_job, expected, f"prepare job:{job['job_id']}"
        )
        if not json_exact_equal(manifest_job, expected):
            raise ArchiveError(
                f"prepare job contract drift: {job['job_id']}"
            )

    if prepare.get("lock_path") != str(DEFAULT_LOCK):
        raise ArchiveError("prepare manifest lock path drift")
    lock_path = resolve(repo, DEFAULT_LOCK)
    lock = load_json_object(lock_path, "Phase-2 lock")
    lock_hash = add_artifact(repo, artifacts, lock_path)
    if prepare.get("lock_sha256") != lock_hash:
        raise ArchiveError("prepare manifest lock hash drift")
    validate_lock_contract(repo, lock, run_root, jobs_path, status_path)
    validate_prepare_runtime_attestation(prepare.get("runtime_attestation"))

    prepared = prepare.get("prepared_buildings")
    if not isinstance(prepared, Mapping) or list(prepared) != list(BUILDINGS):
        raise ArchiveError(
            "prepare manifest prepared_buildings keys/order drift"
        )

    prewarm_path = resolve(repo, PREWARM_MANIFEST)
    prewarm = load_json_object(prewarm_path, "gsplat prewarm manifest")
    validate_prewarm_contract(
        repo,
        lock_path,
        lock_hash,
        lock,
        prewarm_path,
        prewarm,
        artifacts,
    )
    add_artifact(repo, artifacts, jobs_path, expected_hash=jobs_hash)
    add_artifact(repo, artifacts, prepare_path)
    return prepare, lock, prewarm


def validate_prepared_data_manifest(
    repo: Path,
    prepare: Mapping[str, Any],
    building: str,
    data_root_rel: str,
    expected_status_hash: str,
    artifacts: dict[str, str],
) -> str:
    expected_root = (
        "results/tum_transfer/e5_s3ap_phase2/prepared/"
        f"DEBY_LOD2_{building}"
    )
    if data_root_rel != expected_root:
        raise ArchiveError(f"{building}: prepared data_root drift")
    expected_manifest = f"{expected_root}/data_manifest.json"
    data_path = resolve(repo, expected_manifest)
    data = load_json_object(
        data_path, f"{building} prepared data manifest"
    )
    expected_values: dict[str, Any] = {
        "schema": PREPARED_SCHEMA,
        "building_id": f"DEBY_LOD2_{building}",
        "data_root": expected_root,
        "gt_used": False,
        "lod2_used": False,
        "als_used": False,
    }
    for field, expected in expected_values.items():
        actual = data.get(field)
        if actual != expected or type(actual) is not type(expected):
            raise ArchiveError(
                f"{building}: prepared data manifest {field} drift: "
                f"{actual!r} != {expected!r}"
            )

    prepared_buildings = prepare.get("prepared_buildings")
    entry = (
        prepared_buildings.get(building)
        if isinstance(prepared_buildings, Mapping)
        else None
    )
    if not isinstance(entry, Mapping):
        raise ArchiveError(
            f"{building}: prepare prepared_buildings entry absent"
        )
    for field, expected in expected_values.items():
        actual = entry.get(field)
        if actual != expected or type(actual) is not type(expected):
            raise ArchiveError(
                f"{building}: prepare prepared_buildings {field} drift"
            )
    if entry.get("data_manifest") != expected_manifest:
        raise ArchiveError(f"{building}: prepare data_manifest path drift")
    actual_hash = sha256_file(data_path)
    if entry.get("data_manifest_sha256") != actual_hash:
        raise ArchiveError(
            f"{building}: prepare data manifest hash differs from actual file"
        )
    if expected_status_hash != actual_hash:
        raise ArchiveError(
            f"{building}: status data manifest hash differs from actual file"
        )
    add_artifact(
        repo, artifacts, data_path, expected_hash=actual_hash
    )
    return actual_hash


def validate_runner_dry_run_attestation(
    payload: Mapping[str, Any],
    *,
    repo: Path,
    jobs_path: Path,
    prepare_manifest_sha256: str,
    lock: Mapping[str, Any],
) -> str:
    expected_keys = (
        "inventory", "jobs", "status_counts", "gpu_ids", "timeout_s",
        "runtime_attestation", "prepare_manifest_sha256",
        "training_started",
    )
    require_exact_keys(
        payload, expected_keys, "runner dry-run attestation"
    )
    if payload.get("inventory") != relative(repo, jobs_path):
        raise ArchiveError("runner dry-run inventory path drift")
    require_json_int(payload.get("jobs"), 42, "runner dry-run jobs")
    if not json_exact_equal(
        payload.get("status_counts"), {"skipped_final_exists": 42}
    ):
        raise ArchiveError(
            "runner dry-run must attest skipped_final_exists=42 only"
        )
    runtime = lock.get("runtime")
    if not json_exact_equal(
        payload.get("gpu_ids"), runtime.get("gpu_ids")
    ):
        raise ArchiveError("runner dry-run GPU IDs drift")
    if payload.get("timeout_s") != runtime.get("default_run_timeout_s"):
        raise ArchiveError("runner dry-run timeout drift")
    if payload.get("prepare_manifest_sha256") != prepare_manifest_sha256:
        raise ArchiveError("runner dry-run prepare manifest hash drift")
    require_json_false(
        payload.get("training_started"),
        "runner dry-run training_started",
    )
    validate_runner_runtime_attestation(
        payload.get("runtime_attestation"),
        "runner dry-run runtime attestation",
    )
    return sha256_bytes(canonical_json_bytes(payload))


def validate_tools_image_id(value: Any) -> str:
    require_image_id(value, "archive tools image ID")
    if value != TOOLS_IMAGE_ID:
        raise ArchiveError(
            f"archive tools image ID drift: {value!r} != {TOOLS_IMAGE_ID!r}"
        )
    return str(value)


def validate_status_and_collect(
    repo: Path,
    run_root: Path,
    jobs: list[dict[str, str]],
    status_rows: list[dict[str, str]],
    prepare: Mapping[str, Any],
    artifacts: dict[str, str],
) -> dict[str, Any]:
    if len(status_rows) != 42:
        raise ArchiveError(
            f"status.csv must contain exactly 42 rows, got {len(status_rows)}"
        )
    job_ids = [row["job_id"] for row in jobs]
    status_ids = [row.get("job_id", "") for row in status_rows]
    if status_ids != job_ids or len(set(status_ids)) != 42:
        raise ArchiveError(
            "status.csv job IDs/order must exactly equal jobs.csv"
        )

    total_final_bytes = 0
    n_primitives: dict[str, int] = {}
    validated_data_hashes: dict[str, str] = {}
    for job, status in zip(jobs, status_rows):
        job_id = job["job_id"]
        if status.get("sequence") != job.get("sequence"):
            raise ArchiveError(
                f"{job_id}: status sequence differs from jobs.csv"
            )
        if status.get("status") != "complete":
            raise ArchiveError(f"{job_id}: runner status must be complete")
        if status.get("returncode") != "0":
            raise ArchiveError(f"{job_id}: runner returncode must be 0")
        if status.get("final_checkpoint_it") != "30000":
            raise ArchiveError(
                f"{job_id}: final checkpoint iteration must be 30000"
            )
        n_primitives[job_id] = parse_positive_int(
            status.get("final_checkpoint_n_prim", ""),
            f"{job_id}:final_checkpoint_n_prim",
        )
        for field in STATUS_HASH_FIELDS:
            require_hex64(status.get(field, ""), f"{job_id}:{field}")
        comparisons = (
            ("config_path", "config_path"),
            ("config_sha256", "config_sha256"),
            ("out_dir", "out_dir"),
            ("final_checkpoint", "final_checkpoint"),
            ("surface_seed_sha256", "surface_seed_sha256"),
        )
        for status_field, job_field in comparisons:
            if status.get(status_field) != job.get(job_field):
                raise ArchiveError(
                    f"{job_id}: {status_field} differs from jobs.csv"
                )

        add_artifact(
            repo,
            artifacts,
            job["config_path"],
            expected_hash=status["config_sha256"],
        )
        add_artifact(
            repo,
            artifacts,
            job["surface_seed_npz"],
            expected_hash=status["surface_seed_sha256"],
        )
        building = job["building_id"]
        if building not in validated_data_hashes:
            validated_data_hashes[building] = validate_prepared_data_manifest(
                repo,
                prepare,
                building,
                job["data_root"],
                status["data_manifest_sha256"],
                artifacts,
            )
        elif (
            status["data_manifest_sha256"]
            != validated_data_hashes[building]
        ):
            raise ArchiveError(
                f"{job_id}: data manifest hash differs within building"
            )

        out_dir = resolve(repo, job["out_dir"])
        binding_path = out_dir / "phase2_job_binding.json"
        add_artifact(
            repo,
            artifacts,
            binding_path,
            expected_hash=status["job_binding_sha256"],
        )
        binding = load_json_object(binding_path, f"{job_id} binding")
        binding_expected: dict[str, Any] = {
            "schema": "jointbuildgs.s3ap.phase2.job_binding.v1",
            "job_id": job_id,
            "config_path": job["config_path"],
            "config_sha256": job["config_sha256"],
            "data_root": job["data_root"],
            "surface_seed_npz": job["surface_seed_npz"],
            "surface_seed_sha256": job["surface_seed_sha256"],
            "iterations": 30000,
        }
        require_exact_keys(
            binding, binding_expected, f"{job_id}:binding"
        )
        for field, expected_value in binding_expected.items():
            if not json_exact_equal(binding.get(field), expected_value):
                raise ArchiveError(
                    f"{job_id}: binding {field} differs from jobs.csv/lock: "
                    f"{binding.get(field)!r} != {expected_value!r}"
                )

        for suffix in PER_JOB_ARTIFACTS[1:-1]:
            add_artifact(repo, artifacts, out_dir / suffix)
        final_path = resolve(repo, job["final_checkpoint"])
        add_artifact(
            repo,
            artifacts,
            final_path,
            expected_hash=status["final_checkpoint_sha256"],
        )
        total_final_bytes += final_path.stat().st_size

        expected_log = (
            run_root / "runner/logs" / f"{job_id}.log"
        )
        if status.get("log_path") != relative(repo, expected_log):
            raise ArchiveError(f"{job_id}: runner log path drift")
        add_artifact(repo, artifacts, expected_log)

    prepare_hashes = {
        row["prepare_manifest_sha256"] for row in status_rows
    }
    if len(prepare_hashes) != 1:
        raise ArchiveError(
            "status rows disagree on prepare manifest hash"
        )
    return {
        "complete_jobs": 42,
        "total_final_checkpoint_bytes": total_final_bytes,
        "final_n_prim_min": min(n_primitives.values()),
        "final_n_prim_max": max(n_primitives.values()),
        "prepare_manifest_sha256": next(iter(prepare_hashes)),
    }


def artifact_manifest_bytes(artifacts: Mapping[str, str]) -> bytes:
    for path, digest in artifacts.items():
        require_hex64(digest, f"artifact:{path}")
        if "\n" in path or "\r" in path:
            raise ArchiveError(f"newline in artifact path: {path!r}")
    text = "".join(
        f"{artifacts[path]}  {path}\n" for path in sorted(artifacts)
    )
    return text.encode("utf-8")


def git_value(repo: Path, *args: str) -> str:
    try:
        return subprocess.check_output(
            ["git", *args],
            cwd=repo,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return ""


def atomic_write_idempotent(path: Path, payload: bytes) -> str:
    """Write atomically; an identical existing immutable file is success."""

    if path.exists():
        if not path.is_file() or path.read_bytes() != payload:
            raise ArchiveError(
                "immutable archive output already exists with different "
                f"bytes: {path}"
            )
        return "existing_identical"
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp.{os.getpid()}")
    try:
        with temporary.open("xb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        try:
            directory_fd = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        except OSError:
            pass
    finally:
        if temporary.exists():
            temporary.unlink()
    return "created"


def require_existing_equal(path: Path, payload: bytes) -> None:
    if (
        path.exists()
        and (not path.is_file() or path.read_bytes() != payload)
    ):
        raise ArchiveError(
            "immutable archive output already exists with different "
            f"bytes: {path}"
        )


def validate_observational_completion_fields(
    completion: Mapping[str, Any],
) -> None:
    created = completion.get("created_utc")
    if not isinstance(created, str) or not created:
        raise ArchiveError("completion created_utc must be a nonempty string")
    try:
        parsed = datetime.fromisoformat(created)
    except ValueError as error:
        raise ArchiveError("completion created_utc is not ISO-8601") from error
    if parsed.tzinfo is None:
        raise ArchiveError("completion created_utc must include a timezone")
    head = completion.get("archive_git_head")
    if not isinstance(head, str) or (head and not HEX40.fullmatch(head)):
        raise ArchiveError(
            "completion archive_git_head must be empty or lowercase 40-hex"
        )
    if not isinstance(completion.get("archive_git_branch"), str):
        raise ArchiveError(
            "completion archive_git_branch must be a string"
        )


def validate_embedded_runner_attestation(
    completion: Mapping[str, Any],
) -> None:
    payload = completion.get("runner_dry_run_attestation")
    if not isinstance(payload, Mapping):
        raise ArchiveError(
            "completion_base42.json runner dry-run attestation is absent"
        )
    actual_hash = sha256_bytes(canonical_json_bytes(payload))
    if completion.get("runner_dry_run_attestation_sha256") != actual_hash:
        raise ArchiveError(
            "completion_base42.json embedded runner attestation hash mismatch"
        )


def reconcile_existing_completion(
    existing: Mapping[str, Any],
    recomputed: Mapping[str, Any],
) -> dict[str, Any]:
    if set(existing) != set(recomputed):
        raise ArchiveError(
            "immutable completion_base42.json key-set differs from "
            "recomputed contract"
        )
    validate_observational_completion_fields(existing)
    validate_embedded_runner_attestation(existing)
    expected = dict(recomputed)
    for key in COMPLETION_OBSERVATIONAL_KEYS:
        expected[key] = existing[key]
    differing = [
        key
        for key in expected
        if not json_exact_equal(existing.get(key), expected[key])
    ]
    if differing:
        raise ArchiveError(
            "immutable completion_base42.json fields differ from validated "
            f"sources: {sorted(differing)!r}"
        )
    return dict(existing)


def archive_base42(
    *,
    repo: Path,
    jobs_path: Path,
    status_path: Path,
    output_dir: Path,
    runner_dry_run_attestation: Mapping[str, Any],
    tools_image_id: str,
    dry_run: bool = False,
) -> dict[str, Any]:
    repo = repo.resolve()
    jobs_path = resolve(repo, jobs_path)
    status_path = resolve(repo, status_path)
    output_dir = resolve(repo, output_dir)
    run_root = jobs_path.parent
    if jobs_path != resolve(repo, DEFAULT_JOBS):
        raise ArchiveError("jobs.csv must remain at the canonical locked path")
    if run_root != resolve(repo, DEFAULT_RUN_ROOT):
        raise ArchiveError("jobs.csv must remain at the locked base-42 run root")
    if status_path != resolve(repo, DEFAULT_STATUS):
        raise ArchiveError("status.csv must remain at the locked runner path")
    if output_dir != status_path.parent:
        raise ArchiveError(
            "base-42 archive outputs must remain in the runner directory"
        )
    validated_tools_image_id = validate_tools_image_id(tools_image_id)

    jobs_bytes = read_required(jobs_path, "jobs.csv")
    status_bytes = read_required(status_path, "runner status.csv")
    jobs = parse_csv_bytes(jobs_bytes, "jobs.csv", JOB_CSV_FIELDS)
    status_rows = parse_csv_bytes(
        status_bytes, "runner status.csv", STATUS_CSV_FIELDS
    )
    validate_jobs(jobs)

    artifacts: dict[str, str] = {}
    prepare, lock, prewarm = validate_prepare_contract(
        repo,
        run_root,
        jobs_path,
        status_path,
        jobs,
        jobs_bytes,
        artifacts,
    )
    actual_prepare_hash = sha256_file(run_root / "manifest.json")
    runner_attestation_hash = validate_runner_dry_run_attestation(
        runner_dry_run_attestation,
        repo=repo,
        jobs_path=jobs_path,
        prepare_manifest_sha256=actual_prepare_hash,
        lock=lock,
    )
    runner_attestation_canonical = parse_json_object_text(
        canonical_json_bytes(runner_dry_run_attestation).decode("utf-8"),
        "canonical runner dry-run attestation",
    )
    status_summary = validate_status_and_collect(
        repo, run_root, jobs, status_rows, prepare, artifacts
    )
    if (
        status_summary["prepare_manifest_sha256"]
        != actual_prepare_hash
    ):
        raise ArchiveError(
            "status rows' prepare manifest hash differs from the actual file"
        )

    for rel_path in STATIC_PROVENANCE:
        add_artifact(repo, artifacts, rel_path)
    snapshot_path = output_dir / SNAPSHOT_NAME
    snapshot_rel = relative(repo, snapshot_path)
    snapshot_hash = sha256_bytes(status_bytes)
    artifacts[snapshot_rel] = snapshot_hash
    artifacts_bytes = artifact_manifest_bytes(artifacts)
    artifacts_path = output_dir / ARTIFACTS_NAME
    artifacts_hash = sha256_bytes(artifacts_bytes)
    prewarm_hash = sha256_file(resolve(repo, PREWARM_MANIFEST))

    completion = {
        "schema": COMPLETION_SCHEMA,
        "created_utc": utc_now(),
        "status": "complete",
        "wave": "base42",
        "job_count": 42,
        "job_status_counts": {"complete": 42},
        "returncode_counts": {"0": 42},
        "iterations": 30000,
        "jobs_csv": relative(repo, jobs_path),
        "jobs_csv_sha256": sha256_bytes(jobs_bytes),
        "source_status_csv": relative(repo, status_path),
        "source_status_csv_sha256": sha256_bytes(status_bytes),
        "status_snapshot": snapshot_rel,
        "status_snapshot_sha256": snapshot_hash,
        "artifacts_manifest": relative(repo, artifacts_path),
        "artifacts_manifest_sha256": artifacts_hash,
        "artifacts_manifest_entry_count": len(artifacts),
        "final_checkpoint_count": 42,
        "total_final_checkpoint_bytes": (
            status_summary["total_final_checkpoint_bytes"]
        ),
        "final_n_prim_min": status_summary["final_n_prim_min"],
        "final_n_prim_max": status_summary["final_n_prim_max"],
        "phase2_lock_sha256": prepare["lock_sha256"],
        "prepare_manifest_sha256": actual_prepare_hash,
        "prepare_git_head": prepare.get("git_head", ""),
        "docker_image_id": TRAINING_IMAGE_ID,
        "archive_tools_image": TOOLS_IMAGE,
        "archive_tools_image_id": validated_tools_image_id,
        "prewarm_manifest": PREWARM_MANIFEST,
        "prewarm_manifest_sha256": prewarm_hash,
        "prewarm_status": prewarm.get("status", ""),
        "runner_dry_run_attestation": runner_attestation_canonical,
        "runner_dry_run_attestation_sha256": runner_attestation_hash,
        "runner_dry_run_status_counts": {
            "skipped_final_exists": 42
        },
        "runner_dry_run_training_started": False,
        "archive_git_head": git_value(repo, "rev-parse", "HEAD"),
        "archive_git_branch": git_value(
            repo, "branch", "--show-current"
        ),
        "raw_logs_copied": False,
        "raw_checkpoints_copied": False,
        "artifact_policy": (
            "hashes only for runtime logs/checkpoints/bindings/config "
            "audits; no raw runtime payload copied"
        ),
    }
    validate_observational_completion_fields(completion)
    validate_embedded_runner_attestation(completion)
    if dry_run:
        return {
            **completion,
            "dry_run": True,
            "outputs_written": False,
        }

    completion_path = output_dir / COMPLETION_NAME
    require_existing_equal(snapshot_path, status_bytes)
    require_existing_equal(artifacts_path, artifacts_bytes)
    if completion_path.exists():
        existing = load_json_object(
            completion_path, "base-42 completion manifest"
        )
        completion = reconcile_existing_completion(existing, completion)
    completion_bytes = (
        json.dumps(completion, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    require_existing_equal(completion_path, completion_bytes)
    write_results = {
        SNAPSHOT_NAME: atomic_write_idempotent(
            snapshot_path, status_bytes
        ),
        ARTIFACTS_NAME: atomic_write_idempotent(
            artifacts_path, artifacts_bytes
        ),
        COMPLETION_NAME: atomic_write_idempotent(
            completion_path, completion_bytes
        ),
    }
    return {
        **completion,
        "dry_run": False,
        "outputs_written": True,
        "write_results": write_results,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=str(REPO))
    parser.add_argument("--jobs", default=str(DEFAULT_JOBS))
    parser.add_argument("--status", default=str(DEFAULT_STATUS))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument(
        "--runner-dry-run-attestation-json",
        required=True,
        help=(
            "verbatim JSON emitted by the locked training-image runner "
            "run --dry-run"
        ),
    )
    parser.add_argument(
        "--tools-image-id",
        required=True,
        help="host-inspected immutable ID of the locked archive tools image",
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    repo = Path(args.repo)
    attestation = parse_json_object_text(
        args.runner_dry_run_attestation_json,
        "runner dry-run attestation",
    )
    result = archive_base42(
        repo=repo,
        jobs_path=Path(args.jobs),
        status_path=Path(args.status),
        output_dir=Path(args.output_dir),
        runner_dry_run_attestation=attestation,
        tools_image_id=args.tools_image_id,
        dry_run=args.dry_run,
    )
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
