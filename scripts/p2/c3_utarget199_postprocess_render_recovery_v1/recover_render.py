#!/usr/bin/env python3
"""Add-once recovery for C3 postprocess outputs completed before GS rendering."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
from typing import Any


TASK_ID = "P2-C3-UTARGET199-POSTPROCESS-RENDER-RECOVERY-v1"
SOURCE_TASK_ID = "P2-C3-UTARGET199-POSTPROCESS-v1"
CONTROL_FILES = (
    "C3_1_SEM_geometry_frozen_v1.json",
    "C3_2_SEM_DEPTH_geometry_frozen_v1.json",
    "population_associated_v1.json",
    "finalized_v1.json",
)


def _record(path: Path, root: Path) -> dict[str, Any]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as stream:
        while block := stream.read(1024 * 1024):
            digest.update(block)
            size += len(block)
    return {
        "path": path.relative_to(root).as_posix(),
        "bytes": size,
        "sha256": digest.hexdigest(),
    }


def _tree_digest(records: list[dict[str, Any]]) -> str:
    digest = hashlib.sha256()
    for row in records:
        digest.update(
            f"{row['path']}\t{row['bytes']}\t{row['sha256']}\n".encode("utf-8")
        )
    return digest.hexdigest()


def recover(source_root: Path, output_root: Path) -> dict[str, Any]:
    if output_root.exists():
        raise RuntimeError("fresh add-once recovery namespace required")
    for relative in ("conditions", "freeze", "results"):
        if not (source_root / relative).is_dir():
            raise RuntimeError(f"source postprocess directory missing: {relative}")
    for filename in CONTROL_FILES:
        if not (source_root / "control" / filename).is_file():
            raise RuntimeError(f"source postprocess control missing: {filename}")

    source_paths: list[Path] = []
    for relative in ("conditions", "freeze", "results"):
        for path in sorted((source_root / relative).rglob("*")):
            if path.is_symlink():
                raise RuntimeError(f"source postprocess contains symlink: {path}")
            if path.is_file():
                source_paths.append(path)
    source_paths.extend(source_root / "control" / name for name in CONTROL_FILES)
    source_paths.sort(key=lambda path: path.relative_to(source_root).as_posix())
    source_records = [_record(path, source_root) for path in source_paths]

    output_root.mkdir(parents=True)
    for source_path in source_paths:
        relative = source_path.relative_to(source_root)
        target = output_root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        with source_path.open("rb") as source, target.open("xb") as destination:
            shutil.copyfileobj(source, destination, length=1024 * 1024)

    copied_paths = [output_root / row["path"] for row in source_records]
    copied_records = [_record(path, output_root) for path in copied_paths]
    if copied_records != source_records:
        raise RuntimeError("copied postprocess payload differs from preserved source")

    source_finalized = json.loads(
        (source_root / "control/finalized_v1.json").read_text(encoding="utf-8")
    )
    if source_finalized.get("result_rows") != 398:
        raise RuntimeError("source postprocess does not contain exact 398 finalized rows")
    terminal_count = sum(
        row["path"].endswith("/roofer_terminal_v1.json") for row in source_records
    )
    if terminal_count != 25:
        raise RuntimeError(f"source postprocess terminal count differs: {terminal_count}")

    body = {
        "schema": "jointbuildgs.c3_utarget199_postprocess_render_recovery.v1",
        "task_id": TASK_ID,
        "source_task_id": SOURCE_TASK_ID,
        "status": "EXACT_PRE_RENDER_PAYLOAD_RECOVERED",
        "source_root": source_root.as_posix(),
        "file_count": len(source_records),
        "total_bytes": sum(row["bytes"] for row in source_records),
        "tree_sha256": _tree_digest(source_records),
        "result_rows": 398,
        "roofer_terminal_count": terminal_count,
        "c1_c2_reruns": 0,
        "c3_roofer_reruns": 0,
        "metric_recomputations": 0,
        "scientific_verdict": None,
    }
    control = output_root / "control/recovered_pre_render_payload_v1.json"
    with control.open("xb") as stream:
        stream.write(
            (json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()
        )
    return body


def complete(output_root: Path) -> dict[str, Any]:
    recovered = json.loads(
        (output_root / "control/recovered_pre_render_payload_v1.json").read_text(
            encoding="utf-8"
        )
    )
    finalized = json.loads(
        (output_root / "control/finalized_v1.json").read_text(encoding="utf-8")
    )
    rendered = json.loads(
        (output_root / "control/gs_render_complete_v1.json").read_text(encoding="utf-8")
    )
    qualitative = json.loads(
        (output_root / "control/qualitative_complete_v1.json").read_text(encoding="utf-8")
    )
    if recovered.get("status") != "EXACT_PRE_RENDER_PAYLOAD_RECOVERED":
        raise RuntimeError("pre-render payload recovery is incomplete")
    if finalized.get("result_rows") != 398:
        raise RuntimeError("finalized row count differs")
    if rendered.get("render_panel_count") != 8:
        raise RuntimeError("GS render panel count differs")
    if qualitative.get("case_sheet_count") != 199:
        raise RuntimeError("qualitative case sheet count differs")

    body = {
        "schema": "jointbuildgs.c3_utarget199_postprocess_render_recovery_complete.v1",
        "task_id": TASK_ID,
        "source_task_id": SOURCE_TASK_ID,
        "status": "TECHNICAL_COMPLETE",
        "building_count": 199,
        "condition_count": 2,
        "result_rows": 398,
        "render_panel_count": 8,
        "case_sheet_count": 199,
        "roofer_unique_operations": 25,
        "c3_roofer_reruns": 0,
        "metric_recomputations": 0,
        "official_G3_G4_PASS_usable": None,
        "scientific_verdict": None,
    }
    path = output_root / "control/completed_v1.json"
    with path.open("xb") as stream:
        stream.write(
            (json.dumps(body, sort_keys=True, separators=(",", ":")) + "\n").encode()
        )
    return body


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="mode", required=True)
    recovery = sub.add_parser("recover")
    recovery.add_argument("--source-root", type=Path, required=True)
    recovery.add_argument("--output-root", type=Path, required=True)
    completion = sub.add_parser("complete")
    completion.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    if args.mode == "recover":
        result = recover(args.source_root, args.output_root)
    else:
        result = complete(args.output_root)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
