#!/usr/bin/env python3
"""Materialize the preregistered arm A-prime fallback population by CSV join.

The script deliberately selects semantic rows from the immutable W1 target table;
it does not carry a handwritten building-id list.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


INPUT_SHA256 = "256d376080dca7c496aa3f34c9bcbbd1a8e52d0b25d6e98f7eec388b3f6cc943"
EXPECTED_FAILURES = 8
EXPECTED_TOTAL = 9


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    observed_hash = sha256(args.input)
    if observed_hash != INPUT_SHA256:
        raise RuntimeError(
            f"locked target CSV hash mismatch: {observed_hash} != {INPUT_SHA256}"
        )

    with args.input.open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    if len(rows) != 178:
        raise RuntimeError(f"expected 178 canonical rows, got {len(rows)}")
    if any(
        row["gs4buildings_overlap_status"]
        != "unresolvable_public_artifact_missing"
        for row in rows
    ):
        raise RuntimeError("P7 fallback is invalid because overlap status changed")

    failures = [row for row in rows if row["priority_bucket"] == "01_p0_dim_failure"]
    controls = [
        row
        for row in rows
        if row["selection_reason"].startswith("textured_positive_control_anchor:")
    ]
    if len(failures) != EXPECTED_FAILURES:
        raise RuntimeError(f"expected {EXPECTED_FAILURES} DIM failures, got {len(failures)}")
    if len(controls) != 1:
        raise RuntimeError(f"expected one textured anchor, got {len(controls)}")

    failures.sort(key=lambda row: int(row["processing_order"]))
    selected = failures + controls
    if len({row["building_id"] for row in selected}) != EXPECTED_TOTAL:
        raise RuntimeError("fallback selection is not nine unique canonical rows")

    output_fields = [
        "aprime_order",
        "building_id",
        "target_role",
        "tier",
        "cohort",
        "source_processing_order",
        "selection_reason",
        "texture_low_gradient_fraction",
        "selection_sources",
        "gs4buildings_overlap_status",
        "gs4buildings_overlap_reason",
    ]
    output_rows = []
    for index, row in enumerate(selected, start=1):
        output_rows.append(
            {
                "aprime_order": index,
                "building_id": row["building_id"],
                "target_role": "dim_failure" if row in failures else "textured_control",
                "tier": row["tier"],
                "cohort": row["cohort"],
                "source_processing_order": row["processing_order"],
                "selection_reason": row["selection_reason"],
                "texture_low_gradient_fraction": row["texture_low_gradient_fraction"],
                "selection_sources": row["selection_sources"],
                "gs4buildings_overlap_status": row["gs4buildings_overlap_status"],
                "gs4buildings_overlap_reason": row["gs4buildings_overlap_reason"],
            }
        )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=output_fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(output_rows)

    manifest = {
        "schema": "jointbuildgs.fusion_w1_aprime.targets.v1",
        "task_id": "FUS-W1-APRIME-TARGETS-001",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "selection_mode": "P7_fallback_exact_overlap_unresolved",
        "overlap_interpretation": "unknown_not_zero",
        "manual_building_id_entry": False,
        "input": {
            "path": str(args.input),
            "sha256": observed_hash,
            "rows": len(rows),
        },
        "join_predicates": {
            "dim_failures": "priority_bucket == 01_p0_dim_failure",
            "textured_control": "selection_reason startswith textured_positive_control_anchor:",
        },
        "counts": {
            "dim_failure": len(failures),
            "textured_control": len(controls),
            "total": len(output_rows),
        },
        "ordered_building_ids": [row["building_id"] for row in output_rows],
        "output": {
            "path": str(args.output),
            "sha256": sha256(args.output),
        },
        "verdict": None,
    }
    args.manifest.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
