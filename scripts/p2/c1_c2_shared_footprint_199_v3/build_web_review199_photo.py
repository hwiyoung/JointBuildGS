#!/usr/bin/env python3
"""Attach frozen 199-building photo evidence to the existing 3D O/X web review."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
from typing import Any, Mapping

from scripts.p2.qualitative_199_cloudcompare_scene_v1.build_scene import (
    canonical_json_bytes,
    file_record,
    sha256_file,
    write_new,
)


REPO = Path(__file__).resolve().parents[3]
DEFAULT_CONFIG = REPO / "configs/p2/c1_c2_shared_footprint_199_v3/web_review199_photo_v1.json"


def verify(path: Path, record: Mapping[str, Any], label: str) -> dict[str, Any]:
    size, digest = sha256_file(path)
    if size != int(record["bytes"]) or digest != record["sha256"]:
        raise RuntimeError(f"{label} identity drift: {path}")
    return {"path": str(record.get("path", path.name)), "bytes": size, "sha256": digest}


def load_config(path: Path) -> dict[str, Any]:
    config = json.loads(path.read_text(encoding="utf-8"))
    if config.get("schema") != "jointbuildgs.p2.c1_c2_original_global_v3.web_review199_photo.v1":
        raise RuntimeError("unexpected integrated web review config schema")
    if config.get("status") != "USER_APPROVED_FOR_EXECUTION" or config.get("scientific_verdict", "missing") is not None:
        raise RuntimeError("integrated web review is not approved or has a verdict")
    if int(config["features"]["building_count"]) != 199 or int(config["features"]["photos_per_building"]) != 4:
        raise RuntimeError("integrated 199 x 4 photo contract drifted")
    if config["features"]["local_storage_key"] != "jointbuildgs-c1-c2-roofer-ox-v1":
        raise RuntimeError("O/X localStorage continuity key drifted")
    if any(int(config["execution"].get(key, -1)) != 0 for key in (
        "roofer_invocations", "reconstruction_invocations", "gs_training_invocations", "metric_recomputations"
    )):
        raise RuntimeError("integration must not invoke reconstruction")
    return config


def copy_verified(source_root: Path, output_root: Path, record: Mapping[str, Any], label: str) -> dict[str, Any]:
    source = source_root / record["path"]
    verified = verify(source, record, label)
    destination = output_root / record["path"]
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination)
    return verified


def run(config_path: Path, repo_root: Path, artifact_root: Path, output_root: Path, source_commit: str, image_id: str) -> dict[str, Any]:
    config = load_config(config_path)
    if output_root.exists() or output_root.with_name(output_root.name + ".partial").exists():
        raise RuntimeError(f"fresh add-once output namespace required: {output_root}")
    partial = output_root.with_name(output_root.name + ".partial")
    partial.mkdir(parents=True)

    source_spec = config["source_web_review"]
    source_root = artifact_root / source_spec["relative_root"]
    source_manifest_path = source_root / source_spec["manifest_path"]
    verify(source_manifest_path, source_spec, "source web review manifest")
    source_manifest = json.loads(source_manifest_path.read_text(encoding="utf-8"))
    if source_manifest["task_id"] != source_spec["required_task_id"] or source_manifest["status"] != source_spec["required_status"]:
        raise RuntimeError("source web review task/status drifted")
    source_viewer_record = source_manifest["viewer_manifest"]
    verify(source_root / source_viewer_record["path"], source_viewer_record, "source viewer manifest")
    source_viewer = json.loads((source_root / source_viewer_record["path"]).read_text(encoding="utf-8"))
    if len(source_viewer["buildings"]) != 199:
        raise RuntimeError("source viewer does not contain 199 buildings")

    copied_assets = [copy_verified(source_root, partial, record, "source spatial asset") for record in source_manifest["asset_records"]]
    keep_application = {"overview.html", "overview.js", "three.module.min.js"}
    copied_application = [
        copy_verified(source_root, partial, record, "source unchanged application")
        for record in source_manifest["application_records"] if record["path"] in keep_application
    ]

    photo_spec = config["photo_evidence"]
    photo_root = artifact_root / photo_spec["relative_root"]
    photo_manifest_path = photo_root / photo_spec["manifest_path"]
    verify(photo_manifest_path, photo_spec, "photo evidence artifact manifest")
    photo_artifact_manifest = json.loads(photo_manifest_path.read_text(encoding="utf-8"))
    if photo_artifact_manifest["task_id"] != photo_spec["required_task_id"]:
        raise RuntimeError("photo evidence task identity drifted")
    evidence_record = next(row for row in photo_artifact_manifest["records"] if row["path"] == "photo_evidence_manifest_v1.json")
    verify(photo_root / evidence_record["path"], evidence_record, "photo evidence manifest")
    evidence = json.loads((photo_root / evidence_record["path"]).read_text(encoding="utf-8"))
    if len(evidence["buildings"]) != 199:
        raise RuntimeError("photo evidence does not contain 199 buildings")
    photo_by_id = {
        row["stable_id"]: {
            "population_index": row["population_index"],
            "stable_id": row["stable_id"],
            "panels": [
                {
                    **{key: value for key, value in panel.items() if key != "overlays"},
                    "overlays": {"reference": panel.get("overlays", {}).get("reference", {"status": "MISSING", "polylines": []})},
                }
                for panel in row["panels"]
            ],
            "scientific_verdict": None,
        }
        for row in evidence["buildings"]
    }
    viewer_ids = {row["stable_id"] for row in source_viewer["buildings"]}
    if set(photo_by_id) != viewer_ids:
        raise RuntimeError("photo evidence and viewer building membership differ")

    photo_records = []
    for row in evidence["buildings"]:
        for panel in row["panels"]:
            if not panel.get("photo"):
                continue
            record = panel["photo"]
            source = photo_root / record["path"]
            verify(source, record, "photo JPEG")
            destination = partial / record["path"]
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, destination)
            photo_records.append({"path": record["path"], "bytes": int(record["bytes"]), "sha256": record["sha256"]})

    viewer = dict(source_viewer)
    viewer["schema"] = "jointbuildgs.p2.c1_c2_original_global_v3.web_viewer_manifest.photo.v1"
    viewer["task_id"] = config["task_id"]
    viewer["buildings"] = [{**row, "photo_evidence": photo_by_id[row["stable_id"]]} for row in source_viewer["buildings"]]
    viewer["photo_evidence"] = {
        "task_id": evidence["task_id"],
        "display_mode": "FROZEN_INDEPENDENT_LOD2_ROOFLINE_PROJECTION_ONLY",
        "keypoints_rendered": False, "lazy_load_selected_building_only": True,
    }
    viewer["scientific_verdict"] = None
    write_new(partial / "viewer_manifest.json", canonical_json_bytes(viewer))

    application_records = list(copied_application)
    for name, app_spec in config["application"].items():
        source = repo_root / app_spec["git_path"]
        verify(source, app_spec, f"application {name}")
        destination = partial / app_spec["output_path"]
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
        application_records.append(file_record(destination, partial))
    viewer_record = file_record(partial / "viewer_manifest.json", partial)
    readme = (
        "# JointBuildGS 199-building C1/C2 Roofer web review with photo evidence\n\n"
        "Open `index.html` through the supplied HTTP server. The 3D O/X review, localStorage key, "
        "199-building overview and point-size default are retained. `사진 근거` lazily loads TOP + "
        "RANDOM 1-3 with the frozen independent-LoD2 roofline projection. No additional "
        "LiDAR/MVS photo projection or review field is introduced. Scientific verdict remains null.\n"
    ).encode("utf-8")
    write_new(partial / "README.md", readme)
    readme_record = file_record(partial / "README.md", partial)
    config_size, config_sha = sha256_file(config_path)
    script_size, script_sha = sha256_file(Path(__file__))
    receipt = {
        "schema": "jointbuildgs.p2.c1_c2_original_global_v3.web_review199_photo.receipt.v1",
        "task_id": config["task_id"], "state": "complete", "generated_utc": datetime.now(timezone.utc).isoformat(),
        "repository_base_commit": source_commit, "runtime_image_id": image_id,
        "source_web_review_task_id": source_manifest["task_id"], "photo_evidence_task_id": evidence["task_id"],
        "building_count": len(viewer["buildings"]), "photo_count": len(photo_records),
        "config": {"bytes": config_size, "sha256": config_sha}, "script": {"bytes": script_size, "sha256": script_sha},
        "scientific_verdict": None,
    }
    write_new(partial / "run_receipt_v1.json", canonical_json_bytes(receipt))
    receipt_record = file_record(partial / "run_receipt_v1.json", partial)
    manifest = {
        "schema": "jointbuildgs.p2.c1_c2_original_global_v3.web_review199_photo.artifact_manifest.v1",
        "task_id": config["task_id"], "status": "READY_FOR_HUMAN_WEB_REVIEW",
        "source_web_review_manifest": {"path": source_spec["manifest_path"], "bytes": source_spec["bytes"], "sha256": source_spec["sha256"]},
        "photo_evidence_artifact_manifest": {"path": photo_spec["manifest_path"], "bytes": photo_spec["bytes"], "sha256": photo_spec["sha256"]},
        "application_records": sorted(application_records, key=lambda row: row["path"]),
        "viewer_manifest": viewer_record, "readme": readme_record, "receipt": receipt_record,
        "asset_records": copied_assets, "photo_records": sorted(photo_records, key=lambda row: row["path"]),
        "asset_record_count": len(copied_assets), "photo_record_count": len(photo_records),
        "execution": config["execution"], "scientific_verdict": None,
    }
    write_new(partial / "manifest_web_review199_photo_v1.json", canonical_json_bytes(manifest))
    os.rename(partial, output_root)
    return receipt


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--repo-root", type=Path, default=REPO)
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--image-id", required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.config, args.repo_root, args.artifact_root, args.output_root, args.source_commit, args.image_id), ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
