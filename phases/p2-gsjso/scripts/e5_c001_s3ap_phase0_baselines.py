#!/usr/bin/env python3
"""S3-A-prime Phase-0 P0 plane-fill and existing-MVS support measurements.

Learning-zero.  The default input is the cached fixed-COLMAP 2px DLT survivors.
An operating-point manifest can replace those points without changing the
plane-fit/fill/scoring path.  LoD2 is loaded only after P0 construction for
score and overlay.  This stage prepares a Roofer input roofprint exclusively
from the occupied cells of the generated P0 point evidence.  The supplied
footprint is never passed to Roofer, although the P0 points indirectly depend
on it because it is the explicitly permitted plane-fill mask.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
import math
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence

os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib")
os.environ.setdefault("XDG_CACHE_HOME", "/tmp")

import laspy
import matplotlib
import numpy as np
from lxml import etree
from pyproj import CRS
from shapely import contains_xy, make_valid
from shapely.geometry import GeometryCollection, MultiPolygon, Point, Polygon, box, mapping, shape
from shapely.ops import unary_union

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from mpl_toolkits.mplot3d.art3d import Poly3DCollection  # noqa: E402


REPO = Path(__file__).resolve().parents[3]
CONFIG = REPO / "phases/p2-gsjso/configs/e5_c001_s3ap_phase0_baselines.json"
RUN_DIR = REPO / "phases/p2-gsjso/runs/20260715_e5_c001_s3ap_phase0_baselines"
OUT_P0 = REPO / "docs/planefit_baseline.csv"
OUT_MVS = REPO / "docs/mvs_hole_check.csv"
FIG_DIR = REPO / "docs/figs/e5_c001_s3ap_phase0"
P0_FIG = FIG_DIR / "p0_planefit_baseline.png"
MVS_FIG = FIG_DIR / "mvs_hole_check.png"
REPORT = RUN_DIR / "report_fragment.md"
MANIFEST = RUN_DIR / "manifest.json"
PROGRESS = RUN_DIR / "progress.json"
RUN_LOG = RUN_DIR / "run.log"
P0_POINTS = RUN_DIR / "p0_fill_points.npz"
P0_ROOFER_LAS = RUN_DIR / "p0_fill_classified.las"
DERIVED_ROOFPRINTS = RUN_DIR / "point_evidence_derived_roofprints.geojson"
ROOFER_DIR = RUN_DIR / "roofer"
CITYJSON_DIR = RUN_DIR / "cityjson"
CITYJSON = CITYJSON_DIR / "p0_planefit_roofer.city.json"
VAL_DIR = RUN_DIR / "val3dity"
VAL_REPORT = VAL_DIR / "p0_planefit_val3dity_report.json"
VAL_LOG = VAL_DIR / "p0_planefit_val3dity.log"
ROOFER_STATUS = RUN_DIR / "roofer_building_status.csv"
ROOFER_FIG = FIG_DIR / "p0_roofer_readout.png"
FOOTPRINTS = REPO / "results/tum_transfer/analysis/footprints_aoi.geojson"
LOD2_DIR = REPO / "phases/p0-audit/data/raw/lod2"
TRAIN_MANIFEST = REPO / "results/tum_transfer/e5_pilot/C001/C001_train_prep_manifest.json"
PROJECTION_DATUM = REPO / "configs/projection_datum.json"
GROUND_SOURCE = REPO / "docs/e5_c001_s3ap_fm_retri_rescore.csv"


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def rel(path: Path | str) -> str:
    path = Path(path)
    try:
        return str(path.resolve().relative_to(REPO.resolve()))
    except ValueError:
        return str(path.resolve())


def sha256_file(path: Path, block_size: int = 1 << 20) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(block_size), b""):
            digest.update(block)
    return digest.hexdigest()


def git_value(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=REPO, text=True).strip()


def log(message: str) -> None:
    RUN_DIR.mkdir(parents=True, exist_ok=True)
    line = f"{now()} {message}"
    with RUN_LOG.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    print(line, flush=True)


def atomic_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def fmt(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (bool, np.bool_)):
        return "true" if bool(value) else "false"
    if isinstance(value, (float, np.floating)):
        return "" if not math.isfinite(float(value)) else f"{float(value):.6f}"
    return str(value)


HIGH_PRECISION_CSV_FIELDS = {
    "plane_ax_local", "plane_by_local", "plane_c_ransac_local",
    "plane_c_anchor_local", "plane_c_local",
    "height_anchor_z_median_local_m", "anchor_predicted_z_median_local_m",
    "anchor_residual_m",
}


def csv_fmt(key: str, value: Any) -> str:
    if key in HIGH_PRECISION_CSV_FIELDS and isinstance(value, (float, np.floating)):
        return "" if not math.isfinite(float(value)) else f"{float(value):.12f}"
    return fmt(value)


def atomic_csv(path: Path, rows: Sequence[dict[str, Any]], fields: Sequence[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    with tmp.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(fields), extrasaction="ignore", lineterminator="\n")
        writer.writeheader()
        writer.writerows({key: csv_fmt(key, row.get(key)) for key in fields} for row in rows)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, path)


def write_progress(stage: str, completed: Iterable[str], status: str) -> None:
    atomic_text(PROGRESS, json.dumps({
        "schema": "jointbuildgs.s3ap.phase0.baselines.progress.v1",
        "updated_utc": now(), "stage": stage, "completed_buildings": list(completed), "status": status,
        "learning_runs_started": 0, "new_mast3r_inference_runs": 0,
    }, ensure_ascii=False, indent=2) + "\n")


def flatten_polygons(geom: Any) -> list[Polygon]:
    if geom is None or geom.is_empty:
        return []
    if isinstance(geom, Polygon):
        return [geom]
    if isinstance(geom, MultiPolygon):
        return list(geom.geoms)
    if isinstance(geom, GeometryCollection):
        out: list[Polygon] = []
        for part in geom.geoms:
            out.extend(flatten_polygons(part))
        return out
    return []


def load_footprints(targets: Sequence[str]) -> dict[str, Polygon | MultiPolygon]:
    payload = json.loads(FOOTPRINTS.read_text(encoding="utf-8"))
    crs = str(payload.get("crs", {}).get("properties", {}).get("name", ""))
    if "25832" not in crs:
        raise RuntimeError(f"footprint CRS mismatch: {crs}")
    pieces: dict[str, list[Any]] = {short: [] for short in targets}
    for feature in payload["features"]:
        bid = str((feature.get("properties") or {}).get("building_id", ""))
        short = bid.removeprefix("DEBY_LOD2_")
        if short in pieces:
            pieces[short].append(make_valid(shape(feature["geometry"])))
    out = {short: make_valid(unary_union(parts)) for short, parts in pieces.items() if parts}
    missing = sorted(set(targets) - set(out))
    if missing:
        raise RuntimeError(f"missing footprints: {missing}")
    return out


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def gml_id(elem: etree._Element) -> str:
    return next((str(value) for key, value in elem.attrib.items() if local_name(key) == "id"), "")


def first_poslist(elem: etree._Element) -> np.ndarray | None:
    for child in elem.iter():
        if local_name(child.tag) == "posList" and child.text:
            values = np.asarray([float(value) for value in child.text.split()], dtype=np.float64)
            return values.reshape(-1, 3)
    return None


def load_lod2(targets: Sequence[str]) -> dict[str, list[dict[str, Any]]]:
    wanted = {f"DEBY_LOD2_{short}": short for short in targets}
    output: dict[str, list[dict[str, Any]]] = {short: [] for short in targets}
    for path in sorted(LOD2_DIR.glob("*.gml")):
        for _event, elem in etree.iterparse(str(path), events=("end",), recover=True):
            if local_name(elem.tag) != "Building":
                continue
            bid = gml_id(elem)
            if bid in wanted:
                short = wanted[bid]
                index = 0
                for surface in elem.iter():
                    if local_name(surface.tag) != "RoofSurface":
                        continue
                    for poly in surface.iter():
                        if local_name(poly.tag) != "Polygon":
                            continue
                        ring = first_poslist(poly)
                        if ring is None or len(ring) < 3:
                            continue
                        if not np.allclose(ring[0], ring[-1]):
                            ring = np.vstack([ring, ring[0]])
                        polygon = make_valid(Polygon(ring[:, :2]))
                        if polygon.is_empty or polygon.area <= 0.01:
                            continue
                        points = ring[:-1]
                        x0, y0, zmean = points.mean(axis=0)
                        design = np.column_stack([points[:, 0] - x0, points[:, 1] - y0, np.ones(len(points))])
                        ax, by, z0 = np.linalg.lstsq(design, points[:, 2], rcond=None)[0]
                        index += 1
                        output[short].append({
                            "id": f"{bid}_roof_{index}", "ring": ring, "polygon": polygon,
                            "x0": float(x0), "y0": float(y0), "z0": float(z0),
                            "ax": float(ax), "by": float(by), "source": path,
                        })
            elem.clear()
            parent = elem.getparent()
            if parent is not None:
                while elem.getprevious() is not None:
                    del parent[0]
    missing = [short for short, roofs in output.items() if not roofs]
    if missing:
        raise RuntimeError(f"missing LoD2 roofs: {missing}")
    return output


def reference_z(xy: np.ndarray, roofs: Sequence[dict[str, Any]], geoid: float) -> np.ndarray:
    values = np.full(len(xy), np.nan, dtype=np.float64)
    for roof in roofs:
        mask = contains_xy(roof["polygon"], xy[:, 0], xy[:, 1])
        if np.any(mask):
            values[mask] = (
                roof["z0"] + roof["ax"] * (xy[mask, 0] - roof["x0"])
                + roof["by"] * (xy[mask, 1] - roof["y0"]) + geoid
            )
    # Boundary representatives may land exactly on a roof edge.
    if np.any(~np.isfinite(values)):
        for index in np.flatnonzero(~np.isfinite(values)):
            nearest = min(roofs, key=lambda roof: roof["polygon"].distance(Point(float(xy[index, 0]), float(xy[index, 1]))))
            values[index] = (
                nearest["z0"] + nearest["ax"] * (xy[index, 0] - nearest["x0"])
                + nearest["by"] * (xy[index, 1] - nearest["y0"]) + geoid
            )
    return values


def point_inside_mask(points_local: np.ndarray, footprint: Any, offset: np.ndarray) -> np.ndarray:
    if not len(points_local):
        return np.zeros(0, dtype=bool)
    world_xy = points_local[:, :2].astype(np.float64) + offset[:2]
    minx, miny, maxx, maxy = footprint.bounds
    bbox_mask = (
        (world_xy[:, 0] >= minx) & (world_xy[:, 0] <= maxx)
        & (world_xy[:, 1] >= miny) & (world_xy[:, 1] <= maxy)
    )
    result = np.zeros(len(points_local), dtype=bool)
    indices = np.flatnonzero(bbox_mask)
    if len(indices):
        result[indices] = contains_xy(footprint, world_xy[indices, 0], world_xy[indices, 1])
    return result


def acquisition_block(view_stem: str) -> str:
    parts = view_stem.split("_")
    return parts[1][:12] if len(parts) > 1 else view_stem


def load_cached_points(short: str, footprint: Any, offset: np.ndarray, spec: dict[str, Any]) -> tuple[np.ndarray, list[Path], int]:
    paths = sorted((REPO / spec["pair_dir"]).glob(spec["pair_glob"].format(short=short)))
    selected: list[np.ndarray] = []
    eligible_pairs = 0
    for path in paths:
        payload = np.load(path, allow_pickle=False)
        metadata = json.loads(str(payload[spec["metadata_key"]].item()))
        row = metadata["row"]
        eligible = (
            acquisition_block(str(row["view_a"])) != acquisition_block(str(row["view_b"]))
            and float(row["known_colmap_baseline_m"]) > 0.06
        )
        if not eligible:
            continue
        eligible_pairs += 1
        points = np.asarray(payload[spec["points_key"]], dtype=np.float64)
        points = points[np.isfinite(points).all(axis=1)]
        selected.append(points[point_inside_mask(points, footprint, offset)])
    return (np.concatenate(selected, axis=0) if selected else np.empty((0, 3))), paths, eligible_pairs


def _read_points_file(path: Path, key: str) -> np.ndarray:
    if path.suffix.lower() == ".npz":
        payload = np.load(path, allow_pickle=False)
        if key not in payload.files:
            raise RuntimeError(f"points key {key!r} missing in {rel(path)}: {payload.files}")
        return np.asarray(payload[key], dtype=np.float64)
    if path.suffix.lower() == ".npy":
        return np.asarray(np.load(path, allow_pickle=False), dtype=np.float64)
    if path.suffix.lower() == ".csv":
        rows = list(csv.DictReader(path.open(newline="", encoding="utf-8")))
        return np.asarray([[float(row[x]) for x in ("x", "y", "z")] for row in rows], dtype=np.float64)
    raise RuntimeError(f"unsupported points file: {rel(path)}")


def load_manifest_points(short: str, footprint: Any, offset: np.ndarray, manifest_path: Path) -> tuple[np.ndarray, list[Path], int, str]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema") != "jointbuildgs.s3ap.fm_selected_points.v1":
        raise RuntimeError(f"selected manifest schema mismatch: {manifest.get('schema')}")
    entry = (manifest.get("buildings") or {}).get(short) or (manifest.get("buildings") or {}).get(f"DEBY_LOD2_{short}")
    if not entry:
        raise RuntimeError(f"selected manifest missing building {short}")
    paths = [REPO / value for value in entry.get("point_paths", [entry.get("points_path")]) if value]
    key = str(entry.get("points_key", "world_local_xyz"))
    points = np.concatenate([_read_points_file(path, key) for path in paths], axis=0) if paths else np.empty((0, 3))
    points = points[np.isfinite(points).all(axis=1)]
    coordinates = str(entry.get("coordinates", "gs_local"))
    if coordinates == "epsg25832":
        points = points - offset[None, :]
    elif coordinates != "gs_local":
        raise RuntimeError(f"unsupported coordinates {coordinates!r} for {short}")
    return points[point_inside_mask(points, footprint, offset)], [manifest_path, *paths], int(entry.get("eligible_pair_count", 0)), str(manifest.get("threshold_label", "selected"))


def fit_plane_ransac(points: np.ndarray, spec: dict[str, Any], seed_delta: int = 0) -> dict[str, Any]:
    finite = points[np.isfinite(points).all(axis=1)]
    if len(finite) < int(spec["min_samples"]):
        return {"status": "insufficient_points", "coef": np.full(3, np.nan), "inlier": np.zeros(len(finite), bool), "rms": None}
    x = finite[:, :2]
    z = finite[:, 2]
    design = np.column_stack([x, np.ones(len(x))])
    rng = np.random.default_rng(int(spec["random_seed"]) + seed_delta)
    threshold = float(spec["residual_threshold_m"])
    best_mask = np.zeros(len(finite), dtype=bool)
    best_score = (-1, -math.inf)
    for _ in range(int(spec["max_trials"])):
        sample = rng.choice(len(finite), int(spec["min_samples"]), replace=False)
        if np.linalg.matrix_rank(design[sample]) < 3:
            continue
        coef = np.linalg.lstsq(design[sample], z[sample], rcond=None)[0]
        residual = np.abs(z - design @ coef)
        mask = residual <= threshold
        score = (int(mask.sum()), -float(np.median(residual[mask])) if np.any(mask) else -math.inf)
        if score > best_score:
            best_score, best_mask = score, mask
    if int(best_mask.sum()) < 3:
        return {"status": "ransac_no_consensus", "coef": np.full(3, np.nan), "inlier": best_mask, "rms": None}
    coef = np.linalg.lstsq(design[best_mask], z[best_mask], rcond=None)[0]
    for _ in range(3):
        mask = np.abs(z - design @ coef) <= threshold
        if int(mask.sum()) < 3:
            break
        new_coef = np.linalg.lstsq(design[mask], z[mask], rcond=None)[0]
        if np.array_equal(mask, best_mask) and np.allclose(new_coef, coef, atol=1e-12):
            best_mask, coef = mask, new_coef
            break
        best_mask, coef = mask, new_coef
    pre_anchor_coef = coef.copy()
    anchor_z_median = float(np.median(z))
    anchor_shape_median = float(np.median(coef[0] * x[:, 0] + coef[1] * x[:, 1]))
    coef[2] = anchor_z_median - anchor_shape_median
    anchor_predicted_median = float(np.median(design @ coef))
    anchor_residual = anchor_predicted_median - anchor_z_median
    residual = z[best_mask] - design[best_mask] @ coef
    return {
        "status": "fit", "coef": coef, "pre_anchor_coef": pre_anchor_coef,
        "anchor_z_median": anchor_z_median,
        "anchor_predicted_median": anchor_predicted_median,
        "anchor_residual": anchor_residual,
        "inlier": best_mask,
        "rms": float(np.sqrt(np.mean(residual * residual))) if len(residual) else None,
    }


def fill_footprint(footprint: Any, offset: np.ndarray, coef: np.ndarray, grid: float) -> tuple[np.ndarray, int]:
    minx, miny, maxx, maxy = footprint.bounds
    ix0, ix1 = math.floor(minx / grid), math.ceil(maxx / grid)
    iy0, iy1 = math.floor(miny / grid), math.ceil(maxy / grid)
    xy: list[tuple[float, float]] = []
    eligible = 0
    for ix in range(ix0, ix1):
        for iy in range(iy0, iy1):
            cell = box(ix * grid, iy * grid, (ix + 1) * grid, (iy + 1) * grid)
            overlap = footprint.intersection(cell)
            if overlap.is_empty or overlap.area <= 1e-10:
                continue
            eligible += 1
            point = overlap.representative_point()
            xy.append((float(point.x), float(point.y)))
    world_xy = np.asarray(xy, dtype=np.float64).reshape(-1, 2)
    local_xy = world_xy - offset[:2]
    z = coef[0] * local_xy[:, 0] + coef[1] * local_xy[:, 1] + coef[2]
    return np.column_stack([local_xy, z]), eligible


def load_observed_ground(path: Path, targets: Sequence[str]) -> dict[str, dict[str, Any]]:
    output: dict[str, dict[str, Any]] = {}
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if row.get("row_type") != "building_summary":
                continue
            short = str(row.get("building_id", "")).removeprefix("DEBY_LOD2_")
            if short not in targets:
                continue
            output[short] = {
                "z_local_m": float(row["ground_z_local_m"]),
                "method": row.get("ground_method", ""),
                "source": row.get("ground_source", ""),
            }
    missing = sorted(set(targets) - set(output))
    if missing:
        raise RuntimeError(f"observed ground summary missing: {missing}")
    return output


def occupied_cell_union(points_local: np.ndarray, offset: np.ndarray, grid: float) -> Any:
    """Build a roofprint only from P0 point occupied cells.

    No supplied footprint geometry is accepted by this function, so the
    adapter cannot accidentally clip/intersect the evidence-derived polygon.
    """
    world_xy = np.asarray(points_local[:, :2], dtype=np.float64) + offset[:2]
    keys = sorted({
        (math.floor(float(x) / grid), math.floor(float(y) / grid))
        for x, y in world_xy
    })
    if not keys:
        return GeometryCollection()
    geom = make_valid(unary_union([
        box(ix * grid, iy * grid, (ix + 1) * grid, (iy + 1) * grid)
        for ix, iy in keys
    ]))
    if geom.is_empty:
        raise RuntimeError("point-evidence occupied-cell union is empty")
    return geom


def write_derived_roofprints(
    targets: Sequence[str],
    fill_by_short: dict[str, np.ndarray],
    offset: np.ndarray,
    grid: float,
) -> dict[str, Any]:
    features: list[dict[str, Any]] = []
    polygons: dict[str, Any] = {}
    for short in targets:
        geom = occupied_cell_union(fill_by_short[short], offset, grid)
        polygons[short] = geom
        features.append({
            "type": "Feature",
            "properties": {
                "building_id": f"DEBY_LOD2_{short}",
                "source": "p0_fill_point_occupied_cell_union",
                "grid_m": grid,
                "point_count": int(len(fill_by_short[short])),
            },
            "geometry": mapping(geom),
        })
    payload = {
        "type": "FeatureCollection",
        "name": "point_evidence_derived_roofprints",
        "crs": {"type": "name", "properties": {"name": "urn:ogc:def:crs:EPSG::25832"}},
        "features": features,
    }
    atomic_text(DERIVED_ROOFPRINTS, json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n")
    return polygons


def write_roofer_las(
    targets: Sequence[str],
    fill_by_short: dict[str, np.ndarray],
    ground: dict[str, dict[str, Any]],
    offset: np.ndarray,
    roof_class: int,
    ground_class: int,
) -> None:
    roof_world = np.concatenate([
        np.asarray(fill_by_short[short], dtype=np.float64) + offset[None, :]
        for short in targets
    ], axis=0)
    ground_world_parts: list[np.ndarray] = []
    for short in targets:
        roof = np.asarray(fill_by_short[short], dtype=np.float64) + offset[None, :]
        ground_part = roof.copy()
        ground_part[:, 2] = float(ground[short]["z_local_m"]) + offset[2]
        ground_world_parts.append(ground_part)
    ground_world = np.concatenate(ground_world_parts, axis=0)
    xyz = np.vstack([roof_world, ground_world])
    classification = np.concatenate([
        np.full(len(roof_world), roof_class, dtype=np.uint8),
        np.full(len(ground_world), ground_class, dtype=np.uint8),
    ])
    header = laspy.LasHeader(point_format=6, version="1.4")
    header.scales = np.asarray([0.001, 0.001, 0.001])
    header.offsets = np.floor(np.min(xyz, axis=0))
    header.add_crs(CRS.from_epsg(25832))
    cloud = laspy.LasData(header)
    cloud.x, cloud.y, cloud.z = xyz[:, 0], xyz[:, 1], xyz[:, 2]
    cloud.classification = classification
    cloud.write(P0_ROOFER_LAS)


def grid_coverage_world(points_xy: np.ndarray, footprint: Any, grid: float) -> tuple[int, int, float]:
    minx, miny, maxx, maxy = footprint.bounds
    eligible: set[tuple[int, int]] = set()
    for ix in range(math.floor(minx / grid), math.ceil(maxx / grid)):
        for iy in range(math.floor(miny / grid), math.ceil(maxy / grid)):
            if footprint.intersects(box(ix * grid, iy * grid, (ix + 1) * grid, (iy + 1) * grid)):
                eligible.add((ix, iy))
    occupied = {
        (math.floor(float(x) / grid), math.floor(float(y) / grid))
        for x, y in points_xy if footprint.covers(Point(float(x), float(y)))
    } & eligible
    return len(eligible), len(occupied), (len(occupied) / len(eligible) if eligible else 0.0)


P0_FIELDS = [
    "building_id", "fm_threshold_label", "fm_input_mode", "fm_inside_point_count", "eligible_pair_count",
    "plane_status", "plane_ax_local", "plane_by_local", "plane_c_ransac_local",
    "plane_c_anchor_local", "plane_c_local", "height_anchor_z_median_local_m",
    "anchor_predicted_z_median_local_m", "anchor_residual_m", "ransac_inlier_count",
    "ransac_inlier_ratio", "plane_internal_rms_m", "fill_grid_m", "fill_point_count",
    "coverage_eligible_cell_count", "coverage_occupied_cell_count", "coverage_ratio",
    "height_error_signed_median_m", "height_error_abs_median_m", "height_error_mad_m", "height_error_rms_m",
    "gt_role", "footprint_role", "roofer_readout_status", "roofer_block_reason", "roofer_adapter",
    "derived_roofprint_area_m2", "supplied_footprint_passed_to_roofer",
    "point_evidence_derived_roofprint_passed_to_roofer", "roofer_status", "roofer_reason",
    "rf_extrusion_mode", "rf_roof_planes", "cityjson_path", "cityjson_building_object_id",
    "cityjson_child_object_ids", "geometry_has_lod22", "has_lod22",
    "val3dity_valid", "substantive_filter", "citygml_completeness", "citygml_roof_rms_m",
    "crs", "vertical_frame", "learning_runs_started", "new_mast3r_inference_runs", "status",
]


MVS_FIELDS = [
    "building_id", "source", "source_path", "footprint_area_m2", "all_points_in_footprint",
    "building_class6_points_in_footprint", "coverage_grid_m", "coverage_eligible_cell_count",
    "coverage_occupied_cell_count", "building_class6_coverage_ratio", "direct_class6_no_points",
    "canonical_roofer_status", "canonical_roofer_reason", "canonical_roofer_no_points", "canonical_has_lod22",
    "no_points_definition", "footprint_role", "gt_role", "crs", "learning_runs_started", "status",
]


def load_dim_status(path: Path, targets: Sequence[str], label: str) -> dict[str, dict[str, str]]:
    output: dict[str, dict[str, str]] = {}
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            short = row.get("building_id", "").removeprefix("DEBY_LOD2_")
            if short in targets and row.get("input") == label:
                output[short] = row
    if set(output) != set(targets):
        raise RuntimeError(f"canonical DIM status missing: {sorted(set(targets) - set(output))}")
    return output


def plot_outline(ax: Any, geom: Any, centre: np.ndarray, color: str, linestyle: str, label: str, z: float | None = None) -> None:
    first = True
    for polygon in flatten_polygons(geom):
        for ring in [polygon.exterior, *polygon.interiors]:
            xy = np.asarray(ring.coords, dtype=np.float64) - centre[None, :]
            if hasattr(ax, "zaxis"):
                ax.plot(xy[:, 0], xy[:, 1], np.full(len(xy), z if z is not None else 0.0), color=color, linestyle=linestyle, linewidth=1.5, label=label if first else None)
            else:
                ax.plot(xy[:, 0], xy[:, 1], color=color, linestyle=linestyle, linewidth=1.7, label=label if first else None)
            first = False


def make_p0_figure(targets: Sequence[str], footprints: dict[str, Any], roofs: dict[str, list[dict[str, Any]]], details: dict[str, dict[str, Any]], offset: np.ndarray, geoid: float) -> None:
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    fig = plt.figure(figsize=(15, 12), dpi=150)
    for row_index, short in enumerate(targets):
        detail = details[short]
        footprint = footprints[short]
        roof_union = make_valid(unary_union([roof["polygon"] for roof in roofs[short]]))
        centre = np.asarray(footprint.centroid.coords[0], dtype=np.float64)
        fm = detail["fm"]
        fill = detail["fill"]
        fm_world = fm[:, :2] + offset[:2]
        fill_world = fill[:, :2] + offset[:2]
        ax0 = fig.add_subplot(len(targets), 3, row_index * 3 + 1)
        plot_outline(ax0, footprint, centre, "#00a6c8", "-", "footprint")
        plot_outline(ax0, roof_union, centre, "#e67e22", "--", "LoD2 roof outline")
        if len(fm):
            ax0.scatter(fm_world[:, 0] - centre[0], fm_world[:, 1] - centre[1], s=8, c="#263238", marker="x", linewidths=0.45, label="FM inside")
        ax0.set_title(f"{short} FM input | N={len(fm)}")
        ax0.set_aspect("equal"); ax0.legend(fontsize=6, loc="best")
        ax0.set_xlabel("E-centre [m]"); ax0.set_ylabel("N-centre [m]")

        ax1 = fig.add_subplot(len(targets), 3, row_index * 3 + 2)
        plot_outline(ax1, footprint, centre, "#00a6c8", "-", "footprint")
        plot_outline(ax1, roof_union, centre, "#e67e22", "--", "LoD2 roof outline")
        if len(fill):
            ax1.scatter(fill_world[:, 0] - centre[0], fill_world[:, 1] - centre[1], s=7, facecolors="none", edgecolors="#00a6c8", marker="o", linewidths=0.45, label="P0 fill")
        ax1.set_title(f"P0 fill | N={len(fill)}, coverage={detail['row']['coverage_ratio']:.3f}")
        ax1.set_aspect("equal"); ax1.legend(fontsize=6, loc="best")
        ax1.set_xlabel("E-centre [m]"); ax1.set_ylabel("N-centre [m]")

        ax2 = fig.add_subplot(len(targets), 3, row_index * 3 + 3, projection="3d")
        if len(fill):
            ax2.scatter(fill_world[:, 0] - centre[0], fill_world[:, 1] - centre[1], fill[:, 2], s=3, c="#00a6c8", marker="o", alpha=0.65, label="P0 fill")
        for index, roof in enumerate(roofs[short]):
            ring = roof["ring"].copy()
            vertices = np.column_stack([ring[:, 0] - centre[0], ring[:, 1] - centre[1], ring[:, 2] + geoid - offset[2]])
            ax2.plot(vertices[:, 0], vertices[:, 1], vertices[:, 2], color="#e67e22", linestyle="--", linewidth=1.1)
        ax2.set_title("P0 filled surface")
        ax2.set_xlabel("E-centre [m]"); ax2.set_ylabel("N-centre [m]"); ax2.set_zlabel("z local [m]")
        ax2.view_init(24, -58)
        if len(fill):
            ax2.legend(fontsize=6, loc="best")
    fig.suptitle("S3-A-prime Phase 0 P0 plane-fit and footprint fill | EPSG:25832 | LoD2 score/overlay only", fontsize=11)
    fig.tight_layout(rect=[0, 0, 1, 0.97])
    fig.savefig(P0_FIG)
    plt.close(fig)


def make_mvs_figure(targets: Sequence[str], footprints: dict[str, Any], roofs: dict[str, list[dict[str, Any]]], details: dict[str, dict[str, Any]], geoid: float) -> None:
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    fig = plt.figure(figsize=(12, 12), dpi=150)
    for row_index, short in enumerate(targets):
        detail = details[short]
        footprint = footprints[short]
        roof_union = make_valid(unary_union([roof["polygon"] for roof in roofs[short]]))
        centre = np.asarray(footprint.centroid.coords[0], dtype=np.float64)
        all_points, support = detail["all"], detail["support"]
        ax0 = fig.add_subplot(len(targets), 2, row_index * 2 + 1)
        plot_outline(ax0, footprint, centre, "#00a6c8", "-", "footprint")
        plot_outline(ax0, roof_union, centre, "#e67e22", "--", "LoD2 roof outline")
        if len(all_points):
            ax0.scatter(all_points[:, 0] - centre[0], all_points[:, 1] - centre[1], s=7, c="#b0bec5", marker=".", label="all DIM in footprint")
        if len(support):
            ax0.scatter(support[:, 0] - centre[0], support[:, 1] - centre[1], s=20, c="#e67e22", marker="x", linewidths=0.9, label="DIM class 6 support")
        row = detail["row"]
        ax0.set_title(f"{short} DIM support | N6={len(support)}, coverage={row['building_class6_coverage_ratio']:.3f}")
        ax0.set_aspect("equal"); ax0.set_xlabel("E-centre [m]"); ax0.set_ylabel("N-centre [m]"); ax0.legend(fontsize=6, loc="best")

        ax1 = fig.add_subplot(len(targets), 2, row_index * 2 + 2, projection="3d")
        if len(support):
            ax1.scatter(support[:, 0] - centre[0], support[:, 1] - centre[1], support[:, 2], s=13, c="#e67e22", marker="x", linewidths=0.8, label="DIM class 6 support")
        else:
            ax1.text2D(0.5, 0.5, "0 class-6 points", transform=ax1.transAxes, ha="center", va="center")
        for index, roof in enumerate(roofs[short]):
            ring = roof["ring"].copy()
            vertices = np.column_stack([ring[:, 0] - centre[0], ring[:, 1] - centre[1], ring[:, 2] + geoid])
            ax1.plot(vertices[:, 0], vertices[:, 1], vertices[:, 2], color="#00a6c8", linestyle="--", linewidth=1.1)
        ax1.set_title(f"canonical Roofer reason: {row['canonical_roofer_reason']}")
        ax1.set_xlabel("E-centre [m]"); ax1.set_ylabel("N-centre [m]"); ax1.set_zlabel("z ellipsoidal [m]")
        ax1.view_init(24, -58)
        if len(support):
            ax1.legend(fontsize=6, loc="best")
    fig.suptitle("S3-A-prime Phase 0 existing DIM/MVS roof support | EPSG:25832 | LoD2 overlay only", fontsize=11)
    fig.tight_layout(rect=[0, 0, 1, 0.97])
    fig.savefig(MVS_FIG)
    plt.close(fig)


def report_fragment(p0_rows: Sequence[dict[str, Any]], mvs_rows: Sequence[dict[str, Any]]) -> str:
    lines = [
        "## Phase 0 §3-3 — P0 plane-fit baseline and MVS hole check", "",
        "> Measurement only. Learning 0; new MASt3R inference 0. LoD2 is score/overlay only.", "",
        "### P0 plane-fit + footprint fill", "",
        "| building | FM N | inlier | fill N | coverage | median abs dz (m) | RMS (m) | read-out |",
        "|---|---:|---:|---:|---:|---:|---:|---|",
    ]
    for row in p0_rows:
        lines.append(
            f"| {row['building_id']} | {row['fm_inside_point_count']} | {fmt(row['ransac_inlier_ratio'])} "
            f"| {row['fill_point_count']} | {fmt(row['coverage_ratio'])} | {fmt(row['height_error_abs_median_m'])} "
            f"| {fmt(row['height_error_rms_m'])} | `{row['roofer_readout_status']}` |"
        )
    lines.extend([
        "", "The repository's original adapter is blocked because it passes the supplied footprint directly. "
        "This run instead derives Roofer roofprints from the 0.5 m occupied cells of the P0 point evidence. "
        "The supplied footprint itself is not passed to Roofer; this fragment is finalized after Roofer and val3dity.", "",
        f"![P0 plane fill]({rel(P0_FIG)})", "", "### Existing DIM/MVS support", "",
        "| building | all in footprint | class-6 support | class-6 coverage | direct zero | canonical Roofer reason | has_lod22 |",
        "|---|---:|---:|---:|---|---|---|",
    ])
    for row in mvs_rows:
        lines.append(
            f"| {row['building_id']} | {row['all_points_in_footprint']} | {row['building_class6_points_in_footprint']} "
            f"| {fmt(row['building_class6_coverage_ratio'])} | {fmt(row['direct_class6_no_points'])} "
            f"| `{row['canonical_roofer_reason']}` | {row['canonical_has_lod22']} |"
        )
    lines.extend(["", f"![MVS support]({rel(MVS_FIG)})", ""])
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default=str(CONFIG))
    parser.add_argument("--selected-points-manifest")
    args = parser.parse_args()
    config_path = Path(args.config).resolve()
    config = json.loads(config_path.read_text(encoding="utf-8"))
    if config["learning_runs_allowed"] != 0 or config["new_mast3r_inference_allowed"] is not False:
        raise RuntimeError("learning/inference lock mismatch")
    targets = list(config["targets"])
    selected_manifest = Path(args.selected_points_manifest).resolve() if args.selected_points_manifest else None
    if selected_manifest is None and config["fm_input"].get("selected_points_manifest"):
        selected_manifest = (REPO / config["fm_input"]["selected_points_manifest"]).resolve()
    RUN_DIR.mkdir(parents=True, exist_ok=True)
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    atomic_text(RUN_LOG, "")
    write_progress("preflight", [], "started")
    log(f"start selected_points_manifest={rel(selected_manifest) if selected_manifest else 'none'}")
    offset = np.asarray(json.loads(TRAIN_MANIFEST.read_text(encoding="utf-8"))["world_offset"], dtype=np.float64)
    geoid = float(json.loads(PROJECTION_DATUM.read_text(encoding="utf-8"))["orthometric_geoid_m"])
    footprints = load_footprints(targets)
    ground_source_path = REPO / config["roofer_readout"]["adapter"]["ground_source_csv"]
    observed_ground = load_observed_ground(ground_source_path, targets)
    p0_rows: list[dict[str, Any]] = []
    p0_details: dict[str, dict[str, Any]] = {}
    source_paths: set[Path] = {
        Path(__file__), config_path, FOOTPRINTS, TRAIN_MANIFEST, PROJECTION_DATUM, ground_source_path,
        REPO / "phases/p2-gsjso/scripts/e5_c001_s3ap_phase0_roofer_finalize.py",
        REPO / "phases/p2-gsjso/scripts/run_e5_c001_s3ap_phase0_baselines.sh",
    }
    completed: list[str] = []
    fill_arrays: dict[str, np.ndarray] = {}
    fill_by_short: dict[str, np.ndarray] = {}
    for index, short in enumerate(targets):
        if selected_manifest:
            fm_points, paths, eligible_pairs, threshold_label = load_manifest_points(short, footprints[short], offset, selected_manifest)
            input_mode = "selected_points_manifest"
        else:
            fm_points, paths, eligible_pairs = load_cached_points(short, footprints[short], offset, config["fm_input"])
            threshold_label = str(config["fm_input"]["threshold_label"])
            input_mode = "cached_dlt_pairs"
        source_paths.update(paths)
        if len(fm_points) < 3:
            raise RuntimeError(f"P0 plane fit requires >=3 inside FM points: {short} has {len(fm_points)}")
        fit = fit_plane_ransac(fm_points, config["plane_fit"], seed_delta=index)
        if fit["status"] != "fit":
            raise RuntimeError(f"P0 plane fit failed: {short}: {fit['status']}")
        fill, eligible_cells = fill_footprint(footprints[short], offset, fit["coef"], float(config["fill"]["grid_m"]))
        fill_arrays[f"DEBY_LOD2_{short}_local_xyz"] = fill
        fill_arrays[f"DEBY_LOD2_{short}_fm_local_xyz"] = fm_points
        fill_by_short[short] = fill
        row = {
            "building_id": f"DEBY_LOD2_{short}", "fm_threshold_label": threshold_label,
            "fm_input_mode": input_mode, "fm_inside_point_count": len(fm_points), "eligible_pair_count": eligible_pairs,
            "plane_status": fit["status"], "plane_ax_local": fit["coef"][0], "plane_by_local": fit["coef"][1],
            "plane_c_ransac_local": fit["pre_anchor_coef"][2],
            "plane_c_anchor_local": fit["coef"][2],
            "plane_c_local": fit["coef"][2],
            "height_anchor_z_median_local_m": fit["anchor_z_median"],
            "anchor_predicted_z_median_local_m": fit["anchor_predicted_median"],
            "anchor_residual_m": fit["anchor_residual"],
            "ransac_inlier_count": int(fit["inlier"].sum()),
            "ransac_inlier_ratio": float(fit["inlier"].mean()), "plane_internal_rms_m": fit["rms"],
            "fill_grid_m": float(config["fill"]["grid_m"]), "fill_point_count": len(fill),
            "coverage_eligible_cell_count": eligible_cells, "coverage_occupied_cell_count": len(fill),
            "coverage_ratio": len(fill) / eligible_cells if eligible_cells else 0.0,
            "height_error_signed_median_m": None, "height_error_abs_median_m": None,
            "height_error_mad_m": None, "height_error_rms_m": None,
            "gt_role": "LoD2 roof loaded only after all P0 surfaces and Roofer inputs were constructed; score/overlay only",
            "footprint_role": config["fill"]["footprint_role"],
            "roofer_readout_status": config["roofer_readout"]["status"],
            "roofer_block_reason": "",
            "roofer_adapter": config["roofer_readout"]["adapter"]["name"],
            "derived_roofprint_area_m2": None,
            "supplied_footprint_passed_to_roofer": False,
            "point_evidence_derived_roofprint_passed_to_roofer": False,
            "roofer_status": "", "roofer_reason": "", "rf_extrusion_mode": "", "rf_roof_planes": "",
            "cityjson_path": "", "cityjson_building_object_id": "",
            "cityjson_child_object_ids": "",
            "geometry_has_lod22": None, "has_lod22": None,
            "val3dity_valid": None, "substantive_filter": None,
            "citygml_completeness": None, "citygml_roof_rms_m": None,
            "crs": config["crs"], "vertical_frame": "GS local ellipsoidal; LoD2 + geoid for scoring",
            "learning_runs_started": 0, "new_mast3r_inference_runs": 0, "status": "measured_surface_readout_pending",
        }
        p0_rows.append(row)
        p0_details[short] = {"fm": fm_points, "fill": fill, "fit": fit, "row": row}
        atomic_csv(OUT_P0, p0_rows, P0_FIELDS)
        completed.append(short)
        write_progress("p0_planefit", completed, f"building_complete:{short}")
        log(
            f"p0_construct {short} fm={len(fm_points)} fill={len(fill)} "
            f"anchor_residual={row['anchor_residual_m']:.12f}"
        )
    np.savez_compressed(P0_POINTS, **fill_arrays)
    adapter = config["roofer_readout"]["adapter"]
    derived_polygons = write_derived_roofprints(
        targets, fill_by_short, offset, float(adapter["grid_m"]),
    )
    write_roofer_las(
        targets, fill_by_short, observed_ground, offset,
        int(adapter["roof_class"]), int(adapter["ground_class"]),
    )
    for row in p0_rows:
        short = str(row["building_id"]).removeprefix("DEBY_LOD2_")
        row["derived_roofprint_area_m2"] = float(derived_polygons[short].area)
    atomic_csv(OUT_P0, p0_rows, P0_FIELDS)
    log(
        f"roofer_input roofprints={rel(DERIVED_ROOFPRINTS)} las={rel(P0_ROOFER_LAS)} "
        "supplied_footprint_passed=false"
    )
    # Strict GT separation: LoD2 is opened only after every P0 plane/fill and
    # the point-evidence-derived Roofer inputs have been finalized.
    roofs = load_lod2(targets)
    completed = []
    for short in targets:
        detail = p0_details[short]
        fill = detail["fill"]
        world_xy = fill[:, :2] + offset[:2]
        ref_local = reference_z(world_xy, roofs[short], geoid) - offset[2]
        dz = fill[:, 2] - ref_local
        abs_dz = np.abs(dz)
        row = detail["row"]
        row.update({
            "height_error_signed_median_m": float(np.median(dz)),
            "height_error_abs_median_m": float(np.median(abs_dz)),
            "height_error_mad_m": float(np.median(np.abs(abs_dz - np.median(abs_dz)))),
            "height_error_rms_m": float(np.sqrt(np.mean(dz * dz))),
        })
        atomic_csv(OUT_P0, p0_rows, P0_FIELDS)
        completed.append(short)
        write_progress("p0_gt_score", completed, f"building_complete:{short}")
        log(
            f"p0_score {short} dz_med={row['height_error_abs_median_m']:.6f} "
            f"rms={row['height_error_rms_m']:.6f}"
        )
    make_p0_figure(targets, footprints, roofs, p0_details, offset, geoid)

    mvs_rows: list[dict[str, Any]] = []
    mvs_details: dict[str, dict[str, Any]] = {}
    dim_status_path = REPO / config["mvs"]["canonical_status"]
    dim_status = load_dim_status(dim_status_path, targets, config["mvs"]["canonical_input_label"])
    source_paths.add(dim_status_path)
    completed = []
    for short in targets:
        path = REPO / config["mvs"]["source_template"].format(short=short)
        source_paths.add(path)
        cloud = laspy.read(path)
        xyz = np.column_stack([np.asarray(cloud.x), np.asarray(cloud.y), np.asarray(cloud.z)]).astype(np.float64)
        classes = np.asarray(cloud.classification, dtype=np.uint8)
        fp = footprints[short]
        inside = contains_xy(fp, xyz[:, 0], xyz[:, 1])
        all_inside = xyz[inside]
        support = xyz[inside & (classes == int(config["mvs"]["building_class"]))]
        eligible, occupied, coverage = grid_coverage_world(support[:, :2], fp, float(config["mvs"]["coverage_grid_m"]))
        canonical = dim_status[short]
        row = {
            "building_id": f"DEBY_LOD2_{short}", "source": "raw_dense_DIM_existing",
            "source_path": rel(path), "footprint_area_m2": float(fp.area), "all_points_in_footprint": len(all_inside),
            "building_class6_points_in_footprint": len(support), "coverage_grid_m": float(config["mvs"]["coverage_grid_m"]),
            "coverage_eligible_cell_count": eligible, "coverage_occupied_cell_count": occupied,
            "building_class6_coverage_ratio": coverage, "direct_class6_no_points": len(support) == 0,
            "canonical_roofer_status": canonical.get("status", ""), "canonical_roofer_reason": canonical.get("reason", ""),
            "canonical_roofer_no_points": canonical.get("reason") == "pointcloud_unusable_no_points",
            "canonical_has_lod22": canonical.get("has_lod22", ""),
            "no_points_definition": config["mvs"]["no_points_rule"],
            "footprint_role": "inside/coverage spatial mask only",
            "gt_role": "LoD2 outline overlay only; not used for MVS support selection",
            "crs": config["crs"], "learning_runs_started": 0, "status": "measured_existing_artifact",
        }
        mvs_rows.append(row)
        mvs_details[short] = {"all": all_inside, "support": support, "row": row}
        atomic_csv(OUT_MVS, mvs_rows, MVS_FIELDS)
        completed.append(short)
        write_progress("mvs_hole_check", completed, f"building_complete:{short}")
        log(f"mvs {short} all={len(all_inside)} class6={len(support)} coverage={coverage:.6f} canonical={canonical.get('reason')}")
    make_mvs_figure(targets, footprints, roofs, mvs_details, geoid)
    atomic_text(REPORT, report_fragment(p0_rows, mvs_rows))
    write_progress("roofer_input_prepared", targets, "pending_roofer_and_val3dity")
    log("base measurements complete learning=0 inference=0 roofer=point_evidence_derived_roofprint_pending")

    source_paths.update(roof["source"] for values in roofs.values() for roof in values)
    source_paths.add(REPO / config["roofer_readout"]["forbidden_adapter"])
    source_paths.add(REPO / config["roofer_readout"]["design_reference"])
    output_paths = [
        OUT_P0, OUT_MVS, P0_FIG, MVS_FIG, P0_POINTS, P0_ROOFER_LAS,
        DERIVED_ROOFPRINTS, REPORT, PROGRESS, RUN_LOG,
    ]
    manifest = {
        "schema": "jointbuildgs.s3ap.phase0.baselines.v1", "created_utc": now(), "targets": targets,
        "git_head_at_measurement": git_value("rev-parse", "HEAD"), "branch": git_value("branch", "--show-current"),
        "crs": config["crs"], "learning_runs_started": 0, "new_mast3r_inference_runs": 0,
        "docker": {
            "tools_tag": "jointbuildgs-p0-tools:t0",
            "tools_image_id": "sha256:87bea02e5598a3d53a119b754191673497d52641bd8ea4106ffee653407579b0",
            "roofer_tag": "3dgi/roofer:v1.0.0",
            "roofer_image_id": "sha256:9c980b97fba4c3fd30f5bb4afb8f2621be211d4e72e4333ea2053e8cd69b2dba",
            "roofer_version": "1.0.0", "val3dity_version": "2.6.0",
        },
        "fm_threshold_label": p0_rows[0]["fm_threshold_label"] if p0_rows else "",
        "fm_input_mode": p0_rows[0]["fm_input_mode"] if p0_rows else "",
        "selected_points_manifest": rel(selected_manifest) if selected_manifest else None,
        "plane_fit": config["plane_fit"], "fill": config["fill"],
        "gt_separation": {
            "candidate_generation": "FM points and fitted P0 surface only",
            "footprint": "explicit P0 extension plus inside/coverage mask",
            "lod2": "loaded after P0 construction for score/overlay only",
            "als_used": False,
        },
        "roofer_readout": config["roofer_readout"],
        "roofer_input_contract": {
            "supplied_footprint_passed_to_roofer": False,
            "point_evidence_derived_roofprint": rel(DERIVED_ROOFPRINTS),
            "point_evidence_derived_roofprint_passed_to_roofer": False,
            "indirect_supplied_footprint_dependency": config["roofer_readout"]["adapter"]["indirect_dependency"],
            "ground_source": rel(ground_source_path),
        },
        "roofer_adapter_executed": False, "val3dity_executed": False,
        "p0_rows": len(p0_rows), "mvs_rows": len(mvs_rows),
        "source_sha256": {rel(path): sha256_file(path) for path in sorted(source_paths) if path.exists()},
        "output_sha256": {rel(path): sha256_file(path) for path in output_paths},
        "interpretation_or_verdict": None,
    }
    atomic_text(MANIFEST, json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")


if __name__ == "__main__":
    main()
