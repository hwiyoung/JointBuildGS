#!/usr/bin/env python3
"""P2-D6 step0 — CLEAN (gssem-canonical) curved-roof over-seg re-diagnosis: components (a)+(b).

Re-runs the v6 over-seg diagnosis on the gssem CANONICAL roof points (the v6 study read SMRF
points; see W_D6 §0 integrity check). Decomposes the GS-vs-LiDAR roof-FACET gap into:
  (a) input roughness   — per-cell local-plane-fit residual (RMS, p90) + between-cell normal
                          dispersion nDisp + global dominant-plane RMS. GS vs LiDAR, same scale.
  (b) density/distrib   — roof-point density (pts/m^2) + hole ratio (empty footprint cells).
A density-matched GS variant (voxel-downsampled to LiDAR density) isolates roughness from density.
(c) Roofer threshold sweep is in d6_roofer_sweep.py.

Targets: curved 4906969 (+ controls composite 42364659, flat 4906972).
Sources: GS = gs_d4_{dense,acmp} (cp-fair D4). gssem = canonical disk; smrf = regenerated temp
         (phases/p0-audit/runs/_d6_smrf_tmp, written by run_d6_step0.sh). LiDAR = raw_lidar.
Roof points = classification==6 inside the GT footprint polygon (point-in-polygon).

Runs in jointbuildgs-p0-tools:t0 (numpy + laspy + matplotlib; NO scipy). EPSG:25832.
Observation only; verdict = 김휘영. Out: results/.../analysis_pack_d6/overseg_diag_d6.csv + figs.
"""
import csv, json
from pathlib import Path
import numpy as np, laspy
import matplotlib; matplotlib.use("Agg")
from matplotlib.path import Path as MplPath  # point-in-polygon (figures live in d6_figs.py)

REPO = Path("/workspace/JointBuildGS")
EVALROOT = REPO / "phases/p0-audit/runs/mob_eval"
SMRF_TMP = REPO / "phases/p0-audit/runs/_d6_smrf_tmp"
GEOJSON = REPO / "results/tum_transfer/analysis/footprints_aoi.geojson"
OUT = REPO / "results/tum_transfer/mob/analysis_pack_d6"
FIGDIR = REPO / "docs/figs/W_D6"

TARGETS = [("4906969", "curved"), ("42364659", "composite"), ("4906972", "flat")]
# (label, classifier, evalroot, arm)
SOURCES = [
    ("GS_dense", "gssem", EVALROOT, "gs_d4_dense"),
    ("GS_acmp",  "gssem", EVALROOT, "gs_d4_acmp"),
    ("GS_dense", "smrf",  SMRF_TMP, "gs_d4_dense"),
    ("GS_acmp",  "smrf",  SMRF_TMP, "gs_d4_acmp"),
    ("LiDAR",    "lidar", EVALROOT, "raw_lidar"),
]
CELL = 1.5      # local-plane-fit cell (m)
MINPTS = 6      # min points per cell for a PCA plane
HOLE_CELL = 1.0  # grid cell for hole-ratio (m)


def footprint(bid_short):
    full = f"DEBY_LOD2_{bid_short}"
    feats = json.load(open(GEOJSON))["features"]
    paths, area = [], 0.0
    for ft in feats:
        if ft["properties"].get("building_id") != full:
            continue
        area += float(ft["properties"].get("area_m2", 0.0))
        geom = ft["geometry"]
        polys = geom["coordinates"] if geom["type"] == "MultiPolygon" else [geom["coordinates"]]
        for poly in polys:
            paths.append(MplPath(np.asarray(poly[0])[:, :2]))
    return paths, area


def in_fp(P, paths):
    m = np.zeros(len(P), bool)
    xy = P[:, :2]
    for p in paths:
        m |= p.contains_points(xy)
    return m


def read_roof(evalroot, arm, bid_short, paths):
    f = Path(evalroot) / arm / f"DEBY_LOD2_{bid_short}_orig_classified.las"
    if not f.exists():
        return None
    c = laspy.read(f)
    cl = np.asarray(c.classification)
    P = np.column_stack([np.asarray(c.x), np.asarray(c.y), np.asarray(c.z)]).astype(float)[cl == 6]
    if len(P) == 0:
        return P
    return P[in_fp(P, paths)]


def _cell_groups(P, cell):
    g = np.floor(P[:, :2] / cell).astype(np.int64)
    key = g[:, 0] * 1000003 + g[:, 1]
    order = np.argsort(key, kind="stable")
    ks, Ps = key[order], P[order]
    _, counts = np.unique(ks, return_counts=True)
    return np.split(Ps, np.cumsum(counts)[:-1])


def local_fit(P, cell=CELL, minpts=MINPTS):
    """Per-cell PCA plane -> per-point |residual| (kept pts) + per-cell unit normal (nz>=0)."""
    kept, res, normals = [], [], []
    for Q in _cell_groups(P, cell):
        if len(Q) < minpts:
            continue
        c = Q.mean(0)
        _, _, Vt = np.linalg.svd(Q - c, full_matrices=False)
        n = Vt[-1]
        if n[2] < 0:
            n = -n
        d = np.abs((Q - c) @ Vt[-1])
        kept.append(Q); res.append(d); normals.append(n)
    if not res:
        return None
    return (np.concatenate(kept), np.concatenate(res), np.asarray(normals))


def plane_rms(P):
    if len(P) < 3:
        return None
    c = P.mean(0)
    _, _, Vt = np.linalg.svd(P - c, full_matrices=False)
    return float(np.sqrt((((P - c) @ Vt[-1]) ** 2).mean()))


def ndisp(normals):
    if len(normals) < 2:
        return None
    nd = normals.mean(0); nd /= (np.linalg.norm(nd) + 1e-12)
    ang = np.degrees(np.arccos(np.clip(np.abs(normals @ nd), 0, 1)))
    return float(ang.std())


def hole_ratio(P, paths, cell=HOLE_CELL):
    allv = np.vstack([p.vertices for p in paths])
    x0, y0 = allv.min(0); x1, y1 = allv.max(0)
    nx = max(1, int(np.ceil((x1 - x0) / cell))); ny = max(1, int(np.ceil((y1 - y0) / cell)))
    cx = x0 + (np.arange(nx) + 0.5) * cell
    cy = y0 + (np.arange(ny) + 0.5) * cell
    CX, CY = np.meshgrid(cx, cy)
    centers = np.column_stack([CX.ravel(), CY.ravel()])
    inside = np.zeros(len(centers), bool)
    for p in paths:
        inside |= p.contains_points(centers)
    if inside.sum() == 0:
        return None, 0
    gi = np.floor((P[:, 0] - x0) / cell).astype(int)
    gj = np.floor((P[:, 1] - y0) / cell).astype(int)
    occ = set(map(tuple, np.column_stack([gi, gj]).tolist()))
    ci = ((centers[:, 0] - x0) / cell).astype(int)
    cj = ((centers[:, 1] - y0) / cell).astype(int)
    occ_arr = np.fromiter(((i, j) in occ for i, j in zip(ci, cj)), bool, len(centers))
    in_cells = int(inside.sum())
    filled = int((inside & occ_arr).sum())
    return round(1.0 - filled / in_cells, 3), in_cells


def voxel_downsample_2d(P, voxel):
    g = np.floor(P[:, :2] / voxel).astype(np.int64)
    key = g[:, 0] * 1000003 + g[:, 1]
    _, idx = np.unique(key, return_index=True)
    return P[idx]


def metrics(P, paths, area):
    out = {"n_roof": int(len(P))}
    out["dens"] = round(len(P) / area, 1) if area > 0 else None
    out["hole"], out["incells"] = hole_ratio(P, paths)
    lf = local_fit(P)
    if lf is not None:
        _, res, normals = lf
        out["localRMS"] = round(float(np.sqrt((res ** 2).mean())), 3)
        out["localP90"] = round(float(np.percentile(res, 90)), 3)
        out["nDisp"] = round(ndisp(normals), 2) if ndisp(normals) is not None else None
    else:
        out["localRMS"] = out["localP90"] = out["nDisp"] = None
    out["planeRMS"] = round(plane_rms(P), 3) if plane_rms(P) is not None else None
    return out


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    rows = []
    for short, setname in TARGETS:
        paths, area = footprint(short)
        # LiDAR density for density-matched downsample
        li_P = read_roof(EVALROOT, "raw_lidar", short, paths)
        li_dens = (len(li_P) / area) if (li_P is not None and area > 0) else None
        for label, clf, root, arm in SOURCES:
            P = read_roof(root, arm, short, paths)
            if P is None:
                print(f"[skip] {short} {label}/{clf} — no LAS at {root}/{arm}")
                continue
            m = metrics(P, paths, area)
            rows.append({"target": short, "set": setname, "source": label, "classifier": clf,
                         "level": "orig", "area_m2": round(area, 1), **m})
            print(f"{short:9} {setname:9} {label:9} {clf:6} orig   n={m['n_roof']:>8} "
                  f"dens={m['dens']} hole={m['hole']} localRMS={m['localRMS']} p90={m['localP90']} "
                  f"nDisp={m['nDisp']} planeRMS={m['planeRMS']}")
            # density-matched GS (gssem only): voxel-downsample to LiDAR density
            if label.startswith("GS") and clf == "gssem" and li_dens and li_dens > 0:
                voxel = 1.0 / np.sqrt(li_dens)
                Pdm = voxel_downsample_2d(P, voxel)
                md = metrics(Pdm, paths, area)
                rows.append({"target": short, "set": setname, "source": label, "classifier": clf,
                             "level": "lidarD", "area_m2": round(area, 1), **md})
                print(f"{short:9} {'':9} {label:9} {clf:6} lidarD n={md['n_roof']:>8} "
                      f"dens={md['dens']} hole={md['hole']} localRMS={md['localRMS']} "
                      f"p90={md['localP90']} nDisp={md['nDisp']} (voxel={voxel:.2f}m)")

    keys = ["target", "set", "source", "classifier", "level", "area_m2", "n_roof", "dens",
            "hole", "incells", "localRMS", "localP90", "nDisp", "planeRMS"]
    with open(OUT / "overseg_diag_d6.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=keys, extrasaction="ignore")
        w.writeheader(); w.writerows(rows)
    print(f"\n[done] {len(rows)} rows -> {OUT}/overseg_diag_d6.csv")


if __name__ == "__main__":
    main()
