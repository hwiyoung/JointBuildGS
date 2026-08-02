#!/usr/bin/env python3
"""Render only the corrected seven-cell 199-to-72 explainer from sealed evidence."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
from typing import Any

from src.visualization.fixed_view_qualitative import (
    BBox,
    _bbox_from_row,
    _render_eligibility,
    stream_eligibility_cells,
)


def _read_csv(path: Path) -> list[dict[str, str]]:
    if path.is_symlink() or not path.is_file():
        raise RuntimeError(f"required CSV is not a regular file: {path}")
    with path.open("r", encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def _safe(root: Path, relative: str) -> Path:
    value = Path(relative)
    if value.is_absolute() or ".." in value.parts:
        raise RuntimeError(f"unsafe relative path: {relative}")
    root = root.resolve()
    result = (root / value).resolve()
    if root not in result.parents:
        raise RuntimeError(f"path escaped declared root: {relative}")
    return result


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _example_tuple(row: dict[str, str]) -> list[Any]:
    return [
        row["stable_id"],
        row["candidate"].strip().lower() == "true",
        int(row["reference_cells"]),
        int(row["image_views"]),
        int(row["mvs_cells"]),
        int(row["c4_cells"]),
        row["exclusion_reason"],
    ]


def render(*, config_path: Path, repository_root: Path, compact_cells: Path, output_dir: Path) -> dict[str, Any]:
    config = json.loads(config_path.read_text(encoding="utf-8"))
    if (
        config.get("schema") != "jointbuildgs.c1_c2_qualitative_layout_correction_config.v1"
        or config.get("scientific_verdict") is not None
    ):
        raise RuntimeError("layout-correction config identity/verdict mismatch")
    if output_dir.exists() and any(output_dir.iterdir()):
        raise RuntimeError("layout-correction output directory must be absent or empty")
    output_dir.mkdir(parents=True, exist_ok=True)

    examples = _read_csv(_safe(repository_root, config["inputs"]["examples_git_path"]))
    by_label = {row["label"]: row for row in examples}
    labels = list(config["example_labels"])
    if labels != ["P1", "P2", "P3", "F1", "F2", "F3", "F4"] or set(by_label) != set(labels):
        raise RuntimeError("exact eligibility roster labels mismatch")
    selected = [by_label[label] for label in labels]
    for row in selected:
        if _example_tuple(row) != config["expected_examples"][row["label"]][:7]:
            raise RuntimeError(f"eligibility example contract drift: {row['label']}")

    ledgers = _read_csv(_safe(repository_root, config["inputs"]["bbox_ledger_git_path"]))
    ledger_map = {row["stable_id"]: row for row in ledgers}
    specs: dict[str, tuple[BBox, set[str]]] = {}
    for example in selected:
        stable_id = example["stable_id"]
        ledger = ledger_map.get(stable_id)
        if ledger is None:
            raise RuntimeError(f"eligibility bbox ledger row is absent: {stable_id}")
        bbox = _bbox_from_row(ledger)
        if [bbox.min_x, bbox.min_y, bbox.max_x, bbox.max_y] != config["expected_examples"][example["label"]][7]:
            raise RuntimeError(f"eligibility bbox contract drift: {example['label']}")
        patches = {value for value in ledger["reference_candidate_patch_ids"].split(";") if value}
        specs[stable_id] = (bbox, patches)

    compact = config["inputs"]["compact_reference_cells"]
    cells, compact_read = stream_eligibility_cells(
        compact_cells,
        specs,
        expected_bytes=int(compact["bytes"]),
        expected_sha256=str(compact["sha256"]),
        expected_rows=int(compact["expected_rows"]),
    )
    figure_name = config["result"]["figure_filename"]
    figure_path = output_dir / figure_name
    records = _render_eligibility(
        output_path=figure_path,
        examples=selected,
        ledgers=ledger_map,
        cells=cells,
        style=config["style"],
    )
    figure_record = {
        "path": figure_name,
        "bytes": figure_path.stat().st_size,
        "sha256": _sha256(figure_path),
        "post_write_digest_passes": 1,
    }
    if figure_record["bytes"] > int(config["execution"]["new_output_bytes_hard"]):
        raise RuntimeError("layout-correction output cap exceeded")
    manifest = {
        "schema": "jointbuildgs.c1_c2_qualitative_layout_correction_manifest.v1",
        "task_id": config["task_id"],
        "run_id": config["run_id"],
        "status": "LAYOUT_CORRECTED_AUTOMATED_CONTAINMENT_PASS",
        "predecessor": config["predecessor"],
        "examples": records,
        "compact_source_read": compact_read,
        "output": figure_record,
        "scope": config["scope"],
        "scientific_verdict": None,
    }
    manifest_path = output_dir / "layout_correction_manifest_v1.json"
    with manifest_path.open("xb") as stream:
        stream.write((json.dumps(manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8"))
        stream.flush()
        os.fsync(stream.fileno())
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--repository-root", type=Path, required=True)
    parser.add_argument("--compact-reference-cells", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    result = render(
        config_path=args.config,
        repository_root=args.repository_root,
        compact_cells=args.compact_reference_cells,
        output_dir=args.output_dir,
    )
    print(json.dumps({"status": result["status"], "examples": len(result["examples"]), "scientific_verdict": None}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
