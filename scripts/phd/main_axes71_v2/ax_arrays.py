"""PHD-MAIN-AXES71-v2: the per-point arrays of one case x result and the value blocks of 1.1-1.2 (shared by 일 3-8).

arrays(site, prior, res) reads the per-point distance file (the distance task's form; ax_common.dist_file), this task's result-side extras
(__x.npz, a2x_sample.py) and the cells (AX/work/cells_<site>_<prior>.npz, a2_cells.py), and returns:
  rows  (the region rows = the GT points of the cells): d = |d_g|, sign, tau (the row's patch), patch, cell
  scene (the 전체 GT): d, sign, tau (the distance task's rule of 2026-10-17: own patch, else the nearest; ALS one tau), cell (-2 no patch)
  smp   (the result sample): patch (nearest centre, no limit), cell, tau (the patch's), has_gt, spacing (of the patch), pd (to the centre),
        dA = d_r to the scene GT, dP = d_r to the GT of the places (B0: ULS + primary, the distance task's __b0gt), nE = normal distance and
        lE = lateral distance to the scene GT, nP / lP the same to the GT of the places
  vrows / vsmp (the invisible cells on the virtual-view mesh, where it exists)
scientific_verdict: null."""
import numpy as np

from ax_common import CID, WORK, b0gt_file, dist_file, jl, x_file

OUT4 = 4.0


def cells(site, prior):
    return np.load(WORK / f"cells_{site}_{prior}.npz")


def arrays(site, prior, res, C=None, paths=None):
    """paths = (dist file, x file, b0gt file) to read instead of the ones found by name (일 9)."""
    f = dist_file(site, prior, res) if paths is None else paths[0]
    xf = x_file(site, prior, res) if paths is None else paths[1]
    if f is None or not xf.exists():
        meta = jl(xf.with_suffix(".json")) or {}
        return dict(status=meta.get("status", "결과 없음"))
    z = np.load(f)
    x = np.load(xf)
    C = C if C is not None else cells(site, prior)
    cell = C["cell"].astype(np.int64)
    spacing = C["spacing"].astype(np.float64)
    R = np.load(f"/out/regions_v3/regions_ext_v3_{site}_{prior}.npz")
    tau_patch = R["tau"].astype(np.float64)
    out = dict(status="있음")
    rp = z["r_patch"].astype(np.int64)
    out["rows"] = dict(d=z["r_d"].astype(np.float64), sign=z["r_sign"].astype(np.int8), tau=z["r_tau"].astype(np.float64), patch=rp, cell=cell[rp])
    has = z["s_patch"] >= 0
    tg = np.where(has, z["s_tau"].astype(np.float64), z["s_tau_near"].astype(np.float64))
    if prior == "ALS":
        tg = np.full(len(tg), float(np.unique(tau_patch)[0]))
    sg = np.where(has, z["s_sign"], z["s_sign_near"]).astype(np.int8)
    sp = z["s_patch"].astype(np.int64)
    out["scene"] = dict(d=z["s_d"].astype(np.float64), sign=sg, tau=tg, cell=np.where(sp >= 0, cell[np.maximum(sp, 0)], -2))
    qp = z["q_patch"].astype(np.int64)
    fb = b0gt_file(site, prior, res) if paths is None else paths[2]
    dP = np.load(fb)["q_d_b0gt"].astype(np.float64) if (site == "B0_b10" and fb is not None) else z["q_d"].astype(np.float64)
    nP = x["ndist_b"].astype(np.float64) if "ndist_b" in x.files else x["ndist"].astype(np.float64)
    lP = x["lat_b"].astype(np.float64) if "lat_b" in x.files else x["lat"].astype(np.float64)
    out["smp"] = dict(patch=qp, cell=cell[qp], tau=z["q_tau"].astype(np.float64), has_gt=z["q_has_gt"].astype(bool), spacing=spacing[qp], pd=x["pd"].astype(np.float64),
                      dA=z["q_d"].astype(np.float64), dP=dP, nE=x["ndist"].astype(np.float64), lE=x["lat"].astype(np.float64), nP=nP, lP=lP)
    if "v_r_idx" in x.files:
        vi = x["v_r_idx"].astype(np.int64)
        vp = x["v_q_patch"].astype(np.int64)
        out["vrows"] = dict(d=x["v_r_d"].astype(np.float64), sign=x["v_r_sign"].astype(np.int8), tau=z["r_tau"][vi].astype(np.float64), patch=rp[vi], cell=cell[rp[vi]])
        out["vsmp"] = dict(patch=vp, cell=cell[vp], tau=tau_patch[vp], has_gt=x["v_q_has_gt"].astype(bool), spacing=spacing[vp], pd=x["v_q_pd"].astype(np.float64),
                           dA=x["v_q_dr"].astype(np.float64), dP=x["v_q_dr"].astype(np.float64), nE=x["v_q_ndist"].astype(np.float64), lE=x["v_q_lat"].astype(np.float64),
                           nP=x["v_q_ndist"].astype(np.float64), lP=x["v_q_lat"].astype(np.float64))
    return out


def sel(a, m):
    return {k: v[m] for k, v in a.items()}


def cat(blocks):
    blocks = [b for b in blocks if b is not None]
    if not blocks:
        return None
    return {k: np.concatenate([b[k] for b in blocks]) for k in blocks[0]}


def q(a, p):
    return float(np.percentile(a, p)) if len(a) else None


def med_nmad(x):
    x = x[np.isfinite(x)]
    if not len(x):
        return None, None
    m = float(np.median(x))
    return m, 1.4826 * float(np.median(np.abs(x - m)))


def gt_block(g, with05=False):
    """GT-side values of 1.1-1.2 over the GT points g (d = |d_g| m, tau m, sign)."""
    d, t = g["d"], g["tau"]
    n = int(len(d))
    o = dict(n_gt=n)
    if not n:
        return o
    o["R_tau"] = float((d <= t).mean())
    o["R_0.2"] = float((d <= 0.2).mean())
    if with05:
        o["R_0.5"] = float((d <= 0.5).mean())
    o["mean"] = float(d.mean()) * 100
    o["cap1_mean"] = float(np.minimum(d, 1.0).mean()) * 100
    o["med"], o["p90"], o["p95"] = (100 * q(d, 50), 100 * q(d, 90), 100 * q(d, 95))
    o["out4"] = float((d > OUT4 * t).mean())
    o["far1"] = float((d > 1.0).mean())
    o["med_tau"] = float(np.median(d / t))
    s = g["sign"] != 0
    o["n_signed"] = int(s.sum())
    b, sp = med_nmad(d[s] * g["sign"][s]) if s.any() else (None, None)
    o["bias"] = None if b is None else 100 * b
    o["spread"] = None if sp is None else 100 * sp
    return o


COUNTS = ("A", "B", "C", "D", "E", "F")


def res_vals(s, c, place):
    """(distance, counted mask) of count c over the result points s; place=True reads the GT of the places (B0)."""
    dr = s["dP"] if place else s["dA"]
    if c == "A":
        return dr, np.ones(len(dr), bool)
    if c == "B":
        return dr, s["has_gt"]
    if c == "C":
        return dr, s["spacing"] <= s["tau"]
    if c == "D":
        return dr, s["spacing"] <= 0.5 * s["tau"]
    nd, lat = (s["nP"], s["lP"]) if place else (s["nE"], s["lE"])
    lim = 0.5 if c == "E" else 1.0
    ok = np.isfinite(nd) & np.isfinite(lat) & (lat <= lim)
    return nd, ok


def res_block(s, place, with05=False):
    n_all = int(len(s["dA"]))
    o = dict(n_res_all=n_all, far_patch=float((s["pd"] > 1.0).mean()) if n_all else None)
    for c in COUNTS:
        d, ok = res_vals(s, c, place)
        e = dict(n=int(ok.sum()), excluded=int((~ok).sum()), excluded_share=float((~ok).mean()) if n_all else None)
        if ok.any():
            dd, tt = d[ok], s["tau"][ok]
            e["P_tau"] = float((dd <= tt).mean())
            e["P_0.2"] = float((dd <= 0.2).mean())
            if with05:
                e["P_0.5"] = float((dd <= 0.5).mean())
            e["mean"] = float(dd.mean()) * 100
            e["cap1_mean"] = float(np.minimum(dd, 1.0).mean()) * 100
            e["med"], e["p90"], e["p95"] = (100 * q(dd, 50), 100 * q(dd, 90), 100 * q(dd, 95))
            e["out4"] = float((dd > OUT4 * tt).mean())
            e["far1"] = float((dd > 1.0).mean())
        o[c] = e
    return o


def f1(p, r):
    if p is None or r is None:
        return None
    return 0.0 if p + r == 0 else 2 * p * r / (p + r)


def combine(g, r):
    """F1 and Chamfer per count from a GT block and a result block."""
    o = {}
    for c in COUNTS:
        e = r.get(c, {})
        o[c] = dict(F1_tau=f1(e.get("P_tau"), g.get("R_tau")), F1_02=f1(e.get("P_0.2"), g.get("R_0.2")),
                    chamfer=None if e.get("mean") is None or g.get("mean") is None else 0.5 * (e["mean"] + g["mean"]))
        if "P_0.5" in e and "R_0.5" in g:
            o[c]["F1_05"] = f1(e["P_0.5"], g["R_0.5"])
    return o


def cell_sel(cellarr, key, SUMS):
    if key == "all":
        return np.ones(len(cellarr), bool)
    if key in SUMS:
        return np.isin(cellarr, [CID[c] for c in SUMS[key][1]])
    return cellarr == CID[key]
