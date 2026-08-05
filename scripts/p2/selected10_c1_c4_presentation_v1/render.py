#!/usr/bin/env python3
"""Render ten 17-row by four-view C1/C2/matched-C3-2/C4 pages and one PDF."""

from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime, timezone
import hashlib
import html
import json
import math
from pathlib import Path
import textwrap
from typing import Any, Mapping, Sequence

import cv2
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.collections import PolyCollection
from mpl_toolkits.mplot3d.art3d import Poly3DCollection
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from scripts.evidence_and_attributes.population_analysis import population_aux_v3 as projection
from scripts.p2.c1_c2_c3_consolidated_results_v1.compose_v4 import lod2_zlim, shifted_lod2
from scripts.p2.c1_c2_c3_consolidated_results_v1.compose_v5 import (
    VIEWS,
    consensus_panels,
    draw_footprint,
    draw_section_locator,
    mesh_panels,
    panel_axes,
    save_panel,
    surface_faces,
    surface_panels,
    triangle_panel,
)
from scripts.p2.c1_c2_oracle_c3_extract_v1.contract import load_building_references
from scripts.p2.c3_tsdf_roof_diagnostic_v1.render import _principal_frame
from scripts.p2.c4_utarget199_postprocess_v1.render_case_sheets import _checkpoint_arrays, _native_crop
from scripts.p2.utarget199_contract_results_v1.contract import load_config as load_census_config
from scripts.p2.utarget199_contract_results_v1.render_case_sheets import (
    BBox,
    PointSet,
    camera_context,
    city_file,
    load_geometry,
    rows,
)
from scripts.p2.utarget199_c1_c4_matrix_v1.render import condition_tables, postprocess_tables
from scripts.p2.utarget199_presentation_v5.render import load_references
from src.geospatial.projection_datum import as_ellipsoidal_points


REPO = Path(__file__).resolve().parents[3]
CONFIG_PATH = REPO / "configs/p2/selected10_c1_c4_presentation_v1/render_v1.json"
SEMANTIC_COLORS = np.asarray([[0.68, 0.70, 0.73], [0.08, 0.55, 0.82], [0.90, 0.45, 0.08]], dtype=np.float64)


def load_config() -> dict[str, Any]:
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def sha256_file(path: Path) -> tuple[int, str]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
            size += len(chunk)
    return size, digest.hexdigest()


def record(path: Path, root: Path) -> dict[str, Any]:
    size, digest = sha256_file(path)
    return {"path": path.relative_to(root).as_posix(), "bytes": size, "sha256": digest}


def write_new(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(data)


def write_json(path: Path, body: Mapping[str, Any]) -> None:
    write_new(path, (json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode())


def validate_config(config: Mapping[str, Any]) -> None:
    if config.get("schema") != "jointbuildgs.p2.selected10_c1_c4_presentation.v1":
        raise RuntimeError("unexpected selected10 schema")
    if config.get("status") != "APPROVED_BY_USER_FOR_SELECTED10_17ROW_PRESENTATION":
        raise RuntimeError("selected10 presentation is not active")
    if len(config["building_ids"]) != 10 or len(set(config["building_ids"])) != 10:
        raise RuntimeError("selected10 membership drifted")
    if tuple(config["views"]) != VIEWS or len(config["row_order"]) != 17:
        raise RuntimeError("17-row/four-view contract drifted")
    presentation = config["presentation"]
    if presentation["separate_principal_section_pages"] != 0 or not presentation["missing_not_run_failure_preserved"]:
        raise RuntimeError("presentation boundary drifted")
    if presentation["c5_state"] != "NOT_RUN":
        raise RuntimeError("C5 boundary drifted")
    if config.get("official_G3_G4_PASS_usable", "missing") is not None or config.get("scientific_verdict", "missing") is not None:
        raise RuntimeError("official PASS and scientific verdict must remain null")


def verify_exact(path: Path, expected: str, label: str) -> dict[str, Any]:
    size, actual = sha256_file(path)
    if actual != expected:
        raise RuntimeError(f"{label} exact hash differs: {actual}")
    return {"path": path.as_posix(), "bytes": size, "sha256": actual}


def placeholder(path: Path, role: str, status: str, view: str) -> Path:
    width, height = 960, 720
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default(size=34)
    small = ImageFont.load_default(size=26)
    draw.rectangle((4, 4, width - 5, height - 5), outline="#b8bec8", width=4)
    draw.text((width // 2, 150), role, fill="#1f2937", font=font, anchor="mm")
    status_lines = wrap_display_text(status, 30)[:5]
    draw.multiline_text(
        (width // 2, 300),
        "\n".join(status_lines),
        fill="#dc2626",
        font=font,
        anchor="mm",
        align="center",
        spacing=10,
    )
    draw.text((width // 2, 430), view.replace("_", " "), fill="#475569", font=small, anchor="mm")
    draw.text((width // 2, 560), "scientific_verdict=null", fill="#64748b", font=small, anchor="mm")
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, format="PNG", compress_level=5)
    return path


def placeholders(root: Path, role: str, status: str) -> list[Path]:
    return [placeholder(root / f"{role.lower()}_{view}.png", role, status, view) for view in VIEWS]


def wrap_display_text(value: str, width: int) -> list[str]:
    """Wrap long receipt tokens at underscores while retaining their exact spelling."""
    result: list[str] = []
    for paragraph in value.splitlines() or [""]:
        breakable = paragraph.replace("_", "_ ")
        lines = textwrap.wrap(breakable, width=width, break_long_words=False, break_on_hyphens=False) or [""]
        result.extend(line.replace("_ ", "_") for line in lines)
    return result


def point_panels(root: Path, points: PointSet, reference: Any, zlim: tuple[float, float], prefix: str) -> list[Path]:
    if not len(points.xyz):
        return placeholders(root, prefix.upper(), "MISSING_OR_NOT_RUN")
    colors = np.tile(np.asarray([[0.45, 0.48, 0.52]]), (len(points.xyz), 1))
    if points.classification is not None:
        colors[points.classification == 6] = (0.05, 0.45, 0.78)
        colors[points.classification == 2] = (0.63, 0.32, 0.12)
    result = []
    for view in VIEWS:
        path = root / f"{prefix}_{view}.png"
        from scripts.p2.c1_c2_c3_consolidated_results_v1.compose_v5 import point_panel
        point_panel(path, points.xyz, colors, reference, view, zlim)
        result.append(path)
    return result


def native_semantic_panels(root: Path, native: Mapping[str, np.ndarray], bbox: BBox, reference: Any, zlim: tuple[float, float], prefix: str) -> list[Path]:
    indices = _native_crop(native, bbox)
    if not len(indices):
        return placeholders(root, prefix.upper(), "NO_NATIVE_GAUSSIANS")
    if len(indices) > 2500:
        indices = indices[np.linspace(0, len(indices) - 1, 2500, dtype=int)]
    centers = native["means"][indices]
    rotations = native["rotations"][indices]
    scales = native["scales"][indices]
    u = rotations[:, :, 0] * scales[:, 0:1]
    v = rotations[:, :, 1] * scales[:, 1:2]
    quads = np.stack((centers - u - v, centers + u - v, centers + u + v, centers - u + v), axis=1)
    faces = []
    colors = []
    for quad, label in zip(quads, native["labels"][indices]):
        faces.extend((quad[[0, 1, 2]], quad[[0, 2, 3]]))
        color = SEMANTIC_COLORS[min(int(label), len(SEMANTIC_COLORS) - 1)]
        colors.extend((color, color))
    result = []
    for view in VIEWS:
        path = root / f"{prefix}_{view}.png"
        triangle_panel(path, faces, colors, reference, view, zlim)
        result.append(path)
    return result


def output_panels(root: Path, surfaces: Sequence[Any], reference: Any, zlim: tuple[float, float], prefix: str, status: str) -> list[Path]:
    if not surfaces:
        return placeholders(root, prefix.upper(), status)
    return surface_panels(root, surfaces, reference, zlim, prefix)


def building_output_panels(
    root: Path,
    row: Mapping[str, Any],
    surfaces: Sequence[Any],
    reference: Any,
    zlim: tuple[float, float],
    prefix: str,
) -> list[Path]:
    """Never present a shared/multi/empty component as a building-level Roofer output."""
    if row.get("G0_generated") is not True or row.get("one_to_one_building_component") is not True:
        status = f"FAILED: NO BUILDING-LEVEL OUTPUT\nASSOCIATION={row.get('association_status', 'UNASSOCIATED')}"
        return placeholders(root, prefix.upper(), status)
    return output_panels(root, surfaces, reference, zlim, prefix, "FAILED_NO_ROOF_GEOMETRY")


def roofer_attributes(task_root: Path, unit: Mapping[str, Any] | None) -> dict[str, Any]:
    """Read the component-level Roofer receipt attributes without changing geometry."""
    if not unit:
        return {}
    path = city_file(task_root / unit["output_directory"])
    if path is None:
        return {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        feature = json.loads(line)
        for city_object in feature.get("CityObjects", {}).values():
            attributes = city_object.get("attributes")
            if attributes:
                return dict(attributes)
    return {}


def roof_rings(reference: Any) -> list[np.ndarray]:
    return [np.asarray(ring, dtype=np.float64) for semantic, ring in reference.surface_rings if semantic == "RoofSurface"]


def camera_candidates(reference: Any, cameras: Mapping[str, Any], model: tuple[int, int, np.ndarray], scene_ref: Mapping[str, Any], visible: set[str]) -> list[dict[str, Any]]:
    width, height, params = model
    rings = roof_rings(reference)
    points = np.concatenate(rings)
    center_orthometric = points.mean(axis=0)
    center = as_ellipsoidal_points(center_orthometric.reshape(1, 3))[0]
    _fp_center, principal, cross = _principal_frame(reference)
    candidates = []
    for camera in cameras.values():
        if camera.name not in visible:
            continue
        uv, front = projection.project(points, camera, width, height, params, scene_ref)
        inside = front & np.isfinite(uv).all(axis=1) & (uv[:, 0] >= 0) & (uv[:, 0] < width) & (uv[:, 1] >= 0) & (uv[:, 1] < height)
        coverage = float(np.mean(inside))
        if coverage < 0.45:
            continue
        valid = uv[inside]
        area = float(np.ptp(valid[:, 0]) * np.ptp(valid[:, 1])) if len(valid) else 0.0
        if area < 2500.0:
            continue
        vector = np.asarray(camera.center, dtype=np.float64) - center
        vector /= max(float(np.linalg.norm(vector)), 1e-12)
        nadir = math.degrees(math.acos(float(np.clip(vector[2], -1.0, 1.0))))
        horizontal = vector[:2]
        horizontal /= max(float(np.linalg.norm(horizontal)), 1e-12)
        candidates.append({
            "camera": camera,
            "coverage": coverage,
            "area_px2": area,
            "nadir_deg": nadir,
            "principal_dot": float(horizontal @ principal),
            "cross_dot": float(horizontal @ cross),
        })
    return candidates


def select_cameras(candidates: Sequence[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    if not candidates:
        return {}
    remaining = list(candidates)
    selected: dict[str, dict[str, Any]] = {}
    top = min(remaining, key=lambda row: row["nadir_deg"] - 0.000002 * row["area_px2"])
    selected["TOP"] = top
    remaining.remove(top)
    if remaining:
        principal = max(remaining, key=lambda row: abs(row["cross_dot"]) + 0.000001 * row["area_px2"])
        selected["PRINCIPAL_SECTION"] = principal
        remaining.remove(principal)
    if remaining:
        positive = [row for row in remaining if row["principal_dot"] >= 0]
        first = max(positive or remaining, key=lambda row: row["nadir_deg"] + 0.000001 * row["area_px2"])
        selected["OBLIQUE_1"] = first
        remaining.remove(first)
    if remaining:
        negative = [row for row in remaining if row["principal_dot"] < 0]
        second = max(negative or remaining, key=lambda row: row["nadir_deg"] + 0.000001 * row["area_px2"])
        selected["OBLIQUE_2"] = second
    return selected


def letterbox(image: np.ndarray, width: int = 960, height: int = 720) -> np.ndarray:
    scale = min(width / image.shape[1], height / image.shape[0])
    resized = cv2.resize(image, (max(1, int(image.shape[1] * scale)), max(1, int(image.shape[0] * scale))), interpolation=cv2.INTER_AREA)
    canvas = np.full((height, width, 3), 245, dtype=np.uint8)
    x = (width - resized.shape[1]) // 2
    y = (height - resized.shape[0]) // 2
    canvas[y:y + resized.shape[0], x:x + resized.shape[1]] = resized
    return canvas


def roofline_panels(root: Path, artifact_root: Path, census: Mapping[str, Any], reference: Any, cameras: Mapping[str, Any], model: tuple[int, int, np.ndarray], scene_ref: Mapping[str, Any], visible: set[str], stable_id: str) -> tuple[list[Path], list[dict[str, Any]]]:
    candidates = camera_candidates(reference, cameras, model, scene_ref, visible)
    selected = select_cameras(candidates)
    width, height, params = model
    panels = []
    receipts = []
    rings = roof_rings(reference)
    image_directory = artifact_root / census["inputs"]["rgb_context"]["image_directory_relative_path"]
    for view in VIEWS:
        path = root / f"roofline_{view}.png"
        row = selected.get(view)
        if row is None:
            panels.append(placeholder(path, "2024 RGB + 2022 ROOFLINE", "NO_VALID_CAMERA", view))
            receipts.append({"stable_id": stable_id, "view": view, "status": "NO_VALID_CAMERA", "camera": None})
            continue
        camera = row["camera"]
        image = cv2.imread(str(image_directory / camera.name), cv2.IMREAD_COLOR)
        if image is None:
            panels.append(placeholder(path, "2024 RGB + 2022 ROOFLINE", "IMAGE_MISSING", view))
            receipts.append({"stable_id": stable_id, "view": view, "status": "IMAGE_MISSING", "camera": camera.name})
            continue
        projected = []
        for ring in rings:
            uv, front = projection.project(ring, camera, width, height, params, scene_ref)
            valid = front & np.isfinite(uv).all(axis=1)
            if np.count_nonzero(valid) >= 2:
                points = np.rint(uv[valid]).astype(np.int32)
                cv2.polylines(image, [points], True, (0, 190, 255), 10, cv2.LINE_AA)
                projected.append(uv[valid])
        all_uv = np.concatenate(projected)
        x0, y0 = np.min(all_uv, axis=0)
        x1, y1 = np.max(all_uv, axis=0)
        margin = max(x1 - x0, y1 - y0) * 0.65 + 100
        xa, ya = max(0, int(x0 - margin)), max(0, int(y0 - margin))
        xb, yb = min(image.shape[1], int(x1 + margin)), min(image.shape[0], int(y1 + margin))
        crop = image[ya:yb, xa:xb]
        canvas = letterbox(crop)
        label = f"{view.replace('_', ' ')} | {camera.name} | coverage={row['coverage']:.0%}"
        cv2.rectangle(canvas, (0, 0), (960, 52), (255, 255, 255), -1)
        cv2.putText(canvas, label, (16, 36), cv2.FONT_HERSHEY_SIMPLEX, 0.72, (25, 25, 25), 2, cv2.LINE_AA)
        path.parent.mkdir(parents=True, exist_ok=True)
        if not cv2.imwrite(str(path), canvas, [cv2.IMWRITE_PNG_COMPRESSION, 5]):
            raise RuntimeError(f"roofline panel write failed: {path}")
        panels.append(path)
        receipts.append({
            "stable_id": stable_id,
            "view": view,
            "status": "PROJECTED",
            "camera": camera.name,
            "coverage_fraction": row["coverage"],
            "projected_area_px2": row["area_px2"],
            "nadir_deg": row["nadir_deg"],
            "principal_dot": row["principal_dot"],
            "cross_dot": row["cross_dot"],
        })
    return panels, receipts


def compose_page(path: Path, stable_id: str, subtitle: str, row_specs: Sequence[tuple[str, str, Sequence[Path]]], zlim: tuple[float, float]) -> None:
    cell_w, cell_h, label_w, header_h = 760, 540, 480, 260
    canvas = np.full((header_h + len(row_specs) * cell_h, label_w + 4 * cell_w, 3), 255, dtype=np.uint8)
    cv2.putText(canvas, stable_id, (28, 56), cv2.FONT_HERSHEY_SIMPLEX, 1.30, (18, 18, 18), 3, cv2.LINE_AA)
    cv2.putText(canvas, subtitle, (28, 112), cv2.FONT_HERSHEY_SIMPLEX, 0.82, (40, 40, 40), 2, cv2.LINE_AA)
    cv2.putText(canvas, f"matched C3=C3-2 | one PCA cut | LoD2 common Z {zlim[0]:.1f}..{zlim[1]:.1f}m | PASS=null", (28, 162), cv2.FONT_HERSHEY_SIMPLEX, 0.72, (92, 55, 12), 2, cv2.LINE_AA)
    for index, label in enumerate(("TOP + A/B VIEW", "OBLIQUE 1", "OBLIQUE 2", "PCA PRINCIPAL")):
        cv2.putText(canvas, label, (label_w + index * cell_w + 22, 226), cv2.FONT_HERSHEY_SIMPLEX, 0.86, (20, 20, 20), 2, cv2.LINE_AA)
    for row_index, (label, status, panels) in enumerate(row_specs):
        if len(panels) != 4:
            raise RuntimeError(f"row does not have four panels: {label}")
        y0 = header_h + row_index * cell_h
        cv2.rectangle(canvas, (0, y0), (label_w - 1, y0 + cell_h - 1), (243, 245, 248), -1)
        cv2.putText(canvas, f"{row_index + 1:02d}  {label}", (22, y0 + 72), cv2.FONT_HERSHEY_SIMPLEX, 0.84, (24, 24, 24), 2, cv2.LINE_AA)
        wrapped = wrap_display_text(status, 38)
        for line_index, line in enumerate(wrapped[:6]):
            color = (28, 28, 28) if not any(word in line for word in ("FAILED", "NOT_RUN", "MISSING")) else (30, 30, 200)
            cv2.putText(canvas, line, (22, y0 + 126 + 43 * line_index), cv2.FONT_HERSHEY_SIMPLEX, 0.61, color, 2, cv2.LINE_AA)
        for column, panel in enumerate(panels):
            image = cv2.imread(str(panel), cv2.IMREAD_COLOR)
            if image is None:
                raise RuntimeError(f"unreadable panel: {panel}")
            image = cv2.resize(image, (cell_w, cell_h), interpolation=cv2.INTER_AREA)
            x0 = label_w + column * cell_w
            canvas[y0:y0 + cell_h, x0:x0 + cell_w] = image
    path.parent.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(str(path), canvas, [cv2.IMWRITE_PNG_COMPRESSION, 5]):
        raise RuntimeError(f"page write failed: {path}")


def status_text(row: Mapping[str, Any], prefix: str = "") -> str:
    return f"{prefix} assoc={row.get('association_status')} G0={row.get('G0_generated')} G1={row.get('G1_schema_semantic')}"


def run(
    output_root: Path,
    artifact_root: Path,
    source_commit: str,
    run_id: str,
    validation_building_id: str | None = None,
) -> dict[str, Any]:
    config = load_config()
    validate_config(config)
    if output_root.exists() and any(output_root.iterdir()):
        raise RuntimeError("fresh add-once selected10 namespace required")
    output_root.mkdir(parents=True, exist_ok=True)
    source = config["sources"]
    c12_root = artifact_root / source["c1_c2_contract_relative_root"]
    c3_root = artifact_root / source["c3_postprocess_relative_root"]
    c4_root = artifact_root / source["c4_postprocess_relative_root"]
    diagnostic = artifact_root / source["c3_mesh_diagnostic_relative_root"]
    sample_v5 = artifact_root / source["sample_v5_relative_root"]
    checks = {
        "c1_c2_metrics": verify_exact(c12_root / "results/building_method_metrics_v1.jsonl", config["exact_hashes"]["c1_c2_metric_sha256"], "C1/C2 metrics"),
        "c3_metrics": verify_exact(c3_root / "results/building_condition_metrics_v1.jsonl", config["exact_hashes"]["c3_metric_sha256"], "C3 metrics"),
        "c4_metrics": verify_exact(c4_root / "results/building_c4_metrics_v1.jsonl", config["exact_hashes"]["c4_metric_sha256"], "C4 metrics"),
        "c3_checkpoint": verify_exact(artifact_root / source["c3_checkpoint_relative_path"], config["exact_hashes"]["c3_checkpoint_sha256"], "C3 checkpoint"),
        "c4_checkpoint": verify_exact(artifact_root / source["c4_checkpoint_relative_path"], config["exact_hashes"]["c4_checkpoint_sha256"], "C4 checkpoint"),
    }
    lod2_paths = [artifact_root / value for value in source["lod2_relative_paths"]]
    checks["lod2"] = [verify_exact(path, digest, "LoD2") for path, digest in zip(lod2_paths, config["exact_hashes"]["lod2_sha256"])]
    c12, c12_units = condition_tables(c12_root, "building_method_metrics", "method_id")
    c3, c3_units = postprocess_tables(c3_root, "building_condition_metrics", "C3_2_SEM_DEPTH")
    c4, c4_units = postprocess_tables(c4_root, "building_c4_metrics", "C4_EXISTING_ALS")
    ids = list(config["building_ids"])
    production_run = validation_building_id is None
    if validation_building_id is not None:
        if validation_building_id not in ids:
            raise RuntimeError("validation building is outside selected10 membership")
        ids = [validation_building_id]
    if any((stable_id, method) not in c12 for stable_id in ids for method in ("C1_L_upper", "C2_MVS", "C3_GS_image")):
        raise RuntimeError("selected10 C1/C2/sealed-C3 membership differs")
    if any(stable_id not in c3 or stable_id not in c4 for stable_id in ids):
        raise RuntimeError("selected10 matched C3/C4 membership differs")
    references = load_references(lod2_paths, ids)
    shift = np.asarray(config["frame"]["local_shift_xyz"], dtype=np.float64)
    natives = {
        "C3_2_SEM_DEPTH": _checkpoint_arrays(artifact_root / source["c3_checkpoint_relative_path"], shift),
        "C4_EXISTING_ALS": _checkpoint_arrays(artifact_root / source["c4_checkpoint_relative_path"], shift),
    }
    census = load_census_config()
    _best, cameras, camera_model, scene_ref = camera_context(artifact_root, census)
    crosswalk = json.loads((REPO / source["exact_view_manifest_git_path"]).read_text(encoding="utf-8"))
    visible = {str(row["basename"]) for row in crosswalk["rows"]}
    if len(visible) != 937:
        raise RuntimeError("exact 937 camera membership drifted")
    geometry_cache: dict[tuple[str, str], dict[str, Any]] = {}
    pages = []
    page_records = []
    roofline_receipts = []
    selection_rows = []
    for page_index, stable_id in enumerate(ids, 1):
        c1_row = c12[(stable_id, "C1_L_upper")]
        c2_row = c12[(stable_id, "C2_MVS")]
        sealed_c3_row = c12[(stable_id, "C3_GS_image")]
        c3_row = c3[stable_id]
        c4_row = c4[stable_id]
        reference = references[stable_id]
        lod2_surfaces = shifted_lod2(reference, float(config["frame"]["lod2_orthometric_to_current_ellipsoidal_m"]))
        zlim = lod2_zlim(lod2_surfaces)
        bbox = BBox(*(float(c4_row[key]) for key in ("bbox_min_x", "bbox_min_y", "bbox_max_x", "bbox_max_y")))
        viewport = bbox.padded(0.35, 5.0)

        def geometry(condition: str, row: Mapping[str, Any], units: Mapping[str, Any], root: Path) -> dict[str, Any]:
            unit = row.get("operation_unit_id")
            key = (condition, str(unit))
            if unit and key not in geometry_cache:
                geometry_cache[key] = load_geometry(root, units[unit])
            return geometry_cache.get(key, {"points": PointSet.empty(), "surfaces": [], "roofprint": []})

        c1_geometry = geometry("C1", c1_row, c12_units, c12_root)
        c2_geometry = geometry("C2", c2_row, c12_units, c12_root)
        c3_geometry = geometry("C3-2", c3_row, c3_units, c3_root)
        c4_geometry = geometry("C4", c4_row, c4_units, c4_root)
        panel_root = output_root / f"qualitative/{stable_id}/panels"
        roofline, receipts = roofline_panels(panel_root, artifact_root, census, reference, cameras, camera_model, scene_ref, visible, stable_id)
        roofline_receipts.extend(receipts)
        c1_input = point_panels(panel_root, c1_geometry["points"], reference, zlim, "c1_input")
        c1_output = building_output_panels(panel_root, c1_row, c1_geometry["surfaces"], reference, zlim, "c1_roofer")
        c2_input = point_panels(panel_root, c2_geometry["points"], reference, zlim, "c2_mvs_input")
        c2_output = building_output_panels(panel_root, c2_row, c2_geometry["surfaces"], reference, zlim, "c2_roofer")
        c2_texture_source = sample_v5 / f"qualitative/{stable_id}/c1_c2/panels"
        c2_texture = [c2_texture_source / f"c2_roofer_textured_{view}.png" for view in VIEWS]
        if c2_row.get("G0_generated") is not True or c2_row.get("one_to_one_building_component") is not True:
            c2_texture = placeholders(panel_root, "C2_TEXTURED_MESH", f"NOT_RUN_BUILDING_LEVEL_{c2_row.get('association_status')}")
            c2_texture_status = f"NOT_RUN; building-level C2 G0=false ({c2_row.get('association_status')})"
        elif not all(path.is_file() for path in c2_texture):
            c2_texture = placeholders(panel_root, "C2_TEXTURED_MESH", "NOT_RUN_NO_BUILDING_LEVEL_TEXTURE")
            c2_texture_status = "NOT_RUN; no building-level textured C2 mesh"
        else:
            c2_texture_status = "SHARED-COMPONENT DISPLAY TEXTURE; diagnostic only"
        c3_native = native_semantic_panels(panel_root, natives["C3_2_SEM_DEPTH"], viewport, reference, zlim, "c3_2_semantic")
        c3_input = point_panels(panel_root, c3_geometry["points"], reference, zlim, "c3_2_roofer_input")
        c3_output = building_output_panels(panel_root, c3_row, c3_geometry["surfaces"], reference, zlim, "c3_2_roofer")
        c3_mesh_root = diagnostic / f"conditions/C3_2_SEM_DEPTH/buildings/{stable_id}"
        c3_consensus_path = c3_mesh_root / "shared_view_roof_consensus_points_v1.ply"
        c3_tsdf_path = c3_mesh_root / "tsdf_roof_mesh_v1.ply"
        c3_mesh_available = c3_consensus_path.is_file()
        c3_tsdf_available = c3_tsdf_path.is_file()
        c3_mesh_input = consensus_panels(panel_root, c3_consensus_path, reference, zlim, "c3_2_mesh_input") if c3_mesh_available else placeholders(panel_root, "C3_2_MESH_INPUT", "NOT_RUN")
        c3_tsdf = mesh_panels(panel_root, c3_tsdf_path, reference, zlim, "c3_2_tsdf", (0.49, 0.25, 0.77)) if c3_tsdf_available else placeholders(panel_root, "C3_2_TSDF", "NOT_RUN")
        c4_native = native_semantic_panels(panel_root, natives["C4_EXISTING_ALS"], viewport, reference, zlim, "c4_semantic")
        c4_input = point_panels(panel_root, c4_geometry["points"], reference, zlim, "c4_roofer_input")
        c4_output = building_output_panels(panel_root, c4_row, c4_geometry["surfaces"], reference, zlim, "c4_roofer")
        c4_attrs = roofer_attributes(c4_root, c4_units.get(c4_row.get("operation_unit_id")))
        c4_extrusion = str(c4_attrs.get("rf_extrusion_mode", "unknown"))
        c4_height = None
        if c4_attrs.get("rf_h_ground") is not None and c4_attrs.get("rf_h_roof_70p") is not None:
            c4_height = float(c4_attrs["rf_h_roof_70p"]) - float(c4_attrs["rf_h_ground"])
        c4_output_status = status_text(c4_row)
        if c4_row.get("G0_generated") is True:
            height_text = f" height={c4_height:.3f}m" if c4_height is not None else ""
            c4_output_status += f"; {c4_extrusion}{height_text}; {c4_row['lod2_reference_status']}"
        c4_mesh_input = placeholders(panel_root, "C4_MESH_INPUT", "NOT_RUN")
        c4_tsdf = placeholders(panel_root, "C4_TSDF", "NOT_RUN")
        lod2_panels = surface_panels(panel_root, lod2_surfaces, reference, zlim, "lod2_reference")
        rows_for_page = [
            ("ROOFLINE PROJECTED RGB", f"4 cameras reselected from exact 937; LoD2={c4_row['lod2_reference_status']}", roofline),
            ("C1 INPUT", status_text(c1_row, "SELF_REFERENCE_DIAGNOSTIC"), c1_input),
            ("C1 ROOFER OUTPUT", status_text(c1_row), c1_output),
            ("C2 MVS INPUT", status_text(c2_row, "INDEPENDENT_CURRENT_UAS"), c2_input),
            ("C2 ROOFER OUTPUT", status_text(c2_row), c2_output),
            ("C2 TEXTURED MESH", c2_texture_status, c2_texture),
            ("C3-2 GS SEMANTIC 3D", "exact matched image-derived checkpoint", c3_native),
            ("C3-2 ROOFER INPUT", status_text(c3_row), c3_input),
            ("C3-2 ROOFER OUTPUT", status_text(c3_row), c3_output),
            ("C3-2 MESH INPUT", "AVAILABLE_SEALED_24_VIEW_DIAGNOSTIC" if c3_mesh_available else "NOT_RUN", c3_mesh_input),
            ("C3-2 TSDF OUTPUT", "AVAILABLE_SEALED_PARALLEL_DIAGNOSTIC" if c3_tsdf_available else "NOT_RUN", c3_tsdf),
            ("C4 GS SEMANTIC 3D", "same C3-2 base + Existing ALS prior", c4_native),
            ("C4 ROOFER INPUT", status_text(c4_row), c4_input),
            ("C4 ROOFER OUTPUT", c4_output_status, c4_output),
            ("C4 MESH INPUT", "NOT_RUN", c4_mesh_input),
            ("C4 TSDF OUTPUT", "NOT_RUN", c4_tsdf),
            ("2022 LoD2 REFERENCE", f"{c4_row['lod2_reference_status']}; C4 comparison prior-related", lod2_panels),
        ]
        subtitle = (
            f"selection sealed-C3 G0/G2={sealed_c3_row.get('G0_generated')}/{sealed_c3_row.get('G2_geometry_topology_valid')} | "
            f"matched C3-2 G0={c3_row.get('G0_generated')} | C4 G0={c4_row.get('G0_generated')}"
        )
        page = output_root / f"qualitative/pages/{page_index:02d}_{stable_id}_17row_4view_v1.png"
        compose_page(page, stable_id, subtitle, rows_for_page, zlim)
        pages.append(page)
        page_records.append({"page": page_index, "stable_id": stable_id, "output": record(page, output_root), "zlim_m": list(zlim), "scientific_verdict": None})
        selection_rows.append({
            "stable_id": stable_id,
            "c1_G0": c1_row.get("G0_generated"),
            "c2_G0": c2_row.get("G0_generated"),
            "sealed_C3_G0": sealed_c3_row.get("G0_generated"),
            "sealed_C3_G2": sealed_c3_row.get("G2_geometry_topology_valid"),
            "matched_C3_2_G0": c3_row.get("G0_generated"),
            "C4_G0": c4_row.get("G0_generated"),
            "C4_lod2_reference_status": c4_row.get("lod2_reference_status"),
            "official_PASS_usable": None,
            "scientific_verdict": None,
        })
        print(f"rendered selected10 {page_index}/10 {stable_id}", flush=True)
    write_new(output_root / "qualitative/page_manifest_v1.jsonl", b"".join((json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n").encode() for row in page_records))
    write_new(output_root / "results/selection_status_v1.jsonl", b"".join((json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n").encode() for row in selection_rows))
    write_new(output_root / "receipts/roofline_camera_coverage_v1.jsonl", b"".join((json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n").encode() for row in roofline_receipts))
    pdf = output_root / "reports/P2_SELECTED10_C1_C2_C3_2_C4_17row_4view_v1.pdf"
    pdf.parent.mkdir(parents=True, exist_ok=True)
    images = [Image.open(path).convert("RGB") for path in pages]
    images[0].save(pdf, "PDF", save_all=True, append_images=images[1:], resolution=150.0, quality=88)
    for image in images:
        image.close()
    links = "".join(f'<article><h2>{html.escape(row["stable_id"])}</h2><a href="../{html.escape(row["output"]["path"])}"><img loading="lazy" src="../{html.escape(row["output"]["path"])}"></a></article>' for row in page_records)
    write_new(output_root / "reports/index.html", ("<!doctype html><html lang='ko'><meta charset='utf-8'><style>body{font-family:sans-serif;max-width:1800px;margin:auto}img{width:100%}article{border-top:4px solid #222;margin:3rem 0}</style><h1>Selected 10 — 17 rows x 4 views</h1><p>matched C3 means C3-2. Missing/not-run/failure retained. C5=NOT_RUN; PASS_usable=null; scientific_verdict=null.</p>" + links).encode())
    report = """# Selected 10 C1/C2/matched C3-2/C4 qualitative presentation v1

The ten pages use the user-fixed 17-row order and four columns TOP, OBLIQUE_1, OBLIQUE_2, and the single footprint-PCA principal section. The sealed C3_GS_image census status is selection context only; every displayed C3 row is the exact matched C3-2 control used by C4. Missing, not-run, unassociated, and failed outputs remain visible. C2 display texture and C3 mesh/TSDF are reused only when an exact sealed source exists. C4 mesh/TSDF remain NOT_RUN. Roofline panels reselect four valid cameras per building from the exact 937 common-base membership and retain a camera/coverage receipt.

No GS training, Roofer, TSDF, or metric execution was performed. scientific_verdict and official PASS_usable remain null.
"""
    write_new(output_root / "reports/technical_report_v1.md", report.encode())
    checks_body = {
        "schema": "jointbuildgs.p2.selected10_c1_c4_presentation.verification.v1",
        "status": "200-VERIFIED_LOCAL_SELECTED10_PRESENTATION",
        "page_count_expected": len(page_records) == (10 if production_run else 1),
        "row_count_17": len(config["row_order"]) == 17,
        "four_views": tuple(config["views"]) == VIEWS,
        "roofline_receipt_count_expected": len(roofline_receipts) == (40 if production_run else 4),
        "all_roofline_views_projected": all(row["status"] == "PROJECTED" for row in roofline_receipts),
        "missing_preserved": config["presentation"]["missing_not_run_failure_preserved"],
        "c4_mesh_tsdf_not_run": True,
        "c5_not_run": config["presentation"]["c5_state"] == "NOT_RUN",
        "official_PASS_usable": None,
        "scientific_verdict": None,
        "pdf": record(pdf, output_root),
        "source_checks": checks,
    }
    required = ("page_count_expected", "row_count_17", "four_views", "roofline_receipt_count_expected", "all_roofline_views_projected", "missing_preserved", "c4_mesh_tsdf_not_run", "c5_not_run")
    if not all(checks_body[key] for key in required):
        raise RuntimeError(f"selected10 verification failed: {checks_body}")
    write_json(output_root / "control/200-verified.local_v1.json", checks_body)
    material = [path for path in sorted(output_root.rglob("*")) if path.is_file() and path.name not in {"artifact_manifest_v1.json", "300-closed.local_v1.json"}]
    manifest = {
        "schema": "jointbuildgs.p2.selected10_c1_c4_presentation.manifest.v1",
        "status": "COMPLETE_HASHED_MATERIAL_PAYLOAD",
        "source_commit": source_commit,
        "run_id": run_id,
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "records": [record(path, output_root) for path in material],
        "official_PASS_usable": None,
        "scientific_verdict": None,
    }
    manifest["record_count"] = len(manifest["records"])
    write_json(output_root / "control/artifact_manifest_v1.json", manifest)
    closed = {
        "schema": "jointbuildgs.p2.selected10_c1_c4_presentation.closed.v1",
        "status": "300-CLOSED_LOCAL_SELECTED10_PRESENTATION",
        "pdf": record(pdf, output_root),
        "gallery": record(output_root / "reports/index.html", output_root),
        "verification": record(output_root / "control/200-verified.local_v1.json", output_root),
        "manifest": record(output_root / "control/artifact_manifest_v1.json", output_root),
        "official_PASS_usable": None,
        "scientific_verdict": None,
    }
    write_json(output_root / "control/300-closed.local_v1.json", closed)
    return closed


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--validation-building-id")
    args = parser.parse_args()
    print(json.dumps(run(args.output_root, args.artifact_root, args.source_commit, args.run_id, args.validation_building_id), sort_keys=True))


if __name__ == "__main__":
    main()
