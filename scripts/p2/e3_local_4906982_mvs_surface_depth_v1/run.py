#!/usr/bin/env python3
"""Run the combined OpenMVS surface-depth transfer arm in Docker only."""
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
TASK_ID = "P2-E3-LOCAL-4906982-MVS-SURFACE-DEPTH-v1"
TASK_ROOT = ARTIFACT_ROOT / "phase-payloads/p2/e3_local_4906982_mvs_surface_depth_v1" / TASK_ID
CONFIG_DIR = REPO / "configs/p2/e3_local_4906982_mvs_surface_depth_v1"
COMMON_CONFIG = CONFIG_DIR / "common.yaml"
PROJECTION_CONFIG = CONFIG_DIR / "projection.yaml"
ARM_CONFIG = CONFIG_DIR / "mvs_surface_metric.yaml"
BASE_CONFIG = REPO / "configs/p2/e3_local_4906982_mvc_depth_v1/depth03.yaml"
SOURCE_RUN = ARTIFACT_ROOT / "phase-payloads/p2/e3_local_4906982_mvc_depth_v1/P2-E3-LOCAL-4906982-MVC-DEPTH-v1/arms/DEPTH03/R1"
SOURCE_CHECKPOINT = SOURCE_RUN / "ckpt/step_007000.pt"
SOURCE_INPUTS = SOURCE_RUN.parents[2] / "input_hashes.json"
MVS_INPUTS = ARTIFACT_ROOT / "phase-payloads/p2/e3_local_4906982_mvs_transfer_diag_v1/P2-E3-LOCAL-4906982-MVS-TRANSFER-DIAG-v1/input_hashes.json"
RUN_ROOT = TASK_ROOT / "arms/MVS_SURFACE_METRIC/R1"
RUNTIME_CONFIG = TASK_ROOT / "control/runtime_configs/mvs_surface_metric_r1.yaml"
GPU = "1"
ARMS = ("RAW_DEPTH", "MVS_SURFACE_METRIC")
REPLICAS = ("R1",)
CHECKPOINTS = (7000, 12000, 15000, 20000)


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


depth_runner = load_module(
    "mvc_depth_runner",
    REPO / "scripts/p2/e3_local_4906982_mvc_depth_v1/run.py",
)
base = depth_runner.base
base.TASK_ID = TASK_ID
base.TASK_ROOT = TASK_ROOT
base.GPU = GPU
base.ARMS = ARMS
base.REPLICAS = REPLICAS
base.CHECKPOINTS = CHECKPOINTS


def sha256(path: Path) -> str:
    return base.sha256(path)


def container_path(path: Path) -> str:
    return base.container_path(path)


def host_artifact_path(path: Path) -> Path:
    prefix = Path("/artifacts/JointBuildGS")
    try:
        relative = path.relative_to(prefix)
    except ValueError:
        return path
    return ARTIFACT_ROOT / relative


def ensure_run_owner() -> None:
    """Make Docker-created task-local run files writable by the host orchestrator."""
    if not RUN_ROOT.exists():
        return
    argv = base.docker_base() + [
        "chown", "-R", f"{os.getuid()}:{os.getgid()}", container_path(RUN_ROOT)
    ]
    subprocess.run(argv, check=True)


def ensure_task_owner() -> None:
    """Normalize ownership only within this newly created artifact namespace."""
    if not TASK_ROOT.exists():
        return
    argv = base.docker_base() + [
        "chown", "-R", f"{os.getuid()}:{os.getgid()}", container_path(TASK_ROOT)
    ]
    subprocess.run(argv, check=True)


def materialized() -> dict[str, Any]:
    body = yaml.safe_load(BASE_CONFIG.read_text())
    overlay = yaml.safe_load(ARM_CONFIG.read_text())["overrides"]
    body.update(overlay)
    body.update(
        {
            "full_state_checkpoint": True,
            "full_state_checkpoint_steps": [7000, 12000, 15000, 20000],
            "full_state_resume": "auto",
            "full_state_resume_strict_cuda_rng": True,
            "official_PASS_usable": None,
            "scientific_verdict": None,
        }
    )
    return body


def changed(left: dict[str, Any], right: dict[str, Any]) -> list[str]:
    return sorted(key for key in set(left) | set(right) if left.get(key) != right.get(key))


def preflight() -> None:
    for relative in (
        "control/runtime_configs",
        "control/effective_configs",
        "control/receipts",
        "logs",
        "cache/torch_extensions",
        "representative_images",
    ):
        (TASK_ROOT / relative).mkdir(parents=True, exist_ok=True)
    for path in (
        COMMON_CONFIG,
        PROJECTION_CONFIG,
        ARM_CONFIG,
        BASE_CONFIG,
        SOURCE_CHECKPOINT,
        Path(str(SOURCE_CHECKPOINT) + ".sha256"),
        SOURCE_INPUTS,
        MVS_INPUTS,
    ):
        if not path.is_file():
            raise FileNotFoundError(path)
    if not base.checkpoint_valid(SOURCE_RUN, 7000):
        raise RuntimeError("source 7k full-state checkpoint sidecar failed")

    raw = yaml.safe_load(BASE_CONFIG.read_text())
    target = materialized()
    base.atomic_text(RUNTIME_CONFIG, yaml.safe_dump(target, sort_keys=False))
    actual = changed(raw, target)
    expected = sorted(
        {
            "data_root",
            "depth_loss_type",
            "depth_supervision_mode",
            "full_state_resume",
            "out_dir",
            "run_id",
            "task_id",
        }
    )
    if actual != expected:
        raise RuntimeError(f"config-diff gate failed: {actual} != {expected}")
    locked = {
        "seed": 0,
        "downscale": 1.0,
        "load_depth": True,
        "load_normal": False,
        "w_depth": 0.03,
        "depth_warmup": 7000,
        "depth_schedule": "ramp",
        "depth_ramp_steps": 5000,
        "depth_prior_alignment": "none",
        "w_mvc": 0.5,
        "w_nc": 0.05,
        "w_distort": 0.0,
        "max_iter": 20000,
    }
    mismatch = {key: [target.get(key), value] for key, value in locked.items() if target.get(key) != value}
    if mismatch or len(target["visible_views"]) != 55 or len(target["train_views"]) != 47 or len(target["eval_views"]) != 8:
        raise RuntimeError(f"locked config mismatch: {mismatch}")
    diff = "\n".join(
        [
            "comparison: existing RAW_DEPTH DEPTH03/R1 versus new MVS_SURFACE_METRIC/R1",
            "combined substantive intervention: data_root depth payload",
            "selection change: raw positive-finite -> OpenMVS mesh positive finite ray hits",
            "target change: COLMAP geometric depth -> OpenMVS mesh camera-Z",
            "unchanged: sparse initialization, expected rendered depth, metric L1, weight/schedule, MVC, NC, densification, 55 views, seed, GPU",
            "changed config keys: " + ", ".join(actual),
            "causal interpretation: combined transfer test only; selection and target effects are not separable",
            "scientific_verdict: null",
            "",
        ]
    )
    base.atomic_text(TASK_ROOT / "config_diff.txt", diff)

    source_inputs = json.loads(SOURCE_INPUTS.read_text())
    mvs_inputs = json.loads(MVS_INPUTS.read_text())
    mesh_container = Path(yaml.safe_load(PROJECTION_CONFIG.read_text())["source_mesh"])
    mesh = host_artifact_path(mesh_container)
    input_hashes = {
        "schema": "jointbuildgs.p2.e3_local_4906982_mvs_surface_depth_v1.inputs.v1",
        "source_training_manifest": {"path": str(SOURCE_INPUTS), "sha256": sha256(SOURCE_INPUTS)},
        "source_mvs_manifest": {"path": str(MVS_INPUTS), "sha256": sha256(MVS_INPUTS)},
        "source_checkpoint": {"path": str(SOURCE_CHECKPOINT), "sha256": sha256(SOURCE_CHECKPOINT)},
        "openmvs_mesh": {"path": str(mesh_container), "host_path": str(mesh), "bytes": mesh.stat().st_size, "sha256": sha256(mesh)},
        "crop_cameras_sparse_depth_checkpoint_sha256": {
            "colmap_cameras": mvs_inputs["records"]["colmap_cameras"]["sha256"],
            "colmap_images": mvs_inputs["records"]["colmap_images"]["sha256"],
            "sparse_sfm_seed": mvs_inputs["records"]["sparse_sfm_seed"]["sha256"],
            "view_roles": mvs_inputs["records"]["view_roles"]["sha256"],
            "raw_depth_map_count": len(mvs_inputs["colmap_geometric_depth_sha256"]),
            "raw_depth_maps": mvs_inputs["colmap_geometric_depth_sha256"],
        },
        "source_training_manifest_schema": source_inputs.get("schema"),
        "reuse": {"crop_regenerated": False, "cameras_regenerated": False, "view_roles_regenerated": False, "sparse_seed_regenerated": False},
        "scientific_verdict": None,
    }
    base.atomic_json(TASK_ROOT / "input_hashes.json", input_hashes)
    contract = {
        "schema": "jointbuildgs.p2.e3_local_4906982_mvs_surface_depth_v1.contract.v1",
        "task_id": TASK_ID,
        "building_id": "DEBY_LOD2_4906982",
        "status": "PREFLIGHT_BOUND",
        "question": "Can the exact successful OpenMVS reconstructed surface be transferred to GS as metric depth evidence?",
        "comparison": {"control": "existing DEPTH03/R1 raw COLMAP depth", "intervention": "MVS_SURFACE_METRIC/R1"},
        "combined_intervention": ["depth target", "valid depth selection"],
        "interpretation_limit": "does not separate target-value from selection effects",
        "source_completed_updates": 7000,
        "checkpoints": [7000, 12000, 15000, 20000],
        "selected_gpu": 1,
        "lod2_training_use": False,
        "new_loss": False,
        "multiview_densification": False,
        "training_experiments_started": 0,
        "scientific_verdict": None,
    }
    base.atomic_json(TASK_ROOT / "experiment_contract.json", contract)
    sources = [Path(__file__), REPO / "scripts/p2/e3_local_4906982_mvs_surface_depth_v1/inside.py", BASE_CONFIG, COMMON_CONFIG, PROJECTION_CONFIG, ARM_CONFIG, REPO / "src/stage2/train.py", REPO / "src/stage2/dataloader.py", REPO / "src/stage2/loss/data_fitting.py", REPO / "src/stage2/loss/multiview.py"]
    previous = json.loads((TASK_ROOT / "provenance.json").read_text()) if (TASK_ROOT / "provenance.json").is_file() else {}
    base.atomic_json(
        TASK_ROOT / "provenance.json",
        {
            "schema": "jointbuildgs.p2.e3_local_4906982_mvs_surface_depth_v1.provenance.v1",
            "task_id": TASK_ID,
            "git": base.git_record(),
            "docker_image": base.image_record(),
            "gpu": base.gpu_record(),
            "source_config_sha256": {str(path.relative_to(REPO)): sha256(path) for path in sources},
            "input_hashes_sha256": sha256(TASK_ROOT / "input_hashes.json"),
            "random_seed": 0,
            "started_utc": previous.get("started_utc") or base.now(),
            "ended_utc": None,
            "commands": previous.get("commands", []),
            "return_codes": previous.get("return_codes", []),
            "scientific_verdict": None,
        },
    )
    base.atomic_text(TASK_ROOT / "NOTES.md", f"# {TASK_ID}\n\nStatus: `PREFLIGHT_BOUND`. Training not started.\n\nscientific_verdict: null\n")
    print(diff, end="")


def project() -> None:
    output = TASK_ROOT / "mvs_surface_depth_definition.json"
    if output.is_file() and json.loads(output.read_text()).get("status") == "COMPLETE":
        print(output.read_text())
        return
    argv = base.docker_base() + ["python", "scripts/p2/e3_local_4906982_mvs_surface_depth_v1/inside.py"]
    log = TASK_ROOT / "logs/project_depth.log"
    started = base.now()
    with log.open("a", encoding="utf-8") as stream:
        proc = subprocess.run(argv, text=True, stdout=stream, stderr=subprocess.STDOUT)
    base.record_operation("project_depth", argv, proc.returncode, started, base.now())
    if proc.returncode != 0:
        raise RuntimeError(f"mesh-depth projection failed; inspect {log}")
    body = json.loads(output.read_text())
    provenance = json.loads((TASK_ROOT / "provenance.json").read_text())
    provenance["projected_depth_manifest_sha256"] = sha256(output)
    provenance["projected_depth_metrics_sha256"] = sha256(TASK_ROOT / "mvs_surface_depth_metrics.csv")
    base.atomic_json(TASK_ROOT / "provenance.json", provenance)
    print(json.dumps({key: value for key, value in body.items() if key != "views"}, indent=2))


def probe_config() -> Path:
    cfg = materialized()
    cfg.update({
        "run_id": "BINDING_PROBE_MVS_SURFACE_METRIC",
        "out_dir": container_path(TASK_ROOT / "binding_probe"),
        "max_iter": 1,
        "eval_every": 100000,
        "ckpt_every": 100000,
        "full_state_resume": "off",
    })
    path = TASK_ROOT / "control/runtime_configs/binding_probe.yaml"
    base.atomic_text(path, yaml.safe_dump(cfg, sort_keys=False))
    return path


def binding_probe() -> None:
    stable = TASK_ROOT / "control/effective_configs/mvs_surface_metric.json"
    if stable.is_file():
        print(stable.read_text())
        return
    config = probe_config()
    output = TASK_ROOT / "binding_probe"
    argv = base.docker_base(gpu=True) + ["python", "-c", base.DETERMINISTIC_WRAPPER, "--config", container_path(config)]
    log = TASK_ROOT / "logs/binding_probe.log"
    started = base.now()
    with log.open("w", encoding="utf-8") as stream:
        proc = subprocess.run(argv, text=True, stdout=stream, stderr=subprocess.STDOUT)
    base.record_operation("binding_probe", argv, proc.returncode, started, base.now())
    if proc.returncode != 0:
        raise RuntimeError(f"binding probe failed; inspect {log}")
    effective = json.loads((output / "effective_config.json").read_text())
    effective.pop("full_state_runtime", None)
    base.atomic_json(stable, effective)
    print(stable.read_text())


def smoke() -> None:
    receipt = TASK_ROOT / "control/receipts/smoke.json"
    if receipt.is_file() and json.loads(receipt.read_text()).get("passed"):
        print(receipt.read_text())
        return
    cfg = materialized()
    root = TASK_ROOT / "smoke"
    cfg.update({
        "run_id": "SMOKE_MVS_SURFACE_METRIC",
        "out_dir": container_path(root),
        "max_iter": 12,
        "eval_every": 100000,
        "ckpt_every": 100000,
        "full_state_resume": "off",
        "full_state_checkpoint": False,
        "full_state_checkpoint_steps": [],
        "mvc_warmup": 0,
        "mvc_ramp_steps": 1,
        "depth_warmup": 0,
        "depth_ramp_steps": 1,
        "loss_grad_audit_every": 1,
        "refine_start_iter": 500,
    })
    config = TASK_ROOT / "control/runtime_configs/smoke.yaml"
    base.atomic_text(config, yaml.safe_dump(cfg, sort_keys=False))
    argv = base.docker_base(gpu=True) + ["python", "-c", base.DETERMINISTIC_WRAPPER, "--config", container_path(config)]
    log = TASK_ROOT / "logs/smoke.log"
    started = base.now()
    with log.open("w", encoding="utf-8") as stream:
        proc = subprocess.run(argv, text=True, stdout=stream, stderr=subprocess.STDOUT)
    base.record_operation("smoke", argv, proc.returncode, started, base.now())
    text = log.read_text(errors="replace")
    passed = proc.returncode == 0 and "avg 2.0 neighbors/view" in text and "[done]" in text
    base.atomic_json(receipt, {"return_code": proc.returncode, "neighbor_summary_found": "avg 2.0 neighbors/view" in text, "passed": passed, "scientific_verdict": None})
    if not passed:
        raise RuntimeError(f"smoke failed; inspect {log}")
    print(receipt.read_text())


def fork_7k() -> None:
    stable = TASK_ROOT / "control/effective_configs/mvs_surface_metric.json"
    smoke_receipt = TASK_ROOT / "control/receipts/smoke.json"
    receipt = TASK_ROOT / "control/receipts/rebind_mvs_surface_metric_r1.json"
    if not stable.is_file() or not smoke_receipt.is_file() or not json.loads(smoke_receipt.read_text()).get("passed"):
        raise RuntimeError("binding probe and smoke must pass before the 7k fork")
    if receipt.is_file() and json.loads(receipt.read_text()).get("passed") and base.checkpoint_valid(RUN_ROOT, 7000):
        ensure_run_owner()
        print(receipt.read_text())
        return
    if RUN_ROOT.exists():
        raise RuntimeError(f"incomplete target run root requires review: {RUN_ROOT}")
    destination = RUN_ROOT / "ckpt/step_007000.pt"
    argv = base.docker_base() + [
        "python", "-c", depth_runner.REBIND_CODE,
        container_path(SOURCE_CHECKPOINT), container_path(destination),
        container_path(RUNTIME_CONFIG), Path(container_path(RUN_ROOT)),
        container_path(stable), container_path(receipt),
    ]
    started = base.now()
    proc = subprocess.run([str(value) for value in argv], text=True, capture_output=True)
    (TASK_ROOT / "logs/rebind_7k.log").write_text(proc.stdout + proc.stderr)
    base.record_operation("rebind_7k", [str(value) for value in argv], proc.returncode, started, base.now())
    if proc.returncode != 0:
        raise RuntimeError("7k rebind failed; inspect logs/rebind_7k.log")
    body = json.loads(receipt.read_text())
    gate = {
        "schema": "jointbuildgs.p2.e3_local_4906982_mvs_surface_depth_v1.common_state_gate.v1",
        "source": str(SOURCE_CHECKPOINT),
        "source_sha256": body["source_sha256"],
        "learned_sections_equal": body["learned_sections_equal"],
        "depth_weight_at_7k": 0.0,
        "mvc_weight_at_7k": 0.0,
        "passed": body["passed"],
        "scientific_verdict": None,
    }
    base.atomic_json(TASK_ROOT / "control/common_state_gate_7000.json", gate)
    if not gate["passed"]:
        raise RuntimeError("7k exact-state gate failed")
    ensure_run_owner()
    print(json.dumps(gate, indent=2))


def train() -> None:
    gate = TASK_ROOT / "control/common_state_gate_7000.json"
    if not gate.is_file() or not json.loads(gate.read_text()).get("passed"):
        raise RuntimeError("7k exact-state gate required")
    ensure_run_owner()
    contract_path = TASK_ROOT / "experiment_contract.json"
    contract = json.loads(contract_path.read_text())
    contract["training_experiments_started"] = 1
    contract["status"] = "TRAINING_STARTED"
    base.atomic_json(contract_path, contract)
    result = base._launch_training("train_MVS_SURFACE_METRIC_R1", RUN_ROOT, RUNTIME_CONFIG, stop_step=None)
    missing = [step for step in (7000, 12000, 15000, 20000) if not base.checkpoint_valid(RUN_ROOT, step)]
    if missing:
        raise RuntimeError(f"missing required checkpoints: {missing}")
    contract = json.loads(contract_path.read_text())
    contract["status"] = "TRAINING_COMPLETE_EVALUATION_PENDING"
    base.atomic_json(contract_path, contract)
    print(json.dumps(result, indent=2))


def prepare_raw_proxy() -> None:
    """Expose the frozen raw control read-only inside this add-only comparison task."""
    ensure_task_owner()
    root = TASK_ROOT / "arms/RAW_DEPTH/R1"
    for relative in ("ckpt", "tb"):
        (root / relative).mkdir(parents=True, exist_ok=True)
    for step in CHECKPOINTS:
        for suffix in (".pt", ".pt.sha256"):
            source = SOURCE_RUN / "ckpt" / f"step_{step:06d}{suffix}"
            target = root / "ckpt" / source.name
            if not source.is_file():
                raise FileNotFoundError(source)
            if target.is_symlink():
                if target.resolve() != source.resolve():
                    raise RuntimeError(f"raw checkpoint proxy drift: {target}")
            elif target.exists():
                raise RuntimeError(f"raw checkpoint proxy collision: {target}")
            else:
                target.symlink_to(os.path.relpath(source, target.parent))
    for source in sorted((SOURCE_RUN / "tb").glob("events*")):
        target = root / "tb" / source.name
        if not target.exists() and not target.is_symlink():
            target.symlink_to(os.path.relpath(source, target.parent))
    raw_config = yaml.safe_load(BASE_CONFIG.read_text())
    raw_config.update({
        "task_id": TASK_ID,
        "run_id": "RAW_DEPTH_R1_REUSED_CONTROL",
        "out_dir": container_path(root),
        "full_state_resume": "off",
        "scientific_verdict": None,
    })
    base.atomic_text(
        TASK_ROOT / "control/runtime_configs/raw_depth_r1.yaml",
        yaml.safe_dump(raw_config, sort_keys=False),
    )
    source_receipt = json.loads(
        (SOURCE_RUN.parents[2] / "control/receipts/train_DEPTH03_R1.json").read_text()
    )
    source_receipt.update({
        "label": "reuse_RAW_DEPTH_R1",
        "reused_control": True,
        "source_run": str(SOURCE_RUN),
        "scientific_verdict": None,
    })
    base.atomic_json(
        TASK_ROOT / "control/receipts/train_RAW_DEPTH_R1.json", source_receipt
    )
    base.atomic_json(
        TASK_ROOT / "control/raw_control_proxy.json",
        {
            "source_run": str(SOURCE_RUN),
            "checkpoint_mode": "individual read-only symlinks",
            "tensorboard_mode": "source event symlinks plus task-local posthoc events",
            "source_modified": False,
            "scientific_verdict": None,
        },
    )


def adapt_evaluation(code: str) -> str:
    result = code.replace("'MVC05'", "'MVS_SURFACE_METRIC'").replace("'MVC0'", "'RAW_DEPTH'")
    result = result.replace("MVC05", "MVS_SURFACE_METRIC").replace("MVC0", "RAW_DEPTH")
    result = result.replace("mvc0_r1.yaml", "raw_depth_r1.yaml")
    result = result.replace(
        "'metric/psnr_train','eval/psnr','loss/mvc'",
        "'metric/psnr_train','eval/psnr','loss/depth','loss_weight/depth','loss/mvc'",
    )
    result = result.replace("replicas=['R1','R2','R3']", "replicas=['R1']").replace("reps=['R1','R2','R3']", "reps=['R1']").replace("['R1','R2','R3']", "['R1']")
    result = result.replace("'replicates_per_arm':3", "'replicates_per_arm':1").replace("ddof=1", "ddof=0")
    result = result.replace("mvc05_minus_mvc0", "mvs_surface_minus_raw").replace("paired_mvc05_minus_mvc0", "paired_mvs_surface_minus_raw")
    result = result.replace("mvc_weight=0.0 if arm=='RAW_DEPTH' or step<=7000 else .5", "mvc_weight=0.0 if step<=7000 else .5")
    for old, new in (("'cases':24", "'cases':8"), ("'classification_passed':24", "'classification_passed':8"), ("'roofer_return_code_zero':24", "'roofer_return_code_zero':8"), ("'roofer_rf_success_true':24", "'roofer_rf_success_true':8"), ("'roofer_cases':24", "'roofer_cases':8")):
        result = result.replace(old, new)
    result = result.replace("def mean(v):return sum(v)/len(v)", "def mean(v):return None if not v else sum(v)/len(v)")
    result = result.replace("def sd(v):return statistics.stdev(v) if len(v)>1 else 0.0", "def sd(v):return None if not v else (statistics.stdev(v) if len(v)>1 else 0.0)")
    return result


def analyze_checkpoints() -> None:
    prepare_raw_proxy()
    base.ANALYZE_CODE = adapt_evaluation(base.ANALYZE_CODE)
    base.analyze_checkpoints()


def stage3() -> None:
    prepare_raw_proxy()
    base.STAGE3_PREP_CODE = adapt_evaluation(base.STAGE3_PREP_CODE)
    base.STAGE3_VERIFY_CODE = adapt_evaluation(base.STAGE3_VERIFY_CODE)
    base.ROOFER_RECORD_CODE = adapt_evaluation(base.ROOFER_RECORD_CODE)
    base.run_stage3()


def finalize_measurements() -> None:
    base.FINALIZE_CODE = adapt_evaluation(base.FINALIZE_CODE)
    base.finalize_measurements()


def mvs_surface_audit() -> None:
    output_json = TASK_ROOT / "mvs_surface_audit.json"
    output_csv = TASK_ROOT / "mvs_surface_metrics.csv"
    script = REPO / "scripts/p2/e3_local_4906982_depth_rep_diag_v1/surface_audit.py"
    mvs_npy = ARTIFACT_ROOT / "phase-payloads/p2/e3_local_4906982_mvs_transfer_diag_v1/P2-E3-LOCAL-4906982-MVS-TRANSFER-DIAG-v1/fused_seed/mvs_xyz_f32.npy"
    footprint = TASK_ROOT / "control/shared_standard_footprint_4906982.geojson"
    argv = base.eval_docker_base() + [
        "python", "/workspace/JointBuildGS/" + str(script.relative_to(REPO)),
        "--task-root", container_path(TASK_ROOT),
        "--mvs-npy", container_path(mvs_npy),
        "--footprint", container_path(footprint),
        "--output-json", container_path(output_json),
        "--output-csv", container_path(output_csv),
        "--arms", *ARMS,
    ]
    log = TASK_ROOT / "logs/mvs_surface_audit.log"
    started = base.now()
    with log.open("w", encoding="utf-8") as stream:
        proc = subprocess.run(argv, text=True, stdout=stream, stderr=subprocess.STDOUT)
    base.record_operation("mvs_surface_audit", argv, proc.returncode, started, base.now())
    if proc.returncode != 0:
        raise RuntimeError(f"MVS surface audit failed; inspect {log}")
    print(output_json.read_text())


def reference_diagnostic() -> None:
    output = TASK_ROOT / "reference_diagnostic"
    metrics = output / "metrics.json"
    if metrics.is_file() and json.loads(metrics.read_text()).get("status") == "COMPLETE_DIAGNOSTIC":
        print(metrics.read_text())
        return
    source = yaml.safe_load(
        (REPO / "configs/p2/e3_local_4906982_mvc_readout_diag_v1/config.yaml").read_text()
    )
    source.update({
        "task_id": TASK_ID + "-REFERENCE-DIAG",
        "source_task_root": container_path(TASK_ROOT),
        "source_runner": "/workspace/JointBuildGS/scripts/p2/e3_local_4906982_mvs_surface_depth_v1/run.py",
        "shared_footprint": container_path(TASK_ROOT / "control/shared_standard_footprint_4906982.geojson"),
        "arms": list(ARMS),
        "replicas": list(REPLICAS),
        "checkpoints": list(CHECKPOINTS),
        "scientific_verdict": None,
    })
    config = TASK_ROOT / "control/reference_diagnostic.yaml"
    base.atomic_text(config, yaml.safe_dump(source, sort_keys=False))
    runner = (REPO / "scripts/p2/e3_local_4906982_mvc_readout_diag_v1/run.py").read_text()
    runner = runner.replace('"MVC05"', '"MVS_SURFACE_METRIC"').replace('"MVC0"', '"RAW_DEPTH"').replace("'MVC05'", "'MVS_SURFACE_METRIC'").replace("'MVC0'", "'RAW_DEPTH'")
    runner = runner.replace(
        'REPO = Path(__file__).resolve().parents[3]\nARTIFACT_ROOT = REPO.parent / "JointBuildGS-artifacts"',
        'REPO = Path("/workspace/JointBuildGS")\nARTIFACT_ROOT = Path("/artifacts/JointBuildGS")',
    )
    runtime = TASK_ROOT / "control/reference_diag_runtime.py"
    base.atomic_text(runtime, runner)
    output.mkdir(parents=True, exist_ok=True)
    (output / "logs").mkdir(exist_ok=True)
    argv = [
        "docker", "run", "--rm", "--network", "none",
        "--user", f"{os.getuid()}:{os.getgid()}",
        "-e", "MPLCONFIGDIR=/tmp/matplotlib",
        "-v", f"{REPO}:/workspace/JointBuildGS:ro",
        "-v", f"{ARTIFACT_ROOT}:/artifacts/JointBuildGS:ro",
        "-v", f"{TASK_ROOT}:/task:rw",
        "-w", "/workspace/JointBuildGS", base.EVAL_IMAGE,
        "python", "/task/control/reference_diag_runtime.py", "--inside-docker", "analyze",
        "--config", container_path(config), "--output", "/task/reference_diagnostic",
    ]
    log = output / "logs/analyze.log"
    started = base.now()
    with log.open("w", encoding="utf-8") as stream:
        proc = subprocess.run(argv, text=True, stdout=stream, stderr=subprocess.STDOUT)
    base.record_operation("reference_diagnostic", argv, proc.returncode, started, base.now())
    if proc.returncode != 0:
        raise RuntimeError(f"reference diagnostic failed; inspect {log}")
    print(metrics.read_text())


def all_training() -> None:
    preflight()
    project()
    binding_probe()
    smoke()
    fork_7k()
    train()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("preflight", "project", "binding-probe", "smoke", "fork-7k", "train", "analyze-checkpoints", "stage3", "finalize-measurements", "mvs-surface-audit", "reference-diagnostic", "all-training"))
    args = parser.parse_args()
    globals()[args.command.replace("-", "_")]()


if __name__ == "__main__":
    main()
