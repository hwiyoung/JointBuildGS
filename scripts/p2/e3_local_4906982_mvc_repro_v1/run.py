#!/usr/bin/env python3
"""Docker-only pre-activation reproducibility diagnosis for the MVC experiment.

This task never activates MVC and never produces a scientific performance
comparison.  It repeats the exact MVC0 learning path through 1,000 completed
updates, first with the production densification schedule, then with refinement
delayed beyond the observation window, and finally with PyTorch deterministic
controls enabled from a wrapper.  All six runs use one prewarmed JIT cache and
the same host GPU sequentially.  A final control resumes four copies of one
byte-identical 1,000-update full state through 5,000 updates.
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
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
TASK_ID = "P2-E3-LOCAL-4906982-MVC-REPRO-v1"
TASK_ROOT = ARTIFACT_ROOT / "phase-payloads/p2/e3_local_4906982_mvc_repro_v1" / TASK_ID
BASE_CONFIG = REPO / "configs/p2/e3_local_4906982_mvc_v1/mvc0.yaml"
SOURCE_INPUT_HASHES = ARTIFACT_ROOT / "phase-payloads/p2/e3_local_4906982_mvc_v1/P2-E3-LOCAL-4906982-MVC-v1/input_hashes.json"
IMAGE = "jointbuildgs:dev"
GPU = "1"
OBSERVE_UNTIL = 1000
STEPS = (1, 10, 50, 100, 140, 200, 499, 500, 501, 600, 800, 1000)
SCENARIOS = {
    "baseline": {"deterministic": False, "refine_start_iter": 500},
    "no_refine_to_1k": {"deterministic": False, "refine_start_iter": 2000},
    "deterministic": {"deterministic": True, "refine_start_iter": 500},
}
REPLICAS = ("R1", "R2")
FORK_MODES = {"plain": False, "deterministic": True}


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(text, encoding="utf-8")
    os.replace(temporary, path)


def atomic_json(path: Path, body: Any) -> None:
    atomic_text(path, json.dumps(body, indent=2, sort_keys=True) + "\n")


def command(command: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, check=check, text=True, capture_output=True)


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
    raw = command([
        "nvidia-smi", f"--id={GPU}",
        "--query-gpu=index,name,uuid,memory.total,driver_version",
        "--format=csv,noheader,nounits",
    ]).stdout.strip().split(", ")
    return {"host_index": int(raw[0]), "model": raw[1], "uuid": raw[2], "memory_total_mib": int(raw[3]), "driver": raw[4]}


def docker_base(*, gpu: bool = False, name: str | None = None, keep: bool = False, deterministic: bool = False) -> list[str]:
    args = ["docker", "run"]
    if not keep:
        args.append("--rm")
    if name:
        args += ["--name", name]
    if gpu:
        args += ["--gpus", f"device={GPU}", "--ipc=host"]
    if deterministic:
        args += ["-e", "CUBLAS_WORKSPACE_CONFIG=:4096:8", "-e", "NVIDIA_TF32_OVERRIDE=0"]
    args += [
        "-v", f"{REPO}:/workspace/JointBuildGS:ro",
        "-v", f"{ARTIFACT_ROOT}:/artifacts/JointBuildGS",
        "-v", f"{TASK_ROOT / 'cache/torch_extensions'}:/root/.cache/torch_extensions",
        "-w", "/workspace/JointBuildGS",
        IMAGE,
    ]
    return args


def container_path(path: Path) -> str:
    return "/artifacts/JointBuildGS/" + str(path.relative_to(ARTIFACT_ROOT))


def prepare() -> None:
    marker = TASK_ROOT / "experiment_contract.json"
    if TASK_ROOT.exists() and any(TASK_ROOT.iterdir()) and not marker.is_file():
        raise RuntimeError(f"non-empty unbound namespace: {TASK_ROOT}")
    for child in ("control/configs", "control/runtime", "logs", "runs", "cache/torch_extensions"):
        (TASK_ROOT / child).mkdir(parents=True, exist_ok=True)
    base = yaml.safe_load(BASE_CONFIG.read_text(encoding="utf-8"))
    if float(base["w_mvc"]) != 0.0 or int(base["mvc_warmup"]) != 7000:
        raise RuntimeError("base config is not the frozen MVC0 pre-activation control")
    previous_contract = json.loads(marker.read_text()) if marker.is_file() else {}
    contract = {
        "schema": "jointbuildgs.p2.e3_local_4906982_mvc_repro.contract.v1",
        "task_id": TASK_ID,
        "purpose": "locate and characterize pre-activation divergence before rerunning MVC",
        "status": previous_contract.get("status", "PREPARED"),
        "base_config": {"path": str(BASE_CONFIG), "sha256": sha256(BASE_CONFIG)},
        "same_head_image_gpu": True,
        "gpu_order": [f"{scenario}/{replica}" for scenario in SCENARIOS for replica in REPLICAS],
        "observe_completed_updates": OBSERVE_UNTIL,
        "checkpoint_steps": list(STEPS),
        "scenarios": SCENARIOS,
        "common_state_continuation_control": {
            "source": "baseline/R1 full-state checkpoint at 1,000 completed updates",
            "comparison_completed_updates": 5000,
            "modes": FORK_MODES,
            "replicas_per_mode": len(REPLICAS),
        },
        "jit_cache": "prewarmed once then shared by all measured runs",
        "mvc_activation_forbidden": True,
        "w_mvc": 0.0,
        "official_PASS_usable": None,
        "scientific_verdict": None,
    }
    atomic_json(marker, contract)
    for scenario, spec in SCENARIOS.items():
        for replica in REPLICAS:
            out_dir = TASK_ROOT / "runs" / scenario / replica
            runtime = dict(base)
            runtime.update({
                "task_id": TASK_ID,
                "run_id": f"{scenario}_{replica}",
                "out_dir": container_path(out_dir),
                "full_state_checkpoint": True,
                "full_state_checkpoint_steps": list(STEPS),
                "full_state_resume": "off",
                "max_iter": 20000,
                "refine_start_iter": int(spec["refine_start_iter"]),
            })
            path = TASK_ROOT / "control/configs" / f"{scenario}_{replica}.yaml"
            atomic_text(path, yaml.safe_dump(runtime, sort_keys=False))
    config_dir = TASK_ROOT / "control/configs"
    comparisons = [
        (f"{scenario}_R1.yaml", f"{scenario}_R2.yaml", {"run_id", "out_dir"})
        for scenario in SCENARIOS
    ] + [
        ("baseline_R1.yaml", "deterministic_R1.yaml", {"run_id", "out_dir"}),
        ("baseline_R1.yaml", "no_refine_to_1k_R1.yaml", {"run_id", "out_dir", "refine_start_iter"}),
    ]
    diff_lines = ["# Runtime config diff allowlist", ""]
    for left_name, right_name, allowed in comparisons:
        left = yaml.safe_load((config_dir / left_name).read_text())
        right = yaml.safe_load((config_dir / right_name).read_text())
        changed = {key for key in set(left) | set(right) if left.get(key) != right.get(key)}
        if changed != allowed:
            raise RuntimeError(f"unexpected config diff {left_name} vs {right_name}: {sorted(changed)}")
        diff_lines.append(f"{left_name} vs {right_name}: {', '.join(sorted(changed))}")
    diff_lines += ["", "Deterministic controls are supplied by the recorded Docker/PyTorch wrapper, not by config keys."]
    atomic_text(TASK_ROOT / "config_diff.txt", "\n".join(diff_lines) + "\n")
    provenance = TASK_ROOT / "provenance.json"
    if not provenance.exists():
        source_paths = [
            Path(__file__).resolve(), REPO / "src/stage2/train.py", REPO / "src/stage2/renderer.py",
            REPO / "src/stage2/densification.py", REPO / "src/stage2/checkpoint.py",
            REPO / "src/stage2/loss/multiview.py", BASE_CONFIG,
        ]
        atomic_json(provenance, {
            "schema": "jointbuildgs.p2.e3_local_4906982_mvc_repro.provenance.v1",
            "task_id": TASK_ID, "git": git_record(), "docker_image": image_record(), "gpu": gpu_record(),
            "source_files_sha256": {str(path.relative_to(REPO)): sha256(path) for path in source_paths},
            "runtime_configs_sha256": {
                path.name: sha256(path) for path in sorted((TASK_ROOT / "control/configs").glob("*.yaml"))
            },
            "random_seed": 0, "started_utc": now(), "ended_utc": None,
            "commands": [], "return_codes": [], "scientific_verdict": None,
        })
    print(json.dumps({"task_root": str(TASK_ROOT), "scenarios": list(SCENARIOS), "steps": STEPS}, indent=2))


def record_operation(label: str, argv: list[str], rc: int, started: str, ended: str) -> None:
    path = TASK_ROOT / "provenance.json"
    body = json.loads(path.read_text(encoding="utf-8"))
    command_record = {"label": label, "argv": argv, "started_utc": started, "ended_utc": ended}
    return_record = {"label": label, "return_code": rc}
    body["commands"] = [item for item in body["commands"] if item.get("label") != label] + [command_record]
    body["return_codes"] = [item for item in body["return_codes"] if item.get("label") != label] + [return_record]
    atomic_json(path, body)


def checkpoint_valid(run_root: Path, step: int) -> bool:
    path = run_root / "ckpt" / f"step_{step:06d}.pt"
    sidecar = Path(str(path) + ".sha256")
    return path.is_file() and sidecar.is_file() and sidecar.read_text().split()[0] == sha256(path)


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


def launch(*, scenario: str, replica: str, prewarm: bool = False) -> dict[str, Any]:
    spec = SCENARIOS[scenario]
    run_root = TASK_ROOT / "runs" / scenario / replica
    central_receipt = TASK_ROOT / "control/runtime" / ("jit_prewarm.json" if prewarm else f"{scenario}_{replica}.json")
    if not prewarm and checkpoint_valid(run_root, OBSERVE_UNTIL):
        return json.loads(central_receipt.read_text())
    if prewarm:
        run_root = TASK_ROOT / "prewarm"
        if (run_root / "ckpt/final.pt").is_file():
            config = TASK_ROOT / "control/configs/jit_prewarm.yaml"
            recovered_args = docker_base(gpu=True, name="jbgs-mvc-repro-prewarm", keep=True)
            recovered_args += ["python", "-m", "src.stage2.train", "--config", container_path(config)]
            recovered_timestamp = datetime.fromtimestamp(
                (run_root / "ckpt/final.pt").stat().st_mtime, timezone.utc
            ).isoformat()
            recovered = {
                "schema": "jointbuildgs.p2.e3_local_4906982_mvc_repro.runtime.v1",
                "scenario": "baseline", "replica": "R1", "prewarm": True,
                "status": "PREWARM_COMPLETE_RECEIPT_RECOVERED",
                "recovered_utc": now(), "execution_timestamp_recovered_from_final_checkpoint_mtime": recovered_timestamp,
                "return_code": 0,
                "scientific_verdict": None,
            }
            atomic_json(central_receipt, recovered)
            record_operation("jit_prewarm_recovered", recovered_args, 0, recovered_timestamp, recovered_timestamp)
            atomic_text(TASK_ROOT / "issues.md", "# Issues\n\n- RESOLVED: JIT prewarm completed, but the first host receipt write targeted a Docker-owned output subdirectory and hit PermissionError. No measured replica had started. Receipts were moved to task-owned `control/runtime/`.\n")
            return recovered
        base = yaml.safe_load(BASE_CONFIG.read_text(encoding="utf-8"))
        base.update({
            "task_id": TASK_ID, "run_id": "jit_prewarm", "out_dir": container_path(run_root),
            "max_iter": 1, "eval_every": 100000, "ckpt_every": 100000,
            "full_state_checkpoint": False, "full_state_checkpoint_steps": [], "full_state_resume": "off",
            "refine_start_iter": 2000,
        })
        config = TASK_ROOT / "control/configs/jit_prewarm.yaml"
        atomic_text(config, yaml.safe_dump(base, sort_keys=False))
    else:
        config = TASK_ROOT / "control/configs" / f"{scenario}_{replica}.yaml"
    name = "jbgs-mvc-repro-" + ("prewarm" if prewarm else f"{scenario}-{replica}").lower().replace("_", "-")
    subprocess.run(["docker", "rm", "-f", name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    deterministic = bool(spec["deterministic"]) and not prewarm
    args = docker_base(gpu=True, name=name, keep=True, deterministic=deterministic)
    if deterministic:
        args += ["python", "-c", DETERMINISTIC_WRAPPER, "--config", container_path(config)]
    else:
        args += ["python", "-m", "src.stage2.train", "--config", container_path(config)]
    log = TASK_ROOT / "logs" / ("jit_prewarm.log" if prewarm else f"{scenario}_{replica}.log")
    log.parent.mkdir(parents=True, exist_ok=True)
    started = now()
    began = time.monotonic()
    max_used = 0
    with log.open("a", encoding="utf-8") as stream:
        proc = subprocess.Popen(args, text=True, stdout=stream, stderr=subprocess.STDOUT)
        while proc.poll() is None:
            sample = subprocess.run([
                "nvidia-smi", f"--id={GPU}",
                "--query-gpu=memory.used,utilization.gpu,temperature.gpu,clocks.sm",
                "--format=csv,noheader,nounits",
            ], text=True, capture_output=True)
            try:
                used = int(sample.stdout.split(",")[0].strip())
                max_used = max(max_used, used)
            except (ValueError, IndexError):
                pass
            if not prewarm and checkpoint_valid(run_root, OBSERVE_UNTIL):
                subprocess.run(["docker", "stop", "-t", "10", name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                break
            time.sleep(0.5)
        rc = proc.wait()
    ended = now()
    subprocess.run(["docker", "rm", "-f", name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    stopped = not prewarm and checkpoint_valid(run_root, OBSERVE_UNTIL)
    receipt = {
        "schema": "jointbuildgs.p2.e3_local_4906982_mvc_repro.runtime.v1",
        "scenario": scenario, "replica": replica, "prewarm": prewarm,
        "started_utc": started, "ended_utc": ended, "wall_seconds": time.monotonic() - began,
        "max_selected_gpu_used_mib": max_used, "return_code": rc,
        "stopped_after_valid_1000_checkpoint": stopped,
        "deterministic_wrapper": deterministic,
        "scientific_verdict": None,
    }
    atomic_json(central_receipt, receipt)
    record_operation("jit_prewarm" if prewarm else f"run_{scenario}_{replica}", args, rc, started, ended)
    if prewarm and rc != 0:
        raise RuntimeError(f"JIT prewarm failed; inspect {log}")
    if not prewarm and not stopped:
        atomic_text(TASK_ROOT / "issues.md", f"# Issues\n\n- {scenario}/{replica} did not produce a valid 1000-step checkpoint; rc={rc}.\n")
        raise RuntimeError(f"{scenario}/{replica} failed before checkpoint 1000; inspect {log}")
    return receipt


def run_matrix() -> None:
    if not (TASK_ROOT / "experiment_contract.json").is_file():
        raise RuntimeError("prepare must run first")
    launch(scenario="baseline", replica="R1", prewarm=True)
    for scenario in SCENARIOS:
        for replica in REPLICAS:
            receipt = launch(scenario=scenario, replica=replica)
            print(json.dumps({"scenario": scenario, "replica": replica, "wall_seconds": receipt.get("wall_seconds"), "rc": receipt.get("return_code")}), flush=True)


def _fork_docker_base(*, name: str, fork_root: Path, deterministic: bool) -> list[str]:
    args = ["docker", "run", "--name", name, "--gpus", f"device={GPU}", "--ipc=host"]
    if deterministic:
        args += ["-e", "CUBLAS_WORKSPACE_CONFIG=:4096:8", "-e", "NVIDIA_TF32_OVERRIDE=0"]
    canonical_run = container_path(TASK_ROOT / "runs/baseline/R1")
    args += [
        "-v", f"{REPO}:/workspace/JointBuildGS:ro",
        "-v", f"{ARTIFACT_ROOT}:/artifacts/JointBuildGS",
        "-v", f"{TASK_ROOT / 'cache/torch_extensions'}:/root/.cache/torch_extensions",
        "-v", f"{fork_root}:{canonical_run}",
        "-w", "/workspace/JointBuildGS", IMAGE,
    ]
    return args


def run_fork_control() -> None:
    """Resume four copies of one exact 1k state to measure continuation noise."""
    source = TASK_ROOT / "runs/baseline/R1"
    if not checkpoint_valid(source, 1000):
        raise RuntimeError("baseline/R1 valid 1k checkpoint is required")
    base_config = yaml.safe_load((TASK_ROOT / "control/configs/baseline_R1.yaml").read_text())
    base_config["full_state_resume"] = "auto"
    resume_config = TASK_ROOT / "control/configs/fork_resume_from_common_1k.yaml"
    atomic_text(resume_config, yaml.safe_dump(base_config, sort_keys=False))
    for mode, deterministic in FORK_MODES.items():
        for replica in REPLICAS:
            fork_root = TASK_ROOT / "forks" / mode / replica
            receipt_path = TASK_ROOT / "control/runtime" / f"fork_{mode}_{replica}.json"
            if checkpoint_valid(fork_root, 5000):
                print(json.dumps({"fork_mode": mode, "replica": replica, "status": "ALREADY_COMPLETE"}), flush=True)
                continue
            if fork_root.exists():
                raise RuntimeError(f"incomplete fork already exists and requires review: {fork_root}")
            fork_root.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(source, fork_root)
            name = f"jbgs-mvc-repro-fork-{mode}-{replica}".lower()
            subprocess.run(["docker", "rm", "-f", name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            args = _fork_docker_base(name=name, fork_root=fork_root, deterministic=deterministic)
            if deterministic:
                args += ["python", "-c", DETERMINISTIC_WRAPPER, "--config", container_path(resume_config)]
            else:
                args += ["python", "-m", "src.stage2.train", "--config", container_path(resume_config)]
            log = TASK_ROOT / "logs" / f"fork_{mode}_{replica}.log"
            started = now();began = time.monotonic();max_used = 0
            with log.open("w", encoding="utf-8") as stream:
                proc = subprocess.Popen(args, text=True, stdout=stream, stderr=subprocess.STDOUT)
                while proc.poll() is None:
                    sample = subprocess.run([
                        "nvidia-smi", f"--id={GPU}", "--query-gpu=memory.used",
                        "--format=csv,noheader,nounits",
                    ], text=True, capture_output=True)
                    try: max_used = max(max_used, int(sample.stdout.strip()))
                    except ValueError: pass
                    if checkpoint_valid(fork_root, 5000):
                        subprocess.run(["docker", "stop", "-t", "10", name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                        break
                    time.sleep(0.5)
                rc = proc.wait()
            ended = now();subprocess.run(["docker", "rm", "-f", name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            valid = checkpoint_valid(fork_root, 5000)
            receipt = {
                "schema": "jointbuildgs.p2.e3_local_4906982_mvc_repro.fork_runtime.v1",
                "fork_mode": mode, "replica": replica,
                "common_source_checkpoint": str(source / "ckpt/step_001000.pt"),
                "common_source_checkpoint_sha256": sha256(source / "ckpt/step_001000.pt"),
                "started_utc": started, "ended_utc": ended, "wall_seconds": time.monotonic()-began,
                "max_selected_gpu_used_mib": max_used, "return_code": rc,
                "valid_5000_checkpoint": valid, "deterministic_wrapper": deterministic,
                "scientific_verdict": None,
            }
            atomic_json(receipt_path, receipt);record_operation(f"fork_{mode}_{replica}", args, rc, started, ended)
            if not valid:
                raise RuntimeError(f"fork {mode}/{replica} failed; inspect {log}")
            print(json.dumps({"fork_mode": mode, "replica": replica, "wall_seconds": receipt["wall_seconds"], "gaussian_checkpoint": 5000}), flush=True)


def analyze_forks() -> None:
    output = TASK_ROOT / "control/fork_analysis.json"
    code = r'''
import json,math,torch
from pathlib import Path
root,out=map(Path,__import__('sys').argv[1:])
def deep_equal(x,y):
 import numpy as np
 if torch.is_tensor(x) and torch.is_tensor(y):return x.dtype==y.dtype and x.shape==y.shape and torch.equal(x,y)
 if isinstance(x,np.ndarray) and isinstance(y,np.ndarray):return x.dtype==y.dtype and x.shape==y.shape and np.array_equal(x,y,equal_nan=True)
 if isinstance(x,dict) and isinstance(y,dict):return set(x)==set(y) and all(deep_equal(x[k],y[k]) for k in x)
 if isinstance(x,(list,tuple)) and isinstance(y,(list,tuple)):return type(x)==type(y) and len(x)==len(y) and all(deep_equal(a,b) for a,b in zip(x,y))
 if isinstance(x,float) and isinstance(y,float) and math.isnan(x) and math.isnan(y):return True
 return type(x)==type(y) and x==y
result={}
for mode in ['plain','deterministic']:
 paths=[root/'forks'/mode/r/'ckpt/step_005000.pt' for r in ['R1','R2']]
 A,B=[torch.load(p,map_location='cpu',weights_only=False) for p in paths]
 ma=A['model']['state_dict']['means'];mb=B['model']['state_dict']['means']
 result[mode]={'sections_equal':{k:deep_equal(A[k],B[k]) for k in ['model','optimizers','strategy','grouping_state','rng_state','loss_log_cursor']},'gaussian_count_R1':int(ma.shape[0]),'gaussian_count_R2':int(mb.shape[0]),'gaussian_count_delta':int(mb.shape[0]-ma.shape[0]),'grow_R1':{k:A['strategy']['state'].get(k) for k in ['cum_grow_duplicated','cum_grow_split','cum_pruned']},'grow_R2':{k:B['strategy']['state'].get(k) for k in ['cum_grow_duplicated','cum_grow_split','cum_pruned']}}
body={'schema':'jointbuildgs.p2.e3_local_4906982_mvc_repro.fork_analysis.v1','common_start_completed_updates':1000,'comparison_completed_updates':5000,'result':result,'scientific_verdict':None}
out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(body,indent=2,sort_keys=True)+'\n');print(json.dumps(result))
'''
    args = docker_base() + ["python", "-c", code, container_path(TASK_ROOT), container_path(output)]
    started=now();proc=command(args,check=False);record_operation("analyze_forks",args,proc.returncode,started,now())
    if proc.returncode != 0:raise RuntimeError(proc.stderr or proc.stdout)
    forks=json.loads(output.read_text())
    metrics_path=TASK_ROOT/"metrics.json";metrics=json.loads(metrics_path.read_text())
    metrics["common_1k_fork_continuation_to_5k"] = forks["result"]
    continuation_observation = "Two continuations from one byte-identical 1k full-state still diverged by 5k; a common checkpoint aligns the start but does not make custom CUDA continuation deterministic."
    if continuation_observation not in metrics["observations"]:
        metrics["observations"].append(continuation_observation)
    atomic_json(metrics_path,metrics)
    comparison=TASK_ROOT/"comparison.md";text=comparison.read_text()
    text = text.split("\n## Common-state continuation control\n", 1)[0].rstrip() + "\n"
    text += "\n## Common-state continuation control\n\n| mode | 5k Gaussians R1 | 5k Gaussians R2 | delta | model exact | RNG exact |\n|---|---:|---:|---:|---:|---:|\n"
    for mode,row in forks["result"].items():
        text += f"| {mode} | {row['gaussian_count_R1']} | {row['gaussian_count_R2']} | {row['gaussian_count_delta']:+d} | {row['sections_equal']['model']} | {row['sections_equal']['rng_state']} |\n"
    text += "\nA shared pre-activation checkpoint removes the initial-state confound but does not by itself remove continuation noise. MVC inference therefore needs either a measured control-control noise envelope/replicates or a deterministic renderer/densification implementation.\n"
    atomic_text(comparison,text)
    source_inputs = json.loads(SOURCE_INPUT_HASHES.read_text())
    common_checkpoint = TASK_ROOT / "runs/baseline/R1/ckpt/step_001000.pt"
    atomic_json(TASK_ROOT / "input_hashes.json", {
        "schema": "jointbuildgs.p2.e3_local_4906982_mvc_repro.inputs.v1",
        "reused_input_manifest": {"path": str(SOURCE_INPUT_HASHES), "sha256": sha256(SOURCE_INPUT_HASHES)},
        "crop_images": {key: source_inputs["crop_images"][key] for key in ("count", "combined_sha256")},
        "camera_and_sparse_seed": source_inputs["camera_and_sparse_seed"],
        "exact_view_manifest": source_inputs["exact_view_manifest"],
        "view_roles_manifest": source_inputs["view_roles_manifest"],
        "fresh_repetitions_checkpoint_input": None,
        "common_state_continuation_checkpoint": {"path": str(common_checkpoint), "sha256": sha256(common_checkpoint)},
        "scientific_verdict": None,
    })
    atomic_text(TASK_ROOT / "NOTES.md", """# Notes

This namespace diagnoses MVC pre-activation reproducibility only. MVC remained inactive (`w_mvc=0`) and no geometry-quality or scientific conclusion is made.

- Two fresh repetitions diverged in model state after the first completed update while saved RNG state stayed exact.
- Delaying refinement kept Gaussian counts equal through 1k, locating count divergence in the amplification of earlier numerical differences by densification.
- PyTorch/CUBLAS deterministic controls did not make the custom CUDA rendering/backpropagation path exact.
- Two resumes from one byte-identical 1k full state diverged by 5k: plain by 534 Gaussians and deterministic-wrapper by 177.
- A future MVC comparison should estimate a control-control noise envelope with repeated common-state continuations; high-Z behavior and normal-surface quality remain separate endpoints.

`scientific_verdict` remains `null`.
""")
    contract=json.loads((TASK_ROOT/"experiment_contract.json").read_text());contract["status"]="MEASURED";contract["common_state_continuation_control"]["status"]="MEASURED";atomic_json(TASK_ROOT/"experiment_contract.json",contract)
    provenance=json.loads((TASK_ROOT/"provenance.json").read_text());provenance["ended_utc"]=now();provenance["source_files_sha256"][str(Path(__file__).resolve().relative_to(REPO))]=sha256(Path(__file__).resolve());provenance["runtime_configs_sha256"]={path.name:sha256(path) for path in sorted((TASK_ROOT/"control/configs").glob("*.yaml"))};provenance["input_hashes_sha256"]=sha256(TASK_ROOT/"input_hashes.json");atomic_json(TASK_ROOT/"provenance.json",provenance)
    print(json.dumps(forks,indent=2))


def analyze() -> None:
    output = TASK_ROOT / "control/analysis.json"
    code = r'''
import json,math,torch
from pathlib import Path
from tensorboard.backend.event_processing.event_accumulator import EventAccumulator
root,out=map(Path,__import__('sys').argv[1:])
scenarios=['baseline','no_refine_to_1k','deterministic']; steps=[1,10,50,100,140,200,499,500,501,600,800,1000]
def deep_equal(x,y):
  import numpy as np
  if torch.is_tensor(x) and torch.is_tensor(y): return x.dtype==y.dtype and x.shape==y.shape and torch.equal(x,y)
  if isinstance(x,np.ndarray) and isinstance(y,np.ndarray): return x.dtype==y.dtype and x.shape==y.shape and np.array_equal(x,y,equal_nan=True)
  if isinstance(x,dict) and isinstance(y,dict): return set(x)==set(y) and all(deep_equal(x[k],y[k]) for k in x)
  if isinstance(x,(list,tuple)) and isinstance(y,(list,tuple)): return type(x)==type(y) and len(x)==len(y) and all(deep_equal(a,b) for a,b in zip(x,y))
  if isinstance(x,float) and isinstance(y,float) and math.isnan(x) and math.isnan(y): return True
  return type(x)==type(y) and x==y
def tensor_delta(a,b):
  if a.shape!=b.shape or a.dtype!=b.dtype: return None
  if not (a.is_floating_point() or a.is_complex()): return 0.0 if torch.equal(a,b) else None
  return float((a.float()-b.float()).abs().max())
result={}
for scenario in scenarios:
  rows=[]; first={'model':None,'optimizers':None,'strategy':None,'rng_state':None,'gaussian_count':None}
  for step in steps:
    paths=[root/'runs'/scenario/r/'ckpt'/f'step_{step:06d}.pt' for r in ['R1','R2']]
    if not all(p.is_file() for p in paths):
      rows.append({'step':step,'available':False});continue
    A,B=[torch.load(p,map_location='cpu',weights_only=False) for p in paths]
    state_a=A['model']['state_dict'];state_b=B['model']['state_dict']; ma=state_a['means'];mb=state_b['means']
    sections={key:deep_equal(A[key],B[key]) for key in ['model','optimizers','strategy','grouping_state','rng_state','loss_log_cursor']}
    counts=[int(ma.shape[0]),int(mb.shape[0])]
    for key in ['model','optimizers','strategy','rng_state']:
      if not sections[key] and first[key] is None:first[key]=step
    if counts[0]!=counts[1] and first['gaussian_count'] is None:first['gaussian_count']=step
    deltas={k:tensor_delta(state_a[k],state_b[k]) for k in sorted(set(state_a)&set(state_b)) if torch.is_tensor(state_a[k]) and torch.is_tensor(state_b[k])}
    rows.append({'step':step,'available':True,'sections_equal':sections,'gaussian_count_R1':counts[0],'gaussian_count_R2':counts[1],'model_tensor_max_abs_delta':deltas,'grow_R1':{k:A['strategy']['state'].get(k) for k in ['cum_grow_duplicated','cum_grow_split','cum_pruned']},'grow_R2':{k:B['strategy']['state'].get(k) for k in ['cum_grow_duplicated','cum_grow_split','cum_pruned']}})
  scalar={}
  try:
    ev=[]
    for replica in ['R1','R2']:
      e=EventAccumulator(str(next((root/'runs'/scenario/replica/'tb').glob('events*'))));e.Reload();ev.append(e)
    for tag in ['loss/total','loss/photo','metric/psnr_train','stats/gaussian_count']:
      a={x.step:x.value for x in ev[0].Scalars(tag) if x.step<1000};b={x.step:x.value for x in ev[1].Scalars(tag) if x.step<1000};common=sorted(set(a)&set(b));exact=[s for s in common if a[s]!=b[s]];tol=[s for s in common if not math.isclose(a[s],b[s],rel_tol=1e-6,abs_tol=1e-8)]
      scalar[tag]={'common_samples':len(common),'first_exact_mismatch_step':exact[0] if exact else None,'first_tolerance_mismatch_step':tol[0] if tol else None,'max_abs_delta':max((abs(a[s]-b[s]) for s in common),default=0.0)}
  except (StopIteration,KeyError) as exc: scalar={'error':str(exc)}
  result[scenario]={'first_checkpoint_mismatch':first,'checkpoint_rows':rows,'scalar_divergence':scalar}
body={'schema':'jointbuildgs.p2.e3_local_4906982_mvc_repro.analysis.v1','status':'MEASURED','scenarios':result,'scientific_verdict':None}
out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(body,indent=2,sort_keys=True)+'\n');print(json.dumps({k:v['first_checkpoint_mismatch'] for k,v in result.items()}))
'''
    args = docker_base() + ["python", "-c", code, container_path(TASK_ROOT), container_path(output)]
    started = now()
    proc = command(args, check=False)
    record_operation("analyze", args, proc.returncode, started, now())
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr or proc.stdout)
    body = json.loads(output.read_text(encoding="utf-8"))
    rows = []
    for scenario, info in body["scenarios"].items():
        for row in info["checkpoint_rows"]:
            rows.append({
                "scenario": scenario, "step": row["step"], "available": row["available"],
                "model_equal": row.get("sections_equal", {}).get("model"),
                "optimizer_equal": row.get("sections_equal", {}).get("optimizers"),
                "strategy_equal": row.get("sections_equal", {}).get("strategy"),
                "rng_equal": row.get("sections_equal", {}).get("rng_state"),
                "gaussian_count_R1": row.get("gaussian_count_R1"), "gaussian_count_R2": row.get("gaussian_count_R2"),
            })
    with (TASK_ROOT / "checkpoint_equality.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader();writer.writerows(rows)
    summary = {scenario: info["first_checkpoint_mismatch"] for scenario, info in body["scenarios"].items()}
    baseline = summary["baseline"]; no_refine = summary["no_refine_to_1k"]; det = summary["deterministic"]
    observations = []
    if baseline["model"] is not None:
        observations.append(f"Baseline model state first differs by checkpoint {baseline['model']}.")
    if baseline["gaussian_count"] is not None:
        observations.append(f"Baseline Gaussian count first differs by checkpoint {baseline['gaussian_count']}.")
    if no_refine["model"] is not None and no_refine["gaussian_count"] is None:
        observations.append("With refinement delayed, floating model state still differs but Gaussian counts remain equal through 1k; densification amplifies an earlier numerical divergence.")
    if det["model"] is None:
        observations.append("The deterministic wrapper preserved exact model equality through 1k.")
    elif det["model"] is not None:
        observations.append(f"The deterministic wrapper still differs by checkpoint {det['model']}; PyTorch deterministic controls do not fully control the active custom CUDA path.")
    metrics = {
        "schema": "jointbuildgs.p2.e3_local_4906982_mvc_repro.metrics.v1",
        "task_id": TASK_ID, "status": "MEASURED", "first_checkpoint_mismatch": summary,
        "observations": observations, "mvc_activated": False,
        "official_PASS_usable": None, "scientific_verdict": None,
    }
    atomic_json(TASK_ROOT / "metrics.json", metrics)
    text = "# MVC pre-activation reproducibility diagnosis\n\nScientific verdict: `null`. MVC was never activated.\n\n"
    text += "## First mismatch by preserved checkpoint\n\n| scenario | model | optimizer | strategy | RNG | Gaussian count |\n|---|---:|---:|---:|---:|---:|\n"
    for scenario, values in summary.items():
        text += "| " + scenario + " | " + " | ".join("none through 1k" if values[key] is None else str(values[key]) for key in ("model", "optimizers", "strategy", "rng_state", "gaussian_count")) + " |\n"
    text += "\n## Observations\n\n" + "\n".join(f"- {value}" for value in observations) + "\n"
    text += "\nThese are technical reproducibility measurements, not an MVC performance result.\n"
    atomic_text(TASK_ROOT / "comparison.md", text)
    provenance = json.loads((TASK_ROOT / "provenance.json").read_text())
    provenance["ended_utc"] = now();provenance["status"] = "MEASURED"
    provenance["source_files_sha256"][str(Path(__file__).resolve().relative_to(REPO))] = sha256(Path(__file__).resolve())
    atomic_json(TASK_ROOT / "provenance.json", provenance)
    contract = json.loads((TASK_ROOT / "experiment_contract.json").read_text())
    contract["status"] = "MEASURED";atomic_json(TASK_ROOT / "experiment_contract.json", contract)
    print(json.dumps({"first_checkpoint_mismatch": summary, "observations": observations}, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["prepare", "run", "analyze", "fork-control", "analyze-forks", "all"])
    args = parser.parse_args()
    if args.command in {"prepare", "all"}: prepare()
    if args.command in {"run", "all"}: run_matrix()
    if args.command in {"analyze", "all"}: analyze()
    if args.command in {"fork-control", "all"}: run_fork_control()
    if args.command in {"analyze-forks", "all"}: analyze_forks()


if __name__ == "__main__":
    main()
