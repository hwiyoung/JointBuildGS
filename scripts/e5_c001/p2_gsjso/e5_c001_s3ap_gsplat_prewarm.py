#!/usr/bin/env python3
"""Serialize the gsplat CUDA JIT build before Phase-2 GPU workers start."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import torch


REPO = Path(__file__).resolve().parents[3]
DEFAULT_LOCK = REPO / "phases/p2-gsjso/configs/e5_c001/e5_c001_s3ap_phase2_lock.json"
RUNNER = REPO / "phases/p2-gsjso/scripts/e5_c001/e5_c001_s3ap_phase2_runner.py"
SCHEMA = "jointbuildgs.s3ap.phase2.gsplat_prewarm.v1"


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


def load_runner():
    specification = importlib.util.spec_from_file_location("s3ap_phase2_runner_prewarm", RUNNER)
    if specification is None or specification.loader is None:
        raise RuntimeError(f"cannot import runner: {RUNNER}")
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


def git_value(*arguments: str) -> str:
    return subprocess.check_output(["git", *arguments], cwd=REPO, text=True).strip()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lock", default=str(DEFAULT_LOCK))
    parser.add_argument("--manifest")
    args = parser.parse_args()

    runner = load_runner()
    lock = runner.load_lock(args.lock)
    attestation = runner.validate_runtime_attestation(lock)
    contract = lock["runtime"].get("gsplat_prewarm") or {}
    if contract.get("script") != relative(__file__):
        raise RuntimeError("gsplat prewarm script lock drift")
    manifest_path = resolve(args.manifest or contract.get("manifest", ""))
    if not str(manifest_path):
        raise RuntimeError("gsplat prewarm manifest path is absent")
    if not torch.cuda.is_available() or torch.cuda.device_count() < 1:
        raise RuntimeError("gsplat prewarm requires at least one CUDA device")

    started = time.monotonic()
    from gsplat.cuda._backend import _C  # noqa: PLC0415 - import triggers the locked JIT build

    module_path = Path(getattr(_C, "__file__", ""))
    if not module_path.is_file() or module_path.suffix != ".so":
        raise RuntimeError(f"gsplat CUDA extension did not resolve to a shared object: {module_path}")
    extension_root = Path(os.environ["TORCH_EXTENSIONS_DIR"])
    try:
        module_path.resolve().relative_to(extension_root.resolve())
    except ValueError as error:
        raise RuntimeError("gsplat CUDA extension lies outside TORCH_EXTENSIONS_DIR") from error

    payload = {
        "schema": SCHEMA,
        "status": "complete",
        "completed_utc": utc_now(),
        "elapsed_s": round(time.monotonic() - started, 3),
        "git_head": git_value("rev-parse", "HEAD"),
        "git_branch": git_value("branch", "--show-current"),
        "lock_path": relative(args.lock),
        "lock_sha256": sha256_file(args.lock),
        "script": relative(__file__),
        "script_sha256": sha256_file(__file__),
        "runtime_attestation": attestation,
        "torch_version": torch.__version__,
        "torch_cuda_version": torch.version.cuda,
        "cuda_device_count": torch.cuda.device_count(),
        "cuda_devices": [torch.cuda.get_device_name(index) for index in range(torch.cuda.device_count())],
        "extension_module": "gsplat.cuda._backend._C",
        "extension_path": str(module_path),
        "extension_sha256": sha256_file(module_path),
        "torch_extensions_dir": str(extension_root),
    }
    atomic_json(manifest_path, payload)
    print(json.dumps({
        "status": payload["status"],
        "manifest": relative(manifest_path),
        "extension_sha256": payload["extension_sha256"],
        "elapsed_s": payload["elapsed_s"],
    }, sort_keys=True))


if __name__ == "__main__":
    main()
