#!/usr/bin/env python3
"""Idempotent orchestration for confidence-gated fused-normal supervision."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import types

import yaml


REPO = Path(__file__).resolve().parents[3]
ARTIFACT_ROOT = REPO.parent / "JointBuildGS-artifacts"
TASK_ID = "P2-E3-LOCAL-4906982-FUSED-NORMAL-CONFIDENCE-v1"
TASK_ROOT = ARTIFACT_ROOT / "phase-payloads/p2/e3_local_4906982_fused_normal_confidence_v1" / TASK_ID
TEMPLATE = REPO / "scripts/p2/e3_local_4906982_fused_surface_normal_v1/run.py"
COMMON_TASK = ARTIFACT_ROOT / "phase-payloads/p2/e3_local_4906982_fused_dn_common_support_v1/P2-E3-LOCAL-4906982-FUSED-DN-COMMON-SUPPORT-v1"
FIXED_TASK = ARTIFACT_ROOT / "phase-payloads/p2/e3_local_4906982_fused_surface_normal_v1/P2-E3-LOCAL-4906982-FUSED-SURFACE-NORMAL-v1"


def transformed() -> types.ModuleType:
    source = TEMPLATE.read_text()
    replacements = (
        ("P2-E3-LOCAL-4906982-FUSED-SURFACE-NORMAL-v1", TASK_ID),
        ("e3_local_4906982_fused_surface_normal_v1", "e3_local_4906982_fused_normal_confidence_v1"),
        ("FUSED_VIS_CONF_FUSED_NORMAL", "FUSED_VIS_CONF_FUSED_NORMAL_CONFIDENCE"),
        ("fused_depth_surface_normal.yaml", "fused_depth_normal_confidence.yaml"),
        ("fused_surface_normal_target_definition.json", "fused_normal_confidence_definition.json"),
        ("raw_native_fused_metrics.csv", "normal_confidence_mask_metrics.csv"),
        ("prepare_targets.py", "prepare_targets.py"),
    )
    for old, new in replacements:
        if old not in source:
            raise RuntimeError(f"upstream runner contract drift: {old}")
        source = source.replace(old, new)
    module = types.ModuleType("fused_normal_confidence_core")
    module.__file__ = __file__; module.__name__ = "fused_normal_confidence_core"
    exec(compile(source, str(TEMPLATE), "exec"), module.__dict__)
    return module


core = transformed()
runner = core.runner
base = runner.base


def prepare_targets() -> None:
    for relative in ("logs", "control", "representative_images"):
        (TASK_ROOT / relative).mkdir(parents=True, exist_ok=True)
    provenance = TASK_ROOT / "provenance.json"
    if not provenance.is_file():
        base.atomic_json(provenance, {
            "schema": "jointbuildgs.p2.e3_local_4906982_fused_normal_confidence_v1.provenance.v1",
            "task_id": TASK_ID, "started_utc": base.now(), "ended_utc": None,
            "commands": [], "return_codes": [], "scientific_verdict": None,
        })
    argv = base.docker_base() + ["python", "/workspace/JointBuildGS/scripts/p2/e3_local_4906982_fused_normal_confidence_v1/prepare_targets.py"]
    log = TASK_ROOT / "logs/prepare_targets.log"; started = base.now()
    with log.open("w") as stream:
        process = subprocess.run(argv, text=True, stdout=stream, stderr=subprocess.STDOUT)
    base.record_operation("prepare_fused_normal_confidence_targets", argv, process.returncode, started, base.now())
    if process.returncode:
        raise RuntimeError(f"mask/target gate failed; inspect {log}")
    print((TASK_ROOT / "fused_normal_confidence_definition.json").read_text())


def preflight() -> None:
    runner.preflight()
    common_config = yaml.safe_load((REPO / "configs/p2/e3_local_4906982_fused_dn_common_support_v1/fused_depth_normal_common_support.yaml").read_text())["overrides"]
    target_config = yaml.safe_load((REPO / "configs/p2/e3_local_4906982_fused_normal_confidence_v1/fused_depth_normal_confidence.yaml").read_text())["overrides"]
    changed = sorted(key for key in set(common_config) | set(target_config) if common_config.get(key) != target_config.get(key))
    allowed = sorted(("task_id", "run_id", "data_root", "out_dir", "normal_dir"))
    gate = {
        "schema": "jointbuildgs.p2.e3_local_4906982_fused_normal_confidence_v1.primary_config_gate.v1",
        "comparison": "common fused-normal support to confidence-gated fused-normal support",
        "changed_override_keys": changed, "allowed_override_keys": allowed,
        "passed": changed == allowed, "scientific_verdict": None,
    }
    base.atomic_json(TASK_ROOT / "control/primary_config_equality_gate.json", gate)
    if not gate["passed"]:
        raise RuntimeError(f"primary config equality gate failed: {changed} != {allowed}")
    definition = json.loads((TASK_ROOT / "fused_normal_confidence_definition.json").read_text())
    diff = "\n".join((
        "context control: existing FUSED_VIS_CONF/R1 (fused depth only)",
        "primary comparison: read-only FUSED_VIS_CONF_FUSED_NORMAL_COMMON_SUPPORT/R1 versus new FUSED_VIS_CONF_FUSED_NORMAL_CONFIDENCE/R1",
        "branch: exact FUSED_VIS_CONF full-state checkpoint at completed update 7000",
        "single scientific intervention in primary comparison: fused-normal binary mask only",
        "depth target/mask: unchanged frozen FUSED_VIS_CONF OpenMVS camera-Z",
        "normal target values: unchanged first-hit fused-mesh triangle normals on retained pixels",
        "normal mask: M_depth AND native-valid/agreement<=15deg AND local-normal<=15deg AND local-depth-range<=1m AND 1px support erosion",
        "unchanged: initialization/history through 7k, losses/weights/schedules, expected depth, MVC, NC, densification, 55 views, seed, GPU",
        "LoD2 Z/RoofSurface/roof type training use: none", "scientific_verdict: null", "",
    ))
    base.atomic_text(TASK_ROOT / "config_diff.txt", diff)
    contract_path = TASK_ROOT / "experiment_contract.json"; contract = json.loads(contract_path.read_text())
    contract.update({
        "schema": "jointbuildgs.p2.e3_local_4906982_fused_normal_confidence_v1.contract.v1",
        "question": "Does a frozen quantity-specific confidence mask make fused surface-normal supervision improve usable geometry and Roofer read-out?",
        "comparison": {"context_control": "FUSED_VIS_CONF/R1", "read_only_common_support": "FUSED_VIS_CONF_FUSED_NORMAL_COMMON_SUPPORT/R1", "intervention": "FUSED_VIS_CONF_FUSED_NORMAL_CONFIDENCE/R1"},
        "single_intervention": "fused normal mask only", "depth_target_or_mask_changed": False,
        "normal_target_values_changed_on_retained_pixels": False, "normal_mask_pixels": definition["target_valid_pixels"],
        "training_experiments_started": 0, "scientific_verdict": None,
    })
    base.atomic_json(contract_path, contract)
    inputs_path = TASK_ROOT / "input_hashes.json"; inputs = json.loads(inputs_path.read_text())
    inputs.update({
        "read_only_common_support_task": {"path": str(COMMON_TASK / "input_hashes.json"), "sha256": core.sha256(COMMON_TASK / "input_hashes.json")},
        "read_only_fixed_mask_task": {"path": str(FIXED_TASK / "input_hashes.json"), "sha256": core.sha256(FIXED_TASK / "input_hashes.json")},
        "mask_visualization_receipt": {"path": str(TASK_ROOT / "mask_visualization_receipt.json"), "sha256": core.sha256(TASK_ROOT / "mask_visualization_receipt.json")},
    })
    base.atomic_json(inputs_path, inputs)
    base.atomic_text(TASK_ROOT / "NOTES.md", f"# {TASK_ID}\n\nStatus: `PREFLIGHT_BOUND`. Mask overlays were frozen before one new confidence-gated arm.\n\nscientific_verdict: null\n")
    print(diff, end="")


def build_mask_viewer() -> None:
    argv = base.docker_base() + ["python", "/workspace/JointBuildGS/scripts/p2/e3_local_4906982_fused_normal_confidence_v1/build_mask_viewer.py"]
    started = base.now(); process = subprocess.run(argv, text=True, capture_output=True)
    (TASK_ROOT / "logs/build_mask_viewer.log").write_text(process.stdout + process.stderr)
    base.record_operation("build_pretraining_mask_viewer", argv, process.returncode, started, base.now())
    if process.returncode:
        raise RuntimeError("mask viewer publication failed")
    print(process.stdout)


def fork_7k() -> None:
    runner.fork_7k()
    new = runner.RUN_ROOT / "ckpt/step_007000.pt"
    comparisons = {
        "depth_only": runner.SOURCE_CHECKPOINT,
        "common_support": COMMON_TASK / "arms/FUSED_VIS_CONF_FUSED_NORMAL_COMMON_SUPPORT/R1/ckpt/step_007000.pt",
        "fixed_mask": FIXED_TASK / "arms/FUSED_VIS_CONF_FUSED_NORMAL/R1/ckpt/step_007000.pt",
    }
    code = r'''import json,sys,torch
from pathlib import Path
import numpy as np
new=Path(sys.argv[1]);out=Path(sys.argv[2]);others={k:Path(v) for k,v in (x.split('=',1) for x in sys.argv[3:])};N=torch.load(new,map_location='cpu',weights_only=False)
def eq(x,y):
 if torch.is_tensor(x) and torch.is_tensor(y):return x.dtype==y.dtype and x.shape==y.shape and torch.equal(x,y)
 if isinstance(x,np.ndarray) and isinstance(y,np.ndarray):return x.dtype==y.dtype and x.shape==y.shape and np.array_equal(x,y,equal_nan=True)
 if isinstance(x,dict) and isinstance(y,dict):return set(x)==set(y) and all(eq(x[k],y[k]) for k in x)
 if isinstance(x,(list,tuple)) and isinstance(y,(list,tuple)):return type(x)==type(y) and len(x)==len(y) and all(eq(a,b) for a,b in zip(x,y))
 return type(x)==type(y) and x==y
sections=['model','optimizers','strategy','grouping_state','rng_state','loss_log_cursor','learning_runs_started'];rows={}
for name,path in others.items():
 O=torch.load(path,map_location='cpu',weights_only=False);rows[name]={k:eq(N[k],O[k]) for k in sections}
passed=all(all(v.values()) for v in rows.values());body={'schema':'jointbuildgs.p2.e3_local_4906982_fused_normal_confidence_v1.state_gate.v1','completed_updates':7000,'comparisons':rows,'passed':passed,'scientific_verdict':None};out.write_text(json.dumps(body,indent=2,sort_keys=True)+'\n');print(json.dumps(body,indent=2));raise SystemExit(0 if passed else 2)'''
    output = TASK_ROOT / "control/primary_state_gate_7000.json"
    argv = base.docker_base() + ["python", "-c", code, runner.container_path(new), runner.container_path(output)] + [f"{key}={runner.container_path(value)}" for key, value in comparisons.items()]
    started = base.now(); process = subprocess.run(argv, text=True, capture_output=True)
    (TASK_ROOT / "logs/primary_7k_equality.log").write_text(process.stdout + process.stderr)
    base.record_operation("primary_7k_equality", argv, process.returncode, started, base.now())
    if process.returncode:
        raise RuntimeError("7k exact-state comparison failed")
    print(output.read_text())


def main() -> None:
    choices = ("prepare-targets", "preflight", "build-mask-viewer", "binding-probe", "smoke", "fork-7k", "train-to-12k", "dose-gate", "train", "analyze-checkpoints", "stage3", "mvs-surface-audit", "finalize-measurements")
    parser = argparse.ArgumentParser(); parser.add_argument("command", choices=choices); command = parser.parse_args().command
    if command == "prepare-targets": prepare_targets()
    elif command == "preflight": preflight()
    elif command == "build-mask-viewer": build_mask_viewer()
    elif command == "fork-7k": fork_7k()
    else: getattr(runner, command.replace("-", "_"))()


if __name__ == "__main__":
    main()
