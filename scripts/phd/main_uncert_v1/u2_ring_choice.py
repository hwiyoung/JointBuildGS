"""PHD-MAIN-UNCERT-v1 1.7 the ring radius (jointbuildgs:dev, CPU): chosen on the band patches (outside the evaluation range) by the
locked rule (config ring_choice), before any evaluation-range table of the final report.

  python u2_ring_choice.py   -> /out/work/ring_choice.json, /docs/tables/ring_choice.md|json

Band patch = not in_eval, GT plane (gt_status 0), the data's value and real error e. Per site: rho_MVS = Spearman(u, e) of MVS 판 가 over
the site's band patches of both patch sets together, rho_ALS = Spearman(u_A, e_A) over its ALS band patches; criterion = their mean (MVS
only if no ALS value). If every site has >= 1,000 band patches with a GT plane (both sets together) each site chooses on its own band,
else every site chooses on the other two sites' bands (leave one out). Pick = the largest criterion; the 1.5 m radius if its criterion is
within 0.02 of the largest. scientific_verdict: null."""
import sys

import numpy as np

sys.path.insert(0, "/repo/scripts/phd/main_uncert_v1")
import u3_lib as L  # noqa: E402
import uc_common as U  # noqa: E402
from u3_lib import md_table  # noqa: E402

RC = U.CFG["ring_choice"]


def band_values(S, sites):
    """pooled band arrays (u, e) of MVS a (both sets) and ALS (ALS set) over the given sites."""
    um, em, ua, ea = [], [], [], []
    for s in sites:
        for p in U.PRIORS:
            z = S.get(s, p)
            b = ~L.ev(z) & (z["gt_status"] == 0)
            for d, (U_, E_) in (("mvs_a", (um, em)),) + ((("als", (ua, ea)),) if p == "ALS" else ()):
                m = b & L.has(z, d) & np.isfinite(z[f"{d}_e"])
                U_.append(z[f"{d}_u"][m].astype(np.float64)); E_.append(z[f"{d}_e"][m].astype(np.float64))
    cat = lambda a: np.concatenate(a) if a else np.zeros(0)  # noqa: E731
    return cat(um), cat(em), cat(ua), cat(ea)


def main():
    radii = U.D["ring_radii_m"]
    St = {R: L.Store(R) for R in radii}
    counts = {}
    for s in U.SITES:
        n = 0
        for p in U.PRIORS:
            z = St[1.5].get(s, p)
            n += int((~L.ev(z) & (z["gt_status"] == 0)).sum())
        counts[s] = n
    own = all(v >= RC["min_per_site"] for v in counts.values())
    res, rows = {}, []
    for s in U.SITES:
        sites = [s] if own else [x for x in U.SITES if x != s]
        crit = {}
        for R in radii:
            um, em, ua, ea = band_values(St[R], sites)
            rm, nm = L.spearman(um, em)
            ra, na = L.spearman(ua, ea)
            c = np.mean([x for x in (rm, ra) if x is not None]) if (rm is not None or ra is not None) else None
            crit[R] = dict(rho_mvs=rm, n_mvs=nm, rho_als=ra, n_als=na, criterion=float(c) if c is not None else None)
            rows.append([U.SITE_KO[s], "+".join(U.SITE_KO[x] for x in sites), f"{R:g}", f"{nm:,}", L.fmt(rm, "rank", nm), f"{na:,}", L.fmt(ra, "rank", na),
                         L.fmt(crit[R]["criterion"], "rank", nm)])
        best = max(radii, key=lambda R: -1e9 if crit[R]["criterion"] is None else crit[R]["criterion"])
        pick = 1.5 if (crit[1.5]["criterion"] is not None and crit[best]["criterion"] - crit[1.5]["criterion"] <= 0.02) else best
        res[s] = dict(bands_used=sites, per_R=crit, best=best, pick=pick)
        rows.append([U.SITE_KO[s], "고름", f"{pick:g}", "", "", "", "", f"가장 큰 잣대 {best:g} m"])
    picks = sorted({v["pick"] for v in res.values()})
    out = dict(rule=RC, band_patches_with_gt_plane=counts, own_band=own, per_site=res, picks=picks, made=U.now(), scientific_verdict=None)
    U.jdump(U.WORK / "ring_choice.json", out)
    note = (f"띠 패치(평가 범위 밖) 가운데 참값 평면이 있는 패치: " + ", ".join(f"{U.SITE_KO[k]} {v:,}" for k, v in counts.items())
            + (". 모든 지역이 1,000개 이상이라 지역마다 자기 띠로 골랐다." if own else ". 1,000개 미만인 지역이 있어 세 지역 모두 한 지역을 남기고 나머지 두 지역의 띠로 골랐다."))
    L.write(U.DOCS / "tables", "ring_choice", "1.7 고리 크기 고르기 (띠 패치)", md_table(["지역", "고른 띠", "R (m)", "MVS 패치", "ρ_MVS", "항공 LiDAR 패치", "ρ_항공 LiDAR",
                                                                                     "잣대"], rows), out, note)
    U.log(out["picks"], {k: (v["best"], v["pick"]) for k, v in res.items()})


if __name__ == "__main__":
    main()
