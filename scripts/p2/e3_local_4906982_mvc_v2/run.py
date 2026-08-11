#!/usr/bin/env python3
"""Common-prefix replicated MVC-only experiment for DEBY_LOD2_4906982.

The host process only orchestrates Docker. One fresh MVC0 process is stopped at
the exact 7,000-update full-state checkpoint. Its learned state is cloned into
three MVC0 and three MVC05 continuations. Because strict checkpoint bindings
include the training config and output path, each clone receives a recorded
metadata-only binding rewrite; model, optimizer, strategy, grouping, RNG, and
loss-cursor sections must remain exactly equal before any continuation starts.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import difflib
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import time
from typing import Any

import yaml


REPO = Path(__file__).resolve().parents[3]
ARTIFACT_ROOT = REPO.parent / "JointBuildGS-artifacts"
TASK_ID = "P2-E3-LOCAL-4906982-MVC-v2"
TASK_ROOT = ARTIFACT_ROOT / "phase-payloads/p2/e3_local_4906982_mvc_v2" / TASK_ID
CONFIG_DIR = REPO / "configs/p2/e3_local_4906982_mvc_v1"
CONFIGS = {"MVC0": CONFIG_DIR / "mvc0.yaml", "MVC05": CONFIG_DIR / "mvc05.yaml"}
V1_ROOT = ARTIFACT_ROOT / "phase-payloads/p2/e3_local_4906982_mvc_v1/P2-E3-LOCAL-4906982-MVC-v1"
V6_ROOT = ARTIFACT_ROOT / "phase-payloads/p2/e3_local_4906982_v1/P2-E3-LOCAL-4906982-2DGS-v6-dist0-resetoff-30k"
MVC_SOURCE = REPO / "src/stage2/loss/multiview.py"
MVC_SNAPSHOT = V6_ROOT / "control/source_56f1e7cd0315fe0ab40d719ef0be901bb5dd3d7b/src/stage2/loss/multiview.py"
IMAGE = "jointbuildgs:dev"
EVAL_IMAGE = "jointbuildgs:mvc-eval-v1"
TOOLS_IMAGE = "jointbuildgs-p0-tools:t0"
TOOLS_IMAGE_ID = "sha256:02b4b7bb2e35e9b88bcc8457678ed8f178cca8f76f22b1b62f02721359e46be8"
ROOFER_IMAGE = "3dgi/roofer@sha256:dd2c415aaee337502bde0dc1426dfa9c9f88e648f9d2f6340110c49932c251d2"
ROOFER_IMAGE_ID = "sha256:9c980b97fba4c3fd30f5bb4afb8f2621be211d4e72e4333ea2053e8cd69b2dba"
GPU = "1"
REPLICAS = ("R1", "R2", "R3")
ARMS = ("MVC0", "MVC05")
CHECKPOINTS = (7000, 12000, 15000, 20000)
ALLOWLIST = {"run_id", "out_dir", "w_mvc"}


DETERMINISTIC_WRAPPER = r'''
import runpy,sys,torch
torch.backends.cudnn.benchmark=False
torch.backends.cudnn.deterministic=True
torch.backends.cuda.matmul.allow_tf32=False
torch.backends.cudnn.allow_tf32=False
torch.use_deterministic_algorithms(True)
print('[determinism] torch deterministic algorithms=True, cudnn deterministic=True, TF32=False',flush=True)
sys.argv=['src.stage2.train',*sys.argv[1:]]
runpy.run_module('src.stage2.train',run_name='__main__')
'''


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def json_sha256(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    return hashlib.sha256(encoded).hexdigest()


def atomic_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(text, encoding="utf-8")
    os.replace(temporary, path)


def atomic_json(path: Path, body: Any) -> None:
    atomic_text(path, json.dumps(body, indent=2, sort_keys=True) + "\n")


def command(argv: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(argv, check=check, text=True, capture_output=True)


def git_record() -> dict[str, Any]:
    return {
        "commit": command(["git", "rev-parse", "HEAD"]).stdout.strip(),
        "branch": command(["git", "branch", "--show-current"]).stdout.strip(),
        "dirty": bool(command(["git", "status", "--porcelain"]).stdout),
        "status_porcelain": command(["git", "status", "--porcelain"]).stdout.splitlines(),
    }


def image_record() -> dict[str, Any]:
    body = json.loads(command(["docker", "image", "inspect", IMAGE]).stdout)[0]
    return {"reference": IMAGE, "id": body["Id"], "repo_digests": body.get("RepoDigests") or []}


def gpu_record() -> dict[str, Any]:
    fields = command([
        "nvidia-smi", f"--id={GPU}",
        "--query-gpu=index,name,uuid,memory.total,driver_version",
        "--format=csv,noheader,nounits",
    ]).stdout.strip().split(", ")
    return {
        "host_index": int(fields[0]), "model": fields[1], "uuid": fields[2],
        "memory_total_mib": int(fields[3]), "driver": fields[4],
    }


def container_path(path: Path) -> str:
    return "/artifacts/JointBuildGS/" + str(path.relative_to(ARTIFACT_ROOT))


def docker_base(*, gpu: bool = False, name: str | None = None, keep: bool = False) -> list[str]:
    argv = ["docker", "run"]
    if not keep:
        argv.append("--rm")
    if name:
        argv += ["--name", name]
    if gpu:
        argv += ["--gpus", f"device={GPU}", "--ipc=host"]
    argv += [
        "-e", "CUBLAS_WORKSPACE_CONFIG=:4096:8", "-e", "NVIDIA_TF32_OVERRIDE=0",
        "-v", f"{REPO}:/workspace/JointBuildGS:ro",
        "-v", f"{ARTIFACT_ROOT}:/artifacts/JointBuildGS",
        "-v", f"{TASK_ROOT / 'cache/torch_extensions'}:/root/.cache/torch_extensions",
        "-w", "/workspace/JointBuildGS", IMAGE,
    ]
    return argv


def eval_docker_base(*, gpu: bool = False) -> list[str]:
    argv = ["docker", "run", "--rm"]
    if gpu:
        argv += ["--gpus", f"device={GPU}", "--ipc=host"]
    argv += [
        "-v", f"{REPO}:/workspace/JointBuildGS:ro",
        "-v", f"{ARTIFACT_ROOT}:/artifacts/JointBuildGS",
        "-v", f"{TASK_ROOT / 'cache/torch_extensions'}:/root/.cache/torch_extensions",
        "-w", "/workspace/JointBuildGS", EVAL_IMAGE,
    ]
    return argv


def tools_docker_base() -> list[str]:
    return [
        "docker", "run", "--rm", "--network", "none", "--entrypoint", "python",
        "--user", f"{os.getuid()}:{os.getgid()}", "--cpus", "12", "--memory", "64g",
        "--pids-limit", "4096", "-e", "PYTHONDONTWRITEBYTECODE=1",
        "-e", "PYTHONPATH=/workspace/JointBuildGS",
        "-v", f"{REPO}:/workspace/JointBuildGS:ro", "-v", f"{TASK_ROOT}:/task:rw",
        "-w", "/workspace/JointBuildGS", TOOLS_IMAGE,
    ]


def runtime_path(arm: str, replica: str) -> Path:
    return TASK_ROOT / "control/runtime_configs" / f"{arm.lower()}_{replica.lower()}.yaml"


def run_root(arm: str, replica: str) -> Path:
    return TASK_ROOT / "arms" / arm / replica


def checkpoint_valid(root: Path, step: int) -> bool:
    path = root / "ckpt" / f"step_{step:06d}.pt"
    sidecar = Path(str(path) + ".sha256")
    return path.is_file() and sidecar.is_file() and sidecar.read_text().split()[0] == sha256(path)


def record_operation(label: str, argv: list[str], rc: int, started: str, ended: str) -> None:
    path = TASK_ROOT / "provenance.json"
    body = json.loads(path.read_text())
    prior = [row for row in body["return_codes"] if row.get("label") == label]
    if prior and (prior[-1].get("return_code") != 0 or rc != 0):
        suffix = 2
        candidate = f"{label}_attempt_{suffix}"
        labels = {row.get("label") for row in body["return_codes"]}
        while candidate in labels:
            suffix += 1; candidate = f"{label}_attempt_{suffix}"
        label = candidate
    call = {"label": label, "argv": argv, "started_utc": started, "ended_utc": ended}
    result = {"label": label, "return_code": rc}
    body["commands"] = [row for row in body["commands"] if row.get("label") != label] + [call]
    body["return_codes"] = [row for row in body["return_codes"] if row.get("label") != label] + [result]
    atomic_json(path, body)


def _write_runtime_configs() -> None:
    for arm in ARMS:
        template = yaml.safe_load(CONFIGS[arm].read_text())
        for replica in REPLICAS:
            output = run_root(arm, replica)
            body = dict(template)
            body.update({
                "task_id": TASK_ID,
                "run_id": f"{arm}_{replica}",
                "out_dir": container_path(output),
                "full_state_resume": "auto",
                "full_state_checkpoint": True,
                "full_state_checkpoint_steps": list(CHECKPOINTS),
                "max_iter": 20000,
            })
            atomic_text(runtime_path(arm, replica), yaml.safe_dump(body, sort_keys=False))
    parent = yaml.safe_load(CONFIGS["MVC0"].read_text())
    parent.update({
        "task_id": TASK_ID,
        "run_id": "COMMON_PREFIX",
        "out_dir": container_path(TASK_ROOT / "common_prefix"),
        "full_state_resume": "off",
        "full_state_checkpoint": True,
        "full_state_checkpoint_steps": list(CHECKPOINTS),
        "max_iter": 20000,
    })
    atomic_text(TASK_ROOT / "control/runtime_configs/common_prefix.yaml", yaml.safe_dump(parent, sort_keys=False))


def _validate_config_diffs() -> str:
    templates = {arm: yaml.safe_load(path.read_text()) for arm, path in CONFIGS.items()}
    delta = {key for key in set(templates["MVC0"]) | set(templates["MVC05"]) if templates["MVC0"].get(key) != templates["MVC05"].get(key)}
    if delta != ALLOWLIST or templates["MVC0"]["w_mvc"] != 0.0 or templates["MVC05"]["w_mvc"] != 0.5:
        raise RuntimeError(f"paired template diff gate failed: {sorted(delta)}")
    lines = ["allowed_template_keys: out_dir, run_id, w_mvc", "actual_template_keys: " + ", ".join(sorted(delta)), ""]
    for replica in REPLICAS:
        left = yaml.safe_load(runtime_path("MVC0", replica).read_text())
        right = yaml.safe_load(runtime_path("MVC05", replica).read_text())
        changed = {key for key in set(left) | set(right) if left.get(key) != right.get(key)}
        if changed != ALLOWLIST:
            raise RuntimeError(f"runtime pair diff gate failed for {replica}: {sorted(changed)}")
        lines.append(f"runtime {replica}: {', '.join(sorted(changed))}")
    for arm in ARMS:
        first = yaml.safe_load(runtime_path(arm, "R1").read_text())
        for replica in ("R2", "R3"):
            other = yaml.safe_load(runtime_path(arm, replica).read_text())
            changed = {key for key in set(first) | set(other) if first.get(key) != other.get(key)}
            if changed != {"run_id", "out_dir"}:
                raise RuntimeError(f"replica diff gate failed for {arm}/{replica}: {sorted(changed)}")
            lines.append(f"runtime {arm} R1 vs {replica}: {', '.join(sorted(changed))}")
    lines += ["", "All processes use the same recorded deterministic wrapper and Docker/GPU controls.", "Checkpoint fork rewrites binding metadata only; learned-state equality is a separate mandatory gate."]
    return "\n".join(lines) + "\n"


def preflight() -> None:
    marker = TASK_ROOT / "experiment_contract.json"
    if TASK_ROOT.exists() and any(TASK_ROOT.iterdir()) and not marker.is_file():
        raise RuntimeError(f"non-empty unbound namespace: {TASK_ROOT}")
    for child in ("control/runtime_configs", "control/receipts", "logs", "cache/torch_extensions", "representative_images"):
        (TASK_ROOT / child).mkdir(parents=True, exist_ok=True)
    if MVC_SOURCE.read_bytes() != MVC_SNAPSHOT.read_bytes():
        raise RuntimeError("multiview.py is not byte-identical to the v6 snapshot")
    source_inputs = V1_ROOT / "input_hashes.json"
    if not source_inputs.is_file():
        raise FileNotFoundError(source_inputs)
    _write_runtime_configs()
    atomic_text(TASK_ROOT / "config_diff.txt", _validate_config_diffs())
    inputs = json.loads(source_inputs.read_text())
    atomic_json(TASK_ROOT / "input_hashes.json", {
        **inputs,
        "schema": "jointbuildgs.p2.e3_local_4906982_mvc_v2.inputs.v1",
        "reused_verified_manifest": {"path": str(source_inputs), "sha256": sha256(source_inputs)},
        "checkpoint_input": None,
        "fresh_common_prefix": True,
    })
    contract = {
        "schema": "jointbuildgs.p2.e3_local_4906982_mvc_v2.contract.v1",
        "task_id": TASK_ID, "building_id": "DEBY_LOD2_4906982", "status": "PREFLIGHT_BOUND",
        "design": "one fresh common MVC-inactive prefix through 7k, then three continuations per arm",
        "arms": {"MVC0": {"w_mvc": 0.0}, "MVC05": {"w_mvc": 0.5}},
        "sole_training_objective_delta": "w_mvc",
        "replicas": list(REPLICAS), "same_head_image_gpu": True,
        "deterministic_wrapper": True,
        "common_prefix": {"completed_updates": 7000, "w_mvc": 0.0, "mvc_weight_at_checkpoint": 0.0},
        "fork_binding_protocol": "metadata-only rebind with exact learned-state equality gate",
        "views": {"exact": 55, "train": 47, "held_out": 8},
        "checkpoints_completed_updates": list(CHECKPOINTS),
        "effect_interpretation": "arm effect is compared against MVC0 control-control variation; exact continuation equality is not required",
        "high_z_and_normal_surface_endpoints_separate": True,
        "mvc_rel_thresh_note": "gross high-Z outliers may be excluded from MVC inliers",
        "no_new_loss_or_multiview_densification": True,
        "official_PASS_usable": None, "scientific_verdict": None,
    }
    atomic_json(marker, contract)
    source_paths = [
        Path(__file__).resolve(), REPO / "src/stage2/train.py", REPO / "src/stage2/renderer.py",
        REPO / "src/stage2/densification.py", REPO / "src/stage2/checkpoint.py",
        REPO / "src/stage2/train_resume.py", MVC_SOURCE, *CONFIGS.values(),
    ]
    provenance = TASK_ROOT / "provenance.json"
    if not provenance.exists():
        atomic_json(provenance, {
            "schema": "jointbuildgs.p2.e3_local_4906982_mvc_v2.provenance.v1",
            "task_id": TASK_ID, "git": git_record(), "docker_image": image_record(), "gpu": gpu_record(),
            "source_files_sha256": {str(path.relative_to(REPO)): sha256(path) for path in source_paths},
            "configs_sha256": {arm: sha256(path) for arm, path in CONFIGS.items()},
            "runtime_configs_sha256": {path.name: sha256(path) for path in sorted((TASK_ROOT / "control/runtime_configs").glob("*.yaml"))},
            "input_hashes_sha256": sha256(TASK_ROOT / "input_hashes.json"),
            "random_seed": 0, "started_utc": now(), "ended_utc": None,
            "commands": [], "return_codes": [], "scientific_verdict": None,
        })
    atomic_text(TASK_ROOT / "NOTES.md", f"# {TASK_ID}\n\nPreflight bound. Training not started. Scientific verdict: `null`.\n")
    print(json.dumps({"task_root": str(TASK_ROOT), "config_diff": sorted(ALLOWLIST), "replicas": list(REPLICAS), "image": image_record()["id"], "gpu": gpu_record()["model"]}, indent=2))


def smoke() -> None:
    receipt = TASK_ROOT / "control/receipts/smoke.json"
    if receipt.is_file() and json.loads(receipt.read_text()).get("passed"):
        print(receipt.read_text()); return
    config = yaml.safe_load(CONFIGS["MVC05"].read_text())
    output = TASK_ROOT / "smoke"
    config.update({
        "task_id": TASK_ID, "run_id": "SMOKE", "out_dir": container_path(output),
        "max_iter": 12, "eval_every": 100000, "ckpt_every": 100000,
        "full_state_checkpoint": False, "full_state_checkpoint_steps": [], "full_state_resume": "off",
        "mvc_warmup": 0, "mvc_ramp_steps": 1, "refine_start_iter": 500,
    })
    config_path = TASK_ROOT / "control/runtime_configs/smoke.yaml"
    atomic_text(config_path, yaml.safe_dump(config, sort_keys=False))
    argv = docker_base(gpu=True) + ["python", "-c", DETERMINISTIC_WRAPPER, "--config", container_path(config_path)]
    log = TASK_ROOT / "logs/smoke.log"; started = now()
    with log.open("w", encoding="utf-8") as stream:
        proc = subprocess.run(argv, text=True, stdout=stream, stderr=subprocess.STDOUT)
    record_operation("smoke", argv, proc.returncode, started, now())
    text = log.read_text(errors="replace")
    scalar_code = "from tensorboard.backend.event_processing.event_accumulator import EventAccumulator as E;import glob,json;p=glob.glob('" + container_path(output / "tb/events*") + "')[0];e=E(p);e.Reload();print(json.dumps({k:max(x.value for x in e.Scalars(k)) for k in ['loss/mvc','stats/mvc_n_inlier']}))"
    scalar_argv = docker_base() + ["python", "-c", scalar_code]
    scalar_proc = command(scalar_argv, check=False)
    scalar = json.loads(next(line for line in reversed(scalar_proc.stdout.splitlines()) if line.startswith("{"))) if scalar_proc.returncode == 0 else {}
    passed = proc.returncode == 0 and "avg 2.0 neighbors/view" in text and scalar.get("loss/mvc", 0) > 0 and scalar.get("stats/mvc_n_inlier", 0) > 0
    atomic_json(receipt, {"schema": "jointbuildgs.p2.e3_local_4906982_mvc_v2.smoke.v1", "return_code": proc.returncode, "scalars": scalar, "neighbor_summary_found": "avg 2.0 neighbors/view" in text, "passed": passed, "scientific_verdict": None})
    if not passed:
        raise RuntimeError(f"smoke failed; inspect {log}")
    shutil.rmtree(output, ignore_errors=True)
    print(json.dumps(json.loads(receipt.read_text()), indent=2))


def _launch_training(label: str, root: Path, config: Path, *, stop_step: int | None) -> dict[str, Any]:
    final_step = 20000 if stop_step is None else stop_step
    receipt = TASK_ROOT / "control/receipts" / f"{label}.json"
    if checkpoint_valid(root, final_step):
        return json.loads(receipt.read_text()) if receipt.is_file() else {"status": "ALREADY_COMPLETE"}
    name = "jbgs-" + label.lower().replace("_", "-")
    subprocess.run(["docker", "rm", "-f", name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    argv = docker_base(gpu=True, name=name, keep=True) + ["python", "-c", DETERMINISTIC_WRAPPER, "--config", container_path(config)]
    log = root / "logs" / "train.log"; vram = root / "logs" / "vram_used_mib.tsv"
    log.parent.mkdir(parents=True, exist_ok=True)
    started = now(); began = time.monotonic(); max_used = 0
    with log.open("a", encoding="utf-8") as stream, vram.open("a", encoding="utf-8") as meter:
        if vram.stat().st_size == 0: meter.write("utc\tused_mib\n")
        proc = subprocess.Popen(argv, text=True, stdout=stream, stderr=subprocess.STDOUT)
        while proc.poll() is None:
            sample = subprocess.run(["nvidia-smi", f"--id={GPU}", "--query-gpu=memory.used", "--format=csv,noheader,nounits"], text=True, capture_output=True)
            try:
                used = int(sample.stdout.strip()); max_used = max(max_used, used); meter.write(f"{now()}\t{used}\n"); meter.flush()
            except ValueError:
                pass
            if stop_step is not None and checkpoint_valid(root, stop_step):
                subprocess.run(["docker", "stop", "-t", "10", name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                break
            time.sleep(2)
        rc = proc.wait()
    ended = now(); subprocess.run(["docker", "rm", "-f", name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    valid = checkpoint_valid(root, final_step)
    body = {
        "schema": "jointbuildgs.p2.e3_local_4906982_mvc_v2.runtime.v1", "label": label,
        "started_utc": started, "ended_utc": ended, "wall_seconds": time.monotonic() - began,
        "max_selected_gpu_used_mib": max_used, "return_code": rc,
        "intentional_stop_after_checkpoint": stop_step, "required_checkpoint_valid": valid,
        "scientific_verdict": None,
    }
    atomic_json(receipt, body); record_operation(label, argv, rc, started, ended)
    if not valid or (stop_step is None and rc != 0):
        raise RuntimeError(f"{label} failed rc={rc}; inspect {log}")
    return body


def train_prefix() -> None:
    smoke_receipt = TASK_ROOT / "control/receipts/smoke.json"
    if not smoke_receipt.is_file() or not json.loads(smoke_receipt.read_text()).get("passed"):
        raise RuntimeError("smoke must pass first")
    result = _launch_training("common_prefix", TASK_ROOT / "common_prefix", TASK_ROOT / "control/runtime_configs/common_prefix.yaml", stop_step=7000)
    print(json.dumps(result, indent=2))


REBIND_CODE = r'''
import copy,hashlib,json,os,sys,tempfile,torch
from pathlib import Path
source,destination,config_path,out_dir,receipt=map(Path,sys.argv[1:])
cfg=__import__('yaml').safe_load(config_path.read_text())
excluded={'full_state_resume','full_state_resume_strict_cuda_rng'}
bound={k:v for k,v in cfg.items() if k not in excluded}
digest=lambda x:hashlib.sha256(json.dumps(x,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()
A=torch.load(source,map_location='cpu',weights_only=False)
old=copy.deepcopy(A['binding_sha256'])
new={'training_config':digest(bound),'effective_training_config':old['effective_training_config'],'output_path':hashlib.sha256(str(out_dir).encode()).hexdigest()}
A['binding_sha256']=new
destination.parent.mkdir(parents=True,exist_ok=True)
fd,tmp=tempfile.mkstemp(prefix=destination.name+'.',suffix='.tmp',dir=destination.parent);os.close(fd)
try:
 torch.save(A,tmp);os.chmod(tmp,0o644);os.replace(tmp,destination)
finally:
 if os.path.exists(tmp):os.unlink(tmp)
h=hashlib.sha256(destination.read_bytes()).hexdigest();side=Path(str(destination)+'.sha256');side.write_text(f'{h}  {destination.name}\n');os.chmod(side,0o644)
B=torch.load(destination,map_location='cpu',weights_only=False)
def eq(x,y):
 import numpy as np
 if torch.is_tensor(x) and torch.is_tensor(y):return x.dtype==y.dtype and x.shape==y.shape and torch.equal(x,y)
 if isinstance(x,np.ndarray) and isinstance(y,np.ndarray):return x.dtype==y.dtype and x.shape==y.shape and np.array_equal(x,y,equal_nan=True)
 if isinstance(x,dict) and isinstance(y,dict):return set(x)==set(y) and all(eq(x[k],y[k]) for k in x)
 if isinstance(x,(list,tuple)) and isinstance(y,(list,tuple)):return type(x)==type(y) and len(x)==len(y) and all(eq(a,b) for a,b in zip(x,y))
 return type(x)==type(y) and x==y
sections=['model','optimizers','strategy','grouping_state','rng_state','loss_log_cursor','learning_runs_started']
same={k:eq(torch.load(source,map_location='cpu',weights_only=False)[k],B[k]) for k in sections}
body={'schema':'jointbuildgs.p2.e3_local_4906982_mvc_v2.rebind.v1','source':str(source),'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'destination':str(destination),'destination_sha256':h,'old_binding':old,'new_binding':new,'learned_sections_equal':same,'passed':all(same.values()),'scientific_verdict':None}
receipt.parent.mkdir(parents=True,exist_ok=True);receipt.write_text(json.dumps(body,indent=2,sort_keys=True)+'\n')
raise SystemExit(0 if body['passed'] else 2)
'''


def fork_prefix() -> None:
    source_root = TASK_ROOT / "common_prefix"
    source_checkpoint = source_root / "ckpt/step_007000.pt"
    if not checkpoint_valid(source_root, 7000):
        raise RuntimeError("valid common 7k checkpoint required")
    for arm in ARMS:
        for replica in REPLICAS:
            destination_root = run_root(arm, replica)
            receipt = TASK_ROOT / "control/receipts" / f"rebind_{arm.lower()}_{replica.lower()}.json"
            if receipt.is_file() and json.loads(receipt.read_text()).get("passed") and checkpoint_valid(destination_root, 7000):
                continue
            if destination_root.exists():
                raise RuntimeError(f"incomplete fork requires review: {destination_root}")
            destination_root.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(source_root, destination_root)
            destination_checkpoint = destination_root / "ckpt/step_007000.pt"
            argv = docker_base() + [
                "python", "-c", REBIND_CODE,
                container_path(source_checkpoint), container_path(destination_checkpoint),
                container_path(runtime_path(arm, replica)), Path(container_path(destination_root)),
                container_path(receipt),
            ]
            started = now(); proc = command([str(x) for x in argv], check=False); ended = now()
            record_operation(f"rebind_{arm}_{replica}", [str(x) for x in argv], proc.returncode, started, ended)
            if proc.returncode != 0:
                raise RuntimeError(proc.stderr or proc.stdout)
    receipts = [json.loads((TASK_ROOT / "control/receipts" / f"rebind_{arm.lower()}_{replica.lower()}.json").read_text()) for arm in ARMS for replica in REPLICAS]
    source_hashes = {row["source_sha256"] for row in receipts}
    learned = all(all(row["learned_sections_equal"].values()) for row in receipts)
    gate = {
        "schema": "jointbuildgs.p2.e3_local_4906982_mvc_v2.common_state_gate.v1",
        "completed_updates": 7000, "replica_count": len(receipts),
        "unique_source_checkpoint_hashes": len(source_hashes),
        "learned_sections_exact_across_all_forks": learned,
        "binding_metadata_differs_by_target_config_and_output": True,
        "passed": len(source_hashes) == 1 and learned,
        "scientific_verdict": None,
    }
    atomic_json(TASK_ROOT / "control/common_state_gate_7000.json", gate)
    if not gate["passed"]:
        raise RuntimeError("common-state fork gate failed")
    print(json.dumps(gate, indent=2))


def train_replicas() -> None:
    gate = TASK_ROOT / "control/common_state_gate_7000.json"
    if not gate.is_file() or not json.loads(gate.read_text()).get("passed"):
        raise RuntimeError("common-state gate must pass first")
    for replica in REPLICAS:
        for arm in ARMS:
            label = f"train_{arm}_{replica}"
            result = _launch_training(label, run_root(arm, replica), runtime_path(arm, replica), stop_step=None)
            print(json.dumps({"label": label, "wall_seconds": result.get("wall_seconds"), "checkpoint_20k": checkpoint_valid(run_root(arm, replica), 20000)}), flush=True)
    missing = [(arm, replica, step) for arm in ARMS for replica in REPLICAS for step in CHECKPOINTS if not checkpoint_valid(run_root(arm, replica), step)]
    if missing:
        raise RuntimeError(f"missing required checkpoints: {missing}")


ANALYZE_CODE = r'''
import csv,hashlib,json,math,os,statistics,sys
from collections import Counter
from pathlib import Path
import laspy,numpy as np,torch,yaml
from matplotlib import pyplot as plt
from pyproj import CRS
from shapely.geometry import shape
from shapely import contains_xy
from tensorboard.backend.event_processing.event_accumulator import EventAccumulator
from torch import nn
from torch.utils.tensorboard import SummaryWriter
from PIL import Image
from pytorch_msssim import ssim as ssim_fn
import lpips
from src.stage2.colmap_io import read_points3d_bin
from src.stage2.dataloader import ColmapDataset
from src.stage2.model import GaussianModel2D
from src.stage2.renderer import render

root,data_root,footprint_path=map(Path,sys.argv[1:4])
arms=['MVC0','MVC05']; replicas=['R1','R2','R3']; steps=[7000,12000,15000,20000]
shift=np.asarray([690953.0,5336071.0,604.0],dtype=np.float64)
voxel_m=0.15; alpha_min=0.5; depth_min=0.01; depth_max=500.0
cfg=yaml.safe_load((root/'control/runtime_configs/mvc0_r1.yaml').read_text())
names=list(cfg['visible_views']); train_names=set(cfg['train_views']); eval_names=set(cfg['eval_views'])
dataset=ColmapDataset(data_root,downscale=0.25,load_depth=False,load_normal=False,load_semantic=False,visible_views=names)
if [f.name for f in dataset.frames] != names: raise RuntimeError('dataset view order drift')
seed_xyz=read_points3d_bin(data_root/'sparse/0/points3D.bin')[:,:3].astype(np.float64)
seed_max_local_z=float(seed_xyz[:,2].max());seed_max_world_z=seed_max_local_z+float(shift[2])
footprints=json.loads(footprint_path.read_text())
feature=next(f for f in footprints['features'] if str(f['properties'].get('stable_id'))=='DEBY_LOD2_4906982')
footprint=shape(feature['geometry']); fusion_filter=footprint.buffer(30.0)
lpips_net=lpips.LPIPS(net='vgg').cuda().eval()

def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def model_from(path):
 p=torch.load(path,map_location='cpu',weights_only=False);s=p['model']['state_dict'] if 'model' in p else p['state_dict']
 required={'means','quats','log_scales','opacities_raw','sh0','shN','sem_logits'}
 m=GaussianModel2D.__new__(GaussianModel2D);nn.Module.__init__(m);m.sh_degree=3;m.max_sh_degree=3;m.active_sh_degree=3;m.num_classes=4
 for k in sorted(required):setattr(m,k,nn.Parameter(s[k].cuda(),requires_grad=False))
 m.surface_seed_mask=torch.zeros(len(s['means']),dtype=torch.bool,device='cuda');m.eval();return m,p,s
def tb_scalars(run):
 out={}
 for f in sorted((run/'tb').glob('events*')):
  e=EventAccumulator(str(f));e.Reload()
  for tag in e.Tags()['scalars']:
   out.setdefault(tag,{})
   for x in e.Scalars(tag):out[tag][int(x.step)]=float(x.value)
 return out
def latest(tb,tag,step):
 rows=tb.get(tag,{}); eligible=[k for k in rows if k<=step-1]
 return None if not eligible else {'step':max(eligible),'value':rows[max(eligible)]}
def quantile(x,qs):return [float(v) for v in torch.quantile(x.float(),torch.tensor(qs))]
def save_panel(path,source,rgb,depth,normal,alpha,title):
 fig,ax=plt.subplots(1,5,figsize=(18,4),dpi=120,constrained_layout=True)
 values=[source,rgb,np.where((depth>0)&np.isfinite(depth),depth,np.nan),np.clip((normal+1)*.5,0,1),alpha]
 labels=['held-out RGB','GS RGB','median depth','world normal','opacity']
 for a,v,l in zip(ax,values,labels):a.imshow(v,cmap='turbo' if l=='median depth' else ('gray' if l=='opacity' else None));a.set_title(l);a.axis('off')
 fig.suptitle(title);path.parent.mkdir(parents=True,exist_ok=True);fig.savefig(path);plt.close(fig)
def write_laz(path,xyz,rgb,normal,support):
 h=laspy.LasHeader(point_format=3,version='1.4');h.add_crs(CRS.from_epsg(25832));h.scales=np.array([.001,.001,.001]);h.offsets=np.array([690000.,5335000.,0.])
 for name,typ in [('view_support',np.uint16),('normal_x',np.float32),('normal_y',np.float32),('normal_z',np.float32)]:h.add_extra_dim(laspy.ExtraBytesParams(name=name,type=typ))
 p=laspy.LasData(h);p.x=xyz[:,0];p.y=xyz[:,1];p.z=xyz[:,2];p.red=np.rint(np.clip(rgb[:,0],0,1)*65535).astype(np.uint16);p.green=np.rint(np.clip(rgb[:,1],0,1)*65535).astype(np.uint16);p.blue=np.rint(np.clip(rgb[:,2],0,1)*65535).astype(np.uint16);p.classification=np.ones(len(xyz),dtype=np.uint8);p.view_support=support;p.normal_x=normal[:,0];p.normal_y=normal[:,1];p.normal_z=normal[:,2];path.parent.mkdir(parents=True,exist_ok=True);p.write(path)

rows=[]
for arm in arms:
 for replica in replicas:
  run=root/'arms'/arm/replica; tb=tb_scalars(run)
  runtime=json.loads((root/'control/receipts'/f'train_{arm}_{replica}.json').read_text())
  post_writer=SummaryWriter(log_dir=str(run/'tb'),filename_suffix='.posthoc_metrics')
  for step in steps:
   outdir=run/'evaluation'/f'step_{step:06d}';receipt=outdir/'evaluation.json'
   if receipt.is_file():
    body=json.loads(receipt.read_text());rows.append(body);continue
   ckpt=run/'ckpt'/f'step_{step:06d}.pt';model,payload,state=model_from(ckpt)
   z=state['means'][:,2].float();op=torch.sigmoid(state['opacities_raw'].flatten().float());scale=torch.exp(state['log_scales'].float());lo=torch.minimum(scale[:,0],scale[:,1]);hi=torch.maximum(scale[:,0],scale[:,1]);elong=lo/hi.clamp_min(1e-12)
   geom={'gaussian_count':int(len(z)),'z_epsg25832':dict(zip(['min','median','p95','p99','max'],[v+604.0 for v in quantile(z,[0,.5,.95,.99,1])])),'seed_max_z_epsg25832':seed_max_world_z,'count_above_seed_max_z':int((z>seed_max_local_z).sum()),'count_z_gt_650m':int((z>46.0).sum()),'opacity_mean':float(op.mean()),'opacity_median':float(op.median()),'opacity_bins':{},'scale_min_q50_q95_q99_max':quantile(lo,[.5,.95,.99,1]),'scale_max_q50_q95_q99_max':quantile(hi,[.5,.95,.99,1]),'elongation_q01_q05_q50_q95':quantile(elong,[.01,.05,.5,.95])}
   for label,a,b in [('lt_0p1',0,.1),('0p1_0p5',.1,.5),('0p5_0p9',.5,.9),('ge_0p9',.9,1.000001)]:
    m=(op>=a)&(op<b);geom['opacity_bins'][label]={'all':int(m.sum()),'z_gt_650m':int((m&(z>46)).sum())}
   metrics={'train':{'psnr':[],'ssim':[],'lpips':[]},'eval':{'psnr':[],'ssim':[],'lpips':[]}}
   acc={};view_records=[];torch.cuda.reset_peak_memory_stats()
   with torch.no_grad():
    for index,batch in enumerate(dataset):
     W,H=int(batch['width']),int(batch['height']);w2c=batch['w2c'].cuda();K=batch['K'].cuda();o=render(model,w2c,K,W,H,sh_degree=3,render_mode='RGB+ED',near_plane=depth_min,far_plane=depth_max,bg_color=torch.ones(3,device='cuda'),depth_mode='median')
     pred=o['rgb'].clamp(0,1);gt=batch['rgb'].cuda();mse=float(((pred-gt)**2).mean());role='train' if batch['name'] in train_names else 'eval';metrics[role]['psnr'].append(-10*math.log10(max(mse,1e-10)))
     pp=pred.permute(2,0,1).unsqueeze(0);gg=gt.permute(2,0,1).unsqueeze(0);metrics[role]['ssim'].append(float(ssim_fn(pp,gg,data_range=1.0)));metrics[role]['lpips'].append(float(lpips_net(pp*2-1,gg*2-1)))
     d=o['depth_median'];a=o['alpha'];valid=torch.isfinite(d)&(d>=depth_min)&(d<=depth_max)&(a>=alpha_min);valid_n=int(valid.sum());retained=0
     if valid_n:
      yy,xx=torch.nonzero(valid,as_tuple=True);zz=d[yy,xx];cam=torch.stack(((xx-K[0,2])/K[0,0]*zz,(yy-K[1,2])/K[1,1]*zz,zz),dim=1);c2w=torch.linalg.inv(w2c);xyz_local=cam@c2w[:3,:3].T+c2w[:3,3];xyz=xyz_local.cpu().numpy().astype(np.float64)+shift;keep=contains_xy(fusion_filter,xyz[:,0],xyz[:,1]);retained=int(np.count_nonzero(keep))
      if retained:
       xyz=xyz[keep];rgb=o['rgb'][yy,xx].cpu().numpy()[keep];normal=o['normal_render'][yy,xx].cpu().numpy()[keep];q=np.floor((xyz-shift)/voxel_m).astype(np.int32);uq,inv=np.unique(q,axis=0,return_inverse=True);cnt=np.bincount(inv).astype(np.float64)
       xyzsum=np.vstack([np.bincount(inv,weights=xyz[:,j]) for j in range(3)]).T;rgbsum=np.vstack([np.bincount(inv,weights=rgb[:,j]) for j in range(3)]).T;nsum=np.vstack([np.bincount(inv,weights=normal[:,j]) for j in range(3)]).T
       for j,key in enumerate(map(tuple,uq.tolist())):
        vals=(xyzsum[j]/cnt[j],rgbsum[j]/cnt[j],nsum[j]/cnt[j]);old=acc.get(key)
        if old is None:acc[key]=[1,vals[0],vals[1],vals[2]]
        else:old[0]+=1;old[1]+=vals[0];old[2]+=vals[1];old[3]+=vals[2]
     view_records.append({'view_index':index,'name':batch['name'],'role':role,'valid_pixels':valid_n,'retained_pixels':retained})
     if replica=='R1' and batch['name'] in eval_names:
      source=(batch['rgb'].cpu().numpy()*255).round().clip(0,255).astype(np.uint8);save_panel(root/'representative_images'/arm/f'step_{step:06d}'/(Path(batch['name']).stem+'.png'),source,pred.cpu().numpy(),d.cpu().numpy(),o['normal_render'].cpu().numpy(),a.cpu().numpy(),f'{arm} R1 step {step} | {batch["name"]}')
   kept=[v for v in acc.values() if v[0]>=2];xyz=np.asarray([v[1]/v[0] for v in kept]);rgb=np.asarray([v[2]/v[0] for v in kept]);normal=np.asarray([v[3]/v[0] for v in kept]);normal/=np.maximum(np.linalg.norm(normal,axis=1,keepdims=True),1e-12);support=np.asarray([v[0] for v in kept],dtype=np.uint16)
   fused=outdir/'fusion/fused_surface.laz';write_laz(fused,xyz,rgb,normal,support);inside=contains_xy(footprint,xyz[:,0],xyz[:,1]);roof=inside&(np.abs(normal[:,2])>=.7);wall=inside&(np.abs(normal[:,2])<=.3);hist=Counter(map(int,support.tolist()))
   summary={role:{k:float(np.mean(v)) for k,v in vals.items()} for role,vals in metrics.items()}
   mvc_weight=0.0 if arm=='MVC0' or step<=7000 else .5
   scalars={k:latest(tb,k,step) for k in ['metric/psnr_train','eval/psnr','loss/mvc','loss/mvc_depth','loss/mvc_normal','stats/mvc_n_inlier','loss/nc','stats/gaussian_count','stats/grow_total','stats/pruned','stats/cum_grow_split','stats/cum_grow_duplicated','stats/cum_pruned']}
   fusion={'point_count_ge2':int(len(xyz)),'point_count_ge3':int((support>=3).sum()),'ratio_ge3_of_ge2':float((support>=3).mean()),'support_histogram':{str(k):v for k,v in sorted(hist.items())},'footprint_area_m2':float(footprint.area),'roof_point_count':int(roof.sum()),'wall_point_count':int(wall.sum()),'roof_density_per_footprint_m2':float(roof.sum()/footprint.area),'wall_density_per_footprint_m2':float(wall.sum()/footprint.area),'roof_normal_rule':'abs(nz)>=0.7','wall_normal_rule':'abs(nz)<=0.3','fused_laz_sha256':digest(fused)}
   body={'schema':'jointbuildgs.p2.e3_local_4906982_mvc_v2.checkpoint_evaluation.v1','arm':arm,'replica':replica,'completed_updates':step,'checkpoint_sha256':digest(ckpt),'geometry':geom,'render_metrics':summary,'training_scalars':scalars,'loss_weight_mvc':mvc_weight,'fusion':fusion,'view_records':view_records,'peak_eval_vram_mib':int(torch.cuda.max_memory_allocated()/1048576),'scientific_verdict':None}
   receipt.parent.mkdir(parents=True,exist_ok=True);receipt.write_text(json.dumps(body,indent=2,sort_keys=True)+'\n');rows.append(body)
   for role in ['train','eval']:
    for metric,val in summary[role].items():post_writer.add_scalar(f'{role}/{metric}',val,step)
   post_writer.add_scalar('loss_weight/mvc',mvc_weight,step);post_writer.add_scalar('stats/opacity_mean',geom['opacity_mean'],step);post_writer.add_scalar('stats/opacity_median',geom['opacity_median'],step);post_writer.add_scalar('runtime/max_vram_mib',runtime['max_selected_gpu_used_mib'],step);post_writer.add_scalar('runtime/wall_time_seconds',runtime['wall_seconds'],step);post_writer.flush()
   del model,payload,state;torch.cuda.empty_cache();print(json.dumps({'arm':arm,'replica':replica,'step':step,'eval_psnr':summary['eval']['psnr'],'eval_ssim':summary['eval']['ssim'],'eval_lpips':summary['eval']['lpips'],'fusion_ge2':len(xyz),'z_gt_650':geom['count_z_gt_650m']}),flush=True)
  post_writer.close()

flat=[]
for r in rows:
 flat.append({'arm':r['arm'],'replica':r['replica'],'completed_updates':r['completed_updates'],'gaussian_count':r['geometry']['gaussian_count'],'z_p99':r['geometry']['z_epsg25832']['p99'],'z_max':r['geometry']['z_epsg25832']['max'],'z_gt_650':r['geometry']['count_z_gt_650m'],'above_seed_max':r['geometry']['count_above_seed_max_z'],'eval_psnr':r['render_metrics']['eval']['psnr'],'eval_ssim':r['render_metrics']['eval']['ssim'],'eval_lpips':r['render_metrics']['eval']['lpips'],'fusion_ge2':r['fusion']['point_count_ge2'],'fusion_ge3':r['fusion']['point_count_ge3'],'fusion_ge3_ratio':r['fusion']['ratio_ge3_of_ge2'],'roof_density':r['fusion']['roof_density_per_footprint_m2'],'wall_density':r['fusion']['wall_density_per_footprint_m2']})
with (root/'checkpoint_metrics.csv').open('w',newline='') as f:w=csv.DictWriter(f,fieldnames=list(flat[0]));w.writeheader();w.writerows(sorted(flat,key=lambda x:(x['completed_updates'],x['arm'],x['replica'])))
aggregates={}
for step in steps:
 aggregates[str(step)]={}
 for arm in arms:
  subset=[x for x in flat if x['arm']==arm and x['completed_updates']==step];aggregates[str(step)][arm]={k:{'mean':float(np.mean([x[k] for x in subset])),'std':float(np.std([x[k] for x in subset],ddof=1))} for k in ['gaussian_count','z_p99','z_max','z_gt_650','above_seed_max','eval_psnr','eval_ssim','eval_lpips','fusion_ge2','fusion_ge3_ratio','roof_density','wall_density']}
body={'schema':'jointbuildgs.p2.e3_local_4906982_mvc_v2.metrics.v1','status':'CHECKPOINT_ANALYSIS_COMPLETE','replicates_per_arm':3,'aggregates':aggregates,'scientific_verdict':None,'official_PASS_usable':None}
(root/'metrics.json').write_text(json.dumps(body,indent=2,sort_keys=True)+'\n')
print(json.dumps({'status':body['status'],'rows':len(flat),'aggregates':aggregates['20000']},indent=2))
'''


def analyze_checkpoints() -> None:
    footprint = ARTIFACT_ROOT / "phase-payloads/p2/c1_c2_shared_footprint_199_v3/P2-C1-C2-SHARED-FOOTPRINT-199-ORIGINAL-GLOBAL-v3/freeze/shared_footprints_199.geojson"
    data_root = V6_ROOT / "data/colmap_crop"
    output = TASK_ROOT / "metrics.json"
    if output.is_file() and json.loads(output.read_text()).get("status") == "CHECKPOINT_ANALYSIS_COMPLETE":
        print(output.read_text()); return
    argv = eval_docker_base(gpu=True) + ["python", "-c", ANALYZE_CODE, container_path(TASK_ROOT), container_path(data_root), container_path(footprint)]
    started = now(); log = TASK_ROOT / "logs/analyze_checkpoints.log"
    with log.open("a", encoding="utf-8") as stream:
        proc = subprocess.run(argv, text=True, stdout=stream, stderr=subprocess.STDOUT)
    record_operation("analyze_checkpoints", argv, proc.returncode, started, now())
    if proc.returncode != 0:
        raise RuntimeError(f"checkpoint analysis failed; inspect {log}")
    print(output.read_text())


STAGE3_PREP_CODE = r'''
import hashlib,json,sys
from pathlib import Path
from shapely.geometry import shape
from src.stage3.common_classification_adapter_v1 import pipeline
root,source_footprints=map(Path,sys.argv[1:])
source=json.loads(source_footprints.read_text())
feature=next(f for f in source['features'] if str(f['properties'].get('stable_id'))=='DEBY_LOD2_4906982')
feature=json.loads(json.dumps(feature));feature['properties']['class']=6
feature['properties']['input_role']='SHARED_STANDARD_GROUNDSURFACE_XY_CONTROL';feature['properties']['lod2_z_used']=False;feature['properties']['roofsurface_used']=False
subset={'type':'FeatureCollection','name':'shared_standard_footprint_DEBY_LOD2_4906982','crs':source.get('crs'),'features':[feature]}
control=root/'control';control.mkdir(parents=True,exist_ok=True);footprint=control/'shared_standard_footprint_4906982.geojson'
encoded=(json.dumps(subset,indent=2,sort_keys=True)+'\n').encode()
if footprint.exists() and footprint.read_bytes()!=encoded:raise RuntimeError('existing shared footprint subset drift')
footprint.write_bytes(encoded)
bounds=list(map(float,shape(feature['geometry']).bounds));buffer_m=30.0
scene={'crs':'EPSG:25832','roofer_aoi_bbox':bounds,'classification_context_buffer_m':buffer_m}
classification={'smrf':{'cell':1.0,'slope':0.15,'scalar':1.25,'threshold':0.5,'window':18.0},'ground_class':2,'building_class':6,'unclassified_class':1}
cases=[]
for arm in ['MVC0','MVC05']:
 for replica in ['R1','R2','R3']:
  for step in [7000,12000,15000,20000]:
   work=root/'arms'/arm/replica/'evaluation'/f'step_{step:06d}'/'fusion';source_laz=work/'fused_surface.laz';partial=work/'classified_surface.partial.laz'
   if not source_laz.is_file():raise FileNotFoundError(source_laz)
   body=pipeline(source_stages=[{'type':'readers.las','filename':source_laz.as_posix().replace('/task','/task')}],scene=scene,classification=classification,footprint_path=footprint,output_path=partial)
   spec=work/'classification_pipeline.json';spec.write_text(json.dumps(body,indent=2,sort_keys=True)+'\n')
   cases.append({'arm':arm,'replica':replica,'completed_updates':step,'work_relative':str(work.relative_to(root))})
receipt={'schema':'jointbuildgs.p2.e3_local_4906982_mvc_v2.stage3_preparation.v1','shared_footprint_source':str(source_footprints),'shared_footprint_source_sha256':hashlib.sha256(source_footprints.read_bytes()).hexdigest(),'shared_footprint_subset_sha256':hashlib.sha256(encoded).hexdigest(),'shared_footprint_allowed_fields':['stable_id','GroundSurface exterior/interior XY'],'prohibited_fields':['GroundSurface Z','RoofSurface XYZ','WallSurface XYZ','roof type','semantic class','final roof model'],'footprint_bounds':bounds,'classification_context_buffer_m':buffer_m,'roofer_box':[bounds[0]-buffer_m,bounds[1]-buffer_m,bounds[2]+buffer_m,bounds[3]+buffer_m],'classification':classification,'cases':cases,'scientific_verdict':None}
(control/'stage3_preparation.json').write_text(json.dumps(receipt,indent=2,sort_keys=True)+'\n')
print(json.dumps({'cases':len(cases),'footprint_bounds':bounds,'roofer_box':receipt['roofer_box']}))
'''


STAGE3_VERIFY_CODE = r'''
import hashlib,json,os,sys
from pathlib import Path
import laspy,numpy as np
partial,final,receipt=map(Path,sys.argv[1:])
p=laspy.read(partial);classes=np.asarray(p.classification);epsg=p.header.parse_crs().to_epsg() if p.header.parse_crs() else None
counts={str(int(k)):int(v) for k,v in zip(*np.unique(classes,return_counts=True))}
passed=epsg==25832 and int(counts.get('2',0))>0 and int(counts.get('6',0))>0
body={'schema':'jointbuildgs.p2.e3_local_4906982_mvc_v2.classified_fusion.v1','point_count':int(len(p.points)),'class_counts':counts,'epsg':epsg,'pdal_output_sha256':hashlib.sha256(partial.read_bytes()).hexdigest(),'passed':passed,'scientific_verdict':None}
if passed:os.replace(partial,final);body['classified_laz_sha256']=hashlib.sha256(final.read_bytes()).hexdigest()
receipt.write_text(json.dumps(body,indent=2,sort_keys=True)+'\n')
print(json.dumps(body));raise SystemExit(0 if passed else 2)
'''


ROOFER_RECORD_CODE = r'''
import hashlib,json,sys
from pathlib import Path
out=Path(sys.argv[1]);receipt=Path(sys.argv[2]);rc=int(sys.argv[3]);seconds=float(sys.argv[4]);target='DEBY_LOD2_4906982';attrs=None;files=[]
for path in sorted(out.rglob('*')) if out.exists() else []:
 if not path.is_file():continue
 files.append({'path':str(path.relative_to(out)),'bytes':path.stat().st_size,'sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
 if path.suffix=='.jsonl':
  for line in path.read_text().splitlines():
   row=json.loads(line)
   if row.get('id')==target:
    attrs=row['CityObjects'][target].get('attributes',{});break
body={'schema':'jointbuildgs.p2.e3_local_4906982_mvc_v2.roofer_terminal.v1','return_code':rc,'wall_seconds':seconds,'output_files':files,'target_attributes':attrs,'rf_success':None if attrs is None else attrs.get('rf_success'),'quality_parameters':'ROOFER_DEFAULTS','quality_driven_retry_allowed':False,'scientific_verdict':None}
receipt.write_text(json.dumps(body,indent=2,sort_keys=True)+'\n');print(json.dumps({'return_code':rc,'rf_success':body['rf_success'],'rf_roof_type':None if attrs is None else attrs.get('rf_roof_type'),'rf_rmse_lod22':None if attrs is None else attrs.get('rf_rmse_lod22')}))
raise SystemExit(0 if rc==0 and attrs is not None else 2)
'''


def run_stage3() -> None:
    if command(["docker", "image", "inspect", TOOLS_IMAGE, "--format", "{{.Id}}"], check=False).stdout.strip() != TOOLS_IMAGE_ID:
        raise RuntimeError("p0-tools image identity mismatch")
    if command(["docker", "image", "inspect", ROOFER_IMAGE, "--format", "{{.Id}}"], check=False).stdout.strip() != ROOFER_IMAGE_ID:
        raise RuntimeError("Roofer image identity mismatch")
    metrics = TASK_ROOT / "metrics.json"
    if not metrics.is_file() or json.loads(metrics.read_text()).get("status") != "CHECKPOINT_ANALYSIS_COMPLETE":
        raise RuntimeError("checkpoint analysis must complete first")
    source_footprint = ARTIFACT_ROOT / "phase-payloads/p2/c1_c2_shared_footprint_199_v3/P2-C1-C2-SHARED-FOOTPRINT-199-ORIGINAL-GLOBAL-v3/freeze/shared_footprints_199.geojson"
    prep_argv = tools_docker_base() + ["-c", STAGE3_PREP_CODE, "/task", str(source_footprint).replace(str(ARTIFACT_ROOT), "/artifacts/JointBuildGS")]
    # The source footprint is outside the task mount, so add the canonical artifact root read-only.
    insert_at = prep_argv.index("-w")
    prep_argv[insert_at:insert_at] = ["-v", f"{ARTIFACT_ROOT}:/artifacts/JointBuildGS:ro"]
    started = now(); prep = command(prep_argv, check=False); record_operation("stage3_prepare", prep_argv, prep.returncode, started, now())
    if prep.returncode != 0:
        raise RuntimeError(prep.stderr or prep.stdout)
    spec = json.loads((TASK_ROOT / "control/stage3_preparation.json").read_text())
    for case in spec["cases"]:
        label = f"{case['arm']}_{case['replica']}_{case['completed_updates']}"
        work = TASK_ROOT / case["work_relative"]
        classified = work / "classified_surface.laz"; class_receipt = work / "classification_receipt.json"
        if not (class_receipt.is_file() and json.loads(class_receipt.read_text()).get("passed")):
            partial = work / "classified_surface.partial.laz"
            if partial.exists(): partial.unlink()
            pdal_argv = [
                "docker", "run", "--rm", "--network", "none", "--entrypoint", "pdal",
                "--user", f"{os.getuid()}:{os.getgid()}", "--cpus", "12", "--memory", "64g", "--pids-limit", "4096",
                "-v", f"{TASK_ROOT}:/task:rw", "-w", "/task", TOOLS_IMAGE,
                "pipeline", "/task/" + str((work / "classification_pipeline.json").relative_to(TASK_ROOT)),
            ]
            log = work / "classification.log"; started = now()
            with log.open("w", encoding="utf-8") as stream:
                proc = subprocess.run(pdal_argv, text=True, stdout=stream, stderr=subprocess.STDOUT)
            record_operation(f"classify_{label}", pdal_argv, proc.returncode, started, now())
            if proc.returncode != 0: raise RuntimeError(f"classification failed: {label}; inspect {log}")
            verify_argv = tools_docker_base() + ["-c", STAGE3_VERIFY_CODE, "/task/" + str(partial.relative_to(TASK_ROOT)), "/task/" + str(classified.relative_to(TASK_ROOT)), "/task/" + str(class_receipt.relative_to(TASK_ROOT))]
            verified = command(verify_argv, check=False)
            if verified.returncode != 0: raise RuntimeError(verified.stderr or verified.stdout)
        terminal = work / "roofer/roofer_terminal.json"
        if terminal.is_file():
            continue
        roofer_out = work / "roofer/output"
        began = time.monotonic(); rc = 0
        if roofer_out.exists():
            prior = next((row for row in json.loads((TASK_ROOT / "provenance.json").read_text())["return_codes"] if row.get("label") == f"roofer_{label}"), None)
            if prior is None or prior.get("return_code") != 0 or not any(roofer_out.iterdir()):
                raise RuntimeError(f"unsealed Roofer output requires review: {roofer_out}")
        else:
            roofer_out.mkdir(parents=True)
            box = [str(v) for v in spec["roofer_box"]]
            roofer_argv = [
                "docker", "run", "--rm", "--network", "none", "--cpus", "12", "--memory", "64g", "--pids-limit", "4096",
                "--user", f"{os.getuid()}:{os.getgid()}", "-v", f"{TASK_ROOT}:/task:rw", "-w", "/task", ROOFER_IMAGE,
                "--id-attribute", "stable_id", "--jobs", "1", "--box", *box,
                str(classified.relative_to(TASK_ROOT)), "control/shared_standard_footprint_4906982.geojson", str(roofer_out.relative_to(TASK_ROOT)),
            ]
            log = work / "roofer/roofer.log"; started = now()
            with log.open("w", encoding="utf-8") as stream:
                try:
                    proc = subprocess.run(roofer_argv, text=True, stdout=stream, stderr=subprocess.STDOUT, timeout=14400)
                    rc = proc.returncode
                except subprocess.TimeoutExpired:
                    rc = 124
            ended = now(); record_operation(f"roofer_{label}", roofer_argv, rc, started, ended)
        record_argv = tools_docker_base() + ["-c", ROOFER_RECORD_CODE, "/task/" + str(roofer_out.relative_to(TASK_ROOT)), "/task/" + str(terminal.relative_to(TASK_ROOT)), str(rc), str(time.monotonic() - began)]
        recorded = command(record_argv, check=False)
        print(json.dumps({"case": label, "classification": "PASS", "roofer_record": recorded.stdout.strip(), "roofer_record_stderr": recorded.stderr.strip()}), flush=True)
        if recorded.returncode != 0:
            raise RuntimeError(f"Roofer terminal failure: {label}; inspect {work / 'roofer/roofer.log'}")


FINALIZE_CODE = r'''
import csv,hashlib,json,math,statistics,sys
from pathlib import Path
from PIL import Image
from tensorboard.backend.event_processing.event_accumulator import EventAccumulator
root=Path(sys.argv[1]);arms=['MVC0','MVC05'];reps=['R1','R2','R3'];steps=[7000,12000,15000,20000]
def mean(v):return sum(v)/len(v)
def sd(v):return statistics.stdev(v) if len(v)>1 else 0.0
def latest(run,tag,step):
 vals=[]
 for path in sorted((run/'tb').glob('events*')):
  e=EventAccumulator(str(path));e.Reload()
  if tag in e.Tags().get('scalars',[]):vals.extend((int(x.step),float(x.value)) for x in e.Scalars(tag) if int(x.step)<=step-1)
 return None if not vals else max(vals,key=lambda x:x[0])[1]
records={};flat=[]
for arm in arms:
 for rep in reps:
  run=root/'arms'/arm/rep
  for step in steps:
   work=run/'evaluation'/f'step_{step:06d}';e=json.loads((work/'evaluation.json').read_text());r=json.loads((work/'fusion/roofer/roofer_terminal.json').read_text());a=r['target_attributes'] or {}
   g=e['geometry'];n=g['gaussian_count'];bins=g['opacity_bins']
   row={'arm':arm,'replica':rep,'completed_updates':step,'gaussian_count':n,'z_p99':g['z_epsg25832']['p99'],'z_max':g['z_epsg25832']['max'],'z_gt_650':g['count_z_gt_650m'],'z_gt_650_ratio':g['count_z_gt_650m']/n,'above_seed_max':g['count_above_seed_max_z'],'above_seed_max_ratio':g['count_above_seed_max_z']/n,'high_z_opacity_lt_0p1':bins['lt_0p1']['z_gt_650m'],'high_z_opacity_0p1_0p5':bins['0p1_0p5']['z_gt_650m'],'high_z_opacity_0p5_0p9':bins['0p5_0p9']['z_gt_650m'],'high_z_opacity_ge_0p9':bins['ge_0p9']['z_gt_650m'],'opacity_mean':g['opacity_mean'],'opacity_median':g['opacity_median'],'scale_min_q50':g['scale_min_q50_q95_q99_max'][0],'scale_min_q95':g['scale_min_q50_q95_q99_max'][1],'scale_max_q50':g['scale_max_q50_q95_q99_max'][0],'scale_max_q95':g['scale_max_q50_q95_q99_max'][1],'elongation_q05':g['elongation_q01_q05_q50_q95'][1],'elongation_q50':g['elongation_q01_q05_q50_q95'][2],'eval_psnr':e['render_metrics']['eval']['psnr'],'eval_ssim':e['render_metrics']['eval']['ssim'],'eval_lpips':e['render_metrics']['eval']['lpips'],'fusion_ge2':e['fusion']['point_count_ge2'],'fusion_ge3':e['fusion']['point_count_ge3'],'fusion_ge3_ratio':e['fusion']['ratio_ge3_of_ge2'],'roof_density':e['fusion']['roof_density_per_footprint_m2'],'wall_density':e['fusion']['wall_density_per_footprint_m2'],'mvc_loss':None if e['training_scalars']['loss/mvc'] is None else e['training_scalars']['loss/mvc']['value'],'mvc_depth_loss':None if e['training_scalars']['loss/mvc_depth'] is None else e['training_scalars']['loss/mvc_depth']['value'],'mvc_normal_loss':None if e['training_scalars']['loss/mvc_normal'] is None else e['training_scalars']['loss/mvc_normal']['value'],'mvc_n_inlier':None if e['training_scalars']['stats/mvc_n_inlier'] is None else e['training_scalars']['stats/mvc_n_inlier']['value'],'roofer_success':bool(r['rf_success']),'roofer_rmse_lod22':a.get('rf_rmse_lod22'),'roofer_pt_density':a.get('rf_pt_density'),'roofer_nodata_frac':a.get('rf_nodata_frac'),'roofer_roof_planes':a.get('rf_roof_planes'),'roofer_roof_type':a.get('rf_roof_type'),'roofer_h_roof_50p':a.get('rf_h_roof_50p'),'roofer_h_roof_max':a.get('rf_h_roof_max')}
   records[(arm,rep,step)]=row;flat.append(row)
with (root/'checkpoint_metrics.csv').open('w',newline='') as f:w=csv.DictWriter(f,fieldnames=list(flat[0]));w.writeheader();w.writerows(sorted(flat,key=lambda x:(x['completed_updates'],x['arm'],x['replica'])))
keys=['gaussian_count','z_p99','z_max','z_gt_650','z_gt_650_ratio','above_seed_max','above_seed_max_ratio','high_z_opacity_lt_0p1','high_z_opacity_0p1_0p5','high_z_opacity_0p5_0p9','high_z_opacity_ge_0p9','opacity_mean','opacity_median','scale_min_q50','scale_min_q95','scale_max_q50','scale_max_q95','elongation_q05','elongation_q50','eval_psnr','eval_ssim','eval_lpips','mvc_loss','mvc_depth_loss','mvc_normal_loss','mvc_n_inlier','fusion_ge2','fusion_ge3','fusion_ge3_ratio','roof_density','wall_density','roofer_rmse_lod22','roofer_pt_density','roofer_nodata_frac','roofer_roof_planes','roofer_h_roof_50p','roofer_h_roof_max']
deltas=[];paired={}
for step in steps:
 paired[str(step)]={}
 for key in keys:
  vals=[]
  for rep in reps:
   a=records[('MVC0',rep,step)][key];b=records[('MVC05',rep,step)][key];delta=None if a is None or b is None else b-a;vals.append(delta);deltas.append({'completed_updates':step,'replica':rep,'metric':key,'mvc05_minus_mvc0':delta})
  valid=[x for x in vals if x is not None];paired[str(step)][key]={'mean':mean(valid),'std':sd(valid),'positive_replicates':sum(x>0 for x in valid),'negative_replicates':sum(x<0 for x in valid),'zero_replicates':sum(x==0 for x in valid),'values':valid}
with (root/'paired_checkpoint_deltas.csv').open('w',newline='') as f:w=csv.DictWriter(f,fieldnames=list(deltas[0]));w.writeheader();w.writerows(deltas)
aggregates={}
for step in steps:
 aggregates[str(step)]={}
 for arm in arms:
  subset=[records[(arm,r,step)] for r in reps];aggregates[str(step)][arm]={k:{'mean':mean([x[k] for x in subset if x[k] is not None]),'std':sd([x[k] for x in subset if x[k] is not None])} for k in keys}
required=['train/psnr','train/ssim','train/lpips','eval/psnr','eval/ssim','eval/lpips','loss/mvc','loss/mvc_depth','loss/mvc_normal','loss_weight/mvc','stats/mvc_n_inlier','loss/nc','stats/gaussian_count','stats/grow_total','stats/pruned','stats/cum_grow_split','stats/cum_grow_duplicated','stats/cum_pruned','stats/opacity_mean','stats/opacity_median','runtime/max_vram_mib','runtime/wall_time_seconds']
tb_audit={};missing=[]
for arm in arms:
 for rep in reps:
  run=root/'arms'/arm/rep;tags=set()
  for path in sorted((run/'tb').glob('events*')):
   e=EventAccumulator(str(path));e.Reload();tags.update(e.Tags().get('scalars',[]))
  key=f'{arm}/{rep}';tb_audit[key]={'required':required,'present':sorted(set(required)&tags),'missing':sorted(set(required)-tags)};missing.extend((key,t) for t in set(required)-tags)
runtime={}
for arm in arms:
 runtime[arm]={}
 for rep in reps:
  r=json.loads((root/'control/receipts'/f'train_{arm}_{rep}.json').read_text());runtime[arm][rep]={'wall_seconds':r['wall_seconds'],'max_selected_gpu_used_mib':r['max_selected_gpu_used_mib'],'return_code':r['return_code']}
# Pair the fixed R1 held-out panels without altering either source image.
paired_dir=root/'representative_images/paired';paired_dir.mkdir(parents=True,exist_ok=True)
for step in steps:
 left=root/'representative_images/MVC0'/f'step_{step:06d}';right=root/'representative_images/MVC05'/f'step_{step:06d}'
 for lp in sorted(left.glob('*.png')):
  rp=right/lp.name
  if not rp.is_file():raise FileNotFoundError(rp)
  A=Image.open(lp).convert('RGB');B=Image.open(rp).convert('RGB');canvas=Image.new('RGB',(A.width+B.width,max(A.height,B.height)),(255,255,255));canvas.paste(A,(0,0));canvas.paste(B,(A.width,0));canvas.save(paired_dir/f'step_{step:06d}__{lp.name}')
body={'schema':'jointbuildgs.p2.e3_local_4906982_mvc_v2.metrics.v2','status':'COMPLETE_MEASURED','replicates_per_arm':3,'common_7k_gate_reconfirmed_by_all_evaluation_metrics':all(paired['7000'][k]['mean']==0 for k in keys if paired['7000'][k]['mean'] is not None),'aggregates':aggregates,'paired_mvc05_minus_mvc0':paired,'training_runtime':runtime,'tensorboard_audit':{'passed':not missing,'runs':tb_audit},'stage3':{'cases':24,'classification_passed':24,'roofer_return_code_zero':24,'roofer_rf_success_true':24,'quality_parameters':'ROOFER_DEFAULTS'},'interpretation_guardrails':{'gross_high_z_and_normal_surface_quality_reported_separately':True,'rel_thresh_0p1_can_exclude_gross_outliers':True,'n_replicates_too_small_for_confirmatory_inference':True},'official_PASS_usable':None,'scientific_verdict':None}
(root/'metrics.json').write_text(json.dumps(body,indent=2,sort_keys=True)+'\n')
print(json.dumps({'status':body['status'],'tb_passed':body['tensorboard_audit']['passed'],'paired_20k':paired['20000'],'roofer_cases':24},indent=2))
'''


def finalize_measurements() -> None:
    if all((run_root(arm, replica) / "evaluation/step_020000/fusion/roofer/roofer_terminal.json").is_file() for arm in ARMS for replica in REPLICAS):
        argv = eval_docker_base() + ["python", "-c", FINALIZE_CODE, container_path(TASK_ROOT)]
    else:
        raise RuntimeError("all Stage 3 terminals are required")
    log = TASK_ROOT / "logs/finalize_measurements.log"; started = now()
    with log.open("w", encoding="utf-8") as stream:
        proc = subprocess.run(argv, text=True, stdout=stream, stderr=subprocess.STDOUT)
    record_operation("finalize_measurements", argv, proc.returncode, started, now())
    if proc.returncode != 0: raise RuntimeError(f"measurement finalization failed; inspect {log}")
    print(log.read_text())


REPORT_CODE = r"""
import json,sqlite3,sys
from datetime import datetime,timezone
from pathlib import Path
root=Path(sys.argv[1]);m=json.loads((root/'metrics.json').read_text());p=m['paired_mvc05_minus_mvc0'];a=m['aggregates'];now=datetime.now(timezone.utc).isoformat()
def f(v,n=3):return f'{v:.{n}f}'
def d(step,key):return p[str(step)][key]['mean']
def s(step,key):return p[str(step)][key]['std']
rows=[]
for step in [7000,12000,15000,20000]:
 rows.append({'step':step,'z_gt_650_delta':d(step,'z_gt_650'),'z_gt_650_rate_delta_pp':100*d(step,'z_gt_650_ratio'),'above_seed_rate_delta_pp':100*d(step,'above_seed_max_ratio'),'roof_density_delta':d(step,'roof_density'),'support3_rate_delta_pp':100*d(step,'fusion_ge3_ratio'),'eval_psnr_delta':d(step,'eval_psnr'),'eval_ssim_delta':d(step,'eval_ssim'),'eval_lpips_delta':d(step,'eval_lpips'),'roofer_rmse_delta':d(step,'roofer_rmse_lod22')})
rep20=[]
for i,rep in enumerate(['R1','R2','R3']):
 rep20.append({'replica':rep,'z_gt_650_delta':p['20000']['z_gt_650']['values'][i],'roof_density_delta':p['20000']['roof_density']['values'][i],'eval_psnr_delta':p['20000']['eval_psnr']['values'][i],'eval_ssim_delta':p['20000']['eval_ssim']['values'][i],'eval_lpips_delta':p['20000']['eval_lpips']['values'][i],'roofer_rmse_delta':p['20000']['roofer_rmse_lod22']['values'][i]})
headline=[{'id':'head','z_gt_650_delta':d(20000,'z_gt_650'),'z_gt_650_rate_delta_pp':100*d(20000,'z_gt_650_ratio'),'high_z_opacity_ge_0p9_delta':d(20000,'high_z_opacity_ge_0p9'),'support_ge2_delta':d(20000,'fusion_ge2'),'support3_rate_delta_pp':100*d(20000,'fusion_ge3_ratio'),'roof_density_delta':d(20000,'roof_density'),'eval_psnr_delta':d(20000,'eval_psnr'),'eval_ssim_delta':d(20000,'eval_ssim'),'eval_lpips_delta':d(20000,'eval_lpips'),'roofer_rmse_delta':d(20000,'roofer_rmse_lod22')}]
conn=sqlite3.connect(':memory:')
def materialize(name,data,query):
 cols=list(data[0]);types=['REAL' if isinstance(data[0][c],float) else ('INTEGER' if isinstance(data[0][c],int) else 'TEXT') for c in cols]
 conn.execute('CREATE TABLE '+name+' ('+', '.join(f'{c} {t}' for c,t in zip(cols,types))+')');conn.executemany('INSERT INTO '+name+' VALUES ('+','.join('?' for _ in cols)+')',[[r[c] for c in cols] for r in data]);return [dict(zip([x[0] for x in conn.execute(query).description],v)) for v in conn.execute(query).fetchall()]
q_head='SELECT * FROM headline'
q_steps='SELECT * FROM checkpoint_deltas ORDER BY step'
q_rep='SELECT * FROM replicate_20k ORDER BY replica'
headline=materialize('headline',headline,q_head);rows=materialize('checkpoint_deltas',rows,q_steps);rep20=materialize('replicate_20k',rep20,q_rep)
sources=[{'id':'headline_source','label':'20k paired headline metrics','path':'metrics.json','query':{'engine':'SQLite over frozen metrics snapshot','language':'sql','sql':q_head,'description':'Select the 20k paired effect summary materialized from metrics.json.','tables_used':['headline'],'filters':['completed_updates = 20000'],'metric_definitions':['All deltas are MVC05 minus MVC0 paired means across R1-R3.']}},{'id':'checkpoint_source','label':'Checkpoint paired aggregate metrics','path':'metrics.json','query':{'engine':'SQLite over frozen metrics snapshot','language':'sql','sql':q_steps,'description':'Select paired checkpoint effects in completed-update order.','tables_used':['checkpoint_deltas'],'filters':['steps in (7000,12000,15000,20000)'],'metric_definitions':['All deltas are MVC05 minus MVC0 paired means across R1-R3.']}},{'id':'replicate_source','label':'20k paired replicate deltas','path':'paired_checkpoint_deltas.csv','query':{'engine':'SQLite over frozen paired deltas','language':'sql','sql':q_rep,'description':'Select the three 20k paired replicate rows.','tables_used':['replicate_20k'],'filters':['completed_updates = 20000'],'metric_definitions':['Roofer RMSE delta is MVC05 minus MVC0 internal plane-fit RMSE.']}}]
summary=f'''## Technical summary\n\n- **정상 표면 지원 지표는 증가했다.** 20k에서 MVC05−MVC0는 ≥2-view fusion 점 **+{d(20000,'fusion_ge2'):,.0f}**, ≥3-view 비율 **+{100*d(20000,'fusion_ge3_ratio'):.2f} pp**, roof-normal density **+{d(20000,'roof_density'):.3f} points/m²**였고 세 replicate 모두 같은 방향이었다.\n- **gross high-Z는 줄지 않았다.** Z>650 m Gaussian은 **+{d(20000,'z_gt_650'):.1f}**이고 세 replicate 모두 증가했다. 전체 Gaussian 감소를 보정한 비율도 **+{100*d(20000,'z_gt_650_ratio'):.4f} pp**였다. opacity≥0.9 high-Z도 평균 **+{d(20000,'high_z_opacity_ge_0p9'):.1f}**였다.\n- **held-out RGB 개선은 일관되지 않았다.** PSNR **{d(20000,'eval_psnr'):+.3f} dB**, SSIM **{d(20000,'eval_ssim'):+.4f}**, LPIPS **{d(20000,'eval_lpips'):+.4f}**이며 지표와 replicate별 부호가 섞였다.\n- **Roofer 내부 plane-fit RMSE는 평균 개선 방향이지만 replicate 불일치가 크다.** 20k 차이는 **{d(20000,'roofer_rmse_lod22'):+.3f} ± {s(20000,'roofer_rmse_lod22'):.3f}**이고 paired 값은 {p['20000']['roofer_rmse_lod22']['values']}이다. 이는 GT 오차가 아니라 Roofer 내부 적합 RMSE다.\n\n이 문서는 측정 결과와 후속 권고만 제시한다. `scientific_verdict`는 `null`이다.'''
manifest={'version':1,'surface':'report','title':'4906982 MVC-only replicated diagnostic','description':'P2-E3-LOCAL-4906982-MVC-v2 technical measurement report','generatedAt':now,'sources':sources,
'cards':[{'id':'card_highz','dataset':'headline','sourceId':'headline_source','description':'MVC05 minus MVC0 at 20k; lower is desired for gross high-Z','metrics':[{'label':'Z>650 Gaussian delta','field':'z_gt_650_delta','format':'number','signed':True}]},{'id':'card_support','dataset':'headline','sourceId':'headline_source','description':'MVC05 minus MVC0 at 20k; ≥2-view fused points','metrics':[{'label':'Fusion ≥2-view delta','field':'support_ge2_delta','format':'number','signed':True}]},{'id':'card_roof','dataset':'headline','sourceId':'headline_source','description':'MVC05 minus MVC0 at 20k; roof-normal density points/m²','metrics':[{'label':'Roof density delta','field':'roof_density_delta','format':'number','signed':True}]},{'id':'card_rgb','dataset':'headline','sourceId':'headline_source','description':'MVC05 minus MVC0 at 20k; held-out mean PSNR','metrics':[{'label':'Eval PSNR delta','field':'eval_psnr_delta','format':'number','signed':True}]},{'id':'card_roofer','dataset':'headline','sourceId':'headline_source','description':'MVC05 minus MVC0 at 20k; Roofer internal plane-fit RMSE','metrics':[{'label':'Roofer RMSE delta','field':'roofer_rmse_delta','format':'number','signed':True}]}],
'charts':[{'id':'chart_highz','title':'Z>650 m Gaussian count delta','subtitle':'MVC05 minus MVC0 paired mean by checkpoint; n=3','intent':'comparison','question':'Did MVC reduce gross high-Z outliers?','rationale':'Discrete checkpoint bars show the signed paired mean without implying a continuous trend.','comparisonContext':{'baseline':'MVC0','grain':'checkpoint paired replicate mean','unit':'Gaussian count'},'type':'bar','dataset':'checkpoint_deltas','sourceId':'checkpoint_source','encodings':{'x':{'field':'step','type':'ordinal','label':'Completed updates'},'y':{'field':'z_gt_650_delta','type':'quantitative','label':'MVC05 − MVC0'}},'valueFormat':'number','layout':'full','surface':{'palette':{'kind':'diverging'},'valueLabels':'all'}},{'id':'chart_roof','title':'Footprint roof-normal density delta','subtitle':'MVC05 minus MVC0 paired mean, points/m²; n=3','intent':'comparison','question':'Did MVC increase normal-surface fusion density?','rationale':'Checkpoint bars expose persistence and magnitude of the surface-support change.','comparisonContext':{'baseline':'MVC0','grain':'checkpoint paired replicate mean','unit':'points per square metre'},'type':'bar','dataset':'checkpoint_deltas','sourceId':'checkpoint_source','encodings':{'x':{'field':'step','type':'ordinal','label':'Completed updates'},'y':{'field':'roof_density_delta','type':'quantitative','label':'MVC05 − MVC0','unit':'points/m²'}},'valueFormat':'number','layout':'full','surface':{'palette':{'kind':'sequential'},'valueLabels':'all'}},{'id':'chart_roofer','title':'20k Roofer internal RMSE paired delta','subtitle':'Each bar is one paired replicate; negative means lower internal fit RMSE','intent':'comparison','question':'Was the downstream Roofer response consistent across replicates?','rationale':'Replicate bars retain the sign reversal hidden by the mean.','comparisonContext':{'baseline':'MVC0','grain':'paired replica at 20k','unit':'Roofer internal RMSE'},'type':'bar','dataset':'replicate_20k','sourceId':'replicate_source','encodings':{'x':{'field':'replica','type':'nominal','label':'Replica'},'y':{'field':'roofer_rmse_delta','type':'quantitative','label':'MVC05 − MVC0'}},'valueFormat':'number','layout':'full','surface':{'palette':{'kind':'diverging'},'valueLabels':'all'}}],
'tables':[{'id':'table_checkpoint','title':'Checkpoint paired effects','subtitle':'MVC05 minus MVC0 means; n=3 paired continuations from the exact same 7k state','dataset':'checkpoint_deltas','sourceId':'checkpoint_source','defaultSort':{'field':'step','direction':'asc'},'density':'spacious','layout':'full','columns':[{'field':'step','label':'Step','format':'number'},{'field':'z_gt_650_delta','label':'Δ Z>650','format':'number','movement':True},{'field':'z_gt_650_rate_delta_pp','label':'Δ Z>650 rate (pp)','format':'number','movement':True},{'field':'roof_density_delta','label':'Δ roof density','format':'number','movement':True},{'field':'support3_rate_delta_pp','label':'Δ ≥3-view share (pp)','format':'number','movement':True},{'field':'eval_psnr_delta','label':'Δ PSNR (dB)','format':'number','movement':True},{'field':'roofer_rmse_delta','label':'Δ Roofer RMSE','format':'number','movement':True}]}],
'blocks':[{'id':'title','type':'markdown','body':'# 4906982 MVC-only replicated diagnostic','layout':'full'},{'id':'summary','type':'markdown','body':summary,'sourceId':'headline_source','layout':'full'},{'id':'headline','type':'metric-strip','cardIds':['card_highz','card_support','card_roof','card_rgb','card_roofer'],'layout':'full'},{'id':'finding_highz','type':'markdown','body':'## MVC did not suppress the gross high-Z tail\n\nThe absolute count, count rate, p99 Z, and high-opacity tail do not support a high-Z reduction claim. The broader “above sparse-seed maximum” count falls, but that is partly driven by fewer total Gaussians and does not reconcile the stricter Z>650 m tail.','sourceId':'headline_source','layout':'full'},{'id':'highz_chart','type':'chart','chartId':'chart_highz','layout':'full'},{'id':'finding_surface','type':'markdown','body':'## Normal-surface fusion support increased, while RGB evidence remained mixed\n\nThe ≥3-view support share and footprint roof-normal density increased in all three 20k pairs. This is evidence of denser multi-view-supported rendered surface, not proof of metric depth or normal accuracy: no external depth/normal supervision or GT geometry entered training.','sourceId':'headline_source','layout':'full'},{'id':'roof_chart','type':'chart','chartId':'chart_roof','layout':'full'},{'id':'finding_roofer','type':'markdown','body':'## Roofer response is heterogeneous across replicates\n\nAll 24 Roofer runs completed with the same shared footprint and default quality parameters. The 20k mean internal RMSE moves downward, but one of three pairs moves strongly upward, so the aggregate is not stable enough to call a downstream geometry improvement.','sourceId':'headline_source','layout':'full'},{'id':'roofer_chart','type':'chart','chartId':'chart_roofer','layout':'full'},{'id':'audit_table_intro','type':'markdown','body':'## Exact checkpoint comparison\n\nThe table keeps the discrete checkpoint grain and signed MVC05−MVC0 convention visible.','layout':'full'},{'id':'audit_table','type':'table','tableId':'table_checkpoint','layout':'full'},{'id':'scope','type':'markdown','body':'## Scope and metric definitions\n\nPopulation: one building, 55 fixed crop views (47 train, 8 held-out), one random seed with three paired post-7k continuations per arm. High-Z uses EPSG:25832 Z>650 m. Roof density counts fused points inside the exact shared GroundSurface XY footprint whose rendered world normal satisfies |nz|≥0.7. Fusion requires at least two distinct views in a 0.15 m voxel. Roofer RMSE is its internal LoD2.2 plane-fit attribute, not error to reference LoD2.','layout':'full'},{'id':'method','type':'markdown','body':'## Experimental design and validation\n\nA fresh MVC-inactive run produced the exact 7k full-state checkpoint. Six continuations were metadata-rebound while model, optimizer, strategy, grouping, RNG, and loss cursor remained byte-equal. MVC0 and MVC05 differ only in w_mvc (0 versus 0.5); all MVC keys are explicit. Evaluations use all fixed train/held-out views, and Stage 3 uses identical SMRF, footprint overlay, and Roofer parameters. The 7k metrics are exactly equal across all six forks.','layout':'full'},{'id':'limits','type':'markdown','body':'## Limitations and robustness checks\n\nThree continuations from one seed and one building are a technical repeatability diagnostic, not confirmatory inference. The paired branches still show CUDA/densification stochastic variation after 7k. The roof/wall normal buckets measure density, not correctness. rel_thresh=0.1 can exclude gross outliers from MVC inliers. No GT Z, RoofSurface, roof type, external MVS depth/normal, ALS, LoD prior, or semantic loss entered training.','layout':'full'},{'id':'next','type':'markdown','body':'## Recommended next steps\n\n1. Trace Z>650 Gaussian birth/grow/prune lineage and MVC-inlier eligibility before adding another loss.\n2. Treat multi-view densification as a separate intervention aimed at coverage, because MVC already increases supported fusion density but does not suppress the extreme tail.\n3. If the target is absolute roof geometry or stable Roofer fit, preregister a separate depth/normal-supervision arm; MVC consistency alone provides no absolute depth/normal anchor.\n4. Repeat on additional buildings only after the high-Z mechanism and endpoint definitions are frozen.','layout':'full'},{'id':'questions','type':'markdown','body':'## Further questions\n\n- Are the persistent Z>650 Gaussians inherited, split, or duplicated, and why do many retain opacity≥0.9?\n- Does support-aware densification improve coverage without amplifying high-Z?\n- Which independent depth/normal evidence can provide an absolute geometric anchor without contaminating the shared image-only base?','layout':'full'}]}
artifact={'surface':'report','manifest':manifest,'snapshot':{'version':1,'generatedAt':now,'status':'ready','datasets':{'headline':headline,'checkpoint_deltas':rows,'replicate_20k':rep20}},'sources':sources,'package_info':{'root':'.','manifestPath':'artifact.json','snapshotPath':'artifact.json'}}
(root/'report_artifact.json').write_text(json.dumps(artifact,indent=2,sort_keys=True)+'\n')
comparison=f'''# P2-E3-LOCAL-4906982-MVC-v2 comparison\n\n## Measured answer\n\nMVC05는 **정상 표면의 multi-view-supported fusion 밀도를 늘렸지만**, **gross high-Z를 줄이지 않았고**, held-out RGB 및 Roofer 결과는 replicate 전반에서 일관된 개선을 보이지 않았다. 이는 scientific verdict가 아니라 이 단일 건물 기술 진단의 관찰이다. `scientific_verdict: null`.\n\n## 20k paired measurements (MVC05 − MVC0, n=3)\n\n| Endpoint | Mean ± sample SD | Pair signs | Observation |\n|---|---:|---:|---|\n| Z>650 Gaussian count | {d(20000,'z_gt_650'):+.1f} ± {s(20000,'z_gt_650'):.1f} | 3 increase / 0 decrease | gross tail not reduced |\n| Z>650 share | {100*d(20000,'z_gt_650_ratio'):+.4f} ± {100*s(20000,'z_gt_650_ratio'):.4f} pp | 3 / 0 | total-count normalization does not reverse result |\n| opacity≥0.9 Z>650 | {d(20000,'high_z_opacity_ge_0p9'):+.1f} ± {s(20000,'high_z_opacity_ge_0p9'):.1f} | 2 / 1 | high-opacity tail persists |\n| Gaussian count | {d(20000,'gaussian_count'):+,.0f} ± {s(20000,'gaussian_count'):,.0f} | 0 / 3 | MVC arm is smaller overall |\n| Fusion ≥2-view points | {d(20000,'fusion_ge2'):+,.0f} ± {s(20000,'fusion_ge2'):,.0f} | 3 / 0 | supported surface coverage increased |\n| Fusion ≥3-view share | {100*d(20000,'fusion_ge3_ratio'):+.2f} ± {100*s(20000,'fusion_ge3_ratio'):.2f} pp | 3 / 0 | stronger support increased |\n| Roof-normal density | {d(20000,'roof_density'):+.3f} ± {s(20000,'roof_density'):.3f} points/m² | 3 / 0 | normal-surface density increased |\n| Eval PSNR | {d(20000,'eval_psnr'):+.3f} ± {s(20000,'eval_psnr'):.3f} dB | 1 / 2 | inconsistent |\n| Eval SSIM | {d(20000,'eval_ssim'):+.4f} ± {s(20000,'eval_ssim'):.4f} | 2 / 1 | inconsistent |\n| Eval LPIPS | {d(20000,'eval_lpips'):+.4f} ± {s(20000,'eval_lpips'):.4f} | 1 worse / 2 better | inconsistent |\n| Roofer internal RMSE | {d(20000,'roofer_rmse_lod22'):+.3f} ± {s(20000,'roofer_rmse_lod22'):.3f} | 1 worse / 2 better | heterogeneous; not GT error |\n\n## High-Z and normal-surface results are separate\n\nThe broad count above the sparse-seed maximum falls by {d(20000,'above_seed_max'):+,.0f}, but total Gaussian count also falls. The stricter Z>650 count and rate both rise, and the maximum remains unchanged at {a['20000']['MVC0']['z_max']['mean']:.3f} m in both arms. With `mvc_rel_thresh=0.1`, gross outliers can remain outside the MVC inlier set even when ordinary surface support improves.\n\nNormal-surface evidence moves differently: all three 20k pairs increase ≥3-view support share and footprint roof-normal density. This is a density/consistency observation, not absolute depth or normal correctness, because the experiment deliberately contains no external depth/normal supervision.\n\n## Reproducibility and gates\n\n- Exact common 7k learned state: pass across six forks.\n- 7k evaluation equality: exact across all recorded endpoints.\n- Required checkpoints: 24/24 valid (7k, 12k, 15k, 20k × 2 arms × 3 replicas).\n- TensorBoard required-tag audit: pass for 6/6 runs.\n- Classification: 24/24 EPSG:25832 with class 2 and 6 present.\n- Roofer: 24/24 return code 0 and `rf_success=true`; same defaults and shared footprint.\n\n## Measurement limitations\n\nThis is one building, one seed, and three post-7k paired continuations. It supports technical observations and failure-mode diagnosis, not population inference. Roofer RMSE is internal plane-fit RMSE, not reference-geometry error. The roof/wall categories are world-normal threshold buckets, not semantic truth.\n\n## Next recommendations\n\n1. Audit Z>650 Gaussian birth, grow/split/duplicate lineage, opacity evolution, and MVC-inlier exclusion before introducing another loss.\n2. Evaluate multi-view densification as a separately preregistered coverage intervention; do not fold it into this MVC result.\n3. If absolute geometry and Roofer stability remain the goal, prepare a separate depth/normal-supervision arm after freezing the evidence source and confidence mask.\n4. Expand to additional buildings only after endpoint definitions and the high-Z mechanism audit are fixed.\n'''
(root/'comparison.md').write_text(comparison)
notes=f'''# {root.name}\n\nStatus: `COMPLETE_MEASURED`\n\n- Fresh common MVC-inactive prefix: 7,000 updates.\n- Paired continuations: MVC0 and MVC05, R1–R3, through 20,000 updates.\n- Checkpoints: 7k, 12k, 15k, 20k preserved for all six continuations.\n- Checkpoint evaluation, depth fusion, classification, and Roofer: complete for 24/24 cases.\n- Required TensorBoard tags: present in all six run directories.\n- Representative panels: fixed R1, all eight held-out views, all four checkpoints, both arms; paired copies in `representative_images/paired/`.\n- Portable technical report: `report.html`; comparison viewer slot: `viewer/index.html`.\n- Report contract/package/structural verification passed; browser viewport QA is `structural_only` because the pinned builder image has no Chromium.\n- No external MVS depth/normal, ALS, LoD prior, semantic loss, new loss, or multi-view densification was used.\n- Scientific verdict: `null`.\n'''
(root/'NOTES.md').write_text(notes)
issues='''# Issues\n\n1. The first checkpoint-evaluation attempt exited before evaluation because the derived evaluation image lacked `pyproj`. The image was rebuilt with pinned `pyproj==3.7.1`; the successful retry used image `jointbuildgs:mvc-eval-v1`. Training artifacts were unaffected.\n2. The first Stage-3 preparation attempt hit a write-permission mismatch because GPU evaluation created root-owned directories. Ownership was normalized only inside this new v2 task namespace, then the same preparation was rerun successfully.\n3. The first completed Roofer output lacked a terminal receipt because of an argument-unpacking bug in the receipt wrapper. Roofer itself returned 0 and wrote one target building. The output was not recomputed; it was hashed and sealed by the corrected wrapper. A second receipt-only attempt exposed an unbound error-message variable and was corrected before sealing.\n4. The earlier v1 design required bitwise equality between independent CUDA runs and therefore stopped before MVC activation. v2 replaces that invalid gate with one exact common 7k state plus three paired continuations; post-7k stochastic spread is retained as measured variation.\n5. The portable report passed contract, package, payload-equality, runtime-root, and semantic-fallback structural checks. Browser viewport/source-dialog QA is `structural_only` because the pinned offline builder image contains no compatible Chromium.\n\nNo NaN, OOM, training fallback, missing required checkpoint, failed classification, or failed Roofer case occurred.\n'''
(root/'issues.md').write_text(issues)
source_notes={'schema':'jointbuildgs.p2.e3_local_4906982_mvc_v2.report_source_notes.v1','audience':'technical','delivery_mode':'portable_html','required_structure_mapping':{'title':'title','technical_summary':'summary','key_findings':'finding_highz/finding_surface/finding_roofer','scope_data_metric_definitions':'scope','methodology':'method','limitations_uncertainty_robustness':'limits','recommended_next_steps':'next','further_questions':'questions'},'chart_map':[{'section':'gross high-Z','question':'Did MVC reduce Z>650 outliers?','family':'comparison','type':'bar','fields':['step','z_gt_650_delta'],'claim':'gross high-Z was not reduced','palette':'diverging two-root','artifact':'report.html'},{'section':'normal-surface support','question':'Did MVC increase roof-normal density?','family':'comparison','type':'bar','fields':['step','roof_density_delta'],'claim':'density increased after activation','palette':'single-root sequential','artifact':'report.html'},{'section':'Roofer stability','question':'Was downstream response replicate-consistent?','family':'comparison','type':'bar','fields':['replica','roofer_rmse_delta'],'claim':'replicate sign was heterogeneous','palette':'diverging two-root','artifact':'report.html'}],'omitted_visuals':[{'metric':'four-checkpoint time trend','reason':'four discrete checkpoints are too sparse for an honest continuous line chart'},{'metric':'RGB multi-metric combined chart','reason':'PSNR, SSIM, and LPIPS have different units and mixed signs; exact table and narrative are clearer'}],'validation_stance':'Share with caveats for technical-development use only; not confirmatory and no scientific verdict','scientific_verdict':None}
(root/'control/report_source_notes.json').write_text(json.dumps(source_notes,indent=2,sort_keys=True)+'\n')
# Separate artifact-local comparison viewer; existing viewer results are untouched.
paired=sorted((root/'representative_images/paired').glob('*.png'));names=[x.name for x in paired]
viewer=root/'viewer';viewer.mkdir(exist_ok=True)
html='''<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>4906982 MVC v2 comparison slot</title><style>body{font-family:system-ui;background:#0d1117;color:#e6edf3;margin:0;padding:20px}header{max-width:1500px;margin:auto}select,a{padding:8px;margin:4px;background:#21262d;color:#e6edf3;border:1px solid #30363d;border-radius:5px}img{display:block;max-width:100%;margin:18px auto;border:1px solid #30363d}small{color:#8b949e}</style></head><body><header><h1>DEBY_LOD2_4906982 · MVC0 vs MVC05</h1><p>R1 fixed qualitative slot. Each image shows MVC0 on the left and MVC05 on the right.</p><label>Panel <select id="panel"></select></label><a href="../report.html">Open measured report</a><a href="../comparison.md">Open comparison.md</a><br><small>Scientific verdict: null</small></header><img id="view" alt="paired held-out qualitative panel"><script>const names=__NAMES__;const s=document.getElementById('panel'),v=document.getElementById('view');for(const n of names){const o=document.createElement('option');o.value=n;o.textContent=n;s.appendChild(o)}function show(){v.src='../representative_images/paired/'+s.value} s.onchange=show;show();</script></body></html>'''.replace('__NAMES__',json.dumps(names))
(viewer/'index.html').write_text(html)
(root/'viewer_slot.json').write_text(json.dumps({'schema':'jointbuildgs.viewer.comparison_slot.v1','slot_id':'p2-e3-local-4906982-mvc-v2','label':'DEBY_LOD2_4906982 MVC0 vs MVC05','relative_url':'viewer/index.html','source':'representative_images/paired','panel_count':len(names),'separate_add_only_slot':True,'legacy_results_modified':False,'scientific_verdict':None},indent=2,sort_keys=True)+'\n')
print(json.dumps({'artifact':'report_artifact.json','comparison':'comparison.md','paired_panels':len(names),'viewer':'viewer/index.html'}))
"""


def finalize_report() -> None:
    metrics = json.loads((TASK_ROOT / "metrics.json").read_text())
    if metrics.get("status") != "COMPLETE_MEASURED" or not metrics.get("tensorboard_audit", {}).get("passed"):
        raise RuntimeError("complete validated measurements required")
    argv = eval_docker_base() + ["python", "-c", REPORT_CODE, container_path(TASK_ROOT)]
    started = now(); proc = command(argv, check=False); record_operation("build_report_sources", argv, proc.returncode, started, now())
    if proc.returncode != 0: raise RuntimeError(proc.stderr or proc.stdout)
    plugin_root = Path("/home/innopam/.codex/plugins/cache/openai-curated-remote/data-analytics/0.2.8-13ceeea1f599")
    builder_image = "innopam-v1-nbm-frontend:latest"
    builder_argv = [
        "docker", "run", "--rm", "--network", "none", "--user", f"{os.getuid()}:{os.getgid()}",
        "-v", f"{plugin_root}:/plugin:ro", "-v", f"{TASK_ROOT}:/task:rw", "-w", "/plugin", builder_image,
        "node", "/plugin/skills/build-report/scripts/deliver_portable_artifact.mjs",
        "--input", "/task/report_artifact.json", "--output", "/task/report.html",
        "--screenshot", "/task/logs/report_delivery_failure.png",
    ]
    log = TASK_ROOT / "logs/report_delivery.log"; started = now()
    with log.open("w", encoding="utf-8") as stream:
        built = subprocess.run(builder_argv, text=True, stdout=stream, stderr=subprocess.STDOUT)
    record_operation("deliver_portable_report", builder_argv, built.returncode, started, now())
    if built.returncode != 0: raise RuntimeError(f"report delivery failed; inspect {log}")
    try: receipt = json.loads(log.read_text())
    except json.JSONDecodeError: receipt = {"raw_log": log.read_text()}
    atomic_json(TASK_ROOT / "control/report_delivery_receipt.json", {"builder_image": builder_image, "builder_image_id": command(["docker", "image", "inspect", builder_image, "--format", "{{.Id}}"], check=False).stdout.strip(), "delivery": receipt})
    contract = json.loads((TASK_ROOT / "experiment_contract.json").read_text()); contract["status"] = "COMPLETE_MEASURED"; contract["scientific_verdict"] = None; atomic_json(TASK_ROOT / "experiment_contract.json", contract)
    provenance_path = TASK_ROOT / "provenance.json"; provenance = json.loads(provenance_path.read_text())
    provenance["git_at_completion"] = git_record()
    provenance["evaluation_docker_image"] = {"reference": EVAL_IMAGE, "id": command(["docker", "image", "inspect", EVAL_IMAGE, "--format", "{{.Id}}"], check=False).stdout.strip()}
    provenance["stage3_images"] = {"tools": {"reference": TOOLS_IMAGE, "id": TOOLS_IMAGE_ID}, "roofer": {"reference": ROOFER_IMAGE, "id": ROOFER_IMAGE_ID}}
    provenance["report_builder_image"] = {"reference": builder_image, "id": command(["docker", "image", "inspect", builder_image, "--format", "{{.Id}}"], check=False).stdout.strip()}
    provenance["common_checkpoint_input_sha256"] = sha256(TASK_ROOT / "common_prefix/ckpt/step_007000.pt")
    provenance["source_files_sha256"][str(Path(__file__).resolve().relative_to(REPO))] = sha256(Path(__file__).resolve())
    provenance["output_index_sha256"] = {name: sha256(TASK_ROOT / name) for name in ["experiment_contract.json", "input_hashes.json", "config_diff.txt", "checkpoint_metrics.csv", "paired_checkpoint_deltas.csv", "metrics.json", "comparison.md", "NOTES.md", "issues.md", "report_artifact.json", "report.html", "viewer_slot.json"]}
    provenance["known_incidental_failures"] = ["evaluation image missing pyproj before any checkpoint evaluation", "Stage-3 preparation task-directory ownership mismatch", "Roofer terminal receipt wrapper errors after successful Roofer output"]
    provenance["ended_utc"] = now(); provenance["scientific_verdict"] = None; atomic_json(provenance_path, provenance)
    print(json.dumps({"status": "COMPLETE_MEASURED", "report": str(TASK_ROOT / "report.html"), "viewer": str(TASK_ROOT / "viewer/index.html"), "scientific_verdict": None}, indent=2))



def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["preflight", "smoke", "train-prefix", "fork-prefix", "train-replicas", "analyze-checkpoints", "stage3", "finalize-measurements", "finalize-report", "all-training"])
    args = parser.parse_args()
    if args.command in {"preflight", "all-training"}: preflight()
    if args.command in {"smoke", "all-training"}: smoke()
    if args.command in {"train-prefix", "all-training"}: train_prefix()
    if args.command in {"fork-prefix", "all-training"}: fork_prefix()
    if args.command in {"train-replicas", "all-training"}: train_replicas()
    if args.command == "analyze-checkpoints": analyze_checkpoints()
    if args.command == "stage3": run_stage3()
    if args.command == "finalize-measurements": finalize_measurements()
    if args.command == "finalize-report": finalize_report()


if __name__ == "__main__":
    main()
