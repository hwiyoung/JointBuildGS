#!/usr/bin/env python3
"""Idempotent paired MVC-only diagnostic for DEBY_LOD2_4906982.

The host side only orchestrates immutable Docker runs. Training remains owned by
``src.stage2.train``; this driver binds the reviewed v6 inputs, enforces the
three-key config-diff allowlist, performs the 7k full-state equality gate, and
delegates checkpoint read-out to its Docker-only inner commands.
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import difflib
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from typing import Any

import yaml


REPO = Path(__file__).resolve().parents[3]
ARTIFACT_ROOT = REPO.parent / "JointBuildGS-artifacts"
TASK_ID = "P2-E3-LOCAL-4906982-MVC-v1"
TASK_ROOT = ARTIFACT_ROOT / "phase-payloads/p2/e3_local_4906982_mvc_v1" / TASK_ID
CONFIG_DIR = REPO / "configs/p2/e3_local_4906982_mvc_v1"
CONFIGS = {"MVC0": CONFIG_DIR / "mvc0.yaml", "MVC05": CONFIG_DIR / "mvc05.yaml"}
IMAGE = "jointbuildgs:dev"
GPU = "1"
CHECKPOINTS = (7000, 12000, 15000, 20000)
V6_ROOT = ARTIFACT_ROOT / "phase-payloads/p2/e3_local_4906982_v1/P2-E3-LOCAL-4906982-2DGS-v6-dist0-resetoff-30k"
V6_SOURCE = V6_ROOT / "control/source_56f1e7cd0315fe0ab40d719ef0be901bb5dd3d7b"
EXACT_VIEWS = V6_ROOT / "control/exact_views.json"
VIEW_ROLES = V6_ROOT / "control/view_roles.json"
DATA_ROOT = V6_ROOT / "data/colmap_crop"
MVC_SOURCE = REPO / "src/stage2/loss/multiview.py"
MVC_SNAPSHOT = V6_SOURCE / "src/stage2/loss/multiview.py"
ALLOWLIST = {"run_id", "out_dir", "w_mvc"}


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_json(path: Path, body: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(body, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def atomic_text(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(body, encoding="utf-8")
    os.replace(temporary, path)


def run(command: list[str], *, check: bool = True, capture: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, check=check, text=True, capture_output=capture)


def docker_base(*, gpu: bool = False, name: str | None = None, rm: bool = True) -> list[str]:
    command = ["docker", "run"]
    if rm:
        command.append("--rm")
    if name:
        command += ["--name", name]
    if gpu:
        command += ["--gpus", f"device={GPU}", "--ipc=host"]
    command += [
        "-v", f"{REPO}:/workspace/JointBuildGS:ro",
        "-v", f"{ARTIFACT_ROOT}:/artifacts/JointBuildGS",
        "-w", "/workspace/JointBuildGS",
        IMAGE,
    ]
    return command


def config_values() -> dict[str, dict[str, Any]]:
    return {arm: yaml.safe_load(path.read_text(encoding="utf-8")) for arm, path in CONFIGS.items()}


def config_delta(a: dict[str, Any], b: dict[str, Any]) -> dict[str, tuple[Any, Any]]:
    return {key: (a.get(key), b.get(key)) for key in sorted(set(a) | set(b)) if a.get(key) != b.get(key)}


def git_state() -> dict[str, Any]:
    return {
        "commit": run(["git", "rev-parse", "HEAD"]).stdout.strip(),
        "branch": run(["git", "branch", "--show-current"]).stdout.strip(),
        "dirty": bool(run(["git", "status", "--porcelain"]).stdout),
        "status_porcelain": run(["git", "status", "--porcelain"]).stdout.splitlines(),
    }


def image_record() -> dict[str, Any]:
    body = json.loads(run(["docker", "image", "inspect", IMAGE]).stdout)[0]
    return {"reference": IMAGE, "id": body["Id"], "repo_digests": body.get("RepoDigests") or []}


def gpu_record() -> dict[str, Any]:
    fields = run([
        "nvidia-smi", f"--id={GPU}", "--query-gpu=index,name,uuid,memory.total,driver_version",
        "--format=csv,noheader,nounits",
    ]).stdout.strip().split(", ")
    return {"host_index": int(fields[0]), "model": fields[1], "uuid": fields[2], "memory_total_mib": int(fields[3]), "driver": fields[4]}


def input_inventory(configs: dict[str, dict[str, Any]]) -> dict[str, Any]:
    exact = json.loads(EXACT_VIEWS.read_text(encoding="utf-8"))
    roles = json.loads(VIEW_ROLES.read_text(encoding="utf-8"))
    exact_names = [row["basename"] for row in exact["rows"]]
    if exact_names != configs["MVC0"]["visible_views"] or exact_names != configs["MVC05"]["visible_views"]:
        raise RuntimeError("config visible_views drifted from reviewed exact_views row order")
    if roles["train_views"] != configs["MVC0"]["train_views"] or roles["eval_views"] != configs["MVC0"]["eval_views"]:
        raise RuntimeError("config split drifted from reviewed view_roles")
    if len(exact_names) != 55 or len(roles["train_views"]) != 47 or len(roles["eval_views"]) != 8:
        raise RuntimeError("reviewed 55/47/8 membership count drifted")
    images = []
    for name in exact_names:
        path = DATA_ROOT / "images" / name
        if not path.is_file():
            raise FileNotFoundError(path)
        images.append({"basename": name, "bytes": path.stat().st_size, "sha256": sha256(path)})
    sparse = {}
    for name in ("cameras.bin", "images.bin", "points3D.bin"):
        path = DATA_ROOT / "sparse/0" / name
        sparse[name] = {"path": str(path), "bytes": path.stat().st_size, "sha256": sha256(path)}
    combined = hashlib.sha256("".join(row["sha256"] for row in images).encode()).hexdigest()
    return {
        "schema": "jointbuildgs.p2.e3_local_4906982_mvc.input_hashes.v1",
        "created_utc": now(),
        "crop_root": str(DATA_ROOT),
        "exact_view_manifest": {"path": str(EXACT_VIEWS), "sha256": sha256(EXACT_VIEWS), "count": 55},
        "view_roles_manifest": {"path": str(VIEW_ROLES), "sha256": sha256(VIEW_ROLES), "train": 47, "held_out": 8},
        "crop_images": {"count": len(images), "combined_sha256": combined, "files": images},
        "camera_and_sparse_seed": sparse,
        "checkpoint_input": None,
        "fresh_training": True,
    }


def provenance_base() -> dict[str, Any]:
    source_paths = [
        REPO / "src/stage2/train.py", REPO / "src/stage2/renderer.py",
        REPO / "src/stage2/dataloader.py", MVC_SOURCE,
        REPO / "scripts/input_and_alignment/tum_transfer/run_b1.sh",
        REPO / "scripts/p2/c2_c3_rendered_depth_shared_footprint_199_v1/run.py",
        Path(__file__).resolve(),
    ]
    return {
        "schema": "jointbuildgs.p2.e3_local_4906982_mvc.provenance.v1",
        "task_id": TASK_ID,
        "git": git_state(),
        "docker_image": image_record(),
        "gpu": gpu_record(),
        "source_files_sha256": {str(path.relative_to(REPO)): sha256(path) for path in source_paths},
        "mvc_snapshot": {"path": str(MVC_SNAPSHOT), "sha256": sha256(MVC_SNAPSHOT), "byte_identical": MVC_SOURCE.read_bytes() == MVC_SNAPSHOT.read_bytes()},
        "configs_sha256": {arm: sha256(path) for arm, path in CONFIGS.items()},
        "random_seed": 0,
        "started_utc": now(),
        "ended_utc": None,
        "commands": [],
        "return_codes": [],
        "scientific_verdict": None,
    }


def append_operation(label: str, command: list[str], return_code: int, started: str, ended: str) -> None:
    path = TASK_ROOT / "provenance.json"
    body = json.loads(path.read_text(encoding="utf-8"))
    body["commands"].append({"label": label, "argv": command, "started_utc": started, "ended_utc": ended})
    body["return_codes"].append({"label": label, "return_code": return_code})
    atomic_json(path, body)


def preflight() -> None:
    configs = config_values()
    delta = config_delta(configs["MVC0"], configs["MVC05"])
    if set(delta) != ALLOWLIST:
        raise RuntimeError(f"config diff gate failed: actual={sorted(delta)}, allowed={sorted(ALLOWLIST)}")
    if delta["w_mvc"] != (0.0, 0.5):
        raise RuntimeError(f"w_mvc delta drifted: {delta['w_mvc']}")
    if MVC_SOURCE.read_bytes() != MVC_SNAPSHOT.read_bytes():
        raise RuntimeError("current multiview.py is not byte-identical to the v6 snapshot")
    marker = TASK_ROOT / "experiment_contract.json"
    if TASK_ROOT.exists() and any(TASK_ROOT.iterdir()) and not marker.is_file():
        raise RuntimeError(f"non-empty unbound task namespace: {TASK_ROOT}")
    TASK_ROOT.mkdir(parents=True, exist_ok=True)
    (TASK_ROOT / "control").mkdir(exist_ok=True)
    (TASK_ROOT / "logs").mkdir(exist_ok=True)
    for arm in CONFIGS:
        for child in ("ckpt", "tb", "logs", "fusion", "roofer"):
            (TASK_ROOT / "arms" / arm / child).mkdir(parents=True, exist_ok=True)
    (TASK_ROOT / "representative_images").mkdir(exist_ok=True)
    inventory = input_inventory(configs)
    atomic_json(TASK_ROOT / "input_hashes.json", inventory)
    diff = "".join(difflib.unified_diff(
        CONFIGS["MVC0"].read_text().splitlines(True), CONFIGS["MVC05"].read_text().splitlines(True),
        fromfile="mvc0.yaml", tofile="mvc05.yaml",
    ))
    atomic_text(TASK_ROOT / "config_diff.txt", "allowed_keys: out_dir, run_id, w_mvc\nactual_keys: " + ", ".join(delta) + "\n\n" + diff)
    contract = {
        "schema": "jointbuildgs.p2.e3_local_4906982_mvc.contract.v1",
        "task_id": TASK_ID, "building_id": "DEBY_LOD2_4906982",
        "status": "PREFLIGHT_BOUND", "arms": ["MVC0", "MVC05"],
        "sole_training_objective_delta": {"key": "w_mvc", "MVC0": 0.0, "MVC05": 0.5},
        "operational_delta_allowlist": ["out_dir", "run_id"],
        "views": {"exact": 55, "train": 47, "held_out": 8},
        "checkpoints_completed_updates": list(CHECKPOINTS),
        "preactivation_gate": {"step": 7000, "must_pass_before_MVC05_resume": True},
        "fusion": {"source": "checkpoint_rendered_median_depth", "render_downscale": 0.25, "alpha_min": 0.5, "valid_depth_m": [0.01, 500.0], "voxel_m": 0.15, "minimum_distinct_view_support": 2, "post_fusion_voxel_downsampling": False},
        "roofer": {"shared_standard_groundsurface_xy": True, "quality_parameters": "ROOFER_DEFAULTS", "quality_driven_retry_allowed": False},
        "rel_thresh_interpretation": "gross high-Z outliers may be excluded from MVC inliers; high-Z persistence and normal-surface improvement are reported separately",
        "official_PASS_usable": None, "scientific_verdict": None,
    }
    atomic_json(marker, contract)
    if not (TASK_ROOT / "provenance.json").exists():
        atomic_json(TASK_ROOT / "provenance.json", provenance_base())
    atomic_text(TASK_ROOT / "NOTES.md", f"# {TASK_ID}\n\nPreflight bound at {now()}. Training has not started.\n\nScientific verdict: null.\n")
    print(json.dumps({"task_root": str(TASK_ROOT), "config_diff_keys": sorted(delta), "multiview_byte_identical": True, "view_counts": [55, 47, 8], "image_id": image_record()["id"], "gpu": gpu_record()["model"]}, indent=2))


def runtime_config(source: Path, destination: Path, updates: dict[str, Any]) -> None:
    body = yaml.safe_load(source.read_text(encoding="utf-8"))
    body.update(updates)
    destination.parent.mkdir(parents=True, exist_ok=True)
    atomic_text(destination, yaml.safe_dump(body, sort_keys=False))


def smoke() -> None:
    receipt = TASK_ROOT / "control/smoke_receipt.json"
    if receipt.is_file() and json.loads(receipt.read_text()).get("passed"):
        print(receipt.read_text())
        return
    smoke_root = TASK_ROOT / "smoke"
    (TASK_ROOT / "control").mkdir(parents=True, exist_ok=True)
    (TASK_ROOT / "logs").mkdir(parents=True, exist_ok=True)
    cfg_host = TASK_ROOT / "control/smoke_mvc05.yaml"
    cfg_container = "/artifacts/JointBuildGS/phase-payloads/p2/e3_local_4906982_mvc_v1/P2-E3-LOCAL-4906982-MVC-v1/control/smoke_mvc05.yaml"
    runtime_config(CONFIGS["MVC05"], cfg_host, {
        "out_dir": "/artifacts/JointBuildGS/phase-payloads/p2/e3_local_4906982_mvc_v1/P2-E3-LOCAL-4906982-MVC-v1/smoke",
        "max_iter": 12, "eval_every": 100000, "ckpt_every": 100000,
        "full_state_checkpoint": False, "full_state_checkpoint_steps": [], "full_state_resume": "off",
        "mvc_warmup": 0, "mvc_ramp_steps": 1, "refine_start_iter": 500,
    })
    log = TASK_ROOT / "logs/smoke.log"
    command = docker_base(gpu=True) + ["python", "-m", "src.stage2.train", "--config", cfg_container]
    already_complete = (smoke_root / "ckpt/final.pt").is_file() and "[done] 12 iter" in (log.read_text(encoding="utf-8", errors="replace") if log.is_file() else "")
    if already_complete:
        return_code = 0
    else:
        started = now()
        with log.open("w", encoding="utf-8") as stream:
            proc = subprocess.run(command, text=True, stdout=stream, stderr=subprocess.STDOUT)
        return_code = proc.returncode
        append_operation("mvc_smoke", command, return_code, started, now())
    text = log.read_text(encoding="utf-8", errors="replace")
    scalar_cmd = docker_base() + ["python", "-c", (
        "from tensorboard.backend.event_processing.event_accumulator import EventAccumulator as E;"
        "import json,glob; p=glob.glob('/artifacts/JointBuildGS/phase-payloads/p2/e3_local_4906982_mvc_v1/P2-E3-LOCAL-4906982-MVC-v1/smoke/tb/events*')[0];"
        "e=E(p);e.Reload();print(json.dumps({k:max([x.value for x in e.Scalars(k)] or [0]) for k in ['loss/mvc','stats/mvc_n_inlier']}))"
    )]
    if return_code == 0:
        scalar_output = run(scalar_cmd).stdout.splitlines()
        scalar = json.loads(next(line for line in reversed(scalar_output) if line.strip().startswith("{")))
    else:
        scalar = {}
    passed = return_code == 0 and "avg 2.0 neighbors/view" in text and scalar.get("loss/mvc", 0) > 0 and scalar.get("stats/mvc_n_inlier", 0) > 0
    atomic_json(receipt, {"schema": "jointbuildgs.p2.e3_local_4906982_mvc.smoke.v1", "created_utc": now(), "return_code": return_code, "neighbor_summary_found": "avg 2.0 neighbors/view" in text, "scalars": scalar, "passed": passed, "scientific_verdict": None})
    if not passed:
        raise RuntimeError(f"MVC smoke failed; inspect {log}")
    shutil.rmtree(smoke_root, ignore_errors=True)
    print(json.dumps(json.loads(receipt.read_text()), indent=2))


def checkpoint_valid(arm: str, step: int) -> bool:
    path = TASK_ROOT / "arms" / arm / "ckpt" / f"step_{step:06d}.pt"
    sidecar = Path(str(path) + ".sha256")
    return path.is_file() and sidecar.is_file() and sidecar.read_text().split()[0] == sha256(path)


def train_process(arm: str, *, stop_at_7k: bool = False, resume: bool = False) -> int:
    if checkpoint_valid(arm, 20000):
        return 0
    runtime = TASK_ROOT / "control/runtime" / f"{arm.lower()}_{'resume' if resume else 'fresh'}.yaml"
    source = CONFIGS[arm]
    runtime_config(source, runtime, {"full_state_resume": "auto" if resume else "off"})
    container_cfg = "/artifacts/JointBuildGS/" + str(runtime.relative_to(ARTIFACT_ROOT))
    name = f"jbgs-e3-4906982-{arm.lower()}"
    subprocess.run(["docker", "rm", "-f", name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    command = docker_base(gpu=True, name=name, rm=False) + ["python", "-m", "src.stage2.train", "--config", container_cfg]
    log = TASK_ROOT / "arms" / arm / "logs" / ("train_resume.log" if resume else "train.log")
    vram = TASK_ROOT / "arms" / arm / "logs" / "vram_used_mib.tsv"
    started = now()
    start_time = time.monotonic()
    max_vram = 0
    with log.open("a", encoding="utf-8") as stream:
        proc = subprocess.Popen(command, text=True, stdout=stream, stderr=subprocess.STDOUT)
        with vram.open("a", encoding="utf-8") as meter:
            if vram.stat().st_size == 0:
                meter.write("utc\tused_mib\n")
            while proc.poll() is None:
                query = subprocess.run(["nvidia-smi", f"--id={GPU}", "--query-gpu=memory.used", "--format=csv,noheader,nounits"], text=True, capture_output=True)
                try:
                    used = int(query.stdout.strip())
                    max_vram = max(max_vram, used)
                    meter.write(f"{now()}\t{used}\n")
                    meter.flush()
                except ValueError:
                    pass
                if stop_at_7k and checkpoint_valid(arm, 7000):
                    subprocess.run(["docker", "stop", "-t", "10", name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    break
                time.sleep(2)
        rc = proc.wait()
    ended = now()
    subprocess.run(["docker", "rm", "-f", name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    atomic_json(TASK_ROOT / "arms" / arm / "logs" / ("runtime_resume.json" if resume else "runtime.json"), {"started_utc": started, "ended_utc": ended, "wall_seconds": time.monotonic() - start_time, "max_vram_mib": max_vram, "return_code": rc, "stopped_for_7k_gate": bool(stop_at_7k and checkpoint_valid(arm, 7000)), "scientific_verdict": None})
    append_operation(f"train_{arm}_{'resume' if resume else 'fresh'}", command, rc, started, ended)
    if stop_at_7k and checkpoint_valid(arm, 7000):
        return 0
    if rc != 0:
        raise RuntimeError(f"{arm} training failed rc={rc}; inspect {log}")
    return rc


def equality_gate() -> None:
    receipt = TASK_ROOT / "control/preactivation_equality_7000.json"
    if receipt.is_file() and json.loads(receipt.read_text()).get("passed"):
        print(receipt.read_text())
        return
    if not all(checkpoint_valid(arm, 7000) for arm in CONFIGS):
        raise RuntimeError("both valid 7k checkpoints are required")
    a = "/artifacts/JointBuildGS/" + str((TASK_ROOT / "arms/MVC0/ckpt/step_007000.pt").relative_to(ARTIFACT_ROOT))
    b = "/artifacts/JointBuildGS/" + str((TASK_ROOT / "arms/MVC05/ckpt/step_007000.pt").relative_to(ARTIFACT_ROOT))
    out = "/artifacts/JointBuildGS/" + str(receipt.relative_to(ARTIFACT_ROOT))
    code = r'''
import json,math,numpy as np,torch
from pathlib import Path
a,b,out=map(Path,__import__('sys').argv[1:])
A=torch.load(a,map_location='cpu',weights_only=False); B=torch.load(b,map_location='cpu',weights_only=False)
def compare(x,y,path=''):
    bad=[]
    if torch.is_tensor(x) and torch.is_tensor(y):
        if x.dtype!=y.dtype or x.shape!=y.shape or not torch.equal(x,y): bad.append(path)
    elif isinstance(x,np.ndarray) and isinstance(y,np.ndarray):
        if x.dtype!=y.dtype or x.shape!=y.shape or not np.array_equal(x,y,equal_nan=True): bad.append(path)
    elif isinstance(x,dict) and isinstance(y,dict):
        if set(x)!=set(y): bad.append(path+'.keys')
        for k in sorted(set(x)&set(y),key=str): bad += compare(x[k],y[k],path+'/'+str(k))
    elif isinstance(x,(list,tuple)) and isinstance(y,(list,tuple)):
        if len(x)!=len(y): bad.append(path+'.len')
        for i,(u,v) in enumerate(zip(x,y)): bad += compare(u,v,path+'/'+str(i))
    elif isinstance(x,float) and isinstance(y,float) and math.isnan(x) and math.isnan(y): pass
    elif type(x)!=type(y) or x!=y: bad.append(path)
    return bad
sections=['model','optimizers','strategy','grouping_state','rng_state','loss_log_cursor']
result={s:compare(A[s],B[s],s) for s in sections}
bad={k:v[:100] for k,v in result.items() if v}
body={'schema':'jointbuildgs.p2.e3_local_4906982_mvc.preactivation_equality.v1','completed_updates':7000,'compared_sections':sections,'mismatches':bad,'passed':not bad,'scientific_verdict':None}
out.parent.mkdir(parents=True,exist_ok=True); out.write_text(json.dumps(body,indent=2,sort_keys=True)+'\n')
print(json.dumps(body))
raise SystemExit(0 if body['passed'] else 2)
'''
    command = docker_base() + ["python", "-c", code, a, b, out]
    proc = run(command, check=False)
    append_operation("preactivation_equality_7000", command, proc.returncode, now(), now())
    if proc.returncode != 0:
        detail = proc.stderr.strip() or proc.stdout.strip()
        atomic_text(TASK_ROOT / "issues.md", "# Issues\n\n- 7k pre-activation equality gate did not pass. Arm B was not resumed. See `control/preactivation_equality_7000.json`.\n\n```text\n" + detail[-4000:] + "\n```\n")
        raise RuntimeError("7k pre-activation equality gate failed; MVC05 remains stopped")
    issues = TASK_ROOT / "issues.md"
    if issues.is_file():
        atomic_text(issues, "# Issues\n\n- RESOLVED orchestration issue: the first equality comparator referenced a nonexistent checkpoint key and exited before writing a receipt. No training was resumed. The corrected comparator then evaluated the same preserved 7k checkpoints.\n")
    print(proc.stdout)


def train_pair() -> None:
    smoke_receipt = TASK_ROOT / "control/smoke_receipt.json"
    if not smoke_receipt.is_file() or not json.loads(smoke_receipt.read_text()).get("passed"):
        raise RuntimeError("smoke gate must pass before training")
    train_process("MVC0")
    if not checkpoint_valid("MVC0", 20000):
        raise RuntimeError("MVC0 did not produce a valid 20k checkpoint")
    gate = TASK_ROOT / "control/preactivation_equality_7000.json"
    if not checkpoint_valid("MVC05", 7000):
        train_process("MVC05", stop_at_7k=True)
    equality_gate()
    if not json.loads(gate.read_text()).get("passed"):
        raise RuntimeError("preactivation gate is not passed")
    if not checkpoint_valid("MVC05", 20000):
        train_process("MVC05", resume=True)
    missing = [(arm, step) for arm in CONFIGS for step in CHECKPOINTS if not checkpoint_valid(arm, step)]
    if missing:
        raise RuntimeError(f"required checkpoints missing/invalid: {missing}")
    print(json.dumps({"training_complete": True, "checkpoint_steps": CHECKPOINTS, "preactivation_equality": True}, indent=2))


def diagnose_blocked_gate() -> None:
    """Measure only preserved state after the mandatory stop; never resume training."""
    gate = TASK_ROOT / "control/preactivation_equality_7000.json"
    if not gate.is_file() or json.loads(gate.read_text()).get("passed"):
        raise RuntimeError("this diagnostic is only valid after a failed 7k gate")
    output = TASK_ROOT / "control/confound_analysis.json"
    output_container = "/artifacts/JointBuildGS/" + str(output.relative_to(ARTIFACT_ROOT))
    root_container = "/artifacts/JointBuildGS/" + str(TASK_ROOT.relative_to(ARTIFACT_ROOT))
    data_container = "/artifacts/JointBuildGS/" + str(DATA_ROOT.relative_to(ARTIFACT_ROOT))
    code = r'''
import json,math,torch
from pathlib import Path
from tensorboard.backend.event_processing.event_accumulator import EventAccumulator
from src.stage2.colmap_io import read_points3d_bin
root,data,out=map(Path,__import__('sys').argv[1:])
offset_z=604.0
seed=read_points3d_bin(data/'sparse/0/points3D.bin')[:,:3]
seed_max=float(seed[:,2].max())
def events(arm):
    e=EventAccumulator(str(next((root/'arms'/arm/'tb').glob('events*')))); e.Reload(); return e
ev={a:events(a) for a in ['MVC0','MVC05']}
def scalar(arm,tag,step):
    rows=[x for x in ev[arm].Scalars(tag) if x.step <= step-1]
    return None if not rows else {'step':rows[-1].step,'value':rows[-1].value}
def q(t,vals):
    return [float(x) for x in torch.quantile(t.float(),torch.tensor(vals))]
rows=[]
for arm,steps in [('MVC0',[7000,12000,15000,20000]),('MVC05',[7000])]:
  for step in steps:
    p=root/'arms'/arm/'ckpt'/f'step_{step:06d}.pt'
    x=torch.load(p,map_location='cpu',weights_only=False); s=x['model']['state_dict']
    z=s['means'][:,2].float(); op=torch.sigmoid(s['opacities_raw'].flatten().float())
    scale=torch.exp(s['log_scales'].float()); lo=torch.minimum(scale[:,0],scale[:,1]); hi=torch.maximum(scale[:,0],scale[:,1]); elong=lo/hi.clamp_min(1e-12)
    zq=q(z,[0,.5,.95,.99,1]); high=z>46.0; over_seed=z>seed_max
    bins={}
    for label,low,high_op,last in [('lt_0p1',0,.1,False),('0p1_0p5',.1,.5,False),('0p5_0p9',.5,.9,False),('ge_0p9',.9,1.000001,True)]:
      mask=(op>=low)&(op<high_op); bins[label]={'all':int(mask.sum()),'z_gt_650m':int((mask&high).sum())}
    strategy=x['strategy']['state']
    rows.append({
      'arm':arm,'completed_updates':step,'checkpoint_sha256':__import__('hashlib').sha256(p.read_bytes()).hexdigest(),
      'gaussian_count':int(z.numel()),'z_local_min':zq[0],'z_local_median':zq[1],'z_local_p95':zq[2],'z_local_p99':zq[3],'z_local_max':zq[4],
      'z_epsg25832_min':zq[0]+offset_z,'z_epsg25832_median':zq[1]+offset_z,'z_epsg25832_p95':zq[2]+offset_z,'z_epsg25832_p99':zq[3]+offset_z,'z_epsg25832_max':zq[4]+offset_z,
      'seed_max_z_local':seed_max,'seed_max_z_epsg25832':seed_max+offset_z,'count_above_seed_max_z':int(over_seed.sum()),'count_z_gt_650m':int(high.sum()),
      'opacity_mean':float(op.mean()),'opacity_median':float(op.median()),'opacity_bins':bins,
      'scale_min_q50_q95_q99_max':q(lo,[.5,.95,.99,1]),'scale_max_q50_q95_q99_max':q(hi,[.5,.95,.99,1]),'elongation_q01_q05_q50_q95':q(elong,[.01,.05,.5,.95]),
      'cum_grow_duplicated':int(strategy.get('cum_grow_duplicated',0)),'cum_grow_split':int(strategy.get('cum_grow_split',0)),'cum_pruned':int(strategy.get('cum_pruned',0)),
      'train_psnr':scalar(arm,'metric/psnr_train',step),'eval_psnr':scalar(arm,'eval/psnr',step),'loss_mvc':scalar(arm,'loss/mvc',step),'loss_mvc_depth':scalar(arm,'loss/mvc_depth',step),'loss_mvc_normal':scalar(arm,'loss/mvc_normal',step),'mvc_n_inlier':scalar(arm,'stats/mvc_n_inlier',step),'loss_nc':scalar(arm,'loss/nc',step),
    })
tags=['loss/total','loss/photo','metric/psnr_train','stats/gaussian_count','eval/psnr']
div={}
for tag in tags:
    a={x.step:x.value for x in ev['MVC0'].Scalars(tag) if x.step<7000}; b={x.step:x.value for x in ev['MVC05'].Scalars(tag) if x.step<7000}; common=sorted(set(a)&set(b))
    exact=[s for s in common if a[s]!=b[s]]; tol=[s for s in common if not math.isclose(a[s],b[s],rel_tol=1e-6,abs_tol=1e-8)]
    div[tag]={'common_samples':len(common),'first_exact_mismatch_step':exact[0] if exact else None,'first_tolerance_mismatch_step':tol[0] if tol else None,'max_abs_delta':max((abs(a[s]-b[s]) for s in common),default=0.0),'mvc0_last':a[common[-1]] if common else None,'mvc05_last':b[common[-1]] if common else None}
body={'schema':'jointbuildgs.p2.e3_local_4906982_mvc.confound_analysis.v1','status':'BLOCKED_PREACTIVATION_CONFOUND','world_offset':[690953.0,5336071.0,604.0],'seed_point_count':int(len(seed)),'seed_max_z_local':seed_max,'seed_max_z_epsg25832':seed_max+offset_z,'checkpoint_rows':rows,'preactivation_scalar_divergence':div,'observed_equal_sections':['grouping_state','rng_state','loss_log_cursor'],'observed_unequal_sections':['model','optimizers','strategy'],'trainer_determinism_controls':{'seeded_python_numpy_torch_cuda':True,'torch_deterministic_algorithms_enabled_by_trainer':False,'cudnn_deterministic_enabled_by_trainer':False},'scientific_verdict':None}
out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(body,indent=2,sort_keys=True)+'\n');print(json.dumps({'rows':len(rows),'status':body['status']}))
'''
    command = docker_base() + ["python", "-c", code, root_container, data_container, output_container]
    started = now()
    proc = run(command, check=False)
    append_operation("diagnose_failed_7k_gate", command, proc.returncode, started, now())
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr or proc.stdout)
    body = json.loads(output.read_text(encoding="utf-8"))
    fields = [
        "arm", "completed_updates", "gaussian_count", "z_epsg25832_min", "z_epsg25832_median", "z_epsg25832_p95", "z_epsg25832_p99", "z_epsg25832_max",
        "seed_max_z_epsg25832", "count_above_seed_max_z", "count_z_gt_650m", "opacity_mean", "opacity_median", "cum_grow_duplicated", "cum_grow_split", "cum_pruned",
        "train_psnr", "eval_psnr", "loss_mvc", "loss_mvc_depth", "loss_mvc_normal", "mvc_n_inlier", "loss_nc",
    ]
    csv_path = TASK_ROOT / "checkpoint_metrics.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for row in body["checkpoint_rows"]:
            flat = {key: row.get(key) for key in fields}
            for key in ("train_psnr", "eval_psnr", "loss_mvc", "loss_mvc_depth", "loss_mvc_normal", "mvc_n_inlier", "loss_nc"):
                flat[key] = None if row.get(key) is None else row[key]["value"]
            writer.writerow(flat)
    a7 = next(row for row in body["checkpoint_rows"] if row["arm"] == "MVC0" and row["completed_updates"] == 7000)
    b7 = next(row for row in body["checkpoint_rows"] if row["arm"] == "MVC05" and row["completed_updates"] == 7000)
    metrics = {
        "schema": "jointbuildgs.p2.e3_local_4906982_mvc.metrics.v1", "task_id": TASK_ID,
        "status": "BLOCKED_PREACTIVATION_CONFOUND", "preactivation_equality_passed": False,
        "seven_k": {"MVC0": a7, "MVC05": b7, "gaussian_count_delta_MVC05_minus_MVC0": b7["gaussian_count"] - a7["gaussian_count"], "eval_psnr_delta": b7["eval_psnr"]["value"] - a7["eval_psnr"]["value"]},
        "scalar_divergence": body["preactivation_scalar_divergence"],
        "unavailable_due_to_gate": ["MVC05 checkpoints 12k/15k/20k", "paired SSIM and LPIPS", "held-out paired qualitative panels", "post-activation MVC comparison", "depth fusion", "support ratios", "footprint roof/wall density", "Roofer", "viewer comparison slot"],
        "rel_thresh_observation": "No post-activation MVC result exists. Gross high-Z persistence versus normal-surface improvement cannot be separated in this blocked run.",
        "official_PASS_usable": None, "scientific_verdict": None,
    }
    atomic_json(TASK_ROOT / "metrics.json", metrics)
    first = body["preactivation_scalar_divergence"]
    comparison = f"""# {TASK_ID} comparison

Status: **BLOCKED_PREACTIVATION_CONFOUND**. Scientific verdict remains `null`.

The mandatory 7k equality gate did not pass, so MVC05 was not resumed and no post-activation, fusion, Roofer, or viewer comparison was produced.

| 7k observation | MVC0 | MVC05 | delta (MVC05-MVC0) |
|---|---:|---:|---:|
| Gaussian count | {a7['gaussian_count']} | {b7['gaussian_count']} | {b7['gaussian_count']-a7['gaussian_count']} |
| held-out PSNR (last pre-7k eval) | {a7['eval_psnr']['value']:.6f} | {b7['eval_psnr']['value']:.6f} | {b7['eval_psnr']['value']-a7['eval_psnr']['value']:+.6f} |
| EPSG:25832 Z p99 (m) | {a7['z_epsg25832_p99']:.3f} | {b7['z_epsg25832_p99']:.3f} | {b7['z_epsg25832_p99']-a7['z_epsg25832_p99']:+.3f} |
| Z > 650 m count | {a7['count_z_gt_650m']} | {b7['count_z_gt_650m']} | {b7['count_z_gt_650m']-a7['count_z_gt_650m']} |

First scalar divergence was observed at step {first['metric/psnr_train']['first_exact_mismatch_step']} for train PSNR (exact) and step {first['stats/gaussian_count']['first_exact_mismatch_step']} for Gaussian count. By 5k the checkpoint Gaussian counts already differed, so this precedes MVC activation and confounds any MVC effect estimate.

The trainer seeds Python, NumPy, Torch CPU and CUDA RNGs, but it does not enable PyTorch deterministic algorithms or deterministic cuDNN controls. This is a plausible mechanism for separate-process CUDA/gsplat divergence; it is recorded as a technical hypothesis, not a proven cause.

## Observation boundary

`mvc_rel_thresh=0.1` can exclude gross high-Z outliers from MVC inliers, but no post-activation paired result exists here. Therefore neither high-Z change nor normal-surface improvement is attributed to MVC in this run.

## Next recommendation

Before rerunning this experiment, add and validate a deterministic paired-start protocol (for example, one shared exact 7k full-state checkpoint followed by two bound forks, or a separately approved deterministic-kernel preflight). That changes the execution contract and requires human approval; it was not attempted here.
"""
    atomic_text(TASK_ROOT / "comparison.md", comparison)
    notes = f"""# {TASK_ID}

- Preflight and MVC smoke passed.
- MVC0 fresh training completed to 20k; its requested checkpoints are preserved.
- MVC05 fresh training was stopped after its 7k atomic checkpoint (the process had advanced only in uncheckpointed state to about 7.2k).
- The 7k equality gate failed: model, optimizer and densification state differed; RNG, grouping and loss cursor state matched.
- MVC05 was not resumed. Checkpoint evaluation beyond state-only confound measurements, depth fusion, Roofer, and viewer wiring were not run.
- One initial equality-comparator implementation error occurred before any receipt was written; it was corrected without resuming training. `issues.md` retains both the tooling incident and final gate failure.
- No existing legacy or v6 payload was modified.
- No commit was created.
- Scientific verdict: `null`.
"""
    atomic_text(TASK_ROOT / "NOTES.md", notes)
    atomic_text(TASK_ROOT / "representative_images/README.md", "# Representative images\n\nNot generated: the mandatory pre-activation equality gate failed before a valid paired comparison existed.\n")
    atomic_text(TASK_ROOT / "issues.md", "# Issues\n\n- RESOLVED tooling incident: the first equality comparator referenced a nonexistent checkpoint key and exited before writing a receipt. No training was resumed; the same preserved 7k checkpoints were rechecked.\n- OPEN confound: the corrected 7k equality gate failed for model, optimizer, and densification state. MVC05 was not resumed.\n")
    contract = json.loads((TASK_ROOT / "experiment_contract.json").read_text())
    contract["status"] = "BLOCKED_PREACTIVATION_CONFOUND"
    contract["preactivation_gate"]["passed"] = False
    contract["preactivation_gate"]["action"] = "MVC05_NOT_RESUMED"
    atomic_json(TASK_ROOT / "experiment_contract.json", contract)
    provenance = json.loads((TASK_ROOT / "provenance.json").read_text())
    input_hashes = json.loads((TASK_ROOT / "input_hashes.json").read_text())
    provenance["input_sha256"] = {
        "exact_view_manifest": input_hashes["exact_view_manifest"]["sha256"],
        "view_roles_manifest": input_hashes["view_roles_manifest"]["sha256"],
        "crop_images_combined": input_hashes["crop_images"]["combined_sha256"],
        "camera_intrinsics_extrinsics": {
            key: input_hashes["camera_and_sparse_seed"][key]["sha256"]
            for key in ("cameras.bin", "images.bin")
        },
        "sparse_sfm_seed_points3D": input_hashes["camera_and_sparse_seed"]["points3D.bin"]["sha256"],
        "checkpoint_input": None,
    }
    provenance["ended_utc"] = now()
    provenance["status"] = "BLOCKED_PREACTIVATION_CONFOUND"
    provenance["source_files_sha256"][str(Path(__file__).resolve().relative_to(REPO))] = sha256(Path(__file__).resolve())
    atomic_json(TASK_ROOT / "provenance.json", provenance)
    print(json.dumps({"status": metrics["status"], "gaussian_count_7k": {"MVC0": a7["gaussian_count"], "MVC05": b7["gaussian_count"]}, "task_root": str(TASK_ROOT)}, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["preflight", "smoke", "train", "diagnose-blocked", "all"])
    args = parser.parse_args()
    if args.command in {"preflight", "all"}:
        preflight()
    if args.command in {"smoke", "all"}:
        smoke()
    if args.command in {"train", "all"}:
        train_pair()
    if args.command == "diagnose-blocked":
        diagnose_blocked_gate()


if __name__ == "__main__":
    main()
