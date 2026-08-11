#!/usr/bin/env python3
"""Publish one final rectilinear common boundary and its no-margin footprint set."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
from typing import Any

from shapely.affinity import rotate
from shapely.geometry import Polygon, box, mapping, shape
from shapely.ops import unary_union


REPO = Path("/workspace/JointBuildGS")
AR = Path("/artifacts/JointBuildGS")
CONFIG = REPO / "configs/p2/viewer_8876_final_rectilinear_common_v4/viewer.json"
SOURCE = REPO / "scripts/p2/viewer_8876_final_rectilinear_common_v4/build.py"
TASK = AR / "phase-payloads/p2/viewer_8876_final_rectilinear_common_v4/P2-VIEWER-8876-FINAL-RECTILINEAR-COMMON-v4"


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
        raise RuntimeError(f"no polygon in {geometry.geom_type}")
    return max(polygons, key=lambda polygon: polygon.area)


def dominant_angle_deg(polygon: Polygon) -> float:
    coordinates = list(polygon.minimum_rotated_rectangle.exterior.coords)
    edges = []
    for index in range(4):
        dx = coordinates[index + 1][0] - coordinates[index][0]
        dy = coordinates[index + 1][1] - coordinates[index][1]
        edges.append((math.hypot(dx, dy), math.degrees(math.atan2(dy, dx))))
    angle = max(edges)[1]
    if angle > 90:
        angle -= 180
    if angle <= -90:
        angle += 180
    return angle


def rectilinearize(polygon: Polygon, cell_size: float, opening_radius: float) -> tuple[Polygon, dict[str, Any]]:
    angle = dominant_angle_deg(polygon)
    origin = polygon.centroid
    rotated = rotate(polygon, -angle, origin=origin)
    minx, miny, maxx, maxy = rotated.bounds
    x0 = math.floor(minx / cell_size) * cell_size
    y0 = math.floor(miny / cell_size) * cell_size
    nx = int(math.ceil((maxx - x0) / cell_size))
    ny = int(math.ceil((maxy - y0) / cell_size))
    cells = []
    for row in range(ny):
        for col in range(nx):
            cell = box(
                x0 + col * cell_size,
                y0 + row * cell_size,
                x0 + (col + 1) * cell_size,
                y0 + (row + 1) * cell_size,
            )
            if rotated.covers(cell):
                cells.append(cell)
    if not cells:
        raise RuntimeError("rectilinearization retained no cells")
    union = main_polygon(unary_union(cells))
    union = Polygon(union.exterior)
    opened = union.buffer(-opening_radius, join_style=2).buffer(opening_radius, join_style=2)
    opened = Polygon(main_polygon(opened).exterior)
    coordinates = list(opened.exterior.coords)
    for start, end in zip(coordinates, coordinates[1:]):
        dx, dy = abs(end[0] - start[0]), abs(end[1] - start[1])
        if dx > 1e-7 and dy > 1e-7:
            raise RuntimeError("rectilinear boundary contains a non-orthogonal segment")
    world = rotate(opened, angle, origin=origin)
    return world, {
        "dominant_angle_deg_from_easting": angle,
        "grid_origin_rotated_xy": [x0, y0],
        "grid_shape_yx": [ny, nx],
        "fully_covered_cell_count": len(cells),
        "rotated_boundary_vertex_count": len(coordinates),
        "area_m2": float(world.area),
    }


def footprint_row(feature: dict[str, Any], cfg: dict[str, Any], shift: list[float]) -> dict[str, Any]:
    geometry = shape(feature["geometry"])
    polygons = [geometry] if geometry.geom_type == "Polygon" else list(geometry.geoms)
    rings = []
    for polygon in polygons:
        for ring in [polygon.exterior, *polygon.interiors]:
            rings.append([[round(float(x) - shift[0], 3), round(float(y) - shift[1], 3)] for x, y in ring.coords])
    return {
        "stable_id": feature["properties"]["stable_id"],
        "rings_local_xy": rings,
        "z_local": float(cfg["candidate_display_z_local_m"]),
        "color": cfg["candidate_color"],
        "membership": "DISPLAY_ONLY_FINAL_RECTILINEAR_COMMON_FULL_FOOTPRINT",
        "display_style": "FINAL_CANDIDATE_OUTLINE",
    }


def replace_once(body: str, old: str, new: str, label: str) -> str:
    if body.count(old) != 1:
        raise RuntimeError(f"expected one {label}, found {body.count(old)}")
    return body.replace(old, new)


def main() -> None:
    cfg = json.loads(CONFIG.read_text())
    viewer = AR / cfg["viewer_root"]
    output = viewer / cfg["output_json"]
    if TASK.exists() or output.exists():
        raise RuntimeError("add-once output already exists")
    before = {name: verify(viewer / name, expected) for name, expected in cfg["expected_before"].items()}
    source_path = AR / cfg["source_outer_envelope_v3"]["path"]
    footprints_path = AR / cfg["shared_footprints_199"]["path"]
    source_record = verify(source_path, cfg["source_outer_envelope_v3"])
    footprints_record = verify(footprints_path, cfg["shared_footprints_199"])
    source = json.loads(source_path.read_text())
    common = shape(source["common_outer_envelope_geojson"])
    method = cfg["rectilinearization"]
    final_boundary, stats = rectilinearize(
        common,
        float(method["cell_size_m"]),
        float(method["orthogonal_opening_radius_m"]),
    )
    features = json.loads(footprints_path.read_text())["features"]
    candidates = [feature for feature in features if final_boundary.covers(shape(feature["geometry"]))]
    if len(candidates) != 71:
        raise RuntimeError(f"final no-margin candidate count drift: {len(candidates)}")
    shift = [float(value) for value in cfg["world_shift_xyz"]]
    world_ring = [[[round(float(x), 3), round(float(y), 3)] for x, y in final_boundary.exterior.coords]]
    local_ring = [[[round(x - shift[0], 3), round(y - shift[1], 3)] for x, y in world_ring[0]]]
    boundary_layer = {
        "id": "FINAL_RECTILINEAR_COMMON",
        "label_ko": "최종 E1/E2 직교 공통영역",
        "color": cfg["boundary_color"],
        "display_z_local_m": float(cfg["boundary_display_z_local_m"]),
        "outline_width_m": 1.2,
        "rings_world_xy": world_ring,
        "rings_local_xy": local_ring,
        "ring_count": 1,
        "area_m2": stats["area_m2"],
        "display_only": True,
    }
    candidate_rows = [footprint_row(feature, cfg, shift) for feature in candidates]
    output_doc = {
        "schema": "jointbuildgs.p2.viewer_8876.final_rectilinear_common.v4",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "method": method,
        "rectilinearization_stats": stats,
        "final_boundary_geojson": mapping(final_boundary),
        "boundary_layer": boundary_layer,
        "candidate_count": len(candidate_rows),
        "candidate_ids": [row["stable_id"] for row in candidate_rows],
        "candidate_footprints": candidate_rows,
        "source_outer_envelope_v3": source_record,
        "shared_footprints_199": footprints_record,
        "role": "DISPLAY_ONLY_FINAL_RECTILINEAR_COMMON_AND_NO_MARGIN_CANDIDATES",
        "target_membership_modified": False,
        "roofer_inputs_modified": False,
        "scientific_verdict": None,
    }
    atomic_json(output, output_doc)

    manifest_path = viewer / "viewer_manifest.json"
    manifest = json.loads(manifest_path.read_text())
    if len(manifest["target_building_footprints"]) != 72:
        raise RuntimeError("existing target72 drift")
    manifest["outer_common_boundary_contract_v3"] = manifest["coverage_boundary_contract"]
    manifest["outer_common_boundary_layers_v3"] = manifest["coverage_boundary_layers"]
    manifest["outer_common_candidate_contract_v3"] = manifest["common_envelope_candidate_contract"]
    manifest["outer_common_candidate_footprints_v3"] = manifest["common_envelope_candidate_footprints"]
    manifest["coverage_boundary_contract"] = {
        "role": output_doc["role"],
        "source": cfg["output_json"],
        "source_sha256": sha256(output),
        "default_visible": True,
        "layer_count": 1,
        "rectilinearization": method,
        "target_membership_modified": False,
        "roofer_inputs_modified": False,
        "scientific_verdict": None,
    }
    manifest["coverage_boundary_layers"] = [boundary_layer]
    manifest["common_envelope_candidate_contract"] = {
        "role": "DISPLAY_ONLY_FOOTPRINT_FULLY_INSIDE_FINAL_RECTILINEAR_COMMON_NO_BUFFER",
        "candidate_count": len(candidate_rows),
        "candidate_footprint_buffer_m": 0.0,
        "default_visible": True,
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
    old_target_handler = """document.getElementById('toggleTargetFootprints').addEventListener('click', event => {\n  targetFootprintsVisible = !targetFootprintsVisible;\n  for (const viewer of viewers) viewer.targetFootprints.visible = targetFootprintsVisible;\n  event.currentTarget.textContent = `대상72 footprint ${targetFootprintsVisible ? 'ON' : 'OFF'}`;\n  info.textContent = targetFootprintsVisible\n    ? '현재 영상 MVS와 독립 UAS LiDAR 지원이 함께 있는 E_paired 72동만 표시'\n    : 'E_paired 72동 footprint 숨김';\n});\n"""
    app = replace_once(app, old_target_handler, "", "legacy target72 handler")
    app = replace_once(app, "'common-envelope-candidate-footprints-76'", "'final-rectilinear-common-candidates-71'", "candidate group name")
    app = app.replace("공통외곽 후보76", "최종후보71").replace("진단 후보 76동", "최종 후보 71동").replace("후보76 ON", "최종후보71 ON")
    app = app.replace("footprint+2m가 완전히 들어오는", "footprint 자체가 완전히 들어오는")
    app = app.replace("E1/E2 주외곽과 공통외곽 top view", "최종 직교 공통영역 top view")
    app = app.replace("주 관측외곽", "최종경계")
    app = app.replace("파랑 E1 LiDAR 주외곽 · 빨강 E2 MVS 주외곽 · 초록 공통 유효외곽", "초록 최종 직교 공통영역")
    app = replace_once(
        app,
        "document.getElementById('toggleTargetFootprints').textContent = `기존대상72 ${targetFootprintsVisible ? 'ON' : 'OFF'}`;\n",
        "",
        "legacy target72 initial text",
    )
    app = app.replace(
        "E1/E2 매끈한 주외곽과 공통외곽 ON · 최종후보71 ON · 기존72 OFF",
        "최종 직교 공통영역 ON · 최종후보71 ON · 여유폭 0m",
    )
    atomic_text(app_path, app)

    index_path = viewer / "index.html"
    index = index_path.read_text()
    index = replace_once(index, '<button id="toggleTargetFootprints" type="button">기존대상72 OFF</button>', "", "legacy target72 button")
    index = index.replace("공통외곽 후보76", "최종후보71").replace("주 관측외곽", "최종경계")
    index = replace_once(
        index,
        '<span class="legend"><span><i style="background:#3b82f6"></i>E1 주외곽</span><span><i style="background:#ef4444"></i>E2 주외곽</span><span><i style="background:#22c55e"></i>공통외곽</span><span><i style="background:#00e5ff"></i>후보76</span><span><i style="background:#64748b"></i>기존72</span>',
        '<span class="legend"><span><i style="background:#22c55e"></i>최종 직교 공통영역</span><span><i style="background:#00e5ff"></i>최종후보71</span>',
        "final-only legend",
    )
    index = index.replace(
        "app.js?v=e1e6-20260811-outer-only-common-envelope-v3",
        "app.js?v=e1e6-20260811-final-rectilinear-common-v4",
    )
    atomic_text(index_path, index)

    after = {name: record(viewer / name) for name in cfg["expected_before"]}
    TASK.mkdir(parents=True)
    receipt = {
        "schema": "jointbuildgs.p2.viewer_8876_final_rectilinear_common.receipt.v4",
        "task_id": cfg["task_id"],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "config": record(CONFIG),
        "script": record(SOURCE),
        "source_outer_envelope_v3": source_record,
        "shared_footprints_199": footprints_record,
        "output": record(output, cfg["output_json"]),
        "rectilinearization_stats": stats,
        "candidate_count": len(candidate_rows),
        "candidate_buffer_m": 0.0,
        "existing_epaired_target_count_preserved_but_not_active_display": 72,
        "viewer_before": before,
        "viewer_after": after,
        "display_only": True,
        "target_membership_modified": False,
        "roofer_inputs_modified": False,
        "scientific_verdict": None,
    }
    atomic_json(TASK / "receipt.json", receipt)
    print(json.dumps({"task_id": cfg["task_id"], "candidate_count": len(candidate_rows), "buffer_m": 0.0, "stats": stats, "viewer_after": after}, indent=2))


if __name__ == "__main__":
    main()
