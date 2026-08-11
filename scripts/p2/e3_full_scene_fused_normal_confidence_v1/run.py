#!/usr/bin/env python3
"""Docker-only, add-once orchestration for the approved full-scene E3 run."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import time
from typing import Any

import yaml


REPO = Path(__file__).resolve().parents[3]
ARTIFACT_ROOT = REPO.parent / "JointBuildGS-artifacts"
TASK_ID = "P2-E3-FULL-SCENE-FUSED-NORMAL-CONFIDENCE-v1"
TASK_ROOT = ARTIFACT_ROOT / "phase-payloads/p2/e3_full_scene_fused_normal_confidence_v1" / TASK_ID
CONFIG_DIR = REPO / "configs/p2/e3_full_scene_fused_normal_confidence_v1"
COMMON_CONFIG = CONFIG_DIR / "common.yaml"
TRAINING_CONFIG = CONFIG_DIR / "training.yaml"
PREPARE_SOURCE = REPO / "scripts/p2/e3_full_scene_fused_normal_confidence_v1/prepare_targets.py"
EXTRACTOR_SOURCE = REPO / "scripts/p2/e3_full_scene_fused_normal_confidence_v1/extract_native_dmap.cpp"
PROJECT_IMAGE = "jointbuildgs:dev"
EVAL_IMAGE = "jointbuildgs:mvc-eval-v1"
OPENMVS_IMAGE = "jointbuildgs-p0-openmvs:t0"
GPU = "1"
CHECKPOINTS = (7000, 12000, 15000, 20000, 30000)
RUN_ROOT = TASK_ROOT / "arms/E3_GS_image/R1"
MATERIALIZED_TRAINING_CONFIG = TASK_ROOT / "control/training.yaml"


def load_base():
    path = REPO / "scripts/p2/e3_local_4906982_mvc_v2/run.py"
    spec = importlib.util.spec_from_file_location("e3_full_scene_runner_base", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.TASK_ID = TASK_ID
    module.TASK_ROOT = TASK_ROOT
    module.GPU = GPU
    module.CHECKPOINTS = CHECKPOINTS
    module.ARMS = ("E3_GS_image",)
    module.REPLICAS = ("R1",)
    return module


base = load_base()


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def atomic_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(value, encoding="utf-8")
    os.replace(temporary, path)


def atomic_json(path: Path, value: Any) -> None:
    atomic_text(path, json.dumps(value, indent=2, sort_keys=True) + "\n")


def artifact_path(value: str) -> Path:
    prefix = "/artifacts/JointBuildGS/"
    if not value.startswith(prefix):
        raise RuntimeError(f"not a canonical artifact path: {value}")
    return ARTIFACT_ROOT / value[len(prefix):]


def repo_path(value: str) -> Path:
    prefix = "/workspace/JointBuildGS/"
    if not value.startswith(prefix):
        raise RuntimeError(f"not a canonical repository path: {value}")
    return REPO / value[len(prefix):]


def docker_project(*, gpu: bool = False, image: str = PROJECT_IMAGE) -> list[str]:
    argv = ["docker", "run", "--rm", "--network", "none"]
    if gpu:
        argv += ["--gpus", f"device={GPU}", "--ipc=host"]
    argv += [
        "--user", f"{os.getuid()}:{os.getgid()}", "--cpus", "16", "--memory", "96g", "--pids-limit", "4096",
        "-e", "HOME=/tmp", "-e", "PYTHONDONTWRITEBYTECODE=1", "-e", "PYTHONPATH=/workspace/JointBuildGS",
        "-e", "OPENCV_IO_ENABLE_OPENEXR=1",
        "-v", f"{REPO}:/workspace/JointBuildGS:ro",
        "-v", f"{ARTIFACT_ROOT}:/artifacts/JointBuildGS",
        "-v", f"{TASK_ROOT / 'cache/torch_extensions'}:/root/.cache/torch_extensions",
        "-w", "/workspace/JointBuildGS", image,
    ]
    return argv


def record(label: str, argv: list[str], process: subprocess.CompletedProcess[Any], started: str) -> None:
    base.record_operation(label, argv, int(process.returncode), started, now())


def _validate_training_config(common: dict[str, Any], training: dict[str, Any]) -> None:
    required = {
        "task_id": TASK_ID,
        "condition_id": "E3_GS_image",
        "seed": 0,
        "exact_view_count": 937,
        "downscale": 1.0,
        "load_depth": True,
        "depth_supervision_mode": "expected",
        "depth_loss_type": "l1",
        "w_depth": 0.03,
        "depth_warmup": 7000,
        "depth_schedule": "ramp",
        "depth_ramp_steps": 5000,
        "load_normal": True,
        "normal_prior_orientation": "unsigned",
        "w_normal": 0.005,
        "normal_warmup": 7000,
        "normal_schedule": "ramp",
        "normal_ramp_steps": 5000,
        "load_semantic": False,
        "w_sem": 0.0,
        "w_mvc": 0.5,
        "w_nc": 0.05,
        "w_distort": 0.0,
        "reset_every": 100000,
        "max_iter": 30000,
        "full_state_checkpoint": True,
        "full_state_checkpoint_steps": list(CHECKPOINTS),
        "scientific_verdict": None,
    }
    mismatch = {key: [training.get(key), value] for key, value in required.items() if training.get(key) != value}
    if mismatch:
        raise RuntimeError(f"approved E3 training lock drift: {mismatch}")
    if training["data_root"] != common["output_data_root"] or training["normal_dir"] != common["output_normal_dir"]:
        raise RuntimeError("training target binding differs from common contract")
    if any(float(training.get(key, 0.0) or 0.0) != 0.0 for key in ("w_mono_depth", "w_mono_normal", "w_structure", "w_mutual")):
        raise RuntimeError("unapproved supervision is active")
    if training.get("external_als_prior_dir") or training.get("lod_prior_dir"):
        raise RuntimeError("external prior is forbidden in E3")


def _mapping(common: dict[str, Any]) -> dict[str, Any]:
    manifest = json.loads(repo_path(common["exact_view_manifest"]).read_text(encoding="utf-8"))
    exact_names = [str(row["basename"]) for row in manifest["rows"]]
    log_path = artifact_path(common["native_dmap_log"])
    pattern = re.compile(r"Image loaded\s+(\d+):\s+(\S+)")
    loaded: dict[int, str] = {}
    for line in log_path.read_text(encoding="utf-8", errors="replace").splitlines():
        match = pattern.search(line)
        if match:
            loaded[int(match.group(1))] = match.group(2)
    if len(loaded) != 937 or set(loaded.values()) != set(exact_names):
        raise RuntimeError("OpenMVS log image mapping differs from exact-937")
    dmap_dir = artifact_path(common["native_dmap_dir"])
    files = sorted(dmap_dir.glob("depth*.dmap"))
    indexes = {int(path.stem[5:]): path for path in files}
    if len(indexes) != int(common["expected_native_dmap_count"]):
        raise RuntimeError(f"native DMap count drift: {len(indexes)}")
    unknown = sorted(set(indexes) - set(loaded))
    if unknown:
        raise RuntimeError(f"native DMap indexes absent from image log: {unknown}")
    mapped = [
        {"dmap_index": index, "image_name": loaded[index], "relative_path": path.name, "bytes": path.stat().st_size}
        for index, path in sorted(indexes.items())
    ]
    mapped_names = {row["image_name"] for row in mapped}
    missing_names = [name for name in exact_names if name not in mapped_names]
    if len(missing_names) != int(common["expected_native_missing_count"]):
        raise RuntimeError("native missing count drift")
    return {
        "schema": "jointbuildgs.p2.e3_full_scene_fused_normal_confidence_v1.native_mapping.v1",
        "source_log": common["native_dmap_log"],
        "source_log_sha256": sha256(log_path),
        "exact_view_count": len(exact_names),
        "mapped_count": len(mapped),
        "missing_count": len(missing_names),
        "mapped": mapped,
        "missing_image_names": missing_names,
        "scientific_verdict": None,
    }


def preflight() -> None:
    marker = TASK_ROOT / "experiment_contract.json"
    if TASK_ROOT.exists() and any(TASK_ROOT.iterdir()) and not marker.is_file():
        raise RuntimeError(f"nonempty unbound namespace: {TASK_ROOT}")
    for child in ("control/bin", "control/receipts", "logs", "cache/torch_extensions", "representative_images"):
        (TASK_ROOT / child).mkdir(parents=True, exist_ok=True)
    common = yaml.safe_load(COMMON_CONFIG.read_text(encoding="utf-8"))
    training = yaml.safe_load(TRAINING_CONFIG.read_text(encoding="utf-8"))
    if common.get("status") != "USER_APPROVED_FOR_EXECUTION" or common.get("scientific_verdict", "missing") is not None:
        raise RuntimeError("full-scene E3 execution approval/verdict lock drift")
    _validate_training_config(common, training)
    training_text = TRAINING_CONFIG.read_text(encoding="utf-8")
    if MATERIALIZED_TRAINING_CONFIG.is_file() and MATERIALIZED_TRAINING_CONFIG.read_text(encoding="utf-8") != training_text:
        raise RuntimeError("materialized training config differs from the approved repository config")
    atomic_text(MATERIALIZED_TRAINING_CONFIG, training_text)
    manifest = repo_path(common["exact_view_manifest"])
    if sha256(manifest) != common["exact_view_manifest_sha256"]:
        raise RuntimeError("exact-view manifest hash drift")
    mesh = artifact_path(common["source_mesh"])
    if mesh.stat().st_size != int(common["source_mesh_bytes"]) or sha256(mesh) != common["source_mesh_sha256"]:
        raise RuntimeError("source fused mesh identity drift")
    seed = artifact_path(training["init_pointcloud"])
    if seed.stat().st_size != 1_242_719 or sha256(seed) != "ad7d1192de507a4834181d8b61a50431829b3413bf8425497507c2396feabdc4":
        raise RuntimeError("full-scene neutral dense seed identity drift")
    mapping = _mapping(common)
    atomic_json(TASK_ROOT / "control/native_dmap_mapping.json", mapping)
    diff = """approved full-scene E3 transfer
source recipe: local FUSED_VIS_CONF_FUSED_NORMAL_CONFIDENCE through its validated 20k checkpoint
full-scene primary endpoint: 30000 updates; 20000 retained as stability diagnostic, not selected post hoc
scale adaptation: fixed 55-view crop -> exact 937-view full scene
initialization adaptation: local sparse crop -> frozen full-scene sparse plus neutral dense seed
unchanged objectives: expected-depth L1 w=0.03, unsigned fused-normal w=0.005, MVC=0.5, NC=0.05, distortion=0
unchanged schedules: depth/normal/MVC warmup=7000 ramp=5000
unchanged refinement: stop=20000, reset_every=100000, max_gaussians=800000
semantic/external ALS/LoD supervision: off
native evidence: 924 mapped DMaps; 13 zero-supervision RGB/MVC-retained views
checkpoints: 7000, 12000, 15000, 20000, 30000
scientific_verdict: null
"""
    atomic_text(TASK_ROOT / "config_diff.txt", diff)
    sources = [COMMON_CONFIG, TRAINING_CONFIG, Path(__file__), PREPARE_SOURCE, EXTRACTOR_SOURCE,
               REPO / "src/stage2/train.py", REPO / "src/stage2/dataloader.py",
               REPO / "src/stage2/renderer.py", REPO / "src/stage2/loss/data_fitting.py",
               REPO / "src/stage2/loss/multiview.py"]
    inputs = {
        "schema": "jointbuildgs.p2.e3_full_scene_fused_normal_confidence_v1.inputs.v1",
        "exact_view_manifest": {"path": common["exact_view_manifest"], "sha256": common["exact_view_manifest_sha256"], "count": 937},
        "source_mesh": {"path": common["source_mesh"], "bytes": mesh.stat().st_size, "sha256": sha256(mesh)},
        "neutral_dense_seed": {"path": training["init_pointcloud"], "bytes": seed.stat().st_size, "sha256": sha256(seed)},
        "native_mapping": {"path": "control/native_dmap_mapping.json", "sha256": sha256(TASK_ROOT / "control/native_dmap_mapping.json")},
        "source_files_sha256": {str(path.relative_to(REPO)): sha256(path) for path in sources},
        "materialized_training_config": {
            "path": str(MATERIALIZED_TRAINING_CONFIG.relative_to(TASK_ROOT)),
            "sha256": sha256(MATERIALIZED_TRAINING_CONFIG),
        },
        "lod2_training_use": False,
        "scientific_verdict": None,
    }
    atomic_json(TASK_ROOT / "input_hashes.json", inputs)
    contract = {
        "schema": "jointbuildgs.p2.e3_full_scene_fused_normal_confidence_v1.contract.v1",
        "task_id": TASK_ID,
        "condition_id": "E3_GS_image",
        "status": "PREFLIGHT_BOUND",
        "user_approval": "GRANTED_2026-08-11",
        "design": "approved full-scene transfer of the latest fused-depth/fused-normal/new-mask/MVC image-only recipe with a precommitted 30k primary endpoint",
        "views": {"rgb_pose": 937, "native_dmap": 924, "zero_supervision_rgb_mvc_retained": 13},
        "checkpoints": list(CHECKPOINTS),
        "primary_endpoint_updates": 30000,
        "diagnostic_checkpoint_updates": 20000,
        "checkpoint_selection_rule": "30k is primary; 20k is diagnostic and cannot replace 30k post hoc",
        "seed": 0,
        "external_prior": False,
        "semantic_loss": False,
        "target_generation_must_pass_before_training": True,
        "official_PASS_usable": None,
        "scientific_verdict": None,
    }
    atomic_json(marker, contract)
    provenance_path = TASK_ROOT / "provenance.json"
    previous = json.loads(provenance_path.read_text(encoding="utf-8")) if provenance_path.is_file() else {}
    provenance = {
        "schema": "jointbuildgs.p2.e3_full_scene_fused_normal_confidence_v1.provenance.v1",
        "task_id": TASK_ID,
        "git": base.git_record(),
        "docker_images": {"project": base.image_record(), "evaluation": EVAL_IMAGE, "openmvs": OPENMVS_IMAGE},
        "gpu": base.gpu_record(),
        "input_hashes_sha256": sha256(TASK_ROOT / "input_hashes.json"),
        "started_utc": previous.get("started_utc") or now(),
        "ended_utc": previous.get("ended_utc"),
        "commands": previous.get("commands", []),
        "return_codes": previous.get("return_codes", []),
        "scientific_verdict": None,
    }
    atomic_json(provenance_path, provenance)
    atomic_text(TASK_ROOT / "NOTES.md", f"# {TASK_ID}\n\nStatus: `PREFLIGHT_BOUND`. Target generation and training have not started.\n\nscientific_verdict: null\n")
    atomic_text(TASK_ROOT / "issues.md", "# Issues\n\n- 13 exact RGB/pose views have no native OpenMVS DMap and are frozen as zero depth/normal supervision while remaining in RGB/MVC membership.\n\nscientific_verdict: null\n")
    print(json.dumps({"status": "PREFLIGHT_BOUND", "task_root": str(TASK_ROOT), "mapped_dmaps": mapping["mapped_count"], "missing_dmaps": mapping["missing_count"]}, indent=2))


def extract_native() -> None:
    mapping_path = TASK_ROOT / "control/native_dmap_mapping.json"
    if not mapping_path.is_file():
        raise RuntimeError("preflight mapping is required")
    mapping = json.loads(mapping_path.read_text(encoding="utf-8"))
    output = TASK_ROOT / "native_dmap"
    receipt_path = TASK_ROOT / "control/native_dmap_extraction.json"
    if receipt_path.is_file():
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        if receipt.get("status") == "COMPLETE" and len(list(output.glob("*.depth.npy"))) == 924 and len(list(output.glob("*.normal.npy"))) == 924:
            print(json.dumps({key: value for key, value in receipt.items() if key != "rows"}, indent=2))
            return
    output.mkdir(parents=True, exist_ok=True)
    binary = TASK_ROOT / "control/bin/extract_native_dmap"
    build_command = (
        "g++ -std=c++14 -O2 scripts/p2/e3_full_scene_fused_normal_confidence_v1/extract_native_dmap.cpp "
        "-I/usr/local/include/OpenMVS -I/usr/local/include/eigen3 -L/usr/local/lib/OpenMVS "
        "-lMVS -lIO -lCommon -lMath $(pkg-config --cflags --libs opencv) "
        "-lboost_iostreams -lboost_serialization -lpthread "
        f"-o /artifacts/JointBuildGS/{binary.relative_to(ARTIFACT_ROOT)}"
    )
    argv = ["docker", "run", "--rm", "--network", "none", "-v", f"{REPO}:/workspace/JointBuildGS:ro", "-v", f"{ARTIFACT_ROOT}:/artifacts/JointBuildGS", "-w", "/workspace/JointBuildGS", OPENMVS_IMAGE, "bash", "-lc", build_command]
    started = now()
    with (TASK_ROOT / "logs/build_native_extractor.log").open("w") as stream:
        process = subprocess.run(argv, text=True, stdout=stream, stderr=subprocess.STDOUT)
    record("build_native_extractor", argv, process, started)
    if process.returncode:
        raise RuntimeError("native DMap extractor build failed")
    dmap_dir = artifact_path(yaml.safe_load(COMMON_CONFIG.read_text())["native_dmap_dir"])
    rows: list[dict[str, Any]] = []
    for order, row in enumerate(mapping["mapped"], start=1):
        name = row["image_name"]
        stem = Path(name).stem
        source = dmap_dir / row["relative_path"]
        targets = [output / f"{stem}.depth.npy", output / f"{stem}.confidence.npy", output / f"{stem}.normal.npy"]
        if not all(path.is_file() for path in targets):
            command = ["docker", "run", "--rm", "--network", "none", "-v", f"{ARTIFACT_ROOT}:/artifacts/JointBuildGS", OPENMVS_IMAGE,
                       f"/artifacts/JointBuildGS/{binary.relative_to(ARTIFACT_ROOT)}", f"/artifacts/JointBuildGS/{source.relative_to(ARTIFACT_ROOT)}",
                       *[f"/artifacts/JointBuildGS/{path.relative_to(ARTIFACT_ROOT)}" for path in targets]]
            with (TASK_ROOT / "logs/extract_native_dmaps.log").open("a") as stream:
                process = subprocess.run(command, text=True, stdout=stream, stderr=subprocess.STDOUT)
            if process.returncode:
                raise RuntimeError(f"native DMap extraction failed: {row['relative_path']}")
        rows.append({
            **row,
            "source_sha256": sha256(source),
            "depth_sha256": sha256(targets[0]),
            "confidence_sha256": sha256(targets[1]),
            "normal_sha256": sha256(targets[2]),
        })
        if order % 25 == 0 or order == len(mapping["mapped"]):
            print(json.dumps({"extracted": order, "total": len(mapping["mapped"]), "name": name}), flush=True)
    receipt = {
        "schema": "jointbuildgs.p2.e3_full_scene_fused_normal_confidence_v1.native_extract.v1",
        "status": "COMPLETE",
        "mapped_count": len(rows),
        "missing_count": mapping["missing_count"],
        "extractor_source_sha256": sha256(EXTRACTOR_SOURCE),
        "extractor_binary_sha256": sha256(binary),
        "docker_image": OPENMVS_IMAGE,
        "rows": rows,
        "scientific_verdict": None,
    }
    atomic_json(receipt_path, receipt)
    print(json.dumps({key: value for key, value in receipt.items() if key != "rows"}, indent=2))


def prepare_targets() -> None:
    extract_native()
    argv = docker_project(image=EVAL_IMAGE) + ["python", str(PREPARE_SOURCE.relative_to(REPO))]
    started = now()
    log = TASK_ROOT / "logs/prepare_targets.log"
    with log.open("w") as stream:
        process = subprocess.run(argv, text=True, stdout=stream, stderr=subprocess.STDOUT)
    record("prepare_targets", argv, process, started)
    if process.returncode:
        raise RuntimeError(f"target preparation gate failed; inspect {log}")
    definition = json.loads((TASK_ROOT / "target_definition.json").read_text(encoding="utf-8"))
    if definition.get("status") != "GATE_PASSED" or not all(definition["gate_checks"].values()):
        raise RuntimeError("target definition did not pass all frozen gates")
    contract_path = TASK_ROOT / "experiment_contract.json"
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    contract["status"] = "TARGETS_FROZEN_TRAINING_AUTHORIZED"
    contract["target_definition_sha256"] = sha256(TASK_ROOT / "target_definition.json")
    atomic_json(contract_path, contract)
    atomic_text(TASK_ROOT / "NOTES.md", f"# {TASK_ID}\n\nStatus: `TARGETS_FROZEN_TRAINING_AUTHORIZED`. Main training has not started.\n\nscientific_verdict: null\n")
    print(json.dumps(definition, indent=2, sort_keys=True))


def binding_probe() -> None:
    definition_path = TASK_ROOT / "target_definition.json"
    if not definition_path.is_file() or json.loads(definition_path.read_text()).get("status") != "GATE_PASSED":
        raise RuntimeError("frozen target gate is required")
    code = r'''
import json,sys,yaml,numpy as np
from pathlib import Path
from src.stage2.dataloader import ColmapDataset
cfg=yaml.safe_load(Path(sys.argv[1]).read_text())
manifest=json.loads(Path(cfg['exact_view_manifest']).read_text())
names=[row['basename'] for row in manifest['rows']]
ds=ColmapDataset(cfg['data_root'],downscale=cfg['downscale'],load_depth=True,load_normal=True,load_semantic=False,normal_dir=cfg['normal_dir'],visible_views=names)
if len(ds.frames)!=937 or [f.name for f in ds.frames]!=names: raise RuntimeError('dataset membership drift')
missing_depth=[f.name for f in ds.frames if f.depth_path is None]
missing_normal=[f.name for f in ds.frames if f.normal_path is None]
if missing_depth or missing_normal: raise RuntimeError(f'aux inventory incomplete depth={len(missing_depth)} normal={len(missing_normal)}')
zero_depth=zero_normal=0
for i in range(len(ds)):
 b=ds[i]; zero_depth+=int(not bool(b['depth_mask'].any())); zero_normal+=int(not bool(b['normal_mask'].any()))
body={'schema':'jointbuildgs.p2.e3_full_scene_fused_normal_confidence_v1.binding_probe.v1','views':len(ds),'depth_maps':937,'normal_maps':937,'zero_depth_views':zero_depth,'zero_normal_views':zero_normal,'expected_zero_native_views':13,'passed':zero_depth==13 and zero_normal>=13,'scientific_verdict':None}
Path(sys.argv[2]).write_text(json.dumps(body,indent=2,sort_keys=True)+'\n');print(json.dumps(body,indent=2))
raise SystemExit(0 if body['passed'] else 3)
'''
    output = TASK_ROOT / "control/binding_probe.json"
    argv = docker_project(image=EVAL_IMAGE) + ["python", "-c", code, f"/workspace/JointBuildGS/{TRAINING_CONFIG.relative_to(REPO)}", f"/artifacts/JointBuildGS/{output.relative_to(ARTIFACT_ROOT)}"]
    started = now()
    process = subprocess.run(argv, text=True, capture_output=True)
    record("binding_probe", argv, process, started)
    atomic_text(TASK_ROOT / "logs/binding_probe.log", (process.stdout or "") + (process.stderr or ""))
    if process.returncode:
        raise RuntimeError(f"binding probe failed: {process.stdout}{process.stderr}")
    print(output.read_text(encoding="utf-8"))


def _launch_training_30k(label: str, root: Path, config: Path) -> dict[str, Any]:
    """Launch the inherited deterministic trainer with the new 30k completion gate."""
    final_step = 30000
    receipt = TASK_ROOT / "control/receipts" / f"{label}.json"
    if base.checkpoint_valid(root, final_step):
        if receipt.is_file():
            return json.loads(receipt.read_text())
        name = "jbgs-" + label.lower().replace("_", "-")
        inspect_process = subprocess.run(
            ["docker", "inspect", name], text=True, capture_output=True,
        )
        if inspect_process.returncode:
            raise RuntimeError("30k checkpoint exists but the retained runtime container is unavailable for receipt recovery")
        container = json.loads(inspect_process.stdout)[0]
        state = container["State"]
        vram_path = root / "logs/vram_used_mib.tsv"
        used_values = []
        if vram_path.is_file():
            for line in vram_path.read_text(encoding="utf-8", errors="replace").splitlines()[1:]:
                try:
                    used_values.append(int(line.split("\t", 1)[1]))
                except (IndexError, ValueError):
                    continue
        started = str(state.get("StartedAt"))
        ended = str(state.get("FinishedAt"))
        start_time = datetime.fromisoformat(started.replace("Z", "+00:00"))
        end_time = datetime.fromisoformat(ended.replace("Z", "+00:00"))
        body = {
            "schema": "jointbuildgs.p2.e3_full_scene_fused_normal_confidence_v1.runtime.v1",
            "status": "RECOVERED_FROM_COMPLETED_RETAINED_CONTAINER",
            "label": label,
            "started_utc": started,
            "ended_utc": ended,
            "wall_seconds": (end_time - start_time).total_seconds(),
            "max_selected_gpu_used_mib": max(used_values) if used_values else None,
            "return_code": int(state["ExitCode"]),
            "required_checkpoint": final_step,
            "required_checkpoint_valid": True,
            "recovery_evidence": {
                "container_name": name,
                "container_id": container["Id"],
                "container_status": state["Status"],
                "checkpoint_sha256": sha256(root / "ckpt/step_030000.pt"),
                "checkpoint_sidecar_sha256": (root / "ckpt/step_030000.pt.sha256").read_text().split()[0],
                "vram_monitor_scope": "host_launcher_lifetime_only",
                "vram_log_last_utc": vram_path.read_text(encoding="utf-8", errors="replace").splitlines()[-1].split("\t", 1)[0] if used_values else None,
            },
            "scientific_verdict": None,
        }
        if body["return_code"] != 0 or body["recovery_evidence"]["container_status"] != "exited":
            raise RuntimeError(f"retained runtime container is not a successful completed run: {state}")
        if body["recovery_evidence"]["checkpoint_sha256"] != body["recovery_evidence"]["checkpoint_sidecar_sha256"]:
            raise RuntimeError("30k checkpoint recovery hash mismatch")
        atomic_json(receipt, body)
        base.record_operation(
            f"{label}_receipt_recovery",
            ["docker", "inspect", name],
            inspect_process.returncode,
            now(),
            now(),
        )
        return body
    name = "jbgs-" + label.lower().replace("_", "-")
    subprocess.run(["docker", "rm", "-f", name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    argv = base.docker_base(gpu=True, name=name, keep=True) + [
        "python", "-c", base.DETERMINISTIC_WRAPPER, "--config", base.container_path(config),
    ]
    log = root / "logs/train.log"
    vram = root / "logs/vram_used_mib.tsv"
    log.parent.mkdir(parents=True, exist_ok=True)
    started = now()
    began = time.monotonic()
    max_used = 0
    with log.open("a", encoding="utf-8") as stream, vram.open("a", encoding="utf-8") as meter:
        if vram.stat().st_size == 0:
            meter.write("utc\tused_mib\n")
        process = subprocess.Popen(argv, text=True, stdout=stream, stderr=subprocess.STDOUT)
        while process.poll() is None:
            sample = subprocess.run(
                ["nvidia-smi", f"--id={GPU}", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
                text=True, capture_output=True,
            )
            try:
                used = int(sample.stdout.strip())
                max_used = max(max_used, used)
                meter.write(f"{now()}\t{used}\n")
                meter.flush()
            except ValueError:
                pass
            time.sleep(2)
        return_code = process.wait()
    ended = now()
    subprocess.run(["docker", "rm", "-f", name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    valid = base.checkpoint_valid(root, final_step)
    body = {
        "schema": "jointbuildgs.p2.e3_full_scene_fused_normal_confidence_v1.runtime.v1",
        "label": label,
        "started_utc": started,
        "ended_utc": ended,
        "wall_seconds": time.monotonic() - began,
        "max_selected_gpu_used_mib": max_used,
        "return_code": return_code,
        "required_checkpoint": final_step,
        "required_checkpoint_valid": valid,
        "scientific_verdict": None,
    }
    atomic_json(receipt, body)
    base.record_operation(label, argv, return_code, started, ended)
    if not valid or return_code != 0:
        raise RuntimeError(f"{label} failed rc={return_code}; inspect {log}")
    return body


def train() -> None:
    binding_probe()
    contract = json.loads((TASK_ROOT / "experiment_contract.json").read_text(encoding="utf-8"))
    if contract.get("status") != "TARGETS_FROZEN_TRAINING_AUTHORIZED":
        raise RuntimeError("target-frozen training authorization is absent")
    free = int(subprocess.run(["nvidia-smi", f"--id={GPU}", "--query-gpu=memory.free", "--format=csv,noheader,nounits"], check=True, text=True, capture_output=True).stdout.strip())
    if free < 22000:
        raise RuntimeError(f"GPU{GPU} free-memory gate failed: {free} MiB")
    if not MATERIALIZED_TRAINING_CONFIG.is_file() or sha256(MATERIALIZED_TRAINING_CONFIG) != sha256(TRAINING_CONFIG):
        raise RuntimeError("approved materialized training config is absent or drifted; rerun preflight")
    result = _launch_training_30k("train_E3_GS_image_R1", RUN_ROOT, MATERIALIZED_TRAINING_CONFIG)
    missing = [step for step in CHECKPOINTS if not base.checkpoint_valid(RUN_ROOT, step)]
    final_path = RUN_ROOT / "ckpt/final.pt"
    if missing or not final_path.is_file():
        raise RuntimeError(f"training completion inventory failed: checkpoints={missing} final={final_path.is_file()}")
    inspection_path = TASK_ROOT / "control/final_checkpoint_inspection.json"
    inspect_code = r'''
import hashlib,json,sys,torch
from pathlib import Path
p=Path(sys.argv[1]);q=torch.load(p,map_location='cpu',weights_only=False)
body={'iteration':int(q['it']),'primitive_count':int(q['n_prim']),'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
Path(sys.argv[2]).write_text(json.dumps(body,indent=2,sort_keys=True)+'\n');print(json.dumps(body))
'''
    inspect_argv = docker_project(image=PROJECT_IMAGE) + [
        "python", "-c", inspect_code,
        f"/artifacts/JointBuildGS/{final_path.relative_to(ARTIFACT_ROOT)}",
        f"/artifacts/JointBuildGS/{inspection_path.relative_to(ARTIFACT_ROOT)}",
    ]
    inspection_process = subprocess.run(inspect_argv, text=True, capture_output=True)
    if inspection_process.returncode:
        raise RuntimeError(f"final checkpoint inspection failed: {inspection_process.stdout}{inspection_process.stderr}")
    final = json.loads(inspection_path.read_text(encoding="utf-8"))
    completion = {
        "schema": "jointbuildgs.p2.e3_full_scene_fused_normal_confidence_v1.training_complete.v1",
        "status": "TRAINING_COMPLETE",
        "completed_updates": int(final["iteration"]),
        "primitive_count": int(final["primitive_count"]),
        "final_checkpoint": {"path": str(final_path), "bytes": int(final["bytes"]), "sha256": final["sha256"]},
        "full_state_checkpoints": {str(step): sha256(RUN_ROOT / "ckpt" / f"step_{step:06d}.pt") for step in CHECKPOINTS},
        "wall_seconds": result.get("wall_seconds"),
        "max_selected_gpu_used_mib": result.get("max_selected_gpu_used_mib"),
        "official_PASS_usable": None,
        "scientific_verdict": None,
    }
    if completion["completed_updates"] != 30000:
        raise RuntimeError("final checkpoint iteration drift")
    atomic_json(TASK_ROOT / "control/training_complete.json", completion)
    provenance_path = TASK_ROOT / "provenance.json"
    provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
    provenance["ended_utc"] = now()
    provenance["training_complete_sha256"] = sha256(TASK_ROOT / "control/training_complete.json")
    atomic_json(provenance_path, provenance)
    atomic_text(TASK_ROOT / "NOTES.md", f"# {TASK_ID}\n\nStatus: `TRAINING_COMPLETE`. Stage-3 Roofer processing remains pending.\n\nscientific_verdict: null\n")
    print(json.dumps(completion, indent=2, sort_keys=True))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("preflight", "extract-native", "prepare-targets", "binding-probe", "train", "all-training"))
    command = parser.parse_args().command
    if command == "preflight":
        preflight()
    elif command == "extract-native":
        extract_native()
    elif command == "prepare-targets":
        prepare_targets()
    elif command == "binding-probe":
        binding_probe()
    elif command == "train":
        train()
    else:
        preflight(); prepare_targets(); train()


if __name__ == "__main__":
    main()
