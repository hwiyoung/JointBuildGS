#!/usr/bin/env python3
"""Run S2 full-scene arms branched from the sealed new-E3 7000 full-state.

Same harness path as S1 (binding probe with full_state block intact ->
checkpoint rebind -> deterministic docker training), one process per GPU:
`--gpu 0` runs E4_V2_STATIC, `--gpu 1` runs E5_V2_F1.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

REPO = Path(__file__).resolve().parents[3]
ARTIFACT_ROOT = REPO.parent / "JointBuildGS-artifacts"
COMMON = REPO / "configs/p2/e4_e6_redesign_s2_v1/s2_v1.yaml"
TASK_ID = "P2-E4-E6-REDESIGN-S2-v1"
TASK_ROOT = ARTIFACT_ROOT / "phase-payloads/p2/e4_e6_redesign_s2_v1" / TASK_ID


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


surface = load_module("mvs_surface_runner_for_s2", REPO / "scripts/p2/e3_local_4906982_mvs_surface_depth_v1/run.py")
depth_runner = surface.depth_runner
base = surface.base
base.TASK_ID = TASK_ID
base.TASK_ROOT = TASK_ROOT
PROVENANCE_SUFFIX = ""


def _isolated_record_operation(label: str, argv: list[str], rc: int, started: str, ended: str) -> None:
    path = TASK_ROOT / f"provenance{PROVENANCE_SUFFIX}.json"
    if not path.is_file():
        atomic_json(path, {"schema": "jointbuildgs.p2.e4_e6_redesign_s2_v1.provenance.v1", "task_id": TASK_ID, "commands": [], "return_codes": [], "scientific_verdict": None})
    body = json.loads(path.read_text(encoding="utf-8"))
    body["commands"].append({"label": label, "argv": argv, "started_utc": started, "ended_utc": ended})
    body["return_codes"].append({"label": label, "return_code": rc})
    atomic_json(path, body)


base.record_operation = _isolated_record_operation


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
    temporary.replace(path)


def ensure_task_owner() -> None:
    subprocess.run(
        base.docker_base() + ["chown", "-R", f"{os.getuid()}:{os.getgid()}", base.container_path(TASK_ROOT)],
        check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )


def ensure_warm_cache() -> None:
    cache = TASK_ROOT / "cache/torch_extensions/py311_cu121/gsplat_cuda"
    if cache.is_dir():
        return
    warm = ARTIFACT_ROOT / "phase-payloads/p2/e4_local_4906982_55v_als_prior_v1/P2-E4-LOCAL-4906982-55V-ALS-PRIOR-v1/cache/torch_extensions"
    if not warm.is_dir():
        raise RuntimeError("warm gsplat torch_extensions cache missing")
    target = TASK_ROOT / "cache"
    target.mkdir(parents=True, exist_ok=True)
    subprocess.run(["cp", "-r", str(warm), str(target)], check=True)


def arm_runtime_config(common: dict[str, Any], arm: str) -> dict[str, Any]:
    spec = common["arms"][arm]
    arm_common = common["arm_common"]
    cfg = yaml.safe_load((REPO / common["base_training_config"]).read_text(encoding="utf-8"))
    run_root = TASK_ROOT / "arms" / arm / "R1"
    cfg.update({
        "task_id": TASK_ID,
        "run_id": f"{arm}_R1",
        "out_dir": base.container_path(run_root),
        "external_als_prior_dir": base.container_path(TASK_ROOT / "prior" / spec["prior"]),
        "w_external_als_depth": float(spec["w_depth"]),
        "w_external_als_normal": float(spec["w_normal"]),
        "external_als_huber_delta_m": float(arm_common["external_als_huber_delta_m"]),
        "external_als_normalization": str(arm_common["external_als_normalization"]),
        "max_iter": int(arm_common["max_iter"]),
        "full_state_checkpoint": True,
        "full_state_checkpoint_steps": list(arm_common["checkpoints"]),
        "full_state_resume": "auto",
        "full_state_resume_strict_cuda_rng": True,
    })
    if spec.get("alpha_gate") is not None:
        cfg["external_als_alpha_gate"] = float(spec["alpha_gate"])
    return cfg


def runtime_path(arm: str) -> Path:
    return TASK_ROOT / "control/runtime_configs" / f"{arm.lower()}_r1.yaml"


def write_runtime(common: dict[str, Any], arm: str) -> Path:
    path = runtime_path(arm)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(arm_runtime_config(common, arm), sort_keys=True), encoding="utf-8")
    return path


def binding_probe(common: dict[str, Any], arm: str) -> Path:
    effective = TASK_ROOT / "control/effective_configs" / f"{arm.lower()}.json"
    if effective.is_file():
        return effective
    cfg = arm_runtime_config(common, arm)
    probe_root = TASK_ROOT / "probe" / arm
    cfg.update({
        "run_id": f"BINDING_PROBE_{arm}",
        "out_dir": base.container_path(probe_root),
        "max_iter": 1,
        "eval_every": 1000000,
        "ckpt_every": 1000000,
        "full_state_resume": "off",
    })
    probe_cfg = TASK_ROOT / "control/runtime_configs" / f"probe_{arm.lower()}.yaml"
    probe_cfg.parent.mkdir(parents=True, exist_ok=True)
    probe_cfg.write_text(yaml.safe_dump(cfg, sort_keys=True), encoding="utf-8")
    argv = base.docker_base(gpu=True) + ["python", "-c", base.DETERMINISTIC_WRAPPER, "--config", base.container_path(probe_cfg)]
    started = base.now()
    proc = subprocess.run([str(x) for x in argv], text=True, capture_output=True)
    base.record_operation(f"binding_probe_{arm}", [str(x) for x in argv], proc.returncode, started, base.now())
    if proc.returncode != 0:
        raise RuntimeError(f"binding probe failed for {arm}: {proc.stderr[-2000:] or proc.stdout[-2000:]}")
    body = json.loads((probe_root / "effective_config.json").read_text(encoding="utf-8"))
    body.pop("full_state_runtime", None)
    atomic_json(effective, body)
    return effective


def rebind(common: dict[str, Any], arm: str, source_checkpoint: Path) -> None:
    run_root = TASK_ROOT / "arms" / arm / "R1"
    receipt = TASK_ROOT / "control/receipts" / f"rebind_{arm.lower()}.json"
    if receipt.is_file() and json.loads(receipt.read_text()).get("passed") and base.checkpoint_valid(run_root, 7000):
        return
    destination = run_root / "ckpt/step_007000.pt"
    destination.parent.mkdir(parents=True, exist_ok=True)
    argv = base.docker_base() + [
        "python", "-c", depth_runner.REBIND_CODE,
        base.container_path(source_checkpoint), base.container_path(destination),
        base.container_path(runtime_path(arm)), Path(base.container_path(run_root)),
        base.container_path(TASK_ROOT / "control/effective_configs" / f"{arm.lower()}.json"),
        base.container_path(receipt),
    ]
    started = base.now()
    proc = subprocess.run([str(x) for x in argv], text=True, capture_output=True)
    base.record_operation(f"rebind_{arm}", [str(x) for x in argv], proc.returncode, started, base.now())
    if proc.returncode != 0:
        raise RuntimeError(f"rebind failed for {arm}: {proc.stderr[-2000:] or proc.stdout[-2000:]}")


def main() -> None:
    global PROVENANCE_SUFFIX
    parser = argparse.ArgumentParser()
    parser.add_argument("--gpu", required=True, choices=("0", "1"))
    args = parser.parse_args()
    PROVENANCE_SUFFIX = f"_gpu{args.gpu}"
    common = yaml.safe_load(COMMON.read_text(encoding="utf-8"))

    prior_receipt = TASK_ROOT / "control/200-s2-prior-preflight-passed.json"
    if not json.loads(prior_receipt.read_text(encoding="utf-8")).get("leak_qa_passed"):
        raise RuntimeError("S2 prior preflight must pass before training")

    source_run = ARTIFACT_ROOT / common["source_run"]
    source_checkpoint = source_run / f"ckpt/step_{int(common['source_checkpoint_step']):06d}.pt"
    if not base.checkpoint_valid(source_run, int(common["source_checkpoint_step"])):
        raise RuntimeError("source full-scene E3 checkpoint 7000 failed validation")

    ensure_warm_cache()
    arms = [arm for arm, spec in common["arms"].items() if str(spec["gpu"]) == args.gpu]
    results = {}
    for arm in arms:
        base.GPU = str(common["arms"][arm]["gpu"])
        write_runtime(common, arm)
        binding_probe(common, arm)
        rebind(common, arm, source_checkpoint)
        ensure_task_owner()
        label = f"train_{arm}_R1"
        final_step = int(common["arm_common"]["max_iter"])
        receipt = TASK_ROOT / "control/receipts" / f"{label}.json"
        if not base.checkpoint_valid(TASK_ROOT / "arms" / arm / "R1", final_step):
            outcome = base._launch_training(label, TASK_ROOT / "arms" / arm / "R1", runtime_path(arm), stop_step=final_step)
        else:
            outcome = json.loads(receipt.read_text()) if receipt.is_file() else {"status": "ALREADY_COMPLETE"}
        ensure_task_owner()
        results[arm] = {
            "wall_seconds": outcome.get("wall_seconds"),
            "checkpoint_final_valid": base.checkpoint_valid(TASK_ROOT / "arms" / arm / "R1", final_step),
        }
        print(json.dumps({arm: results[arm]}), flush=True)
    atomic_json(TASK_ROOT / f"control/gpu{args.gpu}_training_summary.json", {
        "schema": "jointbuildgs.p2.e4_e6_redesign_s2_v1.training_summary.v1",
        "task_id": TASK_ID,
        "gpu": args.gpu,
        "completed_utc": datetime.now(timezone.utc).isoformat(),
        "arms": results,
        "scientific_verdict": None,
    })
    print(json.dumps({"gpu": args.gpu, "arms": results}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
