#!/usr/bin/env python3
"""Materialize the bounded DN-Splatter depth-only transfer arm."""
from __future__ import annotations

from datetime import datetime, timezone
import difflib
import hashlib
import json
import os
from pathlib import Path
import subprocess

import yaml


REPO = Path("/workspace/JointBuildGS")
AR = Path("/artifacts/JointBuildGS")
TASK_ID = "P2-E3-LOCAL-4906982-DN-SPLATTER-DEPTH-ONLY-v1"
ROOT = AR / "phase-payloads/p2/e3_local_4906982_dn_splatter_depth_only_v1" / TASK_ID
CFG = REPO / "configs/p2/e3_local_4906982_dn_splatter_depth_only_v1"
CHECKPOINTS = (7000, 12000, 15000, 20000)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def atomic_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(value)
    os.replace(tmp, path)


def atomic_json(path: Path, body: object) -> None:
    atomic_text(path, json.dumps(body, indent=2, sort_keys=True) + "\n")


def git(*args: str) -> str:
    return subprocess.check_output(
        ["git", "-c", f"safe.directory={REPO}", *args], cwd=REPO, text=True
    ).strip()


def main() -> None:
    common = yaml.safe_load((CFG / "common.yaml").read_text())
    arm = yaml.safe_load((CFG / "dn_depth.yaml").read_text())
    source = Path(common["source_control_config"])
    base = yaml.safe_load(source.read_text())
    resolved = dict(base)
    resolved.update(arm["overrides"])
    resolved["out_dir"] = arm["out_dir"]

    required = {
        "seed": 0, "load_depth": True, "load_normal": False,
        "depth_supervision_mode": "expected",
        "depth_loss_type": "dn_edge_aware_log_l1", "depth_valid_min": 0.1,
        "w_depth": 0.2, "depth_schedule": "constant", "depth_warmup": 0,
        "depth_ramp_steps": 0, "w_normal": 0.0, "w_mono_depth": 0.0,
        "w_mvc": 0.0, "w_nc": 0.05, "w_distort": 0.0,
        "normal_consistency_mode": "official_2dgs",
        "surface_normal_depth_mode": "surface_intersection_expected",
        "max_iter": 20000, "full_state_checkpoint_steps": list(CHECKPOINTS),
        "scientific_verdict": None,
    }
    mismatch = {k: [resolved.get(k), v] for k, v in required.items() if resolved.get(k) != v}
    if mismatch:
        raise RuntimeError(f"resolved DN config mismatch: {mismatch}")
    if len(resolved["visible_views"]) != 55 or len(resolved["train_views"]) != 47 or len(resolved["eval_views"]) != 8:
        raise RuntimeError("fixed 55/47/8 view gate failed")
    forbidden = {
        k: resolved.get(k) for k in (
            "w_normal", "w_mono_depth", "w_mono_normal", "w_external_als_depth",
            "w_external_als_normal", "w_lod_prior", "w_sem", "w_mutual",
            "w_structure", "w_mvc", "w_distort",
        ) if float(resolved.get(k, 0.0) or 0.0) != 0.0
    }
    if forbidden:
        raise RuntimeError(f"forbidden auxiliary objectives: {forbidden}")

    runtime = ROOT / "control/runtime_configs/dn_depth_r1.yaml"
    atomic_text(runtime, yaml.safe_dump(resolved, sort_keys=False))
    smoke = dict(resolved)
    smoke.update({
        "run_id": "DN_DEPTH_SMOKE", "out_dir": str(ROOT / "smoke/DN_DEPTH"),
        "max_iter": 12, "eval_every": 100000, "ckpt_every": 100000,
        "full_state_checkpoint": False, "full_state_checkpoint_steps": [],
        "full_state_resume": "off", "refine_start_iter": 500,
        "loss_grad_audit_every": 1,
    })
    smoke_path = ROOT / "control/runtime_configs/dn_depth_smoke.yaml"
    atomic_text(smoke_path, yaml.safe_dump(smoke, sort_keys=False))

    diff = "".join(difflib.unified_diff(
        yaml.safe_dump(base, sort_keys=True).splitlines(True),
        yaml.safe_dump(resolved, sort_keys=True).splitlines(True),
        fromfile=str(source), tofile=str(runtime),
    ))
    atomic_text(ROOT / "config_diff.txt", diff)
    prior_hashes = json.loads(Path(common["source_input_hashes"]).read_text())
    atomic_json(ROOT / "input_hashes.json", prior_hashes)

    status = git("status", "--porcelain=v1")
    now = datetime.now(timezone.utc).isoformat()
    contract = {
        "schema": "jointbuildgs.p2.e3_local_4906982_dn_splatter_depth_only_v1.contract.v1",
        "task_id": TASK_ID, "status": "PREFLIGHT_BOUND",
        "causal_question": "Does DN-Splatter-style external depth improve the existing gsplat 2D surface base?",
        "comparator": common["source_control_metrics"],
        "new_training_arms_allowed": ["DN_DEPTH"], "new_training_arms_started": [],
        "depth_prediction": "gsplat RGB+ED expected depth",
        "depth_objective": "0.2 * EdgeAwareLogL1",
        "valid_rule": "raw COLMAP geometric depth > 0.1 m and finite",
        "schedule": "constant from update 1",
        "reference_code_discrepancy": "Pinned main get_depth_loss returns (1+lambda)*loss although README calls lambda a weight; this transfer uses the documented/paper-intended lambda*loss semantics.",
        "excluded": ["normal supervision", "scale loss addition", "confidence filtering", "AGS-Mesh", "MVC", "distortion", "external priors", "semantic supervision"],
        "LoD2_usage": "evaluation-only except frozen standard GroundSurface XY and stable ID",
        "scientific_verdict": None,
    }
    atomic_json(ROOT / "experiment_contract.json", contract)
    atomic_json(ROOT / "provenance.json", {
        "schema": "jointbuildgs.provenance.v1", "task_id": TASK_ID,
        "git_commit": git("rev-parse", "HEAD"), "git_branch": git("branch", "--show-current"),
        "git_dirty": bool(status), "git_status_porcelain": status.splitlines(),
        "source_sha256": {
            str(p.relative_to(REPO)): sha256(p) for p in (
                REPO / "src/stage2/train.py", REPO / "src/stage2/loss/depth_reference.py",
                REPO / "src/stage2/renderer.py", REPO / "src/stage2/dataloader.py",
            )
        },
        "config_sha256": {p.name: sha256(p) for p in CFG.glob("*.yaml")},
        "runtime_config": str(runtime), "runtime_config_sha256": sha256(runtime),
        "docker_image": "jointbuildgs:dev", "gpu_requested": 1, "random_seed": 0,
        "started_utc": now, "ended_utc": None, "commands": [], "return_codes": [],
        "scientific_verdict": None,
    })
    atomic_text(ROOT / "NOTES.md", "# DN-Splatter depth-only\n\nOne new arm ports only expected-depth EdgeAwareLogL1 onto the existing gsplat 2D surface control. Normal, scale, confidence filtering, MVC, and external priors are excluded. `scientific_verdict` remains null.\n")
    atomic_text(ROOT / "issues.md", "# Issues\n\n- Initial host-side reference read used the container-only `/artifacts` path and failed without modifying data; the host backend path was then resolved read-only.\n- Pinned DN-Splatter main applies `depth_loss += lambda * depth_loss`, inconsistent with README weight semantics. The bounded transfer uses `lambda * loss` and records this adaptation.\n")
    atomic_json(ROOT / "control/preflight_gate.json", {
        "passed": True, "runtime_config": str(runtime), "runtime_config_sha256": sha256(runtime),
        "source_control_config": str(source), "source_control_config_sha256": sha256(source),
        "view_counts": {"visible": 55, "train": 47, "held_out": 8},
        "scientific_verdict": None,
    })
    print(json.dumps({"passed": True, "runtime": str(runtime), "smoke": str(smoke_path)}, indent=2))


if __name__ == "__main__":
    main()
