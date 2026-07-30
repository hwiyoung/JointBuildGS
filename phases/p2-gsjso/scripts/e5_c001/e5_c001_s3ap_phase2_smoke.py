#!/usr/bin/env python3
"""Fail-closed CUDA wiring smokes for the locked S3-A-prime Phase-2 inputs.

This is not an experiment runner.  It copies three committed 30k configs into
an ignored smoke-only root, changing only ``max_iter`` and ``out_dir``.  The
source configs and their prepared payloads are hash-checked before every run.
"""
from __future__ import annotations

import argparse
import copy
import csv
import hashlib
import importlib.util
import json
import math
import os
import shlex
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence

import torch
import yaml
from tensorboard.backend.event_processing.event_accumulator import EventAccumulator


REPO = Path(__file__).resolve().parents[3]
DEFAULT_LOCK = REPO / "phases/p2-gsjso/configs/e5_c001/e5_c001_s3ap_phase2_smoke_lock.json"
SCHEMA = "jointbuildgs.s3ap.phase2.smoke_lock.v1"
MANIFEST_SCHEMA = "jointbuildgs.s3ap.phase2.smoke_manifest.v1"
BINDING_SCHEMA = "jointbuildgs.s3ap.phase2.smoke_binding.v1"
COMPLETE_STATUSES = {"complete", "complete_existing"}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def resolve(path: str | Path) -> Path:
    value = Path(path)
    return value if value.is_absolute() else REPO / value


def relative(path: str | Path) -> str:
    value = resolve(path)
    try:
        return str(value.resolve().relative_to(REPO.resolve()))
    except ValueError:
        return str(value.resolve())


def container_path(path: str | Path, lock: dict[str, Any]) -> str:
    rel = resolve(path).resolve().relative_to(REPO.resolve())
    return str(Path(lock["container_repo_root"]) / rel)


def sha256_file(path: str | Path, block_size: int = 1 << 20) -> str:
    digest = hashlib.sha256()
    with resolve(path).open("rb") as handle:
        for block in iter(lambda: handle.read(block_size), b""):
            digest.update(block)
    return digest.hexdigest()


def atomic_json(path: str | Path, payload: dict[str, Any]) -> None:
    destination = resolve(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.name}.tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, destination)


def atomic_yaml(path: str | Path, payload: dict[str, Any]) -> None:
    destination = resolve(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.name}.tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        yaml.safe_dump(payload, handle, sort_keys=False)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, destination)


def load_python_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot import {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def phase2_runner_module():
    return load_python_module(
        "s3ap_phase2_runner_for_smoke",
        REPO / "phases/p2-gsjso/scripts/e5_c001/e5_c001_s3ap_phase2_runner.py",
    )


def read_csv(path: str | Path) -> list[dict[str, str]]:
    with resolve(path).open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def git_output(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=REPO, text=True).strip()


def load_lock(path: str | Path = DEFAULT_LOCK) -> dict[str, Any]:
    resolved = resolve(path)
    lock = json.loads(resolved.read_text(encoding="utf-8"))
    if lock.get("schema") != SCHEMA:
        raise ValueError("unexpected Phase-2 smoke lock schema")
    if lock.get("building_id") != "8568391":
        raise ValueError("the CUDA smoke target must remain building 8568391")
    smokes = lock.get("smokes") or []
    expected = [("a0", 2, 0, 0), ("a1", 2, 1, 0), ("a2", 702, 0, 1)]
    actual = [
        (str(row.get("arm")), int(row.get("max_iter", -1)),
         int(row.get("gpu_id", -1)), int(row.get("stage", -1)))
        for row in smokes
    ]
    if actual != expected or len({row.get("smoke_id") for row in smokes}) != 3:
        raise ValueError(f"unexpected smoke schedule: {actual}")
    for stage in {int(row["stage"]) for row in smokes}:
        gpu_ids = [int(row["gpu_id"]) for row in smokes if int(row["stage"]) == stage]
        if len(gpu_ids) != len(set(gpu_ids)):
            raise ValueError(f"stage {stage} assigns more than one smoke to a GPU")
    if int(smokes[2].get("expected_first_refine_step", -1)) != 600:
        raise ValueError("pinned gsplat schedule requires first refine/protection step 600")
    if lock["safety"].get("allowed_config_changes") != ["max_iter", "out_dir"]:
        raise ValueError("smoke config mutation contract drift")
    lock["_lock_path"] = relative(resolved)
    lock["_lock_sha256"] = sha256_file(resolved)
    return lock


def is_inside_container() -> bool:
    return Path("/.dockerenv").exists() or bool(os.environ.get("container"))


def validate_runtime_attestation(lock: dict[str, Any]) -> dict[str, Any]:
    if not is_inside_container():
        raise RuntimeError("Phase-2 CUDA smoke must execute inside Docker")
    names = lock["runtime"]["attestation_env"]
    image_id = os.environ.get(names["image_id"], "")
    uid_text = os.environ.get(names["host_uid"], "")
    gid_text = os.environ.get(names["host_gid"], "")
    if image_id != lock["runtime"]["docker_image_id"]:
        raise RuntimeError("locked Docker image ID attestation is absent or mismatched")
    if not uid_text.isdigit() or not gid_text.isdigit():
        raise RuntimeError("host UID/GID attestation is absent")
    if (os.getuid(), os.getgid()) != (int(uid_text), int(gid_text)):
        raise RuntimeError(
            f"--user mapping mismatch: container={os.getuid()}:{os.getgid()} "
            f"host={uid_text}:{gid_text}"
        )
    cache_env = lock["runtime"].get("writable_cache_env") or {}
    if set(cache_env) != {"HOME", "XDG_CACHE_HOME", "TORCH_EXTENSIONS_DIR"}:
        raise RuntimeError("writable cache environment lock is incomplete")
    cache_audit: dict[str, dict[str, Any]] = {}
    for name, expected in cache_env.items():
        actual = os.environ.get(name)
        if actual != expected:
            raise RuntimeError(f"{name} cache attestation mismatch: {actual!r} != {expected!r}")
        path = Path(actual)
        if not path.is_dir() or not os.access(path, os.W_OK | os.X_OK):
            raise RuntimeError(f"{name} cache path is not a writable directory: {path}")
        cache_audit[name] = {"path": str(path), "writable": True}
    return {
        "docker_image": lock["runtime"]["docker_image"],
        "docker_image_id": image_id,
        "container_uid": os.getuid(),
        "container_gid": os.getgid(),
        "host_uid": int(uid_text),
        "host_gid": int(gid_text),
        "user_mapping_exact": True,
        "writable_cache_env": cache_audit,
    }


def require_hash(path: str | Path, expected: str, role: str) -> str:
    actual = sha256_file(path)
    if actual != expected:
        raise RuntimeError(f"{role} hash drift: {actual} != {expected}")
    return actual


def validate_source_contract(lock: dict[str, Any]) -> dict[str, Any]:
    """Validate the committed 30k configs plus every prepared input hash."""

    source = lock["source_contract"]
    require_hash(source["phase2_lock"], source["phase2_lock_sha256"], "Phase-2 lock")
    require_hash(source["prepare_manifest"], source["prepare_manifest_sha256"], "prepare manifest")
    require_hash(source["base_inventory"], source["base_inventory_sha256"], "base inventory")
    require_hash(
        source["prepared_data_manifest"],
        source["prepared_data_manifest_sha256"],
        "prepared data manifest",
    )
    git_output("cat-file", "-e", f"{source['phase2_implementation_commit']}^{{commit}}")

    runner = phase2_runner_module()
    phase2_lock = runner.load_lock(source["phase2_lock"])
    if phase2_lock["runtime"]["docker_image_id"] != lock["runtime"]["docker_image_id"]:
        raise RuntimeError("smoke and Phase-2 locks disagree on Docker image ID")
    jobs = read_csv(source["base_inventory"])
    prepare_manifest = runner.validate_inventory_contract(
        resolve(source["base_inventory"]), jobs, phase2_lock
    )
    if prepare_manifest.get("git_head") != source["phase2_implementation_commit"]:
        raise RuntimeError("prepare manifest implementation commit drift")
    if any(prepare_manifest.get(key) is not False for key in ("gt_used", "lod2_used", "als_used")):
        raise RuntimeError("prepare manifest truth-input declaration drift")

    by_id = {row["job_id"]: row for row in jobs}
    payload_cache: dict[str, dict[str, Any]] = {}
    selected: dict[str, Any] = {}
    for smoke in lock["smokes"]:
        source_job = by_id.get(smoke["source_job_id"])
        if source_job is None:
            raise RuntimeError(f"source job absent from locked inventory: {smoke['source_job_id']}")
        expected_fields = {
            "building_id": lock["building_id"],
            "arm": smoke["arm"],
            "replicate": source["required_replicate"],
            "job_class": source["required_job_class"],
            "iterations": str(source["required_source_iterations"]),
            "gt_used": "False",
            "lod2_used": "False",
            "als_used": "False",
        }
        if any(source_job.get(key) != value for key, value in expected_fields.items()):
            raise RuntimeError(f"source inventory row contract drift: {smoke['source_job_id']}")
        if source_job["config_path"] != smoke["source_config"]:
            raise RuntimeError("source config path differs from the smoke lock")
        if source_job["config_sha256"] != smoke["source_config_sha256"]:
            raise RuntimeError("source config hash differs from the smoke lock")
        require_hash(smoke["source_config"], smoke["source_config_sha256"], "source config")
        config = yaml.safe_load(resolve(smoke["source_config"]).read_text(encoding="utf-8"))
        if int(config.get("max_iter", -1)) != source["required_source_iterations"]:
            raise RuntimeError("source config is not the locked 30k config")
        if config.get("out_dir") != container_path(source_job["out_dir"], lock):
            raise RuntimeError("source config out_dir differs from the 30k inventory")
        if config.get("init_pointcloud") or config.get("init_pointcloud_mode"):
            raise RuntimeError("smoke source unexpectedly enables MVS initialization")
        truth = config.get("phase2_input_contract") or {}
        if any(truth.get(key) is not False for key in ("gt_used", "lod2_used", "als_used")):
            raise RuntimeError("source config truth-input declaration drift")
        payload = runner.validate_prepared_payload(
            source_job, config, phase2_lock, prepare_manifest, payload_cache
        )
        selected[smoke["smoke_id"]] = {
            "source_job": source_job,
            "source_config": config,
            "payload_audit": payload,
        }
    return {
        "phase2_lock": phase2_lock,
        "prepare_manifest_sha256": prepare_manifest["_manifest_sha256"],
        "inventory_sha256": sha256_file(source["base_inventory"]),
        "prepared_data_manifest_sha256": sha256_file(source["prepared_data_manifest"]),
        "selected": selected,
    }


def validate_gsplat_prewarm(lock: dict[str, Any]) -> dict[str, Any]:
    phase2_lock_path = resolve(lock["source_contract"]["phase2_lock"])
    phase2_lock = json.loads(phase2_lock_path.read_text(encoding="utf-8"))
    contract = phase2_lock["runtime"].get("gsplat_prewarm") or {}
    if contract.get("script") != lock["runtime"]["gsplat_prewarm"]["script"]:
        raise RuntimeError("smoke/main gsplat prewarm script contract drift")
    manifest_path = resolve(contract.get("manifest", ""))
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    if payload.get("schema") != "jointbuildgs.s3ap.phase2.gsplat_prewarm.v1":
        raise RuntimeError("unexpected gsplat prewarm manifest schema")
    if payload.get("status") != "complete":
        raise RuntimeError("gsplat prewarm did not complete")
    if payload.get("lock_sha256") != sha256_file(phase2_lock_path):
        raise RuntimeError("gsplat prewarm main-lock hash drift")
    script_path = resolve(contract["script"])
    if payload.get("script_sha256") != sha256_file(script_path):
        raise RuntimeError("gsplat prewarm script hash drift")
    extension_path = Path(payload.get("extension_path", ""))
    if not extension_path.is_file() or payload.get("extension_sha256") != sha256_file(extension_path):
        raise RuntimeError("gsplat prewarm extension file/hash drift")
    return {
        "manifest": relative(manifest_path),
        "manifest_sha256": sha256_file(manifest_path),
        "extension_path": str(extension_path),
        "extension_sha256": payload["extension_sha256"],
        "elapsed_s": payload.get("elapsed_s"),
    }


def derive_smoke_config(
    source_config: dict[str, Any], smoke: dict[str, Any], lock: dict[str, Any]
) -> tuple[dict[str, Any], Path]:
    config = copy.deepcopy(source_config)
    output_dir = resolve(lock["outputs"]["run_dir"]) / smoke["smoke_id"]
    config["max_iter"] = int(smoke["max_iter"])
    config["out_dir"] = container_path(output_dir, lock)
    untouched_source = {key: value for key, value in source_config.items() if key not in {"max_iter", "out_dir"}}
    untouched_smoke = {key: value for key, value in config.items() if key not in {"max_iter", "out_dir"}}
    if untouched_source != untouched_smoke:
        raise RuntimeError("derived smoke config changed a key outside max_iter/out_dir")
    main_root = resolve(lock["safety"]["main_training_root_forbidden"])
    if output_dir.resolve() == main_root.resolve() or main_root.resolve() in output_dir.resolve().parents:
        raise RuntimeError("smoke output resolves under the main Phase-2 training root")
    smoke_root = resolve(lock["outputs"]["root"])
    if output_dir.resolve() != smoke_root.resolve() and smoke_root.resolve() not in output_dir.resolve().parents:
        raise RuntimeError("smoke output escapes the locked smoke root")
    return config, output_dir


def materialize_command(template: Sequence[str], config_path: Path) -> list[str]:
    resolved_config = str(config_path.resolve())
    command = [str(token).replace("{config}", resolved_config) for token in template]
    if resolved_config not in command:
        raise RuntimeError("training command does not contain the generated smoke config")
    return command


def prepare_manifest(
    lock: dict[str, Any], runtime: dict[str, Any], source_audit: dict[str, Any]
) -> dict[str, Any]:
    records: list[dict[str, Any]] = []
    for smoke in lock["smokes"]:
        selected = source_audit["selected"][smoke["smoke_id"]]
        config, output_dir = derive_smoke_config(selected["source_config"], smoke, lock)
        config_path = resolve(lock["outputs"]["config_dir"]) / f"{smoke['smoke_id']}.yaml"
        if config_path.exists():
            existing = yaml.safe_load(config_path.read_text(encoding="utf-8"))
            if existing != config:
                raise RuntimeError(f"existing generated smoke config drift: {config_path}")
        else:
            atomic_yaml(config_path, config)
        config_hash = sha256_file(config_path)
        records.append({
            "sequence": int(smoke["sequence"]),
            "stage": int(smoke["stage"]),
            "smoke_id": smoke["smoke_id"],
            "arm": smoke["arm"],
            "gpu_id": int(smoke["gpu_id"]),
            "max_iter": int(smoke["max_iter"]),
            "timeout_s": int(smoke["timeout_s"]),
            "source_job_id": smoke["source_job_id"],
            "source_config": smoke["source_config"],
            "source_config_sha256": smoke["source_config_sha256"],
            "generated_config": relative(config_path),
            "generated_config_sha256": config_hash,
            "data_manifest_sha256": selected["payload_audit"]["data_manifest_sha256"],
            "surface_seed_sha256": selected["payload_audit"]["surface_seed_sha256"],
            "output_dir": relative(output_dir),
            "status": "prepared",
            "started_utc": None,
            "ended_utc": None,
            "elapsed_s": None,
            "returncode": None,
            "log": relative(resolve(lock["outputs"]["log_dir"]) / f"{smoke['smoke_id']}.log"),
            "message": "",
            "audit_summary": None,
        })
    manifest_path = resolve(lock["outputs"]["manifest"])
    if manifest_path.exists():
        existing = json.loads(manifest_path.read_text(encoding="utf-8"))
        if (
            existing.get("schema") != MANIFEST_SCHEMA
            or existing.get("smoke_lock_sha256") != lock["_lock_sha256"]
            or [row.get("generated_config_sha256") for row in existing.get("smokes", [])]
            != [row["generated_config_sha256"] for row in records]
        ):
            raise RuntimeError("existing smoke manifest is not bound to this lock/config set")
        return existing
    manifest = {
        "schema": MANIFEST_SCHEMA,
        "purpose": lock["purpose"],
        "created_utc": utc_now(),
        "updated_utc": utc_now(),
        "status": "prepared",
        "training_started": False,
        "counts_as_phase2_training_run": False,
        "gt_used": False,
        "lod2_used": False,
        "als_used": False,
        "git_head_at_prepare": git_output("rev-parse", "HEAD"),
        "git_branch_at_prepare": git_output("branch", "--show-current"),
        "smoke_lock": lock["_lock_path"],
        "smoke_lock_sha256": lock["_lock_sha256"],
        "phase2_implementation_commit": lock["source_contract"]["phase2_implementation_commit"],
        "phase2_lock_sha256": lock["source_contract"]["phase2_lock_sha256"],
        "prepare_manifest_sha256": source_audit["prepare_manifest_sha256"],
        "base_inventory_sha256": source_audit["inventory_sha256"],
        "prepared_data_manifest_sha256": source_audit["prepared_data_manifest_sha256"],
        "runtime_attestation": runtime,
        "allowed_source_config_changes": ["max_iter", "out_dir"],
        "smokes": records,
    }
    atomic_json(manifest_path, manifest)
    return manifest


def scalar_events(output_dir: Path) -> tuple[dict[str, list[dict[str, Any]]], list[dict[str, str]]]:
    event_files = sorted((output_dir / "tb").glob("events.out.tfevents*"))
    if not event_files:
        raise RuntimeError("TensorBoard event file is absent")
    accumulator = EventAccumulator(str(output_dir / "tb"), size_guidance={"scalars": 0})
    accumulator.Reload()
    scalars: dict[str, list[dict[str, Any]]] = {}
    for tag in accumulator.Tags().get("scalars", []):
        scalars[tag] = [
            {"step": int(event.step), "value": float(event.value)}
            for event in accumulator.Scalars(tag)
        ]
    files = [{"path": relative(path), "sha256": sha256_file(path)} for path in event_files]
    return scalars, files


def require_finite_scalars(
    scalars: dict[str, list[dict[str, Any]]], tags: Iterable[str]
) -> dict[str, list[dict[str, Any]]]:
    selected: dict[str, list[dict[str, Any]]] = {}
    for tag in tags:
        rows = scalars.get(tag) or []
        if not rows or any(not math.isfinite(float(row["value"])) for row in rows):
            raise RuntimeError(f"missing or non-finite TensorBoard scalar: {tag}")
        selected[tag] = rows
    return selected


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if line.strip():
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError as error:
                    raise RuntimeError(f"invalid JSONL line {line_number}: {path}") from error
    return rows


def summarize_output(
    record: dict[str, Any], smoke: dict[str, Any], lock: dict[str, Any]
) -> dict[str, Any]:
    output_dir = resolve(record["output_dir"])
    config_path = resolve(record["generated_config"])
    require_hash(smoke["source_config"], smoke["source_config_sha256"], "source config post-run")
    require_hash(config_path, record["generated_config_sha256"], "generated smoke config")
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if int(config.get("max_iter", -1)) != int(smoke["max_iter"]):
        raise RuntimeError("generated smoke iteration drift")
    if config.get("out_dir") != container_path(output_dir, lock):
        raise RuntimeError("generated smoke output path drift")

    binding_path = output_dir / "smoke_binding.json"
    binding = json.loads(binding_path.read_text(encoding="utf-8"))
    if (
        binding.get("schema") != BINDING_SCHEMA
        or binding.get("smoke_id") != smoke["smoke_id"]
        or binding.get("generated_config_sha256") != record["generated_config_sha256"]
        or binding.get("source_config_sha256") != smoke["source_config_sha256"]
    ):
        raise RuntimeError("smoke binding drift")

    checkpoint_path = output_dir / "ckpt/final.pt"
    payload = torch.load(checkpoint_path, map_location="cpu", weights_only=False)
    if not isinstance(payload, dict) or not isinstance(payload.get("state_dict"), dict):
        raise RuntimeError("invalid final checkpoint dictionary")
    checkpoint_it = int(payload.get("it", -1))
    n_prim = int(payload.get("n_prim", -1))
    if checkpoint_it != int(smoke["max_iter"]) or n_prim <= 0:
        raise RuntimeError(f"checkpoint contract drift: it={checkpoint_it} n_prim={n_prim}")
    lineage = payload.get("surface_seed_lineage_mask")
    if not torch.is_tensor(lineage) or lineage.numel() != n_prim:
        raise RuntimeError("checkpoint surface-seed lineage is absent or misaligned")
    lineage_bool = lineage.to(dtype=torch.bool).flatten()
    lineage_count = int(lineage_bool.sum().item())
    if lineage_count <= 0 or int(payload.get("surface_seed_lineage_count", -1)) != lineage_count:
        raise RuntimeError("checkpoint surface-seed lineage count drift")

    effective_path = output_dir / "effective_config.json"
    seed_audit_path = output_dir / "surface_seed_audit.json"
    effective = json.loads(effective_path.read_text(encoding="utf-8"))
    seed_audit = json.loads(seed_audit_path.read_text(encoding="utf-8"))
    if seed_audit.get("sha256") != record["surface_seed_sha256"]:
        raise RuntimeError("training surface-seed audit hash drift")
    if int(seed_audit.get("n_surface_seed", 0)) <= 0 or float(seed_audit.get("init_opacity", -1)) != 0.1:
        raise RuntimeError("surface seed count/opacity audit drift")
    if bool(effective.get("surface_seed_protect")) != (smoke["arm"] == "a2"):
        raise RuntimeError("effective surface-seed protection arm drift")
    if effective.get("surface_seed", {}).get("sha256") != record["surface_seed_sha256"]:
        raise RuntimeError("effective config surface-seed lineage hash drift")

    scalars, event_files = scalar_events(output_dir)
    scalar_summary = require_finite_scalars(scalars, ["loss/total"])
    mono_summary: dict[str, Any] | None = None
    refine_summary: dict[str, Any] | None = None
    if smoke["arm"] in {"a1", "a2"}:
        scalar_summary.update(require_finite_scalars(scalars, ["loss/normal", "loss/mono_depth"]))
        mono_path = output_dir / "audit/mono_target_regions.jsonl"
        rows = load_jsonl(mono_path)
        if not rows:
            raise RuntimeError("mono-target audit is empty")
        eligible = [
            row for row in rows
            if int((row.get("mono_depth") or {}).get("eligible_region_count", 0)) > 0
            and int((row.get("mono_normal") or {}).get("eligible_region_count", 0)) > 0
        ]
        if not eligible or any(lock["building_id"] not in row.get("target_buildings", []) for row in eligible):
            raise RuntimeError("mono-target audit has no jointly eligible target observation")
        mono_summary = {
            "path": relative(mono_path),
            "sha256": sha256_file(mono_path),
            "row_count": len(rows),
            "jointly_eligible_row_count": len(eligible),
            "steps": sorted({int(row["step"]) for row in rows}),
            "views": sorted({str(row["view"]) for row in rows}),
        }
    if smoke["arm"] == "a2":
        expected_step = int(smoke["expected_first_refine_step"])
        required = require_finite_scalars(
            scalars,
            [
                "stats/seed_protect_active",
                "stats/seed_protected_count",
                "stats/prune_candidates",
                "stats/prune_seed_protected",
                "stats/pruned",
                "stats/effective_prune_opa",
            ],
        )
        scalar_summary.update(required)
        active = {int(row["step"]): float(row["value"]) for row in required["stats/seed_protect_active"]}
        protected = {int(row["step"]): float(row["value"]) for row in required["stats/seed_protected_count"]}
        prune_opa = {int(row["step"]): float(row["value"]) for row in required["stats/effective_prune_opa"]}
        earlier_active = [value for step, value in active.items() if step < expected_step]
        if (
            not earlier_active
            or any(value != 0.0 for value in earlier_active)
            or active.get(expected_step) != 1.0
            or protected.get(expected_step, 0.0) <= 0.0
            or not math.isclose(prune_opa.get(expected_step, math.nan), 0.05, abs_tol=1e-7)
        ):
            raise RuntimeError("first refine/surface-protection transition was not observed at step 600")
        if (
            effective.get("seed_protect_until_iter") != 10000
            or effective.get("surface_seed_prune_opa_initial") != 0.05
            or effective.get("surface_seed_prune_opa_final") != 0.01
            or effective.get("surface_seed_prune_switch_iter") != 10000
        ):
            raise RuntimeError("effective A2 protection schedule drift")
        refine_summary = {
            "expected_first_refine_step": expected_step,
            "observed_seed_protect_transition_step": expected_step,
            "seed_protected_count": int(protected[expected_step]),
            "prune_candidates": int(next(
                row["value"] for row in required["stats/prune_candidates"]
                if int(row["step"]) == expected_step
            )),
            "prune_seed_protected": int(next(
                row["value"] for row in required["stats/prune_seed_protected"]
                if int(row["step"]) == expected_step
            )),
            "pruned": int(next(
                row["value"] for row in required["stats/pruned"]
                if int(row["step"]) == expected_step
            )),
            "effective_prune_opa": prune_opa[expected_step],
        }

    return {
        "checkpoint": {
            "path": relative(checkpoint_path),
            "sha256": sha256_file(checkpoint_path),
            "it": checkpoint_it,
            "n_prim": n_prim,
        },
        "surface_seed_lineage": {
            "source_npz_sha256": record["surface_seed_sha256"],
            "initial_count": int(seed_audit["n_surface_seed"]),
            "final_lineage_count": lineage_count,
        },
        "effective_config": {
            "path": relative(effective_path),
            "sha256": sha256_file(effective_path),
            "surface_seed_protect": bool(effective.get("surface_seed_protect")),
            "mono_normal_loss": effective.get("mono_normal_loss"),
            "mono_depth_loss": effective.get("mono_depth_loss"),
        },
        "surface_seed_audit": {
            "path": relative(seed_audit_path),
            "sha256": sha256_file(seed_audit_path),
        },
        "tensorboard_event_files": event_files,
        "finite_scalar_summary": scalar_summary,
        "mono_target_audit": mono_summary,
        "refine_protection_event": refine_summary,
        "smoke_binding": {"path": relative(binding_path), "sha256": sha256_file(binding_path)},
    }


def write_binding(record: dict[str, Any], smoke: dict[str, Any], lock: dict[str, Any]) -> None:
    output_dir = resolve(record["output_dir"])
    output_dir.mkdir(parents=True, exist_ok=False)
    atomic_json(output_dir / "smoke_binding.json", {
        "schema": BINDING_SCHEMA,
        "purpose": lock["purpose"],
        "counts_as_phase2_training_run": False,
        "smoke_id": smoke["smoke_id"],
        "source_job_id": smoke["source_job_id"],
        "source_config": smoke["source_config"],
        "source_config_sha256": smoke["source_config_sha256"],
        "generated_config": record["generated_config"],
        "generated_config_sha256": record["generated_config_sha256"],
        "surface_seed_sha256": record["surface_seed_sha256"],
        "max_iter": int(smoke["max_iter"]),
        "gpu_id": int(smoke["gpu_id"]),
        "gt_used": False,
        "lod2_used": False,
        "als_used": False,
    })


def run_one_job(record: dict[str, Any], smoke: dict[str, Any], lock: dict[str, Any]) -> dict[str, Any]:
    started = time.monotonic()
    output_dir = resolve(record["output_dir"])
    log_path = resolve(record["log"])
    result = copy.deepcopy(record)
    result.update({"started_utc": utc_now(), "status": "running", "message": ""})
    try:
        require_hash(smoke["source_config"], smoke["source_config_sha256"], "source config pre-run")
        require_hash(record["generated_config"], record["generated_config_sha256"], "generated config pre-run")
        if output_dir.exists():
            if (output_dir / "ckpt/final.pt").is_file():
                result["audit_summary"] = summarize_output(result, smoke, lock)
                result["status"] = "complete_existing"
                result["message"] = "validated pre-existing smoke checkpoint; no training started"
                result["returncode"] = 0
                return result
            result["status"] = "blocked_partial_exists"
            result["message"] = "smoke output exists without a valid final checkpoint; no overwrite"
            return result
        write_binding(result, smoke, lock)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        command = materialize_command(lock["runtime"]["training_command"], resolve(record["generated_config"]))
        environment = os.environ.copy()
        environment["CUDA_VISIBLE_DEVICES"] = str(smoke["gpu_id"])
        with log_path.open("x", encoding="utf-8") as log:
            log.write(f"{utc_now()} gpu={smoke['gpu_id']} command={shlex.join(command)}\n")
            log.flush()
            process = subprocess.run(
                command,
                cwd=REPO,
                env=environment,
                stdout=log,
                stderr=subprocess.STDOUT,
                text=True,
                timeout=int(smoke["timeout_s"]),
                check=False,
            )
        result["returncode"] = int(process.returncode)
        if process.returncode != 0:
            result["status"] = "failed"
            result["message"] = f"training returncode={process.returncode}"
        else:
            result["audit_summary"] = summarize_output(result, smoke, lock)
            result["status"] = "complete"
    except subprocess.TimeoutExpired:
        result["status"] = "timeout"
        result["message"] = f"elapsed exceeded timeout_s={smoke['timeout_s']}"
    except Exception as error:  # noqa: BLE001 - each failure is recorded and the schedule continues
        result["status"] = "runner_error"
        result["message"] = f"{type(error).__name__}: {error}"
    finally:
        result["ended_utc"] = utc_now()
        result["elapsed_s"] = round(time.monotonic() - started, 3)
        if log_path.is_file():
            result["log_sha256"] = sha256_file(log_path)
    return result


def run_schedule(
    manifest: dict[str, Any],
    lock: dict[str, Any],
    *,
    execute: Callable[[dict[str, Any], dict[str, Any], dict[str, Any]], dict[str, Any]] = run_one_job,
    persist: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    smoke_by_id = {row["smoke_id"]: row for row in lock["smokes"]}
    records = {row["smoke_id"]: copy.deepcopy(row) for row in manifest["smokes"]}
    persistence_lock = threading.Lock()

    def save() -> None:
        with persistence_lock:
            manifest["smokes"] = sorted(records.values(), key=lambda row: int(row["sequence"]))
            manifest["updated_utc"] = utc_now()
            manifest["training_started"] = any(
                row["status"] not in {"prepared", "complete_existing", "blocked_partial_exists"}
                for row in manifest["smokes"]
            )
            statuses = [row["status"] for row in manifest["smokes"]]
            manifest["status"] = (
                "complete" if statuses and all(status in COMPLETE_STATUSES for status in statuses)
                else "running" if any(status == "running" for status in statuses)
                else "partial"
            )
            if persist is not None:
                persist(manifest)

    for stage in sorted({int(row["stage"]) for row in lock["smokes"]}):
        stage_smokes = [row for row in lock["smokes"] if int(row["stage"]) == stage]
        with ThreadPoolExecutor(max_workers=len(stage_smokes), thread_name_prefix=f"smoke-stage-{stage}") as pool:
            futures = {}
            for smoke in stage_smokes:
                record = records[smoke["smoke_id"]]
                record["status"] = "running"
                records[smoke["smoke_id"]] = record
                futures[pool.submit(execute, copy.deepcopy(record), smoke, lock)] = smoke["smoke_id"]
            save()
            for future in as_completed(futures):
                smoke_id = futures[future]
                try:
                    records[smoke_id] = future.result()
                except Exception as error:  # defensive: executor bugs also cannot hang the schedule
                    failed = records[smoke_id]
                    failed.update({
                        "status": "runner_error",
                        "ended_utc": utc_now(),
                        "message": f"{type(error).__name__}: {error}",
                    })
                    records[smoke_id] = failed
                save()
    save()
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lock", default=str(DEFAULT_LOCK))
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    lock = load_lock(args.lock)
    runtime = validate_runtime_attestation(lock)
    source_audit = validate_source_contract(lock)
    manifest = prepare_manifest(lock, runtime, source_audit)
    if args.prepare_only or args.dry_run:
        print(json.dumps({
            "manifest": relative(lock["outputs"]["manifest"]),
            "smokes": len(manifest["smokes"]),
            "schedule": [
                {key: row[key] for key in ("smoke_id", "stage", "gpu_id", "max_iter")}
                for row in manifest["smokes"]
            ],
            "training_started": False,
            "counts_as_phase2_training_run": False,
            "runtime_attestation": runtime,
        }, sort_keys=True))
        return
    manifest["gsplat_prewarm"] = validate_gsplat_prewarm(lock)
    atomic_json(lock["outputs"]["manifest"], manifest)
    manifest["git_head_at_run"] = git_output("rev-parse", "HEAD")
    manifest = run_schedule(
        manifest,
        lock,
        persist=lambda payload: atomic_json(lock["outputs"]["manifest"], payload),
    )
    print(json.dumps({
        "manifest": relative(lock["outputs"]["manifest"]),
        "status": manifest["status"],
        "status_counts": {
            status: sum(row["status"] == status for row in manifest["smokes"])
            for status in sorted({row["status"] for row in manifest["smokes"]})
        },
        "counts_as_phase2_training_run": False,
    }, sort_keys=True))


if __name__ == "__main__":
    main()
