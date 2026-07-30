#!/usr/bin/env python3
"""P2 make-or-break eval — clip GS-TSDF to one building, optional ALS-density match, classify.

Runs in the P0 tools container (laspy + pdal CLI + numpy + matplotlib). Reuses P0 T4
classification (filters.smrf ground=2 + filters.overlay footprint building=6, exactly
phases/p0-audit/scripts/04_classify.py:193-224). Writes a classified LAS that the Roofer
service consumes, plus a metrics json. EPSG:25832.
"""
import argparse, json, os, subprocess
import numpy as np, laspy
from matplotlib.path import Path as MplPath

GROUND, BUILDING, UNCLASS = 2, 6, 1


def voxel_downsample(P, voxel):
    q = np.floor(P / voxel).astype(np.int64)
    OFF, MUL = 1 << 20, 1 << 21
    key = ((q[:, 0] + OFF) * MUL + (q[:, 1] + OFF)) * MUL + (q[:, 2] + OFF)
    _, idx = np.unique(key, return_index=True)
    return P[idx]


def plane_rms(P):
    if len(P) < 10:
        return None
    c = P.mean(0); Q = P - c
    _, _, Vt = np.linalg.svd(Q, full_matrices=False)
    n = Vt[-1]
    d = Q @ n
    return float(np.sqrt((d ** 2).mean()))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tsdf", required=True)
    ap.add_argument("--bid", required=True)
    ap.add_argument("--geojson", required=True)
    ap.add_argument("--buffer", type=float, default=15.0)
    ap.add_argument("--target-density", type=float, default=0.0,
                    help="ALS roof pts/m^2; >0 -> voxel-downsample so GS roof density matches ALS")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--outdir", required=True)
    ap.add_argument("--tag", default="orig")
    A = ap.parse_args()
    os.makedirs(A.outdir, exist_ok=True)
    rng = np.random.default_rng(A.seed)

    npz = np.load(A.tsdf)
    TS = npz["P_utm_clean"] if "P_utm_clean" in npz else npz["P_utm"]
    feats = json.load(open(A.geojson))["features"]
    fb = [f for f in feats if f["properties"]["building_id"] == A.bid]
    geom = fb[0]["geometry"]
    ring = np.asarray(geom["coordinates"][0] if geom["type"] == "Polygon" else geom["coordinates"][0][0])
    x0, y0, x1, y1 = ring[:, 0].min(), ring[:, 1].min(), ring[:, 0].max(), ring[:, 1].max()
    fp = MplPath(ring[:, :2])
    area = 0.5 * abs(np.dot(ring[:, 0], np.roll(ring[:, 1], -1)) - np.dot(ring[:, 1], np.roll(ring[:, 0], -1)))

    m = ((TS[:, 0] >= x0 - A.buffer) & (TS[:, 0] <= x1 + A.buffer)
         & (TS[:, 1] >= y0 - A.buffer) & (TS[:, 1] <= y1 + A.buffer))
    P = TS[m]
    n_clip = len(P)
    used_voxel = None
    if A.target_density > 0 and n_clip > 0 and area > 0:
        # voxel-downsample so GS roof (in-footprint) areal density matches ALS roof density.
        # density(voxel) is monotonically decreasing -> bisect voxel in [0.05, 2.0] m.
        lo, hi = 0.05, 2.0
        for _ in range(14):
            mid = float(np.sqrt(lo * hi))  # geometric midpoint
            Pd = voxel_downsample(P, mid)
            dens = fp.contains_points(Pd[:, :2]).sum() / area
            if dens > A.target_density:
                lo = mid  # too dense -> larger voxel
            else:
                hi = mid
        used_voxel = float(np.sqrt(lo * hi))
        P = voxel_downsample(P, used_voxel)
    n_used = len(P)
    if n_used < 4:
        print(f"[prep] {A.bid} {A.tag}: too few points ({n_used})")
        json.dump({"bid": A.bid, "tag": A.tag, "n_clip": n_clip, "n_used": n_used,
                   "classified_las": None, "plane_rms": None, "roof_density": None},
                  open(f"{A.outdir}/{A.bid}_{A.tag}_metrics.json", "w"))
        return

    raw = f"{A.outdir}/{A.bid}_{A.tag}_raw.las"
    hdr = laspy.LasHeader(point_format=6, version="1.4")
    hdr.offsets = [P[:, 0].min(), P[:, 1].min(), P[:, 2].min()]; hdr.scales = [0.001, 0.001, 0.001]
    las = laspy.LasData(hdr); las.x = P[:, 0]; las.y = P[:, 1]; las.z = P[:, 2]; las.write(raw)

    fpg = f"{A.outdir}/{A.bid}_{A.tag}_fp.geojson"
    json.dump({"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {"class": BUILDING}, "geometry": geom}]}, open(fpg, "w"))

    clf = f"{A.outdir}/{A.bid}_{A.tag}_classified.las"
    pipe = {"pipeline": [
        {"type": "readers.las", "filename": raw},
        {"type": "filters.smrf", "cell": 1.0, "slope": 0.15, "scalar": 1.25, "threshold": 0.5, "window": 18.0,
         "ground_class": GROUND, "other_class": UNCLASS},
        {"type": "filters.overlay", "dimension": "Classification", "datasource": fpg, "column": "class",
         "where": f"Classification != {GROUND}"},
        {"type": "writers.las", "filename": clf, "a_srs": "EPSG:25832", "minor_version": 4, "dataformat_id": 3}]}
    pj = f"{A.outdir}/{A.bid}_{A.tag}_pipeline.json"; json.dump(pipe, open(pj, "w"))
    r = subprocess.run(["pdal", "pipeline", pj], capture_output=True, text=True)
    if r.returncode != 0:
        print("PDAL FAIL:", r.stderr[-400:]); raise SystemExit(1)

    c = laspy.read(clf)
    cl = np.asarray(c.classification)
    cx, cy, cz = np.asarray(c.x), np.asarray(c.y), np.asarray(c.z)
    bmask = cl == BUILDING
    infp = fp.contains_points(np.column_stack([cx, cy]))
    roofpts = np.column_stack([cx, cy, cz])[bmask & infp]
    rms = plane_rms(roofpts)
    roof_dens = (int((bmask & infp).sum()) / area) if area > 0 else None
    counts = {int(k): int(v) for k, v in zip(*np.unique(cl, return_counts=True))}
    out = {"bid": A.bid, "tag": A.tag, "n_clip": n_clip, "n_used": n_used, "voxel": used_voxel,
           "classified_las": clf, "class_counts": counts,
           "n_building_in_fp": int((bmask & infp).sum()),
           "plane_rms": rms, "roof_density": roof_dens, "footprint_area": float(area)}
    json.dump(out, open(f"{A.outdir}/{A.bid}_{A.tag}_metrics.json", "w"))
    print(f"[prep] {A.bid} {A.tag}: clip={n_clip} used={n_used} building_fp={out['n_building_in_fp']} "
          f"rms={rms} dens={roof_dens}")


if __name__ == "__main__":
    main()
