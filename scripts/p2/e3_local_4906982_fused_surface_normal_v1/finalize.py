#!/usr/bin/env python3
"""Finalize the fused-surface-normal diagnostic without changing source results."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess


REPO = Path("/workspace/JointBuildGS")
AR = Path("/artifacts/JointBuildGS")
TASK_ID = "P2-E3-LOCAL-4906982-FUSED-SURFACE-NORMAL-v1"
ROOT = AR / "phase-payloads/p2/e3_local_4906982_fused_surface_normal_v1" / TASK_ID
SOURCES = (
    "configs/p2/e3_local_4906982_fused_surface_normal_v1/common.yaml",
    "configs/p2/e3_local_4906982_fused_surface_normal_v1/fused_depth_surface_normal.yaml",
    "configs/p2/e3_local_4906982_fused_surface_normal_v1/viewer.yaml",
    "scripts/p2/e3_local_4906982_fused_surface_normal_v1/extract_native_normal.cpp",
    "scripts/p2/e3_local_4906982_fused_surface_normal_v1/prepare_targets.py",
    "scripts/p2/e3_local_4906982_fused_surface_normal_v1/run.py",
    "scripts/p2/e3_local_4906982_fused_surface_normal_v1/evaluate_lod2.py",
    "scripts/p2/e3_local_4906982_fused_surface_normal_v1/summarize.py",
    "scripts/p2/e3_local_4906982_fused_surface_normal_v1/build_viewer.py",
    "scripts/p2/e3_local_4906982_fused_surface_normal_v1/finalize.py",
    "src/stage2/dataloader.py",
    "src/stage2/loss/data_fitting.py",
    "src/stage2/loss/multiview.py",
    "src/stage2/train.py",
)
REQUIRED = (
    "NOTES.md", "experiment_contract.json", "provenance.json", "config_diff.txt",
    "input_hashes.json", "fused_surface_normal_target_definition.json",
    "raw_native_fused_metrics.csv", "checkpoint_metrics.csv", "metrics.json",
    "comparison.md", "comparison_metrics.csv", "comparison_metrics.json",
    "mvs_surface_audit.json", "lod2_fused_evaluation.json", "viewer_slot.json",
    "representative_images/roofer_3arm_20k_top.png",
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def atomic_json(path: Path, body: dict) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(body, indent=2, sort_keys=True) + "\n")
    tmp.replace(path)


def git(*args: str) -> str:
    return subprocess.check_output(
        ["git", "-c", "safe.directory=/workspace/JointBuildGS", *args],
        cwd=REPO, text=True,
    ).strip()


def main() -> None:
    missing = [name for name in REQUIRED if not (ROOT / name).is_file()]
    if missing:
        raise RuntimeError(f"missing required outputs: {missing}")
    target = json.loads((ROOT / "fused_surface_normal_target_definition.json").read_text())
    gate = json.loads((ROOT / "control/common_state_gate_7000.json").read_text())
    dose = json.loads((ROOT / "control/dose_safety_gate_12000.json").read_text())
    metrics = json.loads((ROOT / "comparison_metrics.json").read_text())
    viewer = json.loads((ROOT / "viewer_slot.json").read_text())
    target_passed = target.get("status") == "GATE_PASSED" and all(target.get("gate_checks", {}).values())
    if not target_passed or not gate["passed"] or not dose["passed"]:
        raise RuntimeError("one or more training gates failed")
    if metrics.get("scientific_verdict") is not None or viewer.get("scientific_verdict") is not None:
        raise RuntimeError("scientific_verdict must remain null")

    notes = f"""# {TASK_ID}

Status: `COMPLETE_MEASURED_VIEWER_PUBLISHED`.

- New training experiments completed: 1 (`FUSED_VIS_CONF_FUSED_NORMAL/R1`, 7k branch to 20k).
- Read-only comparators: `FUSED_VIS_CONF/R1` and `FUSED_VIS_CONF_MVS_NORMAL/R1`.
- Exact 7k full-state equality, smoke, 12k dose, Stage-3, and viewer add-only gates passed.
- The primary comparison changes only the normal target values on the exact frozen 15,879,006-pixel raw-normal mask; fused depth and every other training control are unchanged.
- LoD2 Z, RoofSurface, roof type, and semantic labels were evaluation-only.
- No shared source file or protected viewer root slot was modified by runtime publication.

scientific_verdict: null
"""
    (ROOT / "NOTES.md").write_text(notes)
    issues = f"""# Issues

- Frozen upstream `FUSED_VIS_CONF` support is absent in one of 47 train views; the inherited 46/47 support contract is unchanged.
- `native filtered` is view-local OpenMVS DMAP evidence, while the new training target is the normal of the fused mesh first-hit triangle. They are compared but not mixed.
- The first target-preparation draft used the full fused-depth support (20,159,357 pixels). It was rejected before training because it would change normal-mask coverage; the executed arm uses the exact prior raw-normal valid mask (15,879,006 pixels).
- The first LoD2 evaluation invocation hit a Python dynamic-import/dataclass registration error. The evaluator was corrected and rerun; no checkpoint, fusion, or reference input was changed.
- The first final-packaging invocation expected a generic `passed` field, while the target audit uses `status=GATE_PASSED` plus named gate checks. The validator was corrected to enforce the actual schema and rerun.
- The first syntax-validation invocation attempted to place Python bytecode in the read-only repository mount. Validation was rerun with bytecode directed to container-local `/tmp`.
- The first JSON sweep treated `roofer.log.json` as a single JSON document; it is an inherited stream of one JSON object per line with a trailing comma. The final sweep strips that delimiter and validates each record.
- The controlled 12k stop appears as Docker return code 137 because the container was deliberately stopped immediately after the valid 12k checkpoint; the dose gate passed and the same full state resumed to 20k.
- LoD2 Z, RoofSurface, roof type, and semantic labels were not used to create targets, masks, or views.

scientific_verdict: null
"""
    (ROOT / "issues.md").write_text(issues)

    provenance_path = ROOT / "provenance.json"
    provenance = json.loads(provenance_path.read_text())
    provenance["ended_utc"] = datetime.now(timezone.utc).isoformat()
    provenance["git_at_completion"] = {
        "commit": git("rev-parse", "HEAD"),
        "branch": git("branch", "--show-current"),
        "dirty": bool(git("status", "--porcelain")),
        "status_porcelain": git("status", "--porcelain").splitlines(),
    }
    provenance["source_config_sha256"] = {
        name: sha256(REPO / name) for name in SOURCES
    }
    provenance["output_sha256"] = {
        name: sha256(ROOT / name) for name in REQUIRED if name != "provenance.json"
    }
    provenance["execution_summary"] = {
        "training_experiments_started": 1,
        "training_experiments_completed": 1,
        "gate_stop": None,
        "controlled_checkpoint_stop_return_code": 137,
        "stage3_cases_completed": 8,
        "viewer_cases_published": 12,
    }
    provenance["scientific_verdict"] = None
    atomic_json(provenance_path, provenance)

    artifact_index = {
        "schema": "jointbuildgs.p2.e3_local_4906982_fused_surface_normal_v1.artifact_index.v1",
        "task_id": TASK_ID,
        "required_outputs": {
            name: {"sha256": sha256(ROOT / name), "bytes": (ROOT / name).stat().st_size}
            for name in REQUIRED
        },
        "scientific_verdict": None,
    }
    atomic_json(ROOT / "artifact_index.json", artifact_index)
    print(json.dumps({
        "status": "COMPLETE_MEASURED_VIEWER_PUBLISHED",
        "required_outputs": len(REQUIRED),
        "source_files_hashed": len(SOURCES),
        "scientific_verdict": None,
    }, indent=2))


if __name__ == "__main__":
    main()
