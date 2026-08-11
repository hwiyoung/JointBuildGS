#!/usr/bin/env python3
"""Read-only expected-depth gate and staged MVS-transfer diagnostic.

The host side only records runtime identity and starts the frozen development
image.  Project imports, asset inspection, rendering, and artifact generation
all run in Docker.  Training is deliberately not implemented here: it remains
gated by ``expected_median_audit.json``.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys


REPO = Path(__file__).resolve().parents[3]
ARTIFACT_ROOT = REPO.parent / "JointBuildGS-artifacts"
TASK_ID = "P2-E3-LOCAL-4906982-MVS-TRANSFER-DIAG-v1"
TASK_ROOT = (
    ARTIFACT_ROOT
    / "phase-payloads/p2/e3_local_4906982_mvs_transfer_diag_v1"
    / TASK_ID
)
IMAGE = "jointbuildgs:dev"
GPU = "1"
INNER = "scripts/p2/e3_local_4906982_mvs_transfer_diag_v1/inside.py"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def inspect_image() -> dict:
    body = json.loads(
        subprocess.run(
            ["docker", "image", "inspect", IMAGE],
            check=True,
            text=True,
            capture_output=True,
        ).stdout
    )[0]
    return {
        "reference": IMAGE,
        "id": body["Id"],
        "repo_digests": body.get("RepoDigests") or [],
    }


def docker_command(stage: str, image: dict) -> list[str]:
    return [
        "docker", "run", "--rm", "--gpus", f"device={GPU}", "--ipc=host",
        "--network", "none",
        "-e", "PYTHONDONTWRITEBYTECODE=1",
        "-e", "CUBLAS_WORKSPACE_CONFIG=:4096:8",
        "-e", f"JBGS_HOST_IMAGE_ID={image['id']}",
        "-e", f"JBGS_HOST_IMAGE_DIGESTS={json.dumps(image['repo_digests'])}",
        "-e", f"JBGS_SELECTED_GPU={GPU}",
        "-v", f"{REPO}:/workspace/JointBuildGS:ro",
        "-v", f"{ARTIFACT_ROOT}:/artifacts/JointBuildGS",
        "-v", f"{TASK_ROOT / 'cache/torch_extensions'}:/root/.cache/torch_extensions",
        "-w", "/workspace/JointBuildGS",
        IMAGE, "python", INNER, stage,
    ]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "stage", choices=("preflight", "expected-depth-audit", "gate"),
        help="gate runs preflight and then the read-only expected-depth audit",
    )
    args = parser.parse_args()
    TASK_ROOT.mkdir(parents=True, exist_ok=True)
    (TASK_ROOT / "logs").mkdir(exist_ok=True)
    (TASK_ROOT / "cache/torch_extensions").mkdir(parents=True, exist_ok=True)
    image = inspect_image()
    stages = ("preflight", "expected-depth-audit") if args.stage == "gate" else (args.stage,)
    for stage in stages:
        argv = docker_command(stage, image)
        started = utc_now()
        log = TASK_ROOT / "logs" / f"{stage}.log"
        with log.open("a", encoding="utf-8") as stream:
            stream.write(f"\n[{started}] argv={json.dumps(argv)}\n")
            stream.flush()
            proc = subprocess.run(argv, stdout=stream, stderr=subprocess.STDOUT, text=True)
            ended = utc_now()
            stream.write(f"[{ended}] return_code={proc.returncode}\n")
        # Keep the host-side receipt in the host-created log directory.  The
        # container owns control artifacts and may run with a different UID.
        receipt = TASK_ROOT / "logs" / f"host_{stage}.json"
        receipt.parent.mkdir(parents=True, exist_ok=True)
        temporary = receipt.with_suffix(".json.tmp")
        temporary.write_text(json.dumps({
            "stage": stage, "argv": argv, "started_utc": started,
            "ended_utc": ended, "return_code": proc.returncode,
            "docker_image": image, "selected_gpu": GPU,
            "scientific_verdict": None,
        }, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        os.replace(temporary, receipt)
        if proc.returncode:
            print(f"{stage} failed; inspect {log}", file=sys.stderr)
            raise SystemExit(proc.returncode)
        print(f"{stage}: complete; log={log}")


if __name__ == "__main__":
    main()
