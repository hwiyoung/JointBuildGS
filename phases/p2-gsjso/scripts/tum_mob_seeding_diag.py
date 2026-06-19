#!/usr/bin/env python3
"""P2 make-or-break — recovery cause diagnosis: did GS reconstruct a surface at all?

z-offset-immune (footprint xy only): the GS/OPF frame is ELLIPSOIDAL height, the GML/ALS frame
is ORTHOMETRIC (DHHN), a ~+48 m geoid offset, so absolute-z comparisons are meaningless here —
we ask "are there GS surface points in the footprint column, at any height".

Reports per building: SfM init points (COLMAP points3D) in footprint, and TSDF surface points in
footprint per ablation arm (+ their z-median), to test the seeding hypothesis for the 8 textureless
buildings. Runs in P0 tools container (numpy + matplotlib; reads npz + points3D via stdlib struct).
"""
import json, struct, sys
import numpy as np
from matplotlib.path import Path as MplPath

REPO = "/workspace/JointBuildGS"
TARGETS = ["42364609", "42364659", "42364663", "4907182", "4907510", "4908050",
           "4908166", "4908176", "4906969", "4908023", "4906972"]
RECOVERY = {"42364609", "42364659", "42364663", "4907182", "4907510", "4908050", "4908166", "4908176"}
ARMS = ["vanilla", "baseline", "mutual", "structure", "both"]
SHIFT = np.array([690953.0, 5336071.0, 604.0])


def read_points3d_xyz(path):
    out = []
    with open(path, "rb") as f:
        (n,) = struct.unpack("<Q", f.read(8))
        for _ in range(n):
            f.read(8)  # id
            xyz = struct.unpack("<ddd", f.read(24))
            f.read(3 + 8)  # rgb + err
            (tl,) = struct.unpack("<Q", f.read(8))
            f.read(8 * tl)
            out.append(xyz)
    return np.asarray(out)  # GS-local


def ring_utm(geo, bid):
    g = [f for f in geo if f["properties"]["building_id"] == bid][0]["geometry"]
    return np.asarray(g["coordinates"][0] if g["type"] == "Polygon" else g["coordinates"][0][0])[:, :2]


def main():
    geo = json.load(open(f"{REPO}/results/tum_transfer/analysis/footprints_aoi.geojson"))["features"]
    sfm_local = read_points3d_xyz(f"{REPO}/phases/p0-audit/data/work/mvs/colmap_dense/sparse/points3D.bin")
    sfm_utm = sfm_local + SHIFT
    tsdf = {a: np.load(f"{REPO}/results/tum_transfer/mob/tsdf_{a}.npz")["P_utm_clean"] for a in ARMS}

    rows = []
    print(f"{'building':20} {'rec':4} {'sfm_fp':>7} | " + " ".join(f"{a[:5]:>7}" for a in ARMS) + "   (TSDF surface pts in footprint, any z)")
    for t in TARGETS:
        bid = f"DEBY_LOD2_{t}"
        fp = MplPath(ring_utm(geo, bid))
        n_sfm = int(fp.contains_points(sfm_utm[:, :2]).sum())
        per = {}
        for a in ARMS:
            P = tsdf[a]; inb = fp.contains_points(P[:, :2])
            per[a] = int(inb.sum())
        rows.append({"building": bid, "is_recovery": t in RECOVERY, "sfm_in_fp": n_sfm,
                     **{f"tsdf_{a}": per[a] for a in ARMS}})
        print(f"{bid:20} {'REC' if t in RECOVERY else 'qual':4} {n_sfm:>7} | "
              + " ".join(f"{per[a]:>7}" for a in ARMS))
    json.dump(rows, open(f"{REPO}/results/tum_transfer/mob_analysis/seeding_diag.json", "w"), indent=2)
    print("[done] -> results/tum_transfer/mob_analysis/seeding_diag.json")


if __name__ == "__main__":
    main()
