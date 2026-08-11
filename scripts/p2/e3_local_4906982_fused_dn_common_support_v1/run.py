#!/usr/bin/env python3
"""Thin idempotent orchestration for the fused depth/normal common-support arm."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import types
import yaml


REPO = Path(__file__).resolve().parents[3]
ARTIFACT_ROOT = REPO.parent / "JointBuildGS-artifacts"
CURRENT = REPO / "scripts/p2/e3_local_4906982_fused_surface_normal_v1/run.py"
TASK_ID = "P2-E3-LOCAL-4906982-FUSED-DN-COMMON-SUPPORT-v1"
TASK_ROOT = ARTIFACT_ROOT / "phase-payloads/p2/e3_local_4906982_fused_dn_common_support_v1" / TASK_ID
CURRENT_TASK = ARTIFACT_ROOT / "phase-payloads/p2/e3_local_4906982_fused_surface_normal_v1/P2-E3-LOCAL-4906982-FUSED-SURFACE-NORMAL-v1"


def transformed() -> types.ModuleType:
    source = CURRENT.read_text()
    replacements = (
        ("P2-E3-LOCAL-4906982-FUSED-SURFACE-NORMAL-v1", TASK_ID),
        ("e3_local_4906982_fused_surface_normal_v1", "e3_local_4906982_fused_dn_common_support_v1"),
        ("FUSED_VIS_CONF_FUSED_NORMAL", "FUSED_VIS_CONF_FUSED_NORMAL_COMMON_SUPPORT"),
        ("fused_depth_surface_normal.yaml", "fused_depth_normal_common_support.yaml"),
        ("fused_surface_normal_target_definition.json", "fused_dn_common_support_target_definition.json"),
        ("raw_native_fused_metrics.csv", "fused_dn_common_support_metrics.csv"),
        ("primary comparison: existing FUSED_VIS_CONF_MVS_NORMAL/R1 versus new", "primary comparison: existing FUSED_VIS_CONF_FUSED_NORMAL/R1 versus new"),
        ("single scientific intervention in primary comparison: normal target only", "single scientific intervention in primary comparison: normal mask coverage only"),
        ("raw-normal arm target: COLMAP geometric normal on exact frozen FUSED_VIS_CONF mask", "fixed-mask arm: fused surface normal on support intersected with raw-normal validity"),
        ("fused-normal arm target: world primitive normal of the exact first-hit OpenMVS mesh triangle on the exact prior raw-normal valid mask", "common-support arm: the same fused surface normal on every frozen FUSED_VIS_CONF supported pixel"),
        ("unchanged: initialization/history through 7k, fused depth target/mask/L1/weight/schedule, expected rendered depth, normal weight/schedule/orientation, MVC, NC, densification, 55 views, seed, GPU", "unchanged: initialization/history through 7k, fused depth target/mask/L1/weight/schedule, fused normal values on common pixels, expected rendered depth, normal loss/weight/schedule/orientation, MVC, NC, densification, 55 views, seed, GPU"),
        ("Does changing only the supported normal target from raw COLMAP to the exact fused-mesh first-hit surface normal improve usable geometry and Roofer read-out?", "Does expanding the same fused surface normal target from raw-valid support to the complete frozen FUSED_VIS_CONF depth support improve usable geometry and Roofer read-out?"),
        ('"single_intervention_primary_comparison": "normal target: raw per-view COLMAP to fused mesh surface"', '"single_intervention_primary_comparison": "normal mask: raw-valid intersection to full frozen fused-supported depth mask"'),
        ('"read_only_raw_normal_task"', '"read_only_fixed_mask_task"'),
    )
    for old, new in replacements:
        if old not in source:
            raise RuntimeError(f"upstream runner contract drift: {old}")
        source = source.replace(old, new)
    old_source = 'SOURCE_RAW_NORMAL = ARTIFACT_ROOT / "phase-payloads/p2/e3_local_4906982_mvs_normal_ablation_v1/P2-E3-LOCAL-4906982-MVS-NORMAL-ABLATION-v1"'
    new_source = 'SOURCE_RAW_NORMAL = ARTIFACT_ROOT / "phase-payloads/p2/e3_local_4906982_fused_surface_normal_v1/P2-E3-LOCAL-4906982-FUSED-SURFACE-NORMAL-v1"'
    if old_source not in source:
        raise RuntimeError("fixed-mask comparator binding drift")
    source = source.replace(old_source, new_source)
    module = types.ModuleType("fused_dn_common_support_runner")
    module.__file__ = __file__
    module.__name__ = "fused_dn_common_support_runner"
    exec(compile(source, str(CURRENT), "exec"), module.__dict__)
    return module


runner = transformed()


def reuse_native() -> None:
    source = CURRENT_TASK / "control/native_normal_extraction_receipt.json"
    normals = sorted((CURRENT_TASK / "native_dmap_normal").glob("*.normal.npy"))
    if len(normals) != 55 or not source.is_file() or not json.loads(source.read_text()).get("passed"):
        raise RuntimeError("audited native normal reuse gate failed")
    (TASK_ROOT / "logs").mkdir(parents=True, exist_ok=True)
    provenance = TASK_ROOT / "provenance.json"
    if not provenance.is_file():
        runner.runner.base.atomic_json(provenance, {
            "schema": "jointbuildgs.p2.e3_local_4906982_fused_dn_common_support_v1.provenance.v1",
            "task_id": TASK_ID, "started_utc": runner.runner.base.now(), "ended_utc": None,
            "commands": [], "return_codes": [], "scientific_verdict": None,
        })
    target = TASK_ROOT / "control/native_normal_extraction_receipt.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    runner.runner.base.atomic_json(target, {
        "schema": "jointbuildgs.p2.e3_local_4906982_fused_dn_common_support_v1.native_reuse.v1",
        "source_receipt": str(source), "source_receipt_sha256": runner.sha256(source),
        "count": len(normals), "regenerated": False, "passed": True, "scientific_verdict": None,
    })


runner.extract_native = reuse_native


def fork_7k() -> None:
    runner.runner.fork_7k()
    fixed = CURRENT_TASK / "arms/FUSED_VIS_CONF_FUSED_NORMAL/R1/ckpt/step_007000.pt"
    common = TASK_ROOT / "arms/FUSED_VIS_CONF_FUSED_NORMAL_COMMON_SUPPORT/R1/ckpt/step_007000.pt"
    receipt = TASK_ROOT / "control/primary_common_state_gate_7000.json"
    code = r'''import json,sys,torch
from pathlib import Path
import numpy as np
a,b,out=map(Path,sys.argv[1:]);A=torch.load(a,map_location='cpu',weights_only=False);B=torch.load(b,map_location='cpu',weights_only=False)
def eq(x,y):
 if torch.is_tensor(x) and torch.is_tensor(y):return x.dtype==y.dtype and x.shape==y.shape and torch.equal(x,y)
 if isinstance(x,np.ndarray) and isinstance(y,np.ndarray):return x.dtype==y.dtype and x.shape==y.shape and np.array_equal(x,y,equal_nan=True)
 if isinstance(x,dict) and isinstance(y,dict):return set(x)==set(y) and all(eq(x[k],y[k]) for k in x)
 if isinstance(x,(list,tuple)) and isinstance(y,(list,tuple)):return type(x)==type(y) and len(x)==len(y) and all(eq(i,j) for i,j in zip(x,y))
 return type(x)==type(y) and x==y
sections=['model','optimizers','strategy','grouping_state','rng_state','loss_log_cursor','learning_runs_started'];same={k:eq(A[k],B[k]) for k in sections}
body={'schema':'jointbuildgs.p2.e3_local_4906982_fused_dn_common_support_v1.primary_common_state_gate.v1','completed_updates':7000,'fixed_mask_checkpoint':str(a),'common_support_checkpoint':str(b),'learned_sections_equal':same,'passed':all(same.values()),'scientific_verdict':None};out.write_text(json.dumps(body,indent=2,sort_keys=True)+'\n');print(json.dumps(body,indent=2));raise SystemExit(0 if body['passed'] else 2)'''
    cpath = lambda path: str(path).replace(str(ARTIFACT_ROOT), "/artifacts/JointBuildGS", 1)
    argv = runner.runner.base.docker_base() + ["python", "-c", code, cpath(fixed), cpath(common), cpath(receipt)]
    started = runner.runner.base.now(); process = subprocess.run(argv, text=True, capture_output=True)
    (TASK_ROOT / "logs/primary_7k_equality.log").write_text(process.stdout + process.stderr)
    runner.runner.base.record_operation("primary_7k_equality", argv, process.returncode, started, runner.runner.base.now())
    if process.returncode:
        raise RuntimeError("direct fixed-mask/common-support 7k equality failed")
    print(receipt.read_text())


def preflight() -> None:
    runner.preflight()
    fixed_config = yaml.safe_load((REPO / "configs/p2/e3_local_4906982_fused_surface_normal_v1/fused_depth_surface_normal.yaml").read_text())["overrides"]
    common_config = yaml.safe_load((REPO / "configs/p2/e3_local_4906982_fused_dn_common_support_v1/fused_depth_normal_common_support.yaml").read_text())["overrides"]
    changed = sorted(key for key in set(fixed_config) | set(common_config) if fixed_config.get(key) != common_config.get(key))
    allowed = sorted(("task_id", "run_id", "data_root", "out_dir", "normal_dir"))
    config_gate = {
        "schema": "jointbuildgs.p2.e3_local_4906982_fused_dn_common_support_v1.primary_config_gate.v1",
        "comparison": "FUSED_VIS_CONF_FUSED_NORMAL to FUSED_VIS_CONF_FUSED_NORMAL_COMMON_SUPPORT",
        "changed_override_keys": changed, "allowed_override_keys": allowed,
        "passed": changed == allowed, "scientific_verdict": None,
    }
    runner.runner.base.atomic_json(TASK_ROOT / "control/primary_config_equality_gate.json", config_gate)
    if not config_gate["passed"]:
        raise RuntimeError(f"primary config equality gate failed: {changed} != {allowed}")
    definition = json.loads((TASK_ROOT / "fused_dn_common_support_target_definition.json").read_text())
    contract_path = TASK_ROOT / "experiment_contract.json"
    contract = json.loads(contract_path.read_text())
    contract.update({
        "question": "Does expanding the same fused surface normal target to the complete frozen fused-supported depth mask improve usable geometry and Roofer read-out?",
        "comparison": {"read_only_fixed_mask": "FUSED_VIS_CONF_FUSED_NORMAL/R1", "intervention": "FUSED_VIS_CONF_FUSED_NORMAL_COMMON_SUPPORT/R1"},
        "single_intervention": "fused normal mask coverage only", "normal_target_changed": False,
        "depth_target_or_mask_changed": False, "scientific_verdict": None,
        "fixed_mask_pixels": definition["prior_raw_normal_target_valid_pixels"],
        "common_depth_normal_mask_pixels": definition["target_valid_pixels"],
    })
    runner.runner.base.atomic_json(contract_path, contract)
    runner.runner.base.atomic_text(TASK_ROOT / "NOTES.md", f"# {TASK_ID}\n\nStatus: `PREFLIGHT_BOUND`. One new common-support arm; prior fixed-mask fused-normal arm is read-only.\n\nscientific_verdict: null\n")


def main() -> None:
    choices = ("prepare-targets", "preflight", "binding-probe", "smoke", "fork-7k", "train-to-12k", "dose-gate", "train", "analyze-checkpoints", "stage3", "mvs-surface-audit", "finalize-measurements")
    command = argparse.ArgumentParser()
    command.add_argument("command", choices=choices)
    value = command.parse_args().command
    if value == "prepare-targets":
        reuse_native(); runner.prepare_targets()
    elif value == "preflight":
        preflight()
    elif value == "fork-7k":
        fork_7k()
    else:
        getattr(runner.runner, value.replace("-", "_"))()


if __name__ == "__main__":
    main()
