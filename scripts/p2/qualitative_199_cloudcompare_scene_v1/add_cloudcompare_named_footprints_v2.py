#!/usr/bin/env python3
"""Convert the frozen footprint DXF entities to one CloudCompare-named OBJ."""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import json
import os
from pathlib import Path
from typing import Any, Sequence

from scripts.p2.qualitative_199_cloudcompare_scene_v1.build_scene import (
    REPO,
    canonical_json_bytes,
    file_record,
    sha256_file,
    write_new,
)
from scripts.p2.qualitative_199_cloudcompare_scene_v1.add_named_footprints import (
    DEFAULT_ARTIFACT_ROOT,
    RELATIVE_SCENE_ROOT,
    read_layer_names,
)


def parse_polyline_entities(source: bytes) -> list[dict[str, Any]]:
    lines = source.decode("ascii").splitlines()
    if len(lines) % 2:
        raise RuntimeError("DXF group-code/value stream has odd length")
    pairs = list(zip(lines[0::2], lines[1::2]))
    entities: list[dict[str, Any]] = []
    index = 0
    while index < len(pairs):
        code, value = pairs[index]
        if (code, value) != ("0", "POLYLINE"):
            index += 1
            continue
        index += 1
        layer = None
        closed = False
        vertices: list[tuple[float, float, float]] = []
        while index < len(pairs):
            code, value = pairs[index]
            if code == "8" and layer is None:
                layer = value
            elif code == "70" and not vertices:
                closed = bool(int(value) & 1)
            elif (code, value) == ("0", "VERTEX"):
                index += 1
                xyz = {"10": None, "20": None, "30": None}
                while index < len(pairs) and pairs[index][0] != "0":
                    vertex_code, vertex_value = pairs[index]
                    if vertex_code in xyz:
                        xyz[vertex_code] = float(vertex_value)
                    index += 1
                if any(xyz[key] is None for key in ("10", "20", "30")):
                    raise RuntimeError("DXF VERTEX is missing XYZ")
                vertices.append((float(xyz["10"]), float(xyz["20"]), float(xyz["30"])))
                continue
            elif (code, value) == ("0", "SEQEND"):
                index += 1
                break
            index += 1
        if not layer or len(vertices) < 3:
            raise RuntimeError("DXF POLYLINE is missing a layer or vertices")
        entities.append({"layer": layer, "closed": closed, "vertices": vertices})
    return entities


def named_obj_bytes(entities: Sequence[dict[str, Any]], layer_names: Sequence[str]) -> bytes:
    allowed = set(layer_names)
    if {str(entity["layer"]) for entity in entities} != allowed:
        raise RuntimeError("DXF entity layers do not match the frozen 199-building index")
    lines = [
        "# JointBuildGS CloudCompare 2.13 name-preserving footprint polylines",
        "# Scene-local coordinates; group name is B###_DEBY_LOD2_...",
    ]
    vertex_offset = 1
    group_counts: dict[str, int] = {}
    for entity in entities:
        layer = str(entity["layer"])
        group_counts[layer] = group_counts.get(layer, 0) + 1
        lines.append(f"g {layer}")
        vertices = list(entity["vertices"])
        for x, y, z in vertices:
            lines.append(f"v {x:.6f} {y:.6f} {z:.6f}")
        indices = list(range(vertex_offset, vertex_offset + len(vertices)))
        if entity["closed"]:
            indices.append(indices[0])
        lines.append("l " + " ".join(map(str, indices)))
        vertex_offset += len(vertices)
    if set(group_counts) != allowed or any(count < 1 for count in group_counts.values()):
        raise RuntimeError("OBJ group coverage validation failed")
    return ("\n".join(lines) + "\n").encode("ascii")


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
    output_path = scene_root / "layers/footprints_199_cloudcompare_named_local.obj"
    receipt_path = scene_root / "control/cloudcompare_named_footprint_receipt_v2.json"
    readme_path = scene_root / "README_CLOUDCOMPARE_NAMED_FOOTPRINT_V2.txt"

    names = read_layer_names(index_path)
    entities = parse_polyline_entities(source_path.read_bytes())
    output = named_obj_bytes(entities, names)
    write_new(output_path, output)
    group_lines = [line[2:] for line in output.decode("ascii").splitlines() if line.startswith("g ")]
    if len(set(group_lines)) != 199 or len(group_lines) != len(entities):
        raise RuntimeError("written OBJ group audit failed")

    write_new(
        readme_path,
        (
            "CloudCompare 2.13.x hardcodes imported DXF entity names as Polyline.\n"
            "Load layers/footprints_199_cloudcompare_named_local.obj instead.\n"
            "Its OBJ g-groups are named B###_DEBY_LOD2_... and preserve the exact DXF XYZ vertices.\n"
        ).encode("utf-8"),
    )
    source_size, source_hash = sha256_file(source_path)
    receipt = {
        "schema": "jointbuildgs.p2.qualitative_199_cloudcompare_scene.named_footprint_obj.v2",
        "task_id": "P2-QUALITATIVE-199-CLOUDCOMPARE-NAMED-FOOTPRINT-v2",
        "status": "COMPLETE_CLOUDCOMPARE_2P13_NAME_PRESERVING_OBJ",
        "completed_at_utc": datetime.now(timezone.utc).isoformat(),
        "source": {"path": source_path.relative_to(scene_root).as_posix(), "bytes": source_size, "sha256": source_hash},
        "output": file_record(output_path, scene_root),
        "unique_building_group_count": 199,
        "polyline_count": len(entities),
        "vertex_count": sum(len(entity["vertices"]) for entity in entities),
        "geometry_or_coordinate_change": False,
        "cloudcompare_dxf_behavior": "2.13.2 DxfFilter hardcodes ccPolyline name to Polyline",
        "scientific_verdict": None,
    }
    write_new(receipt_path, canonical_json_bytes(receipt))
    print(json.dumps(receipt, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
