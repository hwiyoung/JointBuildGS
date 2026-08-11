#!/usr/bin/env python3
"""Add-only exact-55 Existing-ALS prior arm branched from FUSED_VIS_CONF at 7k."""
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
TASK_ID = "P2-E4-LOCAL-4906982-55V-ALS-PRIOR-v1"
TASK_ROOT = ARTIFACT_ROOT / "phase-payloads/p2/e4_local_4906982_55v_als_prior_v1" / TASK_ID
CONFIG_DIR = REPO / "configs/p2/e4_local_4906982_55v_als_prior_v1"
COMMON_CONFIG = CONFIG_DIR / "common.yaml"
ARM_CONFIG = CONFIG_DIR / "als_prior_only.yaml"
SMRF_CONFIG = CONFIG_DIR / "smrf_diagnostic.json"
DEPTH_BASE_CONFIG = REPO / "configs/p2/e3_local_4906982_mvc_depth_v1/depth03.yaml"
FUSED_ARM_CONFIG = REPO / "configs/p2/e3_local_4906982_fused_vis_conf_v1/fused_vis_conf.yaml"
SOURCE_TASK = ARTIFACT_ROOT / "phase-payloads/p2/e3_local_4906982_fused_vis_conf_v1/P2-E3-LOCAL-4906982-FUSED-VIS-CONF-v1"
SOURCE_RUN = SOURCE_TASK / "arms/FUSED_VIS_CONF/R1"
SOURCE_CHECKPOINT = SOURCE_RUN / "ckpt/step_007000.pt"
SOURCE_INPUTS = SOURCE_TASK / "input_hashes.json"
PRIOR_RECEIPT = TASK_ROOT / "control/200-55v-als-prior-preflight-passed.json"
RUN_ROOT = TASK_ROOT / "arms/E4_ALS_PRIOR_ONLY/R1"
RUNTIME_CONFIG = TASK_ROOT / "control/runtime_configs/e4_als_prior_only_r1.yaml"
ARMS = ("FUSED_VIS_CONF", "E4_ALS_PRIOR_ONLY")
CHECKPOINTS = (7000, 12000, 15000, 20000)


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


surface = load_module("mvs_surface_runner_for_e4", REPO / "scripts/p2/e3_local_4906982_mvs_surface_depth_v1/run.py")
depth_runner = surface.depth_runner
base = surface.base
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


def materialized_control() -> dict[str, Any]:
    body = yaml.safe_load(DEPTH_BASE_CONFIG.read_text())
    body.update(yaml.safe_load(FUSED_ARM_CONFIG.read_text())["overrides"])
    body.update({
        "full_state_checkpoint": True,
        "full_state_checkpoint_steps": list(CHECKPOINTS),
        "full_state_resume": "auto",
        "full_state_resume_strict_cuda_rng": True,
        "official_PASS_usable": None,
        "scientific_verdict": None,
    })
    return body


def materialized() -> dict[str, Any]:
    body = materialized_control()
    body.update(yaml.safe_load(ARM_CONFIG.read_text())["overrides"])
    body.update({"official_PASS_usable": None, "scientific_verdict": None})
    return body


def changed(left: dict[str, Any], right: dict[str, Any]) -> list[str]:
    return sorted(key for key in set(left) | set(right) if left.get(key) != right.get(key))


def ensure_task_owner() -> None:
    if TASK_ROOT.exists():
        subprocess.run(base.docker_base() + ["chown", "-R", f"{os.getuid()}:{os.getgid()}", container_path(TASK_ROOT)], check=True)


def preflight() -> None:
    for relative in ("control/runtime_configs", "control/effective_configs", "control/receipts", "logs", "cache/torch_extensions", "representative_images"):
        (TASK_ROOT / relative).mkdir(parents=True, exist_ok=True)
    required = (
        COMMON_CONFIG, ARM_CONFIG, SMRF_CONFIG, DEPTH_BASE_CONFIG, FUSED_ARM_CONFIG,
        SOURCE_CHECKPOINT, Path(str(SOURCE_CHECKPOINT) + ".sha256"), SOURCE_INPUTS,
        PRIOR_RECEIPT, REPO / "src/stage2/train.py", REPO / "src/stage2/dataloader.py",
        REPO / "src/stage2/loss/data_fitting.py", REPO / "src/stage2/loss/multiview.py",
    )
    for path in required:
        if not path.is_file():
            raise FileNotFoundError(path)
    if not base.checkpoint_valid(SOURCE_RUN, 7000):
        raise RuntimeError("FUSED_VIS_CONF source 7k checkpoint sidecar failed")
    prior = json.loads(PRIOR_RECEIPT.read_text())
    if prior.get("status") != "200-PASSED_EXACT55_ALIGNMENT_PROJECTION_GRADIENT_AND_GPU_MEMORY_PREFLIGHT":
        raise RuntimeError("exact-55 ALS prior preflight is not passed")
    if prior["view_count"] != 55 or prior["nonempty_view_count"] != 55 or not prior["alignment"]["passed"] or not prior["gradient_and_gpu_memory"]["passed"]:
        raise RuntimeError("exact-55 ALS prior gate values drifted")
    for row in prior["view_receipts"]:
        path = TASK_ROOT / row["path"]
        if not path.is_file() or sha256(path) != row["sha256"]:
            raise RuntimeError(f"ALS prior file hash drift: {path}")

    control = materialized_control()
    target = materialized()
    base.atomic_text(RUNTIME_CONFIG, yaml.safe_dump(target, sort_keys=False))
    actual = changed(control, target)
    expected = sorted({
        "task_id", "run_id", "out_dir", "external_als_prior_dir",
        "w_external_als_depth", "w_external_als_normal", "external_als_huber_delta_m",
        "external_als_depth_loss", "external_als_normal_loss",
        "external_als_confidence_gates", "external_als_conflict_policy",
    })
    if actual != expected:
        raise RuntimeError(f"single-intervention config gate failed: {actual} != {expected}")
    locked = {
        "data_root": control["data_root"], "seed": 0, "downscale": 1.0,
        "load_depth": True, "load_normal": False, "depth_supervision_mode": "expected",
        "depth_loss_type": "l1", "w_depth": 0.03, "depth_warmup": 7000,
        "depth_schedule": "ramp", "depth_ramp_steps": 5000, "w_mvc": 0.5,
        "w_nc": 0.05, "w_distort": 0.0, "max_iter": 20000,
        "w_external_als_depth": 0.01, "w_external_als_normal": 0.005,
        "external_als_huber_delta_m": 1.0,
    }
    mismatch = {key: [target.get(key), value] for key, value in locked.items() if target.get(key) != value}
    if mismatch or len(target["visible_views"]) != 55 or len(target["train_views"]) != 47 or len(target["eval_views"]) != 8:
        raise RuntimeError(f"locked E4 config mismatch: {mismatch}")

    diff = "\n".join([
        "comparison: existing FUSED_VIS_CONF/R1 versus new E4_ALS_PRIOR_ONLY/R1",
        "branch: exact FUSED_VIS_CONF full-state checkpoint at completed update 7000",
        "single substantive intervention: add confidence-gated Existing-ALS metric camera-depth and sign-invariant normal prior",
        "ALS weights: depth=0.01, normal=0.005; Huber delta=1.0 m",
        "activation: first resumed optimizer update after the exact 7k state",
        "unchanged: 55 images, crop cameras, 47/8 roles, FUSED_VIS_CONF MVS depth, sparse initialization history, model/optimizer/RNG at 7k, MVC, NC, densification, seed, GPU",
        "changed config keys: " + ", ".join(actual),
        "LoD2 Z/RoofSurface/roof type training use: none",
        "scientific_verdict: null",
        "",
    ])
    base.atomic_text(TASK_ROOT / "config_diff.txt", diff)

    data_root = Path(target["data_root"].replace("/artifacts/JointBuildGS", str(ARTIFACT_ROOT), 1))
    sparse_link = data_root / "sparse"
    sparse_target = Path(os.readlink(sparse_link)).as_posix().replace("/artifacts/JointBuildGS", str(ARTIFACT_ROOT), 1)
    sparse_root = Path(sparse_target) / "0"
    depth_hashes = {path.name: sha256(path) for path in sorted((data_root / "depth").glob("*.exr"))}
    if len(depth_hashes) != 55:
        raise RuntimeError(f"expected 55 FUSED_VIS_CONF depth maps, got {len(depth_hashes)}")
    input_hashes = {
        "schema": "jointbuildgs.p2.e4_local_4906982_55v_als_prior_v1.inputs.v1",
        "source_fused_vis_conf_manifest": {"path": str(SOURCE_INPUTS), "sha256": sha256(SOURCE_INPUTS)},
        "source_7k_checkpoint": {"path": str(SOURCE_CHECKPOINT), "sha256": sha256(SOURCE_CHECKPOINT)},
        "crop_camera_sparse_sha256": {name: sha256(sparse_root / name) for name in ("cameras.bin", "images.bin", "points3D.bin")},
        "fused_vis_conf_depth_sha256": depth_hashes,
        "als_prior_preflight": {"path": str(PRIOR_RECEIPT), "sha256": sha256(PRIOR_RECEIPT)},
        "als_prior_view_sha256": {row["name"]: row["sha256"] for row in prior["view_receipts"]},
        "raw_als_sha256": {Path(row["path"]).name: row["sha256"] for row in prior["raw_als_sources"]},
        "view_counts": {"visible": 55, "train": 47, "held_out": 8, "sparse_seed_points": 25683},
        "reuse": {"crop_regenerated": False, "cameras_regenerated": False, "view_roles_regenerated": False, "sparse_seed_regenerated": False, "fused_depth_regenerated": False},
        "scientific_verdict": None,
    }
    base.atomic_json(TASK_ROOT / "input_hashes.json", input_hashes)
    contract = {
        "schema": "jointbuildgs.p2.e4_local_4906982_55v_als_prior_v1.contract.v1",
        "task_id": TASK_ID, "building_id": "DEBY_LOD2_4906982",
        "status": "PREFLIGHT_BOUND", "non_confirmatory": True,
        "question": "On the same fixed 55-view FUSED_VIS_CONF base, does confidence-gated Existing ALS depth and normal stabilize geometry?",
        "comparison": {"control": "existing FUSED_VIS_CONF/R1", "intervention": "E4_ALS_PRIOR_ONLY/R1"},
        "single_intervention": ["external_als_metric_depth", "external_als_sign_invariant_normal"],
        "source_completed_updates": 7000, "first_intervention_update": 7001,
        "checkpoints": list(CHECKPOINTS), "selected_gpu": 1,
        "training_experiments_started": 0, "new_loss": False, "multiview_densification": False,
        "lod2_training_use": False, "scientific_verdict": None,
    }
    base.atomic_json(TASK_ROOT / "experiment_contract.json", contract)
    source_files = [Path(__file__), REPO / "scripts/p2/e4_local_4906982_55v_als_prior_v1/prepare_als_prior.py", REPO / "scripts/p2/e4_local_4906982_55v_als_prior_v1/audit_smrf_ground.py", COMMON_CONFIG, ARM_CONFIG, SMRF_CONFIG, DEPTH_BASE_CONFIG, FUSED_ARM_CONFIG, REPO / "src/stage2/train.py", REPO / "src/stage2/dataloader.py", REPO / "src/stage2/loss/data_fitting.py", REPO / "src/stage2/loss/multiview.py"]
    previous = json.loads((TASK_ROOT / "provenance.json").read_text()) if (TASK_ROOT / "provenance.json").is_file() else {}
    base.atomic_json(TASK_ROOT / "provenance.json", {
        "schema": "jointbuildgs.p2.e4_local_4906982_55v_als_prior_v1.provenance.v1",
        "task_id": TASK_ID, "git": base.git_record(), "docker_image": base.image_record(), "gpu": base.gpu_record(),
        "source_config_sha256": {str(path.relative_to(REPO)): sha256(path) for path in source_files},
        "input_hashes_sha256": sha256(TASK_ROOT / "input_hashes.json"), "random_seed": 0,
        "started_utc": previous.get("started_utc") or base.now(), "ended_utc": None,
        "commands": previous.get("commands", []), "return_codes": previous.get("return_codes", []),
        "scientific_verdict": None,
    })
    base.atomic_text(TASK_ROOT / "NOTES.md", f"# {TASK_ID}\n\nStatus: `PREFLIGHT_BOUND`. Training not started.\n\nThe frozen 937-view ALS prior matched only 9/55 crop shapes; the same ALS was reprojected into the exact 55 cameras.\n\nSMRF diagnostic: 42,181/49,981 footprint points were retained as class 2 because the dominant surface is continuous and locally flat; see `smrf_diagnostic/metrics.json`.\n\nscientific_verdict: null\n")
    issues = TASK_ROOT / "issues.md"
    if not issues.exists():
        base.atomic_text(issues, "# Issues\n\n- Preserved pre-training failure: ALS prior representative panel used dataloader key `image` instead of `rgb`; 55 generated priors were hash-validated and recovered without deletion or reprojection.\n- Existing 937-view prior cannot be reused directly: 46/55 stored H/W shapes differ from the exact 55 crop cameras.\n\nscientific_verdict: null\n")
    source_footprint = SOURCE_TASK / "control/shared_standard_footprint_4906982.geojson"
    target_footprint = TASK_ROOT / "control/shared_standard_footprint_4906982.geojson"
    if target_footprint.exists():
        if sha256(target_footprint) != sha256(source_footprint):
            raise RuntimeError("task-local footprint copy drifted")
    else:
        shutil.copy2(source_footprint, target_footprint)
    print(diff, end="")


def probe_config() -> Path:
    cfg = materialized()
    cfg.update({"run_id": "BINDING_PROBE_E4_ALS", "out_dir": container_path(TASK_ROOT / "binding_probe"), "max_iter": 1, "eval_every": 100000, "ckpt_every": 100000, "full_state_resume": "off"})
    path = TASK_ROOT / "control/runtime_configs/binding_probe.yaml"
    base.atomic_text(path, yaml.safe_dump(cfg, sort_keys=False))
    return path


def binding_probe() -> None:
    stable = TASK_ROOT / "control/effective_configs/e4_als_prior_only.json"
    if stable.is_file():
        print(stable.read_text()); return
    cfg = probe_config()
    argv = base.docker_base(gpu=True) + ["python", "-c", base.DETERMINISTIC_WRAPPER, "--config", container_path(cfg)]
    log = TASK_ROOT / "logs/binding_probe.log"; started = base.now()
    with log.open("w") as stream:
        proc = subprocess.run(argv, text=True, stdout=stream, stderr=subprocess.STDOUT)
    base.record_operation("binding_probe", argv, proc.returncode, started, base.now())
    if proc.returncode != 0:
        raise RuntimeError(f"binding probe failed; inspect {log}")
    effective = json.loads((TASK_ROOT / "binding_probe/effective_config.json").read_text())
    effective.pop("full_state_runtime", None)
    base.atomic_json(stable, effective)
    print(stable.read_text())


def smoke() -> None:
    receipt = TASK_ROOT / "control/receipts/smoke.json"
    if receipt.is_file() and json.loads(receipt.read_text()).get("passed"):
        print(receipt.read_text()); return
    if receipt.is_file():
        prior_attempt = json.loads(receipt.read_text())
        scalars = prior_attempt.get("scalars", {})
        recoverable = (
            prior_attempt.get("return_code") == 0
            and prior_attempt.get("neighbor_summary_found") is True
            and scalars.get("loss/external_als_depth_huber", 0) > 0
            and scalars.get("loss/external_als_normal_sign_invariant", 0) > 0
            and abs(scalars.get("loss_weight/external_als_depth", 0) - 0.01) < 1e-7
            and abs(scalars.get("loss_weight/external_als_normal", 0) - 0.005) < 1e-7
            and scalars.get("stats/external_als_depth_valid_pixel_count", 0) > 0
        )
        if recoverable:
            preserved = TASK_ROOT / "control/receipts/smoke_attempt_1_float_equality_failed.json"
            if not preserved.exists():
                shutil.copy2(receipt, preserved)
            prior_attempt.update({
                "passed": True,
                "weight_comparison": "absolute_tolerance_lt_1e-7",
                "recovered_from": {"path": str(preserved), "sha256": sha256(preserved)},
            })
            base.atomic_json(receipt, prior_attempt)
            issues = TASK_ROOT / "issues.md"
            with issues.open("a", encoding="utf-8") as stream:
                stream.write("- Preserved smoke audit false-negative: TensorBoard float32 weights 0.0099999998/0.0049999999 failed exact Python equality; recovered with absolute tolerance <1e-7. The 12-update Docker smoke itself returned 0 with nonzero ALS losses and 10,134 valid pixels.\n")
            print(receipt.read_text())
            return
    cfg = materialized(); root = TASK_ROOT / "smoke"
    cfg.update({"run_id": "SMOKE_E4_ALS", "out_dir": container_path(root), "max_iter": 12, "eval_every": 100000, "ckpt_every": 100000, "full_state_resume": "off", "full_state_checkpoint": False, "full_state_checkpoint_steps": [], "mvc_warmup": 0, "mvc_ramp_steps": 1, "depth_warmup": 0, "depth_ramp_steps": 1, "refine_start_iter": 500})
    path = TASK_ROOT / "control/runtime_configs/smoke.yaml"
    base.atomic_text(path, yaml.safe_dump(cfg, sort_keys=False))
    argv = base.docker_base(gpu=True) + ["python", "-c", base.DETERMINISTIC_WRAPPER, "--config", container_path(path)]
    log = TASK_ROOT / "logs/smoke.log"; started = base.now()
    with log.open("w") as stream:
        proc = subprocess.run(argv, text=True, stdout=stream, stderr=subprocess.STDOUT)
    base.record_operation("smoke", argv, proc.returncode, started, base.now())
    check = "from tensorboard.backend.event_processing.event_accumulator import EventAccumulator as E;import glob,json,sys;e=E(glob.glob(sys.argv[1]+'/events*')[0]);e.Reload();tags=['loss/external_als_depth_huber','loss/external_als_normal_sign_invariant','loss_weight/external_als_depth','loss_weight/external_als_normal','stats/external_als_depth_valid_pixel_count'];print(json.dumps({k:max(x.value for x in e.Scalars(k)) for k in tags}))"
    scalar = subprocess.run(base.docker_base() + ["python", "-c", check, container_path(root / "tb")], text=True, capture_output=True)
    scalars = json.loads(next(line for line in reversed(scalar.stdout.splitlines()) if line.startswith("{"))) if scalar.returncode == 0 else {}
    log_text = log.read_text(errors="replace")
    passed = proc.returncode == 0 and "avg 2.0 neighbors/view" in log_text and "[done]" in log_text and scalars.get("loss/external_als_depth_huber", 0) > 0 and scalars.get("loss/external_als_normal_sign_invariant", 0) > 0 and abs(scalars.get("loss_weight/external_als_depth", 0) - 0.01) < 1e-7 and abs(scalars.get("loss_weight/external_als_normal", 0) - 0.005) < 1e-7 and scalars.get("stats/external_als_depth_valid_pixel_count", 0) > 0
    base.atomic_json(receipt, {"schema": "jointbuildgs.p2.e4_local_4906982_55v_als_prior_v1.smoke.v1", "return_code": proc.returncode, "scalars": scalars, "neighbor_summary_found": "avg 2.0 neighbors/view" in log_text, "prior_gradient_preflight": json.loads(PRIOR_RECEIPT.read_text())["gradient_and_gpu_memory"], "passed": passed, "scientific_verdict": None})
    if not passed:
        raise RuntimeError(f"E4 smoke failed; inspect {log} and {receipt}")
    print(receipt.read_text())


def fork_7k() -> None:
    stable = TASK_ROOT / "control/effective_configs/e4_als_prior_only.json"
    smoke_receipt = TASK_ROOT / "control/receipts/smoke.json"
    receipt = TASK_ROOT / "control/receipts/rebind_e4_als_prior_only_r1.json"
    if not stable.is_file() or not smoke_receipt.is_file() or not json.loads(smoke_receipt.read_text()).get("passed"):
        raise RuntimeError("binding probe and smoke must pass before the 7k fork")
    if receipt.is_file() and json.loads(receipt.read_text()).get("passed") and base.checkpoint_valid(RUN_ROOT, 7000):
        ensure_task_owner(); print(receipt.read_text()); return
    if RUN_ROOT.exists():
        raise RuntimeError(f"incomplete target run root requires review: {RUN_ROOT}")
    destination = RUN_ROOT / "ckpt/step_007000.pt"
    argv = base.docker_base() + ["python", "-c", depth_runner.REBIND_CODE, container_path(SOURCE_CHECKPOINT), container_path(destination), container_path(RUNTIME_CONFIG), Path(container_path(RUN_ROOT)), container_path(stable), container_path(receipt)]
    started = base.now(); proc = subprocess.run([str(value) for value in argv], text=True, capture_output=True)
    (TASK_ROOT / "logs/rebind_7k.log").write_text(proc.stdout + proc.stderr)
    base.record_operation("rebind_7k", [str(value) for value in argv], proc.returncode, started, base.now())
    if proc.returncode != 0:
        raise RuntimeError("7k rebind failed; inspect logs/rebind_7k.log")
    body = json.loads(receipt.read_text())
    gate = {
        "schema": "jointbuildgs.p2.e4_local_4906982_55v_als_prior_v1.common_state_gate.v1",
        "completed_updates": 7000, "source": str(SOURCE_CHECKPOINT), "source_sha256": body["source_sha256"],
        "learned_sections_equal": body["learned_sections_equal"],
        "control_losses_at_completed_update_7000": {"mvc": 0.0, "fused_mvs_depth": 0.0},
        "new_als_weights_at_first_resumed_update": {"depth": 0.01, "normal": 0.005},
        "passed": body["passed"], "scientific_verdict": None,
    }
    base.atomic_json(TASK_ROOT / "control/common_state_gate_7000.json", gate)
    if not gate["passed"]:
        raise RuntimeError("7k exact-state equality gate failed")
    ensure_task_owner(); print(json.dumps(gate, indent=2))


def _mark_training_started() -> None:
    path = TASK_ROOT / "experiment_contract.json"
    contract = json.loads(path.read_text())
    contract["training_experiments_started"] = 1
    contract["status"] = "TRAINING_STARTED"
    base.atomic_json(path, contract)


def train_to_12k() -> None:
    gate = TASK_ROOT / "control/common_state_gate_7000.json"
    if not gate.is_file() or not json.loads(gate.read_text()).get("passed"):
        raise RuntimeError("7k exact-state equality gate required")
    ensure_task_owner(); _mark_training_started()
    result = base._launch_training("train_E4_ALS_PRIOR_ONLY_R1_to12k", RUN_ROOT, RUNTIME_CONFIG, stop_step=12000)
    if not base.checkpoint_valid(RUN_ROOT, 12000):
        raise RuntimeError("12k checkpoint missing")
    print(json.dumps(result, indent=2))


DOSE_GATE_CODE = r'''
import json,math,sys,torch
from pathlib import Path
from tensorboard.backend.event_processing.event_accumulator import EventAccumulator
task=Path(sys.argv[1]);source=Path(sys.argv[2]);target=task/'arms/E4_ALS_PRIOR_ONLY/R1';rows={}
for name,run in [('FUSED_VIS_CONF',source),('E4_ALS_PRIOR_ONLY',target)]:
 p=torch.load(run/'ckpt/step_012000.pt',map_location='cpu',weights_only=False);s=p['model']['state_dict'];z=s['means'][:,2].float();tb={}
 for f in sorted((run/'tb').glob('events*')):
  e=EventAccumulator(str(f));e.Reload()
  for tag in e.Tags()['scalars']:tb.setdefault(tag,{}).update({int(x.step):float(x.value) for x in e.Scalars(tag)})
 def latest(tag):
  d=tb.get(tag,{});ks=[k for k in d if k<=12000];return None if not ks else {'step':max(ks),'value':d[max(ks)]}
 rows[name]={'gaussian_count':int(len(z)),'z_gt_650_count':int((z>46).sum()),'z_p99_epsg25832':float(torch.quantile(z,.99)+604.0),'z_max_epsg25832':float(z.max()+604.0),'eval_psnr':latest('eval/psnr'),'train_psnr':latest('metric/psnr_train'),'als_depth_loss':latest('loss/external_als_depth_huber'),'als_normal_loss':latest('loss/external_als_normal_sign_invariant'),'als_valid_pixels':latest('stats/external_als_depth_valid_pixel_count')}
vals=[x['value'] for row in rows.values() for x in row.values() if isinstance(x,dict) and x is not None and 'value' in x];delta=rows['E4_ALS_PRIOR_ONLY']['eval_psnr']['value']-rows['FUSED_VIS_CONF']['eval_psnr']['value'];passed=all(math.isfinite(x) for x in vals) and rows['E4_ALS_PRIOR_ONLY']['gaussian_count']<=800000 and delta>=-5.0 and (rows['E4_ALS_PRIOR_ONLY']['als_valid_pixels'] or {}).get('value',0)>0
body={'schema':'jointbuildgs.p2.e4_local_4906982_55v_als_prior_v1.dose_safety_gate.v1','completed_updates':12000,'rows':rows,'held_out_psnr_delta_e4_minus_control_db':delta,'thresholds':{'finite_required':True,'max_gaussians':800000,'minimum_psnr_delta_db':-5.0,'positive_als_valid_pixels':True},'passed':passed,'scientific_verdict':None};Path(sys.argv[3]).write_text(json.dumps(body,indent=2,sort_keys=True)+'\n');print(json.dumps(body,indent=2));raise SystemExit(0 if passed else 2)
'''


def dose_gate() -> None:
    if not base.checkpoint_valid(RUN_ROOT, 12000) or not base.checkpoint_valid(SOURCE_RUN, 12000):
        raise RuntimeError("control/intervention 12k checkpoints required")
    output = TASK_ROOT / "control/dose_safety_gate_12000.json"
    argv = base.docker_base() + ["python", "-c", DOSE_GATE_CODE, container_path(TASK_ROOT), container_path(SOURCE_RUN), container_path(output)]
    started = base.now(); proc = subprocess.run(argv, text=True, capture_output=True)
    base.record_operation("dose_safety_gate_12000", argv, proc.returncode, started, base.now())
    (TASK_ROOT / "logs/dose_safety_gate_12000.log").write_text(proc.stdout + proc.stderr)
    if proc.returncode != 0:
        raise RuntimeError("12k dose-safety gate failed; training stopped")
    print(proc.stdout)


def train() -> None:
    gate = TASK_ROOT / "control/dose_safety_gate_12000.json"
    if not gate.is_file() or not json.loads(gate.read_text()).get("passed"):
        raise RuntimeError("passed 12k dose-safety gate required")
    ensure_task_owner()
    result = base._launch_training("train_E4_ALS_PRIOR_ONLY_R1_to20k", RUN_ROOT, RUNTIME_CONFIG, stop_step=None)
    missing = [step for step in CHECKPOINTS if not base.checkpoint_valid(RUN_ROOT, step)]
    if missing:
        raise RuntimeError(f"missing E4 checkpoints: {missing}")
    path = TASK_ROOT / "experiment_contract.json"; contract = json.loads(path.read_text()); contract["status"] = "TRAINING_COMPLETE_EVALUATION_PENDING"; base.atomic_json(path, contract)
    print(json.dumps(result, indent=2))


def prepare_control_proxy() -> None:
    ensure_task_owner()
    root = TASK_ROOT / "arms/FUSED_VIS_CONF/R1"
    for relative in ("ckpt", "tb"):
        (root / relative).mkdir(parents=True, exist_ok=True)
    for step in CHECKPOINTS:
        for suffix in (".pt", ".pt.sha256"):
            source = SOURCE_RUN / "ckpt" / f"step_{step:06d}{suffix}"; target = root / "ckpt" / source.name
            if not source.is_file(): raise FileNotFoundError(source)
            if target.is_symlink():
                if target.resolve() != source.resolve(): raise RuntimeError(f"control proxy drift: {target}")
            elif target.exists(): raise RuntimeError(f"control proxy collision: {target}")
            else: target.symlink_to(os.path.relpath(source, target.parent))
    for source in sorted((SOURCE_RUN / "tb").glob("events*")):
        target = root / "tb" / source.name
        if not target.exists() and not target.is_symlink(): target.symlink_to(os.path.relpath(source, target.parent))
    cfg = materialized_control(); cfg.update({"task_id": TASK_ID, "run_id": "FUSED_VIS_CONF_R1_REUSED_CONTROL", "out_dir": container_path(root), "full_state_resume": "off", "scientific_verdict": None})
    base.atomic_text(TASK_ROOT / "control/runtime_configs/fused_vis_conf_r1.yaml", yaml.safe_dump(cfg, sort_keys=False))
    control_source_receipt = SOURCE_TASK / "control/receipts/train_FUSED_VIS_CONF_R1.json"
    control_receipt = json.loads(control_source_receipt.read_text())
    control_receipt.update({"label": "train_FUSED_VIS_CONF_R1", "reused_control": True, "source_run": str(SOURCE_RUN), "source_receipt": str(control_source_receipt), "scientific_verdict": None})
    base.atomic_json(TASK_ROOT / "control/receipts/train_FUSED_VIS_CONF_R1.json", control_receipt)
    target_receipt_path = TASK_ROOT / "control/receipts/train_E4_ALS_PRIOR_ONLY_R1.json"
    if not target_receipt_path.is_file():
        first = json.loads((TASK_ROOT / "control/receipts/train_E4_ALS_PRIOR_ONLY_R1_to12k.json").read_text())
        second = json.loads((TASK_ROOT / "control/receipts/train_E4_ALS_PRIOR_ONLY_R1_to20k.json").read_text())
        base.atomic_json(target_receipt_path, {
            "schema": "jointbuildgs.p2.e4_local_4906982_55v_als_prior_v1.runtime_aggregate.v1",
            "label": "train_E4_ALS_PRIOR_ONLY_R1", "started_utc": first["started_utc"], "ended_utc": second["ended_utc"],
            "wall_seconds": float(first["wall_seconds"]) + float(second["wall_seconds"]),
            "max_selected_gpu_used_mib": max(first["max_selected_gpu_used_mib"], second["max_selected_gpu_used_mib"]),
            "return_code": second["return_code"], "required_checkpoint_valid": True,
            "segments": [first, second], "scientific_verdict": None,
        })
    base.atomic_json(TASK_ROOT / "control/control_proxy.json", {"source_run": str(SOURCE_RUN), "source_modified": False, "scientific_verdict": None})
    provenance_path = TASK_ROOT / "provenance.json"
    provenance = json.loads(provenance_path.read_text())
    provenance["source_config_sha256"][str(Path(__file__).relative_to(REPO))] = sha256(Path(__file__))
    provenance["post_training_evaluator_receipt_adapter_updated"] = True
    base.atomic_json(provenance_path, provenance)


def adapt(code: str) -> str:
    result = code.replace("'MVC05'", "'E4_ALS_PRIOR_ONLY'").replace("'MVC0'", "'FUSED_VIS_CONF'")
    result = result.replace("MVC05", "E4_ALS_PRIOR_ONLY").replace("MVC0", "FUSED_VIS_CONF")
    result = result.replace("mvc05_r1.yaml", "e4_als_prior_only_r1.yaml").replace("mvc0_r1.yaml", "fused_vis_conf_r1.yaml")
    result = result.replace("'metric/psnr_train','eval/psnr','loss/mvc'", "'metric/psnr_train','eval/psnr','loss/depth','loss_weight/depth','loss/mvc','loss/external_als_depth_huber','loss/external_als_normal_sign_invariant','stats/external_als_depth_valid_pixel_count'")
    result = result.replace("replicas=['R1','R2','R3']", "replicas=['R1']").replace("reps=['R1','R2','R3']", "reps=['R1']").replace("['R1','R2','R3']", "['R1']")
    result = result.replace("'replicates_per_arm':3", "'replicates_per_arm':1").replace("ddof=1", "ddof=0")
    result = result.replace("mvc05_minus_mvc0", "e4_als_minus_fused_vis_conf").replace("paired_mvc05_minus_mvc0", "paired_e4_als_minus_fused_vis_conf")
    result = result.replace("mvc_weight=0.0 if arm=='FUSED_VIS_CONF' or step<=7000 else .5", "mvc_weight=0.0 if step<=7000 else .5")
    for old, new in (("'cases':24", "'cases':8"), ("'classification_passed':24", "'classification_passed':8"), ("'roofer_return_code_zero':24", "'roofer_return_code_zero':8"), ("'roofer_rf_success_true':24", "'roofer_rf_success_true':8"), ("'roofer_cases':24", "'roofer_cases':8")):
        result = result.replace(old, new)
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
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("preflight", "binding-probe", "smoke", "fork-7k", "train-to-12k", "dose-gate", "train", "analyze-checkpoints", "stage3", "finalize-measurements"))
    command = parser.parse_args().command
    globals()[command.replace("-", "_")]()


if __name__ == "__main__":
    main()
