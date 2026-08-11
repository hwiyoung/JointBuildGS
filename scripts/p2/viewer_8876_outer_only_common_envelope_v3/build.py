#!/usr/bin/env python3
"""Fill internal support holes so viewer boundaries represent sensor-domain exteriors only."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
from typing import Any

from shapely.geometry import Polygon, mapping, shape


REPO = Path("/workspace/JointBuildGS")
AR = Path("/artifacts/JointBuildGS")
CONFIG = REPO / "configs/p2/viewer_8876_outer_only_common_envelope_v3/viewer.json"
SOURCE = REPO / "scripts/p2/viewer_8876_outer_only_common_envelope_v3/build.py"
TASK = AR / "phase-payloads/p2/viewer_8876_outer_only_common_envelope_v3/P2-VIEWER-8876-OUTER-ONLY-COMMON-ENVELOPE-v3"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def record(path: Path, relative: str | None = None) -> dict[str, Any]:
    return {"path": relative or str(path), "bytes": path.stat().st_size, "sha256": sha256(path)}


def verify(path: Path, expected: dict[str, Any] | str) -> dict[str, Any]:
    if not path.is_file() or path.is_symlink():
        raise RuntimeError(f"missing or invalid input: {path}")
    result = record(path)
    expected_hash = expected if isinstance(expected, str) else expected["sha256"]
    expected_bytes = None if isinstance(expected, str) else int(expected["bytes"])
    if expected_bytes is not None and result["bytes"] != expected_bytes:
        raise RuntimeError(f"byte drift: {path}")
    if result["sha256"] != expected_hash:
        raise RuntimeError(f"hash drift: {path}")
    return result


def atomic_text(path: Path, text: str) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(text)
    os.replace(temporary, path)


def atomic_json(path: Path, body: object) -> None:
    atomic_text(path, json.dumps(body, indent=2, sort_keys=True) + "\n")


def main_polygon(geometry: Any) -> Polygon:
    if geometry.geom_type == "Polygon":
        return geometry
    polygons = [part for part in geometry.geoms if part.geom_type == "Polygon"]
    if not polygons:
        raise RuntimeError(f"no polygon in {geometry.geom_type}")
    return max(polygons, key=lambda polygon: polygon.area)


def exterior_only(layer: dict[str, Any]) -> Polygon:
    polygon = Polygon(layer["rings_world_xy"][0])
    if not polygon.is_valid:
        polygon = main_polygon(polygon.buffer(0))
    return Polygon(polygon.exterior)


def layer_from_polygon(previous: dict[str, Any], polygon: Polygon, shift: list[float]) -> dict[str, Any]:
    world = [[[round(float(x), 3), round(float(y), 3)] for x, y in polygon.exterior.coords]]
    local = [[[round(x - shift[0], 3), round(y - shift[1], 3)] for x, y in world[0]]]
    return {
        **{key: previous[key] for key in ("id", "label_ko", "color", "display_z_local_m", "outline_width_m", "display_only")},
        "rings_world_xy": world,
        "rings_local_xy": local,
        "ring_count": 1,
        "area_m2": float(polygon.area),
        "interior_holes_filled_for_domain_envelope": int(previous["ring_count"] - 1),
    }


def footprint_row(feature: dict[str, Any], cfg: dict[str, Any], shift: list[float]) -> dict[str, Any]:
    geometry = shape(feature["geometry"])
    polygons = [geometry] if geometry.geom_type == "Polygon" else list(geometry.geoms)
    rings: list[list[list[float]]] = []
    for polygon in polygons:
        for ring in [polygon.exterior, *polygon.interiors]:
            rings.append([[round(float(x) - shift[0], 3), round(float(y) - shift[1], 3)] for x, y in ring.coords])
    return {
        "stable_id": feature["properties"]["stable_id"],
        "rings_local_xy": rings,
        "z_local": float(cfg["candidate_display_z_local_m"]),
        "color": cfg["candidate_color"],
        "membership": "DISPLAY_ONLY_OUTER_COMMON_ENVELOPE_CANDIDATE_2M",
        "display_style": "OUTER_COMMON_ENVELOPE_CANDIDATE_OUTLINE",
    }


def main() -> None:
    cfg = json.loads(CONFIG.read_text())
    viewer = AR / cfg["viewer_root"]
    output = viewer / cfg["output_json"]
    if TASK.exists() or output.exists():
        raise RuntimeError("add-once output already exists")
    before = {name: verify(viewer / name, expected) for name, expected in cfg["expected_before"].items()}
    source_path = AR / cfg["source_envelopes_v2"]["path"]
    footprints_path = AR / cfg["shared_footprints_199"]["path"]
    source_record = verify(source_path, cfg["source_envelopes_v2"])
    footprints_record = verify(footprints_path, cfg["shared_footprints_199"])
    source = json.loads(source_path.read_text())
    source_layers = {layer["id"]: layer for layer in source["layers"]}
    shift = [float(value) for value in cfg["world_shift_xyz"]]
    e1 = exterior_only(source_layers["E1_MAIN_ENVELOPE"])
    e2 = exterior_only(source_layers["E2_MAIN_ENVELOPE"])
    common = main_polygon(e1.intersection(e2))
    common = Polygon(common.exterior)
    layers = [
        layer_from_polygon(source_layers["E1_MAIN_ENVELOPE"], e1, shift),
        layer_from_polygon(source_layers["E2_MAIN_ENVELOPE"], e2, shift),
        layer_from_polygon(source_layers["COMMON_MAIN_ENVELOPE"], common, shift),
    ]
    features = json.loads(footprints_path.read_text())["features"]
    margin = float(cfg["candidate_footprint_buffer_m"])
    no_margin = [feature for feature in features if common.covers(shape(feature["geometry"]))]
    candidates = [feature for feature in features if common.covers(shape(feature["geometry"]).buffer(margin))]
    if len(no_margin) != 82 or len(candidates) != 76:
        raise RuntimeError(f"outer-envelope count drift: no_margin={len(no_margin)}, buffered={len(candidates)}")
    candidate_rows = [footprint_row(feature, cfg, shift) for feature in candidates]
    output_doc = {
        "schema": "jointbuildgs.p2.viewer_8876.coverage_outer_envelopes.v3",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "method": {
            **source["method"],
            "interior_support_holes": "FILLED_TO_REPRESENT_OUTER_SENSOR_DOMAIN_ONLY",
            "candidate_footprint_buffer_m": margin,
        },
        "layers": layers,
        "common_outer_envelope_geojson": mapping(common),
        "no_margin_fully_contained_count": len(no_margin),
        "buffered_candidate_count": len(candidates),
        "buffered_candidate_ids": [row["stable_id"] for row in candidate_rows],
        "candidate_footprints": candidate_rows,
        "source_envelopes_v2": source_record,
        "shared_footprints_199": footprints_record,
        "role": "DISPLAY_ONLY_OUTER_SENSOR_DOMAIN_AND_EDGE_SAFE_CANDIDATE_DIAGNOSTIC",
        "target_membership_modified": False,
        "roofer_inputs_modified": False,
        "scientific_verdict": None,
    }
    atomic_json(output, output_doc)

    manifest_path = viewer / "viewer_manifest.json"
    manifest = json.loads(manifest_path.read_text())
    if len(manifest["target_building_footprints"]) != 72:
        raise RuntimeError("existing target72 drift")
    manifest["coverage_envelope_contract_v2_with_internal_holes"] = manifest["coverage_boundary_contract"]
    manifest["coverage_envelope_layers_v2_with_internal_holes"] = manifest["coverage_boundary_layers"]
    manifest["common_envelope_candidate_contract_v2_70"] = manifest["common_envelope_candidate_contract"]
    manifest["common_envelope_candidate_footprints_v2_70"] = manifest["common_envelope_candidate_footprints"]
    manifest["coverage_boundary_contract"] = {
        "role": output_doc["role"],
        "source": cfg["output_json"],
        "source_sha256": sha256(output),
        "default_visible": True,
        "layer_count": 3,
        "interior_support_holes": "FILLED",
        "target_membership_modified": False,
        "roofer_inputs_modified": False,
        "scientific_verdict": None,
    }
    manifest["coverage_boundary_layers"] = layers
    manifest["common_envelope_candidate_contract"] = {
        "role": "DISPLAY_ONLY_FOOTPRINT_PLUS_2M_FULLY_INSIDE_OUTER_COMMON_ENVELOPE",
        "candidate_count": len(candidate_rows),
        "candidate_footprint_buffer_m": margin,
        "default_visible": True,
        "existing_epaired_72_default_visible": False,
        "not_a_frozen_target_membership": True,
        "target_membership_modified": False,
        "roofer_inputs_modified": False,
        "scientific_verdict": None,
    }
    manifest["common_envelope_candidate_footprints"] = candidate_rows
    manifest["roofer_inputs_modified"] = False
    manifest["scientific_verdict"] = None
    atomic_json(manifest_path, manifest)

    app_path = viewer / "app.js"
    app = app_path.read_text()
    if app.count("후보70") != 6 or app.count("후보 70동") != 1 or app.count("candidate-footprints-70") != 1:
        raise RuntimeError("app candidate70 copy drift")
    app = app.replace("후보70", "후보76").replace("후보 70동", "후보 76동").replace("candidate-footprints-70", "candidate-footprints-76")
    atomic_text(app_path, app)
    index_path = viewer / "index.html"
    index = index_path.read_text()
    if index.count("후보70") != 2:
        raise RuntimeError("index candidate70 copy drift")
    index = index.replace("후보70", "후보76").replace(
        "app.js?v=e1e6-20260811-smooth-common-envelope-v2",
        "app.js?v=e1e6-20260811-outer-only-common-envelope-v3",
    )
    atomic_text(index_path, index)

    after = {name: record(viewer / name) for name in cfg["expected_before"]}
    TASK.mkdir(parents=True)
    receipt = {
        "schema": "jointbuildgs.p2.viewer_8876_outer_only_common_envelope.receipt.v3",
        "task_id": cfg["task_id"],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "config": record(CONFIG),
        "script": record(SOURCE),
        "source_envelopes_v2": source_record,
        "shared_footprints_199": footprints_record,
        "output": record(output, cfg["output_json"]),
        "interior_holes_filled": {layer["id"]: layer["interior_holes_filled_for_domain_envelope"] for layer in layers},
        "no_margin_fully_contained_count": len(no_margin),
        "buffered_candidate_count": len(candidates),
        "existing_epaired_target_count_preserved": 72,
        "viewer_before": before,
        "viewer_after": after,
        "display_only": True,
        "target_membership_modified": False,
        "roofer_inputs_modified": False,
        "scientific_verdict": None,
    }
    atomic_json(TASK / "receipt.json", receipt)
    print(json.dumps({"task_id": cfg["task_id"], "no_margin": len(no_margin), "buffered_candidates": len(candidates), "holes_filled": receipt["interior_holes_filled"], "viewer_after": after}, indent=2))


if __name__ == "__main__":
    main()
