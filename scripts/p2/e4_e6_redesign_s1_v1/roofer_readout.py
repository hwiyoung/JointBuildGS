#!/usr/bin/env python3
"""S1 roofer readout: run the proven mvc/e4-local Stage-3 chain over six runs.

Adapts the validated embedded evaluators (checkpoint analysis -> SMRF
classification -> Roofer -> finalize) to the S1 task root with arms
[FUSED_VIS_CONF control proxy, A1..A5] x R1 x [7000,12000,15000,20000].
Metric definitions are byte-inherited from the sealed harness; only arm
names, replica list, the control runtime-config name, and the tag list of
training scalars are substituted.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import subprocess
from pathlib import Path
from typing import Any

import yaml

REPO = Path(__file__).resolve().parents[3]
ARTIFACT_ROOT = REPO.parent / "JointBuildGS-artifacts"
TASK_ID = "P2-E4-E6-REDESIGN-S1-v1"
TASK_ROOT = ARTIFACT_ROOT / "phase-payloads/p2/e4_e6_redesign_s1_v1" / TASK_ID
COMMON = REPO / "configs/p2/e4_e6_redesign_s1_v1/s1_v1.yaml"
ARMS6 = "['FUSED_VIS_CONF','A1_E4_STATIC','A2_E4_ALPHA','A3_E5_F1','A4_E5_F1F2','A5_E4_W2X']"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


full_e4 = load_module("full_e4_runner_for_s1_readout", REPO / "scripts/p2/e4_local_4906982_55v_als_prior_v1/run.py")
base = full_e4.base
base.TASK_ID = TASK_ID
base.TASK_ROOT = TASK_ROOT
base.GPU = "0"
base.ARMS = ("FUSED_VIS_CONF", "A1_E4_STATIC", "A2_E4_ALPHA", "A3_E5_F1", "A4_E5_F1F2", "A5_E4_W2X")
base.REPLICAS = ("R1",)
base.CHECKPOINTS = (7000, 12000, 15000, 20000)


def _record_operation(label: str, argv: list[str], rc: int, started: str, ended: str) -> None:
    path = TASK_ROOT / "provenance_readout.json"
    if not path.is_file():
        path.write_text(json.dumps({"schema": "jointbuildgs.p2.e4_e6_redesign_s1_v1.readout_provenance.v1", "task_id": TASK_ID, "commands": [], "return_codes": [], "scientific_verdict": None}, indent=2) + "\n", encoding="utf-8")
    body = json.loads(path.read_text(encoding="utf-8"))
    body["commands"].append({"label": label, "argv": [str(x) for x in argv], "started_utc": started, "ended_utc": ended})
    body["return_codes"].append({"label": label, "return_code": rc})
    path.write_text(json.dumps(body, indent=2, sort_keys=True) + "\n", encoding="utf-8")


base.record_operation = _record_operation


def ensure_task_owner() -> None:
    subprocess.run(
        base.docker_base() + ["chown", "-R", f"{os.getuid()}:{os.getgid()}", base.container_path(TASK_ROOT)],
        check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )


def adapt6(code: str) -> str:
    result = code.replace("['MVC0','MVC05']", ARMS6)
    result = result.replace("['R1','R2','R3']", "['R1']")
    result = result.replace("replicas=['R1','R2','R3']", "replicas=['R1']").replace("reps=['R1','R2','R3']", "reps=['R1']")
    result = result.replace("mvc0_r1.yaml", "fused_vis_conf_r1.yaml")
    result = result.replace("mvc_weight=0.0 if arm=='MVC0' or step<=7000 else .5", "mvc_weight=0.0 if step<=7000 else .5")
    result = result.replace(
        "'metric/psnr_train','eval/psnr','loss/mvc'",
        "'metric/psnr_train','eval/psnr','loss/depth','loss_weight/depth','loss/mvc','loss/external_als_depth_huber','loss/external_als_normal_sign_invariant','stats/external_als_depth_valid_pixel_count'",
    )
    # Keep the legacy two-arm paired delta alive as CONTROL vs A1; the real
    # six-arm comparison is aggregated separately from the per-row metrics.
    result = result.replace("records[('MVC0',rep,step)]", "records[('FUSED_VIS_CONF',rep,step)]")
    result = result.replace("records[('MVC05',rep,step)]", "records[('A1_E4_STATIC',rep,step)]")
    result = result.replace("'MVC0'", "'FUSED_VIS_CONF'").replace("'MVC05'", "'A1_E4_STATIC'")
    result = result.replace("MVC05", "A1_E4_STATIC").replace("MVC0", "FUSED_VIS_CONF")
    result = result.replace("mvc05_minus_mvc0", "a1_minus_control").replace("paired_mvc05_minus_mvc0", "paired_a1_minus_control")
    result = result.replace("'replicates_per_arm':3", "'replicates_per_arm':1").replace("ddof=1", "ddof=0")
    result = result.replace("def mean(v):return sum(v)/len(v)", "def mean(v):return None if not v else sum(v)/len(v)")
    result = result.replace("def sd(v):return statistics.stdev(v) if len(v)>1 else 0.0", "def sd(v):return None if not v else (statistics.stdev(v) if len(v)>1 else 0.0)")
    return result


def prepare_control_proxy() -> None:
    common = yaml.safe_load(COMMON.read_text(encoding="utf-8"))
    source_run = ARTIFACT_ROOT / common["source_run"]
    root = TASK_ROOT / "arms/FUSED_VIS_CONF/R1"
    for relative in ("ckpt", "tb"):
        (root / relative).mkdir(parents=True, exist_ok=True)
    for step in base.CHECKPOINTS:
        for suffix in (".pt", ".pt.sha256"):
            source = source_run / "ckpt" / f"step_{step:06d}{suffix}"
            target = root / "ckpt" / source.name
            if not source.is_file():
                raise FileNotFoundError(source)
            if target.is_symlink():
                if target.resolve() != source.resolve():
                    raise RuntimeError(f"control proxy drift: {target}")
            elif target.exists():
                raise RuntimeError(f"control proxy collision: {target}")
            else:
                target.symlink_to(os.path.relpath(source, target.parent))
    for source in sorted((source_run / "tb").glob("events*")):
        target = root / "tb" / source.name
        if not target.exists() and not target.is_symlink():
            target.symlink_to(os.path.relpath(source, target.parent))
    cfg = yaml.safe_load((REPO / common["base_training_config"]).read_text(encoding="utf-8"))
    cfg.update(yaml.safe_load((REPO / common["fused_arm_config"]).read_text(encoding="utf-8"))["overrides"])
    cfg.update({"task_id": TASK_ID, "run_id": "FUSED_VIS_CONF_R1_REUSED_CONTROL", "out_dir": base.container_path(root), "full_state_resume": "off", "scientific_verdict": None})
    config_path = TASK_ROOT / "control/runtime_configs/fused_vis_conf_r1.yaml"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(yaml.safe_dump(cfg, sort_keys=False), encoding="utf-8")
    source_receipt = json.loads((ARTIFACT_ROOT / common["source_run"]).parent.parent.parent.joinpath("control/receipts/train_FUSED_VIS_CONF_R1.json").read_text(encoding="utf-8"))
    source_receipt.update({"reused_control": True, "source_run": str(source_run), "scientific_verdict": None})
    receipt_path = TASK_ROOT / "control/receipts/train_FUSED_VIS_CONF_R1.json"
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(json.dumps(source_receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("proxy", "analyze", "stage3", "finalize", "all"))
    args = parser.parse_args()
    base.ANALYZE_CODE = adapt6(base.ANALYZE_CODE)
    base.STAGE3_PREP_CODE = adapt6(base.STAGE3_PREP_CODE)
    base.STAGE3_VERIFY_CODE = adapt6(base.STAGE3_VERIFY_CODE)
    base.ROOFER_RECORD_CODE = adapt6(base.ROOFER_RECORD_CODE)
    base.FINALIZE_CODE = adapt6(base.FINALIZE_CODE)
    steps: dict[str, Any] = {
        "proxy": prepare_control_proxy,
        "analyze": base.analyze_checkpoints,
        "stage3": base.run_stage3,
        "finalize": base.finalize_measurements,
    }
    order = ("proxy", "analyze", "stage3", "finalize") if args.command == "all" else (args.command,)
    for name in order:
        print(f"[s1-readout] {name} ...", flush=True)
        steps[name]()
        ensure_task_owner()
        print(f"[s1-readout] {name} done", flush=True)


if __name__ == "__main__":
    main()
