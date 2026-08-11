#!/usr/bin/env python3
"""Record idempotent smoke/training receipts for DN depth-only."""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path

import yaml


AR = Path("/artifacts/JointBuildGS")
TASK_ID = "P2-E3-LOCAL-4906982-DN-SPLATTER-DEPTH-ONLY-v1"
ROOT = AR / "phase-payloads/p2/e3_local_4906982_dn_splatter_depth_only_v1" / TASK_ID
RUN = ROOT / "arms/DN_DEPTH/R1"
STEPS = (7000, 12000, 15000, 20000)


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def atomic_json(path: Path, body: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(body, indent=2, sort_keys=True) + "\n")
    os.replace(tmp, path)


def valid_checkpoint(step: int) -> bool:
    p = RUN / f"ckpt/step_{step:06d}.pt"
    s = Path(str(p) + ".sha256")
    return p.is_file() and s.is_file() and s.read_text().split()[0] == sha256(p)


def smoke() -> None:
    grad = ROOT / "smoke/DN_DEPTH/audit/loss_grad_norms.csv"
    rows = list(csv.DictReader(grad.open()))
    row = next(r for r in rows if r["step"] == "0" and r["component"] == "depth")
    effective = ROOT / "smoke/DN_DEPTH/effective_config.json"
    cfg = json.loads(effective.read_text())
    runtime = yaml.safe_load((ROOT / "control/runtime_configs/dn_depth_smoke.yaml").read_text())
    passed = (
        float(row["raw_loss"]) > 0 and float(row["grad_norm"]) > 0
        and runtime["depth_loss_type"] == "dn_edge_aware_log_l1"
        and cfg["depth_supervision_mode"] == "expected"
        and cfg["depth_base_weight"] == 0.2 and runtime["w_normal"] == 0.0
        and runtime["w_mvc"] == 0.0
    )
    body = {
        "schema": "jointbuildgs.dn_depth_only.smoke_gate.v1", "passed": passed,
        "raw_depth_loss_step0": float(row["raw_loss"]),
        "weighted_depth_loss_step0": float(row["weighted_loss"]),
        "depth_weighted_loss_share_step0": float(row["weighted_loss_share"]),
        "depth_grad_norm_step0": float(row["grad_norm"]),
        "finite_final_checkpoint": (ROOT / "smoke/DN_DEPTH/ckpt/final.pt").is_file(),
        "effective_config_sha256": sha256(effective), "scientific_verdict": None,
    }
    atomic_json(ROOT / "control/smoke_gate.json", body)
    if not passed:
        raise SystemExit(2)
    print(json.dumps(body, sort_keys=True))


def start(command: str) -> None:
    gate = json.loads((ROOT / "control/smoke_gate.json").read_text())
    if not gate["passed"]:
        raise RuntimeError("smoke gate is closed")
    receipt_path = ROOT / "control/receipts/train_dn_depth_r1.json"
    prior = json.loads(receipt_path.read_text()) if receipt_path.is_file() else {}
    body = {
        "schema": "jointbuildgs.dn_depth_only.training_receipt.v1",
        "arm": "DN_DEPTH", "status": "RUNNING_OR_RESUMABLE",
        "started_utc": prior.get("started_utc") or now(), "ended_utc": None,
        "command": command, "return_code": None,
        "checkpoint_valid": {str(s): valid_checkpoint(s) for s in STEPS},
        "scientific_verdict": None,
    }
    atomic_json(receipt_path, body)
    contract_path = ROOT / "experiment_contract.json"
    contract = json.loads(contract_path.read_text())
    contract.update({"status": "TRAINING_STARTED", "new_training_arms_started": ["DN_DEPTH"], "scientific_verdict": None})
    atomic_json(contract_path, contract)


def finish(code: int) -> None:
    path = ROOT / "control/receipts/train_dn_depth_r1.json"
    body = json.loads(path.read_text())
    validity = {str(s): valid_checkpoint(s) for s in STEPS}
    passed = code == 0 and all(validity.values())
    body.update({"status": "COMPLETE" if passed else "FAILED_OR_INCOMPLETE", "ended_utc": now(), "return_code": code, "checkpoint_valid": validity, "passed": passed, "scientific_verdict": None})
    atomic_json(path, body)
    contract_path = ROOT / "experiment_contract.json"
    contract = json.loads(contract_path.read_text())
    contract["status"] = "TRAINING_COMPLETE" if passed else "TRAINING_INCOMPLETE"
    contract["scientific_verdict"] = None
    atomic_json(contract_path, contract)
    if not passed:
        raise SystemExit(2)


def main() -> None:
    parser = argparse.ArgumentParser()
    subs = parser.add_subparsers(dest="mode", required=True)
    subs.add_parser("smoke")
    start_parser = subs.add_parser("start")
    start_parser.add_argument("--command", required=True)
    finish_parser = subs.add_parser("finish")
    finish_parser.add_argument("--return-code", type=int, required=True)
    args = parser.parse_args()
    {"smoke": lambda: smoke(), "start": lambda: start(args.command), "finish": lambda: finish(args.return_code)}[args.mode]()


if __name__ == "__main__":
    main()
