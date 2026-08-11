#!/usr/bin/env python3
"""Replace raw occupied-cell contours with smooth main E1/E2 coverage envelopes."""
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
CONFIG = REPO / "configs/p2/viewer_8876_smooth_common_envelope_v2/viewer.json"
SOURCE = REPO / "scripts/p2/viewer_8876_smooth_common_envelope_v2/build.py"
TASK = AR / "phase-payloads/p2/viewer_8876_smooth_common_envelope_v2/P2-VIEWER-8876-SMOOTH-COMMON-ENVELOPE-v2"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def file_record(path: Path, relative_path: str | None = None) -> dict[str, Any]:
    return {"path": relative_path or str(path), "bytes": path.stat().st_size, "sha256": sha256(path)}


def verify(path: Path, expected: dict[str, Any] | str) -> dict[str, Any]:
    if not path.is_file() or path.is_symlink():
        raise RuntimeError(f"missing or invalid input: {path}")
    record = file_record(path)
    expected_hash = expected if isinstance(expected, str) else expected["sha256"]
    expected_bytes = None if isinstance(expected, str) else int(expected["bytes"])
    if expected_bytes is not None and record["bytes"] != expected_bytes:
        raise RuntimeError(f"byte drift: {path}: {record['bytes']} != {expected_bytes}")
    if record["sha256"] != expected_hash:
        raise RuntimeError(f"hash drift: {path}: {record['sha256']} != {expected_hash}")
    return record


def atomic_text(path: Path, body: str) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(body)
    os.replace(temporary, path)


def atomic_json(path: Path, body: object) -> None:
    atomic_text(path, json.dumps(body, indent=2, sort_keys=True) + "\n")


def main_polygon(geometry: Any) -> Polygon:
    if geometry.geom_type == "Polygon":
        return geometry
    polygons = [part for part in geometry.geoms if part.geom_type == "Polygon"]
    if not polygons:
        raise RuntimeError(f"geometry has no polygon component: {geometry.geom_type}")
    return max(polygons, key=lambda polygon: polygon.area)


def source_outer(layer: dict[str, Any]) -> Polygon:
    polygons: list[Polygon] = []
    for ring in layer["rings_world_xy"]:
        polygon = Polygon(ring)
        if not polygon.is_valid:
            polygon = polygon.buffer(0)
        if polygon.is_empty:
            continue
        polygons.append(main_polygon(polygon))
    if not polygons:
        raise RuntimeError(f"layer has no valid polygon rings: {layer['id']}")
    return max(polygons, key=lambda polygon: polygon.area)


def smooth_main(polygon: Polygon, closing_radius: float, simplify_tolerance: float) -> Polygon:
    closed = polygon.buffer(closing_radius).buffer(-closing_radius)
    simplified = closed.simplify(simplify_tolerance, preserve_topology=True)
    result = main_polygon(simplified)
    if not result.is_valid:
        result = main_polygon(result.buffer(0))
    return result


def polygon_rings(polygon: Polygon, shift: list[float]) -> tuple[list[list[list[float]]], list[list[list[float]]]]:
    rings = [polygon.exterior, *polygon.interiors]
    world = [
        [[round(float(x), 3), round(float(y), 3)] for x, y in ring.coords]
        for ring in rings
    ]
    local = [
        [[round(x - shift[0], 3), round(y - shift[1], 3)] for x, y in ring]
        for ring in world
    ]
    return world, local


def display_layer(layer_id: str, polygon: Polygon, cfg: dict[str, Any], shift: list[float]) -> dict[str, Any]:
    world, local = polygon_rings(polygon, shift)
    spec = cfg["layers"][layer_id]
    return {
        "id": layer_id,
        "label_ko": spec["label_ko"],
        "color": spec["color"],
        "display_z_local_m": spec["display_z_local_m"],
        "outline_width_m": 1.15 if layer_id == "COMMON_MAIN_ENVELOPE" else 0.8,
        "rings_world_xy": world,
        "rings_local_xy": local,
        "ring_count": len(local),
        "area_m2": float(polygon.area),
        "display_only": True,
    }


def feature_rings_local(feature: dict[str, Any], shift: list[float]) -> list[list[list[float]]]:
    geometry = shape(feature["geometry"])
    polygons = [geometry] if geometry.geom_type == "Polygon" else list(geometry.geoms)
    rings: list[list[list[float]]] = []
    for polygon in polygons:
        for ring in [polygon.exterior, *polygon.interiors]:
            rings.append([
                [round(float(x) - shift[0], 3), round(float(y) - shift[1], 3)]
                for x, y in ring.coords
            ])
    return rings


def replace_once(body: str, old: str, new: str, label: str) -> str:
    count = body.count(old)
    if count != 1:
        raise RuntimeError(f"expected one {label} replacement, found {count}")
    return body.replace(old, new)


def main() -> None:
    cfg = json.loads(CONFIG.read_text())
    viewer = AR / cfg["viewer_root"]
    if TASK.exists():
        raise RuntimeError(f"add-once task exists: {TASK}")
    output_path = viewer / cfg["output_json"]
    if output_path.exists():
        raise RuntimeError(f"add-once output exists: {output_path}")
    before = {name: verify(viewer / name, expected) for name, expected in cfg["expected_before"].items()}
    source_path = AR / cfg["source_coverage_boundaries"]["path"]
    footprints_path = AR / cfg["shared_footprints_199"]["path"]
    source_record = verify(source_path, cfg["source_coverage_boundaries"])
    footprints_record = verify(footprints_path, cfg["shared_footprints_199"])

    source = json.loads(source_path.read_text())
    source_layers = {layer["id"]: layer for layer in source["layers"]}
    closing_radius = float(cfg["envelope"]["closing_radius_m"])
    simplify_tolerance = float(cfg["envelope"]["simplify_tolerance_m"])
    margin = float(cfg["envelope"]["candidate_footprint_buffer_m"])
    shift = [float(value) for value in cfg["world_shift_xyz"]]
    e1 = smooth_main(source_outer(source_layers["E1_RAW_LIDAR"]), closing_radius, simplify_tolerance)
    e2 = smooth_main(source_outer(source_layers["E2_DENSE_MVS"]), closing_radius, simplify_tolerance)
    common = main_polygon(e1.intersection(e2))
    layers = [
        display_layer("E1_MAIN_ENVELOPE", e1, cfg, shift),
        display_layer("E2_MAIN_ENVELOPE", e2, cfg, shift),
        display_layer("COMMON_MAIN_ENVELOPE", common, cfg, shift),
    ]

    footprints = json.loads(footprints_path.read_text())["features"]
    if len(footprints) != 199:
        raise RuntimeError(f"expected 199 footprints, found {len(footprints)}")
    no_margin_ids = [feature["properties"]["stable_id"] for feature in footprints if common.covers(shape(feature["geometry"]))]
    candidates = [
        feature for feature in footprints
        if common.covers(shape(feature["geometry"]).buffer(margin))
    ]
    if len(no_margin_ids) != 78 or len(candidates) != 70:
        raise RuntimeError(f"bound envelope count drift: no_margin={len(no_margin_ids)}, margin={len(candidates)}")
    candidate_rows = [
        {
            "stable_id": feature["properties"]["stable_id"],
            "rings_local_xy": feature_rings_local(feature, shift),
            "z_local": float(cfg["candidate_display_z_local_m"]),
            "color": cfg["candidate_color"],
            "membership": "DISPLAY_ONLY_COMMON_ENVELOPE_CANDIDATE_2M",
            "display_style": "COMMON_ENVELOPE_CANDIDATE_OUTLINE",
        }
        for feature in candidates
    ]
    envelope_doc = {
        "schema": "jointbuildgs.p2.viewer_8876.coverage_envelopes.v2",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "method": cfg["envelope"],
        "layers": layers,
        "common_envelope_geojson": mapping(common),
        "no_margin_fully_contained_count": len(no_margin_ids),
        "no_margin_fully_contained_ids": no_margin_ids,
        "buffered_candidate_count": len(candidate_rows),
        "buffered_candidate_ids": [row["stable_id"] for row in candidate_rows],
        "candidate_footprints": candidate_rows,
        "source_occupied_cell_boundaries": source_record,
        "shared_footprints_199": footprints_record,
        "role": "DISPLAY_ONLY_MAIN_SENSOR_ENVELOPE_AND_CANDIDATE_DIAGNOSTIC",
        "target_membership_modified": False,
        "roofer_inputs_modified": False,
        "scientific_verdict": None,
    }
    atomic_json(output_path, envelope_doc)

    manifest_path = viewer / "viewer_manifest.json"
    manifest = json.loads(manifest_path.read_text())
    existing_target_ids = [row["stable_id"] for row in manifest["target_building_footprints"]]
    if len(existing_target_ids) != 72:
        raise RuntimeError("existing E_paired target display count drift")
    manifest["raw_occupied_cell_coverage_boundary_contract_v1"] = manifest["coverage_boundary_contract"]
    manifest["raw_occupied_cell_coverage_boundary_layers_v1"] = manifest["coverage_boundary_layers"]
    manifest["coverage_boundary_contract"] = {
        "role": envelope_doc["role"],
        "source": cfg["output_json"],
        "source_sha256": sha256(output_path),
        "default_visible": True,
        "layer_count": 3,
        "component_rule": cfg["envelope"]["component_rule"],
        "closing_radius_m": closing_radius,
        "simplify_tolerance_m": simplify_tolerance,
        "target_membership_modified": False,
        "roofer_inputs_modified": False,
        "scientific_verdict": None,
    }
    manifest["coverage_boundary_layers"] = layers
    manifest["common_envelope_candidate_contract"] = {
        "role": "DISPLAY_ONLY_FOOTPRINT_PLUS_2M_FULLY_INSIDE_COMMON_MAIN_ENVELOPE",
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
    app = replace_once(app, "let targetFootprintsVisible = true;", "let targetFootprintsVisible = false;\nlet envelopeCandidateFootprintsVisible = true;", "footprint visibility states")
    app = replace_once(
        app,
        "function targetFootprintOverlay(rows) {\n  const group = new THREE.Group();\n  group.name = 'target-building-footprints-58-only';\n  const width = Number(manifest.target_building_footprint_contract?.outline_width_m || 0.38);",
        "function targetFootprintOverlay(rows, groupName = 'target-building-footprints-current-selection', widthOverride = null) {\n  const group = new THREE.Group();\n  group.name = groupName;\n  const width = widthOverride === null\n    ? Number(manifest.target_building_footprint_contract?.outline_width_m || 0.38)\n    : Number(widthOverride);",
        "generic footprint overlay",
    )
    app = replace_once(
        app,
        "  scene.add(targetFootprints);\n  const coverageBoundaries",
        "  scene.add(targetFootprints);\n  const envelopeCandidateFootprints = targetFootprintOverlay(\n    manifest.common_envelope_candidate_footprints,\n    'common-envelope-candidate-footprints-70',\n    0.68,\n  );\n  envelopeCandidateFootprints.visible = envelopeCandidateFootprintsVisible;\n  scene.add(envelopeCandidateFootprints);\n  const coverageBoundaries",
        "candidate footprint creation",
    )
    app = replace_once(
        app,
        "surface, targetFootprints, coverageBoundaries, realCandidates, syntheticRegions, spec};",
        "surface, targetFootprints, envelopeCandidateFootprints, coverageBoundaries, realCandidates, syntheticRegions, spec};",
        "candidate viewer member",
    )
    candidate_handler = r'''
document.getElementById('toggleEnvelopeCandidates').addEventListener('click', event => {
  envelopeCandidateFootprintsVisible = !envelopeCandidateFootprintsVisible;
  for (const viewer of viewers) viewer.envelopeCandidateFootprints.visible = envelopeCandidateFootprintsVisible;
  event.currentTarget.textContent = `공통외곽 후보70 ${envelopeCandidateFootprintsVisible ? 'ON' : 'OFF'}`;
  info.textContent = envelopeCandidateFootprintsVisible
    ? 'E1/E2 공통 주외곽 안에 footprint+2m가 완전히 들어오는 진단 후보 70동'
    : '공통외곽 후보70 footprint 숨김';
});
document.getElementById('showCoverageTop').addEventListener('click', () => {
  orbit.target.set(0, 5, -34);
  orbit.distance = 650;
  orbit.yaw = -Math.PI / 2;
  orbit.pitch = 1.48;
  info.textContent = 'E1/E2 주외곽과 공통외곽 top view · 후보70 ON';
});
'''
    app = replace_once(
        app,
        "\ndocument.getElementById('toggleCoverageBoundaries').addEventListener",
        candidate_handler + "\ndocument.getElementById('toggleCoverageBoundaries').addEventListener",
        "candidate toggle and top-view handlers",
    )
    app = replace_once(
        app,
        "  event.currentTarget.textContent = `관측영역 ${coverageBoundariesVisible ? 'ON' : 'OFF'}`;\n  info.textContent = coverageBoundariesVisible\n    ? '파랑 E1 LiDAR · 주황 영상 다중시점 · 빨강 E2 dense MVS · 초록 엄격 공통지원'",
        "  event.currentTarget.textContent = `주 관측외곽 ${coverageBoundariesVisible ? 'ON' : 'OFF'}`;\n  info.textContent = coverageBoundariesVisible\n    ? '파랑 E1 LiDAR 주외곽 · 빨강 E2 MVS 주외곽 · 초록 공통 유효외곽'",
        "smooth boundary toggle copy",
    )
    app = replace_once(
        app,
        "document.getElementById('toggleTargetFootprints').textContent = `대상72 footprint ${targetFootprintsVisible ? 'ON' : 'OFF'}`;\ndocument.getElementById('toggleCoverageBoundaries').textContent = `관측영역 ${coverageBoundariesVisible ? 'ON' : 'OFF'}`;",
        "document.getElementById('toggleTargetFootprints').textContent = `기존대상72 ${targetFootprintsVisible ? 'ON' : 'OFF'}`;\ndocument.getElementById('toggleEnvelopeCandidates').textContent = `공통외곽 후보70 ${envelopeCandidateFootprintsVisible ? 'ON' : 'OFF'}`;\ndocument.getElementById('toggleCoverageBoundaries').textContent = `주 관측외곽 ${coverageBoundariesVisible ? 'ON' : 'OFF'}`;",
        "initial overlay button text",
    )
    app = replace_once(
        app,
        "'표면 mesh 로드 완료 · full-source 불규칙 관측영역 4종 ON · 대상 membership 미변경'",
        "'표면 mesh 로드 완료 · E1/E2 매끈한 주외곽과 공통외곽 ON · 후보70 ON · 기존72 OFF'",
        "surface initial status",
    )
    app = replace_once(
        app,
        "'8개 패널 로드 완료 · full-source 불규칙 관측영역 4종 ON · 대상 membership 미변경'",
        "'8개 패널 로드 완료 · E1/E2 매끈한 주외곽과 공통외곽 ON · 후보70 ON · 기존72 OFF'",
        "default initial status",
    )
    atomic_text(app_path, app)

    index_path = viewer / "index.html"
    index = index_path.read_text()
    index = replace_once(
        index,
        '<button id="toggleTargetFootprints" type="button">대상72 footprint ON</button><button id="toggleCoverageBoundaries" type="button">관측영역 ON</button>',
        '<button id="toggleTargetFootprints" type="button">기존대상72 OFF</button><button id="toggleEnvelopeCandidates" type="button">공통외곽 후보70 ON</button><button id="toggleCoverageBoundaries" type="button">주 관측외곽 ON</button><button id="showCoverageTop" type="button">영역 top</button>',
        "candidate and top buttons",
    )
    index = replace_once(
        index,
        '<span class="legend"><span><i style="background:#3b82f6"></i>E1 LiDAR</span><span><i style="background:#f59e0b"></i>영상 3+경사1+</span><span><i style="background:#ef4444"></i>E2 dense MVS</span><span><i style="background:#22c55e"></i>엄격 공통</span><span><i style="background:#00e5ff"></i>현 표시 대상72</span>',
        '<span class="legend"><span><i style="background:#3b82f6"></i>E1 주외곽</span><span><i style="background:#ef4444"></i>E2 주외곽</span><span><i style="background:#22c55e"></i>공통외곽</span><span><i style="background:#00e5ff"></i>후보70</span><span><i style="background:#64748b"></i>기존72</span>',
        "smooth envelope legend",
    )
    index = replace_once(
        index,
        "app.js?v=e1e6-20260810-full-source-coverage-boundaries-v1",
        "app.js?v=e1e6-20260811-smooth-common-envelope-v2",
        "app cache token",
    )
    atomic_text(index_path, index)

    after = {name: file_record(viewer / name) for name in cfg["expected_before"]}
    TASK.mkdir(parents=True)
    receipt = {
        "schema": "jointbuildgs.p2.viewer_8876_smooth_common_envelope.receipt.v2",
        "task_id": cfg["task_id"],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "config": file_record(CONFIG),
        "script": file_record(SOURCE),
        "source_coverage_boundaries": source_record,
        "shared_footprints_199": footprints_record,
        "output": file_record(output_path, cfg["output_json"]),
        "method": cfg["envelope"],
        "layer_summary": [{"id": layer["id"], "area_m2": layer["area_m2"], "ring_count": layer["ring_count"]} for layer in layers],
        "no_margin_fully_contained_count": len(no_margin_ids),
        "buffered_candidate_count": len(candidate_rows),
        "existing_epaired_target_count_preserved": len(existing_target_ids),
        "viewer_before": before,
        "viewer_after": after,
        "display_only": True,
        "target_membership_modified": False,
        "roofer_inputs_modified": False,
        "scientific_verdict": None,
    }
    atomic_json(TASK / "receipt.json", receipt)
    print(json.dumps({"task_id": cfg["task_id"], "no_margin": len(no_margin_ids), "buffered_candidates": len(candidate_rows), "layers": receipt["layer_summary"], "viewer_after": after}, indent=2))


if __name__ == "__main__":
    main()
