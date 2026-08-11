#!/usr/bin/env python3
"""Validate smoke and update idempotent training receipts."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from datetime import datetime, timezone


ARTIFACT_ROOT = Path("/artifacts/JointBuildGS")
TASK_ID = "P2-E3-LOCAL-4906982-REFERENCE-FAMILY-DIAG-v1"
TASK_ROOT = (
    ARTIFACT_ROOT
    / "phase-payloads/p2/e3_local_4906982_reference_family_diag_v1"
    / TASK_ID
)
SMOKE_ROOT = TASK_ROOT / "smoke/attempt_2/GSPLAT_2DGS_REF"
RUN_ROOT = TASK_ROOT / "arms/GSPLAT_2DGS_REF/R1"


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_json(path: Path, body: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(body, indent=2, sort_keys=True) + "\n")
    os.replace(tmp, path)


def checkpoint_valid(step: int) -> bool:
    checkpoint = RUN_ROOT / "ckpt" / f"step_{step:06d}.pt"
    sidecar = Path(str(checkpoint) + ".sha256")
    if not checkpoint.is_file() or not sidecar.is_file():
        return False
    expected = sidecar.read_text().strip().split()[0]
    return expected == sha256(checkpoint)


def start(command: str) -> None:
    effective_path = SMOKE_ROOT / "effective_config.json"
    final_path = SMOKE_ROOT / "ckpt/final.pt"
    if not effective_path.is_file() or not final_path.is_file():
        raise RuntimeError("attempt-2 smoke outputs are incomplete")
    effective = json.loads(effective_path.read_text())
    required = {
        "normal_consistency_mode": "official_2dgs",
        "surface_normal_depth_mode": "surface_intersection_expected",
        "lr_means_schedule": "official_2dgs_exponential",
        "w_nc": 0.05,
        "nc_warmup": 7000,
        "w_distort": 0.0,
        "depth_supervision_mode": "expected",
    }
    mismatch = {
        key: [effective.get(key), value]
        for key, value in required.items()
        if effective.get(key) != value
    }
    if mismatch:
        raise RuntimeError(f"smoke effective config mismatch: {mismatch}")
    smoke_gate = {
        "schema": "jointbuildgs.reference_family_smoke_gate.v1",
        "attempt": 2,
        "completed_updates": 20,
        "final_checkpoint": str(final_path),
        "final_checkpoint_sha256": sha256(final_path),
        "effective_config": str(effective_path),
        "effective_config_sha256": sha256(effective_path),
        "passed": True,
        "scientific_verdict": None,
    }
    atomic_json(TASK_ROOT / "control/smoke_gate.json", smoke_gate)
    contract_path = TASK_ROOT / "experiment_contract.json"
    contract = json.loads(contract_path.read_text())
    contract.update(
        {
            "status": "TRAINING_STARTED",
            "training_experiments_started": 1,
            "training_arms_started": ["GSPLAT_2DGS_REF"],
            "training_arms_blocked": ["PGSR_REF"],
            "training_started_utc": contract.get("training_started_utc") or now(),
            "scientific_verdict": None,
        }
    )
    atomic_json(contract_path, contract)
    receipt_path = TASK_ROOT / "control/receipts/train_gsplat_2dgs_ref_r1.json"
    prior = json.loads(receipt_path.read_text()) if receipt_path.is_file() else {}
    receipt = {
        "schema": "jointbuildgs.reference_family_training_receipt.v1",
        "arm": "GSPLAT_2DGS_REF",
        "status": "RUNNING_OR_RESUMABLE",
        "started_utc": prior.get("started_utc") or now(),
        "ended_utc": None,
        "command": command,
        "return_code": None,
        "checkpoint_valid": {str(step): checkpoint_valid(step) for step in (7000, 12000, 15000, 20000)},
        "scientific_verdict": None,
    }
    atomic_json(receipt_path, receipt)
    print(json.dumps(smoke_gate, sort_keys=True))


def finish(return_code: int, max_sampled_vram_mib: int | None) -> None:
    receipt_path = TASK_ROOT / "control/receipts/train_gsplat_2dgs_ref_r1.json"
    receipt = json.loads(receipt_path.read_text())
    validity = {str(step): checkpoint_valid(step) for step in (7000, 12000, 15000, 20000)}
    passed = return_code == 0 and all(validity.values())
    receipt.update(
        {
            "status": "COMPLETE" if passed else "FAILED_OR_INCOMPLETE",
            "ended_utc": now(),
            "return_code": return_code,
            "checkpoint_valid": validity,
            "passed": passed,
            "wall_seconds": (
                datetime.fromisoformat(receipt["ended_utc"]).timestamp()
                - datetime.fromisoformat(receipt["started_utc"]).timestamp()
            ),
            "max_selected_gpu_used_mib": max_sampled_vram_mib,
            "scientific_verdict": None,
        }
    )
    atomic_json(receipt_path, receipt)
    contract_path = TASK_ROOT / "experiment_contract.json"
    contract = json.loads(contract_path.read_text())
    contract["status"] = "TRAINING_COMPLETE" if passed else "TRAINING_INCOMPLETE"
    contract["training_completed_utc"] = now() if passed else None
    contract["scientific_verdict"] = None
    atomic_json(contract_path, contract)
    print(json.dumps(receipt, sort_keys=True))
    if not passed:
        raise SystemExit(2)


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    start_parser = sub.add_parser("start")
    start_parser.add_argument("--training-command", required=True)
    finish_parser = sub.add_parser("finish")
    finish_parser.add_argument("--return-code", required=True, type=int)
    finish_parser.add_argument("--max-sampled-vram-mib", type=int)
    args = parser.parse_args()
    if args.command == "start":
        start(args.training_command)
    else:
        finish(args.return_code, args.max_sampled_vram_mib)


if __name__ == "__main__":
    main()
