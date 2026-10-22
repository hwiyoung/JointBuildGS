"""PHD-MAIN-AXES71-v2 일 3 바탕: the result-side distances of this order for every result of a site (jointbuildgs:dev, CPU; no GPU).

  python a2x_sample.py <site> [result ...]   -> AX/dist/<site>_<prior>__<result>__x.npz (+ .json); for a result without the distance task's
                                                per-point file also AX/dist/<site>_<prior>__<result>.npz in that task's form (and __b0gt)

Per result mesh (training view) the result sample is regenerated with the distance task's rule (dm_common.result_sample: triangles with the
centroid in a building-surface cell or area > 0.01 m2, 400 points per m2, seed 0, the points inside the cells) and checked against the
stored one (same number of points, d_r to the scene GT the same). Then per sample point p:
  dr  / ndist / lat         to the scene GT (ULS of the building-surface cells): q = nearest GT point (cKDTree), d_r = |p - q|,
                            normal distance |n_q . (p - q)|, lateral sqrt(|p - q|^2 - ndist^2), n_q = the GT normal of a1_normals.py
  dr_b / ndist_b / lat_b    B0 only: to the GT the B0 regions use (ULS + primary GT in the cells; the distance task's d2b_b0gt.py)
  pd                        per prior: distance to the nearest patch centre (the patch is the distance task's q_patch rule)
셈 마 = ndist where lat <= 0.5 m (else 판단할 수 없음), 셈 바 = lat <= 1.0 m (일 3 reads them). The virtual-view mesh (where it exists): the
GT rows of the invisible cells (codes 5 and 14) and the virtual sample points whose nearest patch is one of them get the same values
(v_*). xyz of the training-view sample is kept as float32 (AX/dist/<site>__<result>__xyz.npy) for the maps and sections.
[새로 셈] scientific_verdict: null."""
import sys
import time

import numpy as np
from scipy.spatial import cKDTree

from ax_common import (CID, DIST, PRIORS, SITES, VIRTUAL_CELLS, WORK, Unit, SiteGT, all_results, b0gt_file, cells_of, dist_file, jdump, jl, log, mesh_of, now,
                       short, x_file)
import dm_common as DMC
from d2_dist import oriented_sign, place_bits
from src.phd.metrics_v3.surface import MeshScene


class Ref:
    """a GT reference set with the normal of every point."""

    def __init__(self, X, N):
        self.X, self.N = X, N
        self.tree = cKDTree(X)

    def query(self, P, bound=None):
        """nearest GT point; `bound` = a known upper bound of each point's nearest distance (the stored exact d_r, float32): the points
        are queried in buckets of bound with the bucket's top as distance_upper_bound (exact, only faster for points far from the GT);
        a point not found under its bucket's bound is queried again without a bound."""
        if not len(P):
            z = np.zeros(0)
            return z, z, z, np.zeros(0, np.int64)
        if bound is None:
            d, i = self.tree.query(P, workers=-1)
        else:
            d = np.full(len(P), np.inf)
            i = np.full(len(P), len(self.X), np.int64)
            b = np.asarray(bound, np.float64) * (1 + 1e-5) + 1e-5
            edges = [0.0, 0.02]
            while edges[-1] < b.max():
                edges.append(edges[-1] * 1.3)
            k = np.searchsorted(np.asarray(edges), b, side="left")
            for kk in np.unique(k):
                m = np.nonzero(k == kk)[0]
                d[m], i[m] = self.tree.query(P[m], distance_upper_bound=edges[kk] * (1 + 1e-6) + 1e-6, workers=-1)
            miss = ~np.isfinite(d)
            if miss.any():
                d[miss], i[miss] = self.tree.query(P[miss], workers=-1)
            self.n_fallback = int(miss.sum())
        v = P - self.X[i]
        n = self.N[i].astype(np.float64)
        nd = np.abs((v * n).sum(1))
        bad = ~np.isfinite(nd)
        lat = np.sqrt(np.clip(d * d - np.nan_to_num(nd) ** 2, 0, None))
        nd[bad] = np.nan
        lat[bad] = np.nan
        return d, nd, lat, i


def normals_full(site, gt):
    Z = np.load(WORK / f"normals_{site}.npz")
    out = {}
    for s, X in gt.X.items():
        a = np.full((len(X), 3), np.nan, np.float32)
        a[Z[f"use_{s}"]] = Z[f"normal_{s}"]
        out[s] = a
    return out


def full_dist(site, prior, res, method, u, gt, sc, smp, n_scene, Nfull, own, near, treeG, tr, why, vv):
    """the distance task's per-point file for a result it did not count (d2_dist.main's loop body for one result and prior)."""
    s_d = sc.distance(gt.Gb)
    q_s, _ = DMC.closest(sc, gt.Gb)
    d_old = cKDTree(smp).query(gt.Gb, workers=-1)[0] if len(smp) else np.full(len(gt.Gb), np.inf)
    q_d = treeG.query(smp, workers=-1)[0] if len(smp) else np.zeros(0)
    o = own[prior]
    n_pat = np.full((len(o), 3), np.nan)
    n_pat[o >= 0] = u.n_p[o[o >= 0]]
    s_sign = oriented_sign(gt.Gb, q_s, s_d, n_scene, n_pat)
    s_tau = np.full(len(o), np.nan, np.float32)
    s_tau[o >= 0] = u.tau[o[o >= 0]]
    nr = near[prior]
    s_sign_near = oriented_sign(gt.Gb, q_s, s_d, n_scene, u.n_p[nr])
    r_d = sc.distance(u.r_P)
    q_r, _ = DMC.closest(sc, u.r_P)
    n_rows = np.full((len(u.r_P), 3), np.nan, np.float32)
    for s_ in np.unique(u.r_src):
        m = u.r_src == s_
        n_rows[m] = Nfull[int(s_)][u.r_pt[m]]
    r_sign = oriented_sign(u.r_P, q_r, r_d, n_rows, u.r_n)
    q_pa = cKDTree(u.centre).query(smp, workers=-1)[1].astype(np.int64) if len(smp) else np.zeros(0, np.int64)
    out = dict(s_d=s_d.astype(np.float32), s_d_old=d_old.astype(np.float32), s_sign=s_sign, s_patch=o.astype(np.int32), s_tau=s_tau,
               s_near=nr.astype(np.int32), s_tau_near=u.tau[nr].astype(np.float32), s_sign_near=s_sign_near,
               r_idx=u.rows_idx.astype(np.int32), r_d=r_d.astype(np.float32), r_sign=r_sign, r_patch=u.r_pa.astype(np.int32),
               r_tau=u.r_tau.astype(np.float32), r_place=place_bits(u, u.r_pa), r_ratio=u.ratio[u.r_pa].astype(np.float32),
               q_d=q_d.astype(np.float32), q_patch=q_pa.astype(np.int32), q_tau=u.tau[q_pa].astype(np.float32), q_has_gt=u.has_gt[q_pa],
               q_place=place_bits(u, q_pa))
    np.savez_compressed(DIST / f"{site}_{prior}__{res}.npz", **out)
    jdump(DIST / f"{site}_{prior}__{res}.json", dict(site=site, prior=prior, result=res, method=method, status="있음", mesh=short(tr), mesh_why=why,
                                                     scene_points=int(len(gt.Gb)), rows=int(len(u.r_P)), sample_points=int(len(smp)),
                                                     sign_undefined_scene=int((s_sign == 0).sum()), sign_undefined_rows=int((r_sign == 0).sum()),
                                                     no_patch_scene=int((o < 0).sum()), virtual=None, made=now(), note="이 발주에서 셈(새 거리 지표 d2_dist 규칙 그대로)",
                                                     scientific_verdict=None))
    return out


def main(site, only=None):
    T0 = time.time()
    gt = SiteGT(site)
    U = {p: Unit(site, p, gt) for p in PRIORS}
    Nfull = normals_full(site, gt)
    refS = Ref(gt.Gb, Nfull[0][gt.bs_idx])
    refB = None
    if site == "B0_b10":
        m1 = gt.G["use_gt_primary"].astype(bool)
        P1 = gt.X[1][m1]
        N1 = Nfull[1][m1]
        k = gt.in_cells(P1)
        refB = Ref(np.vstack([gt.Gb, P1[k]]), np.vstack([Nfull[0][gt.bs_idx], N1[k]]))
    trees = {p: cKDTree(U[p].centre) for p in PRIORS}
    n_scene = Nfull[0][gt.bs_idx]
    own = {p: DMC.owner_of_scene_points(site, p, gt) for p in PRIORS}
    near = {p: trees[p].query(gt.Gb, workers=-1)[1].astype(np.int64) for p in PRIORS}
    treeG = refS.tree
    vcell = {}
    for p in PRIORS:                                                 # patches of the invisible cells (codes 5, 14, in range, with GT)
        cl, _ = cells_of(site, p)
        vcell[p] = np.isin(cl, [CID[c] for c in VIRTUAL_CELLS])
    log(site, "inputs", f"{time.time() - T0:.0f}s")
    done = []
    for res, key, priors in all_results(site):
        if only and res not in only:
            continue
        tr, vv, why = mesh_of(site, res)
        if all((jl(x_file(site, p, res).with_suffix(".json")) or {}).get("status") == "있음" for p in priors):
            log(site, res, "있음 (건너뜀)")
            continue
        if not tr.exists():
            for p in priors:
                jdump(x_file(site, p, res).with_suffix(".json"), dict(site=site, prior=p, result=res, status="결과 없음", mesh=short(tr), why=f"메시 없음 ({why})",
                                                                      made=now(), scientific_verdict=None))
            done.append(dict(result=res, status="결과 없음"))
            log(site, res, "결과 없음")
            continue
        t0 = time.time()
        V, F = DMC.read_mesh(tr)
        n_tri = int(len(F))
        need_full = [p for p in priors if dist_file(site, p, res) is None]
        sc = MeshScene(V, F) if need_full else None
        smp = DMC.result_sample(V, F, gt)
        del V, F
        t_load = time.time() - t0
        np.save(DIST / f"{site}__{res}__xyz.npy", smp.astype(np.float32))
        p0 = priors[0]
        f0 = dist_file(site, p0, res)
        z0 = np.load(f0) if (f0 is not None and p0 not in need_full) else None
        bS = z0["q_d"] if (z0 is not None and len(z0["q_d"]) == len(smp)) else None
        dr, nd, lat, gi = refS.query(smp, bS)
        if refB is not None:
            fb0 = b0gt_file(site, p0, res)
            bB = np.load(fb0)["q_d_b0gt"] if (fb0 is not None and bS is not None) else None
            drb, ndb, latb, _ = refB.query(smp, bB)
        for p in priors:
            u = U[p]
            full = None
            if p in need_full:
                full = full_dist(site, p, res, key, u, gt, sc, smp, n_scene, Nfull, own, near, treeG, tr, why, vv)
                if site == "B0_b10":
                    np.savez_compressed(DIST / f"{site}_{p}__{res}__b0gt.npz", q_d_b0gt=drb.astype(np.float32))
            z = np.load(dist_file(site, p, res))
            chk = dict(n_stored=int(len(z["q_d"])), n_now=int(len(smp)))
            same = chk["n_stored"] == chk["n_now"]
            chk["same_count"] = bool(same)
            if same and len(smp):
                chk["max_abs_dr_diff_m"] = float(np.max(np.abs(z["q_d"].astype(np.float64) - dr)))
                fb = b0gt_file(site, p, res)
                if refB is not None and fb is not None:
                    chk["max_abs_dr_b0gt_diff_m"] = float(np.max(np.abs(np.load(fb)["q_d_b0gt"].astype(np.float64) - drb)))
            if not same:
                raise RuntimeError(f"{site} {p} {res}: sample differs from the stored one {chk}")
            pa = z["q_patch"].astype(np.int64)                     # the stored nearest patch (distance task, cKDTree on the centres, no limit)
            pd = np.linalg.norm(smp - u.centre[pa], axis=1) if len(smp) else np.zeros(0)
            out = dict(dr=dr.astype(np.float32), ndist=nd.astype(np.float32), lat=lat.astype(np.float32), pd=pd.astype(np.float32))
            if refB is not None:
                out.update(dr_b=drb.astype(np.float32), ndist_b=ndb.astype(np.float32), lat_b=latb.astype(np.float32))
            meta = dict(site=site, prior=p, result=res, key=key, status="있음", mesh=short(tr), mesh_why=why, triangles=n_tri, sample_points=int(len(smp)),
                        check=chk, full_dist_counted_here=bool(full is not None), virtual=None)
            # the invisible cells on the virtual-view mesh
            vm = vcell[p]
            rows_v = np.nonzero(vm[u.r_pa])[0]
            if vv is not None and vv.exists():
                Vv, Fv = DMC.read_mesh(vv)
                scv = MeshScene(Vv, Fv)
                smv = DMC.result_sample(Vv, Fv, gt)
                del Vv, Fv
                rv = scv.distance(u.r_P[rows_v]) if len(rows_v) else np.zeros(0)
                qv, _ = DMC.closest(scv, u.r_P[rows_v]) if len(rows_v) else (np.zeros((0, 3)), None)
                n_rows = np.full((len(rows_v), 3), np.nan, np.float32)
                for s_ in np.unique(u.r_src[rows_v]):
                    m = u.r_src[rows_v] == s_
                    n_rows[m] = Nfull[int(s_)][u.r_pt[rows_v][m]]
                vs = oriented_sign(u.r_P[rows_v], qv, rv, n_rows, u.r_n[rows_v]) if len(rows_v) else np.zeros(0, np.int8)
                pav = trees[p].query(smv, workers=-1)[1].astype(np.int64) if len(smv) else np.zeros(0, np.int64)
                kv = vm[pav] if len(pav) else np.zeros(0, bool)
                R_ = refB if refB is not None else refS
                vdr, vnd, vlat, _ = R_.query(smv[kv])
                vpd = trees[p].query(smv[kv], workers=-1)[0] if kv.any() else np.zeros(0)
                out.update(v_r_idx=rows_v.astype(np.int32), v_r_d=np.asarray(rv, np.float32), v_r_sign=vs, v_q_patch=pav[kv].astype(np.int32),
                           v_q_dr=vdr.astype(np.float32), v_q_ndist=vnd.astype(np.float32), v_q_lat=vlat.astype(np.float32), v_q_pd=np.asarray(vpd, np.float32),
                           v_q_has_gt=u.has_gt[pav[kv]] if kv.any() else np.zeros(0, bool))
                meta["virtual"] = dict(mesh=short(vv), rows=int(len(rows_v)), sample_points_in_cells=int(kv.sum()), sample_points=int(len(smv)),
                                       ref="B0 영역 참값" if refB is not None else "장면 참값")
                del scv
            else:
                meta["virtual"] = dict(mesh=None if vv is None else short(vv), exists=False, rows=int(len(rows_v)))
            np.savez_compressed(x_file(site, p, res), **out)
            meta.update(seconds=dict(load=round(t_load, 1), total=round(time.time() - t0, 1)), made=now(), scientific_verdict=None)
            jdump(x_file(site, p, res).with_suffix(".json"), meta)
        del sc, smp
        done.append(dict(result=res, priors=priors, triangles=n_tri, seconds=round(time.time() - t0, 1), full=need_full))
        log(site, res, priors, f"tri {n_tri:,}", f"load {t_load:.0f}s total {time.time() - t0:.0f}s", "full" if need_full else "")
    rec = dict(site=site, log=done, seconds=round(time.time() - T0, 1), made=now(), scientific_verdict=None)
    old = jl(DIST / f"done_x_{site}.json")
    if old and only:
        new = {e["result"]: e for e in done}
        rec = dict(old, log=[new.pop(e["result"], e) for e in old["log"]] + list(new.values()), later=old.get("later", []) + [dict(results=list(only), made=now())])
    jdump(DIST / f"done_x_{site}.json", rec)
    log(site, "done", f"{time.time() - T0:.0f}s")


if __name__ == "__main__":
    a = sys.argv[1:]
    assert a and a[0] in SITES
    main(a[0], a[1:] or None)
