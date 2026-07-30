#!/usr/bin/env python3
"""Build the E5 C001 8-way reference-matched comparison.

Read-only over existing C001 products.  This script does not train, rerun
Roofer, or change the recipe.  It compares each assembled roof shell to the
LoD2 reference roof surfaces and writes observation material only.
"""

from __future__ import annotations

import csv
import json
import math
import os
import shutil
import subprocess
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import laspy
import matplotlib
import numpy as np
from lxml import etree
from shapely import contains_xy, make_valid
from shapely.geometry import GeometryCollection, MultiPolygon, Polygon, shape

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
from mpl_toolkits.mplot3d.art3d import Poly3DCollection

import pointcloud_attributes_v1 as base
from e5_pilot_gate_tools import C001_IDS, READOUT_STRING, run_names


REPO = Path(__file__).resolve().parents[3]
GATE_RUN_DIR = Path("phases/p0-audit/runs/e5p_gate_20260707_C001")
TRAIN_RUN_DIR = Path("phases/p2-gsjso/runs/e5p_train_20260707_C001")
RUN_ID = "20260707_e5_c001_8way"
RUN_DIR = Path("phases/p2-gsjso/runs") / RUN_ID
LOD2_DIR = Path("phases/p0-audit/data/raw/lod2")
FOOTPRINTS_GPKG = Path("phases/p0-audit/data/work/w2/footprints_scene_aoi.gpkg")
W2_RUN = Path("phases/p0-audit/runs/w2_1_roofer_default_20260612_152729")
SPARSE_RUN = Path("phases/p0-audit/runs/e5p_baseline_sparse_20260706_002300")
ACMP_RUN = Path("phases/p0-audit/runs/e5p_baseline_acmp_20260706_001813")

REPORT_PATH = Path("docs/experiments/evaluation/e5_c001_8way/reports/W_E5_C001_8way.md")
METRICS_CSV = Path("docs/experiments/evaluation/e5_c001_8way/tables/e5_c001_8way_metrics.csv")
SOURCE_SUMMARY_CSV = Path("docs/experiments/evaluation/e5_c001_8way/tables/e5_c001_8way_source_summary.csv")
CORRECTION_GAIN_CSV = Path("docs/experiments/evaluation/e5_c001_8way/tables/e5_c001_8way_correction_gain.csv")
CORRECTION_GAIN_SUMMARY_CSV = Path("docs/experiments/evaluation/e5_c001_8way/tables/e5_c001_8way_correction_gain_summary.csv")
STRATA_SUMMARY_CSV = Path("docs/experiments/evaluation/e5_c001_8way/tables/e5_c001_8way_strata_summary.csv")
INVENTORY_CSV = Path("docs/experiments/evaluation/e5_c001_8way/tables/e5_c001_8way_inventory.csv")
FIG_DIR = Path("docs/figs/e5_c001_8way")

MATCH_IOU_MIN = 0.02
MATCH_OVERLAP_MIN_M2 = 0.50
MATCH_Z_P50_MAX_M = 5.0
SAMPLE_SPACING_M = 0.50
MAX_PLOT_POINTS = 15000
RNG = np.random.default_rng(20260707)
ELLIP_TO_REF_SHIFT_M = -45.7
SHELL_FIG_LABEL = {
    "미조립": "not built",
    "지붕면0 성공": "roof0 success",
    "무효·붕괴": "invalid/collapse",
    "조립": "assembled",
    "참조": "reference",
}


@dataclass
class RoofSurface:
    surface_id: str
    polygon: Polygon | MultiPolygon
    x0: float
    y0: float
    z0: float
    ax: float
    by: float

    def z_at(self, x: np.ndarray, y: np.ndarray) -> np.ndarray:
        return self.z0 + self.ax * (x - self.x0) + self.by * (y - self.y0)


@dataclass
class Source:
    source_group: str
    source_run: str
    display_label: str
    status_role: str
    status_path: Path | None
    status_input: str | None
    cityjson_path: Path | None
    pointcloud_path: Path | None
    pointcloud_template: str | None = None
    pair_raw: str | None = None
    run_name: str | None = None
    seed: str | None = None
    replicate: str | None = None
    readout: str = ""
    source_badge: str = ""
    z_shift_to_reference_m: float = 0.0


def configure_korean_font() -> None:
    for path in [
        Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Medium.ttc"),
        Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
        Path("/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc"),
    ]:
        if path.exists():
            font_manager.fontManager.addfont(str(path))
            plt.rcParams["font.family"] = "Noto Sans CJK JP"
            plt.rcParams["axes.unicode_minus"] = False
            break


def rel(path: Path | str | None) -> str:
    if path is None:
        return ""
    p = Path(path)
    try:
        return str(p.relative_to(REPO))
    except ValueError:
        return str(p)


def capture(cmd: list[str]) -> str:
    try:
        return subprocess.check_output(cmd, cwd=REPO, text=True, stderr=subprocess.STDOUT).strip()
    except Exception as exc:  # noqa: BLE001 - versions should preserve failures as text.
        return f"not_available:{exc}"


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fields: list[str] = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def tf(value: Any) -> bool:
    return str(value).strip().lower() in {"true", "1", "yes", "y"}


def num(value: Any) -> float | None:
    if value is None:
        return None
    text = str(value).strip()
    if text == "" or text.lower() in {"none", "nan", "na"}:
        return None
    try:
        v = float(text)
    except ValueError:
        return None
    return v if math.isfinite(v) else None


def fmt(value: Any, digits: int = 4) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, np.integer)):
        return str(int(value))
    if isinstance(value, (float, np.floating)):
        v = float(value)
        if not math.isfinite(v):
            return ""
        return f"{v:.{digits}f}"
    return str(value)


def short_id(building_id: str) -> str:
    return building_id.replace("DEBY_LOD2_", "")


def sources() -> list[Source]:
    out = [
        Source(
            "raw_sparse",
            "raw_sparse",
            "raw sparse",
            "baseline",
            SPARSE_RUN / "building_reconstruction_status.csv",
            "raw-sparse",
            SPARSE_RUN / "cityjson/raw_sparse_roofer.city.json",
            SPARSE_RUN / "classified/raw_sparse_classified.laz",
            z_shift_to_reference_m=ELLIP_TO_REF_SHIFT_M,
        ),
        Source(
            "raw_dense",
            "raw_dense",
            "raw dense(MVS)",
            "baseline",
            W2_RUN / "building_reconstruction_status.csv",
            "DIM",
            W2_RUN / "cityjson/dim_roofer.city.json",
            Path("phases/p0-audit/data/work/w2/dim_v1_classified_z_minus0p174.laz"),
        ),
        Source(
            "raw_acmp",
            "raw_acmp",
            "raw acmp",
            "baseline",
            ACMP_RUN / "building_reconstruction_status.csv",
            "raw-ACMP",
            ACMP_RUN / "cityjson/raw_acmp_roofer.city.json",
            ACMP_RUN / "classified/raw_acmp_classified.laz",
            z_shift_to_reference_m=ELLIP_TO_REF_SHIFT_M,
        ),
    ]
    for name in run_names():
        arm = name.split("_")[-2]
        rep = name.split("_")[-1]
        out.append(
            Source(
                f"gs_{arm}",
                f"gs_{arm}_{rep}",
                f"GS {arm} {rep}",
                "gs",
                GATE_RUN_DIR / "building_reconstruction_status.csv",
                None,
                GATE_RUN_DIR / "cityjson" / f"{name}_run_1.city.json",
                None,
                pointcloud_template=str(GATE_RUN_DIR / "roofer" / name / "run_1" / "{bid}_run_1_classified.las"),
                pair_raw=f"raw_{arm}",
                run_name=name,
                seed=arm,
                replicate=rep,
                readout=READOUT_STRING,
                z_shift_to_reference_m=ELLIP_TO_REF_SHIFT_M,
            )
        )
    out.append(
        Source(
            "lidar",
            "lidar",
            "LiDAR (완전측량 기준선)",
            "lidar",
            W2_RUN / "building_reconstruction_status.csv",
            "ALS",
            W2_RUN / "cityjson/als_roofer.city.json",
            Path("results/tum_transfer/mob_analysis/p0c_step2/als_aoi.laz"),
            source_badge="완전측량 기준선",
        )
    )
    out.append(
        Source(
            "reference",
            "reference",
            "참조 LoD2",
            "reference",
            None,
            None,
            None,
            None,
            source_badge="정답",
        )
    )
    return out


def inventory_rows(srcs: list[Source]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for src in srcs:
        if src.status_role == "reference":
            rows.append(
                {
                    "source_run": src.source_run,
                    "source_group": src.source_group,
                    "status": "present",
                    "status_path": "",
                    "cityjson_path": "phases/p0-audit/data/raw/lod2/*.gml",
                    "pointcloud_path": "",
                    "z_shift_to_reference_m": "0.0000",
                    "note": "LoD2 reference RoofSurface count and shape",
                }
            )
            continue
        required = [src.status_path, src.cityjson_path]
        if src.pointcloud_path is not None:
            required.append(src.pointcloud_path)
        missing = [rel(p) for p in required if p is not None and not p.exists()]
        if src.pointcloud_template:
            missing.extend(
                rel(Path(src.pointcloud_template.format(bid=bid)))
                for bid in C001_IDS
                if not Path(src.pointcloud_template.format(bid=bid)).exists()
            )
        rows.append(
            {
                "source_run": src.source_run,
                "source_group": src.source_group,
                "status": "present" if not missing else "missing",
                "status_path": rel(src.status_path),
                "cityjson_path": rel(src.cityjson_path),
                "pointcloud_path": rel(src.pointcloud_path) if src.pointcloud_path else src.pointcloud_template or "",
                "z_shift_to_reference_m": fmt(src.z_shift_to_reference_m),
                "missing_count": len(missing),
                "missing_examples": ";".join(missing[:5]),
                "note": src.source_badge,
            }
        )
    return rows


def parse_lod2_roofs(lod2_dir: Path, target_ids: set[str]) -> dict[str, list[RoofSurface]]:
    output: dict[str, list[RoofSurface]] = {building_id: [] for building_id in target_ids}
    for path in sorted(lod2_dir.glob("*.gml")):
        for _event, elem in etree.iterparse(str(path), events=("end",), recover=True):
            if local_name(elem.tag) != "Building":
                continue
            building_id = gml_id(elem)
            if building_id in target_ids:
                output[building_id].extend(extract_gml_roof_surfaces(building_id, elem))
            elem.clear()
            parent = elem.getparent()
            while parent is not None and elem.getprevious() is not None:
                del parent[0]
    missing = [bid for bid, roofs in output.items() if not roofs]
    if missing:
        raise RuntimeError(f"missing reference RoofSurface for {missing}")
    return output


def extract_gml_roof_surfaces(building_id: str, building: etree._Element) -> list[RoofSurface]:
    surfaces: list[RoofSurface] = []
    roof_idx = 0
    for roof in building.iter():
        if local_name(roof.tag) != "RoofSurface":
            continue
        roof_idx += 1
        roof_id = gml_id(roof) or f"{building_id}_roof_{roof_idx}"
        poly_idx = 0
        for polygon in roof.iter():
            if local_name(polygon.tag) != "Polygon":
                continue
            poly_idx += 1
            rings = parse_gml_polygon_rings(polygon)
            if rings:
                surf = roof_surface_from_rings(f"{roof_id}_{poly_idx}", rings)
                if surf:
                    surfaces.append(surf)
    return surfaces


def parse_gml_polygon_rings(polygon: etree._Element) -> list[np.ndarray]:
    exterior: np.ndarray | None = None
    interiors: list[np.ndarray] = []
    for child in polygon:
        lname = local_name(child.tag)
        if lname == "exterior":
            exterior = first_poslist_ring(child)
        elif lname == "interior":
            ring = first_poslist_ring(child)
            if ring is not None:
                interiors.append(ring)
    if exterior is None:
        return [parse_poslist(e.text) for e in polygon.iter() if local_name(e.tag) == "posList" and e.text]
    return [exterior, *interiors]


def first_poslist_ring(elem: etree._Element) -> np.ndarray | None:
    for child in elem.iter():
        if local_name(child.tag) == "posList" and child.text:
            return parse_poslist(child.text)
    return None


def parse_poslist(text: str) -> np.ndarray:
    vals = [float(x) for x in text.split()]
    return np.asarray(vals, dtype=float).reshape(-1, 3)


def parse_cityjson_roofs(path: Path | None, target_ids: set[str]) -> dict[str, list[RoofSurface]]:
    output: dict[str, list[RoofSurface]] = {bid: [] for bid in target_ids}
    if path is None or not path.exists():
        return output
    payload = json.loads(path.read_text(encoding="utf-8"))
    vertices = absolute_vertices(payload.get("vertices", []), payload.get("transform") or {})
    cityobjects = payload.get("CityObjects", {})
    for bid in target_ids:
        object_ids = [bid, *cityobjects.get(bid, {}).get("children", [])]
        surfaces: list[RoofSurface] = []
        for object_id in object_ids:
            obj = cityobjects.get(object_id)
            if not obj:
                continue
            surfaces.extend(extract_cityjson_roof_surfaces(object_id, obj, vertices))
        output[bid] = surfaces
    return output


def shift_surface_z(surfaces: list[RoofSurface], dz: float) -> list[RoofSurface]:
    if abs(dz) < 1e-12:
        return surfaces
    return [
        RoofSurface(
            surface_id=s.surface_id,
            polygon=s.polygon,
            x0=s.x0,
            y0=s.y0,
            z0=s.z0 + dz,
            ax=s.ax,
            by=s.by,
        )
        for s in surfaces
    ]


def absolute_vertices(vertices: list[list[int | float]], transform: dict[str, list[float]]) -> np.ndarray:
    arr = np.asarray(vertices, dtype=float)
    if not len(arr):
        return arr.reshape((0, 3))
    scale = np.asarray(transform.get("scale", [1.0, 1.0, 1.0]), dtype=float)
    translate = np.asarray(transform.get("translate", [0.0, 0.0, 0.0]), dtype=float)
    return arr * scale + translate


def extract_cityjson_roof_surfaces(object_id: str, obj: dict[str, Any], vertices: np.ndarray) -> list[RoofSurface]:
    surfaces: list[RoofSurface] = []
    for geom_idx, geom in enumerate(obj.get("geometry", [])):
        semantics = geom.get("semantics") or {}
        semantic_surfaces = semantics.get("surfaces") or []
        values = semantics.get("values")
        for face_idx, (rings, sem_idx) in enumerate(iter_cityjson_faces(geom.get("type"), geom.get("boundaries"), values)):
            if sem_idx is None:
                continue
            try:
                sem_i = int(sem_idx)
            except (TypeError, ValueError):
                continue
            if sem_i < 0 or sem_i >= len(semantic_surfaces):
                continue
            if semantic_surfaces[sem_i].get("type") != "RoofSurface":
                continue
            ring_coords = []
            for ring in rings:
                if ring:
                    ring_coords.append(np.asarray([vertices[int(idx)] for idx in ring], dtype=float))
            if not ring_coords:
                continue
            surf = roof_surface_from_rings(f"{object_id}_g{geom_idx}_f{face_idx}", ring_coords)
            if surf:
                surfaces.append(surf)
    return surfaces


def iter_cityjson_faces(geom_type: str | None, boundaries: Any, values: Any) -> list[tuple[list[list[int]], int | None]]:
    faces: list[tuple[list[list[int]], int | None]] = []
    if boundaries is None:
        return faces
    if geom_type == "Solid":
        for shell_idx, shell in enumerate(boundaries):
            shell_values = values[shell_idx] if isinstance(values, list) and shell_idx < len(values) else []
            for face_idx, rings in enumerate(shell):
                sem_idx = shell_values[face_idx] if isinstance(shell_values, list) and face_idx < len(shell_values) else None
                faces.append((rings, sem_idx))
    elif geom_type in {"MultiSurface", "CompositeSurface"}:
        for face_idx, rings in enumerate(boundaries):
            sem_idx = values[face_idx] if isinstance(values, list) and face_idx < len(values) else None
            faces.append((rings, sem_idx))
    elif geom_type == "MultiSolid":
        for solid_idx, solid in enumerate(boundaries):
            solid_values = values[solid_idx] if isinstance(values, list) and solid_idx < len(values) else []
            for shell_idx, shell in enumerate(solid):
                shell_values = solid_values[shell_idx] if isinstance(solid_values, list) and shell_idx < len(solid_values) else []
                for face_idx, rings in enumerate(shell):
                    sem_idx = shell_values[face_idx] if isinstance(shell_values, list) and face_idx < len(shell_values) else None
                    faces.append((rings, sem_idx))
    return faces


def roof_surface_from_rings(surface_id: str, rings: list[np.ndarray]) -> RoofSurface | None:
    exterior = normalize_ring_3d(rings[0])
    if exterior is None:
        return None
    holes = []
    for ring in rings[1:]:
        normalized = normalize_ring_3d(ring)
        if normalized is not None:
            holes.append(normalized[:, :2])
    polygon = repair_polygon(Polygon(exterior[:, :2], holes))
    if polygon is None or polygon.area <= 0.05:
        return None
    x0, y0, z0, ax, by = fit_z_plane(exterior)
    return RoofSurface(surface_id, polygon, x0, y0, z0, ax, by)


def normalize_ring_3d(coords: np.ndarray) -> np.ndarray | None:
    arr = np.asarray(coords, dtype=float)
    if arr.ndim != 2 or arr.shape[1] != 3 or arr.shape[0] < 3:
        return None
    if not np.all(np.isfinite(arr)):
        return None
    if not np.allclose(arr[0], arr[-1]):
        arr = np.vstack([arr, arr[0]])
    if polygon_area_xy(arr[:, :2]) <= 0.05:
        return None
    return arr


def polygon_area_xy(xy: np.ndarray) -> float:
    if xy.shape[0] < 3:
        return 0.0
    return float(abs(np.dot(xy[:, 0], np.roll(xy[:, 1], -1)) - np.dot(xy[:, 1], np.roll(xy[:, 0], -1))) / 2.0)


def repair_polygon(poly: Polygon) -> Polygon | MultiPolygon | None:
    if poly.is_empty:
        return None
    if not poly.is_valid:
        poly = make_valid(poly)
    polygons = [p for p in flatten_polygons(poly) if p.area > 0.05]
    if not polygons:
        return None
    return polygons[0] if len(polygons) == 1 else MultiPolygon(polygons)


def flatten_polygons(geom: Any) -> list[Polygon]:
    if geom is None or geom.is_empty:
        return []
    if isinstance(geom, Polygon):
        return [geom]
    if isinstance(geom, MultiPolygon):
        return list(geom.geoms)
    if isinstance(geom, GeometryCollection):
        out: list[Polygon] = []
        for item in geom.geoms:
            out.extend(flatten_polygons(item))
        return out
    return []


def fit_z_plane(coords: np.ndarray) -> tuple[float, float, float, float, float]:
    points = coords[:-1] if len(coords) >= 2 and np.allclose(coords[0], coords[-1]) else coords
    x0 = float(np.mean(points[:, 0]))
    y0 = float(np.mean(points[:, 1]))
    z0 = float(np.mean(points[:, 2]))
    if len(points) < 3:
        return x0, y0, z0, 0.0, 0.0
    a = np.column_stack([points[:, 0] - x0, points[:, 1] - y0])
    b = points[:, 2] - z0
    try:
        ax, by = np.linalg.lstsq(a, b, rcond=None)[0]
    except np.linalg.LinAlgError:
        ax, by = 0.0, 0.0
    return x0, y0, z0, float(ax), float(by)


def local_name(tag: str) -> str:
    return tag.split("}", 1)[-1]


def gml_id(elem: etree._Element) -> str:
    for key, value in elem.attrib.items():
        if local_name(key) == "id":
            return value
    return ""


def load_status_maps(srcs: list[Source]) -> dict[str, dict[str, dict[str, str]]]:
    maps: dict[str, dict[str, dict[str, str]]] = {}
    for src in srcs:
        if src.status_path is None:
            maps[src.source_run] = {}
            continue
        rows = read_csv(src.status_path)
        selected: dict[str, dict[str, str]] = {}
        for row in rows:
            if row.get("building_id") not in C001_IDS:
                continue
            if src.status_role == "gs":
                if row.get("run_name") == src.run_name and row.get("roofer_repeat") == "run_1":
                    selected[row["building_id"]] = row
            elif row.get("input") == src.status_input:
                selected[row["building_id"]] = row
        maps[src.source_run] = selected
    return maps


def compare_building(refs: list[RoofSurface], preds: list[RoofSurface]) -> dict[str, Any]:
    matches = match_surfaces(refs, preds)
    ref_n = len(refs)
    pred_n = len(preds)
    match_n = len(matches)
    dist = reference_distance(preds, refs)
    return {
        "match_count": match_n,
        "completeness": match_n / ref_n if ref_n else None,
        "correctness": match_n / pred_n if pred_n else None,
        "mean_match_iou": float(np.mean([m["iou"] for m in matches])) if matches else None,
        "ref_rms_m": dist["ref_rms_m"],
        "ref_hausdorff_m": dist["ref_hausdorff_m"],
        "ref_distance_samples": dist["ref_distance_samples"],
    }


def match_surfaces(refs: list[RoofSurface], preds: list[RoofSurface]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for ref_idx, ref in enumerate(refs):
        for pred_idx, pred in enumerate(preds):
            inter = ref.polygon.intersection(pred.polygon)
            overlap = inter.area
            if overlap < MATCH_OVERLAP_MIN_M2:
                continue
            union = ref.polygon.union(pred.polygon).area
            if union <= 0:
                continue
            iou = overlap / union
            if iou < MATCH_IOU_MIN:
                continue
            dz = surface_pair_abs_dz(ref, pred, inter)
            if dz is None or dz > MATCH_Z_P50_MAX_M:
                continue
            candidates.append({"score": (iou, overlap, -dz), "iou": iou, "overlap_m2": overlap, "dz_p50_m": dz, "ref_idx": ref_idx, "pred_idx": pred_idx})
    candidates.sort(key=lambda x: x["score"], reverse=True)
    used_ref: set[int] = set()
    used_pred: set[int] = set()
    matches: list[dict[str, Any]] = []
    for cand in candidates:
        if cand["ref_idx"] in used_ref or cand["pred_idx"] in used_pred:
            continue
        used_ref.add(cand["ref_idx"])
        used_pred.add(cand["pred_idx"])
        matches.append(cand)
    return matches


def surface_pair_abs_dz(ref: RoofSurface, pred: RoofSurface, overlap_geom: Any) -> float | None:
    pts = sample_polygon_points(overlap_geom, SAMPLE_SPACING_M, limit=500)
    if len(pts) == 0:
        return None
    dz = pred.z_at(pts[:, 0], pts[:, 1]) - ref.z_at(pts[:, 0], pts[:, 1])
    if len(dz) == 0:
        return None
    return float(np.median(np.abs(dz)))


def reference_distance(preds: list[RoofSurface], refs: list[RoofSurface]) -> dict[str, Any]:
    diffs: list[np.ndarray] = []
    for pred in preds:
        pts = sample_polygon_points(pred.polygon, SAMPLE_SPACING_M, limit=1200)
        if len(pts) == 0:
            continue
        pred_z = pred.z_at(pts[:, 0], pts[:, 1])
        ref_z = np.full(len(pts), np.nan, dtype=float)
        for idx, (x, y) in enumerate(pts):
            candidates = [ref for ref in refs if any(poly.covers(shape_point(x, y)) for poly in flatten_polygons(ref.polygon))]
            if not candidates:
                candidates = sorted(refs, key=lambda r: min(poly.distance(shape_point(x, y)) for poly in flatten_polygons(r.polygon)))[:1]
            if candidates:
                z_vals = np.asarray([ref.z_at(np.asarray([x]), np.asarray([y]))[0] for ref in candidates], dtype=float)
                ref_z[idx] = z_vals[int(np.argmin(np.abs(pred_z[idx] - z_vals)))]
        finite = np.isfinite(ref_z)
        if np.any(finite):
            diffs.append(pred_z[finite] - ref_z[finite])
    if not diffs:
        return {"ref_rms_m": None, "ref_hausdorff_m": None, "ref_distance_samples": 0}
    values = np.concatenate(diffs)
    return {
        "ref_rms_m": float(np.sqrt(np.mean(values * values))),
        "ref_hausdorff_m": float(np.max(np.abs(values))),
        "ref_distance_samples": int(values.size),
    }


def shape_point(x: float, y: float) -> Any:
    # Avoid importing Point in tight loops at call sites.
    from shapely.geometry import Point

    return Point(float(x), float(y))


def sample_polygon_points(geom: Any, spacing: float, limit: int | None = None) -> np.ndarray:
    points: list[tuple[float, float]] = []
    for polygon in flatten_polygons(geom):
        if polygon.area <= 0:
            continue
        min_x, min_y, max_x, max_y = polygon.bounds
        xs = np.arange(min_x + spacing / 2.0, max_x, spacing)
        ys = np.arange(min_y + spacing / 2.0, max_y, spacing)
        if xs.size and ys.size:
            xx, yy = np.meshgrid(xs, ys)
            mask = contains_xy(polygon, xx.ravel(), yy.ravel())
            pts = list(zip(xx.ravel()[mask], yy.ravel()[mask]))
            points.extend(pts)
        if not points:
            pt = polygon.representative_point()
            points.append((pt.x, pt.y))
    arr = np.asarray(points, dtype=float) if points else np.empty((0, 2), dtype=float)
    if limit is not None and len(arr) > limit:
        idx = RNG.choice(len(arr), limit, replace=False)
        arr = arr[idx]
    return arr


def build_metric_rows(
    srcs: list[Source],
    refs: dict[str, list[RoofSurface]],
    pred_by_source: dict[str, dict[str, list[RoofSurface]]],
    status_maps: dict[str, dict[str, dict[str, str]]],
    lenses: dict[str, dict[str, str]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for src in srcs:
        for bid in C001_IDS:
            ref_surfaces = refs[bid]
            if src.status_role == "reference":
                row = base_metric_row(src, bid, lenses)
                row.update(
                    {
                        "has_lod22": "true",
                        "val3dity_valid": "true",
                        "status_reason": "reference",
                        "roof_planes": len(ref_surfaces),
                        "ref_roof_planes": len(ref_surfaces),
                        "match_count": len(ref_surfaces),
                        "completeness": "1.0000",
                        "correctness": "1.0000",
                        "mean_match_iou": "1.0000",
                        "ref_rms_m": "0.0000",
                        "ref_hausdorff_m": "0.0000",
                        "ref_distance_samples": "",
                        "rf_rmse_lod22": "",
                        "shell_bucket": "참조",
                    }
                )
                rows.append(row)
                continue
            status = status_maps[src.source_run].get(bid, {})
            preds = pred_by_source[src.source_run].get(bid, [])
            metrics = compare_building(ref_surfaces, preds)
            row = base_metric_row(src, bid, lenses)
            has_lod22 = tf(status.get("has_lod22"))
            valid = tf(status.get("val3dity_valid"))
            roof_planes = len(preds)
            row.update(
                {
                    "has_lod22": fmt(has_lod22),
                    "val3dity_valid": fmt(valid),
                    "status": status.get("status", ""),
                    "status_reason": status.get("reason", ""),
                    "rf_success": status.get("rf_success", ""),
                    "rf_pointcloud_unusable": status.get("rf_pointcloud_unusable", ""),
                    "roof_planes": roof_planes,
                    "status_rf_roof_planes": status.get("rf_roof_planes", ""),
                    "ref_roof_planes": len(ref_surfaces),
                    "match_count": metrics["match_count"],
                    "completeness": fmt(metrics["completeness"]),
                    "correctness": fmt(metrics["correctness"]),
                    "mean_match_iou": fmt(metrics["mean_match_iou"]),
                    "ref_rms_m": fmt(metrics["ref_rms_m"]),
                    "ref_hausdorff_m": fmt(metrics["ref_hausdorff_m"]),
                    "ref_distance_samples": metrics["ref_distance_samples"],
                    "rf_rmse_lod22": status.get("rf_rmse_lod22", ""),
                    "shell_bucket": shell_bucket(has_lod22, valid, roof_planes, False),
                }
            )
            rows.append(row)
    mark_ref_distance_tails(rows)
    return rows


def base_metric_row(src: Source, bid: str, lenses: dict[str, dict[str, str]]) -> dict[str, Any]:
    lens = lenses.get(bid, {})
    return {
        "building_id": bid,
        "source_group": src.source_group,
        "source_run": src.source_run,
        "display_label": src.display_label,
        "source_role": src.status_role,
        "seed": src.seed or "",
        "replicate": src.replicate or "",
        "pair_raw": src.pair_raw or "",
        "source_badge": src.source_badge,
        "readout": src.readout,
        "z_shift_to_reference_m": fmt(src.z_shift_to_reference_m),
        "complexity_lens": lens.get("complexity_lens", "unknown"),
        "size_lens": lens.get("size_lens", "unknown"),
        "texture_lens": lens.get("texture_lens", "unknown"),
        "observation_lens": lens.get("observation_lens", "unknown"),
        "label_lens": lens.get("label_lens", "none"),
    }


def shell_bucket(has_lod22: bool, valid: bool, roof_planes: int, collapse: bool) -> str:
    if not has_lod22:
        return "미조립"
    if roof_planes == 0:
        return "지붕면0 성공"
    if (not valid) or collapse:
        return "무효·붕괴"
    return "조립"


def mark_ref_distance_tails(rows: list[dict[str, Any]]) -> None:
    values = [
        float(r["ref_rms_m"])
        for r in rows
        if r["source_role"] != "reference" and r.get("has_lod22") == "true" and num(r.get("ref_rms_m")) is not None
    ]
    if len(values) < 4:
        upper = math.inf
    else:
        q1, q3 = np.percentile(values, [25, 75])
        upper = float(q3 + 1.5 * (q3 - q1))
    for row in rows:
        v = num(row.get("ref_rms_m"))
        collapse = bool(v is not None and v > upper)
        row["ref_rms_tail"] = fmt(collapse)
        row["ref_rms_tail_fence_m"] = fmt(upper)
        if row["source_role"] != "reference":
            row["shell_bucket"] = shell_bucket(
                tf(row.get("has_lod22")),
                tf(row.get("val3dity_valid")),
                int(row.get("roof_planes") or 0),
                collapse,
            )


def build_lenses() -> dict[str, dict[str, str]]:
    lenses: dict[str, dict[str, str]] = {bid: {} for bid in C001_IDS}
    if Path("docs/regression_input_snapshot.csv").exists():
        for row in read_csv(Path("docs/regression_input_snapshot.csv")):
            bid = row.get("building_id")
            if bid not in lenses or lenses[bid].get("complexity_lens"):
                continue
            lenses[bid].update(
                {
                    "complexity_lens": row.get("stratum_complexity_ref_roof_planes") or "unknown",
                    "size_lens": row.get("stratum_size_area") or "unknown",
                    "observation_lens": row.get("stratum_observation_recon_score") or "unknown",
                    "label_lens": row.get("manual_label") or "none",
                }
            )
    manual: dict[str, dict[str, str]] = {}
    if Path("docs/research/methodology/tables/manual_review_judgments.csv").exists():
        manual = {row["building_id"]: row for row in read_csv(Path("docs/research/methodology/tables/manual_review_judgments.csv")) if row.get("building_id") in lenses}
    for bid, lens in lenses.items():
        row = manual.get(bid)
        label = lens.get("label_lens") or (row.get("label") if row else "none") or "none"
        lens["label_lens"] = label
        if row:
            lowtex = num(row.get("roof_lowtex_v5"))
            if "텍스처" in label or "저조도" in label:
                texture = label
            elif lowtex is None:
                texture = "manual_no_lowtex"
            elif lowtex >= 0.50:
                texture = "lowtex_high"
            elif lowtex >= 0.30:
                texture = "lowtex_mid"
            else:
                texture = "lowtex_low"
        else:
            texture = "not_reviewed"
        lens.setdefault("complexity_lens", "unknown")
        lens.setdefault("size_lens", "unknown")
        lens.setdefault("observation_lens", "unknown")
        lens["texture_lens"] = texture
    return lenses


def build_source_summary(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for source_run, group in group_by(rows, "source_run").items():
        nonref = [r for r in group if r["source_role"] != "reference"]
        use = group if not nonref else nonref
        ref_rms = [float(r["ref_rms_m"]) for r in use if num(r.get("ref_rms_m")) is not None]
        comp = [float(r["completeness"]) for r in use if num(r.get("completeness")) is not None]
        corr = [float(r["correctness"]) for r in use if num(r.get("correctness")) is not None]
        buckets = Counter(r["shell_bucket"] for r in use)
        out.append(
            {
                "source_run": source_run,
                "source_group": use[0]["source_group"],
                "label": use[0]["display_label"],
                "n": len(use),
                "has_lod22": sum(tf(r.get("has_lod22")) for r in use),
                "val3dity_valid": sum(tf(r.get("val3dity_valid")) for r in use),
                "미조립": buckets["미조립"],
                "지붕면0 성공": buckets["지붕면0 성공"],
                "무효·붕괴": buckets["무효·붕괴"],
                "조립": buckets["조립"],
                "mean_completeness": fmt(np.mean(comp) if comp else None),
                "mean_correctness": fmt(np.mean(corr) if corr else None),
                "median_ref_rms_m": fmt(np.median(ref_rms) if ref_rms else None),
                "mean_ref_rms_m": fmt(np.mean(ref_rms) if ref_rms else None),
            }
        )
    return sorted(out, key=lambda r: source_order(r["source_run"]))


def source_order(source_run: str) -> tuple[int, str]:
    order = {
        "raw_sparse": 0,
        "raw_dense": 1,
        "raw_acmp": 2,
        "gs_sparse_r1": 3,
        "gs_sparse_r2": 4,
        "gs_dense_r1": 5,
        "gs_dense_r2": 6,
        "gs_acmp_r1": 7,
        "gs_acmp_r2": 8,
        "lidar": 9,
        "reference": 10,
    }
    return order.get(source_run, 99), source_run


def group_by(rows: list[dict[str, Any]], key: str) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        out[str(row.get(key, ""))].append(row)
    return out


def build_correction_gain(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    by = {(r["source_run"], r["building_id"]): r for r in rows}
    detail: list[dict[str, Any]] = []
    for arm in ("sparse", "dense", "acmp"):
        raw_key = f"raw_{arm}"
        for rep in ("r1", "r2"):
            gs_key = f"gs_{arm}_{rep}"
            for bid in C001_IDS:
                raw = by[(raw_key, bid)]
                gs = by[(gs_key, bid)]
                detail.append(
                    {
                        "arm": arm,
                        "replicate": rep,
                        "building_id": bid,
                        "raw_source": raw_key,
                        "gs_source": gs_key,
                        "raw_has_lod22": raw["has_lod22"],
                        "gs_has_lod22": gs["has_lod22"],
                        "delta_has_lod22": int(tf(gs["has_lod22"])) - int(tf(raw["has_lod22"])),
                        "raw_completeness": raw["completeness"],
                        "gs_completeness": gs["completeness"],
                        "delta_completeness": delta(gs.get("completeness"), raw.get("completeness")),
                        "raw_correctness": raw["correctness"],
                        "gs_correctness": gs["correctness"],
                        "delta_correctness": delta(gs.get("correctness"), raw.get("correctness")),
                        "raw_ref_rms_m": raw["ref_rms_m"],
                        "gs_ref_rms_m": gs["ref_rms_m"],
                        "ref_rms_gain_m": gain_lower_better(raw.get("ref_rms_m"), gs.get("ref_rms_m")),
                    }
                )
    summary: list[dict[str, Any]] = []
    for key, group in group_by2(detail, "arm", "replicate").items():
        dc = [float(r["delta_completeness"]) for r in group if num(r["delta_completeness"]) is not None]
        dcor = [float(r["delta_correctness"]) for r in group if num(r["delta_correctness"]) is not None]
        gain = [float(r["ref_rms_gain_m"]) for r in group if num(r["ref_rms_gain_m"]) is not None]
        summary.append(
            {
                "arm": key[0],
                "replicate": key[1],
                "n": len(group),
                "sum_delta_has_lod22": sum(int(r["delta_has_lod22"]) for r in group),
                "mean_delta_completeness": fmt(np.mean(dc) if dc else None),
                "mean_delta_correctness": fmt(np.mean(dcor) if dcor else None),
                "median_ref_rms_gain_m": fmt(np.median(gain) if gain else None),
                "mean_ref_rms_gain_m": fmt(np.mean(gain) if gain else None),
            }
        )
    return detail, sorted(summary, key=lambda r: (r["arm"], r["replicate"]))


def group_by2(rows: list[dict[str, Any]], key1: str, key2: str) -> dict[tuple[str, str], list[dict[str, Any]]]:
    out: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        out[(str(row.get(key1, "")), str(row.get(key2, "")))].append(row)
    return out


def delta(a: Any, b: Any) -> str:
    av = num(a)
    bv = num(b)
    if av is None or bv is None:
        return ""
    return fmt(av - bv)


def gain_lower_better(raw: Any, gs: Any) -> str:
    rv = num(raw)
    gv = num(gs)
    if rv is None or gv is None:
        return ""
    return fmt(rv - gv)


def build_strata_summary(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for lens_name in ["complexity_lens", "size_lens", "texture_lens", "observation_lens", "label_lens"]:
        groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
        for row in rows:
            if row["source_role"] == "reference":
                continue
            groups[(row["source_run"], row.get(lens_name, "unknown"))].append(row)
        for (source_run, lens_value), group in groups.items():
            comp = [float(r["completeness"]) for r in group if num(r.get("completeness")) is not None]
            corr = [float(r["correctness"]) for r in group if num(r.get("correctness")) is not None]
            rr = [float(r["ref_rms_m"]) for r in group if num(r.get("ref_rms_m")) is not None]
            out.append(
                {
                    "lens": lens_name.replace("_lens", ""),
                    "lens_value": lens_value,
                    "source_run": source_run,
                    "n": len(group),
                    "has_lod22": sum(tf(r.get("has_lod22")) for r in group),
                    "mean_completeness": fmt(np.mean(comp) if comp else None),
                    "mean_correctness": fmt(np.mean(corr) if corr else None),
                    "median_ref_rms_m": fmt(np.median(rr) if rr else None),
                }
            )
    return sorted(out, key=lambda r: (r["lens"], r["lens_value"], source_order(r["source_run"])))


class PointCloudCache:
    def __init__(self, footprints: dict[str, Polygon]):
        self.footprints = footprints
        self.cache: dict[Path, tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]] = {}

    def read_roof_points(self, source: Source, bid: str) -> np.ndarray:
        path = self.pointcloud_path(source, bid)
        if path is None or not path.exists():
            return np.empty((0, 3), dtype=float)
        x, y, z, cls = self._read(path)
        poly = self.footprints[bid]
        minx, miny, maxx, maxy = poly.bounds
        bbox = (x >= minx) & (x <= maxx) & (y >= miny) & (y <= maxy)
        if not np.any(bbox):
            return np.empty((0, 3), dtype=float)
        idx = np.nonzero(bbox)[0]
        in_poly = contains_xy(poly, x[idx], y[idx])
        idx = idx[in_poly]
        if len(idx) == 0:
            return np.empty((0, 3), dtype=float)
        roof = cls[idx] == 6
        idx = idx[roof]
        if len(idx) == 0:
            return np.empty((0, 3), dtype=float)
        return np.column_stack([x[idx], y[idx], z[idx]])

    def pointcloud_path(self, source: Source, bid: str) -> Path | None:
        if source.pointcloud_template:
            return Path(source.pointcloud_template.format(bid=bid))
        return source.pointcloud_path

    def _read(self, path: Path) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        if path not in self.cache:
            las = laspy.read(str(path))
            self.cache[path] = (
                np.asarray(las.x, dtype=np.float64),
                np.asarray(las.y, dtype=np.float64),
                np.asarray(las.z, dtype=np.float64),
                np.asarray(las.classification, dtype=np.uint8),
            )
        return self.cache[path]


def draw_cloud(ax: Any, points: np.ndarray, footprint: Polygon, title: str) -> None:
    ax.set_title(title, fontsize=6.5)
    minx, miny, maxx, maxy = footprint.bounds
    if len(points) == 0:
        ax.text(0.5, 0.5, "no points", ha="center", va="center", transform=ax.transAxes, fontsize=7)
    else:
        pts = points
        if len(pts) > MAX_PLOT_POINTS:
            idx = RNG.choice(len(pts), MAX_PLOT_POINTS, replace=False)
            pts = pts[idx]
        c = pts[:, 2] - np.nanmedian(pts[:, 2])
        ax.scatter(pts[:, 0], pts[:, 1], c=c, cmap="viridis", s=0.7, linewidths=0)
    xpad = max((maxx - minx) * 0.12, 1.0)
    ypad = max((maxy - miny) * 0.12, 1.0)
    ax.set_xlim(minx - xpad, maxx + xpad)
    ax.set_ylim(miny - ypad, maxy + ypad)
    ax.set_aspect("equal", adjustable="box")
    ax.set_xticks([])
    ax.set_yticks([])


def draw_model(ax: Any, surfaces: list[RoofSurface], footprint: Polygon, title: str, note: str = "") -> None:
    ax.set_title(title, fontsize=6.5)
    polys = surface_polys_3d(surfaces)
    if not polys:
        ax.text2D(0.5, 0.5, "no model", ha="center", va="center", transform=ax.transAxes, fontsize=7)
        ax.set_axis_off()
        return
    allpts = np.vstack(polys)
    zmin = float(np.nanmin(allpts[:, 2]))
    shifted = []
    for poly in polys:
        p = poly.copy()
        p[:, 2] -= zmin
        shifted.append(p)
    colors = [plt.cm.tab20(i % 20) for i in range(len(shifted))]
    ax.add_collection3d(Poly3DCollection(shifted, facecolor=colors, edgecolor="k", linewidths=0.20, alpha=0.92))
    minx, miny, maxx, maxy = footprint.bounds
    xpad = max((maxx - minx) * 0.15, 1.0)
    ypad = max((maxy - miny) * 0.15, 1.0)
    ax.set_xlim(minx - xpad, maxx + xpad)
    ax.set_ylim(miny - ypad, maxy + ypad)
    ax.set_zlim(0, max(float(np.nanmax(allpts[:, 2]) - zmin) * 1.2, 1.0))
    ax.view_init(elev=32, azim=-58)
    ax.set_xticks([])
    ax.set_yticks([])
    ax.set_zticks([])
    ax.set_box_aspect((1, 1, 0.45))
    if note:
        ax.text2D(0.02, 0.92, note, transform=ax.transAxes, fontsize=5.8)


def surface_polys_3d(surfaces: list[RoofSurface]) -> list[np.ndarray]:
    out: list[np.ndarray] = []
    for surf in surfaces:
        for poly in flatten_polygons(surf.polygon):
            coords = np.asarray(poly.exterior.coords, dtype=float)
            z = surf.z_at(coords[:, 0], coords[:, 1])
            out.append(np.column_stack([coords[:, 0], coords[:, 1], z]))
    return out


def make_building_figures(
    srcs: list[Source],
    refs: dict[str, list[RoofSurface]],
    pred_by_source: dict[str, dict[str, list[RoofSurface]]],
    metrics: list[dict[str, Any]],
    footprints: dict[str, Polygon],
) -> list[Path]:
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    metric_by = {(r["source_run"], r["building_id"]): r for r in metrics}
    display_sources = [s for s in srcs if s.source_run != "reference"]
    ref_source = next(s for s in srcs if s.source_run == "reference")
    cache = PointCloudCache(footprints)
    written: list[Path] = []
    for bid in C001_IDS:
        ncols = len(display_sources) + 1
        fig = plt.figure(figsize=(2.05 * ncols, 4.9))
        for col, src in enumerate(display_sources, start=1):
            row = metric_by[(src.source_run, bid)]
            pts = cache.read_roof_points(src, bid)
            title = f"{figure_source_label(src)}\nC {row['completeness'] or '-'} R {row['correctness'] or '-'}"
            draw_cloud(fig.add_subplot(2, ncols, col), pts, footprints[bid], title)
            note = f"roof {row['roof_planes']}/{row['ref_roof_planes']}\nRMS {row['ref_rms_m'] or '-'}"
            draw_model(
                fig.add_subplot(2, ncols, ncols + col, projection="3d"),
                pred_by_source[src.source_run][bid],
                footprints[bid],
                SHELL_FIG_LABEL.get(row["shell_bucket"], row["shell_bucket"]),
                note,
            )
        ref_col = ncols
        draw_model(fig.add_subplot(2, ncols, ref_col, projection="3d"), refs[bid], footprints[bid], figure_source_label(ref_source), f"roof {len(refs[bid])}")
        draw_model(fig.add_subplot(2, ncols, ncols + ref_col, projection="3d"), refs[bid], footprints[bid], "ground truth", f"roof {len(refs[bid])}")
        fig.suptitle(f"C001 8-way: {bid}", fontsize=11)
        fig.tight_layout(rect=(0, 0, 1, 0.95))
        out = FIG_DIR / f"8way_{short_id(bid)}.png"
        fig.savefig(out, dpi=150)
        plt.close(fig)
        written.append(out)
    return written


def figure_source_label(src: Source) -> str:
    labels = {
        "raw_sparse": "raw sparse",
        "raw_dense": "raw dense",
        "raw_acmp": "raw acmp",
        "lidar": "LiDAR",
        "reference": "reference",
    }
    return labels.get(src.source_run, src.source_run.replace("gs_", "GS "))


def plot_summary_figures(source_summary: list[dict[str, Any]], metrics: list[dict[str, Any]]) -> list[Path]:
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    labels = [r["source_run"] for r in source_summary if r["source_run"] != "reference"]
    x = np.arange(len(labels))
    comp = [num(next(r for r in source_summary if r["source_run"] == lab)["mean_completeness"]) or 0 for lab in labels]
    corr = [num(next(r for r in source_summary if r["source_run"] == lab)["mean_correctness"]) or 0 for lab in labels]
    fig, ax = plt.subplots(figsize=(12, 4.5))
    ax.bar(x - 0.18, comp, width=0.36, label="completeness")
    ax.bar(x + 0.18, corr, width=0.36, label="correctness")
    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=45, ha="right")
    ax.set_ylim(0, 1.05)
    ax.set_ylabel("rate")
    ax.set_title("Reference roof-surface matching")
    ax.grid(True, axis="y", alpha=0.25)
    ax.legend()
    fig.tight_layout()
    out = FIG_DIR / "summary_completeness_correctness.png"
    fig.savefig(out, dpi=170)
    plt.close(fig)
    paths.append(out)

    values = []
    labels2 = []
    for lab in labels:
        vals = [float(r["ref_rms_m"]) for r in metrics if r["source_run"] == lab and num(r.get("ref_rms_m")) is not None]
        if vals:
            values.append(vals)
            labels2.append(lab)
    fig, ax = plt.subplots(figsize=(12, 4.5))
    ax.boxplot(values, labels=labels2, showfliers=True)
    ax.axhline(1.0, color="#2f855a", linestyle="--", linewidth=1.0, label="1 m")
    ax.axhline(31.0, color="#c53030", linestyle=":", linewidth=1.0, label="31 m")
    ax.set_yscale("symlog", linthresh=1)
    ax.set_ylabel("reference RMS (m)")
    ax.set_title("Reference-distance distribution")
    ax.tick_params(axis="x", labelrotation=45)
    ax.grid(True, axis="y", alpha=0.25)
    ax.legend()
    fig.tight_layout()
    out = FIG_DIR / "summary_ref_distance.png"
    fig.savefig(out, dpi=170)
    plt.close(fig)
    paths.append(out)
    return paths


def md_table(rows: list[dict[str, Any]], columns: list[str], max_rows: int | None = None) -> list[str]:
    use = rows[:max_rows] if max_rows is not None else rows
    out = ["| " + " | ".join(columns) + " |", "|" + "|".join("---" for _ in columns) + "|"]
    for row in use:
        out.append("| " + " | ".join(str(row.get(c, "")) for c in columns) + " |")
    if max_rows is not None and len(rows) > max_rows:
        out.append(f"| ... | {len(rows) - max_rows} rows omitted | " + " | ".join("" for _ in columns[2:]) + " |")
    return out


def write_report(
    srcs: list[Source],
    metrics: list[dict[str, Any]],
    source_summary: list[dict[str, Any]],
    gain_summary: list[dict[str, Any]],
    strata_summary: list[dict[str, Any]],
    figure_paths: list[Path],
    summary_figs: list[Path],
    inventory: list[dict[str, Any]],
) -> None:
    branch = capture(["git", "branch", "--show-current"])
    head = capture(["git", "rev-parse", "HEAD"])
    nonref_summary = [r for r in source_summary if r["source_run"] != "reference"]
    obs_bits = [
        f"{r['source_run']}: C {r['mean_completeness'] or '-'} · R {r['mean_correctness'] or '-'} · RMS중앙 {r['median_ref_rms_m'] or '-'}m"
        for r in nonref_summary
        if r["source_run"].startswith("gs_")
    ]
    lines = [
        "# E5 C001 8-way 참조 매칭",
        "",
        "> 재확인: 신규 학습 0 · 레시피 변경 0 · Roofer 변경 0 · 판정 문구 0. 기존 C001 6런과 기준선 조립 산출만 읽었다. CRS는 EPSG:25832.",
        "",
        "## 시작 전 확인",
        "",
        f"- 브랜치·HEAD: `{branch}` · `{head}`.",
        f"- 기존 게이트 보고: `docs/experiments/pilots/e5_pilot/reports/W_E5_pilot_gate.md`, `docs/experiments/pilots/e5_pilot/reports/W_E5_pilot_gate_검수·판정회부_20260707.md`.",
        f"- GS 점군화·지문: `{TRAIN_RUN_DIR}/`.",
        f"- GS 조립 출력: `{GATE_RUN_DIR}/`.",
        "- 새 학습·새 파라미터·새 Roofer 조립은 하지 않았다.",
        "- 기준문서 파일 머리표기는 v1.25(2026-07-06)다. 발주문은 v1.27을 언급하지만, repo의 잠금본 사전등록서와 현재 기준문서 부록 A/D를 우선 인용했다.",
        "",
        "## 입력 재고",
        "",
        *md_table(inventory, ["source_run", "source_group", "status", "status_path", "cityjson_path", "pointcloud_path", "z_shift_to_reference_m", "missing_count"], max_rows=None),
        "",
        "## 참조 매칭 방법",
        "",
        "- 참조 지붕 구조는 LoD2 CityGML의 RoofSurface 수와 형상이다. W_D6 형상 교정본의 원칙을 준용했다.",
        f"- completeness/correctness 매칭: 수평 중첩 {MATCH_OVERLAP_MIN_M2:.2f} m2 이상, IoU {MATCH_IOU_MIN:.2f} 이상, 겹친 영역 높이 차이 중앙값 {MATCH_Z_P50_MAX_M:.1f} m 이하인 후보를 점수순으로 1:1 매칭했다.",
        "- 참조거리 RMS/Hausdorff: 매칭 성패와 별도로 조립 지붕면 전체를 0.5 m 간격으로 샘플링하고, 같은 수평 위치의 참조 지붕면까지 높이 차이를 계산했다. 자기 점 RMSE가 아니다.",
        "- 높이 프레임: raw-sparse·raw-acmp·GS 조립 CityJSON은 참조거리 계산에서 -45.7 m를 적용했다. raw-dense(MVS)와 LiDAR는 0 m다. 원본 산출물은 수정하지 않았다.",
        "- 껍데기 3분할 규칙: CityJSON에 지붕면이 있으면 무효 모델이어도 면수는 센다. `미조립` / `지붕면0 성공` / `무효·붕괴` / `조립`은 별도 열로 낸다.",
        "- `무효·붕괴`는 val3dity 무효 또는 참조거리 RMS의 Tukey 꼬리다. 이 규칙으로 4908178 같은 그림상 붕괴와 면수 계산을 동시에 보존한다.",
        "",
        "## 8-way 정량 요약",
        "",
        *md_table(
            source_summary,
            [
                "source_run",
                "n",
                "has_lod22",
                "val3dity_valid",
                "미조립",
                "지붕면0 성공",
                "무효·붕괴",
                "조립",
                "mean_completeness",
                "mean_correctness",
                "median_ref_rms_m",
            ],
        ),
        "",
        "## Correction gain",
        "",
        "- 폭 정의: GS-x minus raw-x for completeness/correctness, raw RMS minus GS RMS for 참조거리(양수면 참조 쪽으로 가까워짐).",
        "",
        *md_table(
            gain_summary,
            [
                "arm",
                "replicate",
                "n",
                "sum_delta_has_lod22",
                "mean_delta_completeness",
                "mean_delta_correctness",
                "median_ref_rms_gain_m",
            ],
        ),
        "",
        "## 층화 렌즈",
        "",
        "- 복잡도·크기·관측 렌즈는 `docs/regression_input_snapshot.csv`의 C001 행을 재사용했다.",
        "- 텍스처·라벨 렌즈는 `docs/research/methodology/tables/manual_review_judgments.csv`가 있는 동만 세부 라벨을 쓰고, 나머지는 `not_reviewed` 또는 `none`으로 남겼다.",
        f"- 전체 층화 요약표: `{STRATA_SUMMARY_CSV}`.",
        "",
        "## 그림",
        "",
        "- 건물당 그림은 18동 전수다. 8개 소스 그룹 중 GS 세 그룹은 r1/r2를 내부 칸으로 나눠 표시하므로 그림은 11칸으로 보인다.",
        f"- completeness/correctness 요약: `{summary_figs[0]}`.",
        f"- 참조거리 요약: `{summary_figs[1]}`.",
        f"- 건물별 그림 디렉터리: `{FIG_DIR}/`.",
        "",
        *[f"- `{p}`" for p in figure_paths],
        "",
        "## 산출 표",
        "",
        f"- 원자료 행 단위: `{METRICS_CSV}`.",
        f"- 소스 요약: `{SOURCE_SUMMARY_CSV}`.",
        f"- correction gain 세부: `{CORRECTION_GAIN_CSV}`.",
        f"- correction gain 요약: `{CORRECTION_GAIN_SUMMARY_CSV}`.",
        f"- 재고표: `{INVENTORY_CSV}`.",
        f"- 실행 지문: `{RUN_DIR / 'versions.txt'}`.",
        "",
        "## 관찰",
        "",
        "- " + " / ".join(obs_bits) + ". 위 문장은 수치 관찰이며 게이트 판정이 아니다.",
    ]
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_versions(inventory: list[dict[str, Any]], figure_count: int) -> None:
    RUN_DIR.mkdir(parents=True, exist_ok=True)
    lines = [
        f"run_id: {RUN_ID}",
        f"created_utc: {datetime.now(timezone.utc).isoformat()}",
        "task: E5 C001 8-way reference-matched comparison",
        "mode: read-only over existing C001 outputs; no retraining; no recipe change; no Roofer rerun; no verdict",
        "crs: EPSG:25832",
        f"git_branch: {capture(['git', 'branch', '--show-current'])}",
        f"git_head: {capture(['git', 'rev-parse', 'HEAD'])}",
        "docker_image: jointbuildgs-p0-tools:t0",
        f"script: phases/p2-gsjso/scripts/{Path(__file__).name}",
        f"readout: {READOUT_STRING}",
        f"input_gate_run: {GATE_RUN_DIR}",
        f"input_train_run: {TRAIN_RUN_DIR}",
        "reference_lod2: phases/p0-audit/data/raw/lod2/*.gml",
        "reference_shape_correction: docs/W_D6_shape_audit.md; 4906969=stepped flat roof; curved roofs=0 in D6 set",
        f"match_overlap_min_m2: {MATCH_OVERLAP_MIN_M2}",
        f"match_iou_min: {MATCH_IOU_MIN}",
        f"match_z_p50_max_m: {MATCH_Z_P50_MAX_M}",
        f"sample_spacing_m: {SAMPLE_SPACING_M}",
        f"ellip_to_reference_shift_m: {ELLIP_TO_REF_SHIFT_M}",
        f"inventory_sources: {len(inventory)}",
        f"building_figures: {figure_count}",
    ]
    (RUN_DIR / "versions.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    manifest = {
        "run_id": RUN_ID,
        "outputs": [
            rel(REPORT_PATH),
            rel(METRICS_CSV),
            rel(SOURCE_SUMMARY_CSV),
            rel(CORRECTION_GAIN_CSV),
            rel(CORRECTION_GAIN_SUMMARY_CSV),
            rel(STRATA_SUMMARY_CSV),
            rel(INVENTORY_CSV),
            rel(FIG_DIR),
        ],
    }
    (RUN_DIR / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def copy_small_outputs_to_run_dir() -> None:
    snapshot_dir = RUN_DIR / "snapshots"
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    for path in [REPORT_PATH, METRICS_CSV, SOURCE_SUMMARY_CSV, CORRECTION_GAIN_CSV, CORRECTION_GAIN_SUMMARY_CSV, STRATA_SUMMARY_CSV, INVENTORY_CSV]:
        if path.exists():
            shutil.copy2(path, snapshot_dir / path.name)


def load_reference_and_predictions(srcs: list[Source]) -> tuple[dict[str, list[RoofSurface]], dict[str, dict[str, list[RoofSurface]]]]:
    refs = parse_lod2_roofs(LOD2_DIR, set(C001_IDS))
    pred: dict[str, dict[str, list[RoofSurface]]] = {}
    for src in srcs:
        if src.status_role == "reference":
            pred[src.source_run] = refs
        else:
            parsed = parse_cityjson_roofs(src.cityjson_path, set(C001_IDS))
            pred[src.source_run] = {
                bid: shift_surface_z(surfaces, src.z_shift_to_reference_m) for bid, surfaces in parsed.items()
            }
    return refs, pred


def main() -> None:
    os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib")
    configure_korean_font()
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    srcs = sources()
    inventory = inventory_rows(srcs)
    missing = [row for row in inventory if row["status"] == "missing"]
    if missing:
        write_csv(INVENTORY_CSV, inventory)
        raise RuntimeError(f"missing existing C001 source products: {missing[:3]}")

    refs, pred_by_source = load_reference_and_predictions(srcs)
    status_maps = load_status_maps(srcs)
    lenses = build_lenses()
    metrics = build_metric_rows(srcs, refs, pred_by_source, status_maps, lenses)
    source_summary = build_source_summary(metrics)
    gain_detail, gain_summary = build_correction_gain(metrics)
    strata_summary = build_strata_summary(metrics)

    write_csv(INVENTORY_CSV, inventory)
    write_csv(METRICS_CSV, metrics)
    write_csv(SOURCE_SUMMARY_CSV, source_summary)
    write_csv(CORRECTION_GAIN_CSV, gain_detail)
    write_csv(CORRECTION_GAIN_SUMMARY_CSV, gain_summary)
    write_csv(STRATA_SUMMARY_CSV, strata_summary)

    footprints = base.load_footprints(FOOTPRINTS_GPKG, set(C001_IDS))
    figure_paths = make_building_figures(srcs, refs, pred_by_source, metrics, footprints)
    summary_figs = plot_summary_figures(source_summary, metrics)
    write_versions(inventory, len(figure_paths))
    write_report(srcs, metrics, source_summary, gain_summary, strata_summary, figure_paths, summary_figs, inventory)
    copy_small_outputs_to_run_dir()
    print(json.dumps({"report": rel(REPORT_PATH), "figures": len(figure_paths), "metrics_rows": len(metrics)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
