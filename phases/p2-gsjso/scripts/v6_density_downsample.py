#!/usr/bin/env python3
"""P2 v6 density-match §1 — voxel-downsample GS classified clouds to raw_dense & LiDAR density
(keep classification), so the same Roofer can be re-run to separate density vs surface-waviness.
Read-only of inputs; writes downsampled LAS + a metrics CSV. p0-tools (laspy+numpy). Observation only.

For bids {4906972, 42364663(control)} x arms {gs_seed_dense, gs_seed_acmp} x levels {orig, rawD, lidarD}:
  - read the GS orig classified LAS (the cloud used in diagnosis A)
  - downsample ALL points by a voxel grid (bisected) so building(class6)-in-fp density == target
    (target = raw_dense / raw_lidar building density for that building); orig = no downsample
  - write downsampled classified LAS to phases/p0-audit/runs/mob_eval_density/<arm>/<bid>_<level>.las
  - re-measure on class6: n, plane_rms, patch_rms(2m within), nDisp(2m between), ransac plane count
Out LAS (for Roofer) + results/tum_transfer/mob/analysis_pack_v6/density_match_metrics.csv
"""
import csv, json, sys
from pathlib import Path

sys.path.insert(0, "/workspace/JointBuildGS/phases/p2-gsjso/scripts")
import numpy as np, laspy
from p0c_assembly_diag import plane_rms
from v6_overseg_diag import cell_normals, ransac_planes

REPO = "/workspace/JointBuildGS"
EVAL = f"{REPO}/phases/p0-audit/runs/mob_eval"
OUTRUN = f"{REPO}/phases/p0-audit/runs/mob_eval_density"
PACK = f"{REPO}/results/tum_transfer/mob/analysis_pack_v6"
BIDS = ["4906972", "42364663"]
ARMS = ["gs_seed_dense", "gs_seed_acmp"]


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


def measure(P6):
    if len(P6) < 12:
        return dict(plane_rms_m=None, patch_rms_med_m=None, normal_disp_deg=None, ransac_planes=None)
    nrm, lrms = cell_normals(P6)
    nd = None
    if len(nrm) >= 2:
        ndom = nrm.mean(0); ndom /= np.linalg.norm(ndom) + 1e-12
        ang = np.degrees(np.arccos(np.clip(np.abs(nrm @ ndom), 0, 1)))
        nd = round(float(ang.std()), 2)
    return dict(plane_rms_m=round(plane_rms(P6), 3),
                patch_rms_med_m=(round(float(np.median(lrms)), 3) if len(lrms) else None),
                normal_disp_deg=nd, ransac_planes=ransac_planes(P6))


def write_las(P, cls, path):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    h = laspy.LasHeader(point_format=6, version="1.4")
    h.offsets = [P[:, 0].min(), P[:, 1].min(), P[:, 2].min()]; h.scales = [0.001, 0.001, 0.001]
    las = laspy.LasData(h); las.x, las.y, las.z = P[:, 0], P[:, 1], P[:, 2]
    las.classification = cls.astype(np.uint8); las.write(path)


def main():
    geo = json.load(open(f"{REPO}/results/tum_transfer/analysis/footprints_aoi.geojson"))["features"]
    rows = []
    for bid in BIDS:
        A = area_of(geo, bid)
        # target densities from raw_dense / raw_lidar orig class6 counts
        Prd, crd = read_las(f"{EVAL}/raw_dense/DEBY_LOD2_{bid}_orig_classified.las")
        Pld, cld = read_las(f"{EVAL}/raw_lidar/DEBY_LOD2_{bid}_orig_classified.las")
        tgt = {"rawD": int((crd == 6).sum()) / A, "lidarD": int((cld == 6).sum()) / A}
        for arm in ARMS:
            Pall, cls = read_las(f"{EVAL}/{arm}/DEBY_LOD2_{bid}_orig_classified.las")
            for level in ["orig", "rawD", "lidarD"]:
                if level == "orig":
                    Ps, cs, vox = Pall, cls, None
                else:
                    target_n = tgt[level] * A
                    lo, hi = 0.02, 6.0
                    for _ in range(22):
                        mid = float(np.sqrt(lo * hi))
                        idx = voxel_idx(Pall, mid)
                        c6 = int((cls[idx] == 6).sum())
                        if c6 > target_n:
                            lo = mid
                        else:
                            hi = mid
                    vox = float(np.sqrt(lo * hi)); idx = voxel_idx(Pall, vox)
                    Ps, cs = Pall[idx], cls[idx]
                outlas = f"{OUTRUN}/{arm}/DEBY_LOD2_{bid}_{level}.las"
                write_las(Ps, cs, outlas)
                P6 = Ps[cs == 6]
                m = measure(P6)
                row = {"building": bid, "arm": arm, "level": level,
                       "target_density": (round(tgt.get(level), 1) if level != "orig" else "orig"),
                       "voxel_m": (round(vox, 3) if vox else 0), "n_b6": int(len(P6)),
                       "density_pps_m2": round(len(P6) / A, 1), **m, "las": outlas}
                rows.append(row)
                print(f"{bid} {arm:13} {level:6} vox={row['voxel_m']:>6} n_b6={row['n_b6']:>8} "
                      f"dens={row['density_pps_m2']:>7} patchRMS={m['patch_rms_med_m']} "
                      f"nDisp={m['normal_disp_deg']} ransac={m['ransac_planes']}")

    Path(PACK).mkdir(parents=True, exist_ok=True)
    keys = ["building", "arm", "level", "target_density", "voxel_m", "n_b6", "density_pps_m2",
            "plane_rms_m", "patch_rms_med_m", "normal_disp_deg", "ransac_planes", "las"]
    with open(f"{PACK}/density_match_metrics.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=keys); w.writeheader(); w.writerows(rows)
    print(f"\n[done] {len(rows)} rows -> {PACK}/density_match_metrics.csv  (+ LAS in {OUTRUN})")


if __name__ == "__main__":
    main()
