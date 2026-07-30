#!/usr/bin/env python3
"""P2-D6 step0 — supplementary (b)x(c) cross-test: voxel-downsample GS to LiDAR density, keep
classification, so the SAME Roofer (d6_densmatch_roofer.py) can separate DENSITY from THRESHOLD.

If GS@LiDAR-density facets stay high (~14) -> the curved over-seg is NOT the 33x density (input
waviness / Roofer threshold). If they drop toward LiDAR's 5 -> density is the driver. Mirrors the
v6 density-match method (v6_density_downsample.py) but on the cp-fair D4 gssem canonical clouds and
the curved target 4906969 (+ controls). Writes downsampled classified LAS for Roofer.

Runs in jointbuildgs-p0-tools:t0 (laspy + numpy). EPSG:25832. Observation only; verdict = 김휘영.
Out LAS: phases/p0-audit/runs/_d6_density/<arm>/DEBY_LOD2_<bid>_lidarD.las
"""
import csv, json
from pathlib import Path
import numpy as np, laspy

REPO = Path("/workspace/JointBuildGS")
EVAL = REPO / "phases/p0-audit/runs/mob_eval"
OUTRUN = REPO / "phases/p0-audit/runs/_d6_density"
PACK = REPO / "results/tum_transfer/mob/analysis_pack_d6"
TARGETS = ["4906969", "42364659", "4906972"]
ARMS = ["gs_d4_dense", "gs_d4_acmp"]


def voxel_idx(P, v):
    q = np.floor(P / v).astype(np.int64)
    OFF, MUL = 1 << 20, 1 << 21
    key = ((q[:, 0] + OFF) * MUL + (q[:, 1] + OFF)) * MUL + (q[:, 2] + OFF)
    _, idx = np.unique(key, return_index=True)
    return idx


def read_las(path):
    c = laspy.read(path)
    P = np.column_stack([np.asarray(c.x), np.asarray(c.y), np.asarray(c.z)])
    return P, np.asarray(c.classification)


def area_of(geo, bid):
    g = [f for f in geo if f["properties"]["building_id"] == f"DEBY_LOD2_{bid}"][0]["geometry"]
    r = np.asarray(g["coordinates"][0] if g["type"] == "Polygon" else g["coordinates"][0][0])
    return 0.5 * abs(np.dot(r[:, 0], np.roll(r[:, 1], -1)) - np.dot(r[:, 1], np.roll(r[:, 0], -1)))


def write_las(P, cls, path):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    h = laspy.LasHeader(point_format=6, version="1.4")
    h.offsets = [P[:, 0].min(), P[:, 1].min(), P[:, 2].min()]; h.scales = [0.001, 0.001, 0.001]
    las = laspy.LasData(h); las.x, las.y, las.z = P[:, 0], P[:, 1], P[:, 2]
    las.classification = cls.astype(np.uint8); las.write(path)


def main():
    geo = json.load(open(REPO / "results/tum_transfer/analysis/footprints_aoi.geojson"))["features"]
    rows = []
    for bid in TARGETS:
        A = area_of(geo, bid)
        Pld, cld = read_las(EVAL / "raw_lidar" / f"DEBY_LOD2_{bid}_orig_classified.las")
        tgt_dens = int((cld == 6).sum()) / A
        target_n = tgt_dens * A
        for arm in ARMS:
            Pall, cls = read_las(EVAL / arm / f"DEBY_LOD2_{bid}_orig_classified.las")
            lo, hi = 0.02, 6.0
            for _ in range(24):
                mid = float(np.sqrt(lo * hi))
                c6 = int((cls[voxel_idx(Pall, mid)] == 6).sum())
                if c6 > target_n:
                    lo = mid
                else:
                    hi = mid
            vox = float(np.sqrt(lo * hi)); idx = voxel_idx(Pall, vox)
            Ps, cs = Pall[idx], cls[idx]
            out = OUTRUN / arm / f"DEBY_LOD2_{bid}_lidarD.las"
            write_las(Ps, cs, str(out))
            n6 = int((cs == 6).sum())
            rows.append({"bid": bid, "arm": arm, "voxel_m": round(vox, 3), "lidar_dens": round(tgt_dens, 1),
                         "n6_lidarD": n6, "dens_lidarD": round(n6 / A, 1), "las": str(out)})
            print(f"{bid} {arm:12} vox={vox:.3f} lidar_dens={tgt_dens:.1f} -> n6={n6} dens={n6/A:.1f}")
    PACK.mkdir(parents=True, exist_ok=True)
    with open(PACK / "density_match_d6.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["bid", "arm", "voxel_m", "lidar_dens", "n6_lidarD",
                                          "dens_lidarD", "las"])
        w.writeheader(); w.writerows(rows)
    print(f"\n[done] -> {PACK}/density_match_d6.csv")


if __name__ == "__main__":
    main()
