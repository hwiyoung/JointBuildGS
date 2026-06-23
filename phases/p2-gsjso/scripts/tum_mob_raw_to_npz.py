#!/usr/bin/env python3
"""P2 make-or-break v6 — convert a RAW point cloud to the P_utm npz that tum_mob_eval/_mob_prep_las
consume, so the raw baselines (sparse/dense/ACMP/LiDAR) go through the IDENTICAL classify->Roofer->
val3dity->facet/RMS harness as the GS arm (8-way apples-to-apples).

Datum: all outputs in ELLIPSOIDAL UTM (= GS-LOCAL + [690953,5336071,604]) to match the GS TSDF
clouds, so the Phase-4 ref-RMS dz search (dz in [40,56] ~= +48 geoid vs orthometric LoD2) locks.
  sparse = COLMAP points3D (GS-LOCAL) + [690953,5336071,604]            -> ellipsoidal
  dense  = dim_v1.laz   (already ellipsoidal UTM, local+604)            -> as-is
  acmp   = acmp_aoi_utm.laz (orthometric, local+556) + Z 48             -> ellipsoidal
  lidar  = als_aoi.laz  (orthometric)               + Z 48             -> ellipsoidal
Runs in jointbuildgs-p0-tools:t0 (laspy + numpy). Observation only. EPSG:25832.
"""
import argparse
from pathlib import Path

import numpy as np

R = "/workspace/JointBuildGS"
AOI = (690766.0, 691180.0, 5335839.0, 5336379.0)   # x0,x1,y0,y1 (UTM)
SHIFT = np.array([690953.0, 5336071.0, 604.0])      # GS-LOCAL -> ellipsoidal UTM
GEOID = 48.0                                          # orthometric -> ellipsoidal


def voxel_ds(P, v):
    q = np.floor(P / v).astype(np.int64)
    OFF, MUL = 1 << 20, 1 << 21
    key = ((q[:, 0] + OFF) * MUL + (q[:, 1] + OFF)) * MUL + (q[:, 2] + OFF)
    _, idx = np.unique(key, return_index=True)
    return P[idx]


def crop_aoi(P):
    m = (P[:, 0] >= AOI[0]) & (P[:, 0] <= AOI[1]) & (P[:, 1] >= AOI[2]) & (P[:, 1] <= AOI[3])
    return P[m]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cloud", required=True, choices=["sparse", "dense", "acmp", "lidar"])
    ap.add_argument("--out", required=True)
    ap.add_argument("--voxel", type=float, default=0.10, help="downsample for dense/acmp only")
    A = ap.parse_args()

    if A.cloud == "sparse":
        txt = f"{R}/phases/p0-audit/data/work/mvs/openmvs/colmap_txt/sparse/points3D.txt"
        xyz = []
        for line in open(txt):
            if line.startswith("#") or not line.strip():
                continue
            p = line.split()
            xyz.append((float(p[1]), float(p[2]), float(p[3])))
        P = np.asarray(xyz, dtype=np.float64) + SHIFT       # GS-LOCAL -> ellipsoidal UTM
        P = crop_aoi(P); vx = None
    else:
        import laspy
        path = {
            "dense": f"{R}/phases/p0-audit/data/work/mvs/dim/dim_v1.laz",
            "acmp": f"{R}/results/tum_transfer/mob_analysis/p0c_step2/acmp_aoi_utm.laz",
            "lidar": f"{R}/results/tum_transfer/mob_analysis/p0c_step2/als_aoi.laz",
        }[A.cloud]
        f = laspy.read(path)
        P = np.column_stack([np.asarray(f.x), np.asarray(f.y), np.asarray(f.z)]).astype(np.float64)
        if A.cloud in ("acmp", "lidar"):
            P[:, 2] += GEOID                                # orthometric -> ellipsoidal
        P = crop_aoi(P); vx = None
        if A.cloud in ("dense", "acmp"):
            n0 = len(P); P = voxel_ds(P, A.voxel); vx = A.voxel
            print(f"[raw:{A.cloud}] voxel {A.voxel}: {n0} -> {len(P)}")

    Path(A.out).parent.mkdir(parents=True, exist_ok=True)
    np.savez(A.out, P_utm=P)
    print(f"[raw:{A.cloud}] N={len(P)} voxel={vx} "
          f"Z[{P[:,2].min():.1f}..{P[:,2].max():.1f}] -> {A.out}")


if __name__ == "__main__":
    main()
