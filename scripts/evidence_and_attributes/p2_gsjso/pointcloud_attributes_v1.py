#!/usr/bin/env python3
"""Point-cloud input attributes for P2 structure-learning analysis.

Observation only: no reconstruction, no retraining.  Runs inside
jointbuildgs-p0-tools:t0.  Horizontal CRS is EPSG:25832; raw point-cloud arms
are treated as the existing ellip-unified clips.  Reference LoD2 roof heights
are orthometric and are converted to the raw-arm height frame only for
point-to-reference threshold tests.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import shutil
import subprocess
import tempfile
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import laspy

os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib")
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from lxml import etree
from shapely import contains_xy
from shapely.geometry import Polygon, shape


ARMS = ("raw_dense", "raw_acmp", "raw_lidar")
STATUS_ARM = {"raw_dense": "DIM", "raw_lidar": "ALS"}
RUN_ID = "20260704_attr_v1"
GEOID_MED_M = 48.165
ACMP_ORTHO_TO_ELLIP_M = 48.0


@dataclass
class RoofSurface:
    polygon: Polygon
    point: np.ndarray
    normal: np.ndarray
    z_min: float
    z_max: float

    def z_at(self, x: np.ndarray, y: np.ndarray) -> np.ndarray:
        if abs(float(self.normal[2])) < 1e-9:
            return np.full_like(x, float(self.point[2]), dtype=np.float64)
        return self.point[2] - (
            self.normal[0] * (x - self.point[0]) + self.normal[1] * (y - self.point[1])
        ) / self.normal[2]


@dataclass
class ArmPoints:
    xyz: np.ndarray
    cls: np.ndarray
    source: str
    path: str
    z_history: str
    note: str = ""


def fmt(v, digits: int = 6) -> str:
    if v is None:
        return "none"
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (np.integer, int)):
        return str(int(v))
    if isinstance(v, (np.floating, float)):
        if not math.isfinite(float(v)):
            return "none"
        return f"{float(v):.{digits}f}"
    return str(v)


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def read_population(path: Path) -> list[str]:
    rows = read_csv_rows(path)
    return [r["building_id"] for r in rows]


def status_path(repo: Path, requested: Path) -> tuple[Path, str]:
    if requested.exists():
        return requested, "requested"
    fallback = repo / "phases/p0-audit/runs/w2_1_roofer_default_20260612_152729/building_reconstruction_status.csv"
    if fallback.exists():
        return fallback, "fallback_canonical_w2_1_docs_copy_missing"
    raise FileNotFoundError(f"status CSV not found: {requested} or {fallback}")


def load_status(path: Path) -> dict[tuple[str, str], dict[str, str]]:
    out: dict[tuple[str, str], dict[str, str]] = {}
    for r in read_csv_rows(path):
        out[(r["building_id"], r["input"])] = r
    return out


def load_ref_invalid(repo: Path) -> dict[str, str]:
    invalid = {
        "DEBY_LOD2_42364663": "known_ref_shape_mismatch_flat_lod2_vs_observed_curved_roof",
    }
    for rel in (
        "phases/p0-audit/docs/W3_2c_canonical_paired_status.csv",
        "phases/p0-audit/docs/W2_1c_paired_status.csv",
    ):
        p = repo / rel
        if not p.exists():
            continue
        for r in read_csv_rows(p):
            if str(r.get("reference_mismatch_exclude", "")).lower() in {"true", "1", "yes"}:
                invalid[r["building_id"]] = r.get("reference_mismatch_reason", "reference_mismatch")
    return invalid


def convert_gpkg_to_geojson(gpkg: Path) -> dict:
    cached_candidates = [gpkg.with_suffix(".geojson")]
    if gpkg.name == "footprints_scene_aoi.gpkg":
        cached_candidates.append(gpkg.parent.parent / "w2_city3d" / "footprints_scene_aoi.geojson")
    for cached in cached_candidates:
        if cached.exists():
            return json.loads(cached.read_text(encoding="utf-8"))
    if shutil.which("ogr2ogr") is None:
        tried = ", ".join(str(p) for p in cached_candidates)
        raise FileNotFoundError(f"ogr2ogr not found and cached GeoJSON missing: {tried}")
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "footprints.geojson"
        subprocess.run(["ogr2ogr", "-f", "GeoJSON", str(out), str(gpkg)], check=True)
        return json.loads(out.read_text(encoding="utf-8"))


def load_footprints(gpkg: Path, population: set[str]) -> dict[str, Polygon]:
    data = convert_gpkg_to_geojson(gpkg)
    footprints: dict[str, Polygon] = {}
    for f in data["features"]:
        bid = f["properties"].get("building_id")
        if bid not in population:
            continue
        geom = shape(f["geometry"])
        if not geom.is_valid:
            geom = geom.buffer(0)
        if geom.geom_type == "MultiPolygon":
            geom = max(list(geom.geoms), key=lambda g: g.area)
        footprints[bid] = geom
    missing = sorted(population - set(footprints))
    if missing:
        raise RuntimeError(f"missing footprints for {len(missing)} buildings: {missing[:10]}")
    return footprints


def parse_poslist(text: str) -> np.ndarray | None:
    vals = [float(x) for x in text.split()]
    if len(vals) < 9:
        return None
    if len(vals) % 3 != 0:
        return None
    pts = np.asarray(vals, dtype=np.float64).reshape(-1, 3)
    if len(pts) >= 2 and np.linalg.norm(pts[0] - pts[-1]) < 1e-9:
        pts = pts[:-1]
    if len(pts) < 3:
        return None
    return pts


def surface_from_points(pts: np.ndarray) -> RoofSurface | None:
    poly = Polygon(pts[:, :2])
    if not poly.is_valid:
        poly = poly.buffer(0)
    if poly.is_empty or poly.area <= 0:
        return None
    c = pts.mean(axis=0)
    _, _, vt = np.linalg.svd(pts - c, full_matrices=False)
    n = vt[-1]
    if n[2] < 0:
        n = -n
    return RoofSurface(poly, c, n, float(np.min(pts[:, 2])), float(np.max(pts[:, 2])))


def load_roof_surfaces(gml_dir: Path, population: set[str]) -> dict[str, list[RoofSurface]]:
    ns_gml = "http://www.opengis.net/gml"
    out: dict[str, list[RoofSurface]] = {bid: [] for bid in population}
    remaining = set(population)
    for path in sorted(gml_dir.glob("*.gml")):
        if not remaining:
            break
        tree = etree.parse(str(path))
        for b in tree.xpath(".//*[local-name()='Building']"):
            bid = b.get(f"{{{ns_gml}}}id")
            if bid not in remaining:
                continue
            roofs: list[RoofSurface] = []
            for rs in b.xpath(".//*[local-name()='RoofSurface']"):
                for pos in rs.xpath(".//*[local-name()='posList']"):
                    pts = parse_poslist(pos.text or "")
                    if pts is None:
                        continue
                    surf = surface_from_points(pts)
                    if surf is not None:
                        roofs.append(surf)
            out[bid] = roofs
            remaining.remove(bid)
    return out


def bounds_mask(x: np.ndarray, y: np.ndarray, poly: Polygon, pad: float = 0.0) -> np.ndarray:
    minx, miny, maxx, maxy = poly.bounds
    return (x >= minx - pad) & (x <= maxx + pad) & (y >= miny - pad) & (y <= maxy + pad)


def in_poly_mask(x: np.ndarray, y: np.ndarray, poly: Polygon) -> np.ndarray:
    m = bounds_mask(x, y, poly)
    out = np.zeros(len(x), dtype=bool)
    idx = np.nonzero(m)[0]
    if len(idx):
        out[idx] = contains_xy(poly, x[idx], y[idx])
    return out


def read_las_footprint(path: Path, poly: Polygon) -> tuple[np.ndarray, np.ndarray]:
    las = laspy.read(str(path))
    x = np.asarray(las.x, dtype=np.float64)
    y = np.asarray(las.y, dtype=np.float64)
    z = np.asarray(las.z, dtype=np.float64)
    cls = np.asarray(las.classification, dtype=np.uint8)
    m = in_poly_mask(x, y, poly)
    return np.column_stack([x[m], y[m], z[m]]), cls[m]


class SortedGrid:
    def __init__(self, xy: np.ndarray, cell: float):
        self.xy = xy
        self.cell = float(cell)
        ix = np.floor(xy[:, 0] / self.cell).astype(np.int64)
        iy = np.floor(xy[:, 1] / self.cell).astype(np.int64)
        self.keys = ix * 10_000_000 + iy
        self.order = np.argsort(self.keys)
        sk = self.keys[self.order]
        self.unique, self.starts, self.counts = np.unique(sk, return_index=True, return_counts=True)
        self.lookup = {int(k): (int(s), int(s + c)) for k, s, c in zip(self.unique, self.starts, self.counts)}

    def query_bbox(self, minx: float, miny: float, maxx: float, maxy: float) -> np.ndarray:
        ix0 = math.floor(minx / self.cell)
        ix1 = math.floor(maxx / self.cell)
        iy0 = math.floor(miny / self.cell)
        iy1 = math.floor(maxy / self.cell)
        chunks = []
        for ix in range(ix0, ix1 + 1):
            for iy in range(iy0, iy1 + 1):
                hit = self.lookup.get(int(ix * 10_000_000 + iy))
                if hit is not None:
                    s, e = hit
                    chunks.append(self.order[s:e])
        if not chunks:
            return np.asarray([], dtype=np.int64)
        return np.concatenate(chunks)

    def query_radius(self, x: float, y: float, radius: float) -> np.ndarray:
        idx = self.query_bbox(x - radius, y - radius, x + radius, y + radius)
        if len(idx) == 0:
            return idx
        d2 = (self.xy[idx, 0] - x) ** 2 + (self.xy[idx, 1] - y) ** 2
        return idx[d2 <= radius * radius]


class AcmpFallback:
    def __init__(self, path: Path):
        las = laspy.read(str(path))
        self.x = np.asarray(las.x, dtype=np.float64)
        self.y = np.asarray(las.y, dtype=np.float64)
        self.z = np.asarray(las.z, dtype=np.float64) + ACMP_ORTHO_TO_ELLIP_M
        self.cls = np.asarray(las.classification, dtype=np.uint8)
        self.grid = SortedGrid(np.column_stack([self.x, self.y]), 10.0)
        self.path = path

    def clip(self, poly: Polygon) -> tuple[np.ndarray, np.ndarray]:
        minx, miny, maxx, maxy = poly.bounds
        idx = self.grid.query_bbox(minx, miny, maxx, maxy)
        if len(idx) == 0:
            return np.empty((0, 3), dtype=np.float64), np.empty((0,), dtype=np.uint8)
        m = contains_xy(poly, self.x[idx], self.y[idx])
        idx = idx[m]
        if len(idx) == 0:
            return np.empty((0, 3), dtype=np.float64), np.empty((0,), dtype=np.uint8)
        return np.column_stack([self.x[idx], self.y[idx], self.z[idx]]), self.cls[idx]


def grid_coverage(xy: np.ndarray, poly: Polygon, cell: float) -> tuple[int, int, float, float]:
    minx, miny, maxx, maxy = poly.bounds
    xs = np.arange(minx + cell / 2.0, maxx, cell)
    ys = np.arange(miny + cell / 2.0, maxy, cell)
    if len(xs) == 0 or len(ys) == 0:
        return 0, 0, 0.0, 1.0
    gx, gy = np.meshgrid(xs, ys)
    centers = np.column_stack([gx.ravel(), gy.ravel()])
    inside = contains_xy(poly, centers[:, 0], centers[:, 1])
    inside_centers = centers[inside]
    if len(inside_centers) == 0:
        return 0, 0, 0.0, 1.0
    ix_inside = np.floor((inside_centers[:, 0] - minx) / cell).astype(np.int64)
    iy_inside = np.floor((inside_centers[:, 1] - miny) / cell).astype(np.int64)
    inside_keys = set((ix_inside * 1_000_000 + iy_inside).tolist())
    if len(xy) == 0:
        return len(inside_keys), 0, 0.0, 1.0
    ix = np.floor((xy[:, 0] - minx) / cell).astype(np.int64)
    iy = np.floor((xy[:, 1] - miny) / cell).astype(np.int64)
    pkeys = set((ix * 1_000_000 + iy).tolist())
    occ = len(inside_keys.intersection(pkeys))
    cov = occ / len(inside_keys)
    return len(inside_keys), occ, cov, 1.0 - cov


def deterministic_sample(n: int, max_n: int, seed: int) -> np.ndarray:
    if n <= max_n:
        return np.arange(n, dtype=np.int64)
    rng = np.random.default_rng(seed)
    return np.sort(rng.choice(n, size=max_n, replace=False))


def stable_seed(*parts: str) -> int:
    h = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()
    return int(h[:8], 16)


def fit_plane_rms(points: np.ndarray) -> float | None:
    if len(points) < 3:
        return None
    c = points.mean(axis=0)
    _, _, vt = np.linalg.svd(points - c, full_matrices=False)
    n = vt[-1]
    d = (points - c) @ n
    return float(np.sqrt(np.mean(d * d)))


def local_plane_rms(
    roof_xyz: np.ndarray,
    radius: float,
    min_neighbors: int,
    max_cores: int,
    max_neighbors: int,
    seed: int,
) -> tuple[float | None, int, str]:
    if len(roof_xyz) < min_neighbors:
        return None, 0, "insufficient_roof_points"
    grid = SortedGrid(roof_xyz[:, :2], radius)
    core_idx = deterministic_sample(len(roof_xyz), max_cores, seed)
    rms_vals = []
    for i in core_idx:
        idx = grid.query_radius(float(roof_xyz[i, 0]), float(roof_xyz[i, 1]), radius)
        if len(idx) < min_neighbors:
            continue
        if len(idx) > max_neighbors:
            idx = idx[deterministic_sample(len(idx), max_neighbors, int(i) + seed)]
        r = fit_plane_rms(roof_xyz[idx])
        if r is not None and math.isfinite(r):
            rms_vals.append(r)
    if not rms_vals:
        return None, 0, "insufficient_local_neighborhoods"
    arr = np.asarray(rms_vals, dtype=np.float64)
    return float(np.sqrt(np.mean(arr * arr))), int(len(arr)), "ok"


def local_ref_z(
    x: np.ndarray,
    y: np.ndarray,
    surfaces: list[RoofSurface],
    fallback_ortho_z: float | None,
) -> tuple[np.ndarray | None, float]:
    if len(x) == 0:
        return np.asarray([], dtype=np.float64), 0.0
    if not surfaces and fallback_ortho_z is None:
        return None, 1.0
    zref = np.full(len(x), np.nan, dtype=np.float64)
    for s in surfaces:
        m = contains_xy(s.polygon, x, y)
        if not np.any(m):
            continue
        z = s.z_at(x[m], y[m]) + GEOID_MED_M
        cur = zref[m]
        cur = np.where(np.isnan(cur), z, np.maximum(cur, z))
        zref[m] = cur
    miss = np.isnan(zref)
    miss_frac = float(np.mean(miss))
    if np.any(miss):
        fill = (fallback_ortho_z if fallback_ortho_z is not None else float(np.nanmax(zref) - GEOID_MED_M))
        zref[miss] = fill + GEOID_MED_M
    return zref, miss_frac


def m3c2_against_lidar(
    source_roof: np.ndarray,
    lidar_roof: np.ndarray,
    normal_radius: float,
    proj_radius: float,
    min_neighbors: int,
    max_cores: int,
    seed: int,
) -> tuple[dict[str, float | int | str], str]:
    if len(source_roof) < min_neighbors:
        return {}, "insufficient_source_roof_points"
    if len(lidar_roof) < min_neighbors:
        return {}, "insufficient_lidar_roof_points"
    src_grid = SortedGrid(source_roof[:, :2], proj_radius)
    lid_grid_proj = SortedGrid(lidar_roof[:, :2], proj_radius)
    lid_grid_norm = SortedGrid(lidar_roof[:, :2], normal_radius)
    cores = deterministic_sample(len(lidar_roof), max_cores, seed)
    diffs = []
    for ci in cores:
        core = lidar_roof[ci]
        ni = lid_grid_norm.query_radius(float(core[0]), float(core[1]), normal_radius)
        if len(ni) < min_neighbors:
            continue
        pts = lidar_roof[ni]
        c = pts.mean(axis=0)
        _, _, vt = np.linalg.svd(pts - c, full_matrices=False)
        n = vt[-1]
        if n[2] < 0:
            n = -n
        si = src_grid.query_radius(float(core[0]), float(core[1]), proj_radius)
        li = lid_grid_proj.query_radius(float(core[0]), float(core[1]), proj_radius)
        if len(si) < min_neighbors or len(li) < min_neighbors:
            continue
        ds = (source_roof[si] - core) @ n
        dl = (lidar_roof[li] - core) @ n
        diffs.append(float(np.mean(ds) - np.mean(dl)))
    if not diffs:
        return {}, "insufficient_m3c2_neighborhoods"
    d = np.asarray(diffs, dtype=np.float64)
    return {
        "m3c2_core_count": int(len(d)),
        "m3c2_mean_m": float(np.mean(d)),
        "m3c2_median_abs_m": float(np.median(np.abs(d))),
        "m3c2_rms_m": float(np.sqrt(np.mean(d * d))),
    }, "ok"


def load_arm_points(repo: Path, arm: str, bid: str, poly: Polygon, acmp_fallback: AcmpFallback | None) -> ArmPoints:
    base = repo / f"phases/p0-audit/runs/mob_eval/{arm}/{bid}_orig_classified.las"
    if base.exists():
        xyz, cls = read_las_footprint(base, poly)
        return ArmPoints(
            xyz=xyz,
            cls=cls,
            source="existing_mob_eval_clip",
            path=str(base.relative_to(repo)),
            z_history="ellip-unified existing classified clip",
        )
    if arm == "raw_acmp" and acmp_fallback is not None:
        xyz, cls = acmp_fallback.clip(poly)
        return ArmPoints(
            xyz=xyz,
            cls=cls,
            source="fallback_fused_acmp_footprint_clip",
            path=str(acmp_fallback.path.relative_to(repo)),
            z_history=f"fused ACMP classified LAZ orthometric +{ACMP_ORTHO_TO_ELLIP_M:.1f} m to ellip-unified",
            note="non-persistent fallback because raw_acmp building clip was absent",
        )
    return ArmPoints(
        xyz=np.empty((0, 3), dtype=np.float64),
        cls=np.empty((0,), dtype=np.uint8),
        source="missing_clip",
        path=str(base.relative_to(repo)),
        z_history="none",
        note="building-level clip absent",
    )


def compare_status(row: dict, status: dict[tuple[str, str], dict[str, str]], bid: str, arm: str) -> None:
    source = STATUS_ARM.get(arm)
    row["status_input"] = source or "none"
    if source is None:
        row["status_rf_pt_density"] = None
        row["status_rf_nodata_frac"] = None
        row["status_density_delta"] = None
        row["status_hole_delta"] = None
        row["status_compare_note"] = "no_canonical_status_for_acmp"
        return
    st = status.get((bid, source))
    if st is None:
        row["status_rf_pt_density"] = None
        row["status_rf_nodata_frac"] = None
        row["status_density_delta"] = None
        row["status_hole_delta"] = None
        row["status_compare_note"] = "status_row_missing"
        return
    try:
        sd = float(st["rf_pt_density"])
        sh = float(st["rf_nodata_frac"])
    except Exception:
        row["status_rf_pt_density"] = None
        row["status_rf_nodata_frac"] = None
        row["status_density_delta"] = None
        row["status_hole_delta"] = None
        row["status_compare_note"] = "status_numeric_parse_failed"
        return
    row["status_rf_pt_density"] = sd
    row["status_rf_nodata_frac"] = sh
    row["status_density_delta"] = None if row["pt_density_m2"] is None else row["pt_density_m2"] - sd
    row["status_hole_delta"] = None if row["hole_frac"] is None else row["hole_frac"] - sh
    row["status_compare_note"] = (
        "direct_comparison_same_arm_metric_not_identical_grid" if row["pt_density_m2"] is not None else "metric_none"
    )


def metric_row(
    repo: Path,
    bid: str,
    arm: str,
    poly: Polygon,
    ap: ArmPoints,
    lidar_roof: np.ndarray | None,
    roofs: list[RoofSurface],
    ref_invalid: dict[str, str],
    status: dict[tuple[str, str], dict[str, str]],
    args,
) -> dict:
    xyz = ap.xyz
    cls = ap.cls
    n = int(len(xyz))
    area = float(poly.area)
    row: dict[str, object] = {
        "building_id": bid,
        "arm": arm,
        "clip_source": ap.source,
        "clip_path": ap.path,
        "clip_note": ap.note,
        "crs_xy": "EPSG:25832",
        "z_datum_history": ap.z_history,
        "footprint_area_m2": area,
        "n_points_footprint": n,
        "pt_density_m2": (n / area if area > 0 and n > 0 else None),
        "density_valid": bool(area > 0 and n > 0),
        "density_reason": "ok" if area > 0 and n > 0 else ("missing_clip" if ap.source == "missing_clip" else "no_points"),
        "grid_cell_m": args.grid_cell_m,
    }
    if area > 0:
        cells, occ, cov_raw, hole_raw = grid_coverage(xyz[:, :2], poly, args.grid_cell_m)
        cov = cov_raw if n > 0 else None
        hole = hole_raw if n > 0 else None
    else:
        cells, occ, cov, hole = 0, 0, None, None
    row.update(
        {
            "grid_n_cells": cells,
            "grid_occupied_cells": occ,
            "coverage_frac": cov,
            "hole_frac": hole,
            "coverage_valid": bool(area > 0 and n > 0),
            "coverage_reason": "ok" if area > 0 and n > 0 else ("missing_clip" if ap.source == "missing_clip" else "no_points"),
        }
    )
    compare_status(row, status, bid, arm)

    roof_mask = cls == 6
    ground_mask = cls == 2
    roof_xyz = xyz[roof_mask]
    row["roof_point_count"] = int(len(roof_xyz))
    row["ground_point_count"] = int(np.sum(ground_mask))
    plane, ncores, plane_reason = local_plane_rms(
        roof_xyz,
        args.local_plane_radius_m,
        args.local_plane_min_neighbors,
        args.local_plane_max_cores,
        args.local_plane_max_neighbors,
        seed=stable_seed(bid, arm, "plane"),
    )
    row["local_plane_radius_m"] = args.local_plane_radius_m
    row["local_plane_rms_m"] = plane
    row["local_plane_core_count"] = ncores
    row["local_plane_valid"] = plane_reason == "ok"
    row["local_plane_reason"] = plane_reason

    row["m3c2_normal_radius_m"] = args.m3c2_normal_radius_m
    row["m3c2_proj_radius_m"] = args.m3c2_proj_radius_m
    if arm == "raw_lidar":
        row.update({"m3c2_core_count": None, "m3c2_mean_m": None, "m3c2_median_abs_m": None, "m3c2_rms_m": None})
        row["m3c2_valid"] = False
        row["m3c2_reason"] = "not_applicable_lidar_self"
    elif lidar_roof is None:
        row.update({"m3c2_core_count": None, "m3c2_mean_m": None, "m3c2_median_abs_m": None, "m3c2_rms_m": None})
        row["m3c2_valid"] = False
        row["m3c2_reason"] = "missing_lidar_clip"
    else:
        m3, reason = m3c2_against_lidar(
            roof_xyz,
            lidar_roof,
            args.m3c2_normal_radius_m,
            args.m3c2_proj_radius_m,
            args.m3c2_min_neighbors,
            args.m3c2_max_cores,
            seed=stable_seed(bid, arm, "m3c2"),
        )
        for k in ("m3c2_core_count", "m3c2_mean_m", "m3c2_median_abs_m", "m3c2_rms_m"):
            row[k] = m3.get(k)
        row["m3c2_valid"] = reason == "ok"
        row["m3c2_reason"] = reason

    ref_reason = ref_invalid.get(bid, "")
    row["ref_valid_345"] = not bool(ref_reason)
    row["ref_invalid_reason"] = ref_reason or "none"
    row["ref_roof_surface_count"] = len(roofs)
    fallback_ref_ortho = None
    if roofs:
        fallback_ref_ortho = max(s.z_max for s in roofs)
    zref, miss_frac = local_ref_z(xyz[:, 0], xyz[:, 1], roofs, fallback_ref_ortho)
    row["ref_lookup_miss_frac"] = miss_frac
    row["floater_margin_m"] = args.floater_margin_m
    row["label_proxy_roof_minus_m"] = args.label_proxy_roof_minus_m
    if n == 0:
        row["floater_count"] = 0
        row["floater_frac"] = None
        row["floater_valid"] = False
        row["floater_reason"] = "no_points"
        row["ground_high_count"] = 0
        row["label_proxy_frac_all"] = None
        row["label_proxy_frac_ground"] = None
        row["label_proxy_valid"] = False
        row["label_proxy_reason"] = "no_points"
    elif zref is None:
        row["floater_count"] = None
        row["floater_frac"] = None
        row["floater_valid"] = False
        row["floater_reason"] = "missing_ref_roof"
        row["ground_high_count"] = None
        row["label_proxy_frac_all"] = None
        row["label_proxy_frac_ground"] = None
        row["label_proxy_valid"] = False
        row["label_proxy_reason"] = "missing_ref_roof"
    else:
        floater = xyz[:, 2] > (zref + args.floater_margin_m)
        high_ground = ground_mask & (xyz[:, 2] > (zref - args.label_proxy_roof_minus_m))
        row["floater_count"] = int(np.sum(floater))
        row["floater_frac"] = float(np.mean(floater))
        row["floater_valid"] = True
        row["floater_reason"] = "ok"
        row["ground_high_count"] = int(np.sum(high_ground))
        row["label_proxy_frac_all"] = float(np.sum(high_ground) / n)
        row["label_proxy_frac_ground"] = (
            float(np.sum(high_ground) / np.sum(ground_mask)) if np.sum(ground_mask) > 0 else None
        )
        row["label_proxy_valid"] = True
        row["label_proxy_reason"] = "ok" if np.sum(ground_mask) > 0 else "ok_no_ground_points"
    return row


def numeric_values(rows: list[dict], arm: str, col: str) -> list[float]:
    vals = []
    for r in rows:
        if r["arm"] != arm:
            continue
        v = r.get(col)
        if isinstance(v, (int, float, np.integer, np.floating)) and math.isfinite(float(v)):
            vals.append(float(v))
    return vals


def median_iqr(vals: list[float]) -> tuple[float | None, float | None, float | None]:
    if not vals:
        return None, None, None
    a = np.asarray(vals, dtype=np.float64)
    return float(np.median(a)), float(np.percentile(a, 25)), float(np.percentile(a, 75))


def write_csv(path: Path, rows: list[dict]) -> None:
    fieldnames = [
        "building_id",
        "arm",
        "clip_source",
        "clip_path",
        "clip_note",
        "crs_xy",
        "z_datum_history",
        "footprint_area_m2",
        "n_points_footprint",
        "pt_density_m2",
        "density_valid",
        "density_reason",
        "status_input",
        "status_rf_pt_density",
        "status_density_delta",
        "grid_cell_m",
        "grid_n_cells",
        "grid_occupied_cells",
        "coverage_frac",
        "hole_frac",
        "coverage_valid",
        "coverage_reason",
        "status_rf_nodata_frac",
        "status_hole_delta",
        "status_compare_note",
        "roof_point_count",
        "ground_point_count",
        "local_plane_radius_m",
        "local_plane_rms_m",
        "local_plane_core_count",
        "local_plane_valid",
        "local_plane_reason",
        "m3c2_normal_radius_m",
        "m3c2_proj_radius_m",
        "m3c2_core_count",
        "m3c2_mean_m",
        "m3c2_median_abs_m",
        "m3c2_rms_m",
        "m3c2_valid",
        "m3c2_reason",
        "ref_valid_345",
        "ref_invalid_reason",
        "ref_roof_surface_count",
        "ref_lookup_miss_frac",
        "floater_margin_m",
        "floater_count",
        "floater_frac",
        "floater_valid",
        "floater_reason",
        "label_proxy_roof_minus_m",
        "ground_high_count",
        "label_proxy_frac_all",
        "label_proxy_frac_ground",
        "label_proxy_valid",
        "label_proxy_reason",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow({k: fmt(r.get(k)) for k in fieldnames})


def plot_distributions(rows: list[dict], out: Path) -> None:
    metrics = [
        ("pt_density_m2", "density pt/m2", True),
        ("coverage_frac", "0.5 m coverage", False),
        ("local_plane_rms_m", "local plane RMS m", True),
        ("floater_frac", "floater fraction", True),
        ("label_proxy_frac_all", "ground-high fraction", True),
    ]
    fig, axes = plt.subplots(1, len(metrics), figsize=(16, 4.2))
    colors = {"raw_dense": "#0072B2", "raw_acmp": "#D55E00", "raw_lidar": "#009E73"}
    for ax, (col, title, logy) in zip(axes, metrics):
        data = [numeric_values(rows, arm, col) for arm in ARMS]
        data = [d if d else [np.nan] for d in data]
        bp = ax.boxplot(data, tick_labels=["DIM", "ACMP", "LiDAR"], patch_artist=True, showfliers=False)
        for patch, arm in zip(bp["boxes"], ARMS):
            patch.set_facecolor(colors[arm])
            patch.set_alpha(0.55)
        ax.set_title(title)
        ax.grid(True, axis="y", alpha=0.25)
        if logy:
            positive = [v for d in data for v in d if isinstance(v, (float, int)) and v > 0 and math.isfinite(v)]
            if positive:
                ax.set_yscale("log")
    fig.tight_layout()
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=180)
    plt.close(fig)


def plot_als_scatter(rows: list[dict], out: Path) -> None:
    by = {(r["building_id"], r["arm"]): r for r in rows}
    metrics = [
        ("pt_density_m2", "density pt/m2", True),
        ("coverage_frac", "coverage", False),
        ("local_plane_rms_m", "local RMS m", True),
    ]
    fig, axes = plt.subplots(1, 3, figsize=(12, 4))
    colors = {"raw_dense": "#0072B2", "raw_acmp": "#D55E00"}
    for ax, (col, title, logxy) in zip(axes, metrics):
        maxv = 0.0
        for arm, label in [("raw_dense", "DIM"), ("raw_acmp", "ACMP")]:
            xs, ys = [], []
            for (bid, a), r in by.items():
                if a != arm:
                    continue
                lr = by.get((bid, "raw_lidar"))
                if lr is None:
                    continue
                x = lr.get(col)
                y = r.get(col)
                if isinstance(x, (int, float)) and isinstance(y, (int, float)) and x > 0 and y > 0:
                    xs.append(float(x))
                    ys.append(float(y))
                    maxv = max(maxv, float(x), float(y))
            ax.scatter(xs, ys, s=16, alpha=0.65, label=f"{label} vs LiDAR", color=colors[arm])
        if maxv > 0:
            ax.plot([0, maxv], [0, maxv], color="0.3", lw=1, ls="--")
        ax.set_title(title)
        ax.set_xlabel("LiDAR")
        ax.set_ylabel("raw arm")
        ax.grid(True, alpha=0.25)
        if logxy:
            ax.set_xscale("log")
            ax.set_yscale("log")
        ax.legend(fontsize=8)
    fig.tight_layout()
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=180)
    plt.close(fig)


def make_summary_table(rows: list[dict]) -> list[tuple[str, str, int, float | None, float | None, float | None]]:
    metrics = [
        ("밀도 pt/m2", "pt_density_m2"),
        ("완전성 coverage", "coverage_frac"),
        ("노이즈 local RMS m", "local_plane_rms_m"),
        ("M3C2 RMS m", "m3c2_rms_m"),
        ("부유점 fraction", "floater_frac"),
        ("라벨 프록시 fraction", "label_proxy_frac_all"),
    ]
    table = []
    for label, col in metrics:
        for arm in ARMS:
            vals = numeric_values(rows, arm, col)
            med, q1, q3 = median_iqr(vals)
            table.append((label, arm, len(vals), med, q1, q3))
    return table


def write_report(path: Path, rows: list[dict], args, provenance: dict[str, str]) -> None:
    table = make_summary_table(rows)
    clip_counts = defaultdict(int)
    for r in rows:
        clip_counts[(r["arm"], r["clip_source"])] += 1
    lines = [
        "# W pointcloud attributes v1",
        "",
        "> 재구성/재학습 없음. 이미지-투영 불사용. 수치와 관찰만 기록한다.",
        "",
        "## 입력·규약",
        "",
        f"- 모집단: `docs/experiments/input-and-alignment/population_aux/tables/population_aux_v4.csv`의 199동 전수, arm 3종 = raw_dense(DIM) · raw_acmp · raw_lidar(상한).",
        f"- Footprint: `{args.footprints}` (EPSG:25832, 199 features).",
        f"- Status 대조: `{provenance['status_path']}` ({provenance['status_note']}).",
        f"- 기존 클립: `phases/p0-audit/runs/mob_eval/raw_{{dense,acmp,lidar}}/<ID>_orig_classified.las`.",
        f"- ACMP 결측 fallback: `{args.acmp_fallback_laz}`에서 footprint 내부를 읽고 Z에 +{ACMP_ORTHO_TO_ELLIP_M:.1f} m를 더해 ellip-unified raw arm 이력에 맞췄다. fallback은 CSV의 `clip_source`에 표시했다.",
        f"- LoD2 지붕면 Z는 정표고로 읽고, ③④⑤의 점-참조 높이 비교에서만 +{GEOID_MED_M:.3f} m를 더했다.",
        f"- 채택값: grid={args.grid_cell_m} m, local plane radius={args.local_plane_radius_m} m, M3C2 normal/projection radius={args.m3c2_normal_radius_m}/{args.m3c2_proj_radius_m} m, 부유점 여유={args.floater_margin_m} m, 라벨 프록시=참조 지붕高-{args.label_proxy_roof_minus_m} m 위 ground(2).",
        "",
        "## 클립 출처",
        "",
        "| arm | source | n_rows |",
        "|---|---|---:|",
    ]
    for arm in ARMS:
        for source in sorted({s for (a, s) in clip_counts if a == arm}):
            lines.append(f"| {arm} | {source} | {clip_counts[(arm, source)]} |")
    lines += [
        "",
        "## 축별·arm별 분포",
        "",
        "| 축 | arm | n | median | IQR |",
        "|---|---|---:|---:|---:|",
    ]
    for label, arm, n, med, q1, q3 in table:
        iqr = "none" if q1 is None else f"{q1:.4g}–{q3:.4g}"
        lines.append(f"| {label} | {arm} | {n} | {fmt(med, 4)} | {iqr} |")
    lines += [
        "",
        "## 그림",
        "",
        "- Arm 대조 분포: `docs/figs/pointcloud_attributes_v1/arm_distribution.png`",
        "- ALS 대비 산점: `docs/figs/pointcloud_attributes_v1/als_scatter.png`",
        "",
        "## 관찰",
        "",
    ]
    for col, text in [
        ("pt_density_m2", "밀도"),
        ("coverage_frac", "0.5 m 격자 점유율"),
        ("local_plane_rms_m", "국소 평면 RMS"),
        ("floater_frac", "부유점 비율"),
        ("label_proxy_frac_all", "라벨 프록시 비율"),
    ]:
        vals = {arm: median_iqr(numeric_values(rows, arm, col))[0] for arm in ARMS}
        lines.append(
            f"- {text}: median raw_dense={fmt(vals['raw_dense'], 4)}, raw_acmp={fmt(vals['raw_acmp'], 4)}, raw_lidar={fmt(vals['raw_lidar'], 4)}."
        )
    ref_invalid_rows = sorted({r["building_id"] for r in rows if not r["ref_valid_345"]})
    lines.append(f"- ref_invalid 플래그가 켜진 건물: {', '.join(ref_invalid_rows) if ref_invalid_rows else 'none'}.")
    missing = {arm: clip_counts[(arm, "missing_clip")] for arm in ARMS}
    lines.append(
        f"- missing_clip 행: raw_dense={missing['raw_dense']}, raw_acmp={missing['raw_acmp']}, raw_lidar={missing['raw_lidar']}."
    )
    lines += [
        "",
        "## 판정 필요 지점",
        "",
        "- 부유점 여유 3 m를 유지할지, arm별 z-noise를 반영해 조정할지.",
        "- 라벨 프록시를 전체 점 대비 비율로 둘지 ground(2) 내부 비율로 둘지.",
        "- `none` 처리 행을 회귀에서 결측으로 둘지, arm 결측 자체를 설명변수로 둘지.",
        "- 회귀 사양: 199동 전수 분모를 유지하되 분석 단계에서 층화·제외·ref_invalid 처리 방식을 정할지.",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_versions(path: Path, args, provenance: dict[str, str], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    def cmd_out(cmd: list[str]) -> str:
        try:
            r = subprocess.run(cmd, capture_output=True, text=True)
        except FileNotFoundError as e:
            return f"not_available:{e.filename}"
        return (r.stdout or r.stderr).strip()
    clip_counts = defaultdict(int)
    for r in rows:
        clip_counts[(r["arm"], r["clip_source"])] += 1
    lines = [
        f"run_id: {RUN_ID}",
        f"created_utc: {datetime.now(timezone.utc).isoformat()}",
        "task: attr-v1",
        "mode: observation only; no reconstruction; no retraining; no image projection",
        f"git_head: {cmd_out(['git', 'rev-parse', 'HEAD'])}",
        f"git_branch: {cmd_out(['git', 'branch', '--show-current'])}",
        f"docker_image: jointbuildgs-p0-tools:t0",
        'run_command: docker run --rm --user "$(id -u):$(id -g)" -v "$PWD":/workspace/JointBuildGS -w /workspace/JointBuildGS jointbuildgs-p0-tools:t0 python3 scripts/evidence_and_attributes/p2_gsjso/pointcloud_attributes_v1.py',
        "docker_image_id: recorded by host command in execution log; docker CLI not required inside container",
        f"python: {cmd_out(['python3', '--version'])}",
        f"pdal: {cmd_out(['pdal', '--version'])}",
        "",
        "inputs:",
        f"  population: {args.population}",
        f"  status_requested: {args.status}",
        f"  status_used: {provenance['status_path']}",
        f"  status_note: {provenance['status_note']}",
        f"  footprints: {args.footprints}",
        f"  lod2_gml_dir: {args.lod2_gml_dir}",
        f"  raw_clip_dirs: phases/p0-audit/runs/mob_eval/raw_{{dense,acmp,lidar}}",
        f"  acmp_fallback_laz: {args.acmp_fallback_laz}",
        "",
        "parameters:",
        f"  grid_cell_m: {args.grid_cell_m}",
        f"  local_plane_radius_m: {args.local_plane_radius_m}",
        f"  local_plane_min_neighbors: {args.local_plane_min_neighbors}",
        f"  local_plane_max_cores: {args.local_plane_max_cores}",
        f"  m3c2_normal_radius_m: {args.m3c2_normal_radius_m}",
        f"  m3c2_proj_radius_m: {args.m3c2_proj_radius_m}",
        f"  m3c2_min_neighbors: {args.m3c2_min_neighbors}",
        f"  m3c2_max_cores: {args.m3c2_max_cores}",
        f"  floater_margin_m: {args.floater_margin_m}",
        f"  label_proxy_roof_minus_m: {args.label_proxy_roof_minus_m}",
        f"  ref_ortho_to_ellip_m: {GEOID_MED_M}",
        f"  acmp_fallback_ortho_to_ellip_m: {ACMP_ORTHO_TO_ELLIP_M}",
        "",
        "clip_source_counts:",
    ]
    for arm in ARMS:
        for source in sorted({s for (a, s) in clip_counts if a == arm}):
            lines.append(f"  {arm}.{source}: {clip_counts[(arm, source)]}")
    lines += [
        "",
        "outputs:",
        "  docs/archive/pointcloud_attributes/v1/tables/pointcloud_attributes_v1.csv",
        "  docs/experiments/input-and-alignment/pointcloud_attributes/reports/W_pointcloud_attributes.md",
        "  docs/figs/pointcloud_attributes_v1/arm_distribution.png",
        "  docs/figs/pointcloud_attributes_v1/als_scatter.png",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_argparser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser()
    ap.add_argument("--population", default="docs/experiments/input-and-alignment/population_aux/tables/population_aux_v4.csv")
    ap.add_argument("--status", default="docs/building_reconstruction_status.csv")
    ap.add_argument("--footprints", default="phases/p0-audit/data/work/w2/footprints_scene_aoi.gpkg")
    ap.add_argument("--lod2-gml-dir", default="phases/p0-audit/data/raw/lod2")
    ap.add_argument("--acmp-fallback-laz", default="results/tum_transfer/mob_analysis/p0c_step2/acmp_classified.laz")
    ap.add_argument("--out-csv", default="docs/archive/pointcloud_attributes/v1/tables/pointcloud_attributes_v1.csv")
    ap.add_argument("--out-report", default="docs/experiments/input-and-alignment/pointcloud_attributes/reports/W_pointcloud_attributes.md")
    ap.add_argument("--fig-dir", default="docs/figs/pointcloud_attributes_v1")
    ap.add_argument("--versions", default=f"phases/p2-gsjso/runs/{RUN_ID}/versions.txt")
    ap.add_argument("--grid-cell-m", type=float, default=0.5)
    ap.add_argument("--local-plane-radius-m", type=float, default=0.75)
    ap.add_argument("--local-plane-min-neighbors", type=int, default=10)
    ap.add_argument("--local-plane-max-cores", type=int, default=3000)
    ap.add_argument("--local-plane-max-neighbors", type=int, default=256)
    ap.add_argument("--m3c2-normal-radius-m", type=float, default=1.0)
    ap.add_argument("--m3c2-proj-radius-m", type=float, default=0.75)
    ap.add_argument("--m3c2-min-neighbors", type=int, default=8)
    ap.add_argument("--m3c2-max-cores", type=int, default=2500)
    ap.add_argument("--floater-margin-m", type=float, default=3.0)
    ap.add_argument("--label-proxy-roof-minus-m", type=float, default=1.0)
    return ap


def main() -> None:
    args = build_argparser().parse_args()
    repo = Path.cwd()
    pop_path = repo / args.population
    pop = read_population(pop_path)
    pop_set = set(pop)
    st_path, st_note = status_path(repo, repo / args.status)
    status = load_status(st_path)
    provenance = {"status_path": str(st_path.relative_to(repo)), "status_note": st_note}
    footprints = load_footprints(repo / args.footprints, pop_set)
    roofs = load_roof_surfaces(repo / args.lod2_gml_dir, pop_set)
    ref_invalid = load_ref_invalid(repo)

    missing_acmp = [
        bid
        for bid in pop
        if not (repo / f"phases/p0-audit/runs/mob_eval/raw_acmp/{bid}_orig_classified.las").exists()
    ]
    acmp_fb = None
    if missing_acmp:
        acmp_fb = AcmpFallback(repo / args.acmp_fallback_laz)

    rows: list[dict] = []
    for i, bid in enumerate(pop, 1):
        poly = footprints[bid]
        arm_points = {arm: load_arm_points(repo, arm, bid, poly, acmp_fb) for arm in ARMS}
        lidar_roof = arm_points["raw_lidar"].xyz[arm_points["raw_lidar"].cls == 6]
        lidar_roof_for_m3c2 = lidar_roof if len(lidar_roof) else None
        for arm in ARMS:
            rows.append(
                metric_row(
                    repo,
                    bid,
                    arm,
                    poly,
                    arm_points[arm],
                    lidar_roof_for_m3c2,
                    roofs.get(bid, []),
                    ref_invalid,
                    status,
                    args,
                )
            )
        if i % 25 == 0 or i == len(pop):
            print(f"[attr-v1] processed {i}/{len(pop)} buildings", flush=True)

    out_csv = repo / args.out_csv
    write_csv(out_csv, rows)
    fig_dir = repo / args.fig_dir
    plot_distributions(rows, fig_dir / "arm_distribution.png")
    plot_als_scatter(rows, fig_dir / "als_scatter.png")
    write_report(repo / args.out_report, rows, args, provenance)
    write_versions(repo / args.versions, args, provenance, rows)
    print(f"[done] rows={len(rows)} -> {args.out_csv}")


if __name__ == "__main__":
    main()
