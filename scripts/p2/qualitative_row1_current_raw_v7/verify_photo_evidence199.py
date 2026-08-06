#!/usr/bin/env python3
"""Verify a completed 199-building photo-evidence package without recomputation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping

from scripts.p2.qualitative_199_cloudcompare_scene_v1.build_scene import sha256_file


def comparable_view(view: Mapping[str, Any]) -> dict[str, Any]:
    camera = view.get("camera")
    return {
        "role": view["role"], "status": view["status"], "source": view.get("source"),
        "camera_name": camera.get("camera_name") if camera else None,
        "crop_xyxy": camera.get("crop_xyxy") if camera else None,
    }


def verify_record(root: Path, record: Mapping[str, Any]) -> None:
    size, digest = sha256_file(root / record["path"])
    if size != int(record["bytes"]) or digest != record["sha256"]:
        raise RuntimeError(f"artifact identity mismatch: {record['path']}")


def verify(root: Path, anchor_selection: Path) -> dict[str, Any]:
    manifest = json.loads((root / "control/artifact_manifest_v1.json").read_text(encoding="utf-8"))
    if manifest.get("scientific_verdict", "missing") is not None:
        raise RuntimeError("artifact manifest scientific_verdict must remain null")
    if manifest["record_count"] != len(manifest["records"]):
        raise RuntimeError("artifact manifest record count mismatch")
    for record in manifest["records"]:
        verify_record(root, record)
    summary = json.loads((root / "control/summary_v1.json").read_text(encoding="utf-8"))
    evidence = json.loads((root / "photo_evidence_manifest_v1.json").read_text(encoding="utf-8"))
    selections = [json.loads(line) for line in (root / "selection/row1_camera_selection_v7.jsonl").read_text(encoding="utf-8").splitlines() if line]
    if len(selections) != 199 or len(evidence["buildings"]) != 199:
        raise RuntimeError("photo evidence population is not 199")
    if [int(row["population_index"]) for row in selections] != list(range(1, 200)):
        raise RuntimeError("selection population order drifted")
    selected = missing = photo_count = 0
    for building in evidence["buildings"]:
        if len(building["panels"]) != 4:
            raise RuntimeError(f"panel count drift: {building['stable_id']}")
        for panel in building["panels"]:
            if panel["status"] != "SELECTED":
                missing += 1
                if panel.get("photo") is not None:
                    raise RuntimeError("missing panel unexpectedly has a photo")
                continue
            selected += 1
            photo_count += 1
            fallback = not bool(panel["building_sparse_confirmation"])
            for key in ("reference", "lidar", "mvs"):
                status = panel["overlays"][key]["status"]
                if fallback and status != "OMITTED_NO_BUILDING_SPARSE_CONFIRMATION":
                    raise RuntimeError("terminal fallback unexpectedly has an overlay")
            if not fallback and panel["overlays"]["reference"]["status"] != "PROJECTED":
                raise RuntimeError("validated panel lost its independent reference projection")
    if (selected, missing, photo_count) != (
        int(summary["selected_panel_count"]), int(summary["missing_panel_count"]), int(summary["selected_panel_count"])
    ):
        raise RuntimeError("summary panel counts differ from evidence")
    anchor = {row["building_id"]: row for row in (json.loads(line) for line in anchor_selection.read_text(encoding="utf-8").splitlines() if line)}
    actual = {row["building_id"]: row for row in selections}
    for stable_id, expected in anchor.items():
        if [comparable_view(row) for row in actual[stable_id]["views"]] != [comparable_view(row) for row in expected["views"]]:
            raise RuntimeError(f"frozen 10-building selection anchor drift: {stable_id}")
    return {
        "status": "VERIFIED", "task_id": manifest["task_id"], "building_count": 199,
        "selected_panel_count": selected, "missing_panel_count": missing,
        "record_count": manifest["record_count"], "scientific_verdict": None,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--anchor-selection", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(verify(args.root, args.anchor_selection), ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
