#!/usr/bin/env python3
"""Evaluate the one parity-approved reference-family arm.

The host process only orchestrates pinned Docker images.  The implementation
reuses the frozen 4906982 checkpoint/fusion/Stage-3 evaluator and narrows it to
GSPLAT_2DGS_REF/R1.  PGSR is deliberately absent because the parity audit
blocked it before training.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
from pathlib import Path
import subprocess


REPO = Path(__file__).resolve().parents[3]
ARTIFACT_ROOT = REPO.parent / "JointBuildGS-artifacts"
TASK_ID = "P2-E3-LOCAL-4906982-REFERENCE-FAMILY-DIAG-v1"
TASK_ROOT = (
    ARTIFACT_ROOT
    / "phase-payloads/p2/e3_local_4906982_reference_family_diag_v1"
    / TASK_ID
)
BASE_PATH = REPO / "scripts/p2/e3_local_4906982_mvc_v2/run.py"
ARM = "GSPLAT_2DGS_REF"
REPLICA = "R1"
STEPS = (7000, 12000, 15000, 20000)


def atomic_json(path: Path, body: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(body, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, path)


def load_base():
    spec = importlib.util.spec_from_file_location("jbgs_mvc_v2_eval_base", BASE_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load evaluation base: {BASE_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.TASK_ID = TASK_ID
    module.TASK_ROOT = TASK_ROOT
    module.ARTIFACT_ROOT = ARTIFACT_ROOT
    module.GPU = "1"
    module.ARMS = (ARM,)
    module.REPLICAS = (REPLICA,)
    module.CHECKPOINTS = STEPS
    return module


def replace_once(value: str, old: str, new: str) -> str:
    count = value.count(old)
    if count != 1:
        raise RuntimeError(f"expected one evaluator source match, found {count}: {old!r}")
    return value.replace(old, new)


def prepare_receipts() -> None:
    provenance_path = TASK_ROOT / "provenance.json"
    provenance = json.loads(provenance_path.read_text())
    provenance.setdefault("commands", [])
    provenance.setdefault("return_codes", [])
    provenance["scientific_verdict"] = None
    atomic_json(provenance_path, provenance)

    source = TASK_ROOT / "control/receipts/train_gsplat_2dgs_ref_r1.json"
    alias = TASK_ROOT / f"control/receipts/train_{ARM}_{REPLICA}.json"
    body = json.loads(source.read_text())
    body["receipt_alias_of"] = str(source.relative_to(TASK_ROOT))
    body["scientific_verdict"] = None
    atomic_json(alias, body)


def configure_base(base) -> None:
    code = base.ANALYZE_CODE
    code = replace_once(
        code,
        "arms=['MVC0','MVC05']; replicas=['R1','R2','R3']; steps=[7000,12000,15000,20000]",
        "arms=['GSPLAT_2DGS_REF']; replicas=['R1']; steps=[7000,12000,15000,20000]",
    )
    code = replace_once(
        code,
        "control/runtime_configs/mvc0_r1.yaml",
        "control/runtime_configs/gsplat_2dgs_ref_r1.yaml",
    )
    code = replace_once(
        code,
        "mvc_weight=0.0 if arm=='MVC0' or step<=7000 else .5",
        "mvc_weight=0.0",
    )
    code = replace_once(
        code,
        "jointbuildgs.p2.e3_local_4906982_mvc_v2.checkpoint_evaluation.v1",
        "jointbuildgs.p2.e3_local_4906982_reference_family_diag_v1.checkpoint_evaluation.v1",
    )
    code = replace_once(
        code,
        "float(np.std([x[k] for x in subset],ddof=1))",
        "float(np.std([x[k] for x in subset],ddof=0))",
    )
    code = replace_once(
        code,
        "jointbuildgs.p2.e3_local_4906982_mvc_v2.metrics.v1",
        "jointbuildgs.p2.e3_local_4906982_reference_family_diag_v1.metrics.v1",
    )
    code = replace_once(code, "'replicates_per_arm':3", "'replicates_per_arm':1")
    base.ANALYZE_CODE = code

    prep = base.STAGE3_PREP_CODE
    prep = replace_once(
        prep,
        "for arm in ['MVC0','MVC05']:\n for replica in ['R1','R2','R3']:",
        "for arm in ['GSPLAT_2DGS_REF']:\n for replica in ['R1']:",
    )
    prep = replace_once(
        prep,
        "jointbuildgs.p2.e3_local_4906982_mvc_v2.stage3_preparation.v1",
        "jointbuildgs.p2.e3_local_4906982_reference_family_diag_v1.stage3_preparation.v1",
    )
    base.STAGE3_PREP_CODE = prep
    base.STAGE3_VERIFY_CODE = base.STAGE3_VERIFY_CODE.replace(
        "jointbuildgs.p2.e3_local_4906982_mvc_v2.classified_fusion.v1",
        "jointbuildgs.p2.e3_local_4906982_reference_family_diag_v1.classified_fusion.v1",
    )
    base.ROOFER_RECORD_CODE = base.ROOFER_RECORD_CODE.replace(
        "jointbuildgs.p2.e3_local_4906982_mvc_v2.roofer_terminal.v1",
        "jointbuildgs.p2.e3_local_4906982_reference_family_diag_v1.roofer_terminal.v1",
    )


def normalize_task_ownership() -> None:
    """Keep later host orchestration idempotent after rootful eval containers."""
    argv = [
        "docker", "run", "--rm", "--network", "none",
        "-v", f"{TASK_ROOT}:/task:rw", "--entrypoint", "chown",
        "jointbuildgs:mvc-eval-v1", "-R", f"{os.getuid()}:{os.getgid()}", "/task",
    ]
    completed = subprocess.run(argv, text=True, capture_output=True)
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr or completed.stdout)


def validate_gates() -> None:
    audit = json.loads((TASK_ROOT / "reference_parity_audit.json").read_text())
    arms = {row["arm"]: row for row in audit["arms"]}
    if arms["GSPLAT_2DGS_REF"]["parity_status"] != "PASS_GSPLAT_ADAPTATION":
        raise RuntimeError("GSPLAT_2DGS_REF parity gate is not open")
    if arms["PGSR_REF"]["parity_status"] != "BLOCKED_NOT_REFERENCE_FAITHFUL":
        raise RuntimeError("PGSR parity gate unexpectedly changed")
    receipt = json.loads(
        (TASK_ROOT / "control/receipts/train_gsplat_2dgs_ref_r1.json").read_text()
    )
    if not receipt.get("passed") or not all(
        receipt["checkpoint_valid"].get(str(step)) for step in STEPS
    ):
        raise RuntimeError("required training receipt/checkpoints are not valid")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("analyze", "stage3", "all"))
    args = parser.parse_args()
    validate_gates()
    prepare_receipts()
    base = load_base()
    configure_base(base)
    if args.command in {"analyze", "all"}:
        base.analyze_checkpoints()
        normalize_task_ownership()
    if args.command in {"stage3", "all"}:
        base.run_stage3()
        normalize_task_ownership()


if __name__ == "__main__":
    main()
