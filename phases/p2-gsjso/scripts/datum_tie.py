#!/usr/bin/env python3
"""Datum-tie v3: point-cloud-to-point-cloud height comparison.

No image matching, no edge/corner correspondence, no reconstruction/training.
The measurement compares raw image-derived dense points against ALS on the same
ground/roof surfaces:

    delta = dense_camera_height - (ALS_DHHN2016_height + GCG2016_AOI)

Outputs are written to docs/ plus a run directory with versions.txt.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import laspy
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.path import Path as MplPath
import numpy as np
from shapely.geometry import Polygon, shape


ROOT = Path("/workspace/JointBuildGS")
ALS_AOI = ROOT / "results/tum_transfer/mob_analysis/p0c_step2/als_aoi.laz"
RAW_DENSE = ROOT / "results/tum_transfer/mob/raw/raw_dense.npz"
RAW_VERSIONS = ROOT / "results/tum_transfer/mob/raw/versions.txt"
RAW_SCRIPT = ROOT / "phases/p2-gsjso/scripts/tum_mob_raw_to_npz.py"
FOOTPRINTS = ROOT / "results/tum_transfer/analysis/footprints_aoi.geojson"
STATUS_114 = ROOT / "phases/p0-audit/runs/w2_1d_bucket_relabel_20260612_final/docs/W2_1c_paired_status.csv"
GCG_GRID = ROOT / "phases/p0-audit/data/raw/geoid/de_bkg_gcg2016.tif"
DOC = ROOT / "docs/experiments/datum_tie/reports/datum_tie.md"
CSV_OUT = ROOT / "docs/experiments/datum_tie/tables/datum_tie_patches.csv"
FIG_DIR = ROOT / "docs/figs/datum_tie"

AOI_LON = 11.568962805555556
AOI_LAT = 48.14969263888889


@dataclass
class PatchRow:
    patch_id: str
    surface_type: str
    building_id: str
    x_m: float
    y_m: float
    patch_size_m: float
    n_als: int
    n_dense: int
    n_als_used: int
    n_dense_used: int
    als_orthometric_m: float
    als_plus_gcg_m: float
    dense_camera_m: float
    delta_m: float
    als_mad_m: float
    dense_mad_m: float
    slope_deg: float | None
    icp_dx_m: float | None = None
    icp_dy_m: float | None = None
    note: str = ""


class XIndex:
    def __init__(self, xyz: np.ndarray, cls: np.ndarray | None = None) -> None:
        order = np.argsort(xyz[:, 0], kind="mergesort")
        self.x = np.asarray(xyz[order, 0], dtype=np.float64)
        self.y = np.asarray(xyz[order, 1], dtype=np.float64)
        self.z = np.asarray(xyz[order, 2], dtype=np.float64)
        self.cls = None if cls is None else np.asarray(cls[order], dtype=np.uint8)
        self.bounds = (
            float(self.x.min()),
            float(self.y.min()),
            float(self.x.max()),
            float(self.y.max()),
        )

    def query_box(
        self,
        xmin: float,
        ymin: float,
        xmax: float,
        ymax: float,
        classification: int | None = None,
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray | None]:
        lo = int(np.searchsorted(self.x, xmin, side="left"))
        hi = int(np.searchsorted(self.x, xmax, side="right"))
        y = self.y[lo:hi]
        mask = (y >= ymin) & (y <= ymax)
        if classification is not None:
            if self.cls is None:
                raise ValueError("classification filter requested for unclassified cloud")
            mask &= self.cls[lo:hi] == classification
        cls = None if self.cls is None else self.cls[lo:hi][mask]
        return self.x[lo:hi][mask], y[mask], self.z[lo:hi][mask], cls


def fmt(v: Any, nd: int = 3) -> str:
    if v is None:
        return ""
    if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
        return ""
    if isinstance(v, (float, np.floating)):
        return f"{float(v):.{nd}f}"
    return str(v)


def mad(z: np.ndarray) -> float:
    z = np.asarray(z, dtype=np.float64)
    if z.size == 0:
        return float("nan")
    m = float(np.median(z))
    return float(np.median(np.abs(z - m)))


def densest_mode_height(
    z: np.ndarray,
    *,
    bin_width: float = 0.25,
    radius: float = 0.75,
    expected: float | None = None,
    expected_radius: float = 6.0,
    lower_fraction: float | None = None,
    upper_fraction: float | None = None,
    min_used: int = 30,
) -> tuple[float, float, int, float]:
    z = np.asarray(z, dtype=np.float64)
    z = z[np.isfinite(z)]
    if expected is not None:
        zw = z[(z >= expected - expected_radius) & (z <= expected + expected_radius)]
        if zw.size >= min_used:
            z = zw
    if lower_fraction is not None and 0.0 < lower_fraction < 1.0 and z.size >= min_used:
        q = float(np.quantile(z, lower_fraction))
        zl = z[z <= q]
        if zl.size >= min_used:
            z = zl
    if upper_fraction is not None and 0.0 < upper_fraction < 1.0 and z.size >= min_used:
        q = float(np.quantile(z, upper_fraction))
        zu = z[z >= q]
        if zu.size >= min_used:
            z = zu
    if z.size < min_used:
        raise ValueError(f"insufficient points for mode height: {z.size} < {min_used}")
    zmin = float(np.min(z))
    zmax = float(np.max(z))
    if zmax - zmin < bin_width:
        used = z
        return float(np.median(used)), mad(used), int(used.size), float(np.median(used))
    bins = np.arange(math.floor(zmin / bin_width) * bin_width, zmax + 2 * bin_width, bin_width)
    hist, edges = np.histogram(z, bins=bins)
    idx = int(np.argmax(hist))
    center = float((edges[idx] + edges[idx + 1]) * 0.5)
    used = z[(z >= center - radius) & (z <= center + radius)]
    if used.size < min_used:
        used = z[(z >= center - 2 * radius) & (z <= center + 2 * radius)]
    if used.size < min_used:
        used = z
    return float(np.median(used)), mad(used), int(used.size), center


def fit_slope_deg(x: np.ndarray, y: np.ndarray, z: np.ndarray) -> float:
    x0 = x - float(np.mean(x))
    y0 = y - float(np.mean(y))
    A = np.column_stack([x0, y0, np.ones_like(x0)])
    a, b, _ = np.linalg.lstsq(A, z, rcond=None)[0]
    return float(math.degrees(math.atan(math.sqrt(a * a + b * b))))


def read_als_index() -> XIndex:
    las = laspy.read(ALS_AOI)
    xyz = np.column_stack(
        [
            np.asarray(las.x, dtype=np.float64),
            np.asarray(las.y, dtype=np.float64),
            np.asarray(las.z, dtype=np.float64),
        ]
    )
    cls = np.asarray(las.classification, dtype=np.uint8)
    return XIndex(xyz, cls)


def read_dense_index() -> XIndex:
    with np.load(RAW_DENSE) as data:
        xyz = np.asarray(data["P_utm"], dtype=np.float64)
    return XIndex(xyz)


def load_footprints() -> dict[str, Polygon]:
    data = json.loads(FOOTPRINTS.read_text())
    out: dict[str, Polygon] = {}
    for feat in data["features"]:
        bid = str(feat["properties"]["building_id"])
        geom = shape(feat["geometry"])
        if geom.geom_type == "Polygon":
            out[bid] = geom
        elif geom.geom_type == "MultiPolygon":
            out[bid] = max(list(geom.geoms), key=lambda g: g.area)
    return out


def load_dense_success_114() -> set[str]:
    out: set[str] = set()
    with STATUS_114.open(newline="") as f:
        for row in csv.DictReader(f):
            if row.get("als_has_lod22") == "True" and row.get("dim_has_lod22") == "True":
                out.add(row["building_id"])
    return out


def polygon_mask(poly: Polygon, x: np.ndarray, y: np.ndarray) -> np.ndarray:
    coords = np.asarray(poly.exterior.coords, dtype=np.float64)
    path = MplPath(coords)
    pts = np.column_stack([x, y])
    return path.contains_points(pts, radius=1e-9)


def candidate_ground_cells(als: XIndex, cell: float) -> list[tuple[float, float]]:
    xmin, ymin, xmax, ymax = als.bounds
    xg, yg, zg, cls = als.query_box(xmin, ymin, xmax, ymax, classification=2)
    ix = np.floor((xg - xmin) / cell).astype(np.int64)
    iy = np.floor((yg - ymin) / cell).astype(np.int64)
    n_y = int(math.ceil((ymax - ymin) / cell)) + 1
    key = ix * n_y + iy
    uniq, counts = np.unique(key, return_counts=True)
    good = uniq[counts >= 60]
    centers: list[tuple[float, float]] = []
    for k in good:
        cx = xmin + (int(k // n_y) + 0.5) * cell
        cy = ymin + (int(k % n_y) + 0.5) * cell
        centers.append((float(cx), float(cy)))
    return centers


def select_spatially(rows: list[PatchRow], target: int, bins: int = 5, quality_key=None) -> list[PatchRow]:
    if len(rows) <= target:
        return rows
    if quality_key is None:
        quality_key = lambda r: (r.dense_mad_m, r.als_mad_m, -min(r.n_dense, r.n_als))
    xs = np.array([r.x_m for r in rows])
    ys = np.array([r.y_m for r in rows])
    x0, x1 = float(xs.min()), float(xs.max())
    y0, y1 = float(ys.min()), float(ys.max())
    used: set[int] = set()
    selected: list[PatchRow] = []
    by_bin: dict[tuple[int, int], list[int]] = {}
    for i, r in enumerate(rows):
        bx = min(bins - 1, max(0, int((r.x_m - x0) / max(x1 - x0, 1e-6) * bins)))
        by = min(bins - 1, max(0, int((r.y_m - y0) / max(y1 - y0, 1e-6) * bins)))
        by_bin.setdefault((bx, by), []).append(i)
    for bin_key in sorted(by_bin):
        idxs = sorted(by_bin[bin_key], key=lambda i: quality_key(rows[i]))
        if idxs and len(selected) < target:
            selected.append(rows[idxs[0]])
            used.add(idxs[0])
    if len(selected) < target:
        for i in sorted(range(len(rows)), key=lambda j: quality_key(rows[j])):
            if i not in used:
                selected.append(rows[i])
                used.add(i)
                if len(selected) >= target:
                    break
    return selected[:target]


def measure_ground(als: XIndex, dense: XIndex, gcg_m: float, target: int) -> list[PatchRow]:
    cell = 5.0
    candidates = candidate_ground_cells(als, cell)
    rows: list[PatchRow] = []
    for cx, cy in candidates:
        xmin, xmax = cx - cell / 2, cx + cell / 2
        ymin, ymax = cy - cell / 2, cy + cell / 2
        ax, ay, az, _ = als.query_box(xmin, ymin, xmax, ymax, classification=2)
        bx, by, bz, _ = als.query_box(xmin, ymin, xmax, ymax, classification=6)
        if az.size < 60 or bz.size > 5:
            continue
        slope = fit_slope_deg(ax, ay, az)
        if slope >= 3.0:
            continue
        als_h = float(np.median(az))
        expected = als_h + gcg_m
        dx, dy, dz, _ = dense.query_box(xmin, ymin, xmax, ymax)
        if dz.size < 80:
            continue
        try:
            dense_h, dense_mad, n_dense_used, _ = densest_mode_height(
                dz,
                expected=expected,
                expected_radius=4.0,
                lower_fraction=0.55,
                upper_fraction=None,
                min_used=40,
            )
        except ValueError:
            continue
        if dense_mad > 0.35:
            continue
        rows.append(
            PatchRow(
                patch_id=f"G{len(rows)+1:03d}",
                surface_type="ground",
                building_id="",
                x_m=cx,
                y_m=cy,
                patch_size_m=cell,
                n_als=int(az.size),
                n_dense=int(dz.size),
                n_als_used=int(az.size),
                n_dense_used=n_dense_used,
                als_orthometric_m=als_h,
                als_plus_gcg_m=expected,
                dense_camera_m=dense_h,
                delta_m=dense_h - expected,
                als_mad_m=mad(az),
                dense_mad_m=dense_mad,
                slope_deg=slope,
                note="ALS class-2, slope<3deg, no class-6 in 5x5m cell; dense lower mode",
            )
        )
    ground_quality = lambda r: (r.slope_deg or 99.0, r.dense_mad_m, r.als_mad_m, -r.n_dense)
    rows = sorted(rows, key=ground_quality)
    rows = select_spatially(rows, target=target, bins=6, quality_key=ground_quality)
    for i, row in enumerate(rows, 1):
        row.patch_id = f"G{i:03d}"
    return rows


def roof_inner(poly: Polygon) -> Polygon:
    for inward in (1.5, 1.0, 0.5, 0.0):
        p = poly if inward == 0.0 else poly.buffer(-inward)
        if not p.is_empty and p.area >= 5.0:
            if p.geom_type == "MultiPolygon":
                p = max(list(p.geoms), key=lambda g: g.area)
            return p
    return poly


def roof_icp_xy(dense_xy: np.ndarray, als_xy: np.ndarray, max_points: int = 1200) -> tuple[float, float]:
    if dense_xy.shape[0] < 20 or als_xy.shape[0] < 20:
        return float("nan"), float("nan")
    if dense_xy.shape[0] > max_points:
        dense_xy = dense_xy[np.linspace(0, dense_xy.shape[0] - 1, max_points).astype(int)]
    if als_xy.shape[0] > max_points:
        als_xy = als_xy[np.linspace(0, als_xy.shape[0] - 1, max_points).astype(int)]
    trans = np.zeros(2, dtype=np.float64)
    for _ in range(5):
        moved = dense_xy - trans
        deltas = []
        for start in range(0, moved.shape[0], 200):
            chunk = moved[start : start + 200]
            d2 = ((chunk[:, None, :] - als_xy[None, :, :]) ** 2).sum(axis=2)
            nn = als_xy[np.argmin(d2, axis=1)]
            deltas.append(chunk - nn)
        step = np.median(np.vstack(deltas), axis=0)
        trans += step
        if float(np.linalg.norm(step)) < 0.005:
            break
    return float(trans[0]), float(trans[1])


def measure_roofs(
    als: XIndex,
    dense: XIndex,
    footprints: dict[str, Polygon],
    success_114: set[str],
    gcg_m: float,
    target: int,
) -> list[PatchRow]:
    rows: list[PatchRow] = []
    for bid in sorted(success_114):
        poly0 = footprints.get(bid)
        if poly0 is None:
            continue
        poly = roof_inner(poly0)
        xmin, ymin, xmax, ymax = poly.bounds
        ax, ay, az, ac = als.query_box(xmin, ymin, xmax, ymax, classification=6)
        if az.size < 80:
            continue
        amask = polygon_mask(poly, ax, ay)
        ax, ay, az = ax[amask], ay[amask], az[amask]
        if az.size < 80:
            continue
        try:
            als_h, als_mad, n_als_used, _ = densest_mode_height(
                az,
                upper_fraction=0.60,
                min_used=50,
            )
        except ValueError:
            continue
        expected = als_h + gcg_m
        dx, dy, dz, _ = dense.query_box(xmin, ymin, xmax, ymax)
        if dz.size < 100:
            continue
        dmask = polygon_mask(poly, dx, dy)
        dx, dy, dz = dx[dmask], dy[dmask], dz[dmask]
        if dz.size < 100:
            continue
        try:
            dense_h, dense_mad, n_dense_used, _ = densest_mode_height(
                dz,
                expected=expected,
                expected_radius=6.0,
                upper_fraction=0.50,
                min_used=60,
            )
        except ValueError:
            continue
        if dense_mad > 1.2 or als_mad > 1.2:
            continue
        c = poly.centroid
        rows.append(
            PatchRow(
                patch_id=f"R{len(rows)+1:03d}",
                surface_type="roof",
                building_id=bid,
                x_m=float(c.x),
                y_m=float(c.y),
                patch_size_m=0.0,
                n_als=int(az.size),
                n_dense=int(dz.size),
                n_als_used=n_als_used,
                n_dense_used=n_dense_used,
                als_orthometric_m=als_h,
                als_plus_gcg_m=expected,
                dense_camera_m=dense_h,
                delta_m=dense_h - expected,
                als_mad_m=als_mad,
                dense_mad_m=dense_mad,
                slope_deg=None,
                note="dense success group 114(has_lod22); inward footprint; ALS class-6 upper mode",
            )
        )
    roof_quality = lambda r: (r.dense_mad_m, r.als_mad_m, -min(r.n_dense, r.n_als))
    rows = sorted(rows, key=roof_quality)
    rows = select_spatially(rows, target=target, bins=5, quality_key=roof_quality)
    for i, row in enumerate(rows, 1):
        row.patch_id = f"R{i:03d}"

    for row in rows[:3]:
        poly = roof_inner(footprints[row.building_id])
        xmin, ymin, xmax, ymax = poly.bounds
        ax, ay, az, _ = als.query_box(xmin, ymin, xmax, ymax, classification=6)
        amask = polygon_mask(poly, ax, ay)
        ax, ay, az = ax[amask], ay[amask], az[amask]
        dx, dy, dz, _ = dense.query_box(xmin, ymin, xmax, ymax)
        dmask = polygon_mask(poly, dx, dy)
        dx, dy, dz = dx[dmask], dy[dmask], dz[dmask]
        als_top = np.abs((az + gcg_m) - row.als_plus_gcg_m) <= max(0.75, 3 * row.als_mad_m)
        dense_top = np.abs(dz - row.dense_camera_m) <= max(0.75, 3 * row.dense_mad_m)
        row.icp_dx_m, row.icp_dy_m = roof_icp_xy(
            np.column_stack([dx[dense_top], dy[dense_top]]),
            np.column_stack([ax[als_top], ay[als_top]]),
        )
    return rows


def linear_trend(rows: list[PatchRow], mask: np.ndarray | None = None) -> dict[str, float]:
    selected = rows if mask is None else [r for r, keep in zip(rows, mask) if bool(keep)]
    x = np.array([r.x_m for r in selected], dtype=np.float64)
    y = np.array([r.y_m for r in selected], dtype=np.float64)
    d = np.array([r.delta_m for r in selected], dtype=np.float64)
    if d.size < 3:
        return {
            "n": int(d.size),
            "slope_east_m_per_100m": float("nan"),
            "slope_north_m_per_100m": float("nan"),
            "intercept_m": float("nan"),
            "predicted_span_m": float("nan"),
            "r2": float("nan"),
        }
    x0, y0 = float(np.mean(x)), float(np.mean(y))
    A = np.column_stack([(x - x0) / 100.0, (y - y0) / 100.0, np.ones_like(x)])
    sx, sy, c = np.linalg.lstsq(A, d, rcond=None)[0]
    pred = A @ np.array([sx, sy, c])
    ss_res = float(np.sum((d - pred) ** 2))
    ss_tot = float(np.sum((d - np.mean(d)) ** 2))
    return {
        "n": int(d.size),
        "slope_east_m_per_100m": float(sx),
        "slope_north_m_per_100m": float(sy),
        "intercept_m": float(c),
        "predicted_span_m": float(np.max(pred) - np.min(pred)),
        "r2": float(0.0 if ss_tot == 0 else 1.0 - ss_res / ss_tot),
    }


def summarize(rows: list[PatchRow], gcg_m: float, egm96_m: float, ls_zeta_m: float) -> dict[str, Any]:
    deltas = np.array([r.delta_m for r in rows], dtype=np.float64)
    ground = np.array([r.delta_m for r in rows if r.surface_type == "ground"], dtype=np.float64)
    roof = np.array([r.delta_m for r in rows if r.surface_type == "roof"], dtype=np.float64)
    delta_med = float(np.median(deltas))
    robust_mask = np.abs(deltas - delta_med) <= 0.3
    summary = {
        "n_total": int(deltas.size),
        "n_ground": int(ground.size),
        "n_roof": int(roof.size),
        "delta_median_m": delta_med,
        "delta_mad_m": mad(deltas),
        "ground_delta_median_m": float(np.median(ground)) if ground.size else float("nan"),
        "ground_delta_mad_m": mad(ground),
        "roof_delta_median_m": float(np.median(roof)) if roof.size else float("nan"),
        "roof_delta_mad_m": mad(roof),
        "group_delta_absdiff_m": float(abs(np.median(ground) - np.median(roof))) if ground.size and roof.size else float("nan"),
        "effective_zeta_m": gcg_m + delta_med,
        "gcg_reference_m": gcg_m,
        "egm96_aoi_m": egm96_m,
        "ls_zeta_m": ls_zeta_m,
        "paper_expected_delta_if_camera_egm96_m": egm96_m - gcg_m,
        "trend": linear_trend(rows),
        "trend_central_abs_delta_le_0p3": linear_trend(rows, robust_mask),
        "delta_min_m": float(np.min(deltas)),
        "delta_p10_m": float(np.quantile(deltas, 0.10)),
        "delta_p90_m": float(np.quantile(deltas, 0.90)),
        "delta_max_m": float(np.max(deltas)),
        "outlier_abs_delta_gt_0p3": int(np.sum(np.abs(deltas - delta_med) > 0.3)),
    }
    summary["criterion_patch_mad_le_0p3"] = bool(summary["delta_mad_m"] <= 0.3)
    summary["criterion_group_diff_le_0p3"] = bool(summary["group_delta_absdiff_m"] <= 0.3)
    summary["criterion_spatial_span_le_0p3"] = bool(summary["trend"]["predicted_span_m"] <= 0.3)
    summary["criterion_all_numeric"] = bool(
        summary["criterion_patch_mad_le_0p3"]
        and summary["criterion_group_diff_le_0p3"]
        and summary["criterion_spatial_span_le_0p3"]
    )
    return summary


def write_csv(rows: list[PatchRow], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "patch_id",
        "surface_type",
        "building_id",
        "x_m_epsg25832",
        "y_m_epsg25832",
        "patch_size_m",
        "n_als",
        "n_dense",
        "n_als_used",
        "n_dense_used",
        "als_orthometric_m_dhhn2016",
        "als_plus_gcg_m",
        "dense_camera_m",
        "delta_m",
        "als_mad_m",
        "dense_mad_m",
        "slope_deg",
        "icp_dx_m_aux",
        "icp_dy_m_aux",
        "note",
    ]
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow(
                {
                    "patch_id": r.patch_id,
                    "surface_type": r.surface_type,
                    "building_id": r.building_id,
                    "x_m_epsg25832": fmt(r.x_m),
                    "y_m_epsg25832": fmt(r.y_m),
                    "patch_size_m": fmt(r.patch_size_m),
                    "n_als": r.n_als,
                    "n_dense": r.n_dense,
                    "n_als_used": r.n_als_used,
                    "n_dense_used": r.n_dense_used,
                    "als_orthometric_m_dhhn2016": fmt(r.als_orthometric_m),
                    "als_plus_gcg_m": fmt(r.als_plus_gcg_m),
                    "dense_camera_m": fmt(r.dense_camera_m),
                    "delta_m": fmt(r.delta_m, 4),
                    "als_mad_m": fmt(r.als_mad_m, 4),
                    "dense_mad_m": fmt(r.dense_mad_m, 4),
                    "slope_deg": fmt(r.slope_deg, 3),
                    "icp_dx_m_aux": fmt(r.icp_dx_m, 4),
                    "icp_dy_m_aux": fmt(r.icp_dy_m, 4),
                    "note": r.note,
                }
            )


def write_figures(rows: list[PatchRow], summary: dict[str, Any], fig_dir: Path) -> None:
    fig_dir.mkdir(parents=True, exist_ok=True)
    ground = [r.delta_m for r in rows if r.surface_type == "ground"]
    roof = [r.delta_m for r in rows if r.surface_type == "roof"]

    plt.figure(figsize=(7, 4.5))
    bins = np.linspace(min(r.delta_m for r in rows) - 0.1, max(r.delta_m for r in rows) + 0.1, 24)
    plt.hist(ground, bins=bins, alpha=0.65, label=f"ground n={len(ground)}")
    plt.hist(roof, bins=bins, alpha=0.65, label=f"roof n={len(roof)}")
    plt.axvline(summary["delta_median_m"], color="black", linewidth=1.5, label=f"median {summary['delta_median_m']:.3f} m")
    plt.xlabel("delta = dense camera height - (ALS DHHN2016 + GCG2016) [m]")
    plt.ylabel("patch count")
    plt.legend()
    plt.tight_layout()
    plt.savefig(fig_dir / "datum_tie_histogram.png", dpi=180)
    plt.close()

    plt.figure(figsize=(6.5, 5.5))
    xs = np.array([r.x_m for r in rows])
    ys = np.array([r.y_m for r in rows])
    ds = np.array([r.delta_m for r in rows])
    sc = plt.scatter(xs, ys, c=ds, cmap="coolwarm", s=42, edgecolor="black", linewidth=0.3)
    for r in rows:
        if r.surface_type == "roof":
            plt.text(r.x_m, r.y_m, r.patch_id, fontsize=6)
    plt.colorbar(sc, label="delta [m]")
    plt.xlabel("Easting EPSG:25832 [m]")
    plt.ylabel("Northing EPSG:25832 [m]")
    plt.title(f"spatial trend span {summary['trend']['predicted_span_m']:.3f} m")
    plt.tight_layout()
    plt.savefig(fig_dir / "datum_tie_spatial_map.png", dpi=180)
    plt.close()

    plt.figure(figsize=(6, 4.5))
    plt.boxplot([ground, roof], tick_labels=["ground", "roof"], showmeans=True)
    plt.axhline(summary["delta_median_m"], color="black", linestyle="--", linewidth=1)
    plt.ylabel("delta [m]")
    plt.title(f"group median diff {summary['group_delta_absdiff_m']:.3f} m")
    plt.tight_layout()
    plt.savefig(fig_dir / "datum_tie_group_box.png", dpi=180)
    plt.close()


def run_text(cmd: list[str]) -> str:
    try:
        return subprocess.check_output(cmd, cwd=ROOT, text=True).strip()
    except Exception as exc:
        return f"unavailable: {exc}"


def source_snippet(path: Path, needles: list[str], before: int = 0, after: int = 0) -> list[str]:
    lines = path.read_text(errors="replace").splitlines()
    out: list[str] = []
    for i, line in enumerate(lines):
        if any(n in line for n in needles):
            lo = max(0, i - before)
            hi = min(len(lines), i + after + 1)
            out.extend(lines[lo:hi])
    return out[:12]


def write_versions(run_dir: Path, args: argparse.Namespace, summary: dict[str, Any]) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    versions = {
        "run_id": run_dir.name,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "branch": run_text(["git", "rev-parse", "--abbrev-ref", "HEAD"]),
        "git_commit": run_text(["git", "rev-parse", "HEAD"]),
        "docker_image": args.docker_image,
        "command": " ".join(args.command_for_versions),
        "no_reconstruction_or_retraining": True,
        "no_photo_matching_or_edge_matching": True,
        "geo_crs": "EPSG:25832",
        "opf_crs": "EPSG:32632",
        "inputs": {
            "raw_dense_npz": str(RAW_DENSE.relative_to(ROOT)),
            "raw_dense_versions": str(RAW_VERSIONS.relative_to(ROOT)),
            "raw_dense_converter": str(RAW_SCRIPT.relative_to(ROOT)),
            "als_aoi": str(ALS_AOI.relative_to(ROOT)),
            "footprints": str(FOOTPRINTS.relative_to(ROOT)),
            "dense_success_114_status": str(STATUS_114.relative_to(ROOT)),
            "gcg2016_grid": str(GCG_GRID.relative_to(ROOT)),
        },
        "parameters": {
            "gcg_reference_m": args.gcg,
            "egm96_aoi_m": args.egm96,
            "ls_zeta_reference_m": args.ls_zeta,
            "ground_target": args.ground_target,
            "roof_target": args.roof_target,
        },
        "summary": summary,
        "raw_dense_versions_snippet": RAW_VERSIONS.read_text(errors="replace").splitlines(),
        "raw_converter_snippet": source_snippet(RAW_SCRIPT, ["Datum:", "dense  =", "acmp   =", "SHIFT", "GEOID"]),
    }
    (run_dir / "versions.txt").write_text(json.dumps(versions, indent=2, ensure_ascii=False) + "\n")


def write_doc(rows: list[PatchRow], summary: dict[str, Any], run_dir: Path) -> None:
    trend = summary["trend"]
    central_trend = summary["trend_central_abs_delta_le_0p3"]
    icp_rows = [r for r in rows if r.surface_type == "roof" and r.icp_dx_m is not None]
    criteria_line = (
        "수치 기준 3개는 모두 충족 방향"
        if summary["criterion_all_numeric"]
        else "수치 기준 중 하나 이상이 미달 방향"
    )
    overlay_line = (
        "수치 기준이 모두 충족 방향이라, 별도 지시가 있으면 확정 제안 ζ̂로 as-projected 오버레이를 만들 수 있다."
        if summary["criterion_all_numeric"]
        else "수치 기준이 미달 방향이므로 이 커밋에서는 as-projected 오버레이를 만들지 않았다."
    )
    lines = [
        "# Datum Tie v3 - 측량 방식 높이 맞추기",
        "",
        "> 브랜치 `feat/p2-structure-learn`. 재구성/재학습 없음. 사진 매칭/에지 매칭 없음. 관찰·수치·제안까지만, 최종 판정은 김휘영.",
        "",
        "## 0. 재현 범위",
        "",
        f"- 실행 산출: `{CSV_OUT.relative_to(ROOT)}`, `docs/figs/datum_tie/`, `{run_dir.relative_to(ROOT)}/versions.txt`.",
        "- 지오 산출물 CRS: EPSG:25832. OPF 선언 CRS: EPSG:32632.",
        "- 높이 비교식: `Delta = dense_camera_height - (ALS_DHHN2016 + GCG2016_AOI)`.",
        "- 사진 대응, 에지/코너 매칭, gradient-max, +-28px STEP는 사용하지 않았다.",
        "",
        "## 1. 높이 기준 문서 감사",
        "",
        "| 데이터 | 수직 기준 선언 | 원문 인용/근거 | 관찰 |",
        "|---|---|---|---|",
        "| 바이에른 ALS | DHHN2016 해발/Normalhöhe | LDBV Laserpunkte: `Höhenbezugssystem DHHN2016`; `Koordinatensystem UTM Zone 32`; `Geodätisches Datum ETRS 89`; `Bezugsellipsoid GRS 1980`. <https://www.ldbv.bayern.de/produkte/landschaftsinformationen/laser.html> | `als_aoi.laz`는 EPSG:25832 태그, class 2/6 사용. 원 raw ALS 일부 타일은 CRS 태그가 비어 있으나 수치 범위와 AOI 처리 산출로 EPSG:25832를 보존한다. |",
        "| 참조 LoD2 | DHHN2016 해발/Normalhöhe | LDBV LoD2-BY: `Koordinatensystem UTM Zone 32`, `Datum ETRS89`, `Höhensystem DHHN2016`, `Abgabeformat CityGML`. <https://www.ldbv.bayern.de/produkte/liegenschaftsinformationen/gebaeudemodell.html> | footprint도 LoD2 GroundSurface에서 추출한 XY 도메인이다. 수직값을 직접 쓰지 않지만 기준은 LoD2와 같이 문서화한다. |",
        "| footprint | LoD2 GroundSurface 파생 | `phases/p0-audit/scripts/05_footprints.py`는 `GroundSurface`의 `gml:posList`를 추출하고 `crs=EPSG:25832`로 저장한다. | 이번 측정에서는 지붕 패치의 내부 마스크로만 사용했다. |",
        "| 카메라 포즈(OPF) | 수직 datum 미선언 | `input_cameras.json`: `coordinates=[48.14969263888889, 11.568962805555556, 636.837]`, `crs.definition=EPSG:4326`. `scene_reference_frame.json`: `WGS 84 / UTM zone 32N`, `ID[EPSG,32632]`, `CS[Cartesian,2]`, `shift=[-690953,-5336071,-604]`. | 핵심 한 줄: OPF geolocation/CRS 필드는 3번째 좌표를 갖지만 vertical CRS/geoid 모델을 선언하지 않는다. |",
        "| TUM 동시취득 ULS | 해수면 위, 모델 미상 | Zenodo PDF: `Georeferenced data is WGS84 / UTM 32N (EPSG:32632). Elevation is given above mean sea level.` <https://zenodo.org/records/14899378> | ULS LAZ 헤더는 EPSG:32632만 반환해 vertical model은 명시하지 않는다. |",
        "| TUM Photogrammetry 원본 LAZ | EGM96 height | `TUM_Downtown_Photogrammetry_20241217.laz` LAS header: `COMPD_CS[\"WGS 84 / UTM zone 32N + EGM96 height\" ... AUTHORITY[\"EPSG\",\"5773\"]]`. | 서류상 기대 Delta 계산의 기준 후보로 EGM96을 별도 병기한다. |",
        "| COLMAP/GS-LOCAL | shift -604 관례 | `results/tum_transfer/mob/raw/versions.txt`: `ellipsoidal UTM (GS-LOCAL+[690953,5336071,604])`. `tum_mob_raw_to_npz.py`: `dense = dim_v1.laz ... as-is`, `SHIFT=[690953,5336071,604]`. | 이번 실측 입력은 `raw_dense.npz`만 사용했다. `raw_acmp/raw_lidar`는 versions에 `+48 geoid`가 있어 제외했다. |",
        "| 촬영 측위 | M350 RTK + SAPOS NTRIP | TUM PDF: `DJI Matrice 350 RTK ... Zenmuse L2`; `connected to the NTRIP service of SAPOS Bayern`. SAPOS HEPS: `1-2 cm (Lage) and 2-3 cm (Höhe)`. DJI M350 RTK: `1 cm + 1 ppm horizontal`, `1.5 cm + 1 ppm vertical`. | 측위 편차는 문서상 cm급으로 둔다. 실제 표면 비교 산포는 포즈/표면/모드 선택 오차를 함께 포함한다. |",
        "",
        "참고 수치:",
        "",
        f"- GCG2016(AOI): {summary['gcg_reference_m']:.3f} m (grid 직접 판독 {45.6627006530762:.3f} m, 문서 표기는 45.7 m 반올림).",
        f"- EGM96(AOI): {summary['egm96_aoi_m']:.3f} m (`pyproj` EPSG:4326+5773 -> EPSG:4979, lon/lat={AOI_LON:.6f}/{AOI_LAT:.6f}).",
        f"- LS ζ 참고: {summary['ls_zeta_m']:.3f} ± 0.429 m (`docs/experiments/projection_zeta_ls/reports/projection_zeta_ls.md`).",
        f"- 서류상 기대 Delta: 카메라/원본 Photogrammetry가 EGM96 해수면 선언이면 `N_EGM96 - GCG2016 = {summary['paper_expected_delta_if_camera_egm96_m']:.3f} m`.",
        "",
        "## 2. 같은 표면 3D 실측 비교",
        "",
        f"- 패치 수: 전체 {summary['n_total']} = 지면 {summary['n_ground']} + 지붕 {summary['n_roof']}.",
        f"- Delta 중앙값 ± MAD: {summary['delta_median_m']:.3f} ± {summary['delta_mad_m']:.3f} m.",
        f"- Delta min/p10/p90/max: {summary['delta_min_m']:.3f} / {summary['delta_p10_m']:.3f} / {summary['delta_p90_m']:.3f} / {summary['delta_max_m']:.3f} m.",
        f"- 지면군 Delta: {summary['ground_delta_median_m']:.3f} ± {summary['ground_delta_mad_m']:.3f} m.",
        f"- 지붕군 Delta: {summary['roof_delta_median_m']:.3f} ± {summary['roof_delta_mad_m']:.3f} m.",
        f"- 지면군·지붕군 중앙값 차: {summary['group_delta_absdiff_m']:.3f} m.",
        f"- 유효 ζ = 45.7 + Delta = {summary['effective_zeta_m']:.3f} m.",
        "",
        "측정 입력:",
        "",
        "- 영상 유래 점군: `results/tum_transfer/mob/raw/raw_dense.npz` (`raw_dense`, voxel 0.1 m).",
        "- 금지/제외: `raw_acmp.npz`, `raw_lidar.npz`는 생성 이력에 `+48 geoid`가 있으므로 사용하지 않았다.",
        "- ALS: `results/tum_transfer/mob_analysis/p0c_step2/als_aoi.laz`, class-2 지면과 class-6 지붕.",
        "- 지붕 후보: P0 canonical w2_1의 `als_has_lod22=True AND dim_has_lod22=True` 114동에서, 실제로 ALS class-6와 raw_dense 상부 모드가 충분한 건물만 채택.",
        "",
        "그림:",
        "",
        "- `docs/figs/datum_tie/datum_tie_histogram.png`: Delta 히스토그램.",
        "- `docs/figs/datum_tie/datum_tie_spatial_map.png`: 패치별 Delta 공간 지도.",
        "- `docs/figs/datum_tie/datum_tie_group_box.png`: 지면군/지붕군 분리 분포.",
        "",
        "## 3. 공간 경향과 보조 ICP",
        "",
        f"- Delta 공간 회귀: east {trend['slope_east_m_per_100m']:.3f} m/100m, north {trend['slope_north_m_per_100m']:.3f} m/100m, R2={trend['r2']:.3f}.",
        f"- AOI 내 회귀 예측 span: {trend['predicted_span_m']:.3f} m.",
        f"- 중앙 패치 보조 회귀(|Delta-중앙값|<=0.3m, n={central_trend['n']}): east {central_trend['slope_east_m_per_100m']:.3f} m/100m, north {central_trend['slope_north_m_per_100m']:.3f} m/100m, span {central_trend['predicted_span_m']:.3f} m.",
        f"- |Delta-중앙값|>0.3m outlier: {summary['outlier_abs_delta_gt_0p3']} / {summary['n_total']} patches. 전체 회귀 span은 이 outlier 후보에 민감하다.",
        "",
        "| patch_id | surface | building_id | Delta m | 관찰 |",
        "|---|---|---|---:|---|",
    ]
    for r in sorted(rows, key=lambda item: abs(item.delta_m - summary["delta_median_m"]), reverse=True)[:6]:
        lines.append(
            f"| {r.patch_id} | {r.surface_type} | {r.building_id or '-'} | {r.delta_m:.3f} | 같은 표면 모드 불확실/표면 의존 후보 |"
        )
    lines.extend(
        [
            "",
        "| building_id | ICP dx m | ICP dy m | 비고 |",
        "|---|---:|---:|---|",
        ]
    )
    for r in icp_rows:
        lines.append(f"| {r.building_id} | {fmt(r.icp_dx_m, 3)} | {fmt(r.icp_dy_m, 3)} | 보조 XY 결속 확인용, 판정 도구 아님 |")
    if not icp_rows:
        lines.append("| - | - | - | 산출 없음 |")
    lines.extend(
        [
            "",
            "## 4. 대비표와 제안",
            "",
            "| 항목 | 값 m | 비고 |",
            "|---|---:|---|",
            f"| GCG2016(AOI) | {summary['gcg_reference_m']:.3f} | 공식 DHHN2016 변환 기준, grid 판독 45.663 m |",
            "| 관례 | 48.000 | 기존 파이프라인 상수 |",
            f"| LS ζ 참고 | {summary['ls_zeta_m']:.3f} | `docs/experiments/projection_zeta_ls/reports/projection_zeta_ls.md`의 사진 대응 LS 참고값 |",
            f"| 실측 유효 ζ | {summary['effective_zeta_m']:.3f} | 이번 점군 대 점군 Delta 중앙값 반영 |",
            f"| 서류상 EGM96 기대 Delta | {summary['paper_expected_delta_if_camera_egm96_m']:.3f} | EGM96 - GCG2016 |",
            f"| 실측 Delta | {summary['delta_median_m']:.3f} | 전체 패치 중앙값 |",
            "",
            f"합격 제안 기준의 기계적 관찰: {criteria_line}.",
            "",
            f"- 패치 간 산포 MAD <= 0.3 m: {summary['delta_mad_m']:.3f} m.",
            f"- 지면군·지붕군 Delta 차 <= 0.3 m: {summary['group_delta_absdiff_m']:.3f} m.",
            f"- 공간 경향 span <= 0.3 m: {trend['predicted_span_m']:.3f} m.",
            f"- 문서화용 오버레이: {overlay_line}",
            "",
            "제안 문장(판정 아님): 수치 기준 3개가 모두 충족 방향일 때만 ζ̂ 확정 제안을 검토한다. 미달 방향이면 공간 경향, 표면군 차이, raw_dense 상부/지면 모드 선택을 원인 후보로 남기고 A3a/A3b 투입 전 김휘영 판정을 기다린다.",
            "",
            "## 5. 판정 필요 지점",
            "",
            "1. 이번 점군 대 점군 실측 유효 ζ를 채택할지 여부.",
            "2. OPF 수직 datum 미선언을 카메라 높이 기준 불확실성으로 남길지, Photogrammetry LAZ의 EGM96 선언을 촬영 자 기준으로 볼지 여부.",
            "3. 수치 기준 미달 방향이 있을 경우 A3a/A3b를 중지하고 추가 원인 관찰을 할지 여부.",
            "4. 수치 기준 충족 방향일 경우 as-projected 오버레이를 별도 커밋으로 만들지 여부.",
        ]
    )
    DOC.write_text("\n".join(lines) + "\n")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--gcg", type=float, default=45.7)
    p.add_argument("--egm96", type=float, default=45.544227408539186)
    p.add_argument("--ls-zeta", type=float, default=48.126)
    p.add_argument("--ground-target", type=int, default=36)
    p.add_argument("--roof-target", type=int, default=24)
    p.add_argument("--docker-image", default="jointbuildgs-p0-tools:t0")
    p.add_argument("--run-id", default="")
    args = p.parse_args()
    args.command_for_versions = ["python", "phases/p2-gsjso/scripts/datum_tie.py"] + [
        a for a in __import__("sys").argv[1:] if a != "--docker-image"
    ]
    return args


def main() -> None:
    args = parse_args()
    run_id = args.run_id or datetime.now().strftime("datum_tie_%Y%m%d_%H%M%S")
    run_dir = ROOT / "phases" / "p2-gsjso" / "runs" / run_id

    als = read_als_index()
    dense = read_dense_index()
    footprints = load_footprints()
    success_114 = load_dense_success_114()

    ground = measure_ground(als, dense, args.gcg, args.ground_target)
    roof = measure_roofs(als, dense, footprints, success_114, args.gcg, args.roof_target)
    rows = ground + roof
    if len(ground) < 30:
        raise RuntimeError(f"ground patches below requirement: {len(ground)} < 30")
    if len(roof) < 20:
        raise RuntimeError(f"roof patches below requirement: {len(roof)} < 20")

    summary = summarize(rows, args.gcg, args.egm96, args.ls_zeta)
    write_csv(rows, CSV_OUT)
    write_figures(rows, summary, FIG_DIR)
    write_versions(run_dir, args, summary)
    write_doc(rows, summary, run_dir)
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
