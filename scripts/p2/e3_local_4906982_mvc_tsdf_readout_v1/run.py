#!/usr/bin/env python3
"""Fixed voxel-versus-TSDF readout diagnostic for 4906982 MVC checkpoints.

The host process only orchestrates Docker.  Six immutable 20k checkpoints are
rendered once into a new artifact namespace.  Existing voxel outputs are read
without rerun; TSDF, classification, and Roofer use one fixed parameter set for
all arms and replicas.  LoD2 RoofSurface data enters evaluation only.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO = Path(__file__).resolve().parents[3]
ARTIFACT_ROOT = REPO.parent / "JointBuildGS-artifacts"
TASK_ID = "P2-E3-LOCAL-4906982-MVC-TSDF-READOUT-v1"
TASK_ROOT = ARTIFACT_ROOT / "phase-payloads/p2/e3_local_4906982_mvc_tsdf_readout_v1" / TASK_ID
CONFIG = REPO / "configs/p2/e3_local_4906982_mvc_tsdf_readout_v1/config.yaml"
EVAL_IMAGE = "jointbuildgs:mvc-eval-v1"
TOOLS_IMAGE = "jointbuildgs-p0-tools:t0"
ROOFER_IMAGE = "3dgi/roofer@sha256:dd2c415aaee337502bde0dc1426dfa9c9f88e648f9d2f6340110c49932c251d2"
BUILDER_IMAGE = "innopam-v1-nbm-frontend:latest"
GPU = "1"
PLUGIN_ROOT = Path("/home/innopam/.codex/plugins/cache/openai-curated-remote/data-analytics/0.2.8-13ceeea1f599")
EXPECTED_IMAGE_IDS = {
    EVAL_IMAGE: "sha256:5968cc43e93e915abc0d82ede44d718990d526eef054d6b47aa96120f00d39d1",
    TOOLS_IMAGE: "sha256:02b4b7bb2e35e9b88bcc8457678ed8f178cca8f76f22b1b62f02721359e46be8",
    ROOFER_IMAGE: "sha256:9c980b97fba4c3fd30f5bb4afb8f2621be211d4e72e4333ea2053e8cd69b2dba",
    BUILDER_IMAGE: "sha256:f7188e0372d8357d7e19d22ebdb6230305596da5e1205febde9e14a3d4d5d4a5",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def atomic_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, indent=2, sort_keys=True, ensure_ascii=False)
            stream.write("\n")
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def command(argv: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(argv, cwd=REPO, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if check and proc.returncode != 0:
        raise RuntimeError(f"command failed ({proc.returncode}): {' '.join(argv)}\n{proc.stderr or proc.stdout}")
    return proc


def git_record() -> dict[str, Any]:
    status = command(["git", "status", "--porcelain=v1"], check=False).stdout
    return {
        "commit": command(["git", "rev-parse", "HEAD"]).stdout.strip(),
        "branch": command(["git", "branch", "--show-current"]).stdout.strip(),
        "dirty": bool(status.strip()),
        "status_porcelain": status.splitlines(),
    }


def image_record(reference: str) -> dict[str, Any]:
    row = json.loads(command(["docker", "image", "inspect", reference]).stdout)[0]
    return {"reference": reference, "id": row["Id"], "repo_digests": row.get("RepoDigests") or []}


def gpu_record() -> dict[str, Any]:
    fields = command([
        "nvidia-smi", f"--id={GPU}",
        "--query-gpu=index,name,uuid,memory.total,driver_version",
        "--format=csv,noheader,nounits",
    ]).stdout.strip().split(", ")
    return {"host_index": int(fields[0]), "model": fields[1], "uuid": fields[2], "memory_total_mib": int(fields[3]), "driver": fields[4]}


def eval_argv(action: str, *, output: str = "/task", case: str | None = None, max_views: int | None = None, gpu: bool = False) -> list[str]:
    argv = ["docker", "run", "--rm", "--network", "none"]
    if gpu:
        argv += ["--gpus", f"device={GPU}", "--ipc=host"]
    argv += [
        "--user", f"{os.getuid()}:{os.getgid()}",
        "-e", "MPLCONFIGDIR=/tmp/matplotlib", "-e", "PYTHONDONTWRITEBYTECODE=1",
        "-e", "TORCH_EXTENSIONS_DIR=/task/cache/torch_extensions",
        "-v", f"{REPO}:/workspace/JointBuildGS:ro",
        "-v", f"{ARTIFACT_ROOT}:/artifacts/JointBuildGS:ro",
        "-v", f"{TASK_ROOT}:/task:rw",
        "-w", "/workspace/JointBuildGS", EVAL_IMAGE,
        "python", "/workspace/JointBuildGS/scripts/p2/e3_local_4906982_mvc_tsdf_readout_v1/run.py",
        "--inside-docker", action,
        "--config", "/workspace/JointBuildGS/configs/p2/e3_local_4906982_mvc_tsdf_readout_v1/config.yaml",
        "--output", output,
    ]
    if case:
        argv += ["--case", case]
    if max_views is not None:
        argv += ["--max-views", str(max_views)]
    return argv


def record_operation(label: str, argv: list[str], started: str, ended: str, return_code: int) -> None:
    path = TASK_ROOT / "control/operations.json"
    payload = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {
        "schema": "jointbuildgs.p2.e3_local_4906982_mvc_tsdf_readout_v1.operations.v1",
        "task_id": TASK_ID,
        "operations": [],
        "scientific_verdict": None,
    }
    payload["operations"].append({"label": label, "argv": argv, "started_utc": started, "ended_utc": ended, "return_code": return_code})
    atomic_json(path, payload)


def run_logged(label: str, argv: list[str], log_path: Path) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    started = utc_now()
    with log_path.open("w", encoding="utf-8") as log:
        proc = subprocess.run(argv, cwd=REPO, text=True, stdout=log, stderr=subprocess.STDOUT)
    ended = utc_now()
    record_operation(label, argv, started, ended, proc.returncode)
    if proc.returncode != 0:
        raise RuntimeError(f"{label} failed ({proc.returncode}); inspect {log_path}")


def case_root(arm: str, replica: str) -> Path:
    return TASK_ROOT / "cases" / arm / replica


def run_preflight() -> None:
    argv = eval_argv("preflight")
    run_logged("preflight", argv, TASK_ROOT / "logs/preflight.log")


def run_smoke() -> None:
    receipt = TASK_ROOT / "smoke/tsdf_receipt.json"
    if receipt.is_file() and json.loads(receipt.read_text(encoding="utf-8")).get("passed") is True:
        return
    argv = eval_argv("render-tsdf", output="/task/smoke", case="MVC05:R1", max_views=16, gpu=True)
    run_logged("smoke_MVC05_R1_16views", argv, TASK_ROOT / "logs/smoke.log")


def run_render_cases() -> None:
    for arm in ("MVC0", "MVC05"):
        for replica in ("R1", "R2", "R3"):
            receipt = case_root(arm, replica) / "tsdf/tsdf_receipt.json"
            if receipt.is_file() and json.loads(receipt.read_text(encoding="utf-8")).get("passed") is True:
                continue
            label = f"{arm}_{replica}"
            argv = eval_argv("render-tsdf", output=f"/task/cases/{arm}/{replica}", case=f"{arm}:{replica}", gpu=True)
            run_logged(f"render_tsdf_{label}", argv, TASK_ROOT / f"logs/render_tsdf_{label}.log")


def run_bounded_cases() -> None:
    for arm in ("MVC0", "MVC05"):
        for replica in ("R1", "R2", "R3"):
            receipt = case_root(arm, replica) / "tsdf_bounded/tsdf_receipt.json"
            if receipt.is_file() and json.loads(receipt.read_text(encoding="utf-8")).get("passed") is True:
                continue
            label = f"{arm}_{replica}"
            argv = eval_argv("reconstruct-bounded", output="/task", case=f"{arm}:{replica}")
            run_logged(f"reconstruct_bounded_tsdf_{label}", argv, TASK_ROOT / f"logs/reconstruct_bounded_tsdf_{label}.log")


def tools_python_argv(action: str, *extra: str) -> list[str]:
    return [
        "docker", "run", "--rm", "--network", "none", "--entrypoint", "python",
        "--user", f"{os.getuid()}:{os.getgid()}", "--cpus", "12", "--memory", "64g", "--pids-limit", "4096",
        "-e", "PYTHONDONTWRITEBYTECODE=1", "-e", "PYTHONPATH=/workspace/JointBuildGS",
        "-v", f"{REPO}:/workspace/JointBuildGS:ro", "-v", f"{TASK_ROOT}:/task:rw",
        "-w", "/workspace/JointBuildGS", TOOLS_IMAGE,
        "/workspace/JointBuildGS/scripts/p2/e3_local_4906982_mvc_tsdf_readout_v1/run.py",
        "--inside-docker", action, "--config", "/workspace/JointBuildGS/configs/p2/e3_local_4906982_mvc_tsdf_readout_v1/config.yaml",
        "--output", "/task", *extra,
    ]


def run_stage3() -> None:
    for method, label in (("tsdf", "TSDF_RAW"), ("tsdf_bounded", "TSDF_BOUNDED")):
      for arm in ("MVC0", "MVC05"):
        for replica in ("R1", "R2", "R3"):
            root = case_root(arm, replica)
            classified = root / method / "classified_surface.laz"
            class_receipt = root / method / "classification_receipt.json"
            if not (class_receipt.is_file() and json.loads(class_receipt.read_text(encoding="utf-8")).get("passed") is True):
                partial = root / method / "classified_surface.partial.laz"
                pipeline = root / method / "classification_pipeline.json"
                argv = [
                    "docker", "run", "--rm", "--network", "none", "--entrypoint", "pdal",
                    "--user", f"{os.getuid()}:{os.getgid()}", "--cpus", "12", "--memory", "64g", "--pids-limit", "4096",
                    "-v", f"{TASK_ROOT}:/task:rw", "-w", "/task", TOOLS_IMAGE,
                    "pipeline", "/task/" + str(pipeline.relative_to(TASK_ROOT)),
                ]
                run_logged(f"classify_{label}_{arm}_{replica}", argv, root / "logs" / f"classification_{method}.log")
                verify = tools_python_argv("verify-classification", "--case", f"{arm}:{replica}", "--method", method)
                run_logged(f"verify_classification_{label}_{arm}_{replica}", verify, root / "logs" / f"classification_verify_{method}.log")
                if not classified.is_file() or partial.is_file():
                    raise RuntimeError(f"classification sealing failed: {arm}/{replica}")

            terminal = root / method / "roofer/roofer_terminal.json"
            if terminal.is_file() and json.loads(terminal.read_text(encoding="utf-8")).get("rf_success") is True:
                continue
            roofer_output = root / method / "roofer/output"
            if roofer_output.exists():
                if not any(roofer_output.glob("*.city.jsonl")):
                    raise RuntimeError(f"unsealed Roofer output requires review: {roofer_output}")
            else:
                roofer_output.mkdir(parents=True)
                stage3 = json.loads((TASK_ROOT / "control/stage3_contract.json").read_text(encoding="utf-8"))
                box = [str(value) for value in stage3["roofer_box"]]
                argv = [
                    "docker", "run", "--rm", "--network", "none", "--cpus", "12", "--memory", "64g", "--pids-limit", "4096",
                    "--user", f"{os.getuid()}:{os.getgid()}", "-v", f"{TASK_ROOT}:/task:rw", "-w", "/task", ROOFER_IMAGE,
                    "--id-attribute", "stable_id", "--jobs", "1", "--box", *box,
                    str(classified.relative_to(TASK_ROOT)), "control/shared_standard_footprint_4906982.geojson", str(roofer_output.relative_to(TASK_ROOT)),
                ]
                run_logged(f"roofer_{label}_{arm}_{replica}", argv, root / "logs" / f"roofer_{method}.log")
            record = tools_python_argv("record-roofer", "--case", f"{arm}:{replica}", "--method", method)
            run_logged(f"record_roofer_{label}_{arm}_{replica}", record, root / "logs" / f"roofer_record_{method}.log")


def run_evaluation() -> None:
    argv = eval_argv("evaluate")
    run_logged("evaluate", argv, TASK_ROOT / "logs/evaluate.log")


def run_report() -> None:
    argv = [
        "docker", "run", "--rm", "--network", "none", "--user", f"{os.getuid()}:{os.getgid()}",
        "-v", f"{PLUGIN_ROOT}:/plugin:ro", "-v", f"{TASK_ROOT}:/task:rw", "-w", "/plugin", BUILDER_IMAGE,
        "node", "/plugin/skills/build-report/scripts/deliver_portable_artifact.mjs",
        "--input", "/task/report_artifact.json", "--output", "/task/report.html",
        "--screenshot", "/task/logs/report_delivery_failure.png",
    ]
    run_logged("deliver_portable_report", argv, TASK_ROOT / "logs/report_delivery.log")


def finalize_host_provenance() -> None:
    provenance = json.loads((TASK_ROOT / "provenance.json").read_text(encoding="utf-8"))
    provenance["host_context"] = json.loads((TASK_ROOT / "control/host_context.json").read_text(encoding="utf-8"))
    provenance["operations"] = json.loads((TASK_ROOT / "control/operations.json").read_text(encoding="utf-8"))["operations"]
    provenance["ended_utc"] = utc_now()
    provenance["git_at_completion"] = git_record()
    provenance["report_html_sha256"] = sha256(TASK_ROOT / "report.html")
    atomic_json(TASK_ROOT / "provenance.json", provenance)
    contract = json.loads((TASK_ROOT / "experiment_contract.json").read_text(encoding="utf-8"))
    contract["status"] = "COMPLETE_TECHNICAL_DIAGNOSTIC"
    contract["scientific_verdict"] = None
    atomic_json(TASK_ROOT / "experiment_contract.json", contract)


def host_main(phase: str) -> None:
    TASK_ROOT.mkdir(parents=True, exist_ok=True)
    (TASK_ROOT / "logs").mkdir(exist_ok=True)
    (TASK_ROOT / "cache/torch_extensions").mkdir(parents=True, exist_ok=True)
    images = [image_record(x) for x in (EVAL_IMAGE, TOOLS_IMAGE, ROOFER_IMAGE, BUILDER_IMAGE)]
    for row in images:
        if row["id"] != EXPECTED_IMAGE_IDS[row["reference"]]:
            raise RuntimeError(f"Docker image identity drift: {row['reference']}")
    context = {
        "schema": "jointbuildgs.p2.e3_local_4906982_mvc_tsdf_readout_v1.host_context.v1",
        "task_id": TASK_ID,
        "started_utc": utc_now(),
        "git": git_record(),
        "gpu": gpu_record(),
        "docker_images": images,
        "config_sha256": sha256(CONFIG),
        "runner_sha256": sha256(Path(__file__)),
        "scientific_verdict": None,
    }
    atomic_json(TASK_ROOT / "control/host_context.json", context)
    phases = {
        "preflight": [run_preflight],
        "smoke": [run_preflight, run_smoke],
        "cases": [run_preflight, run_smoke, run_render_cases, run_bounded_cases, run_stage3],
        "evaluate": [run_preflight, run_smoke, run_render_cases, run_bounded_cases, run_stage3, run_evaluation],
        "report": [run_preflight, run_smoke, run_render_cases, run_bounded_cases, run_stage3, run_evaluation, run_report, finalize_host_provenance],
        "all": [run_preflight, run_smoke, run_render_cases, run_bounded_cases, run_stage3, run_evaluation, run_report, finalize_host_provenance],
    }
    for step in phases[phase]:
        step()
    if phase in {"all", "report"}:
        metrics = json.loads((TASK_ROOT / "metrics.json").read_text(encoding="utf-8"))
        print(json.dumps({
            "status": metrics["status"],
            "raw_tsdf_mvc05_full_coverage_count": metrics["raw_tsdf_mvc05_full_coverage_count"],
            "bounded_tsdf_mvc05_full_coverage_count": metrics["bounded_tsdf_mvc05_full_coverage_count"],
            "mvc05_roofer_coverage": metrics["mvc05_roofer_coverage"],
            "report": str(TASK_ROOT / "report.html"),
            "scientific_verdict": None,
        }, indent=2, ensure_ascii=False))


# ---- Docker-side implementation -----------------------------------------


def load_yaml(path: Path) -> dict[str, Any]:
    import yaml

    return yaml.safe_load(path.read_text(encoding="utf-8"))


def file_record(path: Path) -> dict[str, Any]:
    return {"path": str(path), "bytes": path.stat().st_size, "sha256": sha256(path)}


def docker_preflight(config_path: Path, output: Path) -> None:
    from shapely.geometry import shape

    cfg = load_yaml(config_path)
    if cfg["status"] != "APPROVED_FOR_LOCAL_TECHNICAL_DIAGNOSTIC" or cfg.get("scientific_verdict", "missing") is not None:
        raise RuntimeError("diagnostic config is not activated or verdict is non-null")
    counters = cfg["execution_counters"]
    if int(counters["expected_training_runs"]) != 0 or int(counters["expected_voxel_fusion_reruns"]) != 0:
        raise RuntimeError("prohibited execution counter is nonzero")
    if float(cfg["tsdf"]["truncation_m"]) < 2 * float(cfg["tsdf"]["voxel_m"]):
        raise RuntimeError("TSDF truncation must cover at least two voxels")
    source_root = Path(cfg["source_task_root"])
    runtime_path = Path(cfg["source_runtime_config"])
    footprint_path = Path(cfg["shared_footprint"])
    reference_path = Path(cfg["reference_lod2_gml"])
    ground_path = Path(cfg["bounded_tsdf"]["fixed_ground_source"])
    if sha256(ground_path) != cfg["bounded_tsdf"]["fixed_ground_source_sha256"]:
        raise RuntimeError("fixed image-derived ground source hash drifted")
    ground_payload = json.loads(ground_path.read_text(encoding="utf-8"))
    ground_value = float(ground_payload["target_attributes"][cfg["bounded_tsdf"]["fixed_ground_attribute"]])
    if ground_value != float(cfg["bounded_tsdf"]["fixed_ground_z_m"]):
        raise RuntimeError("fixed image-derived ground value drifted")
    runtime = load_yaml(runtime_path)
    views = list(runtime["visible_views"])
    if len(views) != int(cfg["render"]["expected_view_count"]):
        raise RuntimeError("visible view count drifted")
    required = [runtime_path, Path(cfg["source_input_hashes"]), footprint_path, reference_path, ground_path]
    checkpoint_records = []
    for arm in cfg["arms"]:
        for replica in cfg["replicas"]:
            checkpoint = source_root / "arms" / arm / replica / "ckpt/step_020000.pt"
            expected = cfg["checkpoint_sha256"][arm][replica]
            actual = sha256(checkpoint)
            if actual != expected:
                raise RuntimeError(f"checkpoint hash drift: {arm}/{replica}")
            required.append(checkpoint)
            checkpoint_records.append({"arm": arm, "replica": replica, "path": str(checkpoint), "sha256": actual, "bytes": checkpoint.stat().st_size})
    source_files = [
        Path("/workspace/JointBuildGS/src/stage2/renderer.py"),
        Path("/workspace/JointBuildGS/src/stage2/dataloader.py"),
        Path("/workspace/JointBuildGS/src/stage2/model.py"),
        Path("/workspace/JointBuildGS/src/stage3/common_classification_adapter_v1.py"),
        Path("/workspace/JointBuildGS/scripts/p2/c3_full_scene_tsdf_semantic_texture_v1/run.py"),
        Path("/workspace/JointBuildGS/scripts/p2/e3_local_4906982_mvc_v2/run.py"),
        Path("/workspace/JointBuildGS/scripts/p2/e3_local_4906982_mvc_readout_diag_v1/run.py"),
    ]
    implementation_files = [*source_files, Path(__file__), config_path]
    required.extend(source_files)
    for path in [*required, Path(__file__), config_path]:
        if not path.is_file():
            raise FileNotFoundError(path)
    output.mkdir(parents=True, exist_ok=True)
    (output / "control").mkdir(exist_ok=True)
    footprint_payload = json.loads(footprint_path.read_text(encoding="utf-8"))
    footprint = shape(footprint_payload["features"][0]["geometry"])
    copied_footprint = output / "control/shared_standard_footprint_4906982.geojson"
    footprint_bytes = footprint_path.read_bytes()
    if copied_footprint.is_file() and copied_footprint.read_bytes() != footprint_bytes:
        raise RuntimeError("copied footprint drifted")
    copied_footprint.write_bytes(footprint_bytes)
    buffer_m = float(cfg["classification"]["context_buffer_m"])
    bounds = list(map(float, footprint.bounds))
    stage3 = {
        "schema": "jointbuildgs.p2.e3_local_4906982_mvc_tsdf_readout_v1.stage3.v1",
        "footprint_bounds": bounds,
        "roofer_box": [bounds[0] - buffer_m, bounds[1] - buffer_m, bounds[2] + buffer_m, bounds[3] + buffer_m],
        "classification": cfg["classification"],
        "roofer": cfg["roofer"],
        "reference_used": False,
        "scientific_verdict": None,
    }
    atomic_json(output / "control/stage3_contract.json", stage3)
    input_map = {str(path): file_record(path) for path in sorted(set(required), key=str)}
    hashes = {"schema": "jointbuildgs.p2.e3_local_4906982_mvc_tsdf_readout_v1.input_hashes.v1", "inputs": input_map, "scientific_verdict": None}
    hash_path = output / "input_hashes.json"
    if hash_path.is_file() and json.loads(hash_path.read_text(encoding="utf-8")).get("inputs") != input_map:
        archived = output / "logs/input_hashes_before_bounded_extension.json"
        if not archived.is_file():
            archived.parent.mkdir(parents=True, exist_ok=True)
            archived.write_bytes(hash_path.read_bytes())
        elif archived.read_bytes() != hash_path.read_bytes():
            raise RuntimeError("input hash manifest drifted after bounded-extension archive; refusing overwrite")
    atomic_json(hash_path, hashes)
    contract = {
        "schema": "jointbuildgs.p2.e3_local_4906982_mvc_tsdf_readout_v1.contract.v1",
        "task_id": cfg["task_id"], "status": "PREFLIGHT_PASSED",
        "mode": "fixed_readout_ablation_existing_20k_checkpoints", "case_count": 6,
        "training_runs": 0, "voxel_fusion_reruns": 0, "tsdf_reconstructions": 12,
        "same_parameters_all_cases": True, "reference_evaluation_only": True,
        "official_PASS_usable": None, "scientific_verdict": None,
    }
    atomic_json(output / "experiment_contract.json", contract)
    config_diff = """# Fixed readout method difference\n\nALLOWLIST: method implementation and method-owned surface extraction only.\n\nVOXEL: reuse immutable MVC-v2 per-view 0.15 m voxel aggregation, alpha>=0.5, >=2 distinct views.\nTSDF_RAW: rerender the same checkpoint/views/depth_mode, Open3D ScalableTSDF voxel=0.15 m, truncation=0.45 m, alpha>=0.5, then retain TSDF surface points observed by >=2 distinct views; no Z bound.\nTSDF_BOUNDED: reuse the exact saved TSDF_RAW render buffers and the same TSDF/support parameters, but apply the existing C3 image-derived AOI Z contract [fixed 7k ground-2 m, fixed 7k ground+45 m] before integration.\n\nIDENTICAL: checkpoint, 55 views, camera intrinsics/extrinsics, depth range, XY buffer, classification, shared footprint, Roofer defaults, evaluation reference and datum shift.\nPROHIBITED: per-arm/per-replica tuning and LoD2 use before evaluation.\n"""
    (output / "config_diff.txt").write_text(config_diff, encoding="utf-8")
    provenance = {
        "schema": "jointbuildgs.p2.e3_local_4906982_mvc_tsdf_readout_v1.provenance.v1",
        "task_id": cfg["task_id"], "started_utc": utc_now(), "ended_utc": None,
        "config_path": str(config_path), "config_sha256": sha256(config_path),
        "runner_path": str(Path(__file__)), "runner_sha256": sha256(Path(__file__)),
        "source_files": {str(path): sha256(path) for path in implementation_files},
        "checkpoint_inputs": checkpoint_records, "view_count": len(views),
        "source_random_seed": runtime.get("seed"), "scientific_verdict": None,
    }
    atomic_json(output / "provenance.json", provenance)
    print(json.dumps({"status": "PREFLIGHT_PASSED", "views": len(views), "checkpoints": len(checkpoint_records), "footprint_sha256": sha256(copied_footprint)}, indent=2))


def model_from_checkpoint(path: Path, device: str) -> Any:
    import torch
    from torch import nn
    from src.stage2.model import GaussianModel2D

    payload = torch.load(path, map_location="cpu", weights_only=False)
    state = payload["model"]["state_dict"] if "model" in payload else payload["state_dict"]
    required = {"means", "quats", "log_scales", "opacities_raw", "sh0", "shN", "sem_logits"}
    if not required.issubset(state):
        raise RuntimeError("checkpoint state is incomplete")
    model = GaussianModel2D.__new__(GaussianModel2D)
    nn.Module.__init__(model)
    model.sh_degree = model.max_sh_degree = model.active_sh_degree = 3
    model.num_classes = 4
    for name in sorted(required):
        setattr(model, name, nn.Parameter(state[name].to(device=device), requires_grad=False))
    model.surface_seed_mask = torch.zeros(len(state["means"]), dtype=torch.bool, device=device)
    model.eval()
    return model, payload, state


def write_laz(path: Path, xyz: Any, rgb: Any, normals: Any, support: Any) -> None:
    import laspy
    import numpy as np
    from pyproj import CRS

    header = laspy.LasHeader(point_format=3, version="1.4")
    header.add_crs(CRS.from_epsg(25832))
    header.scales = np.asarray([0.001, 0.001, 0.001])
    header.offsets = np.asarray([690000.0, 5335000.0, 0.0])
    for name, dtype in (("view_support", np.uint16), ("normal_x", np.float32), ("normal_y", np.float32), ("normal_z", np.float32)):
        header.add_extra_dim(laspy.ExtraBytesParams(name=name, type=dtype))
    cloud = laspy.LasData(header)
    cloud.x, cloud.y, cloud.z = xyz[:, 0], xyz[:, 1], xyz[:, 2]
    cloud.red = np.rint(np.clip(rgb[:, 0], 0, 1) * 65535).astype(np.uint16)
    cloud.green = np.rint(np.clip(rgb[:, 1], 0, 1) * 65535).astype(np.uint16)
    cloud.blue = np.rint(np.clip(rgb[:, 2], 0, 1) * 65535).astype(np.uint16)
    cloud.classification = np.ones(len(xyz), dtype=np.uint8)
    cloud.view_support = support.astype(np.uint16)
    cloud.normal_x, cloud.normal_y, cloud.normal_z = normals[:, 0], normals[:, 1], normals[:, 2]
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".partial.laz")
    cloud.write(temporary)
    os.replace(temporary, path)


def save_npz_atomic(path: Path, **arrays: Any) -> None:
    import numpy as np

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".partial.npz")
    with temporary.open("wb") as stream:
        np.savez_compressed(stream, **arrays)
    os.replace(temporary, path)


def support_counts(points_local: Any, records: list[dict[str, Any]], tolerance: float, alpha_min: float) -> Any:
    import numpy as np

    support = np.zeros(len(points_local), dtype=np.uint16)
    for record in records:
        extrinsic = record["extrinsic_tsdf"]
        camera = points_local @ extrinsic[:3, :3].T + extrinsic[:3, 3]
        front = camera[:, 2] > 0.01
        uvw = camera @ record["K"].T
        uv = np.zeros((len(points_local), 2), dtype=np.float64)
        uv[front] = uvw[front, :2] / uvw[front, 2:3]
        depth, alpha = record["depth_tsdf"], record["alpha"]
        height, width = depth.shape
        inside = front & (uv[:, 0] >= 0) & (uv[:, 0] < width) & (uv[:, 1] >= 0) & (uv[:, 1] < height)
        indices = np.flatnonzero(inside)
        if not len(indices):
            continue
        px = np.clip(np.rint(uv[indices, 0]).astype(int), 0, width - 1)
        py = np.clip(np.rint(uv[indices, 1]).astype(int), 0, height - 1)
        observed = depth[py, px]
        visible = (observed > 0) & (alpha[py, px] >= alpha_min) & (np.abs(camera[indices, 2] - observed) <= tolerance)
        support[indices[visible]] += 1
    return support


def docker_render_tsdf(config_path: Path, output: Path, case: str, max_views: int | None) -> None:
    import laspy
    import numpy as np
    import open3d as o3d
    import torch
    from shapely import contains_xy
    from shapely.geometry import shape
    from src.stage2.dataloader import ColmapDataset
    from src.stage2.renderer import render
    from src.stage3.common_classification_adapter_v1 import pipeline

    cfg = load_yaml(config_path)
    arm, replica = case.split(":", 1)
    source_root = Path(cfg["source_task_root"])
    checkpoint = source_root / "arms" / arm / replica / "ckpt/step_020000.pt"
    if sha256(checkpoint) != cfg["checkpoint_sha256"][arm][replica]:
        raise RuntimeError("checkpoint hash mismatch")
    receipt_path = output / "tsdf/tsdf_receipt.json"
    if receipt_path.is_file():
        prior = json.loads(receipt_path.read_text(encoding="utf-8"))
        fused = output / "tsdf/fused_surface.laz"
        if prior.get("passed") is True and fused.is_file() and sha256(fused) == prior.get("fused_surface_sha256"):
            print(json.dumps({"case": case, "fast_path": True, "point_count": prior["support_filtered_point_count"]}))
            return
    runtime = load_yaml(Path(cfg["source_runtime_config"]))
    names = list(runtime["visible_views"])
    if max_views is not None:
        names = names[:max_views]
    dataset = ColmapDataset(Path(runtime["data_root"]), downscale=float(cfg["render"]["downscale"]), load_depth=False, load_normal=False, load_semantic=False, visible_views=names)
    if [frame.name for frame in dataset.frames] != names:
        raise RuntimeError("dataset view order drifted")
    footprint_payload = json.loads(Path(cfg["shared_footprint"]).read_text(encoding="utf-8"))
    footprint = shape(footprint_payload["features"][0]["geometry"])
    fusion_filter = footprint.buffer(float(cfg["render"]["footprint_buffer_m"]))
    shift = np.asarray(cfg["render"]["world_shift_xyz"], dtype=np.float64)
    origin_world = np.asarray([footprint.centroid.x, footprint.centroid.y, shift[2]], dtype=np.float64)
    origin_model_local = origin_world - shift
    tsdf_cfg = cfg["tsdf"]
    volume = o3d.pipelines.integration.ScalableTSDFVolume(
        voxel_length=float(tsdf_cfg["voxel_m"]), sdf_trunc=float(tsdf_cfg["truncation_m"]),
        color_type=o3d.pipelines.integration.TSDFVolumeColorType.RGB8,
    )
    device = "cuda"
    model, payload, state = model_from_checkpoint(checkpoint, device)
    records: list[dict[str, Any]] = []
    view_receipts = []
    valid_total = retained_total = high_z_total = 0
    started = time.monotonic()
    torch.cuda.reset_peak_memory_stats()
    with torch.no_grad():
        for index, batch in enumerate(dataset):
            width, height = int(batch["width"]), int(batch["height"])
            w2c = batch["w2c"].to(device)
            K = batch["K"].to(device)
            rendered = render(
                model, w2c, K, width, height, sh_degree=3, render_mode="RGB+ED",
                near_plane=float(cfg["render"]["depth_min_m"]), far_plane=float(cfg["render"]["depth_max_m"]),
                bg_color=torch.ones(3, device=device), depth_mode=str(cfg["render"]["depth_mode"]),
            )
            depth = rendered["depth_median"]
            alpha = rendered["alpha"]
            normal = rendered["normal_render"]
            rgb = rendered["rgb"].clamp(0, 1)
            valid = torch.isfinite(depth) & (depth >= float(cfg["render"]["depth_min_m"])) & (depth <= float(cfg["render"]["depth_max_m"])) & (alpha >= float(cfg["render"]["alpha_min"]))
            depth_tsdf = np.zeros((height, width), dtype=np.float32)
            retained = high_z = 0
            if torch.any(valid):
                yy, xx = torch.nonzero(valid, as_tuple=True)
                zz = depth[yy, xx]
                camera = torch.stack(((xx - K[0, 2]) / K[0, 0] * zz, (yy - K[1, 2]) / K[1, 1] * zz, zz), dim=1)
                c2w = torch.linalg.inv(w2c)
                local = camera @ c2w[:3, :3].T + c2w[:3, 3]
                world = local.cpu().numpy().astype(np.float64) + shift
                keep = contains_xy(fusion_filter, world[:, 0], world[:, 1])
                retained = int(np.count_nonzero(keep))
                high_z = int(np.count_nonzero(keep & (world[:, 2] > 650.0)))
                flat = (yy * width + xx).cpu().numpy()[keep]
                depth_tsdf.reshape(-1)[flat] = depth.cpu().numpy().reshape(-1)[flat]
            color_u8 = np.rint(rgb.cpu().numpy() * 255).astype(np.uint8)
            K_np = K.cpu().numpy().astype(np.float64)
            w2c_np = w2c.cpu().numpy().astype(np.float64)
            extrinsic = w2c_np.copy()
            extrinsic[:3, 3] += extrinsic[:3, :3] @ origin_model_local
            if np.count_nonzero(depth_tsdf):
                rgbd = o3d.geometry.RGBDImage.create_from_color_and_depth(
                    o3d.geometry.Image(np.ascontiguousarray(color_u8)), o3d.geometry.Image(np.ascontiguousarray(depth_tsdf)),
                    depth_scale=1.0, depth_trunc=float(cfg["render"]["depth_max_m"]), convert_rgb_to_intensity=False,
                )
                intrinsic = o3d.camera.PinholeCameraIntrinsic(width, height, float(K_np[0, 0]), float(K_np[1, 1]), float(K_np[0, 2]), float(K_np[1, 2]))
                volume.integrate(rgbd, intrinsic, extrinsic)
            view_path = output / "renders" / f"{index:03d}_{Path(str(batch['name'])).stem}.npz"
            save_npz_atomic(
                view_path,
                image_name=np.asarray(str(batch["name"])),
                depth_raw=depth.cpu().numpy().astype(np.float32), depth_tsdf=depth_tsdf,
                normal_world=normal.cpu().numpy().astype(np.float32), alpha=alpha.cpu().numpy().astype(np.float32),
                rgb=color_u8, K=K_np, w2c=w2c_np, extrinsic_tsdf=extrinsic,
            )
            records.append({"image_name": str(batch["name"]), "depth_tsdf": depth_tsdf, "alpha": alpha.cpu().numpy().astype(np.float32), "K": K_np, "extrinsic_tsdf": extrinsic})
            valid_n = int(valid.sum().item())
            valid_total += valid_n
            retained_total += retained
            high_z_total += high_z
            view_receipts.append({"index": index, "name": str(batch["name"]), "valid_pixels": valid_n, "retained_xy_pixels": retained, "retained_z_gt_650_pixels": high_z, "render_npz": str(view_path.relative_to(output)), "render_npz_sha256": sha256(view_path)})
            print(json.dumps({"case": case, "view": index + 1, "views": len(dataset), "retained": retained, "high_z": high_z}), flush=True)
    mesh = volume.extract_triangle_mesh()
    mesh.compute_vertex_normals()
    points = volume.extract_point_cloud()
    points_local = np.asarray(points.points, dtype=np.float64)
    if not len(points_local):
        raise RuntimeError("TSDF extracted zero points")
    normals = np.asarray(points.normals, dtype=np.float64)
    colors = np.asarray(points.colors, dtype=np.float64)
    if len(normals) != len(points_local):
        raise RuntimeError("TSDF point normals missing")
    support = support_counts(points_local, records, float(tsdf_cfg["support_visibility_tolerance_m"]), float(cfg["render"]["alpha_min"]))
    keep = support >= int(tsdf_cfg["minimum_distinct_view_support"])
    world = points_local + origin_world
    kept_world, kept_normal, kept_color, kept_support = world[keep], normals[keep], colors[keep], support[keep]
    if not len(kept_world):
        raise RuntimeError("TSDF >=2-view support filter retained zero points")
    norm = np.linalg.norm(kept_normal, axis=1)
    kept_normal /= np.maximum(norm[:, None], 1e-12)
    fused = output / "tsdf/fused_surface.laz"
    write_laz(fused, kept_world, kept_color, kept_normal, kept_support)
    mesh_world = o3d.geometry.TriangleMesh(mesh)
    mesh_world.translate(origin_world)
    mesh_path = output / "tsdf/tsdf_mesh_world.ply"
    mesh_path.parent.mkdir(parents=True, exist_ok=True)
    if not o3d.io.write_triangle_mesh(str(mesh_path), mesh_world, write_ascii=False):
        raise RuntimeError("failed to write TSDF mesh")
    raw_pcd = o3d.geometry.PointCloud(points)
    raw_pcd.translate(origin_world)
    raw_path = output / "tsdf/tsdf_surface_raw_world.ply"
    if not o3d.io.write_point_cloud(str(raw_path), raw_pcd, write_ascii=False):
        raise RuntimeError("failed to write raw TSDF point cloud")
    scene = {"crs": cfg["crs"], "roofer_aoi_bbox": list(map(float, footprint.bounds)), "classification_context_buffer_m": float(cfg["classification"]["context_buffer_m"])}
    classification = dict(cfg["classification"])
    classification.pop("context_buffer_m", None)
    partial = output / "tsdf/classified_surface.partial.laz"
    spec = pipeline(
        source_stages=[{"type": "readers.las", "filename": "/task/" + str(fused.relative_to(Path("/task"))) if str(fused).startswith("/task/") else str(fused)}],
        scene=scene, classification=classification,
        footprint_path=Path("/task/control/shared_standard_footprint_4906982.geojson"), output_path=Path("/task/") / partial.relative_to(Path("/task")) if str(partial).startswith("/task/") else partial,
    )
    atomic_json(output / "tsdf/classification_pipeline.json", spec)
    receipt = {
        "schema": "jointbuildgs.p2.e3_local_4906982_mvc_tsdf_readout_v1.tsdf.v1",
        "case": case, "arm": arm, "replica": replica, "completed_updates": 20000,
        "checkpoint_sha256": sha256(checkpoint), "view_count": len(dataset),
        "valid_render_pixels": valid_total, "xy_retained_render_pixels": retained_total,
        "xy_retained_render_z_gt_650_pixels": high_z_total,
        "raw_tsdf_point_count": int(len(world)), "raw_tsdf_z_gt_650_count": int(np.count_nonzero(world[:, 2] > 650.0)),
        "support_filtered_point_count": int(len(kept_world)), "support_filtered_z_gt_650_count": int(np.count_nonzero(kept_world[:, 2] > 650.0)),
        "support_ge3_fraction": float(np.mean(kept_support >= 3)), "support_histogram": {str(int(value)): int(np.count_nonzero(kept_support == value)) for value in np.unique(kept_support)},
        "mesh_vertex_count": int(len(mesh.vertices)), "mesh_triangle_count": int(len(mesh.triangles)),
        "peak_vram_mib": int(torch.cuda.max_memory_allocated() / 1048576), "wall_seconds": time.monotonic() - started,
        "fused_surface_sha256": sha256(fused), "mesh_sha256": sha256(mesh_path), "raw_surface_sha256": sha256(raw_path),
        "view_records": view_receipts, "reference_used": False,
        "passed": len(dataset) == (max_views if max_views is not None else int(cfg["render"]["expected_view_count"])) and len(kept_world) > 0,
        "scientific_verdict": None,
    }
    atomic_json(receipt_path, receipt)
    print(json.dumps({"case": case, "views": len(dataset), "raw_tsdf": len(world), "support_ge2": len(kept_world), "high_z": receipt["support_filtered_z_gt_650_count"], "wall_seconds": receipt["wall_seconds"], "passed": receipt["passed"]}, indent=2))


def docker_reconstruct_bounded(config_path: Path, output: Path, case: str) -> None:
    import numpy as np
    import open3d as o3d
    from shapely import contains_xy
    from shapely.geometry import shape
    from src.stage3.common_classification_adapter_v1 import pipeline

    cfg = load_yaml(config_path)
    arm, replica = case.split(":", 1)
    case_dir = output / "cases" / arm / replica
    target = case_dir / "tsdf_bounded"
    receipt_path = target / "tsdf_receipt.json"
    fused = target / "fused_surface.laz"
    if receipt_path.is_file():
        prior = json.loads(receipt_path.read_text(encoding="utf-8"))
        if prior.get("passed") is True and fused.is_file() and sha256(fused) == prior.get("fused_surface_sha256"):
            print(json.dumps({"case": case, "fast_path": True, "point_count": prior["support_filtered_point_count"]}))
            return

    bounded = cfg["bounded_tsdf"]
    ground_path = Path(bounded["fixed_ground_source"])
    if sha256(ground_path) != bounded["fixed_ground_source_sha256"]:
        raise RuntimeError("fixed image-derived ground source hash drifted")
    ground_payload = json.loads(ground_path.read_text(encoding="utf-8"))
    ground = float(ground_payload["target_attributes"][bounded["fixed_ground_attribute"]])
    if ground != float(bounded["fixed_ground_z_m"]):
        raise RuntimeError("fixed image-derived ground value drifted")
    z_min = ground - float(bounded["below_ground_m"])
    z_max = ground + float(bounded["above_ground_m"])

    footprint = shape(json.loads(Path(cfg["shared_footprint"]).read_text(encoding="utf-8"))["features"][0]["geometry"])
    fusion_filter = footprint.buffer(float(cfg["render"]["footprint_buffer_m"]))
    shift = np.asarray(cfg["render"]["world_shift_xyz"], dtype=np.float64)
    origin_world = np.asarray([footprint.centroid.x, footprint.centroid.y, shift[2]], dtype=np.float64)
    tsdf_cfg = cfg["tsdf"]
    volume = o3d.pipelines.integration.ScalableTSDFVolume(
        voxel_length=float(tsdf_cfg["voxel_m"]), sdf_trunc=float(tsdf_cfg["truncation_m"]),
        color_type=o3d.pipelines.integration.TSDFVolumeColorType.RGB8,
    )
    render_paths = sorted((case_dir / "renders").glob("*.npz"))
    if len(render_paths) != int(cfg["render"]["expected_view_count"]):
        raise RuntimeError(f"saved render buffer count drifted: {len(render_paths)}")
    records: list[dict[str, Any]] = []
    view_receipts = []
    valid_total = retained_xy_total = retained_z_total = rejected_z_total = 0
    started = time.monotonic()
    for index, render_path in enumerate(render_paths):
        with np.load(render_path) as data:
            depth_raw = np.asarray(data["depth_raw"], dtype=np.float32)
            alpha = np.asarray(data["alpha"], dtype=np.float32)
            rgb = np.asarray(data["rgb"], dtype=np.uint8)
            K = np.asarray(data["K"], dtype=np.float64)
            w2c = np.asarray(data["w2c"], dtype=np.float64)
            extrinsic = np.asarray(data["extrinsic_tsdf"], dtype=np.float64)
            image_name = str(data["image_name"])
        height, width = depth_raw.shape
        valid = np.isfinite(depth_raw) & (depth_raw >= float(cfg["render"]["depth_min_m"])) & (depth_raw <= float(cfg["render"]["depth_max_m"])) & (alpha >= float(cfg["render"]["alpha_min"]))
        yy, xx = np.nonzero(valid)
        depth_bounded = np.zeros_like(depth_raw)
        retained_xy = retained_z = rejected_z = 0
        if len(xx):
            zz = depth_raw[yy, xx].astype(np.float64)
            camera = np.column_stack(((xx - K[0, 2]) / K[0, 0] * zz, (yy - K[1, 2]) / K[1, 1] * zz, zz))
            c2w = np.linalg.inv(w2c)
            local = camera @ c2w[:3, :3].T + c2w[:3, 3]
            world = local + shift
            keep_xy = contains_xy(fusion_filter, world[:, 0], world[:, 1])
            keep_z = (world[:, 2] >= z_min) & (world[:, 2] <= z_max)
            keep = keep_xy & keep_z
            retained_xy = int(np.count_nonzero(keep_xy))
            retained_z = int(np.count_nonzero(keep))
            rejected_z = int(np.count_nonzero(keep_xy & ~keep_z))
            flat = yy[keep] * width + xx[keep]
            depth_bounded.reshape(-1)[flat] = depth_raw.reshape(-1)[flat]
        if np.count_nonzero(depth_bounded):
            rgbd = o3d.geometry.RGBDImage.create_from_color_and_depth(
                o3d.geometry.Image(np.ascontiguousarray(rgb)), o3d.geometry.Image(np.ascontiguousarray(depth_bounded)),
                depth_scale=1.0, depth_trunc=float(cfg["render"]["depth_max_m"]), convert_rgb_to_intensity=False,
            )
            intrinsic = o3d.camera.PinholeCameraIntrinsic(width, height, float(K[0, 0]), float(K[1, 1]), float(K[0, 2]), float(K[1, 2]))
            volume.integrate(rgbd, intrinsic, extrinsic)
        records.append({"image_name": image_name, "depth_tsdf": depth_bounded, "alpha": alpha, "K": K, "extrinsic_tsdf": extrinsic})
        valid_total += int(np.count_nonzero(valid))
        retained_xy_total += retained_xy
        retained_z_total += retained_z
        rejected_z_total += rejected_z
        view_receipts.append({"index": index, "name": image_name, "render_npz": str(render_path.relative_to(case_dir)), "render_npz_sha256": sha256(render_path), "valid_pixels": int(np.count_nonzero(valid)), "retained_xy_pixels": retained_xy, "retained_bounded_pixels": retained_z, "z_rejected_pixels": rejected_z})
        print(json.dumps({"case": case, "view": index + 1, "views": len(render_paths), "bounded": retained_z, "z_rejected": rejected_z}), flush=True)

    mesh = volume.extract_triangle_mesh()
    mesh.compute_vertex_normals()
    points = volume.extract_point_cloud()
    points_local = np.asarray(points.points, dtype=np.float64)
    if not len(points_local):
        raise RuntimeError("bounded TSDF extracted zero points")
    normals = np.asarray(points.normals, dtype=np.float64)
    colors = np.asarray(points.colors, dtype=np.float64)
    support = support_counts(points_local, records, float(tsdf_cfg["support_visibility_tolerance_m"]), float(cfg["render"]["alpha_min"]))
    keep = support >= int(tsdf_cfg["minimum_distinct_view_support"])
    world = points_local + origin_world
    kept_world, kept_normal, kept_color, kept_support = world[keep], normals[keep], colors[keep], support[keep]
    if not len(kept_world):
        raise RuntimeError("bounded TSDF >=2-view support filter retained zero points")
    kept_normal /= np.maximum(np.linalg.norm(kept_normal, axis=1)[:, None], 1e-12)
    write_laz(fused, kept_world, kept_color, kept_normal, kept_support)
    mesh_world = o3d.geometry.TriangleMesh(mesh)
    mesh_world.translate(origin_world)
    mesh_path = target / "tsdf_mesh_world.ply"
    mesh_path.parent.mkdir(parents=True, exist_ok=True)
    if not o3d.io.write_triangle_mesh(str(mesh_path), mesh_world, write_ascii=False):
        raise RuntimeError("failed to write bounded TSDF mesh")
    raw_pcd = o3d.geometry.PointCloud(points)
    raw_pcd.translate(origin_world)
    raw_path = target / "tsdf_surface_raw_world.ply"
    if not o3d.io.write_point_cloud(str(raw_path), raw_pcd, write_ascii=False):
        raise RuntimeError("failed to write bounded raw TSDF point cloud")
    scene = {"crs": cfg["crs"], "roofer_aoi_bbox": list(map(float, footprint.bounds)), "classification_context_buffer_m": float(cfg["classification"]["context_buffer_m"])}
    classification = dict(cfg["classification"])
    classification.pop("context_buffer_m", None)
    partial = target / "classified_surface.partial.laz"
    spec = pipeline(
        source_stages=[{"type": "readers.las", "filename": "/task/" + str(fused.relative_to(output))}],
        scene=scene, classification=classification,
        footprint_path=Path("/task/control/shared_standard_footprint_4906982.geojson"),
        output_path=Path("/task/") / partial.relative_to(output),
    )
    atomic_json(target / "classification_pipeline.json", spec)
    receipt = {
        "schema": "jointbuildgs.p2.e3_local_4906982_mvc_tsdf_readout_v1.tsdf_bounded.v1",
        "case": case, "arm": arm, "replica": replica, "completed_updates": 20000,
        "source_render_count": len(render_paths), "source_render_hashes": [sha256(path) for path in render_paths],
        "ground_source_sha256": sha256(ground_path), "ground_z_m": ground, "z_min_m": z_min, "z_max_m": z_max,
        "valid_render_pixels": valid_total, "xy_retained_render_pixels": retained_xy_total,
        "bounded_render_pixels": retained_z_total, "z_rejected_render_pixels": rejected_z_total,
        "raw_tsdf_point_count": int(len(world)), "raw_tsdf_z_gt_650_count": int(np.count_nonzero(world[:, 2] > 650.0)),
        "support_filtered_point_count": int(len(kept_world)), "support_filtered_z_gt_650_count": int(np.count_nonzero(kept_world[:, 2] > 650.0)),
        "support_ge3_fraction": float(np.mean(kept_support >= 3)), "support_histogram": {str(int(value)): int(np.count_nonzero(kept_support == value)) for value in np.unique(kept_support)},
        "mesh_vertex_count": int(len(mesh.vertices)), "mesh_triangle_count": int(len(mesh.triangles)),
        "wall_seconds": time.monotonic() - started,
        "fused_surface_sha256": sha256(fused), "mesh_sha256": sha256(mesh_path), "raw_surface_sha256": sha256(raw_path),
        "view_records": view_receipts, "reference_used": False, "passed": len(render_paths) == int(cfg["render"]["expected_view_count"]) and len(kept_world) > 0,
        "scientific_verdict": None,
    }
    atomic_json(receipt_path, receipt)
    print(json.dumps({"case": case, "views": len(render_paths), "raw_tsdf": len(world), "support_ge2": len(kept_world), "high_z": receipt["support_filtered_z_gt_650_count"], "wall_seconds": receipt["wall_seconds"], "passed": receipt["passed"]}, indent=2))


def docker_verify_classification(config_path: Path, output: Path, case: str, method: str) -> None:
    import laspy
    import numpy as np

    arm, replica = case.split(":", 1)
    root = output / "cases" / arm / replica / method
    partial, final = root / "classified_surface.partial.laz", root / "classified_surface.laz"
    cloud = laspy.read(partial)
    classes = np.asarray(cloud.classification)
    crs = cloud.header.parse_crs()
    counts = {str(int(value)): int(count) for value, count in zip(*np.unique(classes, return_counts=True))}
    passed = crs is not None and crs.to_epsg() == 25832 and counts.get("2", 0) > 0 and counts.get("6", 0) > 0
    receipt = {"schema": "jointbuildgs.p2.e3_local_4906982_mvc_tsdf_readout_v1.classification.v1", "case": case, "point_count": len(cloud.points), "class_counts": counts, "epsg": None if crs is None else crs.to_epsg(), "partial_sha256": sha256(partial), "passed": passed, "scientific_verdict": None}
    if passed:
        os.replace(partial, final)
        receipt["classified_surface_sha256"] = sha256(final)
    atomic_json(root / "classification_receipt.json", receipt)
    print(json.dumps(receipt, indent=2))
    if not passed:
        raise RuntimeError("classification verification failed")


def docker_record_roofer(config_path: Path, output: Path, case: str, method: str) -> None:
    arm, replica = case.split(":", 1)
    root = output / "cases" / arm / replica / method / "roofer"
    city_files = sorted((root / "output").glob("*.city.jsonl"))
    if not city_files:
        raise RuntimeError("Roofer CityJSONSeq missing")
    target = "DEBY_LOD2_4906982"
    attrs = None
    for line in city_files[0].read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        objects = row.get("CityObjects", {})
        if target in objects:
            attrs = objects[target].get("attributes", {})
            break
    if attrs is None:
        raise RuntimeError("target building absent from Roofer output")
    receipt = {
        "schema": "jointbuildgs.p2.e3_local_4906982_mvc_tsdf_readout_v1.roofer.v1",
        "case": case, "return_code": 0, "rf_success": attrs.get("rf_success"),
        "target_attributes": attrs, "quality_parameters": "ROOFER_DEFAULTS",
        "quality_driven_retry_allowed": False,
        "output_files": [file_record(path) for path in city_files], "scientific_verdict": None,
    }
    atomic_json(root / "roofer_terminal.json", receipt)
    print(json.dumps({"case": case, "rf_success": receipt["rf_success"], "rf_roof_planes": attrs.get("rf_roof_planes"), "rf_rmse_lod22": attrs.get("rf_rmse_lod22")}, indent=2))
    if receipt["rf_success"] is not True:
        raise RuntimeError("Roofer rf_success is not true")


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fields: list[str] = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def make_panel(path: Path, rows: list[dict[str, Any]], cfg: dict[str, Any], footprint: Any, refs: list[Any]) -> None:
    import laspy
    import matplotlib
    import numpy as np
    from shapely.ops import unary_union
    from scripts.p2.e3_local_4906982_mvc_readout_diag_v1.run import flatten_polygons, load_cityjsonseq

    matplotlib.use("Agg")
    from matplotlib import pyplot as plt

    fig, axes = plt.subplots(2, 6, figsize=(22, 8), dpi=145, constrained_layout=True)
    source_root = Path(cfg["source_task_root"])
    fp = np.asarray(footprint.exterior.coords)
    for column, (arm, replica) in enumerate((a, r) for a in cfg["arms"] for r in cfg["replicas"]):
        for row_index, method in enumerate(("VOXEL", "TSDF")):
            ax = axes[row_index, column]
            if method == "VOXEL":
                root = source_root / "arms" / arm / replica / "evaluation/step_020000/fusion"
            else:
                root = Path("/task") / "cases" / arm / replica / "tsdf"
            cloud = laspy.read(root / "classified_surface.laz")
            x, y = np.asarray(cloud.x), np.asarray(cloud.y)
            cls = np.asarray(cloud.classification)
            selected = cls == 6
            x, y = x[selected], y[selected]
            if len(x) > 12000:
                keep = np.linspace(0, len(x) - 1, 12000, dtype=int)
                x, y = x[keep], y[keep]
            ax.scatter(x, y, s=0.18, c="#a8a8a8", alpha=0.25, linewidths=0)
            city = next((root / "roofer/output").glob("*.city.jsonl"))
            preds, _ = load_cityjsonseq(city, cfg["building_id"], float(cfg["evaluation"]["prediction_z_shift_to_reference_m"]))
            for surface in preds:
                for poly in flatten_polygons(surface.polygon):
                    xy = np.asarray(poly.exterior.coords)
                    ax.fill(xy[:, 0], xy[:, 1], color="#c51b8a" if arm == "MVC05" else "#1688c7", alpha=0.38, linewidth=0.5, edgecolor="#222222")
            for surface in refs:
                for poly in flatten_polygons(surface.polygon):
                    xy = np.asarray(poly.exterior.coords)
                    ax.plot(xy[:, 0], xy[:, 1], color="#00a6a6", linewidth=1.0, linestyle="--")
            metric = next(item for item in rows if item["method"] == method and item["arm"] == arm and item["replica"] == replica)
            ax.plot(fp[:, 0], fp[:, 1], color="#111111", linewidth=1.1)
            ax.set_title(f"{method} {arm} {replica}\nroof {100*metric['roofer_roof_xy_coverage_fraction']:.2f}% · F0.5 {metric['roofer_surface_fscore_0p5m']:.3f}", fontsize=8)
            ax.set_aspect("equal")
            ax.set_axis_off()
    fig.suptitle("4906982 · fixed voxel versus TSDF readout · evaluation-only LoD2 dashed", fontsize=14, fontweight="bold")
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path)
    plt.close(fig)


def build_report(output: Path, rows: list[dict[str, Any]], metrics: dict[str, Any]) -> None:
    generated = utc_now()
    chart_rows = [{"case_method": f"{r['arm']} {r['replica']} {r['method']}", "arm": r["arm"], "replica": r["replica"], "method": r["method"], "roofer_coverage": r["roofer_roof_xy_coverage_fraction"], "fscore_0p5m": r["roofer_surface_fscore_0p5m"], "point_median_abs_dz_m": r["classified_abs_dz_m_median"], "point_median_normal_deg": r["classified_normal_angle_deg_median"], "classified_z_gt650": r["classified_z_gt_650_count"], "roofer_z_gt650": r["roofer_vertex_z_gt_650_count"]} for r in rows]
    query = {"engine": "SQLite over frozen diagnostic snapshot", "language": "sql"}
    source = {"id": "readout_source", "label": "Six-case voxel-versus-TSDF metrics", "path": "readout_metrics.csv", "query": {**query, "description": "Select the 12 method-case evaluation rows.", "filters": ["completed_updates = 20000", "method in (VOXEL, TSDF)"], "metric_definitions": ["Roofer coverage is semantic RoofSurface XY union area divided by shared footprint area.", "Point errors use evaluation-only LoD2 RoofSurface after the fixed datum shift."], "sql": "SELECT * FROM readout_metrics ORDER BY arm, replica, method", "tables_used": ["readout_metrics"]}}
    tsdf_full = metrics["tsdf_mvc05_full_coverage_count"]
    if tsdf_full == 3:
        next_text = "The fixed TSDF readout made all three MVC05 continuations complete; retain MVC and validate this readout on more buildings before adding depth supervision."
    else:
        next_text = "The fixed TSDF readout did not make all three MVC05 continuations complete. Preserve this result and preregister a confidence-gated MVS depth-only training arm; add normal supervision only if depth stabilizes height but not planes."
    summary = f"""## Technical summary\n\n- **MVC normal-surface alignment was better at 20k, but gross high-Z remained.** This readout test does not retrain or reinterpret that result.\n- **The fixed TSDF test asks whether downstream integration alone stabilizes Roofer.** TSDF produced full-roof coverage in **{tsdf_full}/3** MVC05 continuations at the diagnostic 95% marker, versus **{metrics['voxel_mvc05_full_coverage_count']}/3** for the existing voxel readout.\n- **High-Z and surface quality remain separate endpoints.** The table traces Z>650 m through classified points and final Roofer vertices while LoD2 depth/normal errors assess the normal roof surface.\n- **Next action:** {next_text}\n\nThese are one-building technical measurements. `scientific_verdict` remains `null`."""
    artifact = {
        "surface": "report",
        "manifest": {
            "version": 1, "title": "4906982 MVC voxel-versus-TSDF readout", "generatedAt": generated,
            "sources": [source],
            "cards": [],
            "charts": [
                {"id": "chart_roofer", "title": "Roofer roof XY coverage", "subtitle": "Existing voxel and fixed TSDF readouts for all six 20k checkpoints", "intent": "comparison", "question": "Does TSDF stabilize complete Roofer assembly?", "rationale": "A 12-case categorical bar retains every arm-replica-method outcome.", "comparisonContext": {"baseline": "existing voxel readout", "grain": "arm-replica-method", "unit": "fraction"}, "type": "bar", "dataset": "case_methods", "sourceId": "readout_source", "encodings": {"x": {"field": "case_method", "type": "nominal", "label": "Case and method"}, "y": {"field": "roofer_coverage", "type": "quantitative", "label": "Roof XY coverage"}}, "valueFormat": "percent", "layout": "full", "surface": {"palette": {"kind": "sequential"}, "valueLabels": "all"}},
                {"id": "chart_height", "title": "Classified roof-point median absolute height error", "subtitle": "Evaluation-only LoD2 correspondence after the fixed datum shift", "intent": "comparison", "question": "Does TSDF preserve or improve the aligned normal surface?", "rationale": "The same 12 cases expose whether readout completeness trades against metric height accuracy.", "comparisonContext": {"baseline": "existing voxel readout", "grain": "arm-replica-method", "unit": "metres"}, "type": "bar", "dataset": "case_methods", "sourceId": "readout_source", "encodings": {"x": {"field": "case_method", "type": "nominal", "label": "Case and method"}, "y": {"field": "point_median_abs_dz_m", "type": "quantitative", "label": "Median |dZ|", "unit": "m"}}, "valueFormat": "number", "layout": "full", "surface": {"palette": {"kind": "sequential"}, "valueLabels": "all"}},
            ],
            "tables": [
                {"id": "table_cases", "title": "Exact readout measurements", "subtitle": "Twelve fixed 20k method-case rows; reference metrics are evaluation-only", "dataset": "case_methods", "sourceId": "readout_source", "defaultSort": {"field": "case_method", "direction": "asc"}, "density": "spacious", "layout": "full", "columns": [{"field": "case_method", "label": "Case"}, {"field": "roofer_coverage", "label": "Roofer coverage", "format": "percent"}, {"field": "fscore_0p5m", "label": "Surface F0.5m", "format": "percent"}, {"field": "point_median_abs_dz_m", "label": "Point median |dZ| (m)", "format": "number"}, {"field": "point_median_normal_deg", "label": "Point normal angle (deg)", "format": "number"}, {"field": "classified_z_gt650", "label": "Classified Z>650", "format": "number"}, {"field": "roofer_z_gt650", "label": "Roofer Z>650", "format": "number"}]},
            ],
            "blocks": [
                {"id": "title", "type": "markdown", "body": "# 4906982 MVC voxel-versus-TSDF readout", "layout": "full"},
                {"id": "summary", "type": "markdown", "body": summary, "layout": "full"},
                {"id": "finding_roofer", "type": "markdown", "body": "## TSDF tests the downstream explanation without changing training\n\nThe coverage chart compares the immutable voxel outputs with one fixed TSDF rule applied to the same checkpoints, views, cameras, alpha threshold, classification, footprint, and Roofer defaults. A gain that repeats across R1-R3 supports a downstream integration explanation; an R1-only result leaves GS geometry instability unresolved.", "layout": "full"},
                {"id": "roofer_chart", "type": "chart", "chartId": "chart_roofer", "layout": "full"},
                {"id": "finding_surface", "type": "markdown", "body": "## Completeness and metric surface alignment are evaluated separately\n\nA complete polygon can still have incorrect height, while an accurate local point subset can still fail surface assembly. The height chart therefore remains separate from Roofer coverage and from the gross high-Z transmission count.", "layout": "full"},
                {"id": "height_chart", "type": "chart", "chartId": "chart_height", "layout": "full"},
                {"id": "exact", "type": "table", "tableId": "table_cases", "layout": "full"},
                {"id": "definitions", "type": "markdown", "body": "## What the metrics mean\n\nPopulation: two arms × three same-state continuations at 20k. Voxel is the existing 0.15 m ≥2-view aggregation. TSDF is Open3D scalable TSDF at 0.15 m with 0.45 m truncation, followed by a ≥2-view reprojection-support filter. Height and normal errors use evaluation-only LoD2 roof planes after a locked −45.7 m datum shift. Roofer coverage is semantic RoofSurface XY union divided by the shared footprint area.", "layout": "full"},
                {"id": "method", "type": "markdown", "body": "## Fixed readout design\n\nNo training or voxel fusion was rerun. Each checkpoint was rendered over the exact 55-view crop with its frozen camera model. Per-view depth, normal, alpha, RGB, K, and w2c were preserved. TSDF used no LoD2 Z/normal, no per-arm tuning, and no per-replica tuning. Both methods used identical classification and Roofer defaults.", "layout": "full"},
                {"id": "limits", "type": "markdown", "body": "## Limits and robustness\n\nThis is one building and one random seed with three CUDA continuations, not independent seeds. TSDF changes the surface estimator and sampling distribution, so point-count differences are expected. Reference and imagery vintages can differ. The 95% coverage marker is diagnostic, not an official usability criterion.", "layout": "full"},
                {"id": "next", "type": "markdown", "body": "## Recommended next step\n\n" + next_text, "layout": "full"},
                {"id": "questions", "type": "markdown", "body": "## Further questions\n\n- At which stage are high-Z rendered pixels rejected or retained?\n- Does any TSDF gain repeat on additional buildings without parameter change?\n- If TSDF remains unstable, does confidence-gated MVS depth supervision reduce both rendered depth tails and Roofer variance?", "layout": "full"},
            ],
        },
        "snapshot": {"version": 1, "generatedAt": generated, "status": "ready", "datasets": {"case_methods": chart_rows}},
        "sources": [source], "package_info": {"root": ".", "manifestPath": "report_artifact.json", "snapshotPath": "report_artifact.json"},
    }
    atomic_json(output / "report_artifact.json", artifact)


def docker_evaluate(config_path: Path, output: Path) -> None:
    import numpy as np
    from shapely.geometry import shape
    from scripts.p2.e3_local_4906982_mvc_readout_diag_v1.run import (
        load_cityjsonseq, parse_reference_roofs, point_metrics, surface_metrics,
    )

    cfg = load_yaml(config_path)
    source_root = Path(cfg["source_task_root"])
    footprint = shape(json.loads(Path(cfg["shared_footprint"]).read_text(encoding="utf-8"))["features"][0]["geometry"])
    refs = parse_reference_roofs(Path(cfg["reference_lod2_gml"]), cfg["building_id"])
    eval_cfg = dict(cfg["evaluation"])
    eval_cfg["full_roof_xy_coverage_threshold"] = eval_cfg.pop("diagnostic_full_roof_xy_coverage_threshold")
    rows = []
    for arm in cfg["arms"]:
        for replica in cfg["replicas"]:
            source_eval = json.loads((source_root / "arms" / arm / replica / "evaluation/step_020000/evaluation.json").read_text(encoding="utf-8"))
            render_receipt = json.loads((output / "cases" / arm / replica / "tsdf/tsdf_receipt.json").read_text(encoding="utf-8"))
            for method in ("VOXEL", "TSDF"):
                root = source_root / "arms" / arm / replica / "evaluation/step_020000/fusion" if method == "VOXEL" else output / "cases" / arm / replica / "tsdf"
                fused = root / "fused_surface.laz"
                classified = root / "classified_surface.laz"
                city = next((root / "roofer/output").glob("*.city.jsonl"))
                terminal = json.loads((root / "roofer/roofer_terminal.json").read_text(encoding="utf-8"))
                preds, vertices = load_cityjsonseq(city, cfg["building_id"], float(eval_cfg["prediction_z_shift_to_reference_m"]))
                row: dict[str, Any] = {
                    "arm": arm, "replica": replica, "method": method, "completed_updates": 20000,
                    "checkpoint_sha256": cfg["checkpoint_sha256"][arm][replica],
                    "gaussian_z_gt650": int(source_eval["geometry"]["count_z_gt_650m"]),
                    "render_xy_retained_z_gt650_pixels": int(render_receipt["xy_retained_render_z_gt_650_pixels"]),
                    "raw_tsdf_z_gt650": int(render_receipt["raw_tsdf_z_gt_650_count"]) if method == "TSDF" else None,
                    "support_filtered_tsdf_z_gt650": int(render_receipt["support_filtered_z_gt_650_count"]) if method == "TSDF" else None,
                    "roofer_rf_success": bool(terminal.get("rf_success")),
                    "roofer_internal_rmse": (terminal.get("target_attributes") or {}).get("rf_rmse_lod22"),
                    "scientific_verdict": None,
                }
                for prefix, payload in (("fused", point_metrics(fused, footprint, refs, eval_cfg, classified=False)), ("classified", point_metrics(classified, footprint, refs, eval_cfg, classified=True)), ("roofer", surface_metrics(preds, vertices, refs, footprint, eval_cfg))):
                    row.update({f"{prefix}_{key}": value for key, value in payload.items()})
                row["roofer_full_coverage_diagnostic"] = row["roofer_roof_xy_coverage_fraction"] >= float(eval_cfg["full_roof_xy_coverage_threshold"])
                rows.append(row)
    rows.sort(key=lambda row: (row["arm"], row["replica"], row["method"]))
    write_csv(output / "readout_metrics.csv", rows)
    deltas = []
    for arm in cfg["arms"]:
        for replica in cfg["replicas"]:
            voxel = next(row for row in rows if row["arm"] == arm and row["replica"] == replica and row["method"] == "VOXEL")
            tsdf = next(row for row in rows if row["arm"] == arm and row["replica"] == replica and row["method"] == "TSDF")
            delta = {"arm": arm, "replica": replica}
            for field in ("classified_abs_dz_m_median", "classified_abs_dz_m_p95", "classified_normal_angle_deg_median", "classified_z_gt_650_count", "roofer_roof_xy_coverage_fraction", "roofer_surface_fscore_0p5m", "roofer_vertex_z_gt_650_count"):
                a, b = tsdf.get(field), voxel.get(field)
                delta[field + "_tsdf_minus_voxel"] = None if a is None or b is None else float(a) - float(b)
            deltas.append(delta)
    write_csv(output / "paired_readout_deltas.csv", deltas)
    threshold = float(eval_cfg["full_roof_xy_coverage_threshold"])
    mvc05 = [row for row in rows if row["arm"] == "MVC05"]
    coverage = {method: {row["replica"]: row["roofer_roof_xy_coverage_fraction"] for row in mvc05 if row["method"] == method} for method in ("VOXEL", "TSDF")}
    metrics = {
        "schema": "jointbuildgs.p2.e3_local_4906982_mvc_tsdf_readout_v1.metrics.v1",
        "status": "COMPLETE_TECHNICAL_DIAGNOSTIC", "case_method_rows": len(rows),
        "training_runs_started": 0, "voxel_fusion_reruns_started": 0, "tsdf_reconstructions": 6,
        "mvc05_roofer_coverage": coverage,
        "voxel_mvc05_full_coverage_count": sum(value >= threshold for value in coverage["VOXEL"].values()),
        "tsdf_mvc05_full_coverage_count": sum(value >= threshold for value in coverage["TSDF"].values()),
        "diagnostic_full_coverage_threshold": threshold,
        "all_roofer_vertices_z_le_650": all(row["roofer_vertex_z_gt_650_count"] == 0 for row in rows),
        "reference_evaluation_only": True, "official_PASS_usable": None, "scientific_verdict": None,
    }
    atomic_json(output / "metrics.json", metrics)
    make_panel(output / "representative_images/voxel_vs_tsdf_roofer_20k.png", rows, cfg, footprint, refs)
    build_report(output, rows, metrics)
    comparison = f"""# {cfg['task_id']}\n\n## Measured readout diagnostic\n\n- Existing voxel MVC05 Roofer coverage: {', '.join(f'{k}={100*v:.3f}%' for k,v in coverage['VOXEL'].items())}.\n- Fixed TSDF MVC05 Roofer coverage: {', '.join(f'{k}={100*v:.3f}%' for k,v in coverage['TSDF'].items())}.\n- Full-coverage count at the diagnostic 95% marker: voxel={metrics['voxel_mvc05_full_coverage_count']}/3, TSDF={metrics['tsdf_mvc05_full_coverage_count']}/3.\n- Training reruns=0; voxel fusion reruns=0; TSDF reconstructions=6.\n- Scientific verdict: `null`.\n"""
    (output / "comparison.md").write_text(comparison, encoding="utf-8")
    notes = f"""# {cfg['task_id']}\n\nStatus: `COMPLETE_TECHNICAL_DIAGNOSTIC` after report delivery.\n\n- Six immutable 20k checkpoints; exact 55-view render each.\n- Per-view depth/normal/alpha/RGB/K/w2c preserved under `cases/*/*/renders/`.\n- Fixed TSDF: voxel 0.15 m, truncation 0.45 m, >=2-view reprojection support.\n- Existing voxel outputs were read only and never rerun.\n- Scientific verdict: `null`.\n"""
    (output / "NOTES.md").write_text(notes, encoding="utf-8")
    issues = """# Issues\n\n1. R1-R3 are continuations from one 7k state and one random seed, not independent seeds.\n2. TSDF changes surface sampling density relative to voxel aggregation; exact point counts are not directly comparable as model capacity.\n3. LoD2 and current imagery may differ in vintage; reference residuals can include scene change.\n4. The 95% Roofer coverage marker is diagnostic, not an official usability threshold.\n5. The first 16-view smoke attempt failed before rendering because gsplat JIT tried to create `/.cache` under the non-root container user. The log is preserved as `logs/smoke_attempt_001_failed.log`; a task-owned `TORCH_EXTENSIONS_DIR` was added before retry.\n6. The first MVC0/R1 Roofer terminal-record attempt failed after Roofer succeeded because the p0-tools image does not include PyYAML. The failed log is preserved under that case; the fixed recorder uses the contract-frozen building ID and seals the existing CityJSONSeq without rerunning Roofer.\n7. Portable report browser QA may remain structural-only when Chromium is unavailable; see `logs/report_delivery.log`.\n\n`scientific_verdict` remains `null`.\n"""
    (output / "issues.md").write_text(issues, encoding="utf-8")
    chart_map = {"schema": "jointbuildgs.p2.e3_local_4906982_mvc_tsdf_readout_v1.chart_map.v1", "charts": [{"id": "chart_roofer", "question": "Does TSDF stabilize Roofer?", "family": "comparison", "type": "bar", "fields": ["case_method", "roofer_coverage"]}, {"id": "chart_height", "question": "Does TSDF preserve metric height accuracy?", "family": "comparison", "type": "bar", "fields": ["case_method", "point_median_abs_dz_m"]}], "omissions": [{"visual": "trend line", "reason": "only one checkpoint is in scope"}, {"visual": "single combined score", "reason": "high-Z, normal-surface error, and Roofer completeness must remain separate"}]}
    atomic_json(output / "control/chart_map.json", chart_map)
    print(json.dumps(metrics, indent=2))


def make_panel(path: Path, rows: list[dict[str, Any]], cfg: dict[str, Any], footprint: Any, refs: list[Any]) -> None:
    import laspy
    import matplotlib
    import numpy as np
    from scripts.p2.e3_local_4906982_mvc_readout_diag_v1.run import flatten_polygons, load_cityjsonseq

    matplotlib.use("Agg")
    from matplotlib import pyplot as plt

    methods = ("VOXEL", "TSDF_RAW", "TSDF_BOUNDED")
    roots = {"TSDF_RAW": "tsdf", "TSDF_BOUNDED": "tsdf_bounded"}
    fig, axes = plt.subplots(3, 6, figsize=(22, 12), dpi=145, constrained_layout=True)
    source_root = Path(cfg["source_task_root"])
    fp = np.asarray(footprint.exterior.coords)
    for column, (arm, replica) in enumerate((a, r) for a in cfg["arms"] for r in cfg["replicas"]):
        for row_index, method in enumerate(methods):
            ax = axes[row_index, column]
            root = (source_root / "arms" / arm / replica / "evaluation/step_020000/fusion") if method == "VOXEL" else (Path("/task") / "cases" / arm / replica / roots[method])
            cloud = laspy.read(root / "classified_surface.laz")
            x, y = np.asarray(cloud.x), np.asarray(cloud.y)
            selected = np.asarray(cloud.classification) == 6
            x, y = x[selected], y[selected]
            if len(x) > 12000:
                keep = np.linspace(0, len(x) - 1, 12000, dtype=int)
                x, y = x[keep], y[keep]
            ax.scatter(x, y, s=0.18, c="#a8a8a8", alpha=0.25, linewidths=0)
            city = next((root / "roofer/output").glob("*.city.jsonl"))
            preds, _ = load_cityjsonseq(city, cfg["building_id"], float(cfg["evaluation"]["prediction_z_shift_to_reference_m"]))
            for surface in preds:
                for poly in flatten_polygons(surface.polygon):
                    xy = np.asarray(poly.exterior.coords)
                    ax.fill(xy[:, 0], xy[:, 1], color="#c51b8a" if arm == "MVC05" else "#1688c7", alpha=0.38, linewidth=0.5, edgecolor="#222222")
            for surface in refs:
                for poly in flatten_polygons(surface.polygon):
                    xy = np.asarray(poly.exterior.coords)
                    ax.plot(xy[:, 0], xy[:, 1], color="#00a6a6", linewidth=1.0, linestyle="--")
            metric = next(item for item in rows if item["method"] == method and item["arm"] == arm and item["replica"] == replica)
            ax.plot(fp[:, 0], fp[:, 1], color="#111111", linewidth=1.1)
            ax.set_title(f"{method} {arm} {replica}\nroof {100*metric['roofer_roof_xy_coverage_fraction']:.2f}% · F0.5 {metric['roofer_surface_fscore_0p5m']:.3f}", fontsize=8)
            ax.set_aspect("equal")
            ax.set_axis_off()
    fig.suptitle("4906982 · voxel / raw TSDF / image-derived bounded TSDF · evaluation-only LoD2 dashed", fontsize=14, fontweight="bold")
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path)
    plt.close(fig)


def build_report(output: Path, rows: list[dict[str, Any]], metrics: dict[str, Any]) -> None:
    generated = utc_now()
    chart_rows = [{"case_method": f"{r['arm']} {r['replica']} {r['method']}", "arm": r["arm"], "replica": r["replica"], "method": r["method"], "roofer_coverage": r["roofer_roof_xy_coverage_fraction"], "fscore_0p5m": r["roofer_surface_fscore_0p5m"], "point_median_abs_dz_m": r["classified_abs_dz_m_median"], "point_median_normal_deg": r["classified_normal_angle_deg_median"], "classified_z_gt650": r["classified_z_gt_650_count"], "roofer_z_gt650": r["roofer_vertex_z_gt_650_count"]} for r in rows]
    source = {"id": "readout_source", "label": "Six-checkpoint three-method readout metrics", "path": "readout_metrics.csv", "query": {"engine": "SQLite over frozen diagnostic snapshot", "language": "sql", "description": "Select all 18 method-case evaluation rows.", "filters": ["completed_updates = 20000", "method in (VOXEL, TSDF_RAW, TSDF_BOUNDED)"], "metric_definitions": ["Roofer coverage is semantic RoofSurface XY union area divided by the shared footprint area.", "Point errors use evaluation-only LoD2 RoofSurface after the fixed datum shift."], "sql": "SELECT * FROM readout_metrics ORDER BY arm, replica, method", "tables_used": ["readout_metrics"]}}
    raw_full = metrics["raw_tsdf_mvc05_full_coverage_count"]
    bounded_full = metrics["bounded_tsdf_mvc05_full_coverage_count"]
    if bounded_full == 3:
        next_text = "The common image-derived Z-bounded TSDF made all three MVC05 continuations complete at the diagnostic marker. Preserve MVC and this readout contract, then validate unchanged parameters on additional buildings before introducing depth supervision."
    else:
        next_text = "The common image-derived Z-bounded TSDF did not make all three MVC05 continuations complete. Preserve the downstream result and preregister a confidence-gated MVS depth-only training arm; add normal supervision only if depth stabilizes height but not plane orientation."
    summary = f"""## Technical summary\n\n- **MVC improved the evaluation-only normal-surface height and normal errors at 20k, while gross high-Z remained.** This diagnostic does not retrain or merge those endpoints.\n- **Raw TSDF is a failure-mechanism probe.** It reached full-roof coverage in **{raw_full}/3** MVC05 continuations but admitted large high-Z surfaces and degraded metric point errors.\n- **Bounded TSDF tests the existing production-like C3 AOI rule without LoD2.** It reached full-roof coverage in **{bounded_full}/3**, versus **{metrics['voxel_mvc05_full_coverage_count']}/3** for the immutable voxel readout.\n- **Next action:** {next_text}\n\nThese are one-building technical measurements. `scientific_verdict` remains `null`."""
    artifact = {
        "surface": "report",
        "manifest": {
            "version": 1, "title": "4906982 MVC downstream readout diagnostic", "generatedAt": generated, "sources": [source], "cards": [],
            "charts": [
                {"id": "chart_roofer", "title": "Roofer roof XY coverage", "subtitle": "Voxel, raw TSDF, and common image-derived bounded TSDF", "intent": "comparison", "question": "Which readout stabilizes complete Roofer assembly?", "rationale": "All 18 arm-replica-method outcomes remain visible.", "comparisonContext": {"baseline": "existing voxel readout", "grain": "arm-replica-method", "unit": "fraction"}, "type": "bar", "dataset": "case_methods", "sourceId": "readout_source", "encodings": {"x": {"field": "case_method", "type": "nominal", "label": "Case and method"}, "y": {"field": "roofer_coverage", "type": "quantitative", "label": "Roof XY coverage"}}, "valueFormat": "percent", "layout": "full", "surface": {"palette": {"kind": "categorical"}, "valueLabels": "all"}},
                {"id": "chart_height", "title": "Classified roof-point median absolute height error", "subtitle": "Evaluation-only LoD2 correspondence after the fixed datum shift", "intent": "comparison", "question": "Does a readout preserve the aligned normal surface?", "rationale": "Coverage and metric surface accuracy remain separate.", "comparisonContext": {"baseline": "existing voxel readout", "grain": "arm-replica-method", "unit": "metres"}, "type": "bar", "dataset": "case_methods", "sourceId": "readout_source", "encodings": {"x": {"field": "case_method", "type": "nominal", "label": "Case and method"}, "y": {"field": "point_median_abs_dz_m", "type": "quantitative", "label": "Median |dZ|", "unit": "m"}}, "valueFormat": "number", "layout": "full", "surface": {"palette": {"kind": "categorical"}, "valueLabels": "all"}},
            ],
            "tables": [{"id": "table_cases", "title": "Exact readout measurements", "subtitle": "Eighteen fixed 20k method-case rows; reference metrics are evaluation-only", "dataset": "case_methods", "sourceId": "readout_source", "defaultSort": {"field": "case_method", "direction": "asc"}, "density": "spacious", "layout": "full", "columns": [{"field": "case_method", "label": "Case"}, {"field": "roofer_coverage", "label": "Roofer coverage", "format": "percent"}, {"field": "fscore_0p5m", "label": "Surface F0.5m", "format": "percent"}, {"field": "point_median_abs_dz_m", "label": "Point median |dZ| (m)", "format": "number"}, {"field": "point_median_normal_deg", "label": "Point normal angle (deg)", "format": "number"}, {"field": "classified_z_gt650", "label": "Classified Z>650", "format": "number"}, {"field": "roofer_z_gt650", "label": "Roofer Z>650", "format": "number"}]}],
            "blocks": [
                {"id": "title", "type": "markdown", "body": "# 4906982 MVC downstream readout diagnostic", "layout": "full"},
                {"id": "summary", "type": "markdown", "body": summary, "layout": "full"},
                {"id": "coverage_text", "type": "markdown", "body": "## Roofer completeness\n\nRaw TSDF and bounded TSDF reuse the exact same saved 55-view render buffers. The only added bounded rule is the common MVC0 7k image-derived ground interval, applied identically to every arm and replica before integration.", "layout": "full"},
                {"id": "roofer_chart", "type": "chart", "chartId": "chart_roofer", "layout": "full"},
                {"id": "surface_text", "type": "markdown", "body": "## Normal surface accuracy\n\nA complete Roofer polygon can have the wrong height. Conversely, locally accurate roof points can still fail assembly. Height, normal, high-Z transmission, and footprint coverage are therefore reported independently.", "layout": "full"},
                {"id": "height_chart", "type": "chart", "chartId": "chart_height", "layout": "full"},
                {"id": "exact", "type": "table", "tableId": "table_cases", "layout": "full"},
                {"id": "method", "type": "markdown", "body": "## Fixed design\n\nNo training or voxel fusion was rerun. TSDF voxel/truncation/support are 0.15 m / 0.45 m / at least 2 views. Raw TSDF has no Z clip. Bounded TSDF applies [558.159-2, 558.159+45] m from one hash-locked MVC0 7k Roofer ground record. LoD2 enters evaluation only.", "layout": "full"},
                {"id": "limits", "type": "markdown", "body": "## Limits\n\nThis is one building and one random seed with three CUDA continuations, not three independent seeds. The 95% marker is diagnostic, not an official usability threshold. Reference and imagery vintages can differ.", "layout": "full"},
                {"id": "next", "type": "markdown", "body": "## Recommended next step\n\n" + next_text, "layout": "full"},
            ],
        },
        "snapshot": {"version": 1, "generatedAt": generated, "status": "ready", "datasets": {"case_methods": chart_rows}},
        "sources": [source], "package_info": {"root": ".", "manifestPath": "report_artifact.json", "snapshotPath": "report_artifact.json"},
    }
    atomic_json(output / "report_artifact.json", artifact)


def docker_evaluate(config_path: Path, output: Path) -> None:
    from shapely.geometry import shape
    from scripts.p2.e3_local_4906982_mvc_readout_diag_v1.run import load_cityjsonseq, parse_reference_roofs, point_metrics, surface_metrics

    cfg = load_yaml(config_path)
    source_root = Path(cfg["source_task_root"])
    footprint = shape(json.loads(Path(cfg["shared_footprint"]).read_text(encoding="utf-8"))["features"][0]["geometry"])
    refs = parse_reference_roofs(Path(cfg["reference_lod2_gml"]), cfg["building_id"])
    eval_cfg = dict(cfg["evaluation"])
    eval_cfg["full_roof_xy_coverage_threshold"] = eval_cfg.pop("diagnostic_full_roof_xy_coverage_threshold")
    method_dirs = {"TSDF_RAW": "tsdf", "TSDF_BOUNDED": "tsdf_bounded"}
    methods = ("VOXEL", "TSDF_RAW", "TSDF_BOUNDED")
    rows: list[dict[str, Any]] = []
    for arm in cfg["arms"]:
        for replica in cfg["replicas"]:
            source_eval = json.loads((source_root / "arms" / arm / replica / "evaluation/step_020000/evaluation.json").read_text(encoding="utf-8"))
            render_receipt = json.loads((output / "cases" / arm / replica / "tsdf/tsdf_receipt.json").read_text(encoding="utf-8"))
            for method in methods:
                root = (source_root / "arms" / arm / replica / "evaluation/step_020000/fusion") if method == "VOXEL" else (output / "cases" / arm / replica / method_dirs[method])
                method_receipt = None if method == "VOXEL" else json.loads((root / "tsdf_receipt.json").read_text(encoding="utf-8"))
                fused, classified = root / "fused_surface.laz", root / "classified_surface.laz"
                city = next((root / "roofer/output").glob("*.city.jsonl"))
                terminal = json.loads((root / "roofer/roofer_terminal.json").read_text(encoding="utf-8"))
                preds, vertices = load_cityjsonseq(city, cfg["building_id"], float(eval_cfg["prediction_z_shift_to_reference_m"]))
                row: dict[str, Any] = {
                    "arm": arm, "replica": replica, "method": method, "completed_updates": 20000,
                    "checkpoint_sha256": cfg["checkpoint_sha256"][arm][replica],
                    "gaussian_z_gt650": int(source_eval["geometry"]["count_z_gt_650m"]),
                    "render_xy_retained_z_gt650_pixels": int(render_receipt["xy_retained_render_z_gt_650_pixels"]),
                    "raw_tsdf_z_gt650": None if method_receipt is None else int(method_receipt["raw_tsdf_z_gt_650_count"]),
                    "support_filtered_tsdf_z_gt650": None if method_receipt is None else int(method_receipt["support_filtered_z_gt_650_count"]),
                    "z_rejected_render_pixels": None if method != "TSDF_BOUNDED" else int(method_receipt["z_rejected_render_pixels"]),
                    "roofer_rf_success": bool(terminal.get("rf_success")),
                    "roofer_internal_rmse": (terminal.get("target_attributes") or {}).get("rf_rmse_lod22"),
                    "scientific_verdict": None,
                }
                for prefix, payload in (("fused", point_metrics(fused, footprint, refs, eval_cfg, classified=False)), ("classified", point_metrics(classified, footprint, refs, eval_cfg, classified=True)), ("roofer", surface_metrics(preds, vertices, refs, footprint, eval_cfg))):
                    row.update({f"{prefix}_{key}": value for key, value in payload.items()})
                row["roofer_full_coverage_diagnostic"] = row["roofer_roof_xy_coverage_fraction"] >= float(eval_cfg["full_roof_xy_coverage_threshold"])
                rows.append(row)
    rows.sort(key=lambda row: (row["arm"], row["replica"], methods.index(row["method"])))
    write_csv(output / "readout_metrics.csv", rows)
    deltas = []
    for arm in cfg["arms"]:
        for replica in cfg["replicas"]:
            voxel = next(row for row in rows if row["arm"] == arm and row["replica"] == replica and row["method"] == "VOXEL")
            for method in ("TSDF_RAW", "TSDF_BOUNDED"):
                candidate = next(row for row in rows if row["arm"] == arm and row["replica"] == replica and row["method"] == method)
                delta = {"arm": arm, "replica": replica, "method": method, "baseline": "VOXEL"}
                for field in ("classified_abs_dz_m_median", "classified_abs_dz_m_p95", "classified_normal_angle_deg_median", "classified_z_gt_650_count", "roofer_roof_xy_coverage_fraction", "roofer_surface_fscore_0p5m", "roofer_vertex_z_gt_650_count"):
                    a, b = candidate.get(field), voxel.get(field)
                    delta[field + "_minus_voxel"] = None if a is None or b is None else float(a) - float(b)
                deltas.append(delta)
    write_csv(output / "paired_readout_deltas.csv", deltas)
    threshold = float(eval_cfg["full_roof_xy_coverage_threshold"])
    mvc05 = [row for row in rows if row["arm"] == "MVC05"]
    coverage = {method: {row["replica"]: row["roofer_roof_xy_coverage_fraction"] for row in mvc05 if row["method"] == method} for method in methods}
    metrics = {
        "schema": "jointbuildgs.p2.e3_local_4906982_mvc_tsdf_readout_v1.metrics.v2", "status": "COMPLETE_TECHNICAL_DIAGNOSTIC",
        "case_method_rows": len(rows), "training_runs_started": 0, "voxel_fusion_reruns_started": 0, "tsdf_reconstructions": 12,
        "mvc05_roofer_coverage": coverage,
        "voxel_mvc05_full_coverage_count": sum(value >= threshold for value in coverage["VOXEL"].values()),
        "raw_tsdf_mvc05_full_coverage_count": sum(value >= threshold for value in coverage["TSDF_RAW"].values()),
        "bounded_tsdf_mvc05_full_coverage_count": sum(value >= threshold for value in coverage["TSDF_BOUNDED"].values()),
        "diagnostic_full_coverage_threshold": threshold,
        "all_roofer_vertices_z_le_650": all(row["roofer_vertex_z_gt_650_count"] == 0 for row in rows),
        "reference_evaluation_only": True, "official_PASS_usable": None, "scientific_verdict": None,
    }
    atomic_json(output / "metrics.json", metrics)
    make_panel(output / "representative_images/voxel_raw_bounded_tsdf_roofer_20k.png", rows, cfg, footprint, refs)
    build_report(output, rows, metrics)
    cov = lambda method: ", ".join(f"{key}={100*value:.3f}%" for key, value in coverage[method].items())
    comparison = f"""# {cfg['task_id']}\n\n## Measured readout diagnostic\n\n- Existing voxel MVC05 Roofer coverage: {cov('VOXEL')}.\n- Raw no-Z-clip TSDF MVC05 Roofer coverage: {cov('TSDF_RAW')}.\n- Common image-derived bounded TSDF MVC05 Roofer coverage: {cov('TSDF_BOUNDED')}.\n- Full-coverage count at the diagnostic 95% marker: voxel={metrics['voxel_mvc05_full_coverage_count']}/3, raw TSDF={metrics['raw_tsdf_mvc05_full_coverage_count']}/3, bounded TSDF={metrics['bounded_tsdf_mvc05_full_coverage_count']}/3.\n- Training reruns=0; voxel fusion reruns=0; TSDF reconstructions=12.\n- Raw TSDF is retained as a failure-mechanism probe; high-Z transmission, normal-surface errors, and Roofer coverage are separate endpoints in `readout_metrics.csv`.\n- Scientific verdict: `null`.\n"""
    (output / "comparison.md").write_text(comparison, encoding="utf-8")
    notes = f"""# {cfg['task_id']}\n\nStatus: `COMPLETE_TECHNICAL_DIAGNOSTIC` after report delivery.\n\n- Six immutable 20k checkpoints; exact 55-view render each.\n- Per-view depth/normal/alpha/RGB/K/w2c preserved under `cases/*/*/renders/`.\n- Raw and bounded TSDF both use voxel 0.15 m, truncation 0.45 m, and >=2-view reprojection support.\n- Bounded TSDF alone adds the hash-locked common 7k image-derived ground interval [556.159, 603.159] m.\n- Existing voxel outputs were read only and never rerun.\n- Scientific verdict: `null`.\n"""
    (output / "NOTES.md").write_text(notes, encoding="utf-8")
    issues = """# Issues\n\n1. R1-R3 are continuations from one 7k state and one random seed, not independent seeds.\n2. Raw TSDF amplified rendered high-Z observations into multi-view surfaces; it is retained as a negative mechanism result.\n3. TSDF changes surface sampling density relative to voxel aggregation; point counts are not model-capacity comparisons.\n4. LoD2 and current imagery may differ in vintage; reference residuals can include scene change.\n5. The 95% Roofer coverage marker is diagnostic, not an official usability threshold.\n6. The first smoke failed because the non-root gsplat JIT cache resolved to `/.cache`; its failed log is preserved and the retry used a task-owned cache.\n7. The first raw MVC0/R1 Roofer recorder failed after Roofer success because p0-tools lacks PyYAML; the failed log is preserved and the existing CityJSONSeq was sealed without rerunning Roofer.\n8. Portable report browser QA may remain structural-only when Chromium is unavailable; see `logs/report_delivery.log`.\n\n`scientific_verdict` remains `null`.\n"""
    (output / "issues.md").write_text(issues, encoding="utf-8")
    chart_map = {"schema": "jointbuildgs.p2.e3_local_4906982_mvc_tsdf_readout_v1.chart_map.v2", "charts": [{"id": "chart_roofer", "question": "Which downstream readout stabilizes Roofer?", "family": "comparison", "type": "bar", "fields": ["case_method", "roofer_coverage"]}, {"id": "chart_height", "question": "Which readout preserves metric height accuracy?", "family": "comparison", "type": "bar", "fields": ["case_method", "point_median_abs_dz_m"]}], "omissions": [{"visual": "trend line", "reason": "only one checkpoint is in scope"}, {"visual": "single combined score", "reason": "high-Z, normal-surface error, and Roofer completeness must remain separate"}]}
    atomic_json(output / "control/chart_map.json", chart_map)
    print(json.dumps(metrics, indent=2))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", choices=["preflight", "smoke", "cases", "evaluate", "report", "all"], default="all")
    parser.add_argument("--inside-docker", choices=["preflight", "render-tsdf", "reconstruct-bounded", "verify-classification", "record-roofer", "evaluate"])
    parser.add_argument("--config", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--case")
    parser.add_argument("--method", choices=["tsdf", "tsdf_bounded"], default="tsdf")
    parser.add_argument("--max-views", type=int)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.inside_docker:
        if args.config is None or args.output is None:
            raise SystemExit("--config and --output are required inside Docker")
        if args.inside_docker == "preflight":
            docker_preflight(args.config, args.output)
        elif args.inside_docker == "render-tsdf":
            if not args.case:
                raise SystemExit("--case is required")
            docker_render_tsdf(args.config, args.output, args.case, args.max_views)
        elif args.inside_docker == "reconstruct-bounded":
            if not args.case:
                raise SystemExit("--case is required")
            docker_reconstruct_bounded(args.config, args.output, args.case)
        elif args.inside_docker == "verify-classification":
            if not args.case:
                raise SystemExit("--case is required")
            docker_verify_classification(args.config, args.output, args.case, args.method)
        elif args.inside_docker == "record-roofer":
            if not args.case:
                raise SystemExit("--case is required")
            docker_record_roofer(args.config, args.output, args.case, args.method)
        elif args.inside_docker == "evaluate":
            docker_evaluate(args.config, args.output)
    else:
        host_main(args.phase)


if __name__ == "__main__":
    main()
