"""PHD-MAIN-UNCERT-v1 일 2: the per-patch values of one site, patch set and ring radius in one file (order 9 'patch_values'), with the
values of 1.4 (jointbuildgs:dev, CPU).

  python u2_merge.py <R> [site ...]   -> /out/patch_values/<site>__<LoD2|ALS>__R<R>.npz, /out/patch_values/<site>__<set>__R<R>.json

Keys: the patch table (centre, normal, roof_like, surf, kind, in_eval, cell, code, area, tau, gt_med, edge, building, roof_type), gt_*
(1.5 GT face and plane: status 0 = plane, 1 = no face, 2 = fewer than 10 GT points, 3 = no candidate; runs = layer runs), and per data
(mvs_a, mvs_b, als on the ALS set) <data>_<field> of u2_run.FIELDS_V (status 0 = value, 1 = no face, 2 = too few points, 3 = no
candidate plane). Derived (1.4): u_prior (LoD2 set 0.20 m; ALS set = als_u where als has a value), for v in a, b: w_<v> = MVS weight
share (both values: u_prior^2 / (u_M^2 + u_prior^2); only MVS: 1; only prior: 0; none: NaN), pW_<v> = w x p_M (only prior: 0),
z_<v> = |p_M| / sqrt(u_M^2 + u_prior^2) (both values), the position errors errM_<v> = |p_M - p_G|, errP = |p_G| (prior position 0),
errW_<v> = |pW - p_G|; eL = |p_G| on the LoD2 set (1.5). scientific_verdict: null."""
import sys

import numpy as np

sys.path.insert(0, "/repo/scripts/phd/main_uncert_v1")
import uc_common as U  # noqa: E402

PT_KEYS = ("centre", "normal", "roof_like", "surf", "kind", "in_eval", "cell", "code", "area", "tau", "gt_med", "edge", "building", "roof_type")


def merge(site, pset, R):
    out = {}
    with np.load(U.WORK / f"patches_{site}_{pset}.npz") as z:
        for k in PT_KEYS:
            out[k] = z[k]
    with np.load(U.WORK / f"gt_{site}_{pset}.npz") as z:
        for k in z.files:
            out[f"gt_{k}"] = z[k]
    datas = ("mvs_a", "mvs_b", "als") if pset == "ALS" else ("mvs_a", "mvs_b")
    missing = []
    for d in datas:
        f = U.WORK / f"val_{site}_{pset}_{d}_R{R}.npz"
        if not f.exists():
            missing.append(d)
            continue
        with np.load(f) as z:
            for k in z.files:
                out[f"{d}_{k}"] = z[k]
    N = len(out["centre"])
    if pset == "LoD2":
        up = np.full(N, U.D["lod2_u_m"])
    else:
        up = np.where(out.get("als_status", np.full(N, -1)) == 0, out.get("als_u", np.full(N, np.nan)), np.nan)
    out["u_prior"] = up.astype(np.float64)
    pG = np.where(out["gt_status"] == 0, out["gt_p"], np.nan).astype(np.float64)
    out["errP"] = np.abs(pG)
    if pset == "LoD2":
        out["eL"] = np.abs(pG)
    for v in ("a", "b"):
        d = f"mvs_{v}"
        if f"{d}_status" not in out:
            continue
        hasM = out[f"{d}_status"] == 0
        uM = np.where(hasM, out[f"{d}_u"], np.nan).astype(np.float64)
        pM = np.where(hasM, out[f"{d}_p"], np.nan).astype(np.float64)
        hasP = np.isfinite(up)
        w = np.full(N, np.nan)
        both = hasM & hasP
        den = uM[both] ** 2 + up[both] ** 2
        w[both] = np.where(den > 0, up[both] ** 2 / np.where(den > 0, den, 1), 0.5)
        w[hasM & ~hasP] = 1.0
        w[~hasM & hasP] = 0.0
        pW = np.full(N, np.nan)
        pW[both | (hasM & ~hasP)] = w[both | (hasM & ~hasP)] * pM[both | (hasM & ~hasP)]
        pW[~hasM & hasP] = 0.0
        z = np.full(N, np.nan)
        z[both] = np.abs(pM[both]) / np.sqrt(np.maximum(den, 1e-30))
        out[f"w_{v}"], out[f"pW_{v}"], out[f"z_{v}"] = w, pW, z
        out[f"errM_{v}"] = np.abs(pM - pG)
        out[f"errW_{v}"] = np.abs(pW - pG)
    f = U.PV / f"{site}__{pset}__R{R}.npz"
    np.savez_compressed(f, **out)
    U.jdump(f.with_suffix(".json"), dict(site=site, set=pset, R=R, rule=__doc__, made=U.now(), patches=int(N), keys=sorted(out),
                                         missing_data=missing, scientific_verdict=None))
    U.log(site, pset, R, N, "missing", missing)


if __name__ == "__main__":
    R = float(sys.argv[1])
    for s in sys.argv[2:] or U.SITES:
        for p in U.PRIORS:
            merge(s, p, R)
