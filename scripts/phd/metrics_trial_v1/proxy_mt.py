"""PHD-MAIN-METRICS-TRIAL-v1 record (purpose: check the per-patch MVS proxy that splits 'prior wrong' (11) from 'both wrong' (12)
and 'measured agreement' (2) from 'image wrong' (3); not a criterion) (jointbuildgs:dev, CPU; pre-training data only).

  python proxy_mt.py

The region rule reads |MVS - GT| per patch as |(-mvs_r_med) - gt_med|: the median of the residuals along the view rays through
the prior patch. When the prior is metres away from the current surface those rays meet the current surface away from the
patch. Here the MVS height is read at the GT points instead (paths/mvs_points.npz: median of the confidence-1 MVS points in the
GT point's 0.1 m cell), its median per patch (>= 5 GT roof points with a value) is compared with tau, and the patches of 11 / 12
and of 2 / 3 are cross-tabulated (the 2 / 3 part added after the first training's metrics: the spread in 'image wrong' was 67 %) (roof-like patches; B173 wings = the stage-0 'changed' points). Writes /out/tables/proxy_check.json.
scientific_verdict: null."""
import numpy as np

from mt_common import OUT, jdump


def main():
    G = np.load(OUT / "defs/gt_classes.npz")
    zg = G["xyz"][:, 2].astype(np.float64)
    mv = np.load(OUT / "paths/mvs_points.npz")
    o = np.argsort(mv["point"])
    mpt, mz = mv["point"][o], mv["z"][o].astype(np.float64)
    res = {}
    for prior in ("LoD2", "ALS"):
        r = np.load(OUT / "defs" / f"rows_{prior}.npz")
        R = np.load(OUT / "regions_ext" / f"regions_ext_B173nb_b10_{prior}.npz")
        m = (r["kind"] == 1) & np.isin(r["code"], (2, 3, 11, 12))
        pt, pa = r["point"][m], r["patch"][m]
        i = np.searchsorted(mpt, pt)
        ok = i < len(mpt)
        ok[ok] &= mpt[i[ok]] == pt[ok]
        d = np.full(len(pt), np.nan)
        d[ok] = mz[i[ok]] - zg[pt[ok]]
        wing = G["changed"][pt]
        good = np.isfinite(d)
        order = np.lexsort((d[good], pa[good]))
        pg, dg, wg = pa[good][order], d[good][order], wing[good][order]
        start = np.r_[0, np.nonzero(pg[1:] != pg[:-1])[0] + 1]
        cnt = np.diff(np.r_[start, len(pg)])
        med = 0.5 * (dg[start + (cnt - 1) // 2] + dg[start + cnt // 2])
        patch = pg[start]
        wshare = np.add.reduceat(wg.astype(np.int64), start) / cnt
        keep = cnt >= 5
        patch, med, wshare = patch[keep], med[keep], wshare[keep]
        tau = R["tau"][patch].astype(np.float64)
        code = R["code_ext"][patch]
        proxy = np.abs(R["mvs_minus_prior"][patch].astype(np.float64) - R["gt_med"][patch].astype(np.float64))
        at_gt_ok = np.abs(med) <= tau
        area = R["area"][patch]
        e = {}
        for nm, sel in (("all", np.ones(len(patch), bool)), ("B173 wings (> half of the points)", wshare > 0.5), ("elsewhere", wshare <= 0.5)):
            row = {}
            for c in (2, 3, 11, 12):
                mm = sel & (code == c)
                row[str(c)] = dict(patches=int(mm.sum()), area_m2=round(float(area[mm].sum()), 1),
                                   mvs_at_gt_within_tau=int((mm & at_gt_ok).sum()), area_within_tau_m2=round(float(area[mm & at_gt_ok].sum()), 1),
                                   median_mvs_minus_gt_at_gt_m=None if not mm.any() else round(float(np.median(med[mm])), 3),
                                   median_proxy_abs_m=None if not mm.any() else round(float(np.median(proxy[mm])), 3))
            e[nm] = row
        res[prior] = dict(patches_with_5_points=int(len(patch)), by_part=e)
    jdump(OUT / "tables/proxy_check.json", dict(rule="per patch (>= 5 GT roof points with an MVS value): median of z_MVS(0.1 m cell) - z_GT at the GT points, compared with tau; cross-tabulated with the region codes 11 / 12 and 2 / 3 (record, not a criterion)", result=res, scientific_verdict=None))
    print(res)


if __name__ == "__main__":
    main()
