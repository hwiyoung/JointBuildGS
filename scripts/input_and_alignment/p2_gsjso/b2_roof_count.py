#!/usr/bin/env python3
"""B2 Phase 1 — per-footprint point count for the 46 no_points buildings across 6 sources:
image-side {DIM(mine), OPF/COLMAP-sparse, Pix4D-dense} + co-acquired LiDAR {L2-ULS-nadir, L2-ULS-manual}
+ reference {Bavaria-ALS}. Counts footprint-interior points (XY polygon, all z = building occupancy),
scaled by per-source decimation. All inputs in EPSG:25832 (bundle reprojected 32632->25832 by
b2_bundle_prep.sh; sparse GS-local +[690953,5336071,604]). Read-only, p0-tools. Observation only.
Out: results/tum_transfer/mob/b2/material_46x6.csv
"""
import csv, json, subprocess
from pathlib import Path
import numpy as np, laspy
from matplotlib.path import Path as MplPath

REPO = "/workspace/JointBuildGS"
B2 = f"{REPO}/results/tum_transfer/mob/b2"
SHIFT = np.array([690953.0, 5336071.0, 604.0])
GPKG = f"{REPO}/phases/p0-audit/data/work/footprints/lod2_ground_plan.gpkg"
GEO = "/tmp/lod2_b2.geojson"
# name, path, kind(laz|txt), decimation_step (count scaled x step), needs_shift
SOURCES = [
    ("DIM",          f"{REPO}/phases/p0-audit/data/work/mvs/dim/dim_v1.laz",                       "laz", 1,  False),
    ("OPF_sparse",   f"{REPO}/phases/p0-audit/data/work/mvs/openmvs/colmap_txt/sparse/points3D.txt","txt", 1,  True),
    ("Pix4D_dense",  f"{B2}/pix4d.laz",                                                              "laz", 15, False),
    ("L2_ULS_nadir", f"{B2}/uls_nadir.laz",                                                          "laz", 15, False),
    ("L2_ULS_manual",f"{B2}/uls_manual.laz",                                                         "laz", 10, False),
    ("Bavaria_ALS",  f"{REPO}/results/tum_transfer/mob_analysis/p0c_step2/als_aoi.laz",              "laz", 1,  False),
]


def load_xy(path, kind, shift):
    if kind == "txt":
        xy = []
        for line in open(path):
            if line.startswith("#") or not line.strip():
                continue
            p = line.split()
            xy.append((float(p[1]) + SHIFT[0], float(p[2]) + SHIFT[1]))
        return np.asarray(xy, float)
    f = laspy.read(path)
    return np.column_stack([np.asarray(f.x), np.asarray(f.y)]).astype(float)


def main():
    subprocess.run(["ogr2ogr", "-f", "GeoJSON", GEO, GPKG, "lod2_ground_plan"], check=False,
                   stderr=subprocess.DEVNULL)
    w4c = {r["building_id"]: r["classification"]
           for r in csv.DictReader(open(f"{REPO}/phases/p0-audit/docs/W4c_no_points_breakdown.csv"))}
    ids = [b for b in w4c if b.startswith("DEBY")]
    feats = {f["properties"]["building_id"]: f["geometry"] for f in json.load(open(GEO))["features"]}
    rings, areas, paths = {}, {}, {}
    for b in ids:
        g = feats[b]
        r = np.asarray(g["coordinates"][0] if g["type"] == "Polygon" else g["coordinates"][0][0])[:, :2]
        rings[b] = r; paths[b] = MplPath(r)
        areas[b] = 0.5 * abs(np.dot(r[:, 0], np.roll(r[:, 1], -1)) - np.dot(r[:, 1], np.roll(r[:, 0], -1)))

    counts = {b: {} for b in ids}
    for name, path, kind, step, shift in SOURCES:
        if not Path(path).exists():
            print(f"[skip] {name}: missing {path}"); continue
        P = load_xy(path, kind, shift)
        print(f"[{name}] loaded {len(P)} pts (step={step})")
        for b in ids:
            r = rings[b]; x0, y0, x1, y1 = r[:, 0].min(), r[:, 1].min(), r[:, 0].max(), r[:, 1].max()
            m = (P[:, 0] >= x0) & (P[:, 0] <= x1) & (P[:, 1] >= y0) & (P[:, 1] <= y1)
            n = int(paths[b].contains_points(P[m]).sum()) * step if m.any() else 0
            counts[b][name] = n

    out = []
    for b in ids:
        row = {"building": b.replace("DEBY_LOD2_", ""), "w4c_class": w4c[b], "area_m2": round(areas[b], 1)}
        for name, *_ in SOURCES:
            n = counts[b].get(name, "")
            row[name] = n
            row[f"{name}_dens"] = (round(n / areas[b], 1) if isinstance(n, int) and areas[b] else "")
        out.append(row)
    keys = ["building", "w4c_class", "area_m2"] + [s[0] for s in SOURCES] + [f"{s[0]}_dens" for s in SOURCES]
    Path(B2).mkdir(parents=True, exist_ok=True)
    with open(f"{B2}/material_46x6.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=keys); w.writeheader(); w.writerows(out)
    print(f"[done] -> {B2}/material_46x6.csv ({len(out)} buildings)")


if __name__ == "__main__":
    main()
