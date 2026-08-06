#!/usr/bin/env python3
"""Build the add-once LiDAR | MVS | C3 review package from frozen inputs."""
from __future__ import annotations

import argparse
from collections import defaultdict
import json
import os
from pathlib import Path
import shutil
from typing import Any, Mapping

import laspy
import numpy as np

from scripts.p2.c1_c2_shared_footprint_199_v3.build_cloudcompare_review10 import lod22_triangles, triangles_obj
from scripts.p2.c1_c2_shared_footprint_199_v1.run import canonical_json_bytes, exact_file, file_record, sha256_file, write_new


REPO = Path(__file__).resolve().parents[3]
CONFIG_PATH = REPO / "configs/p2/c2_c3_rendered_depth_shared_footprint_199_v1/web_v2.json"
CONDITIONS = ("C3_1", "C3_2")


def load_config(path: Path = CONFIG_PATH) -> dict[str, Any]:
    config = json.loads(path.read_text(encoding="utf-8"))
    if config.get("schema") != "jointbuildgs.p2.c2_c3_rendered_depth_shared_footprint_199.web.v1":
        raise RuntimeError("web config schema drifted")
    if config.get("status") != "USER_APPROVED_FOR_EXECUTION":
        raise RuntimeError("web config is not approved")
    if config["features"]["layout"] != ["LiDAR", "MVS", "C3"]:
        raise RuntimeError("three-panel layout drifted")
    if config["features"]["c3_conditions"] != ["C3_1", "C3_2"] or config["features"]["default_c3_condition"] != "C3_1":
        raise RuntimeError("C3 toggle contract drifted")
    if config["features"]["local_storage_key"] != "jointbuildgs-c1-c2-roofer-ox-v1":
        raise RuntimeError("localStorage compatibility drifted")
    if config["features"]["csv_fields"] != ["stable_id", "lidar_ox", "mvs_ox", "c3_1_ox", "c3_2_ox", "note"]:
        raise RuntimeError("CSV contract drifted")
    if config.get("official_PASS_usable", "missing") is not None or config.get("scientific_verdict", "missing") is not None:
        raise RuntimeError("verdict fields must remain null")
    return config


def _copy_base(source: Path, destination: Path) -> None:
    excluded = {"app.js", "index.html", "viewer_manifest.json", "README.md", "manifest_web_review199_exact_rows_v1.json", "run_receipt_v1.json"}
    for item in sorted(source.iterdir(), key=lambda path: path.name):
        if item.name in excluded:
            continue
        target = destination / item.name
        if item.is_dir():
            shutil.copytree(item, target)
        elif item.is_file() and not item.is_symlink():
            shutil.copyfile(item, target)
        else:
            raise RuntimeError(f"unsupported source viewer entry: {item}")


def _coordinate_hash(xyz: np.ndarray) -> np.ndarray:
    values = np.rint(np.asarray(xyz, dtype=np.float64) * 1000.0).astype(np.int64).astype(np.uint64, copy=False)
    value = (values[:, 0] * np.uint64(0x9E3779B185EBCA87)) ^ (values[:, 1] * np.uint64(0xC2B2AE3D27D4EB4F)) ^ (values[:, 2] * np.uint64(0x165667B19E3779F9))
    value ^= value >> np.uint64(30)
    value *= np.uint64(0xBF58476D1CE4E5B9)
    value ^= value >> np.uint64(27)
    value *= np.uint64(0x94D049BB133111EB)
    return value ^ (value >> np.uint64(31))


def deterministic_coordinate_sample(rows: np.ndarray, voxel_m: float, cap: int) -> np.ndarray:
    if not len(rows):
        return rows
    q = np.floor(rows[:, :3] / float(voxel_m)).astype(np.int64)
    hashes = _coordinate_hash(rows[:, :3])
    order = np.lexsort((hashes, q[:, 2], q[:, 1], q[:, 0]))
    sorted_q = q[order]
    starts = np.r_[0, np.flatnonzero(np.any(sorted_q[1:] != sorted_q[:-1], axis=1)) + 1]
    selected = order[starts]
    if len(selected) > cap:
        selected = selected[np.argsort(hashes[selected], kind="stable")[:cap]]
    selected_q = q[selected]
    selected = selected[np.lexsort((selected_q[:, 2], selected_q[:, 1], selected_q[:, 0]))]
    return rows[selected]


def collect_building_crops(
    source: Path, bboxes: Mapping[str, tuple[float, float, float, float]], voxel_m: float, cap: int,
) -> tuple[dict[str, np.ndarray], dict[str, int]]:
    chunks: dict[str, list[np.ndarray]] = defaultdict(list)
    raw_counts = {stable_id: 0 for stable_id in bboxes}
    tile_m = 32.0
    tile_to_ids: dict[tuple[int, int], list[str]] = defaultdict(list)
    for stable_id, (x0, y0, x1, y1) in bboxes.items():
        for tx in range(int(np.floor(x0 / tile_m)), int(np.floor(x1 / tile_m)) + 1):
            for ty in range(int(np.floor(y0 / tile_m)), int(np.floor(y1 / tile_m)) + 1):
                tile_to_ids[(tx, ty)].append(stable_id)
    with laspy.open(source) as reader:
        required = {"red", "green", "blue", "classification", "semantic_argmax", "semantic_prob_0", "semantic_prob_1", "semantic_prob_2", "semantic_prob_3", "view_support"}
        dimensions = set(reader.header.point_format.dimension_names)
        if not required.issubset(dimensions):
            raise RuntimeError(f"classified C3 audit dimensions missing: {sorted(required - dimensions)}")
        for points in reader.chunk_iterator(1_000_000):
            xyz = np.column_stack((np.asarray(points.x), np.asarray(points.y), np.asarray(points.z))).astype(np.float64)
            classification = np.asarray(points.classification, dtype=np.uint8)
            if not set(np.unique(classification)).issubset({1, 2, 6}):
                raise RuntimeError("unexpected classified C3 value")
            raw_rgb = np.column_stack((np.asarray(points.red), np.asarray(points.green), np.asarray(points.blue))).astype(np.float64)
            rgb = np.rint(np.clip(raw_rgb / 257.0, 0, 255)).astype(np.uint8)
            semantic = np.column_stack((
                np.asarray(points.semantic_argmax, dtype=np.uint8),
                np.asarray(points.semantic_prob_0, dtype=np.float32), np.asarray(points.semantic_prob_1, dtype=np.float32),
                np.asarray(points.semantic_prob_2, dtype=np.float32), np.asarray(points.semantic_prob_3, dtype=np.float32),
                np.asarray(points.view_support, dtype=np.uint16),
            ))
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
                    chunks[stable_id].append(np.column_stack((xyz[selected], classification[selected], rgb[selected], semantic[selected])).astype(np.float64))
    result = {}
    for stable_id in bboxes:
        rows = np.concatenate(chunks[stable_id]) if chunks[stable_id] else np.empty((0, 13), dtype=np.float64)
        result[stable_id] = deterministic_coordinate_sample(rows, voxel_m, cap)
    return result, raw_counts


def write_c3_ply(path: Path, rows: np.ndarray, origin: np.ndarray) -> None:
    dtype = np.dtype([
        ("x", "<f4"), ("y", "<f4"), ("z", "<f4"),
        ("red", "u1"), ("green", "u1"), ("blue", "u1"), ("classification", "u1"),
        ("semantic_argmax", "u1"),
        ("semantic_prob_0", "<f4"), ("semantic_prob_1", "<f4"), ("semantic_prob_2", "<f4"), ("semantic_prob_3", "<f4"),
        ("view_support", "<u2"),
    ])
    body = np.empty(len(rows), dtype=dtype)
    if len(rows):
        xyz = rows[:, :3] - origin
        body["x"], body["y"], body["z"] = xyz.T
        body["classification"] = rows[:, 3].astype(np.uint8)
        body["red"], body["green"], body["blue"] = rows[:, 4:7].astype(np.uint8).T
        body["semantic_argmax"] = rows[:, 7].astype(np.uint8)
        for index in range(4):
            body[f"semantic_prob_{index}"] = rows[:, 8 + index].astype(np.float32)
        body["view_support"] = rows[:, 12].astype(np.uint16)
    header = (
        "ply\nformat binary_little_endian 1.0\n"
        "comment actual classified C3 rendered-depth fused Roofer input crop; display-only deterministic sample\n"
        f"element vertex {len(rows)}\n"
        "property float x\nproperty float y\nproperty float z\n"
        "property uchar red\nproperty uchar green\nproperty uchar blue\nproperty uchar classification\n"
        "property uchar semantic_argmax\nproperty float semantic_prob_0\nproperty float semantic_prob_1\nproperty float semantic_prob_2\nproperty float semantic_prob_3\nproperty ushort view_support\nend_header\n"
    ).encode("ascii")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(header); stream.write(body.tobytes())


def _replace_once(text: str, old: str, new: str) -> str:
    if text.count(old) != 1:
        raise RuntimeError(f"application base drift for replacement: {old[:80]!r}")
    return text.replace(old, new)


def transform_app(text: str) -> str:
    text = _replace_once(text, "  mvsMesh: 0xe62dd2,", "  mvsMesh: 0xe62dd2,\n  c3Mesh: 0x8b5cf6,")
    text = _replace_once(text, "  mvsPointRgb: [1, 145 / 255, 35 / 255],", "  mvsPointRgb: [1, 145 / 255, 35 / 255],\n  c3PointRgb: [139 / 255, 92 / 255, 246 / 255],\n  otherRgb: [75 / 255, 85 / 255, 99 / 255],")
    text = _replace_once(text, "  sync: true,", "  sync: true,\n  c3Condition: 'C3_1',")
    text = _replace_once(text, "  'mvsReviewO', 'mvsReviewX', 'lidarReviewCurrent', 'mvsReviewCurrent',", "  'mvsReviewO', 'mvsReviewX', 'lidarReviewCurrent', 'mvsReviewCurrent',\n  'c3Condition', 'c3PanelLabel', 'c3Review', 'c3ReviewO', 'c3ReviewX', 'c3ReviewCurrent',")
    text = _replace_once(text, "  const building = method === 'lidar' ? COLORS.lidarPointRgb : COLORS.mvsPointRgb;", "  const building = method === 'lidar' ? COLORS.lidarPointRgb : method === 'mvs' ? COLORS.mvsPointRgb : COLORS.c3PointRgb;")
    text = _replace_once(text, "    const color = classifications[i] === 2 ? COLORS.groundRgb : building;", "    const color = classifications[i] === 2 ? COLORS.groundRgb : classifications[i] === 6 ? building : COLORS.otherRgb;")
    text = _replace_once(text, "    const spec = building[this.method];", "    const spec = this.method === 'c3' ? building.c3[state.c3Condition] : building[this.method];")
    text = _replace_once(text, "      const color = this.method === 'lidar' ? COLORS.lidarMesh : COLORS.mvsMesh;", "      const color = this.method === 'lidar' ? COLORS.lidarMesh : this.method === 'mvs' ? COLORS.mvsMesh : COLORS.c3Mesh;")
    text = _replace_once(text, "    const combined = bounds[0].clone().union(bounds[1]);", "    const combined = bounds.slice(1).reduce((value, item) => value.union(item), bounds[0].clone());")
    text = _replace_once(text, "    viewers[1].orbit.copyFrom(viewers[0].orbit);\n    viewers[1].orbit.apply(viewers[1].camera);", "    for (const viewer of viewers.slice(1)) { viewer.orbit.copyFrom(viewers[0].orbit); viewer.orbit.apply(viewer.camera); }")
    text = _replace_once(text, "    elements.buildingStatus.innerHTML = `LiDAR <strong>${building.lidar.technical_status}</strong> · MVS <strong>${building.mvs.technical_status}</strong>`;", "    elements.buildingStatus.innerHTML = `LiDAR <strong>${building.lidar.technical_status}</strong> · MVS <strong>${building.mvs.technical_status}</strong> · ${state.c3Condition} <strong>${building.c3[state.c3Condition].technical_status}</strong>`;")
    text = _replace_once(text, "  elements.syncCamera.addEventListener('change', (event) => { state.sync = event.target.checked; });", "  elements.syncCamera.addEventListener('change', (event) => { state.sync = event.target.checked; });\n  elements.c3Condition.addEventListener('change', async (event) => {\n    saveReviewForm(); state.c3Condition = event.target.value; elements.c3PanelLabel.textContent = `${state.c3Condition} rendered-depth fused cloud + Roofer`;\n    const viewer = viewers[2]; const saved = new OrbitState(); saved.copyFrom(viewer.orbit);\n    elements.loading.hidden = false;\n    try {\n      const building = manifest.buildings[state.buildingIndex];\n      await viewer.load(building); viewer.orbit.copyFrom(saved); viewer.orbit.apply(viewer.camera);\n      elements.buildingStatus.innerHTML = `LiDAR <strong>${building.lidar.technical_status}</strong> · MVS <strong>${building.mvs.technical_status}</strong> · ${state.c3Condition} <strong>${building.c3[state.c3Condition].technical_status}</strong>`;\n      drawMiniMap(building); loadReviewForm(building.stable_id);\n    }\n    finally { elements.loading.hidden = true; }\n  });")
    text = _replace_once(text, "  setReviewButtons('mvs', review.mvs || '');\n  elements.reviewNote.value", "  setReviewButtons('mvs', review.mvs || '');\n  setReviewButtons('c3', review[state.c3Condition === 'C3_1' ? 'c3_1' : 'c3_2'] || '');\n  elements.reviewNote.value")
    text = _replace_once(text, "    mvs: selectedReviewValue('mvs'),\n    note:", "    mvs: selectedReviewValue('mvs'),\n    c3_1: state.c3Condition === 'C3_1' ? selectedReviewValue('c3') : (previous.c3_1 || ''),\n    c3_2: state.c3Condition === 'C3_2' ? selectedReviewValue('c3') : (previous.c3_2 || ''),\n    note:")
    start = "  const rows = [[\n    'population_index', 'stable_id', 'lidar_technical_status', 'mvs_technical_status',\n    'criterion_id', 'lidar_human_ox', 'mvs_human_ox', 'reviewer_note',\n  ]];"
    text = _replace_once(text, start, "  const rows = [['stable_id', 'lidar_ox', 'mvs_ox', 'c3_1_ox', 'c3_2_ox', 'note']];")
    old = "    rows.push([\n      building.population_index, building.stable_id,\n      building.lidar.technical_status, building.mvs.technical_status,\n      manifest.review_criterion_id, review.lidar || '', review.mvs || '', review.note || '',\n    ]);"
    text = _replace_once(text, old, "    rows.push([building.stable_id, review.lidar || '', review.mvs || '', review.c3_1 || '', review.c3_2 || '', review.note || '']);")
    text = _replace_once(text, "  if (state.sync && viewers.length === 2) {\n    const source = viewers[state.activeViewer];\n    const target = viewers[1 - state.activeViewer];\n    target.orbit.copyFrom(source.orbit);\n    target.orbit.apply(target.camera);\n  }", "  if (state.sync && viewers.length === 3) {\n    const source = viewers[state.activeViewer];\n    for (const target of viewers) if (target !== source) { target.orbit.copyFrom(source.orbit); target.orbit.apply(target.camera); }\n  }")
    text = _replace_once(text, "  new ReviewViewer('mvsViewport', 'mvsStats', 'mvs', 1),", "  new ReviewViewer('mvsViewport', 'mvsStats', 'mvs', 1),\n  new ReviewViewer('c3Viewport', 'c3Stats', 'c3', 2),")
    text = _replace_once(text, "  const mvsCount = building.mvs.point_count;", "  const mvsCount = building.mvs.point_count;\n  const c3Count = building.c3[state.c3Condition].point_count;")
    text = _replace_once(text, "  elements.miniMapStatus.textContent = `LiDAR ${lidarCount.toLocaleString()} · MVS ${mvsCount.toLocaleString()}${absence}`;", "  elements.miniMapStatus.textContent = `LiDAR ${lidarCount.toLocaleString()} · MVS ${mvsCount.toLocaleString()} · ${state.c3Condition} ${c3Count.toLocaleString()}${absence}`;")
    text = _replace_once(text, "  const stride = hasClassification ? 16 : 15;", "  const hasC3Audit = header.includes('property uchar semantic_argmax');\n  const stride = hasC3Audit ? 35 : hasClassification ? 16 : 15;")
    return text


def transform_index(text: str) -> str:
    text = _replace_once(text, "JointBuildGS C1/C2 Roofer 3D Review", "JointBuildGS C2/C3 Roofer 3D Review")
    text = _replace_once(text, "grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);", "grid-template-columns: repeat(3, minmax(340px, 1fr)); overflow-x: auto;")
    text = _replace_once(text, "#viewports { grid-template-columns: 1fr; grid-template-rows: minmax(0, 1fr) minmax(0, 1fr); }", "#viewports { grid-template-columns: repeat(3, minmax(340px, 1fr)); grid-template-rows: minmax(0, 1fr); overflow-x: auto; }")
    mvs_review_end = "      <span class=\"review-current\" id=\"mvsReviewCurrent\">미평가</span>\n    </div>"
    c3_review = mvs_review_end + "\n    <div class=\"review-field\">\n      <label for=\"c3Condition\">C3 조건 / Roofer O/X</label>\n      <select id=\"c3Condition\"><option value=\"C3_1\" selected>C3-1</option><option value=\"C3_2\">C3-2</option></select>\n      <div class=\"review-buttons\" id=\"c3Review\" role=\"group\" aria-label=\"C3 Roofer O/X\">\n        <button class=\"review-choice\" id=\"c3ReviewO\" type=\"button\" data-review-method=\"c3\" data-value=\"O\" aria-pressed=\"false\">O</button>\n        <button class=\"review-choice\" id=\"c3ReviewX\" type=\"button\" data-review-method=\"c3\" data-value=\"X\" aria-pressed=\"false\">X</button>\n      </div><span class=\"review-current\" id=\"c3ReviewCurrent\">미평가</span>\n    </div>"
    text = _replace_once(text, mvs_review_end, c3_review)
    text = _replace_once(text, "<option value=\"condition\">조건 단색</option>", "<option value=\"condition\">Class 2/6</option>")
    third = "    <section class=\"viewport-shell\" aria-label=\"C3 3D 검토 화면\">\n      <div class=\"viewport\" id=\"c3Viewport\"></div>\n      <div class=\"panel-label\" id=\"c3PanelLabel\">C3_1 rendered-depth fused cloud + Roofer</div>\n      <div class=\"panel-stats\" id=\"c3Stats\">불러오는 중</div>\n    </section>\n"
    text = _replace_once(text, "    </section>\n  </div>\n</div>\n<div id=\"loading\">", "    </section>\n" + third + "  </div>\n</div>\n<div id=\"loading\">")
    # Explicit requested order: O/X controls above the compact photo row.
    review_start = text.index('  <div id="reviewbar">')
    photo_start = text.index('  <section id="photoDrawer"')
    if photo_start < review_start:
        photo_end = text.index('  </section>', photo_start) + len('  </section>\n')
        photo = text[photo_start:photo_end]
        text = text[:photo_start] + text[photo_end:]
        review_start = text.index('  <div id="reviewbar">')
        text = text[:review_start] + photo + text[review_start:]
        # The insertion above kept photo first; swap the two complete blocks.
        photo_start = text.index('  <section id="photoDrawer"')
        photo_end = text.index('  </section>', photo_start) + len('  </section>\n')
        review_start = text.index('  <div id="reviewbar">')
        review_end = text.index('  </div>\n  <div id="tools">', review_start) + len('  </div>\n')
        photo, review = text[photo_start:photo_end], text[review_start:review_end]
        text = text[:photo_start] + review + photo + text[review_end:]
    return text


def build(config_path: Path, repo_root: Path, artifact_root: Path) -> dict[str, Any]:
    config = load_config(config_path)
    output_root = artifact_root / config["output_relative_root"]
    partial = output_root.with_name(output_root.name + ".partial")
    if output_root.exists() or partial.exists():
        raise RuntimeError("fresh add-once web namespace required")
    partial.mkdir(parents=True)
    source_spec = config["source_viewer"]
    source_root = artifact_root / source_spec["relative_root"]
    exact_file(source_root / source_spec["viewer_manifest_path"], {"bytes": source_spec["viewer_manifest_bytes"], "sha256": source_spec["viewer_manifest_sha256"]})
    exact_file(source_root / source_spec["artifact_manifest_path"], {"bytes": source_spec["artifact_manifest_bytes"], "sha256": source_spec["artifact_manifest_sha256"]})
    source_viewer = json.loads((source_root / source_spec["viewer_manifest_path"]).read_text(encoding="utf-8"))
    if len(source_viewer["buildings"]) != 199 or source_viewer.get("scientific_verdict", "missing") is not None:
        raise RuntimeError("source viewer population/verdict drifted")
    _copy_base(source_root, partial)
    c3_root = artifact_root / config["c3_result_relative_root"]
    finalized = json.loads((c3_root / "control/finalized_v1.json").read_text(encoding="utf-8"))
    if finalized["building_count"] != 199 or finalized["status"] != "TECHNICAL_COMPLETE_WITH_EXPLICIT_MISSINGNESS" or finalized.get("scientific_verdict", "missing") is not None:
        raise RuntimeError("C3 full199 result is not ready")
    status_rows = [json.loads(line) for line in (c3_root / "results/building_method_results_v1.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    status = {(row["stable_id"], row["condition_id"]): row for row in status_rows}
    origin = np.asarray(config["display"]["scene_local_origin_xyz"], dtype=np.float64)
    bboxes = {row["stable_id"]: tuple(map(float, row["bbox_world_xy"])) for row in source_viewer["buildings"]}
    c3_specs: dict[str, dict[str, Any]] = {stable_id: {} for stable_id in bboxes}
    source_records = {}
    crop_receipts = []
    for condition_id in CONDITIONS:
        classified = c3_root / "work" / condition_id / "classified_scene.laz"
        source_records[condition_id] = file_record(classified, artifact_root)
        details, raw_counts = collect_building_crops(classified, bboxes, float(config["display"]["voxel_m"]), int(config["display"]["maximum_points_per_building_condition"]))
        cityjson = json.loads((c3_root / "work" / condition_id / "assembled.city.json").read_text(encoding="utf-8"))
        for building in source_viewer["buildings"]:
            stable_id = building["stable_id"]
            index = int(building["population_index"])
            directory = partial / f"assets/B{index:03d}_{stable_id}"
            point_path = directory / f"{'07' if condition_id == 'C3_1' else '09'}_{condition_id}_POINTS_rgb_class_semantic.ply"
            write_c3_ply(point_path, details[stable_id], origin)
            triangles = lod22_triangles(cityjson, stable_id)
            roofer_path = None
            if triangles:
                roofer_path = directory / f"{'08' if condition_id == 'C3_1' else '10'}_{condition_id}_ROOFER.obj"
                write_new(roofer_path, triangles_obj(condition_id, "unused.mtl", condition_id.lower(), triangles, origin))
            receipt = {
                "condition_id": condition_id, "stable_id": stable_id,
                "source_cloud": source_records[condition_id], "crop_bbox_world_xy": list(bboxes[stable_id]),
                "raw_crop_point_count": int(raw_counts[stable_id]), "display_point_count": int(len(details[stable_id])),
                "sampling_rule": config["display"]["sampling_rule"], "voxel_m": config["display"]["voxel_m"],
                "coordinate_quantization_m": config["display"]["coordinate_quantization_m"],
                "maximum_points": config["display"]["maximum_points_per_building_condition"],
            }
            crop_receipts.append(receipt)
            state = status[(stable_id, condition_id)]
            c3_specs[stable_id][condition_id] = {
                "point_count": int(len(details[stable_id])), "points": point_path.relative_to(partial).as_posix(),
                "roofer": None if roofer_path is None else roofer_path.relative_to(partial).as_posix(),
                "roofer_triangles": int(len(triangles)), "technical_status": state["status"],
                "reason": state["reason"], "display_receipt": receipt,
            }
    viewer = dict(source_viewer)
    viewer["schema"] = "jointbuildgs.p2.c2_c3_rendered_depth_shared_footprint_199.web_viewer.v1"
    viewer["task_id"] = config["task_id"]
    viewer["status"] = "READY_FOR_HUMAN_WEB_REVIEW_ON_TEMPORARY_PORT"
    viewer["comparison_label"] = "shared-footprint technical diagnostic"
    viewer["features"] = {**viewer.get("features", {}), **config["features"]}
    viewer["buildings"] = [{**row, "c3": c3_specs[row["stable_id"]]} for row in source_viewer["buildings"]]
    viewer["official_PASS_usable"] = None; viewer["scientific_verdict"] = None
    write_new(partial / "viewer_manifest.json", canonical_json_bytes(viewer))
    for name, spec in config["application_sources"].items():
        exact_file(repo_root / spec["path"], spec)
    write_new(partial / "app.js", transform_app((repo_root / config["application_sources"]["app"]["path"]).read_text(encoding="utf-8")).encode("utf-8"))
    write_new(partial / "index.html", transform_index((repo_root / config["application_sources"]["index"]["path"]).read_text(encoding="utf-8")).encode("utf-8"))
    write_new(partial / "README.md", b"# JointBuildGS LiDAR | MVS | C3 web review\n\nShared-footprint technical diagnostic. C3 is checkpoint rendered-depth fused input, never raw Gaussian centres. Scientific verdict and official PASS_usable are null.\n")
    receipt_path = partial / "web_receipt_v1.json"
    receipt = {
        "schema": "jointbuildgs.p2.c2_c3_rendered_depth_shared_footprint_199.web_receipt.v1",
        "task_id": config["task_id"], "status": "READY_FOR_TEMPORARY_PORT_VALIDATION",
        "building_count": 199, "c3_asset_condition_count": 2,
        "source_clouds": source_records, "crop_receipt_count": len(crop_receipts),
        "crop_receipts": crop_receipts, "source_viewer_manifest": file_record(source_root / "viewer_manifest.json", artifact_root),
        "viewer_manifest": file_record(partial / "viewer_manifest.json", partial),
        "application": {name: file_record(partial / name, partial) for name in ("app.js", "index.html")},
        "local_storage_key_preserved": True, "existing_lidar_mvs_assets_reused": True,
        "comparison_label": "shared-footprint technical diagnostic",
        "official_PASS_usable": None, "scientific_verdict": None,
    }
    write_new(receipt_path, canonical_json_bytes(receipt))
    manifest = {
        "schema": "jointbuildgs.p2.c2_c3_rendered_depth_shared_footprint_199.web_manifest.v1",
        "task_id": config["task_id"], "status": "READY_FOR_TEMPORARY_PORT_VALIDATION",
        "viewer_manifest": file_record(partial / "viewer_manifest.json", partial),
        "receipt": file_record(receipt_path, partial),
        "application": receipt["application"], "scientific_verdict": None, "official_PASS_usable": None,
    }
    write_new(partial / "manifest_web_v1.json", canonical_json_bytes(manifest))
    os.rename(partial, output_root)
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
