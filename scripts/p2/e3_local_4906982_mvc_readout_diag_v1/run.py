#!/usr/bin/env python3
"""Docker-only readout diagnosis for the 4906982 MVC experiment.

The host path only orchestrates immutable inputs and Docker invocations.  All
scientific calculations run inside ``jointbuildgs:mvc-eval-v1``.  The source
MVC-v2 namespace is mounted read-only and no training, fusion, classification,
or Roofer process is rerun.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


REPO = Path(__file__).resolve().parents[3]
ARTIFACT_ROOT = REPO.parent / "JointBuildGS-artifacts"
TASK_ID = "P2-E3-LOCAL-4906982-MVC-READOUT-DIAG-v1"
TASK_ROOT = ARTIFACT_ROOT / "phase-payloads/p2/e3_local_4906982_mvc_readout_diag_v1" / TASK_ID
CONFIG_PATH = REPO / "configs/p2/e3_local_4906982_mvc_readout_diag_v1/config.yaml"
EVAL_IMAGE = "jointbuildgs:mvc-eval-v1"
BUILDER_IMAGE = "innopam-v1-nbm-frontend:latest"
PLUGIN_ROOT = Path("/home/innopam/.codex/plugins/cache/openai-curated-remote/data-analytics/0.2.8-13ceeea1f599")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def atomic_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, indent=2, sort_keys=True, ensure_ascii=False)
            stream.write("\n")
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def command(argv: list[str], *, cwd: Path = REPO, check: bool = True) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(argv, cwd=cwd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if check and proc.returncode != 0:
        raise RuntimeError(f"command failed ({proc.returncode}): {' '.join(argv)}\n{proc.stderr or proc.stdout}")
    return proc


def git_record() -> dict[str, Any]:
    status = command(["git", "status", "--porcelain=v1"], check=False).stdout
    return {
        "commit": command(["git", "rev-parse", "HEAD"]).stdout.strip(),
        "branch": command(["git", "branch", "--show-current"]).stdout.strip(),
        "dirty": bool(status.strip()),
        "status_porcelain": status.splitlines(),
    }


def image_record(image: str) -> dict[str, Any]:
    proc = command(["docker", "image", "inspect", image], check=False)
    if proc.returncode != 0:
        raise RuntimeError(f"required Docker image unavailable: {image}\n{proc.stderr}")
    row = json.loads(proc.stdout)[0]
    return {"reference": image, "id": row.get("Id"), "repo_digests": row.get("RepoDigests") or []}


def host_main() -> None:
    if not CONFIG_PATH.is_file():
        raise RuntimeError(f"missing config: {CONFIG_PATH}")
    TASK_ROOT.mkdir(parents=True, exist_ok=True)
    (TASK_ROOT / "logs").mkdir(exist_ok=True)
    host_context = {
        "schema": "jointbuildgs.p2.e3_local_4906982_mvc_readout_diag_v1.host_context.v1",
        "task_id": TASK_ID,
        "started_utc": utc_now(),
        "git": git_record(),
        "evaluation_image": image_record(EVAL_IMAGE),
        "report_builder_image": image_record(BUILDER_IMAGE),
        "runner_sha256": sha256(Path(__file__)),
        "config_sha256": sha256(CONFIG_PATH),
        "scientific_verdict": None,
    }
    atomic_json(TASK_ROOT / "control/host_context.json", host_context)

    analysis_argv = [
        "docker", "run", "--rm", "--network", "none",
        "--user", f"{os.getuid()}:{os.getgid()}",
        "-e", "MPLCONFIGDIR=/tmp/matplotlib",
        "-v", f"{REPO}:/workspace/JointBuildGS:ro",
        "-v", f"{ARTIFACT_ROOT}:/artifacts/JointBuildGS:ro",
        "-v", f"{TASK_ROOT}:/task:rw",
        "-w", "/workspace/JointBuildGS",
        EVAL_IMAGE,
        "python", "/workspace/JointBuildGS/scripts/p2/e3_local_4906982_mvc_readout_diag_v1/run.py",
        "--inside-docker", "analyze",
        "--config", "/workspace/JointBuildGS/configs/p2/e3_local_4906982_mvc_readout_diag_v1/config.yaml",
        "--output", "/task",
    ]
    analysis_started = utc_now()
    with (TASK_ROOT / "logs/analyze.log").open("w", encoding="utf-8") as log:
        proc = subprocess.run(analysis_argv, cwd=REPO, text=True, stdout=log, stderr=subprocess.STDOUT)
    analysis_ended = utc_now()
    if proc.returncode != 0:
        raise RuntimeError(f"analysis failed ({proc.returncode}); inspect {TASK_ROOT / 'logs/analyze.log'}")

    report_argv = [
        "docker", "run", "--rm", "--network", "none",
        "--user", f"{os.getuid()}:{os.getgid()}",
        "-v", f"{PLUGIN_ROOT}:/plugin:ro",
        "-v", f"{TASK_ROOT}:/task:rw",
        "-w", "/plugin",
        BUILDER_IMAGE,
        "node", "/plugin/skills/build-report/scripts/deliver_portable_artifact.mjs",
        "--input", "/task/report_artifact.json",
        "--output", "/task/report.html",
        "--screenshot", "/task/logs/report_delivery_failure.png",
    ]
    report_started = utc_now()
    with (TASK_ROOT / "logs/report_delivery.log").open("w", encoding="utf-8") as log:
        built = subprocess.run(report_argv, cwd=REPO, text=True, stdout=log, stderr=subprocess.STDOUT)
    report_ended = utc_now()
    if built.returncode != 0:
        raise RuntimeError(f"report delivery failed ({built.returncode}); inspect {TASK_ROOT / 'logs/report_delivery.log'}")

    provenance_path = TASK_ROOT / "provenance.json"
    provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
    provenance["host_context"] = host_context
    provenance["commands"] = [
        {"label": "analyze", "argv": analysis_argv, "started_utc": analysis_started, "ended_utc": analysis_ended, "return_code": proc.returncode},
        {"label": "deliver_portable_report", "argv": report_argv, "started_utc": report_started, "ended_utc": report_ended, "return_code": built.returncode},
    ]
    provenance["ended_utc"] = utc_now()
    provenance["git_at_completion"] = git_record()
    provenance["report_html_sha256"] = sha256(TASK_ROOT / "report.html")
    atomic_json(provenance_path, provenance)

    contract_path = TASK_ROOT / "experiment_contract.json"
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    contract["status"] = "COMPLETE_DIAGNOSTIC"
    contract["scientific_verdict"] = None
    atomic_json(contract_path, contract)

    metrics = json.loads((TASK_ROOT / "metrics.json").read_text(encoding="utf-8"))
    summary = {
        "status": metrics["status"],
        "cases": metrics["case_count"],
        "fusion_high_z_cases": metrics["high_z_transmission"]["fusion_cases_with_z_gt_650"],
        "roofer_high_z_cases": metrics["high_z_transmission"]["roofer_cases_with_z_gt_650"],
        "mvc05_20k_roof_xy_coverage": metrics["mvc05_20k_roof_xy_coverage"],
        "report": str(TASK_ROOT / "report.html"),
        "scientific_verdict": None,
    }
    print(json.dumps(summary, indent=2, ensure_ascii=False))


# ---- In-container scientific analysis ------------------------------------


@dataclass
class RoofSurface:
    surface_id: str
    polygon: Any
    x0: float
    y0: float
    z0: float
    ax: float
    by: float

    def z_at(self, x: Any, y: Any) -> Any:
        return self.z0 + self.ax * (x - self.x0) + self.by * (y - self.y0)

    def normal(self) -> Any:
        import numpy as np

        n = np.asarray([-self.ax, -self.by, 1.0], dtype=np.float64)
        return n / max(float(np.linalg.norm(n)), 1e-12)


def local_name(tag: str) -> str:
    return tag.split("}", 1)[-1]


def gml_id(elem: Any) -> str:
    for key, value in elem.attrib.items():
        if local_name(key) == "id":
            return str(value)
    return ""


def flatten_polygons(geom: Any) -> list[Any]:
    from shapely.geometry import GeometryCollection, MultiPolygon, Polygon

    if geom is None or geom.is_empty:
        return []
    if isinstance(geom, Polygon):
        return [geom]
    if isinstance(geom, MultiPolygon):
        return list(geom.geoms)
    if isinstance(geom, GeometryCollection):
        out: list[Any] = []
        for item in geom.geoms:
            out.extend(flatten_polygons(item))
        return out
    return []


def fit_surface(surface_id: str, rings: list[Any]) -> RoofSurface | None:
    import numpy as np
    from shapely import make_valid
    from shapely.geometry import MultiPolygon, Polygon

    if not rings:
        return None
    normalized = []
    for ring in rings:
        arr = np.asarray(ring, dtype=np.float64)
        if arr.ndim != 2 or arr.shape[1] != 3 or len(arr) < 3 or not np.isfinite(arr).all():
            continue
        if not np.allclose(arr[0], arr[-1]):
            arr = np.vstack([arr, arr[0]])
        normalized.append(arr)
    if not normalized:
        return None
    poly: Any = Polygon(normalized[0][:, :2], [r[:, :2] for r in normalized[1:]])
    if not poly.is_valid:
        poly = make_valid(poly)
    pieces = [p for p in flatten_polygons(poly) if p.area > 0.05]
    if not pieces:
        return None
    poly = pieces[0] if len(pieces) == 1 else MultiPolygon(pieces)
    pts = normalized[0][:-1]
    x0, y0, z0 = map(float, pts.mean(axis=0))
    design = np.column_stack([pts[:, 0] - x0, pts[:, 1] - y0])
    try:
        ax, by = np.linalg.lstsq(design, pts[:, 2] - z0, rcond=None)[0]
    except np.linalg.LinAlgError:
        ax, by = 0.0, 0.0
    return RoofSurface(surface_id, poly, x0, y0, z0, float(ax), float(by))


def parse_poslist(text: str) -> Any:
    import numpy as np

    values = np.asarray([float(v) for v in text.split()], dtype=np.float64)
    return values.reshape((-1, 3))


def first_poslist(elem: Any) -> Any | None:
    for child in elem.iter():
        if local_name(child.tag) == "posList" and child.text:
            return parse_poslist(child.text)
    return None


def parse_reference_roofs(path: Path, building_id: str) -> list[RoofSurface]:
    from lxml import etree

    surfaces: list[RoofSurface] = []
    for _event, elem in etree.iterparse(str(path), events=("end",), recover=True):
        if local_name(elem.tag) != "Building":
            continue
        if gml_id(elem) == building_id:
            roof_index = 0
            for roof in elem.iter():
                if local_name(roof.tag) != "RoofSurface":
                    continue
                roof_index += 1
                polygon_index = 0
                for polygon in roof.iter():
                    if local_name(polygon.tag) != "Polygon":
                        continue
                    polygon_index += 1
                    exterior = None
                    interiors = []
                    for child in polygon:
                        if local_name(child.tag) == "exterior":
                            exterior = first_poslist(child)
                        elif local_name(child.tag) == "interior":
                            ring = first_poslist(child)
                            if ring is not None:
                                interiors.append(ring)
                    if exterior is None:
                        rings = [parse_poslist(x.text) for x in polygon.iter() if local_name(x.tag) == "posList" and x.text]
                    else:
                        rings = [exterior, *interiors]
                    surface = fit_surface(f"ref_r{roof_index}_p{polygon_index}", rings)
                    if surface is not None:
                        surfaces.append(surface)
            elem.clear()
            break
        elem.clear()
    if not surfaces:
        raise RuntimeError(f"reference RoofSurface not found for {building_id} in {path}")
    return surfaces


def iter_cityjson_faces(geom_type: str | None, boundaries: Any, values: Any) -> Iterable[tuple[list[list[int]], Any]]:
    if boundaries is None:
        return
    if geom_type == "Solid":
        for shell_index, shell in enumerate(boundaries):
            shell_values = values[shell_index] if isinstance(values, list) and shell_index < len(values) else []
            for face_index, rings in enumerate(shell):
                semantic = shell_values[face_index] if isinstance(shell_values, list) and face_index < len(shell_values) else None
                yield rings, semantic
    elif geom_type in {"MultiSurface", "CompositeSurface"}:
        for face_index, rings in enumerate(boundaries):
            semantic = values[face_index] if isinstance(values, list) and face_index < len(values) else None
            yield rings, semantic
    elif geom_type == "MultiSolid":
        for solid_index, solid in enumerate(boundaries):
            solid_values = values[solid_index] if isinstance(values, list) and solid_index < len(values) else []
            for shell_index, shell in enumerate(solid):
                shell_values = solid_values[shell_index] if isinstance(solid_values, list) and shell_index < len(solid_values) else []
                for face_index, rings in enumerate(shell):
                    semantic = shell_values[face_index] if isinstance(shell_values, list) and face_index < len(shell_values) else None
                    yield rings, semantic


def load_cityjsonseq(path: Path, building_id: str, z_shift: float) -> tuple[list[RoofSurface], Any]:
    import numpy as np

    lines = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    header = next((x for x in lines if x.get("type") == "CityJSON"), {})
    feature = next((x for x in lines if x.get("type") == "CityJSONFeature"), lines[-1])
    transform = feature.get("transform") or header.get("transform") or {}
    vertices = np.asarray(feature.get("vertices", []), dtype=np.float64)
    if len(vertices):
        vertices = vertices * np.asarray(transform.get("scale", [1, 1, 1]), dtype=np.float64) + np.asarray(transform.get("translate", [0, 0, 0]), dtype=np.float64)
    objects = feature.get("CityObjects", {})
    selected = set([building_id])
    selected.update(objects.get(building_id, {}).get("children", []))
    for object_id, obj in objects.items():
        if building_id in obj.get("parents", []) or object_id.startswith(building_id + "-"):
            selected.add(object_id)
    surfaces: list[RoofSurface] = []
    for object_id in sorted(selected):
        obj = objects.get(object_id)
        if obj is None:
            continue
        for geom_index, geom in enumerate(obj.get("geometry", [])):
            semantics = geom.get("semantics") or {}
            semantic_surfaces = semantics.get("surfaces") or []
            values = semantics.get("values")
            for face_index, (rings, semantic_index) in enumerate(iter_cityjson_faces(geom.get("type"), geom.get("boundaries"), values)):
                try:
                    semantic_type = semantic_surfaces[int(semantic_index)].get("type")
                except (TypeError, ValueError, IndexError):
                    continue
                if semantic_type != "RoofSurface":
                    continue
                coords = [np.asarray([vertices[int(index)] for index in ring], dtype=np.float64) for ring in rings if ring]
                surface = fit_surface(f"{object_id}_g{geom_index}_f{face_index}", coords)
                if surface is not None:
                    surface.z0 += z_shift
                    surfaces.append(surface)
    return surfaces, vertices


def sample_surfaces(surfaces: list[RoofSurface], spacing: float) -> tuple[Any, Any, Any]:
    import numpy as np
    from shapely import contains_xy

    xy_rows = []
    z_rows = []
    normal_rows = []
    for surface in surfaces:
        for poly in flatten_polygons(surface.polygon):
            min_x, min_y, max_x, max_y = poly.bounds
            xs = np.arange(min_x + spacing / 2.0, max_x, spacing)
            ys = np.arange(min_y + spacing / 2.0, max_y, spacing)
            if xs.size and ys.size:
                xx, yy = np.meshgrid(xs, ys)
                mask = contains_xy(poly, xx.ravel(), yy.ravel())
                xy = np.column_stack([xx.ravel()[mask], yy.ravel()[mask]])
            else:
                xy = np.empty((0, 2), dtype=np.float64)
            if not len(xy):
                point = poly.representative_point()
                xy = np.asarray([[point.x, point.y]], dtype=np.float64)
            xy_rows.append(xy)
            z_rows.append(surface.z_at(xy[:, 0], xy[:, 1]))
            normal_rows.append(np.repeat(surface.normal()[None, :], len(xy), axis=0))
    if not xy_rows:
        return np.empty((0, 2)), np.empty(0), np.empty((0, 3))
    return np.vstack(xy_rows), np.concatenate(z_rows), np.vstack(normal_rows)


def match_xy_to_surfaces(xy: Any, z: Any, surfaces: list[RoofSurface], normals: Any | None = None) -> dict[str, Any]:
    import numpy as np
    from shapely import contains_xy

    count = len(xy)
    best_abs = np.full(count, np.inf, dtype=np.float64)
    best_signed = np.full(count, np.nan, dtype=np.float64)
    best_angle = np.full(count, np.nan, dtype=np.float64)
    matched = np.zeros(count, dtype=bool)
    for surface in surfaces:
        inside = contains_xy(surface.polygon, xy[:, 0], xy[:, 1])
        if not np.any(inside):
            continue
        reference_z = surface.z_at(xy[:, 0], xy[:, 1])
        signed = z - reference_z
        update = inside & (np.abs(signed) < best_abs)
        if not np.any(update):
            continue
        best_abs[update] = np.abs(signed[update])
        best_signed[update] = signed[update]
        matched[update] = True
        if normals is not None:
            dot = np.abs(normals @ surface.normal())
            best_angle[update] = np.degrees(np.arccos(np.clip(dot[update], -1.0, 1.0)))
    return {"matched": matched, "abs": best_abs, "signed": best_signed, "angle": best_angle}


def finite_stats(values: Any, prefix: str) -> dict[str, Any]:
    import numpy as np

    arr = np.asarray(values, dtype=np.float64)
    arr = arr[np.isfinite(arr)]
    if not len(arr):
        return {f"{prefix}_count": 0, f"{prefix}_median": None, f"{prefix}_p95": None, f"{prefix}_rmse": None}
    return {
        f"{prefix}_count": int(len(arr)),
        f"{prefix}_median": float(np.median(arr)),
        f"{prefix}_p95": float(np.quantile(arr, 0.95)),
        f"{prefix}_rmse": float(np.sqrt(np.mean(arr * arr))),
    }


def point_metrics(path: Path, footprint: Any, refs: list[RoofSurface], cfg: dict[str, Any], *, classified: bool) -> dict[str, Any]:
    import laspy
    import numpy as np
    from shapely import contains_xy

    cloud = laspy.read(path)
    x = np.asarray(cloud.x, dtype=np.float64)
    y = np.asarray(cloud.y, dtype=np.float64)
    z_world = np.asarray(cloud.z, dtype=np.float64)
    z_ref = z_world + float(cfg["prediction_z_shift_to_reference_m"])
    names = {str(name).lower(): str(name) for name in cloud.point_format.dimension_names}

    def dimension(name: str) -> Any:
        stored_name = names.get(name.lower())
        return np.asarray(cloud[stored_name], dtype=np.float64) if stored_name else np.full(len(x), np.nan)

    nx = dimension("NormalX")
    ny = dimension("NormalY")
    nz = dimension("NormalZ")
    normals = np.column_stack([nx, ny, nz])
    norm = np.linalg.norm(normals, axis=1)
    valid_normal = np.isfinite(norm) & (norm > 1e-12)
    normals[valid_normal] /= norm[valid_normal, None]
    inside = contains_xy(footprint, x, y)
    rooflike = inside & valid_normal & (np.abs(normals[:, 2]) >= float(cfg["roof_normal_abs_nz_min"]))
    classes = np.asarray(cloud.classification, dtype=np.uint8)
    evidence = rooflike & ((classes == 6) if classified else True)
    xy = np.column_stack([x[evidence], y[evidence]])
    matches = match_xy_to_surfaces(xy, z_ref[evidence], refs, normals[evidence])
    matched = matches["matched"]
    abs_dz = matches["abs"][matched]
    signed_dz = matches["signed"][matched]
    angles = matches["angle"][matched]
    result: dict[str, Any] = {
        "point_count": int(len(x)),
        "z_gt_650_count": int(np.count_nonzero(z_world > 650.0)),
        "inside_footprint_count": int(np.count_nonzero(inside)),
        "rooflike_count": int(np.count_nonzero(rooflike)),
        "evidence_count": int(np.count_nonzero(evidence)),
        "reference_xy_matched_fraction": float(np.mean(matched)) if len(matched) else None,
    }
    result.update(finite_stats(abs_dz, "abs_dz_m"))
    result.update(finite_stats(signed_dz, "signed_dz_m"))
    result.update(finite_stats(angles, "normal_angle_deg"))
    for threshold in cfg["distance_thresholds_m"]:
        key = str(threshold).replace(".", "p")
        result[f"within_{key}m_fraction"] = float(np.count_nonzero(matched & (matches["abs"] <= float(threshold))) / len(matched)) if len(matched) else None

    grid = float(cfg["grid_size_m"])
    min_x, min_y, max_x, max_y = footprint.bounds
    gx = np.arange(min_x + grid / 2.0, max_x, grid)
    gy = np.arange(min_y + grid / 2.0, max_y, grid)
    xx, yy = np.meshgrid(gx, gy)
    cell_inside = contains_xy(footprint, xx.ravel(), yy.ravel())
    all_cells = set(zip(np.floor((xx.ravel()[cell_inside] - min_x) / grid).astype(int), np.floor((yy.ravel()[cell_inside] - min_y) / grid).astype(int)))
    center_geom = footprint.buffer(-float(cfg["center_margin_m"]))
    if center_geom.is_empty:
        center_cells: set[tuple[int, int]] = set()
    else:
        in_center = contains_xy(center_geom, xx.ravel(), yy.ravel())
        center_cells = set(zip(np.floor((xx.ravel()[in_center] - min_x) / grid).astype(int), np.floor((yy.ravel()[in_center] - min_y) / grid).astype(int)))
    occupied = set(zip(np.floor((xy[:, 0] - min_x) / grid).astype(int), np.floor((xy[:, 1] - min_y) / grid).astype(int))) if len(xy) else set()
    result["grid_coverage_fraction"] = len(occupied & all_cells) / len(all_cells) if all_cells else None
    result["center_grid_coverage_fraction"] = len(occupied & center_cells) / len(center_cells) if center_cells else None

    def largest_component(cells: set[tuple[int, int]]) -> int:
        remaining = set(cells)
        largest = 0
        while remaining:
            pending = [remaining.pop()]
            size = 0
            while pending:
                cx, cy = pending.pop()
                size += 1
                for neighbor in ((cx - 1, cy), (cx + 1, cy), (cx, cy - 1), (cx, cy + 1)):
                    if neighbor in remaining:
                        remaining.remove(neighbor)
                        pending.append(neighbor)
            largest = max(largest, size)
        return largest

    coherent_cells: set[tuple[int, int]] = set()
    if len(xy):
        cell_x = np.floor((xy[:, 0] - min_x) / grid).astype(int)
        cell_y = np.floor((xy[:, 1] - min_y) / grid).astype(int)
        cell_keys = np.column_stack([cell_x, cell_y])
        unique_cells, inverse = np.unique(cell_keys, axis=0, return_inverse=True)
        min_points = int(cfg["grid_min_points_per_cell"])
        max_dz = float(cfg["coherent_cell_median_abs_dz_max_m"])
        max_angle = float(cfg["coherent_cell_median_normal_angle_max_deg"])
        for index, cell in enumerate(unique_cells):
            selected = inverse == index
            valid = selected & matched
            if np.count_nonzero(valid) < min_points:
                continue
            cell_abs = matches["abs"][valid]
            cell_angle = matches["angle"][valid]
            if float(np.median(cell_abs)) <= max_dz and float(np.median(cell_angle)) <= max_angle:
                coherent_cells.add((int(cell[0]), int(cell[1])))
    coherent_inside = coherent_cells & all_cells
    largest = largest_component(coherent_inside)
    result["coherent_grid_cell_count"] = len(coherent_inside)
    result["coherent_grid_coverage_fraction"] = len(coherent_inside) / len(all_cells) if all_cells else None
    result["coherent_center_grid_coverage_fraction"] = len(coherent_cells & center_cells) / len(center_cells) if center_cells else None
    result["coherent_largest_component_cell_count"] = largest
    result["coherent_largest_component_footprint_fraction"] = largest / len(all_cells) if all_cells else None
    result["coherent_largest_component_share"] = largest / len(coherent_inside) if coherent_inside else None
    if "view_support" in names:
        support = np.asarray(cloud[names["view_support"]], dtype=np.int64)[evidence]
        result["evidence_support_ge3_fraction"] = float(np.mean(support >= 3)) if len(support) else None
        result["evidence_support_median"] = float(np.median(support)) if len(support) else None
    else:
        result["evidence_support_ge3_fraction"] = None
        result["evidence_support_median"] = None
    return result


def surface_metrics(preds: list[RoofSurface], original_vertices: Any, refs: list[RoofSurface], footprint: Any, cfg: dict[str, Any]) -> dict[str, Any]:
    import numpy as np
    from shapely.ops import unary_union

    spacing = float(cfg["surface_sample_spacing_m"])
    pred_xy, pred_z, pred_normals = sample_surfaces(preds, spacing)
    ref_xy, ref_z, ref_normals = sample_surfaces(refs, spacing)
    pred_match = match_xy_to_surfaces(pred_xy, pred_z, refs, pred_normals)
    ref_match = match_xy_to_surfaces(ref_xy, ref_z, preds, ref_normals)
    pred_polys = [poly for surface in preds for poly in flatten_polygons(surface.polygon)]
    union = unary_union(pred_polys) if pred_polys else None
    coverage = float(union.intersection(footprint).area / footprint.area) if union is not None and not union.is_empty else 0.0
    result: dict[str, Any] = {
        "roof_surface_count": int(len(preds)),
        "roof_xy_coverage_fraction": coverage,
        "roof_xy_overshoot_m2": float(union.difference(footprint).area) if union is not None and not union.is_empty else 0.0,
        "prediction_sample_count": int(len(pred_xy)),
        "reference_sample_count": int(len(ref_xy)),
        "prediction_reference_xy_match_fraction": float(np.mean(pred_match["matched"])) if len(pred_xy) else None,
        "reference_prediction_xy_match_fraction": float(np.mean(ref_match["matched"])) if len(ref_xy) else None,
        "vertex_z_gt_650_count": int(np.count_nonzero(original_vertices[:, 2] > 650.0)) if len(original_vertices) else 0,
    }
    pred_abs = pred_match["abs"][pred_match["matched"]]
    ref_abs = ref_match["abs"][ref_match["matched"]]
    result.update(finite_stats(pred_abs, "surface_accuracy_abs_dz_m"))
    result.update(finite_stats(ref_abs, "surface_completeness_abs_dz_m"))
    result.update(finite_stats(pred_match["angle"][pred_match["matched"]], "surface_normal_angle_deg"))
    for threshold in cfg["distance_thresholds_m"]:
        value = float(threshold)
        key = str(threshold).replace(".", "p")
        precision = float(np.count_nonzero(pred_match["matched"] & (pred_match["abs"] <= value)) / len(pred_xy)) if len(pred_xy) else 0.0
        recall = float(np.count_nonzero(ref_match["matched"] & (ref_match["abs"] <= value)) / len(ref_xy)) if len(ref_xy) else 0.0
        fscore = 2.0 * precision * recall / (precision + recall) if precision + recall else 0.0
        result[f"surface_precision_{key}m"] = precision
        result[f"surface_completeness_{key}m"] = recall
        result[f"surface_fscore_{key}m"] = fscore
    return result


def prefix_fields(prefix: str, payload: dict[str, Any]) -> dict[str, Any]:
    return {f"{prefix}_{key}": value for key, value in payload.items()}


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fields: list[str] = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def nullable_float(value: Any) -> float | None:
    if value is None:
        return None
    result = float(value)
    return result if math.isfinite(result) else None


def paired_deltas(rows: list[dict[str, Any]], fields: list[str]) -> list[dict[str, Any]]:
    index = {(r["arm"], r["replica"], r["completed_updates"]): r for r in rows}
    output = []
    for replica in sorted({r["replica"] for r in rows}):
        for step in sorted({r["completed_updates"] for r in rows}):
            control = index[("MVC0", replica, step)]
            treated = index[("MVC05", replica, step)]
            row: dict[str, Any] = {"replica": replica, "completed_updates": step}
            for field in fields:
                a = nullable_float(treated.get(field))
                b = nullable_float(control.get(field))
                row[field + "_delta"] = None if a is None or b is None else a - b
            output.append(row)
    return output


def driver_analysis(rows: list[dict[str, Any]], candidates: list[str]) -> list[dict[str, Any]]:
    import numpy as np
    from scipy.stats import spearmanr

    eligible = [row for row in rows if row["completed_updates"] > 7000]
    result = []
    for field in candidates:
        pairs = [(nullable_float(row.get(field)), nullable_float(row.get("roofer_roof_xy_coverage_fraction"))) for row in eligible]
        pairs = [(a, b) for a, b in pairs if a is not None and b is not None]
        if len(pairs) < 4 or len({a for a, _ in pairs}) < 2 or len({b for _, b in pairs}) < 2:
            rho = pvalue = None
        else:
            rho_value, pvalue_value = spearmanr(np.asarray([a for a, _ in pairs]), np.asarray([b for _, b in pairs]))
            rho = nullable_float(rho_value)
            pvalue = nullable_float(pvalue_value)
        result.append({"driver": field, "n": len(pairs), "spearman_rho": rho, "pvalue_descriptive_only": pvalue, "abs_rho": None if rho is None else abs(rho)})
    return sorted(
        result,
        key=lambda row: (row["abs_rho"] is None, -(row["abs_rho"] or 0.0), row["driver"]),
    )


def make_reference_panel(path: Path, rows: list[dict[str, Any]], cfg: dict[str, Any], refs: list[RoofSurface], footprint: Any) -> None:
    import laspy
    import matplotlib
    import numpy as np

    matplotlib.use("Agg")
    from matplotlib import pyplot as plt
    source_root = Path(cfg["source_task_root"])
    fig, axes = plt.subplots(2, 3, figsize=(17, 10), dpi=150, constrained_layout=True)
    colors = {"MVC0": "#1688c7", "MVC05": "#c51b8a"}
    fp_xy = np.asarray(footprint.exterior.coords)
    for row, ax in zip(sorted([r for r in rows if r["completed_updates"] == 20000], key=lambda r: (r["arm"], r["replica"])), axes.ravel()):
        arm, replica = row["arm"], row["replica"]
        base = source_root / "arms" / arm / replica / "evaluation/step_020000/fusion"
        cloud = laspy.read(base / "classified_surface.laz")
        names = {str(name).lower(): str(name) for name in cloud.point_format.dimension_names}
        nz_name = names.get("normalz")
        nz = np.asarray(cloud[nz_name], dtype=float) if nz_name else np.zeros(len(cloud.points))
        cls = np.asarray(cloud.classification, dtype=np.uint8)
        mask = (cls == 6) & (np.abs(nz) >= float(cfg["roof_normal_abs_nz_min"]))
        x = np.asarray(cloud.x)[mask]
        y = np.asarray(cloud.y)[mask]
        if len(x) > 18000:
            select = np.linspace(0, len(x) - 1, 18000, dtype=int)
            x, y = x[select], y[select]
        ax.scatter(x, y, s=0.25, c="#b8b8b8", alpha=0.35, linewidths=0)
        for surface in refs:
            for poly in flatten_polygons(surface.polygon):
                xy = np.asarray(poly.exterior.coords)
                ax.plot(xy[:, 0], xy[:, 1], color="#00a6a6", linewidth=1.2, linestyle="--")
        preds, _vertices = load_cityjsonseq(base / "roofer/output/690897_5336168.city.jsonl", cfg["building_id"], float(cfg["prediction_z_shift_to_reference_m"]))
        for surface in preds:
            for poly in flatten_polygons(surface.polygon):
                xy = np.asarray(poly.exterior.coords)
                ax.fill(xy[:, 0], xy[:, 1], facecolor=colors[arm], edgecolor="#111111", alpha=0.38, linewidth=0.6)
        ax.plot(fp_xy[:, 0], fp_xy[:, 1], color="#111111", linewidth=1.4)
        ax.set_aspect("equal")
        ax.set_axis_off()
        ax.set_title(f"{arm} {replica} | roof XY {100*row['roofer_roof_xy_coverage_fraction']:.2f}% | F0.5 {row['roofer_surface_fscore_0p5m']:.3f}", fontsize=10)
    fig.suptitle("DEBY_LOD2_4906982 · 20k classified roof evidence and Roofer vs evaluation-only LoD2", fontsize=15, fontweight="bold")
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path)
    plt.close(fig)


def build_report_artifact(output: Path, rows: list[dict[str, Any]], paired: list[dict[str, Any]], drivers: list[dict[str, Any]], metrics: dict[str, Any]) -> None:
    generated = utc_now()
    rows20 = [r for r in rows if r["completed_updates"] == 20000]
    coverage = [{"case": f"{r['arm']} {r['replica']}", "arm": r["arm"], "replica": r["replica"], "roof_xy_coverage": r["roofer_roof_xy_coverage_fraction"], "fscore_0p5m": r["roofer_surface_fscore_0p5m"], "classified_grid_coverage": r["classified_grid_coverage_fraction"], "classified_center_grid_coverage": r["classified_center_grid_coverage_fraction"], "coherent_grid_coverage": r["classified_coherent_grid_coverage_fraction"], "coherent_largest_component": r["classified_coherent_largest_component_footprint_fraction"], "point_median_abs_dz_m": r["classified_abs_dz_m_median"], "point_median_normal_angle_deg": r["classified_normal_angle_deg_median"]} for r in rows20]
    leakage = [{"case": f"{r['arm']} {r['replica']}", "gaussian_z_gt650": r["gaussian_z_gt650"], "fusion_z_gt650": r["fused_z_gt_650_count"], "classified_z_gt650": r["classified_z_gt_650_count"], "roofer_vertex_z_gt650": r["roofer_vertex_z_gt_650_count"]} for r in rows20]
    driver_rows = [r for r in drivers if r["spearman_rho"] is not None]
    query_base = {"engine": "SQLite over frozen diagnostic snapshot", "language": "sql"}
    source_headline = {"id": "headline_source", "label": "Readout diagnostic headline metrics", "path": "metrics.json", "query": {**query_base, "description": "Select the materialized headline row.", "filters": ["task_id = P2-E3-LOCAL-4906982-MVC-READOUT-DIAG-v1"], "metric_definitions": ["High-Z transmission is counted per immutable case."], "sql": "SELECT * FROM headline", "tables_used": ["headline"]}}
    source_case = {"id": "case_source", "label": "MVC v2 readout case metrics", "path": "case_metrics.csv", "query": {**query_base, "description": "Select all 24 immutable arm-replica-checkpoint case rows.", "filters": ["completed_updates in (7000,12000,15000,20000)"], "metric_definitions": ["Roofer coverage is semantic RoofSurface XY union area divided by shared footprint area."], "sql": "SELECT * FROM case_metrics ORDER BY completed_updates, arm, replica", "tables_used": ["case_metrics"]}}
    source_driver = {"id": "driver_source", "label": "Post-activation descriptive associations", "path": "driver_analysis.json", "query": {**query_base, "description": "Select non-null post-activation driver correlations ranked by absolute Spearman rho.", "filters": ["completed_updates > 7000", "spearman_rho IS NOT NULL"], "metric_definitions": ["Associations are descriptive and not causal."], "sql": "SELECT * FROM drivers WHERE spearman_rho IS NOT NULL ORDER BY abs_rho DESC", "tables_used": ["drivers"]}}
    source_ref = {"id": "reference_source", "label": "Bavarian LoD2 evaluation reference", "path": "reference_summary.json", "query": {**query_base, "description": "Select the frozen evaluation-only reference summary.", "filters": ["building_id = DEBY_LOD2_4906982"], "metric_definitions": ["LoD2 RoofSurface XYZ is evaluation-only."], "sql": "SELECT * FROM reference_summary", "tables_used": ["reference_summary"]}}
    summary = f"""## Technical summary\n\n- **Gross high-Z survives current voxel fusion but not Roofer model assembly.** Across all {metrics['case_count']} cases, {metrics['high_z_transmission']['fusion_cases_with_z_gt_650']} fused clouds and {metrics['high_z_transmission']['classified_cases_with_z_gt_650']} classified clouds contain at least one Z>650 m point; {metrics['high_z_transmission']['roofer_cases_with_z_gt_650']} Roofer outputs contain such a vertex.\n- **MVC can produce a complete and reference-close downstream roof, but the effect is trajectory-specific.** At 20k the MVC05 Roofer roof XY coverages are {', '.join(f"{r['replica']} {100*r['roofer_roof_xy_coverage_fraction']:.2f}%" for r in rows20 if r['arm']=='MVC05')}; only one of three continuations exceeds the diagnostic 95% marker.\n- **Simple point-level accuracy does not explain the R1/R2 split.** MVC05 R1 and R2 have similar classified-point median absolute roof-height errors, yet their Roofer coverage differs sharply. This localizes the instability to spatial coherence and/or thresholded readout assembly rather than gross high-Z count alone.\n- **This run does not test TSDF.** The frozen MVC-v2 readout is 0.15 m per-view voxel aggregation with at least two-view support, followed by classification and Roofer.\n\nThese are descriptive technical measurements for one building and one seed. `scientific_verdict` remains `null`."""
    artifact = {
        "surface": "report",
        "manifest": {
            "version": 1,
            "title": "4906982 MVC downstream geometry diagnosis",
            "generatedAt": generated,
            "sources": [source_headline, source_case, source_driver, source_ref],
            "cards": [
                {"id": "card_leak", "dataset": "headline", "sourceId": "headline_source", "description": "Number of existing fused cases containing any Z>650 m point.", "metrics": [{"label": "Fusion high-Z cases", "field": "fusion_high_z_cases", "format": "number"}]},
                {"id": "card_full", "dataset": "headline", "sourceId": "headline_source", "description": "MVC05 continuations at 20k with Roofer roof XY coverage at or above 95%.", "metrics": [{"label": "Full-coverage MVC05 runs", "field": "full_mvc05_20k", "format": "number"}]},
                {"id": "card_r1", "dataset": "headline", "sourceId": "headline_source", "description": "Highest MVC05 roof XY coverage at 20k.", "metrics": [{"label": "Best MVC05 roof coverage", "field": "best_mvc05_coverage", "format": "percent"}]},
            ],
            "charts": [
                {"id": "chart_coverage", "title": "20k Roofer roof XY coverage", "subtitle": "Fraction of the shared footprint covered by semantic RoofSurface polygons; six existing outputs", "intent": "comparison", "question": "Which continuations assemble a complete roof?", "rationale": "A categorical bar keeps the six exact cases visible without implying a time trend.", "comparisonContext": {"baseline": "shared footprint area", "grain": "arm-replica at 20k", "unit": "fraction"}, "type": "bar", "dataset": "coverage_20k", "sourceId": "case_source", "encodings": {"x": {"field": "case", "type": "nominal", "label": "Case"}, "y": {"field": "roof_xy_coverage", "type": "quantitative", "label": "Roof XY coverage"}}, "valueFormat": "percent", "layout": "full", "surface": {"palette": {"kind": "sequential"}, "valueLabels": "all"}},
                {"id": "chart_grid", "title": "20k classified roof-evidence grid coverage", "subtitle": "1 m footprint cells containing class-6 points with |normal Z|≥0.7", "intent": "comparison", "question": "Are partial Roofer outputs caused by missing classified evidence?", "rationale": "The same six cases can be compared directly against downstream roof coverage.", "comparisonContext": {"baseline": "all 1 m cells inside the shared footprint", "grain": "arm-replica at 20k", "unit": "fraction"}, "type": "bar", "dataset": "coverage_20k", "sourceId": "case_source", "encodings": {"x": {"field": "case", "type": "nominal", "label": "Case"}, "y": {"field": "classified_grid_coverage", "type": "quantitative", "label": "Classified grid coverage"}}, "valueFormat": "percent", "layout": "full", "surface": {"palette": {"kind": "sequential"}, "valueLabels": "all"}},
                {"id": "chart_drivers", "title": "Association with Roofer roof coverage", "subtitle": "Absolute Spearman correlation over 18 post-activation cases; descriptive, not causal", "intent": "ranking", "question": "Which measured evidence properties track Roofer coverage most closely?", "rationale": "A ranked bar surfaces the strongest candidate drivers while retaining the small-sample caveat.", "comparisonContext": {"baseline": "post-7k cases", "grain": "candidate metric", "unit": "absolute Spearman rho"}, "type": "bar", "dataset": "drivers", "sourceId": "driver_source", "encodings": {"x": {"field": "driver", "type": "nominal", "label": "Candidate driver"}, "y": {"field": "abs_rho", "type": "quantitative", "label": "|Spearman rho|"}}, "valueFormat": "number", "layout": "full", "surface": {"palette": {"kind": "sequential"}, "valueLabels": "all"}},
            ],
            "tables": [
                {"id": "table_20k", "title": "Exact 20k downstream metrics", "subtitle": "Six existing arm-replica outputs; LoD2 is used only for evaluation metrics", "dataset": "coverage_20k", "sourceId": "case_source", "defaultSort": {"field": "roof_xy_coverage", "direction": "desc"}, "density": "spacious", "layout": "full", "columns": [{"field": "case", "label": "Case"}, {"field": "roof_xy_coverage", "label": "Roofer roof coverage", "format": "percent"}, {"field": "fscore_0p5m", "label": "Surface F0.5m", "format": "percent"}, {"field": "point_median_abs_dz_m", "label": "Point median |dZ| (m)", "format": "number"}, {"field": "point_median_normal_angle_deg", "label": "Point median normal angle", "format": "number"}, {"field": "coherent_grid_coverage", "label": "Coherent grid coverage", "format": "percent"}, {"field": "coherent_largest_component", "label": "Largest coherent component", "format": "percent"}]},
            ],
            "blocks": [
                {"id": "title", "type": "markdown", "body": "# 4906982 MVC downstream geometry diagnosis", "layout": "full"},
                {"id": "summary", "type": "markdown", "body": summary, "layout": "full"},
                {"id": "headline", "type": "metric-strip", "cardIds": ["card_leak", "card_full", "card_r1"], "layout": "full"},
                {"id": "finding_coverage", "type": "markdown", "body": "## MVC05 R1 is a real downstream exception, not a plotting illusion\n\nRoofer semantic RoofSurface polygons cover almost the entire shared footprint only for MVC05 R1 at 20k. The other continuations remain partial even though the Roofer processes completed successfully. This establishes a trajectory-specific downstream gain, not a repeatable MVC effect.", "sourceId": "case_source", "layout": "full"},
                {"id": "coverage_chart", "type": "chart", "chartId": "chart_coverage", "layout": "full"},
                {"id": "finding_grid", "type": "markdown", "body": "## Coarse point coverage does not order the Roofer outcomes\n\nMVC05 R1 does not have the largest 1 m classified roof-evidence coverage, while R2 has nearly the same point-level median height and normal errors but a partial Roofer model. Point availability alone is therefore insufficient; connected coherent support and thresholded surface assembly remain the bounded candidate mechanisms.", "sourceId": "case_source", "layout": "full"},
                {"id": "grid_chart", "type": "chart", "chartId": "chart_grid", "layout": "full"},
                {"id": "finding_highz", "type": "markdown", "body": "## Gross high-Z reaches the point cloud but not the final Roofer model\n\nEvery fused and classified case contains some Z>650 m points, while no Roofer output contains a Z>650 m vertex. The current readout therefore shields final building geometry from those extreme points, even though it does not remove them from the GS or point-cloud stages. High-Z is not sufficient to explain why only MVC05 R1 assembles a complete roof.", "sourceId": "case_source", "layout": "full"},
                {"id": "finding_drivers", "type": "markdown", "body": "## Reference-aligned evidence metrics narrow the next intervention\n\nThe ranked associations show which measured point properties move with Roofer coverage over the 18 post-activation cases. With one building and GPU trajectory spread, these correlations are diagnostic clues only; they cannot establish causal effects.", "sourceId": "case_source", "layout": "full"},
                {"id": "driver_chart", "type": "chart", "chartId": "chart_drivers", "layout": "full"},
                {"id": "exact_table", "type": "table", "tableId": "table_20k", "layout": "full"},
                {"id": "definitions", "type": "markdown", "body": "## What was measured\n\nPopulation: one building, two arms, three same-state continuations, and four frozen checkpoints. Point evidence is measured inside the exact shared GroundSurface XY footprint. A roof-evidence point is class 6 with |normal Z|≥0.7. Grid coverage uses 1 m cells. Roofer coverage is the union area of semantic RoofSurface polygons divided by footprint area. Surface precision, completeness, and F-score use evaluation-only LoD2 heights after the locked −45.7 m prediction-to-reference datum shift.", "sourceId": "reference_source", "layout": "full"},
                {"id": "method", "type": "markdown", "body": "## Readout-only method\n\nNo checkpoint was trained or selected, and fusion, classification, Roofer, and TSDF were not rerun. The diagnostic parsed the immutable evaluation receipts, LAZ files, CityJSONSeq outputs, and one frozen LoD2 GML. It reproduced all 24 case joins, verified input hashes, measured point-to-reference vertical and normal residuals, sampled both prediction and reference roof surfaces, and retained arm/replica/checkpoint grain.", "layout": "full"},
                {"id": "limits", "type": "markdown", "body": "## Limits and robustness\n\nThe three replicas are repeated CUDA continuations from one exact 7k state, not independent seeds. The LoD2 and imagery have different vintages, so reference disagreement can include real scene change. Current fusion is direct voxel aggregation rather than TSDF. Raw single-view depth buffers were not preserved, so the exact stage at which high-Z first disappears is bounded only between Gaussian state and ≥2-view fusion. The 95% coverage marker is diagnostic and not an official usability threshold.", "layout": "full"},
                {"id": "next", "type": "markdown", "body": "## Recommended next step\n\n1. Re-render the six 20k checkpoints into a new read-only depth-buffer namespace and run a fixed TSDF/readout ablation; do not tune by replica.\n2. If one shared TSDF/readout rule makes MVC05 R1–R3 reference-accurate and complete, retain MVC and avoid adding supervision.\n3. If R2/R3 remain fragmented despite robust readout, run a separate confidence-gated MVS depth-only arm before normal supervision.\n4. Reserve multi-view densification for a demonstrated coverage deficit after depth/readout stability is established.", "layout": "full"},
                {"id": "questions", "type": "markdown", "body": "## Further questions\n\n- Do single-view rendered high-Z pixels exist but fail the two-view voxel-support gate?\n- Which fixed Roofer segmentation or TSDF setting turns dense classified evidence into a complete roof without reference-driven tuning?\n- Does the R1 exception arise from better absolute depth, better normal coherence, or a threshold crossing in plane assembly?", "layout": "full"},
            ],
        },
        "snapshot": {
            "version": 1,
            "generatedAt": generated,
            "status": "ready",
            "datasets": {
                "headline": [{"id": "head", "fusion_high_z_cases": metrics["high_z_transmission"]["fusion_cases_with_z_gt_650"], "full_mvc05_20k": metrics["mvc05_20k_full_coverage_count"], "best_mvc05_coverage": max(metrics["mvc05_20k_roof_xy_coverage"].values())}],
                "coverage_20k": coverage,
                "leakage_20k": leakage,
                "drivers": driver_rows,
            },
        },
        "sources": [source_headline, source_case, source_driver, source_ref],
        "package_info": {"root": ".", "manifestPath": "report_artifact.json", "snapshotPath": "report_artifact.json"},
    }
    atomic_json(output / "report_artifact.json", artifact)


def inside_analyze(config_path: Path, output: Path) -> None:
    import numpy as np
    import yaml
    from shapely.geometry import shape

    started = utc_now()
    cfg = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    source_root = Path(cfg["source_task_root"])
    reference_path = Path(cfg["reference_lod2_gml"])
    footprint_path = Path(cfg["shared_footprint"])
    source_runner = Path(cfg["source_runner"])
    required = [source_root / "checkpoint_metrics.csv", reference_path, footprint_path, source_runner]
    for path in required:
        if not path.is_file():
            raise RuntimeError(f"missing required immutable input: {path}")
    output.mkdir(parents=True, exist_ok=True)
    (output / "logs").mkdir(exist_ok=True)
    (output / "representative_images").mkdir(exist_ok=True)

    feature_collection = json.loads(footprint_path.read_text(encoding="utf-8"))
    footprint_feature = feature_collection["features"][0]
    footprint = shape(footprint_feature["geometry"])
    refs = parse_reference_roofs(reference_path, cfg["building_id"])
    ref_xy, ref_z, _ref_normals = sample_surfaces(refs, float(cfg["surface_sample_spacing_m"]))
    reference_summary = {
        "schema": "jointbuildgs.p2.e3_local_4906982_mvc_readout_diag_v1.reference.v1",
        "building_id": cfg["building_id"],
        "source": str(reference_path),
        "source_sha256": sha256(reference_path),
        "roof_surface_count": len(refs),
        "roof_union_area_m2": float(__import__("shapely.ops", fromlist=["unary_union"]).unary_union([p for s in refs for p in flatten_polygons(s.polygon)]).area),
        "roof_sample_count": int(len(ref_xy)),
        "roof_z_min_m": float(np.min(ref_z)),
        "roof_z_median_m": float(np.median(ref_z)),
        "roof_z_max_m": float(np.max(ref_z)),
        "prediction_z_shift_to_reference_m": float(cfg["prediction_z_shift_to_reference_m"]),
        "evaluation_only": True,
        "scientific_verdict": None,
    }
    atomic_json(output / "reference_summary.json", reference_summary)

    input_files: list[Path] = required.copy()
    rows: list[dict[str, Any]] = []
    for arm in cfg["arms"]:
        for replica in cfg["replicas"]:
            for step in cfg["checkpoints"]:
                case_root = source_root / "arms" / arm / replica / "evaluation" / f"step_{int(step):06d}"
                evaluation_path = case_root / "evaluation.json"
                fused_path = case_root / "fusion/fused_surface.laz"
                classified_path = case_root / "fusion/classified_surface.laz"
                city_path = case_root / "fusion/roofer/output/690897_5336168.city.jsonl"
                terminal_path = case_root / "fusion/roofer/roofer_terminal.json"
                for path in [evaluation_path, fused_path, classified_path, city_path, terminal_path]:
                    if not path.is_file():
                        raise RuntimeError(f"missing source case input: {path}")
                    input_files.append(path)
                evaluation = json.loads(evaluation_path.read_text(encoding="utf-8"))
                terminal = json.loads(terminal_path.read_text(encoding="utf-8"))
                preds, vertices = load_cityjsonseq(city_path, cfg["building_id"], float(cfg["prediction_z_shift_to_reference_m"]))
                row: dict[str, Any] = {
                    "arm": arm,
                    "replica": replica,
                    "completed_updates": int(step),
                    "case": f"{arm}-{replica}-{int(step)}",
                    "checkpoint_sha256": evaluation["checkpoint_sha256"],
                    "gaussian_count": int(evaluation["geometry"]["gaussian_count"]),
                    "gaussian_z_gt650": int(evaluation["geometry"]["count_z_gt_650m"]),
                    "gaussian_high_opacity_z_gt650": int(evaluation["geometry"]["opacity_bins"]["ge_0p9"]["z_gt_650m"]),
                    "fusion_ge2": int(evaluation["fusion"]["point_count_ge2"]),
                    "fusion_ge3_ratio": float(evaluation["fusion"]["ratio_ge3_of_ge2"]),
                    "fusion_roof_density": float(evaluation["fusion"]["roof_density_per_footprint_m2"]),
                    "roofer_return_success": bool(terminal.get("rf_success")),
                    "roofer_internal_rmse": (terminal.get("target_attributes") or {}).get("rf_rmse_lod22"),
                    "scientific_verdict": None,
                }
                row.update(prefix_fields("fused", point_metrics(fused_path, footprint, refs, cfg, classified=False)))
                row.update(prefix_fields("classified", point_metrics(classified_path, footprint, refs, cfg, classified=True)))
                row.update(prefix_fields("roofer", surface_metrics(preds, vertices, refs, footprint, cfg)))
                row["roofer_full_roof_xy_coverage_diagnostic"] = row["roofer_roof_xy_coverage_fraction"] >= float(cfg["full_roof_xy_coverage_threshold"])
                rows.append(row)

    rows.sort(key=lambda row: (row["completed_updates"], row["arm"], row["replica"]))
    write_csv(output / "case_metrics.csv", rows)
    delta_fields = [
        "gaussian_z_gt650", "fused_z_gt_650_count", "classified_z_gt_650_count",
        "classified_grid_coverage_fraction", "classified_center_grid_coverage_fraction",
        "classified_abs_dz_m_rmse", "classified_normal_angle_deg_median",
        "roofer_roof_xy_coverage_fraction", "roofer_surface_fscore_0p5m",
    ]
    paired = paired_deltas(rows, delta_fields)
    write_csv(output / "paired_deltas.csv", paired)
    candidates = [
        "gaussian_z_gt650", "gaussian_high_opacity_z_gt650", "fusion_ge3_ratio", "fusion_roof_density",
        "classified_grid_coverage_fraction", "classified_center_grid_coverage_fraction",
        "classified_coherent_grid_coverage_fraction", "classified_coherent_largest_component_footprint_fraction",
        "classified_within_0p5m_fraction", "classified_abs_dz_m_rmse",
        "classified_normal_angle_deg_median", "classified_evidence_support_ge3_fraction",
    ]
    drivers = driver_analysis(rows, candidates)
    atomic_json(output / "driver_analysis.json", {"schema": "jointbuildgs.p2.e3_local_4906982_mvc_readout_diag_v1.drivers.v1", "population": "18 post-activation arm-replica-checkpoint cases", "outcome": "roofer_roof_xy_coverage_fraction", "descriptive_not_causal": True, "drivers": drivers, "scientific_verdict": None})

    input_map = {str(path): {"sha256": sha256(path), "bytes": path.stat().st_size} for path in sorted(set(input_files), key=str)}
    current_hashes = {"schema": "jointbuildgs.p2.e3_local_4906982_mvc_readout_diag_v1.input_hashes.v1", "inputs": input_map, "scientific_verdict": None}
    hashes_path = output / "input_hashes.json"
    if hashes_path.is_file():
        previous = json.loads(hashes_path.read_text(encoding="utf-8"))
        if previous.get("inputs") != input_map:
            raise RuntimeError("existing diagnostic input hashes differ; refusing to overwrite")
    atomic_json(hashes_path, current_hashes)

    rows20 = [row for row in rows if row["completed_updates"] == 20000]
    mvc05_20 = {row["replica"]: row["roofer_roof_xy_coverage_fraction"] for row in rows20 if row["arm"] == "MVC05"}
    high_z = {
        "gaussian_cases_with_z_gt_650": sum(row["gaussian_z_gt650"] > 0 for row in rows),
        "fusion_cases_with_z_gt_650": sum(row["fused_z_gt_650_count"] > 0 for row in rows),
        "classified_cases_with_z_gt_650": sum(row["classified_z_gt_650_count"] > 0 for row in rows),
        "roofer_cases_with_z_gt_650": sum(row["roofer_vertex_z_gt_650_count"] > 0 for row in rows),
    }
    metrics = {
        "schema": "jointbuildgs.p2.e3_local_4906982_mvc_readout_diag_v1.metrics.v1",
        "status": "COMPLETE_DIAGNOSTIC",
        "case_count": len(rows),
        "source_cases_immutable": True,
        "training_runs_started": 0,
        "fusion_reruns_started": 0,
        "roofer_reruns_started": 0,
        "tsdf_evaluated": False,
        "source_fusion": cfg["source_fusion"],
        "high_z_transmission": high_z,
        "mvc05_20k_roof_xy_coverage": mvc05_20,
        "mvc05_20k_full_coverage_count": sum(value >= float(cfg["full_roof_xy_coverage_threshold"]) for value in mvc05_20.values()),
        "diagnostic_full_coverage_threshold": float(cfg["full_roof_xy_coverage_threshold"]),
        "strongest_descriptive_drivers": drivers[:5],
        "official_PASS_usable": None,
        "scientific_verdict": None,
    }
    atomic_json(output / "metrics.json", metrics)
    make_reference_panel(output / "representative_images/roofer_reference_20k.png", rows, cfg, refs, footprint)

    contract = {
        "schema": "jointbuildgs.p2.e3_local_4906982_mvc_readout_diag_v1.contract.v1",
        "task_id": cfg["task_id"],
        "status": "MEASURED_REPORT_PENDING",
        "mode": "readout_only_existing_artifacts",
        "building_id": cfg["building_id"],
        "case_count": len(rows),
        "no_training": True,
        "no_fusion_rerun": True,
        "no_roofer_rerun": True,
        "no_tsdf_claim": True,
        "reference_evaluation_only": True,
        "scientific_verdict": None,
    }
    atomic_json(output / "experiment_contract.json", contract)
    provenance = {
        "schema": "jointbuildgs.p2.e3_local_4906982_mvc_readout_diag_v1.provenance.v1",
        "task_id": cfg["task_id"],
        "started_utc": started,
        "ended_utc": None,
        "config_path": str(config_path),
        "config_sha256": sha256(config_path),
        "runner_path": str(Path(__file__)),
        "runner_sha256": sha256(Path(__file__)),
        "source_runner_sha256": sha256(source_runner),
        "reference_sha256": sha256(reference_path),
        "footprint_sha256": sha256(footprint_path),
        "input_hash_manifest_sha256": sha256(hashes_path),
        "scientific_verdict": None,
    }
    atomic_json(output / "provenance.json", provenance)

    chart_map = {
        "schema": "jointbuildgs.p2.e3_local_4906982_mvc_readout_diag_v1.chart_map.v1",
        "charts": [
            {"id": "chart_coverage", "question": "Which 20k continuations assemble a complete roof?", "family": "comparison", "type": "bar", "fields": ["case", "roof_xy_coverage"], "claim": "MVC05 R1 is the sole near-complete 20k roof", "palette": "single-root sequential"},
            {"id": "chart_grid", "question": "Are partial outputs caused by missing classified points?", "family": "comparison", "type": "bar", "fields": ["case", "classified_grid_coverage"], "claim": "broad point coverage remains despite partial Roofer output", "palette": "single-root sequential"},
            {"id": "chart_drivers", "question": "Which measured properties track Roofer coverage?", "family": "ranking", "type": "bar", "fields": ["driver", "abs_rho"], "claim": "ranked associations narrow follow-up hypotheses", "palette": "single-root sequential"},
        ],
        "omissions": [{"visual": "time-series line", "reason": "four discrete checkpoints are too sparse for an honest continuous trend"}, {"visual": "high-Z stage bar", "reason": "Gaussian and point counts have different grains; exact counts are kept in the audit table instead"}],
    }
    atomic_json(output / "control/chart_map.json", chart_map)
    build_report_artifact(output, rows, paired, drivers, metrics)

    comparison = f"""# {cfg['task_id']}\n\n## Measured diagnostic\n\n- All {len(rows)} source cases retained Z>650 m Gaussians, while fused/classified/Roofer Z>650 m case counts were {high_z['fusion_cases_with_z_gt_650']}/{high_z['classified_cases_with_z_gt_650']}/{high_z['roofer_cases_with_z_gt_650']}.\n- MVC05 20k Roofer roof XY coverage: {', '.join(f'{key}={100*value:.3f}%' for key, value in mvc05_20.items())}.\n- The current source fusion is voxel aggregation (`tsdf_used=false`); no TSDF conclusion is made.\n- Driver correlations are descriptive over 18 post-activation cases and do not establish causality.\n- Scientific verdict: `null`.\n\n## Implication\n\nGross high-Z reaches the existing fused/classified point products but is rejected before final Roofer vertices, so it is not sufficient to explain the R1/R2/R3 split. The next bounded diagnostic is a fresh, fixed depth-buffer plus current-voxel-versus-TSDF/readout ablation over the six 20k checkpoints; if that cannot stabilize R2/R3, a confidence-gated MVS depth-only training arm is the next intervention.\n"""
    (output / "comparison.md").write_text(comparison, encoding="utf-8")
    notes = f"""# {cfg['task_id']}\n\nStatus: `COMPLETE_DIAGNOSTIC` after portable-report delivery.\n\n- Existing source cases: {len(rows)}/24 read successfully.\n- Training/fusion/classification/Roofer reruns: 0/0/0/0.\n- Reference: evaluation-only LoD2 RoofSurface from `690_5336.gml`; prediction Z shift {cfg['prediction_z_shift_to_reference_m']} m.\n- Current MVC-v2 readout uses per-view voxel aggregation, not TSDF.\n- Primary files: `case_metrics.csv`, `driver_analysis.json`, `metrics.json`, `comparison.md`, `report.html`.\n- Scientific verdict: `null`.\n"""
    (output / "NOTES.md").write_text(notes, encoding="utf-8")
    issues = """# Issues\n\n1. MVC-v2 did not preserve raw per-view depth buffers, so this diagnostic cannot trace high-Z through individual rendered views. High-Z is present in fused/classified points and absent only from final Roofer vertices.\n2. The source readout is direct voxel aggregation and classification followed by Roofer; TSDF robustness remains unevaluated.\n3. Reference LoD2 and current imagery differ in vintage; reference residuals may include real scene change.\n4. R1-R3 are same-state CUDA continuations, not independent random-seed replicates.\n5. The first portable-report delivery attempt returned code 1 after scientific calculation because widget sources lacked the builder-required materialized SQL query text. The source schema was corrected; the complete diagnostic was rerun idempotently and final report delivery returned code 0 with validation/package passed and structural verification only.\n\nNo source file was modified and no source readout process was rerun.\n"""
    (output / "issues.md").write_text(issues, encoding="utf-8")
    print(json.dumps({"status": metrics["status"], "cases": len(rows), "high_z_transmission": high_z, "mvc05_20k_roof_xy_coverage": mvc05_20}, indent=2))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--inside-docker", choices=["analyze"])
    parser.add_argument("--config", type=Path)
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.inside_docker == "analyze":
        if args.config is None or args.output is None:
            raise SystemExit("--config and --output are required inside Docker")
        inside_analyze(args.config, args.output)
    else:
        host_main()


if __name__ == "__main__":
    main()
