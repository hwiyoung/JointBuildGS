#!/usr/bin/env python3
"""Attach exact frozen-v6-v4 rendered row PNG bytes to the 199-building 3D review."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
from typing import Any, Mapping

from scripts.p2.qualitative_199_cloudcompare_scene_v1.build_scene import canonical_json_bytes, file_record, sha256_file, write_new


REPO = Path(__file__).resolve().parents[3]
DEFAULT_CONFIG = REPO / "configs/p2/c1_c2_shared_footprint_199_v3/web_review199_exact_rows_v1.json"


def verify(path: Path, record: Mapping[str, Any], label: str) -> dict[str, Any]:
    size, digest = sha256_file(path)
    if size != int(record["bytes"]) or digest != record["sha256"]:
        raise RuntimeError(f"{label} identity drift: {path}")
    return {"path": str(record.get("path", path.name)), "bytes": size, "sha256": digest}


def load_config(path: Path) -> dict[str, Any]:
    config = json.loads(path.read_text(encoding="utf-8"))
    if config.get("schema") != "jointbuildgs.p2.c1_c2_original_global_v3.web_review199_exact_rows.v1":
        raise RuntimeError("unexpected exact-row web review config schema")
    if config.get("status") != "USER_APPROVED_FOR_EXECUTION" or config.get("scientific_verdict", "missing") is not None:
        raise RuntimeError("exact-row web review is not approved or has a verdict")
    if config["features"] != {
        "building_count": 199,
        "row_png_count": 199,
        "display": "ALWAYS_VISIBLE_SINGLE_ROW_BELOW_BUILDING_NAVIGATION",
        "source": "EXACT_FROZEN_PREVIEW10_V4_RENDERED_PNG_BYTES",
        "browser_redraw": False,
        "local_storage_key": "jointbuildgs-c1-c2-roofer-ox-v1",
    }:
        raise RuntimeError("exact-row display contract drifted")
    if any(int(config["execution"].get(key, -1)) != 0 for key in (
        "roofer_invocations", "reconstruction_invocations", "gs_training_invocations", "metric_recomputations"
    )):
        raise RuntimeError("web assembly must not invoke reconstruction")
    return config


def copy_verified(source_root: Path, output_root: Path, record: Mapping[str, Any], label: str) -> dict[str, Any]:
    verified = verify(source_root / record["path"], record, label)
    destination = output_root / record["path"]
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source_root / record["path"], destination)
    return verified


def run(config_path: Path, repo_root: Path, artifact_root: Path, output_root: Path, source_commit: str, image_id: str) -> dict[str, Any]:
    config = load_config(config_path)
    if output_root.exists() or output_root.with_name(output_root.name + ".partial").exists():
        raise RuntimeError(f"fresh add-once output namespace required: {output_root}")
    partial = output_root.with_name(output_root.name + ".partial")
    partial.mkdir(parents=True)

    source_spec = config["source_web_review"]
    source_root = artifact_root / source_spec["relative_root"]
    verify(source_root / source_spec["manifest_path"], source_spec, "source web manifest")
    source_manifest = json.loads((source_root / source_spec["manifest_path"]).read_text(encoding="utf-8"))
    if source_manifest["task_id"] != source_spec["required_task_id"] or source_manifest["status"] != source_spec["required_status"]:
        raise RuntimeError("source web review identity/status drifted")
    viewer_record = source_manifest["viewer_manifest"]
    verify(source_root / viewer_record["path"], viewer_record, "source viewer manifest")
    source_viewer = json.loads((source_root / viewer_record["path"]).read_text(encoding="utf-8"))
    if len(source_viewer["buildings"]) != 199:
        raise RuntimeError("source viewer population is not 199")
    copied_assets = [copy_verified(source_root, partial, record, "source spatial asset") for record in source_manifest["asset_records"]]
    keep_application = {"overview.html", "overview.js", "three.module.min.js"}
    copied_application = [
        copy_verified(source_root, partial, record, "unchanged source application")
        for record in source_manifest["application_records"] if record["path"] in keep_application
    ]

    row_spec = config["rendered_rows"]
    row_root = artifact_root / row_spec["relative_root"]
    artifact_manifest_path = row_root / row_spec["artifact_manifest_path"]
    verify(artifact_manifest_path, row_spec, "render199 artifact manifest")
    artifact_manifest = json.loads(artifact_manifest_path.read_text(encoding="utf-8"))
    if artifact_manifest["task_id"] != row_spec["required_task_id"]:
        raise RuntimeError("render199 task identity drifted")
    preview_record = next(row for row in artifact_manifest["records"] if row["path"] == row_spec["preview_manifest_path"])
    verify(row_root / preview_record["path"], preview_record, "render199 preview manifest")
    preview = json.loads((row_root / preview_record["path"]).read_text(encoding="utf-8"))
    if len(preview["rows"]) != 199 or int(preview["anchor_preview10_png_byte_match_count"]) != 10:
        raise RuntimeError("render199 preview count or frozen anchor match drifted")
    row_by_id = {row["building_id"]: row for row in preview["rows"]}
    if set(row_by_id) != {row["stable_id"] for row in source_viewer["buildings"]}:
        raise RuntimeError("rendered row and web viewer memberships differ")
    row_records = []
    projected_by_id = {}
    for stable_id, row in row_by_id.items():
        source_relative = f"preview/rows/{row['filename']}"
        source = row_root / source_relative
        source_record = next(record for record in artifact_manifest["records"] if record["path"] == source_relative)
        verify(source, source_record, "exact rendered row PNG")
        output_relative = f"projected_rows/{row['filename']}"
        destination = partial / output_relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
        copied = file_record(destination, partial)
        if copied["sha256"] != row["output_sha256"]:
            raise RuntimeError(f"copied row differs from preview receipt: {stable_id}")
        row_records.append(copied)
        projected_by_id[stable_id] = {
            "path": output_relative, "bytes": copied["bytes"], "sha256": copied["sha256"],
            "renderer": "scripts/p2/qualitative_row1_current_raw_v6/preview10_v4.py",
            "browser_redraw": False,
        }

    viewer = dict(source_viewer)
    viewer["schema"] = "jointbuildgs.p2.c1_c2_original_global_v3.web_viewer_manifest.exact_rows.v1"
    viewer["task_id"] = config["task_id"]
    viewer["buildings"] = [{**row, "projected_row": projected_by_id[row["stable_id"]]} for row in source_viewer["buildings"]]
    viewer["projected_rows"] = {
        "task_id": artifact_manifest["task_id"], "count": 199,
        "renderer": "scripts/p2/qualitative_row1_current_raw_v6/preview10_v4.py",
        "frozen_preview10_png_byte_match_count": 10, "browser_redraw": False,
    }
    viewer["scientific_verdict"] = None
    write_new(partial / "viewer_manifest.json", canonical_json_bytes(viewer))
    new_viewer_record = file_record(partial / "viewer_manifest.json", partial)

    application_records = list(copied_application)
    for name, app_spec in config["application"].items():
        source = repo_root / app_spec["git_path"]
        verify(source, app_spec, f"application {name}")
        destination = partial / app_spec["output_path"]
        shutil.copyfile(source, destination)
        application_records.append(file_record(destination, partial))
    readme = (
        "# JointBuildGS 199-building web review with exact frozen projected-row PNGs\n\n"
        "The always-visible top image row is copied byte-for-byte from the full199 driver of "
        "`scripts/p2/qualitative_row1_current_raw_v6/preview10_v4.py`. The browser does not redraw "
        "rooflines. Existing O/X localStorage remains unchanged. Scientific verdict is null.\n"
    ).encode("utf-8")
    write_new(partial / "README.md", readme)
    config_size, config_sha = sha256_file(config_path)
    script_size, script_sha = sha256_file(Path(__file__))
    receipt = {
        "schema": "jointbuildgs.p2.c1_c2_original_global_v3.web_review199_exact_rows.receipt.v1",
        "task_id": config["task_id"], "state": "complete", "generated_utc": datetime.now(timezone.utc).isoformat(),
        "repository_base_commit": source_commit, "runtime_image_id": image_id,
        "source_web_review_task_id": source_manifest["task_id"], "rendered_rows_task_id": artifact_manifest["task_id"],
        "building_count": 199, "row_png_count": len(row_records), "browser_redraw": False,
        "config": {"bytes": config_size, "sha256": config_sha}, "script": {"bytes": script_size, "sha256": script_sha},
        "scientific_verdict": None,
    }
    write_new(partial / "run_receipt_v1.json", canonical_json_bytes(receipt))
    manifest = {
        "schema": "jointbuildgs.p2.c1_c2_original_global_v3.web_review199_exact_rows.artifact_manifest.v1",
        "task_id": config["task_id"], "status": "READY_FOR_HUMAN_WEB_REVIEW",
        "application_records": sorted(application_records, key=lambda row: row["path"]),
        "viewer_manifest": new_viewer_record, "readme": file_record(partial / "README.md", partial),
        "receipt": file_record(partial / "run_receipt_v1.json", partial),
        "asset_records": copied_assets, "projected_row_records": sorted(row_records, key=lambda row: row["path"]),
        "asset_record_count": len(copied_assets), "projected_row_record_count": len(row_records),
        "execution": config["execution"], "scientific_verdict": None,
    }
    write_new(partial / "manifest_web_review199_exact_rows_v1.json", canonical_json_bytes(manifest))
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
