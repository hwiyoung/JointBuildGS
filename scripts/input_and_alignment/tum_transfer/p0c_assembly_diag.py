#!/usr/bin/env python3
"""P0 assembly-failure cause diagnosis — ACMP vs ALS deficit per footprint.

For the 17 assembly-limited buildings (ACMP-canonical: planes>=1 but no solid), clip
building points from ACMP (acmp_classified.laz, class 6) and ALS (als_aoi.laz, class 6)
inside each footprint and compare: density, coverage/hole-frac, dominant-plane RMS,
local cell z-std (thickness/noise), vertical extent + wall fraction, and ACMP SMRF
classification sanity inside footprint (ground-frac = roof eaten by SMRF?). Observation
only. Runs in jointbuildgs-p0-tools (numpy/laspy/shapely). EPSG:25832.
"""
import csv, json
import numpy as np, laspy
REPO = "/workspace/JointBuildGS"
R = f"{REPO}/results/tum_transfer/mob_analysis"
TARGETS17 = ["104586480","4907182","4908166","4908050","4907181","4907167","4908046","4907175",
             "4907033","4907036","4907027","4907031","4907030","4907016","4906999","4907014","4907022"]
DEEP3 = ["104586480","4907182","4908050"]


def pip(pts, poly):
    x, y = pts[:, 0], pts[:, 1]; ins = np.zeros(len(pts), bool); j = len(poly) - 1
    for i in range(len(poly)):
        xi, yi = poly[i]; xj, yj = poly[j]
        ins ^= ((yi > y) != (yj > y)) & (x < (xj - xi) * (y - yi) / (yj - yi + 1e-12) + xi); j = i
    return ins


def load_xyzc(path, classes):
    xs, ys, zs, cs = [], [], [], []
    with laspy.open(path) as f:
        for p in f.chunk_iterator(5_000_000):
            cl = np.asarray(p.classification, np.uint8)
            m = np.isin(cl, classes)
            xs.append(np.asarray(p.x)[m]); ys.append(np.asarray(p.y)[m])
            zs.append(np.asarray(p.z)[m]); cs.append(cl[m])
    return np.column_stack([np.concatenate(xs), np.concatenate(ys), np.concatenate(zs)]), np.concatenate(cs)


def plane_rms(P):
    if len(P) < 8: return None
    c = P.mean(0); _, _, Vt = np.linalg.svd(P - c, full_matrices=False)
    return float(np.sqrt((((P - c) @ Vt[-1]) ** 2).mean()))


def cell_zstd(P, cell=0.5):
    if len(P) < 8: return None
    gx = np.floor(P[:, 0] / cell).astype(int); gy = np.floor(P[:, 1] / cell).astype(int)
    key = gx.astype(np.int64) * 100003 + gy
    stds = []
    for k in np.unique(key):
        z = P[key == k, 2]
        if len(z) >= 3: stds.append(z.std())
    return float(np.median(stds)) if stds else None


def coverage(P, ring, cell=1.0):
    x0, y0, x1, y1 = ring[:, 0].min(), ring[:, 1].min(), ring[:, 0].max(), ring[:, 1].max()
    nx, ny = max(1, int((x1 - x0) / cell)), max(1, int((y1 - y0) / cell))
    cx, cy = np.meshgrid(np.arange(nx) * cell + x0 + cell / 2, np.arange(ny) * cell + y0 + cell / 2)
    grid = np.column_stack([cx.ravel(), cy.ravel()]); inside = pip(grid, ring)
    ncells = max(1, int(inside.sum()))
    if not len(P): return 0.0, 1.0
    gxp = ((P[:, 0] - x0) / cell).astype(int); gyp = ((P[:, 1] - y0) / cell).astype(int)
    occ = len(set(zip(gxp.tolist(), gyp.tolist())))
    cov = min(1.0, occ / ncells)
    return round(cov, 2), round(1 - cov, 2)


def metrics(P, ring, area):
    if not len(P):
        return dict(n=0, dens=0.0, cov=0.0, hole=1.0, rms=None, zstd=None, zrange=None, wall=None)
    cov, hole = coverage(P, ring)
    z = P[:, 2]; ztop = np.percentile(z, 90)
    wall = float((z < ztop - 2.0).mean())  # pts >2m below roof = facade/wall
    return dict(n=int(len(P)), dens=round(len(P) / area, 1), cov=cov, hole=hole,
                rms=(round(plane_rms(P), 3) if plane_rms(P) is not None else None),
                zstd=(round(cell_zstd(P), 3) if cell_zstd(P) is not None else None),
                zrange=round(float(z.max() - z.min()), 1), wall=round(wall, 2))


def main():
    geo = json.load(open(f"{REPO}/results/tum_transfer/analysis/footprints_aoi.geojson"))["features"]
    fp = {}
    for f in geo:
        g = f["geometry"]; ring = np.asarray(g["coordinates"][0] if g["type"] == "Polygon" else g["coordinates"][0][0])[:, :2]
        fp[f["properties"]["building_id"]] = ring

    print("loading ACMP (class 2,6) + ALS (class 2,6) ...")
    A_xyz, A_c = load_xyzc(f"{R}/p0c_step2/acmp_classified.laz", [2, 6])
    L_xyz, L_c = load_xyzc(f"{R}/p0c_step2/als_aoi.laz", [2, 6])
    print(f"  ACMP {len(A_xyz):,}  ALS {len(L_xyz):,}")

    rows = []
    for short in TARGETS17:
        bid = f"DEBY_LOD2_{short}"; ring = fp[bid]
        x0, y0, x1, y1 = ring[:, 0].min(), ring[:, 1].min(), ring[:, 0].max(), ring[:, 1].max()
        area = 0.5 * abs(np.dot(ring[:, 0], np.roll(ring[:, 1], -1)) - np.dot(ring[:, 1], np.roll(ring[:, 0], -1)))
        # ACMP inside footprint (all of 2,6) for classification sanity
        Abox = (A_xyz[:, 0] >= x0) & (A_xyz[:, 0] <= x1) & (A_xyz[:, 1] >= y0) & (A_xyz[:, 1] <= y1)
        Ain = Abox.copy(); Ain[Abox] = pip(A_xyz[Abox, :2], ring)
        A_all, A_cls = A_xyz[Ain], A_c[Ain]
        a6 = A_all[A_cls == 6]; a2 = A_all[A_cls == 2]
        ground_frac = round(float((A_cls == 2).mean()), 2) if len(A_cls) else None
        # ALS inside footprint, class 6
        Lbox = (L_xyz[:, 0] >= x0) & (L_xyz[:, 0] <= x1) & (L_xyz[:, 1] >= y0) & (L_xyz[:, 1] <= y1)
        Lin = Lbox.copy(); Lin[Lbox] = pip(L_xyz[Lbox, :2], ring)
        l6 = L_xyz[Lin][L_c[Lin] == 6]
        am = metrics(a6, ring, area); lm = metrics(l6, ring, area)
        rows.append(dict(bid=short, area=round(area, 0), deep=(short in DEEP3),
                         acmp=am, als=lm, acmp_ground_frac=ground_frac,
                         acmp_n2_inside=int(len(a2)), acmp_n6_inside=int(len(a6))))

    json.dump(rows, open(f"{R}/p0c_step2/eval/p0c_assembly_diag.json", "w"), indent=1)

    print("\n##### ACMP vs ALS deficit (17 assembly-limited; building class-6 in footprint) #####")
    h = f"{'bid':10s}{'area':>6s} | {'ACMP dens cov rms  zstd wall':30s} | {'ALS dens cov rms  zstd wall':28s} | grdfrac"
    print(h)
    for r in rows:
        a, l = r["acmp"], r["als"]
        deep = "*" if r["deep"] else " "
        print(f"{deep}{r['bid']:9s}{r['area']:>6.0f} | "
              f"{a['dens']:>5.0f} {a['cov']:>4.2f} {str(a['rms']):>5s} {str(a['zstd']):>5s} {str(a['wall']):>4s}      | "
              f"{l['dens']:>5.0f} {l['cov']:>4.2f} {str(l['rms']):>5s} {str(l['zstd']):>5s} {str(l['wall']):>4s}     | {r['acmp_ground_frac']}")
    print("\n  cols: dens=pts/m2  cov=footprint coverage  rms=dominant-plane RMS(m)  zstd=median 0.5m-cell z-std(m, noise)  wall=frac pts >2m below roof  grdfrac=ACMP pts inside footprint SMRF-labeled ground(=roof eaten)")
    print("  (* = deep-3)")
    print(f"[done] {R}/p0c_step2/eval/p0c_assembly_diag.json")


if __name__ == "__main__":
    main()
