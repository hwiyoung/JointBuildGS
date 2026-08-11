#!/usr/bin/env python3
"""Thin, idempotent orchestration for the fused-surface-normal arm."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import types


REPO = Path(__file__).resolve().parents[3]
ARTIFACT_ROOT = REPO.parent / "JointBuildGS-artifacts"
TASK_ID = "P2-E3-LOCAL-4906982-FUSED-SURFACE-NORMAL-v1"
TASK_ROOT = ARTIFACT_ROOT / "phase-payloads/p2/e3_local_4906982_fused_surface_normal_v1" / TASK_ID
TEMPLATE = REPO / "scripts/p2/e3_local_4906982_mvs_normal_ablation_v1/run.py"
PREPARE = REPO / "scripts/p2/e3_local_4906982_fused_surface_normal_v1/prepare_targets.py"
EXTRACTOR_SOURCE = REPO / "scripts/p2/e3_local_4906982_fused_surface_normal_v1/extract_native_normal.cpp"
SOURCE_FUSED = ARTIFACT_ROOT / "phase-payloads/p2/e3_local_4906982_fused_vis_conf_v1/P2-E3-LOCAL-4906982-FUSED-VIS-CONF-v1"
SOURCE_RAW_NORMAL = ARTIFACT_ROOT / "phase-payloads/p2/e3_local_4906982_mvs_normal_ablation_v1/P2-E3-LOCAL-4906982-MVS-NORMAL-ABLATION-v1"
NATIVE_SOURCE = ARTIFACT_ROOT / "phase-payloads/p2/mvs_native_textured_mesh_preflight_v1/P2-MVS-NATIVE-DENSE-SCENE-RECOVERY-v2/work/mvs/openmvs"
NATIVE_INDEX = SOURCE_FUSED / "native_dmap/image_index.tsv"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def transformed_runner() -> types.ModuleType:
    source = TEMPLATE.read_text()
    replacements = (
        ("P2-E3-LOCAL-4906982-MVS-NORMAL-ABLATION-v1", TASK_ID),
        ("e3_local_4906982_mvs_normal_ablation_v1", "e3_local_4906982_fused_surface_normal_v1"),
        ("FUSED_VIS_CONF_MVS_NORMAL", "FUSED_VIS_CONF_FUSED_NORMAL"),
        ("mvs_depth_normal.yaml", "fused_depth_surface_normal.yaml"),
        ("mvs_normal_target_definition.json", "fused_surface_normal_target_definition.json"),
        ("mvs_normal_preflight_metrics.csv", "raw_native_fused_metrics.csv"),
        ("prepare_normal.py", "prepare_targets.py"),
        ("mvs_normal", "fused_surface_normal"),
        ("MVS normal", "fused surface normal"),
    )
    for old, new in replacements: source = source.replace(old, new)
    module = types.ModuleType("fused_surface_normal_runner")
    module.__file__ = str(Path(__file__).resolve())
    module.__name__ = "fused_surface_normal_runner"
    exec(compile(source, str(TEMPLATE), "exec"), module.__dict__)
    return module


runner = transformed_runner()


def extract_native() -> None:
    output = TASK_ROOT / "native_dmap_normal"; binary = TASK_ROOT / "control/bin/extract_native_normal"
    log_dir = TASK_ROOT / "logs"; log_dir.mkdir(parents=True, exist_ok=True); binary.parent.mkdir(parents=True, exist_ok=True); output.mkdir(parents=True, exist_ok=True)
    existing = sorted(output.glob("*.normal.npy"))
    receipt = TASK_ROOT / "control/native_normal_extraction_receipt.json"
    if len(existing) == 55 and receipt.is_file():
        body = json.loads(receipt.read_text())
        if body.get("passed") and all(sha256(path) == body["outputs_sha256"].get(path.name) for path in existing):
            print(receipt.read_text()); return
    build = [
        "docker", "run", "--rm", "-v", f"{REPO}:/workspace/JointBuildGS:ro", "-v", f"{ARTIFACT_ROOT}:/artifacts/JointBuildGS",
        "-w", "/workspace/JointBuildGS", "jointbuildgs-p0-openmvs:t0", "bash", "-lc",
        "g++ -std=c++14 -O2 scripts/p2/e3_local_4906982_fused_surface_normal_v1/extract_native_normal.cpp "
        "-I/usr/local/include/OpenMVS -I/usr/local/include/eigen3 -L/usr/local/lib/OpenMVS "
        "-lMVS -lIO -lCommon -lMath $(pkg-config --cflags --libs opencv) "
        "-lboost_iostreams -lboost_serialization -lpthread "
        "-o /artifacts/JointBuildGS/phase-payloads/p2/e3_local_4906982_fused_surface_normal_v1/"
        "P2-E3-LOCAL-4906982-FUSED-SURFACE-NORMAL-v1/control/bin/extract_native_normal",
    ]
    with (log_dir / "build_native_normal_extractor.log").open("w") as stream:
        proc = subprocess.run(build, text=True, stdout=stream, stderr=subprocess.STDOUT)
    if proc.returncode: raise RuntimeError("native normal extractor build failed")
    script = r'''set -euo pipefail
out=/artifacts/JointBuildGS/phase-payloads/p2/e3_local_4906982_fused_surface_normal_v1/P2-E3-LOCAL-4906982-FUSED-SURFACE-NORMAL-v1/native_dmap_normal
bin=/artifacts/JointBuildGS/phase-payloads/p2/e3_local_4906982_fused_surface_normal_v1/P2-E3-LOCAL-4906982-FUSED-SURFACE-NORMAL-v1/control/bin/extract_native_normal
src=/artifacts/JointBuildGS/phase-payloads/p2/mvs_native_textured_mesh_preflight_v1/P2-MVS-NATIVE-DENSE-SCENE-RECOVERY-v2/work/mvs/openmvs
index=/artifacts/JointBuildGS/phase-payloads/p2/e3_local_4906982_fused_vis_conf_v1/P2-E3-LOCAL-4906982-FUSED-VIS-CONF-v1/native_dmap/image_index.tsv
mkdir -p "$out"
while IFS=$'\t' read -r idx name; do
  stem="${name%.*}"
  target="$out/$stem.normal.npy"
  if [ ! -f "$target" ]; then "$bin" "$src/depth$(printf '%04d' "$idx").dmap" "$target"; fi
done < "$index"
'''
    argv = ["docker", "run", "--rm", "-v", f"{ARTIFACT_ROOT}:/artifacts/JointBuildGS", "jointbuildgs-p0-openmvs:t0", "bash", "-lc", script]
    with (log_dir / "extract_native_normals.log").open("w") as stream:
        proc = subprocess.run(argv, text=True, stdout=stream, stderr=subprocess.STDOUT)
    if proc.returncode: raise RuntimeError("native normal extraction failed")
    outputs = sorted(output.glob("*.normal.npy"))
    if len(outputs) != 55: raise RuntimeError(f"expected 55 native normal maps, got {len(outputs)}")
    body = {
        "schema": "jointbuildgs.p2.e3_local_4906982_fused_surface_normal_v1.native_extract.v1",
        "source": "OpenMVS native DMAP normalMap in camera space", "source_dmap_dir": str(NATIVE_SOURCE),
        "image_index": {"path": str(NATIVE_INDEX), "sha256": sha256(NATIVE_INDEX)},
        "extractor_source_sha256": sha256(EXTRACTOR_SOURCE), "extractor_binary_sha256": sha256(binary),
        "docker_image": "jointbuildgs-p0-openmvs:t0", "count": len(outputs),
        "outputs_sha256": {path.name: sha256(path) for path in outputs}, "return_code": proc.returncode,
        "passed": True, "scientific_verdict": None,
    }
    runner.base.atomic_json(receipt, body); print(json.dumps(body, indent=2, sort_keys=True))


def prepare_targets() -> None:
    extract_native()
    argv = runner.base.docker_base() + ["python", "/workspace/JointBuildGS/scripts/p2/e3_local_4906982_fused_surface_normal_v1/prepare_targets.py"]
    log = TASK_ROOT / "logs/prepare_targets.log"; started = runner.base.now()
    with log.open("w") as stream: proc = subprocess.run(argv, text=True, stdout=stream, stderr=subprocess.STDOUT)
    runner.base.record_operation("prepare_fused_surface_targets", argv, proc.returncode, started, runner.base.now())
    if proc.returncode: raise RuntimeError(f"target preparation failed; inspect {log}")
    print((TASK_ROOT / "fused_surface_normal_target_definition.json").read_text())


def preflight() -> None:
    runner.preflight()
    definition = json.loads((TASK_ROOT / "fused_surface_normal_target_definition.json").read_text())
    diff = "\n".join([
        "primary comparison: existing FUSED_VIS_CONF_MVS_NORMAL/R1 versus new FUSED_VIS_CONF_FUSED_NORMAL/R1",
        "context control: existing FUSED_VIS_CONF/R1",
        "branch: both normal arms are exact branches of the same FUSED_VIS_CONF full-state checkpoint at completed update 7000",
        "single scientific intervention in primary comparison: normal target only",
        "raw-normal arm target: COLMAP geometric normal on exact frozen FUSED_VIS_CONF mask",
        "fused-normal arm target: world primitive normal of the exact first-hit OpenMVS mesh triangle on the exact prior raw-normal valid mask",
        "unchanged: initialization/history through 7k, fused depth target/mask/L1/weight/schedule, expected rendered depth, normal weight/schedule/orientation, MVC, NC, densification, 55 views, seed, GPU",
        "LoD2 Z/RoofSurface/roof type training use: none", "scientific_verdict: null", "",
    ])
    runner.base.atomic_text(TASK_ROOT / "config_diff.txt", diff)
    contract_path = TASK_ROOT / "experiment_contract.json"; contract = json.loads(contract_path.read_text())
    contract.update({
        "question": "Does changing only the supported normal target from raw COLMAP to the exact fused-mesh first-hit surface normal improve usable geometry and Roofer read-out?",
        "comparison": {"context_control": "FUSED_VIS_CONF/R1", "read_only_raw_normal": "FUSED_VIS_CONF_MVS_NORMAL/R1", "intervention": "FUSED_VIS_CONF_FUSED_NORMAL/R1"},
        "single_intervention_primary_comparison": "normal target: raw per-view COLMAP to fused mesh surface",
        "target_valid_pixels": definition["target_valid_pixels"], "scientific_verdict": None,
    })
    runner.base.atomic_json(contract_path, contract)
    input_path = TASK_ROOT / "input_hashes.json"; inputs = json.loads(input_path.read_text())
    inputs["read_only_raw_normal_task"] = {"path": str(SOURCE_RAW_NORMAL / "input_hashes.json"), "sha256": sha256(SOURCE_RAW_NORMAL / "input_hashes.json")}
    inputs["native_normal_extraction_receipt"] = {"path": str(TASK_ROOT / "control/native_normal_extraction_receipt.json"), "sha256": sha256(TASK_ROOT / "control/native_normal_extraction_receipt.json")}
    runner.base.atomic_json(input_path, inputs)
    runner.base.atomic_text(TASK_ROOT / "NOTES.md", f"# {TASK_ID}\n\nStatus: `PREFLIGHT_BOUND`. One new fused-surface-normal arm; prior control and raw-normal arms are read-only comparators.\n\nscientific_verdict: null\n")
    print(diff, end="")


def main() -> None:
    choices = ("extract-native", "prepare-targets", "preflight", "binding-probe", "smoke", "fork-7k", "train-to-12k", "dose-gate", "train", "analyze-checkpoints", "stage3", "mvs-surface-audit", "finalize-measurements")
    parser = argparse.ArgumentParser(); parser.add_argument("command", choices=choices); command = parser.parse_args().command
    if command == "extract-native": extract_native()
    elif command == "prepare-targets": prepare_targets()
    elif command == "preflight": preflight()
    else: getattr(runner, command.replace("-", "_"))()


if __name__ == "__main__": main()
