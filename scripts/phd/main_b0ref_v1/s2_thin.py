"""PHD-MAIN-B0REF-v1 일 2 5~6번: point spacing of the GeoGS cloud and the same thinning of the raw ULS (jointbuildgs:dev, CPU).

  python s2_thin.py   -> /b0/prep/spacing.json, /b0/crop/uls_nadir_t2first.npz, /b0/crop/uls_nadir_t2mean.npz

No thinning size or method for the example cloud is written in the GeoGS code or README (일 4), so the config's fallback is used:
the raw ULS nadir crop (all returns) thinned on the 2 cm grid floor(X / 0.02) of the comparison frame, (a) the first point of each cell
in file order, (b) the cell mean. The 2 cm grid of the comparison frame is the 2 cm grid of the GeoGS author frame (the xy move
[2, -29, 0] m is a multiple of 0.02). [이 요청에서 냄] scientific_verdict: null."""
import time

import numpy as np
from scipy.spatial import cKDTree

from b0_common import B0, CFG, jdump, load_crop, log, now

G_ = CFG["thinning"]["grid_check_m"]


def cell_keys(X, g):
    k = np.floor(X / g).astype(np.int64)
    k -= k.min(0)
    d1 = int(k[:, 1].max()) + 1; d2 = int(k[:, 2].max()) + 1
    return (k[:, 0] * d1 + k[:, 1]) * d2 + k[:, 2]


def occupancy(X, g):
    kk = cell_keys(X, g)
    u, inv, c = np.unique(kk, return_inverse=True, return_counts=True)
    return dict(grid_m=g, points=int(len(X)), cells=int(len(u)), cells_with_more_than_one=int((c > 1).sum()),
                share_points_alone_in_cell=float(np.mean(c[inv] == 1)), max_points_in_cell=int(c.max()))


def spacing(X, sel=None):
    d = cKDTree(X).query(X, k=2, workers=8)[0][:, 1]
    if sel is not None:
        d = d[sel]
    q = np.percentile(d, [0, 1, 5, 25, 50, 75, 95, 99])
    return dict(n=int(len(d)), min_m=float(q[0]), p01_m=float(q[1]), p05_m=float(q[2]), p25_m=float(q[3]), median_m=float(q[4]),
                p75_m=float(q[5]), p95_m=float(q[6]), p99_m=float(q[7]), share_below_grid=float(np.mean(d < G_)),
                share_exact_duplicates=float(np.mean(d == 0)))


def main():
    t0 = time.time()
    G = load_crop("geogs")["xyz"]
    sg = np.load(B0 / "sel/geogs.npz")
    ev = sg["ev"]
    rec = dict(geogs=dict(all=spacing(G[ev]), wall_space=spacing(G[ev], sg["wall_any"][ev]), roof_space=spacing(G[ev], sg["roof_any"][ev]),
                          occupancy_2cm=occupancy(G[ev], G_)))
    U = load_crop("uls_nadir")
    X = U["xyz"]
    su = np.load(B0 / "sel/uls_nadir.npz")
    rec["uls_nadir"] = dict(all=spacing(X[su["ev"]]), wall_space=spacing(X[su["ev"]], su["wall_any"][su["ev"]]),
                            roof_space=spacing(X[su["ev"]], su["roof_any"][su["ev"]]), occupancy_2cm=occupancy(X[su["ev"]], G_))
    log("spacing done", f"{time.time() - t0:.0f}s")
    kk = cell_keys(X, G_)
    u, first, inv = np.unique(kk, return_index=True, return_inverse=True)
    keep = np.sort(first)
    np.savez(B0 / "crop/uls_nadir_t2first.npz", xyz=X[keep], src_row=keep, red=U["red"][keep], green=U["green"][keep], blue=U["blue"][keep])
    cnt = np.bincount(inv)
    M = np.column_stack([np.bincount(inv, X[:, a]) / cnt for a in range(3)])
    rgbm = {c: (np.bincount(inv, U[c].astype(np.float64)) / cnt) for c in ("red", "green", "blue")}
    np.savez(B0 / "crop/uls_nadir_t2mean.npz", xyz=M, n_in_cell=cnt.astype(np.int32), **{c: v.astype(np.float32) for c, v in rgbm.items()})
    rec["thinned"] = dict(rule=CFG["thinning"]["same_thinning"], first_points=int(len(keep)), mean_points=int(len(M)), raw_points=int(len(X)))
    rec["seconds"] = round(time.time() - t0, 1); rec["made"] = now(); rec["scientific_verdict"] = None
    jdump(B0 / "prep/spacing.json", rec)
    log("thin done", len(keep), f"{time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
