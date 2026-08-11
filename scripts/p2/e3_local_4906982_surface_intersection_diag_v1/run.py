#!/usr/bin/env python3
"""EXPECTED-vs-surface-intersection raw COLMAP supervision experiment."""
from __future__ import annotations

import argparse
import csv
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
ARTIFACT_ROOT = REPO.parent / "JointBuildGS-artifacts"
TASK_ID = "P2-E3-LOCAL-4906982-SURFACE-INTERSECTION-DIAG-v1"
TASK_ROOT = ARTIFACT_ROOT / "phase-payloads/p2/e3_local_4906982_surface_intersection_diag_v1" / TASK_ID
CONFIG_DIR = REPO / "configs/p2/e3_local_4906982_surface_intersection_diag_v1"
COMMON_CONFIG = CONFIG_DIR / "common.yaml"
ARM_CONFIGS = {
    "EXPECTED": CONFIG_DIR / "expected.yaml",
    "SURFACE_INTERSECTION": CONFIG_DIR / "surface_intersection.yaml",
}
BASE_CONFIG = REPO / "configs/p2/e3_local_4906982_mvc_depth_v1/depth03.yaml"
SOURCE_RUN = ARTIFACT_ROOT / "phase-payloads/p2/e3_local_4906982_mvc_depth_v1/P2-E3-LOCAL-4906982-MVC-DEPTH-v1/arms/DEPTH03/R1"
SOURCE_CHECKPOINT = SOURCE_RUN / "ckpt/step_007000.pt"
SOURCE_EFFECTIVE = SOURCE_RUN / "effective_config.json"
SOURCE_INPUTS = SOURCE_RUN.parents[2] / "input_hashes.json"
MVS_AUDIT_INPUTS = ARTIFACT_ROOT / "phase-payloads/p2/e3_local_4906982_mvs_transfer_diag_v1/P2-E3-LOCAL-4906982-MVS-TRANSFER-DIAG-v1/input_hashes.json"
PRIOR_DEPTH_REP = ARTIFACT_ROOT / "phase-payloads/p2/e3_local_4906982_depth_rep_diag_v1/P2-E3-LOCAL-4906982-DEPTH-REP-DIAG-v1"
VALIDATED_CACHE = PRIOR_DEPTH_REP / "cache/torch_extensions"
SURFACE_CACHE = TASK_ROOT / "cache/surface"
SURFACE_OVERLAY = TASK_ROOT / "control/surface_python_overlay/gsplat/cuda/csrc"
ARMS = ("EXPECTED", "SURFACE_INTERSECTION")
REPLICAS = ("R1",)
CHECKPOINTS = (7000, 12000, 15000, 20000)
ALLOWLIST = {"run_id", "out_dir", "depth_supervision_mode"}

spec = importlib.util.spec_from_file_location(
    "depth_rep_runner", REPO / "scripts/p2/e3_local_4906982_depth_rep_diag_v1/run.py"
)
assert spec and spec.loader
prior = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prior)
base = prior.base

for module in (prior, base):
    module.TASK_ID = TASK_ID
    module.TASK_ROOT = TASK_ROOT
    module.ARTIFACT_ROOT = ARTIFACT_ROOT
    module.ARMS = ARMS
    module.REPLICAS = REPLICAS
    module.CHECKPOINTS = CHECKPOINTS
    module.GPU = "1"
prior.CONFIG_DIR = CONFIG_DIR
prior.COMMON_CONFIG = COMMON_CONFIG
prior.ARM_CONFIGS = ARM_CONFIGS
prior.BASE_CONFIG = BASE_CONFIG
prior.SOURCE_RUN = SOURCE_RUN
prior.SOURCE_CHECKPOINT = SOURCE_CHECKPOINT
prior.SOURCE_EFFECTIVE = SOURCE_EFFECTIVE
prior.SOURCE_INPUTS = SOURCE_INPUTS
prior.MVS_AUDIT_INPUTS = MVS_AUDIT_INPUTS
prior.ALLOWLIST = ALLOWLIST


def sha256(path: Path) -> str:
    return base.sha256(path)


def runtime_path(arm: str) -> Path:
    return TASK_ROOT / "control/runtime_configs" / f"{arm.lower()}_r1.yaml"


def run_root(arm: str) -> Path:
    return TASK_ROOT / "arms" / arm / "R1"


prior.runtime_path = runtime_path
prior.run_root = run_root


def docker_base(
    *, surface: bool = False, gpu: bool = False, name: str | None = None,
    keep: bool = False,
) -> list[str]:
    argv = ["docker", "run"]
    if not keep:
        argv.append("--rm")
    if name:
        argv += ["--name", name]
    if gpu:
        argv += ["--gpus", "device=1", "--ipc=host"]
    argv += [
        "--network", "none",
        "-e", "CUBLAS_WORKSPACE_CONFIG=:4096:8",
        "-e", "NVIDIA_TF32_OVERRIDE=0",
        "-v", f"{REPO}:/workspace/JointBuildGS:ro",
        "-v", f"{ARTIFACT_ROOT}:/artifacts/JointBuildGS",
        "-v", f"{SURFACE_CACHE if surface else VALIDATED_CACHE}:/root/.cache/torch_extensions",
    ]
    if surface:
        argv += [
            "-e", "JBGS_GSPLAT_MEDIAN_IS_SURFACE_SUM=1",
            "-v", f"{SURFACE_OVERLAY / 'rasterize_to_pixels_2dgs_fwd.cu'}:/opt/conda/lib/python3.11/site-packages/gsplat/cuda/csrc/rasterize_to_pixels_2dgs_fwd.cu:ro",
            "-v", f"{SURFACE_OVERLAY / 'rasterize_to_pixels_2dgs_bwd.cu'}:/opt/conda/lib/python3.11/site-packages/gsplat/cuda/csrc/rasterize_to_pixels_2dgs_bwd.cu:ro",
        ]
    argv += ["-w", "/workspace/JointBuildGS", base.IMAGE]
    return argv


def standard_base(*, gpu: bool = False, name: str | None = None, keep: bool = False) -> list[str]:
    return docker_base(surface=False, gpu=gpu, name=name, keep=keep)


base.docker_base = standard_base


def materialized(arm: str) -> dict[str, Any]:
    body = yaml.safe_load(BASE_CONFIG.read_text())
    overlay = yaml.safe_load(ARM_CONFIGS[arm].read_text())
    body.update({
        "task_id": TASK_ID,
        "run_id": overlay["run_id"],
        "out_dir": overlay["out_dir"],
        "depth_supervision_mode": overlay["depth_supervision_mode"],
        "full_state_resume": "auto",
        "full_state_resume_strict_cuda_rng": True,
        "full_state_checkpoint": True,
        "full_state_checkpoint_steps": list(CHECKPOINTS),
        "max_iter": 20000,
        "official_PASS_usable": None,
        "scientific_verdict": None,
    })
    return body


prior._materialized_config = materialized


def changed(left: dict[str, Any], right: dict[str, Any]) -> set[str]:
    return {key for key in set(left) | set(right) if left.get(key) != right.get(key)}


def validate_config() -> str:
    configs = {arm: materialized(arm) for arm in ARMS}
    actual = changed(configs[ARMS[0]], configs[ARMS[1]])
    if actual != ALLOWLIST:
        raise RuntimeError(f"config allowlist gate failed: {sorted(actual)}")
    required = {
        "seed": 0, "load_depth": True, "load_normal": False,
        "w_depth": 0.03, "depth_warmup": 7000, "depth_schedule": "ramp",
        "depth_ramp_steps": 5000, "depth_prior_alignment": "none",
        "w_mvc": 0.5, "w_nc": 0.05, "w_distort": 0.0,
        "w_normal": 0.0, "w_external_als_depth": 0.0,
        "w_external_als_normal": 0.0, "max_iter": 20000,
    }
    for arm, cfg in configs.items():
        mismatch = {k: [cfg.get(k), v] for k, v in required.items() if cfg.get(k) != v}
        if mismatch or len(cfg["visible_views"]) != 55 or len(cfg["train_views"]) != 47 or len(cfg["eval_views"]) != 8:
            raise RuntimeError(f"{arm} frozen config mismatch: {mismatch}")
    return "\n".join([
        "single_variable: raw COLMAP rendered-depth representation",
        "control: EXPECTED = alpha-weighted Gaussian-center camera-Z",
        "intervention: SURFACE_INTERSECTION = alpha-weighted exact ray-surfel intersection camera-Z",
        "surface_formula: sum(alpha*T*(s_x*T_wx+s_y*T_wy+T_wz))/sum(alpha*T)",
        "no_hit: historical EXPECTED fallback; raw-valid mask unchanged",
        "allowed_arm_delta_keys: depth_supervision_mode, out_dir, run_id",
        "actual_arm_delta_keys: " + ", ".join(sorted(actual)),
        "same_source_full_state: DEPTH03/R1 step_007000.pt",
        "same_depth_mask_loss_weight_schedule_MVC_NC_densification_views_seed_GPU: true",
        "scientific_verdict: null", "",
    ])


def preflight() -> None:
    for relative in ("control/runtime_configs", "control/effective_configs", "control/receipts", "logs", "representative_images"):
        (TASK_ROOT / relative).mkdir(parents=True, exist_ok=True)
    required_paths = [COMMON_CONFIG, *ARM_CONFIGS.values(), BASE_CONFIG, SOURCE_CHECKPOINT,
                      Path(str(SOURCE_CHECKPOINT) + ".sha256"), SOURCE_EFFECTIVE,
                      SOURCE_INPUTS, MVS_AUDIT_INPUTS,
                      TASK_ROOT / "control/surface_overlay_audit.json",
                      TASK_ROOT / "control/surface_python_overlay/surface_overlay_manifest.json"]
    for path in required_paths:
        if not path.is_file():
            raise FileNotFoundError(path)
    if not base.checkpoint_valid(SOURCE_RUN, 7000):
        raise RuntimeError("source full-state checkpoint sidecar failed")
    overlay_audit = json.loads((TASK_ROOT / "control/surface_overlay_audit.json").read_text())
    if not overlay_audit.get("passed"):
        raise RuntimeError("surface overlay synthetic gate failed")
    for arm in ARMS:
        base.atomic_text(runtime_path(arm), yaml.safe_dump(materialized(arm), sort_keys=False))
    diff = validate_config()
    base.atomic_text(TASK_ROOT / "config_diff.txt", diff)
    source_inputs = json.loads(SOURCE_INPUTS.read_text())
    checked, failures = prior._verify_manifest_file_records(source_inputs)
    crop_root = Path(source_inputs["crop_root"])
    crop_checked = 0
    for row in source_inputs["crop_images"]["files"]:
        path = crop_root / "images" / row["basename"]
        if path.is_file() and sha256(path) == row["sha256"]:
            crop_checked += 1
        else:
            failures.append(str(path))
    depth_checked = 0
    for name, digest in source_inputs["geometric_depth_maps_sha256"].items():
        path = crop_root / "stereo/depth_maps" / f"{name}.geometric.bin"
        if path.is_file() and sha256(path) == digest:
            depth_checked += 1
        else:
            failures.append(str(path))
    mvs_inputs = json.loads(MVS_AUDIT_INPUTS.read_text())
    mvs_checked, mvs_failures = prior._verify_manifest_file_records(mvs_inputs)
    failures.extend(mvs_failures)
    if failures:
        raise RuntimeError("input SHA gate failed: " + "; ".join(failures))
    base.atomic_json(TASK_ROOT / "input_hashes.json", {
        "schema": "jointbuildgs.p2.e3_local_4906982_surface_intersection_diag_v1.inputs.v1",
        "source_training_input_manifest": {"path": str(SOURCE_INPUTS), "sha256": sha256(SOURCE_INPUTS), "live_records": checked + crop_checked + depth_checked},
        "source_mvs_manifest": {"path": str(MVS_AUDIT_INPUTS), "sha256": sha256(MVS_AUDIT_INPUTS), "live_records": mvs_checked},
        "source_full_state_checkpoint": {"path": str(SOURCE_CHECKPOINT), "sha256": sha256(SOURCE_CHECKPOINT)},
        "reuse_contract": {"crop_regenerated": False, "cameras_regenerated": False, "view_roles_regenerated": False, "sparse_seed_regenerated": False, "colmap_depth_regenerated": False},
        "scientific_verdict": None,
    })
    contract = {
        "schema": "jointbuildgs.p2.e3_local_4906982_surface_intersection_diag_v1.contract.v1",
        "task_id": TASK_ID, "building_id": "DEBY_LOD2_4906982", "status": "PREFLIGHT_BOUND",
        "causal_question": "Does exact perspective-correct ray-surfel surface-intersection depth improve geometry when used only for raw COLMAP L1 supervision?",
        "arms": {"EXPECTED": {"prediction": "renderer.depth"}, "SURFACE_INTERSECTION": {"prediction": "renderer.depth_surface_intersection", "no_hit": "renderer.depth fallback"}},
        "sole_training_delta": "depth_supervision_mode", "source_completed_updates": 7000,
        "required_exact_state_sections": ["model", "optimizers", "strategy", "grouping_state", "rng_state", "loss_log_cursor", "learning_runs_started"],
        "sequential_same_gpu": {"host_index": 1, "order": list(ARMS)},
        "checkpoints_completed_updates": list(CHECKPOINTS), "lod2_training_use": False,
        "lod2_reference_use": "evaluation_only_after_training", "new_loss": False,
        "multiview_densification": False, "surface_overlay_synthetic_gate": overlay_audit,
        "training_experiments_started": 0, "scientific_verdict": None,
    }
    base.atomic_json(TASK_ROOT / "experiment_contract.json", contract)
    sources = [Path(__file__), REPO / "src/stage2/train.py", REPO / "src/stage2/renderer.py",
               REPO / "src/stage2/loss/multiview.py", REPO / "tests/stage2/test_depth_supervision_mode.py",
               REPO / "scripts/p2/e3_local_4906982_surface_intersection_diag_v1/prepare_gsplat_overlay.py",
               REPO / "scripts/p2/e3_local_4906982_surface_intersection_diag_v1/audit_surface_overlay.py",
               COMMON_CONFIG, *ARM_CONFIGS.values()]
    previous = json.loads((TASK_ROOT / "provenance.json").read_text()) if (TASK_ROOT / "provenance.json").is_file() else {}
    base.atomic_json(TASK_ROOT / "provenance.json", {
        "schema": "jointbuildgs.p2.e3_local_4906982_surface_intersection_diag_v1.provenance.v1",
        "task_id": TASK_ID, "git": base.git_record(), "docker_image": base.image_record(),
        "gpu": base.gpu_record(), "source_files_sha256": {str(p.relative_to(REPO)): sha256(p) for p in sources},
        "external_source_sha256": {str(SOURCE_CHECKPOINT): sha256(SOURCE_CHECKPOINT), str(SOURCE_INPUTS): sha256(SOURCE_INPUTS), str(MVS_AUDIT_INPUTS): sha256(MVS_AUDIT_INPUTS)},
        "surface_overlay_manifest": json.loads((TASK_ROOT / "control/surface_python_overlay/surface_overlay_manifest.json").read_text()),
        "random_seed": 0, "started_utc": previous.get("started_utc") or base.now(), "ended_utc": None,
        "commands": previous.get("commands", []), "return_codes": previous.get("return_codes", []),
        "scientific_verdict": None,
    })
    base.atomic_text(TASK_ROOT / "NOTES.md", f"# {TASK_ID}\n\nStatus: `PREFLIGHT_BOUND`. Training not started. Scientific verdict: `null`.\n")
    base.atomic_text(TASK_ROOT / "issues.md", "# Issues\n\n- Initial full-overlay JIT attempts yielded while compilation was still active; partial caches are preserved under `logs/failed_preflight_cache_*`. The final two-kernel bind-mount build and synthetic gate passed.\n- A root-owned unused partial `cache/expected` directory remains isolated from all commands.\n\n`scientific_verdict: null`.\n")
    print(diff, end="")
    print(json.dumps({"verified_input_records": checked + crop_checked + depth_checked + mvs_checked, "surface_gate": True, "task_root": str(TASK_ROOT)}, indent=2))


def probe_config(arm: str) -> Path:
    cfg = materialized(arm)
    root = TASK_ROOT / "binding_probe" / arm
    cfg.update({"run_id": f"BINDING_PROBE_{arm}", "out_dir": base.container_path(root), "max_iter": 1,
                "eval_every": 100000, "ckpt_every": 100000, "full_state_resume": "off",
                "full_state_checkpoint_steps": list(CHECKPOINTS)})
    path = TASK_ROOT / "control/runtime_configs" / f"binding_probe_{arm.lower()}.yaml"
    base.atomic_text(path, yaml.safe_dump(cfg, sort_keys=False))
    return path


def binding_probe() -> None:
    for arm in ARMS:
        stable = TASK_ROOT / "control/effective_configs" / f"{arm.lower()}.json"
        if stable.is_file():
            continue
        config = probe_config(arm)
        root = TASK_ROOT / "binding_probe" / arm
        argv = docker_base(surface=arm == "SURFACE_INTERSECTION", gpu=True) + ["python", "-c", base.DETERMINISTIC_WRAPPER, "--config", base.container_path(config)]
        log = TASK_ROOT / "logs" / f"binding_probe_{arm.lower()}.log"
        started = base.now()
        with log.open("w") as stream:
            proc = subprocess.run(argv, text=True, stdout=stream, stderr=subprocess.STDOUT)
        base.record_operation(f"binding_probe_{arm}", argv, proc.returncode, started, base.now())
        if proc.returncode != 0:
            raise RuntimeError(f"binding probe failed: {arm}; inspect {log}")
        effective = json.loads((root / "effective_config.json").read_text())
        effective.pop("full_state_runtime", None)
        base.atomic_json(stable, effective)
    left = json.loads((TASK_ROOT / "control/effective_configs/expected.json").read_text())
    right = json.loads((TASK_ROOT / "control/effective_configs/surface_intersection.json").read_text())
    actual = changed(left, right)
    expected = {"depth_supervision_mode", "depth_supervision_prediction"}
    gate = {"actual_difference": sorted(actual), "expected_difference": sorted(expected),
            "passed": actual == expected, "scientific_verdict": None}
    base.atomic_json(TASK_ROOT / "control/effective_config_gate.json", gate)
    if not gate["passed"]:
        raise RuntimeError(f"effective config gate failed: {sorted(actual)}")
    print(json.dumps(gate, indent=2))


def fork_7k() -> None:
    prior.fork_7k()


def launch(arm: str) -> dict[str, Any]:
    root = run_root(arm)
    receipt = TASK_ROOT / "control/receipts" / f"train_{arm}_R1.json"
    if base.checkpoint_valid(root, 20000):
        return json.loads(receipt.read_text()) if receipt.is_file() else {"status": "ALREADY_COMPLETE"}
    name = "jbgs-surface-diag-" + arm.lower().replace("_", "-")
    subprocess.run(["docker", "rm", "-f", name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    argv = docker_base(surface=arm == "SURFACE_INTERSECTION", gpu=True, name=name, keep=True) + ["python", "-c", base.DETERMINISTIC_WRAPPER, "--config", base.container_path(runtime_path(arm))]
    log = root / "logs/train.log"; vram = root / "logs/vram_used_mib.tsv"
    log.parent.mkdir(parents=True, exist_ok=True)
    started = base.now(); began = time.monotonic(); max_used = 0
    with log.open("a") as stream, vram.open("a") as meter:
        if vram.stat().st_size == 0:
            meter.write("utc\tused_mib\n")
        proc = subprocess.Popen(argv, text=True, stdout=stream, stderr=subprocess.STDOUT)
        while proc.poll() is None:
            sample = subprocess.run(["nvidia-smi", "--id=1", "--query-gpu=memory.used", "--format=csv,noheader,nounits"], text=True, capture_output=True)
            try:
                used = int(sample.stdout.strip()); max_used = max(max_used, used)
                meter.write(f"{base.now()}\t{used}\n"); meter.flush()
            except ValueError:
                pass
            time.sleep(2)
        rc = proc.wait()
    ended = base.now(); subprocess.run(["docker", "rm", "-f", name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    body = {"arm": arm, "started_utc": started, "ended_utc": ended,
            "wall_seconds": time.monotonic() - began, "return_code": rc,
            "max_selected_gpu_used_mib": max_used,
            "required_checkpoint_valid": base.checkpoint_valid(root, 20000), "scientific_verdict": None}
    base.atomic_json(receipt, body); base.record_operation(f"train_{arm}_R1", argv, rc, started, ended)
    if rc != 0 or not body["required_checkpoint_valid"]:
        raise RuntimeError(f"{arm} training failed rc={rc}; inspect {log}")
    return body


def train() -> None:
    gate = TASK_ROOT / "control/common_state_gate_7000.json"
    if not gate.is_file() or not json.loads(gate.read_text()).get("passed"):
        raise RuntimeError("7k exact state gate required")
    contract = json.loads((TASK_ROOT / "experiment_contract.json").read_text())
    contract["training_experiments_started"] = 2
    base.atomic_json(TASK_ROOT / "experiment_contract.json", contract)
    for arm in ARMS:
        print(json.dumps(launch(arm), indent=2), flush=True)
    missing = [(arm, step) for arm in ARMS for step in CHECKPOINTS if not base.checkpoint_valid(run_root(arm), step)]
    if missing:
        raise RuntimeError(f"missing checkpoints: {missing}")


def adapt(code: str) -> str:
    result = code.replace("'MVC05'", "'SURFACE_INTERSECTION'").replace("'MVC0'", "'EXPECTED'")
    result = result.replace("MVC05", "SURFACE_INTERSECTION").replace("MVC0", "EXPECTED")
    result = result.replace("mvc0_r1.yaml", "expected_r1.yaml")
    result = result.replace("replicas=['R1','R2','R3']", "replicas=['R1']").replace("reps=['R1','R2','R3']", "reps=['R1']").replace("['R1','R2','R3']", "['R1']")
    result = result.replace("'replicates_per_arm':3", "'replicates_per_arm':1").replace("ddof=1", "ddof=0")
    result = result.replace("mvc05_minus_mvc0", "surface_intersection_minus_expected").replace("paired_mvc05_minus_mvc0", "paired_surface_intersection_minus_expected")
    for old, new in (("'cases':24", "'cases':8"), ("'classification_passed':24", "'classification_passed':8"), ("'roofer_return_code_zero':24", "'roofer_return_code_zero':8"), ("'roofer_rf_success_true':24", "'roofer_rf_success_true':8"), ("'roofer_cases':24", "'roofer_cases':8")):
        result = result.replace(old, new)
    result = result.replace("def mean(v):return sum(v)/len(v)", "def mean(v):return None if not v else sum(v)/len(v)")
    result = result.replace("def sd(v):return statistics.stdev(v) if len(v)>1 else 0.0", "def sd(v):return None if not v else (statistics.stdev(v) if len(v)>1 else 0.0)")
    return result


def analyze_checkpoints() -> None:
    base.ANALYZE_CODE = adapt(base.ANALYZE_CODE); base.analyze_checkpoints()


def stage3() -> None:
    base.STAGE3_PREP_CODE = adapt(base.STAGE3_PREP_CODE); base.STAGE3_VERIFY_CODE = adapt(base.STAGE3_VERIFY_CODE); base.ROOFER_RECORD_CODE = adapt(base.ROOFER_RECORD_CODE); base.run_stage3()


def finalize_measurements() -> None:
    base.FINALIZE_CODE = adapt(base.FINALIZE_CODE); base.finalize_measurements()


def reference_diagnostic() -> None:
    output = TASK_ROOT / "reference_diagnostic"; metrics = output / "metrics.json"
    if metrics.is_file() and json.loads(metrics.read_text()).get("status") == "COMPLETE_DIAGNOSTIC":
        print(metrics.read_text()); return
    source = yaml.safe_load((REPO / "configs/p2/e3_local_4906982_mvc_readout_diag_v1/config.yaml").read_text())
    source.update({"task_id": TASK_ID + "-REFERENCE-DIAG", "source_task_root": base.container_path(TASK_ROOT),
                   "source_runner": "/workspace/JointBuildGS/scripts/p2/e3_local_4906982_surface_intersection_diag_v1/run.py",
                   "shared_footprint": base.container_path(TASK_ROOT / "control/shared_standard_footprint_4906982.geojson"),
                   "arms": list(ARMS), "replicas": list(REPLICAS), "checkpoints": list(CHECKPOINTS), "scientific_verdict": None})
    config = TASK_ROOT / "control/reference_diagnostic.yaml"; base.atomic_text(config, yaml.safe_dump(source, sort_keys=False))
    runner = (REPO / "scripts/p2/e3_local_4906982_mvc_readout_diag_v1/run.py").read_text()
    runner = runner.replace('"MVC05"', '"SURFACE_INTERSECTION"').replace('"MVC0"', '"EXPECTED"').replace("'MVC05'", "'SURFACE_INTERSECTION'").replace("'MVC0'", "'EXPECTED'")
    runner = runner.replace('REPO = Path(__file__).resolve().parents[3]\nARTIFACT_ROOT = REPO.parent / "JointBuildGS-artifacts"', 'REPO = Path("/workspace/JointBuildGS")\nARTIFACT_ROOT = Path("/artifacts/JointBuildGS")')
    runtime = TASK_ROOT / "control/reference_diag_runtime.py"; base.atomic_text(runtime, runner)
    output.mkdir(parents=True, exist_ok=True); (output / "logs").mkdir(exist_ok=True)
    argv = ["docker", "run", "--rm", "--network", "none", "--user", f"{os.getuid()}:{os.getgid()}", "-e", "MPLCONFIGDIR=/tmp/matplotlib",
            "-v", f"{REPO}:/workspace/JointBuildGS:ro", "-v", f"{ARTIFACT_ROOT}:/artifacts/JointBuildGS:ro", "-v", f"{TASK_ROOT}:/task:rw",
            "-w", "/workspace/JointBuildGS", base.EVAL_IMAGE, "python", "/task/control/reference_diag_runtime.py", "--inside-docker", "analyze", "--config", base.container_path(config), "--output", "/task/reference_diagnostic"]
    log = output / "logs/analyze.log"; started = base.now()
    with log.open("w") as stream:
        proc = subprocess.run(argv, text=True, stdout=stream, stderr=subprocess.STDOUT)
    base.record_operation("reference_diagnostic", argv, proc.returncode, started, base.now())
    if proc.returncode != 0:
        raise RuntimeError(f"reference diagnostic failed; inspect {log}")
    print(metrics.read_text())


def mvs_surface_audit() -> None:
    output_json = TASK_ROOT / "mvs_surface_audit.json"
    output_csv = TASK_ROOT / "mvs_surface_metrics.csv"
    script = REPO / "scripts/p2/e3_local_4906982_depth_rep_diag_v1/surface_audit.py"
    mvs_npy = ARTIFACT_ROOT / "phase-payloads/p2/e3_local_4906982_mvs_transfer_diag_v1/P2-E3-LOCAL-4906982-MVS-TRANSFER-DIAG-v1/fused_seed/mvs_xyz_f32.npy"
    footprint = TASK_ROOT / "control/shared_standard_footprint_4906982.geojson"
    argv = base.eval_docker_base() + [
        "python", "/workspace/JointBuildGS/scripts/p2/e3_local_4906982_depth_rep_diag_v1/surface_audit.py",
        "--task-root", base.container_path(TASK_ROOT), "--mvs-npy", base.container_path(mvs_npy),
        "--footprint", base.container_path(footprint), "--output-json", base.container_path(output_json),
        "--output-csv", base.container_path(output_csv), "--arms", *ARMS,
    ]
    log = TASK_ROOT / "logs/mvs_surface_audit.log"; started = base.now()
    with log.open("w") as stream:
        proc = subprocess.run(argv, text=True, stdout=stream, stderr=subprocess.STDOUT)
    base.record_operation("mvs_surface_audit", argv, proc.returncode, started, base.now())
    if proc.returncode != 0:
        raise RuntimeError(f"MVS surface audit failed; inspect {log}")
    print(output_json.read_text())


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["preflight", "binding-probe", "fork-7k", "train", "analyze-checkpoints", "stage3", "finalize-measurements", "reference-diagnostic", "mvs-surface-audit", "all-training"])
    args = parser.parse_args()
    if args.command in {"preflight", "all-training"}: preflight()
    if args.command in {"binding-probe", "all-training"}: binding_probe()
    if args.command in {"fork-7k", "all-training"}: fork_7k()
    if args.command in {"train", "all-training"}: train()
    if args.command == "analyze-checkpoints": analyze_checkpoints()
    if args.command == "stage3": stage3()
    if args.command == "finalize-measurements": finalize_measurements()
    if args.command == "reference-diagnostic": reference_diagnostic()
    if args.command == "mvs-surface-audit": mvs_surface_audit()


if __name__ == "__main__":
    main()
