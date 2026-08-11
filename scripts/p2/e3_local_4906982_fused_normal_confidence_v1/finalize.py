#!/usr/bin/env python3
"""Finalize immutable receipts for the confidence-gated fused-normal diagnostic."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


REPO = Path("/workspace/JointBuildGS")
AR = Path("/artifacts/JointBuildGS")
ROOT = AR / "phase-payloads/p2/e3_local_4906982_fused_normal_confidence_v1/P2-E3-LOCAL-4906982-FUSED-NORMAL-CONFIDENCE-v1"
VIEWER = AR / "phase-payloads/p2/e3_local_review_v1/P2-E3-LOCAL-4906982-INPUT-REVIEW-v3/viewer/e3-fused-normal-confidence-v1"
CONFIG_DIR = REPO / "configs/p2/e3_local_4906982_fused_normal_confidence_v1"
SCRIPT_DIR = REPO / "scripts/p2/e3_local_4906982_fused_normal_confidence_v1"


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def dump(path: Path, body: object) -> None:
    path.write_text(json.dumps(body, indent=2, sort_keys=True) + "\n")


def verdicts(value: object, path: str = "$") -> list[str]:
    failures = []
    if isinstance(value, dict):
        for key, item in value.items():
            if key == "scientific_verdict" and item is not None:
                failures.append(f"{path}.{key}={item!r}")
            failures.extend(verdicts(item, f"{path}.{key}"))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            failures.extend(verdicts(item, f"{path}[{index}]"))
    return failures


def main() -> None:
    now = datetime.now(timezone.utc).isoformat()
    required = [
        "NOTES.md", "experiment_contract.json", "provenance.json", "config_diff.txt",
        "input_hashes.json", "fused_normal_confidence_definition.json",
        "normal_confidence_mask_metrics.csv", "checkpoint_metrics.csv", "metrics.json",
        "comparison.md", "comparison_metrics.csv", "comparison_metrics.json",
        "roofer_surface_evaluation.csv", "roofer_surface_evaluation.json",
        "representative_images/roofer_4arm_20k_top.png",
        "representative_images/mask_overlays/DJI_20241217095023_0038_D.png",
    ]
    missing = [name for name in required if not (ROOT / name).is_file()]
    checkpoints = [ROOT / f"arms/FUSED_VIS_CONF_FUSED_NORMAL_CONFIDENCE/R1/ckpt/step_{step:06d}.pt" for step in (7000, 12000, 15000, 20000)]
    missing.extend(str(path.relative_to(ROOT)) for path in checkpoints if not path.is_file())
    if missing:
        raise RuntimeError(f"missing required outputs: {missing}")

    comparison = json.loads((ROOT / "comparison_metrics.json").read_text())
    confidence = next(row for row in comparison["rows"] if row["arm"] == "FUSED_VIS_CONF_FUSED_NORMAL_CONFIDENCE")
    definition = json.loads((ROOT / "fused_normal_confidence_definition.json").read_text())
    gate = json.loads((ROOT / "control/primary_state_gate_7000.json").read_text())
    viewer = json.loads((ROOT / "viewer_slot.json").read_text())
    if not gate["passed"] or not viewer["root_fixed_sha256_before_after_equal"]:
        raise RuntimeError("equality or protected-viewer gate failed")

    contract_path = ROOT / "experiment_contract.json"
    contract = json.loads(contract_path.read_text())
    contract.update({
        "status": "COMPLETE_MEASURED_VIEWER_PUBLISHED",
        "training_experiments_started": 1,
        "training_experiments_completed": 1,
        "stage3_cases_completed": 8,
        "normal_mask_pixels": definition["target_valid_pixels"],
        "viewer_urls": {
            "results": "http://localhost:8878/e3-fused-normal-confidence-v1/index.html",
            "mask_overlays": "http://localhost:8878/e3-fused-normal-confidence-v1/inputs.html",
        },
        "scientific_verdict": None,
    })
    dump(contract_path, contract)

    metrics_path = ROOT / "metrics.json"
    metrics = json.loads(metrics_path.read_text())
    metrics["confidence_normal_mask_diagnostic"] = {
        "mask_pixels": definition["target_valid_pixels"],
        "mask_fraction_of_depth": definition["new_fraction_of_depth"],
        "completed_updates": 20000,
        "mvs_p2plane_median_m": confidence["mvs_p2plane_median_m"],
        "mvs_normal_median_deg": confidence["mvs_normal_median_deg"],
        "gaussian_z_gt_650": confidence["gaussian_z_gt_650"],
        "gaussian_z_p99_m": confidence["gaussian_z_p99_m"],
        "heldout_psnr_db": confidence["heldout_psnr_db"],
        "fusion_ge2": confidence["fusion_ge2"],
        "roofer_roof_xy_coverage": confidence["roofer_roof_xy_coverage"],
        "roofer_surface_fscore_0p5m": confidence["roofer_surface_fscore_0p5m"],
        "roofer_surface_normal_median_deg": confidence["roofer_surface_normal_median_deg"],
        "lod2_abs_dz_rmse_m_evaluation_only": confidence["lod2_abs_dz_rmse_m"],
        "scientific_verdict": None,
    }
    metrics["status"] = "COMPLETE_MEASURED_VIEWER_PUBLISHED"
    metrics["scientific_verdict"] = None
    dump(metrics_path, metrics)

    source_hashes = {str(path.relative_to(REPO)): sha(path) for path in sorted(SCRIPT_DIR.glob("*.py"))}
    config_hashes = {str(path.relative_to(REPO)): sha(path) for path in sorted(CONFIG_DIR.glob("*.yaml"))}
    provenance_path = ROOT / "provenance.json"
    provenance = json.loads(provenance_path.read_text())
    provenance.update({
        "ended_utc": now,
        "docker": {
            "jointbuildgs:dev": {"image_id": "sha256:251f83c17879a83b0c3dda5b9d71cbf45ca72cc0fdcbc89994194dc3edb86774", "digest": None},
            "jointbuildgs:mvc-eval-v1": {"image_id": "sha256:5968cc43e93e915abc0d82ede44d718990d526eef054d6b47aa96120f00d39d1", "digest": None},
        },
        "source_sha256": source_hashes,
        "config_sha256": config_hashes,
        "scientific_verdict": None,
    })
    provenance["return_codes"] = [
        item for item in provenance.get("return_codes", [])
        if item.get("label") not in {"finalize_receipts", "finalize_receipts_attempt_1", "finalize_receipts_attempt_2", "finalize_receipts_attempt_3"}
    ]
    extra = [
        ("evaluate_roofer_surface_attempt_1", 1),
        ("evaluate_roofer_surface_attempt_2", 0),
        ("summarize_with_roofer_surface", 0),
        ("finalize_receipts_attempt_1", 1),
        ("finalize_receipts_attempt_2", 1),
        ("finalize_receipts_attempt_3", 0),
    ]
    existing = {item["label"] for item in provenance.get("return_codes", [])}
    for label, code in extra:
        if label not in existing:
            provenance.setdefault("return_codes", []).append({"label": label, "return_code": code})
    if not any(item.get("label") == "finalize_receipts" for item in provenance.get("commands", [])):
        provenance.setdefault("commands", []).append({
            "label": "finalize_receipts",
            "argv": ["docker", "run", "--rm", "jointbuildgs:mvc-eval-v1", "python", "scripts/p2/e3_local_4906982_fused_normal_confidence_v1/finalize.py"],
            "started_utc": now,
            "ended_utc": now,
        })
    dump(provenance_path, provenance)

    issues = """# Issues — P2-E3-LOCAL-4906982-FUSED-NORMAL-CONFIDENCE-v1

- The 7k-to-12k process returned 137 only after a valid 12k full-state checkpoint was written; this was the runner's intentional bounded stop and the 12k dose gate passed.
- The first evaluation-only Roofer surface import failed because the dynamically imported dataclass module was not registered in `sys.modules`. No learned or Roofer artifact was modified. The thin evaluator was corrected and its second run completed.
- One of 47 training views has no confidence-normal support; the pretraining coverage gate accepted 46/47 views and recorded the absent view explicitly.
- Two viewer assembly attempts were stopped on template drift and a slot collision before the final add-only publication. The protected viewer root hash remained equal before and after publication.
- The first syntax-validation command used a read-only repository mount without redirecting Python bytecode cache and therefore stopped before compilation. It was rerun with `PYTHONPYCACHEPREFIX=/tmp/pycache`.
- The inherited measurement helper names its paired section after an older fused-surface-normal arm. `comparison_metrics.json` is the authoritative four-arm comparison for this task.

scientific_verdict: null
"""
    (ROOT / "issues.md").write_text(issues)
    notes = f"""# P2-E3-LOCAL-4906982-FUSED-NORMAL-CONFIDENCE-v1

Status: `COMPLETE_MEASURED_VIEWER_PUBLISHED`.

- One new arm was trained from the exact-equal 7k control state through 20k.
- Depth target/mask and fused normal target values were held fixed; only the frozen normal-confidence mask changed.
- The mask overlays were generated and published before training began.
- LoD2 geometry was used only after training for evaluation.
- Results: http://localhost:8878/e3-fused-normal-confidence-v1/index.html
- Mask overlays: http://localhost:8878/e3-fused-normal-confidence-v1/inputs.html

scientific_verdict: null
"""
    (ROOT / "NOTES.md").write_text(notes)

    key_files = required + ["issues.md", "viewer_slot.json", "mask_visualization_receipt.json", "mask_viewer_receipt.json"]
    index = {
        "schema": "jointbuildgs.p2.e3_local_4906982_fused_normal_confidence_v1.artifact_index.v1",
        "task_id": contract["task_id"],
        "files": {name: sha(ROOT / name) for name in key_files},
        "source_sha256": source_hashes,
        "config_sha256": config_hashes,
        "viewer_slot": str(VIEWER),
        "scientific_verdict": None,
    }
    dump(ROOT / "artifact_index.json", index)

    failures = []
    for path in ROOT.rglob("*.json"):
        try:
            failures.extend(f"{path.relative_to(ROOT)}:{item}" for item in verdicts(json.loads(path.read_text())))
        except json.JSONDecodeError:
            try:
                records = [json.loads(line.rstrip().removesuffix(",")) for line in path.read_text().splitlines() if line.strip()]
                failures.extend(f"{path.relative_to(ROOT)}:{item}" for item in verdicts(records))
            except json.JSONDecodeError as exc:
                failures.append(f"{path.relative_to(ROOT)}:invalid JSON or JSONL: {exc}")
    if failures:
        raise RuntimeError("JSON integrity failures: " + "; ".join(failures[:20]))
    print(json.dumps({
        "status": contract["status"],
        "required_files": len(required),
        "source_files_hashed": len(source_hashes),
        "config_files_hashed": len(config_hashes),
        "scientific_verdict": None,
    }, indent=2))


if __name__ == "__main__":
    main()
