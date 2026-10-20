"""PHD-MAIN-FIXTEST-v1 일 1 (jointbuildgs:dev, CPU): the image share and the prior share of the tolerance, and the band end w of fix A,
for one search region and prior, with the data and the procedure of tau. No ground truth enters w.

  python w1_shares.py <B0|R2|R1> <LoD2|ALS> [--pairs 10] [--boot 1000] [--seed 0]

tau (order table A) = the discard task's s03 stage 1 (scripts/phd/main_prep_discard_rule_v1/s03_stage1.py, module v5 = v6 for the
conversion, tolerance and registration): one residual = one pixel of one training view of the region, r = (MVS geometric depth - prior
render depth) x f (conversion.factor: vertical on roof-like, along the normal on wall-like faces; r = prior - MVS in height / outward
offset), pixels of building faces of the registered prior with a valid MVS depth whose hit lies inside the region; up to 20,000 random
pixels per view and kind; tau = 2.5 x NMAD after one 3-NMAD clip (tolerance.robust_width). This script re-renders the same prior with
the same shift on the same views and MVS, and finds every hit's patch in the v6 moved store (the search-region store of the CH6 task).

image share (order 5.2, residual = one pixel and one view): the centre of every patch of the region (its moved store centre, on the
prior surface) is projected into every training view; a view counts when the pixel there hits that same patch and is a tau residual
pixel (building face, valid MVS depth, inside the region); r of that pixel is the residual of the view. Per patch, at most --pairs
random distinct view pairs (seeded); d = r_i - r_j pooled per kind; sigma_image = NMAD(d) / sqrt(2) (NMAD = 1.4826 x median absolute
deviation, no clip; the clipped value is recorded too). Bootstrap: patches drawn with replacement --boot times (seeded) -> 95 % interval
of sigma_image and of w.
prior share and w (5.3): NMAD = tau / 2.5; sigma_prior = sqrt(NMAD^2 - sigma_image^2); w = min(2.5 sigma_prior, tau); sigma_image >=
NMAD -> 'not separable', w = tau.
records (5.4): residual median (all tau residuals of the stored sample, before and after the clip); plane-fit spread of flat roofs
(prior patches with the cell normal within 5 deg of the vertical, connected within a surface (centres within 0.375 m), >= 10 m^2): a
plane fitted per piece (least squares, one 3-NMAD clip, refit) to the prior surface (patch centres), the MVS points (tau residual
pixels of the piece, C + d_MVS ray) and the ground truth points (the CH6 owner table of the piece's patches); pooled NMAD of the
residuals; ground-truth shares: tau residual pixels (same per-view cap of 20,000 per kind, seeded) of patches with a ground-truth label
(the CH6 task's label reading, labels_of = the fill task 8.4 rule): prior - GT = -g, MVS - GT = -r - g (g = gt_med = GT - prior), NMAD and
median, split outside / inside the four boxes' evaluation ranges (in_eval_rect); check = (NMAD_prior_gt^2 + NMAD_mvs_gt^2) / NMAD^2.
Outputs /out/prep/w1/<R>_<P>.json, .npz. scientific_verdict: null."""
import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, "/repo/scripts/phd/main_stage0_v1")
sys.path.insert(0, "/repo/scripts/phd/ch6_support_v1")
sys.path.insert(0, "/repo")
from common import GRID_H, GRID_W, PREP, Views, inside_range, read_depth_bin  # noqa: E402
from s03_stage1_v6 import Prior  # noqa: E402
from src.phd.prior_propagation_v6 import conversion as conv  # noqa: E402
from src.phd.prior_propagation_v6 import locations as locs  # noqa: E402
from src.phd.prior_propagation_v6 import tolerance as tol  # noqa: E402
import ch6_common as C6  # noqa: E402

DR = Path("/dr")
CH6 = Path("/ph/ch6_support_v1/PHD-CH6-SUPPORT-v1")
OUT = Path("/out/prep/w1")
NMAD_C = 1.4826
CAP = 20000          # tau's per-view and per-kind cap (s03_stage1.py pass 2)
COS5 = float(np.cos(np.radians(5.0)))


def nmad(x):
    x = np.asarray(x, np.float64)
    x = x[np.isfinite(x)]
    if x.size == 0:
        return float("nan"), float("nan")
    m = float(np.median(x))
    return m, float(NMAD_C * np.median(np.abs(x - m)))


def clipped_nmad(x):
    st = tol.robust_width(x)
    return st["median_after"], st["nmad_after"]


def _cw(cw, i):
    return cw[i - 1] if i > 0 else 0.0


def _wmedian(d, cw, a, c):
    """weighted median of the sorted values d[a:c] (cumulative weights cw over the whole array)."""
    base, tot = _cw(cw, a), _cw(cw, c) - _cw(cw, a)
    k = a + int(np.searchsorted(cw[a:c], base + 0.5 * tot, side="left"))
    return float(d[min(k, c - 1)]), tot


def _wmad(d, cw, a, c, m, tot):
    """weighted median of |d - m| over d[a:c] by bisection."""
    lo_, hi_ = 0.0, float(max(abs(d[c - 1] - m), abs(m - d[a])))
    for _ in range(50):
        s = 0.5 * (lo_ + hi_)
        aa = max(a, int(np.searchsorted(d, m - s, side="left"))); cc = min(c, int(np.searchsorted(d, m + s, side="right")))
        if _cw(cw, cc) - _cw(cw, aa) >= 0.5 * tot:
            hi_ = s
        else:
            lo_ = s
    return hi_


def boot_nmad(d_sorted, unit_sorted, n_units, rng, n_boot, clip=3.0):
    """for bootstrap draws of the patches (multiplicity weights on their differences): (NMAD, NMAD after one clip-NMAD clip) of the
    pooled differences = tolerance.robust_width's statistics with weights."""
    plain, clipped = np.empty(n_boot), np.empty(n_boot)
    n = len(d_sorted)
    for b in range(n_boot):
        mult = np.bincount(rng.integers(0, n_units, n_units), minlength=n_units).astype(np.float64)
        cw = np.cumsum(mult[unit_sorted])
        m1, tot = _wmedian(d_sorted, cw, 0, n)
        s1 = NMAD_C * _wmad(d_sorted, cw, 0, n, m1, tot)
        a = int(np.searchsorted(d_sorted, m1 - clip * s1, side="left")); c = int(np.searchsorted(d_sorted, m1 + clip * s1, side="right"))
        m2, tot2 = _wmedian(d_sorted, cw, a, c)
        s2 = NMAD_C * _wmad(d_sorted, cw, a, c, m2, tot2)
        plain[b], clipped[b] = s1, s2
    return plain, clipped


def plane_resid(P):
    """least-squares plane z = a x + b y + c, one 3-NMAD clip, refit; residuals of all points (metres, vertical)."""
    if len(P) < 10:
        return None
    X = P - P.mean(0)
    A = np.column_stack([X[:, 0], X[:, 1], np.ones(len(X))])
    c, *_ = np.linalg.lstsq(A, X[:, 2], rcond=None)
    res = X[:, 2] - A @ c
    m, s = nmad(res)
    keep = np.abs(res - m) <= 3 * s if s > 0 else np.ones(len(res), bool)
    if keep.sum() >= 10:
        c, *_ = np.linalg.lstsq(A[keep], X[keep, 2], rcond=None)
        res = X[:, 2] - A @ c
    return res


def pieces_of(st, loc_in):
    """flat roof pieces of the prior: patches with the cell normal within 5 deg of the vertical, connected inside a surface."""
    from scipy.sparse import coo_matrix
    from scipy.sparse.csgraph import connected_components
    from scipy.spatial import cKDTree
    n = np.cross(st["loc_t1"], st["loc_t2"]); nn = np.linalg.norm(n, axis=1)
    nz = np.where(nn > 1e-12, np.abs(n[:, 2]) / np.maximum(nn, 1e-12), 0.0)
    flat = loc_in & (np.asarray(st["loc_kind"]) == 1) & (nz >= COS5)
    idx = np.nonzero(flat)[0]
    piece = np.full(len(flat), -1, np.int64)
    if len(idx) == 0:
        return piece, []
    cen = np.asarray(st["loc_center"], np.float64)[idx]
    surf = np.asarray(st["loc_surface"])[idx]
    pairs = cKDTree(cen).query_pairs(0.375, output_type="ndarray")
    pairs = pairs[surf[pairs[:, 0]] == surf[pairs[:, 1]]]
    g = coo_matrix((np.ones(len(pairs)), (pairs[:, 0], pairs[:, 1])), shape=(len(idx), len(idx)))
    ncomp, lab = connected_components(g, directed=False)
    area = np.bincount(lab, weights=np.asarray(st["loc_area"], np.float64)[idx], minlength=ncomp)
    big = np.nonzero(area >= 10.0)[0]
    remap = np.full(ncomp, -1, np.int64); remap[big] = np.arange(len(big))
    piece[idx] = remap[lab]
    return piece, area[big].tolist()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("region", choices=["B0", "R2", "R1"]); ap.add_argument("prior", choices=["LoD2", "ALS"])
    ap.add_argument("--pairs", type=int, default=10); ap.add_argument("--boot", type=int, default=1000); ap.add_argument("--seed", type=int, default=0)
    a = ap.parse_args()
    t_all = time.time()
    R, PN = a.region, a.prior
    OUT.mkdir(parents=True, exist_ok=True)
    rng_all = json.loads((PREP / "step01/ranges.json").read_text())
    rdef = rng_all[R]
    summ = json.loads((DR / "s52/s03" / R / PN / "summary.json").read_text())
    shift = np.asarray(summ["registration"]["shift_applied"], np.float64)
    TAU = {conv.KIND_ROOF: float(summ["tolerance"]["roof"]["tau"]), conv.KIND_WALL: float(summ["tolerance"]["wall"]["tau"])}
    spec = {k: summ["tolerance"][k].get("spec") for k in ("roof", "wall")}
    views_all = json.loads((PREP / "step01/views.json").read_text())["views"][R]["train"]
    mvs = DR / "mvs" / R
    views = [n for n in views_all if (mvs / "stereo/depth_maps" / f"{n}.geometric.bin").exists()]
    V = Views()
    pr = Prior(DR / "s02" / R, PN)
    pr.shift = shift
    sc, _ = pr.scene()
    st = locs.move_store(pr.store, shift)
    L = len(st["loc_area"])
    loc_in = inside_range(st["loc_center"][:, :2], rdef)
    # the CH6 search-region run of v6 must have the same store (labels are indexed on it)
    U6 = np.load(CH6 / "t5/s03" / R / PN / "units.npz", allow_pickle=True)
    same_store = bool(len(U6["loc_area"]) == L and np.allclose(U6["loc_center"], st["loc_center"], atol=1e-6))
    if not same_store:
        raise RuntimeError("the store differs from the CH6 search-region store: the labels cannot be read")
    lab, gmed, gtau, gex = C6.labels_of(CH6 / "t5/gt" / R, PN, R)
    has_gt = (lab >= 0) & ~gex & np.isfinite(gmed)
    in_box = np.zeros(L, bool)
    uv = C6.xy_to_uv(np.asarray(st["loc_center"], np.float64)[:, :2])
    for b in ("B0", "B173nb", "B173", "R1rep"):
        in_box |= C6.in_eval_rect(uv, b)
    piece, piece_area = pieces_of(st, loc_in)
    n_piece = len(piece_area)
    kind_loc = np.asarray(st["loc_kind"]).astype(np.int64)
    cen = np.asarray(st["loc_center"], np.float64)
    cand = np.nonzero(loc_in & np.isin(kind_loc, (1, 2)))[0]
    rng = np.random.default_rng(a.seed)
    rec_u, rec_v, rec_r = [], [], []
    tau_samp = {1: [], 2: []}
    gt_rows = {1: [], 2: []}           # (minus g, minus r minus g, in_box, unit)
    mvs_pts = []                       # (piece, x, y, z)
    t0 = time.time()
    for vi, n in enumerate(views):
        Dr = V.rays(n); Cc = V.C(n)
        t, tri = sc.cast(Cc, Dr)
        dm = read_depth_bin(mvs / "stereo/depth_maps" / f"{n}.geometric.bin")
        assert dm.shape == (GRID_H, GRID_W)
        a1 = np.isfinite(dm) & (dm > 0)
        hit = tri >= 0
        idx = np.nonzero(hit.ravel())[0]
        trif = tri.ravel()[idx]
        d = Dr.reshape(-1, 3)[idx].astype(np.float64)
        nrm = pr.n_used[trif]
        f = conv.factor(nrm, d)
        r = (dm.ravel()[idx].astype(np.float64) - t.ravel()[idx]) * f
        X = Cc[None, :] + t.ravel()[idx][:, None] * d
        inr = inside_range(X[:, :2], rng_all[R])
        bf = pr.bface_tri[trif]
        kind = conv.surface_kind(nrm[:, 2])
        a1v = a1.ravel()[idx]
        sel = bf & a1v & inr
        ci = pr.ci_of_tri[trif]
        okl = ci >= 0
        loc = np.full(len(idx), -1, np.int64)
        if okl.any():
            loc[okl] = locs.locate(st, ci[okl], X[okl])
        # (a) tau's residual set (own random cap; tau itself comes from the stored samples)
        for k in (1, 2):
            s_ = np.nonzero(sel & (kind == k))[0]
            if len(s_) > CAP:
                s_ = rng.choice(s_, CAP, replace=False)
            tau_samp[k].append(r[s_].astype(np.float32))
            gs = s_[(loc[s_] >= 0) & has_gt[np.maximum(loc[s_], 0)]]
            gl = loc[gs]
            g = gmed[gl]
            gt_rows[k].append(np.column_stack([-g, -r[gs] - g, in_box[gl], gl]).astype(np.float64))
        # (b) centre pixel of every candidate patch
        H, W = GRID_H, GRID_W
        lm = np.full(H * W, -1, np.int64); lm[idx] = loc
        rm = np.full(H * W, np.nan); rm[idx] = r
        sm = np.zeros(H * W, bool); sm[idx] = sel
        uu, vv, zz = V.project(n, cen[cand])
        ok = np.isfinite(uu) & np.isfinite(vv) & (zz > 0.01)
        ui = np.floor(np.where(ok, uu, -1)).astype(np.int64); vj = np.floor(np.where(ok, vv, -1)).astype(np.int64)
        ok &= (ui >= 0) & (ui < W) & (vj >= 0) & (vj < H)
        k_ = np.where(ok, vj * W + ui, 0)
        ok &= (lm[k_] == cand) & sm[k_]
        rec_u.append(cand[ok].astype(np.int32)); rec_v.append(np.full(int(ok.sum()), vi, np.int16)); rec_r.append(rm[k_[ok]].astype(np.float32))
        # (c) MVS points of the flat pieces (10 % of the pixels, seeded)
        if n_piece:
            pm = sel & (loc >= 0) & (piece[np.maximum(loc, 0)] >= 0)
            pk = np.nonzero(pm)[0]
            if len(pk):
                pk = pk[rng.random(len(pk)) < 0.10]
                XM = Cc[None, :] + dm.ravel()[idx][pk][:, None].astype(np.float64) * d[pk]
                mvs_pts.append(np.column_stack([piece[loc[pk]], XM]))
        if vi % 50 == 0:
            print(f"[w1] {R} {PN} view {vi}/{len(views)} {time.time() - t0:.0f}s", flush=True)
    t_views = time.time() - t0
    U_ = np.concatenate(rec_u); V_ = np.concatenate(rec_v); R_ = np.concatenate(rec_r).astype(np.float64)
    del rec_u, rec_v, rec_r
    order = np.lexsort((V_, U_)); U_, V_, R_ = U_[order], V_[order], R_[order]
    starts = np.r_[0, np.nonzero(np.diff(U_))[0] + 1]; ends = np.r_[starts[1:], len(U_)]
    mcnt = ends - starts
    prng = np.random.default_rng(a.seed + 1)
    PI, PJ = [], []
    # patches with at most --pairs view pairs: every pair; others: --pairs random ordered pairs of distinct views drawn with
    # replacement, duplicates (unordered) removed -> at most --pairs random distinct pairs
    for m in range(2, 64):
        if m * (m - 1) // 2 > a.pairs:
            m_small_max = m - 1
            break
    for m in range(2, m_small_max + 1):
        sel_m = np.nonzero(mcnt == m)[0]
        if not len(sel_m):
            continue
        comb = np.array([(i, j) for i in range(m) for j in range(i + 1, m)], np.int64)
        PI.append((starts[sel_m][:, None] + comb[None, :, 0]).ravel()); PJ.append((starts[sel_m][:, None] + comb[None, :, 1]).ravel())
    big = np.nonzero(mcnt > m_small_max)[0]
    if len(big):
        mb = mcnt[big][:, None]
        i_ = np.floor(prng.random((len(big), a.pairs)) * mb).astype(np.int64)
        j_ = np.floor(prng.random((len(big), a.pairs)) * (mb - 1)).astype(np.int64)
        j_ = j_ + (j_ >= i_)
        lo_, hi_ = np.minimum(i_, j_), np.maximum(i_, j_)
        key = (np.arange(len(big))[:, None] * 4096 + lo_) * 4096 + hi_
        uk = np.unique(key.ravel())
        bi = uk // (4096 * 4096); li = (uk // 4096) % 4096; hj = uk % 4096
        PI.append(starts[big][bi] + li); PJ.append(starts[big][bi] + hj)
    PI = np.concatenate(PI) if PI else np.zeros(0, np.int64); PJ = np.concatenate(PJ) if PJ else np.zeros(0, np.int64)
    sign = np.where(prng.random(len(PI)) < 0.5, 1.0, -1.0)
    dd = sign * (R_[PI] - R_[PJ]); du = U_[PI].astype(np.int64); dk = kind_loc[du]
    n_view_hist = np.bincount(np.minimum(mcnt, 100), minlength=101)
    res = dict(task_id="PHD-MAIN-FIXTEST-v1", item="일 1", region=R, prior=PN, views=len(views), views_without_depth_map=sorted(set(views_all) - set(views)),
               shift=shift.tolist(), tau=TAU, spec=spec, store_same_as_ch6=same_store, mvs=str(mvs), mesh_dir=f"/dr/s02/{R}",
               residual_kind="pixel x view (s03_stage1.py:145, pass 2 :244-261)", method_image_share="patch centre projected per view, pairs of views (order 5.2 first case)",
               pairs_per_patch_max=a.pairs, boot=a.boot, seed=a.seed, seconds=dict(views=round(t_views, 1)), rows={},
               centre_views_per_patch_hist_capped100=n_view_hist.tolist(), scientific_verdict=None)
    stored = np.load(DR / "s52/s03" / R / PN / "residual_samples.npz")
    arrays = {}
    for k, kn in ((1, "roof"), (2, "wall")):
        if PN == "ALS" and k == 2:
            continue
        x = stored[kn].astype(np.float64)
        st_w = tol.robust_width(x)
        mine = np.concatenate(tau_samp[k]) if tau_samp[k] else np.zeros(0)
        st_m = tol.robust_width(mine) if mine.size else None
        tau_k = TAU[k]
        NM = tau_k / 2.5
        sel_k = dk == k
        d_k = dd[sel_k]; u_k = du[sel_k]
        m_d, s_d = nmad(d_k)                                    # record: before the clip
        st_d = tol.robust_width(d_k)                            # tau's statistic: NMAD after one 3-NMAD clip (primary)
        s_dc = st_d["nmad_after"]
        sig_img = s_dc / np.sqrt(2.0)
        sep = bool(sig_img < NM)
        sig_pr = float(np.sqrt(NM ** 2 - sig_img ** 2)) if sep else float("nan")
        w = float(min(2.5 * sig_pr, tau_k)) if sep else tau_k
        sig_img_plain = s_d / np.sqrt(2.0)                      # record: the same with the NMAD before the clip
        sep_p = bool(sig_img_plain < NM)
        w_plain = float(min(2.5 * np.sqrt(NM ** 2 - sig_img_plain ** 2), tau_k)) if sep_p else tau_k
        # bootstrap over patches
        uu_, inv = np.unique(u_k, return_inverse=True)
        o = np.argsort(d_k, kind="stable")
        t_b = time.time()
        if d_k.size:
            bp, bc = boot_nmad(d_k[o], inv[o], len(uu_), np.random.default_rng(a.seed + 2 + k), a.boot)
        else:
            bp = bc = np.zeros(0)
        bs = bc / np.sqrt(2.0)
        sp_b = np.sqrt(np.clip(NM ** 2 - bs ** 2, 0, None))
        wb = np.where(bs < NM, np.minimum(2.5 * sp_b, tau_k), tau_k)
        # ground-truth shares (tau's statistic; the NMAD before the clip recorded)
        G = np.concatenate(gt_rows[k]) if gt_rows[k] else np.zeros((0, 4))
        gtv = {}
        for zone, mz in (("outside", G[:, 2] == 0), ("inside", G[:, 2] == 1), ("all", np.ones(len(G), bool))):
            if mz.sum() < 10:
                gtv[zone] = dict(pixels=int(mz.sum()), patches=int(len(np.unique(G[mz, 3]))))
                continue
            sp_w, sm_w = tol.robust_width(G[mz, 0]), tol.robust_width(G[mz, 1])
            sp_, sm_ = sp_w["nmad_after"], sm_w["nmad_after"]
            gtv[zone] = dict(pixels=int(mz.sum()), patches=int(len(np.unique(G[mz, 3]))),
                             prior_minus_gt_median=sp_w["median_after"], prior_minus_gt_nmad=sp_, mvs_minus_gt_median=sm_w["median_after"], mvs_minus_gt_nmad=sm_,
                             check=(sp_ ** 2 + sm_ ** 2) / NM ** 2,
                             before_clip=dict(prior_minus_gt_median=sp_w["median_before"], prior_minus_gt_nmad=sp_w["nmad_before"],
                                              mvs_minus_gt_median=sm_w["median_before"], mvs_minus_gt_nmad=sm_w["nmad_before"]))
        row = dict(kind=kn, n_tau_residuals=int(x.size), tau=tau_k, tau_recomputed=st_w["width"], NMAD=NM, nmad_recomputed=st_w["nmad_after"],
                   residual_median_all=st_w["median_before"], residual_median_clipped=st_w["median_after"], clipped_share=st_w["clipped_share"],
                   own_sample=dict(n=int(mine.size), width=None if st_m is None else st_m["width"], nmad_after=None if st_m is None else st_m["nmad_after"],
                                   note="this script's own random cap of the same pixels (a re-render check; tau itself is the stored sample's)"),
                   image=dict(patches_with_pairs=int(len(uu_)), pairs=int(d_k.size), median_diff=m_d, nmad_diff_clipped=s_dc, clipped_share=st_d["clipped_share"],
                              sigma_image=sig_img, sigma_image_ci95=[float(np.percentile(bs, 2.5)), float(np.percentile(bs, 97.5))] if bs.size else None,
                              boot_seconds=round(time.time() - t_b, 1),
                              before_clip=dict(nmad_diff=s_d, sigma_image=sig_img_plain, separable=sep_p, w=w_plain,
                                               sigma_image_ci95=[float(np.percentile(bp, 2.5) / np.sqrt(2)), float(np.percentile(bp, 97.5) / np.sqrt(2))] if bp.size else None)),
                   separable=sep, sigma_prior=sig_pr, w=w, w_ci95=[float(np.percentile(wb, 2.5)), float(np.percentile(wb, 97.5))] if wb.size else None,
                   w_over_tau=w / tau_k, gt=gtv, spec_agency=spec[kn],
                   statistic="NMAD after one 3-NMAD clip (tolerance.robust_width = tau's statistic) for sigma_image and the ground-truth shares; "
                             "before-clip values recorded")
        res["rows"][kn] = row
        arrays[f"{kn}_diff"] = d_k.astype(np.float32); arrays[f"{kn}_diff_unit"] = u_k.astype(np.int32)
        arrays[f"{kn}_boot_sigma_image"] = bs.astype(np.float32); arrays[f"{kn}_boot_w"] = wb.astype(np.float32)
        arrays[f"{kn}_gt_rows"] = G.astype(np.float32)
    # plane-fit spread of the flat roof pieces
    pf = dict(pieces=n_piece, area_m2=float(np.sum(piece_area)), rule="cell normal within 5 deg of the vertical, roof-like, connected inside a surface "
              "(centres within 0.375 m), >= 10 m^2; least squares plane, one 3-NMAD clip, refit; pooled NMAD of the residuals (each piece centred on its median)")
    if n_piece:
        def pooled(groups):
            rr, per = [], []
            for P_ in groups:
                if P_ is None or len(P_) < 10:
                    continue
                e = plane_resid(np.asarray(P_, np.float64))
                if e is None:
                    continue
                rr.append(e - np.median(e)); per.append(nmad(e)[1])
            allr = np.concatenate(rr) if rr else np.zeros(0)
            stw = tol.robust_width(allr) if allr.size >= 10 else dict(nmad_after=None, nmad_before=None)
            return dict(points=int(allr.size), pieces_used=len(rr), nmad_pooled=stw["nmad_after"], nmad_pooled_before_clip=stw["nmad_before"],
                        nmad_piece_median_before_clip=float(np.median(per)) if per else None)
        pid = piece[piece >= 0]; ploc = np.nonzero(piece >= 0)[0]
        o = np.argsort(pid, kind="stable"); pid, ploc = pid[o], ploc[o]
        b_ = np.r_[0, np.nonzero(np.diff(pid))[0] + 1, len(pid)]
        pf["prior_surface"] = pooled([cen[ploc[b_[i]:b_[i + 1]]] for i in range(len(b_) - 1)])
        M_ = np.concatenate(mvs_pts) if mvs_pts else np.zeros((0, 4))
        if len(M_):
            o = np.argsort(M_[:, 0], kind="stable"); M_ = M_[o]
            bm = np.r_[0, np.nonzero(np.diff(M_[:, 0]))[0] + 1, len(M_)]
            groups = []
            for i in range(len(bm) - 1):
                g_ = M_[bm[i]:bm[i + 1], 1:]
                if len(g_) > 5000:
                    g_ = g_[np.random.default_rng(a.seed + 7 + i).choice(len(g_), 5000, replace=False)]
                groups.append(g_)
            pf["mvs"] = pooled(groups)
        own_file = CH6 / "t5/gt" / R / f"gt_owner_uls_{PN}.npz"      # B0: the ULS cloud's owner table (gt_owner_<P> there is gt_clean's)
        if not own_file.exists():
            own_file = CH6 / "t5/gt" / R / f"gt_owner_{PN}.npz"
        pf["gt_owner_file"] = str(own_file)
        ow = np.load(own_file)
        inp = piece[ow["patch"]] >= 0
        if inp.any():
            gp = np.load(CH6 / "t5/gt" / R / "gt_points.npz")["xyz"]
            pts = ow["point"][inp]; pp = piece[ow["patch"][inp]]
            o = np.argsort(pp, kind="stable"); pts, pp = pts[o], pp[o]
            bg = np.r_[0, np.nonzero(np.diff(pp))[0] + 1, len(pp)]
            xyz = gp[pts].astype(np.float64)
            del gp
            groups = []
            for i in range(len(bg) - 1):
                g_ = xyz[bg[i]:bg[i + 1]]
                if len(g_) > 5000:
                    g_ = g_[np.random.default_rng(a.seed + 11 + i).choice(len(g_), 5000, replace=False)]
                groups.append(g_)
            pf["gt"] = pooled(groups)
    res["plane_fit"] = pf
    res["seconds"]["total"] = round(time.time() - t_all, 1)
    (OUT / f"{R}_{PN}.json").write_text(json.dumps(res, indent=1, default=float))
    np.savez_compressed(OUT / f"{R}_{PN}.npz", **arrays)
    print("[w1] done", R, PN, json.dumps({k: dict(tau=v["tau"], sigma_image=v["image"]["sigma_image"], w=v["w"], ci=v["w_ci95"]) for k, v in res["rows"].items()}),
          json.dumps({k: pf.get(k, {}).get("nmad_pooled") for k in ("prior_surface", "mvs", "gt")}), f"{res['seconds']['total']}s", flush=True)


if __name__ == "__main__":
    main()
