"""PHD-MAIN-STAGE1-v1 3.1-3.2: region files v3 of the four sites x two priors (jointbuildgs:dev, CPU; pre-training data only;
definitions = configs main_stage1_v1.json 'regions_v3' and 'premise').

  python regions_v3.py mvs       z_MVS at the GT points in float64 (the fix's reading) -> /out/regions_v3/mvs_at_gt_<site>.npz
  python regions_v3.py check     the chain on the stage-0 labels (/s0/regions, /s0/s61/box_gt): must reproduce the trial's
                                 code_ext (/mt/regions_ext) and the fix's code_ext_v2 (/mf/regions_v2) exactly -> v3/checks/chain.json
  python regions_v3.py run       the chain on the v3 labels (/out/v3/regions from regions_v1.py, /out/v3/box_gt) + gt_suspect +
                                 premise violation / band -> /out/regions_v3/regions_ext_v3_<site>_<prior>.npz, moves.json / .md,
                                 premise.json, /out/figs/regions_v3_<site>.png
  python regions_v3.py maps      the maps only

Chain (rules of the stage-0 / trial / fix tasks, copied here with the input folders as parameters): agreement codes of regions_v1.py
-> codes 11-14 and GT point counts (regions_ext_v1.code_ext / gt_rows) and the B173 unseen split (current top from the moved GT)
-> the v2 split by the patch median of z_MVS - z_GT at the patch's GT points (z_MVS = the 0.1 m cell medians of the fix's
mvs_at_gt files: same MVS, same XY). scientific_verdict: null."""
import json
import sys
from pathlib import Path

import numpy as np
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
from scipy.spatial import cKDTree

from s1_common import COL, DR, KO, MF, MT, NAME, ORDER, OUT, PRIOR_KO, S0, SCFG1, SITES, Timer, boxes, gt_arrays, jdump, label_source, log, owner_rows, setup_fonts, xy_to_uv
from src.phd.metrics_v3 import premise as prem
from src.phd.metrics_v3 import regions
from src.phd.prior_propagation_v6 import rule

plt = setup_fonts()
B173 = "DEBY_LOD2_4959326"
UNSEEN_SITES = ["B173nb_b10", "B173_b0"]
MIN_POINTS = 5
SUSPECT = json.loads(Path("/repo/configs/phd/metrics_fix_v1/gt_suspect_rule_v1.json").read_text())["values"]
PR = SCFG1["premise"]
K_CONFLICT = {"LoD2": 1.0, "ALS": 2.0}
R1_HALL_GML = "DEBY_LOD2_4906968_6446cb86-cefc-4c77-9ac7-79641e44b940_2"


# ------------------------------------------------------------------ the trial's rules (regions_ext_v1.py), inputs as parameters
def code_ext(R):
    c = R["code"].astype(np.int8).copy()
    conflict = R["code"] == 1
    st = R["state"]
    mvs = R["mvs_minus_prior"].astype(np.float64)
    off = ~(np.abs(mvs - R["gt_med"].astype(np.float64)) <= R["tau"].astype(np.float64))     # nan (no MVS value) -> off
    c[conflict] = -9
    c[conflict & (st == rule.ST_SUPPORT) & ~off] = 11
    c[conflict & (st == rule.ST_SUPPORT) & off] = 12
    c[conflict & (st == rule.ST_MISSING)] = 13
    c[conflict & (st == rule.ST_INVISIBLE)] = 14
    assert not (c == -9).any(), "a true conflict without a state"
    return c


def gt_rows(gt_dir, site, prior, n):
    D = Path(gt_dir) / site
    o = np.load(D / f"gt_owner_{prior}.npz")
    cnt = np.bincount(o["patch"], minlength=n).astype(np.int64)
    if site.startswith("B0") and (D / f"labels_uls_{prior}.npz").exists():
        G = np.load(D / f"labels_{prior}.npz")
        Gu = np.load(D / f"labels_uls_{prior}.npz")
        use = (G["label"] < 0) & (Gu["label"] >= 0)
        ou = np.load(D / f"gt_owner_uls_{prior}.npz")
        cu = np.bincount(ou["patch"], minlength=n).astype(np.int64)
        cnt = np.where(use, cu, cnt)
    return cnt


def unseen_split(gt_dir, site, R, tau_unseen=None):
    """inferred split of the B173 unseen wall patches (LoD2 file); -2 elsewhere (trial rule; the current top from gt_dir's GT)."""
    U = np.load(S0 / "s61/box" / site / "LoD2" / "units.npz")
    tab = {r["ext"]: r for r in json.loads((DR / "s02_box" / site / "lod2_surfaces.json").read_text())["surfaces"]}
    se = U["surf_ext"][U["loc_surface"]]
    bld = np.array([tab[int(e)]["building"] == B173 for e in se])
    un = bld & (U["loc_kind"] == 2) & (U["state"] == rule.ST_INVISIBLE) & R["in_eval"]
    lab = np.full(len(se), -2, np.int8)
    top = np.full(len(se), np.nan, np.float32)
    idx = np.nonzero(un)[0]
    if not len(idx):
        return lab, top, un
    c = U["loc_center"][idx]
    n = np.array([tab[int(e)]["normal"] for e in se[idx]], np.float64)
    nh = n[:, :2] / np.linalg.norm(n[:, :2], axis=1, keepdims=True)
    g = np.load(Path(gt_dir) / site / "gt_points.npz")["xyz"].astype(np.float64)
    tree = cKDTree(g[:, :2])
    L = tree.query_ball_point(c[:, :2] - nh * 1.15, 1.25)
    tau_w = float(np.median(R["tau"][un]))
    for k, l in enumerate(L):
        if not l:
            continue
        P = g[l]
        v = P[:, :2] - c[k, :2]
        dep = -(v @ nh[k])
        al = np.abs(v @ np.array([-nh[k, 1], nh[k, 0]]))
        m = (dep >= 0.3) & (dep <= 2.0) & (al <= 0.5)
        if m.sum() >= 5:
            top[idx[k]] = P[m, 2].max()
    d = c[:, 2] - top[idx].astype(np.float64)
    li = np.full(len(idx), -1, np.int8)
    li[d > tau_w] = 1
    li[d < -tau_w] = 0
    li[np.abs(d) <= tau_w] = 2
    lab[idx] = li
    return lab, top, un


# ------------------------------------------------------------------ the fix's v2 split with a given GT
def mvs_read(sites):
    """z_MVS at the GT points in float64 (the fix's reading: 0.1 m cell medians of the box MVS geometric depth, >= 3 points) for the
    points the fix read (its mvs_at_gt index lists: same GT XY) -> /out/regions_v3/mvs_at_gt_<site>.npz. The fix stored float32;
    float64 is kept here so that the chain reproduces the fix's codes exactly."""
    from s1_common import PREP, Views, read_depth_bin, mvs_views
    from src.phd.metrics_v3.cells import CellMedian
    (OUT / "regions_v3").mkdir(parents=True, exist_ok=True)
    V = Views()
    for site in sites:
        T = Timer()
        z0 = np.load(MF / "regions_v2" / f"mvs_at_gt_{site}.npz")
        A = gt_arrays(S0 / "s61/box_gt", site)
        keys = [k for k in A if f"{k}_index" in z0.files]
        xy = np.concatenate([A[k][z0[f"{k}_index"], :2] for k in keys])
        cm = CellMedian(xy, 0.1)
        mv = PREP / "mvs" / f"box_{site}" / "stereo/depth_maps"
        for n in mvs_views(site):
            d = read_depth_bin(mv / f"{n}.geometric.bin")
            ok = np.isfinite(d) & (d > 0)
            cm.add(V.C(n)[None, :] + d[ok][:, None].astype(np.float64) * V.rays(n, np.float64)[ok])
        z, cnt = cm.medians(3)
        out, o = {}, 0
        for k in keys:
            n_ = len(z0[f"{k}_index"])
            out[f"{k}_index"] = z0[f"{k}_index"]
            out[f"{k}_z_mvs"] = z[o:o + n_].astype(np.float64)
            out[f"{k}_n"] = cnt[o:o + n_].astype(np.int32)
            o += n_
        np.savez_compressed(OUT / "regions_v3" / f"mvs_at_gt_{site}.npz", **out)
        f32 = np.concatenate([z0[f"{k}_z_mvs"] for k in keys]).astype(np.float64)
        log(site, "MVS read", len(xy), "max |f64 - fix f32|", float(np.nanmax(np.abs(z - f32))), T.mark("all"))


def mvs_full(site, arrays):
    """z_MVS per GT point of each array (float64 reading of mvs_read; NaN where the fix did not read the point)."""
    z = np.load(OUT / "regions_v3" / f"mvs_at_gt_{site}.npz")
    out = {}
    for k, X in arrays.items():
        zf = np.full(len(X), np.nan)
        if f"{k}_index" in z.files:
            zf[z[f"{k}_index"]] = z[f"{k}_z_mvs"]
        out[k] = zf
    return out


def chain(site, prior, gt_dir, reg_dir):
    """the full chain of one site x prior. Returns the arrays of the region file and the rows used."""
    R = np.load(Path(reg_dir) / f"regions_{site}_{prior}.npz")
    ce = code_ext(R)
    n = len(ce)
    arrays = {k: R[k] for k in R.files}
    arrays.update(code_ext=ce, code_ext_values=np.array(sorted(NAME)), code_ext_names=np.array([NAME[k] for k in sorted(NAME)]),
                  gt_points=gt_rows(gt_dir, site, prior, n).astype(np.int32))
    if prior == "LoD2" and site in UNSEEN_SITES:
        ul, top, un = unseen_split(gt_dir, site, R)
        arrays.update(unseen_label_inferred=ul, unseen_top_behind=top)
    A = gt_arrays(gt_dir, site)
    zm = mvs_full(site, A)
    rows = owner_rows(gt_dir, site, prior, label_source(gt_dir, site, prior, n))
    pas, vals, pv = [], [], []
    for name, pt, pa, va, kd in rows:
        m = kd == 1
        dz = zm[name][pt[m]] - A[name][pt[m], 2]
        vals.append(dz)
        pas.append(pa[m])
        pv.append(dz + va[m].astype(np.float64))            # z_MVS - z_prior = (z_MVS - z_GT) + (z_GT - z_prior)
    pa_all = np.concatenate(pas)
    dmed, ncnt = regions.patch_median(pa_all, np.concatenate(vals), n)
    c2, kept = regions.split_v2(ce, R["kind"], R["tau"], dmed, ncnt, MIN_POINTS)
    pmed, _ = regions.patch_median(pa_all, np.concatenate(pv), n)
    arrays.update(code_ext_v2=c2, mvs_minus_gt_at_gt=dmed.astype(np.float32), n_mvs_at_gt=ncnt.astype(np.int32), v1_kept=kept)
    return arrays, pmed, rows, A


def check():
    T = Timer()
    res, ok = {}, True
    for site in SITES:
        for prior in ("LoD2", "ALS"):
            a, _, _, _ = chain(site, prior, S0 / "s61/box_gt", S0 / "regions")
            t = np.load(MT / "regions_ext" / f"regions_ext_{site}_{prior}.npz")
            f = np.load(MF / "regions_v2" / f"regions_ext_v2_{site}_{prior}.npz")
            e = dict(code_ext=bool(np.array_equal(a["code_ext"], t["code_ext"])), gt_points=bool(np.array_equal(a["gt_points"], t["gt_points"])),
                     code_ext_v2=bool(np.array_equal(a["code_ext_v2"], f["code_ext_v2"])), v1_kept=bool(np.array_equal(a["v1_kept"], f["v1_kept"])),
                     mvs_minus_gt_at_gt=bool(np.array_equal(a["mvs_minus_gt_at_gt"], f["mvs_minus_gt_at_gt"], equal_nan=True)))
            if "unseen_label_inferred" in t.files:
                e["unseen_label_inferred"] = bool(np.array_equal(a["unseen_label_inferred"], t["unseen_label_inferred"]))
            res[f"{site}/{prior}"] = e
            ok &= all(e.values())
            log(site, prior, e, T.mark(f"{site}_{prior}"))
    (OUT / "v3/checks").mkdir(parents=True, exist_ok=True)
    jdump(OUT / "v3/checks/chain.json", dict(all_equal=bool(ok), files=res, seconds=T.marks, scientific_verdict=None))
    print("chain check", "all equal" if ok else "DIFFER", res)


# ------------------------------------------------------------------ gt_suspect (the fix rule) on the v3 codes
def suspect(site, prior, arrays, A, rows, attrs):
    """double_adj OR multi-return share >= 5 % of the owned ULS points; roof-like codes 2 and 3 (v3) evaluated."""
    n_p = len(arrays["code_ext_v3"])
    X = A["gt_points"]
    c25 = SUSPECT["cell_m"]
    q = np.floor(X[:, :2] / c25).astype(np.int64)
    key = q[:, 0] * 10_000_000 + q[:, 1]
    o = np.argsort(key)
    ks, zs = key[o], X[o, 2]
    start = np.r_[0, np.nonzero(ks[1:] != ks[:-1])[0] + 1]
    uk = ks[start]
    zmax = np.maximum.reduceat(zs, start)
    zmin = np.minimum.reduceat(zs, start)
    U = np.load(S0 / "s61/box" / site / prior / "units.npz")
    nrm = np.cross(U["loc_t1"], U["loc_t2"])
    nrm /= np.maximum(np.linalg.norm(nrm, axis=1, keepdims=True), 1e-12)
    slope = np.degrees(np.arccos(np.clip(np.abs(nrm[:, 2]), 0, 1)))
    sel = np.nonzero(np.isin(arrays["code_ext_v3"], (2, 3)) & (arrays["kind"] == 1))[0]
    cc = arrays["centre"][sel]
    qk = np.floor(cc[:, :2] / c25).astype(np.int64)
    kk = qk[:, 0] * 10_000_000 + qk[:, 1]
    i = np.searchsorted(uk, kk)
    hit = i < len(uk)
    hit[hit] &= uk[i[hit]] == kk[hit]
    rng_ = np.full(len(sel), np.nan)
    rng_[hit] = zmax[i[hit]] - zmin[i[hit]]
    adj = (np.nan_to_num(rng_, nan=0.0) - c25 * np.sqrt(2) * np.tan(np.radians(np.minimum(slope[sel], SUSPECT["slope_cap_deg"])))) > SUSPECT["double_layer_m"]
    nr = attrs["number_of_returns"]
    tot = np.zeros(n_p)
    mul = np.zeros(n_p)
    up = np.ones(n_p, bool) if site.startswith("B0") else np.zeros(n_p, bool)
    for name, pt, pa, va, kd in owner_rows(OUT / "v3/box_gt", site, prior, up):
        if name != "gt_points":
            continue
        m = (kd == 1) & (nr[pt] >= 0)
        np.add.at(tot, pa[m], 1)
        np.add.at(mul, pa[m], (nr[pt[m]] > 1).astype(float))
    mlt = (mul[sel] / np.maximum(tot[sel], 1)) >= SUSPECT["multi_return_share"]
    ev = np.zeros(n_p, bool)
    sus = np.zeros(n_p, bool)
    ev[sel] = tot[sel] > 0
    sus[sel] = (adj | mlt) & ev[sel]
    return sus, ev


def uls_attrs():
    """intensity / returns of the box GT points owned by roof-like patches of codes 2 / 3 (v3), matched to the raw ULS (the fix's
    obs_check.uls_attributes on the box-aligned points of the stage-0 GT; the point order equals the v3 GT)."""
    sys.path.insert(0, "/repo/scripts/phd/metrics_fix_v1")
    import obs_check as oc
    Xs, need, sh = {}, {}, {}
    for site in SITES:
        X = np.load(S0 / "s61/box_gt" / site / "gt_points.npz")["xyz"].astype(np.float64)
        nd = np.zeros(len(X), bool)
        for prior in ("LoD2", "ALS"):
            f = np.load(OUT / "regions_v3" / f"_pre_{site}_{prior}.npz")
            c = f["code_ext_v3"]
            pp = np.nonzero(np.isin(c, (2, 3)) & (f["kind"] == 1))[0]
            mk = np.zeros(len(c), bool)
            mk[pp] = True
            up = np.ones(len(c), bool) if site.startswith("B0") else np.zeros(len(c), bool)
            for name, pt, pa, va, kd in owner_rows(OUT / "v3/box_gt", site, prior, up):
                if name == "gt_points":
                    nd[pt[(kd == 1) & mk[pa]]] = True
        Xs[site], need[site] = X, nd
        sh[site] = json.loads((DR / "s52/box_gt" / site / "gt_summary.json").read_text())["height_alignment"]["shift_m"]
    return oc.uls_attributes(Xs, need, sh)


def run():
    T = Timer()
    O = OUT / "regions_v3"
    O.mkdir(parents=True, exist_ok=True)
    (OUT / "figs").mkdir(exist_ok=True)
    tmp = {}
    for site in SITES:
        for prior in ("LoD2", "ALS"):
            a, pmed, rows, A = chain(site, prior, OUT / "v3/box_gt", OUT / "v3/regions")
            a["code_ext_v3"] = a.pop("code_ext_v2")
            prev = np.load(MF / "regions_v2" / f"regions_ext_v2_{site}_{prior}.npz")
            a["code_ext_v2_prev"] = prev["code_ext_v2"]
            pval = np.where(a["v1_kept"], a["mvs_minus_prior"].astype(np.float64), pmed)
            a["premise_value"] = pval.astype(np.float32)
            np.savez_compressed(O / f"_pre_{site}_{prior}.npz", **a)
            tmp[(site, prior)] = A
            log(site, prior, "chain", T.mark(f"chain_{site}_{prior}"))
    attrs = uls_attrs()
    T.mark("uls")
    moves, summ = {}, {}
    for site in SITES:
        for prior in ("LoD2", "ALS"):
            a = dict(np.load(O / f"_pre_{site}_{prior}.npz"))
            rows = owner_rows(OUT / "v3/box_gt", site, prior, label_source(OUT / "v3/box_gt", site, prior, len(a["code_ext_v3"])))
            sus, ev = suspect(site, prior, a, tmp[(site, prior)], rows, attrs[site])
            a.update(gt_suspect=sus, gt_suspect_evaluated=ev)
            viol, within, band = prem.split(a["code_ext_v3"], a["premise_value"], a["tau"], K_CONFLICT[prior], a["centre"], radius=2.0)
            a.update(premise_violation=viol, obs_within_threshold=within, premise_band=band)
            np.savez_compressed(O / f"regions_ext_v3_{site}_{prior}.npz", **a)
            (O / f"_pre_{site}_{prior}.npz").unlink()
            area, c2, c3 = a["area"], a["code_ext_v2_prev"], a["code_ext_v3"]
            e = {}
            for cc in sorted(set(np.unique(c2).tolist()) | set(np.unique(c3).tolist())):
                if cc < 0:
                    continue
                e[f"v2 {cc}"] = dict(patches=int((c2 == cc).sum()), area_m2=round(float(area[c2 == cc].sum()), 1))
                e[f"v3 {cc}"] = dict(patches=int((c3 == cc).sum()), area_m2=round(float(area[c3 == cc].sum()), 1))
            mv = (c2 != c3)
            pairs = {}
            for x, y in zip(c2[mv], c3[mv]):
                pairs[f"{x}->{y}"] = pairs.get(f"{x}->{y}", 0) + 1
            e["moved"] = {k: dict(patches=v, area_m2=round(float(area[mv & (c2 == int(k.split('->')[0])) & (c3 == int(k.split('->')[1]))].sum()), 1)) for k, v in sorted(pairs.items())}
            moves[f"{site}/{prior}"] = e
            ie = a["in_eval"]
            summ[f"{site}/{prior}"] = dict(
                observation_error=dict(patches=int((ie & (c3 == 3)).sum()), area_m2=round(float(area[ie & (c3 == 3)].sum()), 1)),
                premise_violation=dict(patches=int((ie & viol).sum()), area_m2=round(float(area[ie & viol].sum()), 1)),
                within_threshold=dict(patches=int((ie & within).sum()), area_m2=round(float(area[ie & within].sum()), 1)),
                premise_band=dict(patches=int((ie & band).sum()), area_m2=round(float(area[ie & band].sum()), 1)),
                support_agreement=dict(patches=int((ie & (c3 == 2)).sum()), area_m2=round(float(area[ie & (c3 == 2)].sum()), 1)),
                gt_suspect_obs=dict(flagged_area_m2=round(float(area[ie & (c3 == 3) & sus].sum()), 1)),
                k_tau=K_CONFLICT[prior], tau_roof=float(np.median(a["tau"][a["kind"] == 1])))
            log(site, prior, summ[f"{site}/{prior}"])
        draw_maps(site)
    jdump(O / "moves.json", dict(rule=SCFG1["regions_v3"], moves=moves, seconds=T.marks, scientific_verdict=None))
    jdump(O / "premise.json", dict(rule=PR, areas=summ, checks=checks(), seconds=T.marks, scientific_verdict=None))
    print("regions v3 done", T.marks)


def site_faces(site, gmls):
    """LoD2 patches of the listed faces; ALS patches within 0.5 m (plan) of those LoD2 patch centres (sites_v1 membership rule)."""
    tab = json.loads((DR / "s02_box" / site / "lod2_surfaces.json").read_text())["surfaces"]
    exts = {r["ext"] for r in tab if r["gml"] in gmls}
    U = np.load(S0 / "s61/box" / site / "LoD2" / "units.npz")
    se = U["surf_ext"][U["loc_surface"]]
    lod = np.isin(se, list(exts))
    Ua = np.load(S0 / "s61/box" / site / "ALS" / "units.npz")
    d, _ = cKDTree(U["loc_center"][lod][:, :2]).query(Ua["loc_center"][:, :2], distance_upper_bound=0.5) if lod.any() else (np.full(len(Ua["loc_center"]), np.inf), None)
    return dict(LoD2=lod, ALS=np.isfinite(d))


def checks():
    out = {}
    sites_cfg = json.loads(Path("/repo/configs/phd/main_prep_discard_rule_v1/sites_v1.json").read_text())["sites"]
    mid = [s for s in sites_cfg if s["id"] == "B173_middle"][0]["faces_gml"]
    for name, site, gmls in (("R1_translucent_roof", "R1rep_b10", [R1_HALL_GML]), ("B173_glass_gutters_nb", "B173nb_b10", mid), ("B173_glass_gutters_b0", "B173_b0", mid)):
        mem = site_faces(site, gmls)
        e = {}
        for prior in ("LoD2", "ALS"):
            a = np.load(OUT / "regions_v3" / f"regions_ext_v3_{site}_{prior}.npz")
            m = mem[prior] & a["in_eval"]
            c = a["code_ext_v3"]
            area = a["area"]
            e[prior] = dict(patches=int(m.sum()), area_m2=round(float(area[m].sum()), 1),
                            by_code={str(k): int(v) for k, v in zip(*np.unique(c[m], return_counts=True))},
                            premise_violation=int((m & a["premise_violation"]).sum()), premise_violation_area_m2=round(float(area[m & a["premise_violation"]].sum()), 1),
                            within_threshold=int((m & a["obs_within_threshold"]).sum()), share_of_obs_error_in_violation=round(float((m & a["premise_violation"]).sum()) / max(int((m & (c == 3)).sum()), 1), 4))
        out[name] = e
    out["stop_r1_translucent_missing"] = bool(sum(out["R1_translucent_roof"][p]["premise_violation"] for p in ("LoD2", "ALS")) == 0)
    return out


def outline(ax, uv, moved, cell=0.25):
    import scipy.ndimage as ndi
    if not moved.any():
        return
    lo = uv[moved].min(0) - 2 * cell
    q = np.floor((uv[moved] - lo) / cell).astype(int)
    g = np.zeros(q.max(0)[::-1] + 3, bool)
    g[q[:, 1], q[:, 0]] = True
    g = ndi.binary_closing(ndi.binary_dilation(g, iterations=1), iterations=1)
    xs = lo[0] + (np.arange(g.shape[1]) + 0.5) * cell
    ys = lo[1] + (np.arange(g.shape[0]) + 0.5) * cell
    ax.contour(xs, ys, g.astype(float), levels=[0.5], colors="k", linewidths=0.9)


def draw_maps(site):
    b = boxes()[SITES[site]]
    fig, axs = plt.subplots(1, 3, figsize=(19, 6.6), constrained_layout=True)
    for prior in ("LoD2", "ALS"):
        R = np.load(OUT / "regions_v3" / f"regions_ext_v3_{site}_{prior}.npz")
        c2, c3, kind = R["code_ext_v2_prev"], R["code_ext_v3"], R["kind"]
        uv = xy_to_uv(R["centre"][:, :2])
        panels = [(0, 1), (1, 2)] if prior == "LoD2" else [(2, 1)]
        for ax_i, kv in panels:
            ax = axs[ax_i]
            m = R["in_eval"] & (kind == kv)
            for c in [0, 2, 4, 5, 3, 12, 13, 14, 11]:
                mm = m & (c3 == c)
                ax.scatter(uv[mm, 0], uv[mm, 1], s=0.6 if kv == 1 else 1.6, c=COL[c], marker="s", linewidths=0, rasterized=True)
            mv = m & (c2 != c3)
            outline(ax, uv, mv)
            ax.plot([b["eval_u"][0], b["eval_u"][1], b["eval_u"][1], b["eval_u"][0], b["eval_u"][0]],
                    [b["eval_v"][0], b["eval_v"][0], b["eval_v"][1], b["eval_v"][1], b["eval_v"][0]], "k-", lw=0.8)
            ax.set_aspect("equal")
            ax.set_xlabel("u (m)")
            ax.set_ylabel("v (m)")
            title = {(0, 1): "LoD2 지붕", (1, 2): "LoD2 벽 (위에서 본 자리)", (2, 1): "항공 LiDAR"}[(ax_i, kv)]
            ax.set_title(f"{title} — v2에서 바뀐 패치 {int(mv.sum()):,}개(검은 윤곽 안)", fontsize=11)
    handles = [Patch(color=COL[c], label=KO[c]) for c in ORDER] + [Line2D([], [], color="k", lw=1, label="v2에서 바뀐 패치의 윤곽")]
    fig.legend(handles=handles, loc="lower center", ncol=5, fontsize=10, bbox_to_anchor=(0.5, -0.1))
    fig.suptitle(f"{site} 영역 v3 (네 상자 공통의 참값 높이 맞춤으로 다시 냄; 학습 전 자료)", fontsize=12, x=0.01, ha="left")
    fig.savefig(OUT / "figs" / f"regions_v3_{site}.png", dpi=110, bbox_inches="tight")
    plt.close(fig)


if __name__ == "__main__":
    {"mvs": lambda: mvs_read(sys.argv[2:] or list(SITES)), "check": check, "run": run, "maps": lambda: [draw_maps(s) for s in SITES]}[sys.argv[1]]()
