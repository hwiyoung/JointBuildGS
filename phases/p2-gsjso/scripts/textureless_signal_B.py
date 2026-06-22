#!/usr/bin/env python3
"""P2 textureless-signal — Part B: did OpenMVS re-densify (resolution-level 4->2) recover MORE roof points?

Reads the relaxed dense cloud (dim_dense_relaxed.ply, GS-LOCAL/COLMAP frame = ellipsoidal), clips to each
footprint, and reports per building: total points, dz=z-true_roof median, points within +-2 m of roof, and
the DELTA vs the original res-4 DIM (from textureless_signal_A.json). Observation only. Runs in dev (open3d).
Frame: ply is GS-local; roof_local = h_roof + geoid(48) - 604; xy_utm = xy_local + shift_xy.
"""
import json, csv, sys
import numpy as np, open3d as o3d
REPO = "/workspace/JointBuildGS"
SHIFT = np.array([690953.0, 5336071.0, 604.0]); GEOID = 48.0
NOSEED = ["42364609", "4907182", "4908050", "4908166", "4908176"]; CTRL = ["42364659", "42364663", "4907510"]
ALLB = NOSEED + CTRL


def pip(pts, poly):
    x, y = pts[:, 0], pts[:, 1]; inside = np.zeros(len(pts), bool); j = len(poly) - 1
    for i in range(len(poly)):
        xi, yi = poly[i]; xj, yj = poly[j]
        cond = ((yi > y) != (yj > y)) & (x < (xj - xi) * (y - yi) / (yj - yi + 1e-12) + xi)
        inside ^= cond; j = i
    return inside


geo = json.load(open(f"{REPO}/results/tum_transfer/analysis/footprints_aoi.geojson"))["features"]
refh = {r["building_id"]: r for r in csv.DictReader(open(f"{REPO}/results/tum_transfer/mob_analysis/ref_roof_heights.csv"))}
A = {r["bid"]: r for r in json.load(open(f"{REPO}/results/tum_transfer/mob_analysis/textureless_signal_A.json"))}
pc = o3d.io.read_point_cloud(f"{REPO}/phases/p0-audit/data/work/mvs/openmvs/dim_dense_relaxed.ply")
P_local = np.asarray(pc.points); P_utm_xy = P_local[:, :2] + SHIFT[:2]
print(f"[ply] relaxed dense points = {len(P_local)}")

rows = []
for b in ALLB:
    bid = f"DEBY_LOD2_{b}"
    g = [f for f in geo if f["properties"]["building_id"] == bid][0]["geometry"]
    ring = np.asarray(g["coordinates"][0] if g["type"] == "Polygon" else g["coordinates"][0][0])[:, :2]
    x0, y0, x1, y1 = ring[:, 0].min(), ring[:, 1].min(), ring[:, 0].max(), ring[:, 1].max()
    box = (P_utm_xy[:, 0] >= x0) & (P_utm_xy[:, 0] <= x1) & (P_utm_xy[:, 1] >= y0) & (P_utm_xy[:, 1] <= y1)
    inb = box.copy(); inb[box] = pip(P_utm_xy[box], ring)
    roof_local = float(refh[bid]["h_roof"]) + GEOID - 604.0
    dz = P_local[inb, 2] - roof_local
    near = int((np.abs(dz) <= 2.0).sum())
    a = A[bid]
    rows.append(dict(bid=bid, klass=("no-seed" if b in NOSEED else "control"),
                     relaxed_n=int(inb.sum()), relaxed_dz_med=(round(float(np.median(dz)), 1) if inb.sum() else None),
                     relaxed_near_roof=near,
                     dim_orig_n=a["dim_n"], dim_orig_near_roof=a["dim_near_roof"],
                     added_near_roof=near - a["dim_near_roof"]))
    print(f"{bid} {rows[-1]['klass']}: relaxed n={rows[-1]['relaxed_n']} dz_med={rows[-1]['relaxed_dz_med']} "
          f"near-roof={near} (orig DIM near={a['dim_near_roof']}, +{rows[-1]['added_near_roof']})")

out = f"{REPO}/results/tum_transfer/mob_analysis/textureless_signal_B"
json.dump(rows, open(out + ".json", "w"), indent=2)
with open(out + ".csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
print(f"[done] -> {out}.csv/.json")
