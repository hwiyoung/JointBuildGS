#!/usr/bin/env python3
"""E1-coverage evaluability selection for the journal1 study area (advisory).

Implements the user's 2026-08-12 boundary rule on top of the sealed current
UAS LiDAR (E1) survey extent:

  1. The E1 coverage region is derived automatically from scene occupancy
     (1 m cells with any E1 return, union → largest component, interior holes
     filled). No hand-drawn boundary.
  2. Buildings whose shared standard footprint lies fully inside the coverage
     region eroded by a safety margin ("interior") are all included —
     interior low coverage (canopy occlusion) is an observation property,
     not a survey-extent artifact.
  3. Buildings touching the boundary ring are included only when E1 covers
     ≥ `cover_min` (default 0.80) of their footprint cells; buildings outside
     the coverage region are excluded.

This is an ADVISORY evaluability mask over the population — it is applied
identically to every condition, never classifies outcomes, never selects
parameters, and awaits human confirmation in the 8882 viewer (per-building
override + export). Non-confirmatory; `scientific_verdict` stays null.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import shapely
from shapely.geometry import box, mapping, shape
from shapely.ops import unary_union

from scripts.p2.journal1_phase_a_v1.geometry_eval import read_ply

REPO = Path(__file__).resolve().parents[3]
DEFAULTS = {
    "occupancy_cell_m": 1.0,
    "boundary_margin_m": 5.0,
    "cover_cell_m": 0.5,
    "cover_min": 0.80,
    "ring_simplify_m": 1.0,
    "ground_grid_m": 4.0,
    "ring_z_lift_m": 1.5,
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def coverage_region(xy: np.ndarray, cell: float) -> shapely.Polygon:
    """Largest occupied component, interior holes filled (exterior ring only)."""
    keys = np.unique(np.floor(xy / cell).astype(np.int64), axis=0)
    cells = [box(k[0] * cell, k[1] * cell, (k[0] + 1) * cell, (k[1] + 1) * cell) for k in keys]
    union = unary_union(cells)
    parts = list(union.geoms) if union.geom_type == "MultiPolygon" else [union]
    largest = max(parts, key=lambda p: p.area)
    return shapely.Polygon(largest.exterior)


def ground_grid(xyz: np.ndarray, cell: float):
    keys = np.floor(xyz[:, :2] / cell).astype(np.int64)
    order = np.lexsort((keys[:, 1], keys[:, 0]))
    keys, z = keys[order], xyz[order, 2]
    starts = np.r_[0, np.flatnonzero(np.any(np.diff(keys, axis=0) != 0, axis=1)) + 1]
    zmin = np.minimum.reduceat(z, starts)
    return {tuple(k): float(v) for k, v in zip(keys[starts], zmin)}


def ring_with_z(ring_xy, grid, cell: float, lift: float, fallback_z: float):
    out = []
    for x, y in ring_xy:
        key = (int(np.floor(x / cell)), int(np.floor(y / cell)))
        z = grid.get(key)
        if z is None:
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    z = grid.get((key[0] + dx, key[1] + dy))
                    if z is not None:
                        break
                if z is not None:
                    break
        out.append([round(float(x), 2), round(float(y), 2), round((z if z is not None else fallback_z) + lift, 2)])
    return out


def region_rings(geom) -> list:
    parts = list(geom.geoms) if geom.geom_type == "MultiPolygon" else [geom] if not geom.is_empty else []
    return [list(p.exterior.coords) for p in parts]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="configs/p2/journal1_phase_a_v1/conditions_viewer_v1.json")
    args = parser.parse_args()
    cfg = json.load(open(args.config))
    params = dict(DEFAULTS)
    origin = np.asarray(cfg["origin"], dtype=np.float64)
    a2_root = Path(cfg["out_dir"]).parent
    out_dir = a2_root / "selection_e1_coverage_v1"
    out_dir.mkdir(parents=True, exist_ok=True)

    e1_scene = Path(cfg["out_dir"]) / "assets_scene/E1.points.ply"
    xyz, cls = read_ply(e1_scene)
    if len(xyz) < 100_000:
        raise RuntimeError("E1 scene voxel asset unexpectedly small")

    region = coverage_region(xyz[:, :2], params["occupancy_cell_m"])
    interior = region.buffer(-params["boundary_margin_m"])
    grid = ground_grid(xyz, params["ground_grid_m"])
    fallback_z = float(np.percentile(xyz[:, 2], 5))

    e1_any = {tuple(k) for k in np.floor(xyz[:, :2] / params["cover_cell_m"]).astype(np.int64)}
    m6 = cls == 6 if cls is not None else np.zeros(len(xyz), bool)
    e1_cls6 = {tuple(k) for k in np.floor(xyz[m6, :2] / params["cover_cell_m"]).astype(np.int64)}

    phaseb = {}
    phaseb_path = Path(
        "/artifacts/JointBuildGS/phase-payloads/p2/journal1_phase_b_v1/P2-JOURNAL1-PHASE-B-v1/"
        "labels_support/coverage_all199_v1.json")
    if phaseb_path.is_file():
        payload = json.loads(phaseb_path.read_text(encoding="utf-8"))
        phaseb = {row["stable_id"]: row for row in payload.get("buildings", []) if "error" not in row}

    tiers = {r["stable_id"]: r["tier"] for r in csv.DictReader(open(cfg["labels_csv"]))}
    footprints = json.load(open(cfg["footprints_geojson"]))
    cell = params["cover_cell_m"]
    rows = []
    for feature in footprints["features"]:
        sid = str(feature["properties"]["stable_id"])
        idx = int(feature["properties"]["population_index"])
        poly_local = shapely.affinity.translate(shape(feature["geometry"]), xoff=-origin[0], yoff=-origin[1])
        if poly_local.within(interior):
            zone = "interior"
        elif poly_local.intersects(region):
            zone = "boundary"
        else:
            zone = "outside"
        x0, y0, x1, y1 = poly_local.bounds
        gx = np.arange(np.floor(x0 / cell) * cell + cell / 2, x1, cell)
        gy = np.arange(np.floor(y0 / cell) * cell + cell / 2, y1, cell)
        cover_any = cover_cls6 = None
        if len(gx) and len(gy):
            xx, yy = np.meshgrid(gx, gy)
            inside = shapely.contains_xy(poly_local, xx.ravel(), yy.ravel())
            centers = np.column_stack((xx.ravel()[inside], yy.ravel()[inside]))
            if len(centers):
                keys = np.floor(centers / cell).astype(np.int64)
                cover_any = float(np.mean([tuple(k) in e1_any for k in keys]))
                cover_cls6 = float(np.mean([tuple(k) in e1_cls6 for k in keys]))
        selected = zone == "interior" or (
            zone == "boundary" and cover_any is not None and cover_any >= params["cover_min"])
        pb = phaseb.get(sid, {}).get("E1", {})
        rows.append({
            "population_index": idx, "stable_id": sid, "bkey": f"B{idx:03d}",
            "tier": tiers.get(sid, "?"), "zone": zone,
            "e1_any_cover": None if cover_any is None else round(cover_any, 3),
            "e1_cls6_cover": None if cover_cls6 is None else round(cover_cls6, 3),
            "phaseb_any_xy": pb.get("any_xy"),
            "selected_rule": bool(selected),
        })
    rows.sort(key=lambda r: r["population_index"])

    counts = {
        "interior": sum(r["zone"] == "interior" for r in rows),
        "boundary": sum(r["zone"] == "boundary" for r in rows),
        "outside": sum(r["zone"] == "outside" for r in rows),
        "selected": sum(r["selected_rule"] for r in rows),
        "boundary_selected": sum(r["selected_rule"] and r["zone"] == "boundary" for r in rows),
        "interior_low_cover_060": sum(
            r["zone"] == "interior" and r["e1_any_cover"] is not None and r["e1_any_cover"] < 0.6 for r in rows),
    }

    generated_utc = datetime.now(timezone.utc).isoformat(timespec="seconds")
    selection = {
        "schema": "jointbuildgs.p2.journal1_phase_a_v1.a2_e1_coverage_selection.v1",
        "task_id": cfg["task_id"],
        "status": "ADVISORY_EVALUABILITY_MASK_PENDING_HUMAN_CONFIRMATION",
        "scientific_verdict": None,
        "generated_utc": generated_utc,
        "rule": {
            **params,
            "definition": "interior (footprint within coverage eroded by margin) → include all; boundary → include iff E1 any-return footprint coverage >= cover_min; outside → exclude",
            "coverage_source": "E1 full-scene 0.5 m voxel asset (any class, survey occupancy)",
        },
        "counts": counts,
        "buildings": rows,
    }
    (out_dir / "selection_v1.json").write_text(json.dumps(selection, ensure_ascii=False, indent=1))
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=list(rows[0].keys()), lineterminator="\n")
    writer.writeheader(); writer.writerows(rows)
    (out_dir / "selection_v1.csv").write_text(stream.getvalue())

    simplify = params["ring_simplify_m"]
    region_s = region.simplify(simplify)
    interior_s = interior.simplify(simplify)
    world = shapely.affinity.translate
    (out_dir / "coverage_boundary.geojson").write_text(json.dumps({
        "type": "FeatureCollection",
        "crs": {"type": "name", "properties": {"name": "urn:ogc:def:crs:EPSG::25832"}},
        "features": [
            {"type": "Feature", "properties": {"role": "E1_COVERAGE_REGION"},
             "geometry": mapping(world(region_s, xoff=origin[0], yoff=origin[1]))},
            {"type": "Feature", "properties": {"role": "E1_INTERIOR_REGION", "margin_m": params["boundary_margin_m"]},
             "geometry": mapping(world(interior_s, xoff=origin[0], yoff=origin[1]))},
        ],
    }))
    viewer_payload = {
        "coverage_rings": [ring_with_z(r, grid, params["ground_grid_m"], params["ring_z_lift_m"], fallback_z)
                            for r in region_rings(region_s)],
        "interior_rings": [ring_with_z(r, grid, params["ground_grid_m"], params["ring_z_lift_m"], fallback_z)
                            for r in region_rings(interior_s)],
        "params": params,
    }
    (out_dir / "boundary_viewer.json").write_text(json.dumps(viewer_payload))

    receipt = {
        "schema": "jointbuildgs.p2.journal1_phase_a_v1.a2_e1_coverage_selection.receipt.v1",
        "task_id": cfg["task_id"],
        "generated_utc": generated_utc,
        "tool": "scripts/p2/journal1_phase_a_v1/a2_e1_coverage_selection.py",
        "inputs": {
            "e1_scene_voxel_asset": {"path": str(e1_scene), "sha256": sha256_file(e1_scene),
                                      "lineage": "C1_L_upper classified_scene.laz → 0.5 m voxel centroid (viewer scene asset)"},
            "footprints_geojson": cfg["footprints_geojson"],
            "labels_csv": cfg["labels_csv"],
            "phaseb_coverage_crosscheck": str(phaseb_path) if phaseb else None,
        },
        "params": params,
        "counts": counts,
        "boundary_note": "coverage region = largest occupied 1 m component, interior holes filled; not a hand-drawn boundary",
        "advisory_note": "evaluability mask only — applied identically to all conditions; never an outcome classifier or parameter input; human confirmation + override export in the 8882 viewer",
        "official_PASS_usable": None,
        "scientific_verdict": None,
    }
    (out_dir / "receipt.json").write_text(json.dumps(receipt, ensure_ascii=False, indent=1))
    print(json.dumps(counts))


if __name__ == "__main__":
    main()
