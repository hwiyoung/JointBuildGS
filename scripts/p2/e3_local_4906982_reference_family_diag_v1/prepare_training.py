#!/usr/bin/env python3
"""Materialize and validate the single allowed reference-family training arm."""
from __future__ import annotations

import difflib
import hashlib
import json
import os
from pathlib import Path

import yaml


REPO = Path("/workspace/JointBuildGS")
ARTIFACT_ROOT = Path("/artifacts/JointBuildGS")
TASK_ID = "P2-E3-LOCAL-4906982-REFERENCE-FAMILY-DIAG-v1"
TASK_ROOT = (
    ARTIFACT_ROOT
    / "phase-payloads/p2/e3_local_4906982_reference_family_diag_v1"
    / TASK_ID
)
CONFIG_DIR = REPO / "configs/p2/e3_local_4906982_reference_family_diag_v1"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(value)
    os.replace(tmp, path)


def atomic_json(path: Path, body: object) -> None:
    atomic_text(path, json.dumps(body, indent=2, sort_keys=True) + "\n")


def main() -> None:
    common = yaml.safe_load((CONFIG_DIR / "common.yaml").read_text())
    arm = yaml.safe_load((CONFIG_DIR / "two_dgs_ref.yaml").read_text())
    audit = json.loads((TASK_ROOT / "reference_parity_audit.json").read_text())
    if not audit["gate"]["two_dgs_training_allowed"]:
        raise RuntimeError("2DGS parity gate does not authorize training")
    if audit["gate"]["pgsr_training_allowed"]:
        raise RuntimeError("PGSR must remain stopped by the parity gate")

    base_path = REPO / common["base_training_config"]
    base = yaml.safe_load(base_path.read_text())
    resolved = dict(base)
    resolved.update(arm["overrides"])
    resolved["out_dir"] = arm["out_dir"]

    required = {
        "seed": 0,
        "load_depth": False,
        "load_normal": False,
        "w_photo": 1.0,
        "photo_lam": 0.2,
        "w_depth": 0.0,
        "w_normal": 0.0,
        "w_mono_depth": 0.0,
        "w_mvc": 0.0,
        "w_nc": 0.05,
        "nc_warmup": 7000,
        "normal_consistency_mode": "official_2dgs",
        "surface_normal_depth_mode": "surface_intersection_expected",
        "w_distort": 0.0,
        "lr_means_schedule": "official_2dgs_exponential",
        "grow_grad2d": 0.0002,
        "refine_start_iter": 500,
        "refine_stop_iter": 15000,
        "refine_every": 100,
        "reset_every": 3000,
        "elongation_filter": False,
        "max_gaussians": None,
        "max_iter": 20000,
        "scientific_verdict": None,
    }
    mismatch = {key: [resolved.get(key), value] for key, value in required.items() if resolved.get(key) != value}
    forbidden_nonzero = {
        key: resolved.get(key)
        for key in (
            "w_depth", "w_normal", "w_mono_depth", "w_mono_normal",
            "w_external_als_depth", "w_external_als_normal", "w_lod_prior",
            "w_sem", "w_mutual", "w_structure", "w_mvc", "w_distort",
        )
        if float(resolved.get(key, 0.0) or 0.0) != 0.0
    }
    if mismatch or forbidden_nonzero:
        raise RuntimeError(
            f"resolved config gate failed mismatch={mismatch} forbidden={forbidden_nonzero}"
        )
    if (
        len(resolved["visible_views"]) != 55
        or len(resolved["train_views"]) != 47
        or len(resolved["eval_views"]) != 8
        or set(resolved["train_views"]) & set(resolved["eval_views"])
        or set(resolved["visible_views"])
        != set(resolved["train_views"]) | set(resolved["eval_views"])
    ):
        raise RuntimeError("55/47/8 fixed-view gate failed")
    prohibited_keys = {
        "photo_mask_dir", "photo_mask_manifest", "roof_audit_mask_manifest",
        "plane_region_mask_manifest", "semantic_dir", "init_pointcloud",
        "surface_seed_npz",
    }
    leaked = {key: resolved[key] for key in prohibited_keys if resolved.get(key) is not None}
    if leaked:
        raise RuntimeError(f"reference training leaked prohibited selectors: {leaked}")

    runtime_path = TASK_ROOT / "control/runtime_configs/gsplat_2dgs_ref_r1.yaml"
    atomic_text(runtime_path, yaml.safe_dump(resolved, sort_keys=False))
    smoke = dict(resolved)
    smoke.update(
        {
            "run_id": "GSPLAT_2DGS_REF_SMOKE",
            "out_dir": str(TASK_ROOT / "smoke/attempt_2/GSPLAT_2DGS_REF"),
            "max_iter": 20,
            "eval_every": 100000,
            "ckpt_every": 100000,
            "full_state_checkpoint": False,
            "full_state_checkpoint_steps": [],
            "full_state_resume": "off",
        }
    )
    smoke_path = TASK_ROOT / "control/runtime_configs/gsplat_2dgs_ref_smoke.yaml"
    atomic_text(smoke_path, yaml.safe_dump(smoke, sort_keys=False))
    base_dump = yaml.safe_dump(base, sort_keys=True).splitlines(keepends=True)
    resolved_dump = yaml.safe_dump(resolved, sort_keys=True).splitlines(keepends=True)
    diff = "".join(
        difflib.unified_diff(
            base_dump,
            resolved_dump,
            fromfile=str(base_path.relative_to(REPO)),
            tofile=str(runtime_path),
        )
    )
    atomic_text(TASK_ROOT / "config_diff.txt", diff)
    gate = {
        "schema": "jointbuildgs.reference_family_resolved_config_gate.v1",
        "runtime_config": str(runtime_path),
        "runtime_config_sha256": sha256(runtime_path),
        "smoke_config": str(smoke_path),
        "smoke_config_sha256": sha256(smoke_path),
        "base_config": str(base_path),
        "base_config_sha256": sha256(base_path),
        "view_counts": {"visible": 55, "train": 47, "held_out": 8},
        "external_supervision_nonzero": forbidden_nonzero,
        "pgsr_training_started": False,
        "passed": True,
        "scientific_verdict": None,
    }
    atomic_json(TASK_ROOT / "control/resolved_config_gate.json", gate)
    contract_path = TASK_ROOT / "experiment_contract.json"
    contract = json.loads(contract_path.read_text())
    contract.update(
        {
            "status": "TRAINING_CONFIG_BOUND",
            "training_experiments_started": 0,
            "training_experiments_allowed": 1,
            "runtime_config": str(runtime_path),
            "runtime_config_sha256": sha256(runtime_path),
            "scientific_verdict": None,
        }
    )
    atomic_json(contract_path, contract)
    print(json.dumps(gate, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
