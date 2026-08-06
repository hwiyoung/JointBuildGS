#!/usr/bin/env python3
"""Add a name-preserving footprint DXF without rewriting the frozen scene bundle."""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import json
import os
from pathlib import Path
from typing import Sequence

from scripts.p2.qualitative_199_cloudcompare_scene_v1.build_scene import (
    REPO,
    canonical_json_bytes,
    dxf_tables,
    file_record,
    sha256_file,
    write_new,
)


DEFAULT_ARTIFACT_ROOT = REPO.parent / "JointBuildGS-artifacts"
RELATIVE_SCENE_ROOT = Path(
    "phase-payloads/p2/qualitative_199_cloudcompare_scene_v1/"
    "P2-QUALITATIVE-199-CLOUDCOMPARE-SCENE-v1"
)


def insert_layer_tables(source: bytes, layer_names: Sequence[str]) -> bytes:
    text = source.decode("ascii")
    if "\n2\nTABLES\n" in text:
        raise RuntimeError("source DXF already contains a TABLES section")
    marker = "0\nSECTION\n2\nENTITIES\n"
    if text.count(marker) != 1:
        raise RuntimeError("source DXF ENTITIES section is missing or ambiguous")
    table_text = "\n".join(dxf_tables(layer_names)) + "\n"
    return text.replace(marker, table_text + marker, 1).encode("ascii")


def read_layer_names(index_path: Path) -> list[str]:
    with index_path.open("r", encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    if len(rows) != 199:
        raise RuntimeError(f"building index count drift: {len(rows)} != 199")
    if [int(row["population_index"]) for row in rows] != list(range(1, 200)):
        raise RuntimeError("building index is not the frozen 1..199 order")
    names = [row["dxf_layer"] for row in rows]
    if len(set(names)) != 199:
        raise RuntimeError("building index DXF layers are not 199 unique names")
    return names


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--artifact-root",
        type=Path,
        default=Path(os.environ.get("JBGS_ARTIFACT_ROOT", DEFAULT_ARTIFACT_ROOT)),
    )
    args = parser.parse_args()
    scene_root = args.artifact_root.resolve() / RELATIVE_SCENE_ROOT
    source_path = scene_root / "layers/footprints_199_local.dxf"
    index_path = scene_root / "control/building_index_v1.csv"
    manifest_path = scene_root / "scene_manifest.json"
    output_path = scene_root / "layers/footprints_199_named_local.dxf"
    receipt_path = scene_root / "control/named_footprint_dxf_receipt_v1.json"
    readme_path = scene_root / "README_NAMED_FOOTPRINT.txt"

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    expected = manifest["layers"]["footprints"]
    source_size, source_hash = sha256_file(source_path)
    if source_size != int(expected["bytes"]) or source_hash != expected["sha256"]:
        raise RuntimeError("source footprint DXF no longer matches the sealed scene manifest")

    layer_names = read_layer_names(index_path)
    repaired = insert_layer_tables(source_path.read_bytes(), layer_names)
    decoded = repaired.decode("ascii")
    declared = {name for name in layer_names if f"0\nLAYER\n2\n{name}\n" in decoded}
    referenced = {name for name in layer_names if f"0\nPOLYLINE\n8\n{name}\n" in decoded}
    if declared != set(layer_names) or referenced != set(layer_names):
        raise RuntimeError("named DXF declaration/entity validation failed")
    write_new(output_path, repaired)

    readme = """Named 199-building footprint DXF add-on

Load layers/footprints_199_named_local.dxf instead of footprints_199_local.dxf.
It has 199 explicitly declared DXF layers named B###_DEBY_LOD2_..., so CloudCompare
can retain the building identifier for each imported footprint polyline.

The original footprint geometry and coordinates are byte-for-byte unchanged outside
the newly inserted DXF TABLES section. This is a display/identity repair only.
"""
    write_new(readme_path, readme.encode("utf-8"))
    receipt = {
        "schema": "jointbuildgs.p2.qualitative_199_cloudcompare_scene.named_footprint_dxf.v1",
        "task_id": "P2-QUALITATIVE-199-CLOUDCOMPARE-SCENE-NAMED-FOOTPRINT-DXF-v1",
        "status": "COMPLETE_DISPLAY_IDENTITY_REPAIR",
        "completed_at_utc": datetime.now(timezone.utc).isoformat(),
        "source": {
            "path": source_path.relative_to(scene_root).as_posix(),
            "bytes": source_size,
            "sha256": source_hash,
        },
        "output": file_record(output_path, scene_root),
        "building_count": 199,
        "declared_unique_building_layer_count": len(declared),
        "entity_referenced_unique_building_layer_count": len(referenced),
        "geometry_or_coordinate_change": False,
        "roofer_invocations": 0,
        "reconstruction_invocations": 0,
        "scientific_verdict": None,
    }
    write_new(receipt_path, canonical_json_bytes(receipt))
    print(json.dumps(receipt, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
