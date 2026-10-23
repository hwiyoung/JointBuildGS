"""PHD-MAIN-UNCERT-v1 2.8 stop check, what was checked before asking (jointbuildgs:geogs-conf-guided-v1, CPU).

  python u2_diag_views.py <site> [...]   -> /out/work/diag_views_<site>.json

(1) The same 3,000 ALS-case refine patches as check_mvs: per view (>= 5 inner points of that view in the patch, before thinning)
    the view's median normal distance t_v and, paired, t_v minus the median of all the patch's inner points (all views). Per view: the
    median over its patches of t_v (the check's value) and of the paired difference; the view's tilt (optical axis from nadir) and the
    median angle between the patch normal and the line of sight. A camera or depth error moves every patch of a view (the paired value
    moves); a different subset of patches per view moves only t_v.
(2) Depth meaning: for 6 training views (3 nearest nadir, 3 most tilted) the prior render depth S0/s61/export/<site>/LoD2/prior/<view>.npy
    (the same export as the MVS maps) unprojected with the same camera and formula as the MVS points (z-depth), and also read as a
    distance along the ray; the normal distance of each point to the nearest LoD2 patch plane (centre within 0.2 m) for both readings.
scientific_verdict: null."""
import sys

import numpy as np
from scipy.spatial import cKDTree

sys.path.insert(0, "/repo/scripts/phd/main_uncert_v1")
sys.path.insert(0, "/repo/scripts/phd/main_axes71_v2")
import u_core as C  # noqa: E402
import u2_run as R2  # noqa: E402
import uc_common as U  # noqa: E402
import mvs_surface as MS  # noqa: E402


def main(site):
    T = U.Timer()
    D = U.D
    R2.build(site, "ALS", "mvs_a", [])
    G = R2.G
    pt = U.patches(site, "ALS")
    cand = np.nonzero(pt["cell"] == U.CID["c_refine"])[0]
    rng = np.random.default_rng([U.CFG["seed"], U.SITE_ID[site], 77])
    sel = np.sort(rng.choice(cand, min(3000, len(cand)), replace=False))
    cams, _ = MS.cameras(site)
    cc = []
    for c in cams:
        C2W = np.linalg.inv(np.asarray(c["W2C"], np.float64))
        cc.append((C2W[:3, 3], C2W[:3, 2]))
    tv, pair, ang, dist = {}, {}, {}, {}
    for i in sel:
        idx, t, rho, H = R2.column(i)
        o, runs, M = C.find_face(t, H, D)
        if o is None:
            continue
        m = np.abs(t - o) <= D["slab_half_m"]
        if m.sum() < D["min_inner"]:
            continue
        inn, tin = idx[m], t[m]
        pm = float(np.median(tin))
        vv = G["V"][inn]
        for w in np.unique(vv):
            k = vv == w
            if k.sum() >= 5:
                x = float(np.median(tin[k]))
                tv.setdefault(int(w), []).append(x)
                pair.setdefault(int(w), []).append(x - pm)
                ray = G["c"][i] - cc[w][0]
                dist.setdefault(int(w), []).append(float(np.linalg.norm(ray)))
                ang.setdefault(int(w), []).append(float(np.degrees(np.arccos(abs(ray @ G["n"][i]) / np.linalg.norm(ray)))))
    rows = []
    for w in sorted(tv):
        if len(tv[w]) < 100:
            continue
        tilt = float(np.degrees(np.arccos(abs(cc[w][1][2]))))
        rows.append(dict(view=cams[w]["name"], patches=len(tv[w]), t_v_cm=100 * float(np.median(tv[w])), paired_cm=100 * float(np.median(pair[w])),
                         tilt_deg=tilt, sight_to_normal_deg=float(np.median(ang[w])),
                         paired_p25_p75_cm=[100 * float(x) for x in np.percentile(pair[w], [25, 75])],
                         paired_share_over_15cm=float(np.mean(np.abs(pair[w]) > 0.15)), range_m_p50=float(np.median(dist[w]))))
    tvv = np.array([r["t_v_cm"] for r in rows]); pv = np.array([r["paired_cm"] for r in rows]); ti = np.array([r["tilt_deg"] for r in rows])
    sa = np.array([r["sight_to_normal_deg"] for r in rows])
    summ = dict(views=len(rows), t_v_range_cm=[float(tvv.min()), float(tvv.max())], paired_range_cm=[float(pv.min()), float(pv.max())],
                paired_spread_cm=float(pv.max() - pv.min()), paired_abs_p50_cm=float(np.median(np.abs(pv))),
                corr_tv_sight_angle=float(np.corrcoef(tvv, sa)[0, 1]) if len(rows) > 2 else None,
                tilt_of_views_t_v_over_7_5cm=[round(float(x), 1) for x in ti[np.abs(tvv - np.median(tvv)) > 7.5]],
                tilt_of_all_views_p10_p50_p90=[float(x) for x in np.percentile(ti, [10, 50, 90])])
    # (2) depth meaning on prior render depth
    lp = U.patches(site, "LoD2")
    tree = cKDTree(lp["centre"])
    tilts = np.array([np.degrees(np.arccos(abs(c[1][2]))) for c in cc])
    sees = np.array([len(tv.get(w, [])) for w in range(len(cams))])
    okv = np.nonzero(sees >= 100)[0]
    pick = list(okv[np.argsort(tilts[okv])[:3]]) + list(okv[np.argsort(tilts[okv])[-3:]])
    dm = []
    for w in pick:
        c = cams[w]
        f = U.S0 / "s61/export" / site / "LoD2/prior" / f"{c['name']}.npy"
        if not f.exists():
            dm.append(dict(view=c["name"], why="렌더 깊이 없음"))
            continue
        d = np.load(f).astype(np.float64)
        vv, uu = np.nonzero(np.isfinite(d) & (d > 0))
        if len(vv) > 200000:
            s_ = np.random.default_rng(0).choice(len(vv), 200000, replace=False)
            vv, uu = vv[s_], uu[s_]
        dd = d[vv, uu]
        x = (uu - np.float64(c["cx"])) / np.float64(c["fx"]); y = (vv - np.float64(c["cy"])) / np.float64(c["fy"])
        C2W = np.linalg.inv(np.asarray(c["W2C"], np.float64))
        res = {}
        for nm, scale in (("z_depth", 1.0), ("ray_distance", 1.0 / np.sqrt(1 + x * x + y * y))):
            Pc = np.stack([x * dd * scale, y * dd * scale, dd * scale], 1)
            P = Pc @ C2W[:3, :3].T + C2W[:3, 3]
            dist, j = tree.query(P, distance_upper_bound=0.5)
            ok = np.isfinite(dist)
            nd = np.einsum("ij,ij->i", P[ok] - lp["centre"][j[ok]], lp["normal"][j[ok]])
            res[nm] = dict(points=int(ok.sum()), abs_normal_dist_p50_cm=100 * float(np.median(np.abs(nd))) if ok.any() else None,
                           p90_cm=100 * float(np.percentile(np.abs(nd), 90)) if ok.any() else None)
        dm.append(dict(view=c["name"], tilt_deg=float(tilts[w]), **res))
    U.jdump(U.WORK / f"diag_views_{site}.json", dict(site=site, rule=__doc__, made=U.now(), summary=summ, views=rows, depth_meaning=dm,
                                                     seconds=T.mark("all"), scientific_verdict=None))
    U.log(site, summ)
    for r in dm:
        U.log(r)


if __name__ == "__main__":
    for s in sys.argv[1:]:
        main(s)
