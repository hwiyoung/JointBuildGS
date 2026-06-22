#!/usr/bin/env python3
"""P2 textureless-signal — Part C: does ACMP (plane-prior PatchMatch MVS) recover textureless roofs?

Reads the ACMP fused cloud (GS-LOCAL/COLMAP frame = ellipsoidal), clips to each footprint, and reports
per building: points, dz=z-true_roof median, points within +-2 m of roof, footprint xy-coverage, and
roof plane-fit RMS (near-roof points). Compares to the original DIM (textureless_signal_A.json).
Observation only. Runs in dev (open3d). roof_local = h_roof + geoid(48) - 604; xy_utm = xy_local + shift_xy.
"""
import json, csv, sys
import numpy as np, open3d as o3d
REPO = "/workspace/JointBuildGS"
SHIFT = np.array([690953.0, 5336071.0, 604.0]); GEOID = 48.0
NOSEED = ["42364609", "4907182", "4908050", "4908166", "4908176"]; CTRL = ["42364659", "42364663", "4907510"]
ALLB = NOSEED + CTRL
ply = sys.argv[1] if len(sys.argv) > 1 else f"{REPO}/results/tum_transfer/mob_analysis/acmp_work/ACMP/ACMP_model.ply"


def pip(pts, poly):
    x, y = pts[:, 0], pts[:, 1]; inside = np.zeros(len(pts), bool); j = len(poly) - 1
    for i in range(len(poly)):
        xi, yi = poly[i]; xj, yj = poly[j]
        inside ^= ((yi > y) != (yj > y)) & (x < (xj - xi) * (y - yi) / (yj - yi + 1e-12) + xi); j = i
    return inside


def plane_rms(P):
    if len(P) < 10:
        return None
    c = P.mean(0); _, _, Vt = np.linalg.svd(P - c, full_matrices=False)
    d = (P - c) @ Vt[-1]
    return round(float(np.sqrt((d ** 2).mean())), 2)


def coverage(xy, ring, cell=1.0):
    x0, y0, x1, y1 = ring[:, 0].min(), ring[:, 1].min(), ring[:, 0].max(), ring[:, 1].max()
    nx, ny = max(1, int((x1 - x0) / cell)), max(1, int((y1 - y0) / cell))
    # footprint cells occupied by >=1 point / footprint cells total
    gx = ((xy[:, 0] - x0) / cell).astype(int); gy = ((xy[:, 1] - y0) / cell).astype(int)
    occ = len(set(zip(gx.tolist(), gy.tolist())))
    # footprint cell count via grid centers inside polygon
    cx, cy = np.meshgrid(np.arange(nx) * cell + x0 + cell / 2, np.arange(ny) * cell + y0 + cell / 2)
    grid = np.column_stack([cx.ravel(), cy.ravel()])
    ncells = max(1, int(pip(grid, ring).sum()))
    return round(occ / ncells, 2)


geo = json.load(open(f"{REPO}/results/tum_transfer/analysis/footprints_aoi.geojson"))["features"]
refh = {r["building_id"]: r for r in csv.DictReader(open(f"{REPO}/results/tum_transfer/mob_analysis/ref_roof_heights.csv"))}
A = {r["bid"]: r for r in json.load(open(f"{REPO}/results/tum_transfer/mob_analysis/textureless_signal_A.json"))}
pc = o3d.io.read_point_cloud(ply); P = np.asarray(pc.points); xy_utm = P[:, :2] + SHIFT[:2]
print(f"[acmp ply] {ply}: {len(P)} points")

rows = []
for b in ALLB:
    bid = f"DEBY_LOD2_{b}"
    g = [f for f in geo if f["properties"]["building_id"] == bid][0]["geometry"]
    ring = np.asarray(g["coordinates"][0] if g["type"] == "Polygon" else g["coordinates"][0][0])[:, :2]
    x0, y0, x1, y1 = ring[:, 0].min(), ring[:, 1].min(), ring[:, 0].max(), ring[:, 1].max()
    box = (xy_utm[:, 0] >= x0) & (xy_utm[:, 0] <= x1) & (xy_utm[:, 1] >= y0) & (xy_utm[:, 1] <= y1)
    inb = box.copy(); inb[box] = pip(xy_utm[box], ring)
    roof_local = float(refh[bid]["h_roof"]) + GEOID - 604.0
    Pin = P[inb]; dz = Pin[:, 2] - roof_local
    near = np.abs(dz) <= 2.0
    rms = plane_rms(Pin[near]) if near.sum() >= 10 else None
    cov = coverage(xy_utm[inb], ring) if inb.sum() else 0.0
    a = A[bid]
    rows.append(dict(bid=bid, klass=("no-seed" if b in NOSEED else "control"),
                     acmp_n=int(inb.sum()), acmp_dz_med=(round(float(np.median(dz)), 1) if inb.sum() else None),
                     acmp_near_roof=int(near.sum()), acmp_coverage=cov, acmp_roof_rms=rms,
                     dim_orig_n=a["dim_n"], dim_orig_near_roof=a["dim_near_roof"]))
    print(f"{bid} {rows[-1]['klass']}: ACMP n={rows[-1]['acmp_n']} dz_med={rows[-1]['acmp_dz_med']} "
          f"near-roof={int(near.sum())} cov={cov} roofRMS={rms} | DIM n={a['dim_n']} near={a['dim_near_roof']}")

out = f"{REPO}/results/tum_transfer/mob_analysis/textureless_signal_C"
json.dump(rows, open(out + ".json", "w"), indent=2)
with open(out + ".csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
print(f"[done] -> {out}.csv/.json")
