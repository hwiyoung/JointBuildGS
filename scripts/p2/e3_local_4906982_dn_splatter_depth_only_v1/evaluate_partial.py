#!/usr/bin/env python3
"""Evaluate valid partial DN depth-only checkpoints with frozen 4906982 tooling."""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import subprocess


REPO = Path(__file__).resolve().parents[3]
AR = REPO.parent / "JointBuildGS-artifacts"
TASK_ID = "P2-E3-LOCAL-4906982-DN-SPLATTER-DEPTH-ONLY-v1"
ROOT = AR / "phase-payloads/p2/e3_local_4906982_dn_splatter_depth_only_v1" / TASK_ID
BASE = REPO / "scripts/p2/e3_local_4906982_mvc_v2/run.py"
ARM, REPLICA, STEPS = "DN_DEPTH", "R1", (7000, 12000)


def load_base():
    spec = importlib.util.spec_from_file_location("jbgs_dn_partial_eval", BASE)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load frozen evaluator")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.TASK_ID, module.TASK_ROOT, module.ARTIFACT_ROOT = TASK_ID, ROOT, AR
    module.GPU, module.ARMS, module.REPLICAS, module.CHECKPOINTS = "1", (ARM,), (REPLICA,), STEPS
    return module


def replace_once(value: str, old: str, new: str) -> str:
    if value.count(old) != 1:
        raise RuntimeError(f"evaluator patch count mismatch: {old!r}")
    return value.replace(old, new)


def configure(base) -> None:
    code = base.ANALYZE_CODE
    code = replace_once(code, "arms=['MVC0','MVC05']; replicas=['R1','R2','R3']; steps=[7000,12000,15000,20000]", "arms=['DN_DEPTH']; replicas=['R1']; steps=[7000,12000]")
    code = replace_once(code, "control/runtime_configs/mvc0_r1.yaml", "control/runtime_configs/dn_depth_r1.yaml")
    code = replace_once(code, "mvc_weight=0.0 if arm=='MVC0' or step<=7000 else .5", "mvc_weight=0.0")
    code = replace_once(code, "jointbuildgs.p2.e3_local_4906982_mvc_v2.checkpoint_evaluation.v1", "jointbuildgs.p2.e3_local_4906982_dn_splatter_depth_only_v1.checkpoint_evaluation.v1")
    code = replace_once(code, "float(np.std([x[k] for x in subset],ddof=1))", "float(np.std([x[k] for x in subset],ddof=0))")
    code = replace_once(code, "jointbuildgs.p2.e3_local_4906982_mvc_v2.metrics.v1", "jointbuildgs.p2.e3_local_4906982_dn_splatter_depth_only_v1.partial_metrics.v1")
    code = replace_once(code, "'replicates_per_arm':3", "'replicates_per_arm':1")
    base.ANALYZE_CODE = code

    prep = base.STAGE3_PREP_CODE
    prep = replace_once(prep, "for arm in ['MVC0','MVC05']:\n for replica in ['R1','R2','R3']:", "for arm in ['DN_DEPTH']:\n for replica in ['R1']:")
    prep = replace_once(prep, "  for step in [7000,12000,15000,20000]:", "  for step in [7000,12000]:")
    prep = replace_once(prep, "jointbuildgs.p2.e3_local_4906982_mvc_v2.stage3_preparation.v1", "jointbuildgs.p2.e3_local_4906982_dn_splatter_depth_only_v1.stage3_preparation.v1")
    base.STAGE3_PREP_CODE = prep
    base.STAGE3_VERIFY_CODE = base.STAGE3_VERIFY_CODE.replace("jointbuildgs.p2.e3_local_4906982_mvc_v2.classified_fusion.v1", "jointbuildgs.p2.e3_local_4906982_dn_splatter_depth_only_v1.classified_fusion.v1")
    base.ROOFER_RECORD_CODE = base.ROOFER_RECORD_CODE.replace("jointbuildgs.p2.e3_local_4906982_mvc_v2.roofer_terminal.v1", "jointbuildgs.p2.e3_local_4906982_dn_splatter_depth_only_v1.roofer_terminal.v1")


def atomic_json(path: Path, body: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(body, indent=2, sort_keys=True) + "\n")
    os.replace(tmp, path)


def prepare_receipt_alias() -> None:
    source = ROOT / "control/receipts/train_dn_depth_r1.json"
    body = json.loads(source.read_text())
    body["partial_evaluation_steps"] = list(STEPS)
    body.setdefault("max_selected_gpu_used_mib", 0)
    if body["max_selected_gpu_used_mib"] is None:
        body["max_selected_gpu_used_mib"] = 0
        body["max_selected_gpu_used_mib_status"] = "not_sampled"
    body["scientific_verdict"] = None
    atomic_json(ROOT / f"control/receipts/train_{ARM}_{REPLICA}.json", body)
    provenance = json.loads((ROOT / "provenance.json").read_text())
    provenance.setdefault("commands", [])
    provenance.setdefault("return_codes", [])
    atomic_json(ROOT / "provenance.json", provenance)


def normalize_owner() -> None:
    subprocess.run(["docker", "run", "--rm", "--network", "none", "-v", f"{ROOT}:/task:rw", "--entrypoint", "chown", "jointbuildgs:mvc-eval-v1", "-R", f"{os.getuid()}:{os.getgid()}", "/task"], check=True)


def main() -> None:
    for step in STEPS:
        checkpoint = ROOT / f"arms/{ARM}/{REPLICA}/ckpt/step_{step:06d}.pt"
        if not checkpoint.is_file() or not Path(str(checkpoint) + ".sha256").is_file():
            raise RuntimeError(f"missing valid partial checkpoint {step}")
    prepare_receipt_alias()
    base = load_base()
    configure(base)
    if not (ROOT / "metrics.json").is_file() or not (ROOT / "checkpoint_metrics.csv").is_file():
        base.analyze_checkpoints()
        normalize_owner()
    normalize_owner()
    base.run_stage3()
    normalize_owner()


if __name__ == "__main__":
    main()
