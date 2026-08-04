#!/usr/bin/env python3
"""Hash-verify and inherit the completed extraction from the preserved first partial."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
from typing import Any, Mapping

from scripts.p2.c3_tsdf_roof_diagnostic_v1.contract import (
    canonical_json_bytes,
    load_config,
    resolve_artifact,
    sha256_file,
    validate_config,
    write_new,
)


def _verify_record(source_root: Path, record: Mapping[str, Any]) -> None:
    relative = Path(str(record.get("path", "")))
    if relative.is_absolute() or ".." in relative.parts:
        raise RuntimeError(f"unsafe inherited record path: {relative}")
    path = source_root / relative
    if path.is_symlink() or not path.is_file():
        raise RuntimeError(f"inherited record missing/non-regular: {path}")
    size, digest = sha256_file(path)
    if size != int(record.get("bytes", -1)) or digest != record.get("sha256"):
        raise RuntimeError(f"inherited record digest drift: {path}")


def run(output_root: Path, artifact_root: Path, source_commit: str) -> dict[str, Any]:
    config = load_config()
    validate_config(config)
    if output_root.exists():
        if output_root.is_symlink() or any(output_root.iterdir()):
            raise RuntimeError(f"recovery output namespace exists/non-empty: {output_root}")
    else:
        output_root.mkdir(parents=True)
    source_root = resolve_artifact(
        artifact_root, config["source"]["recovery_source_relative_root"], "recovery source"
    )
    pair = json.loads((source_root / "control/extraction_pair_complete_v1.json").read_text(encoding="utf-8"))
    if pair.get("status") != "COMPLETE_TWO_CONDITIONS":
        raise RuntimeError("recovery source did not complete both extractions")
    if pair.get("source_commit") != "c9f5b709715d0839f23c0a183d9d6b3084d0859f":
        raise RuntimeError("recovery source implementation commit drifted")
    if pair.get("shared_view_plan_identical") is not True or pair.get("poisson_tsdf_same_rendered_roof_evidence") is not True:
        raise RuntimeError("recovery source comparison contract drifted")
    verified = 0
    for record in pair["condition_controls"]:
        _verify_record(source_root, record)
        verified += 1
    for condition_id in config["scope"]["condition_ids"]:
        control_path = source_root / f"conditions/{condition_id}/control/extraction_complete_v1.json"
        control = json.loads(control_path.read_text(encoding="utf-8"))
        if control.get("status") != "COMPLETE_NO_TRAINING" or control.get("scientific_verdict", "missing") is not None:
            raise RuntimeError(f"incomplete inherited condition: {condition_id}")
        if int(control.get("gs_training_invocations", -1)) != 0 or int(control.get("roofer_invocations", -1)) != 0:
            raise RuntimeError(f"inherited execution counters drifted: {condition_id}")
        for row in control["building_results"]:
            result_path = source_root / f"conditions/{condition_id}/buildings/{row['stable_id']}/result_v1.json"
            result = json.loads(result_path.read_text(encoding="utf-8"))
            if result.get("scientific_verdict", "missing") is not None:
                raise RuntimeError("inherited result verdict drifted")
            for key in ("roof_points",):
                if result.get(key) is not None:
                    _verify_record(source_root, result[key])
                    verified += 1
            for key in ("poisson", "tsdf"):
                if result.get(key) is not None:
                    _verify_record(source_root, result[key]["mesh"])
                    verified += 1
    shutil.copytree(source_root / "conditions", output_root / "conditions")
    (output_root / "control").mkdir(exist_ok=True)
    for name in ("source_commit.txt", "shared_view_plan_v1.json", "extraction_pair_complete_v1.json"):
        shutil.copy2(source_root / "control" / name, output_root / "control" / name)
    write_new(output_root / "control/recovery_source_commit.txt", (source_commit + "\n").encode("ascii"))
    body = {
        "schema": "jointbuildgs.c3_tsdf_roof_extraction_recovery.v1",
        "status": "INHERITED_TWO_HASH_VERIFIED_EXTRACTIONS",
        "source_relative_root": config["source"]["recovery_source_relative_root"],
        "source_extraction_commit": pair["source_commit"],
        "recovery_commit": source_commit,
        "verified_record_count": verified,
        "checkpoint_render_extractions_this_recovery": 0,
        "gs_training_invocations": 0,
        "roofer_invocations": 0,
        "metric_recomputations": 0,
        "scientific_verdict": None,
    }
    write_new(output_root / "control/extraction_recovery_complete_v1.json", canonical_json_bytes(body))
    return body


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--source-commit", required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.output_root, args.artifact_root, args.source_commit), ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
