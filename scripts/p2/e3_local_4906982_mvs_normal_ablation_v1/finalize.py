#!/usr/bin/env python3
"""Seal provenance and output hashes for the measured, add-only task."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess


REPO = Path("/workspace/JointBuildGS")
ROOT = Path("/artifacts/JointBuildGS/phase-payloads/p2/e3_local_4906982_mvs_normal_ablation_v1/P2-E3-LOCAL-4906982-MVS-NORMAL-ABLATION-v1")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""): digest.update(block)
    return digest.hexdigest()


def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=REPO, check=True, text=True, capture_output=True).stdout.strip()


def main() -> None:
    notes = f"""# P2-E3-LOCAL-4906982-MVS-NORMAL-ABLATION-v1

Status: `COMPLETE_MEASURED_VIEWER_PUBLISHED`.

- New training arms executed: 1 (`FUSED_VIS_CONF_MVS_NORMAL/R1`).
- Read-only control: existing `FUSED_VIS_CONF/R1`.
- Common state: exact-equal through completed update 7000; normal activates after the branch.
- Normal target: correctly decoded COLMAP geometric normal, camera-to-world, unsigned, exact FUSED_VIS_CONF support mask.
- Checkpoints: 7k/12k/15k/20k; Stage-3 cases: 8/8; Roofer return success: 8/8.
- Viewer: `http://127.0.0.1:8878/e3-mvs-normal-ablation-v1/index.html`.
- Existing 8878 root files and `mvs-seed-color-v3` state were not changed.
- No commit was created.
- scientific_verdict: null
"""
    (ROOT / "NOTES.md").write_text(notes)
    source_relatives = [
        "configs/p2/e3_local_4906982_mvs_normal_ablation_v1/common.yaml",
        "configs/p2/e3_local_4906982_mvs_normal_ablation_v1/mvs_depth_normal.yaml",
        "configs/p2/e3_local_4906982_mvs_normal_ablation_v1/viewer.yaml",
        "scripts/p2/e3_local_4906982_mvs_normal_ablation_v1/prepare_normal.py",
        "scripts/p2/e3_local_4906982_mvs_normal_ablation_v1/run.py",
        "scripts/p2/e3_local_4906982_mvs_normal_ablation_v1/summarize.py",
        "scripts/p2/e3_local_4906982_mvs_normal_ablation_v1/build_viewer.py",
        "scripts/p2/e3_local_4906982_mvs_normal_ablation_v1/finalize.py",
        "src/stage2/train.py", "src/stage2/dataloader.py", "src/stage2/loss/data_fitting.py", "src/stage2/loss/multiview.py",
    ]
    outputs = [
        "NOTES.md", "issues.md", "experiment_contract.json", "provenance.json", "config_diff.txt", "input_hashes.json",
        "mvs_normal_target_definition.json", "mvs_normal_preflight_metrics.csv", "checkpoint_metrics.csv", "paired_checkpoint_deltas.csv",
        "metrics.json", "mvs_surface_audit.json", "mvs_surface_metrics.csv", "lod2_fused_evaluation.json", "lod2_fused_evaluation.csv",
        "comparison_metrics.json", "comparison_metrics.csv", "comparison.md", "viewer_slot.json",
        "representative_images/roofer_2arm_20k_top.png",
    ]
    for relative in outputs:
        if not (ROOT / relative).is_file(): raise FileNotFoundError(ROOT / relative)
    contract_path = ROOT / "experiment_contract.json"; contract = json.loads(contract_path.read_text())
    contract.update({"status": "COMPLETE_MEASURED_VIEWER_PUBLISHED", "training_experiments_started": 1, "training_experiments_completed": 1,
                     "stage3_cases_completed": 8, "scientific_verdict": None})
    contract_path.write_text(json.dumps(contract, indent=2, sort_keys=True) + "\n")
    provenance_path = ROOT / "provenance.json"; provenance = json.loads(provenance_path.read_text())
    provenance["git_at_completion"] = {"commit": git("rev-parse", "HEAD"), "branch": git("branch", "--show-current"),
        "dirty": bool(git("status", "--porcelain")), "status_porcelain": git("status", "--porcelain").splitlines()}
    provenance["source_config_sha256"] = {relative: sha256(REPO / relative) for relative in source_relatives}
    provenance["output_index_sha256"] = {relative: sha256(ROOT / relative) for relative in outputs if relative != "provenance.json"}
    provenance["manual_container_operations"] = [
        {"label": "prepare_supported_mvs_normal", "image": "jointbuildgs:dev", "return_code": 0},
        {"label": "lod2_fused_evaluation_only", "image": "jointbuildgs:mvc-eval-v1", "return_code": 0},
        {"label": "summarize", "image": "jointbuildgs:mvc-eval-v1", "return_code": 0},
        {"label": "build_add_only_viewer_slot", "image": "jointbuildgs:mvc-eval-v1", "return_code": 0},
    ]
    provenance["known_incidental_failures"] = [
        "initial 47/47 normal support gate conflicted with frozen upstream 46/47 support and was corrected before training",
        "first binding probe collided during task-local gsplat extension compilation; serial retry returned zero",
        "unsigned-normal TensorBoard path omits the signed-only valid-pixel tag; gates use frozen pixel count plus nonzero loss/weight/gradient",
    ]
    provenance["viewer"] = json.loads((ROOT / "viewer_slot.json").read_text())
    provenance["ended_utc"] = datetime.now(timezone.utc).isoformat(); provenance["scientific_verdict"] = None
    provenance_path.write_text(json.dumps(provenance, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"status": contract["status"], "outputs_hashed": len(provenance["output_index_sha256"]), "scientific_verdict": None}, indent=2))


if __name__ == "__main__": main()
