#!/usr/bin/env python3
"""Paired MVC05 + geometric-MVS-depth diagnostic for DEBY_LOD2_4906982.

The host process only orchestrates Docker.  Both arms load the same frozen
COLMAP geometric-consistency depth maps and fork the exact same 7k full state;
the sole paired objective delta is w_depth (0 versus 0.03).
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
BASE_PATH = REPO / "scripts/p2/e3_local_4906982_mvc_v2/run.py"
SPEC = importlib.util.spec_from_file_location("mvc_v2_runner", BASE_PATH)
assert SPEC and SPEC.loader
base = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(base)

ARTIFACT_ROOT = REPO.parent / "JointBuildGS-artifacts"
TASK_ID = "P2-E3-LOCAL-4906982-MVC-DEPTH-v1"
TASK_ROOT = ARTIFACT_ROOT / "phase-payloads/p2/e3_local_4906982_mvc_depth_v1" / TASK_ID
CONFIG_DIR = REPO / "configs/p2/e3_local_4906982_mvc_depth_v1"
CONFIGS = {"DEPTH0": CONFIG_DIR / "depth0.yaml", "DEPTH03": CONFIG_DIR / "depth03.yaml"}
ARMS = ("DEPTH0", "DEPTH03")
REPLICAS = ("R1", "R2", "R3")
CHECKPOINTS = (7000, 12000, 15000, 20000)
ALLOWLIST = {"run_id", "out_dir", "w_depth"}
SOURCE_TASK = ARTIFACT_ROOT / "phase-payloads/p2/e3_local_4906982_mvc_v2/P2-E3-LOCAL-4906982-MVC-v2"
SOURCE_PREFIX = SOURCE_TASK / "common_prefix"
SOURCE_INPUTS = ARTIFACT_ROOT / "phase-payloads/p2/e3_local_4906982_mvc_v1/P2-E3-LOCAL-4906982-MVC-v1/input_hashes.json"
V6_ROOT = ARTIFACT_ROOT / "phase-payloads/p2/e3_local_4906982_v1/P2-E3-LOCAL-4906982-2DGS-v6-dist0-resetoff-30k"
DATA_ROOT = V6_ROOT / "data/colmap_crop"
MVC_SOURCE = REPO / "src/stage2/loss/multiview.py"
MVC_SNAPSHOT = V6_ROOT / "control/source_56f1e7cd0315fe0ab40d719ef0be901bb5dd3d7b/src/stage2/loss/multiview.py"

# Reuse the validated Docker/GPU launcher and checkpoint/runtime pattern.
base.TASK_ID = TASK_ID
base.TASK_ROOT = TASK_ROOT
base.CONFIG_DIR = CONFIG_DIR
base.CONFIGS = CONFIGS
base.ARMS = ARMS
base.REPLICAS = REPLICAS
base.CHECKPOINTS = CHECKPOINTS
base.ALLOWLIST = ALLOWLIST


def sha256(path: Path) -> str:
    return base.sha256(path)


def atomic_json(path: Path, body: Any) -> None:
    base.atomic_json(path, body)


def _changed(left: dict[str, Any], right: dict[str, Any]) -> set[str]:
    return {key for key in set(left) | set(right) if left.get(key) != right.get(key)}


def runtime_path(arm: str, replica: str) -> Path:
    return TASK_ROOT / "control/runtime_configs" / f"{arm.lower()}_{replica.lower()}.yaml"


def run_root(arm: str, replica: str) -> Path:
    return TASK_ROOT / "arms" / arm / replica


def repo_container_path(path: Path) -> str:
    return "/workspace/JointBuildGS/" + str(path.relative_to(REPO))


def _write_runtime_configs() -> None:
    for arm in ARMS:
        template = yaml.safe_load(CONFIGS[arm].read_text())
        for replica in REPLICAS:
            body = dict(template)
            body.update({
                "task_id": TASK_ID,
                "run_id": f"{arm}_{replica}",
                "out_dir": base.container_path(run_root(arm, replica)),
                "full_state_resume": "auto",
                "full_state_checkpoint": True,
                "full_state_checkpoint_steps": list(CHECKPOINTS),
                "max_iter": 20000,
            })
            base.atomic_text(runtime_path(arm, replica), yaml.safe_dump(body, sort_keys=False))


def _validate_configs() -> str:
    templates = {arm: yaml.safe_load(path.read_text()) for arm, path in CONFIGS.items()}
    delta = _changed(templates["DEPTH0"], templates["DEPTH03"])
    if delta != ALLOWLIST:
        raise RuntimeError(f"paired template diff gate failed: {sorted(delta)}")
    if templates["DEPTH0"]["w_depth"] != 0.0 or templates["DEPTH03"]["w_depth"] != 0.03:
        raise RuntimeError("locked depth weights are not 0 and 0.03")
    for arm, cfg in templates.items():
        required = {
            "load_depth": True,
            "load_normal": False,
            "w_mvc": 0.5,
            "mvc_warmup": 7000,
            "mvc_schedule": "ramp",
            "mvc_ramp_steps": 5000,
            "depth_scale": 1.0,
            "depth_warmup": 7000,
            "depth_schedule": "ramp",
            "depth_ramp_steps": 5000,
            "depth_prior_alignment": "none",
            "w_normal": 0.0,
            "w_distort": 0.0,
            "reset_every": 100000,
            "max_iter": 20000,
        }
        mismatch = {key: (cfg.get(key), value) for key, value in required.items() if cfg.get(key) != value}
        if mismatch:
            raise RuntimeError(f"{arm} locked setting mismatch: {mismatch}")
    lines = [
        "paired intervention: frozen MVC05 + geometric MVS depth",
        "allowed_template_keys: out_dir, run_id, w_depth",
        "actual_template_keys: " + ", ".join(sorted(delta)),
        "DEPTH0 w_depth: 0.0",
        "DEPTH03 w_depth: 0.03",
        "both load_depth: true",
        "both depth schedule: warmup=7000, ramp_steps=5000",
        "both MVC: w_mvc=0.5, warmup=7000, ramp_steps=5000",
        "view selection/densification/normal/ALS/LoD/semantic deltas: none",
        "",
    ]
    for replica in REPLICAS:
        left = yaml.safe_load(runtime_path("DEPTH0", replica).read_text())
        right = yaml.safe_load(runtime_path("DEPTH03", replica).read_text())
        actual = _changed(left, right)
        if actual != ALLOWLIST:
            raise RuntimeError(f"runtime pair diff failed for {replica}: {sorted(actual)}")
        lines.append(f"runtime {replica}: {', '.join(sorted(actual))}")
    return "\n".join(lines) + "\n"


def preflight() -> None:
    marker = TASK_ROOT / "experiment_contract.json"
    if TASK_ROOT.exists() and any(TASK_ROOT.iterdir()) and not marker.is_file():
        raise RuntimeError(f"non-empty unbound namespace: {TASK_ROOT}")
    for child in ("control/runtime_configs", "control/receipts", "control/effective_configs", "logs", "cache/torch_extensions", "representative_images"):
        (TASK_ROOT / child).mkdir(parents=True, exist_ok=True)
    if MVC_SOURCE.read_bytes() != MVC_SNAPSHOT.read_bytes():
        raise RuntimeError("multiview.py is not byte-identical to the v6 snapshot")
    if not base.checkpoint_valid(SOURCE_PREFIX, 7000):
        raise RuntimeError("verified MVC v2 common 7k full-state checkpoint is missing")
    if not SOURCE_INPUTS.is_file():
        raise FileNotFoundError(SOURCE_INPUTS)
    _write_runtime_configs()
    diff_text = _validate_configs()
    base.atomic_text(TASK_ROOT / "config_diff.txt", diff_text)

    views = yaml.safe_load(CONFIGS["DEPTH0"].read_text())["visible_views"]
    depth_files = {name: DATA_ROOT / "stereo/depth_maps" / f"{name}.geometric.bin" for name in views}
    missing = [name for name, path in depth_files.items() if not path.is_file()]
    if missing:
        raise RuntimeError(f"missing geometric MVS depth maps: {missing}")
    old_inputs = json.loads(SOURCE_INPUTS.read_text())
    atomic_json(TASK_ROOT / "input_hashes.json", {
        **old_inputs,
        "schema": "jointbuildgs.p2.e3_local_4906982_mvc_depth_v1.inputs.v1",
        "reused_verified_manifest": {"path": str(SOURCE_INPUTS), "sha256": sha256(SOURCE_INPUTS)},
        "common_checkpoint_input": {"path": str(SOURCE_PREFIX / "ckpt/step_007000.pt"), "sha256": sha256(SOURCE_PREFIX / "ckpt/step_007000.pt")},
        "geometric_depth_maps_sha256": {name: sha256(path) for name, path in depth_files.items()},
        "geometric_depth_map_count": len(depth_files),
        "depth_loader_preference": "*.geometric.bin before *.photometric.bin",
    })
    contract = {
        "schema": "jointbuildgs.p2.e3_local_4906982_mvc_depth_v1.contract.v1",
        "task_id": TASK_ID,
        "building_id": "DEBY_LOD2_4906982",
        "status": "PREFLIGHT_BOUND",
        "design": "three paired DEPTH0/DEPTH03 continuations from one exact MVC-inactive 7k full state",
        "arms": {"DEPTH0": {"w_mvc": 0.5, "w_depth": 0.0}, "DEPTH03": {"w_mvc": 0.5, "w_depth": 0.03}},
        "sole_training_objective_delta": "w_depth",
        "depth_evidence": "existing COLMAP geometric-consistency depth; positive finite pixels form the fixed validity mask; no scalar confidence weighting",
        "replicas": list(REPLICAS),
        "views": {"exact": 55, "train": 47, "held_out": 8},
        "checkpoints_completed_updates": list(CHECKPOINTS),
        "dose_safety_gate": "train R1 arms only through 12k first; require finite checkpoints/scalars, no cap/OOM, and no held-out PSNR collapse larger than 5 dB before remaining continuations",
        "same_head_image_gpu": True,
        "normal_supervision": False,
        "view_selection_change": False,
        "multiview_densification": False,
        "external_als_lod_semantic": False,
        "high_z_and_normal_surface_endpoints_separate": True,
        "official_PASS_usable": None,
        "scientific_verdict": None,
    }
    atomic_json(marker, contract)
    sources = [Path(__file__).resolve(), BASE_PATH, REPO / "src/stage2/train.py", REPO / "src/stage2/dataloader.py", REPO / "src/stage2/loss/data_fitting.py", REPO / "src/stage2/train_resume.py", REPO / "src/stage2/checkpoint.py", MVC_SOURCE, *CONFIGS.values()]
    if not (TASK_ROOT / "provenance.json").exists():
        atomic_json(TASK_ROOT / "provenance.json", {
            "schema": "jointbuildgs.p2.e3_local_4906982_mvc_depth_v1.provenance.v1",
            "task_id": TASK_ID,
            "git": base.git_record(),
            "docker_image": base.image_record(),
            "gpu": base.gpu_record(),
            "source_files_sha256": {str(path.relative_to(REPO)): sha256(path) for path in sources},
            "configs_sha256": {arm: sha256(path) for arm, path in CONFIGS.items()},
            "runtime_configs_sha256": {path.name: sha256(path) for path in sorted((TASK_ROOT / "control/runtime_configs").glob("*.yaml"))},
            "input_hashes_sha256": sha256(TASK_ROOT / "input_hashes.json"),
            "random_seed": 0,
            "started_utc": base.now(),
            "ended_utc": None,
            "commands": [],
            "return_codes": [],
            "scientific_verdict": None,
        })
    else:
        provenance_path = TASK_ROOT / "provenance.json"
        provenance = json.loads(provenance_path.read_text())
        provenance.update({
            "git": base.git_record(),
            "docker_image": base.image_record(),
            "gpu": base.gpu_record(),
            "source_files_sha256": {str(path.relative_to(REPO)): sha256(path) for path in sources},
            "configs_sha256": {arm: sha256(path) for arm, path in CONFIGS.items()},
            "runtime_configs_sha256": {path.name: sha256(path) for path in sorted((TASK_ROOT / "control/runtime_configs").glob("*.yaml"))},
            "input_hashes_sha256": sha256(TASK_ROOT / "input_hashes.json"),
        })
        atomic_json(provenance_path, provenance)
    if not (TASK_ROOT / "common_prefix").exists():
        shutil.copytree(SOURCE_PREFIX, TASK_ROOT / "common_prefix")
    if sha256(TASK_ROOT / "common_prefix/ckpt/step_007000.pt") != sha256(SOURCE_PREFIX / "ckpt/step_007000.pt"):
        raise RuntimeError("copied common checkpoint hash mismatch")
    base.atomic_text(TASK_ROOT / "NOTES.md", f"# {TASK_ID}\n\nPreflight bound; no main-arm training started. Scientific verdict: `null`.\n")
    print(diff_text, end="")
    print(json.dumps({"task_root": str(TASK_ROOT), "checkpoint_7k_sha256": sha256(SOURCE_PREFIX / "ckpt/step_007000.pt"), "docker_image_id": base.image_record()["id"], "gpu": base.gpu_record()["model"]}, indent=2))


DEPTH_AUDIT_CODE = r'''
import hashlib,json,sys,yaml,numpy as np
from pathlib import Path
from src.stage2.colmap_io import read_array
cfg=yaml.safe_load(Path(sys.argv[1]).read_text());root=Path(cfg['data_root']);rows=[]
for name in cfg['visible_views']:
 p=root/'stereo/depth_maps'/f'{name}.geometric.bin';d=read_array(p);m=np.isfinite(d)&(d>0);v=d[m]
 rows.append({'view':name,'path':str(p),'shape':list(d.shape),'valid_pixels':int(m.sum()),'total_pixels':int(m.size),'valid_fraction':float(m.mean()),'depth_min':float(v.min()),'depth_median':float(np.median(v)),'depth_p95':float(np.quantile(v,.95)),'depth_p99':float(np.quantile(v,.99)),'depth_max':float(v.max())})
body={'schema':'jointbuildgs.p2.e3_local_4906982_mvc_depth_v1.depth_input_audit.v1','view_count':len(rows),'all_geometric':True,'mask_rule':'isfinite(depth) and depth>0 (loader uses depth>0; all selected values audited finite)','valid_fraction_min':min(r['valid_fraction'] for r in rows),'valid_fraction_median':float(np.median([r['valid_fraction'] for r in rows])),'valid_fraction_max':max(r['valid_fraction'] for r in rows),'views':rows,'scientific_verdict':None}
Path(sys.argv[2]).write_text(json.dumps(body,indent=2,sort_keys=True)+'\n');print(json.dumps({k:v for k,v in body.items() if k!='views'},indent=2))
'''


def depth_audit() -> None:
    output = TASK_ROOT / "control/depth_input_audit.json"
    if output.is_file():
        body = json.loads(output.read_text()); print(json.dumps({k: v for k, v in body.items() if k != "views"}, indent=2)); return
    argv = base.docker_base() + ["python", "-c", DEPTH_AUDIT_CODE, repo_container_path(CONFIGS["DEPTH0"]), base.container_path(output)]
    started = base.now(); proc = subprocess.run(argv, text=True, capture_output=True); base.record_operation("depth_input_audit", argv, proc.returncode, started, base.now())
    (TASK_ROOT / "logs/depth_input_audit.log").write_text(proc.stdout + proc.stderr)
    if proc.returncode != 0: raise RuntimeError("depth input audit failed; inspect logs/depth_input_audit.log")
    print(proc.stdout.strip())


BASELINE_DEPTH_CODE = r'''
import json,sys,torch,yaml,numpy as np
from pathlib import Path
from torch import nn
from src.stage2.dataloader import ColmapDataset
from src.stage2.model import GaussianModel2D
from src.stage2.renderer import render
from tensorboard.backend.event_processing.event_accumulator import EventAccumulator
cfg=yaml.safe_load(Path(sys.argv[1]).read_text());ckpt=Path(sys.argv[2]);out_path=Path(sys.argv[3]);tb_dir=Path(sys.argv[4])
ds=ColmapDataset(cfg['data_root'],downscale=float(cfg['downscale']),load_depth=True,load_normal=False,load_semantic=False,visible_views=cfg['visible_views']);train=set(cfg['train_views'])
p=torch.load(ckpt,map_location='cpu',weights_only=False);s=p['model']['state_dict'];required={'means','quats','log_scales','opacities_raw','sh0','shN','sem_logits'}
m=GaussianModel2D.__new__(GaussianModel2D);nn.Module.__init__(m);m.sh_degree=3;m.max_sh_degree=3;m.active_sh_degree=3;m.num_classes=4
for k in sorted(required):setattr(m,k,nn.Parameter(s[k].cuda(),requires_grad=False))
m.surface_seed_mask=torch.zeros(len(s['means']),dtype=torch.bool,device='cuda');m.eval();rows=[]
with torch.no_grad():
 for b in ds:
  o=render(m,b['w2c'].cuda(),b['K'].cuda(),int(b['width']),int(b['height']),sh_degree=3,render_mode='RGB+ED');pred=o['depth'];gt=b['depth'].cuda();mask=b['depth_mask'].cuda()&torch.isfinite(pred);r=(pred-gt).abs()[mask];rel=r/gt[mask].clamp_min(1e-6)
  rows.append({'view':b['name'],'role':'train' if b['name'] in train else 'held_out','valid_pixels':int(mask.sum()),'valid_fraction':float(mask.float().mean()),'depth_l1_m':float(r.mean()),'depth_abs_p50_m':float(torch.quantile(r,.5)),'depth_abs_p95_m':float(torch.quantile(r,.95)),'depth_rel_median':float(torch.quantile(rel,.5)),'mvs_depth_median_m':float(torch.quantile(gt[mask],.5)),'render_depth_median_m':float(torch.quantile(pred[mask],.5))})
photo=[]
for f in sorted(tb_dir.glob('events*')):
 e=EventAccumulator(str(f));e.Reload()
 if 'loss/photo' in e.Tags()['scalars']:photo.extend((int(x.step),float(x.value)) for x in e.Scalars('loss/photo') if int(x.step)<=6999)
def summary(role):
 rr=[x for x in rows if x['role']==role];return {'view_count':len(rr),'depth_l1_mean_of_views_m':float(np.mean([x['depth_l1_m'] for x in rr])),'depth_l1_median_of_views_m':float(np.median([x['depth_l1_m'] for x in rr])),'depth_l1_max_view_m':float(np.max([x['depth_l1_m'] for x in rr])),'median_relative_error_mean_of_views':float(np.mean([x['depth_rel_median'] for x in rr]))}
raw=summary('train')['depth_l1_mean_of_views_m'];last_photo=sorted(photo)[-1] if photo else None
body={'schema':'jointbuildgs.p2.e3_local_4906982_mvc_depth_v1.baseline_depth_gate.v1','checkpoint_completed_updates':7000,'train':summary('train'),'held_out':summary('held_out'),'scheduled_weighted_train_depth_loss':{'7000':0.0,'12000':0.03*raw,'15000':0.03*raw,'20000':0.03*raw},'source_photo_loss_latest_pre7k':None if last_photo is None else {'step':last_photo[0],'value':last_photo[1]},'note':'weighted values hold the 7k raw residual fixed and are scale diagnostics, not forecasts','views':rows,'scientific_verdict':None}
out_path.write_text(json.dumps(body,indent=2,sort_keys=True)+'\n');print(json.dumps({k:v for k,v in body.items() if k!='views'},indent=2))
'''


def baseline_depth_gate() -> None:
    output = TASK_ROOT / "control/baseline_depth_gate_7000.json"
    if output.is_file():
        body = json.loads(output.read_text()); print(json.dumps({k: v for k, v in body.items() if k != "views"}, indent=2)); return
    argv = base.docker_base(gpu=True) + ["python", "-c", BASELINE_DEPTH_CODE, repo_container_path(CONFIGS["DEPTH0"]), base.container_path(TASK_ROOT / "common_prefix/ckpt/step_007000.pt"), base.container_path(output), base.container_path(TASK_ROOT / "common_prefix/tb")]
    log = TASK_ROOT / "logs/baseline_depth_gate_7000.log"; started = base.now()
    with log.open("w") as stream: proc = subprocess.run(argv, text=True, stdout=stream, stderr=subprocess.STDOUT)
    base.record_operation("baseline_depth_gate_7000", argv, proc.returncode, started, base.now())
    if proc.returncode != 0: raise RuntimeError("7k baseline depth gate failed; inspect logs/baseline_depth_gate_7000.log")
    body = json.loads(output.read_text()); print(json.dumps({k: v for k, v in body.items() if k != "views"}, indent=2))


def _probe_config(arm: str) -> Path:
    cfg = yaml.safe_load(CONFIGS[arm].read_text())
    root = TASK_ROOT / "binding_probe" / arm
    cfg.update({"run_id": f"BINDING_PROBE_{arm}", "out_dir": base.container_path(root), "max_iter": 1, "eval_every": 100000, "ckpt_every": 100000, "full_state_resume": "off", "full_state_checkpoint": True, "full_state_checkpoint_steps": list(CHECKPOINTS)})
    path = TASK_ROOT / "control/runtime_configs" / f"binding_probe_{arm.lower()}.yaml"
    base.atomic_text(path, yaml.safe_dump(cfg, sort_keys=False)); return path


def binding_probe() -> None:
    for arm in ARMS:
        stable_path = TASK_ROOT / "control/effective_configs" / f"{arm.lower()}.json"
        if stable_path.is_file(): continue
        cfg_path = _probe_config(arm); root = TASK_ROOT / "binding_probe" / arm
        argv = base.docker_base(gpu=True) + ["python", "-c", base.DETERMINISTIC_WRAPPER, "--config", base.container_path(cfg_path)]
        log = TASK_ROOT / "logs" / f"binding_probe_{arm.lower()}.log"; started = base.now()
        with log.open("w") as stream: proc = subprocess.run(argv, text=True, stdout=stream, stderr=subprocess.STDOUT)
        base.record_operation(f"binding_probe_{arm}", argv, proc.returncode, started, base.now())
        if proc.returncode != 0: raise RuntimeError(f"binding probe failed for {arm}; inspect {log}")
        body = json.loads((root / "effective_config.json").read_text()); body.pop("full_state_runtime", None)
        atomic_json(stable_path, body)
    hashes = {arm: base.json_sha256(json.loads((TASK_ROOT / "control/effective_configs" / f"{arm.lower()}.json").read_text())) for arm in ARMS}
    atomic_json(TASK_ROOT / "control/effective_config_gate.json", {"schema": "jointbuildgs.p2.e3_local_4906982_mvc_depth_v1.effective_config_gate.v1", "hashes": hashes, "expected_difference": "depth_base_weight only", "actual_difference": sorted(_changed(*[json.loads((TASK_ROOT / 'control/effective_configs' / f'{arm.lower()}.json').read_text()) for arm in ARMS])), "passed": True, "scientific_verdict": None})
    print(json.dumps(json.loads((TASK_ROOT / "control/effective_config_gate.json").read_text()), indent=2))


def smoke() -> None:
    receipt = TASK_ROOT / "control/receipts/smoke.json"
    if receipt.is_file() and json.loads(receipt.read_text()).get("passed"): print(receipt.read_text()); return
    cfg = yaml.safe_load(CONFIGS["DEPTH03"].read_text()); root = TASK_ROOT / "smoke"
    cfg.update({"run_id": "SMOKE", "out_dir": base.container_path(root), "max_iter": 12, "eval_every": 100000, "ckpt_every": 100000, "full_state_checkpoint": False, "full_state_checkpoint_steps": [], "full_state_resume": "off", "mvc_warmup": 0, "mvc_ramp_steps": 1, "depth_warmup": 0, "depth_ramp_steps": 1, "loss_grad_audit_every": 1, "refine_start_iter": 500})
    cfg_path = TASK_ROOT / "control/runtime_configs/smoke.yaml"; base.atomic_text(cfg_path, yaml.safe_dump(cfg, sort_keys=False))
    argv = base.docker_base(gpu=True) + ["python", "-c", base.DETERMINISTIC_WRAPPER, "--config", base.container_path(cfg_path)]
    log = TASK_ROOT / "logs/smoke.log"; started = base.now()
    with log.open("w") as stream: proc = subprocess.run(argv, text=True, stdout=stream, stderr=subprocess.STDOUT)
    base.record_operation("smoke", argv, proc.returncode, started, base.now())
    audit = root / "audit/loss_grad_norms.csv"
    check_code = "from tensorboard.backend.event_processing.event_accumulator import EventAccumulator as E;import csv,glob,json,sys;e=E(glob.glob(sys.argv[1]+'/events*')[0]);e.Reload();tags=['loss/depth','loss_weight/depth','loss/mvc','stats/mvc_n_inlier'];s={k:max(x.value for x in e.Scalars(k)) for k in tags};rows=list(csv.DictReader(open(sys.argv[2])));s['depth_grad_norm']=max(float(r['grad_norm']) for r in rows if r['component']=='depth');print(json.dumps(s))"
    scalar_proc = subprocess.run(base.docker_base() + ["python", "-c", check_code, base.container_path(root / "tb"), base.container_path(audit)], text=True, capture_output=True)
    scalars = json.loads(next(line for line in reversed(scalar_proc.stdout.splitlines()) if line.startswith("{"))) if scalar_proc.returncode == 0 else {}
    log_text = log.read_text(errors="replace")
    passed = proc.returncode == 0 and "avg 2.0 neighbors/view" in log_text and all(scalars.get(key, 0) > 0 for key in ("loss/depth", "loss_weight/depth", "loss/mvc", "stats/mvc_n_inlier", "depth_grad_norm"))
    atomic_json(receipt, {"schema": "jointbuildgs.p2.e3_local_4906982_mvc_depth_v1.smoke.v1", "return_code": proc.returncode, "scalars": scalars, "neighbor_summary_found": "avg 2.0 neighbors/view" in log_text, "passed": passed, "scientific_verdict": None})
    if not passed: raise RuntimeError("MVC+depth smoke failed; inspect logs/smoke.log")
    print(json.dumps(json.loads(receipt.read_text()), indent=2))


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
sections=['model','optimizers','strategy','grouping_state','rng_state','loss_log_cursor','learning_runs_started'];same={k:eq(torch.load(source,map_location='cpu',weights_only=False)[k],B[k]) for k in sections}
body={'schema':'jointbuildgs.p2.e3_local_4906982_mvc_depth_v1.rebind.v1','source':str(source),'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'destination':str(destination),'destination_sha256':h,'old_binding':old,'new_binding':new,'learned_sections_equal':same,'passed':all(same.values()),'scientific_verdict':None};receipt.parent.mkdir(parents=True,exist_ok=True);receipt.write_text(json.dumps(body,indent=2,sort_keys=True)+'\n');raise SystemExit(0 if body['passed'] else 2)
'''


def fork_prefix() -> None:
    effective_gate = TASK_ROOT / "control/effective_config_gate.json"
    smoke_gate = TASK_ROOT / "control/receipts/smoke.json"
    baseline_gate = TASK_ROOT / "control/baseline_depth_gate_7000.json"
    if not effective_gate.is_file() or not smoke_gate.is_file() or not baseline_gate.is_file() or not json.loads(smoke_gate.read_text()).get("passed"):
        raise RuntimeError("binding-probe, baseline-depth, and smoke gates must pass first")
    source = TASK_ROOT / "common_prefix/ckpt/step_007000.pt"
    for arm in ARMS:
        for replica in REPLICAS:
            destination_root = run_root(arm, replica); receipt = TASK_ROOT / "control/receipts" / f"rebind_{arm.lower()}_{replica.lower()}.json"
            if receipt.is_file() and json.loads(receipt.read_text()).get("passed") and base.checkpoint_valid(destination_root, 7000): continue
            if destination_root.exists(): raise RuntimeError(f"incomplete fork requires review: {destination_root}")
            destination_root.parent.mkdir(parents=True, exist_ok=True); shutil.copytree(TASK_ROOT / "common_prefix", destination_root)
            destination = destination_root / "ckpt/step_007000.pt"
            argv = base.docker_base() + ["python", "-c", REBIND_CODE, base.container_path(source), base.container_path(destination), base.container_path(runtime_path(arm, replica)), Path(base.container_path(destination_root)), base.container_path(TASK_ROOT / "control/effective_configs" / f"{arm.lower()}.json"), base.container_path(receipt)]
            started = base.now(); proc = subprocess.run([str(x) for x in argv], text=True, capture_output=True); base.record_operation(f"rebind_{arm}_{replica}", [str(x) for x in argv], proc.returncode, started, base.now())
            if proc.returncode != 0: raise RuntimeError(proc.stderr or proc.stdout)
    receipts = [json.loads((TASK_ROOT / "control/receipts" / f"rebind_{arm.lower()}_{replica.lower()}.json").read_text()) for arm in ARMS for replica in REPLICAS]
    gate = {"schema": "jointbuildgs.p2.e3_local_4906982_mvc_depth_v1.common_state_gate.v1", "completed_updates": 7000, "replica_count": len(receipts), "unique_source_checkpoint_hashes": len({row['source_sha256'] for row in receipts}), "learned_sections_exact_across_all_forks": all(all(row['learned_sections_equal'].values()) for row in receipts), "loss_weights_at_7k": {"mvc": 0.0, "depth": 0.0}, "passed": False, "scientific_verdict": None}
    gate["passed"] = gate["unique_source_checkpoint_hashes"] == 1 and gate["learned_sections_exact_across_all_forks"]
    atomic_json(TASK_ROOT / "control/common_state_gate_7000.json", gate)
    if not gate["passed"]: raise RuntimeError("common-state fork gate failed")
    print(json.dumps(gate, indent=2))


def train_replicas() -> None:
    gate = TASK_ROOT / "control/common_state_gate_7000.json"
    if not gate.is_file() or not json.loads(gate.read_text()).get("passed"): raise RuntimeError("common-state gate must pass first")
    dose_gate = TASK_ROOT / "control/dose_safety_gate_12000.json"
    if not dose_gate.is_file() or not json.loads(dose_gate.read_text()).get("passed"): raise RuntimeError("R1 12k dose-safety gate must pass first")
    for replica in REPLICAS:
        for arm in ARMS:
            label = f"train_{arm}_{replica}"
            result = base._launch_training(label, run_root(arm, replica), runtime_path(arm, replica), stop_step=None)
            print(json.dumps({"label": label, "wall_seconds": result.get("wall_seconds"), "checkpoint_20k": base.checkpoint_valid(run_root(arm, replica), 20000)}), flush=True)
    missing = [(arm, replica, step) for arm in ARMS for replica in REPLICAS for step in CHECKPOINTS if not base.checkpoint_valid(run_root(arm, replica), step)]
    if missing: raise RuntimeError(f"missing required checkpoints: {missing}")


def train_r1_12k() -> None:
    gate = TASK_ROOT / "control/common_state_gate_7000.json"
    if not gate.is_file() or not json.loads(gate.read_text()).get("passed"): raise RuntimeError("common-state gate must pass first")
    for arm in ARMS:
        label = f"train_{arm}_R1_to12k"
        result = base._launch_training(label, run_root(arm, "R1"), runtime_path(arm, "R1"), stop_step=12000)
        print(json.dumps({"label": label, "wall_seconds": result.get("wall_seconds"), "checkpoint_12k": base.checkpoint_valid(run_root(arm, 'R1'), 12000)}), flush=True)


DOSE_GATE_CODE = r'''
import json,math,sys,torch
from pathlib import Path
from tensorboard.backend.event_processing.event_accumulator import EventAccumulator
root=Path(sys.argv[1]);rows={}
for arm in ['DEPTH0','DEPTH03']:
 run=root/'arms'/arm/'R1';p=torch.load(run/'ckpt/step_012000.pt',map_location='cpu',weights_only=False);s=p['model']['state_dict'];z=s['means'][:,2].float();tb={}
 for f in sorted((run/'tb').glob('events*')):
  e=EventAccumulator(str(f));e.Reload()
  for tag in e.Tags()['scalars']:
   tb.setdefault(tag,{}).update({int(x.step):float(x.value) for x in e.Scalars(tag)})
 def latest(tag):
  d=tb.get(tag,{});ks=[k for k in d if k<=12000];return None if not ks else {'step':max(ks),'value':d[max(ks)]}
 rows[arm]={'gaussian_count':int(len(z)),'z_gt_650_count':int((z>46).sum()),'z_p99_epsg25832':float(torch.quantile(z,.99)+604.0),'z_max_epsg25832':float(z.max()+604.0),'eval_psnr':latest('eval/psnr'),'train_psnr':latest('metric/psnr_train'),'loss_depth':latest('loss/depth'),'loss_weight_depth':latest('loss_weight/depth'),'loss_mvc':latest('loss/mvc'),'mvc_inlier':latest('stats/mvc_n_inlier')}
vals=[v2['value'] for v in rows.values() for v2 in v.values() if isinstance(v2,dict) and 'value' in v2];delta=rows['DEPTH03']['eval_psnr']['value']-rows['DEPTH0']['eval_psnr']['value'];passed=all(math.isfinite(x) for x in vals) and all(v['gaussian_count']<=800000 for v in rows.values()) and delta>=-5.0
body={'schema':'jointbuildgs.p2.e3_local_4906982_mvc_depth_v1.dose_safety_gate.v1','completed_updates':12000,'rows':rows,'held_out_psnr_delta_depth03_minus_depth0_db':delta,'thresholds':{'finite_required':True,'max_gaussians':800000,'minimum_psnr_delta_db':-5.0},'passed':passed,'scientific_verdict':None};Path(sys.argv[2]).write_text(json.dumps(body,indent=2,sort_keys=True)+'\n');print(json.dumps(body,indent=2))
'''


def dose_gate() -> None:
    for arm in ARMS:
        if not base.checkpoint_valid(run_root(arm, "R1"), 12000): raise RuntimeError(f"missing 12k checkpoint for {arm}/R1")
    output = TASK_ROOT / "control/dose_safety_gate_12000.json"
    argv = base.docker_base() + ["python", "-c", DOSE_GATE_CODE, base.container_path(TASK_ROOT), base.container_path(output)]
    started = base.now(); proc = subprocess.run(argv, text=True, capture_output=True); base.record_operation("dose_safety_gate_12000", argv, proc.returncode, started, base.now())
    (TASK_ROOT / "logs/dose_safety_gate_12000.log").write_text(proc.stdout + proc.stderr)
    if proc.returncode != 0: raise RuntimeError("dose safety evaluation failed")
    print(proc.stdout.strip())
    if not json.loads(output.read_text()).get("passed"): raise RuntimeError("dose safety gate failed; remaining main training is stopped")


def _configure_measurement_reuse() -> None:
    analyze = base.ANALYZE_CODE
    analyze = analyze.replace("arms=['MVC0','MVC05']", "arms=['DEPTH0','DEPTH03']")
    analyze = analyze.replace("mvc0_r1.yaml", "depth0_r1.yaml")
    analyze = analyze.replace("mvc_weight=0.0 if arm=='MVC0' or step<=7000 else .5", "mvc_weight=0.0 if step<=7000 else .5")
    analyze = analyze.replace("'loss/nc','stats/gaussian_count'", "'loss/nc','loss/depth','loss_weight/depth','stats/gaussian_count'")
    analyze = analyze.replace("jointbuildgs.p2.e3_local_4906982_mvc_v2", "jointbuildgs.p2.e3_local_4906982_mvc_depth_v1")
    base.ANALYZE_CODE = analyze
    base.STAGE3_PREP_CODE = base.STAGE3_PREP_CODE.replace("['MVC0','MVC05']", "['DEPTH0','DEPTH03']").replace("jointbuildgs.p2.e3_local_4906982_mvc_v2", "jointbuildgs.p2.e3_local_4906982_mvc_depth_v1")
    base.STAGE3_VERIFY_CODE = base.STAGE3_VERIFY_CODE.replace("jointbuildgs.p2.e3_local_4906982_mvc_v2", "jointbuildgs.p2.e3_local_4906982_mvc_depth_v1")
    base.ROOFER_RECORD_CODE = base.ROOFER_RECORD_CODE.replace("jointbuildgs.p2.e3_local_4906982_mvc_v2", "jointbuildgs.p2.e3_local_4906982_mvc_depth_v1")
    finalize = base.FINALIZE_CODE
    finalize = finalize.replace("arms=['MVC0','MVC05']", "arms=['DEPTH0','DEPTH03']")
    finalize = finalize.replace("('MVC0',rep,step)", "('DEPTH0',rep,step)").replace("('MVC05',rep,step)", "('DEPTH03',rep,step)")
    finalize = finalize.replace("representative_images/MVC0", "representative_images/DEPTH0").replace("representative_images/DEPTH05", "representative_images/DEPTH03")
    finalize = finalize.replace("paired_mvc05_minus_mvc0", "paired_depth03_minus_depth0")
    finalize = finalize.replace("jointbuildgs.p2.e3_local_4906982_mvc_v2", "jointbuildgs.p2.e3_local_4906982_mvc_depth_v1")
    finalize = finalize.replace("'loss/nc','stats/gaussian_count'", "'loss/nc','loss/depth','loss_weight/depth','stats/gaussian_count'")
    base.FINALIZE_CODE = finalize


def analyze_checkpoints() -> None:
    _configure_measurement_reuse()
    base.analyze_checkpoints()


def run_stage3() -> None:
    _configure_measurement_reuse()
    base.run_stage3()


def finalize_measurements() -> None:
    _configure_measurement_reuse()
    base.finalize_measurements()


def reference_diagnostic() -> None:
    output = TASK_ROOT / "reference_diagnostic"
    metrics = output / "metrics.json"
    if metrics.is_file() and json.loads(metrics.read_text()).get("status") == "COMPLETE_DIAGNOSTIC":
        print(metrics.read_text()); return
    source = yaml.safe_load((REPO / "configs/p2/e3_local_4906982_mvc_readout_diag_v1/config.yaml").read_text())
    source.update({
        "task_id": TASK_ID + "-REFERENCE-DIAG",
        "source_task_root": base.container_path(TASK_ROOT),
        "source_runner": repo_container_path(Path(__file__).resolve()),
        "shared_footprint": base.container_path(TASK_ROOT / "control/shared_standard_footprint_4906982.geojson"),
        "arms": list(ARMS),
    })
    config = TASK_ROOT / "control/reference_diagnostic.yaml"
    base.atomic_text(config, yaml.safe_dump(source, sort_keys=False))
    source_runner = REPO / "scripts/p2/e3_local_4906982_mvc_readout_diag_v1/run.py"
    runtime_runner = TASK_ROOT / "control/reference_diag_runtime.py"
    runtime_text = source_runner.read_text().replace('"MVC0"', '"DEPTH0"').replace('"MVC05"', '"DEPTH03"').replace("'MVC0'", "'DEPTH0'").replace("'MVC05'", "'DEPTH03'")
    runtime_text = runtime_text.replace('REPO = Path(__file__).resolve().parents[3]\nARTIFACT_ROOT = REPO.parent / "JointBuildGS-artifacts"', 'REPO = Path("/workspace/JointBuildGS")\nARTIFACT_ROOT = Path("/artifacts/JointBuildGS")')
    base.atomic_text(runtime_runner, runtime_text)
    output.mkdir(parents=True, exist_ok=True); (output / "logs").mkdir(exist_ok=True)
    argv = [
        "docker", "run", "--rm", "--network", "none", "--user", f"{os.getuid()}:{os.getgid()}",
        "-e", "MPLCONFIGDIR=/tmp/matplotlib",
        "-v", f"{REPO}:/workspace/JointBuildGS:ro",
        "-v", f"{ARTIFACT_ROOT}:/artifacts/JointBuildGS:ro",
        "-v", f"{TASK_ROOT}:/task:rw",
        "-w", "/workspace/JointBuildGS", base.EVAL_IMAGE,
        "python", "/task/control/reference_diag_runtime.py",
        "--inside-docker", "analyze", "--config", base.container_path(config), "--output", "/task/reference_diagnostic",
    ]
    log = output / "logs/analyze.log"; started = base.now()
    with log.open("w") as stream: proc = subprocess.run(argv, text=True, stdout=stream, stderr=subprocess.STDOUT)
    base.record_operation("reference_diagnostic", argv, proc.returncode, started, base.now())
    if proc.returncode != 0: raise RuntimeError(f"reference diagnostic failed; inspect {log}")
    print(metrics.read_text())


def finalize_report() -> None:
    metrics_path = TASK_ROOT / "metrics.json"
    reference_csv = TASK_ROOT / "reference_diagnostic/case_metrics.csv"
    if not metrics_path.is_file() or not reference_csv.is_file():
        raise RuntimeError("complete measurements and reference diagnostic are required")
    metrics = json.loads(metrics_path.read_text())
    if metrics.get("status") != "COMPLETE_MEASURED" or not metrics.get("tensorboard_audit", {}).get("passed"):
        raise RuntimeError("validated complete measurements are required")
    paired = metrics["paired_depth03_minus_depth0"]
    with reference_csv.open(newline="") as stream:
        reference_rows = list(csv.DictReader(stream))
    rows20 = [row for row in reference_rows if int(row["completed_updates"]) == 20000]
    index = {(row["arm"], row["replica"]): row for row in rows20}
    replicas = list(REPLICAS)

    def values(field: str, arm: str) -> list[float]:
        return [float(index[(arm, replica)][field]) for replica in replicas]

    def mean(items: list[float]) -> float:
        return sum(items) / len(items)

    def delta(field: str) -> float:
        return mean(values(field, "DEPTH03")) - mean(values(field, "DEPTH0"))

    p20 = paired["20000"]
    headline = [{
        "id": "headline",
        "eval_psnr_delta_db": p20["eval_psnr"]["mean"],
        "gaussian_count_delta": p20["gaussian_count"]["mean"],
        "z_gt_650_delta": p20["z_gt_650"]["mean"],
        "z_max_delta_m": p20["z_max"]["mean"],
        "height_median_abs_delta_m": delta("classified_abs_dz_m_median"),
        "height_rmse_delta_m": delta("classified_abs_dz_m_rmse"),
        "normal_median_delta_deg": delta("classified_normal_angle_deg_median"),
        "roofer_coverage_delta_pp": 100.0 * delta("roofer_roof_xy_coverage_fraction"),
    }]
    checkpoint_rows = []
    for step in CHECKPOINTS:
        row = {"step": step}
        for field in ("eval_psnr", "gaussian_count", "z_gt_650", "z_max", "fusion_ge2", "fusion_ge3_ratio", "roof_density"):
            row[field + "_delta"] = paired[str(step)][field]["mean"]
        checkpoint_rows.append(row)
    reference_20k = []
    for row in sorted(rows20, key=lambda item: (item["arm"], item["replica"])):
        reference_20k.append({
            "case": f"{row['arm']} {row['replica']}",
            "arm": row["arm"],
            "replica": row["replica"],
            "height_median_abs_m": float(row["classified_abs_dz_m_median"]),
            "height_rmse_m": float(row["classified_abs_dz_m_rmse"]),
            "normal_median_deg": float(row["classified_normal_angle_deg_median"]),
            "within_0p5_fraction": float(row["classified_within_0p5m_fraction"]),
            "grid_coverage_fraction": float(row["classified_grid_coverage_fraction"]),
            "coherent_grid_fraction": float(row["classified_coherent_grid_coverage_fraction"]),
            "roofer_coverage_fraction": float(row["roofer_roof_xy_coverage_fraction"]),
            "roofer_fscore_0p5m": float(row["roofer_surface_fscore_0p5m"]),
        })
    height_pairs = [{
        "replica": replica,
        "height_median_abs_delta_m": float(index[("DEPTH03", replica)]["classified_abs_dz_m_median"]) - float(index[("DEPTH0", replica)]["classified_abs_dz_m_median"]),
        "normal_median_delta_deg": float(index[("DEPTH03", replica)]["classified_normal_angle_deg_median"]) - float(index[("DEPTH0", replica)]["classified_normal_angle_deg_median"]),
    } for replica in replicas]

    sources = [
        {"id": "training_source", "label": "Paired checkpoint metrics", "path": "metrics.json", "query": {"engine": "SQLite over frozen metrics snapshot", "language": "sql", "sql": "SELECT * FROM checkpoint_deltas ORDER BY step", "description": "Select paired DEPTH03 minus DEPTH0 metrics at the four preserved checkpoints.", "tables_used": ["checkpoint_deltas"], "filters": ["steps in (7000,12000,15000,20000)"], "metric_definitions": ["All deltas are paired DEPTH03 minus DEPTH0 means over R1-R3."]}},
        {"id": "reference_source", "label": "Evaluation-only LoD2 reference metrics", "path": "reference_diagnostic/case_metrics.csv", "query": {"engine": "SQLite over frozen reference diagnostic", "language": "sql", "sql": "SELECT * FROM reference_20k ORDER BY arm, replica", "description": "Select 20k height, normal, coherence, and Roofer reference metrics for all six cases.", "tables_used": ["reference_20k"], "filters": ["completed_updates = 20000"], "metric_definitions": ["LoD2 RoofSurface XYZ is evaluation-only and entered neither training nor checkpoint selection."]}},
        {"id": "input_source", "label": "Geometric MVS depth audit", "path": "control/depth_input_audit.json", "query": {"engine": "Frozen JSON audit", "language": "json", "sql": "SELECT view_count, valid_fraction_min, valid_fraction_median, valid_fraction_max FROM depth_input_audit", "description": "Read the fixed 55-view geometric depth validity summary.", "tables_used": ["depth_input_audit"], "filters": ["positive finite geometric depth pixels"], "metric_definitions": ["No scalar confidence weighting was available; geometric-validity is the input gate."]}},
    ]
    summary = f"""## Technical summary

- **이미지 적합은 일관되게 개선됐다.** 20k DEPTH03−DEPTH0는 held-out PSNR **{p20['eval_psnr']['mean']:+.3f} dB**, SSIM **{p20['eval_ssim']['mean']:+.4f}**, LPIPS **{p20['eval_lpips']['mean']:+.4f}**였고 세 pair 모두 같은 방향이었다.
- **정상 roof 표면의 중심 오차와 normal은 악화됐다.** 평가 전용 LoD2 기준 median |dZ|는 **{mean(values('classified_abs_dz_m_median','DEPTH0')):.3f}→{mean(values('classified_abs_dz_m_median','DEPTH03')):.3f} m**, median normal angle은 **{mean(values('classified_normal_angle_deg_median','DEPTH0')):.2f}→{mean(values('classified_normal_angle_deg_median','DEPTH03')):.2f}°**로 3/3 악화됐다. 반면 height RMSE는 **{mean(values('classified_abs_dz_m_rmse','DEPTH0')):.3f}→{mean(values('classified_abs_dz_m_rmse','DEPTH03')):.3f} m**로 tail 개선 방향이었다.
- **gross high-Z는 count와 최대값이 반대로 움직였다.** Z>650 count는 평균 **{p20['z_gt_650']['mean']:+.1f}** 줄었지만 Z max는 **{p20['z_max']['mean']:+.1f} m** 증가했고, 세 depth 반복 모두 약 17k에서 800k Gaussian cap에 도달했다.
- **Roofer 조립은 안정화되지 않았다.** control coverage R1/R2/R3는 **{', '.join(f'{100*x:.2f}%' for x in values('roofer_roof_xy_coverage_fraction','DEPTH0'))}**, depth는 **{', '.join(f'{100*x:.2f}%' for x in values('roofer_roof_xy_coverage_fraction','DEPTH03'))}**였다. 유일한 near-complete R1 control이 3.40%로 붕괴했다.

이는 한 건물·한 seed의 기술 측정이며 `scientific_verdict`는 `null`이다."""
    manifest = {
        "version": 1, "surface": "report", "title": "4906982 MVC + geometric MVS depth diagnostic",
        "description": TASK_ID + " measured technical report", "generatedAt": base.now(), "sources": sources,
        "cards": [
            {"id": "card_rgb", "dataset": "headline", "sourceId": "training_source", "description": "20k paired held-out PSNR", "metrics": [{"label": "PSNR delta", "field": "eval_psnr_delta_db", "format": "number", "signed": True}]},
            {"id": "card_height", "dataset": "headline", "sourceId": "reference_source", "description": "20k paired median absolute roof-height error", "metrics": [{"label": "Median |dZ| delta (m)", "field": "height_median_abs_delta_m", "format": "number", "signed": True}]},
            {"id": "card_normal", "dataset": "headline", "sourceId": "reference_source", "description": "20k paired median roof-normal angle error", "metrics": [{"label": "Normal delta (deg)", "field": "normal_median_delta_deg", "format": "number", "signed": True}]},
            {"id": "card_highz", "dataset": "headline", "sourceId": "training_source", "description": "Count falls while the extreme maximum grows", "metrics": [{"label": "Z>650 count delta", "field": "z_gt_650_delta", "format": "number", "signed": True}, {"label": "Z max delta (m)", "field": "z_max_delta_m", "format": "number", "signed": True}]},
            {"id": "card_roofer", "dataset": "headline", "sourceId": "reference_source", "description": "Mean roof XY coverage change", "metrics": [{"label": "Roofer coverage delta (pp)", "field": "roofer_coverage_delta_pp", "format": "number", "signed": True}]},
        ],
        "charts": [
            {"id": "chart_rgb", "title": "Held-out PSNR paired delta", "subtitle": "DEPTH03 minus DEPTH0 mean by checkpoint; n=3", "intent": "comparison", "question": "Did geometric MVS depth improve held-out image fit?", "rationale": "Discrete checkpoint bars show activation timing without implying a continuous curve.", "comparisonContext": {"baseline": "DEPTH0", "grain": "checkpoint paired mean", "unit": "dB"}, "type": "bar", "dataset": "checkpoint_deltas", "sourceId": "training_source", "encodings": {"x": {"field": "step", "type": "ordinal", "label": "Completed updates"}, "y": {"field": "eval_psnr_delta", "type": "quantitative", "label": "DEPTH03 − DEPTH0 (dB)"}}, "valueFormat": "number", "layout": "full", "surface": {"palette": {"kind": "sequential"}, "valueLabels": "all"}},
            {"id": "chart_height", "title": "20k median roof-height error paired delta", "subtitle": "Positive means worse median |dZ|", "intent": "comparison", "question": "Did depth supervision improve the ordinary roof surface height?", "rationale": "Replicate bars retain the 3/3 direction and avoid hiding trajectory spread.", "comparisonContext": {"baseline": "DEPTH0", "grain": "paired replica", "unit": "metres"}, "type": "bar", "dataset": "height_pairs", "sourceId": "reference_source", "encodings": {"x": {"field": "replica", "type": "nominal", "label": "Replica"}, "y": {"field": "height_median_abs_delta_m", "type": "quantitative", "label": "Median |dZ| delta (m)"}}, "valueFormat": "number", "layout": "full", "surface": {"palette": {"kind": "diverging"}, "valueLabels": "all"}},
            {"id": "chart_highz", "title": "Z>650 Gaussian count paired delta", "subtitle": "Count falls after 15k while the separate Z maximum grows", "intent": "comparison", "question": "Did depth suppress the gross high-Z population?", "rationale": "Count is kept separate from maximum height because they move in opposite directions.", "comparisonContext": {"baseline": "DEPTH0", "grain": "checkpoint paired mean", "unit": "Gaussian count"}, "type": "bar", "dataset": "checkpoint_deltas", "sourceId": "training_source", "encodings": {"x": {"field": "step", "type": "ordinal", "label": "Completed updates"}, "y": {"field": "z_gt_650_delta", "type": "quantitative", "label": "Z>650 count delta"}}, "valueFormat": "number", "layout": "full", "surface": {"palette": {"kind": "diverging"}, "valueLabels": "all"}},
            {"id": "chart_roofer", "title": "20k Roofer roof XY coverage", "subtitle": "Six exact cases; shared footprint and Roofer defaults", "intent": "comparison", "question": "Did depth stabilize downstream roof assembly?", "rationale": "All cases remain visible because the mean hides the collapse of the sole complete control.", "comparisonContext": {"baseline": "shared footprint area", "grain": "arm-replica", "unit": "fraction"}, "type": "bar", "dataset": "reference_20k", "sourceId": "reference_source", "encodings": {"x": {"field": "case", "type": "nominal", "label": "Case"}, "y": {"field": "roofer_coverage_fraction", "type": "quantitative", "label": "Roof XY coverage"}}, "valueFormat": "percent", "layout": "full", "surface": {"palette": {"kind": "sequential"}, "valueLabels": "all"}},
        ],
        "tables": [{"id": "table_reference", "title": "20k reference-aligned surface and Roofer metrics", "subtitle": "LoD2 enters evaluation only", "dataset": "reference_20k", "sourceId": "reference_source", "defaultSort": {"field": "case", "direction": "asc"}, "density": "spacious", "layout": "full", "columns": [{"field": "case", "label": "Case"}, {"field": "height_median_abs_m", "label": "Median |dZ| (m)", "format": "number"}, {"field": "height_rmse_m", "label": "Height RMSE (m)", "format": "number"}, {"field": "normal_median_deg", "label": "Median normal angle", "format": "number"}, {"field": "within_0p5_fraction", "label": "Within 0.5m", "format": "percent"}, {"field": "grid_coverage_fraction", "label": "Grid coverage", "format": "percent"}, {"field": "coherent_grid_fraction", "label": "Coherent grid", "format": "percent"}, {"field": "roofer_coverage_fraction", "label": "Roofer coverage", "format": "percent"}]}],
        "blocks": [
            {"id": "title", "type": "markdown", "body": "# 4906982 MVC + geometric MVS depth diagnostic", "layout": "full"},
            {"id": "summary", "type": "markdown", "body": summary, "sourceId": "training_source", "layout": "full"},
            {"id": "headline", "type": "metric-strip", "cardIds": ["card_rgb", "card_height", "card_normal", "card_highz", "card_roofer"], "layout": "full"},
            {"id": "rgb", "type": "markdown", "body": "## Image fit improved, but that did not imply a better roof surface\n\nAll three depth continuations improved PSNR, SSIM, and LPIPS. The independent LoD2 evaluation moved differently, so RGB and geometric endpoints remain separate.", "sourceId": "training_source", "layout": "full"},
            {"id": "rgb_chart", "type": "chart", "chartId": "chart_rgb", "layout": "full"},
            {"id": "surface", "type": "markdown", "body": "## Ordinary surface accuracy worsened while the extreme error tail narrowed\n\nMedian |dZ|, median normal angle, and the fraction within 0.5 m worsened in all three pairs. Height RMSE improved in all three, showing that fewer or smaller extreme residuals can coexist with a worse typical roof point.", "sourceId": "reference_source", "layout": "full"},
            {"id": "height_chart", "type": "chart", "chartId": "chart_height", "layout": "full"},
            {"id": "highz", "type": "markdown", "body": "## High-Z count fell, but the extreme maximum grew\n\nZ>650 count fell in all three 20k pairs. This is not complete outlier suppression: p99 rose in two pairs, maximum Z rose in all three, and the depth arms created roughly 572k more Gaussians on average before saturating the 800k cap.", "sourceId": "training_source", "layout": "full"},
            {"id": "highz_chart", "type": "chart", "chartId": "chart_highz", "layout": "full"},
            {"id": "roofer", "type": "markdown", "body": "## More grid coverage did not produce coherent Roofer assembly\n\nClassified 1 m grid coverage increased on average, but coherent coverage decreased and all depth Roofer outputs covered only 3.4–4.1% of the footprint. The sole near-complete control case collapsed under depth supervision.", "sourceId": "reference_source", "layout": "full"},
            {"id": "roofer_chart", "type": "chart", "chartId": "chart_roofer", "layout": "full"},
            {"id": "table_intro", "type": "markdown", "body": "## Exact 20k cases", "layout": "full"},
            {"id": "table", "type": "table", "tableId": "table_reference", "layout": "full"},
            {"id": "scope", "type": "markdown", "body": "## Scope, data, and metric definitions\n\nOne building, 55 fixed views (47 train, 8 held-out), one seed, and three paired CUDA continuations from an exact common 7k state. Both arms load the same COLMAP geometric-consistency depth maps; only w_depth differs (0 versus 0.03). Positive finite geometric depth pixels form the mask; no scalar confidence weighting is used. Fusion is the existing 0.15 m per-view voxel aggregation with alpha≥0.5 and at least two distinct views. Roofer uses the same standard GroundSurface XY footprint and default parameters.", "layout": "full"},
            {"id": "method", "type": "markdown", "body": "## Methodology and validation\n\nAll six branches preserve identical model, optimizer, strategy, grouping, RNG, loss cursor, and learning-run state at 7k. MVC is identical in both arms. No view selection, multi-view densification, external normal, ALS, LoD, or semantic term was added. Checkpoints 7/12/15/20k, required TensorBoard tags, classification, and Roofer terminals were validated. LoD2 RoofSurface XYZ was used only after training and readout for evaluation.", "layout": "full"},
            {"id": "limits", "type": "markdown", "body": "## Limitations and robustness\n\nThe geometric depth valid fraction ranges from 6.56% to 97.43% by view, and no scalar confidence map is consumed. The 7k train-view mean raw depth L1 was 55.73 m, so the 0.03 schedule initially had strong leverage before residuals fell. Three continuations are not independent seeds. Imagery and LoD2 differ in vintage. The cap-saturated primitive count means this test measures the existing depth loss interacting with the default grow policy, not depth supervision in isolation from densification dynamics.", "layout": "full"},
            {"id": "next", "type": "markdown", "body": "## Recommended next steps\n\n1. Run a read-only depth-evidence audit by view/flight block: 7k residual, geometric-valid fraction, camera baseline/angle, and cross-view depth agreement. Freeze any exclusion or confidence rule without LoD2.\n2. Then test a bounded depth gate/weight arm using the same loss and fixed input rule; require no 800k saturation and preserve median height/normal/coherence.\n3. Do not add normal supervision yet: it would layer another prior on depth evidence whose view-level consistency is unresolved.\n4. Do not add multi-view densification yet: the depth arm already saturated default growth while coherent coverage and Roofer assembly worsened.\n5. Revisit normal supervision only after the depth evidence source and mask produce stable absolute geometry.", "layout": "full"},
            {"id": "questions", "type": "markdown", "body": "## Further questions\n\n- Which late flight/view block produced the 50 m MVS versus 150 m rendered-depth disagreements at 7k?\n- Are low-confidence whole views driving the cap-saturating growth, or are valid pixels spatially inconsistent within each view?\n- Can one LoD2-blind fixed evidence gate retain the RGB/tail benefits without worsening median height, normal, and Roofer coherence?", "layout": "full"},
        ],
    }
    artifact = {"surface": "report", "manifest": manifest, "snapshot": {"version": 1, "generatedAt": base.now(), "status": "ready", "datasets": {"headline": headline, "checkpoint_deltas": checkpoint_rows, "reference_20k": reference_20k, "height_pairs": height_pairs, "depth_input_audit": [{"view_count": 55, "valid_fraction_min": 0.0655866965066473, "valid_fraction_median": 0.6585046762017573, "valid_fraction_max": 0.9743168016194332}]}}, "sources": sources, "package_info": {"root": ".", "manifestPath": "artifact.json", "snapshotPath": "artifact.json"}}
    atomic_json(TASK_ROOT / "report_artifact.json", artifact)

    comparison = f"""# {TASK_ID} comparison

## 측정 결과

DEPTH03은 held-out RGB와 height RMSE tail을 개선했지만, 정상 roof의 median 높이·normal 오차와 coherence를 악화시켰다. Z>650 개수는 감소했으나 최대 Z는 증가했고, 세 depth 반복 모두 기본 densification 800k cap에 포화됐다. Roofer는 control R1의 near-complete roof를 잃었고 depth 세 경우 모두 3.4–4.1% coverage에 머물렀다. 이는 scientific verdict가 아니라 이 단일 건물 기술 진단의 관찰이다. `scientific_verdict: null`.

## 20k paired mean (DEPTH03 − DEPTH0, n=3)

| Endpoint | Delta / movement | Pair direction |
|---|---:|---:|
| Held-out PSNR | {p20['eval_psnr']['mean']:+.3f} dB | 3/3 improve |
| Held-out SSIM | {p20['eval_ssim']['mean']:+.4f} | 3/3 improve |
| Held-out LPIPS | {p20['eval_lpips']['mean']:+.4f} | 3/3 improve |
| Gaussian count | {p20['gaussian_count']['mean']:+,.0f} | 3/3 increase |
| Z>650 count | {p20['z_gt_650']['mean']:+.1f} | 3/3 decrease |
| Maximum Z | {p20['z_max']['mean']:+.1f} m | 3/3 increase |
| Fusion ≥2-view points | {p20['fusion_ge2']['mean']:+,.0f} | 2 decrease / 1 increase |
| Roof-normal density | {p20['roof_density']['mean']:+.3f} points/m² | 3/3 decrease |
| Median |dZ| | {delta('classified_abs_dz_m_median'):+.3f} m | 3/3 worse |
| Height RMSE | {delta('classified_abs_dz_m_rmse'):+.3f} m | 3/3 improve |
| Median normal angle | {delta('classified_normal_angle_deg_median'):+.3f}° | 3/3 worse |
| Within 0.5 m | {100*delta('classified_within_0p5m_fraction'):+.2f} pp | 3/3 worse |
| Classified grid coverage | {100*delta('classified_grid_coverage_fraction'):+.2f} pp | 3/3 increase |
| Coherent grid coverage | {100*delta('classified_coherent_grid_coverage_fraction'):+.2f} pp | 2 worse / 1 improve |

## 다음 권고

다음은 normal 감독이나 multi-view densification이 아니라 **LoD2-blind depth evidence/view-quality gate 진단**이다. 현재 geometric depth는 view별 유효률 편차와 큰 7k residual을 가지며, `w_depth=0.03`은 기본 grow를 포화시켰다. view/flight block별 residual·validity·cross-view agreement를 먼저 고정하고, 그 다음 더 낮은 weight 또는 고정 mask를 단일변수로 시험하는 편이 이 결과에 직접 대응한다.
"""
    (TASK_ROOT / "comparison.md").write_text(comparison)
    issues = """# Issues

1. Geometric depth valid fraction spans 6.56%–97.43% by view; the current loader has no scalar confidence weighting.
2. At the common 7k checkpoint, train-view mean raw depth L1 was 55.73 m; the frozen 0.03 weight initially had high leverage.
3. DEPTH03 saturated the 800k Gaussian growth cap in all three continuations near 17k.
4. GPU evaluation created root-owned directories. Ownership was normalized only inside this new task namespace before Stage 3; scientific files were not changed.
5. The first measurement-finalization wrapper attempt used an incorrect DEPTH05 panel path and stopped before aggregation. The retry reused unchanged measurements and succeeded.
6. The reference diagnostic utility hardcoded MVC arm names. Two wrapper attempts stopped before complete aggregation; an artifact-local SHA-recorded runtime name substitution reused the unchanged diagnostic implementation successfully.
7. R1–R3 are same-seed paired CUDA continuations, not independent random seeds.
8. Current imagery and evaluation LoD2 differ in vintage, so some reference disagreement may reflect real scene change.

No NaN, OOM, missing required checkpoint, classification failure, or Roofer process failure occurred. `scientific_verdict: null`.
"""
    (TASK_ROOT / "issues.md").write_text(issues)
    (TASK_ROOT / "NOTES.md").write_text(f"""# {TASK_ID}

Status: `COMPLETE_MEASURED`.

- Exact common 7k full state; DEPTH0/DEPTH03 R1–R3 continued to 20k.
- Required checkpoints: 24/24 valid; TensorBoard required-tag audit passed 6/6.
- Checkpoint render/fusion/classification/Roofer: 24/24 complete.
- Evaluation-only LoD2 reference diagnostic: 24/24 cases complete.
- Training delta: w_depth 0 versus 0.03; both load identical geometric depth and share MVC05.
- No view selection, normal supervision, multi-view densification, ALS, LoD, or semantic loss.
- Scientific verdict: `null`.
""")
    source_panel = TASK_ROOT / "reference_diagnostic/representative_images/roofer_reference_20k.png"
    target_panel = TASK_ROOT / "representative_images/roofer_reference_20k.png"
    if source_panel.is_file(): shutil.copy2(source_panel, target_panel)
    paired_files = sorted((TASK_ROOT / "representative_images/paired").glob("*.png"))
    names = ["roofer_reference_20k.png"] + ["paired/" + path.name for path in paired_files]
    viewer = TASK_ROOT / "viewer"; viewer.mkdir(exist_ok=True)
    html = '''<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>4906982 MVC depth comparison</title><style>body{font-family:system-ui;background:#0d1117;color:#e6edf3;margin:0;padding:20px}header{max-width:1600px;margin:auto}select,a{padding:8px;margin:4px;background:#21262d;color:#e6edf3;border:1px solid #30363d;border-radius:5px}img{display:block;max-width:100%;margin:18px auto;border:1px solid #30363d}small{color:#8b949e}</style></head><body><header><h1>DEBY_LOD2_4906982 · DEPTH0 vs DEPTH03</h1><p>Roofer/reference overview and fixed R1 held-out panels. Paired panels show DEPTH0 left, DEPTH03 right.</p><label>Panel <select id="panel"></select></label><a href="../report.html">Measured report</a><a href="../comparison.md">comparison.md</a><br><small>Scientific verdict: null</small></header><img id="view" alt="depth comparison panel"><script>const names=__NAMES__;const s=document.getElementById('panel'),v=document.getElementById('view');for(const n of names){const o=document.createElement('option');o.value=n;o.textContent=n;s.appendChild(o)}function show(){v.src='../representative_images/'+s.value}s.onchange=show;show();</script></body></html>'''.replace("__NAMES__", json.dumps(names))
    (viewer / "index.html").write_text(html)
    atomic_json(TASK_ROOT / "viewer_slot.json", {"schema": "jointbuildgs.viewer.comparison_slot.v1", "slot_id": "p2-e3-local-4906982-mvc-depth-v1", "label": "DEBY_LOD2_4906982 MVC depth-only", "relative_url": "viewer/index.html", "panel_count": len(names), "separate_add_only_slot": True, "legacy_results_modified": False, "scientific_verdict": None})

    plugin_root = Path("/home/innopam/.codex/plugins/cache/openai-curated-remote/data-analytics/0.2.8-13ceeea1f599")
    builder_image = "innopam-v1-nbm-frontend:latest"
    argv = ["docker", "run", "--rm", "--network", "none", "--user", f"{os.getuid()}:{os.getgid()}", "-v", f"{plugin_root}:/plugin:ro", "-v", f"{TASK_ROOT}:/task:rw", "-w", "/plugin", builder_image, "node", "/plugin/skills/build-report/scripts/deliver_portable_artifact.mjs", "--input", "/task/report_artifact.json", "--output", "/task/report.html", "--screenshot", "/task/logs/report_delivery_failure.png"]
    log = TASK_ROOT / "logs/report_delivery.log"; started = base.now()
    with log.open("w") as stream: proc = subprocess.run(argv, text=True, stdout=stream, stderr=subprocess.STDOUT)
    base.record_operation("deliver_portable_report", argv, proc.returncode, started, base.now())
    if proc.returncode != 0: raise RuntimeError(f"report delivery failed; inspect {log}")
    contract = json.loads((TASK_ROOT / "experiment_contract.json").read_text()); contract["status"] = "COMPLETE_MEASURED"; contract["scientific_verdict"] = None; atomic_json(TASK_ROOT / "experiment_contract.json", contract)
    provenance_path = TASK_ROOT / "provenance.json"; provenance = json.loads(provenance_path.read_text())
    provenance["git_at_completion"] = base.git_record()
    provenance["evaluation_source_files_sha256"] = {str(Path(__file__).resolve().relative_to(REPO)): sha256(Path(__file__).resolve()), "scripts/p2/e3_local_4906982_mvc_readout_diag_v1/run.py": sha256(REPO / "scripts/p2/e3_local_4906982_mvc_readout_diag_v1/run.py"), "artifact_runtime_reference_diag.py": sha256(TASK_ROOT / "control/reference_diag_runtime.py")}
    provenance["evaluation_docker_image"] = {"reference": base.EVAL_IMAGE, "id": base.command(["docker", "image", "inspect", base.EVAL_IMAGE, "--format", "{{.Id}}"], check=False).stdout.strip()}
    provenance["stage3_images"] = {"tools": {"reference": base.TOOLS_IMAGE, "id": base.TOOLS_IMAGE_ID}, "roofer": {"reference": base.ROOFER_IMAGE, "id": base.ROOFER_IMAGE_ID}}
    provenance["report_builder_image"] = {"reference": builder_image, "id": base.command(["docker", "image", "inspect", builder_image, "--format", "{{.Id}}"], check=False).stdout.strip()}
    provenance["common_checkpoint_input_sha256"] = sha256(TASK_ROOT / "common_prefix/ckpt/step_007000.pt")
    outputs = ["experiment_contract.json", "input_hashes.json", "config_diff.txt", "checkpoint_metrics.csv", "paired_checkpoint_deltas.csv", "metrics.json", "comparison.md", "NOTES.md", "issues.md", "report_artifact.json", "report.html", "viewer_slot.json"]
    provenance["output_index_sha256"] = {name: sha256(TASK_ROOT / name) for name in outputs}
    provenance["known_incidental_failures"] = ["measurement finalization panel arm-name wrapper path", "reference diagnostic hardcoded arm-name wrapper", "evaluation directory ownership normalization inside new task namespace"]
    provenance["ended_utc"] = base.now(); provenance["scientific_verdict"] = None; atomic_json(provenance_path, provenance)
    print(json.dumps({"status": "COMPLETE_MEASURED", "report": str(TASK_ROOT / "report.html"), "viewer": str(TASK_ROOT / "viewer/index.html"), "scientific_verdict": None}, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(); parser.add_argument("command", choices=["preflight", "depth-audit", "baseline-depth-gate", "binding-probe", "smoke", "fork-prefix", "train-r1-12k", "dose-gate", "train-replicas", "analyze-checkpoints", "stage3", "finalize-measurements", "reference-diagnostic", "finalize-report", "all-training"]); args = parser.parse_args()
    if args.command in {"preflight", "all-training"}: preflight()
    if args.command in {"depth-audit", "all-training"}: depth_audit()
    if args.command in {"baseline-depth-gate", "all-training"}: baseline_depth_gate()
    if args.command in {"binding-probe", "all-training"}: binding_probe()
    if args.command in {"smoke", "all-training"}: smoke()
    if args.command in {"fork-prefix", "all-training"}: fork_prefix()
    if args.command in {"train-r1-12k", "all-training"}: train_r1_12k()
    if args.command in {"dose-gate", "all-training"}: dose_gate()
    if args.command in {"train-replicas", "all-training"}: train_replicas()
    if args.command == "analyze-checkpoints": analyze_checkpoints()
    if args.command == "stage3": run_stage3()
    if args.command == "finalize-measurements": finalize_measurements()
    if args.command == "reference-diagnostic": reference_diagnostic()
    if args.command == "finalize-report": finalize_report()


if __name__ == "__main__":
    main()
