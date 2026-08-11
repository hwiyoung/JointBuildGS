#!/usr/bin/env python3
"""Build the interactive 119-building multi-view diagnostic gallery."""

from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path
from typing import Any, Iterable, Mapping


TRACKS = {
    "MVS_RAW_GEOMETRY_SUPPORT": ("MVS raw support", "--viz-series-1"),
    "GEOMETRY_REFERENCE_ACCURACY": ("Reference accuracy", "--viz-series-2"),
    "GEOMETRY_INPUT_FIT": ("Input-fit geometry", "--viz-series-3"),
    "ROOFER_ASSEMBLY_TOPOLOGY": ("Assembly/topology", "--viz-series-4"),
    "CLASSIFICATION_SUPPORT": ("Classification support", "--viz-series-5"),
    "CLASSIFICATION_CLIPPING": ("Classification/clipping", "--viz-series-6"),
}

REASONS = {
    "MVS_RAW_GEOMETRY_SUPPORT": "footprint 안의 raw MVS 지원이 90% 미만이라 dense geometry와 시점·texture 지원부터 보완해야 합니다.",
    "GEOMETRY_REFERENCE_ACCURACY": "no-clip LoD2는 생성됐지만 current-UAS 기준 candidate 정확도 band를 통과하지 못했습니다.",
    "GEOMETRY_INPUT_FIT": "LoD2 면적은 복구됐지만 분류 입력점과의 RMSE가 2m 이상이라 잔차 원인 분해가 필요합니다.",
    "ROOFER_ASSEMBLY_TOPOLOGY": "no-clip LoD2가 존재하지만 val3dity가 invalid라 shell 조립과 topology를 고쳐야 합니다.",
    "CLASSIFICATION_SUPPORT": "raw 지원은 충분하지만 class-6 지원이 크게 줄고 Roofer point cloud가 unusable 상태입니다.",
    "CLASSIFICATION_CLIPPING": "raw 지원은 충분하고 LoD2도 생성되지만 class-6 손실과 terrain clipping 민감성이 함께 남았습니다.",
}


def number(value: str | None) -> float | None:
    return round(float(value), 5) if value else None


def iter_surfaces(geometry: Mapping[str, Any]) -> Iterable[tuple[list[Any], Any]]:
    boundaries = geometry.get("boundaries") or []
    values = (geometry.get("semantics") or {}).get("values") or []
    kind = geometry.get("type")
    if kind in ("MultiSurface", "CompositeSurface"):
        yield from zip(boundaries, values)
    elif kind == "Solid":
        for shell, shell_values in zip(boundaries, values):
            yield from zip(shell, shell_values)
    elif kind in ("MultiSolid", "CompositeSolid"):
        for solid, solid_values in zip(boundaries, values):
            for shell, shell_values in zip(solid, solid_values):
                yield from zip(shell, shell_values)


def lod22_surfaces(path: Path) -> dict[str, dict[str, Any]]:
    """Read compact RoofSurface and WallSurface meshes from CityJSONSeq."""
    transform: Mapping[str, Any] | None = None
    output: dict[str, dict[str, Any]] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        if record.get("type") == "CityJSON":
            transform = record["transform"]
            continue
        if record.get("type") != "CityJSONFeature" or transform is None:
            raise RuntimeError("invalid CityJSONSeq inheritance")
        scale, translate = transform["scale"], transform["translate"]
        vertices = [
            [
                float(value[0]) * scale[0] + translate[0],
                float(value[1]) * scale[1] + translate[1],
                float(value[2]) * scale[2] + translate[2],
            ]
            for value in record["vertices"]
        ]
        objects = record.get("CityObjects") or {}
        buildings = [key for key, value in objects.items() if value.get("type") == "Building"]
        if len(buildings) != 1:
            raise RuntimeError("CityJSONFeature building identity is ambiguous")
        stable_id = buildings[0]
        compact_vertices: list[list[float]] = []
        vertex_map: dict[tuple[float, float, float], int] = {}
        compact_surfaces: list[list[Any]] = []
        for city_object in objects.values():
            for geometry in city_object.get("geometry") or []:
                if str(geometry.get("lod")) != "2.2":
                    continue
                semantics = (geometry.get("semantics") or {}).get("surfaces") or []
                semantic_types = {
                    index: surface.get("type")
                    for index, surface in enumerate(semantics)
                    if isinstance(surface, Mapping)
                }
                for rings, semantic in iter_surfaces(geometry):
                    surface_type = semantic_types.get(semantic)
                    if surface_type not in ("RoofSurface", "WallSurface"):
                        continue
                    compact_rings: list[list[int]] = []
                    for raw_ring in rings:
                        raw_indices = [int(index) for index in raw_ring]
                        if len(raw_indices) >= 2 and raw_indices[0] == raw_indices[-1]:
                            raw_indices = raw_indices[:-1]
                        if len(raw_indices) < 3:
                            continue
                        compact_ring: list[int] = []
                        for index in raw_indices:
                            point = tuple(vertices[index])
                            if point not in vertex_map:
                                vertex_map[point] = len(compact_vertices)
                                compact_vertices.append(list(point))
                            compact_ring.append(vertex_map[point])
                        compact_rings.append(compact_ring)
                    if compact_rings:
                        compact_surfaces.append(["r" if surface_type == "RoofSurface" else "w", compact_rings])
        output[stable_id] = {"v": compact_vertices, "s": compact_surfaces}
    return output


def footprint_rings(path: Path) -> dict[str, list[list[list[float]]]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    output: dict[str, list[list[list[float]]]] = {}
    for feature in data["features"]:
        stable_id = feature["properties"]["stable_id"]
        geometry = feature["geometry"]
        coordinates = geometry["coordinates"]
        polygons = [coordinates] if geometry["type"] == "Polygon" else coordinates
        output[stable_id] = [
            [[float(x), float(y)] for x, y, *_ in ring[:-1] if ring]
            for polygon in polygons for ring in polygon
        ]
    return output


def sampled_class6_points(
    path: Path,
    footprint_path: Path,
    selected_ids: set[str],
    max_points_per_building: int = 180,
) -> dict[str, dict[str, Any]]:
    """Extract a deterministic display sample of the Roofer class-6 input."""
    import laspy
    import numpy as np
    from shapely import contains_xy
    from shapely.geometry import shape

    geojson = json.loads(footprint_path.read_text(encoding="utf-8"))
    geometries = {
        str(feature["properties"]["stable_id"]): shape(feature["geometry"])
        for feature in geojson["features"]
        if str(feature["properties"]["stable_id"]) in selected_ids
    }
    samples: dict[str, list[list[float]]] = {stable_id: [] for stable_id in geometries}
    min_x = min(geometry.bounds[0] for geometry in geometries.values())
    min_y = min(geometry.bounds[1] for geometry in geometries.values())
    max_x = max(geometry.bounds[2] for geometry in geometries.values())
    max_y = max(geometry.bounds[3] for geometry in geometries.values())
    with laspy.open(path) as reader:
        for chunk in reader.chunk_iterator(2_000_000):
            classes = np.asarray(chunk.classification)
            x, y, z = np.asarray(chunk.x), np.asarray(chunk.y), np.asarray(chunk.z)
            scene_keep = (
                (classes == 6) & (x >= min_x) & (x <= max_x) & (y >= min_y) & (y <= max_y)
            )
            if not np.any(scene_keep):
                continue
            sx, sy, sz = x[scene_keep], y[scene_keep], z[scene_keep]
            for stable_id, geometry in geometries.items():
                gx0, gy0, gx1, gy1 = geometry.bounds
                bbox = (sx >= gx0) & (sx <= gx1) & (sy >= gy0) & (sy <= gy1)
                if not np.any(bbox):
                    continue
                bx, by, bz = sx[bbox], sy[bbox], sz[bbox]
                inside = contains_xy(geometry, bx, by)
                if np.any(inside):
                    samples[stable_id].extend(
                        [float(px), float(py), float(pz)]
                        for px, py, pz in zip(bx[inside], by[inside], bz[inside])
                    )
    output: dict[str, dict[str, Any]] = {}
    for stable_id, points in samples.items():
        total = len(points)
        if total > max_points_per_building:
            indices = np.linspace(0, total - 1, max_points_per_building, dtype=np.int64)
            points = [points[int(index)] for index in indices]
        output[stable_id] = {"points": points, "total": total}
    return output


def sampled_current_uas_cells(
    path: Path,
    selected_ids: set[str],
    max_points_per_building: int = 180,
) -> dict[str, dict[str, Any]]:
    """Read a deterministic display sample of evaluation-only UAS top cells."""
    import numpy as np

    cells: dict[str, list[list[float]]] = {stable_id: [] for stable_id in selected_ids}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        stable_id = str(row["stable_id"])
        if stable_id in cells:
            cells[stable_id].append([
                float(row["cell_x"]), float(row["cell_y"]), float(row["top_z"])
            ])
    output: dict[str, dict[str, Any]] = {}
    for stable_id, points in cells.items():
        total = len(points)
        if total > max_points_per_building:
            indices = np.linspace(0, total - 1, max_points_per_building, dtype=np.int64)
            points = [points[int(index)] for index in indices]
        output[stable_id] = {"points": points, "total": total}
    return output


def lod2_reference_roofs(
    paths: list[Path],
    selected_ids: set[str],
    z_shift_m: float,
) -> dict[str, dict[str, Any]]:
    """Load evaluation-only LoD2 RoofSurfaces into the compact viewer schema."""
    from scripts.p2.utarget199_presentation_v5.render import load_references

    references = load_references(paths, sorted(selected_ids))
    output: dict[str, dict[str, Any]] = {}
    for stable_id, reference in references.items():
        vertices: list[list[float]] = []
        vertex_map: dict[tuple[float, float, float], int] = {}
        surfaces: list[list[Any]] = []
        for raw_ring in reference.roof_rings_xyz:
            ring_points = raw_ring[:-1] if len(raw_ring) >= 2 and all(raw_ring[0] == raw_ring[-1]) else raw_ring
            ring: list[int] = []
            for raw_point in ring_points:
                point = (float(raw_point[0]), float(raw_point[1]), float(raw_point[2]) + z_shift_m)
                if point not in vertex_map:
                    vertex_map[point] = len(vertices)
                    vertices.append(list(point))
                ring.append(vertex_map[point])
            if len(ring) >= 3:
                surfaces.append(["r", [ring]])
        output[stable_id] = {"v": vertices, "s": surfaces}
    return output


def local_geometry(
    footprint: list[list[list[float]]],
    clip: Mapping[str, Any],
    no_clip: Mapping[str, Any],
    input_points: Mapping[str, Any],
    lidar_points: Mapping[str, Any],
    lod2_reference: Mapping[str, Any],
) -> tuple[
    list[list[list[float]]], dict[str, Any], dict[str, Any], dict[str, Any],
    list[list[float]], list[list[float]], float,
]:
    footprint_points = [point for ring in footprint for point in ring]
    all_xy = footprint_points or [point[:2] for arm in (clip, no_clip) for point in arm.get("v", [])]
    origin_x = sum(point[0] for point in all_xy) / max(len(all_xy), 1)
    origin_y = sum(point[1] for point in all_xy) / max(len(all_xy), 1)
    all_vertices = [point for arm in (clip, no_clip, lod2_reference) for point in arm.get("v", [])]
    support_vertices = [point for group in (input_points, lidar_points) for point in group.get("points", [])]
    origin_z = min((point[2] for point in all_vertices + support_vertices), default=0.0)

    local_fp = [
        [[round(point[0] - origin_x, 2), round(point[1] - origin_y, 2)] for point in ring]
        for ring in footprint
    ]

    def local_arm(arm: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "v": [
                [round(point[0] - origin_x, 2), round(point[1] - origin_y, 2), round(point[2] - origin_z, 2)]
                for point in arm.get("v", [])
            ],
            "s": arm.get("s", []),
        }

    centered = [point for ring in local_fp for point in ring]
    if len(centered) >= 2:
        cxx = sum(point[0] * point[0] for point in centered) / len(centered)
        cyy = sum(point[1] * point[1] for point in centered) / len(centered)
        cxy = sum(point[0] * point[1] for point in centered) / len(centered)
        theta = 0.5 * math.atan2(2 * cxy, cxx - cyy)
    else:
        theta = 0.0
    local_points = [
        [round(point[0] - origin_x, 2), round(point[1] - origin_y, 2), round(point[2] - origin_z, 2)]
        for point in input_points.get("points", [])
    ]
    local_lidar = [
        [round(point[0] - origin_x, 2), round(point[1] - origin_y, 2), round(point[2] - origin_z, 2)]
        for point in lidar_points.get("points", [])
    ]
    return (
        local_fp, local_arm(clip), local_arm(no_clip), local_arm(lod2_reference),
        local_points, local_lidar, round(theta, 6),
    )


def build_fragment(
    rows: list[dict[str, str]],
    clip_rows: Mapping[str, Mapping[str, str]],
    clip: dict[str, Any],
    no_clip: dict[str, Any],
    footprints: dict[str, Any],
    input_points: Mapping[str, Mapping[str, Any]],
    lidar_points: Mapping[str, Mapping[str, Any]],
    lod2_references: Mapping[str, Mapping[str, Any]],
) -> str:
    selected = [
        row for row in rows
        if row["fully_inside_roofer_aoi"] == "True" and row["primary_improvement_track"] in TRACKS
    ]
    if len(selected) != 119:
        raise RuntimeError(f"expected 119 improvement buildings, got {len(selected)}")
    payload = []
    for row in selected:
        stable_id = row["stable_id"]
        diagnostic = clip_rows[stable_id]
        point_record = input_points.get(stable_id, {"points": [], "total": 0})
        lidar_record = lidar_points.get(stable_id, {"points": [], "total": 0})
        fp, ct, nc, lod2_ref, points, lidar, theta = local_geometry(
            footprints.get(stable_id, []),
            clip.get(stable_id, {"v": [], "s": []}),
            no_clip.get(stable_id, {"v": [], "s": []}),
            point_record,
            lidar_record,
            lod2_references.get(stable_id, {"v": [], "s": []}),
        )
        no_cov = number(row["no_clip_lod22_xy_coverage"])
        delta = number(row["clip_coverage_delta"])
        payload.append({
            "id": stable_id.removeprefix("DEBY_LOD2_"),
            "track": row["primary_improvement_track"],
            "reason": REASONS[row["primary_improvement_track"]],
            "flags": [value for value in row["improvement_flags"].split(";") if value != "CURRENT_REFERENCE_ASSESSMENT_GAP"],
            "raw": number(row["all_point_coverage_0p5m"]),
            "c6": number(row["class6_coverage_0p5m"]),
            "clipCov": round((no_cov or 0) - (delta or 0), 5),
            "noCov": no_cov,
            "clipParts": number(row["clip_true_building_part_count"]),
            "noParts": number(row["no_clip_building_part_count"]),
            "clipInputRmse": number(diagnostic["clip_true_rf_rmse_lod22"]),
            "noInputRmse": number(diagnostic["clip_false_rf_rmse_lod22"]),
            "refCoverage": number(row["current_uas_vertical_coverage"]),
            "refMae": number(row["current_uas_height_mae_m"]),
            "refSurfaceRmse": number(row["current_uas_surface_rmse_m"]),
            "refRmsz": number(row["current_uas_rmsz_m"]),
            "refRmsxy": number(row["current_uas_rmsxy_m"]),
            "refP95": number(row["current_uas_surface_p95_m"]),
            "refPass": row["current_uas_accuracy_candidate"] or None,
            "fp": fp,
            "theta": theta,
            "clip": ct,
            "noClip": nc,
            "points": points,
            "pointTotal": int(point_record.get("total", 0)),
            "lidar": lidar,
            "lidarTotal": int(lidar_record.get("total", 0)),
            "lod2Ref": lod2_ref,
            "temporalStatus": row["temporal_reference_status"],
            "referenceEligible": row["current_uas_reference_eligible"] == "True",
        })
    payload.sort(key=lambda row: (list(TRACKS).index(row["track"]), row["id"]))
    data = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    track_data = json.dumps({key: {"label": value[0], "color": value[1]} for key, value in TRACKS.items()}, separators=(",", ":"))
    return f'''<div id="c2-improvement-vis">
  <div class="viz-controls">
    <label class="form-label" for="c2-track-filter">개선 트랙
      <select class="form-select" id="c2-track-filter">
        <option value="ALL">전체 119동</option>
        {''.join(f'<option value="{key}">{label}</option>' for key, (label, _) in TRACKS.items())}
      </select>
    </label>
    <span class="text-muted" id="c2-visible-count">119동</span>
  </div>
  <section class="card" aria-live="polite">
    <div class="c2-selected-head">
      <div><strong id="c2-building-id"></strong> <span class="viz-badge" id="c2-track-label"></span></div>
      <div class="text-muted" id="c2-reason"></div>
    </div>
    <div class="viz-controls c2-view-controls">
      <button type="button" class="btn" data-view="top">Top</button>
      <button type="button" class="btn" data-view="oblique">Oblique</button>
      <button type="button" class="btn" data-view="principal">Principal</button>
      <label class="form-check"><input class="form-check-input" id="c2-show-points" type="checkbox" checked><span class="form-check-label">class-6 입력점</span></label>
      <label class="form-check"><input class="form-check-input" id="c2-show-lidar" type="checkbox" checked><span class="form-check-label">UAS LiDAR cells</span></label>
      <label class="form-check"><input class="form-check-input" id="c2-show-lod2-ref" type="checkbox" checked><span class="form-check-label">2022 LoD2 roof</span></label>
      <label class="form-check"><input class="form-check-input" id="c2-show-clip" type="checkbox" checked><span class="form-check-label">clip=true</span></label>
      <label class="form-check"><input class="form-check-input" id="c2-show-no-clip" type="checkbox" checked><span class="form-check-label">no-clip</span></label>
    </div>
    <div class="c2-view-note text-small text-muted">드래그: 회전 · 휠: 확대/축소 · 각 점군은 최대 180개 표본 · LiDAR/LoD2는 평가 전용</div>
    <svg id="c2-viewer" viewBox="0 0 160 92" role="img" aria-label="선택 건물 입력점, Current-UAS LiDAR top cells, 2022 LoD2 RoofSurface와 clip/no-clip 결과의 인터랙티브 3D 비교"></svg>
    <div class="c2-view-caption text-small" id="c2-view-caption"></div>
    <div class="c2-support" id="c2-support"></div>
    <div class="c2-error-grid">
      <div class="c2-error-card">
        <div class="c2-error-title">Roofer input-fit <span>class-6 입력점 기준</span></div>
        <div id="c2-input-errors"></div>
      </div>
      <div class="c2-error-card">
        <div class="c2-error-title">Current-UAS 평가 <span>no-clip LoD2 기준</span></div>
        <div id="c2-reference-errors"></div>
      </div>
    </div>
    <div class="text-small text-muted c2-reference-note">두 RMSE 묶음의 기준점 집합은 다릅니다. input-fit은 Roofer에 들어간 class-6, Current-UAS는 독립 평가 기준입니다.</div>
    <div class="text-small" id="c2-flags"></div>
  </section>
  <div class="c2-grid" id="c2-building-grid" aria-label="개선 대상 건물 선택"></div>
  <div class="c2-legend" id="c2-legend"></div>
</div>
<style>
#c2-improvement-vis {{ color:var(--foreground); width:100%; }}
#c2-improvement-vis .c2-selected-head {{ display:grid; gap:.35rem; margin-bottom:.65rem; }}
#c2-improvement-vis .c2-view-note {{ margin-bottom:.45rem; }}
#c2-improvement-vis .c2-view-controls {{ margin-bottom:.35rem; }}
#c2-improvement-vis #c2-viewer {{ display:block; width:100%; height:430px; background:color-mix(in srgb,var(--muted) 30%,transparent); cursor:grab; touch-action:none; }}
#c2-improvement-vis #c2-viewer:active {{ cursor:grabbing; }}
#c2-improvement-vis .c2-view-caption {{ display:flex; flex-wrap:wrap; gap:.8rem; margin-top:.35rem; }}
#c2-improvement-vis .c2-layer-key::before {{ content:'●'; color:var(--layer-color); margin-right:.25rem; }}
#c2-improvement-vis .c2-footprint {{ fill:none; stroke:var(--muted-foreground); stroke-width:1; stroke-dasharray:3 2; vector-effect:non-scaling-stroke; }}
#c2-improvement-vis .c2-roof,.c2-wall {{ vector-effect:non-scaling-stroke; stroke-linejoin:round; }}
#c2-improvement-vis .c2-roof.c2-clip {{ fill:color-mix(in srgb,var(--viz-series-2) 25%,transparent); stroke:var(--viz-series-2); stroke-width:1.05; }}
#c2-improvement-vis .c2-wall.c2-clip {{ fill:color-mix(in srgb,var(--viz-series-2) 10%,transparent); stroke:color-mix(in srgb,var(--viz-series-2) 62%,var(--muted-foreground)); stroke-width:.75; }}
#c2-improvement-vis .c2-roof.c2-no-clip {{ fill:color-mix(in srgb,var(--viz-series-1) 25%,transparent); stroke:var(--viz-series-1); stroke-width:1.05; }}
#c2-improvement-vis .c2-wall.c2-no-clip {{ fill:color-mix(in srgb,var(--viz-series-1) 10%,transparent); stroke:color-mix(in srgb,var(--viz-series-1) 62%,var(--muted-foreground)); stroke-width:.75; }}
#c2-improvement-vis .c2-input-point {{ fill:var(--viz-series-3); stroke:var(--background); stroke-width:.25; vector-effect:non-scaling-stroke; }}
#c2-improvement-vis .c2-lidar-point {{ fill:var(--viz-series-4); stroke:var(--background); stroke-width:.3; vector-effect:non-scaling-stroke; }}
#c2-improvement-vis .c2-roof.c2-lod2-ref {{ fill:color-mix(in srgb,var(--viz-series-5) 8%,transparent); stroke:var(--viz-series-5); stroke-width:1.2; stroke-dasharray:2 1; }}
#c2-improvement-vis .c2-empty {{ fill:var(--muted-foreground); text-anchor:middle; dominant-baseline:middle; }}
#c2-improvement-vis .c2-support {{ display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:.45rem; margin:.75rem 0; }}
#c2-improvement-vis .c2-support-card,.c2-error-card {{ border:1px solid var(--border); padding:.55rem; min-width:0; }}
#c2-improvement-vis .c2-support-track,.c2-error-track {{ height:.38rem; background:var(--muted); overflow:hidden; margin-top:.25rem; }}
#c2-improvement-vis .c2-support-fill {{ height:100%; background:var(--viz-series-1); }}
#c2-improvement-vis .c2-error-grid {{ display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:.65rem; }}
#c2-improvement-vis .c2-error-title {{ font-weight:500; margin-bottom:.45rem; }}
#c2-improvement-vis .c2-error-title span {{ font-size:.72rem; color:var(--muted-foreground); font-weight:400; }}
#c2-improvement-vis .c2-error-row {{ display:grid; grid-template-columns:minmax(82px,.65fr) minmax(0,1fr) auto; gap:.4rem; align-items:center; margin:.3rem 0; font-size:.78rem; }}
#c2-improvement-vis .c2-error-fill {{ height:100%; background:var(--viz-series-2); }}
#c2-improvement-vis .c2-error-fill.ref {{ background:var(--viz-series-1); }}
#c2-improvement-vis .c2-reference-note {{ margin:.55rem 0; }}
#c2-improvement-vis .c2-grid {{ display:grid; grid-template-columns:repeat(auto-fill,minmax(72px,1fr)); gap:.35rem; margin-top:1rem; }}
#c2-improvement-vis .c2-grid .btn {{ min-width:0; }}
#c2-improvement-vis .c2-grid .is-selected {{ outline:2px solid var(--ring); outline-offset:1px; }}
#c2-improvement-vis .c2-legend {{ display:flex; flex-wrap:wrap; gap:.75rem; margin-top:.75rem; }}
#c2-improvement-vis .c2-swatch {{ display:inline-block; width:.7rem; height:.7rem; margin-right:.3rem; background:var(--track-color); }}
@media (max-width:650px) {{
  #c2-improvement-vis #c2-viewer {{ height:320px; }}
  #c2-improvement-vis .c2-support {{ grid-template-columns:repeat(2,minmax(0,1fr)); }}
  #c2-improvement-vis .c2-error-grid {{ grid-template-columns:1fr; }}
}}
</style>
<script>
(() => {{
  const root=document.getElementById('c2-improvement-vis');
  const data={data};
  const tracks={track_data};
  const filter=root.querySelector('#c2-track-filter');
  const grid=root.querySelector('#c2-building-grid');
  const ns='http://www.w3.org/2000/svg';
  const viewer=root.querySelector('#c2-viewer');
  const showPoints=root.querySelector('#c2-show-points');
  const showLidar=root.querySelector('#c2-show-lidar');
  const showLod2Ref=root.querySelector('#c2-show-lod2-ref');
  const showClip=root.querySelector('#c2-show-clip');
  const showNoClip=root.querySelector('#c2-show-no-clip');
  let selected=data.find(d=>d.id==='4906982')||data[0];
  let camera={{yaw:0,elevation:Math.PI/5,zoom:1,preset:'oblique'}};
  let drag=null;
  const pct=v=>v==null?'—':`${{(v*100).toFixed(v>=.995?2:1)}}%`;
  const meters=v=>v==null?'—':`${{v.toFixed(3)}} m`;
  function project3d(p) {{
    const c=Math.cos(camera.yaw),s=Math.sin(camera.yaw),x=c*p[0]+s*p[1],y=-s*p[0]+c*p[1],z=p[2]||0;
    const se=Math.sin(camera.elevation),ce=Math.cos(camera.elevation);
    return [x,-(se*y+ce*z),ce*y-se*z];
  }}
  function bounds() {{
    const projected=[];
    if(showClip.checked) selected.clip.v.forEach(p=>projected.push(project3d(p)));
    if(showNoClip.checked) selected.noClip.v.forEach(p=>projected.push(project3d(p)));
    if(showLod2Ref.checked) selected.lod2Ref.v.forEach(p=>projected.push(project3d(p)));
    if(showPoints.checked) selected.points.forEach(p=>projected.push(project3d(p)));
    if(showLidar.checked) selected.lidar.forEach(p=>projected.push(project3d(p)));
    selected.fp.flat().forEach(p=>projected.push(project3d([p[0],p[1],0])));
    if(!projected.length) return {{midX:0,midY:0,factor:1}};
    const minX=Math.min(...projected.map(p=>p[0])),maxX=Math.max(...projected.map(p=>p[0])),minY=Math.min(...projected.map(p=>p[1])),maxY=Math.max(...projected.map(p=>p[1]));
    return {{midX:(minX+maxX)/2,midY:(minY+maxY)/2,factor:Math.min(148/Math.max(maxX-minX,1),82/Math.max(maxY-minY,1))*.9*camera.zoom}};
  }}
  function screen(point,frame) {{return [80+(point[0]-frame.midX)*frame.factor,46+(point[1]-frame.midY)*frame.factor];}}
  function pathFromRings(rings,vertices,frame) {{
    return rings.map(ring=>{{const points=ring.map(index=>screen(project3d(vertices[index]),frame));return points.length?`M${{points.map(p=>`${{p[0].toFixed(2)}},${{p[1].toFixed(2)}}`).join('L')}}Z`:'';}}).join('');
  }}
  function footprintPath(frame) {{
    return selected.fp.map(ring=>{{const points=ring.map(p=>screen(project3d([p[0],p[1],0]),frame));return points.length?`M${{points.map(v=>`${{v[0].toFixed(2)}},${{v[1].toFixed(2)}}`).join('L')}}Z`:'';}}).join('');
  }}
  function drawViewer() {{
    viewer.replaceChildren();
    const frame=bounds();
    const fp=document.createElementNS(ns,'path');fp.setAttribute('d',footprintPath(frame));fp.setAttribute('class','c2-footprint');viewer.appendChild(fp);
    const items=[];
    if(showClip.checked) selected.clip.s.forEach(surface=>items.push({{type:'surface',arm:'clip',kind:surface[0],rings:surface[1],vertices:selected.clip.v,depth:surface[1][0].reduce((sum,index)=>sum+project3d(selected.clip.v[index])[2],0)/surface[1][0].length}}));
    if(showNoClip.checked) selected.noClip.s.forEach(surface=>items.push({{type:'surface',arm:'no-clip',kind:surface[0],rings:surface[1],vertices:selected.noClip.v,depth:surface[1][0].reduce((sum,index)=>sum+project3d(selected.noClip.v[index])[2],0)/surface[1][0].length}}));
    if(showLod2Ref.checked) selected.lod2Ref.s.forEach(surface=>items.push({{type:'surface',arm:'lod2-ref',kind:surface[0],rings:surface[1],vertices:selected.lod2Ref.v,depth:surface[1][0].reduce((sum,index)=>sum+project3d(selected.lod2Ref.v[index])[2],0)/surface[1][0].length}}));
    if(showPoints.checked) selected.points.forEach(point=>items.push({{type:'point',point,depth:project3d(point)[2]}}));
    if(showLidar.checked) selected.lidar.forEach(point=>items.push({{type:'lidar',point,depth:project3d(point)[2]}}));
    items.sort((a,b)=>a.depth-b.depth).forEach(item=>{{
      if(item.type==='surface') {{const path=document.createElementNS(ns,'path');path.setAttribute('d',pathFromRings(item.rings,item.vertices,frame));path.setAttribute('class',`${{item.kind==='r'?'c2-roof':'c2-wall'}} c2-${{item.arm}}`);path.setAttribute('fill-rule','evenodd');viewer.appendChild(path);}}
      else {{const p=screen(project3d(item.point),frame),circle=document.createElementNS(ns,'circle');circle.setAttribute('cx',p[0].toFixed(2));circle.setAttribute('cy',p[1].toFixed(2));circle.setAttribute('r',item.type==='lidar'?'0.85':'0.65');circle.setAttribute('class',item.type==='lidar'?'c2-lidar-point':'c2-input-point');viewer.appendChild(circle);}}
    }});
    const lidarState=selected.lidarTotal?`${{selected.lidar.length.toLocaleString()}} / ${{selected.lidarTotal.toLocaleString()}} cells · ${{selected.referenceEligible?'평가 포함':'평가 제외'}}`:'coverage 없음';
    root.querySelector('#c2-view-caption').innerHTML=`<span class="c2-layer-key" style="--layer-color:var(--viz-series-3)">class-6 ${{selected.points.length.toLocaleString()}} / ${{selected.pointTotal.toLocaleString()}}점</span><span class="c2-layer-key" style="--layer-color:var(--viz-series-4)">UAS LiDAR ${{lidarState}}</span><span class="c2-layer-key" style="--layer-color:var(--viz-series-5)">2022 LoD2 RoofSurface +45.7m · ${{selected.temporalStatus}}</span><span>clip ${{pct(selected.clipCov)}} / ${{selected.clipParts??'—'}} parts</span><span>no-clip ${{pct(selected.noCov)}} / ${{selected.noParts??'—'}} parts</span>`;
  }}
  function setView(name) {{
    camera.preset=name;camera.zoom=1;
    if(name==='top') {{camera.yaw=0;camera.elevation=Math.PI/2;}}
    else if(name==='principal') {{camera.yaw=selected.theta;camera.elevation=0;}}
    else {{camera.yaw=selected.theta+.55;camera.elevation=Math.PI/5;}}
    root.querySelectorAll('[data-view]').forEach(button=>button.setAttribute('aria-pressed',String(button.dataset.view===name)));
    drawViewer();
  }}
  function supportCard(label,value) {{return `<div class="c2-support-card"><div class="text-small text-muted">${{label}}</div><div>${{pct(value)}}</div><div class="c2-support-track"><div class="c2-support-fill" style="width:${{value==null?0:Math.max(0,Math.min(100,value*100))}}%"></div></div></div>`;}}
  function errorRows(items,reference=false) {{
    const values=items.map(item=>item[1]).filter(v=>v!=null),max=Math.max(1,...values);
    return items.map(item=>`<div class="c2-error-row"><span>${{item[0]}}</span><div class="c2-error-track"><div class="c2-error-fill${{reference?' ref':''}}" style="width:${{item[1]==null?0:item[1]/max*100}}%"></div></div><strong>${{meters(item[1])}}</strong></div>`).join('');
  }}
  function renderSelected() {{
    const meta=tracks[selected.track];
    root.querySelector('#c2-building-id').textContent=selected.id;
    const badge=root.querySelector('#c2-track-label');badge.textContent=meta.label;
    root.querySelector('#c2-reason').textContent=selected.reason;
    setView('oblique');
    root.querySelector('#c2-support').innerHTML=[supportCard('raw MVS 지원',selected.raw),supportCard('class-6 지원',selected.c6),supportCard('clip 면적',selected.clipCov),supportCard('no-clip 면적',selected.noCov)].join('');
    root.querySelector('#c2-input-errors').innerHTML=errorRows([['clip=true',selected.clipInputRmse],['no-clip',selected.noInputRmse]]);
    const pass=selected.refPass==null?'평가 제외':selected.refPass==='True'?'candidate 통과':'candidate 실패';
    root.querySelector('#c2-reference-errors').innerHTML=errorRows([['surface RMSE',selected.refSurfaceRmse],['RMSZ',selected.refRmsz],['RMSXY',selected.refRmsxy],['P95',selected.refP95]],true)+`<div class="text-small text-muted">수직 coverage ${{pct(selected.refCoverage)}} · 높이 MAE ${{meters(selected.refMae)}} · ${{pass}}</div>`;
    root.querySelector('#c2-flags').textContent=selected.flags.length?`플래그: ${{selected.flags.join(' · ')}}`:'추가 플래그 없음';
    grid.querySelectorAll('button').forEach(button=>button.classList.toggle('is-selected',button.dataset.id===selected.id));
  }}
  function renderGrid() {{
    const visible=data.filter(d=>filter.value==='ALL'||d.track===filter.value);
    root.querySelector('#c2-visible-count').textContent=`${{visible.length}}동`;
    grid.replaceChildren(...visible.map(d=>{{const b=document.createElement('button');b.type='button';b.className='btn viz-tile';b.dataset.id=d.id;b.textContent=d.id;b.setAttribute('aria-label',`${{d.id}}, ${{tracks[d.track].label}}, ${{d.flags.join(', ')}}`);b.style.background=`color-mix(in srgb,var(${{tracks[d.track].color}}) 14%,transparent)`;b.addEventListener('click',()=>{{selected=d;renderSelected();}});return b;}}));
    if(!visible.includes(selected)) selected=visible[0];
    renderSelected();
  }}
  root.querySelector('#c2-legend').innerHTML=Object.values(tracks).map(t=>`<span class="text-small"><span class="c2-swatch" style="--track-color:var(${{t.color}})"></span>${{t.label}}</span>`).join('');
  root.querySelectorAll('[data-view]').forEach(button=>button.addEventListener('click',()=>setView(button.dataset.view)));
  [showPoints,showLidar,showLod2Ref,showClip,showNoClip].forEach(control=>control.addEventListener('change',drawViewer));
  viewer.addEventListener('pointerdown',event=>{{drag={{x:event.clientX,y:event.clientY}};viewer.setPointerCapture(event.pointerId);}});
  viewer.addEventListener('pointermove',event=>{{if(!drag)return;const dx=event.clientX-drag.x,dy=event.clientY-drag.y;drag={{x:event.clientX,y:event.clientY}};camera.yaw+=dx*.01;camera.elevation=Math.max(0,Math.min(Math.PI/2,camera.elevation-dy*.008));camera.preset='free';root.querySelectorAll('[data-view]').forEach(button=>button.setAttribute('aria-pressed','false'));drawViewer();}});
  viewer.addEventListener('pointerup',event=>{{drag=null;viewer.releasePointerCapture(event.pointerId);}});
  viewer.addEventListener('pointercancel',()=>{{drag=null;}});
  viewer.addEventListener('wheel',event=>{{event.preventDefault();camera.zoom=Math.max(.55,Math.min(4,camera.zoom*Math.exp(-event.deltaY*.001)));drawViewer();}},{{passive:false}});
  filter.addEventListener('change',renderGrid);
  renderGrid();
}})();
</script>
'''


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--census", type=Path, required=True)
    parser.add_argument("--clip-census", type=Path, required=True)
    parser.add_argument("--clip-cityjsonseq", type=Path, required=True)
    parser.add_argument("--no-clip-cityjsonseq", type=Path, required=True)
    parser.add_argument("--footprints", type=Path, required=True)
    parser.add_argument("--classified-pointcloud", type=Path, required=True)
    parser.add_argument("--current-uas-cells", type=Path, required=True)
    parser.add_argument("--lod2-reference", type=Path, action="append", required=True)
    parser.add_argument("--lod2-z-shift-m", type=float, default=45.7)
    parser.add_argument("--inline-output", type=Path, required=True)
    parser.add_argument("--artifact-output", type=Path, required=True)
    args = parser.parse_args()
    rows = list(csv.DictReader(args.census.open(encoding="utf-8")))
    clip_rows = {row["stable_id"]: row for row in csv.DictReader(args.clip_census.open(encoding="utf-8"))}
    selected_ids = {
        row["stable_id"] for row in rows
        if row["fully_inside_roofer_aoi"] == "True" and row["primary_improvement_track"] in TRACKS
    }
    input_points = sampled_class6_points(args.classified_pointcloud, args.footprints, selected_ids)
    lidar_points = sampled_current_uas_cells(args.current_uas_cells, selected_ids)
    lod2_references = lod2_reference_roofs(args.lod2_reference, selected_ids, args.lod2_z_shift_m)
    fragment = build_fragment(
        rows,
        clip_rows,
        lod22_surfaces(args.clip_cityjsonseq),
        lod22_surfaces(args.no_clip_cityjsonseq),
        footprint_rings(args.footprints),
        input_points,
        lidar_points,
        lod2_references,
    )
    if len(fragment.encode("utf-8")) >= 2_000_000:
        raise RuntimeError("inline visualization exceeds 2 MB")
    for path in (args.inline_output, args.artifact_output):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(fragment, encoding="utf-8")
    print(json.dumps({"status": "COMPLETE", "buildings": 119, "bytes": len(fragment.encode("utf-8")), "inline": args.inline_output.as_posix(), "artifact": args.artifact_output.as_posix()}, ensure_ascii=False))


if __name__ == "__main__":
    main()
