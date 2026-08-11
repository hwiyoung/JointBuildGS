#!/usr/bin/env python3
"""Exact-55 ALS-normal ablation, branched from the frozen FUSED_VIS_CONF 7k state."""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
from typing import Any

import yaml


REPO = Path(__file__).resolve().parents[3]
ARTIFACT_ROOT = REPO.parent / "JointBuildGS-artifacts"
TASK_ID = "P2-E4-LOCAL-4906982-55V-ALS-NORMAL-ABLATION-v1"
TASK_ROOT = ARTIFACT_ROOT / "phase-payloads/p2/e4_local_4906982_55v_als_normal_ablation_v1" / TASK_ID
CONFIG_DIR = REPO / "configs/p2/e4_local_4906982_55v_als_normal_ablation_v1"
COMMON_CONFIG = CONFIG_DIR / "common.yaml"
ARM_CONFIG = CONFIG_DIR / "als_depth_only.yaml"
VIEWER_CONFIG = CONFIG_DIR / "viewer.yaml"
SOURCE_TASK = ARTIFACT_ROOT / "phase-payloads/p2/e3_local_4906982_fused_vis_conf_v1/P2-E3-LOCAL-4906982-FUSED-VIS-CONF-v1"
SOURCE_RUN = SOURCE_TASK / "arms/FUSED_VIS_CONF/R1"
SOURCE_CHECKPOINT = SOURCE_RUN / "ckpt/step_007000.pt"
FULL_E4_TASK = ARTIFACT_ROOT / "phase-payloads/p2/e4_local_4906982_55v_als_prior_v1/P2-E4-LOCAL-4906982-55V-ALS-PRIOR-v1"
FULL_E4_RUN = FULL_E4_TASK / "arms/E4_ALS_PRIOR_ONLY/R1"
PRIOR_RECEIPT = FULL_E4_TASK / "control/200-55v-als-prior-preflight-passed.json"
RUN_ROOT = TASK_ROOT / "arms/ALS_DEPTH_ONLY/R1"
RUNTIME_CONFIG = TASK_ROOT / "control/runtime_configs/als_depth_only_r1.yaml"
ARMS = ("FUSED_VIS_CONF", "ALS_DEPTH_ONLY")
CHECKPOINTS = (7000, 12000, 15000, 20000)


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


full_e4 = load_module("full_e4_runner_for_normal_ablation", REPO / "scripts/p2/e4_local_4906982_55v_als_prior_v1/run.py")
base = full_e4.base
depth_runner = full_e4.depth_runner
base.TASK_ID = TASK_ID
base.TASK_ROOT = TASK_ROOT
base.GPU = "1"
base.ARMS = ARMS
base.REPLICAS = ("R1",)
base.CHECKPOINTS = CHECKPOINTS


def sha256(path: Path) -> str:
    return base.sha256(path)


def container_path(path: Path) -> str:
    return base.container_path(path)


def full_config() -> dict[str, Any]:
    return full_e4.materialized()


def control_config() -> dict[str, Any]:
    return full_e4.materialized_control()


def target_config() -> dict[str, Any]:
    body = full_config()
    body.update(yaml.safe_load(ARM_CONFIG.read_text())["overrides"])
    body.update({"official_PASS_usable": None, "scientific_verdict": None})
    return body


def changed(left: dict[str, Any], right: dict[str, Any]) -> list[str]:
    return sorted(key for key in set(left) | set(right) if left.get(key) != right.get(key))


def ensure_owner() -> None:
    if TASK_ROOT.exists():
        subprocess.run(base.docker_base() + ["chown", "-R", f"{os.getuid()}:{os.getgid()}", container_path(TASK_ROOT)], check=True)


def viewer_root() -> Path:
    path = yaml.safe_load(VIEWER_CONFIG.read_text())["viewer_root"]
    return Path(path.replace("/artifacts/JointBuildGS", str(ARTIFACT_ROOT), 1))


def preflight() -> None:
    for relative in ("control/runtime_configs", "control/effective_configs", "control/receipts", "logs", "cache/torch_extensions", "representative_images"):
        (TASK_ROOT / relative).mkdir(parents=True, exist_ok=True)
    required = [COMMON_CONFIG, ARM_CONFIG, VIEWER_CONFIG, SOURCE_CHECKPOINT, Path(str(SOURCE_CHECKPOINT) + ".sha256"), PRIOR_RECEIPT,
                FULL_E4_TASK / "input_hashes.json", FULL_E4_RUN / "ckpt/step_007000.pt", REPO / "src/stage2/train.py",
                REPO / "src/stage2/dataloader.py", REPO / "src/stage2/loss/data_fitting.py", REPO / "src/stage2/loss/multiview.py"]
    for path in required:
        if not path.is_file():
            raise FileNotFoundError(path)
    if not base.checkpoint_valid(SOURCE_RUN, 7000) or not base.checkpoint_valid(FULL_E4_RUN, 7000):
        raise RuntimeError("source/full-E4 7k checkpoint sidecar failed")
    prior = json.loads(PRIOR_RECEIPT.read_text())
    if prior.get("status") != "200-PASSED_EXACT55_ALIGNMENT_PROJECTION_GRADIENT_AND_GPU_MEMORY_PREFLIGHT":
        raise RuntimeError("frozen exact-55 ALS preflight is not passed")
    if prior["view_count"] != 55 or prior["nonempty_view_count"] != 55 or not prior["alignment"]["passed"] or not prior["gradient_and_gpu_memory"]["passed"]:
        raise RuntimeError("frozen ALS prior gate drifted")
    for row in prior["view_receipts"]:
        path = FULL_E4_TASK / row["path"]
        if not path.is_file() or sha256(path) != row["sha256"]:
            raise RuntimeError(f"ALS prior hash drift: {path}")

    full = full_config()
    target = target_config()
    actual = changed(full, target)
    expected = sorted(("task_id", "run_id", "out_dir", "w_external_als_normal"))
    if actual != expected:
        raise RuntimeError(f"normal-only config gate failed: {actual} != {expected}")
    locked = {
        "seed": 0, "downscale": 1.0, "load_depth": True, "depth_supervision_mode": "expected",
        "depth_loss_type": "l1", "w_depth": 0.03, "depth_warmup": 7000, "depth_schedule": "ramp",
        "depth_ramp_steps": 5000, "w_mvc": 0.5, "w_nc": 0.05, "w_distort": 0.0, "max_iter": 20000,
        "w_external_als_depth": 0.01, "w_external_als_normal": 0.0, "external_als_huber_delta_m": 1.0,
        "external_als_depth_loss": "HUBER_METRIC_CAMERA_DEPTH", "external_als_normal_loss": "SIGN_INVARIANT_ONE_MINUS_ABS_DOT",
    }
    mismatch = {key: [target.get(key), value] for key, value in locked.items() if target.get(key) != value}
    if mismatch or len(target["visible_views"]) != 55 or len(target["train_views"]) != 47 or len(target["eval_views"]) != 8:
        raise RuntimeError(f"locked depth-only config mismatch: {mismatch}")
    base.atomic_text(RUNTIME_CONFIG, yaml.safe_dump(target, sort_keys=False))

    diff = "\n".join([
        "comparison 1: existing FUSED_VIS_CONF versus new ALS_DEPTH_ONLY (ALS depth package effect)",
        "comparison 2: new ALS_DEPTH_ONLY versus existing E4_ALS_PRIOR_ONLY (ALS normal addition effect)",
        "branch: exact FUSED_VIS_CONF full-state checkpoint at completed update 7000",
        "single scientific variable against full E4: w_external_als_normal 0.005 -> 0.0",
        "unchanged: ALS metric depth/weight/Huber target, MVS depth, 55 images, crop cameras, 47/8 roles, sparse history, model/optimizer/RNG at 7k, MVC, NC, densification, seed, GPU",
        "LoD2 Z/RoofSurface/roof type training use: none; evaluation-only after training",
        "existing artifacts and viewer root state modified: false",
        "scientific_verdict: null", "",
    ])
    base.atomic_text(TASK_ROOT / "config_diff.txt", diff)

    data_root = Path(target["data_root"].replace("/artifacts/JointBuildGS", str(ARTIFACT_ROOT), 1))
    sparse_link = data_root / "sparse"
    sparse_root = Path(os.readlink(sparse_link).replace("/artifacts/JointBuildGS", str(ARTIFACT_ROOT), 1)) / "0"
    depths = sorted((data_root / "depth").glob("*.exr"))
    if len(depths) != 55:
        raise RuntimeError(f"expected 55 MVS depth maps, got {len(depths)}")
    input_hashes = {
        "schema": "jointbuildgs.p2.e4_local_4906982_55v_als_normal_ablation_v1.inputs.v1",
        "source_7k_checkpoint": {"path": str(SOURCE_CHECKPOINT), "sha256": sha256(SOURCE_CHECKPOINT)},
        "full_e4_7k_checkpoint": {"path": str(FULL_E4_RUN / "ckpt/step_007000.pt"), "sha256": sha256(FULL_E4_RUN / "ckpt/step_007000.pt")},
        "full_e4_input_hashes": {"path": str(FULL_E4_TASK / "input_hashes.json"), "sha256": sha256(FULL_E4_TASK / "input_hashes.json")},
        "crop_camera_sparse_sha256": {name: sha256(sparse_root / name) for name in ("cameras.bin", "images.bin", "points3D.bin")},
        "fused_vis_conf_depth_sha256": {path.name: sha256(path) for path in depths},
        "als_prior_preflight": {"path": str(PRIOR_RECEIPT), "sha256": sha256(PRIOR_RECEIPT)},
        "als_prior_view_sha256": {row["name"]: row["sha256"] for row in prior["view_receipts"]},
        "reuse": {"crop_regenerated": False, "cameras_regenerated": False, "view_roles_regenerated": False, "sparse_seed_regenerated": False, "mvs_depth_regenerated": False, "als_prior_regenerated": False},
        "scientific_verdict": None,
    }
    base.atomic_json(TASK_ROOT / "input_hashes.json", input_hashes)
    contract = {
        "schema": "jointbuildgs.p2.e4_local_4906982_55v_als_normal_ablation_v1.contract.v1", "task_id": TASK_ID,
        "building_id": "DEBY_LOD2_4906982", "status": "PREFLIGHT_BOUND", "non_confirmatory": True,
        "question": "Does the ALS normal channel explain the 55-view E4 Roofer improvement beyond ALS metric depth alone?",
        "comparisons": [
            {"left": "FUSED_VIS_CONF", "right": "ALS_DEPTH_ONLY", "effect": "ALS depth package"},
            {"left": "ALS_DEPTH_ONLY", "right": "E4_ALS_PRIOR_ONLY", "effect": "ALS normal addition"},
        ],
        "new_arm": "ALS_DEPTH_ONLY", "single_variable_against_full_e4": {"key": "w_external_als_normal", "full_e4": 0.005, "depth_only": 0.0},
        "source_completed_updates": 7000, "first_intervention_update": 7001, "checkpoints": list(CHECKPOINTS),
        "selected_gpu": 1, "training_experiments_started": 0, "new_loss": False, "multiview_densification": False,
        "lod2_training_use": False, "scientific_verdict": None,
    }
    base.atomic_json(TASK_ROOT / "experiment_contract.json", contract)
    source_files = [Path(__file__), COMMON_CONFIG, ARM_CONFIG, VIEWER_CONFIG, REPO / "src/stage2/train.py", REPO / "src/stage2/dataloader.py", REPO / "src/stage2/loss/data_fitting.py", REPO / "src/stage2/loss/multiview.py"]
    previous = json.loads((TASK_ROOT / "provenance.json").read_text()) if (TASK_ROOT / "provenance.json").is_file() else {}
    base.atomic_json(TASK_ROOT / "provenance.json", {
        "schema": "jointbuildgs.p2.e4_local_4906982_55v_als_normal_ablation_v1.provenance.v1", "task_id": TASK_ID,
        "git": base.git_record(), "docker_image": base.image_record(), "gpu": base.gpu_record(),
        "source_config_sha256": {str(path.relative_to(REPO)): sha256(path) for path in source_files},
        "input_hashes_sha256": sha256(TASK_ROOT / "input_hashes.json"), "random_seed": 0,
        "started_utc": previous.get("started_utc") or base.now(), "ended_utc": None,
        "commands": previous.get("commands", []), "return_codes": previous.get("return_codes", []), "scientific_verdict": None,
    })
    base.atomic_text(TASK_ROOT / "NOTES.md", f"# {TASK_ID}\n\nStatus: `PREFLIGHT_BOUND`. One new ALS-depth-only training arm; existing control/full-E4 outputs are read-only comparators.\n\nRoofer evidence and roof geometry will be published to an add-only 8878 comparison slot.\n\nscientific_verdict: null\n")
    if not (TASK_ROOT / "issues.md").exists():
        base.atomic_text(TASK_ROOT / "issues.md", "# Issues\n\n- None at preflight.\n\nscientific_verdict: null\n")
    source_footprint = SOURCE_TASK / "control/shared_standard_footprint_4906982.geojson"
    target_footprint = TASK_ROOT / "control/shared_standard_footprint_4906982.geojson"
    if target_footprint.exists() and sha256(target_footprint) != sha256(source_footprint):
        raise RuntimeError("task-local footprint drifted")
    if not target_footprint.exists():
        shutil.copy2(source_footprint, target_footprint)
    root = viewer_root()
    fixed = yaml.safe_load(VIEWER_CONFIG.read_text())["root_files_must_remain_unchanged"]
    hashes = {name: sha256(root / name) for name in fixed}
    base.atomic_json(TASK_ROOT / "control/viewer_root_precondition.json", {"viewer_root": str(root), "fixed_file_sha256": hashes, "scientific_verdict": None})
    print(diff, end="")


def binding_probe() -> None:
    stable = TASK_ROOT / "control/effective_configs/als_depth_only.json"
    if stable.is_file():
        print(stable.read_text()); return
    cfg = target_config(); cfg.update({"run_id": "BINDING_PROBE_ALS_DEPTH_ONLY", "out_dir": container_path(TASK_ROOT / "binding_probe"), "max_iter": 1, "eval_every": 100000, "ckpt_every": 100000, "full_state_resume": "off"})
    path = TASK_ROOT / "control/runtime_configs/binding_probe.yaml"; base.atomic_text(path, yaml.safe_dump(cfg, sort_keys=False))
    argv = base.docker_base(gpu=True) + ["python", "-c", base.DETERMINISTIC_WRAPPER, "--config", container_path(path)]
    log = TASK_ROOT / "logs/binding_probe.log"; started = base.now()
    with log.open("w") as stream: proc = subprocess.run(argv, text=True, stdout=stream, stderr=subprocess.STDOUT)
    base.record_operation("binding_probe", argv, proc.returncode, started, base.now())
    if proc.returncode: raise RuntimeError(f"binding probe failed: {log}")
    effective = json.loads((TASK_ROOT / "binding_probe/effective_config.json").read_text()); effective.pop("full_state_runtime", None)
    base.atomic_json(stable, effective); print(stable.read_text())


def smoke() -> None:
    receipt = TASK_ROOT / "control/receipts/smoke.json"
    if receipt.is_file() and json.loads(receipt.read_text()).get("passed"):
        print(receipt.read_text()); return
    cfg = target_config(); root = TASK_ROOT / "smoke"
    cfg.update({"run_id": "SMOKE_ALS_DEPTH_ONLY", "out_dir": container_path(root), "max_iter": 12, "eval_every": 100000, "ckpt_every": 100000,
                "full_state_resume": "off", "full_state_checkpoint": False, "full_state_checkpoint_steps": [], "mvc_warmup": 0, "mvc_ramp_steps": 1,
                "depth_warmup": 0, "depth_ramp_steps": 1, "refine_start_iter": 500})
    path = TASK_ROOT / "control/runtime_configs/smoke.yaml"; base.atomic_text(path, yaml.safe_dump(cfg, sort_keys=False))
    argv = base.docker_base(gpu=True) + ["python", "-c", base.DETERMINISTIC_WRAPPER, "--config", container_path(path)]
    log = TASK_ROOT / "logs/smoke.log"; started = base.now()
    with log.open("w") as stream: proc = subprocess.run(argv, text=True, stdout=stream, stderr=subprocess.STDOUT)
    base.record_operation("smoke", argv, proc.returncode, started, base.now())
    check = "from tensorboard.backend.event_processing.event_accumulator import EventAccumulator as E;import glob,json,sys;e=E(glob.glob(sys.argv[1]+'/events*')[0]);e.Reload();tags=['loss/external_als_depth_huber','loss_weight/external_als_depth','loss_weight/external_als_normal','stats/external_als_depth_valid_pixel_count'];print(json.dumps({k:max(x.value for x in e.Scalars(k)) for k in tags}))"
    scalar = subprocess.run(base.docker_base() + ["python", "-c", check, container_path(root / "tb")], text=True, capture_output=True)
    scalars = json.loads(next(line for line in reversed(scalar.stdout.splitlines()) if line.startswith("{"))) if scalar.returncode == 0 else {}
    text = log.read_text(errors="replace")
    passed = proc.returncode == 0 and "avg 2.0 neighbors/view" in text and "[done]" in text and scalars.get("loss/external_als_depth_huber", 0) > 0 and abs(scalars.get("loss_weight/external_als_depth", 0) - .01) < 1e-7 and abs(scalars.get("loss_weight/external_als_normal", 1)) < 1e-8 and scalars.get("stats/external_als_depth_valid_pixel_count", 0) > 0
    base.atomic_json(receipt, {"schema": "jointbuildgs.p2.e4_local_4906982_55v_als_normal_ablation_v1.smoke.v1", "return_code": proc.returncode, "scalars": scalars, "neighbor_summary_found": "avg 2.0 neighbors/view" in text, "passed": passed, "scientific_verdict": None})
    if not passed: raise RuntimeError(f"depth-only smoke failed: {log}")
    print(receipt.read_text())


COMPARE_7K_CODE = r'''
import json,sys,torch
from pathlib import Path
a=torch.load(sys.argv[1],map_location='cpu',weights_only=False);b=torch.load(sys.argv[2],map_location='cpu',weights_only=False)
sections=['model','optimizers','schedulers','strategy','grouping','rng','loss_cursor']
def eq(x,y):
 if torch.is_tensor(x):return torch.equal(x,y)
 if isinstance(x,dict):return x.keys()==y.keys() and all(eq(x[k],y[k]) for k in x)
 if isinstance(x,(list,tuple)):return type(x)==type(y) and len(x)==len(y) and all(eq(i,j) for i,j in zip(x,y))
 return x==y
rows={k:eq(a.get(k),b.get(k)) for k in sections};body={'sections_equal':rows,'passed':all(rows.values()),'scientific_verdict':None};Path(sys.argv[3]).write_text(json.dumps(body,indent=2,sort_keys=True)+'\n');print(json.dumps(body,indent=2));raise SystemExit(0 if body['passed'] else 2)
'''


def fork_7k() -> None:
    stable = TASK_ROOT / "control/effective_configs/als_depth_only.json"
    smoke_receipt = TASK_ROOT / "control/receipts/smoke.json"
    receipt = TASK_ROOT / "control/receipts/rebind_als_depth_only_r1.json"
    if not stable.is_file() or not smoke_receipt.is_file() or not json.loads(smoke_receipt.read_text()).get("passed"):
        raise RuntimeError("binding probe and passed smoke required")
    if not (receipt.is_file() and json.loads(receipt.read_text()).get("passed") and base.checkpoint_valid(RUN_ROOT, 7000)):
        if RUN_ROOT.exists(): raise RuntimeError(f"incomplete target run requires review: {RUN_ROOT}")
        destination = RUN_ROOT / "ckpt/step_007000.pt"
        argv = base.docker_base() + ["python", "-c", depth_runner.REBIND_CODE, container_path(SOURCE_CHECKPOINT), container_path(destination), container_path(RUNTIME_CONFIG), Path(container_path(RUN_ROOT)), container_path(stable), container_path(receipt)]
        started = base.now(); proc = subprocess.run([str(x) for x in argv], text=True, capture_output=True)
        (TASK_ROOT / "logs/rebind_7k.log").write_text(proc.stdout + proc.stderr); base.record_operation("rebind_7k", [str(x) for x in argv], proc.returncode, started, base.now())
        if proc.returncode: raise RuntimeError("7k rebind failed")
    equality = TASK_ROOT / "control/depth_only_vs_full_e4_state_gate_7000.json"
    argv = base.docker_base() + ["python", "-c", COMPARE_7K_CODE, container_path(RUN_ROOT / "ckpt/step_007000.pt"), container_path(FULL_E4_RUN / "ckpt/step_007000.pt"), container_path(equality)]
    proc = subprocess.run(argv, text=True, capture_output=True); (TASK_ROOT / "logs/equality_vs_full_e4_7k.log").write_text(proc.stdout + proc.stderr)
    body = json.loads(receipt.read_text())
    gate = {"schema": "jointbuildgs.p2.e4_local_4906982_55v_als_normal_ablation_v1.common_state_gate.v1", "completed_updates": 7000,
            "source_learned_sections_equal": body["learned_sections_equal"], "full_e4_learned_sections_equal": json.loads(equality.read_text())["sections_equal"],
            "new_weights_at_update_7001": {"external_als_depth": .01, "external_als_normal": 0.0}, "passed": body["passed"] and proc.returncode == 0, "scientific_verdict": None}
    base.atomic_json(TASK_ROOT / "control/common_state_gate_7000.json", gate)
    if not gate["passed"]: raise RuntimeError("7k exact-state equality gate failed")
    ensure_owner(); print(json.dumps(gate, indent=2))


def mark_training_started() -> None:
    path = TASK_ROOT / "experiment_contract.json"; body = json.loads(path.read_text()); body.update({"status": "TRAINING_STARTED", "training_experiments_started": 1}); base.atomic_json(path, body)


def train_to_12k() -> None:
    gate = TASK_ROOT / "control/common_state_gate_7000.json"
    if not gate.is_file() or not json.loads(gate.read_text()).get("passed"): raise RuntimeError("passed 7k gate required")
    ensure_owner(); mark_training_started(); result = base._launch_training("train_ALS_DEPTH_ONLY_R1_to12k", RUN_ROOT, RUNTIME_CONFIG, stop_step=12000)
    if not base.checkpoint_valid(RUN_ROOT, 12000): raise RuntimeError("12k checkpoint missing")
    print(json.dumps(result, indent=2))


DOSE_GATE_CODE = r'''
import json,math,sys,torch
from pathlib import Path
from tensorboard.backend.event_processing.event_accumulator import EventAccumulator
runs={'FUSED_VIS_CONF':Path(sys.argv[1]),'ALS_DEPTH_ONLY':Path(sys.argv[2]),'E4_ALS_PRIOR_ONLY':Path(sys.argv[3])};rows={}
for name,run in runs.items():
 p=torch.load(run/'ckpt/step_012000.pt',map_location='cpu',weights_only=False);z=p['model']['state_dict']['means'][:,2].float();tb={}
 for f in sorted((run/'tb').glob('events*')):
  e=EventAccumulator(str(f));e.Reload()
  for tag in e.Tags()['scalars']:tb.setdefault(tag,{}).update({int(x.step):float(x.value) for x in e.Scalars(tag)})
 def latest(tag):
  d=tb.get(tag,{});ks=[k for k in d if k<=12000];return None if not ks else {'step':max(ks),'value':d[max(ks)]}
 rows[name]={'gaussian_count':int(len(z)),'z_gt_650_count':int((z>46).sum()),'eval_psnr':latest('eval/psnr'),'als_depth_loss':latest('loss/external_als_depth_huber'),'als_normal_weight':latest('loss_weight/external_als_normal'),'als_valid_pixels':latest('stats/external_als_depth_valid_pixel_count')}
vals=[x['value'] for row in rows.values() for x in row.values() if isinstance(x,dict) and x is not None];delta=rows['ALS_DEPTH_ONLY']['eval_psnr']['value']-rows['FUSED_VIS_CONF']['eval_psnr']['value'];passed=all(math.isfinite(x) for x in vals) and rows['ALS_DEPTH_ONLY']['gaussian_count']<=800000 and delta>=-5 and (rows['ALS_DEPTH_ONLY']['als_depth_loss'] or {}).get('value',0)>0 and (rows['ALS_DEPTH_ONLY']['als_valid_pixels'] or {}).get('value',0)>0 and abs((rows['ALS_DEPTH_ONLY']['als_normal_weight'] or {}).get('value',99))<1e-8
body={'schema':'jointbuildgs.p2.e4_local_4906982_55v_als_normal_ablation_v1.dose_gate.v1','rows':rows,'held_out_psnr_delta_depth_only_minus_control_db':delta,'passed':passed,'scientific_verdict':None};Path(sys.argv[4]).write_text(json.dumps(body,indent=2,sort_keys=True)+'\n');print(json.dumps(body,indent=2));raise SystemExit(0 if passed else 2)
'''


def dose_gate() -> None:
    for run in (SOURCE_RUN, RUN_ROOT, FULL_E4_RUN):
        if not base.checkpoint_valid(run, 12000): raise RuntimeError(f"12k checkpoint missing: {run}")
    output = TASK_ROOT / "control/dose_safety_gate_12000.json"
    argv = base.docker_base() + ["python", "-c", DOSE_GATE_CODE, container_path(SOURCE_RUN), container_path(RUN_ROOT), container_path(FULL_E4_RUN), container_path(output)]
    started = base.now(); proc = subprocess.run(argv, text=True, capture_output=True); base.record_operation("dose_safety_gate_12000", argv, proc.returncode, started, base.now())
    (TASK_ROOT / "logs/dose_safety_gate_12000.log").write_text(proc.stdout + proc.stderr)
    if proc.returncode: raise RuntimeError("12k dose gate failed; training stopped")
    print(proc.stdout)


def train() -> None:
    gate = TASK_ROOT / "control/dose_safety_gate_12000.json"
    if not gate.is_file() or not json.loads(gate.read_text()).get("passed"): raise RuntimeError("passed 12k gate required")
    ensure_owner(); result = base._launch_training("train_ALS_DEPTH_ONLY_R1_to20k", RUN_ROOT, RUNTIME_CONFIG, stop_step=None)
    missing = [step for step in CHECKPOINTS if not base.checkpoint_valid(RUN_ROOT, step)]
    if missing: raise RuntimeError(f"missing checkpoints: {missing}")
    path = TASK_ROOT / "experiment_contract.json"; body = json.loads(path.read_text()); body["status"] = "TRAINING_COMPLETE_EVALUATION_PENDING"; base.atomic_json(path, body)
    print(json.dumps(result, indent=2))


def prepare_control_proxy() -> None:
    ensure_owner(); root = TASK_ROOT / "arms/FUSED_VIS_CONF/R1"
    for relative in ("ckpt", "tb"): (root / relative).mkdir(parents=True, exist_ok=True)
    for step in CHECKPOINTS:
        for suffix in (".pt", ".pt.sha256"):
            source = SOURCE_RUN / "ckpt" / f"step_{step:06d}{suffix}"; target = root / "ckpt" / source.name
            if target.is_symlink() and target.resolve() != source.resolve(): raise RuntimeError(f"proxy drift: {target}")
            if not target.exists() and not target.is_symlink(): target.symlink_to(os.path.relpath(source, target.parent))
    for source in sorted((SOURCE_RUN / "tb").glob("events*")):
        target = root / "tb" / source.name
        if not target.exists() and not target.is_symlink(): target.symlink_to(os.path.relpath(source, target.parent))
    cfg = control_config(); cfg.update({"task_id": TASK_ID, "run_id": "FUSED_VIS_CONF_R1_REUSED_CONTROL", "out_dir": container_path(root), "full_state_resume": "off", "scientific_verdict": None})
    base.atomic_text(TASK_ROOT / "control/runtime_configs/fused_vis_conf_r1.yaml", yaml.safe_dump(cfg, sort_keys=False))
    source_receipt = SOURCE_TASK / "control/receipts/train_FUSED_VIS_CONF_R1.json"; control_receipt = json.loads(source_receipt.read_text()); control_receipt.update({"reused_control": True, "source_run": str(SOURCE_RUN), "scientific_verdict": None})
    base.atomic_json(TASK_ROOT / "control/receipts/train_FUSED_VIS_CONF_R1.json", control_receipt)
    target_receipt = TASK_ROOT / "control/receipts/train_ALS_DEPTH_ONLY_R1.json"
    if not target_receipt.is_file():
        one = json.loads((TASK_ROOT / "control/receipts/train_ALS_DEPTH_ONLY_R1_to12k.json").read_text()); two = json.loads((TASK_ROOT / "control/receipts/train_ALS_DEPTH_ONLY_R1_to20k.json").read_text())
        base.atomic_json(target_receipt, {"label": "train_ALS_DEPTH_ONLY_R1", "started_utc": one["started_utc"], "ended_utc": two["ended_utc"], "wall_seconds": float(one["wall_seconds"])+float(two["wall_seconds"]), "max_selected_gpu_used_mib": max(one["max_selected_gpu_used_mib"],two["max_selected_gpu_used_mib"]), "return_code": two["return_code"], "required_checkpoint_valid": True, "segments": [one,two], "scientific_verdict": None})
    base.atomic_json(TASK_ROOT / "control/control_proxy.json", {"source_run": str(SOURCE_RUN), "source_modified": False, "scientific_verdict": None})


def adapt(code: str) -> str:
    result = code.replace("'MVC05'", "'ALS_DEPTH_ONLY'").replace("'MVC0'", "'FUSED_VIS_CONF'")
    result = result.replace("MVC05", "ALS_DEPTH_ONLY").replace("MVC0", "FUSED_VIS_CONF")
    result = result.replace("mvc05_r1.yaml", "als_depth_only_r1.yaml").replace("mvc0_r1.yaml", "fused_vis_conf_r1.yaml")
    result = result.replace("'metric/psnr_train','eval/psnr','loss/mvc'", "'metric/psnr_train','eval/psnr','loss/depth','loss_weight/depth','loss/mvc','loss/external_als_depth_huber','loss_weight/external_als_normal','stats/external_als_depth_valid_pixel_count'")
    result = result.replace("replicas=['R1','R2','R3']", "replicas=['R1']").replace("reps=['R1','R2','R3']", "reps=['R1']").replace("['R1','R2','R3']", "['R1']")
    result = result.replace("'replicates_per_arm':3", "'replicates_per_arm':1").replace("ddof=1", "ddof=0")
    result = result.replace("mvc05_minus_mvc0", "als_depth_only_minus_fused_vis_conf").replace("paired_mvc05_minus_mvc0", "paired_als_depth_only_minus_fused_vis_conf")
    result = result.replace("mvc_weight=0.0 if arm=='FUSED_VIS_CONF' or step<=7000 else .5", "mvc_weight=0.0 if step<=7000 else .5")
    for old,new in (("'cases':24","'cases':8"),("'classification_passed':24","'classification_passed':8"),("'roofer_return_code_zero':24","'roofer_return_code_zero':8"),("'roofer_rf_success_true':24","'roofer_rf_success_true':8"),("'roofer_cases':24","'roofer_cases':8")): result = result.replace(old,new)
    result = result.replace("def mean(v):return sum(v)/len(v)", "def mean(v):return None if not v else sum(v)/len(v)")
    result = result.replace("def sd(v):return statistics.stdev(v) if len(v)>1 else 0.0", "def sd(v):return None if not v else (statistics.stdev(v) if len(v)>1 else 0.0)")
    return result


def analyze_checkpoints() -> None:
    prepare_control_proxy(); base.ANALYZE_CODE = adapt(base.ANALYZE_CODE); base.analyze_checkpoints()


def stage3() -> None:
    prepare_control_proxy(); base.STAGE3_PREP_CODE = adapt(base.STAGE3_PREP_CODE); base.STAGE3_VERIFY_CODE = adapt(base.STAGE3_VERIFY_CODE); base.ROOFER_RECORD_CODE = adapt(base.ROOFER_RECORD_CODE); base.run_stage3()


def finalize_measurements() -> None:
    base.FINALIZE_CODE = adapt(base.FINALIZE_CODE); base.finalize_measurements()


def main() -> None:
    parser = argparse.ArgumentParser(); parser.add_argument("command", choices=("preflight","binding-probe","smoke","fork-7k","train-to-12k","dose-gate","train","analyze-checkpoints","stage3","finalize-measurements"))
    globals()[parser.parse_args().command.replace("-", "_")]()


if __name__ == "__main__":
    main()
