#!/usr/bin/env python3
"""Run a prepared S3-A-prime inventory with one job per GPU and atomic status.

The runner must itself execute inside the locked Docker image.  It does not
attempt approximate checkpoint resume: final.pt is complete and skipped, while
any partial checkpoint is marked blocked_resume_unsupported and other jobs
continue.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import queue
import shlex
import subprocess
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

import yaml
import torch


REPO = Path(__file__).resolve().parents[3]
DEFAULT_LOCK = REPO / "phases/p2-gsjso/configs/e5_c001/e5_c001_s3ap_phase2_lock.json"
STATUS_FIELDS = [
    "sequence", "job_id", "gpu_id", "status", "attempt", "config_path", "config_sha256",
    "out_dir", "final_checkpoint", "partial_checkpoints", "started_utc", "ended_utc",
    "elapsed_s", "timeout_s", "returncode", "log_path",
    "prepare_manifest_sha256", "data_manifest_sha256", "surface_seed_sha256",
    "job_binding_sha256",
    "final_checkpoint_sha256", "final_checkpoint_it", "final_checkpoint_n_prim",
    "message",
]


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


def sha256_file(path: str | Path, block_size: int = 1 << 20) -> str:
    digest = hashlib.sha256()
    with resolve(path).open("rb") as handle:
        for block in iter(lambda: handle.read(block_size), b""):
            digest.update(block)
    return digest.hexdigest()


def atomic_csv(path: Path, rows: Sequence[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    with temporary.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=STATUS_FIELDS, extrasaction="ignore", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def load_lock(path: str | Path) -> dict[str, Any]:
    resolved_path = resolve(path)
    lock = json.loads(resolved_path.read_text(encoding="utf-8"))
    if lock.get("schema") != "jointbuildgs.s3ap.phase2.lock.v1":
        raise ValueError("unexpected Phase-2 lock schema")
    runtime = lock["runtime"]
    if int(runtime.get("jobs_per_gpu", 0)) != 1 or len(runtime.get("gpu_ids", [])) != 2:
        raise ValueError("runner lock requires exactly one job on each of two GPUs")
    lock["_lock_path"] = relative(resolved_path)
    lock["_lock_sha256"] = sha256_file(resolved_path)
    return lock


def is_inside_container() -> bool:
    return Path("/.dockerenv").exists() or bool(os.environ.get("container"))


def validate_runtime_attestation(lock: dict[str, Any]) -> dict[str, Any]:
    if not is_inside_container():
        raise RuntimeError("Phase-2 runner must execute inside Docker")
    names = lock["runtime"]["attestation_env"]
    image_id = os.environ.get(names["image_id"], "")
    uid_text = os.environ.get(names["host_uid"], "")
    gid_text = os.environ.get(names["host_gid"], "")
    if image_id != lock["runtime"]["docker_image_id"]:
        raise RuntimeError("locked Docker image ID attestation is absent or mismatched")
    if not uid_text.isdigit() or not gid_text.isdigit():
        raise RuntimeError("host UID/GID attestation is absent")
    if os.getuid() != int(uid_text) or os.getgid() != int(gid_text):
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
        "docker_image_id": image_id,
        "container_uid": os.getuid(), "container_gid": os.getgid(),
        "host_uid": int(uid_text), "host_gid": int(gid_text),
        "writable_cache_env": cache_audit,
    }


def checkpoint_state(
    out_dir: str | Path,
    expected_iterations: int = 30000,
    *,
    expected_job_id: str | None = None,
    expected_config_sha256: str | None = None,
) -> dict[str, Any]:
    out = resolve(out_dir)
    final = out / "ckpt/final.pt"
    binding = out / "phase2_job_binding.json"
    partial = sorted(
        path for path in (out / "ckpt").glob("*.pt")
        if path.name != "final.pt" and path.is_file() and path.stat().st_size > 0
    ) if (out / "ckpt").is_dir() else []
    final_hash = ""
    final_it: int | str = ""
    final_n_prim: int | str = ""
    binding_hash = sha256_file(binding) if binding.is_file() else ""
    message = ""
    if final.is_file() and final.stat().st_size > 0:
        final_hash = sha256_file(final)
        try:
            payload = torch.load(final, map_location="cpu", weights_only=False)
            if not isinstance(payload, dict):
                raise ValueError("checkpoint payload is not a dictionary")
            final_it = int(payload.get("it", -1))
            final_n_prim = int(payload.get("n_prim", -1))
            if final_it != int(expected_iterations):
                raise ValueError(f"checkpoint it={final_it}, expected={expected_iterations}")
            if final_n_prim <= 0 or not isinstance(payload.get("state_dict"), dict):
                raise ValueError("checkpoint lacks a positive n_prim or state_dict")
            if expected_job_id is not None or expected_config_sha256 is not None:
                if not binding.is_file():
                    raise ValueError("checkpoint lacks phase2_job_binding.json")
                binding_payload = json.loads(binding.read_text(encoding="utf-8"))
                if binding_payload.get("schema") != "jointbuildgs.s3ap.phase2.job_binding.v1":
                    raise ValueError("unexpected Phase-2 job binding schema")
                if (
                    expected_job_id is not None
                    and binding_payload.get("job_id") != expected_job_id
                ):
                    raise ValueError("checkpoint job binding job_id mismatch")
                if (
                    expected_config_sha256 is not None
                    and binding_payload.get("config_sha256") != expected_config_sha256
                ):
                    raise ValueError("checkpoint job binding config_sha256 mismatch")
            status = "skipped_final_exists"
        except Exception as error:  # noqa: BLE001
            status = "invalid_final_checkpoint"
            message = f"{type(error).__name__}: {error}"
    elif partial:
        status = "blocked_resume_unsupported"
    else:
        status = "pending"
    return {
        "status": status,
        "final_checkpoint": relative(final),
        "partial_checkpoints": [relative(path) for path in partial],
        "final_checkpoint_sha256": final_hash,
        "final_checkpoint_it": final_it,
        "final_checkpoint_n_prim": final_n_prim,
        "job_binding": relative(binding),
        "job_binding_sha256": binding_hash,
        "message": message,
    }


def write_job_binding(job: dict[str, str]) -> dict[str, Any]:
    binding_path = resolve(job["out_dir"]) / "phase2_job_binding.json"
    payload = {
        "schema": "jointbuildgs.s3ap.phase2.job_binding.v1",
        "job_id": job["job_id"],
        "config_path": relative(job["config_path"]),
        "config_sha256": job["config_sha256"],
        "data_root": job.get("data_root", ""),
        "surface_seed_npz": job.get("surface_seed_npz", ""),
        "surface_seed_sha256": job.get("surface_seed_sha256", ""),
        "iterations": int(job["iterations"]),
    }
    atomic_json(binding_path, payload)
    return {
        "path": relative(binding_path),
        "sha256": sha256_file(binding_path),
        "payload": payload,
    }


def materialize_command(template: Sequence[str], config_path: str | Path) -> list[str]:
    config = str(resolve(config_path))
    command = [str(token).replace("{config}", config) for token in template]
    if not any(config == token for token in command):
        raise ValueError("training command does not contain the materialized config path")
    return command


def container_repo_path(value: str | Path, lock: dict[str, Any]) -> Path:
    path = Path(value)
    root = Path(lock["container_repo_root"])
    try:
        relative_path = path.relative_to(root)
    except ValueError as error:
        raise ValueError(f"container path is outside the locked repo mount: {path}") from error
    return resolve(relative_path)


def validate_inventory_contract(
    inventory_path: Path,
    jobs: list[dict[str, str]],
    lock: dict[str, Any],
) -> dict[str, Any]:
    inventory_path = resolve(inventory_path)
    if inventory_path == resolve(lock["outputs"]["base_inventory"]):
        manifest_path = resolve(lock["outputs"]["prepare_manifest"])
        expected_count = 42
        expected_mode = "base"
    elif inventory_path == resolve(lock["outputs"]["tilt_inventory"]):
        manifest_path = resolve(lock["outputs"]["tilt_prepare_manifest"])
        expected_count = 18
        expected_mode = "tilt"
    else:
        raise RuntimeError("runner inventory is not one of the locked base/tilt inventories")
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    if payload.get("status") != "complete" or payload.get("mode") != expected_mode:
        raise RuntimeError("prepare manifest is not complete for the requested inventory")
    if payload.get("training_started") is not False:
        raise RuntimeError("prepare manifest training_started must be false")
    if payload.get("lock_path") != lock["_lock_path"] or payload.get("lock_sha256") != lock["_lock_sha256"]:
        raise RuntimeError("prepare manifest lock path/hash differs from the runner lock")
    attestation = payload.get("runtime_attestation") or {}
    if attestation.get("docker_image_id") != lock["runtime"]["docker_image_id"]:
        raise RuntimeError("prepare manifest Docker image attestation drift")
    if len(jobs) != expected_count or int(payload.get("job_count", -1)) != expected_count:
        raise RuntimeError(
            f"inventory count mismatch: csv={len(jobs)} manifest={payload.get('job_count')} expected={expected_count}"
        )
    actual_hash = sha256_file(inventory_path)
    if payload.get("inventory") != relative(inventory_path) or payload.get("inventory_sha256") != actual_hash:
        raise RuntimeError("inventory path/hash differs from the prepare manifest")
    manifest_jobs = payload.get("jobs") or []
    csv_ids = [row["job_id"] for row in jobs]
    manifest_ids = [row.get("job_id") for row in manifest_jobs]
    if csv_ids != manifest_ids or len(set(csv_ids)) != expected_count:
        raise RuntimeError("inventory job IDs/order differ from the prepare manifest")
    payload["_manifest_path"] = relative(manifest_path)
    payload["_manifest_sha256"] = sha256_file(manifest_path)
    return payload


def validate_prepared_payload(
    job: dict[str, str],
    config: dict[str, Any],
    lock: dict[str, Any],
    input_contract: dict[str, Any],
    cache: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    building = str(job["building_id"])
    prepared = (input_contract.get("prepared_buildings") or {}).get(building)
    if not isinstance(prepared, dict):
        raise ValueError(f"prepare manifest misses building {building}")
    data_root = resolve(job["data_root"])
    if container_repo_path(config["data_root"], lock) != data_root:
        raise ValueError("config data_root differs from jobs.csv")
    if resolve(prepared.get("data_root", "")) != data_root:
        raise ValueError("jobs.csv data_root differs from prepare manifest")

    cache_key = str(data_root.resolve())
    if cache_key not in cache:
        data_manifest_path = data_root / "data_manifest.json"
        expected_manifest_path = resolve(prepared["data_manifest"])
        if data_manifest_path.resolve() != expected_manifest_path.resolve():
            raise ValueError("prepared data_manifest path drift")
        data_manifest_hash = sha256_file(data_manifest_path)
        if data_manifest_hash != prepared["data_manifest_sha256"]:
            raise ValueError("prepared data_manifest hash drift")
        data_manifest = json.loads(data_manifest_path.read_text(encoding="utf-8"))
        if str(data_manifest.get("building_id", "")).removeprefix("DEBY_LOD2_") != building:
            raise ValueError("prepared data building mismatch")
        if any(data_manifest.get(key) is not False for key in ("gt_used", "lod2_used", "als_used")):
            raise ValueError("prepared data truth-input declaration drift")

        camera_manifest_path = resolve(data_manifest["camera_manifest"])
        if sha256_file(camera_manifest_path) != data_manifest["camera_manifest_sha256"]:
            raise ValueError("camera manifest hash drift")
        camera_manifest = json.loads(camera_manifest_path.read_text(encoding="utf-8"))
        sparse_root = data_root / "sparse/0"
        for name, expected_hash in camera_manifest["output_sparse_sha256"].items():
            if sha256_file(sparse_root / name) != expected_hash:
                raise ValueError(f"prepared sparse payload hash drift: {name}")
        for view in data_manifest["views"]:
            stem = str(view["view_stem"])
            paths = {
                "image": data_root / "images" / view["output_image_name"],
                "semantic": data_root / "semantic" / f"{stem}.png",
                "normal": data_root / "mono_normal" / f"{stem}.npy",
                "mono_depth": data_root / "mono_depth" / f"{stem}.npy",
                "semantic_region": data_root / "semantic_regions" / f"{stem}.npz",
            }
            for role, path in paths.items():
                if sha256_file(path) != view["output_sha256"][role]:
                    raise ValueError(f"prepared {role} payload hash drift: {stem}")
        for key in ("p0_surface_seed", "bc_aux_surface_seed", "bc_graph_propagation", "a1a2_surface_seed"):
            seed_row = data_manifest.get(key)
            if seed_row is None:
                continue
            if sha256_file(seed_row["path"]) != seed_row["sha256"]:
                raise ValueError(f"prepared seed payload hash drift: {key}")
            if key == "bc_graph_propagation":
                if sha256_file(seed_row["lineage_csv"]) != seed_row["lineage_csv_sha256"]:
                    raise ValueError("B-c graph-propagation lineage hash drift")
        cache[cache_key] = {
            "data_manifest": data_manifest,
            "data_manifest_sha256": data_manifest_hash,
        }
    data_manifest = cache[cache_key]["data_manifest"]

    seed_path = resolve(job["surface_seed_npz"])
    if container_repo_path(config["surface_seed_npz"], lock) != seed_path:
        raise ValueError("config surface seed path differs from jobs.csv")
    seed_hash = sha256_file(seed_path)
    if seed_hash != job["surface_seed_sha256"]:
        raise ValueError("surface seed payload hash drift")
    expected_seed = (
        data_manifest["p0_surface_seed"] if job["arm"] == "a0"
        else data_manifest["a1a2_surface_seed"]
    )
    if resolve(expected_seed["path"]) != seed_path or expected_seed["sha256"] != seed_hash:
        raise ValueError("arm surface seed differs from prepared data manifest")
    return {
        "prepare_manifest_sha256": input_contract["_manifest_sha256"],
        "data_manifest_sha256": cache[cache_key]["data_manifest_sha256"],
        "surface_seed_sha256": seed_hash,
    }


def preflight_job(
    job: dict[str, str],
    lock: dict[str, Any],
    *,
    input_contract: dict[str, Any] | None = None,
    payload_cache: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    config_path = resolve(job["config_path"])
    if not config_path.is_file():
        return {"status": "missing_config", "message": str(config_path)}
    actual_hash = sha256_file(config_path)
    if actual_hash != job["config_sha256"]:
        return {"status": "config_hash_mismatch", "message": f"{actual_hash}!={job['config_sha256']}"}
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if int(config.get("max_iter", -1)) != 30000 or int(job.get("iterations", -1)) != 30000:
        return {"status": "iteration_lock_mismatch", "message": str(config.get("max_iter"))}
    if config.get("init_pointcloud") or config.get("init_pointcloud_mode"):
        return {"status": "forbidden_mvs_initialization", "message": "init_pointcloud key present"}
    contract = config.get("phase2_input_contract") or {}
    if contract.get("gt_used") is not False or contract.get("lod2_used") is not False or contract.get("als_used") is not False:
        return {"status": "forbidden_reference_input", "message": "Phase-2 no-GT contract drift"}
    if config.get("visible_views") != config.get("train_views") or config.get("eval_views") != []:
        return {"status": "view_role_mismatch", "message": "visible_views must equal train_views and eval_views must be []"}
    payload_audit: dict[str, Any] = {}
    if input_contract is not None:
        try:
            payload_audit = validate_prepared_payload(
                job, config, lock, input_contract, payload_cache if payload_cache is not None else {},
            )
        except Exception as error:  # noqa: BLE001
            return {
                "status": "input_payload_mismatch",
                "message": f"{type(error).__name__}: {error}",
            }
    arm = str(job.get("arm", ""))
    if arm == "a0":
        zero_terms = (
            "w_depth", "w_normal", "w_mono_depth", "w_nc", "w_sem", "w_semdepth_smooth",
            "w_semdepth_plane", "w_boundary_normal", "w_structure", "w_mutual", "w_mvc", "w_distort",
        )
        if any(float(config.get(key, float("nan"))) != 0.0 for key in zero_terms):
            return {"status": "a0_not_photo_only", "message": "non-photometric term is nonzero or implicit"}
    elif arm in {"a1", "a2"}:
        required = {
            "mono_normal_loss": "target_region", "mono_depth_loss": "ssi",
            "mono_target_buildings": [job["building_id"]], "mono_target_min_pixels": 64,
            "load_normal": True, "load_semantic": True, "load_depth": False,
            "w_normal": 0.05, "w_mono_depth": 0.05,
        }
        if any(config.get(key) != expected for key, expected in required.items()):
            return {"status": "target_signal_wiring_mismatch", "message": "A1/A2 target-region signal contract drift"}
        if any(not config.get(key) for key in ("normal_dir", "mono_depth_dir", "semantic_region_cache")):
            return {"status": "target_signal_path_missing", "message": "A1/A2 cache path missing"}
    checkpoint = checkpoint_state(
        job["out_dir"],
        expected_iterations=int(job["iterations"]),
        expected_job_id=job["job_id"],
        expected_config_sha256=job["config_sha256"],
    )
    return {**payload_audit, **checkpoint, "message": checkpoint.get("message", "")}


def initial_status_rows(
    jobs: list[dict[str, str]],
    lock: dict[str, Any],
    *,
    input_contract: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    payload_cache: dict[str, dict[str, Any]] = {}
    for sequence, job in enumerate(jobs, 1):
        state = preflight_job(
            job, lock, input_contract=input_contract, payload_cache=payload_cache
        )
        rows.append({
            "sequence": sequence, "job_id": job["job_id"], "gpu_id": "",
            "status": state["status"], "attempt": 0, "config_path": job["config_path"],
            "config_sha256": job["config_sha256"], "out_dir": job["out_dir"],
            "final_checkpoint": state.get("final_checkpoint", job["final_checkpoint"]),
            "partial_checkpoints": ";".join(state.get("partial_checkpoints", [])),
            "started_utc": "", "ended_utc": utc_now() if state["status"] != "pending" else "",
            "elapsed_s": "", "timeout_s": "", "returncode": "", "log_path": "",
            "prepare_manifest_sha256": state.get("prepare_manifest_sha256", ""),
            "data_manifest_sha256": state.get("data_manifest_sha256", ""),
            "surface_seed_sha256": state.get("surface_seed_sha256", ""),
            "job_binding_sha256": state.get("job_binding_sha256", ""),
            "final_checkpoint_sha256": state.get("final_checkpoint_sha256", ""),
            "final_checkpoint_it": state.get("final_checkpoint_it", ""),
            "final_checkpoint_n_prim": state.get("final_checkpoint_n_prim", ""),
            "message": state.get("message", ""),
        })
    return rows


def run_inventory(
    jobs: list[dict[str, str]],
    lock: dict[str, Any],
    *,
    status_path: Path,
    log_dir: Path,
    timeout_s: int,
    gpu_ids: Sequence[int],
    input_contract: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    rows = initial_status_rows(jobs, lock, input_contract=input_contract)
    row_by_id = {row["job_id"]: row for row in rows}
    pending: queue.Queue[dict[str, str]] = queue.Queue()
    for job, row in zip(jobs, rows):
        if row["status"] == "pending":
            pending.put(job)
    atomic_csv(status_path, rows)
    log_dir.mkdir(parents=True, exist_ok=True)
    state_lock = threading.Lock()

    def persist() -> None:
        atomic_csv(status_path, sorted(rows, key=lambda row: int(row["sequence"])))

    def worker(gpu_id: int) -> None:
        while True:
            try:
                job = pending.get_nowait()
            except queue.Empty:
                return
            row = row_by_id[job["job_id"]]
            execution_state = preflight_job(
                job, lock, input_contract=input_contract, payload_cache={}
            )
            if execution_state["status"] != "pending":
                with state_lock:
                    row.update({
                        "status": execution_state["status"], "ended_utc": utc_now(),
                        "prepare_manifest_sha256": execution_state.get("prepare_manifest_sha256", ""),
                        "data_manifest_sha256": execution_state.get("data_manifest_sha256", ""),
                        "surface_seed_sha256": execution_state.get("surface_seed_sha256", ""),
                        "job_binding_sha256": execution_state.get("job_binding_sha256", ""),
                        "final_checkpoint_sha256": execution_state.get("final_checkpoint_sha256", ""),
                        "final_checkpoint_it": execution_state.get("final_checkpoint_it", ""),
                        "final_checkpoint_n_prim": execution_state.get("final_checkpoint_n_prim", ""),
                        "message": "execution-time preflight: " + execution_state.get("message", ""),
                    })
                    persist()
                pending.task_done()
                continue
            started = time.monotonic()
            log_path = log_dir / f"{job['job_id']}.log"
            command = materialize_command(lock["runtime"]["training_command"], job["config_path"])
            with state_lock:
                row.update({
                    "gpu_id": gpu_id, "status": "running", "attempt": int(row["attempt"]) + 1,
                    "started_utc": utc_now(), "ended_utc": "", "elapsed_s": "",
                    "timeout_s": timeout_s, "returncode": "", "log_path": relative(log_path),
                    "message": shlex.join(command),
                })
                persist()
            environment = os.environ.copy()
            environment["CUDA_VISIBLE_DEVICES"] = str(gpu_id)
            returncode: int | None = None
            final_status = "failed"
            message = ""
            try:
                binding = write_job_binding(job)
                with state_lock:
                    row["job_binding_sha256"] = binding["sha256"]
                    persist()
                with log_path.open("a", encoding="utf-8") as log:
                    log.write(f"{utc_now()} gpu={gpu_id} command={shlex.join(command)}\n")
                    log.flush()
                    process = subprocess.run(
                        command, cwd=REPO, env=environment, stdout=log, stderr=subprocess.STDOUT,
                        text=True, timeout=timeout_s, check=False,
                    )
                    returncode = int(process.returncode)
                checkpoint = checkpoint_state(
                    job["out_dir"], expected_iterations=int(job["iterations"]),
                    expected_job_id=job["job_id"],
                    expected_config_sha256=job["config_sha256"],
                )
                if returncode == 0 and checkpoint["status"] == "skipped_final_exists":
                    final_status = "complete"
                elif returncode == 0 and checkpoint["status"] == "invalid_final_checkpoint":
                    final_status = "failed_invalid_final"
                    message = checkpoint.get("message", "invalid final checkpoint")
                elif returncode == 0:
                    final_status = "failed_missing_final"
                    message = "training returned 0 without nonempty ckpt/final.pt"
                else:
                    final_status = "failed"
                    message = f"returncode={returncode}"
            except subprocess.TimeoutExpired:
                final_status = "timeout"
                message = f"elapsed exceeded timeout_s={timeout_s}"
            except Exception as error:  # noqa: BLE001
                final_status = "runner_error"
                message = f"{type(error).__name__}: {error}"
            elapsed = time.monotonic() - started
            with state_lock:
                checkpoint = checkpoint_state(
                    job["out_dir"], expected_iterations=int(job["iterations"]),
                    expected_job_id=job["job_id"],
                    expected_config_sha256=job["config_sha256"],
                )
                row.update({
                    "status": final_status, "ended_utc": utc_now(), "elapsed_s": f"{elapsed:.3f}",
                    "returncode": "" if returncode is None else returncode,
                    "final_checkpoint": checkpoint["final_checkpoint"],
                    "partial_checkpoints": ";".join(checkpoint["partial_checkpoints"]),
                    "final_checkpoint_sha256": checkpoint.get("final_checkpoint_sha256", ""),
                    "final_checkpoint_it": checkpoint.get("final_checkpoint_it", ""),
                    "final_checkpoint_n_prim": checkpoint.get("final_checkpoint_n_prim", ""),
                    "job_binding_sha256": checkpoint.get("job_binding_sha256", ""),
                    "message": message,
                })
                persist()
            pending.task_done()

    threads = [threading.Thread(target=worker, args=(int(gpu),), name=f"gpu-{gpu}") for gpu in gpu_ids]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    return sorted(rows, key=lambda row: int(row["sequence"]))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lock", default=str(DEFAULT_LOCK))
    parser.add_argument("--inventory", help="defaults to the base 42-job inventory")
    parser.add_argument("--timeout-s", type=int)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    lock = load_lock(args.lock)
    runtime_attestation = validate_runtime_attestation(lock)
    inventory_path = resolve(args.inventory or lock["outputs"]["base_inventory"])
    jobs = read_csv(inventory_path)
    if not jobs:
        raise RuntimeError(f"empty inventory: {inventory_path}")
    input_contract = validate_inventory_contract(inventory_path, jobs, lock)
    timeout_s = int(args.timeout_s or lock["runtime"]["default_run_timeout_s"])
    if timeout_s <= 0:
        raise ValueError("timeout must be positive")
    rows = initial_status_rows(jobs, lock, input_contract=input_contract)
    if args.dry_run:
        print(json.dumps({
            "inventory": relative(inventory_path), "jobs": len(jobs),
            "status_counts": {status: sum(row["status"] == status for row in rows) for status in sorted({row["status"] for row in rows})},
            "gpu_ids": lock["runtime"]["gpu_ids"], "timeout_s": timeout_s,
            "runtime_attestation": runtime_attestation,
            "prepare_manifest_sha256": input_contract["_manifest_sha256"],
            "training_started": False,
        }, sort_keys=True))
        return
    status_path = resolve(lock["outputs"]["runner_status"])
    log_dir = resolve(lock["outputs"]["runner_log_dir"])
    final = run_inventory(
        jobs, lock, status_path=status_path, log_dir=log_dir, timeout_s=timeout_s,
        gpu_ids=[int(value) for value in lock["runtime"]["gpu_ids"]],
        input_contract=input_contract,
    )
    print(json.dumps({
        "inventory": relative(inventory_path), "jobs": len(final), "status_path": relative(status_path),
        "status_counts": {status: sum(row["status"] == status for row in final) for status in sorted({row["status"] for row in final})},
    }, sort_keys=True))


if __name__ == "__main__":
    main()
