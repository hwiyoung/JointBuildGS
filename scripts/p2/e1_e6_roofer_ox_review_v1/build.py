#!/usr/bin/env python3
"""Build the dedicated E1-E6 building-level Roofer O/X review viewer."""
from __future__ import annotations

import argparse
from collections import defaultdict
import json
import os
from pathlib import Path
import shutil
from typing import Any

import numpy as np
import laspy

from scripts.p2.c1_c2_shared_footprint_199_v1.run import (
    canonical_json_bytes,
    exact_file,
    file_record,
    write_new,
)
from scripts.p2.c1_c2_shared_footprint_199_v3.build_cloudcompare_review10 import (
    lod22_triangles,
    triangles_obj,
)
from scripts.p2.c2_c3_rendered_depth_shared_footprint_199_v1.build_web import (
    _copy_base,
    collect_building_crops,
    deterministic_coordinate_sample,
    transform_app,
    transform_index,
    write_c3_ply,
)


REPO = Path(__file__).resolve().parents[3]
CONFIG_PATH = REPO / "configs/p2/e1_e6_roofer_ox_review_v1/run_v1.json"
E3_KEY = "E3_GS_image"
CONDITIONS = ("E3", "E4", "E5", "E6")


def load_config(path: Path) -> dict[str, Any]:
    config = json.loads(path.read_text(encoding="utf-8"))
    if config.get("schema") != "jointbuildgs.p2.e1_e6_roofer_ox_review.v1":
        raise RuntimeError("config schema drifted")
    if config.get("status") != "USER_APPROVED_FOR_EXECUTION":
        raise RuntimeError("viewer build is not approved")
    expected = {
        "E1": "AVAILABLE_CURRENT_UAS_LIDAR",
        "E2": "AVAILABLE_CURRENT_IMAGE_MVS",
        "E3": "AVAILABLE_NEW_30K_IMAGE_ONLY_GS",
        "E4": "AVAILABLE_EXISTING_LEGACY_BASE",
        "E5": "AVAILABLE_EXISTING_LEGACY_BASE",
        "E6": "AVAILABLE_EXISTING_LEGACY_BASE",
    }
    if config.get("conditions") != expected:
        raise RuntimeError("condition availability drifted")
    contract = config["roofer_ox_contract"]
    if contract["authority"] != "HUMAN_REVIEW" or contract["technical_status_role"] != "ADVISORY_ONLY":
        raise RuntimeError("O/X authority drifted")
    if contract["missing_or_unrun_is_x"] is not False:
        raise RuntimeError("missing/unrun must remain distinct from X")
    if config.get("official_PASS_usable", "missing") is not None or config.get("scientific_verdict", "missing") is not None:
        raise RuntimeError("verdict fields must remain null")
    return config


def _replace_function(text: str, name: str, next_name: str, replacement: str) -> str:
    start = text.index(f"function {name}(")
    end = text.index(f"function {next_name}(", start)
    return text[:start] + replacement.rstrip() + "\n\n" + text[end:]


def _reason_options(method: str) -> str:
    return (
        f'<select id="{method}Reason" aria-label="{method} X 사유">'
        '<option value="">X 사유 선택(선택)</option>'
        '<option value="NO_OUTPUT">출력 없음</option>'
        '<option value="LOW_FOOTPRINT_COVERAGE">footprint coverage 부족</option>'
        '<option value="GROSS_ROOF_FORM_ERROR">명백한 지붕 형태 오류</option>'
        '<option value="INVALID_GEOMETRY">invalid geometry</option>'
        '<option value="OTHER">기타</option></select>'
        f'<input class="review-reason-note" id="{method}ReasonNote" type="text" maxlength="160" '
        f'aria-label="{method} 성공 또는 실패 이유" placeholder="성공/실패 이유를 짧게 입력">'
    )


def collect_basic_building_crops(
    source: Path,
    bboxes: dict[str, tuple[float, float, float, float]],
    voxel_m: float,
    cap: int,
) -> tuple[dict[str, np.ndarray], dict[str, int]]:
    """Crop legacy classified LAZ while preserving its exact Roofer-input classes."""
    chunks: dict[str, list[np.ndarray]] = defaultdict(list)
    raw_counts = {stable_id: 0 for stable_id in bboxes}
    tile_m = 32.0
    tile_to_ids: dict[tuple[int, int], list[str]] = defaultdict(list)
    for stable_id, (x0, y0, x1, y1) in bboxes.items():
        for tx in range(int(np.floor(x0 / tile_m)), int(np.floor(x1 / tile_m)) + 1):
            for ty in range(int(np.floor(y0 / tile_m)), int(np.floor(y1 / tile_m)) + 1):
                tile_to_ids[(tx, ty)].append(stable_id)
    with laspy.open(source) as reader:
        dimensions = set(reader.header.point_format.dimension_names)
        has_rgb = {"red", "green", "blue"}.issubset(dimensions)
        for points in reader.chunk_iterator(1_000_000):
            xyz = np.column_stack((np.asarray(points.x), np.asarray(points.y), np.asarray(points.z))).astype(np.float64)
            classification = np.asarray(points.classification, dtype=np.uint8)
            if not set(np.unique(classification)).issubset({1, 2, 6}):
                raise RuntimeError("unexpected legacy classified value")
            if has_rgb:
                raw_rgb = np.column_stack((np.asarray(points.red), np.asarray(points.green), np.asarray(points.blue))).astype(np.float64)
                rgb = np.rint(np.clip(raw_rgb / 257.0, 0, 255)).astype(np.uint8)
                zero_rgb = np.all(raw_rgb == 0, axis=1)
                fallback = np.where(classification[:, None] == 2, np.asarray([[145, 145, 145]]), np.asarray([[139, 92, 246]])).astype(np.uint8)
                rgb[zero_rgb] = fallback[zero_rgb]
            else:
                rgb = np.where(classification[:, None] == 2, np.asarray([[145, 145, 145]]), np.asarray([[139, 92, 246]])).astype(np.uint8)
            tile_xy = np.floor(xyz[:, :2] / tile_m).astype(np.int64)
            order = np.lexsort((tile_xy[:, 1], tile_xy[:, 0]))
            sorted_tiles = tile_xy[order]
            boundaries = np.flatnonzero(np.any(sorted_tiles[1:] != sorted_tiles[:-1], axis=1)) + 1
            candidate: dict[str, list[np.ndarray]] = defaultdict(list)
            for positions in np.split(order, boundaries):
                if len(positions):
                    for stable_id in tile_to_ids.get(tuple(int(value) for value in tile_xy[positions[0]]), ()):
                        candidate[stable_id].append(positions)
            for stable_id, parts in candidate.items():
                indices = np.concatenate(parts)
                x0, y0, x1, y1 = bboxes[stable_id]
                inside = (xyz[indices, 0] >= x0) & (xyz[indices, 0] <= x1) & (xyz[indices, 1] >= y0) & (xyz[indices, 1] <= y1)
                selected = indices[inside]
                if len(selected):
                    raw_counts[stable_id] += len(selected)
                    audit_zeros = np.zeros((len(selected), 6), dtype=np.float64)
                    chunks[stable_id].append(np.column_stack((xyz[selected], classification[selected], rgb[selected], audit_zeros)))
    result = {}
    for stable_id in bboxes:
        rows = np.concatenate(chunks[stable_id]) if chunks[stable_id] else np.empty((0, 13), dtype=np.float64)
        result[stable_id] = deterministic_coordinate_sample(rows, voxel_m, cap)
    return result, raw_counts


def load_expanded_obj_triangles(path: Path) -> np.ndarray:
    """Load the frozen comparison LoD2 OBJ as local-coordinate triangles."""
    vertices: list[list[float]] = []
    triangles: list[np.ndarray] = []
    for line in path.read_text(encoding="ascii").splitlines():
        if line.startswith("v "):
            vertices.append([float(value) for value in line.split()[1:4]])
        elif line.startswith("f "):
            indices = [int(token.split("/")[0]) - 1 for token in line.split()[1:]]
            if len(indices) < 3:
                continue
            for index in range(1, len(indices) - 1):
                triangles.append(np.asarray([vertices[indices[0]], vertices[indices[index]], vertices[indices[index + 1]]], dtype=np.float64))
    return np.asarray(triangles, dtype=np.float64).reshape(-1, 3, 3)


def add_comparison_prior_assets(
    config: dict[str, Any],
    artifact_root: Path,
    partial: Path,
    source_viewer: dict[str, Any],
    origin: np.ndarray,
    bboxes: dict[str, tuple[float, float, float, float]],
    crop_receipts: list[dict[str, Any]],
) -> tuple[dict[str, dict[str, dict[str, Any]]], dict[str, dict[str, Any]]]:
    prior_spec = config["comparison_priors"]
    prior_root = artifact_root / prior_spec["relative_root"]
    als_source = prior_root / prior_spec["existing_als"]["path"]
    lod2_source = prior_root / prior_spec["existing_lod2"]["path"]
    exact_file(als_source, prior_spec["existing_als"])
    exact_file(lod2_source, prior_spec["existing_lod2"])
    prior_als_local = np.fromfile(als_source, dtype="<f4")
    if prior_als_local.size % 3:
        raise RuntimeError("Existing ALS comparison adapter is not xyz float32")
    prior_als_local = prior_als_local.reshape(-1, 3).astype(np.float64)
    prior_lod2_local = load_expanded_obj_triangles(lod2_source)
    source_shift = np.asarray(prior_spec["source_world_shift_xyz"], dtype=np.float64)
    frame_offset = source_shift - origin
    prior_als_scene = prior_als_local + frame_offset
    prior_lod2_scene = prior_lod2_local + frame_offset
    prior_lod2_centers = prior_lod2_scene.mean(axis=1)
    comparison_assets: dict[str, dict[str, dict[str, Any]]] = {}
    for building in source_viewer["buildings"]:
        stable_id = building["stable_id"]
        index = int(building["population_index"])
        directory = partial / f"assets/B{index:03d}_{stable_id}"
        x0, y0, x1, y1 = bboxes[stable_id]
        local_bbox = np.asarray([x0 - origin[0], y0 - origin[1], x1 - origin[0], y1 - origin[1]])
        als_inside = (
            (prior_als_scene[:, 0] >= local_bbox[0]) & (prior_als_scene[:, 0] <= local_bbox[2])
            & (prior_als_scene[:, 1] >= local_bbox[1]) & (prior_als_scene[:, 1] <= local_bbox[3])
        )
        als_local = prior_als_scene[als_inside]
        als_rows = np.zeros((len(als_local), 13), dtype=np.float64)
        if len(als_local):
            als_rows[:, :3] = als_local + origin
            als_rows[:, 3] = 6
            als_rows[:, 4:7] = np.asarray([56, 189, 248])
        als_path = directory / "15_EXISTING_ALS_PRIOR_FRAME_ALIGNED_v12.ply"
        write_c3_ply(als_path, als_rows, origin)

        lod2_inside = (
            (prior_lod2_centers[:, 0] >= local_bbox[0]) & (prior_lod2_centers[:, 0] <= local_bbox[2])
            & (prior_lod2_centers[:, 1] >= local_bbox[1]) & (prior_lod2_centers[:, 1] <= local_bbox[3])
        )
        lod2_triangles = prior_lod2_scene[lod2_inside]
        lod2_path = None
        if len(lod2_triangles):
            lod2_path = directory / "16_EXISTING_LOD2_PRIOR_FRAME_ALIGNED_v12.obj"
            write_new(lod2_path, triangles_obj("Existing_LoD2_prior", "unused.mtl", "prior_lod2", lod2_triangles + origin, origin))
        empty_path = directory / "17_EXISTING_LOD2_EMPTY_POINTS_v12.ply"
        write_c3_ply(empty_path, np.empty((0, 13), dtype=np.float64), origin)
        crop_receipts.extend([
            {
                "stable_id": stable_id,
                "source_condition": "PRIOR_ALS_COMPARISON",
                "crop_bbox_world_xy": list(bboxes[stable_id]),
                "display_point_count": int(len(als_local)),
                "sampling_rule": "FROZEN_8876_1M_ADAPTER_NO_ADDITIONAL_SAMPLE",
                "source_world_shift_xyz": source_shift.tolist(),
                "target_scene_origin_xyz": origin.tolist(),
                "applied_scene_offset_xyz": frame_offset.tolist(),
            },
            {
                "stable_id": stable_id,
                "source_condition": "PRIOR_LOD2_COMPARISON",
                "crop_bbox_world_xy": list(bboxes[stable_id]),
                "display_triangle_count": int(len(lod2_triangles)),
                "selection_rule": "TRIANGLE_CENTROID_INSIDE_BUILDING_DISPLAY_BBOX",
                "source_world_shift_xyz": source_shift.tolist(),
                "target_scene_origin_xyz": origin.tolist(),
                "applied_scene_offset_xyz": frame_offset.tolist(),
            },
        ])
        comparison_assets[stable_id] = {
            "PRIOR_ALS": {
                "asset_role": "EXISTING_ALS_COMPARISON_PRIOR",
                "point_count": int(len(als_local)),
                "points": als_path.relative_to(partial).as_posix(),
                "roofer": None,
                "roofer_triangles": 0,
                "technical_status": "COMPARISON_PRIOR_NOT_EVALUATED",
                "diagnostic_summary": "frozen 8876 1m display adapter · frame-aligned · O/X 비대상",
                "lineage_label": "EXISTING_ALS_RAW_PRIOR_DISPLAY_ADAPTER",
            },
            "PRIOR_LOD2": {
                "asset_role": "EXISTING_LOD2_COMPARISON_PRIOR",
                "point_count": 0,
                "points": empty_path.relative_to(partial).as_posix(),
                "roofer": None if lod2_path is None else lod2_path.relative_to(partial).as_posix(),
                "roofer_triangles": int(len(lod2_triangles)),
                "technical_status": "REFERENCE_DERIVED_DIAGNOSTIC_COMPARISON_ONLY",
                "diagnostic_summary": "Existing LoD2 original · frame-aligned · 독립 reference/OX 비대상",
                "lineage_label": "EXISTING_LOD2_ORIGINAL_REFERENCE_DERIVED_DIAGNOSTIC",
            },
        }
    frame_record = {
        "source_world_shift_xyz": source_shift.tolist(),
        "target_scene_origin_xyz": origin.tolist(),
        "applied_scene_offset_xyz": frame_offset.tolist(),
    }
    return comparison_assets, {
        "PRIOR_ALS": {**file_record(als_source, artifact_root), **frame_record},
        "PRIOR_LOD2": {**file_record(lod2_source, artifact_root), **frame_record},
    }


def build_app(source: str, storage_key: str) -> str:
    text = transform_app(source)
    text = text.replace("  c3Mesh: 0x8b5cf6,", "  c3Mesh: 0x8b5cf6,\n  priorLod2Mesh: 0xeab308,")
    text = text.replace("  c3PointRgb: [139 / 255, 92 / 255, 246 / 255],", "  c3PointRgb: [139 / 255, 92 / 255, 246 / 255],\n  priorAlsPointRgb: [56 / 255, 189 / 255, 248 / 255],")
    text = text.replace(
        "const building = method === 'lidar' ? COLORS.lidarPointRgb : method === 'mvs' ? COLORS.mvsPointRgb : COLORS.c3PointRgb;",
        "const building = method === 'lidar' ? COLORS.lidarPointRgb : method === 'mvs' ? COLORS.mvsPointRgb : method === 'prior' ? COLORS.priorAlsPointRgb : COLORS.c3PointRgb;",
    )
    text = text.replace("colorMode: 'rgb'", "colorMode: 'condition'")
    text = text.replace("const STORAGE_KEY = 'jointbuildgs-c1-c2-roofer-ox-v1';", f"const STORAGE_KEY = '{storage_key}';")
    text = text.replace("c3Condition: 'C3_1'", f"c3Condition: '{E3_KEY}'")
    text = text.replace(
        "'reviewNote', 'exportCsv'",
        "'lidarReason', 'mvsReason', 'c3Reason', 'lidarReasonNote', 'mvsReasonNote', 'c3ReasonNote', 'e4Review', 'e4ReviewO', 'e4ReviewX', 'e4ReviewCurrent', 'e4Reason', 'e4ReasonNote', 'e5Review', 'e5ReviewO', 'e5ReviewX', 'e5ReviewCurrent', 'e5Reason', 'e5ReasonNote', 'e6Review', 'e6ReviewO', 'e6ReviewX', 'e6ReviewCurrent', 'e6Reason', 'e6ReasonNote', 'reviewNote', 'exportCsv', 'togglePhoto'",
    )
    text = text.replace("constructor(rootId, statsId, method, index) {", "constructor(rootId, statsId, method, index, conditionId = null) {")
    text = text.replace(
        "    this.method = method;\n    this.index = index;",
        "    this.method = method;\n    this.index = index;\n    this.conditionId = conditionId;",
    )
    text = text.replace(
        "    const spec = this.method === 'c3' ? building.c3[state.c3Condition] : building[this.method];",
        "    const spec = this.conditionId ? (building.conditions[this.conditionId] || building.comparison_priors[this.conditionId]) : building[this.method];",
    )
    text = text.replace(
        "const color = this.method === 'lidar' ? COLORS.lidarMesh : this.method === 'mvs' ? COLORS.mvsMesh : COLORS.c3Mesh;",
        "const color = this.conditionId === 'PRIOR_LOD2' ? COLORS.priorLod2Mesh : this.method === 'lidar' ? COLORS.lidarMesh : this.method === 'mvs' ? COLORS.mvsMesh : COLORS.c3Mesh;",
    )
    text = text.replace(
        "const roofLabel = this.roofer ? `${spec.roofer_triangles.toLocaleString()} triangles` : 'Roofer MISSING';",
        "const roofLabel = spec.asset_role === 'EXISTING_ALS_COMPARISON_PRIOR' ? 'ALS prior points' : spec.asset_role === 'EXISTING_LOD2_COMPARISON_PRIOR' ? (this.roofer ? `${spec.roofer_triangles.toLocaleString()} prior triangles` : 'prior LoD2 MISSING') : (this.roofer ? `${spec.roofer_triangles.toLocaleString()} triangles` : 'Roofer MISSING');",
    )
    text = text.replace(
        "this.baseStats = `${ply.count.toLocaleString()} points · ${roofLabel} · ${spec.technical_status}`;",
        """this.stats.classList.remove('auto-o', 'auto-x');
    if (spec.automatic_candidate) this.stats.classList.add(spec.automatic_candidate === 'AUTO_O_CANDIDATE' ? 'auto-o' : 'auto-x');
    const diagnostic = spec.diagnostic_summary ? ` · ${spec.diagnostic_summary}` : '';
    const compact = compactGateSummary(spec, Boolean(this.roofer));
    this.stats.title = `${ply.count.toLocaleString()} points · ${roofLabel} · ${spec.technical_status}${diagnostic}`;
    this.baseStats = compact;""",
    )
    text = text.replace(
        "    canvas.addEventListener('contextmenu', (event) => event.preventDefault());",
        """    canvas.addEventListener('contextmenu', (event) => event.preventDefault());
    canvas.addEventListener('dblclick', () => {
      const grid = document.getElementById('viewports');
      const shell = this.root.parentElement;
      const closing = shell.classList.contains('focus-panel');
      document.querySelectorAll('.viewport-shell').forEach((item) => item.classList.remove('focus-panel'));
      grid.classList.toggle('focus-mode', !closing);
      if (!closing) shell.classList.add('focus-panel');
    });""",
    )
    text = text.replace("if (state.sync && viewers.length === 3)", "if (state.sync && viewers.length === 8)")
    old_push = """viewers.push(
  new ReviewViewer('lidarViewport', 'lidarStats', 'lidar', 0),
  new ReviewViewer('mvsViewport', 'mvsStats', 'mvs', 1),
  new ReviewViewer('c3Viewport', 'c3Stats', 'c3', 2),
);"""
    new_push = """viewers.push(
  new ReviewViewer('lidarViewport', 'lidarStats', 'lidar', 0),
  new ReviewViewer('mvsViewport', 'mvsStats', 'mvs', 1),
  new ReviewViewer('c3Viewport', 'c3Stats', 'c3', 2, 'E3'),
  new ReviewViewer('e4Viewport', 'e4Stats', 'c3', 3, 'E4'),
  new ReviewViewer('e5Viewport', 'e5Stats', 'c3', 4, 'E5'),
  new ReviewViewer('e6Viewport', 'e6Stats', 'c3', 5, 'E6'),
  new ReviewViewer('priorAlsViewport', 'priorAlsStats', 'prior', 6, 'PRIOR_ALS'),
  new ReviewViewer('priorLod2Viewport', 'priorLod2Stats', 'prior', 7, 'PRIOR_LOD2'),
);"""
    if old_push not in text:
        raise RuntimeError("viewer constructor block drifted")
    text = text.replace(old_push, new_push)
    status_line = "elements.buildingStatus.innerHTML = `LiDAR <strong>${building.lidar.technical_status}</strong> · MVS <strong>${building.mvs.technical_status}</strong> · ${state.c3Condition} <strong>${building.c3[state.c3Condition].technical_status}</strong>`;"
    text = text.replace(status_line, "elements.buildingStatus.innerHTML = conditionSummary(building);")
    text = text.replace(
        "async function loadBuilding(index) {",
        """function compactReason(spec, hasRoofer) {
  if (spec.asset_role) return spec.diagnostic_summary || '비교용 prior · O/X 비대상';
  if (hasRoofer) {
    if (spec.metrics && spec.metrics.val3dity_valid === false) return 'LoD2 생성 · val3dity 실패';
    if (spec.technical_status === 'TECHNICAL_VALID_LOD22') return 'LoD2 생성 · 기술 유효';
    return 'LoD2 생성 · G1/G2 기록 없음';
  }
  const reason = spec.reason || '';
  if (reason.includes('insufficient_coverage') || (spec.metrics && spec.metrics.rf_pointcloud_unusable)) return 'LoD2 없음 · coverage 부족';
  if (reason.includes('no_points')) return 'LoD2 없음 · 내부점 없음';
  if (reason.includes('val3dity')) return 'LoD2 실패 · val3dity';
  if (spec.technical_status === 'MISSING' || reason.includes('missing_roofer_feature')) return '출력 없음';
  return 'LoD2 생성 실패';
}

function compactGateSummary(spec, hasRoofer) {
  if (spec.asset_role) return compactReason(spec, hasRoofer);
  const g0 = hasRoofer && Number(spec.roofer_triangles || 0) > 0 ? 'O' : 'X';
  let g1 = '?';
  let g2 = '?';
  if (g0 === 'X') {
    g1 = '–';
    g2 = '–';
  } else if (spec.technical_status === 'TECHNICAL_VALID_LOD22') {
    g1 = 'O';
    g2 = 'O';
  } else if (spec.metrics && typeof spec.metrics.val3dity_valid === 'boolean') {
    g1 = 'O';
    g2 = spec.metrics.val3dity_valid ? 'O' : 'X';
  }
  return `G0 ${g0} · G1 ${g1} · G2 ${g2} · G3 ? · G4 ? · ${compactReason(spec, hasRoofer)}`;
}

function conditionSummary(building) {
  return ['E1', 'E2', 'E3', 'E4', 'E5', 'E6'].map((id) => {
    const spec = id === 'E1' ? building.lidar : id === 'E2' ? building.mvs : building.conditions[id];
    const candidate = spec.automatic_candidate === 'AUTO_O_CANDIDATE' ? '자동 O' : '자동 X';
    return `${id} <strong>${candidate}</strong>`;
  }).join(' · ');
}

async function loadBuilding(index) {""",
    )
    text = _replace_function(text, "loadReviewForm", "selectedReviewValue", """
function loadReviewForm(stableId) {
  const review = state.reviews[stableId] || {};
  setReviewButtons('lidar', review.lidar || '');
  setReviewButtons('mvs', review.mvs || '');
  setReviewButtons('c3', review.c3 || '');
  setReviewButtons('e4', review.e4 || '');
  setReviewButtons('e5', review.e5 || '');
  setReviewButtons('e6', review.e6 || '');
  for (const method of ['lidar', 'mvs', 'c3', 'e4', 'e5', 'e6']) {
    elements[`${method}Reason`].value = review[`${method}Reason`] || '';
    elements[`${method}ReasonNote`].value = review[`${method}ReasonNote`] || '';
  }
  elements.reviewNote.value = review.note || '';
}""")
    text = _replace_function(text, "saveReviewForm", "csvCell", """
function saveReviewForm() {
  const building = manifest.buildings[state.buildingIndex];
  const previous = state.reviews[building.stable_id] || {};
  const next = { ...previous, note: elements.reviewNote.value };
  for (const method of ['lidar', 'mvs', 'c3', 'e4', 'e5', 'e6']) {
    next[method] = selectedReviewValue(method);
    next[`${method}Reason`] = elements[`${method}Reason`].value;
    next[`${method}ReasonNote`] = elements[`${method}ReasonNote`].value.trim();
  }
  state.reviews[building.stable_id] = next;
  localStorage.setItem(STORAGE_KEY, JSON.stringify(state.reviews));
}""")
    text = _replace_function(text, "exportReviewsCsv", "renderPhotoEvidence", """
function exportReviewsCsv() {
  saveReviewForm();
  const rows = [['population_index', 'stable_id', 'condition_id', 'comparison_base', 'lineage_label', 'technical_status', 'automatic_candidate', 'human_roofer_ox', 'x_reason', 'reviewer_reason', 'reviewer_note']];
  for (const building of manifest.buildings) {
    const review = state.reviews[building.stable_id] || {};
    const conditions = [
      ['E1', 'CURRENT_BASELINE', 'CURRENT_BASELINE', building.lidar.technical_status, building.lidar.automatic_candidate, review.lidar || '', review.lidarReason || '', review.lidarReasonNote || ''],
      ['E2', 'CURRENT_BASELINE', 'CURRENT_BASELINE', building.mvs.technical_status, building.mvs.automatic_candidate, review.mvs || '', review.mvsReason || '', review.mvsReasonNote || ''],
      ['E3', 'NEW_30K_BASE', building.conditions.E3.lineage_label, building.conditions.E3.technical_status, building.conditions.E3.automatic_candidate, review.c3 || '', review.c3Reason || '', review.c3ReasonNote || ''],
      ['E4', 'EXISTING_LEGACY_BASE', building.conditions.E4.lineage_label, building.conditions.E4.technical_status, building.conditions.E4.automatic_candidate, review.e4 || '', review.e4Reason || '', review.e4ReasonNote || ''],
      ['E5', 'EXISTING_LEGACY_BASE', building.conditions.E5.lineage_label, building.conditions.E5.technical_status, building.conditions.E5.automatic_candidate, review.e5 || '', review.e5Reason || '', review.e5ReasonNote || ''],
      ['E6', 'EXISTING_LEGACY_BASE', building.conditions.E6.lineage_label, building.conditions.E6.technical_status, building.conditions.E6.automatic_candidate, review.e6 || '', review.e6Reason || '', review.e6ReasonNote || ''],
    ];
    for (const row of conditions) rows.push([building.population_index, building.stable_id, ...row, review.note || '']);
  }
  const blob = new Blob([rows.map((row) => row.map(csvCell).join(',')).join('\\n') + '\\n'], { type: 'text/csv;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = 'JointBuildGS_E1_E6_ROOFER_OX_REVIEW_v14.csv';
  link.click();
  URL.revokeObjectURL(url);
}""")
    text = text.replace(
        "elements.reviewNote.addEventListener('input', saveReviewForm);",
        "for (const id of ['lidarReason', 'mvsReason', 'c3Reason', 'e4Reason', 'e5Reason', 'e6Reason']) elements[id].addEventListener('change', saveReviewForm);\n  for (const id of ['lidarReasonNote', 'mvsReasonNote', 'c3ReasonNote', 'e4ReasonNote', 'e5ReasonNote', 'e6ReasonNote']) elements[id].addEventListener('input', saveReviewForm);\n  elements.reviewNote.addEventListener('input', saveReviewForm);\n  elements.togglePhoto.addEventListener('click', () => { elements.photoDrawer.classList.toggle('collapsed'); elements.togglePhoto.textContent = elements.photoDrawer.classList.contains('collapsed') ? '사진 펼치기' : '사진 접기'; });",
    )
    return text


def build_index(source: str) -> str:
    text = transform_index(source)
    replacements = {
        "JointBuildGS C2/C3 Roofer 3D Review": "JointBuildGS E1-E6 Roofer O/X Review",
        "LiDAR Roofer O/X": "E1 · current UAS LiDAR Roofer O/X",
        "MVS Roofer O/X": "E2 · current-image MVS Roofer O/X",
        "C3 조건 / Roofer O/X": "E3 · image-only GS 30k Roofer O/X",
        '<select id="c3Condition"><option value="C3_1" selected>C3-1</option><option value="C3_2">C3-2</option></select>': f'<select id="c3Condition"><option value="{E3_KEY}" selected>E3 · new 30k</option></select>',
        "C3_1 rendered-depth fused cloud + Roofer": "E3 · new 30k rendered-depth fused cloud + Roofer",
        "LiDAR point cloud + Roofer": "E1 · current UAS LiDAR + Roofer",
        "MVS point cloud + Roofer": "E2 · current-image MVS + Roofer",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    text = text.replace("Roofer O/X</label>", "Roofer 사람 판정 O/X</label>")
    text = text.replace('<option value="rgb">RGB</option>', '<option value="rgb">RGB</option>')
    text = text.replace('<option value="condition">Class 2/6</option>', '<option value="condition" selected>Class 2/6</option>')
    for method in ("lidar", "mvs", "c3"):
        marker = f'<span class="review-current" id="{method}ReviewCurrent">미평가</span>'
        text = text.replace(marker, marker + _reason_options(method))
    extra_reviews = []
    for method, label in (
        ("e4", "E4 · existing ALS unweighted (legacy base)"),
        ("e5", "E5 · conflict-aware ALS (legacy base)"),
        ("e6", "E6 · LoD prior diagnostic (legacy base)"),
    ):
        extra_reviews.append(
            f'<div class="review-field"><label for="{method}Review">{label} · 사람 판정 O/X</label>'
            f'<div class="review-buttons" id="{method}Review" role="group" aria-label="{label} Roofer O/X">'
            f'<button class="review-choice" id="{method}ReviewO" type="button" data-review-method="{method}" data-value="O" aria-pressed="false">O</button>'
            f'<button class="review-choice" id="{method}ReviewX" type="button" data-review-method="{method}" data-value="X" aria-pressed="false">X</button></div>'
            f'<span class="review-current" id="{method}ReviewCurrent">미평가</span>{_reason_options(method)}</div>'
        )
    text = text.replace('<div class="review-field" style="flex:1 1 360px">', "".join(extra_reviews) + '<div class="review-field" style="flex:1 1 360px">')
    text = text.replace(
        '<div id="reviewbar">',
        '<div class="status lineage-warning" style="padding:5px 10px;border-bottom:1px solid var(--line)">패널은 <strong>자동 후보 O/X + G0–G4 압축 사유</strong>를 표시합니다. G3/G4는 threshold 미동결이라 <strong>?</strong>이며 자동 후보가 공식 PASS 또는 사람 판정을 대신하지 않습니다. 상단에서 조건별 사람 O/X와 <strong>짧은 성공/실패 이유</strong>를 직접 입력할 수 있습니다. E3는 새 30k, E4–E6는 legacy-base라 cross-lineage 기술 비교입니다. 마지막 두 패널은 비교용 Existing ALS/LoD2 prior이며 O/X 대상이나 독립 reference가 아닙니다. 패널 더블클릭은 확대/복귀입니다. Semantic textured mesh O/X는 별도 계약입니다.</div>\n  <div id="reviewbar">',
    )
    text = text.replace(
        "grid-template-rows: auto auto auto auto minmax(0, 1fr);",
        "grid-template-rows: auto auto auto auto auto minmax(0, 1fr);",
    )
    text = text.replace(
        "grid-template-columns: repeat(3, minmax(340px, 1fr)); overflow-x: auto;",
        "grid-template-columns: repeat(4, minmax(260px, 1fr)); grid-template-rows: repeat(2, minmax(230px, 1fr)); overflow: auto;",
    )
    text = text.replace(
        "  .viewport-shell {",
        """  #viewports.focus-mode { grid-template-columns: minmax(0, 1fr); grid-template-rows: minmax(0, 1fr); }
  #viewports.focus-mode .viewport-shell:not(.focus-panel) { display: none; }
  .panel-stats::before { display:inline-block; margin-right:6px; padding:2px 5px; border-radius:3px; color:#07130b; font-weight:800; }
  .panel-stats.auto-o::before { content:'자동 후보 O'; background:var(--good); }
  .panel-stats.auto-x::before { content:'자동 후보 X'; color:#18070a; background:var(--bad); }
  #lidarViewport + .panel-label, #lidarViewport + .panel-label + .panel-stats { left:280px; max-width:calc(100% - 288px); }
  .viewport-shell {""",
    )
    text = text.replace(
        "  .review-field select { height: 31px; }",
        "  .review-field select { height: 31px; }\n  .review-reason-note { min-width:180px; height:31px; padding:5px 7px; color:var(--text); background:var(--panel); border:1px solid var(--line); border-radius:4px; }",
    )
    text = text.replace(
        "#photoDrawer { min-height: 0; display: grid;",
        "#photoDrawer { min-height: 0; display: grid;",
    )
    text = text.replace(
        "  #photoHeader {",
        "  #photoDrawer.collapsed { grid-template-rows: auto 0; }\n  #photoDrawer.collapsed #projectedRowStage { display: none; }\n  .lineage-warning { color: var(--warn) !important; }\n  #photoHeader {",
    )
    text = text.replace('<section id="photoDrawer"', '<section id="photoDrawer" class="collapsed"')
    text = text.replace(
        '<span class="status">동결 preview10_v4.py가 생성한 PNG 원본</span>',
        '<span class="status">동결 preview10_v4.py가 생성한 PNG 원본</span><button id="togglePhoto" type="button">사진 펼치기</button>',
    )
    extra_panels = """
    <section class="viewport-shell" aria-label="E4 3D 검토 화면">
      <div class="viewport" id="e4Viewport"></div><div class="panel-label">E4 · existing ALS unweighted · LEGACY BASE</div><div class="panel-stats" id="e4Stats">불러오는 중</div>
    </section>
    <section class="viewport-shell" aria-label="E5 3D 검토 화면">
      <div class="viewport" id="e5Viewport"></div><div class="panel-label">E5 · conflict-aware ALS · LEGACY BASE</div><div class="panel-stats" id="e5Stats">불러오는 중</div>
    </section>
    <section class="viewport-shell" aria-label="E6 3D 검토 화면">
      <div class="viewport" id="e6Viewport"></div><div class="panel-label">E6 · LoD prior diagnostic · LEGACY BASE</div><div class="panel-stats" id="e6Stats">불러오는 중</div>
    </section>
    <section class="viewport-shell comparison-prior" aria-label="Existing ALS 비교 화면">
      <div class="viewport" id="priorAlsViewport"></div><div class="panel-label">P-ALS · Existing ALS raw prior · 비교용</div><div class="panel-stats" id="priorAlsStats">불러오는 중</div>
    </section>
    <section class="viewport-shell comparison-prior" aria-label="Existing LoD2 비교 화면">
      <div class="viewport" id="priorLod2Viewport"></div><div class="panel-label">P-LoD2 · Existing LoD2 original · reference-derived diagnostic</div><div class="panel-stats" id="priorLod2Stats">불러오는 중</div>
    </section>
"""
    text = text.replace("  </div>\n</div>\n<div id=\"loading\">", extra_panels + "  </div>\n</div>\n<div id=\"loading\">")
    text = text.replace('<script type="module" src="./app.js"></script>', '<script type="module" src="./app.js?v=e1e6-roofer-ox-v14"></script>')
    return text


def build_from_reuse(config: dict[str, Any], repo_root: Path, artifact_root: Path) -> dict[str, Any]:
    output = artifact_root / config["output_relative_root"]
    partial = output.with_name(output.name + ".partial")
    if output.exists() or partial.exists():
        raise RuntimeError("fresh add-once viewer namespace required")
    base_spec = config["reuse_viewer"]
    base_root = artifact_root / base_spec["relative_root"]
    base_manifest_path = base_root / base_spec["viewer_manifest_path"]
    base_receipt_path = base_root / base_spec["receipt_path"]
    exact_file(base_manifest_path, {"bytes": base_spec["viewer_manifest_bytes"], "sha256": base_spec["viewer_manifest_sha256"]})
    exact_file(base_receipt_path, {"bytes": base_spec["receipt_bytes"], "sha256": base_spec["receipt_sha256"]})
    base_viewer = json.loads(base_manifest_path.read_text(encoding="utf-8"))
    base_receipt = json.loads(base_receipt_path.read_text(encoding="utf-8"))
    if len(base_viewer.get("buildings", [])) != 199 or base_viewer.get("scientific_verdict", "missing") is not None:
        raise RuntimeError("reused viewer population/verdict drifted")
    shutil.copytree(base_root, partial, copy_function=os.link)
    for name in ("viewer_manifest.json", "web_receipt_v1.json", "app.js", "index.html", "README.md"):
        (partial / name).unlink()

    origin = np.asarray(config["display"]["scene_local_origin_xyz"], dtype=np.float64)
    bboxes = {row["stable_id"]: tuple(map(float, row["bbox_world_xy"])) for row in base_viewer["buildings"]}
    crop_receipts = list(base_receipt["crop_receipts"])
    comparison_assets, comparison_sources = add_comparison_prior_assets(
        config, artifact_root, partial, base_viewer, origin, bboxes, crop_receipts,
    )
    viewer = dict(base_viewer)
    viewer.update({
        "task_id": config["task_id"],
        "status": "READY_FOR_HUMAN_ROOFER_OX_REVIEW",
        "comparison_prior_sources": comparison_sources,
        "official_PASS_usable": None,
        "scientific_verdict": None,
    })
    viewer["buildings"] = [
        {**row, "comparison_priors": comparison_assets[row["stable_id"]]}
        for row in base_viewer["buildings"]
    ]
    write_new(partial / "viewer_manifest.json", canonical_json_bytes(viewer))
    for spec in config["application_sources"].values():
        exact_file(repo_root / spec["path"], spec)
    app = build_app((repo_root / config["application_sources"]["app"]["path"]).read_text(encoding="utf-8"), config["local_storage_key"])
    index = build_index((repo_root / config["application_sources"]["index"]["path"]).read_text(encoding="utf-8"))
    write_new(partial / "app.js", app.encode("utf-8"))
    write_new(partial / "index.html", index.encode("utf-8"))
    write_new(partial / "README.md", b"# E1-E6 Roofer O/X review v14\n\nE1/E2 are current baselines, E3 is the new 30k result, and E4-E6 are existing legacy-base outputs. The exact v9 condition display assets are hash-bound and reused without recomputation. Separate Existing ALS and Existing LoD2 comparison-prior panels are transformed from the 8876 world shift into the current viewer scene frame and use cache-distinct asset names. Compact G0-G4 diagnostic labels keep G3/G4 unknown until numerical thresholds are frozen. Per-condition human success/failure reason notes are persisted with O/X and exported to CSV. Existing LoD2 is reference-derived diagnostic evidence, not an independent reference or O/X target. Automatic candidates remain advisory, human O/X remains separate, semantic textured mesh is a separate output contract, and scientific_verdict is null.\n")
    receipt = dict(base_receipt)
    receipt.update({
        "task_id": config["task_id"],
        "status": "READY_FOR_HUMAN_ROOFER_OX_REVIEW",
        "crop_receipt_count": len(crop_receipts),
        "crop_receipts": crop_receipts,
        "reused_parent_viewer_manifest": file_record(base_manifest_path, artifact_root),
        "reused_parent_receipt": file_record(base_receipt_path, artifact_root),
        "reuse_method": "SAME_FILESYSTEM_HARDLINK_EXACT_V9_DISPLAY_ASSETS",
        "comparison_prior_sources": comparison_sources,
        "viewer_manifest": file_record(partial / "viewer_manifest.json", partial),
        "application": {name: file_record(partial / name, partial) for name in ("app.js", "index.html")},
        "official_PASS_usable": None,
        "scientific_verdict": None,
    })
    write_new(partial / "web_receipt_v1.json", canonical_json_bytes(receipt))
    os.rename(partial, output)
    return receipt


def build(config_path: Path, repo_root: Path, artifact_root: Path) -> dict[str, Any]:
    config = load_config(config_path)
    if config.get("reuse_viewer"):
        return build_from_reuse(config, repo_root, artifact_root)
    output = artifact_root / config["output_relative_root"]
    partial = output.with_name(output.name + ".partial")
    if output.exists() or partial.exists():
        raise RuntimeError("fresh add-once viewer namespace required")
    partial.mkdir(parents=True)

    source_spec = config["source_viewer"]
    source_root = artifact_root / source_spec["relative_root"]
    exact_file(source_root / source_spec["viewer_manifest_path"], {"bytes": source_spec["viewer_manifest_bytes"], "sha256": source_spec["viewer_manifest_sha256"]})
    exact_file(source_root / source_spec["artifact_manifest_path"], {"bytes": source_spec["artifact_manifest_bytes"], "sha256": source_spec["artifact_manifest_sha256"]})
    source_viewer = json.loads((source_root / source_spec["viewer_manifest_path"]).read_text(encoding="utf-8"))
    if len(source_viewer["buildings"]) != 199 or source_viewer.get("scientific_verdict", "missing") is not None:
        raise RuntimeError("source population/verdict drifted")
    _copy_base(source_root, partial)

    e3_spec = config["e3_result"]
    e3_root = artifact_root / e3_spec["relative_root"]
    for key in ("finalized", "classified", "cityjson"):
        exact_file(e3_root / e3_spec[f"{key}_path"], {"bytes": e3_spec[f"{key}_bytes"], "sha256": e3_spec[f"{key}_sha256"]})
    finalized = json.loads((e3_root / e3_spec["finalized_path"]).read_text(encoding="utf-8"))
    if finalized["status"] != "TECHNICAL_COMPLETE_WITH_EXPLICIT_MISSINGNESS" or finalized["building_count"] != 199 or finalized.get("scientific_verdict", "missing") is not None:
        raise RuntimeError("new E3 Stage-3 result is not ready")
    statuses = {
        row["stable_id"]: row
        for row in map(json.loads, (e3_root / "results/building_method_results_v1.jsonl").read_text(encoding="utf-8").splitlines())
        if row["condition_id"] == E3_KEY
    }
    if len(statuses) != 199:
        raise RuntimeError("E3 status population drifted")

    origin = np.asarray(config["display"]["scene_local_origin_xyz"], dtype=np.float64)
    bboxes = {row["stable_id"]: tuple(map(float, row["bbox_world_xy"])) for row in source_viewer["buildings"]}
    classified = e3_root / e3_spec["classified_path"]
    crops, raw_counts = collect_building_crops(classified, bboxes, float(config["display"]["voxel_m"]), int(config["display"]["maximum_points_per_building_condition"]))
    cityjson = json.loads((e3_root / e3_spec["cityjson_path"]).read_text(encoding="utf-8"))
    e3_assets = {}
    crop_receipts = []
    for building in source_viewer["buildings"]:
        stable_id = building["stable_id"]
        index = int(building["population_index"])
        directory = partial / f"assets/B{index:03d}_{stable_id}"
        points_path = directory / "07_E3_POINTS_rgb_class_audit.ply"
        write_c3_ply(points_path, crops[stable_id], origin)
        triangles = lod22_triangles(cityjson, stable_id)
        roofer_path = None
        if triangles:
            roofer_path = directory / "08_E3_ROOFER.obj"
            write_new(roofer_path, triangles_obj("E3", "unused.mtl", "e3", triangles, origin))
        receipt = {
            "stable_id": stable_id,
            "source_condition": E3_KEY,
            "crop_bbox_world_xy": list(bboxes[stable_id]),
            "raw_crop_point_count": int(raw_counts[stable_id]),
            "display_point_count": int(len(crops[stable_id])),
            "sampling_rule": config["display"]["sampling_rule"],
        }
        crop_receipts.append(receipt)
        state = statuses[stable_id]
        e3_assets[stable_id] = {
            "point_count": int(len(crops[stable_id])),
            "points": points_path.relative_to(partial).as_posix(),
            "roofer": None if roofer_path is None else roofer_path.relative_to(partial).as_posix(),
            "roofer_triangles": int(len(triangles)),
            "technical_status": state["status"],
            "automatic_candidate": "AUTO_O_CANDIDATE" if state["status"] == "TECHNICAL_VALID_LOD22" else "AUTO_X_CANDIDATE",
            "lineage_label": "NEW_E3_30K_FUSED_NORMAL_CONFIDENCE",
            "reason": state["reason"],
            "metrics": {key: state.get(key) for key in ("rf_nodata_frac", "rf_pt_density", "rf_rmse_lod22", "rf_roof_planes", "rf_roof_type", "val3dity_valid")},
        }

    all_condition_assets: dict[str, dict[str, dict[str, Any]]] = {"E3": e3_assets}
    legacy_source_records = {}
    legacy_root = artifact_root / config["legacy_results"]["relative_root"]
    asset_numbers = {"E4": (9, 10), "E5": (11, 12), "E6": (13, 14)}
    for condition_id, legacy_spec in config["legacy_results"]["conditions"].items():
        for key in ("classified", "cityjson", "receipt"):
            exact_file(
                legacy_root / legacy_spec[f"{key}_path"],
                {"bytes": legacy_spec[f"{key}_bytes"], "sha256": legacy_spec[f"{key}_sha256"]},
            )
        legacy_receipt = json.loads((legacy_root / legacy_spec["receipt_path"]).read_text(encoding="utf-8"))
        if legacy_receipt.get("scientific_verdict", "missing") is not None or legacy_receipt.get("parameters") != "ROOFER_DEFAULTS":
            raise RuntimeError(f"legacy {condition_id} receipt contract drifted")
        if legacy_receipt.get("footprint", {}).get("sha256") != "5f9b703b06676db4400f6568fc3db315e319913f98ba491e98922eb747e4488a":
            raise RuntimeError(f"legacy {condition_id} shared footprint drifted")
        legacy_classified = legacy_root / legacy_spec["classified_path"]
        legacy_source_records[condition_id] = file_record(legacy_classified, artifact_root)
        legacy_crops, legacy_raw_counts = collect_basic_building_crops(
            legacy_classified,
            bboxes,
            float(config["display"]["voxel_m"]),
            int(config["display"]["maximum_points_per_building_condition"]),
        )
        legacy_cityjson = json.loads((legacy_root / legacy_spec["cityjson_path"]).read_text(encoding="utf-8"))
        condition_assets = {}
        point_number, roofer_number = asset_numbers[condition_id]
        for building in source_viewer["buildings"]:
            stable_id = building["stable_id"]
            index = int(building["population_index"])
            directory = partial / f"assets/B{index:03d}_{stable_id}"
            points_path = directory / f"{point_number:02d}_{condition_id}_POINTS_rgb_class_audit.ply"
            write_c3_ply(points_path, legacy_crops[stable_id], origin)
            triangles = lod22_triangles(legacy_cityjson, stable_id)
            city_object = legacy_cityjson.get("CityObjects", {}).get(stable_id, {})
            attributes = city_object.get("attributes", {})
            roofer_path = None
            if triangles:
                roofer_path = directory / f"{roofer_number:02d}_{condition_id}_ROOFER.obj"
                write_new(roofer_path, triangles_obj(condition_id, "unused.mtl", condition_id.lower(), triangles, origin))
            raw_count = int(legacy_raw_counts[stable_id])
            if raw_count == 0:
                technical_status, reason = "MISSING_POINT_SUPPORT", "no_points_inside_building_bbox"
            elif not triangles:
                if attributes.get("rf_pointcloud_unusable"):
                    technical_status, reason = "NO_LOD22", "roofer_skipped_pointcloud_with_insufficient_coverage"
                else:
                    technical_status, reason = "NO_LOD22", "no_lod22_geometry_for_stable_id"
            else:
                technical_status, reason = "TECHNICAL_LOD22_PRESENT", "lod22_present_not_official_usable"
            diagnostic_parts = []
            if attributes.get("rf_pointcloud_unusable"):
                diagnostic_parts.append("Roofer input unusable")
            if attributes.get("rf_nodata_frac") is not None:
                diagnostic_parts.append(f"nodata {float(attributes['rf_nodata_frac']) * 100:.1f}%")
            if attributes.get("rf_roof_planes") is not None:
                diagnostic_parts.append(f"roof planes {int(attributes['rf_roof_planes'])}")
            if attributes.get("rf_roof_type"):
                diagnostic_parts.append(str(attributes["rf_roof_type"]))
            if attributes.get("rf_extrusion_mode"):
                diagnostic_parts.append(f"extrusion {attributes['rf_extrusion_mode']}")
            receipt = {
                "stable_id": stable_id,
                "source_condition": condition_id,
                "lineage_label": legacy_spec["lineage_label"],
                "crop_bbox_world_xy": list(bboxes[stable_id]),
                "raw_crop_point_count": raw_count,
                "display_point_count": int(len(legacy_crops[stable_id])),
                "sampling_rule": config["display"]["sampling_rule"],
            }
            crop_receipts.append(receipt)
            condition_assets[stable_id] = {
                "point_count": int(len(legacy_crops[stable_id])),
                "points": points_path.relative_to(partial).as_posix(),
                "roofer": None if roofer_path is None else roofer_path.relative_to(partial).as_posix(),
                "roofer_triangles": int(len(triangles)),
                "technical_status": technical_status,
                "reason": reason,
                "diagnostic_summary": " · ".join(diagnostic_parts),
                "metrics": {key: attributes.get(key) for key in ("rf_pointcloud_unusable", "rf_pc_select", "rf_nodata_frac", "rf_pt_density", "rf_roof_planes", "rf_roof_type", "rf_extrusion_mode")},
                "automatic_candidate": "AUTO_O_CANDIDATE" if technical_status == "TECHNICAL_LOD22_PRESENT" else "AUTO_X_CANDIDATE",
                "lineage_label": legacy_spec["lineage_label"],
                "matched_to_new_e3": False,
            }
        all_condition_assets[condition_id] = condition_assets

    prior_spec = config["comparison_priors"]
    prior_root = artifact_root / prior_spec["relative_root"]
    als_source = prior_root / prior_spec["existing_als"]["path"]
    lod2_source = prior_root / prior_spec["existing_lod2"]["path"]
    exact_file(als_source, prior_spec["existing_als"])
    exact_file(lod2_source, prior_spec["existing_lod2"])
    prior_als_local = np.fromfile(als_source, dtype="<f4")
    if prior_als_local.size % 3:
        raise RuntimeError("Existing ALS comparison adapter is not xyz float32")
    prior_als_local = prior_als_local.reshape(-1, 3).astype(np.float64)
    prior_lod2_local = load_expanded_obj_triangles(lod2_source)
    prior_lod2_centers = prior_lod2_local.mean(axis=1)
    comparison_assets: dict[str, dict[str, dict[str, Any]]] = {}
    for building in source_viewer["buildings"]:
        stable_id = building["stable_id"]
        index = int(building["population_index"])
        directory = partial / f"assets/B{index:03d}_{stable_id}"
        x0, y0, x1, y1 = bboxes[stable_id]
        local_bbox = np.asarray([x0 - origin[0], y0 - origin[1], x1 - origin[0], y1 - origin[1]])
        als_inside = (
            (prior_als_local[:, 0] >= local_bbox[0]) & (prior_als_local[:, 0] <= local_bbox[2])
            & (prior_als_local[:, 1] >= local_bbox[1]) & (prior_als_local[:, 1] <= local_bbox[3])
        )
        als_local = prior_als_local[als_inside]
        als_rows = np.zeros((len(als_local), 13), dtype=np.float64)
        if len(als_local):
            als_rows[:, :3] = als_local + origin
            als_rows[:, 3] = 6
            als_rows[:, 4:7] = np.asarray([56, 189, 248])
        als_path = directory / "15_EXISTING_ALS_PRIOR_POINTS.ply"
        write_c3_ply(als_path, als_rows, origin)

        lod2_inside = (
            (prior_lod2_centers[:, 0] >= local_bbox[0]) & (prior_lod2_centers[:, 0] <= local_bbox[2])
            & (prior_lod2_centers[:, 1] >= local_bbox[1]) & (prior_lod2_centers[:, 1] <= local_bbox[3])
        )
        lod2_triangles = prior_lod2_local[lod2_inside]
        lod2_path = None
        if len(lod2_triangles):
            lod2_path = directory / "16_EXISTING_LOD2_PRIOR.obj"
            write_new(lod2_path, triangles_obj("Existing_LoD2_prior", "unused.mtl", "prior_lod2", lod2_triangles + origin, origin))
        empty_path = directory / "17_EXISTING_LOD2_EMPTY_POINTS.ply"
        write_c3_ply(empty_path, np.empty((0, 13), dtype=np.float64), origin)
        crop_receipts.extend([
            {
                "stable_id": stable_id,
                "source_condition": "PRIOR_ALS_COMPARISON",
                "crop_bbox_world_xy": list(bboxes[stable_id]),
                "display_point_count": int(len(als_local)),
                "sampling_rule": "FROZEN_8876_1M_ADAPTER_NO_ADDITIONAL_SAMPLE",
            },
            {
                "stable_id": stable_id,
                "source_condition": "PRIOR_LOD2_COMPARISON",
                "crop_bbox_world_xy": list(bboxes[stable_id]),
                "display_triangle_count": int(len(lod2_triangles)),
                "selection_rule": "TRIANGLE_CENTROID_INSIDE_BUILDING_DISPLAY_BBOX",
            },
        ])
        comparison_assets[stable_id] = {
            "PRIOR_ALS": {
                "asset_role": "EXISTING_ALS_COMPARISON_PRIOR",
                "point_count": int(len(als_local)),
                "points": als_path.relative_to(partial).as_posix(),
                "roofer": None,
                "roofer_triangles": 0,
                "technical_status": "COMPARISON_PRIOR_NOT_EVALUATED",
                "diagnostic_summary": "frozen 8876 1m display adapter · O/X 비대상",
                "lineage_label": "EXISTING_ALS_RAW_PRIOR_DISPLAY_ADAPTER",
            },
            "PRIOR_LOD2": {
                "asset_role": "EXISTING_LOD2_COMPARISON_PRIOR",
                "point_count": 0,
                "points": empty_path.relative_to(partial).as_posix(),
                "roofer": None if lod2_path is None else lod2_path.relative_to(partial).as_posix(),
                "roofer_triangles": int(len(lod2_triangles)),
                "technical_status": "REFERENCE_DERIVED_DIAGNOSTIC_COMPARISON_ONLY",
                "diagnostic_summary": "Existing LoD2 original · 독립 reference/OX 비대상",
                "lineage_label": "EXISTING_LOD2_ORIGINAL_REFERENCE_DERIVED_DIAGNOSTIC",
            },
        }

    viewer = dict(source_viewer)
    viewer.update({
        "schema": "jointbuildgs.p2.e1_e6_roofer_ox_review.viewer.v1",
        "task_id": config["task_id"],
        "status": "READY_FOR_HUMAN_ROOFER_OX_REVIEW",
        "condition_availability": config["conditions"],
        "roofer_ox_contract": config["roofer_ox_contract"],
        "comparison_prior_sources": {
            "PRIOR_ALS": file_record(als_source, artifact_root),
            "PRIOR_LOD2": file_record(lod2_source, artifact_root),
        },
        "official_PASS_usable": None,
        "scientific_verdict": None,
    })
    viewer["buildings"] = []
    for row in source_viewer["buildings"]:
        stable_id = row["stable_id"]
        lidar = {
            **row["lidar"],
            "automatic_candidate": "AUTO_O_CANDIDATE" if row["lidar"]["technical_status"] == "TECHNICAL_VALID_LOD22" else "AUTO_X_CANDIDATE",
        }
        mvs = {
            **row["mvs"],
            "automatic_candidate": "AUTO_O_CANDIDATE" if row["mvs"]["technical_status"] == "TECHNICAL_VALID_LOD22" else "AUTO_X_CANDIDATE",
        }
        conditions = {condition_id: all_condition_assets[condition_id][stable_id] for condition_id in CONDITIONS}
        viewer["buildings"].append({**row, "lidar": lidar, "mvs": mvs, "c3": {E3_KEY: conditions["E3"]}, "conditions": conditions, "comparison_priors": comparison_assets[stable_id]})
    write_new(partial / "viewer_manifest.json", canonical_json_bytes(viewer))

    for spec in config["application_sources"].values():
        exact_file(repo_root / spec["path"], spec)
    app = build_app((repo_root / config["application_sources"]["app"]["path"]).read_text(encoding="utf-8"), config["local_storage_key"])
    index = build_index((repo_root / config["application_sources"]["index"]["path"]).read_text(encoding="utf-8"))
    write_new(partial / "app.js", app.encode("utf-8"))
    write_new(partial / "index.html", index.encode("utf-8"))
    write_new(partial / "README.md", b"# E1-E6 Roofer O/X review v14\n\nE1/E2 are current baselines, E3 is the new 30k result, and E4-E6 are existing legacy-base outputs. The six condition panels are accompanied by cache-distinct, frame-aligned Existing ALS and Existing LoD2 comparison-prior panels. Compact G0-G4 diagnostic labels keep G3/G4 unknown until numerical thresholds are frozen. Per-condition human success/failure reason notes are persisted with O/X and exported to CSV. Existing LoD2 is reference-derived diagnostic evidence, not an independent reference or O/X target. Automatic-candidate badges and legacy Roofer failure diagnostics are shown per condition panel. Cross-lineage comparison is descriptive, not a matched causal contrast. Automatic candidates are advisory; human O/X remains separate. Semantic textured mesh is a separate output contract. scientific_verdict is null.\n")
    receipt = {
        "schema": "jointbuildgs.p2.e1_e6_roofer_ox_review.receipt.v1",
        "task_id": config["task_id"],
        "status": "READY_FOR_HUMAN_ROOFER_OX_REVIEW",
        "building_count": 199,
        "condition_availability": config["conditions"],
        "crop_receipt_count": len(crop_receipts),
        "crop_receipts": crop_receipts,
        "source_viewer_manifest": file_record(source_root / source_spec["viewer_manifest_path"], artifact_root),
        "e3_classified_source": file_record(classified, artifact_root),
        "legacy_classified_sources": legacy_source_records,
        "comparison_prior_sources": {
            "PRIOR_ALS": file_record(als_source, artifact_root),
            "PRIOR_LOD2": file_record(lod2_source, artifact_root),
        },
        "cross_lineage_comparison": True,
        "viewer_manifest": file_record(partial / "viewer_manifest.json", partial),
        "application": {name: file_record(partial / name, partial) for name in ("app.js", "index.html")},
        "official_PASS_usable": None,
        "scientific_verdict": None,
    }
    write_new(partial / "web_receipt_v1.json", canonical_json_bytes(receipt))
    os.rename(partial, output)
    return receipt


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=CONFIG_PATH)
    parser.add_argument("--repo-root", type=Path, default=REPO)
    parser.add_argument("--artifact-root", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(build(args.config, args.repo_root, args.artifact_root), ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
