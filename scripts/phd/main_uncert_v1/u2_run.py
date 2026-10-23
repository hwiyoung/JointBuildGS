"""PHD-MAIN-UNCERT-v1 일 2: the per-patch values of one site, one patch set and one data (jointbuildgs:dev, CPU, forked workers).

  python u2_run.py <site> <LoD2|ALS> gt                          -> /out/work/gt_<site>_<set>.npz        (1.5 GT face and plane)
  python u2_run.py <site> <LoD2|ALS> <mvs_a|mvs_b|als> <R,...>   -> /out/work/val_<site>_<set>_<data>_R<R>.npz  (1.1-1.2, 1.5 errors)
  python u2_run.py <site> <LoD2|ALS> check_mvs                   -> /out/work/check_mvs_<site>.json      (2.8 stop check, ALS set)
  [--workers N] [--limit K (first K patches, for a timing run)]

Per patch (u_core, config defs): the data points of the column (lateral <= 0.5 m, |normal distance| <= 10 m roof-like / 3 m wall-like)
-> the face o -> the inner points (lateral <= 0.5, |t - o| <= 1) and the ring points (0.5 < lateral <= R, |t - o| <= 1) -> counts ->
the LMedS ring plane -> a, s, u, q of the inner points' distances to it; p = median normal distance of the inner points; the quadrant
and support flags; with the GT plane of the patch (gt_<site>_<set>.npz) the real error of the same inner points.
MVS thinning is exact: the points are stored sorted by their random key, so 'the 2,000 (8,000) points with the smallest keys' = the 2,000
(8,000) smallest indices; the ring is searched on the prefix 'key < 4^-k' (a k-d tree per k) from the sparsest prefix expected to hold
1.1 x 8,000 ring points, going denser while it holds fewer than 8,000; if a prefix holds >= 8,000 the 8,000 smallest keys of the whole
ring are in it. Column search: balls of radius sqrt(0.5^2 + 0.25^2) along the axis every 0.5 m, then the exact filters.
scientific_verdict: null."""
import argparse
import multiprocessing as mp
import sys
import time

import numpy as np
from scipy.spatial import cKDTree

sys.path.insert(0, "/repo/scripts/phd/main_uncert_v1")
import u_core as C  # noqa: E402
import uc_common as U  # noqa: E402

D = U.D
RI = D["inner_radius_m"]
G = {}                                                   # globals shared with the forked workers


def load_points(site, data):
    P = U.PTS / site
    if data in ("mvs_a", "mvs_b"):
        v = data[-1]
        X = np.load(P / f"mvs_{v}_xyz.npy").astype(np.float64)
        return X, np.load(P / f"mvs_{v}_view.npy"), np.load(P / f"mvs_{v}_key.npy")
    if data == "als":
        return np.load(P / "als_xyz.npy").astype(np.float64), None, None
    return np.load(P / "gt_xyz.npy").astype(np.float64), None, None


def build(site, pset, data, radii):
    T = U.Timer()
    X, V, K = load_points(site, data)
    G.update(X=X, V=V, data=data, radii=radii, site=site, pset=pset)
    G["tree"] = cKDTree(X, leafsize=32, balanced_tree=False, compact_nodes=False)
    G["levels"] = {}
    if data in ("mvs_a", "mvs_b"):
        for k in range(1, 6):
            nk = int(np.searchsorted(K, 4.0 ** -k))
            if nk < 1000:
                break
            G["levels"][k] = (nk, cKDTree(X[:nk], leafsize=32, balanced_tree=False, compact_nodes=False))
    pt = U.patches(site, pset)
    G["c"], G["n"], G["roof"] = pt["centre"], pt["normal"], pt["roof_like"]
    if data not in ("gt", "check_mvs"):
        gf = U.WORK / f"gt_{site}_{pset}.npz"
        if gf.exists():
            with np.load(gf) as z:
                G["gt"] = {k: z[k] for k in z.files}       # read fully: a lazy npz handle is not safe across forked workers
        else:
            G["gt"] = None
    U.log("built", site, pset, data, len(X), "points, levels", {k: v[0] for k, v in G["levels"].items()}, T.mark("build"), "s")
    return T.marks["build"]


def column(i):
    """indices of the points with lateral <= 0.5 and |t| <= H around patch i, their t and rho, H."""
    c, n = G["c"][i], G["n"][i]
    H = D["column_half_m"]["roof" if G["roof"][i] else "wall"]
    tj = np.arange(-H + 0.25, H, 0.5)
    ctr = c[None, :] + tj[:, None] * n[None, :]
    lists = G["tree"].query_ball_point(ctr, np.hypot(RI, 0.25) + 1e-6)
    arrs = [np.asarray(L, np.int64) for L in lists if len(L)]
    idx = np.unique(np.concatenate(arrs)) if arrs else np.zeros(0, np.int64)
    if not len(idx):
        return idx, np.zeros(0), np.zeros(0), H
    t, rho, _ = C.column_coords(G["X"][idx] - c, n)
    m = (rho <= RI) & (np.abs(t) <= H)
    return idx[m], t[m], rho[m], H


def ring_points(i, o, R, n_inner_all):
    """the ring points of patch i (indices, ascending = by key for MVS), the prefix level used and the count found there."""
    c, n = G["c"][i], G["n"][i]
    ctr = c + o * n
    rad = np.hypot(R, D["slab_half_m"]) + 1e-6
    cap = D["mvs_cap_ring"] if G["data"] in ("mvs_a", "mvs_b") else None
    k = 0
    if cap and G["levels"]:
        dens = max(n_inner_all, 1) / (np.pi * RI ** 2)
        exp = dens * np.pi * (R ** 2 - RI ** 2)
        for kk in sorted(G["levels"], reverse=True):
            if exp * 4.0 ** -kk >= 1.1 * cap:
                k = kk
                break
    while True:
        tree = G["levels"][k][1] if k > 0 else G["tree"]
        idx = np.asarray(tree.query_ball_point(ctr, rad), np.int64)
        if len(idx):
            t, rho, L = C.column_coords(G["X"][idx] - c, n)
            m = (rho > RI) & (rho <= R) & (np.abs(t - o) <= D["slab_half_m"])
            idx, L = idx[m], L[m]
        else:
            L = np.zeros((0, 3))
        if cap is None or len(idx) >= cap or k == 0:
            break
        k -= 1
    o_ = np.argsort(idx)
    idx, L = idx[o_], L[o_]
    found = len(idx)
    if cap and len(idx) > cap:
        idx, L = idx[:cap], L[:cap]
    return idx, L, k, found


FIELDS_V = ["status", "o", "n_col", "n_inner_all", "n_inner", "views", "n_ring", "ring_level", "ring_found", "thinned_inner", "thinned_ring",
            "a", "s", "u", "q", "med", "p", "nx", "ny", "nz", "h", "angle", "s0", "n_inl", "support_lmeds", "support_final", "n_cand",
            "quadrants", "e_bias", "e_spread", "e", "qe", "f", "seconds"]
FIELDS_G = ["status", "o", "runs", "n_col", "n_inner", "p", "nx", "ny", "nz", "h", "angle", "s0", "support_lmeds", "seconds"]


def one_patch(i):
    """values of patch i for every ring radius (dict R -> row)."""
    t0 = time.time()
    c, n = G["c"][i], G["n"][i]
    data = G["data"]
    idx, t, rho, H = column(i)
    o, runs, M = C.find_face(t, H, D)
    rows = {}
    if data == "gt":
        r = dict(status=1, o=np.nan, runs=runs, n_col=M, n_inner=0)
        if o is not None:
            m = np.abs(t - o) <= D["slab_half_m"]
            r.update(o=o, n_inner=int(m.sum()))
            if m.sum() < D["gt_min_points"]:
                r["status"] = 2
            else:
                Q = G["X"][idx[m]] - c
                rng = np.random.default_rng([U.CFG["seed"], U.SITE_ID[G["site"]], U.SET_ID[G["pset"]], U.DATA_ID["gt"], 9, int(i)])
                pl = C.lmeds_plane(Q, n, rng, D)
                if pl is None:
                    r["status"] = 3
                else:
                    r.update(status=0, p=float(np.median(t[m])), nx=pl["normal"][0], ny=pl["normal"][1], nz=pl["normal"][2], h=pl["offset"],
                             angle=pl["angle_deg"], s0=pl["s0"], support_lmeds=pl["support_lmeds"])
        r["seconds"] = time.time() - t0
        return {0: r}
    base = dict(status=1, o=np.nan, n_col=M, n_inner_all=0, n_inner=0, thinned_inner=0)
    if o is None:
        for R in G["radii"]:
            rows[R] = dict(base, seconds=time.time() - t0)
        return rows
    m = np.abs(t - o) <= D["slab_half_m"]
    inn = idx[m]
    tin = t[m]
    base.update(o=o, n_inner_all=int(len(inn)))
    if G["V"] is not None:
        base["views"] = int(np.unique(G["V"][inn]).size)
    cap_i = D["mvs_cap_inner"] if data in ("mvs_a", "mvs_b") else None
    if cap_i and len(inn) > cap_i:
        o_ = np.argsort(inn)[:cap_i]
        inn, tin = inn[o_], tin[o_]
        base["thinned_inner"] = 1
    base["n_inner"] = int(len(inn))
    Q = G["X"][inn] - c
    gt = G.get("gt")
    e1, e2 = C.in_plane_basis(n)
    for R in G["radii"]:
        r = dict(base)
        ridx, L, lev, found = ring_points(i, o, R, base["n_inner_all"])
        r.update(n_ring=int(len(ridx)), ring_level=lev, ring_found=found, thinned_ring=int(lev > 0 or found > len(ridx)))
        if base["n_inner_all"] < D["min_inner"] or (lev == 0 and found < D["min_ring"]):
            r["status"] = 2
        else:
            P = G["X"][ridx] - c
            rng = np.random.default_rng([U.CFG["seed"], U.SITE_ID[G["site"]], U.SET_ID[G["pset"]], U.DATA_ID[data], U.R_ID[R], int(i)])
            pl = C.lmeds_plane(P, n, rng, D)
            if pl is None:
                r["status"] = 3
            else:
                d = (Q - pl["point"]) @ pl["normal"]
                st = C.stats(d, D)
                r.update(status=0, a=st["a"], s=st["s"], u=st["u"], q=st["q"], med=st["med"], p=float(np.median(tin)),
                         nx=pl["normal"][0], ny=pl["normal"][1], nz=pl["normal"][2], h=pl["offset"], angle=pl["angle_deg"], s0=pl["s0"],
                         n_inl=pl["n_inliers"], support_lmeds=pl["support_lmeds"], support_final=pl["support_final"], n_cand=pl["n_candidates"],
                         quadrants=C.quadrants(L, e1, e2))
        if gt is not None and gt["status"][i] == 0 and base["n_inner_all"] >= D["min_inner"]:
            mG = np.array([gt["nx"][i], gt["ny"][i], gt["nz"][i]], np.float64)
            re = C.real_error(Q @ mG - float(gt["h"][i]), D)
            r.update(e_bias=re["bias"], e_spread=re["spread"], e=re["e"], qe=re["qe"], f=re["f"])
        r["seconds"] = time.time() - t0
        rows[R] = r
    return rows


def work(chunk):
    return [(i, one_patch(i)) for i in chunk]


def run(site, pset, data, radii, workers, limit=None):
    T = U.Timer()
    tb = build(site, pset, data, radii)
    N = len(G["c"])
    order = np.arange(N if limit is None else min(limit, N))
    chunks = [order[b:b + 200] for b in range(0, len(order), 200)]
    fields = FIELDS_G if data == "gt" else FIELDS_V
    keys = [0] if data == "gt" else radii
    out = {R: {f: np.full(N, np.nan, np.float32) for f in fields} for R in keys}
    for R in keys:
        out[R]["status"] = np.full(N, -1, np.int8)
    done = 0
    ctx = mp.get_context("fork")
    with ctx.Pool(workers) as pool:
        for res in pool.imap_unordered(work, chunks, chunksize=1):
            for i, rows in res:
                for R, r in rows.items():
                    for f, v in r.items():
                        out[R][f][i] = v
            done += len(res)
            if done % 20000 < 200:
                U.log(site, pset, data, done, "/", len(order), T.mark("loop"), "s")
    secs = T.mark("loop")
    files = []
    for R in keys:
        f = U.WORK / (f"gt_{site}_{pset}.npz" if data == "gt" else f"val_{site}_{pset}_{data}_R{R}.npz")
        if limit is not None:
            f = f.with_name(f.stem + f"_limit{limit}.npz")
        np.savez(f, **out[R])
        files.append(str(f))
        st = out[R]["status"]
        U.log(site, pset, data, R, {int(k): int(v) for k, v in zip(*np.unique(st, return_counts=True))})
    U.jdump(U.WORK / (f"run_gt_{site}_{pset}.json" if data == "gt" else f"run_{site}_{pset}_{data}_{'_'.join(map(str, radii))}.json")
            if limit is None else U.WORK / f"run_limit_{site}_{pset}_{data}.json",
            dict(site=site, set=pset, data=data, radii=radii, workers=workers, patches=len(order), points=len(G["X"]),
                 levels={k: v[0] for k, v in G["levels"].items()}, seconds_build=tb, seconds_loop=secs, files=files, made=U.now(), env=U.env(),
                 peak_gb_parent=U.peak_gb(), gt_file_used=(G.get("gt") is not None), scientific_verdict=None))


def check_mvs(site, workers):
    """2.8 stop check on the ALS case: p_M of a random sample of refine patches (in evaluation range) and the per-view medians."""
    T = U.Timer()
    out = {}
    for v in ("mvs_a",):
        build(site, "ALS", v, [])
        pt = U.patches(site, "ALS")
        cand = np.nonzero((pt["cell"] == U.CID["c_refine"]))[0]
        rng = np.random.default_rng([U.CFG["seed"], U.SITE_ID[site], 77])
        sel = np.sort(rng.choice(cand, min(3000, len(cand)), replace=False))
        pM, per_view = [], {}
        for i in sel:
            idx, t, rho, H = column(i)
            o, runs, M = C.find_face(t, H, D)
            if o is None:
                continue
            m = np.abs(t - o) <= D["slab_half_m"]
            if m.sum() < D["min_inner"]:
                continue
            inn, tin = idx[m], t[m]
            o_ = np.argsort(inn)[:D["mvs_cap_inner"]]
            pM.append(float(np.median(tin[o_])))
            vv = G["V"][inn]
            for w in np.unique(vv):
                k = vv == w
                if k.sum() >= 5:
                    per_view.setdefault(int(w), []).append(float(np.median(tin[k])))
        pM = np.array(pM)
        med_v = {w: float(np.median(x)) for w, x in per_view.items() if len(x) >= 100}
        vals = np.array(list(med_v.values()))
        out[v] = dict(sampled=int(len(sel)), with_value=int(len(pM)), p_M_median_cm=100 * float(np.median(pM)),
                      p_M_nmad_cm=100 * 1.4826 * float(np.median(np.abs(pM - np.median(pM)))),
                      views_ge100=int(len(vals)), view_median_min_cm=100 * float(vals.min()) if len(vals) else None,
                      view_median_max_cm=100 * float(vals.max()) if len(vals) else None,
                      view_spread_cm=100 * float(vals.max() - vals.min()) if len(vals) else None,
                      stop_p_M=bool(abs(np.median(pM)) > 0.10), stop_views=bool(len(vals) and (vals.max() - vals.min()) > 0.15),
                      per_view_median_cm={str(w): 100 * x for w, x in sorted(med_v.items())})
    U.jdump(U.WORK / f"check_mvs_{site}.json", dict(site=site, rule=U.CFG["checks"]["mvs_place_stop"], made=U.now(), result=out,
                                                    seconds=T.mark("all"), scientific_verdict=None))
    U.log(site, {k: {kk: vv for kk, vv in v.items() if kk != "per_view_median_cm"} for k, v in out.items()})


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("site"); ap.add_argument("pset"); ap.add_argument("data"); ap.add_argument("radii", nargs="?", default="")
    ap.add_argument("--workers", type=int, default=16); ap.add_argument("--limit", type=int, default=None)
    a = ap.parse_args()
    if a.data == "check_mvs":
        check_mvs(a.site, a.workers)
    else:
        radii = [] if a.data == "gt" else [float(x) for x in a.radii.split(",")]
        run(a.site, a.pset, a.data, radii, a.workers, a.limit)
