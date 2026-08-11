#!/usr/bin/env python3
"""Finalize the common-support diagnostic and preserve null scientific verdict."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess


REPO = Path("/workspace/JointBuildGS")
AR = Path("/artifacts/JointBuildGS")
TASK_ID = "P2-E3-LOCAL-4906982-FUSED-DN-COMMON-SUPPORT-v1"
ROOT = AR / "phase-payloads/p2/e3_local_4906982_fused_dn_common_support_v1" / TASK_ID
SOURCES = (
    "configs/p2/e3_local_4906982_fused_dn_common_support_v1/common.yaml",
    "configs/p2/e3_local_4906982_fused_dn_common_support_v1/fused_depth_normal_common_support.yaml",
    "configs/p2/e3_local_4906982_fused_dn_common_support_v1/viewer.yaml",
    "scripts/p2/e3_local_4906982_fused_dn_common_support_v1/prepare_targets.py",
    "scripts/p2/e3_local_4906982_fused_dn_common_support_v1/run.py",
    "scripts/p2/e3_local_4906982_fused_dn_common_support_v1/evaluate_lod2.py",
    "scripts/p2/e3_local_4906982_fused_dn_common_support_v1/summarize.py",
    "scripts/p2/e3_local_4906982_fused_dn_common_support_v1/build_viewer.py",
    "scripts/p2/e3_local_4906982_fused_dn_common_support_v1/finalize.py",
    "src/stage2/dataloader.py", "src/stage2/loss/data_fitting.py", "src/stage2/loss/multiview.py", "src/stage2/train.py",
)
REQUIRED = (
    "NOTES.md", "experiment_contract.json", "provenance.json", "config_diff.txt", "input_hashes.json",
    "fused_dn_common_support_target_definition.json", "fused_dn_common_support_metrics.csv",
    "checkpoint_metrics.csv", "metrics.json", "comparison.md", "comparison_metrics.csv", "comparison_metrics.json",
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
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(body, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def git(*args: str) -> str:
    return subprocess.check_output(["git", "-c", "safe.directory=/workspace/JointBuildGS", *args], cwd=REPO, text=True).strip()


def main() -> None:
    missing = [name for name in REQUIRED if not (ROOT / name).is_file()]
    if missing:
        raise RuntimeError(f"missing required outputs: {missing}")
    target = json.loads((ROOT / "fused_dn_common_support_target_definition.json").read_text())
    equality = json.loads((ROOT / "control/common_state_gate_7000.json").read_text())
    dose = json.loads((ROOT / "control/dose_safety_gate_12000.json").read_text())
    if target.get("status") != "GATE_PASSED" or not all(target.get("gate_checks", {}).values()) or not equality["passed"] or not dose["passed"]:
        raise RuntimeError("one or more gates failed")
    if target["target_valid_pixels"] != target["depth_support_pixels"]:
        raise RuntimeError("depth/normal common-support equality failed")
    (ROOT / "NOTES.md").write_text(f"""# {TASK_ID}

Status: `COMPLETE_MEASURED_VIEWER_PUBLISHED`.

- One new arm completed from exact-equal 7k state through 20k.
- Fused depth and fused surface normal use the exact same frozen FUSED_VIS_CONF support ({target['target_valid_pixels']:,} pixels).
- The primary comparison changes only normal mask coverage relative to the read-only fixed raw-valid-mask fused-normal arm.
- LoD2 Z, RoofSurface, roof type, and semantic labels were evaluation-only.

scientific_verdict: null
""")
    (ROOT / "issues.md").write_text("""# Issues

- The first target-driver invocation created the reuse receipt before the new `logs/` directory and stopped before target generation. Directory creation order was corrected; no input or prior artifact was modified.
- The second target-driver invocation caught a redundant transformed-config path assertion and a missing initial provenance ledger before target generation. Both driver contracts were corrected; no target or training artifact had been produced.
- The third pre-target reuse gate resolved the 55 native normal maps but still looked for their extractor binary in the new namespace. Its hash binding was corrected to the audited source binary before raycasting or training.
- Frozen FUSED_VIS_CONF support remains absent in one of 47 train views; RGB/MVC remain active there while depth/normal priors are absent.
- The support mask is LoD2-blind native-filtered/OpenMVS-fused agreement, not an independent ground truth mask.
- The controlled 12k stop may appear as Docker return code 137 after a valid checkpoint; the dose gate and full-state resume determine validity.

scientific_verdict: null
""")
    contract_path = ROOT / "experiment_contract.json"; contract = json.loads(contract_path.read_text())
    contract.update({"status": "COMPLETE_MEASURED_VIEWER_PUBLISHED", "viewer_slot": "e3-fused-dn-common-support-v1", "scientific_verdict": None})
    atomic_json(contract_path, contract)
    provenance_path = ROOT / "provenance.json"; provenance = json.loads(provenance_path.read_text())
    provenance.update({
        "ended_utc": datetime.now(timezone.utc).isoformat(),
        "git_at_completion": {"commit": git("rev-parse", "HEAD"), "branch": git("branch", "--show-current"), "dirty": bool(git("status", "--porcelain")), "status_porcelain": git("status", "--porcelain").splitlines()},
        "source_config_sha256": {name: sha256(REPO / name) for name in SOURCES},
        "output_sha256": {name: sha256(ROOT / name) for name in REQUIRED if name != "provenance.json"},
        "execution_summary": {"training_experiments_started": 1, "training_experiments_completed": 1, "gate_stop": None, "stage3_cases_completed": 8, "viewer_cases_published": 12},
        "scientific_verdict": None,
    })
    atomic_json(provenance_path, provenance)
    atomic_json(ROOT / "artifact_index.json", {
        "schema": "jointbuildgs.p2.e3_local_4906982_fused_dn_common_support_v1.artifact_index.v1", "task_id": TASK_ID,
        "required_outputs": {name: {"sha256": sha256(ROOT / name), "bytes": (ROOT / name).stat().st_size} for name in REQUIRED},
        "scientific_verdict": None,
    })
    print(json.dumps({"status": contract["status"], "normal_mask_pixels": target["target_valid_pixels"], "depth_mask_pixels": target["depth_support_pixels"], "scientific_verdict": None}, indent=2))


if __name__ == "__main__":
    main()
