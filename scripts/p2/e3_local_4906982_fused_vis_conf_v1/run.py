#!/usr/bin/env python3
"""Add-only orchestration for the fused-target, native-view-support mask arm."""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
from pathlib import Path
import shutil

import yaml

REPO = Path(__file__).resolve().parents[3]
ARTIFACT_ROOT = REPO.parent / "JointBuildGS-artifacts"
TASK_ID = "P2-E3-LOCAL-4906982-FUSED-VIS-CONF-v1"
TASK_ROOT = ARTIFACT_ROOT / "phase-payloads/p2/e3_local_4906982_fused_vis_conf_v1" / TASK_ID
CONFIG_DIR = REPO / "configs/p2/e3_local_4906982_fused_vis_conf_v1"
COMMON_CONFIG = CONFIG_DIR / "common.yaml"
SUPPORT_CONFIG = CONFIG_DIR / "support.yaml"
ARM_CONFIG = CONFIG_DIR / "fused_vis_conf.yaml"
BASE_CONFIG = REPO / "configs/p2/e3_local_4906982_mvc_depth_v1/depth03.yaml"
SURFACE_CONFIG = REPO / "configs/p2/e3_local_4906982_mvs_surface_depth_v1/mvs_surface_metric.yaml"
SUPPORT_DEFINITION = TASK_ROOT / "fusion_support_definition.json"
RUN_ROOT = TASK_ROOT / "arms/FUSED_VIS_CONF/R1"
RUNTIME_CONFIG = TASK_ROOT / "control/runtime_configs/fused_vis_conf_r1.yaml"
CONTROL_SOURCE = ARTIFACT_ROOT / "phase-payloads/p2/e3_local_4906982_mvs_surface_depth_v1/P2-E3-LOCAL-4906982-MVS-SURFACE-DEPTH-v1/arms/MVS_SURFACE_METRIC/R1"
ARMS = ("MVS_SURFACE_METRIC", "FUSED_VIS_CONF")
CHECKPOINTS = (7000, 12000, 15000, 20000)


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


surface = load_module("mvs_surface_runner", REPO / "scripts/p2/e3_local_4906982_mvs_surface_depth_v1/run.py")
base = surface.base
surface.TASK_ID = TASK_ID
surface.TASK_ROOT = TASK_ROOT
surface.CONFIG_DIR = CONFIG_DIR
surface.COMMON_CONFIG = COMMON_CONFIG
surface.ARM_CONFIG = ARM_CONFIG
surface.RUN_ROOT = RUN_ROOT
surface.RUNTIME_CONFIG = RUNTIME_CONFIG
surface.ARMS = ARMS
surface.REPLICAS = ("R1",)
surface.CHECKPOINTS = CHECKPOINTS
base.TASK_ID = TASK_ID
base.TASK_ROOT = TASK_ROOT
base.GPU = "1"
base.ARMS = ARMS
base.REPLICAS = ("R1",)
base.CHECKPOINTS = CHECKPOINTS


def materialized() -> dict:
    body = yaml.safe_load(BASE_CONFIG.read_text())
    body.update(yaml.safe_load(ARM_CONFIG.read_text())["overrides"])
    body.update({
        "full_state_checkpoint": True,
        "full_state_checkpoint_steps": list(CHECKPOINTS),
        "full_state_resume": "auto",
        "full_state_resume_strict_cuda_rng": True,
        "official_PASS_usable": None,
        "scientific_verdict": None,
    })
    return body


surface.materialized = materialized


def preflight() -> None:
    for relative in ("control/runtime_configs", "control/effective_configs", "control/receipts", "logs", "cache/torch_extensions", "representative_images"):
        (TASK_ROOT / relative).mkdir(parents=True, exist_ok=True)
    for path in (COMMON_CONFIG, SUPPORT_CONFIG, ARM_CONFIG, BASE_CONFIG, SURFACE_CONFIG,
                 SUPPORT_DEFINITION, TASK_ROOT / "fusion_support_metrics.csv",
                 surface.SOURCE_CHECKPOINT, Path(str(surface.SOURCE_CHECKPOINT) + ".sha256")):
        if not path.is_file():
            raise FileNotFoundError(path)
    support = json.loads(SUPPORT_DEFINITION.read_text())
    if support.get("status") != "GATE_PASSED" or not all(support.get("gate_checks", {}).values()):
        raise RuntimeError("native OpenMVS support gate did not pass")
    if not base.checkpoint_valid(surface.SOURCE_RUN, 7000):
        raise RuntimeError("source 7k full-state checkpoint sidecar failed")

    target = materialized()
    base.atomic_text(RUNTIME_CONFIG, yaml.safe_dump(target, sort_keys=False))
    control = yaml.safe_load(BASE_CONFIG.read_text())
    control.update(yaml.safe_load(SURFACE_CONFIG.read_text())["overrides"])
    changed = sorted(key for key in set(control) | set(target) if control.get(key) != target.get(key))
    expected = ["data_root", "out_dir", "run_id", "task_id"]
    if changed != expected:
        raise RuntimeError(f"single-variable config gate failed: {changed} != {expected}")
    locked = {
        "seed": 0, "downscale": 1.0, "load_depth": True, "load_normal": False,
        "depth_supervision_mode": "expected", "depth_loss_type": "l1",
        "w_depth": 0.03, "depth_warmup": 7000, "depth_schedule": "ramp",
        "depth_ramp_steps": 5000, "w_mvc": 0.5, "w_nc": 0.05,
        "w_distort": 0.0, "max_iter": 20000,
    }
    mismatch = {key: [target.get(key), value] for key, value in locked.items() if target.get(key) != value}
    if mismatch or len(target["train_views"]) != 47 or len(target["eval_views"]) != 8:
        raise RuntimeError(f"locked training config mismatch: {mismatch}")

    diff = "\n".join([
        "comparison: existing MVS_SURFACE_METRIC/R1 versus new FUSED_VIS_CONF/R1",
        "single substantive intervention: depth valid mask",
        "control mask: every positive-finite OpenMVS mesh ray hit",
        "intervention mask: mesh hit AND native filtered view depth/confidence AND OpenMVS 1% depth agreement",
        "target on common pixels unchanged: OpenMVS mesh camera-Z",
        "unchanged: sparse initialization, expected rendered depth, metric L1, weight/schedule, MVC, NC, densification, 55 views, seed, GPU",
        "changed config keys: " + ", ".join(changed),
        "scientific_verdict: null", "",
    ])
    base.atomic_text(TASK_ROOT / "config_diff.txt", diff)
    depth_dir = Path(target["data_root"].replace("/artifacts/JointBuildGS", str(ARTIFACT_ROOT), 1)) / "depth"
    hashes = {path.name: base.sha256(path) for path in sorted(depth_dir.glob("*.exr"))}
    if len(hashes) != 55:
        raise RuntimeError(f"expected 55 frozen masked depth maps, found {len(hashes)}")
    inputs = {
        "schema": "jointbuildgs.p2.e3_local_4906982_fused_vis_conf_v1.inputs.v1",
        "source_7k_checkpoint": {"path": str(surface.SOURCE_CHECKPOINT), "sha256": base.sha256(surface.SOURCE_CHECKPOINT)},
        "surface_control_config": {"path": str(SURFACE_CONFIG), "sha256": base.sha256(SURFACE_CONFIG)},
        "support_definition": {"path": str(SUPPORT_DEFINITION), "sha256": base.sha256(SUPPORT_DEFINITION)},
        "native_dmap_manifest": {"path": str(TASK_ROOT / "native_dmap/manifest.jsonl"), "sha256": base.sha256(TASK_ROOT / "native_dmap/manifest.jsonl")},
        "masked_fused_depth_sha256": hashes,
        "crop_cameras_view_roles_regenerated": False,
        "lod2_training_use": False,
        "scientific_verdict": None,
    }
    base.atomic_json(TASK_ROOT / "input_hashes.json", inputs)
    contract = {
        "schema": "jointbuildgs.p2.e3_local_4906982_fused_vis_conf_v1.contract.v1",
        "task_id": TASK_ID, "building_id": "DEBY_LOD2_4906982",
        "status": "PREFLIGHT_BOUND", "question": "Did unconditioned per-view use of a globally fused target cause the prior fused-depth regression?",
        "comparison": {"control": "MVS_SURFACE_METRIC/R1", "intervention": "FUSED_VIS_CONF/R1"},
        "single_variable": "depth valid mask", "target_unchanged": True,
        "source_completed_updates": 7000, "checkpoints": list(CHECKPOINTS),
        "selected_gpu": 1, "training_experiments_started": 0,
        "new_loss": False, "multiview_densification": False, "lod2_training_use": False,
        "scientific_verdict": None,
    }
    base.atomic_json(TASK_ROOT / "experiment_contract.json", contract)
    sources = [Path(__file__), REPO / "scripts/p2/e3_local_4906982_fused_vis_conf_v1/prepare_support.py",
               REPO / "scripts/p2/e3_local_4906982_fused_vis_conf_v1/inspect_openmvs_dmap.cpp",
               BASE_CONFIG, SURFACE_CONFIG, COMMON_CONFIG, SUPPORT_CONFIG, ARM_CONFIG,
               REPO / "src/stage2/train.py", REPO / "src/stage2/dataloader.py",
               REPO / "src/stage2/loss/data_fitting.py", REPO / "src/stage2/loss/multiview.py"]
    previous_path = TASK_ROOT / "provenance.json"
    previous = json.loads(previous_path.read_text()) if previous_path.is_file() else {}
    base.atomic_json(previous_path, {
        "schema": "jointbuildgs.p2.e3_local_4906982_fused_vis_conf_v1.provenance.v1",
        "task_id": TASK_ID, "git": base.git_record(), "docker_image": base.image_record(),
        "gpu": base.gpu_record(),
        "source_config_sha256": {str(p.relative_to(REPO)): base.sha256(p) for p in sources},
        "input_hashes_sha256": base.sha256(TASK_ROOT / "input_hashes.json"),
        "random_seed": 0, "started_utc": previous.get("started_utc") or base.now(),
        "ended_utc": None, "commands": previous.get("commands", []),
        "return_codes": previous.get("return_codes", []), "scientific_verdict": None,
    })
    base.atomic_text(TASK_ROOT / "NOTES.md", f"# {TASK_ID}\n\nSupport gate: `GATE_PASSED`. Training not started.\n\nscientific_verdict: null\n")
    issues = TASK_ROOT / "issues.md"
    if not issues.exists():
        base.atomic_text(issues, "# Issues\n\n- Read-only `InterfaceCOLMAP dim_dense.mvs` export attempt failed with `std::bad_alloc`; the source remained unchanged. Native `.dmap` files were read directly instead.\n\nscientific_verdict: null\n")
    print(diff, end="")


def prepare_control_proxy() -> None:
    root = TASK_ROOT / "arms/MVS_SURFACE_METRIC/R1"
    for relative in ("ckpt", "tb"):
        (root / relative).mkdir(parents=True, exist_ok=True)
    for step in CHECKPOINTS:
        for suffix in (".pt", ".pt.sha256"):
            source = CONTROL_SOURCE / "ckpt" / f"step_{step:06d}{suffix}"
            target = root / "ckpt" / source.name
            if not source.is_file(): raise FileNotFoundError(source)
            if target.is_symlink():
                if target.resolve() != source.resolve(): raise RuntimeError(f"control proxy drift: {target}")
            elif target.exists(): raise RuntimeError(f"control proxy collision: {target}")
            else: target.symlink_to(os.path.relpath(source, target.parent))
    for source in sorted((CONTROL_SOURCE / "tb").glob("events*")):
        target = root / "tb" / source.name
        if not target.exists() and not target.is_symlink(): target.symlink_to(os.path.relpath(source, target.parent))
    cfg = yaml.safe_load(BASE_CONFIG.read_text())
    cfg.update(yaml.safe_load(SURFACE_CONFIG.read_text())["overrides"])
    cfg.update({"task_id": TASK_ID, "run_id": "MVS_SURFACE_METRIC_R1_REUSED_CONTROL", "out_dir": surface.container_path(root), "full_state_resume": "off", "scientific_verdict": None})
    base.atomic_text(TASK_ROOT / "control/runtime_configs/mvs_surface_metric_r1.yaml", yaml.safe_dump(cfg, sort_keys=False))
    base.atomic_json(TASK_ROOT / "control/control_proxy.json", {"source_run": str(CONTROL_SOURCE), "source_modified": False, "scientific_verdict": None})
    # The reused surface runner writes its historical arm label into the receipt.
    # Preserve that receipt, but expose an accurately labelled task-local alias for
    # the generic evaluator.
    legacy_receipt = TASK_ROOT / "control/receipts/train_MVS_SURFACE_METRIC_R1.json"
    intervention_receipt = TASK_ROOT / "control/receipts/train_FUSED_VIS_CONF_R1.json"
    if not intervention_receipt.is_file():
        if not legacy_receipt.is_file():
            raise FileNotFoundError(legacy_receipt)
        receipt = json.loads(legacy_receipt.read_text())
        receipt.update({
            "label": "train_FUSED_VIS_CONF_R1",
            "legacy_runner_receipt": str(legacy_receipt),
            "arm": "FUSED_VIS_CONF",
            "scientific_verdict": None,
        })
        base.atomic_json(intervention_receipt, receipt)


def adapt(code: str) -> str:
    result = code.replace("'MVC05'", "'FUSED_VIS_CONF'").replace("'MVC0'", "'MVS_SURFACE_METRIC'")
    result = result.replace("MVC05", "FUSED_VIS_CONF").replace("MVC0", "MVS_SURFACE_METRIC")
    result = result.replace("mvc05_r1.yaml", "fused_vis_conf_r1.yaml").replace("mvc0_r1.yaml", "mvs_surface_metric_r1.yaml")
    result = result.replace("'metric/psnr_train','eval/psnr','loss/mvc'", "'metric/psnr_train','eval/psnr','loss/depth','loss_weight/depth','loss/mvc'")
    result = result.replace("replicas=['R1','R2','R3']", "replicas=['R1']").replace("reps=['R1','R2','R3']", "reps=['R1']").replace("['R1','R2','R3']", "['R1']")
    result = result.replace("'replicates_per_arm':3", "'replicates_per_arm':1").replace("ddof=1", "ddof=0")
    result = result.replace("mvc05_minus_mvc0", "fused_vis_conf_minus_surface").replace("paired_mvc05_minus_mvc0", "paired_fused_vis_conf_minus_surface")
    result = result.replace("mvc_weight=0.0 if arm=='MVS_SURFACE_METRIC' or step<=7000 else .5", "mvc_weight=0.0 if step<=7000 else .5")
    for old, new in (("'cases':24", "'cases':8"), ("'classification_passed':24", "'classification_passed':8"), ("'roofer_return_code_zero':24", "'roofer_return_code_zero':8"), ("'roofer_rf_success_true':24", "'roofer_rf_success_true':8"), ("'roofer_cases':24", "'roofer_cases':8")):
        result = result.replace(old, new)
    result = result.replace("def mean(v):return sum(v)/len(v)", "def mean(v):return None if not v else sum(v)/len(v)")
    result = result.replace("def sd(v):return statistics.stdev(v) if len(v)>1 else 0.0", "def sd(v):return None if not v else (statistics.stdev(v) if len(v)>1 else 0.0)")
    return result


def train() -> None:
    contract_path = TASK_ROOT / "experiment_contract.json"
    contract = json.loads(contract_path.read_text())
    contract["training_experiments_started"] = 1; contract["status"] = "TRAINING_STARTED"
    base.atomic_json(contract_path, contract)
    surface.train()


def analyze_checkpoints() -> None:
    prepare_control_proxy()
    base.ANALYZE_CODE = adapt(base.ANALYZE_CODE)
    base.analyze_checkpoints()


def stage3() -> None:
    prepare_control_proxy()
    base.STAGE3_PREP_CODE = adapt(base.STAGE3_PREP_CODE)
    base.STAGE3_VERIFY_CODE = adapt(base.STAGE3_VERIFY_CODE)
    base.ROOFER_RECORD_CODE = adapt(base.ROOFER_RECORD_CODE)
    base.run_stage3()


def finalize_measurements() -> None:
    base.FINALIZE_CODE = adapt(base.FINALIZE_CODE)
    base.finalize_measurements()


def all_training() -> None:
    preflight(); surface.binding_probe(); surface.smoke(); surface.fork_7k(); train()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("preflight", "binding-probe", "smoke", "fork-7k", "train", "analyze-checkpoints", "stage3", "finalize-measurements", "mvs-surface-audit", "all-training"))
    command = parser.parse_args().command
    if command == "preflight": preflight()
    elif command == "binding-probe": surface.binding_probe()
    elif command == "smoke": surface.smoke()
    elif command == "fork-7k": surface.fork_7k()
    elif command == "train": train()
    elif command == "analyze-checkpoints": analyze_checkpoints()
    elif command == "stage3": stage3()
    elif command == "finalize-measurements": finalize_measurements()
    elif command == "mvs-surface-audit": surface.mvs_surface_audit()
    elif command == "all-training": all_training()


if __name__ == "__main__":
    main()
