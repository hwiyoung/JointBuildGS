#!/usr/bin/env python3
"""Launch the DEC-P1-017 bounded C4 run after a closed preflight."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from typing import Any

import torch
import yaml


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def checkpoint_records(out_dir: Path) -> list[dict[str, Any]]:
    return [
        {"path": str(path), "bytes": path.stat().st_size, "sha256": digest(path)}
        for path in sorted((out_dir / "ckpt").glob("*"))
        if path.is_file()
    ]


def run(config_path: Path, artifact_root: Path) -> int:
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if config.get("decision") != "DEC-P1-017" or int(config.get("max_iter", -1)) != 30000:
        raise RuntimeError("bounded C4 decision/iteration contract drifted")
    if config.get("scientific_verdict", "missing") is not None:
        raise RuntimeError("scientific_verdict must remain null")
    preflight_path = artifact_root / "control/200-c4-preflight-passed.json"
    preflight = json.loads(preflight_path.read_text(encoding="utf-8"))
    if preflight.get("status") != "200-PASSED_ALIGNMENT_GRADIENT_AND_GPU_MEMORY_PREFLIGHT":
        raise RuntimeError("C4 preflight is not closed-passed")
    final_preflight_path = artifact_root / "control/210-c4-final-preflight-passed.json"
    final_preflight = json.loads(final_preflight_path.read_text(encoding="utf-8"))
    if final_preflight.get("status") != "210-PASSED_NONZERO_GRADIENT_AND_22000MIB_GPU_GATE":
        raise RuntimeError("final C4 gradient/22,000 MiB gate is not passed")
    free, total = torch.cuda.mem_get_info()
    if free < 22_000 * 1024**2:
        raise RuntimeError(f"GPU free-memory gate failed immediately before launch: {free}")
    out_dir = Path(config["out_dir"])
    if out_dir.exists() and any(out_dir.iterdir()):
        raise RuntimeError(f"add-once C4 training namespace is not empty: {out_dir}")
    out_dir.mkdir(parents=True, exist_ok=True)
    started = {
        "schema": "jointbuildgs.p2.c4_existing_als_run_started.v1",
        "status": "110-STARTED_BOUNDED_C4_OVERNIGHT",
        "started_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "config": str(config_path),
        "config_sha256": digest(config_path),
        "preflight": str(preflight_path),
        "preflight_sha256": digest(preflight_path),
        "final_preflight": str(final_preflight_path),
        "final_preflight_sha256": digest(final_preflight_path),
        "gpu_name": torch.cuda.get_device_name(0),
        "gpu_total_bytes": int(total),
        "gpu_free_bytes": int(free),
        "matched_control": preflight["matched_control"],
        "c5_executed": False,
        "official_G3_G4_PASS_usable": None,
        "scientific_verdict": None,
    }
    atomic_json(artifact_root / "control/110-c4-run-started.json", started)
    command = [sys.executable, "-m", "src.stage2.train", "--config", str(config_path)]
    try:
        completed = subprocess.run(command, check=False)
        if completed.returncode != 0:
            failure = {
                "schema": "jointbuildgs.p2.c4_existing_als_run_failure.v1",
                "status": "100-FAILED_BOUNDED_C4_TRAINING",
                "returncode": completed.returncode,
                "ended_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                "checkpoints_preserved": checkpoint_records(out_dir),
                "c5_executed": False,
                "scientific_verdict": None,
            }
            atomic_json(artifact_root / "control/100-c4-run-failed.json", failure)
            return completed.returncode
        closed = {
            "schema": "jointbuildgs.p2.c4_existing_als_run_complete.v1",
            "status": "200-COMPLETED_BOUNDED_C4_TRAINING",
            "ended_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "checkpoints": checkpoint_records(out_dir),
            "c5_executed": False,
            "official_G3_G4_PASS_usable": None,
            "scientific_verdict": None,
        }
        atomic_json(artifact_root / "control/200-c4-run-complete.json", closed)
        return 0
    except BaseException as exc:
        atomic_json(artifact_root / "control/100-c4-run-exception.json", {
            "schema": "jointbuildgs.p2.c4_existing_als_run_exception.v1",
            "status": "100-FAILED_BOUNDED_C4_TRAINING_EXCEPTION",
            "error_type": type(exc).__name__,
            "error": str(exc),
            "checkpoints_preserved": checkpoint_records(out_dir),
            "c5_executed": False,
            "scientific_verdict": None,
        })
        raise


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--artifact-root", type=Path, required=True)
    args = parser.parse_args()
    raise SystemExit(run(args.config, args.artifact_root))


if __name__ == "__main__":
    main()
