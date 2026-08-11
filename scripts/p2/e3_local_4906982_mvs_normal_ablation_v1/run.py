#!/usr/bin/env python3
"""One-arm MVS-normal ablation branched exactly from FUSED_VIS_CONF at 7k."""
from __future__ import annotations

import argparse
import csv
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
TASK_ID = "P2-E3-LOCAL-4906982-MVS-NORMAL-ABLATION-v1"
TASK_ROOT = ARTIFACT_ROOT / "phase-payloads/p2/e3_local_4906982_mvs_normal_ablation_v1" / TASK_ID
CONFIG_DIR = REPO / "configs/p2/e3_local_4906982_mvs_normal_ablation_v1"
COMMON_CONFIG = CONFIG_DIR / "common.yaml"
ARM_CONFIG = CONFIG_DIR / "mvs_depth_normal.yaml"
VIEWER_CONFIG = CONFIG_DIR / "viewer.yaml"
DEPTH_BASE_CONFIG = REPO / "configs/p2/e3_local_4906982_mvc_depth_v1/depth03.yaml"
FUSED_ARM_CONFIG = REPO / "configs/p2/e3_local_4906982_fused_vis_conf_v1/fused_vis_conf.yaml"
SOURCE_TASK = ARTIFACT_ROOT / "phase-payloads/p2/e3_local_4906982_fused_vis_conf_v1/P2-E3-LOCAL-4906982-FUSED-VIS-CONF-v1"
SOURCE_RUN = SOURCE_TASK / "arms/FUSED_VIS_CONF/R1"
SOURCE_CHECKPOINT = SOURCE_RUN / "ckpt/step_007000.pt"
RAW_CROP = ARTIFACT_ROOT / "phase-payloads/p2/e3_local_4906982_v1/P2-E3-LOCAL-4906982-2DGS-v6-dist0-resetoff-30k/data/colmap_crop"
RUN_ROOT = TASK_ROOT / "arms/FUSED_VIS_CONF_MVS_NORMAL/R1"
RUNTIME_CONFIG = TASK_ROOT / "control/runtime_configs/fused_vis_conf_mvs_normal_r1.yaml"
ARMS = ("FUSED_VIS_CONF", "FUSED_VIS_CONF_MVS_NORMAL")
CHECKPOINTS = (7000, 12000, 15000, 20000)


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None: raise RuntimeError(path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module); return module


surface = load_module("mvs_surface_runner_for_mvs_normal", REPO / "scripts/p2/e3_local_4906982_mvs_surface_depth_v1/run.py")
depth_runner = surface.depth_runner
base = surface.base
base.TASK_ID = TASK_ID; base.TASK_ROOT = TASK_ROOT; base.GPU = "1"
base.ARMS = ARMS; base.REPLICAS = ("R1",); base.CHECKPOINTS = CHECKPOINTS


def sha256(path: Path) -> str: return base.sha256(path)
def container_path(path: Path) -> str: return base.container_path(path)


def control_config() -> dict[str, Any]:
    body = yaml.safe_load(DEPTH_BASE_CONFIG.read_text())
    body.update(yaml.safe_load(FUSED_ARM_CONFIG.read_text())["overrides"])
    body.update({"full_state_checkpoint": True, "full_state_checkpoint_steps": list(CHECKPOINTS), "full_state_resume": "auto", "full_state_resume_strict_cuda_rng": True, "official_PASS_usable": None, "scientific_verdict": None})
    return body


def target_config() -> dict[str, Any]:
    body = control_config(); body.update(yaml.safe_load(ARM_CONFIG.read_text())["overrides"])
    body.update({"official_PASS_usable": None, "scientific_verdict": None}); return body


def changed(left: dict[str, Any], right: dict[str, Any]) -> list[str]:
    return sorted(key for key in set(left) | set(right) if left.get(key) != right.get(key))


def ensure_owner() -> None:
    if TASK_ROOT.exists(): subprocess.run(base.docker_base() + ["chown", "-R", f"{os.getuid()}:{os.getgid()}", container_path(TASK_ROOT)], check=True)


def viewer_root() -> Path:
    value = yaml.safe_load(VIEWER_CONFIG.read_text())["viewer_root"]
    return Path(value.replace("/artifacts/JointBuildGS", str(ARTIFACT_ROOT), 1))


def preflight() -> None:
    for relative in ("control/runtime_configs", "control/effective_configs", "control/receipts", "logs", "cache/torch_extensions", "representative_images"):
        (TASK_ROOT / relative).mkdir(parents=True, exist_ok=True)
    definition = TASK_ROOT / "mvs_normal_target_definition.json"
    required = [COMMON_CONFIG, ARM_CONFIG, VIEWER_CONFIG, DEPTH_BASE_CONFIG, FUSED_ARM_CONFIG, definition,
                TASK_ROOT / "mvs_normal_preflight_metrics.csv", SOURCE_CHECKPOINT, Path(str(SOURCE_CHECKPOINT) + ".sha256"),
                REPO / "src/stage2/train.py", REPO / "src/stage2/dataloader.py", REPO / "src/stage2/loss/data_fitting.py", REPO / "src/stage2/loss/multiview.py"]
    for path in required:
        if not path.is_file(): raise FileNotFoundError(path)
    normal_definition = json.loads(definition.read_text())
    if normal_definition.get("status") != "GATE_PASSED" or not all(normal_definition.get("gate_checks", {}).values()):
        raise RuntimeError("MVS normal frame/support gate is not passed")
    if not base.checkpoint_valid(SOURCE_RUN, 7000): raise RuntimeError("source 7k checkpoint sidecar failed")
    control, target = control_config(), target_config(); actual = changed(control, target)
    expected = sorted(("task_id", "run_id", "data_root", "out_dir", "load_normal", "normal_dir", "normal_prior_orientation", "w_normal", "normal_warmup", "normal_schedule", "normal_ramp_steps"))
    if actual != expected: raise RuntimeError(f"normal-only config gate failed: {actual} != {expected}")
    locked = {"seed": 0, "downscale": 1.0, "load_depth": True, "depth_supervision_mode": "expected", "depth_loss_type": "l1",
              "w_depth": .03, "depth_warmup": 7000, "depth_schedule": "ramp", "depth_ramp_steps": 5000,
              "w_mvc": .5, "w_nc": .05, "w_distort": 0.0, "max_iter": 20000,
              "load_normal": True, "normal_prior_orientation": "unsigned", "w_normal": .005,
              "normal_warmup": 7000, "normal_schedule": "ramp", "normal_ramp_steps": 5000}
    mismatch = {key: [target.get(key), value] for key, value in locked.items() if target.get(key) != value}
    if mismatch or len(target["visible_views"]) != 55 or len(target["train_views"]) != 47 or len(target["eval_views"]) != 8:
        raise RuntimeError(f"locked config mismatch: {mismatch}")
    base.atomic_text(RUNTIME_CONFIG, yaml.safe_dump(target, sort_keys=False))
    diff = "\n".join([
        "comparison: existing FUSED_VIS_CONF/R1 versus new FUSED_VIS_CONF_MVS_NORMAL/R1",
        "branch: exact FUSED_VIS_CONF full-state checkpoint at completed update 7000",
        "single scientific intervention: add supported COLMAP geometric normal supervision",
        "normal: canonical Fortran-order decode, camera-to-world, sign-invariant 1-|dot|, weight=0.005, ramp 7k+5k",
        "support: exact FUSED_VIS_CONF positive-finite depth mask; 46/47 train views have support",
        "unchanged: initialization/history through 7k, FUSED_VIS_CONF depth target/mask/L1/weight/schedule, expected rendered depth, MVC, NC, densification, 55 views, seed, GPU",
        "changed config keys: " + ", ".join(actual), "LoD2 Z/RoofSurface/roof type training use: none", "scientific_verdict: null", ""])
    base.atomic_text(TASK_ROOT / "config_diff.txt", diff)
    data_root = Path(target["data_root"].replace("/artifacts/JointBuildGS", str(ARTIFACT_ROOT), 1))
    normal_root = Path(target["normal_dir"].replace("/artifacts/JointBuildGS", str(ARTIFACT_ROOT), 1))
    # Task-local links intentionally store canonical container paths, which are
    # not host-resolvable. Hash their immutable host-side sources directly.
    source_data_root = SOURCE_TASK / "data/fused_vis_conf_colmap_crop"
    depths = sorted((source_data_root / "depth").glob("*.exr")); normals = sorted(normal_root.glob("*.npy"))
    if len(depths) != 55 or len(normals) != 55: raise RuntimeError(f"expected 55 depth/normal maps, got {len(depths)}/{len(normals)}")
    sparse_root = RAW_CROP / "sparse/0"
    input_hashes = {
        "schema": "jointbuildgs.p2.e3_local_4906982_mvs_normal_ablation_v1.inputs.v1",
        "source_7k_checkpoint": {"path": str(SOURCE_CHECKPOINT), "sha256": sha256(SOURCE_CHECKPOINT)},
        "source_fused_vis_conf_inputs": {"path": str(SOURCE_TASK / "input_hashes.json"), "sha256": sha256(SOURCE_TASK / "input_hashes.json")},
        "crop_camera_sparse_sha256": {name: sha256(sparse_root / name) for name in ("cameras.bin", "images.bin", "points3D.bin")},
        "fused_vis_conf_depth_sha256": {path.name: sha256(path) for path in depths},
        "mvs_normal_world_sha256": {path.name: sha256(path) for path in normals},
        "normal_target_definition": {"path": str(definition), "sha256": sha256(definition)},
        "reuse": {"crop_regenerated": False, "cameras_regenerated": False, "view_roles_regenerated": False, "sparse_seed_regenerated": False, "mvs_depth_regenerated": False},
        "scientific_verdict": None,
    }
    base.atomic_json(TASK_ROOT / "input_hashes.json", input_hashes)
    contract = {
        "schema": "jointbuildgs.p2.e3_local_4906982_mvs_normal_ablation_v1.contract.v1", "task_id": TASK_ID,
        "building_id": "DEBY_LOD2_4906982", "status": "PREFLIGHT_BOUND", "non_confirmatory": True,
        "question": "On the fixed 55-view FUSED_VIS_CONF base, does supported MVS normal supervision improve usable building geometry and Roofer read-out?",
        "comparison": {"control": "existing FUSED_VIS_CONF/R1", "intervention": "FUSED_VIS_CONF_MVS_NORMAL/R1"},
        "single_intervention": "supported MVS normal supervision", "source_completed_updates": 7000,
        "first_intervention_update": 7001, "checkpoints": list(CHECKPOINTS), "selected_gpu": 1,
        "training_experiments_started": 0, "new_loss": False, "multiview_densification": False, "lod2_training_use": False,
        "scientific_verdict": None,
    }
    base.atomic_json(TASK_ROOT / "experiment_contract.json", contract)
    sources = [Path(__file__), REPO / "scripts/p2/e3_local_4906982_mvs_normal_ablation_v1/prepare_normal.py", COMMON_CONFIG, ARM_CONFIG, VIEWER_CONFIG,
               REPO / "src/stage2/train.py", REPO / "src/stage2/dataloader.py", REPO / "src/stage2/loss/data_fitting.py", REPO / "src/stage2/loss/multiview.py"]
    previous_path = TASK_ROOT / "provenance.json"; previous = json.loads(previous_path.read_text()) if previous_path.is_file() else {}
    base.atomic_json(previous_path, {"schema": "jointbuildgs.p2.e3_local_4906982_mvs_normal_ablation_v1.provenance.v1", "task_id": TASK_ID,
        "git": base.git_record(), "docker_image": base.image_record(), "gpu": base.gpu_record(),
        "source_config_sha256": {str(path.relative_to(REPO)): sha256(path) for path in sources}, "input_hashes_sha256": sha256(TASK_ROOT / "input_hashes.json"),
        "random_seed": 0, "started_utc": previous.get("started_utc") or base.now(), "ended_utc": None,
        "commands": previous.get("commands", []), "return_codes": previous.get("return_codes", []), "scientific_verdict": None})
    base.atomic_text(TASK_ROOT / "NOTES.md", f"# {TASK_ID}\n\nStatus: `PREFLIGHT_BOUND`. One new MVS-normal arm; existing FUSED_VIS_CONF is read-only control.\n\nscientific_verdict: null\n")
    footprint_source = SOURCE_TASK / "control/shared_standard_footprint_4906982.geojson"; footprint_target = TASK_ROOT / "control/shared_standard_footprint_4906982.geojson"
    if footprint_target.exists() and sha256(footprint_target) != sha256(footprint_source): raise RuntimeError("footprint drift")
    if not footprint_target.exists(): shutil.copy2(footprint_source, footprint_target)
    root = viewer_root(); fixed = yaml.safe_load(VIEWER_CONFIG.read_text())["root_files_must_remain_unchanged"]
    base.atomic_json(TASK_ROOT / "control/viewer_root_precondition.json", {"viewer_root": str(root), "fixed_file_sha256": {name: sha256(root / name) for name in fixed}, "scientific_verdict": None})
    print(diff, end="")


def binding_probe() -> None:
    stable = TASK_ROOT / "control/effective_configs/fused_vis_conf_mvs_normal.json"
    if stable.is_file(): print(stable.read_text()); return
    cfg = target_config(); cfg.update({"run_id": "BINDING_PROBE_MVS_NORMAL", "out_dir": container_path(TASK_ROOT / "binding_probe"), "max_iter": 1, "eval_every": 100000, "ckpt_every": 100000, "full_state_resume": "off"})
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
    if receipt.is_file() and json.loads(receipt.read_text()).get("passed"): print(receipt.read_text()); return
    cfg = target_config(); root = TASK_ROOT / "smoke"
    cfg.update({"run_id": "SMOKE_MVS_NORMAL", "out_dir": container_path(root), "max_iter": 12, "eval_every": 100000, "ckpt_every": 100000,
                "full_state_resume": "off", "full_state_checkpoint": False, "full_state_checkpoint_steps": [],
                "mvc_warmup": 0, "mvc_ramp_steps": 1, "depth_warmup": 0, "depth_ramp_steps": 1,
                "normal_warmup": 0, "normal_ramp_steps": 1, "loss_grad_audit_every": 1, "refine_start_iter": 500})
    path = TASK_ROOT / "control/runtime_configs/smoke.yaml"; base.atomic_text(path, yaml.safe_dump(cfg, sort_keys=False))
    argv = base.docker_base(gpu=True) + ["python", "-c", base.DETERMINISTIC_WRAPPER, "--config", container_path(path)]
    log = TASK_ROOT / "logs/smoke.log"; started = base.now()
    with log.open("w") as stream: proc = subprocess.run(argv, text=True, stdout=stream, stderr=subprocess.STDOUT)
    base.record_operation("smoke", argv, proc.returncode, started, base.now())
    rows = list(csv.DictReader((root / "audit/loss_grad_norms.csv").open())) if (root / "audit/loss_grad_norms.csv").is_file() else []
    normal_rows = [row for row in rows if row["component"] == "normal"]
    scalars: dict[str, float] = {}
    code = "from tensorboard.backend.event_processing.event_accumulator import EventAccumulator as E;import glob,json,sys;e=E(glob.glob(sys.argv[1]+'/events*')[0]);e.Reload();tags=['loss/normal','loss_weight/normal','stats/normal_prior_valid_pixel_count'];print(json.dumps({k:max(x.value for x in e.Scalars(k)) for k in tags if k in e.Tags()['scalars']}))"
    scalar = subprocess.run(base.docker_base() + ["python", "-c", code, container_path(root / "tb")], text=True, capture_output=True)
    if scalar.returncode == 0: scalars = json.loads(next(line for line in reversed(scalar.stdout.splitlines()) if line.startswith("{")))
    normal_grad = max((float(row["grad_norm"]) for row in normal_rows), default=0.0)
    text = log.read_text(errors="replace")
    resolved_normals = "normal maps on 55/55" in text
    passed = proc.returncode == 0 and "avg 2.0 neighbors/view" in text and "[done]" in text and resolved_normals and normal_grad > 0 and scalars.get("loss/normal", 0) > 0 and scalars.get("loss_weight/normal", 0) > 0
    base.atomic_json(receipt, {"schema": "jointbuildgs.p2.e3_local_4906982_mvs_normal_ablation_v1.smoke.v1", "return_code": proc.returncode, "scalars": scalars, "normal_grad_norm_max": normal_grad, "resolved_normal_maps_55_of_55": resolved_normals, "unsigned_valid_pixel_tag_expected": False, "target_valid_pixels_from_frozen_preflight": json.loads((TASK_ROOT / "mvs_normal_target_definition.json").read_text())["target_valid_pixels"], "passed": passed, "scientific_verdict": None})
    if not passed: raise RuntimeError(f"MVS normal smoke failed: {log}")
    print(receipt.read_text())


def fork_7k() -> None:
    stable = TASK_ROOT / "control/effective_configs/fused_vis_conf_mvs_normal.json"; smoke_receipt = TASK_ROOT / "control/receipts/smoke.json"
    if not stable.is_file() or not smoke_receipt.is_file() or not json.loads(smoke_receipt.read_text()).get("passed"): raise RuntimeError("binding probe and smoke required")
    receipt = TASK_ROOT / "control/receipts/rebind_fused_vis_conf_mvs_normal_r1.json"
    if not (receipt.is_file() and json.loads(receipt.read_text()).get("passed") and base.checkpoint_valid(RUN_ROOT, 7000)):
        if RUN_ROOT.exists(): raise RuntimeError(f"incomplete target run requires review: {RUN_ROOT}")
        destination = RUN_ROOT / "ckpt/step_007000.pt"
        argv = base.docker_base() + ["python", "-c", depth_runner.REBIND_CODE, container_path(SOURCE_CHECKPOINT), container_path(destination), container_path(RUNTIME_CONFIG), Path(container_path(RUN_ROOT)), container_path(stable), container_path(receipt)]
        started = base.now(); proc = subprocess.run([str(x) for x in argv], text=True, capture_output=True)
        (TASK_ROOT / "logs/rebind_7k.log").write_text(proc.stdout + proc.stderr); base.record_operation("rebind_7k", [str(x) for x in argv], proc.returncode, started, base.now())
        if proc.returncode: raise RuntimeError("7k rebind failed")
    body = json.loads(receipt.read_text())
    gate = {"schema": "jointbuildgs.p2.e3_local_4906982_mvs_normal_ablation_v1.common_state_gate.v1", "completed_updates": 7000,
            "source": str(SOURCE_CHECKPOINT), "learned_sections_equal": body["learned_sections_equal"],
            "new_normal_weight_at_update_7000": 0.0, "first_nonzero_after_update": 7000,
            "passed": body["passed"] and all(body["learned_sections_equal"].values()), "scientific_verdict": None}
    base.atomic_json(TASK_ROOT / "control/common_state_gate_7000.json", gate)
    if not gate["passed"]: raise RuntimeError("7k equality gate failed")
    ensure_owner(); print(json.dumps(gate, indent=2))


def mark_training_started() -> None:
    path = TASK_ROOT / "experiment_contract.json"; body = json.loads(path.read_text()); body.update({"status": "TRAINING_STARTED", "training_experiments_started": 1}); base.atomic_json(path, body)


def train_to_12k() -> None:
    gate = TASK_ROOT / "control/common_state_gate_7000.json"
    if not gate.is_file() or not json.loads(gate.read_text()).get("passed"): raise RuntimeError("passed 7k gate required")
    ensure_owner(); mark_training_started(); result = base._launch_training("train_FUSED_VIS_CONF_MVS_NORMAL_R1_to12k", RUN_ROOT, RUNTIME_CONFIG, stop_step=12000)
    if not base.checkpoint_valid(RUN_ROOT, 12000): raise RuntimeError("12k checkpoint missing")
    print(json.dumps(result, indent=2))


def dose_gate() -> None:
    if not base.checkpoint_valid(RUN_ROOT, 12000): raise RuntimeError("12k checkpoint missing")
    code = r'''import json,math,sys,torch
from pathlib import Path
from tensorboard.backend.event_processing.event_accumulator import EventAccumulator
run=Path(sys.argv[1]);out=Path(sys.argv[2]);definition=json.loads(Path(sys.argv[3]).read_text());p=torch.load(run/'ckpt/step_012000.pt',map_location='cpu',weights_only=False);z=p['model']['state_dict']['means'][:,2].float();tb={}
for f in sorted((run/'tb').glob('events*')):
 e=EventAccumulator(str(f));e.Reload()
 for tag in e.Tags()['scalars']:tb.setdefault(tag,{}).update({int(x.step):float(x.value) for x in e.Scalars(tag)})
def latest(tag):
 d=tb.get(tag,{});k=max((x for x in d if x<=12000),default=None);return None if k is None else {'step':k,'value':d[k]}
rows={'gaussian_count':int(len(z)),'z_local_gt_46_count':int((z>46).sum()),'eval_psnr':latest('eval/psnr'),'normal_loss':latest('loss/normal'),'normal_weight':latest('loss_weight/normal'),'normal_valid_pixels_frozen_preflight':int(definition['target_valid_pixels'])}
vals=[x['value'] for x in rows.values() if isinstance(x,dict) and x is not None];passed=all(math.isfinite(x) for x in vals) and rows['gaussian_count']<=800000 and (rows['normal_loss'] or {}).get('value',0)>0 and (rows['normal_weight'] or {}).get('value',0)>0 and rows['normal_valid_pixels_frozen_preflight']>0
body={'schema':'jointbuildgs.p2.e3_local_4906982_mvs_normal_ablation_v1.dose_gate.v1','rows':rows,'passed':passed,'scientific_verdict':None};out.write_text(json.dumps(body,indent=2,sort_keys=True)+'\n');print(json.dumps(body,indent=2));raise SystemExit(0 if passed else 2)'''
    output = TASK_ROOT / "control/dose_safety_gate_12000.json"; argv = base.docker_base() + ["python", "-c", code, container_path(RUN_ROOT), container_path(output), container_path(TASK_ROOT / "mvs_normal_target_definition.json")]
    started = base.now(); proc = subprocess.run(argv, text=True, capture_output=True); base.record_operation("dose_safety_gate_12000", argv, proc.returncode, started, base.now())
    (TASK_ROOT / "logs/dose_safety_gate_12000.log").write_text(proc.stdout + proc.stderr)
    if proc.returncode: raise RuntimeError("12k dose gate failed")
    print(proc.stdout)


def train() -> None:
    gate = TASK_ROOT / "control/dose_safety_gate_12000.json"
    if not gate.is_file() or not json.loads(gate.read_text()).get("passed"): raise RuntimeError("passed 12k gate required")
    ensure_owner(); result = base._launch_training("train_FUSED_VIS_CONF_MVS_NORMAL_R1_to20k", RUN_ROOT, RUNTIME_CONFIG, stop_step=None)
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
    receipt = json.loads((SOURCE_TASK / "control/receipts/train_FUSED_VIS_CONF_R1.json").read_text()); receipt.update({"reused_control": True, "source_run": str(SOURCE_RUN), "scientific_verdict": None})
    base.atomic_json(TASK_ROOT / "control/receipts/train_FUSED_VIS_CONF_R1.json", receipt)
    target_receipt = TASK_ROOT / "control/receipts/train_FUSED_VIS_CONF_MVS_NORMAL_R1.json"
    if not target_receipt.is_file():
        one = json.loads((TASK_ROOT / "control/receipts/train_FUSED_VIS_CONF_MVS_NORMAL_R1_to12k.json").read_text()); two = json.loads((TASK_ROOT / "control/receipts/train_FUSED_VIS_CONF_MVS_NORMAL_R1_to20k.json").read_text())
        base.atomic_json(target_receipt, {"label": "train_FUSED_VIS_CONF_MVS_NORMAL_R1", "started_utc": one["started_utc"], "ended_utc": two["ended_utc"], "wall_seconds": float(one["wall_seconds"]) + float(two["wall_seconds"]), "max_selected_gpu_used_mib": max(one["max_selected_gpu_used_mib"], two["max_selected_gpu_used_mib"]), "return_code": two["return_code"], "required_checkpoint_valid": True, "segments": [one, two], "scientific_verdict": None})
    base.atomic_json(TASK_ROOT / "control/control_proxy.json", {"source_run": str(SOURCE_RUN), "source_modified": False, "scientific_verdict": None})


def adapt(code: str) -> str:
    result = code.replace("'MVC05'", "'FUSED_VIS_CONF_MVS_NORMAL'").replace("'MVC0'", "'FUSED_VIS_CONF'")
    result = result.replace("MVC05", "FUSED_VIS_CONF_MVS_NORMAL").replace("MVC0", "FUSED_VIS_CONF")
    result = result.replace("mvc05_r1.yaml", "fused_vis_conf_mvs_normal_r1.yaml").replace("mvc0_r1.yaml", "fused_vis_conf_r1.yaml")
    result = result.replace("'metric/psnr_train','eval/psnr','loss/mvc'", "'metric/psnr_train','eval/psnr','loss/depth','loss_weight/depth','loss/normal','loss_weight/normal','stats/normal_prior_valid_pixel_count','loss/mvc'")
    result = result.replace("replicas=['R1','R2','R3']", "replicas=['R1']").replace("reps=['R1','R2','R3']", "reps=['R1']").replace("['R1','R2','R3']", "['R1']")
    result = result.replace("'replicates_per_arm':3", "'replicates_per_arm':1").replace("ddof=1", "ddof=0")
    result = result.replace("mvc05_minus_mvc0", "mvs_normal_minus_fused_vis_conf").replace("paired_mvc05_minus_mvc0", "paired_mvs_normal_minus_fused_vis_conf")
    result = result.replace("mvc_weight=0.0 if arm=='FUSED_VIS_CONF' or step<=7000 else .5", "mvc_weight=0.0 if step<=7000 else .5")
    for old, new in (("'cases':24", "'cases':8"), ("'classification_passed':24", "'classification_passed':8"), ("'roofer_return_code_zero':24", "'roofer_return_code_zero':8"), ("'roofer_rf_success_true':24", "'roofer_rf_success_true':8"), ("'roofer_cases':24", "'roofer_cases':8")): result = result.replace(old, new)
    result = result.replace("def mean(v):return sum(v)/len(v)", "def mean(v):return None if not v else sum(v)/len(v)")
    result = result.replace("def sd(v):return statistics.stdev(v) if len(v)>1 else 0.0", "def sd(v):return None if not v else (statistics.stdev(v) if len(v)>1 else 0.0)")
    return result


def analyze_checkpoints() -> None:
    prepare_control_proxy(); base.ANALYZE_CODE = adapt(base.ANALYZE_CODE); base.analyze_checkpoints()


def stage3() -> None:
    prepare_control_proxy(); base.STAGE3_PREP_CODE = adapt(base.STAGE3_PREP_CODE); base.STAGE3_VERIFY_CODE = adapt(base.STAGE3_VERIFY_CODE); base.ROOFER_RECORD_CODE = adapt(base.ROOFER_RECORD_CODE); base.run_stage3()


def finalize_measurements() -> None:
    base.FINALIZE_CODE = adapt(base.FINALIZE_CODE); base.finalize_measurements()


def mvs_surface_audit() -> None:
    surface.TASK_ID = TASK_ID; surface.TASK_ROOT = TASK_ROOT; surface.ARMS = ARMS; surface.REPLICAS = ("R1",); surface.CHECKPOINTS = CHECKPOINTS
    surface.mvs_surface_audit()


def main() -> None:
    parser = argparse.ArgumentParser(); parser.add_argument("command", choices=("preflight", "binding-probe", "smoke", "fork-7k", "train-to-12k", "dose-gate", "train", "analyze-checkpoints", "stage3", "mvs-surface-audit", "finalize-measurements"))
    globals()[parser.parse_args().command.replace("-", "_")]()


if __name__ == "__main__": main()
