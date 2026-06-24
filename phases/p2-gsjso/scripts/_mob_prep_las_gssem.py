#!/usr/bin/env python3
"""P2-D Lever 3 — GS-SEMANTIC classification read-out (SMRF replacement).

Drop-in for _mob_prep_las.py (same CLI + same metrics json), but ground/building labels come
from the per-point GS semantic argmax carried through TSDF fusion (npz key P_class_clean), NOT
from PDAL filters.smrf + GT-footprint overlay. Mapping (engine K=4: 0 BG/1 Roof/2 Wall/3 Terrain):
    Roof(1), Wall(2) -> BUILDING(6)   |   Terrain(3) -> GROUND(2)   |   BG(0) -> dropped.
Because GS Terrain is sparse (~2%), a DATA-DERIVED ground base (grid at the low-percentile Z over
the GS building XY extent — NOT the GT footprint polygon) is synthesised so Roofer can seat walls.

GT separation (root CLAUDE.md §4-9): building=6 comes ONLY from GS semantics; the footprint is used
solely for eval-side metrics + Roofer's per-building crop, never to assign the building class.
Runs in the P0 tools container (laspy + numpy + matplotlib). EPSG:25832.
"""
import argparse, json, os
import numpy as np, laspy
from matplotlib.path import Path as MplPath

GROUND, BUILDING, UNCLASS = 2, 6, 1
BG, ROOF, WALL, TERRAIN = 0, 1, 2, 3


def voxel_downsample_idx(P, voxel):
    """Return indices of one representative point per occupied voxel (keeps class alignment)."""
    q = np.floor(P / voxel).astype(np.int64)
    OFF, MUL = 1 << 20, 1 << 21
    key = ((q[:, 0] + OFF) * MUL + (q[:, 1] + OFF)) * MUL + (q[:, 2] + OFF)
    _, idx = np.unique(key, return_index=True)
    return idx


def plane_rms(P):
    if len(P) < 10:
        return None
    c = P.mean(0); Q = P - c
    _, _, Vt = np.linalg.svd(Q, full_matrices=False)
    n = Vt[-1]
    d = Q @ n
    return float(np.sqrt((d ** 2).mean()))


def synth_ground(build_xy, ground_z, spacing=2.0, pad=2.0):
    """Coarse ground grid at `ground_z` over the GS building XY extent (data-derived, not GT footprint)."""
    if len(build_xy) == 0:
        return np.zeros((0, 3))
    x0, y0 = build_xy.min(0) - pad
    x1, y1 = build_xy.max(0) + pad
    xs = np.arange(x0, x1 + spacing, spacing)
    ys = np.arange(y0, y1 + spacing, spacing)
    gx, gy = np.meshgrid(xs, ys)
    return np.column_stack([gx.ravel(), gy.ravel(), np.full(gx.size, ground_z)])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tsdf", required=True)
    ap.add_argument("--bid", required=True)
    ap.add_argument("--geojson", required=True)
    ap.add_argument("--buffer", type=float, default=15.0)
    ap.add_argument("--target-density", type=float, default=0.0,
                    help="ALS roof pts/m^2; >0 -> voxel-downsample so GS in-fp density matches ALS")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--outdir", required=True)
    ap.add_argument("--tag", default="orig")
    ap.add_argument("--min-ground", type=int, default=200,
                    help="if GS Terrain ground points < this, synthesise a data-derived ground base")
    ap.add_argument("--synth-spacing", type=float, default=2.0)
    A = ap.parse_args()
    os.makedirs(A.outdir, exist_ok=True)

    npz = np.load(A.tsdf, allow_pickle=True)
    if "P_class_clean" not in npz:
        raise SystemExit(f"[gssem] {A.tsdf} has no P_class_clean — re-run tum_mob_tsdf_extract.py "
                         f"WITHOUT --no-sem (the GS-semantic classifier needs per-point class).")
    TS = npz["P_utm_clean"] if "P_utm_clean" in npz else npz["P_utm"]
    CL = npz["P_class_clean"].astype(np.int64)
    assert len(TS) == len(CL), f"point/class length mismatch {len(TS)} vs {len(CL)}"

    feats = json.load(open(A.geojson))["features"]
    fb = [f for f in feats if f["properties"]["building_id"] == A.bid]
    geom = fb[0]["geometry"]
    ring = np.asarray(geom["coordinates"][0] if geom["type"] == "Polygon" else geom["coordinates"][0][0])
    x0, y0, x1, y1 = ring[:, 0].min(), ring[:, 1].min(), ring[:, 0].max(), ring[:, 1].max()
    fp = MplPath(ring[:, :2])
    area = 0.5 * abs(np.dot(ring[:, 0], np.roll(ring[:, 1], -1)) - np.dot(ring[:, 1], np.roll(ring[:, 0], -1)))

    m = ((TS[:, 0] >= x0 - A.buffer) & (TS[:, 0] <= x1 + A.buffer)
         & (TS[:, 1] >= y0 - A.buffer) & (TS[:, 1] <= y1 + A.buffer))
    P = TS[m]; C = CL[m]
    n_clip = len(P)
    used_voxel = None
    if A.target_density > 0 and n_clip > 0 and area > 0:
        # voxel-downsample so GS in-footprint areal density matches ALS (identical knob to the SMRF arm)
        lo, hi = 0.05, 2.0
        for _ in range(14):
            mid = float(np.sqrt(lo * hi))
            idx = voxel_downsample_idx(P, mid)
            dens = fp.contains_points(P[idx][:, :2]).sum() / area
            if dens > A.target_density:
                lo = mid
            else:
                hi = mid
        used_voxel = float(np.sqrt(lo * hi))
        idx = voxel_downsample_idx(P, used_voxel)
        P = P[idx]; C = C[idx]
    n_used = len(P)

    # --- GS-semantic class -> LAS Classification (NO smrf, NO footprint-overlay for building) ---
    is_build = (C == ROOF) | (C == WALL)
    is_terr = (C == TERRAIN)
    build_pts = P[is_build]
    terr_pts = P[is_terr]

    if len(build_pts) < 4:
        print(f"[gssem] {A.bid} {A.tag}: too few GS building points ({len(build_pts)})")
        json.dump({"bid": A.bid, "tag": A.tag, "n_clip": n_clip, "n_used": n_used,
                   "classified_las": None, "plane_rms": None, "roof_density": None,
                   "classifier": "gssem"},
                  open(f"{A.outdir}/{A.bid}_{A.tag}_metrics.json", "w"))
        return

    # ground = GS Terrain + (if sparse) a data-derived synthetic base under the building extent
    ground_pts = terr_pts
    n_synth = 0
    if len(terr_pts) >= 10:
        ground_z = float(np.median(terr_pts[:, 2]))
    else:
        ground_z = float(np.percentile(build_pts[:, 2], 5))
    if len(terr_pts) < A.min_ground:
        synth = synth_ground(build_pts[:, :2], ground_z, spacing=A.synth_spacing)
        n_synth = len(synth)
        ground_pts = np.vstack([terr_pts, synth]) if len(terr_pts) else synth

    allP = np.vstack([build_pts, ground_pts])
    allC = np.concatenate([np.full(len(build_pts), BUILDING, np.uint8),
                           np.full(len(ground_pts), GROUND, np.uint8)])

    clf = f"{A.outdir}/{A.bid}_{A.tag}_classified.las"
    hdr = laspy.LasHeader(point_format=6, version="1.4")
    hdr.offsets = [allP[:, 0].min(), allP[:, 1].min(), allP[:, 2].min()]
    hdr.scales = [0.001, 0.001, 0.001]
    las = laspy.LasData(hdr)
    las.x = allP[:, 0]; las.y = allP[:, 1]; las.z = allP[:, 2]
    las.classification = allC
    try:  # tag EPSG:25832 (coords are already in it); harmless if pyproj/CRS VLR unavailable
        las.header.add_crs(__import__("pyproj").CRS.from_epsg(25832))
    except Exception:
        pass
    las.write(clf)

    # --- metrics (footprint used for EVAL only) ---
    infp = fp.contains_points(build_pts[:, :2])
    roofpts = build_pts[infp]
    rms = plane_rms(roofpts)
    roof_dens = (int(infp.sum()) / area) if area > 0 else None
    real_counts = {int(k): int(v) for k, v in zip(*np.unique(C, return_counts=True))}
    out = {"bid": A.bid, "tag": A.tag, "n_clip": n_clip, "n_used": n_used, "voxel": used_voxel,
           "classified_las": clf, "classifier": "gssem",
           "gs_class_counts": real_counts,
           "n_building": int(len(build_pts)), "n_terrain": int(len(terr_pts)), "n_synth_ground": int(n_synth),
           "ground_z": ground_z,
           "n_building_in_fp": int(infp.sum()),
           "plane_rms": rms, "roof_density": roof_dens, "footprint_area": float(area)}
    json.dump(out, open(f"{A.outdir}/{A.bid}_{A.tag}_metrics.json", "w"))
    print(f"[gssem] {A.bid} {A.tag}: clip={n_clip} used={n_used} build={len(build_pts)} "
          f"terr={len(terr_pts)} synth={n_synth} build_in_fp={out['n_building_in_fp']} rms={rms} dens={roof_dens}")


if __name__ == "__main__":
    main()
