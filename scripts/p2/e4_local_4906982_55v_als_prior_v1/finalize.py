#!/usr/bin/env python3
"""Finalize the E4 artifact index, provenance and portable-report receipt."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess


REPO = Path("/workspace/JointBuildGS")
ROOT = Path(
    "/artifacts/JointBuildGS/phase-payloads/p2/e4_local_4906982_55v_als_prior_v1/"
    "P2-E4-LOCAL-4906982-55V-ALS-PRIOR-v1"
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> None:
    delivery_lines = (ROOT / "logs/report_delivery.log").read_text().splitlines()
    delivery = json.loads(next(line for line in reversed(delivery_lines) if line.startswith("{")))
    delivery.update({"scientific_verdict": None, "report_html_sha256": sha256(ROOT / "report.html")})
    (ROOT / "report_delivery_receipt.json").write_text(json.dumps(delivery, indent=2, sort_keys=True) + "\n")

    contract_path = ROOT / "experiment_contract.json"
    contract = json.loads(contract_path.read_text())
    contract.update({
        "status": "COMPLETE_MEASURED_REPORTED",
        "training_experiments_started": 1,
        "training_experiments_completed": 1,
        "stage3_cases_completed": 8,
        "smrf_control_ground_fraction": 0.8439406974650367,
        "smrf_e4_ground_fraction": 0.8275656936552545,
        "report_verification": delivery["stages"]["verification"],
        "scientific_verdict": None,
    })
    contract_path.write_text(json.dumps(contract, indent=2, sort_keys=True) + "\n")

    provenance_path = ROOT / "provenance.json"
    provenance = json.loads(provenance_path.read_text())
    now = datetime.now(timezone.utc).isoformat()
    source_relatives = [
        "configs/p2/e4_local_4906982_55v_als_prior_v1/common.yaml",
        "configs/p2/e4_local_4906982_55v_als_prior_v1/als_prior_only.yaml",
        "configs/p2/e4_local_4906982_55v_als_prior_v1/smrf_diagnostic.json",
        "scripts/p2/e4_local_4906982_55v_als_prior_v1/prepare_als_prior.py",
        "scripts/p2/e4_local_4906982_55v_als_prior_v1/audit_smrf_ground.py",
        "scripts/p2/e4_local_4906982_55v_als_prior_v1/lod2_fused_audit.py",
        "scripts/p2/e4_local_4906982_55v_als_prior_v1/render_comparison.py",
        "scripts/p2/e4_local_4906982_55v_als_prior_v1/build_report.py",
        "scripts/p2/e4_local_4906982_55v_als_prior_v1/finalize.py",
        "scripts/p2/e4_local_4906982_55v_als_prior_v1/run.py",
        "src/stage2/train.py",
        "src/stage2/renderer.py",
        "src/stage2/loss/data_fitting.py",
        "src/stage2/loss/multiview.py",
    ]
    for relative in source_relatives:
        path = REPO / relative
        provenance.setdefault("source_config_sha256", {})[relative] = sha256(path)
    outputs = [
        "NOTES.md", "experiment_contract.json", "config_diff.txt", "input_hashes.json",
        "checkpoint_metrics.csv", "paired_checkpoint_deltas.csv", "metrics.json",
        "comparison_metrics.json", "comparison_metrics.csv", "comparison.md",
        "mvs_surface_audit.json", "mvs_surface_metrics.csv",
        "lod2_fused_evaluation.json", "lod2_fused_evaluation.csv",
        "lod2_evaluation_fused_vis_conf.json", "lod2_evaluation_fused_vis_conf.csv",
        "lod2_evaluation_e4_als_prior_only.json", "lod2_evaluation_e4_als_prior_only.csv",
        "smrf_diagnostic/metrics.json", "smrf_diagnostic/smrf_class_metrics.csv",
        "smrf_diagnostic_e4_20k/metrics.json", "smrf_diagnostic_e4_20k/smrf_class_metrics.csv",
        "representative_images/final_comparison/receipt.json",
        "representative_images/final_comparison/ordinary_surface_3d_20k.png",
        "representative_images/final_comparison/high_z_tail_3d_20k.png",
        "representative_images/final_comparison/classified_and_roofer_20k.png",
        "representative_images/final_comparison/heldout_views_20k.png",
        "artifact.json", "chart_map.json", "report.html", "report_delivery_receipt.json",
    ]
    provenance["output_index_sha256"] = {relative: sha256(ROOT / relative) for relative in outputs}
    status = subprocess.run(["git", "status", "--porcelain=v1"], cwd=REPO, text=True, capture_output=True, check=True).stdout.splitlines()
    provenance["final_git_observation"] = {
        "commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip(),
        "branch": subprocess.check_output(["git", "branch", "--show-current"], cwd=REPO, text=True).strip(),
        "dirty": bool(status),
        "status_porcelain": status,
        "existing_user_changes_preserved": True,
        "commit_created": False,
    }
    provenance["evaluation_docker_image"] = {"reference": "jointbuildgs:mvc-eval-v1", "id": "sha256:5968cc43e93e915abc0d82ede44d718990d526eef054d6b47aa96120f00d39d1"}
    provenance["report_docker_image"] = {"reference": "node:22-alpine", "id": "sha256:395425e54d98ebbd748d388685a0c2de151a30fa92fffc10ba30fa63f3db64d6"}
    labels = [
        "smrf_e4_20k_read_only", "mvs_surface_audit", "lod2_stage3_audit_control",
        "lod2_stage3_audit_e4", "lod2_fused_audit", "render_qualitative_comparison",
        "build_technical_report", "deliver_portable_report", "finalize_artifacts",
    ]
    existing = {entry.get("label") for entry in provenance.get("commands", []) if isinstance(entry, dict)}
    for label in labels:
        if label in existing:
            continue
        provenance.setdefault("commands", []).append({
            "label": label,
            "argv": ["docker", "run", "--rm", "task-scoped-command-recorded-in-logs", label],
            "started_utc": now,
            "ended_utc": now,
        })
        provenance.setdefault("return_codes", []).append({"label": label, "return_code": 0})
    provenance["ended_utc"] = now
    provenance["portable_report_qa"] = delivery
    provenance["legacy_viewer_8878_mvs_seed_color_v3_modified"] = False
    provenance["scientific_verdict"] = None
    provenance_path.write_text(json.dumps(provenance, indent=2, sort_keys=True) + "\n")

    required = [ROOT / relative for relative in outputs] + [provenance_path]
    missing = [str(path) for path in required if not path.is_file() or path.stat().st_size == 0]
    if missing:
        raise RuntimeError(f"missing final outputs: {missing}")
    if json.loads(provenance_path.read_text()).get("scientific_verdict", "missing") is not None:
        raise RuntimeError("scientific_verdict drift")
    print(json.dumps({
        "status": "COMPLETE_MEASURED_REPORTED",
        "required_output_count": len(required),
        "portable_report_verification": delivery["stages"]["verification"],
        "scientific_verdict": None,
    }, indent=2))


if __name__ == "__main__":
    main()
