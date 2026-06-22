#!/usr/bin/env python3
"""P2 textureless-signal diagnosis — Part A: characterize EXISTING points per footprint.

For the 5 textureless + 3 control buildings, clip COLMAP SfM points (full fields: reproj error,
track length) and the DIM/MVS cloud to each footprint, and report:
  count / confidence (SfM error+track dist; DIM density) / location (edge=eave vs interior) /
  z - true_roof (median, dist) / # CONFIDENT points within +-2 m of the true roof (and edge share).
Observation only. Runs in P0 tools container (numpy, laspy, shapely, matplotlib). EPSG:25832.

Frames -> all compared in GS-local z (ref_roof_local = h_roof + geoid - 604):
  SfM  : GS-local (ellipsoidal). xy_utm = xy_local + shift_xy.  dz = z_local - ref_roof_local.
  DIM  : orthometric UTM.        dz = z_ortho - h_roof  (geoid cancels).
"""
import argparse, csv, json, struct
from pathlib import Path
import numpy as np, laspy
from shapely.geometry import Polygon, Point
from matplotlib.path import Path as MplPath
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt

REPO = "/workspace/JointBuildGS"
SHIFT = np.array([690953.0, 5336071.0, 604.0]); GEOID = 48.0
NOSEED = ["42364609", "4907182", "4908050", "4908166", "4908176"]
CTRL = ["42364659", "42364663", "4907510"]
ALLB = NOSEED + CTRL
ERR_MAX, TRK_MIN, NEAR = 2.0, 3, 2.0   # confident = err<=2px & track>=3 ; near-roof = |dz|<=2 m
EDGE_BUF = 1.5                          # within 1.5 m of footprint boundary = eave/edge


def read_points3d_full(path):
    xyz, err, trk = [], [], []
    with open(path, "rb") as f:
        (n,) = struct.unpack("<Q", f.read(8))
        for _ in range(n):
            f.read(8)                                  # point id
            x, y, z = struct.unpack("<ddd", f.read(24))
            f.read(3)                                  # rgb
            (e,) = struct.unpack("<d", f.read(8))      # reprojection error
            (tl,) = struct.unpack("<Q", f.read(8))     # track length
            f.read(8 * tl)                             # track (image_id, pt2d_idx)*tl
            xyz.append((x, y, z)); err.append(e); trk.append(tl)
    return np.asarray(xyz), np.asarray(err), np.asarray(trk, np.int64)


def main():
    geo = json.load(open(f"{REPO}/results/tum_transfer/analysis/footprints_aoi.geojson"))["features"]
    refh = {r["building_id"]: r for r in csv.DictReader(open(f"{REPO}/results/tum_transfer/mob_analysis/ref_roof_heights.csv"))}
    sfm_xyz, sfm_err, sfm_trk = read_points3d_full(f"{REPO}/phases/p0-audit/data/work/mvs/colmap_dense/sparse/points3D.bin")
    sfm_utm = sfm_xyz + SHIFT                                   # for footprint (UTM) test
    dim = np.load(f"{REPO}/results/tum_transfer/mob_analysis/mvs.npz")["P_utm_clean"]  # orthometric UTM

    rows = []
    fig, axes = plt.subplots(2, 4, figsize=(18, 9))
    for i, b in enumerate(ALLB):
        bid = f"DEBY_LOD2_{b}"
        g = [f for f in geo if f["properties"]["building_id"] == bid][0]["geometry"]
        ring = np.asarray(g["coordinates"][0] if g["type"] == "Polygon" else g["coordinates"][0][0])[:, :2]
        poly = Polygon(ring); interior = poly.buffer(-EDGE_BUF)
        area = poly.area
        fp_path = MplPath(ring)
        # interior polygon -> path(s) for a vectorized edge test (may be empty for tiny buildings)
        int_paths = []
        if not interior.is_empty:
            geoms = interior.geoms if interior.geom_type == "MultiPolygon" else [interior]
            int_paths = [MplPath(np.asarray(gm.exterior.coords)) for gm in geoms]

        def in_interior(xy):
            if not len(xy):
                return np.zeros(0, bool)
            m = np.zeros(len(xy), bool)
            for p in int_paths:
                m |= p.contains_points(xy)
            return m

        h_roof = float(refh[bid]["h_roof"]); roof_local = h_roof + GEOID - 604.0

        # ---- SfM ---- (vectorized footprint + edge test)
        inb = fp_path.contains_points(sfm_utm[:, :2]) if len(sfm_utm) else np.zeros(0, bool)
        s_xyz, s_err, s_trk = sfm_xyz[inb], sfm_err[inb], sfm_trk[inb]
        s_dz = s_xyz[:, 2] - roof_local
        s_edge = ~in_interior(sfm_utm[inb][:, :2]) if len(s_xyz) else np.zeros(0, bool)
        conf = (s_err <= ERR_MAX) & (s_trk >= TRK_MIN)
        near = np.abs(s_dz) <= NEAR
        conf_near = conf & near
        # ---- DIM ----
        dmask = fp_path.contains_points(dim[:, :2]) if len(dim) else np.zeros(0, bool)
        d_dz = dim[dmask, 2] - h_roof
        d_near = np.abs(d_dz) <= NEAR

        row = dict(bid=bid, klass=("no-seed" if b in NOSEED else "control"), area_m2=round(area, 1),
                   ref_roof_local=round(roof_local, 2),
                   sfm_n=int(len(s_xyz)),
                   sfm_err_med=(round(float(np.median(s_err)), 2) if len(s_err) else None),
                   sfm_trk_med=(int(np.median(s_trk)) if len(s_trk) else None),
                   sfm_edge_frac=(round(float(s_edge.mean()), 2) if len(s_xyz) else None),
                   sfm_dz_med=(round(float(np.median(s_dz)), 1) if len(s_dz) else None),
                   sfm_conf=int(conf.sum()),
                   sfm_conf_near_roof=int(conf_near.sum()),
                   sfm_conf_near_roof_interior=int((conf_near & ~s_edge).sum()) if len(s_xyz) else 0,
                   dim_n=int(dmask.sum()), dim_density=round(float(dmask.sum() / area), 1),
                   dim_dz_med=(round(float(np.median(d_dz)), 1) if dmask.sum() else None),
                   dim_near_roof=int(d_near.sum()))
        rows.append(row)
        print(f"{bid} {row['klass']}: SfM n={row['sfm_n']} (conf={row['sfm_conf']}, "
              f"conf&near-roof={row['sfm_conf_near_roof']} [interior={row['sfm_conf_near_roof_interior']}]) "
              f"err_med={row['sfm_err_med']} trk_med={row['sfm_trk_med']} edge%={row['sfm_edge_frac']} "
              f"dz_med={row['sfm_dz_med']} | DIM n={row['dim_n']} dz_med={row['dim_dz_med']} near={row['dim_near_roof']}")

        # ---- figure: footprint + SfM (interior/edge) + DIM faint, with roof line context ----
        ax = axes[i // 4, i % 4]
        ax.plot(*poly.exterior.xy, "k-", lw=1)
        if interior.geom_type == "Polygon" and not interior.is_empty:
            ax.plot(*interior.exterior.xy, "k:", lw=0.6)
        if dmask.sum():
            ax.scatter(dim[dmask, 0], dim[dmask, 1], s=2, c="#cccccc", label=f"DIM({dmask.sum()})")
        if len(s_xyz):
            u = sfm_utm[inb]
            ax.scatter(u[~s_edge, 0], u[~s_edge, 1], s=22, c="#1f77b4", label=f"SfM int({int((~s_edge).sum())})")
            ax.scatter(u[s_edge, 0], u[s_edge, 1], s=22, c="#ff7f0e", label=f"SfM edge({int(s_edge.sum())})")
            cn = conf_near
            if cn.any():
                ax.scatter(u[cn, 0], u[cn, 1], s=60, facecolors="none", edgecolors="r", lw=1.3,
                           label=f"conf&near-roof({int(cn.sum())})")
        ax.set_title(f"{b} ({row['klass']}) area={area:.0f}m²\nSfM {row['sfm_n']} conf{row['sfm_conf']} dz~{row['sfm_dz_med']}m",
                     fontsize=8)
        ax.set_aspect("equal"); ax.set_xticks([]); ax.set_yticks([]); ax.legend(fontsize=5, loc="upper right")
    fig.suptitle("Part A — existing points in footprint: SfM interior(blue)/edge(orange), conf&near-roof(red ring), DIM(grey)", fontsize=11)
    fig.tight_layout()
    fig.savefig(f"{REPO}/docs/figs/tum_transfer/textureless_signal_A.png", dpi=110); plt.close(fig)

    out = f"{REPO}/results/tum_transfer/mob_analysis/textureless_signal_A"
    json.dump(rows, open(out + ".json", "w"), indent=2)
    with open(out + ".csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
    print(f"[done] -> {out}.csv/.json + docs/figs/tum_transfer/textureless_signal_A.png")


if __name__ == "__main__":
    main()
