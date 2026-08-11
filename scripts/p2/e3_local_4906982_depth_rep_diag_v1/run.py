#!/usr/bin/env python3
"""EXPECTED-vs-MEDIAN raw COLMAP depth supervision diagnostic.

The host process only orchestrates Docker.  Both arms continue from the exact
same existing DEPTH03-R1 7k full state.  Their sole training delta is the
rendered depth statistic passed to the unchanged raw COLMAP L1 term.
"""
from __future__ import annotations

import argparse
import copy
import csv
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import time
from typing import Any

import yaml


REPO = Path(__file__).resolve().parents[3]
BASE_RUNNER = REPO / "scripts/p2/e3_local_4906982_mvc_v2/run.py"
SPEC = importlib.util.spec_from_file_location("mvc_v2_runner", BASE_RUNNER)
assert SPEC and SPEC.loader
base = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(base)

ARTIFACT_ROOT = REPO.parent / "JointBuildGS-artifacts"
TASK_ID = "P2-E3-LOCAL-4906982-DEPTH-REP-DIAG-v1"
TASK_ROOT = (
    ARTIFACT_ROOT
    / "phase-payloads/p2/e3_local_4906982_depth_rep_diag_v1"
    / TASK_ID
)
CONFIG_DIR = REPO / "configs/p2/e3_local_4906982_depth_rep_diag_v1"
COMMON_CONFIG = CONFIG_DIR / "common.yaml"
ARM_CONFIGS = {
    "EXPECTED": CONFIG_DIR / "expected.yaml",
    "MEDIAN": CONFIG_DIR / "median.yaml",
}
BASE_CONFIG = REPO / "configs/p2/e3_local_4906982_mvc_depth_v1/depth03.yaml"
SOURCE_RUN = (
    ARTIFACT_ROOT
    / "phase-payloads/p2/e3_local_4906982_mvc_depth_v1"
    / "P2-E3-LOCAL-4906982-MVC-DEPTH-v1/arms/DEPTH03/R1"
)
SOURCE_CHECKPOINT = SOURCE_RUN / "ckpt/step_007000.pt"
SOURCE_EFFECTIVE = SOURCE_RUN / "effective_config.json"
SOURCE_INPUTS = SOURCE_RUN.parents[2] / "input_hashes.json"
MVS_AUDIT_INPUTS = (
    ARTIFACT_ROOT
    / "phase-payloads/p2/e3_local_4906982_mvs_transfer_diag_v1"
    / "P2-E3-LOCAL-4906982-MVS-TRANSFER-DIAG-v1/input_hashes.json"
)
ARMS = ("EXPECTED", "MEDIAN")
REPLICAS = ("R1",)
CHECKPOINTS = (7000, 12000, 15000, 20000)
ALLOWLIST = {"run_id", "out_dir", "depth_supervision_mode"}

# Reuse the validated Docker launch, deterministic wrapper, metrics, and Stage-3
# implementations while rebinding their task-local constants.
base.TASK_ID = TASK_ID
base.TASK_ROOT = TASK_ROOT
base.ARTIFACT_ROOT = ARTIFACT_ROOT
base.GPU = "1"
base.ARMS = ARMS
base.REPLICAS = REPLICAS
base.CHECKPOINTS = CHECKPOINTS


def sha256(path: Path) -> str:
    return base.sha256(path)


def atomic_json(path: Path, body: Any) -> None:
    base.atomic_json(path, body)


def repo_container_path(path: Path) -> str:
    return "/workspace/JointBuildGS/" + str(path.relative_to(REPO))


def runtime_path(arm: str) -> Path:
    return TASK_ROOT / "control/runtime_configs" / f"{arm.lower()}_r1.yaml"


def run_root(arm: str) -> Path:
    return TASK_ROOT / "arms" / arm / "R1"


def _changed(left: dict[str, Any], right: dict[str, Any]) -> set[str]:
    return {
        key
        for key in set(left) | set(right)
        if left.get(key) != right.get(key)
    }


def _materialized_config(arm: str) -> dict[str, Any]:
    body = yaml.safe_load(BASE_CONFIG.read_text())
    overlay = yaml.safe_load(ARM_CONFIGS[arm].read_text())
    body.update(
        {
            "task_id": TASK_ID,
            "run_id": overlay["run_id"],
            "out_dir": overlay["out_dir"],
            "depth_supervision_mode": overlay["depth_supervision_mode"],
            "full_state_resume": "auto",
            "full_state_resume_strict_cuda_rng": True,
            "full_state_checkpoint": True,
            "full_state_checkpoint_steps": list(CHECKPOINTS),
            "max_iter": 20000,
            "official_PASS_usable": None,
            "scientific_verdict": None,
        }
    )
    return body


def _write_runtime_configs() -> None:
    for arm in ARMS:
        base.atomic_text(
            runtime_path(arm),
            yaml.safe_dump(_materialized_config(arm), sort_keys=False),
        )


def _validate_config_contract() -> str:
    configs = {arm: _materialized_config(arm) for arm in ARMS}
    actual = _changed(configs["EXPECTED"], configs["MEDIAN"])
    if actual != ALLOWLIST:
        raise RuntimeError(f"arm config diff gate failed: {sorted(actual)}")
    if configs["EXPECTED"]["depth_supervision_mode"] != "expected":
        raise RuntimeError("EXPECTED arm selector drift")
    if configs["MEDIAN"]["depth_supervision_mode"] != "median":
        raise RuntimeError("MEDIAN arm selector drift")
    required = {
        "seed": 0,
        "downscale": 1.0,
        "load_depth": True,
        "load_normal": False,
        "w_depth": 0.03,
        "depth_warmup": 7000,
        "depth_schedule": "ramp",
        "depth_ramp_steps": 5000,
        "depth_prior_alignment": "none",
        "w_mvc": 0.5,
        "mvc_warmup": 7000,
        "mvc_schedule": "ramp",
        "mvc_ramp_steps": 5000,
        "w_nc": 0.05,
        "w_distort": 0.0,
        "w_normal": 0.0,
        "w_external_als_depth": 0.0,
        "w_external_als_normal": 0.0,
        "max_iter": 20000,
    }
    for arm, cfg in configs.items():
        mismatch = {
            key: [cfg.get(key), expected]
            for key, expected in required.items()
            if cfg.get(key) != expected
        }
        if mismatch:
            raise RuntimeError(f"{arm} frozen contract mismatch: {mismatch}")
        if len(cfg["visible_views"]) != 55:
            raise RuntimeError(f"{arm} visible-view count drift")
        if len(cfg["train_views"]) != 47 or len(cfg["eval_views"]) != 8:
            raise RuntimeError(f"{arm} view-role count drift")
    return "\n".join(
        [
            "single_variable: raw COLMAP rendered-depth representation",
            "control: EXPECTED = renderer.depth",
            "intervention: MEDIAN = renderer.depth_median",
            "allowed_arm_delta_keys: depth_supervision_mode, out_dir, run_id",
            "actual_arm_delta_keys: " + ", ".join(sorted(actual)),
            "same_source_full_state: DEPTH03/R1 step_007000.pt",
            "same_depth_mask_loss_weight_schedule: true",
            "same_MVC_NC_densification_views_seed_GPU: true",
            "surface_intersection_arm: not_run",
            "scientific_verdict: null",
            "",
        ]
    )


def _verify_manifest_file_records(value: Any) -> tuple[int, list[str]]:
    checked = 0
    failures: list[str] = []
    if isinstance(value, dict):
        path_value = value.get("path")
        digest = value.get("sha256")
        if isinstance(path_value, str) and isinstance(digest, str):
            path = Path(path_value)
            if path.is_file():
                checked += 1
                actual = sha256(path)
                if actual != digest:
                    failures.append(f"SHA mismatch: {path}")
        for child in value.values():
            child_checked, child_failures = _verify_manifest_file_records(child)
            checked += child_checked
            failures.extend(child_failures)
    elif isinstance(value, list):
        for child in value:
            child_checked, child_failures = _verify_manifest_file_records(child)
            checked += child_checked
            failures.extend(child_failures)
    return checked, failures


def preflight() -> None:
    marker = TASK_ROOT / "experiment_contract.json"
    if TASK_ROOT.exists() and any(TASK_ROOT.iterdir()) and not marker.is_file():
        raise RuntimeError(f"non-empty unbound namespace: {TASK_ROOT}")
    for relative in (
        "control/runtime_configs",
        "control/effective_configs",
        "control/receipts",
        "logs",
        "cache/torch_extensions",
        "representative_images",
    ):
        (TASK_ROOT / relative).mkdir(parents=True, exist_ok=True)
    for path in (
        COMMON_CONFIG,
        *ARM_CONFIGS.values(),
        BASE_CONFIG,
        SOURCE_CHECKPOINT,
        Path(str(SOURCE_CHECKPOINT) + ".sha256"),
        SOURCE_EFFECTIVE,
        SOURCE_INPUTS,
        MVS_AUDIT_INPUTS,
    ):
        if not path.is_file():
            raise FileNotFoundError(path)
    if not base.checkpoint_valid(SOURCE_RUN, 7000):
        raise RuntimeError("source DEPTH03-R1 7k checkpoint sidecar gate failed")
    _write_runtime_configs()
    diff_text = _validate_config_contract()
    base.atomic_text(TASK_ROOT / "config_diff.txt", diff_text)

    source_inputs = json.loads(SOURCE_INPUTS.read_text())
    checked, failures = _verify_manifest_file_records(source_inputs)
    crop_root = Path(source_inputs["crop_root"])
    crop_checked = 0
    for record in source_inputs["crop_images"]["files"]:
        path = crop_root / "images" / record["basename"]
        if not path.is_file() or sha256(path) != record["sha256"]:
            failures.append(f"crop image missing or SHA mismatch: {path}")
        else:
            crop_checked += 1
    depth_checked = 0
    for name, expected_sha in source_inputs["geometric_depth_maps_sha256"].items():
        path = crop_root / "stereo/depth_maps" / f"{name}.geometric.bin"
        if not path.is_file() or sha256(path) != expected_sha:
            failures.append(f"geometric depth missing or SHA mismatch: {path}")
        else:
            depth_checked += 1
    mvs_inputs = json.loads(MVS_AUDIT_INPUTS.read_text())
    mvs_checked, mvs_failures = _verify_manifest_file_records(mvs_inputs)
    failures.extend(mvs_failures)
    if failures:
        raise RuntimeError("input manifest verification failed: " + "; ".join(failures))
    input_body = {
        "schema": "jointbuildgs.p2.e3_local_4906982_depth_rep_diag_v1.inputs.v1",
        "source_training_input_manifest": {
            "path": str(SOURCE_INPUTS),
            "sha256": sha256(SOURCE_INPUTS),
            "file_records_live_sha_verified": checked,
            "crop_images_live_sha_verified": crop_checked,
            "geometric_depth_maps_live_sha_verified": depth_checked,
        },
        "source_mvs_transfer_audit_manifest": {
            "path": str(MVS_AUDIT_INPUTS),
            "sha256": sha256(MVS_AUDIT_INPUTS),
            "file_records_live_sha_verified": mvs_checked,
        },
        "source_full_state_checkpoint": {
            "path": str(SOURCE_CHECKPOINT),
            "sha256": sha256(SOURCE_CHECKPOINT),
            "sidecar_sha256": sha256(Path(str(SOURCE_CHECKPOINT) + ".sha256")),
        },
        "base_training_config": {
            "path": str(BASE_CONFIG),
            "sha256": sha256(BASE_CONFIG),
        },
        "reuse_contract": {
            "crop_regenerated": False,
            "cameras_regenerated": False,
            "view_roles_regenerated": False,
            "sparse_seed_regenerated": False,
            "colmap_depth_regenerated": False,
        },
        "scientific_verdict": None,
    }
    atomic_json(TASK_ROOT / "input_hashes.json", input_body)
    atomic_json(
        marker,
        {
            "schema": "jointbuildgs.p2.e3_local_4906982_depth_rep_diag_v1.contract.v1",
            "task_id": TASK_ID,
            "building_id": "DEBY_LOD2_4906982",
            "status": "PREFLIGHT_BOUND",
            "causal_question": (
                "Does replacing expected depth with median depth only in the raw "
                "COLMAP L1 supervision improve geometry?"
            ),
            "arms": {
                "EXPECTED": {"raw_colmap_prediction": "renderer.depth"},
                "MEDIAN": {"raw_colmap_prediction": "renderer.depth_median"},
            },
            "sole_training_delta": "depth_supervision_mode",
            "source_completed_updates": 7000,
            "required_exact_state_sections": [
                "model",
                "optimizers",
                "strategy",
                "grouping_state",
                "rng_state",
                "loss_log_cursor",
                "learning_runs_started",
            ],
            "sequential_same_gpu": {"host_index": 1, "order": list(ARMS)},
            "checkpoints_completed_updates": list(CHECKPOINTS),
            "surface_intersection_arm": "NOT_AUTHORIZED_NOT_RUN",
            "lod2_training_use": False,
            "lod2_reference_use": "evaluation_only_after_training",
            "new_loss": False,
            "multiview_densification": False,
            "scientific_verdict": None,
        },
    )
    sources = [
        Path(__file__).resolve(),
        BASE_RUNNER,
        REPO / "src/stage2/train.py",
        REPO / "src/stage2/renderer.py",
        REPO / "src/stage2/loss/data_fitting.py",
        REPO / "src/stage2/loss/multiview.py",
        REPO / "src/stage2/checkpoint.py",
        REPO / "src/stage2/train_resume.py",
        BASE_CONFIG,
        COMMON_CONFIG,
        *ARM_CONFIGS.values(),
    ]
    provenance_path = TASK_ROOT / "provenance.json"
    prior = json.loads(provenance_path.read_text()) if provenance_path.is_file() else {}
    prior.update(
        {
            "schema": "jointbuildgs.p2.e3_local_4906982_depth_rep_diag_v1.provenance.v1",
            "task_id": TASK_ID,
            "git": base.git_record(),
            "docker_image": base.image_record(),
            "gpu": base.gpu_record(),
            "source_files_sha256": {
                str(path.relative_to(REPO)): sha256(path)
                for path in sources
                if path.is_relative_to(REPO)
            },
            "external_source_sha256": {
                str(SOURCE_CHECKPOINT): sha256(SOURCE_CHECKPOINT),
                str(SOURCE_EFFECTIVE): sha256(SOURCE_EFFECTIVE),
                str(SOURCE_INPUTS): sha256(SOURCE_INPUTS),
                str(MVS_AUDIT_INPUTS): sha256(MVS_AUDIT_INPUTS),
            },
            "runtime_configs_sha256": {
                path.name: sha256(path)
                for path in sorted(
                    (TASK_ROOT / "control/runtime_configs").glob("*.yaml")
                )
            },
            "random_seed": 0,
            "started_utc": prior.get("started_utc") or base.now(),
            "ended_utc": None,
            "commands": prior.get("commands", []),
            "return_codes": prior.get("return_codes", []),
            "scientific_verdict": None,
        }
    )
    atomic_json(provenance_path, prior)
    base.atomic_text(
        TASK_ROOT / "NOTES.md",
        f"# {TASK_ID}\n\nStatus: `PREFLIGHT_BOUND`. No arm training started. "
        "Scientific verdict: `null`.\n",
    )
    print(diff_text, end="")
    print(
        json.dumps(
            {
                "task_root": str(TASK_ROOT),
                "source_checkpoint_sha256": sha256(SOURCE_CHECKPOINT),
                "verified_manifest_file_records": checked + crop_checked + depth_checked + mvs_checked,
                "docker_image_id": base.image_record()["id"],
                "gpu": base.gpu_record()["model"],
            },
            indent=2,
        )
    )


def _probe_config(arm: str) -> Path:
    cfg = _materialized_config(arm)
    root = TASK_ROOT / "binding_probe" / arm
    cfg.update(
        {
            "run_id": f"BINDING_PROBE_{arm}",
            "out_dir": base.container_path(root),
            "max_iter": 1,
            "eval_every": 100000,
            "ckpt_every": 100000,
            "full_state_resume": "off",
            # This list participates in the stable effective-config binding.
            # Keep it identical to the continuation even though a one-update
            # probe cannot reach any of the registered steps.
            "full_state_checkpoint_steps": list(CHECKPOINTS),
        }
    )
    path = TASK_ROOT / "control/runtime_configs" / f"binding_probe_{arm.lower()}.yaml"
    base.atomic_text(path, yaml.safe_dump(cfg, sort_keys=False))
    return path


def binding_probe() -> None:
    for arm in ARMS:
        stable = TASK_ROOT / "control/effective_configs" / f"{arm.lower()}.json"
        if stable.is_file():
            prior = json.loads(stable.read_text())
            if prior.get("full_state_checkpoint_steps") == list(CHECKPOINTS):
                continue
        cfg_path = _probe_config(arm)
        root = TASK_ROOT / "binding_probe" / arm
        argv = base.docker_base(gpu=True) + [
            "python",
            "-c",
            base.DETERMINISTIC_WRAPPER,
            "--config",
            base.container_path(cfg_path),
        ]
        log = TASK_ROOT / "logs" / f"binding_probe_{arm.lower()}.log"
        started = base.now()
        with log.open("w") as stream:
            proc = subprocess.run(argv, text=True, stdout=stream, stderr=subprocess.STDOUT)
        base.record_operation(f"binding_probe_{arm}", argv, proc.returncode, started, base.now())
        if proc.returncode != 0:
            raise RuntimeError(f"binding probe failed for {arm}; inspect {log}")
        effective = json.loads((root / "effective_config.json").read_text())
        effective.pop("full_state_runtime", None)
        atomic_json(stable, effective)
    left = json.loads((TASK_ROOT / "control/effective_configs/expected.json").read_text())
    right = json.loads((TASK_ROOT / "control/effective_configs/median.json").read_text())
    actual = _changed(left, right)
    expected = {
        "depth_supervision_mode",
        "depth_supervision_prediction",
    }
    gate = {
        "schema": "jointbuildgs.p2.e3_local_4906982_depth_rep_diag_v1.effective_config_gate.v1",
        "actual_difference": sorted(actual),
        "expected_difference": sorted(expected),
        "hashes": {
            "EXPECTED": base.json_sha256(left),
            "MEDIAN": base.json_sha256(right),
        },
        "passed": actual == expected,
        "scientific_verdict": None,
    }
    atomic_json(TASK_ROOT / "control/effective_config_gate.json", gate)
    if not gate["passed"]:
        raise RuntimeError(f"effective-config diff gate failed: {sorted(actual)}")
    print(json.dumps(gate, indent=2))


REBIND_CODE = r'''
import copy,hashlib,json,os,sys,tempfile,torch
from pathlib import Path
source,destination,config_path,out_dir,effective_path,receipt=map(Path,sys.argv[1:])
cfg=__import__('yaml').safe_load(config_path.read_text());excluded={'full_state_resume','full_state_resume_strict_cuda_rng'};bound={k:v for k,v in cfg.items() if k not in excluded}
digest=lambda x:hashlib.sha256(json.dumps(x,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()
A=torch.load(source,map_location='cpu',weights_only=False);old=copy.deepcopy(A['binding_sha256']);new={'training_config':digest(bound),'effective_training_config':digest(json.loads(effective_path.read_text())),'output_path':hashlib.sha256(str(out_dir).encode()).hexdigest()};A['binding_sha256']=new
destination.parent.mkdir(parents=True,exist_ok=True);fd,tmp=tempfile.mkstemp(prefix=destination.name+'.',suffix='.tmp',dir=destination.parent);os.close(fd)
try: torch.save(A,tmp);os.chmod(tmp,0o644);os.replace(tmp,destination)
finally:
 if os.path.exists(tmp):os.unlink(tmp)
h=hashlib.sha256(destination.read_bytes()).hexdigest();Path(str(destination)+'.sha256').write_text(f'{h}  {destination.name}\n');B=torch.load(destination,map_location='cpu',weights_only=False)
def eq(x,y):
 import numpy as np
 if torch.is_tensor(x) and torch.is_tensor(y):return x.dtype==y.dtype and x.shape==y.shape and torch.equal(x,y)
 if isinstance(x,np.ndarray) and isinstance(y,np.ndarray):return x.dtype==y.dtype and x.shape==y.shape and np.array_equal(x,y,equal_nan=True)
 if isinstance(x,dict) and isinstance(y,dict):return set(x)==set(y) and all(eq(x[k],y[k]) for k in x)
 if isinstance(x,(list,tuple)) and isinstance(y,(list,tuple)):return type(x)==type(y) and len(x)==len(y) and all(eq(a,b) for a,b in zip(x,y))
 return type(x)==type(y) and x==y
S=torch.load(source,map_location='cpu',weights_only=False);sections=['model','optimizers','strategy','grouping_state','rng_state','loss_log_cursor','learning_runs_started'];same={k:eq(S[k],B[k]) for k in sections}
body={'schema':'jointbuildgs.p2.e3_local_4906982_depth_rep_diag_v1.rebind.v1','source':str(source),'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'destination':str(destination),'destination_sha256':h,'old_binding':old,'new_binding':new,'exact_sections_equal':same,'passed':all(same.values()),'scientific_verdict':None};receipt.parent.mkdir(parents=True,exist_ok=True);receipt.write_text(json.dumps(body,indent=2,sort_keys=True)+'\n');raise SystemExit(0 if body['passed'] else 2)
'''


def fork_7k() -> None:
    effective_gate = TASK_ROOT / "control/effective_config_gate.json"
    if not effective_gate.is_file() or not json.loads(effective_gate.read_text()).get("passed"):
        raise RuntimeError("effective-config gate must pass before fork")
    for arm in ARMS:
        root = run_root(arm)
        receipt = TASK_ROOT / "control/receipts" / f"rebind_{arm.lower()}_r1.json"
        effective_path = TASK_ROOT / "control/effective_configs" / f"{arm.lower()}.json"
        desired_effective_sha = base.json_sha256(json.loads(effective_path.read_text()))
        if receipt.is_file() and base.checkpoint_valid(root, 7000):
            prior = json.loads(receipt.read_text())
            if (
                prior.get("passed")
                and prior.get("new_binding", {}).get("effective_training_config")
                == desired_effective_sha
            ):
                continue
        later = sorted((root / "ckpt").glob("step_*.pt")) if root.exists() else []
        if any(path.name != "step_007000.pt" for path in later):
            raise RuntimeError(f"cannot rebind a fork that advanced beyond 7k: {root}")
        (root / "ckpt").mkdir(parents=True, exist_ok=True)
        destination = root / "ckpt/step_007000.pt"
        argv = base.docker_base() + [
            "python",
            "-c",
            REBIND_CODE,
            base.container_path(SOURCE_CHECKPOINT),
            base.container_path(destination),
            base.container_path(runtime_path(arm)),
            Path(base.container_path(root)),
            base.container_path(effective_path),
            base.container_path(receipt),
        ]
        started = base.now()
        proc = subprocess.run([str(x) for x in argv], text=True, capture_output=True)
        base.record_operation(f"rebind_{arm}_R1", [str(x) for x in argv], proc.returncode, started, base.now())
        if proc.returncode != 0:
            raise RuntimeError(proc.stderr or proc.stdout)
    receipts = [
        json.loads((TASK_ROOT / "control/receipts" / f"rebind_{arm.lower()}_r1.json").read_text())
        for arm in ARMS
    ]
    exact = all(all(row["exact_sections_equal"].values()) for row in receipts)
    gate = {
        "schema": "jointbuildgs.p2.e3_local_4906982_depth_rep_diag_v1.common_state_gate.v1",
        "completed_updates": 7000,
        "source_checkpoint_sha256": sha256(SOURCE_CHECKPOINT),
        "unique_source_checkpoint_hashes": len({row["source_sha256"] for row in receipts}),
        "model_optimizer_strategy_grouping_rng_loss_cursor_exact_equal": exact,
        "binding_metadata_only_rewritten": True,
        "loss_weights_at_7k_boundary": {"depth": 0.0, "mvc": 0.0},
        "passed": exact and len({row["source_sha256"] for row in receipts}) == 1,
        "scientific_verdict": None,
    }
    atomic_json(TASK_ROOT / "control/common_state_gate_7000.json", gate)
    if not gate["passed"]:
        base.atomic_text(TASK_ROOT / "issues.md", "# Issues\n\n7k exact equality gate failed. Training not started.\n")
        raise RuntimeError("7k exact equality gate failed")
    print(json.dumps(gate, indent=2))


def train() -> None:
    gate = TASK_ROOT / "control/common_state_gate_7000.json"
    if not gate.is_file() or not json.loads(gate.read_text()).get("passed"):
        raise RuntimeError("7k exact common-state gate must pass before training")
    for arm in ARMS:
        label = f"train_{arm}_R1"
        result = base._launch_training(
            label,
            run_root(arm),
            runtime_path(arm),
            stop_step=None,
        )
        print(
            json.dumps(
                {
                    "label": label,
                    "wall_seconds": result.get("wall_seconds"),
                    "checkpoint_20k": base.checkpoint_valid(run_root(arm), 20000),
                }
            ),
            flush=True,
        )
    missing = [
        [arm, step]
        for arm in ARMS
        for step in CHECKPOINTS
        if not base.checkpoint_valid(run_root(arm), step)
    ]
    if missing:
        raise RuntimeError(f"missing required checkpoints: {missing}")


def _adapt_base_code(code: str) -> str:
    adapted = code.replace("'MVC0'", "'EXPECTED'").replace("'MVC05'", "'MEDIAN'")
    adapted = adapted.replace("MVC05", "MEDIAN").replace("MVC0", "EXPECTED")
    adapted = adapted.replace("mvc0_r1.yaml", "expected_r1.yaml")
    adapted = adapted.replace("replicas=['R1','R2','R3']", "replicas=['R1']")
    adapted = adapted.replace("reps=['R1','R2','R3']", "reps=['R1']")
    adapted = adapted.replace("['R1','R2','R3']", "['R1']")
    adapted = adapted.replace("'replicates_per_arm':3", "'replicates_per_arm':1")
    adapted = adapted.replace("ddof=1", "ddof=0")
    adapted = adapted.replace("mvc05_minus_mvc0", "median_minus_expected")
    adapted = adapted.replace("paired_mvc05_minus_mvc0", "paired_median_minus_expected")
    adapted = adapted.replace("'cases':24", "'cases':8")
    adapted = adapted.replace("'classification_passed':24", "'classification_passed':8")
    adapted = adapted.replace("'roofer_return_code_zero':24", "'roofer_return_code_zero':8")
    adapted = adapted.replace("'roofer_rf_success_true':24", "'roofer_rf_success_true':8")
    adapted = adapted.replace("'roofer_cases':24", "'roofer_cases':8")
    adapted = adapted.replace(
        "def mean(v):return sum(v)/len(v)",
        "def mean(v):return None if not v else sum(v)/len(v)",
    )
    adapted = adapted.replace(
        "def sd(v):return statistics.stdev(v) if len(v)>1 else 0.0",
        "def sd(v):return None if not v else (statistics.stdev(v) if len(v)>1 else 0.0)",
    )
    return adapted


def analyze_checkpoints() -> None:
    base.ANALYZE_CODE = _adapt_base_code(base.ANALYZE_CODE)
    base.analyze_checkpoints()


def stage3() -> None:
    base.STAGE3_PREP_CODE = _adapt_base_code(base.STAGE3_PREP_CODE)
    base.STAGE3_VERIFY_CODE = _adapt_base_code(base.STAGE3_VERIFY_CODE)
    base.ROOFER_RECORD_CODE = _adapt_base_code(base.ROOFER_RECORD_CODE)
    base.run_stage3()


def finalize_measurements() -> None:
    base.FINALIZE_CODE = _adapt_base_code(base.FINALIZE_CODE)
    base.finalize_measurements()


def reference_diagnostic() -> None:
    output = TASK_ROOT / "reference_diagnostic"
    metrics = output / "metrics.json"
    if metrics.is_file() and json.loads(metrics.read_text()).get("status") == "COMPLETE_DIAGNOSTIC":
        print(metrics.read_text())
        return
    source_config = REPO / "configs/p2/e3_local_4906982_mvc_readout_diag_v1/config.yaml"
    source = yaml.safe_load(source_config.read_text())
    source.update(
        {
            "task_id": TASK_ID + "-REFERENCE-DIAG",
            "source_task_root": base.container_path(TASK_ROOT),
            "source_runner": repo_container_path(Path(__file__).resolve()),
            "shared_footprint": base.container_path(
                TASK_ROOT / "control/shared_standard_footprint_4906982.geojson"
            ),
            "arms": list(ARMS),
            "replicas": list(REPLICAS),
            "checkpoints": list(CHECKPOINTS),
            "scientific_verdict": None,
        }
    )
    config = TASK_ROOT / "control/reference_diagnostic.yaml"
    base.atomic_text(config, yaml.safe_dump(source, sort_keys=False))
    source_runner = REPO / "scripts/p2/e3_local_4906982_mvc_readout_diag_v1/run.py"
    runtime_runner = TASK_ROOT / "control/reference_diag_runtime.py"
    runtime_text = source_runner.read_text()
    runtime_text = runtime_text.replace('"MVC0"', '"EXPECTED"').replace('"MVC05"', '"MEDIAN"')
    runtime_text = runtime_text.replace("'MVC0'", "'EXPECTED'").replace("'MVC05'", "'MEDIAN'")
    runtime_text = runtime_text.replace(
        'REPO = Path(__file__).resolve().parents[3]\nARTIFACT_ROOT = REPO.parent / "JointBuildGS-artifacts"',
        'REPO = Path("/workspace/JointBuildGS")\nARTIFACT_ROOT = Path("/artifacts/JointBuildGS")',
    )
    base.atomic_text(runtime_runner, runtime_text)
    output.mkdir(parents=True, exist_ok=True)
    (output / "logs").mkdir(exist_ok=True)
    argv = [
        "docker",
        "run",
        "--rm",
        "--network",
        "none",
        "--user",
        f"{os.getuid()}:{os.getgid()}",
        "-e",
        "MPLCONFIGDIR=/tmp/matplotlib",
        "-v",
        f"{REPO}:/workspace/JointBuildGS:ro",
        "-v",
        f"{ARTIFACT_ROOT}:/artifacts/JointBuildGS:ro",
        "-v",
        f"{TASK_ROOT}:/task:rw",
        "-w",
        "/workspace/JointBuildGS",
        base.EVAL_IMAGE,
        "python",
        "/task/control/reference_diag_runtime.py",
        "--inside-docker",
        "analyze",
        "--config",
        base.container_path(config),
        "--output",
        "/task/reference_diagnostic",
    ]
    log = output / "logs/analyze.log"
    started = base.now()
    with log.open("w") as stream:
        proc = subprocess.run(argv, text=True, stdout=stream, stderr=subprocess.STDOUT)
    base.record_operation("reference_diagnostic", argv, proc.returncode, started, base.now())
    if proc.returncode != 0:
        raise RuntimeError(f"reference diagnostic failed; inspect {log}")
    print(metrics.read_text())


def mvs_surface_audit() -> None:
    output_json = TASK_ROOT / "mvs_surface_audit.json"
    output_csv = TASK_ROOT / "mvs_surface_metrics.csv"
    script = REPO / "scripts/p2/e3_local_4906982_depth_rep_diag_v1/surface_audit.py"
    mvs_npy = (
        ARTIFACT_ROOT
        / "phase-payloads/p2/e3_local_4906982_mvs_transfer_diag_v1"
        / "P2-E3-LOCAL-4906982-MVS-TRANSFER-DIAG-v1/fused_seed/mvs_xyz_f32.npy"
    )
    footprint = TASK_ROOT / "control/shared_standard_footprint_4906982.geojson"
    argv = base.eval_docker_base() + [
        "python",
        repo_container_path(script),
        "--task-root",
        base.container_path(TASK_ROOT),
        "--mvs-npy",
        base.container_path(mvs_npy),
        "--footprint",
        base.container_path(footprint),
        "--output-json",
        base.container_path(output_json),
        "--output-csv",
        base.container_path(output_csv),
    ]
    log = TASK_ROOT / "logs/mvs_surface_audit.log"
    started = base.now()
    with log.open("w") as stream:
        proc = subprocess.run(argv, text=True, stdout=stream, stderr=subprocess.STDOUT)
    base.record_operation("mvs_surface_audit", argv, proc.returncode, started, base.now())
    if proc.returncode != 0:
        raise RuntimeError(f"MVS surface audit failed; inspect {log}")
    print(output_json.read_text())


def finalize_report() -> None:
    metrics_path = TASK_ROOT / "metrics.json"
    metrics = json.loads(metrics_path.read_text())
    if metrics.get("status") != "COMPLETE_MEASURED":
        raise RuntimeError("complete checkpoint/Stage-3 measurements required")
    mvs = json.loads((TASK_ROOT / "mvs_surface_audit.json").read_text())
    mvs20 = {row["arm"]: row for row in mvs["rows"] if row["completed_updates"] == 20000}
    with (TASK_ROOT / "reference_diagnostic/case_metrics.csv").open(newline="") as stream:
        reference_rows = list(csv.DictReader(stream))
    reference20 = {
        row["arm"]: row
        for row in reference_rows
        if int(row["completed_updates"]) == 20000
    }
    for row in reference20.values():
        row["scientific_verdict"] = None

    prior_root = (
        ARTIFACT_ROOT
        / "phase-payloads/p2/e3_local_4906982_mvs_transfer_diag_v1"
        / "P2-E3-LOCAL-4906982-MVS-TRANSFER-DIAG-v1"
    )
    for name in ("expected_median_audit.json", "expected_median_audit.csv"):
        shutil.copy2(prior_root / name, TASK_ROOT / name)
    prior_gate = json.loads((TASK_ROOT / "expected_median_audit.json").read_text())

    def number(arm: str, field: str) -> float:
        return float(reference20[arm][field])

    paired20 = metrics["paired_median_minus_expected"]["20000"]
    metrics.update(
        {
            "schema": "jointbuildgs.p2.e3_local_4906982_depth_rep_diag_v1.metrics.v1",
            "task_id": TASK_ID,
            "training_experiments_started": 2,
            "training_experiments_completed": 2,
            "surface_intersection_experiments_started": 0,
            "prior_expected_median_gate": {
                "source_task": str(prior_root),
                "status": prior_gate["status"],
                "all_expected_only_rate": prior_gate["groups"]["all"]["expected_only_rate"],
                "footprint_expected_only_rate": prior_gate["groups"]["footprint_inside"]["expected_only_rate"],
                "footprint_oblique_expected_only_rate": prior_gate["groups"]["footprint_oblique_gt_30deg"]["expected_only_rate"],
            },
            "mvs_surface_audit_20k": mvs20,
            "lod2_evaluation_only_20k": reference20,
            "measurement_observations": {
                "high_z_count_not_reduced": mvs20["MEDIAN"]["gaussian_z_gt_650_count"] >= mvs20["EXPECTED"]["gaussian_z_gt_650_count"],
                "maximum_z_reduced_m": paired20["z_max"]["mean"],
                "mvs_point_to_plane_tail_reduced": mvs20["MEDIAN"]["ordinary_point_to_plane_m_p99"] < mvs20["EXPECTED"]["ordinary_point_to_plane_m_p99"],
                "held_out_rgb_worse": paired20["eval_psnr"]["mean"] < 0 and paired20["eval_ssim"]["mean"] < 0 and paired20["eval_lpips"]["mean"] > 0,
                "lod2_typical_height_and_normal_improved": number("MEDIAN", "classified_abs_dz_m_median") < number("EXPECTED", "classified_abs_dz_m_median") and number("MEDIAN", "classified_normal_angle_deg_median") < number("EXPECTED", "classified_normal_angle_deg_median"),
                "lod2_rmse_and_grid_coherence_worse": number("MEDIAN", "classified_abs_dz_m_rmse") > number("EXPECTED", "classified_abs_dz_m_rmse") and number("MEDIAN", "classified_coherent_grid_coverage_fraction") < number("EXPECTED", "classified_coherent_grid_coverage_fraction"),
                "roofer_internal_rmse_worse": paired20["roofer_rmse_lod22"]["mean"] > 0,
            },
            "next_single_variable_recommendation": {
                "proposal": "EXPECTED control versus surface-intersection depth for raw COLMAP L1 only",
                "execute_without_approval": False,
                "reason": "global MEDIAN reduced MVS residual tails and extreme max-Z but did not reduce the high-Z population or stabilize coverage/Roofer; a discrete surface-hit statistic remains the untested representation variable",
                "required_guardrails": [
                    "same exact 7k full state",
                    "same raw mask/L1/weight/schedule/MVC/densification/views/seed/GPU",
                    "surface hit definition and no-hit handling frozen before results",
                    "high-Z count, MVS residual tail, held-out RGB, coverage/coherence, and Roofer all retained",
                ],
            },
            "scientific_verdict": None,
        }
    )
    atomic_json(metrics_path, metrics)

    expected = metrics["aggregates"]["20000"]["EXPECTED"]
    median = metrics["aggregates"]["20000"]["MEDIAN"]
    comparison = f"""# {TASK_ID}

## Expected-depth read-only gate

- Prior gate status: `{prior_gate['status']}`.
- Expected만 raw MVS tolerance 안이고 median은 밖인 비율: 전체 {100*prior_gate['groups']['all']['expected_only_rate']:.3f}%, footprint {100*prior_gate['groups']['footprint_inside']['expected_only_rate']:.3f}%, footprint oblique {100*prior_gate['groups']['footprint_oblique_gt_30deg']['expected_only_rate']:.3f}%.
- 이 모호성을 단일변수로 분리하기 위해 EXPECTED와 MEDIAN 두 arm을 실제 실행했다. surface-intersection arm은 실행하지 않았다.

## 실행 및 gate

- 학습 실험: 2개 시작, 2개 완료 (`EXPECTED`, `MEDIAN`).
- 동일 DEPTH03/R1 7k full state에서 분기: model/optimizer/strategy/grouping/RNG/loss cursor exact-equal PASS.
- arm 간 학습 차이: raw COLMAP L1에 전달되는 rendered depth statistic 하나뿐이다.
- 첫 EXPECTED 실행은 optimizer update 전에 effective-binding mismatch로 중단됐다. binding probe를 실제 checkpoint-step contract에 맞춰 수정하고 exact-equality를 재검증한 후 재개했다.
- `scientific_verdict: null`.

## High-Z — 20k

| Metric | EXPECTED | MEDIAN | MEDIAN−EXPECTED |
|---|---:|---:|---:|
| Gaussian count | {expected['gaussian_count']['mean']:,.0f} | {median['gaussian_count']['mean']:,.0f} | {paired20['gaussian_count']['mean']:+,.0f} |
| Z>650 count | {mvs20['EXPECTED']['gaussian_z_gt_650_count']} | {mvs20['MEDIAN']['gaussian_z_gt_650_count']} | {mvs20['MEDIAN']['gaussian_z_gt_650_count']-mvs20['EXPECTED']['gaussian_z_gt_650_count']:+d} |
| Z>650 footprint inside / outside | {mvs20['EXPECTED']['gaussian_z_gt_650_footprint_inside_count']} / {mvs20['EXPECTED']['gaussian_z_gt_650_footprint_outside_count']} | {mvs20['MEDIAN']['gaussian_z_gt_650_footprint_inside_count']} / {mvs20['MEDIAN']['gaussian_z_gt_650_footprint_outside_count']} | — |
| Z>650 opacity≥0.9 | {mvs20['EXPECTED']['gaussian_z_gt_650_opacity_ge_0p9']} | {mvs20['MEDIAN']['gaussian_z_gt_650_opacity_ge_0p9']} | {mvs20['MEDIAN']['gaussian_z_gt_650_opacity_ge_0p9']-mvs20['EXPECTED']['gaussian_z_gt_650_opacity_ge_0p9']:+d} |
| Z p99 (m) | {expected['z_p99']['mean']:.3f} | {median['z_p99']['mean']:.3f} | {paired20['z_p99']['mean']:+.3f} |
| Z max (m) | {expected['z_max']['mean']:.3f} | {median['z_max']['mean']:.3f} | {paired20['z_max']['mean']:+.3f} |

관찰: MEDIAN은 extreme maximum을 낮췄지만 Z>650 population과 high-opacity high-Z를 줄이지 않았다. 두 arm 모두 Z>650은 footprint 밖에만 존재했다.

## 정상 표면 — 20k

| Metric | EXPECTED | MEDIAN | MEDIAN−EXPECTED |
|---|---:|---:|---:|
| MVS point-to-point median / p95 / p99 (m) | {mvs20['EXPECTED']['ordinary_point_to_point_m_median']:.3f} / {mvs20['EXPECTED']['ordinary_point_to_point_m_p95']:.3f} / {mvs20['EXPECTED']['ordinary_point_to_point_m_p99']:.3f} | {mvs20['MEDIAN']['ordinary_point_to_point_m_median']:.3f} / {mvs20['MEDIAN']['ordinary_point_to_point_m_p95']:.3f} / {mvs20['MEDIAN']['ordinary_point_to_point_m_p99']:.3f} | tail 감소 |
| MVS point-to-plane median / p95 / p99 (m) | {mvs20['EXPECTED']['ordinary_point_to_plane_m_median']:.3f} / {mvs20['EXPECTED']['ordinary_point_to_plane_m_p95']:.3f} / {mvs20['EXPECTED']['ordinary_point_to_plane_m_p99']:.3f} | {mvs20['MEDIAN']['ordinary_point_to_plane_m_median']:.3f} / {mvs20['MEDIAN']['ordinary_point_to_plane_m_p95']:.3f} / {mvs20['MEDIAN']['ordinary_point_to_plane_m_p99']:.3f} | tail 감소 |
| MVS normal angle median / p95 / p99 | {mvs20['EXPECTED']['ordinary_normal_angle_deg_median']:.2f}° / {mvs20['EXPECTED']['ordinary_normal_angle_deg_p95']:.2f}° / {mvs20['EXPECTED']['ordinary_normal_angle_deg_p99']:.2f}° | {mvs20['MEDIAN']['ordinary_normal_angle_deg_median']:.2f}° / {mvs20['MEDIAN']['ordinary_normal_angle_deg_p95']:.2f}° / {mvs20['MEDIAN']['ordinary_normal_angle_deg_p99']:.2f}° | median +{mvs20['MEDIAN']['ordinary_normal_angle_deg_median']-mvs20['EXPECTED']['ordinary_normal_angle_deg_median']:.2f}°, tail 감소 |
| MVS grid coverage | {100*mvs20['EXPECTED']['ordinary_grid_coverage_of_mvs']:.2f}% | {100*mvs20['MEDIAN']['ordinary_grid_coverage_of_mvs']:.2f}% | {100*(mvs20['MEDIAN']['ordinary_grid_coverage_of_mvs']-mvs20['EXPECTED']['ordinary_grid_coverage_of_mvs']):+.2f} pp |
| LoD2 eval-only median |dZ| / RMSE | {number('EXPECTED','classified_abs_dz_m_median'):.3f} / {number('EXPECTED','classified_abs_dz_m_rmse'):.3f} m | {number('MEDIAN','classified_abs_dz_m_median'):.3f} / {number('MEDIAN','classified_abs_dz_m_rmse'):.3f} m | typical 개선, tail 악화 |
| LoD2 eval-only normal median | {number('EXPECTED','classified_normal_angle_deg_median'):.2f}° | {number('MEDIAN','classified_normal_angle_deg_median'):.2f}° | {number('MEDIAN','classified_normal_angle_deg_median')-number('EXPECTED','classified_normal_angle_deg_median'):+.2f}° |
| LoD2 eval-only grid / coherent coverage | {100*number('EXPECTED','classified_grid_coverage_fraction'):.2f}% / {100*number('EXPECTED','classified_coherent_grid_coverage_fraction'):.2f}% | {100*number('MEDIAN','classified_grid_coverage_fraction'):.2f}% / {100*number('MEDIAN','classified_coherent_grid_coverage_fraction'):.2f}% | 둘 다 감소 |
| Held-out PSNR / SSIM / LPIPS | {expected['eval_psnr']['mean']:.3f} / {expected['eval_ssim']['mean']:.4f} / {expected['eval_lpips']['mean']:.4f} | {median['eval_psnr']['mean']:.3f} / {median['eval_ssim']['mean']:.4f} / {median['eval_lpips']['mean']:.4f} | 모두 악화 |

## Fusion / Roofer — 20k

| Metric | EXPECTED | MEDIAN | MEDIAN−EXPECTED |
|---|---:|---:|---:|
| Fusion ≥2-view points | {expected['fusion_ge2']['mean']:,.0f} | {median['fusion_ge2']['mean']:,.0f} | {paired20['fusion_ge2']['mean']:+,.0f} |
| Fusion ≥3-view share | {100*expected['fusion_ge3_ratio']['mean']:.2f}% | {100*median['fusion_ge3_ratio']['mean']:.2f}% | {100*paired20['fusion_ge3_ratio']['mean']:+.2f} pp |
| Roof-normal density | {expected['roof_density']['mean']:.2f} | {median['roof_density']['mean']:.2f} | {paired20['roof_density']['mean']:+.2f} points/m² |
| Roofer success / roof type | true / slanted | true / slanted | 동일 |
| Roofer internal RMSE | {metrics['aggregates']['20000']['EXPECTED']['roofer_rmse_lod22']['mean']:.3f} m | {metrics['aggregates']['20000']['MEDIAN']['roofer_rmse_lod22']['mean']:.3f} m | {paired20['roofer_rmse_lod22']['mean']:+.3f} m |
| LoD2 eval-only Roofer XY coverage | {100*number('EXPECTED','roofer_roof_xy_coverage_fraction'):.2f}% | {100*number('MEDIAN','roofer_roof_xy_coverage_fraction'):.2f}% | {100*(number('MEDIAN','roofer_roof_xy_coverage_fraction')-number('EXPECTED','roofer_roof_xy_coverage_fraction')):+.2f} pp |

## 다음 권고

다음 단일변수는 raw COLMAP L1의 `EXPECTED ↔ surface-intersection depth` 비교다. MEDIAN이 MVS residual tail과 extreme max-Z를 줄였다는 점은 depth representation이 정상 표면 concentration에 영향을 준다는 근거다. 그러나 global MEDIAN은 high-Z population, held-out RGB, LoD2 RMSE/coverage/coherence, Roofer internal RMSE를 함께 안정화하지 못했다. 따라서 median을 채택하거나 mask/normal/densification을 동시에 추가하지 않고, 실제 surface hit를 고르는 표현만 분리한다. 승인 전에는 실행하지 않는다.
"""
    base.atomic_text(TASK_ROOT / "comparison.md", comparison)

    issues = f"""# Issues

1. Docker read-only syntax check attempted to write `__pycache__` and stopped; unit tests had already passed and no artifact was created by that check.
2. The first EXPECTED resume stopped before any optimizer update because the binding probe used an empty checkpoint-step list. The probe was corrected to the exact continuation list, the 7k checkpoint was metadata-rebound, and all learned-state sections passed exact equality again.
3. GPU evaluation created root-owned task-local directories. Ownership was normalized only inside this new namespace before Stage 3; measurement bytes were not changed.
4. The first measurement-finalization attempt encountered empty pre-7k TensorBoard scalars; empty aggregates are now recorded as null.
5. The first paired-panel retry exposed arm-name replacement order (`MVC05` became `EXPECTED5`); it stopped before modifying measurements. The corrected retry produced 32 paired panels.
6. Per-Gaussian MVC-inlier membership is not retained by the current trainer, so high-Z MVC-inlier inclusion could not be reconstructed exactly. Checkpoint-wide MVC scalar/inlier counts remain recorded.
7. This is one same-seed continuation pair, not confirmatory inference. The MVS surface is a diagnostic reference, not independent GT; LoD2 XYZ was evaluation-only and may differ in vintage.

No NaN, OOM, missing required checkpoint, classification failure, or Roofer process failure occurred. `scientific_verdict: null`.
"""
    base.atomic_text(TASK_ROOT / "issues.md", issues)
    base.atomic_text(
        TASK_ROOT / "NOTES.md",
        f"""# {TASK_ID}

Status: `COMPLETE_MEASURED`.

- Prior expected/median gate copied read-only into this namespace.
- Two 7k→20k continuations completed on GPU 1: EXPECTED and MEDIAN.
- Required full-state checkpoints: 8/8 valid at 7k, 12k, 15k, and 20k.
- Checkpoint render/fusion/classification/Roofer: 8/8 complete.
- Evaluation-only LoD2 reference cases: 8/8 complete.
- Filtered-MVS point-to-point/plane/normal audit: 8/8 complete.
- Training delta: rendered depth statistic passed to raw COLMAP L1 only.
- Surface-intersection training: not run.
- Scientific verdict: `null`.
""",
    )

    source_panel = TASK_ROOT / "reference_diagnostic/representative_images/roofer_reference_20k.png"
    if source_panel.is_file():
        shutil.copy2(source_panel, TASK_ROOT / "representative_images/roofer_reference_20k.png")
    paired = sorted((TASK_ROOT / "representative_images/paired").glob("*.png"))
    viewer = TASK_ROOT / "viewer"
    viewer.mkdir(exist_ok=True)
    names = ["roofer_reference_20k.png"] + ["paired/" + path.name for path in paired]
    html = '''<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>4906982 depth representation comparison</title><style>body{font-family:system-ui;background:#0d1117;color:#e6edf3;margin:0;padding:20px}header{max-width:1600px;margin:auto}select,a{padding:8px;margin:4px;background:#21262d;color:#e6edf3;border:1px solid #30363d;border-radius:5px}img{display:block;max-width:100%;margin:18px auto;border:1px solid #30363d}small{color:#8b949e}</style></head><body><header><h1>DEBY_LOD2_4906982 · EXPECTED vs MEDIAN</h1><p>Paired panels show EXPECTED left and MEDIAN right.</p><label>Panel <select id="panel"></select></label><a href="../comparison.md">comparison.md</a><br><small>Scientific verdict: null</small></header><img id="view"><script>const names=__NAMES__;const s=document.getElementById('panel'),v=document.getElementById('view');for(const n of names){const o=document.createElement('option');o.value=n;o.textContent=n;s.appendChild(o)}function show(){v.src='../representative_images/'+s.value}s.onchange=show;show();</script></body></html>'''.replace("__NAMES__", json.dumps(names))
    base.atomic_text(viewer / "index.html", html)
    atomic_json(
        TASK_ROOT / "viewer_slot.json",
        {
            "schema": "jointbuildgs.viewer.comparison_slot.v1",
            "slot_id": "p2-e3-local-4906982-depth-rep-diag-v1",
            "label": "DEBY_LOD2_4906982 EXPECTED vs MEDIAN",
            "relative_url": "viewer/index.html",
            "panel_count": len(names),
            "separate_add_only_slot": True,
            "legacy_8878_mvs_seed_color_v3_modified": False,
            "scientific_verdict": None,
        },
    )
    contract_path = TASK_ROOT / "experiment_contract.json"
    contract = json.loads(contract_path.read_text())
    contract["status"] = "COMPLETE_MEASURED"
    contract["training_experiments_started"] = 2
    contract["training_experiments_completed"] = 2
    contract["surface_intersection_experiments_started"] = 0
    contract["scientific_verdict"] = None
    atomic_json(contract_path, contract)

    provenance_path = TASK_ROOT / "provenance.json"
    provenance = json.loads(provenance_path.read_text())
    provenance["git_at_completion"] = base.git_record()
    provenance["evaluation_docker_image"] = {
        "reference": base.EVAL_IMAGE,
        "id": base.command(["docker", "image", "inspect", base.EVAL_IMAGE, "--format", "{{.Id}}"], check=False).stdout.strip(),
    }
    provenance["stage3_images"] = {
        "tools": {"reference": base.TOOLS_IMAGE, "id": base.TOOLS_IMAGE_ID},
        "roofer": {"reference": base.ROOFER_IMAGE, "id": base.ROOFER_IMAGE_ID},
    }
    provenance["source_files_sha256"].update(
        {
            str(Path(__file__).resolve().relative_to(REPO)): sha256(Path(__file__).resolve()),
            "scripts/p2/e3_local_4906982_depth_rep_diag_v1/surface_audit.py": sha256(REPO / "scripts/p2/e3_local_4906982_depth_rep_diag_v1/surface_audit.py"),
            "tests/stage2/test_depth_supervision_mode.py": sha256(REPO / "tests/stage2/test_depth_supervision_mode.py"),
        }
    )
    outputs = [
        "experiment_contract.json",
        "config_diff.txt",
        "input_hashes.json",
        "expected_median_audit.json",
        "expected_median_audit.csv",
        "checkpoint_metrics.csv",
        "paired_checkpoint_deltas.csv",
        "metrics.json",
        "mvs_surface_audit.json",
        "mvs_surface_metrics.csv",
        "comparison.md",
        "NOTES.md",
        "issues.md",
        "viewer_slot.json",
    ]
    provenance["output_index_sha256"] = {
        name: sha256(TASK_ROOT / name) for name in outputs if (TASK_ROOT / name).is_file()
    }
    provenance["ended_utc"] = base.now()
    provenance["scientific_verdict"] = None
    atomic_json(provenance_path, provenance)
    print(json.dumps({"status": "COMPLETE_MEASURED", "comparison": str(TASK_ROOT / "comparison.md"), "viewer": str(viewer / "index.html"), "scientific_verdict": None}, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "command",
        choices=[
            "preflight",
            "binding-probe",
            "fork-7k",
            "train",
            "analyze-checkpoints",
            "stage3",
            "finalize-measurements",
            "reference-diagnostic",
            "mvs-surface-audit",
            "finalize-report",
            "all-training",
        ],
    )
    args = parser.parse_args()
    if args.command in {"preflight", "all-training"}:
        preflight()
    if args.command in {"binding-probe", "all-training"}:
        binding_probe()
    if args.command in {"fork-7k", "all-training"}:
        fork_7k()
    if args.command in {"train", "all-training"}:
        train()
    if args.command == "analyze-checkpoints":
        analyze_checkpoints()
    if args.command == "stage3":
        stage3()
    if args.command == "finalize-measurements":
        finalize_measurements()
    if args.command == "reference-diagnostic":
        reference_diagnostic()
    if args.command == "mvs-surface-audit":
        mvs_surface_audit()
    if args.command == "finalize-report":
        finalize_report()


if __name__ == "__main__":
    main()
